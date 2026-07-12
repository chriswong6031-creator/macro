"""engine/rebalance_pulse.py — Rebalance Pulse detector (RLT-R2).

Pure function: compute_pulse(asof, volume_cache_df, updown_df, calendar_tags, closes)
returns a classified day-descriptor for a single session.

Frozen class vocabulary (RLT-R2):
  mechanical_spike_absorbed     calendar window AND vol_ratio>=1.5 AND up_share>=0.55
  mechanical_spike_distributed  calendar window AND vol_ratio>=1.5 AND up_share<=0.45
  mechanical_spike_mixed        calendar window AND vol_ratio>=1.5 AND 0.45<up_share<0.55
  unscheduled_volume_event      vol_ratio>=1.75 AND no calendar tag
  quiet                         everything else

Authority: display/context tier.
  may_rank=false, may_gate=false, may_size=false.

NOT a bottom-caller: a rebalance-day spike marking THE low is coincident-by-construction
(RRX-R4/R10 class); this pulse ships as context only.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Frozen class vocabulary ──────────────────────────────────────────────────
PULSE_CLASSES = (
    "mechanical_spike_absorbed",
    "mechanical_spike_distributed",
    "mechanical_spike_mixed",
    "unscheduled_volume_event",
    "quiet",
)

# ── Thresholds (per RLT-R2) ──────────────────────────────────────────────────
VOL_RATIO_SPIKE = 1.5          # calendar-window spike threshold
VOL_RATIO_UNSCHEDULED = 1.75   # unscheduled spike threshold (higher bar)
UP_SHARE_ABSORBED = 0.55       # up_share >= this → absorbed
UP_SHARE_DISTRIBUTED = 0.45    # up_share <= this → distributed

# ── Mega-cap list ────────────────────────────────────────────────────────────
# Static top-30 by approximate market cap (as of mid-2026).
# This is a context-only organ; the exact list does not affect any score or rank.
# Choice: static constant is simpler and more stable than reading a live reference
# (which can be absent at build time).  Includes Mag-7 plus the next tier.
MEGACAP_TICKERS: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA",
    "AVGO", "BRK-B", "LLY", "WMT", "JPM", "V", "MA", "XOM", "UNH",
    "NFLX", "ORCL", "COST", "HD", "PG", "ABBV", "BAC", "JNJ",
    "CRM", "CVX", "MRK", "TMUS", "AMD",
]

# RVOL threshold to count a name as "spiking"
RVOL_SPIKE_THRESHOLD = 2.0

# Rolling window (business days) for volume baseline
VOL_BASELINE_WINDOW = 20

# ── Summary text templates ────────────────────────────────────────────────────

_SUMMARY_EN = {
    "mechanical_spike_absorbed": (
        "Rebalancing-window volume spike absorbed by buyers — "
        "large mechanical flows, price held up."
    ),
    "mechanical_spike_distributed": (
        "Rebalancing-window volume spike met by sellers — "
        "large mechanical flows, price pressure notable."
    ),
    "mechanical_spike_mixed": (
        "Rebalancing-window volume spike with mixed breadth — "
        "large mechanical flows, direction inconclusive."
    ),
    "unscheduled_volume_event": (
        "Elevated volume with no calendar rebalancing scheduled — "
        "watch for news-driven or institutional catalyst."
    ),
    "quiet": "No elevated volume or scheduled rebalancing activity.",
}

_SUMMARY_ZH = {
    "mechanical_spike_absorbed": "再平衡窗口量能放大、买方消化——大规模机械性资金流，价格企稳。",
    "mechanical_spike_distributed": "再平衡窗口量能放大、卖方承压——大规模机械性资金流，价格走弱。",
    "mechanical_spike_mixed": "再平衡窗口量能放大、方向混合——大规模机械性资金流，方向不明。",
    "unscheduled_volume_event": "量能异常放大，无对应再平衡日历——关注新闻或机构性催化剂。",
    "quiet": "无异常量能或计划中的再平衡活动。",
}


# ── Main pure function ────────────────────────────────────────────────────────

def compute_pulse(
    asof: date,
    volume_cache_df: pd.DataFrame,
    updown_df: pd.DataFrame | None,
    calendar_tags: dict[str, Any],
    closes: pd.Series | None = None,
) -> dict[str, Any]:
    """Compute one session's Rebalance Pulse descriptor.

    Parameters
    ----------
    asof :
        Session date to classify.
    volume_cache_df :
        DataFrame indexed by date with one column per ticker (daily volume).
        Expected path: data/breadth/_volume_cache.parquet
    updown_df :
        DataFrame indexed by date with at least 'up_vol' and 'down_vol' columns.
        Expected path: data/breadth/updown.parquet — may be None or absent for date.
    calendar_tags :
        Dict from engine.rebalance_calendar.tag(asof).
    closes :
        Optional Series indexed by ticker with the session's close prices
        (for close-direction fallback when updown absent).

    Returns
    -------
    dict with keys: date, class, market_vol_ratio, up_share, basis,
                    n_megacap_rvol2, megacap_rvol, calendar, summary_en, summary_zh,
                    authority.
    """
    asof_ts = pd.Timestamp(asof)

    # ── Market volume ratio (total vol vs 20d median) ────────────────────────
    market_vol_ratio: float | None = None
    try:
        if not volume_cache_df.empty:
            # Sum across all tickers for each date → market total volume
            vol_total = volume_cache_df.sum(axis=1).sort_index()
            if asof_ts in vol_total.index:
                today_vol = float(vol_total.loc[asof_ts])
                # Exclude today from the baseline window
                prior = vol_total[vol_total.index < asof_ts].iloc[-VOL_BASELINE_WINDOW:]
                if len(prior) >= 5:
                    baseline = float(prior.median())
                    if baseline > 0:
                        market_vol_ratio = today_vol / baseline
    except Exception as exc:  # noqa: BLE001
        log.warning("rebalance_pulse: vol ratio calc failed — %s", exc)

    # ── Per-name RVOL for mega-caps ──────────────────────────────────────────
    megacap_rvol: dict[str, float] = {}
    n_megacap_rvol2: int = 0
    try:
        if not volume_cache_df.empty and asof_ts in volume_cache_df.index:
            for ticker in MEGACAP_TICKERS:
                if ticker not in volume_cache_df.columns:
                    continue
                col = volume_cache_df[ticker].sort_index()
                if asof_ts not in col.index:
                    continue
                today_v = float(col.loc[asof_ts])
                prior = col[col.index < asof_ts].iloc[-VOL_BASELINE_WINDOW:]
                if len(prior) < 5 or prior.median() <= 0:
                    continue
                rvol = today_v / float(prior.median())
                megacap_rvol[ticker] = round(rvol, 2)
                if rvol >= RVOL_SPIKE_THRESHOLD:
                    n_megacap_rvol2 += 1
    except Exception as exc:  # noqa: BLE001
        log.warning("rebalance_pulse: megacap RVOL calc failed — %s", exc)

    # ── Up-share ────────────────────────────────────────────────────────────
    up_share: float | None = None
    basis: str = "updown"  # or "volume_only"
    try:
        if updown_df is not None and not updown_df.empty:
            updown_ts = updown_df.copy()
            updown_ts.index = pd.DatetimeIndex(updown_ts.index)
            if asof_ts in updown_ts.index:
                row = updown_ts.loc[asof_ts]
                uv = float(row.get("up_vol", 0) or 0)
                dv = float(row.get("down_vol", 0) or 0)
                total = uv + dv
                if total > 0:
                    up_share = uv / total
    except Exception as exc:  # noqa: BLE001
        log.warning("rebalance_pulse: updown read failed — %s", exc)

    # Fallback: close direction when updown absent
    if up_share is None:
        basis = "volume_only"
        if closes is not None and not closes.empty:
            # If we have a close-level proxy (e.g., SPY), use its direction
            try:
                # closes: Series indexed by ticker; check for SPY/QQQ
                for proxy in ("SPY", "QQQ", "IWM"):
                    if proxy in closes.index and closes[proxy] is not None:
                        # We can't derive up_share without prior close,
                        # so leave None but flag basis
                        break
            except Exception:  # noqa: BLE001
                pass

    # ── In-calendar-window check ──────────────────────────────────────────────
    in_calendar_window = bool(
        calendar_tags.get("in_qtr_end_window")
        or calendar_tags.get("is_russell_recon_session")
        or calendar_tags.get("in_recon_week")
        or calendar_tags.get("is_sp_rebalance_session")
    )

    # ── Classification ────────────────────────────────────────────────────────
    pulse_class = _classify(
        in_calendar_window=in_calendar_window,
        market_vol_ratio=market_vol_ratio,
        up_share=up_share,
    )

    # Top-8 megacap RVOL (by ratio, descending)
    top8_rvol = dict(
        sorted(megacap_rvol.items(), key=lambda kv: kv[1], reverse=True)[:8]
    )

    return {
        "date": asof.isoformat(),
        "class": pulse_class,
        "market_vol_ratio": round(market_vol_ratio, 3) if market_vol_ratio is not None else None,
        "up_share": round(up_share, 3) if up_share is not None else None,
        "basis": basis,
        "n_megacap_rvol2": n_megacap_rvol2,
        "megacap_rvol": top8_rvol,
        "calendar": calendar_tags,
        "summary_en": _SUMMARY_EN[pulse_class],
        "summary_zh": _SUMMARY_ZH[pulse_class],
        "authority": {
            "may_rank": False,
            "may_gate": False,
            "may_size": False,
        },
    }


def _classify(
    in_calendar_window: bool,
    market_vol_ratio: float | None,
    up_share: float | None,
) -> str:
    """Pure classification logic — all thresholds per RLT-R2."""
    vr = market_vol_ratio or 0.0

    if in_calendar_window and vr >= VOL_RATIO_SPIKE:
        if up_share is None:
            return "mechanical_spike_mixed"
        if up_share >= UP_SHARE_ABSORBED:
            return "mechanical_spike_absorbed"
        if up_share <= UP_SHARE_DISTRIBUTED:
            return "mechanical_spike_distributed"
        return "mechanical_spike_mixed"

    if not in_calendar_window and vr >= VOL_RATIO_UNSCHEDULED:
        return "unscheduled_volume_event"

    return "quiet"
