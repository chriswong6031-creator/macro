# CI Scope and Latency Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan one carrier at a time,
> with a fresh implementer context and an adversarial reviewer before each merge.

**Goal:** Reduce ordinary pull-request verdict latency without weakening coverage by
measuring actual logical-job costs, separating false ownership coupling, eliminating
repeated dependency setup, and rebalancing packs from evidence.

**Architecture:** Keep the current hosted planner, twelve stable semantic check names,
`legacy-jobs.yml`, `run_ci_pack.py`, semantic proof fragments, and `ci-gate` as the single
authority path. Extend the existing receipt plane with non-authoritative timing facts;
never make wall-clock timing part of a semantic hash. Narrow ownership only through the
existing closure auditor. Cache dependencies or results only when exact immutable inputs
and hermeticity are proved; otherwise execute live.

**Spec:** `research/CI_LATENCY_AND_AUTONOMOUS_HEALING_MASTERPLAN.md`, especially the
2026-08-26 amendment and acceptance gates.

## Preconditions and carrier law

- Do not edit CI authority or manifest files until P3B-B PR #6505 has concluded and P4
  has accepted three natural ordinary PRs on its exact merged head.
- Re-pin `origin/main`, enumerate all open PRs touching the task's files, and run the
  exact current manifest validation before each carrier. One carrier owns one wave.
- Preserve the twelve check names until every merge-control consumer is migrated.
- Timing and cache metadata are evidence, not a second scheduler, planner, gate, queue,
  registry, database, or retry plane.
- A missing timing observation never changes a verdict. Missing, corrupt, stale, or
  non-hermetic cache evidence executes the task live.
- Any ownership narrowing must print the exact logical jobs it drops and must pass the
  existing representative-diff and closure audits.

---

### Wave L1: Capture an exact natural-traffic baseline

**Likely files after the post-P4 re-pin:**
- Modify: `scripts/run_ci_pack.py`
- Modify: the post-#6505 executor/workflow upload step named by the fresh tree
- Modify: the existing receipt reducer only if it consumes the new sidecar
- Modify: `tests/test_ci_pack.py`
- Modify: `tests/test_ci_canary_tools.py`

- [ ] Define one non-authoritative `ci.execution_timing.v1` JSONL sidecar keyed by
  repository, run/attempt, exact head/base/tested-merge SHA, semantic plan hash, pack
  identity, logical-job name, runner profile, and phase. Its only measurements are bounded
  monotonic start/end/duration values and an explicit observed/missing status.
- [ ] Write tests proving the sidecar is not accepted as a semantic plan, fragment, or
  aggregate; its bytes never enter their hashes; and no timing value is read by `ci-gate`.
- [ ] Prove an absent or malformed sidecar preserves the existing semantic verdict
  byte-for-byte and is reported only as missing/degraded telemetry.
- [ ] Upload the sidecar beside the existing artifacts from the same execution. Do not add
  keys to the closed `ci.pack_plan.v2`, `ci.semantic_fragment.v1`, or
  `ci.semantic_evidence.v1` schemas, and do not create a workflow, service, database,
  status, or authority path.
- [ ] Record selected jobs, dropped jobs, checkout/setup/install/test durations, queue
  time, pack completion time, and runner profile for a **post-P4** natural corpus. P4's
  existing route/resource receipts remain its acceptance evidence; L1 telemetry is not
  claimed retroactively.
- [ ] Publish a baseline with named run IDs and p50/p95; do not claim improvement in this
  wave.

Minimum proof:

```bash
python3.12 -m pytest -q tests/test_ci_pack.py tests/test_ci_canary_tools.py
python3.12 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml \
  --gate code --pack-count 12 --validate-only
```

Gate: the semantic hashes and conclusions match the pre-wave implementation for the same
fixtures; timing is present on live receipts and cannot turn a red into green.

---

### Wave L2: Split false ownership coupling

**Files selected only after the L1 corpus and a fresh collision census:**
- Modify: `.github/ci/legacy-jobs.yml`
- Modify: `tests/test_ci_pack.py`
- Modify: task-specific tests identified by the closure report

Start with the measured broad-tail owner, not a guessed slow job. The current exact-main
audit identifies `self-mod-fence` as a candidate because it serially owns the actual
self-modification fence, ship-loop/worktree suites, self-modification tests, and Agent OS
validation/tests. That is a hypothesis to prove from L1, not authority to split blindly.

Measure the legacy-manifest `self-mod-fence` separately from the independent always-on
`.github/workflows/fences.yml` `fence-pack`, which publishes required historical contexts.
L2 may split false coupling inside the manifest owner only. Any attempt to optimize the
always-on fence is a separate authority carrier that must preserve its sparse checkout,
published contexts, runner policy, branch/ruleset consumers, and current P3B/P4 law.

- [ ] Add representative changed-path tests for each proposed child owner before editing
  the manifest. Each fixture must prove both positive selection and negative isolation.
- [ ] Preserve the true fence as always-on or broadly scoped wherever its trust law
  requires. Never hide Agent OS or authority coverage merely to improve a ratio.
- [ ] Move only independently owned suites into separate logical jobs with explicit paths.
- [ ] Use `scope: exclusive` only after the existing as-if-not-exclusive closure report is
  empty or every additional inferred owner is explicitly reconciled.
- [ ] Prove the representative-diff ratio, unrun-test audit, and all authority inventories
  still pass.

`cycle-ontology-js` is a second candidate because the observed evidence commit
`854c2764e8756c8ebc6640796bf98e724e2479b7` contains that logical job in
`.github/ci/legacy-jobs.yml` without an explicit path list. Re-establish that fact on the
future carrier head, then discover its exact producer, generated artifact, direct imports,
and tests through the closure audit; do not copy a guessed file list into the manifest.

Gate: selected ordinary diffs lose only demonstrably unrelated jobs, every dropped job is
named in planner output, and the full manifest has no unowned validation.

---

### Wave L3: Add immutable dependency environments

**Likely files after the L2 merge:**
- Modify: `scripts/run_ci_pack.py`
- Modify: the existing dependency-environment helpers selected by current code
- Modify: `tests/test_ci_pack.py`
- Modify: runner cache/update helpers only if required by the chosen execution profile

- [ ] Define one canonical dependency identity from lockfiles, install command, Python/Node
  versions, OS/architecture, runner contract, and relevant environment inputs.
- [ ] Write mutation tests for every identity component and for incomplete/corrupt cache
  state.
- [ ] Build cache contents in a trusted updater; candidate jobs receive read-only access
  and cannot mutate objects, refs, metadata, or maintenance state.
- [ ] Materialize a fresh per-job writable environment from the immutable cache.
- [ ] Refuse or execute live on identity mismatch; never fall back to an unpinned direct
  install while claiming a cache hit.

Gate: selected packs spend less than 60 seconds in checkout plus dependency preparation at
p95 on the measured corpus, with exact cache-hit identity and read-only receipts.

---

### Wave L4: Add hermetic result reuse, narrowly

- [ ] Use the existing GitHub Actions artifact plane, not a new database or cache service.
  Only a successful, main-ref, main-owned trusted-proof workflow may write a reusable
  fragment artifact. Resolve it by exact repository, workflow identity, run ID/attempt,
  `refs/heads/main`, base SHA, execution digest, proof ID, and successful conclusion.
- [ ] Retain reusable artifacts for seven days. Expired, evicted, missing, ambiguous, or
  API-unavailable evidence executes live; no candidate-maintained cache is authoritative.
- [ ] Inventory logical jobs whose outputs depend only on the exact tree, declared inputs,
  dependency identity, toolchain, and execution profile.
- [ ] Start with one deterministic, side-effect-free job. Write tests that mutate every key
  dimension and prove the old result is rejected.
- [ ] Store the existing semantic fragment plus exact key and provenance; do not store a
  naked boolean pass.
- [ ] Give candidate execution read-only consumption through the existing trusted broker/
  resolver. A negative test uploads a same-named candidate artifact and proves it cannot
  replace or satisfy the allowlisted main-proof fragment.
- [ ] Make absence, expiry, corruption, nondeterminism, or an undeclared input execute the
  job live.
- [ ] Compare replayed and live output on a bounded natural corpus before enabling reuse.

Gate: zero same-SHA green-to-red mismatches, zero false hits on mutation fixtures, and no
change to the aggregate proof law.

---

### Wave L5: Rebalance from empirical cost

- [ ] Generate a reviewed observed-cost table from L1-L4 natural runs, separating queue,
  setup, and useful execution time.
- [ ] Update the existing observed-weight source; pack index remains ephemeral and is never
  treated as job identity.
- [ ] Simulate the real selected-job corpus at 3 and 4 PC slots and on hosted runners.
- [ ] Change the partition count only if measured p95 and queueing improve without check
  name or consumer breakage. Prefer correcting weights over multiplying packs.
- [ ] Re-run every consumer/inventory/semantic-plan test and a natural-traffic acceptance.

Gate: ordinary green PR final-push-to-gate p95 below 10 minutes; heavy PR p95 below
15–20 minutes; no coverage, authority, render, or same-SHA determinism regression.

The acceptance population is frozen before measurement: at least 20 natural green
ordinary PR final heads and five natural heavy final heads over a bounded 14-day window.
“Ordinary” selects one to four packs without a global invalidator; “heavy” selects eight or
more packs or the declared full-suite path. Final-push-to-gate includes GitHub queue wait.
Cancelled/superseded runs are excluded from the latency percentile but reported as a
separate churn rate. Permission/startup/infra failures are separately counted and block
acceptance while unresolved. A post-merge or main-proof run cannot substitute for a PR
final-head receipt.

## Delivery and rollback

Each wave is a separate fresh branch and PR: red tests, smallest implementation, focused
proof, adversarial review, re-pin, concluded binding CI, squash merge, and current-main
verification. A regression reverts only that wave. The prior planner, manifest, live
execution, and semantic proof remain usable at every boundary; no all-at-once migration is
permitted.
