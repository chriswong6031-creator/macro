# Bitcoin Vector — accuracy upgrade plan

_Authored 2026-06-12. Companion to VECTOR_SIGNAL_RECON.md (what Swissblock does)
and VECTOR_DATA_AUDIT.md (what data we have). This doc is **what to change in
our math and why**, with the calibration gate every addition must pass._

---

## 1. Diagnosis — why the current Vector is less accurate than it could be

Three structural gaps, found by tracing `engine/btc_signals.py` against
`engine/btc_inputs.py` and the data store:

### 1a. No valuation / cycle anchor anywhere in the scoring
`momentum()` and `structure()` are **100 % price-derived trend votes** (EMA,
MACD, RSI, breakout, SMA200). This is exactly why the calibration report grades
them **"DIRECTIONAL — one half weak"**: pure trend-following degraded after 2021
because it has no concept of *cheap vs. expensive*. The metrics that define
**where in the cycle** BTC sits — MVRV-Z, NUPL, realized-price multiples — are
absent from the math, even though they carry the **deepest history (2010→)** and
are therefore also our best calibration anchors.

### 1b. ~60 % of collected, calibration-grade series never enter a calculation
Loaded (or one identity away) but **never scored**:

| Series | Depth | Status before this upgrade |
|---|---|---|
| MVRV | 2010→ | only used to *derive* realized_cap; never scored |
| **NUPL** | 2010→ (derived) | derived in `btc_inputs`, then never consumed |
| realized_price, supply_in_profit | 2022→ | unused |
| LTH-SOPR, STH-SOPR | 2022→ | unused (only the `sopr` aggregate is used) |
| open_interest (15 exch), OKX OI | 2022→ | unused |
| DVOL (Deribit implied vol) | 2021→ | unused |
| miner_sell_pressure | 2022→ | unused |
| fear_greed | 2018→ | unused |
| cot_bitcoin (CME net-spec) | 2018→ | not even loaded into inputs |
| hashrate, issuance_usd | 2010→ | unused |
| SSR (derived), SOL | — | unused |
| FRED macro (WALCL, RRP, real yields, HY-OAS, VIX) | deep | not connected to the Vector at all |

### 1c. Leverage / positioning is invisible
Funding is a weak binary "extreme" flag and open interest is ignored, so the
single best **short-term** risk amplifier — the reflexive leverage /
liquidation-cascade state — is unmodelled, despite us holding funding (deep) +
OI (15 exchanges) + DVOL.

---

## 2. The metric catalogue (what to add, mapped to source & axis)

### Tier 1 — free, deepest history, biggest gain (THIS PASS)
| Metric | Formula | Source (on disk) | Axis |
|---|---|---|---|
| **MVRV-Z score** | `(mcap − realized_cap) / rolling_std(mcap)` | coinmetrics mcap + derived realized_cap (2010→) | Valuation |
| **NUPL** | `1 − 1/MVRV` | derived (2010→) | Valuation / contrarian |
| **Mayer Multiple** | `close / SMA200(close)` | price (2014→) | Valuation (price-only cross-check) |
| **Puell Multiple** | `issuance_usd / SMA365(issuance_usd)` | coinmetrics issuance_usd (2010→) | Miner cycle |
| **Hash Ribbons** | `SMA30(hashrate) < SMA60(hashrate)` = capitulation; cross-back = recovery | coinmetrics hashrate (2010→) | Miner cycle / bottom |
| **STH cost-basis ratio** | `close / sth_realized_price − 1` | bgeo sth_realized_price (2022→) | Support level / regime line |
| **Capitulation/Euphoria overlay** | vote of {NUPL<0, supply-in-profit<50 %, F&G<25, MVRV-Z<0} (and the mirror) | nupl + supply_in_profit/supply + fear_greed + mvrv_z | Contrarian regime |

### Tier 2 — free, ~1 cycle, confirmation-only (NEXT)
- **Leverage/positioning risk**: funding level+slope + ΔOI-vs-Δprice (crowding) + COT net-spec extremes → a new Risk Index component.
- **DVOL implied-vol risk** + variance-risk-premium (implied − realized) → forward-looking risk; accumulate options skew (25-delta) from `deribit/options_summary`.
- **SSR dry-powder gauge** (already derived).

### Tier 3 — macro overlay (data already collected for the sister dashboard)
- **Net liquidity** = `WALCL − RRP − TGA`, as a 13-week rate-of-change → Strategic regime input (BTC tracks the *rate of change* of liquidity, ~8-month lead; T-bill issuance strongest — needs TGA, the treasury collector exists).
- **Risk-appetite layer**: real yields (DFII10), HY-OAS, VIX, DXY → Tactical/Strategic context.

### Tier 4 — small new collection
TGA (completes net liquidity) · Coin-Days-Destroyed / dormancy (unlocks **Reserve Risk**) · exchange netflows (alt source — bgeo was 403-gated) · options term-structure/skew accumulation.

---

## 3. Design decisions for this pass (Tier 1)

1. **Add, then measure — do not blend first.** New signals are emitted as
   **standalone columns** (`mvrv_z`, `nupl`, `puell`, `mayer`, `hash_ribbon_capit`,
   `sth_cb_ratio`, `market_extreme`/`extreme_score`). The existing
   momentum/risk/structure composites are **left byte-for-byte unchanged** so the
   prior calibration stays comparable and we can read each new metric's *marginal*
   forward-return record in isolation. Blending into the composites is a
   **follow-up pass, gated on the calibration verdict below.**
2. **Valuation is a 4th peer axis**, orthogonal to the three trend engines
   (mean-reversion vs. trend) — the documented fix for post-2021 momentum decay.
3. **ETF-era robustness**: MVRV-Z uses a **rolling** std window (config
   `z_window_d`, default 4y ≈ one cycle) rather than an expanding all-history std,
   because cycle peaks are diminishing and a fixed 2017-era threshold over-warns.
4. **Watch multicollinearity.** MVRV-Z, NUPL, supply-in-profit and Mayer are all
   functions of price/realized-price. We keep them separate **for measurement**,
   but when we blend we take **one representative per axis** — stacking all four
   just triple-counts the same signal and fakes confidence.
5. **No look-ahead.** Everything is rolling + `ffill` of already-published series;
   the backtest still acts on `shift(1)`.

---

## 4. Calibration gate (house rule)

Each new numeric signal gets a forward-return band table at 7/30/90d on the full
sample **and** both halves (split 2021-01-01), via the existing
`scripts/calibrate_vector.py` SIGNALS registry. A metric is promoted from
"context" to "signal" only if its rank-trend matches the expected sign in the
full sample **and survives both halves** (|rho| > 0.6, tolerant of one
small-sample tail). Expected signs:

| Signal | `want` | Rationale |
|---|--:|---|
| mvrv_z | −1 | higher valuation → lower forward return (mean-reversion) |
| nupl | −1 | euphoria → lower forward return |
| mayer | −1 | stretched above 200d → lower forward return |
| puell | −1 | low miner revenue (bottoming) → higher forward return |
| hash_ribbon_capit | +1 | capitulation periods → higher forward return |
| sth_cb_ratio | +1 (watch U-shape) | above STH cost basis = bull; report, don't assume |

Deep-history metrics (mvrv_z, nupl, mayer, puell, hash ribbon) are the ones we
trust as **calibration anchors**; the 2022→ cohort metrics are confirmation-only
until another cycle accrues.

---

## 5. Tier-2 options/funding structure (DONE — Deribit, the highest-reproducibility layer)

Provider recon (research/VECTOR_PROVIDER_RECON.md) confirmed Laevitas's options
analytics are essentially a skin over the **free public Deribit API** we already
pull. Built `collectors/deribit.compute_structure()` — ONE
`get_book_summary_by_currency` call → the full panel with locally-computed
Black-Scholes greeks (scipy-free, r=0): **ATM IV term structure (7/30/90/180d),
25Δ skew & risk reversal, put/call OI & vol ratios, max pain, gamma exposure**.
Stored as `deribit/options_structure` (one row/day, accumulating). Engine
`options()` adds the calibratable core (DVOL + VRP) plus the snapshot columns as
forward-accumulating context.

**Calibration (DVOL/VRP, history 2021→ ⇒ confirmation-only, ~1 cycle):**
- **DVOL is a risk gauge with a U-shape.** The `70-90` band (elevated-but-not-
  panic vol) is the danger zone: **−12.6%/90d, 18.7% hit (n=401)** — the bleed
  before/through a break; the `>90` panic tail bounces (+15.8%/90d, 71.4%). Best
  read as forward-drawdown (like the Risk Index), not a return ranker.
- **VRP `<−5`** (realized vol overshooting implied = mid-shock) → **+17.2%/90d,
  77.8% hit (n=203)** — a post-capitulation recovery tell; the complacent
  `5-15` middle is weakest (+3.9%).
- Caveat: both are post-2021 only and episode-autocorrelated → context, not a
  calibration anchor. The per-strike snapshot (skew/term/GEX) has no history yet
  — display-only until ~6-12mo accrues, then it enters the calibration gate.

## 6. Status

- [x] Tier 1 engine functions + config + inputs wiring; calibration extended
- [x] Tier 2 options layer (Deribit): structure collector + DVOL/VRP signals + calibration
- [x] **Tier 2 leverage/liquidation: OI crowding + funding stress + leverage_stress (D65)**
- [x] **Tier-1b blend: MVRV-Z<0 floor / Mayer>2.4 cap into allocation — A/B-confirmed, Sharpe↑ all variants (D66); composite_state headline**
- [x] **Surfaced on vector.html: hero Stance + Valuation/Options/Leverage panels (D67)**
- [x] **Tier 3 macro overlay (WALCL−RRP−TGA RoC + real-yields/HY-OAS/VIX/DXY): macro_score CONFIRMED both halves (D68); kept strategic, not blended into allocation — gate failed (D69); panel on vector.html**
- [x] **On-chain regime adds (D70): Coinbase Premium (CONTRARIAN top >1.5%, the only survivor), SSR oscillator (context), MPI (inverted) — measured + surfaced honestly**
- [ ] Tier 4 new collection: bgeo `reserve-risk` + `cdd` endpoints VERIFIED LIVE (→ Reserve Risk, a deep cycle-bottom signal) — highest-value remaining add; exchange netflows still 403-gated
- [ ] Calibrate options skew/term + leverage once more history accrues; consider a long-horizon allocation variant where macro is the primary timing input
