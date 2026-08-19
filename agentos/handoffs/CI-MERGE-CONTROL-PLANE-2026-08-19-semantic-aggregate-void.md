---
workstream: WS:CI-MERGE-CONTROL-PLANE
session: claude/heal-semantic-aggregate-dark-step
model: opus
ended_because: blocked
prs: [5964, 5978]
discoveries:
  - DSC:DARK-STEP-VOIDS-THE-WHOLE-MAIN-AGGREGATE
mission: >
  Fleet escalation 2026-08-19: heal the workflow-yaml red on main, which was
  reported as also causing a fleet-wide witness outage (aggregate semantic
  evidence emitted with jobs: []), leaving every session Stop-blocked.
state_before: >
  workflow-yaml was red because #5938 shipped tests/test_ci_gate_reliability_report.py
  named by no run: step. The aggregate evidence for main runs was being emitted as
  jobs: [] with a single planner_configuration_failure.
changed:
  - path: scripts/ci_semantic_proof.py
    what: >
      reconcile_evidence(): the role=="main" branch stamped classification=main_failure
      on ANY non-passed outcome. The validator requires outcome=="failed" for that
      classification, so a step that went dark (not_run_prior_failure / timed_out /
      infrastructure_blocked) raised SemanticProofError and voided the ENTIRE
      aggregate. Now mirrors the pr_head guard: main_failure only when the outcome is
      genuinely "failed", otherwise "unknown" (already a legal main-role value).
  - path: tests/test_ci_semantic_proof.py
    what: >
      Four regression cases, verified to fail without the fix. Drives the real
      reconcile CLI with the exact production shape, pins that dark steps classify
      unknown, that a genuine main failure still classifies main_failure, and that
      semantic_gate_verdict still refuses to clear on unknown.
  - path: agentos/discoveries/DSC-DARK-STEP-VOIDS-THE-WHOLE-MAIN-AGGREGATE.md
    what: the defect as a citable record with its falsifier.
verified:
  - claim: >
      The workflow-yaml unrun-census red was ALREADY healed before this session by
      #5952 (merged 09:03Z); no further work was needed on it.
    command: >
      python3 scripts/audit_unrun_tests.py  (exit 0 on origin/main); and main run
      32235791079 at that commit came back green on ci-pack-1, which owns workflow-yaml.
  - claim: >
      The jobs: [] voiding is INDEPENDENT of that red and recurs on any main red with
      downstream steps in the same job.
    command: >
      gh run download 32235791079 -p "ci-semantic-*" — 44 minutes after the census
      heal, the aggregate voided again on a different job, naming
      qledger-cluster-honest-ci/"qledger forward-only desk adapters + evidence clock
      (P3) + nightly grader & W6 readiness runner".
  - claim: >
      The fix restores the evidence plane on the exact runs that were blocking the fleet.
    command: >
      python3 scripts/ci_semantic_proof.py reconcile --plan <plan> --fragments-dir <frags>
      --output <out>  replayed against BOTH incident runs' own artifacts.
      Run 32231891958: jobs 0 -> 194, infrastructure [] , witness-capable 0 -> 193.
      Run 32235791079: jobs 0 -> 194, infrastructure [] , witness-capable 0 -> 194,
      classifications {passed 610, main_failure 5, unknown 18}, correctly naming
      qledger-cluster-honest-ci, house-law-registry, unrun-intl-libraries,
      unrun-picks-boards, unrun-pit-probes. Still status=failure / rc=1.
  - claim: >
      Every red on PR #5964 is main's own, matched by JOB NAME (pack indices are not
      comparable between a PR and main).
    command: >
      per-pack semantic fragments of run 32239276014 —
      {house-law-registry, qledger-cluster-honest-ci, unrun-intl-libraries,
      unrun-pit-probes} is a strict SUBSET of main's
      {those four, plus unrun-picks-boards}. The diff touches only
      scripts/ci_semantic_proof.py and tests/test_ci_semantic_proof.py; no red job
      reads either file.
  - claim: >
      One of main's reds has a precise, cheap, and so far UNCLAIMED root cause.
    command: >
      git log --oneline origin/main -- data/qledger/control_evidence_clock_start
      -> 13750ecd1789 "engine: regime update 2026-08-19" (dashboard-bot) COMMITTED
      data/qledger/control_evidence_clock_start/demand_chain.json.
      tests/test_qledger_control_policy.py::test_t9_no_clock_file_is_ever_committed
      asserts `git ls-files` over that path is empty. `git check-ignore` says the path
      is NOT ignored, so the nightly's broad data/ staging swept it in.
unverified: []
unresolved:
  - >
    Main is red on four data-coupled jobs (house-law-registry,
    qledger-cluster-honest-ci, unrun-intl-libraries, unrun-pit-probes; plus
    unrun-picks-boards on main's own baseline). PR #5964 inherits four of them and
    therefore cannot merge under the authority-changed standard.
  - >
    The qledger clock-file heal is diagnosed but NOT claimed by this session — see
    the body. It needs the nightly's data/ staging rule fixed, not just an untrack.
next_actions:
  - >
    Watch PR #5964: it is armed merge-on-green and needs no edits. The moment main is
    green on those four job names, a rerun of its failed packs greens the head and the
    sweeper merges it on the next sweep.
  - >
    Heal data/qledger/control_evidence_clock_start/demand_chain.json being committed —
    fix the staging rule or add an ignore entry, then untrack. Owner: qledger lane.
    Opt into a full checkout first; this repo's session worktrees are sparse.
  - >
    After #5964 merges, confirm the unblock on the next main run: download
    ci-semantic-evidence-<run> and assert jobs is non-empty. That is the live
    verification this session could not perform, because it requires a main run that
    postdates the merge.
next_action: >
  RESOLVED the same session. All five of main's reds cleared: qledger healed on main
  independently (.gitignore now covers data/qledger/control_evidence_clock_start/);
  the three test defects landed as PR #5978 (merged 12:16:41Z, commit 7a3771a58156);
  and house-law-registry cleared when the nightly finally wrote
  data/symbol_directory/snapshots/2026-08-19.parquet under the merged #5936 collector
  fix — 13,160 rows, VMRK and RDDT both present, zero NaN symbols. PR #5964 was then
  rebased onto the healed main (conflict was append/append in
  tests/test_ci_semantic_proof.py only; both test sets kept, 44 passed) and is armed
  merge-on-green.
do_not_redo:
  - >
    Do NOT re-heal the workflow-yaml unrun-census red. #5952 fixed it at 09:03Z by
    wiring the suite into the workflow-yaml job; audit_unrun_tests.py exits 0 on main.
  - >
    Do NOT attribute PR #5964's reds to its diff. They are main's, proven by job name
    against main's own baseline, and the diff cannot reach any of them.
  - >
    Do NOT open a second main-red-repair PR. #5929 already holds that lane.
  - >
    Do NOT compare failing ci-pack-N indices between a PR and main to decide whether a
    red is inherited — path scoping and weight rebalance move the same job between
    packs. Match by logical job name from the semantic fragments.
danger_areas:
  - >
    Merging an authority-changing PR (any scripts/**) onto a RED main freezes the
    merged head's red set with the unit-healing path already disabled before
    attribution, which is permanently unclearable. This is why #5964 was NOT
    admin-merged despite every red being provably inherited.
  - >
    The qledger clock-file heal is a data/ path. This session's worktree is SPARSE
    (data/ not checked out) — a write into an omitted tree TRUNCATES the committed
    artifact. Opt in with `python3 scripts/worktree_sparse.py full` before touching it,
    and prefer fixing the nightly's staging rule over a one-off `git rm --cached`,
    which the next nightly would simply undo.
---

## The part that was misdiagnosed

The escalation described one defect: a suite shipped dark, reddening `workflow-yaml`,
and that red causing the aggregate to void. It is two, and they are independent.

The census red was real and is fixed (#5952). The voiding is a separate latent bug in
`reconcile_evidence()` that the census red merely *triggered*, and it had been latent
since #5750. The proof is that it recurred 44 minutes after the census heal, on
`qledger-cluster-honest-ci`, with `ci-pack-1` green.

That distinction matters because the remedies differ in scope. Healing a dark suite
removes one trigger. There is a trigger available on every main red that has further
semantic steps in the same job — which, at main's measured ~44% green rate
(`DSC:MERGE-GATE-IS-GATED-ON-MOVING-DATA`), is most nights.

## Why the blast radius is inverted

The loud symptom is one red check. The quiet one is an evidence artifact that
validates itself out of existence and takes all 194 jobs with it, while reporting a
single proof id that has nothing to do with most of them. A session reading that
message reasonably concludes it has a `workflow-yaml` problem. It does not — it has
no evidence plane at all, and no amount of healing its own head restores one.

## The unclaimed heal

`test_t9_no_clock_file_is_ever_committed` is red on main because tonight's
`dashboard-bot` commit `13750ecd1789` committed
`data/qledger/control_evidence_clock_start/demand_chain.json`. The contract exists to
forbid exactly that (a committed clock file is a hand-written retrospective
timestamp). The path is not gitignored, so the nightly's broad `data/` staging swept
it in.

Untracking the file alone is not the heal — the next nightly re-adds it. The staging
rule or an ignore entry has to change too. Left unclaimed here deliberately: it
belongs to the qledger lane, `#5929` already holds the single permitted
`main-red-repair` slot, and greening `#5964`'s own head would require healing all four
of main's reds, which is precisely the second `main-red-repair` that house law forbids.
