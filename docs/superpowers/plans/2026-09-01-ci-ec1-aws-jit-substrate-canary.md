# CI EC1 AWS JIT Substrate Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove one second-failure-domain, one-job GitHub Actions JIT runner can execute one non-destructive diagnostic CI pack with exact semantic parity, external logs, bounded AWS effect reconciliation, and zero production `ci-linux` eligibility.

**Architecture:** AWS EC2 is the first EC1 substrate because GitHub OIDC removes long-lived AWS credentials and EC2 `RunInstances` client tokens give native idempotent creation that matches Mastermind's `EFFECT_UNKNOWN` law. EC1 remains diagnostic only: a protected GitHub-hosted launcher creates one isolated `c7i.2xlarge` from an immutable AMI, obtains one JIT configuration through a dedicated GitHub App, and boots a runner labeled only `ci-linux-burst-canary` in the existing `macro-home-canary` runner group. A main-defined diagnostic workflow executes one selected pack, compares its semantic fragment to a hosted control, uploads the existing receipt/timing artifacts, and then the VM terminates. No webhook scaler or production `ci-linux` route exists in this wave.

**Tech Stack:** GitHub Actions, GitHub JIT self-hosted-runner REST API, AWS EC2 `us-east-1`, CloudFormation, Packer HCL, GitHub OIDC, AWS CLI v2, Bash/Python 3, existing `run_ci_pack.py`/canary receipt/comparator tooling, systemd, nftables, CloudWatch Logs.

**Spec:** `docs/superpowers/specs/2026-09-01-ci-elastic-pressure-capacity-design.md`.

## Global Constraints

- Do not start until #6717 architecture is merged, C3 production four-slot capacity is Sol-accepted, and L3 immutable dependency/execution-profile proof is `PROVEN_LIVE` for the persistent Linux/x86_64 route.
- EC1 is a fresh operation/carrier. It does not reuse C3R-A/C3R-B/C3-PROMOTE or #6628.
- The AWS account, GitHub App installation, GitHub Environment approvals, and runner-group selected-workflow change are privileged admin effects and require their own explicit ceremony/receipt; source code alone cannot claim them.
- Initial provider region is `us-east-1`; instance type is exactly `c7i.2xlarge`; root volume is one encrypted 150-GiB gp3 EBS volume; instance count hard ceiling is one.
- The EC1 runner carries `self-hosted`, `Linux`, `X64`, and `ci-linux-burst-canary`; it must not carry `ci-linux`, `ci-linux-canary`, or `render-linux`.
- EC1 workflow is `workflow_dispatch` on protected `main` only and must be the only new selected workflow added to the existing `macro-home-canary` group.
- The candidate process receives no AWS provisioning role, no GitHub App private key/token, no home-network route, and no persistent JIT configuration bytes.
- The instance profile is log-only. The `macroci` UID is blocked from EC2 Instance Metadata Service before runner registration; IMDSv2 is required and IPv6 IMDS is disabled.
- GitHub runner application logs and bootstrap logs must leave the instance through CloudWatch Logs before production-style proof is accepted. CloudWatch evidence is diagnostic only; it never substitutes for semantic fragments.
- The VM is configured with `InstanceInitiatedShutdownBehavior=terminate` and a root-owned 45-minute hard-stop timer. One job or timeout ends the machine.
- Provider-create ambiguity is reconciled by deterministic EC2 `ClientToken` plus tags; no blind second `RunInstances` and no provider failover.
- No webhook, autoscaling policy, queue classifier, production `ci-linux`, `max-parallel` change, second provider, ARC, Runner Scale Set Client, scheduler, queue, registry, proof store, or retry service enters EC1.

---

### Task 1: Freeze AWS and GitHub privileged interfaces as source contracts

**Files:**
- Create: `ops/runner-cloud/aws/ci-burst-stack.yml`
- Create: `ops/runner-cloud/aws/README.md`
- Create: `tests/test_ci_burst_aws_stack.py`
- Modify: `.github/runner-policy.yml`
- Modify: `scripts/check_runner_policy.py`
- Modify: `tests/test_runner_policy.py`

**Interfaces:**
- CloudFormation parameters: `GitHubOidcProviderArn`, `GitHubRepository=mastermindx-market-intelligence/macro`.
- CloudFormation outputs: `BurstAdminRoleArn`, `BurstSubnetId`, `BurstSecurityGroupId`, `BurstInstanceProfileName`, `BurstLogGroupName`.
- New declared diagnostic label: `ci-linux-burst-canary`, status `pending` until live proof.

- [ ] **Step 1: Write RED stack and runner-policy tests**

In `tests/test_ci_burst_aws_stack.py`, parse the YAML and require exactly:

```python
assert stack["Parameters"]["GitHubRepository"]["Default"] == \
    "mastermindx-market-intelligence/macro"
assert stack["Resources"]["BurstLogGroup"]["Properties"]["RetentionInDays"] == 14
assert stack["Resources"]["BurstSecurityGroup"]["Properties"].get("SecurityGroupIngress", []) == []
assert stack["Resources"]["BurstInstanceRole"]["Properties"]["Policies"][0]["PolicyDocument"] \
    ["Statement"][0]["Action"] == ["logs:CreateLogStream", "logs:PutLogEvents"]
```

Also assert the GitHub OIDC trust condition is exact:

```text
repo:mastermindx-market-intelligence/macro:environment:ci-burst-admin
```

and the AWS admin policy can create/describe/terminate only EC2 resources carrying the fixed `MastermindRole=ci-burst` tag plus the exact stack-owned subnet/security-group/profile resources.

In `tests/test_runner_policy.py`, require a pending `ci-linux-burst-canary` label with empty `carried_by`, forbid that label on scheduled consumers, and continue to require production `ci-linux.carried_by` only the accepted persistent runners.

- [ ] **Step 2: Run and confirm RED**

```bash
python3.12 -m pytest -q tests/test_ci_burst_aws_stack.py tests/test_runner_policy.py \
  -k "burst or runner_policy"
```

Expected: missing stack and missing pending label.

- [ ] **Step 3: Implement the dedicated AWS network and roles**

`ops/runner-cloud/aws/ci-burst-stack.yml` must create:

- VPC `10.77.0.0/24` with DNS support/hostnames enabled and no peering/VPN/Tailscale resources;
- one public subnet `10.77.0.0/26` in the stack-selected `us-east-1` AZ;
- internet gateway + route table for outbound internet only;
- security group with **no ingress**, egress TCP/443 to `0.0.0.0/0`, UDP+TCP/53 to `0.0.0.0/0`, UDP/123 to `169.254.169.123/32`; no all-protocol egress;
- CloudWatch log group `/mastermind/ci-burst` with 14-day retention;
- instance role with only `logs:CreateLogStream` and `logs:PutLogEvents` on that log group; no EC2, STS, Secrets Manager, S3, SSM, IAM, KMS, or GitHub authority;
- instance profile wrapping that log-only role;
- GitHub OIDC admin role trusted only from the `ci-burst-admin` GitHub environment, with session duration 3600 seconds;
- admin permissions bounded to launch `c7i.2xlarge` from an AMI tagged `MastermindCiBurstImage=true`, in the stack subnet/security group/profile, tag resources with the fixed role/generation/reconcile keys, `DescribeInstances`, and terminate only tagged burst instances.

Set EC2 launch conditions in IAM for region `us-east-1` and require request/resource tag `MastermindRole=ci-burst` wherever AWS supports that condition. The code-level launcher will enforce the same constraints again.

- [ ] **Step 4: Add the diagnostic label declaration without making it live**

Add only the new pending label/capability. Do **not** add a live pool slot or `carried_by` runner. `scripts/check_runner_policy.py` must reject:

- `ci-linux-burst-canary` on a production trusted-pack job;
- any live carrier before EC1 host proof;
- any burst label on render/fork/scheduled work;
- `ci-linux` on a declared EC1 burst runner.

- [ ] **Step 5: Run focused proof and commit**

```bash
python3.12 -m pytest -q tests/test_ci_burst_aws_stack.py tests/test_runner_policy.py
python3.12 scripts/check_runner_policy.py
git diff --check
git add ops/runner-cloud/aws/ci-burst-stack.yml ops/runner-cloud/aws/README.md \
  tests/test_ci_burst_aws_stack.py .github/runner-policy.yml \
  scripts/check_runner_policy.py tests/test_runner_policy.py
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
- Image version manifest schema `mastermind.ci_burst_image.v1`.
- GitHub Actions runner fixed initially at `2.337.0`, Linux x64 archive SHA-256 `70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613`.
- AMI tags: `MastermindCiBurstImage=true`, `ExecutionProfileId`, `SourceCommit`, `RunnerVersion`.

- [ ] **Step 1: Write RED image-contract tests**

Tests must statically require:

```python
versions = json.loads(Path("ops/runner-cloud/aws/image-versions.json").read_text())
assert versions["schema"] == "mastermind.ci_burst_image.v1"
assert versions["github_actions_runner"]["version"] == "2.337.0"
assert versions["github_actions_runner"]["sha256"] == \
    "70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613"
```

Require the Packer source to resolve only Canonical Ubuntu 24.04 amd64 images owned by AWS account `099720109477`, use a 150-GiB encrypted gp3 root device, and write a Packer manifest containing the resolved source AMI ID and built AMI ID.

Require `provision-image.sh` to install nftables, CloudWatch Agent, Git, jq, unzip/tar prerequisites, the pinned runner archive with SHA verification, `macroci` user, the current L3 dependency-cache verifier, current Git prewarm/cache-update helpers, and root-only hard-stop unit/timer.

- [ ] **Step 2: Run and confirm RED**

```bash
python3.12 -m pytest -q tests/test_ci_burst_image.py
```

Expected: missing image files/workflow.

- [ ] **Step 3: Implement the Packer image**

The Packer source uses:

```hcl
source "amazon-ebs" "ci_burst" {
  region        = "us-east-1"
  instance_type = "c7i.2xlarge"
  ssh_username  = "ubuntu"
  source_ami_filter {
    filters = {
      name                = "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
      architecture        = "x86_64"
    }
    owners      = ["099720109477"]
    most_recent = true
  }
  launch_block_device_mappings {
    device_name           = "/dev/sda1"
    volume_size           = 150
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }
}
```

`provision-image.sh` must verify the runner archive hash before extraction. It must create `/var/cache/mastermind-ci/macro.git` and `/var/cache/mastermind-ci/python` as root-owned, candidate-read-only cache roots and install the current main-owned helper bytes under `/usr/local/libexec` with a generated manifest of SHA-256 hashes.

Do not pre-register a GitHub runner in the image and do not bake JIT configuration, GitHub tokens, AWS admin credentials, or candidate repository credentials into it.

- [ ] **Step 4: Implement the one-use JIT wrapper and metadata fence**

`run-jit-once.sh` runs as `macroci`. Before it contacts GitHub it must:

1. read `/run/mastermind-ci/jit.config` once;
2. require the file owner UID to equal `macroci`, mode `0400`, and size `1..131072` bytes;
3. read into memory;
4. unlink the file and fsync its parent directory;
5. verify `/proc/self/cgroup`, current helper-manifest hashes, read-only Git/dependency cache permissions, and the execution-profile ID;
6. `exec /opt/actions-runner/run.sh --jitconfig "$jit"`.

The Packer image installs an nftables rule loaded before this service:

```text
meta skuid macroci ip daddr 169.254.169.254 reject
```

and the launch request later uses `HttpTokens=required`, `HttpPutResponseHopLimit=1`, `HttpProtocolIpv6=disabled`, `InstanceMetadataTags=disabled`.

No runner process may start until the IMDS fence is active.

- [ ] **Step 5: Implement the image-build workflow with pinned actions**

`.github/workflows/ci-burst-image.yml` is `workflow_dispatch` only, uses protected environment `ci-burst-admin`, permission `id-token: write`, and pins:

```yaml
- uses: aws-actions/configure-aws-credentials@cbe3b392738ccf3f987d68400dafcf4b0624a56c
```

It runs `packer init`, `packer validate`, `packer build`, then writes a non-secret image receipt containing source AMI, built AMI, Packer template SHA, exact repository commit, execution-profile ID and runner archive SHA. It never uploads AWS credentials.

- [ ] **Step 6: Local/static proof and commit**

```bash
python3.12 -m pytest -q tests/test_ci_burst_image.py
packer fmt -check ops/runner-cloud/aws/packer/ci-burst.pkr.hcl
packer validate ops/runner-cloud/aws/packer/ci-burst.pkr.hcl
git diff --check
git add ops/runner-cloud/aws/packer/ci-burst.pkr.hcl \
  ops/runner-cloud/aws/scripts/provision-image.sh \
  ops/runner-cloud/aws/scripts/run-jit-once.sh \
  ops/runner-cloud/aws/scripts/hard-stop.sh \
  ops/runner-cloud/aws/cloudwatch-agent.json \
  ops/runner-cloud/aws/image-versions.json \
  tests/test_ci_burst_image.py .github/workflows/ci-burst-image.yml
git commit -m "ci: build sealed AWS JIT runner image"
```

---

### Task 3: Implement deterministic AWS/JIT effect control without a state database

**Files:**
- Create: `scripts/ci_burst_aws.py`
- Create: `tests/test_ci_burst_aws.py`

**Interfaces:**
- Pure functions: `reconcile_id()`, `client_token()`, `runner_name()`, `build_run_instances_args()`, `classify_instances()`.
- Side-effect CLI: `launch`, `wait-online`, `reconcile`, `terminate`.
- GitHub endpoint: `POST /orgs/mastermindx-market-intelligence/actions/runners/generate-jitconfig`.

- [ ] **Step 1: Write RED deterministic identity tests**

```python
def test_effect_identity_is_stable_and_bounded() -> None:
    rid = BURST.reconcile_id(
        repository="mastermindx-market-intelligence/macro",
        workflow_run_id="123456",
        workflow_run_attempt=1,
        execution_profile_id="ci-linux-x64-deadbeef",
    )
    assert rid == BURST.reconcile_id(
        repository="mastermindx-market-intelligence/macro",
        workflow_run_id="123456",
        workflow_run_attempt=1,
        execution_profile_id="ci-linux-x64-deadbeef",
    )
    assert len(BURST.client_token(rid)) <= 64
    assert BURST.runner_name(rid).startswith("ci-burst-")
```

Add tests proving changed attempt/profile yields a different identity, same identity + conflicting two live instances is `CONFLICT`, zero instance is `ABSENT`, one matching instance is `PRESENT`, terminal instance is not a license to create again under the same completed reconcile ID, and AWS errors/timeouts classify `EFFECT_UNKNOWN` until inventory is read.

- [ ] **Step 2: Implement exact `RunInstances` arguments**

`build_run_instances_args()` must produce one instance only with:

```text
--count 1
--instance-type c7i.2xlarge
--instance-initiated-shutdown-behavior terminate
--metadata-options HttpTokens=required,HttpPutResponseHopLimit=1,HttpEndpoint=enabled,HttpProtocolIpv6=disabled,InstanceMetadataTags=disabled
```

plus exact AMI/subnet/security-group/instance-profile inputs from the deployed stack, encrypted 150-GiB gp3 root, deterministic client token, and tags:

```text
MastermindRole=ci-burst
MastermindReconcileId=<stable id>
ExecutionProfileId=<exact profile>
GitHubRunId=<run id>
GitHubRunAttempt=<attempt>
```

The code validates those inputs before invoking AWS CLI. Any instance count other than one is a local refusal.

- [ ] **Step 3: Implement GitHub JIT request with a closed response parser**

Use Python `urllib.request`, bearer token from environment `CI_BURST_GITHUB_TOKEN`, API version `2022-11-28`, and body:

```json
{
  "name": "ci-burst-<stable-id>",
  "runner_group_id": 123,
  "labels": ["ci-linux-burst-canary"],
  "work_folder": "_work"
}
```

The actual runner group ID is discovered immediately before launch by listing the organization runner groups and requiring exactly one named `macro-home-canary`. Do not persist the ID in source as authority.

Parse only `runner.id`, `runner.name`, and non-empty `encoded_jit_config`. Never print/log/store the encoded config in receipts. Return it only to the launch path that embeds it in root bootstrap userdata.

- [ ] **Step 4: Implement ambiguous-effect reconciliation**

`launch` sequence:

1. `DescribeInstances` by exact `MastermindReconcileId` + `MastermindRole=ci-burst`;
2. if one nonterminal matching instance exists, return it without `RunInstances`;
3. if more than one exists, `CONFLICT` and stop;
4. if absent, issue exactly one `RunInstances` with deterministic client token;
5. on client timeout/error, immediately `DescribeInstances` using the same tags; do not call `RunInstances` again in that command;
6. only a later explicit reconcile command may decide whether the same AWS-idempotent request is safe to query/recover; no provider failover.

`terminate` requires the exact role/reconcile/profile tags and refuses a running GitHub job/runner-busy state supplied by the caller.

- [ ] **Step 5: Run tests and commit**

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
- Dispatch inputs: `pr_number` integer-like string and optional `pack` integer-like string; absent pack means use current `select_ci_canary_packs.py --count 1`.
- Jobs: `plan`, `hosted-control`, `launch-burst`, `burst-pack`, `compare`, `teardown`, `summary`.
- Self-hosted job `runs-on`: group `macro-home-canary`, label `ci-linux-burst-canary` only.

- [ ] **Step 1: Write RED workflow-security tests**

Tests must prove:

- only `workflow_dispatch` exists; no `pull_request`, `pull_request_target`, `push`, `schedule`, or `workflow_call`;
- `burst-pack` uses group `macro-home-canary` and static label `ci-linux-burst-canary`;
- the workflow text contains no production `labels: ci-linux` for burst-pack;
- fork PRs are refused by `plan` before JIT generation;
- candidate workflow YAML is data only; control checkout comes from `main` and the exact candidate SHA is separately resolved;
- hosted control and burst pack consume the same plan/changed-file artifact and pack identity;
- `compare` calls existing `scripts/compare_ci_canary_receipts.py` and does not call merge control;
- `teardown` is hosted and `if: always()`;
- no job except hosted `launch-burst`/`teardown` receives AWS OIDC permission;
- no self-hosted job receives `CI_BURST_GITHUB_TOKEN`, AWS credentials, App private key, or cloud role ARN.

- [ ] **Step 2: Implement `plan` using current main-defined CI helpers**

Use current main checkout/control, resolve the exact same-repo PR with `scripts/resolve_ci_canary_ref.py`, freeze one `gate: code` `ci.pack_plan.v2`, publish exact candidate/base/head/tested SHA + changed-files artifact, and select exactly one non-empty pack. Preserve current production `RUNNER_CONTRACT` and L3 dependency lock.

- [ ] **Step 3: Implement hosted control**

Mirror the existing diagnostic hosted-control contract: exact candidate checkout, setup Python `3.12.13`, setup Node `20`, run the selected pack against the frozen plan, emit semantic fragment, execution timing and canary receipt.

- [ ] **Step 4: Implement `launch-burst` with two protected credentials**

The job uses environment `ci-burst-admin`, `id-token: write`, current pinned AWS credentials action:

```yaml
- uses: aws-actions/configure-aws-credentials@cbe3b392738ccf3f987d68400dafcf4b0624a56c
  with:
    role-to-assume: ${{ vars.CI_BURST_AWS_ROLE_ARN }}
    aws-region: us-east-1
```

and a dedicated GitHub App token action pinned at:

```yaml
- uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1
  id: registrar
  with:
    app-id: ${{ vars.CI_BURST_REGISTRAR_APP_ID }}
    private-key: ${{ secrets.CI_BURST_REGISTRAR_PRIVATE_KEY }}
    owner: mastermindx-market-intelligence
```

The registrar App permission set is exactly organization `Self-hosted runners: write` plus metadata. It has no contents/actions/issues/pulls/workflows/administration permission.

`launch-burst` generates one JIT config, calls `ci_burst_aws.py launch`, then polls GitHub runner inventory until the exact runner is `online`/idle or 10 minutes elapse. It does not complete until online; therefore `burst-pack` is not queued before the runner is known eligible.

- [ ] **Step 5: Implement root bootstrap userdata without leaking JIT bytes**

Generate a MIME/cloud-init payload without shell tracing. The payload writes the encoded JIT config to `/run/mastermind-ci/jit.config` owned `macroci:macroci`, mode `0400`; starts CloudWatch Agent and nftables; verifies the AMI/helper/profile/cache identities; root-updates the public Git cache **before** runner registration; builds/verifies any missing L3 dependency group only through the trusted root updater; then starts the `macroci` JIT service.

The userdata script must never `echo`, `set -x`, or serialize JIT config into the receipt. Tests scan for forbidden logging patterns.

- [ ] **Step 6: Implement the burst pack from existing semantics, not a new gate**

`burst-pack` downloads the same control/plan artifacts, checks exact SHA/profile, setup-python 3.12.13 and Node 20, runs current `run_ci_pack.py --execute`, captures resources/timing/fragment/receipt through the existing helpers, and uploads artifacts. It must verify `RUNNER_NAME` starts with `ci-burst-` and the execution profile equals the L3 profile.

- [ ] **Step 7: Compare, teardown, and summarize**

`compare` requires hosted vs burst equality through the existing comparator. `teardown` obtains fresh AWS OIDC, fresh-reads GitHub runner/job state, and terminates only the matching tagged instance after `burst-pack` is terminal. The instance's 45-minute hard-stop remains a backstop, not normal teardown authority.

`summary` writes one non-authoritative Markdown/JSON receipt with launch, runner-online, queue/pickup, pack, compare, log-stream, and termination state. JIT bytes/tokens are never included.

- [ ] **Step 8: Run static tests and commit**

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

### Task 5: Admin bootstrap, one real JIT canary, and terminal EC1 proof

**Source files:**
- Modify: `docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md`
- Modify: `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
- Create: `agentos/handoffs/CI-EC1-AWS-JIT-SUBSTRATE-CANARY-2026-09-01.md`

**External privileged effects:**
- Deploy CloudFormation stack in `us-east-1`.
- Configure protected GitHub Environment `ci-burst-admin`.
- Create/install dedicated GitHub App `Mastermind CI Burst Registrar` with org self-hosted-runners write only.
- Add the merged `ci-burst-canary.yml@refs/heads/main` as the sole new selected workflow in existing runner group.
- Build one AMI through merged `ci-burst-image.yml`.

- [ ] **Step 1: Stop for explicit privileged admin ceremony before external writes**

Re-pin current procedure and obtain the current authorized operator/admin edge. Record pre-change runner-group selected workflows, runners, AWS stack absence/presence, OIDC-provider ARN, and existing AWS resources matching `MastermindRole=ci-burst`. Do not request/paste private keys or JIT config in chat/Slack/GitHub.

- [ ] **Step 2: Deploy the stack once and verify negative network/permission boundaries**

Use:

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
GITHUB_OIDC_PROVIDER_ARN=$(aws iam list-open-id-connect-providers \
  --query 'OpenIDConnectProviderList[].Arn' --output text | \
  tr '\t' '\n' | grep 'token.actions.githubusercontent.com$')
test -n "$GITHUB_OIDC_PROVIDER_ARN"
aws cloudformation deploy \
  --region us-east-1 \
  --stack-name mastermind-ci-burst \
  --template-file ops/runner-cloud/aws/ci-burst-stack.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides GitHubOidcProviderArn="$GITHUB_OIDC_PROVIDER_ARN"
```

If zero or multiple matching GitHub OIDC providers are found, stop; do not create a second provider automatically.

Verify no inbound SG rules, no peering/VPN, instance-role policy is log-only, admin trust subject exact, and AWS account/region are the intended ones.

- [ ] **Step 3: Build and attest one AMI**

Dispatch merged `ci-burst-image.yml` once. Record exact AMI ID, source AMI ID, runner version/hash, repository commit, helper-manifest SHA, dependency-lock document SHA and execution-profile ID. AMI must have `MastermindCiBurstImage=true`.

- [ ] **Step 4: Update runner-group selected workflows as one audited change**

Fresh-read the group. Add only:

```text
mastermindx-market-intelligence/macro/.github/workflows/ci-burst-canary.yml@refs/heads/main
```

Keep every previously accepted selected workflow byte-for-byte in the membership list. Re-read after write and record exact group ID + selected workflow list. Do not add `trusted-ci-executor.yml` if it is already present or loosen to all workflows.

- [ ] **Step 5: Dispatch exactly one non-destructive canary**

Choose a current same-repo PR that does not edit CI/runner/admission/provider surfaces. Record exact head/base/tested SHA before dispatch. Dispatch:

```bash
gh workflow run ci-burst-canary.yml --ref main -f pr_number="$PR_NUMBER"
```

Do not dispatch a second EC1 run while the first effect is nonterminal or ambiguous.

- [ ] **Step 6: Acceptance checklist**

PASS requires all of:

- one and only one EC2 resource for the reconcile ID;
- correct `c7i.2xlarge`, AMI, subnet, SG, profile, metadata options and tags;
- runner appears once in existing group with `ci-linux-burst-canary`, never `ci-linux`/render;
- JIT config absent from Actions/CloudWatch/receipt logs;
- candidate UID cannot read IMDS;
- external bootstrap + runner `_diag` logs exist in `/mastermind/ci-burst`;
- one burst job and no second job on the runner;
- hosted/burst tested SHA, base, plan, logical jobs, semantic fragment and result match;
- execution-profile/dependency-lock identities match the approved L3 contract;
- candidate does not mutate Git/dependency caches;
- runner auto-deregisters after the job;
- EC2 terminates and no matching live resource remains;
- no production trusted pack ran on the burst instance;
- existing four persistent runners/render route are unchanged.

Any mismatch is EC1 FAIL; do not move to EC2.

- [ ] **Step 7: Record and return held implementation PR**

Update the runbook/workstream and exact handoff with immutable run/job/AMI/log/instance/runner/fragment/receipt IDs and rollback. Run:

```bash
python3.12 scripts/agentos.py validate
python3.12 -m pytest -q tests/test_ci_burst_aws_stack.py tests/test_ci_burst_image.py \
  tests/test_ci_burst_aws.py tests/test_ci_burst_workflow.py tests/test_runner_policy.py
git diff --check
```

Independent adversarial review is required. Return the source PR DRAFT/HOLD-FOR-SOL; worker does not self-merge.

## Stop Condition

Stop before external effect or next wave if AWS OIDC cannot be scoped to the protected GitHub environment, the registrar App needs broader authority than self-hosted-runner write, the VM needs a cloud-management credential visible to `macroci`, the existing runner group cannot restrict the canary workflow, JIT bytes cannot be erased before candidate execution, external logs cannot survive termination, semantic parity fails, or an existing AWS/provider owner already owns the same infrastructure.

## Completion Truth

EC1 success means `AWS_JIT_BURST_SUBSTRATE = PROVEN_DIAGNOSTIC_ONLY`. It proves one second-domain one-job runner can safely execute a diagnostic pack. It does **not** create queue-driven autoscaling, production `ci-linux` eligibility, a webhook receiver, a persistent cloud pool, or permission to launch more than one runner.