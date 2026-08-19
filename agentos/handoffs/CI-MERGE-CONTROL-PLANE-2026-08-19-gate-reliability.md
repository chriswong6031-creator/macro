---
workstream: WS:CI-MERGE-CONTROL-PLANE
session: claude/ci-gate-reliability-diagnosis
model: opus
ended_because: context_budget
prs: [5930, 5922, 5937]
discoveries:
  - DSC:MERGE-GATE-IS-GATED-ON-MOVING-DATA
  - DSC:FLOATING-PYTHON-PIN-BREAKS-A-SEALED-RUNTIME
mission: >
  Operator escalation 2026-08-19: 24 open pull requests, a backlog running about
  two weeks, and session compute roughly doubled because sessions repair CI
  instead of building. Find the root cause and either fix it end to end or hand
  it off with the diagnosis done.
state_before: >
  Individual reds were being healed one at a time by whichever session hit them.
  Three separate causes had been fixed in the preceding 24h and the backlog did
  not move, which is the signal that the healing target was wrong.
changed:
  - path: scripts/ci_gate_reliability_report.py
    what: >
      New. Measures main's own ci.yml green rate and statically classifies every
      merge-gate legacy job by whether its named suites read the committed data
      tree. Coupling section is offline and sparse-safe; the green-rate section
      degrades to a stated skip rather than reporting an unmeasured number.
  - path: tests/test_ci_gate_reliability_report.py
    what: >
      14 cases. Pins that a missing suite classifies as unknown rather than
      code-only (a sparse worktree must not flatter the count), that in-flight
      runs are excluded rather than counted red, that only `success` is green,
      and that every gh failure path is a stated skip.
  - path: research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md
    what: >
      The diagnosis, the arithmetic, the staged remediation W1-W4 with acceptance
      gates as section 0, and the authority-changed trap the program must plan
      around.
  - path: agentos/discoveries/DSC-MERGE-GATE-IS-GATED-ON-MOVING-DATA.md
    what: the root cause as a citable record with its falsifier.
verified:
  - claim: main's own ci.yml is green 44% of the time.
    command: python3 scripts/ci_gate_reliability_report.py
    result: >
      "main green rate: 44/100 = 44.0% [2026-08-09T15:32:57Z ->
      2026-08-19T05:46:08Z]; conclusions: {'failure': 45, 'success': 44,
      'cancelled': 11}". These are main's own runs with no pull-request diff.
  - claim: two thirds of the merge gate asserts against the committed data tree.
    command: python3 scripts/ci_gate_reliability_report.py --coupling
    result: >
      "merge-gate legacy jobs: 194; assert against the committed data tree: 130;
      code-only: 63; => 67% of classified merge-gate jobs are data-coupled".
  - claim: the failing set rotates faster than a heal cycle, so per-red healing cannot converge.
    command: gh run view 32217049650; gh run view 32220671521
    result: >
      main red on capital-structure-intelligence at 04:47Z; healed and merged
      05:15Z (#5930); red on market-memory-contract + unrun-prophet-learning-loop
      + signal-contract at 05:46Z. Three different jobs, one hour, no PR involved.
  - claim: the reds are data and environment conditions, not code defects.
    command: python3 -m pytest research/prophet_us_audit/test_price_ladder.py; python3 -m pytest tests/test_prophet_postmortem.py
    result: >
      "CEG disagrees across bases at 2026-06-22; assert 275.5299987792969 ==
      275.1070861816406 ± 0.001" (0.153%, a dividend factor) and "'yahoo' ==
      'baskets_ohlcv'" (data/baskets/ohlcv/ASTS.parquet ends 2026-08-17 while
      data/yahoo/ASTS.parquet reaches 2026-08-18).
  - claim: the new tests pass and the report renders without gh.
    command: python3 -m pytest tests/test_ci_gate_reliability_report.py -q
    result: 14 passed.
unverified:
  - claim: moving data-coupled jobs off the merge gate raises the green rate above 90%.
    what_would_verify: >
      After W2 lands, `python3 scripts/ci_gate_reliability_report.py` over a
      trailing 100 runs measured at least 72h later, plus two consecutive
      ordinary pull requests merging with no intervening main-red-repair.
  - claim: the static classifier's 130/194 split is the right split.
    what_would_verify: >
      Per-job review in W1. A job that reads data/ only to build a fixture, or
      that reads a pinned golden, is code-gated despite matching the heuristic.
      The script is a starting point for judgement, not the answer.
unresolved:
  - >
    W1-W4 in research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md are not
    started. That is the remediation; this session delivered only the diagnosis
    and three generator removals.
  - >
    #5916 — the semantic base replay cannot check out base SHAs in the blobless
    partial clone, so reds classify `unknown` rather than base-inherited. Does not
    raise the green rate but makes diagnosis instant for every session that hits one.
  - >
    #5935 — the four roots red on main at 07:00Z, fully characterised there.
    signal-contract is FIXED by #5937 (green on its head, blocked by the others).
    market-memory-contract is a TEST DEFECT and fixable: the fixture froze the
    ratio's numerator (n_members @ 2026-08-07 = 504) and left the denominator live
    (constituents.parquet = 503), so coverage reads 1.0020 and fails the <= 1.0
    bound; live-vs-live is 502/503 = 0.998 and passes. house-law-registry / VMRK
    was a DEAD COLLECTOR, already fixed by #5936 (merged 2026-08-19T07:10Z — the
    live Nasdaq listing `NA`, Nano Labs, parsed as NaN, so the completeness guard
    refused every day's snapshot after 2026-08-10); it clears on the next nightly
    that writes a snapshot. unrun-prophet-learning-loop is a stale baskets store for
    ASTS and should NOT be "fixed" — the test is correctly reporting it.
  - >
    unrun-intl-libraries aborts at interpreter shutdown after its check prints OK
    (exit 134, "terminate called without an active exception"), so a passing verdict
    reads as a contract failure.
authorization: >
  OPERATOR GRANT 2026-08-19 to the executing session, given after being shown the 44% / 130-of-194
  measurement: full latitude to fix this from the root, including `gh pr merge --admin --squash`
  on its own waves while main is red when the reds are provably inherited; merging without waiting
  for a full-green window; and free diagnosis of any other bug it finds in any lane. NOT granted,
  and not implied: rotating or reading secrets, force-cancelling the protected production lanes
  (daily / render / closing-bell / asia-close / engine-render / weekly / prophet-rescue /
  nightly-liveness), re-stamping data/** receipts from a pull request, or widening a
  tamper-detection allowlist to turn a check green. Full text and conditions in
  research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md section 4b.
next_actions:
  - >
    W1 — add an explicit `gate: code | data` field to every job in
    `.github/ci/legacy-jobs.yml`, using `python3 scripts/ci_gate_reliability_report.py`
    as the candidate split and per-job judgement as the authority. Log the count and
    the by-name list in the PR body.
  - >
    W2 — `run_ci_pack.py` packs only `gate: code` into the packs `ci-gate` requires;
    `gate: data` jobs move to a post-nightly `data-health.yml` whose failure opens or
    updates ONE issue naming them. Nothing is deleted.
  - >
    W3 — re-measure. Green rate above 90% over a trailing 100 runs, 72h after landing,
    plus two consecutive ordinary PRs merged with no main-red-repair between them.
  - >
    W4 — a test asserting no `gate: data` job is reachable from `ci-gate`.
  - >
    Land each wave in the SMALLEST possible PR. The operator grant above lifts the
    "wait for a fully green main" constraint — use `--admin --squash` when the reds
    are provably inherited, and record which logical jobs they are in the PR before
    doing it.
  - >
    Verify the symbol-directory collector actually recovered: after the next nightly,
    `data/symbol_directory/manifest.json` should show `last_snapshot_date` past
    2026-08-10 and `n_symbols` non-zero (it read 0 while frozen), and a new file
    should appear in `data/symbol_directory/snapshots/`. If it has not, #5936's fix
    did not take and the VMRK red will not clear on its own.
  - >
    Then drain the four pull requests this session left armed and blocked — #5937,
    #5938, #5922, #5737 — none of which has a red its own diff can reach.
do_not_redo:
  - >
    Do not audit merge-on-green. It ran every ~2 minutes throughout the backlog and
    behaved correctly at every step. "The sweeper is broken" was checked and is false.
  - >
    Do not heal individual reds hoping the backlog drains. Three were healed in the 24h
    before this session and the backlog did not move; the failing set rotates faster
    than a ~35 min heal cycle.
  - >
    Do not attack `p` — retries, wider tolerances, faster healing. P(all green) is
    (1-p)^N and N is 130. Only N moves the number.
  - >
    Do not re-pin a data-derived constant to today's value, and do not widen a
    tamper-detection allowlist to make CI pass. See DEC:PRICE-LADDER-CONTROL-DERIVES-ITS-ASSUMPTION
    and DSC:FLOATING-PYTHON-PIN-BREAKS-A-SEALED-RUNTIME for the two shapes.
  - >
    Do not delete a data receipt when moving it off the gate. Section 0 gate 3 of the
    masterplan: it must still run and still red something a human reads.
danger_areas:
  - >
    Every wave of this program is authority-changing (`scripts/**`, `.github/ci/**`,
    `.github/workflows/**`), which removes the base-inherited excuse entirely. Merging
    one while main is red buys a permanently unclearable stop gate — the merged head's
    checks are frozen and descendant healing is disabled by design.
  - >
    Editing `.github/ci/legacy-jobs.yml` is a global invalidator: the PR runs the full
    manifest and inherits every latent main red. At a 44% green rate that is close to a
    coin flip per attempt; expect to re-run and re-check main before each merge.
  - >
    Pack indices are not identifiers. `run_ci_pack.py` rebalances per PR — the same
    logical job appeared as ci-pack-1 on one head and ci-pack-4 on another the same
    morning. Reason in job names.
---

## The answer in one line

`main`, carrying no pull request at all, passes its own gate 44% of the time — because 130 of its 194 merge-gate jobs assert against a data tree the nightly rewrites 250 times a day.

## Why every previous attempt failed

Each one healed a red. The reds are not the disease; they are the symptom of gating merges on moving data. Three were healed in the 24 hours before this session — a stale circuit breaker, a CPython tool-cache rollout, a dividend re-basing a hardcoded control — and the backlog did not move, because the generator kept producing new ones. The failing set on main changed completely inside one hour on the morning this was measured.

## Why it is self-sustaining

The remedy touches `scripts/**` and `.github/**`, which sets `authority_changed=true` and removes the base-inherited excuse entirely. So the fix can only land during a fully-green window that the 44% rate makes rare. That is the mechanism that turned a CI problem into a two-week one.

## Records that land with the sibling pull requests

Two records cited by this work are not on main yet, so they are named here in prose rather
than in the frontmatter (validation is fail-closed on a dangling reference):
`DSC:PUSH-TRIGGERED-FRESHNESS-PROOF-IS-SELF-LOCKING` lands with #5922, and
`DEC:PRICE-LADDER-CONTROL-DERIVES-ITS-ASSUMPTION` with #5937. Add them to this handoff's
`discoveries:`/`decisions:` lists once both are merged.

## What a session picking this up should read first

1. `research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md` — §0 acceptance gates, §4 the plan.
2. `python3 scripts/ci_gate_reliability_report.py` — re-measure before trusting any number above; both are current as of 2026-08-19 but the green rate moves.
3. `DSC:MERGE-GATE-IS-GATED-ON-MOVING-DATA` — the falsifier, in case the shape has changed.

The diagnosis is done and reproducible. What remains is judgement work across 194 jobs, which is why it is handed off rather than rushed.
