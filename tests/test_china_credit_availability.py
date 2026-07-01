"""China TSF credit-impulse publication-availability stamping (audit #27).

The bug: the collector stamps TSF at reference-month START (April data -> 2026-04-01)
and the consumers shifted it a fixed 22 trading days, landing the impulse ~10 days
BEFORE the real ~day 9-15 release — a systematic look-ahead on China's most market-
moving macro print, feeding the 0.45-weight credit leg of the leveraged China book.

The fix re-stamps the TSF-derived series onto its publication-availability date
(day 16 of the following month, conservative bound) so a value can only be acted on
AFTER it was released. These tests are pure-function / synthetic-store — no network.

Run: python -m pytest tests/test_china_credit_availability.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.china_credit import tsf_availability_date, TSF_RELEASE_DOM  # noqa: E402
from engine import china_strategies as S  # noqa: E402


# --------------------------------------------------------------------------- #
# the availability-date model
# --------------------------------------------------------------------------- #
def test_availability_is_day16_of_following_month():
    # April data (reference-month start) becomes actable day 16 of MAY.
    assert tsf_availability_date(pd.Timestamp("2026-04-01")) == pd.Timestamp("2026-05-16")
    # December rolls into the next year.
    assert tsf_availability_date(pd.Timestamp("2025-12-01")) == pd.Timestamp("2026-01-16")
    # January.
    assert tsf_availability_date(pd.Timestamp("2026-01-01")) == pd.Timestamp("2026-02-16")
    assert TSF_RELEASE_DOM == 16


def test_availability_never_precedes_the_real_release_window():
    """NBS/PBoC release the prior month's TSF ~day 9-15 of the following month.
    The conservative availability bound (day 16) must be on/after the LATEST of
    that window for every month — so a backtest can never peek early."""
    for m in pd.date_range("2015-01-01", "2026-04-01", freq="MS"):
        avail = tsf_availability_date(m)
        latest_real_release = (m + pd.offsets.MonthBegin(1)).replace(day=15)
        assert avail >= latest_real_release, f"{m.date()} avail {avail.date()} precedes real release"


def test_availability_is_strictly_later_than_old_22bd_guess():
    """Guard-the-guard: the OLD fixed 22-trading-day shift from month-start landed
    BEFORE the availability date for recent months — proving the leak existed and
    the fix moves the actable date later (never earlier)."""
    moved_later = 0
    for m in pd.date_range("2024-01-01", "2026-04-01", freq="MS"):
        new_avail = tsf_availability_date(m)
        old_avail = pd.bdate_range(m, periods=23)[-1]     # month-start + 22 business days
        assert new_avail >= old_avail, f"{m.date()}: fix must not move the print EARLIER"
        if new_avail > old_avail:
            moved_later += 1
    assert moved_later >= 20, "the fix should push most prints materially later (the closed leak)"


# --------------------------------------------------------------------------- #
# the engine re-stamper (synthetic store — no network)
# --------------------------------------------------------------------------- #
def _synthetic_tsf_frame():
    """A reference-month-start-indexed TSF frame with the additive
    availability_date column, exactly as the patched collector emits."""
    idx = pd.date_range("2015-01-01", periods=36, freq="MS")
    df = pd.DataFrame({"tsf_total": np.linspace(1000, 2000, len(idx))}, index=idx)
    df["availability_date"] = [tsf_availability_date(d) for d in idx]
    return df


def test_availability_stamp_moves_index_to_release_dates(monkeypatch):
    df = _synthetic_tsf_frame()
    monkeypatch.setattr(S.store, "read",
                        lambda g, k: df if (g, k) == ("china_credit", "tsf") else None)
    # a reference-month-start-indexed derived series (as _credit_derisk builds)
    ref_series = pd.Series(np.arange(len(df), dtype=float), index=df.index)
    stamped = S._tsf_availability_stamp(ref_series)
    # every stamped date must be a day-16 availability date, strictly AFTER its ref month
    for ref, avail in zip(df.index, stamped.index):
        assert avail.day == TSF_RELEASE_DOM
        assert avail > ref
    # values are preserved, just re-dated
    assert list(stamped.to_numpy()) == list(ref_series.to_numpy())


def test_availability_stamp_falls_back_without_column(monkeypatch):
    """A parquet written before this change (no availability_date column) must
    still de-leak via the conservative model, never fall back to reference dates."""
    idx = pd.date_range("2020-01-01", periods=6, freq="MS")
    df = pd.DataFrame({"tsf_total": np.arange(6.0)}, index=idx)   # NO availability_date
    monkeypatch.setattr(S.store, "read",
                        lambda g, k: df if (g, k) == ("china_credit", "tsf") else None)
    ref_series = pd.Series(np.arange(6.0), index=idx)
    stamped = S._tsf_availability_stamp(ref_series)
    for ref, avail in zip(idx, stamped.index):
        assert avail == tsf_availability_date(ref)
        assert avail > ref


def test_credit_leg_lag_is_small_not_22(monkeypatch):
    """The consumers must now use the small residual execution lag, not the old
    22-trading-day peek (the availability stamp already carries the release lag)."""
    assert S._CREDIT_EXEC_LAG <= 2
    # both consumers key on the shared constant, so they stay in lockstep
    from engine import china_masterminds as MM
    assert MM._LAG_CREDIT == S._CREDIT_EXEC_LAG


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
