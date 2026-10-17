# QA Checklist — Scene Continuity Lock v1

TARGET: `tooling/scene-continuity-lock-v1`
TYPE: visual-governance/tooling review
DO NOT RUN: Gates A-E, Gate F, Recovery acceptance, Runtime promotion

## SCL-01 Scope isolation
PASS only if changes remain GitHub tooling/QA artifacts. No active Runtime, Campaign Canon, Recovery, Geometry Master or Project Source membership mutation.

## SCL-02 Source budget
PASS only if `PROJECT_SOURCE_SLOT_DELTA=0`; future live activation must consolidate into an existing Visual/Runtime owner bundle.

## SCL-03 Trusted proof registries
PASS only if inline PASS/COMMITTED/player-safe labels are insufficient and proof-bearing claims must resolve through external trusted receipt registries.

## SCL-04 PKP / leak-gate binding
PASS only if group and every frame bind exact materialized PKP, observer branch, state epoch and leak-gate receipt through external receipts.

## SCL-05 EVS source binding
PASS only if every tracked entity resolves an external EVS receipt bound to exact entity, class, identity authority, PKP, branch, epoch and entity-state digest. Foreign EVS receipt must fail.

## SCL-06 Scene-fact source binding
PASS only if every fact resolves an external source receipt bound to exact fact/class/value digest/PKP/branch/epoch and allowed source kind.

## SCL-07 Hidden-content exclusion
PASS only if hidden/DM/sealed/unrestricted geometry sources cannot be relabeled as player-safe. `IMMUTABLE_STRUCTURE` must additionally bind exact player-safe structure package + GEOMETRY_LOCK identity.

## SCL-08 Geometry non-ownership
PASS only if continuity preserves but cannot mutate immutable player-safe structure/topology authority.

## SCL-09 Frame-chain integrity
PASS if IDs/indexes/previous-frame/group/observer bindings remain exact and fail closed on gaps or drift.

## SCL-10 Identity / anchor continuity
PASS if identity authority and approved recurring anchor lineage cannot drift inside one continuity group.

## SCL-11 Presentation boundary
PASS if camera/in-frame/art-direction changes remain presentation-only and cannot authorize gameplay/state changes.

## SCL-12 Applied-event proof
PASS only if gameplay/state changes reference an external Applied Event Ledger receipt. Self-asserted `COMMITTED`/`PASS` strings are forbidden as authority.

## SCL-13 Applied-event binding
PASS only if the external receipt binds exact EVENT_ID, transaction receipt, logical commit index, ledger membership, from/to epochs, committed revision and affected keys.

## SCL-14 Authoritative changeset proof
PASS only if the external receipt contains the authoritative before/after changeset and digest, and both exactly match the actual continuity diff for all claimed affected keys.

## SCL-15 Event replay/foreign rejection
PASS if wrong EVENT_ID, wrong epochs, wrong affected key, absent receipt, replayed receipt or digest mismatch fails closed. Sequence-level validation must reject reuse of a state-changing `APPLIED_EVENT_LEDGER_RECEIPT_ID` or `EVENT_ID` on any later transition in the same continuity group and require strictly increasing `LOGICAL_COMMIT_INDEX` in frame order.

## SCL-16 Post-render artifact binding
PASS only if render acceptance binds exact FRAME_ID, group, render artifact ID/hash, visual manifest ID and derived frame-state digest.

## SCL-17 VIL / player-safe render binding
PASS only if external VIL and player-safe-render receipts are PASS and bind the exact same frame/render/hash/manifest/state identity.

## SCL-18 Per-entity/per-fact render receipts
PASS only if every in-frame entity/fact has its own external structured receipt bound to exact frame/render/hash/manifest/state plus entity/fact identity and state/value digest. Bare PASS maps are forbidden.

## SCL-19 Replay regressions
PASS if CI rejects foreign VIL, reused entity/fact continuity receipt, render hash mismatch, foreign EVS, hidden fact with fake PASS source, forged event status, wrong event ID, wrong affected-key receipt, replayed Applied Event receipt/event across separate transitions, and non-monotonic logical commit progression. CI must also retain a valid multi-event monotonic-sequence acceptance case.

## SCL-20 Non-mutating failure / machine discovery
PASS if rejected render cannot mutate gameplay or reroll/replay state, tests are Developer-Preflight-discovered, and manifest regressions exactly match executable regressions.

## Acceptance

QA PASS approves only this tooling/governance candidate. It does not activate Runtime logic, mutate Campaign Canon, modify Recovery, change a Gate verdict, create a Project Source, alter Geometry Master authority or promote generated art into gameplay authority.
