#!/usr/bin/env python3
"""Fail-closed hardening layer for Live Visual Activation v1.

Tooling-only. Composes the already validated base activation implementation
with three additional trust boundaries required by QA:
1) exact player-safe decoration-brief proof binding,
2) external tactical proof receipts, never renderer self-asserted PASS strings,
3) a mandatory external display-ledger owner that remembers successful displays
   automatically and rejects replay without caller-managed history.
"""
from __future__ import annotations

import copy
import re
import threading
import uuid
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from . import live_visual_activation_guard_base as _base
from .live_visual_activation_guard_base import *  # re-export validated base API
from .scene_continuity_guard import canonical_digest

TACTICAL_RECEIPT_SPECS = {
    "STRUCTURAL_RECEIPT_ID": ("STRUCTURAL_COMPARATOR", "STRUCTURAL_PASS"),
    "PRESENTATION_RECEIPT_ID": ("PRESENTATION_VALIDATOR", "PRESENTATION_PASS"),
    "GEOMETRY_COMPARE_RECEIPT_ID": ("GEOMETRY_COMPARATOR", "GEOMETRY_COMPARE"),
    "VISUAL_PIPELINE_RECEIPT_ID": ("VISUAL_PIPELINE", "VISUAL_PIPELINE_RECEIPT_STATUS"),
    "DETERMINISTIC_OVERLAY_RECEIPT_ID": ("DETERMINISTIC_OVERLAY_VALIDATOR", "DETERMINISTIC_OVERLAY_STATUS"),
}
SELF_ASSERTED_TACTICAL_FIELDS = {
    "STRUCTURAL_PASS", "PRESENTATION_PASS", "GEOMETRY_COMPARE",
    "VISUAL_PIPELINE_RECEIPT_STATUS", "DETERMINISTIC_OVERLAY_STATUS",
    "OVERLAY_SOURCE", "TOPOLOGY_SOURCE",
}
GEOMETRY_MISMATCH_FIELDS = (
    "TOPOLOGY_MISMATCH_COUNT", "CONNECTIVITY_MISMATCH_COUNT",
    "DOOR_STATE_MISMATCH_COUNT", "GRID_CELL_MISMATCH_COUNT",
    "CREATURE_CELL_MISMATCH_COUNT",
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class ActivationProofRegistry:
    status: str
    source_revision: str
    identity_comparator_receipts: Mapping[str, Mapping[str, object]]
    decoration_brief_receipts: Mapping[str, Mapping[str, object]]
    tactical_receipts: Mapping[str, Mapping[str, object]]
    display_ledger_owner_id: str | None
    digest: str


@dataclass(frozen=True)
class DisplayLedgerSnapshot:
    status: str
    authority: str
    source_revision: str
    ledger_id: str
    authority_instance_id: str
    records: Mapping[str, Mapping[str, object]]
    logical_index: int
    digest: str


class DisplayLedgerOwner:
    """Tooling adapter for the external durable display-ledger owner.

    Runtime promotion must replace/back this adapter with durable storage. The
    important contract here is ownership: callers do not pass an optional list
    of remembered receipts. The owner snapshots and commits display receipts
    itself, atomically rechecking replay before commit.
    """

    def __init__(self, records, source_revision, ledger_id="DISPLAY-LEDGER-V1"):
        self.status = "MATERIALIZED_OWNER"
        self.authority = "DISPLAY_LEDGER_OWNER"
        self.source_revision = str(source_revision)
        self.ledger_id = str(ledger_id)
        self.authority_instance_id = f"DLO-{uuid.uuid4()}"
        self._lock = threading.RLock()
        self._records = {
            str(key): copy.deepcopy(dict(value))
            for key, value in (records or {}).items() if isinstance(value, Mapping)
        }
        self._logical_index = max(
            [int(v.get("DISPLAY_LEDGER_LOGICAL_INDEX", 0)) for v in self._records.values()] or [0]
        )

    def snapshot(self):
        with self._lock:
            frozen = _freeze(self._records)
            body = {k: dict(v) for k, v in frozen.items()}
            return DisplayLedgerSnapshot(
                "MATERIALIZED_READ_ONLY", self.authority, self.source_revision,
                self.ledger_id, self.authority_instance_id, frozen, self._logical_index,
                canonical_digest({
                    "LEDGER_ID": self.ledger_id,
                    "AUTHORITY_INSTANCE_ID": self.authority_instance_id,
                    "LOGICAL_INDEX": self._logical_index,
                    "RECORDS": body,
                }),
            )

    def commit_if_fresh(self, display_receipt, tactical_ids):
        with self._lock:
            findings = _replay_findings(
                self.snapshot(),
                display_receipt.get("ACTIVATION_ID"),
                display_receipt.get("RENDER_ARTIFACT_ID"),
                display_receipt.get("IDENTITY_COMPARATOR_RECEIPT_ID"),
                display_receipt.get("PLAYER_SAFE_CONTENT_RECEIPT_ID"),
                tactical_ids,
            )
            if findings:
                return findings
            self._logical_index += 1
            record = copy.deepcopy(dict(display_receipt))
            record["DISPLAY_LEDGER_LOGICAL_INDEX"] = self._logical_index
            record["TACTICAL_RECEIPT_IDS"] = list(tactical_ids)
            key = str(record.get("DISPLAY_RECEIPT_ID") or f"DISPLAY-{self._logical_index}")
            self._records[key] = record
            return []


def _freeze(receipts):
    receipts = receipts or {}
    return MappingProxyType({
        str(key): MappingProxyType(copy.deepcopy(dict(value)))
        for key, value in receipts.items() if isinstance(value, Mapping)
    })


def materialize_display_ledger_owner(records, source_revision, ledger_id="DISPLAY-LEDGER-V1"):
    return DisplayLedgerOwner(records, source_revision, ledger_id)


materialize_display_ledger = materialize_display_ledger_owner


def materialize_activation_proof_registry(
    identity_comparator_receipts,
    source_revision,
    decoration_brief_receipts=None,
    tactical_receipts=None,
    display_ledger_owner_id=None,
):
    identity = _freeze(identity_comparator_receipts)
    decoration = _freeze(decoration_brief_receipts)
    tactical = _freeze(tactical_receipts)
    body = {
        "IDENTITY": {k: dict(v) for k, v in identity.items()},
        "DECORATION": {k: dict(v) for k, v in decoration.items()},
        "TACTICAL": {k: dict(v) for k, v in tactical.items()},
        "DISPLAY_LEDGER_OWNER_ID": display_ledger_owner_id,
    }
    return ActivationProofRegistry(
        "MATERIALIZED_READ_ONLY", str(source_revision), identity, decoration,
        tactical, None if display_ledger_owner_id is None else str(display_ledger_owner_id),
        canonical_digest(body),
    )


def _registry_findings(value):
    if not isinstance(value, ActivationProofRegistry):
        return None, ["ACTIVATION_PROOF_REGISTRY_REQUIRED"]
    findings = []
    if value.status != "MATERIALIZED_READ_ONLY" or not value.source_revision:
        findings.append("ACTIVATION_PROOF_REGISTRY_INVALID")
    body = {
        "IDENTITY": {k: dict(v) for k, v in value.identity_comparator_receipts.items()},
        "DECORATION": {k: dict(v) for k, v in value.decoration_brief_receipts.items()},
        "TACTICAL": {k: dict(v) for k, v in value.tactical_receipts.items()},
        "DISPLAY_LEDGER_OWNER_ID": value.display_ledger_owner_id,
    }
    if value.digest != canonical_digest(body):
        findings.append("ACTIVATION_PROOF_REGISTRY_DIGEST_MISMATCH")
    return value, findings


def _ledger_owner_findings(value, registry):
    if not isinstance(value, DisplayLedgerOwner):
        return None, ["DISPLAY_LEDGER_OWNER_REQUIRED"]
    findings = []
    if value.status != "MATERIALIZED_OWNER" or value.authority != "DISPLAY_LEDGER_OWNER":
        findings.append("DISPLAY_LEDGER_OWNER_AUTHORITY_INVALID")
    if registry is None or value.source_revision != registry.source_revision:
        findings.append("DISPLAY_LEDGER_SOURCE_REVISION_MISMATCH")
    if registry is not None:
        if not registry.display_ledger_owner_id:
            findings.append("DISPLAY_LEDGER_OWNER_BINDING_REQUIRED")
        elif registry.display_ledger_owner_id != value.authority_instance_id:
            findings.append("DISPLAY_LEDGER_OWNER_INSTANCE_MISMATCH")
    snapshot = value.snapshot()
    body = {k: dict(v) for k, v in snapshot.records.items()}
    expected = canonical_digest({
        "LEDGER_ID": snapshot.ledger_id,
        "AUTHORITY_INSTANCE_ID": snapshot.authority_instance_id,
        "LOGICAL_INDEX": snapshot.logical_index,
        "RECORDS": body,
    })
    if snapshot.status != "MATERIALIZED_READ_ONLY" or snapshot.digest != expected:
        findings.append("DISPLAY_LEDGER_SNAPSHOT_INVALID")
    return value, findings


def _decoration_findings(request, registry):
    rid = request.get("DECORATION_BRIEF_RECEIPT_ID")
    if not rid:
        return ["DECORATION_BRIEF_RECEIPT_ID_REQUIRED"]
    if registry is None:
        return ["DECORATION_BRIEF_TRUSTED_REGISTRY_REQUIRED"]
    receipt = registry.decoration_brief_receipts.get(str(rid))
    if not isinstance(receipt, Mapping):
        return [f"DECORATION_BRIEF_RECEIPT_NOT_FOUND:{rid}"]
    expected = {
        "RECEIPT_ID": rid,
        "STATUS": "PASS",
        "PROOF_AUTHORITY": "PLAYER_SAFE_DECORATION_BRIEF",
        "PLAYER_KNOWLEDGE_PROJECTION_ID": request.get("PLAYER_KNOWLEDGE_PROJECTION_ID"),
        "OBSERVER_BRANCH_ID": request.get("OBSERVER_BRANCH_ID"),
        "SOURCE_STATE_EPOCH": request.get("SOURCE_STATE_EPOCH"),
        "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID": request.get("KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID"),
        "DECORATION_BRIEF_DIGEST": canonical_digest(request.get("DECORATION_BRIEF")),
    }
    return [
        f"DECORATION_BRIEF_RECEIPT_{key}_BINDING_MISMATCH"
        for key, expected_value in expected.items()
        if receipt.get(key) != expected_value
    ]


def build_generation_packet(request, scene_proofs=None, activation_proofs=None):
    registry, findings = _registry_findings(activation_proofs)
    findings.extend(_decoration_findings(request, registry))
    base_result = _base.build_generation_packet(request, scene_proofs)
    findings.extend(base_result.findings)
    if findings or not base_result.passed:
        return ActivationResult("BLOCKED", tuple(findings), None, None)
    return ActivationResult("GENERATION_READY", (), base_result.packet, None)


def _tactical_input_digest(request, packet, render_result):
    return canonical_digest({
        "ACTIVATION_ID": request.get("ACTIVATION_ID"),
        "PACKET_DIGEST": packet.get("PACKET_DIGEST"),
        "FRAME_ID": request.get("SCENE_FRAME", {}).get("FRAME_ID"),
        "VISUAL_MANIFEST_ID": request.get("VISUAL_MANIFEST_ID"),
        "RENDER_ARTIFACT_ID": render_result.get("RENDER_ARTIFACT_ID"),
        "RENDER_ARTIFACT_HASH": render_result.get("RENDER_ARTIFACT_HASH"),
        "PLAYER_SAFE_STRUCTURE_PACKAGE_ID": request.get("PLAYER_SAFE_STRUCTURE_PACKAGE_ID"),
        "GEOMETRY_LOCK_ID": request.get("GEOMETRY_LOCK_ID"),
    })


def _tactical_output_payload(authority, receipt):
    if authority == "STRUCTURAL_COMPARATOR":
        return {"STRUCTURAL_PASS": receipt.get("STRUCTURAL_PASS"), "TOPOLOGY_SOURCE": receipt.get("TOPOLOGY_SOURCE")}
    if authority == "PRESENTATION_VALIDATOR":
        return {"PRESENTATION_PASS": receipt.get("PRESENTATION_PASS")}
    if authority == "GEOMETRY_COMPARATOR":
        return {"GEOMETRY_COMPARE": receipt.get("GEOMETRY_COMPARE"), **{k: receipt.get(k) for k in GEOMETRY_MISMATCH_FIELDS}}
    if authority == "VISUAL_PIPELINE":
        return {"VISUAL_PIPELINE_RECEIPT_STATUS": receipt.get("VISUAL_PIPELINE_RECEIPT_STATUS")}
    if authority == "DETERMINISTIC_OVERLAY_VALIDATOR":
        return {
            "DETERMINISTIC_OVERLAY_STATUS": receipt.get("DETERMINISTIC_OVERLAY_STATUS"),
            "OVERLAY_SOURCE": receipt.get("OVERLAY_SOURCE"),
            "MECHANICAL_OVERLAY_AUTHORITY": receipt.get("MECHANICAL_OVERLAY_AUTHORITY"),
            "OVERLAY_ARTIFACT_ID": receipt.get("OVERLAY_ARTIFACT_ID"),
            "OVERLAY_ARTIFACT_HASH": receipt.get("OVERLAY_ARTIFACT_HASH"),
        }
    return {}


def tactical_output_digest(authority, receipt):
    return canonical_digest(_tactical_output_payload(authority, receipt))


def tactical_input_digest(request, packet, render_result):
    return _tactical_input_digest(request, packet, render_result)


def _tactical_findings(request, packet, render_result, registry):
    findings, ids = [], []
    for key in sorted(SELF_ASSERTED_TACTICAL_FIELDS & set(render_result)):
        findings.append(f"SELF_ASSERTED_TACTICAL_STATUS_FORBIDDEN:{key}")
    if registry is None:
        return findings + ["TACTICAL_TRUSTED_PROOF_REGISTRY_REQUIRED"], ids
    input_digest = _tactical_input_digest(request, packet, render_result)
    common = {
        "STATUS": "PASS",
        "ACTIVATION_ID": request.get("ACTIVATION_ID"),
        "PACKET_DIGEST": packet.get("PACKET_DIGEST"),
        "FRAME_ID": request.get("SCENE_FRAME", {}).get("FRAME_ID"),
        "VISUAL_MANIFEST_ID": request.get("VISUAL_MANIFEST_ID"),
        "RENDER_ARTIFACT_ID": render_result.get("RENDER_ARTIFACT_ID"),
        "RENDER_ARTIFACT_HASH": render_result.get("RENDER_ARTIFACT_HASH"),
        "PLAYER_SAFE_STRUCTURE_PACKAGE_ID": request.get("PLAYER_SAFE_STRUCTURE_PACKAGE_ID"),
        "GEOMETRY_LOCK_ID": request.get("GEOMETRY_LOCK_ID"),
        "COMPARATOR_INPUT_DIGEST": input_digest,
    }
    for field, (authority, pass_field) in TACTICAL_RECEIPT_SPECS.items():
        rid = render_result.get(field)
        if not rid:
            findings.append(f"TACTICAL_{field}_REQUIRED")
            continue
        rid = str(rid)
        ids.append(rid)
        receipt = registry.tactical_receipts.get(rid)
        if not isinstance(receipt, Mapping):
            findings.append(f"TACTICAL_RECEIPT_NOT_FOUND:{rid}")
            continue
        expected = {"RECEIPT_ID": rid, "PROOF_AUTHORITY": authority, **common}
        for key, expected_value in expected.items():
            if receipt.get(key) != expected_value:
                findings.append(f"TACTICAL_{authority}_{key}_BINDING_MISMATCH")
        if receipt.get(pass_field) != "PASS":
            findings.append(f"TACTICAL_{authority}_{pass_field}_NOT_PASS")
        if receipt.get("COMPARATOR_OUTPUT_DIGEST") != tactical_output_digest(authority, receipt):
            findings.append(f"TACTICAL_{authority}_OUTPUT_DIGEST_MISMATCH")
        if authority == "STRUCTURAL_COMPARATOR" and receipt.get("TOPOLOGY_SOURCE") != "PLAYER_SAFE_STRUCTURE_PACKAGE":
            findings.append("TACTICAL_STRUCTURAL_TOPOLOGY_SOURCE_INVALID")
        if authority == "GEOMETRY_COMPARATOR":
            for key in GEOMETRY_MISMATCH_FIELDS:
                if receipt.get(key) != 0:
                    findings.append(f"TACTICAL_GEOMETRY_ZERO_TOLERANCE_VIOLATION:{key}")
        if authority == "DETERMINISTIC_OVERLAY_VALIDATOR":
            if receipt.get("OVERLAY_SOURCE") != "DETERMINISTIC_POST_ART":
                findings.append("TACTICAL_OVERLAY_SOURCE_INVALID")
            if receipt.get("MECHANICAL_OVERLAY_AUTHORITY") != "DETERMINISTIC_POST_ART_ONLY":
                findings.append("TACTICAL_OVERLAY_AUTHORITY_INVALID")
            if not receipt.get("OVERLAY_ARTIFACT_ID"):
                findings.append("TACTICAL_OVERLAY_ARTIFACT_ID_REQUIRED")
            if not isinstance(receipt.get("OVERLAY_ARTIFACT_HASH"), str) or not _SHA256.fullmatch(receipt.get("OVERLAY_ARTIFACT_HASH")):
                findings.append("TACTICAL_OVERLAY_ARTIFACT_HASH_INVALID")
    if len(ids) != len(set(ids)):
        findings.append("TACTICAL_RECEIPT_ID_REUSE_WITHIN_RENDER")
    return findings, ids


def _replay_findings(snapshot, activation_id, render_id, identity_id, player_safe_id, tactical_ids):
    findings = []
    for item in snapshot.records.values():
        if item.get("ACTIVATION_ID") == activation_id:
            findings.append(f"REPLAYED_ACTIVATION_ID:{activation_id}")
        if item.get("RENDER_ARTIFACT_ID") == render_id:
            findings.append(f"REPLAYED_RENDER_ARTIFACT_ID:{render_id}")
        if item.get("IDENTITY_COMPARATOR_RECEIPT_ID") == identity_id:
            findings.append(f"REPLAYED_IDENTITY_COMPARATOR_RECEIPT:{identity_id}")
        if item.get("PLAYER_SAFE_CONTENT_RECEIPT_ID") == player_safe_id:
            findings.append(f"REPLAYED_PLAYER_SAFE_RECEIPT:{player_safe_id}")
        used = item.get("TACTICAL_RECEIPT_IDS", [])
        if isinstance(used, list):
            for rid in tactical_ids:
                if rid in used:
                    findings.append(f"REPLAYED_TACTICAL_RECEIPT:{rid}")
    return findings


def evaluate_for_display(
    request,
    packet,
    render_result,
    identity_comparator_receipts,
    scene_post_render_receipt,
    scene_proofs,
    activation_proofs,
    display_ledger_owner=None,
):
    registry, findings = _registry_findings(activation_proofs)
    owner, owner_findings = _ledger_owner_findings(display_ledger_owner, registry)
    findings.extend(owner_findings)

    tactical_ids = []
    sanitized_render = copy.deepcopy(dict(render_result))
    if request.get("TACTICAL_MODE") is True:
        tactical_findings, tactical_ids = _tactical_findings(request, packet, render_result, registry)
        findings.extend(tactical_findings)
        if not tactical_findings:
            sanitized_render.update({
                "STRUCTURAL_PASS": "PASS", "PRESENTATION_PASS": "PASS",
                "GEOMETRY_COMPARE": "PASS", "VISUAL_PIPELINE_RECEIPT_STATUS": "PASS",
                "DETERMINISTIC_OVERLAY_STATUS": "PASS",
                "OVERLAY_SOURCE": "DETERMINISTIC_POST_ART",
                "TOPOLOGY_SOURCE": "PLAYER_SAFE_STRUCTURE_PACKAGE",
            })

    base_registry = None
    if registry:
        base_registry = _base.materialize_activation_proof_registry(
            {key: dict(value) for key, value in registry.identity_comparator_receipts.items()},
            registry.source_revision,
        )
    base_result = _base.evaluate_for_display(
        request, packet, sanitized_render, identity_comparator_receipts,
        scene_post_render_receipt, scene_proofs, base_registry, (),
    )
    findings.extend(base_result.findings)

    identity_id = render_result.get("IDENTITY_COMPARATOR_RECEIPT_ID")
    player_safe_id = scene_post_render_receipt.get("PLAYER_SAFE_CONTENT_RECEIPT_ID")
    if owner:
        findings.extend(_replay_findings(
            owner.snapshot(), request.get("ACTIVATION_ID"),
            render_result.get("RENDER_ARTIFACT_ID"), identity_id,
            player_safe_id, tactical_ids,
        ))
    if findings or not base_result.passed:
        return ActivationResult("DISPLAY_BLOCKED", tuple(findings), packet, None)

    display_receipt = dict(base_result.display_receipt)
    display_receipt["TACTICAL_RECEIPT_IDS"] = list(tactical_ids)
    display_receipt["DISPLAY_LEDGER_ID"] = owner.ledger_id
    display_receipt["DISPLAY_LEDGER_OWNER_ID"] = owner.authority_instance_id
    display_receipt.pop("DISPLAY_RECEIPT_DIGEST", None)
    display_receipt["DISPLAY_RECEIPT_DIGEST"] = canonical_digest(display_receipt)

    commit_findings = owner.commit_if_fresh(display_receipt, tactical_ids)
    if commit_findings:
        return ActivationResult("DISPLAY_BLOCKED", tuple(commit_findings), packet, None)
    return ActivationResult("DISPLAY_PASS", (), packet, MappingProxyType(display_receipt))
