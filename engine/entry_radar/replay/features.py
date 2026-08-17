"""PIT matching features, cohort assignment, C32, regime tag — frozen laws.

Everything here is computable from confirmed daily bars ≤ the decision session
(PIT by construction).  The COHORT LAW below is frozen in this implementation PR
before any outcome read (prereg §7): assignment is mechanical, first-match-wins
in the exact order stated, from the features named — never tuned after results.

Cohort law (first match wins; all inputs as of the decision session D, prior
confirmed close for indicator values):

1. ``ipo_young``            — history < 252 sessions at D.
2. ``gap_catalyst``         — any |open/prev_close − 1| ≥ 5% in the trailing
                              5 sessions ending at D.
3. ``deep_mtf_washout``     — 63-session close drawdown ≤ −35%, OR both 2D and
                              3D StochRSI %D < 20 at the last confirmed bucket
                              (absolute session anchor, Radar era).
4. ``full_daily_washout``   — min confirmed daily K over the trailing 5
                              sessions < 5.
5. ``partial_shallow_washout`` — min confirmed daily K over the trailing 8
                              sessions in (5, 20].
6. ``smallcap_highvol_momentum`` — cap bucket "<2B" AND realized-20d-vol
                              quintile 5 AND |60d return| quintile 5.
7. ``damaged_trend_rebound``— close < 200DMA AND 252-high drawdown ≤ −25%.
8. ``leader_reset``         — trailing-120-session return ≥ +30%.
9. ``other``                — none of the above (reported, never hidden).

C32 (prereg §7 frozen final form): fresh-low ∧ decelerating —
``close ≤ min(close, 60)`` AND ``roc20 > min(roc20, 20)`` on confirmed closes
through the prior session, ``roc20 = close/close.shift(20) − 1``.

Regime tag: SPY 63-session drawdown ≤ −10% at D ⇒ ``stressed`` else ``quiet``.

Matching features per (ticker, session): sector, cap_bucket, proximity_decile
(63-bar close-min), dollar_vol_decile, ret60_quintile, vol20_quintile, hot_tier
(PIT proxy: rel-volume-20d decile ≥ 9 or |5-session return| decile ≥ 9 ⇒ hot).
Deciles/quintiles are cross-sectional within (panel, session).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from engine.entry_radar.replay import prereg

COHORTS = (
    "ipo_young", "gap_catalyst", "deep_mtf_washout", "full_daily_washout",
    "partial_shallow_washout", "smallcap_highvol_momentum",
    "damaged_trend_rebound", "leader_reset", "other",
)

GAP_ABS_PCT = 0.05
GAP_LOOKBACK_SESSIONS = 5
DEEP_DRAWDOWN = -0.35
DEEP_DD_SESSIONS = 63
FULL_WASHOUT_K = 5.0
FULL_WASHOUT_LOOKBACK = 5
PARTIAL_WASHOUT_LOOKBACK = 8
DAMAGED_DD_252 = -0.25
LEADER_RET120 = 0.30
IPO_YOUNG_SESSIONS = 252


@dataclass(frozen=True)
class NameDayFeatures:
    """The §7 matching row + cohort/C32/regime for one (ticker, session)."""

    ticker: str
    session: date
    sector: str | None
    cap_bucket: str            # "<2B" | "2-10B" | "10-200B" | ">200B" | "unknown"
    proximity_decile: int      # 0-9 within (panel, session)
    dollar_vol_decile: int
    ret60_quintile: int
    vol20_quintile: int
    hot_tier: int              # 1 = hot, 0 = cold (PIT proxy)
    cohort: str
    c32: bool | None
    regime: str
    history_sessions: int


def cap_bucket_of(cap_usd: float | None) -> str:
    if cap_usd is None or not np.isfinite(cap_usd) or cap_usd <= 0:
        return "unknown"
    lo, mid, hi = prereg.CAP_BUCKET_EDGES_USD
    if cap_usd < lo:
        return "<2B"
    if cap_usd < mid:
        return "2-10B"
    if cap_usd < hi:
        return "10-200B"
    return ">200B"


def c32_flag(close: pd.Series, asof_pos: int) -> bool | None:
    """Frozen C32 on confirmed closes through position ``asof_pos`` (inclusive,
    the prior confirmed session relative to the decision).  None when history
    is too short to evaluate (< 60+20 sessions)."""
    need = prereg.C32_FRESH_LOW_SESSIONS + prereg.C32_ROC_SESSIONS
    if asof_pos + 1 < need:
        return None
    c = close.iloc[: asof_pos + 1]
    win = c.iloc[-prereg.C32_FRESH_LOW_SESSIONS:]
    fresh_low = bool(c.iloc[-1] <= win.min())
    roc20 = c / c.shift(prereg.C32_ROC_SESSIONS) - 1.0
    r = roc20.iloc[-prereg.C32_ROC_SESSIONS:]
    if not np.isfinite(r.iloc[-1]):
        return None
    floor = r.min()
    if not np.isfinite(floor):
        return None
    # Prereg form is `roc20 > min(roc20, 20)`. Today at the floor is still
    # making lows and must refuse. A 1-ULP lift (2.22e-16) on a constant-rate
    # tail used to pass that `>` and read acceleration as deceleration.
    decel = bool(r.iloc[-1] > float(floor) + 1e-12)
    return fresh_low and decel


def regime_tag(spy_close: pd.Series, session: date) -> str:
    idx = spy_close.index
    pos = int(idx.searchsorted(pd.Timestamp(session), side="right")) - 1
    if pos < 0:
        return "unknown"
    lo = max(0, pos - prereg.REGIME_DRAWDOWN_SESSIONS + 1)
    win = spy_close.iloc[lo: pos + 1]
    if win.empty or not np.isfinite(win.iloc[-1]):
        return "unknown"
    dd = float(win.iloc[-1] / win.max() - 1.0)
    return "stressed" if dd <= prereg.REGIME_DRAWDOWN_STRESSED else "quiet"


__all__ = ["COHORTS", "NameDayFeatures", "cap_bucket_of", "c32_flag",
           "regime_tag", "GAP_ABS_PCT", "GAP_LOOKBACK_SESSIONS", "DEEP_DRAWDOWN",
           "DEEP_DD_SESSIONS", "FULL_WASHOUT_K", "FULL_WASHOUT_LOOKBACK",
           "PARTIAL_WASHOUT_LOOKBACK", "DAMAGED_DD_252", "LEADER_RET120",
           "IPO_YOUNG_SESSIONS"]
