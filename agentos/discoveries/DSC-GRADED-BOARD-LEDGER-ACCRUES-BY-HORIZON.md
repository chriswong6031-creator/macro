---
key: GRADED-BOARD-LEDGER-ACCRUES-BY-HORIZON
claim: >
  `data/us_board_ledger/retro_grades.parquet` carries ONE ROW PER (board date, ticker,
  horizon) and appends each horizon as it matures, so a board date keeps GROWING for 21
  sessions after it is published — the growth lands INSIDE already-published dates, not
  only at the tail. Measured across `6adf8b728785` (PR-2's own commit, 2026-08-14) ->
  `f960202b482a` ("engine: regime update 2026-08-18", 08:25Z): 4,077 -> 4,566 rows, 24 ->
  25 dates, entirely from H=21 maturing on 2026-07-15 (0 -> 60 rows), H=10 on 2026-07-30
  (0 -> 140) and 2026-07-31 (0 -> 132), plus the new 2026-08-07 board at H=5 (157). This
  reads like a double-collected board — row counts roughly DOUBLE on the affected dates —
  and is not one: unique tickers per date are unchanged (64/147/142 before and after) and
  only the `horizon` column differs between the old and new copies.
falsifier: >
  A vintage pair in which an affected date's UNIQUE TICKER count moves with its row count
  (that would be a re-collection, not maturation), or one in which rows appear at a
  horizon that had already matured. Check with:
  `git show <old>:data/us_board_ledger/retro_grades.parquet > /tmp/old.parquet` then
  `pd.crosstab(f['as_of'].astype(str).str.slice(0,10), f['horizon'])` on both sides —
  maturation moves cells from 0 to N in an EMPTY horizon column and leaves the others and
  the per-date ticker count fixed.
so_what: >
  Any study registered against this ledger has a frame that keeps moving for ~21 sessions
  after its last board date, so a test that rebuilds the study and asserts the REGISTERED
  numbers is a standing race that reds the fleet on data alone — with no code change and
  nothing to fix on either side. An as-of cutoff does NOT recover the vintage, because the
  maturation lands inside the registered window: cutting the live ledger at the registered
  end date 2026-07-31 yields 4,409 rows, not the registered 4,077. Freezing the input as a
  fixture is also unavailable — the G0 champion replay needs
  `data/us_board_ledger/snapshots.jsonl`, whose registered slice alone is 17.6 MB. The
  remedy is to assert registered claims against the COMMITTED artifact and to pin the
  input in the only terms that hold at every vintage: accrual-only (rows and dates may
  grow, the window's first date may not move) plus one closed-by-date invariant — the
  `unverified_pre_20260806` price_basis population, 1,335 at both vintages, which cannot
  be re-graded into another basis and so is a rewrite alarm a moving frame cannot trip.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  ci.yml main baseline 32119485639 (head 8227d096) ci-pack-9 / unrun-picks-boards, 9
  failures in tests/test_prophet_fusion_c2.py, reproduced locally in a FULL checkout;
  ledger read at 6adf8b728785 (4,077 rows / 24 dates / adjusted 1,476), at 0324e0c7a012
  and at 2a9764ba5b44 (the 07:11Z baseline that was GREEN on this pack — still 4,077),
  and live (4,566 / 25 / 1,910); per-date x horizon crosstab across the pair;
  `c2.build_c2_frame(raw=<cut at 2026-07-31>)` -> rows_in 4,409;
  `research/prophet_fusion/pr2_c2/report.json` and
  `research/prophet_fusion/pr1b_baseline_race/report.json` both carrying
  labels_receipt.rows_in 4,077 / n_dates 24 / date_range 2026-06-15..2026-07-31.
scope: [macro]
confidence: verified
---

## Detail

The suite's own opening principle is "A research artifact nobody can reproduce is an
anecdote", and `tests/test_prophet_fusion_c2.py` honoured it by re-running `c2.run_c2()`
on the real frame and asserting PR-2's registered literals against the result. That is the
right instinct pointed at the wrong input: the artifact is a `counterfactual_replay` over
a frame that was still maturing when it was registered, so the rebuild was guaranteed to
diverge from it — the only question was which nightly would mature the first horizon into
the window. It was `f960202b`, four days after PR-2 merged.

Both sides of the divergence are correct. The committed artifacts are right for their
registered vintage; the fresh run is right for today's ledger. Re-stamping the artifacts
was therefore not available: it would rewrite registered evidence (the doc's central
result is "the graded frame still holds 24 dates … 91 graded dates needed before the first
lawful fold exists"), it would require re-running PR-1b's baseline race as well — the §9.4
parity test compares two COMMITTED artifacts — and it would break again at the next
maturation.

Note the headline result is unchanged by the growth: 25 dates still cannot satisfy the
frozen §9.2 fold law (≥60 train / ≥10 test at a 21-session embargo), so `c2_fit` still
refuses and `test_real_frame_refuses_and_embeds_verbatim` passed throughout. Whether PR-2
should be RE-RUN and re-registered on the extended frame is a program decision for
`WS:PROPHET-CONDITIONAL-FUSION`, not a CI heal; nothing in this repair forecloses it.
