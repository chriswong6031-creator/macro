"""The eight-state bars-only tagger v0 (registration §6 / masterplan §7.1).

Eight mutually-exclusive path states from daily bars only:

    post_event_dislocation, deep_washout, breakdown, recovery_reclaim,
    controlled_pullback, structural_uptrend, vol_transition, range

Three bars-only variables plus a bars-only event proxy drive all eight:

``d200``     ``close / SMA200 - 1``
``dd``       ``close / max(close, 252 sessions) - 1``
``volp``     percentile of 21-session realized vol within the name's own trailing 756
``gap_atr``  the event proxy — plane-aware, see below

**Never an earnings calendar.** No deep historical earnings-date archive exists, so
a calendar-keyed state would be unbuildable over the history this program measures
(masterplan §7.1, review finding 9). The gap proxy is the substitute and its
divergence from true earnings dates is a disclosed limitation, not a hidden one.

**The gap basis is plane-asymmetric and every row says so.** Planes carrying
``open`` use ``|open_t - close_{t-1}| / ATR14``; the open-less ``data/stocks``
plane uses ``|close_t - close_{t-1}| / ATR14``. These are not the same statistic —
a close-to-close proxy absorbs the whole session's move, not just the overnight
jump — so ``gap_basis`` is recorded on every row and a cross-plane comparison of
``post_event_dislocation`` shares has to carry that caveat.

State is a **covariate** on episodes, not a fit-cell key (§7.1). Nothing here
ranks, gates, or originates anything.

Precedence is first-match-wins, which is what makes the eight mutually exclusive;
``range`` is the residual, which is what makes them total. Both properties are
test-enforced against a synthetic grid rather than asserted.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from engine.stock_identity.plane import PLANES_WITH_OPEN
from engine.stock_technicals import atr as _atr, realized_vol as _realized_vol

log = logging.getLogger(__name__)

STATES: tuple[str, ...] = (
    "post_event_dislocation",
    "deep_washout",
    "breakdown",
    "recovery_reclaim",
    "controlled_pullback",
    "structural_uptrend",
    "vol_transition",
    "range",
)

GAP_BASIS_OPEN = "open_vs_prev_close"
GAP_BASIS_CLOSE = "close_vs_prev_close"

#: SMA200 slope is measured over this many sessions. Declared here (a geometry
#: choice, not a partition-computed constant): a one-session diff on a 200-bar mean
#: is numerically dominated by the single bar entering and leaving the window, so a
#: one-month lookback is what "the 200DMA is falling" actually means.
SLOPE_LOOKBACK = 21

_VOL_WIN = 21
_VOL_PCTILE_WIN = 756
_DD_WIN = 252


@dataclass(frozen=True)
class StateConstants:
    """Thresholds frozen in ``si_constants_v1.json``. Never edited after sealing."""

    g: float           # gap_atr level defining an event dislocation
    theta_dw: float    # deep-washout drawdown depth (positive fraction)
    theta_bd: float    # breakdown distance below the 200DMA (positive fraction)
    theta_pb: float    # controlled-pullback drawdown floor (positive fraction)
    theta_up: float    # structural-uptrend d200 floor (declared 0)
    J: float           # vol-percentile band jump, in percentile points
    V: int             # sessions over which the band jump is measured
    E: int             # sessions a gap keeps the dislocation state alive
    R: int             # sessions a washout/breakdown remains "recent" for reclaim

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


def state_variables(df: pd.DataFrame, plane_id: str) -> pd.DataFrame:
    """The bars-only variable frame for one instrument.

    Every column at row t is a function of rows <= t. ``gap_basis`` is a constant
    column (the plane decides it) and is carried so no downstream consumer has to
    re-derive which proxy produced ``gap_atr``.
    """
    close = df["close"].astype(float)
    has_hl = {"high", "low"}.issubset(df.columns)
    atr14 = (
        _atr(df["high"], df["low"], close, n=14)
        if has_hl
        else pd.Series(np.nan, index=df.index)
    )
    sma200 = close.rolling(200, min_periods=200).mean()

    prev_close = close.shift(1)
    if plane_id in PLANES_WITH_OPEN and "open" in df.columns:
        raw_gap = (df["open"].astype(float) - prev_close).abs()
        basis = GAP_BASIS_OPEN
    else:
        raw_gap = (close - prev_close).abs()
        basis = GAP_BASIS_CLOSE

    rv21 = _realized_vol(close, n=_VOL_WIN)
    volp = rv21.rolling(_VOL_PCTILE_WIN, min_periods=_VOL_PCTILE_WIN).rank(pct=True) * 100.0

    out = pd.DataFrame(index=df.index)
    out["close"] = close
    out["sma200"] = sma200
    out["d200"] = close / sma200.replace(0.0, np.nan) - 1.0
    out["dd"] = close / close.rolling(_DD_WIN, min_periods=_DD_WIN).max() - 1.0
    out["volp"] = volp
    # NOTE: the vol band-jump is deliberately NOT computed here — its lookback is the
    # frozen constant V, which lives in StateConstants. `tag_states` derives it.
    out["atr14"] = atr14
    out["gap_atr"] = raw_gap / atr14.replace(0.0, np.nan)
    out["gap_basis"] = basis
    out["sma200_slope"] = sma200 - sma200.shift(SLOPE_LOOKBACK)
    return out


def classify_single(
    *,
    gap_recent: bool,
    dd: float | None,
    d200: float | None,
    sma200_slope: float | None,
    washout_or_breakdown_recent: bool,
    volp_jump: float | None,
    const: StateConstants,
) -> str:
    """The precedence kernel — exactly one of ``STATES`` for any input, including
    all-missing warm-up rows.

    This is the single source of truth for the ordering; the vectorized path calls
    it row by row so the tagger and its tests can never drift apart. Missing values
    make their rule fail rather than raise, which is why ``range`` (the residual)
    absorbs the warm-up window instead of a ninth "unknown" state existing.
    """
    def ok(x: float | None) -> bool:
        return x is not None and isinstance(x, (int, float)) and np.isfinite(x)

    # 1
    if gap_recent:
        return "post_event_dislocation"
    # 2
    if ok(dd) and dd <= -const.theta_dw:
        return "deep_washout"
    # 3
    if ok(d200) and ok(sma200_slope) and d200 <= -const.theta_bd and sma200_slope <= 0:
        return "breakdown"
    # 4
    if ok(d200) and d200 >= 0.0 and washout_or_breakdown_recent:
        return "recovery_reclaim"
    # 5
    if ok(d200) and ok(dd) and d200 > 0.0 and (-const.theta_dw < dd <= -const.theta_pb):
        return "controlled_pullback"
    # 6
    if ok(d200) and ok(dd) and d200 >= const.theta_up and dd > -const.theta_pb:
        return "structural_uptrend"
    # 7
    if ok(volp_jump) and volp_jump >= const.J:
        return "vol_transition"
    # 8
    return "range"


def tag_states(df: pd.DataFrame, plane_id: str, const: StateConstants) -> pd.DataFrame:
    """Daily state series for one instrument.

    Rule 4 (``recovery_reclaim``) is defined against the *assigned* state history —
    "d200 back to 0 after a deep_washout/breakdown state within the trailing R
    sessions" — so the pass is sequential by necessity, not by accident.
    """
    v = state_variables(df, plane_id)
    n = len(v)
    d200 = v["d200"].to_numpy(dtype=float)
    dd = v["dd"].to_numpy(dtype=float)
    slope = v["sma200_slope"].to_numpy(dtype=float)
    volp = v["volp"].to_numpy(dtype=float)
    gap = v["gap_atr"].to_numpy(dtype=float)

    # a gap_atr > g day within the trailing E sessions (inclusive of today)
    gap_hit = np.where(np.isfinite(gap), gap > const.g, False)
    gap_recent = (
        pd.Series(gap_hit).rolling(const.E, min_periods=1).max().to_numpy().astype(bool)
    )

    # band jump over the trailing V sessions
    volp_s = pd.Series(volp)
    jump = (volp_s - volp_s.shift(const.V)).abs().to_numpy(dtype=float)

    states: list[str] = []
    last_wb = -10**9  # last index carrying deep_washout or breakdown
    for i in range(n):
        recent_wb = (i - last_wb) <= const.R
        s = classify_single(
            gap_recent=bool(gap_recent[i]),
            dd=float(dd[i]),
            d200=float(d200[i]),
            sma200_slope=float(slope[i]),
            washout_or_breakdown_recent=recent_wb,
            volp_jump=float(jump[i]),
            const=const,
        )
        if s in ("deep_washout", "breakdown"):
            last_wb = i
        states.append(s)

    out = pd.DataFrame(index=df.index)
    out["state"] = states
    out["gap_basis"] = v["gap_basis"]
    out["d200"] = v["d200"]
    out["dd"] = v["dd"]
    out["volp"] = v["volp"]
    out["gap_atr"] = v["gap_atr"]
    out["sma200"] = v["sma200"]
    return out


def state_share_by_year(states: pd.Series) -> pd.DataFrame:
    """Per-calendar-year share of each state — the dossier's state table."""
    s = states.dropna()
    if s.empty:
        return pd.DataFrame(columns=list(STATES))
    tab = pd.crosstab(s.index.year, s, normalize="index")
    for st in STATES:
        if st not in tab.columns:
            tab[st] = 0.0
    tab = tab[list(STATES)]
    tab.index.name = "year"
    return tab
