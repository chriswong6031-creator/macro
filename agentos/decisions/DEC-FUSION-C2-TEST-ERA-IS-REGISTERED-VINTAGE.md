---
key: FUSION-C2-TEST-ERA-IS-REGISTERED-VINTAGE
question: >
  The graded board ledger accrued past the 7/7/4 date-block era PR-2 / PR-1b registered
  against, so C2 tests that rebuild from the LIVE frame diverge from the frozen artifact
  and doc tables. Re-run and re-freeze the published numbers (Option A), PIT-pin the
  test frame to the registered era and keep a separate live assertion (Option B), or
  relax tolerances / skip when the frame has moved (Option C)?
answer: >
  Option B. Reconstruct the PR-2 frame by (date, ticker, horizon) row identity from the
  live ledger (committed pin at research/prophet_fusion/pr2_c2/era_frame_keys.parquet),
  rebuild C2 against that era, and assert construction parity with the frozen PR-1b /
  PR-2 artifacts and doc tables. The live grown frame is checked only by accrual-aware
  assertions (rows/dates may grow; the window's first date and the closed-by-date
  unverified_pre_20260806 population may not move). Published research numbers are not
  rewritten.
rationale: >
  Both sides of the 2026-08-18 divergence are correct: the committed artifacts are right
  for the vintage they registered, and a live rebuild is right for today's ledger. The
  defect is asserting REGISTERED literals against an accruing input. Option A changes
  published research numbers and would have to re-run PR-1b too; nothing in the growth
  (still far short of the frozen §9.2 fold law) forces that. Option C deletes the parity
  property the suite exists to hold. Option B keeps that property pointed at the frame
  the numbers were derived from. An as-of cutoff is the wrong pin — maturation lands
  INSIDE the registered window (cut at 2026-07-31 yields 4,409 rows, not 4,077). The
  grain that recovers the vintage is (date, ticker, horizon); unique tickers per date
  do not move. Snapshots are filtered to the pinned dates, not frozen as a 17.6 MB
  fixture. #5893's artifact-read remains the record of what was registered; construction
  is the era rebuild.
alternatives:
  - option: Re-run PR-1b and PR-2 on the current frame and re-freeze artifact + doc tables (A)
    why_not: Changes published research numbers. The headline result is unchanged —
      25 dates still cannot satisfy the frozen fold law — so nothing forces a re-stamp.
      The next horizon maturation would force another. Requires a separate program
      re-registration, not a CI heal.
  - option: Relax tolerances or skip when the frame has moved (C)
    why_not: Deletes the parity property. The §9.4 test's own docstring forbids pinning
      a hand-copied number in place of the construction.
  - option: Date-cut the live ledger at the registered end date
    why_not: Measured — yields 4,409 rows, not 4,077, because H=10/H=21 maturation
      lands inside 2026-06-15..2026-07-31. DSC:GRADED-BOARD-LEDGER-ACCRUES-BY-HORIZON.
  - option: Commit the full vintage parquet + snapshots.jsonl as a fixture
    why_not: The G0 replay's registered snapshots slice alone is 17.6 MB. The 3-column
      key pin is 11 KB and recovers the 4,077 rows from the live ledger, which is
      required to keep accruing.
evidence:
  - "git show 6adf8b728785:data/us_board_ledger/retro_grades.parquet is 4,077 rows / 24 dates / 2026-06-15..2026-07-31; live ledger is 4,566 rows / 25 dates / ..2026-08-07"
  - "Inner-join of live rows onto the 4,075 unique (date, ticker, horizon) keys recovers exactly 4,077 rows (the two duplicates the labels receipt already drops); 0 vintage keys are missing from live"
  - "As-of cutoff at 2026-07-31 on live = 4,409 rows, not 4,077"
  - "Horizon date-blocks on the pin: H=5 24, H=10 17, H=21 7 — the 7/7/4 CMI/secondary refusals are this era, not a code defect"
  - "#5893 / DSC:GRADED-BOARD-LEDGER-ACCRUES-BY-HORIZON documented the race; this DEC chooses the construction pin that session left as a program call"
affects:
  - WS:PROPHET-CONDITIONAL-FUSION
  - tests/test_prophet_fusion_c2.py
  - research/prophet_fusion/pr2_c2/
confidence: high
reversibility: easy
reversibility_detail: >
  Tests and an 11 KB key pin. Runtime C2, Prophet rankers, and published report.json /
  doc tables are untouched. Reverse by reverting the PR. A later Option A re-registration
  rewrites the pin from the new vintage.
decided_by: chairman
decided_at: 2026-08-18
---

## What this does not authorize

It does not re-run PR-1b or PR-2. It does not rewrite `research/prophet_fusion/pr2_c2/report.json` or the PR-1b baseline-race artifact or the printed tables in `PR2_C2_REDUNDANCY.md`. It does not change C2 coefficients, the fold law, or any Prophet scoring path. The nightly remains the sole advancer of `data/us_board_ledger/**`.
