---
workstream: WS:PROPHET-CONDITIONAL-FUSION
session: worktree-bold-golick-373048 (CI heal only; no program work)
model: opus
ended_because: complete
mission: >
  Heal ci-pack-9 / unrun-picks-boards on main's baseline 32119485639 (head 8227d096):
  9 failures in tests/test_prophet_fusion_c2.py blocking every authority-changing PR
  through ci-gate. Adjudicate which side of the divergence was wrong before editing
  either — explicitly NOT authorised to re-stamp a registered artifact to go green.
state_before: >
  PR-2's committed report.json and PR-1b's baseline-race report.json both registered
  against a graded frame of 4,077 rows / 24 dates / 2026-06-15..2026-07-31. The suite
  re-ran c2.run_c2() on the LIVE frame and asserted those registered literals against
  the result. Green from PR-2's merge (2026-08-14) until 2026-08-18, including at the
  07:11Z baseline 2a9764ba.
changed:
  - path: "tests/test_prophet_fusion_c2.py"
    what: "Nine vintage-bound tests repointed from the live rebuild to the COMMITTED report.json via new registered_report/registered_census fixtures. Two of them (test_the_cmi_table_cells_match_report_json, test_the_what_does_x_add_table_matches_report_json) were already NAMED for the artifact and compared the doc against a fresh run instead. Added TestTheLedgerAccruesRatherThanRewrites so the removed literal-vs-rebuild assertions are replaced by a gate, not by nothing. @NEEDS_REAL_FRAME dropped from the repointed tests (they no longer read data/)."
  - path: "agentos/discoveries/DSC-GRADED-BOARD-LEDGER-ACCRUES-BY-HORIZON.md"
    what: "New landmine: the graded ledger accrues one row per (board date, ticker, horizon) as each horizon matures, so any study registered against it has a frame that moves for ~21 sessions after its last board date."
verified:
  - claim: "The full ci-pack-9 fusion step is green in a FULL checkout."
    command: "python3 -m pytest tests/test_prophet_fusion_families.py tests/test_prophet_fusion_arena.py tests/test_prophet_fusion_labels.py tests/test_prophet_fusion_race.py tests/test_prophet_fusion_c2.py -q"
    result: "265 passed in 122.39s."
  - claim: "Still green after rebasing onto fresh origin/main."
    command: "python3 -m pytest tests/test_prophet_fusion_c2.py -q"
    result: "77 passed."
  - claim: "The growth is horizon maturation, not a re-collected board."
    command: "pd.crosstab(as_of[:10], horizon) over git show 6adf8b728785:data/us_board_ledger/retro_grades.parquet vs live"
    result: "07-15 H21 0->60, 07-30 H10 0->140, 07-31 H10 0->132, new 08-07 H5 157; unique tickers per date unchanged at 64/147/142."
  - claim: "An as-of cutoff does NOT recover the registered vintage."
    command: "c2.build_c2_frame(raw=<raw cut at as_of <= 2026-07-31>).labels.receipt"
    result: "rows_in 4,409 — not the registered 4,077; the maturation lands inside the window."
  - claim: "The committed doc and the committed artifact agree, so the repointed doc tests are a real gate."
    command: "doc verdict rows vs report.json what_does_x_add rows"
    result: "3/3 verdicts match; doc 0.005 == artifact 0.00495."
  - claim: "agentos records validate."
    command: "python3 scripts/agentos.py validate"
    result: "193 records, 0 errors (8 pre-existing phantom-owns-path warnings in other records)."
do_not_redo:
  - "Do NOT re-stamp research/prophet_fusion/pr2_c2/report.json or the PR2_C2_REDUNDANCY.md tables to today's numbers. The doc's central registered result is 'the graded frame still holds 24 dates … 91 graded dates needed before the first lawful fold exists', test_the_descriptive_tier_reproduces_pr1b_section_9_4 compares two COMMITTED artifacts so PR-1b would have to be re-run too, and the next maturation breaks it again."
  - "Do NOT try to fix this with an as-of cutoff — measured, it yields 4,409 rows, not 4,077."
  - "Do NOT freeze the input as a committed fixture — the G0 champion replay needs data/us_board_ledger/snapshots.jsonl, whose registered slice alone is 17.6 MB."
  - "Do NOT diagnose this as the daily.yml double-collection class (#5865/#5870). It has that signature (rows nearly double on the affected dates) and is not it; the discriminator is that unique tickers per date do not move and only the horizon column differs."
danger_areas:
  - "Any NEW assertion in this suite that reads a registered VALUE from real_report is the same standing race and will red the fleet at the next maturation. Registered claims belong on registered_report."
  - "The frame keeps moving until ~2026-09, when the 2026-08-07 board's H=21 matures — and again with every new board date."
unverified: []
unresolved:
  - question: >
      Should PR-2 be re-run and re-registered on the extended frame (25 dates and
      growing), or does the registration stand as a frozen record of the W2 read?
    why_open: >
      A program call for WS:PROPHET-CONDITIONAL-FUSION, not a CI heal. The headline
      result is unchanged by the growth — 25 dates still cannot satisfy the frozen
      §9.2 fold law, so c2_fit still refuses — so nothing forces the move. Re-running
      PR-2 alone would also break the §9.4 parity test unless PR-1b's baseline race is
      re-run with it.
next_actions:
  - owner: WS:PROPHET-CONDITIONAL-FUSION
    action: >
      Decide the re-registration question above. Nothing in this repair forecloses a
      re-run; if it happens, the repointed tests keep passing because they read the
      artifact that the re-run would rewrite.

---

## Detail

The suite's own opening line is "A research artifact nobody can reproduce is an anecdote",
and it honoured that by re-running the study on the real frame. That is the right instinct
pointed at the wrong input: PR-2 is a `counterfactual_replay` over a frame that was still
maturing when it was registered, so the rebuild was guaranteed to diverge — the only open
question was which nightly would mature the first horizon into the window. It was
`f960202b482a` ("engine: regime update 2026-08-18", 08:25Z), four days after PR-2 merged
and roughly 75 minutes after the 07:11Z baseline that was still green on this pack.

Both sides of the divergence are correct, which is why neither could be edited: the
committed artifacts are right for their registered vintage, the fresh run is right for
today's ledger. The repair moves the ASSERTION to the artifact rather than moving either
number, and pins the input in the only terms that survive maturation.
