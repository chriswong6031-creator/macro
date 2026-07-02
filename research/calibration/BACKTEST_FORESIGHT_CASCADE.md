# Backtest Foresight Cascade — Wave 3a Calibration Results

*Generated: 2026-07-02  |  Replay: 2019-01 → 2025-12  |  Script: scripts/research/backtest_foresight_cascade.py*

> **Wave 3a (§3.3) — research-only script.  No live engine constants changed.**
> Thresholds RECOMMENDED here go through the §3.2 shadow machinery + human approval.

---

## 1. PIT Accounting

- **Vintage matrix present:** YES
- **Bottleneck series with PIT vintages:** 0/8

**ALL BOTTLENECK SERIES ARE LATEST-REVISED-TRUNCATED (look-ahead contaminated).**

The vintage matrix exists but contains NONE of the bottleneck/power series
(CAPUTLG*, PCU*, MNFCTRIRSA, AMTMUO, AMTMVS).  A FRED_API_KEY + re-run of
`collectors/fred.py fetch_vintages` (now that these series are in
`config.yml fred.vintage_series`) will backfill them so the next Wave 3a run
upgrades to genuine point-in-time.  Until then, every FRED leg in this backtest
is the latest-revised value truncated at the replay date: LOOK-AHEAD CONTAMINATED.

**Label: `pit_mode = LATEST_REVISED_TRUNCATED`** (all 0/8 bottleneck series missing from vintage matrix)

- **EDGAR text leg:** EFFECTIVELY ABSENT (query success rate 5.6% — network blocked or cache empty; the text leg contributed nothing to this run)

---

## 2. Band-Threshold Sweep — PRECIPICE vs WATCH Discrimination at 90d

| TIGHT cutoff | PRECIPICE mean excess (90d) | WATCH mean excess (90d) | Discrimination |
|---|---|---|---|
| 0.5 | -0.08% | 2.47% | -2.55% |
| 0.75 | -2.24% | 2.59% | -4.83% |
| 1.0 | -5.64% | 2.56% | -8.20% |
| 1.25 | n/a (no PRECIPICE obs) | 2.60% | n/a |

**Recommended TIGHT cutoff:** 0.75 — INDETERMINATE (no positive discrimination — keep live threshold 0.75)

---

## 3. Stage Hierarchy — Empirical Forward Returns by Stage

*(Live cutoff 0.75; all themes; 2019-2025)*

| Stage | N obs | 30d excess | 60d excess | 90d excess | 180d excess |
|---|---|---|---|---|---|
| PRECIPICE | 16 | -1.28% | -1.17% | -2.24% | 8.64% |
| PRECIPICE (text) | 0 | n/a (no basket data) | n/a (no basket data) | n/a (no basket data) | n/a (no basket data) |
| BROADENING | 65 | 0.19% | 1.69% | 2.56% | 4.98% |
| WATCH | 1431 | 0.73% | 1.62% | 2.59% | 6.09% |

---

## 4. Known-Answer Validation

**Pass rate: 0/5**

| Episode | Expected | Frac TIGHT | Frac LOOSE | Pass |
|---|---|---|---|---|
| memory_storage 2020-07→2021-03 | tightening | 0% | 100% | ✗ |
| ai_semiconductors 2021-01→2021-12 | tightening | 0% | 50% | ✗ |
| semicap_equipment 2021-01→2021-12 | tightening | 0% | 50% | ✗ |
| memory_storage 2024-01→2024-09 | tightening | 0% | 100% | ✗ |
| memory_storage 2022-06→2023-06 | loosening | 0% | 38% | ✗ |

---

## 5. Honesty Section — Non-PIT Inputs & Caveats

### Non-PIT inputs

| Series / Input | PIT status | Caveat |
|---|---|---|
| AMTMUO | LATEST-REVISED-TRUNCATED | Look-ahead contaminated: post-replay revisions visible. Thresholds from this series apply only via §3.2 shadow ledger. |
| AMTMVS | LATEST-REVISED-TRUNCATED | Look-ahead contaminated: post-replay revisions visible. Thresholds from this series apply only via §3.2 shadow ledger. |
| CAPUTLG331S | LATEST-REVISED-TRUNCATED | Look-ahead contaminated: post-replay revisions visible. Thresholds from this series apply only via §3.2 shadow ledger. |
| CAPUTLG3344S | LATEST-REVISED-TRUNCATED | Look-ahead contaminated: post-replay revisions visible. Thresholds from this series apply only via §3.2 shadow ledger. |
| CAPUTLG334S | LATEST-REVISED-TRUNCATED | Look-ahead contaminated: post-replay revisions visible. Thresholds from this series apply only via §3.2 shadow ledger. |
| MNFCTRIRSA | LATEST-REVISED-TRUNCATED | Look-ahead contaminated: post-replay revisions visible. Thresholds from this series apply only via §3.2 shadow ledger. |
| PCU331110331110 | LATEST-REVISED-TRUNCATED | Look-ahead contaminated: post-replay revisions visible. Thresholds from this series apply only via §3.2 shadow ledger. |
| PCU334413334413 | LATEST-REVISED-TRUNCATED | Look-ahead contaminated: post-replay revisions visible. Thresholds from this series apply only via §3.2 shadow ledger. |
| EDGAR phrase counts | ABSENT | Text leg absent from this backtest run. |

### Survivorship caveat

Theme member lists reflect **today's config.yml** (as of the run date).
Members that were delisted, merged, or restructured during 2019-2025 are excluded.
This biases estimated forward basket returns UPWARD.  For large-cap-heavy mapped
themes (memory, semis, semicap, metals) the bias is modest (0-5% across the window).
For newer-company themes (space, fintech, some healthcare names) it may be larger.

### Text-leg filer-count approximation

The replay uses quarterly aggregated EDGAR phrase counts without per-filer breakdown.
The live engine requires ≥2 distinct filers for the text leg to enter the composite.
The replay approximates this gate: any positive accel is treated as 'sufficient'.
This may overcount text-band episodes in the replay vs. live behavior.

---

## 6. Threshold Recommendations (for §3.2 shadow promotion)

> **This run used LATEST-REVISED-TRUNCATED data for all bottleneck series.**
> The findings below are INFORMATIVE but NOT authoritative.  Re-run after
> `collectors/fred.py fetch_vintages` with a FRED_API_KEY to upgrade to genuine PIT.

**Forward return coverage:** 18/18 themes have priceable member
tickers in data/yahoo/ for this run.

- **TIGHT cutoff:** 0.75 — INDETERMINATE (no positive discrimination — keep live threshold 0.75)
- **SOLD_OUT cutoff:** 1.5 (maintained at 2× TIGHT)
- **Z_WIN:** 120 months (no sweep performed — expanding in a future run)
- **Leg weights:** current PROVISIONAL weights (0.21/0.165/0.1875/0.1875/0.25) maintained
  pending ≥30 graded PRECIPICE rows from the shadow ledger (§3.2).
- **Known-answer root cause:** the mapped physical legs are themselves
  NON-RESPONSIVE — this is NOT just the economy-wide inv/sales drag. Verified
  counterfactuals: removing MNFCTRIRSA entirely still never reads TIGHT (max
  no-inventory composite +0.09 vs the 0.75 threshold), and the semi-specific
  NAICS-3344 capacity leg never exceeded tightness 0.37 even through the
  documented 2021 crunch. Reweighting the existing legs will NOT fix this;
  the leverage is per-theme member-level physical fingerprints (XBRL
  inventory/RPO/margin legs — upgrade-doc Q2), which this result strengthens.

- **Statistical fragility (disclose before citing the discrimination table):**
  the entire PRECIPICE bucket at cutoff 0.75 is 6 rows from ONE Q3-2021 metals
  episode — two themes (rare_earth, copper_steel) with IDENTICAL NAICS-331 legs
  and overlapping forward windows, driven by a single PPI-YoY z=5.33 outlier.
  Effective sample: ~1 episode. The negative discrimination headline is a
  1-observation read, not a calibration result.

> These recommendations do NOT change any live engine constants.  Promotion requires
> a shadow ledger slice that beats the live slice with BY-FDR significance (§3.2).

---

*Backtest data: `data/research/backtest_foresight_results.parquet`*
*PIT mode: `LATEST_REVISED_TRUNCATED` — see §4 above*
