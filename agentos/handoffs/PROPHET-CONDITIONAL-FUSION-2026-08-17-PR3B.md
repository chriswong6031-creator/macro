---
workstream: WS:PROPHET-CONDITIONAL-FUSION
title: Prophet Conditional Fusion — PR-3B outcome-blind LOFO + member census
date: 2026-08-17
session: claude/prophet-fusion-pr3b-lofo
model: local
ended_because: complete
prs: ["#5829"]
repo: mastermindx-market-intelligence/macro
main_at_start: c76767c72d41cd74e498d514d502cea0c2b364c0
mission: >
  PR-3B only. Implement exact outcome-blind leave-one-family-out rank displacement,
  a complete registered-member census, and a compact board-level fusion structural
  receipt, with adversarial tests proving the diagnostics cannot change production
  authority. Do not roll into PR-3C. Do not read forward C1-vs-shadow outcomes.
state_before: >
  PR-3A merged as #5813 (8b5cd60f706e). W3_RACE_PREREG.md is frozen. C1/us_prophet_v3
  is the live US ranker. Fusion receipt reported floors and family presence but had
  no exact LOFO and no admitted-member census. No data/us_prophet_rank/w3 store.
  Last durable handoff: agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-16-PR3A.md.
changed:
  - path: engine/us_prophet_fusion.py
    what: "diagnose_structure: exact LOFO on frozen admitted members + full member
      census. fuse_board keeps extracted members and the Admission on the plane.
      Floor measurement helper shared with admit_members; admission decisions unchanged."
  - path: engine/us_board_rank.py
    what: "After score/rank/display/featured are final, compute structural diagnostics
      on a ticker/stage/rank copy and attach the compact block to the existing fusion
      receipt via fusion_floors. Degraded/fallback nights still have no fusion receipt
      and therefore no canonical W3 observation. No new persistent engine write."
  - path: tests/test_prophet_fusion_w3_structural.py
    what: "Ten required mutations plus census/receipt pins. Outcome-blind; no grades store."
  - path: .github/ci/legacy-jobs.yml
    what: "Name the new suite in unrun-picks-boards exclusive paths and pytest run."
  - path: agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md
    what: "w3 title notes PR-3A (#5813) and PR-3B scope; next_action is PR-3C after merge.
      w3 status stays todo until PR-3D."
  - path: agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-17-PR3B.md
    what: "This handoff."
verified:
  - claim: PR-3B structural suite and existing C1 fusion suite green (sparse-safe subset)
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python3 -m pytest tests/test_prophet_fusion_w3_structural.py tests/test_us_prophet_fusion.py -q --tb=short -k 'not TestByteParityWithTheRacedC1 and not TestLegacyV2ByteParity'"
    result: "71 passed, 1 skipped, 6 deselected. Skipped/deselected need site/ or data/ (sparse worktree)."
  - claim: curated exclusive import-closure still covers unrun-picks-boards
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python3 -m pytest tests/test_ci_pack.py::test_curated_exclusive_scopes_cover_their_own_import_closure -q --tb=short"
    result: "1 passed"
  - claim: AgentOS store validates with 0 errors
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python3 scripts/agentos.py validate"
    result: "0 error(s); pre-existing phantom-owns-path warnings on other workstreams"
  - claim: no data/us_prophet_rank/w3 path was introduced
    command: "rg -n 'us_prophet_rank/w3' engine/us_prophet_fusion.py engine/us_board_rank.py tests/test_prophet_fusion_w3_structural.py"
    result: "only the test that forbids the path"
  - claim: daily.yml was not modified
    command: "git diff --stat origin/main -- .github/workflows/daily.yml"
    result: "empty"
  - claim: C1 floors/weights/families.yml/SELECTION_ERA/BOARD_DEFINITION were not altered
    command: "git diff --stat origin/main -- research/prophet_fusion/families.yml engine/us_prophet_fusion.py | head"
    result: "families.yml empty; us_prophet_fusion.py adds diagnostics beside unchanged PRESENCE_FLOOR/VARIANCE_* constants"
unverified:
  - claim: CI packs on this PR conclude green (or spurious-only Workers X)
    what_would_verify: "gh pr checks after packs conclude"
  - claim: live board order is byte-identical to pre-PR-3B on the same pool
    what_would_verify: "first post-merge nightly; mutation 10 already pins score/rank/display/featured/population locally"
unresolved:
  - "PR-3C is not built. Next session starts PR-3C only: durable paired ledger + us_prophet_ledgers wiring. Do not begin it from this checkout."
  - "No durable post-#5769 paired stamp yet. Do not backfill the Pages-only night. Honest-N remains 0 until that stamp exists and matures."
  - "#5742 availability/push contention remains external; keep the fail-closed checkpoint fence."
  - "C2 commissioning is data-gated, not a code project. Do not rebuild #5700. Do not relax fold/depth laws."
next_actions:
  - "After this PR merges, a FRESH session starts PR-3C only. Do not read forward C1-vs-shadow outcomes."
  - "Do not implement W3 display, C2 fit, or C3/C4/C5 in that session."
do_not_redo:
  - "Do not re-litigate C1 / us_prophet_v3 adoption."
  - "Do not rebuild C2 or relax C2 fold/depth laws."
  - "Do not build another v2 scorer or another grader."
  - "Do not copy prophet_shadow_* into canonical prophet_* columns on v3."
  - "Do not backfill the Pages-only v3 session; do not count retries of one as_of as multiple nights; do not stamp shadow on us_prophet_v2_fallback."
  - "Do not weaken the fail-closed git/checkpoint behavior (#5742)."
  - "Do not bump SELECTION_ERA."
  - "Do not treat LOFO displacement as predictive importance or as a floor-retune signal."
  - "Do not recompute presence/variance floors after family ablation."
danger_areas:
  - "The fusion plane is pre-sort aligned; joining published score_rank onto diagnostic rows must be by ticker, never by post-sort index."
  - "Exact family scores live on the in-memory plane. The stamped family_contribution is 2-decimal display and must not be the LOFO input."
  - "A degraded night has no prophet.fusion, so fusion_ranking_receipt returns None. That is the no-observation, not a zero-displacement row."
  - "Reading W3 outcomes, or wiring data/us_prophet_rank/w3, is PR-3C+. Doing it here contaminates the frozen prereg."
---

# PR-3B — outcome-blind LOFO + member census

PR-3B instruments structural diagnostics only. C1 stays the live ranker. No
forward C1-vs-shadow outcome was read. No `data/us_prophet_rank/w3` store. No
`daily.yml` change.

## What landed

- **Exact LOFO** on the frozen admitted member set. One family is removed from
  the already-computed in-memory family scores. Floors, percentiles, and
  `aggregate` are not re-run. Null stays null. Order is stage bucket, then
  scored-before-unscored, then score, then ticker. Tie-share is descriptive.
- **Full member census** for every C1 registered member: voting /
  below_presence / vote_inert / collapsed_duplicate / absent, with coverage,
  distinct-value count, variation share, thresholds, reason, and source.
  Staleness basis is filled only where the registered source already names one.
- **Compact receipt** on the existing board-level fusion block
  (`schema: prophet_fusion.w3_structural.v1`). Computed after
  score/rank/display/featured are final. No new persistent engine write.

## Mutations pinned

1. High tie-share family still shows large planted LOFO movement.
2. Variance-floor eligibility is not LOFO usefulness.
3. Recomputing floors / percentiles / aggregate during ablation reds.
4. Ignoring stage buckets reds.
5. Null-as-zero reds.
6. Degraded/fallback board emits no canonical W3 observation.
7. Injected outcome columns cannot affect diagnostics.
8. Input-row permutation cannot affect diagnostics.
9. Reconstructed full-model diagnostic order equals published canonical rank.
10. Diagnostics cannot mutate canonical score/rank/display/featured/population.

## Forward

PR-3C is a new session: durable paired ledger using the existing candidates
store plus one shared grader, wired into `us_prophet_ledgers`. Do not start it
from this checkout.
