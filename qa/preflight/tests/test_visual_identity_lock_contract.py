import copy
import json
import unittest
from pathlib import Path

from tools.visual.visual_identity_guard import (
    COMPARATOR_CLASSES,
    IDENTITY_CLASS_LOCK_LEVELS,
    evaluate_post_render,
    validate_continuity_sequence,
    validate_manifest,
)

ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT / "qa" / "visual" / "VISUAL_IDENTITY_LOCK_MANIFEST_v1.json"
CONTRACT_PATH = ROOT / "docs" / "visual" / "VISUAL_IDENTITY_LOCK_CONTRACT_v1.md"


def valid_scene_manifest():
    return {
        "SCENE_ID": "visual-regression-scene-1",
        "CONTINUITY_GROUP_ID": "combat-sequence-1",
        "PLAYER_SAFE_SCENE": True,
        "PLAYER_KNOWLEDGE_PROJECTION_ID": "PKP-regression-1",
        "CANON_DIRECTION": "CANON_TO_VISUAL_ONLY",
        "VISUAL_TO_CANON": False,
        "PROJECT_SOURCE_SLOT_DELTA": 0,
        "ENTITIES": [
            {
                "ENTITY_ID": "PC_AELIAN",
                "ENTITY_CLASS": "PC",
                "CURRENT_FORM": "BASE",
                "IDENTITY_LOCK_LEVEL": "VERY_STRICT",
                "REQUIRED_REFERENCE_AUTHORITY": "VIS_PC_AELIAN_v1",
                "ACTUAL_REFERENCE_ASSET": "VIS_PC_AELIAN_v1.jpeg",
                "CURRENT_VISIBLE_STATE_SOURCE": "COMMITTED_RUNTIME_OR_SAVE",
                "HANDOFF_STATUS": "PASSED",
                "REFERENCE_MODE": "APPROVED_CANON_VISUAL_MASTER",
                "GENERIC_CLASS_SUBSTITUTE_ALLOWED": False,
                "CAMPAIGN_ANCHOR_STATUS": "N/A",
            },
            {
                "ENTITY_ID": "NPC_KRUNG_YUNG",
                "ENTITY_CLASS": "NAMED_RECURRING_MONSTER",
                "CURRENT_FORM": "ETTIN_BASE_FORM",
                "IDENTITY_LOCK_LEVEL": "STRICT",
                "REQUIRED_REFERENCE_AUTHORITY": "MM_OFFICIAL_ETTIN_SPECIES",
                "ACTUAL_REFERENCE_ASSET": "official_ettin_reference_crop.png",
                "CURRENT_VISIBLE_STATE_SOURCE": "COMMITTED_RUNTIME_OR_SAVE",
                "HANDOFF_STATUS": "PASSED",
                "REFERENCE_MODE": "CAMPAIGN_ANCHOR_PLUS_OFFICIAL_SPECIES",
                "STYLE_TRANSFORM_ALLOWED": True,
                "SPECIES_DRIFT_ALLOWED": False,
                "FORM_DRIFT_ALLOWED": False,
                "CAMPAIGN_ANCHOR_STATUS": "APPROVED",
                "CAMPAIGN_VISUAL_ANCHOR_ID": "VIS_NPC_KRUNG_YUNG_v1",
                "CAMPAIGN_VISUAL_ANCHOR_ASSET": "VIS_NPC_KRUNG_YUNG_v1.jpeg",
                "ANCHOR_OVERRIDES_SPECIES_AUTHORITY": False,
            },
        ],
    }


def complete_receipts():
    return {
        "PC_AELIAN": {
            "COMPARATORS": {
                "PC_IDENTITY": "PASS",
                "SPECIES_FORM_IDENTITY": "NA",
                "RECURRING_INSTANCE_IDENTITY": "NA",
                "VISIBLE_EQUIPMENT_STATE": "PASS",
                "SCENE_CONTINUITY": "PASS",
                "PLAYER_SAFE_CONTENT": "PASS",
            },
            "FAILURE_FLAGS": [],
        },
        "NPC_KRUNG_YUNG": {
            "COMPARATORS": {
                "PC_IDENTITY": "NA",
                "SPECIES_FORM_IDENTITY": "PASS",
                "RECURRING_INSTANCE_IDENTITY": "PASS",
                "VISIBLE_EQUIPMENT_STATE": "PASS",
                "SCENE_CONTINUITY": "PASS",
                "PLAYER_SAFE_CONTENT": "PASS",
            },
            "FAILURE_FLAGS": [],
        },
    }


class VisualIdentityLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        cls.contract = CONTRACT_PATH.read_text(encoding="utf-8")

    def test_candidate_does_not_consume_project_source_slot(self):
        self.assertEqual(self.policy["project_source_slot_delta"], 0)
        self.assertFalse(self.policy["active_runtime_mutation"])
        self.assertFalse(self.policy["campaign_canon_mutation"])
        self.assertFalse(self.policy["recovery_pr7_mutation"])
        self.assertIn("zero new Project Source slots", self.contract)

    def test_identity_class_enum_and_lock_levels_are_pinned(self):
        self.assertEqual(self.policy["identity_classes"], IDENTITY_CLASS_LOCK_LEVELS)

    def test_pc_visual_master_is_required(self):
        manifest = valid_scene_manifest()
        self.assertTrue(validate_manifest(manifest).passed)
        manifest["ENTITIES"][0]["REFERENCE_MODE"] = "GENERIC_CLASS_DESCRIPTION"
        result = validate_manifest(manifest)
        self.assertFalse(result.passed)
        self.assertIn("PC_AELIAN:PC_VISUAL_MASTER_REQUIRED", result.findings)

    def test_missing_required_reference_blocks_generation(self):
        manifest = valid_scene_manifest()
        manifest["ENTITIES"][0]["ACTUAL_REFERENCE_ASSET"] = None
        manifest["ENTITIES"][0]["HANDOFF_STATUS"] = "MISSING"
        result = validate_manifest(manifest)
        self.assertFalse(result.passed)
        self.assertIn("PC_AELIAN:REQUIRED_REFERENCE_HANDOFF_NOT_PASSED", result.findings)

    def test_complete_post_render_receipts_pass(self):
        result = evaluate_post_render(valid_scene_manifest(), complete_receipts())
        self.assertTrue(result.passed)

    def test_empty_observations_fail_closed(self):
        result = evaluate_post_render(valid_scene_manifest(), {})
        self.assertEqual(result.status, "REJECT_AND_REGENERATE")
        self.assertIn("PC_AELIAN:POST_RENDER_RECEIPT_MISSING", result.findings)
        self.assertIn("NPC_KRUNG_YUNG:POST_RENDER_RECEIPT_MISSING", result.findings)

    def test_missing_one_entity_receipt_fails_closed(self):
        receipts = complete_receipts()
        receipts.pop("NPC_KRUNG_YUNG")
        result = evaluate_post_render(valid_scene_manifest(), receipts)
        self.assertEqual(result.status, "REJECT_AND_REGENERATE")
        self.assertIn("NPC_KRUNG_YUNG:POST_RENDER_RECEIPT_MISSING", result.findings)

    def test_missing_required_comparator_class_fails_closed(self):
        receipts = complete_receipts()
        receipts["PC_AELIAN"]["COMPARATORS"].pop("PC_IDENTITY")
        result = evaluate_post_render(valid_scene_manifest(), receipts)
        self.assertIn("PC_AELIAN:MISSING_COMPARATOR_CLASS:PC_IDENTITY", result.findings)

    def test_missing_non_applicable_comparator_class_still_fails_coverage(self):
        receipts = complete_receipts()
        receipts["PC_AELIAN"]["COMPARATORS"].pop("SPECIES_FORM_IDENTITY")
        result = evaluate_post_render(valid_scene_manifest(), receipts)
        self.assertIn("PC_AELIAN:MISSING_COMPARATOR_CLASS:SPECIES_FORM_IDENTITY", result.findings)

    def test_unknown_comparator_class_fails_closed(self):
        receipts = complete_receipts()
        receipts["PC_AELIAN"]["COMPARATORS"]["TYPO_COMPARATOR"] = "PASS"
        result = evaluate_post_render(valid_scene_manifest(), receipts)
        self.assertIn("PC_AELIAN:UNKNOWN_COMPARATOR_CLASS:TYPO_COMPARATOR", result.findings)

    def test_unknown_comparator_status_fails_closed(self):
        receipts = complete_receipts()
        receipts["PC_AELIAN"]["COMPARATORS"]["PC_IDENTITY"] = "PAAAS"
        result = evaluate_post_render(valid_scene_manifest(), receipts)
        self.assertIn(
            "PC_AELIAN:UNKNOWN_COMPARATOR_STATUS:PC_IDENTITY:PAAAS",
            result.findings,
        )

    def test_required_comparator_cannot_be_na(self):
        receipts = complete_receipts()
        receipts["PC_AELIAN"]["COMPARATORS"]["PC_IDENTITY"] = "NA"
        result = evaluate_post_render(valid_scene_manifest(), receipts)
        self.assertIn("PC_AELIAN:REQUIRED_COMPARATOR_NA:PC_IDENTITY", result.findings)

    def test_unknown_failure_flag_fails_closed(self):
        receipts = complete_receipts()
        receipts["PC_AELIAN"]["FAILURE_FLAGS"].append("TYPO_DRIFT_FLAG")
        result = evaluate_post_render(valid_scene_manifest(), receipts)
        self.assertIn("PC_AELIAN:UNKNOWN_FAILURE_FLAG:TYPO_DRIFT_FLAG", result.findings)

    def test_pc_dark_hair_generic_substitute_is_hard_fail_observation(self):
        receipts = complete_receipts()
        receipts["PC_AELIAN"]["COMPARATORS"]["PC_IDENTITY"] = "FAIL"
        receipts["PC_AELIAN"]["FAILURE_FLAGS"].append("PC_IDENTITY_DRIFT")
        result = evaluate_post_render(valid_scene_manifest(), receipts)
        self.assertEqual(result.status, "REJECT_AND_REGENERATE")
        self.assertIn("PC_AELIAN:PC_IDENTITY_DRIFT", result.findings)

    def test_monster_campaign_style_transform_passes_when_species_is_preserved(self):
        manifest = valid_scene_manifest()
        monster = manifest["ENTITIES"][1]
        self.assertTrue(monster["STYLE_TRANSFORM_ALLOWED"])
        self.assertFalse(monster["SPECIES_DRIFT_ALLOWED"])
        self.assertTrue(evaluate_post_render(manifest, complete_receipts()).passed)

    def test_monster_species_or_defining_anatomy_drift_is_rejected(self):
        receipts = complete_receipts()
        receipts["NPC_KRUNG_YUNG"]["COMPARATORS"]["SPECIES_FORM_IDENTITY"] = "FAIL"
        receipts["NPC_KRUNG_YUNG"]["FAILURE_FLAGS"].append("DEFINING_ANATOMY_DRIFT")
        result = evaluate_post_render(valid_scene_manifest(), receipts)
        self.assertIn("NPC_KRUNG_YUNG:DEFINING_ANATOMY_DRIFT", result.findings)

    def test_named_monster_anchor_drift_is_rejected(self):
        receipts = complete_receipts()
        receipts["NPC_KRUNG_YUNG"]["COMPARATORS"]["RECURRING_INSTANCE_IDENTITY"] = "FAIL"
        receipts["NPC_KRUNG_YUNG"]["FAILURE_FLAGS"].append("RECURRING_ANCHOR_DRIFT")
        result = evaluate_post_render(valid_scene_manifest(), receipts)
        self.assertIn("NPC_KRUNG_YUNG:RECURRING_ANCHOR_DRIFT", result.findings)

    def test_approved_anchor_cannot_override_species_authority(self):
        manifest = valid_scene_manifest()
        manifest["ENTITIES"][1]["ANCHOR_OVERRIDES_SPECIES_AUTHORITY"] = True
        result = validate_manifest(manifest)
        self.assertFalse(result.passed)
        self.assertIn("NPC_KRUNG_YUNG:ANCHOR_CANNOT_OVERRIDE_SPECIES", result.findings)

    def test_invented_visible_equipment_conflict_is_rejected(self):
        receipts = complete_receipts()
        receipts["PC_AELIAN"]["COMPARATORS"]["VISIBLE_EQUIPMENT_STATE"] = "FAIL"
        receipts["PC_AELIAN"]["FAILURE_FLAGS"].append("INVENTED_VISIBLE_EQUIPMENT_CONFLICT")
        result = evaluate_post_render(valid_scene_manifest(), receipts)
        self.assertEqual(result.status, "REJECT_AND_REGENERATE")

    def test_unknown_entity_class_is_rejected(self):
        manifest = valid_scene_manifest()
        manifest["ENTITIES"][1]["ENTITY_CLASS"] = "TOTALLY_UNKNOWN_CLASS"
        result = validate_manifest(manifest)
        self.assertIn("NPC_KRUNG_YUNG:UNKNOWN_ENTITY_CLASS", result.findings)

    def test_wrong_moderate_lock_level_is_rejected(self):
        manifest = valid_scene_manifest()
        monster = manifest["ENTITIES"][1]
        monster["ENTITY_CLASS"] = "STANDARD_MONSTER_SPECIES"
        monster["IDENTITY_LOCK_LEVEL"] = "STRICT"
        monster["CAMPAIGN_ANCHOR_STATUS"] = "N/A"
        result = validate_manifest(manifest)
        self.assertIn("NPC_KRUNG_YUNG:WRONG_IDENTITY_LOCK_LEVEL", result.findings)

    def test_wrong_loose_lock_level_is_rejected(self):
        manifest = valid_scene_manifest()
        monster = manifest["ENTITIES"][1]
        monster["ENTITY_CLASS"] = "GENERIC_MOB"
        monster["IDENTITY_LOCK_LEVEL"] = "MODERATE"
        monster["CAMPAIGN_ANCHOR_STATUS"] = "N/A"
        result = validate_manifest(manifest)
        self.assertIn("NPC_KRUNG_YUNG:WRONG_IDENTITY_LOCK_LEVEL", result.findings)

    def test_multipanel_reference_swap_is_rejected(self):
        first = valid_scene_manifest()
        second = copy.deepcopy(first)
        second["SCENE_ID"] = "visual-regression-scene-2"
        second["ENTITIES"][0]["ACTUAL_REFERENCE_ASSET"] = "wrong_aelian_reference.jpeg"
        result = validate_continuity_sequence([first, second])
        self.assertFalse(result.passed)
        self.assertIn("PC_AELIAN:PANEL_REFERENCE_SWAP", result.findings)

    def test_contract_keeps_monster_identity_separate_from_style(self):
        monster_policy = self.policy["monster_style_policy"]
        self.assertEqual(monster_policy["official_reference_role"], "IDENTITY_AUTHORITY_NOT_STYLE_AUTHORITY")
        self.assertTrue(monster_policy["campaign_style_transformation_allowed"])
        self.assertFalse(monster_policy["species_drift_allowed"])
        self.assertFalse(monster_policy["defining_anatomy_drift_allowed"])

    def test_comparator_policy_is_complete_and_fail_closed(self):
        policy = self.policy["post_render_comparator_receipt_policy"]
        self.assertEqual(set(policy["comparator_classes"]), COMPARATOR_CLASSES)
        self.assertEqual(set(policy["allowed_statuses"]), {"PASS", "FAIL", "NA"})
        self.assertTrue(policy["receipt_required_for_every_manifest_entity"])
        self.assertTrue(policy["all_comparator_classes_explicit"])
        self.assertTrue(policy["missing_coverage_fails_closed"])
        self.assertTrue(policy["unknown_comparator_or_status_fails_closed"])
        self.assertTrue(policy["unknown_failure_flag_fails_closed"])

    def test_required_regression_set_is_pinned(self):
        required = set(self.policy["required_regressions"])
        expected = {
            "PC_DARK_HAIR_SUBSTITUTE_REJECTED",
            "MONSTER_STYLE_TRANSFORM_SPECIES_PRESERVED_ACCEPTED",
            "MONSTER_SPECIES_DRIFT_REJECTED",
            "NAMED_MONSTER_ANCHOR_DRIFT_REJECTED",
            "MULTIPANEL_REFERENCE_SWAP_REJECTED",
            "MISSING_REQUIRED_REFERENCE_BLOCKS_GENERATION",
            "INVENTED_EQUIPMENT_REJECTED",
            "PROJECT_SOURCE_SLOT_DELTA_ZERO",
            "EMPTY_POST_RENDER_RECEIPTS_REJECTED",
            "MISSING_ENTITY_RECEIPT_REJECTED",
            "MISSING_COMPARATOR_CLASS_REJECTED",
            "UNKNOWN_COMPARATOR_CLASS_REJECTED",
            "UNKNOWN_COMPARATOR_STATUS_REJECTED",
            "UNKNOWN_FAILURE_FLAG_REJECTED",
            "UNKNOWN_ENTITY_CLASS_REJECTED",
            "WRONG_MODERATE_LOCK_LEVEL_REJECTED",
            "WRONG_LOOSE_LOCK_LEVEL_REJECTED",
        }
        self.assertEqual(required, expected)


if __name__ == "__main__":
    unittest.main()
