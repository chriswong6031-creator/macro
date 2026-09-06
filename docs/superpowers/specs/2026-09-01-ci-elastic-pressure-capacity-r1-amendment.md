# CI Elastic Pressure + Capacity Architecture — R1 Truth/Continuity Amendment

**Status:** records-only amendment; no runner, workflow, provider, ruleset, host, queue, merge, credential, or production effect  
**Operation:** `ci-elastic-capacity-architecture-20260901-sol-001`  
**Parent:** Macro #6351 / `WS:CI-MERGE-CONTROL-PLANE` + `WS:RUNNER-FLEET-RESILIENCE`  
**Amends:** `docs/superpowers/specs/2026-09-01-ci-elastic-pressure-capacity-design.md`  
**Protected procedure:** `mastermindx-market-intelligence/Mastermind@21a721427743fdae6d513eeb0f993ebd1c327a81`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  
**Action-time Macro main:** `88ac6cfd664b442633374ff788281a59fb2e137e`  
**Current persistent-capacity carrier:** Macro #6714 / PR #6718  
**Current main-integrity carrier:** Macro #6637 / PR #6665  

## 0. Precedence and scope

This file is an amendment inside the same architecture operation and carrier as the original freeze. It is not a second capacity design, runner registry, liveness store, scheduler, queue, monitor, proof plane, main-health gate, worker lifecycle, or host-control system.

Where this amendment conflicts with the original freeze, **R1 wins**. The original freeze remains controlling everywhere else.

R1 closes five ambiguities exposed by exact-head implementation review and live incident recovery:

1. per-runner cgroup membership is not aggregate parent-slice evidence;
2. a strict four-slot profile that is never reached by the real workflow is dead code, not a gate;
3. a static runner declaration is not live runner or queue truth;
4. a required check name produced by the generic GitHub Actions integration is not an immutable required workflow;
5. a remote Git head is not complete effect reconciliation when a started worker's exact runtime/worktree can disappear with unknown local state.

This amendment authorizes no implementation by itself.

## 1. Incident evidence and corrected capability ledger

### 1.1 Persistent fourth-slot source

Macro PR #6718 reached exact head `88c0cb704d065e600fa83f3417acd8730e48603f` while preserving the important production boundary:

- `pool_topology.pc-ci.slots = 3`;
- `ci-linux.carried_by = [pc-ci-1, pc-ci-2, pc-ci-3]`;
- production trusted-executor `max-parallel = 3`;
- `pc-ci-4` pending/unroutable only;
- no registration, label, systemd, host, cgroup, credential, canary, or production-concurrency effect.

Exact-head CEO review nevertheless returned `REQUEST_CHANGES` because the implementation could produce false aggregate-resource proof. The source substrate remains `PARTIAL / RELEASE_BLOCKED`, not `BUILT_NOT_HOST_PROVEN`, until the blockers below close.

### 1.2 Main integrity

PR #6665 exact head `13165711cc8edfe4d72b161e11d013844ff36610` puts the canonical Agent OS whole-store validator into the existing fast fence. Natural hosted evidence shows the validator itself completes in roughly four seconds and the complete fence job in roughly forty seconds on the observed run. This is a useful `FAST_AGENTOS_REJECTION` capability.

It is **not** an unbypassable native main interlock. Same-repository `pull_request` workflow YAML is candidate-controlled, and GitHub Actions Integration `15368` is the broad Actions App rather than one exact protected workflow definition. PR #6665 therefore may become `BUILT` as a fast signal while #6637 remains `EVALUATE_ONLY / NON_ENFORCING` until C0C/C0D close.

### 1.3 Host/runtime continuity

The original #6718 writer started on exact RuntimeBinding `2cb9f91d-96e2-4fb9-8dcf-5d509cc90d68` with recorded worktree `.claude/worktrees/fourth-slot-source-recovery-19eb45`. The remote source effect is known, but later loss of the exact Mac Studio control path made local post-effect state and exact runtime identity unprovable.

That state is correctly classified:

```text
REMOTE_EFFECT_KNOWN
LOCAL_EFFECT_UNKNOWN
RUNTIME_BINDING_RECONCILIATION_REQUIRED
NO_FAILOVER
```

A replacement writer may not inherit the started operation merely because the branch is visible remotely.

### 1.4 Corrected ledger

| Capability | R1 state | Release boundary |
|---|---|---|
| Three persistent PC CI slots | `PROVEN_LIVE` | Existing #6351 accepted production path |
| Fourth-slot declaration + source scaffold | `PARTIAL / RELEASE_BLOCKED` | #6718 exact-head blockers unresolved |
| Parent-slice aggregate proof | `NOT_BUILT` | Current candidate reads the wrong cgroup level |
| Fourth physical listener | `NOT_BUILT` | C3R-B only after source acceptance |
| Production concurrency 3→4 | `NOT_BUILT` | Separate post-C3R-B carrier |
| Fast Agent OS rejection | `BUILT_NOT_MERGED` | #6665 exact-head proof/review/merge outstanding |
| Native immutable main interlock | `PARTIAL / EVALUATE_ONLY` | Exact publisher identity + exact required workflow + canaries outstanding |
| Live fleet/queue projection | `NOT_BUILT` | Existing Runner Fleet W5/EC2A owner; no second registry |
| Elastic one-runner burst | `SPEC_ONLY` | Held behind main integrity, four-slot proof, live projection, and portability |

## 2. Parent-slice evidence contract

### 2.1 Two identities, never one overloaded path

Every persistent CI observation must distinguish:

```text
candidate_cgroup = /mastermind-ci.slice/<exact-runner-service>.service
aggregate_cgroup = /mastermind-ci.slice
```

`candidate_cgroup` proves **membership and exact service identity** for one runner process tree.

`aggregate_cgroup` proves the **combined parent envelope and aggregate counters** for every CI listener inside the shared slice.

A candidate service cgroup is never an acceptable substitute for the aggregate parent, even when its path contains `/mastermind-ci.slice/`. A host-global sample is never an acceptable substitute for either identity.

### 2.2 Direct membership law

The accepted shape is exactly one direct service child beneath the fixed parent:

```text
/mastermind-ci.slice/<expected-systemd-service>.service
```

Reject:

- nested descendants used as the service identity;
- `..`, symlink, prefix/suffix, Unicode-lookalike, repeated-slash, or lexical-only matches;
- another `.service` component deeper in the path;
- a service name not bound to the expected `pc-ci-N` unit;
- one sample changing candidate service identity during the window.

Where available, capture stable kernel identity for both candidate and parent nodes—such as cgroup inode/id—in addition to canonical path. If the identity changes during one acceptance window, classify the window `CGROUP_RECREATED_OR_CHANGED`; emit no numeric acceptance fields.

### 2.3 Exact parent envelope

The parent node must expose and exactly match:

```text
cpu.max          = 800000 100000
memory.high      = 10737418240
memory.max       = 12884901888
memory.swap.max  = 2147483648
```

The source template may use systemd units (`CPUQuota=800%`, `CPUQuotaPeriodSec=100ms`, `MemoryHigh=10G`, `MemoryMax=12G`, `MemorySwapMax=2G`), but runtime proof is the effective parent cgroup files—not template prose and not child-local limits.

Missing, unreadable, malformed, unlimited, or different parent limits are `PARENT_ENVELOPE_UNPROVEN` and fail the strict profile. Admission-policy identity remains separate from envelope identity; changing one must not silently restamp the other.

### 2.4 Aggregate counters

Read aggregate acceptance counters from the parent node only:

- `cpu.stat` / `cpu.pressure`;
- `memory.current`, `memory.peak`, `memory.events`, `memory.pressure`;
- `memory.swap.current`;
- `pids.current`, `pids.max`;
- `io.pressure`;
- any later accepted parent-only fields.

Per-runner service counters may be recorded separately for diagnosis, but they cannot drive the combined-slice acceptance verdict.

The receipt must make provenance explicit:

```text
candidate_cgroup_path
candidate_cgroup_identity
aggregate_cgroup_path
aggregate_cgroup_identity
aggregate_cpu_max_quota_us
aggregate_cpu_max_period_us
aggregate_memory_high_bytes
aggregate_memory_max_bytes
aggregate_memory_swap_max_bytes
aggregate_metric_source = parent_slice
```

No field may be populated from a different level while retaining these names.

### 2.5 Time and monotonicity

Every sample carries one mechanically comparable timestamp and one fixed parent/candidate identity tuple. The reducer must verify:

- timestamps are strictly increasing;
- cumulative counters never decrease;
- the sample window names one parent identity and one candidate identity per candidate stream;
- missing required samples are not converted to zero;
- a counter reset, time reversal, process/service restart, cgroup recreation, or mixed identity makes the window non-bound.

Negative event/throttling/pressure deltas are impossible as acceptance values. They are evidence of reset/reorder/identity change and must fail closed.

`memory.peak` remains a cgroup-lifetime high-water mark, not a run-local delta. The receipt must label it accordingly.

### 2.6 Null and unavailable law

For every strict acceptance input:

```text
absent != zero
unparseable != zero
permission_denied != zero
wrong_cgroup != zero
identity_changed != zero
```

The strict four-slot profile requires present, parseable memory and I/O PSI `full avg10` observations. Missing or malformed PSI is `UNAVAILABLE`, not safe pressure.

A readable keyed file missing a required key is degraded/unproven. The parser may preserve optional diagnostic fields as null, but strict acceptance cannot pass without every required input.

## 3. Four-slot end-to-end gate

### 3.1 One real journey

The strict profile must be reached by the actual `slots=4` workflow path. A profile that exists only as a CLI option or runbook command is `DARK_OR_DISCONNECTED`.

Required journey:

```text
main-defined dispatch requests slots=4
-> hosted trust/input gate validates exact PR/ref and current source law
-> one no-checkout strict preflight runs on the existing persistent PC failure domain
-> preflight proves expected live identities, exact parent slice/envelope, required PSI/disk/memory/swap headroom, and no mixed admission bytes
-> only successful preflight releases four-way diagnostic fanout
-> each candidate job re-proves its exact service membership and same parent envelope
-> existing monitor/receipt records candidate + aggregate evidence
-> hosted comparator/semantic owner consumes all four fragments/receipts
-> render-reservation coexistence is proved
-> any missing/refused/identity-changed evidence makes the diagnostic fail
```

Use the existing workflow, guard, monitor, receipt, comparator, runner group, and semantic proof path. Do not create another scheduler, queue, monitor, receipt schema, or gate.

### 3.2 Preflight placement

The first strict preflight must run before four candidate jobs are admitted. It must not require a candidate checkout or execute candidate-controlled code. It may use one existing selected main-defined diagnostic job on the shared PC host/failure domain.

The preflight proves the guest/parent envelope and current runner inventory are ready for four-way admission. It does not replace per-runner membership proof during the jobs.

### 3.3 Installation atomicity

C3R-B installs as one drain-bounded unit:

- parent slice definition;
- updated root-owned guard/helper that understands the exact parent contract;
- all existing `pc-ci-1..3` service units migrated to the slice;
- new `pc-ci-4` service unit/root, initially without production `ci-linux` eligibility;
- exact rollback snapshots.

Do not install a service unit with `--require-slice` while the old helper or absent parent slice would make existing listeners restart-loop. Installation must validate bytes before daemon reload/start, drain existing jobs, apply the complete tuple, start one listener at a time, and roll back all changed units/helpers on first failure.

### 3.4 Root sealing

An allowlisted literal path is insufficient when the root itself can be a symlink. Before cleanup or listener start:

- resolve and compare the runner root to the expected canonical root;
- reject symlinked roots and any ancestor/path traversal ambiguity;
- prove `_work`, toolcache, temp, hook, service user, and cache paths remain inside their accepted roots;
- add hostile proof that `/opt/mastermind-ci/runner-4 -> <foreign-tree>` is refused without touching the target.

## 4. Static topology versus live fleet truth

### 4.1 One owner per fact

- `.github/runner-policy.yml` owns **declared topology and allowed capability relationships**.
- GitHub runner/job APIs plus accepted host receipts own **current online/idle/busy/job assignment observations**.
- GitHub Actions owns **queue and assignment state**.
- existing CI receipts own **execution and timing observations**.
- Runner Fleet W5/EC2A owns the **read-only projection that joins those sources**.

The projection owns no scheduler, assignment, retry, runner registration, queue mirror, or durable liveness truth.

### 4.2 Split the overloaded W5 dependency without creating a new workstream

The existing W5 title combines two separable capabilities. On the next collision-safe Agent OS reconciliation, preserve `WS:RUNNER-FLEET-RESILIENCE` and split its internal wave only:

```text
W5A — hosted read-only live fleet + queue projection
  depends on: W1, W3, accepted PC trusted-CI route; C3 fields expand when four-slot proof lands
  does not depend on W4 M1 admission

W5B — retire obsolete M2 roles
  depends on: W1, W3, W4 and rollback-soak evidence
```

This prevents unresolved M1 capacity from blocking visibility into the already-live PC CI fleet. It creates no new program/workstream.

### 4.3 Projection contract

One fresh projection may represent:

```text
observed_at
source_freshness
repository
runner_group
expected_persistent_slots
expected_carriers
observed_registered_carriers
persistent_online
persistent_idle
persistent_busy
missing_expected_carriers
unexpected_carriers
eligible_queue_depth
oldest_eligible_queue_age_seconds
in_progress_eligible_jobs
execution_profile_ids
admission_policy_versions
host_control_reachable = true | false | unknown
classification
reasons[]
```

Closed classifications:

```text
HEALTHY_IDLE
HEALTHY_BUSY
HEALTHY_SATURATED
DEGRADED_MISSING_EXPECTED_RUNNER
DEGRADED_IDENTITY_OR_POLICY_DRIFT
DEGRADED_HOST_CONTROL_UNREACHABLE
UNKNOWN_STALE_OR_UNAVAILABLE
```

`HEALTHY_SATURATED` requires every expected persistent identity online, zero idle slots, and eligible queued work. A static `status: live` value can never establish it.

`DEGRADED_MISSING_EXPECTED_RUNNER` is not inferred merely because a job waited; it requires fresh runner inventory proving an expected identity absent/offline. Queue pressure with all expected runners busy is saturation, not outage.

`UNKNOWN` never becomes zero/healthy. Stale projection may be displayed with age but cannot authorize host mutation, promotion, or elastic provision.

### 4.4 No liveness database

The projection is derived on demand or emitted as bounded append-only operational evidence through an existing receipt/publication path. Correctness must not depend on replaying a custom cursor or persisting a shadow queue.

Webhook data may wake a refresh but never supplies canonical queue truth. Every actionable decision fresh-reads current GitHub runner/job state after acquiring the existing serialized decision slot.

## 5. Main integrity must bind an exact trusted workflow

### 5.1 Fast signal versus native enforcement

C0A’s fast fence is useful for early rejection and operator clarity. It is not the final native interlock because candidate-controlled workflow YAML can affect same-repository `pull_request` checks.

A required status **name** plus broad GitHub Actions Integration ID does not prove the check came from the exact trusted validator workflow.

### 5.2 C0D exact required-workflow law

Before ruleset `21813020` becomes Active, #6637 must qualify a native required workflow through GitHub’s organization/enterprise ruleset workflow mechanism, or independently prove an equivalent exact-workflow binding on the current GitHub surface.

The exact required workflow must:

1. be selected by immutable repository/path/ref identity under protected administration;
2. run for the required `pull_request` and `merge_group` contexts;
3. use GitHub-hosted isolated compute;
4. resolve the immutable candidate SHA/base/ancestry as data;
5. execute protected validator/control bytes—not candidate workflow/script/dependency-hook bytes;
6. pass no write or publisher credential into candidate execution;
7. emit/bridge the existing semantic result rather than create a second main-health or merge gate;
8. fail closed on missing candidate identity, invalid ancestry, missing evidence, wrong workflow source, or stale result;
9. prove that candidate edits to `.github/workflows/fences.yml`, `.github/workflows/ci.yml`, job/check names, or publication code cannot satisfy the native rule.

Do not use privileged `pull_request_target` to check out and execute candidate code. If that event is used as a trusted orchestration surface, candidate material remains inert data and every executed byte comes from the trusted source.

### 5.3 C0C publisher identity remains separate

Native required workflows will block ordinary direct pushes. The accepted bypass is exactly one dedicated `Macro Production Publisher` GitHub App:

- metadata read + contents write only;
- installed only on Macro;
- no workflow/Actions/check/status/PR/issue/admin/organization authority;
- short-lived repository-narrowed installation tokens;
- credentials absent from candidate jobs;
- exact Integration ID admitted only after negative proof.

The App is a principal, not a scheduler, queue, merge controller, publisher workflow, or state store.

### 5.4 Activation order

```text
C0A fast signal merged and measured
-> C0C exact publisher App created/installed and each natural publisher migrated one at a time
-> C0D exact required workflow qualified
-> Evaluate canaries: known green merge, known red rejection, direct-push rejection, natural publisher success, rollback
-> Active ruleset
```

Do not activate based only on green check names. Do not grant a user/PAT/generic Actions App broad bypass to make activation convenient.

Elastic EC1/EC2 preparation may remain records-only, but no paid production burst and no production four-slot promotion may rely on “main healthy” until #6637 supplies a current exact-workflow/native-enforcement result.

## 6. Runtime and host continuity contract

### 6.1 Recovery identity at START

Every modifying host/repository worker operation records, in its existing carrier/receipt surfaces:

```text
operation_key
RuntimeBinding / native task or exact session identity
host identity (nonsecret stable reference)
worktree absolute path
Git common-dir identity or nonsecret hash
branch
local HEAD
upstream remote/ref
remote head
status_porcelain_v2_digest
started_at
```

This is not a session registry. It is a bounded recovery receipt attached to the existing operation, allowing an authorized exact-host read to determine whether local effect remains after session loss.

### 6.2 Checkpoint after each material Git effect

After commit/push/PR-head change, the worker fresh-reads the carrier and records:

```text
new local HEAD/tree/parents
new remote head
push mode = non_force | force_with_lease
expected old remote head when force-with-lease is used
staged/unstaged/untracked path census
local-only commits count/digest
worktree path/common-dir identity
```

A remote push proves remote effect only. It does not prove the local worktree is clean or that no later local-only commit exists.

### 6.3 Session-loss reconciliation

When the exact reasoning session disappears:

1. freeze same-operation writes;
2. query remote Git/PR state;
3. restore one previously approved exact-host control path;
4. inspect the recorded exact worktree read-only;
5. classify local/remote effect precisely;
6. continue the same operation only in the original RuntimeBinding when it is provably alive and current law permits;
7. otherwise terminally stop/reconcile the old child before any fresh operation is commissioned.

Never bind a replacement session by Slack seat/display name alone. Never copy a dirty worktree into a new branch to evade effect reconciliation.

### 6.4 Host-control reachability as operational health

Runner process liveness and host-control reachability are separate axes. A runner may execute jobs while the approved administrative path is unavailable; that state is operationally degraded because incident response, exact worktree reconciliation, and safe drain/install cannot be performed.

W5A may project `host_control_reachable`, but that field is descriptive only. It never authorizes host actions or changes the GitHub runner’s online status.

### 6.5 No second host-control plane

Recover existing approved local-exec/Tailscale/OpenClaw paths in place. Do not create a second Gateway, duplicate node identity, replacement machine registry, parallel SSH credential, or new host daemon merely because one control path is down.

Repair proceeds identity-first:

```text
read-only topology census
-> exact existing service/node identity
-> smallest restart/start only when effect is unambiguous
-> post-repair identity and benign-command proof
```

Install/pair/config/credential changes require a separate explicit gate.

## 7. Revised implementation sequence

The architecture now admits parallel work only where authority/path surfaces are disjoint:

1. **C0A fast fence:** conclude #6665 exact-head proof and land only as early deterministic rejection.
2. **C0C/C0D main integrity:** create/qualify the exact publisher identity and exact required workflow; keep ruleset Evaluate until natural canaries pass.
3. **C3R-A source repair:** reconcile original runtime/worktree, repair the parent-slice/workflow/root-sealing blockers on the same #6718 carrier, obtain fresh exact-head CI and independent review, then merge only to `BUILT_NOT_HOST_PROVEN`.
4. **C3R-B host proof:** drain, atomically install parent slice/helper/service tuple, bring `pc-ci-4` online without production `ci-linux`, prove exact identities/envelope, and run one strict four-slot + real-render diagnostic.
5. **C3-PROMOTE:** separate carrier adds the exact live inventory and moves `max-parallel: 3→4`; accrue ordinary PR/load proof and rollback on regression.
6. **W5A/EC2A read-only projection:** fresh live runner/queue/host-control projection and dry-run pressure classification through existing evidence paths.
7. **Portable execution/L3 and EC1/EC2:** only then prepare one second-domain JIT canary and dry actuator.
8. **EC3/EC4:** paid production burst only after main integrity, four-slot production, profile parity, logs, and no-duplicate effect proof.

No wave may call the next wave complete merely because its substrate merged.

## 8. Discriminating tests and proof additions

### 8.1 Persistent C3 mutations that must die

- aggregate metrics read from child service instead of parent slice;
- parent `cpu.max`, `memory.high`, `memory.max`, or `memory.swap.max` absent, malformed, unlimited, or changed;
- missing/unparseable memory or I/O PSI treated as safe;
- strict `slots=4` preflight removed, made non-blocking, or run after fanout;
- candidate/nested/lookalike cgroup accepted;
- timestamp reversal, cumulative-counter regression, parent/candidate identity change, or cgroup recreation produces numeric deltas;
- allowlisted runner root is a symlink;
- pending labels empty/subset/duplicated/non-string/malformed;
- live roster or production `max-parallel` changes in C3R-A.

### 8.2 Live-projection mutations that must die

- static policy `status: live` counted as online;
- queue wait alone classified as runner outage;
- stale/unavailable GitHub inventory converted to zero/healthy;
- webhook payload used as authoritative queue state;
- unexpected runner identity silently expands capacity;
- projection creates a durable cursor/queue mirror or assigns work;
- missing expected runner produces `HEALTHY_SATURATED`;
- host-control unreachable relabeled as runner offline.

### 8.3 Main-integrity mutations that must die

- candidate edits the workflow/job/check name and still satisfies the native rule;
- generic Actions Integration ID is treated as exact workflow identity;
- privileged orchestration executes candidate bytes with write credentials;
- direct push by an ordinary user/PAT succeeds after Active;
- publisher App receives workflow/check/PR/admin/org authority;
- known-red candidate merges because one context is skipped/missing/stale;
- ruleset Active is enabled before rollback canary and natural publisher proof.

### 8.4 Continuity mutations that must die

- same Slack seat is accepted as the lost exact RuntimeBinding;
- remote head equality is treated as proof of clean local worktree;
- unknown local effect triggers replacement-writer failover;
- recorded worktree path resolves to a different Git common-dir/host;
- host-control outage creates a new Gateway/node/machine identity;
- service restart with unknown active effect is blind-retried.

## 9. R1 acceptance ruler

R1 architecture is accepted when a fresh session can answer, without this chat:

- which layer owns declared capacity, live runner state, queue state, execution evidence, and host-control reachability;
- why parent-slice evidence and per-runner membership require separate identities;
- exactly which runtime fields prove the 8-CPU/10G/12G/2G envelope;
- where the real four-slot preflight occurs before fanout;
- why #6665 is fast rejection but not immutable native enforcement;
- why #6637 needs an exact required workflow plus a dedicated publisher App;
- how a lost writer is reconciled without duplicate carrier or blind failover;
- which capability each merge/host action actually makes true.

Merge of this records-only amendment means only:

```text
ELASTIC_CI_PRESSURE_ARCHITECTURE = SPEC_ONLY / FROZEN / R1_CORRECTED
```

It does not mean #6718 is repaired, a fourth listener exists, W5A is built, main is protected, a publisher App exists, or elastic capacity is available.
