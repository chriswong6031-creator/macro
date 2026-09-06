---
schema: agentos.handoff.v1
workstream: "WS:RUNNER-FLEET-RESILIENCE"
session: "sol/ci-runtime-continuity-live-fleet-hardening-20260901-r1"
model: sol
status: active_checkpoint
ended_because: ci_handoff
program_key: "ci-runtime-continuity-live-fleet-hardening-20260901-sol-001"
operation_key: "ci-runtime-continuity-live-fleet-hardening-20260901-sol-001"
wave: "RCH-0-R1"
state: "ARCHITECTURE_R1_RECONCILED_C3RA_REPAIR_ACTIVE"
mission: >
  Recover the C3R-A fourth-slot program after session ambiguity, terminal-edge confusion, an
  exact-head review bypass, real-host false-proof discoveries, a contained one-slot outage and
  Mac Studio ENOSPC; complete the existing #6728 source repair and harden release, watcher,
  live-fleet, host-admission and staged-rollout behavior without creating a duplicate scheduler,
  registry, lifecycle, queue, retry, watcher, proof, health or merge plane.
state_before: >
  Macro PR #6718 had already merged as b260d28a6efbfb4593dfcc453731f71703252ac0
  while immutable exact-head review 5084468618 remained CHANGES_REQUESTED. The merged source was
  therefore BUILT_NOT_PROVEN / RELEASE_BLOCKED. Real-host installation then disproved two shared
  test premises: systemd slice names expand into /mastermind.slice/mastermind-ci.slice and aggregate
  limits/counters live on the parent slice, not the candidate service leaf. A staged pc-ci-1
  migration refused for about 96 seconds and was rolled back; pc-ci-2 and pc-ci-3 remained serving.
  Repeated full-tree scratch extraction and many simultaneous sessions also exhausted a 1.8 TiB
  Mac Studio filesystem. PR #6728 existed with only the two host-discovered repairs. The first #6729
  architecture draft duplicated the already-frozen W5A owner, described #6718 as a future candidate,
  and collapsed historical three-slot acceptance into current liveness.
changed:
  - path: "docs/superpowers/specs/2026-09-01-ci-runtime-continuity-and-live-fleet-hardening.md"
    what: >
      Replaced the draft with the R1-reconciled architecture. It maps all live-fleet and queue work
      into the existing Runner Fleet W5A/EC2A owner; records #6718 as MERGED / BUILT_NOT_PROVEN /
      RELEASE_BLOCKED and #6728 as the sole active repair carrier; separates historical acceptance
      from action-time liveness; freezes remote-complete branch-writer release, terminal STOP
      monotonicity, exact-head review/merge refusal, delivery acknowledgement, host disk/scratch
      admission, one-listener staged rollout, and the hard C3R-A -> C3R-B -> C3P ladder.
  - path: "agentos/handoffs/RUNNER-FLEET-RESILIENCE-2026-09-01-runtime-continuity-live-fleet-hardening.md"
    what: >
      Reconciled this durable checkpoint to current protected procedure, current Git carriers,
      terminal Slack edges, the #6728 repair commission, exact remaining gates and no-rebuild laws.
verified:
  - claim: "Current protected Sol procedure was atomically loaded before modification."
    command: >
      Fresh-read Mastermind docs/sol_skills/INDEX.md and required COLD_START, RECONCILE_STATE,
      WATCHER_ACTION_LOOP, REVIEW_RETURN, COMMISSION_WAVE, WORKER_AVENUE_ROUTING, CLOSEOUT,
      AGENT_DIALOGUE_SESSION_CLOSE_LAW and EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM from
      821e90f8f0f01dd1ed7bf11a6c548a5f410c2a32.
    result: >
      PASS — mastermind.sol_skillpack.v1 version 1.0.1, minimum bootstrap major 1; every later
      modifying/release operation must re-pin then-current protected master.
  - claim: "The architecture has one owner for live fleet and queue truth."
    command: >
      Compare the R1 architecture with PR #6717 R1 amendment at head
      32636a3846f3e1e96c78980f5848aff77983e960.
    result: >
      PASS at Sol author review — former LFO-1, QPC-1, SQH-1 and CR-1 names are explicitly non-owners
      and map only to internal W5A.1-W5A.5 under WS:RUNNER-FLEET-RESILIENCE / EC2A.
  - claim: "The architecture reflects current C3R-A Git truth without treating merge as acceptance."
    command: >
      Fresh-read issue #6714, merged PR #6718, exact-head review 5084468618, open PR #6728 and review
      5085372259.
    result: >
      PASS — #6718 is merged-but-rejected; #6728 at 04d30860e1309d427e160319072c6cb150f35e47
      is PARTIAL and remains the one repair carrier; C3R-B and production 3-to-4 remain forbidden.
  - claim: "Historical route proof cannot manufacture current liveness."
    command: "Adversarial document read with fresh observation removed."
    result: >
      PASS at Sol author review — historical three-slot acceptance remains PROVEN_LIVE only at its
      receipt timestamps; action-time availability is UNKNOWN until a fresh observed_at-bound
      GitHub/host observation exists.
  - claim: "Stale worker/release loops were given explicit terminal edges."
    command: >
      Read Slack carriers C0BSBM78V1N/1788257745.762809 and
      C0BSBM78V1N/1788317568.499069 after posting terminal STOP replies.
    result: >
      PASS — ci-c3ra-final-release-adjudication-20260901-sol-001 terminated as RELEASE_GATE_FAILED /
      SOURCE_NOT_ACCEPTED; ci-main-integrity-red-relay-audit-20260901-sol-001 terminated as a
      point-in-time READ_ONLY_AUDIT_COMPLETE. Exact child watcher removal was instructed without
      reopening either child.
  - claim: "One bounded same-carrier source repair is assigned."
    command: "Read Slack carrier C0BSBM78V1N/1788321063.979999 and GitHub PR #6728."
    result: >
      PASS for delivery only — operation ci-c3ra-merged-substrate-full-repair-20260901-sol-001 targets
      the existing #6728 branch, requires PICKUP_ACK plus separate START, full six-blocker repair,
      exact hostile mutants, current-head CI and no host/runner/label/production effect. Delivery is
      not pickup, execution or completion.
unverified:
  - claim: "PR #6729 R1 records are release-ready."
    what_would_verify: >
      History-preserving current-main join on the same branch, exact two-path compare, Agent OS and
      hosted CI/fence completion, empty unresolved threads, and a fresh separate-principal exact-head
      architecture approval. Keep DRAFT / HOLD-FOR-SOL until then.
  - claim: "PR #6728 closes every false-proof blocker."
    what_would_verify: >
      Worker ACK/START, same-branch implementation, RED-to-GREEN hostile mutants, exact parent envelope,
      strict main-defined preflight, monotonic/identity-safe receipt windows, cleanup containment,
      exact R14 labels, durable records, terminal current-head CI and separate-principal approval.
  - claim: "Current three-runner fleet is online and healthy now."
    what_would_verify: >
      A fresh observed_at-bound GitHub runner/job read joined to accepted host attestations within the
      action's freshness budget. Historical proof and static policy are insufficient.
  - claim: "Remote-complete transfer, STOP monotonicity and exact-head merge refusal are enforced."
    what_would_verify: >
      A separately admitted RCH-1 implementation in existing Agent Dialogue / Executive / merge-control
      owners, including a regression canary that refuses the exact #6718 review-bypass shape before effect.
  - claim: "Wake delivery acknowledgement closes the DELIVERED-to-ACK crash window."
    what_would_verify: >
      RCH-2 / ACK1 production qualification through the existing wake owner, with no watcher registry.
  - claim: "Host ENOSPC cannot recur."
    what_would_verify: >
      Existing worktree/scratch admission and GC extended with versioned reserve/quota, archive-copy
      refusal, live-process ownership and prospective high-pressure canaries.
unresolved:
  - "#6728 repair child has been delivered but, at this checkpoint, has not yet ACKed or STARTed."
  - "#6729 R1 branch still requires remote commit/readback, hosted validation and independent exact-head review."
  - "Main integrity remains non-authoritative until its existing #6637 lane reaches active exact publisher/required-workflow enforcement."
  - "Trusted-red relay remains its own existing #6628 carrier and requires then-current release/proven-live reconciliation."
  - "Current live runner/queue/host truth remains W5A work and must be fresh-read at every modifying gate."
  - "C3R-B privileged host/admin/registration surface, natural drain and credential ceremony are not yet bound."
  - "C3P natural-traffic promotion, rollback and learning evidence remain not built."
next_actions:
  - >
    Monitor the exact #6728 Slack carrier. On PICKUP_ACK verify the named native task/GitHub identity;
    require a separate START before source effect. On BLOCKED/DECISION_REQUEST/RESULT, fresh-read and
    issue one explicit same-carrier Sol CONTINUE, REQUEST_REPAIR or terminal STOP.
  - >
    Commit this R1 architecture and handoff on the existing #6729 branch with prior branch head as first
    parent and then-current Macro main as second parent; verify the exact effective diff remains these
    two records-only paths; keep DRAFT / HOLD-FOR-SOL.
  - >
    Commission one separate-principal exact-current-head review for #6729 after hosted checks are visible;
    repair only genuine findings on the same carrier and merge records only when expected-head,
    current-main, path, CI, review, thread and action-time gates all pass.
  - >
    After #6728 accepts and merges, activate a fresh C3R-B privileged host child; install and prove one
    listener at a time, register pc-ci-4 without production ci-linux, run one slots=4 diagnostic with a
    real render and stop before production promotion.
  - >
    After C3R-B acceptance, activate C3P for production roster/max-parallel 3-to-4, natural traffic,
    queue/resource learning and rollback proof.
  - >
    Separately decompose RCH-1, RCH-2, W5A internal verticals and host-hygiene hardening only after each
    owner/current-state/collision gate; do not bundle them into #6728 or #6729.
do_not_redo:
  - "Do not revive terminal ci-pc-fourth-slot-recovery-20260901-sol-001 or terminal release/audit children."
  - "Do not create a replacement #6728 PR/branch, second C3R-A writer, duplicate fourth-slot source, or blind failover for ambiguous effects."
  - "Do not treat #6718 merge, #6728 local tests, GitHub QUEUED, Slack delivery, static runner policy or a helper invocation as acceptance, physical capacity or production proof."
  - "Do not create LFO/QPC/SQH/CR workstreams outside the existing Runner Fleet W5A/EC2A owner."
  - "Do not create another lifecycle, scheduler, queue, registry, retry plane, watcher service, proof store, main-health gate or merge controller."
  - "Do not register/label pc-ci-4, mutate runner groups/services/cgroups/hosts, run slots=4, handle credentials or move max-parallel to 4 in source/records waves."
  - "Do not use full git archive/tar source copies by default or delete active foreign worktrees to recover space."
  - "Do not let a late CONTINUE or stale watcher fire reopen a terminal child."
danger_areas:
  - >
    Merge is not acceptance. #6718 proves exact-head CHANGES_REQUESTED must be a hard pre-effect barrier,
    not merely a post-merge diagnostic.
  - >
    A remote-complete receipt is invalidated by any later modifying continuation; local/effect-unknown
    work remains exact-session sticky, while release maintenance becomes a separate responsibility on
    the same PR only after terminal worker STOP.
  - >
    Systemd slice hyphens encode hierarchy, aggregate ceilings/counters live on the parent slice, and
    candidate leaf metrics can falsely look like aggregate proof. Require exact parent/candidate identity.
  - >
    Updated Slice=/--require-slice units, helper and parent slice must be installed as one compatible
    drain-bounded set. All-at-once migration can take the complete CI pool down; one-listener staging and
    exact rollback are mandatory.
  - >
    Current runner availability cannot be inferred from historical acceptance or checked-in policy.
    Missing/stale observation is UNKNOWN, not offline or healthy.
  - >
    Host pressure can turn ordinary current-main reconciliation into an operational outage. Admission
    must reserve space for Git writes, active runners, logs and rollback before creating worktrees or
    scratch copies; cleanup must never follow symlinks or destroy live foreign ownership.
  - >
    Terminal STOP removes only the exact child watcher source. WATCH_STOP_FAILED reports transport cleanup
    failure but never reopens the child or authorizes a successor.
---
