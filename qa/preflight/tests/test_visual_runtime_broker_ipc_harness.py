#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
_FRAME_HEADER = struct.Struct("!I")


def _send_frame(sock: socket.socket, payload: dict[str, object]) -> None:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sock.sendall(_FRAME_HEADER.pack(len(raw)) + raw)


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            if remaining == size:
                raise EOFError
            raise ConnectionError("TEST_IPC_TRUNCATED_FRAME")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_frame(sock: socket.socket) -> dict[str, object]:
    size = _FRAME_HEADER.unpack(_recv_exact(sock, _FRAME_HEADER.size))[0]
    raw = _recv_exact(sock, size)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("TEST_IPC_OBJECT_REQUIRED")
    return payload


def _generate_private_key(root: Path) -> Path:
    openssl = shutil.which("openssl")
    if not openssl:
        raise RuntimeError("OPENSSL_REQUIRED_FOR_BROKER_IPC_QA")
    path = root / "broker-private.pem"
    subprocess.run(
        [openssl, "genpkey", "-algorithm", "ED25519", "-out", str(path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return path


def _authority_snapshot() -> dict[str, str]:
    return {
        "session_id": "SESSION-IPC-1",
        "activation_id": "ACT-IPC-1",
        "source_revision": "REV-IPC-1",
        "checkpoint_receipt_id": "CP-IPC-1",
        "checkpoint_digest": "cp-digest-1",
        "event_id": "EVENT-IPC-1",
        "applied_event_ledger_owner_id": "AEL-IPC-1",
        "applied_event_ledger_snapshot_digest": "ael-digest-1",
        "player_knowledge_projection_id": "PKP-IPC-1",
        "observer_branch_id": "BRANCH-IPC-1",
        "player_knowledge_projection_revision": "REV-IPC-1",
        "player_knowledge_projection_digest": "pkp-digest-1",
        "leak_gate_receipt_id": "LEAK-IPC-1",
        "leak_gate_receipt_digest": "leak-digest-1",
        "player_safe_bundle_digest": "player-safe-digest-1",
        "display_ledger_owner_id": "DLO-IPC-1",
        "display_ledger_backing_store_id": "DLS-IPC-1",
        "display_ledger_backing_namespace": "NS-IPC-1",
    }


def _grant_request() -> dict[str, object]:
    return {
        "TYPE": "GRANT_REQUEST",
        "REQUEST_ID": "REQ-IPC-1",
        "SESSION_ID": "SESSION-IPC-1",
        "ACTIVATION_ID": "ACT-IPC-1",
        "SOURCE_REVISION": "REV-IPC-1",
    }


class _BrokerHarness:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-broker-ipc-qa-")
        private_key = _generate_private_key(Path(self.temp.name))
        runtime_parent, runtime_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        source_parent, source_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        runtime_parent.settimeout(10.0)
        source_parent.settimeout(10.0)
        signing_fd = os.open(private_key, os.O_RDONLY)
        try:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "broker.authority_broker_process",
                    "--runtime-ipc-fd",
                    str(runtime_child.fileno()),
                    "--authority-source-fd",
                    str(source_child.fileno()),
                    "--signing-key-fd",
                    str(signing_fd),
                    "--key-id",
                    "BROKER-IPC-QA-K1",
                ],
                cwd=ROOT,
                pass_fds=(runtime_child.fileno(), source_child.fileno(), signing_fd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                close_fds=True,
                text=True,
            )
        finally:
            runtime_child.close()
            source_child.close()
            os.close(signing_fd)
        self.runtime = runtime_parent
        self.source = source_parent

    def close_source(self) -> None:
        if self.source is not None:
            self.source.close()
            self.source = None

    def close_runtime(self) -> None:
        if self.runtime is not None:
            self.runtime.close()
            self.runtime = None

    def stderr(self) -> str:
        if self.process.poll() is None or self.process.stderr is None:
            return ""
        return self.process.stderr.read()

    def close(self) -> None:
        self.close_runtime()
        self.close_source()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.process.stderr is not None:
            self.process.stderr.close()
        self.temp.cleanup()


class BrokerIpcAdversarialHarnessTests(unittest.TestCase):
    def test_forbidden_broker_field_injection_matrix_is_denied(self):
        harness = _BrokerHarness()
        try:
            forbidden = {
                "CHECKPOINT_RECEIPT_ID": "ATTACK-CP",
                "CHECKPOINT_DIGEST": "ATTACK-DIGEST",
                "APPLIED_EVENT_LEDGER_OWNER_ID": "ATTACK-AEL",
                "APPLIED_EVENT_LEDGER_SNAPSHOT_DIGEST": "ATTACK-AEL-DIGEST",
                "PLAYER_KNOWLEDGE_PROJECTION_ID": "ATTACK-PKP",
                "PLAYER_KNOWLEDGE_PROJECTION_DIGEST": "ATTACK-PKP-DIGEST",
                "LEAK_GATE_RECEIPT_ID": "ATTACK-LEAK",
                "LEAK_GATE_RECEIPT_DIGEST": "ATTACK-LEAK-DIGEST",
                "PLAYER_SAFE_BUNDLE_DIGEST": "ATTACK-PLAYER-SAFE",
                "DISPLAY_LEDGER_OWNER_ID": "ATTACK-DLO",
                "DISPLAY_LEDGER_BACKING_STORE_ID": "ATTACK-DLS",
                "DISPLAY_LEDGER_BACKING_NAMESPACE": "ATTACK-NS",
                "KEY_ID": "ATTACKER-K1",
                "SIGNING_KEY": "ATTACKER-KEY-MATERIAL",
                "VERIFICATION_ROOT": "ATTACKER-ROOT",
            }
            for field, value in forbidden.items():
                with self.subTest(field=field):
                    payload = _grant_request()
                    payload[field] = value
                    _send_frame(harness.runtime, payload)
                    response = _recv_frame(harness.runtime)
                    self.assertEqual(response, {"TYPE": "GRANT_DENIED", "ERROR": "AUTHORITY_GRANT_DENIED"})

            seen: list[dict[str, object]] = []
            source_errors: list[BaseException] = []

            def source_once() -> None:
                try:
                    incoming = _recv_frame(harness.source)
                    seen.append(incoming)
                    _send_frame(
                        harness.source,
                        {
                            "TYPE": "AUTHORITY_SNAPSHOT_RESPONSE",
                            "REQUEST_ID": incoming["REQUEST_ID"],
                            "SNAPSHOT": _authority_snapshot(),
                        },
                    )
                except BaseException as exc:  # pragma: no cover
                    source_errors.append(exc)

            responder = threading.Thread(target=source_once, daemon=True)
            responder.start()
            _send_frame(harness.runtime, _grant_request())
            response = _recv_frame(harness.runtime)
            responder.join(timeout=10)
            self.assertFalse(responder.is_alive(), "authority source responder hung")
            self.assertEqual(source_errors, [])
            self.assertEqual(response.get("TYPE"), "AUTHORITY_GRANT")
            self.assertEqual(
                seen,
                [{
                    "TYPE": "AUTHORITY_SNAPSHOT_REQUEST",
                    "REQUEST_ID": "REQ-IPC-1",
                    "SESSION_ID": "SESSION-IPC-1",
                    "ACTIVATION_ID": "ACT-IPC-1",
                    "SOURCE_REVISION": "REV-IPC-1",
                }],
            )
        finally:
            harness.close()

    def test_authority_source_disconnect_returns_denial_without_fallback(self):
        harness = _BrokerHarness()
        try:
            harness.close_source()
            _send_frame(harness.runtime, _grant_request())
            response = _recv_frame(harness.runtime)
            self.assertEqual(response, {"TYPE": "GRANT_DENIED", "ERROR": "AUTHORITY_GRANT_DENIED"})
            self.assertIsNone(harness.process.poll(), harness.stderr())
        finally:
            harness.close()

    def test_broker_termination_closes_runtime_channel_instead_of_fallback(self):
        harness = _BrokerHarness()
        try:
            harness.process.terminate()
            harness.process.wait(timeout=5)
            with self.assertRaises((EOFError, ConnectionResetError)):
                _recv_frame(harness.runtime)
        finally:
            harness.close()

    def test_runtime_ipc_disconnect_causes_clean_broker_exit(self):
        harness = _BrokerHarness()
        try:
            harness.close_runtime()
            returncode = harness.process.wait(timeout=5)
            self.assertEqual(returncode, 0, harness.stderr())
        finally:
            harness.close()


if __name__ == "__main__":
    unittest.main()
