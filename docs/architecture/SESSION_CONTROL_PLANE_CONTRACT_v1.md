# DND Session Control Plane Contract v1

STATUS: CANDIDATE_CONTRACT_ONLY
SCOPE: tooling/session-control-plane-v1
ACTIVE_RUNTIME_MUTATION: FALSE
CAMPAIGN_CANON_MUTATION: FALSE
RUNTIME_PROMOTION: FALSE
GATE_STATUS_MUTATION: FALSE
SOURCE_OF_TRUTH_POLICY: docs/SOURCE_OF_TRUTH_POLICY.md
ACTIVE_RUNTIME_EXECUTION_BINDING: SYS.NATIVE.R107 + SYS.NATIVE.R108 + SYS.NATIVE.R109 + SAVE.NATIVE.R110

## Purpose

Define a future orchestration contract for deterministic session execution without modifying the active runtime or current campaign recovery line.

The control plane coordinates owners. It is not a new gameplay authority and must preserve the active System Integrity ordering rather than invent a competing save/commit model.

## Required execution pipeline

The normative required stage order is:

`COMMAND -> EVENT_ENVELOPE -> VALIDATION -> TRANSACTION_STAGE -> LEDGER_STAGE_PREPARED -> ATOMIC_COMMIT -> CHECKPOINT_BARRIER -> PLAYER_PROJECTION`

An optional `PRECOMMIT_SERIALIZATION_VALIDATION` may run between `LEDGER_STAGE_PREPARED` and `ATOMIC_COMMIT`, but it is validation only. It is not `/save`, not a checkpoint, not durable checkpoint authority, and cannot set `CHECKPOINT_STATUS=COMMITTED`.

This ordering preserves the active runtime contract:
- `EVENT_ID` is allocated before mutation and checked against committed applied-event history;
- intended owner writes are staged before commit;
- `APPLIED_EVENT_LEDGER` is updated only with a successful atomic commit;
- `/save` or checkpoint work may begin only at a transaction boundary and must be deferred while `TX_STATUS=PREPARED|COMMITTING`;
- a checkpoint captures one already-committed logical revision including `LAST_COMMITTED_EVENT_ID` and `APPLIED_EVENT_LEDGER` continuity.

### 1. COMMAND

- Normalize player/DM intent into a command request.
- Command parsing alone cannot mutate gameplay state.
- Observer/party branch context must be resolved before any player-facing consequence is emitted.
- Unknown or ambiguous mutation ownership fails closed rather than guessing.

### 2. EVENT_ENVELOPE

- Assign a stable `EVENT_ID` before mutation.
- Bind campaign/session/branch/actor identity and observer scope.
- Bind source-authority references required for resolution.
- Bind idempotency identity before transaction execution.
- Envelope creation is not itself a Canon mutation.

### 3. VALIDATION

Validation must occur before authoritative state mutation.

Required checks include:
- source authority and ruleset availability;
- command legality;
- state preconditions;
- owner set completeness;
- Geometry Master ownership for mapped topology;
- observer/branch scope;
- knowledge-leak constraints;
- RNG requirement and RNG state availability;
- idempotency check against committed `APPLIED_EVENT_LEDGER` entries;
- capability availability for deterministic mechanics.

Missing deterministic capability or authority fails closed unless an exact deterministic fallback is explicitly defined.

### 4. TRANSACTION_STAGE

All intended gameplay mutations are prepared inside one multi-owner transaction against one frozen pre-commit revision.

Potential owners include, when relevant:
- campaign/save state;
- spatial state;
- effect state;
- timer state;
- RNG state/receipt state;
- DM state;
- inventory/resource state;
- NPC state;
- knowledge state.

Rules:
- intended writes are staged without mutating authoritative state;
- all affected owners are resolved before commit;
- no owner may publish independently;
- any failed validation aborts the transaction;
- renderer, analytics, research and plugin systems are never transaction owners.

### 5. LEDGER_STAGE_PREPARED

Transaction-local ledger candidates are prepared before commit.

Required invariants:
- staged ledger candidates carry the same `TX_ID`/`EVENT_ID` identity as the transaction;
- transaction-local event status may be `PREPARED`;
- the event MUST NOT yet be appended as committed to durable `APPLIED_EVENT_LEDGER`;
- staged/pending candidates MUST NOT suppress a legitimate retry;
- required Spatial/Effect/Timer/RNG/DM receipts are prepared consistently with the same frozen pre-state;
- secret/discovered/traversed semantics remain distinct;
- unknown facts remain explicit `UNKNOWN`/unavailable states rather than inferred replacements.

### Optional PRECOMMIT_SERIALIZATION_VALIDATION

This optional stage may validate that the candidate post-state is structurally serializable before commit.

It MUST NOT:
- invoke `/save` authority;
- allocate a committed checkpoint;
- claim `CHECKPOINT_STATUS=COMMITTED`;
- write a committed `APPLIED_EVENT_LEDGER` receipt;
- be treated as recovery authority after a crash.

Its only purpose is fail-fast validation before entering `ATOMIC_COMMIT`.

### 6. ATOMIC_COMMIT

The active runtime commit boundary is authoritative.

Required invariants:
- no narration, `/save`, render, tool retry side-effect or unrelated event may interleave inside commit;
- all dependent owner writes become authoritative as one logical commit boundary;
- committed `EVENT_ID` values are appended to `APPLIED_EVENT_LEDGER` only with successful commit;
- successful commit advances one logical commit revision and exposes `LAST_COMMITTED_EVENT_ID`;
- commit failure restores all touched owners to the PREPARE snapshot, marks the transaction aborted and leaves no committed applied-event entry;
- committed RNG/resource/movement/effect consequences are not replayed merely because later checkpoint persistence fails.

After successful `ATOMIC_COMMIT`, the gameplay event is authoritative even if the subsequent checkpoint write must be retried.

### 7. CHECKPOINT_BARRIER

Checkpoint work occurs only after the transaction has reached a boundary.

Required invariants:
- if `TX_STATUS=PREPARED|COMMITTING`, checkpoint is deferred and serialization as checkpoint authority is forbidden;
- checkpoint freezes one `CHECKPOINT_SNAPSHOT_ID` from all durable owners at the same already-committed logical commit index;
- checkpoint includes `LAST_COMMITTED_EVENT_ID` and `APPLIED_EVENT_LEDGER` continuity data;
- required save serialization and roundtrip/consistency checks operate on committed state, not staged owner candidates;
- `FINAL_CHECKPOINT_STATUS=COMMITTED` is allowed only if the save/roundtrip barrier succeeds;
- no checkpoint may contain a partial multi-owner event.

Checkpoint-write/roundtrip failure after a successful gameplay commit does **not** roll back or replay the gameplay event. Instead:
- gameplay state remains committed;
- the committed `EVENT_ID` remains in `APPLIED_EVENT_LEDGER`;
- RNG/resource/movement/effect mutations are not repeated;
- only checkpoint persistence/verification is retried for the same committed logical revision;
- player-facing delivery may fail closed until the required durable checkpoint policy is satisfied, but the semantic event is not executed twice.

### 8. PLAYER_PROJECTION

Every player-facing result is built from a materialized `PLAYER_KNOWLEDGE_PROJECTION` for the correct observer/branch.

Required constraints:
- unrestricted DM/Combat/Adventure runtime data cannot be serialized directly to player output;
- enemy exact HP remains hidden unless explicitly enabled by the user;
- hidden geometry, source provenance, DM room IDs/pages/stat-block references and sealed fields remain hidden during normal gameplay;
- observable consequences may be narrated without revealing hidden causes/stats;
- split-party knowledge does not merge without valid communication/reunion;
- `KNOWLEDGE_LEAK_PREOUTPUT_GATE` must approve the projection before delivery.

## Post-checkpoint derivative bus

Optional derivatives may consume only committed gameplay state and safe projections/checkpoint receipts according to their own contracts:

`COMMITTED_STATE / CHECKPOINT / PLAYER_PROJECTION -> SAFE_EXPORT_BUS -> Visual / Audio / Neon / Miro / Notion / Firecrawl / Acrobat / future VTT adapters`

External integrations:
- never become transaction owners;
- never mutate Canon automatically;
- never create Gate PASS;
- never create Geometry Master authority;
- fail independently from gameplay state.

## Geometry ownership

- Geometry Master owns mapped topology.
- `PLAYER_SAFE_STRUCTURE_PACKAGE` owns player-visible geometry.
- `GEOMETRY_LOCK` must be materialized before illustrated tactical structure can be valid.
- art generation owns decoration only.
- grid/tokens/footprints/AoE/paths/labels/mechanical UI are deterministic post-art overlays.
- topology/connectivity/door-state/grid-cell/creature-cell mismatch tolerance is zero.
- CANON -> VISUAL only; VISUAL -> CANON is forbidden.

## Idempotency and retry contract

For every mutating command:
- one stable `EVENT_ID` is selected before mutation;
- committed `APPLIED_EVENT_LEDGER` entries suppress duplicate mutation;
- PREPARED transaction-local candidates do not;
- a committed duplicate returns prior durable result/receipt or `IDEMPOTENT_REPLAY_NOOP`;
- commit failure/abort may deterministically retry the same logical event under the active runtime policy;
- checkpoint failure after commit is **checkpoint retry only**, never gameplay retry;
- checkpoint retry must not reroll RNG or reapply resource spend, movement, damage, effects, loot or knowledge changes.

## Rollback contract

Rollback applies to failed PREPARE/VALIDATE/ATOMIC_COMMIT, restoring every touched owner to the frozen pre-event revision.

A post-commit checkpoint failure is not a transaction rollback.

Forbidden states:
- spatial committed while inventory rolled back;
- RNG advanced while action/effect rolled back after failed commit without a durable compensating rule;
- knowledge delta emitted for an event that never committed;
- checkpoint accepted from PREPARED or COMMITTING state;
- checkpoint payload whose `LAST_COMMITTED_EVENT_ID`, `APPLIED_EVENT_LEDGER` or logical revision differs from the committed state it claims to snapshot;
- committed event replayed because checkpoint persistence failed.

## Runtime-alignment regression requirements

The contract is not acceptable without executable regressions demonstrating at minimum:
1. checkpoint cannot start while `TX_STATUS=PREPARED|COMMITTING`;
2. a committed event survives checkpoint-write/roundtrip failure and keeps its committed applied-event entry;
3. retrying checkpoint persistence for that revision does not repeat RNG/resources/movement/other gameplay consequences;
4. a successful checkpoint contains the committed `EVENT_ID`, committed `APPLIED_EVENT_LEDGER`, and the same logical commit revision;
5. duplicate delivery of an already committed `EVENT_ID` remains an idempotent no-op.

## Session lifecycle contract

Future session boot should validate, without mutating Canon:
- active runtime identity;
- save/runtime schema compatibility;
- required PC sheets;
- source bindings/hashes;
- active map/Geometry Master binding when mapped play requires it;
- durable Spatial/Effect/Timer/RNG/DM state;
- current branch/observer integrity;
- knowledge-projection buildability.

Optional integrations are health indicators only and cannot block core gameplay unless the user explicitly requests a dependent feature.

## Activation barrier

This candidate is documentation/tooling only. It MUST NOT:
- modify the active runtime bundle;
- mutate the campaign save;
- claim runtime promotion;
- claim recovery acceptance;
- reopen Gates A-E;
- claim Gate F;
- change source-of-truth cutover state.

Runtime implementation requires a separate reviewed implementation candidate and explicit promotion path.
