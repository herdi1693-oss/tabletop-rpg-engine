#!/usr/bin/env python3
"""Presentation-only backup/restore tooling for the SQLite display ledger.

This helper exists only to prove migration rollback/export recovery. It does not
promote Runtime v1.3.8, change routing, touch PostgreSQL, or create gameplay/
Canon authority. Restore is fail-closed to the ledger's original resolved
namespace so copied database bytes cannot be promoted under a different path.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from runtime.visual_display_ledger_sqlite import SQLiteDisplayLedgerOwner
from tools.visual.scene_continuity_guard import canonical_digest


@dataclass(frozen=True)
class DisplayLedgerBackupReceipt:
    source_path: str
    source_namespace: str
    export_path: str
    export_sha256: str
    authority_instance_id: str
    backing_store_id: str
    snapshot_digest: str
    logical_index: int


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _namespace_for(path: Path) -> str:
    return canonical_digest({"RESOLVED_SQLITE_PATH": str(path)})


def _sqlite_namespace_paths(path: Path) -> tuple[Path, Path, Path]:
    return (path, Path(str(path) + "-wal"), Path(str(path) + "-shm"))


def _assert_restore_namespace_quiescent(target: Path) -> None:
    occupied = [candidate for candidate in _sqlite_namespace_paths(target) if candidate.exists()]
    if occupied:
        names = ",".join(candidate.name for candidate in occupied)
        raise RuntimeError(f"DISPLAY_LEDGER_RESTORE_NAMESPACE_NOT_QUIESCENT:{names}")


def _cleanup_sqlite_namespace(path: Path) -> None:
    for candidate in _sqlite_namespace_paths(path):
        candidate.unlink(missing_ok=True)


def _read_metadata(db_path: Path, key: str) -> str:
    with sqlite3.connect(str(db_path)) as connection:
        row = connection.execute(
            "SELECT value FROM visual_display_metadata WHERE key=?", (key,)
        ).fetchone()
    if row is None:
        raise RuntimeError(f"DISPLAY_LEDGER_BACKUP_METADATA_MISSING:{key}")
    return str(row[0])


def _integrity_check(db_path: Path) -> None:
    with sqlite3.connect(str(db_path)) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    if row is None or str(row[0]).lower() != "ok":
        raise RuntimeError("DISPLAY_LEDGER_BACKUP_INTEGRITY_CHECK_FAILED")


def export_display_ledger_backup(
    source_path: str | Path,
    export_path: str | Path,
    *,
    source_revision: str,
) -> DisplayLedgerBackupReceipt:
    """Create a consistent SQLite backup while preserving pinned ledger identity."""

    source = _resolved(source_path)
    destination = _resolved(export_path)
    if source == destination:
        raise ValueError("DISPLAY_LEDGER_BACKUP_DESTINATION_MUST_DIFFER")
    if not source.exists():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    owner = SQLiteDisplayLedgerOwner(source, source_revision)
    snapshot = owner.snapshot()
    expected_namespace = _namespace_for(source)
    if owner.backing_namespace != expected_namespace:
        raise RuntimeError("DISPLAY_LEDGER_BACKUP_SOURCE_NAMESPACE_MISMATCH")

    with sqlite3.connect(str(source)) as source_db:
        with sqlite3.connect(str(destination)) as backup_db:
            source_db.backup(backup_db)

    _integrity_check(destination)
    if _read_metadata(destination, "backing_namespace") != expected_namespace:
        destination.unlink(missing_ok=True)
        raise RuntimeError("DISPLAY_LEDGER_BACKUP_NAMESPACE_NOT_PRESERVED")

    return DisplayLedgerBackupReceipt(
        source_path=str(source),
        source_namespace=expected_namespace,
        export_path=str(destination),
        export_sha256=_sha256_file(destination),
        authority_instance_id=owner.authority_instance_id,
        backing_store_id=owner.backing_store_id,
        snapshot_digest=snapshot.digest,
        logical_index=snapshot.logical_index,
    )


def restore_display_ledger_backup(
    export_path: str | Path,
    target_path: str | Path,
    *,
    source_revision: str,
    expected_export_sha256: str,
    expected_snapshot_digest: str,
) -> SQLiteDisplayLedgerOwner:
    """Restore a validated backup only into its original pinned namespace.

    The entire target SQLite namespace (DB, ``-wal`` and ``-shm``) must be
    absent. Callers must hold the presentation owner quiescent for the duration
    of restore. Any pre-existing namespace member is rejected; this function
    never clears unknown stale sidecars on the caller's behalf.
    """

    export = _resolved(export_path)
    target = _resolved(target_path)
    if not export.exists():
        raise FileNotFoundError(export)

    expected_hash = str(expected_export_sha256).lower()
    if _sha256_file(export) != expected_hash:
        raise RuntimeError("DISPLAY_LEDGER_BACKUP_SHA256_MISMATCH")

    stored_namespace = _read_metadata(export, "backing_namespace")
    target_namespace = _namespace_for(target)
    if stored_namespace != target_namespace:
        raise RuntimeError("DISPLAY_LEDGER_RESTORE_NAMESPACE_MISMATCH")

    # Fail closed on the complete SQLite namespace. This catches the historical
    # case where the main DB was absent but stale WAL/SHM files survived.
    _assert_restore_namespace_quiescent(target)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.restore-{uuid.uuid4().hex}.tmp")
    installed = False
    try:
        with sqlite3.connect(str(export)) as source_db:
            with sqlite3.connect(str(temporary)) as target_db:
                source_db.backup(target_db)
        _integrity_check(temporary)

        # Re-check immediately before installation so a namespace member that
        # appeared while the temporary backup was built cannot be silently
        # combined with the restored DB.
        _assert_restore_namespace_quiescent(target)
        os.replace(temporary, target)
        installed = True

        # A quiescent namespace cannot gain WAL/SHM files between the second
        # check and install. Treat their appearance as a broken restore boundary.
        if Path(str(target) + "-wal").exists() or Path(str(target) + "-shm").exists():
            raise RuntimeError("DISPLAY_LEDGER_RESTORE_NAMESPACE_CHANGED_DURING_INSTALL")

        owner = SQLiteDisplayLedgerOwner(target, source_revision)
        snapshot = owner.snapshot()
        if snapshot.digest != str(expected_snapshot_digest):
            raise RuntimeError("DISPLAY_LEDGER_RESTORE_SNAPSHOT_DIGEST_MISMATCH")
        return owner
    except Exception:
        if installed:
            _cleanup_sqlite_namespace(target)
        raise
    finally:
        _cleanup_sqlite_namespace(temporary)


__all__ = [
    "DisplayLedgerBackupReceipt",
    "export_display_ledger_backup",
    "restore_display_ledger_backup",
]
