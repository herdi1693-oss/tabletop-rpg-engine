#!/usr/bin/env python3
"""Fail-closed Scene Continuity Lock validator.

Tooling-only. Proof-bearing inputs are resolved through external trusted receipt
registries. Inline PASS/COMMITTED labels are never sufficient authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping, Sequence

SCENE_FACT_CLASSES = {"IMMUTABLE_STRUCTURE", "DYNAMIC_PLAYER_SAFE"}
PRESENTATION_FIELDS = {
    "IN_FRAME_ENTITY_IDS",
    "IN_FRAME_SCENE_FACT_IDS",
    "CAMERA_SHOT_ID",
    "LIGHTING_STYLE_ID",
    "COLOR_GRADE_ID",
}
DYNAMIC_ENTITY_FIELDS = {
    "CURRENT_FORM",
    "CURRENT_VISIBLE_EQUIPMENT",
    "CURRENT_VISIBLE_WOUNDS_OR_MARKS",
    "CURRENT_VISIBLE_EFFECTS",
    "CURRENT_VISIBLE_TRANSFORMATION",
}
ALLOWED_CAUSE_TYPES = {"CAMERA_ONLY", "COMMITTED_GAMEPLAY_EVENT"}
PROOF_REGISTRIES = {
    "PKP_RECEIPTS",
    "LEAK_GATE_RECEIPTS",
    "EVS_RECEIPTS",
    "PLAYER_SAFE_SOURCE_RECEIPTS",
    "APPLIED_EVENT_LEDGER_RECEIPTS",
    "VIL_RECEIPTS",
    "ENTITY_RENDER_RECEIPTS",
    "FACT_RENDER_RECEIPTS",
    "PLAYER_SAFE_RENDER_RECEIPTS",
}
REQUIRED_GROUP_FIELDS = {
    "CONTINUITY_GROUP_ID",
    "OBSERVER_BRANCH_ID",
    "OPENING_STATE_EPOCH",
    "PLAYER_KNOWLEDGE_PROJECTION_ID",
    "PLAYER_KNOWLEDGE_PROJECTION_STATUS",
    "PLAYER_KNOWLEDGE_PROJECTION_OBSERVER_BRANCH_ID",
    "PLAYER_KNOWLEDGE_PROJECTION_SOURCE_STATE_EPOCH",
    "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID",
    "KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS",
    "STATE_AUTHORITY",
    "CANON_DIRECTION",
    "VISUAL_TO_CANON",
    "PROJECT_SOURCE_SLOT_DELTA",
    "ENTITY_BASELINES",
    "SCENE_FACTS",
}
REQUIRED_FRAME_FIELDS = {
    "FRAME_ID",
    "CONTINUITY_GROUP_ID",
    "FRAME_INDEX",
    "PREVIOUS_FRAME_ID",
    "OBSERVER_BRANCH_ID",
    "SOURCE_STATE_EPOCH",
    "PLAYER_KNOWLEDGE_PROJECTION_ID",
    "PLAYER_KNOWLEDGE_PROJECTION_STATUS",
    "PLAYER_KNOWLEDGE_PROJECTION_OBSERVER_BRANCH_ID",
    "PLAYER_KNOWLEDGE_PROJECTION_SOURCE_STATE_EPOCH",
    "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID",
    "KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS",
    "TRACKED_ENTITIES",
    "SCENE_FACTS",
    "IN_FRAME_ENTITY_IDS",
    "IN_FRAME_SCENE_FACT_IDS",
    "CAMERA_SHOT_ID",
    "LIGHTING_STYLE_ID",
    "COLOR_GRADE_ID",
    "VISUAL_MANIFEST_ID",
    "PROJECT_SOURCE_SLOT_DELTA",
}
REQUIRED_POST_RENDER_FIELDS = {
    "FRAME_ID",
    "CONTINUITY_GROUP_ID",
    "RENDER_ARTIFACT_ID",
    "RENDER_ARTIFACT_HASH",
    "VISUAL_MANIFEST_ID",
    "FRAME_STATE_DIGEST",
    "VISUAL_IDENTITY_LOCK_RECEIPT_ID",
    "ENTITY_CONTINUITY_RECEIPT_IDS",
    "SCENE_FACT_CONTINUITY_RECEIPT_IDS",
    "PLAYER_SAFE_CONTENT_RECEIPT_ID",
}
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class GuardResult:
    status: str
    findings: Sequence[str]

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def canonical_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _missing(record: Mapping[str, object], required: set[str]) -> list[str]:
    return sorted(k for k in required if k not in record)


def _result(findings: list[str]) -> GuardResult:
    return GuardResult("PASS" if not findings else "FAIL", tuple(findings))


def _registry(proofs: object, name: str, prefix: str, findings: list[str]) -> Mapping[str, object]:
    if not isinstance(proofs, Mapping):
        findings.append(f"{prefix}:PROOF_BUNDLE_REQUIRED")
        return {}
    registry = proofs.get(name)
    if not isinstance(registry, Mapping):
        findings.append(f"{prefix}:{name}_REGISTRY_REQUIRED")
        return {}
    return registry


def _external_receipt(
    proofs: object,
    registry_name: str,
    receipt_id: object,
    prefix: str,
    findings: list[str],
) -> Mapping[str, object] | None:
    if not receipt_id:
        findings.append(f"{prefix}:RECEIPT_ID_REQUIRED")
        return None
    registry = _registry(proofs, registry_name, prefix, findings)
    receipt = registry.get(str(receipt_id))
    if not isinstance(receipt, Mapping):
        findings.append(f"{prefix}:{registry_name}_RECEIPT_NOT_FOUND:{receipt_id}")
        return None
    if receipt.get("RECEIPT_ID") != receipt_id:
        findings.append(f"{prefix}:RECEIPT_ID_BINDING_MISMATCH")
    return receipt


def _context(record: Mapping[str, object], epoch_field: str) -> dict[str, object]:
    return {
        "PKP_ID": record.get("PLAYER_KNOWLEDGE_PROJECTION_ID"),
        "BRANCH_ID": record.get("OBSERVER_BRANCH_ID"),
        "STATE_EPOCH": record.get(epoch_field),
    }


def _validate_player_safe(
    record: Mapping[str, object],
    epoch_field: str,
    prefix: str,
    proofs: object,
) -> list[str]:
    findings: list[str] = []
    branch = record.get("OBSERVER_BRANCH_ID")
    epoch = record.get(epoch_field)
    pkp_id = record.get("PLAYER_KNOWLEDGE_PROJECTION_ID")
    leak_id = record.get("KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID")

    if not branch:
        findings.append(f"{prefix}:OBSERVER_BRANCH_ID_REQUIRED")
    if not epoch:
        findings.append(f"{prefix}:STATE_EPOCH_REQUIRED")
    if not pkp_id:
        findings.append(f"{prefix}:PKP_ID_REQUIRED")
    if record.get("PLAYER_KNOWLEDGE_PROJECTION_STATUS") != "MATERIALIZED":
        findings.append(f"{prefix}:PKP_MATERIALIZED_REQUIRED")
    if record.get("PLAYER_KNOWLEDGE_PROJECTION_OBSERVER_BRANCH_ID") != branch:
        findings.append(f"{prefix}:PKP_OBSERVER_BRANCH_MISMATCH")
    if record.get("PLAYER_KNOWLEDGE_PROJECTION_SOURCE_STATE_EPOCH") != epoch:
        findings.append(f"{prefix}:PKP_STATE_EPOCH_MISMATCH")
    if not leak_id:
        findings.append(f"{prefix}:LEAK_GATE_RECEIPT_ID_REQUIRED")
    if record.get("KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS") != "PASS":
        findings.append(f"{prefix}:LEAK_GATE_PASS_REQUIRED")

    pkp_receipt = _external_receipt(proofs, "PKP_RECEIPTS", pkp_id, f"{prefix}:PKP", findings)
    if pkp_receipt:
        if pkp_receipt.get("STATUS") != "MATERIALIZED":
            findings.append(f"{prefix}:PKP_EXTERNAL_STATUS_INVALID")
        if pkp_receipt.get("PLAYER_KNOWLEDGE_PROJECTION_ID") != pkp_id:
            findings.append(f"{prefix}:PKP_EXTERNAL_ID_MISMATCH")
        if pkp_receipt.get("OBSERVER_BRANCH_ID") != branch:
            findings.append(f"{prefix}:PKP_EXTERNAL_BRANCH_MISMATCH")
        if pkp_receipt.get("SOURCE_STATE_EPOCH") != epoch:
            findings.append(f"{prefix}:PKP_EXTERNAL_EPOCH_MISMATCH")
        if not pkp_receipt.get("PROJECTION_DIGEST"):
            findings.append(f"{prefix}:PKP_PROJECTION_DIGEST_REQUIRED")

    leak_receipt = _external_receipt(proofs, "LEAK_GATE_RECEIPTS", leak_id, f"{prefix}:LEAK", findings)
    if leak_receipt:
        if leak_receipt.get("STATUS") != "PASS":
            findings.append(f"{prefix}:LEAK_EXTERNAL_STATUS_NOT_PASS")
        if leak_receipt.get("PLAYER_KNOWLEDGE_PROJECTION_ID") != pkp_id:
            findings.append(f"{prefix}:LEAK_PKP_BINDING_MISMATCH")
        if leak_receipt.get("OBSERVER_BRANCH_ID") != branch:
            findings.append(f"{prefix}:LEAK_BRANCH_BINDING_MISMATCH")
        if leak_receipt.get("SOURCE_STATE_EPOCH") != epoch:
            findings.append(f"{prefix}:LEAK_EPOCH_BINDING_MISMATCH")
    return findings


def entity_state_digest(entity: Mapping[str, object]) -> str:
    payload = {
        "ENTITY_ID": entity.get("ENTITY_ID"),
        "ENTITY_CLASS": entity.get("ENTITY_CLASS"),
        "IDENTITY_AUTHORITY_ID": entity.get("IDENTITY_AUTHORITY_ID"),
        "CAMPAIGN_VISUAL_ANCHOR_ID": entity.get("CAMPAIGN_VISUAL_ANCHOR_ID"),
        "DYNAMIC_STATE": {key: entity.get(key) for key in sorted(DYNAMIC_ENTITY_FIELDS)},
    }
    return canonical_digest(payload)


def fact_value_digest(fact: Mapping[str, object]) -> str:
    return canonical_digest({
        "FACT_ID": fact.get("FACT_ID"),
        "FACT_CLASS": fact.get("FACT_CLASS"),
        "VALUE": fact.get("VALUE"),
    })


def _entity_map(
    items: object,
    prefix: str,
    context: Mapping[str, object] | None = None,
    proofs: object = None,
) -> tuple[dict[str, Mapping[str, object]], list[str]]:
    findings: list[str] = []
    if not isinstance(items, list):
        return {}, [f"{prefix}:TRACKED_ENTITIES_MUST_BE_LIST"]
    out: dict[str, Mapping[str, object]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            findings.append(f"{prefix}:ENTITY_RECORD_INVALID")
            continue
        entity_id = item.get("ENTITY_ID")
        if not entity_id:
            findings.append(f"{prefix}:ENTITY_ID_REQUIRED")
            continue
        entity_id = str(entity_id)
        if entity_id in out:
            findings.append(f"{prefix}:DUPLICATE_ENTITY_ID:{entity_id}")
            continue
        for key in ("ENTITY_CLASS", "IDENTITY_AUTHORITY_ID", "EVS_VALIDATION_RECEIPT_ID"):
            if not item.get(key):
                findings.append(f"{prefix}:{entity_id}:{key}_REQUIRED")
        for key in DYNAMIC_ENTITY_FIELDS:
            if key not in item:
                findings.append(f"{prefix}:{entity_id}:{key}_REQUIRED")

        if context is not None:
            rid = item.get("EVS_VALIDATION_RECEIPT_ID")
            receipt = _external_receipt(
                proofs, "EVS_RECEIPTS", rid, f"{prefix}:{entity_id}:EVS", findings
            )
            if receipt:
                if receipt.get("STATUS") != "PASS":
                    findings.append(f"{prefix}:{entity_id}:EVS_EXTERNAL_STATUS_NOT_PASS")
                if receipt.get("ENTITY_ID") != entity_id:
                    findings.append(f"{prefix}:{entity_id}:EVS_ENTITY_BINDING_MISMATCH")
                if receipt.get("ENTITY_CLASS") != item.get("ENTITY_CLASS"):
                    findings.append(f"{prefix}:{entity_id}:EVS_CLASS_BINDING_MISMATCH")
                if receipt.get("IDENTITY_AUTHORITY_ID") != item.get("IDENTITY_AUTHORITY_ID"):
                    findings.append(f"{prefix}:{entity_id}:EVS_IDENTITY_BINDING_MISMATCH")
                if receipt.get("PLAYER_KNOWLEDGE_PROJECTION_ID") != context.get("PKP_ID"):
                    findings.append(f"{prefix}:{entity_id}:EVS_PKP_BINDING_MISMATCH")
                if receipt.get("OBSERVER_BRANCH_ID") != context.get("BRANCH_ID"):
                    findings.append(f"{prefix}:{entity_id}:EVS_BRANCH_BINDING_MISMATCH")
                if receipt.get("SOURCE_STATE_EPOCH") != context.get("STATE_EPOCH"):
                    findings.append(f"{prefix}:{entity_id}:EVS_EPOCH_BINDING_MISMATCH")
                if receipt.get("ENTITY_STATE_DIGEST") != entity_state_digest(item):
                    findings.append(f"{prefix}:{entity_id}:EVS_STATE_DIGEST_MISMATCH")
        out[entity_id] = item
    return out, findings


def _fact_map(
    items: object,
    prefix: str,
    context: Mapping[str, object] | None = None,
    proofs: object = None,
) -> tuple[dict[str, Mapping[str, object]], list[str]]:
    findings: list[str] = []
    if not isinstance(items, list):
        return {}, [f"{prefix}:SCENE_FACTS_MUST_BE_LIST"]
    out: dict[str, Mapping[str, object]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            findings.append(f"{prefix}:SCENE_FACT_RECORD_INVALID")
            continue
        fact_id = item.get("FACT_ID")
        if not fact_id:
            findings.append(f"{prefix}:FACT_ID_REQUIRED")
            continue
        fact_id = str(fact_id)
        if fact_id in out:
            findings.append(f"{prefix}:DUPLICATE_FACT_ID:{fact_id}")
            continue
        fact_class = item.get("FACT_CLASS")
        if fact_class not in SCENE_FACT_CLASSES:
            findings.append(f"{prefix}:{fact_id}:UNKNOWN_SCENE_FACT_CLASS")
        if "VALUE" not in item:
            findings.append(f"{prefix}:{fact_id}:VALUE_REQUIRED")
        if not item.get("SOURCE_RECEIPT_ID"):
            findings.append(f"{prefix}:{fact_id}:SOURCE_RECEIPT_ID_REQUIRED")

        if context is not None:
            receipt = _external_receipt(
                proofs,
                "PLAYER_SAFE_SOURCE_RECEIPTS",
                item.get("SOURCE_RECEIPT_ID"),
                f"{prefix}:{fact_id}:SOURCE",
                findings,
            )
            if receipt:
                if receipt.get("STATUS") != "PASS":
                    findings.append(f"{prefix}:{fact_id}:SOURCE_EXTERNAL_STATUS_NOT_PASS")
                if receipt.get("FACT_ID") != fact_id:
                    findings.append(f"{prefix}:{fact_id}:SOURCE_FACT_BINDING_MISMATCH")
                if receipt.get("FACT_CLASS") != fact_class:
                    findings.append(f"{prefix}:{fact_id}:SOURCE_CLASS_BINDING_MISMATCH")
                if receipt.get("VALUE_DIGEST") != fact_value_digest(item):
                    findings.append(f"{prefix}:{fact_id}:SOURCE_VALUE_DIGEST_MISMATCH")
                if receipt.get("PLAYER_KNOWLEDGE_PROJECTION_ID") != context.get("PKP_ID"):
                    findings.append(f"{prefix}:{fact_id}:SOURCE_PKP_BINDING_MISMATCH")
                if receipt.get("OBSERVER_BRANCH_ID") != context.get("BRANCH_ID"):
                    findings.append(f"{prefix}:{fact_id}:SOURCE_BRANCH_BINDING_MISMATCH")
                if receipt.get("SOURCE_STATE_EPOCH") != context.get("STATE_EPOCH"):
                    findings.append(f"{prefix}:{fact_id}:SOURCE_EPOCH_BINDING_MISMATCH")
                source_kind = receipt.get("SOURCE_KIND")
                if fact_class == "IMMUTABLE_STRUCTURE":
                    if source_kind != "PLAYER_SAFE_STRUCTURE_PACKAGE":
                        findings.append(f"{prefix}:{fact_id}:STRUCTURE_SOURCE_KIND_INVALID")
                    if not receipt.get("PLAYER_SAFE_STRUCTURE_PACKAGE_ID"):
                        findings.append(f"{prefix}:{fact_id}:PSSP_ID_REQUIRED")
                    if not receipt.get("GEOMETRY_LOCK_ID"):
                        findings.append(f"{prefix}:{fact_id}:GEOMETRY_LOCK_ID_REQUIRED")
                    if receipt.get("GEOMETRY_LOCK_STATUS") != "PASS":
                        findings.append(f"{prefix}:{fact_id}:GEOMETRY_LOCK_PASS_REQUIRED")
                elif source_kind != "PLAYER_KNOWLEDGE_PROJECTION":
                    findings.append(f"{prefix}:{fact_id}:DYNAMIC_SOURCE_KIND_INVALID")
        out[fact_id] = item
    return out, findings


def frame_state_digest(frame: Mapping[str, object]) -> str:
    entities, _ = _entity_map(frame.get("TRACKED_ENTITIES"), "DIGEST")
    facts, _ = _fact_map(frame.get("SCENE_FACTS"), "DIGEST")
    payload = {
        "FRAME_ID": frame.get("FRAME_ID"),
        "CONTINUITY_GROUP_ID": frame.get("CONTINUITY_GROUP_ID"),
        "SOURCE_STATE_EPOCH": frame.get("SOURCE_STATE_EPOCH"),
        "PLAYER_KNOWLEDGE_PROJECTION_ID": frame.get("PLAYER_KNOWLEDGE_PROJECTION_ID"),
        "OBSERVER_BRANCH_ID": frame.get("OBSERVER_BRANCH_ID"),
        "VISUAL_MANIFEST_ID": frame.get("VISUAL_MANIFEST_ID"),
        "ENTITIES": {k: entity_state_digest(v) for k, v in sorted(entities.items())},
        "FACTS": {k: fact_value_digest(v) for k, v in sorted(facts.items())},
        "IN_FRAME_ENTITY_IDS": frame.get("IN_FRAME_ENTITY_IDS"),
        "IN_FRAME_SCENE_FACT_IDS": frame.get("IN_FRAME_SCENE_FACT_IDS"),
        "CAMERA_SHOT_ID": frame.get("CAMERA_SHOT_ID"),
        "LIGHTING_STYLE_ID": frame.get("LIGHTING_STYLE_ID"),
        "COLOR_GRADE_ID": frame.get("COLOR_GRADE_ID"),
    }
    return canonical_digest(payload)


def validate_continuity_group(group: Mapping[str, object], proofs: object = None) -> GuardResult:
    findings: list[str] = []
    missing = _missing(group, REQUIRED_GROUP_FIELDS)
    findings.extend(f"GROUP:MISSING_{k}" for k in missing)
    if missing:
        return _result(findings)
    findings.extend(_validate_player_safe(group, "OPENING_STATE_EPOCH", "GROUP", proofs))
    if group.get("STATE_AUTHORITY") != "DERIVED_NONAUTHORITATIVE":
        findings.append("GROUP:STATE_AUTHORITY_INVALID")
    if group.get("CANON_DIRECTION") != "CANON_TO_VISUAL_ONLY" or group.get("VISUAL_TO_CANON") is not False:
        findings.append("GROUP:CANON_DIRECTION_INVALID")
    if group.get("PROJECT_SOURCE_SLOT_DELTA") != 0:
        findings.append("GROUP:PROJECT_SOURCE_SLOT_DELTA_MUST_BE_ZERO")
    ctx = _context(group, "OPENING_STATE_EPOCH")
    _, entity_findings = _entity_map(group.get("ENTITY_BASELINES"), "GROUP", ctx, proofs)
    _, fact_findings = _fact_map(group.get("SCENE_FACTS"), "GROUP", ctx, proofs)
    findings.extend(entity_findings)
    findings.extend(fact_findings)
    return _result(findings)


def validate_frame(frame: Mapping[str, object], proofs: object = None) -> GuardResult:
    findings: list[str] = []
    missing = _missing(frame, REQUIRED_FRAME_FIELDS)
    prefix = str(frame.get("FRAME_ID", "FRAME"))
    findings.extend(f"{prefix}:MISSING_{k}" for k in missing)
    if missing:
        return _result(findings)
    findings.extend(_validate_player_safe(frame, "SOURCE_STATE_EPOCH", prefix, proofs))
    if frame.get("PROJECT_SOURCE_SLOT_DELTA") != 0:
        findings.append(f"{prefix}:PROJECT_SOURCE_SLOT_DELTA_MUST_BE_ZERO")
    if not isinstance(frame.get("FRAME_INDEX"), int) or int(frame.get("FRAME_INDEX")) < 0:
        findings.append(f"{prefix}:FRAME_INDEX_INVALID")
    if not frame.get("VISUAL_MANIFEST_ID"):
        findings.append(f"{prefix}:VISUAL_MANIFEST_ID_REQUIRED")

    ctx = _context(frame, "SOURCE_STATE_EPOCH")
    entities, entity_findings = _entity_map(frame.get("TRACKED_ENTITIES"), prefix, ctx, proofs)
    facts, fact_findings = _fact_map(frame.get("SCENE_FACTS"), prefix, ctx, proofs)
    findings.extend(entity_findings)
    findings.extend(fact_findings)

    for field, allowed in (("IN_FRAME_ENTITY_IDS", set(entities)), ("IN_FRAME_SCENE_FACT_IDS", set(facts))):
        value = frame.get(field)
        if not isinstance(value, list):
            findings.append(f"{prefix}:{field}_MUST_BE_LIST")
            continue
        if len(value) != len(set(value)):
            findings.append(f"{prefix}:{field}_DUPLICATE_ID")
        unknown = sorted(set(value) - allowed)
        if unknown:
            findings.append(f"{prefix}:{field}_UNTRACKED:{','.join(map(str, unknown))}")

    for field in ("CAMERA_SHOT_ID", "LIGHTING_STYLE_ID", "COLOR_GRADE_ID"):
        if not frame.get(field):
            findings.append(f"{prefix}:{field}_REQUIRED")
    return _result(findings)


def _raw_entity_map(items: object) -> dict[str, Mapping[str, object]]:
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("ENTITY_ID")): item
        for item in items
        if isinstance(item, Mapping) and item.get("ENTITY_ID")
    }


def _raw_fact_map(items: object) -> dict[str, Mapping[str, object]]:
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("FACT_ID")): item
        for item in items
        if isinstance(item, Mapping) and item.get("FACT_ID")
    }


def _gameplay_changes(
    previous: Mapping[str, object], current: Mapping[str, object]
) -> tuple[dict[str, dict[str, object]], list[str]]:
    findings: list[str] = []
    changes: dict[str, dict[str, object]] = {}
    prev_entities = _raw_entity_map(previous.get("TRACKED_ENTITIES"))
    cur_entities = _raw_entity_map(current.get("TRACKED_ENTITIES"))

    for entity_id in sorted(set(prev_entities) | set(cur_entities)):
        if entity_id not in prev_entities or entity_id not in cur_entities:
            changes[f"TRACKED_ENTITY:{entity_id}:ENTER_EXIT"] = {
                "BEFORE": None if entity_id not in prev_entities else entity_state_digest(prev_entities[entity_id]),
                "AFTER": None if entity_id not in cur_entities else entity_state_digest(cur_entities[entity_id]),
            }
            continue
        p = prev_entities[entity_id]
        c = cur_entities[entity_id]
        if p.get("IDENTITY_AUTHORITY_ID") != c.get("IDENTITY_AUTHORITY_ID"):
            findings.append(f"{entity_id}:IDENTITY_AUTHORITY_DRIFT")
        if p.get("CAMPAIGN_VISUAL_ANCHOR_ID") != c.get("CAMPAIGN_VISUAL_ANCHOR_ID"):
            findings.append(f"{entity_id}:CAMPAIGN_ANCHOR_DRIFT")
        for field in sorted(DYNAMIC_ENTITY_FIELDS):
            if p.get(field) != c.get(field):
                changes[f"ENTITY:{entity_id}:{field}"] = {
                    "BEFORE": p.get(field),
                    "AFTER": c.get(field),
                }

    prev_facts = _raw_fact_map(previous.get("SCENE_FACTS"))
    cur_facts = _raw_fact_map(current.get("SCENE_FACTS"))
    if set(prev_facts) != set(cur_facts):
        findings.append("SCENE_FACT_SET_CHANGED_WITHIN_GROUP")
    for fact_id in sorted(set(prev_facts) & set(cur_facts)):
        p = prev_facts[fact_id]
        c = cur_facts[fact_id]
        if p.get("FACT_CLASS") != c.get("FACT_CLASS"):
            findings.append(f"{fact_id}:SCENE_FACT_CLASS_DRIFT")
        if p.get("VALUE") != c.get("VALUE"):
            if p.get("FACT_CLASS") == "IMMUTABLE_STRUCTURE":
                findings.append(f"{fact_id}:IMMUTABLE_STRUCTURE_CHANGED")
            else:
                changes[f"SCENE_FACT:{fact_id}:VALUE"] = {
                    "BEFORE": p.get("VALUE"),
                    "AFTER": c.get("VALUE"),
                }
    return changes, findings


def _presentation_change_keys(previous: Mapping[str, object], current: Mapping[str, object]) -> set[str]:
    return {
        f"PRESENTATION:{field}"
        for field in PRESENTATION_FIELDS
        if previous.get(field) != current.get(field)
    }


def _validate_applied_event_receipt(
    cause: Mapping[str, object],
    previous: Mapping[str, object],
    current: Mapping[str, object],
    expected_changes: Mapping[str, dict[str, object]],
    proofs: object,
    prefix: str,
    findings: list[str],
) -> set[str]:
    if "EVENT_COMMIT_STATUS" in cause or "APPLIED_EVENT_LEDGER_RECEIPT_STATUS" in cause:
        findings.append(f"{prefix}:SELF_ASSERTED_EVENT_STATUS_FORBIDDEN")
    event_id = cause.get("EVENT_ID")
    receipt_id = cause.get("APPLIED_EVENT_LEDGER_RECEIPT_ID")
    affected = cause.get("AFFECTED_KEYS")
    if not event_id:
        findings.append(f"{prefix}:EVENT_ID_REQUIRED")
    if not isinstance(affected, list) or len(affected) != len(set(affected)):
        findings.append(f"{prefix}:COMMITTED_GAMEPLAY_EVENT_AFFECTED_KEYS_INVALID")
        return set()
    affected_set = set(map(str, affected))
    invalid = sorted(
        k for k in affected_set
        if not (k.startswith("ENTITY:") or k.startswith("SCENE_FACT:") or k.startswith("TRACKED_ENTITY:"))
    )
    if invalid:
        findings.append(f"{prefix}:UNKNOWN_GAMEPLAY_CHANGE_KEY:{','.join(invalid)}")

    external = _external_receipt(
        proofs,
        "APPLIED_EVENT_LEDGER_RECEIPTS",
        receipt_id,
        f"{prefix}:APPLIED_EVENT",
        findings,
    )
    if not external:
        return affected_set

    if external.get("AUTHORITY") != "APPLIED_EVENT_LEDGER":
        findings.append(f"{prefix}:APPLIED_RECEIPT_AUTHORITY_INVALID")
    if external.get("STATUS") != "PASS" or external.get("COMMIT_STATUS") != "COMMITTED":
        findings.append(f"{prefix}:APPLIED_RECEIPT_NOT_COMMITTED")
    if external.get("EVENT_ID") != event_id:
        findings.append(f"{prefix}:APPLIED_RECEIPT_EVENT_ID_MISMATCH")
    if not external.get("TRANSACTION_RECEIPT_ID"):
        findings.append(f"{prefix}:TRANSACTION_RECEIPT_ID_REQUIRED")
    if not isinstance(external.get("LOGICAL_COMMIT_INDEX"), int) or external.get("LOGICAL_COMMIT_INDEX") < 0:
        findings.append(f"{prefix}:LOGICAL_COMMIT_INDEX_INVALID")
    if external.get("APPLIED_EVENT_LEDGER_CONTAINS_EVENT") is not True:
        findings.append(f"{prefix}:APPLIED_LEDGER_MEMBERSHIP_REQUIRED")
    if external.get("FROM_STATE_EPOCH") != previous.get("SOURCE_STATE_EPOCH"):
        findings.append(f"{prefix}:APPLIED_RECEIPT_FROM_EPOCH_MISMATCH")
    if external.get("TO_STATE_EPOCH") != current.get("SOURCE_STATE_EPOCH"):
        findings.append(f"{prefix}:APPLIED_RECEIPT_TO_EPOCH_MISMATCH")
    if external.get("COMMITTED_REVISION") != current.get("SOURCE_STATE_EPOCH"):
        findings.append(f"{prefix}:COMMITTED_REVISION_MISMATCH")

    ext_keys = external.get("AFFECTED_KEYS")
    if not isinstance(ext_keys, list) or set(map(str, ext_keys)) != affected_set or len(ext_keys) != len(set(ext_keys)):
        findings.append(f"{prefix}:APPLIED_RECEIPT_AFFECTED_KEYS_MISMATCH")

    expected_subset = {key: expected_changes[key] for key in sorted(affected_set) if key in expected_changes}
    if set(expected_subset) != affected_set:
        findings.append(f"{prefix}:APPLIED_RECEIPT_CLAIMS_NONEXISTENT_CHANGE")
    changeset = external.get("AUTHORITATIVE_CHANGESET")
    if changeset != expected_subset:
        findings.append(f"{prefix}:AUTHORITATIVE_CHANGESET_MISMATCH")
    digest_payload = {
        "EVENT_ID": event_id,
        "FROM_STATE_EPOCH": previous.get("SOURCE_STATE_EPOCH"),
        "TO_STATE_EPOCH": current.get("SOURCE_STATE_EPOCH"),
        "AFFECTED_KEYS": sorted(affected_set),
        "AUTHORITATIVE_CHANGESET": expected_subset,
    }
    if external.get("AUTHORITATIVE_CHANGESET_DIGEST") != canonical_digest(digest_payload):
        findings.append(f"{prefix}:AUTHORITATIVE_CHANGESET_DIGEST_MISMATCH")
    return affected_set


def validate_transition(
    previous: Mapping[str, object],
    current: Mapping[str, object],
    receipt: Mapping[str, object],
    proofs: object = None,
) -> GuardResult:
    findings: list[str] = []
    prefix = f"{previous.get('FRAME_ID','?')}->{current.get('FRAME_ID','?')}"
    if (
        receipt.get("CONTINUITY_GROUP_ID") != current.get("CONTINUITY_GROUP_ID")
        or receipt.get("CONTINUITY_GROUP_ID") != previous.get("CONTINUITY_GROUP_ID")
    ):
        findings.append(f"{prefix}:TRANSITION_GROUP_MISMATCH")
    if (
        receipt.get("FROM_FRAME_ID") != previous.get("FRAME_ID")
        or receipt.get("TO_FRAME_ID") != current.get("FRAME_ID")
    ):
        findings.append(f"{prefix}:TRANSITION_FRAME_BINDING_MISMATCH")
    causes = receipt.get("CAUSES")
    if not isinstance(causes, list):
        return _result(findings + [f"{prefix}:CAUSES_MUST_BE_LIST"])

    gameplay_changes, change_findings = _gameplay_changes(previous, current)
    findings.extend(change_findings)
    gameplay_changed = set(gameplay_changes)
    presentation_changed = _presentation_change_keys(previous, current)
    gameplay_covered: set[str] = set()
    presentation_covered: set[str] = set()
    committed_event_seen = False
    used_applied_receipts: set[str] = set()

    for i, cause in enumerate(causes):
        cause_prefix = f"{prefix}:CAUSE_{i}"
        if not isinstance(cause, Mapping):
            findings.append(f"{cause_prefix}_INVALID")
            continue
        cause_type = cause.get("CAUSE_TYPE")
        affected = cause.get("AFFECTED_KEYS")
        if cause_type not in ALLOWED_CAUSE_TYPES:
            findings.append(f"{prefix}:UNKNOWN_CAUSE_TYPE:{cause_type}")
            continue
        if cause_type == "CAMERA_ONLY":
            if not isinstance(affected, list) or len(affected) != len(set(affected)):
                findings.append(f"{prefix}:CAMERA_ONLY_AFFECTED_KEYS_INVALID")
                continue
            affected_set = set(map(str, affected))
            invalid = sorted(
                k for k in affected_set
                if k not in {f"PRESENTATION:{x}" for x in PRESENTATION_FIELDS}
            )
            if invalid:
                findings.append(f"{prefix}:CAMERA_ONLY_GAMEPLAY_KEY:{','.join(invalid)}")
            presentation_covered |= affected_set
        else:
            committed_event_seen = True
            rid = cause.get("APPLIED_EVENT_LEDGER_RECEIPT_ID")
            if rid in used_applied_receipts and rid is not None:
                findings.append(f"{prefix}:DUPLICATE_APPLIED_EVENT_RECEIPT:{rid}")
            if rid:
                used_applied_receipts.add(str(rid))
            affected_set = _validate_applied_event_receipt(
                cause,
                previous,
                current,
                gameplay_changes,
                proofs,
                cause_prefix,
                findings,
            )
            if (
                cause.get("FROM_STATE_EPOCH") != previous.get("SOURCE_STATE_EPOCH")
                or cause.get("TO_STATE_EPOCH") != current.get("SOURCE_STATE_EPOCH")
            ):
                findings.append(f"{prefix}:EVENT_EPOCH_BINDING_MISMATCH")
            gameplay_covered |= affected_set

    if gameplay_changed != gameplay_covered:
        for key in sorted(gameplay_changed - gameplay_covered):
            findings.append(f"{prefix}:UNCAUSED_GAMEPLAY_CHANGE:{key}")
        for key in sorted(gameplay_covered - gameplay_changed):
            findings.append(f"{prefix}:NONEXISTENT_GAMEPLAY_CHANGE_CLAIM:{key}")
    if presentation_changed != presentation_covered:
        for key in sorted(presentation_changed - presentation_covered):
            findings.append(f"{prefix}:UNCAUSED_PRESENTATION_CHANGE:{key}")
        for key in sorted(presentation_covered - presentation_changed):
            findings.append(f"{prefix}:NONEXISTENT_PRESENTATION_CHANGE_CLAIM:{key}")

    epoch_changed = previous.get("SOURCE_STATE_EPOCH") != current.get("SOURCE_STATE_EPOCH")
    if epoch_changed and not committed_event_seen:
        findings.append(f"{prefix}:STATE_EPOCH_CHANGE_WITHOUT_COMMITTED_EVENT")
    if gameplay_changed and not epoch_changed:
        findings.append(f"{prefix}:GAMEPLAY_CHANGE_WITHOUT_EPOCH_ADVANCE")
    if not gameplay_changed and committed_event_seen:
        findings.append(f"{prefix}:COMMITTED_EVENT_WITHOUT_CONTINUITY_CHANGE")
    return _result(findings)


def validate_sequence(
    group: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    transitions: Sequence[Mapping[str, object]],
    proofs: object = None,
) -> GuardResult:
    findings: list[str] = list(validate_continuity_group(group, proofs).findings)
    if not frames:
        return _result(findings + ["SEQUENCE:AT_LEAST_ONE_FRAME_REQUIRED"])

    frame_ids: set[str] = set()
    indexes: set[int] = set()
    lineage: dict[str, tuple[object, object]] = {}
    group_entities = _raw_entity_map(group.get("ENTITY_BASELINES"))
    group_facts = _raw_fact_map(group.get("SCENE_FACTS"))

    for position, frame in enumerate(frames):
        findings.extend(validate_frame(frame, proofs).findings)
        frame_id = str(frame.get("FRAME_ID"))
        idx = frame.get("FRAME_INDEX")
        if frame_id in frame_ids:
            findings.append(f"SEQUENCE:DUPLICATE_FRAME_ID:{frame_id}")
        frame_ids.add(frame_id)
        if isinstance(idx, int):
            if idx in indexes:
                findings.append(f"SEQUENCE:DUPLICATE_FRAME_INDEX:{idx}")
            indexes.add(idx)
            if idx != position:
                findings.append(f"{frame_id}:FRAME_INDEX_GAP_OR_ORDER_MISMATCH")
        if frame.get("CONTINUITY_GROUP_ID") != group.get("CONTINUITY_GROUP_ID"):
            findings.append(f"{frame_id}:GROUP_MISMATCH")
        if frame.get("OBSERVER_BRANCH_ID") != group.get("OBSERVER_BRANCH_ID"):
            findings.append(f"{frame_id}:OBSERVER_BRANCH_CHANGED")
        expected_prev = None if position == 0 else frames[position - 1].get("FRAME_ID")
        if frame.get("PREVIOUS_FRAME_ID") != expected_prev:
            findings.append(f"{frame_id}:PREVIOUS_FRAME_CHAIN_MISMATCH")

        entities = _raw_entity_map(frame.get("TRACKED_ENTITIES"))
        facts = _raw_fact_map(frame.get("SCENE_FACTS"))
        if position == 0:
            if set(entities) != set(group_entities):
                findings.append(f"{frame_id}:OPENING_ENTITY_SET_MISMATCH")
            if set(facts) != set(group_facts):
                findings.append(f"{frame_id}:OPENING_SCENE_FACT_SET_MISMATCH")
            for entity_id in set(entities) & set(group_entities):
                left, right = entities[entity_id], group_entities[entity_id]
                if left.get("IDENTITY_AUTHORITY_ID") != right.get("IDENTITY_AUTHORITY_ID"):
                    findings.append(f"{entity_id}:OPENING_IDENTITY_AUTHORITY_MISMATCH")
                if left.get("CAMPAIGN_VISUAL_ANCHOR_ID") != right.get("CAMPAIGN_VISUAL_ANCHOR_ID"):
                    findings.append(f"{entity_id}:OPENING_ANCHOR_MISMATCH")
                if left.get("EVS_VALIDATION_RECEIPT_ID") != right.get("EVS_VALIDATION_RECEIPT_ID"):
                    findings.append(f"{entity_id}:OPENING_EVS_RECEIPT_MISMATCH")
            for fact_id in set(facts) & set(group_facts):
                left, right = facts[fact_id], group_facts[fact_id]
                if left.get("FACT_CLASS") != right.get("FACT_CLASS") or left.get("VALUE") != right.get("VALUE"):
                    findings.append(f"{fact_id}:OPENING_SCENE_FACT_MISMATCH")
                if left.get("SOURCE_RECEIPT_ID") != right.get("SOURCE_RECEIPT_ID"):
                    findings.append(f"{fact_id}:OPENING_SOURCE_RECEIPT_MISMATCH")
            if frame.get("SOURCE_STATE_EPOCH") != group.get("OPENING_STATE_EPOCH"):
                findings.append(f"{frame_id}:OPENING_STATE_EPOCH_MISMATCH")

        for entity_id, entity in entities.items():
            signature = (
                entity.get("IDENTITY_AUTHORITY_ID"),
                entity.get("CAMPAIGN_VISUAL_ANCHOR_ID"),
            )
            if entity_id in lineage and lineage[entity_id] != signature:
                findings.append(f"{entity_id}:SEQUENCE_IDENTITY_LINEAGE_DRIFT")
            lineage.setdefault(entity_id, signature)

    transition_map: dict[tuple[object, object], Mapping[str, object]] = {}
    for tr in transitions:
        if not isinstance(tr, Mapping):
            findings.append("SEQUENCE:TRANSITION_RECEIPT_INVALID")
            continue
        key = (tr.get("FROM_FRAME_ID"), tr.get("TO_FRAME_ID"))
        if key in transition_map:
            findings.append(f"SEQUENCE:DUPLICATE_TRANSITION:{key[0]}->{key[1]}")
        transition_map[key] = tr

    expected_keys: set[tuple[object, object]] = set()
    for i in range(1, len(frames)):
        key = (frames[i - 1].get("FRAME_ID"), frames[i].get("FRAME_ID"))
        expected_keys.add(key)
        tr = transition_map.get(key)
        if tr is None:
            findings.append(f"SEQUENCE:MISSING_TRANSITION:{key[0]}->{key[1]}")
        else:
            findings.extend(validate_transition(frames[i - 1], frames[i], tr, proofs).findings)
    for key in sorted(set(transition_map) - expected_keys, key=lambda x: str(x)):
        findings.append(f"SEQUENCE:EXTRA_TRANSITION:{key[0]}->{key[1]}")
    return _result(findings)


def _render_binding(
    receipt: Mapping[str, object],
    frame: Mapping[str, object],
    outer: Mapping[str, object],
    prefix: str,
    findings: list[str],
) -> None:
    expected = {
        "FRAME_ID": frame.get("FRAME_ID"),
        "CONTINUITY_GROUP_ID": frame.get("CONTINUITY_GROUP_ID"),
        "RENDER_ARTIFACT_ID": outer.get("RENDER_ARTIFACT_ID"),
        "RENDER_ARTIFACT_HASH": outer.get("RENDER_ARTIFACT_HASH"),
        "VISUAL_MANIFEST_ID": frame.get("VISUAL_MANIFEST_ID"),
        "FRAME_STATE_DIGEST": frame_state_digest(frame),
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            findings.append(f"{prefix}:{key}_BINDING_MISMATCH")


def evaluate_post_render(
    frame: Mapping[str, object],
    receipt: Mapping[str, object],
    proofs: object = None,
) -> GuardResult:
    findings: list[str] = list(validate_frame(frame, proofs).findings)
    prefix = str(frame.get("FRAME_ID", "FRAME"))
    missing = _missing(receipt, REQUIRED_POST_RENDER_FIELDS)
    findings.extend(f"{prefix}:POST_RENDER_MISSING_{k}" for k in missing)
    if missing:
        return _result(findings)

    if (
        receipt.get("FRAME_ID") != frame.get("FRAME_ID")
        or receipt.get("CONTINUITY_GROUP_ID") != frame.get("CONTINUITY_GROUP_ID")
    ):
        findings.append(f"{prefix}:POST_RENDER_BINDING_MISMATCH")
    if receipt.get("VISUAL_MANIFEST_ID") != frame.get("VISUAL_MANIFEST_ID"):
        findings.append(f"{prefix}:POST_RENDER_MANIFEST_BINDING_MISMATCH")
    expected_frame_digest = frame_state_digest(frame)
    if receipt.get("FRAME_STATE_DIGEST") != expected_frame_digest:
        findings.append(f"{prefix}:POST_RENDER_FRAME_STATE_DIGEST_MISMATCH")
    render_hash = receipt.get("RENDER_ARTIFACT_HASH")
    if not isinstance(render_hash, str) or not _SHA256_RE.match(render_hash):
        findings.append(f"{prefix}:RENDER_ARTIFACT_HASH_INVALID")
    if not receipt.get("RENDER_ARTIFACT_ID"):
        findings.append(f"{prefix}:RENDER_ARTIFACT_ID_REQUIRED")

    vil = _external_receipt(
        proofs,
        "VIL_RECEIPTS",
        receipt.get("VISUAL_IDENTITY_LOCK_RECEIPT_ID"),
        f"{prefix}:VIL",
        findings,
    )
    if vil:
        if vil.get("STATUS") != "PASS":
            findings.append(f"{prefix}:VIL_EXTERNAL_STATUS_NOT_PASS")
        _render_binding(vil, frame, receipt, f"{prefix}:VIL", findings)

    ps = _external_receipt(
        proofs,
        "PLAYER_SAFE_RENDER_RECEIPTS",
        receipt.get("PLAYER_SAFE_CONTENT_RECEIPT_ID"),
        f"{prefix}:PLAYER_SAFE_RENDER",
        findings,
    )
    if ps:
        if ps.get("STATUS") != "PASS":
            findings.append(f"{prefix}:PLAYER_SAFE_RENDER_NOT_PASS")
        _render_binding(ps, frame, receipt, f"{prefix}:PLAYER_SAFE_RENDER", findings)

    expected_entities = set(frame.get("IN_FRAME_ENTITY_IDS", []))
    expected_facts = set(frame.get("IN_FRAME_SCENE_FACT_IDS", []))
    entity_refs = receipt.get("ENTITY_CONTINUITY_RECEIPT_IDS")
    fact_refs = receipt.get("SCENE_FACT_CONTINUITY_RECEIPT_IDS")

    if not isinstance(entity_refs, Mapping):
        findings.append(f"{prefix}:ENTITY_CONTINUITY_RECEIPT_IDS_INVALID")
    else:
        actual = set(entity_refs)
        for item in sorted(expected_entities - actual):
            findings.append(f"{prefix}:MISSING_ENTITY_CONTINUITY_RECEIPT:{item}")
        for item in sorted(actual - expected_entities):
            findings.append(f"{prefix}:EXTRA_ENTITY_CONTINUITY_RECEIPT:{item}")
        if len(list(entity_refs.values())) != len(set(entity_refs.values())):
            findings.append(f"{prefix}:REUSED_ENTITY_CONTINUITY_RECEIPT_ID")
        entities = _raw_entity_map(frame.get("TRACKED_ENTITIES"))
        for item in sorted(expected_entities & actual):
            ext = _external_receipt(
                proofs,
                "ENTITY_RENDER_RECEIPTS",
                entity_refs[item],
                f"{prefix}:ENTITY_RENDER:{item}",
                findings,
            )
            if ext:
                if ext.get("STATUS") != "PASS":
                    findings.append(f"{prefix}:ENTITY_CONTINUITY_NOT_PASS:{item}")
                _render_binding(ext, frame, receipt, f"{prefix}:ENTITY_RENDER:{item}", findings)
                if ext.get("ENTITY_ID") != item:
                    findings.append(f"{prefix}:ENTITY_RENDER_ID_MISMATCH:{item}")
                if item in entities and ext.get("ENTITY_STATE_DIGEST") != entity_state_digest(entities[item]):
                    findings.append(f"{prefix}:ENTITY_RENDER_STATE_DIGEST_MISMATCH:{item}")

    if not isinstance(fact_refs, Mapping):
        findings.append(f"{prefix}:SCENE_FACT_CONTINUITY_RECEIPT_IDS_INVALID")
    else:
        actual = set(fact_refs)
        for item in sorted(expected_facts - actual):
            findings.append(f"{prefix}:MISSING_SCENE_FACT_CONTINUITY_RECEIPT:{item}")
        for item in sorted(actual - expected_facts):
            findings.append(f"{prefix}:EXTRA_SCENE_FACT_CONTINUITY_RECEIPT:{item}")
        if len(list(fact_refs.values())) != len(set(fact_refs.values())):
            findings.append(f"{prefix}:REUSED_SCENE_FACT_CONTINUITY_RECEIPT_ID")
        facts = _raw_fact_map(frame.get("SCENE_FACTS"))
        for item in sorted(expected_facts & actual):
            ext = _external_receipt(
                proofs,
                "FACT_RENDER_RECEIPTS",
                fact_refs[item],
                f"{prefix}:FACT_RENDER:{item}",
                findings,
            )
            if ext:
                if ext.get("STATUS") != "PASS":
                    findings.append(f"{prefix}:SCENE_FACT_CONTINUITY_NOT_PASS:{item}")
                _render_binding(ext, frame, receipt, f"{prefix}:FACT_RENDER:{item}", findings)
                if ext.get("FACT_ID") != item:
                    findings.append(f"{prefix}:FACT_RENDER_ID_MISMATCH:{item}")
                if item in facts and ext.get("FACT_VALUE_DIGEST") != fact_value_digest(facts[item]):
                    findings.append(f"{prefix}:FACT_RENDER_VALUE_DIGEST_MISMATCH:{item}")
    return _result(findings)
