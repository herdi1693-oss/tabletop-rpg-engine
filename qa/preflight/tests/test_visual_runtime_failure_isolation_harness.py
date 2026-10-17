#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from qa.preflight.tests.test_live_visual_activation_contract import request
from qa.preflight.tests.test_visual_runtime_promotion_candidate import (
    render_bundle,
    runtime_fixture,
)
from runtime.visual_runtime_bridge import (
    RuntimeVisualBridge,
    capture_applied_event_ledger_snapshot,
    capture_checkpoint_owner_snapshot,
    capture_player_safe_proof_snapshot,
)
from runtime.visual_sql_shadow_runtime import (
    PostgresVisualSqlShadowObserver,
    RuntimeVisualSqlShadowBridge,
)
from tools.visual.scene_continuity_guard import canonical_digest


ROOT = Path(__file__).resolve().parents[3]
_CHILD_ENV = "DND_VISUAL_FAILURE_ISOLATION_CHILD"


class FailureStateIsolationHarnessTests(unittest.TestCase):
    def _run_isolated(self, method_name: str) -> None:
        env = os.environ.copy()
        env[_CHILD_ENV] = "1"
        target = (
            "qa.preflight.tests.test_visual_runtime_failure_isolation_harness."
            f"FailureStateIsolationHarnessTests.{method_name}"
        )
        result = subprocess.run(
            [sys.executable, "-m", "unittest", target],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def _non_display_state(self, bindings, context) -> dict[str, object]:
        revision = context.source_revision
        checkpoint = capture_checkpoint_owner_snapshot(bindings.checkpoint_owner, revision)
        ael = capture_applied_event_ledger_snapshot(bindings.applied_event_ledger_owner, revision)
        player = capture_player_safe_proof_snapshot(
            bindings.player_safe_proof_owner,
            context.player_safe_request,
            revision,
        )
        return {
            "checkpoint": checkpoint.digest,
            "ael": ael.digest,
            "player_safe": player.digest,
            "request": canonical_digest(dict(context.player_safe_request)),
            "authority_binding": bindings.digest,
            "source_revision": bindings.source_revision,
        }

    def test_malicious_failed_render_cannot_mutate_authority_or_display_state(self):
        if os.environ.get(_CHILD_ENV) != "1":
            self._run_isolated(
                "test_malicious_failed_render_cannot_mutate_authority_or_display_state"
            )
            return
        req = request(False)
        with tempfile.TemporaryDirectory() as tmp:
            context, bindings, scene_proofs, *_ = runtime_fixture(
                req, Path(tmp) / "display.sqlite"
            )
            bridge = RuntimeVisualBridge(bindings)
            prepared = bridge.prepare_generation(context)
            self.assertTrue(prepared.passed, prepared.findings)
            before = self._non_display_state(bindings, context)
            ledger_before = bindings.display_ledger_owner.snapshot()
            render, comparator, identity, scene_post = render_bundle(
                req, prepared.packet, scene_proofs
            )
            render.update(
                {
                    "STATUS": "FAILED",
                    "CANON_WRITE_ATTEMPT": True,
                    "VISUAL_TO_CANON_ATTEMPT": True,
                    "GAMEPLAY_MUTATION_ATTEMPT": True,
                    "GAMEPLAY_EVENT_REQUESTED": True,
                    "RNG_REQUESTED": True,
                }
            )
            result = bridge.evaluate_render(
                context,
                prepared.packet,
                render,
                comparator,
                identity,
                {},
                scene_post,
                scene_proofs,
            )
            after = self._non_display_state(bindings, context)
            ledger_after = bindings.display_ledger_owner.snapshot()
            self.assertFalse(result.passed)
            self.assertEqual(after, before)
            self.assertEqual(ledger_after.logical_index, ledger_before.logical_index)
            self.assertEqual(ledger_after.digest, ledger_before.digest)

    def test_sql_outage_after_successful_sqlite_display_changes_only_display_ledger(self):
        if os.environ.get(_CHILD_ENV) != "1":
            self._run_isolated(
                "test_sql_outage_after_successful_sqlite_display_changes_only_display_ledger"
            )
            return
        req = request(False)
        with tempfile.TemporaryDirectory() as tmp:
            context, bindings, scene_proofs, *_ = runtime_fixture(
                req, Path(tmp) / "display.sqlite"
            )

            def unavailable_connection():
                raise ConnectionError("simulated PostgreSQL outage")

            observer = PostgresVisualSqlShadowObserver(
                unavailable_connection,
                source_commit_sha="c" * 40,
                verification_root_fingerprint_sha256="d" * 64,
            )
            bridge = RuntimeVisualSqlShadowBridge(bindings, observer)
            before = self._non_display_state(bindings, context)
            ledger_before = bindings.display_ledger_owner.snapshot()
            prepared = bridge.prepare_generation(context)
            self.assertTrue(prepared.passed, prepared.findings)
            self.assertEqual(bridge.last_migration_state.status, "NOT_READY")
            render, comparator, identity, scene_post = render_bundle(
                req, prepared.packet, scene_proofs
            )
            result = bridge.evaluate_render(
                context,
                prepared.packet,
                render,
                comparator,
                identity,
                {},
                scene_post,
                scene_proofs,
            )
            after = self._non_display_state(bindings, context)
            ledger_after = bindings.display_ledger_owner.snapshot()
            self.assertTrue(result.passed, result.findings)
            self.assertEqual(bridge.last_migration_state.status, "NOT_READY")
            self.assertEqual(after, before)
            self.assertEqual(ledger_before.logical_index, 0)
            self.assertEqual(ledger_after.logical_index, 1)


if __name__ == "__main__":
    unittest.main()
