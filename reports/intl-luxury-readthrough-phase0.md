# European Luxury → China-Consumer Read-Through Phase-0

**Channel:** C7 (masterplan §5)
**Wave:** W4
**Date:** 2026-07-02
**Author:** Fable (Claude Sonnet 4.6), Wave-4 C7 agent
**Builders:** `scripts/c7_luxury_readthrough.py`, `scripts/intl_phase0.py --c7`
**Ledger entry:** `data/intl_bridge/ledger.json` (id: `c7_luxury_china_consumer`)
**Verdict: CONTEXT — do NOT wire**

---

## Thesis and declared spec

Per masterplan §5 C7:

> "European luxury (LVMH ~30% China-consumer revenue, Richemont, Hermès) is a
> *policy-undistorted* real-time read on the Chinese consumer that the A-share
> consumer tape cannot give. The validated grain is DE-RISK: luxury rolling over
> → trim CN-consumer conviction."

**Pre-registered claim** (`engine/intl_claims.CLAIMS`, id `c7_luxury_china_consumer`):
- Direction: de-risk
- Target: `yahoo/FXI` (CSI300/HK consumer proxy, the CN-consumer declared target)
- Horizon: 21d (ONE pre-registered DD horizon)
- Source series: `yahoo/LVMUY` (freshness SLA 5d)
- Budget family: `intl_bridge` (N=17 declared grid, pre-logged at generation)

---

## Data

### LVMUY ADR cold-start seed

`data/yahoo/LVMUY.parquet` was not present in the daily store (W0 item 4 added the ticker
to the config but the daily fetch had not run). A clean cold-start seed was performed:

```
yfinance LVMUY, period=max, auto_adjust=False
5,139 rows: 2006-01-27 to 2026-07-02
Format: close (Adj Close), close_price (Close), volume — standard yahoo store schema
```

Stored via `store.upsert('yahoo', 'LVMUY', ..., overwrite_overlap=True)`. This is the
committed seed — the normal daily yahoo collector will maintain it going forward.

### Luxury basket constituents

| Constituent | Source | History | Notes |
|---|---|---|---|
| LVMUY | `data/yahoo/LVMUY.parquet` | 2006-01-27 to 2026-07-02 (~20y) | ADR; declared source_series; primary |
| RMS.PA | `data/intl_search/closes.parquet` | 2021-06-15 to 2026-07-01 (~5y) | Hermès local Paris |
| CFR.SW | `data/intl_search/closes.parquet` | 2021-06-15 to 2026-07-01 (~5y) | Richemont local Zurich |

**Basket construction:** Equal-weight daily return (EW total-return, not EW price-level,
to avoid level-dominated weighting: RMS.PA ~€1,600 vs LVMUY ~$110). Constituents are
normalized by computing per-constituent returns, then taking the unweighted mean.

**Full 3-leg overlap:** 2021-06-15 onwards (~5 years). Before that date, LVMUY is the
sole basket leg.

---

## Effective-N honesty (CRITICAL)

The declared CRISES table spans: asian_97 / dotcom_00 / gfc_08 / eurozone_11 / covid_20 /
rate_22. The basket's crisis coverage:

| Crisis | Window | LVMUY available | RMS.PA/CFR.SW | Basket legs |
|---|---|---|---|---|
| asian_97 | 1997-07 to 1998-10 | No (starts 2006) | No | 0 |
| dotcom_00 | 2000-03 to 2002-10 | No | No | 0 |
| gfc_08 | 2007-10 to 2009-03 | Yes (LVMUY only) | No | 1 |
| eurozone_11 | 2011-05 to 2011-12 | Yes (LVMUY only) | No | 1 |
| covid_20 | 2020-02 to 2020-04 | Yes (LVMUY only) | No | 1 |
| rate_22 | 2022-01 to 2022-10 | Yes | Yes (all 3) | 3 |

**LVMUY alone (20y history):** 4 crisis windows covered (gfc_08, eurozone_11, covid_20, rate_22)
→ crisis-count gate PASSES for the LVMUY-primary basket.

**Full 3-leg basket (5y history):** only 1 declared crisis window (rate_22) → effective-N=1,
well below the 3-crisis floor. The 3-leg basket result would fail crisis-count.

**Decision:** the harness grades the LVMUY-primary basket (effective-N=4, which passes the
crisis-count floor). The local luxury constituents are included in the EW basket where
available but the effective-N accounting follows the longest-dated constituent (LVMUY) since
that drives the FULL test window. The report notes honestly that the 5y locals cover only
1 crisis — this does not change the verdict (the DSR and lead-lag kernel are the binding failures)
but is documented for full transparency.

---

## Earnings-print excision

Earnings prints are exactly the spikes that would be miscoded as trend in a rolling-return
signal. The causal excision method (±2 trading days around each print date → NaN the signal,
not the returns):

**Excised constituents and approximate dates:**
- LVMH: full-year results (~late Jan/early Feb) + first-half (~late July) — from 2006 onwards
- Hermès: full-year (~mid Feb) + first-half (~late Jul/early Aug) — from 2021 onwards
- Richemont: full-year (~mid May) + half-year (~mid Nov) — from 2021 onwards

**Bars excised:** 271 (out of 5,139 total LVMUY trading days)

The excision is applied BEFORE the causal trailing-percentile conversion, so no print spike
enters the de-risk signal. The ex-earnings IC is the reported figure.

---

## Signal construction (causal)

1. **EW basket return:** daily EW return across available constituents (NaN-safe mean)
2. **Trend-turn signal:** rolling 21d momentum of the basket (`pct_change(21)`)
   — the "rolling over" component per the C7 mechanism
3. **Earnings excision:** signal NaN'd at ±2td around each print date
4. **De-risk signal:** `−trend` (flip sign so HIGH value = basket declining = de-risk danger);
   converted to a causal trailing-percentile (252d window, fallback to z-score if shorter)
5. **Long/flat strategy:** hold FXI; go flat when the causal pctile > 0.70 (top-30% danger zone)
   — position shift(1) before interacting with next-bar FXI returns (causal)

---

## Gate table

| Gate | Result | Notes |
|---|---|---|
| Freshness (LVMUY 5d SLA) | **PASS** | LVMUY last: 2026-07-02 (cold-seeded today) |
| DSR (promotion gate, N=17 intl_bridge budget) | **FAIL: 0.1609** | Far below the 0.90 door; the signal has no directional forecast power |
| Lead-lag kernel (HAC-t + BH-FDR) | **FAIL: no lag≥1 survivor** | lag=0 t=11.75 (contemporaneous); lag=1 t=−1.49 p=0.14 (not significant, wrong sign); lag=2/5 not significant |
| Orthogonality (vs FXI-momentum + CNH-RORO basis) | PASS | residual partial −0.061 (just above the 0.03 noise floor; the luxury basket carries minimal but measurable residual information beyond FXI's own trend + the RORO leg) |
| Crisis-count (effective-N) | PASS | 4 crises covered (LVMUY 20y: gfc_08 / eurozone_11 / covid_20 / rate_22) |
| Crisis-independent ES | PASS | ES reduction ex top-3 DD windows: +0.0076 |
| Drawdown-reduction | **FAIL** | MaxDD cut: +6.4pp (−66.3% vs −72.7% B&H) — passes the 1pp floor, BUT Calmar strat = −0.008 vs bench = +0.045 → the overlay has NEGATIVE return while B&H FXI recovered, meaning the strategy destroys value by staying flat during FXI's up-periods |
| Split-half same-sign Sharpe | PASS (trivially) | Both halves positive (+0.19 / +0.16) — a mirage: the strategy is near-always long and simply inherits FXI's positive drift; this is not a real split-half signal test |

**Verdict: CONTEXT** (weight_cap 0, kill=True — two hard failures, see below)

---

## Lead-lag kernel detail

The standing ADJ-4 prior: "survivors are timezone lag-1 artifacts." Here luxury (US ADR +
Paris/Zurich locals, all accessible in US hours) and FXI (HK underlying, US-hours ADR)
trade in the **same US session**, not across timezones. So the prior specifically warns:
contemporaneous correlation does NOT indicate a lead.

| Lag | HAC-t (NW, 10 lags) | p-value | BH-FDR | Notes |
|---|---|---|---|---|
| 0 (same-day) | **11.75** | ~0 | — | Strongly significant **contemporaneous** co-movement |
| 1 (luxury leads FXI by 1 day) | −1.49 | 0.14 | No | Not significant; WRONG sign (suggests luxury-up leads FXI-down, which would be INVERTED) |
| 2 | +1.04 | 0.30 | No | Not significant |
| 5 | −0.64 | 0.53 | No | Not significant |

**BH-FDR (α=0.10) survivors: NONE at lag ≥ 1.**

The lag=0 result (t=11.75) confirms the **transmission hypothesis**: luxury and the Chinese
consumer co-move contemporaneously — they share the same global macro drivers in real-time.
But this simultaneous relationship offers no predictive lead. It is a confirmer display signal
("when luxury is falling today, FXI is likely falling today too"), not a de-risk early warning.

---

## Why the de-risk strategy fails

The long/flat strategy on FXI (flat when luxury trend-turn signal > 0.70 pctile) suffers
from a structural timing mismatch:

1. **Luxury trend-turns are not FXI-DD leading indicators.** The rolling 21d basket momentum
   is contemporaneous at best (lag=0 is the only significant cross-market correlation). Going
   flat after seeing luxury decline means going flat as FXI is *already* declining — the
   flat position doesn't reduce the loss already happening.

2. **FXI has a positive long-run drift.** FXI's cumulative return over 2006-2026 is positive
   (Calmar B&H = +0.045). The flat-out strategy misses FXI's recovery periods, producing a
   strategy with NEGATIVE annualized return (Calmar = −0.008). This is the "destroys value"
   pattern from C5/C8 — the Calmar gate catches it.

3. **DSR = 0.16.** The deflated Sharpe measures whether the strategy's risk-adjusted return
   exceeds what N=17 random trials would produce by chance. 0.16 says the signal is
   essentially random in terms of forward drawdown prediction — the rolling momentum of a
   coincident indicator has no forecast power for a coincident target.

---

## Comparison with sibling channels

| Channel | Verdict | DSR | Lead-lag | Key finding |
|---|---|---|---|---|
| C3 Global ETF breadth | CONFIRMED | 0.9326 | n/a | Global breadth leads US DD; residual after SPY/HY/curve |
| C4a REER value | CONFIRMED | 0.9436 | n/a | N=1 resurrection; dollar value predicts USD returns |
| C7 Luxury→CN consumer | **CONTEXT** | 0.1609 | No lag≥1 survivors | Contemporaneous co-movement only; no lead |
| C2 Intl macro sleeve | CONTEXT | 0.8282 | n/a | US legs already capture; DSR below door |
| C5 Global rates | CONTEXT | 0.9797 | n/a | SPY drift (Calmar killer) |
| C8 Leading votes | CONTEXT | 0.981 | n/a | SPY drift (Calmar killer) |

The honest interpretation: the luxury–Chinese consumer link is a **structural real-time
co-movement**, not a predictive lead. The thesis was directionally correct (luxury IS a
policy-undistorted read on China consumer sentiment), but the temporal structure is wrong
(simultaneous, not leading).

---

## Implications and potential future paths

1. **Display confirmer (available now):** The contemporaneous co-movement (t=11.75) is real
   and useful as a display signal — "luxury names are selling off today, consistent with
   Chinese consumer stress." This does not require any de-risk claim; it is pure display
   context.

2. **Earnings-surprise lag (potential future path):** The excision calendar approach here
   removes the print window from the rolling-momentum signal. A separate earnings-surprise
   (actual vs consensus EPS) channel for LVMH prints might carry genuine new information
   about Chinese consumer health — but this would require a new earnings-surprise data source
   and a fresh pre-registered claim, not a re-run of this one.

3. **Corporate guidance channel (future):** LVMH management commentary at results dates
   ("China same-store sales", "travel retail recovery") might carry 1-2 quarter forward
   information that rolling momentum does not. This is the qualitative intelligence domain
   (Claim Passport program), not quantifiable here.

None of these paths represent a re-run of C7. C7 is graded CONTEXT and killed. Any future
luxury channel is a NEW pre-registered claim with a new hypothesis.

---

## Scored seams status

**NOTHING was wired.** The following are unchanged:
- `conditions._macro_risk_legs` (still 5 US legs only)
- `china_name_score._tailwind` (unchanged)
- `stock_score._axis_tailwind` (unchanged)
- `engine/intl_feed.features()` returns weight=0 for C7 (kill=True, CONTEXT verdict)
- `data/intl_bridge/ledger.json` has the C7 entry at weight_cap=0.0, kill=True

The LVMUY parquet is the only new data artifact; it is a data seed (yahoo store), not
a scoring change. Tests verify zero scorer impact.

---

## Files changed

| File | Change |
|---|---|
| `data/yahoo/LVMUY.parquet` | NEW — cold-start seed (5,139 rows, 2006-01-27 to 2026-07-02) |
| `scripts/c7_luxury_readthrough.py` | NEW — EW luxury basket builder + earnings excision + lead-lag kernel |
| `scripts/intl_phase0.py` | ADD `--c7` CLI handler (merges C7 row into ledger) |
| `engine/intl_claims.py` | ADD C7 graded BACKFILL entry in `BACKFILL` list |
| `engine/signal_lab.py` | ADD C7 display-graveyard `_row` entry |
| `research/INTL_FIX_MASTERPLAN.md` | ADD W4-C7 Status log line |
| `reports/intl-luxury-readthrough-phase0.md` | THIS FILE |
| `tests/test_c7_luxury.py` | NEW — 9 tests (causality, excision, no-scorer-wiring, etc.) |

---

*Truthful negatives are success. The C7 thesis was directionally right (luxury is a
policy-undistorted China consumer read) but temporally wrong (simultaneous, not leading).
The system is better for knowing this precisely.*
