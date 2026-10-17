#!/usr/bin/env python3
"""Durable SQLite-backed DisplayLedgerOwner for Runtime v1.3.8 candidate.

Presentation-only durability. This store never becomes Campaign Canon and never
owns gameplay, RNG, checkpoint or recovery state. A storage failure blocks
visual display only.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import threading
import uuid
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from tools.visual.live_visual_activation_guard_hardened import (
    DisplayLedgerOwner,
    DisplayLedgerSnapshot,
)
from tools.visual.scene_continuity_guard import canonical_digest


class SQLiteDisplayLedgerOwner(DisplayLedgerOwner):
    """Persistent owner compatible with Live Visual Activation's owner contract."""

    def __init__(self, db_path: str | Path, source_revision: str, ledger_id: str = "DISPLAY-LEDGER-V1"):
        self.status = "MATERIALIZED_OWNER"
        self.authority = "DISPLAY_LEDGER_OWNER"
        self.source_revision = str(source_revision)
        self.ledger_id = str(ledger_id)
        self._db_path = str(Path(db_path).resolve())
        self._lock = threading.RLock()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=30.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _metadata_get(self, connection: sqlite3.Connection, key: str):
        return connection.execute(
            "SELECT value FROM visual_display_metadata WHERE key=?", (key,)
        ).fetchone()

    def _metadata_put_once(self, connection: sqlite3.Connection, key: str, value: str) -> str:
        row = self._metadata_get(connection, key)
        if row is None:
            connection.execute(
                "INSERT INTO visual_display_metadata(key,value) VALUES(?,?)", (key, value)
            )
            return value
        return str(row["value"])

    def _initialize(self) -> None:
        namespace = canonical_digest({"RESOLVED_SQLITE_PATH": self._db_path})
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS visual_display_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS visual_display_records (
                    display_receipt_id TEXT PRIMARY KEY,
                    logical_index INTEGER NOT NULL UNIQUE,
                    activation_id TEXT NOT NULL UNIQUE,
                    render_artifact_id TEXT NOT NULL UNIQUE,
                    identity_receipt_id TEXT NOT NULL UNIQUE,
                    player_safe_receipt_id TEXT NOT NULL UNIQUE,
                    tactical_receipt_ids_json TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    record_digest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS visual_display_tactical_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    display_receipt_id TEXT NOT NULL REFERENCES visual_display_records(display_receipt_id) ON DELETE RESTRICT
                );
                """
            )
            stored_ledger = self._metadata_put_once(connection, "ledger_id", self.ledger_id)
            if stored_ledger != self.ledger_id:
                raise ValueError("DISPLAY_LEDGER_ID_MISMATCH")

            owner_row = self._metadata_get(connection, "authority_instance_id")
            if owner_row is None:
                self.authority_instance_id = f"DLO-SQLITE-{uuid.uuid4()}"
                connection.execute(
                    "INSERT INTO visual_display_metadata(key,value) VALUES('authority_instance_id',?)",
                    (self.authority_instance_id,),
                )
            else:
                self.authority_instance_id = str(owner_row["value"])

            self.backing_store_id = self._metadata_put_once(
                connection, "backing_store_id", f"DLS-SQLITE-{uuid.uuid4()}"
            )
            self.backing_namespace = self._metadata_put_once(
                connection, "backing_namespace", namespace
            )
            if self.backing_namespace != namespace:
                raise ValueError("DISPLAY_LEDGER_BACKING_NAMESPACE_MISMATCH")

            index_row = self._metadata_get(connection, "logical_index")
            if index_row is None:
                connection.execute(
                    "INSERT INTO visual_display_metadata(key,value) VALUES('logical_index','0')"
                )

    def bind_source_revision(self, source_revision: str) -> None:
        """Bind this runtime session to the exact activation proof revision."""
        self.source_revision = str(source_revision)

    def snapshot(self) -> DisplayLedgerSnapshot:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT display_receipt_id, record_json, record_digest FROM visual_display_records ORDER BY logical_index"
            ).fetchall()
            records: dict[str, Mapping[str, object]] = {}
            for row in rows:
                record = json.loads(row["record_json"])
                if canonical_digest(record) != row["record_digest"]:
                    raise RuntimeError("DISPLAY_LEDGER_RECORD_DIGEST_MISMATCH")
                records[row["display_receipt_id"]] = MappingProxyType(record)
            frozen = MappingProxyType(records)
            index_row = self._metadata_get(connection, "logical_index")
            logical_index = int(index_row["value"] if index_row else 0)
            body = {key: dict(value) for key, value in frozen.items()}
            # Keep the legacy Live Visual Activation snapshot digest shape exact.
            # Backing store/namespace identity is pinned separately by RuntimeAuthorityBindings.
            digest = canonical_digest(
                {
                    "LEDGER_ID": self.ledger_id,
                    "AUTHORITY_INSTANCE_ID": self.authority_instance_id,
                    "LOGICAL_INDEX": logical_index,
                    "RECORDS": body,
                }
            )
            return DisplayLedgerSnapshot(
                "MATERIALIZED_READ_ONLY",
                self.authority,
                self.source_revision,
                self.ledger_id,
                self.authority_instance_id,
                frozen,
                logical_index,
                digest,
            )

    def _replay_findings(
        self,
        connection: sqlite3.Connection,
        display_receipt: Mapping[str, object],
        tactical_ids: Sequence[str],
    ) -> list[str]:
        findings: list[str] = []
        checks = (
            ("activation_id", display_receipt.get("ACTIVATION_ID"), "REPLAYED_ACTIVATION_ID"),
            ("render_artifact_id", display_receipt.get("RENDER_ARTIFACT_ID"), "REPLAYED_RENDER_ARTIFACT_ID"),
            ("identity_receipt_id", display_receipt.get("IDENTITY_COMPARATOR_RECEIPT_ID"), "REPLAYED_IDENTITY_COMPARATOR_RECEIPT"),
            ("player_safe_receipt_id", display_receipt.get("PLAYER_SAFE_CONTENT_RECEIPT_ID"), "REPLAYED_PLAYER_SAFE_RECEIPT"),
        )
        for column, value, code in checks:
            if not value:
                findings.append(f"DISPLAY_LEDGER_REQUIRED_ID_MISSING:{column}")
                continue
            if connection.execute(
                f"SELECT 1 FROM visual_display_records WHERE {column}=? LIMIT 1", (str(value),)
            ).fetchone():
                findings.append(f"{code}:{value}")
        for receipt_id in tactical_ids:
            if connection.execute(
                "SELECT 1 FROM visual_display_tactical_receipts WHERE receipt_id=? LIMIT 1",
                (str(receipt_id),),
            ).fetchone():
                findings.append(f"REPLAYED_TACTICAL_RECEIPT:{receipt_id}")
        return findings

    def commit_if_fresh(self, display_receipt: Mapping[str, object], tactical_ids: Sequence[str]):
        """Atomically reject replay and persist one display receipt."""
        with self._lock, self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                findings = self._replay_findings(connection, display_receipt, tactical_ids)
                if findings:
                    connection.execute("ROLLBACK")
                    return findings

                index_row = self._metadata_get(connection, "logical_index")
                logical_index = int(index_row["value"] if index_row else 0) + 1
                record = copy.deepcopy(dict(display_receipt))
                record["DISPLAY_LEDGER_LOGICAL_INDEX"] = logical_index
                record["TACTICAL_RECEIPT_IDS"] = list(tactical_ids)
                display_receipt_id = str(record.get("DISPLAY_RECEIPT_ID") or f"DISPLAY-{logical_index}")
                record["DISPLAY_RECEIPT_ID"] = display_receipt_id
                record_json = json.dumps(
                    record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
                )
                connection.execute(
                    """
                    INSERT INTO visual_display_records(
                        display_receipt_id, logical_index, activation_id, render_artifact_id,
                        identity_receipt_id, player_safe_receipt_id, tactical_receipt_ids_json,
                        record_json, record_digest
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        display_receipt_id,
                        logical_index,
                        str(record.get("ACTIVATION_ID")),
                        str(record.get("RENDER_ARTIFACT_ID")),
                        str(record.get("IDENTITY_COMPARATOR_RECEIPT_ID")),
                        str(record.get("PLAYER_SAFE_CONTENT_RECEIPT_ID")),
                        json.dumps(list(tactical_ids), sort_keys=True),
                        record_json,
                        canonical_digest(record),
                    ),
                )
                for receipt_id in tactical_ids:
                    connection.execute(
                        "INSERT INTO visual_display_tactical_receipts(receipt_id,display_receipt_id) VALUES(?,?)",
                        (str(receipt_id), display_receipt_id),
                    )
                connection.execute(
                    "UPDATE visual_display_metadata SET value=? WHERE key='logical_index'",
                    (str(logical_index),),
                )
                connection.execute("COMMIT")
                return []
            except sqlite3.IntegrityError:
                connection.execute("ROLLBACK")
                return ["DISPLAY_LEDGER_UNIQUE_CONSTRAINT_VIOLATION"]
            except Exception:
                connection.execute("ROLLBACK")
                raise


def materialize_sqlite_display_ledger_owner(
    db_path: str | Path,
    source_revision: str,
    ledger_id: str = "DISPLAY-LEDGER-V1",
) -> SQLiteDisplayLedgerOwner:
    return SQLiteDisplayLedgerOwner(db_path, source_revision, ledger_id)
