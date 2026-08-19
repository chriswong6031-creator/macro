---
workstream: WS:PROPHET-CONDITIONAL-FUSION
title: Prophet Conditional Fusion — PR-3C durable W3 prospective evidence ledger
date: 2026-08-17
session: claude/prophet-fusion-pr3c-ledger
model: local
ended_because: complete
prs: ["#5839"]
repo: mastermindx-market-intelligence/macro
main_at_start: 88e580eb2d65eafc235b6e5e34dada61dd6e193e
mission: >
  PR-3C only. Build the durable prospective W3 evidence ledger and its nightly
  accrual path from already-produced C1 + v2-shadow paired observations, the one
  shared grader, and the PR-3B outcome-blind structural receipt. No rank
  authority, no second scorer/grader, no comparative outcome read, no PR-3D.
state_before: >
  PR-3A merged as #5813 (8b5cd60f706e). PR-3B merged as #5829 (88e580eb2d65).
  W3_RACE_PREREG.md is frozen. Compact prophet_fusion.w3_structural.v1 receipt
  exists on the board fusion block. No data/us_prophet_rank/w3 store. No
  daily.yml W3 wiring. Last durable handoff:
  agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-17-PR3B.md.
changed:
  - path: engine/us_prophet_w3.py
    what: "Append-only W3 store: paired/family/coverage daily parts + status.json.
      Pairing filter, shared-grader join, structural-receipt serialization without
      LOFO recompute, keep-first/conflict-fail-closed, nightly lane gate."
  - path: scripts/accrue_us_prophet_w3.py
    what: "Nightly CLI for the W3 ledger. --nightly is the sole writer path."
  - path: tests/test_us_prophet_w3.py
    what: "Adversarial pairing, idempotency, conflict, Pages refusal, structural
      persistence, one-grader, zero-authority, and workflow-order pins."
  - path: tests/test_prophet_off_engine_lane.py
    what: "Register accrue_us_prophet_w3 in us_prophet_ledgers order, lane gate,
      and commit staging."
  - path: tests/test_us_prophet_grades.py
    what: "Allow the W3 ledger as a zero-authority importer of load_grades."
  - path: .github/workflows/daily.yml
    what: "Run W3 accrual after grade_us_prophet_candidates and before miss-audit;
      git add data/us_prophet_rank/w3."
  - path: config/dag.yml
    what: "Declare scripts.accrue_us_prophet_w3 in the us_prophet_ledgers lane."
  - path: .github/ci/legacy-jobs.yml
    what: "Name the new module/script/suite in unrun-picks-boards exclusive paths
      and pytest run."
  - path: agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md
    what: "w3 title notes PR-3B (#5829) and PR-3C scope; next_action is PR-3D after
      merge. w3 status stays todo until PR-3D."
  - path: agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-17-PR3C.md
    what: "This handoff."
verified:
  - claim: W3 ledger suite, off-engine lane suite, grades zero-authority/DAG pins, and exclusive-scope closure are green
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python3 -m pytest tests/test_us_prophet_w3.py tests/test_prophet_off_engine_lane.py tests/test_us_prophet_grades.py::TestZeroAuthorityFence tests/test_us_prophet_grades.py::TestDagWiring tests/test_ci_pack.py::test_curated_exclusive_scopes_cover_their_own_import_closure -q --tb=short"
    result: "71 passed"
  - claim: AgentOS store validates with 0 errors
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python3 scripts/agentos.py validate"
    result: "0 error(s); pre-existing phantom-owns-path warnings on other workstreams"
  - claim: DAG conformance matches the new us_prophet_ledgers step
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python3 scripts/check_dag_conformance.py"
    result: "DAG conformance OK — 26 lane(s) checked"
  - claim: no live rank consumer imports the W3 store
    command: "rg -n 'us_prophet_w3|us_prophet_rank/w3' engine/us_board_rank.py engine/us_prophet_fusion.py engine/prophet_bridge.py engine/us_candidate_lanes.py scripts/build_stock_library.py"
    result: "empty"
  - claim: no engine-side persistent W3 write was added to the ranker
    command: "rg -n 'us_prophet_rank/w3' engine/us_board_rank.py engine/us_prophet_fusion.py"
    result: "empty"
  - claim: C1 floors/weights/families.yml/SELECTION_ERA were not altered
    command: "git diff --stat origin/main HEAD -- research/prophet_fusion/families.yml engine/us_prophet_fusion.py engine/us_board_rank.py"
    result: "empty"
unverified:
  - claim: CI packs on this PR conclude green (or spurious-only Workers X)
    what_would_verify: "gh pr checks 5839 after packs conclude"
  - claim: first lawful durable post-#5769 paired stamp will accrue on a natural nightly
    what_would_verify: "first post-merge us_prophet_ledgers run that sees a committed v3+shadow candidates stamp; inspect row persistence/schema/idempotency only, not C1-vs-shadow outcomes"
unresolved:
  - "PR-3D is not built. Next session starts PR-3D only: live instrumentation acceptance + lawful status/display. Before the 20 matured-H10-session floor, display may show accrual/maturity/gap status only."
  - "No durable post-#5769 paired stamp has been inspected for outcomes. Do not backfill the Pages-only night. Honest-N remains 0 until that stamp exists and matures."
  - "#5742 availability/push contention remains external; keep the fail-closed checkpoint fence."
  - "C2 commissioning is data-gated, not a code project. Do not rebuild #5700. Do not relax fold/depth laws."
next_actions:
  - "After this PR merges, a FRESH session starts PR-3D only. Do not read forward C1-vs-shadow outcomes. Do not print who is winning before the 20 matured-H10-session floor."
  - "Do not implement C2 fit, C3/C4/C5, a second scorer/grader, or Pages backfill in that session."
do_not_redo:
  - "Do not re-litigate C1 / us_prophet_v3 adoption."
  - "Do not rebuild C2 or relax C2 fold/depth laws."
  - "Do not build another v2 scorer or another grader."
  - "Do not copy prophet_shadow_* into canonical prophet_* columns on v3."
  - "Do not backfill the Pages-only v3 session; do not count retries of one as_of as multiple nights; do not stamp shadow on us_prophet_v2_fallback."
  - "Do not weaken the fail-closed git/checkpoint behavior (#5742)."
  - "Do not bump SELECTION_ERA."
  - "Do not recompute LOFO in the W3 ledger writer; persist the PR-3B receipt."
  - "Do not emit ΔIC, HAC, p-values, CIs, or a leader from this ledger."
danger_areas:
  - "Observation identity is (stamp_date, ticker, horizon), never a GitHub run id. Identical retries must not increment honest-N."
  - "Filling a pending H=10 outcome is maturation, not a rewrite. A conflicting identity payload on a frozen key must fail closed."
  - "A degraded/fallback night is excluded from the paired race; it is not a zero and not a tie."
  - "Pages-only / reconstructed input must not enter through the normal writer. Missing sessions stay gaps."
  - "Family/coverage rows are outcome-blind. Do not join grades into structural diagnostics."
  - "Reading comparative W3 outcomes, or building the PR-3D display surface, is the next session. Doing it here contaminates the frozen prereg."
---

# PR-3C — durable prospective W3 evidence ledger

PR-3C is measurement plumbing. C1 stays the live ranker. No forward C1-vs-shadow
outcome was read. The nightly `us_prophet_ledgers` job owns W3 writes. The
ranking engine still has no persistent W3 store.

## What landed

- **Paired grain** at `data/us_prophet_rank/w3/paired/YYYY-MM/YYYY-MM-DD.parquet`.
  Canonical buy rows with both C1 and `us_prophet_v2_shadow` ranks join one
  existing H=10 grade row. Unmatured outcomes stay pending.
- **Family / coverage grains** serialize the PR-3B compact receipt. LOFO is not
  recomputed in the writer.
- **status.json** records liveness (`paired_accrued` / `unmatured` /
  `degraded_or_unpaired` / `session_missing`) and forbids a comparison surface.
- **Nightly wiring** after `grade_us_prophet_candidates` and before the ledger
  commit; `COLLECT_LANE=nightly` gates every write.

## Forward

PR-3D is a new session: live instrumentation acceptance + lawful status/display.
Before 20 distinct matured H=10 paired sessions, that display may show
accrual/maturity/gap status only. The prereg forbids comparison, confidence
intervals, p-values, or “who is winning” before the floor.
