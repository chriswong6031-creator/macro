# China Policy Events — Phase-0 Report

**Pre-registration:** `research/CHINA_POLICY_EVENTS_PREREG.md` (committed before any outcome computation — git timestamp is proof)
**Study date:** 2026-07-06
**Script:** `scripts/china_policy_events_phase0.py`
**Results JSON:** `data/experiments/china_policy_events_results.json`

---

## DATE SEMANTICS — Read This First

Before any outcome was computed, the REPORT_DATE column in `data/china_macro/rrr.parquet` was verified against known PBoC announcements.

**Finding: REPORT_DATE = ANNOUNCE DATE (not effective date).**

Evidence:
- 2008-10-08: PBoC announced; effective 2008-10-15. REPORT_DATE = announcement.
- 2020-01-01 (New Year holiday, non-trading day): REPORT_DATE matches the announcement.
- 2018-10-07 (Sunday, non-trading): REPORT_DATE is the weekend announcement day.
- 2012-02-18, 2015-04-19, 2018-06-24: all weekends, all announcement days.

Announcement precedes effective date by 1–10 business days. Measuring from the first close **after the announcement** captures the market's immediate reaction to the policy signal — the economically appropriate anchor. Effective-date entry would understate the announcement-day drift.

Verified and cached: `data/experiments/rrr_date_semantics_check.json`

> **In plain English:** PBoC typically says "we're cutting the reserve ratio" on a Monday, and the cut takes effect the following weekend or week later. We use the announcement date because that's when the market hears the news. Using the effective date would be like measuring a stock's reaction to an earnings release starting a week after it came out.

---

## Events

| Family | Description | Episodes | Coverage |
|---|---|---|---|
| F-A RRR ease | rrr_change < 0 | **26** | 2008-10-08 → 2025-05-07 |
| F-B LPR cut | 1y or 5y diff < 0 | **15** | 2019-08-20 → 2025-05-20 |
| F-X RRR hike | rrr_change > 0 | 27 | 2006–2011 era (exploratory only) |
| F-C MPC communiques | communiques.parquet | — | **BLOCKED-DATA** |

Event counts match prereg (26/15). Same-date merge applied within each family.

F-C is BLOCKED-DATA because `data/china_official/communiques.parquet` was absent on main when the study started. Per prereg: if the file is absent, verdict = BLOCKED-DATA — do not wait.

---

## Results

### Gated Trials — Verdict at H=20

Six pre-registered trials. BH-FDR applied across all six H=20 p-values.

| Trial | K usable | Mean CAR | HAC-t | BH-q | DSR | Split-half | **Verdict** |
|---|---|---|---|---|---|---|---|
| T1: F-A → SHCOMP abs | 26 | −0.12% | −0.089 | 0.78 | — | — | **NO-GO** |
| T2: F-A → banks rel | 20 | +0.39% | 0.554 | 0.78 | 0.11 | inconsistent | **ACCRUE** |
| T3: F-A → real estate rel | 26 | −1.21% | −1.441 | 0.93 | — | — | **NO-GO** |
| T4: F-B → SHCOMP abs | 15 | −0.25% | −0.392 | 0.78 | — | — | **NO-GO** |
| T5: F-B → banks rel | 15 | +0.53% | 1.007 | 0.78 | 0.12 | **consistent** | **ACCRUE** |
| T6: F-B → real estate rel | 15 | +0.08% | 0.145 | 0.78 | 0.06 | inconsistent | **ACCRUE** |

No trial clears the full gate cascade. No verdict of GO.

Note on T2 (K=20 vs 26 events): The Shenwan banks sector panel starts 2014-02-21. Six RRR eases before that date (2008, 2011, 2012) have no usable window. K=20 is the honest usable count.

> **In plain English:** We asked six questions: Do RRR cuts lift the market? Do they lift banks? Do they lift real estate? Same three questions for LPR cuts. None of the answers are strong enough to act on yet. Three families returned negative mean returns (wrong sign = NO-GO). Three returned positive mean returns but the signal is too weak to clear our statistical bars (ACCRUE = "promising but unproven — let more events accumulate").

### BH-FDR Summary

No trial has q ≤ 0.10. The smallest q is 0.78 (applied uniformly after BH monotone enforcement). The six H=20 p-values:

| Trial | one-sided p | BH-q | Reject? |
|---|---|---|---|
| T5 FB banks rel | 0.157 | 0.78 | No |
| T2 FA banks rel | 0.290 | 0.78 | No |
| T6 FB restate rel | 0.442 | 0.78 | No |
| T4 FB SHCOMP | 0.652 | 0.78 | No |
| T1 FA SHCOMP | 0.535 | 0.78 | No |
| T3 FA restate rel | 0.925 | 0.93 | No |

---

## Horizon Curves (Descriptive)

Verdict is AT H=20 only. The curves below are descriptive — not a menu for fishing.

### F-A RRR Ease → SHCOMP (absolute)

| H | K | Mean CAR | HAC-t |
|---|---|---|---|
| 5 | 26 | −0.20% | −0.258 |
| 10 | 26 | +0.33% | 0.364 |
| **20** | 26 | **−0.12%** | **−0.089** |
| 40 | 26 | +3.39% | 2.348 |
| 60 | 26 | +1.23% | 0.769 |

The H=40 result (t=2.35) is a descriptive observation only — it was not pre-registered and cannot be used as a verdict. It will be noted in the come-back review for potential pre-registration of an H=40 study.

### F-B LPR Cut → Banks rel (strongest accruing trial)

| H | K | Mean CAR | HAC-t |
|---|---|---|---|
| 5 | 15 | +0.14% | 0.393 |
| 10 | 15 | −0.18% | −0.251 |
| **20** | 15 | **+0.53%** | **1.007** |
| 40 | 15 | +0.48% | 0.707 |
| 60 | 15 | +0.09% | 0.130 |

---

## Exploratory Legs (NOT gated, NOT in FDR family)

### F-X RRR Hikes (exploratory, labeled)

K=27 | Mean CAR = −1.32% | HAC-t = not computed (exploratory)

Easing events (F-A) did not produce positive SHCOMP drift at H=20 (mean = −0.12%). Hiking events show −1.32%. The asymmetry is directionally consistent with the hypothesis (hikes drag, eases don't lift) but the null result for eases means the mechanism claim is not confirmed.

### 510300 ETF (descriptive repeat)

F-A: 12 events with ETF coverage (2012+), mean = not the verdict instrument.
F-B: all 15 events have ETF coverage. Qualitatively similar to SHCOMP results.

### F-C MPC Communiques

**BLOCKED-DATA** — `data/china_official/communiques.parquet` is absent. Per prereg, this is the correct status. Do not compute outcomes speculatively.

---

## Conditioning Tables (Descriptive Only — No t-stats, No Verdict Language)

Regime at event date (last known quad/liquidity/cycle). Cells with n < 5 show n only.

### F-A RRR Ease → SHCOMP abs CAR@H20 by Quad

Regime quad labels: Q1=goldilocks (GG), Q2=reflationary, Q3=stagflation, Q4=recessionary.

| Quad | n | Mean CAR | Median CAR |
|---|---|---|---|
| Q1 | 11 | +0.64% | +3.24% |
| Q2 | 4 | n=4 | — |
| Q3 | 3 | n=3 | — |
| Q4 | 8 | −0.79% | −0.77% |

### F-A RRR Ease → SHCOMP by Liquidity Regime

| Liquidity | n | Mean CAR | Median CAR |
|---|---|---|---|
| contracting | 8 | −3.44% | −2.69% |
| expanding | 11 | +1.59% | +0.99% |
| neutral | 7 | +1.00% | +0.01% |

### F-A RRR Ease → Banks rel CAR@H20 by Quad

| Quad | n | Mean CAR | Median CAR |
|---|---|---|---|
| Q1 | 8 | +0.16% | −0.15% |
| Q2 | 4 | n=4 | — |
| Q3 | 3 | n=3 | — |
| Q4 | 5 | +2.35% | +2.90% |

### F-A RRR Ease → Banks rel by Sector Phase (partial 2014+)

| Phase | n | Mean CAR | Median CAR |
|---|---|---|---|
| Downturn | 7 | +0.22% | +0.04% |
| Trough | 10 | +0.51% | +0.19% |
| Expansion | 1 | n=1 | — |
| Peak | 1 | n=1 | — |
| Recovery | 1 | n=1 | — |

### F-B LPR Cut → SHCOMP abs CAR@H20 by Quad

| Quad | n | Mean CAR | Median CAR |
|---|---|---|---|
| Q1 | 6 | −1.24% | −1.17% |
| Q2 | 1 | n=1 | — |
| Q3 | 3 | n=3 | — |
| Q4 | 5 | +2.23% | +3.83% |

### F-B LPR Cut → Banks rel CAR@H20 by Quad

| Quad | n | Mean CAR | Median CAR |
|---|---|---|---|
| Q1 | 6 | +2.47% | +2.54% |
| Q2 | 1 | n=1 | — |
| Q3 | 3 | n=3 | — |
| Q4 | 5 | −0.74% | −1.21% |

### F-B LPR Cut → Banks rel by Liquidity Regime

| Liquidity | n | Mean CAR | Median CAR |
|---|---|---|---|
| contracting | 5 | −1.32% | −1.21% |
| expanding | 8 | +1.10% | +0.19% |
| neutral | 2 | n=2 | — |

(Full conditioning tables in `data/experiments/china_policy_events_results.json`.)

> No t-stats. No verdict language. Descriptive only. Cells n<5 print n only.

### Sector Cycle Phase (2010 → partial coverage)

Banks sector (801780) phase at F-A event date — see table above. Banks backfill starts 2014-05-30, so most cells are thin. Many F-A events (2008–2013) have no phase data.

(See JSON for full breakdown — many cells n<5 and show n only.)

> **In plain English:** We looked at whether the results change depending on the macro regime at the time of the policy announcement (growth/inflation quad, liquidity regime, cycle phase). The conditioning tables are purely descriptive — no conclusions. With small sample sizes, patterns are unreliable noise. A future amendment with its own pre-registered budget would be required before any conditioning cell could graduate to a formal claim.

---

## Forward Accrual Registry

Three ACCRUE families registered in `data/experiments/registry_seed.json`:

| ID | Come-back | Rationale |
|---|---|---|
| `china-policy-events-fa-banks-rel` | 2028-07-01 | Need ~6 more RRR events for power |
| `china-policy-events-fb-banks-rel` | 2027-07-01 | Need ~3-4 more LPR cuts (T5 strongest) |
| `china-policy-events-fb-restate-rel` | 2029-01-01 | Very weak signal (HAC_t=0.145), low priority |

No-go families (T1 F-A SHCOMP, T3 F-A real estate, T4 F-B SHCOMP) are not registered.

---

## Summary Scorecard

| Family | Sign correct? | HAC-t | Gates passed | Verdict |
|---|---|---|---|---|
| F-A → SHCOMP | No | −0.089 | 0/5 | **NO-GO** |
| F-A → banks | Yes | 0.554 | 0/5 | **ACCRUE** |
| F-A → real estate | No | −1.441 | 0/5 | **NO-GO** |
| F-B → SHCOMP | No | −0.392 | 0/5 | **NO-GO** |
| F-B → banks | Yes | 1.007 | 1/5 (split-half) | **ACCRUE** |
| F-B → real estate | Yes (barely) | 0.145 | 0/5 | **ACCRUE** |
| F-C communiques | — | — | — | **BLOCKED-DATA** |

> **In plain English, the full summary:** PBoC rate cuts (RRR and LPR) do not reliably move the A-share market over a 4-week horizon. The broad market results are null-to-negative. Banks show the most consistent positive tilt — LPR cuts in particular produce a modest positive spread vs the market that almost survives our stats bar — but we don't have enough events yet to be confident. Real estate, despite being the sector most directly affected by rate cuts, shows no consistent positive response after netting out the market.
>
> The honest answer is: we measured 15–26 events depending on the series. That's a thin dataset for a high-volatility daily return. We need more events. Come back in 2027–2028.

---

## What Is NOT Shown Here

- No "validated" claims. The word "validated" requires the BC-2 allowlist process.
- No wiring: nothing here feeds any engine, board, or score.
- No post-outcome threshold edits. The prereg is law.
- No p-hacking: 6 gated trials were declared, all 6 are reported including nulls.
