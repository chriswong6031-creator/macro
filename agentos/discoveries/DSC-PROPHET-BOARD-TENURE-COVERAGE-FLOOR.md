---
key: PROPHET-BOARD-TENURE-COVERAGE-FLOOR
claim: >
  A board fossil that under-records any name-visible lane makes absence-proof tenure
  claims unsound for that market: a candidate demoted to an unfossiled-but-visible
  shelf and later returning reads as exit+re-add in the canonical record, minting a
  confidently WRONG "continuously since" date rather than a null. Measured: CN's
  board.parquet persisted only the featured lane while china_stocks rendered 106
  more_actionable cards (30/237 tickers show the gap-and-return shape); HK's ledger
  deliberately excludes its name-visible leaders/laggards strips; CA's excludes its
  laggards grid.
falsifier: >
  For a given market, prove every lane whose names render readably on the shipped
  board page is persisted in that market's fossil for the full claim window: compare
  the template's name-rendering loops (grep -n "setups.laggards\|leaders-strip\|for r
  in" templates/canada.html.j2 — laggards loop at templates/canada.html.j2:2517) with
  the fossil's distinct lane/group values (python3 -c "import pandas;
  print(pandas.read_parquet('data/board_ledger/ca_board.parquet')['group'].value_counts())").
  If every name-visible lane appears in the fossil, absence-proofs there are sound
  with no floor and this record does not apply to that market.
so_what: >
  Any tenure/membership feature over a board fossil must (a) trace name-visible lanes
  from the TEMPLATES, never from the fossil's own lane inventory; (b) either extend
  the existing canonical writer to persist the missing lanes going forward (under a
  distinct definition/group so grading-authority selection is untouched) or refuse
  absence-proofs anchored before the dynamic full-coverage floor (first date the
  extended lanes exist), shipping honest nulls until coverage accrues. Applied in
  engine/prophet_board_since.py (#6719): CN floor via <definition>_more_actionable
  rows; HK/CA requires_full_coverage=True with no writer extension because persisting
  display-tier lanes into board_ledger corrupts Spearman rank-IC grading (2026-08-03
  finding in scripts/build_hk_library.py) — lifting HK/CA nulls needs a separately
  authorized rank-authority-safe coverage extension.
kind: data
verified_at: 2026-09-01
verified_by: >
  Adversarial review of PR #6719 head ca1fe0828edb: pandas census of
  data/china_standout_track/board.parquet (lane values featured/reversal_watch/null
  only; 30/237 tickers with single-observation gap-and-return),
  data/board_ledger/{hk,ca}_board.parquet group counters (entry_open/setting_up/watch
  only), template traces templates/hk.html.j2:4341,4459,4489 and
  templates/canada.html.j2:2387,2516-2520 rendering leaders/laggards names, and
  scripts/build_hk_library.py's documented rank-IC exclusion. Repair verified by the
  round-3 review on head becf409188ce (real-fossil stamps: HK/CA all-None, US 40/40).
scope:
  - macro
  - engine/prophet_board_since.py
  - data/china_standout_track/board.parquet
  - data/board_ledger/
  - WS:PROPHET-CANDIDATE-ADDED-DATE
confidence: verified
---

# Board tenure claims are only as sound as the fossil's lane coverage

Retrospective membership truth requires the published record to cover every lane a
user can see a name in. Where it does not, honest nulls with a forward coverage
floor beat mostly-right dates whose error cases are unknowable. Same epistemic
family as GD1C-PIT-MEMBERSHIP-PREHISTORY-ABSENT (retrospective "added" fields
cannot establish PIT cohorts).
