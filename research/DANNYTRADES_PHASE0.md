# DannyTrades composite — reconstruction + phase-0 results

Status: **RESEARCH / RETIRED as signal — all directional reads failed time-controlled replication (DT-W1a/DT-W2, 2026-07-06); chip is a descriptive positioning readout.**
The contrarian read IS live, display-only: `engine/dannytrades_chip.py` →
`dt_contra` on US stock pages (basket-level fields via `engine/basket_tape.py`;
the Canada builder degrades gracefully on its close-only universe). See
`research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md` (2026-07-06,
rulings DT-R1..R12; §7 Amendment DT-W1a 2026-07-06: all four contrarian reads FAILED time-controlled replication on the 2021+ survivorship-honest PIT panel — whale line dropped from the chip, extension band downgraded to weak tilt; §8 DT-W2 64y settlement: the one pooled survivor (whale-surge fade) is pre-2010-only, null 2011-2026 → restoration DENIED (DT-R15), ALL directional claims retired) for the standing adjudication. Engine `engine/dannytrades.py`; harness
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

## Follow-up (`scripts/dannytrades_whale.py`, `engine.dannytrades.whale_buy_fraction`)

Two open questions from the phase-0, settled with a FAITHFUL saturating whale metric
(`whale_buy_fraction` = share of windowed volume that traded as buying, 0–100 — runs
to the 90s like his reads) on **monthly bars** (his actual timeframe) with
**NON-OVERLAPPING** forward returns (the overlap that sank daily-63d significance is
gone). Results (`/tmp/dt_whale.json`):

**Q1 — the whale signal is statistically REAL, but it INVERTS his thesis.**
- Whale *level* alone: weak (IC@1m −0.009, t −1.2, p 0.24).
- **Whale *change* = "whales entering": IC@1m −0.023, t −3.9, p 0.0001** (and −0.022,
  t −2.9 at 3m, non-overlapping) — **significant and NEGATIVE**.
- Event study (ticker-cluster bootstrap, CIs **exclude zero**): "whales entering"
  (Δ>+10) → next-month P(up) 0.546 vs 0.572 base, +1.22% vs +1.54% (lift −0.025,
  CI [−0.034, −0.016]); **"whales leaving" (Δ<−10) → 0.593, +2.01%** (lift +0.022,
  CI [+0.015, +0.029]); whale **hot >75** → 0.546, lift −0.026, CI [−0.047, −0.006].
- Reading: by the time his accumulation metric is **hot/rising**, the move is mature
  and **mean-reverts → FADE**; when it has bled out, that's the bounce. The whale
  strategy works **as a contrarian signal — the opposite of how he uses it.**

**Q2 — the extension/contrarian read is clean and monotone.** Forward-63d return
falls monotonically across all ten composite-score deciles (**5.68% → 4.30%**,
top−bottom −1.38%, **Spearman −0.88**); whale-level deciles likewise (Spearman −0.82).
A high DannyTrades score is a textbook **"extended / don't-chase"** flag.

**Net update:** the validated, combinable signal is **contrarian** — (a) high composite
score = extension caution (Spearman −0.88), and (b) "whales entering" = a significant
fade tilt (t −3.9). Both align with the repo's washout/extension-veto philosophy.
Caveat unchanged: 114-name survivor panel (survivorship flatters mean-reversion).
**Live-shipping prerequisite:** the daily pipeline only stores ~1 month of per-stock
volume (`data/stocks/*.parquet`), so any volume-based leg needs the stocks collector
extended to persist full-history volume first.
