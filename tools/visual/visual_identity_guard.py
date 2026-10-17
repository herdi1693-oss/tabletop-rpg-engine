#!/usr/bin/env python3
"""Visual identity guard for contract/tooling QA.

This helper is deliberately presentation-only. It validates a frozen visual
reference manifest and complete post-render comparator receipts; it never reads
or mutates Campaign Canon, Runtime, RNG, saves, Geometry Master, or player
knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Set


IDENTITY_CLASS_LOCK_LEVELS = {
    "PC": "VERY_STRICT",
    "NAMED_RECURRING_NPC": "STRICT",
    "NAMED_RECURRING_MONSTER": "STRICT",
    "UNIQUE_BOSS": "STRICT",
    "STANDARD_MONSTER_SPECIES": "MODERATE",
    "BACKGROUND_CROWD": "LOOSE_WITH_SPECIES_GUARD",
    "GENERIC_MOB": "LOOSE_WITH_SPECIES_GUARD",
}

MONSTER_CLASSES = {
    "NAMED_RECURRING_MONSTER",
    "UNIQUE_BOSS",
    "STANDARD_MONSTER_SPECIES",
    "GENERIC_MOB",
    "BACKGROUND_CROWD",
}

ANCHOR_ELIGIBLE = {
    "NAMED_RECURRING_NPC",
    "NAMED_RECURRING_MONSTER",
    "UNIQUE_BOSS",
}

REQUIRED_ENTITY_FIELDS = {
    "ENTITY_ID",
    "ENTITY_CLASS",
    "CURRENT_FORM",
    "IDENTITY_LOCK_LEVEL",
    "REQUIRED_REFERENCE_AUTHORITY",
    "ACTUAL_REFERENCE_ASSET",
    "CURRENT_VISIBLE_STATE_SOURCE",
    "HANDOFF_STATUS",
}

COMPARATOR_CLASSES = {
    "PC_IDENTITY",
    "SPECIES_FORM_IDENTITY",
    "RECURRING_INSTANCE_IDENTITY",
    "VISIBLE_EQUIPMENT_STATE",
    "SCENE_CONTINUITY",
    "PLAYER_SAFE_CONTENT",
}

ALLOWED_COMPARATOR_STATUSES = {"PASS", "FAIL", "NA"}

BASE_REQUIRED_COMPARATORS_BY_CLASS: Mapping[str, Set[str]] = {
    "PC": {"PC_IDENTITY", "VISIBLE_EQUIPMENT_STATE", "PLAYER_SAFE_CONTENT"},
    "NAMED_RECURRING_NPC": {
        "RECURRING_INSTANCE_IDENTITY",
        "VISIBLE_EQUIPMENT_STATE",
        "PLAYER_SAFE_CONTENT",
    },
    "NAMED_RECURRING_MONSTER": {
        "SPECIES_FORM_IDENTITY",
        "RECURRING_INSTANCE_IDENTITY",
        "VISIBLE_EQUIPMENT_STATE",
        "PLAYER_SAFE_CONTENT",
    },
    "UNIQUE_BOSS": {
        "SPECIES_FORM_IDENTITY",
        "RECURRING_INSTANCE_IDENTITY",
        "VISIBLE_EQUIPMENT_STATE",
        "PLAYER_SAFE_CONTENT",
    },
    "STANDARD_MONSTER_SPECIES": {
        "SPECIES_FORM_IDENTITY",
        "VISIBLE_EQUIPMENT_STATE",
        "PLAYER_SAFE_CONTENT",
    },
    "GENERIC_MOB": {"SPECIES_FORM_IDENTITY", "PLAYER_SAFE_CONTENT"},
    "BACKGROUND_CROWD": {"SPECIES_FORM_IDENTITY", "PLAYER_SAFE_CONTENT"},
}

HARD_FAIL_OBSERVATIONS = {
    "PC_IDENTITY_DRIFT",
    "SPECIES_DRIFT",
    "WRONG_MONSTER_FORM",
    "DEFINING_ANATOMY_DRIFT",
    "UNIQUE_VARIANT_DRIFT",
    "RECURRING_ANCHOR_DRIFT",
    "INVENTED_VISIBLE_EQUIPMENT_CONFLICT",
    "HIDDEN_DM_INFORMATION_LEAK",
    "PANEL_IDENTITY_SWAP",
}


@dataclass(frozen=True)
class GuardResult:
    status: str
    findings: Sequence[str]

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def _missing_fields(entity: Mapping[str, object]) -> List[str]:
    return sorted(field for field in REQUIRED_ENTITY_FIELDS if field not in entity)


def _required_comparators(entity_class: str, continuity_group_present: bool) -> Set[str]:
    required = set(BASE_REQUIRED_COMPARATORS_BY_CLASS[entity_class])
    if continuity_group_present:
        required.add("SCENE_CONTINUITY")
    return required


def validate_manifest(manifest: Mapping[str, object]) -> GuardResult:
    findings: List[str] = []

    if manifest.get("PLAYER_SAFE_SCENE") is not True:
        findings.append("PLAYER_SAFE_SCENE_REQUIRED")
    if not manifest.get("PLAYER_KNOWLEDGE_PROJECTION_ID"):
        findings.append("PLAYER_KNOWLEDGE_PROJECTION_ID_REQUIRED")
    if manifest.get("CANON_DIRECTION") != "CANON_TO_VISUAL_ONLY":
        findings.append("CANON_DIRECTION_INVALID")
    if manifest.get("VISUAL_TO_CANON") is not False:
        findings.append("VISUAL_TO_CANON_MUST_BE_FALSE")
    if manifest.get("PROJECT_SOURCE_SLOT_DELTA") != 0:
        findings.append("PROJECT_SOURCE_SLOT_DELTA_MUST_BE_ZERO")

    entities = manifest.get("ENTITIES")
    if not isinstance(entities, list) or not entities:
        findings.append("ENTITIES_REQUIRED")
        entities = []

    seen_entity_ids = set()
    for entity in entities:
        if not isinstance(entity, dict):
            findings.append("ENTITY_RECORD_INVALID")
            continue

        entity_id = str(entity.get("ENTITY_ID", "UNKNOWN"))
        missing = _missing_fields(entity)
        findings.extend(f"{entity_id}:MISSING_{field}" for field in missing)
        if missing:
            continue

        if entity_id in seen_entity_ids:
            findings.append(f"{entity_id}:DUPLICATE_ENTITY_ID")
        seen_entity_ids.add(entity_id)

        entity_class = str(entity["ENTITY_CLASS"])
        lock_level = str(entity["IDENTITY_LOCK_LEVEL"])
        handoff = str(entity["HANDOFF_STATUS"])
        ref_asset = entity.get("ACTUAL_REFERENCE_ASSET")
        ref_authority = entity.get("REQUIRED_REFERENCE_AUTHORITY")

        if entity_class not in IDENTITY_CLASS_LOCK_LEVELS:
            findings.append(f"{entity_id}:UNKNOWN_ENTITY_CLASS")
            continue

        expected_lock = IDENTITY_CLASS_LOCK_LEVELS[entity_class]
        if lock_level != expected_lock:
            findings.append(f"{entity_id}:WRONG_IDENTITY_LOCK_LEVEL")

        if handoff != "PASSED" or not ref_asset or not ref_authority:
            findings.append(f"{entity_id}:REQUIRED_REFERENCE_HANDOFF_NOT_PASSED")

        if entity.get("CURRENT_VISIBLE_STATE_SOURCE") != "COMMITTED_RUNTIME_OR_SAVE":
            findings.append(f"{entity_id}:VISIBLE_STATE_NOT_RUNTIME_BOUND")

        if entity_class == "PC":
            if entity.get("REFERENCE_MODE") != "APPROVED_CANON_VISUAL_MASTER":
                findings.append(f"{entity_id}:PC_VISUAL_MASTER_REQUIRED")
            if entity.get("GENERIC_CLASS_SUBSTITUTE_ALLOWED") is not False:
                findings.append(f"{entity_id}:GENERIC_PC_SUBSTITUTE_FORBIDDEN")

        if entity_class in MONSTER_CLASSES:
            if entity.get("SPECIES_DRIFT_ALLOWED") is not False:
                findings.append(f"{entity_id}:SPECIES_DRIFT_MUST_BE_FALSE")
            if entity.get("FORM_DRIFT_ALLOWED") is not False:
                findings.append(f"{entity_id}:FORM_DRIFT_MUST_BE_FALSE")
            if entity.get("STYLE_TRANSFORM_ALLOWED") is not True:
                findings.append(f"{entity_id}:MONSTER_STYLE_TRANSFORM_SHOULD_BE_ALLOWED")

        anchor_status = entity.get("CAMPAIGN_ANCHOR_STATUS")
        if entity_class in ANCHOR_ELIGIBLE and anchor_status == "APPROVED":
            if not entity.get("CAMPAIGN_VISUAL_ANCHOR_ID"):
                findings.append(f"{entity_id}:APPROVED_ANCHOR_ID_REQUIRED")
            if not entity.get("CAMPAIGN_VISUAL_ANCHOR_ASSET"):
                findings.append(f"{entity_id}:APPROVED_ANCHOR_ASSET_REQUIRED")
            if entity.get("ANCHOR_OVERRIDES_SPECIES_AUTHORITY") is not False:
                findings.append(f"{entity_id}:ANCHOR_CANNOT_OVERRIDE_SPECIES")

    return GuardResult("PASS" if not findings else "FAIL", tuple(findings))


def evaluate_post_render(
    manifest: Mapping[str, object],
    receipts: Mapping[str, Mapping[str, object]],
) -> GuardResult:
    """Evaluate complete per-entity comparator receipts fail-closed.

    Every entity present in VISUAL_REFERENCE_MANIFEST is treated as visible and
    required for display. Each must submit all comparator classes explicitly as
    PASS/FAIL/NA plus an explicit FAILURE_FLAGS list. NA is legal only for a
    comparator that is not applicable to that entity in the current scene.
    """

    preflight = validate_manifest(manifest)
    findings = list(preflight.findings)

    entities = {
        str(entity["ENTITY_ID"]): entity
        for entity in manifest.get("ENTITIES", [])
        if isinstance(entity, dict) and entity.get("ENTITY_ID")
    }
    continuity_group_present = bool(manifest.get("CONTINUITY_GROUP_ID"))

    if not isinstance(receipts, Mapping):
        return GuardResult(
            "REJECT_AND_REGENERATE",
            tuple(findings + ["POST_RENDER_RECEIPTS_INVALID"]),
        )

    for receipt_entity_id in receipts:
        if receipt_entity_id not in entities:
            findings.append(f"{receipt_entity_id}:RECEIPT_ENTITY_NOT_IN_MANIFEST")

    for entity_id, entity in entities.items():
        receipt = receipts.get(entity_id)
        if not isinstance(receipt, Mapping):
            findings.append(f"{entity_id}:POST_RENDER_RECEIPT_MISSING")
            continue

        comparators = receipt.get("COMPARATORS")
        if not isinstance(comparators, Mapping):
            findings.append(f"{entity_id}:COMPARATOR_MAP_MISSING")
            comparators = {}

        comparator_keys = set(str(key) for key in comparators.keys())
        for unknown in sorted(comparator_keys - COMPARATOR_CLASSES):
            findings.append(f"{entity_id}:UNKNOWN_COMPARATOR_CLASS:{unknown}")
        for missing in sorted(COMPARATOR_CLASSES - comparator_keys):
            findings.append(f"{entity_id}:MISSING_COMPARATOR_CLASS:{missing}")

        entity_class = str(entity.get("ENTITY_CLASS", ""))
        if entity_class not in IDENTITY_CLASS_LOCK_LEVELS:
            findings.append(f"{entity_id}:UNKNOWN_ENTITY_CLASS")
            required_comparators: Set[str] = set()
        else:
            required_comparators = _required_comparators(
                entity_class,
                continuity_group_present,
            )

        for comparator_name in sorted(COMPARATOR_CLASSES & comparator_keys):
            status = comparators[comparator_name]
            if status not in ALLOWED_COMPARATOR_STATUSES:
                findings.append(
                    f"{entity_id}:UNKNOWN_COMPARATOR_STATUS:{comparator_name}:{status}"
                )
                continue
            if status == "FAIL":
                findings.append(f"{entity_id}:COMPARATOR_FAIL:{comparator_name}")
            if comparator_name in required_comparators and status == "NA":
                findings.append(f"{entity_id}:REQUIRED_COMPARATOR_NA:{comparator_name}")

        flags = receipt.get("FAILURE_FLAGS")
        if not isinstance(flags, list):
            findings.append(f"{entity_id}:FAILURE_FLAGS_LIST_MISSING")
            flags = []

        for flag in flags:
            if flag not in HARD_FAIL_OBSERVATIONS:
                findings.append(f"{entity_id}:UNKNOWN_FAILURE_FLAG:{flag}")
            else:
                findings.append(f"{entity_id}:{flag}")

    return GuardResult("PASS" if not findings else "REJECT_AND_REGENERATE", tuple(findings))


def validate_continuity_sequence(manifests: Sequence[Mapping[str, object]]) -> GuardResult:
    findings: List[str] = []
    if not manifests:
        return GuardResult("FAIL", ("EMPTY_CONTINUITY_SEQUENCE",))

    group_ids = {m.get("CONTINUITY_GROUP_ID") for m in manifests}
    if len(group_ids) != 1 or None in group_ids:
        findings.append("CONTINUITY_GROUP_ID_MISMATCH")

    expected_refs: Dict[str, tuple] = {}
    for manifest in manifests:
        preflight = validate_manifest(manifest)
        findings.extend(preflight.findings)
        for entity in manifest.get("ENTITIES", []):
            if not isinstance(entity, dict) or not entity.get("ENTITY_ID"):
                continue
            entity_id = str(entity["ENTITY_ID"])
            signature = (
                entity.get("REQUIRED_REFERENCE_AUTHORITY"),
                entity.get("ACTUAL_REFERENCE_ASSET"),
                entity.get("CAMPAIGN_VISUAL_ANCHOR_ID"),
            )
            if entity_id in expected_refs and expected_refs[entity_id] != signature:
                findings.append(f"{entity_id}:PANEL_REFERENCE_SWAP")
            expected_refs.setdefault(entity_id, signature)

    return GuardResult("PASS" if not findings else "FAIL", tuple(findings))
