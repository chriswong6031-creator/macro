# Oracle P3 Gauntlet — Results

**Registration:** [ORACLE_GAUNTLET_P3_PREREG.md](ORACLE_GAUNTLET_P3_PREREG.md)
**Seed:** 20260704  **Trials:** 109  **Runtime:** 114.71s
**BH-FDR:** q=0.10, 35/109 trials rejected

> Verdicts in this document are left as **PENDING ADJUDICATION** — the orchestrator applies the pre-bound vocabulary per §3 of the registration.

---

## Primary endpoints

| Endpoint | Direction | n | Raw mean | DA mean | Placebo p95 | Boot CI lo | Boot CI hi | Boot p | BH pass | G1 | G2 | G3 | G4 | G6 | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **P-EXIT** | out | 388 | 0.15% | -0.15% | 0.16% | -0.55% | 0.26% | 0.7740 | N | ✗ | ✗ | ✗ | ✗ | ✗ | PENDING ADJUDICATION |
| **P-ENTRY** | in | 355 | -0.17% | -0.17% | 0.23% | -0.70% | 0.42% | 0.7210 | N | ✗ | ✗ | ✗ | ✗ | ✗ | PENDING ADJUDICATION |

## Secondary endpoint grid (S1) — all 18 cells

| cell_id | direction | tier | h | n | raw mean | DA mean | placebo p95 | boot CI | boot p | BH pass | G1 | G2 | G3 | G4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ep_out_onset_5d | out | onset | 5d | 391 | -0.50% | 0.50% | 0.08% | [0.31%, 0.70%] | 0.0000 | N | ✓ | ✓ | ✓ | ✓ |
| ep_out_onset_21d | out | onset | 21d | 388 | -0.25% | 0.25% | 0.13% | [-0.05%, 0.55%] | 0.0505 | N | ✓ | ✗ | ✓ | ✓ |
| ep_out_onset_63d | out | onset | 63d | 384 | -0.44% | 0.44% | 0.39% | [-0.12%, 1.03%] | 0.0595 | N | ✓ | ✗ | ✓ | ✓ |
| ep_out_confirmed_5d | out | confirmed | 5d | 391 | 0.13% | -0.13% | 0.07% | [-0.42%, 0.14%] | 0.8270 | N | ✗ | ✗ | ✗ | ✓ |
| ep_out_confirmed_21d | out | confirmed | 21d | 388 | 0.15% | -0.15% | 0.16% | [-0.55%, 0.26%] | 0.7740 | N | ✗ | ✗ | ✗ | ✗ |
| ep_out_confirmed_63d | out | confirmed | 63d | 384 | -0.05% | 0.05% | 0.46% | [-0.52%, 0.68%] | 0.4100 | N | ✗ | ✗ | ✗ | ✗ |
| ep_out_undeniable_5d | out | undeniable | 5d | 369 | 0.05% | -0.05% | 0.07% | [-0.33%, 0.21%] | 0.6340 | N | ✗ | ✗ | ✗ | ✓ |
| ep_out_undeniable_21d | out | undeniable | 21d | 369 | 0.14% | -0.14% | 0.19% | [-0.52%, 0.20%] | 0.7735 | N | ✗ | ✗ | ✗ | ✗ |
| ep_out_undeniable_63d | out | undeniable | 63d | 366 | -0.03% | 0.03% | 0.48% | [-0.49%, 0.59%] | 0.4690 | N | ✗ | ✗ | ✗ | ✗ |
| ep_in_onset_5d | in | onset | 5d | 356 | 0.57% | 0.57% | 0.09% | [0.40%, 0.74%] | 0.0000 | N | ✓ | ✓ | ✓ | ✓ |
| ep_in_onset_21d | in | onset | 21d | 355 | 0.62% | 0.62% | 0.27% | [0.13%, 1.16%] | 0.0075 | Y | ✓ | ✓ | ✓ | ✓ |
| ep_in_onset_63d | in | onset | 63d | 350 | 0.07% | 0.07% | 0.45% | [-0.61%, 0.82%] | 0.4335 | N | ✗ | ✗ | ✓ | ✗ |
| ep_in_confirmed_5d | in | confirmed | 5d | 356 | 0.00% | 0.00% | 0.09% | [-0.20%, 0.23%] | 0.5100 | N | ✗ | ✗ | ✗ | ✗ |
| ep_in_confirmed_21d | in | confirmed | 21d | 355 | -0.17% | -0.17% | 0.23% | [-0.70%, 0.42%] | 0.7210 | N | ✗ | ✗ | ✗ | ✗ |
| ep_in_confirmed_63d | in | confirmed | 63d | 350 | -0.58% | -0.58% | 0.47% | [-1.37%, 0.32%] | 0.9075 | N | ✗ | ✗ | ✗ | ✗ |
| ep_in_undeniable_5d | in | undeniable | 5d | 341 | 0.13% | 0.13% | 0.10% | [-0.05%, 0.34%] | 0.0815 | N | ✓ | ✗ | ✓ | ✓ |
| ep_in_undeniable_21d | in | undeniable | 21d | 341 | -0.13% | -0.13% | 0.22% | [-0.56%, 0.38%] | 0.7240 | N | ✗ | ✗ | ✗ | ✗ |
| ep_in_undeniable_63d | in | undeniable | 63d | 336 | -0.50% | -0.50% | 0.48% | [-1.14%, 0.18%] | 0.9280 | N | ✗ | ✗ | ✗ | ✗ |

## G3 Regime stratification — primary endpoints

| Endpoint | Stratum | DA mean |
|---|---|---|
| P-EXIT | vix_high | -0.18% |
| P-EXIT | vix_low | -0.11% |
| P-EXIT | spy_above_200 | -0.01% |
| P-EXIT | spy_below_200 | -0.40% |
| P-EXIT | G3 note | G3 fail: larger stratum vix_high (n=250) has non-positive mean=-0.0018; G3 fail: larger stratum spy_above_200 (n=246) has non-positive mean=-0.0001 |
| P-ENTRY | vix_high | -0.34% |
| P-ENTRY | vix_low | -0.02% |
| P-ENTRY | spy_above_200 | -0.03% |
| P-ENTRY | spy_below_200 | -0.39% |
| P-ENTRY | G3 note | G3 fail: larger stratum vix_low (n=191) has non-positive mean=-0.0002; G3 fail: larger stratum spy_above_200 (n=217) has non-positive mean=-0.0003 |

## G4 Era consistency — primary endpoints

| Endpoint | Era | DA mean |
|---|---|---|
| P-EXIT | 1999-2014 | -0.34% |
| P-EXIT | 2015-2019 | -0.55% |
| P-EXIT | 2020-2022 | 0.53% |
| P-EXIT | 2023-2026 | 0.11% |
| P-EXIT | G4 note | 2/4 eras positive, 2023-2026=0.0011 |
| P-ENTRY | 1999-2014 | -0.02% |
| P-ENTRY | 2015-2019 | -0.35% |
| P-ENTRY | 2020-2022 | -0.30% |
| P-ENTRY | 2023-2026 | -0.31% |
| P-ENTRY | G4 note | 0/4 eras positive, 2023-2026=-0.0031 |

## S2 Two-sided premium (Tier M, display-grade)

| Metric | Value |
|---|---|
| n two-sided | 491 |
| n not two-sided | 4976 |
| DA mean two-sided | 2.15% |
| DA mean not two-sided | 0.64% |
| Boot p-value | 0.0000 |
| Note | Tier M; survivorship-watermarked; display-grade only |

## S3 Early-tier error rates (descriptive)

| Metric | Value |
|---|---|
| False-start rate OUT +5d | 38.11% |
| False-start rate IN +5d | 34.27% |
| Onset→confirmed rate OUT | 99.74% |
| Onset→confirmed rate IN | 99.72% |

## Benchmarks

### B1 — Momentum null (trailing-1M-RS decile)

| Endpoint | Oracle DA mean +21d | B1 momentum null DA mean | G6 pass |
|---|---|---|---|
| P-EXIT | -0.15% | -0.08% | ✗ |
| P-ENTRY | -0.17% | -0.01% | ✗ |

### B2 — vs sector_signals SELL baseline

| Metric | Value |
|---|---|
| Oracle undeniable OUT +63d DA mean | 0.03% |
| Oracle n | 366 |
| Baseline (sector_signals SELL) mean | -1.24% |
| Baseline hit rate | 40% |
| Baseline n | 169 |
| Note | informative only — different universe granularities (B2 per §3 G6) |

## S4 Routing cells summary

Total routing trials (cells × 3 horizons): 90
BH-FDR rejected: per trial ledger

| trial_id | n | horizon | mean_fwd_rs | hit_rate | boot_p | BH rejected |
|---|---|---|---|---|---|---|
| routing_ai_compute/software/high_vix_5d | 12 | 5d | -0.23% | 0.3636 | 1.0000 | N |
| routing_ai_compute/software/high_vix_10d | 12 | 10d | -0.60% | 0.2727 | 1.0000 | N |
| routing_ai_compute/software/high_vix_15d | 12 | 15d | -0.30% | 0.5455 | 1.0000 | N |
| routing_ai_compute/healthcare_defensive/high_vix_5d | 12 | 5d | 0.02% | 0.6364 | 0.0000 | Y |
| routing_ai_compute/healthcare_defensive/high_vix_10d | 12 | 10d | -0.06% | 0.6364 | 1.0000 | N |
| routing_ai_compute/healthcare_defensive/high_vix_15d | 12 | 15d | -0.36% | 0.4545 | 1.0000 | N |
| routing_ai_compute/consumer_staples_defensive/high_vix_5d | 12 | 5d | -0.81% | 0.2727 | 1.0000 | N |
| routing_ai_compute/consumer_staples_defensive/high_vix_10d | 12 | 10d | -1.04% | 0.0909 | 1.0000 | N |
| routing_ai_compute/consumer_staples_defensive/high_vix_15d | 12 | 15d | -0.80% | 0.2727 | 1.0000 | N |
| routing_ai_compute/energy_commodities/high_vix_5d | 12 | 5d | 0.53% | 0.7273 | 0.0000 | Y |
| routing_ai_compute/energy_commodities/high_vix_10d | 12 | 10d | 1.00% | 0.7273 | 0.0000 | Y |
| routing_ai_compute/energy_commodities/high_vix_15d | 12 | 15d | 0.93% | 0.7273 | 0.0000 | Y |
| routing_ai_compute/financials_rates/high_vix_5d | 12 | 5d | -0.16% | 0.6364 | 1.0000 | N |
| routing_ai_compute/financials_rates/high_vix_10d | 12 | 10d | -0.69% | 0.1818 | 1.0000 | N |
| routing_ai_compute/financials_rates/high_vix_15d | 12 | 15d | -0.64% | 0.3636 | 1.0000 | N |
| routing_ai_compute/long_duration_growth/high_vix_5d | 12 | 5d | -0.48% | 0.4545 | 1.0000 | N |
| routing_ai_compute/long_duration_growth/high_vix_10d | 12 | 10d | -0.25% | 0.4545 | 1.0000 | N |
| routing_ai_compute/long_duration_growth/high_vix_15d | 12 | 15d | -0.31% | 0.5455 | 1.0000 | N |
| routing_software/ai_compute/high_vix_5d | 12 | 5d | 1.77% | 0.8333 | 0.0000 | Y |
| routing_software/ai_compute/high_vix_10d | 12 | 10d | 1.79% | 0.7500 | 0.0000 | Y |
| routing_software/ai_compute/high_vix_15d | 12 | 15d | -0.14% | 0.5000 | 1.0000 | N |
| routing_software/healthcare_defensive/high_vix_5d | 12 | 5d | -0.37% | 0.4167 | 1.0000 | N |
| routing_software/healthcare_defensive/high_vix_10d | 12 | 10d | -0.82% | 0.2500 | 1.0000 | N |
| routing_software/healthcare_defensive/high_vix_15d | 12 | 15d | -0.71% | 0.2500 | 1.0000 | N |
| routing_software/consumer_staples_defensive/high_vix_5d | 12 | 5d | -0.99% | 0.2500 | 1.0000 | N |
| routing_software/consumer_staples_defensive/high_vix_10d | 12 | 10d | -1.06% | 0.3333 | 1.0000 | N |
| routing_software/consumer_staples_defensive/high_vix_15d | 12 | 15d | -0.95% | 0.2500 | 1.0000 | N |
| routing_software/energy_commodities/high_vix_5d | 12 | 5d | 0.04% | 0.5000 | 0.0000 | Y |
| routing_software/energy_commodities/high_vix_10d | 12 | 10d | -0.28% | 0.6667 | 1.0000 | N |
| routing_software/energy_commodities/high_vix_15d | 12 | 15d | -0.79% | 0.5833 | 1.0000 | N |
| routing_software/financials_rates/high_vix_5d | 12 | 5d | -0.46% | 0.3333 | 1.0000 | N |
| routing_software/financials_rates/high_vix_10d | 12 | 10d | -0.42% | 0.2500 | 1.0000 | N |
| routing_software/financials_rates/high_vix_15d | 12 | 15d | 0.95% | 0.7500 | 0.0000 | Y |
| routing_software/long_duration_growth/high_vix_5d | 12 | 5d | -0.89% | 0.3333 | 1.0000 | N |
| routing_software/long_duration_growth/high_vix_10d | 12 | 10d | -1.40% | 0.2500 | 1.0000 | N |
| routing_software/long_duration_growth/high_vix_15d | 12 | 15d | -1.32% | 0.2500 | 1.0000 | N |
| routing_consumer_staples_defensive/ai_compute/high_vix_5d | 10 | 5d | -0.28% | 0.3000 | 1.0000 | N |
| routing_consumer_staples_defensive/ai_compute/high_vix_10d | 10 | 10d | 0.07% | 0.5000 | 0.0000 | Y |
| routing_consumer_staples_defensive/ai_compute/high_vix_15d | 10 | 15d | -0.00% | 0.5000 | 1.0000 | N |
| routing_consumer_staples_defensive/software/high_vix_5d | 10 | 5d | -0.21% | 0.4000 | 1.0000 | N |
| routing_consumer_staples_defensive/software/high_vix_10d | 10 | 10d | 0.16% | 0.5000 | 0.0000 | Y |
| routing_consumer_staples_defensive/software/high_vix_15d | 10 | 15d | -0.14% | 0.3000 | 1.0000 | N |
| routing_consumer_staples_defensive/healthcare_defensive/high_vix_5d | 10 | 5d | 0.61% | 0.8000 | 0.0000 | Y |
| routing_consumer_staples_defensive/healthcare_defensive/high_vix_10d | 10 | 10d | -0.05% | 0.5000 | 1.0000 | N |
| routing_consumer_staples_defensive/healthcare_defensive/high_vix_15d | 10 | 15d | 0.32% | 0.4000 | 0.0000 | Y |
| routing_consumer_staples_defensive/energy_commodities/high_vix_5d | 10 | 5d | -0.02% | 0.5000 | 1.0000 | N |
| routing_consumer_staples_defensive/energy_commodities/high_vix_10d | 10 | 10d | -0.12% | 0.5000 | 1.0000 | N |
| routing_consumer_staples_defensive/energy_commodities/high_vix_15d | 10 | 15d | -0.20% | 0.6000 | 1.0000 | N |
| routing_consumer_staples_defensive/financials_rates/high_vix_5d | 10 | 5d | 0.94% | 0.7000 | 0.0000 | Y |
| routing_consumer_staples_defensive/financials_rates/high_vix_10d | 10 | 10d | 0.67% | 0.5000 | 0.0000 | Y |
| routing_consumer_staples_defensive/financials_rates/high_vix_15d | 10 | 15d | 0.55% | 0.6000 | 0.0000 | Y |
| routing_consumer_staples_defensive/long_duration_growth/high_vix_5d | 10 | 5d | 0.07% | 0.6000 | 0.0000 | Y |
| routing_consumer_staples_defensive/long_duration_growth/high_vix_10d | 10 | 10d | -0.96% | 0.2000 | 1.0000 | N |
| routing_consumer_staples_defensive/long_duration_growth/high_vix_15d | 10 | 15d | -0.39% | 0.5000 | 1.0000 | N |
| routing_energy_commodities/ai_compute/high_vix_5d | 10 | 5d | 0.23% | 0.6000 | 0.0000 | Y |
| routing_energy_commodities/ai_compute/high_vix_10d | 10 | 10d | 1.06% | 0.8000 | 0.0000 | Y |
| routing_energy_commodities/ai_compute/high_vix_15d | 10 | 15d | 0.12% | 0.8000 | 0.0000 | Y |
| routing_energy_commodities/software/high_vix_5d | 10 | 5d | -0.12% | 0.4000 | 1.0000 | N |
| routing_energy_commodities/software/high_vix_10d | 10 | 10d | -0.22% | 0.4000 | 1.0000 | N |
| routing_energy_commodities/software/high_vix_15d | 10 | 15d | -0.52% | 0.3000 | 1.0000 | N |
| routing_energy_commodities/healthcare_defensive/high_vix_5d | 10 | 5d | 0.12% | 0.3000 | 0.0000 | Y |
| routing_energy_commodities/healthcare_defensive/high_vix_10d | 10 | 10d | -0.49% | 0.2000 | 1.0000 | N |
| routing_energy_commodities/healthcare_defensive/high_vix_15d | 10 | 15d | -0.06% | 0.5000 | 1.0000 | N |
| routing_energy_commodities/consumer_staples_defensive/high_vix_5d | 10 | 5d | -0.30% | 0.4000 | 1.0000 | N |
| routing_energy_commodities/consumer_staples_defensive/high_vix_10d | 10 | 10d | -0.15% | 0.5000 | 1.0000 | N |
| routing_energy_commodities/consumer_staples_defensive/high_vix_15d | 10 | 15d | -0.41% | 0.5000 | 1.0000 | N |
| routing_energy_commodities/financials_rates/high_vix_5d | 10 | 5d | -0.16% | 0.4000 | 1.0000 | N |
| routing_energy_commodities/financials_rates/high_vix_10d | 10 | 10d | -1.12% | 0.2000 | 1.0000 | N |
| routing_energy_commodities/financials_rates/high_vix_15d | 10 | 15d | -1.33% | 0.3000 | 1.0000 | N |
| routing_energy_commodities/long_duration_growth/high_vix_5d | 10 | 5d | 0.11% | 0.6000 | 0.0000 | Y |
| routing_energy_commodities/long_duration_growth/high_vix_10d | 10 | 10d | 0.67% | 0.6000 | 0.0000 | Y |
| routing_energy_commodities/long_duration_growth/high_vix_15d | 10 | 15d | 0.46% | 0.6000 | 0.0000 | Y |
| routing_long_duration_growth/ai_compute/high_vix_5d | 10 | 5d | 0.62% | 0.6000 | 0.0000 | Y |
| routing_long_duration_growth/ai_compute/high_vix_10d | 10 | 10d | -0.14% | 0.7000 | 1.0000 | N |
| routing_long_duration_growth/ai_compute/high_vix_15d | 10 | 15d | -0.04% | 0.6000 | 1.0000 | N |
| routing_long_duration_growth/software/high_vix_5d | 10 | 5d | 0.09% | 0.5000 | 0.0000 | Y |
| routing_long_duration_growth/software/high_vix_10d | 10 | 10d | 0.03% | 0.5000 | 0.0000 | Y |
| routing_long_duration_growth/software/high_vix_15d | 10 | 15d | 0.19% | 0.6000 | 0.0000 | Y |
| routing_long_duration_growth/healthcare_defensive/high_vix_5d | 10 | 5d | 0.45% | 0.4000 | 0.0000 | Y |
| routing_long_duration_growth/healthcare_defensive/high_vix_10d | 10 | 10d | 0.38% | 0.6000 | 0.0000 | Y |
| routing_long_duration_growth/healthcare_defensive/high_vix_15d | 10 | 15d | 0.48% | 0.7000 | 0.0000 | Y |
| routing_long_duration_growth/consumer_staples_defensive/high_vix_5d | 10 | 5d | -1.20% | 0.0000 | 1.0000 | N |
| routing_long_duration_growth/consumer_staples_defensive/high_vix_10d | 10 | 10d | -0.27% | 0.5000 | 1.0000 | N |
| routing_long_duration_growth/consumer_staples_defensive/high_vix_15d | 10 | 15d | 0.03% | 0.6000 | 0.0000 | Y |
| routing_long_duration_growth/energy_commodities/high_vix_5d | 10 | 5d | 0.17% | 0.5000 | 0.0000 | Y |
| routing_long_duration_growth/energy_commodities/high_vix_10d | 10 | 10d | -0.42% | 0.2000 | 1.0000 | N |
| routing_long_duration_growth/energy_commodities/high_vix_15d | 10 | 15d | -0.22% | 0.3000 | 1.0000 | N |
| routing_long_duration_growth/financials_rates/high_vix_5d | 10 | 5d | -0.02% | 0.6000 | 1.0000 | N |
| routing_long_duration_growth/financials_rates/high_vix_10d | 10 | 10d | 0.43% | 0.7000 | 0.0000 | Y |
| routing_long_duration_growth/financials_rates/high_vix_15d | 10 | 15d | 0.27% | 0.6000 | 0.0000 | Y |

---

*Trial ledger: p3_trial_ledger.json (gitignored) — 109 trials enumerated before p-computation.*
*Runtime: 114.71s*
