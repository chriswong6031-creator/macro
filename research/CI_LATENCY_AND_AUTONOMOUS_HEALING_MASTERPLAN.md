# CI Latency + Autonomous Healing — masterplan

**Commissioned by the operator, 2026-08-17.** Status: chartered, no wave built.

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

### W3 — Collapse the planner (< 60 s)
Feed the planner PR changed-file metadata directly, or sparse-checkout only the CI
authority/config/scope files it needs. Profile the ~3m47 compute stage separately before
optimizing it — the checkout and the compute are different problems and may have
different fixes.

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

| Class | Routing |
|---|---|
| `PR_OWNED` | back to the producing agent on a trusted same-repo branch, with the exact failed logical job, command, annotations, and changed files |
| `BASE_INHERITED` | to a CI/main healer — **never** the feature author |
| `INFRA_TRANSIENT` | one automatic rerun |
| `NON_BINDING_DESIGNED_RED` | no work generated, ever |

The classification inputs already exist and are load-bearing: `ship_loop_guard.py`
already distinguishes base-inherited from PR-owned reds (same check red on ≥2 independent
sibling heads, or a green run on a main descendant, with the proof required to *postdate*
the failing check). This wave should **consume** that logic, not fork a second copy.

Gate: on a labelled corpus of historical reds, ≥95% correct classification, **zero**
`BASE_INHERITED` misrouted to a feature author, and zero work items filed against a
designed-red. Hazards: a pack is ONE check, so two partial heals deadlock — the router
must route a pack's whole failure set to one owner; and "not red" is not "green" — a
pending check is not a pass.

### W8 — Definition of done is "green", not "PR created"
Sessions (Claude / Codex / Cursor) run the fast local preflight **before** pushing, and
stay responsible for their branch until binding CI is green or they produce an explicit
`BLOCKED` handoff with evidence. This is the accountability loop the rest of the program
depends on; the hook layer (`ship_loop_guard.py`) already encodes most of it.

Gate: local preflight is one documented command, runs in the same budget as W2, and its
verdict matches CI's for the checks it covers — including **on a sparse worktree**, where
a naive local run is measurably misleading (2026-08-13: 1,281 failures + 419 errors purely
as sparseness artifacts).

### W9 — Runner experiments, *last*
Only after W2–W6. Benchmark larger hosted runners (8-core/32 GB and up) on genuinely
CPU-heavy packs. Rationale for the ordering: paying for 16 cores while spending three
minutes cloning 19 GB and synchronously replaying base failures treats the symptom, not
the architecture.

Keep the self-hosted fleet a **measured option, not the default**: benchmark the same
heavy pack hosted vs `ci-linux` with the persistent repo cache — the existing canary is
already instrumented for checkout/test/resource comparison. If self-hosted wins
decisively, reserve **one or two** CI slots; never consume all four render machines. The
render budget is law (~67 min, 4-core-bound), and the nightly/render lanes have priority
over CI throughput.

---

## §3 Sequencing and ownership

W2 → W3 → W4 → W5 → W6 → W7 → W8, then W9. W3/W4 are coupled (the planner emits what W4
consumes) but ship separately so a planner regression is bisectable.

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
