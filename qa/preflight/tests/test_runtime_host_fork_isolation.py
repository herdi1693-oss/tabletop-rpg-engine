import json
import os
import socket
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
class RuntimeHostForkIsolationTests(unittest.TestCase):
    def assert_isolated_ok(self, source: str) -> None:
        result = _run_isolated(source)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}\nstderr={result.stderr!r}",
        )

    def test_forked_child_cannot_use_or_rebootstrap_host_context_authority(self):
        self.assert_isolated_ok(
            r'''
            import json
            import os
            import runtime.runtime_host_request_context as rhctx

            read_fd, write_fd = os.pipe()
            os.write(write_fd, b"K" * 64)
            os.close(write_fd)
            rhctx.bootstrap_runtime_host_request_context_authority_from_inherited_fd(read_fd)
            context = rhctx.issue_runtime_host_request_context(
                "SESSION-FORK",
                "ACTIVATION-FORK",
                "REV-FORK",
                now_unix=1000,
            )

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

                attack(
                    "issue",
                    lambda: rhctx.issue_runtime_host_request_context(
                        "SESSION-FORK",
                        "ACTIVATION-FORK-CHILD",
                        "REV-FORK",
                        now_unix=1001,
                    ),
                )
                attack(
                    "verify",
                    lambda: rhctx.verify_runtime_host_request_context(
                        context,
                        require_active=True,
                    ),
                )
                attack("consume", lambda: rhctx.consume_runtime_host_request_context(context))
                attack("cancel", lambda: rhctx.cancel_runtime_host_request_context(context))

                child_read, child_write = os.pipe()
                os.write(child_write, b"Z" * 64)
                os.close(child_write)
                attack(
                    "rebootstrap",
                    lambda: rhctx.bootstrap_runtime_host_request_context_authority_from_inherited_fd(
                        child_read
                    ),
                )
                try:
                    os.fstat(child_read)
                except OSError:
                    outcomes["rebootstrap_fd_closed"] = True
                else:
                    outcomes["rebootstrap_fd_closed"] = False

                outcomes["fork_invalidated"] = rhctx._FORK_CHILD_INVALIDATED
                outcomes["key_destroyed"] = rhctx._CONTEXT_KEY is None
                outcomes["active_registry_cleared"] = rhctx._ACTIVE_CONTEXTS == {}
                os.write(report_w, json.dumps(outcomes, sort_keys=True).encode("utf-8"))
                os.close(report_w)
                os._exit(0)

            os.close(report_w)
            payload = bytearray()
            while True:
                chunk = os.read(report_r, 4096)
                if not chunk:
                    break
                payload.extend(chunk)
            os.close(report_r)
            waited, status = os.waitpid(child, 0)
            assert waited == child
            assert os.waitstatus_to_exitcode(status) == 0, status
            outcomes = json.loads(bytes(payload).decode("utf-8"))

            for name in ("issue", "verify", "consume", "cancel", "rebootstrap"):
                assert "FORKED_CHILD_FORBIDDEN" in outcomes[name], (name, outcomes)
            assert outcomes["rebootstrap_fd_closed"] is True, outcomes
            assert outcomes["fork_invalidated"] is True, outcomes
            assert outcomes["key_destroyed"] is True, outcomes
            assert outcomes["active_registry_cleared"] is True, outcomes

            # The child cannot produce a split-brain terminal transition. The
            # original Host retains the ACTIVE proof and transitions it once.
            rhctx.verify_runtime_host_request_context(context, require_active=True)
            assert context.request_id in rhctx._ACTIVE_CONTEXTS
            rhctx.consume_runtime_host_request_context(context)
            assert context.request_id not in rhctx._ACTIVE_CONTEXTS
            assert context.request_id in rhctx._CONSUMED_CONTEXTS
            assert context.request_id not in rhctx._CANCELLED_CONTEXTS
            '''
        )

    def test_forked_child_cannot_use_inherited_broker_ipc_but_parent_channel_survives(self):
        self.assert_isolated_ok(
            r'''
            import json
            import os
            import socket
            import runtime.runtime_host_request_context as rhctx
            from runtime.authority_broker_client import RuntimeHostAuthorityBrokerClient

            key_r, key_w = os.pipe()
            os.write(key_w, b"K" * 64)
            os.close(key_w)
            rhctx.bootstrap_runtime_host_request_context_authority_from_inherited_fd(key_r)
            context = rhctx.issue_runtime_host_request_context(
                "SESSION-BROKER-FORK",
                "ACTIVATION-BROKER-FORK",
                "REV-BROKER-FORK",
                now_unix=1000,
            )

            host_sock, broker_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
            inherited_fd = host_sock.detach()
            client = RuntimeHostAuthorityBrokerClient.from_inherited_fd(inherited_fd)

            report_r, report_w = os.pipe()
            child = os.fork()
            if child == 0:
                os.close(report_r)
                outcomes = {
                    "socket_fileno_after_fork": client._socket.fileno(),
                }
                try:
                    os.fstat(inherited_fd)
                except OSError:
                    outcomes["inherited_fd_closed"] = True
                else:
                    outcomes["inherited_fd_closed"] = False

                try:
                    client.request_grant(context)
                except BaseException as exc:
                    outcomes["request_grant"] = f"{type(exc).__name__}:{exc}"
                else:
                    outcomes["request_grant"] = "UNEXPECTED_SUCCESS"

                try:
                    os.write(inherited_fd, b"X")
                except OSError:
                    outcomes["raw_inherited_fd_write_blocked"] = True
                else:
                    outcomes["raw_inherited_fd_write_blocked"] = False

                os.write(report_w, json.dumps(outcomes, sort_keys=True).encode("utf-8"))
                os.close(report_w)
                os._exit(0)

            os.close(report_w)
            payload = bytearray()
            while True:
                chunk = os.read(report_r, 4096)
                if not chunk:
                    break
                payload.extend(chunk)
            os.close(report_r)
            waited, status = os.waitpid(child, 0)
            assert waited == child
            assert os.waitstatus_to_exitcode(status) == 0, status
            outcomes = json.loads(bytes(payload).decode("utf-8"))

            assert outcomes["socket_fileno_after_fork"] == -1, outcomes
            assert outcomes["inherited_fd_closed"] is True, outcomes
            assert outcomes["raw_inherited_fd_write_blocked"] is True, outcomes
            assert "FORKED_CHILD_FORBIDDEN" in outcomes["request_grant"], outcomes

            # Child-side close is process-local: the owning Host channel remains
            # usable and the parent lifecycle state is still authoritative.
            assert client._socket.fileno() >= 0
            client._socket.sendall(b"P")
            assert broker_sock.recv(1) == b"P"
            rhctx.cancel_runtime_host_request_context(context)
            client.close()
            broker_sock.close()
            '''
        )


if __name__ == "__main__":
    unittest.main()
