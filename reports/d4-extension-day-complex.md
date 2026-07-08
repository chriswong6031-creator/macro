# d4-extension-day-complex — Phase-0 Validation Report
# Family Amendment: d2_rates_calendar_flows

**Family:** d2_rates_calendar_flows (AMENDMENT — D4 extension cells added to confirmed V3)
**Pre-reg:** Lane D4-06 (research SIGNAL_LAB_FRONTIER_DAY2_FABLE_ADJUDICATION_2026-07-06.md,
             V3 month-end extension confirmed; D4 adds LQD + confirmatory AGG/IEI)
**Date run:** 2026-07-08
**V3 construction replicated exactly:** last-business-day return vs same-month
             average-other-day return; one obs per event-date; NW HAC t-stat.

## Pre-registered amendments (filed BEFORE computing)

- AM-D4-1: AGG + IEI absent from data/yahoo/ and data/massive_stock_day/
  (massive_stock_day carries per-day equity files; bond ETFs excluded from store).
  These confirmatory cells are SKIP-DATA on this run.  Per lane: "AGG failure does
  not falsify the family; their index mechanics differ from the Treasury-ladder
  extension."  Data-absent skip = non-falsifying.
- AM-D4-2: BH FDR correction applied jointly to D4 cells + V3 original cells
  (amended family cell-set).  V3 p-values from phase0 report used as anchors:
  v3_tlt_last_day p≈0.0003, v3_tlt_excess p≈0.0009,
  v3_ief_last_day p≈0.0, v3_ief_excess p≈0.0.
- AM-D4-3: LQD date range matches TLT/IEF (2002-07-30 onward); 287-month window.

## Data store verification
```
LQD (yahoo): 6022 rows, 2002-07-30 .. 2026-07-07
AGG (massive_stock_day): skip_data_absent
IEI (massive_stock_day): skip_data_absent
```

**Trial budget:** 2 new D4 configs registered; amended family total = 13 configs (family=d2_rates_calendar_flows)

**Confirmatory cell status:** AGG=skip_data_absent; IEI=skip_data_absent

## D4 — LQD month-end extension (PRIMARY)

Universe: all calendar months in LQD history (2002-2026). Last trading day return vs avg of all other days in the month.  Construction identical to confirmed V3.

```
cell                               n     mean%   t_HAC       p  sign_ok    BH_q  BH_rej
d4_lqd_last_day                  287     0.145   3.631  0.0003     True  0.0004    True
d4_lqd_excess                    287     0.131   3.142  0.0017     True  0.0017    True
d4_lqd_avg_other                 287     0.013   2.137  0.0326      N/A     N/A     N/A
```

**Split-half (G2) — D4 LQD last-day return:**
```
H1: mean=0.2208% (n=143)
H2: mean=0.0689% (n=144)
Same-sign positive: True
GATE G2 D4 LQD: PASS
```

**G3 D4 (last-day mean > avg-other-days baseline, informational):**
  Last-day mean: 0.145%  Avg-other-days mean: 0.013%  PASS

## Confirmatory cells (AGG + IEI)

Per AM-D4-1 and lane pre-declaration: these cells are NON-FALSIFYING.
AGG and IEI are absent from data/yahoo/ and data/massive_stock_day/.
Status: SKIP-DATA (data absent on this run).
Per lane: 'AGG failure does not falsify the family; their index
mechanics differ from the Treasury-ladder extension.'
A data-absent skip is treated as non-falsifying absent evidence.

## BH FDR — amended family cell-set (D4 + V3 anchors)

```
cell                                  p     BH_q   reject
v3_ief_excess                       0.0      0.0     True
v3_ief_last_day                     0.0      0.0     True
d4_lqd_last_day                  0.0003   0.0004     True
v3_tlt_last_day                  0.0003   0.0004     True
v3_tlt_excess                    0.0009   0.0011     True
d4_lqd_excess                    0.0017   0.0017     True
```

## Gate summary (frozen gates per lane, LQD primary)

```
Gate                                                      Result
-----------------------------------------------------------------
G1 BH FDR q<=0.10 (any D4 LQD cell in amended family BH)  PASS
   -> d4_lqd_last_day: q=0.0004, reject=True
   -> d4_lqd_excess: q=0.0017, reject=True
G2 split-half same-sign positive (LQD last-day):          PASS
   H1=0.2208% H2=0.0689%
G4 |t_HAC| >= 2 (d4_lqd_last_day headline):              PASS
   t_HAC = 3.631
-----------------------------------------------------------------
All LQD gates (G1+G2+G4):                                 PASS
Confirmatory AGG/IEI:                                      SKIP-DATA (non-falsifying per AM-D4-1)
```

## VERDICT

**SCORED**

## In plain English

This study extends the confirmed V3 month-end extension finding to corporate bond ETFs.

**Why LQD?** LQD tracks the iBoxx USD Liquid Investment Grade Index — the most liquid
investment-grade corporate bond benchmark.  Like Treasury ETFs (TLT, IEF), LQD is held
widely in bond index funds.  At month-end, index managers who own corporate bonds must
rebalance to the newly extended benchmark duration, creating the same buying pressure
observed for Treasuries.

**The test:** On the last trading day of each month (2002-2026), does LQD return more
than it typically does on other days of the same month?  We use the identical
construction as the confirmed V3 test: collapse to one observation per month, compute
raw return and the excess over the same-month average, apply Newey-West HAC and
Benjamini-Hochberg FDR correction within the amended family.

**Why AGG and IEI are skipped:** AGG (US broad bond aggregate) and IEI (3-7y Treasury)
were pre-declared as confirmatory cells only — a failure would not have falsified the
family in any case.  Both are absent from the available data stores and are therefore
skipped on this run.  This skip is equivalent to a non-result, consistent with the
pre-declaration.

A null result is a successful test.

## Family amendment record

**Amendment to d2_rates_calendar_flows:**
- D4 cells (LQD primary, AGG/IEI confirmatory) added to the family.
- All D4 cells participate in the joint BH FDR correction with existing V3 cells.
- This amendment does NOT alter the V3 SCORED verdict; it adds evidence.
- If LQD SCORES: LQD month-end extension is a confirmed generalization of the
  Treasury-ladder finding, strengthening the mechanism (index-rebalancing flows
  drive cross-asset bond ETF returns on the last business day of the month).
- Nightly wiring: if SCORED, add `month_end_extension_signal()` to cover LQD
  alongside TLT; no new data collection needed (LQD already in yahoo store).
