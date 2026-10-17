from __future__ import annotations

import hashlib
import json
from typing import Any

FORMAT = "DND_RUNTIME_INTEGRITY_PARITY_SNAPSHOT_V3"
HEX64 = set("0123456789abcdef")

REQUIRED_KEYS = {
    "format",
    "event_ids",
    "applied_event_ledger",
    "transaction_receipts",
    "last_committed_event_id",
    "logical_commit_revision",
    "checkpoint",
    "rng_receipts",
    "unknown_values",
    "player_visibility_fingerprint_sha256",
    "topology_semantics_fingerprint_sha256",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def owner_set_sha256(owner_ids: list[str]) -> str:
    return canonical_sha256(sorted(owner_ids))


def _hex64(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def _valid_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _transaction_semantics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        normalized.append(
            {
                "transaction_id": row["transaction_id"],
                "event_id": row["event_id"],
                "logical_revision": row["logical_revision"],
                "owner_ids": sorted(row["owner_ids"]),
                "owner_set_sha256": row["owner_set_sha256"],
                "transaction_status": row["transaction_status"],
            }
        )
    return sorted(normalized, key=lambda row: (row["event_id"], row["transaction_id"]))


def validate_snapshot(snapshot: Any) -> list[str]:
    findings: list[str] = []
    if not isinstance(snapshot, dict):
        return ["SNAPSHOT_ROOT_NOT_OBJECT"]
    if set(snapshot) != REQUIRED_KEYS:
        findings.append("SNAPSHOT_KEY_SET_MISMATCH")
        return findings
    if snapshot.get("format") != FORMAT:
        findings.append("SNAPSHOT_FORMAT_MISMATCH")

    event_ids = snapshot.get("event_ids")
    event_set: set[str] | None = None
    if not isinstance(event_ids, list) or not all(_valid_nonempty_string(x) for x in event_ids):
        findings.append("EVENT_ID_LIST_INVALID")
    elif len(event_ids) != len(set(event_ids)):
        findings.append("EVENT_ID_DUPLICATE")
    else:
        event_set = set(event_ids)

    logical_revision = snapshot.get("logical_commit_revision")
    logical_revision_valid = (
        isinstance(logical_revision, int)
        and not isinstance(logical_revision, bool)
        and logical_revision > 0
    )
    if not logical_revision_valid:
        findings.append("LOGICAL_COMMIT_REVISION_INVALID")

    ael = snapshot.get("applied_event_ledger")
    ael_revision_by_event: dict[str, int] = {}
    if not isinstance(ael, list):
        findings.append("AEL_NOT_LIST")
    else:
        ael_ids: list[str] = []
        ael_revisions: list[int] = []
        for row in ael:
            if not isinstance(row, dict) or set(row) != {
                "event_id", "ael_owner_id", "logical_revision", "payload_sha256"
            }:
                findings.append("AEL_ROW_SHAPE_INVALID")
                continue
            event_id = row["event_id"]
            row_revision = row["logical_revision"]
            if not _valid_nonempty_string(event_id):
                findings.append("AEL_EVENT_ID_INVALID")
            if not _valid_nonempty_string(row["ael_owner_id"]):
                findings.append("AEL_OWNER_ID_INVALID")
            if not isinstance(row_revision, int) or isinstance(row_revision, bool) or row_revision <= 0:
                findings.append("AEL_LOGICAL_REVISION_INVALID")
            if not _hex64(row["payload_sha256"]):
                findings.append("AEL_PAYLOAD_SHA_INVALID")
            if _valid_nonempty_string(event_id):
                ael_ids.append(event_id)
                if isinstance(row_revision, int) and not isinstance(row_revision, bool) and row_revision > 0:
                    ael_revision_by_event[event_id] = row_revision
                    ael_revisions.append(row_revision)
                    if logical_revision_valid and row_revision > logical_revision:
                        findings.append("AEL_LOGICAL_REVISION_EXCEEDS_COMMIT")
        if len(ael_ids) != len(set(ael_ids)):
            findings.append("AEL_EVENT_ID_DUPLICATE")
        if len(ael_revisions) != len(set(ael_revisions)):
            findings.append("AEL_LOGICAL_REVISION_DUPLICATE")
        if event_set is not None and set(ael_ids) != event_set:
            findings.append("AEL_EVENT_SET_MISMATCH")

    last_event = snapshot.get("last_committed_event_id")
    if not _valid_nonempty_string(last_event):
        findings.append("LAST_COMMITTED_EVENT_ID_INVALID")
    elif event_set is not None and last_event not in event_set:
        findings.append("LAST_COMMITTED_EVENT_NOT_IN_EVENT_SET")
    if (
        _valid_nonempty_string(last_event)
        and logical_revision_valid
        and last_event in ael_revision_by_event
        and ael_revision_by_event[last_event] != logical_revision
    ):
        findings.append("AEL_LAST_EVENT_REVISION_MISMATCH")

    transactions = snapshot.get("transaction_receipts")
    transaction_owner_set_by_event: dict[str, set[str]] = {}
    if not isinstance(transactions, list):
        findings.append("TRANSACTION_RECEIPTS_NOT_LIST")
    else:
        transaction_ids: list[str] = []
        transaction_event_ids: list[str] = []
        for row in transactions:
            if not isinstance(row, dict) or set(row) != {
                "transaction_id",
                "event_id",
                "logical_revision",
                "owner_ids",
                "owner_set_sha256",
                "transaction_status",
            }:
                findings.append("TRANSACTION_ROW_SHAPE_INVALID")
                continue
            transaction_id = row["transaction_id"]
            event_id = row["event_id"]
            row_revision = row["logical_revision"]
            owner_ids = row["owner_ids"]
            if not _valid_nonempty_string(transaction_id):
                findings.append("TRANSACTION_ID_INVALID")
            else:
                transaction_ids.append(transaction_id)
            if not _valid_nonempty_string(event_id):
                findings.append("TRANSACTION_EVENT_ID_INVALID")
            else:
                transaction_event_ids.append(event_id)
            if not isinstance(row_revision, int) or isinstance(row_revision, bool) or row_revision <= 0:
                findings.append("TRANSACTION_LOGICAL_REVISION_INVALID")
            owner_ids_valid = (
                isinstance(owner_ids, list)
                and bool(owner_ids)
                and all(_valid_nonempty_string(owner_id) for owner_id in owner_ids)
            )
            owner_ids_unique = owner_ids_valid and len(owner_ids) == len(set(owner_ids))
            if not owner_ids_valid:
                findings.append("TRANSACTION_OWNER_IDS_INVALID")
            elif not owner_ids_unique:
                findings.append("TRANSACTION_OWNER_ID_DUPLICATE")
            if not _hex64(row["owner_set_sha256"]):
                findings.append("TRANSACTION_OWNER_SET_SHA_INVALID")
            elif owner_ids_unique:
                if row["owner_set_sha256"] != owner_set_sha256(owner_ids):
                    findings.append("TRANSACTION_OWNER_SET_DIGEST_MISMATCH")
            if row["transaction_status"] != "COMMITTED":
                findings.append("TRANSACTION_STATUS_NOT_COMMITTED")
            if (
                _valid_nonempty_string(event_id)
                and isinstance(row_revision, int)
                and not isinstance(row_revision, bool)
                and row_revision > 0
                and event_id in ael_revision_by_event
                and row_revision != ael_revision_by_event[event_id]
            ):
                findings.append("TRANSACTION_EVENT_REVISION_MISMATCH")
            if _valid_nonempty_string(event_id) and owner_ids_unique:
                transaction_owner_set_by_event[event_id] = set(owner_ids)
        if len(transaction_ids) != len(set(transaction_ids)):
            findings.append("TRANSACTION_ID_DUPLICATE")
        if len(transaction_event_ids) != len(set(transaction_event_ids)):
            findings.append("TRANSACTION_EVENT_ID_DUPLICATE")
        if event_set is not None and set(transaction_event_ids) != event_set:
            findings.append("TRANSACTION_EVENT_SET_MISMATCH")

    checkpoint = snapshot.get("checkpoint")
    if not isinstance(checkpoint, dict) or set(checkpoint) != {
        "checkpoint_id", "status", "logical_revision", "last_committed_event_id",
        "checkpoint_digest_sha256", "owner_binding_count", "owner_state_hashes"
    }:
        findings.append("CHECKPOINT_SHAPE_INVALID")
    else:
        if not _valid_nonempty_string(checkpoint["checkpoint_id"]):
            findings.append("CHECKPOINT_ID_INVALID")
        if checkpoint["status"] != "COMMITTED":
            findings.append("CHECKPOINT_STATUS_NOT_COMMITTED")
        checkpoint_revision = checkpoint["logical_revision"]
        if (
            not isinstance(checkpoint_revision, int)
            or isinstance(checkpoint_revision, bool)
            or checkpoint_revision <= 0
        ):
            findings.append("CHECKPOINT_LOGICAL_REVISION_INVALID")
        elif logical_revision_valid and checkpoint_revision != logical_revision:
            findings.append("CHECKPOINT_LOGICAL_REVISION_MISMATCH")
        checkpoint_last_event = checkpoint["last_committed_event_id"]
        if not _valid_nonempty_string(checkpoint_last_event):
            findings.append("CHECKPOINT_LAST_EVENT_INVALID")
        else:
            if event_set is not None and checkpoint_last_event not in event_set:
                findings.append("CHECKPOINT_LAST_EVENT_NOT_IN_EVENT_SET")
            if _valid_nonempty_string(last_event) and checkpoint_last_event != last_event:
                findings.append("CHECKPOINT_LAST_EVENT_MISMATCH")
        if not _hex64(checkpoint["checkpoint_digest_sha256"]):
            findings.append("CHECKPOINT_DIGEST_INVALID")
        owner_binding_count = checkpoint["owner_binding_count"]
        if (
            not isinstance(owner_binding_count, int)
            or isinstance(owner_binding_count, bool)
            or owner_binding_count <= 0
        ):
            findings.append("CHECKPOINT_OWNER_BINDING_COUNT_INVALID")
        owner_hashes = checkpoint["owner_state_hashes"]
        owner_hashes_valid = isinstance(owner_hashes, dict) and bool(owner_hashes)
        if not owner_hashes_valid:
            findings.append("OWNER_STATE_HASH_BINDINGS_INVALID")
        elif any(not _valid_nonempty_string(k) or not _hex64(v) for k, v in owner_hashes.items()):
            findings.append("OWNER_STATE_HASH_BINDINGS_INVALID")
            owner_hashes_valid = False
        if owner_hashes_valid and isinstance(owner_binding_count, int) and not isinstance(owner_binding_count, bool):
            if owner_binding_count != len(owner_hashes):
                findings.append("CHECKPOINT_OWNER_BINDING_COUNT_MISMATCH")
        if (
            owner_hashes_valid
            and _valid_nonempty_string(checkpoint_last_event)
            and checkpoint_last_event in transaction_owner_set_by_event
            and set(owner_hashes) != transaction_owner_set_by_event[checkpoint_last_event]
        ):
            findings.append("TRANSACTION_CHECKPOINT_OWNER_SET_MISMATCH")

    rng = snapshot.get("rng_receipts")
    if not isinstance(rng, list):
        findings.append("RNG_RECEIPTS_NOT_LIST")
    else:
        identities: set[tuple[str, int]] = set()
        for row in rng:
            if not isinstance(row, dict) or set(row) != {
                "rng_stream_id",
                "event_id",
                "logical_revision",
                "rng_cursor",
                "rng_state_sha256",
                "draw_receipt_sha256",
            }:
                findings.append("RNG_ROW_SHAPE_INVALID")
                continue
            stream_id = row["rng_stream_id"]
            event_id = row["event_id"]
            row_revision = row["logical_revision"]
            if not _valid_nonempty_string(stream_id):
                findings.append("RNG_STREAM_ID_INVALID")
            if not _valid_nonempty_string(event_id):
                findings.append("RNG_EVENT_ID_INVALID")
            elif event_set is not None and event_id not in event_set:
                findings.append("RNG_EVENT_NOT_IN_EVENT_SET")
            if not isinstance(row_revision, int) or isinstance(row_revision, bool) or row_revision <= 0:
                findings.append("RNG_LOGICAL_REVISION_INVALID")
            elif (
                _valid_nonempty_string(event_id)
                and event_id in ael_revision_by_event
                and row_revision != ael_revision_by_event[event_id]
            ):
                findings.append("RNG_EVENT_REVISION_MISMATCH")
            if not isinstance(row["rng_cursor"], int) or isinstance(row["rng_cursor"], bool) or row["rng_cursor"] < 0:
                findings.append("RNG_CURSOR_INVALID")
            if not _hex64(row["rng_state_sha256"]) or not _hex64(row["draw_receipt_sha256"]):
                findings.append("RNG_DIGEST_INVALID")
            if (
                _valid_nonempty_string(stream_id)
                and isinstance(row_revision, int)
                and not isinstance(row_revision, bool)
                and row_revision > 0
            ):
                identity = (stream_id, row_revision)
                if identity in identities:
                    findings.append("RNG_STREAM_REVISION_DUPLICATE")
                identities.add(identity)

    if not isinstance(snapshot.get("unknown_values"), dict):
        findings.append("UNKNOWN_VALUES_NOT_OBJECT")
    for key in ("player_visibility_fingerprint_sha256", "topology_semantics_fingerprint_sha256"):
        if not _hex64(snapshot.get(key)):
            findings.append(f"{key.upper()}_INVALID")
    return findings


def compare(file_snapshot: Any, sql_snapshot: Any) -> dict[str, Any]:
    findings = [f"FILE:{x}" for x in validate_snapshot(file_snapshot)]
    findings += [f"SQL:{x}" for x in validate_snapshot(sql_snapshot)]
    if findings:
        return {"status": "FAIL", "findings": findings}

    checks = {
        "EXACT_EVENT_ID_SET_EQUALITY":
            set(file_snapshot["event_ids"]) == set(sql_snapshot["event_ids"]),
        "APPLIED_EVENT_LEDGER_ORDER_AND_MEMBERSHIP_EQUALITY":
            file_snapshot["applied_event_ledger"] == sql_snapshot["applied_event_ledger"],
        "MULTI_OWNER_TRANSACTION_RECEIPT_EQUALITY":
            _transaction_semantics(file_snapshot["transaction_receipts"])
            == _transaction_semantics(sql_snapshot["transaction_receipts"]),
        "LAST_COMMITTED_EVENT_ID_EQUALITY":
            file_snapshot["last_committed_event_id"] == sql_snapshot["last_committed_event_id"],
        "LOGICAL_COMMIT_REVISION_EQUALITY":
            file_snapshot["logical_commit_revision"] == sql_snapshot["logical_commit_revision"],
        "CHECKPOINT_ID_AND_STATUS_EQUALITY":
            (
                file_snapshot["checkpoint"]["checkpoint_id"],
                file_snapshot["checkpoint"]["status"],
                file_snapshot["checkpoint"]["logical_revision"],
                file_snapshot["checkpoint"]["last_committed_event_id"],
                file_snapshot["checkpoint"]["checkpoint_digest_sha256"],
                file_snapshot["checkpoint"]["owner_binding_count"],
            ) == (
                sql_snapshot["checkpoint"]["checkpoint_id"],
                sql_snapshot["checkpoint"]["status"],
                sql_snapshot["checkpoint"]["logical_revision"],
                sql_snapshot["checkpoint"]["last_committed_event_id"],
                sql_snapshot["checkpoint"]["checkpoint_digest_sha256"],
                sql_snapshot["checkpoint"]["owner_binding_count"],
            ),
        "OWNER_STATE_HASH_BINDING_EQUALITY":
            file_snapshot["checkpoint"]["owner_state_hashes"] == sql_snapshot["checkpoint"]["owner_state_hashes"],
        "RNG_RECEIPT_AND_CURSOR_EQUALITY":
            file_snapshot["rng_receipts"] == sql_snapshot["rng_receipts"],
        "EXPLICIT_UNKNOWN_VALUES_PRESERVED_WITHOUT_FABRICATION":
            file_snapshot["unknown_values"] == sql_snapshot["unknown_values"],
        "NO_PLAYER_VISIBILITY_EXPANSION":
            file_snapshot["player_visibility_fingerprint_sha256"]
            == sql_snapshot["player_visibility_fingerprint_sha256"],
        "NO_TOPOLOGY_SEMANTIC_REASSIGNMENT":
            file_snapshot["topology_semantics_fingerprint_sha256"]
            == sql_snapshot["topology_semantics_fingerprint_sha256"],
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "findings": [f"PARITY_MISMATCH:{name}" for name in failed],
        "file_snapshot_sha256": canonical_sha256(file_snapshot),
        "sql_snapshot_sha256": canonical_sha256(sql_snapshot),
    }
