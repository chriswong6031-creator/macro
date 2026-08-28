---
key: STAGE-STALE-NAMES-ARE-FETCH-UNIVERSE-DRIFT
claim: >
  The frozen names polluting Stage Analysis are NOT a price-store precedence bug —
  they are collector fetch-universe drift, and the existing freshness tripwire is
  structurally blind to them. `engine/stage_analysis.py::build_universe()` does
  `for p in ohlcv_dir.glob("*.parquet"): _add(p.stem, "ohlcv")`, so it classifies
  every ticker whose file was EVER written and never forgets one, while
  `scripts/fetch_basket_ohlcv.py::_resolve_universe()` maintains only
  `membership ∪ finviz(idx_ndx, idx_rut)` (2,603 names) and the finviz screener JSONs
  are re-pulled nightly — so index reconstitution silently shrinks the maintained set
  and a dropped name's parquet freezes forever while Stage keeps reading it.
  Measured 2026-08-20 over all 2,782 files in `data/baskets/ohlcv/`: 183 stale,
  and the separation is near-perfect — 2,599 of 2,599 FRESH files are inside the
  fetch universe, 179 of 183 STALE files are OUTSIDE it. The 2026-07-10 cluster is
  110 files on one day (plus 35 on 2026-07-21), far too many to be simultaneous
  delistings. Only 4 stale files are inside the universe: BLD (genuinely delisted
  2026-07-01, correctly disclosed), EA (a real broken per-member pull), and WBS/AVB
  (one session of ordinary jitter). The blindness is the second half:
  `check_membership_staleness()` censuses only `_membership_tickers(active_only=True)`
  — 702 names — and never looks at the finviz-derived universe or at orphan files, so
  `data/quality/basket_ohlcv_freshness.json` reported `n_stale: 1` while 179 files
  sat frozen. The competing hypothesis (a stale `baskets/ohlcv` shadowing a current
  `data/stocks` fallback in `_load_prices`) is FALSIFIED: `data/stocks/<TK>.parquet`
  does not exist for any of the 9 affected names, and across the 241 tickers present
  in both stores there are ZERO cases where `stocks` is fresher than `ohlcv`.
falsifier: >
  Rebuild the collector's own universe and cross it against file recency:
  import `_resolve_universe` from `scripts/fetch_basket_ohlcv.py`, take
  `max(index)` of every `data/baskets/ohlcv/*.parquet`, and tabulate stale-vs-fresh
  against membership. If a material share of FRESH files sits outside the universe,
  or a material share of STALE files sits inside it, the drift explanation is wrong.
  For the falsified sibling: `python3 -c "from engine.stage_analysis import _load_prices;
  from pathlib import Path; print(_load_prices('SILA', Path('data'))[0].index.max())"`
  alongside a direct read of both stores — if `data/stocks/SILA.parquet` exists and is
  fresher, precedence WAS the mechanism.
so_what: >
  Do not "fix" stale Stage names by changing `_load_prices` store precedence — it
  would fix nothing, because the fallback store has no file for the affected names
  and is a 242-name large-cap subset. The cure is upstream: give a ticker that leaves
  the fetch universe an explicit disposition (keep fetching it, or mark it inactive so
  `build_universe()` stops treating it as live), and widen the staleness census past
  the 702-name membership subset to the actual store it is responsible for. Until that
  lands, Wave 8's `stage_current` admission boundary is CONTAINMENT only: the frozen
  files keep accumulating and the population receipt is the instrument that shows it.
kind: data
verified_at: 2026-08-20
verified_by: "PR #6156; research/STAGE_OBSERVATION_TRUTH_WAVE8.md §9; census of all 2,782 data/baskets/ohlcv/*.parquet"
scope:
  - macro
  - engine/stage_analysis.py
  - scripts/fetch_basket_ohlcv.py
  - data/baskets/ohlcv/**
  - data/quality/basket_ohlcv_freshness.json
confidence: verified
---

# Stage's stale names are fetch-universe drift, not store precedence

See `research/STAGE_OBSERVATION_TRUTH_WAVE8.md` §9 for the full measurement tables,
including the per-ticker dispositions for SILA, EML, COOK, AHR, TBRG, TMCI, LPRO,
MRDN and TMHC, and the adjusted-basis comparison across the 241 both-store tickers
(median close ratio exactly 1.000000 for 232 of them; Pearson ≥0.9999982 for every
name — so the two stores are the same adjusted basis, which makes the precedence
question moot rather than merely unnecessary).
