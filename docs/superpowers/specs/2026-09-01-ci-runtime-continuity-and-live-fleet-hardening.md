# CI Runtime Continuity + Live Fleet Hardening Architecture

**Status:** records-only architecture freeze; implementation is separately gated  
**Operation:** `ci-runtime-continuity-live-fleet-hardening-20260901-sol-001`  
**Parent:** Macro #6351 / `WS:RUNNER-FLEET-RESILIENCE` + `WS:CI-MERGE-CONTROL-PLANE`  
**Related carriers:** Macro #6714, PR #6718, architecture PR #6717  
**Protected procedure loaded for this freeze:** `mastermindx-market-intelligence/Mastermind@21a721427743fdae6d513eeb0f993ebd1c327a81`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  

This document freezes the architecture required to make CI capacity and Sol↔worker continuity resilient under peak operating pressure. It is deliberately not another scheduler, runner registry, lifecycle, queue mirror, watcher registry, retry plane, proof store, or merge controller.

## 1. Chairman outcome

Mastermind must remain capable of proving, releasing, and operating software when several PRs, builders, reviews, and host workloads overlap. A runner shortage, stale declaration, dead provider tab, missed watcher wake, inherited main red, or long-running render must become an explicit bounded state with a deterministic recovery path—not a silent multi-hour company stall.

The target is not merely “add another runner.” The target is a resilient operating path in which:

1. declared runner policy and observed live fleet truth are never confused;
2. queue pressure is classified by cause rather than inferred from one stale field;
3. an ephemeral worker can finish a source wave and lawfully release branch-writer responsibility before its session disappears;
4. a lost exact session blocks only while it still owns local or effect-unknown state;
5. remote-complete source may continue through a separately bound release responsibility on the same PR/branch without duplicating implementation;
6. watchers wake the correct responsibility and never become lifecycle or retry authority;
7. a fourth persistent PC runner is installed and proven before production concurrency changes;
8. later elastic capacity consumes GitHub truth and existing CI proof owners without becoming a second scheduler;
9. Control Room can explain declared capacity, observed capacity, queue age, cause, stale evidence, and the exact next legal action;
10. no green CI, merge, Slack delivery, or static declaration is misrepresented as physical capacity or production proof.

The 10/10 state is operationally boring: peak load may increase wait time or create a typed degraded state, but it cannot make the organization guess whether a worker is alive, whether a runner exists, whether source is safely transferable, or whether a red belongs to the candidate or main.

## 2. Incident model

This architecture addresses six incident families that currently amplify each other.

### 2.1 Declaration-observation collapse

`.github/runner-policy.yml` is checked-in policy. It can prove that a label, route, slot ceiling, and pending carrier are allowed or forbidden. It cannot prove a declared runner is registered, online, idle, running the expected service, rooted in the expected workspace, or physically located on the expected host.

### 2.2 Queue-cause ambiguity

A delayed job may mean no eligible runner is online, all eligible runners are busy, GitHub-hosted capacity is queued, the job was never created, an admission hook refused it, a concurrency group is held by an older run, the candidate is red, main is red, or timestamps are unavailable. “Queued” is not one diagnosis.

### 2.3 Ephemeral-session writer stickiness

A source worker can return a clean remote PR, remain nonterminal while Sol reviews it, receive a later current-main join request, then lose its exact provider session. If the protocol never recorded that local effects were zero and remote source was complete, the whole source carrier becomes unnecessarily hostage to a dead tab.

### 2.4 Notification-only continuation

A watcher may notice a return yet stop at “Sol action required,” or may remain bound to a dead exact session even after the responsibility became safely transferable. The watcher then preserves attention but not progress.

### 2.5 Main-red amplification

A candidate may execute correctly and still remain red because an inherited main defect enters an always-on pack. Without exact attribution, teams either rerun blindly, absorb unrelated repairs into the candidate, or falsely treat the candidate as green.

### 2.6 Capacity-before-proof pressure

Under queue pressure, there is a temptation to register a runner, add a live label, or raise `max-parallel` before source, host identity, cgroup isolation, render coexistence, cleanup, and rollback have been proven separately.

## 3. Canonical owners and no-rebuild boundaries

This program extends existing owners:

- **GitHub Actions** remains the sole workflow scheduler, job queue, matcher, assignment mechanism, and source for runner/job observation.
- **`.github/runner-policy.yml` + Runner Fleet source law** remain the declaration/policy owner. They do not become a live registry.
- **The existing runner group** remains the access boundary for trusted workflows.
- **Existing `ci-plan`, semantic fragments, `ci-gate`, CI authority, and merge controller** remain the proof and merge owners.
- **Existing CI monitor/receipt tooling** remains the capacity/latency evidence path.
- **Executive OS** remains Job/Attempt/Worker/Event lifecycle authority.
- **RuntimeBinding / Wake / Agent Dialogue owners** remain the session-continuity authorities.
- **Agent OS** remains durable workstream/decision/discovery/handoff memory.
- **Slack** remains transport and hot-state visibility.
- **Control Room/Workroom** remain projections over canonical owners.

This program must not create:

- a second scheduler, queue, runner matcher, runner registry, or retry ledger;
- a daemon database whose cursor is required to know whether GitHub work exists;
- a second semantic gate, CI proof database, or merge controller;
- a second session registry or worker lifecycle;
- a watcher-owned completion/retry/continuation state machine;
- a “live” policy file populated by unverified host declarations;
- automatic cross-runner failover for a modifying job;
- automatic cancellation of an old queued run merely because a newer run exists;
- a generic self-hosted route for fork or untrusted code;
- an elastic runner that carries production `ci-linux` before isolated proof.

## 4. Capability ledger at architecture freeze

| Capability | State | Boundary |
|---|---|---|
| Three persistent sealed PC CI slots | `PROVEN_LIVE` | Existing P1–P4 path; current production ceiling remains three. |
| Fourth-slot source substrate | `BUILT_NOT_PROVEN` candidate | PR #6718; merge would not create a listener or increase concurrency. |
| Fourth persistent runner host proof | `NOT_BUILT` | Requires separate C3R-B privileged wave. |
| Production concurrency 3→4 | `NOT_BUILT` | Requires separate promotion after C3R-B acceptance. |
| Static runner declaration policy | `PROVEN_LIVE` for declaration | Explicitly not liveness evidence. |
| Fresh live fleet observation contract | `NOT_BUILT` | Must read GitHub + host attestation without a second registry. |
| Queue wait fields in existing receipt | `BUILT_NOT_PROVEN` candidate | #6718 adds nullable forward-compatible fields; live population remains later. |
| Queue cause classifier | `NOT_BUILT` | Must consume existing observations only. |
| Remote-complete writer release | `SPEC_ONLY` after this freeze | Needed to avoid dead-session hostage state. |
| Exact-session loss reconciliation | `PARTIAL` | Fail-closed law exists; safe transfer boundary is incomplete. |
| Action-authoritative watcher loop | `PARTIAL` | Source law exists; production and exact responsibility wake remain incomplete. |
| Stale queued-run hostage census | `PARTIAL` | Historical incidents known; no bounded current read-only projection yet. |
| Elastic JIT overflow | `SPEC_ONLY` in #6717 | Held behind main integrity, portability, four-slot proof, and residual-demand evidence. |

No row may be promoted by this document alone.

## 5. Live fleet observation architecture

### 5.1 Declaration remains declaration

Policy fields such as pool slots, allowed labels, pending carriers, forbidden labels, selected workflows, and production `max-parallel` remain checked-in intent. They are valid for admission and diff review, not for proving liveness.

### 5.2 Observation source

The live observation source is a fresh read of GitHub’s runner and workflow-job APIs, constrained to the existing repository/organization and runner group. The observation is ephemeral or emitted into the existing receipt path; it is never copied into a new canonical database.

A valid observation records at least:

```text
schema: ci.runner_fleet_observation.v1
repository
runner_group_id / runner_group_name
observed_at
source_request_identity
runners[]:
  github_runner_id
  runner_name
  status
  busy
  labels[]
  observed_at
policy_revision
host_attestations[]
staleness_budget_seconds
freshness_state
mismatches[]
```

`source_request_identity` is an auditable request/receipt identity, not a durable queue cursor.

### 5.3 Host identity binding

Runner names are mutable presentation identifiers and are not physical-host identity. A live runner may be called `pc-ci-4` only after it is joined to a host attestation produced by the existing host-install/proof path. The attestation binds:

```text
host_fingerprint
service_unit_digest
runner_service_pid
runner_root
workspace_root
cache_root
cgroup_path
runner_binary/version
GitHub runner id/name
observed labels
audit time
```

Host fingerprint must be privacy-safe and stable enough to distinguish physical/VM identity without exposing secrets. A rename changes presentation, not host identity. A new GitHub runner ID on the same host is a registration event and must be reconciled explicitly.

### 5.4 Freshness law

A fleet observation older than its accepted freshness budget may still be displayed with `STALE`, but it cannot authorize:

- roster promotion;
- `max-parallel` increase;
- runner removal;
- queued-run cancellation;
- branch release based on presumed capacity;
- autoscaler create/destroy action.

Missing observation is `UNKNOWN`, never “offline.” Static policy plus no API read is not negative liveness evidence.

### 5.5 Mismatch taxonomy

The observer reports, without mutating:

- `DECLARED_LIVE_NOT_OBSERVED`
- `OBSERVED_NOT_DECLARED`
- `LABEL_MISMATCH`
- `GROUP_MISMATCH`
- `HOST_ATTESTATION_MISSING`
- `HOST_ATTESTATION_MISMATCH`
- `RUNNER_REPLACED`
- `OBSERVATION_STALE`
- `RUNNER_BUSY`
- `RUNNER_OFFLINE`
- `RUNNER_IDLE`

A mismatch is evidence for adjudication. It never self-repairs labels, registration, services, or policy.

## 6. Queue pressure and cause classification

### 6.1 Inputs

The classifier consumes only existing or fresh canonical observations:

- GitHub workflow run and workflow job status/timestamps;
- required labels and runner group from the main-owned workflow/policy;
- fresh live runner observation;
- existing runner admission-hook receipt;
- existing execution receipt fields, including optional `workflow_job_queued_at`, `runner_job_started_at`, and derived `queue_wait_seconds`;
- existing concurrency-group/run relationship where GitHub exposes it;
- existing semantic proof/main-integrity result.

It does not assign jobs, start runners, retry, reroute, cancel, or change proof.

### 6.2 Cause states

One delayed job resolves to one primary cause with supporting secondary context:

```text
NO_ELIGIBLE_ONLINE_RUNNER
ALL_ELIGIBLE_RUNNERS_BUSY
GITHUB_HOSTED_QUEUE
JOB_NOT_CREATED_OR_HELD
CONCURRENCY_GROUP_HELD
RUNNER_ADMISSION_REFUSED
RUNNER_SETUP_OR_DEPENDENCY_DELAY
CANDIDATE_SEMANTIC_RED
INHERITED_MAIN_RED
PROOF_INCOMPLETE
OBSERVATION_STALE
UNKNOWN_INSUFFICIENT_EVIDENCE
```

A classifier may return `UNKNOWN_INSUFFICIENT_EVIDENCE`; it must not manufacture certainty.

### 6.3 Time and null behavior

`queue_wait_seconds` is derived only when both timestamps are present, parseable, and ordered. Missing, malformed, clock-incomparable, or reversed timestamps produce `null`, not `0` and not a negative value. An observed `0.0` remains a real measurement distinct from unavailable.

Queue time remains separate from checkout, cache prewarm, dependency setup, test execution, artifact upload, and total wall time.

### 6.4 Pressure levels

Pressure levels are descriptive, not scheduler authority:

- `NORMAL`: no eligible job exceeds the accepted queue SLO.
- `ELEVATED`: at least one eligible job exceeds SLO while capacity still exists.
- `SATURATED`: all eligible persistent slots are busy and queue age exceeds SLO.
- `DEGRADED`: an expected persistent slot is not freshly observed/attested, or admission refuses.
- `POISONED_BASE`: accepted main-integrity owner reports a known structural red.
- `UNKNOWN`: evidence is stale or incomplete.

Elastic work may eventually consume these states, but it cannot originate or redefine them in a separate store.

## 7. Remote-complete handoff and branch-writer transfer

### 7.1 Why this boundary is required

Exact-session stickiness is correct while an execution surface owns local-only, unpushed, untracked, credential-bearing, host-mutating, or effect-unknown state. It is unnecessarily disruptive after all accepted source exists remotely and the local worktree has no unique effect.

### 7.2 Remote-complete receipt

Before a source worker returns `RESULT / HOLD-FOR-SOL`, it must return a machine-checkable or command-backed receipt:

```text
schema: agent_dialogue.remote_complete.v1
operation_key
repository
pr_number
branch
remote_head_sha
remote_tree_sha
merge_base_sha
changed_paths[]
local_head_sha
local_equals_remote
worktree_clean
untracked_in_scope_count
unpushed_commit_count
uncommitted_in_scope_count
local_only_effect
external_effect_state
branch_writer_state
verified_at
commands[]
```

Required truth for `REMOTE_COMPLETE`:

- exact remote PR/branch/head exists;
- local HEAD equals remote HEAD;
- zero unpushed commits;
- zero uncommitted or untracked files in the owned scope;
- no local-only host/provider/runtime/credential effect;
- every external effect is `NONE` or separately reconciled and bound;
- worker explicitly releases branch-writer responsibility after Sol’s terminal worker STOP.

A dirty worktree outside the owned scope is still reported and must not be silently erased; it may be nonblocking only when ownership/collision law proves it unrelated.

### 7.3 Responsibility states

These are evidence/projection states, not a second Executive lifecycle:

```text
LOCAL_EFFECT_OPEN
REMOTE_COMPLETE_HELD
BRANCH_WRITER_RELEASED
RELEASE_OWNER_BOUND
RELEASE_RECONCILING_CURRENT_MAIN
RELEASE_READY
MERGED_BUILT_NOT_PROVEN
```

They describe who may maintain one Git carrier. They do not create Jobs, Attempts, Workers, queues, or retries.

### 7.4 Terminal worker boundary

When source is `REMOTE_COMPLETE_HELD`, Sol reviews the worker portion. If accepted:

1. Sol sends `SOL ACCEPTED / STOP` for the worker child;
2. the worker removes only that child watcher source;
3. the worker performs no further source or current-main maintenance;
4. branch-writer responsibility becomes `RELEASED`;
5. no next wave is authorized by the STOP.

This prevents “the next step is mine” from leaving a dead-session hostage while preserving explicit closure.

### 7.5 Same-PR release responsibility

After branch-writer release, a separate bounded release operation may bind an eligible release owner to the **same PR and same branch**. This is not a new implementation carrier and may perform only:

- fresh source/procedure/collision read;
- history-preserving current-main join if allowed;
- exact-path delta verification;
- required exact-head CI/review refresh;
- final merge adjudication;
- no feature edits except an explicit bounded repair return to a builder.

The release operation has its own operation key and continuation source because it is a distinct responsibility. The Git carrier remains one PR/branch.

### 7.6 Session-loss law

- Session lost while `LOCAL_EFFECT_OPEN` or effect is `EFFECT_UNKNOWN` → block and reconcile exact RuntimeBinding/worktree; no failover.
- Session lost after verified `REMOTE_COMPLETE_HELD` but before Sol STOP → source is safe, but branch writer is not yet released; Sol may terminally STOP based on remote receipt if current law permits.
- Session lost after `BRANCH_WRITER_RELEASED` → no source hostage; release owner may continue on the same PR/branch after fresh binding.
- Any host/provider effect remains on its original carrier until separately reconciled, regardless of remote source completeness.

## 8. Watcher and attention hardening

### 8.1 What a watcher binds to

A watcher source binds to:

```text
side + responsibility + operation_key + exact carrier + purpose
```

It binds to an exact provider session only while that exact session owns non-transferable local/effect state or is itself the acceptance target.

### 8.2 Responsibility-aware wake

- During implementation with local effect, wake the exact RuntimeBinding.
- After remote-complete receipt and branch-writer release, wake the current release responsibility, not the dead implementation tab.
- After terminal child STOP, remove only that child source; preserve seat/principal/sibling sources.
- A watcher never chooses a replacement worker, retries a mutation, merges, or originates a new wave.

### 8.3 Missed-fire behavior

Multiple missed expected watcher fires produce `WATCH_DEGRADED`. The next substantive action requires a fresh carrier read. The system must not stack a duplicate watcher, shorten model polling below the accepted floor, or assume silence means no return.

### 8.4 Notification-only refusal

When a qualifying return arrives and current authority/gates permit action, a Sol-owned watcher must re-enter normal procedure and issue the lawful same-carrier edge. “Sol action required” is not completion when the exact Sol responsibility can adjudicate.

## 9. Stale queued-run hostage census

A read-only census may identify queued or pending runs whose age, required labels, runner availability, and concurrency relationships indicate likely hostage state.

The census emits observation only. It cannot cancel or rerun.

A future cancellation action requires a separate, reviewed law proving all of:

- exact run/job identity;
- current same-run reread immediately before action;
- accepted supersession/cancellation authority;
- no unique evidence would be destroyed;
- no effect ambiguity;
- one carrier and one stable operation identity;
- post-action readback.

“Old” or “a newer run exists” is insufficient cancellation authority.

## 10. Fourth persistent runner acceptance ladder

### 10.1 C3R-A — source substrate

Landing #6718 may establish only `FOURTH_SLOT_CODE_SUBSTRATE = BUILT_NOT_HOST_PROVEN`. Production remains three slots. No registration, label, listener, host mutation, four-slot run, or `max-parallel` change is implied.

### 10.2 C3R-B — privileged host proof

A fresh, separately authorized host wave must:

1. fresh-census GitHub runner group, policy, service units, helper bytes, host resources, render state, cache/workspace roots, and rollback packet;
2. wait for a natural drain;
3. install the slice unit, updated helper, and affected service unit changes as one reviewed installation set, preserving exact pre-change bytes;
4. prove existing `pc-ci-1..3` restart cleanly under the slice before adding a new listener;
5. register/bootstrap `pc-ci-4` with platform/architecture identity only—without production `ci-linux`;
6. bind GitHub runner ID/name to host attestation, service PID, root, workspace, cache, and exact cgroup;
7. prove all four CI units are descendants of `/mastermind-ci.slice` and render is outside it;
8. run exactly one `slots=4` diagnostic while a real render/reservation workload runs;
9. prove cleanup, cache immutability, resource ceilings, no contamination, and rollback behavior;
10. stop and return to Sol without changing production `max-parallel`.

The installation ordering hazard is binding: an updated unit carrying both `Slice=mastermind-ci.slice` and `--require-slice` must not be installed ahead of the compatible slice/helper set.

### 10.3 Separate production promotion

Only after C3R-B Sol acceptance may a fresh promotion carrier:

- add the exact attested `pc-ci-4` to the live `ci-linux` roster;
- change trusted executor `max-parallel: 3 → 4`;
- preserve runner-group/workflow/fork boundaries;
- prove natural same-repository PR traffic, including simultaneous pressure and active render;
- compare queue wait and resource behavior to the three-slot baseline;
- roll back to three on semantic, cleanup, cache, queue, pressure, admission, or render regression.

### 10.4 Elastic overflow remains later

No slot 5, provider actuator, JIT create/delete, burst label, webhook scaler, ARC, or scale set is authorized until:

- main integrity is reliable;
- demand-reduction/ownership work is materially complete;
- the execution profile is portable;
- four persistent slots are proven in production;
- residual eligible queue pressure is measured prospectively;
- one isolated manual JIT proof passes without carrying production `ci-linux`.

## 11. Control Room projection

The existing Control Room/Workroom projection should eventually show, from canonical reads:

- declared persistent slots and production ceiling;
- fresh observed runners with online/offline/busy/idle and staleness;
- host-attestation match state;
- oldest eligible queue age and primary cause;
- active/busy jobs by runner;
- inherited-main-red versus candidate-red attribution;
- current source responsibility: implementation, remote-complete hold, release owner, merged-not-proven;
- watcher health: active, degraded, unavailable, terminal child source removed;
- exact next legal action and its owner.

The view is read-only until separately authorized admin controls exist. A button may request an existing canonical operation; it does not mutate runners or lifecycle directly.

## 12. Deterministic, statistical, and model-generated methods

- Runner policy validation, API observation parsing, freshness, identity joins, queue timing, cause prerequisites, path deltas, remote-complete checks, watcher-source uniqueness, and promotion gates are deterministic.
- Pressure thresholds and economic capacity decisions may use descriptive statistics over prospective receipts, with sample size and missingness disclosed.
- Model-generated summaries may explain the state but have zero authority to rank proof, cancel jobs, register runners, rebind started operations, approve merges, or promote capacity.

## 13. Failure states

The implementation must preserve and expose at least:

- runner API unavailable or permission denied;
- observation stale;
- declared/observed mismatch;
- duplicate runner name or replacement ID;
- host attestation missing/mismatched;
- queue timestamps unavailable/reversed;
- all runners busy versus none eligible online;
- admission refusal;
- job never created / concurrency held;
- inherited main red versus candidate red;
- local worktree dirty, unpushed, or effect unknown;
- exact RuntimeBinding lost;
- remote source complete but branch writer not released;
- duplicate watcher source;
- watcher missed fire / unavailable / stop failed;
- current-main path collision;
- CI incomplete or review stale;
- host drain unavailable;
- installation partial or helper/unit incompatibility;
- render joins CI slice;
- fourth listener online but mislabeled/routable early;
- four-slot diagnostic regression;
- promotion regression and rollback failure.

No failure may be normalized to success merely because a sibling layer is green.

## 14. Discriminating acceptance tests

### Live fleet

- Static policy says a carrier is live while GitHub reports offline → mismatch displayed; promotion refused.
- GitHub reports a runner not declared → observed-not-declared; no automatic adoption.
- Snapshot exceeds freshness budget → visible stale state; every modifying consumer refuses.
- Runner rename with same attested host identity → presentation change, not a new host.
- Same name with new runner ID and no accepted registration receipt → replacement mismatch.

### Queue pressure

- No eligible online runner versus all eligible runners busy resolve differently.
- Missing/unparseable/out-of-order timestamps yield `null`; real zero remains `0.0`.
- Checkout/dependency delay cannot be labeled queue wait.
- Candidate-green execution with inherited main red remains red with correct attribution; no false-green.

### Continuity

- Session loss with unpushed commit or local-only effect blocks transfer.
- Session loss after exact remote-complete receipt + branch-writer release permits a separately bound release responsibility on the same PR/branch.
- Release owner cannot edit outside release-maintenance scope.
- Current-main join that introduces an extra path or collision stops before push.
- Duplicate logical implementation PR is rejected.

### Watchers

- Duplicate source for same side/responsibility/operation/carrier/purpose is refused.
- Worker RESULT without later Sol edge remains awaiting Sol.
- Terminal STOP removes only the exact child source, preserving aggregate seat/principal sources.
- Watcher stop failure leaves child terminal and emits `WATCH_STOP_FAILED`.
- Notification-only wake fails when the same Sol responsibility can lawfully act.

### Capacity

- `pc-ci-4` entering any live roster before host proof fails.
- `ci-linux` on `pc-ci-4` before C3R-B acceptance fails.
- `max-parallel: 4` before separate promotion fails.
- Any CI unit outside the CI slice or render inside it fails four-slot acceptance.
- Missing aggregate slice evidence refuses rather than substituting host-global values.
- Capacity receipt cannot make semantic CI green.

## 15. Ordered implementation waves

### RCH-0 — architecture freeze

This document and its review. Records only.

### LFO-1 — live fleet observer

Extend the existing Runner Fleet/receipt tooling with a read-only GitHub observation and declaration-vs-observation diff. No daemon or database. Produce CLI/fixture proof and one real read-only observation receipt.

### QPC-1 — queue pressure classifier

Use existing workflow-job and receipt data to classify queue cause and expose nullable timing. No actuation. Produce retrospective fixtures plus prospective natural-traffic receipts.

### RCH-1 — remote-complete handoff contract

Add the command-backed remote-complete receipt and branch-writer release law to existing Agent Dialogue/continuity owners. Add fail-closed tests for local effect and same-PR release transfer.

### RCH-2 — responsibility-aware watcher wake

Teach the existing watcher/continuity path to wake implementation responsibility while local effect exists and release responsibility after branch-writer release. No watcher registry or new lifecycle.

### SQH-1 — stale queued-run read-only census

Expose likely hostage runs and exact reason. Alert only; no cancellation.

### C3R-B — fourth-slot privileged host proof

Install/attest/diagnose as §10.2. No production promotion.

### C3P — production 3→4 promotion

Promote and prove natural traffic as §10.3, with automatic rollback only if the existing accepted promotion/rollback owner has been separately reviewed and authorized; otherwise operator rollback remains explicit.

### CR-1 — Control Room projection

Project existing canonical observations and responsibilities. Read-only first.

### EC1+ — elastic overflow

Held behind the gates in §10.4 and #6717.

Implementation waves may be parallel only when changed paths and authority are genuinely disjoint. C3R-B is gated on accepted/merged C3R-A. C3P is gated on accepted C3R-B. Elastic production is gated on accepted C3P plus residual-demand evidence.

## 16. Release and completion law

This program is not complete when documentation merges, #6718 merges, a runner registers, or `max-parallel` changes.

Completion requires:

- **Truth:** fresh declaration-vs-observation and host-attested fleet identity;
- **Continuity:** remote-complete source can be safely released without dead-session hostage state, while local/effect-unknown work remains fail-closed;
- **Capacity:** four persistent slots are proven under aggregate isolation and render coexistence;
- **Product:** Control Room explains capacity, queue cause, staleness, responsibility, and next action;
- **Learning:** prospective queue/resource receipts demonstrate whether 3→4 reduced eligible wait without new semantic, cleanup, cache, admission, or render regressions;
- **Operations:** all material decisions/discoveries/handoffs are durable in Agent OS, with exact next action recoverable without this chat.

This architecture authorizes no implementation, merge, host action, runner registration, label change, CI retry/cancellation, provider action, watcher creation, or production promotion by itself.
