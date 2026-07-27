# PSS-SR1 — stress-matched second-test elasticity

Frozen, causal challenge–response test. The construction and decision law were committed before final outcomes in `research/PSS_SR1_STRESS_ELASTICITY_PREREG.md`. Positive deltas below always mean SR1 is better than the disjoint geometry control.

SR1 remains display/shadow research. Historical qualification could only authorize a prospective frozen shadow; it cannot change entry, ranking, or sizing.

## Construction audit

- Anchor: fresh prior-60-close low, 21-session cooldown.
- Route: prior-126-session beta > 0, sector R² ≥ 0.35, prior sector 20-session return < 0.
- Pulse A: sector shock cluster begins within three sessions and stock downside elasticity ≥ 0.75.
- Pulse B: observed after a one-ATR rebound, begins within 15 sessions, and normalized stress is at least 80% of pulse A.
- Treatment: tested low holds within 0.5 frozen ATR and pulse-B elasticity is no more than half pulse A. Geometry control holds the same tested low but does not collapse elasticity.
- Action: pulse-B confirmation close, never its retrospective start.

## Coverage and outcomes

### DEV 2020H2–2022

| group | events | names | names ≥3 | sector pulses | MAE63 | W5 | called | tail≤−10 | rebound8 first | unresolved | delay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stress_path | 450 | 327 | 26 | 130 | -6.66% | +37.3% | +24.3% | +33.4% | +42.2% | +2.7% | +9.0td |
| geometry | 349 | 263 | 11 | 113 | -8.31% | +25.4% | +12.5% | +40.9% | +48.6% | +3.4% | +9.0td |
| geometry_control | 213 | 170 | 7 | 87 | -8.51% | +29.1% | +13.7% | +42.4% | +42.2% | +1.5% | +9.8td |
| sr1 | 136 | 124 | 0 | 71 | -7.11% | +18.1% | +9.3% | +38.3% | +56.5% | +5.6% | +9.0td |

#### SR1 minus geometry-control pulse effects

| metric | effect | 95% month-block CI | pulse-permutation p | informative pulses |
|---|---:|---:|---:|---:|
| mae | -1.15 | [-4.07, +0.84] | 0.8691 | 45 |
| tail10 | -2.35 | [-13.17, +8.11] | 0.6312 | 45 |
| w5 | -14.69 | [-29.42, +1.41] | 0.9775 | 45 |
| called | -10.81 | [-18.45, -3.03] | 0.9810 | 45 |
| rebound8_first | +10.61 | [-6.31, +25.07] | 0.0900 | 45 |

### VAL 2023–2024

| group | events | names | names ≥3 | sector pulses | MAE63 | W5 | called | tail≤−10 | rebound8 first | unresolved | delay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stress_path | 199 | 161 | 2 | 72 | -5.19% | +47.2% | +20.5% | +21.8% | +28.0% | +2.7% | +12.0td |
| geometry | 148 | 125 | 1 | 63 | -5.20% | +44.4% | +14.0% | +20.9% | +36.0% | +3.5% | +12.0td |
| geometry_control | 102 | 90 | 0 | 45 | -5.88% | +49.4% | +15.6% | +20.6% | +29.4% | +2.8% | +12.2td |
| sr1 | 46 | 43 | 0 | 31 | -3.17% | +32.6% | +10.5% | +23.3% | +50.0% | +5.8% | +12.0td |

#### SR1 minus geometry-control pulse effects

| metric | effect | 95% month-block CI | pulse-permutation p | informative pulses |
|---|---:|---:|---:|---:|
| mae | +0.73 | [-4.54, +6.39] | 0.4148 | 13 |
| tail10 | +1.10 | [-29.23, +31.60] | 0.4523 | 13 |
| w5 | -19.41 | [-36.58, -2.22] | 0.9850 | 13 |
| called | -14.07 | [-36.58, +4.33] | 0.9735 | 13 |
| rebound8_first | -2.41 | [-26.85, +17.68] | 0.5687 | 13 |

### FWD 2025+

| group | events | names | names ≥3 | sector pulses | MAE63 | W5 | called | tail≤−10 | rebound8 first | unresolved | delay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stress_path | 195 | 157 | 7 | 61 | -5.63% | +37.1% | +25.8% | +35.8% | +34.3% | +6.5% | +11.0td |
| geometry | 147 | 123 | 4 | 52 | -8.11% | +26.9% | +13.7% | +41.2% | +41.1% | +8.7% | +11.5td |
| geometry_control | 93 | 82 | 1 | 34 | -7.84% | +30.1% | +15.9% | +37.6% | +44.7% | +7.3% | +12.0td |
| sr1 | 54 | 51 | 0 | 31 | -8.35% | +20.6% | +9.8% | +47.1% | +39.2% | +9.8% | +11.0td |

#### SR1 minus geometry-control pulse effects

| metric | effect | 95% month-block CI | pulse-permutation p | informative pulses |
|---|---:|---:|---:|---:|
| mae | -1.02 | [-2.56, +1.00] | 0.7286 | 13 |
| tail10 | -1.92 | [-11.41, +11.81] | 0.5957 | 13 |
| w5 | -13.89 | [-45.14, +10.42] | 0.8796 | 13 |
| called | +2.67 | [-18.83, +25.64] | 0.4078 | 13 |
| rebound8_first | -4.91 | [-22.22, +14.35] | 0.6982 | 13 |

## Frozen decision law

| check | pass | evidence |
|---|:---:|---|
| DEV 2020H2–2022 mae positive lower CI and p≤.05 | NO | effect=-1.15, CI=[-4.07, +0.84], p=0.8691 |
| DEV 2020H2–2022 tail10 positive lower CI and p≤.05 | NO | effect=-2.35, CI=[-13.17, +8.11], p=0.6312 |
| DEV 2020H2–2022 timing and rebound-first improve | NO | W5=-14.69, called=-10.81, rebound8=+10.61 |
| VAL 2023–2024 mae positive lower CI and p≤.05 | NO | effect=+0.73, CI=[-4.54, +6.39], p=0.4148 |
| VAL 2023–2024 tail10 positive lower CI and p≤.05 | NO | effect=+1.10, CI=[-29.23, +31.60], p=0.4523 |
| VAL 2023–2024 timing and rebound-first improve | NO | W5=-19.41, called=-14.07, rebound8=-2.41 |
| Coverage: 500 names, 100 names≥3, 30 informative pulses/era | NO | names=200, names≥3=1, pulses={'DEV 2020H2–2022': 45, 'VAL 2023–2024': 13} |
| H1-2022 monthly density below Sep–Nov 2022 | NO | 13.83/month vs 11.33/month |
| No FWD primary sign reversal | NO | MAE=-1.02, tail=-1.92 |

**Verdict: KILLED**.

## 2022 containment and execution diagnostics

- H1-2022 monthly treatments: {'2022-01': 1, '2022-02': 9, '2022-03': 11, '2022-04': 0, '2022-05': 27, '2022-06': 35}.
- Sep–Nov 2022 monthly treatments: {'2022-09': 7, '2022-10': 17, '2022-11': 10}.
- Next-open gap median / 95th percentile: +0.04% / +2.06%.

## Exclusion and path census

- `eligible`: 799 names
- `missing_sector_map`: 501 names

Aggregate anchor/path counters:

- `anchors`: 13,431
- `sector_not_down`: 2,189
- `systemic_anchors`: 3,924
- `pulse_a_not_damaging`: 487
- `no_pulse_a`: 1,464
- `no_rebound_comparable_b`: 1,115
- `r2_below_min`: 7,296
- `stress_paths`: 844
- `geometry`: 644
- `geometry_controls`: 408
- `treatments`: 236
- `beta_nonpositive`: 22
- `incomplete_outcome`: 14

## Interpretation

At least one frozen requirement failed. This exact SR1 construction is not usable and must not be threshold-tuned after outcomes. Its mechanism-level evidence may inform a genuinely different preregistered family, but SR1 itself is blocklisted.

Inference draws: 2,000 within-pulse permutations (base seed 20260802); 1,000 month-block bootstraps (base seed 20260803).
