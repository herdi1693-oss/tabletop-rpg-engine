#!/usr/bin/env python3
"""Trusted Runtime Host client for the isolated Authority Broker.

The client accepts only a cryptographically authenticated RuntimeHostRequestContext.
It never accepts a caller-selected REQUEST_ID/session/activation/revision tuple.
The exact Host-owned identity is serialized to the Broker request, the Broker
response must echo the same REQUEST_ID, and the signed claims must carry the same
REQUEST_ID before the envelope can continue to Runtime materialization.

The Host-side Broker client is process-bound. ``fork()`` does not clone a usable
Broker capability: every live client is invalidated and its child-side socket is
closed by an at-fork handler, while a PID guard fails closed even if callback
registration is unavailable or bypassed.
"""
from __future__ import annotations

import json
import os
import socket
import struct
import weakref
from typing import Mapping

from runtime.authority_grant_protocol import (
    AUTHORITY_GRANT_SCHEMA,
    AuthorityGrantClaims,
    AuthorityGrantEnvelope,
)
from runtime.runtime_host_request_context import (
    RuntimeHostRequestContext,
    verify_runtime_host_request_context,
)

MAX_IPC_MESSAGE_BYTES = 64 * 1024
_FRAME_HEADER = struct.Struct("!I")
_LIVE_CLIENTS: weakref.WeakSet[RuntimeHostAuthorityBrokerClient] = weakref.WeakSet()


def _invalidate_clients_after_fork_in_child() -> None:
    """Close every cloned Host-side Broker socket in the forked child."""

    global _LIVE_CLIENTS
    clients = list(_LIVE_CLIENTS)
    _LIVE_CLIENTS = weakref.WeakSet()
    for client in clients:
        try:
            client._invalidate_after_fork_in_child()
        except BaseException:
            # The PID guard remains an independent fail-closed boundary even if
            # a defensive close encounters an unexpected local error.
            client._fork_invalidated = True


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_invalidate_clients_after_fork_in_child)


class RuntimeHostAuthorityBrokerClient:
    """One connected Host-side channel to the isolated Authority Broker."""

    def __init__(self, broker_socket: socket.socket) -> None:
        self._socket = _require_private_unix_socket(broker_socket)
        self._owner_pid = os.getpid()
        self._fork_invalidated = False
        try:
            os.set_inheritable(self._socket.fileno(), False)
        except OSError as exc:
            self._socket.close()
            raise RuntimeError("RUNTIME_HOST_BROKER_IPC_FD_UNAVAILABLE") from exc
        _LIVE_CLIENTS.add(self)

    @classmethod
    def from_inherited_fd(cls, fd: int) -> "RuntimeHostAuthorityBrokerClient":
        """Take ownership of one inherited Broker IPC descriptor.

        No ``dup()`` is retained. The returned client owns the exact descriptor;
        its child-side copy is closed automatically after ``fork()``.
        """

        if type(fd) is not int or fd < 0:
            raise ValueError("RUNTIME_HOST_BROKER_IPC_FD_INVALID")
        try:
            os.fstat(fd)
            os.set_inheritable(fd, False)
            sock = socket.socket(fileno=fd)
        except OSError as exc:
            try:
                os.close(fd)
            except OSError:
                pass
            raise RuntimeError("RUNTIME_HOST_BROKER_IPC_FD_UNAVAILABLE") from exc
        try:
            return cls(sock)
        except Exception:
            sock.close()
            raise

    def _assert_owner_process(self) -> None:
        if self._fork_invalidated or self._owner_pid != os.getpid():
            raise PermissionError("RUNTIME_HOST_BROKER_CLIENT_FORKED_CHILD_FORBIDDEN")
        if self._socket.fileno() < 0:
            raise RuntimeError("RUNTIME_HOST_BROKER_CLIENT_CLOSED")

    def _invalidate_after_fork_in_child(self) -> None:
        self._fork_invalidated = True
        try:
            self._socket.close()
        except OSError:
            pass

    def request_grant(
        self,
        host_request_context: RuntimeHostRequestContext,
    ) -> AuthorityGrantEnvelope:
        self._assert_owner_process()
        context = verify_runtime_host_request_context(
            host_request_context,
            require_active=True,
        )
        _send_json_frame(
            self._socket,
            {
                "TYPE": "GRANT_REQUEST",
                "REQUEST_ID": context.request_id,
                "SESSION_ID": context.session_id,
                "ACTIVATION_ID": context.activation_id,
                "SOURCE_REVISION": context.source_revision,
            },
        )
        response = _recv_json_frame(self._socket)
        if response.get("TYPE") != "AUTHORITY_GRANT":
            raise PermissionError("RUNTIME_HOST_BROKER_GRANT_DENIED")
        if response.get("REQUEST_ID") != context.request_id:
            raise PermissionError("RUNTIME_HOST_BROKER_RESPONSE_REQUEST_ID_MISMATCH")
        claims_raw = response.get("CLAIMS")
        signature_b64 = response.get("SIGNATURE_B64")
        claims = _claims_from_mapping(claims_raw)
        if claims.request_id != context.request_id:
            raise PermissionError("RUNTIME_HOST_BROKER_CLAIMS_REQUEST_ID_MISMATCH")
        if claims.session_id != context.session_id:
            raise PermissionError("RUNTIME_HOST_BROKER_CLAIMS_SESSION_ID_MISMATCH")
        if claims.activation_id != context.activation_id:
            raise PermissionError("RUNTIME_HOST_BROKER_CLAIMS_ACTIVATION_ID_MISMATCH")
        if claims.source_revision != context.source_revision:
            raise PermissionError("RUNTIME_HOST_BROKER_CLAIMS_SOURCE_REVISION_MISMATCH")
        if type(signature_b64) is not str or not signature_b64:
            raise ValueError("RUNTIME_HOST_BROKER_SIGNATURE_REQUIRED")
        return AuthorityGrantEnvelope(claims=claims, signature_b64=signature_b64)

    def close(self) -> None:
        _LIVE_CLIENTS.discard(self)
        self._socket.close()


def _require_private_unix_socket(sock: object) -> socket.socket:
    if not isinstance(sock, socket.socket):
        raise TypeError("RUNTIME_HOST_BROKER_SOCKET_REQUIRED")
    if sock.family != socket.AF_UNIX:
        raise PermissionError("RUNTIME_HOST_BROKER_SOCKET_AF_UNIX_REQUIRED")
    if sock.type & socket.SOCK_STREAM != socket.SOCK_STREAM:
        raise PermissionError("RUNTIME_HOST_BROKER_SOCKET_STREAM_REQUIRED")
    try:
        sock.getpeername()
    except OSError as exc:
        raise PermissionError("RUNTIME_HOST_BROKER_SOCKET_CONNECTED_PEER_REQUIRED") from exc
    return sock


def _send_json_frame(sock: socket.socket, payload: Mapping[str, object]) -> None:
    raw = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if not raw or len(raw) > MAX_IPC_MESSAGE_BYTES:
        raise ValueError("RUNTIME_HOST_BROKER_IPC_PAYLOAD_SIZE_INVALID")
    sock.sendall(_FRAME_HEADER.pack(len(raw)) + raw)


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            if remaining == size:
                raise EOFError
            raise ConnectionError("RUNTIME_HOST_BROKER_IPC_TRUNCATED_FRAME")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_json_frame(sock: socket.socket) -> Mapping[str, object]:
    header = _recv_exact(sock, _FRAME_HEADER.size)
    size = _FRAME_HEADER.unpack(header)[0]
    if size <= 0 or size > MAX_IPC_MESSAGE_BYTES:
        raise ValueError("RUNTIME_HOST_BROKER_IPC_FRAME_SIZE_INVALID")
    raw = _recv_exact(sock, size)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("RUNTIME_HOST_BROKER_IPC_JSON_INVALID") from exc
    if not isinstance(payload, dict):
        raise TypeError("RUNTIME_HOST_BROKER_IPC_OBJECT_REQUIRED")
    return payload


def _claims_from_mapping(raw: object) -> AuthorityGrantClaims:
    if not isinstance(raw, Mapping):
        raise TypeError("RUNTIME_HOST_BROKER_CLAIMS_OBJECT_REQUIRED")
    expected = {
        "SCHEMA",
        "GRANT_ID",
        "KEY_ID",
        "REQUEST_ID",
        "SESSION_ID",
        "ACTIVATION_ID",
        "SOURCE_REVISION",
        "CHECKPOINT_RECEIPT_ID",
        "CHECKPOINT_DIGEST",
        "EVENT_ID",
        "APPLIED_EVENT_LEDGER_OWNER_ID",
        "APPLIED_EVENT_LEDGER_SNAPSHOT_DIGEST",
        "PLAYER_KNOWLEDGE_PROJECTION_ID",
        "OBSERVER_BRANCH_ID",
        "PLAYER_KNOWLEDGE_PROJECTION_REVISION",
        "PLAYER_KNOWLEDGE_PROJECTION_DIGEST",
        "LEAK_GATE_RECEIPT_ID",
        "LEAK_GATE_RECEIPT_DIGEST",
        "PLAYER_SAFE_BUNDLE_DIGEST",
        "DISPLAY_LEDGER_OWNER_ID",
        "DISPLAY_LEDGER_BACKING_STORE_ID",
        "DISPLAY_LEDGER_BACKING_NAMESPACE",
        "ISSUED_AT_UNIX",
        "EXPIRES_AT_UNIX",
        "NONCE",
    }
    if set(raw) != expected:
        raise PermissionError("RUNTIME_HOST_BROKER_CLAIMS_SCHEMA_MISMATCH")
    if raw.get("SCHEMA") != AUTHORITY_GRANT_SCHEMA:
        raise PermissionError("RUNTIME_HOST_BROKER_GRANT_SCHEMA_INVALID")
    text_names = expected - {"SCHEMA", "ISSUED_AT_UNIX", "EXPIRES_AT_UNIX"}
    for name in text_names:
        if type(raw.get(name)) is not str or not raw.get(name):
            raise ValueError(f"RUNTIME_HOST_BROKER_{name}_REQUIRED")
    if type(raw.get("ISSUED_AT_UNIX")) is not int or type(raw.get("EXPIRES_AT_UNIX")) is not int:
        raise ValueError("RUNTIME_HOST_BROKER_GRANT_TIME_FIELDS_INVALID")
    kwargs = {
        "grant_id": raw["GRANT_ID"],
        "key_id": raw["KEY_ID"],
        "request_id": raw["REQUEST_ID"],
        "session_id": raw["SESSION_ID"],
        "activation_id": raw["ACTIVATION_ID"],
        "source_revision": raw["SOURCE_REVISION"],
        "checkpoint_receipt_id": raw["CHECKPOINT_RECEIPT_ID"],
        "checkpoint_digest": raw["CHECKPOINT_DIGEST"],
        "event_id": raw["EVENT_ID"],
        "applied_event_ledger_owner_id": raw["APPLIED_EVENT_LEDGER_OWNER_ID"],
        "applied_event_ledger_snapshot_digest": raw["APPLIED_EVENT_LEDGER_SNAPSHOT_DIGEST"],
        "player_knowledge_projection_id": raw["PLAYER_KNOWLEDGE_PROJECTION_ID"],
        "observer_branch_id": raw["OBSERVER_BRANCH_ID"],
        "player_knowledge_projection_revision": raw["PLAYER_KNOWLEDGE_PROJECTION_REVISION"],
        "player_knowledge_projection_digest": raw["PLAYER_KNOWLEDGE_PROJECTION_DIGEST"],
        "leak_gate_receipt_id": raw["LEAK_GATE_RECEIPT_ID"],
        "leak_gate_receipt_digest": raw["LEAK_GATE_RECEIPT_DIGEST"],
        "player_safe_bundle_digest": raw["PLAYER_SAFE_BUNDLE_DIGEST"],
        "display_ledger_owner_id": raw["DISPLAY_LEDGER_OWNER_ID"],
        "display_ledger_backing_store_id": raw["DISPLAY_LEDGER_BACKING_STORE_ID"],
        "display_ledger_backing_namespace": raw["DISPLAY_LEDGER_BACKING_NAMESPACE"],
        "issued_at_unix": raw["ISSUED_AT_UNIX"],
        "expires_at_unix": raw["EXPIRES_AT_UNIX"],
        "nonce": raw["NONCE"],
    }
    return AuthorityGrantClaims(**kwargs)


__all__ = ["RuntimeHostAuthorityBrokerClient"]
