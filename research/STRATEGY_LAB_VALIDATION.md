# Strategy Lab — cross-sectional backtest & live-model validation

*Built 2026-06-21. Harness: `engine/strategy_lab.py` + `scripts/backtest_strategies.py`.
Artifacts: `data/signal_training/strategies_h{63,21}.json`.*

## What this is

A reusable, point-in-time, sector-neutral / market-neutral forward-IC backtest of a
registry of single-stock strategy legs (momentum, reversal, trend, low-vol, the live
confluence components, and a PIT earnings-surprise leg), measured across three panels
with the repo's honest statistics (Newey-West HAC t, a contiguous sub-period
sign-stability gate, cross-panel sign agreement, a Deflated-Sharpe multiple-testing
gate, and a forward-drawdown test).

The headline result is a **confirmation, not a change**: every robust edge it finds is
*already implemented and PIT-calibrated* in `engine/stock_score.py` (the single-stock
Conviction Profile) and already published in `engine/signal_lab.py`. The independent
re-measurement — different panels, different construction — reproduces the live model's
calibrated parameters, which is strong external validation that the model is honestly
built.

## Panels (all survivorship-touched — see caveats)

| panel | source | names | span | role |
|---|---|---|---|---|
| deep | `data/stocks` | 114 | 1962–2026 (~64y) | length / the statistically meaningful one |
| sp500 | `data/breadth/_closes_cache.parquet` + sp1500 PIT membership | 503 | ~15 mo | breadth, recent — **thin, one regime, do not trust its inflated IC-IR** |
| smallcap | `data/smallcap_breadth/_closes_cache.parquet` | 603 | ~3y | breadth, small-cap |

## Findings (deep panel, sector-neutral, H=63d, n≈767 monthly rebalances)

| leg | family | IC | IC-IR | t_HAC | sub-stable | DSR | verdict |
|---|---|---|---|---|---|---|---|
| ma200_slope | trend | 0.036 | 0.191 | 3.29 | yes | 0.47 | context |
| mom_12_1 | momentum | 0.033 | 0.170 | 3.01 | yes | 0.24 | context |
| volscaled_mom | momentum | 0.031 | 0.165 | 2.92 | yes | 0.20 | context |
| live_rs_crowded | model (penalized) | 0.031 | 0.155 | 2.72 | yes | 0.20 | context |
| rsi_oversold | reversal | 0.021 | 0.126 | 2.81 | **no** | 0.62 | fragile |
| mom_accel | momentum | −0.019 | −0.113 | −2.79 | no | 0.00 | inverse |
| sue | fundamental | −0.004 | −0.034 | −0.33 | no (n=186) | — | no-edge |
| live_macd_pos | model | −0.014 | −0.089 | −2.45 | no | 0.00 | no-edge |

At the **21-day (entry) horizon** the extension proxies invert hard: `live_dist_50dma`
IC-IR −0.206 (t −5.1) and `live_macd_pos` −0.171 (t −4.2) — extended / MACD-hot names
pull back short-term — while pure `mom_12_1` stays positive (+0.134, t 3.8).

### The four conclusions

1. **Cross-sectional momentum/trend is the only robust constructive edge** (`mom_12_1`,
   `ma200_slope`, `volscaled_mom`): t≈3 on the 64-year panel, sign-stable across 4
   sub-periods AND across panels. But **it FAILS the Deflated-Sharpe gate** (all legs
   DSR < 0.90 as standalone L/S; best 0.47) — a *context* tilt, not standalone alpha.
2. **Mean-reversion is not a stable cross-sectional edge.** `rsi_oversold`/`rev_1m`/
   `drawdown_252` flip sign across sub-periods (fragile) or across panels
   (panel-artifact). The earlier survivor-panel "mean-reversion dominates" read was a
   **survivorship + market-beta artifact** that vanishes under sector/market-neutral
   construction.
3. **Crowding is a drawdown risk, not a return penalty to remove.** The factor the
   confluence "crowding" term penalizes (`live_rs_crowded`) has positive 63d return-IC
   (+0.031, t 2.7) — but the top-RS decile suffers materially deeper forward drawdowns
   (MAE p10 **−23.7%** vs **−19.5%** for the rest; median −7.2% vs −5.5%). The dock is
   risk-justified; the correct treatment is sizing/entry, exactly as the live model does.
4. **Earnings-surprise (SUE) shows no robust cross-sectional edge here** (no-edge/fragile).

## Cross-check: the live model already encodes all of this

| backtest finding | already in the live model |
|---|---|
| momentum sector-neutral IC ≈ +0.033, DSR-fails, regime-switching | `stock_score._edge_weights`: momentum is a **0.10 context weight**, regime-scaled `_MOM_W_CALM 0.28`/`_MOM_W_STRESS 0.04`; `stock_score.py:81` cites *"sector-neutral rank-IC +0.030 in a calm tape"*; `signal_lab` publishes momentum as *"0.03 — dead"* |
| extended/crowded names → worst forward return + deepest drawdown | `stock_score._stretch_penalty` / `_STRETCH_BLOCK=30%`, documented from *"deep+PIT 18y, top-momentum-decile … >35% above 200dma = worst median fwd return AND deepest drawdowns"* |
| conviction(63d)=trend vs entry(21d)=don't-chase-extension | `stock_score._axis_entry` (`_drawdown_hump`, `_rsi_band`, `_stretch_penalty`, `_EXT_PENALTY` parabolic) is a separate entry axis that caps the verb, never the selection rank |
| SUE collapsed on deep history | `stock_score` keeps SUE as PEAD **context**, not a validated leg (reports/sue-deep-history-phase0.md) |

**Therefore no live-scoring change was made.** Wiring a duplicate momentum/trend leg
into the sector confluence (`engine/technicals.py`) or the single-stock selection axis
would double-count an already-weighted, already-regime-conditioned context signal and
violate the model's no-double-count / no-overfit discipline. The honest action is to
*publish the re-validation* (this note + a `signal_lab` confirmer row) and keep the
reusable harness for future, PIT-clean re-runs.

## Caveats / what would change the verdict

- **Survivorship.** No panel folds in delisted names; the deep panel is 114 survivors.
  The delisted-aware deep PIT matrix (`_closes_deep.parquet`) is **not built here** and
  the fetch is network-blocked (Yahoo 429), so the DSR gate runs on the survivor panel.
  The true ship-gate remains `scripts/conviction_v2_measure --pit` + `scripts/validate`
  on a delisted-aware universe.
- **Static sector labels.** `sector_demean` uses current GICS labels for historical
  dates (slow-moving; a small known bias on the sector-neutral column only).
- **Multiple testing.** ~21 legs tested; the DSR gate haircuts for this, and the
  sub-period + cross-panel gates are the anti-artifact filters.

## Institutional factor-research battery (`scripts/factor_research.py`)

A second, deeper layer on the deep panel. Artifact: `data/signal_training/factor_research.json`.

**IC-DECAY by horizon** (mean rank-IC; the holding-period structure):

| leg | H10 | H21 | H63 | H126 |
|---|---|---|---|---|
| resid_mom | 0.028 | 0.031 | 0.043 | **0.059** |
| mom_12_1 | 0.027 | 0.028 | 0.034 | 0.041 |
| ma200_slope | 0.014 | 0.018 | 0.032 | 0.049 |
| rsi_oversold | **0.050** | 0.038 | 0.029 | 0.013 |

Momentum is a **slow** signal (IC rises to H126 → 3–6 month hold); short-term reversal
is a **fast** signal (peaks at H10 → ~2 week hold). This is the empirical basis for
"select on momentum (long hold), time entry on reversal (short hold)."

**REGIME-CONDITIONAL IC** (H63, split by causal trailing-63d market tape):

| leg | up-tape (n≈579) | down-tape (n≈175) |
|---|---|---|
| mom_12_1 | +0.047 | −0.006 |
| resid_mom | +0.056 | 0.000 |
| ma200_slope | +0.046 | −0.014 |
| rsi_oversold | +0.017 | **+0.071** |

Momentum works in up-tapes and dies/inverts in down-tapes — **empirically validating
`stock_score.py`'s regime-scaled momentum weight (0.28 calm / 0.04 stress)**. Reversal
is the mirror: it works in stress. `resid_mom` does NOT invert in stress (more robust
than raw momentum, per Blitz).

**MARGINAL IC vs the momentum core** (`mom_12_1`): `rsi_oversold` adds the most
independent info (+0.036 — orthogonal reversal axis); `resid_mom`/`volscaled_mom` add
modest independent momentum info (+0.013); `ma200_slope`/`live_rs_crowded` are largely
redundant (+0.006). NOTE — `resid_mom` is the best *standalone* momentum leg, but it is
0.84-correlated to `mom_12_1`, so its *marginal* value is modest: it **refines** the
momentum axis, it does not replace it, and `rsi_oversold` (the reversal axis) adds ~3×
more incremental information than any momentum variant.

**ENSEMBLE** (mom_12_1 + resid_mom + ma200_slope, EW-z): IC-IR 0.21, t 3.82, **positive
in all 5 purged+embargoed CV folds** — but net-of-cost L/S Sharpe **0.31** with **−68%**
maxDD. Combining adds IR over any single leg, yet it remains **context, not standalone
alpha** (consistent with every leg failing the DSR gate).

### Novel idea surfaced (research-only, needs the PIT/DSR gate)

A **regime-switched US selection leg** — momentum in calm tapes, short-term reversal in
stress tapes — is directionally supported by the regime-conditional table (momentum
+0.047/−0.006, reversal +0.017/+0.071). The live model already up-weights the
event/earnings edge in stress for US and uses reversal only for China; this suggests a
measured reversal leg could fill the US stress regime. CAVEATS before any wiring: the
down-tape sample is small (n≈175), `rsi_oversold` was sub-period-FRAGILE in the leg
screen, and the panel is survivorship-touched — so this must clear
`scripts/conviction_v2_measure --pit` + DSR on a delisted-aware universe first.

## Bugs found & fixed (adversarial signal-core audit)

A 7-finder + skeptical-verifier bug hunt over the signal core confirmed **2 real bugs**
(2 medium false-positives were refuted with real-data checks):

1. **Look-ahead in the PIT factor scorecard** — `engine/equity_factors.py::compute_factors`
   pulled the *current* FINRA `short_interest` snapshot at every historical rebalance
   (every other input was asof-truncated), inflating that leg's measured PIT IC / BH-FDR
   survival. **Fixed**: the leg is now dropped for any `asof`-set (point-in-time) run, not
   only `universe=='deep'`; the live `asof=None` page is unchanged. (Composite and
   `factor_series.py` were already unaffected.)
2. **Unit error in the inflation nowcast** — sticky/flexible CPI (FRED M157, already
   "Percent Change at Annual Rate") was **double-annualized**, printing ~46% for a true
   ~3.2%. **Fixed**: `_ann_monthly_pct` → `_smooth_annual_rate` (smooth, no re-annualize)
   across all call sites; chart axis 84 → 10. Regression test in
   `tests/test_inflation_units.py`.

## How to re-run

```
.venv/bin/python -m scripts.backtest_strategies --horizon 63 --subperiods 4   # leg IC screen
.venv/bin/python -m scripts.backtest_strategies --horizon 21 --panels deep,smallcap  # timing
.venv/bin/python -m scripts.factor_research                                   # institutional battery
```
(Use the main-checkout `.venv` — it has scipy; the worktree has none.)
