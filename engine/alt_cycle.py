"""Altcoin-cycle / ETH-allocation engine for the Vector's allocation deep-dive page.

Where are we in the alt cycle, and how should BTC vs ETH vs alts vs cash be split?
All free data already on disk: ETH-USD (deep, 2017->), CoinGecko /global snapshot
(btc/eth dominance, total mcap). The deep, calibratable core is the ETH/BTC ratio;
dominance / TOTAL2-3 are current-context only (CoinGecko is a daily snapshot).

Honest framing (surfaced on the page): the 0.05/0.07 ETH/BTC lines and the
allocation % grid are conventions/judgment, not optimized; ~1.5-2 clean ETH/BTC
cycles = low calibration confidence. It is a regime OVERLAY / risk governor, not a
precise alt-entry timer.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ethbtc_signal(eth: pd.Series | None, btc: pd.Series, cfg: dict) -> dict:
    """ETH/BTC ratio cycle — the cleanest deep alt proxy. 0.05 = deep BTC-season,
    0.07 = alt-season confirmed (historical reference levels)."""
    if eth is None:
        return {}
    ratio = (eth.reindex(btc.index).ffill() / btc).dropna()
    if len(ratio) < 120:
        return {}
    level = float(ratio.iloc[-1])
    ma = ratio.rolling(cfg["ethbtc_ma_d"], min_periods=100).mean()
    above_ma = bool(level > ma.iloc[-1]) if pd.notna(ma.iloc[-1]) else None
    n = cfg["slope_window_d"]
    slope = float(ratio.iloc[-1] / ratio.iloc[-n] - 1) if len(ratio) > n else None
    pct = ratio.rolling(cfg["pctile_lookback_d"], min_periods=120).rank(pct=True).iloc[-1]
    season = ("alt" if level >= cfg["alt_season_line"]
              else ("btc" if level < cfg["btc_season_line"] else "mixed"))
    return {"ratio": ratio, "ma": ma, "level": level, "above_ma": above_ma,
            "slope": slope, "pctile": round(100 * float(pct), 0) if pd.notna(pct) else None,
            "season": season}


def alt_season_score(eb: dict, dom_pct: float | None, cfg: dict):
    """Blend ETH/BTC (deep, dominant weight) + dominance (context) into a 0-100
    alt-season score. <25 BTC-season / 25-75 Mixed / >75 Alt-season."""
    if not eb:
        return None, "—"
    s, w = 0.0, 0.0
    if eb.get("pctile") is not None:
        s += eb["pctile"] * 0.6; w += 0.6                       # ratio percentile
    if eb.get("slope") is not None:
        s += (50 + float(np.clip(eb["slope"] * 200, -50, 50))) * 0.25; w += 0.25  # rising ratio
    if dom_pct is not None:
        s += float(np.clip((70 - dom_pct) / 0.30, 0, 100)) * 0.15; w += 0.15      # falling dominance
    if not w:
        return None, "—"
    score = round(s / w, 0)
    bucket = ("BTC season" if score < cfg["btc_season_max"]
              else ("Alt season" if score > cfg["alt_season_min"] else "Mixed"))
    return score, bucket


# BTC / ETH / alts / cash by (cycle regime x alt-season). Judgment grid (labelled
# context on the page). Rules: alts only when alt-season AND not bear; ETH leads
# alts; cash dominates in bear regardless of season (the "nimble only" message).
ALLOC_GRID = {
    "bull":    {"btc": (70, 20, 0, 10), "mixed": (50, 30, 15, 5), "alt": (30, 30, 35, 5)},
    "neutral": {"btc": (55, 15, 0, 30), "mixed": (45, 20, 5, 30), "alt": (35, 25, 20, 20)},
    "bear":    {"btc": (25, 5, 0, 70),  "mixed": (25, 10, 0, 65), "alt": (30, 15, 5, 50)},
}


def alloc_grid(regime: str | None, season_bucket: str | None) -> dict:
    reg = regime if regime in ALLOC_GRID else "neutral"
    sk = ("btc" if "BTC" in (season_bucket or "") else
          ("alt" if "Alt" in (season_bucket or "") else "mixed"))
    btc, eth, alts, cash = ALLOC_GRID[reg][sk]
    return {"btc": btc, "eth": eth, "alts": alts, "cash": cash,
            "regime_key": reg, "season_key": sk}
