#!/usr/bin/env python3
"""Authority Broker request validation and trusted-owner adapter boundary.

This module belongs to the separately deployed broker process.

Security model:
- an untrusted Runtime/Visual caller may submit only correlation/session fields;
- owner IDs, digests, PKP/leak facts and Display Ledger lineage are NEVER taken
  from the request;
- those authority claims are obtained only from the broker's bootstrap-pinned
  ``TrustedAuthoritySource`` adapter;
- the signing key remains encapsulated by ``AuthorityGrantBrokerSigner``;
- there is no fallback to caller-provided claims, owner objects or key material;
- a broker service is bound to the exact PID that assembled it and cannot issue
  grants from a forked Python child.
"""
from __future__ import annotations

import os
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass

from broker.authority_grant_signer import AuthorityGrantBrokerSigner
from runtime.authority_grant_protocol import (
    DEFAULT_MAX_TTL_SECONDS,
    AuthorityGrantClaims,
    AuthorityGrantEnvelope,
)

DEFAULT_GRANT_TTL_SECONDS = 60


@dataclass(frozen=True)
class BrokerGrantRequest:
    request_id: str
    session_id: str
    activation_id: str
    source_revision: str


@dataclass(frozen=True)
class TrustedAuthoritySnapshot:
    session_id: str
    activation_id: str
    source_revision: str
    checkpoint_receipt_id: str
    checkpoint_digest: str
    event_id: str
    applied_event_ledger_owner_id: str
    applied_event_ledger_snapshot_digest: str
    player_knowledge_projection_id: str
    observer_branch_id: str
    player_knowledge_projection_revision: str
    player_knowledge_projection_digest: str
    leak_gate_receipt_id: str
    leak_gate_receipt_digest: str
    player_safe_bundle_digest: str
    display_ledger_owner_id: str
    display_ledger_backing_store_id: str
    display_ledger_backing_namespace: str


class TrustedAuthoritySource(ABC):
    @abstractmethod
    def authorize_and_snapshot(self, request: BrokerGrantRequest) -> TrustedAuthoritySnapshot:
        raise NotImplementedError


class AuthorityGrantBrokerService:
    """Issue grants only from broker-owned authority state in one process."""

    def __init__(
        self,
        signer: AuthorityGrantBrokerSigner,
        authority_source: TrustedAuthoritySource,
        *,
        grant_ttl_seconds: int = DEFAULT_GRANT_TTL_SECONDS,
    ) -> None:
        if not isinstance(signer, AuthorityGrantBrokerSigner):
            raise TypeError("BROKER_SIGNER_REQUIRED")
        if not isinstance(authority_source, TrustedAuthoritySource):
            raise TypeError("BROKER_TRUSTED_AUTHORITY_SOURCE_REQUIRED")
        if type(grant_ttl_seconds) is not int or grant_ttl_seconds <= 0:
            raise ValueError("BROKER_GRANT_TTL_INVALID")
        if grant_ttl_seconds > DEFAULT_MAX_TTL_SECONDS:
            raise ValueError("BROKER_GRANT_TTL_EXCEEDS_PROTOCOL_MAX")

        self._signer = signer
        self._authority_source = authority_source
        self._grant_ttl_seconds = grant_ttl_seconds
        self._owner_pid = os.getpid()

    def _require_owner_process(self) -> None:
        if os.getpid() != self._owner_pid:
            raise PermissionError("BROKER_SERVICE_PROCESS_MISMATCH")

    def issue_grant(self, request: BrokerGrantRequest, *, now_unix: int) -> AuthorityGrantEnvelope:
        self._require_owner_process()
        if type(request) is not BrokerGrantRequest:
            raise TypeError("BROKER_GRANT_REQUEST_REQUIRED")
        if type(now_unix) is not int or now_unix < 0:
            raise ValueError("BROKER_NOW_UNIX_INVALID")
        _validate_request(request)

        snapshot = self._authority_source.authorize_and_snapshot(request)
        if type(snapshot) is not TrustedAuthoritySnapshot:
            raise TypeError("BROKER_TRUSTED_AUTHORITY_SNAPSHOT_REQUIRED")
        _validate_snapshot(snapshot)
        _bind_request_to_snapshot(request, snapshot)

        claims = AuthorityGrantClaims(
            grant_id=f"GRANT-{secrets.token_hex(16)}",
            key_id=self._signer.key_id,
            request_id=request.request_id,
            session_id=snapshot.session_id,
            activation_id=snapshot.activation_id,
            source_revision=snapshot.source_revision,
            checkpoint_receipt_id=snapshot.checkpoint_receipt_id,
            checkpoint_digest=snapshot.checkpoint_digest,
            event_id=snapshot.event_id,
            applied_event_ledger_owner_id=snapshot.applied_event_ledger_owner_id,
            applied_event_ledger_snapshot_digest=snapshot.applied_event_ledger_snapshot_digest,
            player_knowledge_projection_id=snapshot.player_knowledge_projection_id,
            observer_branch_id=snapshot.observer_branch_id,
            player_knowledge_projection_revision=snapshot.player_knowledge_projection_revision,
            player_knowledge_projection_digest=snapshot.player_knowledge_projection_digest,
            leak_gate_receipt_id=snapshot.leak_gate_receipt_id,
            leak_gate_receipt_digest=snapshot.leak_gate_receipt_digest,
            player_safe_bundle_digest=snapshot.player_safe_bundle_digest,
            display_ledger_owner_id=snapshot.display_ledger_owner_id,
            display_ledger_backing_store_id=snapshot.display_ledger_backing_store_id,
            display_ledger_backing_namespace=snapshot.display_ledger_backing_namespace,
            issued_at_unix=now_unix,
            expires_at_unix=now_unix + self._grant_ttl_seconds,
            nonce=f"NONCE-{secrets.token_hex(16)}",
        )
        return self._signer.sign(claims)


def _require_text(value: object, name: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"BROKER_{name}_REQUIRED")
    return value


def _validate_request(request: BrokerGrantRequest) -> None:
    _require_text(request.request_id, "REQUEST_ID")
    _require_text(request.session_id, "SESSION_ID")
    _require_text(request.activation_id, "ACTIVATION_ID")
    _require_text(request.source_revision, "SOURCE_REVISION")


def _validate_snapshot(snapshot: TrustedAuthoritySnapshot) -> None:
    fields = {
        "SESSION_ID": snapshot.session_id,
        "ACTIVATION_ID": snapshot.activation_id,
        "SOURCE_REVISION": snapshot.source_revision,
        "CHECKPOINT_RECEIPT_ID": snapshot.checkpoint_receipt_id,
        "CHECKPOINT_DIGEST": snapshot.checkpoint_digest,
        "EVENT_ID": snapshot.event_id,
        "APPLIED_EVENT_LEDGER_OWNER_ID": snapshot.applied_event_ledger_owner_id,
        "APPLIED_EVENT_LEDGER_SNAPSHOT_DIGEST": snapshot.applied_event_ledger_snapshot_digest,
        "PLAYER_KNOWLEDGE_PROJECTION_ID": snapshot.player_knowledge_projection_id,
        "OBSERVER_BRANCH_ID": snapshot.observer_branch_id,
        "PLAYER_KNOWLEDGE_PROJECTION_REVISION": snapshot.player_knowledge_projection_revision,
        "PLAYER_KNOWLEDGE_PROJECTION_DIGEST": snapshot.player_knowledge_projection_digest,
        "LEAK_GATE_RECEIPT_ID": snapshot.leak_gate_receipt_id,
        "LEAK_GATE_RECEIPT_DIGEST": snapshot.leak_gate_receipt_digest,
        "PLAYER_SAFE_BUNDLE_DIGEST": snapshot.player_safe_bundle_digest,
        "DISPLAY_LEDGER_OWNER_ID": snapshot.display_ledger_owner_id,
        "DISPLAY_LEDGER_BACKING_STORE_ID": snapshot.display_ledger_backing_store_id,
        "DISPLAY_LEDGER_BACKING_NAMESPACE": snapshot.display_ledger_backing_namespace,
    }
    for name, value in fields.items():
        _require_text(value, f"AUTHORITY_{name}")


def _bind_request_to_snapshot(
    request: BrokerGrantRequest,
    snapshot: TrustedAuthoritySnapshot,
) -> None:
    checks = {
        "SESSION_ID": (request.session_id, snapshot.session_id),
        "ACTIVATION_ID": (request.activation_id, snapshot.activation_id),
        "SOURCE_REVISION": (request.source_revision, snapshot.source_revision),
    }
    for name, (requested, authoritative) in checks.items():
        if requested != authoritative:
            raise PermissionError(f"BROKER_REQUEST_{name}_NOT_AUTHORIZED")


__all__ = [
    "DEFAULT_GRANT_TTL_SECONDS",
    "BrokerGrantRequest",
    "TrustedAuthoritySnapshot",
    "TrustedAuthoritySource",
    "AuthorityGrantBrokerService",
]
