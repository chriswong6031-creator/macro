# Liquidity-shock reversal classifier — phase-0 (LSR-P0)

**Date:** 2026-08-05 · **Verdict:** **NO-GO (construction-scoped)** · **Family:** `liquidity_shock_reversal_p0`
**Reproduce:** `PYTHONPATH=. python -m scripts.research_liquidity_shock_reversal`
**Prereg + decision:** `research/LIQUIDITY_SHOCK_REVERSAL_PHASE0.md`

---

## §0 The candidate

Separate *"this stock is falling because informed investors learned something bad"*
from *"this stock is falling because someone urgently needed liquidity"*. The two
charts look identical; the forward paths are supposed to differ. Savor (2012)
is the canonical support: major price shocks **accompanied by information drift**,
shocks **without information reverse**. The proposal is a classifier over extreme
residual returns, abnormal volume, signed order imbalance, spread/price-impact
proxies, peer divergence and a news firewall, sorting each shock into full
reversal / partial reversal / continued information-driven move — with two uses
for Prophet: generate genuine mean-reversion candidates, and stop the momentum
engine buying the last stage of a forced-covering squeeze.

## §1 Verdict in one line

**The separation does not exist on our frame.** Across 16,315 firewall-covered
±3σ high-volume shocks (1,274 names, 1,191 trading dates, 2021-09→2026-07), the
information firewall separates **0 of 10** news-vs-no-news contrasts; the
microstructure feature set separates **3 of 36** feature×horizon tests (1.8
expected by chance at α=0.05, no feature consistent across horizons); the veto
stand-in moves **0 of 6** conditional gaps. The one effect that *is* real — plain
unconditional short-horizon residual reversal — is ~4× too small to be worth
trading and is unimproved by any of the proposed conditioning.

## §2 What was measured

Universe: `data/massive_stock_day`, 4,281 tradeable names (≥$5, ≥$2M median
dollar volume) over 2021-07-06→2026-07-02, split-repaired with the canonical
`replay_standout_pipeline.split_adjust`. Residual = own return minus the
**equal-weighted same-sector ex-self peer return**. Shock = residual-return
z ≤ −3 (or ≥ +3) with volume ≥ 2× its trailing-60d median. Information proxy =
an EDGAR 8-K (earnings item 2.02, or material items) filed within ±1 calendar day.
All intervals are **circular block bootstraps over trading dates** — shocks arrive
in market-wide bunches, so the honest unit is the day, never the name-day.

### The firewall works — checked before believing any null

| median, down-shocks | no-news | news (8-K ±1d) |
|---|---|---|
| overnight gap | −1.16% | **−4.73%** (4.1×) |
| abnormal volume | 2.87× | 3.64× |
| abnormal trade count | 2.35× | 2.87× |
| residual z | −3.89 | −5.36 |

8-K ±1-day windows cover ~4.1% of days unconditionally but **60.0%** of
down-shocks — a ~15× enrichment. Earnings move overnight; liquidity shocks move
intraday, and the flag sees exactly that. This is not a null off a broken flag.

### (B) The headline contrast — 0 of 10

Forward **residual** return from the t0 close, per-date equal-weighted, %:

| side | h | no-news | news | **DIFF (no-news − news)** |
|---|---|---|---|---|
| down | 1 | +0.006 | −0.071 | +0.076 [−0.174, +0.320] |
| down | 3 | −0.247 | −0.181 | −0.080 [−0.449, +0.272] |
| down | **5** | **−0.329** [−0.649, −0.040] | **−0.232** [−0.486, +0.034] | **−0.199 [−0.622, +0.211]** |
| down | 10 | −0.472 | −0.437 | −0.266 [−0.803, +0.261] |
| down | 21 | −0.572 | −0.822 | −0.065 [−0.753, +0.622] |
| up | 5 | −0.173 | −0.402 [−0.666, −0.147] | +0.183 [−0.350, +0.712] |
| up | 21 | −0.572 | −0.818 | +0.408 [−0.511, +1.350] |

Every DIFF interval spans zero. Worse for the thesis: **no-news down-shocks
continue down** (−0.33% at 5d, interval excludes zero) rather than reverting, and
the biggest no-news shocks continue hardest (z ≤ −6 → −1.0% at 5d vs −0.03% for
z ∈ (−4,−3]). Hit rates sit at 50%. On the up side, *news* shocks fade more than
no-news ones — the opposite of the predicted drift.

### (C) The microstructure classifier — 3 of 36, i.e. noise

Date-clustered rank-IC of each candidate feature vs forward residual return,
inside the no-news down-shock population (n=3,285). Only three intervals exclude
zero — `avg_trade_size_rel` at h=3 (−0.052), `intraday_ret` at h=5 (−0.065),
`resid_z` at h=5 (−0.077) — against 1.8 expected by chance, and **no feature
survives at more than one horizon**; several flip sign between horizons
(`clv` +0.007 → −0.045 → −0.046, `intraday_ret` +0.020 → −0.065 → −0.030).
Close-location value, abnormal volume, abnormal trade count, Amihud price impact,
spread proxy, flow persistence and dollar volume are all null at every horizon.

### (D) The veto stand-in — 0 of 6

The live Prophet frames cannot answer this: `data/prophet_postmortem` holds 808
episodes over 24 board dates and `us_board_ledger/retro_grades` 2,282 rows over
five weeks — one regime, no power against a ~0.3pp effect. So this uses the
roadmap's own retro-stand-in pattern: names above their 200dma, within 15% of the
252d high, top momentum tercile (748,571 name-days, ~597 names/day).

| h | base stand-in | +3σ up-day (chase) | gap vs base | −3σ down-day (flush) | gap vs base |
|---|---|---|---|---|---|
| 5 | −0.228 | −0.143 | +0.068 [−0.202, +0.354] | −0.105 | +0.063 [−0.281, +0.395] |
| 10 | −0.428 | −0.377 | +0.015 [−0.367, +0.398] | −0.195 | +0.157 [−0.341, +0.646] |
| 21 | −0.882 | −0.985 | −0.197 [−0.704, +0.308] | −0.270 | +0.484 [−0.200, +1.131] |

Chasing a +3σ high-volume day in a momentum name is, if anything, marginally
*better* than the base state at 5 and 10 days. There is no veto here to install.

### (A) The base effect — real, and ~4× too small

Unconditional reversal (signal = minus the trailing residual return) does exist,
significantly, in every liquidity tercile — and it is nowhere near the cost bar.
Decile long-short per cycle, 1-day formation:

| hold | tercile | rank-IC | D10−D1 | break-even / leg | cycles/yr |
|---|---|---|---|---|---|
| 5d | illiquid | +0.011 [+0.003, +0.019] | +0.077% [−0.076, +0.237] | 3.8 bp | 50 |
| 5d | mid | +0.011 [+0.004, +0.019] | +0.187% [+0.049, +0.333] | 9.4 bp | 50 |
| 5d | **liquid** | **+0.013 [+0.004, +0.022]** | **+0.284% [+0.092, +0.485]** | **14.2 bp** | 50 |
| 1d | liquid | +0.012 [+0.002, +0.021] | +0.038% | 1.9 bp | 252 |

A 5-day decile long/short turns the whole book over 50× a year on both legs. The
edge dies at **14 bp of round-trip cost per leg** in the best (liquid) slice, and
at 4–9 bp elsewhere. This reproduces, at the 1–5 day horizon the candidate
proposed, what `scripts/validate_reversal.py` already concluded at the monthly
horizon: *"reversal as selection alpha is a net-of-cost mirage"* (liquid residual
reversal IC t_HAC 0.351, net-10bp −1.34%/yr) — and what
`validate_reversal_nonsurvivor.py` confirmed on a delisting-recovered panel.

## §3 Correction on the cost proxy — do not reuse `spread_shock` as a cost

The study's first cut subtracted the Corwin-Schultz high-low spread as if it were
a trading cost, producing net figures of −0.9% to −1.2%. **That was an
overstatement and has been withdrawn.** Simulated against a *known* planted
spread, the clipped C-S mean is dominated by volatility: a 5 bp true spread reads
**38 bp** at 1.5%/day vol and **74 bp** at 3%/day, rising only to 80/110 bp when
the true spread is genuinely 100 bp. A shock-day population is selected for high
range, so the measured 62–91 bp on our events is consistent with a near-zero true
spread plus contamination. The shipped script therefore reports a **break-even in
basis points** and never subtracts a point estimate; the behaviour is pinned in
`tests/test_liquidity_shock_reversal.py::test_corwin_schultz_is_dominated_by_volatility_not_spread`
so a later session cannot quietly reuse the column as a cost. **None of the four
verdicts depends on this** — all are measured gross.

## §4 Power — what this study could and could not have seen

At h=5 the per-arm interval half-width is ≈±0.31 pp, so the minimum detectable
effect is ~0.3 pp per 5 days. Against a break-even of 4–14 bp per leg, the study
is comfortably powered to rule out a **tradeable** effect. It is *not* powered to
rule out a small one, and it should not be read as saying the separation is
exactly zero — only that it is smaller than anything that could pay for itself.

## §5 What this closes, and what it explicitly does not

**Closed:** the 1–5 day liquidity-shock reversal classifier as selection alpha or
as a Prophet veto, on the ≥$5 / ≥$5M-ADV US panel, with an EDGAR-8-K information
firewall and OHLCV-derived microstructure proxies.

**Not closed, and each is a real reopener:**

1. **Tape-grade features.** The candidate's `signed_order_imbalance`,
   `price_change_per_dollar_flow` and a true `spread_proxy` need the per-trade
   tape and the NBBO. Our massive.com entitlement is aggregates-only —
   `trades_v1` and `quotes_v1` both 403 (`collectors/massive_flatfiles`). The
   order-flow half of the proposal was **never tested at its intended fidelity**;
   it was proxied from daily bars. This is the single largest caveat.
2. **A richer information firewall.** Savor used *analyst reports*; we used 8-Ks.
   `data/finnhub/recommendation.parquet` and the revisions store are unwired here,
   and a firewall that misses guidance, newswire and sector news leaves informed
   moves inside the "no-news" arm, attenuating the contrast toward zero.
3. **The illiquid tail.** Sub-$5 / sub-$5M-ADV names are excluded by the
   tradeability floor, and the literature puts short-horizon reversal there —
   though that is also where cost is worst, and the repo's non-survivor study
   already found the tail *worse*, not better.
4. **A stress-conditioned version.** Nagel (2012) ties reversal returns to
   liquidity-provision compensation that spikes with VIX. This study did not
   condition on the market-wide liquidity regime; a VIX/dispersion-gated variant
   is a genuinely different construction.

## §6 What to do instead

Nothing here is worth building today. The one honest follow-up with real option
value is **(1)** — and it is a data-acquisition question, not a modelling one.
Until a per-trade tape and NBBO exist in this repo, the discriminator the
candidate is built on cannot be measured properly, and every OHLCV-grade proxy
for it has now been tested and come back null.

---

**Sources.** Savor, *Stock Returns after Major Price Shocks: The Impact of
Information* (JFE 2012); Corwin & Schultz (JF 2012); Holden & Jacobs (2014) on
high-low spread bias; Nagel, *Evaporating Liquidity* (RFS 2012). In-repo priors:
`scripts/validate_reversal.py`, `scripts/validate_reversal_nonsurvivor.py`,
DO_NOT_REBUILD rows PSS-SR1/SR2/SR3.
