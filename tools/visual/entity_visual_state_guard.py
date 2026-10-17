#!/usr/bin/env python3
"""Fail-closed validator for derived entity visual state and campaign anchors.

Tooling-only. Never reads or mutates Campaign Canon, Runtime, saves, RNG,
Geometry Master, Recovery, or Project Source membership.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


IDENTITY_CLASSES = {
    "PC": "VERY_STRICT",
    "NAMED_RECURRING_NPC": "STRICT",
    "NAMED_RECURRING_MONSTER": "STRICT",
    "UNIQUE_BOSS": "STRICT",
    "STANDARD_MONSTER_SPECIES": "MODERATE",
    "GENERIC_MOB": "LOOSE_WITH_SPECIES_GUARD",
    "BACKGROUND_CROWD": "LOOSE_WITH_SPECIES_GUARD",
}
ANCHOR_ELIGIBLE = {
    "NAMED_RECURRING_NPC",
    "NAMED_RECURRING_MONSTER",
    "UNIQUE_BOSS",
}
MONSTER_ANCHOR_CLASSES = {"NAMED_RECURRING_MONSTER", "UNIQUE_BOSS"}
ALLOWED_ANCHOR_STATUS = {"NONE", "CANDIDATE", "APPROVED"}
ALLOWED_APPROVAL_STATUS = {"PLAYER_APPROVED", "QA_APPROVED"}
UNKNOWNABLE_FIELDS = {
    "CURRENT_VISIBLE_EQUIPMENT",
    "CURRENT_VISIBLE_WOUNDS_OR_MARKS",
    "CURRENT_VISIBLE_EFFECTS",
    "CURRENT_VISIBLE_TRANSFORMATION",
}
UNKNOWN_SENTINEL = {"VISIBILITY_STATE": "UNKNOWN"}

REQUIRED_STATE_FIELDS = {
    "ENTITY_ID",
    "ENTITY_CLASS",
    "IDENTITY_LOCK_LEVEL",
    "IDENTITY_AUTHORITY_ID",
    "IDENTITY_REFERENCE_ASSET",
    "CURRENT_FORM",
    "CURRENT_VISIBLE_EQUIPMENT",
    "CURRENT_VISIBLE_WOUNDS_OR_MARKS",
    "CURRENT_VISIBLE_EFFECTS",
    "CURRENT_VISIBLE_TRANSFORMATION",
    "SOURCE_STATE_EPOCH",
    "CURRENT_VISIBLE_STATE_SOURCE",
    "OBSERVER_SCOPE",
    "OBSERVER_BRANCH_ID",
    "PLAYER_KNOWLEDGE_PROJECTION_ID",
    "PLAYER_KNOWLEDGE_PROJECTION_STATUS",
    "PLAYER_KNOWLEDGE_PROJECTION_OBSERVER_BRANCH_ID",
    "PLAYER_KNOWLEDGE_PROJECTION_SOURCE_STATE_EPOCH",
    "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID",
    "KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS",
    "UNKNOWN_VISIBLE_FIELDS",
    "UNKNOWN_POLICY",
    "STATE_AUTHORITY",
    "PROJECT_SOURCE_SLOT_DELTA",
    "CAMPAIGN_ANCHOR_STATUS",
}

REQUIRED_PROMOTION_FIELDS = {
    "ENTITY_ID",
    "ENTITY_CLASS",
    "IDENTITY_AUTHORITY_ID",
    "ANCHOR_ID",
    "ANCHOR_ASSET",
    "SOURCE_RENDER_ID",
    "SOURCE_STATE_EPOCH",
    "FORM_SCOPE",
    "VISUAL_IDENTITY_LOCK_RECEIPT_STATUS",
    "APPROVAL_STATUS",
    "PROMOTION_RECEIPT_ID",
    "PROMOTION_RECEIPT_STATUS",
    "ANCHOR_LIFECYCLE_STATUS",
    "ANCHOR_IS_GAMEPLAY_CANON",
    "ANCHOR_OVERRIDES_SPECIES_AUTHORITY",
    "ANCHOR_OVERRIDES_CURRENT_FORM",
    "ANCHOR_OVERRIDES_RUNTIME_EQUIPMENT",
    "ANCHOR_OVERRIDES_MECHANICS",
    "ANCHOR_OVERRIDES_PLAYER_KNOWLEDGE",
    "PROJECT_SOURCE_SLOT_DELTA",
}


@dataclass(frozen=True)
class GuardResult:
    status: str
    findings: Sequence[str]

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def _missing(record: Mapping[str, object], required: set[str]) -> list[str]:
    return sorted(key for key in required if key not in record)


def _is_unknown(value: object) -> bool:
    return value == UNKNOWN_SENTINEL


def validate_entity_visual_state(state: Mapping[str, object]) -> GuardResult:
    findings: list[str] = []
    missing = _missing(state, REQUIRED_STATE_FIELDS)
    findings.extend(f"MISSING_{field}" for field in missing)
    if missing:
        return GuardResult("FAIL", tuple(findings))

    entity_id = str(state.get("ENTITY_ID"))
    entity_class = str(state.get("ENTITY_CLASS"))
    lock_level = str(state.get("IDENTITY_LOCK_LEVEL"))

    if entity_class not in IDENTITY_CLASSES:
        findings.append(f"{entity_id}:UNKNOWN_ENTITY_CLASS")
    elif lock_level != IDENTITY_CLASSES[entity_class]:
        findings.append(f"{entity_id}:WRONG_IDENTITY_LOCK_LEVEL")

    if not state.get("IDENTITY_AUTHORITY_ID") or not state.get("IDENTITY_REFERENCE_ASSET"):
        findings.append(f"{entity_id}:IDENTITY_AUTHORITY_REQUIRED")
    if not state.get("CURRENT_FORM"):
        findings.append(f"{entity_id}:CURRENT_FORM_REQUIRED")
    if not state.get("SOURCE_STATE_EPOCH"):
        findings.append(f"{entity_id}:SOURCE_STATE_EPOCH_REQUIRED")
    if state.get("CURRENT_VISIBLE_STATE_SOURCE") != "COMMITTED_RUNTIME_OR_SAVE":
        findings.append(f"{entity_id}:VISIBLE_STATE_NOT_COMMITTED")

    # Player-safety is receipt-bound, never self-asserted by a label alone.
    if state.get("OBSERVER_SCOPE") != "PLAYER_SAFE":
        findings.append(f"{entity_id}:PLAYER_SAFE_OBSERVER_SCOPE_REQUIRED")
    if not state.get("OBSERVER_BRANCH_ID"):
        findings.append(f"{entity_id}:OBSERVER_BRANCH_ID_REQUIRED")
    if not state.get("PLAYER_KNOWLEDGE_PROJECTION_ID"):
        findings.append(f"{entity_id}:PKP_ID_REQUIRED")
    if state.get("PLAYER_KNOWLEDGE_PROJECTION_STATUS") != "MATERIALIZED":
        findings.append(f"{entity_id}:PKP_MATERIALIZED_RECEIPT_REQUIRED")
    if state.get("PLAYER_KNOWLEDGE_PROJECTION_OBSERVER_BRANCH_ID") != state.get("OBSERVER_BRANCH_ID"):
        findings.append(f"{entity_id}:PKP_OBSERVER_BRANCH_MISMATCH")
    if state.get("PLAYER_KNOWLEDGE_PROJECTION_SOURCE_STATE_EPOCH") != state.get("SOURCE_STATE_EPOCH"):
        findings.append(f"{entity_id}:PKP_STATE_EPOCH_MISMATCH")
    if not state.get("KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID"):
        findings.append(f"{entity_id}:LEAK_GATE_RECEIPT_ID_REQUIRED")
    if state.get("KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS") != "PASS":
        findings.append(f"{entity_id}:LEAK_GATE_PASS_REQUIRED")

    if state.get("UNKNOWN_POLICY") != "PRESERVE_UNKNOWN_NO_INVENTION":
        findings.append(f"{entity_id}:UNKNOWN_POLICY_INVALID")
    if state.get("STATE_AUTHORITY") != "DERIVED_NONAUTHORITATIVE":
        findings.append(f"{entity_id}:STATE_AUTHORITY_INVALID")
    if state.get("PROJECT_SOURCE_SLOT_DELTA") != 0:
        findings.append(f"{entity_id}:PROJECT_SOURCE_SLOT_DELTA_MUST_BE_ZERO")

    unknown_fields = state.get("UNKNOWN_VISIBLE_FIELDS")
    if not isinstance(unknown_fields, list):
        findings.append(f"{entity_id}:UNKNOWN_VISIBLE_FIELDS_MUST_BE_LIST")
        unknown_fields = []
    else:
        unknown_set = set(unknown_fields)
        unknown_bad = sorted(unknown_set - UNKNOWNABLE_FIELDS)
        for field in unknown_bad:
            findings.append(f"{entity_id}:UNKNOWN_VISIBLE_FIELD_NOT_ALLOWED:{field}")
        if len(unknown_set) != len(unknown_fields):
            findings.append(f"{entity_id}:UNKNOWN_VISIBLE_FIELDS_DUPLICATED")

        for field in UNKNOWNABLE_FIELDS:
            value = state.get(field)
            if field in unknown_set:
                if not _is_unknown(value):
                    findings.append(f"{entity_id}:{field}_UNKNOWN_REQUIRES_NEUTRAL_SENTINEL")
            elif _is_unknown(value):
                findings.append(f"{entity_id}:{field}_UNKNOWN_SENTINEL_REQUIRES_DECLARATION")

    for list_field in (
        "CURRENT_VISIBLE_EQUIPMENT",
        "CURRENT_VISIBLE_WOUNDS_OR_MARKS",
        "CURRENT_VISIBLE_EFFECTS",
    ):
        value = state.get(list_field)
        if not _is_unknown(value) and not isinstance(value, list):
            findings.append(f"{entity_id}:{list_field}_MUST_BE_LIST_OR_UNKNOWN")

    anchor_status = str(state.get("CAMPAIGN_ANCHOR_STATUS"))
    if anchor_status not in ALLOWED_ANCHOR_STATUS:
        findings.append(f"{entity_id}:UNKNOWN_ANCHOR_STATUS")
    elif anchor_status == "APPROVED":
        if entity_class not in ANCHOR_ELIGIBLE:
            findings.append(f"{entity_id}:APPROVED_ANCHOR_CLASS_INELIGIBLE")
        if not state.get("CAMPAIGN_VISUAL_ANCHOR_ID"):
            findings.append(f"{entity_id}:APPROVED_ANCHOR_ID_REQUIRED")
        if not state.get("CAMPAIGN_VISUAL_ANCHOR_ASSET"):
            findings.append(f"{entity_id}:APPROVED_ANCHOR_ASSET_REQUIRED")
        if not state.get("CAMPAIGN_VISUAL_ANCHOR_PROMOTION_RECEIPT_ID"):
            findings.append(f"{entity_id}:APPROVED_ANCHOR_PROMOTION_RECEIPT_ID_REQUIRED")
        if state.get("CAMPAIGN_VISUAL_ANCHOR_PROMOTION_RECEIPT_STATUS") != "PASS":
            findings.append(f"{entity_id}:APPROVED_ANCHOR_PROMOTION_RECEIPT_PASS_REQUIRED")
        form_scope = state.get("CAMPAIGN_VISUAL_ANCHOR_FORM_SCOPE")
        if not isinstance(form_scope, list) or not form_scope:
            findings.append(f"{entity_id}:APPROVED_ANCHOR_FORM_SCOPE_REQUIRED")
        elif state.get("CURRENT_FORM") not in form_scope:
            findings.append(f"{entity_id}:ANCHOR_FORM_SCOPE_MISMATCH")
        if state.get("ANCHOR_OVERRIDES_SPECIES_AUTHORITY") is not False:
            findings.append(f"{entity_id}:ANCHOR_CANNOT_OVERRIDE_SPECIES")
        if state.get("ANCHOR_OVERRIDES_CURRENT_FORM") is not False:
            findings.append(f"{entity_id}:ANCHOR_CANNOT_OVERRIDE_FORM")
        if state.get("ANCHOR_OVERRIDES_RUNTIME_EQUIPMENT") is not False:
            findings.append(f"{entity_id}:ANCHOR_CANNOT_OVERRIDE_EQUIPMENT")
        if state.get("ANCHOR_OVERRIDES_PLAYER_KNOWLEDGE") is not False:
            findings.append(f"{entity_id}:ANCHOR_CANNOT_OVERRIDE_KNOWLEDGE")

    return GuardResult("PASS" if not findings else "FAIL", tuple(findings))


def validate_anchor_promotion(record: Mapping[str, object]) -> GuardResult:
    findings: list[str] = []
    missing = _missing(record, REQUIRED_PROMOTION_FIELDS)
    findings.extend(f"MISSING_{field}" for field in missing)
    if missing:
        return GuardResult("FAIL", tuple(findings))

    entity_id = str(record.get("ENTITY_ID"))
    entity_class = str(record.get("ENTITY_CLASS"))
    if entity_class not in IDENTITY_CLASSES:
        findings.append(f"{entity_id}:UNKNOWN_ENTITY_CLASS")
    elif entity_class not in ANCHOR_ELIGIBLE:
        findings.append(f"{entity_id}:ANCHOR_CLASS_INELIGIBLE")

    if not record.get("IDENTITY_AUTHORITY_ID"):
        findings.append(f"{entity_id}:IDENTITY_AUTHORITY_REQUIRED")
    if not record.get("ANCHOR_ID") or not record.get("ANCHOR_ASSET"):
        findings.append(f"{entity_id}:ANCHOR_ASSET_REQUIRED")
    if not record.get("SOURCE_RENDER_ID") or not record.get("SOURCE_STATE_EPOCH"):
        findings.append(f"{entity_id}:ANCHOR_PROVENANCE_REQUIRED")

    form_scope = record.get("FORM_SCOPE")
    if not isinstance(form_scope, list) or not form_scope:
        findings.append(f"{entity_id}:FORM_SCOPE_REQUIRED")

    if record.get("VISUAL_IDENTITY_LOCK_RECEIPT_STATUS") != "PASS":
        findings.append(f"{entity_id}:VIL_PASS_REQUIRED")
    if record.get("APPROVAL_STATUS") not in ALLOWED_APPROVAL_STATUS:
        findings.append(f"{entity_id}:EXPLICIT_APPROVAL_REQUIRED")
    if not record.get("PROMOTION_RECEIPT_ID"):
        findings.append(f"{entity_id}:PROMOTION_RECEIPT_ID_REQUIRED")
    if record.get("PROMOTION_RECEIPT_STATUS") != "PASS":
        findings.append(f"{entity_id}:PROMOTION_RECEIPT_PASS_REQUIRED")
    if record.get("ANCHOR_LIFECYCLE_STATUS") != "APPROVED":
        findings.append(f"{entity_id}:ANCHOR_LIFECYCLE_NOT_APPROVED")

    if entity_class in MONSTER_ANCHOR_CLASSES and not record.get("OFFICIAL_SPECIES_OR_VARIANT_AUTHORITY_ID"):
        findings.append(f"{entity_id}:MONSTER_SPECIES_AUTHORITY_REQUIRED")

    if record.get("ANCHOR_IS_GAMEPLAY_CANON") is not False:
        findings.append(f"{entity_id}:ANCHOR_MUST_NOT_BE_GAMEPLAY_CANON")
    for field, code in (
        ("ANCHOR_OVERRIDES_SPECIES_AUTHORITY", "ANCHOR_CANNOT_OVERRIDE_SPECIES"),
        ("ANCHOR_OVERRIDES_CURRENT_FORM", "ANCHOR_CANNOT_OVERRIDE_FORM"),
        ("ANCHOR_OVERRIDES_RUNTIME_EQUIPMENT", "ANCHOR_CANNOT_OVERRIDE_EQUIPMENT"),
        ("ANCHOR_OVERRIDES_MECHANICS", "ANCHOR_CANNOT_OVERRIDE_MECHANICS"),
        ("ANCHOR_OVERRIDES_PLAYER_KNOWLEDGE", "ANCHOR_CANNOT_OVERRIDE_KNOWLEDGE"),
    ):
        if record.get(field) is not False:
            findings.append(f"{entity_id}:{code}")
    if record.get("PROJECT_SOURCE_SLOT_DELTA") != 0:
        findings.append(f"{entity_id}:PROJECT_SOURCE_SLOT_DELTA_MUST_BE_ZERO")

    return GuardResult("PASS" if not findings else "FAIL", tuple(findings))


def validate_anchor_reuse(anchor: Mapping[str, object], current_state: Mapping[str, object]) -> GuardResult:
    findings: list[str] = []
    state_result = validate_entity_visual_state(current_state)
    findings.extend(state_result.findings)
    entity_id = str(current_state.get("ENTITY_ID", "UNKNOWN"))
    entity_class = str(current_state.get("ENTITY_CLASS", "UNKNOWN"))

    # Reuse is impossible unless the anchor itself still satisfies the exact
    # promotion barrier. This prevents forged/unapproved anchors from bypassing
    # promotion simply by entering through the reuse path.
    promotion_result = validate_anchor_promotion(anchor)
    findings.extend(f"{entity_id}:REUSE_{item}" for item in promotion_result.findings)

    if entity_class not in ANCHOR_ELIGIBLE:
        findings.append(f"{entity_id}:ANCHOR_REUSE_CLASS_INELIGIBLE")
    if current_state.get("CAMPAIGN_ANCHOR_STATUS") != "APPROVED":
        findings.append(f"{entity_id}:CURRENT_STATE_ANCHOR_NOT_APPROVED")

    if anchor.get("ENTITY_ID") != current_state.get("ENTITY_ID"):
        findings.append(f"{entity_id}:ANCHOR_ENTITY_MISMATCH")
    if anchor.get("ENTITY_CLASS") != current_state.get("ENTITY_CLASS"):
        findings.append(f"{entity_id}:ANCHOR_ENTITY_CLASS_MISMATCH")
    if anchor.get("IDENTITY_AUTHORITY_ID") != current_state.get("IDENTITY_AUTHORITY_ID"):
        findings.append(f"{entity_id}:ANCHOR_IDENTITY_LINEAGE_MISMATCH")
    if anchor.get("ANCHOR_ID") != current_state.get("CAMPAIGN_VISUAL_ANCHOR_ID"):
        findings.append(f"{entity_id}:ANCHOR_ID_MISMATCH")
    if anchor.get("ANCHOR_ASSET") != current_state.get("CAMPAIGN_VISUAL_ANCHOR_ASSET"):
        findings.append(f"{entity_id}:ANCHOR_ASSET_MISMATCH")
    if anchor.get("PROMOTION_RECEIPT_ID") != current_state.get("CAMPAIGN_VISUAL_ANCHOR_PROMOTION_RECEIPT_ID"):
        findings.append(f"{entity_id}:ANCHOR_PROMOTION_RECEIPT_MISMATCH")
    if current_state.get("CAMPAIGN_VISUAL_ANCHOR_PROMOTION_RECEIPT_STATUS") != "PASS":
        findings.append(f"{entity_id}:CURRENT_STATE_PROMOTION_RECEIPT_NOT_PASS")

    form_scope = anchor.get("FORM_SCOPE")
    if not isinstance(form_scope, list) or current_state.get("CURRENT_FORM") not in form_scope:
        findings.append(f"{entity_id}:ANCHOR_FORM_SCOPE_MISMATCH")
    if form_scope != current_state.get("CAMPAIGN_VISUAL_ANCHOR_FORM_SCOPE"):
        findings.append(f"{entity_id}:ANCHOR_FORM_SCOPE_RECEIPT_MISMATCH")

    if entity_class in MONSTER_ANCHOR_CLASSES and not anchor.get("OFFICIAL_SPECIES_OR_VARIANT_AUTHORITY_ID"):
        findings.append(f"{entity_id}:MONSTER_SPECIES_AUTHORITY_REQUIRED")

    # Dynamic fields intentionally come from current_state and are not compared
    # against the old anchor snapshot. Equipment/wounds/effects may legitimately
    # change without changing recurring identity.
    return GuardResult("PASS" if not findings else "FAIL", tuple(findings))
