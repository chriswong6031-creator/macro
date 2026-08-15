"""Outcome attachment under the frozen §6/§7 prereg laws.

Inputs are plain daily OHLC frames (the run's vendor plane) plus the episode's
already-derived reference units (P0, A0).  Everything here is pure and
per-episode; sign conventions follow the house precedents exactly
(MFE >= 0, MAE <= 0, strictly-forward daily window `sessions D+1..D+H`).

The daily primary NEVER consults minute data — battery G proves the primary is
byte-identical whether or not minute coverage exists.  The secondary minute-path
read is a separate, coverage-flagged table produced elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping

import numpy as np
import pandas as pd

from engine.entry_radar.replay import prereg


@dataclass(frozen=True)
class EpisodeRef:
    """The minimal identity outcomes need — produced by the episodes stage."""

    ticker: str
    detector_id: str
    panel: str                    # "A" | "B"
    decision_session: date        # D (era membership, windows key off this)
    p0: float
    p0_basis: str                 # sampled_last_trade_at_decision | first_trade_after_known_at | next_session_close
    a0: float | None              # ATR14 prior-confirmed; None => no ATR
    atr_basis: str                # true_range_daily_ohlc | close_proxy | absent
    washout_low: float | None     # frozen §7 definition (arm-to-decision min low,
                                  # or trailing-63 min low for G0/C5/incumbent)
    first_armed_session: date | None = None
    cohort: str = "unassigned"
    regime: str = "unknown"
    c32: bool | None = None
    extra: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OutcomeRow:
    """One episode's attached outcomes at one horizon (primary H=10 unless
    stated).  ``evidence_tier`` rides every row (HISTORICAL/TEST/...)."""

    ticker: str
    detector_id: str
    panel: str
    decision_session: date
    horizon: int
    era: str                      # FIT | TEST  (holdout refused upstream)
    p0: float
    p0_basis: str
    a0: float | None
    atr_basis: str
    fwd_ret: float | None         # close[D+H]/P0 - 1 (or censored-last)
    fwd_ret_net: float | None     # after round-trip §11 costs
    mfe: float | None             # >= 0
    mae: float | None             # <= 0
    time_to_positive: int | None  # sessions from D (close > P0); None = never
    time_to_mfe: int | None
    target_before_invalidation: bool | None
    gap_through_invalidation: bool
    false_start: bool | None      # None when excluded (close-proxy ATR / no A0)
    false_start_reason: str | None
    time_to_failure: int | None
    excess_vs_bench: float | None
    excess_vs_sector: float | None
    cost_per_side_bps: float
    cost_basis: str               # measured | floor
    censored: bool
    terminated_reason: str | None
    sessions_covered: int
    cohort: str
    regime: str
    c32: bool | None
    evidence_tier: str


def era_of(decision_session: date) -> str:
    """FIT | TEST for an in-era decision (gates.check_decision_in_era ran first)."""
    return "FIT" if decision_session <= prereg.FIT_END else "TEST"


def _forward_frame(daily: pd.DataFrame, decision_session: date,
                   horizon: int) -> pd.DataFrame:
    """Sessions strictly after D, first ``horizon`` rows (may be short =>
    censoring).  ``daily`` is indexed by session date, columns o/h/l/c."""
    idx = daily.index
    pos = int(idx.searchsorted(pd.Timestamp(decision_session), side="right"))
    return daily.iloc[pos: pos + horizon]


def attach(episode: EpisodeRef, *, daily: pd.DataFrame,
           bench_close: pd.Series, sector_close: pd.Series | None,
           cost_per_side_bps: float, cost_basis: str,
           horizon: int = prereg.HORIZON_PRIMARY,
           adverse_atr: float = prereg.FALSE_START_ADVERSE_ATR,
           favorable_atr: float = prereg.FALSE_START_FAVORABLE_ATR) -> OutcomeRow:
    """Attach the frozen outcome set for one episode at one horizon.

    ``daily`` MUST be the episode's own panel plane (vendor basis) with columns
    ``o,h,l,c`` indexed by session; ``bench_close``/``sector_close`` are close
    series on the same plane.  ``adverse_atr``/``favorable_atr`` exist ONLY for
    the pre-counted 27-cell sensitivity grid; every primary read uses the
    defaults and the runner never varies them elsewhere.
    """
    p0 = float(episode.p0)
    fwd = _forward_frame(daily, episode.decision_session, horizon)
    n = int(len(fwd))
    censored = n < horizon
    terminated = "no_further_trades" if censored else None

    # §7 window law (M4): LIVE episodes carry the session-D remainder after T as
    # sampled last-trade prints ("session 0"); confirmed-bar episodes carry none.
    day0 = [float(x) for x in (episode.extra.get("day0_samples") or ())
            if x is not None and np.isfinite(x)]

    if n == 0 and not day0:
        fwd_ret = mfe = mae = None
        t_pos = t_mfe = t_fail = None
        target_first = None
        gap_through = False
        fs = None
        fs_reason = "no_forward_sessions"
    elif n == 0:
        # only the day-0 sampled remainder exists (delisting after D): censor there
        arr = np.asarray(day0, dtype=float)
        fwd_ret = float(arr[-1] / p0 - 1.0)
        mfe = max(0.0, float(arr.max() / p0 - 1.0))
        mae = min(0.0, float(arr.min() / p0 - 1.0))
        t_pos = 0 if bool(np.any(arr > p0)) else None
        t_mfe = 0 if mfe > 0 else None
        target_first, gap_through = None, False
        fs, fs_reason, t_fail = _false_start(
            episode, highs=np.empty(0), lows=np.empty(0), closes=np.empty(0),
            p0=p0, adverse_atr=adverse_atr, favorable_atr=favorable_atr,
            daily=daily, horizon=horizon, day0=day0,
        )
    else:
        highs = fwd["h"].to_numpy(dtype=float)
        lows = fwd["l"].to_numpy(dtype=float)
        opens = fwd["o"].to_numpy(dtype=float)
        closes = fwd["c"].to_numpy(dtype=float)
        d0_max = max(day0) if day0 else None
        d0_min = min(day0) if day0 else None
        fwd_ret = float(closes[-1] / p0 - 1.0)
        path_high = float(highs.max()) if d0_max is None else max(float(highs.max()), d0_max)
        path_low = float(lows.min()) if d0_min is None else min(float(lows.min()), d0_min)
        mfe = max(0.0, path_high / p0 - 1.0)
        mae = min(0.0, path_low / p0 - 1.0)
        pos_hits = np.nonzero(closes > p0)[0]
        t_pos = int(pos_hits[0]) + 1 if pos_hits.size else (
            0 if (d0_max is not None and d0_max > p0) else None)
        if mfe > 0:
            t_mfe = (0 if (d0_max is not None and d0_max >= path_high)
                     else int(np.argmax(highs)) + 1)
        else:
            t_mfe = None

        if episode.a0 is not None and episode.a0 > 0:
            a0 = float(episode.a0)
            target = p0 + prereg.TARGET_ATR * a0
            invalid = p0 - prereg.INVALIDATION_ATR * a0
            first_t = _first_touch(day0, highs, target, up=True)
            first_i = _first_touch(day0, lows, invalid, up=False)
            if first_t is None and first_i is None:
                target_first = None
            elif first_i is None:
                target_first = True
            elif first_t is None:
                target_first = False
            else:
                # equal-position tie resolves ADVERSE-FIRST (frozen conservative law)
                target_first = first_t < first_i
            prior_closes = np.concatenate(([p0], closes[:-1]))
            gap_through = bool(np.any((opens < invalid) & (prior_closes >= invalid)))
        else:
            target_first = None
            gap_through = False

        fs, fs_reason, t_fail = _false_start(
            episode, highs=highs, lows=lows, closes=closes, p0=p0,
            adverse_atr=adverse_atr, favorable_atr=favorable_atr,
            daily=daily, horizon=horizon, day0=day0,
        )

    cost = float(cost_per_side_bps)
    fwd_net = None if fwd_ret is None else fwd_ret - 2.0 * cost / 1e4

    exb = _leg_excess(fwd_ret, bench_close, episode.decision_session, n)
    exs = (_leg_excess(fwd_ret, sector_close, episode.decision_session, n)
           if sector_close is not None else None)

    return OutcomeRow(
        ticker=episode.ticker, detector_id=episode.detector_id,
        panel=episode.panel, decision_session=episode.decision_session,
        horizon=horizon, era=era_of(episode.decision_session),
        p0=p0, p0_basis=episode.p0_basis, a0=episode.a0,
        atr_basis=episode.atr_basis,
        fwd_ret=fwd_ret, fwd_ret_net=fwd_net, mfe=mfe, mae=mae,
        time_to_positive=t_pos, time_to_mfe=t_mfe,
        target_before_invalidation=target_first,
        gap_through_invalidation=gap_through,
        false_start=fs, false_start_reason=fs_reason, time_to_failure=t_fail,
        excess_vs_bench=exb, excess_vs_sector=exs,
        cost_per_side_bps=cost, cost_basis=cost_basis,
        censored=censored, terminated_reason=terminated,
        sessions_covered=n, cohort=episode.cohort, regime=episode.regime,
        c32=episode.c32,
        evidence_tier="HISTORICAL" if era_of(episode.decision_session) == "FIT"
                      else "TEST",
    )


def _leg_excess(fwd_ret: float | None, leg_close: pd.Series,
                decision_session: date, n: int) -> float | None:
    """Subject P0-anchored minus leg close-to-close over the same n sessions."""
    if fwd_ret is None or n == 0:
        return None
    idx = leg_close.index
    pos = int(idx.searchsorted(pd.Timestamp(decision_session), side="right"))
    base_pos = pos - 1
    if base_pos < 0 or pos + n - 1 >= len(leg_close):
        return None
    base = float(leg_close.iloc[base_pos])
    end = float(leg_close.iloc[pos + n - 1])
    if not (np.isfinite(base) and np.isfinite(end)) or base <= 0:
        return None
    return fwd_ret - (end / base - 1.0)


def _first_touch(day0: list[float], session_arr: np.ndarray, level: float,
                 *, up: bool) -> tuple[int, int] | None:
    """Ordered first touch of ``level`` over (day-0 samples, then sessions).

    Returns a sortable position (segment, index): day-0 sample touches are
    (0, sample_idx); session touches are (1, session_idx).  ``up`` picks the
    crossing direction (>= level for favorable, <= level for adverse).
    """
    for i, px in enumerate(day0):
        if (px >= level) if up else (px <= level):
            return (0, i)
    arr = session_arr
    hits = np.nonzero(arr >= level)[0] if up else np.nonzero(arr <= level)[0]
    if hits.size:
        return (1, int(hits[0]))
    return None


def _false_start(episode: EpisodeRef, *, highs: np.ndarray, lows: np.ndarray,
                 closes: np.ndarray, p0: float, adverse_atr: float,
                 favorable_atr: float, daily: pd.DataFrame,
                 horizon: int,
                 day0: list[float] | None = None) -> tuple[bool | None, str | None, int | None]:
    """Frozen §10/§7 false-start law.

    Clause A: MAE reaches ``adverse_atr``x A0 BEFORE MFE reaches
    ``favorable_atr``x A0 — first-touch ordering over the §7 window INCLUDING
    the LIVE day-0 sampled segment (position (0, i)) ahead of daily sessions
    (position (1, s)); equal-position tie adverse-first.
    Clause B: confirmed 1D StochRSI re-enters K<20 AND a low below the episode
    washout low — the K-series is precomputed per name by the episodes stage and
    handed in via ``episode.extra["confirmed_k_fwd"]`` (array aligned to the
    forward sessions); absent => clause B is unevaluable and reported so.
    Episodes on a close-proxy ATR are EXCLUDED from the primary read (None).
    """
    if episode.a0 is None or episode.a0 <= 0 or episode.atr_basis != "true_range_daily_ohlc":
        return None, "excluded_close_proxy_atr" if episode.a0 else "excluded_no_atr", None
    day0 = day0 or []
    a0 = float(episode.a0)
    adverse_lvl = p0 - adverse_atr * a0
    favorable_lvl = p0 + favorable_atr * a0
    pos_a = _first_touch(day0, lows, adverse_lvl, up=False)
    pos_f = _first_touch(day0, highs, favorable_lvl, up=True)
    clause_a = (pos_a is not None
                and (pos_f is None or pos_a <= pos_f))  # tie => adverse-first

    clause_b = False
    k_fwd = episode.extra.get("confirmed_k_fwd")
    if episode.washout_low is not None and k_fwd is not None:
        k_arr = np.asarray(k_fwd, dtype=float)[: len(lows)]
        low_break = lows < float(episode.washout_low)
        k_below = np.zeros(len(lows), dtype=bool)
        m = min(len(k_arr), len(lows))
        k_below[:m] = k_arr[:m] < 20.0
        clause_b = bool(np.any(low_break & k_below))

    fs = bool(clause_a or clause_b)
    reason = ("mae_before_mfe" if clause_a else
              "k_reentry_below_washout_low" if clause_b else None)
    if clause_a and pos_a is not None:
        t_fail = 0 if pos_a[0] == 0 else pos_a[1] + 1
    elif (clause_b and episode.washout_low is not None
          and lows.size and np.any(lows < float(episode.washout_low))):
        t_fail = int(np.nonzero(lows < float(episode.washout_low))[0][0]) + 1
    else:
        t_fail = None
    return fs, reason, t_fail


__all__ = ["EpisodeRef", "OutcomeRow", "attach", "era_of"]
