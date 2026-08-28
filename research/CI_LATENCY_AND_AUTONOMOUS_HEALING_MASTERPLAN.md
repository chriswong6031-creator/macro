# CI Latency + Autonomous Healing — masterplan

**Commissioned by the operator, 2026-08-17.** Status: active; W1 and substantial
planner/checkout infrastructure have landed, trusted-PC production routing is in
P3B-B on issue #6351, and the remaining latency/capacity waves are held behind that
route's exact-head proof and P4 natural-traffic acceptance.

This is a **dedicated wave, deliberately separate from PR #5823**. Standing constraint
for the whole program: *do not let a routing-feature PR rewrite CI infrastructure while
it is trying to become green.* A feature PR that also edits the planner, the packer, or
the gate cannot be reasoned about — its own red is then indistinguishable from the
infrastructure it is changing. Every wave below lands as its own PR against a green base.

**Explicit non-goal: do NOT replace the `ci-pack` system.** The 194→6 semantic scoping
already does real work (measured on #5823: `scoped to 16 changed file(s): 6/194 jobs
(2 unscoped always-on, 4 scoped matches); derived scopes for 177/194 jobs; 15 declared
exclusive`). This program is that system's next maturation step — fast front-door
validation, cheap checkouts, cached base proofs, empirical balancing, a closed-loop
healer — not a rewrite.

## 2026-08-26 current-state amendment

This amendment reconciles the original charter with the system that now exists. It does
not authorize a parallel CI plane and it does not make the private-repository cutover.

### What the repository is actually doing

- The code gate currently contains **132 logical jobs**, partitioned into twelve stable
  semantic check names. A full-suite validation at current main reports pack weights
  `274,272,172,172,172,171,170,170,170,170,173,171`; the first two partitions carry a
  materially heavier tail than the other ten.
- Ordinary PRs do **not** automatically execute all 132 jobs or all twelve packs. The
  hosted planner computes one exact changed-file set, conservatively infers ownership,
  and launches only the non-empty pack indices. Global-invalidating paths, unscoped jobs,
  opaque filesystem/subprocess traversals, and deliberately broad owners still widen a
  PR. That conservatism is why a small-looking change can legitimately select a long
  tail.
- A logical job is one serial sequence of checkout, tool setup, dependency installation,
  and one or more validation steps. The repository repeatedly folded unrelated suites
  into existing logical jobs to preserve the representative-diff scoping ratio. That kept
  coverage visible, but it also made one selected owner inherit every folded suite and
  made a slow step hold the whole pack open.
- P1/P2 proved three isolated Linux/x86 CI slots on the PC with a root-owned read-only
  object cache and an independent render reservation. P3B-A made the main-owned executor
  callable. P3B-B is the single live production-route carrier; no latency or slot-count
  edit may overlap it. P4 must then prove three natural ordinary PRs before the route is
  accepted as production behavior.
- The PC is a 24-core/24-thread Core Ultra 9 285K, but WSL is intentionally limited to
  16 CPUs, 44 GiB memory, and 8 GiB swap. Three CI candidates are proven. A fourth is the
  next admissible experiment only after an aggregate CI cgroup/slice budget and a
  render-aware resource receipt exist. Six or eight are not inferred from idle core
  count.
- The stationary M4 Pro MacBook is available for six months, but it is a macOS/ARM host,
  not a semantic substitute for Linux/x86 CI. Its first lawful role is a narrow,
  main-defined `macos-arm-validation` capability with no production route. The three
  current M4 minis are deferred because they will be replaced in roughly two weeks; the
  role must be device-independent so a replacement mini can assume it later.

### Why packs are numerous and why some are long

The answer is not simply "the codebase is huge." The repository spans product rendering,
data contracts, workflow authority, market engines, publication, Agent OS, deployment,
and security fences, so broad validation is real. But the current latency comes from four
separable mechanisms:

1. **Conservative ownership.** Static inference must widen when a test traverses the
   filesystem, launches opaque subprocesses, imports dynamically, or owns a global graph.
2. **Folded ownership.** Several independent suites share one logical owner because the
   manifest's scoping-ratio guard punished adding a broad job. Selecting that owner runs
   the whole bundle.
3. **Repeated environment startup.** Every selected pack repeats checkout, Python/Node
   setup, virtual-environment creation, and dependency installation before useful work.
4. **Stale balancing units.** Hand-maintained job weights do not reliably predict current
   checkout/install/test wall time, so one long owner can dominate the verdict after the
   other packs finish.

This is recognizable in large monorepos, but mature systems normally combine explicit
ownership graphs, hermetic task caching, immutable dependency caches, empirical weights,
and a small always-on trust core. Running every test for every PR is not the target here;
running every validation that the exact change can affect, plus the non-negotiable trust
fences, is.

### Revised execution order

The route and latency programs share authority files, so they are serialized:

1. Finish the existing P3B-B carrier and P4 natural-traffic proof without changing its
   planner, job selection, pack topology, or resource envelope.
2. Capture a current per-logical-job cost/selection corpus from those natural PRs. This is
   the baseline for every later latency claim.
3. Split false ownership coupling, beginning with suites folded into broad jobs. Preserve
   the actual security/merge fences and use coverage-audited `scope: exclusive` only where
   the closure checker proves the declaration complete.
4. Remove repeated startup cost with immutable dependency caches keyed by lock/input and
   execution profile. Candidate jobs may consume but never mutate shared cache state.
5. Add result reuse only for hermetic jobs keyed by exact tree/input/dependency/toolchain
   identity. Missing, stale, corrupt, or non-hermetic evidence must execute live.
6. Recalibrate job weights and, only from measured evidence, reconsider the fixed twelve
   partitions. Check names remain stable until merge-control consumers are migrated.
7. In a separate capacity carrier, prove a fourth PC slot under one aggregate CI resource
   slice and a naturally active render. Do not proceed to six until four has a clean
   pressure, cache, teardown, and render receipt.
8. In a separate host carrier, build the device-independent macOS/ARM validation role and
   keep production routing disabled until its isolation, reboot, contamination, cache,
   and thermal gates pass.
9. Recompute hosted-minute projection, ordinary-PR p50/p95, simultaneous-PR queueing, and
   render/native contention. Only then assemble the private-cutover packet.

---

## §0 ACCEPTANCE GATES

Hard SLOs. A wave is not done until its own gate holds **and** no earlier gate regressed.

| Metric | Target |
|---|---|
| structural/preflight failure surfaces | < 2 min |
| CI planner (`ci-plan`) | < 1 min |
| per-pack checkout | < 60 sec |
| ordinary green PR, final push → gate | < 10 min p95 |
| heavy PR | < 15–20 min p95 |
| PR-owned red routed back to producing agent | automatic |
| avoidable cancelled / micro-push runs | near zero |
| same-SHA green→red nondeterminism | **zero tolerated** |

Program-level gates, binding on every wave:

1. **No wave may weaken the semantic proof law.** Base evidence may be *cached* and
   *reused*; it may never be *assumed*. Fail-closed stays fail-closed: absent, expired,
   or contract-changed evidence forces a live replay. A wave that turns a missing proof
   into a pass is rejected outright.
2. **Every latency claim is measured, not asserted.** Before/after numbers from real runs,
   named run IDs, p50/p95 — never "should be faster". Reuse
   `scripts/capture_ci_canary_receipt.py` / `compare_ci_canary_receipts.py` /
   `monitor_ci_host_resources.py` rather than minting a second instrumentation path.
3. **No silent coverage loss.** Any wave that narrows what runs prints what it dropped
   (`::warning`, line-start, bare `print(..., flush=True)` — never through a logger, per
   the CI-guarded house rule). A pack that runs fewer jobs must say so by name.
4. **Designed-red contexts generate zero healing work.** `ci-authority/codex/merge-queue-pilot`
   is intentionally red on main-targeted PRs (#5815); `ci-authority/main` is the binding
   authority. Any classifier that files work against a designed-red is itself a defect.
5. **Each wave ships its own guard + test.** An SLO with no automated check is a wish;
   the next regression re-teaches it by hand.

---

## §1 The problem, as measured

Evidence from 2026-08-17 (two PRs, same afternoon):

- **Planner is a bottleneck, not a router.** `ci-plan` took **6m51s** on PR #5826 — to
  discover changed files and select six jobs. Operator-supplied profile: ~7 min wall,
  with a ~3m47 compute stage. The planner needs a broad repo checkout to answer a
  question that PR changed-file metadata already answers.
- **Checkout dominates execution.** Operator-supplied: pack 3 spent **3m03 materializing
  the repository to execute 53 seconds of work**. The repo is ~19 GB.
- **Pack balance is badly skewed.** Operator-supplied: one pack **13m36**, another
  **53 seconds**. Weights are hand-maintained and stale. Observed on #5823:
  `ci-pack-0` 16m55s vs `ci-pack-3` 4m11s.
- **Structural failures cost a full expensive cycle.** #5823's `ci-pack-0` red was
  `tests/test_agent_routing_control.py is a collecting pytest suite named by no run: step`
  — a *registration* fault, knowable in seconds, that instead surfaced after **16m55s**
  of pack execution.
- **Two-cycle discovery.** That PR's two root failures sat in different packs, so fixing
  one and waiting ~20 min to discover the other was the default path. (This wave's
  companion repair deliberately landed both in one push.)
- **Red is over-reported to humans and agents alike.** GitHub showed four reds on #5823;
  there were **two root causes**, one downstream aggregator (`ci-gate`), and one
  designed-red non-binding receipt. Nothing in the UI or the evidence packet says so.

Consequence: an agent session cannot close its own loop. It pushes, waits ~30 min, reads
an ambiguous red, and cannot tell "my bug" from "main was already broken" from "runner
flake" from "that one is red on purpose".

---

## §2 Waves

Ordered. Each is one PR. W1 is already discharged; W2 is the highest-leverage remaining.

### W1 — Repair #5823 in one push *(DONE, 2026-08-17)*
Wire the orphan suite into its owning job; reproduce and repair the HOUSE-U2 routing
matrix. Landed as `b1fbfd45bcf2` on `claude/fable-agent-routing-control`. Found in
passing, and worth carrying forward as method: the matrix failure split into a **genuine
guard bug** (an `^`-anchored `FABLE-WHY` regex that could never match the documented
`// FABLE-WHY:` JS-comment form, silently denying every fable workflow stage) and
**intended contract tightening** (three tests encoding the superseded contract). A red
pack is not one verdict — classify per assertion before touching either side.

### W2 — Fast Preflight gate (< 2 min), ahead of `ci-plan`
A cheap structural front door that runs **before** any expensive pack launches, and
short-circuits the run on registration/shape faults. Candidate contents, all already
existing as scripts: `audit_unrun_tests.py`, workflow-YAML validity
(`check_workflow_yaml.py`), trigger closure (`check_ci_trigger_closure.py`),
skip-only-suite detection, manifest validation, changed routing-contract checks,
template↔site pair sync, blocklist drift.

Gate: a fault of #5823's class surfaces in **30–120 s**, and the expensive packs
**never launch**. Guard: a test asserting preflight precedes `ci-pack` in the dependency
graph, so a later edit cannot reorder it back.

Watch: preflight must not become a second scoping authority. It answers *"is this diff
structurally well-formed"*, never *"which jobs run"*.

Implementation must specify and test the full dependency/aggregate matrix on the
post-P3B-B workflow: same-repository trusted execution, fork-hosted execution,
`workflow_dispatch` main proof, a no-work PR, malformed/absent planner evidence, and
preflight failure. Uncertainty widens to the existing full-suite path; it never suppresses
work. `ci-gate` must still publish one affirmative conclusion when downstream packs are
lawfully skipped. Checks that can be red on base use the existing differential
base-versus-head contract rather than becoming absolute always-on fleet blockers.

### W3 — Collapse the planner (< 60 s) *(CAPABILITY LANDED; residual work measured only)*
The sparse/tracked planner checkout and preserved selection law have landed. Do not reopen
or duplicate W3. Profile current natural traffic after P4; only a measured residual above
the gate may commission a new optimization carrier. That carrier may feed PR changed-file
metadata directly or further reduce the exact authority/config/scope materialization, but
checkout and compute remain separately receipted.

Gate: `ci-plan` < 60 s p95, with the **identical** job selection as today on a corpus of
replayed real PRs (selection equality is the correctness proof; a faster planner that
picks different jobs is a regression, not a win).

### W4 — Planner-produced per-pack sparse manifests (< 60 s checkout)
The planner already knows which logical jobs a pack owns; it should also emit the files
and dependency roots that pack needs, so a pack materializes a slice rather than 19 GB.
`scripts/ci_scope_dependencies.py` and the existing sparse-worktree machinery
(`config/sparse_worktree.json`, `scripts/worktree_sparse.py`) are the reuse surface.

Gate: per-pack checkout < 60 s; **zero** same-SHA green→red nondeterminism across a
replay corpus. Hard hazard, learned the expensive way in this repo (2026-08-13): a write
into an omitted tree **truncates** the committed artifact, and a guard whose baseline
lives under an omitted tree **over-reports**. Any pack manifest must therefore either
materialize what its jobs read or make the absence loud — never silently thin a tree a
job then writes into. Sparse-blind guards should read omitted bytes from HEAD (the
pattern already established for `check_template_site_sync.py`).

### W5 — Cached exact-base evidence; remove synchronous replay from the red path
Preserve the semantic law; stop paying for it synchronously on every ordinary red. Cache
base evidence keyed by **exact base SHA + job execution digest + proof ID**. Consume
trustworthy existing evidence immediately; live-replay only when evidence is absent or
the execution contract changed. `scripts/ci_semantic_proof.py` is the existing authority
and must remain the single one.

Gate: measured minutes removed from red feedback, with the fail-closed property proven by
mutation — corrupt/expire/contract-shift the cached evidence and confirm a replay is
forced. §0 gate 1 governs: cached, never assumed.

### W6 — Empirical pack balancing
Record checkout, dependency install, head execution, and base-replay time **separately**
for every logical job. Partition on rolling hosted-runner p50/p95 instead of stale
hand-maintained weights. Note `run_ci_pack.py` already rebalances when any job's weight
moves — so pack indices are not stable identifiers, and no report may hard-code one.

Gate: max/min pack wall-clock ratio ≤ 2× on a replay corpus (from the current ~15×:
13m36 vs 53 s).

### W7 — CI Failure Router / healer
Classify every concluded red as exactly one of:

| Class | Advisory disposition |
|---|---|
| `PR_OWNED` | evidence names the producing carrier and exact failed logical job, command, annotations, and changed files |
| `BASE_INHERITED` | evidence names the CI/main owner — **never** the feature author |
| `INFRA_TRANSIENT` | eligible for a later controller-owned bounded retry only after the separate retry gate |
| `NON_BINDING_DESIGNED_RED` | no work generated, ever |
| `UNKNOWN_UNATTRIBUTABLE` | advisory only; no blame, rerun, or work generated |

The classification inputs already exist and are load-bearing: `ship_loop_guard.py`
already distinguishes base-inherited from PR-owned reds (same check red on ≥2 independent
sibling heads, or a green run on a main descendant, with the proof required to *postdate*
the failing check). This wave should **consume** that logic, not fork a second copy.

Gate: on a labelled corpus of historical reds, ≥95% correct classification, **zero**
`BASE_INHERITED` misrouted to a feature author, and zero work items filed against a
designed-red. Hazards: a pack is ONE check, so two partial heals deadlock — the router
must route a pack's whole failure set to one owner; and "not red" is not "green" — a
pending check is not a pass.

The first W7 carrier is **advisory classification only** and writes no work item, message,
rerun, dispatch, scheduler state, or producer-agent assignment. An infra-transient retry
may be added only through the existing merge controller after it proves the exact same SHA
and tested merge tree, owns one bounded retry under the existing concurrency contract, and
cannot race a baseline refresh. No new queue, lease, registry, retry, or lifecycle plane is
authorized by this masterplan.

The implementation seam is one pure `scripts/ci_failure_classification.py` module
extracted under tests from the existing `ship_loop_guard.py` rules. It accepts explicit
immutable check/provenance/timing inputs and returns only the classification plus evidence;
it has no GitHub or filesystem mutation. Both the hook and the advisory reporter import
that module. A labelled fixture corpus must prove parity with the pre-extraction hook and
with every overlapping merge-controller classification before either consumer changes.

### W8 — Definition of done is "delivered", not "PR created"
Sessions (Claude / Codex / Cursor) run the fast local preflight **before** pushing, and
stay responsible through concluded binding CI, merge, and relevant live verification. The
only non-merge terminal states are those already allowed by repository law: a fully
ratified `HOLD-FOR-SOL` or the separately governed actual-external-blocker protocol with
exact evidence. This masterplan does not create a generic `BLOCKED` handoff escape. The
hook layer (`ship_loop_guard.py`) already encodes most of the accountability loop.

Gate: local preflight is one documented command, runs in the same budget as W2, and its
verdict matches CI's for the checks it covers — including **on a sparse worktree**, where
a naive local run is measurably misleading (2026-08-13: 1,281 failures + 419 errors purely
as sparseness artifacts).

### W9 — Runner experiments, *last*
Only after W2–W6. Benchmark larger hosted runners (8-core/32 GB and up) on genuinely
CPU-heavy packs. Rationale for the ordering: paying for 16 cores while spending three
minutes cloning 19 GB and synchronously replaying base failures treats the symptom, not
the architecture.

Keep the self-hosted fleet a **measured option, not an unbounded default**: benchmark the
same heavy pack hosted vs `ci-linux` with the persistent repo cache — the existing canary
is already instrumented for checkout/test/resource comparison. The original one-or-two
slot proposal is superseded by the accepted 2026-08-26 topology: three PC CI slots are
proven, and exactly one fourth slot is the next capacity experiment. All four must share
one enforced aggregate CI resource slice and preserve the independent render reservation.
Do not infer six or eight slots from nominal core count; each increase requires natural
traffic, cgroup pressure, teardown, cache, and concurrent-render receipts from the prior
level. The render budget remains law (~67 min, 4-core-bound), and the nightly/render lanes
retain priority over CI throughput.

The stationary M4 Pro MacBook is a separate native-validation experiment, not a fifth
Linux/x86 pack slot. Its role is one narrow `macos-arm-validation` capability, sealed so
that the same contract can be reconstructed on a replacement M4 mini. It does not acquire
`ci-linux`, `macstudio`, render, merge-control, or generic overflow authority.

---

## §3 Sequencing and ownership

W2 → residual planner measurement → W4 → W5 → W6 → advisory W7 → W8, then W9. The landed
W3 capability is not rerun; any measured residual planner optimization and W4 ship
separately so a planner regression is bisectable.

Run as a **chain of short sessions** over this document, one wave per session, per the
context-economy law — not one long session. Each session: read this file, read the
latest `research/CI_LATENCY_*_HANDOFF_<date>.md` if present, build one wave, ship it to
merged + verified, write the handoff, stop.

## §4 Reuse inventory (do not rebuild)

`ci_semantic_proof.py` (proof authority) · `ci_authority.py` / `ci_authority_paths.py` ·
`ci_scope_dependencies.py` (scope derivation) · `run_ci_pack.py` (partitioning,
`--validate-only`) · `audit_unrun_tests.py` · `check_workflow_yaml.py` ·
`check_ci_trigger_closure.py` · `capture_ci_canary_receipt.py` +
`compare_ci_canary_receipts.py` (hosted vs self-hosted) · `monitor_ci_host_resources.py` ·
`ship_loop_guard.py` (red attribution) · `merge-on-green.yml` (base-inherited-red refresh) ·
`worktree_sparse.py` + `config/sparse_worktree.json`.

## §5 Risks

- **Speed bought with coverage.** Every narrowing must print what it dropped (§0 gate 3).
- **A second scoping authority.** Preflight and the planner must not both decide what runs.
- **Cached proof drifting into assumed proof.** §0 gate 1 is the line; mutation tests hold it.
- **Sparse thinning corrupting artifacts.** W4's central hazard; see the 2026-08-13 receipts.
- **Router blaming authors for main's breakage.** A main break newer than main's last proof
  is *unattributable* for a window — the router must compare merge time to proof time and
  say "unknown" rather than guess. Fail-closed: unattributable is not PR_OWNED.
- **Livelock on the main-proof lever.** Main-ref `ci.yml` dispatches share one
  concurrency group with `cancel-in-progress`, so re-dispatching kills the in-flight proof
  every pinned session is waiting on. Any automation that dispatches a baseline must
  preflight for a live one first.
