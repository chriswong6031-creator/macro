# CI Elastic Pressure + Capacity Architecture Freeze

**Status:** records-only architecture freeze; implementation not started  
**Operation:** `ci-elastic-capacity-architecture-20260901-sol-001`  
**Parent program:** Macro #6351 / `WS:CI-MERGE-CONTROL-PLANE` + `WS:RUNNER-FLEET-RESILIENCE`  
**Protected Sol procedure at freeze:** `mastermindx-market-intelligence/Mastermind@7191702e3b0104525b6b26cd30ddb53d89a8a663`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Macro base at freeze:** `901d06e41c0ffd1ede7d26b55b1ca113c815694e`  
**Current fourth-slot source carrier:** Macro #6714 / `ci-pc-fourth-slot-recovery-20260901-sol-001`  
**Current red-fragment repair carrier:** Macro PR #6628  

## 1. Chairman outcome

Mastermind CI must remain reliable during simultaneous PR pressure without turning CI capacity into another scheduler, another retry plane, another proof store, or another source of semantic nondeterminism.

The target is not "more runners." The target is a pressure-resilient proof system in which:

1. deterministic structural defects are rejected before expensive fan-out and are mechanically difficult to merge into `main`;
2. ordinary trusted same-repository pack execution has four proven persistent Linux/x86 slots under one bounded PC resource envelope, with render capacity physically and semantically isolated;
3. false ownership, repeated dependency startup, unnecessary checkout, and stale balancing are reduced so demand shrinks before supply is expanded indefinitely;
4. when genuine eligible queue pressure still exceeds the four-slot local pool, at most one separately isolated ephemeral Linux/x64 burst runner may be added on demand;
5. GitHub Actions remains the sole job scheduler and job-to-runner matcher;
6. `ci-plan`, semantic fragments, `ci-gate`, CI authority, and merge control remain the sole existing proof/merge owners;
7. every capacity decision is fail-closed, bounded, measurable, correction-safe, and economically falsifiable;
8. capacity never converts a poisoned base, a coverage defect, dependency-network flake, or false ownership problem into "run more machines."

The 10/10 state is boring under load: a burst of PRs may increase compute, but it does not change proof semantics, fork trust boundaries, merge authority, runner identity law, or the operator's ability to explain why each job ran and where its evidence came from.

## 2. Current canonical state and capability ledger

This architecture extends current owners; it does not replace them.

| Capability | State at freeze | Canonical evidence / boundary |
|---|---|---|
| Three persistent sealed PC CI slots | `PROVEN_LIVE` | #6351 P1/P2/P3/P4 accepted path; current trusted executor targets `macro-home-canary` + `ci-linux` with `max-parallel: 3` |
| Trusted main-defined self-hosted executor | `PROVEN_LIVE` | `.github/workflows/trusted-ci-executor.yml`; fork/untrusted work remains hosted |
| Red trusted-pack evidence survives hosted relay into `ci-gate` | `BUILT_NOT_PROVEN` on current #6628 candidate | #6628 exact carrier; must not be conflated with capacity work |
| Fourth persistent PC slot source substrate | `SPEC_ONLY` | frozen plan `docs/superpowers/plans/2026-08-26-pc-ci-fourth-slot-resource-isolation.md`; fresh implementation issue #6714 has no worker `START` or code PR at this freeze |
| Fourth persistent PC slot host proof | `NOT_BUILT` | C3R-B is intentionally future privileged work |
| Ordinary production concurrency 3 -> 4 | `NOT_BUILT` | separate post-host-proof promotion carrier only |
| Main structural integrity / <2m poisoning refusal | `PARTIAL` / unresolved | #6637 remains open; Macro `main` has no server-side branch protection at this freeze |
| False-ownership / proof-graph reduction | `PARTIAL` | CI latency masterplan C2/L2 follow-up remains necessary; capacity is not a substitute |
| Immutable dependency environment/cache | `NOT_BUILT` as production contract | latency masterplan requires immutable dependency inputs; candidate jobs may consume but never mutate shared cache state |
| Hermetic result reuse | `NOT_BUILT` | later latency wave only after execution identity is closed |
| Elastic JIT burst runner | `SPEC_ONLY` after this architecture lands | no current implementation carrier, webhook scaler, scale-set deployment, cloud credential, or burst runner exists |

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
- a webhook-delivery cursor that is treated as canonical job state;
- a generic public-repository `self-hosted` path;
- a fork/untrusted route to persistent or elastic Mastermind-controlled runners.

A capacity reconciler may provision or remove **eligible compute only**. It never chooses a job for a machine. GitHub chooses among matching online/idle runners using the existing group/label contract.

## 4. Why the architecture is layered

Queue latency has at least four independent causes already recorded in the CI latency masterplan:

1. conservative ownership widens affected-job selection;
2. folded ownership makes one logical owner carry unrelated suites;
3. repeated checkout/tool/dependency setup delays useful execution;
4. stale balancing causes long pack tails.

A fifth cause is finite physical capacity during simultaneous PR pressure.

Adding runners attacks only cause five. Therefore the architecture deliberately separates **demand correctness**, **persistent capacity**, **portable execution**, and **elastic overflow**.

The intended maturity ladder is:

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

## 5. Persistent-capacity architecture: 3 -> 4

The existing fourth-slot plan remains controlling for C3R-A/C3R-B. This freeze does not replace it.

### 5.1 C3R-A — source/code substrate only

Macro #6714 remains the current carrier. It may re-derive frozen plan Tasks 1-5 from current `main` and produce a held code PR, while production remains exactly three slots.

In addition to the frozen plan's existing receipts, C3R-A must make the existing receipt path capable of carrying these forward-compatible identity fields wherever the current schema can be extended compatibly:

- `execution_profile_id` — stable semantic name for the reviewed execution environment, initially the persistent PC profile;
- `admission_policy_version` — version/hash identity of resource/admission thresholds independently from the systemd slice ceilings;
- queue timing fields sufficient to derive `job_created_or_queued -> runner_started` latency without confusing GitHub queue time with checkout or test time.

If the existing receipt schema cannot add these fields compatibly, the worker must stop for Sol rather than silently invent a parallel receipt format. A schema version bump is allowed only with explicit migration/comparator tests proving old P1/P2/P4 receipts remain honestly readable.

C3R-A must still perform zero live host/runner/group/label/credential/systemd/cgroup mutation and zero production `max-parallel` change.

### 5.2 C3R-B — privileged host proof

After C3R-A is accepted and merged, one separate privileged child may:

1. fresh-census the runner group, persistent runner identities, selected workflows, host resource state, existing unit bytes, render state and rollback packet;
2. install `/mastermind-ci.slice` and migrate only the four CI units into it at a natural drain;
3. bring `pc-ci-4` online initially **without `ci-linux`** so service/PID/root/cache/cgroup identity is provable while unroutable;
4. prove `pc-ci-1..4` are descendants of the exact CI slice and render remains outside it;
5. only after identity proof, add the existing `ci-linux` eligibility as one audited activation edge;
6. run exactly one `slots=4` diagnostic while a real/render-reservation workload proves coexistence;
7. accept or roll back under the frozen memory/swap/PSI/event/throttling limits.

The existing WSL envelope remains 16 CPU / 44 GiB memory / 8 GiB swap. Four-slot proof does not imply six or eight slots.

### 5.3 Separate production promotion

Only after C3R-B acceptance may a fresh carrier change trusted executor `max-parallel: 3 -> 4` and the exact live runner-policy carrier inventory. It must then prove at least three ordinary production PRs, including simultaneous PR pressure and active render, and roll back to three on semantic, cleanup, cache, queue, pressure or render regression.

## 6. Demand-reduction prerequisites before elastic production

Elastic capacity is intentionally **not** the next implementation immediately after C3.

### 6.1 Main integrity

The autoscaling path must not compensate for a known poisoned base. The existing #6637/main-integrity owner must provide a bounded machine-readable or directly queryable health condition from the existing proof path. The elastic controller may consume this condition; it may not create another "main health" implementation.

If the exact accepted base/control state is known structurally invalid, elastic scale-out is suppressed. Local production CI may continue under its existing law, but no paid/ephemeral capacity is added merely to accelerate inherited failure.

If health cannot be established from the existing owner, the first elastic production policy fails closed to **no burst** rather than manufacturing a new health check.

### 6.2 False ownership and fast preflight

C2/L2 work remains independently required. A small diff selecting most logical jobs is a proof-graph issue, not evidence that capacity should grow without bound. Any elastic-capacity acceptance report must separately state:

- selected logical-job count;
- selected pack count;
- whether a global invalidator or broad owner caused widening;
- queue time removed by extra capacity;
- compute time that would still exist after perfect queue removal.

This prevents capacity from hiding ownership debt.

### 6.3 Immutable dependency/toolchain inputs

A second physical failure domain is useful only if it can execute the same reviewed contract. Before a JIT runner becomes production-eligible, the dependency/toolchain layer must be sufficiently immutable that the burst route does not replace queue delay with internet-resolution nondeterminism.

Minimum contract:

- Python/Node/runtime versions are exact, not floating;
- dependency input identity is immutable and hashed;
- candidate jobs consume but cannot mutate shared dependency/cache state;
- missing/corrupt/stale cache forces a known live install/fetch path and is surfaced explicitly;
- a same-SHA parity corpus proves persistent-PC and burst execution agree on selected jobs and semantic result;
- no route may claim the PC execution profile when it actually ran a materially different cloud image.

Pack-specific sparse manifests/result reuse may land before or alongside this work under the latency masterplan, but remain separate carriers.

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

The first burst runner must not share the PC's physical host/WSL failure domain. Its intended role is both queue relief and failure-domain diversification.

Provider choice remains implementation-time and must satisfy:

- Linux/x64 environment compatible with the reviewed CI execution profile;
- immutable image or equivalent sealed bootstrap identity;
- short-lived machine lifecycle;
- provider-side hard concurrency/quota ceiling of one burst machine for the canary/first production wave;
- OIDC or another short-lived provisioning credential path for the hosted capacity actuator; no long-lived cloud credential in candidate jobs;
- network policy that provides no route to Mastermind home/private infrastructure;
- external runner/application log forwarding before production use;
- deterministic provider resource tags sufficient for effect reconciliation without a new capacity database.

The stationary macOS/ARM host is not a substitute for this Linux/x64 role.

### 7.3 Main-defined trust boundary

Macro is public, so a burst runner must never be generic PR self-hosted capacity.

A burst runner may register into the existing trusted runner group only after its image/bootstrap attestation succeeds and only with the exact labels needed by the already-main-defined trusted executor. The runner-group selected-workflow restriction remains mandatory.

Fork/untrusted PR execution remains GitHub-hosted. Candidate-edited workflow YAML must not grant persistent or elastic runner authority.

The burst candidate job receives no cloud-management credential, no home-network credential, no GitHub write credential, and no broader secret merely because the machine is ephemeral. The existing trusted executor permission boundary remains controlling.

### 7.4 Ephemeral/JIT lifecycle

GitHub currently recommends ephemeral runners for autoscaling and supports JIT configuration through its self-hosted-runner REST API. The expected lifecycle is:

```text
pressure wake
-> fresh reconciliation
-> provider creates one sealed machine (still not a GitHub runner)
-> image/bootstrap attestation passes
-> capacity actuator requests one JIT config for existing group + exact eligible labels
-> machine registers/starts ephemeral runner
-> GitHub assigns at most one matching job
-> runner executes existing trusted executor job
-> runner exits / GitHub auto-deregisters after one job
-> runner logs/receipts flush externally
-> machine self-terminates
-> later reconciler cleans only proven orphan residue if needed
```

Never generate/register the JIT runner before host/image attestation. Registration is the eligibility edge.

The ephemeral runner must use a reviewed runner software version embedded in the image or controlled bootstrap. If automatic runner updates are disabled, the image/update owner must satisfy GitHub's current runner-version support window; stale images become ineligible rather than updating themselves during a candidate job.

### 7.5 External log requirement

Before production eligibility, runner application logs and capacity-actuator logs must be exported off the ephemeral machine. The machine may disappear after one job, so local-only logs are not adequate production evidence.

Log forwarding is diagnostic evidence only. It is not a second CI proof store and cannot turn a missing semantic fragment into green.

## 8. Pressure detection and scale decision

### 8.1 Webhook is a wake signal, never truth

GitHub exposes `workflow_job` lifecycle events such as `queued`, `in_progress`, and `completed`, but documents webhook delivery timeliness as an autoscaling reliability concern.

Therefore:

- a webhook may wake the capacity reconciler;
- duplicate, delayed, out-of-order or missing webhook deliveries must not change correctness;
- the reconciler must fresh-read GitHub's actual eligible queued jobs and runner state before every scale decision;
- no webhook cursor/database is canonical job state;
- a scheduled/time-of-day signal may later prewarm infrastructure but may not independently authorize JIT registration.

### 8.2 GitHub-owned serialization

The first implementation must serialize reconciliation through a GitHub-owned concurrency primitive or another already-canonical single-flight mechanism. It must not implement its own lock database.

For a hosted Actions-based capacity actuator, the required shape is conceptually:

```text
concurrency group = one stable CI-capacity-reconcile group
cancel-in-progress = false
```

Each serialized run fresh-reads state after acquiring the slot. A stale queued reconcile run that discovers no pressure exits with `NO_SCALE`; it does not provision because its original wake was once valid.

If the chosen implementation surface cannot provide one bounded single-flight mechanism plus fresh provider/GitHub effect reconciliation, it must stop before production.

### 8.3 Eligible demand

Only jobs belonging to the existing trusted main-defined execution route may count toward burst demand. Generic Actions queue depth is irrelevant.

The pressure census must distinguish at least:

- eligible trusted-pack jobs queued;
- age of oldest eligible queued trusted-pack job;
- persistent `pc-ci` runners online/idle/busy;
- any already registered/provisioning ephemeral burst runner;
- current accepted main/base-integrity condition from the existing owner;
- provider hard quota/availability;
- current execution-profile eligibility.

Unknown/ambiguous eligibility widens to **no burst**, not "probably scale."

### 8.4 Initial trigger policy

Production thresholds are calibrated from natural four-slot traffic rather than guessed. The first canary may use provisional values solely to collect data.

The production trigger must require both:

1. **capacity saturation:** no eligible persistent slot is currently idle for the matching route; and
2. **sustained user-visible pressure:** a measured queue-age/depth threshold exceeded for eligible trusted packs.

The initial calibration hypothesis is approximately:

- oldest eligible trusted-pack wait >= 60-90 seconds, or another measured threshold that predicts final-push->gate SLO breach; and
- eligible queued pack count exceeds currently available persistent capacity.

Those numbers are not architecture authority until the four-slot natural corpus calibrates them.

Time of day is advisory only. A known peak window may justify pre-booting an unregistered image later, but cannot create `ci-linux` eligibility without live pressure and current attestation.

## 9. Effect reconciliation and duplicate suppression

Capacity provisioning is modifying external state and must have one stable effect identity.

The provider resource name/tag is deterministic for one reconcile decision, including at minimum the repository, burst role, execution-profile generation and a bounded reconcile identity. If the provision request times out or the client loses its response:

1. classify the provision effect as unknown;
2. do not issue another create;
3. query provider inventory for the deterministic resource identity;
4. query GitHub runner inventory for a corresponding JIT runner identity;
5. reconcile the existing effect or remain failed closed.

A duplicate `workflow_job` webhook must therefore converge on the already-existing provider/GitHub resource and may not create a second runner.

Provider inventory and GitHub runner inventory are source evidence; this architecture creates no durable capacity ledger.

## 10. Scale-in, teardown and orphan handling

The normal scale-in path is intentionally simple: one ephemeral runner processes one job, auto-deregisters, flushes logs/receipts and causes its machine to terminate.

Do not use the `workflow_job completed` webhook alone as permission to kill the VM. The local runner process exit plus GitHub runner/job state is the primary teardown fence, because event delivery and job-finalization timing can differ.

A safety reaper may remove an orphan only when all are true:

- provider resource exceeds the reviewed orphan age;
- no matching GitHub runner is busy;
- no matching eligible job is assigned/in progress;
- the resource identity matches the exact burst role/generation;
- logs/diagnostics have either flushed or the cleanup receipt explicitly records their loss;
- deletion effect is reconciled on ambiguity rather than blindly retried.

The first production implementation must also enforce a hard maximum instance lifetime derived from the trusted job timeout plus bounded provisioning/teardown margin. The exact lifetime is frozen in the provider-specific implementation carrier, not here.

## 11. Execution-profile identity

Capacity is only useful if evidence says truthfully **where and under what contract** it ran.

Every persistent or burst trusted receipt must carry or derive:

- `execution_profile_id`;
- runner name/kind;
- runner software version;
- OS/kernel/architecture identity required by the profile;
- Python/Node/toolchain identity;
- immutable dependency-input identity;
- image/bootstrap digest where applicable;
- admission-policy version/hash;
- tested SHA, base SHA and semantic plan SHA;
- selected logical jobs / pack index;
- GitHub queue timestamp, runner start timestamp, checkout/dependency/test/wall phases;
- semantic fragment/result;
- relevant resource and cleanup evidence.

Two execution routes may share a semantic profile only after mutation/parity proof demonstrates that the distinction is not semantically material. Otherwise their profile IDs remain different and the semantic layer must explicitly allow the route rather than falsifying identity.

## 12. Resource and economic bounds

### 12.1 Persistent PC bound

The current frozen C3 envelope remains:

- `/mastermind-ci.slice`
- `CPUQuota=800%`
- `CPUQuotaPeriodSec=100ms`
- `MemoryHigh=10G`
- `MemoryMax=12G`
- `MemorySwapMax=2G`

with the existing separate guard/acceptance thresholds and render outside the slice.

### 12.2 Elastic hard ceiling

The first burst environment has:

- maximum concurrent burst machines: 1;
- maximum eligible jobs per burst runner: 1;
- provider-side quota preventing accidental scale beyond one;
- bounded maximum machine lifetime;
- no automatic failover to a second provider;
- no automatic move from local to cloud merely because one provider call is slow;
- no capacity increase on ambiguous provisioning state.

This makes cost and blast radius bounded even if the trigger logic is wrong.

### 12.3 Economic acceptance

After a natural corpus, retain elastic capacity only if measured evidence shows it materially lowers relevant queue/final-push->gate latency without causing semantic nondeterminism, infrastructure-red growth, excessive provisioning delay, or disproportionate cost.

The receipt corpus must calculate at least:

- burst launch count;
- burst pickup success rate;
- provisioning-to-online latency;
- job queue time avoided versus a four-slot counterfactual/observed pressure window where possible;
- incremental compute cost;
- fraction of burst launches that executed useful work;
- parity/failure rate;
- same-SHA green->red nondeterminism count;
- orphan/cleanup failures.

If benefit is not demonstrated, the correct outcome is to disable/kill elastic production rather than preserving infrastructure because it was expensive to build.

## 13. Failure-state matrix

### Duplicate/delayed webhook
Fresh-read GitHub/provider state; serialized reconcile converges on `NO_SCALE` or one existing burst resource. No duplicate create.

### Webhook missing
Correctness is unchanged. Local four-slot capacity continues. A future low-frequency reconciliation sweep may improve responsiveness but is not necessary for job correctness.

### Provider create returns ambiguous/timeout
`EFFECT_UNKNOWN`; query deterministic provider identity and GitHub runner inventory. No blind second create or provider failover.

### Provider unavailable
No burst. Local capacity continues. Record `BURST_PROVIDER_UNAVAILABLE` in the non-authoritative capacity receipt.

### JIT configuration generated but machine never registers
No job authority exists on the machine. Reconcile provider resource/JIT runner state, let config become unusable/expire as appropriate, clean the known orphan after the accepted fence. Never reuse the configuration on a different machine.

### Runner registers but does not pick up assignment
GitHub's runner routing will requeue an assignment that is not accepted in its service window. Capacity logic does not retry the job. Reconcile and destroy only after proving the runner is not executing work.

### Runner software/image stale
Burst profile becomes ineligible. Update through a separately tested image release/canary; never hot-update during candidate execution merely to become eligible.

### External log forwarding unavailable
No production JIT eligibility. Diagnostic canary may fail with explicit missing-log evidence; semantic CI remains separate.

### Dependency/cache unavailable
Follow the reviewed execution-profile contract. Missing immutable cache must be explicit and may force a known live dependency path or refuse the burst profile; never silently change dependency versions.

### Main/base integrity known bad
Suppress burst scale-out. Do not spend elastic capacity accelerating an inherited structural incident.

### Main/base integrity unknown
First production policy fails closed to no burst unless the existing main-integrity owner provides an accepted `unknown-but-safe-to-scale` law. Do not invent one here.

### Semantic parity mismatch
Disable burst eligibility immediately. Existing local route remains canonical. Return to Sol for execution-profile adjudication.

### Cloud runner compromised by candidate code
One job only; no home-network route; no cloud-management credentials in job; no subsequent job; VM destruction after the job. Incident still requires normal security review—ephemerality reduces persistence, not seriousness.

### Burst cleanup fails
Do not create a second burst while the hard provider concurrency ceiling is occupied. Reconcile/remove the orphan or remain degraded.

### Four-slot local pressure exceeds frozen slice envelope
Roll production concurrency back to three under C3 law. Elastic capacity does not justify expanding WSL or local resource ceilings.

## 14. Observability and existing receipt extension

Do not create an autoscaler database.

Extend existing CI canary/timing/receipt paths with a bounded non-authoritative capacity section that can represent:

```text
capacity_trigger_source
eligible_queue_depth
oldest_eligible_queue_age_seconds
persistent_online
persistent_idle
persistent_busy
burst_resource_present
burst_runner_status
scale_decision = NO_SCALE | PROVISION_ONE | EFFECT_UNKNOWN | REFUSED
scale_reason
execution_profile_id
admission_policy_version
provider_resource_identity_hash_or_nonsecret_id
provision_started_at
runner_registered_at
runner_job_started_at
runner_job_completed_at
teardown_completed_at
```

Secrets, JIT config bytes, registration tokens, cloud credentials, instance metadata credentials and private host/network details are never receipts.

Capacity receipts are explanatory/operational evidence. They do not override semantic fragments or `ci-gate`.

## 15. Test and proof architecture

### 15.1 Deterministic source tests

The later implementation must have tests that kill at least these forbidden mutations:

- webhook payload directly authorizes create without fresh state read;
- two simultaneous reconcile wakes can create two instances;
- burst ceiling raised above one;
- fork/untrusted workflow becomes eligible for burst group;
- candidate-controlled workflow ref can reach burst runners;
- main-integrity known-red still provisions;
- unknown runner/image/profile registers as `ci-linux`;
- execution receipt omits profile identity;
- provider timeout triggers blind second create;
- cleanup kills a busy runner;
- job-completed webhook alone kills the VM;
- JIT runner receives more than one job;
- burst route receives cloud-management/home-network credentials;
- missing external runner logs is treated as production-ready;
- capacity receipt is allowed to make semantic CI green;
- time-of-day alone registers burst capacity.

### 15.2 Manual/JIT canary before automation

Before queue-driven automation, prove one manually authorized JIT canary through the existing trusted executor contract:

1. one sealed second-domain machine;
2. exact image/profile/runner version attestation;
3. one JIT registration into the existing selected-workflow runner group;
4. one exact non-destructive diagnostic candidate/pack;
5. semantic parity to hosted/persistent control as defined by current evidence law;
6. one-job deregistration;
7. external log preservation;
8. machine termination and zero provider/GitHub orphan residue.

A manual canary proves the execution substrate, not autoscaling.

### 15.3 Queue-driven canary

Only after manual canary PASS:

- enable serialized pressure reconciliation with ceiling one;
- use natural queue pressure, not an intentionally poisoned product PR;
- record trigger, fresh-state census, provisioning, registration, GitHub pickup, semantic result, teardown and cost;
- a false-positive scale may execute no job and still be valuable evidence, but repeated useless launches fail economic acceptance.

### 15.4 Production acceptance corpus

Elastic production remains `BUILT_NOT_PROVEN` until at least 30 natural qualifying pressure events or another preregistered statistically/operationally adequate corpus is accumulated, containing:

- several simultaneous-PR pressure windows;
- at least one window with active render on the independent route;
- successful no-scale decisions;
- successful scale-and-execute decisions;
- at least one provider-unavailable or intentionally disabled-burst negative control if it occurs naturally/can be tested without disrupting product traffic;
- zero same-SHA semantic nondeterminism attributable to route;
- zero fork/untrusted burst executions;
- zero duplicate burst resources from duplicate wakes;
- zero orphaned busy-runner deletions;
- bounded cost and demonstrable p95 queue/final-gate improvement.

Do not manufacture semantic reds merely to complete the corpus.

## 16. Phased implementation program

Each phase is an independently bounded carrier. Do not combine them because the architecture is broad.

### EC0 — records/source contracts only

This architecture freeze. No runner, webhook, provider or workflow behavior changes.

### C3R-A / C3R-B / C3-PROMOTE — persistent four-slot capacity

Continue existing #6714 and frozen C3 plan. Add the three forward-compatible receipt identities without expanding C3's host/production authority.

### L3 — immutable dependency/execution profile closure

Use the existing latency masterplan owner. Freeze portable dependency/toolchain identity and same-SHA parity requirements. No elastic provisioning yet.

### EC1 — second-domain JIT substrate canary

One new carrier. Provider selection, immutable image/bootstrap, external log path, OIDC/provisioning boundary, deterministic resource identity, one manual JIT runner, one diagnostic job, teardown. No webhook scaling.

### EC2 — read-only pressure classifier + serialized actuator dry run

One new carrier. Wake adapter and reconciler fresh-read GitHub/provider state, but production create is disabled. Replay real historical/natural queue events and prove decisions, duplicate suppression and fail-closed ambiguity.

### EC3 — one-runner queue-driven canary

One new carrier. Enable `PROVISION_ONE` with provider hard ceiling one under natural pressure. No second provider and no scale >1.

### EC4 — production acceptance / rollback soak

Accrue the natural corpus, evaluate queue improvement, cost, parity and cleanup. Promote to `PROVEN_LIVE` only after the preregistered gates hold.

### EC5 — optional capacity expansion

Not authorized by this freeze. Only if four persistent + one burst still misses SLOs after demand-reduction waves may a future Sol architecture decide whether a second burst runner, GitHub Actions Runner Scale Set Client, ARC, or another official capacity mechanism is justified.

## 17. Why not ARC or a large scale set now

GitHub currently presents ARC as the reference Kubernetes implementation and also offers a standalone Runner Scale Set Client for custom VM/container infrastructure. Both are legitimate future mechanisms.

Mastermind's current need is much smaller: one repository, four persistent runners, and at most one burst runner. Introducing Kubernetes/ARC or a large scale-set control surface before measured need would add an operational failure domain and deployment/upgrade burden without improving the initial acceptance question.

The escalation rule is:

- `0 -> 1` burst runner: bounded JIT architecture above;
- recurring need for multiple elastic runners, multi-repo routing, or webhook responsiveness becoming the dominant reliability risk: evaluate GitHub's Scale Set Client first, and ARC when Kubernetes infrastructure/expertise is independently justified;
- never keep extending a hand-rolled scaler into a general scheduler.

## 18. Security invariants for a public repository

GitHub's current documentation warns against self-hosted runners for public repositories because forked PR code can be dangerous. Mastermind's exception remains acceptable only because the execution boundary is intentionally narrower than generic self-hosting.

Permanent invariants:

1. only the existing main-defined trusted executor is runner-group eligible;
2. fork/untrusted PR work is hosted;
3. candidate YAML cannot redefine the self-hosted admission workflow;
4. candidate code receives no provisioning credential;
5. persistent home runners remain isolated/sealed; burst runners have no home/private-network route;
6. every burst machine is one-job ephemeral;
7. execution identity is explicit and verified;
8. JIT registration occurs only after machine attestation;
9. no generic `self-hosted` route is introduced;
10. a runner-group/workflow restriction drift is a hard admission refusal, not an autoscaler repair opportunity.

## 19. Rollback model

The architecture is deliberately additive and reversible.

- If #6714/C3 fails: production remains three persistent slots.
- If four-slot production regresses: return `max-parallel` and live carrier inventory to three while retaining the proven-but-idle fourth host only if current C3 rollback law allows.
- If JIT canary fails: no autoscaling is enabled.
- If queue-driven burst regresses: disable burst registration/provisioning; persistent four-slot route remains unchanged.
- If provider credentials/permissions are suspect: revoke the provisioning principal; no candidate job has that credential.
- If provider becomes unavailable: local four-slot route remains canonical; no automatic provider failover.
- If the scaler implementation becomes more complex than a bounded capacity actuator: stop and reassess official Scale Set Client/ARC rather than creating another internal platform.

No rollback changes semantic CI, merge authority, fork execution, or product code.

## 20. Acceptance ruler for the whole pressure-resilience program

The program is not complete when a fourth runner or cloud VM exists. Completion requires:

### Truth

- base/main structural integrity is visible through the existing owner;
- every tested tree/plan/execution profile is exact;
- dependency/toolchain inputs are immutable or explicitly degraded;
- capacity state is derived from GitHub/provider evidence, not webhook memory;
- corrections/ambiguous effects fail closed.

### Intelligence / operability

- queue pressure is separated from broad ownership, inherited red, dependency failure and runner outage;
- receipts explain why capacity was or was not added;
- operator/Sol can distinguish queue wait, provisioning, checkout, dependency, execution and teardown time.

### Product / machine capability

- ordinary PRs receive four persistent trusted execution slots without render regression;
- genuine residual pressure can receive one isolated JIT slot without changing semantic authority;
- forks/untrusted work cannot reach Mastermind-controlled capacity;
- loss of elastic infrastructure degrades to local capacity rather than CI correctness failure.

### Learning

- natural traffic demonstrates whether added capacity actually improves p50/p95 final-push->gate latency;
- launch usefulness/cost/parity/orphan rates are measured;
- evidence determines whether the burst system is retained, killed or graduated to a larger official scale-set mechanism.

## 21. Primary-source platform facts relied on by this freeze

Verified against current GitHub Enterprise Cloud documentation on 2026-09-01:

- GitHub routes self-hosted jobs by matching runner group/labels; if an assigned runner does not pick up within 60 seconds, GitHub requeues the job; if no matching runner is online/idle, the job remains queued.
- GitHub recommends ephemeral self-hosted runners for autoscaling; ephemeral registration receives one job and then automatically deregisters.
- GitHub supports just-in-time runner configuration through self-hosted-runner REST APIs.
- `workflow_job` webhook events expose lifecycle actions including queued/in-progress/completed and may be used to wake autoscaling logic, but GitHub warns webhook timeliness can introduce reliability concerns.
- GitHub recommends external preservation of ephemeral runner application logs before production autoscaling.
- GitHub warns that self-hosted runners on public repositories are dangerous because forked PRs may execute untrusted code; runner-group workflow restrictions are therefore a mandatory Mastermind boundary, not optional hardening.

Primary references:

- https://docs.github.com/en/enterprise-cloud@latest/actions/reference/runners/self-hosted-runners
- https://docs.github.com/en/enterprise-cloud@latest/rest/actions/self-hosted-runners
- https://docs.github.com/en/enterprise-cloud@latest/actions/how-tos/manage-runners/self-hosted-runners/manage-access
- https://docs.github.com/en/actions/reference/security/secure-use

## 22. Final freeze and exact next actions

This document authorizes no implementation by itself.

Frozen sequence:

1. keep #6628 separate and finish its current proof/release loop;
2. keep #6714 as the one C3R-A source carrier; add only the forward-compatible execution-profile/admission-policy/queue-timing receipt requirements described here;
3. complete #6637/main-integrity and path-disjoint demand-reduction work under their existing carriers;
4. complete C3R-A, then separate C3R-B, then separate 3->4 production promotion with natural proof;
5. close portable immutable execution-profile prerequisites;
6. only then commission EC1 manual second-domain JIT canary;
7. EC2 proves the fresh-read serialized pressure reconciler without provisioning authority;
8. EC3 enables one burst runner under natural pressure;
9. EC4 decides from evidence whether elastic capacity deserves to live.

**DO NOT REBUILD:** GitHub remains scheduler/queue/assignment owner; existing Runner Fleet remains topology owner; existing semantic CI remains proof owner; existing merge controller remains merge owner. Elastic capacity is an actuator around available compute, never another execution lifecycle.
