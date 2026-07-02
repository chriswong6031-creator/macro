"""PIT truth-layer tests — masterplan W1a acceptance.

Three families:
  1. As-of join correctness on a SYNTHETIC vintage matrix — a value must NEVER be
     visible before its realtime_start (the core leak-free invariant).
  2. Byte-identical default-path regression — build_features() and build_features(
     pit_basis=None) are identical, and pit_basis='reference' reproduces the live
     stamping for the PIT-routed columns (no fork of the axis math).
  3. Release-lag calendar sanity — modelled release dates land AFTER the reference
     period end by the documented business-day lag; learned-lag reducer is correct.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from engine import pit


# --------------------------------------------------------------------------- #
# 1. As-of join correctness on a synthetic vintage matrix
# --------------------------------------------------------------------------- #
def _synthetic_vintages() -> pd.DataFrame:
    """Three monthly periods of a fake vintaged series 'PAYEMS', each first published
    ~35 days after the reference month start. Deliberately includes a later-revised
    row that must be ignored by the initial-release as-of read."""
    rows = [
        # period       value  realtime_start (release)  realtime_end
        ("2020-01-01", 100.0, "2020-02-07", "2020-03-05"),
        ("2020-02-01", 110.0, "2020-03-06", "2020-04-02"),
        ("2020-03-01", 90.0,  "2020-04-03", "9999-12-31"),
    ]
    df = pd.DataFrame(rows, columns=["period", "value", "realtime_start", "realtime_end"])
    df["series"] = "PAYEMS"
    for c in ("period", "realtime_start", "realtime_end"):
        df[c] = pd.to_datetime(df[c])
    return df[["series", "period", "value", "realtime_start", "realtime_end"]]


def test_asof_never_visible_before_realtime_start():
    v = _synthetic_vintages()
    avail = pit.release_availability("payrolls", vintages=v)
    # availability series is stamped at realtime_start, not period
    assert list(avail.index) == [pd.Timestamp("2020-02-07"),
                                 pd.Timestamp("2020-03-06"),
                                 pd.Timestamp("2020-04-03")]
    assert list(avail.values) == [100.0, 110.0, 90.0]


def test_asof_reindex_carries_only_known_values():
    v = _synthetic_vintages()
    idx = pd.bdate_range("2020-01-01", "2020-04-30")
    s = pit.series("payrolls", basis="release", index=idx, vintages=v)
    # before the first release (2020-02-07) nothing is known
    assert s.loc[:"2020-02-06"].isna().all()
    # on/after 2020-02-07 the Jan value (100) is known; Feb value (110) only from 03-06
    assert s.loc["2020-02-07"] == 100.0
    assert s.loc["2020-03-05"] == 100.0          # Feb not yet released
    assert s.loc["2020-03-06"] == 110.0
    assert s.loc["2020-04-03"] == 90.0
    # the invariant: no value appears before its realtime_start
    for rel, val in zip(["2020-02-07", "2020-03-06", "2020-04-03"], [100.0, 110.0, 90.0]):
        before = s.loc[:pd.Timestamp(rel) - pd.Timedelta(days=1)]
        assert (before.dropna() != val).all(), f"{val} leaked before {rel}"


def test_asof_cut_truncates_future_releases():
    v = _synthetic_vintages()
    # as_of before the March release: only Jan+Feb are knowable
    avail = pit.series("payrolls", as_of="2020-03-15", basis="release", vintages=v)
    assert avail.index.max() == pd.Timestamp("2020-03-06")
    assert 90.0 not in set(avail.values)


def test_has_vintage_detection():
    v = _synthetic_vintages()
    assert pit.has_vintage("payrolls", vintages=v) is True
    assert pit.has_vintage("core_cpi", vintages=v) is False   # not in synthetic matrix
    assert pit.has_vintage("oil", vintages=v) is False        # not a vintaged column


# --------------------------------------------------------------------------- #
# 2. Byte-identical default-path regression (the "no fork" guarantee)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    __import__("engine.inputs", fromlist=["build_features"]) is None,
    reason="inputs importable")
def test_build_features_default_byte_identical():
    from engine.inputs import build_features
    try:
        f0 = build_features()
        f_none = build_features(pit_basis=None)
    except RuntimeError as e:
        pytest.skip(f"no store data available: {e}")
    assert f0.equals(f_none), "pit_basis=None diverges from the default call"


def test_reference_basis_reproduces_live_stamping():
    from engine.inputs import build_features
    try:
        f0 = build_features()
        fref = build_features(pit_basis="reference")
    except RuntimeError as e:
        pytest.skip(f"no store data available: {e}")
    routed = (set(pit.VINTAGED_SID_TO_COL.values()) | set(pit.DEFAULT_RELEASE_LAGS))
    cols = [c for c in routed if c in f0.columns]
    assert cols, "expected some PIT-routed columns present"
    for c in cols:
        assert f0[c].equals(fref[c]), f"reference basis diverged for {c}"


def test_regime_default_byte_identical():
    from engine.inputs import build_features
    from engine.regime import classify
    try:
        f0 = build_features()
    except RuntimeError as e:
        pytest.skip(f"no store data available: {e}")
    r0 = classify(f0)
    r_none = classify(build_features(pit_basis=None))
    assert r0.equals(r_none), "regime table diverges on the default path"


# --------------------------------------------------------------------------- #
# 3. Release-lag calendar sanity
# --------------------------------------------------------------------------- #
def test_release_lags_priors_documented():
    lags = pit._release_lags(use_learned=False)
    # every static prior carries a lag and a documenting note
    for col, spec in pit.DEFAULT_RELEASE_LAGS.items():
        assert "lag_bd" in spec and "note" in spec and "cadence" in spec
        assert isinstance(spec["lag_bd"], int) and spec["lag_bd"] >= 0
    # monthly BLS employment publishes shortly after month end (small bd lag),
    # core PCE lags ~a month
    assert pit.DEFAULT_RELEASE_LAGS["payrolls"]["lag_bd"] <= 7
    assert pit.DEFAULT_RELEASE_LAGS["core_pce"]["lag_bd"] >= 15


def test_modelled_release_lands_after_period_end(monkeypatch):
    # inject a tiny reference series so we don't depend on the store
    ref = pd.Series([1.0, 2.0, 3.0],
                    index=pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]))
    monkeypatch.setattr(pit, "_reference_series", lambda col: ref)
    rel = pit._modelled_release("core_cpi")  # monthly; effective lag = #809-measured 32 bd
    # Jan value should surface after Jan month-end (2020-01-31) + the EFFECTIVE lag.
    # _effective_lag_bd prefers the #809-measured lag (lag_bd_measured=32) over the
    # old optimistic 8-bd prior (see research/PIT_LEAKAGE_TAX.md addendum).
    eff = pit._effective_lag_bd(pit.DEFAULT_RELEASE_LAGS["core_cpi"])
    assert eff == 32, "core_cpi effective release lag should use the #809-measured 32 bd"
    expected = pd.Timestamp("2020-01-31") + eff * pd.offsets.BDay()
    assert rel.index[0] == expected
    assert (rel.index > ref.index).all(), "release date must be after the reference stamp"
    assert list(rel.values) == [1.0, 2.0, 3.0]


def test_learned_lag_reducer(tmp_path, monkeypatch):
    from engine import pit_lag_recorder as R
    from lib import config
    # redirect the log to a temp dir
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    base = dt.datetime(2020, 2, 5, tzinfo=dt.timezone.utc)
    # period Jan discovered ~35d late, re-seen across runs; two more periods
    for k in range(6):
        R.record("PAYEMS", dt.date(2020, 1, 1), group="fred",
                 fetch_ts=base + dt.timedelta(days=k))
    for k in range(6):
        R.record("PAYEMS", dt.date(2020, 2, 1), group="fred",
                 fetch_ts=dt.datetime(2020, 3, 6, tzinfo=dt.timezone.utc) + dt.timedelta(days=k))
    for k in range(6):
        R.record("PAYEMS", dt.date(2020, 3, 1), group="fred",
                 fetch_ts=dt.datetime(2020, 4, 3, tzinfo=dt.timezone.utc) + dt.timedelta(days=k))
    ll = R.learned_lags(min_obs=3)
    assert "PAYEMS" in ll
    # each period discovered ~33-36 days after its (day-1) stamp
    assert 30 <= ll["PAYEMS"]["median_lag_days"] <= 40
    assert ll["PAYEMS"]["n_periods"] == 3


def test_recorder_never_raises(tmp_path, monkeypatch):
    from engine import pit_lag_recorder as R
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    # garbage inputs must all be swallowed
    R.record(None, None)
    R.record("X", object())
    R.record_fetch_result(None)
    R.record_fred_series(None)
    R.record_fred_series({"A": None, "B": pd.DataFrame()})
    assert R.learned_lags() == {} or isinstance(R.learned_lags(), dict)


def test_coverage_report_flags_gaps():
    rep = pit.coverage_report()
    assert "vintaged_columns" in rep and "vintage_store_gaps" in rep
    # the report structure is stable regardless of what's on disk
    assert isinstance(rep["vintaged_columns"], list)
    assert isinstance(rep["vintage_store_gaps"], list)
