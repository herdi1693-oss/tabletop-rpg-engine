import os
import re
import subprocess
import unittest
from pathlib import PurePosixPath

ROOT_COMMIT = "93a622e92caa0312fc657b82977f016bafacd2e5"
ROOT_TREE = "80c2cdb27242247344fb9db960469e02f9f43d14"

ALLOWED_COMMIT_EMAILS = {
    "noreply@github.com",
}
ALLOWED_EMAIL_SUFFIXES = (
    "@users.noreply.github.com",
)

FORBIDDEN_PATH_PARTS = {
    ".env",
    "private",
    "recovery",
    "recoveries",
    "save",
    "saves",
    "secrets",
    "source_compat",
}

FORBIDDEN_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
}

FORBIDDEN_SUFFIXES = {
    ".7z",
    ".db",
    ".der",
    ".gz",
    ".jpeg",
    ".jpg",
    ".key",
    ".p12",
    ".pem",
    ".pfx",
    ".pdf",
    ".png",
    ".sqlite",
    ".tar",
    ".webp",
    ".zip",
}

SECRET_PATTERNS = {
    "github_token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "aws_access_key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    "credentialed_postgres_url": re.compile(rb"postgres(?:ql)?://[^\s:/]+:[^@\s]+@[^\s]+", re.IGNORECASE),
    "credentialed_http_url": re.compile(rb"https?://[^\s/:@]+:[^@\s]+@[^\s]+", re.IGNORECASE),
}

MAX_TEXT_BLOB_BYTES = 2_000_000


def git(*args, text=True):
    return subprocess.check_output(["git", *args], text=text).strip()


def target_sha():
    return os.environ.get("PUBLIC_GUARD_TARGET_SHA") or git("rev-parse", "HEAD")


class PublicRepositoryBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = target_sha()

    def test_history_has_exact_clean_root(self):
        roots = git("rev-list", "--max-parents=0", self.target).splitlines()
        self.assertEqual([ROOT_COMMIT], roots)
        root_tree = git("show", "-s", "--format=%T", ROOT_COMMIT)
        self.assertEqual(ROOT_TREE, root_tree)

    def test_reachable_commit_identities_are_public_neutral(self):
        commits = git("rev-list", self.target).splitlines()
        self.assertGreaterEqual(len(commits), 1)
        for commit in commits:
            raw = git("show", "-s", "--format=%ae%n%ce", commit).splitlines()
            self.assertEqual(2, len(raw))
            for email in raw:
                allowed = (
                    email in ALLOWED_COMMIT_EMAILS
                    or email.endswith(ALLOWED_EMAIL_SUFFIXES)
                )
                self.assertTrue(
                    allowed,
                    msg=f"non-neutral Git identity reachable at {commit}: {email}",
                )

    def test_tracked_paths_exclude_private_state_and_heavy_assets(self):
        paths = git("ls-tree", "-r", "--name-only", self.target).splitlines()
        self.assertGreaterEqual(len(paths), 1)
        for raw_path in paths:
            path = PurePosixPath(raw_path)
            lowered_parts = {part.casefold() for part in path.parts}
            self.assertTrue(
                FORBIDDEN_PATH_PARTS.isdisjoint(lowered_parts),
                msg=f"forbidden private-state path component: {raw_path}",
            )
            self.assertNotIn(
                path.name.casefold(),
                FORBIDDEN_FILENAMES,
                msg=f"forbidden sensitive filename: {raw_path}",
            )
            self.assertNotIn(
                path.suffix.casefold(),
                FORBIDDEN_SUFFIXES,
                msg=f"forbidden binary/heavy asset type: {raw_path}",
            )

    def test_tracked_content_has_no_obvious_credentials_or_binary_payloads(self):
        paths = git("ls-tree", "-r", "--name-only", self.target).splitlines()
        for path in paths:
            data = subprocess.check_output(["git", "show", f"{self.target}:{path}"])
            self.assertLessEqual(
                len(data),
                MAX_TEXT_BLOB_BYTES,
                msg=f"oversized public text blob: {path}",
            )
            self.assertNotIn(
                b"\x00",
                data,
                msg=f"binary payload forbidden in public engine source: {path}",
            )
            for label, pattern in SECRET_PATTERNS.items():
                self.assertIsNone(
                    pattern.search(data),
                    msg=f"possible {label} material in public file: {path}",
                )


if __name__ == "__main__":
    unittest.main()
