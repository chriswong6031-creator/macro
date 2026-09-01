# CI EC2 Pressure Reconciler Dry-Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert real GitHub `workflow_job` queue pressure into a serialized, explainable **dry-run** capacity decision while provisioning remains disabled, proving duplicate/delayed/missing webhooks cannot change correctness and that degraded local capacity, bad/unknown main integrity, stale execution profile, or an existing burst effect always refuses scale-out.

**Architecture:** A low-authority GitHub App sends `workflow_job` webhooks to an AWS Lambda Function URL. Lambda verifies GitHub HMAC, filters only eligible queued trusted-pack hints, and dispatches `ci-capacity-reconcile.yml@main` only when no reconcile run is already queued/in progress. Lambda stores no cursor/job state and has no EC2 permission. The GitHub-hosted reconcile workflow serializes on one Actions concurrency group, then fresh-reads current `main`, the accepted #6637 integrity context, queued trusted-pack jobs, current runner-group inventory, current four-runner liveness and AWS burst inventory. A pure classifier emits `NO_SCALE`, `WOULD_PROVISION_ONE`, `REFUSED`, or `EFFECT_UNKNOWN`. EC2 never calls `RunInstances`, `TerminateInstances`, JIT generation, runner mutation, or production routing.

**Tech Stack:** GitHub App webhooks, AWS Lambda Python 3.12, Lambda Function URL, AWS Secrets Manager, CloudFormation, GitHub Actions workflow dispatch/concurrency, GitHub REST API, AWS EC2 read-only API, Python dataclasses/pytest.

**Spec:** `docs/superpowers/specs/2026-09-01-ci-elastic-pressure-capacity-design.md`.

## Global Constraints

- Do not START until #6717, C3 four-slot production promotion, L3 immutable execution profile, EC1 diagnostic JIT substrate, and #6637 main-integrity source are Sol-accepted on current `main`.
- EC2 has zero runner/EC2 capacity mutation: no `RunInstances`, `TerminateInstances`, `generate-jitconfig`, runner-group/label mutation, or production workflow routing.
- GitHub Actions remains job scheduler/queue/assignment owner. Webhook is transport only; no persistent cursor, queue mirror or completion inference.
- Every reconcile fresh-reads GitHub/AWS after acquiring concurrency. Duplicate, delayed, out-of-order or missing webhook delivery cannot change decision correctness.
- Wake Lambda has zero EC2 permission. Reconcile AWS role has only `ec2:DescribeInstances`.
- Wake GitHub App is distinct from EC1 registrar App; permissions are repository `Actions: write` + metadata only.
- Webhook secret/App private key live only in AWS Secrets Manager; candidate/self-hosted jobs never receive them.
- Initial calibration hypothesis is queue age >=90s with at least one eligible queued trusted pack and all four accepted persistent runners online/busy. It is not EC3 authority until EC2 corpus calibrates it.
- If #6637 does not expose one accepted exact-main machine-queryable integrity context at EC2 START, STOP. Do not create a second health check.
- Expected persistent set must be exactly `pc-ci-1..4`, all online; any missing/offline member => `REFUSED_LOCAL_POOL_DEGRADED`. Any idle persistent member => `NO_SCALE`.
- Main integrity red/unknown, wrong execution profile, provider read ambiguity, existing burst resource, or malformed/incomplete snapshot refuses scale.
- Time-of-day is context only. No second provider/scheduler/queue DB/retry ledger/runner registry/proof store/capacity DB/semantic gate.

---

### Task 1: Define the immutable pressure snapshot and pure decision matrix

**Files:**
- Create: `scripts/ci_capacity_reconcile.py`
- Create: `config/ci_capacity_policy.v1.json`
- Create: `tests/test_ci_capacity_reconcile.py`

**Interfaces:**
- Snapshot schema: `mastermind.ci_capacity_snapshot.v1`.
- Policy schema: `mastermind.ci_capacity_policy.v1`.
- Pure API: `classify(snapshot, policy) -> CapacityDecision`.

- [ ] **Step 1: Write the complete RED decision matrix**

Use immutable types:

```python
@dataclass(frozen=True)
class QueuedJob:
    job_id: int
    run_id: int
    run_attempt: int
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
    scale_decision: str
    reason: str
    eligible_queue_depth: int
    oldest_eligible_queue_age_seconds: float | None
```

Test at minimum:

```python
assert classify(healthy(), policy).code == "WOULD_PROVISION_ONE"
assert classify(replace(healthy(), persistent_idle=("pc-ci-4",)), policy).code == "NO_SCALE"
assert classify(replace(healthy(), persistent_online=("pc-ci-1","pc-ci-2","pc-ci-3")), policy).code == "REFUSED_LOCAL_POOL_DEGRADED"
assert classify(replace(healthy(), main_integrity="red"), policy).code == "REFUSED_MAIN_INTEGRITY_RED"
assert classify(replace(healthy(), main_integrity="unknown"), policy).code == "REFUSED_MAIN_INTEGRITY_UNKNOWN"
assert classify(replace(healthy(), burst_instances=("i-123",)), policy).code == "NO_SCALE_BURST_PRESENT"
assert classify(replace(healthy(), provider_state="effect_unknown"), policy).code == "EFFECT_UNKNOWN"
```

Also test queue-age boundaries 89.999/90.0, future/malformed timestamps, duplicate runner names, runner both idle/busy, wrong profile, wrong job name/labels, provider unavailable, multiple burst resources and invalid snapshot set relationships.

- [ ] **Step 2: Confirm RED**

```bash
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py
```

- [ ] **Step 3: Implement closed policy and validation**

Initial `config/ci_capacity_policy.v1.json`:

```json
{
  "schema": "mastermind.ci_capacity_policy.v1",
  "repository": "mastermindx-market-intelligence/macro",
  "expected_persistent_runners": ["pc-ci-1", "pc-ci-2", "pc-ci-3", "pc-ci-4"],
  "diagnostic_burst_label": "ci-linux-burst-canary",
  "production_label": "ci-linux",
  "max_burst_instances": 1,
  "min_oldest_queue_age_seconds": 90,
  "min_eligible_queue_depth": 1,
  "mode": "dry_run"
}
```

No mutable count/cursor belongs in policy.

Decision precedence is exact:

1. validate identities/set consistency/timestamps;
2. provider `effect_unknown` => `EFFECT_UNKNOWN`;
3. main red/unknown => refuse;
4. expected persistent set not exactly online => local-pool degraded refusal;
5. profile mismatch => refuse;
6. multiple burst resources/runners => conflict refusal;
7. one burst resource/runner => no scale;
8. any persistent idle => no scale;
9. no eligible queue => no scale;
10. queue depth/age below threshold => no scale;
11. otherwise `WOULD_PROVISION_ONE`.

- [ ] **Step 4: Prove/commit**

```bash
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py
git diff --check
git add scripts/ci_capacity_reconcile.py config/ci_capacity_policy.v1.json tests/test_ci_capacity_reconcile.py
git commit -m "ci: define fail-closed capacity classifier"
```

---

### Task 2: Collect fresh GitHub/AWS snapshot truth without durable state

**Files:**
- Modify: `scripts/ci_capacity_reconcile.py`
- Create: `tests/test_ci_capacity_snapshot.py`
- Modify at START: `config/ci_capacity_policy.v1.json`

**Interfaces:**
- CLI: `snapshot --repository mastermindx-market-intelligence/macro --output snapshot.json`.
- GitHub: current main/checks, Actions runs/jobs, existing `macro-home-canary` runners.
- AWS: `DescribeInstances` tagged `MastermindRole=ci-burst`.

- [ ] **Step 1: Write RED API-fixture tests**

Fixtures cover queued/in-progress CI runs, exact `trusted-ci / trusted-executor-pack-N` jobs, labels, four persistent runners, diagnostic burst runner, current-main integrity context and AWS instance states/tags.

Eligible demand requires all:

```text
status == queued
name matches ^trusted-ci / trusted-executor-pack-[0-9]+$
labels contain ci-linux
run belongs to this repository's ordinary trusted route
```

Non-CI/similarly named payload text does not count.

- [ ] **Step 2: Freeze the real #6637 integrity context at EC2 START**

Fresh-read accepted #6637 implementation. If it has no stable exact-main context/interface, STOP. Otherwise add exact key:

```json
"main_integrity_check": "<the exact accepted context from current #6637>"
```

The worker must replace the angle-bracket description with the literal observed context in the same first implementation commit and tests must pin that literal; no symbolic value may survive a commit.

- [ ] **Step 3: Implement bounded GitHub reads**

Every request uses API version `2022-11-28`, bounded pagination and hard failure on partial inventory. Sequence:

1. resolve current main SHA;
2. read the configured #6637 integrity check for that exact SHA;
3. list recent queued/in-progress `ci` runs;
4. list jobs and exact eligible queued trusted packs, resolving current run attempt;
5. list org runner groups, require exactly one `macro-home-canary`;
6. list its runners, classify exact persistent names and `ci-burst-*` runners.

Use the workflow's repository token for repository reads and the existing EC1 registrar App token only for runner-group reads. No runner mutation endpoint is called in EC2.

- [ ] **Step 4: Implement AWS read-only collection**

Only:

```bash
aws ec2 describe-instances --region us-east-1 \
  --filters Name=tag:MastermindRole,Values=ci-burst \
            Name=instance-state-name,Values=pending,running,stopping,stopped,shutting-down
```

Classify exact reconcile/profile tags. Multiple nonterminal resources are visible conflict evidence.

- [ ] **Step 5: Preserve unknown as unknown**

GitHub pagination failure, group ambiguity, main-check ambiguity, malformed time, or AWS read failure => typed snapshot error and `REFUSED_SNAPSHOT_INCOMPLETE`; never empty queue/provider available.

- [ ] **Step 6: Prove/commit**

```bash
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py tests/test_ci_capacity_snapshot.py
git diff --check
git add scripts/ci_capacity_reconcile.py tests/test_ci_capacity_snapshot.py config/ci_capacity_policy.v1.json
git commit -m "ci: collect fresh capacity truth"
```

---

### Task 3: Build the stateless webhook wake adapter

**Files:**
- Create: `ops/runner-cloud/aws/ci-burst-wake-stack.yml`
- Create: `ops/runner-cloud/aws/wake/handler.py`
- Create: `ops/runner-cloud/aws/wake/requirements.in`
- Create: `ops/runner-cloud/aws/wake/requirements.lock`
- Create: `tests/test_ci_burst_wake.py`

**Interfaces:**
- Input: GitHub `workflow_job` webhook on Lambda Function URL.
- Secrets: `/mastermind/ci-burst/wake/webhook-secret`, `/mastermind/ci-burst/wake/github-app-private-key`.
- Dispatch: `.github/workflows/ci-capacity-reconcile.yml@main`.

- [ ] **Step 1: Write RED webhook tests**

Prove invalid/missing HMAC => 401/no GitHub call; non-workflow-job/non-queued/wrong repo/wrong job/wrong labels => ignored 202; active reconcile => no dispatch; eligible wake => one dispatch; duplicate wake correctness still relies on workflow fresh-state/concurrency; handler has no EC2/local/sqlite/DynamoDB/SQS state.

- [ ] **Step 2: Implement HMAC before semantic parsing**

```python
expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
if not hmac.compare_digest(expected, supplied):
    return response(401, "invalid signature")
```

Then bounded JSON parse; require repo exact, `action == "queued"`, exact job-name regex and `ci-linux` label. Payload is wake hint only.

- [ ] **Step 3: Lock Lambda dependencies and mint Wake-App token**

`requirements.in` contains exactly:

```text
PyJWT==2.10.1
cryptography==45.0.7
```

On the exact Linux/Python-3.12 build environment:

```bash
python3.12 -m pip download --only-binary=:all: -d /tmp/ci-burst-wake-wheels -r ops/runner-cloud/aws/wake/requirements.in
python3.12 -m pip hash /tmp/ci-burst-wake-wheels/* | \
  python3.12 scripts/render_hashed_requirements.py \
    --requirements-in ops/runner-cloud/aws/wake/requirements.in \
    --wheel-dir /tmp/ci-burst-wake-wheels \
    --output ops/runner-cloud/aws/wake/requirements.lock
python3.12 -m pip install --require-hashes -r ops/runner-cloud/aws/wake/requirements.lock -t /tmp/ci-burst-wake-package
```

If `scripts/render_hashed_requirements.py` does not exist at EC2 START, create it inside this Task with focused tests in `tests/test_ci_burst_wake.py`; it is a packaging helper, not a runtime dependency/cache authority. It must preserve exact input package versions and output every downloaded wheel hash deterministically. No unhashed Lambda dependency may ship.

Use App private key from Secrets Manager to mint JWT/install token. Only GitHub calls:

- GET reconcile workflow queued runs;
- GET reconcile workflow in-progress runs;
- POST reconcile workflow dispatch.

Wake App permission: repository `Actions: write` + metadata only.

- [ ] **Step 4: Implement wake stack**

CloudFormation creates only secret containers, Lambda role with CloudWatch Logs + GetSecretValue on those two secrets, Python 3.12 Lambda reserved concurrency 1, Function URL `AuthType: NONE`. No VPC, EC2, DynamoDB, SQS, EventBridge scheduler or Step Functions.

- [ ] **Step 5: Prove/commit**

```bash
python3.12 -m pytest -q tests/test_ci_burst_wake.py
git diff --check
git add ops/runner-cloud/aws/ci-burst-wake-stack.yml ops/runner-cloud/aws/wake \
  tests/test_ci_burst_wake.py
git commit -m "ci: add stateless workflow-job wake adapter"
```

---

### Task 4: Build the serialized GitHub-hosted dry-run workflow

**Files:**
- Create: `.github/workflows/ci-capacity-reconcile.yml`
- Create: `tests/test_ci_capacity_workflow.py`
- Modify: `ops/runner-cloud/aws/ci-burst-wake-stack.yml`

**Interfaces:**
- Trigger: `workflow_dispatch` only.
- Concurrency: `group: ci-capacity-reconcile`, `cancel-in-progress: false`.
- Artifact: `ci-capacity-decision`, 14-day retention.

- [ ] **Step 1: Write RED workflow-authority tests**

Require workflow_dispatch only, `ubuntu-latest`, no candidate `uses: ./`, no self-hosted job, no Run/Terminate/JIT text, and:

```yaml
concurrency:
  group: ci-capacity-reconcile
  cancel-in-progress: false
permissions:
  actions: read
  checks: read
  contents: read
  id-token: write
```

- [ ] **Step 2: Add read-only AWS observer role**

Trust only:

```text
repo:mastermindx-market-intelligence/macro:environment:ci-burst-reconcile
```

Permission exactly `ec2:DescribeInstances`; no pass-role/run/terminate/IAM/Secrets/SSM/log mutation.

- [ ] **Step 3: Implement workflow**

One hosted job/environment `ci-burst-reconcile`: checkout main; Python 3.12.13; mint registrar App token for runner-group read; AWS OIDC observer role; collect `snapshot.json`; classify to `decision.json`; upload both and write summary. `REFUSED`/`NO_SCALE` are successful observations; malformed/incomplete collection is workflow failure.

- [ ] **Step 4: Prove/commit**

```bash
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py tests/test_ci_capacity_snapshot.py \
  tests/test_ci_capacity_workflow.py tests/test_ci_burst_wake.py
git diff --check
git add .github/workflows/ci-capacity-reconcile.yml tests/test_ci_capacity_workflow.py \
  ops/runner-cloud/aws/ci-burst-wake-stack.yml
git commit -m "ci: add serialized capacity dry run"
```

---

### Task 5: Deploy wake transport, accrue corpus, and freeze EC3 threshold

**Files:**
- Modify: `docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md`
- Modify: `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
- Create: `agentos/handoffs/CI-EC2-PRESSURE-RECONCILER-2026-09-01.md`
- Create: `research/CI_ELASTIC_EC2_DRY_RUN_RESULTS_2026_09.md`
- Modify after corpus: `config/ci_capacity_policy.v1.json`
- Modify after corpus: `tests/test_ci_capacity_reconcile.py`

- [ ] **Step 1: Stop for admin deployment authority**

Fresh-census EC1 AWS stack, four-runner live fleet, group, Apps, #6637 interface and path collisions. Deploy merged source only.

- [ ] **Step 2: Create/install Wake App and deploy stack**

Create `Mastermind CI Capacity Wake` with Actions write, `workflow_job` subscription only, Macro install only. Deploy `mastermind-ci-burst-wake`; place webhook secret/App private key directly into AWS Secrets Manager. Configure App webhook URL/secret; never transport secret values through source/chat/Slack.

- [ ] **Step 3: Configure `ci-burst-reconcile` environment**

Add observer-role ARN variable and EC1 registrar App ID/private-key secret for runner-group read. Protect as current CI-control environment policy requires.

- [ ] **Step 4: Prove wake negative controls**

Invalid signature refused; unrelated job ignored; eligible queued hint dispatches once when no reconcile active; duplicate delivery while active produces no second active reconcile; Lambda has no EC2 authority; decision remains dry-run.

- [ ] **Step 5: Accrue at least 30 natural observations**

Require >=10 NO_SCALE; >=5 WOULD_PROVISION_ONE if natural traffic produces them; >=3 refusal/negative-control observations; simultaneous PR windows; >=1 independent render window; duplicate/delayed redelivery evidence. Record queue depth/age, local state, integrity/profile/provider, decision, selected jobs/packs and estimated SLO relevance.

If fewer than five genuine WOULD_PROVISION_ONE observations after 14 days, do not manufacture load: elastic production demand is unproven and EC3 stays held.

- [ ] **Step 6: Compute and commit one exact EC3 threshold**

Use a deterministic grid over integer seconds 30..300 inclusive in 15-second steps. For each candidate threshold replay the full EC2 corpus and compute:

- `capture_rate`: fraction of observed p95-risk pressure windows that would yield WOULD_PROVISION_ONE;
- `useless_rate`: fraction of would-provision decisions where a persistent slot became idle within 30 seconds without burst;
- median and p95 queue age at decision.

Choose the **highest** threshold satisfying `capture_rate >= 0.90` and `useless_rate <= 0.20`; tie-break by higher threshold. If no threshold satisfies both, EC3 is NO-GO and policy remains 90/dry-run.

If a threshold qualifies, write its literal integer into `min_oldest_queue_age_seconds` while keeping `mode: dry_run`; add field `calibration_corpus_sha256` with SHA-256 of the canonical results JSON embedded in `research/CI_ELASTIC_EC2_DRY_RUN_RESULTS_2026_09.md`. Add a test asserting policy threshold/corpus SHA equal the research artifact's accepted values. No symbolic or provisional threshold survives the commit.

- [ ] **Step 7: Final proof/return**

```bash
python3.12 scripts/agentos.py validate
python3.12 -m pytest -q tests/test_ci_capacity_reconcile.py tests/test_ci_capacity_snapshot.py \
  tests/test_ci_burst_wake.py tests/test_ci_capacity_workflow.py
git diff --check
```

Independent review exact head. Return DRAFT/HOLD-FOR-SOL with corpus and either `GO_EC3` or `NO_GO_ELASTIC_DEMAND`; no provisioning/self-merge.

## Stop Condition

Stop before EC3 if Wake App needs broader permission, webhook validation cannot close, duplicate wakes bypass serialized fresh-state reads, #6637 integrity is not safely queryable, local four-runner liveness is not a hard prerequisite, observer role needs mutation rights, or the corpus/threshold ruler produces NO-GO.

## Completion Truth

EC2 PASS is `CAPACITY_PRESSURE_RECONCILER = PROVEN_DRY_RUN` plus literal calibrated policy/corpus identity. It creates zero elastic capacity and does not authorize production `PROVISION_ONE` until a fresh EC3 carrier.