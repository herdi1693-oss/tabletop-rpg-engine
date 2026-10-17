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


class RuntimeHostRequestContextLifecycleTests(unittest.TestCase):
    def assert_isolated_ok(self, source: str) -> None:
        result = _run_isolated(source)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}\nstderr={result.stderr!r}",
        )

    def test_cancelled_identity_is_tombstoned_and_collision_blocked(self):
        self.assert_isolated_ok(
            r'''
            import os
            from unittest import mock
            import runtime.runtime_host_request_context as rhctx

            read_fd, write_fd = os.pipe()
            os.write(write_fd, b"K" * 64)
            os.close(write_fd)
            rhctx.bootstrap_runtime_host_request_context_authority_from_inherited_fd(read_fd)

            request_hex = "ab" * 24
            first_nonce = "cd" * 24
            second_nonce = "ef" * 24
            with mock.patch.object(
                rhctx.secrets,
                "token_hex",
                side_effect=[request_hex, first_nonce, request_hex, second_nonce],
            ):
                context = rhctx.issue_runtime_host_request_context(
                    "SESSION-LIFECYCLE",
                    "ACTIVATION-LIFECYCLE",
                    "REV-LIFECYCLE",
                )
                rhctx.cancel_runtime_host_request_context(context)

                try:
                    rhctx.verify_runtime_host_request_context(context, require_active=True)
                except PermissionError as exc:
                    assert "NOT_ACTIVE" in str(exc), exc
                else:
                    raise AssertionError("cancelled context remained ACTIVE")

                assert context.request_id in rhctx._CANCELLED_CONTEXTS
                assert context.request_id not in rhctx._ACTIVE_CONTEXTS
                assert context.request_id not in rhctx._CONSUMED_CONTEXTS

                try:
                    rhctx.issue_runtime_host_request_context(
                        "SESSION-LIFECYCLE",
                        "ACTIVATION-LIFECYCLE",
                        "REV-LIFECYCLE",
                    )
                except RuntimeError as exc:
                    assert "ID_COLLISION" in str(exc), exc
                else:
                    raise AssertionError("cancelled request identity was re-issued")
            '''
        )

    def test_second_cancel_is_rejected(self):
        self.assert_isolated_ok(
            r'''
            import os
            import runtime.runtime_host_request_context as rhctx

            read_fd, write_fd = os.pipe()
            os.write(write_fd, b"K" * 64)
            os.close(write_fd)
            rhctx.bootstrap_runtime_host_request_context_authority_from_inherited_fd(read_fd)

            context = rhctx.issue_runtime_host_request_context(
                "SESSION-SECOND-CANCEL",
                "ACTIVATION-SECOND-CANCEL",
                "REV-SECOND-CANCEL",
            )
            rhctx.cancel_runtime_host_request_context(context)
            try:
                rhctx.cancel_runtime_host_request_context(context)
            except PermissionError as exc:
                assert "NOT_ACTIVE" in str(exc), exc
            else:
                raise AssertionError("second cancel unexpectedly succeeded")
            '''
        )

    def test_cancel_consume_race_reaches_exactly_one_terminal_state(self):
        self.assert_isolated_ok(
            r'''
            import os
            import threading
            import runtime.runtime_host_request_context as rhctx

            read_fd, write_fd = os.pipe()
            os.write(write_fd, b"K" * 64)
            os.close(write_fd)
            rhctx.bootstrap_runtime_host_request_context_authority_from_inherited_fd(read_fd)

            context = rhctx.issue_runtime_host_request_context(
                "SESSION-RACE",
                "ACTIVATION-RACE",
                "REV-RACE",
            )
            start = threading.Barrier(3)
            outcomes = []
            outcomes_lock = threading.Lock()

            def run(name, operation):
                start.wait()
                try:
                    operation(context)
                except PermissionError as exc:
                    outcome = (name, "FAIL", str(exc))
                else:
                    outcome = (name, "SUCCESS", "")
                with outcomes_lock:
                    outcomes.append(outcome)

            consume_thread = threading.Thread(
                target=run,
                args=("consume", rhctx.consume_runtime_host_request_context),
            )
            cancel_thread = threading.Thread(
                target=run,
                args=("cancel", rhctx.cancel_runtime_host_request_context),
            )
            consume_thread.start()
            cancel_thread.start()
            start.wait()
            consume_thread.join()
            cancel_thread.join()

            successes = [item for item in outcomes if item[1] == "SUCCESS"]
            failures = [item for item in outcomes if item[1] == "FAIL"]
            assert len(successes) == 1, outcomes
            assert len(failures) == 1, outcomes
            assert "NOT_ACTIVE" in failures[0][2], outcomes

            request_id = context.request_id
            consumed = request_id in rhctx._CONSUMED_CONTEXTS
            cancelled = request_id in rhctx._CANCELLED_CONTEXTS
            assert consumed ^ cancelled, (consumed, cancelled, outcomes)
            assert request_id not in rhctx._ACTIVE_CONTEXTS

            try:
                rhctx.verify_runtime_host_request_context(context, require_active=True)
            except PermissionError as exc:
                assert "NOT_ACTIVE" in str(exc), exc
            else:
                raise AssertionError("terminal race left context ACTIVE")
            '''
        )


if __name__ == "__main__":
    unittest.main()
