---
key: CAP-S1-SOURCE-ABSENT-W3A-COMPOSITION-REQUIRED
claim: >
  At protected Mastermind 21a721427743fdae6d513eeb0f993ebd1c327a81,
  CAP-S1 had no source implementation or GitHub carrier, while protected W3A
  already owned accepted semantics in its shared Operator Harness and Codex
  adapter paths and the comparator still permitted a duplicate same-name
  observation to be hidden by one matching row.
falsifier: >
  Re-read the pinned protected Mastermind and its then-current PR census, run
  `git -C Mastermind cat-file -e
  21a721427743fdae6d513eeb0f993ebd1c327a81:control_plane/executive_capability_packages.py`,
  inspect `classify_observed_capabilities` in
  `control_plane/operator_harness_contract.py`, and inspect the latest commits
  for the two W3A shared paths. This historical discovery is false if CAP-S1
  source existed at that pin, the exact-one comparator was already present, or
  W3A did not own the accepted shared-seam law.
so_what: >
  Preserve this as the historical pickup boundary only. Current sessions must
  load DSC:CAP-S1-CURRENT-CARRIER-REQUIRES-SERIALIZED-RELEASE-CLOSURE and must
  not use the older source-absent state to create a replacement CAP-S1 carrier.
kind: architecture
verified_at: 2026-09-01
verified_by: >
  Mastermind protected branch read at
  21a721427743fdae6d513eeb0f993ebd1c327a81; PR #325 merge
  484fb1d5b3660d69709767421c63aaa2fafb587a; current reads of
  control_plane/operator_harness_contract.py and
  control_plane/codex_operator_adapter.py; W3A merge
  fc407e1638a26932c8615c98c7732d7f3202b3b1; PR #325 comment 5502570222.
scope:
  - WS:SOL-CAPABILITY-FABRIC
  - mastermind:control_plane/executive_capability_packages.py
  - mastermind:control_plane/operator_harness_contract.py
  - mastermind:control_plane/codex_operator_adapter.py
confidence: verified
superseded_by: DSC:CAP-S1-CURRENT-CARRIER-REQUIRES-SERIALIZED-RELEASE-CLOSURE
---

# Historical evidence

At the verified pin, SCF-PKG0 was protected source law, the package
implementation file did not exist, and no CAP-S1 implementation branch or PR
was present. W3A had already changed the two shared paths and established
accepted OperationId, epoch/generation, current-writer Wake and attention
semantics that a later CAP-S1 implementation had to preserve.

The comparator used `any(...)` over same-name observations, so one exact match
could satisfy a requirement while a second same-name observation remained.
That defect was subsequently incorporated into the CAP-S1 implementation work.

# Supersession

CAP-S1 now has one canonical started carrier, Mastermind PR #350. The current
question is no longer whether source exists; it is whether that same carrier can
close its security, release-closure, real-canary and cleanup obligations without
racing the Capacity and Control Room owners. The superseding discovery records
that current state.
