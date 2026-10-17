# QA Checklist — Entity Visual State + Persistent Anchor v1

TARGET: `tooling/entity-visual-state-v1`
TYPE: visual-governance/tooling review
DO NOT RUN: Gates A-E, Gate F, Recovery acceptance, Runtime promotion

## EVS-01 Scope isolation
PASS if only GitHub tooling/QA artifacts change. No active Runtime, Campaign Canon, Recovery, Geometry Master or Project Source membership mutation.

## EVS-02 Source budget
PASS only if `PROJECT_SOURCE_SLOT_DELTA=0`; future live activation must consolidate into an existing Visual/Runtime owner bundle.

## EVS-03 Derived-state authority
PASS if EVS is `DERIVED_NONAUTHORITATIVE` and committed Runtime/Save remains owner of current visible state.

## EVS-04 Player-safe provenance
PASS only if every player-facing EVS is bound to an exact materialized PKP ID, exact observer branch, matching source-state epoch and a concrete `KNOWLEDGE_LEAK_PREOUTPUT_GATE` PASS receipt. A bare `OBSERVER_SCOPE=PLAYER_SAFE` label is insufficient.

## EVS-05 Unknown-state semantics
PASS only if unknownable field names are pinned, typo/unknown names reject, each declared unknown contains exactly `{"VISIBILITY_STATE":"UNKNOWN"}`, a declared unknown cannot simultaneously carry resolved content, and the sentinel cannot appear without declaration.

## EVS-06 Identity class enforcement
PASS if all seven Visual Identity Lock classes are pinned to exact lock levels; unknown class or wrong lock level fails closed.

## EVS-07 Persistent anchor eligibility
PASS if anchors are limited to named recurring NPCs, named recurring monsters and unique bosses. PC/generic/background reuse is rejected.

## EVS-08 Anchor promotion receipt
PASS if promotion requires exact provenance, VIL PASS, explicit PLAYER_APPROVED|QA_APPROVED, nonempty promotion receipt ID, `PROMOTION_RECEIPT_STATUS=PASS`, and `ANCHOR_LIFECYCLE_STATUS=APPROVED`.

## EVS-09 Monster species authority
PASS if named monster/boss promotion requires official species/variant authority and anchors cannot replace it.

## EVS-10 No gameplay authority
PASS if anchors remain presentation-only and cannot own Canon, stats, equipment, form, mechanics or knowledge.

## EVS-11 Dynamic-state precedence
PASS if current Runtime/Save equipment/wounds/effects/form override stale anchor-image details.

## EVS-12 Form scope
PASS if reuse is rejected outside approved `FORM_SCOPE` or when bound scope metadata mismatches.

## EVS-13 Reuse promotion barrier
PASS only if reuse revalidates the full anchor-promotion contract and current EVS binds the same approved anchor ID/asset/promotion receipt. Unapproved, VIL-failed, candidate or forged anchors must reject.

## EVS-14 Fail-closed missing fields
PASS if missing required state/promotion/provenance fields reject instead of defaulting.

## EVS-15 Regression: forged player-safe label
PASS if `OBSERVER_SCOPE=PLAYER_SAFE` without exact materialized PKP receipt and leak-gate PASS receipt rejects.

## EVS-16 Regression: projection mismatch
PASS if PKP observer-branch mismatch or source-state-epoch mismatch rejects.

## EVS-17 Regression: unknown with content
PASS if a field listed unknown while carrying invented/resolved content rejects; typo unknown field also rejects.

## EVS-18 Regression: anchor reuse barrier
PASS if unapproved/VIL-failed/receipt-mismatched anchor reuse rejects, and PC/generic anchor reuse rejects.

## EVS-19 Regression: dynamic equipment continuity
PASS if a valid approved anchor remains reusable after a legitimate committed equipment change because dynamic state comes from current EVS.

## EVS-20 Machine discovery
PASS if Developer Preflight discovers the test file and covers every regression pinned by the manifest, including source-budget zero.

## Acceptance

QA PASS approves only the tooling/governance candidate. It does not activate Runtime logic, mutate Campaign Canon, modify Recovery, change a Gate verdict, create a Project Source or promote any visual asset into gameplay authority.
