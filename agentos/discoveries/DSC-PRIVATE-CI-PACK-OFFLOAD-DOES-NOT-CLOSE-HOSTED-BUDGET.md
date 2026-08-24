---
key: PRIVATE-CI-PACK-OFFLOAD-DOES-NOT-CLOSE-HOSTED-BUDGET
claim: >
  Macro's first safe trusted-CI cutover cannot make the repository private-ready by
  moving execution packs alone. In the 2026-08-23/24 measurement, removing hosted pack
  execution and modeling PR #6286's planner at one rounded minute still leaves about
  102,000 raw rounded hosted job-minutes per 30 days: roughly 25,600 CI controls, 4,000
  fences and 72,700 other hosted workflows. That is more than twice the 50,000-minute
  GitHub Enterprise Cloud allowance before unknown organization-wide consumers or any
  billing adjustment.
falsifier: >
  After #6286 is Sol-accepted, PC 3+1 capacity is accepted and the trusted pack route is
  naturally production-proven, obtain the authoritative organization Actions ledger plus
  at least seven representative natural days of job/queue telemetry. This discovery is
  falsified if the full projected private-repository allowance use, including other
  organization consumers and platform billing treatment, has meaningful headroom below
  50,000 minutes/month without another optimization or trusted execution lane.
so_what: >
  Treat pack migration as one independently useful execution-plane capability, not the
  private-cutover finish line. Preserve hosted planner/gate/fences/authority/merge control
  and fork/untrusted independence in that first wave; then measure cancellation/execution
  amplification and move one further expensive trusted lane at a time. Do not recruit the
  M4 fleet until these post-optimization receipts still show a quantified capacity or queue
  failure.
kind: constraint
verified_at: 2026-08-24
verified_by: >
  Latest 100 completed ci.yml runs: 19.5125 hours, 1,182 hosted jobs and 10,854
  per-job-rounded minutes, including 896 packs / 9,782 minutes and 286 controls / 1,072
  minutes. Replacing 477 observed planner minutes with 98 one-minute planner jobs and
  removing packs yields about 25,600 monthly control minutes. Latest 100 fences runs add
  about 4,000 monthly minutes. Top-ten plus sampled long-tail non-CI hosted workflows yield
  about 72,700 monthly minutes. The organization billing API was unavailable to the current
  credential (moved endpoint plus admin:org requirement), so this is explicitly a run/job
  capacity projection rather than a billed-usage receipt.
scope:
  - macro
  - ci-merge-control-plane
  - runner-fleet-resilience
  - private-repository-cutover
confidence: verified
---

## Measurement boundary

The repository was PUBLIC during the observation, so standard hosted execution was free and
GitHub exposed duration rather than a post-private billed-minute ledger. Each hosted job was
rounded up independently to mirror the documented billing unit. The projection is useful as
a lower-bound decision gate: its failure to fit is decisive, while a later apparent fit still
requires the authoritative organization ledger and natural post-cutover telemetry.

The same CI sample had 92 pull-request events and eight dispatches, 100 distinct heads, only
11 distinct GitHub-associated PR identities, 28 cancelled runs, 67 successes and five
failures. This makes candidate/execution amplification a first-class capacity dimension;
planning from PR count alone understates the work admitted to the scheduler.

## Architectural boundary

This discovery does not authorize moving the hosted trust/control plane merely because it is
expensive. The first trusted executor remains main-defined and runner-group-restricted; PR code
supplies bounded identities only. Any later hosted reduction is its own measured vertical wave
with exact policy declaration, semantic-proof preservation, natural production proof and
route-only rollback.
