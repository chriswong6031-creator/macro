# China full-universe masterplan — from a 1,510-name sample to the whole board

**Status:** W0 SHIPPED (whole-board 涨跌家数). W1–W3 scoped, not started. W-DEPTH (§7)
costed 2026-08-05, awaiting operator ratification.
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
  `china_search` or the heatmap builders. Re-checked 2026-08-05: still true.

---

## §7 W-DEPTH — search-universe DEPTH (open; operator ratification required)

**Status:** costed, NOT shipped. **Opened:** 2026-08-05.
**Origin:** operator, 2026-08-04 — 湖南白银/002716.SZ had no Prophet picks; a THS
metals/nonferrous board sweep found **66 clean non-ST names ≥30亿 outside the
universe**, several with turnover far above the 0.5亿 ADV floor (东方锆业 18.3亿/day,
晓程科技 23.8亿/day).

Distinct from W1/W2: those widen the *breadth count* and are explicitly told to
ship a NEW store (§3). This one asks whether the **search panel itself** — the
thing `build_china_library`, the reversal sleeve and the Prophet board all read —
should reach deeper. It cannot be answered on a new store, so §0 gate 6 binds:
**a written before/after N for every consumer.** That is what follows.

### §7.1 Unit costs (measured, not modelled)

CI run **30905719412** (`asia-close.yml`, 2026-08-04, self-hosted Studio). The
`asia` job ran **99.1 min of its 165 min cap**. These collectors are `china*`, so
they land on the **asia lane, not the ~67 min render path** — the render budget is
the wrong meter for this decision.

| stage | measured | per name |
|---|---|---|
| `china_universe` collect | 216.9 s / 1,518 | 0.143 s |
| `china_stocks` collect | 213.3 s / 1,592 | 0.134 s |
| `china_stocks_raw` collect | 209.4 s / 1,592 | 0.132 s |
| `build_china_library` per-name detail loop | 1,096.6 s / 1,524 | **0.720 s** |
| **total, universe-proportional** | | **1.128 s/name/night** |
| *(+ `context drips + tushare health` 705.5 s, if fully proportional)* | | *(1.591 s upper bound)* |

Bytes: `data/china_stocks` + `_raw` are **git-tracked** (1,679 + 1,668 files,
452 MB) — the cost is not `closes.parquet`. Per name in the rank-801–2500 band:
**255 KB** working tree, **7.2 KB** in `china_search/closes.parquet`.

Recurring pack cost is the real number. A sampled 20 names showed **12.9 unique
blob revisions per name per 14 days** (~250 KB each, parquet rewritten whole);
`git pack-objects` over 407 real blobs measured **52.5 MB → 7.4 MB = 7.1× delta
compression**. Net **16.2 MB/name/year of pack growth**. The existing 1,518 names
therefore commit the repo to **~24.5 GB/yr** on their own; the pack is 26.65 GiB
today and `data/china_stocks` is only 7 weeks old (first commit 2026-06-14).

### §7.2 Reach today (live Sina walk, 2026-08-05: 4,258 names ≥30亿)

| cap rank | names | already in panel |
|---|---|---|
| 1–800 | 800 | 788 (98.5%) |
| 801–1500 | 700 | 330 (47.1%) |
| 1501–2000 | 500 | 225 (45.0%) |
| 2001–2500 | 500 | 139 (27.8%) |
| 2501–4258 | 1,758 | 36 (2.0%) |

800th = 243.5亿, 1500th = 124.0亿, 2000th = 88.2亿. History depth is **not** a
constraint: 96–99% of already-collected names in *every* band carry ≥300 bars.

**Baseline note — cost everything against 1,713, not 1,518.** The committed panel
is 1,518, but that file predates #4577. With the authoritative CSIndex lists
(fetched 2026-08-05), `top-800 ∪ CSI 300 ∪ CSI 1000` = **1,713**, so #4577 alone
moves the panel **+195** the next time `china_universe` runs. Every figure below
is net of that.

### §7.3 The options, costed

Set arithmetic is measured against the authoritative constituent lists, not
estimated. CSI 2000 ∩ CSI 300 = **0**, ∩ CSI 1000 = **0**, ∩ Sina top-800 = **6** —
the index's published exclusion of CSI 800 + CSI 1000 holds empirically.

| option | +names | panel | asia lane | (upper) | tree | pack/yr |
|---|---|---|---|---|---|---|
| (a) `size` 800→1200 | +206 | 1,919 | +3.9 m | +5.5 m | +53 MB | +3.3 GB |
| (a) `size` 800→1500 | +297 | 2,010 | +5.6 m | +7.9 m | +76 MB | +4.8 GB |
| (a) `size` 800→2000 | +496 | 2,209 | +9.3 m | +13.2 m | +127 MB | +8.0 GB |
| (b) ∪ CSI 2000 | **+1,994** | 3,707 | **+37.5 m** | +52.9 m | +510 MB | **+32.2 GB** |
| (c) +66 theme `extra_tickers` | +66 | 1,779 | +1.2 m | +1.8 m | +17 MB | +1.1 GB |
| (d) as-is | 0 | 1,713 | — | — | — | — |

(b) lands at the very top of its plausible range: 1,994 of CSI 2000's 2,000
mappable members are net-new. It is the only option that cannot fit the asia lane's
65.9 min of slack alongside the lane's own known variance.

### §7.4 #4577 already lands this era break tonight (measured, small, unstamped)

The +195 CSI 1000 members #4577 restores are *mid-caps below the Sina top-800* —
the same cohort direction as option (a), at ~2/3 of (a)@1500's size. Removing 195
names of exactly that shape from the live panel and recomputing (5 trials):

| | median rev_z shift | quintile Jaccard | top-16 retained |
|---|---|---|---|
| #4577's +195 | **−0.029** (range −0.025…−0.037, all 5 negative) | 0.931 | 13/16 |

So the discontinuity this section warns about for option (a) is **already scheduled
for tonight's asia-close**, at about 1/6 the magnitude of the 800→1,518 step. It is
small enough not to be an incident and one-directional enough not to be noise.
Record it: whoever later finds a step in `cn_reversal_watch_v1` continuity dated
2026-08-05/06 should find this line rather than hunt a phantom.

### §7.5 The consumer audit — this is the finding, not the cost

**A cap-ordered deepening re-bases the reversal signal for every name already
covered.** `engine.china_reversal` scores `rev_z` as a within-*sector* z of the
3-month relative dip, and `deepest_quintile` as `sector_rank <= sector_n // 5`.
Both are functions of who else is in the sector. Recomputing `reversal_watch` on
the committed panel at varying widths (`research/china_universe_depth/`):

| panel | median rev_z shift vs prev | quintile Jaccard | top-16 watch overlap |
|---|---|---|---|
| 300 → 400 | −0.026 | 0.873 | 9/16 |
| 400 → 600 | −0.087 | 0.813 | 10/16 |
| 600 → 800 | −0.059 | 0.887 | 12/16 |
| 800 → 1,518 | **−0.175** | 0.806 | **5/16** |

The count is not what drives it — the **cohort direction** is. Same 600 names
removed, two ways:

| | median shift | median \|shift\| | Jaccard | top-16 |
|---|---|---|---|---|
| drop 600 **smallest-cap** (cap-ordered) | **+0.154** | 0.155 | 0.840 | 6/16 |
| drop 600 **random** | −0.005 | 0.044 | 0.846 | 10/16 |

Cap-ordered is one-directional, so it does not average out; random is noise.
At the 66-name scale the effect is gone entirely (median |shift| **0.014**,
Jaccard **0.969**, 14/16 retained).

This matters because `data/china_standout_track/board.parquet` has been accruing
**`cn_reversal_watch_v1` since 2026-06-30** (1,167 rows, 507 tickers). An
unstamped cap-ordered widening silently re-bases the input under a live forward
ledger — the era-break shape, not a cost question.

Two more consumer facts:

- **`china_board_rank` caps are fixed** — `FEATURED_CAP = 24`, `SECTOR_CAP = 4`.
  Lanes are lossless, so a new name always gets a row, but a wider universe buys
  *competition for 24 slots*, not more featured slots. And `adv is None` →
  `liquidity_unknown` → `more_actionable`: a name is not featurable until its
  per-name OHLCV parquet exists, i.e. one full backfill night later.
- **`enrich_per_run: 120` gates the sector label, and sector is the reversal
  grouping key.** Unenriched names fall back to the `A-share` catch-all. Nights
  in that bucket: (c) 0.6 · (a)@1500 3.2 · (a)@2000 5.5 · (b) **15.8**. §4 already
  flagged this in miniature — it is live *today*: 9 names rank inside the fake
  `A-share` sector against `sector_n=9`, one of them flagged `deepest_quintile`.

### §7.6 Recommendation (operator ratifies)

**Ship (c) now; hold (a) behind an era stamp; reject (b).**

- **(c)** is the only option with *zero* era-break risk (measured), costs
  **+1.2 min/night** on a lane with 65.9 min of slack, clears the enrich budget in
  one night, and reaches all 66 measured names — including 002167.SZ and
  300139.SZ, the two highest-turnover ones, which (a)@1500 partly misses (ranks
  1,447 and 1,522). It has a real weakness worth saying plainly: it fixes only the
  themes someone thought to sweep. This one sweep was metals.
- **(a)@1500** is the affordable structural answer (**+5.6 min, +4.8 GB/yr** net of
  #4577) but is a **cap-ordered** move, so it must land with the
  `cn_reversal_watch_v1` ledger era-stamped and the discontinuity disclosed — not
  as a config bump. §7.4 shows what that stamp should look like: #4577's own +195
  is the same move at −0.029, and it is going out unstamped tonight.
- **(b)** costs **+37.5 min/night** on a lane whose cap has killed runs before —
  more than half its 65.9 min of slack, before the lane's own variance. It adds
  **+32.2 GB/yr** of pack growth against a 26.65 GiB pack, spends 15.8 nights with
  wrong sectors feeding the reversal grouping, and buys the least-liquid tier.
  Reject on cost.
- **(d)** leaves a gap the operator has now documented twice. Not recommended
  alone, but the honest-disclosure half of (d) should ship *with* (c) regardless:
  the panel's reach is a stated denominator, per §0 gate 1.

### §7.7 Two defects found while measuring (not fixed here)

1. **The CSIndex fallback is silent and lossy, and it fired TWICE today** — in two
   independent probes, both on `000300`, both returning `src=index_stock_cons`
   (the legacy endpoint) at **288 unique of 300**. The second probe recovered only
   because the harness retried; `_index_rows` itself does not retry, it just
   `log.warning`s and returns the short list. So #4577 fixed the *source* while
   leaving a degraded path that fires on ordinary CSIndex flakiness and shrinks
   the universe by ~12 names without an alarm — and a name dropping out freezes its
   `closes` column and marks `dropped.parquet`. This is not hypothetical: two
   observations in one afternoon. (b) would add a third fetch on that same host.
2. **`ak.index_stock_cons_csindex` calls `requests.get(url)` with no timeout.**
   A probe here hung **742 s** before erroring. Nothing bounds a CSIndex stall
   inside `china_universe` except the job cap.

Note for whoever reads §7.2 against a stale panel: `002716.SZ` is absent from the
committed `members.parquet` only because it entered `extra_tickers` in #4577
(merged 2026-08-05 00:27) *after* the last `china_search` commit (2026-08-04
04:20). yfinance serves it fine. Tonight's asia-close picks it up. Not a defect.
