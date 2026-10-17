#!/usr/bin/env python3
from __future__ import annotations

import base64
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from runtime.authority_grant_protocol import AuthorityGrantClaims, AuthorityGrantEnvelope
from runtime.visual_runtime_bridge import RuntimeVisualResult
from runtime.visual_sql_shadow_runtime import (
    PostgresVisualSqlShadowObserver,
    RuntimeVisualSqlShadowBridge,
    VisualSqlMigrationState,
)


HEX64_A = "a" * 64
HEX64_B = "b" * 64
COMMIT40 = "c" * 40
ROOTFP64 = "d" * 64


def fake_bindings():
    claims = AuthorityGrantClaims(
        grant_id="GRANT-1",
        key_id="KEY-1",
        request_id="REQ-1",
        session_id="SESSION-1",
        activation_id="ACT-1",
        source_revision="rev-1",
        checkpoint_receipt_id="CP-1",
        checkpoint_digest=HEX64_A,
        event_id="EVENT-1",
        applied_event_ledger_owner_id="AEL-1",
        applied_event_ledger_snapshot_digest=HEX64_A,
        player_knowledge_projection_id="PKP-1",
        observer_branch_id="BRANCH-1",
        player_knowledge_projection_revision="rev-1",
        player_knowledge_projection_digest=HEX64_A,
        leak_gate_receipt_id="LEAK-1",
        leak_gate_receipt_digest=HEX64_A,
        player_safe_bundle_digest=HEX64_A,
        display_ledger_owner_id="DLO-1",
        display_ledger_backing_store_id="DLS-1",
        display_ledger_backing_namespace="NS-1",
        issued_at_unix=1_800_000_000,
        expires_at_unix=1_800_000_120,
        nonce="NONCE-1",
    )
    envelope = AuthorityGrantEnvelope(
        claims=claims,
        signature_b64=base64.b64encode(b"x" * 64).decode("ascii"),
    )
    return SimpleNamespace(
        grant_envelope=envelope,
        verification_root_id="BOOTSTRAP-ROOT-1",
        authority_grant_id=claims.grant_id,
        session_id=claims.session_id,
        source_revision=claims.source_revision,
    )


class StubObserver(PostgresVisualSqlShadowObserver):
    def __init__(self, generation_state=None, display_state=None):
        self.generation_state = generation_state or VisualSqlMigrationState("SHADOW_WRITTEN", ())
        self.display_state = display_state or VisualSqlMigrationState("PASS", (), 1, 1)
        self.generation_calls = 0
        self.display_calls = 0

    def observe_generation(self, bindings, context, packet):
        self.generation_calls += 1
        return self.generation_state

    def observe_display(self, bindings, context, packet, display_receipt):
        self.display_calls += 1
        return self.display_state


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.description = None

    def execute(self, sql, params):
        self.calls.append((sql, params))


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
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


class FakeVisualBridge:
    def __init__(self, bindings):
        self.bindings = bindings

    def prepare_generation(self, context):
        return RuntimeVisualResult(
            "GENERATION_READY", (), {"PACKET_DIGEST": f"sha256:{HEX64_B}"}, None
        )

    def evaluate_render(self, context, packet, *args, **kwargs):
        return RuntimeVisualResult(
            "DISPLAY_PASS", (), packet, {"DISPLAY_RECEIPT_ID": "DISPLAY-1"}
        )


class VisualSqlShadowRuntimeTests(unittest.TestCase):
    def test_shadow_observer_accepts_fingerprint_not_verification_key_material(self):
        params = inspect.signature(PostgresVisualSqlShadowObserver.__init__).parameters
        for forbidden in (
            "verification_root",
            "public_key",
            "public_key_pem",
            "keyring",
            "private_key",
            "signing_key",
        ):
            self.assertNotIn(forbidden, params)
        self.assertIn("verification_root_fingerprint_sha256", params)

    def test_generation_shadow_write_is_transactional(self):
        connection = FakeConnection()
        observer = PostgresVisualSqlShadowObserver(
            lambda: connection,
            source_commit_sha=COMMIT40,
            verification_root_fingerprint_sha256=ROOTFP64,
        )
        context = SimpleNamespace(player_safe_request={})
        packet = {"PACKET_DIGEST": f"sha256:{HEX64_B}"}
        state = observer.observe_generation(fake_bindings(), context, packet)
        self.assertEqual(state.status, "SHADOW_WRITTEN")
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertTrue(connection.closed)
        self.assertEqual(len(connection.cursor_obj.calls), 2)
        sql_text = "\n".join(call[0] for call in connection.cursor_obj.calls)
        self.assertIn("dnd_control.authority_grant_record", sql_text)
        self.assertIn("dnd_visual.visual_activation_run", sql_text)

    def test_sql_failure_does_not_change_successful_visual_result(self):
        observer = StubObserver(
            display_state=VisualSqlMigrationState(
                "NOT_READY", ("VSQL4_DISPLAY_SHADOW_OR_PARITY_FAILED:RuntimeError",)
            )
        )
        with patch("runtime.visual_sql_shadow_runtime.RuntimeVisualBridge", FakeVisualBridge):
            bridge = RuntimeVisualSqlShadowBridge(fake_bindings(), observer)
            context = SimpleNamespace()
            prepared = bridge.prepare_generation(context)
            displayed = bridge.evaluate_render(
                context, prepared.packet, {}, {}, {}, {}, {}, {}
            )
        self.assertTrue(displayed.passed)
        self.assertEqual(displayed.status, "DISPLAY_PASS")
        self.assertEqual(bridge.last_migration_state.status, "NOT_READY")
        self.assertEqual(observer.display_calls, 1)

    def test_parity_pass_is_observable_but_does_not_promote_visual_result(self):
        observer = StubObserver()
        with patch("runtime.visual_sql_shadow_runtime.RuntimeVisualBridge", FakeVisualBridge):
            bridge = RuntimeVisualSqlShadowBridge(fake_bindings(), observer)
            context = SimpleNamespace()
            prepared = bridge.prepare_generation(context)
            displayed = bridge.evaluate_render(
                context, prepared.packet, {}, {}, {}, {}, {}, {}
            )
        self.assertTrue(displayed.passed)
        self.assertTrue(bridge.last_migration_state.ready)
        self.assertEqual(bridge.last_migration_state.sqlite_count, 1)
        self.assertEqual(bridge.last_migration_state.sql_count, 1)

    def test_vsql4_schema_records_non_authoritative_parity_receipts(self):
        root = Path(__file__).resolve().parents[3]
        sql = (root / "runtime/sql/VSQL_4_VISUAL_DUAL_WRITE_PARITY_v1.sql").read_text(
            encoding="utf-8"
        )
        for needle in (
            "dnd_visual.visual_sql_parity_run",
            "sqlite_snapshot_digest_sha256",
            "sql_projection_digest_sha256",
            "parity_status",
            "semantic_authority = false",
            "does not promote Runtime",
        ):
            self.assertIn(needle, sql)


if __name__ == "__main__":
    unittest.main()
