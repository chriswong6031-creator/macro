# W3 Bank Call-Report Stress — Phase-0 Validation

**Family:** `w3_bank_callreport_stress` | **Verdict:** ACCRUE

## In plain English

We collected quarterly bank balance-sheet data from the FDIC BankFind API
for 23 regional-bank BHCs: 20 current basket tickers (RF, KEY, CFG, HBAN, FITB, MTB,
TFC, USB, PNC, WAL, EWBC, CFR, FHN, WTFC, WBS, SSB, UMBF, BPOP, COLB, FCNCA)
**plus 3 failed banks retained for survivorship-bias correction**
(SIVB/SVB, SBNY/Signature, FRC/First Republic — the three failures that ARE
the Mar-2023 stress episode). Failed banks are included per the frozen
FRC/SIVB-era rule: terminal -100% return settlement at delisting date.
We tested whether banks showing balance-sheet stress
— rising CRE delinquencies (YoY), worsening deposit mix, high uninsured-deposit share —
delivered worse subsequent stock performance (vs the KRE beta benchmark).

The primary finding: the V1 CRE-stress proxy has a NEGATIVE IC
at 63d (IC = -0.0061), meaning stressed banks slightly OUTPERFORMED (contrarian/value-reversal pattern).

IMPORTANT — design-substitution disclosure: this study uses FDIC call-report
data as an authorized proxy for FR Y-9C (assessed and confirmed as too heavy
for budget — see §1 for full disclosure). V1 is therefore a proxy for the
CRE maturity-roll signal, not the exact maturity-bucket construct. The
spannedness gate result should be interpreted in that context.

Neither result supports the original hypothesis (stress -> underperformance)
in the short-to-medium term horizon tested. The DSR does not clear for any
variant (p: V1 0.0753,
V2 0.3942,
V3 0.7695 — none >= 0.90).

Family ACCRUES per pre-registered expectation (n=1 crisis episode in sample).

---

## 1. Data plane

**Source:** FDIC BankFind Suite API (https://banks.data.fdic.gov/api/financials)
**Coverage:** 2018-Q1 to 2026-Q1 (33 quarters × 20 surviving BHCs + 3 failed BHCs)
**Crosswalk:** FDIC RSSDHCR (parent HC RSSD) -> ticker, verified 2026-07-07
  via FDIC institutions endpoint. See `data/ffiec_y9c/bhc_ticker_map.csv`.

**PIT enforcement:** signal_date = report_date + 60 calendar days
  (widened from 45d to 60d to enforce worst-case FDIC bulk-data release lag).
  Receipt: FDIC bulk 'Statistics on Depository Institutions' release calendar
  (https://www.fdic.gov/analysis/sdi/index.html) shows Q1 2023 data appeared
  2023-05-30 (60 days after 2023-03-31 quarter-end). The 45-day assumption in
  the prior build was insufficiently conservative for large-bank late filers.
  Enforced worst case: 60 days. No look-ahead possible with this lag.

**PIT amendment (2026-07-08):** the prior merged ACCRUE run (#1856/#1860)
  enforced the 60d lag only on failed-bank rows; surviving banks' signal
  dates flowed from the store panel at the collector's legacy
  report_date + 45d, so survivor signals could pre-date FDIC bulk
  availability by up to 15 days (mild look-ahead). Amended: signal_date =
  report_date + 60d is now recomputed for ALL rows at panel load,
  and the collector writes 60d. All IC tables in this report are
  regenerated under the uniform lag. The trial grid is unchanged — the
  correction applies uniformly to all variants (no new configs, no change
  to the multiple-testing count). Prior-run tables (mixed 45/60 lag) are
  superseded; the verdict under both lag treatments is reported in §5.

**Survivorship-bias correction (FRC/SIVB-era rule):**
  Failed banks included in point-in-time panel:
  | Ticker | BHC | Failed | FDIC quarters | Price source |
  |--------|-----|--------|---------------|-------------|
  | SIVB | SVB Financial Group | 2023-03-10 | 20 (2018-Q1 to 2022-Q4) | massive_stock_day (2021+) |
  | SBNY | Signature Bank NY | 2023-03-12 | 20 (2018-Q1 to 2022-Q4) | massive_stock_day (2021+) |
  | FRC | First Republic Bank | 2023-05-01 | 21 (2018-Q1 to 2023-Q1) | massive_stock_day (2021+) |

  Terminal -100% return settlement applied at delisting (per FRC/SIVB-era rule).
  Price data pre-2021-07-06 is unavailable in the local store (massive_stock_day
  coverage starts 2021-07-06); failed banks drop from IC cross-section for
  signal dates before that date — correct PIT behavior.

  Store-backed since 2026-07-08: the three failed banks are backfilled into
  `data/ffiec_y9c/bhc_panel.parquet` by `scripts/collect_ffiec_y9c.py`
  (`FAILED_TICKER_CERT_MAP`). This study reads them from the store and only
  falls back to a live FDIC fetch when the store copy predates the backfill.

**Design-substitution disclosure (FR Y-9C vs FDIC call reports):**
  Frozen spec (§1) specifies FR Y-9C as primary, FDIC as authorized fallback
  'if Y-9C bulk proves too heavy.' Assessment:
  - Chicago Fed Y-9C bulk download: ~8 GB compressed, Schedule HC-C Part II
    (CRE maturity buckets, GAP-2) is NOT in the public bulk download — it
    requires the full NIC/RSSD historical file. Y-9C bulk assessed as too heavy
    AND as failing to provide the maturity-schedule data that differentiates V1.
  - FALLBACK AUTHORIZED: FDIC call-report data used per §1 authorization.
  - CONSEQUENCE: V1 is a PROXY (delinquency delta + concentration trend),
    NOT the exact maturity-roll signal. This is pre-registered as GAP-2.
    Spannedness gate failure may partly reflect missing maturity data.
    This study is disclosed as a proxy-only partial study.

### Pre-registered gaps

- **GAP-1** (FDIC vs FR Y-9C): FDIC carries bank-subsidiary-level data
  (individual charter), not BHC-level. We aggregate by RSSDHCR to BHC.
  For large BHCs with one primary subsidiary this is near-exact; for
  multi-charter BHCs (e.g., WTFC has 3 chartered subsidiaries in 2018)
  the aggregation may miss thin subsidiaries. COVERAGE VERIFIED: all
  20 surviving tickers have 33/33 quarters.

- **GAP-2** (CRE maturity schedule): CRE maturity-bucket breakdown is
  in FR Y-9C Schedule HC-C Part II, which is NOT available from FDIC call
  reports NOR from the Chicago Fed Y-9C bulk download (confirmed). V1 uses
  a proxy: rising nonfarm-nonresidential CRE noncurrent rate YoY delta +
  CRE concentration trend (YoY). The true maturity-roll signal would require
  the NIC/RSSD historical file + RC-C Part II schedule.

- **GAP-3** (AOCI/HTM): FDIC publishes total securities (SC) but not the
  AFS/HTM split or unrealized P&L. AOCI excluded from V3 composite.

- **GAP-4** (FHLB advances): Not available as a standalone field in FDIC
  financials. Excluded from V3.

**DEPUNINS/LNNDEPC definition-break caveat (pre-registered):**
  DEPUNINS (estimated uninsured deposits) methodology: pre-2009 = deposits
  >$100K; 2009-2011 = transition to $250K; 2012+ = self-reported for banks
  >=$1B. Our sample (2018+) is methodologically consistent (all BHCs well
  above $1B). LNNDEPC (brokered deposits) has a definitional narrowing effective
  2021-Q2 per the FDIC brokered deposit rule revision, creating a structural
  step-down in some banks' reported brokered deposits from 2021-Q2 onward.
  V2 (streak signal) and V3 (level composite) users should note this break
  when comparing pre/post-2021 levels.

### Asset size distribution (max quarter, $K)

| stat | value |
|------|-------|
| min | $53,127,804K |
| 25% | $79,058,364K |
| 50% | $163,179,000K |
| 75% | $234,232,580K |
| max | $692,852,440K |

All tickers pass the >=$2B assets threshold (smallest surviving bank: CFR at $53,127,804K).

---

## 2. Signal design

| Variant | Description | Gate | Pre-registered expectation |
|---------|-------------|------|---------------------------|
| V1 | CRE stress proxy: NCRENRER YoY delta + CRE/equity YoY delta + CRE/loans YoY delta | GATED | Primary; must beat V3 ex-2023 |
| V2 | Deposit-mix deterioration streak (uninsured + brokered, YoY deseasonalized) | GATED | Secondary |
| V3 | Canonical-ratio level composite (control, spanned) | GATED | Expected weaker ex-2023 |
| V4 | V1 at 21d horizon (robustness check) | NON-GATED | — |
| V5 | V1 -> max-drawdown AVOID lens | NON-GATED | — |

**TrialLedger:** 6 distinct configs registered for family `w3_bank_callreport_stress`
(3 variants x 2 horizons = 6 configs; BH-FDR correction on 3 gated x 1 primary horizon).

**Deseasonalization amendment:** all quarterly deltas use diff(4) [YoY] instead of
diff(1) [QoQ] as in the original build. This applies to NCRENRER, CRE/equity,
CRE/loans, uninsured-deposit share, and brokered-deposit share changes.
Level composites (V3) are not affected. See module docstring for rationale.

---

## 3. Results — IC by variant and horizon

### 3.1 Full sample (2018-Q1 to 2026-Q1, 33 quarters)

| Variant | Horizon | N dates | Mean IC | Std IC | ICIR | %Pos | t-stat | p-val | 95% CI | CI excl. 0? |
|---------|---------|---------|---------|--------|------|------|--------|-------|--------|-------------|
| V1 | 21d | 28 | -0.0270 | 0.2356 | -0.606 | 0.393 | -0.606 | 0.5448 | [-0.1119, 0.0620] | no |
| V1 | 63d | 28 | -0.0061 | 0.2321 | -0.140 | 0.500 | -0.140 | 0.8888 | [-0.0660, 0.0523] | no |
| V2 | 21d | 28 | 0.0563 | 0.2195 | 1.357 | 0.643 | 1.357 | 0.1746 | [-0.0012, 0.1160] | no |
| V2 | 63d | 28 | 0.0418 | 0.2030 | 1.090 | 0.643 | 1.090 | 0.2759 | [-0.0157, 0.0999] | no |
| V3 | 21d | 28 | 0.0443 | 0.1979 | 1.184 | 0.571 | 1.184 | 0.2363 | [-0.0047, 0.0943] | no |
| V3 | 63d | 28 | 0.1057 | 0.2577 | 2.170 | 0.643 | 2.170 | 0.0300 | [0.0335, 0.1876] | YES |

### 3.2 Ex-2023 decomposition (mandatory crisis-concentration gate)

Crisis window dropped: signal dates 2022-11-29 to 2023-11-29 (PIT-shifted by 60d).

| Variant | Horizon | N dates | Mean IC | ICIR | %Pos | t-stat | p-val | CI excl. 0? |
|---------|---------|---------|---------|------|------|--------|-------|-------------|
| V1 | 21d | 23 | -0.0157 | -0.317 | 0.435 | -0.317 | 0.7511 | no |
| V1 | 63d | 23 | 0.0089 | 0.178 | 0.565 | 0.178 | 0.8584 | no |
| V2 | 21d | 23 | 0.0766 | 1.788 | 0.652 | 1.788 | 0.0738 | YES |
| V2 | 63d | 23 | 0.0576 | 1.433 | 0.652 | 1.433 | 0.1519 | YES |
| V3 | 21d | 23 | 0.0574 | 1.324 | 0.565 | 1.324 | 0.1854 | YES |
| V3 | 63d | 23 | 0.1171 | 2.086 | 0.696 | 2.086 | 0.0370 | YES |

### 3.3 Crisis-only (2023 window)

| Variant | Horizon | N dates | Mean IC | ICIR | %Pos | t-stat | p-val |
|---------|---------|---------|---------|------|------|--------|-------|
| V1 | 21d | 5 | -0.0787 | -0.719 | 0.200 | -0.719 | 0.4723 |
| V1 | 63d | 5 | -0.0751 | -0.798 | 0.200 | -0.798 | 0.4249 |
| V2 | 21d | 5 | -0.0370 | -0.293 | 0.600 | -0.293 | 0.7697 |
| V2 | 63d | 5 | -0.0309 | -0.270 | 0.600 | -0.270 | 0.7873 |
| V3 | 21d | 5 | -0.0160 | -0.246 | 0.600 | -0.246 | 0.8057 |
| V3 | 63d | 5 | 0.0534 | 0.558 | 0.400 | 0.558 | 0.5770 |

---

## 4. Gate verdicts

### 4.1 Deflated Sharpe (DSR) — gated variants at 63d, n_trials=6

Threshold: DSR p >= 0.90 (per family constitution; 'the only door to GO').

| Variant | DSR p | BH-adjusted p | DSR verdict |
|---------|-------|---------------|-------------|
| V1 | 0.0753 | 0.2259 | FAIL |
| V2 | 0.3942 | 0.5913 | FAIL |
| V3 | 0.7695 | 0.7695 | FAIL |

### 4.2 Spannedness gate: V1 vs V3 ex-2023

Criterion: |IC(V1 ex-2023)| > |IC(V3 ex-2023)| at 63d horizon.

| Metric | V1 (primary) | V3 (control) | V1 > V3? |
|--------|--------------|--------------|----------|
| |mean IC| ex-2023 (63d) | 0.0089 | 0.1171 | FAIL |

**Interpretation:** V3 >= V1 ex-2023 — the canonical-level ratios contain at least as much signal as the proxy. The spannedness failure may reflect missing CRE maturity-bucket data (GAP-2): V1 is a delinquency+concentration proxy, not the exact maturity-roll signal that the adjudication identified as non-spanned.

### 4.3 V4 — 21d ruler robustness (non-gated)

| Metric | V1@21d ex-2023 | V3@21d ex-2023 |
|--------|----------------|----------------|
| Mean IC | -0.0157 | 0.0574 |
| ICIR | -0.317 | 1.324 |

### 4.4 V5 — AVOID-side drawdown lens (non-gated)

Does high V1 score predict deeper max drawdown in next 63d?
A positive IC here = stressed banks suffer larger drawdowns = AVOID signal.

| Metric | Value |
|--------|-------|
| V5 IC (full, V1 -> max_dd_63d) | -0.0519 |
| V5 IC (ex-2023) | 0.0164 |
| N observations | 626 |

---

## 5. Overall verdict: ACCRUE

**DSR gate did not clear (p=0.075, threshold=0.90) and/or spannedness gate borderline. Pre-registered expectation: this IS the expected outcome for n=1 crisis. Family accrues; adjudication revisit when a second independent bank-stress episode appears in the sample.**

PIT-lag amendment cross-check (see §1): the prior merged run (mixed 45/60d
lag) landed ACCRUE; this regenerated run (uniform 60d lag) lands
ACCRUE.

Sign finding: V1 63d mean IC = -0.0061 (NEGATIVE IC = stressed banks slightly OUTPERFORMED (contrarian/value-reversal pattern)).
V3 63d mean IC = 0.1057. DSR gate: V1 p=0.0753,
V2 p=0.3942,
V3 p=0.7695 — none >= 0.90 threshold.
Spannedness gate: V3 >= V1 ex-2023 (FAIL).

Note on survivorship correction: the three failed banks (SIVB, SBNY, FRC)
are included in the panel and contribute terminal -100% returns at delisting.
Their inclusion corrects the survivorship bias identified in review (the prior
result was measured only on banks that survived the 2023 stress episode).
The current IC values incorporate their balance-sheet signal scores and
forward returns including the terminal settlement.

Pre-registered expectation (from SIGNAL_LAB_FRONTIER_WAVE3_FABLE_ADJUDICATION_2026-07-06.md §1):
> 'Mandatory ex-2023 decomposition; the pre-registered expectation is that the
> first adjudication lands ACCRUE-with-clock awaiting a second independent episode,
> not GO. A spectacular in-sample Sharpe here is the archetypal single-event dummy.'

The DSR gate result (p = 0.0753) is consistent with the pre-registered expectation.

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
Failed-bank (SIVB/SBNY/FRC) rows are part of the canonical store panel:
the collector backfills them per-CERT via `FAILED_TICKER_CERT_MAP` (frozen
historical data; missing quarters after each bank's failure date are
expected). A live FDIC fetch inside `w3_bank_callreport_stress_phase0.py`
remains as fallback for store copies that predate the backfill.

---

*Report generated by `scripts/w3_bank_callreport_stress_phase0.py`*
