from __future__ import annotations

import copy
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SQL_PATH = ROOT / "runtime" / "sql" / "RUNTIME_INTEGRITY_BACKBONE_v1.sql"
PARITY_PATH = ROOT / "qa" / "engine_spec" / "runtime_integrity_parity.py"

spec = importlib.util.spec_from_file_location("runtime_integrity_parity", PARITY_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"cannot load {PARITY_PATH}")
parity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parity)

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64
HEX_E = "e" * 64


def snapshot() -> dict:
    owner_ids = ["pc:hero", "runtime"]
    return {
        "format": parity.FORMAT,
        "event_ids": ["evt-1"],
        "applied_event_ledger": [
            {
                "event_id": "evt-1",
                "ael_owner_id": "ael-main",
                "logical_revision": 1,
                "payload_sha256": HEX_A,
            }
        ],
        "transaction_receipts": [
            {
                "transaction_id": "tx-1",
                "event_id": "evt-1",
                "logical_revision": 1,
                "owner_ids": owner_ids,
                "owner_set_sha256": parity.owner_set_sha256(owner_ids),
                "transaction_status": "COMMITTED",
            }
        ],
        "last_committed_event_id": "evt-1",
        "logical_commit_revision": 1,
        "checkpoint": {
            "checkpoint_id": "cp-1",
            "status": "COMMITTED",
            "logical_revision": 1,
            "last_committed_event_id": "evt-1",
            "checkpoint_digest_sha256": HEX_B,
            "owner_binding_count": 2,
            "owner_state_hashes": {"runtime": HEX_C, "pc:hero": HEX_D},
        },
        "rng_receipts": [
            {
                "rng_stream_id": "main",
                "event_id": "evt-1",
                "logical_revision": 1,
                "rng_cursor": 7,
                "rng_state_sha256": HEX_D,
                "draw_receipt_sha256": HEX_E,
            }
        ],
        "unknown_values": {"legacy_timer": None, "opaque_field": "UNKNOWN"},
        "player_visibility_fingerprint_sha256": HEX_A,
        "topology_semantics_fingerprint_sha256": HEX_B,
    }


def mutate_transaction_owners(s: dict) -> None:
    owners = ["npc:ally", "pc:hero", "runtime"]
    s["transaction_receipts"][0]["owner_ids"] = owners
    s["transaction_receipts"][0]["owner_set_sha256"] = parity.owner_set_sha256(owners)
    s["checkpoint"]["owner_binding_count"] = len(owners)
    s["checkpoint"]["owner_state_hashes"]["npc:ally"] = HEX_E


def rewrite_event_identity(s: dict, event_id: str = "evt-2") -> None:
    s["event_ids"][0] = event_id
    s["applied_event_ledger"][0]["event_id"] = event_id
    s["transaction_receipts"][0]["event_id"] = event_id
    s["last_committed_event_id"] = event_id
    s["checkpoint"]["last_committed_event_id"] = event_id
    s["rng_receipts"][0]["event_id"] = event_id


def rewrite_logical_revision(s: dict, logical_revision: int = 2) -> None:
    s["logical_commit_revision"] = logical_revision
    s["applied_event_ledger"][0]["logical_revision"] = logical_revision
    s["transaction_receipts"][0]["logical_revision"] = logical_revision
    s["checkpoint"]["logical_revision"] = logical_revision
    s["rng_receipts"][0]["logical_revision"] = logical_revision


class RuntimeIntegrityBackboneDDLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = SQL_PATH.read_text(encoding="utf-8")

    def test_parent_phase_b_qa_head_is_exact_current_accepted_head(self) -> None:
        self.assertIn(
            "-- PARENT_ENGINE_PHASE_B_QA_HEAD=f548facf24f9e107f31744fd18fa2dc2a9d6bdca",
            self.sql,
        )
        self.assertNotIn(
            "-- PARENT_ENGINE_PHASE_B_QA_HEAD=853a21d7ac0fec398f5d8ac8a32500fa4a21a797",
            self.sql,
        )

    def test_initial_schema_creation_is_fail_closed_not_if_not_exists(self) -> None:
        self.assertIn("CREATE SCHEMA dnd_runtime;", self.sql)
        self.assertNotIn("CREATE SCHEMA IF NOT EXISTS dnd_runtime", self.sql)

    def test_only_first_slice_tables_are_materialized(self) -> None:
        tables = set(re.findall(r"CREATE TABLE dnd_runtime\.([a-z_]+)", self.sql))
        self.assertEqual(
            tables,
            {
                "session_revision",
                "event_commit",
                "applied_event_ledger",
                "transaction_receipt",
                "checkpoint_commit",
                "checkpoint_owner_state",
                "rng_state_receipt",
            },
        )
        forbidden = {
            "actor", "pc_sheet", "combat", "encounter", "inventory", "resource",
            "effect", "timer", "npc", "spatial", "topology", "knowledge", "pkp",
            "visual", "source_asset",
        }
        self.assertTrue(tables.isdisjoint(forbidden))

    def test_event_ael_transaction_checkpoint_exact_cycles_are_deferred(self) -> None:
        required_constraints = {
            "ael_event_fk",
            "event_ael_fk",
            "tx_event_fk",
            "event_tx_fk",
            "checkpoint_event_fk",
            "event_checkpoint_fk",
            "session_last_event_fk",
            "session_last_checkpoint_fk",
            "rng_event_fk",
        }
        for name in required_constraints:
            with self.subTest(name=name):
                pattern = (
                    rf"ADD CONSTRAINT {name}\b"
                    rf".*?DEFERRABLE INITIALLY DEFERRED;"
                )
                self.assertRegex(self.sql, re.compile(pattern, re.S))

    def test_save_barrier_owner_membership_is_deferred_and_cardinality_bound(self) -> None:
        self.assertIn(
            "CREATE FUNCTION dnd_runtime.assert_save_barrier_owner_membership()",
            self.sql,
        )
        self.assertIn("v_owner_binding_count <> v_checkpoint_owner_count", self.sql)
        self.assertIn("v_owner_binding_count <> cardinality(v_tx_owner_ids_canonical)", self.sql)
        self.assertIn("v_tx_owner_ids_canonical <> v_checkpoint_owner_ids", self.sql)
        for trigger_name, table_name in (
            ("transaction_receipt_save_barrier_owner_ck", "transaction_receipt"),
            ("checkpoint_commit_save_barrier_owner_ck", "checkpoint_commit"),
            ("checkpoint_owner_state_save_barrier_owner_ck", "checkpoint_owner_state"),
        ):
            with self.subTest(trigger_name=trigger_name):
                pattern = (
                    rf"CREATE CONSTRAINT TRIGGER {trigger_name}\s+"
                    rf"AFTER INSERT ON dnd_runtime\.{table_name}\s+"
                    rf"DEFERRABLE INITIALLY DEFERRED\s+"
                    rf"FOR EACH ROW EXECUTE FUNCTION "
                    rf"dnd_runtime\.assert_save_barrier_owner_membership\(\);"
                )
                self.assertRegex(self.sql, re.compile(pattern, re.S))

    def test_committed_evidence_families_are_append_only(self) -> None:
        self.assertIn("CREATE FUNCTION dnd_runtime.reject_committed_row_mutation()", self.sql)
        for table in (
            "event_commit",
            "applied_event_ledger",
            "transaction_receipt",
            "checkpoint_commit",
            "checkpoint_owner_state",
            "rng_state_receipt",
        ):
            self.assertIn(f"'{table}'", self.sql)
        self.assertIn("BEFORE UPDATE OR DELETE", self.sql)

    def test_no_cutover_or_neighbor_authority_is_materialized(self) -> None:
        self.assertIn("-- SQL_PRIMARY_AUTHORIZATION=NO", self.sql)
        self.assertIn("-- RUNTIME_PROMOTION_AUTHORIZATION=NO", self.sql)
        self.assertIn("-- SHARED_NEON_MUTATION_AUTHORIZATION=NO", self.sql)
        self.assertNotRegex(self.sql, re.compile(r"CREATE\s+(?:TABLE|SCHEMA)\s+dnd_(?:knowledge|source|topology)\b", re.I))
        self.assertNotRegex(self.sql, re.compile(r"\bUPDATE\s+integrations\b", re.I))

    def test_migration_is_one_explicit_transaction(self) -> None:
        stripped = self.sql.strip()
        self.assertIn("\nBEGIN;\n", "\n" + stripped)
        self.assertTrue(stripped.endswith("COMMIT;"))


class RuntimeIntegrityParityHarnessTests(unittest.TestCase):
    def test_exact_snapshot_passes(self) -> None:
        s = snapshot()
        result = parity.compare(s, copy.deepcopy(s))
        self.assertEqual(result["status"], "PASS", result)
        self.assertTrue(all(result["checks"].values()))

    def test_each_normative_parity_axis_fails_closed(self) -> None:
        cases = {
            "EXACT_EVENT_ID_SET_EQUALITY":
                rewrite_event_identity,
            "APPLIED_EVENT_LEDGER_ORDER_AND_MEMBERSHIP_EQUALITY":
                lambda s: s["applied_event_ledger"][0].__setitem__("ael_owner_id", "other"),
            "MULTI_OWNER_TRANSACTION_RECEIPT_EQUALITY":
                mutate_transaction_owners,
            "LAST_COMMITTED_EVENT_ID_EQUALITY":
                rewrite_event_identity,
            "LOGICAL_COMMIT_REVISION_EQUALITY":
                rewrite_logical_revision,
            "CHECKPOINT_ID_AND_STATUS_EQUALITY":
                lambda s: s["checkpoint"].__setitem__("checkpoint_id", "cp-other"),
            "OWNER_STATE_HASH_BINDING_EQUALITY":
                lambda s: s["checkpoint"]["owner_state_hashes"].__setitem__("runtime", HEX_E),
            "RNG_RECEIPT_AND_CURSOR_EQUALITY":
                lambda s: s["rng_receipts"][0].__setitem__("rng_cursor", 8),
            "EXPLICIT_UNKNOWN_VALUES_PRESERVED_WITHOUT_FABRICATION":
                lambda s: s["unknown_values"].__setitem__("fabricated", 1),
            "NO_PLAYER_VISIBILITY_EXPANSION":
                lambda s: s.__setitem__("player_visibility_fingerprint_sha256", HEX_C),
            "NO_TOPOLOGY_SEMANTIC_REASSIGNMENT":
                lambda s: s.__setitem__("topology_semantics_fingerprint_sha256", HEX_C),
        }
        base = snapshot()
        for check, mutate in cases.items():
            with self.subTest(check=check):
                altered = copy.deepcopy(base)
                mutate(altered)
                result = parity.compare(base, altered)
                self.assertEqual(result["status"], "FAIL", result)
                self.assertIn(f"PARITY_MISMATCH:{check}", result["findings"])

    def test_duplicate_event_and_rng_identity_are_rejected_before_compare(self) -> None:
        s = snapshot()
        s["event_ids"].append("evt-1")
        result = parity.compare(s, snapshot())
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("FILE:EVENT_ID_DUPLICATE", result["findings"])

        s = snapshot()
        s["rng_receipts"].append(copy.deepcopy(s["rng_receipts"][0]))
        result = parity.compare(s, snapshot())
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("FILE:RNG_STREAM_REVISION_DUPLICATE", result["findings"])

    def test_unknown_fields_fail_closed(self) -> None:
        s = snapshot()
        s["authority_override"] = "SQL_PRIMARY"
        result = parity.compare(s, snapshot())
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("FILE:SNAPSHOT_KEY_SET_MISMATCH", result["findings"])

    def test_identically_corrupt_cross_family_snapshots_fail_closed(self) -> None:
        cases = {
            "AEL_EVENT_SET_MISMATCH":
                lambda s: s["applied_event_ledger"][0].__setitem__("event_id", "evt-other"),
            "LAST_COMMITTED_EVENT_NOT_IN_EVENT_SET":
                lambda s: s.__setitem__("last_committed_event_id", "evt-other"),
            "CHECKPOINT_LOGICAL_REVISION_MISMATCH":
                lambda s: s["checkpoint"].__setitem__("logical_revision", 2),
            "CHECKPOINT_LAST_EVENT_MISMATCH":
                lambda s: s["checkpoint"].__setitem__("last_committed_event_id", "evt-other"),
            "TRANSACTION_EVENT_SET_MISMATCH":
                lambda s: s["transaction_receipts"][0].__setitem__("event_id", "evt-other"),
            "TRANSACTION_OWNER_SET_DIGEST_MISMATCH":
                lambda s: s["transaction_receipts"][0]["owner_ids"].append("npc:ally"),
            "RNG_EVENT_NOT_IN_EVENT_SET":
                lambda s: s["rng_receipts"][0].__setitem__("event_id", "evt-other"),
            "RNG_EVENT_REVISION_MISMATCH":
                lambda s: s["rng_receipts"][0].__setitem__("logical_revision", 2),
        }
        for expected_finding, mutate in cases.items():
            with self.subTest(expected_finding=expected_finding):
                corrupted = snapshot()
                mutate(corrupted)
                result = parity.compare(corrupted, copy.deepcopy(corrupted))
                self.assertEqual(result["status"], "FAIL", result)
                self.assertTrue(
                    any(item.endswith(expected_finding) for item in result["findings"]),
                    result,
                )

    def test_identical_transaction_checkpoint_owner_corruption_fails_closed(self) -> None:
        substitution = snapshot()
        substitution["checkpoint"]["owner_state_hashes"] = {
            "runtime": HEX_C,
            "npc:ally": HEX_E,
        }
        result = parity.compare(substitution, copy.deepcopy(substitution))
        self.assertEqual(result["status"], "FAIL", result)
        self.assertIn(
            "FILE:TRANSACTION_CHECKPOINT_OWNER_SET_MISMATCH",
            result["findings"],
        )

        missing = snapshot()
        del missing["checkpoint"]["owner_state_hashes"]["pc:hero"]
        missing["checkpoint"]["owner_binding_count"] = 1
        result = parity.compare(missing, copy.deepcopy(missing))
        self.assertEqual(result["status"], "FAIL", result)
        self.assertIn(
            "FILE:TRANSACTION_CHECKPOINT_OWNER_SET_MISMATCH",
            result["findings"],
        )

        extra = snapshot()
        extra["checkpoint"]["owner_state_hashes"]["npc:ally"] = HEX_E
        extra["checkpoint"]["owner_binding_count"] = 3
        result = parity.compare(extra, copy.deepcopy(extra))
        self.assertEqual(result["status"], "FAIL", result)
        self.assertIn(
            "FILE:TRANSACTION_CHECKPOINT_OWNER_SET_MISMATCH",
            result["findings"],
        )

        count_mismatch = snapshot()
        count_mismatch["checkpoint"]["owner_binding_count"] = 3
        result = parity.compare(count_mismatch, copy.deepcopy(count_mismatch))
        self.assertEqual(result["status"], "FAIL", result)
        self.assertIn(
            "FILE:CHECKPOINT_OWNER_BINDING_COUNT_MISMATCH",
            result["findings"],
        )

    def test_transaction_identity_owner_membership_and_digest_fail_closed(self) -> None:
        s = snapshot()
        duplicate = copy.deepcopy(s["transaction_receipts"][0])
        duplicate["transaction_id"] = "tx-2"
        s["transaction_receipts"].append(duplicate)
        result = parity.compare(s, copy.deepcopy(s))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("FILE:TRANSACTION_EVENT_ID_DUPLICATE", result["findings"])

        s = snapshot()
        s["transaction_receipts"][0]["owner_ids"].append("pc:hero")
        result = parity.compare(s, copy.deepcopy(s))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("FILE:TRANSACTION_OWNER_ID_DUPLICATE", result["findings"])

        s = snapshot()
        s["transaction_receipts"][0]["owner_set_sha256"] = HEX_A
        result = parity.compare(s, copy.deepcopy(s))
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("FILE:TRANSACTION_OWNER_SET_DIGEST_MISMATCH", result["findings"])

    def test_whitespace_only_owner_identity_fails_closed_even_when_snapshots_match(self) -> None:
        s = snapshot()
        owner_ids = ["   ", "runtime"]
        s["transaction_receipts"][0]["owner_ids"] = owner_ids
        s["transaction_receipts"][0]["owner_set_sha256"] = parity.owner_set_sha256(owner_ids)
        s["checkpoint"]["owner_binding_count"] = 2
        s["checkpoint"]["owner_state_hashes"] = {"   ": HEX_D, "runtime": HEX_C}
        result = parity.compare(s, copy.deepcopy(s))
        self.assertEqual(result["status"], "FAIL", result)
        self.assertIn("FILE:TRANSACTION_OWNER_IDS_INVALID", result["findings"])
        self.assertIn("FILE:OWNER_STATE_HASH_BINDINGS_INVALID", result["findings"])
        self.assertIn("SQL:TRANSACTION_OWNER_IDS_INVALID", result["findings"])
        self.assertIn("SQL:OWNER_STATE_HASH_BINDINGS_INVALID", result["findings"])


if __name__ == "__main__":
    unittest.main()
