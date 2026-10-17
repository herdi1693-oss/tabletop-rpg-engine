#!/usr/bin/env python3
"""Broker-side Ed25519 signing primitive for Runtime authority grants.

Signing authority is process-bound. A forked Python child cannot reuse or
re-bootstrap inherited broker signing authority.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
import threading
import weakref
from dataclasses import dataclass
from pathlib import Path

from runtime.authority_grant_protocol import (
    AuthorityGrantClaims,
    AuthorityGrantEnvelope,
    canonical_grant_payload,
)

DEFAULT_OPENSSL_BINARY = "openssl"
DEFAULT_SIGN_TIMEOUT_SECONDS = 5
MAX_BOOTSTRAP_PRIVATE_KEY_BYTES = 16 * 1024


@dataclass(frozen=True)
class BrokerSignerIdentity:
    key_id: str
    bootstrap_fd: int


_LIVE_SIGNERS = weakref.WeakSet()
_BROKER_FORK_INVALIDATED = False


def _zero_buffer(buffer: bytearray) -> None:
    for index in range(len(buffer)):
        buffer[index] = 0


def _after_fork_child() -> None:
    global _BROKER_FORK_INVALIDATED
    _BROKER_FORK_INVALIDATED = True
    for signer in tuple(_LIVE_SIGNERS):
        signer._invalidate_after_fork_child()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_child)


class AuthorityGrantBrokerSigner:
    """Ed25519 signer bound to the broker PID that constructed it."""

    def __init__(
        self,
        identity: BrokerSignerIdentity,
        *,
        openssl_binary: str = DEFAULT_OPENSSL_BINARY,
        sign_timeout_seconds: int = DEFAULT_SIGN_TIMEOUT_SECONDS,
    ) -> None:
        if not isinstance(identity, BrokerSignerIdentity):
            raise TypeError("BROKER_SIGNER_IDENTITY_REQUIRED")
        if type(identity.key_id) is not str or not identity.key_id:
            raise ValueError("BROKER_SIGNER_KEY_ID_REQUIRED")
        if type(identity.bootstrap_fd) is not int or identity.bootstrap_fd < 0:
            raise ValueError("BROKER_SIGNER_BOOTSTRAP_FD_INVALID")
        if type(sign_timeout_seconds) is not int or sign_timeout_seconds <= 0:
            raise ValueError("BROKER_SIGN_TIMEOUT_INVALID")
        if not hasattr(os, "register_at_fork"):
            raise RuntimeError("BROKER_SIGNER_AT_FORK_INVALIDATION_REQUIRED")
        if _BROKER_FORK_INVALIDATED:
            raise PermissionError("BROKER_SIGNER_FORK_INVALIDATED")

        binary = shutil.which(str(openssl_binary or ""))
        if not binary:
            raise RuntimeError("BROKER_OPENSSL_UNAVAILABLE")

        key_buffer = bytearray(_read_bootstrap_private_key(identity.bootstrap_fd))
        try:
            _validate_private_key_pem(key_buffer)
        except BaseException:
            _zero_buffer(key_buffer)
            raise

        self._key_id = identity.key_id
        self._private_key_pem = key_buffer
        self._openssl_binary = binary
        self._sign_timeout_seconds = sign_timeout_seconds
        self._owner_pid = os.getpid()
        self._fork_invalidated = False
        self._sign_lock = threading.RLock()
        _LIVE_SIGNERS.add(self)

    def _require_owner_process(self) -> None:
        if self._fork_invalidated or _BROKER_FORK_INVALIDATED:
            raise PermissionError("BROKER_SIGNER_FORK_INVALIDATED")
        if os.getpid() != self._owner_pid:
            raise PermissionError("BROKER_SIGNER_PROCESS_MISMATCH")
        if not self._private_key_pem:
            raise PermissionError("BROKER_SIGNER_KEY_UNAVAILABLE")

    def _invalidate_after_fork_child(self) -> None:
        self._fork_invalidated = True
        self._owner_pid = -1
        _zero_buffer(self._private_key_pem)
        self._private_key_pem.clear()
        self._sign_lock = threading.RLock()

    @property
    def key_id(self) -> str:
        self._require_owner_process()
        return self._key_id

    def sign(self, claims: AuthorityGrantClaims) -> AuthorityGrantEnvelope:
        self._require_owner_process()
        if not isinstance(claims, AuthorityGrantClaims):
            raise TypeError("AUTHORITY_GRANT_CLAIMS_REQUIRED")
        with self._sign_lock:
            self._require_owner_process()
            if claims.key_id != self._key_id:
                raise PermissionError("BROKER_GRANT_KEY_ID_MISMATCH")
            payload = canonical_grant_payload(claims)
            signature = _sign_ed25519(
                self._openssl_binary,
                self._private_key_pem,
                payload,
                timeout_seconds=self._sign_timeout_seconds,
            )
        return AuthorityGrantEnvelope(
            claims=claims,
            signature_b64=base64.b64encode(signature).decode("ascii"),
        )


def _read_bootstrap_private_key(fd: int) -> bytes:
    try:
        duplicate = os.dup(fd)
    except OSError as exc:
        raise RuntimeError("BROKER_BOOTSTRAP_KEY_FD_UNAVAILABLE") from exc
    try:
        with os.fdopen(duplicate, "rb", closefd=True) as stream:
            data = stream.read(MAX_BOOTSTRAP_PRIVATE_KEY_BYTES + 1)
    except OSError as exc:
        raise RuntimeError("BROKER_BOOTSTRAP_KEY_READ_FAILED") from exc
    if not data:
        raise RuntimeError("BROKER_BOOTSTRAP_PRIVATE_KEY_EMPTY")
    if len(data) > MAX_BOOTSTRAP_PRIVATE_KEY_BYTES:
        raise RuntimeError("BROKER_BOOTSTRAP_PRIVATE_KEY_TOO_LARGE")
    return bytes(data)


def _validate_private_key_pem(private_key_pem: bytes | bytearray) -> None:
    if b"BEGIN PRIVATE KEY" not in private_key_pem:
        raise ValueError("BROKER_ED25519_PRIVATE_KEY_PEM_REQUIRED")
    if b"BEGIN PUBLIC KEY" in private_key_pem:
        raise ValueError("BROKER_PRIVATE_KEY_MATERIAL_INVALID")


def _sign_ed25519(
    openssl_binary: str,
    private_key_pem: bytes | bytearray,
    payload: bytes,
    *,
    timeout_seconds: int,
) -> bytes:
    with tempfile.TemporaryDirectory(prefix="dnd-authority-sign-") as tmp:
        root = Path(tmp)
        key_path = root / "private-key.pem"
        payload_path = root / "payload.bin"
        signature_path = root / "signature.bin"
        key_path.write_bytes(private_key_pem)
        payload_path.write_bytes(payload)
        try:
            os.chmod(key_path, 0o600)
            result = subprocess.run(
                [
                    openssl_binary,
                    "pkeyutl",
                    "-sign",
                    "-inkey",
                    str(key_path),
                    "-rawin",
                    "-in",
                    str(payload_path),
                    "-out",
                    str(signature_path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("BROKER_AUTHORITY_GRANT_SIGNER_FAILURE") from exc
        finally:
            try:
                key_path.write_bytes(b"")
            except OSError:
                pass
        if result.returncode != 0:
            raise RuntimeError("BROKER_AUTHORITY_GRANT_SIGN_FAILED")
        try:
            signature = signature_path.read_bytes()
        except OSError as exc:
            raise RuntimeError("BROKER_AUTHORITY_GRANT_SIGNATURE_MISSING") from exc
        if len(signature) != 64:
            raise RuntimeError("BROKER_ED25519_SIGNATURE_LENGTH_INVALID")
        return signature


__all__ = ["BrokerSignerIdentity", "AuthorityGrantBrokerSigner"]
