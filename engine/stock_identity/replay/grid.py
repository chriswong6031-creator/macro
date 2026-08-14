"""Bucket grids and the known-ts map each producer's own convention implies.

**The whole point of this module is that no grid is re-derived here.** A 2D/3D Macro
bucket comes from ``engine.signal_quality._tf_grid`` — the module's own absolute-session
grid — because a second implementation of "which sessions are in bucket k" is exactly the
silent fork the archaeology (§4.2) names as the standing hazard. What this module adds is
the *stamping* rule the known-ts law needs, which the producers do not export:

===========  ==================================  ==========================================
grain        ``signal_ts``                        ``signal_known_ts``  (``known_basis``)
===========  ==================================  ==========================================
1D           the session itself                  the same session's close  (``daily_close``)
2D / 3D      the bucket's OPEN date (the §7       the bucket's LAST session that carried a
             public marker contract)              close  (``bucket_last_session_close``)
W-FRI        the completed weekly bar's Friday    the last actual session in that week
             label                                (``w_fri_completed_close``)
===========  ==================================  ==========================================

A 3D marker is therefore stamped with a ``known_ts`` up to two sessions AFTER its own
``signal_ts`` — that asymmetry is not a defect, it is the availability truth (Radar §3.1
records the same, with measured examples: NVDA ts 2026-01-21 -> known 01-23). Every
consumer of these events must key off ``signal_known_ts``.

The trailing bucket is **excluded** wherever it is still open: its close, and therefore
every oscillator on it, keeps moving until the bucket completes, so a fire read off it is
not knowable (``engine.us_early_turn._completed_bucket_mask`` records the measured ghost
re-dating this prevents). ``completed_mask`` implements that as a pure function of the
grid, so truncating the input frame and masking after the fact agree by construction.

The Terminal twin's ``resample("2B")`` bucketing lives in :mod:`..grey_dot`, not here —
it is part of that locked-spec port, not a house grid.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Registration §2 scoped allowlist. `_tf_grid` is the module's OWN grid helper; the brief
# is explicit that the Macro absolute-anchor grid must come from it and never be re-derived.
from engine.signal_quality import _tf_grid

__all__ = [
    "BucketGrid",
    "KNOWN_BASIS_DAILY",
    "KNOWN_BASIS_BUCKET",
    "KNOWN_BASIS_WEEKLY",
    "macro_grid",
    "daily_known",
    "period_bars",
    "weekly_completed",
]

KNOWN_BASIS_DAILY = "daily_close"
KNOWN_BASIS_BUCKET = "bucket_last_session_close"
KNOWN_BASIS_WEEKLY = "w_fri_completed_close"


@dataclass(frozen=True)
class BucketGrid:
    """One n-session Macro grid, with both stamps aligned on the same rows.

    ``label`` is the bucket OPEN date (the public §7 marker date); ``known`` is the
    bucket's last session carrying a close (the date the value became final). Both are
    ``DatetimeIndex``-shaped ``Series`` on the SAME positional order, so a boolean fire
    mask computed on the producer's frame indexes straight into either.
    """

    n: int
    label: pd.DatetimeIndex
    known: pd.Series          #: label -> last session with a close
    close: pd.Series          #: label -> bucket close
    daily_index: pd.DatetimeIndex

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.label)

    def completed_mask(self) -> np.ndarray:
        """Which rows are FINAL given the daily history that built this grid.

        The trailing bucket is complete only when its last session IS the last daily
        session AND that session sits on the bucket's final slot — i.e. the bucket holds
        ``n`` sessions of the working index. Everything earlier is complete by definition.
        """
        m = np.ones(len(self.label), dtype=bool)
        if len(self.label) == 0:
            return m
        di = self.daily_index
        last_known = pd.Timestamp(self.known.iloc[-1])
        # Count the working sessions inside the trailing bucket: from its open label to
        # its last session, inclusive.
        lo = int(di.searchsorted(pd.Timestamp(self.label[-1]), side="left"))
        hi = int(di.searchsorted(last_known, side="right"))
        if (hi - lo) < self.n:
            m[-1] = False
        return m


def macro_grid(daily_close: pd.Series, n: int, market: str = "US") -> BucketGrid:
    """The producer's OWN n-session absolute-anchor grid, with the known-ts stamp attached.

    Delegates entirely to :func:`engine.signal_quality._tf_grid`; this function adds no
    bucketing logic of its own, which is the point.
    """
    g = _tf_grid(daily_close, n, market)
    label = pd.DatetimeIndex(g.close.index)
    known = pd.Series(pd.DatetimeIndex(g.last_session.to_numpy()), index=label)
    return BucketGrid(
        n=int(n),
        label=label,
        known=known,
        close=pd.Series(g.close.to_numpy(), index=label),
        daily_index=pd.DatetimeIndex(g.index),
    )


def daily_known(dates) -> pd.Series:
    """1D grain: a daily event is knowable at its own close."""
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    return pd.Series(idx, index=idx)


def period_bars(daily_close: pd.Series, rule: str) -> pd.DataFrame:
    """Calendar-resampled bars carrying BOTH real session stamps.

    A right-labelled resample (``W-FRI``, ``2W-FRI``, ``ME``) stamps each bucket with a
    calendar date the instrument may never have traded, and that label sits at the END of
    the period — so using it as ``signal_ts`` would put the event's own date AFTER the
    close that made it knowable, which inverts the known-ts law. The fix is to carry the
    bucket's first and last ACTUAL sessions and let callers stamp
    ``signal_ts = open_session`` / ``signal_known_ts = known`` — the same "opens here,
    becomes final there" semantics the session-anchored 2D/3D grids already have.

    The trailing bucket is dropped: whether it has closed is not decidable from the series
    alone for every rule, and one forgone bucket at the very end of history is the only
    conservative direction.

    Returns a positionally-indexed frame of ``label``, ``open``, ``known``, ``close``.
    """
    s = pd.to_numeric(daily_close, errors="coerce").dropna().sort_index()
    empty = pd.DataFrame({"label": pd.Series(dtype="datetime64[ns]"),
                          "open": pd.Series(dtype="datetime64[ns]"),
                          "known": pd.Series(dtype="datetime64[ns]"),
                          "close": pd.Series(dtype="float64")})
    if s.empty:
        return empty
    grp = s.resample(rule)
    vals = grp.last().dropna()
    if len(vals) < 2:
        return empty
    first = grp.apply(lambda x: x.index[0] if len(x) else pd.NaT).reindex(vals.index)
    last = grp.apply(lambda x: x.index[-1] if len(x) else pd.NaT).reindex(vals.index)
    out = pd.DataFrame({
        "label": pd.DatetimeIndex(vals.index),
        "open": pd.DatetimeIndex(first),
        "known": pd.DatetimeIndex(last),
        "close": vals.to_numpy(dtype="float64"),
    }).reset_index(drop=True)
    return out.iloc[:-1].reset_index(drop=True)


def weekly_completed(daily_close: pd.Series) -> pd.DataFrame:
    """Completed W-FRI bars — the grain the weekly washout organ reads."""
    return period_bars(daily_close, "W-FRI")
