"""scripts/build_intraday_flow.py — Intraday Flow Tracker builder (IFT A1 + A3).

Two modes:

  --mode nightly  (daily.yml render band)
    Reads existing committed/cached stores only (no network).
    Produces site/flowtracker/base.json with per-leader EOD context:
      ADV20, vol-share curve, ATR14, prevClose, washout context,
      mtf_upturn, vol_squeeze, personality, entry_signal,
      options_entry context, premium baselines.
    Renders templates/intraday_flow.html.j2 → site/intraday_flow.html
    (guarded: logs and skips when template absent — added in stage A2).

  --mode fastpath  (intraday-fastpath.yml, 30-min cadence)
    Reads data/intraday/<T>.parquet today-bars for the universe.
    Computes VWAP, volume_durability, higher_lows, cum vol.
    Writes site/live/flow_pulse.json + site/live/flow_pulse_lastgood.json.
    ZERO data/ writes (HOUSE-U5).

Kill-switch: config intraday_flow.enabled: false → exit 0, no output.
Fail-soft: any per-ticker exception is logged and skipped; script always
exits 0 (additive, like build_flow_desk.py).

Universe resolution: config intraday_flow.universe_baskets resolved via
data/baskets/membership.json ∩ engine.options_universe.gex_symbols().
Falls back to ALWAYS_INCLUDE from mtf_upturn when membership absent.

Data-root override (for fixture generation):
  --data-root <path>  override the data/ directory for store reads.
  Environment variable MACRO_DATA_DIR is also honoured (lower priority
  than --data-root, higher priority than config data_dir).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Allow standalone execution.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader
from lib import config
from engine.intraday_flow import washout_context as _washout_context

log = logging.getLogger(__name__)

# Sidecar filename (mirrors basket_pulse pattern).
_LASTGOOD_FILENAME = "flow_pulse_lastgood.json"

# States that qualify for L6 (UPTURN_WATCH or better).
_UPTURN_QUALIFYING = frozenset({"UPTURN_WATCH", "UPTURN_CONFIRMED"})

# Minimum daily volume (shares) to compute meaningful vol-share curve.
_MIN_ADV_SHARES = 500_000

# Forward ledger — data/intraday_flow/ledger.parquet
_LEDGER_DIR = "intraday_flow"
_LEDGER_FILE = "ledger.parquet"
# Horizons (calendar days) for forward return stamping.
_FWD_HORIZONS: tuple[int, ...] = (1, 5, 10, 21)


def _ledger_enabled() -> bool:
    """True only when running in the nightly lane.

    Mirrors mtf_upturn._ledger_advance_enabled() — gate: COLLECT_LANE=nightly.
    Intraday lanes MUST NOT write data/ (HOUSE-U5).
    """
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"


def _ledger_path(data_root: Path) -> Path:
    return data_root / _LEDGER_DIR / _LEDGER_FILE


def _load_ledger(data_root: Path) -> pd.DataFrame:
    """Load ledger.parquet; return empty DataFrame with expected schema on miss."""
    p = _ledger_path(data_root)
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("build_intraday_flow: ledger load failed (%s) — starting fresh", e)
        return pd.DataFrame()


def _write_ledger(df: pd.DataFrame, data_root: Path) -> None:
    """Atomic write: temp-file + os.replace (mirrors mtf_upturn pattern)."""
    p = _ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".ift_ledger_tmp_", suffix=".parquet")
    try:
        os.close(fd)
        df.to_parquet(tmp, index=False, engine="pyarrow")
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_close_series(ticker: str, data_root: Path) -> pd.Series | None:
    """Load daily close series for a ticker.

    Search order: data/baskets/ohlcv/<T>.parquet → data/stocks/<T>.parquet.
    Returns a DatetimeIndex float Series sorted ascending, or None on failure.
    """
    for base_dir in ("baskets/ohlcv", "stocks"):
        p = data_root / base_dir / f"{ticker}.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                df.index = pd.to_datetime(df.index)
                s = df["close"].astype(float).dropna().sort_index()
                if len(s) >= 5:
                    return s
            except Exception as e:  # noqa: BLE001
                log.debug(
                    "build_intraday_flow: close series %s/%s failed: %s",
                    base_dir, ticker, e,
                )
    return None


def _fwd_ret(
    close_series: pd.Series,
    entry_date: str,
    horizon_d: int,
) -> float | None:
    """Compute forward return for a single horizon.

    Entry: close on entry_date (or last bar on/before it).
    Exit: close at most horizon_d calendar days later.
    Returns None if data unavailable or the exit bar is not yet covered.
    """
    try:
        ts = pd.Timestamp(entry_date)
        end_ts = ts + pd.Timedelta(days=horizon_d)
        if close_series.index.max() < end_ts:
            return None  # exit day not yet covered — do not grade
        before_entry = close_series[close_series.index <= ts]
        if before_entry.empty:
            return None
        e0 = float(before_entry.iloc[-1])
        if not e0:
            return None
        at_exit = close_series[close_series.index <= end_ts]
        if at_exit.empty:
            return None
        e1 = float(at_exit.iloc[-1])
        return round(e1 / e0 - 1.0, 6)
    except Exception as e:  # noqa: BLE001
        log.debug("build_intraday_flow: _fwd_ret(%s, %d) failed: %s", entry_date, horizon_d, e)
        return None


def _stamp_forward_returns(df: pd.DataFrame, data_root: Path) -> pd.DataFrame:
    """For existing ledger rows with null forward returns, attempt to fill them.

    Iterates unique tickers; loads price series once per ticker.
    Only fills rows where the horizon has now matured.
    Returns the updated DataFrame (modified in-place on the copy passed in).
    """
    if df.empty:
        return df

    for h in _FWD_HORIZONS:
        col = f"fwd_ret_{h}d"
        if col not in df.columns:
            df[col] = None

    for ticker in df["ticker"].unique():
        mask = df["ticker"] == ticker
        rows_for_ticker = df[mask]
        # Skip if all horizons already stamped for all rows.
        unfilled_cols = [
            f"fwd_ret_{h}d" for h in _FWD_HORIZONS
            if rows_for_ticker[f"fwd_ret_{h}d"].isna().any()
        ]
        if not unfilled_cols:
            continue

        close_s = _load_close_series(ticker, data_root)
        if close_s is None:
            continue

        for idx in df[mask].index:
            session = df.at[idx, "session"]
            for h in _FWD_HORIZONS:
                col = f"fwd_ret_{h}d"
                if pd.isna(df.at[idx, col]):
                    v = _fwd_ret(close_s, session, h)
                    if v is not None:
                        df.at[idx, col] = v

    return df


def _append_ledger_rows(
    new_rows: list[dict],
    data_root: Path,
) -> int:
    """Append new session rows + stamp any matured forward returns.

    Idempotent: keep-first per (session, ticker). Nightly-gate checked by caller.

    Returns the number of new rows actually appended.
    """
    if not new_rows:
        return 0
    try:
        df = _load_ledger(data_root)

        # Build existing key set.
        if not df.empty and "session" in df.columns and "ticker" in df.columns:
            existing = set(zip(df["session"].tolist(), df["ticker"].tolist()))
        else:
            existing = set()

        fresh = [r for r in new_rows if (r.get("session"), r.get("ticker")) not in existing]

        # Stamp forward returns on existing rows first.
        df = _stamp_forward_returns(df, data_root)

        if fresh:
            new_df = pd.DataFrame(fresh)
            # Ensure forward-return columns exist on the new slice (all null — not yet matured).
            for h in _FWD_HORIZONS:
                col = f"fwd_ret_{h}d"
                if col not in new_df.columns:
                    new_df[col] = None
            # Stamp forward returns immediately (in case we're running on a stale/historic date).
            new_df = _stamp_forward_returns(new_df, data_root)
            df = pd.concat([df, new_df], ignore_index=True) if not df.empty else new_df

        _write_ledger(df, data_root)
        return len(fresh)
    except Exception as e:  # noqa: BLE001
        log.warning("build_intraday_flow: _append_ledger_rows failed: %s", e)
        return 0


# ── universe resolution ───────────────────────────────────────────────────────

def _resolve_universe(cfg: dict, data_root: Path) -> list[str]:
    """Resolve the per-basket leader universe.

    Intersects the config universe_baskets with:
      1. data/baskets/membership.json — basket → member symbols
      2. engine.options_universe.gex_symbols() — names in the options universe

    Falls back gracefully when either store is absent.
    """
    basket_ids: list[str] = (cfg.get("intraday_flow") or {}).get(
        "universe_baskets", []
    )
    if not basket_ids:
        log.warning("build_intraday_flow: no universe_baskets in config")
        return []

    # Step 1: resolve basket membership.
    mem_path = data_root / "baskets" / "membership.json"
    symbols: set[str] = set()
    if mem_path.exists():
        try:
            mem = json.loads(mem_path.read_text())
            baskets = mem.get("baskets") or {}
            for bid in basket_ids:
                b = baskets.get(bid) or {}
                for m in b.get("members") or []:
                    if isinstance(m, dict):
                        t = m.get("ticker")
                    else:
                        t = m
                    if t and not (m if isinstance(m, dict) else {}).get("removed"):
                        symbols.add(str(t).upper())
        except Exception as e:  # noqa: BLE001
            log.warning("build_intraday_flow: membership.json load failed: %s", e)
    else:
        log.warning("build_intraday_flow: membership.json absent at %s", mem_path)

    # Step 2: intersect with GEX universe (options-eligible names only).
    try:
        from engine.options_universe import gex_symbols
        gex = set(gex_symbols())
        if gex:
            symbols &= gex
    except Exception as e:  # noqa: BLE001
        log.debug("build_intraday_flow: gex_symbols failed (%s) — no intersection", e)

    if not symbols:
        # Last-resort fallback: use mtf_upturn ALWAYS_INCLUDE (Mag7 + AI leaders).
        try:
            from engine.mtf_upturn import ALWAYS_INCLUDE
            symbols = set(ALWAYS_INCLUDE)
            log.warning(
                "build_intraday_flow: universe empty after resolution — "
                "falling back to mtf_upturn.ALWAYS_INCLUDE (%d names)",
                len(symbols),
            )
        except Exception:  # noqa: BLE001
            pass

    result = sorted(symbols)
    log.info("build_intraday_flow: universe = %d symbols", len(result))
    return result


# ── intraday parquet helpers ──────────────────────────────────────────────────

def _load_intraday_bars(ticker: str, data_root: Path) -> pd.DataFrame | None:
    """Load data/intraday/<T>.parquet — hourly OHLCV bars."""
    p = data_root / "intraday" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        # Ensure a date column for session grouping.
        if "date" not in df.columns and isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
            if "index" in df.columns:
                df = df.rename(columns={"index": "timestamp"})
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("build_intraday_flow: intraday/%s unreadable: %s", ticker, e)
        return None


def _adv20_and_curve(ticker: str, data_root: Path) -> tuple[float | None, list[float] | None]:
    """Compute ADV20 in shares and the vol-share curve from trailing 20 sessions.

    Returns (adv20_shares, curve) or (None, None) on missing/insufficient data.
    """
    from engine.intraday_flow import vol_share_curve

    df = _load_intraday_bars(ticker, data_root)
    if df is None or df.empty:
        return None, None

    # Identify the timestamp column.
    ts_col = next(
        (c for c in ("timestamp", "t", "datetime", "time") if c in df.columns), None
    )
    if ts_col is None:
        return None, None

    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    df = df.dropna(subset=[ts_col]).sort_values(ts_col)
    if df.empty:
        return None, None

    # Convert to ET before extracting calendar date — bars are tz-aware ET epochs.
    # date.today() uses the runner locale; pd.Timestamp.now(tz='America/New_York').date()
    # is always ET regardless of runner timezone (fixes the UTC/locale date-boundary mismatch).
    df["_date"] = df[ts_col].dt.tz_convert("America/New_York").dt.date
    unique_dates = sorted(df["_date"].unique())

    if len(unique_dates) < 2:
        return None, None

    # Use up to trailing 20 sessions (excluding today) for the baseline.
    today = pd.Timestamp.now(tz="America/New_York").date()
    hist_dates = [d for d in unique_dates if d < today][-20:]
    if len(hist_dates) < 2:
        # Include today as well when not enough history.
        hist_dates = unique_dates[-20:]

    sessions_bars: list[list[dict]] = []
    daily_totals: list[float] = []

    for d_val in hist_dates:
        day_df = df[df["_date"] == d_val]
        bars = []
        total_vol = 0.0
        for _, row in day_df.iterrows():
            v = float(row.get("volume") or row.get("v") or 0)
            total_vol += v
            bars.append({
                "open": row.get("open") or row.get("o"),
                "high": row.get("high") or row.get("h"),
                "low": row.get("low") or row.get("l"),
                "close": row.get("close") or row.get("c"),
                "volume": v,
            })
        if bars and total_vol > 0:
            sessions_bars.append(bars)
            daily_totals.append(total_vol)

    adv20 = float(np.mean(daily_totals)) if len(daily_totals) >= 2 else None
    # Enforce minimum ADV floor: skip vol-share curve for illiquid names (§3 design).
    if adv20 is not None and adv20 < _MIN_ADV_SHARES:
        return adv20, None
    curve = vol_share_curve(sessions_bars) if len(sessions_bars) >= 2 else None
    return adv20, curve


def _atr14(ticker: str, data_root: Path) -> float | None:
    """14-day ATR as a percentage of closing price from intraday EOD bars."""
    df = _load_intraday_bars(ticker, data_root)
    if df is None or df.empty:
        return None
    # Need high, low, close at daily resolution.
    ts_col = next(
        (c for c in ("timestamp", "t", "datetime", "time") if c in df.columns), None
    )
    if ts_col is None:
        return None
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    df = df.dropna(subset=[ts_col]).sort_values(ts_col)
    df["_date"] = df[ts_col].dt.date

    # Take the last bar of each day as the daily close/high/low.
    daily = (df.groupby("_date")
               .agg(
                   high=pd.NamedAgg(column=df.columns[df.columns.str.contains("high|h$", regex=True)][0] if any(df.columns.str.contains("high|h$", regex=True)) else "high", aggfunc="max"),
                   low=pd.NamedAgg(column=df.columns[df.columns.str.contains("low|l$", regex=True)][0] if any(df.columns.str.contains("low|l$", regex=True)) else "low", aggfunc="min"),
                   close=pd.NamedAgg(column=df.columns[df.columns.str.contains("close|c$", regex=True)][0] if any(df.columns.str.contains("close|c$", regex=True)) else "close", aggfunc="last"),
               )
               .tail(30))
    if len(daily) < 3:
        return None
    try:
        h = pd.to_numeric(daily["high"], errors="coerce")
        lo = pd.to_numeric(daily["low"], errors="coerce")
        c = pd.to_numeric(daily["close"], errors="coerce")
        prev_c = c.shift(1)
        tr = pd.concat([h - lo, (h - prev_c).abs(), (lo - prev_c).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14, min_periods=5).mean().iloc[-1]
        last_c = c.iloc[-1]
        if atr is None or not np.isfinite(atr) or last_c is None or last_c <= 0:
            return None
        return round(float(atr) / float(last_c) * 100, 2)
    except Exception as e:  # noqa: BLE001
        log.debug("build_intraday_flow: ATR14 for %s failed: %s", ticker, e)
        return None


def _today_bars(ticker: str, data_root: Path) -> list[dict]:
    """Return today's hourly bars as a list of dicts."""
    df = _load_intraday_bars(ticker, data_root)
    if df is None or df.empty:
        return []
    ts_col = next(
        (c for c in ("timestamp", "t", "datetime", "time") if c in df.columns), None
    )
    if ts_col is None:
        return []
    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    df = df.dropna(subset=[ts_col]).sort_values(ts_col)
    # Convert to ET before comparing dates (design: bars are tz-aware ET epochs).
    today_et = pd.Timestamp.now(tz="America/New_York").date()
    day_df = df[df[ts_col].dt.tz_convert("America/New_York").dt.date == today_et]
    rows = []
    for _, row in day_df.iterrows():
        rows.append({
            "open": _safe_float(row, ["open", "o"]),
            "high": _safe_float(row, ["high", "h"]),
            "low": _safe_float(row, ["low", "l"]),
            "close": _safe_float(row, ["close", "c"]),
            "volume": _safe_float(row, ["volume", "v"]) or 0.0,
        })
    return rows


def _safe_float(row: Any, keys: list[str]) -> float | None:
    for k in keys:
        v = row.get(k) if hasattr(row, "get") else getattr(row, k, None)
        if v is not None:
            try:
                f = float(v)
                return f if np.isfinite(f) else None
            except (TypeError, ValueError):
                pass
    return None


# ── stockdata context readers ─────────────────────────────────────────────────

def _load_stockdata(ticker: str, site_root: Path) -> dict:
    """Load site/stockdata/<T>.json — graceful empty dict on absence."""
    p = site_root / "stockdata" / f"{ticker}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.debug("build_intraday_flow: stockdata/%s unreadable: %s", ticker, e)
        return {}


def _extract_stockdata_context(sd: dict) -> dict:
    """Extract the fields needed for base.json from a stockdata record.

    Fields:
      - mtf_upturn_state: from external mtf_upturn.json or absent → None
      - vol_squeeze: from sd.vol_squeeze
      - personality: stair_step_leader, failed_breakout_trap, current_mode
      - entry_signal: stop, atr_pct, buy_zone, status
      - prevClose: from sd.tech.price (last close)
    """
    ctx: dict[str, Any] = {}

    # vol_squeeze — top-level key in stockdata.
    vs = sd.get("vol_squeeze") or {}
    if vs:
        ctx["vol_squeeze"] = {
            "state": vs.get("state"),
            "coiled": vs.get("coiled"),
            "days_compressed": vs.get("days_compressed"),
        }
    else:
        ctx["vol_squeeze"] = None

    # personality — may be in sd.personality (when build_stock_library writes it).
    pers = sd.get("personality") or {}
    base_chart = pers.get("base", {}).get("chart_personality") or pers.get("chart_personality") or {}
    labels = base_chart.get("labels") or []
    ctx["stair_step_leader"] = "stair_step_leader" in labels if labels else None
    ctx["failed_breakout_trap"] = "failed_breakout_trap" in labels if labels else None
    current_mode = (pers.get("current_mode") or {}).get("modes") or None
    ctx["current_mode"] = current_mode

    # entry_signal — top-level.
    es = sd.get("entry_signal") or {}
    ctx["entry_signal"] = {
        "status": es.get("status"),
        "stop": es.get("stop"),
        "buy_zone": es.get("buy_zone"),
        "atr_pct": es.get("atr_pct"),
        "spot": es.get("spot"),
    } if es else None

    # prevClose — from tech.price.
    tech = sd.get("tech") or {}
    ctx["prev_close"] = tech.get("price")

    # L1 washout inputs — surfaced when stockdata carries them (graceful null otherwise).
    # bb_lower_reclaim_days: sessions since last BB lower-band reclaim event.
    # drawdown_21d_pct: 21-session max drawdown (negative float, e.g. -0.15).
    # recovery_begun: bool, True when close has recovered above the drawdown low.
    ctx["bb_lower_reclaim_days"] = sd.get("bb_lower_reclaim_days")
    ctx["drawdown_21d_pct"] = sd.get("drawdown_21d_pct")
    ctx["recovery_begun"] = sd.get("recovery_begun")

    return ctx


def _dealer_from_gex(ticker: str, site_root: Path) -> dict | None:
    """Read site/gex/<TICKER>.json and return a flat dealer dict per ruling §4.

    Fail-soft: missing file or parse error → None.
    All numeric values pass through NaN/inf→None safety.
    """
    p = site_root / "gex" / f"{ticker}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.debug("build_intraday_flow: gex/%s.json unreadable: %s", ticker, e)
        return None

    def _g(obj: Any, *keys: str) -> Any:
        """Safe nested get; returns None on missing key or bad type."""
        cur = obj
        for k in keys:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(k)
        if cur is None:
            return None
        if isinstance(cur, float) and not np.isfinite(cur):
            return None
        return cur

    summary = d.get("summary") or {}
    regime_pp = summary.get("regime_passport") or {}
    skew = summary.get("skew") or {}
    iv_rank = summary.get("iv_rank") or {}
    em = d.get("expected_move") or {}
    vh = d.get("vol_hole") or {}
    tilt = d.get("tilt") or {}

    return {
        "regime":                   _g(summary, "regime"),
        "structurally_constant":    _g(regime_pp, "structurally_constant"),
        "net_gex_bn":               _g(summary, "net_gex_bn"),
        "gamma_flip":               _g(summary, "gamma_flip"),
        "dist_to_flip_pct":         _g(summary, "dist_to_flip_pct"),
        "call_wall":                _g(summary, "call_wall"),
        "put_wall":                 _g(summary, "put_wall"),
        "call_wall_band":           _g(summary, "call_wall_band"),
        "call_wall_hard":           _g(summary, "call_wall_hard"),
        "call_wall_dist_sigma":     _g(summary, "call_wall_dist_sigma"),
        "put_wall_band":            _g(summary, "put_wall_band"),
        "magnet_up":                _g(summary, "magnet_up"),
        "magnet_down":              _g(summary, "magnet_down"),
        "max_pain":                 _g(summary, "max_pain"),
        "expected_move_daily_pct":  _g(em, "daily_pct"),
        "expected_move_weekly_pct": _g(em, "weekly_pct"),
        "vol_hole_state":           _g(vh, "state"),
        "vol_hole_bias":            _g(vh, "bias"),
        "vol_hole_upper":           _g(vh, "upper"),
        "vol_hole_lower":           _g(vh, "lower"),
        "vol_hole_compression":     _g(vh, "compression"),
        "skew_tone":                _g(skew, "tone"),
        "skew_rr25":                _g(skew, "rr25"),
        "iv30":                     _g(summary, "iv30"),
        "iv_rank_band":             _g(iv_rank, "band"),
        "iv_rank_pct":              _g(iv_rank, "rank_pct"),
        "iv_rank_low_confidence":   _g(iv_rank, "low_confidence"),
        "opex_days":                _g(summary, "opex_days"),
        "tier":                     _g(summary, "tier"),
        "top_oi_share":             _g(summary, "top_oi_share"),
        "tilt_read":                _g(tilt, "read"),
    }


# ivspread band labels per options_ivspread language (bilingual handled in template).
def _ivspread_lean_label(ivspread_rel: Any) -> str | None:
    """Map ivspread_rel float to a plain-text lean label."""
    try:
        v = float(ivspread_rel)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    if v >= 0.015:
        return "calls richer (bullish lean)"
    if v >= 0.005:
        return "mild call richness"
    if v <= -0.015:
        return "puts richer (hedge bid)"
    if v <= -0.005:
        return "mild put richness"
    return "balanced"


def _load_options_entry(ticker: str, data_root: Path, site_root: Path) -> dict | None:
    """Load options_entry context for a ticker.

    Keeps v1 keys (gamma_regime, dist_to_flip_pct, walls) for back-compat.
    Adds:
      - dealer: from _dealer_from_gex (site/gex/<T>.json)
      - ivspread_rel, ivspread_lean, net_doi, evidence_quality: from state.parquet
        (all display-only / inert context; all fail-soft to None)
    """
    # v1 base from state.parquet
    p = data_root / "options_entry" / "state.parquet"
    base: dict[str, Any] = {
        "gamma_regime": None,
        "dist_to_flip_pct": None,
        "walls": None,
    }
    # opex_days from parquet (not present in gex JSON summary; merged into dealer below)
    _parquet_opex_days: Any = None
    if p.exists():
        try:
            df = pd.read_parquet(p)
            if "ticker" in df.columns:
                row = df[df["ticker"] == ticker]
                if not row.empty:
                    r = row.iloc[0]
                    base["gamma_regime"] = _safe_field(r, "gamma_regime")
                    base["dist_to_flip_pct"] = _safe_field(r, "dist_to_flip_pct")
                    base["walls"] = _safe_field(r, "walls")
                    # Supplementary context (display-only, inert)
                    ivspread_rel = _safe_field(r, "ivspread_rel")
                    base["ivspread_rel"] = ivspread_rel
                    base["ivspread_lean"] = _ivspread_lean_label(ivspread_rel)
                    base["net_doi"] = _safe_field(r, "net_doi")
                    base["evidence_quality"] = _safe_field(r, "evidence_quality")
                    # opex_days: not in gex JSON summary, sourced from parquet
                    _parquet_opex_days = _safe_field(r, "opex_days")
        except Exception as e:  # noqa: BLE001
            log.debug("build_intraday_flow: options_entry read failed: %s", e)

    # Ensure supplementary keys always present (fail-soft on missing parquet)
    for k in ("ivspread_rel", "ivspread_lean", "net_doi", "evidence_quality"):
        base.setdefault(k, None)

    # dealer from gex JSON (pure site→site join); merge parquet opex_days into it
    dealer = _dealer_from_gex(ticker, site_root)
    if dealer is not None and dealer.get("opex_days") is None and _parquet_opex_days is not None:
        dealer["opex_days"] = _parquet_opex_days
    base["dealer"] = dealer

    return base


def _load_baselines(ticker: str, data_root: Path) -> dict | None:
    """Load premium baselines for a ticker from data/live_flow_baselines/baselines.json."""
    p = data_root / "live_flow_baselines" / "baselines.json"
    if not p.exists():
        return None
    try:
        bl = json.loads(p.read_text())
        return bl.get(ticker) or bl.get(ticker.upper())
    except Exception as e:  # noqa: BLE001
        log.debug("build_intraday_flow: baselines.json load failed: %s", e)
        return None


def _load_daily_bars(ticker: str, data_root: Path, site_root: Path) -> "pd.DataFrame | None":
    """Load up to 120 sessions of daily OHLCV bars for a ticker.

    Priority:
      1. <data_root>/stocks/<T>.parquet  (columns: close, high, low, volume)
      2. <site_root>/ohlc/<T>.json       (chart store, if present)
      3. None (graceful absence)

    Returns a DataFrame with at minimum close/high/low columns, date-ordered
    ascending, tailed to the last 120 rows. The caller should further tail
    before expensive computation.
    """
    # 1. Try daily parquet store.
    parquet_path = data_root / "stocks" / f"{ticker}.parquet"
    if parquet_path.exists():
        try:
            df = pd.read_parquet(parquet_path)
            # Ensure date-ascending order.
            if not df.index.is_monotonic_increasing:
                df = df.sort_index()
            return df.tail(120)
        except Exception as e:  # noqa: BLE001
            log.debug("build_intraday_flow: daily bars parquet %s failed: %s", parquet_path, e)

    # 2. Fall back to site/ohlc/<T>.json (chart store).
    ohlc_path = site_root / "ohlc" / f"{ticker}.json"
    if ohlc_path.exists():
        try:
            raw = json.loads(ohlc_path.read_text())
            # Chart store schema: {"dates": [...], "o": [...], "h": [...], "l": [...], "c": [...], "v": [...]}
            # or a list of {date, open, high, low, close, volume} dicts.
            if isinstance(raw, list):
                df = pd.DataFrame(raw)
                rename = {}
                for src, dst in [("date", "date"), ("o", "open"), ("h", "high"),
                                  ("l", "low"), ("c", "close"), ("v", "volume")]:
                    if src in df.columns and dst not in df.columns:
                        rename[src] = dst
                if rename:
                    df = df.rename(columns=rename)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"], errors="coerce")
                    df = df.set_index("date").sort_index()
            elif isinstance(raw, dict) and "c" in raw:
                dates = raw.get("dates") or raw.get("t") or []
                df = pd.DataFrame({
                    "open":   raw.get("o", [None] * len(dates)),
                    "high":   raw.get("h", [None] * len(dates)),
                    "low":    raw.get("l", [None] * len(dates)),
                    "close":  raw.get("c", [None] * len(dates)),
                    "volume": raw.get("v", [None] * len(dates)),
                }, index=pd.to_datetime(dates, errors="coerce"))
                df = df.sort_index()
            else:
                return None
            return df.tail(120) if not df.empty else None
        except Exception as e:  # noqa: BLE001
            log.debug("build_intraday_flow: ohlc json %s failed: %s", ohlc_path, e)

    return None


def _load_mtf_upturn(ticker: str, site_root: Path) -> dict | None:
    """Load mtf_upturn context from site/stockdata/mtf_upturn.json."""
    p = site_root / "stockdata" / "mtf_upturn.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
        tickers = d.get("tickers") or {}
        return tickers.get(ticker)
    except Exception as e:  # noqa: BLE001
        log.debug("build_intraday_flow: mtf_upturn.json load failed: %s", e)
        return None


def _safe_field(row: Any, key: str) -> Any:
    """Safe extraction from a pandas Series row."""
    try:
        v = row[key]
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return None
        return v
    except (KeyError, TypeError):
        return None


# ── nightly mode ─────────────────────────────────────────────────────────────

def _build_leader_record(
    ticker: str,
    data_root: Path,
    site_root: Path,
) -> dict:
    """Assemble the per-leader record for base.json.

    All fields are graceful-null on missing stores.
    """
    rec: dict[str, Any] = {"ticker": ticker, "built": str(date.today())}

    # ADV20 and vol-share curve from intraday store.
    try:
        adv20, curve = _adv20_and_curve(ticker, data_root)
    except Exception as e:  # noqa: BLE001
        log.debug("build_intraday_flow: ADV20/curve for %s failed: %s", ticker, e)
        adv20, curve = None, None
    rec["adv20_shares"] = adv20
    rec["vol_share_curve"] = curve

    # ATR14 from intraday store.
    try:
        rec["atr14_pct"] = _atr14(ticker, data_root)
    except Exception as e:  # noqa: BLE001
        log.debug("build_intraday_flow: ATR14 for %s failed: %s", ticker, e)
        rec["atr14_pct"] = None

    # EOD context from stockdata.
    sd = _load_stockdata(ticker, site_root)
    sd_ctx = _extract_stockdata_context(sd)
    rec.update(sd_ctx)

    # mtf_upturn state from dedicated artifact.
    mtu = _load_mtf_upturn(ticker, site_root)
    if mtu:
        rec["mtf_upturn_state"] = mtu.get("state")
        rec["mtf_upturn_K"] = mtu.get("K")
    else:
        rec["mtf_upturn_state"] = None
        rec["mtf_upturn_K"] = None

    # Washout context — computed from daily bars when available; falls back
    # to the sd.get() values already set by _extract_stockdata_context.
    try:
        daily_bars = _load_daily_bars(ticker, data_root, site_root)
        if daily_bars is not None and not daily_bars.empty:
            wctx = _washout_context(daily_bars.tail(120), lookback=90)
            # Override sd fallback values with computed values (non-None wins).
            if wctx.get("bb_lower_reclaim_days") is not None:
                rec["bb_lower_reclaim_days"] = wctx["bb_lower_reclaim_days"]
            if wctx.get("drawdown_21d_pct") is not None:
                rec["drawdown_21d_pct"] = wctx["drawdown_21d_pct"]
            if wctx.get("recovery_begun") is not None:
                rec["recovery_begun"] = wctx["recovery_begun"]
    except Exception as e:  # noqa: BLE001
        log.debug("build_intraday_flow: washout_context for %s failed: %s", ticker, e)

    # Options entry context (v2: enriched with dealer block from gex JSON).
    rec["options_entry"] = _load_options_entry(ticker, data_root, site_root)

    # Premium baselines.
    rec["baselines"] = _load_baselines(ticker, data_root)

    return rec


def _run_nightly(cfg: dict, data_root: Path, site_root: Path, tpl_root: Path) -> None:
    """Nightly mode: build site/flowtracker/base.json and render HTML."""
    ift_cfg = cfg.get("intraday_flow") or {}
    universe = _resolve_universe(cfg, data_root)

    out_dir = site_root / "flowtracker"
    out_dir.mkdir(parents=True, exist_ok=True)

    as_of = datetime.now(timezone.utc).isoformat()

    # Build per-ticker basket map for client-side filtering.
    tk_baskets: dict[str, list[str]] = {}
    basket_ids: list[str] = ift_cfg.get("universe_baskets", [])
    mem_path = data_root / "baskets" / "membership.json"
    if mem_path.exists():
        try:
            mem = json.loads(mem_path.read_text())
            baskets_map = mem.get("baskets") or {}
            for bid in basket_ids:
                b = baskets_map.get(bid) or {}
                for m in b.get("members") or []:
                    t = m.get("ticker") if isinstance(m, dict) else m
                    if t:
                        t = str(t).upper()
                        tk_baskets.setdefault(t, [])
                        if bid not in tk_baskets[t]:
                            tk_baskets[t].append(bid)
        except Exception as e:  # noqa: BLE001
            log.debug("build_intraday_flow: basket map build failed: %s", e)

    leaders: list[dict] = []

    for ticker in universe:
        try:
            rec = _build_leader_record(ticker, data_root, site_root)
            rec["baskets"] = tk_baskets.get(ticker, [])
            leaders.append(rec)
        except Exception as e:  # noqa: BLE001
            log.warning("build_intraday_flow nightly: %s failed (skipped): %s", ticker, e)

    payload: dict[str, Any] = {
        "schema": "intraday_flow_base.v1",
        "built_utc": as_of,
        "as_of": as_of,
        "n_leaders": len(leaders),
        "universe_baskets": ift_cfg.get("universe_baskets", []),
        "rvol_confirm": ift_cfg.get("rvol_confirm", 1.30),
        "durability_min": ift_cfg.get("durability_min", 0.60),
        "washout_lookback": ift_cfg.get("washout_lookback", 10),
        "direction_note": (
            "~net call premium direction is SOFT — "
            "approximate (minute tick-rule signing, RUL-F3.12)"
        ),
        "leaders": leaders,
    }

    out_path = out_dir / "base.json"
    out_path.write_text(json.dumps(payload, separators=(",", ":"), default=_json_default))
    log.info(
        "build_intraday_flow nightly: wrote %s (%d leaders, %d bytes)",
        out_path, len(leaders), out_path.stat().st_size,
    )

    # ── Forward ledger (nightly-only, COLLECT_LANE gate) ──────────────────────
    # Append one row per leader with EOD confluence legs + price snapshot.
    # Subsequent runs stamp t+1/t+5/t+10/t+21 forward returns.
    # Gated on COLLECT_LANE=nightly (HOUSE-U5 compliance).
    _advance_ledger(leaders, data_root, site_root, as_of)

    # ── run_status registration (P0.7 law) ────────────────────────────────────
    try:
        from lib import store as _store         # noqa: PLC0415
        _rs = _store.read_status()
        # Repo-relative path only: run_status.json is a committed registry — an
        # absolute path would leak the local checkout/worktree location.
        try:
            _bj = str(out_path.resolve().relative_to(Path(config.ROOT).resolve()))
        except ValueError:
            _bj = "/".join(out_path.parts[-2:])
        _rs.setdefault("sources", {})["intraday_flow_nightly"] = {
            "status":     "ok",
            "n_leaders":  len(leaders),
            "base_json":  _bj,
            "as_of":      as_of,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        _store.write_status(_rs)
        log.info("build_intraday_flow nightly: run_status updated")
    except Exception as _rs_err:  # noqa: BLE001
        log.debug("build_intraday_flow nightly: run_status write failed (non-fatal): %s", _rs_err)

    # Render HTML if template exists (stage A2 adds the template).
    tpl_path = tpl_root / "intraday_flow.html.j2"
    if not tpl_path.exists():
        log.info(
            "build_intraday_flow nightly: template %s absent — "
            "HTML render deferred to stage A2",
            tpl_path,
        )
        return

    try:
        env = Environment(loader=FileSystemLoader(str(tpl_root)), autoescape=False)
        tpl = env.get_template("intraday_flow.html.j2")
        # Coerce numpy/parquet scalar types to pure-python before render: Jinja's
        # `tojson` filter uses the stdlib encoder (not our _json_default), so a
        # numpy int64/float64 introduced by the state.parquet enrichment
        # (net_doi, ivspread_rel) would otherwise abort the whole HTML render.
        payload_safe = json.loads(json.dumps(payload, default=_json_default))
        rendered = tpl.render(intraday_flow=payload_safe)
        html_out = site_root / "intraday_flow.html"
        html_out.write_text(rendered)
        log.info("build_intraday_flow nightly: rendered %s", html_out)
    except Exception as e:  # noqa: BLE001
        log.warning("build_intraday_flow nightly: HTML render failed: %s", e)


# ── ledger advance (nightly helper) ──────────────────────────────────────────

def _advance_ledger(
    leaders: list[dict],
    data_root: Path,
    site_root: Path,
    as_of_utc: str,
) -> None:
    """Build ledger rows from the nightly leaders list and append.

    Each row captures EOD leg booleans (computed from the base.json context),
    K, close price, session date, and null forward-return slots.

    Gate: COLLECT_LANE=nightly (HOUSE-U5). Falls back silently when the price
    stores or confluence engine are absent.
    """
    if not _ledger_enabled():
        log.debug(
            "build_intraday_flow: ledger advance skipped "
            "(COLLECT_LANE != nightly)"
        )
        return

    try:
        from engine.intraday_flow import confluence_legs  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        log.warning("build_intraday_flow: confluence_legs import failed: %s", e)
        return

    # Try importing stance(); graceful if engine hasn't landed yet (nightly fills it once).
    _stance_fn = None
    try:
        from engine.intraday_flow import stance as _stance_fn  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        log.debug("build_intraday_flow: stance() not yet importable — stance column will be null")

    today_str = str(date.today())
    new_rows: list[dict] = []

    for rec in leaders:
        ticker = rec.get("ticker")
        if not ticker:
            continue
        try:
            # Compute confluence legs from nightly EOD context.
            # At nightly time there are no intraday bars, so intraday-only
            # metrics (RVOL_tod, vol_durability, flow metrics) are null.
            # The row captures the EOD setup snapshot; intraday metrics
            # are left null and are the subject of future accrual research.
            mtu_state = rec.get("mtf_upturn_state")
            # L1 washout inputs: base.json may carry bb_lower_reclaim_days
            # if the stockdata reader populates it; else both remain None.
            legs = confluence_legs(
                bb_lower_reclaim_days=rec.get("bb_lower_reclaim_days"),
                drawdown_21d_pct=rec.get("drawdown_21d_pct"),
                recovery_begun=rec.get("recovery_begun"),
                # L2: at nightly, price == prev_close (no intraday VWAP).
                price=rec.get("prev_close"),
                prev_close=rec.get("prev_close"),
                # L3/L4/L5 are intraday-only — leave as None.
                rvol_tod_val=None,
                vol_durability_val=None,
                cum_ncp=None,
                flow_durability_val=None,
                # L6
                mtf_upturn_state=mtu_state,
                # L7
                failed_breakout_trap=rec.get("failed_breakout_trap"),
            )
            # EOD stance from stance() over settled legs + dealer context.
            # guard: stance() may not yet be importable when engine hasn't landed.
            _eod_stance: str | None = None
            if _stance_fn is not None:
                try:
                    dealer = (rec.get("options_entry") or {}).get("dealer")
                    _eod_stance = _stance_fn(legs=legs, dealer=dealer)
                except Exception as _se:  # noqa: BLE001
                    log.debug(
                        "build_intraday_flow: stance() for %s failed: %s", ticker, _se
                    )

            row: dict[str, Any] = {
                "session":        today_str,
                "ticker":         ticker,
                "built_utc":      as_of_utc,
                # Confluence legs (EOD context; intraday legs null at stamp time)
                "L1_washout_recent":  legs.L1_washout_recent,
                "L2_reclaim":         legs.L2_reclaim,
                "L3_rvol_elevated":   legs.L3_rvol_elevated,
                "L4_vol_durable":     legs.L4_vol_durable,
                "L5_flow_bid":        legs.L5_flow_bid,
                "L6_upturn_organ":    legs.L6_upturn_organ,
                "L7_leader_quality":  legs.L7_leader_quality,
                "K":                  legs.K,
                # EOD stance (categorical label from stance(); null until engine lands)
                "stance":             _eod_stance,
                # EOD snapshot metrics
                "close":              rec.get("prev_close"),
                "mtf_upturn_state":   mtu_state,
                "mtf_upturn_K":       rec.get("mtf_upturn_K"),
                "failed_breakout_trap": rec.get("failed_breakout_trap"),
                # Intraday metrics (null at nightly stamp; future research accrual).
                "rvol_tod_close":     None,
                "cum_ncp":            None,
                "flow_durability_eod": None,
            }
            new_rows.append(row)
        except Exception as e:  # noqa: BLE001
            log.debug("build_intraday_flow: ledger row for %s failed: %s", ticker, e)

    if not new_rows:
        log.info("build_intraday_flow: ledger advance: no rows to append")
        return

    appended = _append_ledger_rows(new_rows, data_root)
    ledger_path = _ledger_path(data_root)
    log.info(
        "build_intraday_flow: ledger advance: %d new rows appended → %s",
        appended, ledger_path,
    )


# ── fastpath mode ─────────────────────────────────────────────────────────────

def _load_base_json_index(site_root: Path) -> dict[str, dict]:
    """Load site/flowtracker/base.json and return a dict keyed by ticker.

    Used by the fastpath to access per-ticker ADV20 and vol_share_curve for the
    full L4 metric definition (volume ≥ time-of-day baseline gate, §2.2/§2.5).
    Returns an empty dict when the file is absent (graceful; first-run or off-hours).
    """
    p = site_root / "flowtracker" / "base.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        leaders = d.get("leaders") or []
        return {r["ticker"]: r for r in leaders if r.get("ticker")}
    except Exception as e:  # noqa: BLE001
        log.debug("_run_fastpath: base.json load failed: %s", e)
        return {}


def _run_fastpath(cfg: dict, data_root: Path, site_root: Path) -> None:
    """Fastpath mode: compute live pulse from today's intraday bars.

    Writes site/live/flow_pulse.json + site/live/flow_pulse_lastgood.json.
    Zero data/ writes (HOUSE-U5).
    """
    from engine.intraday_flow import (
        higher_lows,
        rvol_tod as _rvol_tod,
        session_vwap,
        volume_durability,
    )

    ift_cfg = cfg.get("intraday_flow") or {}
    universe = _resolve_universe(cfg, data_root)

    live_dir = site_root / "live"
    live_dir.mkdir(parents=True, exist_ok=True)

    # Load nightly base.json for per-ticker vol_share_curve and adv20_shares.
    # These are needed for the full L4 volume_durability definition (upper half AND
    # volume ≥ time-of-day baseline — design §2.2/§2.5 + engine docstring §4).
    base_index = _load_base_json_index(site_root)

    now_utc = datetime.now(timezone.utc)
    tickers_out: list[dict] = []

    for ticker in universe:
        try:
            bars = _today_bars(ticker, data_root)
            if not bars:
                tickers_out.append({
                    "ticker": ticker, "bars_today": 0,
                    "vwap": None, "vol_durability": None,
                    "higher_lows": None, "cum_vol": None,
                })
                continue

            # Retrieve vol_share_curve and adv20_shares from nightly base for L4.
            base_rec = base_index.get(ticker) or {}
            baseline_curve = base_rec.get("vol_share_curve")
            adv20_shares = base_rec.get("adv20_shares")

            vwap = session_vwap(bars)
            cum_vol = sum(b.get("volume") or 0 for b in bars)
            vol_dur = volume_durability(
                bars, baseline_curve=baseline_curve, adv20_shares=adv20_shares
            )
            hl = higher_lows(bars)

            # ── NEW fastpath fields (ruling §4) ──────────────────────────────
            # rvol_tod: cum_vol / (adv20_shares × expected_share_at_current_bar)
            # expected_share: baseline_curve[min(bar_idx, len-1)] if curve present
            _expected_share: float | None = None
            if baseline_curve and len(bars) > 0:
                bar_idx = min(len(bars) - 1, len(baseline_curve) - 1)
                _expected_share = baseline_curve[bar_idx]
            _rvol_tod_val = _rvol_tod(
                cum_vol_today=cum_vol if cum_vol > 0 else None,
                adv20_shares=adv20_shares,
                expected_share=_expected_share,
            )
            # session_high / session_low: max/min of bar highs/lows
            _highs = [b.get("high") for b in bars if b.get("high") is not None]
            _lows  = [b.get("low")  for b in bars if b.get("low")  is not None]
            _session_high = float(max(_highs)) if _highs else None
            _session_low  = float(min(_lows))  if _lows  else None
            # bars_above_vwap: count of bars whose close >= session vwap
            _bars_above_vwap: int | None = None
            if vwap is not None:
                _bars_above_vwap = sum(
                    1 for b in bars
                    if b.get("close") is not None and b["close"] >= vwap
                )

            tickers_out.append({
                "ticker": ticker,
                "bars_today": len(bars),
                "vwap": vwap,
                "vol_durability": vol_dur,
                "higher_lows": hl,
                "cum_vol": cum_vol,
                "last_close": (bars[-1].get("close") if bars else None),
                "last_high": (bars[-1].get("high") if bars else None),
                "last_low": (bars[-1].get("low") if bars else None),
                # NEW §4 fastpath fields
                "rvol_tod":          _rvol_tod_val,
                "session_high":      _session_high,
                "session_low":       _session_low,
                "bars_above_vwap":   _bars_above_vwap,
            })
        except Exception as e:  # noqa: BLE001
            log.debug("build_intraday_flow fastpath: %s failed: %s", ticker, e)

    # Determine mode (mirrors basket_pulse mode hierarchy).
    mode = "fastpath"
    has_data = any(t.get("bars_today", 0) > 0 for t in tickers_out)
    if not has_data:
        mode = "no_data"

    pulse: dict[str, Any] = {
        "schema": "flow_pulse.v1",
        "as_of": now_utc.isoformat(),
        "as_of_ms": int(now_utc.timestamp() * 1000),
        "mode": mode,
        "stale": False,
        "n_tickers": len(tickers_out),
        "direction_note": (
            "Volume durability is deterministic. VWAP is an hourly-bar "
            "approximation, labeled. Options flow velocity computed client-side "
            "from R2 feed (~-soft per RUL-F3.12)."
        ),
        "tickers": tickers_out,
    }

    out_path = live_dir / "flow_pulse.json"
    out_path.write_text(json.dumps(pulse, separators=(",", ":"), default=_json_default))
    log.info(
        "build_intraday_flow fastpath: wrote %s (%d tickers, mode=%s)",
        out_path, len(tickers_out), mode,
    )

    # Write lastgood sidecar when data is present (mirrors basket_pulse pattern).
    if has_data:
        lastgood_path = live_dir / _LASTGOOD_FILENAME
        lastgood_path.write_text(
            json.dumps(pulse, separators=(",", ":"), default=_json_default)
        )
        log.info("build_intraday_flow fastpath: updated lastgood sidecar")


# ── JSON serialiser ───────────────────────────────────────────────────────────

def _json_default(obj: Any) -> Any:
    """Fallback serialiser: numpy scalars → Python, date → str."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if not np.isfinite(float(obj)) else float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# ── entrypoint ────────────────────────────────────────────────────────────────

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    ap = argparse.ArgumentParser(description="Intraday Flow Tracker builder (IFT A1)")
    ap.add_argument(
        "--mode",
        choices=["nightly", "fastpath"],
        default="nightly",
        help="nightly: build base.json + render HTML; fastpath: build flow_pulse.json",
    )
    ap.add_argument(
        "--data-root",
        default=None,
        help="Override data/ directory (for fixture generation / testing)",
    )
    ap.add_argument(
        "--site-root",
        default=None,
        help="Override site/ directory (for fixture generation / testing)",
    )
    args = ap.parse_args()

    cfg = config.load()

    # Kill-switch: config intraday_flow.enabled: false → exit 0 silently.
    ift_cfg = cfg.get("intraday_flow") or {}
    if not ift_cfg.get("enabled", True):
        log.info("build_intraday_flow: disabled in config — skipping")
        return 0

    # Resolve data_root: --data-root > MACRO_DATA_DIR > config.
    if args.data_root:
        data_root = Path(args.data_root).resolve()
    elif os.environ.get("MACRO_DATA_DIR"):
        data_root = Path(os.environ["MACRO_DATA_DIR"]).resolve()
    else:
        data_root = config.data_dir()

    if args.site_root:
        site_root = Path(args.site_root).resolve()
    else:
        site_root = config.ROOT / cfg["storage"]["site_dir"]
    tpl_root = config.ROOT / "templates"

    try:
        if args.mode == "nightly":
            _run_nightly(cfg, data_root, site_root, tpl_root)
        else:
            _run_fastpath(cfg, data_root, site_root)
    except Exception as e:  # noqa: BLE001 — fail-soft; never break the pipeline
        log.error("build_intraday_flow %s: unexpected error: %s", args.mode, e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
