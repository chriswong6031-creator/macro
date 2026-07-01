"""China per-name LIQUIDITY + turnover-shape from the deep OHLCV store (data/china_stocks/
<ticker>.parquet — close,high,low,volume).

Two REAL, data-backed reads the standout board needs and did not have:

  • dollar-ADV  = median(close×volume) over the last `win` sessions, in 亿 CNY. This is the one
    tradability leg backed by real data (the members.parquet market-cap field is 46% a 30亿
    placeholder), so it does the actual garbage-weeding — a name whose median turnover is a few
    million CNY/day is untradeable size for anything but a token position. We only EXCLUDE names
    we can PROVE are illiquid (a missing/thin series returns None → the caller passes it through).

  • turnover RATIO = recent(5d) median volume ÷ base(60d) median volume. The early-vs-already-run
    DISCRIMINATOR the plan asked for: turnover EXPANSION off a quiet base (ratio>1 while price is
    near/below its MA) reads as accumulation; a turnover SPIKE at a stretched price reads as
    distribution / a blow-off the board should NOT chase. Directional context, never a standalone
    signal — it feeds the anti-chase extension penalty, it is not itself a buy.

Heuristic thresholds (ADV floor, expansion cut) are tradability/context flags, NOT validated
alpha. KEYLESS · DEGRADE-NEVER-RAISE · point-in-time (reads only past bars). None on shortfall.
See [[china-name-potential-score]] and the standout garbage-filter (build_china_library).
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

DEFAULT_WIN = 20          # sessions for the dollar-ADV median (~one trading month)
ADV_FLOOR_YI = 0.5        # 亿 CNY/day — a name below ~5,000万 median turnover is untradeable size
_RECENT = 5               # short window for the turnover-expansion numerator
_BASE = 60               # base window for the turnover-expansion denominator


def _load(ticker: str, group: str) -> pd.DataFrame | None:
    p = config.data_dir() / group / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p, columns=["close", "volume"])
    except Exception:  # noqa: BLE001 — a name with no volume column / corrupt file just has no read
        try:
            df = pd.read_parquet(p)
        except Exception:  # noqa: BLE001
            return None
    return df if ("close" in df and "volume" in df) else None


def profile(ticker: str, group: str = "china_stocks", win: int = DEFAULT_WIN) -> dict | None:
    """{adv_yi, turn_ratio} for one name from its deep OHLCV parquet, or None if unavailable.

    adv_yi     — `win`-session median dollar volume in 亿 CNY.
    turn_ratio — median 5-day volume ÷ median 60-day volume (>1 = expanding turnover). None if the
                 history is too short to form the base.
    """
    df = _load(ticker, group)
    if df is None:
        return None
    dv = (df["close"] * df["volume"]).dropna()
    if dv.empty:
        return None
    adv_yi = float(dv.tail(win).median()) / 1e8
    vol = df["volume"].dropna()
    turn_ratio = None
    if len(vol) >= _BASE:
        base = float(vol.tail(_BASE).median())
        recent = float(vol.tail(_RECENT).median())
        if base > 0:
            turn_ratio = round(recent / base, 3)
    return {"adv_yi": round(adv_yi, 4), "turn_ratio": turn_ratio}


def liquidity_map(tickers, group: str = "china_stocks", win: int = DEFAULT_WIN) -> dict[str, dict]:
    """{ticker: {adv_yi, turn_ratio}} for every ticker with a deep OHLCV parquet (others omitted).
    One read per name (~3s for the full ~1,500-name store); safe to call once per build."""
    out: dict[str, dict] = {}
    for t in tickers:
        try:
            pr = profile(t, group, win)
        except Exception as e:  # noqa: BLE001 — never let one bad parquet kill the map
            log.debug("china_liquidity profile %s failed: %s", t, e)
            pr = None
        if pr is not None:
            out[t] = pr
    return out


def adv_map(tickers, group: str = "china_stocks", win: int = DEFAULT_WIN) -> dict[str, float]:
    """{ticker: dollar-ADV 亿} — the liquidity floor input (convenience over liquidity_map)."""
    return {t: v["adv_yi"] for t, v in liquidity_map(tickers, group, win).items()
            if v.get("adv_yi") is not None}
