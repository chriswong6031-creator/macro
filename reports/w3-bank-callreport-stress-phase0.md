# W3 Bank Call-Report Stress — Phase-0 Validation

**Family:** `w3_bank_callreport_stress` | **Verdict:** ACCRUE

## In plain English

We collected quarterly bank balance-sheet data from the FDIC BankFind API
for all 20 regional-bank basket tickers (RF, KEY, CFG, HBAN, FITB, MTB,
TFC, USB, PNC, WAL, EWBC, CFR, FHN, WTFC, WBS, SSB, UMBF, BPOP, COLB, FCNCA),
covering 33 quarters from 20180331 to 20260331.
We tested whether banks showing balance-sheet stress
— rising CRE delinquencies, worsening deposit mix, high uninsured-deposit share —
delivered worse subsequent stock performance (vs the KRE beta benchmark).

The primary finding is counterintuitive: the V1 CRE-stress proxy (rising delinquency
delta + concentration trend) has a small NEGATIVE IC at 63d (IC = -0.032), meaning
stressed banks on this proxy slightly OUTPERFORMED over the following 63 trading days.
This is consistent with a contrarian/mean-reversion dynamic: markets over-punish
banks on rising CRE stress metrics, creating a value-reversal premium. V3 (the level
of canonical post-SVB ratios) also shows a POSITIVE IC (IC = +0.114 at 63d full
sample), suggesting banks with persistently HIGH stress levels have also outperformed
— again consistent with markets over-pricing the tail risk.

Neither result supports the original hypothesis (stress -> underperformance) in the
short-to-medium term horizon tested. The DSR does not clear for any variant (p: V1
0.0142, V2 0.0996, V3 0.8222 — none ≥ 0.90). The V5 AVOID lens (does high V1 predict
larger max drawdown?) shows IC = +0.046, a weak positive — stressed banks do suffer
slightly larger drawdowns, but the effect is small and not separately gated.

Family ACCRUES per pre-registered expectation (n=1 crisis episode in sample).

---

## 1. Data plane

**Source:** FDIC BankFind Suite API (https://banks.data.fdic.gov/api/financials)
**Coverage:** 2018-Q1 to 2026-Q1 (33 quarters × 20 BHCs = 660 observations)
**Crosswalk:** FDIC RSSDHCR (parent HC RSSD) → ticker, verified 2026-07-07
  via FDIC institutions endpoint. See `data/ffiec_y9c/bhc_ticker_map.csv`.
**PIT enforcement:** signal_date = report_date + 45 calendar days
  (FDIC bulk release lag; verified against published FDIC schedule).

### Pre-registered gaps

- **GAP-1** (FDIC vs FR Y-9C): FDIC carries bank-subsidiary-level data
  (individual charter), not BHC-level. We aggregate by RSSDHCR to BHC.
  For large BHCs with one primary subsidiary this is near-exact; for
  multi-charter BHCs (e.g., WTFC has 3 chartered subsidiaries in 2018)
  the aggregation may miss thin subsidiaries. COVERAGE VERIFIED: all
  20 tickers have 33/33 quarters.

- **GAP-2** (CRE maturity schedule): CRE maturity-bucket breakdown is
  in FR Y-9C Schedule HC-C Part II, which is NOT available from FDIC call
  reports. V1 uses a proxy: rising nonfarm-nonresidential CRE noncurrent
  rate delta + CRE concentration trend. The true maturity-roll signal
  would require a full FR Y-9C bulk download; scripted for future re-run.

- **GAP-3** (AOCI/HTM): FDIC publishes total securities (SC) but not the
  AFS/HTM split or unrealized P&L. AOCI excluded from V3 composite.

- **GAP-4** (FHLB advances): Not available as a standalone field in FDIC
  financials. Excluded from V3.

### Asset size distribution (max quarter, $K)

| stat | value |
|------|-------|
| min | $53,127,804K |
| 25% | $74,927,461K |
| 50% | $131,002,221K |
| 75% | $247,674,594K |
| max | $692,852,440K |

All 20 tickers pass the ≥$2B assets threshold (smallest: CFR at $53,127,804K).

---

## 2. Signal design

| Variant | Description | Gate | Pre-registered expectation |
|---------|-------------|------|---------------------------|
| V1 | CRE stress proxy: NCRENRER delta + CRE/equity delta + CRE/loans delta | GATED | Primary; must beat V3 ex-2023 |
| V2 | Deposit-mix deterioration streak (uninsured + brokered) | GATED | Secondary |
| V3 | Canonical-ratio level composite (control, spanned) | GATED | Expected weaker ex-2023 |
| V4 | V1 at 21d horizon (robustness check) | NON-GATED | — |
| V5 | V1 → max-drawdown AVOID lens | NON-GATED | — |

**TrialLedger:** 6 distinct configs registered for family `w3_bank_callreport_stress`
(3 variants × 2 horizons = 6 configs; BH-FDR correction on 3 gated × 1 primary horizon).

---

## 3. Results — IC by variant and horizon

### 3.1 Full sample (2018-Q1 to 2026-Q1, 33 quarters)

| Variant | Horizon | N dates | Mean IC | Std IC | ICIR | %Pos | t-stat | p-val | 95% CI | CI excl. 0? |
|---------|---------|---------|---------|--------|------|------|--------|-------|--------|-------------|
| V1 | 21d | 31 | -0.0030 | 0.2668 | -0.062 | 0.516 | -0.062 | 0.9508 | [-0.0928, 0.0982] | no |
| V1 | 63d | 30 | -0.0315 | 0.1892 | -0.913 | 0.333 | -0.913 | 0.3615 | [-0.1027, 0.0430] | no |
| V2 | 21d | 31 | 0.0667 | 0.2326 | 1.596 | 0.645 | 1.596 | 0.1105 | [-0.0061, 0.1444] | no |
| V2 | 63d | 30 | 0.0007 | 0.2264 | 0.017 | 0.400 | 0.017 | 0.9868 | [-0.1003, 0.0944] | no |
| V3 | 21d | 31 | 0.0227 | 0.2223 | 0.567 | 0.645 | 0.567 | 0.5704 | [-0.0619, 0.1016] | no |
| V3 | 63d | 30 | 0.1136 | 0.2596 | 2.396 | 0.633 | 2.396 | 0.0166 | [0.0175, 0.2116] | YES |

### 3.2 Ex-2023 decomposition (mandatory crisis-concentration gate)

Crisis window dropped: signal dates 2022-11-14 to 2023-11-14 (PIT-shifted).

| Variant | Horizon | N dates | Mean IC | ICIR | %Pos | t-stat | p-val | CI excl. 0? |
|---------|---------|---------|---------|------|------|--------|-------|-------------|
| V1 | 21d | 26 | -0.0105 | -0.198 | 0.500 | -0.198 | 0.8432 | no |
| V1 | 63d | 25 | -0.0419 | -1.046 | 0.280 | -1.046 | 0.2957 | no |
| V2 | 21d | 26 | 0.0947 | 2.016 | 0.692 | 2.016 | 0.0438 | YES |
| V2 | 63d | 25 | 0.0369 | 0.810 | 0.480 | 0.810 | 0.4180 | no |
| V3 | 21d | 26 | 0.0361 | 0.800 | 0.692 | 0.800 | 0.4239 | no |
| V3 | 63d | 25 | 0.1445 | 2.755 | 0.680 | 2.755 | 0.0059 | YES |

### 3.3 Crisis-only (2023 window)

| Variant | Horizon | N dates | Mean IC | ICIR | %Pos | t-stat | p-val |
|---------|---------|---------|---------|------|------|--------|-------|
| V1 | 21d | 5 | 0.0364 | 0.305 | 0.600 | 0.305 | 0.7607 |
| V1 | 63d | 5 | 0.0205 | 0.381 | 0.600 | 0.381 | 0.7031 |
| V2 | 21d | 5 | -0.0791 | -1.415 | 0.400 | -1.415 | 0.1571 |
| V2 | 63d | 5 | -0.1802 | -3.711 | 0.000 | -3.711 | 0.0002 |
| V3 | 21d | 5 | -0.0475 | -0.601 | 0.400 | -0.601 | 0.5478 |
| V3 | 63d | 5 | -0.0412 | -0.460 | 0.400 | -0.460 | 0.6453 |

---

## 4. Gate verdicts

### 4.1 Deflated Sharpe (DSR) — gated variants at 63d, n_trials=6

Threshold: DSR p ≥ 0.90 (per family constitution; 'the only door to GO').

| Variant | DSR p | BH-adjusted p | DSR verdict |
|---------|-------|---------------|-------------|
| V1 | 0.0142 | 0.0426 | FAIL |
| V2 | 0.0996 | 0.1494 | FAIL |
| V3 | 0.8222 | 0.8222 | FAIL |

### 4.2 Spannedness gate: V1 vs V3 ex-2023

Criterion: |IC(V1 ex-2023)| > |IC(V3 ex-2023)| at 63d horizon.

| Metric | V1 (primary) | V3 (control) | V1 > V3? |
|--------|--------------|--------------|----------|
| |mean IC| ex-2023 (63d) | 0.0419 | 0.1445 | FAIL |

**Interpretation:** V3 >= V1 ex-2023 — the canonical-level ratios contain at least as much signal as the proxy. Family may be fully spanned.

### 4.3 V4 — 21d ruler robustness (non-gated)

| Metric | V1@21d ex-2023 | V3@21d ex-2023 |
|--------|----------------|----------------|
| Mean IC | -0.0105 | 0.0361 |
| ICIR | -0.198 | 0.800 |

### 4.4 V5 — AVOID-side drawdown lens (non-gated)

Does high V1 score predict deeper max drawdown in next 63d?
A positive IC here = stressed banks suffer larger drawdowns = AVOID signal.

| Metric | Value |
|--------|-------|
| V5 IC (full, V1 → max_dd_63d) | 0.0458 |
| V5 IC (ex-2023) | 0.0793 |
| N observations | 620 |

---

## 5. Overall verdict: ACCRUE

**Sign finding (important):** V1 and V3 are SIGN-OPPOSITE to the stress-predicts-underperformance
hypothesis. Both show that stressed banks outperform on average in the 63d window
(V1 IC = -0.032, meaning high V1 -> positive residual return; V3 IC = +0.114,
meaning high canonical-stress-level -> positive residual return). This is consistent
with a contrarian/value-reversal interpretation: markets over-penalize banks on balance-
sheet stress metrics, creating a mean-reversion premium for the most-punished names.
The AVOID lens (V5: IC = +0.046) confirms stressed banks do suffer slightly larger
drawdowns, but the effect is too small to gate on.

**DSR gate:** V1 p=0.014, V2 p=0.100, V3 p=0.822 — none ≥ 0.90 threshold.
Spannedness gate: V3 > V1 ex-2023 (FAIL — canonical ratios dominate the proxy).

Pre-registered expectation: this IS the expected outcome for n=1 crisis.
Family accrues; adjudication revisit when a second independent bank-stress episode appears in the sample.

Pre-registered expectation (from SIGNAL_LAB_FRONTIER_WAVE3_FABLE_ADJUDICATION_2026-07-06.md §1):
> 'Mandatory ex-2023 decomposition; the pre-registered expectation is that the
> first adjudication lands ACCRUE-with-clock awaiting a second independent episode,
> not GO. A spectacular in-sample Sharpe here is the archetypal single-event dummy.'

The DSR gate result (p = 0.0142) is consistent with the pre-registered expectation.

**Come-back clock:** next adjudication when a second independent bank-stress
episode enters the sample. Current sample (2018-Q1 to 2026-Q1) contains
exactly one: Mar-2023 SVB/Signature/First Republic. The 2022 rising-rate
period is a stress regime but produced no major failures in this basket.

---

## 6. Nightly wiring (for consolidation)

The FDIC collector (`scripts/collect_ffiec_y9c.py`) is standalone and resumable.
Add to `daily.yml` as a pre-analysis step:

```yaml
- name: Collect FDIC Y-9C proxy
  run: python3 -m scripts.collect_ffiec_y9c --resume
```

No `scripts/collect.py` or `engine/signal_lab.py` edits required.

---

*Report generated by `scripts/w3_bank_callreport_stress_phase0.py`*
