"""scripts/tech_lab_cli.py — Tech Lab descriptor and per-ticker CLI harness.

Run as: python -m scripts.tech_lab_cli <subcommand> [options]

Subcommands
-----------
  list [--family F]
      Print the signal inventory as JSON: id, family, kind, direction, display en/zh.

  state <TICKER>
      Emit latest per-signal state for one ticker (reads single-ticker data via
      lib.store.read, no whole-universe load). Output is a JSON dict keyed by
      signal_id with {state, direction, kind, display_en}.

  profile <SIGNAL_ID> [--tickers A,B,C | --sample N] [--horizon 10|21|42|63 (repeatable)]
      Descriptive pooled fire metrics via engine.tech_stars.compute_fire_metrics.
      Output includes wr/mean/mfe_mae/durable per horizon, base-rate comparison,
      era split (pre/post 2010) ALWAYS printed, n_fires AND n_months, top-level
      {"tier": "descriptive_profile", "caveat": ...}.
      Horizon must be in {10, 21, 42, 63}. Exit 0 on honest nulls.

  series <SIGNAL_ID> <TICKER> [--tail N]
      Emit the last N bars of the raw signal series for a ticker (for chart debugging).

HOUSE RULES
-----------
- No "validated" or 已验证 in any output string (CI-guarded).
- No buy/sell threshold semantics on display surfaces.
- No DannyTrades/Danny/whale identifiers in output.
- Everything is display-tier / descriptive research framing.
- tier:"descriptive_profile" is stamped on every profile output.
- Era split (pre/post 2010) is ALWAYS printed per DT-R16.
- n_fires AND n_months are BOTH printed per DT-R14.
- Horizons restricted to {10, 21, 42, 63} trading days (TLT-R6).

TLT-R6 ruling: NEVER emit a verdict; descriptive only.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import timezone, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import os
os.chdir(_REPO_ROOT)

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("tech_lab_cli")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_VALID_HORIZONS: frozenset[int] = frozenset({10, 21, 42, 63})
_ERA_SPLIT = "2010-01-01"
_FIRE_CAP = 2000
_CAVEAT = (
    "survivor universe; descriptive, not a verdict; "
    "effective N ≈ months not fires"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_catalog():
    from engine import tech_catalog as tc  # noqa: PLC0415
    return tc


def _import_tech_stars():
    from engine import tech_stars  # noqa: PLC0415
    return tech_stars


def _load_single_ticker(ticker: str) -> pd.DataFrame | None:
    """Load a single ticker's OHLCV via lib.store.read (no whole-universe load)."""
    try:
        from lib import store  # noqa: PLC0415
        df = store.read("stocks", ticker)
        if df is None or df.empty:
            return None
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df
    except Exception as exc:
        log.error("Failed to load ticker %s: %s", ticker, exc)
        return None


def _load_sample_universe(sample_n: int | None = None, tickers: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Load a sample universe for profile computation."""
    try:
        from engine import lab  # noqa: PLC0415
        if tickers:
            universe = lab.load(tickers, group="stocks")
        elif sample_n is not None:
            all_u = lab.load("ALL", group="stocks")
            keys = sorted(all_u.keys())[:sample_n]
            universe = {k: all_u[k] for k in keys}
        else:
            universe = lab.load("ALL", group="stocks")
        return universe
    except Exception as exc:
        log.error("Failed to load universe: %s", exc)
        return {}


def _era_wr_profile(
    metrics_df: pd.DataFrame, era_split: str = _ERA_SPLIT
) -> dict[str, Any]:
    """Return era split metrics for a pooled fire-metrics DataFrame."""
    if metrics_df.empty:
        return {"era_split_date": era_split, "pre_split": None, "post_split": None}
    split_dt = pd.Timestamp(era_split)
    pre = metrics_df[metrics_df.index < split_dt]
    post = metrics_df[metrics_df.index >= split_dt]

    def _era_stats(sub: pd.DataFrame) -> dict[str, Any] | None:
        if sub.empty:
            return None
        n = len(sub)
        wr = float(sub["win"].mean()) if n > 0 else None
        mean_ret = float(sub["fwd_ret"].mean()) if n > 0 else None
        return {
            "n_fires": n,
            "wr": round(wr, 4) if wr is not None else None,
            "mean_ret": round(mean_ret, 6) if mean_ret is not None else None,
        }

    return {
        "era_split_date": era_split,
        "pre_split": _era_stats(pre),
        "post_split": _era_stats(post),
    }


# ---------------------------------------------------------------------------
# Subcommand: list
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> dict[str, Any]:
    tc = _import_catalog()
    family_filter = getattr(args, "family", None)
    sigs = tc.list_signals(family=family_filter)

    signals = []
    for s in sigs:
        signals.append({
            "id": s["signal_id"],
            "family": s.get("family", ""),
            "kind": s.get("kind", "event"),
            "direction": int(s.get("direction", 0)),
            "display_en": s.get("display", {}).get("en", s["signal_id"]),
            "display_zh": s.get("display", {}).get("zh", ""),
        })

    return {
        "n_signals": len(signals),
        "family_filter": family_filter,
        "signals": signals,
    }


# ---------------------------------------------------------------------------
# Subcommand: state
# ---------------------------------------------------------------------------

def cmd_state(args: argparse.Namespace) -> dict[str, Any]:
    ticker = args.ticker.upper()
    tc = _import_catalog()

    df = _load_single_ticker(ticker)
    if df is None:
        return {
            "ticker": ticker,
            "error": f"No data found for ticker '{ticker}'",
            "signals": {},
        }

    all_sigs = tc.list_signals()
    results: dict[str, Any] = {}

    for sig in all_sigs:
        sid = sig["signal_id"]
        kind = sig.get("kind", "event")
        direction = int(sig.get("direction", 0))
        display_en = sig.get("display", {}).get("en", sid)

        try:
            series = tc.compute(sid, df)
        except Exception:
            results[sid] = {
                "state": None,
                "direction": direction,
                "kind": kind,
                "display_en": display_en,
                "error": "compute failed",
            }
            continue

        if series.empty:
            results[sid] = {
                "state": 0,
                "direction": direction,
                "kind": kind,
                "display_en": display_en,
            }
            continue

        latest = series.iloc[-1]
        state = 0 if pd.isna(latest) or latest == 0 else 1

        results[sid] = {
            "state": state,
            "direction": direction,
            "kind": kind,
            "display_en": display_en,
        }

    last_bar = str(df.index[-1].date()) if not df.empty else None

    return {
        "ticker": ticker,
        "last_bar": last_bar,
        "n_signals": len(results),
        "signals": results,
    }


# ---------------------------------------------------------------------------
# Subcommand: profile
# ---------------------------------------------------------------------------

def cmd_profile(args: argparse.Namespace) -> dict[str, Any]:
    signal_id: str = args.signal_id
    horizons: list[int] = sorted(set(args.horizon)) if args.horizon else [21]
    tickers_raw: str | None = getattr(args, "tickers", None)
    sample_n: int | None = getattr(args, "sample", None)

    # Horizon whitelist enforcement (TLT-R6)
    bad_horizons = [h for h in horizons if h not in _VALID_HORIZONS]
    if bad_horizons:
        return {
            "error": (
                f"Horizon(s) {bad_horizons} are not in the allowed ladder "
                f"{sorted(_VALID_HORIZONS)}. TLT-R6 restricts horizons to "
                f"{{10, 21, 42, 63}} trading days."
            ),
            "valid_horizons": sorted(_VALID_HORIZONS),
        }

    tc = _import_catalog()
    tech_stars = _import_tech_stars()

    # Resolve signal descriptor
    try:
        sig = tc.get_signal(signal_id)
    except KeyError:
        return {
            "error": f"Signal '{signal_id}' not found. Run 'list' to see available signals.",
            "tier": "descriptive_profile",
        }

    family = sig.get("family", "")
    kind = sig.get("kind", "event")
    direction = int(sig.get("direction", 0))
    display_en = sig.get("display", {}).get("en", signal_id)
    lab_exempt = family in ("fundamental_valuation", "insider")

    # Load universe
    tickers_list: list[str] | None = None
    if tickers_raw:
        tickers_list = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]

    universe = _load_sample_universe(sample_n=sample_n, tickers=tickers_list)

    if not universe:
        return {
            "tier": "descriptive_profile",
            "caveat": _CAVEAT,
            "signal_id": signal_id,
            "display_en": display_en,
            "error": "No universe data available. Check that data/stocks/ is populated.",
            "n_tickers_loaded": 0,
        }

    # Gather fires across universe
    all_metrics_by_horizon: dict[int, list[pd.DataFrame]] = {h: [] for h in horizons}
    n_fires_total = 0
    n_tickers_with_fires = 0

    for ticker, df in universe.items():
        df.attrs["ticker"] = ticker
        try:
            series = tc.compute(signal_id, df)
        except Exception:
            continue

        if series.empty:
            continue

        # For state signals: rising-edge transitions only
        if kind == "state":
            prev = series.shift(1, fill_value=0.0)
            event_pos = ((series > 0) & (prev == 0)).astype(float)
        else:
            event_pos = series

        fires = event_pos[event_pos > 0]
        if fires.empty:
            continue

        n_fires_total += len(fires)
        n_tickers_with_fires += 1

        # Compute per-horizon metrics
        for h in horizons:
            try:
                # P0-1: thread direction from catalog descriptor
                m = tech_stars.compute_fire_metrics(
                    df, event_pos, horizon=h, direction=direction
                )
                if not m.empty:
                    all_metrics_by_horizon[h].append(m)
            except Exception:
                continue

    # Aggregate per horizon
    horizon_profiles: dict[str, Any] = {}

    for h in horizons:
        all_metrics = all_metrics_by_horizon[h]
        if not all_metrics or lab_exempt:
            horizon_profiles[str(h)] = {
                "horizon_td": h,
                "n_fires": 0,
                "n_months": 0,
                "wr": None,
                "mean_ret": None,
                "mfe_mae_med": None,
                "durable_rate": None,
                "base_wr": None,
                "base_mean": None,
                "edge_wr": None,
                "edge_mean": None,
                "era_split": {
                    "era_split_date": _ERA_SPLIT,
                    "pre_split": None,
                    "post_split": None,
                },
            }
            continue

        pooled_full = pd.concat(all_metrics).sort_index()
        n_fires_total_h = len(pooled_full)

        # P0-3: n_months = distinct calendar months with >=1 fire, on FULL set before cap
        if n_fires_total_h > 0:
            months_with_fires = pooled_full.index.to_period("M").unique()
            n_months = len(months_with_fires)
        else:
            n_months = 0

        # P0-3: top_fire_days — 5 calendar dates with most simultaneous fires (full set)
        if n_fires_total_h > 0:
            daily_counts = pooled_full.groupby(pooled_full.index.normalize()).size()
            top5 = daily_counts.nlargest(5)
            top_fire_days = [
                {"date": str(d.date()), "n_fires": int(c)} for d, c in top5.items()
            ]
        else:
            top_fire_days = []

        # Cap for per-fire detail storage; summary stats computed on full set
        truncated_h = n_fires_total_h > _FIRE_CAP
        if truncated_h:
            pooled = pooled_full.iloc[-_FIRE_CAP:]
        else:
            pooled = pooled_full

        # P0-3: summary stats on FULL set
        n = n_fires_total_h
        wr = float(pooled_full["win"].mean()) if n > 0 else None
        # P0-1 fix: use signed_return (direction-adjusted) for mean; fwd_ret stored per-fire
        mean_ret = float(pooled_full["signed_return"].mean()) if n > 0 else None
        mfe_mae_vals = pooled_full["mfe_mae"].dropna()
        mfe_mae_med = float(mfe_mae_vals.median()) if len(mfe_mae_vals) > 0 else None
        durable_rate = float(pooled_full["durable"].mean()) if n > 0 else None

        # Base rate
        rng = np.random.default_rng(42)
        tickers_arr = list(universe.keys())
        sample_rets: list[float] = []
        for t_key in rng.choice(tickers_arr, size=min(20, len(tickers_arr)), replace=False):
            df_b = universe[t_key]
            close = df_b["close"]
            if len(close) < h + 5:
                continue
            max_idx = len(close) - h - 2
            if max_idx < 5:
                continue
            idxs = rng.integers(0, max_idx, size=min(50, max_idx))
            for idx in idxs:
                entry = float(close.iloc[idx + 1])
                exit_ = float(close.iloc[idx + 1 + h])
                if entry > 0:
                    sample_rets.append(exit_ / entry - 1.0)

        base_wr = float(np.mean([r > 0 for r in sample_rets])) if sample_rets else None
        base_mean = float(np.mean(sample_rets)) if sample_rets else None
        # P0-1: baseline signed to match the signal's direction (short random bars
        # win at 1 - base_wr and earn -base_mean).
        if direction < 0 and base_wr is not None:
            base_wr = 1.0 - base_wr
        if direction < 0 and base_mean is not None:
            base_mean = -base_mean
        edge_wr = (round(wr - base_wr, 6) if wr is not None and base_wr is not None else None)
        edge_mean = (round(mean_ret - base_mean, 6) if mean_ret is not None and base_mean is not None else None)

        # P0-3: era_split on full set
        era_split = _era_wr_profile(pooled_full)

        h_profile: dict = {
            "horizon_td": h,
            "n_fires": n,
            "n_months": n_months,
            "top_fire_days": top_fire_days,
            "wr": round(wr, 4) if wr is not None else None,
            "mean_ret": round(mean_ret, 6) if mean_ret is not None else None,
            "mfe_mae_med": round(mfe_mae_med, 4) if mfe_mae_med is not None else None,
            "durable_rate": round(durable_rate, 4) if durable_rate is not None else None,
            "base_wr": round(base_wr, 4) if base_wr is not None else None,
            "base_mean": round(base_mean, 6) if base_mean is not None else None,
            "edge_wr": edge_wr,
            "edge_mean": edge_mean,
            "era_split": era_split,
        }
        # P0-3: truncation disclosure
        if truncated_h:
            h_profile["truncated"] = True
            h_profile["n_fires_total"] = n_fires_total_h
        horizon_profiles[str(h)] = h_profile

    return {
        "tier": "descriptive_profile",
        "caveat": _CAVEAT,
        "signal_id": signal_id,
        "display_en": display_en,
        "family": family,
        "kind": kind,
        "direction": direction,
        "lab_exempt": lab_exempt,
        "n_tickers_loaded": len(universe),
        "n_tickers_with_fires": n_tickers_with_fires,
        "n_fires_total": n_fires_total,
        "horizons": horizon_profiles,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------------------
# Subcommand: series
# ---------------------------------------------------------------------------

def cmd_series(args: argparse.Namespace) -> dict[str, Any]:
    signal_id: str = args.signal_id
    ticker: str = args.ticker.upper()
    tail_n: int = getattr(args, "tail", 50) or 50

    tc = _import_catalog()

    try:
        sig = tc.get_signal(signal_id)
    except KeyError:
        return {
            "error": f"Signal '{signal_id}' not found. Run 'list' to see available signals.",
        }

    df = _load_single_ticker(ticker)
    if df is None:
        return {
            "ticker": ticker,
            "signal_id": signal_id,
            "error": f"No data found for ticker '{ticker}'",
        }

    try:
        series = tc.compute(signal_id, df)
    except Exception as exc:
        return {
            "ticker": ticker,
            "signal_id": signal_id,
            "error": f"compute failed: {exc}",
        }

    if series.empty:
        return {
            "ticker": ticker,
            "signal_id": signal_id,
            "n_bars": 0,
            "bars": [],
        }

    tail = series.iloc[-tail_n:]
    bars = [
        {"date": str(idx.date()), "value": (None if pd.isna(v) else float(v))}
        for idx, v in tail.items()
    ]

    display_en = sig.get("display", {}).get("en", signal_id)
    kind = sig.get("kind", "event")

    return {
        "ticker": ticker,
        "signal_id": signal_id,
        "display_en": display_en,
        "kind": kind,
        "direction": int(sig.get("direction", 0)),
        "last_bar": str(df.index[-1].date()),
        "n_bars_tail": len(bars),
        "bars": bars,
    }


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.tech_lab_cli",
        description="Tech Lab signal CLI — descriptive research harness (display-tier only).",
    )
    sub = parser.add_subparsers(dest="subcommand")

    # list
    p_list = sub.add_parser("list", help="Signal inventory")
    p_list.add_argument("--family", default=None, help="Filter by signal family")

    # state
    p_state = sub.add_parser("state", help="Latest per-signal state for one ticker")
    p_state.add_argument("ticker", help="Ticker symbol (e.g. NVDA)")

    # profile
    p_profile = sub.add_parser("profile", help="Descriptive fire metrics for a signal")
    p_profile.add_argument("signal_id", help="Signal ID (e.g. rsi14_oversold)")
    p_profile.add_argument(
        "--tickers", default=None,
        help="Comma-separated ticker list (e.g. AAPL,MSFT,NVDA)",
    )
    p_profile.add_argument(
        "--sample", type=int, default=None,
        help="Run on first N tickers of the universe",
    )
    p_profile.add_argument(
        "--horizon", type=int, action="append",
        metavar="{10|21|42|63}",
        help="Horizon in trading days (repeatable). Must be in {10,21,42,63}.",
    )

    # series
    p_series = sub.add_parser("series", help="Per-bar signal series tail for debugging")
    p_series.add_argument("signal_id", help="Signal ID")
    p_series.add_argument("ticker", help="Ticker symbol")
    p_series.add_argument(
        "--tail", type=int, default=50,
        help="Number of trailing bars to return (default 50)",
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.subcommand:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "list": cmd_list,
        "state": cmd_state,
        "profile": cmd_profile,
        "series": cmd_series,
    }

    fn = dispatch.get(args.subcommand)
    if fn is None:
        parser.print_help()
        sys.exit(1)

    result = fn(args)
    print(json.dumps(result, indent=2, default=str))

    # Exit 0 on honest nulls; exit 1 only on hard errors
    if isinstance(result, dict) and "error" in result and "n_fires" not in result:
        # Only exit non-zero if it's a hard error (bad signal, no data)
        # Honest null (zero fires) exits 0
        sys.exit(1)


if __name__ == "__main__":
    main()
