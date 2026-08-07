"""walk_forward.tf_bars must share confluence.compute_signals' 3D label geometry.

The 2026-08-06 defect: tf_bars built its own ``resample("3B")`` calendar bins while
``confluence.compute_signals`` had moved to session-grouped 3D bars labelled by OPEN
date.  The gold path exact-match-reindexes tf_bars' known-date series onto
``compute_signals``' index, and the two label systems only coincided while the
cumulative market-holiday count since series start ≡ 0 (mod 3) — so 67.3-67.6% of 3D
bars (measured AAPL/NUE/PEP) got NaN known-dates and were silently dropped from the
gold entry/exit stream.  tf_bars now delegates to ``confluence._3d_groups``; these
tests pin the label agreement on a calendar where the old construction provably
diverged, so a revert to resample-style bins fails loudly here.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _wf():
    sys.path.insert(0, str(_ROOT / "research" / "signal_engine"))
    import walk_forward as W  # noqa: E402
    return W


def _holiday_daily(periods: int = 400) -> pd.Series:
    """A synthetic close series on a session calendar with an EARLY mid-week holiday.

    Dropping one business day shifts the cumulative-holiday count to 1 (mod 3) for the
    rest of the series — the exact regime where resample("3B") bin labels diverge from
    session-grouped OPEN-date labels, i.e. where the old tf_bars dropped nearly every
    bar.  A fixture without the holiday would pass even under the old defective code."""
    idx = pd.bdate_range("2020-01-06", periods=periods + 1)
    idx = idx.delete(7)  # remove a mid-week session (2020-01-15, a Wednesday)
    rng = np.random.default_rng(7)
    px = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, len(idx))))
    return pd.Series(px, index=idx, name="close")


def test_known_dates_cover_every_compute_signals_bar():
    """THE defect check: reindexing tf_bars' known series onto compute_signals' index
    must lose nothing — a single NaN means the gold stream is subsampling itself."""
    W = _wf()
    from confluence import compute_signals

    daily = _holiday_daily()
    sig = compute_signals(daily)
    assert not sig.empty, "fixture too short for compute_signals' 90-bar floor"
    _, kn = W.tf_bars(daily, 3)

    assert sig.index.equals(kn.index), "tf_bars labels != compute_signals labels"
    reindexed = kn.reindex(sig.index)
    assert reindexed.notna().all(), (
        f"{reindexed.isna().mean():.0%} of 3D bars lost their known date — "
        "tf_bars' label geometry has drifted from confluence.compute_signals again")

    # fixture self-check: the old resample("3B") construction really does diverge on
    # this calendar (otherwise this file could go vacuous under a revert).
    old_labels = daily.resample("3B").last().dropna().index
    assert not old_labels.equals(kn.index)


def test_known_dates_are_the_bars_last_traded_session():
    """Leak-freeness: each bar's known date is its LAST session — a real traded day, at
    or after the OPEN-date label — and the next bar opens the session right after it."""
    W = _wf()
    daily = _holiday_daily()
    s, kn = W.tf_bars(daily, 3)

    assert (kn.values >= kn.index.values).all()
    assert pd.DatetimeIndex(kn.values).isin(daily.index).all()

    di = daily.index
    pos_open = di.searchsorted(kn.index)
    pos_known = di.searchsorted(pd.DatetimeIndex(kn.values))
    assert (pos_open[1:] == pos_known[:-1] + 1).all(), "bars must partition the sessions"
    widths = pos_known - pos_open + 1
    assert set(np.unique(widths[1:-1])) == {3}, "interior 3D bars must span 3 sessions"
    assert widths[-1] in (1, 2, 3)
    # the bar close is the daily close at the known date
    assert np.allclose(s.to_numpy(), daily.reindex(pd.DatetimeIndex(kn.values)).to_numpy())


def test_n1_identity_and_other_n_refused():
    """n==1 stays the daily identity; any n without a confluence geometry is refused
    instead of silently handing back calendar bins (the defect's shape)."""
    W = _wf()
    daily = _holiday_daily(120)
    d1, k1 = W.tf_bars(daily, 1)
    assert d1.equals(daily)
    assert (k1.index == pd.DatetimeIndex(k1.values)).all()
    for n in (2, 5):
        with pytest.raises(ValueError, match="confluence"):
            W.tf_bars(daily, n)
