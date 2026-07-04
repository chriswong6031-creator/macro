# Oracle P8 — Washout-Confluence Gauntlet — Results

**Registration:** [ORACLE_GAUNTLET_P8_WASHOUT_PREREG.md](ORACLE_GAUNTLET_P8_WASHOUT_PREREG.md)
**Inherits:** [ORACLE_GAUNTLET_P3_PREREG.md](ORACLE_GAUNTLET_P3_PREREG.md)
**Seed:** 20260704  **Trials:** 14  **Runtime:** 104.55s
**BH-FDR:** q=0.10, 1/14 trials rejected

> All verdict cells marked **PENDING ADJUDICATION** — adjudicator applies pre-bound vocabulary from §3 of the registration.

---

## P-W1 — Standalone Washout Claim (primary)

| Horizon | n | Raw mean (exc SPY) | Hit rate | Placebo p95 | Boot CI lo | Boot CI hi | Boot p | BH pass | G1 | G2 | G3 | G4 | G6 mean | G6 hit | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| +21d | 639 | 0.05% | 50.08% | 0.20% | -0.27% | 0.37% | 0.3920 | N | ✗ | ✗ | ✓ | ✗ | — | — | PENDING ADJUDICATION |
| +63d | 629 | 0.45% | 50.72% | 0.31% | -0.18% | 1.09% | 0.0880 | N | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | PENDING ADJUDICATION |

### P-W1 Era consistency

| Horizon | 1999-2014 | 2015-2019 | 2020-2022 | 2023-2026 | G4 note |
|---|---|---|---|---|---|
| +21d | 0.14% | -0.15% | 0.39% | -0.38% | 2/4 eras positive, 2023-2026=-0.0038 |
| +63d | 0.52% | -0.74% | 1.29% | 1.01% | 3/4 eras positive, 2023-2026=0.0101 |

---

## P-W2 — Confluence Multiplier (primary; genuinely open)

### P-W2 Increment table (conditioned vs unconditioned vs coin-flip placebo)

| Horizon | Condition | n_cond | n_uncond | Uncond mean | Cond mean | Increment | Boot CI lo | Boot CI hi | G6 > coin-flip | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| +21d | accel_z_5d>0 | 541 | 639 | 0.05% | -0.03% | -0.08% | -1.42% | 1.40% | ✗ | PENDING ADJUDICATION |
| +21d | opp_out_active | 201 | 639 | 0.05% | 0.16% | 0.11% | -2.10% | 2.63% | ✗ | PENDING ADJUDICATION |
| +21d | both | 160 | 639 | 0.05% | 0.23% | 0.19% | -2.18% | 3.04% | ✗ | PENDING ADJUDICATION |
| +63d | accel_z_5d>0 | 534 | 629 | 0.45% | 0.14% | -0.31% | -2.22% | 2.49% | ✗ | PENDING ADJUDICATION |
| +63d | opp_out_active | 194 | 629 | 0.45% | 1.59% | 1.14% | -2.67% | 6.30% | ✓ | PENDING ADJUDICATION |
| +63d | both | 155 | 629 | 0.45% | 1.39% | 0.94% | -3.17% | 6.40% | ✓ | PENDING ADJUDICATION |

---

## B-Comparison: P-W1 vs sector_signals BUY base rate

> Source: engine/sector_signals.py STATE_BASE_RATES

| Metric | P-W1 @63d | sector_signals BUY @63d |
|---|---|---|
| Excess vs SPY mean | 0.45% | 1.1% |
| Hit rate | 50.7% | 56.0% |
| Exceeds BUY mean | ✗ | baseline |
| Exceeds BUY hit | ✗ | baseline |

---

## Per-ETF entry counts (P-W1, 27y universe)

| ETF | Washout entries (expected ~10-40) |
|---|---|
| XLK | 69 |
| XLV | 65 |
| XLF | 71 |
| XLY | 70 |
| XLC | 17 |
| XLI | 68 |
| XLP | 61 |
| XLE | 74 |
| XLU | 61 |
| XLRE | 24 |
| XLB | 61 |

---

## S-W3 — Monthly washouts (secondary, likely underpowered)

| Horizon | n | Mean | Hit rate | Boot p | Underpowered note | Verdict |
|---|---|---|---|---|---|---|
| +21d | 152 | 0.09% | 52.63% | 0.4105 | — | PENDING ADJUDICATION |
| +63d | 151 | -0.86% | 43.71% | 0.9095 | — | PENDING ADJUDICATION |

## S-W4 — Topping exit mirror (secondary)

| Horizon | n | Actual excess (should be neg) | Boot p | G1 | G2 | Verdict |
|---|---|---|---|---|---|---|
| +21d | 814 | -0.12% | 0.1955 | ✗ | ✗ | PENDING ADJUDICATION |
| +63d | 811 | -0.24% | 0.2555 | ✓ | ✗ | PENDING ADJUDICATION |

## S-W5 — Theme echo (Tier-M, 2021+, confirmatory only)

| Horizon | n | Mean | Hit rate | Boot p | Verdict |
|---|---|---|---|---|---|
| +21d | 4326 | 1.43% | 51.34% | 0.0790 | PENDING ADJUDICATION |
| +63d | 4144 | 6.01% | 54.20% | 0.0005 | PENDING ADJUDICATION |

---

*Trial ledger: p8_trial_ledger.json (gitignored) — 14 trials before p-computation.*
*Runtime: 104.55s*

## BH-FDR summary

q=0.10, 1/14 rejected

| trial_id | p_value | bh_rejected |
|---|---|---|
| pw1_21d | 0.3920 | N |
| pw1_63d | 0.0880 | N |
| pw2_cond_a_21d | 0.5150 | N |
| pw2_cond_a_63d | 0.4530 | N |
| pw2_cond_b_21d | 0.4565 | N |
| pw2_cond_b_63d | 0.2365 | N |
| pw2_cond_both_21d | 0.4205 | N |
| pw2_cond_both_63d | 0.2725 | N |
