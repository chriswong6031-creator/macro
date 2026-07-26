# PSS-F4R — causal terminality repair

Exploratory shadow study. This does **not** reverse the standalone F4 kill and does not promote authority: all available history was already visible before this repair wave. The engineering question is whether a causal multi-stage architecture can improve timing robustness without backdating persistence.

## Fixed architecture

1. The incumbent Stoch-RSI signal at the structure-derived rung arms a 15-trading-day watch.
2. Price timing is an observable rejection of a fresh 20-day intraday low (bullish rejection bar or next-day reclaim).
3. Soft terminality requires price within 5% of its trailing 60-day close low, ROC20 off its prior 20-day worst, and the rolling-low slope flattening.
4. Orthogonal blocks are recent range/volume climax or down-volume-share reversal; stock-vs-sector relative-strength repair; and simultaneous SPY/sector-ETF repair.
5. R4 requires at least two of those three orthogonal blocks. The F4 variant additionally restricts the original watch to a causal high-asymmetry stress state. Actions are stamped only on the confirmation day.
6. R5–R8 add a survival clock: a rejection must remain the low for three or five completed sessions and price must stand above the rejection close. R8 then requires at least one orthogonal confirmation. This is causal post-rejection evidence, never a backdated label.
7. R9–R11 add a break-of-structure clock: after a rejection in the prior 10 sessions, close must exceed the prior five-day high. R10 retains recent terminality and R11 also requires an orthogonal confirmation.

Ruler: per-name-first MAE63, within-5%-of-±31td-low (W5), called window (−2..+5td), MAE≤−10% tail rate, and td-to-trough. Positive paired deltas mean improvement; for tail rate the sign is inverted so positive is also better. Inference uses signal-month clustered bootstrap.

Universe/event census: 1300 names; 25,343 incumbent events; 2020-07-06 through 2026-04-23.

## DEV 2020H2–2022

| construction | events | names | ≥3 names | MAE | W5 | called | tail≤−10 | median tdt | delay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| incumbent | 10,749 | 1,300 | 1,261 | -8.92% | 17.5% | 6.4% | 45.1% | -2.0td | 0.0td |
| R0 price rejection | 2,938 | 1,108 | 501 | -8.96% | 38.3% | 32.0% | 44.1% | +9.0td | 7.0td |
| R1 + soft terminality | 1,549 | 870 | 170 | -9.22% | 39.3% | 33.7% | 46.2% | +10.0td | 9.5td |
| R2 + volume exhaustion | 1,205 | 757 | 107 | -9.46% | 36.9% | 33.8% | 47.4% | +10.0td | 10.0td |
| R3 + relative/systemic repair | 208 | 192 | 1 | -12.79% | 26.0% | 33.3% | 59.1% | +7.0td | 10.0td |
| R4 orthogonal 2-of-3 consensus | 926 | 652 | 57 | -10.00% | 34.4% | 33.8% | 50.6% | +10.0td | 9.5td |
| R4 + F4-stress arm | 658 | 502 | 31 | -10.31% | 37.0% | 34.1% | 51.4% | +10.0td | 10.0td |
| R5 3-day rejection survival | 2,131 | 947 | 318 | -9.17% | 20.4% | 7.7% | 46.5% | +4.0td | 3.0td |
| R6 + terminality, 3-day survival | 919 | 629 | 69 | -8.93% | 23.4% | 6.4% | 46.8% | +4.0td | 6.0td |
| R7 + terminality, 5-day survival | 1,027 | 699 | 64 | -9.35% | 16.9% | 4.3% | 46.8% | -4.0td | 3.0td |
| R8 survival + orthogonal confirmation | 909 | 623 | 68 | -8.99% | 22.8% | 6.4% | 47.0% | +4.0td | 6.0td |
| R8 + F4-stress arm | 636 | 483 | 26 | -8.93% | 24.8% | 7.0% | 46.3% | +6.0td | 7.0td |
| R9 rejection → 5-day structure break | 3,553 | 1,108 | 618 | -9.65% | 8.7% | 7.9% | 47.7% | -2.0td | 2.0td |
| R10 + terminality structure break | 1,758 | 909 | 242 | -10.18% | 9.2% | 8.1% | 48.7% | -1.0td | 3.0td |
| R11 structure break + orthogonal confirmation | 1,747 | 905 | 240 | -10.19% | 9.0% | 8.1% | 48.9% | -1.0td | 3.0td |
| R11 + F4-stress arm | 1,168 | 725 | 108 | -10.77% | 10.0% | 9.5% | 50.6% | +1.5td | 4.0td |

### Paired improvement vs incumbent (95% month-cluster CI)

| construction | ΔMAE | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |
|---|---:|---:|---:|---:|---:|
| R0 price rejection | [-0.85, +1.75] | [+14.34, +26.11] | [+20.72, +28.79] | [-2.03, +9.49] | [+3.90, +8.31] |
| R1 + soft terminality | [-0.82, +2.36] | [+17.91, +30.97] | [+22.45, +33.12] | [-2.93, +10.89] | [+2.90, +8.25] |
| R2 + volume exhaustion | [-1.36, +2.56] | [+15.41, +28.41] | [+21.42, +33.48] | [-4.66, +11.84] | [+2.84, +8.43] |
| R3 + relative/systemic repair | [-4.14, +0.64] | [+0.94, +16.49] | [+19.99, +33.82] | [-15.91, +4.45] | [+0.23, +7.82] |
| R4 orthogonal 2-of-3 consensus | [-1.92, +1.79] | [+12.44, +25.11] | [+22.03, +32.50] | [-7.57, +8.01] | [+2.51, +8.11] |
| R4 + F4-stress arm | [-2.01, +2.40] | [+13.98, +27.59] | [+22.08, +33.10] | [-10.25, +10.64] | [+2.50, +8.36] |
| R5 3-day rejection survival | [-1.54, +0.45] | [-3.19, +2.76] | [-3.71, +0.08] | [-3.34, +3.15] | [+0.35, +4.33] |
| R6 + terminality, 3-day survival | [-1.81, +0.95] | [-0.28, +8.02] | [-5.48, -0.94] | [-5.53, +5.06] | [-0.26, +4.31] |
| R7 + terminality, 5-day survival | [-1.92, +0.69] | [-5.87, -0.27] | [-8.10, -3.35] | [-6.14, +4.92] | [-2.05, +2.36] |
| R8 survival + orthogonal confirmation | [-1.76, +0.90] | [-0.41, +7.76] | [-5.87, -0.79] | [-5.25, +5.20] | [-0.21, +4.14] |
| R8 + F4-stress arm | [-1.85, +1.18] | [-0.50, +8.33] | [-5.17, +0.31] | [-6.43, +6.17] | [+0.29, +5.03] |
| R9 rejection → 5-day structure break | [-1.62, -0.39] | [-13.24, -9.27] | [-2.20, +0.81] | [-5.24, +0.20] | [-0.98, +2.10] |
| R10 + terminality structure break | [-2.38, -0.19] | [-12.61, -8.18] | [-2.30, +2.38] | [-7.96, +0.70] | [-0.89, +3.36] |
| R11 structure break + orthogonal confirmation | [-2.28, -0.16] | [-12.85, -8.19] | [-2.20, +2.10] | [-7.75, +1.10] | [-1.08, +3.48] |
| R11 + F4-stress arm | [-2.67, -0.27] | [-13.98, -8.20] | [-1.58, +3.45] | [-10.17, -0.70] | [-0.55, +4.14] |

## VAL 2023–2024

| construction | events | names | ≥3 names | MAE | W5 | called | tail≤−10 | median tdt | delay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| incumbent | 8,648 | 1,293 | 1,150 | -7.36% | 18.5% | 7.4% | 37.8% | -1.0td | 0.0td |
| R0 price rejection | 2,344 | 966 | 353 | -7.34% | 42.1% | 33.0% | 38.1% | +10.0td | 7.0td |
| R1 + soft terminality | 1,358 | 789 | 137 | -7.63% | 40.4% | 32.5% | 39.9% | +11.0td | 9.0td |
| R2 + volume exhaustion | 1,088 | 705 | 85 | -7.58% | 41.3% | 34.2% | 39.2% | +10.0td | 9.0td |
| R3 + relative/systemic repair | 168 | 156 | 0 | -8.25% | 22.8% | 34.0% | 41.3% | +8.0td | 8.0td |
| R4 orthogonal 2-of-3 consensus | 850 | 584 | 58 | -7.96% | 35.5% | 33.3% | 38.5% | +10.0td | 9.0td |
| R4 + F4-stress arm | 620 | 455 | 33 | -7.59% | 37.4% | 33.6% | 36.4% | +11.0td | 9.0td |
| R5 3-day rejection survival | 1,807 | 855 | 260 | -7.31% | 22.0% | 5.4% | 37.3% | +2.5td | 2.0td |
| R6 + terminality, 3-day survival | 892 | 608 | 58 | -7.64% | 22.7% | 4.5% | 38.9% | +3.0td | 4.0td |
| R7 + terminality, 5-day survival | 902 | 610 | 59 | -7.71% | 17.5% | 3.2% | 38.1% | +3.0td | 3.0td |
| R8 survival + orthogonal confirmation | 885 | 606 | 57 | -7.64% | 22.4% | 4.6% | 39.1% | +3.0td | 4.0td |
| R8 + F4-stress arm | 610 | 459 | 25 | -7.64% | 24.3% | 6.3% | 39.9% | +3.5td | 5.0td |
| R9 rejection → 5-day structure break | 2,985 | 1,023 | 512 | -7.32% | 11.5% | 9.6% | 37.8% | -2.0td | 1.5td |
| R10 + terminality structure break | 1,558 | 821 | 189 | -7.30% | 12.0% | 11.1% | 37.0% | -1.5td | 2.5td |
| R11 structure break + orthogonal confirmation | 1,548 | 816 | 188 | -7.28% | 12.0% | 11.1% | 37.0% | -1.2td | 2.5td |
| R11 + F4-stress arm | 1,062 | 659 | 95 | -7.43% | 14.4% | 12.1% | 36.4% | -1.0td | 3.5td |

### Paired improvement vs incumbent (95% month-cluster CI)

| construction | ΔMAE | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |
|---|---:|---:|---:|---:|---:|
| R0 price rejection | [-0.34, +1.57] | [+18.47, +27.71] | [+19.90, +29.19] | [-0.28, +7.84] | [+1.65, +6.36] |
| R1 + soft terminality | [-0.52, +2.07] | [+17.50, +29.53] | [+19.29, +30.02] | [-2.06, +8.54] | [+0.76, +6.16] |
| R2 + volume exhaustion | [-0.39, +2.34] | [+18.23, +27.99] | [+20.44, +30.70] | [-0.37, +10.07] | [+0.07, +6.66] |
| R3 + relative/systemic repair | [-1.48, +2.15] | [-1.61, +12.36] | [+19.77, +31.00] | [-2.28, +10.52] | [-1.75, +6.07] |
| R4 orthogonal 2-of-3 consensus | [-0.54, +1.99] | [+12.24, +23.10] | [+19.52, +29.51] | [+0.14, +10.25] | [+0.18, +6.34] |
| R4 + F4-stress arm | [-0.54, +2.34] | [+12.59, +25.90] | [+19.27, +31.33] | [+0.29, +12.79] | [-0.04, +5.72] |
| R5 3-day rejection survival | [-0.44, +1.06] | [-2.51, +3.60] | [-7.78, -3.96] | [-0.37, +5.53] | [-2.09, +2.13] |
| R6 + terminality, 3-day survival | [-0.55, +1.63] | [-1.94, +5.91] | [-9.55, -3.91] | [-1.40, +6.74] | [-2.61, +2.98] |
| R7 + terminality, 5-day survival | [-1.12, +1.23] | [-6.76, -0.35] | [-10.21, -5.72] | [-2.40, +6.73] | [-3.52, +1.74] |
| R8 survival + orthogonal confirmation | [-0.50, +1.67] | [-2.38, +6.08] | [-9.51, -3.24] | [-2.10, +7.24] | [-2.80, +2.39] |
| R8 + F4-stress arm | [-0.41, +1.78] | [-1.94, +7.89] | [-8.99, -0.82] | [-2.52, +7.43] | [-3.09, +2.06] |
| R9 rejection → 5-day structure break | [-1.05, +0.29] | [-12.57, -7.10] | [-1.82, +1.23] | [-2.03, +3.63] | [-2.70, +0.16] |
| R10 + terminality structure break | [-1.08, +0.96] | [-12.31, -6.43] | [-0.48, +3.06] | [-1.29, +6.78] | [-3.57, +0.50] |
| R11 structure break + orthogonal confirmation | [-1.04, +0.85] | [-12.52, -6.13] | [-0.57, +3.31] | [-1.28, +6.46] | [-3.29, +0.42] |
| R11 + F4-stress arm | [-0.89, +1.34] | [-11.32, -4.36] | [+0.02, +4.24] | [-1.84, +7.53] | [-3.63, +0.97] |

## FWD 2025+

| construction | events | names | ≥3 names | MAE | W5 | called | tail≤−10 | median tdt | delay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| incumbent | 5,946 | 1,290 | 1,054 | -7.84% | 20.1% | 7.4% | 40.8% | -3.0td | 0.0td |
| R0 price rejection | 1,410 | 800 | 149 | -9.48% | 35.9% | 35.9% | 46.8% | +8.0td | 7.0td |
| R1 + soft terminality | 754 | 552 | 33 | -9.25% | 36.1% | 38.3% | 44.0% | +8.0td | 9.2td |
| R2 + volume exhaustion | 638 | 485 | 22 | -8.46% | 37.0% | 40.6% | 42.8% | +7.5td | 10.0td |
| R3 + relative/systemic repair | 55 | 54 | 0 | -13.59% | 6.5% | 27.8% | 55.6% | +11.5td | 10.0td |
| R4 orthogonal 2-of-3 consensus | 426 | 351 | 8 | -8.93% | 28.2% | 39.5% | 44.5% | +6.0td | 10.0td |
| R4 + F4-stress arm | 320 | 271 | 2 | -8.46% | 31.9% | 44.1% | 42.7% | +5.0td | 10.0td |
| R5 3-day rejection survival | 1,199 | 739 | 107 | -10.92% | 17.9% | 6.4% | 50.9% | +0.0td | 2.0td |
| R6 + terminality, 3-day survival | 485 | 395 | 11 | -8.76% | 19.6% | 9.5% | 44.9% | -1.0td | 5.5td |
| R7 + terminality, 5-day survival | 499 | 417 | 8 | -7.83% | 19.8% | 5.5% | 41.6% | -4.0td | 3.0td |
| R8 survival + orthogonal confirmation | 482 | 393 | 10 | -8.80% | 19.7% | 9.5% | 44.9% | -1.0td | 5.5td |
| R8 + F4-stress arm | 357 | 307 | 4 | -7.76% | 23.1% | 11.2% | 43.3% | -0.5td | 6.5td |
| R9 rejection → 5-day structure break | 1,876 | 921 | 260 | -10.25% | 9.1% | 5.2% | 50.1% | -2.0td | 2.0td |
| R10 + terminality structure break | 794 | 584 | 31 | -8.85% | 10.4% | 7.3% | 44.2% | -3.0td | 2.0td |
| R11 structure break + orthogonal confirmation | 780 | 580 | 30 | -8.88% | 10.6% | 7.2% | 44.4% | -3.0td | 2.0td |
| R11 + F4-stress arm | 547 | 446 | 7 | -8.53% | 11.9% | 7.6% | 43.4% | -3.0td | 3.0td |

### Paired improvement vs incumbent (95% month-cluster CI)

| construction | ΔMAE | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |
|---|---:|---:|---:|---:|---:|
| R0 price rejection | [-2.45, +2.23] | [+8.63, +21.90] | [+16.61, +33.52] | [-5.90, +8.99] | [+0.64, +6.92] |
| R1 + soft terminality | [-1.84, +3.59] | [+9.73, +23.45] | [+16.20, +40.63] | [-2.26, +15.16] | [-0.59, +5.55] |
| R2 + volume exhaustion | [-1.82, +4.49] | [+7.55, +24.56] | [+16.36, +42.94] | [-2.83, +16.69] | [-1.13, +5.38] |
| R3 + relative/systemic repair | [-4.30, +2.74] | [-12.92, +0.43] | [+10.85, +29.61] | [-11.03, +14.91] | [-0.48, +8.49] |
| R4 orthogonal 2-of-3 consensus | [-2.05, +4.79] | [+3.73, +16.39] | [+16.02, +39.78] | [-3.15, +18.69] | [-2.46, +4.45] |
| R4 + F4-stress arm | [-2.26, +4.27] | [+3.19, +18.43] | [+18.96, +44.90] | [-3.74, +18.77] | [-2.64, +4.48] |
| R5 3-day rejection survival | [-4.37, +0.49] | [-9.87, -1.11] | [-7.28, -1.33] | [-13.06, +3.28] | [-1.57, +4.25] |
| R6 + terminality, 3-day survival | [-2.58, +2.60] | [-8.47, +2.89] | [-6.63, +5.08] | [-6.02, +10.68] | [-4.00, +1.96] |
| R7 + terminality, 5-day survival | [-2.18, +2.46] | [-8.29, +0.84] | [-8.99, -1.83] | [-3.01, +12.59] | [-4.70, +0.50] |
| R8 survival + orthogonal confirmation | [-2.19, +2.45] | [-8.09, +3.29] | [-6.92, +5.30] | [-5.05, +10.64] | [-4.07, +1.58] |
| R8 + F4-stress arm | [-2.63, +2.91] | [-8.68, +5.33] | [-6.69, +7.81] | [-5.99, +11.78] | [-3.54, +2.92] |
| R9 rejection → 5-day structure break | [-3.67, -0.17] | [-16.89, -9.85] | [-6.59, -2.78] | [-11.66, +0.18] | [-2.06, +2.19] |
| R10 + terminality structure break | [-2.29, +1.85] | [-14.17, -8.02] | [-5.43, -0.04] | [-4.53, +7.78] | [-4.20, -0.06] |
| R11 structure break + orthogonal confirmation | [-2.20, +1.57] | [-14.19, -7.60] | [-5.18, -0.22] | [-4.82, +7.23] | [-4.07, +0.07] |
| R11 + F4-stress arm | [-2.42, +2.22] | [-15.52, -6.81] | [-6.74, +0.65] | [-4.18, +9.71] | [-4.73, +0.21] |

## F4 incremental ablation

Each +F4 pair shares its confirmation rule with the non-F4 row; only the watch arm differs. This isolates whether requiring high downside-asymmetry stress improves an already-qualified action.

| pair | era | +F4 − no-F4 ΔMAE | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |
|---|---|---:|---:|---:|---:|---:|
| R4 orthogonal 2-of-3 consensus | DEV 2020H2–2022 | [-0.13, +0.03] | [+0.00, +0.00] | [-0.83, +0.00] | [+0.00, +0.00] | [+0.00, +0.27] |
| R4 orthogonal 2-of-3 consensus | VAL 2023–2024 | [-0.18, +0.11] | [+0.00, +0.00] | [+0.00, +0.00] | [+0.00, +0.00] | [-0.16, +0.12] |
| R4 orthogonal 2-of-3 consensus | FWD 2025+ | [+0.00, +0.00] | [+0.00, +0.00] | [+0.00, +0.00] | [+0.00, +0.00] | [+0.00, +0.00] |
| R8 survival + orthogonal confirmation | DEV 2020H2–2022 | [-0.15, +0.11] | [+0.00, +0.00] | [+0.00, +0.00] | [-0.74, +0.30] | [-0.03, +0.45] |
| R8 survival + orthogonal confirmation | VAL 2023–2024 | [-0.22, +0.02] | [+0.00, +0.00] | [+0.00, +0.00] | [-1.12, +0.00] | [+0.00, +0.59] |
| R8 survival + orthogonal confirmation | FWD 2025+ | [-0.05, +0.00] | [+0.00, +0.00] | [+0.00, +0.00] | [+0.00, +0.00] | [+0.00, +0.00] |
| R11 structure break + orthogonal confirmation | DEV 2020H2–2022 | [-0.18, +0.31] | [+0.00, +0.00] | [+0.00, +0.45] | [-1.53, +1.20] | [-0.16, +0.75] |
| R11 structure break + orthogonal confirmation | VAL 2023–2024 | [-0.20, +0.16] | [+0.00, +0.00] | [+0.00, +0.47] | [-1.21, +0.68] | [+0.01, +1.07] |
| R11 structure break + orthogonal confirmation | FWD 2025+ | [-0.07, +0.14] | [+0.00, +0.00] | [+0.00, +0.00] | [+0.00, +0.00] | [-0.19, +0.06] |

## 2022 containment diagnostic

Raw counts are shown with monthly density because H1 spans six months while the September–November terminal-low window is approximately two.

| construction | H1 events | H1/month | terminal-window events | window/month | density ratio |
|---|---:|---:|---:|---:|---:|
| incumbent | 2,738 | 456.3 | 1,071 | 535.5 | 0.85 |
| R0 price rejection | 1,080 | 180.0 | 258 | 129.0 | 1.40 |
| R1 + soft terminality | 674 | 112.3 | 141 | 70.5 | 1.59 |
| R2 + volume exhaustion | 553 | 92.2 | 116 | 58.0 | 1.59 |
| R3 + relative/systemic repair | 96 | 16.0 | 13 | 6.5 | 2.46 |
| R4 orthogonal 2-of-3 consensus | 398 | 66.3 | 98 | 49.0 | 1.35 |
| R4 + F4-stress arm | 289 | 48.2 | 72 | 36.0 | 1.34 |
| R5 3-day rejection survival | 584 | 97.3 | 223 | 111.5 | 0.87 |
| R6 + terminality, 3-day survival | 293 | 48.8 | 114 | 57.0 | 0.86 |
| R7 + terminality, 5-day survival | 343 | 57.2 | 115 | 57.5 | 0.99 |
| R8 survival + orthogonal confirmation | 290 | 48.3 | 114 | 57.0 | 0.85 |
| R8 + F4-stress arm | 211 | 35.2 | 86 | 43.0 | 0.82 |
| R9 rejection → 5-day structure break | 1,069 | 178.2 | 372 | 186.0 | 0.96 |
| R10 + terminality structure break | 646 | 107.7 | 201 | 100.5 | 1.07 |
| R11 structure break + orthogonal confirmation | 644 | 107.3 | 199 | 99.5 | 1.08 |
| R11 + F4-stress arm | 447 | 74.5 | 135 | 67.5 | 1.10 |

## Promotion law

A construction is robust enough for further forward shadowing only if:

- the lower 95% bound is positive for paired MAE **and** MAE≤−10% tail improvement in both DEV and VAL;
- W5 or called-window timing improves without relying on a degenerate small sample;
- it beats its price-only, terminality-only, and F4-removal ablations;
- coverage spans at least 500 names with meaningful repeated events; and
- H1-2022 firing density is materially below the terminal-low window.

No result in this report is an untouched holdout. A passing exploratory construction must be frozen and verified prospectively.

## What was found

- Immediate rejection/terminality materially improves W5 and called-window timing, but its median action remains early and MAE/tail improvement is not stable.
- Three/five-day survival moves median tdt toward the trough and restores 2022 density discrimination, but does not improve forward risk.
- A five-day break of structure gives up W5 and often worsens MAE; it is confirmation after the useful entry window, not a repair.
- Requiring F4 stress does not improve any matched non-F4 construction. No hand-built candidate passes the promotion law.

## Limitations

- Current-listed-name and current-sector mappings introduce survivor and classification bias; the sector/market inputs are causal in time but the universe composition is not point-in-time.
- Yahoo-adjusted closes and local OHLCV are suitable for relative tests, not executable intraday fills.
- The fixed thresholds are mechanism choices, not optimized cutoffs. This reduces search freedom but does not turn inspected history into validation.
