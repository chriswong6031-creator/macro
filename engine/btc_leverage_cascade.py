"""BTC macro-regime P5: funding + OI cascade gate — DISPLAY-ONLY context.

ONE-SIDED: this module can only flag DE-RISK (never add exposure). It is a
hard context gate on the dashboard — when cascade_risk is "high", a
derisk_cap is surfaced for the template to show, but it NEVER modifies any
allocation or regime score.

Signal logic (deterministic, NaN-safe):
  - funding_state: classify the perpetual funding rate regime
      • "high"     — funding_annual_pct ≥ HIGH_FUNDING and sustained ≥ 3 days
      • "elevated" — funding_annual_pct ≥ ELEV_FUNDING
      • "negative" — funding_annual_pct ≤ NEG_FUNDING (shorts paying longs,
                     historically a capitulation signal, NOT risk-off)
      • "neutral"  — otherwise
    Uses funding_z when available to normalize across funding regimes
    (funding_annual_pct alone is regime-sensitive; z-score is more robust).

  - oi_state: classify open-interest crowding
      • "stretched" — oi_mcap_ratio is in the top decile of its rolling window
                      AND oi_change > 0 (still building)
      • "elevated"  — oi_mcap_ratio above the 75th percentile
      • "declining" — oi_change < 0 (OI unwinding, reduces cascade risk)
      • "normal"    — otherwise

  - cascade_risk:
      • "high"     — funding_state=="high" AND oi_state=="stretched"
      • "elevated" — funding_state in {"high","elevated"} AND oi_state in {"stretched","elevated"}
      • "low"      — otherwise (including when either signal is absent)

  derisk_cap (display-only suggested max-exposure cap):
      • "high"     → 0.5 (halve max exposure suggestion)
      • "elevated" → 0.75
      • else       → None (no cap suggested)

Data source note: OKX is the ONLY US-CI-accessible funding-rate source.
Binance and Bybit are geo-blocked in CI. The repo already stores OKX funding
in the signals.parquet columns funding_z / funding_annual_pct / oi_mcap_ratio
/ oi_change (from collectors/bgeo.py). These are read directly from the
pre-computed parquet for maximum build-pipeline safety.

Config keys (under btc_leverage_cascade:):
  enabled: true
  high_funding_annual_pct: 50.0   # annualized % → "high" threshold
  elev_funding_annual_pct: 25.0
  neg_funding_annual_pct: -10.0
  high_funding_z: 1.5             # z-score alternative gate (either OR funding_pct)
  sustain_days: 3                 # consecutive days of high funding required
  oi_top_decile_w: 252            # lookback for OI percentile (trading days)
  oi_top_decile_thresh: 0.90      # percentile → "stretched"
  oi_elev_thresh: 0.75

Dependencies: pandas, numpy (already in repo).  No new pip deps.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)


def _f(v):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _pctile_rank(series: pd.Series, window: int) -> float | None:
    """Return the percentile rank of the last value in a rolling window."""
    if series.dropna().empty or len(series) < window // 4:
        return None
    roll = series.dropna().iloc[-window:]
    if roll.empty:
        return None
    last = _f(roll.iloc[-1])
    if last is None:
        return None
    rank = (roll <= last).sum() / len(roll)
    return float(rank)


def _funding_state(df: pd.DataFrame, cfg: dict) -> str:
    """Classify the funding-rate regime from the signals DataFrame."""
    high_pct = float(cfg.get("high_funding_annual_pct", 50.0))
    elev_pct = float(cfg.get("elev_funding_annual_pct", 25.0))
    neg_pct = float(cfg.get("neg_funding_annual_pct", -10.0))
    high_z = float(cfg.get("high_funding_z", 1.5))
    sustain = int(cfg.get("sustain_days", 3))

    # Prefer funding_annual_pct; fall back to funding_z for the state call
    if "funding_annual_pct" not in df.columns or df["funding_annual_pct"].dropna().empty:
        if "funding_z" not in df.columns or df["funding_z"].dropna().empty:
            return "unknown"
        # z-score path only
        fz = df["funding_z"].dropna()
        last_z = _f(fz.iloc[-1])
        if last_z is None:
            return "unknown"
        recent_high_z = (fz.iloc[-sustain:] >= high_z).all()
        if recent_high_z:
            return "high"
        if last_z >= high_z * 0.6:
            return "elevated"
        if last_z <= -abs(high_z) * 0.6:
            return "negative"
        return "neutral"

    fa = df["funding_annual_pct"].dropna()
    fz_col = df.get("funding_z", pd.Series(dtype=float)).reindex(fa.index).dropna()

    last_fa = _f(fa.iloc[-1])
    if last_fa is None:
        return "unknown"

    last_z = _f(fz_col.iloc[-1]) if not fz_col.empty else None

    # "high" requires sustained high funding for `sustain` consecutive days
    recent = fa.iloc[-sustain:]
    sustained_high_pct = len(recent) >= sustain and (recent >= high_pct).all()
    sustained_high_z = (
        last_z is not None and last_z >= high_z
        and not fz_col.empty and len(fz_col) >= sustain
        and (fz_col.iloc[-sustain:] >= high_z).all()
    )

    if sustained_high_pct or sustained_high_z:
        return "high"
    if last_fa >= elev_pct:
        return "elevated"
    if last_fa <= neg_pct:
        return "negative"
    return "neutral"


def _oi_state(df: pd.DataFrame, cfg: dict) -> str:
    """Classify OI crowding from the signals DataFrame."""
    top_decile_w = int(cfg.get("oi_top_decile_w", 252))
    top_thresh = float(cfg.get("oi_top_decile_thresh", 0.90))
    elev_thresh = float(cfg.get("oi_elev_thresh", 0.75))

    if "oi_mcap_ratio" not in df.columns or df["oi_mcap_ratio"].dropna().empty:
        return "unknown"

    ratio = df["oi_mcap_ratio"].dropna()
    pctile = _pctile_rank(ratio, top_decile_w)
    if pctile is None:
        return "unknown"

    oi_chg: float | None = None
    if "oi_change" in df.columns and not df["oi_change"].dropna().empty:
        oi_chg = _f(df["oi_change"].dropna().iloc[-1])

    building = oi_chg is None or oi_chg >= 0  # None → conservative, assume building
    declining = oi_chg is not None and oi_chg < 0

    if declining:
        return "declining"
    if pctile >= top_thresh and building:
        return "stretched"
    if pctile >= elev_thresh:
        return "elevated"
    return "normal"


def compute(sig_df: pd.DataFrame | None = None) -> dict:
    """Build the leverage-cascade gate card. Never raises.

    Parameters
    ----------
    sig_df:
        Optional pre-loaded signals.parquet DataFrame. When None the function
        reads store.read("vector", "signals") automatically.
    """
    try:
        cfg = config.load().get("btc_leverage_cascade", {})
        if not cfg.get("enabled", True):
            return {"ok": False, "reason": "btc_leverage_cascade disabled in config"}

        # ------------------------------------------------------------------ #
        # Load signals
        # ------------------------------------------------------------------ #
        if sig_df is None:
            sig_df = store.read("vector", "signals")
        if sig_df is None or sig_df.empty:
            return {
                "ok": False,
                "reason": "signals.parquet not found; store may not be built yet",
            }

        df = sig_df.copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # ------------------------------------------------------------------ #
        # Classify states
        # ------------------------------------------------------------------ #
        f_state = _funding_state(df, cfg)
        oi_state = _oi_state(df, cfg)

        # ------------------------------------------------------------------ #
        # Cascade risk
        # ------------------------------------------------------------------ #
        if f_state == "high" and oi_state == "stretched":
            cascade_risk = "high"
            derisk_cap = 0.5
        elif f_state in ("high", "elevated") and oi_state in ("stretched", "elevated"):
            cascade_risk = "elevated"
            derisk_cap = 0.75
        else:
            cascade_risk = "low"
            derisk_cap = None

        # ------------------------------------------------------------------ #
        # Current readings (for the display card)
        # ------------------------------------------------------------------ #
        fa_last = None
        if "funding_annual_pct" in df.columns:
            fa_last = _f(df["funding_annual_pct"].dropna().iloc[-1]
                         if not df["funding_annual_pct"].dropna().empty else None)
        fz_last = None
        if "funding_z" in df.columns:
            fz_last = _f(df["funding_z"].dropna().iloc[-1]
                         if not df["funding_z"].dropna().empty else None)
        oi_ratio_last = None
        if "oi_mcap_ratio" in df.columns:
            oi_ratio_last = _f(df["oi_mcap_ratio"].dropna().iloc[-1]
                               if not df["oi_mcap_ratio"].dropna().empty else None)
        oi_chg_last = None
        if "oi_change" in df.columns:
            oi_chg_last = _f(df["oi_change"].dropna().iloc[-1]
                             if not df["oi_change"].dropna().empty else None)

        asof = str(df.index[-1].date())

        return {
            "ok": True,
            "display_only": True,
            "one_sided": True,   # can only flag de-risk, never add
            "asof": asof,
            "cascade_risk": cascade_risk,
            "funding_state": f_state,
            "oi_state": oi_state,
            "derisk_cap": derisk_cap,
            "funding_annual_pct": round(fa_last, 2) if fa_last is not None else None,
            "funding_z": round(fz_last, 2) if fz_last is not None else None,
            "oi_mcap_ratio": round(oi_ratio_last, 4) if oi_ratio_last is not None else None,
            "oi_change": round(oi_chg_last, 4) if oi_chg_last is not None else None,
            "note": (
                "Display-only, ONE-SIDED (de-risk gate only — never adds exposure). "
                "Reads OKX funding (the only US-CI-accessible source; Binance/Bybit "
                "are geo-blocked). cascade_risk='high' when sustained high funding "
                "AND stretched OI coincide. derisk_cap is a display suggestion only."
            ),
        }
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
