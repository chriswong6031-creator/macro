# Defensive-sector rotation → tech top + vol shock — Phase-0 verdict

**VERDICT: FALSIFIED / DISPLAY-ONLY — fails the pre-registered gate**

HYPOTHESIS (discretionary, tested adversarially): defensives (esp. XLU) are sold hardest when tech peaks hardest, so XLU technicals bottoming + turning up WHILE tech rolls over should LEAD an equity vol shock by days. The repo already found sector-flow rank-IC ≈ 0, so the bar is a real falsification gate, pre-registered before running.

Sample 1998-12-22 → 2026-06-18 (6914 trading days). TRAIN ≤ 2014-12-31 (tune+freeze), OOS ≥ 2015-01-01 (headline). Frozen trigger params: W=8 (bottom co-occurrence window), W2=2 (tech-top window), cooldown=10d. Triggers: 95 full / 39 OOS. Seed 20260623.

## Pre-registered falsification gate (evaluated OOS @ N=10)

| Check | Pass? |
|---|:--:|
| oos_ci_excludes_zero | ✗ |
| ratio_ge_1_30 | ✓ |
| false_alarm_ok | ✗ |
| lead_24_share_ok | ✗ |
| median_lead_ok | ✓ |
| vix_strat_survives | ✗ |

**OOS primary (N=10, VIX≥1.4× OR SPY mae≤−5%):** base 0.143 · cond 0.205 · **lift +0.062** (×1.44) · false-alarm 0.80 · n=39
- OOS block-bootstrap 95% CI on lift: [-0.0482, 0.1994] (median 0.0604, P(lift>0)=0.841, 2000 usable iters, block=21)
- OOS lead-time of hits: median 7.0 d, IQR [5.5, 8.25], 2–4d-lead share 0.25 (n_hit 8/39)

## Outcome grid — OOS (lift vs base over the whole outcome menu)

| Outcome | N=3 | N=5 | N=10 | N=21 |
|---|---|---|---|---|
| primary | -0.0028 | -0.0092 | 0.0624 | 0.1527 |
| vix_25 | -0.0341 | -0.0156 | 0.073 | 0.1742 |
| vix_40 | 0.002 | 0.0002 | 0.0379 | 0.1501 |
| vix_60 | -0.0083 | -0.0191 | -0.0193 | 0.0675 |
| vix_abs8 | -0.0181 | -0.0095 | -0.0084 | 0.0793 |
| spy_dd3 | -0.0518 | -0.0679 | -0.0019 | 0.0516 |
| qqq_dd3 | -0.0179 | -0.0552 | 0.0504 | 0.0713 |
| spy_dd5 | -0.0149 | -0.0313 | 0.0035 | 0.0543 |
| qqq_dd5 | -0.0247 | -0.0521 | 0.0215 | 0.0286 |
| spy_dd8 | -0.0042 | -0.0094 | -0.0251 | -0.018 |
| qqq_dd8 | -0.0052 | -0.0115 | -0.0182 | 0.0211 |

## Full-sample primary (more power; in+out of sample)
- base 0.134 · cond 0.168 · **lift +0.034** (×1.25) · false-alarm 0.83 · n=95
- full block-bootstrap 95% CI on lift: [-0.0303, 0.1093] (median 0.0335, P(lift>0)=0.831)
- full lead-time: median 7.0 d, IQR [4.0, 9.0], 2–4d share 0.312 (n_hit 16/95)

## Confounder controls
**(a) VIX-level** — raw lift 0.0624 vs VIX-stratified lift **0.0238**. Trigger mean VIX pctile 0.453 vs overall 0.409 (triggers fire in lower-VIX tape if the former is smaller — the mean-reversion confound).

| VIX pctile bucket | n | n_trig | within-bucket lift |
|---|--:|--:|--:|
| 0.0–0.15 | 1664 | 22 | 0.0092 |
| 0.15–0.35 | 1663 | 22 | 0.0712 |
| 0.35–0.65 | 1663 | 21 | 0.0486 |
| 0.65–1.0 | 1663 | 28 | -0.0337 |

**(b) Trend regime (put-state proxy = SPY vs 200dma)** — bull: base 0.109 · cond 0.129 · **lift +0.020** (×1.18) · false-alarm 0.87 · n=62; bear: base 0.199 · cond 0.242 · **lift +0.044** (×1.22) · false-alarm 0.76 · n=33.
**(c) XLU-only vs defensive basket** — XLU-only: base 0.134 · cond 0.168 · **lift +0.034** (×1.25) · false-alarm 0.83 · n=95; XLU+XLP+XLV: base 0.134 · cond 0.140 · **lift +0.005** (×1.04) · false-alarm 0.86 · n=93.
**(d) Rates control (TLT 10d)** — rates-driven (TLT↑): base 0.131 · cond 0.231 · **lift +0.099** (×1.76) · false-alarm 0.77 · n=26; rotation-driven (TLT flat/↓): base 0.137 · cond 0.145 · **lift +0.008** (×1.06) · false-alarm 0.85 · n=69. If the edge concentrates in rates-driven fires, it is a 'rates fell' story, not money rotating defensive.

## Variant re-test (SAME frozen params + SAME pre-registered gate — no re-tuning)

Tests the levers the controls implicated: rates state IN the trigger, a rate-insensitive defensive (XLP/XLV), and the purest rotation proxy (XLU/XLK ratio). A variant 'passes' only if it clears ALL six gate checks OOS.

| Variant | OOS base→cond (ratio) | lift N10 | lift N21 | CI lo,hi | VIX-strat | lead 2-4d | n | PASS |
|---|---|--:|--:|---|--:|--:|--:|:--:|
| V0 baseline XLU | 0.1428→0.2051 (×1.437) | 0.0624 | 0.1527 | [-0.0482,0.1994] | 0.0238 | 0.25 | 39 | ✗ |
| V1 XLU ∧ rates-driven (TLT↑) | 0.1428→0.3214 (×2.252) | 0.1787 | 0.1498 | [-0.0037,0.3314] | 0.099 | 0.222 | 28 | ✗ |
| V2 XLU ∧ rotation-only (TLT flat/↓) | 0.1428→0.2069 (×1.449) | 0.0641 | 0.1696 | [-0.0693,0.2257] | 0.0119 | 0.0 | 29 | ✗ |
| V3 XLP-only (rate-insensitive defensive) | 0.1428→0.1064 (×0.745) | -0.0364 | -0.0393 | [-0.1181,0.0653] | -0.0083 | 0.0 | 47 | ✗ |
| V4 XLV-only (healthcare defensive) | 0.1428→0.1304 (×0.914) | -0.0123 | -0.0338 | [-0.0987,0.0826] | -0.0103 | 0.167 | 46 | ✗ |
| V5 defensive basket (XLU+XLP+XLV) | 0.1428→0.1707 (×1.196) | 0.028 | 0.1303 | [-0.0939,0.1249] | -0.0078 | 0.143 | 41 | ✗ |
| V6 XLU/XLK ratio bottoming | 0.1428→0.1613 (×1.13) | 0.0185 | 0.0168 | [-0.0737,0.0922] | -0.026 | 0.1 | 62 | ✗ |

- **V1 XLU ∧ rates-driven (TLT↑)** — rates state built INTO the trigger — if THIS is the only variant that works, the signal is 'rates fell', not rotation. fails: oos_ci_excludes_zero, false_alarm_ok, lead_24_share_ok (n=28).
- **V2 XLU ∧ rotation-only (TLT flat/↓)** — isolates NON-rates rotation — the hypothesis's actual mechanism. fails: oos_ci_excludes_zero, false_alarm_ok, lead_24_share_ok, vix_strat_survives (n=29).
- **V3 XLP-only (rate-insensitive defensive)** — staples have ~zero rate sensitivity — if rotation matters, XLP should lead. fails: oos_ci_excludes_zero, ratio_ge_1_30, false_alarm_ok, lead_24_share_ok, vix_strat_survives (n=47).
- **V4 XLV-only (healthcare defensive)** — another defensive cross-check. fails: oos_ci_excludes_zero, ratio_ge_1_30, false_alarm_ok, lead_24_share_ok, vix_strat_survives (n=46).
- **V5 defensive basket (XLU+XLP+XLV)** — broad-defensive bottom. fails: oos_ci_excludes_zero, ratio_ge_1_30, false_alarm_ok, lead_24_share_ok, vix_strat_survives (n=41).
- **V6 XLU/XLK ratio bottoming** — purest rotation proxy — defensives gaining vs tech directly. fails: oos_ci_excludes_zero, ratio_ge_1_30, false_alarm_ok, lead_24_share_ok, vix_strat_survives (n=62).

**Any variant passes the gate: NO.**

## TRAIN tuning grid (frozen pick maximizes primary lift @N=10, n≥12)

| W | W2 | cooldown | base | cond | lift | n_trig |
|--:|--:|--:|--:|--:|--:|--:|
| 3 | 2 | 10 | 0.1285 | 0.04 | -0.0885 | 25 |
| 3 | 2 | 21 | 0.1285 | 0.0435 | -0.085 | 23 |
| 3 | 3 | 10 | 0.1285 | 0.0312 | -0.0972 | 32 |
| 3 | 3 | 21 | 0.1285 | 0.0357 | -0.0928 | 28 |
| 5 | 2 | 10 | 0.1285 | 0.119 | -0.0094 | 42 |
| 5 | 2 | 21 | 0.1285 | 0.0833 | -0.0451 | 36 |
| 5 | 3 | 10 | 0.1285 | 0.1087 | -0.0198 | 46 |
| 5 | 3 | 21 | 0.1285 | 0.0789 | -0.0495 | 38 |
| 8 | 2 | 10 | 0.1285 | 0.1429 | 0.0144 | 56 ⟵ |
| 8 | 2 | 21 | 0.1285 | 0.125 | -0.0035 | 48 |
| 8 | 3 | 10 | 0.1285 | 0.1356 | 0.0071 | 59 |
| 8 | 3 | 21 | 0.1285 | 0.1176 | -0.0108 | 51 |

## Method / honesty notes
- Triggers are CAUSAL (engine.advanced_indicators uses only t and earlier bars; 3-day series resample→ffill, leak-free). Outcomes use engine.forward_dist.forward_paths (last-N rows NaN → no look-ahead).
- Sector ETFs store close+volume only (no OHLC), so the equity drawdown leg is close-based (mae). The stored VIX intraday HIGH only begins 2026-05 (the collector just started persisting OHLC), so the VIX-spike leg is CLOSE-based across history (a slightly conservative spike bar — close understates the intraday wick) and uses true highs only as they accumulate forward.
- DISPLAY-ONLY research. No live wiring. Even on a PASS the live signal would ship display-only with these measured base-rate / lift / lead-time numbers printed (engine/sector_bottom.py discipline).
