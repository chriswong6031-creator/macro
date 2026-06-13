# Vector — new-factor hunt + Tier-1 additions

_2026-06-13. A 6-agent research+audit workflow mapped our ~25 signals against the
BTC factor universe. Verdict: the Vector is **saturated in valuation/trend but
structurally blind to four orthogonal axes** — time/cycle, positioning, cross-asset
co-movement, and spending-behaviour. All four are now added (each calibrated)._

## The gaps (coverage audit)
Dense/over-covered: cost-basis/valuation (MVRV-Z, NUPL, Mayer, Reserve Risk,
SOPR, supply-in-profit) and trend (momentum, structure, impulse). **Absent**:
- **Time / cycle clock** — `cycle_position` was a momentum knob, *zero temporal
  info*. No halving phase.
- **CME COT positioning** — `cot_bitcoin` collected but never wired in.
- **Cross-asset correlation regime** — macro ingested as *levels*, never BTC's
  *co-movement* (is it trading as a risk-asset?).
- **Spending-behaviour / coin-age** — no CDD/dormancy/VDD despite STH/LTH-SOPR
  loaded-and-idle. The single best "we completely lack this" gap.

## What shipped (4 new factors, all calibrated)

### 1. Halving Cycle Clock — DIRECTIONAL, huge separation
`cycle_clock()`: `days_since_halving`, `cycle_pct` (= days/1458), `cycle_phase`.
Deterministic, zero data dependency, maximally orthogonal. Calibration (n=3
cycles, a soft PRIOR): **accumulation (post-halving) +47.9%/90d @81% hit** vs
**markdown (mid-cycle) +5.1%/90d @43% hit** — the textbook 4-year structure.
Wired as a **±5pp tilt on the scenario probabilities** (accumulation up, markdown
down), never a trigger. config `vector.cycle_clock`. _Now: cycle_pct 0.54 =
markdown = historically the weakest phase._

### 2. CME COT positioning — CONFIRMED contrarian top (was idle data)
`positioning()`: `cot_net_pct` + `cot_z` (z-score of net-spec % of OI, ~2y). The
only regulated, real-money, weekly positioning input. Calibration: **crowded spec
long (z>1.5) → −5.8%/90d @35% hit** (contrarian TOP). Wired into `composite_state`
as a DISTRIBUTE trigger. config `vector.positioning`. _Now: z = +3.0 (crowded
long) → the headline reads DISTRIBUTE._

### 3. Cross-asset correlation regime — DIRECTIONAL (context)
`cross_asset_corr()`: 90d rolling Pearson of BTC vs SPX/gold/DXY returns +
`risk_asset_regime`. A 2nd-moment signal the all-levels overlay can't express.
Calibration: **coupled to equities (corr>0.4) → +13%/90d vs decoupled +33%** —
risk-asset coupling = lower forward returns. Zero new data (Yahoo on disk).
Surfaced as context. config `vector.cross_asset`. _Now: BTC↔SPX 0.44 (mixed)._

### 4. VDD Multiple (spending-behaviour) — CONTEXT (honest)
`behaviour()`: Value-Days-Destroyed Multiple from checkonchain (2011->, deep, no
bgeo quota) — the coin-age axis (old coins waking = LTH distribution). Calibration
was HONEST: VDD is **coincident with bull phases, not a clean forward-return top
signal** (elevated 1.4-2.9 → +41%/90d; the >2.9 "Hot" band isn't cleanly
negative because tops are processes). So surfaced as a **context gauge** for the
spending-behaviour axis, NOT claimed as a signal. _Now: 0.36 (8th pctile) = dormant
network / accumulation, consistent with the markdown phase._

## Honest caveats (held)
- **cycle clock is a PRIOR (n=3 tops)** — a small tilt, not a trigger; "post" half
  weak by construction (partial cycles).
- **VDD demoted to context** when the data didn't support the "tops" thesis —
  measure, don't overclaim.
- **corr_spx one-half-weak** (pre-2021 BTC-SPX coupling was structurally different)
  → confirmation/context, not standalone alpha.
- No double-counting: cycle is orthogonal (time), COT orthogonal (regulated
  positioning), corr orthogonal (2nd moment), VDD orthogonal (coin-age) — none
  re-touch the saturated valuation/trend cluster.

## Deferred (next)
- **bgeo CDD/Liveliness/Dormancy Flow** — bottom-side behaviour signals; bgeo was
  rate-limited (429) this session. VDD (checkonchain) already covers the tops/
  activity side of the axis.
- **Deribit annualized futures basis** (+ slope) and **options skew term structure**
  — the derivatives-curve axis; ~1-cycle depth = confirmation-grade. Read *with*
  COT (carry confirmation vs leverage blow-off).
- **Global M2 liquidity impulse** (forward-led, FRED multi-country + Yahoo FX) —
  the macro *lead* our Fed-only net-liquidity lacks.
