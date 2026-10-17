import json
import unittest
from pathlib import Path

from tools.visual.scene_continuity_guard import (
    evaluate_post_render,
    validate_sequence,
    validate_transition,
)
from qa.preflight.scl_fixture_factory import (
    add_post_render_proofs,
    gameplay_transition,
    valid_frame,
    valid_group,
    valid_proofs,
)

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "qa" / "visual" / "SCENE_CONTINUITY_LOCK_MANIFEST_v1.json"
CONTRACT_PATH = ROOT / "docs" / "visual" / "SCENE_CONTINUITY_LOCK_CONTRACT_v1.md"


class SceneContinuityEventRenderProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.contract = CONTRACT_PATH.read_text(encoding="utf-8")

    def test_forged_committed_event_status_is_rejected(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0", "REV-2")
        f1["TRACKED_ENTITIES"][0]["CURRENT_VISIBLE_WOUNDS_OR_MARKS"] = ["fresh cut"]
        proofs = valid_proofs(f0, f1)
        key = "ENTITY:PC_AELIAN:CURRENT_VISIBLE_WOUNDS_OR_MARKS"
        tr = {
            "CONTINUITY_GROUP_ID": "CG-001",
            "FROM_FRAME_ID": "FRAME-0",
            "TO_FRAME_ID": "FRAME-1",
            "CAUSES": [{
                "CAUSE_TYPE": "COMMITTED_GAMEPLAY_EVENT",
                "EVENT_ID": "EVENT-FAKE",
                "EVENT_COMMIT_STATUS": "COMMITTED",
                "APPLIED_EVENT_LEDGER_RECEIPT_STATUS": "PASS",
                "APPLIED_EVENT_LEDGER_RECEIPT_ID": "NOT-IN-LEDGER",
                "FROM_STATE_EPOCH": "REV-1",
                "TO_STATE_EPOCH": "REV-2",
                "AFFECTED_KEYS": [key],
            }],
        }
        result = validate_transition(f0, f1, tr, proofs)
        self.assertFalse(result.passed)
        self.assertTrue(any("SELF_ASSERTED_EVENT_STATUS_FORBIDDEN" in x for x in result.findings))
        self.assertTrue(any("RECEIPT_NOT_FOUND" in x for x in result.findings))

    def test_wrong_event_id_receipt_is_rejected(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0", "REV-2")
        f1["TRACKED_ENTITIES"][0]["CURRENT_VISIBLE_WOUNDS_OR_MARKS"] = ["fresh cut"]
        proofs = valid_proofs(f0, f1)
        key = "ENTITY:PC_AELIAN:CURRENT_VISIBLE_WOUNDS_OR_MARKS"
        tr, _ = gameplay_transition(f0, f1, key, proofs)
        tr["CAUSES"][0]["EVENT_ID"] = "EVENT-OTHER"
        result = validate_transition(f0, f1, tr, proofs)
        self.assertFalse(result.passed)
        self.assertTrue(any("APPLIED_RECEIPT_EVENT_ID_MISMATCH" in x for x in result.findings))

    def test_wrong_affected_key_receipt_is_rejected(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0", "REV-2")
        f1["TRACKED_ENTITIES"][0]["CURRENT_VISIBLE_WOUNDS_OR_MARKS"] = ["fresh cut"]
        proofs = valid_proofs(f0, f1)
        key = "ENTITY:PC_AELIAN:CURRENT_VISIBLE_WOUNDS_OR_MARKS"
        tr, rid = gameplay_transition(f0, f1, key, proofs)
        proofs["APPLIED_EVENT_LEDGER_RECEIPTS"][rid]["AFFECTED_KEYS"] = ["ENTITY:PC_AELIAN:CURRENT_FORM"]
        result = validate_transition(f0, f1, tr, proofs)
        self.assertFalse(result.passed)
        self.assertTrue(any("APPLIED_RECEIPT_AFFECTED_KEYS_MISMATCH" in x for x in result.findings))

    def test_authoritative_changeset_digest_mismatch_is_rejected(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0", "REV-2")
        f1["TRACKED_ENTITIES"][0]["CURRENT_VISIBLE_WOUNDS_OR_MARKS"] = ["fresh cut"]
        proofs = valid_proofs(f0, f1)
        key = "ENTITY:PC_AELIAN:CURRENT_VISIBLE_WOUNDS_OR_MARKS"
        tr, rid = gameplay_transition(f0, f1, key, proofs)
        proofs["APPLIED_EVENT_LEDGER_RECEIPTS"][rid]["AUTHORITATIVE_CHANGESET_DIGEST"] = "sha256:" + "0" * 64
        result = validate_transition(f0, f1, tr, proofs)
        self.assertFalse(result.passed)
        self.assertTrue(any("AUTHORITATIVE_CHANGESET_DIGEST_MISMATCH" in x for x in result.findings))

    def test_valid_committed_event_transition_is_accepted(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0", "REV-2")
        f1["TRACKED_ENTITIES"][0]["CURRENT_VISIBLE_WOUNDS_OR_MARKS"] = ["fresh cut"]
        proofs = valid_proofs(f0, f1)
        key = "ENTITY:PC_AELIAN:CURRENT_VISIBLE_WOUNDS_OR_MARKS"
        tr, _ = gameplay_transition(f0, f1, key, proofs)
        self.assertTrue(validate_transition(f0, f1, tr, proofs).passed)

    def test_state_epoch_change_without_committed_event_is_rejected(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0", "REV-2")
        proofs = valid_proofs(f0, f1)
        tr = {"CONTINUITY_GROUP_ID": "CG-001", "FROM_FRAME_ID": "FRAME-0", "TO_FRAME_ID": "FRAME-1", "CAUSES": []}
        result = validate_transition(f0, f1, tr, proofs)
        self.assertFalse(result.passed)
        self.assertTrue(any("STATE_EPOCH_CHANGE_WITHOUT_COMMITTED_EVENT" in x for x in result.findings))

    def test_replayed_applied_event_receipt_across_sequence_is_rejected(self):
        key = "ENTITY:PC_AELIAN:CURRENT_VISIBLE_WOUNDS_OR_MARKS"
        f0 = valid_frame(0, None, "REV-1")
        f1 = valid_frame(1, "FRAME-0", "REV-2")
        f1["TRACKED_ENTITIES"][0]["CURRENT_VISIBLE_WOUNDS_OR_MARKS"] = ["fresh cut"]
        f2 = valid_frame(2, "FRAME-1", "REV-1")
        f3 = valid_frame(3, "FRAME-2", "REV-2")
        f3["TRACKED_ENTITIES"][0]["CURRENT_VISIBLE_WOUNDS_OR_MARKS"] = ["fresh cut"]
        proofs = valid_proofs(f0, f1, f2, f3)

        tr01, rid01 = gameplay_transition(f0, f1, key, proofs, event_id="EVENT-77")
        tr12, rid12 = gameplay_transition(f1, f2, key, proofs, event_id="EVENT-78")
        proofs["APPLIED_EVENT_LEDGER_RECEIPTS"][rid12]["LOGICAL_COMMIT_INDEX"] = 78
        tr23, rid23 = gameplay_transition(f2, f3, key, proofs, event_id="EVENT-77")
        self.assertEqual(rid01, rid23)

        result = validate_sequence(valid_group(), [f0, f1, f2, f3], [tr01, tr12, tr23], proofs)
        self.assertFalse(result.passed)
        self.assertTrue(any("REPLAYED_APPLIED_EVENT_RECEIPT_ACROSS_SEQUENCE" in x for x in result.findings))
        self.assertTrue(any("REPLAYED_EVENT_ID_ACROSS_SEQUENCE" in x for x in result.findings))

    def test_non_monotonic_logical_commit_index_is_rejected(self):
        key = "ENTITY:PC_AELIAN:CURRENT_VISIBLE_WOUNDS_OR_MARKS"
        f0 = valid_frame(0, None, "REV-1")
        f1 = valid_frame(1, "FRAME-0", "REV-2")
        f1["TRACKED_ENTITIES"][0]["CURRENT_VISIBLE_WOUNDS_OR_MARKS"] = ["fresh cut"]
        f2 = valid_frame(2, "FRAME-1", "REV-3")
        proofs = valid_proofs(f0, f1, f2)
        tr01, _ = gameplay_transition(f0, f1, key, proofs, event_id="EVENT-77")
        tr12, rid12 = gameplay_transition(f1, f2, key, proofs, event_id="EVENT-78")
        proofs["APPLIED_EVENT_LEDGER_RECEIPTS"][rid12]["LOGICAL_COMMIT_INDEX"] = 76

        result = validate_sequence(valid_group(), [f0, f1, f2], [tr01, tr12], proofs)
        self.assertFalse(result.passed)
        self.assertTrue(any("NON_MONOTONIC_LOGICAL_COMMIT_INDEX" in x for x in result.findings))

    def test_valid_multi_event_monotonic_sequence_is_accepted(self):
        key = "ENTITY:PC_AELIAN:CURRENT_VISIBLE_WOUNDS_OR_MARKS"
        f0 = valid_frame(0, None, "REV-1")
        f1 = valid_frame(1, "FRAME-0", "REV-2")
        f1["TRACKED_ENTITIES"][0]["CURRENT_VISIBLE_WOUNDS_OR_MARKS"] = ["fresh cut"]
        f2 = valid_frame(2, "FRAME-1", "REV-3")
        proofs = valid_proofs(f0, f1, f2)
        tr01, _ = gameplay_transition(f0, f1, key, proofs, event_id="EVENT-77")
        tr12, rid12 = gameplay_transition(f1, f2, key, proofs, event_id="EVENT-78")
        proofs["APPLIED_EVENT_LEDGER_RECEIPTS"][rid12]["LOGICAL_COMMIT_INDEX"] = 78

        result = validate_sequence(valid_group(), [f0, f1, f2], [tr01, tr12], proofs)
        self.assertTrue(result.passed, result.findings)

    def test_post_render_valid_bound_receipts_are_accepted(self):
        frame = valid_frame()
        proofs = valid_proofs(frame)
        receipt = add_post_render_proofs(proofs, frame)
        self.assertTrue(evaluate_post_render(frame, receipt, proofs).passed)

    def test_foreign_vil_receipt_from_another_frame_is_rejected(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0")
        proofs = valid_proofs(f0, f1)
        r0 = add_post_render_proofs(proofs, f0)
        r1 = add_post_render_proofs(proofs, f1)
        r1["VISUAL_IDENTITY_LOCK_RECEIPT_ID"] = r0["VISUAL_IDENTITY_LOCK_RECEIPT_ID"]
        result = evaluate_post_render(f1, r1, proofs)
        self.assertFalse(result.passed)
        self.assertTrue(any("VIL:FRAME_ID_BINDING_MISMATCH" in x for x in result.findings))

    def test_reused_entity_continuity_receipt_is_rejected(self):
        f0 = valid_frame()
        f1 = valid_frame(1, "FRAME-0")
        proofs = valid_proofs(f0, f1)
        r0 = add_post_render_proofs(proofs, f0)
        r1 = add_post_render_proofs(proofs, f1)
        r1["ENTITY_CONTINUITY_RECEIPT_IDS"]["PC_AELIAN"] = r0["ENTITY_CONTINUITY_RECEIPT_IDS"]["PC_AELIAN"]
        result = evaluate_post_render(f1, r1, proofs)
        self.assertFalse(result.passed)
        self.assertTrue(any("ENTITY_RENDER:PC_AELIAN:FRAME_ID_BINDING_MISMATCH" in x for x in result.findings))

    def test_render_artifact_hash_mismatch_is_rejected(self):
        frame = valid_frame()
        proofs = valid_proofs(frame)
        receipt = add_post_render_proofs(proofs, frame)
        receipt["RENDER_ARTIFACT_HASH"] = "sha256:" + "f" * 64
        result = evaluate_post_render(frame, receipt, proofs)
        self.assertFalse(result.passed)
        self.assertTrue(any("RENDER_ARTIFACT_HASH_BINDING_MISMATCH" in x for x in result.findings))

    def test_post_render_missing_entity_receipt_is_rejected(self):
        frame = valid_frame()
        proofs = valid_proofs(frame)
        receipt = add_post_render_proofs(proofs, frame)
        receipt["ENTITY_CONTINUITY_RECEIPT_IDS"] = {}
        result = evaluate_post_render(frame, receipt, proofs)
        self.assertFalse(result.passed)
        self.assertIn("FRAME-0:MISSING_ENTITY_CONTINUITY_RECEIPT:PC_AELIAN", result.findings)

    def test_post_render_missing_scene_fact_receipt_is_rejected(self):
        frame = valid_frame()
        proofs = valid_proofs(frame)
        receipt = add_post_render_proofs(proofs, frame)
        receipt["SCENE_FACT_CONTINUITY_RECEIPT_IDS"].pop("SCENE-FIRE-1")
        result = evaluate_post_render(frame, receipt, proofs)
        self.assertFalse(result.passed)
        self.assertIn("FRAME-0:MISSING_SCENE_FACT_CONTINUITY_RECEIPT:SCENE-FIRE-1", result.findings)

    def test_post_render_extra_receipt_is_rejected(self):
        frame = valid_frame()
        proofs = valid_proofs(frame)
        receipt = add_post_render_proofs(proofs, frame)
        receipt["ENTITY_CONTINUITY_RECEIPT_IDS"]["HIDDEN_BOSS"] = "ECR-FAKE"
        result = evaluate_post_render(frame, receipt, proofs)
        self.assertFalse(result.passed)
        self.assertIn("FRAME-0:EXTRA_ENTITY_CONTINUITY_RECEIPT:HIDDEN_BOSS", result.findings)

    def test_required_regression_set_is_pinned(self):
        expected = {
            "VALID_CAMERA_ONLY_SEQUENCE_ACCEPTED",
            "PLAYER_SAFE_GROUP_PROVENANCE_REQUIRED",
            "FRAME_PKP_BRANCH_AND_EPOCH_BINDING_REQUIRED",
            "EXTERNAL_PKP_AND_LEAK_RECEIPTS_REQUIRED",
            "DUPLICATE_ENTITY_OR_FACT_ID_REJECTED",
            "UNKNOWN_SCENE_FACT_CLASS_REJECTED",
            "HIDDEN_FACT_WITH_FAKE_PASS_SOURCE_REJECTED",
            "FOREIGN_EVS_RECEIPT_REJECTED",
            "UNTRACKED_IN_FRAME_ENTITY_OR_FACT_REJECTED",
            "FRAME_CHAIN_GAP_OR_DUPLICATE_INDEX_REJECTED",
            "IDENTITY_AUTHORITY_DRIFT_REJECTED",
            "CAMPAIGN_ANCHOR_DRIFT_REJECTED",
            "DYNAMIC_ENTITY_CHANGE_WITHOUT_EVENT_REJECTED",
            "DYNAMIC_SCENE_FACT_CHANGE_WITHOUT_EVENT_REJECTED",
            "IMMUTABLE_STRUCTURE_CHANGE_REJECTED",
            "CAMERA_ONLY_GAMEPLAY_KEY_REJECTED",
            "UNKNOWN_TRANSITION_CAUSE_REJECTED",
            "FORGED_COMMITTED_EVENT_STATUS_REJECTED",
            "WRONG_EVENT_ID_RECEIPT_REJECTED",
            "WRONG_AFFECTED_KEY_RECEIPT_REJECTED",
            "AUTHORITATIVE_CHANGESET_DIGEST_MISMATCH_REJECTED",
            "STATE_EPOCH_CHANGE_WITHOUT_COMMITTED_EVENT_REJECTED",
            "REPLAYED_APPLIED_EVENT_RECEIPT_ACROSS_SEQUENCE_REJECTED",
            "NON_MONOTONIC_LOGICAL_COMMIT_INDEX_REJECTED",
            "VALID_MULTI_EVENT_MONOTONIC_SEQUENCE_ACCEPTED",
            "POST_RENDER_VALID_BOUND_RECEIPTS_ACCEPTED",
            "FOREIGN_VIL_RECEIPT_FROM_ANOTHER_FRAME_REJECTED",
            "REUSED_ENTITY_CONTINUITY_RECEIPT_REJECTED",
            "RENDER_ARTIFACT_HASH_MISMATCH_REJECTED",
            "POST_RENDER_MISSING_ENTITY_RECEIPT_REJECTED",
            "POST_RENDER_MISSING_SCENE_FACT_RECEIPT_REJECTED",
            "POST_RENDER_EXTRA_RECEIPT_REJECTED",
            "RENDER_FAILURE_NONMUTATING_POLICY_PINNED",
            "PROJECT_SOURCE_SLOT_DELTA_ZERO"
        }
        self.assertEqual(set(self.manifest["required_regressions"]), expected)


if __name__ == "__main__":
    unittest.main()
