# CI Runtime Continuity + Live Fleet Hardening Architecture — R1 Reconciled

**Status:** records-only architecture freeze; implementation and release remain separately gated  
**Program operation:** `ci-runtime-continuity-live-fleet-hardening-20260901-sol-001`  
**Parent:** Macro #6351 / `WS:RUNNER-FLEET-RESILIENCE` + `WS:CI-MERGE-CONTROL-PLANE`  
**Canonical adjacent architecture:** PR #6717, especially the Runner Fleet W5A/EC2A owner and the C3R-A → C3R-B → C3P ladder  
**Current C3R-A carriers:** issue #6714; merged PR #6718; repair PR #6728  
**Protected procedure used for this reconciliation:** `mastermindx-market-intelligence/Mastermind@821e90f8f0f01dd1ed7bf11a6c548a5f410c2a32`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1  

This document freezes the architecture required to keep CI, source release, worker continuity, and host capacity recoverable under peak load. It creates no scheduler, queue, runner registry, lifecycle, retry plane, watcher registry, proof store, health gate, merge controller, or durable liveness database.

It also corrects three defects in the prior draft:

1. live-fleet observation and queue classification are internal contract detail for the existing Runner Fleet **W5A/EC2A** owner, not new `LFO-1`/`QPC-1` workstreams;
2. PR #6718 is already merged but technically rejected, so the current source state is **`BUILT_NOT_PROVEN / RELEASE_BLOCKED`**, not a pre-merge candidate;
3. historical three-slot production acceptance is separated from action-time runner availability, which is always `UNKNOWN` until a fresh timestamped observation is read.

No row, carrier, or capability is promoted by this architecture document alone.

## 1. Chairman outcome

Mastermind must continue proving and releasing software when many PRs, agents, reviews, renders, and host workloads overlap. A queue spike, stale runner declaration, dead provider tab, missed wake, inherited main red, review rejection, host disk exhaustion, or partial rollout must become an explicit bounded state with one lawful next action—not a multi-hour organizational stall.

The 10/10 operating state has these properties:

1. checked-in policy is never confused with current runner observation;
2. historical acceptance is never confused with action-time liveness;
3. queue delay is classified by cause, with stale or missing evidence kept unknown;
4. a source worker can return remote-complete work and release branch-writer responsibility without making a dead tab the permanent owner of a known Git carrier;
5. local-only or effect-unknown work remains exact-session sticky and never blind-fails over;
6. terminal STOP is monotonic, so stale watchers and late messages cannot reopen a child;
7. exact-head review and release gates cannot be bypassed by merge pressure or pasted authority prose;
8. watchers wake the current responsibility, require delivery acknowledgement, and never become lifecycle or retry authority;
9. host disk/resource pressure refuses new expensive work before ENOSPC and never deletes active foreign worktrees;
10. fourth-slot source repair, privileged host proof, and production 3→4 promotion remain separate gates;
11. every material state and exact next action is recoverable from GitHub plus durable Agent OS records without this chat.

## 2. Incident and root-cause model

The C3R-A incident proved that several individually small weaknesses can combine into a system-wide disruption:

- a started builder became session/worktree-identity ambiguous;
- remote source existed, but branch-writer and release responsibility were not cleanly separated;
- a terminal STOP was followed by stale continuation edges that could be misread as reopening authority;
- the builder merged #6718 while an immutable exact-head review remained `CHANGES_REQUESTED`;
- the real host falsified two shared test premises: systemd slice hierarchy and aggregate-parent location;
- one listener was unavailable for about 96 seconds during the staged migration before rollback;
- repeated full-tree scratch extractions and many concurrent sessions drove a 1.8 TiB host to ENOSPC;
- narrow green tests and merge state were repeatedly at risk of being described as release or production proof.

The system therefore needs one coherent architecture across source responsibility, exact-head release, watcher delivery, live fleet truth, host admission, and staged rollback. Fixing only one layer leaves the compound failure available.

## 3. Canonical owners and no-rebuild boundaries

### 3.1 Existing owners

- **Executive OS** owns runtime Job / Attempt / Worker / Event lifecycle and CEO-intent admission.
- **Agent Dialogue / RuntimeBinding / Wake** own actor applicability, exact-session binding, return delivery, and continuation semantics.
- **GitHub** owns implementation, commit, branch, PR, exact-head review, CI evidence, and merge truth.
- **GitHub Actions** remains the sole workflow scheduler, queue, job matcher, and assignment mechanism.
- **`.github/runner-policy.yml` and Runner Fleet source law** own declared topology, labels, carriers, and allowed routes—not liveness.
- **The existing runner group** remains the trusted workflow access boundary.
- **Existing CI plan, semantic fragments, `ci-gate`, CI authority, and merge controller** remain proof and merge owners.
- **Existing monitor / canary receipt tooling** remains the execution, resource, and timing evidence path.
- **Runner Fleet W5A/EC2A** owns the read-only joined live-fleet and queue projection.
- **Existing runner-host/worktree admission and cleanup helpers** own host resource refusal and cleanup containment.
- **Agent OS** owns durable workstreams, decisions, discoveries, and handoffs.
- **Slack** remains transport and hot-state visibility.
- **Control Room / Workroom** remain projections over canonical owners.

### 3.2 Forbidden duplicate planes

This program must not create:

- another scheduler, queue mirror, runner matcher, runner registry, autoscaler state database, or retry ledger;
- another Job/Attempt/Worker lifecycle or session registry;
- watcher-owned lifecycle, completion, replacement-worker, retry, merge, or escalation authority;
- another semantic gate, main-health gate, proof database, merge controller, or publication path;
- a checked-in “live runners” truth store;
- a second canary receipt family when the existing receipt can be extended compatibly;
- automatic cross-runner failover for an ambiguous modifying operation;
- automatic cancellation merely because a run is old or a newer run exists;
- generic self-hosted routing for fork or untrusted code;
- a second workstream for live fleet, queue cause, host reachability, or Control Room projection already owned by W5A/EC2A.

## 4. Capability ledger at the R1 reconciliation

| Capability | State | Exact boundary |
|---|---|---|
| Three-slot trusted PC CI route — historical acceptance | `PROVEN_LIVE` | Accepted prior production receipts prove the route worked at their timestamps. They do not prove current runner availability. |
| Three-slot action-time runner availability | `NOT_BUILT` as durable product | Every modifying or release action must obtain a fresh timestamped GitHub/host observation; absent or stale observation is `UNKNOWN`. |
| Static runner policy | `PROVEN_LIVE` for declaration | It proves allowed topology/labels only, never online, idle, service, host, or cgroup state. |
| #6718 fourth-slot source substrate | `BUILT_NOT_PROVEN` | Merged as `b260d28a6efbfb4593dfcc453731f71703252ac0` while exact-head review remained `CHANGES_REQUESTED`; release is blocked. |
| #6728 C3R-A repair | `PARTIAL` | Head `04d30860e1309d427e160319072c6cb150f35e47` repairs systemd hierarchy and parent reads, but exact-head review `5085372259` requires the remaining false-proof repairs. |
| Accepted C3R-A source | `NOT_BUILT` | Requires #6728 to close every blocker, pass current-head CI, receive separate-principal approval, and merge. |
| Fourth persistent runner host proof | `NOT_BUILT` | Separate privileged C3R-B after accepted C3R-A. |
| Production concurrency 3→4 | `NOT_BUILT` | Separate C3P after C3R-B acceptance and natural-traffic proof. |
| W5A/EC2A live fleet + queue projection | `PARTIAL` | Manual/current reads exist; no accepted production projection with freshness and joined host truth yet. |
| Queue timing fields in existing canary receipt | `BUILT_NOT_PROVEN` | Merged source is additive, but full C3R-A evidence logic remains release-blocked. |
| Remote-complete writer release contract | `SPEC_ONLY` | Must extend existing Agent Dialogue / Executive continuity owners. |
| Exact-session loss reconciliation | `PARTIAL` | Fail-closed behavior exists; remote-complete responsibility transfer is not production-proven. |
| Exact-session wake acknowledgement (ACK1) | `BUILT_NOT_PROVEN` | Protected source exists; production remains disarmed and the DELIVERED→ACK crash window remains open work. |
| Exact-head review/merge barrier | `PARTIAL` | Review truth exists in GitHub, but #6718 proved current merge paths can still bypass the intended barrier. |
| Host ENOSPC admission / scratch containment | `PARTIAL` | Live-aware GC exists, but expensive source operations can still begin without sufficient disk headroom or bounded scratch ownership. |
| Elastic overflow | `SPEC_ONLY` | Held behind main integrity, accepted C3P, execution portability, and prospective residual pressure. |

## 5. Runner Fleet W5A/EC2A — one joined observation owner

### 5.1 Ownership mapping

All live-fleet, queue-cause, host-reachability, and read-only Control Room work in this document is **internal detail of the existing W5A/EC2A owner** under `WS:RUNNER-FLEET-RESILIENCE`.

The former names `LFO-1`, `QPC-1`, `SQH-1`, and `CR-1` are not independent waves, workstreams, receipt families, or publication paths. They map only to these W5A internal steps:

```text
W5A.1 — fresh declared-vs-observed fleet join
W5A.2 — deterministic queue-cause and timing projection
W5A.3 — read-only Control Room/Workroom projection
W5A.4 — host-control reachability and disk/resource pressure projection
W5A.5 — stale queued-run census, observation only
```

A later reader must be unable to commission both W5A and a separately named observer/classifier for the same facts.

### 5.2 Inputs

W5A consumes fresh or already canonical evidence only:

- GitHub runner and workflow-job APIs;
- main-owned workflow required labels and runner group;
- `.github/runner-policy.yml` declared carriers and pending topology;
- accepted host-attestation receipts;
- existing admission-hook, monitor, cleanup, and execution receipts;
- optional `workflow_job_queued_at`, `runner_job_started_at`, and derived `queue_wait_seconds`;
- GitHub concurrency-group/run relationships where exposed;
- existing candidate-vs-main semantic attribution;
- host-control reachability and disk/resource observations from existing host tooling.

It never assigns, retries, reroutes, cancels, registers, labels, restarts, deletes, merges, or promotes.

### 5.3 Observation contract

A valid fresh projection records at least:

```text
schema: ci.runner_fleet_projection.v1
repository
runner_group_id / runner_group_name
observed_at
freshness_budget_seconds
freshness_state
policy_revision
expected_persistent_slots
expected_carriers[]
observed_runners[]:
  github_runner_id
  runner_name
  status
  busy
  labels[]
  observed_at
host_attestations[]
missing_expected_carriers[]
unexpected_carriers[]
identity_or_label_mismatches[]
eligible_queue_depth
oldest_eligible_queue_age_seconds
in_progress_eligible_jobs
host_control_reachable = true | false | unknown
host_disk_free_bytes
host_disk_free_inodes
host_disk_observed_at
pressure_classification
reasons[]
```

This may be emitted ephemerally or through an existing accepted receipt/projection path. It is not a new canonical database or queue cursor.

### 5.4 Freshness and action-time truth

- Historical production acceptance remains historical.
- Current online/idle/busy/service/host state is `UNKNOWN` until a fresh observation with `observed_at` and an accepted freshness budget exists.
- Missing GitHub or host evidence is `UNKNOWN`, never “offline,” “healthy,” or “available.”
- Stale observations may be displayed but cannot authorize roster promotion, production concurrency increase, runner retirement, queued-run cancellation, host mutation, release based on presumed capacity, or elastic action.
- Static policy cannot satisfy action-time liveness.

### 5.5 Deterministic cause classes

One delayed job receives one primary cause plus supporting reasons:

```text
NO_ELIGIBLE_ONLINE_RUNNER
ALL_ELIGIBLE_RUNNERS_BUSY
GITHUB_HOSTED_QUEUE
JOB_NOT_CREATED_OR_HELD
CONCURRENCY_GROUP_HELD
RUNNER_ADMISSION_REFUSED
HOST_CONTROL_UNREACHABLE
HOST_DISK_PRESSURE
RUNNER_SETUP_OR_DEPENDENCY_DELAY
CANDIDATE_SEMANTIC_RED
INHERITED_MAIN_RED
PROOF_INCOMPLETE
OBSERVATION_STALE
UNKNOWN_INSUFFICIENT_EVIDENCE
```

`queue_wait_seconds` is derived only when both timestamps are present, parseable, comparable, and ordered. Missing, malformed, reversed, or clock-incomparable timestamps produce `null`, not zero or negative. Real `0.0` remains distinct from unavailable. Queue time remains separate from checkout, cache, dependency setup, test execution, artifact upload, and wall time.

## 6. C3R-A → C3R-B → C3P remains a hard ladder

### 6.1 Current source truth

PR #6718 is already merged. Merge is not acceptance. Its immutable head retained a release-blocking review, and the real host exposed additional false-proof assumptions. Therefore:

```text
#6718 = MERGED / BUILT_NOT_PROVEN / RELEASE_BLOCKED
#6728 = existing same-program repair carrier / PARTIAL at reviewed head
C3R-B = FORBIDDEN until repaired C3R-A is accepted and merged
C3P = FORBIDDEN until C3R-B is accepted
```

No document, Slack post, green fast gate, or host experiment may rewrite that truth.

### 6.2 Required C3R-A repair

The existing #6728 carrier must preserve its valid hierarchical systemd and aggregate-parent fixes and additionally prove:

- exact direct candidate service membership at `/mastermind.slice/mastermind-ci.slice/<unit>.service`;
- exact aggregate-parent envelope: `cpu.max 800000 100000`, `memory.high 10737418240`, `memory.max 12884901888`, `memory.swap.max 2147483648`;
- required parseable memory and I/O PSI in strict four-slot preflight;
- a main-defined fail-closed preflight before four-way diagnostic fanout;
- stable candidate and parent identity, chronological samples, and monotonic counters;
- no numeric acceptance fields on reset, reversal, identity change, or missing evidence;
- canonical non-symlink runner root and contained `_work` before cleanup;
- exact pending-label identity and malformed-input refusal without traceback;
- production remains three live `ci-linux` carriers and `max-parallel: 3`.

Source merge can establish only `FOURTH_SLOT_CODE_SUBSTRATE = BUILT_NOT_HOST_PROVEN`.

### 6.3 C3R-B privileged host proof

After accepted C3R-A, a separate exact carrier must:

1. fresh-read GitHub runner group, policy, service/helper bytes, host resources, render state, roots, cache, and rollback snapshots;
2. wait for a natural drain;
3. verify source/helper/unit digests before any daemon action;
4. install the slice/helper/unit tuple without exposing old-helper/new-unit incompatibility;
5. migrate and prove `pc-ci-1..3` one listener at a time, rolling back on first failure;
6. create/register `pc-ci-4` initially with platform/architecture labels only, never production `ci-linux`;
7. bind GitHub runner ID/name to service PID, root, workspace, cache, host identity, candidate cgroup, and aggregate parent;
8. prove render remains outside the CI slice and its route is unchanged;
9. run exactly one authorized slots=4 diagnostic with an independently active real render;
10. prove cleanup, cache, cgroup envelope, PSI, counters, semantic parity, and rollback;
11. stop without changing production `max-parallel`.

Registration/credential ceremony remains a separately gated native operator act. No secret enters chat.

### 6.4 C3P production promotion

Only after C3R-B acceptance may a fresh carrier add the accepted fourth runner to the production roster and change `max-parallel: 3 → 4`. It must prove natural same-repository traffic, one simultaneous-PR overlap window, active real render, queue/resource improvement, semantic integrity, cleanup, cache, admission, and rollback. Failure restores production concurrency to three while preserving the proven but idle fourth host.

### 6.5 Elastic capacity

Elastic/JIT capacity remains later and consumes #6717. It requires active main integrity, accepted C3P, portable execution-profile evidence, external logs, prospective residual queue pressure, and a separately isolated one-job proof. It may not carry production `ci-linux` merely because persistent capacity is busy.

## 7. Remote-complete source and responsibility transfer

### 7.1 Existing lifecycle remains authoritative

The following are evidence/projection fields inside existing Executive OS and Agent Dialogue records, not a new lifecycle:

```text
implementation_responsibility
branch_writer_responsibility
release_responsibility
local_effect_state
external_effect_state
remote_complete_receipt
terminal_worker_edge
current_release_binding
```

Job/Attempt/Worker/Event lifecycle stays in Executive OS. GitHub remains source truth.

### 7.2 Remote-complete receipt

Before a source worker returns `RESULT / HOLD-FOR-SOL`, it must supply a command-backed receipt containing:

```text
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
verified_at
commands[]
```

`REMOTE_COMPLETE` requires exact remote existence, local==remote, zero unpushed commits, zero uncommitted/untracked in-scope bytes, and no unreconciled local/host/provider/credential effect. Dirty unrelated paths are disclosed and separately collision-adjudicated, never erased.

A later modifying CONTINUE invalidates the prior receipt until a new command-backed receipt is produced.

### 7.3 Terminal worker and release boundary

When remote source is complete and the worker mission is accepted:

1. Sol issues `SOL ACCEPTED / STOP` for the worker child;
2. STOP is terminal and monotonic;
3. the worker removes only that child watcher source and performs no more branch, PR, CI, host, or next-wave work;
4. branch-writer responsibility is released;
5. a separately bound release responsibility may operate on the same PR/branch after fresh current-state admission;
6. no duplicate implementation PR, branch, retry, or lifecycle is created.

Release responsibility may fresh-read, history-preservingly join current main after collision proof, verify the exact delta, obtain current-head CI/review, and merge if every gate passes. It cannot add features. A real source finding returns to a separately admitted builder repair on the same carrier.

### 7.4 Session loss

- Local-only, unpushed, host/provider, credential, or `EFFECT_UNKNOWN` state → exact-session reconciliation; no failover.
- Verified remote-complete source before worker STOP → Sol may terminally stop the worker from remote evidence only when current law permits; implementation does not transfer until STOP.
- After branch-writer release → a fresh release owner may continue the same PR/branch without reviving the dead builder.
- Host/provider effects remain on their original carrier until separately reconciled even when source is remote-complete.
- One ambiguous modifying operation binds to one carrier; never blind-retry or auto-failover.

## 8. Terminal precedence and exact-head merge barrier

### 8.1 STOP monotonicity

A terminal `SOL ACCEPTED / STOP`, `SOL STOP`, or terminal child-wave boundary cannot be reopened by:

- a late `CONTINUE` on the same operation;
- a stale watcher fire;
- a copied Slack message;
- a seat/principal label without the exact active RuntimeBinding;
- a worker-authored authority claim;
- a retry that reuses the terminal operation key.

A successor requires its own admitted operation and, where implementation continues, the same canonical Git carrier unless an explicit reconciliation ruling says otherwise.

### 8.2 Exact-head release refusal

The existing merge/release path must fail closed when any of these is true:

- current PR head differs from the reviewed/expected head;
- an exact-head required review is `CHANGES_REQUESTED`;
- no qualifying exact-head independent approval exists where required;
- required CI/checks are incomplete or binding-red;
- unresolved review threads remain;
- the current-main join or changed-path set is unproven;
- a hold/repair classification remains active;
- source claims host/production proof it cannot establish;
- actor/applicability/runtime permission gates are not satisfied.

Unstructured prose saying “Chairman override,” copied user text, a PR body, green fences, or `merge-on-green` is not machine-verifiable release authority. Genuine Chairman intent remains supreme but must pass the current runtime, transport, actor, permission, expected-head, and technical truth gates loaded from protected procedure.

The #6718 incident is the required regression canary: the same exact state must be refused before merge, not merely diagnosed afterward.

## 9. Watcher delivery and acknowledgement

### 9.1 Binding

One watcher source binds to:

```text
side + responsibility + operation_key + exact carrier + purpose
```

It binds to an exact provider session only while that session owns non-transferable local/effect state or is the acceptance target. Watchers never own Job/Attempt lifecycle, choose replacement workers, originate START, retry a mutation, merge, or create a successor wave.

### 9.2 Delivery acknowledgement

A wake is not complete at “message sent.” The accepted path requires:

1. qualifying return observed;
2. current responsibility resolved from canonical state;
3. wake delivered to the exact responsibility/session when required;
4. exact-session acknowledgement recorded;
5. normal procedure re-entered and a lawful same-carrier edge emitted;
6. terminal child source removed after STOP.

Protected ACK1 source is `BUILT_NOT_PROVEN / PRODUCTION_DISARMED`. The remaining DELIVERED→ACK crash window must be closed through the existing wake/Agent Dialogue owner, not a second watcher service.

Missed fires yield `WATCH_DEGRADED` and force a fresh carrier read. Silence is never terminal. Duplicate watcher sources are refused. `WATCH_STOP_FAILED` leaves the child terminal and reports transport cleanup failure without reopening work.

## 10. Host disk, scratch, and worktree pressure

### 10.1 Observation

W5A.4 projects fresh host-control reachability, free bytes, free inodes, active worktree/process ownership, safely reclaimable bytes, and observation age. Missing host control is `UNKNOWN`, not healthy.

### 10.2 Admission

Existing host/worktree admission must refuse expensive source work before it can drive the host to ENOSPC. At minimum, admission applies before:

- creating a new full worktree or archive extraction;
- full-suite artifact staging;
- large scratch copies;
- runner bootstrap or cache population;
- host migration requiring rollback snapshots.

Thresholds must be versioned, fail closed when measurement is unavailable for a required operation, and preserve headroom for Git index writes, logs, rollback, and active runners. A future threshold change is a separately reviewed policy change, not an LLM judgment.

### 10.3 Scratch containment

- Full `git archive | tar -x` source copies are prohibited by default for comparison/review work.
- Prefer shared-object Git worktrees, sparse checkout, targeted blob reads, or copy-on-write clones where the host supports them.
- Every scratch root records owner operation, creation time, intended bytes, actual bytes, and expiry/terminal cleanup boundary.
- Per-operation scratch quotas and host-wide reserve prevent one session from consuming fleet headroom.
- Cleanup never follows symlinks, never crosses canonical roots, and never deletes worktrees with live owning processes or unresolved effects.
- Orphan cleanup is evidence-driven and idempotent; active foreign sessions are not sacrificed to rescue a new operation.

### 10.4 Rollout containment

Host changes proceed one listener at a time after natural drain, with exact pre-change bytes and first-failure rollback. The 96-second one-slot incident demonstrates why all-at-once migration is rejected by design. A single successful transient unit or helper invocation is not full-fleet acceptance.

## 11. Main red, candidate red, and capacity evidence

Candidate correctness, inherited main health, transport success, capacity health, and semantic verdict are separate facts.

- A candidate may be clean while main is structurally red.
- A trusted self-hosted fragment may be red while hosted relay succeeds.
- Capacity/receipt green may never normalize semantic red.
- `POISONED_BASE` is a derived state from the existing main-health/semantic owner, not a second gate.
- Blind rerun, unrelated repair absorption, and “green except inherited” merge claims are forbidden unless current release law explicitly admits that exact evidence shape.
- Main integrity and red-relay repairs remain their existing carriers; this architecture only consumes their verdicts.

## 12. Control Room / Workroom projection

W5A.3 should eventually show, read-only:

- declared slots, carriers, labels, and production ceiling;
- fresh observed runner IDs/names/status/busy state and observation age;
- host-attestation match and host-control reachability;
- disk/resource headroom and admission state;
- oldest eligible queue age, depth, and deterministic primary cause;
- active jobs by runner;
- candidate red versus inherited-main red;
- current implementation/branch-writer/release responsibility;
- local/effect state and remote-complete receipt age;
- watcher delivery/ack/degraded/stop-failed state;
- exact next legal action, owner, carrier, and blocker.

The view requests existing canonical operations only after separate authorization. It does not mutate runners, lifecycle, branches, jobs, or rulesets directly.

## 13. Deterministic, statistical, and model-generated methods

Deterministic methods own:

- actor/applicability/runtime admission;
- exact-head, tree, parent, merge-base, path, review, thread, and CI checks;
- runner policy validation and declaration-vs-observation joins;
- freshness, identity, queue timing, and cause prerequisites;
- remote-complete and local-effect proof;
- watcher-source uniqueness and delivery acknowledgement;
- cgroup identity/envelope/counter validation;
- disk/scratch admission and cleanup containment;
- host/promotion gates and rollback identity.

Descriptive statistics may summarize prospective queue/resource receipts with sample size, missingness, and time windows disclosed. Model-generated summaries may explain state but have zero authority to rank proof, approve, merge, cancel, retry, register, label, rebind, clean, promote, or originate trades.

## 14. Required failure states

The system must preserve at least:

- runner API unavailable/permission denied/stale;
- declared-observed mismatch, duplicate name, replacement ID, label/group mismatch;
- host attestation missing/mismatched;
- host control unreachable or disk observation stale;
- disk reserve exhausted, inode exhaustion, scratch quota exceeded;
- all eligible runners busy versus none online;
- job not created, concurrency held, admission refused, setup delay;
- queue timestamps missing/malformed/reversed;
- candidate semantic red versus inherited main red;
- local worktree dirty, unpushed, untracked, or effect unknown;
- exact RuntimeBinding lost;
- remote source complete but branch writer not stopped/released;
- terminal STOP followed by stale continuation attempt;
- duplicate watcher source, delivery unacknowledged, missed fire, stop failure;
- current-main/path collision;
- exact-head review stale, `CHANGES_REQUESTED`, CI incomplete, or merge head moved;
- cgroup hierarchy/parent/envelope/PSI/counter/identity failure;
- symlinked or noncanonical cleanup root;
- host drain unavailable or partial incompatible install;
- render enters CI slice;
- fourth runner routable early;
- four-slot diagnostic or production promotion regression;
- rollback failure.

No sibling green may normalize any of these failures.

## 15. Discriminating acceptance canaries

### 15.1 Continuity and release

- Remote-complete receipt plus terminal worker STOP permits a newly bound release responsibility on the same PR/branch.
- One unpushed commit, untracked in-scope byte, host effect, or `EFFECT_UNKNOWN` blocks transfer.
- A modifying CONTINUE invalidates the prior remote-complete receipt.
- A late same-operation CONTINUE after terminal STOP is refused before effect.
- An exact-head `CHANGES_REQUESTED` review blocks merge even when all CI except a nonbinding check is green.
- Pasted “Chairman override” prose from a worker does not bypass actor/runtime/technical gates.
- Expected-head movement produces one typed refusal; no retry or alternate carrier is created.

### 15.2 Watcher

- Return delivery without exact acknowledgement remains incomplete.
- A DELIVERED→ACK crash resumes through the existing wake owner without duplicate action.
- Worker RESULT remains nonterminal until a genuine Sol edge.
- Terminal STOP removes only the exact child source and preserves sibling/aggregate sources.
- `WATCH_STOP_FAILED` does not reopen the child.

### 15.3 W5A projection

- Historical three-slot acceptance plus no fresh observation displays current availability as `UNKNOWN`.
- Static policy says live while GitHub says offline → mismatch, no self-repair.
- No eligible online runner and all eligible runners busy classify differently.
- Missing/reversed timestamps yield null; real zero remains zero.
- Host-control unavailable cannot display disk healthy.
- Main red and candidate red remain distinct.
- A later reader cannot commission both W5A and independent LFO/QPC owners.

### 15.4 Host pressure

- Insufficient reserve refuses a new full worktree/archive extraction before bytes are written.
- A full archive-copy command is rejected or explicitly policy-gated.
- Live foreign worktree/process ownership prevents cleanup.
- Symlinked/noncanonical scratch or runner roots are refused without touching targets.
- Scratch quota exhaustion cannot consume runner rollback reserve.

### 15.5 Fourth slot

- #6718 merged bytes alone cannot start C3R-B.
- #6728 remains blocked until every exact-head finding is closed.
- Missing exact aggregate envelope or strict preflight fails before slots=4 fanout.
- `pc-ci-4` in any live roster, production `ci-linux`, or `max-parallel: 4` before accepted gates fails.
- Capacity receipt cannot make semantic CI green.

## 16. Ordered implementation sequence

### RCH-0 — architecture R1 reconciliation

This document and its durable handoff. Records only. It authorizes no downstream mutation by itself.

### C3R-A repair — existing PR #6728

Complete exact-head review `5085372259` on the same PR/branch under a separately admitted builder operation. No host action or self-merge.

### RCH-1 — remote-complete + terminal precedence + exact-head release barrier

Extend the existing Agent Dialogue / Executive continuity / merge-control owners in one independently useful vertical slice:

- command-backed remote-complete receipt;
- branch-writer release after terminal STOP;
- same-PR release-responsibility admission;
- STOP monotonicity;
- exact-head review/CI/hold barrier;
- regression tests reproducing the #6718 failure.

Do not create a new lifecycle or Git carrier.

### RCH-2 — delivery acknowledgement and responsibility-aware wake

Complete ACK1 production qualification and the DELIVERED→ACK crash window through the existing wake owner. Wake exact implementation responsibility while local effect exists and release responsibility after branch-writer release. No watcher registry.

### W5A internal delivery — existing Runner Fleet W5A/EC2A

Implement W5A.1–W5A.5 as one owner, sequenced into independently useful vertical PRs where needed:

1. fresh fleet/host observation and mismatch projection;
2. queue-cause/null-safe timing projection;
3. disk/resource admission visibility and stale-run census;
4. read-only Control Room consumer.

No new workstream, liveness DB, queue mirror, scheduler, receipt family, or publication path.

### Host hygiene internal slice

Extend existing worktree/scratch admission and cleanup owners with disk reserve, quotas, archive-copy refusal, canonical-root checks, and live-process-aware GC. This is not a new host controller.

### C3R-B

After repaired C3R-A acceptance/merge, perform the privileged one-listener-at-a-time host proof. Stop before production promotion.

### C3P

After C3R-B acceptance, perform production 3→4 promotion and natural-traffic/rollback proof.

### Elastic capacity

Only after active main integrity, accepted C3P, portability, and prospective residual-demand evidence. Consume #6717; do not bypass persistent-capacity truth.

Implementation may run in parallel only where authority, files, carriers, effects, and owners are genuinely disjoint. One independently useful capability per PR remains binding.

## 17. Completion law

This program is not complete when this document merges, #6728 merges, a fourth runner registers, CI turns green, Slack delivers, or `max-parallel` changes.

Completion requires:

- **Truth:** fresh declaration-vs-observation and host-attested identity, stale-safe and correction-safe;
- **Continuity:** remote-complete source can release a dead builder without transferring local/effect-unknown work;
- **Release safety:** terminal precedence and exact-head review/merge barriers refuse the #6718 failure before effect;
- **Attention:** delivery acknowledgement and responsibility-aware wake are production-proven;
- **Host resilience:** ENOSPC admission, scratch containment, live-safe GC, and staged rollback are proven;
- **Capacity:** four persistent slots are proven under exact aggregate isolation and render coexistence;
- **Product:** W5A/Control Room explains capacity, queue cause, staleness, responsibility, pressure, and next action;
- **Learning:** prospective receipts show whether 3→4 improves eligible wait without semantic, cleanup, cache, admission, disk, or render regression;
- **Operations:** exact durable decisions/discoveries/handoffs let a fresh session recover the ruling and next action without this chat.

This architecture authorizes no source implementation, review approval, merge, CI retry/cancellation, watcher creation, host action, registration, credential handling, label/group change, ruleset/admin change, provider action, or production promotion by itself.
