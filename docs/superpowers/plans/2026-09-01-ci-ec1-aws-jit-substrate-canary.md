# CI EC1 AWS JIT Substrate Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove one second-failure-domain, one-job GitHub Actions JIT runner can execute one non-destructive diagnostic CI pack with exact semantic parity, external logs, bounded AWS effect reconciliation, and zero production `ci-linux` eligibility.

**Architecture:** AWS EC2 is the first EC1 substrate because GitHub OIDC removes long-lived AWS credentials and EC2 `RunInstances` client tokens give native idempotent creation that matches Mastermind's `EFFECT_UNKNOWN` law. EC1 remains diagnostic only: a protected GitHub-hosted launcher creates one isolated `c7i.2xlarge` from an immutable AMI, obtains one JIT configuration through a dedicated GitHub App, and boots a runner labeled only `ci-linux-burst-canary` in the existing `macro-home-canary` group. A main-defined diagnostic workflow executes one selected pack, compares its semantic fragment to a hosted control, uploads existing receipt/timing evidence, and the one-job runner powers off. No webhook scaler or production `ci-linux` route exists in EC1.

**Tech Stack:** GitHub Actions, GitHub JIT self-hosted-runner REST API, AWS EC2 `us-east-1`, CloudFormation, Packer 1.16.0 HCL, GitHub OIDC, AWS CLI v2, Bash/Python 3, existing CI pack/canary receipt/comparator tooling, systemd, nftables, CloudWatch Logs.

**Spec:** `docs/superpowers/specs/2026-09-01-ci-elastic-pressure-capacity-design.md`.

## Global Constraints

- Do not start until #6717 is merged, C3 four-slot production capacity is Sol-accepted, and L3 immutable dependency/execution profile is `PROVEN_LIVE` on persistent Linux/x86_64.
- EC1 is a fresh operation/carrier; never reuse C3 or #6628.
- AWS account setup, GitHub App install, GitHub Environment configuration, runner-group selected-workflow mutation and live canary launch are privileged effects with explicit receipts.
- Region is `us-east-1`; runtime instance is exactly `c7i.2xlarge`; one encrypted 150-GiB gp3 root volume; one instance maximum.
- EC1 runner carries `self-hosted`, `Linux`, `X64`, `ci-linux-burst-canary`; never `ci-linux`, `ci-linux-canary`, or `render-linux`.
- EC1 diagnostic workflow is `workflow_dispatch` from protected `main` and is the sole new selected workflow added to `macro-home-canary`.
- Candidate process receives no AWS provisioning authority, no registrar App token/private key, no home/private-network route, and no persistent JIT bytes.
- Runtime instance profile is CloudWatch-log-only; `macroci` is blocked from IMDS before registration. IMDSv2 required, IPv6 IMDS disabled, metadata tags disabled.
- Runner/bootstrap logs are exported to CloudWatch before EC1 acceptance. They are diagnostic only and never substitute semantic fragments.
- Runtime instance uses `InstanceInitiatedShutdownBehavior=terminate`. The JIT service has `SuccessAction=poweroff` and `FailureAction=poweroff`. A root-owned **210-minute** hard-stop is the final backstop because current trusted-pack timeout is 180 minutes plus 30-minute provisioning/teardown margin.
- Provider-create ambiguity uses deterministic EC2 `ClientToken` + tags; no blind second create/provider failover.
- Packer image building uses a separate OIDC role/environment from runtime canary launch. Build-time temporary SSH ingress is limited to the exact GitHub-hosted builder public `/32` and is deleted with the Packer build; runtime security group has no ingress.
- No webhook, autoscaling policy, queue classifier, production `ci-linux`, production concurrency edit, second provider, ARC/Scale Set Client, scheduler, queue, registry, proof store or retry service in EC1.

---

### Task 1: Freeze AWS and GitHub privileged interfaces

**Files:**
- Create: `ops/runner-cloud/aws/ci-burst-stack.yml`
- Create: `ops/runner-cloud/aws/README.md`
- Create: `tests/test_ci_burst_aws_stack.py`
- Modify: `.github/runner-policy.yml`
- Modify: `scripts/check_runner_policy.py`
- Modify: `tests/test_runner_policy.py`

**Interfaces:**
- CloudFormation parameters: `GitHubOidcProviderArn`, `GitHubRepository` default `mastermindx-market-intelligence/macro`.
- Outputs: `BurstImageBuilderRoleArn`, `BurstCanaryRoleArn`, `BurstSubnetId`, `BurstSecurityGroupId`, `BurstInstanceProfileName`, `BurstLogGroupName`.
- New diagnostic label `ci-linux-burst-canary`, declared pending until live proof.

- [ ] **Step 1: Write RED stack/policy tests**

Require:

```python
assert stack["Parameters"]["GitHubRepository"]["Default"] == "mastermindx-market-intelligence/macro"
assert stack["Resources"]["BurstLogGroup"]["Properties"]["RetentionInDays"] == 14
assert stack["Resources"]["BurstSecurityGroup"]["Properties"].get("SecurityGroupIngress", []) == []
```

Require instance role actions exactly `logs:CreateLogStream`, `logs:PutLogEvents`. Require OIDC subjects exactly:

```text
repo:mastermindx-market-intelligence/macro:environment:ci-burst-image
repo:mastermindx-market-intelligence/macro:environment:ci-burst-admin
```

`tests/test_runner_policy.py` requires pending `ci-linux-burst-canary` with no live carrier, forbids it on schedules/forks/render/production trusted pack, and preserves production persistent `ci-linux` carriers.

- [ ] **Step 2: Confirm RED**

```bash
python3.12 -m pytest -q tests/test_ci_burst_aws_stack.py tests/test_runner_policy.py -k "burst or runner_policy"
```

- [ ] **Step 3: Implement runtime network, logging and roles**

CloudFormation creates:

- VPC `10.77.0.0/24`, subnet `10.77.0.0/26`, DNS enabled, internet gateway/route, no peering/VPN/Tailscale;
- runtime SG no ingress; egress TCP/443, TCP+UDP/53, UDP/123 only;
- `/mastermind/ci-burst` log group, 14-day retention;
- runtime instance role/profile with log-stream create/put only;
- `BurstCanaryRole` trusted only by `ci-burst-admin`, allowed exact bounded `RunInstances`, `DescribeInstances`, tagged `TerminateInstances`, and `iam:PassRole` only the log-only EC2 instance role;
- `BurstImageBuilderRole` trusted only by `ci-burst-image`, allowed the Packer build operations: EC2 describe calls; tagged build `RunInstances`/Stop/Terminate; CreateImage/DeregisterImage; Create/DeleteSnapshot; Create/Delete/Authorize/Revoke temporary SecurityGroup; Create/Delete temporary KeyPair; CreateTags; ModifyImageAttribute; and no runner/GitHub/Secrets Manager authority.

Both mutation roles are region-bounded to `us-east-1` and require stack/build role tags wherever AWS supports conditions.

- [ ] **Step 4: Declare diagnostic label only**

Add pending `ci-linux-burst-canary` without live carrier/pool promotion. `check_runner_policy.py` rejects accidental production use, render/fork/scheduled use, `ci-linux` on EC1 diagnostic runner, or a fifth persistent slot hidden under this label.

- [ ] **Step 5: Prove and commit**

```bash
python3.12 -m pytest -q tests/test_ci_burst_aws_stack.py tests/test_runner_policy.py
python3.12 scripts/check_runner_policy.py
git diff --check
git add ops/runner-cloud/aws/ci-burst-stack.yml ops/runner-cloud/aws/README.md \
  tests/test_ci_burst_aws_stack.py .github/runner-policy.yml scripts/check_runner_policy.py \
  tests/test_runner_policy.py
git commit -m "ci: define isolated AWS burst substrate"
```

---

### Task 2: Build an immutable JIT runner AMI

**Files:**
- Create: `ops/runner-cloud/aws/packer/ci-burst.pkr.hcl`
- Create: `ops/runner-cloud/aws/scripts/provision-image.sh`
- Create: `ops/runner-cloud/aws/scripts/run-jit-once.sh`
- Create: `ops/runner-cloud/aws/scripts/hard-stop.sh`
- Create: `ops/runner-cloud/aws/cloudwatch-agent.json`
- Create: `ops/runner-cloud/aws/image-versions.json`
- Create: `tests/test_ci_burst_image.py`
- Create: `.github/workflows/ci-burst-image.yml`

**Interfaces:**
- Image manifest schema `mastermind.ci_burst_image.v1`.
- GitHub Actions runner fixed initially `2.337.0`, Linux x64 archive SHA-256 `70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613`.
- Packer fixed `1.16.0`; setup action pinned `hashicorp/setup-packer@ce93c3c08a6c2ff2275bf4b54ff0d9a75f6c9789`.
- AMI tags: `MastermindCiBurstImage=true`, `ExecutionProfileId`, `SourceCommit`, `RunnerVersion`.

- [ ] **Step 1: Write RED image tests**

Require exact version/hash JSON, Canonical Ubuntu 24.04 amd64 owner `099720109477`, encrypted 150-GiB gp3 root, source/built AMI receipt, no pre-registered runner/JIT/token bytes, 210-minute hard-stop, and systemd JIT service `SuccessAction=poweroff`/`FailureAction=poweroff`.

Require Packer's temporary build SG CIDR comes from explicit variable `builder_cidr`; runtime SG is never used for SSH.

- [ ] **Step 2: Confirm RED**

```bash
python3.12 -m pytest -q tests/test_ci_burst_image.py
```

- [ ] **Step 3: Implement Packer source**

Core source:

```hcl
variable "builder_cidr" { type = string }
source "amazon-ebs" "ci_burst" {
  region        = "us-east-1"
  instance_type = "c7i.2xlarge"
  ssh_username  = "ubuntu"
  temporary_security_group_source_cidrs = [var.builder_cidr]
  source_ami_filter {
    filters = {
      name = "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"
      root-device-type = "ebs"
      virtualization-type = "hvm"
      architecture = "x86_64"
    }
    owners = ["099720109477"]
    most_recent = true
  }
  launch_block_device_mappings {
    device_name = "/dev/sda1"
    volume_size = 150
    volume_type = "gp3"
    encrypted = true
    delete_on_termination = true
  }
}
```

`provision-image.sh` installs nftables, CloudWatch Agent, Git/jq prerequisites, verified runner archive, `macroci`, current main-owned Git/dependency cache helpers under `/usr/local/libexec` with helper SHA manifest, cache roots, JIT systemd unit and 210-minute timer. No runner registration or secret is baked.

- [ ] **Step 4: Implement one-use JIT/metadata fence**

`run-jit-once.sh` as `macroci` validates `/run/mastermind-ci/jit.config` owner/mode/size, reads it, unlinks it before any GitHub registration, fsyncs parent, validates helper/profile/cache identities, then:

```bash
exec /opt/actions-runner/run.sh --jitconfig "$jit"
```

Runtime image loads nftables before JIT service:

```text
meta skuid macroci ip daddr 169.254.169.254 reject
```

JIT service includes:

```ini
SuccessAction=poweroff
FailureAction=poweroff
```

Hard-stop service fires at 210 minutes only.

- [ ] **Step 5: Implement pinned image-build workflow**

`.github/workflows/ci-burst-image.yml`: `workflow_dispatch` only, environment `ci-burst-image`, `id-token: write`. Pin:

```yaml
- uses: aws-actions/configure-aws-credentials@cbe3b392738ccf3f987d68400dafcf4b0624a56c
- uses: hashicorp/setup-packer@ce93c3c08a6c2ff2275bf4b54ff0d9a75f6c9789
  with:
    version: "1.16.0"
```

Resolve the builder public CIDR:

```bash
BUILDER_IP=$(curl -fsS https://checkip.amazonaws.com | tr -d '\n')
test -n "$BUILDER_IP"
packer init ops/runner-cloud/aws/packer/ci-burst.pkr.hcl
packer validate -var "builder_cidr=${BUILDER_IP}/32" ops/runner-cloud/aws/packer/ci-burst.pkr.hcl
packer build -var "builder_cidr=${BUILDER_IP}/32" ops/runner-cloud/aws/packer/ci-burst.pkr.hcl
```

After build, verify no tagged build instance, temporary SG or temporary key pair remains. Receipt includes source/built AMI, repo commit, execution profile, Packer/runner versions and helper manifest SHA; no AWS credentials.

- [ ] **Step 6: Prove/commit**

```bash
python3.12 -m pytest -q tests/test_ci_burst_image.py
git diff --check
git add ops/runner-cloud/aws/packer/ci-burst.pkr.hcl ops/runner-cloud/aws/scripts \
  ops/runner-cloud/aws/cloudwatch-agent.json ops/runner-cloud/aws/image-versions.json \
  tests/test_ci_burst_image.py .github/workflows/ci-burst-image.yml
git commit -m "ci: build sealed AWS JIT runner image"
```

---

### Task 3: Implement deterministic AWS/JIT effect control

**Files:**
- Create: `scripts/ci_burst_aws.py`
- Create: `tests/test_ci_burst_aws.py`

**Interfaces:**
- Pure: `reconcile_id`, `client_token`, `runner_name`, `build_run_instances_args`, `classify_instances`.
- CLI: `launch`, `wait-online`, `reconcile`, `terminate`.
- JIT endpoint: `POST /orgs/mastermindx-market-intelligence/actions/runners/generate-jitconfig`.

- [ ] **Step 1: Write RED deterministic identity/effect tests**

Require stable bounded IDs, changed attempt/profile => different ID, one matching instance => `PRESENT`, >1 => `CONFLICT`, absent => `ABSENT`, AWS timeout => `EFFECT_UNKNOWN` followed by inventory read, and local refusal if same client token would be paired with changed launch parameters.

- [ ] **Step 2: Implement exact launch args**

One instance only:

```text
--count 1
--instance-type c7i.2xlarge
--instance-initiated-shutdown-behavior terminate
--metadata-options HttpTokens=required,HttpPutResponseHopLimit=1,HttpEndpoint=enabled,HttpProtocolIpv6=disabled,InstanceMetadataTags=disabled
```

Use exact AMI/subnet/runtime SG/profile, encrypted 150-GiB gp3 root, deterministic client token, tags `MastermindRole=ci-burst`, reconcile/profile/run IDs. Any count/region/type/identity drift refuses before AWS.

- [ ] **Step 3: Implement closed JIT API client**

Use Python `urllib.request`, bearer env `CI_BURST_GITHUB_TOKEN`, API version `2022-11-28`. Discover exactly one runner group named `macro-home-canary`, then request:

```json
{
  "name": "ci-burst-stable-id",
  "runner_group_id": 123,
  "labels": ["ci-linux-burst-canary"],
  "work_folder": "_work"
}
```

The integer above is fixture shape only; live group ID is fresh-discovered. Parse only runner ID/name + non-empty encoded JIT config. Never print/persist JIT bytes in receipts.

- [ ] **Step 4: Implement ambiguity reconciliation**

Before create, describe exact tagged effect. One existing resource => reuse/reconcile; >1 => conflict; absent => issue one idempotent `RunInstances`. On client timeout/error immediately describe exact tags; no second create in that command and no provider failover.

- [ ] **Step 5: Prove/commit**

```bash
python3.12 -m pytest -q tests/test_ci_burst_aws.py
git diff --check
git add scripts/ci_burst_aws.py tests/test_ci_burst_aws.py
git commit -m "ci: add replay-safe AWS JIT effect control"
```

---

### Task 4: Build the dispatch-only burst parity workflow

**Files:**
- Create: `.github/workflows/ci-burst-canary.yml`
- Create: `tests/test_ci_burst_workflow.py`
- Modify: `.github/runner-policy.yml`
- Modify: `scripts/check_runner_policy.py`
- Modify: `tests/test_runner_policy.py`

**Interfaces:**
- Inputs: `pr_number`; optional `pack` integer-like string, otherwise current selector chooses one non-empty pack.
- Jobs: `plan`, `hosted-control`, `launch-burst`, `burst-pack`, `compare`, `teardown`, `summary`.
- `burst-pack` runs in group `macro-home-canary`, label `ci-linux-burst-canary` only.

- [ ] **Step 1: Write RED workflow-security tests**

Require workflow_dispatch only; static burst label/group; same plan artifact for hosted/burst; same pack; existing comparator; hosted teardown always; no AWS/App credential on self-hosted job; fork refusal; main-owned control; no merge controller/production labels.

- [ ] **Step 2: Implement exact plan/hosted control**

Use current main control, `resolve_ci_canary_ref.py`, one `gate: code` plan, one selected pack, exact candidate/base/head/tested SHA. Hosted control uses Python 3.12.13 + Node 20 and existing semantic/receipt path.

- [ ] **Step 3: Implement launch job with separate protected credentials**

Environment `ci-burst-admin`; pin AWS credentials action. Mint dedicated registrar token using:

```yaml
- uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1
  id: registrar
  with:
    app-id: ${{ vars.CI_BURST_REGISTRAR_APP_ID }}
    private-key: ${{ secrets.CI_BURST_REGISTRAR_PRIVATE_KEY }}
    owner: mastermindx-market-intelligence
```

Registrar App has organization self-hosted-runners write plus metadata only. Generate one JIT config, launch one VM, then wait up to 10 minutes for exact online/idle runner **before** `launch-burst` completes and `burst-pack` queues.

- [ ] **Step 4: Bootstrap without JIT leakage**

Root cloud-init with shell tracing off writes JIT config to `/run/mastermind-ci/jit.config` `macroci:macroci` mode `0400`, starts log/IMDS fences, validates AMI/profile/helper/cache identities, root-updates current public Git/dependency caches before eligibility, then starts JIT unit. Tests forbid `echo`/trace/JIT receipt leakage.

- [ ] **Step 5: Execute/compare/teardown**

`burst-pack` downloads exact same plan/control, verifies profile/runner name, setup Python 3.12.13/Node 20, executes current pack, emits existing fragment/timing/receipt. `compare` uses existing comparator. `teardown` fresh-reads GitHub/AWS and terminates only exact tagged idle/terminal effect after burst job; normal service exit already powers off/terminates. 210-minute hard-stop is last resort.

- [ ] **Step 6: Prove/commit**

```bash
python3.12 -m pytest -q tests/test_ci_burst_workflow.py tests/test_runner_policy.py \
  tests/test_ci_canary_tools.py tests/test_ci_burst_aws.py
python3.12 scripts/check_runner_policy.py
git diff --check
git add .github/workflows/ci-burst-canary.yml tests/test_ci_burst_workflow.py \
  .github/runner-policy.yml scripts/check_runner_policy.py tests/test_runner_policy.py
git commit -m "ci: add dispatch-only AWS burst canary"
```

---

### Task 5: Privileged bootstrap and one real JIT canary

**Files after proof:**
- Modify: `docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md`
- Modify: `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
- Create: `agentos/handoffs/CI-EC1-AWS-JIT-SUBSTRATE-CANARY-2026-09-01.md`

- [ ] **Step 1: Stop for explicit admin ceremony**

Record pre-change runner-group selected workflows/runners, AWS stack absence/presence/OIDC provider, resources matching `MastermindRole=ci-burst`. Never request/paste JIT config/private keys.

- [ ] **Step 2: Deploy AWS stack once**

```bash
GITHUB_OIDC_PROVIDER_ARN=$(aws iam list-open-id-connect-providers \
  --query 'OpenIDConnectProviderList[].Arn' --output text | tr '\t' '\n' | \
  grep 'token.actions.githubusercontent.com$')
test "$(printf '%s\n' "$GITHUB_OIDC_PROVIDER_ARN" | sed '/^$/d' | wc -l)" -eq 1
aws cloudformation deploy --region us-east-1 --stack-name mastermind-ci-burst \
  --template-file ops/runner-cloud/aws/ci-burst-stack.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides GitHubOidcProviderArn="$GITHUB_OIDC_PROVIDER_ARN"
```

Zero/multiple provider matches => STOP; do not auto-create another OIDC provider.

- [ ] **Step 3: Configure protected environments and registrar App**

Create `ci-burst-image` with builder role variable and `ci-burst-admin` with canary role variable. Create/install `Mastermind CI Burst Registrar` with only org self-hosted-runners write + metadata. Store App private key only in `ci-burst-admin`; source never contains it.

- [ ] **Step 4: Build/attest one AMI**

Dispatch merged `ci-burst-image.yml` once. Record exact built/source AMI, runner/Packer versions, repo commit, helper manifest, dependency-lock document and execution-profile IDs; verify no temporary build resources remain.

- [ ] **Step 5: Add only the canary selected workflow**

Add exactly:

```text
mastermindx-market-intelligence/macro/.github/workflows/ci-burst-canary.yml@refs/heads/main
```

to existing `macro-home-canary`, preserving existing selected workflows. Re-read exact list/group ID.

- [ ] **Step 6: Dispatch exactly one safe candidate**

Choose same-repo PR not editing CI/runner/provider/admission paths; record exact head/base/tested SHA. Dispatch once:

```bash
gh workflow run ci-burst-canary.yml --ref main -f pr_number="$PR_NUMBER"
```

No second run while first effect nonterminal/ambiguous.

- [ ] **Step 7: EC1 PASS gate**

Require one EC2 effect; exact type/AMI/network/profile/metadata; one runner with canary label and no production/render labels; no JIT leakage; `macroci` IMDS refusal; external logs; one job only; hosted/burst SHA/plan/jobs/fragment/result parity; exact L3 profile/lock; unchanged caches; auto-deregister; instance terminated; no persistent/render route change.

- [ ] **Step 8: Durable records/review**

```bash
python3.12 scripts/agentos.py validate
python3.12 -m pytest -q tests/test_ci_burst_aws_stack.py tests/test_ci_burst_image.py \
  tests/test_ci_burst_aws.py tests/test_ci_burst_workflow.py tests/test_runner_policy.py
git diff --check
```

Independent review required. Return source PR DRAFT/HOLD-FOR-SOL; no self-merge.

## Stop Condition

Stop if AWS OIDC cannot be narrowly scoped, image building requires runtime broad credentials, registrar requires broader GitHub authority, VM exposes cloud management to `macroci`, group cannot restrict canary workflow, JIT bytes survive into candidate execution/logs, external logs fail, semantic parity fails, or another current provider owner collides.

## Completion Truth

EC1 success means `AWS_JIT_BURST_SUBSTRATE = PROVEN_DIAGNOSTIC_ONLY`. It proves one second-domain one-job diagnostic runner. It does not enable queue-driven autoscaling, production `ci-linux`, a webhook receiver, persistent cloud pool, or >1 runner.