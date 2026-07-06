# Insider Sponsor LH Family — Ruler-P Study Results

**Family:** `long_hold.insider_sponsor_lh` | **m = 3** | **Ruler-P cutoff:** fires ≤ 2023-12-31 | **Generated:** 2026-07-06

**Authority ceiling:** DISPLAY ONLY (G1-DEFERRED ruling 2026-07-06). No SURVIVE/KILL vocabulary. All cells stamped UPPER BOUND (survivorship-biased).

---

## In plain English

This study tests whether three insider-buying signals measured at the time of a tactical entry fire predict which fires end up as cheap traps (durable hold candidates) vs tactical-only at 252 days. The contrast is cheap_trap vs tactical_only using fires up to end-2023 only (Ruler-P). Because the data goes back to 2014, all results carry a survivorship-bias stamp (UPPER BOUND). No result here is a final verdict — that requires Ruler-H on 2025+ OOS data at the G1-Retest (~2027-H2).

## Coverage

| Feature | Type | Expected sign | Coverage in Ruler-P |
|---|---|---|---|
| `insider_net_usd_mcap_6m_pct` | cont | + | 39.0% (RETAINED) |
| `cluster_buy_pre_fire` | bin | + | 100.0% (RETAINED) |
| `officer_buy_flag` | bin | + | 100.0% (RETAINED) |

## Cell: full_ruler_p_2014-2023

Stamp: **UPPER_BOUND** | cheap_trap n=2663 | tactical_only n=2662 (after episode-cluster dedup)

| Feature | Type | RBC | p-value | q-value (BH) | Rejected (BH) | Passes reshuffle | Reshuffle p90 | CI lo | CI hi | n_pos | n_neg | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `insider_net_usd_mcap_6m_pct` | cont | -0.032 | 0.2117 | 0.3175 | False | False | 0.025 | -0.187 | 0.038 | 861 | 1213 | NULL |
| `cluster_buy_pre_fire` | bin | 0.011 | 0.0601 | 0.1802 | False | True | 0.009 | -0.035 | 0.022 | 2663 | 2662 | NULL |
| `officer_buy_flag` | bin | 0.002 | 0.8279 | 0.8279 | False | False | 0.009 | -0.055 | 0.016 | 2663 | 2662 | NULL |

## Cell: fit_2014-2019

Stamp: **UPPER_BOUND** | cheap_trap n=376 | tactical_only n=378 (after episode-cluster dedup)

| Feature | Type | RBC | p-value | q-value (BH) | Rejected (BH) | Passes reshuffle | Reshuffle p90 | CI lo | CI hi | n_pos | n_neg | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `insider_net_usd_mcap_6m_pct` | cont | 0.018 | 0.7318 | 1.0000 | False | False | 0.053 | -0.224 | 0.145 | 217 | 249 | NULL |
| `cluster_buy_pre_fire` | bin | 0.000 | 1.0000 | 1.0000 | False | False | 0.016 | -0.023 | 0.044 | 376 | 378 | NULL |
| `officer_buy_flag` | bin | 0.003 | 0.8568 | 1.0000 | False | False | 0.019 | -0.044 | 0.055 | 376 | 378 | NULL |

## Cell: oos_2020-2021

Stamp: **UPPER_BOUND_partial** | cheap_trap n=467 | tactical_only n=470 (after episode-cluster dedup)

| Feature | Type | RBC | p-value | q-value (BH) | Rejected (BH) | Passes reshuffle | Reshuffle p90 | CI lo | CI hi | n_pos | n_neg | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `insider_net_usd_mcap_6m_pct` | cont | -0.095 | 0.0967 | 0.1451 | False | False | 0.069 | -0.348 | 0.435 | 175 | 243 | NULL |
| `cluster_buy_pre_fire` | bin | 0.019 | 0.0818 | 0.1451 | False | True | 0.011 | -0.012 | 0.068 | 467 | 470 | NULL |
| `officer_buy_flag` | bin | 0.005 | 0.7646 | 0.7646 | False | False | 0.017 | -0.045 | 0.091 | 467 | 470 | NULL |

## Cell: oos_2022-2023

Stamp: **UPPER_BOUND_partial** | cheap_trap n=1820 | tactical_only n=1814 (after episode-cluster dedup)

| Feature | Type | RBC | p-value | q-value (BH) | Rejected (BH) | Passes reshuffle | Reshuffle p90 | CI lo | CI hi | n_pos | n_neg | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `insider_net_usd_mcap_6m_pct` | cont | -0.034 | 0.3244 | 0.4867 | False | False | 0.037 | -0.356 | 0.136 | 469 | 721 | NULL |
| `cluster_buy_pre_fire` | bin | 0.011 | 0.1485 | 0.4455 | False | False | 0.013 | -0.093 | 0.030 | 1820 | 1814 | NULL |
| `officer_buy_flag` | bin | 0.001 | 0.9509 | 0.9509 | False | False | 0.013 | -0.111 | 0.029 | 1820 | 1814 | NULL |

---

## Protocol notes

- **BH-FDR:** q ≤ 0.1 across all m=3 retained features
- **Reshuffle null:** 1000 permutations, seed=42 (LOCKED)
- **Episode-cluster floor:** ≥25 per arm
- **Episode-cluster dedup:** ±14 calendar days (≈±10 trading days, documented deviation from LH-R4)
- **CI method:** wider of cluster-bootstrap (ticker × macro_regime; seed=44) and block-bootstrap (seed=43)
- **Ruler-P cutoff:** fires ≤ 2023-12-31 only. OOS-2 2025+ cohort is reserved for Ruler-H at G1-Retest (~2027-H2). No contact.
- **Authority ceiling:** DISPLAY ONLY. A feature passing both BH-FDR and reshuffle null may be shown in display context. SURVIVE/KILL vocabulary is banned until Ruler-H.
- **TrialLedger:** `log_declared_budget(3, family='long_hold.insider_sponsor_lh')` called BEFORE p-value computation.
- **Survivorship bias:** all Ruler-P cells are UPPER BOUND (pre-2021-07 tickers survivorship-biased per LH-R3).
- The word 'validated' does not appear in this document (CI-enforced).

**G1 ratification:** PENDING RULER-H (OOS-2, ~2027-H2). These results are display-tier upper bounds only.
