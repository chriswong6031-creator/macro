# Signal Track-Record Logger & Audit

> **Read `CHARTER.md` first.** This is **measurement, not modelling.** It grades the
> *already-deployed* MTF buy-filter signals on **forward data** (CHARTER §3: out-of-sample /
> forward generalization is the only verdict). It **does not** change `engine/signal_quality.py`
> and it is framed entirely on **drawdown / entry-quality**, never return-alpha (CHARTER §2b, §4).

## Why this exists

The buy-filter (`take` vs `block` on `buy`/`rebuy` markers) was *designed* on Tencent/BABA and
validated held-out across the 110 US names (CHARTER §5). That validation was a one-shot backtest.
This logger turns it into a **standing forward track record**: every signal the engine emits is
written down on its date, then **graded forward** as price matures. The audit then asks the only
question that matters — *does the filter's verdict actually correspond to better forward drawdown
outcomes, and where is it blind?*

This is a **microscope + regression test** (CHARTER §6), not a verdict machine. Its job is to
**surface regime-/archetype-dependent blind spots** as concrete topics for the brainstorm/tuning
sessions.

## Inputs (read-only)

- `site/signals/<TICKER>.json` — per-ticker chart markers (the §7 contract). The full marker history.
- `data/signal_archive/mtf_signals_latest.json` — brain leaf; provides `asof` (the "as-of" stamp
  used as each row's `first_seen_asof`) and per-ticker current `state`/`above200`/`weekly_bull`.
- `data/stocks/<TICKER>.parquet` — daily OHLC (`close`/`high`/`low`/`volume`). **The only price
  source** for forward returns, forward drawdown, the regime proxy, and the vol/archetype features.
  (Tracked in git, so this runs self-contained.)

## Output

`data/signal_archive/track_record.parquet` — **append-only, key-deduped on `(ticker, date, type)`.**
Git-ignored (a churning research log, not a deployed artifact). Created on first run; grows on each.

### Which markers are logged

- `buy` / `rebuy` with `quality ∈ {take, block}` → logged (these carry the filter verdict).
- `sell` / `cut` → logged with `quality = null` (needed to resolve each entry's exit).
- `buy` / `rebuy` with `quality == "pending"` → **skipped** (the engine itself says it cannot confirm
  the last 1–2 bars yet; logging it would be repaint bait). It is logged later, once a subsequent
  build resolves the same `(ticker,date,type)` key to `take`/`block`.
- `risk_flags` (a separate date list, not a marker) → **not logged** (display-only tail-risk layer).

### Schema (one row per logged marker)

Immutable identity + entry-time features (frozen once written — **append-only**, first-observed wins):

| column | type | meaning |
|---|---|---|
| `ticker` | str | |
| `date` | str `YYYY-MM-DD` | the marker's 3D bar date (entry/exit date) |
| `type` | str | `buy` / `rebuy` / `sell` / `cut` |
| `quality` | str/null | `take` / `block` for entries; null for sell/cut |
| `reason` | str/null | engine's reason text for entries; null for sell/cut |
| `entry_price` | float | daily `close` on `date` (snapped to nearest prior bar if needed) |
| `regime_at_entry` | str | `bull` / `bear` / `choppy` / `unknown` — **forward-only** proxy (below) |
| `above200_at_entry` | bool/null | `close > SMA200` as of `date` (regime input) |
| `sma200_rising_at_entry` | bool/null | `SMA200[t] > SMA200[t-20]` as of `date` (regime input) |
| `vol_annual_at_entry` | float/null | trailing-63d daily-return σ × √252 as of `date` (archetype input) |
| `er_at_entry` | float/null | Kaufman Efficiency Ratio (20-bar) as of `date` (CHARTER-blessed primitive) |
| `first_seen_asof` | str | the `mtf` `asof` when this row was first written (**provenance / forward honesty**) |

Maturation columns — **NULL until enough forward data exists, then filled once and frozen:**

| column | type | meaning |
|---|---|---|
| `fwd_ret_20/60/180` | float/null | `close[t+H]/entry − 1`, H in **trading days** on the daily series |
| `fwd_price_20/60/180` | float/null | `close[t+H]` |
| `fwd_mdd_20/60/180` | float/null | **forward max drawdown from entry** `min(0, min(close[t+1..t+H])/entry − 1)` (≤0; floored at 0 — a trough above entry is not a drawdown) — *the §3 metric* |
| `trade_mae` | float/null | **held-trade max adverse excursion** `min(0, min(close[t+1..exit])/entry − 1)` (≤0; entry→its exit, or →latest if still open) — *the trade-level §3-faithful drawdown* |
| `outcome` | str/null | `win` / `loss` / `still_held` (entry rows only; trade-level: entry→next exit) |
| `exit_date` | str/null | date of the next `sell`/`cut` after this entry |
| `exit_type` | str/null | `sell` / `cut` |
| `exit_price` | float/null | `close` on `exit_date` |
| `trade_ret` | float/null | `exit_price/entry − 1` (realized entry→exit return — **secondary** context, not the verdict) |
| `last_backfill_asof` | str/null | provenance: `asof` of the run that last filled a maturation column |

## Design choices (and why) — honoring the CHARTER

- **Forward-only regime proxy.** `latest['regime']` does not exist on the `mtf` leaf, and the leaf's
  `above200`/`weekly_bull` are *current*, not as-of the historical entry — using them would **leak the
  future**. So `regime_at_entry` is reconstructed from the daily close **using only data ≤ `date`**:
  `bull` = above SMA200 **and** SMA200 rising; `bear` = below **and** falling; `choppy` = mixed;
  `unknown` = <200 bars of history. Filtered/forward-only, confirmed — no repaint (CHARTER §3).
- **Drawdown, not return, is the verdict.** Maturation stores `fwd_mdd_*` and `trade_mae` precisely so
  the audit can ask the §2b question. `fwd_ret_*`/`trade_ret` are kept only as **secondary** context and
  are never the pass/fail metric (CHARTER §4 tripwire #1).
- **Trade-level + fixed-horizon, both.** `trade_mae`/`outcome` are the §3-faithful *trade simulation*
  (enter on signal → exit on the next sell/cut). `fwd_*_{20,60,180}` are the fixed-horizon supplement,
  clearly labelled secondary (the old `_bt_signals.py` "state forward-return" lens is **not** the verdict).
- **Archetype via a persistent property.** `vol_annual_at_entry` (and `er_at_entry`) read volatility /
  efficiency — CHARTER-blessed persistent properties (§2e). The audit buckets by **cross-sectional
  percentile** (terciles), never absolute thresholds (CHARTER §3).
- **All close-based** for internal consistency with the close-driven signal (`signal_quality` reads
  `close`). Horizons are **trading days** on the daily bar series.
- **Price-store honesty (not strictly point-in-time).** `data/stocks` `close` is split- AND
  dividend-back-adjusted total-return (verified empirically). Splits are a constant multiplicative
  factor that **cancels in every ratio** we compute (entry_price, fwd_ret/fwd_mdd/trade_ret,
  price-vs-SMA200, pct_change vol, the ER ratio are all scale-invariant) → leak-neutral. The residual
  is **dividends**: an interim dividend rebases the entry-leg bar but not the t+H bar, so forward
  drawdowns are total-return-with-hindsight, with a bias bounded by interim dividend yield (typically
  <1% over 60d). It nudges drawdown *magnitudes* slightly, **not** the take-vs-block *direction*.
  Feed an unadjusted/as-of price series to remove it entirely. (Documented in the module docstring.)
- **Append-only & idempotent.** Re-running with unchanged inputs is a no-op. Identity/entry columns are
  frozen on first write (first-observed wins — the honest record of what the engine asserted at the time;
  a later repaint of the same key is counted, not overwritten). Only NULL maturation columns get filled
  as data matures. Safe to re-run any number of times.
- **`first_seen_asof` separates backfill from live-forward.** The first run backfills the entire marker
  history with `first_seen_asof = today`; rows whose `date` ≪ `first_seen_asof` are *historical backfill*
  (out-of-sample of the filter's **design**, but data that already existed), while rows whose `date ≈
  first_seen_asof` are captured **strictly live-forward**. The audit can restrict to the strict set.

## Components

- `engine/track_record.py` — pure, importable logic + `update_track_record(...)` + CLI.
- `scripts/build_track_record.py` — thin runner, repo-relative defaults; **never breaks a build** (logs
  and exits 0 on internal error). Intended cadence: run after `build_signal_quality.py`.
- `research/signal_engine/track_record_audit.py` — the reader/audit (below). Writes
  `research/signal_engine/_track_record_audit.md` (scratch, git-ignored).
- `tests/test_track_record.py` — idempotency, key-dedup, append-only freezing, maturation,
  no-look-ahead on the regime/vol features, pending-skip.

## Audit questions (the reader)

All framed on **drawdown / entry-quality**, with small-sample (`n`) warnings and numpy-only bootstrap
CIs (no scipy dependency). `still_held` rows are excluded from realized-outcome stats but kept for
`fwd_mdd` stats where matured.

- **(a) take vs block** — do `block` entries really sit in **worse forward drawdowns** than `take`?
  Compare `fwd_mdd_60` and `trade_mae` distributions for `quality=take` vs `block` across `buy`+`rebuy`;
  report median/mean, tail rate (share with drawdown < −15%), and a bootstrap CI on the gap. The filter
  earns its keep iff `take` drawdowns are **shallower** than `block`.
- **(b) per-regime** — same comparison split by `regime_at_entry ∈ {bull, bear, choppy}`. Surface cells
  where `block` fails to avoid drawdown or `take` still draws down deeply — those are **blind spots**.
- **(c) per-archetype** — bucket by `vol_annual_at_entry` cross-sectional tercile (low-vol grinder vs
  high-beta). Same take-vs-block drawdown gap per bucket; surface archetype blind spots.
- **Output ends with `TOPICS FOR TUNING / BRAINSTORM`** — the weakest (regime × archetype) cells, phrased
  as concrete questions for the next session. This is the deliverable's *point*.
