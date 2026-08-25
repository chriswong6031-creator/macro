---
key: PRIVATE-CI-HOSTED-MINUTES-REQUIRE-TWO-LEVER-CUTOVER
claim: >
  Moving Macro's ci-pack jobs to isolated self-hosted capacity is necessary but
  is not sufficient to make the repository private-ready under the 50,000-minute
  Enterprise allowance. The latest three complete billing days project 744,890
  gross hosted Linux minutes per 30 days. On 2026-08-23, ci-pack jobs account for
  20,400 of 28,135 reported Macro Actions Linux minutes, but keeping every other
  hosted consumer and applying PR #6286's sub-minute ci-plan result still leaves
  a 6,878-minute daily counterfactual, or 206,340 minutes per 30 days.
falsifier: >
  A GitHub enhanced-billing report and complete job-timing census showing that
  packs moved to self-hosted capacity plus PR #6286's planner optimization, with
  no other hosted-route or trigger change, project total Macro Actions Linux use
  below 50,000 minutes per 30 days with explicit headroom. The claim also fails
  if GitHub documents or demonstrates that the usage item dated 2026-08-23 is not
  comparable to the same UTC day's completed job executions.
so_what: >
  Do not return a private-cutover acceptance packet on pack parity alone. Keep
  hosted authority, fences, merge control and untrusted jobs independent, but
  measure the whole hosted estate and remove execution amplification or needless
  hosted work until the billing projection has real headroom. Optimize existing
  GitHub Actions routes before considering M4 capacity; self-hosted capacity
  cannot repair hosted-minute amplification by itself.
kind: constraint
verified_at: 2026-08-24
verified_by: >
  gh api -H 'X-GitHub-Api-Version: 2026-03-10'
  'organizations/mastermindx-market-intelligence/settings/billing/usage?year=2026&month=8';
  bounded four-window GET census of
  repos/mastermindx-market-intelligence/macro/actions/runs?created=2026-08-23;
  GET repos/mastermindx-market-intelligence/macro/actions/workflows/ci.yml/runs
  plus GET repos/mastermindx-market-intelligence/macro/actions/runs/{id}/jobs
  for all 291 ci.yml runs; every executed job rounded up independently from
  started_at/completed_at in accordance with GitHub's per-job billing rule.
scope: [macro]
confidence: verified
---

## Billing trajectory

The enhanced-billing API reports gross `Actions Linux` minutes for the public
repository. Public usage is discounted today, but the gross quantity is the
prospective private-repository consumption envelope.

| Window | Gross minutes | Daily mean | 30-day projection |
|---|---:|---:|---:|
| 2026-08-09 through 2026-08-14 | 519,805 | 86,634.2 | 2,599,025 |
| 2026-08-15 through 2026-08-23 | 342,501 | 38,055.7 | 1,141,670 |
| latest three complete days, 2026-08-21 through 2026-08-23 | 74,489 | 24,829.7 | 744,890 |

The fleet has already reduced gross hosted use materially, but the most recent
complete window remains about 14.9 times the whole monthly allowance before
headroom.

## Exact 2026-08-23 CI census

The day contained 2,433 workflow runs across 53 workflows. `ci.yml` accounted
for 291 runs: 284 pull-request runs and seven main dispatches; 151 succeeded,
122 were cancelled and 18 failed. The pull-request population occupied 83 branch
names, leaving 208 runs beyond one run per branch. That is an amplification
observation, not a claim that every extra exact head was semantically redundant.

All 291 `ci.yml` runs were expanded through the jobs API. The census found 2,703
executed jobs and the following billed-equivalent minutes, rounding each job up
to a whole minute:

| CI component | Minutes |
|---|---:|
| `ci-pack-*` | 20,400 |
| `ci-plan` | 1,148 |
| `contract-delta` | 1,275 |
| `ci-gate` | 279 |
| **CI total** | **23,102** |

Cancelled CI runs consumed 3,590 billed-equivalent minutes. The organization
billing item for Macro on the same date is 28,135 Actions Linux minutes, leaving
5,033 minutes outside `ci.yml` in the comparison.

Moving all packs alone leaves 2,702 hosted CI minutes that day. Replacing
the observed 1,148 planner minutes with one billed minute for each of the 291
runs, consistent with PR #6286's three 40-48 second exact-head proofs, leaves
1,845 hosted CI minutes. Holding the 5,033-minute non-CI remainder constant gives
the 6,878-minute/day, 206,340-minute/month feasibility bound in the claim.

## Named non-CI pressure

The same-day workflow-run census found substantial hosted execution outside
`ci.yml`, including 784 `merge-on-green` runs, 369 `ci-authority` runs, 353
`fences` runs and 38 `integration-baseline` runs. Bounded job samples show the
first three normally cost one hosted minute per executed run; the exact
integration-baseline population cost 490 billed-equivalent minutes. These are
not instructions to weaken or self-host the trust plane. They are proof that the
post-cutover measurement must cover the whole hosted estate, not merely packs.

## Acceptance consequence

Private readiness requires two measured levers:

1. move the expensive trusted pack execution behind the existing main-defined
   workflow and runner-group boundary after PC acceptance; and
2. reduce hosted execution amplification and other avoidable hosted work while
   leaving the protected control and untrusted lanes independent.

The post-cutover packet must use the enhanced-billing API again and state both
the projected monthly quantity and its headroom below 50,000. A proposed 40,000
minute operating target would leave 20 percent headroom, but that number is a
Sol acceptance choice, not authority granted by this discovery.
