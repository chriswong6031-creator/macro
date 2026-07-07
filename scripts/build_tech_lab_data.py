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

_HORIZON = 21          # forward-return horizon (trading days)
_FIRE_CAP = 2000       # cap per-signal pool to this many fires (logged if hit)
_SPX_KEY = "_GSPC"    # SPX series key in yahoo store
_ERA_SPLIT = "2010-01-01"  # era split date

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
# Screener: compute per-ticker signal states + scores
# ---------------------------------------------------------------------------

def build_screener_data(
    universe: dict[str, pd.DataFrame],
    tc: Any,
    tech_score: Any,
    name_map: dict[str, str],
) -> dict[str, Any]:
    """Build the tech_screener.json payload."""
    all_sigs = tc.list_signals()
    n_sigs = len(all_sigs)
    tickers = list(universe.keys())
    n_tickers = len(tickers)

    log.info("Screener: %d tickers × %d signals", n_tickers, n_sigs)

    # Initialise per-signal firing lists
    sig_firing: dict[str, list[dict[str, Any]]] = {s["signal_id"]: [] for s in all_sigs}

    # Per-ticker output
    stocks_out: dict[str, dict[str, Any]] = {}

    for i, ticker in enumerate(tickers):
        if (i + 1) % 50 == 0:
            log.info("  screener: %d/%d tickers done", i + 1, n_tickers)

        df = universe[ticker]
        df.attrs["ticker"] = ticker

        close_series = df["close"]
        price = round(float(close_series.iloc[-1]), 4)

        # Composite score
        try:
            score_result = tech_score.score(df)
            score = round(score_result.score, 4)
            band = score_result.band
            # active_buy = direction == +1 and raw_value > 0
            active_buy = sum(
                1 for c in score_result.contributors
                if c.direction == 1 and c.raw_value > 0
            )
            # active_total = any direction, raw_value > 0 (truthy)
            active_total = sum(
                1 for c in score_result.contributors if c.raw_value > 0
            )
        except Exception as exc:
            log.debug("score failed for %s: %s", ticker, exc)
            score, band, active_buy, active_total = 0.0, "Hold", 0, 0

        # Performance
        perf_7d = _perf(close_series, _PERF_7D)
        perf_30d = _perf(close_series, _PERF_30D)
        perf_12m = _perf(close_series, _PERF_12M)

        # Per-signal latest-bar state
        sig_entries: list[dict[str, Any]] = []
        for sig in all_sigs:
            sid = sig["signal_id"]
            direction = int(sig.get("direction", 0))
            display_en = sig.get("display", {}).get("en", sid)
            glyph = sig.get("glyph", "")
            kind = sig.get("kind", "event")

            try:
                series = tc.compute(sid, df)
            except Exception:
                continue

            if series.empty:
                continue

            latest_val = series.iloc[-1]
            state = 0 if pd.isna(latest_val) or latest_val == 0 else 1

            # age_days: for event signals = bars since last fire; for state signals = 0 if firing
            if kind == "event":
                fires = series[series > 0]
                if len(fires) > 0:
                    last_fire_date = fires.index[-1]
                    last_bar = df.index[-1]
                    # calendar days
                    age_days = (last_bar - last_fire_date).days
                else:
                    age_days = None
            else:
                # state signal
                age_days = 0 if state == 1 else None

            sig_entries.append({
                "id": sid,
                "display_en": display_en,
                "direction": direction,
                "glyph": glyph,
                "state": state,
                "age_days": age_days,
            })

            # record into per-signal firing list (only if firing on latest bar)
            if state == 1:
                sig_firing[sid].append({
                    "ticker": ticker,
                    "name": name_map.get(ticker, ticker),
                    "price": price,
                    "score": score,
                    "band": band,
                })

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

    # Build signals section
    signals_out: dict[str, dict[str, Any]] = {}
    for sig in all_sigs:
        sid = sig["signal_id"]
        display_en = sig.get("display", {}).get("en", sid)
        display_zh = sig.get("display", {}).get("zh", "")
        family = sig.get("family", "")
        direction = int(sig.get("direction", 0))
        glyph = sig.get("glyph", "")
        firing_tickers = sig_firing[sid]
        signals_out[sid] = {
            "display_en": display_en,
            "display_zh": display_zh,
            "family": family,
            "direction": direction,
            "glyph": glyph,
            "n_firing": len(firing_tickers),
            "tickers": firing_tickers,
        }

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe_n": n_tickers,
        "signals": signals_out,
        "stocks": stocks_out,
    }


# ---------------------------------------------------------------------------
# Lab: per-signal descriptive fire-metric profiles
# ---------------------------------------------------------------------------

def build_lab_data(
    universe: dict[str, pd.DataFrame],
    tc: Any,
    tech_stars: Any,
    df_spx: pd.DataFrame,
) -> dict[str, Any]:
    """Build the tech_lab.json payload (descriptive; no placebo/bootstrap)."""
    all_sigs = tc.list_signals()
    tickers = list(universe.keys())
    n_tickers = len(tickers)

    log.info("Lab: pooling fires across %d tickers × %d signals", n_tickers, len(all_sigs))

    # Compute SPX 200d-MA for regime split (above-tape = up-tape)
    from engine.strategy_signals import sma  # noqa: PLC0415
    spx_close = df_spx["close"]
    spx_ma200 = sma(spx_close, 200)
    above_ma = (spx_close > spx_ma200).rename("above_ma")

    signals_out: dict[str, dict[str, Any]] = {}

    for sig_idx, sig in enumerate(all_sigs):
        sid = sig["signal_id"]
        family = sig.get("family", "")
        direction = int(sig.get("direction", 0))
        display_en = sig.get("display", {}).get("en", sid)
        kind = sig.get("kind", "event")

        # Pure-state signals (no discrete fires) → null profile
        is_fundamental = (family == "fundamental_valuation")

        if is_fundamental:
            signals_out[sid] = {
                "display_en": display_en,
                "family": family,
                "direction": direction,
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
            continue

        log.debug("Lab signal %d/%d: %s", sig_idx + 1, len(all_sigs), sid)

        # Pool fires across the universe
        all_metrics: list[pd.DataFrame] = []
        all_fire_dates_for_regime: list[pd.Timestamp] = []
        all_lag_pcts: list[float] = []
        all_days_since: list[float] = []

        for ticker in tickers:
            df = universe[ticker]
            df.attrs["ticker"] = ticker

            try:
                pos = tc.compute(sid, df)
            except Exception:
                continue

            if pos.empty:
                continue

            # For state signals with no discrete fires: use transitions 0→1 as "fires"
            if kind == "state":
                # fire on rising edge (transition from 0 to 1)
                pos_shifted = pos.shift(1, fill_value=0.0)
                event_pos = ((pos > 0) & (pos_shifted == 0)).astype(float)
            else:
                event_pos = pos

            fires = event_pos[event_pos > 0]
            if fires.empty:
                continue

            all_fire_dates_for_regime.extend(fires.index.tolist())

            # Lag metric
            lag_pct, days_low = _lag_metrics(df, fires.index)
            if lag_pct is not None:
                all_lag_pcts.append(lag_pct)
            if days_low is not None:
                all_days_since.append(days_low)

            # Per-fire forward metrics
            try:
                m = tech_stars.compute_fire_metrics(df, event_pos, horizon=_HORIZON)
                if not m.empty:
                    all_metrics.append(m)
            except Exception:
                continue

        # --- aggregate -------------------------------------------------------
        if not all_metrics:
            signals_out[sid] = {
                "display_en": display_en,
                "family": family,
                "direction": direction,
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
            continue

        pooled = pd.concat(all_metrics, axis=0).sort_index()

        # Cap fires if needed
        if len(pooled) > _FIRE_CAP:
            log.info(
                "Lab: %s has %d fires (> cap %d); sampling most recent %d",
                sid, len(pooled), _FIRE_CAP, _FIRE_CAP,
            )
            pooled = pooled.iloc[-_FIRE_CAP:]

        n_fires = len(pooled)
        # n_months: span in months
        if n_fires > 0:
            span_days = (pooled.index[-1] - pooled.index[0]).days
            n_months = max(1, round(span_days / 30))
        else:
            n_months = 0

        wr_21d = float(pooled["win"].mean()) if n_fires > 0 else None
        mean_21d = float(pooled["fwd_ret"].mean()) if n_fires > 0 else None
        mfe_mae_vals = pooled["mfe_mae"].dropna()
        mfe_mae_med = float(mfe_mae_vals.median()) if len(mfe_mae_vals) > 0 else None
        durable_rate = float(pooled["durable"].mean()) if n_fires > 0 else None

        # Lag metrics (aggregated from per-ticker lists)
        med_lag = float(np.median(all_lag_pcts)) if all_lag_pcts else None
        med_days = float(np.median(all_days_since)) if all_days_since else None

        # Up-tape pct: fraction of fires where SPX was above 200d MA
        fire_dates_idx = pd.DatetimeIndex(all_fire_dates_for_regime[:_FIRE_CAP])
        if len(fire_dates_idx) > 0 and not above_ma.empty:
            aligned = above_ma.reindex(fire_dates_idx, method="ffill")
            up_tape_pct = float(aligned.sum() / len(aligned)) if len(aligned) > 0 else None
        else:
            up_tape_pct = None

        # Era split
        wr_pre2010, wr_post2010 = _era_wr(pooled, _ERA_SPLIT)

        # Base rate: random ticker-day sampling (approximate)
        # We estimate: draw n_fires random bars from a sample of tickers
        # and compute fwd_ret win rate — a rough "any day" null
        rng = np.random.default_rng(42)
        sample_rets: list[float] = []
        for ticker in rng.choice(tickers, size=min(20, len(tickers)), replace=False):
            df = universe[ticker]
            close = df["close"]
            if len(close) < _HORIZON + 5:
                continue
            # random bars (not near end)
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
        edge_wr = (round(wr_21d - base_wr, 6) if wr_21d is not None and base_wr is not None else None)
        edge_mean = (round(mean_21d - base_mean, 6) if mean_21d is not None and base_mean is not None else None)

        signals_out[sid] = {
            "display_en": display_en,
            "family": family,
            "direction": direction,
            "n_fires": n_fires,
            "n_months": n_months,
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
        }

    # Count total fires
    total_fires = sum(v["n_fires"] for v in signals_out.values())

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe_n": n_tickers,
        "universe_caveat": "survivor mega-caps; descriptive not §5.9 verdict",
        "signals": signals_out,
        "_meta": {"total_fires": total_fires},
    }


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

    # --- Screener -----------------------------------------------------------
    log.info("Building screener data …")
    screener_payload = build_screener_data(universe, tc, tech_score, name_map)

    screener_path = output_dir / _SCREENER_FILE
    with open(screener_path, "w") as fh:
        json.dump(screener_payload, fh, separators=(",", ":"))
    log.info("Wrote %s (%.1f KB)", screener_path, screener_path.stat().st_size / 1024)

    # --- Lab ----------------------------------------------------------------
    log.info("Building lab data …")
    lab_payload = build_lab_data(universe, tc, tech_stars, df_spx)

    lab_path = output_dir / _LAB_FILE
    with open(lab_path, "w") as fh:
        json.dump(lab_payload, fh, separators=(",", ":"))
    log.info("Wrote %s (%.1f KB)", lab_path, lab_path.stat().st_size / 1024)

    # Summary
    total_fires = lab_payload["_meta"]["total_fires"]
    elapsed = time.monotonic() - t0
    log.info("=== DONE in %.1fs ===", elapsed)
    print(
        f"\n[build_tech_lab_data] {n_signals} signals | {n_stocks} stocks | "
        f"{total_fires} fires pooled | {elapsed:.1f}s"
    )
    print(f"  Screener: {screener_path}")
    print(f"  Lab:      {lab_path}")


if __name__ == "__main__":
    main()
