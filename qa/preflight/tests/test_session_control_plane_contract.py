import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "qa" / "architecture" / "SESSION_CONTROL_PLANE_MANIFEST_v1.json"
CONTROL_PATH = ROOT / "docs" / "architecture" / "SESSION_CONTROL_PLANE_CONTRACT_v1.md"
EVENT_PATH = ROOT / "docs" / "architecture" / "EVENT_ENVELOPE_CONTRACT_v1.md"
POLICY_PATH = ROOT / "docs" / "SOURCE_OF_TRUTH_POLICY.md"

EXPECTED_PIPELINE = [
    "COMMAND", "EVENT_ENVELOPE", "VALIDATION", "TRANSACTION_STAGE",
    "LEDGER_STAGE_PREPARED", "ATOMIC_COMMIT", "CHECKPOINT_BARRIER",
    "PLAYER_PROJECTION",
]

REQUIRED_REGRESSIONS = {
    "CHECKPOINT_BLOCKED_WHILE_PREPARED_OR_COMMITTING",
    "COMMITTED_EVENT_SURVIVES_CHECKPOINT_FAILURE",
    "CHECKPOINT_RETRY_DOES_NOT_REAPPLY_GAMEPLAY",
    "CHECKPOINT_MATCHES_COMMITTED_EVENT_LEDGER_AND_REVISION",
    "DUPLICATE_COMMITTED_EVENT_ID_NOOP",
}


def policy_value(text: str, key: str) -> str:
    m = re.search(rf"`{re.escape(key)}\s*=\s*([^`]+)`", text)
    if not m:
        raise AssertionError(f"{key} missing from source-of-truth policy")
    return m.group(1).strip()


class RuntimeBoundaryHarness:
    """Executable contract model only; not active runtime code."""

    def __init__(self):
        self.tx_status = "IDLE"
        self.pending_event = None
        self.logical_commit_index = 0
        self.last_committed_event_id = None
        self.applied_event_ledger = {}
        self.gameplay_mutations = 0
        self.rng_consumptions = 0
        self.resource_spends = 0
        self.movements = 0
        self.checkpoint = None

    def prepare(self, event_id: str):
        if event_id in self.applied_event_ledger:
            return "IDEMPOTENT_REPLAY_NOOP"
        self.tx_status = "PREPARED"
        self.pending_event = event_id
        return "PREPARED"

    def begin_commit(self):
        if self.tx_status != "PREPARED":
            raise AssertionError("commit requires PREPARED")
        self.tx_status = "COMMITTING"

    def finish_commit(self):
        if self.tx_status != "COMMITTING":
            raise AssertionError("finish_commit requires COMMITTING")
        event_id = self.pending_event
        self.logical_commit_index += 1
        self.last_committed_event_id = event_id
        self.gameplay_mutations += 1
        self.rng_consumptions += 1
        self.resource_spends += 1
        self.movements += 1
        self.applied_event_ledger[event_id] = {
            "status": "COMMITTED",
            "logical_commit_index": self.logical_commit_index,
        }
        self.tx_status = "COMMITTED"
        self.pending_event = None
        return "COMMITTED"

    def checkpoint_attempt(self, write_ok: bool):
        if self.tx_status in {"PREPARED", "COMMITTING"}:
            return {"status": "DEFERRED_TX_NOT_AT_BOUNDARY"}
        if self.tx_status not in {"COMMITTED", "ABORTED", "IDLE"}:
            raise AssertionError("invalid checkpoint boundary")

        payload = {
            "logical_commit_index": self.logical_commit_index,
            "last_committed_event_id": self.last_committed_event_id,
            "applied_event_ledger": json.loads(json.dumps(self.applied_event_ledger)),
        }
        if not write_ok:
            return {"status": "CHECKPOINT_RETRY_REQUIRED", "candidate": payload}
        self.checkpoint = payload
        return {"status": "COMMITTED", "checkpoint": payload}


class SessionControlPlaneContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.control = CONTROL_PATH.read_text(encoding="utf-8")
        cls.event = EVENT_PATH.read_text(encoding="utf-8")
        cls.policy = POLICY_PATH.read_text(encoding="utf-8")

    def test_pipeline_order_is_exact(self):
        self.assertEqual(self.manifest["pipeline"], EXPECTED_PIPELINE)
        self.assertIn(" -> ".join(EXPECTED_PIPELINE), self.control)

    def test_precommit_serialization_is_non_authoritative(self):
        s = self.manifest["optional_precommit_stage"]
        self.assertEqual(s["name"], "PRECOMMIT_SERIALIZATION_VALIDATION")
        self.assertFalse(s["checkpoint_authority"])
        self.assertFalse(s["save_authority"])
        self.assertFalse(s["may_set_checkpoint_committed"])

    def test_runtime_rule_binding_and_required_regressions(self):
        self.assertEqual(
            self.manifest["active_runtime_execution_rules"],
            ["SYS.NATIVE.R107", "SYS.NATIVE.R108", "SYS.NATIVE.R109", "SAVE.NATIVE.R110"],
        )
        self.assertEqual(set(self.manifest["required_runtime_alignment_regressions"]), REQUIRED_REGRESSIONS)
        self.assertEqual(set(self.manifest["checkpoint_forbidden_tx_statuses"]), {"PREPARED", "COMMITTING"})

    def test_event_envelope_fields_present(self):
        for field in self.manifest["event_envelope_required_fields"]:
            self.assertIn(f"`{field}`", self.event)

    def test_source_of_truth_policy_is_not_overridden(self):
        migration_mode = policy_value(self.policy, "MIGRATION_MODE")
        github_cutover = policy_value(self.policy, "GITHUB_CUTOVER")
        self.assertEqual(self.manifest["migration_mode_expected"], migration_mode)
        self.assertEqual(self.manifest["github_cutover_expected"], github_cutover)
        if github_cutover != "APPROVED":
            self.assertEqual(self.manifest["authoritative_source_expected"], "Project Canon")

    def test_contract_is_not_activated(self):
        self.assertFalse(self.manifest["active_runtime_mutation"])
        self.assertFalse(self.manifest["campaign_canon_mutation"])
        self.assertFalse(self.manifest["runtime_promotion"])
        self.assertFalse(self.manifest["gate_status_mutation"])

    def test_checkpoint_blocked_while_prepared_or_committing(self):
        h = RuntimeBoundaryHarness()
        h.prepare("evt-1")
        self.assertEqual(h.checkpoint_attempt(True)["status"], "DEFERRED_TX_NOT_AT_BOUNDARY")
        h.begin_commit()
        self.assertEqual(h.checkpoint_attempt(True)["status"], "DEFERRED_TX_NOT_AT_BOUNDARY")
        self.assertIsNone(h.checkpoint)

    def test_committed_event_survives_checkpoint_failure(self):
        h = RuntimeBoundaryHarness()
        h.prepare("evt-2")
        h.begin_commit()
        h.finish_commit()
        result = h.checkpoint_attempt(False)
        self.assertEqual(result["status"], "CHECKPOINT_RETRY_REQUIRED")
        self.assertIn("evt-2", h.applied_event_ledger)
        self.assertEqual(h.applied_event_ledger["evt-2"]["status"], "COMMITTED")
        self.assertEqual(h.logical_commit_index, 1)
        self.assertEqual(h.gameplay_mutations, 1)

    def test_checkpoint_retry_does_not_reapply_gameplay(self):
        h = RuntimeBoundaryHarness()
        h.prepare("evt-3")
        h.begin_commit()
        h.finish_commit()
        h.checkpoint_attempt(False)
        before = (h.gameplay_mutations, h.rng_consumptions, h.resource_spends, h.movements)
        retry = h.checkpoint_attempt(True)
        after = (h.gameplay_mutations, h.rng_consumptions, h.resource_spends, h.movements)
        self.assertEqual(retry["status"], "COMMITTED")
        self.assertEqual(before, after)

    def test_successful_checkpoint_matches_committed_revision_and_ledger(self):
        h = RuntimeBoundaryHarness()
        h.prepare("evt-4")
        h.begin_commit()
        h.finish_commit()
        result = h.checkpoint_attempt(True)
        cp = result["checkpoint"]
        self.assertEqual(cp["logical_commit_index"], h.logical_commit_index)
        self.assertEqual(cp["last_committed_event_id"], "evt-4")
        self.assertEqual(cp["applied_event_ledger"], h.applied_event_ledger)
        self.assertEqual(cp["applied_event_ledger"]["evt-4"]["logical_commit_index"], cp["logical_commit_index"])

    def test_duplicate_committed_event_is_noop(self):
        h = RuntimeBoundaryHarness()
        h.prepare("evt-5")
        h.begin_commit()
        h.finish_commit()
        before = (h.gameplay_mutations, h.rng_consumptions, h.resource_spends, h.movements)
        self.assertEqual(h.prepare("evt-5"), "IDEMPOTENT_REPLAY_NOOP")
        self.assertEqual(before, (h.gameplay_mutations, h.rng_consumptions, h.resource_spends, h.movements))


if __name__ == "__main__":
    unittest.main()
