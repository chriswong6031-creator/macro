# China full-universe masterplan — from a 1,510-name sample to the whole board

**Status:** W0 SHIPPED (whole-board 涨跌家数). W1–W3 scoped, not started.
**Owner:** main session. **Opened:** 2026-07-26.
**Origin:** operator, 2026-07-26 — *"china should have like 5000 companies, but this
advancer decliner is showing only around 1500."*

---

## §0 ACCEPTANCE GATES (not done unless)

Every wave below is **not done** unless all of these hold. These are gates, not
aspirations — a wave that cannot meet them gets descoped, not waved through.

1. **The denominator is stated wherever a count is shown.** A 涨跌家数 with an
   unstated universe is the defect this program exists to close. Any surface that
   prints adv/dec names what it counted, in plain words, in both languages.
2. **One sentence, one universe.** A panel may not mix a whole-board count with a
   sample-derived median in the same read. If a metric can't be computed on the
   stated universe, it moves to its own labelled block or it doesn't ship.
3. **Fresh end-to-end happy path, zero manual workarounds.** Nightly collect →
   build → render → live page, with no hand-run step and no reload-to-fix race.
4. **Per-step visual crops in the PR body** — light + dark, EN + 中文, at the
   default timeframe and at one non-default timeframe (the fallback path).
5. **Stale degrades to honest, never to wrong.** Every feed carries a session key;
   a feed that stops advancing must fall back to a self-consistent narrower read
   and say so — never print a stale board count beside a fresh map.
6. **No silent universe change downstream.** `china_search` is the panel for
   `build_china_library`, the reversal sleeve, `tushare_history._panel_tickers`
   and the `china_validation` harness. Any wave that widens it lands a written
   before/after N for every consumer, or it ships on a NEW store and leaves
   `china_search` alone. Prereg'd/frozen studies (`rrr.parquet`) are untouchable.
7. **Render budget respected** (~67 min, 4-core-bound). Any wave adding >2 min to
   the render path moves its compute off-path with the artifact to R2.

---

## §1 The measurement (2026-07-24 session, all figures verified)

| | |
|---|---|
| A-shares listed | **5,526** — SZ 2,889 / SH 2,308 / **BJ 329** |
| 沪深 that traded | **5,197** |
| Heatmap tiles | **1,510** |
| Tile coverage, market cap | **82.3%** (99.7 of 121.2 trn CNY) |
| Tile coverage, daily turnover | **72.8%** |
| Excluded names | 4,017 — median cap **38亿** (~$530M) |

Tile universe = Sina top-800 by market cap ∪ CSI 300 ∪ CSI 1000 ∪ 7 config extras
(`config.yml` `china.search_universe`), deduped, with 北交所 excluded at
`collectors/china_universe.py:_to_ticker`.

**The ratio was never the problem.** Measured the same session:

| | tile sample (1,510) | whole board (5,197) |
|---|---|---|
| % advancing | 10.3% | **10.28%** |
| median move | −2.96% | **−2.81%** |
| adv / dec | 154 / 1,346 | **534 / 4,631** |

A cap-quintile split of the sample (19.9% → 11.9% → 9.3% → 5.6% → 4.6% up, largest
to smallest) predicted the tail would drag the reading lower. It did not — the
whole-board print landed on the sample's number. **Record this: the sample was
representative, and only the COUNT was misleading.** The fix was therefore a
labelling + denominator fix, not a data-coverage fix. Do not let a future wave
re-argue this from the quintile gradient alone.

---

## §2 W0 — whole-board 涨跌家数 (SHIPPED 2026-07-26)

`collectors/china_board_breadth.py` → `data/china_board_breadth/breadth.parquet`,
one row per session: `n / adv / dec / flat / pct_up / med_pct / source`.

- **Primary:** Tushare `daily` — whole board in one `trade_date=` call, 120积分,
  inside the ¥500/5000积分 tier. Exact session date.
- **Fallback:** Sina `Market_Center.getHQNodeData` node=hs_a, ~65 pages, keyless.
  Session date from the 上证指数 quote line. Eastmoney push2
  (`ak.stock_zh_a_spot_em`) is **not usable** — it resets the connection from a
  non-CN IP, the failure that bought this repo its Tushare token.
- **Scope:** 沪深 only (operator call, 2026-07-26). 北交所 excluded — thinly traded,
  would drag the reading on very low volume.
- **Convention:** 涨/跌/平 on strict zero, matching 东方财富 / 同花顺, because the
  whole point of the number is that a user can cross-check it.
- **Gate:** `engine.market_heatmap._board_breadth_block` emits the block only when
  its date equals the map's own `asof`. Stale, malformed, or non-China → the
  front-end counts tiles and the card says `本图样本 · 1,510 只`.
- **Surfaces:** breadth card, map status strip, and the market-pulse sentence
  (% up **and** median both from the board, so one sentence describes one universe).
  1D only — 涨跌家数 is a daily count by definition and the feed has no history.

Also closed here: the status strip and the breadth card used different dead-bands
(strict zero vs ±0.05%) and printed adv/dec pairs a couple of names apart for the
same timeframe on the same screen. Both now use ±0.05% on the tile path.

---

## §3 W1 — whole-board breadth HISTORY (next)

W0 is 1D-only because there is no board history. To carry 1W/1M/3M breadth at
whole-board scale we need a close panel for ~5,200 names.

- Tushare `daily` + `adj_factor`, whole board per trade date: ~250 calls for 1y,
  ~1,220 for 5y, against a 500/min lane — minutes, not hours.
- **Do not** grow `data/china_search/closes.parquet` for this. It is 11.4MB
  committed for 1,588 columns; at 5,500 columns it is ~40MB and growing, breaking
  its own "committed — small" contract. New store, R2-backed (§0 gate 7).
- Gate 6 applies hard: this is a NEW store. `china_search` does not move.

## §4 W2 — the tile map at board scale

The expensive wave, and the one to descope first if anything slips.

- **Payload:** 253 bytes/tile → ~1.4MB JSON at 5,200 tiles (from 356KB). Needs
  measurement against the blocking-round-trip budget before it ships.
- **Rendering:** the US map runs 503 tiles; CN runs 1,510. At 5,200 the bottom
  quintile is sub-pixel at any normal viewport. A cap-tier filter
  (全部 / 沪深300 / 中证1000 / 全市场) is the likely answer — the map stays legible
  and the *count* stays whole-board regardless of the filter.
- **Sector classification:** yfinance `get_info` at `enrich_per_run: 120`/night
  = ~33 nights to classify 4,000 new names. Tushare `stock_basic` does the whole
  board in one call but in 申万 taxonomy — mixing it with the existing yfinance
  sectors needs one deliberate mapping, not a merge.
- 14 tiles already sit in an `A-share` catch-all sector today; fix that first, it
  is the same defect in miniature.

## §5 W3 — the same audit for HK / Canada / US

W0 names the denominator on the China map only, because China is the only market
where both denominators have been measured. HK, Canada and the US maps make the
same implicit whole-board claim and have not been checked. One session, three
measurements, then either a scope line or a documented "this IS the board".

---

## §6 Standing notes

- The gauntlet does not apply here. This is context/display infrastructure — a
  count of what happened today, no forward claim, nothing scored. It ships
  display-tier freely (CLAUDE.md §Epistemics).
- `research/DO_NOT_REBUILD.md` carries no kill against a China universe
  expansion as of 2026-07-26; `docs/ACTIVE_BUILD_MAP.md` shows no open lane on
  `china_search` or the heatmap builders.
