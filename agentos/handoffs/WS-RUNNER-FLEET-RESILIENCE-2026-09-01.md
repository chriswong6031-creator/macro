---
workstream: "WS:RUNNER-FLEET-RESILIENCE"
session: "claude/ci-c3ra-fourth-slot-source-20260901 (worktree fourth-slot-source-recovery-19eb45)"
model: opus
ended_because: complete
mission: >
  Operation ci-pc-fourth-slot-recovery-20260901-sol-001 (issue #6714, C3R-A).
  Independently re-derive from current Macro main the CODE SUBSTRATE ONLY for a
  fourth sealed PC CI slot plus its aggregate resource envelope, completing frozen
  plan docs/superpowers/plans/2026-08-26-pc-ci-fourth-slot-resource-isolation.md
  Tasks 1-5 under RED-first TDD with independent adversarial review, and return one
  exact-head DRAFT / HOLD-FOR-SOL PR. Live production must remain at exactly three
  CI slots and max-parallel 3. Zero host, runner, registration, credential, cgroup,
  cache or render mutation.
state_before: >
  #6351 P4 is PROVEN_LIVE and admits C3 fourth-slot capacity relief independently.
  Policy declared exactly three PC CI slots with no vocabulary for pending capacity,
  so a fourth slot could only be expressed by RAISING the live count. The canary
  admitted slots=1|3 only. Resource monitoring was host-global only, with no cgroup
  binding at all. There was no CI slice template and cleanup admitted three roots.
  The predecessor child #6640 (operation ci-pc-fourth-slot-20260829-sol-001) is
  terminal SOL CLOSED / STOP, closed not_planned after an authority violation, with
  its bytes quarantined. It produced no PR, no remote branch and no host effect.
changed:
  - path: .github/runner-policy.yml
    what: >
      pool_topology.pc-ci gains pending_slots: 1, pending_carriers: [pc-ci-4] and
      pending_labels: [self-hosted, Linux, X64]. slots stays 3 and
      label_registry.ci-linux.carried_by stays [pc-ci-1, pc-ci-2, pc-ci-3].
      pending_labels deliberately OMITS ci-linux so the fourth runner can later be
      bootstrapped online but unroutable.
  - path: scripts/check_runner_policy.py
    what: >
      New rule R14 (_pending_capacity_findings) owns the live/pending boundary. It
      refuses a fifth slot (live+pending must total exactly 4), a carrier name other
      than the exact next slot, a pending block on any pool other than pc-ci, a
      pending label outside platform identity, a missing pending contract, and —
      the activation act itself — any pending carrier appearing in ANY
      label_registry carried_by roster. Module docstring documents R14.
  - path: .github/workflows/selfhosted-ci-canary.yml
    what: >
      slots input options 1|3 -> 1|3|4. The red-surfacing gate and the
      render-reservation-probe condition change from `inputs.slots == '3'` to
      `inputs.slots != '1'`. runs-on, max-parallel, hosted planner, semantic plan,
      cache, labels and the render-reservation job are otherwise untouched.
  - path: scripts/select_ci_canary_packs.py
    what: "--count argparse choices (1, 3) -> (1, 3, 4); 5 still refused."
  - path: scripts/monitor_ci_host_resources.py
    what: >
      New EXPECTED_SLICE, candidate_cgroup() and slice_sample(). Each candidate
      derives its own cgroup from /proc/self/cgroup and must bind to
      /mastermind-ci.slice/<unit>.service by exact path COMPONENT. Emits
      bound/refused/degraded/unavailable; refused and unavailable carry NO metric
      values. Adds --cgroup-root and --proc-self-cgroup so the logic is testable off
      Linux. Stays stdlib-only self-contained (it is copied alone into the
      trusted-control directory outside the untrusted candidate checkout).
  - path: scripts/capture_ci_canary_receipt.py
    what: >
      New load_samples() and slice_metrics(), plus receipt key "ci_slice". Reports
      aggregate numbers only when EVERY sample in the window was cleanly bound;
      otherwise it returns the worst status with all numbers null. memory.peak is
      exposed as memory_peak_bytes_cgroup_lifetime with memory_peak_is_run_local
      false. The host-global metrics() reduction keeps its exact previous keys.
  - path: ops/runner-host/pc/mastermind-ci.slice.template
    what: >
      NEW. The frozen envelope exactly — CPUQuota=800%, CPUQuotaPeriodSec=100ms,
      MemoryHigh=10G, MemoryMax=12G, MemorySwapMax=2G — with CPU/memory/IO/tasks
      accounting enabled. AllowedCPUs, CPUWeight, IOWeight and TasksMax deliberately
      unset this wave. Sets no KillMode, so CI's control-group kill semantics cannot
      leak onto a render unit.
  - path: ops/runner-host/pc/actions-runner-ci.service.template
    what: >
      Adds Slice=mastermind-ci.slice and --require-slice on the ExecStartPre guard.
      Every pre-existing seal is preserved (KillMode=control-group, ReadOnlyPaths,
      ReadWritePaths, UMask=0022, StartLimitIntervalSec=0, the full sandbox set).
  - path: ops/runner-host/pc/mastermind_ci_resource_guard.py
    what: >
      Adds slice_reasons(), THRESHOLDS_VERSION and PREFLIGHT_PROFILES, plus
      --require-slice, --preflight-profile, --cgroup-root, --proc-self-cgroup.
      Thresholds are versioned separately from the slice ceilings. The steady
      profile keeps the accepted 4 GiB floor; four-slot-canary adds the plan's
      stricter pre-diagnostic gate (20 GiB MemAvailable, 512 MiB swap, PSI full
      avg10 < 0.10). The memory floor stays a guest-wide MemAvailable read.
  - path: ops/runner-host/common/runner_cleanup.py
    what: >
      PC_CI_ROOTS admits /opt/mastermind-ci/runner-4. Still an exact allowlist, not
      a prefix match, so runner-5, runner-0 and any render root remain refused.
  - path: docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md
    what: >
      New "Fourth slot and the aggregate CI resource envelope" section: capability
      state, what pending means in policy, the envelope table, render-outside-the-
      slice proof, evidence/refusal semantics, the cumulative-vs-delta trap, the
      security-sensitive registration stop, and this carrier's rollback. pc-ci-4 is
      added to the pool topology table marked not registered.
verified:
  - claim: >
      All three governing suites pass on the exact head, including 10 new policy
      tests, 5 new canary-workflow tests and 26 new tool tests.
    command: "python3 -m pytest -q tests/test_runner_policy.py tests/test_ci_canary_workflows.py tests/test_ci_canary_tools.py"
    result: "135 passed, 168 warnings in 24.95s"
  - claim: "The runner-policy guard passes on the live tree with the pending fourth slot declared."
    command: "python3 scripts/check_runner_policy.py"
    result: "OK: P3B-B routes only same-repository PR execution through the protected-main PC executor. (rc=0)"
  - claim: >
      Every new test was RED before its implementation. Task 1 failed 10/12 with
      KeyError 'pending_slots' and, critically, the guard returned rc=0 when pc-ci-4
      was appended to ci-linux.carried_by — that silent pass is the hole R14 closes.
    command: "python3 -m pytest -q tests/test_runner_policy.py -k 'pending or three_slot_bound'  (run before implementing R14)"
    result: "10 failed, 2 passed, 37 deselected — the 2 passing are pre-existing-invariant regression guards"
  - claim: "The CI pack manifest still validates with the changed workflow and scripts."
    command: "python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-count 12 --validate-only"
    result: "Validated 206 legacy jobs; 206 in scope; pack weights=[860, 626, 626, 625, 625, 625, 627, 627, 627, 627, 625, 625]"
  - claim: >
      The 10 agentos validate errors are INHERITED from main, not introduced here.
      All 10 are in agentos/handoffs/AUTONOMY-MASTERMIND-OS-2026-08-30-accelerated-execution-reconciliation.md,
      a file this carrier never touched, and a clean origin/main tree reports the
      identical count.
    command: "git archive origin/main agentos scripts/agentos.py | tar -x -C $TMPD && cd $TMPD && python3 scripts/agentos.py validate"
    result: "agentos: 966 records — 10 error(s), 595 warning(s), identical error count to this head"
  - claim: "Production concurrency is unchanged: trusted-executor still binds three slots."
    command: "grep -n 'max-parallel' .github/workflows/trusted-ci-executor.yml"
    result: "319:      max-parallel: 3"
  - claim: >
      No open PR collides with any owned path. Census over all 72 open PRs by exact
      changed-path intersection returned zero hits; the single census blind spot
      (#6657, files null via list) has 0 files on direct read.
    command: "gh pr list --state open --limit 200 --json number,title,headRefName,isDraft,files  + jq path intersection over the 16 owned paths"
    result: "zero collisions; #6657 files length 0"
  - claim: >
      The predecessor #6640 produced no remote artifact to collide with or be
      tempted by: it is a closed ISSUE, no PR of that number exists, and no remote
      branch matches the fourth-slot carrier.
    command: "gh issue view 6640 --json state,stateReason ; gh pr view 6640 ; git ls-remote --heads origin | grep -Ei 'fourth|pc-ci|slot|canary'"
    result: "issue CLOSED/NOT_PLANNED; PR 6640 does not resolve; only sol/runner-fleet-w1a-hosted-merge-canary matches, a different W1-A scope"
unverified:
  - claim: >
      That the slice actually bounds four concurrent candidates to 8 vCPU-equivalents
      and 12 GiB on the real WSL guest, and that pc-ci-1..3 restart cleanly into the
      slice at a natural drain.
    what_would_verify: >
      The C3R-B privileged host carrier: install the slice, replace the three units
      from their exact pre-change snapshot, restart only those listeners, and read
      back cpu.max / memory.max / cgroup membership per PID. Nothing in this carrier
      can establish it, because nothing is installed.
  - claim: >
      That a four-slot canary dispatch selects four distinct non-empty packs against
      a REAL plan.json and that all four hosted controls reach strict parity.
    what_would_verify: >
      One slots=4 dispatch after pc-ci-4 exists. Deliberately not run here: a
      four-slot diagnostic dispatch is an explicit hard non-goal of C3R-A, and with
      only three live carriers the fourth matrix leg would queue indefinitely.
  - claim: "That the renderer is unaffected in practice while CI saturates the slice."
    what_would_verify: >
      The canary's render-reservation-probe during a real slots=4 run alongside a
      real render workload. Source proves only that render is not IN the slice.
unresolved:
  - >
      C3R-B (privileged host installation and four-slot acceptance) is unstarted and
      requires a fresh host/runner/group/resource census plus explicit Chairman/Sol
      authorization for the organization runner registration.
  - >
      Production promotion of trusted-executor max-parallel 3 -> 4 is a THIRD,
      separate carrier, permitted only after C3R-B is Sol-accepted.
next_actions:
  - >
      Sol reviews the held DRAFT PR and either accepts C3R-A or returns REPAIR. Do
      not merge it from a worker seat; this carrier holds by commission.
  - >
      On acceptance, open C3R-B as a fresh child. Before any privileged act, re-run
      a host/runner/group/resource census and obtain explicit confirmation for the
      pc-ci-4 organization registration. Never paste a registration token anywhere.
  - >
      In C3R-B, bring pc-ci-4 online WITHOUT ci-linux first, prove roster/service/
      PID/root/cgroup identity and slice membership, then run exactly one four-slot
      diagnostic in a naturally safe pressure window with a real render workload.
  - >
      Only after C3R-B acceptance, a separate promotion carrier adds pc-ci-4 to the
      live carrier list and moves trusted-executor max-parallel to 4, followed by
      natural traffic proof and rollback-on-regression.
do_not_redo:
  - >
      Do NOT express the fourth slot by raising pool_topology.pc-ci.slots. R14 refuses
      it and R7 already did. The live/pending split is the accepted shape: slots is
      live inventory, pending_slots/pending_carriers/pending_labels are architecture.
  - >
      Do NOT add ci-linux to pending_labels or pc-ci-4 to any carried_by roster to
      "make the code consistent". That IS the live activation act and R14 refuses it
      by design; it belongs to the separately audited C3R-B activation packet gated
      on a GitHub online/idle receipt.
  - >
      Do NOT make the prestart guard refuse on cumulative memory.events `high`. These
      counters are cumulative over the slice lifetime and `high` counts MemoryHigh
      reclaim working as designed, so refusing on it means that once CI ever touched
      10G every later listener start refuses forever and the slot is stranded
      permanently. This was written that way first and the test fixture caught it.
      The plan's "zero high/max/oom/oom_kill DELTA" is a per-run acceptance criterion
      owned by slice_metrics(), not by the gate.
  - >
      Do NOT make the resource guard's memory floor slice-local. The renderer lives
      OUTSIDE the slice, so a slice-local read shows a nearly idle cgroup while the
      guest is starved and would admit a CI job that then starves render. The floor
      is deliberately guest-wide MemAvailable.
  - >
      Do NOT let slice evidence fall back to host-global metrics when the cgroup is
      wrong. refused/degraded/unavailable carry no numbers on purpose: a green
      produced from the wrong cgroup reads downstream as proof, which is worse than
      no green.
  - >
      Do NOT touch, cherry-pick, recover or inspect-as-authority the terminal #6640
      carrier. Everything here was re-derived from main. #6640 has no PR and no
      remote branch, so there is nothing to salvage anyway.
  - >
      Do NOT add a second monitor, receipt schema, scheduler, queue, runner registry,
      cache or proof plane. Task 3 extends the EXISTING monitor and receipt on
      purpose; the receipt stays ci.selfhosted_canary_receipt.v2 with one added key.
danger_areas:
  - >
      ops/runner-host/pc/actions-runner-ci.service.template now carries
      Slice=mastermind-ci.slice AND --require-slice. These two must be installed
      together with the slice unit. Shipping the unit to a host without
      /etc/systemd/system/mastermind-ci.slice is a bootstrap hazard for pc-ci-1..3 —
      sequence it at a natural drain per the runbook, and keep the exact pre-change
      unit snapshot for rollback.
  - >
      scripts/monitor_ci_host_resources.py and scripts/select_ci_canary_packs.py are
      copied ALONE into a trusted-control directory outside the untrusted candidate
      checkout. They must stay stdlib-only and import no sibling module, or the trust
      boundary breaks in a way tests off-host will not notice.
  - >
      The canary conditions now read `inputs.slots != '1'` rather than naming a
      count. Adding a new slots identity later inherits multi-slot semantics
      automatically — which is correct — but adding a new SINGLE-slot identity would
      silently inherit the wrong branch. Gate on the semantic, not the literal.
  - >
      _is_bound_to_ci_slice does exact path-COMPONENT matching. A substring test
      would accept `other-mastermind-ci.slice`; do not "simplify" it to `in`.
  - >
      R14 derives both the expected pending carrier name and the expected ci-linux
      roster from the live `slots` value. If a future carrier legitimately changes
      the live count, R14's expectations move with it by construction — verify that
      is intended rather than assuming the constant is pinned.
prs: [6714]
---

# Summary

`FOURTH_SLOT_CODE_SUBSTRATE = BUILT_NOT_HOST_PROVEN`. Everything needed to run four
PC CI candidates inside one enforced envelope now exists in the repository, and none
of it is installed. No `pc-ci-4` registration, no `/opt/mastermind-ci/runner-4`, no
`mastermind-ci.slice` on any host, no fourth listener. Live capacity is still three
slots; trusted execution is still `max-parallel: 3`; `ci-linux` is still carried by
exactly `pc-ci-1..3`.

The load-bearing design property, worth preserving: **live capacity and code
capability are separate vocabulary, and the guard refuses to let them merge.**
`slots` is what is routable; `pending_slots`/`pending_carriers`/`pending_labels` are
what the code supports. Rule R14 makes the activation act — `pc-ci-4` entering any
`carried_by` roster, or `ci-linux` appearing in `pending_labels` — a CI failure
rather than a one-line edit. Before R14, appending `pc-ci-4` to
`label_registry.ci-linux.carried_by` passed the policy guard clean; that silent pass
is the hole this closes, and it is the exact shape by which a policy file starts
claiming capacity that does not physically exist.

The second design property: **slice evidence refuses rather than substitutes.** Once
four candidates share one envelope, host-global numbers cannot distinguish "CI stayed
inside its budget" from "the guest happened to be quiet". Every candidate binds to
`/mastermind-ci.slice/<unit>.service` by exact path component; a wrong cgroup yields
`refused` with no numbers at all, and the reducer reports aggregates only when every
sample in the window was cleanly bound. A green produced from the wrong cgroup would
read downstream as proof, which is strictly worse than a missing green.

One design bug is recorded in `do_not_redo` because it was written wrong first and a
test fixture caught it before it shipped: the prestart guard originally refused on
cumulative `memory.events` `high`. Those counters are cumulative over the slice
lifetime and `high` counts `MemoryHigh` reclaim working exactly as designed, so that
rule would have meant that once CI ever touched 10G, every subsequent listener start
refused forever and the slot was stranded permanently. The gate now refuses only on
real kills; the zero-delta requirement is a per-run acceptance criterion owned by the
receipt reducer.

Render stays outside the slice by construction, and that is proven from source: the
slice sets no `KillMode`, and a test asserts `actions-runner-ci.service.template` is
the only checked-in unit carrying `Slice=mastermind-ci.slice`. What source cannot
prove — that four concurrent candidates actually stay inside 8 vCPU-equivalents and
12 GiB on the real guest, and that the renderer is unaffected in practice — is listed
under `unverified` and belongs to C3R-B.
