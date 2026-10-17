# DND Visual Identity Lock Contract v1

STATUS: CANDIDATE_TOOLING_CONTRACT_ONLY
SCOPE: tooling/visual-identity-lock-v1
ACTIVE_RUNTIME_MUTATION: FALSE
CAMPAIGN_CANON_MUTATION: FALSE
PROJECT_SOURCE_SLOT_DELTA: 0
SOURCE_BUDGET_POLICY: ENFORCED

## Purpose

Enforce the visual rules that already exist in the active Project Runtime and Visual Master Registry so that image generation preserves recurring-PC identity, preserves monster species/form identity under campaign-style transformation, and preserves continuity across repeated depictions.

This package creates zero new Project Source slots. If later promoted into live execution, its normative behavior must be consolidated into an existing Runtime/Visual owner bundle unless separately justified under SOURCE_BUDGET_POLICY_V1.

## Authority chain

For player-facing art:

`COMMITTED_CANON / SAVE -> PLAYER_KNOWLEDGE_PROJECTION -> SCENE_STATE -> ENTITY_VISUAL_STATE -> VISUAL_REFERENCE_MANIFEST -> GENERATION -> COMPLETE_IDENTITY_COMPARATOR_RECEIPTS -> DISPLAY`

Visual output is derived presentation only. `CANON -> VISUAL` is allowed; `VISUAL -> CANON` is forbidden.

## PC authority

For an approved recurring PC:

`PC_ID -> PC Sheet -> approved individual VIS_PC_* Visual Master -> committed runtime-visible state -> scene render`

The individual Visual Master owns stable face/body/silhouette/persistent visible identity. Committed Runtime/Save owns current equipment, wounds, dirt, active effects, transformations and other time-dependent visible state. Group art, new scene art or a comic panel never replaces the individual PC Visual Master unless the player explicitly approves the normal visual-master update flow.

## Monster authority

Official Monster Manual/adventure art is an **identity authority, not a style authority**.

Campaign restyling may change realism, materials, lighting, grime, scars, horror intensity and other non-mechanical presentation while preserving species/form identity. Locked features include species silhouette, head/face structure or number of heads, limb/anatomy plan, characteristic proportions, iconic visible organs/features, current form, and unique/adventure variant traits.

Style transformation MUST NOT become species redesign.

## Identity class enum and lock levels

The only accepted `ENTITY_CLASS` values and exact lock levels are:

- `PC` -> `VERY_STRICT`
- `NAMED_RECURRING_NPC` -> `STRICT`
- `NAMED_RECURRING_MONSTER` -> `STRICT`
- `UNIQUE_BOSS` -> `STRICT`
- `STANDARD_MONSTER_SPECIES` -> `MODERATE`
- `BACKGROUND_CROWD` -> `LOOSE_WITH_SPECIES_GUARD`
- `GENERIC_MOB` -> `LOOSE_WITH_SPECIES_GUARD`

Unknown `ENTITY_CLASS` is a hard fail. A known class with the wrong `IDENTITY_LOCK_LEVEL` is a hard fail. No class may bypass visual policy by using an unrecognized label.

### PC — VERY_STRICT

Requires the individual approved Visual Master, stable face/hair/eyes/persistent traits, stable body silhouette/relative build, defining gear silhouette when visible, and no generic class substitute. Material identity drift is a hard visual failure.

### Named recurring NPC/monster/boss — STRICT

Requires species/variant authority where applicable and stable instance identity after an approved campaign anchor exists. Approved distinguishing scars, color pattern, heads/horns/facial structure, signature equipment and other recurring features remain stable unless canonically changed.

### Standard monster species — MODERATE

Requires species/form identity and iconic anatomy. Campaign style transformation and non-recurring individual variation are allowed.

### Background crowd / generic mob — LOOSE_WITH_SPECIES_GUARD

Individual faces/equipment may vary within canonical possibility, but visible species/form identity may not drift.

## Campaign Visual Anchor

For named recurring NPC/monster/unique creatures:

`OFFICIAL_SPECIES_OR_VARIANT_REFERENCE -> CAMPAIGN_STYLE_TRANSFORMATION -> APPROVED_INSTANCE_RENDER -> CAMPAIGN_VISUAL_ANCHOR`

An approved anchor becomes the recurring instance reference in addition to, not instead of, official species/form authority. It may preserve non-mechanical instance details such as scars, coloration, clothing, grime, hairstyle or armor decoration already established.

It MUST NOT change statistics, equipment ownership, current form, hidden information, official species/anatomy identity, or become Campaign Canon merely by existing as art.

## ENTITY_VISUAL_STATE

Before generation, derive a non-authoritative `ENTITY_VISUAL_STATE` for every visible recurring entity from authoritative state. Minimum fields:

- `ENTITY_ID`
- `ENTITY_CLASS`
- `IDENTITY_AUTHORITY_ID`
- `CURRENT_FORM`
- `CURRENT_VISIBLE_EQUIPMENT`
- `CURRENT_VISIBLE_WOUNDS_OR_MARKS`
- `CURRENT_VISIBLE_EFFECTS`
- `CURRENT_VISIBLE_TRANSFORMATION`
- `CAMPAIGN_VISUAL_ANCHOR_ID` when applicable
- `SOURCE_STATE_EPOCH`
- `OBSERVER_SCOPE`

If derived visual state conflicts with an authoritative owner, the owner wins and visual state is rebuilt.

## Visual Reference Manifest

Immediately before generation, build one `VISUAL_REFERENCE_MANIFEST` from the frozen player-safe scene. Every entity record in `ENTITIES` is considered a visible entity required for display acceptance.

For each entity include at least:

- `ENTITY_ID`
- `ENTITY_CLASS`
- `CURRENT_FORM`
- `IDENTITY_LOCK_LEVEL`
- `REQUIRED_REFERENCE_AUTHORITY`
- `ACTUAL_REFERENCE_ASSET`
- `OFFICIAL_SPECIES_REFERENCE` when required/available
- `CAMPAIGN_VISUAL_ANCHOR_ID` when approved
- `CURRENT_VISIBLE_STATE_SOURCE`
- `HANDOFF_STATUS`

Generation is blocked if a required entity has missing/unresolved reference handoff.

## Scene continuity lock

A multi-panel comic, battle sequence, recap sequence or repeated shot group receives one `CONTINUITY_GROUP_ID`. Within a continuity group, recurring entities keep the same identity authority and campaign anchor, the same individual PC Visual Master is reused, and persistent scene facts do not reset unless an event changes them. An uncaused face/body/species/reference swap is a visual failure.

## Equipment and state guard

Image generation does not invent equipment for composition. Visible gear comes from committed Runtime/Save state or from a cosmetic variant explicitly permitted by the canonical item. It may not restore removed items from an old reference, infer current equipment from art, or change wounds/effects/forms for cinematic convenience.

## Post-render comparator receipt — fail closed

Before display, every entity in `VISUAL_REFERENCE_MANIFEST.ENTITIES` MUST provide one explicit post-render receipt. A render cannot pass merely because no failure observation was supplied.

Each entity receipt MUST contain all six comparator class keys:

- `PC_IDENTITY`
- `SPECIES_FORM_IDENTITY`
- `RECURRING_INSTANCE_IDENTITY`
- `VISIBLE_EQUIPMENT_STATE`
- `SCENE_CONTINUITY`
- `PLAYER_SAFE_CONTENT`

Every comparator status MUST be exactly one of `PASS`, `FAIL`, or `NA`.

Rules:
- missing entity receipt -> hard fail;
- missing comparator key -> hard fail, even when that comparator would be non-applicable;
- unknown comparator key -> hard fail;
- unknown comparator status -> hard fail;
- `FAIL` -> hard fail;
- `NA` is allowed only when that comparator is non-applicable to that entity/current scene;
- an applicable comparator reported as `NA` -> hard fail;
- `PLAYER_SAFE_CONTENT` is applicable to every entity;
- when `CONTINUITY_GROUP_ID` is present, `SCENE_CONTINUITY` is applicable to every entity;
- an explicit `FAILURE_FLAGS` list is required for every receipt;
- any unknown/typo failure flag -> hard fail;
- any known hard-failure flag -> hard fail;
- a receipt for an entity not present in the manifest -> hard fail.

Base comparator applicability:

- `PC`: `PC_IDENTITY`, `VISIBLE_EQUIPMENT_STATE`, `PLAYER_SAFE_CONTENT`
- `NAMED_RECURRING_NPC`: `RECURRING_INSTANCE_IDENTITY`, `VISIBLE_EQUIPMENT_STATE`, `PLAYER_SAFE_CONTENT`
- `NAMED_RECURRING_MONSTER` / `UNIQUE_BOSS`: `SPECIES_FORM_IDENTITY`, `RECURRING_INSTANCE_IDENTITY`, `VISIBLE_EQUIPMENT_STATE`, `PLAYER_SAFE_CONTENT`
- `STANDARD_MONSTER_SPECIES`: `SPECIES_FORM_IDENTITY`, `VISIBLE_EQUIPMENT_STATE`, `PLAYER_SAFE_CONTENT`
- `BACKGROUND_CROWD` / `GENERIC_MOB`: `SPECIES_FORM_IDENTITY`, `PLAYER_SAFE_CONTENT`

Known hard-failure flags include PC identity drift, species drift, wrong monster form, defining anatomy drift, unique-variant drift, recurring-anchor drift, invented visible equipment conflict, hidden DM information leak and panel identity swap.

On any hard failure:

`REJECT -> REGENERATE_FROM_SAME_FROZEN_SCENE_STATE_AND_SAME_REFERENCE_MANIFEST`

Aesthetics never override comparator failure.

## Knowledge firewall

All art consumes a materialized `PLAYER_KNOWLEDGE_PROJECTION` / player-safe scene package, never unrestricted hidden DM/adventure state. Hidden DM geometry, hidden creatures, future forms, source provenance, DM room IDs and sealed fields are excluded unless legitimately player-known or explicitly requested in development/QA context.

## Source budget

This package uses **zero new Project Source slots**. Artifacts remain GitHub/tooling/QA artifacts. Live activation should extend or replace an existing Visual/Runtime owner bundle by default.

## Activation barrier

This package is not an active Runtime patch. It MUST NOT mutate Campaign Canon, change the active Runtime bundle, reopen Gates A-E, claim Gate F, modify Recovery PR #7, promote generated art into gameplay authority, or consume a new Project Source slot.

Live implementation/promotion requires a separate reviewed activation change after QA PASS.
