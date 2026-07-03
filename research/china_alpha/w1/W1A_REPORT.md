# W1-A Report — W-tier setup layer (engine/setup_tier.py)

**Wave:** W1-A  
**Date:** 2026-07-03  
**Status:** COMPLETE — 49/49 tests pass; PIT repaint measured; no git write  
**Files touched:** `engine/setup_tier.py` (new), `tests/test_setup_tier.py` (new),
`scripts/shadow_pit_china.py` (extended with `measure_wsetup_repaint()`)

---

## 1. What was built

### engine/setup_tier.py — two public functions

**`w_setup(close: pd.Series) -> dict | None`**

Computes the W-tier setup state per the masterplan F2/W1 spec using existing
primitives only (`cycles._tf_state`, `confluence_tiers._stoch_rsi_kd`,
`._rsi_macd`, `._tf_bars`, `._xup`). No new math invented.

Returns dict with:
- `w2`: `_tf_state` on `close.resample("2W-FRI").last().dropna()` — the full
  output dict including `stoch`, `stoch_cross_up`, `macd_pos`, `macd_approaching_up`,
  `macd_bars_to_cross`, `macd_cross_up`, `rsi14`
- `w1_cross`: last bullish 1W StochRSI k/d cross — `cross_date`, `bars_since`,
  `d_at_cross`, `from_washout` (d_at_cross < 25)
- `base`: 2-year (504-bar) range — `range_lo`, `range_hi`, `range_width_pct`,
  `spot_pct_in_range`, `bars_used`
- `setup_live`: bool — any of three conditions active
- `setup_reasons`: list of human-readable condition strings

Guard: `< 120` daily bars or `< 40` 2W-FRI bars returns `None`. NaNs, suspensions,
non-DatetimeIndex all handled gracefully.

**`assign_stage(...) -> dict`**

Implements the five lifecycle stage rules from masterplan F1/W1 EXACTLY:

| Rule | Condition | Stage |
|---|---|---|
| 1 | gate_eligible AND entry_status in {buy_now, partial} AND NOT overextended | ENTRY |
| 2 | gate_eligible AND (overextended OR entry_status not actionable) | RAN_LATE "signal live - entry passed; wait for pullback" |
| 3 | NOT gate_eligible, last cross within 15 sessions | RAN_LATE with date + sessions_since + pct_since; basing chip if hold_state.state == "intact" |
| 4 | NOT gate_eligible, no recent cross, setup_live | RIPENING with reason chips |
| 5 | else | None (no shelf) |

Rules execute in priority order (1 > 2 > 3 > 4 > 5). The JNJ-blasted-off invariant
(rule 2 fires before rule 1 when overextended=True) is enforced and test-pinned.

---

## 2. Probe fixture validation

All three exemplar chart reads from `probes-inline.md` reproduce exactly on the
live panel (`data/china_search/closes.parquet` through 2026-07-03):

| Ticker | Probe claim | `w_setup()` says | Match |
|---|---|---|---|
| 300725.SZ | 1W bull cross from d=9.3, 1 bar ago | `cross_date=2026-06-26, bars_since=1, d_at_cross=9.3, from_washout=True` | EXACT |
| 300725.SZ | 2W stoch washout (stoch=24, stoch_cross_up) | `stoch=24.0, stoch_cross_up=True` | EXACT |
| 688306.SS | 2W MACD approaching, bars_to_cross=4.9 | `macd_approaching_up=True, macd_bars_to_cross=4.9` | EXACT |
| 603129.SS | spot at 83% of 2y range (extended) | `spot_pct_in_range=83.1` | EXACT |

Tests pin RELATIONSHIPS (d_at_cross < 15; approaching_up True or crossed) rather
than hard stale dates, so they continue to pass on future panel updates that preserve
the structural story.

---

## 3. PIT bucket repaint tax (O1 measurement — W1-A required)

Measured via `scripts/shadow_pit_china.py:measure_wsetup_repaint()`:
- **Sample:** 100 names from `china_search/closes.parquet`
- **Method:** 8 completed 2W-FRI buckets before 2026-07-03; for each bucket,
  compare flags computed mid-bucket (panel truncated ~7 days before bucket close)
  vs flags computed at bucket-close (completed)
- **n_total_graded:** 728 name-bucket observations

| Flag | Flip rate | Raw count |
|---|---|---|
| `setup_live` | **1.65%** | 12/728 |
| `macd_approaching_up` | **0.27%** | 2/728 |

**Per-bucket breakdown:**

| Bucket end | setup_live flip | macd_approaching flip |
|---|---|---|
| 2026-03-13 | 2.2% | 0.0% |
| 2026-03-27 | 1.1% | 1.1% |
| 2026-04-10 | 3.3% | 0.0% |
| 2026-04-24 | 0.0% | 0.0% |
| 2026-05-08 | 3.3% | 0.0% |
| 2026-05-22 | 0.0% | 0.0% |
| 2026-06-05 | 1.1% | 0.0% |
| 2026-06-19 | 2.2% | 1.1% |

**Verdict (vs the F2 guardrail):** The W-tier 2W-FRI repaint tax is materially lower
than the 2D/3D cascade repaint: T3 (2D MACD projected) measured 23.8% US / 15.1% CN
in `calibration/provisional_replay.json`. The W-tier's 1.65% setup_live flip rate is
well below the ~15% flip criterion that would make the flag untradeable intraweek.
The RIPENING shelf can be safely published during live sessions; it does NOT need a
provisional badge. The `macd_approaching_up` flag at 0.27% is essentially stable.

---

## 4. Test coverage

**`tests/test_setup_tier.py`** — 44 tests in 5 sections:

1. **Smoke tests (8):** None on thin data, required keys, NaN/empty/non-datetime-index
   handling, spot_pct_in_range within [0,100]
2. **Live probe fixtures (5, skip-if-absent):** 300725 d_at_cross < 15,
   from_washout=True, 2W stoch washout; 688306 approaching_or_crossed, setup_live;
   603129 spot_pct_in_range > 70%
3. **assign_stage rules 1-5 (18):** Every rule branch covered; boundary cases
   (exactly-15 sessions_since, hold invalidated vs intact, entry "hold" vs "partial",
   overextended overrides buy_now, JNJ never-ENTRY invariant, rule 1 priority over rule 4)
4. **w1_cross_info boundary cases (5):** Monotone rising, washout+recovery, bars_since
   non-negative, d_at_cross threshold alignment, short series
5. **Base range sanity (3):** spot within lo/hi, width non-negative, short returns None

All 44 pass (+ 5 shadow_pit_china tests = 49 total). The single pytest warning is a
class-scoped fixture deprecation in pytest 8.x that does not affect test execution.

---

## 5. Artifacts

| Path | Description |
|---|---|
| `engine/setup_tier.py` | W-tier setup layer — `w_setup()` + `assign_stage()` |
| `tests/test_setup_tier.py` | 44 tests — probe fixtures + synthetic rule coverage |
| `scripts/shadow_pit_china.py` | Extended with `measure_wsetup_repaint()` |
| `research/china_alpha/w1/W1A_REPORT.md` | This file |

---

## 6. Open items carried forward

- **O1 (MEASURED, CLOSED):** 2W partial-bucket repaint tax = 1.65% setup_live flip,
  0.27% macd_approaching_up flip. Below the ~15% untradeable threshold — RIPENING
  does not need a provisional badge intraweek.
- **Next W1 tasks:** board partition + card redesign (RIPENING/ENTRY/RAN_LATE shelves),
  JSON output extension (stage field on buy rows + ripening/ran arrays), ledger logging.

---

## 7. F3 discipline compliance

- `_cn_bonus` weights are untouched.
- `blend_sorted` math is untouched.
- The three-shelf PARTITION introduced here is a new layer on top of the existing
  pipeline; existing buy array semantics are unchanged.
- RIPENING screens the full closes panel universe (all 1,514 columns in
  `data/china_search/closes.parquet`), not just current board rows — the `w_setup()`
  function is panel-agnostic.
