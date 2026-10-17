# QA Checklist — Visual Identity Lock v1

TARGET: `tooling/visual-identity-lock-v1`
TYPE: visual-governance/tooling review
DO NOT RUN: Gates A-E, Gate F, Recovery acceptance, Runtime promotion

## VIL-01 Scope isolation
PASS if the candidate changes only GitHub/tooling/QA artifacts. No active Runtime bundle, Campaign Save, PC Sheet, Recovery PR #7, Geometry Master or Project Source membership may change.

## VIL-02 Source budget
PASS only if `PROJECT_SOURCE_SLOT_DELTA=0`. Architecture docs, manifests, validators and tests remain outside permanent Project Sources. Any future activation must prefer consolidation into an existing Visual/Runtime owner bundle.

## VIL-03 PC identity authority
PASS if every approved PC requires its individual Visual Master and `VERY_STRICT` identity lock; group art or generic class appearance cannot replace it.

## VIL-04 Monster identity vs style
PASS if official MM/adventure art is treated as species/form identity authority but not style authority. Campaign realism/cinematic restyling is allowed while species silhouette, anatomy, defining heads/limbs/features, current form and unique variant identity remain locked.

## VIL-05 Named recurring anchor
PASS if an approved campaign anchor may lock the recurring appearance of a named NPC/monster/boss but cannot override species authority, current runtime form, equipment ownership, mechanics or hidden information.

## VIL-06 Derived ENTITY_VISUAL_STATE
PASS if current visible equipment, wounds, effects/forms and other dynamic appearance are derived from committed owners, never inferred from old art, and never become independent Canon.

## VIL-07 Reference handoff fail-closed
PASS if every manifest entity has resolved reference authority, actual reference asset and `HANDOFF_STATUS=PASSED`; otherwise image generation is blocked.

## VIL-08 Equipment guard
PASS if visual composition cannot invent, restore or swap visible equipment in conflict with committed Runtime/Save state.

## VIL-09 Multi-panel continuity
PASS if one continuity group reuses the same PC Visual Master / recurring anchor per entity across panels and rejects uncaused face/body/species/reference swaps.

## VIL-10 Post-render comparator completeness / fail-closed
PASS only if every entity in the visual manifest has one explicit comparator receipt before display. The receipt must explicitly contain all six comparator classes (`PC_IDENTITY`, `SPECIES_FORM_IDENTITY`, `RECURRING_INSTANCE_IDENTITY`, `VISIBLE_EQUIPMENT_STATE`, `SCENE_CONTINUITY`, `PLAYER_SAFE_CONTENT`) using only `PASS|FAIL|NA`, plus an explicit `FAILURE_FLAGS` list.

Fail if any of the following is possible:
- empty observations/receipts implicitly pass;
- one manifest entity is omitted from post-render review;
- one comparator key is missing, even if non-applicable;
- an unknown comparator key or status is ignored;
- an applicable comparator is marked `NA`;
- an unknown/typo failure flag is ignored;
- a receipt exists for an entity not in the manifest.

Any comparator `FAIL` or known hard-failure flag must reject the render regardless of aesthetics.

## VIL-11 ENTITY_CLASS enum / lock-level completeness
PASS only if the allowed entity classes are pinned exactly and every class enforces its required lock level:
- PC = VERY_STRICT
- NAMED_RECURRING_NPC = STRICT
- NAMED_RECURRING_MONSTER = STRICT
- UNIQUE_BOSS = STRICT
- STANDARD_MONSTER_SPECIES = MODERATE
- BACKGROUND_CROWD = LOOSE_WITH_SPECIES_GUARD
- GENERIC_MOB = LOOSE_WITH_SPECIES_GUARD

Unknown `ENTITY_CLASS` or a wrong lock level for any class must fail closed.

## VIL-12 Player-safe input
PASS if art consumes a materialized player-safe scene / PLAYER_KNOWLEDGE_PROJECTION and cannot expose hidden DM geometry, creatures, future forms, source provenance or sealed fields during normal play.

## VIL-13 Canon direction
PASS if `CANON -> VISUAL` only; visual output and campaign anchors are presentation infrastructure and cannot mutate gameplay state.

## VIL-14 Regression: PC drift
PASS if an approved PC rendered as a visibly different identity (example: Aelian rendered with an incompatible dark-haired generic-barbarian identity) is rejected even when the image is otherwise high quality.

## VIL-15 Regression: monster style freedom
PASS if a monster rendered in campaign cinematic-realism is accepted when species/form identity is preserved; visual restyling alone must not fail.

## VIL-16 Regression: monster species drift
PASS if wrong species/form/defining anatomy is rejected. Example: an ettin losing defining two-headed anatomy must fail regardless of aesthetics.

## VIL-17 Regression: recurring anchor / continuity
PASS if an approved named-monster/NPC anchor is required on future depictions and changing a recurring entity's reference/anchor between panels in the same `CONTINUITY_GROUP_ID` fails.

## VIL-18 Machine test discovery
PASS if `qa/preflight/tests/test_visual_identity_lock_contract.py` is discovered by Developer Preflight and covers at least:
1. PC Visual Master required;
2. complete valid comparator receipts pass;
3. empty post-render receipts reject;
4. missing entity receipt rejects;
5. missing comparator class rejects;
6. unknown comparator class rejects;
7. unknown comparator status rejects;
8. unknown failure flag rejects;
9. applicable comparator cannot be `NA`;
10. PC identity drift rejects;
11. monster style-transform with identity preserved passes;
12. species/anatomy drift rejects;
13. recurring anchor drift rejects;
14. invented-equipment conflict rejects;
15. unknown ENTITY_CLASS rejects;
16. wrong MODERATE lock level rejects;
17. wrong LOOSE_WITH_SPECIES_GUARD lock level rejects;
18. continuity reference swap rejects;
19. Project Source slot delta stays zero.

## Acceptance

QA PASS approves only the visual-governance/tooling candidate. It does not activate new Runtime logic, mutate Campaign Canon, modify Recovery, create a Project Source, change any Gate verdict or authorize visual-to-canon writeback.
