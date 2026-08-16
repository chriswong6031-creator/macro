---
key: REFUSAL-BRANCH-HIDES-A-DEAD-LOOKUP
claim: >
  A per-item lookup wrapped in a broad `except -> refusal row` cannot distinguish a
  sparse input from a structurally dead lookup, and the dead case is the silent one.
  Measured in W5's §7 control matching: the feature panel's `session` column is OBJECT
  dtype holding `datetime.date` (`feature_panel._as_dates` -> `build_feature_rows`,
  preserved by `cross_sectionalize`), `_ctx_session_rows` keyed it on
  `pd.Timestamp(session)`, and `date == Timestamp` is False in Python — so the mask was
  all-False for EVERY session, every episode raised into
  `{"reason": "control_match_unavailable"}`, and the run emitted a full refusal census
  instead of a stack trace. The same function counted §7 session offsets from the
  panel's own DECISION sessions rather than the bench calendar, so the frozen ±5 and
  (D, D+H] exclusions over-excluded and shrank every pool on top of that.
falsifier: >
  `panel = feature_panel.cross_sectionalize(feature_panel.build_feature_rows(...))`
  followed by `panel["session"].dtype` returning anything but `object`, or
  `(panel["session"] == pd.Timestamp(s)).sum()` returning non-zero for a session `s`
  that is in the panel; or `controls.ControlMatch.session` ceasing to be annotated
  `date`; or `scripts/entry_radar_replay.build_match_context` ceasing to pass
  `panels.session_calendar(spy)` to `attach_session_positions`.
so_what: >
  Two things change. (1) When a run reports a refusal/coverage census at or near 100%,
  treat that as a BROKEN INSTRUMENT hypothesis before a data hypothesis, and test the
  lookup directly — the census is the defect's camouflage, not evidence about the
  universe. Any refusal count >= the episode count is disqualifying on its face.
  (2) A branch that turns an exception into a counted refusal needs a structural guard
  ABOVE it that refuses when the branch would fire for everything; `build_match_context`
  now raises `ReplayRefusal` when the panel answers 0 of N decision sessions and prints
  a `::warning` on partial coverage. Applies to every replay/census path in
  `engine/entry_radar/replay/` and to any builder whose per-item failure is a data row.
  Concretely for W5: the definitive Panel-A/Panel-B confirmatory replays have never been
  run (no `w5_results_panel_*.json` exists), so nothing needs re-reading — but every
  §7-matched question is UNPRODUCED, not merely unverified.
kind: landmine
verified_at: 2026-08-15
verified_by: >
  Reproduced through the production builder at 65f9669f (pandas 3.0.3):
  `panel["session"].dtype` = object, `type(...iloc[0])` = datetime.date,
  `(panel["session"] == pd.Timestamp(s)).sum()` = 0 vs `== s` = 1. Real-run receipt in
  `data/trial_ledger.jsonl`: 81 `source: w5_replay` looks 2026-08-15T09:19-09:33Z, all
  `names_shard: [NVDA,KO,JPM,MSFT,XOM]`, whose Panel-B row reads
  `{"cell": "refusal_census", "n_refusals": 543, "n_episodes": 502}` — refusals exceed
  episodes. Mutation controls both directions in
  tests/test_entry_radar_w5_data.py::test_ctx_session_rows_reads_the_dtype_the_production_builder_emits
  and ::test_build_match_context_counts_offsets_on_the_bench_calendar (the latter fails
  `assert 2 == 400` on the pre-fix map). Full write-up:
  research/live_entry_radar/W5_CONTROL_MATCHING_DEFECT_2026-08-15.md.
scope: [macro, research/live_entry_radar/, scripts/entry_radar_replay.py, engine/entry_radar/replay/]
confidence: verified
---

## Detail

The two defects are one failure mode at two altitudes, which is why they shipped
together and why neither was caught by a green suite.

`_ctx_session_rows` was unit-testable and untested; `build_match_context` had **no test
at all**. What tests did exist covered the primitives correctly —
`tests/test_entry_radar_w5_data.py` even built a bench calendar and asserted "a bench
calendar must override the panel's own" against `attach_session_positions`. The
primitive was right, the wiring was absent, and no test looked at the wiring.
`panels.session_calendar` had zero callers in the replay stack.

The dtype half is the more instructive one. It is not a crash that got swallowed; it is
a comparison that is *legally False*. `pd.Timestamp` subclasses `datetime` subclasses
`date`, so `isinstance(Timestamp(...), date)` is True — which makes the two spellings
look interchangeable to a reader and to a type checker — while `date.__eq__(datetime)`
returns False, so a pandas elementwise mask over them is silently all-False. A lookup
that returns an empty frame instead of raising is indistinguishable from a legitimately
empty slice at the call site, and the call site had already decided that an empty slice
means "refuse this episode".

The fix keeps `date` as the panel's canonical spelling rather than converting the column
to datetime64, because `controls.ControlMatch.session` is annotated `date` and is
populated straight from `candidate_row["session"]`: converting the column would change
the §7 result object's own type and its serialized shape, which is a frozen-output
change, not a repair. The conversion boundary stays where it was already declared —
`attach_session_positions`, documented as returning `dict[pd.Timestamp, int]`.

Related: [[DSC-CHAMPION-BASELINE-COLUMNS-CARRY-THE-CHALLENGER]] — same family, one level
up: a column whose meaning silently changed announces nothing at the first read, while a
null announces itself immediately.
