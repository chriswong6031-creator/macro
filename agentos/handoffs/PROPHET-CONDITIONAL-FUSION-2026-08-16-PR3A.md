---
workstream: WS:PROPHET-CONDITIONAL-FUSION
title: Prophet Conditional Fusion — PR-3A semantics, PIT admission, W3 prereg freeze
date: 2026-08-16
session: claude/prophet-fusion-pr3a-semantics
model: local
ended_because: complete
prs: ["#5813"]
repo: mastermindx-market-intelligence/macro
main_at_start: e7cdfa25732209d56633f2d734024c90057d3538
mission: >
  PR-3A only. Reconcile AgentOS/workstream truth, make families.yml baseline roles
  definition-aware, admit pit_settlement under the #5705 producer law, and freeze
  W3_RACE_PREREG.md before any forward C1-vs-shadow outcome read. Do not roll into
  PR-3B. Do not reopen C1 adoption.
state_before: >
  C1/us_prophet_v3 is the live US ranker. W2 machinery merged as #5700 but the
  workstream still needed the done-status reconciliation. families.yml still had a
  timeless champion_baseline.columns list. Fusion arena still refused pit_settlement
  on the retired settlement+10-calendar derivation. W3_RACE_PREREG.md did not exist.
  Durable paired-race N was 0. Last durable handoff:
  agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-16-W3-BUILD-HANDOFF.md (#5807).
changed:
  - path: agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md
    what: "w2 status done (#5700) with C2 commissioning still data-gated; cite
      DEC:US-SHADOW-ACCRUES-UNDER-ITS-OWN-COLUMN-FAMILY and
      DSC:CHAMPION-BASELINE-COLUMNS-CARRY-THE-CHALLENGER; close task_8c904665;
      keep #5742 as external availability debt; next_action is PR-3B after this merge."
  - path: agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-16-ACCEPTANCE.md
    what: "Body addendum: shadow-store/task_8c904665 closed by #5769; #5742 remains
      external. Historical YAML unresolved block left as that session's record."
  - path: agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-15-SHADOW-ACCRUAL.md
    what: "Body addendum: champion_baseline drift recut in PR-3A; no timeless columns list."
  - path: research/prophet_fusion/families.yml
    what: "baseline_roles keyed by meaning; champion_baseline is definition-keyed;
      pit_settlement admitted under #5705 with depth/basis caveats retained."
  - path: scripts/prophet_fusion_arena.py
    what: "BACKTEST_LAWFUL_STATUSES = {pit, pit_settlement}. Snapshot and forward_only
      still refused."
  - path: scripts/prophet_fusion_c2.py
    what: "Comment-only: pit_settlement is PIT-lawful after PR-3A and still not estimable."
  - path: tests/test_prophet_fusion_families.py
    what: "Definition-aware role tests, canonical/shadow swap mutation, #5705 PIT
      admission pin, W3 prereg freeze-token pin."
  - path: tests/test_prophet_fusion_arena.py
    what: "pit_settlement is backtest-lawful; snapshot/forward_only stay refused."
  - path: tests/test_prophet_fusion_c2.py
    what: "Deferral class flipped to admission; no would-have-entered / family-score claims."
  - path: research/prophet_fusion/W3_RACE_PREREG.md
    what: "Frozen W3 paired-race preregistration. No outcome read at freeze time."
  - path: research/prophet_fusion/W3_SHADOW_RACE_RECUT.md
    what: "Pointer: the freeze file is the decision; the recut remains the charter."
  - path: research/prophet_fusion/PR2_C2_REDUNDANCY.md
    what: "PR-3A reconciliation note on the historical F-5 deferral. PR-2 record not rewritten."
verified:
  - claim: AgentOS store validates with 0 errors
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python3 scripts/agentos.py validate"
    result: "122 records — 0 error(s), 39 warning(s) (pre-existing phantom-owns-path warnings on other workstreams)"
  - claim: targeted Fusion suites green on the PR-3A assertions
    command: "python3 -m pytest tests/test_prophet_fusion_families.py tests/test_prophet_fusion_arena.py tests/test_prophet_fusion_c2.py -q -k 'not test_the_real_frames_depth_refuses_every_fold and not test_the_cli_survey_reports_the_refusals'"
    result: "157 passed, 39 skipped, 2 deselected. The two deselected tests need data/ (sparse worktree); CI has a full checkout."
  - claim: no timeless champion_baseline.columns list remains
    command: "python3 -c \"import yaml; d=yaml.safe_load(open('research/prophet_fusion/families.yml')); print('columns' in d['champion_baseline'], list(d['champion_baseline']['by_board_definition']))\""
    result: "False ['us_prophet_v2', 'us_prophet_v2_fallback', 'us_prophet_v3']"
  - claim: BACKTEST_LAWFUL_STATUSES admits pit_settlement and producer lag is 8 sessions
    command: "python3 -c \"from scripts.prophet_fusion_arena import BACKTEST_LAWFUL_STATUSES, PIT_OK, PIT_SETTLEMENT; from lib.finra_knowable import KNOWABLE_LAG_SESSIONS; print(BACKTEST_LAWFUL_STATUSES, KNOWABLE_LAG_SESSIONS)\""
    result: "frozenset({PIT_OK, PIT_SETTLEMENT}) 8"
  - claim: W3_RACE_PREREG.md is frozen with no promotion arm
    command: "rg -n 'no promotion arm|20 distinct matured H=10 paired sessions|L=9' research/prophet_fusion/W3_RACE_PREREG.md"
    result: "tokens present; primary tripwire is HAC-t CI for ΔIC entirely below 0"
  - claim: engine/us_board_rank.py and engine/us_prophet_fusion.py were not edited
    command: "git diff --stat origin/main -- engine/us_board_rank.py engine/us_prophet_fusion.py"
    result: "empty"
unverified:
  - claim: CI packs on #5813 conclude green (or spurious-only Workers X)
    what_would_verify: "gh pr checks 5813 after packs conclude; arm merge-on-green and stay"
  - claim: squash-merge SHA of #5813
    what_would_verify: "gh pr view 5813 --json state,mergeCommit after merge"
  - claim: C2 still needs 91 graded dates / 67 more than held at the #5700 measurement
    what_would_verify: "re-run the #5700 C2 harness; the 24/91 figure is a dated distance receipt"
unresolved:
  - "W3 instrumentation is not built. Next session starts PR-3B only: outcome-blind LOFO plus full member census."
  - "No durable post-#5769 paired stamp yet. Do not backfill the Pages-only night. Honest-N remains 0 until that stamp exists and matures."
  - "#5742 availability/push contention remains external; keep the fail-closed checkpoint fence."
  - "C2 commissioning is data-gated, not a code project. Do not rebuild #5700. Do not relax fold/depth laws."
  - "Committed short-interest history is still 3 settlements; PIT-lawful is not estimable."
next_actions:
  - "After #5813 merges, a FRESH session starts PR-3B only: exact outcome-blind LOFO plus full member census. Do not read forward C1-vs-shadow outcomes."
  - "Do not implement W3 durable ledgers, nightly wiring, display, C2 fit, or C3/C4/C5 in that session."
do_not_redo:
  - "Do not re-litigate C1 / us_prophet_v3 adoption."
  - "Do not rebuild C2 or relax C2 fold/depth laws."
  - "Do not build another v2 scorer or another grader."
  - "Do not copy prophet_shadow_* into canonical prophet_* columns on v3."
  - "Do not backfill the Pages-only v3 session; do not count retries of one as_of as multiple nights; do not stamp shadow on us_prophet_v2_fallback."
  - "Do not weaken the fail-closed git/checkpoint behavior (#5742)."
  - "Do not bump SELECTION_ERA."
  - "Do not read forward outcomes before W3_RACE_PREREG.md (already frozen this PR)."
  - "Do not treat PIT-lawful short interest as statistically estimable."
danger_areas:
  - "A timeless champion_baseline.columns list would silently score C1 against itself on v3 rows."
  - "Copying shadow legs into canonical prophet_* on v3 is misattribution in an append-only store."
  - "Reading W3 outcomes before the freeze, or treating a point-estimate ΔIC as the tripwire, turns a guardrail into a post-hoc story."
  - "Admitting pit_settlement is a PIT gate, not permission to fit C2 or to infer from 3 settlements."
  - "A nightly can publish to Pages and not to git (#5742). W3 counts durable paired stamps only."
---

# PR-3A — semantics, PIT admission, W3 prereg freeze

PR-3A is the first W3 build slice. It does not instrument LOFO, ledgers, nightly
wiring, or a display surface. C1 stays the live ranker. No forward outcome
comparison was read.

## Reconciled

- **W2 status:** `done`, PR #5700. Real-frame C2 commissioning remains data-gated
  (24/91 graded dates at the #5700 measurement) and is not called operationally
  validated.
- **#5769 shadow-store record:** resolved. Canonical five-leg nulls on v3 are
  correct. `DEC:US-SHADOW-ACCRUES-UNDER-ITS-OWN-COLUMN-FAMILY` is cited from the
  workstream. `task_8c904665` is closed.
- **#5705 PIT integration:** Fusion arena/registry now admit `pit_settlement`
  under the 8th-NYSE-session law, floored by stored `knowable_date` and
  `capture_date`. The retired settlement+10-calendar refusal is gone from current
  Fusion law. Snapshot/forward-only stay refused. PIT-lawful ≠ estimable.
- **Stale workstream/landmine text:** #5742 kept as external availability debt.
  Acceptance/shadow-accrual handoffs carry body addenda so a cold reader does not
  reopen the shadow-store gap.

## Baseline semantics

- **canonical role:** `published_ranker_output` = `prophet_score` / `score_rank` /
  `display_rank`, interpreted under `board_definition`.
- **shadow role:** `retired_shadow_output` = `prophet_shadow_*`, valid when
  `board_definition=us_prophet_v3` and `prophet_shadow_definition=us_prophet_v2_shadow`.
- **legacy-v2 decomposition role:** the ten `prophet_{leg}` / `_points` columns;
  null by design on `us_prophet_v3`.
- **board consequence:** `featured` is `published_board_output`, not a shadow
  comparator.
- `champion_baseline` is definition-keyed. There is no timeless `columns` list.
- Tests pin disjointness, the role-swap mutation, and equality with
  `engine.us_context_vector.SHADOW_COLUMNS`.

## W3 prereg (frozen; no outcome read)

- Start boundary: first durably committed post-#5769 (`0233445657e8`) paired stamp.
  No Pages-only backfill.
- Primary horizon: H=10.
- Primary metric/sign: Spearman of `(-score_rank)` vs `excess_spy`; positive IC =
  ranker worked. Δ = IC_C1 − IC_shadow.
- Secondary: top-30 mean `excess_spy`, confirmatory only, not an OR tripwire.
- Honest-N floor: 20 distinct matured H=10 paired sessions.
- Overlap: Newey-West HAC, L=9, t-referenced, df = N_sessions − 1.
- Adverse tripwire: 95% HAC-t CI for Δ lies entirely below 0.
- Missing/degraded-session law: gaps remain gaps; fallback excluded; keep-first
  on `as_of` retries.
- Promotion arm: NONE. No automatic reversion. No C2 trigger. No second scorer.
  No second grader.

## Forward

PR-3B is a new session: outcome-blind LOFO + full member census. Do not start it
from this checkout.
