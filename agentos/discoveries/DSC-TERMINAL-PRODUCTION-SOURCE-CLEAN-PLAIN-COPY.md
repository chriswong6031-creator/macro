---
key: TERMINAL-PRODUCTION-SOURCE-CLEAN-PLAIN-COPY
claim: >
  At the accepted 2026-08-30 Wave-0 observation, Terminal production served from the plain-copy
  tree `/opt/terminal/terminal`, its canonical Git checkout `/opt/terminal/.gitsrc` was pristine at
  accepted commit `b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea`, and the read-only census found
  zero unexplained implementation files or tracked source differences.
falsifier: >
  A fresh secret-safe production census that identifies a different Terminal service working
  directory, a dirty or differently rooted canonical checkout, a tracked Git-to-live mismatch,
  an ignored/untracked implementation candidate, or a deployment marker that does not bind the
  serving tree to the recorded accepted commit would disprove this claim for the new observation.
so_what: >
  Future sessions may stop treating current production-only implementation as unknown and may
  design the exact-SHA deploy/preflight from this topology, but they must rerun the source audit
  immediately before any destructive convergence and must not infer served-build provenance,
  runtime-data freshness or rollback correctness from this one clean census.
kind: runtime
verified_at: 2026-08-30
verified_by: >
  Terminal issue #483 Wave-0 acceptance receipt, backed by the read-only production archaeology
  RESULT on operation terminal-github-canonical-deploy-20260829-sol-001.
scope: [terminal, terminal-charting]
confidence: verified
---

## Boundaries of the finding

This discovery is an observation, not a permanent invariant and not deployment authorization.
It establishes the actual source topology and absence of unexplained implementation at one point in
time. It does not establish that:

- `.next` was reproducibly built from the marker SHA;
- every runtime-code directory was deployed atomically with the application;
- mutable `public/data` or Macro upstream artifacts were current;
- a failed health check restored the previous deployment marker and receipt;
- repository settings prevent an administrator/API bypass;
- future host state remains clean without a fresh audit.

The deployment program therefore carries the discovery as the W0 baseline and revalidates it through
the PR #484 source-audit capability before each later release mutation.
