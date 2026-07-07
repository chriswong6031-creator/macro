"""tests/test_build_netliq_daily.py — contract tests for the CPI net-liquidity artifact.

Covers (all on synthetic component parquets, never the live data tree):
  (a) billions-scale unit contract: WALCL_bn dominates the drains, and the canon
      identity netliq_bn == walcl_bn − rrp_bn − tga_bn holds elementwise;
  (b) fillna(0) drain behavior: a missing TGA file and a late-starting RRP series
      contribute 0 instead of annihilating the balance-sheet trend;
  (c) d13w/d26w window math: exact 65-/130-row differences on a linear ramp;
  (d) expanding-percentile PIT purity: values at t are unchanged when future rows
      are appended (and a strictly rising series ranks 1.0 everywhere);
  (e) stale-guard truncation: the frame stops at min(component last obs) + 10bd;
  (f) determinism: two rebuilds from the same inputs are identical.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.build_netliq_daily import (  # noqa: E402
    D13W_ROWS,
    D26W_ROWS,
    STALE_GUARD_BDAYS,
    build_frame,
)

# ---------------------------------------------------------------------------
# Synthetic component fixtures — raw-parquet schemas mirror the live files:
#   data/fred/WALCL.parquet      col fed_balance_sheet, $ MILLIONS, weekly
#   data/fred/RRPONTSYD.parquet  col on_rrp,            $ BILLIONS, business-daily
#   data/treasury/tga.parquet    col tga_mn,            $ MILLIONS, business-daily
# ---------------------------------------------------------------------------


def _write(path: Path, dates: pd.DatetimeIndex, values, col: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({col: values}, index=pd.DatetimeIndex(dates, name="date")).to_parquet(path)


def _setup(tmp_path: Path, walcl=None, rrp=None, tga=None) -> tuple[Path, Path]:
    """Write whichever synthetic components are given; return (fred_dir, tga_path)."""
    fred = tmp_path / "fred"
    fred.mkdir(parents=True, exist_ok=True)
    tga_path = tmp_path / "treasury" / "tga.parquet"
    if walcl is not None:
        _write(fred / "WALCL.parquet", walcl[0], walcl[1], "fed_balance_sheet")
    if rrp is not None:
        _write(fred / "RRPONTSYD.parquet", rrp[0], rrp[1], "on_rrp")
    if tga is not None:
        _write(tga_path, tga[0], tga[1], "tga_mn")
    return fred, tga_path


_DATES = pd.bdate_range("2024-01-01", periods=300)


def _standard_components():
    """A realistic-magnitude component set on a 300-bday calendar."""
    walcl_dates = _DATES[::5]                                    # weekly, like H.4.1
    walcl_mn = 7_000_000.0 + np.arange(len(walcl_dates)) * 1_000.0
    rrp_bn = np.linspace(500.0, 5.0, len(_DATES))                # drain running off
    tga_mn = np.full(len(_DATES), 750_000.0)                     # $750bn, in millions
    return (walcl_dates, walcl_mn), (_DATES, rrp_bn), (_DATES, tga_mn)


# ---------------------------------------------------------------------------
# (a) billions-scale unit contract + canon identity
# ---------------------------------------------------------------------------


def test_billions_scale_ordering_and_identity(tmp_path):
    walcl, rrp, tga = _standard_components()
    fred, tga_path = _setup(tmp_path, walcl=walcl, rrp=rrp, tga=tga)
    df, meta = build_frame(fred, tga_path)

    # WALCL correctly landed in the THOUSANDS of billions and dominates both drains
    assert 1_000 < df["walcl_bn"].max() < 100_000, "WALCL not in billions — unit contract broken"
    assert df["walcl_bn"].max() >= df["rrp_bn"].max()
    assert df["walcl_bn"].max() >= df["tga_bn"].max()
    # drains scaled correctly (TGA millions → billions)
    assert df["tga_bn"].max() == pytest.approx(750.0)
    assert df["rrp_bn"].max() == pytest.approx(500.0)
    # the ONE formula, elementwise
    resid = (df["netliq_bn"] - (df["walcl_bn"] - df["rrp_bn"] - df["tga_bn"])).abs().max()
    assert resid < 1e-9
    # union index covers every business day (rrp+tga are daily) minus nothing
    assert len(df) == len(_DATES)
    assert meta["components_missing"] == []


# ---------------------------------------------------------------------------
# (b) fillna(0) drain behavior
# ---------------------------------------------------------------------------


def test_missing_tga_file_contributes_zero(tmp_path):
    walcl, rrp, _ = _standard_components()
    fred, tga_path = _setup(tmp_path, walcl=walcl, rrp=rrp, tga=None)  # NO tga parquet
    df, meta = build_frame(fred, tga_path)
    assert (df["tga_bn"] == 0.0).all(), "missing TGA must contribute 0, not NaN"
    resid = (df["netliq_bn"] - (df["walcl_bn"] - df["rrp_bn"])).abs().max()
    assert resid < 1e-9
    assert meta["components_missing"] == ["tga"]
    # the balance-sheet trend must NOT be annihilated (the original audit-#28 failure)
    assert df["netliq_bn"].max() > 1_000


def test_late_starting_rrp_prehistory_is_zero(tmp_path):
    walcl, rrp, tga = _standard_components()
    late_rrp = (_DATES[150:], np.full(150, 300.0))               # RRP only exists late
    fred, tga_path = _setup(tmp_path, walcl=walcl, rrp=late_rrp, tga=tga)
    df, _ = build_frame(fred, tga_path)
    pre = df[df["date"] < _DATES[150]]
    post = df[df["date"] >= _DATES[150]]
    assert (pre["rrp_bn"] == 0.0).all(), "pre-history drain must fillna(0)"
    assert (post["rrp_bn"] == 300.0).all()


# ---------------------------------------------------------------------------
# (c) d13w / d26w window math
# ---------------------------------------------------------------------------


def test_window_changes_on_linear_ramp(tmp_path):
    n = 200
    dates = pd.bdate_range("2024-01-01", periods=n)
    walcl_mn = (1_000.0 + np.arange(n)) * 1_000.0                # walcl_bn = 1000 + i
    fred, tga_path = _setup(
        tmp_path,
        walcl=(dates, walcl_mn),
        rrp=(dates, np.zeros(n)),
        tga=(dates, np.zeros(n)),
    )
    df, _ = build_frame(fred, tga_path)
    assert len(df) == n
    # netliq_bn is the pure ramp: diff over exactly 65 / 130 ROWS
    assert df["netliq_d13w"].iloc[:D13W_ROWS].isna().all()
    assert np.allclose(df["netliq_d13w"].iloc[D13W_ROWS:], float(D13W_ROWS))
    assert df["netliq_d26w"].iloc[:D26W_ROWS].isna().all()
    assert np.allclose(df["netliq_d26w"].iloc[D26W_ROWS:], float(D26W_ROWS))
    # strictly rising level ⇒ expanding percentile pinned at 1.0
    assert (df["netliq_pctile_expanding"] == 1.0).all()


# ---------------------------------------------------------------------------
# (d) expanding percentile is PIT-pure
# ---------------------------------------------------------------------------


def test_expanding_percentile_pit_purity(tmp_path):
    rng = np.random.default_rng(7)
    n_full, n_past = 180, 120
    dates = pd.bdate_range("2024-01-01", periods=n_full)
    walcl_mn = 6_000_000.0 + np.cumsum(rng.normal(0, 20_000.0, n_full))
    rrp_bn = np.abs(rng.normal(200.0, 50.0, n_full))
    tga_mn = np.abs(rng.normal(700_000.0, 50_000.0, n_full))

    fred_a, tga_a = _setup(tmp_path / "past",
                           walcl=(dates[:n_past], walcl_mn[:n_past]),
                           rrp=(dates[:n_past], rrp_bn[:n_past]),
                           tga=(dates[:n_past], tga_mn[:n_past]))
    fred_b, tga_b = _setup(tmp_path / "full",
                           walcl=(dates, walcl_mn), rrp=(dates, rrp_bn), tga=(dates, tga_mn))
    past, _ = build_frame(fred_a, tga_a)
    full, _ = build_frame(fred_b, tga_b)

    merged = past.merge(full, on="date", suffixes=("_past", "_full"))
    assert len(merged) == n_past
    for col in ("netliq_bn", "netliq_d13w", "netliq_d26w", "netliq_pctile_expanding"):
        a, b = merged[f"{col}_past"], merged[f"{col}_full"]
        assert ((a == b) | (a.isna() & b.isna())).all(), (
            f"{col} changed at a past date when future rows were appended — PIT violation"
        )


# ---------------------------------------------------------------------------
# (e) stale-guard truncation
# ---------------------------------------------------------------------------


def test_stale_guard_truncates_at_slowest_component(tmp_path):
    n = 250
    dates = pd.bdate_range("2024-01-01", periods=n)
    tga_stop = 199                                               # TGA dies 50 bdays early
    walcl, rrp, _ = ((dates[::5], 7_000_000.0 + np.arange(50) * 1_000.0),
                     (dates, np.full(n, 100.0)), None)
    fred, tga_path = _setup(tmp_path, walcl=walcl, rrp=rrp,
                            tga=(dates[:tga_stop + 1], np.full(tga_stop + 1, 750_000.0)))
    df, meta = build_frame(fred, tga_path)

    cutoff = dates[tga_stop] + pd.offsets.BDay(STALE_GUARD_BDAYS)
    assert meta["stalest_component"] == "tga"
    assert meta["stale_guard_cutoff"] == str(cutoff.date())
    assert pd.Timestamp(df["date"].max()) == dates[tga_stop + STALE_GUARD_BDAYS]
    assert pd.Timestamp(df["date"].max()) < dates[-1], "stale-guard did not truncate"
    dropped = n - (tga_stop + STALE_GUARD_BDAYS + 1)
    assert meta["rows_dropped_by_stale_guard"] == dropped
    assert meta["component_last_obs"]["tga"] == str(dates[tga_stop].date())


# ---------------------------------------------------------------------------
# (f) determinism / idempotent full rebuild
# ---------------------------------------------------------------------------


def test_rebuild_is_deterministic(tmp_path):
    walcl, rrp, tga = _standard_components()
    fred, tga_path = _setup(tmp_path, walcl=walcl, rrp=rrp, tga=tga)
    df1, meta1 = build_frame(fred, tga_path)
    df2, meta2 = build_frame(fred, tga_path)
    pd.testing.assert_frame_equal(df1, df2)
    assert meta1 == meta2
