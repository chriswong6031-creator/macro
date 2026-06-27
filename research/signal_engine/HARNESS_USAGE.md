# `walk_forward.py` — the validation harness (how to use it)

> Read `CHARTER.md` first. This harness is the mechanical enforcement of charter §3
> (metrics + validation discipline) and §4 (tripwires). **It judges signals on RISK —
> max drawdown, shake-outs, loss size, entry quality — never on total return or
> beat-buy-&-hold.** Total return is carried only as a labelled *context* field
> (`captured`) and is never allowed into a verdict.

It is **one reusable harness, built once**. Don't fork it per experiment — point it at a
new signal callable.

---

## Quick start

```bash
# Confirm the harness itself is correct (reproduces the published buy-filter result):
python3 research/signal_engine/walk_forward.py --gold
#   avg maxDD: RAW -23.7 -> FILTERED -15.5  (shallower on 84% of 110 names)   ✅ REPRODUCED
```

If `--gold` ever stops printing `✅ REPRODUCED`, the harness is broken — fix it before
trusting any other result. The gold path mirrors `test_buyfilter.py` exactly (native 3D
grid, enter `CB|revBuy`, exit `CS|revSell`, next-3D-close fills).

---

## The signal-callable contract

You give the harness a **signal callable**. Two shapes are accepted:

**Simple mode** (the default contract — daily grid):
```python
def my_buy(close: pd.Series, high=None, low=None) -> pd.Series:   # bool, daily index
    ma = close.rolling(50).mean()
    return (close > ma) & (close.shift(1) <= ma.shift(1))
```
The harness pairs your daily buy events with the **default confluence exit**
(`default_confluence_exit`, the 3D oscillator SELL/cut mapped leak-free to daily) and
fills on the **next daily close** after each signal. Use this for daily or multi-TF rules.

**Rich mode** (you control the grid, exit, and close — for faithful TF reproductions):
```python
def my_signal(close, high=None, low=None) -> pd.DataFrame:
    # index = your eval grid (e.g. 3D bars); columns: close, buy(bool), exit(bool)
    return pd.DataFrame({"close": ..., "buy": ..., "exit": ...}, index=eval_grid)
```
The trade sim then runs on the grid you returned. This is how `--gold` reproduces the
3D result to the decimal.

### Multi-timeframe? Use the leak-free cross-grid helpers
A TF bar's close is only *known* on the last daily date in its bin (resample labels the
bin's **left** edge). Map by the known date and fill the first daily bar strictly after:
```python
from walk_forward import tf_bars, to_daily
bars, known = tf_bars(daily_close, 2)          # 2-business-day bars + true known dates
events_daily = to_daily(buy_events_on_2d, known, daily_close.index, how="event")
```
This is the same tested mapping `tuning_harness.py` uses, so a 2D trigger and a 3D
trigger compare apples-to-apples.

---

## Running it

```python
from walk_forward import walk_forward, _load_panel

panel = _load_panel()                          # {ticker: DataFrame[close,high,low,volume]}
res = walk_forward(
    my_signal, panel,
    cfg={"train_len": 60, "test_len": 40, "step": 40, "purge": 3, "embargo": 3},  # EVAL-GRID bars
    baseline_fn=baseline_signal,               # optional — the simpler rule you must beat
    n_trials=1,                                # how many configs you searched (deflates the bar)
    metric="max_dd",                           # the verdict metric (drawdown)
)
```

> The verdict metric is **risk-only**. Passing a total-return metric
> (`metric="captured"`/`"cap"`) raises `ValueError` — the harness refuses to render a
> SHIP/REJECT verdict on return (charter §4 #1). Use `max_dd` (default), `avg_loss`,
> `shake_rate`, or `expectancy`.

Returns `{run_id, config, by_ticker, pooled, overfit_flags, dropped, ...}`:

- `by_ticker[T] = {"treat": {...}, "base": {...}}`, each with **three views**:
  - `full` — entire post-`SINCE` sample (this is what reproduces `test_buyfilter.py`).
  - `oos`  — walk-forward **out-of-sample**, stitched over purged/embargoed test windows.
            **This is the generalisation read that decides ship/reject.**
  - `is`   — the in-sample burn-in region (entries before the first OOS window).
- `pooled[view]` — cross-sectional **percentiles** (p10/25/50/75/90 + mean) of the metric
  for treatment and baseline, plus **`frac_improved`** = % of names that improved vs
  baseline. (Percentiles + %-improved, never a lone pooled mean — charter §3.)
- `overfit_flags` — IS-vs-OOS decay + the kill rule (below).
- `dropped` — `{ticker: reason}` for names not evaluated. Expected skips read
  `skip: ...` (thin history, empty signals); genuine failures read `ERROR: ...` and are
  also printed to stderr — so a real bug never hides as a silent undercount.

Every run also writes a per-trial JSON log to
`data/signal_archive/wf_<run_id>.json` (compact per-ticker metrics + pooled + flags + dropped).

> **Rich mode, omitted `exit`:** if a rich frame leaves out the `exit` column, the
> harness supplies the default confluence exit **event-aligned** to your grid (each
> known exit date lands on the first eval-grid bar on/after it) — it does **not** ffill a
> sparse daily series onto a coarse grid (which would silently drop most exits).

---

## The verdict (don't skip this)

The harness pre-commits the charter's kill rule so you can't move the goalposts later:

```python
res["overfit_flags"]["kill_rule"]
# -> {"verdict": "SHIP" | "REJECT — ship the simpler baseline",
#     "frac_improved": 0.80, "min_frac": 0.70, "view": "oos"}
```

- **SHIP** only if ≥ **70%** of held-out names improve on **drawdown out-of-sample**.
- Otherwise **REJECT and ship the simpler baseline** (this is exactly how the regime
  router was killed — §5).
- `n_trials > 1` raises the bar (`deflated_bar`, a deflated-Sharpe-style multiple-testing
  bump) so a lucky best-of-N config can't sneak through.
- `decay_flag = True` warns that IS→OOS improvement dropped sharply (overfit smell).

Helpers if you want them directly: `kill_rule(by_ticker, view, metric, min_frac)`,
`overfit_guard(by_ticker, n_trials, metric)`, `cross_section(by_ticker, view, metric)`.

---

## Metrics (`trade_metrics`)

| key | meaning | role |
|---|---|---|
| `max_dd` | max drawdown of the equity curve (%) | **PRIMARY verdict** |
| `shake_rate` | % of trades that went ≤ −8% underwater before exit | risk / entry quality |
| `avg_loss` | mean of losing trades (%) | risk |
| `expectancy` | mean per-trade return (%) | risk-adjusted context |
| `win_rate` | % winning trades | context |
| `captured` | total return (%) | **context ONLY — never a verdict** (§4) |

---

## Rules of the road (charter, condensed)

- Verdict = **drawdown out-of-sample**, never total return / beat-buy-&-hold.
- **Confirmed, forward-only pivots only** — no smoothed/Viterbi states, no repaint.
- Don't hand-tune thresholds on the test panel; keep the spec tiny (multiple testing
  inflates in-sample winners — that's what `n_trials`/`deflated_bar` guards).
- Report **% of names improved**, not a pooled mean.
- Faithful indicator math only: RSI-MACD = `EMA(RSI14,14) − EMA(RSI14,60)`, signal
  `EMA(·,5)`; StochRSI = `SMA(stoch(RSI14,14),3)` then `SMA(·,3)`. **Not** price MACD(12,26,9).
