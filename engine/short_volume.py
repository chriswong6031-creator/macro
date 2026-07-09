"""Daily short-volume signal — a CONTEXT confirmer derived from the keyless FINRA
daily short-sale volume panel (collectors/finra_short_volume.py).

For each ticker we compare a short window (default last 5 sessions) against a
baseline window (default last 20) of volume-weighted short ratio
(sum ShortVolume / sum TotalVolume). `trend_pp` = recent - baseline, in
percentage points: positive = off-exchange short flow building *recently* vs the
trailing norm — a fresher read than the bi-monthly short-interest settlement.

`ratio_z` = (latest short_ratio − mean) / std over ALL available history, using
the same formula as build_darkpool_desk.py (nanmean / nanstd, min 5 rows, 0.0
when sigma is zero). Surfaces on the per-stock page as context only.

Honest framing: daily short-volume is noisy and its standalone edge is
modest/contested, so this is surfaced as a positioning confirmer on the stock
page, NOT folded into any scored alpha factor. Pure + import-light so it stays
trivially testable.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_PANEL = ("finra_short_volume", "panel.parquet")


def load_panel(path=None) -> pd.DataFrame | None:
    p = path or (config.data_dir() / _PANEL[0] / _PANEL[1])
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    if df.empty or not {"date", "ticker", "short_vol", "total_vol"} <= set(df.columns):
        return None
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    return df


def _ticker_signal(g: pd.DataFrame, recent: int, baseline: int) -> dict | None:
    g = g.sort_values("date")
    if len(g) < 3:
        return None
    base = g.tail(baseline)
    rec = g.tail(recent)

    def _vw(frame: pd.DataFrame) -> float | None:
        tot = float(frame["total_vol"].sum())
        return round(float(frame["short_vol"].sum()) / tot, 4) if tot > 0 else None

    vw_base = _vw(base)
    vw_rec = _vw(rec)
    latest = g.iloc[-1]
    if vw_base is None or vw_rec is None:
        return None

    # Short ratio for z-score: use pre-computed column if available, else vw_rec
    has_col = "short_ratio" in g.columns and pd.notna(latest.get("short_ratio"))
    short_ratio_latest = float(latest["short_ratio"]) if has_col else vw_rec

    # Z-score vs own full history — same definition as build_darkpool_desk.py:
    # nanmean/nanstd over ALL rows, min 5 rows, 0.0 when sigma is zero.
    if has_col and len(g) >= 5:
        ratios = g["short_ratio"].values
        mu = float(np.nanmean(ratios))
        sigma = float(np.nanstd(ratios))
        ratio_z = round((short_ratio_latest - mu) / sigma, 2) if sigma > 0 else 0.0
    else:
        ratio_z = None

    return {
        "short_ratio": round(short_ratio_latest, 4),
        "ratio_recent": vw_rec,
        "ratio_baseline": vw_base,
        "trend_pp": round((vw_rec - vw_base) * 100, 2),
        "ratio_z": ratio_z,
        "n_days": int(len(g)),
        "asof": str(latest["date"].date()),
    }


def signal_map(panel: pd.DataFrame | None = None, *, recent: int = 5,
               baseline: int = 20) -> dict[str, dict]:
    """{ticker: {short_ratio, ratio_recent, ratio_baseline, trend_pp, ratio_z, n_days, asof}}.
    Empty dict when the panel is missing — callers degrade gracefully."""
    if panel is None:
        panel = load_panel()
    if panel is None or panel.empty:
        return {}
    out: dict[str, dict] = {}
    for tk, g in panel.groupby("ticker"):
        sig = _ticker_signal(g, recent, baseline)
        if sig is not None:
            out[str(tk)] = sig
    return out
