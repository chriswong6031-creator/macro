# CI EC3-EC4 One-Runner Burst Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable exactly one ephemeral AWS JIT runner under natural eligible CI pressure, prove it cannot mask local-fleet/main-integrity failure or duplicate an ambiguous provisioning effect, and retain it only if a preregistered natural corpus demonstrates real latency benefit with zero semantic/trust regression.

**Architecture:** EC3 promotes the accepted EC2 classifier from `WOULD_PROVISION_ONE` to one replay-safe `PROVISION_ONE` effect. The GitHub-hosted reconcile workflow remains serialized and performs two fresh state reads before modification. A production JIT runner enters the existing `macro-home-canary` group with labels `ci-linux` + `ci-burst`; GitHub, not Mastermind, assigns one matching trusted-pack job. AWS EC2 idempotent client tokens, current EC2 inventory, CloudTrail's native management-event history, exact GitHub runner inventory, and a dedicated AWS-account Standard On-Demand vCPU quota of exactly 8 provide effect/capacity fences without a Mastermind capacity database. A `c7i.2xlarge` is 8 vCPUs, so that dedicated-account quota permits at most one production runtime instance of the only allowed Standard instance type. EC4 then measures a fixed natural corpus and decides retain/hold/kill/repair; it cannot authorize a second runner.

**Tech Stack:** Accepted EC1 AWS/JIT substrate, accepted EC2 wake/reconciler, AWS EC2/CloudTrail/Service Quotas, GitHub JIT runner API, GitHub Actions protected environments/concurrency, existing CI semantic/receipt/timing plane, Python/pytest.

**Spec:** `docs/superpowers/specs/2026-09-01-ci-elastic-pressure-capacity-design.md`.

## Global Constraints

- Do not START until EC2 is Sol-accepted with `GO_EC3`, a literal calibrated threshold/corpus SHA in `config/ci_capacity_policy.v1.json`, and current prerequisites re-proven.
- Re-pin current four-runner production route, L3 execution profile, EC1 AMI/JIT proof, #6637 integrity context, EC2 wake/reconciler, AWS account and all owned-path collisions.
- Production elastic ceiling is exactly one burst instance/runner. Code, policy, fresh inventory and the AWS regional Standard On-Demand quota all enforce it.
- Production burst JIT labels are exactly `ci-linux` + `ci-burst`; diagnostic `ci-linux-burst-canary` is not used.
- Fork/untrusted PRs remain hosted. Candidate-controlled workflow code cannot invoke/provision/register burst capacity.
- Burst VM retains EC1 no-home-route, IMDS fence, log-only instance profile, external-log and immutable-profile laws.
- No burst unless exactly `pc-ci-1..4` are online and all busy. Missing/offline local runner => `REFUSED_LOCAL_POOL_DEGRADED`; idle local runner => `NO_SCALE`.
- Main integrity red/unknown, profile mismatch, provider/history ambiguity, existing burst effect, queue below calibrated threshold, or oldest queue age >900s refuses new effect. Very old queue is treated as systemic degradation, not permission to add machines.
- No automatic semantic-job rerun/cancel, second provider, hosted fallback mutation, local `max-parallel > 4`, WSL expansion, ARC/Scale Set Client, scheduler, queue DB, retry ledger, capacity DB, runner registry, semantic gate or merge controller.
- Failed/ambiguous burst attempt never changes the GitHub job. GitHub assignment/requeue remains authority.
- Time-of-day is context only.

---

### Task 1: Freeze production policy and elastic topology

**Files:**
- Modify: `config/ci_capacity_policy.v1.json`
- Modify: `.github/runner-policy.yml`
- Modify: `scripts/check_runner_policy.py`
- Modify: `tests/test_ci_capacity_reconcile.py`
- Modify: `tests/test_runner_policy.py`

**Interfaces:**
- Preserve EC2-calibrated literal `min_oldest_queue_age_seconds` and `calibration_corpus_sha256`.
- Add `mode="production_canary"`, `max_new_attempt_queue_age_seconds=900`, `production_burst_label="ci-burst"`, `aws_standard_vcpu_quota=8`.

- [ ] **Step 1: Write RED policy/topology tests**

Require mode/ceiling/quota and prove EC2 threshold/corpus SHA are unchanged when mode changes.

Runner policy gains exactly one elastic declaration:

```yaml
  ci-burst:
    slots: 1
    mode: ephemeral-jit
    labels: [self-hosted, ci-linux, ci-burst]
    static_carried_by: []
    forbidden_labels: [render-linux, ci-linux-canary, ci-linux-burst-canary]
```

`label_registry.ci-burst` is `elastic`, no static carriers. `ci-linux.carried_by` remains the four persistent runners; its note permits at most one temporarily attested `ci-burst-*` through the elastic topology instead of falsifying static inventory.

`check_runner_policy.py` rejects >1 elastic pool/slot, static burst carrier, missing production `ci-linux`, burst on render/fork/scheduled work, or candidate-defined runner admission.

- [ ] **Step 2: Add stale-pressure refusal**

`REFUSED_QUEUE_TOO_OLD` when oldest eligible queue age >900 seconds. Production window is:

```text
accepted EC2 threshold <= oldest eligible queue age <= 900 seconds
```

with all earlier safety gates green.

- [ ] **Step 3: Prove/commit**

```bash
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py tests/test_runner_policy.py
python3.12 scripts/check_runner_policy.py
git diff --check
git add config/ci_capacity_policy.v1.json .github/runner-policy.yml \
  scripts/check_runner_policy.py tests/test_ci_capacity_reconcile.py tests/test_runner_policy.py
git commit -m "ci: freeze one-runner production burst policy"
```

---

### Task 2: Add provider hard-cap and native effect-history reconciliation

**Files:**
- Modify: `scripts/ci_burst_aws.py`
- Modify: `tests/test_ci_burst_aws.py`
- Modify: `ops/runner-cloud/aws/ci-burst-stack.yml`
- Modify: `tests/test_ci_burst_aws_stack.py`

**Interfaces:**
- Production reconcile identity binds repository + oldest eligible job ID/run ID/run attempt + profile ID + policy SHA.
- Provider evidence: EC2 inventory + CloudTrail `LookupEvents` + Service Quotas `L-1216C47A`.
- Protected environment: `ci-burst-production`.

- [ ] **Step 1: Write RED reconcile-history and quota tests**

Require:

- changed job/run-attempt/profile/policy => changed reconcile ID;
- one matching nonterminal instance => `PRESENT`;
- >1 => `CONFLICT`;
- no current instance + CloudTrail RunInstances with same client token => `ATTEMPT_ALREADY_OCCURRED_NO_RETRY`;
- no instance/history => `ABSENT`;
- incomplete/unavailable CloudTrail => `EFFECT_UNKNOWN`, never `ABSENT`;
- same token + changed EC2 parameters => local refusal;
- Standard On-Demand service quota !=8 => `REFUSED_PROVIDER_HARD_CAP`;
- any other nonterminal Standard On-Demand EC2 instance in this **dedicated CI-burst AWS account/region** => `REFUSED_PROVIDER_ACCOUNT_NOT_QUIESCENT`.

- [ ] **Step 2: Implement native CloudTrail history lookup**

CloudTrail Event History is native AWS management-event history; create no trail/table/store. Query:

```bash
aws cloudtrail lookup-events --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=RunInstances \
  --start-time "$START_TIME" --end-time "$END_TIME" --max-results 50
```

Inspect `CloudTrailEvent.requestParameters.clientToken`. Traverse all returned pages covering from target job queued time minus 5 minutes to now, bounded to <=24h. If coverage cannot be proven, `EFFECT_UNKNOWN`.

- [ ] **Step 3: Implement the provider hard-cap qualification**

The production AWS account must be dedicated to Mastermind CI burst Standard On-Demand runtime. Before source activation/admin release, verify:

```bash
aws service-quotas get-service-quota --region us-east-1 \
  --service-code ec2 --quota-code L-1216C47A \
  --query 'Quota.Value' --output text
```

Expected literal value: `8.0`. Also `describe-instances` must show no other nonterminal Standard On-Demand instance outside the exact current `MastermindRole=ci-burst` effect. EC3 refuses if either condition fails.

If the dedicated account starts with a lower adjustable quota, the privileged operator may request an increase to exactly 8 before EC3. If the account's quota is already >8 and cannot be reduced to exactly 8, this provider hard-cap gate is **not satisfied**; do not waive it—return to Sol for a new provider-cap mechanism/account.

- [ ] **Step 4: Add least-privilege production actuator role**

OIDC trust subject exactly:

```text
repo:mastermindx-market-intelligence/macro:environment:ci-burst-production
```

Permissions: EC1-bounded `RunInstances`, `DescribeInstances`, tagged `TerminateInstances`, `iam:PassRole` only log-only instance role, `cloudtrail:LookupEvents`, `servicequotas:GetServiceQuota`; no IAM mutation, Secrets Manager, SSM, S3/network mutation, runner-group mutation.

- [ ] **Step 5: Prove/commit**

```bash
python3.12 -m pytest -q tests/test_ci_burst_aws.py tests/test_ci_burst_aws_stack.py
git diff --check
git add scripts/ci_burst_aws.py tests/test_ci_burst_aws.py \
  ops/runner-cloud/aws/ci-burst-stack.yml tests/test_ci_burst_aws_stack.py
git commit -m "ci: reconcile production burst effects natively"
```

---

### Task 3: Promote serialized reconcile from dry-run to one effect

**Files:**
- Modify: `.github/workflows/ci-capacity-reconcile.yml`
- Modify: `scripts/ci_capacity_reconcile.py`
- Modify: `tests/test_ci_capacity_workflow.py`
- Modify: `tests/test_ci_capacity_snapshot.py`
- Modify: `ops/runner-cloud/aws/scripts/run-jit-once.sh`
- Modify: `ops/runner-cloud/aws/scripts/hard-stop.sh`
- Modify: `tests/test_ci_burst_image.py`

**Interfaces:**
- `decide` stays pure.
- `actuate --snapshot-before ... --decision ... --snapshot-after ... --output capacity-effect.json` runs only after two agreeing permit decisions.
- Effect schema `mastermind.ci_capacity_effect.v1`.

- [ ] **Step 1: Write RED two-read TOCTOU workflow tests**

Required order:

```text
snapshot-before -> decide-before
-> fresh snapshot-after -> decide-after
-> both WOULD_PROVISION_ONE
-> same oldest job/run/attempt/main/profile/policy
-> reconcile provider quota/inventory/history
-> generate JIT config
-> launch exactly one EC2 effect
-> wait exact runner online
-> effect receipt
```

Kill a workflow that launches from first snapshot, generates JIT before second read, or continues when oldest job/local idle/main integrity/profile changed.

- [ ] **Step 2: Re-prove production route before JIT**

Require current L3 profile exact, EC1 AMI tagged same profile, four persistent online/busy, zero current `ci-burst-*` runner/effect, exact selected-workflow restriction, trusted executor still `group=macro-home-canary`, `labels=ci-linux`, local `max-parallel=4`, provider quota/account quiescent.

- [ ] **Step 3: Generate one production JIT runner**

Use existing registrar App; labels exactly:

```json
["ci-linux", "ci-burst"]
```

Name `ci-burst-<reconcile-id-prefix>`, group `macro-home-canary`. No canary/render labels. Capture returned runner ID/name in memory; encoded JIT config never enters receipt/log.

- [ ] **Step 4: Launch/reconcile one EC2 effect**

Use `ci-burst-production`, current AMI and deterministic EC2 client token. Wait up to 10 minutes only for exact runner `online`; do not choose/dispatch/retry a job. GitHub assigns naturally.

If `RunInstances` returns timeout/error, reconcile EC2+CloudTrail before any further action. If inventory/history says no effect occurred, delete only the exact offline never-started JIT runner record and end failed; do not generate a second JIT config in that reconcile turn. If AWS effect is unknown/present, do not delete runner record until the effect is reconciled because the instance may still register.

A future wake for the same oldest job sees prior attempt history and returns `ATTEMPT_ALREADY_OCCURRED_NO_RETRY`, not another VM.

- [ ] **Step 5: Keep one-job exit self-terminating**

JIT service retains:

```ini
SuccessAction=poweroff
FailureAction=poweroff
```

and EC2 `InstanceInitiatedShutdownBehavior=terminate`. Hard-stop remains 210 minutes (trusted pack timeout 180 + 30 margin). Tests bind these values so EC3 cannot shorten a lawful heavy job.

- [ ] **Step 6: Publish non-authoritative effect receipt**

Separate fields:

```text
schema
reconcile_id
source_job_id
source_run_id
source_run_attempt
policy_sha256
execution_profile_id
snapshot_before_sha256
snapshot_after_sha256
scale_decision
aws_instance_id
aws_client_token_sha256
runner_id
runner_name
provision_started_at
runner_registered_at
result
```

`result` is one of `REGISTERED | REFUSED | EFFECT_UNKNOWN | ATTEMPT_ALREADY_OCCURRED_NO_RETRY`. Receipt cannot change semantic CI.

- [ ] **Step 7: Prove/commit**

```bash
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py tests/test_ci_capacity_snapshot.py \
  tests/test_ci_capacity_workflow.py tests/test_ci_burst_aws.py tests/test_runner_policy.py \
  tests/test_ci_burst_image.py
python3.12 scripts/check_runner_policy.py
git diff --check
git add .github/workflows/ci-capacity-reconcile.yml scripts/ci_capacity_reconcile.py \
  tests/test_ci_capacity_workflow.py tests/test_ci_capacity_snapshot.py \
  ops/runner-cloud/aws/scripts/run-jit-once.sh ops/runner-cloud/aws/scripts/hard-stop.sh \
  tests/test_ci_burst_image.py
git commit -m "ci: enable one fail-closed burst runner"
```

---

### Task 4: Add safe orphan cleanup without job retry authority

**Files:**
- Modify: `scripts/ci_burst_aws.py`
- Modify: `scripts/ci_capacity_reconcile.py`
- Modify: `tests/test_ci_burst_aws.py`
- Modify: `tests/test_ci_capacity_reconcile.py`

- [ ] **Step 1: Write RED cleanup tests**

Refuse termination when matching runner busy, matching job in_progress, runner/job inventory unavailable, tags/profile differ, or resource may still lawfully register/execute. Allow cleanup only for:

1. pre-registration instance >10 minutes with no matching runner/job and reconciled effect identity;
2. instance >210 minutes with no busy runner/in-progress job, recording external-log preserved/lost status.

- [ ] **Step 2: Implement cleanup inside same serialized reconcile**

Every reconcile examines existing burst effect before new launch. Unresolved resource blocks new capacity. `TerminateInstances` only after all negative-authority checks. Never cancel/rerun GitHub work.

- [ ] **Step 3: Freeze rollback trigger**

Any burst-attributable semantic mismatch, fork execution, duplicate instance, candidate IMDS/provisioning access, missing completed-run external logs, persistent/render regression, same-SHA nondeterminism, or busy-resource deletion immediately requires mode rollback to `dry_run` before another automatic launch. Rollback never disables four persistent runners.

- [ ] **Step 4: Prove/commit**

```bash
python3.12 -m pytest -q tests/test_ci_burst_aws.py tests/test_ci_capacity_reconcile.py
git diff --check
git add scripts/ci_burst_aws.py scripts/ci_capacity_reconcile.py \
  tests/test_ci_burst_aws.py tests/test_ci_capacity_reconcile.py
git commit -m "ci: make burst cleanup fail closed"
```

---

### Task 5: Run the first natural queue-driven production canary

**Files after proof:**
- Modify: `docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md`
- Modify: `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
- Create: `agentos/handoffs/CI-EC3-ONE-RUNNER-BURST-CANARY-2026-09-01.md`

- [ ] **Step 1: Stop for production actuator/admin quota qualification**

Fresh-read dedicated AWS account ID/region, Standard quota exact 8, no other Standard instances, AWS roles/environments, runner group, AMI/profile, wake adapter/policy, current main and all four persistent runners. Deploy merged source only.

- [ ] **Step 2: Enable production-canary mode only after source release**

Source PR must be exact-head green/fenced/independently reviewed; Sol owns release. Re-read deployed policy/IAM/quota after effect.

- [ ] **Step 3: Wait for first natural EC2-qualified pressure event**

No manufactured product PR/red. On two agreeing fresh permit snapshots: one instance, one JIT runner, GitHub natural assignment, at most one job, exact semantic/receipt/timing identity, auto-deregister and termination. No second burst until first event is fully reconciled and Sol-reviewed.

- [ ] **Step 4: First-event PASS**

Require local four-runner fleet/main/profile/provider healthy; one unambiguous effect; no trust drift; actual burst job semantic contract valid; JIT one-job + external logs complete; no orphan; full queue/provision/pickup/checkout/dependency/test/wall/teardown timing; no cache mutation.

Any first-event FAIL returns mode to dry-run before a second automatic event.

- [ ] **Step 5: Bank immutable first-event record and return to Sol**

Run Agent OS validation; worker does not widen directly into EC4 without fresh Sol continuation/child law.

---

### Task 6: EC4 preregistered natural acceptance and retention ruling

**Files:**
- Create: `research/CI_ELASTIC_EC4_ACCEPTANCE_2026_09.md`
- Modify: `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
- Create: `agentos/handoffs/CI-EC4-ELASTIC-BURST-ACCEPTANCE-2026-09-01.md`
- Modify on hold/kill: `config/ci_capacity_policy.v1.json`

- [ ] **Step 1: Freeze population before event 2**

Population is next 30 natural **qualifying pressure events** after first-event Sol acceptance, no outcome cherry-picking. Must contain >=10 actual launches, >=10 correct no-scale/refusal observations, >=3 simultaneous-PR windows, >=1 active-render window; no manufactured semantic-red PRs. If 30 qualify but <10 launches, need/usefulness is not adequately evidenced: disable/hold rather than manufacture load.

- [ ] **Step 2: Compute deterministic metrics per event**

Queue depth/age; persistent state; provisioning-to-online; online-to-job-start; actual queue wait; checkout/dependency/test/wall; final-push-to-gate where applicable; instance lifetime; queue minutes avoided versus EC2 four-slot matched queue-depth bands; launch usefulness; parity/nondeterminism/orphan/security outcomes.

- [ ] **Step 3: Apply hard EC4 PASS ruler**

All required:

- zero fork/untrusted burst jobs;
- zero duplicate burst instances;
- zero route-attributable same-SHA nondeterminism;
- zero candidate access to provisioning/IMDS;
- zero busy-runner orphan deletions;
- zero unexplained missing semantic fragments/external runner logs;
- launch usefulness >=80%;
- successful-launch GitHub pickup >=95%;
- p95 eligible pack queue wait in matched queue-depth bands improves >=20% vs EC2 corpus;
- `estimated_queue_minutes_avoided / burst_instance_minutes >= 0.50`;
- ordinary/heavy final-push-to-gate SLOs do not regress from <10m / <15-20m due to burst path.

Any hard-gate miss => `KILL_OR_REPAIR`, never permission for runner two.

- [ ] **Step 4: Sol ruling states**

`PROVEN_LIVE` keep ceiling one/current threshold; `BUILT_NOT_PROVEN/HOLD` return to dry-run for statistical incompleteness; `KILL` return dry-run + disable production role/environment while preserving diagnostic EC1 if useful; `REQUEST_REPAIR` bounded same-plane fix then new forward corpus. EC5 is the only place allowed to reconsider count/provider/Scale Set/ARC.

- [ ] **Step 5: Durable closeout proof**

```bash
python3.12 scripts/agentos.py validate
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py tests/test_ci_capacity_snapshot.py \
  tests/test_ci_capacity_workflow.py tests/test_ci_burst_aws.py tests/test_ci_burst_wake.py \
  tests/test_runner_policy.py tests/test_ci_canary_tools.py
git diff --check
```

Record exact event/run/job/instance/runner/profile/policy/AMI IDs, AWS account/region/quota receipt and final ruling without secrets.

## Stop Condition

Stop if production label cannot remain behind main-defined trusted executor, queue pressure can outvote integrity/local/profile/provider gates, dedicated AWS quota hard-cap cannot be proven exactly 8, AWS history cannot reconcile prior attempt, JIT grants candidate cloud authority, cleanup requires GitHub job cancel/retry, or evidence shows capacity is masking ownership/dependency/main-integrity debt.

## Completion Truth

Only EC4 PASS plus Sol retention makes `ELASTIC_ONE_RUNNER_BURST = PROVEN_LIVE`. Ceiling remains one. Loss of AWS/wake infrastructure degrades to four persistent slots and cannot change CI correctness. >1 elastic capacity remains `NOT_AUTHORIZED` pending EC5.