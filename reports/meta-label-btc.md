# Bitcoin meta-label (GBT) — honest evaluation

_As of 2026-06-13 · span 2015-01-01..2026-06-13 · primary grid `alloc_optimal` · 2934 long calls over 4182 bars_

## VERDICT: 🚫 DO NOT WIRE LIVE — meta does not beat the primary baseline out-of-fold on a calibrated, multiple-testing-honest basis. (The institutional review anticipated this: meta-labeling adds nothing here, which is a valid result.)

- ✗ risk-adjusted: ΔSharpe -0.431 (need ≥0.05), ΔMaxDD +16.3pp (need ≥−2.0); ΔCAGR -40.3pp (informational)
- ✗ calibrated: skill=-0.207, Platt a=0.134, b=0.298
- ✓ multiple-testing: DSR=0.9502 over n_trials=20 (need ≥0.9)

> DEFAULT-OFF LEAF. The verdict keys off the CAUSAL walk-forward OOF backtest; CPCV OOF (train on all other purged folds) drives the probability-calibration read. n_trials counts every (label × mode × size-scheme) strategy compared. Wiring live requires recommend_live AND a human flip of vector.meta_label.enabled.

## What meta-labeling is

The **primary** model (the deterministic momentum × risk_index allocation grid) sets the **side**. The **secondary** GBT takes that call plus context and learns **P(the call is correct)** over the forward horizon — used to **filter / size**, never to pick direction. This is the one high-N layer (~2934 labeled long calls) where a tree won't just memorize noise.

## Selected meta strategy vs the primary baseline (net of cost)

Selected config: **forward_sign · walkforward · prob_raw** (coverage 2016-11-28..2026-05-14).

| | CAGR | Sharpe | MaxDD | Time-in-mkt |
|---|---:|---:|---:|---:|
| Primary baseline | 65.9% | 1.816 | -46.5% | 100.0% |
| Meta-sized | 25.6% | 1.385 | -30.2% | 100.0% |
| **Δ (meta − base)** | -40.3pp | -0.431 | +16.3pp | |

_The verdict keys off the **walk-forward** (causal) backtest. CPCV (train on all other purged folds) is reported too — it uses more data but is non-causal, so it measures information content, not a tradeable curve._

## Multiple-testing haircut (Deflated Sharpe)

- **Meta:** DSR **0.9502** (SR 1.38 ann vs haircut SR0 0.74); n_trials=20, T=2266d — _SURVIVES multiple-testing (DSR≥0.95)_
- **Baseline:** DSR 1.0 (SR 1.82 ann), n_trials=1

_n_trials = every (label × CV-mode × size-scheme) strategy compared = **20**. Overestimating is the conservative direction._

## Probability calibration (out-of-fold)

_Skill > 0 means the OOF probabilities beat the base-rate climatology; Platt a≈1, b≈0 means they need no recalibration. A heavily shrunk a (≪1) means the GBT's probabilities barely move with the truth — no information._

- **triple_barrier** (h=30d): Brier 0.2871 vs base 0.2424 → skill **-0.184** → _NO skill (worse than base-rate)_; base-rate 0.587; Platt a=0.132, b=0.308.
- **forward_sign** (h=30d): Brier 0.2934 vs base 0.2431 → skill **-0.207** → _NO skill (worse than base-rate)_; base-rate 0.583; Platt a=0.134, b=0.298.

## Full grid (every config tried)

| label | mode | size | n_oof | meta Sharpe | base Sharpe | ΔSharpe | ΔCAGR | ΔMaxDD |
|---|---|---|---:|---:|---:|---:|---:|---:|
| triple_barrier | cpcv | prob_raw | 2860 | 1.793 | 1.752 | +0.041 | -29.3pp | +17.8pp |
| forward_sign | cpcv | prob_raw | 2870 | 1.73 | 1.738 | -0.008 | -30.7pp | +16.7pp |
| triple_barrier | cpcv | filter@0.50 | 2860 | 1.478 | 1.752 | -0.274 | -30.2pp | +6.6pp |
| forward_sign | cpcv | filter@0.50 | 2870 | 1.433 | 1.738 | -0.305 | -32.0pp | +9.8pp |
| triple_barrier | cpcv | filter@0.55 | 2860 | 1.418 | 1.752 | -0.334 | -34.7pp | +7.7pp |
| forward_sign | walkforward | prob_raw | 2266 | 1.385 | 1.816 | -0.431 | -40.3pp | +16.3pp |
| triple_barrier | walkforward | prob_raw | 2266 | 1.383 | 1.816 | -0.433 | -40.4pp | +16.2pp |
| triple_barrier | cpcv | prob_linear | 2860 | 1.302 | 1.752 | -0.450 | -41.5pp | +19.5pp |
| forward_sign | cpcv | filter@0.55 | 2870 | 1.217 | 1.738 | -0.521 | -39.3pp | +8.9pp |
| triple_barrier | cpcv | filter@0.60 | 2860 | 1.227 | 1.752 | -0.525 | -41.3pp | +16.7pp |
| forward_sign | walkforward | filter@0.60 | 2266 | 1.255 | 1.816 | -0.561 | -39.9pp | +15.6pp |
| forward_sign | cpcv | prob_linear | 2870 | 1.16 | 1.738 | -0.578 | -43.9pp | +17.7pp |
| forward_sign | cpcv | filter@0.60 | 2870 | 1.149 | 1.738 | -0.589 | -41.9pp | +13.8pp |
| triple_barrier | walkforward | filter@0.50 | 2266 | 1.189 | 1.816 | -0.627 | -40.3pp | +15.5pp |
| forward_sign | walkforward | prob_linear | 2266 | 1.182 | 1.816 | -0.634 | -43.6pp | +15.3pp |
| triple_barrier | walkforward | filter@0.55 | 2266 | 1.155 | 1.816 | -0.661 | -42.1pp | +11.3pp |
| forward_sign | walkforward | filter@0.55 | 2266 | 1.155 | 1.816 | -0.661 | -42.2pp | +13.6pp |
| triple_barrier | walkforward | filter@0.60 | 2266 | 1.144 | 1.816 | -0.672 | -43.6pp | +13.6pp |
| forward_sign | walkforward | filter@0.50 | 2266 | 1.093 | 1.816 | -0.723 | -43.4pp | +10.1pp |
| triple_barrier | walkforward | prob_linear | 2266 | 1.067 | 1.816 | -0.749 | -47.0pp | +13.5pp |

## Feature collinearity (VIF)

mvrv_z 31.64, reserve_risk 26.54, cycle_pct 7.64, risk_index 7.23, oi_mcap_ratio 6.72, corr_spx 6.54, global_m2_yoy 5.13, vol_pctile 4.96

Redundant (VIF≥5): risk_index, cycle_pct, oi_mcap_ratio, corr_spx, mvrv_z, reserve_risk, global_m2_yoy

## Block-bootstrap CI (selected meta, net)

Sharpe 95% CI [0.52, 1.39, 2.21] · MaxDD% CI [-52.4, -31.8, -19.7] · P(Sharpe>0)=0.999

## Features (21)

`momentum`, `risk_index`, `risk_oscillator`, `vol_pctile`, `cycle_position`, `cycle_pct`, `impulse`, `structure`, `funding_z`, `leverage_stress`, `oi_mcap_ratio`, `corr_spx`, `mvrv_z`, `reserve_risk`, `vdd_multiple`, `bfi`, `cot_z`, `macro_score`, `global_m2_yoy`, `drawdown`, `risk_regime_hi`

Label base rates: triple_barrier 0.587, forward_sign 0.585