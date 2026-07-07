# EXIT-TAX-SCENARIOS — Scenario After-Tax Table Report

**Derived from surfaces:** exit_grid_v1, wait_grid_v1, long_hold_labels.parquet
**Run date:** 2026-07-06
**Verdict criteria:** descriptive-only
**Registry note:** Research-lane scenario analysis. No new registered experiment. No new trial cells. This is NOT tax advice.

---

## IMPORTANT: SCENARIO ANALYSIS, NOT TAX ADVICE

Symbolic tax rates are illustrative assumptions for scenario comparison. Real tax outcomes depend on jurisdiction, holding period election, tax lots, wash-sale rules, entity type, income level, and many other factors. Nothing in this report constitutes tax advice. Consult a qualified tax professional.

---

## The question (RUL-F3.10)

> Does short-term-rate churn at hold(21)-recycling erase its gross edge vs deferring into long-term treatment at 252d+ holds?

---

## House law: ALL exit-grid holds are SHORT-TERM

**All exit-grid cells (≤126 bars = ≤6 calendar months) are short-term by construction in US tax law.** The within-grid "tax kink" is zero — every exit-grid cell faces the same ST rate regardless of which cell is chosen. The ST vs LT comparison only becomes meaningful at the 252d (≈1 year) horizon. This is stated plainly and labeled throughout.

---

## In plain English

> At a 35% short-term rate, hold(21) recycled 12 times per year compounds to about 16.1% annual after-tax vs 25.8% gross. Hold(126) recycled ~2x/yr computes to about 9.7% after-tax at the same 35% rate vs 15.1% gross. The tax drag on shorter-cycle exit policies is larger in absolute bps terms because the same rate applies to more events per year. For the long-hold comparison, the honest cohort (n=2,105 fires with valid 252d returns, not survivor-biased) shows a 36.8% gross annual return; at the illustrative ST=35%→LT=20% pairing, the long-hold net is about 29.5% annual. These numbers reflect a specific cohort window (massive-era fires, 2021+) and should not be read as representative of all long-hold outcomes. The survivor-biased cohort (n=11,110) is an UPPER BOUND only.

---

## Scenario rates

Symbolic scenario rates used: **0%, 15%, 20%, 35%, 40%**.

These are not jurisdiction verdicts. The ST→LT pairing (illustrative, US-style):

| ST scenario | LT pair (illustrative) |
|---|---|
| 0% | 0% |
| 15% | 15% |
| 20% | 15% |
| 35% | 20% |
| 40% | 20% |

---

## Exit-grid hold_21 — short-term recycling (~12 cycles/yr)

Source: exit_grid_v1/hold_21 (confirmed by wait_grid_v1 delay1_hold21)
- Gross mean return per cycle: +1.93%
- WR: 0.577
- n fires: 49,939
- Cycles per year: 252/21 ≈ 12.0

| ST rate | Gross annual (compounded) | After-tax annual | Tax drag (bps/yr) |
|---|---|---|---|
| 0% | 25.8% | 25.8% | 0 |
| 15% | 25.8% | 21.6% | 422 |
| 20% | 25.8% | 20.2% | 560 |
| **35%** | **25.8%** | **16.1%** | **965** |
| 40% | 25.8% | 14.8% | 1,097 |

---

## Exit-grid hold_126 — short-term reference (~2 cycles/yr)

Source: exit_grid_v1/hold_126
- Gross mean return per cycle: +7.32%
- WR: 0.590
- Cycles per year: 252/126 ≈ 2.0

| ST rate | Gross annual (compounded) | After-tax annual | Tax drag (bps/yr) |
|---|---|---|---|
| 0% | 15.1% | 15.1% | 0 |
| 15% | 15.1% | 12.8% | 234 |
| 20% | 15.1% | 12.0% | 311 |
| **35%** | **15.1%** | **9.7%** | **542** |
| 40% | 15.1% | 9.0% | 618 |

**Observation (descriptive only):** hold(21) shows higher absolute tax drag per year than hold(126) at the same ST rate because 12 taxable events/yr vs 2 taxable events/yr. At 35%, hold(21) loses ~965 bps/yr to tax vs ~542 bps/yr for hold(126). This does not make hold(21) inferior; gross compounded returns also differ (25.8% vs 15.1%). No verdict is drawn.

---

## Long-hold 252d — LT rate scenario

**Important survivorship note:** The 252d cohort is split by survivorship_biased.

### Honest cohort (survivorship_biased = False)

n = 2,105 fires with valid total_return_252d
n episode clusters = 2,412 (from manifest)
Gross mean 252d return: +36.8% | Median: +17.2% | WR: 0.660

| ST scenario | LT paired rate | Gross annual | After-tax annual (LT) | Tax drag (bps/yr) |
|---|---|---|---|---|
| 0% | 0% | 36.8% | 36.8% | 0 |
| 15% | 15% | 36.8% | 31.3% | 553 |
| 20% | 15% | 36.8% | 31.3% | 553 |
| **35%** | **20%** | **36.8%** | **29.5%** | **737** |
| 40% | 20% | 36.8% | 29.5% | 737 |

### Survivor-biased cohort — UPPER BOUND only

n = 11,110 fires with valid total_return_252d
Gross mean 252d return: +43.9% | Median: +22.3% | WR: 0.732

**These are UPPER BOUND figures.** The survivor-biased cohort includes only names that matured to 252d with valid outcomes; delisted/failed names are underrepresented. True long-hold performance is lower.

| ST scenario | LT paired rate | Gross annual | After-tax annual (LT) | Tax drag (bps/yr) |
|---|---|---|---|---|
| 0% | 0% | 43.9% | 43.9% | 0 |
| 15% | 15% | 43.9% | 37.3% | 659 |
| 20% | 15% | 43.9% | 37.3% | 659 |
| **35%** | **20%** | **43.9%** | **35.1%** | **878** |
| 40% | 20% | 43.9% | 35.1% | 878 |

---

## Tax kink summary

The "kink" question: does the LT rate reduction at 252d change the comparison vs ST churn?

At ST=35%, LT=20% (illustrative pairing):
- hold(21) recycled 12x/yr: gross 25.8% → after-tax ST 16.1%
- hold(126) recycled 2x/yr: gross 15.1% → after-tax ST 9.7%
- 252d hold (honest, n=2,105): gross 36.8% → after-tax LT 29.5%

**The kink appears at the 252d comparison only** — within the exit-grid (all ≤126 bars), every cell faces the same ST rate. The 252d gross is substantially higher because the cohort is different (long-hold thesis, not Oracle-fire reversion), not because of the holding period per se.

This report draws no verdict on which policy is superior. The tax scenario is one of many factors that depend on investor circumstances.

---

## Cohort notes

- Exit-grid fires: 49,939 verdict_grade=True fires from replay_boarded.parquet (massive-era, 2021-07-06+), 100% coverage, survivorship caveat: dead_name_coverage ~38%.
- Long-hold 252d cohort: from long_hold_labels.parquet (113,542 total rows; 2,105 honest fires with valid total_return_252d; 11,110 survivor-biased). The honest cohort is the decision-relevant number for any forward-looking analysis.

---

## Output artifact

`data/execution/exit_tax_scenarios.json` — machine-readable scenario table with all cohorts, rates, gross/net figures, and metadata.
