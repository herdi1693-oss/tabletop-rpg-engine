# DND Event Envelope Contract v1

STATUS: CANDIDATE_CONTRACT_ONLY
RUNTIME_ACTIVATION: FALSE
CANON_MUTATION: FALSE
ACTIVE_RUNTIME_EXECUTION_BINDING: SYS.NATIVE.R107 + SYS.NATIVE.R108 + SYS.NATIVE.R109 + SAVE.NATIVE.R110

## Purpose

Define the minimum deterministic event wrapper expected by the future Session Control Plane without changing the active runtime/event schema.

## Required fields

Every mutating event proposal must expose at least:

- `EVENT_ID`
- `EVENT_SCHEMA_VERSION`
- `CAMPAIGN_ID`
- `SESSION_ID`
- `BRANCH_ID`
- `OBSERVER_SCOPE`
- `ACTOR_ID`
- `COMMAND_ID`
- `COMMAND_KIND`
- `IDEMPOTENCY_KEY`
- `SOURCE_AUTHORITY_BINDINGS`
- `PRE_STATE_REVISION`
- `PRE_STATE_HASH`
- `TRANSACTION_OWNERS`
- `TX_ID`
- `TX_STATUS`
- `RNG_REQUIREMENT`
- `RNG_RECEIPTS`
- `STATE_PATCH_SET`
- `SPATIAL_DELTA`
- `EFFECT_DELTA`
- `TIMER_DELTA`
- `INVENTORY_RESOURCE_DELTA`
- `NPC_STATE_DELTA`
- `KNOWLEDGE_DELTA`
- `DM_STATE_DELTA`
- `OBSERVABLE_RESULT`
- `POST_STATE_REVISION`
- `POST_STATE_HASH`
- `EVENT_LEDGER_CANDIDATE_STATUS`
- `APPLIED_EVENT_LEDGER_RECEIPT`
- `LOGICAL_COMMIT_INDEX`
- `LAST_COMMITTED_EVENT_ID`
- `PRECOMMIT_SERIALIZATION_VALIDATION_STATUS`
- `CHECKPOINT_ID`
- `CHECKPOINT_STATUS`
- `CHECKPOINT_SNAPSHOT_ID`
- `PLAYER_PROJECTION_ID`
- `PLAYER_PROJECTION_STATUS`
- `ROLLBACK_STATUS`
- `REPLAY_STATUS`

A field may carry `N/A` only when genuinely not applicable. Unknown factual state must be explicit, not omitted or invented.

## State model

Recommended event lifecycle:

`PROPOSED -> VALIDATED -> PREPARED -> COMMITTING -> COMMITTED -> CHECKPOINT_PENDING|CHECKPOINTED -> PROJECTED`

Abort/failure states include:
- `REJECTED_VALIDATION`
- `ABORTED`
- `COMMIT_FAILED`
- `CHECKPOINT_RETRY_REQUIRED`
- `PROJECTION_REJECTED`

A checkpoint failure after `COMMITTED` does not move the gameplay event back to PREPARED and does not make it eligible for gameplay re-execution.

## EVENT_ID / idempotency

- `EVENT_ID` is immutable once assigned.
- One semantic mutating action maps to one stable idempotency identity.
- `APPLIED_EVENT_LEDGER` is checked before applying consequences.
- Only an already committed event suppresses duplicate mutation.
- PREPARED transaction-local ledger candidates are not committed applied-event authority.
- A render/network/plugin/checkpoint-write retry cannot create a second gameplay mutation for a committed event.
- RNG results bound to a committed event cannot be rerolled because later persistence or presentation failed.

## Transaction and ledger preparation

Before `ATOMIC_COMMIT`:
- intended owner writes are transaction-local;
- `TX_STATUS` is `PREPARED` or `COMMITTING` as appropriate;
- event/receipt candidates may be prepared locally, but committed `APPLIED_EVENT_LEDGER_RECEIPT` is absent;
- `/save` or checkpoint authority is forbidden while TX is PREPARED or COMMITTING;
- optional `PRECOMMIT_SERIALIZATION_VALIDATION_STATUS` may record a non-authoritative structural validation result only.

## Atomic commit receipt

With successful `ATOMIC_COMMIT`:
- all dependent owner writes become authoritative at one logical commit boundary;
- the committed `EVENT_ID` is appended to `APPLIED_EVENT_LEDGER` exactly once;
- `TX_STATUS=COMMITTED`;
- `LOGICAL_COMMIT_INDEX` advances consistently;
- `LAST_COMMITTED_EVENT_ID` becomes the committed event;
- committed RNG/Spatial/Effect/Timer/DM/resource state is now gameplay authority.

If commit fails:
- touched owners restore to the PREPARE snapshot;
- `TX_STATUS=ABORTED`;
- no committed applied-event receipt survives;
- the logical event may follow the active deterministic retry policy.

## Optional precommit serialization validation

`PRECOMMIT_SERIALIZATION_VALIDATION_STATUS` may be used as a fail-fast structural check before commit.

It is never:
- `CHECKPOINT_STATUS`;
- `/save` authority;
- crash-recovery authority;
- evidence that a gameplay event committed.

## Checkpoint receipt

Checkpoint is post-commit.

Before checkpoint starts:
- `TX_STATUS` must be at a transaction boundary; PREPARED/COMMITTING must defer;
- committed owner state, committed `APPLIED_EVENT_LEDGER`, `LAST_COMMITTED_EVENT_ID`, and `LOGICAL_COMMIT_INDEX` are already authoritative.

A successful checkpoint must snapshot the same committed logical revision and include `APPLIED_EVENT_LEDGER` continuity.

If checkpoint write/roundtrip fails after commit:
- `CHECKPOINT_STATUS=CHECKPOINT_RETRY_REQUIRED` (or equivalent non-committed state);
- gameplay state remains committed;
- the committed event remains in `APPLIED_EVENT_LEDGER`;
- retry is checkpoint persistence only;
- RNG/resources/movement/damage/effects/loot/knowledge are not executed again.

## Source authority binding

`SOURCE_AUTHORITY_BINDINGS` records authoritative inputs needed to resolve the event. Before GitHub cutover, a Git commit alone cannot elevate mirrored bytes above approved Project authority.

## Transaction ownership

`TRANSACTION_OWNERS` enumerates all durable state owners touched before commit. Missing an affected owner is validation failure.

Potential owner classes include:
- `SAVE`
- `SPATIAL`
- `EFFECT`
- `TIMER`
- `RNG`
- `DM_STATE`
- `INVENTORY_RESOURCE`
- `NPC_STATE`
- `KNOWLEDGE`

No optional plugin, renderer, analytics sink or research connector may be a gameplay transaction owner.

## Knowledge / geometry / projection

`KNOWLEDGE_DELTA` is observer/branch scoped. Hidden causes/stats/geometry cannot leak merely because unrestricted state contains them.

Mapped topology binds Geometry Master identity; player-visible geometry follows `PLAYER_SAFE_STRUCTURE_PACKAGE`; deterministic mechanics own cell/door/connectivity semantics; visual output cannot become spatial truth.

`PLAYER_PROJECTION_STATUS=PASS` requires materialized `PLAYER_KNOWLEDGE_PROJECTION` and a passed knowledge-leak preoutput gate.

## Replay semantics

`REPLAY_STATUS` distinguishes at minimum:
- `FIRST_APPLY`
- `IDEMPOTENT_REPLAY_NOOP`
- `ABORTED_RETRY`
- `CHECKPOINT_RETRY_ONLY`
- `REPLAY_REJECTED_CONFLICT`

A committed event with failed checkpoint persistence is `CHECKPOINT_RETRY_ONLY`, not `ABORTED_RETRY`.
