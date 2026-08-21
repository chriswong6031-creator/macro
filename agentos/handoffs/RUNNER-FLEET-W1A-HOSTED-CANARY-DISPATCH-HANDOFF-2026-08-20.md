---
key: RUNNER-FLEET-W1A-HOSTED-CANARY-DISPATCH-HANDOFF-2026-08-20
program: project-active-build-control
workstream: RUNNER-FLEET-RESILIENCE
owner: ceo-sol
status: ready_for_operator
class: operator_handoff
reversible: true
---

# Runner Fleet W1-A — hosted merge-control canary dispatch handoff

**Date:** 2026-08-20  
**Program:** `WS:RUNNER-FLEET-RESILIENCE`  
**Wave:** W1-A post-merge production proof  
**Authority:** `DEC:RUNNER-FLEET-PHYSICAL-FAILURE-DOMAINS` → merged M0 PR #6094 → merged W1-A PR #6113  
**Operator:** bounded GitHub-CLI session only

## Observable mission

Dispatch `.github/workflows/merge-control-hosted-canary.yml` from `main` three times and return exact evidence proving GitHub-hosted capacity can satisfy the production merge controller's environment contract. One accepted run must overlap a genuinely busy M2 production/render job.

This handoff does **not** authorize changing the real `merge-on-green` route. W1-B remains blocked until Sol reviews every attempt and explicitly authorizes the route-only cutover.

## Why this matters

The current merge arbiter runs on `mac-builder-4`, a listener on the same physical M2 Ultra that carries production/render/operator I/O. The 2026-08-20 starvation incident proved that logical labels do not create physical isolation. The architecture therefore targets hosted merge-control, but requires current capacity/environment receipts because the dedicated-M2 route was created after a historical hosted saturation event.

## Authority / document precedence

1. `agentos/decisions/DEC-RUNNER-FLEET-PHYSICAL-FAILURE-DOMAINS.md`
2. `research/RUNNER_FLEET_RESILIENCE_ARCHITECTURE_FREEZE_2026-08-20.md`
3. `research/RUNNER_FLEET_RESILIENCE_M0_ADVERSARIAL_AMENDMENT_2026-08-20.md`
4. `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
5. `.github/workflows/merge-control-hosted-canary.yml` on `main`
6. this handoff

If a lower item conflicts with a higher item, stop and return the conflict to Sol.

## Verified current state

- M0 PR #6094 is merged as `9dcd4c24a547c11d1205b94da98ae0ff5b401b85`.
- W1-A PR #6113 is merged as `29d52200af45d2a8afe44e8bdf8a29aacc63809c`.
- #6113's final accepted PR surface was exactly four files: the hosted canary workflow, canonical canary tests, fast-fence bridge, and fleet workstream state.
- Exact-head pre-merge proof on `11b6195c73f65f505b26fcea2610e0b08e492a5c`: fences green including 57/57 fast-fence tests, planner green, contract-delta green, all 12 semantic packs green, and `ci-gate` green.
- Production `.github/workflows/merge-on-green.yml` still uses the self-hosted `merge-control` route; no production merge route changed in W1-A.
- The canary is dispatch-only, `contents: read`, main-pinned, GitHub-hosted, has no merge/admin token, and never executes the production sweeper.
- A trusted hosted attempt initializes `accepted:false` evidence before checkout and records `run_id`, `run_attempt`, `job_started_at_observed`, SHA, hosted runner/runtime identity, phase state, and contract-parity state.
- Canary artifact name is rerun-safe: `merge-control-hosted-canary-${run_id}-${run_attempt}`.
- ChatGPT's current GitHub connection cannot invoke `workflow_dispatch`; that is the only reason this bounded external operator action is required.

## Exact scope

Repository: `mastermindx-market-intelligence/macro`

Perform only:

1. prove #6113 is merged and capture the current `main` SHA for each dispatch;
2. dispatch the canary three times from `main`, sequentially rather than batch-firing;
3. preserve **all** attempts, including failed/rerun attempts;
4. capture workflow/job timestamps and hosted runner identities;
5. download the exact `run_id + run_attempt` canary artifact and validate its JSON receipt;
6. for one accepted attempt, capture timestamped overlap with a real M2 production/render job;
7. return the complete evidence package to Sol.

## Explicit non-goals

Do **not**:

- edit or merge any PR;
- change `.github/workflows/merge-on-green.yml`;
- run `scripts/merge_on_green.py`;
- add/remove `merge-control` or any runner label;
- alter M1/PC services;
- change `render.yml` defaults;
- restart a self-hosted runner;
- manufacture M2 load solely for this proof;
- create a scheduler, queue, registry, or second merge implementation;
- call W1 complete;
- start W1-B.

## Deterministic acceptance method

No statistical/model-generated decision is used. Acceptance is deterministic from GitHub Actions metadata plus the JSON receipt. `accepted:true` is necessary but **never sufficient** for pickup proof; pickup is adjudicated from Actions timestamps.

## Preconditions

```bash
set -euo pipefail
REPO="mastermindx-market-intelligence/macro"

gh auth status
gh pr view 6113 --repo "$REPO" \
  --json state,mergedAt,mergeCommit,headRefOid,url

gh api "repos/$REPO/contents/.github/workflows/merge-control-hosted-canary.yml?ref=main" \
  --jq '.sha'
```

Require:

- #6113 is merged;
- `main` contains the canary workflow;
- workflow remains `workflow_dispatch` only;
- workflow permission remains `contents: read`;
- trust-gate and hosted-environment remain `ubuntu-latest`;
- production `merge-on-green.yml` has not already been moved by another operator.

If any precondition fails, stop and return the observed state.

## Ordered execution sequence

Repeat for labels A, B and C. Do not fire the three runs simultaneously because the workflow has a non-cancelling concurrency group and pickup is measured per eligible job.

### 1. Capture the dispatch subject

```bash
MAIN_SHA=$(gh api "repos/$REPO/commits/main" --jq '.sha')
echo "MAIN_SHA=$MAIN_SHA"
```

### 2. Dispatch from trusted main

```bash
gh workflow run merge-control-hosted-canary.yml \
  --repo "$REPO" \
  --ref main
```

### 3. Resolve the exact run

```bash
gh run list --repo "$REPO" \
  --workflow merge-control-hosted-canary.yml \
  --branch main \
  --event workflow_dispatch \
  --limit 10 \
  --json databaseId,createdAt,startedAt,status,conclusion,headSha,url
```

Choose only the newly created run whose `headSha` equals the captured `MAIN_SHA`. Record `run_id`, raw timestamps, SHA and URL. Do not reuse an older green run.

### 4. Capture every attempt and both hosted jobs

For attempt 1, set `RUN_ATTEMPT=1`. If GitHub reruns the same run, increment/use the actual attempt reported by GitHub; never overwrite attempt-1 evidence.

```bash
RUN_ID=<exact-run-id>
RUN_ATTEMPT=<actual-attempt>

gh api "repos/$REPO/actions/runs/$RUN_ID/attempts/$RUN_ATTEMPT/jobs" \
  > "/tmp/w1a-$RUN_ID-$RUN_ATTEMPT-jobs.json"

jq '.jobs[] | {
  id,
  name,
  status,
  conclusion,
  started_at,
  completed_at,
  runner_name,
  runner_group_name,
  labels
}' "/tmp/w1a-$RUN_ID-$RUN_ATTEMPT-jobs.json"
```

Expected jobs:

- `trust-gate`
- `hosted-environment`

Both must conclude `success` for an accepted attempt and identify GitHub-hosted execution, not a self-hosted runner.

### 5. Compute the two pickup clocks

Trust-gate pickup:

```text
trust_gate.started_at - workflow_run.created_at
```

Hosted-environment pickup:

```text
hosted_environment.started_at - trust_gate.completed_at
```

The second clock deliberately does **not** use workflow `created_at`, because hosted-environment is dependency-blocked until trust-gate completes.

Require **both pickup latencies < 60 seconds** on every accepted attempt. Preserve raw timestamps and the exact arithmetic result; do not silently clamp negative/zero values caused by API timestamp rounding.

### 6. Require successful workflow conclusion

```bash
gh run view "$RUN_ID" --repo "$REPO" \
  --json status,conclusion,createdAt,startedAt,updatedAt,headSha,url
```

Require `conclusion == "success"`. A queued, in-progress, cancelled, skipped or neutral run is not a pass.

### 7. Download the rerun-safe receipt artifact

```bash
OUT="/tmp/w1a-$RUN_ID-$RUN_ATTEMPT"
rm -rf "$OUT"
mkdir -p "$OUT"

gh run download "$RUN_ID" --repo "$REPO" \
  -n "merge-control-hosted-canary-$RUN_ID-$RUN_ATTEMPT" \
  -D "$OUT"

cat "$OUT/merge-control-hosted-canary.json"
```

Require:

```text
schema == merge_control.hosted_environment_canary.v1
run_id == RUN_ID
run_attempt == RUN_ATTEMPT
sha == run.headSha
job_started_at_observed is non-null
phase1 == production_sparse_import_ok
phase2 == control_tests_ok
production_contract_parity == true
accepted == true
runner_os == Linux
```

Also preserve `runner_name`, `runner_arch`, `python`, and `platform`. Any run/attempt/SHA mismatch, null required identity, or missing artifact fails that attempt.

## Congested-window requirement

At least one of A/B/C must overlap naturally occurring M2 production/render execution. Do not manufacture a production workload solely for this proof.

Discover candidate active work:

```bash
gh run list --repo "$REPO" --status in_progress --limit 50 \
  --json databaseId,name,workflowName,createdAt,startedAt,headSha,url
```

For a candidate:

```bash
gh api "repos/$REPO/actions/runs/$CANDIDATE_RUN_ID/jobs" \
  --jq '.jobs[] | {id,name,status,started_at,completed_at,runner_name,labels}'
```

Accepted overlap evidence must include:

- concurrent workflow name;
- concurrent run ID;
- concurrent job ID/name;
- an M2 runner identity such as the currently registered `mac-builder-*` listener;
- concurrent job start/completion timestamps;
- canary job timestamps proving interval overlap.

A statement such as "the Mac was busy", fan noise, or a queued job with no runner assignment is not evidence.

## Failure states / stop conditions

Return the failed evidence and stop W1-A acceptance if any attempt has:

- non-main subject or trust-gate rejection;
- either eligible pickup clock >=60 seconds;
- any self-hosted runner identity;
- checkout/dependency/bootstrap/parity/import failure;
- any phase-2 control suite red;
- workflow conclusion other than success;
- missing rerun-safe artifact;
- receipt `accepted != true`;
- run ID, run-attempt or SHA mismatch;
- material flake requiring repeated retries to manufacture three greens.

Do not hide a failed first attempt by firing replacements until three green receipts exist. All attempts are evidence.

## Required returned receipt

Return one JSON/table containing every attempt. Minimum fields:

```text
label: A | B | C | retry-N
run_id
run_attempt
run_url
head_sha
run_created_at
trust_started_at
trust_completed_at
trust_pickup_seconds
trust_runner_name
trust_conclusion
hosted_started_at
hosted_completed_at
hosted_pickup_seconds
hosted_runner_name
hosted_conclusion
workflow_conclusion
receipt_schema
receipt_run_id
receipt_run_attempt
receipt_job_started_at_observed
receipt_phase1
receipt_phase2
receipt_production_contract_parity
receipt_accepted
receipt_runner_os
receipt_runner_arch
receipt_python
receipt_platform
congested_window: true|false
concurrent_m2_run_id|null
concurrent_m2_job_id|null
concurrent_m2_runner_name|null
notes
```

Preserve nulls as null; never replace absent evidence with guessed values.

## Acceptance tests

Sol may authorize W1-B only when:

1. three distinct trusted main-ref dispatches exist;
2. all attempts are disclosed, including any failures/reruns;
3. three accepted attempts have successful workflow conclusions;
4. each accepted attempt has a unique internally consistent `run_id + run_attempt` artifact with `accepted:true`;
5. trust and hosted pickup clocks are each <60 seconds on every accepted attempt;
6. accepted attempts identify hosted Linux capacity;
7. one accepted run has timestamped overlap with a real M2 production/render job;
8. there is no material environmental flake hidden by retries.

## Production-proof boundary

These canaries prove **hosted environment and capacity only**. They do not prove merge authority. Even after three accepted receipts, W1-B is a separate route-only change and must prove a real armed PR is merged by the hosted sweeper while M2 is busy, with zero `scripts/merge_on_green.py` semantic change.

## Stop condition

Stop after returning the complete three-run evidence package. Do not edit workflows, routes, tests, labels, runner registrations, or render defaults.

## Required continuation handoff

Return the evidence to Sol with the exact statement:

```text
W1-A dispatch proof complete. No W1-B change was made. Review all attempts, run_id + run_attempt receipts, pickup clocks, hosted runner identities, and the congested-window overlap before authorizing the merge-control route cutover.
```
