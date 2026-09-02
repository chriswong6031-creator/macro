---
key: CAP-S1-CURRENT-CARRIER-REQUIRES-SERIALIZED-RELEASE-CLOSURE
claim: >
  CAP-S1 now has one canonical started implementation carrier, Mastermind PR
  #350, whose source spans the package verifier, V4 registry, exact-one
  comparator, Codex Skill projection and synthetic canary; its remaining
  release closure is serialized behind Capacity C1 PR #329 and Control Room PR
  #326, while the real four-turn Codex canary and cleanup remain unaccepted.
falsifier: >
  Re-read protected Mastermind, PRs #350, #329 and #326, their current heads,
  changed paths, reviews and hosted checks; inspect
  control_plane/executive_capability_packages.py,
  control_plane/executive_agent_capabilities.py,
  control_plane/operator_harness_contract.py and
  control_plane/codex_operator_adapter.py. This discovery is false when #350 is
  no longer the canonical carrier, the shared closure no longer depends on
  #329/#326, or an accepted real four-turn provider proof plus complete cleanup
  exists on released source.
so_what: >
  Future Sol sessions must continue the existing #350 carrier with sticky Fable
  ownership, must not create a parser-only or replacement CAP-S1 PR, and must
  preserve the owner order #329 -> #326 -> #350 before any CAP-PROMOTE1 action.
  A green synthetic suite, merge or source install is not the real-provider
  acceptance test.
kind: architecture
verified_at: 2026-09-02
verified_by: >
  GitHub reads of Mastermind PR #350 head
  f4eaf1eac053b62af550e88293cc51b2c8ff3c77, PR #329 head
  c251acb49aef7e22d5268feb2894fbf701548b32, PR #326 head
  889805b2b4f44d5a6240f98f76b15b43b55b35be, exact changed-path and check
  census, and control_plane source reads on the #350 head.
scope:
  - WS:SOL-CAPABILITY-FABRIC
  - mastermind:pull/350
  - mastermind:pull/329
  - mastermind:pull/326
  - mastermind:control_plane/executive_capability_packages.py
  - mastermind:control_plane/executive_agent_capabilities.py
  - mastermind:control_plane/operator_harness_contract.py
  - mastermind:control_plane/codex_operator_adapter.py
confidence: verified
---

# Current source state

PR #350 is not the older source-absent CAP-S1 state. It contains a material
implementation across fifteen governed paths, including the package source
verifier, V4 capability registry and fixture, exact-name comparison changes,
Codex attempt-local Skill projection, protocol parsing, synthetic canary and
associated tests.

That progress remains `BUILT_NOT_PROVEN / PRODUCTION_UNARMED`. The current head
is red and behind protected master. Exact-head investigation identified both
hosted failures and additional security/provenance gaps:

- the Control Room remote install closure does not yet include the new package
  verifier dependency;
- first-census file identity is not retained strongly enough to prevent
  unlink/recreate inode reuse from escaping revalidation;
- a forged projection receipt can redirect the adapter toward another real
  tree unless the receipt is bound to adapter-held attempt state;
- post-start revalidation loses exact path, descriptor, binary and schema
  precision;
- Mode-B protocol support is still caller-asserted rather than derived from
  exact-binary schema/probe evidence;
- duplicate-key refusal must not echo attacker-controlled key text;
- source-origin, projection, cleanup and skills/changed race receipts are not
  yet complete;
- the real isolated four-Skill model journey and cleanup have not been accepted.

# Owner serialization

Two of the required closure paths are already owned by the active Control Room
carrier #326. That carrier is itself held on Capacity C1 #329. The lawful order
is therefore:

```text
#329 Capacity C1 repair and release
-> #326 Control Room current-base closure and release
-> #350 CAP-S1 closure, exact-head review and real canary
```

This order is a shared-path/owner constraint, not permission for a later wave to
absorb an earlier one. It creates no automatic merge or production START.

# Acceptance boundary

CAP-S1 becomes accepted only when exact protected source drives one fresh,
read-only Codex App Server process/thread through empty/add-four/clear-empty
Skill discovery, four path-bound governed Skill turns, source/list/schema
invalidation checks and complete process/thread/artifact/projection cleanup.
Provider output is behavior evidence only and cannot self-author source,
authority, success or cleanup. CAP-PROMOTE1 remains separate.
