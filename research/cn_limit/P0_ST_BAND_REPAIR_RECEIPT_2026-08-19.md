# P0-ST Repair Receipt — Main-Board Risk-Warning Band ±5% → ±10% (effective 2026-07-06)

Date: 2026-08-19 · Wave: P0-ST · Program: `WS:CN-LIMIT-ALPHA`

## 1. Mission + authority

Sol's P0-ST ruling under CN-LIMIT R6 commissioned a repair to the main-board (SSE/SZSE)
risk-warning (ST/\*ST) price-limit band: both exchanges' 2026 trading-rules revisions
widened it from ±5% to ±10%, effective **2026-07-06**. This wave lands under PR #6009's
canonical package (`research/cn_limit/CN_LIMIT_R6_*`), and this file plus the code/config/
test changes it documents are **strictly additive** — the six sealed R6 artifacts are
untouched by this wave.

## 2. Official primary-source receipts

**SSE.** Official release, 2026-04-24:
<https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20260424_10816474.shtml> —
《上海证券交易所交易规则（2026年修订）》. Exact sentence:

> "将主板风险警示股票价格涨跌幅限制比例由5%调整为10%。"

Effective date, same release: "《交易规则》于2026年7月6日起正式实施".

**SZSE.** 《深圳证券交易所交易规则（2026年修订）》, notice 深证上〔2026〕551号 (published
2026-04-24), official PDF:
<https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf>
(SHA-256 `9b66f8b0db70f84a25ef1ccb4ee2351001724e408117552d75f6d8993483c586`).

Article 3.3.13:

> "主板股票的价格涨跌幅限制比例为 10%，创业板股票的价格涨跌幅限制比例为 20%"

— no risk-warning carve-out remains (the superseded 2023 rules carved ST names to 5%).

Article 10.9:

> "本规则自 2026 年 7 月 6 日起施行"

— superseding the 2023-02-17 edition.

Both venues: announced 2026-04-24, effective 2026-07-06. The main-board risk-warning band
now equals the ordinary main-board band (10%); the ST/\*ST series stays a distinct
classification because the status and its other trading-mechanism constraints (e.g.
disclosure, delisting-risk labeling) are unaffected by the width change.

## 3. Definition change + definition hash

**Old cell** (`engine/china_microstructure.py::limit_width_for_date`, main-board tail):
unconditional

```python
if is_st:
    return 0.05
return 0.10
```

**New cell** (era-dated on the new `MAIN_ST_BAND_WIDE_DATE = pd.Timestamp("2026-07-06")`
constant):

```python
if is_st:
    return 0.05 if trade_date < MAIN_ST_BAND_WIDE_DATE else 0.10
return 0.10
```

**Coincidence note.** `MAIN_ST_BAND_WIDE_DATE` (2026-07-06, the exchanges' rule effective
date) is numerically identical to the pre-existing `ST_STORE_COVERAGE_DATE` (2026-07-06,
the first date our `data/china_st/` ST-membership store covers). These are two unrelated
facts that happen to share a calendar date — one is a rulebook date, the other is a
data-coverage floor for our own collector. They must not be merged into one constant or
read as causally related (an R6-registered trap). Both constants are kept separate in code
with the coincidence called out at each site.

**Definition hash** (sha256 over `inspect.getsource(limit_width_for_date)` concatenated
with the raw bytes of `config/cn_limit_rules.yml`), as measured by
`research/cn_limit/p0_st_band_replay.py` at repo HEAD `354f8cd6cf9cd645b8903e9c2ad6cc5f9a071c9e`:

```
ff121335bd50cd81cff1b4ebb2c2b4181cb5727f3bfbba76571b2c18d00c01b8
```

(Two consecutive runs of the replay script produced byte-identical JSON receipts and this
same hash — see §5.)

## 4. Exact affected-row census

Measured by `p0_st_band_replay.py` against the live data stores in this worktree:

| Metric | Value |
|---|---|
| `data/china_microstructure/limit_events.parquet` total rows | 60,589 |
| Rows with `limit_width == 5.0` (stale-5% rows) | **0** |
| `limit_events` date range | 2011-01-05 → 2026-08-19 |
| `data/china_st/st_snapshot.parquet` row count | 100 |
| `st_snapshot` `asof` date(s) | 2026-07-06 |
| `data/china_st/st_history.parquet` date(s) covered | 2026-07-06 |
| Affected universe (st_snapshot ∩ raw-store names, main board only) | `['600079.SS']` |
| Affected-universe matches pre-registered expectation | **True** |

Zero `limit_width == 5.0` rows exist in the store **today, before this wave's code change**,
because the detection-level ST gate (`ST_STORE_COVERAGE_DATE`) never fires before
2026-07-06 in the first place — see §8. No stale 5%-width rows need correcting.

## 5. Old-vs-new comparison + bounded replay result

`p0_st_band_replay.py` replays `engine.china_microstructure._detect_limit_events` for the
one affected name, `600079.SS`, over the window `2026-07-06 → 2026-08-19` (its last store
bar), under two arms:

- **ARM current** — the width function as shipped in this PR (era-dated, 10% on/after
  2026-07-06).
- **ARM superseded** — the same detector with `limit_width_for_date` monkeypatched to
  return 0.05 unconditionally for `(board == "main", is_st=True)` — i.e. the law this wave
  replaces — restored immediately after the run.

Result for `600079.SS` (33 scored sessions in the window):

| | current arm | superseded arm |
|---|---|---|
| sealed/touched events produced | 0 | 0 |
| `current_only` events | 0 | — |
| `superseded_only` events | 0 | — |
| event sets identical | **True** | |

The per-session transparency table (independent of the detector, computed directly from
OHLC vs. each width) confirms why: the largest single-session move against the previous
close across all 33 sessions was **3.08%** — nowhere near either the 5% or the 10% band —
so `would_touch` is `False` at both widths on every session, and no ex-div suspect gap
(`|open − prev_close| / prev_close > width × 1.5`) fired at either width either.

**Diff is empty ⇒ zero store corrections are required.** This is a *measured*, not
assumed, result: correction discipline for this wave is additive-only (nothing in
`data/` is rewritten — the replay is read-only), and the empty diff is the proof that no
correction is needed, not merely an excuse for not attempting one.

Running the replay script twice produced byte-identical JSON receipts (`cmp` clean) with
the same definition hash, satisfying the determinism gate.

## 6. Downstream parity

Every production consumer of the width function or the detector was enumerated and is
either unaffected or automatically inherits the fix (no separate patch needed):

- `engine/china_microstructure.py` — `_detect_limit_events` (event detection) and
  `name_packet` (`limit_width_for_date` call for the packet's live width) both call the
  now-era-dated function directly.
- `scripts/build_china_library.py` — the V3 R3 chase/relay-position helper
  `_limit_close_bars` imports `limit_width_for_date as _limit_width` and resolves each
  bar's band through it; it inherits the era-dated width with no code change.
- `scripts/backfill_china_limit_tape.py` — calls `_detect_limit_events` directly (the
  historical backfill path); inherits the fix identically to the nightly incremental path.

Measured zero-delta: none of these consumers require a separate patch because all of them
resolve the width through the single owner function this wave changed, and the replay in
§5 already proves the change produces zero corrections for the only affected name in the
current data window.

## 7. Gaps, honestly

- `st_snapshot.parquet`'s `asof` is frozen at 2026-07-06 (a single collector snapshot, not
  a rolling feed). Widening or refreshing that cadence is out of scope for this wave —
  it is a separate collector concern, not a width-law concern.
- The pre-2026-07-06 ST-width detection blindness (§8, `st_flags_current_only`) is
  **unchanged** by this wave: dates before the store's coverage floor still take the
  ordinary (non-ST) board width at detection time, regardless of the width law's own
  era-dating.
- The raw store (`data/china_stocks_raw/`) is the ~1,848-name survivor slice as of this
  session; the census and affected-universe count in §4 bind to that universe only —
  delisted/suspended names outside the raw store are not represented.

## 8. Boundary semantics

Because `ST_STORE_COVERAGE_DATE` (the ST-membership detection floor) and
`MAIN_ST_BAND_WIDE_DATE` (the rule's own effective date) are numerically the same date
(2026-07-06), the store-coverage gate now coincides exactly with the wide (10%) era. This
means detection-level ST width application can **never** apply the historical 5% band
today: bars before 2026-07-06 are undetected as ST at all (they fall back to the ordinary
board width), and bars on/after 2026-07-06 that ARE detected as ST already sit inside the
±10% era. That is a property of the two dates' coincidence and the width function's own
era-dating working together — **by law, not by luck**: `limit_width_for_date` still
correctly returns 0.05 for any *direct* caller passing a pre-2026-07-06 date with
`is_st=True` (see `TestLimitWidthForDate` boundary tests); it is only the *detector's*
combination with `ST_STORE_COVERAGE_DATE` that makes the 5% branch unreachable through the
production event-detection path as of today.
