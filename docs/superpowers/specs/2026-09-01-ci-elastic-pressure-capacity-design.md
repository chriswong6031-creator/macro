# CI Elastic Pressure + Capacity Architecture Freeze

**Status:** records-only architecture freeze; implementation not started  
**Operation:** `ci-elastic-capacity-architecture-20260901-sol-001`  
**Parent program:** Macro #6351 / `WS:CI-MERGE-CONTROL-PLANE` + `WS:RUNNER-FLEET-RESILIENCE`  
**Protected Sol procedure at freeze:** `mastermindx-market-intelligence/Mastermind@7191702e3b0104525b6b26cd30ddb53d89a8a663`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Macro base at freeze:** `901d06e41c0ffd1ede7d26b55b1ca113c815694e`  
**Current fourth-slot source carrier:** Macro #6714 / `ci-pc-fourth-slot-recovery-20260901-sol-001`  
**Current red-fragment repair carrier:** Macro PR #6628  

## 1. Chairman outcome

Mastermind CI must remain reliable during simultaneous PR pressure without turning capacity into another scheduler, retry plane, proof store, or source of semantic nondeterminism.

The target is not simply "more runners." The target is a pressure-resilient proof system in which:

1. deterministic structural defects are rejected before expensive fan-out and are mechanically difficult to merge into `main`;
2. ordinary trusted same-repository pack execution has four proven persistent Linux/x86 slots under one bounded PC resource envelope, with render capacity physically and semantically isolated;
3. false ownership, repeated dependency startup, unnecessary checkout and stale balancing are reduced so demand shrinks before supply expands indefinitely;
4. when genuine eligible queue pressure still exceeds the four-slot local pool, at most one separately isolated ephemeral Linux/x64 burst runner may be added on demand;
5. GitHub Actions remains the sole job scheduler, queue and job-to-runner matcher;
6. `ci-plan`, semantic fragments, `ci-gate`, CI authority and merge control remain the sole existing proof/merge owners;
7. every capacity decision is fail-closed, bounded, measurable, correction-safe and economically falsifiable;
8. capacity never converts a poisoned base, coverage defect, dependency-network flake, false ownership problem or runner outage into "run more machines."

The 10/10 state is boring under load: a burst of PRs may increase compute, but it does not change proof semantics, fork trust boundaries, merge authority, runner identity law, or the operator's ability to explain why each job ran and where its evidence came from.

## 2. Current canonical state and capability ledger

This architecture extends current owners; it does not replace them.

| Capability | State at freeze | Canonical evidence / boundary |
|---|---|---|
| Three persistent sealed PC CI slots | `PROVEN_LIVE` | #6351 P1/P2/P3/P4 accepted path; current trusted executor targets `macro-home-canary` + `ci-linux` with `max-parallel: 3` |
| Trusted main-defined self-hosted executor | `PROVEN_LIVE` | `.github/workflows/trusted-ci-executor.yml`; fork/untrusted work remains hosted |
| Red trusted-pack evidence survives hosted relay into `ci-gate` | `BUILT_NOT_PROVEN` on current #6628 candidate | #6628 exact carrier; separate from capacity work |
| Fourth persistent PC slot source substrate | `SPEC_ONLY` | frozen plan `docs/superpowers/plans/2026-08-26-pc-ci-fourth-slot-resource-isolation.md`; fresh implementation issue #6714 has no worker `START` or code PR at this freeze |
| Fourth persistent PC slot host proof | `NOT_BUILT` | C3R-B is intentionally future privileged work |
| Ordinary production concurrency 3 -> 4 | `NOT_BUILT` | separate post-host-proof promotion carrier only |
| Main structural integrity / <2m poisoning refusal | `PARTIAL` / unresolved | #6637 remains open; Macro `main` has no server-side branch protection at this freeze |
| False-ownership / proof-graph reduction | `PARTIAL` | CI latency masterplan C2/L2 remains necessary; capacity is not a substitute |
| Immutable dependency environment/cache | `NOT_BUILT` as production contract | latency masterplan requires immutable dependency inputs; candidate jobs may consume but never mutate shared cache state |
| Hermetic result reuse | `NOT_BUILT` | later latency wave only after execution identity is closed |
| Elastic JIT burst runner | `SPEC_ONLY` after this architecture lands | no current implementation carrier, webhook scaler, scale-set deployment, cloud credential or burst runner exists |

No capability above may be promoted by documentation alone.

## 3. Binding no-rebuild and authority laws

### 3.1 Owners that remain canonical

- **GitHub Actions** owns workflow scheduling, job queueing, matching, assignment and requeue semantics.
- **`.github/runner-policy.yml` + Runner Fleet source law** own declared runner capabilities/topology; they are not a live scheduler.
- **The existing GitHub runner group** owns which selected trusted workflows may reach self-hosted capacity.
- **`ci-plan`** remains the sole logical selection/partition authority.
- **Existing semantic plan + fragments + `ci-gate`** remain the sole semantic aggregate proof path.
- **Existing CI authority / merge controller** remain the sole merge-facing authority.
- **Existing CI receipt/monitor tooling** remains the instrumentation path; elastic-capacity evidence extends it rather than creating a second database.
- **Agent OS** remains durable organizational memory.

### 3.2 Explicitly forbidden replacements

This program must not create:

- a second CI scheduler;
- a second job queue or durable queue mirror;
- a runner-assignment engine;
- a retry ledger or automatic semantic retry plane;
- a second runner registry;
- a second semantic gate or proof database;
- a new merge controller;
- a capacity database whose state becomes necessary to know whether GitHub work exists;
- a webhook-delivery cursor treated as canonical job state;
- a generic public-repository `self-hosted` path;
- a fork/untrusted route to persistent or elastic Mastermind-controlled runners.

A capacity reconciler may provision or remove **eligible compute only**. It never chooses a job for a machine. GitHub chooses among matching online/idle runners using the existing group/label contract.

## 4. Why the architecture is layered

Queue latency has at least five separable causes:

1. conservative ownership widens affected-job selection;
2. folded ownership makes one logical owner carry unrelated suites;
3. repeated checkout/tool/dependency setup delays useful execution;
4. stale balancing creates long pack tails;
5. finite physical capacity creates queue amplification during simultaneous PR pressure.

Adding runners attacks only cause five. Therefore the architecture deliberately separates **main integrity**, **demand correctness**, **persistent capacity**, **portable execution**, and **elastic overflow**.

The maturity ladder is:

```text
trustworthy main + fast structural refusal
    -> smaller/correct proof graph
    -> immutable/portable execution inputs
    -> 4 proven persistent PC slots
    -> measured residual queue pressure
    -> 1 ephemeral JIT burst slot
    -> natural acceptance corpus
    -> only then reconsider >1 elastic slot
```

The fourth-slot work may proceed while path-disjoint latency work advances, but elastic production activation is held until the execution profile is portable enough to prove parity across failure domains.

## 5. Persistent capacity: 3 -> 4

The existing fourth-slot plan remains controlling for C3R-A/C3R-B. This freeze does not replace it.

### 5.1 C3R-A — source/code substrate only

Macro #6714 remains the current carrier. It may re-derive frozen plan Tasks 1-5 from current `main` and produce a held code PR while production remains exactly three slots.

In addition to the frozen plan's existing receipts, C3R-A must make the existing receipt path capable of carrying these forward-compatible identities wherever the current schema can be extended compatibly:

- `execution_profile_id` — stable semantic name for the reviewed execution environment, initially the persistent PC profile;
- `admission_policy_version` — version/hash identity of resource/admission thresholds independently from systemd slice ceilings;
- `workflow_job_queued_at` — GitHub-observed queue timestamp for the exact job when available;
- `runner_job_started_at` — first trustworthy runner-side job-start observation;
- `queue_wait_seconds` — mechanically derived only when both timestamps are present and ordered; unavailable is distinct from zero.

The existing checkout/dependency/test/wall timing fields remain separate. No field may relabel checkout or workflow startup as queue time.

If the existing receipt schema cannot add these fields compatibly, the worker must stop for Sol rather than invent a parallel receipt format. A schema version bump is allowed only with explicit migration/comparator tests proving old P1/P2/P4 receipts remain honestly readable.

C3R-A still performs zero live host/runner/group/label/credential/systemd/cgroup mutation and zero production `max-parallel` change.

### 5.2 C3R-B — privileged host proof

After C3R-A is accepted and merged, one separate privileged child may:

1. fresh-census runner group, persistent runner identities, selected workflows, host resource state, existing unit bytes, render state and rollback packet;
2. install `/mastermind-ci.slice` and migrate only the four CI units into it at a natural drain;
3. bring `pc-ci-4` online initially **without `ci-linux`** so service/PID/root/cache/cgroup identity is provable while unroutable;
4. prove `pc-ci-1..4` are descendants of the exact CI slice and render remains outside it;
5. only after identity proof, add the existing `ci-linux` eligibility as one audited activation edge;
6. run exactly one `slots=4` diagnostic while a real/render-reservation workload proves coexistence;
7. accept or roll back under the frozen memory/swap/PSI/event/throttling limits.

The WSL envelope remains 16 CPU / 44 GiB memory / 8 GiB swap. Four-slot proof does not imply six or eight slots.

### 5.3 Separate production promotion

Only after C3R-B acceptance may a fresh carrier change trusted executor `max-parallel: 3 -> 4` and the exact live runner-policy carrier inventory. It must then prove at least three ordinary production PRs, including simultaneous PR pressure and active render, and roll back to three on semantic, cleanup, cache, queue, pressure or render regression.

## 6. Demand-reduction prerequisites before elastic production

Elastic capacity is intentionally **not** the next production implementation immediately after C3.

### 6.1 Main integrity

The autoscaling path must not compensate for a known poisoned base. Existing #6637/main-integrity must provide a bounded machine-readable or directly queryable condition from the existing proof path. Elastic capacity may consume this condition; it may not create another "main health" implementation.

If the exact accepted base/control state is known structurally invalid, elastic scale-out is suppressed. Local production CI continues under existing law, but no paid/ephemeral capacity is added merely to accelerate inherited failure.

If integrity cannot be established from the existing owner, first production policy fails closed to **no burst** rather than manufacturing a new health check.

### 6.2 False ownership and fast preflight

C2/L2 remains independently required. A small diff selecting most logical jobs is a proof-graph issue, not evidence that capacity should grow without bound. Elastic acceptance reporting must separately state:

- selected logical-job count;
- selected pack count;
- global invalidator/broad-owner reason when applicable;
- queue time removed by extra capacity;
- compute time that would remain even with zero queue.

This prevents capacity from hiding ownership debt.

### 6.3 Immutable dependency/toolchain inputs

A second physical failure domain is useful only if it executes the same reviewed contract. Before a JIT runner becomes production-eligible, the dependency/toolchain layer must be sufficiently immutable that burst execution does not replace queue delay with internet-resolution nondeterminism.

Minimum contract:

- Python/Node/runtime versions are exact, not floating;
- dependency input identity is immutable and hashed;
- candidate jobs consume but cannot mutate shared dependency/cache state;
- missing/corrupt/stale cache forces a known live install/fetch path and is surfaced explicitly;
- a same-SHA parity corpus proves persistent-PC and burst execution agree on selected jobs and semantic result;
- no route may claim the PC execution profile when it actually ran a materially different cloud image.

Pack-specific sparse manifests and hermetic result reuse remain separate latency carriers.

## 7. Elastic burst architecture

### 7.1 Initial production ceiling

The first elastic production target is exactly:

```text
persistent capacity: 4 proven pc-ci slots
elastic capacity:    0 or 1 ephemeral JIT Linux/x64 runner
maximum total:       5 concurrent eligible trusted-pack runners
```

There is no initial scale-to-six/eight policy. More than one ephemeral runner requires a new measured architecture amendment after the first acceptance corpus.

### 7.2 Separate physical failure domain

The first burst runner must not share the PC's physical host/WSL failure domain. It serves both queue relief and failure-domain diversification.

Provider choice remains implementation-time and must satisfy:

- Linux/x64 environment compatible with the reviewed CI execution profile;
- immutable image or equivalent sealed bootstrap identity;
- short-lived machine lifecycle;
- provider-side hard concurrency/quota ceiling of one burst machine for canary/first production;
- OIDC or another short-lived provisioning credential path for the hosted capacity actuator; no long-lived cloud credential in candidate jobs;
- network policy with no route to Mastermind home/private infrastructure;
- external runner/application log forwarding before production use;
- deterministic provider resource tags sufficient for effect reconciliation without a capacity database.

The stationary macOS/ARM host is not a substitute for this Linux/x64 role.

### 7.3 Main-defined trust boundary

Macro is public, so a burst runner must never be generic PR self-hosted capacity.

Production burst eligibility is granted only after image/bootstrap attestation succeeds and only through the existing selected-workflow runner-group boundary. Fork/untrusted PR execution remains GitHub-hosted. Candidate-edited YAML cannot grant persistent or elastic runner authority.

The burst candidate job receives no cloud-management credential, no home-network credential, no GitHub write credential, no OIDC provider-creation permission, and no broader secret merely because the machine is ephemeral.

### 7.4 Diagnostic canary eligibility is deliberately disjoint from production

The first manual JIT canary must **not** register with production `ci-linux` eligibility. Otherwise it could steal an ordinary trusted production pack while Sol is trying to prove the new failure domain.

EC1 therefore uses one dedicated dispatch-only burst-canary capability, provisionally named `ci-linux-burst-canary`, declared in the existing runner-policy registry and reachable only from an already-selected main-defined diagnostic workflow. The exact name may change only during EC1 source review if current label law requires a different existing-family spelling; the semantics may not change:

- dispatch-only;
- main-defined selected workflow only;
- no production trusted-executor route;
- no fork/untrusted route;
- one JIT job maximum;
- absent outside the EC1 canary machine.

Only EC3, after EC1 parity and EC2 dry-run admission proof, may register an ephemeral runner with production `ci-linux` eligibility.

### 7.5 Ephemeral/JIT lifecycle

GitHub currently recommends ephemeral runners for autoscaling and supports JIT configuration through self-hosted-runner REST APIs. Production lifecycle:

```text
pressure wake
-> fresh reconciliation
-> provider creates one sealed machine (not yet a GitHub runner)
-> image/bootstrap attestation passes
-> capacity actuator requests one JIT config for existing runner group + production-eligible labels
-> machine registers/starts ephemeral runner
-> GitHub assigns at most one matching job
-> runner executes existing trusted executor job
-> runner exits / GitHub auto-deregisters after one job
-> runner logs/receipts flush externally
-> machine self-terminates
-> later reconciler cleans only proven orphan residue if needed
```

Never generate/register the JIT runner before host/image attestation. Registration is the eligibility edge.

The ephemeral image must pin a reviewed runner software version or controlled bootstrap version. If automatic runner updates are disabled, the image-release owner must update within GitHub's current support window—currently no later than 30 days after a runner release, and immediately when a critical security update makes the older runner ineligible. Stale images are refused before registration; never hot-update during candidate execution merely to become eligible.

### 7.6 External log requirement

Before production eligibility, runner application logs and capacity-actuator logs must be exported off the ephemeral machine. Local-only logs are inadequate because the machine disappears after one job.

Log forwarding is diagnostic evidence only. It is not a semantic proof store and cannot turn missing semantic evidence green.

## 8. Pressure detection and scale decision

### 8.1 Webhook is a wake signal, never truth

GitHub exposes `workflow_job` lifecycle events such as `queued`, `in_progress` and `completed`, but documents webhook timeliness as an autoscaling reliability concern.

Therefore:

- a webhook may wake capacity reconciliation;
- duplicate, delayed, out-of-order or missing webhook delivery must not change correctness;
- reconciliation fresh-reads GitHub's actual eligible queued jobs and runner state before every decision;
- no webhook cursor/database is canonical job state;
- time-of-day may later prewarm an unregistered machine but may not independently authorize JIT registration.

### 8.2 Wake adapter boundary

Prefer an already-existing GitHub App/webhook ingress if current estate archaeology proves it can safely receive `workflow_job`. If no accepted ingress exists, EC2 may add one **minimal stateless wake adapter** whose only authority is to authenticate the GitHub webhook and request a main-defined hosted reconciliation run.

The wake adapter:

- stores no queue/capacity truth;
- carries no provider-provisioning credential;
- cannot generate JIT config;
- cannot choose a job or runner;
- cannot mutate semantic CI;
- may collapse obvious duplicate deliveries opportunistically but correctness never depends on that collapse.

If adding such an adapter would require a new lifecycle/control plane rather than a thin transport bridge, EC2 stops and evaluates GitHub's official Scale Set Client instead.

### 8.3 GitHub-owned serialization

The first implementation serializes capacity decisions through a GitHub-owned concurrency primitive or another already-canonical single-flight mechanism, never a custom lock database.

For a hosted Actions-based actuator the required shape is conceptually:

```text
concurrency group = one stable CI-capacity-reconcile group
cancel-in-progress = false
```

Each serialized run fresh-reads state **after** acquiring the slot. A stale queued reconcile run that discovers no pressure exits `NO_SCALE`; its old wake cannot provision merely because it was once valid.

The reconcile workflow run ID/generation is the preferred bounded effect identity input for the provider resource name/tag. Duplicate webhook deliveries converge through serialization and fresh state rather than sharing a custom dedupe ledger.

If the chosen surface cannot provide bounded single-flight plus fresh provider/GitHub effect reconciliation, production provisioning is refused.

### 8.4 Eligible demand

Only jobs belonging to the existing trusted main-defined execution route count toward burst demand. Generic Actions queue depth is irrelevant.

The pressure census distinguishes at least:

- eligible trusted-pack jobs queued;
- age of oldest eligible queued trusted-pack job;
- expected persistent-slot count;
- persistent `pc-ci` runners online/idle/busy;
- any already registered/provisioning ephemeral burst runner;
- current accepted base/main-integrity condition from the existing owner;
- provider hard quota/availability;
- current execution-profile eligibility.

Unknown/ambiguous eligibility widens to **no burst**.

### 8.5 Initial production trigger and degraded-pool boundary

Production thresholds are calibrated from natural four-slot traffic rather than guessed. The canary may use provisional values only to collect data.

The first production burst policy requires all of:

1. **healthy expected persistent pool:** all four production `pc-ci` identities are established online under current Runner Fleet law;
2. **capacity saturation:** no eligible persistent slot is currently idle;
3. **sustained user-visible pressure:** measured queue-age/depth exceeds the calibrated threshold for eligible trusted packs;
4. **main/base integrity admissible:** existing integrity owner does not report known poison/hold;
5. **no burst already provisioning/registered/active:** GitHub + provider state agree the ceiling is free;
6. **burst execution profile current:** image, runner version, dependency identity and admission policy are eligible.

The initial calibration hypothesis is roughly oldest eligible wait >= 60-90 seconds and queue depth beyond available persistent capacity, but those numbers are not architecture authority until the four-slot natural corpus freezes them.

**Important:** the first elastic release does not automatically replace a missing/offline persistent runner. If expected persistent count is below four, return `LOCAL_POOL_DEGRADED / NO_BURST` and hand the condition to the existing Runner Fleet owner. This prevents autoscaling from masking a local fleet outage. A later architecture amendment may admit a bounded degraded-backup mode only after ordinary burst scaling is `PROVEN_LIVE` and persistent liveness semantics are explicit.

Time of day is advisory only. A peak window may later justify pre-booting an unregistered image; registration still requires live pressure, fresh state and current attestation.

## 9. Effect reconciliation and duplicate suppression

Capacity provisioning modifies external state and must have one stable effect identity.

The provider resource name/tag is deterministic for one serialized reconcile generation, including repository, burst role, execution-profile generation and reconcile workflow run/generation identity.

If provider create times out or the client loses its response:

1. classify the effect `EFFECT_UNKNOWN`;
2. do not issue another create;
3. query provider inventory for the deterministic resource identity;
4. query GitHub runner inventory for a corresponding JIT runner identity;
5. reconcile the existing effect or remain failed closed.

A duplicate `workflow_job` webhook therefore converges on the already-existing provider/GitHub resource and cannot create a second runner.

Provider inventory and GitHub runner inventory are evidence sources; this architecture creates no durable capacity ledger.

## 10. Scale-in, teardown and orphan handling

Normal scale-in is simple: one ephemeral runner processes one job, auto-deregisters, flushes logs/receipts and causes its machine to terminate.

Do not use `workflow_job completed` alone as permission to kill the VM. Local runner-process exit plus GitHub runner/job state is the primary teardown fence because event delivery and job-finalization timing can differ.

A safety reaper may remove an orphan only when all are true:

- provider resource exceeds the reviewed orphan age;
- no matching GitHub runner is busy;
- no matching eligible job is assigned/in progress;
- resource identity matches exact burst role/generation;
- logs/diagnostics flushed or cleanup receipt explicitly records their loss;
- deletion effect is reconciled on ambiguity rather than blindly retried.

The provider-specific carrier freezes a hard maximum instance lifetime derived from trusted job timeout plus bounded provision/teardown margin. The reaper never uses age alone to kill a busy runner.

## 11. Execution-profile identity

Capacity is useful only if evidence says truthfully **where and under what contract** it ran.

Every persistent or burst trusted receipt must carry or derive:

- `execution_profile_id`;
- runner name/kind and runner software version;
- OS/kernel/architecture identity required by profile;
- Python/Node/toolchain identity;
- immutable dependency-input identity;
- image/bootstrap digest when applicable;
- admission-policy version/hash;
- tested SHA, base SHA and semantic plan SHA;
- selected logical jobs / pack index;
- `workflow_job_queued_at`, `runner_job_started_at`, `queue_wait_seconds` when available;
- checkout/dependency/test/wall phases;
- semantic fragment/result;
- relevant resource and cleanup evidence.

Two execution routes share a semantic profile only after mutation/parity proof demonstrates their differences are not semantically material. Otherwise profile IDs remain different and semantic law must explicitly admit both routes rather than falsifying identity.

## 12. Resource, policy and economic bounds

### 12.1 Persistent PC bound

The frozen C3 envelope remains:

- `/mastermind-ci.slice`
- `CPUQuota=800%`
- `CPUQuotaPeriodSec=100ms`
- `MemoryHigh=10G`
- `MemoryMax=12G`
- `MemorySwapMax=2G`

with separate existing guard/acceptance thresholds and render outside the slice.

### 12.2 Elastic runner-policy declaration

Elastic configuration belongs in the **existing** runner-policy source, not a new capacity registry. EC1/EC2 may extend `.github/runner-policy.yml` with a bounded declaration equivalent to:

```text
elastic_burst:
  mode: disabled | canary | enabled
  max_concurrent: 1
  production_label: ci-linux
  canary_label: ci-linux-burst-canary
  execution_profile_id: <reviewed open token>
```

Exact schema is implementation-time and must follow current runner-policy grammar/tests. Semantics are frozen:

- default/off before proof;
- canary does not imply production eligibility;
- maximum one;
- policy is declaration, not live runner state;
- emergency provider/principal disable may stop provisioning immediately, followed by canonical policy reconciliation; it does not create an alternate scheduler.

### 12.3 Elastic hard ceiling

First production burst environment has:

- maximum concurrent burst machines: 1;
- maximum eligible jobs per burst runner: 1;
- provider-side hard quota preventing accidental scale beyond one;
- bounded maximum machine lifetime;
- no automatic second-provider failover;
- no capacity increase on ambiguous provisioning state.

This bounds cost and blast radius even if trigger logic is wrong.

### 12.4 Economic acceptance

Retain elastic capacity only if a natural corpus shows material queue/final-push->gate improvement without semantic nondeterminism, infrastructure-red growth, excessive provisioning delay or disproportionate cost.

Corpus computes at least:

- burst launch count;
- pickup success rate;
- provisioning-to-online latency;
- queue time avoided versus four-slot observation/counterfactual where defensible;
- incremental compute cost;
- fraction of burst launches that execute useful work;
- parity/failure rate;
- same-SHA green->red nondeterminism count;
- orphan/cleanup failures.

If benefit is not demonstrated, disable/kill elastic production rather than preserving infrastructure because it was expensive to build.

## 13. Failure-state matrix

### Duplicate/delayed webhook
Fresh-read GitHub/provider state; serialized reconcile converges on `NO_SCALE` or one existing burst resource. No duplicate create.

### Webhook missing
Correctness is unchanged. Local four-slot capacity continues. A later low-frequency reconciliation sweep may improve responsiveness but is not required for correctness.

### Provider create ambiguous/timeout
`EFFECT_UNKNOWN`; query deterministic provider identity and GitHub runner inventory. No blind second create or provider failover.

### Provider unavailable
No burst. Local capacity continues. Record `BURST_PROVIDER_UNAVAILABLE` in non-authoritative capacity evidence.

### JIT config generated but machine never registers
No job authority exists on the machine. Reconcile provider/JIT runner state, let configuration become unusable/expire as appropriate, clean known orphan after accepted fence. Never reuse configuration on a different machine.

### Runner registers but does not pick up assignment
GitHub requeues an assignment not accepted within its service window. Capacity logic never retries the job. Destroy only after proving runner is not executing work.

### Persistent pool degraded
`LOCAL_POOL_DEGRADED / NO_BURST` in first release. Runner Fleet diagnosis owns the outage; elastic capacity does not mask it.

### Runner software/image stale
Burst profile becomes ineligible. Update through separate image release/canary; never hot-update during candidate execution.

### External log forwarding unavailable
No production JIT eligibility. Diagnostic canary fails explicitly; semantic CI remains separate.

### Dependency/cache unavailable
Follow reviewed execution-profile contract. Missing immutable cache is explicit and may force a known live path or refuse burst profile; never silently change dependency versions.

### Main/base integrity known bad
Suppress burst. Do not spend elastic capacity accelerating inherited structural failure.

### Main/base integrity unknown
First production policy fails closed to no burst unless existing integrity owner later defines an accepted safe-unknown state.

### Semantic parity mismatch
Disable burst eligibility immediately. Existing local route remains canonical. Return to Sol for execution-profile adjudication.

### Cloud runner compromised by candidate code
One job only; no home-network route; no cloud-management credentials; no subsequent job; destroy VM after job. Ephemerality limits persistence but does not reduce incident severity.

### Burst cleanup fails
Do not create a second burst while provider hard ceiling is occupied. Reconcile/remove orphan or remain degraded.

### Four-slot local pressure exceeds frozen slice envelope
Roll production concurrency back to three under C3 law. Elastic capacity does not justify WSL/local-envelope expansion.

## 14. Observability and existing receipt extension

Do not create an autoscaler database.

Extend existing CI canary/timing/receipt paths with bounded non-authoritative capacity evidence that can represent:

```text
capacity_trigger_source
eligible_queue_depth
oldest_eligible_queue_age_seconds
expected_persistent_slots
persistent_online
persistent_idle
persistent_busy
burst_resource_present
burst_runner_status
scale_decision = NO_SCALE | PROVISION_ONE | EFFECT_UNKNOWN | REFUSED | LOCAL_POOL_DEGRADED
scale_reason
execution_profile_id
admission_policy_version
provider_resource_identity_hash_or_nonsecret_id
provision_started_at
runner_registered_at
workflow_job_queued_at
runner_job_started_at
queue_wait_seconds
runner_job_completed_at
teardown_completed_at
```

Secrets, JIT config bytes, registration tokens, cloud credentials, instance metadata credentials and private host/network details are never receipts.

Capacity evidence is explanatory/operational only. It never overrides semantic fragments or `ci-gate`.

## 15. Test and proof architecture

### 15.1 Deterministic source tests

Later implementation must kill at least these forbidden mutations:

- webhook payload directly authorizes create without fresh state read;
- two simultaneous reconcile wakes can create two instances;
- burst ceiling raised above one;
- fork/untrusted workflow becomes burst-eligible;
- candidate-controlled workflow ref can reach burst runners;
- manual EC1 canary accidentally carries production `ci-linux`;
- production burst allowed before EC1 parity + EC2 dry-run admission proof;
- local pool degraded yet first-release scaler provisions;
- main-integrity known-red still provisions;
- unknown runner/image/profile registers as production `ci-linux`;
- execution receipt omits profile identity;
- unavailable queue timestamp is converted to zero queue wait;
- provider timeout triggers blind second create;
- cleanup kills a busy runner;
- job-completed webhook alone kills VM;
- JIT runner receives more than one job;
- burst route receives cloud-management/home-network credentials;
- missing external runner logs is treated as production-ready;
- capacity receipt makes semantic CI green;
- time-of-day alone registers burst capacity.

### 15.2 Manual/JIT canary before production eligibility

Before queue-driven production automation, prove one manually authorized JIT canary:

1. one sealed second-domain machine;
2. exact image/profile/runner-version attestation;
3. one JIT registration using dispatch-only burst-canary capability, **not production `ci-linux`**;
4. one exact non-destructive diagnostic candidate/pack through a main-defined selected diagnostic workflow;
5. semantic parity to hosted/persistent control under current evidence law;
6. one-job deregistration;
7. external log preservation;
8. machine termination and zero provider/GitHub orphan residue.

A manual canary proves execution substrate, not autoscaling or production eligibility.

### 15.3 Read-only pressure dry run

EC2 may begin after four-slot production is proven and can run in parallel with portable-execution work because it has no provider-create authority. It must replay historical/natural four-slot queue windows and prove:

- eligible-demand filtering;
- healthy-pool versus degraded-pool distinction;
- webhook duplicate/out-of-order independence;
- GitHub-owned serialization;
- deterministic effect identity;
- `NO_SCALE`, `LOCAL_POOL_DEGRADED`, `REFUSED` and hypothetical `PROVISION_ONE` decisions;
- zero provider/JIT/runner mutation.

EC3 depends on both EC1 substrate PASS and EC2 dry-run PASS.

### 15.4 Queue-driven canary

Only after EC1 and EC2 PASS:

- production runner may register with existing `ci-linux` under current selected-workflow group;
- enable serialized pressure reconciliation with ceiling one;
- use natural queue pressure, not an intentionally poisoned product PR;
- record trigger, fresh-state census, provision, registration, GitHub pickup, semantic result, teardown and cost;
- false-positive scale may execute no job and still be evidence, but repeated useless launches fail economic acceptance.

### 15.5 Production acceptance corpus

Elastic production remains `BUILT_NOT_PROVEN` until at least 30 natural qualifying pressure decisions/events or another preregistered operationally adequate corpus is accumulated, containing:

- several simultaneous-PR pressure windows;
- at least one window with active render on independent route;
- successful no-scale decisions;
- successful scale-and-execute decisions;
- degraded-local-pool observations that correctly do **not** burst under first-release law, if they occur naturally;
- provider-unavailable/disabled-burst negative control when safely observable;
- zero same-SHA semantic nondeterminism attributable to route;
- zero fork/untrusted burst executions;
- zero duplicate burst resources from duplicate wakes;
- zero orphaned busy-runner deletions;
- bounded cost and demonstrable p95 queue/final-gate improvement.

Do not manufacture semantic reds merely to complete the corpus.

## 16. Phased implementation program

Each phase is an independently bounded carrier.

### EC0 — records/source contracts only

This architecture freeze. No runner, webhook, provider or workflow behavior changes.

### C3R-A / C3R-B / C3-PROMOTE — persistent four-slot capacity

Continue existing #6714 and frozen C3 plan. Add only the forward-compatible profile/admission/queue-timing receipt fields without expanding C3 host/production authority.

### EC2A — four-slot pressure telemetry/dry-run classifier

May begin after four-slot production is proven. Read-only decisions only; no provider/JIT mutation. It may run in parallel with L3 portable execution and EC1 substrate preparation when path/authority surfaces are disjoint.

### L3 — immutable dependency/execution-profile closure

Use existing latency masterplan owner. Freeze portable dependency/toolchain identity and same-SHA parity requirements. No elastic production provisioning.

### EC1 — second-domain JIT substrate canary

One new carrier. Provider selection, immutable image/bootstrap, external log path, OIDC/provisioning boundary, deterministic resource identity, dispatch-only burst-canary label, one manual JIT diagnostic job, teardown. No production `ci-linux`; no webhook scale-out.

### EC2B — serialized actuator implementation, still dry

One new or properly continued EC2 carrier after current-state reconciliation. Wake adapter + main-defined reconciler fresh-read GitHub/provider state; production create stays disabled. Prove duplicate suppression and `EFFECT_UNKNOWN` handling.

### EC3 — one-runner queue-driven production canary

One new carrier. Enable `PROVISION_ONE` with provider hard ceiling one under natural pressure. This is the first wave allowed to give a JIT runner production `ci-linux` eligibility.

### EC4 — production acceptance / rollback soak

Accrue natural corpus, evaluate queue improvement, cost, parity and cleanup. Promote to `PROVEN_LIVE` only after preregistered gates hold.

### EC5 — optional capacity expansion

Not authorized by this freeze. Only if four persistent + one burst still misses SLOs after demand-reduction waves may future Sol architecture decide whether a second burst runner, GitHub Actions Runner Scale Set Client, ARC, or another official mechanism is justified.

## 17. Why not ARC or a large scale set now

GitHub currently presents ARC as its reference Kubernetes autoscaling implementation and also offers a standalone Runner Scale Set Client for custom VM/container infrastructure.

Mastermind's current measured need is smaller: one repository, four persistent runners and at most one burst runner. Introducing Kubernetes/ARC or a large scale-set surface now would add an operational failure domain and deployment/upgrade burden before it answers the first acceptance question.

Escalation rule:

- `0 -> 1` burst runner: bounded JIT architecture above;
- recurring need for multiple elastic runners, multi-repo routing, or webhook responsiveness becoming the dominant reliability risk: evaluate GitHub's Scale Set Client first;
- use ARC when Kubernetes infrastructure/expertise is independently justified;
- never keep extending a hand-rolled actuator into a general scheduler.

## 18. Security invariants for a public repository

GitHub's current documentation warns against self-hosted runners for public repositories because forked PR code can be dangerous. Mastermind's exception remains acceptable only because its boundary is narrower than generic self-hosting.

Permanent invariants:

1. only main-defined selected workflows may reach Mastermind-controlled runners;
2. fork/untrusted PR work remains hosted;
3. candidate YAML cannot redefine self-hosted admission;
4. candidate code receives no provisioning credential;
5. persistent home runners remain isolated/sealed; burst runners have no home/private-network route;
6. every burst machine is one-job ephemeral;
7. execution identity is explicit and verified;
8. JIT registration occurs only after machine attestation;
9. EC1 canary is dispatch-only and not production `ci-linux`;
10. no generic `self-hosted` route is introduced;
11. runner-group/workflow restriction drift is a hard refusal, not an autoscaler repair opportunity.

## 19. Rollback and emergency-disable model

Architecture is additive and reversible.

- If #6714/C3 fails: production remains three persistent slots.
- If four-slot production regresses: return `max-parallel`/live carrier inventory to three under C3 rollback law.
- If JIT canary fails: no production elastic eligibility exists.
- If queue-driven burst regresses: disable burst registration/provisioning; persistent four-slot route remains unchanged.
- If provider credentials/permissions are suspect: revoke provisioning principal/provider quota immediately; candidate jobs never possessed that credential.
- If provider is unavailable: local four-slot route remains canonical; no automatic provider failover.
- If wake adapter is unavailable: local capacity continues; missed burst is latency degradation, not proof corruption.
- If actuator grows beyond bounded capacity reconciliation: stop and reassess official Scale Set Client/ARC.

No rollback changes semantic CI, merge authority, fork execution or product code.

## 20. Acceptance ruler

The program is not complete when a fourth runner or cloud VM exists.

### Truth

- base/main structural integrity is visible through existing owner;
- every tested tree/plan/execution profile is exact;
- dependency/toolchain inputs are immutable or explicitly degraded;
- capacity state is derived from GitHub/provider evidence, not webhook memory;
- ambiguous effects fail closed.

### Intelligence / operability

- queue pressure is separated from broad ownership, inherited red, dependency failure, local fleet degradation and true saturation;
- receipts explain why capacity was or was not added;
- operator/Sol can distinguish queue, provision, registration, checkout, dependency, test and teardown time.

### Machine capability

- ordinary PRs receive four persistent trusted execution slots without render regression;
- genuine residual pressure can receive one isolated JIT slot without changing semantic authority;
- forks/untrusted work cannot reach Mastermind-controlled capacity;
- local fleet degradation is surfaced rather than silently hidden by first-release burst logic;
- loss of elastic infrastructure degrades to local capacity rather than CI correctness failure.

### Learning

- natural traffic measures p50/p95 final-push->gate improvement;
- launch usefulness/cost/parity/orphan rates are measured;
- evidence decides whether burst is retained, killed or graduated to a larger official scale-set mechanism.

## 21. Primary-source platform facts

Verified against current GitHub Enterprise Cloud documentation on 2026-09-01:

- GitHub routes self-hosted jobs by matching runner groups/labels; if an assigned runner does not pick up within 60 seconds, GitHub requeues the job; if no matching runner is online/idle, the job remains queued.
- GitHub recommends ephemeral self-hosted runners for autoscaling; an ephemeral runner receives one job and automatically deregisters.
- GitHub supports just-in-time runner configuration through self-hosted-runner REST APIs.
- `workflow_job` webhooks expose queued/in-progress/completed lifecycle actions but GitHub warns webhook timeliness can create autoscaling reliability concerns.
- GitHub recommends preserving ephemeral runner application logs externally before production autoscaling.
- When runner auto-update is disabled, GitHub currently requires runner versions to be updated within 30 days of a new release; critical security updates may make old runners ineligible sooner.
- GitHub warns that self-hosted runners on public repositories are dangerous because forked PRs may execute untrusted code; selected-workflow runner-group restrictions are therefore mandatory Mastermind law.

Primary references:

- https://docs.github.com/en/enterprise-cloud@latest/actions/reference/runners/self-hosted-runners
- https://docs.github.com/en/enterprise-cloud@latest/rest/actions/self-hosted-runners
- https://docs.github.com/en/enterprise-cloud@latest/actions/how-tos/manage-runners/self-hosted-runners/manage-access
- https://docs.github.com/en/actions/reference/security/secure-use

## 22. Final freeze and exact next actions

This document authorizes no runtime/provider implementation by itself.

Frozen sequence:

1. keep #6628 separate and finish its current proof/release loop;
2. keep #6714 as the one C3R-A source carrier; add only the profile/admission/queue-timing receipt requirements described here;
3. complete #6637/main-integrity and path-disjoint demand-reduction work under existing carriers;
4. complete C3R-A, separate C3R-B, then separate 3->4 production promotion with natural proof;
5. once four-slot production is proven, EC2A may begin read-only pressure telemetry while L3 closes portable execution;
6. EC1 proves one second-domain JIT runner through a dispatch-only canary capability with no production `ci-linux`;
7. EC2B proves fresh-read serialized reconciliation and effect handling while create remains disabled;
8. only EC3 may give one JIT runner production `ci-linux` eligibility under natural pressure;
9. EC4 decides from evidence whether elastic capacity deserves to live.

**DO NOT REBUILD:** GitHub remains scheduler/queue/assignment owner; existing Runner Fleet remains topology owner; existing semantic CI remains proof owner; existing merge controller remains merge owner. Elastic capacity is an actuator around available compute, never another execution lifecycle.
