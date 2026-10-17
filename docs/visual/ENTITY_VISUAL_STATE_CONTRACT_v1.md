# DND Entity Visual State + Persistent Anchor Contract v1

STATUS: CANDIDATE_TOOLING_CONTRACT_ONLY
SCOPE: tooling/entity-visual-state-v1
ACTIVE_RUNTIME_MUTATION: FALSE
CAMPAIGN_CANON_MUTATION: FALSE
RECOVERY_MUTATION: FALSE
PROJECT_SOURCE_SLOT_DELTA: 0
SOURCE_BUDGET_POLICY: ENFORCED
DEPENDS_ON: VISUAL_IDENTITY_LOCK_V1

## Purpose

Materialize derived visual state from committed, player-safe information and define persistent visual anchors for named recurring NPCs/monsters/bosses. `ENTITY_VISUAL_STATE` never creates gameplay truth.

## Authority chain

`COMMITTED_CANON / SAVE -> MATERIALIZED PLAYER_KNOWLEDGE_PROJECTION -> KNOWLEDGE_LEAK_PREOUTPUT_GATE PASS -> ENTITY_VISUAL_STATE -> VISUAL_REFERENCE_MANIFEST -> GENERATION -> VISUAL_IDENTITY_LOCK_RECEIPT -> DISPLAY`

`ENTITY_VISUAL_STATE = DERIVED_NONAUTHORITATIVE`.

## Player-safe provenance binding

`OBSERVER_SCOPE=PLAYER_SAFE` is not proof by itself. Every player-facing EVS must carry all of the following and fail closed if any are missing or mismatched:

- `OBSERVER_BRANCH_ID`;
- exact `PLAYER_KNOWLEDGE_PROJECTION_ID`;
- `PLAYER_KNOWLEDGE_PROJECTION_STATUS = MATERIALIZED`;
- `PLAYER_KNOWLEDGE_PROJECTION_OBSERVER_BRANCH_ID` equal to `OBSERVER_BRANCH_ID`;
- `PLAYER_KNOWLEDGE_PROJECTION_SOURCE_STATE_EPOCH` equal to the EVS `SOURCE_STATE_EPOCH`;
- `KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID`;
- `KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS = PASS`.

A self-asserted player-safe label, a projection from another observer branch, a stale projection epoch, or a missing leak-gate receipt cannot authorize display.

## ENTITY_VISUAL_STATE schema

Each visible recurring entity includes identity authority, current form, current visible equipment/wounds/effects/transformation, committed source epoch, exact player-safe provenance receipts, unknown-state metadata, derived authority marker, source-slot delta, and anchor metadata when applicable.

Allowed identity classes/lock levels:

- `PC -> VERY_STRICT`
- `NAMED_RECURRING_NPC -> STRICT`
- `NAMED_RECURRING_MONSTER -> STRICT`
- `UNIQUE_BOSS -> STRICT`
- `STANDARD_MONSTER_SPECIES -> MODERATE`
- `GENERIC_MOB -> LOOSE_WITH_SPECIES_GUARD`
- `BACKGROUND_CROWD -> LOOSE_WITH_SPECIES_GUARD`

Unknown class or wrong lock level fails closed.

## Dynamic state ownership

The identity reference owns stable visual identity only. The newest committed Runtime/Save owns current visible equipment, wounds, effects, form and transformation. Old art or anchors cannot restore stale state.

## Unknown-state rule

Unknown is a machine-enforced state, not a prose label.

Only these fields may be placed in `UNKNOWN_VISIBLE_FIELDS`:

- `CURRENT_VISIBLE_EQUIPMENT`
- `CURRENT_VISIBLE_WOUNDS_OR_MARKS`
- `CURRENT_VISIBLE_EFFECTS`
- `CURRENT_VISIBLE_TRANSFORMATION`

An unknown field must contain exactly the neutral representation:

`{"VISIBILITY_STATE":"UNKNOWN"}`

A listed unknown field carrying resolved/invented content fails. The sentinel without declaration fails. Unknown/typo field names fail. Unknown values may not be filled from hidden DM state, old art or aesthetic preference.

## Campaign Visual Anchor lifecycle

Anchor-eligible classes are only:

- `NAMED_RECURRING_NPC`
- `NAMED_RECURRING_MONSTER`
- `UNIQUE_BOSS`

PCs remain bound to their approved individual `VIS_PC_*` masters. Generic mobs and background crowds do not receive persistent instance anchors.

Lifecycle:

`IDENTITY AUTHORITY -> CAMPAIGN STYLE RENDER -> VIL PASS -> PLAYER_APPROVED|QA_APPROVED -> PROMOTION RECEIPT PASS -> ANCHOR_LIFECYCLE_STATUS=APPROVED`

Promotion requires exact entity/identity authority, actual anchor asset, source render/state epoch, form scope, VIL PASS, explicit approval, `PROMOTION_RECEIPT_ID`, `PROMOTION_RECEIPT_STATUS=PASS`, approved lifecycle, and for named monsters/bosses official species/variant authority. Anchors remain non-canonical presentation infrastructure and all override flags must remain false.

## Anchor reuse

Reuse cannot bypass promotion. Before reuse the anchor record is revalidated against the full promotion contract.

Reuse additionally requires:

- current entity class is anchor-eligible;
- current EVS has `CAMPAIGN_ANCHOR_STATUS=APPROVED`;
- entity ID/class and identity lineage match;
- current anchor ID/asset match the approved record;
- promotion receipt ID matches the one bound into current EVS and its status is PASS;
- current form is inside the exact approved `FORM_SCOPE` and form-scope metadata matches;
- monster species/variant authority remains present where required.

PC/generic/background anchor reuse is rejected. A VIL-failed, unapproved, candidate, forged, receipt-mismatched or otherwise invalid anchor is rejected.

Dynamic equipment/wounds/effects still come from current EVS and may legitimately change without invalidating recurring identity.

## Persistent anchor storage

Anchors are presentation assets/metadata. They do not become Campaign Canon. Storage must preserve provenance and must not consume a new permanent Project Source slot unless separately justified under `SOURCE_BUDGET_POLICY_V1`.

## Fail-closed summary

Reject when player-safe provenance is unbound, observer branch/epoch mismatches, leak gate did not PASS, unknown semantics are malformed, identity class/lock is invalid, anchor promotion lacks its proof chain, anchor reuse bypasses promotion, an ineligible class uses an anchor, or source-slot delta is non-zero.

## Source budget

This package uses **zero new Project Source slots**. Future live activation must consolidate into an existing Visual/Runtime owner bundle or replacement bundle.

## Activation barrier

This PR is tooling/governance only. It does not activate Runtime logic, mutate Campaign Canon, alter Recovery, reopen Gates A-E, claim Gate F, or promote any image to gameplay authority. Live activation requires a separate reviewed change.
