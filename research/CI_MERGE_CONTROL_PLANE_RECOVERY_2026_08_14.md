# CI + Merge Control Plane Recovery — incident model, verdicts, and repair architecture

Incident commander session, 2026-08-14 (UTC). Mission: break the recurring CI/merge
traffic jam structurally — not one more local patch. This document is the durable
incident record: every claim below carries a live run ID, PR number, or a locally
reproducible measurement.

## §0 Definition of done (from the operator handoff)

PASS requires live GitHub evidence: measured incident model (this doc) · ci-plan
p95 < 60s service time · unwired-test fixture fails in preflight within minutes ·
narrow PRs stop fanning out to ~156/188 · worker count scales with selected work ·
obsolete commits cancelled without killing current-head evidence · recovery cannot
self-DDoS Enterprise concurrency · armed PRs progress unattended · green→merge
near-immediate · fast-moving main stops re-proving unrelated PRs · no lost merge
wakes · main stays green · queue drains by automation · red/pending/stale/conflict
safety invariants preserved · native Merge Queue adopted or rejected on fresh
evidence · succinct architecture doc. Anything less = PARTIAL.

## §1 Measured incident model (live, 2026-08-13T18:00Z → 2026-08-14T06:00Z)

### The anchor failure: run 31763116872 (PR #5506, 8 files changed)

| phase | measured |
|---|---|
| ci-plan queue delay | **17m08s** (created 02:14:23Z → started 02:31:31Z) |
| ci-plan execution | 7m52s (fetch-depth:0 checkout dominates) |
| pack queue delay | 5m58s–**19m09s** across the 12 packs |
| pack execution | 14m58s–31m02s |
| failing job surfaced | ci-pack-1 fails at 03:21:36Z — **67m13s after trigger** |
| root failure | `tests/test_prophet_lifecycle_state.py` added but wired into no workflow — a structural fact knowable in seconds |
| ci-gate | 4s (never the bottleneck; 9/9 runs inspected: 0–1s handoff) |

### Fleet-level (representative windows, true API totals)

- PR validation wall clock, executed ci.yml runs (n=24, 2h window 03:45–05:45Z):
  **p50 = 64.5 min, p95 = 78.4 min**, max 79m32s (run 31767882214). Failures cost
  MORE than successes at every percentile (median 70.8m vs 64.5m) — reds surface
  at the end.
- Pack runner-queue delay swings **62s → 37m43s** across structurally identical
  12-pack matrices (runs 31769511335 vs 31768358077) — Enterprise hosted
  concurrency saturation, not billing.
- **merge-on-green.yml ran 394 times in the 8h jam window** (42% of ALL 936
  fleet-wide Actions runs in the window), 64% of its last 100 runs `cancelled`
  in a median 12s (concurrency-group churn).
- Main: **323 commits/24h** (~4.5-min mean cadence, bursty: one 23-commit burst in
  ~2 min at 22:44Z), 41.5% `[skip ci]`; top lanes hot-tape/earnings-wire/data/
  research_vault/press-wire = 57.6% of all commits.
- Main proof (full-suite workflow_dispatch, ci.yml has no push trigger): last 4
  runtimes **31m51s → 38m16s → 65m53s → 73m28s** (newest 31767934869, concluded
  05:02:30Z); 3 of last 10 main baselines failed. Proof was 32 commits behind
  main at census.
- Backlog: 35 open PRs, **32 armed** `merge-on-green`, median age 23h, max 43h.
  **7/8 sampled armed heads carry a completed RED** (ci-gate + 1–3 packs) that is
  clean on main → inherited/flaky, not PR-caused. Only 1 of 7 carried a
  `merge-blocked` marker.
- Sweep run 31768886250 (04:08Z): evaluated 47 PRs → **merged 0** ("2 blocked,
  2 excluded, 43 pending, 0 main commits classified, 0/8 refresh slots used").
  Then run at 05:44Z merged **7 PRs inside a 42-second window** — merges happen
  only in batch windows right after a fresh main baseline concludes.
- Refresh treadmill: every sampled armed PR's history ends in bot
  `Merge branch 'main'` commits; #5516's refresh gaps accelerate 5h26m → 3h34m →
  1h17m. Each refresh = a fresh 12-pack run (~4.4 runner-hours).

### Fanout (measured locally against the live manifest, `run_ci_pack.py --plan-only`)

| one-file diff | selected jobs | packs |
|---|---|---|
| `research/DESIGN_NOTES.md` (markdown!) | **118/188** | 12/12 |
| `engine/neuralweb/brain_gateway.py` | 121/188 | 12/12 |
| `templates/index.html` | 129/188 | 12/12 |
| `scripts/merge_on_green.py` | 127/188 | 12/12 |
| `config.yml` | 4/188 | 4/12 |
| new test file | 3/188 | 3/12 |
| any `.github/workflows/*` file | 188/188 (global invalidator) | 12/12 |

Cause: ambiguity-fallback smearing — an opaque subprocess/traversal anywhere in a
suite's transitive import closure claims whole scan roots (`research/**`,
`templates/**`, `engine/**`…), so ~116–130 jobs "own" every ordinary file. Prior
census (#5434, memory `ci-scope-smears-module-literals-onto-every-opaque-edge`):
of 144 selected, 19 from honest closure, **124 from fallbacks**; per-call
precision is NOT the lever, class-level constraints are.
Pack imbalance: weights `[1036, 556, 555, …]` — `engine-render-guards` (1036s)
alone pins pack 0; `workflow-yaml` (438s) buries ALL structural preflight checks
(`check_workflow_yaml`, `audit_unrun_tests` — the exact check that would have
caught #5506's unwired suite — `check_ci_trigger_closure`, plan/pack/handoff
contracts) in the middle of a pack.

### The self-amplifying loop, confirmed end to end

32 armed PRs × 12 packs ≈ 480 hosted jobs vs the ~500-job Enterprise ceiling →
queue delays (measured to 37m) → PR proofs take ~65 min while main moves every
~4.5 min → proofs stale/reds conclude after the last baseline → freshness law
("a proof that predates the failure does not excuse it", correct in isolation)
pins them until the NEXT 65–73-min baseline → sweeper refreshes armed PRs
(update-branch) → each refresh re-runs ~12 packs → more load → longer queues →
more staleness. The recovery lever (baseline dispatch) itself competes for the
same saturated pool. Meanwhile 394 sweeper wakes/8h churn 64% cancelled.

## §2 Root causes

1. **RC-fanout** — fallback smearing turns one-file edits into 118–129/188 jobs,
   12 packs, ~4.4 runner-hours per proof.
2. **RC-amplification** — staleness → update-branch → full re-proof, per armed PR,
   on a main that moves 323×/day; bounded only recently (#5580) and still
   re-proving on data ticks that cannot affect the PR.
3. **RC-freshness-deadlock** — red-excuse requires a main proof NEWER than the
   red, main proof costs 65–73 min, so drains happen in rare batch windows;
   30% of baselines fail → windows sometimes never open.
4. **RC-planner-cost** — ci-plan fetch-depth:0 (7–8 min exec) + every pack
   re-running 106.5s scope inference ×12; run-level overhead ~4–5 min/pack.
5. **RC-heavies** — 1036s + 438s indivisible jobs set pack critical paths;
   structural failures surface at minute ~40–67 instead of minute 2.
6. **RC-wake-churn** — sweeper woken by every workflow completion (394/8h);
   coalescing groups cancel 64%; mark-writes unverifiable (5 red armed PRs
   carried no marker at census).
7. **RC-no-classification** — nobody (human or machine) can tell PR-caused vs
   inherited vs flaky vs infra without reading pack logs.

## §3 Native GitHub Merge Queue — verdict with fresh receipts (Phase 7)

The July ruling's premises are STALE: repo now lives in org
`mastermindx-market-intelligence` (Enterprise plan, receipt: `gh api orgs/…`
plan_name=enterprise) and rulesets are available (repo had zero).

Live experiment (2026-08-14T05:52–05:59Z, scratch branch `mq-eval-base`,
ruleset id 20833101, probe PR #5581):

1. **Available**: ruleset with `merge_queue` + `required_status_checks` rules
   ACCEPTED and enforced; `gh pr merge --squash` refused ("merge strategy … set
   by the merge queue"); enqueue via GraphQL worked; merge group ref
   `gh-readonly-queue/mq-eval-base/pr-5581-dbfa67d…` created with merge commit
   `00951d82`.
2. **Fast**: probe status green on group head at 05:58:19Z → PR MERGED at
   05:58:50Z (**31s green→merge**).
3. **Fatal incompatibility 1 — base-push invalidation**: one direct push to the
   target branch (commit `9065b39c`, message carried `[skip ci]`) DESTROYED the
   in-flight merge group and rebuilt it (`341d7706`, state reset to
   AWAITING_CHECKS, ref renamed `…pr-5581-9065b39c…`). Main receives 323 direct
   producer pushes/24h; any queue validation longer than the ~4.5-min bursty gap
   restarts indefinitely; `[skip ci]` does not exempt. The queue has no concept
   of "this base move cannot affect this PR" — the exact discrimination Phase 9
   requires.
4. **Fatal incompatibility 2 — producer identity**: adding the `github-actions`
   integration (id 15368) as a ruleset bypass actor is REJECTED live:
   `422 "Actor GitHub Actions integration must be part of the ruleset source or
   owner organization"`. ~35 producer workflows push to main with
   `GITHUB_TOKEN`; a merge_queue/required-checks ruleset on main would refuse
   those pushes outright unless every lane migrates to a dedicated App/PAT — and
   after migrating, incompatibility 1 still applies.

**Verdict: REJECT native Merge Queue for `main` under the current producer
architecture — with adoption preconditions recorded**: it becomes the preferred
design iff producers stop pushing directly to main (e.g. data moves to a
non-main branch/store), and queue CI is scoped fast. That is the separate
producer-architecture project, not this incident. Design ideas ADOPTED from MQ
into the custom controller: serialize merges not validation; head-SHA-keyed
idempotent operations; durable per-PR wake.

## §4 Repair architecture

**PR-1 `ci.yml` v2 — plan once, consume everywhere, preflight first, scoped fanout**
- ci-plan: depth-1 blob:none checkout (kills fetch-depth:0); PR diff from the
  **PR files API** (fail-safe: widen to full suite on overflow/error); scope
  inference cached via `actions/cache` keyed on scan-root tree OIDs + selector
  script OIDs (hit ⇒ ~0s, miss ⇒ one 106s inference per base, shared by every PR
  on that base); emits authoritative plan JSON as an **artifact** (jobs per pack,
  explain map, plan_sha).
- **preflight steps inside ci-plan** (target < 2–3 min total): workflow YAML
  parse, `audit_unrun_tests` (unwired suites), trigger closure, conflict
  markers, plan/manifest validity — structural reds surface in minutes and
  fanout never launches (`ci-pack` needs ci-plan success).
- ci-pack: downloads the plan artifact, verifies `plan_sha`, executes its job
  list — **no re-inference** (retires the ×12 106s recomputation; planner
  fallback path keeps the old recompute as the escape hatch).
- dynamic pack count: `K = clamp(ceil(total_weight / 600s), 1, 12)` — a 3-job PR
  gets 1 pack, not 12; full suite still 12.
- Scope honesty: fallback-provenance patterns stop matching narrative kinds
  (`**/*.md` unless the job's commands or closure name them); declared
  `scope: exclusive` manifest tier (declared paths REPLACE inference, coverage-
  audited fatal); regression fixtures pin selected-job counts for the seven
  measured shapes above.
- Heavies: split `engine-render-guards` into balanced shards; move the
  structural checks out of `workflow-yaml` into preflight (job body keeps its
  pytest suites).
- ci-gate: unchanged adjudication + emits a one-line machine-readable
  classification (`CI_CLASS=pr-caused|infra|planner|…`, first failing legacy
  jobs named) into the run summary.

**PR-2 merge controller — wake diet + verified markers (CORRECTED SCOPE)**
Code reading during the build corrected the §4 draft: `stale_for` in
`scripts/merge_on_green.py` is ALREADY overlap-gated as of #5562 (2026-08-13):
skip-ci ticks and data/site bakes are excluded, unowned files do not stale
anyone, and staleness requires a main-moved file to intersect the PR's OWN
surface. Phase 9's classifier therefore already exists at pattern granularity;
what made it a treadmill was the COST of each re-proof (PR-1's job) and the
freshness deadlock (PR-1 shrinks baselines and re-proof latency). PR-2 keeps
the controller small instead of growing it:
- Wake diet: `skipped`-conclusion workflow_run completions (measured 20/44 of
  ci.yml runs — closed-PR zero-runs) no longer schedule sweeper runs at all.
- Verified marker writes: `mark_only_pass` now read-after-writes the label so
  "already labeled" and "both writes silently failed" — opposite outcomes,
  previously logged identically — are distinguished, and a verifiably absent
  marker annotates at error level (the #5291 invisible-red class).
- Everything else stands untouched: affirmative ci-gate requirement (#4779),
  never merge red/pending/conflicting/empty, concluded-checks-only, spurious
  Workers X exclusion, capacity caps (#5580), lease machinery.
- The plan-document artifact (PR-1) is published for future per-job-granular
  surface refinement but deliberately NOT consumed yet — simplicity outranks.

**Local proof measurements (pre-push)**
- Unwired-test probe: `audit_unrun_tests` exits 1 in **10s** naming the file.
- Preflight stack: workflow-yaml parse 0.7s + unrun audit 10s + trigger
  closure 20s + conflict scan ~1s ≈ **32s** on a dev Mac.
- Scope inference: 122s cold, **~1s on scope-cache hit**; plan service time on
  a warm cache ≈ 1s.
- Shapes (jobs / packs): research md 118/12 → **3/1** · docs md → 2/1 · new
  test 3/1 · config.yml 4/4→4/1-ish · engine module 121/12 → 121/**11** ·
  template 129/12 → 129/12 · full suite/invalidator unchanged 188/12 (the
  sweeper's ci-pack-0..11 main-proof anchor preserved). Code-file fanout
  awaits the curated `scope: exclusive` tier for the heavy tail.

## §5 Live evidence (PR #5585, run 31777873919, 2026-08-14)

The repair PR edits `.github/workflows/**` and the manifest — a GLOBAL
INVALIDATOR — so its own run is a full-suite (188-job, 12-pack) proof of the
new pipeline. Step-level receipts:

| phase | incident run 31763116872 | repair run 31777873919 |
|---|---|---|
| ci-plan queue delay | 17m08s | **17s** |
| ci-plan checkout | (fetch-depth:0, inside 7m52s exec) | 5m32s (depth-1, 64k files) |
| diff resolution | git diff vs base (needed full history) | **1s** (PR files API) |
| planner service (diff→plan→artifact) | — | **7s** (06:59:10→06:59:17) |
| preflight, 4 structural guards | did not exist | **42s** (yaml 1s, unrun-audit 13s, trigger-closure 28s, conflict 0s) |
| ci-plan total | 25m00s (queue+exec) | **6m42s** |
| pack queue delay | 5m58s – 19m09s | **2–3s** (all 12 launched 07:00:04–05) |
| pack plan materialization | ~106s re-inference ×12 | **instant** (document consumed) |
| first green pack | — | ci-pack-2 16m23s (5m23s checkout + 10m37s tests) |

Honest scoping of these numbers:
* **Planner service time is 7s**, far inside the <60s p95 target. The remaining
  ci-plan cost is CHECKOUT (5m32s) — file materialization of ~64k files, not
  history. That is the next bottleneck and is NOT irreducible; a sparse
  checkout is blocked today because `audit_unrun_tests` discovers suites across
  the whole tree. Recorded as a known bottleneck, not as a win.
* This run did NOT exercise cold scope inference: a global invalidator skips
  inference by design ("scope inference not needed"), so the 1s plan step here
  is the invalidator path. The cache path is measured locally (122s cold → ~1s
  warm) and will be measured live on the first narrow PR (probe A).
* Three packs (0/3/4) died in 5–13s on a GitHub-side transient —
  `actions/checkout` archive 404 from codeload — the exact `infra` class the new
  taxonomy names. Nine packs passed the consume gate and executed, which is
  itself the proof that plan consumption works: a parity failure refuses in
  seconds, and nine did not.

## §6 Live probes (post-merge)

- Probe A — narrow PR (one research `.md`): expect ci-plan ~1–2 min, 3 jobs /
  1 pack, warm-cache plan, unattended sweeper merge; record green→merge latency.
- Probe B — deliberately broken structural fixture (new unwired pytest file):
  expect `ci-plan` red at the unrun-audit preflight in ~2–3 min with
  `CI_CLASS=structural-preflight` and ZERO packs launched.

## §7 Experiment artifact cleanup

`mq-eval-base` branch, ruleset 20833101, merged probe PR #5581, branch
`mq-eval-pr1` (auto-deleted) — remove after the closure report cites them.
