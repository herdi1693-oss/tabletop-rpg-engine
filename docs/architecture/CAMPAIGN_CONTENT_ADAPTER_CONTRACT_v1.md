# Tabletop RPG Campaign Content Adapter Contract v1

STATUS: CANDIDATE_CONTRACT_ONLY
SCOPE: public-generic-campaign-content-adapter-v1
ACTIVE_RUNTIME_MUTATION: FALSE
CAMPAIGN_STATE_MUTATION: FALSE
PUBLIC_PROVIDER_IDENTITY: OPAQUE_ONLY
PRIVATE_TO_PUBLIC_REPOSITORY_FLOW: FORBIDDEN
PUBLIC_RESOLVED_CONTENT_PERSISTENCE: FORBIDDEN
PLAYER_FACING_UNPROJECTED_PRIVATE_PAYLOAD: FORBIDDEN
ORIGINAL_PRIVATE_DISPLAY_CONTENT_ALLOWED_AT_RUNTIME: TRUE

## Purpose

Define a public, campaign-neutral boundary between a reusable tabletop RPG engine and a separately owned private campaign-content provider.

The public engine owns generic identifiers, request/response shapes, validation rules and failure semantics. The private provider owns the mapping from those generic identifiers to private display names, narrative text, source-bound content, private assets and campaign-specific metadata.

This contract deliberately does not define any concrete campaign, setting, adventure, provider endpoint, repository identity, workspace identity or source package.

## Stable public identifiers

Every adapter-visible identifier MUST use the following grammar:

`ID_REGEX: ^[a-z][a-z0-9_]{1,31}:[a-z0-9][a-z0-9._-]{0,63}:[a-z0-9][a-z0-9._-]{0,127}$`

The three components are:

`kind:namespace:local_id`

Rules:
- `kind` is a generic engine category such as `campaign`, `location`, `entity`, `scene`, `item`, `rule`, `asset` or `text`;
- `namespace` is an opaque public-neutral package namespace and MUST NOT encode a private campaign title, source title, repository name or provider account identity;
- `local_id` is stable within the namespace and MUST NOT depend on a display name;
- identifiers are immutable once persisted in engine state;
- renaming private display content MUST NOT change its public identifier;
- two private bindings MUST NOT resolve the same `(namespace, local_id, binding_revision)` tuple to different semantic objects.

Generic examples:

`campaign:pkg01:campaign_001`

`location:pkg01:loc_0042`

`entity:pkg01:entity_0017`

## Public adapter request

A public engine request to the private provider MUST contain only generic routing and authorization context:

- `campaign_id`;
- `content_kind`;
- `content_id`;
- `binding_revision`;
- `observer_scope`;
- `knowledge_scope`;
- `locale` when localization is requested;
- `request_id` for idempotent tracing within the authorized runtime boundary.

The request MUST NOT require the public repository to know or persist original display names, narrative text, private source references, private asset paths, provider credentials, repository identities or infrastructure identities.

## Private provider response

The private provider MAY resolve an authorized request to a private content envelope containing fields such as:

- `resolved_id` equal to the requested generic identifier;
- `binding_revision`;
- `display_name`;
- `display_text` or structured narrative payload;
- private asset references;
- private rules/source references;
- provider-private metadata required by the authorized runtime.

Exact values of private fields are intentionally outside this public contract and outside the public repository.

A provider response is not automatically player-visible. Any player-facing use MUST pass the runtime's player-knowledge projection and leak-preoutput gate before output. The adapter MUST NOT create a bypass around observer scope, knowledge scope, secret-state handling or any equivalent runtime visibility boundary.

## One-way repository boundary

The allowed information flow is:

`PUBLIC_GENERIC_REQUEST -> PRIVATE_PROVIDER -> AUTHORIZED_PRIVATE_RUNTIME_PAYLOAD`

The following reverse flow is forbidden:

`RESOLVED_PRIVATE_PAYLOAD -> PUBLIC_REPOSITORY_OR_PUBLIC_BUILD_ARTIFACT`

Therefore:
- resolved private names or narrative MAY be used in the authorized game runtime;
- resolved private content MUST NOT be committed back into the public engine repository;
- public test fixtures MUST use synthetic generic values only;
- public logs, CI artifacts, crash fixtures and telemetry MUST NOT persist resolved private payloads;
- public code MUST NOT embed a private binding table;
- public code MUST NOT infer missing private content from identifier shape, neighboring records, cached text or source-specific assumptions.

## Binding ownership and versioning

The private provider owns the binding table.

A binding is identified by:

`(campaign_id, content_id, binding_revision)`

Required properties:
- `binding_revision` is explicit and immutable for a resolved request;
- a newer binding revision may change private display content while retaining stable generic IDs when semantic identity is unchanged;
- semantic replacement requires a new generic ID;
- the public engine MAY persist the generic ID and binding revision but MUST NOT persist the private resolved payload in public artifacts;
- provider identity and provider location remain runtime configuration, not source-code constants in the public repository.

## Fail-closed behavior

The adapter MUST fail closed with a structured non-content-bearing error when resolution cannot be trusted.

Required failure codes:

- `BINDING_NOT_FOUND`;
- `BINDING_AMBIGUOUS`;
- `BINDING_REVISION_MISMATCH`;
- `CONTENT_KIND_MISMATCH`;
- `SCOPE_DENIED`;
- `PROVIDER_UNAVAILABLE`;
- `PRIVATE_PAYLOAD_VALIDATION_FAILED`.

Failure handling MUST NOT:
- guess an original name;
- substitute neighboring private content;
- expose provider-private metadata in a player-facing error;
- downgrade observer or knowledge checks;
- write private payload fragments to a public artifact as diagnostics.

## Runtime isolation

This contract is a data-boundary contract, not a new authority owner.

It does not authorize:
- gameplay-state mutation by the content provider;
- topology mutation by display content;
- player-knowledge expansion;
- persistence-mode promotion;
- source-of-truth replacement;
- public repository mutation from private runtime data.

Private content resolution MAY enrich an already-authorized runtime operation with display/source material. It MUST NOT become an alternate Canon, transaction owner, topology owner or player-knowledge authority.

## Public implementation requirements

A conforming public implementation MUST:
- accept only syntactically valid generic IDs;
- keep provider identity outside source constants;
- pass `observer_scope` and `knowledge_scope` through the request boundary;
- bind every response to the requested `content_id` and `binding_revision`;
- reject ambiguous, stale, mismatched or unavailable bindings;
- ensure unprojected private payload is not directly rendered to a player;
- ensure resolved private payload is not persisted into public repository/build/test/telemetry artifacts;
- use synthetic generic fixtures in public tests.

## Compatibility rule

A private campaign binding is compatible with this contract only when it can satisfy the generic request/response and fail-closed rules without requiring any campaign-specific value to be committed into the public repository.

Public and private implementations may evolve independently, but compatibility MUST be explicit through an adapter contract version and a binding revision. Unknown versions fail closed.