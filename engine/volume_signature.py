"""Accumulation/Distribution Volume Signature — scorecard dimension 4 (Wyckoff up/down-vol split + OBV).

DISPLAY-ONLY · directional: false.

Computes, per basket member, the classic Wyckoff up-volume / down-volume split over a
rolling lookback window and an On-Balance Volume (OBV) slope. The outputs are then
aggregated to the basket level as the median ad_ratio and the fraction of members
classified as 'accumulation'. This is a DESCRIPTIVE lens — it tells you where volume
is concentrating (buyers vs. sellers), not whether price will rise. It is NOT a
forward-return prediction and has NOT been subjected to an IC gate.

HONEST CAVEATS:
- Volume in the store is thin / backfilled for many members: older parquets have no
  volume column at all (StockPriceAdapter started capturing it recently). Members
  without a volume column are silently skipped; baskets with fewer than 3 members
  that have volume history return a neutral structure.
- OBV slope is computed via a simple linear regression over the last `obv_slope_d`
  days, which is noise-sensitive on short histories.
- The ad_ratio thresholds (1.1 / 0.9) are heuristic and not calibrated against
  future returns. This is Wyckoff interpretation, not tested alpha.
- directional:false — never read into regime/axes/macro_risk.

Public API:
    volume_signature(region='us', lookback_d=42, obv_slope_d=20)
    -> dict[theme_id, {ad_ratio, pct_accumulation, signature, n, members}]

Data access mirrors:
- engine.holdings_signals.volume_surge  — how it reads store.read("stocks", ticker)
  and accesses the "volume" column + "close" column.
- engine.group_flow._setup / engine.theme_scoring.compute_theme_intel — how it
  enumerates basket members from _membership() and iterates bdict.items().
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.baskets import _basket_extras, _membership
from engine.equity_factors import _closes
from lib import store

log = logging.getLogger(__name__)

# Classification thresholds (heuristic / Wyckoff convention)
_ACC_RATIO = 1.1   # ad_ratio > this AND obv_slope > 0  => accumulation
_DIST_RATIO = 0.9  # ad_ratio < this AND obv_slope < 0  => distribution

_NEUTRAL_RESULT: dict = {
    "ad_ratio": None,
    "pct_accumulation": None,
    "signature": "neutral",
    "n": 0,
    "members": [],
}


def _obv_slope(close: pd.Series, volume: pd.Series, slope_d: int) -> float | None:
    """Linear slope of the OBV over the last `slope_d` days (normalised by mean OBV
    so it is scale-free). Returns None if there is insufficient history."""
    obv = (np.sign(close.diff()) * volume).fillna(0.0).cumsum()
    seg = obv.iloc[-slope_d:]
    if len(seg) < slope_d // 2:
        return None
    x = np.arange(len(seg), dtype=float)
    y = seg.values.astype(float)
    if not np.isfinite(y).all():
        y = y[np.isfinite(y)]
        x = x[: len(y)]
    if len(x) < 3:
        return None
    slope = float(np.polyfit(x, y, 1)[0])
    denom = float(np.abs(obv).mean()) if float(np.abs(obv).mean()) > 0 else 1.0
    return slope / denom


def _member_signature(ticker: str, lookback_d: int, obv_slope_d: int) -> dict | None:
    """Compute the up/down-volume split and OBV slope for one ticker.

    Mirrors engine.holdings_signals.volume_surge: reads store.read("stocks", ticker)
    and accesses the 'volume' and 'close' columns. Returns None if the ticker lacks
    volume history or has insufficient rows — callers skip None silently."""
    px = store.read("stocks", str(ticker).replace(".", "-"))
    if px is None or "volume" not in px.columns or "close" not in px.columns:
        return None
    close = pd.to_numeric(px["close"], errors="coerce").dropna()
    volume = pd.to_numeric(px["volume"], errors="coerce").reindex(close.index)
    volume = volume.fillna(0.0)
    # need at least lookback_d rows plus a few extra for the diff
    if len(close) < max(lookback_d, obv_slope_d) + 5:
        return None
    window_close = close.iloc[-lookback_d:]
    window_vol = volume.reindex(window_close.index).fillna(0.0)
    daily_ret = window_close.pct_change(fill_method=None)
    up_mask = daily_ret > 0
    down_mask = daily_ret < 0
    up_vol = float(window_vol[up_mask].sum())
    down_vol = float(window_vol[down_mask].sum())
    if down_vol <= 0:
        ad_ratio = None   # degenerate; skip
    else:
        ad_ratio = round(up_vol / down_vol, 3)
    slope = _obv_slope(close, volume.reindex(close.index).fillna(0.0), obv_slope_d)
    if ad_ratio is None:
        sig = "neutral"
    elif ad_ratio > _ACC_RATIO and (slope is not None and slope > 0):
        sig = "accumulation"
    elif ad_ratio < _DIST_RATIO and (slope is not None and slope < 0):
        sig = "distribution"
    else:
        sig = "neutral"
    return {
        "ticker": ticker,
        "ad_ratio": ad_ratio,
        "obv_slope": round(slope, 4) if slope is not None else None,
        "up_vol": round(up_vol),
        "down_vol": round(down_vol),
        "signature": sig,
    }


def _basket_agg(member_rows: list[dict]) -> dict:
    """Aggregate per-member results to the basket level."""
    if not member_rows:
        return dict(_NEUTRAL_RESULT)
    ratios = [r["ad_ratio"] for r in member_rows if r["ad_ratio"] is not None]
    n = len(member_rows)
    median_ratio = float(np.median(ratios)) if ratios else None
    pct_acc = round(
        sum(1 for r in member_rows if r["signature"] == "accumulation") / n, 3
    )
    pct_dist = round(
        sum(1 for r in member_rows if r["signature"] == "distribution") / n, 3
    )
    if median_ratio is not None and median_ratio > _ACC_RATIO and pct_acc >= 0.4:
        basket_sig = "accumulation"
    elif median_ratio is not None and median_ratio < _DIST_RATIO and pct_dist >= 0.4:
        basket_sig = "distribution"
    else:
        basket_sig = "neutral"
    return {
        "ad_ratio": round(median_ratio, 3) if median_ratio is not None else None,
        "pct_accumulation": pct_acc,
        "pct_distribution": pct_dist,
        "signature": basket_sig,
        "n": n,
        "members": member_rows,
    }


def volume_signature(
    region: str = "us",
    lookback_d: int = 42,
    obv_slope_d: int = 20,
) -> dict[str, dict]:
    """Compute per-basket accumulation/distribution volume signatures.

    Parameters
    ----------
    region:
        Currently only 'us' is fully supported (the S&P-1500 close cache with
        basket extras). Non-US regions return an empty dict gracefully.
    lookback_d:
        Rolling window (trading days) for the up/down-volume split.
    obv_slope_d:
        Trailing window for the linear OBV slope (should be <= lookback_d).

    Returns
    -------
    dict[theme_id -> {ad_ratio, pct_accumulation, pct_distribution, signature, n, members}]
    On any data shortfall the basket returns the _NEUTRAL_RESULT shape, never raises.
    """
    if region.lower() not in ("us", "usa"):
        log.debug("volume_signature: non-US region '%s' — no data plane, returning {}", region)
        return {}

    mem = _membership()
    if not mem or not mem.get("baskets"):
        log.debug("volume_signature: membership unavailable")
        return {}

    # Build the close matrix so we know which tickers are present in the cache.
    closes = _closes()
    if closes is None or closes.empty:
        log.debug("volume_signature: close cache unavailable")
        return {}
    extras = _basket_extras()
    if extras is not None and not extras.empty:
        add = [c for c in extras.columns if c not in closes.columns]
        if add:
            closes = closes.join(extras[add], how="left")

    bdict = mem["baskets"]
    items = bdict.items() if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]

    out: dict[str, dict] = {}
    for bid, b in items:
        members = b.get("members", [])
        # Only consider currently active members (no 'removed' field or removed is None)
        active = [m for m in members if not m.get("removed")]
        present = [m["ticker"] for m in active if m["ticker"] in closes.columns]
        if not present:
            out[bid] = dict(_NEUTRAL_RESULT)
            continue
        rows: list[dict] = []
        for tk in present:
            try:
                r = _member_signature(tk, lookback_d, obv_slope_d)
            except Exception as exc:  # noqa: BLE001 — one member must not kill the basket
                log.debug("volume_signature member %s failed: %s", tk, exc)
                r = None
            if r is not None:
                rows.append(r)
        out[bid] = _basket_agg(rows)
    return out
