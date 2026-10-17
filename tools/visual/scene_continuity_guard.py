#!/usr/bin/env python3
"""Public fail-closed Scene Continuity Lock validator.

This module preserves the validated v1 implementation in
`scene_continuity_guard_base` and hardens sequence-level Applied Event Ledger
proof reuse. Tooling-only; no Runtime/Canon/Recovery mutation.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from . import scene_continuity_guard_base as _base
from .scene_continuity_guard_base import *  # re-export validated public API


def _sequence_event_proof_findings(
    frames: Sequence[Mapping[str, object]],
    transitions: Sequence[Mapping[str, object]],
    proofs: object,
) -> list[str]:
    """Enforce group-wide uniqueness and commit-order progression.

    A state-changing Applied Event Ledger receipt/event may authorize at most one
    transition in a continuity sequence. Logical commit indexes must advance
    strictly in frame order. This closes replay across separate calls to the
    base `validate_transition()` validator.
    """

    findings: list[str] = []
    seen_receipt_ids: set[str] = set()
    seen_event_ids: set[str] = set()
    last_commit_index: int | None = None

    transition_map: dict[tuple[object, object], Mapping[str, object]] = {}
    for transition in transitions:
        if not isinstance(transition, Mapping):
            continue
        key = (transition.get("FROM_FRAME_ID"), transition.get("TO_FRAME_ID"))
        transition_map.setdefault(key, transition)

    registry: Mapping[str, object] = {}
    if isinstance(proofs, Mapping):
        candidate = proofs.get("APPLIED_EVENT_LEDGER_RECEIPTS")
        if isinstance(candidate, Mapping):
            registry = candidate

    for index in range(1, len(frames)):
        previous = frames[index - 1]
        current = frames[index]
        key = (previous.get("FRAME_ID"), current.get("FRAME_ID"))
        transition = transition_map.get(key)
        if not isinstance(transition, Mapping):
            continue
        causes = transition.get("CAUSES")
        if not isinstance(causes, list):
            continue

        for cause_index, cause in enumerate(causes):
            if not isinstance(cause, Mapping):
                continue
            if cause.get("CAUSE_TYPE") != "COMMITTED_GAMEPLAY_EVENT":
                continue

            prefix = f"SEQUENCE:{key[0]}->{key[1]}:CAUSE_{cause_index}"
            receipt_id = cause.get("APPLIED_EVENT_LEDGER_RECEIPT_ID")
            event_id = cause.get("EVENT_ID")

            if receipt_id:
                receipt_key = str(receipt_id)
                if receipt_key in seen_receipt_ids:
                    findings.append(
                        f"{prefix}:REPLAYED_APPLIED_EVENT_RECEIPT_ACROSS_SEQUENCE:{receipt_key}"
                    )
                else:
                    seen_receipt_ids.add(receipt_key)
            if event_id:
                event_key = str(event_id)
                if event_key in seen_event_ids:
                    findings.append(f"{prefix}:REPLAYED_EVENT_ID_ACROSS_SEQUENCE:{event_key}")
                else:
                    seen_event_ids.add(event_key)

            external = registry.get(str(receipt_id)) if receipt_id else None
            if not isinstance(external, Mapping):
                # Base transition validation owns missing/invalid external-receipt findings.
                continue
            commit_index = external.get("LOGICAL_COMMIT_INDEX")
            if not isinstance(commit_index, int) or commit_index < 0:
                # Base transition validation owns invalid-index findings.
                continue
            if last_commit_index is not None and commit_index <= last_commit_index:
                findings.append(
                    f"{prefix}:NON_MONOTONIC_LOGICAL_COMMIT_INDEX:"
                    f"{commit_index}<={last_commit_index}"
                )
                last_commit_index = max(last_commit_index, commit_index)
            else:
                last_commit_index = commit_index

    return findings


def validate_sequence(
    group: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    transitions: Sequence[Mapping[str, object]],
    proofs: object = None,
) -> GuardResult:
    """Run the validated base sequence checks plus group-wide replay defense."""

    base_result = _base.validate_sequence(group, frames, transitions, proofs)
    findings = list(base_result.findings)
    findings.extend(_sequence_event_proof_findings(frames, transitions, proofs))
    return GuardResult("PASS" if not findings else "FAIL", tuple(findings))
