import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import runtime.visual_runtime_bridge as runtime_bridge
from broker.authority_grant_signer import AuthorityGrantBrokerSigner, BrokerSignerIdentity
from runtime.authority_grant_protocol import (
    AuthorityGrantClaims,
    GrantBindingExpectation,
)
from runtime.authority_grant_verifier import (
    AuthorityGrantVerifier,
    BootstrapVerificationKeyring,
)
from runtime.visual_display_ledger_sqlite import materialize_sqlite_display_ledger_owner


class _FakeOwner:
    def __init__(self, authority: str, owner_id: str):
        self.authority = authority
        self.authority_instance_id = owner_id

    def snapshot(self, *args, **kwargs):
        return {}


def _claims(key_id: str) -> AuthorityGrantClaims:
    return AuthorityGrantClaims(
        grant_id="GRANT-ATTACK-1",
        key_id=key_id,
        request_id="REQ-ATTACK-1",
        session_id="SESSION-1",
        activation_id="ACTIVATION-1",
        source_revision="REVISION-1",
        checkpoint_receipt_id="CHECKPOINT-1",
        checkpoint_digest="CHECKPOINT-DIGEST-1",
        event_id="EVENT-1",
        applied_event_ledger_owner_id="AEL-OWNER-1",
        applied_event_ledger_snapshot_digest="AEL-DIGEST-1",
        player_knowledge_projection_id="PKP-1",
        observer_branch_id="BRANCH-1",
        player_knowledge_projection_revision="PKP-REVISION-1",
        player_knowledge_projection_digest="PKP-DIGEST-1",
        leak_gate_receipt_id="LEAK-1",
        leak_gate_receipt_digest="LEAK-DIGEST-1",
        player_safe_bundle_digest="PLAYER-SAFE-DIGEST-1",
        display_ledger_owner_id="DISPLAY-OWNER-1",
        display_ledger_backing_store_id="DISPLAY-STORE-1",
        display_ledger_backing_namespace="DISPLAY-NS-1",
        issued_at_unix=1000,
        expires_at_unix=1060,
        nonce="NONCE-ATTACK-1",
    )


def _expectation(*, request_id: str = "REQ-ATTACK-1") -> GrantBindingExpectation:
    return GrantBindingExpectation(
        request_id=request_id,
        session_id="SESSION-1",
        activation_id="ACTIVATION-1",
        source_revision="REVISION-1",
        checkpoint_receipt_id="CHECKPOINT-1",
        checkpoint_digest="CHECKPOINT-DIGEST-1",
        event_id="EVENT-1",
        applied_event_ledger_owner_id="AEL-OWNER-1",
        applied_event_ledger_snapshot_digest="AEL-DIGEST-1",
        player_knowledge_projection_id="PKP-1",
        observer_branch_id="BRANCH-1",
        player_knowledge_projection_revision="PKP-REVISION-1",
        player_knowledge_projection_digest="PKP-DIGEST-1",
        leak_gate_receipt_id="LEAK-1",
        leak_gate_receipt_digest="LEAK-DIGEST-1",
        player_safe_bundle_digest="PLAYER-SAFE-DIGEST-1",
        display_ledger_owner_id="DISPLAY-OWNER-1",
        display_ledger_backing_store_id="DISPLAY-STORE-1",
        display_ledger_backing_namespace="DISPLAY-NS-1",
    )


def _generate_ed25519_pair(root: Path, prefix: str) -> tuple[Path, str]:
    openssl = shutil.which("openssl")
    if not openssl:
        raise RuntimeError("OPENSSL_REQUIRED_FOR_AUTHORITY_BOUNDARY_REGRESSION")
    private_path = root / f"{prefix}-private.pem"
    public_path = root / f"{prefix}-public.pem"
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
    return private_path, public_path.read_text(encoding="utf-8")


class AuthorityBrokerAdversarialTests(unittest.TestCase):
    def test_forged_graph_cannot_self_register_as_trusted_assembly(self):
        """FORGED_GRAPH_CANNOT_SELF_REGISTER_AS_TRUSTED_ASSEMBLY.

        A visual/request caller with import access must not possess any callable
        surface that can turn caller-created owners into a trusted authority
        graph. This intentionally attacks the legacy in-process registration
        hook directly rather than reusing a legitimate capability.
        """
        checkpoint = _FakeOwner("RUNTIME_CHECKPOINT_OWNER", "FAKE-CHECKPOINT")
        ael = _FakeOwner("APPLIED_EVENT_LEDGER_OWNER", "FAKE-AEL")
        player_safe = _FakeOwner("PLAYER_SAFE_PROOF_OWNER", "FAKE-PLAYER-SAFE")
        with tempfile.TemporaryDirectory() as tmp:
            ledger = materialize_sqlite_display_ledger_owner(
                Path(tmp) / "fresh-ledger-b.sqlite", "REVISION-ATTACK"
            )
            registration = getattr(
                runtime_bridge,
                "_register_authority_graph_from_trusted_runtime_assembly",
                None,
            )
            self.assertIsNone(
                registration,
                "FORGED_GRAPH_CANNOT_SELF_REGISTER_AS_TRUSTED_ASSEMBLY: "
                "legacy caller-reachable registration surface still exists",
            )

    def test_full_client_compromise_cannot_mint_authority_grant(self):
        """FULL_CLIENT_COMPROMISE_CANNOT_MINT_AUTHORITY_GRANT.

        The attacker may import broker/client code, run subprocesses, create a
        private key, and sign perfectly matching claims. The trusted Runtime
        Host still uses its independently pinned verification root, so the
        attacker-produced grant must be rejected.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legitimate_private, legitimate_public = _generate_ed25519_pair(root, "legitimate")
            # The host keeps only its independently pinned public root in this
            # regression. The legitimate signing secret is removed before the
            # attacker step begins.
            legitimate_private.unlink()
            verifier = AuthorityGrantVerifier(
                BootstrapVerificationKeyring(
                    root_id="BOOTSTRAP-ROOT-1",
                    ed25519_public_keys_pem={"PINNED-K1": legitimate_public},
                    revoked_key_ids=frozenset(),
                )
            )

            attacker_private, _ = _generate_ed25519_pair(root, "attacker")
            fd = os.open(attacker_private, os.O_RDONLY)
            try:
                attacker_signer = AuthorityGrantBrokerSigner(
                    BrokerSignerIdentity(key_id="PINNED-K1", bootstrap_fd=fd)
                )
            finally:
                os.close(fd)
            forged_envelope = attacker_signer.sign(_claims("PINNED-K1"))

            with self.assertRaises(PermissionError) as error:
                verifier.verify(forged_envelope, _expectation(), now_unix=1030)
            self.assertIn("AUTHORITY_GRANT_SIGNATURE_INVALID", str(error.exception))

    def test_valid_signature_cannot_cross_request_boundary(self):
        """A valid signature is insufficient when trusted host request context differs."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_path, public_pem = _generate_ed25519_pair(root, "request-binding")
            fd = os.open(private_path, os.O_RDONLY)
            try:
                signer = AuthorityGrantBrokerSigner(
                    BrokerSignerIdentity(key_id="PINNED-K1", bootstrap_fd=fd)
                )
            finally:
                os.close(fd)
            verifier = AuthorityGrantVerifier(
                BootstrapVerificationKeyring(
                    root_id="BOOTSTRAP-ROOT-REQUEST-BINDING",
                    ed25519_public_keys_pem={"PINNED-K1": public_pem},
                    revoked_key_ids=frozenset(),
                )
            )
            envelope = signer.sign(_claims("PINNED-K1"))
            with self.assertRaises(PermissionError) as error:
                verifier.verify(
                    envelope,
                    _expectation(request_id="REQ-ATTACK-2"),
                    now_unix=1030,
                )
            self.assertIn("AUTHORITY_GRANT_REQUEST_ID_MISMATCH", str(error.exception))


if __name__ == "__main__":
    unittest.main()
