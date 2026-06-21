# Strategy Lab — momentum / technical / mean-reversion research harness

A reusable, **honest** backtest harness that tests a library of buy-in-timing and
stock-selection strategies, records per-strategy results, and combines only the
genuine survivors into deployable engines. Built to advance two distinct goals:

* **Short-term → buy-in TIMING** (when to enter a name we already want).
* **Medium/long → SELECTION & swing** (which names, and the trend/risk state).

Everything runs on `engine/validation.py`'s honest-validation toolkit: turnover-cost
backtests, Deflated Sharpe (multiple-testing haircut), Newey-West HAC t-stats,
Benjamini-Hochberg FDR across the strategy family, block-bootstrap CIs, split-half
robustness. Results are recorded in `data/strategies/strategy_lab.json` +
`reports/strategy-lab.md`.

## Files

| File | Role |
|---|---|
| `engine/strategy_signals.py` | Pure, causal signal library (17 time-series strategies + composites). `signal(df)` (continuous, bullish-oriented) and `position(df)` (long/flat [0,1]). |
| `scripts/strategy_lab.py` | The evaluator. Per-name tradable backtest + per-name IC + entry-quality (MAE) + cross-sectional rank-IC + the combination validation. Writes the scorecard + report. |
| `engine/strategy_composite.py` | The deployable distillation: per-name entry-timing gauge, exit/extension gauge, trend gate, plain verdict. Feeds the score + the Mastermind emit. |
| `scripts/build_strategy_composite.py` | Standalone emit → `site/strategy/composite.json` (schema `strategy_composite.v1`). |

Run (worktree cwd, scipy main-checkout venv):
```
.venv/bin/python -m scripts.strategy_lab              # full scorecard
.venv/bin/python -m scripts.build_strategy_composite  # the per-name emit
```

## Universe & the survivorship caveat (read first)

The price panel is `data/stocks/*` — **114 currently-listed mega-caps**, median ~42yr
history, clean adjusted OHLCV+volume. Because the names all *survived*, any long-biased
or cross-sectional result is an **optimistic bound / CONTEXT, not proven alpha**. This
is stamped on every output. Time-series *timing* edges (entry overlays) are far less
exposed to survivorship than cross-sectional *selection* edges, which is reflected in
how much weight each is given downstream.

## Methodology

**Time-series strategies** (per name) are scored three honest ways:
1. **Tradable backtest** — `position(df)` → long/flat alloc, `backtest_core` net of a
   5bps one-way cost, aggregated to one equal-weight portfolio return → Sharpe / CAGR /
   MaxDD vs an always-invested benchmark, **DSR** (n_trials = full family ≈ 23),
   block-bootstrap Sharpe CI, split-half consistency.
2. **Per-name IC** — Spearman of the signal vs the horizon-h forward return, sampled
   **non-overlapping**, t-tested **across names** (each name = one observation —
   conservative; no cross-name-correlation inflation).
3. **Entry quality** — forward max-adverse-excursion on signal-fire days vs all days
   (the drawdown / capital-efficiency lens — entry timing is a *risk* lever).

**Cross-sectional strategies** — monthly rank-IC (HAC-t, BH-FDR) + a long-only
top-tercile vs equal-weight portfolio.

### Honest taxonomy of verdicts
* **ENTRY-SIGNAL (predictive timing overlay)** — short-horizon signal whose cross-name
  forward-return IC is significant & positive. Buying ON the signal beats buying on an
  arbitrary day. An **overlay** (better fills, shallower entry drawdown), *not* a
  standalone system — most such rules sit in cash too often to beat always-invested
  survivors.
* **TRADABLE STANDALONE** — the long/flat rule beats always-invested on net Sharpe and
  survives DSR + bootstrap + split-half. (None did — stated plainly.)
* **RISK-CONTROL** — matches buy&hold Sharpe while materially cutting drawdown / time in
  market (the validated de-risking role of a trend gate).
* **NO EDGE** — neither.

## Findings (latest run — see `reports/strategy-lab.md` for the live table)

**Buy-in TIMING — a real, robust edge.** Six oversold mean-reversion entries are
FDR-significant with large cross-name IC t-stats:

| strategy | horizon | IC t (across names) |
|---|--:|--:|
| RSI(2) oversold in uptrend | 5d | **9.9** |
| Stretch-below-20dma reversion | 8d | 6.1 |
| RSI(14)<35 buy-the-dip | 10d | 5.4 |
| Pullback-from-20d-high reversion | 10d | 4.9 |
| Down-day fade in uptrend | 3d | 4.8 |
| Bollinger %b lower-band reversion | 10d | 4.7 |

As standalone long/flat rules they *trail* always-invested (they sit in cash); their
value is **timing the entry of a name already selected**.

**Medium-term TREND — validated RISK CONTROL.** Above-200dma / vol-targeted / 12-1 /
MA-cross trend states match buy&hold Sharpe (~1.06) while cutting MaxDD from **−0.50** to
**−0.14 … −0.30**. The capital-efficiency lever, not a return lever.

**Breakout / acceleration (Donchian, NR7, accel-mom) — NO EDGE** on this universe;
short-horizon mean reversion dominates breakout in liquid mega-caps.

**Cross-sectional SELECTION — modest, survivorship-biased CONTEXT.** Only 12-1 momentum
(IC 0.035, t_hac 3.9) and residual momentum (0.019, t 1.9) clear FDR; 52w-high and
low-vol are flat/negative here. Consistent with the prior "modest_or_none" verdict.

## Combined engines (from the survivors)

* **Entry-timing composite** — blends the five FDR-significant oversold legs, uptrend-
  gated. Composite IC **0.039 (t≈9.7)**, beating the best single leg (+0.004 lift via
  diversification). Top-vs-bottom oversold-quintile **+0.39%/5d** forward spread. The
  trend-gate × oversold combination cuts MaxDD to **−0.16** (vs −0.50 always-in).
* **Selection composite** — 12-1 + residual momentum ≈ 12-1 alone (IC 0.035). Modest,
  survivorship-biased; **CONTEXT only, never sizes alone.**

## Relationship to the production engines (already on main)

This is the **research / validation layer**. The production stock engine already ships
the institutional levers this harness validates, via two merged PRs:

* **PR #350** — two-gauge stock engine (conviction × entry) + the cycle-top fix. The
  *entry-timing gauge* (`engine/entry_signal.py`) and the higher-timeframe topping veto
  in `engine/cycles.py` (`rollover_veto`) are the production homes of the entry-timing /
  "don't chase a topping name" findings here.
* **PR #354** — portfolio-edge layer: **vol-managed sizing** (`engine/risk_sizing.py`,
  the two-layer Moreira-Muir sizer) + dispersion regime + a decorrelated composite. This
  is the production home of the vol-managed sizing result (Sharpe ↑, drawdown ↓) measured
  by `eval_vol_managed` here.

So this harness's job is **reproducible, honest validation** — it independently re-derived
the same conclusions (a strong cross-check), and it is the place to test *new* candidate
strategies before they ever touch the live score. `engine/strategy_signals.py` is the
strategy library under test; `engine/vol_managed.py` is the backtest-only vol-target helper
(production sizing = `engine/risk_sizing.py`).

## Honest bottom line

On a survivorship-biased mega-cap universe, the durable, real edges are **(1) short-term
mean-reversion ENTRY timing** and **(2) trend-state RISK CONTROL** — exactly a *buy-in
timing* lever and a *drawdown* lever. There is **no standalone return-alpha** here, and
cross-sectional selection is modest context. The system is wired to use these for what
they are: better entries on names already chosen, and de-risking — not as a magic
return engine. That is the honest improvement to both the individual stock scores and
the Mastermind toolkit.
