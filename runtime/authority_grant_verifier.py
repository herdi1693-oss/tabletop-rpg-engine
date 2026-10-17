#!/usr/bin/env python3
"""Trusted-host verification side for Runtime authority grants.

Security boundary:
- generic verifier construction remains a library primitive for broker/QA code;
- the live Runtime Host integration never accepts a verifier/keyring from a
  visual/request caller;
- the live Runtime Host verification root is bootstrapped exactly once from a
  supervisor-inherited file descriptor before untrusted request handling begins;
- that process-global root cannot be replaced after bootstrap;
- private signing material is never loaded here;
- there is no sign/mint/register-authority API in this module.

The process/bootstrap boundary is the security primitive. Python privacy inside
one compromised interpreter is not treated as a security boundary.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from runtime.authority_grant_protocol import (
    AuthorityGrantEnvelope,
    GrantBindingExpectation,
    canonical_grant_payload,
    validate_grant_claims,
)

DEFAULT_OPENSSL_BINARY = "openssl"
DEFAULT_VERIFY_TIMEOUT_SECONDS = 5
MAX_BOOTSTRAP_KEYRING_BYTES = 256 * 1024


@dataclass(frozen=True)
class BootstrapVerificationKeyring:
    """Public verification roots supplied by trusted bootstrap/supervisor."""

    root_id: str
    ed25519_public_keys_pem: Mapping[str, str]
    revoked_key_ids: frozenset[str]


class AuthorityGrantVerifier:
    """Fail-closed Ed25519 verifier for broker-issued authority grants.

    This class is intentionally reusable by tests/tooling. Possessing an
    instance does not make it the Runtime Host trust root. The live Runtime Host
    path below uses only the once-bootstrapped process-global verifier.
    """

    def __init__(
        self,
        keyring: BootstrapVerificationKeyring,
        *,
        openssl_binary: str = DEFAULT_OPENSSL_BINARY,
        verify_timeout_seconds: int = DEFAULT_VERIFY_TIMEOUT_SECONDS,
    ) -> None:
        if not isinstance(keyring, BootstrapVerificationKeyring):
            raise TypeError("BOOTSTRAP_VERIFICATION_KEYRING_REQUIRED")
        if type(keyring.root_id) is not str or not keyring.root_id:
            raise ValueError("BOOTSTRAP_VERIFICATION_ROOT_ID_REQUIRED")
        if not keyring.ed25519_public_keys_pem:
            raise ValueError("BOOTSTRAP_VERIFICATION_KEYS_REQUIRED")
        if type(verify_timeout_seconds) is not int or verify_timeout_seconds <= 0:
            raise ValueError("AUTHORITY_GRANT_VERIFY_TIMEOUT_INVALID")
        binary = shutil.which(str(openssl_binary or ""))
        if not binary:
            raise RuntimeError("AUTHORITY_GRANT_OPENSSL_UNAVAILABLE")

        keys: dict[str, str] = {}
        for key_id, pem in keyring.ed25519_public_keys_pem.items():
            if type(key_id) is not str or not key_id:
                raise ValueError("BOOTSTRAP_VERIFICATION_KEY_ID_INVALID")
            if type(pem) is not str or "BEGIN PUBLIC KEY" not in pem:
                raise ValueError(f"BOOTSTRAP_VERIFICATION_PUBLIC_KEY_INVALID:{key_id}")
            if "PRIVATE KEY" in pem:
                raise ValueError(f"BOOTSTRAP_VERIFICATION_PRIVATE_KEY_FORBIDDEN:{key_id}")
            keys[key_id] = pem

        self._root_id = keyring.root_id
        self._keys = MappingProxyType(keys)
        self._revoked = frozenset(str(item) for item in keyring.revoked_key_ids)
        self._openssl_binary = binary
        self._verify_timeout_seconds = verify_timeout_seconds

    @property
    def root_id(self) -> str:
        return self._root_id

    def verify(
        self,
        envelope: AuthorityGrantEnvelope,
        expected: GrantBindingExpectation,
        *,
        now_unix: int,
    ) -> None:
        if not isinstance(envelope, AuthorityGrantEnvelope):
            raise TypeError("AUTHORITY_GRANT_ENVELOPE_REQUIRED")
        key_id = envelope.claims.key_id
        if type(key_id) is not str or not key_id:
            raise ValueError("AUTHORITY_GRANT_KEY_ID_REQUIRED")
        if key_id in self._revoked:
            raise PermissionError("AUTHORITY_GRANT_KEY_REVOKED")
        public_key_pem = self._keys.get(key_id)
        if public_key_pem is None:
            raise PermissionError("AUTHORITY_GRANT_UNKNOWN_KEY_ID")

        signature = _decode_signature(envelope.signature_b64)
        payload = canonical_grant_payload(envelope.claims)
        _verify_ed25519_signature(
            self._openssl_binary,
            public_key_pem,
            payload,
            signature,
            timeout_seconds=self._verify_timeout_seconds,
        )
        validate_grant_claims(envelope.claims, expected, now_unix=now_unix)


def _keyring_from_json_object(raw: object) -> BootstrapVerificationKeyring:
    if not isinstance(raw, dict):
        raise ValueError("BOOTSTRAP_KEYRING_OBJECT_REQUIRED")
    allowed = {"ROOT_ID", "ED25519_PUBLIC_KEYS_PEM", "REVOKED_KEY_IDS"}
    if set(raw) - allowed:
        raise ValueError("BOOTSTRAP_KEYRING_UNKNOWN_FIELD")

    root_id = raw.get("ROOT_ID")
    keys = raw.get("ED25519_PUBLIC_KEYS_PEM")
    revoked = raw.get("REVOKED_KEY_IDS", [])
    if type(root_id) is not str or not root_id:
        raise ValueError("BOOTSTRAP_VERIFICATION_ROOT_ID_REQUIRED")
    if not isinstance(keys, dict) or not keys:
        raise ValueError("BOOTSTRAP_VERIFICATION_KEYS_REQUIRED")
    if not isinstance(revoked, list) or not all(type(item) is str and item for item in revoked):
        raise ValueError("BOOTSTRAP_REVOKED_KEY_IDS_INVALID")

    return BootstrapVerificationKeyring(
        root_id=root_id,
        ed25519_public_keys_pem=MappingProxyType(dict(keys)),
        revoked_key_ids=frozenset(revoked),
    )


def load_bootstrap_verification_keyring(path: Path) -> BootstrapVerificationKeyring:
    """Generic loader retained for tooling/tests, not the live Host integration.

    Live Runtime Host bootstrap MUST use ``bootstrap_runtime_host_verifier_from_inherited_fd``.
    """

    p = Path(path)
    if not p.is_absolute():
        raise ValueError("BOOTSTRAP_KEYRING_ABSOLUTE_PATH_REQUIRED")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("BOOTSTRAP_KEYRING_LOAD_FAILED") from exc
    return _keyring_from_json_object(raw)


def load_bootstrap_verification_keyring_from_fd(fd: int) -> BootstrapVerificationKeyring:
    """Read bootstrap keyring only from a supervisor-inherited descriptor."""

    if type(fd) is not int or fd < 0:
        raise ValueError("RUNTIME_HOST_BOOTSTRAP_KEYRING_FD_INVALID")
    try:
        duplicate = os.dup(fd)
        os.set_inheritable(duplicate, False)
    except OSError as exc:
        raise RuntimeError("RUNTIME_HOST_BOOTSTRAP_KEYRING_FD_UNAVAILABLE") from exc

    data = bytearray()
    try:
        while True:
            chunk = os.read(duplicate, 64 * 1024)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_BOOTSTRAP_KEYRING_BYTES:
                raise ValueError("RUNTIME_HOST_BOOTSTRAP_KEYRING_TOO_LARGE")
    finally:
        os.close(duplicate)
    if not data:
        raise ValueError("RUNTIME_HOST_BOOTSTRAP_KEYRING_EMPTY")
    try:
        raw = json.loads(bytes(data).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("RUNTIME_HOST_BOOTSTRAP_KEYRING_JSON_INVALID") from exc
    return _keyring_from_json_object(raw)


_RUNTIME_HOST_BOOTSTRAP_LOCK = threading.Lock()
_RUNTIME_HOST_VERIFIER: AuthorityGrantVerifier | None = None
_RUNTIME_HOST_ROOT_ID: str | None = None


def bootstrap_runtime_host_verifier_from_inherited_fd(
    fd: int,
    *,
    openssl_binary: str = DEFAULT_OPENSSL_BINARY,
    verify_timeout_seconds: int = DEFAULT_VERIFY_TIMEOUT_SECONDS,
) -> str:
    """Install the one Runtime Host verification root before serving requests.

    There is intentionally no reset/replace API. The trusted supervisor must
    call this during host startup, before any visual/request IPC is accepted.
    A second initialization attempt fails closed.
    """

    global _RUNTIME_HOST_VERIFIER, _RUNTIME_HOST_ROOT_ID
    with _RUNTIME_HOST_BOOTSTRAP_LOCK:
        if _RUNTIME_HOST_VERIFIER is not None:
            raise RuntimeError("RUNTIME_HOST_VERIFICATION_ROOT_ALREADY_BOOTSTRAPPED")
        keyring = load_bootstrap_verification_keyring_from_fd(fd)
        verifier = AuthorityGrantVerifier(
            keyring,
            openssl_binary=openssl_binary,
            verify_timeout_seconds=verify_timeout_seconds,
        )
        _RUNTIME_HOST_VERIFIER = verifier
        _RUNTIME_HOST_ROOT_ID = verifier.root_id
        return verifier.root_id


def runtime_host_verification_root_id() -> str:
    root_id = _RUNTIME_HOST_ROOT_ID
    if not root_id:
        raise RuntimeError("RUNTIME_HOST_VERIFICATION_ROOT_NOT_BOOTSTRAPPED")
    return root_id


def verify_with_runtime_host_root(
    envelope: AuthorityGrantEnvelope,
    expected: GrantBindingExpectation,
    *,
    now_unix: int,
) -> None:
    """Verify using only the already-bootstrapped Runtime Host trust root."""

    verifier = _RUNTIME_HOST_VERIFIER
    if verifier is None:
        raise RuntimeError("RUNTIME_HOST_VERIFICATION_ROOT_NOT_BOOTSTRAPPED")
    verifier.verify(envelope, expected, now_unix=now_unix)


def _decode_signature(signature_b64: object) -> bytes:
    if type(signature_b64) is not str or not signature_b64:
        raise ValueError("AUTHORITY_GRANT_SIGNATURE_REQUIRED")
    try:
        decoded = base64.b64decode(signature_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("AUTHORITY_GRANT_SIGNATURE_BASE64_INVALID") from exc
    if len(decoded) != 64:
        raise ValueError("AUTHORITY_GRANT_ED25519_SIGNATURE_LENGTH_INVALID")
    return decoded


def _verify_ed25519_signature(
    openssl_binary: str,
    public_key_pem: str,
    payload: bytes,
    signature: bytes,
    *,
    timeout_seconds: int,
) -> None:
    with tempfile.TemporaryDirectory(prefix="dnd-authority-verify-") as tmp:
        root = Path(tmp)
        key_path = root / "key.pem"
        payload_path = root / "payload.bin"
        signature_path = root / "signature.bin"
        key_path.write_text(public_key_pem, encoding="utf-8")
        payload_path.write_bytes(payload)
        signature_path.write_bytes(signature)
        try:
            result = subprocess.run(
                [
                    openssl_binary,
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(key_path),
                    "-rawin",
                    "-in",
                    str(payload_path),
                    "-sigfile",
                    str(signature_path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("AUTHORITY_GRANT_SIGNATURE_VERIFIER_FAILURE") from exc
        if result.returncode != 0:
            raise PermissionError("AUTHORITY_GRANT_SIGNATURE_INVALID")


__all__ = [
    "DEFAULT_OPENSSL_BINARY",
    "DEFAULT_VERIFY_TIMEOUT_SECONDS",
    "MAX_BOOTSTRAP_KEYRING_BYTES",
    "BootstrapVerificationKeyring",
    "AuthorityGrantVerifier",
    "load_bootstrap_verification_keyring",
    "load_bootstrap_verification_keyring_from_fd",
    "bootstrap_runtime_host_verifier_from_inherited_fd",
    "runtime_host_verification_root_id",
    "verify_with_runtime_host_root",
]
