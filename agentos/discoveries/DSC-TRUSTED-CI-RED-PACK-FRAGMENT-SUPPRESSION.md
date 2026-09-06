---
key: TRUSTED-CI-RED-PACK-FRAGMENT-SUPPRESSION
claim: >
  A main-owned trusted CI pack can complete red after successfully emitting its raw
  semantic fragment, while the caller's aggregate trusted-ci job also concludes red.
  The P3B caller previously gated the entire hosted ci-pack relay matrix on aggregate
  trusted-ci success, so one genuine pack failure suppressed every relay artifact and
  made ci-gate report fleet-wide missing evidence instead of the actual semantic red.
falsifier: >
  Falsified if .github/workflows/ci.yml preserves a completed red trusted pack's
  trusted-ci-fragment-N into the corresponding ci-semantic-pack artifact for ci-gate,
  and tests/test_trusted_ci_production_route.py plus #6628 prove that behavior without
  adding a second semantic gate or weakening fragment-to-plan binding.
so_what: >
  Trusted execution may remain diagnostically red, but its completed raw evidence must
  still cross the existing lightweight relay into ci-gate. Missing evidence and negative
  evidence are different states; collapsing them blinds Sol and can turn one candidate
  defect into a false fleet-infrastructure incident.
kind: architecture
verified_at: 2026-08-29
verified_by: >
  #6628 ; .github/workflows/ci.yml ; tests/test_trusted_ci_production_route.py ;
  https://github.com/mastermindx-market-intelligence/macro/actions/runs/33167775126 ;
  trusted pack 10 job 98838430203 ; ci-gate job 98896302514
scope:
  - macro
confidence: verified
---

## Boundary

This discovery does not authorize a second CI scheduler, queue, retry plane, evidence store,
runner registry, merge controller or semantic verdict. The accepted repair keeps `ci-gate` as
the sole semantic aggregate, preserves the existing trusted executor and fork boundary, and
changes only whether already-produced trusted evidence is allowed to reach that aggregate when
the reusable workflow is red.
