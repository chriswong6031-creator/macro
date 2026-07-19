"""scripts/build_tech_lab_data.py — Generate tech_screener.json + tech_lab.json.

Iterates the full US stocks universe (~219 mega-cap survivors), computes every
signal from engine.tech_catalog, and writes two JSON artefacts to
site/factordata/:

  tech_screener.json  — per-ticker latest-bar state + composite score
  tech_lab.json       — per-signal descriptive fire-metrics (display-only)

HONESTY CONTRACT
----------------
- Display-only / research artefact. SURVIVORSHIP-BIASED universe.
- No 'validated' in any user-facing string (CI-guarded).
- No LLM-originated signals or escalations.
- Nothing wired to allocation or masterminds.
- Fundamental signals are cross-sectional state; forward metrics are NULL for
  pure-state signals (no per-bar fires to study).

USAGE
-----
    python scripts/build_tech_lab_data.py [--sample N] [--output-dir PATH]

    --sample N     run on first N tickers only (smoke-test mode)
    --output-dir   write output here instead of site/factordata/ (default)

The full run (~219 tickers × 43 signals) takes a few minutes on a 4-core Mac.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap — allow running from any cwd
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
os.chdir(_REPO_ROOT)  # engine modules that do relative data/ reads need this

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_tech_lab_data")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_OUTPUT_DIR = _REPO_ROOT / "site" / "factordata"
_SCREENER_FILE = "tech_screener.json"
_LAB_FILE = "tech_lab.json"
_TECH_EVENTS_DIR = "tech_events"
_TECH_EVENTS_INDEX = "_index.json"

_HORIZON = 21          # forward-return horizon (trading days)
_FIRE_CAP = 2000       # cap per-signal pool to this many fires (logged if hit)
_SPX_KEY = "_GSPC"    # SPX series key in yahoo store
_ERA_SPLIT = "2010-01-01"  # era split date

# tech_events export: fires within the last 3 years
_EVENTS_WINDOW_YEARS = 3

# Lab-exempt snapshot families: skip per-bar fires, but keep latest state
_LAB_EXEMPT_FAMILIES = frozenset({"fundamental_valuation", "insider"})

# performance lookback in bars (approximate)
_PERF_7D = 7
_PERF_30D = 30
_PERF_12M = 252

# Lag metric: trailing window for "% above X-day low"
_LAG_WINDOW = 60


# ---------------------------------------------------------------------------
# Lazy imports (deferred so failures are loud at runtime, not import-time)
# ---------------------------------------------------------------------------

def _import_engine():
    from engine import tech_catalog as tc  # noqa: PLC0415
    from engine import tech_score          # noqa: PLC0415
    from engine import tech_stars          # noqa: PLC0415
    from engine import lab                 # noqa: PLC0415
    return tc, tech_score, tech_stars, lab


# ---------------------------------------------------------------------------
# Name lookup helper
# ---------------------------------------------------------------------------

def _build_name_map() -> dict[str, str]:
    """Scan site/factordata JSON files to build ticker → company name map.

    Falls back to the ticker string itself when no name is found.
    """
    name_map: dict[str, str] = {}
    data_dir = _REPO_ROOT / "site" / "factordata"
    if not data_dir.exists():
        return name_map

    def _extract(obj: Any) -> None:
        if isinstance(obj, list):
            for item in obj:
                _extract(item)
        elif isinstance(obj, dict):
            t = obj.get("ticker")
            n = obj.get("name")
            if isinstance(t, str) and isinstance(n, str) and t and n:
                name_map[t] = n
            for v in obj.values():
                if isinstance(v, (list, dict)):
                    _extract(v)

    for fp in sorted(data_dir.glob("*.json")):
        try:
            with open(fp) as fh:
                _extract(json.load(fh))
        except Exception:
            pass

    return name_map


# ---------------------------------------------------------------------------
# Performance helper
# ---------------------------------------------------------------------------

def _perf(close: pd.Series, n_bars: int) -> float | None:
    if len(close) <= n_bars:
        return None
    base = float(close.iloc[-(n_bars + 1)])
    cur = float(close.iloc[-1])
    if base <= 0:
        return None
    return round(cur / base - 1.0, 6)


# ---------------------------------------------------------------------------
# Lag metric helpers (for lab descriptive profile)
# ---------------------------------------------------------------------------

def _lag_metrics(
    df: pd.DataFrame, fire_dates: pd.DatetimeIndex, window: int = _LAG_WINDOW
) -> tuple[float | None, float | None]:
    """Return (median_lag_pct, days_since_low_med) over fire_dates.

    lag_pct  = (close[fire] - rolling_min_close[fire-window:fire]) / rolling_min
    days_since_low = calendar days from trailing-window argmin to fire date
    """
    if len(fire_dates) == 0:
        return None, None

    close = df["close"].sort_index()
    rolling_min = close.rolling(window, min_periods=1).min()

    lag_pcts: list[float] = []
    days_list: list[int] = []

    for fd in fire_dates:
        if fd not in close.index:
            continue
        t = close.index.get_loc(fd)
        start_t = max(0, t - window)
        win_close = close.iloc[start_t : t + 1]
        if win_close.empty:
            continue

        low_val = float(rolling_min.loc[fd])
        cur_val = float(close.loc[fd])
        if low_val <= 0:
            continue

        lag_pcts.append((cur_val - low_val) / low_val)

        # calendar days from the low bar to fire date
        low_date = win_close.idxmin()
        days_list.append(max(0, (fd - low_date).days))

    med_pct = float(np.median(lag_pcts)) if lag_pcts else None
    med_days = float(np.median(days_list)) if days_list else None
    return (round(med_pct, 6) if med_pct is not None else None,
            round(med_days, 1) if med_days is not None else None)


# ---------------------------------------------------------------------------
# Era win-rate helper
# ---------------------------------------------------------------------------

def _era_wr(metrics: pd.DataFrame, era_split: str) -> tuple[float | None, float | None]:
    """Return (wr_pre2010, wr_post2010) from a fire-metrics DataFrame."""
    if metrics.empty:
        return None, None
    split_dt = pd.Timestamp(era_split)
    pre = metrics[metrics.index < split_dt]
    post = metrics[metrics.index >= split_dt]
    wr_pre = float(pre["win"].mean()) if len(pre) >= 5 else None
    wr_post = float(post["win"].mean()) if len(post) >= 5 else None
    return wr_pre, wr_post


# ---------------------------------------------------------------------------
# Combined single-pass build — screener + lab in one tc.compute pass
# ---------------------------------------------------------------------------

def build_all(
    universe: dict[str, pd.DataFrame],
    tc: Any,
    tech_score: Any,
    tech_stars: Any,
    df_spx: pd.DataFrame,
    name_map: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    """Single-pass over (ticker × signal): compute each series ONCE and feed
    BOTH the screener state and the lab fire-accumulation AND tech_events export.

    Returns (screener_payload, lab_payload, tech_events_by_ticker).

    tech_events_by_ticker maps ticker → per-ticker events dict (raw, pre-serialization).
    The caller writes site/factordata/tech_events/<TICKER>.json + _index.json.
    """
    all_sigs = tc.list_signals()
    n_sigs = len(all_sigs)
    tickers = list(universe.keys())
    n_tickers = len(tickers)

    log.info("Single-pass: %d tickers × %d signals", n_tickers, n_sigs)

    # Compute SPX 200d-MA for regime split (above-tape = up-tape)
    from engine.strategy_signals import sma  # noqa: PLC0415
    spx_close = df_spx["close"]
    spx_ma200 = sma(spx_close, 200)
    above_ma = (spx_close > spx_ma200).rename("above_ma")

    # -----------------------------------------------------------------------
    # Per-signal lab accumulators (keyed by signal_id)
    # -----------------------------------------------------------------------
    # These mirror what build_lab_data collected inside its signal→ticker loop.
    lab_acc: dict[str, dict[str, Any]] = {}
    for sig in all_sigs:
        sid = sig["signal_id"]
        family = sig.get("family", "")
        kind = sig.get("kind", "event")
        lab_acc[sid] = {
            "sig": sig,
            "lab_exempt": (family in ("fundamental_valuation", "insider")),  # snapshot families: constant cross-sectional score, no dated per-bar fires -> null lab profile
            "kind": kind,
            "all_metrics": [],           # list[pd.DataFrame]
            "all_fire_dates": [],        # list[pd.Timestamp]
            "all_lag_pcts": [],          # list[float]
            "all_days_since": [],        # list[float]
        }

    # -----------------------------------------------------------------------
    # Per-signal screener accumulators
    # -----------------------------------------------------------------------
    sig_firing: dict[str, list[dict[str, Any]]] = {s["signal_id"]: [] for s in all_sigs}

    # Which signals belong in the "who's firing now" screen. Raw-score / direction-0
    # state signals (insider_power_state 0-100, valuation_pctile 0-1, return_1d, …)
    # are non-zero for ~the whole universe, so a firing list over them would list
    # every ticker — not a meaningful screen. They are excluded here but remain in
    # each stock's per-signal profile (sig_entries) and as rank keys.
    firing_eligible: dict[str, bool] = {
        s["signal_id"]: tc.is_screener_firing(s) for s in all_sigs
    }

    # -----------------------------------------------------------------------
    # Per-ticker screener output
    # -----------------------------------------------------------------------
    stocks_out: dict[str, dict[str, Any]] = {}

    # -----------------------------------------------------------------------
    # tech_events per-ticker accumulator (TLT-R3)
    # -----------------------------------------------------------------------
    # fires within the last 3 years only; omit signals with zero fires AND state==0
    tech_events_by_ticker: dict[str, dict[str, Any]] = {}
    _now = datetime.now(timezone.utc)
    _events_cutoff = pd.Timestamp(_now.year - _EVENTS_WINDOW_YEARS, _now.month, _now.day)

    # -----------------------------------------------------------------------
    # SINGLE PASS: outer = ticker, inner = signal
    # -----------------------------------------------------------------------
    for i, ticker in enumerate(tickers):
        if (i + 1) % 50 == 0:
            log.info("  pass: %d/%d tickers done", i + 1, n_tickers)

        df = universe[ticker]
        df.attrs["ticker"] = ticker

        close_series = df["close"]
        price = round(float(close_series.iloc[-1]), 4)

        # Composite score (screener)
        try:
            score_result = tech_score.score(df)
            score = round(score_result.score, 4)
            band = score_result.band
            active_buy = sum(
                1 for c in score_result.contributors
                if c.direction == 1 and c.raw_value > 0
            )
            active_total = sum(
                1 for c in score_result.contributors if c.raw_value > 0
            )
        except Exception as exc:
            log.debug("score failed for %s: %s", ticker, exc)
            score, band, active_buy, active_total = 0.0, "Hold", 0, 0

        # Performance (screener)
        perf_7d = _perf(close_series, _PERF_7D)
        perf_30d = _perf(close_series, _PERF_30D)
        perf_12m = _perf(close_series, _PERF_12M)

        # Per-signal inner loop
        sig_entries: list[dict[str, Any]] = []
        # Per-ticker tech_events accumulator (collected in this inner loop)
        _te_signals: dict[str, dict[str, Any]] = {}

        for sig in all_sigs:
            sid = sig["signal_id"]
            direction = int(sig.get("direction", 0))
            display_en = sig.get("display", {}).get("en", sid)
            glyph = sig.get("glyph", "")
            kind = sig.get("kind", "event")
            acc = lab_acc[sid]

            # --- ONE compute call ---
            try:
                series = tc.compute(sid, df)
            except Exception:
                continue

            if series.empty:
                continue

            # ---- SCREENER side ----
            latest_val = series.iloc[-1]
            state = 0 if pd.isna(latest_val) or latest_val == 0 else 1

            if kind == "event":
                fires_s = series[series > 0]
                if len(fires_s) > 0:
                    last_fire_date = fires_s.index[-1]
                    last_bar = df.index[-1]
                    age_days = (last_bar - last_fire_date).days
                else:
                    age_days = None
            else:
                age_days = 0 if state == 1 else None

            sig_entries.append({
                "id": sid,
                "display_en": display_en,
                "direction": direction,
                "glyph": glyph,
                "state": state,
                "age_days": age_days,
            })

            if state == 1 and firing_eligible[sid]:
                sig_firing[sid].append({
                    "ticker": ticker,
                    "name": name_map.get(ticker, ticker),
                    "price": price,
                    "score": score,
                    "band": band,
                })

            # ---- TECH_EVENTS side (TLT-R3) ----
            # Lab-exempt families: skip fires but keep latest state.
            # Non-exempt: collect fires within the 3-year window.
            family_te = sig.get("family", "")
            if family_te in _LAB_EXEMPT_FAMILIES:
                # Only include if state is active (avoid noise from zero-state exempt signals)
                if state == 1:
                    _te_signals[sid] = {
                        "dir": int(sig.get("direction", 0)),
                        "kind": kind,
                        "fires": [],
                        "state": state,
                    }
            else:
                # Determine event fires (state→rising-edge; event→fire bars)
                if kind == "state":
                    pos_shifted_te = series.shift(1, fill_value=0.0)
                    event_te = ((series > 0) & (pos_shifted_te == 0)).astype(float)
                else:
                    event_te = series

                fires_in_window = event_te[
                    (event_te > 0) & (event_te.index >= _events_cutoff)
                ]
                fire_dates_str = [str(d.date()) for d in fires_in_window.index]

                # Omit signals with zero fires in-window AND state==0
                if fire_dates_str or state == 1:
                    _te_signals[sid] = {
                        "dir": int(sig.get("direction", 0)),
                        "kind": kind,
                        "fires": fire_dates_str,
                        "state": state,
                    }

            # ---- LAB side (skip snapshot-family signals: fundamental + insider) ----
            if acc["lab_exempt"]:
                continue

            # For state signals: use rising-edge transitions as fires
            if kind == "state":
                pos_shifted = series.shift(1, fill_value=0.0)
                event_pos = ((series > 0) & (pos_shifted == 0)).astype(float)
            else:
                event_pos = series

            lab_fires = event_pos[event_pos > 0]
            if lab_fires.empty:
                continue

            acc["all_fire_dates"].extend(lab_fires.index.tolist())

            # Lag metric
            lag_pct, days_low = _lag_metrics(df, lab_fires.index)
            if lag_pct is not None:
                acc["all_lag_pcts"].append(lag_pct)
            if days_low is not None:
                acc["all_days_since"].append(days_low)

            # Per-fire forward metrics (P0-1: thread direction from catalog descriptor)
            try:
                m = tech_stars.compute_fire_metrics(
                    df, event_pos, horizon=_HORIZON, direction=direction
                )
                if not m.empty:
                    acc["all_metrics"].append(m)
            except Exception:
                continue

        # Finalize tech_events for this ticker
        last_bar_date = str(df.index[-1].date()) if not df.empty else ""
        window_start_date = str(_events_cutoff.date())
        tech_events_by_ticker[ticker] = {
            "ticker": ticker,
            "generated_utc": _now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_start": window_start_date,
            "signals": _te_signals,
        }

        stocks_out[ticker] = {
            "name": name_map.get(ticker, ticker),
            "price": price,
            "score": score,
            "band": band,
            "active_buy": active_buy,
            "active_total": active_total,
            "perf_7d": perf_7d,
            "perf_30d": perf_30d,
            "perf_12m": perf_12m,
            "signals": sig_entries,
        }

    # -----------------------------------------------------------------------
    # Build screener output (same as old build_screener_data post-loop)
    # -----------------------------------------------------------------------
    signals_screener: dict[str, dict[str, Any]] = {}
    for sig in all_sigs:
        sid = sig["signal_id"]
        display_en = sig.get("display", {}).get("en", sid)
        display_zh = sig.get("display", {}).get("zh", "")
        family = sig.get("family", "")
        direction = int(sig.get("direction", 0))
        glyph = sig.get("glyph", "")
        firing_tickers = sig_firing[sid]
        signals_screener[sid] = {
            "display_en": display_en,
            "display_zh": display_zh,
            "family": family,
            "direction": direction,
            "glyph": glyph,
            "n_firing": len(firing_tickers),
            "tickers": firing_tickers,
        }

    screener_payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe_n": n_tickers,
        "signals": signals_screener,
        "stocks": stocks_out,
    }

    # -----------------------------------------------------------------------
    # Build lab output (aggregate per-signal accumulators)
    # Same aggregation logic as old build_lab_data post-inner-loop
    # -----------------------------------------------------------------------
    signals_lab: dict[str, dict[str, Any]] = {}

    _null_lab_entry = lambda sig, kind: {  # noqa: E731
        "display_en": sig.get("display", {}).get("en", sig["signal_id"]),
        "family": sig.get("family", ""),
        "direction": int(sig.get("direction", 0)),
        "n_fires": 0,
        "n_months": 0,
        "wr_21d": None,
        "mean_21d": None,
        "base_wr": None,
        "base_mean": None,
        "edge_wr": None,
        "edge_mean": None,
        "mfe_mae_med": None,
        "durable_rate": None,
        "median_lag_pct": None,
        "days_since_low_med": None,
        "up_tape_pct": None,
        "wr_pre2010": None,
        "wr_post2010": None,
        "kind": kind,
    }

    for sig_idx, sig in enumerate(all_sigs):
        sid = sig["signal_id"]
        family = sig.get("family", "")
        direction = int(sig.get("direction", 0))
        display_en = sig.get("display", {}).get("en", sid)
        kind = sig.get("kind", "event")
        acc = lab_acc[sid]

        log.debug("Lab aggregate %d/%d: %s", sig_idx + 1, n_sigs, sid)

        if acc["lab_exempt"]:
            signals_lab[sid] = _null_lab_entry(sig, kind)
            continue

        all_metrics = acc["all_metrics"]
        all_fire_dates_for_regime = acc["all_fire_dates"]
        all_lag_pcts = acc["all_lag_pcts"]
        all_days_since = acc["all_days_since"]

        if not all_metrics:
            signals_lab[sid] = _null_lab_entry(sig, kind)
            continue

        pooled_full = pd.concat(all_metrics, axis=0).sort_index()
        n_fires_total_sig = len(pooled_full)

        # P0-3: compute n_months on the FULL pooled set (before cap) as distinct
        # calendar months containing >=1 fire, not span/30 on the capped slice.
        if n_fires_total_sig > 0:
            months_with_fires = pooled_full.index.to_period("M").unique()
            n_months = len(months_with_fires)
            first_fire = str(pooled_full.index[0].date())
            last_fire = str(pooled_full.index[-1].date())
        else:
            n_months = 0
            first_fire = None
            last_fire = None

        # P0-3: top_fire_days — 5 calendar dates with the most simultaneous fires
        if n_fires_total_sig > 0:
            daily_counts = pooled_full.groupby(pooled_full.index.normalize()).size()
            top5 = daily_counts.nlargest(5)
            top_fire_days = [
                {"date": str(d.date()), "n_fires": int(c)} for d, c in top5.items()
            ]
        else:
            top_fire_days = []

        # Cap fires for per-fire detail storage (stats computed on FULL set above)
        truncated = n_fires_total_sig > _FIRE_CAP
        if truncated:
            log.info(
                "Lab: %s has %d fires (> cap %d); capping to most recent %d for detail",
                sid, n_fires_total_sig, _FIRE_CAP, _FIRE_CAP,
            )
            pooled = pooled_full.iloc[-_FIRE_CAP:]
        else:
            pooled = pooled_full

        # P0-3: all summary stats on the FULL set, not the capped slice
        n_fires = n_fires_total_sig
        wr_21d = float(pooled_full["win"].mean()) if n_fires > 0 else None
        # P0-1 fix: use signed_return (direction-adjusted) for mean; fwd_ret is stored per-fire
        mean_21d = float(pooled_full["signed_return"].mean()) if n_fires > 0 else None
        mfe_mae_vals = pooled_full["mfe_mae"].dropna()
        mfe_mae_med = float(mfe_mae_vals.median()) if len(mfe_mae_vals) > 0 else None
        durable_rate = float(pooled_full["durable"].mean()) if n_fires > 0 else None

        med_lag = float(np.median(all_lag_pcts)) if all_lag_pcts else None
        med_days = float(np.median(all_days_since)) if all_days_since else None

        # Up-tape pct
        fire_dates_idx = pd.DatetimeIndex(all_fire_dates_for_regime[:_FIRE_CAP])
        if len(fire_dates_idx) > 0 and not above_ma.empty:
            aligned = above_ma.reindex(fire_dates_idx, method="ffill")
            up_tape_pct = float(aligned.sum() / len(aligned)) if len(aligned) > 0 else None
        else:
            up_tape_pct = None

        # Era split — use full pooled set (P0-3)
        wr_pre2010, wr_post2010 = _era_wr(pooled_full, _ERA_SPLIT)

        # Base rate: random ticker-day sampling (same logic as before, seeded identically)
        rng = np.random.default_rng(42)
        sample_rets: list[float] = []
        for ticker in rng.choice(tickers, size=min(20, len(tickers)), replace=False):
            df = universe[ticker]
            close = df["close"]
            if len(close) < _HORIZON + 5:
                continue
            max_idx = len(close) - _HORIZON - 2
            if max_idx < 5:
                continue
            idxs = rng.integers(0, max_idx, size=min(50, max_idx))
            for idx in idxs:
                entry = float(close.iloc[idx + 1])
                exit_ = float(close.iloc[idx + 1 + _HORIZON])
                if entry > 0:
                    sample_rets.append(exit_ / entry - 1.0)

        base_wr = float(np.mean([r > 0 for r in sample_rets])) if sample_rets else None
        base_mean = float(np.mean(sample_rets)) if sample_rets else None
        # P0-1: the signal stats are direction-signed, so the random baseline must be
        # signed the same way — shorting random bars wins at (1 - base_wr) and earns
        # -base_mean. Stored base_* values are the direction-adjusted comparators.
        if direction < 0 and base_wr is not None:
            base_wr = 1.0 - base_wr
        if direction < 0 and base_mean is not None:
            base_mean = -base_mean
        edge_wr = (round(wr_21d - base_wr, 6) if wr_21d is not None and base_wr is not None else None)
        edge_mean = (round(mean_21d - base_mean, 6) if mean_21d is not None and base_mean is not None else None)

        entry: dict = {
            "display_en": display_en,
            "family": family,
            "direction": direction,
            "n_fires": n_fires,
            "n_months": n_months,
            "first_fire": first_fire,
            "last_fire": last_fire,
            "wr_21d": round(wr_21d, 6) if wr_21d is not None else None,
            "mean_21d": round(mean_21d, 6) if mean_21d is not None else None,
            "base_wr": round(base_wr, 6) if base_wr is not None else None,
            "base_mean": round(base_mean, 6) if base_mean is not None else None,
            "edge_wr": round(edge_wr, 6) if edge_wr is not None else None,
            "edge_mean": round(edge_mean, 6) if edge_mean is not None else None,
            "mfe_mae_med": round(mfe_mae_med, 4) if mfe_mae_med is not None else None,
            "durable_rate": round(durable_rate, 6) if durable_rate is not None else None,
            "median_lag_pct": round(med_lag, 6) if med_lag is not None else None,
            "days_since_low_med": round(med_days, 1) if med_days is not None else None,
            "up_tape_pct": round(up_tape_pct, 6) if up_tape_pct is not None else None,
            "wr_pre2010": round(wr_pre2010, 6) if wr_pre2010 is not None else None,
            "wr_post2010": round(wr_post2010, 6) if wr_post2010 is not None else None,
            "kind": kind,
            "top_fire_days": top_fire_days,
        }
        # P0-3: truncation disclosure when cap binds
        if truncated:
            entry["truncated"] = True
            entry["n_fires_total"] = n_fires_total_sig
        signals_lab[sid] = entry

    total_fires = sum(v["n_fires"] for v in signals_lab.values())

    lab_payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe_n": n_tickers,
        "universe_caveat": "survivor mega-caps; descriptive not §5.9 verdict",
        "signals": signals_lab,
        "_meta": {"total_fires": total_fires},
    }

    return screener_payload, lab_payload, tech_events_by_ticker


# ---------------------------------------------------------------------------
# tech_events writer (TLT-R3)
# ---------------------------------------------------------------------------

def write_tech_events(
    tech_events_by_ticker: dict[str, dict[str, Any]],
    output_dir: Path,
) -> Path:
    """Write per-ticker tech_events JSON and the _index.json summary.

    Writes:
      <output_dir>/tech_events/<TICKER>.json  — per-ticker fires/state per signal
      <output_dir>/tech_events/_index.json    — index: generated_utc + n_fires_total per ticker

    Schema (per-ticker JSON):
      {
        "ticker": "NVDA",
        "generated_utc": "...",
        "window_start": "YYYY-MM-DD",
        "signals": {
          "<signal_id>": {
            "dir": 1|-1|0,
            "kind": "event"|"state",
            "fires": ["YYYY-MM-DD", ...],
            "state": 0|1
          },
          ...
        }
      }

    Per TLT-R3: fires are event fires (or state rising edges) within the last 3 years only.
    Signals with zero fires in-window AND state==0 are omitted.
    Lab-exempt snapshot families (fundamental_valuation, insider) appear with fires=[] and
    latest state only.
    """
    events_dir = output_dir / _TECH_EVENTS_DIR
    events_dir.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    index_tickers: dict[str, int] = {}

    for ticker, payload in tech_events_by_ticker.items():
        n_fires = sum(
            len(sig_data.get("fires", []))
            for sig_data in payload.get("signals", {}).values()
        )
        index_tickers[ticker] = n_fires

        out_path = events_dir / f"{ticker}.json"
        with open(out_path, "w") as fh:
            json.dump(payload, fh, separators=(",", ":"))

    # Write _index.json
    index_payload = {
        "generated_utc": now_utc,
        "tickers": index_tickers,
    }
    index_path = events_dir / _TECH_EVENTS_INDEX
    with open(index_path, "w") as fh:
        json.dump(index_payload, fh, separators=(",", ":"))

    log.info(
        "tech_events: wrote %d ticker files + _index.json to %s",
        len(tech_events_by_ticker), events_dir,
    )
    return events_dir


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build tech_screener.json + tech_lab.json")
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Run on first N tickers only (smoke-test mode)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=_OUTPUT_DIR,
        help="Output directory (default: site/factordata/)",
    )
    args = parser.parse_args(argv)

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    log.info("=== build_tech_lab_data starting ===")

    # Import engine modules
    tc, tech_score, tech_stars, lab = _import_engine()

    # Load universe
    log.info("Loading universe …")
    universe = lab.load("ALL", group="stocks")
    if args.sample:
        tickers = sorted(universe.keys())[: args.sample]
        universe = {t: universe[t] for t in tickers}
        log.info("Sample mode: %d tickers", len(universe))

    n_stocks = len(universe)
    all_sigs = tc.list_signals()
    n_signals = len(all_sigs)
    log.info("Universe: %d tickers, %d signals", n_stocks, n_signals)

    # Name map
    log.info("Building name map …")
    name_map = _build_name_map()
    log.info("Name map: %d entries", len(name_map))

    # SPX for regime split
    log.info("Loading SPX for regime split …")
    spx_series = lab.bench(_SPX_KEY)
    if spx_series.empty:
        log.warning("SPX not found — regime split will be skipped")
        df_spx = pd.DataFrame({"close": pd.Series(dtype=float)})
    else:
        df_spx = pd.DataFrame({"close": spx_series})

    # --- Single pass (screener + lab + tech_events) -------------------------
    log.info("Running single-pass build …")
    screener_payload, lab_payload, tech_events_by_ticker = build_all(
        universe, tc, tech_score, tech_stars, df_spx, name_map,
    )

    # --- Write screener -----------------------------------------------------
    screener_path = output_dir / _SCREENER_FILE
    with open(screener_path, "w") as fh:
        json.dump(screener_payload, fh, separators=(",", ":"))
    log.info("Wrote %s (%.1f KB)", screener_path, screener_path.stat().st_size / 1024)

    # --- Write lab ----------------------------------------------------------
    lab_path = output_dir / _LAB_FILE
    with open(lab_path, "w") as fh:
        json.dump(lab_payload, fh, separators=(",", ":"))
    log.info("Wrote %s (%.1f KB)", lab_path, lab_path.stat().st_size / 1024)

    # --- Write tech_events (TLT-R3) -----------------------------------------
    events_dir = write_tech_events(tech_events_by_ticker, output_dir)
    log.info("tech_events written to %s", events_dir)

    # Summary
    total_fires = lab_payload["_meta"]["total_fires"]
    elapsed = time.monotonic() - t0
    log.info("=== DONE in %.1fs ===", elapsed)
    print(
        f"\n[build_tech_lab_data] {n_signals} signals | {n_stocks} stocks | "
        f"{total_fires} fires pooled | {elapsed:.1f}s"
    )
    print(f"  Screener:     {screener_path}")
    print(f"  Lab:          {lab_path}")
    print(f"  Tech Events:  {events_dir}/")


if __name__ == "__main__":
    main()
