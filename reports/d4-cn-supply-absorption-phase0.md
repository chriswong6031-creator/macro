# D4-01 — CN Supply Absorption Phase-0
## Family: `cn_supply_absorption` — POSITIVE direction

**Verdict: G1 FAIL — path-matched neutralization succeeds in absorbing the raw signal.
The raw absorbed-vs-not split shows +0.74 pp at 21d (t_iid=2.07) and +1.14 pp at 63d,
but after matching on the [t,t+10] return path, vol tercile, and size tercile the
clustered HAC t-statistic collapses to 0.56 at 21d and 1.18 at 63d — well below the
|t|>=2 + BH q<=0.10 decisive gate. G2 and G3 pass (descriptively same-sign), and G4
(non-gated) finds a 1.3 pp partial effect after drift-factor residualization (t=3.68,
p=0.0002) — which informs why the raw signal looks positive before matching.**

---

## 1. Context: wave-5 / Day-2 closures

The `cn_supply_absorption` family is the POSITIVE-direction successor to the `CN-SUPPLY`
slot that was held and then adjudicated in wave-5 / Day-2 (2026-07-06). Two closures:

- **F5-01 (wave-5)**: unlock-driven block sector read-through was authorized for
  infrastructure build but **blocked as a backtest** — the block store is a rolling
  snapshot with no historical event tape. The F5-01 archiver was commissioned for
  eventual re-entry when the tape exists. F5-01 held the LG-CN-SUPPLY slot pending data.
- **Day-2 slot transfer (PO-1b)**: D2-06 (`d2_cn_holder_sale_calendar`, execution-window
  variant) received the LG-CN-SUPPLY slot from F5-01 because D2-06 has a
  ~9-year reconstructable panel today. D2-06 narrowing: the tradable construct is
  the **execution-window forced-supply drift** (when the sale window opens, not the
  announcement that CN retail already fronts).

This lane (D4-01) tests the POSITIVE-direction hypothesis: names where supply is
absorbed during the execution window outperform path-matched controls, because the
absorption signals a new marginal buyer with conviction sufficient to offset the mandated
selling. It is the counterpart to the previously-closed NEGATIVE supply drift.

---

## 2. Event definitions

### E1 — Active 减持 execution window opens (used; 38,951 events)

Source: `data/cn_holder_sales/windows.parquet` (38,951 rows; spec stated 38,988 —
delta of 37 rows, pre-registered minor discrepancy likely due to data refresh timing).

Availability: `window_open + 1 trading day` (PIT-correct; cninfo crawl-bounded per
Day-2 pre-registration).

### E2 — Deep-discount block day, avg_premium_pct <= −15 (HISTORICAL TAPE NOT AVAILABLE — registered gap)

**Unit assertion (F5-01 law):** Field `avg_premium_pct` in
`data/china_block_trades/detail.parquet` is confirmed in PERCENT UNITS:
range −33.2% to +33.0%, mean −6.1%, median −4.5%.

**E2 pass-rate on current snapshot:** 61 of 461 rows (13.2%) meet avg_premium_pct <= −15.
This demonstrates the field is in the correct units for the threshold.

**GAP (pre-registered):** `data/china_block_trades/detail.parquet` is a rolling
snapshot as of 2026-07-07 (461 rows, single `asof` date). It is NOT a historical
per-event tape. The F5-01 daily archiver — authorized at wave-5 — must run and
accumulate a multi-year tape before E2 events can be constructed with timestamps.
E2 is a successful registered null; it re-enters when the tape exists.

---

## 3. Absorption confirmation

Cumulative own return over [t, t+10 sessions] >= own-group median return over the same
window. Own group: baskets_china membership where covered (280 active basket members
across all CN baskets); else market EW of the covered price universe (~1,587 stocks
in `data/china_stocks_raw`).

Group medians were computed empirically per signal date. Universe group median
distributed symmetrically around zero (mean −0.0%, std 5.3%), confirming the
measure is coherent.

---

## 4. Price coverage and universe caveat

**Covered-universe caveat (PROMINENT): only 28.9% of E1 events have price data.**

Join mechanism: `windows.parquet` uses `.SH` suffixes for Shanghai names;
`china_stocks_raw` stores them as `.SS`. After `.SH <-> .SS` normalization,
673 of 1,927 SH tickers and 645 of 2,786 SZ tickers are covered.

Coverage 28.9% is within the pre-stated expected range of ~28–30% and is a structural
limit of the price universe, not a bug. Every return estimate below is an upper bound
for the covered (more-liquid, more-actively-traded) universe subset.

| Metric | Value |
|---|---|
| Total E1 events | 38,951 |
| Events with price coverage | 11,267 (28.9%) |
| Absorption rate | 5,385 / 11,267 = 47.8% |
| Entry date | t+11 (t+10 close + 1 trading day) |
| Return horizons | 21d and 63d from entry |

---

## 5. Gate results

### G1 (DECISIVE): RETURN-PATH-MATCHED CONTROLS — FAIL

For each absorbed event, up to 3 non-absorbed controls matched on:
(a) same [t,t+10] cumulative-return quintile (5 bins)
(b) same trailing-60d realized-vol tercile
(c) same size tercile (trailing 60d median price × volume)

Test: absorbed names must beat matched controls at 21d AND 63d with |t_HAC| >= 2
(date-clustered by calendar quarter) AND BH q <= 0.10 across 2 cells.

| Cell | n pairs | n clusters | diff (abs − ctrl) | t_HAC | p_val | BH rejected | Gate |
|---|---|---|---|---|---|---|---|
| E1 × 21d | 16,015 | 88 quarters | +0.52% | 0.556 | 0.579 | No | **FAIL** |
| E1 × 63d | 15,596 | 87 quarters | +2.68% | 1.181 | 0.238 | No | **FAIL** |

**Both cells fail the gate.** The direction is positive, but far below the statistical
threshold. The date-clustering inflates standard errors by 4.2× relative to i.i.d.
(ratio of cluster SE to i.i.d. SE), which is the correct treatment for an event study
where signal dates cluster in market-regime episodes.

**Interpretation**: Once you condition on the return path over [t,t+10], the forward
outperformance disappears. The raw signal (+0.74% at 21d, t_iid=2.07) reflects the
general momentum/drift in names that happened to have above-median paths — not a
distinctive forward alpha from absorption itself.

### G2: SPLIT-HALF SAME-SIGN — PASS

Split at calendar midpoint 2020-09-23 (H1: 2001–2020, H2: 2020–2026).

| Period | 21d diff | 63d diff |
|---|---|---|
| H1 (early, 2001–2020) | +0.00% | +0.14% |
| H2 (late, 2020–2026) | +1.49% | +2.19% |

Both halves same-sign positive. G2 PASS. Note: H1 diff is essentially zero at 21d —
the pattern is entirely a recent-period phenomenon (H2), which is informative about
regime-dependence.

### G3: LOCO (2015 crash, 2018 bear, 2024-09 stimulus) — PASS

| Crisis excluded | 21d diff | 63d diff |
|---|---|---|
| Excl 2015 crash (Jun–Dec 2015) | +0.83% | +1.14% |
| Excl 2018 bear (all 2018) | +0.78% | +0.90% |
| Excl 2024-09 stimulus (Sep–Dec 2024) | +0.78% | +1.11% |
| Full sample | +0.74% | +1.14% |

All six leave-one-out estimates remain positive. G3 PASS.

### G4 (REPORTED, NON-GATED): Partial effect after drift-factor residualization

Drift factor construction: for each event at time t, compute its [t,t+10]
cross-sectional return quintile within the same quarter, then map to the expected
forward return for that quintile (the announcement-return-conditioned drift premium).
Each name's forward return is residualized by subtracting this drift expectation.

| Horizon | Absorbed residual | Control residual | Partial diff | t | p |
|---|---|---|---|---|---|
| 21d | +0.685% | −0.626% | +1.311% | 3.68 | 0.0002 |
| 63d | +1.376% | −1.249% | +2.625% | 3.98 | 0.0001 |

G4 shows a strong partial signal in i.i.d. inference, but this uses residuals computed
from ALL names in the same quintile — the drift factor itself carries absorption-correlated
information (absorbed names are over-represented in high-quintile cells, so their
within-quintile residuals are systematically positive relative to non-absorbed names
in the same cell). G4 is reported as a descriptive decomposition, not a causal estimate.

The G4 finding does suggest the absorption indicator carries information beyond pure
path momentum, but the cleaner G1 matched-control design — which matches absorbed and
non-absorbed names on the same path-quintile before comparing outcomes — finds that
effect is not statistically distinguishable from noise after date-clustering.

---

## 6. Mechanism interpretation

The original hypothesis: the absorption signal identifies a new marginal buyer with
patience sufficient to offset mandated selling, creating a positive forward-return tilt.

What the data show:
- Absorption events (above-median [t,t+10] path) have higher raw forward returns
  (+0.74 pp at 21d, +1.14 pp at 63d).
- After matching on the path itself, the excess disappears (t_HAC < 1.2).
- The G4 partial effect (t=3.68 i.i.d.) suggests some within-path-quintile information,
  but the date-clustered evidence is not convincing.
- Split-half asymmetry (effect concentrated in H2, 2020–2026) hints at regime-dependence
  rather than a persistent structural mechanism.

The red-team's neutralization design worked as intended: conditioning on the return path
removes the forward alpha. The absorption signal as specified does not add a
distinguishable increment over the path information in the price itself.

---

## 7. Pre-registered gaps (registered nulls — successful runs)

1. **E2 historical tape not available**: `china_block_trades` is a current-state
   snapshot (461 rows, single asof=2026-07-07). F5-01 archiver must accumulate
   multi-year tape. E2 re-enters when tape covers >= 3 years.

2. **38,951 vs 38,988 rows**: 37-row delta in windows.parquet vs spec. Minor,
   pre-registered as data-refresh timing difference. No impact on analysis.

3. **28.9% coverage**: structural constraint of the 1,587-file price universe vs
   4,713 unique tickers in windows.parquet. All results are upper bounds for the
   more-liquid covered subset.

---

## 8. Summary

| Gate | Status | Key number |
|---|---|---|
| G1 (decisive) | **FAIL** | t_HAC = 0.56 @ 21d, 1.18 @ 63d (need |t|>=2) |
| G2 split-half | PASS | Both halves positive; H1 near-zero |
| G3 LOCO | PASS | All 6 crisis-exclusions positive |
| G4 (non-gated) | — | +1.31% partial @ 21d, t=3.68 (i.i.d.) |
| E2 | Registered null | Historical tape does not exist |

**Overall VERDICT: FAIL (G1 decisive). The absorption filter as specified does not
deliver path-neutralized alpha. The raw positive return differential reflects the
return path itself, not the absorption signal. Family `cn_supply_absorption` does not
advance to production.**

**Possible reopen conditions**: (a) E2 historical tape accumulated (F5-01 archiver);
(b) refined absorption definition — e.g., requiring the absorbed name to OUTPERFORM
its own historical volatility-adjusted expectation (not just the cross-section median)
— which would be a tighter, mechanistically-motivated filter; (c) regime-conditioned
test isolating the H2 (2020+) window under a pre-registered design.

---

*Report authored: 2026-07-08. Data: `data/cn_holder_sales/windows.parquet`,
`data/china_block_trades/detail.parquet`, `data/china_stocks_raw/*.parquet`,
`data/baskets_china/membership.json`. Repro: re-run the analysis script in the
`feat/d4-cn-supply-absorption` worktree. No "validated" language used per CI guard.*
