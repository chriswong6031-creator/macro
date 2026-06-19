# DannyTrades composite — reconstruction + phase-0 results

Status: **RESEARCH / NEUTRAL for buy-confirmation; one validated contrarian read.**
Not wired into any live page. Engine `engine/dannytrades.py`; harness
`scripts/dannytrades_phase0.py`; robustness `scripts/dannytrades_sweep.py`;
tests `tests/test_dannytrades.py`. Backtest on a local yfinance OHLCV cache
(`/tmp/dtcache`, 114 large-cap US names, 1962–2026 — real historical volume; the
`data/stocks/*.parquet` files only carry the last ~month of volume).

> **One-line verdict.** Danny Cheng's ("DannyTrades", X @dannycheng2022) method,
> faithfully reconstructed and rigorously backtested on his own style of names,
> does **not** produce a statistically significant *buy*-confirmation edge. The one
> result that survives the gate is the **inversion**: the composite is a
> *significantly contrarian* ranker (high score = recently-strong/extended name
> that tends to mean-revert) — usable as a "don't-chase / extension" caution, never
> as a buy. The whale-accumulation leg is the only positive-but-not-significant
> contributor and is genuinely orthogonal to momentum (a research lead, not a
> shippable signal).

## What was reconstructed (proxies for paywalled indicators)

Danny is a weekly/monthly *investor* whose public stack (from his X posts) is four
proprietary chart indicators we approximate with standard, documented tools:

| Danny's indicator | Our reproducible proxy (`engine/dannytrades.py`) |
|---|---|
| "whale accumulation %" (Panel 3, red=institutions/green=retail, 0–100; >35 momentum / >50 rises / >75 soars) | Chaikin Money-Flow accumulation, smoothed, rescaled 0–100 by its own trailing **percentile** |
| "volatility hole / black hole" (sticky box; close above upper=buy, below lower=sell) | Bollinger-bandwidth **squeeze** whose frozen range is the box; close-beyond-edge breakout |
| "momentum bars" / POC (whale levels / avg cost; close above=bullish) | rolling **volume-weighted price** (POC proxy) + reclaim |
| red/blue "ribbon" + inverted candles + MACD/RSI "down-curl" | EMA-ribbon trend state + MACD/RSI momentum-OK filter |

Combined into a 0–100 confluence **score** and discrete `danny_buy` / `danny_sell`
states from his checklist. All functions are **causal** (trailing windows only).

## Headline results (`/tmp/dt_results2.json`)

| Test | Result | Read |
|---|---|---|
| **Standalone XS rank-IC @63d** | **−0.0218** (t_HAC −2.83, q_FDR 0.009, survives) | **Significantly CONTRARIAN.** High composite → underperforms next quarter. Don't pick longs with it. Sub-periods −0.024 / −0.015 (stable sign). |
| Combine with 12-1 momentum | mom IC 0.031 → **mom⊕danny 0.005** | Linearly adding it **dilutes** momentum (negatively correlated). Don't blend. |
| **Pullback confirmation lift** | +2.1pp P(up) (0.631→0.652); **95% CI [−0.2pp, +4.7pp]** (cluster bootstrap, includes 0); beats placebo only at **P=0.068**; median-return payoff **≈0**; drawdown tail **−1.0pp worse** | Directionally consistent (P(lift>0)=0.96) but **not significant** and economically ≈0. |
| **Whale-leg ablation** | ribbon+momentum *without* whale = **−0.99pp**; **whale-gate alone = +1.93pp**; corr(whale, mom12-1) = −0.06 | The whale gate is the **only** positive part; trend/momentum alone hurts; **not momentum-in-disguise** (whale-high names have *lower* momentum). |
| Breakout veto (`danny_sell`) | 0.624→0.562 but **n=32**, CI contains base rate, sign-flips under perturbation | **Statistical noise. Dropped.** |
| Discrete `danny_buy` event study | P(up) 0.619 vs unconditional 0.627 | No standalone timing edge. |

## Robustness (`scripts/dannytrades_sweep.py`, `/tmp/dt_sweep.json`)

The pullback lift's **sign** is structural — positive across every genuinely-independent
parameter perturbation (whale window, CMF length, squeeze pctile, confirm threshold)
and both eras — but its **magnitude** is fragile (lift−placebo gap collapses to
+0.006–0.014) and never clears significance. Higher whale thresholds (whale_momentum=60)
give the strongest tilt, consistent with the ablation: the whale gate carries it.

## Adversarial verification

Red-teamed by a 5-agent workflow (lookahead / overfit-survivorship / statistical-validity
/ alternative-explanation / synthesis):

- **Leakage: NONE** — prefix-truncation equivalence is byte-identical across all
  columns and cut points (signals on `df[:k]` == full-series at every index < k);
  forward labels are strictly future and never reused as features. (Encoded as a
  test.)
- **Overstatement corrected** — the original write-up wrongly called the drawdown
  tail "improved" (it is ~1pp **worse**) and called the lift "placebo-beating /
  era-stable" without an error bar. With cluster/block bootstrap the **lift's CI
  spans zero** and the breakout veto (n=32) is noise. The harness now ships its own
  bootstrap CI + full placebo distribution so it cannot reproduce the overstatement.
- **Survivorship** is a live, uncontrolled alternative generator: 114 names that
  survived as large-caps through 2026; the within-ticker placebo controls base-rate
  and timing but **not** survivorship.

## Verdict & recommendation

- **Buy-confirmation use (Danny's intended one): NEUTRAL / research-only.** The lift
  is real-but-insignificant (CI includes 0, P≈0.07, payoff ≈0, tail worse). Do **not**
  wire it into the dashboard as a buy/confirm chip — it has not earned the gate.
- **The validated, combinable read is the inversion:** a high composite is a
  significant **contrarian / extension** flag (FDR-passed). This aligns with the
  existing extension-veto philosophy and is the one piece worth a dedicated
  follow-up (validate as a "don't-chase" caution leg on `us_stocks`).
- **The whale-accumulation gate** is a genuine, momentum-orthogonal, but
  not-significant tilt — a research lead. A faithful (vs percentile-proxy) whale
  metric and a non-overlapping / longer-horizon test are the natural next steps.

Honest bottom line: his *framework* is coherent and his *names* did well (a
concentrated AI-leader book in a bull market — selection, not signal); the
*reconstructed signals* carry no significant forward buy-edge, but do carry a
small, validated **contrarian** one.
