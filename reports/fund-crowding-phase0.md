# ETF / Fund crowding — fragility tag Phase 0

*`scripts/fund_crowding_phase0.py`. Tests whether a CONTRARIAN crowding/fragility
conjunction earns a place as a subtract-only TEMPER in the per-stock conviction
score, or is display-only context (research/DATA_SIGNAL_EXPANSION_2026.md #6).*

## The question

The proposed live tag is **fragile = high RS-crowding pctile AND high
short-interest pctile AND extended**. Two hard limits on validating it:

1. **Short interest has no point-in-time history.** Our FINRA store keeps only the
   latest snapshot (`data/finra/short_interest.parquet`, one settlement date — the
   collector overwrites, never appends). The SI leg therefore **cannot be
   back-tested at all**, so it can never be a validated sizing leg.
2. **The price panel is shallow** (`_closes()` = 2023-05 → 2026-06, ~777 trading
   days, 1106 names). Enough to *characterize* the price-only core, not to deeply
   validate it.

So Phase-0 tests the only legs we have history for — **crowded (trailing RS
percentile ≥ 80) AND extended (cross-sectional stretch above the 50dma ≥ 80th
pctile & actually above the 50dma)** — against forward outcomes. Weekly
rebalances, PIT features, by-date bucket means (no pseudo-replication),
Newey-West t-stats over the forward overlap, split-half sign check.
Sample 2023-05-09 → 2026-06-12, 92 rebalance dates, ≈69 fragile / 579 rest per day.

Decision rule (conservative, the team's "no unvalidated scoring leg" bar): WIRE a
subtract-only temper only if FRAGILE underperforms the rest on **both** forward
excess return **and** forward drawdown, |t| ≥ 2 on the full sample **and** the
same sign in both halves.

## Result — FRAGILE minus REST (contrarian ⇒ should be negative)

| horizon | metric | FULL | H1 | H2 | FULL·t |
|---|---|--:|--:|--:|--:|
| 21d | fwd excess ret (pp) | +0.10 | −0.12 | +0.32 | +0.20 |
| 21d | fwd max drawdown (pp) | −0.35 | −0.24 | −0.46 | −1.45 |
| 63d | fwd excess ret (pp) | +0.04 | −0.62 | +0.70 | +0.03 |
| 63d | fwd max drawdown (pp) | −0.61 | −0.53 | −0.68 | **−2.32** |

* **Forward return: no edge.** The excess-return difference is ≈0 on the full
  sample and the sign **flips** between halves. Crowding + extension is *not* a
  return-based short signal — leaders mostly keep leading.
* **Forward drawdown: marginal, weak.** Fragile names do carry a slightly worse
  forward drawdown (more downside path), sign-consistent across halves, but the
  magnitude is tiny (≈0.6pp deeper over 3 months) and only the 63d full sample
  crosses |t| = 2 (−2.32; H1 just −1.33). Directional "sharper-pullback" context,
  not a sizing edge.

## Verdict — DISPLAY-ONLY

The decision rule is **not met** (the excess-return leg fails outright; the
drawdown leg is not robust in both halves), and the short-interest leg cannot be
validated at all. So the fragility tag is shipped as a **contrarian risk
annotation on the stock page only** — it NEVER touches the conviction score (cf.
the COT / RS-crowding penalty, which *was* validated before it sized anything).
The existing per-stock score already penalises crowding (RS percentile) and
extension (the `extended` timing tilt), so there is nothing additive to wire.

Shipped alongside: the cross-fund **VIP / overlap** read from the already-collected
13F snapshots (`vip` = # tracked funds currently holding, `ownership_hhi` =
Herfindahl of holders' dollar values, top/avg book conviction) — display context
on the stock page, never scored.
