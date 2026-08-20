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
with the raw bytes of `config/cn_limit_rules.yml`), as measured on the P0-ST working tree
(base `354f8cd6cf9cd645b8903e9c2ad6cc5f9a071c9e` — `git merge-base origin/main HEAD`,
stable across this wave's own amendment commits; see the replay script's provenance note
for why the sha is informational and this hash, not any git sha, is the binding
fingerprint) by `research/cn_limit/p0_st_band_replay.py`:

```
e0c70f39f62e7639355128644f872c4e992699524bbdca775f24f1e1ad45e4a4
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

Zero `limit_width == 5.0` rows exist in the store **today, even under the pre-fix code**.
This zero is **empirical, not structural** — the detection-level ST gate
(`ST_STORE_COVERAGE_DATE`) DOES fire on/after 2026-07-06 (that is the whole point of the
gate), so the pre-fix unconditional-5% code WOULD have written `limit_width == 5.0` rows
had a qualifying sealed/touched event actually occurred for a detected ST main-board name
on or after that date. None did: the sole such name (`600079.SS`, §5) simply never moved
far enough to trigger one in the window measured. No stale 5%-width rows need correcting,
but that is a fact about what the tape happened to do, not a guarantee the mechanism
could not have produced one.

## 5. Old-vs-new comparison + bounded replay result

`p0_st_band_replay.py` replays `engine.china_microstructure._detect_limit_events` for the
one affected name, `600079.SS`, over the window `2026-07-06 → 2026-08-19` (its last store
bar), under two arms:

- **ARM current** — the width function as shipped in this PR (era-dated, 10% on/after
  2026-07-06).
- **ARM superseded** — the same detector with `limit_width_for_date` monkeypatched to
  return 0.05 unconditionally for `(board == "main", is_st=True)` — i.e. the law this wave
  replaces — restored immediately after the run.

Both arms are called with a `start_date` buffered a full calendar week before the window
(`2026-06-29`, not `2026-07-06` itself) and their returned events are then filtered back
down to the window: `_detect_limit_events` applies its own `start_date` filter to the
frame BEFORE computing the `prev_close` shift, so passing the window's own first day
directly would leave that day's `prev_close` `NaN` and silently drop it from scoring —
32 of 33 sessions, not 33. The buffer preserves a real prior close for 2026-07-06 itself;
the replay separately proves the fix (`detector_scored_sessions == 33`, matching the
independent per-session table below) rather than asserting it.

Result for `600079.SS` (**33 of 33** sessions detector-scored in the window — verified,
not merely counted from the independent table):

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

Every production consumer of the width function or the detector was enumerated. Two of
the three need no separate patch because they resolve the width through the single owner
function this wave changed and the §5 replay already bounds their behavior; the third
has a real behavioral delta, named and measured below rather than waved through.

- `engine/china_microstructure.py` — `_detect_limit_events` (event detection) and
  `name_packet` (`limit_width_for_date` call for the packet's live width) both call the
  now-era-dated function directly. Covered by the §5 replay.
- `scripts/backfill_china_limit_tape.py` — calls `_detect_limit_events` directly (the
  historical backfill path); inherits the fix identically to the nightly incremental path.
  Covered by the §5 replay.
- `scripts/build_china_library.py` — the V3 R3 chase/relay-position helper
  `_limit_close_bars` imports `limit_width_for_date as _limit_width` and resolves each
  bar's band through it, so it DOES inherit the era-dated width — but it carries no ST
  store-coverage gate of its own (unlike `_detect_limit_events`, which only ever applies
  `is_st=True` on/after `ST_STORE_COVERAGE_DATE`). For a currently-ST main-board name on
  a post-2026-07-06 bar, `_limit_close_bars`'s own "limit close" threshold — a bar whose
  close sits at the day's high with `_ret >= 0.95 * _band` — moves from `0.95 × 5% =
  4.75%` to `0.95 × 10% = 9.5%`. This threshold feeds relay-position counting into
  `engine/china_board_rank.py::_featured_shortfalls` (an admission effect on featured
  names). This is the ONE real, intended behavioral delta of this wave, not an
  oversight — it is exactly the correction the rule change requires; it is named here so
  it is not silently assumed away as "the replay already proved zero delta everywhere."

**Measured, not assumed.** `_limit_close_bars` reads its close series from
`_close_map`, which for a name upgraded to the deep OHLC store (`data/china_stocks/`,
`_overlay_deep_ohlc`, ≥300 rows) is that store's own close column — for `600079.SS` this
is byte-identical to `data/china_search/closes.parquet`'s column over the window checked
below (both are the ADJUSTED close series, not the raw nominal series
`engine/china_microstructure.py`'s detector reads from `data/china_stocks_raw/` — a
second, separate cross-store nuance worth naming: the chase helper and the limit-event
detector do not share a price basis).

Reproduced directly (read `data/china_search/closes.parquet`, intersected its columns
with the main-board ST set derived the same way as §4 but WITHOUT restricting to raw-store
presence — i.e. every `st_snapshot` ticker classified `main` by `_board_from_ticker`,
69 tickers — then computed each present name's maximum post-2026-07-06 session-over-session
`|close/prev_close − 1|`):

- Of the 69 main-board ST tickers in `st_snapshot`, exactly **one** — `600079.SS` — has a
  column in `data/china_search/closes.parquet`. No other main-board ST name is covered by
  this consumer's own data source at all, so no other name can produce a delta here
  regardless of width.
- `600079.SS`: 33 post-2026-07-06 sessions: **max session-over-session move = 2.24%**
  (2026-07-17), **zero** sessions above 4.75%, **zero** above 9.5%.
- Cross-check on the OTHER basis (raw nominal OHLC, `data/china_stocks_raw/`, the same
  data §5's per-session table used): max intraday move vs. prior close over the identical
  window = **3.08%** (already cited in §5) — also nowhere near 4.75%. The two numbers
  differ (2.24% vs 3.08%) because they are genuinely different quantities: one is an
  adjusted close-to-close return (what `_limit_close_bars` actually computes), the other
  is a raw-nominal intraday-extreme-vs-prior-close (what the §5 per-session table
  computes for the primary band question) — not a measurement error, and not something
  this wave needs to reconcile, since either number clears the 4.75% threshold by a wide
  margin.

**Verdict: the true delta for `_limit_close_bars` is zero today** — reproduced, not
quoted. No `600079.SS` session in the window would flip its "limit close" classification
between the old 4.75% threshold and the new 9.5% one, and no other main-board ST name is
even present in this consumer's data source to evaluate. This is the intended correction
taking effect with no observed side effect in the current data window; it is not proof the
delta stays zero forever, only that it measures zero now.

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

Two separate claims here, kept deliberately apart because they have different sources —
one is a code guarantee, the other is a contingent fact about two dates and a tape that
happened not to move:

**By law** (a code guarantee, verified by tests): `limit_width_for_date` correctly returns
0.05 for any *direct* caller passing a pre-2026-07-06 date with `is_st=True`, and 0.10 on
or after `MAIN_ST_BAND_WIDE_DATE` — see `TestLimitWidthForDate`'s boundary tests. This is
deterministic and does not depend on any other constant, store, or date.

**By luck, not by law** (contingent, not guaranteed by any code): that the detection-level
5% branch is *unreachable through the production event-detection path today* is a
coincidence, not a property the code enforces. `ST_STORE_COVERAGE_DATE` (the ST-membership
detection floor — a data-coverage fact about `data/china_st/`) happens to equal
`MAIN_ST_BAND_WIDE_DATE` (the rule's own effective date — a fact about SSE/SZSE
rulebooks) only because both landed on 2026-07-06; nothing in the code ties them together
(see the `MAIN_ST_BAND_WIDE_DATE` "R6 trap" comment in `engine/china_microstructure.py`,
which explicitly warns against reading them as related). Had `ST_STORE_COVERAGE_DATE`
instead been, say, 2026-06-01, the detector would have been ABLE to apply the stale 5%
width to detected ST main-board bars between 2026-06-01 and 2026-07-05 — the current
alignment happens to close that window to zero width, but that is luck in the calendar,
not a law in the code. Separately, and just as contingently: §4/§5's empirical zero
(no `limit_width == 5.0` rows exist, and the two-arm replay is identical) is a fact about
`600079.SS`'s price never having moved far enough in the measured window to produce an
event either way (§6/§5) — a fact about the tape, not a guarantee about the mechanism
(see §4's corrected wording). Both contingent facts could have come out differently under
a different calendar or a different tape; the code's *correctness*, not these two
coincidences, is what this wave actually guarantees.
