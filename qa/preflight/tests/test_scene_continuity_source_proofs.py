import copy
import json
import unittest
from pathlib import Path

from tools.visual.scene_continuity_guard import (
    fact_value_digest,
    validate_continuity_group,
    validate_frame,
    validate_sequence,
    validate_transition,
)
from qa.preflight.scl_fixture_factory import (
    add_entity_fact_proofs,
    add_player_safe_proofs,
    camera_transition,
    dynamic_fact,
    empty_proofs,
    valid_frame,
    valid_group,
    valid_proofs,
)

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "qa" / "visual" / "SCENE_CONTINUITY_LOCK_MANIFEST_v1.json"
CONTRACT_PATH = ROOT / "docs" / "visual" / "SCENE_CONTINUITY_LOCK_CONTRACT_v1.md"


class SceneContinuitySourceProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.contract = CONTRACT_PATH.read_text(encoding="utf-8")

    def test_source_budget_and_scope_stay_zero(self):
        self.assertEqual(self.manifest["project_source_slot_delta"], 0)
        self.assertFalse(self.manifest["active_runtime_mutation"])
        self.assertFalse(self.manifest["campaign_canon_mutation"])
        self.assertFalse(self.manifest["recovery_mutation"])
        self.assertIn("zero new Project Source slots", self.contract)

    def test_valid_camera_only_sequence_is_accepted(self):
        group = valid_group()
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0")
        f1["CAMERA_SHOT_ID"] = "CLOSE-1"
        proofs = valid_proofs(f0, f1)
        self.assertTrue(validate_sequence(group, [f0, f1], [camera_transition(f0, f1, "CAMERA_SHOT_ID")], proofs).passed)

    def test_player_safe_group_provenance_is_required(self):
        group = valid_group()
        proofs = valid_proofs(valid_frame())
        group["PLAYER_KNOWLEDGE_PROJECTION_ID"] = None
        group["KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS"] = "NOT_RUN"
        result = validate_continuity_group(group, proofs)
        self.assertFalse(result.passed)
        self.assertIn("GROUP:PKP_ID_REQUIRED", result.findings)
        self.assertIn("GROUP:LEAK_GATE_PASS_REQUIRED", result.findings)

    def test_frame_pkp_branch_and_epoch_binding_is_required(self):
        frame = valid_frame()
        proofs = valid_proofs(frame)
        frame["PLAYER_KNOWLEDGE_PROJECTION_OBSERVER_BRANCH_ID"] = "OTHER"
        frame["PLAYER_KNOWLEDGE_PROJECTION_SOURCE_STATE_EPOCH"] = "REV-OLD"
        result = validate_frame(frame, proofs)
        self.assertFalse(result.passed)
        self.assertIn("FRAME-0:PKP_OBSERVER_BRANCH_MISMATCH", result.findings)
        self.assertIn("FRAME-0:PKP_STATE_EPOCH_MISMATCH", result.findings)

    def test_external_pkp_and_leak_receipts_are_required(self):
        result = validate_frame(valid_frame(), empty_proofs())
        self.assertFalse(result.passed)
        self.assertTrue(any("PKP_RECEIPTS_RECEIPT_NOT_FOUND" in x for x in result.findings))
        self.assertTrue(any("LEAK_GATE_RECEIPTS_RECEIPT_NOT_FOUND" in x for x in result.findings))

    def test_duplicate_entity_or_fact_id_is_rejected(self):
        frame = valid_frame()
        frame["TRACKED_ENTITIES"].append(copy.deepcopy(frame["TRACKED_ENTITIES"][0]))
        frame["SCENE_FACTS"].append(copy.deepcopy(frame["SCENE_FACTS"][0]))
        result = validate_frame(frame, valid_proofs(valid_frame()))
        self.assertFalse(result.passed)
        self.assertTrue(any("DUPLICATE_ENTITY_ID" in x for x in result.findings))
        self.assertTrue(any("DUPLICATE_FACT_ID" in x for x in result.findings))

    def test_unknown_scene_fact_class_is_rejected(self):
        frame = valid_frame()
        proofs = valid_proofs(frame)
        frame["SCENE_FACTS"][1]["FACT_CLASS"] = "DM_SECRET_DECOR"
        result = validate_frame(frame, proofs)
        self.assertFalse(result.passed)
        self.assertIn("FRAME-0:SCENE-FIRE-1:UNKNOWN_SCENE_FACT_CLASS", result.findings)

    def test_hidden_fact_with_fake_pass_source_is_rejected(self):
        frame = valid_frame()
        proofs = valid_proofs(frame)
        hidden = dynamic_fact("REV-1", "SECRET_DOOR_PRESENT")
        hidden["FACT_ID"] = "SECRET-DOOR-DM"
        hidden["SOURCE_RECEIPT_ID"] = "FAKE-DM-RECEIPT"
        hidden["PLAYER_SAFE_SOURCE_STATUS"] = "PASS"
        frame["SCENE_FACTS"].append(hidden)
        proofs["PLAYER_SAFE_SOURCE_RECEIPTS"]["FAKE-DM-RECEIPT"] = {
            "RECEIPT_ID": "FAKE-DM-RECEIPT",
            "STATUS": "PASS",
            "FACT_ID": "SECRET-DOOR-DM",
            "FACT_CLASS": "DYNAMIC_PLAYER_SAFE",
            "VALUE_DIGEST": fact_value_digest(hidden),
            "PLAYER_KNOWLEDGE_PROJECTION_ID": frame["PLAYER_KNOWLEDGE_PROJECTION_ID"],
            "OBSERVER_BRANCH_ID": frame["OBSERVER_BRANCH_ID"],
            "SOURCE_STATE_EPOCH": frame["SOURCE_STATE_EPOCH"],
            "SOURCE_KIND": "SEALED_DM_STATE",
        }
        result = validate_frame(frame, proofs)
        self.assertFalse(result.passed)
        self.assertIn("FRAME-0:SECRET-DOOR-DM:DYNAMIC_SOURCE_KIND_INVALID", result.findings)

    def test_foreign_evs_receipt_is_rejected(self):
        frame = valid_frame(1, "FRAME-0", "REV-2")
        proofs = valid_proofs(frame)
        old_ctx = valid_frame()
        add_player_safe_proofs(proofs, old_ctx, "SOURCE_STATE_EPOCH")
        add_entity_fact_proofs(proofs, old_ctx, "TRACKED_ENTITIES", "SOURCE_STATE_EPOCH")
        frame["TRACKED_ENTITIES"][0]["EVS_VALIDATION_RECEIPT_ID"] = "EVS-AELIAN-REV-1"
        result = validate_frame(frame, proofs)
        self.assertFalse(result.passed)
        self.assertTrue(any("EVS_EPOCH_BINDING_MISMATCH" in x for x in result.findings))

    def test_untracked_in_frame_entity_or_fact_is_rejected(self):
        frame = valid_frame()
        proofs = valid_proofs(frame)
        frame["IN_FRAME_ENTITY_IDS"].append("HIDDEN_BOSS")
        frame["IN_FRAME_SCENE_FACT_IDS"].append("SECRET_DOOR")
        result = validate_frame(frame, proofs)
        self.assertFalse(result.passed)
        self.assertTrue(any("IN_FRAME_ENTITY_IDS_UNTRACKED" in x for x in result.findings))
        self.assertTrue(any("IN_FRAME_SCENE_FACT_IDS_UNTRACKED" in x for x in result.findings))

    def test_frame_chain_gap_or_duplicate_index_is_rejected(self):
        group = valid_group()
        f0 = valid_frame()
        f1 = valid_frame(0, "WRONG")
        result = validate_sequence(group, [f0, f1], [], valid_proofs(f0, f1))
        self.assertFalse(result.passed)
        self.assertTrue(any("DUPLICATE_FRAME_INDEX" in x for x in result.findings))
        self.assertTrue(any("PREVIOUS_FRAME_CHAIN_MISMATCH" in x for x in result.findings))

    def test_identity_authority_drift_is_rejected(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0")
        f1["TRACKED_ENTITIES"][0]["IDENTITY_AUTHORITY_ID"] = "GENERIC_BARBARIAN"
        tr = {"CONTINUITY_GROUP_ID": "CG-001", "FROM_FRAME_ID": "FRAME-0", "TO_FRAME_ID": "FRAME-1", "CAUSES": []}
        result = validate_sequence(valid_group(), [f0, f1], [tr], valid_proofs(f0, f1))
        self.assertFalse(result.passed)
        self.assertTrue(any("IDENTITY_AUTHORITY_DRIFT" in x or "SEQUENCE_IDENTITY_LINEAGE_DRIFT" in x for x in result.findings))

    def test_dynamic_entity_change_without_event_is_rejected(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0")
        f1["TRACKED_ENTITIES"][0]["CURRENT_VISIBLE_WOUNDS_OR_MARKS"] = ["fresh cut"]
        tr = {"CONTINUITY_GROUP_ID": "CG-001", "FROM_FRAME_ID": "FRAME-0", "TO_FRAME_ID": "FRAME-1", "CAUSES": []}
        result = validate_transition(f0, f1, tr, valid_proofs(f0, f1))
        self.assertFalse(result.passed)
        self.assertTrue(any("UNCAUSED_GAMEPLAY_CHANGE" in x for x in result.findings))

    def test_dynamic_scene_fact_change_without_event_is_rejected(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0")
        f1["SCENE_FACTS"][1] = dynamic_fact("REV-1", "BURNING")
        tr = {"CONTINUITY_GROUP_ID": "CG-001", "FROM_FRAME_ID": "FRAME-0", "TO_FRAME_ID": "FRAME-1", "CAUSES": []}
        result = validate_transition(f0, f1, tr, valid_proofs(f0, f1))
        self.assertFalse(result.passed)
        self.assertTrue(any("SCENE_FACT:SCENE-FIRE-1:VALUE" in x for x in result.findings))

    def test_immutable_structure_change_is_rejected(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0")
        f1["SCENE_FACTS"][0]["VALUE"] = "WALL_REMOVED"
        tr = {"CONTINUITY_GROUP_ID": "CG-001", "FROM_FRAME_ID": "FRAME-0", "TO_FRAME_ID": "FRAME-1", "CAUSES": []}
        result = validate_transition(f0, f1, tr, valid_proofs(f0, f1))
        self.assertFalse(result.passed)
        self.assertIn("STRUCTURE-WALL-NORTH:IMMUTABLE_STRUCTURE_CHANGED", result.findings)

    def test_camera_only_cannot_claim_gameplay_key(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0")
        tr = camera_transition(f0, f1, "CAMERA_SHOT_ID")
        tr["CAUSES"][0]["AFFECTED_KEYS"] = ["ENTITY:PC_AELIAN:CURRENT_FORM"]
        result = validate_transition(f0, f1, tr, valid_proofs(f0, f1))
        self.assertFalse(result.passed)
        self.assertTrue(any("CAMERA_ONLY_GAMEPLAY_KEY" in x for x in result.findings))

    def test_unknown_transition_cause_is_rejected(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0")
        tr = {"CONTINUITY_GROUP_ID": "CG-001", "FROM_FRAME_ID": "FRAME-0", "TO_FRAME_ID": "FRAME-1", "CAUSES": [{"CAUSE_TYPE": "TRUST_ME", "AFFECTED_KEYS": []}]}
        result = validate_transition(f0, f1, tr, valid_proofs(f0, f1))
        self.assertFalse(result.passed)
        self.assertTrue(any("UNKNOWN_CAUSE_TYPE" in x for x in result.findings))

    def test_render_failure_nonmutating_policy_is_pinned(self):
        self.assertIn("does not mutate gameplay", self.contract)
        self.assertIn("reroll RNG", self.contract)
        self.assertIn("roll back a committed event", self.contract)


if __name__ == "__main__":
    unittest.main()
