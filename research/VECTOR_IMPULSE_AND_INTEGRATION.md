# Vector — Impulse signal + full-signal integration

_2026-06-13. Grounded by a 5-agent research+audit workflow (Glassnode/Swissblock
Impulse, scenario-probability methodology, momentum-acceleration techniques, and
an adversarial integration audit). Answers the user's question: "are all factors
integrated into the final outputs, and do we have an Impulse?"_

## The gap that was found

Many signals were built as standalone columns but **under-wired into the four
things the user actually reads.** Audit (pre-change):

| Final output | Used | Confirmed signals MISSING |
|---|---|---|
| Market-state headline (`composite_state`) | momentum + risk + extreme + valuation_state | **macro_score** (CONFIRMED), **reserve_risk** (TOP), BFI |
| BTC allocation (`allocation`) | momentum + risk + MVRV-Z/Mayer overlay | reserve_risk cap (macro tested → rejected) |
| Short-term 3-day scenarios (`scenarios_3d`) | **momentum_state only** + ATR | everything (DVOL, risk, …) |
| Scenario probabilities (`env_probabilities`) | **momentum_state only** base rate | everything — the weakest link |

And there was **no Impulse** — only a narrow EMA-of-returns "impulse" inside the
flash-crash alert machine, not a core signal.

## What Glassnode/Swissblock's Impulse is

Their **Impulse** measures the *"exponential price structure"* — the **rate of
trend / acceleration of momentum** across the top ~350 assets, surfaced as
breadth (% in negative impulse). It spots the **START and EXHAUSTION** of a move,
not the level: "when capitulation peaks the Impulse collapses to zero — panic
exhausts and buyers step in" (cryptodnes/Daily Hodl). Displayed as dual
Positive%/Negative% breadth bars (HAWKEYE_NOTES). It is **directionally
reproducible** on free data (a BTC-only single-asset impulse is trivial); the
exact spans/breadth need their feed.

## What shipped

### 1. `impulse()` signal (engine/btc_signals.py) — NEW, CONFIRMED
`impulse = efficiency_ratio × weighted_mean(zscore(MACD-histogram, 90d),
zscore(Δfunding)+zscore(ΔOI))`, winsorized ±3. The MACD-histogram is the denoised
2nd-derivative of price (the inflection core); the **Kaufman efficiency ratio is a
MULTIPLIER not a vote** (collapses the signal to ~0 in chop — the dominant
false-positive mode); funding+OI add an orthogonal positioning impulse (NaN-skipping
weighted mean so the deep 2014→ accel core isn't poisoned by the 2023→ funding).
Emits `impulse`, `impulse_state`, `impulse_pos_pct` (breadth proxy),
`efficiency_ratio`. config `vector.impulse`.
**Calibration: CONFIRMED both halves** — `>0.5` → +3.7%/7d, +32.6%/90d @66% hit;
the `<−0.5` exhaustion band bounces +1.5%/7d. 4th signal to clear both halves
(with Risk Index, BFI, macro_score). Surfaced as its own panel (state + breadth
bar + efficiency-ratio chop gate).

### 2. Market-state headline now fuses the confirmed signals
`composite_state` gained **macro_regime** (tailwind/headwind), **BFI>60**
(confirms RISK-ON), and the **reserve_risk TOP** (>0.02 → DISTRIBUTE). config
`vector.composite`.

### 3. Scenario probabilities rebuilt (build_vector.py) — the big fix
`_cond_up_prob(df, cfg, horizon)`: P(up) conditioned on **momentum_state ×
risk_regime** (both CONFIRMED), **empirical-Bayes shrunk** toward the momentum
marginal (`p̂=(k+α·p₀)/(n+α)`, α=10), **macro tailwind/headwind tilt** (±5pp), and
**capped to [30%, 70%]** (anti-overfit for ~3 cycles). Honest n + cell shown.
`env_probabilities` (7d) and `scenarios_3d` (3d) both use it — replacing the
momentum-only 60/40/25 lookup. A "bear / high-risk" tape now reads ~52% (near
coin-flip, the contrarian U-shape), not the old naive 25%. `scenarios_3d` also
**scales the ATR bands by DVOL** (forward vol sizes the 3-day cones). config
`vector.scenarios`.

### 4. Allocation — reserve_risk safety cap (gated)
A/B-tested: **macro gate REJECTED** (CAGR 51→41 — macro is strategic, not
tactical, reconfirmed); **reserve_risk>0.02 trim** added as a calibrated TOP
safety cap — neutral in-sample (momentum/risk de-risk first) so **no regression**,
but guards a regime where they lag. config `vector.allocation.overvalued_rr`.

## Honest caveats (held to)
- **No double-counting**: reserve_risk/MVRV-Z/NUPL are one cost-basis factor;
  impulse correlates with momentum — so impulse is NOT added as a probability tilt
  on top of the momentum-conditioned base (avoids double-count). Macro (orthogonal)
  is the only tilt.
- **~3 cycles = prior-dominated**: probabilities are shrunk + capped; a >15-20%
  edge over base rate would be overfit, so we don't claim it.
- **Anticipation ≠ edge**: the `<−0.5` impulse bounce is milder than the
  positive-continuation edge — surfaced honestly, not oversold.
- Macro stays out of tactical allocation (failed the A/B twice) — it lives in the
  headline + the probability tilt instead.
