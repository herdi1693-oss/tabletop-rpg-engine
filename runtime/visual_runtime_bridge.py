#!/usr/bin/env python3
"""Runtime v1.3.8 candidate bridge into Live Visual Activation.

Authority is no longer rooted in an in-process Python registration/capability
registry. The trusted Runtime Host must present a broker-issued authority grant
and verify it against the Runtime Host verification root that was pinned once by
trusted bootstrap before untrusted request handling begins.

The visual/request worker never registers owners, chooses verification keys,
passes verifier objects, or mints/signs grants. Process/bootstrap isolation +
broker signature provenance are the security boundary; Python privacy is not.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from runtime.authority_grant_protocol import (
    AuthorityGrantEnvelope,
    GrantBindingExpectation,
)
from runtime.authority_grant_verifier import (
    runtime_host_verification_root_id,
    verify_with_runtime_host_root,
)
from runtime.runtime_host_request_context import (
    RuntimeHostRequestContext,
    consume_runtime_host_request_context,
    runtime_host_request_context_proof_digest,
    verify_runtime_host_request_context,
)
from runtime.visual_display_ledger_sqlite import SQLiteDisplayLedgerOwner
from tools.visual import live_visual_activation_guard as live
from tools.visual.scene_continuity_guard import canonical_digest

__all__ = [
    "RuntimeCheckpointOwnerSnapshot",
    "AppliedEventLedgerOwnerSnapshot",
    "PlayerSafeProofOwnerSnapshot",
    "RuntimeAuthorityBindings",
    "RuntimeVisualContext",
    "RuntimeVisualResult",
    "capture_checkpoint_owner_snapshot",
    "capture_applied_event_ledger_snapshot",
    "capture_player_safe_proof_snapshot",
    "materialize_runtime_authority_bindings",
    "materialize_runtime_visual_context",
    "RuntimeVisualBridge",
]

_REQUIRED_CHECKPOINT_FIELDS = {
    "RECEIPT_ID",
    "RECEIPT_STATUS",
    "PROOF_AUTHORITY",
    "CHECKPOINT_OWNER_ID",
    "ATOMIC_COMMIT_STATUS",
    "CHECKPOINT_BARRIER_STATUS",
    "EVENT_ID",
    "CHECKPOINT_EVENT_ID",
    "LOGICAL_REVISION",
    "CHECKPOINT_LOGICAL_REVISION",
    "APPLIED_EVENT_LEDGER_OWNER_ID",
    "APPLIED_EVENT_LEDGER_DIGEST",
    "PLAYER_SAFE_PROOF_OWNER_ID",
    "PLAYER_KNOWLEDGE_PROJECTION_ID",
    "PLAYER_KNOWLEDGE_PROJECTION_STATUS",
    "PLAYER_KNOWLEDGE_PROJECTION_DIGEST",
    "OBSERVER_BRANCH_ID",
    "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID",
    "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_DIGEST",
    "PLAYER_SAFE_PROOF_BUNDLE_DIGEST",
    "DISPLAY_LEDGER_OWNER_ID",
    "DISPLAY_LEDGER_BACKING_STORE_ID",
    "DISPLAY_LEDGER_BACKING_NAMESPACE",
    "RECEIPT_DIGEST",
}

_BASELINE_SCENE_PROOF_REGISTRIES = {
    "PKP_RECEIPTS",
    "LEAK_GATE_RECEIPTS",
    "EVS_RECEIPTS",
    "PLAYER_SAFE_SOURCE_RECEIPTS",
    "APPLIED_EVENT_LEDGER_RECEIPTS",
}
_RENDER_SCENE_PROOF_REGISTRIES = {
    "VIL_RECEIPTS",
    "ENTITY_RENDER_RECEIPTS",
    "FACT_RENDER_RECEIPTS",
    "PLAYER_SAFE_RENDER_RECEIPTS",
}


@dataclass(frozen=True)
class RuntimeCheckpointOwnerSnapshot:
    authority_instance_id: str
    source_revision: str
    records: Mapping[str, Mapping[str, object]]
    digest: str


@dataclass(frozen=True)
class AppliedEventLedgerOwnerSnapshot:
    authority_instance_id: str
    source_revision: str
    event_ids: tuple[str, ...]
    digest: str


@dataclass(frozen=True)
class PlayerSafeProofOwnerSnapshot:
    authority_instance_id: str
    source_revision: str
    projection_id: str
    observer_branch_id: str
    projection_digest: str
    leak_receipt_id: str
    leak_receipt_digest: str
    scene_proofs: Mapping[str, object]
    scene_proofs_digest: str
    digest: str


@dataclass(frozen=True)
class RuntimeAuthorityBindings:
    grant_envelope: AuthorityGrantEnvelope
    host_request_context: RuntimeHostRequestContext
    request_id: str
    session_id: str
    checkpoint_receipt_id: str
    checkpoint_owner: object
    applied_event_ledger_owner: object
    player_safe_proof_owner: object
    display_ledger_owner: SQLiteDisplayLedgerOwner
    player_safe_request: Mapping[str, object]
    source_revision: str
    checkpoint_owner_id: str
    applied_event_ledger_owner_id: str
    player_safe_proof_owner_id: str
    display_ledger_owner_id: str
    display_ledger_backing_store_id: str
    display_ledger_backing_namespace: str
    authority_grant_id: str
    verification_root_id: str
    digest: str


@dataclass(frozen=True)
class RuntimeVisualContext:
    checkpoint_receipt_id: str
    authority_grant_id: str
    authority_binding_digest: str
    checkpoint_snapshot_digest: str
    applied_event_ledger_snapshot_digest: str
    player_safe_snapshot_digest: str
    player_safe_request: Mapping[str, object]
    scene_proofs: Mapping[str, object]
    decoration_brief_receipts: Mapping[str, Mapping[str, object]]
    source_revision: str
    expected_display_ledger_owner_id: str
    expected_display_ledger_backing_store_id: str
    expected_display_ledger_backing_namespace: str
    context_digest: str


@dataclass(frozen=True)
class RuntimeVisualResult:
    status: str
    findings: tuple[str, ...]
    packet: Mapping[str, object] | None = None
    display_receipt: Mapping[str, object] | None = None

    @property
    def passed(self) -> bool:
        return self.status in {"GENERATION_READY", "DISPLAY_PASS"}


def _plain(value):
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _receipt_digest(record: Mapping[str, object]) -> str:
    body = dict(record)
    body.pop("RECEIPT_DIGEST", None)
    return canonical_digest(_plain(body))


def _owner_identity(owner: object, expected_authority: str) -> str:
    if isinstance(owner, Mapping):
        raise TypeError(f"{expected_authority}_OWNER_OBJECT_REQUIRED")
    if getattr(owner, "authority", None) != expected_authority:
        raise TypeError(f"{expected_authority}_OWNER_AUTHORITY_REQUIRED")
    owner_id = getattr(owner, "authority_instance_id", None)
    if not isinstance(owner_id, str) or not owner_id:
        raise TypeError(f"{expected_authority}_OWNER_ID_REQUIRED")
    if not callable(getattr(owner, "snapshot", None)):
        raise TypeError(f"{expected_authority}_SNAPSHOT_METHOD_REQUIRED")
    return owner_id


def capture_checkpoint_owner_snapshot(owner: object, source_revision: str) -> RuntimeCheckpointOwnerSnapshot:
    owner_id = _owner_identity(owner, "RUNTIME_CHECKPOINT_OWNER")
    raw = owner.snapshot(str(source_revision))
    if not isinstance(raw, Mapping):
        raise TypeError("RUNTIME_CHECKPOINT_OWNER_SNAPSHOT_REQUIRED")
    if str(raw.get("SOURCE_REVISION")) != str(source_revision):
        raise ValueError("RUNTIME_CHECKPOINT_OWNER_REVISION_MISMATCH")
    records = raw.get("RECORDS")
    if not isinstance(records, Mapping):
        raise TypeError("RUNTIME_CHECKPOINT_OWNER_RECORDS_REQUIRED")
    frozen: dict[str, Mapping[str, object]] = {}
    for key, value in records.items():
        if not isinstance(value, Mapping):
            raise TypeError("RUNTIME_CHECKPOINT_RECEIPT_INVALID")
        record = copy.deepcopy(dict(value))
        if record.get("CHECKPOINT_OWNER_ID") != owner_id:
            raise ValueError(f"RUNTIME_CHECKPOINT_OWNER_ID_MISMATCH:{key}")
        if record.get("RECEIPT_DIGEST") != _receipt_digest(record):
            raise ValueError(f"RUNTIME_CHECKPOINT_RECEIPT_DIGEST_MISMATCH:{key}")
        frozen[str(key)] = MappingProxyType(record)
    wrapped = MappingProxyType(frozen)
    digest = canonical_digest(
        {
            "AUTHORITY_INSTANCE_ID": owner_id,
            "SOURCE_REVISION": str(source_revision),
            "RECORDS": _plain(wrapped),
        }
    )
    return RuntimeCheckpointOwnerSnapshot(owner_id, str(source_revision), wrapped, digest)


def capture_applied_event_ledger_snapshot(owner: object, source_revision: str) -> AppliedEventLedgerOwnerSnapshot:
    owner_id = _owner_identity(owner, "APPLIED_EVENT_LEDGER_OWNER")
    raw = owner.snapshot(str(source_revision))
    if not isinstance(raw, Mapping):
        raise TypeError("APPLIED_EVENT_LEDGER_OWNER_SNAPSHOT_REQUIRED")
    if str(raw.get("SOURCE_REVISION")) != str(source_revision):
        raise ValueError("APPLIED_EVENT_LEDGER_OWNER_REVISION_MISMATCH")
    event_ids = raw.get("EVENT_IDS")
    if not isinstance(event_ids, (list, tuple)) or not all(
        isinstance(item, str) and item for item in event_ids
    ):
        raise TypeError("APPLIED_EVENT_LEDGER_EVENT_IDS_REQUIRED")
    ordered = tuple(event_ids)
    if len(ordered) != len(set(ordered)):
        raise ValueError("APPLIED_EVENT_LEDGER_DUPLICATE_EVENT_ID")
    digest = canonical_digest(
        {
            "AUTHORITY_INSTANCE_ID": owner_id,
            "SOURCE_REVISION": str(source_revision),
            "EVENT_IDS": list(ordered),
        }
    )
    return AppliedEventLedgerOwnerSnapshot(owner_id, str(source_revision), ordered, digest)


def capture_player_safe_proof_snapshot(
    owner: object,
    player_safe_request: Mapping[str, object],
    source_revision: str,
) -> PlayerSafeProofOwnerSnapshot:
    owner_id = _owner_identity(owner, "PLAYER_SAFE_PROOF_OWNER")
    projection_id = str(player_safe_request.get("PLAYER_KNOWLEDGE_PROJECTION_ID") or "")
    observer_branch_id = str(player_safe_request.get("OBSERVER_BRANCH_ID") or "")
    leak_receipt_id = str(
        player_safe_request.get("KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID") or ""
    )
    if not projection_id or not observer_branch_id or not leak_receipt_id:
        raise ValueError("RUNTIME_PLAYER_SAFE_REQUEST_AUTHORITY_BINDINGS_REQUIRED")
    raw = owner.snapshot(projection_id, observer_branch_id, str(source_revision))
    if not isinstance(raw, Mapping):
        raise TypeError("PLAYER_SAFE_PROOF_OWNER_SNAPSHOT_REQUIRED")
    if str(raw.get("SOURCE_REVISION")) != str(source_revision):
        raise ValueError("PLAYER_SAFE_PROOF_OWNER_REVISION_MISMATCH")
    if raw.get("PROJECTION_ID") != projection_id:
        raise ValueError("PLAYER_SAFE_PROJECTION_ID_MISMATCH")
    if raw.get("OBSERVER_BRANCH_ID") != observer_branch_id:
        raise ValueError("PLAYER_SAFE_OBSERVER_BRANCH_MISMATCH")
    scene_proofs = raw.get("SCENE_PROOFS")
    if not isinstance(scene_proofs, Mapping):
        raise TypeError("PLAYER_SAFE_SCENE_PROOFS_REQUIRED")
    frozen_scene = MappingProxyType(copy.deepcopy(dict(scene_proofs)))
    pkp_registry = frozen_scene.get("PKP_RECEIPTS")
    leak_registry = frozen_scene.get("LEAK_GATE_RECEIPTS")
    if not isinstance(pkp_registry, Mapping) or not isinstance(
        pkp_registry.get(projection_id), Mapping
    ):
        raise ValueError("PLAYER_SAFE_PKP_RECEIPT_REQUIRED")
    if not isinstance(leak_registry, Mapping) or not isinstance(
        leak_registry.get(leak_receipt_id), Mapping
    ):
        raise ValueError("PLAYER_SAFE_LEAK_GATE_RECEIPT_REQUIRED")
    projection_digest = canonical_digest(_plain(pkp_registry[projection_id]))
    leak_digest = canonical_digest(_plain(leak_registry[leak_receipt_id]))
    scene_digest = canonical_digest(_plain(frozen_scene))
    digest = canonical_digest(
        {
            "AUTHORITY_INSTANCE_ID": owner_id,
            "SOURCE_REVISION": str(source_revision),
            "PROJECTION_ID": projection_id,
            "OBSERVER_BRANCH_ID": observer_branch_id,
            "PROJECTION_DIGEST": projection_digest,
            "LEAK_RECEIPT_ID": leak_receipt_id,
            "LEAK_RECEIPT_DIGEST": leak_digest,
            "SCENE_PROOFS_DIGEST": scene_digest,
        }
    )
    return PlayerSafeProofOwnerSnapshot(
        owner_id,
        str(source_revision),
        projection_id,
        observer_branch_id,
        projection_digest,
        leak_receipt_id,
        leak_receipt_digest=leak_digest,
        scene_proofs=frozen_scene,
        scene_proofs_digest=scene_digest,
        digest=digest,
    )


def _grant_expectation(
    *,
    request_id: str,
    session_id: str,
    checkpoint_receipt_id: str,
    request: Mapping[str, object],
    source_revision: str,
    checkpoint_snapshot: RuntimeCheckpointOwnerSnapshot,
    ael_snapshot: AppliedEventLedgerOwnerSnapshot,
    player_safe_snapshot: PlayerSafeProofOwnerSnapshot,
    display_ledger_owner: SQLiteDisplayLedgerOwner,
) -> GrantBindingExpectation:
    receipt = checkpoint_snapshot.records.get(str(checkpoint_receipt_id))
    if not isinstance(receipt, Mapping):
        raise ValueError(f"RUNTIME_CHECKPOINT_RECEIPT_NOT_FOUND:{checkpoint_receipt_id}")
    checkpoint_digest = str(receipt.get("RECEIPT_DIGEST") or "")
    event_id = str(receipt.get("EVENT_ID") or "")
    if not checkpoint_digest or not event_id:
        raise ValueError("RUNTIME_CHECKPOINT_GRANT_BINDING_FIELDS_REQUIRED")
    if type(request_id) is not str or not request_id:
        raise ValueError("RUNTIME_HOST_REQUEST_ID_REQUIRED")
    activation_id = str(request.get("ACTIVATION_ID") or "")
    if not activation_id:
        raise ValueError("RUNTIME_VISUAL_ACTIVATION_ID_REQUIRED")
    return GrantBindingExpectation(
        request_id=request_id,
        session_id=session_id,
        activation_id=activation_id,
        source_revision=source_revision,
        checkpoint_receipt_id=str(checkpoint_receipt_id),
        checkpoint_digest=checkpoint_digest,
        event_id=event_id,
        applied_event_ledger_owner_id=ael_snapshot.authority_instance_id,
        applied_event_ledger_snapshot_digest=ael_snapshot.digest,
        player_knowledge_projection_id=player_safe_snapshot.projection_id,
        observer_branch_id=player_safe_snapshot.observer_branch_id,
        player_knowledge_projection_revision=source_revision,
        player_knowledge_projection_digest=player_safe_snapshot.projection_digest,
        leak_gate_receipt_id=player_safe_snapshot.leak_receipt_id,
        leak_gate_receipt_digest=player_safe_snapshot.leak_receipt_digest,
        player_safe_bundle_digest=player_safe_snapshot.scene_proofs_digest,
        display_ledger_owner_id=display_ledger_owner.authority_instance_id,
        display_ledger_backing_store_id=display_ledger_owner.backing_store_id,
        display_ledger_backing_namespace=display_ledger_owner.backing_namespace,
    )


def _binding_body(bindings: RuntimeAuthorityBindings) -> Mapping[str, object]:
    claims = bindings.grant_envelope.claims
    return {
        "AUTHORITY_GRANT_ID": bindings.authority_grant_id,
        "AUTHORITY_GRANT_KEY_ID": claims.key_id,
        "AUTHORITY_GRANT_NONCE": claims.nonce,
        "REQUEST_ID": bindings.request_id,
        "HOST_REQUEST_CONTEXT_AUTHORITY_ID": bindings.host_request_context.authority_id,
        "HOST_REQUEST_CONTEXT_PROOF_DIGEST": runtime_host_request_context_proof_digest(
            bindings.host_request_context
        ),
        "VERIFICATION_ROOT_ID": bindings.verification_root_id,
        "SESSION_ID": bindings.session_id,
        "CHECKPOINT_RECEIPT_ID": bindings.checkpoint_receipt_id,
        "SOURCE_REVISION": bindings.source_revision,
        "CHECKPOINT_OWNER_ID": bindings.checkpoint_owner_id,
        "APPLIED_EVENT_LEDGER_OWNER_ID": bindings.applied_event_ledger_owner_id,
        "PLAYER_SAFE_PROOF_OWNER_ID": bindings.player_safe_proof_owner_id,
        "DISPLAY_LEDGER_OWNER_ID": bindings.display_ledger_owner_id,
        "DISPLAY_LEDGER_BACKING_STORE_ID": bindings.display_ledger_backing_store_id,
        "DISPLAY_LEDGER_BACKING_NAMESPACE": bindings.display_ledger_backing_namespace,
    }


def _verify_bindings(bindings: object, *, now_unix: int | None = None) -> RuntimeAuthorityBindings:
    if not isinstance(bindings, RuntimeAuthorityBindings):
        raise TypeError("RUNTIME_AUTHORITY_BINDINGS_REQUIRED")
    if not isinstance(bindings.grant_envelope, AuthorityGrantEnvelope):
        raise TypeError("RUNTIME_AUTHORITY_GRANT_ENVELOPE_REQUIRED")
    verify_runtime_host_request_context(
        bindings.host_request_context,
        expected_request_id=bindings.request_id,
        expected_session_id=bindings.session_id,
        expected_activation_id=bindings.grant_envelope.claims.activation_id,
        expected_source_revision=bindings.source_revision,
        require_active=False,
    )
    if type(bindings.request_id) is not str or not bindings.request_id:
        raise ValueError("RUNTIME_HOST_REQUEST_ID_REQUIRED")
    if not isinstance(bindings.display_ledger_owner, SQLiteDisplayLedgerOwner):
        raise TypeError("SQLITE_DISPLAY_LEDGER_OWNER_REQUIRED")
    if bindings.verification_root_id != runtime_host_verification_root_id():
        raise PermissionError("RUNTIME_HOST_VERIFICATION_ROOT_BINDING_MISMATCH")
    if bindings.digest != canonical_digest(_plain(_binding_body(bindings))):
        raise PermissionError("RUNTIME_AUTHORITY_BINDING_DIGEST_MISMATCH")

    revision = bindings.source_revision
    checkpoint_snapshot = capture_checkpoint_owner_snapshot(bindings.checkpoint_owner, revision)
    ael_snapshot = capture_applied_event_ledger_snapshot(
        bindings.applied_event_ledger_owner, revision
    )
    player_safe_snapshot = capture_player_safe_proof_snapshot(
        bindings.player_safe_proof_owner,
        bindings.player_safe_request,
        revision,
    )
    if checkpoint_snapshot.authority_instance_id != bindings.checkpoint_owner_id:
        raise PermissionError("RUNTIME_CHECKPOINT_OWNER_ID_DRIFT")
    if ael_snapshot.authority_instance_id != bindings.applied_event_ledger_owner_id:
        raise PermissionError("RUNTIME_AEL_OWNER_ID_DRIFT")
    if player_safe_snapshot.authority_instance_id != bindings.player_safe_proof_owner_id:
        raise PermissionError("RUNTIME_PLAYER_SAFE_OWNER_ID_DRIFT")
    if bindings.display_ledger_owner.authority_instance_id != bindings.display_ledger_owner_id:
        raise PermissionError("RUNTIME_DISPLAY_LEDGER_OWNER_ID_DRIFT")
    if bindings.display_ledger_owner.backing_store_id != bindings.display_ledger_backing_store_id:
        raise PermissionError("RUNTIME_DISPLAY_LEDGER_STORE_DRIFT")
    if bindings.display_ledger_owner.backing_namespace != bindings.display_ledger_backing_namespace:
        raise PermissionError("RUNTIME_DISPLAY_LEDGER_NAMESPACE_DRIFT")

    expected = _grant_expectation(
        request_id=bindings.request_id,
        session_id=bindings.session_id,
        checkpoint_receipt_id=bindings.checkpoint_receipt_id,
        request=bindings.player_safe_request,
        source_revision=revision,
        checkpoint_snapshot=checkpoint_snapshot,
        ael_snapshot=ael_snapshot,
        player_safe_snapshot=player_safe_snapshot,
        display_ledger_owner=bindings.display_ledger_owner,
    )
    verify_with_runtime_host_root(
        bindings.grant_envelope,
        expected,
        now_unix=int(time.time()) if now_unix is None else int(now_unix),
    )
    return bindings


def materialize_runtime_authority_bindings(
    grant_envelope: AuthorityGrantEnvelope,
    host_request_context: RuntimeHostRequestContext,
    session_id: str,
    checkpoint_receipt_id: str,
    checkpoint_owner: object,
    applied_event_ledger_owner: object,
    player_safe_proof_owner: object,
    display_ledger_owner: SQLiteDisplayLedgerOwner,
    source_revision: str,
    player_safe_request: Mapping[str, object],
    *,
    now_unix: int | None = None,
) -> RuntimeAuthorityBindings:
    """Materialize host bindings from a Host-owned request transaction context.

    ``host_request_context`` is minted by the trusted Runtime Host from a
    supervisor-inherited HMAC authority and must still be ACTIVE.  A raw or
    caller-selected REQUEST_ID is not accepted.  The same Host-owned identity is
    required to have been sent to the Authority Broker and is matched exactly to
    the signed grant before the context is consumed.

    No verifier, keyring, public key, key path, SQL row, caller-selected request
    ID, or caller-selected verification configuration is accepted by this API.
    """

    if not isinstance(grant_envelope, AuthorityGrantEnvelope):
        raise TypeError("RUNTIME_AUTHORITY_GRANT_ENVELOPE_REQUIRED")
    if not isinstance(host_request_context, RuntimeHostRequestContext):
        raise TypeError("RUNTIME_HOST_REQUEST_CONTEXT_REQUIRED")
    if type(session_id) is not str or not session_id:
        raise ValueError("RUNTIME_SESSION_ID_REQUIRED")
    revision = str(source_revision or "")
    if not revision:
        raise ValueError("RUNTIME_AUTHORITY_SOURCE_REVISION_REQUIRED")
    if not isinstance(player_safe_request, Mapping):
        raise TypeError("PLAYER_SAFE_REQUEST_REQUIRED")
    if not isinstance(display_ledger_owner, SQLiteDisplayLedgerOwner):
        raise TypeError("SQLITE_DISPLAY_LEDGER_OWNER_REQUIRED")

    root_id = runtime_host_verification_root_id()
    request = MappingProxyType(copy.deepcopy(dict(player_safe_request)))
    activation_id = str(request.get("ACTIVATION_ID") or "")
    if not activation_id:
        raise ValueError("RUNTIME_VISUAL_ACTIVATION_ID_REQUIRED")
    host_context = verify_runtime_host_request_context(
        host_request_context,
        expected_session_id=session_id,
        expected_activation_id=activation_id,
        expected_source_revision=revision,
        require_active=True,
    )
    checkpoint_snapshot = capture_checkpoint_owner_snapshot(checkpoint_owner, revision)
    ael_snapshot = capture_applied_event_ledger_snapshot(applied_event_ledger_owner, revision)
    player_safe_snapshot = capture_player_safe_proof_snapshot(
        player_safe_proof_owner, request, revision
    )
    expected = _grant_expectation(
        request_id=host_context.request_id,
        session_id=session_id,
        checkpoint_receipt_id=str(checkpoint_receipt_id),
        request=request,
        source_revision=revision,
        checkpoint_snapshot=checkpoint_snapshot,
        ael_snapshot=ael_snapshot,
        player_safe_snapshot=player_safe_snapshot,
        display_ledger_owner=display_ledger_owner,
    )
    verify_with_runtime_host_root(
        grant_envelope,
        expected,
        now_unix=int(time.time()) if now_unix is None else int(now_unix),
    )

    bindings = RuntimeAuthorityBindings(
        grant_envelope=grant_envelope,
        host_request_context=host_context,
        request_id=host_context.request_id,
        session_id=session_id,
        checkpoint_receipt_id=str(checkpoint_receipt_id),
        checkpoint_owner=checkpoint_owner,
        applied_event_ledger_owner=applied_event_ledger_owner,
        player_safe_proof_owner=player_safe_proof_owner,
        display_ledger_owner=display_ledger_owner,
        player_safe_request=request,
        source_revision=revision,
        checkpoint_owner_id=checkpoint_snapshot.authority_instance_id,
        applied_event_ledger_owner_id=ael_snapshot.authority_instance_id,
        player_safe_proof_owner_id=player_safe_snapshot.authority_instance_id,
        display_ledger_owner_id=display_ledger_owner.authority_instance_id,
        display_ledger_backing_store_id=display_ledger_owner.backing_store_id,
        display_ledger_backing_namespace=display_ledger_owner.backing_namespace,
        authority_grant_id=grant_envelope.claims.grant_id,
        verification_root_id=root_id,
        digest="",
    )
    object.__setattr__(bindings, "digest", canonical_digest(_plain(_binding_body(bindings))))

    receipt, findings = _checkpoint_findings(
        str(checkpoint_receipt_id),
        bindings,
        request,
        checkpoint_snapshot,
        ael_snapshot,
        player_safe_snapshot,
    )
    if receipt is None or findings:
        raise ValueError(";".join(findings or ["RUNTIME_CHECKPOINT_RECEIPT_REQUIRED"]))
    consume_runtime_host_request_context(host_context)
    return bindings


def _checkpoint_findings(
    checkpoint_receipt_id: str,
    bindings: RuntimeAuthorityBindings,
    request: Mapping[str, object],
    checkpoint_snapshot: RuntimeCheckpointOwnerSnapshot,
    ael_snapshot: AppliedEventLedgerOwnerSnapshot,
    player_safe_snapshot: PlayerSafeProofOwnerSnapshot,
) -> tuple[Mapping[str, object] | None, list[str]]:
    findings: list[str] = []
    receipt = checkpoint_snapshot.records.get(str(checkpoint_receipt_id))
    if not isinstance(receipt, Mapping):
        return None, [f"RUNTIME_CHECKPOINT_RECEIPT_NOT_FOUND:{checkpoint_receipt_id}"]
    for field in sorted(_REQUIRED_CHECKPOINT_FIELDS - set(receipt)):
        findings.append(f"RUNTIME_CHECKPOINT_MISSING_FIELD:{field}")
    if findings:
        return receipt, findings
    if receipt.get("RECEIPT_DIGEST") != _receipt_digest(receipt):
        findings.append("RUNTIME_CHECKPOINT_RECEIPT_DIGEST_MISMATCH")
    if receipt.get("RECEIPT_STATUS") != "PASS":
        findings.append("RUNTIME_CHECKPOINT_RECEIPT_NOT_PASS")
    if receipt.get("PROOF_AUTHORITY") != "RUNTIME_CHECKPOINT_BARRIER":
        findings.append("RUNTIME_CHECKPOINT_PROOF_AUTHORITY_INVALID")
    if receipt.get("CHECKPOINT_OWNER_ID") != bindings.checkpoint_owner_id:
        findings.append("RUNTIME_CHECKPOINT_OWNER_BINDING_MISMATCH")
    if receipt.get("ATOMIC_COMMIT_STATUS") != "COMMITTED":
        findings.append("RUNTIME_ATOMIC_COMMIT_REQUIRED")
    if receipt.get("CHECKPOINT_BARRIER_STATUS") != "PASS":
        findings.append("RUNTIME_CHECKPOINT_BARRIER_PASS_REQUIRED")
    if receipt.get("CHECKPOINT_EVENT_ID") != receipt.get("EVENT_ID"):
        findings.append("RUNTIME_CHECKPOINT_EVENT_BINDING_MISMATCH")
    if receipt.get("CHECKPOINT_LOGICAL_REVISION") != receipt.get("LOGICAL_REVISION"):
        findings.append("RUNTIME_CHECKPOINT_REVISION_MISMATCH")
    if str(receipt.get("LOGICAL_REVISION")) != bindings.source_revision:
        findings.append("RUNTIME_AUTHORITY_REVISION_MISMATCH")

    if receipt.get("APPLIED_EVENT_LEDGER_OWNER_ID") != ael_snapshot.authority_instance_id:
        findings.append("RUNTIME_APPLIED_EVENT_LEDGER_OWNER_BINDING_MISMATCH")
    if receipt.get("APPLIED_EVENT_LEDGER_DIGEST") != ael_snapshot.digest:
        findings.append("RUNTIME_APPLIED_EVENT_LEDGER_DIGEST_MISMATCH")
    if receipt.get("EVENT_ID") not in ael_snapshot.event_ids:
        findings.append("RUNTIME_EVENT_NOT_IN_APPLIED_EVENT_LEDGER")

    if receipt.get("PLAYER_SAFE_PROOF_OWNER_ID") != player_safe_snapshot.authority_instance_id:
        findings.append("RUNTIME_PLAYER_SAFE_OWNER_BINDING_MISMATCH")
    if receipt.get("PLAYER_KNOWLEDGE_PROJECTION_DIGEST") != player_safe_snapshot.projection_digest:
        findings.append("RUNTIME_PLAYER_SAFE_PROJECTION_DIGEST_MISMATCH")
    if (
        receipt.get("KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_DIGEST")
        != player_safe_snapshot.leak_receipt_digest
    ):
        findings.append("RUNTIME_PLAYER_SAFE_LEAK_RECEIPT_DIGEST_MISMATCH")
    if receipt.get("PLAYER_SAFE_PROOF_BUNDLE_DIGEST") != player_safe_snapshot.scene_proofs_digest:
        findings.append("RUNTIME_PLAYER_SAFE_PROOF_BUNDLE_DIGEST_MISMATCH")

    if receipt.get("DISPLAY_LEDGER_OWNER_ID") != bindings.display_ledger_owner_id:
        findings.append("RUNTIME_DISPLAY_LEDGER_OWNER_BINDING_MISMATCH")
    if receipt.get("DISPLAY_LEDGER_BACKING_STORE_ID") != bindings.display_ledger_backing_store_id:
        findings.append("RUNTIME_DISPLAY_LEDGER_BACKING_STORE_BINDING_MISMATCH")
    if receipt.get("DISPLAY_LEDGER_BACKING_NAMESPACE") != bindings.display_ledger_backing_namespace:
        findings.append("RUNTIME_DISPLAY_LEDGER_BACKING_NAMESPACE_BINDING_MISMATCH")

    request_bindings = {
        "SOURCE_STATE_EPOCH": receipt.get("LOGICAL_REVISION"),
        "PLAYER_KNOWLEDGE_PROJECTION_ID": receipt.get("PLAYER_KNOWLEDGE_PROJECTION_ID"),
        "OBSERVER_BRANCH_ID": receipt.get("OBSERVER_BRANCH_ID"),
        "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID": receipt.get(
            "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID"
        ),
    }
    for key, expected in request_bindings.items():
        if request.get(key) != expected:
            findings.append(f"RUNTIME_VISUAL_REQUEST_{key}_BINDING_MISMATCH")
    if receipt.get("PLAYER_KNOWLEDGE_PROJECTION_STATUS") != "MATERIALIZED":
        findings.append("RUNTIME_PLAYER_PROJECTION_MATERIALIZED_REQUIRED")
    if request.get("PLAYER_KNOWLEDGE_PROJECTION_STATUS") != "MATERIALIZED":
        findings.append("RUNTIME_VISUAL_REQUEST_PKP_MATERIALIZED_REQUIRED")
    if request.get("SOURCE_KIND") != "COMMITTED_GAME_STATE":
        findings.append("RUNTIME_VISUAL_REQUEST_SOURCE_KIND_INVALID")
    return receipt, findings


def _context_body(
    checkpoint_receipt_id: str,
    authority_grant_id: str,
    authority_binding_digest: str,
    checkpoint_snapshot_digest: str,
    ael_snapshot_digest: str,
    player_safe_snapshot_digest: str,
    request: Mapping[str, object],
    scene_proofs: Mapping[str, object],
    decoration_brief_receipts: Mapping[str, Mapping[str, object]],
    source_revision: str,
    display_owner_id: str,
    display_backing_store_id: str,
    display_backing_namespace: str,
):
    return {
        "CHECKPOINT_RECEIPT_ID": checkpoint_receipt_id,
        "AUTHORITY_GRANT_ID": authority_grant_id,
        "AUTHORITY_BINDING_DIGEST": authority_binding_digest,
        "CHECKPOINT_SNAPSHOT_DIGEST": checkpoint_snapshot_digest,
        "APPLIED_EVENT_LEDGER_SNAPSHOT_DIGEST": ael_snapshot_digest,
        "PLAYER_SAFE_SNAPSHOT_DIGEST": player_safe_snapshot_digest,
        "PLAYER_SAFE_REQUEST_DIGEST": canonical_digest(_plain(request)),
        "SCENE_PROOFS_DIGEST": canonical_digest(_plain(scene_proofs)),
        "DECORATION_RECEIPTS_DIGEST": canonical_digest(_plain(decoration_brief_receipts)),
        "SOURCE_REVISION": source_revision,
        "DISPLAY_LEDGER_OWNER_ID": display_owner_id,
        "DISPLAY_LEDGER_BACKING_STORE_ID": display_backing_store_id,
        "DISPLAY_LEDGER_BACKING_NAMESPACE": display_backing_namespace,
    }


def materialize_runtime_visual_context(
    checkpoint_receipt_id: str,
    authority_bindings: RuntimeAuthorityBindings,
    player_safe_request: Mapping[str, object],
    decoration_brief_receipts: Mapping[str, Mapping[str, object]],
) -> RuntimeVisualContext:
    _verify_bindings(authority_bindings)
    if str(checkpoint_receipt_id) != authority_bindings.checkpoint_receipt_id:
        raise PermissionError("RUNTIME_AUTHORITY_GRANT_CHECKPOINT_RECEIPT_MISMATCH")
    if not isinstance(player_safe_request, Mapping):
        raise TypeError("PLAYER_SAFE_REQUEST_REQUIRED")
    if not isinstance(decoration_brief_receipts, Mapping):
        raise TypeError("DECORATION_RECEIPTS_REQUIRED")
    request = copy.deepcopy(dict(player_safe_request))
    decoration = copy.deepcopy(dict(decoration_brief_receipts))
    if str(request.get("SOURCE_STATE_EPOCH")) != authority_bindings.source_revision:
        raise ValueError("RUNTIME_VISUAL_REQUEST_SOURCE_REVISION_BINDING_MISMATCH")

    checkpoint_snapshot = capture_checkpoint_owner_snapshot(
        authority_bindings.checkpoint_owner, authority_bindings.source_revision
    )
    ael_snapshot = capture_applied_event_ledger_snapshot(
        authority_bindings.applied_event_ledger_owner, authority_bindings.source_revision
    )
    player_safe_snapshot = capture_player_safe_proof_snapshot(
        authority_bindings.player_safe_proof_owner,
        request,
        authority_bindings.source_revision,
    )
    expected = _grant_expectation(
        request_id=authority_bindings.request_id,
        session_id=authority_bindings.session_id,
        checkpoint_receipt_id=str(checkpoint_receipt_id),
        request=request,
        source_revision=authority_bindings.source_revision,
        checkpoint_snapshot=checkpoint_snapshot,
        ael_snapshot=ael_snapshot,
        player_safe_snapshot=player_safe_snapshot,
        display_ledger_owner=authority_bindings.display_ledger_owner,
    )
    verify_with_runtime_host_root(
        authority_bindings.grant_envelope,
        expected,
        now_unix=int(time.time()),
    )
    receipt, findings = _checkpoint_findings(
        str(checkpoint_receipt_id),
        authority_bindings,
        request,
        checkpoint_snapshot,
        ael_snapshot,
        player_safe_snapshot,
    )
    if findings:
        raise ValueError(";".join(findings))
    source_revision = str(receipt.get("LOGICAL_REVISION"))
    frozen_decoration = MappingProxyType(
        {str(k): MappingProxyType(copy.deepcopy(dict(v))) for k, v in decoration.items()}
    )
    body = _context_body(
        str(checkpoint_receipt_id),
        authority_bindings.authority_grant_id,
        authority_bindings.digest,
        checkpoint_snapshot.digest,
        ael_snapshot.digest,
        player_safe_snapshot.digest,
        request,
        player_safe_snapshot.scene_proofs,
        frozen_decoration,
        source_revision,
        authority_bindings.display_ledger_owner_id,
        authority_bindings.display_ledger_backing_store_id,
        authority_bindings.display_ledger_backing_namespace,
    )
    return RuntimeVisualContext(
        str(checkpoint_receipt_id),
        authority_bindings.authority_grant_id,
        authority_bindings.digest,
        checkpoint_snapshot.digest,
        ael_snapshot.digest,
        player_safe_snapshot.digest,
        MappingProxyType(request),
        player_safe_snapshot.scene_proofs,
        frozen_decoration,
        source_revision,
        authority_bindings.display_ledger_owner_id,
        authority_bindings.display_ledger_backing_store_id,
        authority_bindings.display_ledger_backing_namespace,
        canonical_digest(body),
    )


def _context_findings(context: object, bindings: RuntimeAuthorityBindings) -> list[str]:
    if not isinstance(context, RuntimeVisualContext):
        return ["RUNTIME_VISUAL_CONTEXT_REQUIRED"]
    findings: list[str] = []
    try:
        _verify_bindings(bindings)
    except Exception as error:
        return [f"RUNTIME_AUTHORITY_GRANT_BINDING_INVALID:{type(error).__name__}"]
    if context.authority_grant_id != bindings.authority_grant_id:
        findings.append("RUNTIME_AUTHORITY_GRANT_CONTEXT_MISMATCH")
    if context.authority_binding_digest != bindings.digest:
        findings.append("RUNTIME_AUTHORITY_BINDING_MISMATCH")
    if context.source_revision != bindings.source_revision:
        findings.append("RUNTIME_AUTHORITY_REVISION_MISMATCH")
    if context.expected_display_ledger_owner_id != bindings.display_ledger_owner_id:
        findings.append("RUNTIME_DISPLAY_LEDGER_OWNER_BINDING_MISMATCH")
    if (
        context.expected_display_ledger_backing_store_id
        != bindings.display_ledger_backing_store_id
    ):
        findings.append("RUNTIME_DISPLAY_LEDGER_BACKING_STORE_BINDING_MISMATCH")
    if (
        context.expected_display_ledger_backing_namespace
        != bindings.display_ledger_backing_namespace
    ):
        findings.append("RUNTIME_DISPLAY_LEDGER_BACKING_NAMESPACE_BINDING_MISMATCH")
    try:
        checkpoint_snapshot = capture_checkpoint_owner_snapshot(
            bindings.checkpoint_owner, context.source_revision
        )
        ael_snapshot = capture_applied_event_ledger_snapshot(
            bindings.applied_event_ledger_owner, context.source_revision
        )
        player_safe_snapshot = capture_player_safe_proof_snapshot(
            bindings.player_safe_proof_owner,
            context.player_safe_request,
            context.source_revision,
        )
        expected = _grant_expectation(
            request_id=bindings.request_id,
            session_id=bindings.session_id,
            checkpoint_receipt_id=context.checkpoint_receipt_id,
            request=context.player_safe_request,
            source_revision=context.source_revision,
            checkpoint_snapshot=checkpoint_snapshot,
            ael_snapshot=ael_snapshot,
            player_safe_snapshot=player_safe_snapshot,
            display_ledger_owner=bindings.display_ledger_owner,
        )
        verify_with_runtime_host_root(
            bindings.grant_envelope,
            expected,
            now_unix=int(time.time()),
        )
    except Exception as error:
        findings.append(f"RUNTIME_AUTHORITY_SNAPSHOT_INVALID:{type(error).__name__}")
        return findings
    if checkpoint_snapshot.digest != context.checkpoint_snapshot_digest:
        findings.append("RUNTIME_CHECKPOINT_SNAPSHOT_DRIFT")
    if ael_snapshot.digest != context.applied_event_ledger_snapshot_digest:
        findings.append("RUNTIME_APPLIED_EVENT_LEDGER_SNAPSHOT_DRIFT")
    if player_safe_snapshot.digest != context.player_safe_snapshot_digest:
        findings.append("RUNTIME_PLAYER_SAFE_SNAPSHOT_DRIFT")
    receipt, checkpoint_findings = _checkpoint_findings(
        context.checkpoint_receipt_id,
        bindings,
        context.player_safe_request,
        checkpoint_snapshot,
        ael_snapshot,
        player_safe_snapshot,
    )
    findings.extend(checkpoint_findings)
    if receipt is None:
        return findings
    if canonical_digest(_plain(player_safe_snapshot.scene_proofs)) != canonical_digest(
        _plain(context.scene_proofs)
    ):
        findings.append("RUNTIME_PLAYER_SAFE_CONTEXT_PROOF_DRIFT")
    body = _context_body(
        context.checkpoint_receipt_id,
        context.authority_grant_id,
        context.authority_binding_digest,
        context.checkpoint_snapshot_digest,
        context.applied_event_ledger_snapshot_digest,
        context.player_safe_snapshot_digest,
        context.player_safe_request,
        context.scene_proofs,
        context.decoration_brief_receipts,
        context.source_revision,
        context.expected_display_ledger_owner_id,
        context.expected_display_ledger_backing_store_id,
        context.expected_display_ledger_backing_namespace,
    )
    if context.context_digest != canonical_digest(body):
        findings.append("RUNTIME_VISUAL_CONTEXT_DIGEST_MISMATCH")
    return findings


def _render_scene_proof_findings(
    context: RuntimeVisualContext, render_scene_proofs: object
) -> list[str]:
    if not isinstance(render_scene_proofs, Mapping):
        return ["RUNTIME_RENDER_SCENE_PROOF_BUNDLE_REQUIRED"]
    findings: list[str] = []
    baseline = context.scene_proofs
    for registry_name in sorted(_BASELINE_SCENE_PROOF_REGISTRIES):
        if registry_name not in baseline:
            findings.append(f"RUNTIME_BASELINE_SCENE_PROOF_REGISTRY_MISSING:{registry_name}")
            continue
        if registry_name not in render_scene_proofs:
            findings.append(f"RUNTIME_RENDER_SCENE_PROOF_REGISTRY_MISSING:{registry_name}")
            continue
        if canonical_digest(_plain(render_scene_proofs.get(registry_name))) != canonical_digest(
            _plain(baseline.get(registry_name))
        ):
            findings.append(f"RUNTIME_RENDER_SCENE_PROOF_BASELINE_MUTATION:{registry_name}")
    for registry_name in sorted(_RENDER_SCENE_PROOF_REGISTRIES):
        if not isinstance(render_scene_proofs.get(registry_name), Mapping):
            findings.append(f"RUNTIME_RENDER_SCENE_PROOF_REGISTRY_REQUIRED:{registry_name}")
    allowed = _BASELINE_SCENE_PROOF_REGISTRIES | _RENDER_SCENE_PROOF_REGISTRIES
    extras = set(render_scene_proofs) - allowed
    for registry_name in sorted(map(str, extras)):
        findings.append(f"RUNTIME_RENDER_SCENE_PROOF_UNKNOWN_REGISTRY:{registry_name}")
    return findings


class RuntimeVisualBridge:
    """Trusted-host post-checkpoint visual side-effect bridge."""

    def __init__(self, authority_bindings: RuntimeAuthorityBindings):
        _verify_bindings(authority_bindings)
        self.authority_bindings = authority_bindings
        self.display_ledger_owner = authority_bindings.display_ledger_owner

    def prepare_generation(self, context: RuntimeVisualContext) -> RuntimeVisualResult:
        findings = _context_findings(context, self.authority_bindings)
        if findings:
            return RuntimeVisualResult("GENERATION_BLOCKED", tuple(findings))
        self.display_ledger_owner.bind_source_revision(context.source_revision)
        registry = live.materialize_activation_proof_registry(
            {},
            context.source_revision,
            context.decoration_brief_receipts,
            {},
            context.expected_display_ledger_owner_id,
        )
        try:
            result = live.build_generation_packet(
                context.player_safe_request,
                context.scene_proofs,
                registry,
            )
        except Exception as error:
            return RuntimeVisualResult(
                "GENERATION_BLOCKED",
                (f"VISUAL_PIPELINE_EXCEPTION:{type(error).__name__}",),
            )
        return RuntimeVisualResult(
            "GENERATION_READY" if result.passed else "GENERATION_BLOCKED",
            tuple(result.findings),
            result.packet,
            None,
        )

    def evaluate_render(
        self,
        context: RuntimeVisualContext,
        packet: Mapping[str, object],
        render_result: Mapping[str, object],
        identity_comparator_payload: Mapping[str, object],
        identity_proof_receipts: Mapping[str, Mapping[str, object]],
        tactical_receipts: Mapping[str, Mapping[str, object]],
        scene_post_render_receipt: Mapping[str, object],
        render_scene_proofs: Mapping[str, object],
    ) -> RuntimeVisualResult:
        findings = _context_findings(context, self.authority_bindings)
        findings.extend(_render_scene_proof_findings(context, render_scene_proofs))
        if findings:
            return RuntimeVisualResult("DISPLAY_BLOCKED", tuple(findings), packet)
        self.display_ledger_owner.bind_source_revision(context.source_revision)
        registry = live.materialize_activation_proof_registry(
            identity_proof_receipts,
            context.source_revision,
            context.decoration_brief_receipts,
            tactical_receipts,
            context.expected_display_ledger_owner_id,
        )
        try:
            result = live.evaluate_for_display(
                context.player_safe_request,
                packet,
                render_result,
                identity_comparator_payload,
                scene_post_render_receipt,
                render_scene_proofs,
                registry,
                self.display_ledger_owner,
            )
        except Exception as error:
            return RuntimeVisualResult(
                "DISPLAY_BLOCKED",
                (f"VISUAL_DURABLE_BACKING_EXCEPTION:{type(error).__name__}",),
                packet,
            )
        return RuntimeVisualResult(
            "DISPLAY_PASS" if result.passed else "DISPLAY_BLOCKED",
            tuple(result.findings),
            packet,
            result.display_receipt,
        )
