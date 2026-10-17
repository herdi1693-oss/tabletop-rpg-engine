# QA Checklist — Live Visual Activation v1

TARGET: `tooling/live-visual-activation-v1`
MODE: targeted tooling execution QA
DO NOT RUN: Runtime promotion, Recovery #7 acceptance, Gate F, Gates A-E

## Scope
PASS only if current Runtime, Campaign Canon, Recovery, Geometry Master and Project Source membership are untouched and `PROJECT_SOURCE_SLOT_DELTA=0`.

## Pipeline ownership
Attack every shortcut around:
`COMMITTED_STATE -> PKP -> LEAK_GATE -> EVS -> SCL -> VIL -> PLAYER_SAFE_GENERATION_PACKET`.
Any direct unrestricted Runtime/Canon/DM input to generation must fail closed.

Verify the executable entrypoint actually calls EVS, Scene Continuity and Visual Identity guards; import-only/dead-code integration is FAIL.

## Decoration-brief player-safety proof
Do not limit hidden-state attacks to suspicious key names. Put hidden DM truth under ordinary keys such as `MOOD`, `DETAILS`, nested arrays and localized text.

Generation PASS requires an external `PLAYER_SAFE_DECORATION_BRIEF` receipt bound to exact brief digest + PKP + observer branch + epoch + leak-gate receipt. Change any one after receipt issuance: FAIL. Missing/foreign/raw self-asserted decoration proof: FAIL.

## Hidden-state / geometry isolation
Inject hidden DM facts, secrets, raw DM map/topology or direct MAP_GEOMETRY_MASTER fields at any nested generation-input level. Generation must fail before art dispatch.

Only exact `PLAYER_SAFE_STRUCTURE_PACKAGE_ID + GEOMETRY_LOCK_ID` lineage may cross the structure boundary. Art gets decoration authority only.

## Render failure semantics
Force art failure, comparator rejection and missing receipts. Gameplay state, Canon, RNG/resources/events and committed revisions must remain untouched. A retry is a visual retry only.

## Post-render barrier and replay ledger
Identity and player-safe/scene-continuity comparators are mandatory. Attack with missing, foreign, old-render, wrong-manifest, wrong-packet and replayed receipts. Display must remain blocked.

Omit display history entirely or pass `[]`/`{}`: FAIL. Display requires a materialized read-only `DisplayLedgerSnapshot` from `DISPLAY_LEDGER_OWNER`, same source revision as activation proofs, valid digest. Reuse a prior activation/render/identity/player-safe/tactical receipt from the materialized ledger: FAIL.

A raw caller-provided mapping may not self-assert activation proof authority.

## Tactical mode
Renderer-authored PASS strings are not proof. Supplying `STRUCTURAL_PASS`, `PRESENTATION_PASS`, `GEOMETRY_COMPARE`, pipeline/overlay PASS, overlay source or topology source directly in `render_result` must fail.

Require five external receipts: structural, presentation, geometry, visual-pipeline and deterministic-overlay. Bind each to exact PSSP + GEOMETRY_LOCK + activation + packet + render ID/hash. Change any binding: FAIL.

Geometry comparator semantic mismatch tolerance is zero for topology/connectivity/door-state/grid-cell/creature-cell. Either `STRUCTURAL_PASS` or `PRESENTATION_PASS` failing independently blocks display. Generated grid/tokens/footprints/AoE/path/labels/mechanical UI is FAIL.

## Source budget
No permanent new Project Source. Future live Runtime activation remains a separate reviewed integration/promotion change.

## Verdict
PASS authorizes only this exact tooling head for merge. It does not itself promote or replace the active Project Runtime.