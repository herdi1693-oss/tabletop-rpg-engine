#!/usr/bin/env python3
"""VSQL-4 trusted-host SQL shadow integration for visual runtime.

SQLite remains the active presentation replay owner during this migration stage.
PostgreSQL receives structured shadow state/evidence only after the canonical
SQLite display commit. SQL failure marks migration NOT_READY and never changes
the visual result, gameplay, Canon, RNG, checkpoint, AEL, PKP, Recovery, or Gates.

The connection factory and audit root fingerprint are trusted-host bootstrap
configuration. No verification key/root material is accepted from visual/request
payloads, grants, SQL rows, or render packets.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from runtime.authority_grant_protocol import canonical_grant_payload
from runtime.visual_runtime_bridge import (
    RuntimeAuthorityBindings,
    RuntimeVisualBridge,
    RuntimeVisualContext,
    RuntimeVisualResult,
)
from runtime.visual_sql_parity import build_shadow_display_plan, validate_display_parity
from tools.visual.scene_continuity_guard import canonical_digest


@dataclass(frozen=True)
class VisualSqlMigrationState:
    status: str
    findings: tuple[str, ...]
    sqlite_count: int = 0
    sql_count: int = 0

    @property
    def ready(self) -> bool:
        return self.status == "PASS"


def _hex64(value: object, field: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"VSQL4_{field}_REQUIRED")
    text = value.lower()
    if text.startswith("sha256:"):
        text = text[7:]
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"VSQL4_{field}_INVALID")
    return text


def _commit40(value: object) -> str:
    if type(value) is not str:
        raise ValueError("VSQL4_SOURCE_COMMIT_SHA_REQUIRED")
    text = value.lower()
    if len(text) != 40 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError("VSQL4_SOURCE_COMMIT_SHA_INVALID")
    return text


def _utc(unix_seconds: int) -> datetime:
    return datetime.fromtimestamp(int(unix_seconds), tz=timezone.utc)


def _signature_sha256(signature_b64: str) -> str:
    try:
        raw = base64.b64decode(signature_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("VSQL4_GRANT_SIGNATURE_INVALID") from exc
    return hashlib.sha256(raw).hexdigest()


def _packet_digest(packet: Mapping[str, object]) -> str:
    return _hex64(packet.get("PACKET_DIGEST"), "GENERATION_PACKET_SHA256")


def _packet_id(packet: Mapping[str, object]) -> str:
    explicit = packet.get("PACKET_ID")
    if type(explicit) is str and explicit:
        return explicit
    return f"GENPACK-{_packet_digest(packet)[:24]}"


def _activation_run_id(bindings: RuntimeAuthorityBindings) -> str:
    claims = bindings.grant_envelope.claims
    return f"{claims.session_id}:{claims.activation_id}:attempt:1"


def _row_mappings(cursor) -> list[Mapping[str, object]]:
    rows = cursor.fetchall()
    description = getattr(cursor, "description", None)
    if not description:
        return [row for row in rows if isinstance(row, Mapping)]
    names = [item[0] for item in description]
    out = []
    for row in rows:
        if isinstance(row, Mapping):
            out.append(row)
        else:
            out.append(dict(zip(names, row)))
    return out


class PostgresVisualSqlShadowObserver:
    """Trusted-host DB-API adapter for VSQL-4 shadow writes and parity evidence."""

    def __init__(
        self,
        connection_factory: Callable[[], object],
        *,
        source_commit_sha: str,
        verification_root_fingerprint_sha256: str,
        broker_version: str = "AUTHORITY_BROKER_V1",
        validator_version: str = "VSQL4_PARITY_V1",
    ) -> None:
        if not callable(connection_factory):
            raise TypeError("VSQL4_CONNECTION_FACTORY_REQUIRED")
        self._connection_factory = connection_factory
        self.source_commit_sha = _commit40(source_commit_sha)
        self.verification_root_fingerprint_sha256 = _hex64(
            verification_root_fingerprint_sha256,
            "VERIFICATION_ROOT_FINGERPRINT_SHA256",
        )
        self.broker_version = str(broker_version)
        self.validator_version = str(validator_version)

    def _transaction(self, callback):
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            value = callback(cursor)
            connection.commit()
            return value
        except Exception:
            try:
                connection.rollback()
            finally:
                raise
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def _record_grant(self, cursor, bindings: RuntimeAuthorityBindings) -> None:
        envelope = bindings.grant_envelope
        claims = envelope.claims
        payload_sha = hashlib.sha256(canonical_grant_payload(claims)).hexdigest()
        cursor.execute(
            """
            INSERT INTO dnd_control.authority_grant_record (
                grant_id, schema_version, request_id, key_id, verification_root_id,
                verification_root_fingerprint_sha256, session_id, activation_id,
                source_revision, checkpoint_receipt_id, checkpoint_digest_sha256,
                event_id, ael_owner_id, ael_snapshot_digest_sha256, pkp_id,
                observer_branch_id, pkp_revision, pkp_digest_sha256,
                leak_gate_receipt_id, leak_gate_receipt_digest_sha256,
                player_safe_bundle_digest_sha256, display_ledger_owner_id,
                display_store_id, display_namespace, grant_payload_sha256,
                signature_sha256, nonce, issued_at, expires_at, verified_at,
                grant_status, source_commit_sha, broker_version, validator_version,
                exposure_class, semantic_authority, trust_root_authority
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (grant_id) DO NOTHING
            """,
            (
                claims.grant_id, 1, claims.request_id, claims.key_id,
                bindings.verification_root_id,
                self.verification_root_fingerprint_sha256,
                claims.session_id, claims.activation_id, claims.source_revision,
                claims.checkpoint_receipt_id, _hex64(claims.checkpoint_digest, "CHECKPOINT_DIGEST"),
                claims.event_id, claims.applied_event_ledger_owner_id,
                _hex64(claims.applied_event_ledger_snapshot_digest, "AEL_SNAPSHOT_DIGEST"),
                claims.player_knowledge_projection_id, claims.observer_branch_id,
                claims.player_knowledge_projection_revision,
                _hex64(claims.player_knowledge_projection_digest, "PKP_DIGEST"),
                claims.leak_gate_receipt_id,
                _hex64(claims.leak_gate_receipt_digest, "LEAK_GATE_RECEIPT_DIGEST"),
                _hex64(claims.player_safe_bundle_digest, "PLAYER_SAFE_BUNDLE_DIGEST"),
                claims.display_ledger_owner_id, claims.display_ledger_backing_store_id,
                claims.display_ledger_backing_namespace, payload_sha,
                _signature_sha256(envelope.signature_b64), claims.nonce,
                _utc(claims.issued_at_unix), _utc(claims.expires_at_unix),
                datetime.now(timezone.utc), "VERIFIED", self.source_commit_sha,
                self.broker_version, self.validator_version, "SECURITY_INTERNAL",
                False, False,
            ),
        )

    def _record_activation(
        self,
        cursor,
        bindings: RuntimeAuthorityBindings,
        context: RuntimeVisualContext,
        packet: Mapping[str, object],
    ) -> str:
        claims = bindings.grant_envelope.claims
        run_id = _activation_run_id(bindings)
        profile = context.player_safe_request.get("VISUAL_PROFILE_ID")
        if type(profile) is not str or not profile:
            profile = "LIVE_VISUAL_ACTIVATION_V1"
        cursor.execute(
            """
            INSERT INTO dnd_visual.visual_activation_run (
                activation_run_id, activation_id, attempt_no, session_id,
                source_revision, grant_id, generation_packet_id,
                generation_packet_sha256, player_safe_bundle_digest_sha256,
                visual_profile_id, visual_pipeline_status, structural_gate_status,
                presentation_gate_status, render_status, source_commit_sha,
                exposure_class, semantic_authority
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (session_id, activation_id, source_revision, attempt_no)
            DO NOTHING
            """,
            (
                run_id, claims.activation_id, 1, claims.session_id,
                claims.source_revision, claims.grant_id, _packet_id(packet),
                _packet_digest(packet),
                _hex64(claims.player_safe_bundle_digest, "PLAYER_SAFE_BUNDLE_DIGEST"),
                profile, "GENERATION_READY", "UNKNOWN", "UNKNOWN", "PENDING",
                self.source_commit_sha, "PLAYER_SAFE_VISUAL_METADATA", False,
            ),
        )
        return run_id

    def observe_generation(
        self,
        bindings: RuntimeAuthorityBindings,
        context: RuntimeVisualContext,
        packet: Mapping[str, object],
    ) -> VisualSqlMigrationState:
        def write(cursor):
            self._record_grant(cursor, bindings)
            self._record_activation(cursor, bindings, context, packet)
        try:
            self._transaction(write)
            return VisualSqlMigrationState("SHADOW_WRITTEN", ())
        except Exception as exc:
            return VisualSqlMigrationState(
                "NOT_READY", (f"VSQL4_GENERATION_SHADOW_WRITE_FAILED:{type(exc).__name__}",)
            )

    def _write_display_transaction(
        self,
        bindings: RuntimeAuthorityBindings,
        context: RuntimeVisualContext,
        packet: Mapping[str, object],
        display_receipt_id: str,
    ) -> None:
        run_id = _activation_run_id(bindings)
        plan = build_shadow_display_plan(
            bindings.display_ledger_owner,
            display_receipt_id,
            activation_run_id=run_id,
            session_id=bindings.session_id,
            grant_id=bindings.authority_grant_id,
            generation_packet_id=_packet_id(packet),
            generation_packet_sha256=_packet_digest(packet),
            source_commit_sha=self.source_commit_sha,
        )

        def write(cursor):
            self._record_grant(cursor, bindings)
            self._record_activation(cursor, bindings, context, packet)
            row = plan.display_row
            cursor.execute(
                """
                INSERT INTO dnd_visual.display_commit (
                    display_commit_id, display_receipt_id, activation_run_id,
                    activation_id, session_id, source_revision, grant_id,
                    generation_packet_id, generation_packet_sha256,
                    render_artifact_id, render_artifact_sha256,
                    identity_comparator_receipt_id, player_safe_receipt_id,
                    tactical_receipt_id, display_ledger_owner_id, display_store_id,
                    display_namespace, logical_display_index, display_status,
                    source_commit_sha, canonical_display_record_sha256,
                    semantic_authority
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                ) ON CONFLICT (display_commit_id) DO NOTHING
                """,
                tuple(row[key] for key in (
                    "display_commit_id", "display_receipt_id", "activation_run_id",
                    "activation_id", "session_id", "source_revision", "grant_id",
                    "generation_packet_id", "generation_packet_sha256",
                    "render_artifact_id", "render_artifact_sha256",
                    "identity_comparator_receipt_id", "player_safe_receipt_id",
                    "tactical_receipt_id", "display_ledger_owner_id",
                    "display_store_id", "display_namespace", "logical_display_index",
                    "display_status", "source_commit_sha",
                    "canonical_display_record_sha256", "semantic_authority",
                )),
            )
            for tactical in plan.tactical_rows:
                cursor.execute(
                    """
                    INSERT INTO dnd_visual.display_tactical_receipt (
                        display_commit_id, display_ledger_owner_id, display_store_id,
                        display_namespace, receipt_id, ordinal, semantic_authority
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        tactical["display_commit_id"], tactical["display_ledger_owner_id"],
                        tactical["display_store_id"], tactical["display_namespace"],
                        tactical["receipt_id"], tactical["ordinal"], tactical["semantic_authority"],
                    ),
                )
            cursor.execute(
                """
                UPDATE dnd_visual.visual_activation_run
                   SET visual_pipeline_status='DISPLAYED',
                       presentation_gate_status='PASS', render_status='SUCCESS',
                       completed_at=COALESCE(completed_at, now()),
                       render_artifact_id=%s, render_artifact_sha256=%s
                 WHERE activation_run_id=%s
                """,
                (
                    row["render_artifact_id"], row["render_artifact_sha256"], run_id,
                ),
            )
        self._transaction(write)

    def _read_parity_rows(self, bindings: RuntimeAuthorityBindings):
        owner = bindings.display_ledger_owner
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT display_commit_id, display_receipt_id, activation_run_id,
                       activation_id, session_id, source_revision, grant_id,
                       generation_packet_id, generation_packet_sha256,
                       render_artifact_id, render_artifact_sha256,
                       identity_comparator_receipt_id, player_safe_receipt_id,
                       tactical_receipt_id, display_ledger_owner_id, display_store_id,
                       display_namespace, logical_display_index, display_status,
                       source_commit_sha, canonical_display_record_sha256,
                       semantic_authority
                  FROM dnd_visual.display_commit
                 WHERE display_ledger_owner_id=%s AND display_store_id=%s
                   AND display_namespace=%s
                 ORDER BY logical_display_index
                """,
                (owner.authority_instance_id, owner.backing_store_id, owner.backing_namespace),
            )
            display_rows = _row_mappings(cursor)
            cursor.execute(
                """
                SELECT display_commit_id, display_ledger_owner_id, display_store_id,
                       display_namespace, receipt_id, ordinal, semantic_authority
                  FROM dnd_visual.display_tactical_receipt
                 WHERE display_ledger_owner_id=%s AND display_store_id=%s
                   AND display_namespace=%s
                 ORDER BY display_commit_id, ordinal
                """,
                (owner.authority_instance_id, owner.backing_store_id, owner.backing_namespace),
            )
            tactical_rows = _row_mappings(cursor)
            return display_rows, tactical_rows
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()

    def _record_parity_receipt(
        self,
        bindings: RuntimeAuthorityBindings,
        parity,
        display_rows: Sequence[Mapping[str, object]],
        tactical_rows: Sequence[Mapping[str, object]],
    ) -> None:
        owner = bindings.display_ledger_owner
        sqlite_snapshot = owner.snapshot()
        sql_projection_digest = canonical_digest({
            "DISPLAY_ROWS": [dict(row) for row in display_rows],
            "TACTICAL_ROWS": [dict(row) for row in tactical_rows],
        })
        findings_digest = canonical_digest(list(parity.findings))
        parity_run_id = "VSQL4-" + hashlib.sha256(
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
                    owner.backing_namespace, _hex64(sqlite_snapshot.digest, "SQLITE_SNAPSHOT_DIGEST"),
                    _hex64(sql_projection_digest, "SQL_PROJECTION_DIGEST"),
                    parity.sqlite_count, parity.sql_count,
                    "PASS" if parity.passed else "NOT_READY", len(parity.findings),
                    _hex64(findings_digest, "PARITY_FINDINGS_DIGEST"),
                    self.source_commit_sha, self.validator_version,
                    "SECURITY_INTERNAL", False,
                ),
            )
        self._transaction(write)

    def observe_display(
        self,
        bindings: RuntimeAuthorityBindings,
        context: RuntimeVisualContext,
        packet: Mapping[str, object],
        display_receipt: Mapping[str, object],
    ) -> VisualSqlMigrationState:
        display_receipt_id = display_receipt.get("DISPLAY_RECEIPT_ID")
        if type(display_receipt_id) is not str or not display_receipt_id:
            return VisualSqlMigrationState(
                "NOT_READY", ("VSQL4_DISPLAY_RECEIPT_ID_REQUIRED",)
            )
        try:
            self._write_display_transaction(bindings, context, packet, display_receipt_id)
            display_rows, tactical_rows = self._read_parity_rows(bindings)
            parity = validate_display_parity(
                bindings.display_ledger_owner, display_rows, tactical_rows
            )
            self._record_parity_receipt(
                bindings, parity, display_rows, tactical_rows
            )
            return VisualSqlMigrationState(
                "PASS" if parity.passed else "NOT_READY",
                tuple(parity.findings), parity.sqlite_count, parity.sql_count,
            )
        except Exception as exc:
            return VisualSqlMigrationState(
                "NOT_READY", (f"VSQL4_DISPLAY_SHADOW_OR_PARITY_FAILED:{type(exc).__name__}",)
            )


class RuntimeVisualSqlShadowBridge:
    """Canonical VSQL-4 wrapper: visual outcome remains SQLite-owned; SQL is shadow."""

    def __init__(
        self,
        authority_bindings: RuntimeAuthorityBindings,
        sql_observer: PostgresVisualSqlShadowObserver,
    ) -> None:
        if not isinstance(sql_observer, PostgresVisualSqlShadowObserver):
            raise TypeError("VSQL4_POSTGRES_SHADOW_OBSERVER_REQUIRED")
        self.authority_bindings = authority_bindings
        self._visual = RuntimeVisualBridge(authority_bindings)
        self.sql_observer = sql_observer
        self.last_migration_state = VisualSqlMigrationState(
            "NOT_READY", ("VSQL4_SQL_PARITY_NOT_YET_OBSERVED",)
        )

    def prepare_generation(self, context: RuntimeVisualContext) -> RuntimeVisualResult:
        visual = self._visual.prepare_generation(context)
        if visual.status == "GENERATION_READY" and visual.packet is not None:
            self.last_migration_state = self.sql_observer.observe_generation(
                self.authority_bindings, context, visual.packet
            )
        return visual

    def evaluate_render(self, context: RuntimeVisualContext, packet, render_result,
                        identity_comparator_payload, identity_proof_receipts,
                        tactical_receipts, scene_post_render_receipt,
                        render_scene_proofs) -> RuntimeVisualResult:
        visual = self._visual.evaluate_render(
            context, packet, render_result, identity_comparator_payload,
            identity_proof_receipts, tactical_receipts,
            scene_post_render_receipt, render_scene_proofs,
        )
        if visual.status == "DISPLAY_PASS" and visual.display_receipt is not None:
            # Canonical SQLite display commit has already happened inside the
            # wrapped visual bridge. SQL observation therefore cannot authorize
            # or roll back gameplay/presentation state.
            self.last_migration_state = self.sql_observer.observe_display(
                self.authority_bindings, context, packet, visual.display_receipt
            )
        return visual


__all__ = [
    "VisualSqlMigrationState",
    "PostgresVisualSqlShadowObserver",
    "RuntimeVisualSqlShadowBridge",
]
