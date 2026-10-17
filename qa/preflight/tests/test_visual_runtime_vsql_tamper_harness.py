#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qa.preflight.tests.test_visual_sql_full_parity import (
    A,
    B,
    C,
    D,
    fixture as full_parity_fixture,
)
from runtime.visual_display_ledger_sqlite import SQLiteDisplayLedgerOwner
from runtime.visual_sql_full_parity import validate_control_activation_shadow
from runtime.visual_sql_parity import build_shadow_display_plan, validate_display_parity


class VsqlFullTamperMatrixHarnessTests(unittest.TestCase):
    def test_grant_readback_tamper_matrix_is_never_pass(self):
        bindings, packet, grant, activation = full_parity_fixture()
        cases = {
            "checkpoint_digest_sha256": "0" * 64,
            "ael_snapshot_digest_sha256": "1" * 64,
            "pkp_digest_sha256": "2" * 64,
            "leak_gate_receipt_digest_sha256": "3" * 64,
            "player_safe_bundle_digest_sha256": "4" * 64,
            "verification_root_fingerprint_sha256": "5" * 64,
            "display_ledger_owner_id": "DLO-FORGED",
            "display_store_id": "DLS-FORGED",
            "display_namespace": "NS-FORGED",
            "grant_payload_sha256": "6" * 64,
            "signature_sha256": "7" * 64,
            "nonce": "NONCE-FORGED",
            "source_commit_sha": "8" * 40,
            "semantic_authority": True,
            "trust_root_authority": True,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                tampered = dict(grant)
                tampered[field] = value
                findings = validate_control_activation_shadow(
                    bindings,
                    packet,
                    [tampered],
                    [activation],
                    verification_root_fingerprint_sha256=D,
                    source_commit_sha=C,
                )
                self.assertIn(f"VSQL4_GRANT_FIELD_MISMATCH:{field}", findings)

    def test_activation_and_packet_readback_tamper_matrix_is_never_pass(self):
        bindings, packet, grant, activation = full_parity_fixture()
        cases = {
            "activation_run_id": "RUN-FORGED",
            "activation_id": "ACT-FORGED",
            "attempt_no": 2,
            "session_id": "SESSION-FORGED",
            "source_revision": "REV-FORGED",
            "grant_id": "GRANT-FORGED",
            "generation_packet_id": "PACKET-FORGED",
            "generation_packet_sha256": "9" * 64,
            "player_safe_bundle_digest_sha256": "0" * 64,
            "source_commit_sha": "1" * 40,
            "semantic_authority": True,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                tampered = dict(activation)
                tampered[field] = value
                findings = validate_control_activation_shadow(
                    bindings,
                    packet,
                    [grant],
                    [tampered],
                    verification_root_fingerprint_sha256=D,
                    source_commit_sha=C,
                )
                self.assertIn(f"VSQL4_ACTIVATION_FIELD_MISMATCH:{field}", findings)

    def test_display_readback_binds_packet_and_lineage_fields(self):
        bindings, packet, grant, activation = full_parity_fixture()
        display = {
            "display_commit_id": "DISPLAY-1",
            "display_receipt_id": "DISPLAY-1",
            "activation_run_id": activation["activation_run_id"],
            "activation_id": activation["activation_id"],
            "session_id": activation["session_id"],
            "source_revision": activation["source_revision"],
            "grant_id": activation["grant_id"],
            "generation_packet_id": activation["generation_packet_id"],
            "generation_packet_sha256": activation["generation_packet_sha256"],
            "render_artifact_id": "RENDER-1",
            "render_artifact_sha256": A,
            "display_ledger_owner_id": "DLO-1",
            "display_store_id": "DLS-1",
            "display_namespace": "NS-1",
            "display_status": "COMMITTED",
            "source_commit_sha": C,
            "semantic_authority": False,
        }
        displayed = dict(activation)
        displayed.update({
            "visual_pipeline_status": "DISPLAYED",
            "presentation_gate_status": "PASS",
            "render_status": "SUCCESS",
            "render_artifact_id": "RENDER-1",
            "render_artifact_sha256": A,
        })
        baseline = validate_control_activation_shadow(
            bindings,
            packet,
            [grant],
            [displayed],
            verification_root_fingerprint_sha256=D,
            source_commit_sha=C,
            display_row=display,
        )
        self.assertEqual(baseline, ())
        cases = {
            "activation_run_id": "RUN-FORGED",
            "activation_id": "ACT-FORGED",
            "session_id": "SESSION-FORGED",
            "source_revision": "REV-FORGED",
            "grant_id": "GRANT-FORGED",
            "generation_packet_id": "PACKET-FORGED",
            "generation_packet_sha256": "f" * 64,
            "display_ledger_owner_id": "DLO-FORGED",
            "display_store_id": "DLS-FORGED",
            "display_namespace": "NS-FORGED",
            "source_commit_sha": "e" * 40,
            "semantic_authority": True,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                tampered = dict(display)
                tampered[field] = value
                findings = validate_control_activation_shadow(
                    bindings,
                    packet,
                    [grant],
                    [displayed],
                    verification_root_fingerprint_sha256=D,
                    source_commit_sha=C,
                    display_row=tampered,
                )
                self.assertIn(f"VSQL4_DISPLAY_FIELD_MISMATCH:{field}", findings)

    def test_display_and_tactical_tamper_matrix_is_never_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner = SQLiteDisplayLedgerOwner(Path(tmp) / "display.sqlite", "rev-1")
            receipt = {
                "DISPLAY_RECEIPT_ID": "DISPLAY-1",
                "ACTIVATION_ID": "ACT-1",
                "RENDER_ARTIFACT_ID": "RENDER-1",
                "RENDER_ARTIFACT_HASH": f"sha256:{A}",
                "IDENTITY_COMPARATOR_RECEIPT_ID": "IDENTITY-1",
                "PLAYER_SAFE_CONTENT_RECEIPT_ID": "PSAFE-1",
            }
            self.assertEqual(owner.commit_if_fresh(receipt, ["TACT-1", "TACT-2"]), [])
            plan = build_shadow_display_plan(
                owner,
                "DISPLAY-1",
                activation_run_id="RUN-1",
                session_id="SESSION-1",
                grant_id="GRANT-1",
                generation_packet_id="PACKET-1",
                generation_packet_sha256=B,
                source_commit_sha=C,
            )
            baseline = validate_display_parity(owner, [plan.display_row], list(plan.tactical_rows))
            self.assertTrue(baseline.passed, baseline.findings)
            cases = {
                "logical_display_index": 99,
                "activation_id": "ACT-FORGED",
                "render_artifact_id": "RENDER-FORGED",
                "render_artifact_sha256": "f" * 64,
                "identity_comparator_receipt_id": "IDENTITY-FORGED",
                "player_safe_receipt_id": "PSAFE-FORGED",
                "canonical_display_record_sha256": "0" * 64,
                "display_ledger_owner_id": "DLO-FORGED",
                "display_store_id": "DLS-FORGED",
                "display_namespace": "NS-FORGED",
                "display_status": "FORGED",
                "semantic_authority": True,
            }
            for field, value in cases.items():
                with self.subTest(field=field):
                    tampered = dict(plan.display_row)
                    tampered[field] = value
                    result = validate_display_parity(owner, [tampered], list(plan.tactical_rows))
                    self.assertFalse(result.passed, f"tamper unexpectedly passed: {field}")
                    self.assertIn(f"VSQL4_FIELD_MISMATCH:DISPLAY-1:{field}", result.findings)

            tactical_cases = {
                "receipt_id": "TACT-FORGED",
                "ordinal": 99,
                "display_ledger_owner_id": "DLO-FORGED",
                "display_store_id": "DLS-FORGED",
                "display_namespace": "NS-FORGED",
                "semantic_authority": True,
            }
            for field, value in tactical_cases.items():
                with self.subTest(tactical_field=field):
                    tactical = [dict(row) for row in plan.tactical_rows]
                    tactical[0][field] = value
                    result = validate_display_parity(owner, [plan.display_row], tactical)
                    self.assertFalse(result.passed, f"tactical tamper unexpectedly passed: {field}")


if __name__ == "__main__":
    unittest.main()
