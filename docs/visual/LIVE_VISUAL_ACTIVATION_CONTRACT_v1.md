# DND Live Visual Activation Contract v1

STATUS: CANDIDATE_TOOLING_EXECUTION_ONLY
SCOPE: tooling/live-visual-activation-v1
ACTIVE_RUNTIME_MUTATION: FALSE
CAMPAIGN_CANON_MUTATION: FALSE
RECOVERY_MUTATION: FALSE
GEOMETRY_MASTER_MUTATION: FALSE
PROJECT_SOURCE_SLOT_DELTA: 0

## Required live visual path

`COMMITTED GAME STATE -> PLAYER_KNOWLEDGE_PROJECTION -> KNOWLEDGE_LEAK_PREOUTPUT_GATE -> ENTITY_VISUAL_STATE -> SCENE CONTINUITY -> VISUAL_REFERENCE_MANIFEST / IDENTITY LOCK -> PLAYER_SAFE_GENERATION_PACKET -> ART GENERATION -> POST_RENDER COMPARATORS -> DISPLAY`

No alternate Runtime/Canon -> generator route is allowed. The activation layer is fail-closed and produces zero gameplay authority.

## Generation packet and decoration proof

The packet is synthesized only after the existing EVS, Scene Continuity Lock and Visual Identity Lock validators all PASS on the same state epoch / observer branch / materialized PKP lineage. The generator never receives unrestricted Runtime, Campaign Canon, hidden DM state, secrets, raw DM map data, or MAP_GEOMETRY_MASTER.

`DECORATION_BRIEF` is not trusted because its keys look harmless. It requires an external `PLAYER_SAFE_DECORATION_BRIEF` receipt binding the exact brief digest to exact PKP ID, observer branch, state epoch and leak-gate receipt. A changed value under `MOOD`, `DETAILS` or any other ordinary key invalidates the receipt. Key-name filtering remains defense-in-depth only.

The only geometry-facing handoff allowed to art is the identity of the exact materialized `PLAYER_SAFE_STRUCTURE_PACKAGE` plus `GEOMETRY_LOCK`. Topology remains owned by deterministic structure. The generator authority is `DECORATION_ONLY`.

For tactical output, grid, tokens, footprints, AoE, paths, labels and mechanical UI remain `DETERMINISTIC_POST_ART_ONLY` and never become generator authority.

## Canon direction and failure semantics

`CANON -> VISUAL` only. `VISUAL -> CANON` is forbidden.

A render result may not request or perform Canon writes, gameplay mutations, new gameplay events, rerolls or RNG. A failed/rejected render blocks display only. It never rolls back, repeats or changes committed gameplay.

## Post-render display barrier

Display requires both existing comparator systems to execute in the live path:

- Visual Identity Lock post-render comparator coverage for every visible entity, including mandatory identity and player-safe comparator classes.
- Scene Continuity post-render validation bound to the exact frame, render artifact ID/hash, visual manifest and current player-safe entity/fact state.

The identity-comparator payload resolves through an out-of-band read-only activation proof registry and binds exact activation ID, packet digest, frame, render artifact, visual manifest and comparator payload digest. Missing/foreign/mismatched receipts fail closed.

## Mandatory display ledger

Replay protection never depends on an optional caller-provided history list. `evaluate_for_display()` requires a materialized read-only `DisplayLedgerSnapshot` from `DISPLAY_LEDGER_OWNER`, bound to the same authoritative source revision as the activation proof registry. Raw lists/mappings, omitted ledgers, stale revisions and invalid ledger digests fail closed.

The ledger is checked for previously consumed activation IDs, render artifact IDs, identity-comparator receipts, player-safe receipts and tactical proof receipts. Runtime activation must source the current ledger snapshot from the durable display-ledger owner; the generator is not a ledger authority.

## Tactical gate — external proof only

The renderer may provide receipt IDs, but it may not self-assert tactical PASS strings. Legacy result fields such as `STRUCTURAL_PASS`, `PRESENTATION_PASS`, `GEOMETRY_COMPARE`, `VISUAL_PIPELINE_RECEIPT_STATUS`, `DETERMINISTIC_OVERLAY_STATUS`, `OVERLAY_SOURCE` and `TOPOLOGY_SOURCE` are rejected if supplied by the render result.

Tactical display requires five external read-only receipts, each bound to the exact activation, packet digest, render artifact ID/hash, `PLAYER_SAFE_STRUCTURE_PACKAGE_ID` and `GEOMETRY_LOCK_ID`:

- structural comparator: `STRUCTURAL_PASS=PASS` and topology source is the player-safe structure package;
- presentation validator: `PRESENTATION_PASS=PASS`;
- geometry comparator: `GEOMETRY_COMPARE=PASS` with zero mismatch counts for topology, connectivity, door state, grid cell and creature cell;
- visual pipeline receipt: `VISUAL_PIPELINE_RECEIPT_STATUS=PASS`;
- deterministic overlay validator: overlay PASS, `OVERLAY_SOURCE=DETERMINISTIC_POST_ART`, mechanical overlay authority deterministic post-art only.

The two tactical quality gates remain independent. A deterministic tactical diagram remains fallback-only and is never promoted to a primary illustrated pass by this contract.

## Source budget and activation boundary

This candidate consumes **zero new Project Source slots**. It is executable GitHub tooling/governance only and does not activate or edit the current Project Runtime bundle.

A later Runtime integration/promotion remains a separate reviewed change. Recovery #7 / Gate F, active Campaign Canon, Gates A-E and Geometry Master are untouched by this PR.