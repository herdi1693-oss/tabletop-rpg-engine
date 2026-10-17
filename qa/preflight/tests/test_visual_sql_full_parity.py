#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from runtime.authority_grant_protocol import (
    AuthorityGrantClaims,
    AuthorityGrantEnvelope,
    canonical_grant_payload,
)
from runtime.visual_runtime_host import (
    DUAL_READ_PARITY,
    FILE_EXPORT_ONLY,
    FILE_PRIMARY,
    SQL_PRIMARY,
    materialize_visual_runtime_host,
)
from runtime.visual_sql_full_parity import (
    FullParityPostgresVisualSqlShadowObserver,
    validate_control_activation_shadow,
)


A = "a" * 64
B = "b" * 64
C = "c" * 40
D = "d" * 64
SIG = base64.b64encode(b"x" * 64).decode("ascii")


def fixture():
    claims = AuthorityGrantClaims(
        grant_id="GRANT-1",
        key_id="KEY-1",
        request_id="REQ-1",
        session_id="SESSION-1",
        activation_id="ACT-1",
        source_revision="rev-1",
        checkpoint_receipt_id="CP-1",
        checkpoint_digest=A,
        event_id="EVENT-1",
        applied_event_ledger_owner_id="AEL-1",
        applied_event_ledger_snapshot_digest=A,
        player_knowledge_projection_id="PKP-1",
        observer_branch_id="BRANCH-1",
        player_knowledge_projection_revision="rev-1",
        player_knowledge_projection_digest=A,
        leak_gate_receipt_id="LEAK-1",
        leak_gate_receipt_digest=A,
        player_safe_bundle_digest=A,
        display_ledger_owner_id="DLO-1",
        display_ledger_backing_store_id="DLS-1",
        display_ledger_backing_namespace="NS-1",
        issued_at_unix=1_800_000_000,
        expires_at_unix=1_800_000_120,
        nonce="NONCE-1",
    )
    envelope = AuthorityGrantEnvelope(claims, SIG)
    bindings = SimpleNamespace(
        grant_envelope=envelope,
        verification_root_id="BOOTSTRAP-ROOT-1",
        authority_grant_id=claims.grant_id,
        session_id=claims.session_id,
        source_revision=claims.source_revision,
    )
    packet = {"PACKET_DIGEST": f"sha256:{B}"}
    grant = {
        "grant_id": claims.grant_id,
        "request_id": claims.request_id,
        "key_id": claims.key_id,
        "verification_root_id": bindings.verification_root_id,
        "verification_root_fingerprint_sha256": D,
        "session_id": claims.session_id,
        "activation_id": claims.activation_id,
        "source_revision": claims.source_revision,
        "checkpoint_receipt_id": claims.checkpoint_receipt_id,
        "checkpoint_digest_sha256": A,
        "event_id": claims.event_id,
        "ael_owner_id": claims.applied_event_ledger_owner_id,
        "ael_snapshot_digest_sha256": A,
        "pkp_id": claims.player_knowledge_projection_id,
        "observer_branch_id": claims.observer_branch_id,
        "pkp_revision": claims.player_knowledge_projection_revision,
        "pkp_digest_sha256": A,
        "leak_gate_receipt_id": claims.leak_gate_receipt_id,
        "leak_gate_receipt_digest_sha256": A,
        "player_safe_bundle_digest_sha256": A,
        "display_ledger_owner_id": claims.display_ledger_owner_id,
        "display_store_id": claims.display_ledger_backing_store_id,
        "display_namespace": claims.display_ledger_backing_namespace,
        "grant_payload_sha256": hashlib.sha256(canonical_grant_payload(claims)).hexdigest(),
        "signature_sha256": hashlib.sha256(b"x" * 64).hexdigest(),
        "nonce": claims.nonce,
        "grant_status": "VERIFIED",
        "source_commit_sha": C,
        "semantic_authority": False,
        "trust_root_authority": False,
    }
    activation = {
        "activation_run_id": "SESSION-1:ACT-1:attempt:1",
        "activation_id": "ACT-1",
        "attempt_no": 1,
        "session_id": "SESSION-1",
        "source_revision": "rev-1",
        "grant_id": "GRANT-1",
        "generation_packet_id": f"GENPACK-{B[:24]}",
        "generation_packet_sha256": B,
        "player_safe_bundle_digest_sha256": A,
        "visual_pipeline_status": "GENERATION_READY",
        "presentation_gate_status": "UNKNOWN",
        "render_status": "PENDING",
        "render_artifact_id": None,
        "render_artifact_sha256": None,
        "source_commit_sha": C,
        "semantic_authority": False,
    }
    return bindings, packet, grant, activation


def display_row(activation, *, render_artifact_id="RENDER-1", render_artifact_sha256=A):
    return {
        "display_commit_id": "DISPLAY-1",
        "display_receipt_id": "DISPLAY-1",
        "activation_run_id": activation["activation_run_id"],
        "activation_id": activation["activation_id"],
        "session_id": activation["session_id"],
        "source_revision": activation["source_revision"],
        "grant_id": activation["grant_id"],
        "generation_packet_id": activation["generation_packet_id"],
        "generation_packet_sha256": activation["generation_packet_sha256"],
        "render_artifact_id": render_artifact_id,
        "render_artifact_sha256": render_artifact_sha256,
        "display_ledger_owner_id": "DLO-1",
        "display_store_id": "DLS-1",
        "display_namespace": "NS-1",
        "display_status": "COMMITTED",
        "source_commit_sha": C,
        "semantic_authority": False,
    }


class VisualSqlFullParityTests(unittest.TestCase):
    def test_exact_grant_and_activation_readback_passes(self):
        bindings, packet, grant, activation = fixture()
        findings = validate_control_activation_shadow(
            bindings,
            packet,
            [grant],
            [activation],
            verification_root_fingerprint_sha256=D,
            source_commit_sha=C,
        )
        self.assertEqual(findings, ())

    def test_sql_root_metadata_cannot_silently_replace_bootstrap_lineage(self):
        bindings, packet, grant, activation = fixture()
        tampered = dict(grant)
        tampered["verification_root_fingerprint_sha256"] = "0" * 64
        findings = validate_control_activation_shadow(
            bindings,
            packet,
            [tampered],
            [activation],
            verification_root_fingerprint_sha256=D,
            source_commit_sha=C,
        )
        self.assertIn(
            "VSQL4_GRANT_FIELD_MISMATCH:verification_root_fingerprint_sha256",
            findings,
        )

    def test_stale_or_forged_control_row_blocks_migration_readiness(self):
        bindings, packet, grant, activation = fixture()
        tampered = dict(grant)
        tampered["checkpoint_digest_sha256"] = "0" * 64
        findings = validate_control_activation_shadow(
            bindings,
            packet,
            [tampered],
            [activation],
            verification_root_fingerprint_sha256=D,
            source_commit_sha=C,
        )
        self.assertIn("VSQL4_GRANT_FIELD_MISMATCH:checkpoint_digest_sha256", findings)

    def test_display_phase_requires_activation_readback_to_match_render(self):
        bindings, packet, grant, activation = fixture()
        display = display_row(activation)
        displayed = dict(activation)
        displayed.update({
            "visual_pipeline_status": "DISPLAYED",
            "presentation_gate_status": "PASS",
            "render_status": "SUCCESS",
            "render_artifact_id": "RENDER-1",
            "render_artifact_sha256": A,
        })
        self.assertEqual(
            validate_control_activation_shadow(
                bindings,
                packet,
                [grant],
                [displayed],
                verification_root_fingerprint_sha256=D,
                source_commit_sha=C,
                display_row=display,
            ),
            (),
        )
        stale = dict(displayed)
        stale["render_status"] = "PENDING"
        findings = validate_control_activation_shadow(
            bindings,
            packet,
            [grant],
            [stale],
            verification_root_fingerprint_sha256=D,
            source_commit_sha=C,
            display_row=display,
        )
        self.assertIn("VSQL4_ACTIVATION_FIELD_MISMATCH:render_status", findings)

    def test_route_factory_has_no_silent_sql_fallback(self):
        bindings = SimpleNamespace()
        with patch("runtime.visual_runtime_host.RuntimeVisualBridge", lambda value: ("FILE", value)):
            self.assertEqual(
                materialize_visual_runtime_host(
                    bindings, visual_state_stage=FILE_PRIMARY
                )[0],
                "FILE",
            )
        with self.assertRaisesRegex(RuntimeError, "VISUAL_SQL_FULL_PARITY_OBSERVER_REQUIRED"):
            materialize_visual_runtime_host(
                bindings, visual_state_stage=DUAL_READ_PARITY
            )
        for stage in (SQL_PRIMARY, FILE_EXPORT_ONLY):
            with self.assertRaisesRegex(RuntimeError, "VISUAL_SQL_PRIMARY_CUTOVER_NOT_APPROVED"):
                materialize_visual_runtime_host(bindings, visual_state_stage=stage)

    def test_full_parity_observer_remains_a_shadow_observer(self):
        self.assertTrue(
            issubclass(
                FullParityPostgresVisualSqlShadowObserver,
                __import__(
                    "runtime.visual_sql_shadow_runtime",
                    fromlist=["PostgresVisualSqlShadowObserver"],
                ).PostgresVisualSqlShadowObserver,
            )
        )


if __name__ == "__main__":
    unittest.main()
