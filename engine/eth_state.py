"""Display-only ETH and SOL market-state contracts.

This module deliberately owns no allocation, recommendation, gate, score, or
money-path output.  It converts Coinbase daily OHLCV into plain-word trend,
drawdown, volatility and relative-strength states for the Crypto Cockpit.
Yahoo close-only history is an explicitly labelled availability fallback until
the Coinbase series has accrued.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import numpy as np
import pandas as pd

from lib import store

SCHEMA = "crypto.asset_states/v1"
MIN_PUBLISH_DAYS = 30


def _close(frame: pd.DataFrame | pd.Series | None) -> pd.Series:
    if frame is None:
        return pd.Series(dtype=float)
    if isinstance(frame, pd.Series):
        series = frame
    else:
        if frame.empty or "close" not in frame.columns:
            return pd.Series(dtype=float)
        series = frame["close"]
    out = pd.to_numeric(series, errors="coerce").dropna()
    out.index = pd.to_datetime(out.index).tz_localize(None).normalize()
    return out[~out.index.duplicated(keep="last")].sort_index()


def _pct_change(series: pd.Series, sessions: int) -> float | None:
    if len(series) <= sessions:
        return None
    start = float(series.iloc[-sessions - 1])
    end = float(series.iloc[-1])
    return round(100.0 * (end / start - 1.0), 2) if start > 0 else None


def _relative_state(asset: pd.Series, btc: pd.Series) -> tuple[str, str, float | None]:
    joined = pd.concat(
        [asset.rename("asset"), btc.rename("btc")], axis=1, sort=False
    ).dropna()
    if len(joined) < 91:
        return "Building history", "积累历史中", None
    ratio = joined["asset"] / joined["btc"]
    change = _pct_change(ratio, 90)
    if change is None:
        return "Building history", "积累历史中", None
    if change >= 5:
        return "Leading Bitcoin", "领先比特币", change
    if change <= -5:
        return "Lagging Bitcoin", "落后比特币", change
    return "Tracking Bitcoin", "跟随比特币", change


def build_asset_state(
    symbol: str,
    asset_frame: pd.DataFrame | pd.Series | None,
    btc_frame: pd.DataFrame | pd.Series | None,
    *,
    source: str,
) -> dict:
    """Return a states-only contract for one asset."""
    symbol = symbol.upper()
    asset = _close(asset_frame)
    btc = _close(btc_frame)
    days = int(len(asset))
    first = str(asset.index.min().date()) if days else None
    last = str(asset.index.max().date()) if days else None
    source_en = (
        "Coinbase daily OHLCV"
        if source == "coinbase"
        else "Yahoo close-only availability fallback"
    )
    source_zh = (
        "Coinbase 日频 OHLCV"
        if source == "coinbase"
        else "Yahoo 仅收盘价可用性备用源"
    )
    coverage = {
        "available": days >= MIN_PUBLISH_DAYS,
        "observations": days,
        "first_date": first,
        "last_date": last,
        "source": source,
        "note_en": (
            f"{days:,} daily observations from {source_en}."
            if days >= MIN_PUBLISH_DAYS
            else f"Building daily history; {days:,} observations available."
        ),
        "note_zh": (
            f"{source_zh}已积累 {days:,} 个日频观测。"
            if days >= MIN_PUBLISH_DAYS
            else f"正在积累日频历史；目前有 {days:,} 个观测。"
        ),
    }
    base = {
        "symbol": symbol,
        "display_only": True,
        "authority": "states_only",
        "allocation": None,
        "recommendation": None,
        "as_of": last,
        "coverage": coverage,
    }
    if days < MIN_PUBLISH_DAYS:
        return {
            **base,
            "price": float(asset.iloc[-1]) if days else None,
            "change_30d_pct": None,
            "trend": {"state": "Building history", "state_zh": "积累历史中", "votes": None},
            "risk": {"state": "Unavailable", "state_zh": "暂无", "drawdown_pct": None,
                     "realized_vol_30d_pct": None},
            "relative": {"state": "Building history", "state_zh": "积累历史中",
                         "change_90d_pct": None},
            "summary_en": "Not enough daily history for a market-state read yet.",
            "summary_zh": "日频历史尚不足以形成市场状态解读。",
            "tone": "neutral",
        }

    price = float(asset.iloc[-1])
    votes: list[bool] = [
        price > float(asset.tail(min(50, days)).mean()),
        (_pct_change(asset, 30) or 0.0) > 0,
    ]
    if days >= 200:
        votes.append(price > float(asset.tail(200).mean()))
    if days >= 91:
        votes.append((_pct_change(asset, 90) or 0.0) > 0)
    positive = int(sum(votes))
    if positive >= max(3, len(votes) - 1):
        trend_en, trend_zh, tone = "Advancing", "上行", "bull"
    elif positive <= 1:
        trend_en, trend_zh, tone = "Fading", "走弱", "bear"
    else:
        trend_en, trend_zh, tone = "Range", "震荡", "neutral"

    rolling_high = float(asset.tail(min(365, days)).max())
    drawdown = round(100.0 * (price / rolling_high - 1.0), 2) if rolling_high > 0 else None
    returns = asset.pct_change().dropna().tail(30)
    rv = round(float(returns.std(ddof=0) * np.sqrt(365) * 100.0), 1) if len(returns) >= 20 else None
    if drawdown is None:
        risk_en, risk_zh = "Unavailable", "暂无"
    elif drawdown <= -25:
        risk_en, risk_zh = "Stressed", "承压"
    elif drawdown <= -10 or (rv is not None and rv >= 100):
        risk_en, risk_zh = "Watch", "留意"
    else:
        risk_en, risk_zh = "Calm", "平稳"

    rel_en, rel_zh, rel_change = _relative_state(asset, btc)
    summary_en = f"{trend_en}; {risk_en.lower()} risk; {rel_en.lower()} over 90 days."
    summary_zh = f"{trend_zh}；风险{risk_zh}；90 日内{rel_zh}。"
    return {
        **base,
        "price": round(price, 8),
        "change_30d_pct": _pct_change(asset, 30),
        "trend": {"state": trend_en, "state_zh": trend_zh,
                  "votes": f"{positive}/{len(votes)}"},
        "risk": {"state": risk_en, "state_zh": risk_zh,
                 "drawdown_pct": drawdown, "realized_vol_30d_pct": rv},
        "relative": {"state": rel_en, "state_zh": rel_zh,
                     "change_90d_pct": rel_change},
        "summary_en": summary_en,
        "summary_zh": summary_zh,
        "tone": tone,
    }


def build_states(reader: Callable[[str, str], pd.DataFrame | None] = store.read) -> dict:
    """Build ETH/SOL contracts, preferring real Coinbase OHLCV."""
    btc = reader("coinbase", "btc_daily")
    if btc is None or btc.empty:
        btc = reader("yahoo", "BTC-USD")
    assets: dict[str, dict] = {}
    for symbol in ("ETH", "SOL"):
        frame = reader("coinbase", f"{symbol.lower()}_daily")
        source = "coinbase"
        if frame is None or frame.empty:
            frame = reader("yahoo", f"{symbol}-USD")
            source = "yahoo_fallback"
        assets[symbol] = build_asset_state(symbol, frame, btc, source=source)
    as_ofs = [v.get("as_of") for v in assets.values() if v.get("as_of")]
    return {
        "schema": SCHEMA,
        "tier": "display",
        "display_only": True,
        "authority": "states_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": max(as_ofs) if as_ofs else None,
        "assets": assets,
    }
