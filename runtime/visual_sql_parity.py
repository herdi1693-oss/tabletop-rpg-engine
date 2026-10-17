#!/usr/bin/env python3
"""VSQL-4 shadow-write planning and deterministic SQLite/PostgreSQL parity.

Migration stage only. SQLite remains the active presentation replay owner.
PostgreSQL receives shadow operational/evidence rows and is never used here to
select the Runtime Host verification root, mutate Canon, or authorize gameplay.
A SQL/shadow failure means migration NOT_READY; it never rolls back gameplay.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from runtime.visual_display_ledger_sqlite import SQLiteDisplayLedgerOwner
from tools.visual.scene_continuity_guard import canonical_digest


@dataclass(frozen=True)
class DisplayParityProjection:
    display_receipt_id: str
    logical_index: int
    activation_id: str
    render_artifact_id: str
    render_artifact_sha256: str
    identity_receipt_id: str
    player_safe_receipt_id: str
    tactical_receipt_ids: tuple[str, ...]
    canonical_record_sha256: str


@dataclass(frozen=True)
class ShadowDisplayPlan:
    display_row: Mapping[str, object]
    tactical_rows: tuple[Mapping[str, object], ...]


@dataclass(frozen=True)
class VisualSqlParityResult:
    status: str
    findings: tuple[str, ...]
    sqlite_count: int
    sql_count: int

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def _required_text(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if type(value) is not str or not value:
        raise ValueError(f"VSQL4_REQUIRED_FIELD:{key}")
    return value


def _normalize_sha256(value: object, field: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"VSQL4_SHA256_REQUIRED:{field}")
    text = value.lower()
    if text.startswith("sha256:"):
        text = text[7:]
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"VSQL4_SHA256_INVALID:{field}")
    return text


def _normalize_commit_sha(value: object) -> str:
    if type(value) is not str or len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value.lower()):
        raise ValueError("VSQL4_SOURCE_COMMIT_SHA_INVALID")
    return value.lower()


def project_sqlite_display(owner: SQLiteDisplayLedgerOwner) -> tuple[DisplayParityProjection, ...]:
    if not isinstance(owner, SQLiteDisplayLedgerOwner):
        raise TypeError("VSQL4_SQLITE_DISPLAY_LEDGER_OWNER_REQUIRED")
    snapshot = owner.snapshot()
    ordered: list[DisplayParityProjection] = []
    for display_receipt_id, raw in snapshot.records.items():
        record = dict(raw)
        logical_index = record.get("DISPLAY_LEDGER_LOGICAL_INDEX")
        if type(logical_index) is not int or logical_index <= 0:
            raise ValueError(f"VSQL4_SQLITE_LOGICAL_INDEX_INVALID:{display_receipt_id}")
        tactical = record.get("TACTICAL_RECEIPT_IDS", [])
        if not isinstance(tactical, list) or not all(type(item) is str and item for item in tactical):
            raise ValueError(f"VSQL4_SQLITE_TACTICAL_RECEIPTS_INVALID:{display_receipt_id}")
        ordered.append(
            DisplayParityProjection(
                display_receipt_id=str(display_receipt_id),
                logical_index=logical_index,
                activation_id=_required_text(record, "ACTIVATION_ID"),
                render_artifact_id=_required_text(record, "RENDER_ARTIFACT_ID"),
                render_artifact_sha256=_normalize_sha256(
                    record.get("RENDER_ARTIFACT_HASH"), "RENDER_ARTIFACT_HASH"
                ),
                identity_receipt_id=_required_text(record, "IDENTITY_COMPARATOR_RECEIPT_ID"),
                player_safe_receipt_id=_required_text(record, "PLAYER_SAFE_CONTENT_RECEIPT_ID"),
                tactical_receipt_ids=tuple(tactical),
                canonical_record_sha256=canonical_digest(record),
            )
        )
    ordered.sort(key=lambda item: item.logical_index)
    expected_indexes = list(range(1, snapshot.logical_index + 1))
    actual_indexes = [item.logical_index for item in ordered]
    if actual_indexes != expected_indexes:
        raise ValueError("VSQL4_SQLITE_LOGICAL_INDEX_SEQUENCE_INVALID")
    return tuple(ordered)


def build_shadow_display_plan(
    owner: SQLiteDisplayLedgerOwner,
    display_receipt_id: str,
    *,
    activation_run_id: str,
    session_id: str,
    grant_id: str,
    generation_packet_id: str,
    generation_packet_sha256: str,
    source_commit_sha: str,
) -> ShadowDisplayPlan:
    """Build shadow SQL rows only from an already committed SQLite record."""
    if not isinstance(owner, SQLiteDisplayLedgerOwner):
        raise TypeError("VSQL4_SQLITE_DISPLAY_LEDGER_OWNER_REQUIRED")
    snapshot = owner.snapshot()
    raw = snapshot.records.get(str(display_receipt_id))
    if not isinstance(raw, Mapping):
        raise ValueError("VSQL4_SQLITE_DISPLAY_RECEIPT_NOT_COMMITTED")
    record = dict(raw)
    logical_index = record.get("DISPLAY_LEDGER_LOGICAL_INDEX")
    if type(logical_index) is not int or logical_index <= 0:
        raise ValueError("VSQL4_SQLITE_LOGICAL_INDEX_INVALID")
    tactical = record.get("TACTICAL_RECEIPT_IDS", [])
    if not isinstance(tactical, list) or not all(type(item) is str and item for item in tactical):
        raise ValueError("VSQL4_SQLITE_TACTICAL_RECEIPTS_INVALID")

    packet_sha = _normalize_sha256(generation_packet_sha256, "GENERATION_PACKET_SHA256")
    render_sha = _normalize_sha256(record.get("RENDER_ARTIFACT_HASH"), "RENDER_ARTIFACT_HASH")
    commit_sha = _normalize_commit_sha(source_commit_sha)
    display_commit_id = str(display_receipt_id)

    display_row = MappingProxyType({
        "display_commit_id": display_commit_id,
        "display_receipt_id": str(display_receipt_id),
        "activation_run_id": str(activation_run_id),
        "activation_id": _required_text(record, "ACTIVATION_ID"),
        "session_id": str(session_id),
        "source_revision": str(snapshot.source_revision),
        "grant_id": str(grant_id),
        "generation_packet_id": str(generation_packet_id),
        "generation_packet_sha256": packet_sha,
        "render_artifact_id": _required_text(record, "RENDER_ARTIFACT_ID"),
        "render_artifact_sha256": render_sha,
        "identity_comparator_receipt_id": _required_text(record, "IDENTITY_COMPARATOR_RECEIPT_ID"),
        "player_safe_receipt_id": _required_text(record, "PLAYER_SAFE_CONTENT_RECEIPT_ID"),
        "tactical_receipt_id": tactical[0] if tactical else None,
        "display_ledger_owner_id": owner.authority_instance_id,
        "display_store_id": owner.backing_store_id,
        "display_namespace": owner.backing_namespace,
        "logical_display_index": logical_index,
        "display_status": "COMMITTED",
        "source_commit_sha": commit_sha,
        "canonical_display_record_sha256": canonical_digest(record),
        "semantic_authority": False,
    })
    tactical_rows = tuple(
        MappingProxyType({
            "display_commit_id": display_commit_id,
            "display_ledger_owner_id": owner.authority_instance_id,
            "display_store_id": owner.backing_store_id,
            "display_namespace": owner.backing_namespace,
            "receipt_id": receipt_id,
            "ordinal": ordinal,
            "semantic_authority": False,
        })
        for ordinal, receipt_id in enumerate(tactical)
    )
    return ShadowDisplayPlan(display_row, tactical_rows)


_DISPLAY_INSERT = """
INSERT INTO dnd_visual.display_commit (
    display_commit_id, display_receipt_id, activation_run_id, activation_id,
    session_id, source_revision, grant_id, generation_packet_id,
    generation_packet_sha256, render_artifact_id, render_artifact_sha256,
    identity_comparator_receipt_id, player_safe_receipt_id, tactical_receipt_id,
    display_ledger_owner_id, display_store_id, display_namespace,
    logical_display_index, display_status, source_commit_sha,
    canonical_display_record_sha256, semantic_authority
) VALUES (
    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
)
"""
_TACTICAL_INSERT = """
INSERT INTO dnd_visual.display_tactical_receipt (
    display_commit_id, display_ledger_owner_id, display_store_id,
    display_namespace, receipt_id, ordinal, semantic_authority
) VALUES (%s,%s,%s,%s,%s,%s,%s)
"""


def execute_shadow_display_plan(connection_factory: Callable[[], object], plan: ShadowDisplayPlan) -> None:
    """Write a shadow display plan in one SQL transaction.

    This function must be called only after the canonical SQLite commit. Failure
    is migration NOT_READY evidence; callers must not reverse gameplay or Canon.
    """
    connection = connection_factory()
    try:
        cursor = connection.cursor()
        row = plan.display_row
        cursor.execute(_DISPLAY_INSERT, (
            row["display_commit_id"], row["display_receipt_id"], row["activation_run_id"],
            row["activation_id"], row["session_id"], row["source_revision"], row["grant_id"],
            row["generation_packet_id"], row["generation_packet_sha256"], row["render_artifact_id"],
            row["render_artifact_sha256"], row["identity_comparator_receipt_id"],
            row["player_safe_receipt_id"], row["tactical_receipt_id"], row["display_ledger_owner_id"],
            row["display_store_id"], row["display_namespace"], row["logical_display_index"],
            row["display_status"], row["source_commit_sha"], row["canonical_display_record_sha256"],
            row["semantic_authority"],
        ))
        for tactical in plan.tactical_rows:
            cursor.execute(_TACTICAL_INSERT, (
                tactical["display_commit_id"], tactical["display_ledger_owner_id"],
                tactical["display_store_id"], tactical["display_namespace"],
                tactical["receipt_id"], tactical["ordinal"], tactical["semantic_authority"],
            ))
        connection.commit()
    except Exception as exc:
        try:
            connection.rollback()
        finally:
            raise RuntimeError("VSQL4_SHADOW_WRITE_FAILED") from exc
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()


def validate_display_parity(
    owner: SQLiteDisplayLedgerOwner,
    sql_display_rows: Sequence[Mapping[str, object]] | None,
    sql_tactical_rows: Sequence[Mapping[str, object]] | None,
) -> VisualSqlParityResult:
    sqlite_rows = project_sqlite_display(owner)
    if sql_display_rows is None or sql_tactical_rows is None:
        return VisualSqlParityResult(
            "NOT_READY", ("VSQL4_SQL_PARITY_EVIDENCE_UNAVAILABLE",), len(sqlite_rows), 0
        )

    findings: list[str] = []
    tactical_by_commit: dict[str, list[tuple[int, str]]] = {}
    for raw in sql_tactical_rows:
        commit_id = str(raw.get("display_commit_id") or "")
        receipt_id = str(raw.get("receipt_id") or "")
        ordinal = raw.get("ordinal")
        if not commit_id or not receipt_id or type(ordinal) is not int or ordinal < 0:
            findings.append("VSQL4_SQL_TACTICAL_ROW_INVALID")
            continue
        tactical_checks = {
            "display_ledger_owner_id": owner.authority_instance_id,
            "display_store_id": owner.backing_store_id,
            "display_namespace": owner.backing_namespace,
            "semantic_authority": False,
        }
        for field, expected_value in tactical_checks.items():
            if raw.get(field) != expected_value:
                findings.append(f"VSQL4_TACTICAL_FIELD_MISMATCH:{commit_id}:{field}")
        tactical_by_commit.setdefault(commit_id, []).append((ordinal, receipt_id))

    sql_by_receipt: dict[str, Mapping[str, object]] = {}
    for raw in sql_display_rows:
        receipt_id = str(raw.get("display_receipt_id") or "")
        if not receipt_id or receipt_id in sql_by_receipt:
            findings.append("VSQL4_SQL_DISPLAY_RECEIPT_ID_INVALID_OR_DUPLICATE")
            continue
        sql_by_receipt[receipt_id] = raw

    if len(sql_by_receipt) != len(sqlite_rows):
        findings.append(f"VSQL4_DISPLAY_COUNT_MISMATCH:{len(sqlite_rows)}:{len(sql_by_receipt)}")

    for expected in sqlite_rows:
        actual = sql_by_receipt.get(expected.display_receipt_id)
        if actual is None:
            findings.append(f"VSQL4_SQL_DISPLAY_MISSING:{expected.display_receipt_id}")
            continue
        commit_id = str(actual.get("display_commit_id") or "")
        ordered_tactical = tuple(
            receipt_id for _, receipt_id in sorted(tactical_by_commit.get(commit_id, []))
        )
        checks = {
            "display_commit_id": expected.display_receipt_id,
            "logical_display_index": expected.logical_index,
            "activation_id": expected.activation_id,
            "render_artifact_id": expected.render_artifact_id,
            "render_artifact_sha256": expected.render_artifact_sha256,
            "identity_comparator_receipt_id": expected.identity_receipt_id,
            "player_safe_receipt_id": expected.player_safe_receipt_id,
            "tactical_receipt_id": expected.tactical_receipt_ids[0] if expected.tactical_receipt_ids else None,
            "canonical_display_record_sha256": expected.canonical_record_sha256,
            "display_ledger_owner_id": owner.authority_instance_id,
            "display_store_id": owner.backing_store_id,
            "display_namespace": owner.backing_namespace,
            "display_status": "COMMITTED",
            "semantic_authority": False,
        }
        for field, expected_value in checks.items():
            if actual.get(field) != expected_value:
                findings.append(f"VSQL4_FIELD_MISMATCH:{expected.display_receipt_id}:{field}")
        if ordered_tactical != expected.tactical_receipt_ids:
            findings.append(f"VSQL4_TACTICAL_RECEIPT_MISMATCH:{expected.display_receipt_id}")

    return VisualSqlParityResult(
        "PASS" if not findings else "NOT_READY",
        tuple(findings),
        len(sqlite_rows),
        len(sql_by_receipt),
    )


__all__ = [
    "DisplayParityProjection",
    "ShadowDisplayPlan",
    "VisualSqlParityResult",
    "project_sqlite_display",
    "build_shadow_display_plan",
    "execute_shadow_display_plan",
    "validate_display_parity",
]
