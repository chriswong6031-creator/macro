"""Composition layer: candidates → reference units → outcomes → episode frame.

The runner (scripts/entry_radar_replay.py) owns I/O and iteration; THIS module
owns the lawful composition of the granular pieces (episodes → §6 reference
units → outcomes.attach → controls.match → the §7-contract frame
`confirmatory` consumes).  Pure: every price series, minute tape, quote list
and shares count is injected.

Prereg §6 P0 resolution, exactly:

* LIVE candidates (C1/C2) carry ``sampled_close_at_decision`` from the W3
  evaluation path — that IS P0 (`sampled_last_trade_at_decision`).
* Confirmed-bar candidates (G0/C3/C5/incumbent) take the opening print of the
  first RTH minute bar of the session AFTER the knowability session
  (`first_trade_after_known_at`); a refused minute window falls back to the
  next session's close (`next_session_close`) — never the signal bar's close.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from engine.entry_radar.indicator_core import atr14, last_finite
from engine.entry_radar.replay import controls, episodes, outcomes, prereg


@dataclass(frozen=True)
class ReferenceUnits:
    p0: float | None
    p0_basis: str
    a0: float | None
    atr_basis: str
    refusal: str | None  # non-None => the episode is refused, reason named


def _next_session_pos(daily: pd.DataFrame, session: date) -> int | None:
    idx = daily.index
    pos = int(idx.searchsorted(pd.Timestamp(session), side="right"))
    return pos if pos < len(daily) else None


def resolve_reference_units(
    cand: Mapping[str, Any], daily_vendor: pd.DataFrame,
    minute_open_fn: Callable[[str, date], float | None],
) -> ReferenceUnits:
    """§6 P0 + A0 for one candidate on the vendor plane.

    ``minute_open_fn(ticker, session)`` returns the first RTH minute bar's open
    for that session (the runner wraps the vendor client; fixtures inject a
    dict lookup), or None when the window is refused.
    """
    ticker = str(cand["ticker"])
    decision = cand["decision_session"]
    decision = decision if isinstance(decision, date) else pd.Timestamp(decision).date()

    basis_req = str(cand.get("p0_basis_required") or "")
    if basis_req == "sampled_last_trade_at_decision":
        p0 = cand.get("sampled_close_at_decision")
        if p0 is None or not np.isfinite(float(p0)):
            return ReferenceUnits(None, basis_req, None, "absent",
                                  "no_sampled_price_at_decision")
        p0, p0_basis = float(p0), basis_req
    elif basis_req == "first_trade_after_known_at":
        pos = _next_session_pos(daily_vendor, decision)
        if pos is None:
            return ReferenceUnits(None, basis_req, None, "absent",
                                  "no_session_after_knowability")
        entry_session = pd.Timestamp(daily_vendor.index[pos]).date()
        opening = minute_open_fn(ticker, entry_session)
        if opening is not None and np.isfinite(float(opening)) and float(opening) > 0:
            p0, p0_basis = float(opening), "first_trade_after_known_at"
        else:
            close = float(daily_vendor["c"].iloc[pos])
            if not np.isfinite(close) or close <= 0:
                return ReferenceUnits(None, basis_req, None, "absent",
                                      "no_lawful_p0")
            p0, p0_basis = close, "next_session_close"
    else:
        return ReferenceUnits(None, basis_req or "unknown", None, "absent",
                              f"unknown_p0_basis:{basis_req!r}")

    # A0: Wilder true-range ATR14 as of the PRIOR confirmed close (vendor plane).
    # ``hist`` ends strictly before the decision session, so the UNSHIFTED
    # atr14 tail IS the prior-confirmed value — the shifted variant here would
    # double-shift and hand back D-2's ATR.
    idx = daily_vendor.index
    dpos = int(idx.searchsorted(pd.Timestamp(decision), side="left"))
    hist = daily_vendor.iloc[:dpos]  # strictly before the decision session
    if len(hist) < 15:
        return ReferenceUnits(p0, p0_basis, None, "absent", "atr_warmup_short")
    a0 = last_finite(atr14(hist["h"], hist["l"], hist["c"]))
    if a0 is None or not np.isfinite(a0) or a0 <= 0:
        return ReferenceUnits(p0, p0_basis, None, "absent", "atr_unavailable")
    return ReferenceUnits(p0, p0_basis, float(a0), "true_range_daily_ohlc", None)


def control_forward_return(daily: pd.DataFrame, session: date, horizon: int) -> float | None:
    """Close-to-close D → D+H (the §7 control/bench leg shape)."""
    idx = daily.index
    pos = int(idx.searchsorted(pd.Timestamp(session), side="right"))
    base_pos = pos - 1
    if base_pos < 0 or pos + horizon - 1 >= len(daily):
        return None
    base = float(daily["c"].iloc[base_pos])
    end = float(daily["c"].iloc[pos + horizon - 1])
    if not (np.isfinite(base) and np.isfinite(end)) or base <= 0:
        return None
    return end / base - 1.0


def episode_row(
    ref: outcomes.EpisodeRef, row: outcomes.OutcomeRow,
    matched: controls.ControlMatch, unmatched: controls.ControlMatch,
    panel_daily: Mapping[str, pd.DataFrame], horizon: int = prereg.HORIZON_PRIMARY,
) -> dict[str, Any]:
    """One §7-contract frame row: net excess vs matched-control mean, plus the
    §9 proximity-unmatched companion and common-support flag."""
    def _pool_mean(match: controls.ControlMatch) -> float | None:
        rets = []
        for t in match.controls:
            d = panel_daily.get(t)
            if d is None:
                continue
            r = control_forward_return(d, ref.decision_session, horizon)
            if r is not None:
                rets.append(r)
        return float(np.mean(rets)) if rets else None

    m_mean = None if matched.uninformative_no_control else _pool_mean(matched)
    u_mean = None if unmatched.uninformative_no_control else _pool_mean(unmatched)
    excess = (None if (row.fwd_ret_net is None or m_mean is None)
              else row.fwd_ret_net - m_mean)
    excess_un = (None if (row.fwd_ret_net is None or u_mean is None)
                 else row.fwd_ret_net - u_mean)
    return {
        "name": ref.ticker, "session": pd.Timestamp(ref.decision_session),
        "detector": _look_key(ref.detector_id), "panel": ref.panel,
        "era": row.era, "excess_net": excess, "excess_net_unmatched": excess_un,
        "same_band_support": unmatched.same_band_control,
        "uninformative_no_control": matched.uninformative_no_control,
        "n_cell": int(matched.n_cell),
        "n_controls": len(matched.controls), "false_start": row.false_start,
        "fwd_ret": row.fwd_ret, "fwd_ret_net": row.fwd_ret_net,
        "mfe": row.mfe, "mae": row.mae,
        "time_to_positive": row.time_to_positive, "time_to_mfe": row.time_to_mfe,
        "target_before_invalidation": row.target_before_invalidation,
        "gap_through_invalidation": row.gap_through_invalidation,
        "excess_vs_bench": row.excess_vs_bench,
        "excess_vs_sector": row.excess_vs_sector,
        "cost_per_side_bps": row.cost_per_side_bps, "cost_basis": row.cost_basis,
        "censored": row.censored, "terminated_reason": row.terminated_reason,
        "cohort": ref.cohort, "regime": ref.regime, "c32": ref.c32,
        "p0_basis": ref.p0_basis, "atr_basis": ref.atr_basis,
        "variant": ref.extra.get("variant"),
        "c2a_fired_in_episode": ref.extra.get("c2a_fired_in_episode"),
        "common_eligible_c3_c2a": ref.extra.get("common_eligible_c3_c2a"),
        "evidence_tier": row.evidence_tier,
    }


def _look_key(detector_id: str) -> str:
    return {"G0_GREY_DOT@1": "G0", "C1_1D_LIVE_WASHOUT@1": "C1",
            "C2_1D_TURN@1": "C2A", "C3_1D_4H_RECOVERY@1": "C3",
            "C5_BOTTOM_WATCH@1": "C5", "INCUMBENT_2W_STOCH@0": "INCUMBENT",
            }.get(detector_id, detector_id)


def q5_pairs(g0_rows: pd.DataFrame, incumbent_fires_by_name: Mapping[str, Sequence[date]],
             session_positions: Mapping[pd.Timestamp, int],
             g0_false_start: Mapping[tuple[str, date], bool | None],
             incumbent_false_start: Mapping[tuple[str, date], bool | None],
             ) -> pd.DataFrame:
    """§10 Q5 two-sided nearest matching within ±30 sessions, signed gaps.

    ``session_positions`` maps session Timestamps to integer positions on the
    panel calendar (so the gap is in SESSIONS, not calendar days).  Unmatched
    candidates appear with NaN gap (counted for coverage; the +30 bounding read
    is a separate assembly).
    """
    rows: list[dict[str, Any]] = []
    for _, r in g0_rows.iterrows():
        name = str(r["name"])
        d = pd.Timestamp(r["session"])
        dpos = session_positions.get(d)
        best: tuple[int, date] | None = None
        for f in incumbent_fires_by_name.get(name, ()):
            fpos = session_positions.get(pd.Timestamp(f))
            if dpos is None or fpos is None:
                continue
            gap = fpos - dpos
            if abs(gap) <= prereg.Q5_INCUMBENT_JOIN_SESSIONS:
                if best is None or abs(gap) < abs(best[0]) or (
                        abs(gap) == abs(best[0]) and gap > best[0]):
                    best = (gap, f)
        row = {"name": name, "session": d,
               "matched_pair_gap": float(best[0]) if best else np.nan,
               "g0_false_start": g0_false_start.get((name, d.date())),
               "incumbent_false_start": (
                   incumbent_false_start.get((name, best[1])) if best else None)}
        rows.append(row)
    return pd.DataFrame(rows)


__all__ = ["ReferenceUnits", "resolve_reference_units", "control_forward_return",
           "episode_row", "q5_pairs"]
