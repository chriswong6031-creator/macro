---
key: COVERAGE-FLOOR-MEASURES-PRESENCE-NOT-VARIANCE
claim: >
  A non-null coverage floor (the families.yml default 0.50) admits features that are
  present everywhere but cross-sectionally constant, so they pass the gate while being
  unable to reorder anything. Measured in PR-1b: news_burst fires on 19 of 1,493
  graded-frame rows; its within-date percentile is a near-constant, F8's
  leave-one-family-out delta is exactly 0.000 with CI [0,0], yet the 0.50 floor
  admitted it because non-null share is ~100%.
falsifier: >
  A registry floor spec that additionally gates on within-date cross-sectional
  dispersion (e.g. minimum distinct-value share or MAD > 0 on >=X% of dates) under
  which a near-constant flag like this frame's news_burst is excluded or marked
  vote-inert, while genuinely sparse-but-variable features still pass.
so_what: >
  Any equal-weight or budgeted family vote (C1 now, C2+ later, and any future
  confluence-style construction) can silently carry dead voters that dilute the
  live ones — a C1 vote "four families wide" was really two readable voters wide.
  When PR-2 revisits the registry's floors, the floor law needs a variance axis
  beside the presence axis; until then, per-family distinct-fire counts belong next
  to every family-vote table (PR-1b prints them in §9.1).
kind: constraint
verified_at: 2026-08-14
verified_by: >
  research/prophet_fusion/PR1B_BASELINE_RACE.md §9.1-§9.2 (fire counts, LOFO
  F8 = 0.000 CI [0,0]); research/prophet_fusion/pr1b_baseline_race/report.json
  c1_analysis; families.yml coverage_floor semantics (masterplan §5.1).
scope: [macro]
confidence: verified
---

## Detail

The floor was registered to stop families from imputing their way into a vote
(abstain-not-impute, #4485). It does that. What it cannot see is a column whose
values are almost all the same value: presence 100%, information ~0. The failure is
quiet because the vote arithmetic still runs — the family contributes a constant
percentile that shifts every row equally and cancels in ranking. The registered
fix direction (variance-aware floor) is a PR-2 registry question, not a patch to
sneak into a race PR.

## Resolution (PR-2, 2026-08-14)

The falsifier's spec landed in `research/prophet_fusion/families.yml`
(`semantics.variance_floor` + `variance_floor_spec`): a member is VOTE-INERT on a
frame when fewer than 50% of frame dates carry >= 2 distinct non-null oriented
values — defined on features alone (no outcome enters the rule), frame-relative,
computed at evaluation time, disclosed rather than hidden. The PR-2 harness
(`scripts/prophet_fusion_c2.py`) computes it for every wired member; the suite pins
both halves of the falsifier (news_burst-shaped near-constants marked inert;
sparse-but-VARIABLE synthetic members pass). The constraint this record states
remains true of the PRESENCE floor; the variance axis now exists beside it.
