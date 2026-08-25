---
key: CI-EXECUTION-PROFILE-V2
question: >
  Can the semantic job-identity contract keep hashing the historical string
  "ci-pack/ubuntu-latest/python-3.12/node-20/v1" once self-hosted execution
  becomes a production CI route, and if not, how is runtime identity preserved
  without falsifying the executor?
answer: >
  No. The v1 string falsely names ubuntu-latest for any self-hosted Linux
  executor and floats the Python patch level production actually pins. It is
  replaced by one reviewed portable Linux execution profile v2 —
  "ci-pack/linux-x86_64/python-3.12.13/node-20/v2" — which describes logical
  execution invariants rather than a hosting brand, and is runtime-attested
  in scripts/run_ci_pack.py before any semantic execution: OS family Linux,
  machine x86_64, Python exactly 3.12.13, Node major exactly 20, and (when an
  authoritative plan is consumed) checkout HEAD equal to the plan's
  tested_tree_sha. Attestation runs on the --execute path whenever a plan is
  consumed (--plan-json) or a semantic fragment is emitted
  (--emit-semantic-fragment); it fails closed before any legacy job runs.
  There is no environment or CLI bypass; unit tests monkeypatch the in-process
  function.
rationale: >
  Sol's architecture freeze on issue #6351 (2026-08-24T06:21:57Z) rules the
  old string "cannot remain unchanged once self-hosted execution becomes a
  production route" and forbids both silent retention and deleting runtime
  identity from the digest. A truthful shared logical contract that hosted
  fallback and ci-linux both actually satisfy is the narrower of the two
  options Sol offered, and it preserves the existing digest architecture: the
  contract string still enters every semantic job execution digest, so a
  runtime that cannot satisfy the frozen profile changes identity rather than
  silently minting equal evidence. This is a deliberate semantic-contract
  version change: pre-change evidence and post-change evidence are
  intentionally non-comparable at digest level, and hosted-oracle parity
  (same logical plans/outcomes on the same candidate under the new profile)
  must be demonstrated before the profile is used for self-hosted promotion.
alternatives:
  - option: Keep "ubuntu-latest" in the string and ignore the mismatch
    why_not: >
      Production self-hosted packs would emit evidence that falsely claims a
      hosted runtime — explicitly forbidden by the #6351 commission ("A
      production self-hosted pack may not emit evidence that falsely claims
      ubuntu-latest").
  - option: Make execution-route identity an explicit plan/evidence field
    why_not: >
      Sol's other admitted route, but it widens the plan/evidence schema and
      forces every consumer (ci-gate, semantic proof, merge control) to learn
      route semantics. The portable-profile route keeps the schema unchanged
      and the authority surface untouched.
  - option: Drop runtime identity from the digest entirely
    why_not: >
      Explicitly forbidden — it would let any runtime mint identity-equal
      evidence, erasing the very invariant the contract string exists to pin.
evidence:
  - "Issue #6351, Sol architecture freeze comment 2026-08-24T06:21:57Z, §4 Runtime execution-profile migration"
  - "Issue #6351, Sol live-incident amendment 2026-08-25T19:44Z (materialization semantics as acceptance surface)"
  - "scripts/run_ci_pack.py RUNNER_CONTRACT v1 at merged main fafe8d7ee775f8b60a0229c085fb7aee6d4349e7"
  - "Production ci.yml pins python-version 3.12.13 (toolcache 3.12.14 fingerprint incident, ci.yml ~4393-4409)"
affects: ["WS:CI-MERGE-CONTROL-PLANE", "WS:RUNNER-FLEET-RESILIENCE", "scripts/run_ci_pack.py", ".github/workflows/selfhosted-ci-canary.yml"]
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-24
---

## Grounds

Sol froze the bridge design in the #6351 carrier; this record durably captures the
executed choice and its non-comparability consequence. The v2 change deliberately
invalidates digest-level comparison against v1-era evidence; any parity claim across
the boundary must be logical (plans/outcomes), never digest equality.

## What would reopen this

A PC/WSL runtime that cannot satisfy the frozen profile without weakening an
invariant (STOP FOR SOL per the freeze — broaden nothing ad hoc), or a later
reviewed profile v3 with its own oracle-parity proof.
