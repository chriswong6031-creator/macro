# CI EC2 Pressure Reconciler Dry-Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn real GitHub `workflow_job` queue pressure into a serialized, explainable **dry-run** capacity decision while provisioning authority remains disabled, proving duplicate/delayed webhooks cannot create state drift and that a degraded local pool, bad/unknown main integrity, stale execution profile, or existing burst resource always refuses scale-out.

**Architecture:** A separate low-authority GitHub App delivers `workflow_job` webhooks to an AWS Lambda Function URL. Lambda validates GitHub's HMAC signature, filters only queued trusted-pack-shaped jobs, checks GitHub for an already queued/in-progress reconcile workflow, and dispatches `ci-capacity-reconcile.yml@main`; it stores no cursor or job state. The GitHub-hosted reconcile workflow uses one stable Actions concurrency group, fresh-reads GitHub job/runner truth plus AWS `DescribeInstances`, consumes the accepted #6637 main-integrity condition, and runs a pure deterministic classifier. EC2 outputs `NO_SCALE`, `WOULD_PROVISION_ONE`, `REFUSED`, or `EFFECT_UNKNOWN` only. It never calls `RunInstances`, generates JIT config, changes runner labels, or terminates a VM.

**Tech Stack:** GitHub App webhooks, AWS Lambda Python 3.12, Lambda Function URL, AWS Secrets Manager, CloudFormation, GitHub Actions workflow dispatch/concurrency, GitHub REST API, AWS EC2 read-only API, Python dataclasses/pytest.

**Spec:** `docs/superpowers/specs/2026-09-01-ci-elastic-pressure-capacity-design.md`.

## Global Constraints

- Do not start until #6717 architecture, C3 four-slot production promotion, L3 immutable execution profile, EC1 diagnostic JIT substrate, and #6637 main-integrity source are Sol-accepted on current `main`.
- EC2 is read-only with respect to runners/EC2 capacity. No `RunInstances`, `TerminateInstances`, `generate-jitconfig`, runner-group mutation, label mutation, or production workflow routing occurs.
- GitHub Actions remains the job scheduler/queue/assignment owner. The Lambda webhook receiver is transport only and may not persist a queue cursor or infer completion.
- A duplicate, delayed, out-of-order or missing webhook cannot change correctness. Every dispatched reconcile run fresh-reads GitHub/AWS state after acquiring one stable Actions concurrency group.
- The webhook Lambda has **zero EC2 permissions** and the dry-run workflow's AWS role has only `ec2:DescribeInstances`.
- The wake GitHub App is distinct from the EC1 runner registrar App. It has repository `Actions: write` plus metadata only; it has no self-hosted-runner, contents-write, workflows-write, issues, pulls, administration, or merge permission.
- Webhook secret and wake-App private key live only in AWS Secrets Manager. Candidate jobs and self-hosted runners never receive them.
- EC2's initial threshold is a **calibration value**, not production authority: oldest eligible queue age 90 seconds and at least one eligible queued trusted pack while all four accepted persistent runners are online/busy. EC3 may replace the threshold only from the accepted EC2 corpus.
- If the accepted #6637 main-integrity owner does not expose a machine-readable or directly queryable current-main condition, EC2 must return `REFUSED_MAIN_INTEGRITY_UNKNOWN`; do not create a new main-health check.
- If the expected four persistent runners are not all present and online, return `REFUSED_LOCAL_POOL_DEGRADED`; cloud burst cannot hide local-fleet failure.
- No time-of-day trigger authorizes scale. Time window may be recorded as context only.
- No second provider, retry plane, runner registry, scheduler, queue database, proof store, capacity database, or semantic gate.

---

### Task 1: Freeze the deterministic pressure snapshot and decision contract

**Files:**
- Create: `scripts/ci_capacity_reconcile.py`
- Create: `config/ci_capacity_policy.v1.json`
- Create: `tests/test_ci_capacity_reconcile.py`

**Interfaces:**
- Schema: `mastermind.ci_capacity_snapshot.v1` for non-authoritative snapshots.
- Policy schema: `mastermind.ci_capacity_policy.v1`.
- Public API: `classify(snapshot, policy) -> CapacityDecision`.

- [ ] **Step 1: Write the complete decision matrix RED tests first**

Create immutable test helpers:

```python
from dataclasses import replace
from scripts import ci_capacity_reconcile as CAP


def healthy() -> CAP.CapacitySnapshot:
    return CAP.CapacitySnapshot(
        repository="mastermindx-market-intelligence/macro",
        observed_at="2026-09-01T12:00:00Z",
        main_sha="a" * 40,
        main_integrity="green",
        execution_profile_id="ci-linux-x64-deadbeef",
        expected_persistent=("pc-ci-1", "pc-ci-2", "pc-ci-3", "pc-ci-4"),
        persistent_online=("pc-ci-1", "pc-ci-2", "pc-ci-3", "pc-ci-4"),
        persistent_idle=(),
        persistent_busy=("pc-ci-1", "pc-ci-2", "pc-ci-3", "pc-ci-4"),
        eligible_queued=(
            CAP.QueuedJob(job_id=11, run_id=22, name="trusted-ci / trusted-executor-pack-7",
                          queued_at="2026-09-01T11:58:00Z"),
        ),
        burst_instances=(),
        burst_runners=(),
        provider_state="available",
    )
```

Required decisions:

```python
assert CAP.classify(healthy(), CAP.load_policy()).code == "WOULD_PROVISION_ONE"
assert CAP.classify(replace(healthy(), persistent_idle=("pc-ci-4",)), CAP.load_policy()).code == "NO_SCALE"
assert CAP.classify(replace(healthy(), persistent_online=("pc-ci-1", "pc-ci-2", "pc-ci-3")), CAP.load_policy()).code == "REFUSED_LOCAL_POOL_DEGRADED"
assert CAP.classify(replace(healthy(), main_integrity="red"), CAP.load_policy()).code == "REFUSED_MAIN_INTEGRITY_RED"
assert CAP.classify(replace(healthy(), main_integrity="unknown"), CAP.load_policy()).code == "REFUSED_MAIN_INTEGRITY_UNKNOWN"
assert CAP.classify(replace(healthy(), burst_instances=("i-123",)), CAP.load_policy()).code == "NO_SCALE_BURST_PRESENT"
assert CAP.classify(replace(healthy(), provider_state="effect_unknown"), CAP.load_policy()).code == "EFFECT_UNKNOWN"
```

Add boundaries at 89.999/90 seconds, malformed future queue timestamps, duplicate runner names, a runner both idle and busy, wrong execution profile, queued job with wrong job name/labels, provider unavailable, and multiple burst resources. Invalid snapshots raise before a decision.

- [ ] **Step 2: Run and confirm RED**

```bash
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py
```

Expected: module/policy missing.

- [ ] **Step 3: Implement the closed dataclasses and validation**

Public types:

```python
@dataclass(frozen=True)
class QueuedJob:
    job_id: int
    run_id: int
    name: str
    queued_at: str

@dataclass(frozen=True)
class CapacitySnapshot:
    repository: str
    observed_at: str
    main_sha: str
    main_integrity: str
    execution_profile_id: str
    expected_persistent: tuple[str, ...]
    persistent_online: tuple[str, ...]
    persistent_idle: tuple[str, ...]
    persistent_busy: tuple[str, ...]
    eligible_queued: tuple[QueuedJob, ...]
    burst_instances: tuple[str, ...]
    burst_runners: tuple[str, ...]
    provider_state: str

@dataclass(frozen=True)
class CapacityDecision:
    code: str
    scale_decision: str  # NO_SCALE | WOULD_PROVISION_ONE | REFUSED | EFFECT_UNKNOWN
    reason: str
    eligible_queue_depth: int
    oldest_eligible_queue_age_seconds: float | None
```

`config/ci_capacity_policy.v1.json` at EC2 starts with:

```json
{
  "schema": "mastermind.ci_capacity_policy.v1",
  "repository": "mastermindx-market-intelligence/macro",
  "expected_persistent_runners": ["pc-ci-1", "pc-ci-2", "pc-ci-3", "pc-ci-4"],
  "burst_label": "ci-linux-burst-canary",
  "production_label": "ci-linux",
  "max_burst_instances": 1,
  "min_oldest_queue_age_seconds": 90,
  "min_eligible_queue_depth": 1,
  "mode": "dry_run"
}
```

Do not place a mutable count/state/cursor in this file.

- [ ] **Step 4: Encode decision precedence explicitly**

`classify()` order is fixed:

1. validate snapshot/policy identities;
2. provider `effect_unknown` -> `EFFECT_UNKNOWN`;
3. main integrity red/unknown -> refuse;
4. expected persistent set not exactly online -> local-pool degraded refuse;
5. execution-profile mismatch -> refuse;
6. multiple burst resources/runners -> conflict refuse;
7. one burst resource/runner present -> no scale;
8. any persistent idle -> no scale;
9. no eligible queue -> no scale;
10. queue age/depth below threshold -> no scale;
11. otherwise `WOULD_PROVISION_ONE`.

This order is tested; later refactors cannot make queue pressure outrank safety.

- [ ] **Step 5: Run tests and commit**

```bash
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py
git diff --check
git add scripts/ci_capacity_reconcile.py config/ci_capacity_policy.v1.json \
  tests/test_ci_capacity_reconcile.py
git commit -m "ci: define fail-closed capacity classifier"
```

---

### Task 2: Implement fresh GitHub/AWS snapshot collection without durable state

**Files:**
- Modify: `scripts/ci_capacity_reconcile.py`
- Create: `tests/test_ci_capacity_snapshot.py`

**Interfaces:**
- CLI: `snapshot --repository mastermindx-market-intelligence/macro --output PATH`.
- GitHub inputs: repository Actions runs/jobs, org runner group/runners, current main commit/checks.
- AWS input: `DescribeInstances` for `MastermindRole=ci-burst`.

- [ ] **Step 1: Write RED parsing/eligibility tests using captured API fixture shapes**

Fixtures must include:

- one `ci` run with hosted control jobs and queued `trusted-ci / trusted-executor-pack-3` carrying label `ci-linux`;
- another queued non-CI job that must not count;
- four persistent runners with names/status/busy fields;
- one `ci-burst-*` diagnostic runner;
- current main check runs with the accepted #6637 integrity check;
- AWS instances in running/stopped/terminated states with exact tags.

Eligibility requires **all**:

```text
job status == queued
job name matches ^trusted-ci / trusted-executor-pack-[0-9]+$
job labels contain ci-linux
job belongs to the current repository's ordinary trusted route
```

A job whose payload merely contains a similarly named string does not count.

- [ ] **Step 2: Implement bounded GitHub REST reads**

Use `GITHUB_TOKEN` for repository Actions/check reads and `CI_BURST_REGISTRAR_TOKEN` only for organization runner-group/runners reads. Every request sets GitHub API version `2022-11-28`, checks HTTP status, bounds pagination, and refuses partial/ambiguous inventory.

Required ladder:

1. resolve current `main` SHA;
2. read accepted #6637 main-integrity check for **that SHA**;
3. list queued + in-progress `ci` workflow runs in a bounded recent window;
4. list jobs for those runs and filter exact eligible jobs;
5. list runner groups, require exactly one `macro-home-canary`;
6. list its runners, classify exact persistent names and `ci-burst-*` runners.

If #6637 has not landed a stable check/context by EC2 START, STOP. At implementation START, record its exact accepted context in `config/ci_capacity_policy.v1.json` under key `main_integrity_check`; do not invent a synonym. Tests then pin that exact string.

- [ ] **Step 3: Implement AWS read-only collection**

Invoke AWS CLI only as:

```text
aws ec2 describe-instances --region us-east-1 \
  --filters Name=tag:MastermindRole,Values=ci-burst \
            Name=instance-state-name,Values=pending,running,stopping,stopped,shutting-down
```

Classify instances by exact `MastermindReconcileId`/`ExecutionProfileId`. Multiple nonterminal resources for the current role are visible conflict evidence, not silently collapsed.

- [ ] **Step 4: Preserve missing/ambiguous state explicitly**

Any GitHub pagination failure, runner-group ambiguity, main-check ambiguity, malformed timestamp, or AWS read failure must produce a typed snapshot collection failure and an EC2 workflow conclusion `REFUSED_SNAPSHOT_INCOMPLETE`. Do not transform it to empty queue/provider available.

- [ ] **Step 5: Run tests and commit**

```bash
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py tests/test_ci_capacity_snapshot.py
git diff --check
git add scripts/ci_capacity_reconcile.py tests/test_ci_capacity_snapshot.py \
  config/ci_capacity_policy.v1.json
git commit -m "ci: collect fresh capacity truth"
```

---

### Task 3: Build the webhook wake adapter with no lifecycle state

**Files:**
- Create: `ops/runner-cloud/aws/ci-burst-wake-stack.yml`
- Create: `ops/runner-cloud/aws/wake/handler.py`
- Create: `ops/runner-cloud/aws/wake/requirements.txt`
- Create: `tests/test_ci_burst_wake.py`

**Interfaces:**
- Public input: GitHub `workflow_job` webhook over Lambda Function URL.
- AWS secrets: `/mastermind/ci-burst/wake/webhook-secret`, `/mastermind/ci-burst/wake/github-app-private-key`.
- Dispatch target: `.github/workflows/ci-capacity-reconcile.yml@main`.

- [ ] **Step 1: Write RED webhook verification/filter tests**

Tests must prove:

- invalid/missing `X-Hub-Signature-256` -> HTTP 401 and no GitHub call;
- valid non-`workflow_job`/non-queued event -> HTTP 202 ignored;
- queued job without `ci-linux` label -> ignored;
- queued job name outside `trusted-ci / trusted-executor-pack-N` -> ignored;
- fork/untrusted repository identity -> ignored;
- an already queued/in-progress reconcile workflow -> no new dispatch;
- clean eligible wake -> exactly one workflow dispatch call;
- duplicate wake may produce another dispatch only if GitHub says no reconcile run exists; correctness is still enforced by workflow concurrency/fresh state;
- handler imports/uses no boto3 EC2 client and no local/sqlite/dynamodb/sqs state.

- [ ] **Step 2: Implement HMAC validation before JSON parsing authority**

Compute:

```python
expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
if not hmac.compare_digest(expected, supplied):
    return response(401, "invalid signature")
```

Then parse bounded JSON, require repository full name exact, `action == "queued"`, exact job-name regex, and labels containing `ci-linux`. The payload is still a wake hint; no scale decision is made here.

- [ ] **Step 3: Implement the separate wake GitHub App token**

Package `PyJWT==2.10.1` and `cryptography==45.0.7` in the Lambda artifact with hashes recorded in `requirements.txt`. Mint a GitHub App JWT from the secret private key, discover the installation for `mastermindx-market-intelligence`, request an installation token, then use only:

- `GET /repos/.../actions/workflows/ci-capacity-reconcile.yml/runs?status=queued`
- same endpoint `status=in_progress`
- `POST /repos/.../actions/workflows/ci-capacity-reconcile.yml/dispatches`

The wake App repository permission is `Actions: write` plus metadata. It has no contents-write, runner, administration, pull-request, issue, workflow-edit, or merge permission.

- [ ] **Step 4: Implement the AWS wake stack**

CloudFormation creates:

- two Secrets Manager secret containers with no source-controlled secret value;
- Lambda role with CloudWatch Logs + `secretsmanager:GetSecretValue` on exactly those two secrets;
- Python 3.12 Lambda with reserved concurrency `1`;
- Function URL `AuthType: NONE` because GitHub HMAC is the application authentication;
- no VPC attachment, EC2 permissions, DynamoDB, SQS, EventBridge scheduler, Step Functions, or persistent queue.

Output `WakeFunctionUrl` only.

- [ ] **Step 5: Run tests/static policy proof and commit**

```bash
python3.12 -m pytest -q tests/test_ci_burst_wake.py
python3.12 - <<'PY'
import yaml
p = yaml.safe_load(open('ops/runner-cloud/aws/ci-burst-wake-stack.yml'))
text = open('ops/runner-cloud/aws/ci-burst-wake-stack.yml').read()
for forbidden in ('dynamodb:', 'sqs:', 'ec2:RunInstances', 'ec2:TerminateInstances'):
    assert forbidden not in text
PY
git diff --check
git add ops/runner-cloud/aws/ci-burst-wake-stack.yml \
  ops/runner-cloud/aws/wake/handler.py ops/runner-cloud/aws/wake/requirements.txt \
  tests/test_ci_burst_wake.py
git commit -m "ci: add stateless workflow-job wake adapter"
```

---

### Task 4: Build the serialized GitHub-hosted dry-run reconcile workflow

**Files:**
- Create: `.github/workflows/ci-capacity-reconcile.yml`
- Create: `tests/test_ci_capacity_workflow.py`
- Modify: `ops/runner-cloud/aws/ci-burst-wake-stack.yml`

**Interfaces:**
- Trigger: `workflow_dispatch` only.
- Concurrency: `group: ci-capacity-reconcile`, `cancel-in-progress: false`.
- Output artifact: `ci-capacity-decision` containing snapshot + decision, retention 14 days.

- [ ] **Step 1: Write RED workflow authority tests**

Require:

```yaml
on:
  workflow_dispatch:
concurrency:
  group: ci-capacity-reconcile
  cancel-in-progress: false
permissions:
  actions: read
  checks: read
  contents: read
  id-token: write
```

Reject `pull_request`, `pull_request_target`, `push`, `schedule`, candidate-controlled `uses: ./`, any self-hosted `runs-on`, and any EC2 create/terminate/JIT request text.

- [ ] **Step 2: Add a read-only AWS observer role to the wake stack**

Trust only GitHub OIDC subject:

```text
repo:mastermindx-market-intelligence/macro:environment:ci-burst-reconcile
```

Permission: `ec2:DescribeInstances` only. No pass-role, run, terminate, IAM, Secrets Manager, SSM, or logs mutation.

- [ ] **Step 3: Implement the workflow**

One hosted job in protected environment `ci-burst-reconcile`:

1. checkout `main` control;
2. setup Python 3.12.13;
3. mint the existing EC1 registrar App token for runner-group **read** (the App's self-hosted-runners write permission already implies the needed API read, but no mutation endpoint is called in EC2);
4. configure AWS OIDC using the read-only observer role;
5. `python scripts/ci_capacity_reconcile.py snapshot --output snapshot.json`;
6. `python scripts/ci_capacity_reconcile.py decide --snapshot snapshot.json --policy config/ci_capacity_policy.v1.json --output decision.json`;
7. upload the two non-secret JSON files;
8. write a job summary.

The workflow fails only on malformed/incomplete collection/code errors. A `REFUSED` or `NO_SCALE` decision is a successful dry-run observation, not a CI failure.

- [ ] **Step 4: Run tests and commit**

```bash
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py tests/test_ci_capacity_snapshot.py \
  tests/test_ci_capacity_workflow.py tests/test_ci_burst_wake.py
git diff --check
git add .github/workflows/ci-capacity-reconcile.yml \
  tests/test_ci_capacity_workflow.py ops/runner-cloud/aws/ci-burst-wake-stack.yml
git commit -m "ci: add serialized capacity dry run"
```

---

### Task 5: Deploy wake transport and accrue the preregistered dry-run corpus

**Files:**
- Modify: `docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md`
- Modify: `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
- Create: `agentos/handoffs/CI-EC2-PRESSURE-RECONCILER-2026-09-01.md`
- Create after corpus: `research/CI_ELASTIC_EC2_DRY_RUN_RESULTS_2026_09.md`

- [ ] **Step 1: Stop for admin deployment authority**

Fresh-census the existing EC1 AWS stack, runner group, GitHub Apps, current four-runner liveness, #6637 current-main interface, and open path collisions. No deploy from an unmerged source PR.

- [ ] **Step 2: Create/install the Wake App and deploy the stack**

Create `Mastermind CI Capacity Wake` with repository `Actions: write`, subscribe only to `workflow_job`, install only for Macro. Deploy `mastermind-ci-burst-wake` CloudFormation stack and place webhook secret + App private key directly into the two AWS Secrets Manager secrets through the privileged operator path. Never paste their values into chat/Slack/GitHub.

Configure the GitHub App webhook URL to the stack's Function URL and the exact same webhook secret.

- [ ] **Step 3: Configure GitHub Environment `ci-burst-reconcile`**

Set only non-secret variable `CI_BURST_AWS_OBSERVER_ROLE_ARN` and the EC1 registrar App ID/private-key secret already needed to read runner inventory. Require current repository environment protection appropriate for CI-control infrastructure.

- [ ] **Step 4: Prove webhook negative controls before natural traffic**

Using GitHub's webhook redelivery/test surface or a signed local fixture routed only to the deployed endpoint, prove:

- invalid signature refused;
- unrelated workflow job ignored;
- eligible `workflow_job queued` causes exactly one reconcile workflow dispatch when no reconcile is active;
- duplicate delivery while a reconcile is queued/in-progress does not create another active reconcile;
- Lambda has no EC2 permission and decision remains dry-run.

- [ ] **Step 5: Accrue at least 30 natural dry-run observations**

Corpus must include:

- at least 10 `NO_SCALE` with persistent capacity available or queue under threshold;
- at least 5 `WOULD_PROVISION_ONE` pressure decisions if natural traffic produces them;
- at least 3 local-pool/main-integrity/provider/profile refusal/negative-control observations across natural or non-disruptive controlled conditions;
- simultaneous-PR windows;
- at least one window with independent render active;
- duplicate/delayed webhook redelivery evidence showing decision correctness unchanged.

For every observation record eligible queue depth, oldest queue age, persistent online/idle/busy, main integrity, profile, provider inventory, decision, selected logical-job/pack counts where available, and whether the decision would have helped final-push-to-gate SLO.

If natural traffic produces fewer than 5 genuine `WOULD_PROVISION_ONE` decisions after 14 days, do not manufacture load; report that elastic production demand is unproven and hold EC3.

- [ ] **Step 6: Calibrate, do not guess, the EC3 threshold**

Freeze one recommended threshold from the corpus before EC3 implementation. The chosen threshold must minimize useless launches while catching observed p95 SLO-risk windows. Record the exact method in `research/CI_ELASTIC_EC2_DRY_RUN_RESULTS_2026_09.md`; do not train a model or make the threshold an LLM output.

- [ ] **Step 7: Exact-head review and return**

```bash
python3.12 scripts/agentos.py validate
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py tests/test_ci_capacity_snapshot.py \
  tests/test_ci_burst_wake.py tests/test_ci_capacity_workflow.py
git diff --check
```

Return one DRAFT/HOLD-FOR-SOL implementation PR and the natural dry-run evidence. Worker does not enable provisioning or self-merge.

## Stop Condition

Stop before EC3 if the wake App requires broader permissions, webhook validation cannot be closed, duplicate wakes can bypass serialized fresh-state reconciliation, #6637 main integrity cannot be queried safely, four-runner liveness is not a hard scale prerequisite, the AWS observer role requires mutation rights, or the natural corpus fails to demonstrate genuine residual pressure.

## Completion Truth

EC2 success means `CAPACITY_PRESSURE_RECONCILER = PROVEN_DRY_RUN`. It proves wake -> fresh state -> deterministic decision, including safe duplicate/missing-event behavior. It creates **zero** elastic capacity and does not authorize `PROVISION_ONE` in production.