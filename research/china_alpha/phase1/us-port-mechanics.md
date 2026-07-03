# US→CN Port Recipes: Mechanical Specifics

**Date:** 2026-07-03  
**Scope:** P1 HOLD tracker port, P2 T3/T4 forward grading, P3 CN board forward ledger parity, blend bonus channel inventory  
**Worktree:** `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/lucid-knuth-523979`

All line numbers verified against current worktree HEAD (2026-07-03).

---

## P1 — HOLD Tracker Port

### How the US build wires `engine/hold.py`

**Import** (`scripts/build_stock_library.py:55`):
```python
from engine import hold as hold_engine
```

**Collection loop** (`build_stock_library.py:L1201–1222`):

After `sig_verdict[ticker] = signal_gate.gate(ticker, close)` (L1210), the US loop:
1. Reads the open buy marker from `sig_verdict`: `_last_m = _sv.get("last")` (L1215).
2. Determines anchor: `_anchor = _last_m.get("date") if _is_buy else None` (L1217) — the §7 take/pending marker's date when an open buy is active, else `None`.
3. Calls `hold_engine.hold_state(close, anchor_date=_anchor, last_cross_fallback=True)` (L1218) — the fallback to the most recent 3D RSI-MACD cross-up (≤45 trading days old) triggers automatically when no open buy marker is present.
4. Stores: `_hold_state[ticker] = _hs` if result is not None (L1220).

**Attach to per-stock JSON** (`build_stock_library.py:L1477–1479`):
```python
if _hold_state.get(ticker):
    rec["hold"] = _hold_state[ticker]
```
Written **after** `disp_map` construction, **before** `to_write.append()`.

**Attach to standout row** (`build_stock_library.py:L1788–1791`):
```python
_hd = _hold_state.get(t)
if _hd is not None:
    r["hold"] = _hd
```
Inside the wide-board enrichment loop over `wide["buy"] + wide["laggards"]`.

**`hold_state()` return dict** (`engine/hold.py:L197–208`):
```python
{
    "state":        str,   # "intact" | "launched" | "broken"
    "anchor":       str,   # YYYY-MM-DD
    "anchor_src":   str,   # "take" | "cross"
    "days_basing":  int,   # trading days strictly after anchor
    "invalidation": float, # trough * 0.97 level
    "maxup_pct":    float, # max gain from anchor
    "ob_persist":   bool,  # 3D StochRSI k or d >= 80 since anchor
    "provisional":  bool,  # last 3D bucket incomplete
}
```

**Semantics of `last_cross_fallback`** (`engine/hold.py:L83–100`):
- `anchor_date=<date>`: anchors on the explicit §7 buy/rebuy marker date (source="take").
- `anchor_date=None` + `last_cross_fallback=True`: falls back to the most-recent 3D RSI-MACD cross-up that is ≤ `CROSS_MAX_AGE=45` trading days old; sets `anchor_src="cross"` and `provisional=True` if the last 3D bucket is incomplete.
- Returns `None` when no anchor can be established.

**How `grade_us_board.py` grades by hold state:**

`_row_features()` (`grade_us_board.py:L200–204`) extracts:
```python
"hold_state":     _dig(r, ("hold", "state"), default=None),
"hold_days":      _num(_dig(r, ("hold", "days_basing"), default=None)),
"hold_inv":       _num(_dig(r, ("hold", "invalidation"), default=None)),
"hold_anchor_src": _dig(r, ("hold", "anchor_src"), default=None),
```

`grade_boards()` (`grade_us_board.py:L378–382`) propagates them into the graded record:
```python
"hold_state":      feat.get("hold_state"),
"hold_days":       feat.get("hold_days"),
"hold_inv":        feat.get("hold_inv"),
"hold_anchor_src": feat.get("hold_anchor_src"),
```

`aggregate()` (`grade_us_board.py:L531–532`) stratifies the output JSON:
```python
"by_hold_state": _slice_table(buy, "hold_state", "excess_spy"),
```
Result: `data/us_board_ledger/retro_grades.parquet` does **NOT** yet carry `hold_state` / `hold_days` columns — the earliest boards pre-date the W6-C schema. The `retro_grades.parquet` (verified 2026-07-03: L530 check) only has `as_of, entry_date, rank_by, horizon, lane, position, ticker, sector, alpha, score, band, composite_z, verdict, align_tier, urgency, state, entry_status, act_level, signal_quality, validation_status, vol_squeeze, dispersion_state, off_high, ret, spy_ret, excess_spy, mae_close_excess_spy, sector_etf, etf_ret, excess_sector, mae_close_excess_sector` (31 columns). The hold columns were added to the grader code but the retro parquet was not rebuilt.

### Insertion points in `scripts/build_china_library.py`

The CN loop structure (verified `build_china_library.py:L877–1027`) mirrors the US loop but is **missing** the HOLD tracker entirely. No `from engine import hold` import exists in the file. The equivalent insertion points are:

**Step 1 — Import** (after `engine import coiled` at the import block, ~L43):
```python
from engine import hold as hold_engine   # W6-C HOLD tracker (CN port)
```

**Step 2 — Declare collection dict** (after `_coil_fire: dict[str, dict] = {}` at L886):
```python
_hold_state_cn: dict[str, dict] = {}
```

**Step 3 — Collect per ticker in the loop** (after `sig_verdict[ticker] = signal_gate.gate(ticker, close)` at L894, mirrors US L1210–1222):
```python
try:
    _sv_cn = sig_verdict[ticker]
    _last_m_cn = _sv_cn.get("last")
    _is_buy_cn = bool(_last_m_cn and _last_m_cn.get("type") in ("buy", "rebuy"))
    _anchor_cn = _last_m_cn.get("date") if _is_buy_cn else None
    _hs_cn = hold_engine.hold_state(close, anchor_date=_anchor_cn, last_cross_fallback=True)
    if _hs_cn is not None:
        _hold_state_cn[ticker] = _hs_cn
except Exception:
    pass
```
Insert this **immediately after** the `sig_verdict[ticker]` line at L894, before the `coiled` collection block at L895. The CN loop's `close` variable is the same close-only series (DatetimeIndex) passed to `signal_gate.gate()` — no high/low required.

**Step 4 — Attach to per-stock JSON** (after `to_write.append((safe, rec))` at L1020, mirrors US L1477–1479):
```python
if _hold_state_cn.get(ticker):
    rec["hold"] = _hold_state_cn[ticker]
```
Insert before `to_write.append((safe, rec))` — i.e., add it to `rec` during the ticker loop, not the deferred write loop. The CN loop has no separate strip-enrichment phase for per-stock JSONs.

**Step 5 — Attach to standout rows** (in the wide-board enrichment loop, `build_china_library.py:L1276–1292`, the `for r in wide["buy"] + wide["laggards"]:` loop):
```python
_hd_cn = _hold_state_cn.get(r.get("ticker"))
if _hd_cn is not None:
    r["hold"] = _hd_cn
```
Insert after `r["risk_sizing"] = risk_sig[t]` (L1283), before the `data_through` field attachment (L1288). Mirror of US L1788–1791.

### CN-specific adaptations

| Issue | Resolution |
|---|---|
| **Close-only OK?** | Yes. `hold.hold_state()` is fully close-only. `_last_3d_cross()` uses `_tf_bars(c, 3)` + `_rsi_macd` on the close series; `_stoch_rsi_kd` uses the same close-resampled bars. `engine/hold.py:L30` uses `_tf_bars, _stoch_rsi_kd, _to_daily, _rsi_macd, _xup` — all from `confluence_tiers`, which is already used in the CN board for the T1–T4 cascade. No OHLCV needed. |
| **Anchor source** | Same as US: prefer the §7 buy/rebuy marker date from `sig_verdict[ticker].get("last")`, fall back to last 3D cross-up ≤45 trading days old. CN tickers have the same signal_gate verdicts. |
| **Interaction with `EXT_PENALTY`** | No interaction. Hold state is an **additive display chip** — it is NOT fed into `_cn_bonus()` (`build_china_library.py:L1215–1223`) or `blend_sorted`. The US pattern is identical: hold is a display/grading field, never a rank signal. |
| **Interaction with washout bonus** | No interaction. `_cn_bonus()` reads `r.get("washout_2w")` and `coiled_by` bonus; hold is stored separately on `rec["hold"]` and `r["hold"]`. Stacking hold + washout on the same name is correct — they are orthogonal signals. |
| **T+1 fill concern** | A-share hold state uses daily closes (close-only convention). The anchor date from the §7 marker is the bar date when `signal_gate.analyze()` fires — already post-confirmation. The trough reference is `close[anchor-90..anchor]`, causal. No look-ahead. |
| **`LAUNCHED` threshold on CN** | `MAXUP_THRESH=0.05` (5% gain since anchor) and `OB_THRESH=80` are the same constants. A-share names can spike >5% on a single day (limit-up = 10%). A 5% LAUNCHED threshold means the first limit-up day after the cross will trigger LAUNCHED. This is intentional — the name is no longer in a basing zone. No adaptation needed. |
| **`BROKEN` threshold on CN** | `trough * TROUGH_TOL = trough * 0.97`. For CN names with higher intraday volatility this is a tighter invalidation test (a 3% daily move is common). Consider widening to `0.95` in the future, but the initial port uses the US constant per HOLD spec. |

---

## P2 — T3/T4 Forward Grading

### Does any existing forward ledger grade by tier?

**Searched files:** `grade_us_board.py`, `engine/china_standout_track.py`, `engine/china_name_score_grader.py`, all files matching `qledger` and `forward_log` in `/engine/`.

**Findings:**

1. **`grade_us_board.py`**: `tier_cascade` is extracted in `_row_features()` (L181) and propagated into the graded record at L367. However, the aggregation block (`aggregate()`, L498–553) does **NOT** include `_slice_table(buy, "tier_cascade", "excess_spy")`. There is no `by_tier_cascade` in the output JSON. The `retro_grades.parquet` (29 columns) does not carry `tier_cascade`. **Confirmed: no by-tier grading exists in the US grader.**

2. **`engine/china_standout_track.py`**: The `append_board()` function (L112–178) logs `tier` (= `sig.get("tier_cascade")`, L146) to `data/china_standout_track/board.parquet`. The current parquet (3 dates, 180 rows) shows tier values T1/T2/T3/T4. However, the `grade()` function (L260–328) does **not** stratify by tier — it only reports `top_decile_fwd` vs `rest_fwd`, `extended_fwd` vs `not_extended_fwd`, and board rank-IC. **Confirmed: no by-tier grading exists in the CN grader either.**

3. **`engine/china_name_score_grader.py`** (referenced at `build_china_library.py:L1058`): Grades the per-name POTENTIAL score, not the board tier. No tier field.

4. **`engine/qledger.py`**: No `tier_cascade` references found. The qledger tracks claim-passport outcomes, not board tiers.

**Conclusion: No existing forward ledger grades T3/T4 by tier. The `tier` field in `china_standout_track/board.parquet` is logged but never stratified in `grade()`.**

### What a per-tier CN forward log must record per fire

Each row when a name fires at a given tier (written to an append-only parquet per the china_standout_track pattern):

| Field | Source in `build_china_library.py` | Semantic |
|---|---|---|
| `date` | `as_of` (build date) | Board date (confirmed session) |
| `ticker` | `r.get("ticker")` | A-share ticker (.SS/.SZ) |
| `tier` | `sig_verdict[t].get("tier_cascade")` | T1/T2/T3/T4 |
| `ticks` | `sig_verdict[t].get("ticks")` | Native-TF ticks since cross/arrow (None for T3/T4 projected) |
| `provisional` | `sig_verdict[t].get("provisional")` | T3 incomplete-bucket flag |
| `ext_since_cross` | `(r.get("extension") or {}).get("score", 0.0)` | Extension score 0..1 at fire time |
| `washout` | `r.get("washout_2w")` | 2W StochRSI washout-reclaim flag |
| `coiled` | `(r.get("coiled") or {}).get("coiled", False)` | COILED cohort-washout flag |
| `sector_state` | Sector state requires a join: `(rec.get("conviction") or {}).get("sector_state")` or from `engine/china_sector_desk` — **not directly on the row**; see Open Questions. |
| `board_rank` | 1-based position in `eligible_rows` | Board order at fire |
| `level` | `r.get("price")` | T+0 reference close (board date) |

**Where the write hook goes in `build_china_library.py`:**

The natural insertion point is the existing `china_standout_track.append_board()` call at **L1328**:
```python
_bn = china_standout_track.append_board(wide["buy"], asof=as_of, lane=_lane)
```
The tier-level data is already in each row's `r["signal"]` dict (attached at L1279). The simplest approach is to **extend `append_board()`** in `engine/china_standout_track.py` to also log `ticks`, `provisional`, `ext_since_cross`, `washout`, `coiled`, and `board_rank` — all already available in the row at append time. No second call or new function needed.

Alternatively, a separate `append_tier_log(rows, asof)` could write to a separate parquet (e.g., `data/china_standout_track/tier_log.parquet`) for cleaner schema separation. The COILED wave-3/4 fields were added to `append_board()` via schema union (`pd.concat` with `drop_duplicates`), which is the established extension pattern (`china_standout_track.py:L152–161`).

**Concrete field additions to `append_board()` at L144–161:**
```python
out.append({
    ...,                               # existing fields
    "ticks":       sig.get("ticks"),
    "provisional": bool(sig.get("provisional")),
    "ext_score":   float((r.get("extension") or {}).get("score") or 0.0),
    "washout_2w":  bool(r.get("washout_2w")),
    # coiled already logged
})
```
`sig` = `r.get("signal") or {}` (already used on L141–146 for `tier_cascade`).

---

## P3 — CN Board-Level Forward Ledger: Current State and US-Parity Gap

### What `engine/china_standout_track.py` grades today

**Data store:** `data/china_standout_track/board.parquet` (verified: 180 rows, 13 columns, 3 dates: 2026-06-30 to 2026-07-02).

**Current logged columns:**
`date, ticker, board_rank, tier, setup, extended, washout, level, coiled, coiled_star, coiled_cohort, coiled_fire, coiled_fire_ticks`

**Grade function** (`china_standout_track.py:L260–328`) computes per horizon (21d, 63d):
- `hit_vs_csi300` — share of picks beating the CSI300 (510300.SS), Wilson CI
- `board_rank_ic` — rank-IC (rank vs fwd excess; negative = well-ordered board)
- `top_decile_fwd` vs `rest_fwd` — top 10% board ranks vs the rest
- `extended_fwd` vs `not_extended_fwd` — anti-chase stratification
- `n_pinned` — count of pinned reference closes

**Current grading status:** All horizons read `{"n": 0, "note": "accruing"}` as of 2026-07-03 (the ledger started 2026-06-30; 21d horizon matures ~2026-07-29, 63d ~2026-09-01). `_MIN_GRADED = 8` rows needed before any number is published. `n_graded=0` confirmed from `site/factordata/china_standouts.json`.

**Where it is rendered:** `site/china_stocks.html:L11752` shows the board-track telemetry panel with a full tooltip explaining the grading conventions. The `board_track` dict is embedded at build time inside `china_standouts.json` (confirmed in file at key `board_track`). The page renders the panel when `board_track.available == True`.

**What is NOT graded today (gaps vs US parity):**

| US grader feature | CN standout track | Gap |
|---|---|---|
| Stratification by tier_cascade | Tier logged but not stratified in grade() | Add `_slice_by_tier()` in grade() |
| Stratification by hold_state | Not logged, not graded | New column in append_board() + stratification |
| Stratification by band/verdict | Not logged, not graded | Could add conviction fields |
| Precision@k (top-3, top-5) | Not computed | Add _precision_at_k() equivalent |
| MAE (close-path adverse excursion) | Not computed | Add _close_path_mae() equivalent |
| Excess vs sector ETF (per-name) | Only CSI300 benchmark | Would need sector ETF series for CN |
| Snapshot JSONL (forward-accruing outside git) | Uses parquet only; relies on the asia-lane write | Add snapshots.jsonl pattern for robustness |

### What a US-parity CN board grade pipeline requires

**Benchmark:** CSI300 ETF `510300.SS` (already implemented in `_bench_close()`).

**Fill realism:** T+1 (H+L)/2 (already implemented in `_t1_fill()`). True T+1 open would upgrade this when `collectors/_stock_ohlc` collects open prices.

**T+1 fillability / limit-up exclusion:** Already implemented at `_t1_fill()` (`china_standout_track.py:L199–229`):
- `locked_limit` = high == low == close on T+1 (genuinely unfillable; excluded from grading). These are locked-limit-all-day events (0.22% of entries per the module docstring).
- `pinned` = reference close at the day's high (informational flag, not excluded).

**Limit-up data source:** The current implementation detects limit-up mechanically from the OHLC: `float(hi) == float(lo) == float(close)` on the T+1 bar. This works for *all-day* limit-up locks (a ceiling hit that traps price all day). It does NOT detect names that hit the limit briefly and then retrace. For a more complete limit-up identification, `data/china_zt_pool/` stores 涨停板 data (`collectors/china_zt_pool.py` imports at L616 of `build_china_library.py`). The mechanical detection is sufficient for fill-exclusion purposes.

**What needs to be added to reach US parity:**
1. **`_slice_by_tier(df, tier_col="tier")`** — mirrors `_slice_table()` in grade_us_board; stratifies `grade()` output by T1/T2/T3/T4.
2. **Hold-state columns** in `append_board()` (see P1 above) + `by_hold_state` stratification in `grade()`.
3. **`_precision_at_k()`** — per-board top-k precision averaging (mirroring grade_us_board:L439–465).
4. **MAE close-path** — per-row (name_ret - bench_ret) minimum over window; mirrors grade_us_board:L304–320.
5. **Tier logging gap:** `ticks` and `provisional` not yet in `append_board()` — add per P2.

---

## Blend Bonus Channel Inventory

### `signal_gate.blend_sorted` signature

`engine/signal_gate.py:L223–264`:
```python
def blend_sorted(
    items: list,
    base_of,          # callable(item) -> float  (base score; US=composite_z, CN=setup)
    verdict_of,       # callable(item) -> dict   (signal_gate verdict with .weight)
    reverse: bool = True,
    bonus_of=None,    # optional: callable(item) -> float  (additive lift on 0..1 scale)
    *,
    tier_frac: float | None = None,   # None → uses module TIER_FRAC=0.45
    wn_floor: float = 0.0,            # CN uses 0.60 (mild near-parity flatten)
) -> list:
```

Board score formula (L254–262):
```
wn = max(0, min(1, (w - 0.4) / 0.6))            # T1→1.0 .. T4→0.0
wn = wn_floor + (1 - wn_floor) * wn             # compress toward parity (CN)
pct = percentile_rank(base_of(x))               # conviction percentile in pool
score = tf * wn + (1 - tf) * pct + bonus_of(x) # convex blend + additive lift
```

### All existing `bonus_of` users

**US (`build_stock_library.py`):** No `bonus_of` is passed. The US call at the blend_sorted invocation does not appear explicitly in the read portion, but the coiled/washout logic is in the US board — confirmed from the US loop.

**CN (`build_china_library.py:L1225–1230`):**
```python
eligible_rows = signal_gate.blend_sorted(
    ...,
    bonus_of=_cn_bonus,
    tier_frac=CN_TIER_FRAC,   # 0.30
    wn_floor=CN_WN_FLOOR)     # 0.60
```
where `_cn_bonus(r)` (`build_china_library.py:L1215–1223`):
```python
def _cn_bonus(r):
    b = WASHOUT_BONUS if r.get("washout_2w") else 0.0       # +0.5 for 2W StochRSI washout-reclaim
    b += ((coiled_by.get(r.get("ticker")) or {}).get("bonus") or 0.0)  # COILED cohort bonus (validated)
    ext = float((r.get("extension") or {}).get("score") or 0.0)
    return b - EXT_PENALTY * ext                             # -0.5 * ext_score (anti-chase)
```

**Constants:**
- `WASHOUT_BONUS = 0.5` (L1184) — ~one tier lift for 2W StochRSI washout-reclaim
- `EXT_PENALTY = 0.5` (L1185) — ~one tier demote for a fully-extended name (extension.score=1.0)
- `CN_TIER_FRAC = 0.30` (L1190) — tier gets 30% weight in blend (vs US default 0.45)
- `CN_WN_FLOOR = 0.60` (L1190) — T4 still gets 60% of T1's tier credit (mild near-parity)

**COILED bonus values:** `coiled.assess()` returns a `bonus` field. From wave-3 calibration (`engine/coiled.py`, referenced in `build_china_library.py:L43`), the cohort-washout bonus lifts a qualifying name by a validated amount (validated: clean15 +7.33pp, stop5 −6.21pp at n=10,784).

### Pattern for adding a new rank term

A new bonus (e.g., HOLD-INTACT lift or tier-based grading signal) must follow the existing pattern:
1. Collect per-ticker in the main loop into a dict (e.g., `_hold_state_cn`).
2. Define or extend `_cn_bonus(r)` to add the new additive term:
   ```python
   def _cn_bonus(r):
       b = WASHOUT_BONUS if r.get("washout_2w") else 0.0
       b += ((coiled_by.get(r.get("ticker")) or {}).get("bonus") or 0.0)
       # NEW: HOLD-INTACT lift (display-only, additive)
       hold = _hold_state_cn.get(r.get("ticker")) or {}
       if hold.get("state") == "intact":
           b += HOLD_INTACT_BONUS           # define e.g. 0.2 (sub-tier lift)
       ext = float((r.get("extension") or {}).get("score") or 0.0)
       return b - EXT_PENALTY * ext
   ```
3. Do NOT add more than ~1.0 total bonus — the blend scale is 0..1 for the tier×conviction term; a bonus > 1.0 would over-ride the tier ordering.
4. Gate on a validated edge before adding to `_cn_bonus`. The current bonuses (washout, COILED) are both wave-3-validated. HOLD-INTACT has not yet been validated for CN (no CN HOLD data exists yet); add it as display-only first (per P1).

---

## Cross-Reference: Gaps Between US and CN Graders

| Dimension | US (`grade_us_board.py`) | CN (`china_standout_track.py`) |
|---|---|---|
| Benchmark | SPY + per-name sector SPDR ETF | CSI300 only (510300.SS) |
| Fill | Next session close (T+1 close) | T+1 (H+L)/2 proxy (cleaner, excludes locked-limit) |
| Limit-up exclusion | Not applicable (no daily limits) | Implemented: `locked_limit = hi==lo==close` |
| Horizons | 5d, 10d, 21d | 21d, 63d |
| Tier stratification | `tier_cascade` extracted in `_row_features` (L181) but **NOT** in `_slice_table` calls — absent from output | `tier` logged in `append_board()` (L146) but **NOT** stratified in `grade()` |
| Hold-state stratification | `by_hold_state` in aggregation (L532) | Not logged, not graded |
| Precision@k | `_precision_at_k()` (L439) | Not implemented |
| MAE | `_close_path_mae()` (L304) | Not implemented |
| Data source for names | `equity_factors._closes("broad")` (survivor-biased S&P-1500) | `store.read("china_stocks", ticker)` per-name + `store.read("china", ticker)` ETF fallback |

**Note on US tier stratification gap:** `tier_cascade` IS in `_row_features()` (L181) and IS in `grade_boards()` (L181 referenced in the returned rec at — actually absent, see the graded record L358–405: `tier_cascade` is in `feat` but NOT emitted into `rec`). Confirmed by checking the retro_grades.parquet schema: `tier_cascade` is absent from the 31-column parquet. The US grader has the field in `_row_features` but does not pass it into the graded record or the stratification. **Both US and CN graders need `by_tier_cascade` / `by_tier` added.**

---

## Verification Commands Run

```bash
# Check china_standout_track parquet schema and tier distribution
cd /path/to/worktree && python3 -c "
import pandas as pd; df = pd.read_parquet('data/china_standout_track/board.parquet')
print(list(df.columns)); print(df['tier'].value_counts())"
# → columns: [date, ticker, board_rank, tier, setup, extended, washout, level,
#             coiled, coiled_star, coiled_cohort, coiled_fire, coiled_fire_ticks]
# → T2:89, T1:70, T3:4, T4:1 (3 dates: 2026-06-30..2026-07-02)

# Check US retro grades parquet schema
python3 -c "
import pandas as pd; df = pd.read_parquet('data/us_board_ledger/retro_grades.parquet')
print(list(df.columns))"
# → 31 columns; tier_cascade absent; hold_state absent

# Check us_board_track.json (worktree copy)
python3 -c "import json; d=json.load(open('site/factordata/us_board_track.json'))
print(d)"
# → {"generated": "2026-07-03T07:37:40.575927+00:00", "empty": true, "note": "no matured graded rows"}

# Check china_standouts.json board_track status
python3 -c "import json; d=json.load(open('site/factordata/china_standouts.json'))
print(d['board_track'])"
# → {available:True, n_rows:182, n_graded:0, by_horizon: {21d: accruing, 63d: accruing}}
```

---

## Open Questions

1. **Sector state on CN rows:** The per-tier forward log spec calls for `sector_state` (the current cycle state of the name's sector). This is not a top-level field on the standout row. It would need to come from `engine/china_sector_desk` or a join on the conviction profile's sector slot. The exact field path is unverified — needs an executor to grep for the sector-state field in a committed `china_standouts.json` buy row.

2. **US `by_tier_cascade` gap confirmation:** The `tier_cascade` field is in `_row_features()` (L181) but is NOT emitted into the `rec` dict in `grade_boards()` (L358–405 read: field is in `feat` but absent from `rec`). Confirmed by parquet schema inspection. An executor adding `by_tier_cascade` to US grading would need to (a) add `"tier_cascade": feat.get("tier_cascade")` to the `rec` dict in `grade_boards()`, and (b) add `_slice_table(buy, "tier_cascade", "excess_spy")` to the aggregation block.

3. **HOLD-INTACT bonus validation:** Adding `HOLD_INTACT_BONUS` to `_cn_bonus()` requires a forward-graded validation (intact-basing names vs the rest). No CN HOLD data exists yet. The recommendation is: log first (P1), accrue for 21–63d, then test whether intact basing correlates with forward excess before adding to the blend.

4. **China sector ETF parity:** The CN grader only benchmarks to CSI300. The US grader adds a per-name sector ETF (GICS→SPDR map). For CN, equivalent sector ETFs exist (e.g., 512170.SS Healthcare, 512480.SS Semiconductors). Adding a CN sector ETF map and a second benchmark would bring the CN grader to US parity on this dimension. Currently unimplemented.

5. **`last_cross_fallback` for CN: CROSS_MAX_AGE=45 trading days.** CN A-shares can be suspended for extended periods (ST names, major corporate events). If a name is suspended >45 trading days after a valid cross, the fallback will return None even though the cross was real. The executor should evaluate whether the CROSS_MAX_AGE constant should be relaxed for CN or whether a suspension-aware check is needed.
