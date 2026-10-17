import copy
import json
import unittest
from pathlib import Path

from tools.visual.entity_visual_state_guard import (
    UNKNOWN_SENTINEL,
    validate_anchor_promotion,
    validate_anchor_reuse,
    validate_entity_visual_state,
)

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "qa" / "visual" / "ENTITY_VISUAL_STATE_MANIFEST_v1.json"
CONTRACT_PATH = ROOT / "docs" / "visual" / "ENTITY_VISUAL_STATE_CONTRACT_v1.md"


def valid_state():
    return {
        "ENTITY_ID": "NPC_KRUNG_YUNG",
        "ENTITY_CLASS": "NAMED_RECURRING_MONSTER",
        "IDENTITY_LOCK_LEVEL": "STRICT",
        "IDENTITY_AUTHORITY_ID": "MM_OFFICIAL_ETTIN_SPECIES",
        "IDENTITY_REFERENCE_ASSET": "official_ettin_reference_crop.png",
        "CURRENT_FORM": "ETTIN_BASE_FORM",
        "CURRENT_VISIBLE_EQUIPMENT": ["club", "hide scraps"],
        "CURRENT_VISIBLE_WOUNDS_OR_MARKS": ["old left-shoulder scar"],
        "CURRENT_VISIBLE_EFFECTS": [],
        "CURRENT_VISIBLE_TRANSFORMATION": None,
        "SOURCE_STATE_EPOCH": "REV-1042",
        "CURRENT_VISIBLE_STATE_SOURCE": "COMMITTED_RUNTIME_OR_SAVE",
        "OBSERVER_SCOPE": "PLAYER_SAFE",
        "OBSERVER_BRANCH_ID": "BRANCH-PARTY-A",
        "PLAYER_KNOWLEDGE_PROJECTION_ID": "PKP-REV1042-PARTY-A",
        "PLAYER_KNOWLEDGE_PROJECTION_STATUS": "MATERIALIZED",
        "PLAYER_KNOWLEDGE_PROJECTION_OBSERVER_BRANCH_ID": "BRANCH-PARTY-A",
        "PLAYER_KNOWLEDGE_PROJECTION_SOURCE_STATE_EPOCH": "REV-1042",
        "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID": "KLG-REV1042-PARTY-A",
        "KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS": "PASS",
        "UNKNOWN_VISIBLE_FIELDS": [],
        "UNKNOWN_POLICY": "PRESERVE_UNKNOWN_NO_INVENTION",
        "STATE_AUTHORITY": "DERIVED_NONAUTHORITATIVE",
        "PROJECT_SOURCE_SLOT_DELTA": 0,
        "CAMPAIGN_ANCHOR_STATUS": "APPROVED",
        "CAMPAIGN_VISUAL_ANCHOR_ID": "VIS_NPC_KRUNG_YUNG_v1",
        "CAMPAIGN_VISUAL_ANCHOR_ASSET": "VIS_NPC_KRUNG_YUNG_v1.jpeg",
        "CAMPAIGN_VISUAL_ANCHOR_PROMOTION_RECEIPT_ID": "APR-KRUNG-001",
        "CAMPAIGN_VISUAL_ANCHOR_PROMOTION_RECEIPT_STATUS": "PASS",
        "CAMPAIGN_VISUAL_ANCHOR_FORM_SCOPE": ["ETTIN_BASE_FORM"],
        "ANCHOR_OVERRIDES_SPECIES_AUTHORITY": False,
        "ANCHOR_OVERRIDES_CURRENT_FORM": False,
        "ANCHOR_OVERRIDES_RUNTIME_EQUIPMENT": False,
        "ANCHOR_OVERRIDES_PLAYER_KNOWLEDGE": False,
    }


def valid_promotion():
    return {
        "ENTITY_ID": "NPC_KRUNG_YUNG",
        "ENTITY_CLASS": "NAMED_RECURRING_MONSTER",
        "IDENTITY_AUTHORITY_ID": "MM_OFFICIAL_ETTIN_SPECIES",
        "OFFICIAL_SPECIES_OR_VARIANT_AUTHORITY_ID": "MM_OFFICIAL_ETTIN_SPECIES",
        "ANCHOR_ID": "VIS_NPC_KRUNG_YUNG_v1",
        "ANCHOR_ASSET": "VIS_NPC_KRUNG_YUNG_v1.jpeg",
        "SOURCE_RENDER_ID": "RENDER-ETTIN-001",
        "SOURCE_STATE_EPOCH": "REV-1042",
        "FORM_SCOPE": ["ETTIN_BASE_FORM"],
        "VISUAL_IDENTITY_LOCK_RECEIPT_STATUS": "PASS",
        "APPROVAL_STATUS": "PLAYER_APPROVED",
        "PROMOTION_RECEIPT_ID": "APR-KRUNG-001",
        "PROMOTION_RECEIPT_STATUS": "PASS",
        "ANCHOR_LIFECYCLE_STATUS": "APPROVED",
        "ANCHOR_IS_GAMEPLAY_CANON": False,
        "ANCHOR_OVERRIDES_SPECIES_AUTHORITY": False,
        "ANCHOR_OVERRIDES_CURRENT_FORM": False,
        "ANCHOR_OVERRIDES_RUNTIME_EQUIPMENT": False,
        "ANCHOR_OVERRIDES_MECHANICS": False,
        "ANCHOR_OVERRIDES_PLAYER_KNOWLEDGE": False,
        "PROJECT_SOURCE_SLOT_DELTA": 0,
    }


def without_anchor(state):
    state = copy.deepcopy(state)
    state["CAMPAIGN_ANCHOR_STATUS"] = "NONE"
    for key in list(state):
        if key.startswith("CAMPAIGN_VISUAL_ANCHOR") or key.startswith("ANCHOR_OVERRIDES"):
            state.pop(key, None)
    return state


class EntityVisualStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.contract = CONTRACT_PATH.read_text(encoding="utf-8")

    def test_source_budget_stays_zero(self):
        self.assertEqual(self.manifest["project_source_slot_delta"], 0)
        self.assertFalse(self.manifest["active_runtime_mutation"])
        self.assertFalse(self.manifest["campaign_canon_mutation"])
        self.assertIn("zero new Project Source slots", self.contract)

    def test_valid_derived_state_is_accepted(self):
        self.assertTrue(validate_entity_visual_state(valid_state()).passed)

    def test_unknown_entity_class_is_rejected(self):
        state = valid_state()
        state["ENTITY_CLASS"] = "TOTALLY_UNKNOWN_CLASS"
        result = validate_entity_visual_state(state)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:UNKNOWN_ENTITY_CLASS", result.findings)

    def test_wrong_moderate_and_loose_levels_are_rejected(self):
        state = without_anchor(valid_state())
        state["ENTITY_ID"] = "MONSTER_ETTIN_GENERIC"
        state["ENTITY_CLASS"] = "STANDARD_MONSTER_SPECIES"
        state["IDENTITY_LOCK_LEVEL"] = "STRICT"
        self.assertFalse(validate_entity_visual_state(state).passed)

        mob = copy.deepcopy(state)
        mob["ENTITY_CLASS"] = "GENERIC_MOB"
        mob["IDENTITY_LOCK_LEVEL"] = "MODERATE"
        self.assertFalse(validate_entity_visual_state(mob).passed)

    def test_noncommitted_visible_state_is_rejected(self):
        state = valid_state()
        state["CURRENT_VISIBLE_STATE_SOURCE"] = "OLD_REFERENCE_IMAGE"
        result = validate_entity_visual_state(state)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:VISIBLE_STATE_NOT_COMMITTED", result.findings)

    def test_player_safe_requires_materialized_pkp_receipt(self):
        state = valid_state()
        state["PLAYER_KNOWLEDGE_PROJECTION_ID"] = None
        state["PLAYER_KNOWLEDGE_PROJECTION_STATUS"] = "DECLARED_ONLY"
        result = validate_entity_visual_state(state)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:PKP_ID_REQUIRED", result.findings)
        self.assertIn("NPC_KRUNG_YUNG:PKP_MATERIALIZED_RECEIPT_REQUIRED", result.findings)

    def test_player_safe_requires_leak_gate_pass_receipt(self):
        state = valid_state()
        state["KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID"] = None
        state["KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS"] = "NOT_RUN"
        result = validate_entity_visual_state(state)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:LEAK_GATE_RECEIPT_ID_REQUIRED", result.findings)
        self.assertIn("NPC_KRUNG_YUNG:LEAK_GATE_PASS_REQUIRED", result.findings)

    def test_pkp_observer_branch_mismatch_is_rejected(self):
        state = valid_state()
        state["PLAYER_KNOWLEDGE_PROJECTION_OBSERVER_BRANCH_ID"] = "OTHER-BRANCH"
        result = validate_entity_visual_state(state)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:PKP_OBSERVER_BRANCH_MISMATCH", result.findings)

    def test_pkp_state_epoch_mismatch_is_rejected(self):
        state = valid_state()
        state["PLAYER_KNOWLEDGE_PROJECTION_SOURCE_STATE_EPOCH"] = "REV-OLD"
        result = validate_entity_visual_state(state)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:PKP_STATE_EPOCH_MISMATCH", result.findings)

    def test_unknown_visual_fact_requires_explicit_neutral_sentinel(self):
        state = valid_state()
        state["UNKNOWN_VISIBLE_FIELDS"] = ["CURRENT_VISIBLE_WOUNDS_OR_MARKS"]
        state["CURRENT_VISIBLE_WOUNDS_OR_MARKS"] = copy.deepcopy(UNKNOWN_SENTINEL)
        result = validate_entity_visual_state(state)
        self.assertTrue(result.passed)

    def test_unknown_field_with_resolved_or_invented_value_is_rejected(self):
        state = valid_state()
        state["UNKNOWN_VISIBLE_FIELDS"] = ["CURRENT_VISIBLE_WOUNDS_OR_MARKS"]
        state["CURRENT_VISIBLE_WOUNDS_OR_MARKS"] = ["invented dramatic facial scar"]
        result = validate_entity_visual_state(state)
        self.assertFalse(result.passed)
        self.assertIn(
            "NPC_KRUNG_YUNG:CURRENT_VISIBLE_WOUNDS_OR_MARKS_UNKNOWN_REQUIRES_NEUTRAL_SENTINEL",
            result.findings,
        )

    def test_typo_unknown_field_is_rejected(self):
        state = valid_state()
        state["UNKNOWN_VISIBLE_FIELDS"] = ["CURRENT_VISBLE_WOUNDZ"]
        result = validate_entity_visual_state(state)
        self.assertFalse(result.passed)
        self.assertIn(
            "NPC_KRUNG_YUNG:UNKNOWN_VISIBLE_FIELD_NOT_ALLOWED:CURRENT_VISBLE_WOUNDZ",
            result.findings,
        )

    def test_unknown_sentinel_without_declaration_is_rejected(self):
        state = valid_state()
        state["CURRENT_VISIBLE_EFFECTS"] = copy.deepcopy(UNKNOWN_SENTINEL)
        result = validate_entity_visual_state(state)
        self.assertFalse(result.passed)
        self.assertIn(
            "NPC_KRUNG_YUNG:CURRENT_VISIBLE_EFFECTS_UNKNOWN_SENTINEL_REQUIRES_DECLARATION",
            result.findings,
        )

    def test_ineligible_approved_anchor_is_rejected(self):
        state = valid_state()
        state["ENTITY_ID"] = "PC_AELIAN"
        state["ENTITY_CLASS"] = "PC"
        state["IDENTITY_LOCK_LEVEL"] = "VERY_STRICT"
        state["IDENTITY_AUTHORITY_ID"] = "VIS_PC_AELIAN_v1"
        result = validate_entity_visual_state(state)
        self.assertFalse(result.passed)
        self.assertIn("PC_AELIAN:APPROVED_ANCHOR_CLASS_INELIGIBLE", result.findings)

    def test_anchor_promotion_requires_vil_pass(self):
        promotion = valid_promotion()
        promotion["VISUAL_IDENTITY_LOCK_RECEIPT_STATUS"] = "FAIL"
        result = validate_anchor_promotion(promotion)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:VIL_PASS_REQUIRED", result.findings)

    def test_anchor_promotion_requires_explicit_approval(self):
        promotion = valid_promotion()
        promotion["APPROVAL_STATUS"] = "AUTO_APPROVED_BY_GENERATOR"
        result = validate_anchor_promotion(promotion)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:EXPLICIT_APPROVAL_REQUIRED", result.findings)

    def test_anchor_promotion_requires_approved_receipt_lifecycle(self):
        promotion = valid_promotion()
        promotion["PROMOTION_RECEIPT_STATUS"] = "PENDING"
        promotion["ANCHOR_LIFECYCLE_STATUS"] = "CANDIDATE"
        result = validate_anchor_promotion(promotion)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:PROMOTION_RECEIPT_PASS_REQUIRED", result.findings)
        self.assertIn("NPC_KRUNG_YUNG:ANCHOR_LIFECYCLE_NOT_APPROVED", result.findings)

    def test_monster_anchor_requires_species_authority(self):
        promotion = valid_promotion()
        promotion.pop("OFFICIAL_SPECIES_OR_VARIANT_AUTHORITY_ID")
        result = validate_anchor_promotion(promotion)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:MONSTER_SPECIES_AUTHORITY_REQUIRED", result.findings)

    def test_anchor_cannot_override_runtime_or_canon(self):
        promotion = valid_promotion()
        promotion["ANCHOR_IS_GAMEPLAY_CANON"] = True
        promotion["ANCHOR_OVERRIDES_RUNTIME_EQUIPMENT"] = True
        promotion["ANCHOR_OVERRIDES_CURRENT_FORM"] = True
        result = validate_anchor_promotion(promotion)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:ANCHOR_MUST_NOT_BE_GAMEPLAY_CANON", result.findings)
        self.assertIn("NPC_KRUNG_YUNG:ANCHOR_CANNOT_OVERRIDE_EQUIPMENT", result.findings)
        self.assertIn("NPC_KRUNG_YUNG:ANCHOR_CANNOT_OVERRIDE_FORM", result.findings)

    def test_dynamic_equipment_change_does_not_invalidate_anchor(self):
        state = valid_state()
        anchor = valid_promotion()
        state["CURRENT_VISIBLE_EQUIPMENT"] = ["different currently committed club"]
        self.assertTrue(validate_anchor_reuse(anchor, state).passed)

    def test_form_scope_mismatch_is_rejected(self):
        state = valid_state()
        state["CURRENT_FORM"] = "OTHER_FORM"
        anchor = valid_promotion()
        result = validate_anchor_reuse(anchor, state)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:ANCHOR_FORM_SCOPE_MISMATCH", result.findings)

    def test_unapproved_anchor_reuse_is_rejected(self):
        state = valid_state()
        anchor = valid_promotion()
        anchor["PROMOTION_RECEIPT_STATUS"] = "PENDING"
        anchor["ANCHOR_LIFECYCLE_STATUS"] = "CANDIDATE"
        result = validate_anchor_reuse(anchor, state)
        self.assertFalse(result.passed)
        self.assertTrue(any("PROMOTION_RECEIPT_PASS_REQUIRED" in x for x in result.findings))
        self.assertTrue(any("ANCHOR_LIFECYCLE_NOT_APPROVED" in x for x in result.findings))

    def test_vil_failed_anchor_reuse_is_rejected(self):
        state = valid_state()
        anchor = valid_promotion()
        anchor["VISUAL_IDENTITY_LOCK_RECEIPT_STATUS"] = "FAIL"
        result = validate_anchor_reuse(anchor, state)
        self.assertFalse(result.passed)
        self.assertTrue(any("VIL_PASS_REQUIRED" in x for x in result.findings))

    def test_anchor_receipt_mismatch_is_rejected(self):
        state = valid_state()
        anchor = valid_promotion()
        anchor["PROMOTION_RECEIPT_ID"] = "FORGED-OTHER-RECEIPT"
        result = validate_anchor_reuse(anchor, state)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:ANCHOR_PROMOTION_RECEIPT_MISMATCH", result.findings)

    def test_pc_anchor_reuse_is_rejected(self):
        state = valid_state()
        state["ENTITY_ID"] = "PC_AELIAN"
        state["ENTITY_CLASS"] = "PC"
        state["IDENTITY_LOCK_LEVEL"] = "VERY_STRICT"
        state["IDENTITY_AUTHORITY_ID"] = "VIS_PC_AELIAN_v1"
        state["IDENTITY_REFERENCE_ASSET"] = "VIS_PC_AELIAN_v1.jpeg"
        anchor = valid_promotion()
        anchor.update({
            "ENTITY_ID": "PC_AELIAN",
            "ENTITY_CLASS": "PC",
            "IDENTITY_AUTHORITY_ID": "VIS_PC_AELIAN_v1",
            "ANCHOR_ID": state["CAMPAIGN_VISUAL_ANCHOR_ID"],
            "ANCHOR_ASSET": state["CAMPAIGN_VISUAL_ANCHOR_ASSET"],
        })
        result = validate_anchor_reuse(anchor, state)
        self.assertFalse(result.passed)
        self.assertIn("PC_AELIAN:ANCHOR_REUSE_CLASS_INELIGIBLE", result.findings)
        self.assertTrue(any("ANCHOR_CLASS_INELIGIBLE" in x for x in result.findings))

    def test_generic_anchor_reuse_is_rejected(self):
        state = without_anchor(valid_state())
        state["ENTITY_ID"] = "GENERIC_GOBLIN_1"
        state["ENTITY_CLASS"] = "GENERIC_MOB"
        state["IDENTITY_LOCK_LEVEL"] = "LOOSE_WITH_SPECIES_GUARD"
        anchor = valid_promotion()
        anchor.update({"ENTITY_ID": "GENERIC_GOBLIN_1", "ENTITY_CLASS": "GENERIC_MOB"})
        result = validate_anchor_reuse(anchor, state)
        self.assertFalse(result.passed)
        self.assertIn("GENERIC_GOBLIN_1:ANCHOR_REUSE_CLASS_INELIGIBLE", result.findings)

    def test_required_regression_set_is_pinned(self):
        required = set(self.manifest["required_regressions"])
        expected = {
            "VALID_DERIVED_STATE_ACCEPTED",
            "UNKNOWN_ENTITY_CLASS_REJECTED",
            "WRONG_LOCK_LEVEL_REJECTED",
            "NONCOMMITTED_VISIBLE_STATE_REJECTED",
            "PLAYER_SAFE_REQUIRES_MATERIALIZED_PKP_RECEIPT",
            "PLAYER_SAFE_REQUIRES_LEAK_GATE_PASS_RECEIPT",
            "PKP_OBSERVER_BRANCH_MISMATCH_REJECTED",
            "PKP_STATE_EPOCH_MISMATCH_REJECTED",
            "UNKNOWN_VISUAL_FACT_REQUIRES_NEUTRAL_SENTINEL",
            "UNKNOWN_FIELD_WITH_VALUE_REJECTED",
            "TYPO_UNKNOWN_FIELD_REJECTED",
            "UNKNOWN_SENTINEL_WITHOUT_DECLARATION_REJECTED",
            "INELIGIBLE_APPROVED_ANCHOR_REJECTED",
            "ANCHOR_PROMOTION_REQUIRES_VIL_PASS",
            "ANCHOR_PROMOTION_REQUIRES_EXPLICIT_APPROVAL",
            "ANCHOR_PROMOTION_REQUIRES_APPROVED_RECEIPT_LIFECYCLE",
            "MONSTER_ANCHOR_REQUIRES_SPECIES_AUTHORITY",
            "ANCHOR_CANNOT_OVERRIDE_RUNTIME_OR_CANON",
            "DYNAMIC_EQUIPMENT_CHANGE_DOES_NOT_INVALIDATE_IDENTITY_ANCHOR",
            "FORM_SCOPE_MISMATCH_REJECTED",
            "UNAPPROVED_ANCHOR_REUSE_REJECTED",
            "VIL_FAILED_ANCHOR_REUSE_REJECTED",
            "ANCHOR_RECEIPT_MISMATCH_REJECTED",
            "PC_ANCHOR_REUSE_REJECTED",
            "GENERIC_ANCHOR_REUSE_REJECTED",
            "PROJECT_SOURCE_SLOT_DELTA_ZERO",
        }
        self.assertEqual(required, expected)


if __name__ == "__main__":
    unittest.main()
