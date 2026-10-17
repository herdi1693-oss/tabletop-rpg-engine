#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.visual_display_ledger_sqlite import SQLiteDisplayLedgerOwner
from runtime.visual_sql_parity import (
    build_shadow_display_plan,
    execute_shadow_display_plan,
    validate_display_parity,
)


HEX64_A = "a" * 64
HEX64_B = "b" * 64
COMMIT40 = "c" * 40


def committed_owner(tmp: str):
    owner = SQLiteDisplayLedgerOwner(Path(tmp) / "display.sqlite", "rev-1")
    receipt = {
        "DISPLAY_RECEIPT_ID": "DISPLAY-1",
        "ACTIVATION_ID": "ACT-1",
        "RENDER_ARTIFACT_ID": "RENDER-1",
        "RENDER_ARTIFACT_HASH": f"sha256:{HEX64_A}",
        "IDENTITY_COMPARATOR_RECEIPT_ID": "IDENTITY-1",
        "PLAYER_SAFE_CONTENT_RECEIPT_ID": "PSAFE-1",
    }
    findings = owner.commit_if_fresh(receipt, ["TACT-1", "TACT-2"])
    if findings:
        raise AssertionError(findings)
    return owner


class FakeCursor:
    def __init__(self, fail_at: int | None = None):
        self.calls = []
        self.fail_at = fail_at

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            raise RuntimeError("simulated sql failure")


class FakeConnection:
    def __init__(self, fail_at: int | None = None):
        self.cursor_obj = FakeCursor(fail_at)
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class VisualSqlParityTests(unittest.TestCase):
    def test_shadow_plan_requires_existing_canonical_sqlite_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner = SQLiteDisplayLedgerOwner(Path(tmp) / "display.sqlite", "rev-1")
            with self.assertRaisesRegex(ValueError, "VSQL4_SQLITE_DISPLAY_RECEIPT_NOT_COMMITTED"):
                build_shadow_display_plan(
                    owner,
                    "DISPLAY-404",
                    activation_run_id="RUN-1",
                    session_id="SESSION-1",
                    grant_id="GRANT-1",
                    generation_packet_id="PACKET-1",
                    generation_packet_sha256=HEX64_B,
                    source_commit_sha=COMMIT40,
                )

    def test_exact_sqlite_sql_shadow_parity_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner = committed_owner(tmp)
            plan = build_shadow_display_plan(
                owner,
                "DISPLAY-1",
                activation_run_id="RUN-1",
                session_id="SESSION-1",
                grant_id="GRANT-1",
                generation_packet_id="PACKET-1",
                generation_packet_sha256=HEX64_B,
                source_commit_sha=COMMIT40,
            )
            passed = validate_display_parity(owner, [plan.display_row], list(plan.tactical_rows))
            self.assertTrue(passed.passed, passed.findings)
            self.assertEqual(passed.sqlite_count, 1)
            self.assertEqual(passed.sql_count, 1)

            tampered = dict(plan.display_row)
            tampered["canonical_display_record_sha256"] = "0" * 64
            failed = validate_display_parity(owner, [tampered], list(plan.tactical_rows))
            self.assertFalse(failed.passed)
            self.assertIn("VSQL4_FIELD_MISMATCH:DISPLAY-1:canonical_display_record_sha256", failed.findings)

            tactical = [dict(row) for row in plan.tactical_rows]
            tactical[1]["receipt_id"] = "TACT-FORGED"
            failed_tactical = validate_display_parity(owner, [plan.display_row], tactical)
            self.assertFalse(failed_tactical.passed)
            self.assertIn("VSQL4_TACTICAL_RECEIPT_MISMATCH:DISPLAY-1", failed_tactical.findings)

    def test_missing_sql_evidence_is_not_ready_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner = committed_owner(tmp)
            result = validate_display_parity(owner, None, None)
            self.assertEqual(result.status, "NOT_READY")
            self.assertEqual(result.findings, ("VSQL4_SQL_PARITY_EVIDENCE_UNAVAILABLE",))

    def test_shadow_write_transaction_commits_or_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner = committed_owner(tmp)
            plan = build_shadow_display_plan(
                owner,
                "DISPLAY-1",
                activation_run_id="RUN-1",
                session_id="SESSION-1",
                grant_id="GRANT-1",
                generation_packet_id="PACKET-1",
                generation_packet_sha256=HEX64_B,
                source_commit_sha=COMMIT40,
            )

            ok = FakeConnection()
            execute_shadow_display_plan(lambda: ok, plan)
            self.assertTrue(ok.committed)
            self.assertFalse(ok.rolled_back)
            self.assertTrue(ok.closed)
            self.assertEqual(len(ok.cursor_obj.calls), 3)

            bad = FakeConnection(fail_at=2)
            with self.assertRaisesRegex(RuntimeError, "VSQL4_SHADOW_WRITE_FAILED"):
                execute_shadow_display_plan(lambda: bad, plan)
            self.assertFalse(bad.committed)
            self.assertTrue(bad.rolled_back)
            self.assertTrue(bad.closed)

    def test_vsql31_schema_preserves_replay_and_tactical_parity_keys(self):
        root = Path(__file__).resolve().parents[3]
        sql = (root / "runtime/sql/VSQL_3_1_VISUAL_RUNTIME_PARITY_KEYS_v1.sql").read_text(encoding="utf-8")
        for needle in (
            "canonical_display_record_sha256",
            "display_receipt_id",
            "display_commit_activation_replay_uq",
            "display_commit_render_replay_uq",
            "display_commit_identity_receipt_replay_uq",
            "display_commit_player_safe_receipt_replay_uq",
            "dnd_visual.display_tactical_receipt",
            "semantic_authority = false",
        ):
            self.assertIn(needle, sql)


if __name__ == "__main__":
    unittest.main()
