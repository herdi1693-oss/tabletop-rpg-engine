# DND Scene Continuity Lock Contract v1

STATUS: CANDIDATE_TOOLING_CONTRACT_ONLY
SCOPE: tooling/scene-continuity-lock-v1
ACTIVE_RUNTIME_MUTATION: FALSE
CAMPAIGN_CANON_MUTATION: FALSE
RECOVERY_MUTATION: FALSE
PROJECT_SOURCE_SLOT_DELTA: 0
SOURCE_BUDGET_POLICY: ENFORCED
DEPENDS_ON: VISUAL_IDENTITY_LOCK_V1, ENTITY_VISUAL_STATE_V1

## Purpose

Keep repeated shots, comic panels, combat sequences and recap frames visually continuous without allowing art to create gameplay truth. Scene Continuity is a derived presentation contract over already committed, player-safe state.

`CANON -> VISUAL` only. `VISUAL -> CANON` is forbidden.

## Proof model

Scene Continuity MUST NOT trust inline `PASS`, `COMMITTED`, `PLAYER_SAFE` or similar strings as authority.

All proof-bearing claims are resolved against external trusted receipt registries supplied by the upstream owner that actually produced the proof. At minimum the tooling validator requires registries for materialized Player Knowledge Projection receipts, knowledge-leak preoutput gate receipts, Entity Visual State receipts, player-safe scene source receipts, Applied Event Ledger receipts, Visual Identity Lock receipts, per-entity post-render receipts, per-fact post-render receipts, and player-safe render receipts.

A receipt ID that is absent from the matching trusted registry, foreign to the frame/branch/epoch/entity/fact/event, replayed from another frame/render/transition, or internally inconsistent fails closed.

## Player-safe provenance

Every continuity group and every frame is bound to exact `PLAYER_KNOWLEDGE_PROJECTION_ID`, observer branch, source state epoch, external materialized PKP receipt, and external leak-gate PASS receipt bound to that same PKP/branch/epoch. Inline group/frame status fields are descriptive only and cannot replace the external receipts.

## Entity source proof

Every tracked entity carries an `EVS_VALIDATION_RECEIPT_ID`. The corresponding external EVS receipt MUST bind receipt ID, `STATUS=PASS`, exact `ENTITY_ID`, entity class, identity authority, exact PKP, observer branch, source state epoch, and digest of the actual entity visual state used by the frame. A foreign EVS receipt from another epoch, branch, entity or state fails.

## Player-safe scene facts

Only `IMMUTABLE_STRUCTURE` and `DYNAMIC_PLAYER_SAFE` are accepted. Every fact carries a source receipt ID. The external source receipt MUST bind exact `FACT_ID`, fact class, digest of exact fact value, PKP, observer branch, state epoch, `STATUS=PASS`, and allowed source kind.

For `IMMUTABLE_STRUCTURE`, source kind MUST be `PLAYER_SAFE_STRUCTURE_PACKAGE` and the receipt MUST identify both the exact player-safe structure package and exact `GEOMETRY_LOCK`, with geometry-lock proof PASS.

For `DYNAMIC_PLAYER_SAFE`, source kind MUST be `PLAYER_KNOWLEDGE_PROJECTION`.

Hidden DM state, sealed state, unrestricted Geometry Master content, source-only room facts, unrevealed creatures and self-labeled player-safe data are invalid sources.

## Continuity identity

Within one continuity group, identity authority and approved recurring campaign anchor lineage are stable. Current form, equipment, wounds, effects and transformations come from validated EVS state and may change only after proven committed gameplay state change.

## Presentation-only freedom

In-frame lists, camera shot, art-direction lighting and color grade may change without gameplay mutation. Presentation choices never authorize mechanics, topology, knowledge or state mutation.

## Transition proof

Allowed causes are `CAMERA_ONLY` and `COMMITTED_GAMEPLAY_EVENT`. `CAMERA_ONLY` may cover only presentation keys.

A `COMMITTED_GAMEPLAY_EVENT` cause MUST reference an external `APPLIED_EVENT_LEDGER_RECEIPT_ID`. Inline claims such as `EVENT_COMMIT_STATUS=COMMITTED` or `APPLIED_EVENT_LEDGER_RECEIPT_STATUS=PASS` are forbidden as proof.

The external Applied Event Ledger receipt MUST bind exact receipt ID, `AUTHORITY=APPLIED_EVENT_LEDGER`, exact `EVENT_ID`, committed status, transaction receipt ID, logical commit index, proof that the event is present in the applied-event ledger, exact from-state epoch, exact to-state epoch, exact committed revision, exact affected continuity keys, authoritative before/after changeset for every affected key, and deterministic digest of event ID, epochs, affected-key list and authoritative changeset.

The validator computes the actual continuity diff between the two frames and requires receipt `AFFECTED_KEYS` and authoritative changeset to match that diff exactly for the keys claimed by that cause. Foreign, replayed, fabricated or mismatched applied-event receipts fail closed.

Across one continuity group, a state-changing `APPLIED_EVENT_LEDGER_RECEIPT_ID` may authorize at most one transition and a committed `EVENT_ID` may not be reused to authorize a later transition. `LOGICAL_COMMIT_INDEX` values for state-changing causes must increase strictly in frame order across the whole sequence. Duplicate receipt/event identity or non-monotonic commit progression fails closed even when each transition would pass in isolation.

## Frame chain

Frames are ordered by unique `FRAME_INDEX`, linked by `PREVIOUS_FRAME_ID`, bound to one continuity group and observer branch, and independently player-safe validated. First frame uses `PREVIOUS_FRAME_ID=null`; later frames point to the immediately preceding frame.

## Post-render proof

The render acceptance envelope MUST identify exact frame, continuity group, render artifact ID, SHA-256 render artifact hash, visual manifest ID, derived frame-state digest, external VIL receipt ID, external player-safe-render receipt ID, one external entity-continuity receipt ID for every in-frame entity, and one external scene-fact-continuity receipt ID for every in-frame fact.

Bare `entity_id -> PASS` or `fact_id -> PASS` maps are forbidden.

Every external render-time receipt MUST bind the same `FRAME_ID`, `CONTINUITY_GROUP_ID`, `RENDER_ARTIFACT_ID`, `RENDER_ARTIFACT_HASH`, `VISUAL_MANIFEST_ID`, and `FRAME_STATE_DIGEST`. Entity receipts additionally bind exact `ENTITY_ID` and entity-state digest. Fact receipts additionally bind exact `FACT_ID` and fact-value digest. VIL and player-safe render receipts must both be `PASS`.

A receipt from another frame, render, manifest, frame state, entity or fact fails closed. Render-artifact hash mismatch fails closed. Reusing one per-entity/per-fact receipt ID for multiple targets fails closed.

## Geometry ownership

Scene Continuity may preserve player-safe deterministic structure but never owns or changes topology. `IMMUTABLE_STRUCTURE` cannot be mutated inside a continuity group. Geometry Master ownership, player-safe structure ownership, deterministic overlays and zero-tolerance topology rules remain unchanged.

## Render failure semantics

A rejected continuity render is presentation failure only. It does not mutate gameplay, spend resources, reroll RNG, move actors, alter knowledge, change scene facts or roll back a committed event. Regeneration uses the same committed/player-safe frame state unless a later committed event legitimately changes it.

## Source budget

This package uses **zero new Project Source slots**. Future live activation must consolidate into an existing Visual/Runtime owner bundle or replacement bundle under `SOURCE_BUDGET_POLICY_V1`.

## Activation barrier

This PR is tooling/governance only. It does not activate Runtime logic, mutate Campaign Canon, alter Recovery, reopen Gates A-E, claim Gate F, change Geometry Master authority or create a Project Source. Live activation requires a separate reviewed change.
