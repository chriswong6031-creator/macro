# W2-153 USITC Section 337 Exclusion Risk — Phase-0 Event Study

**Date:** 2026-07-06  
**Family:** `w2153_itc337`  
**VERDICT: NULL — no pre-registered gate passed**

> **In plain English:** Section 337 of the Tariff Act allows the ITC to issue
> exclusion orders (import bans) against foreign companies infringing US patents.
> This study asks: when the ITC names a US-listed company's products or a
> US-listed respondent in a 337 investigation, do that company's shares
> systematically underperform the market over the following 5 and 21 trading days?
> Two event types are tested: (1) the formal institution of an investigation,
> and (2) an adverse final determination finding a violation. Both are predicted
> to drive negative beta-adjusted abnormal returns. If a gate is marked
> UNDERPOWERED (fewer than 25 calendar-date observations), the result is
> descriptive only — no promotion claim is made.

---

## 1. Pre-Registered Design

**Family:** `w2153_itc337` (4 gated cells, logged before results)  
**Direction:** NEGATIVE (exclusion-order risk → stock underperformance)  

| Cell | Event | Forward window | PIT fence | Power gate |
|------|-------|---------------|-----------|------------|
| E1_institution_5d  | Institution notice (FR pub) | 5 td  | pub+1 BD | n≥25 calendar dates |
| E1_institution_21d | Institution notice (FR pub) | 21 td | pub+1 BD | n≥25 calendar dates |
| E2_adverse_5d      | Adverse final determination | 5 td  | same day | n≥25 calendar dates |
| E2_adverse_21d     | Adverse final determination | 21 td | same day | n≥25 calendar dates |

**Gate G1:** ≥1 cell negative, |HAC-t| ≥ 2, BH-FDR q ≤ 0.10 across 4 cells;
  underpowered cells (n < 25) excluded from G1.  
**Gate G2:** contributing tickers span ≥ 2 distinct GICS-2 sectors (not-one-sector).

**Amendment A1 (pre-registered before first run):** UNDERPOWERED flag
  (n_dates < 25) — descriptive only, no gate claims.  
**Amendment A2 (pre-registered before first run):** Sector lookup uses
  TICKER_SECTOR manual map; missing-sector tickers included in return stats
  but excluded from sector count.

---

## 2. Data Coverage

**Price store:** massive_stock_day (2021-07-06 → 2026-07-02); 
  stocks/ for tickers with deeper history.  
**Event source:** Federal Register API — ITC institution notices and adverse
  determination notices with '337-TA' in title/docket.  
**PIT fence:** E1 = FR publication date + 1 BD; E2 = FR publication date.  

**Respondent map:** 108 US-listed patterns (Tier-A), 49 private/foreign-listed (Tier-X, excluded).  
**Distinct US tickers in map:** 89

**Mapping coverage statement:**
Many ITC 337 respondents are foreign companies (Asian OEM manufacturers,
Korean conglomerates, European industrials) or private US entities — these
are marked Tier-X and excluded from the return study. Only US-listed
companies with tradable tickers contribute to the event study. Coverage is
biased toward large-cap technology respondents (Apple, Qualcomm, etc.) where
ITC cases are most frequently filed against US-listed companies.

| Metric | E1 (institution) | E2 (adverse final) |
|--------|-----------------|-------------------|
| Total respondent-notice rows | 320 | 351 |
| Rows with mapped US ticker | 99 | 94 |
| Unique US tickers mapped | 36 | 42 |

**E1 mapped tickers:** AAPL, AMD, AMZN, AVGO, CAJ, CAT, CSCO, DD, DELL, ERIC, GLW, GM, GOOGL, HON, HPE, HPQ, IDCC, INTC, LLY, MDT, MRVL, MSFT, MSI, MU, NLST, NOK, NTDOY, NTGR, NVDA, QCOM, SONY, SWKS, SYK, TSLA, TSM, ZBRA  
**E2 mapped tickers:** AAPL, ABT, AMD, AMZN, AVGO, CAJ, CSCO, DD, DE, DELL, DOW, EMR, ERIC, F, GM, GOOGL, HMC, HON, HPQ, IBM, IDCC, INTC, MMM, MSFT, MSI, MU, NFLX, NLST, NOK, NTDOY, NVDA, NVO, PFE, PHG, QCOM, SNY, SONY, TM, TSM, TXN, WOLF, ZBH  
**Tickers with price data:** AAPL, ABT, AMD, AMZN, AVGO, CAJ, CAT, CSCO, DD, DE, DELL, DOW, EMR, ERIC, F, GLW, GM, GOOGL, HMC, HON, HPE, HPQ, IBM, IDCC, INTC, LLY, MDT, MMM, MRVL, MSFT, MSI, MU, NFLX, NOK, NTGR, NVDA, NVO, PFE, PHG, QCOM, SNY, SONY, SWKS, SYK, TM, TSLA, TSM, TXN, WOLF, ZBH, ZBRA

---

## 3. Results

### E1 — Institution of Investigation

**Hypothesis:** ITC institution notice → negative beta-adjusted AR over 5d, 21d.
**PIT:** FR publication date + 1 business day.

**E1_institution_5d** (powered (n_dates=57)):
  - Events (respondent-ticker pairs in window): 96
  - Calendar dates (post-collapse): 57
  - Mean beta-adj AR: 0.7762%
  - NW HAC: mean=0.00776, HAC-t=1.898, p=0.0577, n=57

**E1_institution_21d** (powered (n_dates=56)):
  - Events: 93
  - Calendar dates: 56
  - Mean beta-adj AR: -0.0243%
  - NW HAC: mean=-0.00024, HAC-t=-0.018, p=0.9859, n=56

**Per-ticker breakdown (E1, in study window):**

| Ticker | n events | Mean AR % |
|--------|----------|-----------|
| AAPL | 13 | 1.413 |
| AMD | 1 | 3.423 |
| AMZN | 1 | -3.611 |
| AVGO | 2 | 10.801 |
| CAJ | 4 | 4.068 |
| CAT | 1 | 21.298 |
| CSCO | 2 | 3.718 |
| DD | 1 | -8.017 |
| DELL | 4 | 0.281 |
| ERIC | 5 | -1.105 |
| GLW | 2 | 0.305 |
| GM | 1 | 5.505 |
| GOOGL | 6 | 1.432 |
| HON | 3 | 2.576 |
| HPE | 1 | -12.912 |
| HPQ | 3 | -2.08 |
| IDCC | 3 | -2.534 |
| INTC | 2 | -6.477 |
| LLY | 1 | -3.975 |
| MDT | 1 | -2.476 |
| MRVL | 1 | -7.394 |
| MSFT | 1 | -0.407 |
| MSI | 4 | 0.473 |
| MU | 2 | -19.507 |
| NOK | 5 | 8.147 |
| NTGR | 1 | 6.656 |
| NVDA | 2 | -34.635 |
| QCOM | 4 | -1.729 |
| SONY | 4 | -0.582 |
| SWKS | 2 | -3.996 |
| SYK | 1 | -0.681 |
| TSLA | 5 | 0.594 |
| TSM | 1 | 2.315 |
| ZBRA | 3 | -1.088 |

**Honest prior on E1:** Institution notices are forward-looking; the market
may price patent litigation risk gradually as complaints are filed (before
the FR notice). Some respondents are named in cases where they are confident
of success. The 5d window captures the immediate market reaction; 21d captures
the medium-term settlement/order-risk repricing.

### E2 — Adverse Final Determination

**Hypothesis:** Commission finding of 337 violation → negative beta-adj AR
over 5d, 21d. Final determinations are typically telegraphed by the ALJ's
initial determination weeks earlier, so much of the news may be priced in.

**E2_adverse_5d** (powered (n_dates=61)):
  - Events: 92
  - Calendar dates: 61
  - Mean beta-adj AR: 0.4668%
  - NW HAC: mean=0.00467, HAC-t=1.122, p=0.2618, n=61

**E2_adverse_21d** (powered (n_dates=61)):
  - Events: 92
  - Calendar dates: 61
  - Mean beta-adj AR: -2.6178%
  - NW HAC: mean=-0.02618, HAC-t=-1.282, p=0.1998, n=61

**Per-ticker breakdown (E2, in study window):**

| Ticker | n events | Mean AR % |
|--------|----------|-----------|
| AAPL | 11 | 0.723 |
| ABT | 1 | 0.917 |
| AMD | 2 | 14.159 |
| AMZN | 2 | -44.917 |
| AVGO | 4 | 1.67 |
| CAJ | 3 | 5.671 |
| CSCO | 2 | 3.718 |
| DD | 2 | -4.787 |
| DE | 2 | 6.904 |
| DELL | 2 | 1.1 |
| DOW | 1 | -2.915 |
| EMR | 2 | 2.94 |
| ERIC | 1 | -12.139 |
| F | 1 | -9.535 |
| GM | 1 | -4.674 |
| GOOGL | 4 | -23.415 |
| HMC | 1 | 2.132 |
| HON | 3 | 3.441 |
| HPQ | 2 | -5.075 |
| IBM | 1 | 1.47 |
| IDCC | 3 | -2.494 |
| INTC | 3 | -0.622 |
| MMM | 1 | -1.072 |
| MSFT | 4 | 1.79 |
| MSI | 4 | -0.586 |
| MU | 1 | -0.287 |
| NFLX | 1 | -5.882 |
| NOK | 6 | 13.547 |
| NVDA | 2 | -76.91 |
| NVO | 1 | 14.076 |
| PFE | 1 | 13.619 |
| PHG | 5 | -7.887 |
| QCOM | 3 | 3.582 |
| SNY | 1 | -4.206 |
| SONY | 3 | -0.23 |
| TM | 1 | 2.747 |
| TSM | 1 | -2.489 |
| TXN | 1 | -0.78 |
| WOLF | 1 | 2.893 |
| ZBH | 1 | -10.336 |

---

## 4. Gate Verdicts

### G1 — |HAC-t| ≥ 2, BH-FDR q ≤ 0.10, negative direction

**BH correction (across powered cells only):**

| Cell | n_dates | mean_AR% | HAC-t | p | q (BH) | H0 rejected |
|------|---------|---------|-------|---|--------|-------------|
| E1_institution_5d | 57 | 0.7762 | 1.898 | 0.0577 | 0.2308 | NO |
| E1_institution_21d | 56 | -0.0243 | -0.018 | 0.9859 | 0.9859 | NO |
| E2_adverse_5d | 61 | 0.4668 | 1.122 | 0.2618 | 0.3491 | NO |
| E2_adverse_21d | 61 | -2.6178 | -1.282 | 0.1998 | 0.3491 | NO |

**G1 result: FAIL**
  - Passing cells: none
  - E1_institution_5d: FAIL (mean_ar=0.7762%, t=1.898, neg_dir=False, |t|≥2=False, BH_reject=False)
  - E1_institution_21d: FAIL (mean_ar=-0.0243%, t=-0.018, neg_dir=True, |t|≥2=False, BH_reject=False)
  - E2_adverse_5d: FAIL (mean_ar=0.4668%, t=1.122, neg_dir=False, |t|≥2=False, BH_reject=False)
  - E2_adverse_21d: FAIL (mean_ar=-2.6178%, t=-1.282, neg_dir=True, |t|≥2=False, BH_reject=False)

### G2 — Sector Diversity (≥2 GICS-2 sectors among contributing tickers)

**G2 result: PASS**  
  - Sectors represented: ['15', '20', '25', '35', '45', '50']  
  - Number of distinct GICS-2 sectors: 6  
  - Tickers with sector code: ['AAPL', 'AMD', 'AMZN', 'AVGO', 'CAJ', 'CAT', 'CSCO', 'DD', 'DELL', 'ERIC', 'GLW', 'GM', 'GOOGL', 'HON', 'HPE', 'HPQ', 'IDCC', 'INTC', 'LLY', 'MDT', 'MRVL', 'MSFT', 'MSI', 'MU', 'NOK', 'NTGR', 'NVDA', 'QCOM', 'SONY', 'SWKS', 'SYK', 'TSLA', 'TSM', 'ZBRA', 'ABT', 'DE', 'DOW', 'EMR', 'F', 'HMC', 'IBM', 'MMM', 'NFLX', 'NVO', 'PFE', 'PHG', 'SNY', 'TM', 'TXN', 'WOLF', 'ZBH']  
  - Tickers missing sector code (excluded from count): []

### FINAL VERDICT: **NULL — no pre-registered gate passed**

---

## 5. PIT Assumptions and Caveats

- **No look-ahead.** All thresholds and beta estimates use only data
  available strictly before the event availability date.
- **Price store covers 2021-07 → 2026-07.** ITC investigations go back to
  the 1970s; events before 2021-07 are parsed but excluded from return study.
  Any cell with n < 25 after the price window filter is flagged UNDERPOWERED.
- **Respondent mapping is partial.** Most ITC 337 respondents are foreign
  manufacturers or private US entities. The fraction of investigations with at
  least one mappable US-listed respondent is estimated at 15–30% (varies by
  technology sector). Mapping coverage is printed at runtime.
- **Calendar-time collapse.** Same-day events are averaged to prevent
  pseudo-replication from large complaints naming 10–30 respondents.
- **Beta adjustment.** Trailing 252-day OLS beta vs SPY, PIT. Default = 1.0
  if fewer than 60 trading days of overlap.
- **Text parsing.** Respondent names are extracted by regex from raw FR
  notice text. The parser may miss names with unusual formatting or
  over-match on tangentially mentioned companies. Coverage counts are
  conservative lower bounds.
- **Investigation heterogeneity.** Not all 337 cases carry equal exclusion
  risk. A complaint by a non-practicing entity (NPE/patent troll) against
  Apple differs from a Qualcomm-Ericsson standards-essential patent dispute.
  This study treats all institutions equally — a severity-stratified
  follow-up would be the natural extension.

---

## 6. Nightly Wiring (for consolidation)

This is a phase-0 standalone harness. No collector or nightly job is proposed
unless the gates pass and this study advances to phase-1.

If promoted, the wiring would be:
  1. Weekly incremental fetch of new FR notices (institution + adverse).
  2. Parse respondent names → map to tickers → append to events_e1/e2.
  3. Nightly: compute beta-adjusted AR for events that have aged into their
     forward window; update signal panel.
  4. Signal consumed as a confirmer (display-only context overlay),
     never as a direct scoring input.

---

## 7. Conclusion

No pre-registered gate passed. The ITC Section 337 institution and adverse
determination events do not show statistically reliable negative beta-adjusted
abnormal returns in the tested forward windows.

Possible explanations:
- **Already priced.** Patent litigation risk may be partially priced at
  complaint filing (before FR institution notice), especially for tech majors.
- **Sample composition.** The mapped US-listed respondents are predominantly
  large-cap companies with strong balance sheets for whom a single ITC case
  is a routine legal cost, not an existential threat.
- **Heterogeneous cases.** Mixing NPE trolls, standards-essential disputes,
  and genuine competitive IP battles dilutes any systematic effect.

---

*Generated by scripts/w2153_itc337_phase0.py — lane A6, wave-2.*