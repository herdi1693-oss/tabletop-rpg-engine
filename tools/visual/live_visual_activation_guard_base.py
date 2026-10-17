#!/usr/bin/env python3
"""Fail-closed live visual activation candidate.

Tooling-only composition layer. It executes the already-validated visual guards
in the required order and emits a player-safe generation packet plus a display
receipt. It never mutates Runtime, Campaign Canon, Recovery, Geometry Master,
RNG, or Project Source membership.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from .entity_visual_state_guard import validate_entity_visual_state
from .scene_continuity_guard import canonical_digest, evaluate_post_render as evaluate_scene_post_render, validate_frame
from .visual_identity_guard import evaluate_post_render as evaluate_identity_post_render, validate_manifest


REQUEST_KINDS = {"ILLUSTRATED_SCENE", "TACTICAL_MAP"}
FORBIDDEN_KEY_TOKENS = {"HIDDEN", "SECRET", "DM_ONLY", "DM_TRUTH", "RAW_DM", "RAW_MAP", "MAP_GEOMETRY_MASTER"}
GENERATION_PACKET_KEYS = {
    "ACTIVATION_ID", "REQUEST_KIND", "SOURCE_STATE_EPOCH", "OBSERVER_BRANCH_ID",
    "PLAYER_KNOWLEDGE_PROJECTION_ID", "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID",
    "SCENE_FRAME_ID", "CONTINUITY_GROUP_ID", "VISUAL_MANIFEST_ID",
    "PLAYER_SAFE_STRUCTURE_PACKAGE_ID", "GEOMETRY_LOCK_ID", "STRUCTURE_INPUT_MODE",
    "GENERATOR_AUTHORITY", "MECHANICAL_OVERLAY_AUTHORITY", "TACTICAL_MODE",
    "ENTITY_VISUAL_STATES", "PLAYER_SAFE_SCENE_FACTS", "VISUAL_REFERENCE_MANIFEST",
    "DECORATION_BRIEF", "CANON_DIRECTION", "VISUAL_TO_CANON", "PROJECT_SOURCE_SLOT_DELTA",
    "PACKET_AUTHORITY", "PACKET_DIGEST",
}


@dataclass(frozen=True)
class ActivationProofRegistry:
    status: str
    source_revision: str
    identity_comparator_receipts: Mapping[str, Mapping[str, object]]
    digest: str


@dataclass(frozen=True)
class ActivationResult:
    status: str
    findings: Sequence[str]
    packet: Mapping[str, object] | None = None
    display_receipt: Mapping[str, object] | None = None

    @property
    def passed(self) -> bool:
        return self.status in {"GENERATION_READY", "DISPLAY_PASS"}


def _result(status: str, findings: Sequence[str], packet=None, display_receipt=None) -> ActivationResult:
    return ActivationResult(status, tuple(findings), packet, display_receipt)


def _frozen_receipts(receipts: Mapping[str, Mapping[str, object]]) -> Mapping[str, Mapping[str, object]]:
    return MappingProxyType({str(k): MappingProxyType(copy.deepcopy(dict(v))) for k, v in receipts.items() if isinstance(v, Mapping)})


def materialize_activation_proof_registry(receipts: Mapping[str, Mapping[str, object]], source_revision: str) -> ActivationProofRegistry:
    frozen = _frozen_receipts(receipts)
    body = {k: dict(v) for k, v in frozen.items()}
    return ActivationProofRegistry("MATERIALIZED_READ_ONLY", str(source_revision), frozen, canonical_digest(body))


def _registry_findings(registry: object) -> tuple[ActivationProofRegistry | None, list[str]]:
    if not isinstance(registry, ActivationProofRegistry):
        return None, ["ACTIVATION_PROOF_REGISTRY_REQUIRED"]
    findings = []
    if registry.status != "MATERIALIZED_READ_ONLY":
        findings.append("ACTIVATION_PROOF_REGISTRY_STATUS_INVALID")
    if not registry.source_revision:
        findings.append("ACTIVATION_PROOF_REGISTRY_SOURCE_REVISION_REQUIRED")
    body = {k: dict(v) for k, v in registry.identity_comparator_receipts.items()}
    if registry.digest != canonical_digest(body):
        findings.append("ACTIVATION_PROOF_REGISTRY_DIGEST_MISMATCH")
    return registry, findings


def _forbidden_paths(value: object, path: str = "ROOT") -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_s = str(key).upper()
            if any(token in key_s for token in FORBIDDEN_KEY_TOKENS):
                findings.append(f"FORBIDDEN_GENERATOR_INPUT_KEY:{path}.{key}")
            findings.extend(_forbidden_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_forbidden_paths(child, f"{path}[{index}]"))
    return findings


def _scene_structure_bindings(frame: Mapping[str, object], proofs: object, package_id: object, geometry_lock_id: object) -> list[str]:
    findings: list[str] = []
    if not isinstance(proofs, Mapping):
        return ["SCENE_PROOF_REGISTRY_REQUIRED"]
    sources = proofs.get("PLAYER_SAFE_SOURCE_RECEIPTS")
    if not isinstance(sources, Mapping):
        return ["PLAYER_SAFE_SOURCE_RECEIPT_REGISTRY_REQUIRED"]
    for fact in frame.get("SCENE_FACTS", []):
        if not isinstance(fact, Mapping) or fact.get("FACT_CLASS") != "IMMUTABLE_STRUCTURE":
            continue
        rid = fact.get("SOURCE_RECEIPT_ID")
        receipt = sources.get(rid)
        prefix = f"STRUCTURE_FACT:{fact.get('FACT_ID')}"
        if not isinstance(receipt, Mapping):
            findings.append(f"{prefix}:SOURCE_RECEIPT_NOT_FOUND")
            continue
        if receipt.get("SOURCE_KIND") != "PLAYER_SAFE_STRUCTURE_PACKAGE":
            findings.append(f"{prefix}:PLAYER_SAFE_STRUCTURE_SOURCE_REQUIRED")
        if receipt.get("PLAYER_SAFE_STRUCTURE_PACKAGE_ID") != package_id:
            findings.append(f"{prefix}:PLAYER_SAFE_STRUCTURE_PACKAGE_BINDING_MISMATCH")
        if receipt.get("GEOMETRY_LOCK_ID") != geometry_lock_id or receipt.get("GEOMETRY_LOCK_STATUS") != "PASS":
            findings.append(f"{prefix}:GEOMETRY_LOCK_BINDING_MISMATCH")
    return findings


def _packet_digest(packet: Mapping[str, object]) -> str:
    body = dict(packet)
    body.pop("PACKET_DIGEST", None)
    return canonical_digest(body)


def build_generation_packet(request: Mapping[str, object], scene_proofs: object = None) -> ActivationResult:
    findings: list[str] = []
    required = {
        "ACTIVATION_ID", "REQUEST_KIND", "SOURCE_KIND", "SOURCE_STATE_EPOCH", "OBSERVER_BRANCH_ID",
        "PLAYER_KNOWLEDGE_PROJECTION_ID", "PLAYER_KNOWLEDGE_PROJECTION_STATUS",
        "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID", "KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS",
        "ENTITY_VISUAL_STATES", "SCENE_FRAME", "VISUAL_REFERENCE_MANIFEST", "VISUAL_MANIFEST_ID",
        "PLAYER_SAFE_STRUCTURE_PACKAGE_ID", "GEOMETRY_LOCK_ID", "GEOMETRY_LOCK_STATUS",
        "GENERATOR_AUTHORITY", "STRUCTURE_AUTHORITY", "MECHANICAL_OVERLAY_AUTHORITY",
        "DECORATION_BRIEF", "TACTICAL_MODE", "CANON_DIRECTION", "VISUAL_TO_CANON", "PROJECT_SOURCE_SLOT_DELTA",
    }
    for key in sorted(required - set(request)):
        findings.append(f"MISSING_{key}")
    if findings:
        return _result("BLOCKED", findings)

    if request.get("REQUEST_KIND") not in REQUEST_KINDS:
        findings.append("UNKNOWN_REQUEST_KIND")
    if request.get("SOURCE_KIND") != "COMMITTED_GAME_STATE":
        findings.append("COMMITTED_GAME_STATE_REQUIRED")
    if request.get("PLAYER_KNOWLEDGE_PROJECTION_STATUS") != "MATERIALIZED":
        findings.append("MATERIALIZED_PKP_REQUIRED")
    if request.get("KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS") != "PASS":
        findings.append("KNOWLEDGE_LEAK_PREOUTPUT_GATE_PASS_REQUIRED")
    if request.get("CANON_DIRECTION") != "CANON_TO_VISUAL_ONLY" or request.get("VISUAL_TO_CANON") is not False:
        findings.append("CANON_TO_VISUAL_ONLY_REQUIRED")
    if request.get("GENERATOR_AUTHORITY") != "DECORATION_ONLY":
        findings.append("GENERATOR_DECORATION_ONLY_REQUIRED")
    if request.get("STRUCTURE_AUTHORITY") != "PLAYER_SAFE_STRUCTURE_PACKAGE_IMMUTABLE":
        findings.append("PLAYER_SAFE_STRUCTURE_AUTHORITY_REQUIRED")
    if request.get("MECHANICAL_OVERLAY_AUTHORITY") != "DETERMINISTIC_POST_ART_ONLY":
        findings.append("DETERMINISTIC_POST_ART_OVERLAYS_REQUIRED")
    if request.get("GEOMETRY_LOCK_STATUS") != "PASS":
        findings.append("GEOMETRY_LOCK_PASS_REQUIRED")
    if request.get("PROJECT_SOURCE_SLOT_DELTA") != 0:
        findings.append("PROJECT_SOURCE_SLOT_DELTA_MUST_BE_ZERO")
    if not isinstance(request.get("TACTICAL_MODE"), bool):
        findings.append("TACTICAL_MODE_BOOLEAN_REQUIRED")
    if not isinstance(request.get("DECORATION_BRIEF"), Mapping):
        findings.append("DECORATION_BRIEF_MAPPING_REQUIRED")

    frame = request.get("SCENE_FRAME")
    manifest = request.get("VISUAL_REFERENCE_MANIFEST")
    states = request.get("ENTITY_VISUAL_STATES")
    if not isinstance(frame, Mapping):
        findings.append("SCENE_FRAME_REQUIRED")
        frame = {}
    if not isinstance(manifest, Mapping):
        findings.append("VISUAL_REFERENCE_MANIFEST_REQUIRED")
        manifest = {}
    if not isinstance(states, list) or not states:
        findings.append("ENTITY_VISUAL_STATES_REQUIRED")
        states = []

    # The live path calls the validated guards; these are not import-only dependencies.
    for state in states:
        if not isinstance(state, Mapping):
            findings.append("ENTITY_VISUAL_STATE_RECORD_INVALID")
            continue
        result = validate_entity_visual_state(state)
        findings.extend(f"EVS:{item}" for item in result.findings)
    if frame:
        result = validate_frame(frame, scene_proofs)
        findings.extend(f"SCL:{item}" for item in result.findings)
    if manifest:
        result = validate_manifest(manifest)
        findings.extend(f"VIL:{item}" for item in result.findings)

    epoch = request.get("SOURCE_STATE_EPOCH")
    branch = request.get("OBSERVER_BRANCH_ID")
    pkp = request.get("PLAYER_KNOWLEDGE_PROJECTION_ID")
    leak = request.get("KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID")
    if frame:
        for field, expected in (
            ("SOURCE_STATE_EPOCH", epoch), ("OBSERVER_BRANCH_ID", branch),
            ("PLAYER_KNOWLEDGE_PROJECTION_ID", pkp), ("KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID", leak),
        ):
            if frame.get(field) != expected:
                findings.append(f"SCENE_FRAME_{field}_BINDING_MISMATCH")
        if frame.get("VISUAL_MANIFEST_ID") != request.get("VISUAL_MANIFEST_ID"):
            findings.append("SCENE_FRAME_VISUAL_MANIFEST_ID_MISMATCH")
    if manifest:
        if manifest.get("PLAYER_KNOWLEDGE_PROJECTION_ID") != pkp:
            findings.append("VISUAL_MANIFEST_PKP_BINDING_MISMATCH")
        if manifest.get("CONTINUITY_GROUP_ID") != frame.get("CONTINUITY_GROUP_ID"):
            findings.append("VISUAL_MANIFEST_CONTINUITY_GROUP_MISMATCH")
        if manifest.get("VISUAL_MANIFEST_ID") not in (None, request.get("VISUAL_MANIFEST_ID")):
            findings.append("VISUAL_MANIFEST_ID_BINDING_MISMATCH")
    for state in states:
        if not isinstance(state, Mapping):
            continue
        for field, expected in (
            ("SOURCE_STATE_EPOCH", epoch), ("OBSERVER_BRANCH_ID", branch),
            ("PLAYER_KNOWLEDGE_PROJECTION_ID", pkp), ("KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID", leak),
        ):
            if state.get(field) != expected:
                findings.append(f"EVS:{state.get('ENTITY_ID')}:{field}_BINDING_MISMATCH")

    evs_ids = {str(x.get("ENTITY_ID")) for x in states if isinstance(x, Mapping)}
    manifest_ids = {str(x.get("ENTITY_ID")) for x in manifest.get("ENTITIES", []) if isinstance(x, Mapping)}
    frame_ids = set(map(str, frame.get("IN_FRAME_ENTITY_IDS", [])))
    if evs_ids != manifest_ids or manifest_ids != frame_ids:
        findings.append("VISIBLE_ENTITY_SET_BINDING_MISMATCH")

    findings.extend(_scene_structure_bindings(
        frame, scene_proofs, request.get("PLAYER_SAFE_STRUCTURE_PACKAGE_ID"), request.get("GEOMETRY_LOCK_ID")
    ))
    findings.extend(_forbidden_paths(request.get("DECORATION_BRIEF"), "DECORATION_BRIEF"))

    if findings:
        return _result("BLOCKED", findings)

    packet = {
        "ACTIVATION_ID": request["ACTIVATION_ID"],
        "REQUEST_KIND": request["REQUEST_KIND"],
        "SOURCE_STATE_EPOCH": epoch,
        "OBSERVER_BRANCH_ID": branch,
        "PLAYER_KNOWLEDGE_PROJECTION_ID": pkp,
        "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID": leak,
        "SCENE_FRAME_ID": frame.get("FRAME_ID"),
        "CONTINUITY_GROUP_ID": frame.get("CONTINUITY_GROUP_ID"),
        "VISUAL_MANIFEST_ID": request["VISUAL_MANIFEST_ID"],
        "PLAYER_SAFE_STRUCTURE_PACKAGE_ID": request["PLAYER_SAFE_STRUCTURE_PACKAGE_ID"],
        "GEOMETRY_LOCK_ID": request["GEOMETRY_LOCK_ID"],
        "STRUCTURE_INPUT_MODE": "IMMUTABLE_PLAYER_SAFE_REFERENCE_ONLY",
        "GENERATOR_AUTHORITY": "DECORATION_ONLY",
        "MECHANICAL_OVERLAY_AUTHORITY": "DETERMINISTIC_POST_ART_ONLY",
        "TACTICAL_MODE": request["TACTICAL_MODE"],
        "ENTITY_VISUAL_STATES": copy.deepcopy(states),
        "PLAYER_SAFE_SCENE_FACTS": copy.deepcopy(frame.get("SCENE_FACTS", [])),
        "VISUAL_REFERENCE_MANIFEST": copy.deepcopy(manifest),
        "DECORATION_BRIEF": copy.deepcopy(request["DECORATION_BRIEF"]),
        "CANON_DIRECTION": "CANON_TO_VISUAL_ONLY",
        "VISUAL_TO_CANON": False,
        "PROJECT_SOURCE_SLOT_DELTA": 0,
        "PACKET_AUTHORITY": "DERIVED_NONAUTHORITATIVE",
    }
    packet["PACKET_DIGEST"] = _packet_digest(packet)
    if set(packet) != GENERATION_PACKET_KEYS:
        return _result("BLOCKED", ["GENERATION_PACKET_SCHEMA_DRIFT"])
    forbidden = _forbidden_paths(packet)
    if forbidden:
        return _result("BLOCKED", forbidden)
    return _result("GENERATION_READY", [], MappingProxyType(packet))


def _display_history_findings(history: Sequence[Mapping[str, object]], activation_id: object, render_id: object, identity_receipt_id: object, player_safe_receipt_id: object) -> list[str]:
    findings: list[str] = []
    for item in history:
        if not isinstance(item, Mapping):
            continue
        if item.get("ACTIVATION_ID") == activation_id:
            findings.append(f"REPLAYED_ACTIVATION_ID:{activation_id}")
        if item.get("RENDER_ARTIFACT_ID") == render_id:
            findings.append(f"REPLAYED_RENDER_ARTIFACT_ID:{render_id}")
        if item.get("IDENTITY_COMPARATOR_RECEIPT_ID") == identity_receipt_id:
            findings.append(f"REPLAYED_IDENTITY_COMPARATOR_RECEIPT:{identity_receipt_id}")
        if item.get("PLAYER_SAFE_CONTENT_RECEIPT_ID") == player_safe_receipt_id:
            findings.append(f"REPLAYED_PLAYER_SAFE_RECEIPT:{player_safe_receipt_id}")
    return findings


def evaluate_for_display(
    request: Mapping[str, object],
    packet: Mapping[str, object],
    render_result: Mapping[str, object],
    identity_comparator_receipts: Mapping[str, Mapping[str, object]],
    scene_post_render_receipt: Mapping[str, object],
    scene_proofs: object,
    activation_proofs: object,
    display_history: Sequence[Mapping[str, object]] = (),
) -> ActivationResult:
    findings: list[str] = []
    registry, reg_findings = _registry_findings(activation_proofs)
    findings.extend(reg_findings)

    if not isinstance(packet, Mapping) or packet.get("PACKET_DIGEST") != _packet_digest(packet):
        findings.append("GENERATION_PACKET_DIGEST_MISMATCH")
    if set(packet) != GENERATION_PACKET_KEYS:
        findings.append("GENERATION_PACKET_SCHEMA_INVALID")
    findings.extend(_forbidden_paths(packet))

    required_render = {
        "STATUS", "ACTIVATION_ID", "PACKET_DIGEST", "RENDER_ARTIFACT_ID", "RENDER_ARTIFACT_HASH",
        "IDENTITY_COMPARATOR_RECEIPT_ID", "CANON_WRITE_ATTEMPT", "VISUAL_TO_CANON_ATTEMPT",
        "GAMEPLAY_MUTATION_ATTEMPT", "GAMEPLAY_EVENT_REQUESTED", "RNG_REQUESTED",
    }
    for key in sorted(required_render - set(render_result)):
        findings.append(f"RENDER_MISSING_{key}")
    if render_result.get("ACTIVATION_ID") != request.get("ACTIVATION_ID"):
        findings.append("RENDER_ACTIVATION_BINDING_MISMATCH")
    if render_result.get("PACKET_DIGEST") != packet.get("PACKET_DIGEST"):
        findings.append("RENDER_PACKET_BINDING_MISMATCH")
    for key in ("CANON_WRITE_ATTEMPT", "VISUAL_TO_CANON_ATTEMPT", "GAMEPLAY_MUTATION_ATTEMPT", "GAMEPLAY_EVENT_REQUESTED", "RNG_REQUESTED"):
        if render_result.get(key) is not False:
            findings.append(f"FORBIDDEN_RENDER_SIDE_EFFECT:{key}")

    if render_result.get("STATUS") != "SUCCESS":
        findings.append("RENDER_NOT_SUCCESSFUL")
        return _result("DISPLAY_BLOCKED", findings)

    if scene_post_render_receipt.get("RENDER_ARTIFACT_ID") != render_result.get("RENDER_ARTIFACT_ID") or scene_post_render_receipt.get("RENDER_ARTIFACT_HASH") != render_result.get("RENDER_ARTIFACT_HASH"):
        findings.append("SCENE_POST_RENDER_ARTIFACT_BINDING_MISMATCH")

    identity_result = evaluate_identity_post_render(request.get("VISUAL_REFERENCE_MANIFEST", {}), identity_comparator_receipts)
    findings.extend(f"VIL_POST:{item}" for item in identity_result.findings)
    scene_result = evaluate_scene_post_render(request.get("SCENE_FRAME", {}), scene_post_render_receipt, scene_proofs)
    findings.extend(f"SCL_POST:{item}" for item in scene_result.findings)

    identity_receipt_id = render_result.get("IDENTITY_COMPARATOR_RECEIPT_ID")
    if registry:
        external = registry.identity_comparator_receipts.get(str(identity_receipt_id))
        if not isinstance(external, Mapping):
            findings.append(f"IDENTITY_COMPARATOR_RECEIPT_NOT_FOUND:{identity_receipt_id}")
        else:
            expected = {
                "RECEIPT_ID": identity_receipt_id,
                "STATUS": "PASS",
                "PROOF_AUTHORITY": "VISUAL_IDENTITY_LOCK",
                "ACTIVATION_ID": request.get("ACTIVATION_ID"),
                "PACKET_DIGEST": packet.get("PACKET_DIGEST"),
                "FRAME_ID": request.get("SCENE_FRAME", {}).get("FRAME_ID"),
                "RENDER_ARTIFACT_ID": render_result.get("RENDER_ARTIFACT_ID"),
                "RENDER_ARTIFACT_HASH": render_result.get("RENDER_ARTIFACT_HASH"),
                "VISUAL_MANIFEST_ID": request.get("VISUAL_MANIFEST_ID"),
                "COMPARATOR_PAYLOAD_DIGEST": canonical_digest(identity_comparator_receipts),
            }
            for key, value in expected.items():
                if external.get(key) != value:
                    findings.append(f"IDENTITY_COMPARATOR_RECEIPT_{key}_BINDING_MISMATCH")

    player_safe_receipt_id = scene_post_render_receipt.get("PLAYER_SAFE_CONTENT_RECEIPT_ID")
    findings.extend(_display_history_findings(
        display_history, request.get("ACTIVATION_ID"), render_result.get("RENDER_ARTIFACT_ID"), identity_receipt_id, player_safe_receipt_id
    ))

    if request.get("TACTICAL_MODE") is True:
        tactical_expected = {
            "STRUCTURAL_PASS": "PASS",
            "PRESENTATION_PASS": "PASS",
            "GEOMETRY_COMPARE": "PASS",
            "VISUAL_PIPELINE_RECEIPT_STATUS": "PASS",
            "DETERMINISTIC_OVERLAY_STATUS": "PASS",
            "OVERLAY_SOURCE": "DETERMINISTIC_POST_ART",
            "TOPOLOGY_SOURCE": "PLAYER_SAFE_STRUCTURE_PACKAGE",
        }
        for key, value in tactical_expected.items():
            if render_result.get(key) != value:
                findings.append(f"TACTICAL_{key}_REQUIRED")

    if findings:
        return _result("DISPLAY_BLOCKED", findings)

    display_receipt = {
        "DISPLAY_RECEIPT_ID": f"DISPLAY-{request.get('ACTIVATION_ID')}-{render_result.get('RENDER_ARTIFACT_ID')}",
        "STATUS": "PASS",
        "ACTIVATION_ID": request.get("ACTIVATION_ID"),
        "PACKET_DIGEST": packet.get("PACKET_DIGEST"),
        "FRAME_ID": request.get("SCENE_FRAME", {}).get("FRAME_ID"),
        "VISUAL_MANIFEST_ID": request.get("VISUAL_MANIFEST_ID"),
        "RENDER_ARTIFACT_ID": render_result.get("RENDER_ARTIFACT_ID"),
        "RENDER_ARTIFACT_HASH": render_result.get("RENDER_ARTIFACT_HASH"),
        "IDENTITY_COMPARATOR_RECEIPT_ID": identity_receipt_id,
        "PLAYER_SAFE_CONTENT_RECEIPT_ID": player_safe_receipt_id,
        "CANON_WRITE": False,
        "GAMEPLAY_MUTATION": False,
    }
    display_receipt["DISPLAY_RECEIPT_DIGEST"] = canonical_digest(display_receipt)
    return _result("DISPLAY_PASS", [], packet, MappingProxyType(display_receipt))
