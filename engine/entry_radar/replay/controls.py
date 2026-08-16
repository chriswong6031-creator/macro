"""Matched-control selection under the frozen §7 prereg law.

Deterministic by construction: CEM cell (same session, sector, cap bucket,
proximity decile) then k=5 nearest by L1 over four bucket indices, ties broken
by (distance, lexicographic ticker).  Exclusions: fired the detector within
±5 sessions of D; fires it anywhere in (D, D+H]; suppressed_by_rearm at D.
Zero eligible controls => the candidate is recorded ``uninformative_no_control``
and excluded from the primary mean (counted in the §9 overlap diagnostic).

The feature panel rows are produced by the features stage; this module only
selects.  Pure; no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from engine.entry_radar.replay import prereg


#: Feature-panel columns this module requires per (ticker, session) row.
REQUIRED_COLUMNS = (
    "ticker", "sector", "cap_bucket", "proximity_decile",
    "dollar_vol_decile", "ret60_quintile", "vol20_quintile", "hot_tier",
)

_DIST_COLS = ("dollar_vol_decile", "ret60_quintile", "vol20_quintile", "hot_tier")


@dataclass(frozen=True)
class ControlMatch:
    """The controls chosen for one candidate, with the §9 diagnostics."""

    ticker: str
    session: date
    controls: tuple[str, ...]          # <= k tickers, deterministic order
    n_cell: int                        # CEM cell size before k-NN
    uninformative_no_control: bool
    same_band_control: bool            # >= 1 control in the same proximity band


def eligible_pool(panel: pd.DataFrame, *, detector_fire_sessions: Mapping[str, Sequence[date]],
                  candidate_session: date, horizon: int = prereg.HORIZON_PRIMARY,
                  suppressed: frozenset[str] = frozenset()) -> pd.DataFrame:
    """Filter the session's feature panel down to lawful control rows.

    ``panel`` holds ONE session's rows (every name in the candidate's panel with
    features computable at D).  ``detector_fire_sessions`` maps ticker -> sorted
    fire decision-sessions for the SAME detector (replay-wide), used for both
    the ±5-session window and the (D, D+H] forward-fire exclusion.
    ``suppressed`` carries tickers inside the §10 re-arm blackout at D.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in panel.columns]
    if missing:
        raise ValueError(f"feature panel missing columns {missing}")
    near = prereg.CONTROL_NO_FIRE_NEAR_SESSIONS
    keep: list[bool] = []
    d0 = pd.Timestamp(candidate_session)
    for t in panel["ticker"]:
        fires = detector_fire_sessions.get(str(t), ())
        bad = False
        if str(t) in suppressed:
            bad = True
        else:
            for f in fires:
                off = _session_offset(panel, f, candidate_session)
                if off is None:
                    # fire session outside this panel's calendar → conservative
                    # calendar-day proxy only for the ±near window
                    delta = abs((pd.Timestamp(f) - d0).days)
                    if delta <= near * 2:
                        bad = True
                        break
                    continue
                if -near <= off <= near:
                    bad = True
                    break
                if 0 < off <= horizon:
                    bad = True
                    break
        keep.append(not bad)
    return panel[np.asarray(keep, dtype=bool)]


def _session_offset(panel: pd.DataFrame, other: date, base: date) -> int | None:
    """Session-count offset (other - base) using the panel's session calendar
    when it carries one (column ``session_pos``); None => unknown."""
    if "session_pos_by_date" in panel.attrs:
        pos = panel.attrs["session_pos_by_date"]
        a, b = pos.get(pd.Timestamp(other)), pos.get(pd.Timestamp(base))
        if a is None or b is None:
            return None
        return int(a - b)
    return None


#: §7 normalizers (M6): every soft axis maps to [0, 1] before L1, so no axis
#: silently dominates.  deciles 0-9 → /9; quintiles 1-5 → (q-1)/4; hot 0/1.
_AXIS_SCALE = {
    "dollar_vol_decile": lambda v: v / 9.0,
    "ret60_quintile": lambda v: (v - 1.0) / 4.0,
    "vol20_quintile": lambda v: (v - 1.0) / 4.0,
    "hot_tier": lambda v: float(v),
}


def _norm_vec(row_like) -> np.ndarray:
    return np.asarray([_AXIS_SCALE[c](float(row_like[c])) for c in _DIST_COLS])


def match(candidate_row: pd.Series, pool: pd.DataFrame,
          *, k: int = prereg.CONTROL_K,
          match_proximity: bool = True,
          max_distance: float = prereg.CONTROL_MAX_DISTANCE) -> ControlMatch:
    """CEM cell + capped, normalized k-NN inside the lawful pool.

    ``match_proximity=True`` is the §7 primary (proximity decile in the CEM
    cell); ``False`` is the §9 NC-2 proximity-UNMATCHED companion — identical
    mechanics with the proximity dimension dropped.  ``same_band_control``
    reports whether the chosen set contains ≥1 control in the candidate's own
    proximity band — on the unmatched variant this is the §9 common-support
    diagnostic (on the matched variant it is trivially True when any control
    exists).
    """
    mask = (
        (pool["sector"] == candidate_row["sector"])
        & (pool["cap_bucket"] == candidate_row["cap_bucket"])
        & (pool["ticker"] != candidate_row["ticker"])
    )
    if match_proximity:
        mask &= pool["proximity_decile"] == candidate_row["proximity_decile"]
    cell = pool[mask]
    n_cell = int(len(cell))
    if n_cell == 0:
        return ControlMatch(
            ticker=str(candidate_row["ticker"]),
            session=candidate_row["session"],
            controls=(), n_cell=0,
            uninformative_no_control=True, same_band_control=False,
        )
    cand_vec = _norm_vec(candidate_row)
    dists = np.abs(
        np.stack([cell[c].map(_AXIS_SCALE[c]).to_numpy(dtype=float)
                  for c in _DIST_COLS], axis=1) - cand_vec
    ).sum(axis=1)
    admissible = [i for i in range(n_cell) if dists[i] <= max_distance]
    if not admissible:
        return ControlMatch(
            ticker=str(candidate_row["ticker"]),
            session=candidate_row["session"],
            controls=(), n_cell=n_cell,
            uninformative_no_control=True, same_band_control=False,
        )
    order = sorted(admissible, key=lambda i: (dists[i], str(cell["ticker"].iloc[i])))
    chosen_idx = order[:k]
    chosen = tuple(str(cell["ticker"].iloc[i]) for i in chosen_idx)
    band = candidate_row["proximity_decile"]
    same_band = bool(any(cell["proximity_decile"].iloc[i] == band for i in chosen_idx))
    return ControlMatch(
        ticker=str(candidate_row["ticker"]),
        session=candidate_row["session"],
        controls=chosen, n_cell=n_cell,
        uninformative_no_control=False, same_band_control=same_band,
    )


def overlap_share(matches: Sequence[ControlMatch]) -> float:
    """§9 NC-2 common-support diagnostic: share of candidates whose
    proximity-UNMATCHED admissible control set contains ≥1 same-band member.
    Feed this the ``match_proximity=False`` matches.  NaN on empty input."""
    if not matches:
        return float("nan")
    return float(np.mean([m.same_band_control for m in matches]))


__all__ = ["REQUIRED_COLUMNS", "ControlMatch", "eligible_pool", "match",
           "overlap_share"]
