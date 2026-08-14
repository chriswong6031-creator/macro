---
key: CANCELLED-DAILY-RUN-CAN-STILL-DELIVER-PROPHET
claim: >
  daily.yml commits Prophet artifacts mid-job via the dedicated prophet_checkpoint step
  (allowlisted paths, rebase-retry push, then R2 publish), hours before the run's tail
  jobs finish. A daily run whose final conclusion is `cancelled` or `failure` can
  therefore have fully delivered Prophet — and conversely a run that concludes without
  red can have delivered nothing for the session. Run conclusions carry near-zero
  information about Prophet delivery.
falsifier: >
  The prophet_checkpoint step (currently .github/workflows/daily.yml:2608-2830, gated
  on prophet_nightly success) being moved after the tail jobs or folded into the
  job-final commit step, so that delivery and run conclusion become coupled.
so_what: >
  Never diagnose a Prophet outage from `gh run list` conclusions, and never treat a
  cancelled nightly as "picks lost" (or a concluded one as "picks delivered") without
  reading the artifact. Triage and watchdogs must read source_asof + recorded_at
  cohorts (see DSC:PROPHET-ASOF-IS-WALL-CLOCK). Recovery dispatch decisions keyed on
  conclusions alone either re-bake a night that already delivered (wasting the render
  budget) or skip a night that silently delivered nothing.
kind: landmine
verified_at: 2026-08-14
verified_by: >
  gh run view 31649984834 --json conclusion,jobs (cancelled 06:32:22Z mid
  tech_lab_offrender) vs git show f9140631d37 (its 03:28:16Z checkpoint: asof
  08-10→08-12, 25 plans recorded_at=2026-08-12); gh run view 31671422158 --json
  conclusion,jobs (failure, disk-full annotations) vs git show a47caf6a0ad (its
  12:38:26Z checkpoint: asof→08-13, zero 08-13 plans). Checkpoint-early design:
  .github/workflows/daily.yml:2608-2830 (step prophet_checkpoint), :2205-2208.
scope: [macro]
confidence: verified
---

## Detail

The checkpoint-early design is deliberate (daily.yml:2205-2208): Prophet delivery is
protected from tail-job failures. The corollary — conclusions decouple from delivery in
BOTH directions — is what every triage session in the 2026-08-11/13 outage rediscovered
independently. The 08-12 overnight thrash (ten dispatches, six killed) was fought over
runs whose Prophet payload status nobody read from the artifact.
