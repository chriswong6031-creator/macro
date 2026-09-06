---
key: SCF-DIGEST-ONLY-PREPARED-ACTION-REQUIRES-HIDDEN-STORE
claim: >
  A two-turn action protocol that asks commit to accept only a digest while also
  forbidding a prepared-action lookup store is internally unsatisfiable. A
  digest proves equality but cannot reconstruct the target, normalized effect,
  source preconditions, principal binding and expiry. Implementing that shape
  would require hidden state, caller resubmission of privileged fields or an
  unauthenticated bearer digest.
falsifier: >
  Run `git -C Mastermind show
  98bc7a71dcd70947c7a18eb5af7493a2f62a2571:docs/superpowers/specs/2026-08-30-sol-capability-fabric-prepared-action-token-correction.md`
  and produce an implementation that reconstructs and authenticates every
  load-bearing prepared field from a bare digest with no lookup state and no
  caller resubmission. If that is possible under the protected constraints,
  this discovery is false.
so_what: >
  Future W2/A3 families must use an owner-specific authenticated,
  self-contained, expiring `prepared_token`, then independently reauthenticate
  the caller and revalidate current organizational/action-target authority,
  source and prior effects. There is no durable prepared-action store, shared
  token service, global action router, queue, lock or lifecycle.
kind: architecture
verified_at: 2026-08-30
verified_by: >
  Mastermind PR #283; run `git -C Mastermind show
  98bc7a71dcd70947c7a18eb5af7493a2f62a2571:docs/superpowers/specs/2026-08-30-sol-capability-fabric-prepared-action-token-correction.md`.
scope:
  - WS:SOL-CAPABILITY-FABRIC
confidence: verified
---

# Evidence

The original SCF-F0 wording paired:

```text
commit_prepared_action(prepared_digest)
no durable prepared-action store
```

The digest did not contain the request fields needed for commit-time validation.
Adversarial review therefore forced a narrow correction before architecture
protection.

The protected contract now returns an **authenticated self-contained expiring
token** from the owner app. The server validates integrity and expiry, binds the
token to one app/schema/policy generation, principal, operation, action family,
target, normalized secret-free effect and source preconditions, and rechecks
current authority before one owner-native request.

# Consequence

The prepared token is not organizational authority and is not a transferable
company-wide bearer grant. Each app keeps its own key custody and action family.
Owner-native idempotency and `reconcile_effect(...)` preserve replay safety.
There is **no durable prepared-action store** or cross-owner dispatch service.
