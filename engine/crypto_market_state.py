"""Crypto-class display state assembled from existing, governed stores.

The outputs are descriptive market context.  They do not alter Bitcoin Vector
scores, final exposure, strategy rules, or any measured authority.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from lib import store

Reader = Callable[[str, str], pd.DataFrame | None]


def _series(reader: Reader, group: str, name: str, columns: tuple[str, ...]) -> pd.Series:
    frame = reader(group, name)
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    for column in columns:
        if column in frame.columns:
            out = pd.to_numeric(frame[column], errors="coerce").dropna()
            out.index = pd.to_datetime(out.index).tz_localize(None).normalize()
            return out[~out.index.duplicated(keep="last")].sort_index()
    return pd.Series(dtype=float)


def _value(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _delta(series: pd.Series, periods: int = 30, pct: bool = False) -> float | None:
    clean = series.dropna()
    if len(clean) <= periods:
        return None
    now, then = float(clean.iloc[-1]), float(clean.iloc[-periods - 1])
    if pct:
        return None if then == 0 else 100 * (now / then - 1)
    return now - then


def total_market_cap_history(reader: Reader = store.read) -> pd.Series:
    """Derive class market cap from BTC cap / BTC share, then splice snapshots."""
    btc_cap = _series(reader, "coinmetrics", "mcap_usd", ("mcap_usd",))
    dominance = _series(
        reader, "bgeo", "btc_dominance", ("btc_dominance", "btc_dominance_pct")
    )
    if not btc_cap.empty and not dominance.empty:
        aligned = pd.concat(
            [btc_cap.rename("btc"), dominance.rename("dom")], axis=1, sort=False
        )
        aligned = aligned.sort_index().ffill(limit=3).dropna()
        derived = aligned["btc"] / (aligned["dom"] / 100).replace(0, np.nan)
        derived = derived.replace([np.inf, -np.inf], np.nan).dropna()
    else:
        derived = pd.Series(dtype=float)

    snapshot = _series(reader, "coingecko", "global_market", ("total_mcap_usd",))
    if snapshot.empty:
        return derived
    combined = pd.concat([derived.rename("derived"), snapshot.rename("snapshot")], axis=1)
    return combined["snapshot"].combine_first(combined["derived"]).dropna().sort_index()


def class_regimes(total_cap: pd.Series) -> list[dict]:
    """Collapse a trend/momentum read into calendar-true visual bands."""
    clean = total_cap.dropna().sort_index()
    if len(clean) < 100:
        return []
    state = pd.Series("neutral", index=clean.index)
    ma = clean.rolling(90, min_periods=60).mean()
    mom = clean.pct_change(30)
    state[(clean > ma) & (mom > 0.03)] = "bull"
    state[(clean < ma) & (mom < -0.03)] = "bear"
    out: list[dict] = []
    start = state.index[0]
    previous = state.iloc[0]
    for date, tone in state.iloc[1:].items():
        if tone != previous:
            out.append(
                {"start": str(start.date()), "end": str(date.date()), "tone": previous}
            )
            start, previous = date, tone
    out.append(
        {
            "start": str(start.date()),
            "end": str(state.index[-1].date()),
            "tone": previous,
        }
    )
    return out


def _direction(value: float | None, up: float, down: float) -> tuple[str, str]:
    if value is None:
        return "Unavailable", "neutral"
    if value >= up:
        return "Rising", "bull"
    if value <= down:
        return "Falling", "bear"
    return "Steady", "neutral"


def _fear_state(value: float | None) -> tuple[str, str]:
    if value is None:
        return "Unavailable", "neutral"
    if value <= 24:
        return "Extreme fear", "bear"
    if value <= 44:
        return "Fearful", "bear"
    if value < 56:
        return "Neutral", "neutral"
    if value < 76:
        return "Greedy", "bull"
    return "Extreme greed", "bull"


def _latest_signals(reader: Reader) -> pd.Series:
    frame = reader("vector", "signals")
    if frame is None or frame.empty:
        return pd.Series(dtype=object)
    return frame.sort_index().iloc[-1]


def build_market_state(reader: Reader = store.read) -> dict:
    total = total_market_cap_history(reader)
    dominance = _series(
        reader, "bgeo", "btc_dominance", ("btc_dominance", "btc_dominance_pct")
    )
    fear = _series(reader, "sentiment_crypto", "fear_greed", ("fear_greed",))
    stable = _series(
        reader, "defillama", "stablecoins", ("stablecoin_mcap_usd",)
    )
    btc = _series(reader, "coinbase", "btc_daily", ("close", "Close"))
    btc_volume = _series(reader, "coinbase", "btc_daily", ("volume", "Volume"))
    eth = _series(reader, "yahoo", "ETH-USD", ("close", "close_price", "Close"))
    etf_frame = reader("farside", "etf_flows")
    signals = _latest_signals(reader)

    total_30d = _delta(total, 30, pct=True)
    dom_30d = _delta(dominance, 30)
    total_state, total_tone = _direction(total_30d, 3, -3)
    dom_state, dom_tone = _direction(dom_30d, 1, -1)
    fear_value = _value(fear.iloc[-1]) if not fear.empty else None
    fear_state, fear_tone = _fear_state(fear_value)

    if total_30d is not None and total_30d > 3:
        if dom_30d is not None and dom_30d < -1:
            stance = "Advancing with wider participation"
            summary = "Capital is expanding beyond Bitcoin while the class trend remains firm."
            stance_zh = "上涨，参与度扩大"
            summary_zh = "资金正从比特币扩散至更广市场，同时资产类别趋势保持稳健。"
            hero_tone = "bull"
        else:
            stance = "Advancing, led by Bitcoin"
            summary = "The class is expanding, but Bitcoin is carrying more of the move."
            stance_zh = "上涨，由比特币领涨"
            summary_zh = "加密总市值正在扩大，但更多涨幅仍由比特币承担。"
            hero_tone = "bull"
    elif total_30d is not None and total_30d < -3:
        if dom_30d is not None and dom_30d > 1:
            stance = "Cooling, with participation narrowing"
            summary = "Bitcoin is holding the class together while breadth and capital retreat."
            stance_zh = "降温，参与度收窄"
            summary_zh = "比特币仍在支撑全市场，但广度与资金正在后退。"
        else:
            stance = "Risk receding across the complex"
            summary = "Market value and participation are contracting together."
            stance_zh = "风险在全市场退潮"
            summary_zh = "总市值与参与度正在同步收缩。"
        hero_tone = "bear"
    else:
        stance = "Range-bound, waiting for participation"
        summary = "The class lacks a decisive capital trend; follow flows and leverage for the break."
        stance_zh = "区间震荡，等待参与度"
        summary_zh = "全市场尚无明确资金趋势；需跟踪资金流与杠杆以判断突破方向。"
        hero_tone = "neutral"

    stable_30d_pct = _delta(stable, 30, pct=True)
    stable_30d_usd = _delta(stable, 30)
    stable_state, stable_tone = _direction(stable_30d_pct, 1, -1)

    etf_5d = None
    etf_asof = None
    if etf_frame is not None and not etf_frame.empty:
        totals = pd.to_numeric(etf_frame.get("total"), errors="coerce").dropna()
        if not totals.empty:
            etf_5d = float(totals.tail(5).sum())
            etf_asof = str(pd.Timestamp(totals.index[-1]).date())
    etf_state, etf_tone = _direction(etf_5d, 100, -100)

    volume_pctile = None
    if len(btc_volume) >= 90:
        window = btc_volume.tail(365)
        volume_pctile = round(100 * float((window <= window.iloc[-1]).mean()))
    volume_state = (
        "High participation"
        if volume_pctile is not None and volume_pctile >= 70
        else ("Quiet tape" if volume_pctile is not None and volume_pctile <= 30 else "Normal")
    )
    volume_tone = (
        "bull"
        if volume_pctile is not None and volume_pctile >= 70
        else ("bear" if volume_pctile is not None and volume_pctile <= 30 else "neutral")
    )

    funding_annual = _value(signals.get("funding_annual_pct"))
    funding_state = (
        "Longs crowded"
        if funding_annual is not None and funding_annual >= 15
        else (
            "Shorts paying"
            if funding_annual is not None and funding_annual <= -5
            else ("Balanced" if funding_annual is not None else "Unavailable")
        )
    )
    funding_tone = (
        "bear"
        if funding_annual is not None and funding_annual >= 15
        else ("bull" if funding_annual is not None and funding_annual <= -5 else "neutral")
    )
    oi_ratio = _value(signals.get("oi_mcap_ratio"))
    oi_pctile = _value(signals.get("oi_mcap_pctile"))
    oi_state = (
        "Leverage elevated"
        if oi_pctile is not None and oi_pctile >= 75
        else (
            "Leverage light"
            if oi_pctile is not None and oi_pctile <= 25
            else ("Leverage normal" if oi_pctile is not None else "Unavailable")
        )
    )
    oi_tone = (
        "bear"
        if oi_pctile is not None and oi_pctile >= 75
        else ("bull" if oi_pctile is not None and oi_pctile <= 25 else "neutral")
    )
    vol_value = _value(signals.get("dvol"))
    vol_pctile = _value(signals.get("dvol_pctile"))
    vol_state = (
        "Volatility hot"
        if vol_pctile is not None and vol_pctile >= 75
        else (
            "Volatility compressed"
            if vol_pctile is not None and vol_pctile <= 25
            else ("Volatility normal" if vol_pctile is not None else "Unavailable")
        )
    )
    vol_tone = "bear" if vol_pctile is not None and vol_pctile >= 75 else "neutral"

    alt_score = None
    if not btc.empty and not eth.empty and len(btc) > 90 and len(eth) > 90:
        aligned = pd.concat(
            [eth.rename("eth"), btc.rename("btc")], axis=1, sort=False
        ).dropna()
        if len(aligned) > 90:
            rel = aligned["eth"] / aligned["btc"]
            rel_90d = 100 * (rel.iloc[-1] / rel.iloc[-91] - 1)
            alt_score = round(float(np.clip(50 + rel_90d * 1.5 - (dom_30d or 0) * 4, 0, 100)))
    alt_state = (
        "Alt participation broad"
        if alt_score is not None and alt_score >= 65
        else (
            "Bitcoin-led"
            if alt_score is not None and alt_score <= 35
            else ("Mixed participation" if alt_score is not None else "Building history")
        )
    )
    alt_tone = (
        "bull"
        if alt_score is not None and alt_score >= 65
        else ("bear" if alt_score is not None and alt_score <= 35 else "neutral")
    )

    asof_candidates = [
        s.index[-1]
        for s in (total, dominance, fear, stable, btc)
        if not s.empty
    ]
    as_of = str(pd.Timestamp(max(asof_candidates)).date()) if asof_candidates else "—"
    history = total.tail(1460)
    return {
        "as_of": as_of,
        "stance": stance,
        "stance_zh": stance_zh,
        "summary": summary,
        "summary_zh": summary_zh,
        "tone": hero_tone,
        "total_market_cap": _value(total.iloc[-1]) if not total.empty else None,
        "total_30d_pct": total_30d,
        "total_state": total_state,
        "total_tone": total_tone,
        "btc_dominance": _value(dominance.iloc[-1]) if not dominance.empty else None,
        "dominance_30d": dom_30d,
        "dominance_state": dom_state,
        "dominance_tone": dom_tone,
        "fear_greed": fear_value,
        "fear_state": fear_state,
        "fear_tone": fear_tone,
        "history": {
            "dates": [str(pd.Timestamp(x).date()) for x in history.index],
            "vals": [float(x) for x in history.to_numpy()],
        },
        "regimes": class_regimes(history),
        "flows": {
            "etf": {
                "value": etf_5d,
                "state": etf_state,
                "tone": etf_tone,
                "as_of": etf_asof,
            },
            "stablecoins": {
                "value": _value(stable.iloc[-1]) if not stable.empty else None,
                "change_30d_pct": stable_30d_pct,
                "change_30d_usd": stable_30d_usd,
                "state": stable_state,
                "tone": stable_tone,
            },
            "volume": {
                "value": _value(btc_volume.iloc[-1]) if not btc_volume.empty else None,
                "percentile": volume_pctile,
                "state": volume_state,
                "tone": volume_tone,
                "proxy": "BTC spot-volume proxy",
            },
        },
        "heat": {
            "funding": {
                "value": funding_annual,
                "state": funding_state,
                "tone": funding_tone,
            },
            "open_interest": {
                "value": oi_ratio,
                "percentile": oi_pctile,
                "state": oi_state,
                "tone": oi_tone,
            },
            "volatility": {
                "value": vol_value,
                "percentile": vol_pctile,
                "state": vol_state,
                "tone": vol_tone,
            },
            "altseason": {
                "value": alt_score,
                "state": alt_state,
                "tone": alt_tone,
            },
        },
    }
