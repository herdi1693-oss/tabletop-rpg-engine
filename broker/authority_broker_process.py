#!/usr/bin/env python3
"""Isolated Authority Broker process boundary for Runtime authority grants.

This module is the executable broker-side IPC/bootstrap boundary. It deliberately
uses only supervisor-inherited file descriptors:

- a connected AF_UNIX Runtime Host IPC descriptor;
- a separate connected AF_UNIX authoritative-source descriptor;
- an already-open private signing-key descriptor.

There is no filesystem socket path, key path, PEM, verification key, owner
object, authority digest, or trusted-source implementation accepted from the
Runtime/Visual request. A caller that merely imports or executes this module but
does not possess those inherited descriptors cannot mint a grant that the
bootstrap-pinned Runtime Host verifier will accept.

All broker authority-bearing channel capabilities are process-bound. A Python
``fork()`` permanently invalidates the broker copy in the child. Child-side
invalidation closes not only registered socket objects but every inherited file
descriptor whose kernel socket identity matches a protected Runtime/source
channel, including aliases created with ``dup()``/``dup2()`` before the fork.
Supervisor-provided bootstrap descriptors are consumed exactly once by
``run_from_inherited_fds``.

The visual worker must never inherit any of these descriptors.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import stat
import struct
import time
import weakref
from dataclasses import fields
from typing import Mapping

from broker.authority_grant_broker import (
    AuthorityGrantBrokerService,
    BrokerGrantRequest,
    TrustedAuthoritySnapshot,
    TrustedAuthoritySource,
)
from broker.authority_grant_signer import AuthorityGrantBrokerSigner, BrokerSignerIdentity

MAX_IPC_MESSAGE_BYTES = 64 * 1024
_FRAME_HEADER = struct.Struct("!I")

_LIVE_BROKER_SOCKETS: weakref.WeakSet[socket.socket] = weakref.WeakSet()
_LIVE_AUTHORITY_SOURCES: weakref.WeakSet[InheritedFDAuthoritySource] = weakref.WeakSet()
_LIVE_BROKER_PROCESSES: weakref.WeakSet[AuthorityBrokerProcess] = weakref.WeakSet()
_PROTECTED_BROKER_SOCKET_IDENTITIES: set[tuple[int, int, int]] = set()
_BROKER_PROCESS_FORK_INVALIDATED = False


def _resolve_fd_scan_limit() -> int | None:
    """Return None for /proc enumeration or a finite fail-closed scan ceiling."""
    if os.path.isdir("/proc/self/fd"):
        return None
    try:
        import resource

        soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft_limit == resource.RLIM_INFINITY:
            raise RuntimeError("BROKER_FD_ALIAS_SWEEP_UNBOUNDED")
        limit = int(soft_limit)
    except (ImportError, OSError, ValueError) as exc:
        raise RuntimeError("BROKER_FD_ALIAS_SWEEP_UNAVAILABLE") from exc
    if limit <= 3 or limit > 1_048_576:
        raise RuntimeError("BROKER_FD_ALIAS_SWEEP_LIMIT_INVALID")
    return limit


_BROKER_FD_SCAN_LIMIT = _resolve_fd_scan_limit()


def _close_socket_quietly(sock: object) -> None:
    if isinstance(sock, socket.socket):
        try:
            sock.close()
        except OSError:
            pass


def _detach_socket_quietly(sock: object) -> None:
    """Mark a Python socket wrapper closed without re-closing its raw fd."""
    if isinstance(sock, socket.socket):
        try:
            sock.detach()
        except OSError:
            pass


def _close_fd_quietly(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def _fd_identity(fd: int) -> tuple[int, int, int]:
    status = os.fstat(fd)
    return (int(status.st_dev), int(status.st_ino), int(stat.S_IFMT(status.st_mode)))


def _iter_open_fds_after_fork() -> tuple[int, ...] | range:
    if _BROKER_FD_SCAN_LIMIT is None:
        try:
            return tuple(
                int(name)
                for name in os.listdir("/proc/self/fd")
                if name.isdigit()
            )
        except OSError:
            # This callback is a security boundary. If the kernel fd view that
            # was selected at trusted bootstrap becomes unavailable, do not
            # continue a child that may retain broker authority capabilities.
            os._exit(126)
    return range(_BROKER_FD_SCAN_LIMIT)


def _close_all_inherited_broker_socket_aliases() -> None:
    """Close every child fd alias of every protected broker channel.

    ``FD_CLOEXEC`` does not help a fork-without-exec child. Tracking only the
    Python socket objects is also insufficient because arbitrary ``dup`` aliases
    share the same kernel socket identity while having unrelated descriptor
    numbers and wrappers. We therefore snapshot protected socket identities in
    the owning broker and, after fork, close every open child descriptor whose
    ``fstat`` identity matches one of them.
    """
    protected = frozenset(_PROTECTED_BROKER_SOCKET_IDENTITIES)

    # Detach known wrappers first. This prevents their later close/destructor
    # from double-closing a descriptor number that the kernel might reuse after
    # the raw alias sweep.
    for sock in tuple(_LIVE_BROKER_SOCKETS):
        _detach_socket_quietly(sock)

    if not protected:
        return
    for fd in _iter_open_fds_after_fork():
        try:
            identity = _fd_identity(fd)
        except OSError:
            continue
        if identity in protected:
            _close_fd_quietly(fd)


def _after_fork_child() -> None:
    """Destroy every inherited broker channel capability in a forked child."""
    global _BROKER_PROCESS_FORK_INVALIDATED
    _BROKER_PROCESS_FORK_INVALIDATED = True

    # Close all raw aliases, including independent dup/dup2 descriptors unknown
    # to the object registry. This must happen before any higher-level broker
    # path can run in the child.
    _close_all_inherited_broker_socket_aliases()

    for source in tuple(_LIVE_AUTHORITY_SOURCES):
        source._invalidate_after_fork_child()
    for process in tuple(_LIVE_BROKER_PROCESSES):
        process._invalidate_after_fork_child()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_child)


def _require_broker_process_bootstrap_allowed() -> None:
    if not hasattr(os, "register_at_fork"):
        raise RuntimeError("BROKER_PROCESS_AT_FORK_INVALIDATION_REQUIRED")
    if _BROKER_PROCESS_FORK_INVALIDATED:
        raise PermissionError("BROKER_PROCESS_FORK_INVALIDATED")


def _register_broker_socket(sock: socket.socket) -> socket.socket:
    identity = _fd_identity(sock.fileno())
    if identity[2] != stat.S_IFSOCK:
        raise PermissionError("BROKER_CHANNEL_SOCKET_IDENTITY_REQUIRED")
    _PROTECTED_BROKER_SOCKET_IDENTITIES.add(identity)
    _LIVE_BROKER_SOCKETS.add(sock)
    return sock


class InheritedFDAuthoritySource(TrustedAuthoritySource):
    """Read authoritative snapshots over a process-bound private channel."""

    def __init__(self, source_socket: socket.socket) -> None:
        _require_broker_process_bootstrap_allowed()
        _require_private_unix_socket(source_socket, "BROKER_AUTHORITY_SOURCE_SOCKET")
        self._socket = _register_broker_socket(source_socket)
        self._owner_pid = os.getpid()
        self._fork_invalidated = False
        _LIVE_AUTHORITY_SOURCES.add(self)

    def _require_owner_process(self) -> None:
        if self._fork_invalidated:
            raise PermissionError("BROKER_AUTHORITY_SOURCE_FORK_INVALIDATED")
        if _BROKER_PROCESS_FORK_INVALIDATED:
            raise PermissionError("BROKER_PROCESS_FORK_INVALIDATED")
        if os.getpid() != self._owner_pid:
            raise PermissionError("BROKER_AUTHORITY_SOURCE_PROCESS_MISMATCH")
        if self._socket.fileno() < 0:
            raise PermissionError("BROKER_AUTHORITY_SOURCE_SOCKET_UNAVAILABLE")

    def _invalidate_after_fork_child(self) -> None:
        self._fork_invalidated = True
        self._owner_pid = -1
        _close_socket_quietly(self._socket)

    def authorize_and_snapshot(self, request: BrokerGrantRequest) -> TrustedAuthoritySnapshot:
        self._require_owner_process()
        _send_json_frame(
            self._socket,
            {
                "TYPE": "AUTHORITY_SNAPSHOT_REQUEST",
                "REQUEST_ID": request.request_id,
                "SESSION_ID": request.session_id,
                "ACTIVATION_ID": request.activation_id,
                "SOURCE_REVISION": request.source_revision,
            },
        )
        response = _recv_json_frame(self._socket)
        self._require_owner_process()
        if response.get("TYPE") != "AUTHORITY_SNAPSHOT_RESPONSE":
            raise PermissionError("BROKER_AUTHORITY_SOURCE_RESPONSE_TYPE_INVALID")
        if response.get("REQUEST_ID") != request.request_id:
            raise PermissionError("BROKER_AUTHORITY_SOURCE_REQUEST_ID_MISMATCH")
        snapshot_raw = response.get("SNAPSHOT")
        if not isinstance(snapshot_raw, Mapping):
            raise TypeError("BROKER_AUTHORITY_SOURCE_SNAPSHOT_OBJECT_REQUIRED")
        return _snapshot_from_mapping(snapshot_raw)


class AuthorityBrokerProcess:
    """Serve minimal grant requests on one process-bound Runtime Host channel."""

    def __init__(
        self,
        runtime_socket: socket.socket,
        service: AuthorityGrantBrokerService,
    ) -> None:
        _require_broker_process_bootstrap_allowed()
        _require_private_unix_socket(runtime_socket, "BROKER_RUNTIME_SOCKET")
        if not isinstance(service, AuthorityGrantBrokerService):
            raise TypeError("BROKER_SERVICE_REQUIRED")
        self._runtime_socket = _register_broker_socket(runtime_socket)
        self._service = service
        self._owner_pid = os.getpid()
        self._fork_invalidated = False
        _LIVE_BROKER_PROCESSES.add(self)

    def _require_owner_process(self) -> None:
        if self._fork_invalidated:
            raise PermissionError("BROKER_RUNTIME_PROCESS_FORK_INVALIDATED")
        if _BROKER_PROCESS_FORK_INVALIDATED:
            raise PermissionError("BROKER_PROCESS_FORK_INVALIDATED")
        if os.getpid() != self._owner_pid:
            raise PermissionError("BROKER_RUNTIME_PROCESS_MISMATCH")
        if self._runtime_socket.fileno() < 0:
            raise PermissionError("BROKER_RUNTIME_SOCKET_UNAVAILABLE")

    def _invalidate_after_fork_child(self) -> None:
        self._fork_invalidated = True
        self._owner_pid = -1
        _close_socket_quietly(self._runtime_socket)

    def serve_forever(self) -> None:
        self._require_owner_process()
        while True:
            self._require_owner_process()
            try:
                message = _recv_json_frame(self._runtime_socket)
            except EOFError:
                return
            try:
                response = self._handle_request(message)
            except Exception:
                # Fail closed. Do not fall back to in-process trust, caller
                # claims, alternate keys, or self-registration.
                response = {
                    "TYPE": "GRANT_DENIED",
                    "ERROR": "AUTHORITY_GRANT_DENIED",
                }
            self._require_owner_process()
            _send_json_frame(self._runtime_socket, response)

    def _handle_request(self, message: Mapping[str, object]) -> Mapping[str, object]:
        self._require_owner_process()
        if message.get("TYPE") != "GRANT_REQUEST":
            raise PermissionError("BROKER_IPC_REQUEST_TYPE_INVALID")
        allowed = {
            "TYPE",
            "REQUEST_ID",
            "SESSION_ID",
            "ACTIVATION_ID",
            "SOURCE_REVISION",
        }
        extras = set(message) - allowed
        if extras:
            raise PermissionError("BROKER_IPC_CALLER_AUTHORITY_FIELDS_FORBIDDEN")

        request = BrokerGrantRequest(
            request_id=_required_text(message.get("REQUEST_ID"), "REQUEST_ID"),
            session_id=_required_text(message.get("SESSION_ID"), "SESSION_ID"),
            activation_id=_required_text(message.get("ACTIVATION_ID"), "ACTIVATION_ID"),
            source_revision=_required_text(message.get("SOURCE_REVISION"), "SOURCE_REVISION"),
        )
        envelope = self._service.issue_grant(request, now_unix=int(time.time()))
        return {
            "TYPE": "AUTHORITY_GRANT",
            "REQUEST_ID": request.request_id,
            "CLAIMS": dict(envelope.claims.as_mapping()),
            "SIGNATURE_B64": envelope.signature_b64,
        }


def run_from_inherited_fds(
    *,
    runtime_ipc_fd: int,
    authority_source_fd: int,
    signing_key_fd: int,
    key_id: str,
) -> None:
    """Bootstrap exclusively from one-shot supervisor-inherited descriptors."""
    _require_broker_process_bootstrap_allowed()
    fds = (runtime_ipc_fd, authority_source_fd, signing_key_fd)
    if not all(type(fd) is int and fd >= 0 for fd in fds):
        raise ValueError("BROKER_INHERITED_FD_INVALID")
    if len(set(fds)) != len(fds):
        raise ValueError("BROKER_INHERITED_FDS_MUST_BE_DISTINCT")
    key_id = _required_text(key_id, "KEY_ID")

    runtime_socket: socket.socket | None = None
    source_socket: socket.socket | None = None
    try:
        runtime_socket = _socket_from_inherited_fd(runtime_ipc_fd, "BROKER_RUNTIME_SOCKET")
        source_socket = _socket_from_inherited_fd(
            authority_source_fd,
            "BROKER_AUTHORITY_SOURCE_SOCKET",
        )
        signer = AuthorityGrantBrokerSigner(
            BrokerSignerIdentity(key_id=key_id, bootstrap_fd=signing_key_fd)
        )
    finally:
        # These exact supervisor descriptors are bootstrap capabilities, not
        # durable broker handles. Consume them on every success/failure path.
        for fd in fds:
            _close_fd_quietly(fd)

    try:
        source = InheritedFDAuthoritySource(source_socket)
        service = AuthorityGrantBrokerService(signer, source)
        AuthorityBrokerProcess(runtime_socket, service).serve_forever()
    finally:
        _close_socket_quietly(runtime_socket)
        _close_socket_quietly(source_socket)


def _socket_from_inherited_fd(fd: int, name: str) -> socket.socket:
    _require_broker_process_bootstrap_allowed()
    try:
        duplicate = os.dup(fd)
        os.set_inheritable(duplicate, False)
        sock = socket.socket(fileno=duplicate)
    except OSError as exc:
        raise RuntimeError(f"{name}_FD_UNAVAILABLE") from exc
    try:
        _require_private_unix_socket(sock, name)
        return _register_broker_socket(sock)
    except Exception:
        sock.close()
        raise


def _require_private_unix_socket(sock: object, name: str) -> socket.socket:
    if not isinstance(sock, socket.socket):
        raise TypeError(f"{name}_REQUIRED")
    if sock.family != socket.AF_UNIX:
        raise PermissionError(f"{name}_AF_UNIX_REQUIRED")
    if sock.type & socket.SOCK_STREAM != socket.SOCK_STREAM:
        raise PermissionError(f"{name}_SOCK_STREAM_REQUIRED")
    try:
        sock.getpeername()
    except OSError as exc:
        raise PermissionError(f"{name}_CONNECTED_PEER_REQUIRED") from exc
    return sock


def _send_json_frame(sock: socket.socket, payload: Mapping[str, object]) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError("BROKER_IPC_PAYLOAD_OBJECT_REQUIRED")
    data = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if not data or len(data) > MAX_IPC_MESSAGE_BYTES:
        raise ValueError("BROKER_IPC_PAYLOAD_SIZE_INVALID")
    sock.sendall(_FRAME_HEADER.pack(len(data)) + data)


def _recv_json_frame(sock: socket.socket) -> Mapping[str, object]:
    header = _recv_exact(sock, _FRAME_HEADER.size)
    size = _FRAME_HEADER.unpack(header)[0]
    if size <= 0 or size > MAX_IPC_MESSAGE_BYTES:
        raise ValueError("BROKER_IPC_FRAME_SIZE_INVALID")
    raw = _recv_exact(sock, size)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("BROKER_IPC_JSON_INVALID") from exc
    if not isinstance(payload, dict):
        raise TypeError("BROKER_IPC_JSON_OBJECT_REQUIRED")
    return payload


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            if remaining == size:
                raise EOFError
            raise ConnectionError("BROKER_IPC_TRUNCATED_FRAME")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _snapshot_from_mapping(raw: Mapping[str, object]) -> TrustedAuthoritySnapshot:
    names = {field.name for field in fields(TrustedAuthoritySnapshot)}
    if set(raw) != names:
        raise PermissionError("BROKER_AUTHORITY_SOURCE_SNAPSHOT_SCHEMA_MISMATCH")
    values = {name: _required_text(raw.get(name), f"AUTHORITY_{name.upper()}") for name in names}
    return TrustedAuthoritySnapshot(**values)


def _required_text(value: object, name: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"BROKER_{name}_REQUIRED")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="DND isolated authority broker")
    parser.add_argument("--runtime-ipc-fd", type=int, required=True)
    parser.add_argument("--authority-source-fd", type=int, required=True)
    parser.add_argument("--signing-key-fd", type=int, required=True)
    parser.add_argument("--key-id", required=True)
    args = parser.parse_args()
    run_from_inherited_fds(
        runtime_ipc_fd=args.runtime_ipc_fd,
        authority_source_fd=args.authority_source_fd,
        signing_key_fd=args.signing_key_fd,
        key_id=args.key_id,
    )


if __name__ == "__main__":
    main()


__all__ = [
    "MAX_IPC_MESSAGE_BYTES",
    "InheritedFDAuthoritySource",
    "AuthorityBrokerProcess",
    "run_from_inherited_fds",
]
