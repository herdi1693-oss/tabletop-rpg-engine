# QA Checklist — Session Control Plane v1

TARGET: `tooling/session-control-plane-v1`
TYPE: contract/tooling architecture review
DO NOT RUN: Gates A-E, runtime promotion, campaign recovery acceptance

## SCP-01 Scope isolation
PASS if only architecture docs/manifest/targeted regression tests change. Runtime and campaign Canon paths must be untouched.

## SCP-02 Runtime execution ordering
PASS if the required order is exactly `COMMAND -> EVENT_ENVELOPE -> VALIDATION -> TRANSACTION_STAGE -> LEDGER_STAGE_PREPARED -> ATOMIC_COMMIT -> CHECKPOINT_BARRIER -> PLAYER_PROJECTION`, matching active runtime rules R107/R108/R109/R110 rather than placing checkpoint authority before commit.

## SCP-03 Optional precommit serialization
PASS if `PRECOMMIT_SERIALIZATION_VALIDATION` is optional, occurs only before `ATOMIC_COMMIT`, and is explicitly non-authoritative: not `/save`, not a checkpoint, not crash-recovery authority, and unable to mark a checkpoint committed.

## SCP-04 EVENT_ID and idempotency
PASS if `EVENT_ID` is bound before mutation, committed `APPLIED_EVENT_LEDGER` is checked before consequences, committed EVENT_ID is appended only with successful `ATOMIC_COMMIT`, and duplicate committed events cannot reapply gameplay consequences.

## SCP-05 Multi-owner atomicity
PASS if intended writes are staged against one frozen pre-state, no owner publishes independently, successful commit makes all dependent writes authoritative at one boundary, and commit failure restores all touched owners to PREPARE state.

## SCP-06 Checkpoint transaction boundary
PASS if checkpoint cannot start while `TX_STATUS=PREPARED|COMMITTING`, starts only after COMMITTED or ABORTED transaction boundary, and snapshots committed durable state only.

## SCP-07 Checkpoint contents
PASS if checkpoint freezes one logical committed revision and includes `LAST_COMMITTED_EVENT_ID`, `APPLIED_EVENT_LEDGER` continuity, and all required durable owner state; no checkpoint may contain a partial multi-owner event.

## SCP-08 Checkpoint failure after commit
PASS if checkpoint write/roundtrip failure after successful `ATOMIC_COMMIT` does not roll back or replay the gameplay event, does not remove the committed applied-event entry, and changes only checkpoint persistence status to retry-required/non-committed.

## SCP-09 Checkpoint retry non-reexecution
PASS if retrying checkpoint persistence cannot reroll RNG or repeat movement, damage, resource spend, effects, loot, knowledge or any other committed gameplay mutation.

## SCP-10 Observer/branch knowledge
PASS if knowledge deltas remain observer/branch scoped, split-party knowledge does not merge without valid communication/reunion, and unknown state is never invented.

## SCP-11 Player projection
PASS if every player-facing output requires materialized `PLAYER_KNOWLEDGE_PROJECTION` and `KNOWLEDGE_LEAK_PREOUTPUT_GATE`; exact enemy HP and hidden DM/source fields remain protected by default.

## SCP-12 Geometry ownership
PASS if Geometry Master remains mapped-topology owner, `PLAYER_SAFE_STRUCTURE_PACKAGE` owns player-visible geometry, deterministic mechanics own grid/door/cell semantics, visual output cannot become Canon, and semantic topology tolerance remains zero.

## SCP-13 Optional integrations
PASS if plugins/renderers/analytics/research systems are post-commit derivatives only, never transaction owners, never Gate authority and never required for core gameplay.

## SCP-14 Source-of-truth alignment
PASS if the contract remains consistent with `docs/SOURCE_OF_TRUTH_POLICY.md` and does not change `GITHUB_CUTOVER` or elevate GitHub above current Project authority.

## SCP-15 Activation barrier
PASS if the candidate is contract-only: no active Runtime change, no campaign-save mutation, no recovery acceptance, no Gate F claim, and implementation/promotion are deferred to a separate reviewed candidate.

## SCP-16 Machine regressions
PASS if `qa/preflight/tests/test_session_control_plane_contract.py` is discovered by Developer Preflight and validates at least:
1. checkpoint is blocked/deferred while TX is PREPARED or COMMITTING;
2. a committed event and committed applied-event entry survive checkpoint failure;
3. checkpoint retry does not repeat RNG/resources/movement or other gameplay mutation;
4. a successful checkpoint contains committed EVENT_ID + APPLIED_EVENT_LEDGER and matches the same logical commit revision;
5. duplicate delivery after committed event remains an idempotent no-op.

## Acceptance

QA PASS for this package approves only the future orchestration contract. It does not activate the control plane, modify Runtime, mutate Campaign Canon, approve recovery v1.14, reopen Gates A-E, or change Gate F.
