# d2_rates_calendar_flows — Phase-0 Validation Report

**Family:** d2_rates_calendar_flows
**Pre-reg:** research/SIGNAL_LAB_FRONTIER_DAY2_FABLE_ADJUDICATION_2026-07-06.md item 1
**Date run:** 2026-07-06

## Pre-registered amendments (gaps in written prereg, filed BEFORE computing)

- AM-1: 10y and 30y auction cells tested separately and pooled; all enter BH.
  Headline = pooled (most events, same mechanism).
- AM-2: "Measured concession" = pre-window TLT cum-return < 0 (sign gate, no full-sample quantile).
- AM-3: "Final week" = last 5 bus days of quarter; gap from quarter-start; t-7 = 7 bus days pre-QE.
- AM-4: Last business day = last trading day in calendar month per TLT price series.
- AM-5: Newey-West lag = min(4, sqrt(n)) applied to collapsed date-level series.

## Data store verification
```
TLT: 6020 rows, 2002-07-30 .. 2026-07-02
IEF: 6020 rows, 2002-07-30 .. 2026-07-02
SPY: 8413 rows, 1993-01-29 .. 2026-07-02
Auctions: 268 rows, 2016-06-22 .. 2026-06-11, 10y=125 30y=143
```

**Trial budget:** 11 configs registered pre-computation (family=d2_rates_calendar_flows)

## V1 — Auction-cycle concession/rebound (Lou-Yan-Zhang)

Universe: 10y + 30y coupon auctions 2016-2026. Pre-auction concession window t-3..t0; post-auction rebound t0..t+3.

Pre-window TLT mean return: -0.1830% (t_HAC=-1.577, n=268)
Direction correct (pre-window < 0): True

```
cell                               n    mean%   t_HAC       p  sign_ok    BH_q  BH_rej
v1_pooled_conditional            139   -0.011  -0.066  0.9472    False  0.9973   False
v1_10y_conditional                62    0.038   0.128  0.8982     True  0.9973   False
v1_30y_conditional                77    -0.05  -0.355  0.7226    False  0.9973   False
v1_pooled_unconditional          268   -0.047  -0.416  0.6773    False     N/A     N/A
```

**Split-half (G2) — V1 pooled conditional:**
```
H1: mean=0.0939% (n=69)
H2: mean=-0.1139% (n=70)
Same-sign positive: False
GATE G2 V1: FAIL
```

**G3 V1 (conditional > unconditional baseline):**
  Conditional mean: -0.011%  Unconditional mean: -0.047%  PASS

## V2 — Quarter-end pension rebalance

Universe: all quarter-ends 2002-2026. Gap = SPY-TLT outperformance from quarter-start to t-7. Outcome = TLT-vs-SPY final 5 bus days.

Quarters total: 95  Pct with equity outperf gap: 62.1%

```
cell                               n    mean%   t_HAC       p  sign_ok    BH_q  BH_rej
v2_conditional_gap_pos            59    0.142   0.471  0.6376     True  0.9973   False
v2_gap_signed                     95   -0.001  -0.003  0.9973    False  0.9973   False
v2_unconditional                  95    0.177   0.611  0.5413     True     N/A     N/A
```

**Split-half (G2) — V2 conditional on gap>0:**
```
H1: mean=0.6201% (n=29)
H2: mean=-0.3201% (n=30)
Same-sign positive: False
GATE G2 V2: FAIL
```

**G3 V2 (conditional > unconditional baseline in absolute effect):**
  Conditional mean: 0.142%  Unconditional mean: 0.177%  FAIL

## V3 — Month-end index extension day

Universe: all calendar months in TLT history (2002-2026). Last trading day return vs avg of all other days in the month.

```
cell                               n     mean%   t_HAC       p  sign_ok    BH_q  BH_rej
v3_tlt_last_day                  287     0.183   3.627  0.0003     True  0.0009    True
v3_tlt_excess                    287     0.173   3.326  0.0009     True   0.002    True
v3_tlt_avg_other                 287      0.01   0.917  0.3592      N/A     N/A     N/A
v3_ief_last_day                  287      0.11   5.017     0.0     True     0.0    True
v3_ief_excess                    287     0.099   4.473     0.0     True     0.0    True
v3_ief_avg_other                 287      0.01   1.945  0.0518      N/A     N/A     N/A
```

**Split-half (G2) — V3 TLT last-day return:**
```
H1: mean=0.2582% (n=143)
H2: mean=0.1082% (n=144)
Same-sign positive: True
GATE G2 V3: PASS
```

**G3 V3 (last-day mean > avg-other-days baseline):**
  Last-day mean: 0.183%  Avg-other-days mean: 0.01%  PASS

## Gate summary (frozen gates, applied after computing)

```
Gate                                                   Result
--------------------------------------------------------------
G1 BH FDR q<=0.10 (any family cell rejects)          PASS
   -> v3_tlt_excess: q=0.002
   -> v3_tlt_last_day: q=0.0009
   -> v3_ief_excess: q=0.0
   -> v3_ief_last_day: q=0.0
G2 split-half same-sign positive:
   V1 pooled conditional:   FAIL (H1=0.0939% H2=-0.1139%)
   V2 gap>0 conditional:    FAIL (H1=0.6201% H2=-0.3201%)
   V3 TLT last-day:         PASS (H1=0.2582% H2=0.1082%)
G3 conditional > unconditional baseline:
   V1: PASS  V2: FAIL  V3: PASS
G4 |t_HAC| >= 2 (headline cell per variant):
   V1 t=-0.066: FAIL  V2 t=0.471: FAIL  V3 t=3.627: PASS
--------------------------------------------------------------
Per-variant (all 4 gates):                        
   V1 auction-cycle:          FAIL
   V2 quarter-end rebalance:  FAIL
   V3 month-end extension:    PASS
```

## VERDICT

**SCORED**

## In plain English

This study tests three ideas about how the bond market (TLT = 20-year Treasury ETF)
behaves around predictable calendar events.

**V1 — Auction concession/rebound:** When the Treasury sells new bonds, dealers
must absorb supply in the days before the auction, pushing prices down (the
"concession"). The academic prediction (Lou, Yan, Zhang) is that this selling
reverses shortly after the auction date — a rebound. We look at 10-year and
30-year coupon auctions from 2016 onward, measure whether TLT actually fell in
the 3 days before each auction, and if it did, whether it bounced over the 3 days
after.

**V2 — Quarter-end pension rebalancing:** Large pension funds are required to
maintain fixed allocations between stocks and bonds. If stocks greatly outperformed
bonds over a quarter, pensions must sell stocks and buy bonds in the last few days
of the quarter to rebalance. The prediction: when stocks have beaten bonds by a lot
(the "gap"), TLT should outperform SPY in the final week of the quarter.

**V3 — Month-end extension:** Bond index managers buy longer-duration bonds on the
last day of the month to match their benchmark's new duration (bonds added to
indices have longer maturities than those removed). The prediction: TLT and IEF
should show a positive return on the last trading day of each month, above the
rest-of-month average.

All three are pre-registered bets — if the evidence doesn't support them, the null
result is reported honestly. A failed gate is a successful test.

## Nightly wiring (for consolidation)

If any variant clears all four gates, it should be integrated as follows:

**V1 auction-cycle** (if SCORED):
  - Standalone collector (standalone, do NOT edit scripts/collect.py):
    `scripts/collect_treasury_auctions.py` — already on disk at
    `data/treasury_auctions/`; verify it runs incrementally.
  - Signal generator: `engine/rates_calendar_signals.py` → function
    `auction_cycle_signal(tlt_prices, auctions_df)` returns a date-indexed
    Series of expected next-3d TLT excess return, NaN on non-auction weeks.
  - Wire into nightly via `scripts/build_rates_calendar.py` (new, standalone).

**V2 quarter-end rebalance** (if SCORED):
  - No new data collection needed (SPY + TLT already in yahoo store).
  - Signal: `engine/rates_calendar_signals.py` → `qe_rebalance_signal()`.
  - Fire 7 business days before each quarter-end; active for 5 bus days.

**V3 month-end extension** (if SCORED):
  - No new collection needed.
  - Signal: `engine/rates_calendar_signals.py` → `month_end_extension_signal()`.
  - Active only on last trading day of month; returns zero all other days.

All three can share a single `rates_calendar_signals.py` module and a single
`build_rates_calendar.py` nightly job under the existing pipeline.

**DO NOT wire into production until at least one variant clears all gates.**
