import os
import subprocess
import sys
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
class AuthorityBrokerChannelForkIsolationTests(unittest.TestCase):
    def test_forked_child_loses_source_runtime_and_duplicated_channel_fds_while_parent_survives(self):
        result = _run_isolated(
            r'''
            import json
            import os
            import shutil
            import socket
            import subprocess
            import tempfile
            import threading
            from dataclasses import asdict
            from pathlib import Path

            from broker.authority_broker_process import (
                AuthorityBrokerProcess,
                InheritedFDAuthoritySource,
                _recv_json_frame,
                _send_json_frame,
            )
            from broker.authority_grant_broker import (
                AuthorityGrantBrokerService,
                BrokerGrantRequest,
                TrustedAuthoritySnapshot,
            )
            from broker.authority_grant_signer import (
                AuthorityGrantBrokerSigner,
                BrokerSignerIdentity,
            )

            def snapshot():
                return TrustedAuthoritySnapshot(
                    session_id="SESSION-CHANNEL-FORK",
                    activation_id="ACT-CHANNEL-FORK",
                    source_revision="REV-CHANNEL-FORK",
                    checkpoint_receipt_id="CP-CHANNEL-FORK",
                    checkpoint_digest="CP-DIGEST",
                    event_id="EVENT-CHANNEL-FORK",
                    applied_event_ledger_owner_id="AEL-CHANNEL-FORK",
                    applied_event_ledger_snapshot_digest="AEL-DIGEST",
                    player_knowledge_projection_id="PKP-CHANNEL-FORK",
                    observer_branch_id="BRANCH-CHANNEL-FORK",
                    player_knowledge_projection_revision="PKP-REV",
                    player_knowledge_projection_digest="PKP-DIGEST",
                    leak_gate_receipt_id="LEAK-CHANNEL-FORK",
                    leak_gate_receipt_digest="LEAK-DIGEST",
                    player_safe_bundle_digest="PLAYER-SAFE-DIGEST",
                    display_ledger_owner_id="DLO-CHANNEL-FORK",
                    display_ledger_backing_store_id="DLS-BROKER-FORK",
                    display_ledger_backing_namespace="DNS-CHANNEL-FORK",
                )

            request = BrokerGrantRequest(
                request_id="REQ-CHANNEL-FORK",
                session_id="SESSION-CHANNEL-FORK",
                activation_id="ACT-CHANNEL-FORK",
                source_revision="REV-CHANNEL-FORK",
            )

            openssl = shutil.which("openssl")
            if not openssl:
                raise SystemExit("openssl required")

            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                private_path = root / "private.pem"
                subprocess.run(
                    [openssl, "genpkey", "-algorithm", "ED25519", "-out", str(private_path)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                fd = os.open(private_path, os.O_RDONLY)
                try:
                    signer = AuthorityGrantBrokerSigner(
                        BrokerSignerIdentity(key_id="CHANNEL-FORK-K1", bootstrap_fd=fd)
                    )
                finally:
                    os.close(fd)

                source_broker, source_peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
                runtime_broker, runtime_peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
                duplicate_source_fd = None
                duplicate_runtime_fd = None
                try:
                    source = InheritedFDAuthoritySource(source_broker)
                    service = AuthorityGrantBrokerService(signer, source)
                    process = AuthorityBrokerProcess(runtime_broker, service)
                    raw_source_socket = source._socket
                    raw_runtime_socket = process._runtime_socket

                    parent_result = {}
                    parent_error = {}

                    def parent_source_call():
                        try:
                            parent_result["snapshot"] = source.authorize_and_snapshot(request)
                        except BaseException as exc:
                            parent_error["error"] = f"{type(exc).__name__}:{exc}"

                    worker = threading.Thread(target=parent_source_call, daemon=True)
                    worker.start()
                    observed = _recv_json_frame(source_peer)
                    assert observed["TYPE"] == "AUTHORITY_SNAPSHOT_REQUEST", observed
                    assert observed["REQUEST_ID"] == request.request_id, observed

                    # Create independent raw descriptor aliases while trusted
                    # source traffic is already in flight. These aliases are not
                    # represented in the broker's WeakSet of Python socket
                    # objects and reproduce the hostile QA bypass directly.
                    duplicate_source_fd = os.dup(raw_source_socket.fileno())
                    duplicate_runtime_fd = os.dup(raw_runtime_socket.fileno())
                    os.set_inheritable(duplicate_source_fd, False)
                    os.set_inheritable(duplicate_runtime_fd, False)

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

                        attack("source_call", lambda: source.authorize_and_snapshot(request))
                        attack("raw_source_socket", lambda: raw_source_socket.sendall(b"child-source"))
                        attack(
                            "process_handle",
                            lambda: process._handle_request(
                                {
                                    "TYPE": "GRANT_REQUEST",
                                    "REQUEST_ID": request.request_id,
                                    "SESSION_ID": request.session_id,
                                    "ACTIVATION_ID": request.activation_id,
                                    "SOURCE_REVISION": request.source_revision,
                                }
                            ),
                        )
                        attack("raw_runtime_socket", lambda: raw_runtime_socket.sendall(b"child-runtime"))

                        # The exact HIGH: reconstruct/use independent dup() fd
                        # capabilities that were created before fork.
                        attack("dup_source_fstat", lambda: os.fstat(duplicate_source_fd))
                        attack("dup_runtime_fstat", lambda: os.fstat(duplicate_runtime_fd))
                        attack(
                            "dup_source_reconstruct",
                            lambda: socket.socket(fileno=duplicate_source_fd).sendall(b"dup-child-source"),
                        )
                        attack(
                            "dup_runtime_reconstruct",
                            lambda: socket.socket(fileno=duplicate_runtime_fd).sendall(b"dup-child-runtime"),
                        )

                        fresh_source, fresh_source_peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
                        try:
                            attack(
                                "source_rebootstrap",
                                lambda: InheritedFDAuthoritySource(fresh_source),
                            )
                        finally:
                            fresh_source.close()
                            fresh_source_peer.close()

                        fresh_runtime, fresh_runtime_peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
                        try:
                            attack(
                                "process_rebootstrap",
                                lambda: AuthorityBrokerProcess(fresh_runtime, service),
                            )
                        finally:
                            fresh_runtime.close()
                            fresh_runtime_peer.close()

                        outcomes["source_fileno"] = raw_source_socket.fileno()
                        outcomes["runtime_fileno"] = raw_runtime_socket.fileno()
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

                    assert outcomes["source_call"] != "UNEXPECTED_SUCCESS", outcomes
                    assert "FORK_INVALIDATED" in outcomes["source_call"], outcomes
                    assert outcomes["raw_source_socket"] != "UNEXPECTED_SUCCESS", outcomes
                    assert outcomes["process_handle"] != "UNEXPECTED_SUCCESS", outcomes
                    assert "FORK_INVALIDATED" in outcomes["process_handle"], outcomes
                    assert outcomes["raw_runtime_socket"] != "UNEXPECTED_SUCCESS", outcomes
                    assert outcomes["dup_source_fstat"] != "UNEXPECTED_SUCCESS", outcomes
                    assert outcomes["dup_runtime_fstat"] != "UNEXPECTED_SUCCESS", outcomes
                    assert outcomes["dup_source_reconstruct"] != "UNEXPECTED_SUCCESS", outcomes
                    assert outcomes["dup_runtime_reconstruct"] != "UNEXPECTED_SUCCESS", outcomes
                    assert outcomes["source_rebootstrap"] != "UNEXPECTED_SUCCESS", outcomes
                    assert "BROKER_PROCESS_FORK_INVALIDATED" in outcomes["source_rebootstrap"], outcomes
                    assert outcomes["process_rebootstrap"] != "UNEXPECTED_SUCCESS", outcomes
                    assert "BROKER_PROCESS_FORK_INVALIDATED" in outcomes["process_rebootstrap"], outcomes
                    assert outcomes["source_fileno"] == -1, outcomes
                    assert outcomes["runtime_fileno"] == -1, outcomes

                    # Closing a child descriptor table never mutates the parent.
                    os.fstat(duplicate_source_fd)
                    os.fstat(duplicate_runtime_fd)
                    assert raw_source_socket.fileno() >= 0
                    assert raw_runtime_socket.fileno() >= 0

                    _send_json_frame(
                        source_peer,
                        {
                            "TYPE": "AUTHORITY_SNAPSHOT_RESPONSE",
                            "REQUEST_ID": request.request_id,
                            "SNAPSHOT": asdict(snapshot()),
                        },
                    )
                    worker.join(timeout=5)
                    assert not worker.is_alive(), "parent source call did not finish"
                    assert not parent_error, parent_error
                    assert parent_result["snapshot"] == snapshot(), parent_result

                    process._require_owner_process()
                    runtime_peer.sendall(b"P")
                    assert raw_runtime_socket.recv(1) == b"P"
                finally:
                    if duplicate_source_fd is not None:
                        try:
                            os.close(duplicate_source_fd)
                        except OSError:
                            pass
                    if duplicate_runtime_fd is not None:
                        try:
                            os.close(duplicate_runtime_fd)
                        except OSError:
                            pass
                    source_broker.close()
                    source_peer.close()
                    runtime_broker.close()
                    runtime_peer.close()
            '''
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}\nstderr={result.stderr!r}",
        )

    def test_full_bootstrap_consumes_supervisor_descriptors_once(self):
        result = _run_isolated(
            r'''
            import os
            import shutil
            import socket
            import subprocess
            import tempfile
            from pathlib import Path

            import broker.authority_broker_process as broker_process

            openssl = shutil.which("openssl")
            if not openssl:
                raise SystemExit("openssl required")

            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                private_path = root / "private.pem"
                subprocess.run(
                    [openssl, "genpkey", "-algorithm", "ED25519", "-out", str(private_path)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                runtime_broker, runtime_peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
                source_broker, source_peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
                runtime_fd = runtime_broker.detach()
                source_fd = source_broker.detach()
                key_fd = os.open(private_path, os.O_RDONLY)

                original_serve = broker_process.AuthorityBrokerProcess.serve_forever
                broker_process.AuthorityBrokerProcess.serve_forever = lambda self: None
                try:
                    broker_process.run_from_inherited_fds(
                        runtime_ipc_fd=runtime_fd,
                        authority_source_fd=source_fd,
                        signing_key_fd=key_fd,
                        key_id="BOOTSTRAP-CONSUME-K1",
                    )
                finally:
                    broker_process.AuthorityBrokerProcess.serve_forever = original_serve
                    runtime_peer.close()
                    source_peer.close()

                for name, fd in {
                    "runtime": runtime_fd,
                    "source": source_fd,
                    "key": key_fd,
                }.items():
                    try:
                        os.fstat(fd)
                    except OSError:
                        pass
                    else:
                        raise AssertionError(f"{name} bootstrap descriptor remained open")
            '''
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}\nstderr={result.stderr!r}",
        )


if __name__ == "__main__":
    unittest.main()
