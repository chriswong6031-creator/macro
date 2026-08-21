---
workstream: WS:PROPHET-CONDITIONAL-FUSION
session: claude/fusion-c2-era-pin
model: local
ended_because: complete
mission: >
  Option B for the C2 live-frame CI red: PIT-pin tests to the PR-1b/PR-2 registered
  era by (date, ticker, horizon) row identity, rebuild C2 from that pin, keep a
  separate live accrual assertion. Do not re-stamp published numbers. Do not rewrite
  data/. Do not start PR-3D, C3, or a fold-law change.
state_before: >
  #5893 pointed nine vintage-bound tests at the committed report.json so they no
  longer raced the accruing ledger. Construction parity (rebuild the study, compare
  to PR-1b / doc tables) was still pointed at the grown live frame whenever a
  session reintroduced a live rebuild, and the program call left in
  PROPHET-CONDITIONAL-FUSION-2026-08-18-C2-VINTAGE.md was whether to re-register.
  Chairman commissioned Option B: pin the test era, do not re-freeze artifacts.
changed:
  - path: research/prophet_fusion/pr2_c2/era_frame_keys.parquet
    what: "4,075 unique (date, ticker, horizon) keys from 6adf8b728785's graded ledger (11 KB). Inner-join against live recovers the registered 4,077 rows."
  - path: research/prophet_fusion/pr2_c2/era_frame_pin.json
    what: "Pin metadata: 24 dates, 2026-06-15..2026-07-31, horizon date-blocks 24/17/7."
  - path: tests/test_prophet_fusion_c2.py
    what: "era_report rebuilds C2 from the pinned live rows + date-filtered snapshots. The nine vintage-bound tests (H=21 CMI/secondary, multiplicity, news_burst 1474, PR-1b §9.4, p_t literals, design membership, both doc tables) now consume era_report. TestRegisteredEraPin proves the key pin recovers 4,077 rows and that an as-of cutoff does not. TestTheLedgerAccruesRatherThanRewrites still watches the grown live frame. Runtime C2 untouched."
  - path: .github/ci/legacy-jobs.yml
    what: "Name era_frame_keys.parquet and era_frame_pin.json in unrun-picks-boards exclusive paths. Path literals in the C2 suite made them part of the job's import closure; leaving them unnamed redded pack-1's curated-closure ratchet (hosted-runner packing contract)."
  - path: agentos/decisions/DEC-FUSION-C2-TEST-ERA-IS-REGISTERED-VINTAGE.md
    what: "Program decision: Option B. Rejects A (re-stamp), C (relax/skip), and as-of cutoff."
  - path: agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md
    what: "Cited the DEC; landmine that C2 vintage tests pin the registered era, never the grown ledger."
verified:
  - claim: "Key pin recovers exactly 4,077 rows / 24 dates from the grown live ledger; 0 vintage keys missing."
    command: "python3 -m pytest tests/test_prophet_fusion_c2.py::TestRegisteredEraPin -q"
    result: "2 passed. Live inner-join == pin n_rows_expected; as-of cutoff at 2026-07-31 is strictly larger."
  - claim: "The original nine failures pass on the era rebuild with ledger_state/grades still grown."
    command: "python3 -m pytest tests/test_prophet_fusion_c2.py::TestCMI::test_h21_refuses_on_real_frame tests/test_prophet_fusion_c2.py::TestDescriptiveMinDates::test_h21_secondary_table_is_empty_because_every_cell_refuses tests/test_prophet_fusion_c2.py::TestWhatDoesXAddTable::test_multiplicity_sensitivity_is_reported tests/test_prophet_fusion_c2.py::TestNullSemanticsOnTheVarianceAxis::test_news_burst_is_unchanged_by_the_null_semantics_fix tests/test_prophet_fusion_c2.py::TestWhatDoesXAddTable::test_the_descriptive_tier_reproduces_pr1b_section_9_4 tests/test_prophet_fusion_c2.py::TestWhatDoesXAddTable::test_the_verdict_keys_on_t_and_both_references_are_printed tests/test_prophet_fusion_c2.py::TestWhatDoesXAddTable::test_design_membership_rides_beside_every_verdict tests/test_prophet_fusion_c2.py::TestDocTablesMatchTheArtifact -q"
    result: "those nine plus the two pin tests passed (11 passed in the combined invocation)."
  - claim: "Full C2 suite green."
    command: "python3 -m pytest tests/test_prophet_fusion_c2.py -q"
    result: "79 passed in 93.33s."
  - claim: "unrun-picks-boards fusion step green (families + arena + labels + race + C2)."
    command: "python3 -m pytest tests/test_prophet_fusion_families.py tests/test_prophet_fusion_arena.py tests/test_prophet_fusion_labels.py tests/test_prophet_fusion_race.py tests/test_prophet_fusion_c2.py -q"
    result: "267 passed in 144.35s."
  - claim: "unrun-picks-boards exclusive paths cover the era-pin files the C2 suite now reads."
    command: "python3 -m pytest tests/test_ci_pack.py::test_curated_exclusive_scopes_cover_their_own_import_closure -q"
    result: "1 passed in 160.15s after naming the two era-pin files. Pre-fix miss was exactly those two files."
  - claim: "Agent OS records validate."
    command: "python3 scripts/agentos.py validate"
    result: "0 errors (8 pre-existing phantom-owns-path / active-but-complete warnings in other records)."
  - claim: "Published C2/PR-1b artifacts and Prophet engine paths were not modified."
    command: "git diff --stat HEAD -- research/prophet_fusion/pr2_c2/report.json research/prophet_fusion/pr1b_baseline_race/report.json research/prophet_fusion/PR2_C2_REDUNDANCY.md engine/prophet_*.py engine/entry_signal.py engine/us_prophet_fusion.py data/"
    result: "empty."
unverified: []
unresolved:
  - question: >
      Should PR-2 / PR-1b ever be re-run and re-registered once ~91 graded dates exist?
    why_open: >
      Option A remains a future program call. This repair does not foreclose it. The
      frozen fold law still refuses C2 fit; 25 live dates are not 91.
next_actions:
  - owner: session
    action: "Squash-merge this PR once ci-pack / unrun-picks-boards concludes green."
  - owner: WS:PROPHET-CONDITIONAL-FUSION
    action: "Do not start PR-3D comparative outcome reads. Do not re-stamp C2 artifacts on the next horizon maturation — the pin absorbs it."
do_not_redo:
  - "Do not re-stamp research/prophet_fusion/pr2_c2/report.json or PR2_C2_REDUNDANCY.md tables to today's numbers to green CI."
  - "Do not recover the vintage with an as-of cutoff — TestRegisteredEraPin::test_an_as_of_cutoff_does_not_recover_the_registered_vintage pins that it is larger than 4,077."
  - "Do not commit snapshots.jsonl as a fixture (17.6 MB). Date-filter the live file."
  - "Do not rewrite data/us_board_ledger/**. Nightly is the sole advancer."
  - "Do not relax tolerances or skip when the live frame grows (Option C)."
danger_areas:
  - "A new vintage-bound literal asserted against real_report is the same standing race. Registered construction belongs on era_report; live growth belongs on TestTheLedgerAccruesRatherThanRewrites."
  - "A new path literal under research/prophet_fusion/ in tests/test_prophet_fusion_c2.py must be named in unrun-picks-boards exclusive paths or pack-1's curated-closure ratchet reds."
  - "If a nightly REWRITES settled (date, ticker, horizon) keys rather than accruing, the pin's inner-join will drop below 4,077 and fail closed — that is the rewrite alarm, not a reason to refresh the pin."
decisions:
  - DEC:FUSION-C2-TEST-ERA-IS-REGISTERED-VINTAGE
discoveries:
  - DSC:GRADED-BOARD-LEDGER-ACCRUES-BY-HORIZON
---

## Option B in one paragraph

The graded ledger accrued H=10/H=21 inside already-published dates, so a live C2 rebuild
diverged from the frozen 4,077-row / 24-date / 7/7/4-block era. Reconstruct that era by
joining today's ledger to the committed key pin, rebuild, and compare to the frozen
artifacts. Leave the published numbers alone. Leave data/ alone.
