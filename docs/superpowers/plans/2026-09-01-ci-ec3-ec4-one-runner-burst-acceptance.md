# CI EC3-EC4 One-Runner Burst Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable exactly one ephemeral AWS JIT runner under natural eligible CI pressure, prove it cannot mask local-fleet/main-integrity failure or duplicate an ambiguous provisioning effect, and retain it only if a preregistered natural corpus demonstrates real latency benefit with zero semantic/trust regression.

**Architecture:** EC3 promotes the proven EC2 classifier from `WOULD_PROVISION_ONE` to one replay-safe `PROVISION_ONE` effect. The GitHub-hosted reconcile workflow remains serialized and fresh-reads state immediately before the effect. It generates JIT config for the existing production trusted executor with labels `ci-linux` + `ci-burst`, launches one EC2 instance using a deterministic client token tied to the oldest eligible workflow-job/run/profile/policy identity, and then GitHub—not Mastermind—chooses which matching queued trusted pack the runner receives. Normal one-job JIT exit powers off the instance; EC2 termination follows from `InstanceInitiatedShutdownBehavior=terminate`. AWS EC2 idempotency plus current instance inventory and native CloudTrail management-event history provide effect reconciliation without a custom capacity ledger. EC4 then measures at least 30 natural qualifying pressure events and either promotes, keeps disabled, or kills elastic production.

**Tech Stack:** Existing EC1 AWS/JIT substrate, existing EC2 wake/reconciler, AWS EC2/CloudTrail, GitHub JIT runner API, GitHub Actions protected environments/concurrency, existing CI semantic/receipt/timing plane, Python/pytest.

**Spec:** `docs/superpowers/specs/2026-09-01-ci-elastic-pressure-capacity-design.md`.

## Global Constraints

- Do not start until EC2 is Sol-accepted with its natural dry-run corpus and one exact production threshold has been frozen in `config/ci_capacity_policy.v1.json` from evidence.
- Before EC3 START, re-pin current #6717 spec, current four-runner production route, current L3 execution profile, current EC1 AMI/JIT canary proof, #6637 main-integrity interface, current EC2 wake/reconciler, and every open collision on owned paths.
- Production elastic ceiling is exactly one burst instance/runner. Provider-side IAM/code/policy/tests all enforce one.
- Production burst JIT labels are exactly `ci-linux` and `ci-burst` in existing `macro-home-canary`; the diagnostic `ci-linux-burst-canary` label is not used by production.
- Fork/untrusted PRs remain hosted. Candidate-controlled workflows cannot invoke/provision/register a burst runner.
- The burst VM retains the EC1 no-home-route/IMDS fence/log-only instance profile/external-log/immutable-profile laws.
- Cloud burst is suppressed unless all four accepted persistent runners are present, online and none idle; any missing/offline local runner is `REFUSED_LOCAL_POOL_DEGRADED`.
- Main integrity red/unknown, profile mismatch, provider ambiguity, existing burst resource, queue below threshold, or queue age above 15 minutes all refuse a new production effect. Queue age above 15 minutes is treated as a likely systemic/degraded condition rather than a license to keep throwing machines at it.
- No automatic semantic-job rerun, no second AWS provider, no hosted fallback change, no `max-parallel > 4` local change, no WSL expansion, no ARC/Scale Set Client, no scheduler, queue DB, retry ledger, capacity DB, runner registry, semantic gate, or merge controller.
- A failed or ambiguous burst attempt never changes the GitHub job. GitHub's own assignment/requeue semantics remain authoritative.
- Time of day may be recorded but never changes `PROVISION_ONE` eligibility.

---

### Task 1: Freeze the production policy and burst topology contract

**Files:**
- Modify: `config/ci_capacity_policy.v1.json`
- Modify: `.github/runner-policy.yml`
- Modify: `scripts/check_runner_policy.py`
- Modify: `tests/test_ci_capacity_reconcile.py`
- Modify: `tests/test_runner_policy.py`

**Interfaces:**
- EC2-proven threshold remains the exact `min_oldest_queue_age_seconds` in policy.
- New policy keys: `mode="production_canary"`, `max_new_attempt_queue_age_seconds=900`, `production_burst_label="ci-burst"`.
- Runner policy declares one elastic JIT pool without pretending a static runner name is live.

- [ ] **Step 1: Bank the EC2 threshold before changing mode**

At EC3 carrier creation, verify the committed `min_oldest_queue_age_seconds` equals the threshold accepted in `research/CI_ELASTIC_EC2_DRY_RUN_RESULTS_2026_09.md`. Tests read both and refuse disagreement. EC3 does not choose a new threshold.

- [ ] **Step 2: Write RED policy/topology tests**

Require policy:

```python
policy = json.loads(Path("config/ci_capacity_policy.v1.json").read_text())
assert policy["mode"] == "production_canary"
assert policy["max_burst_instances"] == 1
assert policy["max_new_attempt_queue_age_seconds"] == 900
assert policy["production_burst_label"] == "ci-burst"
```

Runner policy must gain exactly one elastic topology declaration such as:

```yaml
  ci-burst:
    slots: 1
    mode: ephemeral-jit
    labels: [self-hosted, ci-linux, ci-burst]
    static_carried_by: []
    forbidden_labels: [render-linux, ci-linux-canary, ci-linux-burst-canary]
```

and `label_registry.ci-burst` status `elastic` with zero static carriers. `ci-linux.carried_by` remains the four persistent runners only; its note explicitly permits at most one *temporarily attested* `ci-burst-*` JIT carrier through the `ci-burst` topology instead of lying in static `carried_by`.

`check_runner_policy.py` rejects a second elastic pool, slots >1, a burst pool without production `ci-linux`, a static `ci-burst` carrier, burst on render/fork/scheduled workflows, or candidate-defined runner workflow.

- [ ] **Step 3: Make the classifier refuse stale systemic pressure**

Add exact decision `REFUSED_QUEUE_TOO_OLD` when oldest eligible queue age exceeds 900 seconds. The production effect window is therefore:

```text
accepted threshold <= oldest eligible queue age <= 900 seconds
```

with all other safety gates green.

- [ ] **Step 4: Run tests and commit**

```bash
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py tests/test_runner_policy.py
python3.12 scripts/check_runner_policy.py
git diff --check
git add config/ci_capacity_policy.v1.json .github/runner-policy.yml \
  scripts/check_runner_policy.py tests/test_ci_capacity_reconcile.py tests/test_runner_policy.py
git commit -m "ci: freeze one-runner production burst policy"
```

---

### Task 2: Add native effect-history reconciliation and production JIT identity

**Files:**
- Modify: `scripts/ci_burst_aws.py`
- Modify: `tests/test_ci_burst_aws.py`
- Modify: `ops/runner-cloud/aws/ci-burst-stack.yml`
- Modify: `tests/test_ci_burst_aws_stack.py`

**Interfaces:**
- Production `reconcile_id` derives from repository + oldest queued workflow-job ID + its run ID + current run attempt + execution-profile ID + policy document SHA.
- AWS history source: EC2 inventory + CloudTrail `LookupEvents` for `RunInstances`, parsed for exact client token.
- New protected GitHub environment: `ci-burst-production`.

- [ ] **Step 1: Write RED reconcile-history tests**

Add:

```python
def test_production_reconcile_id_binds_exact_queue_job() -> None:
    one = BURST.production_reconcile_id(
        repository="mastermindx-market-intelligence/macro",
        job_id=123,
        run_id=456,
        run_attempt=1,
        execution_profile_id="ci-linux-x64-abc",
        policy_sha256="d" * 64,
    )
    two = BURST.production_reconcile_id(
        repository="mastermindx-market-intelligence/macro",
        job_id=124,
        run_id=456,
        run_attempt=1,
        execution_profile_id="ci-linux-x64-abc",
        policy_sha256="d" * 64,
    )
    assert one != two
```

Required provider reconciliations:

- matching nonterminal instance -> `PRESENT`;
- >1 matching instance -> `CONFLICT`;
- no current instance + CloudTrail `RunInstances` with same client token -> `ATTEMPT_ALREADY_OCCURRED_NO_RETRY`;
- no instance/history -> `ABSENT`;
- CloudTrail unavailable/ambiguous -> `EFFECT_UNKNOWN`, never `ABSENT`;
- same client token + changed EC2 parameters is rejected locally before AWS can return `IdempotentParameterMismatch`.

- [ ] **Step 2: Implement bounded CloudTrail lookup as source evidence, not a ledger**

Invoke:

```text
aws cloudtrail lookup-events --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=RunInstances \
  --max-results 50
```

Parse each `CloudTrailEvent` JSON and inspect `requestParameters.clientToken`. Bound pagination to events newer than the eligible GitHub job's queued time minus five minutes and never older than 24 hours; if the target interval cannot be fully inspected within the bound, return `EFFECT_UNKNOWN`.

This uses AWS's native management-event history. No trail/database/table is created by Mastermind for capacity attempts.

- [ ] **Step 3: Add a least-privilege production actuator role**

Extend the EC1 stack with GitHub OIDC role trusted only by:

```text
repo:mastermindx-market-intelligence/macro:environment:ci-burst-production
```

Permissions:

- exact bounded `ec2:RunInstances` conditions from EC1;
- `ec2:DescribeInstances`;
- idempotent `ec2:TerminateInstances` on tagged burst resources;
- `iam:PassRole` only the stack's log-only instance role, only to EC2;
- `cloudtrail:LookupEvents`;
- no IAM mutation, Secrets Manager, SSM RunCommand, S3, network mutation, runner-group mutation, or GitHub authority.

The provider-side EC2 quota/service-quota operational setting must also cap this role/workflow to one concurrent burst instance by tag/code checks; if an account-level service-quota construct cannot express tag-specific one, code + IAM + fresh inventory remain binding and EC4 treats any duplicate as terminal failure.

- [ ] **Step 4: Run and commit**

```bash
python3.12 -m pytest -q tests/test_ci_burst_aws.py tests/test_ci_burst_aws_stack.py
git diff --check
git add scripts/ci_burst_aws.py tests/test_ci_burst_aws.py \
  ops/runner-cloud/aws/ci-burst-stack.yml tests/test_ci_burst_aws_stack.py
git commit -m "ci: reconcile production burst effects natively"
```

---

### Task 3: Promote the serialized reconcile workflow from dry-run to one effect

**Files:**
- Modify: `.github/workflows/ci-capacity-reconcile.yml`
- Modify: `scripts/ci_capacity_reconcile.py`
- Modify: `tests/test_ci_capacity_workflow.py`
- Modify: `tests/test_ci_capacity_snapshot.py`

**Interfaces:**
- `decide` remains pure.
- New CLI `actuate --snapshot-before PATH --decision PATH --snapshot-after PATH --output PATH` may call EC2/JIT helpers only when two consecutive classifications both permit one effect.
- Production result schema `mastermind.ci_capacity_effect.v1`.

- [ ] **Step 1: Write RED workflow tests for the two-read TOCTOU fence**

Production workflow must have this order:

```text
snapshot-before
-> decide-before
-> if WOULD_PROVISION_ONE: fresh snapshot-after
-> decide-after
-> require both WOULD_PROVISION_ONE and same oldest eligible job/profile/main/policy identity
-> reconcile AWS effect history
-> generate JIT config
-> RunInstances once
-> wait for exact runner online or fail closed
-> publish effect receipt
```

Tests kill a workflow that launches from the first snapshot only, generates JIT before the second read, or launches when the oldest job changed/started/local runner became idle/main integrity changed.

- [ ] **Step 2: Add exact production execution-profile/runner checks**

Before JIT generation require:

- current L3 `execution_profile_id` exactly equals policy/snapshot;
- EC1 current AMI tagged with that profile;
- current four persistent expected runners online/busy;
- zero current `ci-burst-*` runner and zero nonterminal burst instance;
- trusted executor selected-workflow restriction still exact;
- production trusted executor still `group=macro-home-canary`, `labels=ci-linux` and local `max-parallel=4`.

Any drift is `REFUSED`.

- [ ] **Step 3: Generate one production JIT config after all gates**

Use the existing EC1 registrar App and request labels:

```json
["ci-linux", "ci-burst"]
```

Runner name is deterministic `ci-burst-<reconcile-id-prefix>`. Do not include `ci-linux-burst-canary` or `render-linux`.

The runner group remains `macro-home-canary`; no selected-workflow change is needed because production `trusted-ci-executor.yml@refs/heads/main` is already selected.

- [ ] **Step 4: Launch exactly one EC2 instance and wait only for eligibility**

Use environment `ci-burst-production`, pinned AWS OIDC credentials action, deterministic client token, current EC1 AMI, and existing bootstrap contract. The reconcile workflow waits up to 10 minutes for the exact runner to appear online. It does **not** choose/dispatch/retry a GitHub job. Once online, it records the runner and returns; GitHub decides which matching queued pack receives it.

If the runner fails to register, the reconcile workflow fails and records the effect. A future wake with the same oldest job must see EC2/CloudTrail attempt history and return `ATTEMPT_ALREADY_OCCURRED_NO_RETRY` rather than creating another VM.

- [ ] **Step 5: Make normal one-job exit self-terminate**

Amend the EC1 runner systemd unit/image contract so the JIT listener unit has:

```ini
SuccessAction=poweroff
FailureAction=poweroff
```

and the EC2 launch remains `InstanceInitiatedShutdownBehavior=terminate`. The image hard-stop timer is corrected to **210 minutes**: the trusted pack timeout is currently 180 minutes, so 210 provides a bounded 30-minute provisioning/teardown margin without killing a still-lawful semantic job. Tests reject a hard-stop shorter than 210 while trusted pack timeout remains 180.

A failed pre-registration bootstrap may terminate earlier through the launcher/reconcile cleanup because no GitHub job can be executing.

- [ ] **Step 6: Publish a non-authoritative effect receipt**

`capacity-effect.json` includes:

```text
schema
reconcile_id
source_job_id/source_run_id/source_run_attempt
policy_sha256
execution_profile_id
snapshot_before_sha256
snapshot_after_sha256
scale_decision
aws_instance_id (nonsecret)
aws_client_token_sha256 (hash only, not raw token if policy treats it sensitive)
runner_id/runner_name
provision_started_at
runner_registered_at
result = REGISTERED | REFUSED | EFFECT_UNKNOWN | ATTEMPT_ALREADY_OCCURRED_NO_RETRY
```

It cannot change semantic CI or merge state.

- [ ] **Step 7: Run source proof and commit**

```bash
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py tests/test_ci_capacity_snapshot.py \
  tests/test_ci_capacity_workflow.py tests/test_ci_burst_aws.py tests/test_runner_policy.py
python3.12 scripts/check_runner_policy.py
git diff --check
git add .github/workflows/ci-capacity-reconcile.yml scripts/ci_capacity_reconcile.py \
  tests/test_ci_capacity_workflow.py tests/test_ci_capacity_snapshot.py \
  ops/runner-cloud/aws/scripts/run-jit-once.sh ops/runner-cloud/aws/scripts/hard-stop.sh \
  tests/test_ci_burst_image.py
git commit -m "ci: enable one fail-closed burst runner"
```

---

### Task 4: Production safety reaper and rollback without job retry authority

**Files:**
- Modify: `scripts/ci_burst_aws.py`
- Modify: `scripts/ci_capacity_reconcile.py`
- Modify: `tests/test_ci_burst_aws.py`
- Modify: `tests/test_ci_capacity_reconcile.py`

**Interfaces:**
- `classify_orphans()` returns diagnostic orphan candidates.
- `reap-safe` terminates only an exact tagged resource proven unable to be executing a job.

- [ ] **Step 1: Write RED orphan tests**

Refuse termination if:

- matching GitHub runner is busy;
- matching workflow job is in_progress;
- runner/job inventory is unavailable;
- instance/reconcile/profile tags differ;
- bootstrap/runner logs have not flushed and instance is younger than hard-stop;
- instance age is below the reviewed pre-registration timeout while it may still register.

Allow termination of:

1. a `pending/running` instance older than 10 minutes whose runner never registered and no matching runner/job exists;
2. an instance older than 210 minutes with no busy runner/in-progress job, recording whether logs were preserved or lost.

- [ ] **Step 2: Implement reaper as part of the same serialized reconcile**

Every production reconcile fresh-reads orphan candidates before considering a new launch. If one unresolved burst resource exists, no new burst is created. `reap-safe` uses idempotent `TerminateInstances` only after all negative-authority checks.

The reaper never cancels/reruns a GitHub job and never changes semantic evidence.

- [ ] **Step 3: Define immediate rollback trigger**

Any of these disables further EC3 automatic provisioning through a source/config rollback to `mode=dry_run` before another production attempt:

- semantic parity mismatch attributable to burst route;
- fork/untrusted execution on burst;
- duplicate burst instances;
- candidate access to AWS management credentials/IMDS;
- missing external logs on a completed burst job;
- persistent pool/render regression caused by burst policy;
- same-SHA green/red nondeterminism attributable to execution profile;
- orphan deletion while a runner/job was busy.

Operational rollback is one bounded PR/config release plus, if needed, idempotent termination of an already-proven-idle burst instance. Do not disable the four persistent runners.

- [ ] **Step 4: Run and commit**

```bash
python3.12 -m pytest -q tests/test_ci_burst_aws.py tests/test_ci_capacity_reconcile.py
git diff --check
git add scripts/ci_burst_aws.py scripts/ci_capacity_reconcile.py \
  tests/test_ci_burst_aws.py tests/test_ci_capacity_reconcile.py
git commit -m "ci: make burst cleanup fail closed"
```

---

### Task 5: EC3 first natural queue-driven canary

**Files after proof:**
- Modify: `docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md`
- Modify: `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
- Create: `agentos/handoffs/CI-EC3-ONE-RUNNER-BURST-CANARY-2026-09-01.md`

- [ ] **Step 1: Stop for production actuator admin deployment**

Fresh-read AWS/GitHub environments, roles, runner group, EC1 AMI, EC2 wake adapter, policy, current main and all four persistent runners. Deploy the amended AWS stack/production environment only from accepted merged source. No cloud private key/token is shared through the worker carrier.

- [ ] **Step 2: Enable `mode=production_canary` only after exact-head/source proof**

The source PR must be exact-head green/fenced and independently reviewed. Merge/release is Sol-owned. Re-read deployed policy and role after effect.

- [ ] **Step 3: Wait for the first natural EC2-qualified pressure event**

Do not manufacture a product PR or semantic red. When a natural wake produces two consecutive `WOULD_PROVISION_ONE` snapshots:

- exactly one EC2 instance is created;
- exactly one production JIT runner registers;
- GitHub assigns its matching job naturally;
- runner consumes at most one job;
- semantic/receipt/timing evidence identifies actual job/profile;
- runner deregisters and instance terminates.

Do not launch another burst until this first event is fully reconciled and Sol reviews it.

- [ ] **Step 4: First-event PASS gate**

Require:

- local four-runner fleet stayed healthy;
- main integrity/profile stayed green/exact;
- provider effect identity unambiguous;
- no production/fork trust boundary drift;
- actual burst job semantic result agrees with the same accepted execution contract;
- JIT one-job behavior and external logs complete;
- no instance/runner orphan;
- queue/provision/pickup/checkout/dependency/test/wall/teardown timings present;
- no cache mutation.

A first-event fail returns EC3 to dry-run before any second automatic burst.

- [ ] **Step 5: Bank first-event records and continue only after Sol ACCEPT/CONTINUE**

Run Agent OS validation and return the immutable event receipt. EC3 worker does not independently widen to acceptance soak.

---

### Task 6: EC4 natural production acceptance and kill/retain ruling

**Files:**
- Create after corpus: `research/CI_ELASTIC_EC4_ACCEPTANCE_2026_09.md`
- Modify: `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
- Create: `agentos/handoffs/CI-EC4-ELASTIC-BURST-ACCEPTANCE-2026-09-01.md`
- Modify if verdict is kill/hold: `config/ci_capacity_policy.v1.json`

- [ ] **Step 1: Preregister the EC4 population before event 2**

Population is the next 30 natural **qualifying pressure events** seen by the production classifier after first-event Sol acceptance, with no cherry-picking by outcome. Record every qualifying event whether decision is scale, no-scale, refuse, provider unavailable, or already-present.

The population must contain, or EC4 remains incomplete:

- at least 10 actual `PROVISION_ONE` launches;
- at least 10 correct no-scale/refusal observations;
- at least 3 simultaneous-PR pressure windows;
- at least 1 independent active-render window;
- duplicate/delayed webhook observations if naturally delivered/redelivered;
- no manufactured semantic-red PRs.

If 30 qualifying events accrue but fewer than 10 genuine launches occurred, elastic need/usefulness is not sufficiently evidenced; keep the capability `BUILT_NOT_PROVEN`/disabled rather than manufacturing load.

- [ ] **Step 2: Compute the acceptance metrics deterministically**

For each event compute:

- queue depth and oldest queue age before decision;
- persistent runner online/idle/busy;
- provisioning-to-runner-online time;
- runner-online-to-job-start pickup time;
- actual job queue time;
- checkout/dependency/test/wall time;
- final-push-to-gate when the associated PR final head is eligible;
- instance billed lifetime approximation from EC2 launch/termination timestamps;
- estimated queue minutes avoided using the EC2 dry-run four-slot corpus in the same queue-depth band;
- launch usefulness (`executed_job` boolean);
- semantic parity/nondeterminism/orphan/security outcomes.

Do not use an LLM to grade acceptance.

- [ ] **Step 3: Apply the preregistered EC4 PASS ruler**

All hard gates:

- zero fork/untrusted burst jobs;
- zero duplicate burst instances;
- zero same-SHA semantic nondeterminism attributable to burst profile;
- zero candidate access to provisioning credentials/IMDS;
- zero busy-runner orphan deletions;
- zero unexplained missing semantic fragments or external runner logs;
- launch usefulness >= 80%;
- among successful launches, GitHub pickup success >= 95%;
- p95 eligible pack queue wait in matched queue-depth bands improves >= 20% versus the EC2 four-slot dry-run corpus;
- aggregate `estimated_queue_minutes_avoided / burst_instance_minutes >= 0.50`;
- ordinary/heavy PR final-push-to-gate SLOs do not regress from the existing <10m / <15-20m targets due to the burst path.

If any hard gate fails, verdict is `KILL_OR_REPAIR`, not `PROVEN_LIVE`. A metric miss does not authorize a second burst runner.

- [ ] **Step 4: Sol retention ruling**

Possible outcomes:

- `PROVEN_LIVE`: keep ceiling one and current measured threshold;
- `BUILT_NOT_PROVEN / HOLD`: disable automatic provisioning (`mode=dry_run`) and collect more natural evidence only if the missing gate is statistical rather than a defect;
- `KILL`: set `mode=dry_run`, revoke/disable production AWS role/environment path, preserve diagnostic EC1 canary if still useful, and retain records;
- `REQUEST_REPAIR`: bounded same-plane defect repair, then a new preregistered forward corpus—never erase failed events.

EC4 cannot authorize burst count two, another provider, ARC, or Scale Set Client. Those require EC5 fresh architecture.

- [ ] **Step 5: Durable closeout proof**

```bash
python3.12 scripts/agentos.py validate
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py tests/test_ci_capacity_snapshot.py \
  tests/test_ci_capacity_workflow.py tests/test_ci_burst_aws.py tests/test_ci_burst_wake.py \
  tests/test_runner_policy.py tests/test_ci_canary_tools.py
git diff --check
```

Record exact event/run/job/instance/runner/profile/policy/AMI IDs and final ruling without secrets.

## Stop Condition

Stop immediately if the production label cannot remain behind the existing main-defined trusted executor, a queue decision can outvote main-integrity/local-pool/profile gates, AWS effect history cannot distinguish a prior attempt safely, JIT registration gives candidate code cloud authority, automatic cleanup requires job cancellation/retry authority, or the acceptance evidence suggests more capacity is masking ownership/dependency/main-integrity debt.

## Completion Truth

Only EC4 PASS plus Sol retention ruling makes `ELASTIC_ONE_RUNNER_BURST = PROVEN_LIVE`. Even then the hard ceiling remains one. Loss of AWS/wake infrastructure degrades to the proven four persistent slots; it does not change CI correctness. Any >1 elastic capacity remains EC5 `NOT_AUTHORIZED`.