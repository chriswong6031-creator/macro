# Entry-Quality score — research & validation

**Question (user):** a per-stock/ETF score for *how much conviction there is in
buying right now*, multi-faceted — weighting how close we are in **time** to the
momentum cross (about-to-cross → just-crossed, decaying as days pass) and how
close price is to the **bottom**, rewarding a clear bottoming process that is
arching up (accumulation). Mirror for tops. "Primary goal: the safest and best
time for entry, at the relative price and time to when the bottom occurred."

**Method.** Walked 110 deep-history names (`data/stocks/*`, ~14y, all regimes) at
a weekly step on a trailing 600-day window — the same machinery `calibrate_ladder`
uses — recording per-sample features + forward 21/42/63-day outcomes:
endpoint **return**, **MAE** (max adverse excursion = the drawdown you sit
through), **MFE** (max favorable excursion). 54,030 samples.
Code: `scripts/research_conviction.py`.

## What the levers actually do (each tested in isolation)

| Lever | Result |
|---|---|
| **Price proximity to the cycle low** | **Dominant & robust.** Avg forward 63d drawdown: **−7.0%** at 0–3% above the low → **−8.8%** at 12–25% → **−10.5%** when chasing (>25%). Hit-rate and reward:risk shape (median MFE/\|MAE\|) also best near the low (1.31 vs 0.85 at +5–10%). Monotone across 21/42/63d. |
| **Freshness of the momentum cross** | **Real, mainly as a staleness penalty.** Crosses >20 trading days old are the worst band; fresh-to-~2-weeks is fine; very fresh is best at 63d. Decay should be gentle, not a sharp "today vs 5 days ago" cliff. |
| **Bottoming "arch" (10d MA already turning up)** | **Naively underperforms** — by the time the MA is visibly rising you're later and higher above the low (the proximity penalty). Use swing-low / curl as a *knife-catch filter* (proof the low is holding), **not** a "wait for full confirmation" gate. |
| **Regime (higher-TF trend)** | With-trend entries carry **smaller drawdowns**; its value here is risk, not hit-rate. |

## The decisive, humbling finding

A "buy near the low + fresh" score **does not predict higher forward return** —
it *anti-correlates* (rank-corr −0.05 to −0.14), **even inside confirmed
uptrends**. Return is U-shaped: the most *extended* (momentum) names return the
most. This is ordinary momentum/trend-persistence beating short-horizon
mean-reversion, and it matches this project's own ladder calibration note ("these
states don't beat buy-and-hold; their value is risk placement").

**Conclusion: the idea works — as a RISK / ENTRY-TIMING-QUALITY score, not an
alpha leaderboard.** The single thing near-the-low + fresh reliably delivers is a
**tighter, lower-drawdown entry** (the user's literal "safest entry, relative to
the bottom"). It must be labeled and calibrated as such, with the explicit caveat
that it does not forecast return.

## Shipped design (`engine.cycles.entry_quality`)

Signed −100..+100; **buy-setup positive, sell/exit-setup negative**. The **sign is
anchored to the ladder state** (`_EQ_BULLISH` / `_EQ_BEARISH`) so it can never
contradict the displayed call. Magnitude =
`gate × (0.55 + 0.45·hold) × (0.52·proximity + 0.30·freshness + 0.18·momentum)`:

- **proximity** — hump peaking 0–3% above the pivot (mirror: below the high for
  shorts), decaying outward, discounted once the pivot breaks;
- **freshness** — flat for ~12 days after the cross, decaying to 0.35 by ~30d,
  with anticipation credit before the cross;
- **hold** — swing-low / above-10dMA / 10dMA-rising = evidence the low is holding
  (knife-catch filter), as a 0.55–1.0 multiplier;
- **gate** — bull 1.0 / neutral 0.8 / counter-trend 0.45; failed-cycle ×0.3.

Calibration of the engine score (drawdown by buy-setup band) is written to
`data/regime/entry_quality_calibration.json`. **UI: concise badge + one-line
honest tooltip** (no full table on the page, per product decision).

What would change it: a different universe/period (small-caps, mean-reverting
assets, or a bear-dominated sample) could shift the trend-vs-mean-reversion
balance; re-run the walk before trusting the bands elsewhere.
