#!/usr/bin/env python3
"""Authority-grant protocol contract for the v1.3.8 Runtime candidate.

This module is intentionally verification-side protocol code only. It contains
no signing key, no grant minting API, no authority-owner registration API and
no fallback to the in-process Runtime assembly registry.

The actual authority grant must be issued outside the visual/request caller
interpreter by a trusted Runtime broker/bootstrap boundary. This module only
normalizes and validates the immutable claims that such a grant must bind.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping

AUTHORITY_GRANT_SCHEMA = "DND_RUNTIME_AUTHORITY_GRANT_V1"
DEFAULT_MAX_TTL_SECONDS = 120


@dataclass(frozen=True)
class AuthorityGrantClaims:
    grant_id: str
    key_id: str
    request_id: str
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
    issued_at_unix: int
    expires_at_unix: int
    nonce: str

    def as_mapping(self) -> Mapping[str, object]:
        return {
            "SCHEMA": AUTHORITY_GRANT_SCHEMA,
            "GRANT_ID": self.grant_id,
            "KEY_ID": self.key_id,
            "REQUEST_ID": self.request_id,
            "SESSION_ID": self.session_id,
            "ACTIVATION_ID": self.activation_id,
            "SOURCE_REVISION": self.source_revision,
            "CHECKPOINT_RECEIPT_ID": self.checkpoint_receipt_id,
            "CHECKPOINT_DIGEST": self.checkpoint_digest,
            "EVENT_ID": self.event_id,
            "APPLIED_EVENT_LEDGER_OWNER_ID": self.applied_event_ledger_owner_id,
            "APPLIED_EVENT_LEDGER_SNAPSHOT_DIGEST": self.applied_event_ledger_snapshot_digest,
            "PLAYER_KNOWLEDGE_PROJECTION_ID": self.player_knowledge_projection_id,
            "OBSERVER_BRANCH_ID": self.observer_branch_id,
            "PLAYER_KNOWLEDGE_PROJECTION_REVISION": self.player_knowledge_projection_revision,
            "PLAYER_KNOWLEDGE_PROJECTION_DIGEST": self.player_knowledge_projection_digest,
            "LEAK_GATE_RECEIPT_ID": self.leak_gate_receipt_id,
            "LEAK_GATE_RECEIPT_DIGEST": self.leak_gate_receipt_digest,
            "PLAYER_SAFE_BUNDLE_DIGEST": self.player_safe_bundle_digest,
            "DISPLAY_LEDGER_OWNER_ID": self.display_ledger_owner_id,
            "DISPLAY_LEDGER_BACKING_STORE_ID": self.display_ledger_backing_store_id,
            "DISPLAY_LEDGER_BACKING_NAMESPACE": self.display_ledger_backing_namespace,
            "ISSUED_AT_UNIX": self.issued_at_unix,
            "EXPIRES_AT_UNIX": self.expires_at_unix,
            "NONCE": self.nonce,
        }


@dataclass(frozen=True)
class AuthorityGrantEnvelope:
    claims: AuthorityGrantClaims
    signature_b64: str


@dataclass(frozen=True)
class GrantBindingExpectation:
    request_id: str
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


def canonical_grant_payload(claims: AuthorityGrantClaims) -> bytes:
    """Return the exact bytes that the external broker must sign."""
    return json.dumps(
        dict(claims.as_mapping()),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _require_text(value: object, name: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"AUTHORITY_GRANT_{name}_REQUIRED")
    return value


def validate_grant_claims(
    claims: AuthorityGrantClaims,
    expected: GrantBindingExpectation,
    *,
    now_unix: int,
    max_ttl_seconds: int = DEFAULT_MAX_TTL_SECONDS,
) -> None:
    """Fail closed unless grant claims exactly match the trusted host state.

    ``expected.request_id`` is supplied by the trusted Runtime Host request /
    transaction context. It must never be copied from the grant being verified
    or from the visual/player-safe request payload.

    Cryptographic signature verification is deliberately not implemented here;
    it must be performed by the trusted host against a bootstrap-pinned
    verification root before this semantic binding check is called.
    """
    _require_text(claims.grant_id, "GRANT_ID")
    _require_text(claims.key_id, "KEY_ID")
    _require_text(claims.request_id, "REQUEST_ID")
    _require_text(claims.nonce, "NONCE")

    if type(claims.issued_at_unix) is not int or type(claims.expires_at_unix) is not int:
        raise ValueError("AUTHORITY_GRANT_TIME_FIELDS_INVALID")
    if claims.expires_at_unix <= claims.issued_at_unix:
        raise ValueError("AUTHORITY_GRANT_EXPIRY_INVALID")
    if claims.expires_at_unix - claims.issued_at_unix > int(max_ttl_seconds):
        raise ValueError("AUTHORITY_GRANT_TTL_EXCEEDED")
    if now_unix < claims.issued_at_unix:
        raise ValueError("AUTHORITY_GRANT_NOT_YET_VALID")
    if now_unix >= claims.expires_at_unix:
        raise ValueError("AUTHORITY_GRANT_EXPIRED")

    checks = {
        "REQUEST_ID": (claims.request_id, expected.request_id),
        "SESSION_ID": (claims.session_id, expected.session_id),
        "ACTIVATION_ID": (claims.activation_id, expected.activation_id),
        "SOURCE_REVISION": (claims.source_revision, expected.source_revision),
        "CHECKPOINT_RECEIPT_ID": (claims.checkpoint_receipt_id, expected.checkpoint_receipt_id),
        "CHECKPOINT_DIGEST": (claims.checkpoint_digest, expected.checkpoint_digest),
        "EVENT_ID": (claims.event_id, expected.event_id),
        "APPLIED_EVENT_LEDGER_OWNER_ID": (
            claims.applied_event_ledger_owner_id,
            expected.applied_event_ledger_owner_id,
        ),
        "APPLIED_EVENT_LEDGER_SNAPSHOT_DIGEST": (
            claims.applied_event_ledger_snapshot_digest,
            expected.applied_event_ledger_snapshot_digest,
        ),
        "PLAYER_KNOWLEDGE_PROJECTION_ID": (
            claims.player_knowledge_projection_id,
            expected.player_knowledge_projection_id,
        ),
        "OBSERVER_BRANCH_ID": (claims.observer_branch_id, expected.observer_branch_id),
        "PLAYER_KNOWLEDGE_PROJECTION_REVISION": (
            claims.player_knowledge_projection_revision,
            expected.player_knowledge_projection_revision,
        ),
        "PLAYER_KNOWLEDGE_PROJECTION_DIGEST": (
            claims.player_knowledge_projection_digest,
            expected.player_knowledge_projection_digest,
        ),
        "LEAK_GATE_RECEIPT_ID": (claims.leak_gate_receipt_id, expected.leak_gate_receipt_id),
        "LEAK_GATE_RECEIPT_DIGEST": (
            claims.leak_gate_receipt_digest,
            expected.leak_gate_receipt_digest,
        ),
        "PLAYER_SAFE_BUNDLE_DIGEST": (
            claims.player_safe_bundle_digest,
            expected.player_safe_bundle_digest,
        ),
        "DISPLAY_LEDGER_OWNER_ID": (
            claims.display_ledger_owner_id,
            expected.display_ledger_owner_id,
        ),
        "DISPLAY_LEDGER_BACKING_STORE_ID": (
            claims.display_ledger_backing_store_id,
            expected.display_ledger_backing_store_id,
        ),
        "DISPLAY_LEDGER_BACKING_NAMESPACE": (
            claims.display_ledger_backing_namespace,
            expected.display_ledger_backing_namespace,
        ),
    }
    for name, (actual, required) in checks.items():
        _require_text(actual, name)
        _require_text(required, f"EXPECTED_{name}")
        if actual != required:
            raise PermissionError(f"AUTHORITY_GRANT_{name}_MISMATCH")


__all__ = [
    "AUTHORITY_GRANT_SCHEMA",
    "DEFAULT_MAX_TTL_SECONDS",
    "AuthorityGrantClaims",
    "AuthorityGrantEnvelope",
    "GrantBindingExpectation",
    "canonical_grant_payload",
    "validate_grant_claims",
]
