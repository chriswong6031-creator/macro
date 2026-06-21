"""BTC macro-regime P5: Howell net-liquidity stack — DISPLAY-ONLY context.

Assembles the Fed net-liquidity spine (WALCL − RRP − TGA) and optionally
extends it with non-US central-bank balance sheets (BOJ and PBOC via FX),
and money-market funds (MMMFFAQ027S). Computes the YoY rate-of-change and
its 2nd derivative (acceleration), then classifies the impulse state.

BTC ~10-week leading relationship: historically BTC tends to front-run the
net-liquidity direction by ~6–12 weeks (Howell 2022, OECD global-liquidity
cycle).  This lag is DOCUMENTED CONTEXT ONLY — it is never wired into any
sizing engine.

FRED series consumed (daily / weekly, auto-ffill):
  Core (required — already in the store via collectors/fred.py):
    WALCL   — Fed balance-sheet total assets (weekly, billions)
    RRPONTSYD — overnight reverse-repo outstanding (daily, billions)
    WTREGEN  — Treasury General Account (weekly, billions)
  Optional extensions (add to config.yml fred.series if you want them):
    MMMFFAQ027S — money-market fund total assets (quarterly, billions)
    JPNASSETS   — Bank of Japan total assets (monthly, JPY billions)
    EXJPUS      — USD/JPY spot (daily, from FRED)
    CNAASSETS   — PBOC total assets (monthly, CNY billions) [may be stale]
    DEXCHUS     — USD/CNY spot (daily, from FRED)

How the store is read: lib/store.read("fred", series_id) returns a DataFrame
whose index is datetime; the primary value column is the FRED series ID
lowercased or the snake_case alias from config. This module reads the
signals.parquet column "net_liquidity_bn" first (the pre-computed core spine
already in the build pipeline) and only falls back to raw FRED assembly when
that column is absent.

Config keys (all under btc_netliq:):
  enabled: true                  # master switch
  yoy_window_d: 252              # trading-day YoY baseline
  accel_window_d: 30             # smoothing for 2nd-derivative
  impulse_expand_accel_thresh: 0 # accel > this → expanding-accelerating
  # no pip deps beyond pandas/numpy already in the repo
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

_CORE_FRED = {
    "walcl": "WALCL",
    "rrp": "RRPONTSYD",
    "tga": "WTREGEN",
}
_EXT_FRED = {
    "mmf": "MMMFFAQ027S",
    "boj_jpy": "JPNASSETS",
    "usdjpy": "EXJPUS",
    "pboc_cny": "CNAASSETS",
    "usdcny": "DEXCHUS",
}


def _f(v):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _read_fred_series(sid: str) -> pd.Series | None:
    """Return the first numeric column of a FRED store entry, or None."""
    df = store.read("fred", sid)
    if df is None or df.empty:
        return None
    num = df.select_dtypes(include="number")
    if num.empty:
        return None
    s = num.iloc[:, 0].dropna()
    return s if not s.empty else None


def _safe_last(s: pd.Series | None) -> float | None:
    if s is None or s.empty:
        return None
    return _f(s.iloc[-1])


def _align(*series: pd.Series) -> pd.DataFrame:
    """Union-index all series, forward-fill with a 90-day cap."""
    df = pd.concat(series, axis=1)
    df.index = pd.to_datetime(df.index)
    return df.sort_index().ffill(limit=90)


def _impulse_state(yoy: float | None, accel: float | None,
                   expand_accel_thresh: float = 0.0) -> str:
    if yoy is None:
        return "unknown"
    if yoy < 0:
        return "contracting"
    if accel is None or accel > expand_accel_thresh:
        return "expanding-accelerating"
    return "expanding-decelerating"


def compute(sig_df: pd.DataFrame | None = None) -> dict:
    """Build the Howell net-liquidity card. Never raises.

    Parameters
    ----------
    sig_df:
        Optional pre-loaded signals.parquet DataFrame. When None the function
        tries store.read("vector", "signals") to obtain net_liquidity_bn.
    """
    try:
        cfg = config.load().get("btc_netliq", {})
        if not cfg.get("enabled", True):
            return {"ok": False, "reason": "btc_netliq disabled in config"}

        yoy_w = int(cfg.get("yoy_window_d", 252))
        accel_w = int(cfg.get("accel_window_d", 30))
        expand_thresh = float(cfg.get("impulse_expand_accel_thresh", 0.0))

        # ------------------------------------------------------------------ #
        # Step 1: try the pre-computed column first
        # ------------------------------------------------------------------ #
        netliq: pd.Series | None = None
        components_present: list[str] = []
        source_note = ""

        if sig_df is not None and "net_liquidity_bn" in sig_df.columns:
            netliq = sig_df["net_liquidity_bn"].dropna()
            components_present = ["walcl", "rrp", "tga"]
            source_note = "pre-computed net_liquidity_bn from signals.parquet"
        else:
            # try to load signals parquet ourselves
            _sdf = store.read("vector", "signals")
            if _sdf is not None and "net_liquidity_bn" in _sdf.columns:
                netliq = _sdf["net_liquidity_bn"].dropna()
                components_present = ["walcl", "rrp", "tga"]
                source_note = "pre-computed net_liquidity_bn from signals.parquet"

        # ------------------------------------------------------------------ #
        # Step 2: fallback — assemble from raw FRED series
        # ------------------------------------------------------------------ #
        if netliq is None or netliq.empty:
            walcl = _read_fred_series("WALCL")
            rrp = _read_fred_series("RRPONTSYD")
            tga = _read_fred_series("WTREGEN")
            if walcl is None:
                return {"ok": False, "reason": "WALCL not in store; core series absent"}
            parts = {"walcl": walcl}
            if rrp is not None:
                parts["rrp"] = rrp
                components_present.append("rrp")
            else:
                log.warning("btc_netliq: RRPONTSYD absent, skipping from core")
            if tga is not None:
                parts["tga"] = tga
                components_present.append("tga")
            else:
                log.warning("btc_netliq: WTREGEN absent, skipping from core")
            components_present.insert(0, "walcl")

            df_raw = _align(*parts.values())
            df_raw.columns = list(parts.keys())
            core = df_raw["walcl"]
            if "rrp" in df_raw:
                core = core - df_raw["rrp"]
            if "tga" in df_raw:
                core = core - df_raw["tga"]
            netliq = core.dropna()
            source_note = "assembled from raw FRED series"

        if netliq.empty:
            return {"ok": False, "reason": "net_liquidity_bn empty after assembly"}

        # ------------------------------------------------------------------ #
        # Step 3: optional extensions
        # ------------------------------------------------------------------ #
        extensions: list[pd.Series] = []

        # MMF
        mmf = _read_fred_series("MMMFFAQ027S")
        if mmf is not None and not mmf.empty:
            components_present.append("mmf")
            extensions.append(mmf.rename("mmf"))

        # BOJ (JPY bn → USD bn via USDJPY)
        boj_jpy = _read_fred_series("JPNASSETS")
        usdjpy = _read_fred_series("EXJPUS")
        if boj_jpy is not None and usdjpy is not None:
            try:
                df_boj = _align(boj_jpy.rename("boj"), usdjpy.rename("fx"))
                boj_usd = (df_boj["boj"] / df_boj["fx"]).dropna()
                if not boj_usd.empty:
                    components_present.append("boj_usd")
                    extensions.append(boj_usd.rename("boj_usd"))
            except Exception as e:
                log.warning("btc_netliq: BOJ extension failed: %s", e)

        # PBOC (CNY bn → USD bn via USDCNY)
        pboc_cny = _read_fred_series("CNAASSETS")
        usdcny = _read_fred_series("DEXCHUS")
        if pboc_cny is not None and usdcny is not None:
            try:
                df_pboc = _align(pboc_cny.rename("pboc"), usdcny.rename("fx"))
                pboc_usd = (df_pboc["pboc"] / df_pboc["fx"]).dropna()
                if not pboc_usd.empty:
                    components_present.append("pboc_usd")
                    extensions.append(pboc_usd.rename("pboc_usd"))
            except Exception as e:
                log.warning("btc_netliq: PBOC extension failed: %s", e)

        # Combine spine + extensions on a shared daily index
        all_parts = [netliq.rename("core")] + extensions
        if len(all_parts) > 1:
            df_all = _align(*all_parts)
            # Sum extensions, NaN-safe
            ext_cols = [c for c in df_all.columns if c != "core"]
            ext_sum = df_all[ext_cols].sum(axis=1, min_count=1).fillna(0)
            total = df_all["core"] + ext_sum
        else:
            total = netliq.rename("total")

        total = total.sort_index().ffill(limit=14).dropna()

        if len(total) < max(yoy_w, accel_w) // 2:
            return {"ok": False, "reason": f"insufficient history: {len(total)} rows"}

        # ------------------------------------------------------------------ #
        # Step 4: metrics
        # ------------------------------------------------------------------ #
        yoy = (total / total.shift(yoy_w) - 1) * 100   # YoY %
        accel = yoy.diff(accel_w).ewm(span=accel_w, adjust=False).mean()

        last_val = _f(total.iloc[-1])
        last_yoy = _f(yoy.dropna().iloc[-1]) if not yoy.dropna().empty else None
        last_accel = _f(accel.dropna().iloc[-1]) if not accel.dropna().empty else None
        impulse = _impulse_state(last_yoy, last_accel, expand_thresh)

        # 4-week trailing trend for mini-sparkline (display)
        spark = [round(float(v), 1) for v in total.iloc[-28:].tolist()
                 if np.isfinite(float(v))]

        return {
            "ok": True,
            "display_only": True,
            "asof": str(total.index[-1].date()),
            "netliq_bn": round(last_val, 1) if last_val is not None else None,
            "yoy_roc": round(last_yoy, 2) if last_yoy is not None else None,
            "accel": round(last_accel, 3) if last_accel is not None else None,
            "impulse_state": impulse,
            "components_present": components_present,
            "spark": spark,
            "source_note": source_note,
            "note": (
                "Display-only. Howell net-liquidity stack. BTC historically leads "
                "this series by ~6-12 weeks — context, not a trigger. "
                "Extensions (MMF/BOJ/PBOC) degrade gracefully when absent."
            ),
        }
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
