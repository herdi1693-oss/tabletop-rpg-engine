import base64
import json
import socket
import struct
import threading
import unittest

from qa.preflight.tests.test_visual_runtime_promotion_candidate import (
    SESSION_ID,
    _ensure_test_host_context_authority,
)
from runtime.authority_broker_client import RuntimeHostAuthorityBrokerClient
from runtime.authority_grant_protocol import AuthorityGrantClaims
from runtime.runtime_host_request_context import (
    cancel_runtime_host_request_context,
    issue_runtime_host_request_context,
)

_FRAME_HEADER = struct.Struct("!I")


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise EOFError
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv(sock: socket.socket):
    size = _FRAME_HEADER.unpack(_recv_exact(sock, _FRAME_HEADER.size))[0]
    return json.loads(_recv_exact(sock, size).decode("utf-8"))


def _send(sock: socket.socket, payload) -> None:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sock.sendall(_FRAME_HEADER.pack(len(raw)) + raw)


def _claims_for(context: object) -> AuthorityGrantClaims:
    return AuthorityGrantClaims(
        grant_id="GRANT-HOST-CTX-1",
        key_id="BROKER-HOST-CTX-K1",
        request_id=context.request_id,
        session_id=context.session_id,
        activation_id=context.activation_id,
        source_revision=context.source_revision,
        checkpoint_receipt_id="CP-HOST-CTX-1",
        checkpoint_digest="a" * 64,
        event_id="EVENT-HOST-CTX-1",
        applied_event_ledger_owner_id="AEL-HOST-CTX-1",
        applied_event_ledger_snapshot_digest="b" * 64,
        player_knowledge_projection_id="PKP-HOST-CTX-1",
        observer_branch_id="BRANCH-HOST-CTX-1",
        player_knowledge_projection_revision=context.source_revision,
        player_knowledge_projection_digest="c" * 64,
        leak_gate_receipt_id="LEAK-HOST-CTX-1",
        leak_gate_receipt_digest="d" * 64,
        player_safe_bundle_digest="e" * 64,
        display_ledger_owner_id="DLO-HOST-CTX-1",
        display_ledger_backing_store_id="DLS-HOST-CTX-1",
        display_ledger_backing_namespace="DLN-HOST-CTX-1",
        issued_at_unix=1000,
        expires_at_unix=1060,
        nonce="NONCE-HOST-CTX-1",
    )


class RuntimeHostAuthorityBrokerClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_test_host_context_authority()

    def test_same_host_owned_identity_flows_to_broker_and_signed_claims(self):
        context = issue_runtime_host_request_context(
            SESSION_ID,
            "ACT-HOST-BROKER-1",
            "REV-HOST-BROKER-1",
            now_unix=1000,
        )
        client_sock, broker_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        client = RuntimeHostAuthorityBrokerClient(client_sock)
        seen = []
        errors = []

        def broker() -> None:
            try:
                incoming = _recv(broker_sock)
                seen.append(incoming)
                claims = _claims_for(context)
                _send(
                    broker_sock,
                    {
                        "TYPE": "AUTHORITY_GRANT",
                        "REQUEST_ID": context.request_id,
                        "CLAIMS": dict(claims.as_mapping()),
                        "SIGNATURE_B64": base64.b64encode(b"0" * 64).decode("ascii"),
                    },
                )
            except BaseException as exc:  # pragma: no cover
                errors.append(exc)

        thread = threading.Thread(target=broker, daemon=True)
        thread.start()
        try:
            envelope = client.request_grant(context)
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(
                seen,
                [{
                    "TYPE": "GRANT_REQUEST",
                    "REQUEST_ID": context.request_id,
                    "SESSION_ID": context.session_id,
                    "ACTIVATION_ID": context.activation_id,
                    "SOURCE_REVISION": context.source_revision,
                }],
            )
            self.assertEqual(envelope.claims.request_id, context.request_id)
        finally:
            client.close()
            broker_sock.close()
            cancel_runtime_host_request_context(context)

    def test_client_rejects_caller_selected_request_id_string(self):
        client_sock, broker_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        client = RuntimeHostAuthorityBrokerClient(client_sock)
        try:
            with self.assertRaises(TypeError) as error:
                client.request_grant("REQ-CALLER-SELECTED")
            self.assertIn("RUNTIME_HOST_REQUEST_CONTEXT_REQUIRED", str(error.exception))
        finally:
            client.close()
            broker_sock.close()

    def test_broker_response_request_id_must_match_actual_host_context(self):
        context = issue_runtime_host_request_context(
            SESSION_ID,
            "ACT-HOST-BROKER-2",
            "REV-HOST-BROKER-2",
            now_unix=1000,
        )
        client_sock, broker_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        client = RuntimeHostAuthorityBrokerClient(client_sock)

        def broker() -> None:
            _recv(broker_sock)
            claims = _claims_for(context)
            _send(
                broker_sock,
                {
                    "TYPE": "AUTHORITY_GRANT",
                    "REQUEST_ID": "REQ-WRONG-TRANSACTION",
                    "CLAIMS": dict(claims.as_mapping()),
                    "SIGNATURE_B64": base64.b64encode(b"0" * 64).decode("ascii"),
                },
            )

        thread = threading.Thread(target=broker, daemon=True)
        thread.start()
        try:
            with self.assertRaises(PermissionError) as error:
                client.request_grant(context)
            self.assertIn("RUNTIME_HOST_BROKER_RESPONSE_REQUEST_ID_MISMATCH", str(error.exception))
        finally:
            thread.join(timeout=5)
            client.close()
            broker_sock.close()
            cancel_runtime_host_request_context(context)


if __name__ == "__main__":
    unittest.main()
