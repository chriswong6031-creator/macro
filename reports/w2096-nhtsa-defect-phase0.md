# W2-096 NHTSA Defect Escalation — Phase-0 Event Study

**Date:** 2026-07-06  
**Family:** `w2096_nhtsa_defect`  
**VERDICT: NULL — no pre-registered gate passed**

> **In plain English:** This study asks whether public NHTSA safety events —
> opening a defect investigation, a spike in consumer complaints, or a large
> recall — predict negative returns for the automaker's stock over the following
> 1-3 months, after stripping out market and sector moves. The results below
> show whether any of those three signals cleared our pre-set statistical bar.

---

## 1. Pre-Registered Design

**Family:** `w2096_nhtsa_defect` (6 gated cells, logged before results)  
**Direction:** all hypotheses predict NEGATIVE peer-adjusted abnormal returns.

| Cell | Signal | Forward window | Gate |
|------|--------|---------------|------|
| V1_inv_5d  | Investigation open (PE/EA) | 5 trading days  | G1 |
| V1_inv_21d | Investigation open (PE/EA) | 21 trading days | G1 |
| V2_cmpl_21d | Complaint acceleration (top-decile of trailing 24m) | 21 td | G1 |
| V2_cmpl_63d | Complaint acceleration | 63 trading days | G1 |
| V3_rcl_21d  | Major recall (>trailing-3y p90 for make) | 21 td | G1 |
| V3_rcl_21d_notsla | Major recall, TSLA excluded | 21 td | G3 robustness |

**Gate G1:** ≥1 cell negative direction, |t| ≥ 2 (NW HAC), BH-FDR q ≤ 0.10  
**Gate G2:** split-half same-sign for any G1 cell  
**Gate G3:** effect must persist after TSLA exclusion  

---

## 2. Data Coverage

**Price panel:** 2021-07-06 to 2026-07-02 (~5 years). ODI history spans 1990s+;
events before 2021-07-06 are parsed into the event table but excluded from
return study (price store limitation). Future re-runs with a deeper price panel
will extend coverage automatically.

**PIT availability fences:**
- V1 (investigations): event_date + 7 calendar days  
- V2 (complaints): signal available first day of month after the complaint month;
  z-score uses trailing 24 months of own history; no scoring before 25 months available  
- V3 (recalls): p90 threshold uses trailing 3-year per-make history;
  no scoring before 37 months of history available  

**Mapping coverage:**
- F: Tier-A, V1=545 investigations, V2=71 complaint-acceleration months, V3=0 major recalls
- GM: Tier-A, V1=500 investigations, V2=45 complaint-acceleration months, V3=0 major recalls
- HMC: Tier-B, V1=91 investigations, V2=185 complaint-acceleration months, V3=0 major recalls
- HOG: Tier-A, V1=14 investigations, V2=81 complaint-acceleration months, V3=0 major recalls
- LCID: Tier-A, V1=0 investigations, V2=3 complaint-acceleration months, V3=0 major recalls
- PCAR: Tier-A, V1=17 investigations, V2=42 complaint-acceleration months, V3=0 major recalls
- RIVN: Tier-A, V1=2 investigations, V2=7 complaint-acceleration months, V3=0 major recalls
- STLA: Tier-B, V1=338 investigations, V2=80 complaint-acceleration months, V3=0 major recalls
- TM: Tier-B, V1=77 investigations, V2=120 complaint-acceleration months, V3=0 major recalls
- TSLA: Tier-A, V1=18 investigations, V2=55 complaint-acceleration months, V3=0 major recalls

**Event counts by variant:**

| Variant | Total events | Events in price window | Calendar dates |
|---------|-------------|------------------------|----------------|
| V1_inv_5d | 1602 | 76 | 64 |
| V1_inv_21d | 1602 | 75 | 63 |
| V2_cmpl_21d | 689 | 113 | 54 |
| V2_cmpl_63d | 689 | 108 | 52 |
| V3_rcl_21d | 0 | 0 | 0 |
| V3_rcl_21d_notsla | 0 | 0 | 0 |

**Per-ticker event breakdown (Tier-A, in price window):**

| Ticker | V1 events | V2 events | V3 events |
|--------|-----------|-----------|-----------|
| F | 17 | 21 | 0 |
| GM | 8 | 3 | 0 |
| HOG | 0 | 0 | 0 |
| LCID | 0 | 3 | 0 |
| PCAR | 1 | 7 | 0 |
| RIVN | 1 | 6 | 0 |
| TSLA | 13 | 24 | 0 |

---

## 3. Results

### V1 — Defect Investigation Opening

**Hypothesis:** PE/EA investigation open → negative peer-adjusted AR over 5d, 21d.

**V1_inv_5d:** 76 events, 64 calendar dates
  - Mean peer-adj AR: -1.2166%
  - NW HAC: mean=-0.0122, t=-0.78, p=0.4374, n=64

**V1_inv_21d:** 75 events, 63 calendar dates
  - Mean peer-adj AR: -3.252%
  - NW HAC: mean=-0.0325, t=-0.77, p=0.4439, n=63

**Honest prior:** investigations are typically launched after safety data is
already public; the market may have partially priced the event before the PE opens.

### V2 — Complaint Acceleration (W2-156 fold-in)

**Hypothesis:** Top-decile complaint month (vs trailing 24m own history) →
negative peer-adjusted AR over 21d, 63d.

**V2_cmpl_21d:** 113 events, 54 calendar dates
  - Mean peer-adj AR: -0.3989%
  - NW HAC: mean=-0.0040, t=-0.26, p=0.7920, n=54

**V2_cmpl_63d:** 108 events, 52 calendar dates
  - Mean peer-adj AR: -1.3005%
  - NW HAC: mean=-0.0130, t=-0.45, p=0.6515, n=52

**Note:** W2-156 adjudication struck the 'per-active-fleet' denominator.
Own-history z-score (no fleet normalization) is the pre-registered ruler.

### V3 — Major Recall

**Hypothesis:** Recall with potentially-affected units > trailing-3y p90 →
negative peer-adjusted AR over 21d.

**V3_rcl_21d:** 0 events, 0 calendar dates
  - Mean peer-adj AR: None%
  - NW HAC: n/a (too few observations)

**Honest prior:** recalls are often negotiated weeks before announcement;
same-day pricing of material recalls is common for large events.

**V3_rcl_21d (TSLA excluded — G3 check):**
  - Events: 0, dates: 0
  - Mean peer-adj AR: None%
  - NW HAC: n/a (too few observations)

### Tier-B ADR Robustness (non-gated)

Tier-B (TM, HMC, STLA) V1 21d: 35 events, mean PAR: -3.4235%
NW HAC: mean=-0.0342, t=-0.72, p=0.4737, n=29

---

## 4. Gate Verdicts

### Benjamini-Hochberg FDR (q ≤ 0.10 across 6 gated cells):

| Cell | p | q | Reject H0 |
|------|---|---|-----------|
| V1_inv_21d | 0.4439 | 0.7920 | NO |
| V1_inv_5d | 0.4374 | 0.7920 | NO |
| V2_cmpl_21d | 0.7920 | 0.7920 | NO |
| V2_cmpl_63d | 0.6515 | 0.7920 | NO |

**G1 (≥1 cell negative, |t|≥2, BH q≤0.10):** FAIL
  - Passing cells: []
**G2 (split-half same-sign):** NOT REACHED (G1 failed)
**G3 (TSLA-exclusion robustness):** NOT REACHED (G1 failed)

### FINAL VERDICT: **NULL — no pre-registered gate passed**

---

## 5. PIT Assumptions & Caveats

- **No look-ahead in any threshold.** Every quantile/z-score uses only data
  available strictly before the event date being scored.
- **Price store is 5-year rolling window.** ODI complaints go back to 1996;
  the complaint-z and recall-p90 thresholds use the full complaint history,
  but return study is limited to the 2021-07..2026-07 price window.
- **Mapping may miss make-string variants.** Unusual OEM name strings in ODI
  that don't match the make map are silently excluded. Coverage counts above
  reflect mapped events only.
- **Peer adjustment:** abnormal return = stock return − beta × SPY, then minus
  equal-weighted mean AR of other Tier-A OEMs. Beta is trailing-252d PIT.
  On dates where fewer than 3 peers have returns, peer adjustment may be noisy.
- **Calendar-time collapse:** multiple same-date events are averaged to one
  observation before Newey-West. This prevents pseudo-replication from dates
  with many OEMs simultaneously triggering the signal.
- **TSLA dominance risk:** TSLA generates a disproportionate share of NHTSA
  complaints and investigations; G3 gates out results that vanish without TSLA.

---

## 6. Conclusion

No pre-registered gate passed. The three NHTSA defect-escalation signals
(investigation opening, complaint acceleration, major recall) do not show
statistically reliable negative peer-adjusted returns over the tested windows
in this price panel. This is a null result; no collector is proposed.

Possible explanations:
- **Already priced:** the market prices NHTSA events in real time (news); formal
  ODI filing may be lagged or anticipated.
- **Event heterogeneity:** not all PE openings carry equal severity; a
  severity-stratified study might find edge in the tail.
- **Short panel:** ~5 years and few Tier-A tickers limits power, especially
  for rare events (RIVN/LCID have thin histories).

---

*Generated by scripts/w2096_nhtsa_defect_phase0.py — wave-2 spike S2, no collector, no nightly edits.*