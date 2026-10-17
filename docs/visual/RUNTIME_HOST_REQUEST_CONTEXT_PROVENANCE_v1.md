# Runtime Host Request Context Provenance v1

STATUS: CANDIDATE_ONLY
RUNTIME_PROMOTION: NO
SQL_PRIMARY_CUTOVER: NO
GITHUB_CUTOVER: NOT_APPROVED

## Security objective

`REQUEST_ID` is a correlation/security binding, not a caller-selected string.
The exact transaction identity used by the Authority Broker and by Runtime grant
verification must originate in the trusted Runtime Host and must remain the same
identity across:

`HOST REQUEST CONTEXT -> BROKER GRANT REQUEST -> SIGNED GRANT -> RUNTIME AUTHORITY BINDING`

## Host request-context authority

Before accepting untrusted request traffic, the trusted Runtime Host receives a
separate high-entropy HMAC key through a supervisor-inherited one-shot descriptor.
`runtime.runtime_host_request_context` bootstraps that authority exactly once.
There is no path/PEM/config/request argument and no reset/replace API.

### Bootstrap descriptor ownership

The bootstrap call takes ownership of the exact inherited descriptor. For every
valid descriptor accepted by the API, the Runtime Host closes that original FD
on success and on all bootstrap failure paths, including a rejected second
bootstrap. The implementation does not `dup()` the secret-bearing FD before
reading it.

The key-delivery descriptor must also be non-seekable. A seekable file, memfd or
temporary-file descriptor is rejected and closed. The supervisor is required to
pass a dedicated pipe/socket-style one-shot read capability and must not retain a
second process-local readable copy. This makes EOF/non-rewindability part of the
bootstrap contract instead of assuming that advancing a shared file offset is
sufficient secret erasure.

After successful bootstrap, the HMAC key exists only in private Host memory under
the process/supervisor trust boundary; the inherited descriptor capability has
been consumed.

The Host mints `RuntimeHostRequestContext` objects. The minting API accepts only
`SESSION_ID`, `ACTIVATION_ID`, and `SOURCE_REVISION`; it has **no REQUEST_ID
argument**. The Host generates a fresh REQUEST_ID and nonce, authenticates the
context with HMAC-SHA256, and records the exact proof as ACTIVE in Host memory.

Python object construction/private names are not the trust boundary. A manually
constructed context without the supervisor-rooted MAC fails closed.

### Process ownership and fork non-clonability

The request-context authority is bound to the exact Runtime Host PID that
completed bootstrap. Every public issue/verify/consume/cancel/proof operation
checks the current PID against that owner before using authority state.

The Runtime Host authority process is intentionally **no-fork**. The module
registers an `os.register_at_fork(after_in_child=...)` invalidator. In a forked
child the handler:

- zeroizes the child copy of the Host-context HMAC key;
- drops the child copy of the authority identity and owner PID;
- replaces ACTIVE/CONSUMED/CANCELLED registries with empty child-local maps;
- replaces the inherited lifecycle lock instead of acquiring a potentially
  parent-owned lock;
- marks the child permanently fork-invalidated.

A forked child therefore cannot issue, verify, consume or cancel the parent's
Host request contexts and cannot bootstrap a replacement Host authority. The
parent keeps its original authority and lifecycle state unchanged. This prevents
one pre-fork ACTIVE identity from creating split-brain terminal transitions.

This is a process-capability boundary, not merely a probabilistic REQUEST_ID
property. The child is rejected even if it possesses an exact copied Python
`RuntimeHostRequestContext` object.

### Transaction lifecycle and terminal tombstones

A Host request identity has one ACTIVE state and exactly two terminal states:

`ACTIVE -> CONSUMED`

`ACTIVE -> CANCELLED`

Both transitions are lock-protected lifecycle operations. The Host first verifies
the authenticated context proof, then while holding the lifecycle lock it checks
the exact registered ACTIVE proof and moves the identity into exactly one terminal
registry. A concurrent consume/cancel race can therefore produce only one winner;
the loser observes `NOT_ACTIVE` after the first terminal transition.

CONSUMED and CANCELLED identities remain tombstoned for the lifetime of the Host
process. Issuance rejects collisions against ACTIVE, CONSUMED and CANCELLED
registries. Cancellation is therefore a revocation event, not deletion of
security history: a request identity that reached CANCELLED can never become
ACTIVE again in that Host process even if the RNG would produce the same ID.

Terminal contexts remain cryptographically verifiable as retained proofs in the
owning Host process, but neither terminal state is accepted by any path requiring
an ACTIVE transaction. In particular, a previously issued Broker grant that
matches a later-cancelled Host context cannot authorize Runtime materialization.

## Host -> Broker

`RuntimeHostAuthorityBrokerClient` accepts only an ACTIVE authenticated
`RuntimeHostRequestContext`. It serializes the exact Host-owned REQUEST_ID,
SESSION_ID, ACTIVATION_ID and SOURCE_REVISION to the isolated Broker IPC channel.
A raw REQUEST_ID string is not a valid client input.

The Broker response must echo the same REQUEST_ID and the signed grant claims
must carry the same REQUEST_ID/session/activation/revision tuple before the
envelope can continue to Runtime materialization.

The Host-context HMAC/key is never sent to the Broker and never sent to the
visual/request worker.

### Broker IPC process ownership

A `RuntimeHostAuthorityBrokerClient` is bound to the PID that constructed it.
Every request checks that owner PID. Live Host-side Broker clients are tracked by
a weak registry and an at-fork child handler closes the cloned child-side socket
before child code can use the client. The PID guard remains an independent
fail-closed check even if socket invalidation were incomplete.

`from_inherited_fd()` takes ownership of the exact inherited Broker descriptor;
it does not retain a second `dup()` capability. The descriptor remains open only
for the owning Host client's lifetime. After `fork()`, the child-side copy is
closed while the parent's channel remains usable.

The supervisor must not separately retain another Host-process Broker descriptor
outside this ownership path. A deliberately duplicated capability created before
handoff is outside the client's ability to revoke and is a supervisor-boundary
violation, not an authority feature.

### Broker socket trust scope

The inherited AF_UNIX stream is a private transport capability, not the signing
authority. The current client requires a connected AF_UNIX stream but does not
claim that socket peer identity alone proves Broker authority. Security authority
for the returned grant comes from the Ed25519 signature verified later against
the independently bootstrap-pinned Runtime Host verification root, together with
the exact Host-context request/session/activation/source bindings. A malicious or
misbound socket peer that cannot produce a grant under that signing root cannot
authorize Runtime materialization.

Peer-credential pinning may be added as defense in depth, but it is not part of
the current authority proof and must not be described as one.

## Broker -> Runtime materialization

`materialize_runtime_authority_bindings()` accepts a
`RuntimeHostRequestContext`, not a request-id string. It requires:

- valid supervisor-rooted context MAC;
- context is still ACTIVE;
- exact context session == Runtime session;
- exact context activation == player-safe visual request activation;
- exact context source revision == Runtime source revision;
- exact signed grant REQUEST_ID == Host context REQUEST_ID;
- all existing checkpoint/AEL/PKP/leak/display authority bindings.

Only after the complete authority/checkpoint/player-safe binding succeeds is the
Host request context consumed. A consumed context cannot authorize a second
materialization transaction. A cancelled context cannot authorize any later
materialization, even if a matching signed grant already exists.

`RuntimeAuthorityBindings` retains the authenticated context for durable
in-process verification. Its binding digest commits the REQUEST_ID, Host context
authority ID and Host context proof digest. Later Runtime verification rechecks
the context MAC/provenance and the broker-signed grant. A forked child cannot use
that durable verification path because Host-context authority verification fails
closed before the retained proof can authorize anything.

## Fail-closed adversarial requirements

The candidate must reject all of the following:

- raw caller-selected REQUEST_ID supplied to production materialization;
- manually constructed context with a forged/invalid MAC;
- valid signed grant A applied to Host transaction context B while every other
  session/activation/source/checkpoint/AEL/PKP/display binding is identical;
- a consumed Host transaction context reused for a second materialization;
- a cancelled Host transaction context used with a matching previously signed grant;
- a cancelled REQUEST_ID re-issued after forced RNG collision/replay;
- a second cancel of the same terminal identity;
- a concurrent cancel/consume race yielding neither terminal state or both;
- post-materialization tamper of the retained Host context proof;
- Broker response REQUEST_ID different from the actual Host context;
- caller-selected request-id string supplied to the canonical Host Broker client;
- successful bootstrap leaving the original inherited secret FD usable;
- failed bootstrap leaving the original inherited secret FD usable;
- seekable bootstrap backing that can be rewound/re-read after bootstrap;
- rejected second bootstrap leaving its newly supplied descriptor open;
- forked child issue/verify/consume/cancel of a parent Host context;
- forked child re-bootstrap of Host request-context authority;
- forked child use of an inherited Host-side Broker client/socket;
- a pre-fork ACTIVE context reaching a terminal state independently in both
  parent and child.

These checks are additive to the existing broker signing-root, checkpoint,
player-safe, display-ledger, SQL-shadow and no-silent-fallback barriers.
