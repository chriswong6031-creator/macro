# W2-153 USITC Section 337 Exclusion Risk — Phase-0 Event Study

**Date:** 2026-07-07  
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

**Respondent map:** 108 US-listed patterns (Tier-A), 5 foreign-primary-listed (Tier-B, excluded), 49 private/unlisted (Tier-X, excluded) = 162 total patterns.  
**Distinct US tickers in map:** 89

**Parser provenance (Amendment A4):**
All respondent names are extracted exclusively from the ITC-standard
'(b) The respondent(s) are/is' section of each Federal Register notice.
The preceding '(a) The complainant(s)' block is skipped. Lines containing
'on behalf of' or statute/boilerplate text are dropped before matching.
This prevents complainant names from the SUMMARY preamble clause
('complaint filed on behalf of [COMPLAINANT]') from being tagged as
respondents. No full-text fallback pattern is used.

| Metric | E1 (institution) | E2 (adverse final) |
|--------|-----------------|-------------------|
| Total respondent-section rows parsed | 298 | 11 |
| Respondent-confirmed, mapped US ticker (Tier-A) | 83 | 1 |
| Not matched (foreign/private/unknown) | 215 | 10 |
| Unique US tickers mapped | 28 | 1 |

**Mapping coverage statement:**
Most ITC 337 respondents are foreign manufacturers (Asian OEMs, Korean
conglomerates, European industrials) or private US entities — Tier-X and
Tier-B patterns are excluded from the return study. Only Tier-A (US-listed
with tradable tickers) contribute to the event study. Coverage is biased
toward large-cap technology respondents where ITC cases most frequently
name US-listed companies. Tier-B patterns (5 in map) cover foreign-primary
listings (e.g. Samsung KQ) with no US price data — treated as excluded.

**E1 mapped tickers:** AAPL, AMD, AMZN, AVGO, CAT, CSCO, DELL, ERIC, GOOGL, HON, HPE, HPQ, INTC, MRVL, MSFT, MSI, MU, NOK, NTDOY, NTGR, NVDA, PHG, QCOM, SONY, SWKS, TSLA, TSM, ZBRA  
**E2 mapped tickers:** NVDA  
**Tickers with price data:** AAPL, AMD, AMZN, AVGO, CAT, CSCO, DELL, ERIC, GOOGL, HON, HPE, HPQ, INTC, MRVL, MSFT, MSI, MU, NOK, NTGR, NVDA, PHG, QCOM, SONY, SWKS, TSLA, TSM, ZBRA

---

## 3. Results

### E1 — Institution of Investigation

**Hypothesis:** ITC institution notice → negative beta-adjusted AR over 5d, 21d.
**PIT:** FR publication date + 1 business day.

**E1_institution_5d** (powered (n_dates=49)):
  - Events (respondent-ticker pairs in window): 82
  - Calendar dates (post-collapse): 49
  - Mean beta-adj AR: 0.6496%
  - NW HAC: mean=0.00650, HAC-t=1.195, p=0.2323, n=49

**E1_institution_21d** (powered (n_dates=47)):
  - Events: 78
  - Calendar dates: 47
  - Mean beta-adj AR: 0.0413%
  - NW HAC: mean=0.00041, HAC-t=0.031, p=0.9754, n=47

**Per-ticker breakdown (E1, in study window):**

| Ticker | n events | Mean AR % |
|--------|----------|-----------|
| AAPL | 11 | 1.293 |
| AMD | 1 | 3.423 |
| AMZN | 6 | -5.57 |
| AVGO | 2 | 10.801 |
| CAT | 1 | 21.298 |
| CSCO | 2 | 3.718 |
| DELL | 4 | 0.281 |
| ERIC | 4 | -5.716 |
| GOOGL | 5 | 0.343 |
| HON | 1 | -0.548 |
| HPE | 1 | -12.912 |
| HPQ | 3 | -2.08 |
| INTC | 1 | -5.302 |
| MRVL | 1 | -7.394 |
| MSFT | 1 | -0.407 |
| MSI | 4 | -2.744 |
| MU | 2 | -19.507 |
| NOK | 1 | 13.547 |
| NTGR | 1 | 6.656 |
| NVDA | 1 | 7.64 |
| PHG | 1 | -8.485 |
| QCOM | 5 | -1.611 |
| SONY | 7 | 1.528 |
| SWKS | 1 | 4.253 |
| TSLA | 9 | -2.26 |
| TSM | 1 | 2.315 |
| ZBRA | 1 | 8.152 |

**Honest prior on E1:** Institution notices are forward-looking; the market
may price patent litigation risk gradually as complaints are filed (before
the FR notice). Some respondents are named in cases where they are confident
of success. The 5d window captures the immediate market reaction; 21d captures
the medium-term settlement/order-risk repricing.

### E2 — Adverse Final Determination

**Hypothesis:** Commission finding of 337 violation → negative beta-adj AR
over 5d, 21d. Final determinations are typically telegraphed by the ALJ's
initial determination weeks earlier, so much of the news may be priced in.

**E2_adverse_5d** (UNDERPOWERED (n_dates=1, need≥25)):
  - Events: 1
  - Calendar dates: 1
  - Mean beta-adj AR: -2.7812%
  - NW HAC: n/a (insufficient observations)

**E2_adverse_21d** (UNDERPOWERED (n_dates=1, need≥25)):
  - Events: 1
  - Calendar dates: 1
  - Mean beta-adj AR: -76.9102%
  - NW HAC: n/a (insufficient observations)

**Per-ticker breakdown (E2, in study window):**

| Ticker | n events | Mean AR % |
|--------|----------|-----------|
| NVDA | 1 | -76.91 |

---

## 4. Gate Verdicts

### G1 — |HAC-t| ≥ 2, BH-FDR q ≤ 0.10, negative direction

**BH correction (across powered cells only):**

| Cell | n_dates | mean_AR% | HAC-t | p | q (BH) | H0 rejected |
|------|---------|---------|-------|---|--------|-------------|
| E1_institution_5d | 49 | 0.6496 | 1.195 | 0.2323 | 0.4646 | NO |
| E1_institution_21d | 47 | 0.0413 | 0.031 | 0.9754 | 0.9754 | NO |
| E2_adverse_5d (UNDERPOWERED) | 1 | -2.7812 | n/a | n/a | n/a | n/a |
| E2_adverse_21d (UNDERPOWERED) | 1 | -76.9102 | n/a | n/a | n/a | n/a |

**G1 result: FAIL**
  - Passing cells: none
  - E1_institution_5d: FAIL (mean_ar=0.6496%, t=1.195, neg_dir=False, |t|≥2=False, BH_reject=False)
  - E1_institution_21d: FAIL (mean_ar=0.0413%, t=0.031, neg_dir=False, |t|≥2=False, BH_reject=False)
  - E2_adverse_5d: UNDERPOWERED (n_dates=1)
  - E2_adverse_21d: UNDERPOWERED (n_dates=1)

### G2 — Sector Diversity (≥2 GICS-2 sectors among contributing tickers)

**G2 result: PASS**  
  - Sectors represented: ['20', '25', '45', '50']  
  - Number of distinct GICS-2 sectors: 4  
  - Tickers with sector code: ['AAPL', 'AMD', 'AMZN', 'AVGO', 'CAT', 'CSCO', 'DELL', 'ERIC', 'GOOGL', 'HON', 'HPE', 'HPQ', 'INTC', 'MRVL', 'MSFT', 'MSI', 'MU', 'NOK', 'NTGR', 'NVDA', 'PHG', 'QCOM', 'SONY', 'SWKS', 'TSLA', 'TSM', 'ZBRA']  
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