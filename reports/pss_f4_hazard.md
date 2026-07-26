# PSS-F4H — frozen causal hazard-score ablation

Exploratory shadow evidence only. Two shallow boosted-tree hazards were fit on DEV 2020H2–2022: P(within 5% of the ±31td low) and P(avoids MAE≤−10%). Their geometric mean is gated at the frozen DEV top-20% threshold. No candidate changes its threshold after 2022.

The four-way comparison is the point: F4-only, orthogonal-only, combined, and a matched-coverage trailing-low-distance placebo. A combined model must beat both ablations out of time for F4 to earn an incremental role.

Training events: 10,749; features: 3 F4 + 15 orthogonal; target coverage: 20%.

## Discrimination and realized coverage

| era | model | near-low AUC | tail-safety AUC | realized coverage |
|---|---|---:|---:|---:|
| DEV 2020H2–2022 | F4-only hazard | 0.704 | 0.579 | 20.0% |
| DEV 2020H2–2022 | orthogonal hazard | 0.885 | 0.688 | 20.0% |
| DEV 2020H2–2022 | combined F4 + orthogonal hazard | 0.887 | 0.693 | 20.0% |
| VAL 2023–2024 | F4-only hazard | 0.678 | 0.511 | 21.2% |
| VAL 2023–2024 | orthogonal hazard | 0.838 | 0.566 | 26.1% |
| VAL 2023–2024 | combined F4 + orthogonal hazard | 0.840 | 0.577 | 26.2% |
| FWD 2025+ | F4-only hazard | 0.698 | 0.520 | 20.4% |
| FWD 2025+ | orthogonal hazard | 0.863 | 0.588 | 21.1% |
| FWD 2025+ | combined F4 + orthogonal hazard | 0.862 | 0.581 | 20.9% |

## DEV 2020H2–2022

| gate | events | names | ≥3 names | MAE | W5 | called | tail≤−10 | median tdt |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| incumbent | 10,749 | 1,300 | 1,261 | -8.92% | 17.5% | 6.4% | 45.1% | -2.0td |
| matched price-distance gate | 2,150 | 872 | 339 | -7.48% | 50.6% | 15.5% | 38.3% | +10.0td |
| F4-only hazard | 2,150 | 935 | 341 | -8.30% | 33.3% | 12.1% | 42.0% | +7.0td |
| orthogonal hazard | 2,150 | 817 | 335 | -6.10% | 55.6% | 12.8% | 30.2% | +6.0td |
| combined F4 + orthogonal hazard | 2,150 | 819 | 330 | -6.01% | 56.3% | 12.2% | 29.7% | +6.0td |

### Paired improvement vs incumbent (95% month-cluster CI)

| gate | ΔMAE | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |
|---|---:|---:|---:|---:|---:|
| matched price-distance gate | [-0.92, +0.90] | [+19.86, +28.90] | [+4.27, +8.84] | [-1.91, +7.13] | [+3.84, +7.66] |
| F4-only hazard | [-0.85, +0.70] | [+10.42, +15.02] | [+1.93, +5.26] | [-0.65, +6.08] | [+1.88, +5.10] |
| orthogonal hazard | [+0.00, +1.79] | [+22.43, +31.69] | [+2.79, +6.27] | [+3.34, +11.71] | [+1.93, +5.63] |
| combined F4 + orthogonal hazard | [-0.01, +1.94] | [+23.60, +32.17] | [+2.32, +6.15] | [+3.42, +12.33] | [+1.61, +5.73] |

## VAL 2023–2024

| gate | events | names | ≥3 names | MAE | W5 | called | tail≤−10 | median tdt |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| incumbent | 8,648 | 1,293 | 1,150 | -7.36% | 18.5% | 7.4% | 37.8% | -1.0td |
| matched price-distance gate | 2,148 | 882 | 320 | -7.43% | 47.2% | 15.9% | 38.2% | +13.2td |
| F4-only hazard | 1,834 | 875 | 270 | -7.77% | 33.0% | 12.7% | 38.1% | +9.0td |
| orthogonal hazard | 2,259 | 878 | 361 | -7.24% | 46.5% | 12.3% | 37.8% | +11.8td |
| combined F4 + orthogonal hazard | 2,268 | 876 | 355 | -7.25% | 46.9% | 12.2% | 37.6% | +11.0td |

### Paired improvement vs incumbent (95% month-cluster CI)

| gate | ΔMAE | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |
|---|---:|---:|---:|---:|---:|
| matched price-distance gate | [-1.58, +0.11] | [+14.67, +23.77] | [+3.65, +7.98] | [-5.38, +2.88] | [+3.46, +8.64] |
| F4-only hazard | [-1.42, +0.38] | [+7.03, +13.65] | [+0.61, +5.46] | [-3.88, +3.34] | [+1.12, +5.42] |
| orthogonal hazard | [-1.75, +0.08] | [+15.01, +22.98] | [+1.14, +4.99] | [-6.31, +1.73] | [+2.89, +8.03] |
| combined F4 + orthogonal hazard | [-1.59, +0.01] | [+15.40, +23.41] | [+0.89, +5.20] | [-5.59, +0.98] | [+3.27, +7.76] |

## FWD 2025+

| gate | events | names | ≥3 names | MAE | W5 | called | tail≤−10 | median tdt |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| incumbent | 5,946 | 1,290 | 1,054 | -7.84% | 20.1% | 7.4% | 40.8% | -3.0td |
| matched price-distance gate | 1,331 | 721 | 151 | -6.79% | 55.3% | 19.3% | 38.7% | +8.0td |
| F4-only hazard | 1,213 | 741 | 111 | -7.91% | 35.4% | 16.0% | 41.0% | +5.0td |
| orthogonal hazard | 1,253 | 658 | 157 | -6.65% | 54.7% | 12.0% | 36.6% | +6.5td |
| combined F4 + orthogonal hazard | 1,243 | 651 | 152 | -6.80% | 54.9% | 13.1% | 36.9% | +7.0td |

### Paired improvement vs incumbent (95% month-cluster CI)

| gate | ΔMAE | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |
|---|---:|---:|---:|---:|---:|
| matched price-distance gate | [-1.85, +2.63] | [+13.78, +28.13] | [+4.40, +10.08] | [-4.65, +9.89] | [+0.87, +6.20] |
| F4-only hazard | [-1.68, +2.13] | [+4.08, +14.17] | [+2.45, +8.03] | [-4.38, +7.69] | [-0.04, +4.28] |
| orthogonal hazard | [-1.97, +2.34] | [+12.89, +24.90] | [-0.01, +3.52] | [-5.74, +10.30] | [+0.70, +5.34] |
| combined F4 + orthogonal hazard | [-2.04, +1.35] | [+11.23, +25.95] | [+0.44, +4.59] | [-5.03, +7.32] | [+1.01, +5.14] |

## Incremental F4 ablation: combined − orthogonal

| era | ΔMAE | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |
|---|---:|---:|---:|---:|---:|
| DEV 2020H2–2022 | [-0.01, +0.10] | [+0.00, +1.15] | [+0.00, +0.00] | [+0.00, +0.23] | [-0.25, +0.07] |
| VAL 2023–2024 | [-0.05, +0.02] | [-0.02, +0.03] | [+0.00, +0.00] | [+0.00, +0.00] | [-0.17, +0.00] |
| FWD 2025+ | [-0.07, +0.03] | [-0.12, +0.00] | [+0.00, +0.00] | [-0.45, +0.00] | [-0.03, +0.24] |

## Two-stage composition: frozen watch → observable rejection action

The direct hazard gate is a locator. This composition waits up to 15 trading days for the first fresh-20d-low rejection after a selected watch, then stamps the actual rejection day. It tests whether separating location from timing repairs the early-signal trade-off.

### DEV 2020H2–2022

| action | events | names | ≥3 names | MAE | W5 | called | tail≤−10 | median tdt | delay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| price watch → rejection action | 1,010 | 643 | 83 | -8.14% | 43.0% | 32.7% | 40.5% | +10.5td | 5.0td |
| F4-hazard watch → rejection action | 833 | 583 | 47 | -8.57% | 43.2% | 33.7% | 42.1% | +8.5td | 5.5td |
| orthogonal-hazard watch → rejection action | 810 | 524 | 61 | -6.48% | 48.1% | 32.4% | 31.8% | +9.0td | 5.0td |
| combined-hazard watch → rejection action | 801 | 518 | 64 | -6.68% | 48.1% | 32.3% | 32.0% | +9.0td | 6.0td |

| action | ΔMAE vs incumbent | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |
|---|---:|---:|---:|---:|---:|
| price watch → rejection action | [-1.39, +1.33] | [+14.30, +25.69] | [+19.09, +28.62] | [-3.32, +10.01] | [+3.96, +8.98] |
| F4-hazard watch → rejection action | [-1.11, +1.70] | [+17.18, +29.13] | [+20.43, +29.92] | [-1.55, +11.83] | [+2.78, +8.09] |
| orthogonal-hazard watch → rejection action | [-0.20, +1.86] | [+17.82, +26.69] | [+20.98, +27.06] | [+2.03, +13.07] | [+2.97, +8.21] |
| combined-hazard watch → rejection action | [-0.30, +1.85] | [+18.74, +26.92] | [+20.57, +28.13] | [+1.57, +14.10] | [+3.48, +8.72] |

### VAL 2023–2024

| action | events | names | ≥3 names | MAE | W5 | called | tail≤−10 | median tdt | delay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| price watch → rejection action | 958 | 569 | 101 | -7.16% | 44.9% | 35.0% | 36.3% | +11.0td | 5.0td |
| F4-hazard watch → rejection action | 688 | 483 | 41 | -6.74% | 45.5% | 34.4% | 37.8% | +11.0td | 5.5td |
| orthogonal-hazard watch → rejection action | 902 | 552 | 86 | -6.91% | 45.1% | 34.1% | 35.4% | +10.8td | 6.0td |
| combined-hazard watch → rejection action | 902 | 548 | 88 | -6.85% | 45.0% | 33.6% | 35.2% | +11.0td | 6.0td |

| action | ΔMAE vs incumbent | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |
|---|---:|---:|---:|---:|---:|
| price watch → rejection action | [-0.96, +1.33] | [+15.03, +25.86] | [+18.71, +30.23] | [-1.69, +7.64] | [+1.10, +7.08] |
| F4-hazard watch → rejection action | [-0.80, +1.65] | [+18.29, +29.84] | [+18.72, +30.31] | [-0.94, +9.06] | [+0.80, +5.83] |
| orthogonal-hazard watch → rejection action | [-0.70, +1.45] | [+15.87, +25.71] | [+19.48, +29.39] | [-2.24, +6.84] | [+1.07, +7.74] |
| combined-hazard watch → rejection action | [-0.69, +1.33] | [+15.96, +26.19] | [+18.75, +29.20] | [-2.02, +7.32] | [+1.06, +7.33] |

### FWD 2025+

| action | events | names | ≥3 names | MAE | W5 | called | tail≤−10 | median tdt | delay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| price watch → rejection action | 554 | 400 | 29 | -9.47% | 42.2% | 35.8% | 45.8% | +10.0td | 5.0td |
| F4-hazard watch → rejection action | 463 | 371 | 12 | -8.97% | 40.0% | 40.5% | 45.1% | +7.0td | 6.0td |
| orthogonal-hazard watch → rejection action | 438 | 335 | 21 | -8.85% | 45.9% | 32.7% | 44.0% | +11.0td | 6.5td |
| combined-hazard watch → rejection action | 439 | 333 | 25 | -8.81% | 47.1% | 32.8% | 43.3% | +11.0td | 6.0td |

| action | ΔMAE vs incumbent | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |
|---|---:|---:|---:|---:|---:|
| price watch → rejection action | [-2.73, +1.86] | [+8.48, +21.34] | [+16.75, +30.11] | [-9.24, +7.25] | [+0.74, +7.24] |
| F4-hazard watch → rejection action | [-2.35, +3.10] | [+10.00, +21.98] | [+19.61, +36.60] | [-5.71, +9.99] | [+0.02, +6.54] |
| orthogonal-hazard watch → rejection action | [-2.45, +2.13] | [+9.76, +22.44] | [+13.45, +30.64] | [-8.68, +8.36] | [+1.24, +7.26] |
| combined-hazard watch → rejection action | [-2.57, +1.92] | [+9.91, +23.74] | [+13.97, +28.37] | [-8.38, +10.42] | [+0.92, +7.41] |

## Decision law

The combined hazard is robust enough for prospective shadowing only if it preserves positive near-low and tail-safety discrimination in both post-DEV eras, has CI-clean paired MAE/tail improvement, beats the matched price gate, and the combined-minus-orthogonal ablation is positive. Otherwise the hazard layer may still be useful, but F4 has not earned an incremental gate role.

## What was found

- Orthogonal near-low discrimination survives the frozen time split (AUC 0.838 in 2023–24 and 0.863 in 2025+), but tail-safety discrimination is weak.
- Direct orthogonal-gate W5 rises to 46.5% / 54.7% post-DEV, while paired MAE and tail CIs still include harm.
- Watch→rejection composition raises called-window rates to roughly 33%, but does not stabilize MAE/tail out of time.
- F4-only is weaker than the orthogonal model, and combined-minus-orthogonal ablations are effectively zero. Disposition: retain the orthogonal score as a prospective shadow locator; do not promote F4.

## Limitations

- Available history was already inspected, so 2023+ is a frozen out-of-training comparison, not an untouched confirmatory holdout.
- Current-listed-name/current-sector membership creates survivor bias.
- The fitted model is intentionally shallow and coverage-fixed; no per-name model or post-2022 threshold selection is allowed.
