# Liquidity × Cycle-Ladder — measured record

**Question.** Does conditioning the per-stock **cycle-ladder BUY states** (FRESH BUY +
TURN SIGNALED — the "BUY ZONE" / "BOTTOMING" calls users act on) on the US
**net-liquidity regime** (expanding vs contracting) improve forward odds? This is the
"generalize the validated macro/liquidity overlay to the per-stock ladder" win — the
overlay already drives `engine/playbook.py:exposure_dial` but was **absent** from
`engine/cycles.py` (the ladder) and the stock/sector pages.

**Method.** `scripts/research_liquidity_ladder.py` re-runs the *actual* engine ladder
(`engine.cycles`) over the cross-asset parquet panel — the same walk-forward as
`calibrate_ladder` — and tags every evaluation with the net-liquidity regime a trader
actually had that day. Net-liquidity is reconstructed and **lagged 3 business days**
exactly like `engine.regime.liquidity_overlay` (`scripts/research_liquidity_gate.net_liquidity`),
so the label is the de-biased one the engine ships. Regime = 20-day RoC of
`WALCL/1000 − RRP − TGA/1000` vs ±$25bn (the `config.engine.liquidity` thresholds).
Judges BOTH forward return (hit-rate / avg) AND forward drawdown (the D43 lens), at
21d and 63d. Cache: `/tmp/research_liq_ladder.parquet` (122,087 evaluations, 141
instruments, panel 1963→2026; net-liquidity labelled 2010→).

## Result — CONFIRMED (an odds + drawdown edge, not a point-return promise)

Buy setups (FRESH BUY + TURN SIGNALED), liquidity **expanding vs contracting**:

| Horizon | exp hit | neu hit | con hit | exp−con hit | exp bad-dip(p10) | con bad-dip(p10) |
|--------:|--------:|--------:|--------:|------------:|-----------------:|-----------------:|
| 21d     | 61.2%   | 58.5%   | 54.8%   | **+6.4pp**  | −8.9%            | −11.2%           |
| 63d     | 66.2%   | 63.0%   | 58.0%   | **+8.2pp**  | −16.2%           | −18.5%           |

- **Monotone** dose-response (expanding > neutral > contracting) at both horizons.
- **Per state** holds: FRESH BUY 62.1% vs 53.9% (21d); TURN SIGNALED 60.8% vs 55.1%.
- **Split-half** (both halves positive): pre-2019 +2.7pp / post-2019 +9.5pp (21d);
  +5.3pp / +10.4pp (63d). Stronger post-2019, never inverts.
- **2020–21 QE excluded** (single-episode artifact test): +7.3pp (21d), +5.6pp (63d) — survives.
- **By class:** equity robust (+6.7pp / +8.1pp). Crypto thin (n≈75) but agrees on the
  honest 63d/drawdown read (73% vs 49% hit; far deeper dips in contraction — "BTC tracks
  net-liquidity"). Commodity weak/in-family (+1.4pp / +2.3pp), as expected (supply-driven).

## Honesty framing & the effective-N caveats (4-agent adversarial verify)

It is an **ODDS edge**, never a point-return-magnitude promise. One macro series ⇒ the
honest effective N ≈ #liquidity **episodes**, NOT 122k asset-days. The per-row headline
above (+6.4pp/21d, +8.2pp/63d) overstates significance because cross-asset same-week rows
and overlapping forward windows are heavily correlated. Collapsing to a defensible unit:

- **21d hit edge — REAL but borderline, carried by consistency.** At calendar-month-dominant
  units (N=194) +6.2pp, perm-p=0.013 (significant); at true liquidity-episode units (N≈72)
  +8.3pp, Welch t=1.88 / perm-p≈0.06 (just above 0.05). What carries it is **sign-consistency,
  not the p-value**: leave-one-year-out 17/17 positive, leave-one-episode-out 72/72 positive.
- **63d hit edge — largely a clustering artifact.** At episode level it collapses to ~0
  (median 0.662 vs 0.658, t=0.61, p=0.54). The big per-row 63d number is overlapping 3-month
  windows within an episode. **Do not lean on 63d hit-rate.**
- **Drawdown edge — solid at 21d, not 63d.** Episode-level 10th-pctile dd is shallower for
  expanding at both horizons, but only the 21d bad-case dd survives block-bootstrap (CI
  [+0.3,+4.2pp]); the 63d dd CI crosses zero.
- **Binary split > graded dose-response.** exp>neu>con is clean only in the pooled sample;
  per-era the neutral bucket is noisy (strict monotonicity in 1 of 4 sub-periods). So the
  shipped lever is a **binary** tailwind/caution, neutral = no nudge — not a graded scale.
- **Not an era proxy / genuine headwind.** The edge is positive in all four sub-periods
  (largest in the *earliest*, 2010-14 — so not a post-2019 artifact), contraction sits below
  the all-buy baseline on hit AND has deeper dd in every era, and it is broad cross-sectionally
  (≈80% of instruments positive, survives dropping the top-5 contributors). 95%+ equity.

**Net:** wire it, framed as a **near-term (21d) odds + drawdown tilt** — which is exactly
what the shipped `liq_line` says ("~+6pp hit at 21d … an odds edge, not a bigger expected
gain"). Consistent with last session's verdict that the same factor is real/robust/orthogonal
but an odds edge (episode-unit Welch t≈0.79). See [[macro-dashboard-project]].

## Wiring (what shipped)

Surfaced as a **liquidity-context line** on every ladder state and a **conviction-score
nudge on buy setups only** (expanding tailwind, contracting caution) — *without* changing
the calibrated internal LADDER state keys, so `data/regime/ladder_calibration.json` keeps
matching (same pattern as the translation ±5/−10 and early-bull +6/+12 nudges). The live
label comes from `data/regime/latest.json['liquidity_overlay']`, passed into `analyze()`
from `build_site` (sector pages) and `build_stock_library` (stock search). Crypto (-USD)
gets the same US label; China builds are untouched (default `None`).

Re-run the report (instant, from cache): `.venv/bin/python -m scripts.research_liquidity_ladder --report-only`
