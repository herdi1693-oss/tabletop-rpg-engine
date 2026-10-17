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


class RuntimeHostRequestContextBootstrapFdTests(unittest.TestCase):
    def assert_isolated_ok(self, source: str) -> None:
        result = _run_isolated(source)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r}\nstderr={result.stderr!r}",
        )

    def test_successful_pipe_bootstrap_consumes_original_fd(self):
        self.assert_isolated_ok(
            r'''
            import errno
            import os
            from runtime.runtime_host_request_context import (
                bootstrap_runtime_host_request_context_authority_from_inherited_fd,
            )

            read_fd, write_fd = os.pipe()
            os.write(write_fd, b"K" * 64)
            os.close(write_fd)
            bootstrap_runtime_host_request_context_authority_from_inherited_fd(read_fd)

            try:
                os.fstat(read_fd)
            except OSError as exc:
                assert exc.errno == errno.EBADF, exc
            else:
                raise AssertionError("bootstrap left original inherited FD open")
            '''
        )

    def test_seekable_memfd_is_rejected_and_consumed(self):
        self.assert_isolated_ok(
            r'''
            import errno
            import os
            from runtime.runtime_host_request_context import (
                bootstrap_runtime_host_request_context_authority_from_inherited_fd,
            )

            if not hasattr(os, "memfd_create"):
                raise SystemExit(0)
            fd = os.memfd_create("dnd-host-context-key", flags=0)
            os.write(fd, b"M" * 64)
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                bootstrap_runtime_host_request_context_authority_from_inherited_fd(fd)
            except PermissionError as exc:
                assert "BOOTSTRAP_FD_SEEKABLE_FORBIDDEN" in str(exc), exc
            else:
                raise AssertionError("seekable bootstrap source was accepted")

            for operation in (
                lambda: os.fstat(fd),
                lambda: os.lseek(fd, 0, os.SEEK_SET),
                lambda: os.read(fd, 1),
            ):
                try:
                    operation()
                except OSError as exc:
                    assert exc.errno == errno.EBADF, exc
                else:
                    raise AssertionError("rejected seekable FD remained usable")
            '''
        )

    def test_short_key_failure_still_consumes_original_fd(self):
        self.assert_isolated_ok(
            r'''
            import errno
            import os
            from runtime.runtime_host_request_context import (
                bootstrap_runtime_host_request_context_authority_from_inherited_fd,
            )

            read_fd, write_fd = os.pipe()
            os.write(write_fd, b"short")
            os.close(write_fd)
            try:
                bootstrap_runtime_host_request_context_authority_from_inherited_fd(read_fd)
            except ValueError as exc:
                assert "BOOTSTRAP_KEY_TOO_SHORT" in str(exc), exc
            else:
                raise AssertionError("short bootstrap key was accepted")

            try:
                os.fstat(read_fd)
            except OSError as exc:
                assert exc.errno == errno.EBADF, exc
            else:
                raise AssertionError("failed bootstrap left original FD open")
            '''
        )

    def test_rejected_second_bootstrap_consumes_new_fd(self):
        self.assert_isolated_ok(
            r'''
            import errno
            import os
            from runtime.runtime_host_request_context import (
                bootstrap_runtime_host_request_context_authority_from_inherited_fd,
            )

            first_read, first_write = os.pipe()
            os.write(first_write, b"A" * 64)
            os.close(first_write)
            bootstrap_runtime_host_request_context_authority_from_inherited_fd(first_read)

            second_read, second_write = os.pipe()
            os.write(second_write, b"B" * 64)
            os.close(second_write)
            try:
                bootstrap_runtime_host_request_context_authority_from_inherited_fd(second_read)
            except RuntimeError as exc:
                assert "AUTHORITY_ALREADY_BOOTSTRAPPED" in str(exc), exc
            else:
                raise AssertionError("second bootstrap unexpectedly succeeded")

            try:
                os.fstat(second_read)
            except OSError as exc:
                assert exc.errno == errno.EBADF, exc
            else:
                raise AssertionError("rejected second-bootstrap FD remained open")
            '''
        )


if __name__ == "__main__":
    unittest.main()
