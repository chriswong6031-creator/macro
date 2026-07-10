"""scripts/build_intraday_flow.py — Intraday Flow Tracker builder (IFT A1).

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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Allow standalone execution.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader
from lib import config

log = logging.getLogger(__name__)

# Sidecar filename (mirrors basket_pulse pattern).
_LASTGOOD_FILENAME = "flow_pulse_lastgood.json"

# States that qualify for L6 (UPTURN_WATCH or better).
_UPTURN_QUALIFYING = frozenset({"UPTURN_WATCH", "UPTURN_CONFIRMED"})

# Minimum daily volume (shares) to compute meaningful vol-share curve.
_MIN_ADV_SHARES = 500_000


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

    df["_date"] = df[ts_col].dt.date
    unique_dates = sorted(df["_date"].unique())

    if len(unique_dates) < 2:
        return None, None

    # Use up to trailing 20 sessions (excluding today) for the baseline.
    today = date.today()
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
    today = date.today()
    day_df = df[df[ts_col].dt.date == today]
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

    return ctx


def _load_options_entry(ticker: str, data_root: Path) -> dict | None:
    """Load options_entry context for a ticker from state.parquet.

    Returns a slim dict with gamma_regime, dist_to_flip_pct, walls or None.
    """
    p = data_root / "options_entry" / "state.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if "ticker" not in df.columns:
            return None
        row = df[df["ticker"] == ticker]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "gamma_regime": _safe_field(r, "gamma_regime"),
            "dist_to_flip_pct": _safe_field(r, "dist_to_flip_pct"),
            "walls": _safe_field(r, "walls"),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("build_intraday_flow: options_entry read failed: %s", e)
        return None


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

    # Options entry context.
    rec["options_entry"] = _load_options_entry(ticker, data_root)

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
        rendered = tpl.render(intraday_flow=payload)
        html_out = site_root / "intraday_flow.html"
        html_out.write_text(rendered)
        log.info("build_intraday_flow nightly: rendered %s", html_out)
    except Exception as e:  # noqa: BLE001
        log.warning("build_intraday_flow nightly: HTML render failed: %s", e)


# ── fastpath mode ─────────────────────────────────────────────────────────────

def _run_fastpath(cfg: dict, data_root: Path, site_root: Path) -> None:
    """Fastpath mode: compute live pulse from today's intraday bars.

    Writes site/live/flow_pulse.json + site/live/flow_pulse_lastgood.json.
    Zero data/ writes (HOUSE-U5).
    """
    from engine.intraday_flow import (
        higher_lows,
        session_vwap,
        volume_durability,
    )

    ift_cfg = cfg.get("intraday_flow") or {}
    universe = _resolve_universe(cfg, data_root)

    live_dir = site_root / "live"
    live_dir.mkdir(parents=True, exist_ok=True)

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

            vwap = session_vwap(bars)
            cum_vol = sum(b.get("volume") or 0 for b in bars)
            vol_dur = volume_durability(bars, baseline_curve=None)
            hl = higher_lows(bars)
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
