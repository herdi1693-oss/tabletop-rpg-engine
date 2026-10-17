#!/usr/bin/env python3
"""Exact VSQL-4 control + activation + display readback parity.

This is migration-readiness logic only. It cannot authorize a grant, select a
verification root, mutate Canon, or replace the SQLite presentation replay owner.
PostgreSQL rows are checked against already verified Runtime Host bindings.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Sequence

from runtime.authority_grant_protocol import canonical_grant_payload
from runtime.visual_sql_parity import validate_display_parity
from runtime.visual_sql_shadow_runtime import (
    PostgresVisualSqlShadowObserver,
    VisualSqlMigrationState,
    _activation_run_id,
    _hex64,
    _packet_digest,
    _packet_id,
    _row_mappings,
    _signature_sha256,
)
from tools.visual.scene_continuity_guard import canonical_digest


@dataclass(frozen=True)
class FullVisualSqlParityResult:
    status: str
    findings: tuple[str, ...]
    sqlite_count: int
    sql_count: int

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def _one(rows: Sequence[Mapping[str, object]], code: str):
    if len(rows) != 1:
        return None, [f"{code}_ROW_COUNT:{len(rows)}"]
    return rows[0], []


def _field_findings(prefix: str, row: Mapping[str, object], expected: Mapping[str, object]):
    return [
        f"{prefix}_FIELD_MISMATCH:{field}"
        for field, value in expected.items()
        if row.get(field) != value
    ]


def validate_control_activation_shadow(
    bindings,
    packet: Mapping[str, object],
    grant_rows: Sequence[Mapping[str, object]],
    activation_rows: Sequence[Mapping[str, object]],
    *,
    verification_root_fingerprint_sha256: str,
    source_commit_sha: str,
    display_row: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    """Verify SQL control/read-model rows against trusted host bindings exactly."""
    findings: list[str] = []
    grant, grant_findings = _one(grant_rows, "VSQL4_GRANT")
    activation, activation_findings = _one(activation_rows, "VSQL4_ACTIVATION")
    findings.extend(grant_findings)
    findings.extend(activation_findings)
    claims = bindings.grant_envelope.claims

    if grant is not None:
        expected_grant = {
            "grant_id": claims.grant_id,
            "request_id": claims.request_id,
            "key_id": claims.key_id,
            "verification_root_id": bindings.verification_root_id,
            "verification_root_fingerprint_sha256": _hex64(
                verification_root_fingerprint_sha256,
                "VERIFICATION_ROOT_FINGERPRINT_SHA256",
            ),
            "session_id": claims.session_id,
            "activation_id": claims.activation_id,
            "source_revision": claims.source_revision,
            "checkpoint_receipt_id": claims.checkpoint_receipt_id,
            "checkpoint_digest_sha256": _hex64(claims.checkpoint_digest, "CHECKPOINT_DIGEST"),
            "event_id": claims.event_id,
            "ael_owner_id": claims.applied_event_ledger_owner_id,
            "ael_snapshot_digest_sha256": _hex64(
                claims.applied_event_ledger_snapshot_digest, "AEL_SNAPSHOT_DIGEST"
            ),
            "pkp_id": claims.player_knowledge_projection_id,
            "observer_branch_id": claims.observer_branch_id,
            "pkp_revision": claims.player_knowledge_projection_revision,
            "pkp_digest_sha256": _hex64(
                claims.player_knowledge_projection_digest, "PKP_DIGEST"
            ),
            "leak_gate_receipt_id": claims.leak_gate_receipt_id,
            "leak_gate_receipt_digest_sha256": _hex64(
                claims.leak_gate_receipt_digest, "LEAK_GATE_RECEIPT_DIGEST"
            ),
            "player_safe_bundle_digest_sha256": _hex64(
                claims.player_safe_bundle_digest, "PLAYER_SAFE_BUNDLE_DIGEST"
            ),
            "display_ledger_owner_id": claims.display_ledger_owner_id,
            "display_store_id": claims.display_ledger_backing_store_id,
            "display_namespace": claims.display_ledger_backing_namespace,
            "grant_payload_sha256": hashlib.sha256(
                canonical_grant_payload(claims)
            ).hexdigest(),
            "signature_sha256": _signature_sha256(bindings.grant_envelope.signature_b64),
            "nonce": claims.nonce,
            "grant_status": "VERIFIED",
            "source_commit_sha": source_commit_sha,
            "semantic_authority": False,
            "trust_root_authority": False,
        }
        findings.extend(_field_findings("VSQL4_GRANT", grant, expected_grant))

    if display_row is not None:
        expected_display = {
            "activation_run_id": _activation_run_id(bindings),
            "activation_id": claims.activation_id,
            "session_id": claims.session_id,
            "source_revision": claims.source_revision,
            "grant_id": claims.grant_id,
            "generation_packet_id": _packet_id(packet),
            "generation_packet_sha256": _packet_digest(packet),
            "display_ledger_owner_id": claims.display_ledger_owner_id,
            "display_store_id": claims.display_ledger_backing_store_id,
            "display_namespace": claims.display_ledger_backing_namespace,
            "display_status": "COMMITTED",
            "source_commit_sha": source_commit_sha,
            "semantic_authority": False,
        }
        findings.extend(_field_findings("VSQL4_DISPLAY", display_row, expected_display))
        if display_row.get("display_commit_id") != display_row.get("display_receipt_id"):
            findings.append("VSQL4_DISPLAY_COMMIT_RECEIPT_ID_MISMATCH")

    if activation is not None:
        expected_activation = {
            "activation_run_id": _activation_run_id(bindings),
            "activation_id": claims.activation_id,
            "attempt_no": 1,
            "session_id": claims.session_id,
            "source_revision": claims.source_revision,
            "grant_id": claims.grant_id,
            "generation_packet_id": _packet_id(packet),
            "generation_packet_sha256": _packet_digest(packet),
            "player_safe_bundle_digest_sha256": _hex64(
                claims.player_safe_bundle_digest, "PLAYER_SAFE_BUNDLE_DIGEST"
            ),
            "source_commit_sha": source_commit_sha,
            "semantic_authority": False,
        }
        if display_row is None:
            expected_activation.update({
                "visual_pipeline_status": "GENERATION_READY",
                "presentation_gate_status": "UNKNOWN",
                "render_status": "PENDING",
                "render_artifact_id": None,
                "render_artifact_sha256": None,
            })
        else:
            expected_activation.update({
                "visual_pipeline_status": "DISPLAYED",
                "presentation_gate_status": "PASS",
                "render_status": "SUCCESS",
                "render_artifact_id": display_row.get("render_artifact_id"),
                "render_artifact_sha256": display_row.get("render_artifact_sha256"),
            })
        findings.extend(
            _field_findings("VSQL4_ACTIVATION", activation, expected_activation)
        )
    return tuple(findings)


class FullParityPostgresVisualSqlShadowObserver(PostgresVisualSqlShadowObserver):
    """VSQL-4 observer whose PASS covers grant + activation + display readback."""

    def _read_control_activation(self, bindings):
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT grant_id, request_id, key_id, verification_root_id,
                       verification_root_fingerprint_sha256, session_id,
                       activation_id, source_revision, checkpoint_receipt_id,
                       checkpoint_digest_sha256, event_id, ael_owner_id,
                       ael_snapshot_digest_sha256, pkp_id, observer_branch_id,
                       pkp_revision, pkp_digest_sha256, leak_gate_receipt_id,
                       leak_gate_receipt_digest_sha256,
                       player_safe_bundle_digest_sha256, display_ledger_owner_id,
                       display_store_id, display_namespace, grant_payload_sha256,
                       signature_sha256, nonce, grant_status, source_commit_sha,
                       semantic_authority, trust_root_authority
                  FROM dnd_control.authority_grant_record
                 WHERE grant_id=%s
                """,
                (bindings.authority_grant_id,),
            )
            grant_rows = _row_mappings(cursor)
            cursor.execute(
                """
                SELECT activation_run_id, activation_id, attempt_no, session_id,
                       source_revision, grant_id, generation_packet_id,
                       generation_packet_sha256, player_safe_bundle_digest_sha256,
                       visual_pipeline_status, presentation_gate_status,
                       render_status, render_artifact_id, render_artifact_sha256,
                       source_commit_sha, semantic_authority
                  FROM dnd_visual.visual_activation_run
                 WHERE activation_run_id=%s
                """,
                (_activation_run_id(bindings),),
            )
            activation_rows = _row_mappings(cursor)
            return grant_rows, activation_rows
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def observe_generation(self, bindings, context, packet) -> VisualSqlMigrationState:
        base = super().observe_generation(bindings, context, packet)
        if base.status == "NOT_READY":
            return base
        try:
            grant_rows, activation_rows = self._read_control_activation(bindings)
            findings = validate_control_activation_shadow(
                bindings,
                packet,
                grant_rows,
                activation_rows,
                verification_root_fingerprint_sha256=self.verification_root_fingerprint_sha256,
                source_commit_sha=self.source_commit_sha,
            )
            return VisualSqlMigrationState(
                "SHADOW_WRITTEN" if not findings else "NOT_READY", findings
            )
        except Exception as exc:
            return VisualSqlMigrationState(
                "NOT_READY",
                (f"VSQL4_GENERATION_READBACK_FAILED:{type(exc).__name__}",),
            )

    def _record_full_parity_receipt(
        self,
        bindings,
        parity: FullVisualSqlParityResult,
        grant_rows,
        activation_rows,
        display_rows,
        tactical_rows,
    ) -> None:
        owner = bindings.display_ledger_owner
        sqlite_snapshot = owner.snapshot()
        sql_projection_digest = canonical_digest({
            "GRANT_ROWS": [dict(row) for row in grant_rows],
            "ACTIVATION_ROWS": [dict(row) for row in activation_rows],
            "DISPLAY_ROWS": [dict(row) for row in display_rows],
            "TACTICAL_ROWS": [dict(row) for row in tactical_rows],
        })
        findings_digest = canonical_digest(list(parity.findings))
        parity_run_id = "VSQL4F-" + hashlib.sha256(
            json.dumps(
                {
                    "session": bindings.session_id,
                    "revision": bindings.source_revision,
                    "owner": owner.authority_instance_id,
                    "sqlite": sqlite_snapshot.digest,
                    "sql": sql_projection_digest,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:32]

        def write(cursor):
            cursor.execute(
                """
                INSERT INTO dnd_visual.visual_sql_parity_run (
                    parity_run_id, session_id, source_revision,
                    display_ledger_owner_id, display_store_id, display_namespace,
                    sqlite_snapshot_digest_sha256, sql_projection_digest_sha256,
                    sqlite_display_count, sql_display_count, parity_status,
                    findings_count, findings_digest_sha256, source_commit_sha,
                    validator_version, exposure_class, semantic_authority
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (parity_run_id) DO NOTHING
                """,
                (
                    parity_run_id, bindings.session_id, bindings.source_revision,
                    owner.authority_instance_id, owner.backing_store_id,
                    owner.backing_namespace,
                    _hex64(sqlite_snapshot.digest, "SQLITE_SNAPSHOT_DIGEST"),
                    _hex64(sql_projection_digest, "SQL_PROJECTION_DIGEST"),
                    parity.sqlite_count, parity.sql_count,
                    "PASS" if parity.passed else "NOT_READY",
                    len(parity.findings),
                    _hex64(findings_digest, "PARITY_FINDINGS_DIGEST"),
                    self.source_commit_sha, self.validator_version,
                    "SECURITY_INTERNAL", False,
                ),
            )
        self._transaction(write)

    def observe_display(self, bindings, context, packet, display_receipt):
        display_receipt_id = display_receipt.get("DISPLAY_RECEIPT_ID")
        if type(display_receipt_id) is not str or not display_receipt_id:
            return VisualSqlMigrationState(
                "NOT_READY", ("VSQL4_DISPLAY_RECEIPT_ID_REQUIRED",)
            )
        try:
            self._write_display_transaction(
                bindings, context, packet, display_receipt_id
            )
            grant_rows, activation_rows = self._read_control_activation(bindings)
            display_rows, tactical_rows = self._read_parity_rows(bindings)
            display_parity = validate_display_parity(
                bindings.display_ledger_owner, display_rows, tactical_rows
            )
            current_display = next(
                (
                    row
                    for row in display_rows
                    if row.get("display_receipt_id") == display_receipt_id
                ),
                None,
            )
            control_findings = validate_control_activation_shadow(
                bindings,
                packet,
                grant_rows,
                activation_rows,
                verification_root_fingerprint_sha256=self.verification_root_fingerprint_sha256,
                source_commit_sha=self.source_commit_sha,
                display_row=current_display,
            )
            findings = tuple(display_parity.findings) + tuple(control_findings)
            parity = FullVisualSqlParityResult(
                "PASS" if not findings else "NOT_READY",
                findings,
                display_parity.sqlite_count,
                display_parity.sql_count,
            )
            self._record_full_parity_receipt(
                bindings,
                parity,
                grant_rows,
                activation_rows,
                display_rows,
                tactical_rows,
            )
            return VisualSqlMigrationState(
                parity.status, parity.findings, parity.sqlite_count, parity.sql_count
            )
        except Exception as exc:
            return VisualSqlMigrationState(
                "NOT_READY",
                (f"VSQL4_FULL_PARITY_FAILED:{type(exc).__name__}",),
            )


__all__ = [
    "FullVisualSqlParityResult",
    "validate_control_activation_shadow",
    "FullParityPostgresVisualSqlShadowObserver",
]
