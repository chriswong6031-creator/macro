# `walk_forward.py` — the validation harness (how to use it)

> Read `CHARTER.md` first. This harness enforces the charter's validation discipline
> (§3) and tripwires (§4). **It judges entry signals the way the owner actually trades —
> WITH A STOP — on the STOP-OUT / FAKEOUT RATE, never on total return and never on the
> max drawdown of a position carried with no stop.** Total return and both max-DD flavours
> (`strat_max_dd`, `nostop_max_dd`) are carried only as labelled **context** fields and can
> never enter a verdict.

It is **one reusable harness, built once**. Don't fork it per experiment — point it at a
new signal callable.

---

## Why this exists — the metric correction (read this)

The owner trades with a **stop-loss** (default ≤ −5%). A *bad entry* is therefore one that
gets **faked out and stopped out** before the move it was trying to catch. So the one
metric that measures entry quality is the **stop-out rate**: the fraction of taken entries
that hit the stop. **Lower is better.**

A prior harness scored the **loose-hold max drawdown** of a position carried with *no
stop* (the "−23.7% → −15.5% max-DD" headline). That number conflates *entry quality* with
*exit policy* — it is the drawdown of a strategy nobody runs. Two entries with identical
loose-hold max-DD can stop out at completely different rates, and the owner only ever
experiences the stopped version. So every trade is simulated **as traded, with the stop**:

```
enter on the (leak-free) signal
  -> exit at the ≤ stop_pct stop  OR  the validated exit signal (CS / revSell), whichever first
  -> re-buy on the next reversal signal
```

and we judge on **stop-out rate + the realised per-trade loss distribution under the stop
+ entry efficiency**. `captured` (total return), `strat_max_dd` (the with-stop strategy
equity drawdown) and `nostop_max_dd` (the retired no-stop loose-hold drawdown) survive only
as labelled context. Passing any of them as the verdict `metric=` raises `ValueError`.

---

## Quick start

```bash
# Run the gold-standard test: does the validated buy-filter cut the STOP-OUT rate
# vs raw confluence buys, across the 110 US names in data/stocks/?
python3 research/signal_engine/walk_forward.py --gold
```

It prints a raw-vs-filtered table on every metric, the % of names whose stop-out rate
improved, the walk-forward OOS read, the kill-rule verdict, and a non-tradeable
**attribution** line (selection vs entry-timing). See "The gold-standard finding" below
for how to read it.

---

## The signal-callable contract

You give the harness a **signal callable**: `fn(close, high=None, low=None)`. The whole
trade sim runs on the **daily grid** (so the stop is checked every day); `close/high/low`
for the stop always come from `panel`, never from your callable. Two return shapes:

**Simple mode** — return a daily boolean **buy** series:
```python
def my_buy(close: pd.Series, high=None, low=None) -> pd.Series:   # bool, daily index
    ma = close.rolling(50).mean()
    return (close > ma) & (close.shift(1) <= ma.shift(1))
```
The harness pairs your daily buy events with the **default confluence exit**
(`default_confluence_exit` = the 3D `CS|revSell` mapped leak-free to daily) and the −5%
stop.

**Rich mode** — return a daily DataFrame with `buy` (and optionally your own `exit`):
```python
def my_signal(close, high=None, low=None) -> pd.DataFrame:
    return pd.DataFrame({"buy": daily_buy_bool, "exit": daily_exit_bool}, index=close.index)
```

### Multi-timeframe? Use the leak-free cross-grid helpers — or you WILL leak

A TF bar's close is only *known* on the **last daily date in its bin**. `resample("3B")`
labels the bin's **left edge**, which sits **2–4 calendar days before** that close — so
acting on the label date is a multi-day lookahead. Map by the true known date and fire on
the **first daily bar strictly after** it:

```python
from walk_forward import tf_bars, _daily_events_after
bars, known = tf_bars(daily_close, 3)               # 3-business-day bars + true known dates
buy_daily = _daily_events_after(known[buy_on_3d_bars].values, daily_close.index)
```

`_daily_events_after` uses `searchsorted(..., side="right")` → strictly after the known
date (a known date is itself a real daily close; you can only act on the *next* bar).
This is the exact mapping the gold path uses, so a 2D trigger and a 3D trigger compare
apples-to-apples.

---

## Running it

```python
from walk_forward import walk_forward, _load_panel

panel = _load_panel()                          # {ticker: DataFrame[close,high,low,volume]}
res = walk_forward(
    my_signal, panel,
    cfg={"train_len": 378, "test_len": 189, "step": 189,
         "purge": 5, "embargo": 5, "stop_pct": -0.05},   # window lengths in DAILY bars
    baseline_fn=baseline_signal,               # optional — the simpler rule you must beat
    n_trials=1,                                # how many configs you searched (deflates the bar)
    metric="stop_out_rate",                    # the verdict metric (default)
)
```

> The verdict metric is **risk-only**. Passing `metric="captured"`, `"strat_max_dd"` or
> `"nostop_max_dd"` raises `ValueError` — the harness refuses to render SHIP/REJECT on total
> return or on the max-DD metrics this harness exists to retire. Valid verdict metrics:
> `stop_out_rate` (default), `avg_loss`, `worst_loss`, `expectancy`, `win_rate`, `entry_eff`.

Returns `{run_id, config, by_ticker, pooled, overfit_flags, dropped, ...}`:

- `by_ticker[T] = {"treat": {...}, "base": {...}}`, each with **three views**:
  - `full` — entire post-`SINCE` (default 2010-01-01) sample.
  - `oos`  — walk-forward **out-of-sample**, stitched over purged/embargoed test windows.
            **This is the generalisation read that decides ship/reject.**
  - `is`   — the in-sample burn-in region (entries before the first OOS window).
- `pooled[view]` — cross-sectional **percentiles** (p10/25/50/75/90 + mean) of the metric
  for treatment and baseline, plus **`frac_improved`** = % of *comparable* names (both arms
  traded) that improved, and `treat_means`/`base_means` for the other risk metrics.
- `overfit_flags` — IS-vs-OOS decay + the kill rule (below).
- `dropped` — `{ticker: reason}`. Expected skips read `skip: ...`; genuine failures read
  `ERROR: ...` and are also printed to stderr, so a real bug never hides as a silent
  undercount.

Every run writes a per-trial JSON log to `data/signal_archive/wf_<run_id>.json`.

---

## The verdict (don't skip this)

The harness pre-commits the charter's kill rule so you can't move the goalposts later:

```python
res["overfit_flags"]["kill_rule"]
# -> {"verdict": "SHIP" | "REJECT — ship the simpler baseline",
#     "frac_improved": 0.54, "min_frac": 0.70, "view": "oos"}
```

- **SHIP** only if ≥ **70%** of held-out names improve on the **stop-based metric
  out-of-sample**.
- Otherwise **REJECT and ship the simpler baseline** (exactly how the regime router was
  killed — §5).
- `n_trials > 1` raises the bar (`deflated_bar`, a deflated-Sharpe-style multiple-testing
  bump) so a lucky best-of-N config can't sneak through.
- `decay_flag = True` warns that IS→OOS improvement dropped sharply (overfit smell).

---

## Metrics (`trade_metrics`)

| key | meaning | role |
|---|---|---|
| `stop_out_rate` | % of trades exited by the stop | **PRIMARY verdict** (lower better) |
| `avg_loss` | mean of losing trades (%) | risk |
| `worst_loss` | worst single trade (%) — can be < stop on a gap-through | risk tail |
| `frac_below_stop` | % of trades whose realised loss beat the stop (gap risk) | risk tail |
| `entry_eff` | median entry position in the forward range (0 = bought the low) | entry quality (lower better) |
| `expectancy` | mean per-trade return (%) | quality |
| `win_rate` | % winning trades | quality |
| `captured` | total compounded return (%) | **context ONLY — never a verdict** |
| `strat_max_dd` | max-DD of the with-stop strategy equity (%) | **context ONLY** |
| `nostop_max_dd` | max-DD of the same entries held with NO stop (%) | **context ONLY — the retired metric** |

Stop fills: a normal intraday touch fills at the stop level; a bar that **gaps through**
(whole range below the stop) fills at the bar high, so the realised loss can exceed the
stop — that's what `worst_loss`/`frac_below_stop` surface. Close-only names fall back to a
close-based stop.

---

## The gold-standard finding (what `--gold` shows)

Run on the validated buy-filter (`buy_filters` / `engine.signal_quality` / `diagnose_v2`)
vs raw confluence buys, 110 US names, −5% stop, full sample:

| metric (full sample) | RAW buys | FILTERED (tradeable) |
|---|---:|---:|
| **stop-out rate %** (PRIMARY, per-name mean) | **39.5** | **38.5** |
| stop-out rate % (trade-weighted pooled) | 39.2 | 37.7 |
| avg loss % | −4.0 | −4.0 |
| worst trade % | −6.5 | −5.4 |
| win rate % | 40.9 | 42.9 |
| trades / name | 49 | 19 |
| _[ctx] with-stop strat max-DD %_ | _−35.9_ | _−24.3_ |
| _[ctx] no-stop loose-hold max-DD %_ | _−40.9_ | _−29.0_ |

- The filter lowers the stop-out rate on only **54%** of names (OOS **51%**) → **kill rule
  REJECT**. The context-only **no-stop loose-hold max-DD reproduces the old win** (−40.9% →
  −29.0%, ~30% shallower) — but that win **does not survive an actual stop**: with the −5%
  stop in place, the stop-out rate barely moves and the per-trade losses are already capped
  for *both* arms (avg ≈ −4.0%, worst ≈ −5 to −6.5% on gap-throughs).
- **Attribution** (a non-tradeable diagnostic the test also prints): the take *subset*
  entered at the raw bar gives **29.4%** (improves 90% of names) — so the filter's
  **selection** genuinely picks lower-fakeout entries. But the only leak-free way to trade
  it is to wait for the reclaim-and-hold confirmation, which buys **~2.4% later/higher**
  (closer to the stop); that timing cost **pays the selection benefit back**, leaving the
  tradeable filter at 38.5%. (Much of the 29.4% is itself look-ahead — `reclaim_and_hold`
  conditions on the next bar being up — which is exactly why it isn't tradeable.)
- **The metric is sensitive, not saturated.** Sweeping the stop, the stop-out rate spans
  59% (−3%) → 39.5% (−5%) → 22% (−8%); an *oracle* entry filter (cheating) drives the −5%
  rate to ~19% on 99% of names. So an entry edge *can* move it — the buy-filter simply
  lacks one once traded leak-free. (The OOS read here measures temporal/regime **stability**
  of a fixed causal rule, not parameter-overfit decay — there is nothing fitted per window.)

**Takeaway for the engine (stop-conditional):** at the owner's **−5% stop**, the buy-filter's
celebrated drawdown win is a *loose-hold artifact the stop already neutralizes*. As an entry
de-faker traded with that stop, it does **not** clear the bar — ship the simpler baseline
(raw confluence buys + stop). The filter is not worthless: it has a real selection edge, a
higher win-rate, and lower loose-hold DD, and it nearly clears the bar at **looser** stops
(the higher entry matters less when the stop is wide). The next move is a **cheaper
confirmation** that captures the selection without buying so high. This is the honest,
as-traded restatement of the headline — and a clean example of the charter's rule that the
metric, not the mechanism, decides.

---

## Rules of the road (charter, condensed)

- Verdict = **stop-out rate out-of-sample**, never total return / loose-hold max-DD.
- **Confirmed, forward-only pivots only** — no smoothed/Viterbi states, no repaint.
- Don't hand-tune thresholds on the test panel; keep the spec tiny (`n_trials`/`deflated_bar`
  guard multiple testing).
- Report **% of names improved**, not a pooled mean.
- Faithful indicator math only: RSI-MACD = `EMA(RSI14,14) − EMA(RSI14,60)`, signal
  `EMA(·,5)`; StochRSI = `SMA(stoch(RSI14,14),3)` then `SMA(·,3)`. **Not** price MACD(12,26,9).
