#!/usr/bin/env python3
"""Canonical Runtime Host factory for visual SQL-first migration stages.

Storage routing is explicit. There is no silent fallback between SQLite/file
state and PostgreSQL. SQL_PRIMARY is intentionally unavailable until the VSQL-5
cutover barrier is independently approved.
"""
from __future__ import annotations

from runtime.visual_runtime_bridge import RuntimeAuthorityBindings, RuntimeVisualBridge
from runtime.visual_sql_full_parity import FullParityPostgresVisualSqlShadowObserver
from runtime.visual_sql_shadow_runtime import RuntimeVisualSqlShadowBridge

FILE_PRIMARY = "FILE_PRIMARY"
DUAL_READ_PARITY = "DUAL_READ_PARITY"
SQL_PRIMARY = "SQL_PRIMARY"
FILE_EXPORT_ONLY = "FILE_EXPORT_ONLY"


def materialize_visual_runtime_host(
    authority_bindings: RuntimeAuthorityBindings,
    *,
    visual_state_stage: str,
    sql_observer: FullParityPostgresVisualSqlShadowObserver | None = None,
):
    """Build only the host implementation allowed by the explicit route stage."""
    stage = str(visual_state_stage)
    if stage == FILE_PRIMARY:
        if sql_observer is not None:
            raise ValueError("VISUAL_SQL_OBSERVER_FORBIDDEN_IN_FILE_PRIMARY")
        return RuntimeVisualBridge(authority_bindings)
    if stage == DUAL_READ_PARITY:
        if not isinstance(sql_observer, FullParityPostgresVisualSqlShadowObserver):
            raise RuntimeError("VISUAL_SQL_FULL_PARITY_OBSERVER_REQUIRED")
        return RuntimeVisualSqlShadowBridge(authority_bindings, sql_observer)
    if stage in (SQL_PRIMARY, FILE_EXPORT_ONLY):
        raise RuntimeError("VISUAL_SQL_PRIMARY_CUTOVER_NOT_APPROVED")
    raise ValueError(f"VISUAL_STATE_ROUTE_STAGE_INVALID:{stage}")


__all__ = [
    "FILE_PRIMARY",
    "DUAL_READ_PARITY",
    "SQL_PRIMARY",
    "FILE_EXPORT_ONLY",
    "materialize_visual_runtime_host",
]
