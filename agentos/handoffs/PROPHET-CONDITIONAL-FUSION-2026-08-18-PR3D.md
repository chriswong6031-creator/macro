---
workstream: WS:PROPHET-CONDITIONAL-FUSION
title: Prophet Conditional Fusion — PR-3D production commissioning + liveness fence + lawful status
date: 2026-08-18
session: claude/prophet-fusion-pr3d-liveness
model: local
ended_because: blocked
prs: []
repo: mastermindx-market-intelligence/macro
main_at_start: 4b77e9afd24c15127b7206d4aed855d2a1b36234
mission: >
  PR-3D only. Close W3 instrumentation as a real production capability: durable
  session_missing semantics, W3-native provenance fence against #5878 generic
  backfill, live three-lane acceptance, and a lawful pre-floor status surface.
  No V4, no C2/C3/C4/C5, no comparative outcome read.
state_before: >
  PR-3A #5813, PR-3B #5829, PR-3C #5839 merged. W3_RACE_PREREG frozen. data/us_prophet_rank/w3
  absent on origin/main. First post-#5839 daily (run 32084697588) still in engine;
  us_scan_tier and us_prophet_ledgers had not started. Committed board as_of=2026-08-17
  is us_prophet_v3 with prophet_fusion.w3_structural.v1. Candidates store has 65
  v3+shadow buy rows on that stamp. Grades store has never been committed to main.
changed:
  - path: engine/us_prophet_w3.py
    what: "Durable sessions.jsonl; terminal session_missing/degraded_or_unpaired
      cannot be resurrected; gap receipts persist before fail-closed; lawful
      pre-floor status surface; required stamp from committed board as_of."
  - path: scripts/accrue_us_prophet_w3.py
    what: "--require-board-as-of nightly flag. Observation identity is board as_of,
      never wall-clock / run id."
  - path: scripts/report_us_prophet_w3.py
    what: "Read-only CLI status surface. Exit 2 if store is not commissioned.
      Never computes comparison statistics."
  - path: tests/test_us_prophet_w3.py
    what: "PR-3D adversarial tests: durable missing receipt, commit-survival,
      reconstruction refusal, degraded refusal, unmatured→matured, UTC≠stamp,
      Pages-only exclusion, structural-absent, board mismatch, status tokens."
  - path: tests/test_prophet_off_engine_lane.py
    what: "Lane-gate sessions.jsonl/status writes; allow extra fail-closed flags
      on the W3 nightly command."
  - path: .github/workflows/daily.yml
    what: "W3 step passes --require-board-as-of. git add data/us_prophet_rank/w3
      still covers sessions.jsonl."
  - path: config/dag.yml
    what: "Declare --require-board-as-of on accrue_us_prophet_w3."
  - path: agentos/decisions/DEC-W3-PROSPECTIVE-SAMPLE-IGNORES-GENERIC-BACKFILL.md
    what: "#5878 product backfill does not admit reconstructed sessions to the W3 race."
  - path: agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md
    what: "PR-3D scope; w3 stays todo until live acceptance; owns report script."
verified:
  - claim: "W3 + off-engine-lane + grades zero-authority/DAG tests are green"
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python3 -m pytest tests/test_us_prophet_w3.py tests/test_prophet_off_engine_lane.py tests/test_us_prophet_grades.py::TestZeroAuthorityFence tests/test_us_prophet_grades.py::TestDagWiring -q --tb=line"
    result: "84 passed"
  - claim: "AgentOS store validates with 0 errors after the new DEC"
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python3 scripts/agentos.py validate"
    result: "0 error(s); 8 pre-existing warnings on other workstreams"
  - claim: "DAG conformance accepts the W3 --require-board-as-of args"
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python3 scripts/check_dag_conformance.py"
    result: "DAG conformance OK — 27 lane(s) checked"
  - claim: "exclusive-scope closure still covers the W3 import set"
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python3 -m pytest tests/test_ci_pack.py::test_curated_exclusive_scopes_cover_their_own_import_closure -q --tb=line"
    result: "1 passed"
  - claim: "no live rank consumer imports the W3 store"
    command: "rg -n 'us_prophet_w3|us_prophet_rank/w3' engine/us_board_rank.py engine/us_prophet_fusion.py engine/prophet_bridge.py engine/us_candidate_lanes.py scripts/build_stock_library.py"
    result: "empty"
  - claim: "dry-run against committed main sees 2026-08-17 as unmatured paired=65 pending=65; older stamps degraded_or_unpaired; no comparison statistic printed"
    command: "COLLECT_LANE=nightly python3 -m scripts.accrue_us_prophet_w3 --dry-run --require-board-as-of"
    result: "paired_rows=65 family_rows=8 coverage_rows=8 honest_n_matured_h10=0; 2026-08-17 unmatured; comparison forbidden"
unverified:
  - claim: "CI packs on this PR conclude green (or spurious-only Workers X)"
    what_would_verify: "gh pr checks after packs conclude"
  - claim: "a completed natural us_prophet_ledgers run persists paired/family/coverage/status on main"
    what_would_verify: "post-merge or in-flight daily 32084697588: us_prophet_ledgers step accrue_us_prophet_w3; git ls-tree origin/main -- data/us_prophet_rank/w3"
unresolved:
  - "PRODUCTION PROOF is BUILT_NOT_PROVEN. Daily 32084697588 was still in engine when this session stopped; us_scan_tier and us_prophet_ledgers had not started. Do not dispatch a second daily over that in-flight baseline."
  - "w3 wave stays todo. Do not call W3 done."
  - "Grades store is empty on main, so the first lawful liveness for 2026-08-17 is unmatured even if paired/family/coverage land. That is not a comparative outcome."
  - "C2 commissioning remains data-gated. Do not rebuild #5700."
next_actions:
  - "Watch daily 32084697588 to us_prophet_ledgers (do not cancel; do not re-dispatch). Inspect W3 step logs and whether data/us_prophet_rank/w3 reached main. Do not read C1-vs-shadow IC/delta/p-values/leader."
  - "If that run writes W3 parts, treat 2026-08-17 as the first prospective paired stamp (unmatured until H=10 grades exist) and update this handoff + WS w3 status."
  - "If the run never reaches us_prophet_ledgers, keep BUILT_NOT_PROVEN and name the external availability defect. Do not weaken checkpoint/push fences."
  - "Do not start Prophet V4 or C2/C3/C4/C5 from this wave."
do_not_redo:
  - "Do not re-litigate C1 / us_prophet_v3 adoption."
  - "Do not rebuild C2 or relax C2 fold/depth laws."
  - "Do not build another v2 scorer or another grader."
  - "Do not copy prophet_shadow_* into canonical prophet_* columns on v3."
  - "Do not backfill the Pages-only v3 session; do not count retries of one as_of as multiple nights; do not stamp shadow on us_prophet_v2_fallback."
  - "Do not let #5878 generic backfill resurrect a W3 session_missing or degraded_or_unpaired receipt."
  - "Do not weaken the fail-closed git/checkpoint behavior (#5742)."
  - "Do not bump SELECTION_ERA."
  - "Do not recompute LOFO in the W3 ledger writer; persist the PR-3B receipt."
  - "Do not emit ΔIC, HAC, p-values, CIs, or a leader from this ledger before N=20 matured H=10."
danger_areas:
  - "Observation identity is candidate stamp_date / board as_of, never GitHub run date or UTC wall clock."
  - "session_missing and degraded_or_unpaired are terminal. Only unmatured → paired_accrued is lawful."
  - "W3 step must fail visible on a first missing required stamp, but the always-run commit must still land sessions.jsonl + status.json."
  - "A pytest tmp path containing the substring 'pages' is not a Pages artifact; the source-token fence must not scan filesystem paths."
  - "Reading comparative W3 outcomes before the honest-N floor contaminates the frozen prereg."
---

# PR-3D — production commissioning (BUILT_NOT_PROVEN)

PR-3D is instrumentation closure, not a statistical read. C1 stays the live
ranker. No forward C1-vs-shadow outcome was inspected.

## Step 0 — natural night (re-inspected 2026-08-18)

Post-#5839 daily **32084697588** (`workflow_dispatch`, head `63f4055e`, contains
PR-3C) was still `in_progress` with **engine running**. `us_scan_tier` had not
started. `us_prophet_ledgers` needs `[et_gate, engine, us_scan_tier]`, so W3
accrual has not run. `data/us_prophet_rank/w3` is absent on `origin/main`.
The 6-second "success" scheduled run 32081800404 skipped every job except
`et_gate`. Do not treat that as a bake.

Committed board `as_of=2026-08-17` is `us_prophet_v3` and already carries
`ranking.fusion.w3_structural` schema `prophet_fusion.w3_structural.v1`.
The candidates store has **65** canonical-buy rows with both C1 and
`us_prophet_v2_shadow` on that stamp. The grades store has **never** been
committed to main, so first liveness is **unmatured**.

A dry-run of the PR-3D writer against that committed tree (no writes) reported
`2026-08-17 unmatured paired=65 pending=65` and older stamps
`degraded_or_unpaired`. That is not production proof.

## What landed in this PR

Durable `sessions.jsonl` keep-first history. Required stamp comes from committed
board as_of (`--require-board-as-of`). A first missing required stamp persists
`session_missing` then fails visible so the `if: always()` commit can still
stage the gap. Terminal states refuse later reconstructed candidate payloads
(`DEC:W3-PROSPECTIVE-SAMPLE-IGNORES-GENERIC-BACKFILL`). Status/CLI may show
accrual/maturity/gap plus outcome-blind structural counts only.
