"""BTC intraday aggressor-CVD — the real sub-daily order-flow feed (DISPLAY-ONLY).

The impulse-radar screens concluded that the slow, options-calm flush (e.g.
2026-06-24) leaves NO signature in OHLCV candles, and that the only path to a
pre-alarm is a TRUE sub-daily aggressor-CVD — taker buy vs sell volume from the
exchange, not candle sign. `collectors/okx.py::_taker_volume_hourly` now pulls
OKX rubik taker-volume at 1H (the US-accessible feed) and `store.upsert`
accumulates it forward (the rubik window is ~30 days, recent-only).

This module reads that accruing store and computes:
  - CVD = Σ(taker_buy − taker_sell)  (cumulative volume delta)
  - short-horizon net aggressor flow (24h / 72h) and a sign state
  - the CVD/price DIVERGENCE form the screen identified as the one genuinely
    LEADING shape ("hidden distribution": price firm while cumulative aggressor
    flow turns down) — but ONLY once enough hourly history has accrued.

HONESTY — this is display-only and NOT scored:
  - It is REAL taker CVD (not a candle proxy), so it is the right instrument.
  - But the feed starts ~empty and accrues ~30d/refresh-window forward; until it
    has the months of history to be re-derived under the leak-free falsifier
    (engine/btc_impulse_radar_backtest), it CANNOT be an act-tier leg. It ships
    as an `accruing` context read with an explicit history note. When it matures,
    the divergence form is the candidate to validate and (if it passes) promote.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import store

log = logging.getLogger(__name__)

DIV_W = 720              # causal window for the divergence z-scores (~30d of hours)
RUBIK_WINDOW_H = 720     # OKX rubik 1H serves only ~720h; a gap wider than this is UNbackfillable
STALE_AFTER_H = 48       # hourly feed is STALE if it lags the live intraday reference by >2d
# The divergence PERCENTILE needs DIV_W valid `div` values, and `div` itself only
# becomes valid after a DIV_W causal warmup -> ~2*DIV_W hours before it is real.
MIN_HOURS_DIV = 2 * DIV_W + 72   # ~63d
ACCRUE_NOTE = ("Real OKX taker CVD, accruing forward (~30d/refresh window). "
               "Display-only until it has the months of history to be validated "
               "by the falsifier; not scored, never an act trigger yet.")


def _f(v):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _causal_z(s: pd.Series, w: int) -> pd.Series:
    mu = s.rolling(w).mean().shift(1)
    sd = s.rolling(w).std().shift(1)
    return (s - mu) / sd.replace(0.0, np.nan)


def compute(sig_df: pd.DataFrame | None = None) -> dict:
    """Build the intraday-CVD read. `sig_df` is accepted (context-leg contract)
    but unused — this reads its own hourly stores. Never raises."""
    try:
        h = store.read("okx", "taker_volume_hourly")
        if h is None or h.empty or "taker_buy_vol" not in h.columns:
            return {"ok": False, "reason": "okx/taker_volume_hourly not collected yet",
                    "display_only": True, "accruing": True}
        h = h.copy(); h.index = pd.to_datetime(h.index); h = h.sort_index()
        h = h[~h.index.duplicated(keep="last")]
        okx_last = h.index[-1]
        asof = str(okx_last)

        # FRESHNESS (audit HIGH): if the okx hourly feed silently freezes, okx still
        # reports 'ok' off its DAILY series, so nothing else would notice. Use
        # coinbase/btc_hourly (a DIFFERENT adapter's intraday feed) as the live
        # reference — if okx-hourly lags it by >2d, the feed has stalled.
        stale = False; hours_behind = None
        ref = store.read("coinbase", "btc_hourly")
        if ref is not None and not ref.empty:
            ref_last = pd.to_datetime(ref.index).max()
            hours_behind = round(float((ref_last - okx_last) / pd.Timedelta(hours=1)), 1)
            stale = hours_behind > STALE_AFTER_H

        # GAP (audit MEDIUM): rubik 1H can't backfill a gap wider than its ~720h
        # window, so a sustained outage leaves a permanent hole that a naive cumsum
        # would silently span and corrupt. Detect it and restart the cumsum after
        # the last unbackfillable gap.
        diffs = h.index.to_series().diff()
        big = diffs > pd.Timedelta(hours=RUBIK_WINDOW_H)
        gap_detected = bool(big.any())
        if gap_detected:
            seg_start = int(np.where(big.to_numpy())[0].max())
            h = h.iloc[seg_start:]

        signed = h["taker_buy_vol"] - h["taker_sell_vol"]
        cvd = signed.cumsum()
        n = int(signed.dropna().shape[0])

        net24 = _f(signed.tail(24).sum())
        net72 = _f(signed.tail(72).sum())
        # sign state from the 24h net flow, scaled by typical hourly |flow|
        scale = _f(signed.abs().tail(168).mean()) or 1.0
        z24 = (net24 / (scale * 24 ** 0.5)) if net24 is not None else 0.0
        if z24 is None:
            state = "neutral"
        elif z24 <= -1.0:
            state = "distribution"     # net aggressor SELLING
        elif z24 >= 1.0:
            state = "accumulation"     # net aggressor BUYING
        else:
            state = "neutral"

        out = {
            "ok": True, "display_only": True, "asof": asof, "n_hours": n,
            "stale": bool(stale), "hours_behind_ref": hours_behind,
            "gap_detected": gap_detected,
            "cvd_last_bn": round(_f(cvd.iloc[-1]) / 1e9, 3) if _f(cvd.iloc[-1]) is not None else None,
            "net_flow_24h_mn": round(net24 / 1e6, 1) if net24 is not None else None,
            "net_flow_72h_mn": round(net72 / 1e6, 1) if net72 is not None else None,
            "flow_state": state,
            "accruing": n < MIN_HOURS_DIV,
            "history_note": (f"{n} hourly rows (~{n // 24}d). Need ≥{MIN_HOURS_DIV} "
                             f"(~{MIN_HOURS_DIV // 24}d) for the divergence feature; "
                             "months before it can be falsifier-validated."),
            "divergence": None,
            "note": ACCRUE_NOTE,
        }

        # CVD/price divergence — only once enough history has accrued.
        if n >= MIN_HOURS_DIV:
            px = store.read("coinbase", "btc_hourly")
            if px is not None and not px.empty and "close" in px.columns:
                close = px["close"].copy(); close.index = pd.to_datetime(close.index)
                close = close.sort_index().reindex(cvd.index).ffill()
                ret24 = close / close.shift(24) - 1.0
                price_z = _causal_z(ret24, DIV_W)
                slope_z = _causal_z(cvd.diff(24), DIV_W)
                div = price_z - slope_z                       # high = price up, flow down
                div_pct = div.rolling(DIV_W).rank(pct=True)
                dp = _f(div_pct.iloc[-1])
                if dp is not None:
                    dstate = ("hidden_distribution" if dp >= 0.90
                              else "hidden_accumulation" if dp <= 0.10 else "none")
                    out["divergence"] = {
                        "value": round(_f(div.iloc[-1]), 2) if _f(div.iloc[-1]) is not None else None,
                        "pctile": round(dp, 3), "state": dstate,
                        "note": ("'hidden distribution' = price firm while aggressor flow "
                                 "turns down; the screen's one genuinely-leading shape "
                                 "(~10h lead) — display context, not validated/scored."),
                    }
        return out
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        return {"ok": False, "reason": f"{type(e).__name__}: {e}", "display_only": True, "accruing": True}
