---
key: CAP-S1-SOURCE-ABSENT-W3A-COMPOSITION-REQUIRED
claim: >
  At protected Mastermind 21a721427743fdae6d513eeb0f993ebd1c327a81,
  CAP-S1 has no source implementation or GitHub carrier, while protected W3A
  already owns accepted semantics in its shared Operator Harness and Codex
  adapter paths and the current comparator still permits a duplicate same-name
  observation to be hidden by one matching row.
falsifier: >
  Re-read current protected Mastermind and its open/merged PR census, run
  `git -C Mastermind cat-file -e
  <protected>:control_plane/executive_capability_packages.py`, inspect
  `classify_observed_capabilities` in
  `control_plane/operator_harness_contract.py`, and inspect the latest commits
  for `control_plane/operator_harness_contract.py` and
  `control_plane/codex_operator_adapter.py`. This discovery is false when a
  protected CAP-S1 implementation exists, the exact-one comparator behavior is
  already present, or W3A no longer supplies the accepted shared-seam law.
so_what: >
  A future CAP-S1 receiver must begin from current protected source, preserve
  W3A OperationId/effect, epoch/generation, Wake and ordinary text-turn
  behavior, add the structured Skill path only as a closed V4-canary extension,
  and repair the comparator to exactly one observed identity per required name;
  it must not replay the older plan onto the shared files or revive historical
  native attempts.
kind: architecture
verified_at: 2026-09-01
verified_by: >
  Mastermind protected branch read at
  21a721427743fdae6d513eeb0f993ebd1c327a81; PR #325 merge
  484fb1d5b3660d69709767421c63aaa2fafb587a; compare from that merge to
  protected master; current reads of
  control_plane/operator_harness_contract.py and
  control_plane/codex_operator_adapter.py; W3A merge
  fc407e1638a26932c8615c98c7732d7f3202b3b1; current open-PR changed-path
  census; PR #325 reconciliation comment 5502570222.
scope:
  - WS:SOL-CAPABILITY-FABRIC
  - mastermind:control_plane/executive_capability_packages.py
  - mastermind:control_plane/operator_harness_contract.py
  - mastermind:control_plane/codex_operator_adapter.py
confidence: verified
---

# Evidence

SCF-PKG0 is protected source law in Mastermind PR #325. Current protected
Mastermind still returns no file at
`control_plane/executive_capability_packages.py`, and the current branch/PR
census contains no CAP-S1 implementation carrier.

The protected movement after SCF-PKG0 is not an active-writer collision.
W3A merge `fc407e1638a26932c8615c98c7732d7f3202b3b1` already changed the two
shared paths and established accepted current-writer Wake and operation
semantics. Those semantics must survive the later CAP-S1 vertical.

The current capability classifier groups observations by `(kind, name)` but
uses `any(...)` to determine whether the required identity is proven. One
matching Skill identity can therefore satisfy the requirement while a second
same-name observation remains present. That is the exact duplicate-shadow
defect frozen by CAP-S1 source law.

# Consequence

CAP-S1 remains `NOT_BUILT / NOT_PROVEN / PRODUCTION_UNARMED`. The next lawful
step is receiver placement and current-source SCOPE_MAP, not native proof,
default-policy migration or a parser-only PR. Historical CAP-S1 preflight,
broker and provider child operations terminated while their source predecessor
was unprotected and are not reusable evidence.
