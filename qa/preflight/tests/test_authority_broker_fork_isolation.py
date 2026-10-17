import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_isolated(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


@unittest.skipUnless(hasattr(os, "fork"), "requires os.fork")
class AuthorityBrokerForkIsolationTests(unittest.TestCase):
    def test_forked_child_cannot_reuse_or_rebootstrap_signing_authority(self):
        result = _run_isolated(
            r'''
            import json
            import os
            import shutil
            import subprocess
            import tempfile
            from pathlib import Path

            from broker.authority_grant_broker import (
                AuthorityGrantBrokerService,
                BrokerGrantRequest,
                TrustedAuthoritySnapshot,
                TrustedAuthoritySource,
            )
            from broker.authority_grant_signer import (
                AuthorityGrantBrokerSigner,
                BrokerSignerIdentity,
            )
            from runtime.authority_grant_protocol import AuthorityGrantClaims, GrantBindingExpectation
            from runtime.authority_grant_verifier import AuthorityGrantVerifier, BootstrapVerificationKeyring

            class Source(TrustedAuthoritySource):
                def authorize_and_snapshot(self, request):
                    return TrustedAuthoritySnapshot(
                        session_id="SESSION-BROKER-FORK",
                        activation_id="ACT-BROKER-FORK",
                        source_revision="REV-BROKER-FORK",
                        checkpoint_receipt_id="CP-BROKER-FORK",
                        checkpoint_digest="CP-DIGEST",
                        event_id="EVENT-BROKER-FORK",
                        applied_event_ledger_owner_id="AEL-BROKER-FORK",
                        applied_event_ledger_snapshot_digest="AEL-DIGEST",
                        player_knowledge_projection_id="PKP-BROKER-FORK",
                        observer_branch_id="BRANCH-BROKER-FORK",
                        player_knowledge_projection_revision="PKP-REV",
                        player_knowledge_projection_digest="PKP-DIGEST",
                        leak_gate_receipt_id="LEAK-BROKER-FORK",
                        leak_gate_receipt_digest="LEAK-DIGEST",
                        player_safe_bundle_digest="PLAYER-SAFE-DIGEST",
                        display_ledger_owner_id="DLO-BROKER-FORK",
                        display_ledger_backing_store_id="DLS-BROKER-FORK",
                        display_ledger_backing_namespace="DNS-BROKER-FORK",
                    )

            def claims():
                return AuthorityGrantClaims(
                    grant_id="GRANT-BROKER-FORK",
                    key_id="BROKER-FORK-K1",
                    request_id="REQ-BROKER-FORK",
                    session_id="SESSION-BROKER-FORK",
                    activation_id="ACT-BROKER-FORK",
                    source_revision="REV-BROKER-FORK",
                    checkpoint_receipt_id="CP-BROKER-FORK",
                    checkpoint_digest="CP-DIGEST",
                    event_id="EVENT-BROKER-FORK",
                    applied_event_ledger_owner_id="AEL-BROKER-FORK",
                    applied_event_ledger_snapshot_digest="AEL-DIGEST",
                    player_knowledge_projection_id="PKP-BROKER-FORK",
                    observer_branch_id="BRANCH-BROKER-FORK",
                    player_knowledge_projection_revision="PKP-REV",
                    player_knowledge_projection_digest="PKP-DIGEST",
                    leak_gate_receipt_id="LEAK-BROKER-FORK",
                    leak_gate_receipt_digest="LEAK-DIGEST",
                    player_safe_bundle_digest="PLAYER-SAFE-DIGEST",
                    display_ledger_owner_id="DLO-BROKER-FORK",
                    display_ledger_backing_store_id="DLS-BROKER-FORK",
                    display_ledger_backing_namespace="DNS-BROKER-FORK",
                    issued_at_unix=1000,
                    expires_at_unix=1060,
                    nonce="NONCE-BROKER-FORK",
                )

            expectation = GrantBindingExpectation(
                request_id="REQ-BROKER-FORK",
                session_id="SESSION-BROKER-FORK",
                activation_id="ACT-BROKER-FORK",
                source_revision="REV-BROKER-FORK",
                checkpoint_receipt_id="CP-BROKER-FORK",
                checkpoint_digest="CP-DIGEST",
                event_id="EVENT-BROKER-FORK",
                applied_event_ledger_owner_id="AEL-BROKER-FORK",
                applied_event_ledger_snapshot_digest="AEL-DIGEST",
                player_knowledge_projection_id="PKP-BROKER-FORK",
                observer_branch_id="BRANCH-BROKER-FORK",
                player_knowledge_projection_revision="PKP-REV",
                player_knowledge_projection_digest="PKP-DIGEST",
                leak_gate_receipt_id="LEAK-BROKER-FORK",
                leak_gate_receipt_digest="LEAK-DIGEST",
                player_safe_bundle_digest="PLAYER-SAFE-DIGEST",
                display_ledger_owner_id="DLO-BROKER-FORK",
                display_ledger_backing_store_id="DLS-BROKER-FORK",
                display_ledger_backing_namespace="DNS-BROKER-FORK",
            )

            request = BrokerGrantRequest(
                request_id="REQ-BROKER-FORK",
                session_id="SESSION-BROKER-FORK",
                activation_id="ACT-BROKER-FORK",
                source_revision="REV-BROKER-FORK",
            )

            openssl = shutil.which("openssl")
            if not openssl:
                raise SystemExit("openssl required")

            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                private_path = root / "private.pem"
                public_path = root / "public.pem"
                subprocess.run(
                    [openssl, "genpkey", "-algorithm", "ED25519", "-out", str(private_path)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                subprocess.run(
                    [openssl, "pkey", "-in", str(private_path), "-pubout", "-out", str(public_path)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                fd = os.open(private_path, os.O_RDONLY)
                try:
                    signer = AuthorityGrantBrokerSigner(
                        BrokerSignerIdentity(key_id="BROKER-FORK-K1", bootstrap_fd=fd)
                    )
                finally:
                    os.close(fd)
                service = AuthorityGrantBrokerService(signer, Source())

                report_r, report_w = os.pipe()
                child = os.fork()
                if child == 0:
                    os.close(report_r)
                    outcomes = {}

                    def attack(name, callback):
                        try:
                            callback()
                        except BaseException as exc:
                            outcomes[name] = f"{type(exc).__name__}:{exc}"
                        else:
                            outcomes[name] = "UNEXPECTED_SUCCESS"

                    attack("sign", lambda: signer.sign(claims()))
                    attack("service", lambda: service.issue_grant(request, now_unix=1000))

                    child_fd = os.open(private_path, os.O_RDONLY)
                    try:
                        attack(
                            "rebootstrap",
                            lambda: AuthorityGrantBrokerSigner(
                                BrokerSignerIdentity(
                                    key_id="BROKER-FORK-K1",
                                    bootstrap_fd=child_fd,
                                )
                            ),
                        )
                    finally:
                        os.close(child_fd)

                    outcomes["child_key_buffer_len"] = len(signer._private_key_pem)
                    os.write(report_w, json.dumps(outcomes, sort_keys=True).encode("utf-8"))
                    os.close(report_w)
                    os._exit(0)

                os.close(report_w)
                raw = b""
                while True:
                    chunk = os.read(report_r, 4096)
                    if not chunk:
                        break
                    raw += chunk
                os.close(report_r)
                _, status = os.waitpid(child, 0)
                assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
                outcomes = json.loads(raw.decode("utf-8"))

                assert outcomes["sign"] != "UNEXPECTED_SUCCESS", outcomes
                assert "BROKER_SIGNER_FORK_INVALIDATED" in outcomes["sign"], outcomes
                assert outcomes["service"] != "UNEXPECTED_SUCCESS", outcomes
                assert "BROKER_SERVICE_PROCESS_MISMATCH" in outcomes["service"], outcomes
                assert outcomes["rebootstrap"] != "UNEXPECTED_SUCCESS", outcomes
                assert "BROKER_SIGNER_FORK_INVALIDATED" in outcomes["rebootstrap"], outcomes
                assert outcomes["child_key_buffer_len"] == 0, outcomes

                verifier = AuthorityGrantVerifier(
                    BootstrapVerificationKeyring(
                        root_id="BROKER-FORK-ROOT",
                        ed25519_public_keys_pem={
                            "BROKER-FORK-K1": public_path.read_text(encoding="utf-8")
                        },
                        revoked_key_ids=frozenset(),
                    )
                )
                parent_envelope = signer.sign(claims())
                verifier.verify(parent_envelope, expectation, now_unix=1030)
                parent_service_envelope = service.issue_grant(request, now_unix=1000)
                verifier.verify(parent_service_envelope, expectation, now_unix=1030)
            '''
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}\nstderr={result.stderr!r}",
        )


if __name__ == "__main__":
    unittest.main()
