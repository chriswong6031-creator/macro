---
key: NA-SENTINEL-IS-A-TWO-LAYER-DEFECT
claim: >
  pandas NA-sentinel corruption of a ticker column is never fixed by the parse
  flag alone. It has three coupled layers: (1) the read call needs
  keep_default_na=False AND na_values=[""] — the bare flag is a regression
  because blank cells stop decoding to NaN, silently turning numeric columns to
  dtype str; (2) the parsed symbol must survive the CONSUMER's sentinel/skip
  set, which in this repo independently swallowed "NA"
  (collectors/holdings._SENTINEL_TICKERS, canada_universe._to_ticker,
  intl_universe._SKIP), so a parse-only fix is a no-op; (3) the fix opens a NEW
  hole in the NAME column, because literal "N/A"/"NULL"/"-" cells now arrive as
  strings instead of NaN and flip name-corroborated logic. pd.read_excel shares
  the identical defaults, so a read_csv-only grep under-scopes the audit.
falsifier: >
  Layer 2 is refuted for a parse site whose consumer carries no symbol sentinel
  set — check with `grep -n "_SENTINEL_TICKERS" collectors/holdings.py:51`,
  `collectors/canada_universe.py:_to_ticker`, `collectors/intl_universe.py:70`
  (_SKIP); a collector answering none of those needs only layer 1. Layer 3 is
  refuted for a name-blind consumer (`collectors/holdings.py:236` is where the
  name is normalized — a caller that never passes `name` cannot flip). Layer 1
  retires if pandas stops applying default na_values to object columns: re-run
  `tests/test_collectors_na_sentinel.py::test_bare_keep_default_na_is_a_regression`
  and see it fail. Whole record dies if #5942 is reverted with no re-breakage.
so_what: >
  Any future NA/NULL/NONE-sentinel repair budgets a consumer trace, not just a
  kwarg sweep, and asserts the exemplar END-TO-END rather than at the parse
  boundary. Detection corollary: absence of 'nan' in artifacts is NOT health —
  a scan of 3,629 committed data/etf_holdings|holdings|intl_search parquets
  found ZERO 'nan' tickers because the sentinel filters swallow the residue and
  the rows drop without trace. The finding came from the opposite direction: a
  KNOWN member missing (NA.TO absent from data/canada_search/members.parquet
  while RY/TD/BNS/BMO/CM were all present). Audit by looking for who should be
  there, never for corrupt values.
kind: constraint
verified_at: 2026-08-19
verified_by: "PR #5942 — 18 parse sites across 9 collectors; pandas 3.0.5 dtype table reproduced in tests/test_collectors_na_sentinel.py::test_bare_keep_default_na_is_a_regression; layer 2 reproduced as is_non_equity_holding('NA','Nano Labs Ltd')==True pre-fix; layer 3 reproduced as is_non_equity_holding('USD','N/A') flipping True->False; artifact scan via git cat-file --batch over 3,629 parquets"
scope:
  - "macro"
  - "collectors/"
  - "engine/ and scripts/ (35 sites still unguarded — deliberate follow-up)"
confidence: verified
---

Sibling of #5936, which fixed the identity-roster half
(`collectors/symbol_directory.py`) after an `NA` ticker froze every daily
exchange snapshot 2026-08-11 → 2026-08-19 with the adapter still reporting
status `ok`. This record covers the rest of `collectors/`.

`NA` is a live listing on both sides of the border — Nano Labs Ltd (Nasdaq)
and National Bank of Canada (`NA.TO`, TSX) — which is why the sentinel sets
that predate this discovery treated it as a missing-value literal. `"NAN"` and
`"NONE"` must STAY unconditional sentinels: they are what `str(float('nan'))`
and `str(None)` produce. `"NA"` is the only entry that is both a real listing
and never produced by stringifying a pandas missing value.
