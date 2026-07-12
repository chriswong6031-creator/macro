"""tests/test_broad_etf_flows.py — hermetic unit tests for RLT-R3 broad ETF proxy.

Tests cover:
- _derive_flow_guarded: proxy math + SO-jump guard (>25% single-day SO change
  clamped to NaN, ≤25% passes through)
- _z60_causal: z-score uses only past data (no lookahead); min_periods=2
- broad_flows_wide: schema, missing-ticker robustness, guarded flow
- rebuild_broad: creates parquet, correct schema, upsert idempotency
- load_broad_proxy: reads written file
- Schema of broad_flow_proxy: columns [date, ticker, flow_mn, flow_z60]
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.etf_flows import (
    BROAD_ETFS,
    _SO_JUMP_GUARD_FRAC,
    _derive_flow_guarded,
    _z60_causal,
    broad_flows_wide,
    load_broad_proxy,
    rebuild_broad,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_so_file(tmp_dir: Path, ticker: str, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df.pop("date"))
    df.index.name = "date"
    df.to_parquet(tmp_dir / f"{ticker}.parquet")


def _flat_rows(n: int = 10, so_start: float = 100.0,
               so_delta: float = 1.0, nav: float = 400.0) -> list[dict]:
    """Synthetic SO rows: constant NAV, SO increases by so_delta each day."""
    base = pd.Timestamp("2026-06-02")
    rows = []
    for i in range(n):
        so = so_start + i * so_delta
        rows.append({
            "date": base + pd.Timedelta(days=i),
            "nav": nav,
            "aum_mn": so * nav,
            "so_mn": so,
        })
    return rows


# ── _derive_flow_guarded ──────────────────────────────────────────────────────


def test_guarded_first_row_nan():
    """First row must be NaN (no prior day to diff against)."""
    df = pd.DataFrame(
        {"nav": [400.0, 400.0], "so_mn": [100.0, 101.0]},
        index=pd.to_datetime(["2026-06-02", "2026-06-03"]),
    )
    result = _derive_flow_guarded(df)
    assert pd.isna(result.iloc[0])


def test_guarded_normal_creation():
    """delta_so=1.0 × nav=400 → flow=400 (no guard triggered)."""
    df = pd.DataFrame(
        {"nav": [400.0, 400.0], "so_mn": [100.0, 101.0]},
        index=pd.to_datetime(["2026-06-02", "2026-06-03"]),
    )
    result = _derive_flow_guarded(df)
    assert abs(result.iloc[1] - 400.0) < 1e-6, f"expected 400.0 got {result.iloc[1]}"


def test_guarded_outflow_negative():
    """Declining SO → negative flow."""
    df = pd.DataFrame(
        {"nav": [400.0, 400.0], "so_mn": [100.0, 99.0]},
        index=pd.to_datetime(["2026-06-02", "2026-06-03"]),
    )
    result = _derive_flow_guarded(df)
    assert result.iloc[1] < 0


def test_guarded_jump_above_threshold_clamped():
    """A >25% single-day SO jump must be clamped to NaN."""
    threshold_frac = _SO_JUMP_GUARD_FRAC  # 0.25
    # 100 → 130 is a 30% jump → above threshold → NaN
    so_after_jump = 100.0 * (1 + threshold_frac + 0.05)  # 130
    df = pd.DataFrame(
        {"nav": [400.0, 400.0], "so_mn": [100.0, so_after_jump]},
        index=pd.to_datetime(["2026-06-02", "2026-06-03"]),
    )
    result = _derive_flow_guarded(df)
    assert pd.isna(result.iloc[1]), (
        f"SO jump of {(so_after_jump/100 - 1)*100:.0f}% should be clamped to NaN"
    )


def test_guarded_jump_at_threshold_passes():
    """A jump exactly at the threshold (25%) passes through (guard is strict >)."""
    threshold_frac = _SO_JUMP_GUARD_FRAC  # 0.25
    # 100 → 125 is exactly 25% — should NOT be clamped (guard is > not >=)
    so_exactly_at = 100.0 * (1 + threshold_frac)  # 125.0
    df = pd.DataFrame(
        {"nav": [400.0, 400.0], "so_mn": [100.0, so_exactly_at]},
        index=pd.to_datetime(["2026-06-02", "2026-06-03"]),
    )
    result = _derive_flow_guarded(df)
    # Should not be NaN (at threshold, not above it)
    assert not pd.isna(result.iloc[1]), (
        f"SO jump of exactly {threshold_frac*100:.0f}% should NOT be clamped"
    )


def test_guarded_multi_row_only_jump_clamped():
    """Only the jump row is clamped; surrounding rows are unaffected."""
    # Rows: day0 (base), day1 (normal +1%), day2 (jump +50%), day3 (normal +1%)
    so = [100.0, 101.0, 151.5, 152.5]  # day2: 151.5/101 - 1 ≈ 50% jump
    dates = pd.date_range("2026-06-02", periods=4)
    df = pd.DataFrame({"nav": [400.0] * 4, "so_mn": so}, index=dates)
    result = _derive_flow_guarded(df)
    assert pd.isna(result.iloc[0]), "day0: NaN (no prior)"
    assert not pd.isna(result.iloc[1]), "day1: normal creation, should be finite"
    assert pd.isna(result.iloc[2]), "day2: jump >25%, should be NaN"
    assert not pd.isna(result.iloc[3]), "day3: normal after jump, should be finite"


# ── _z60_causal ──────────────────────────────────────────────────────────────


def test_z60_no_lookahead():
    """z60 on day t uses only data up to and including day t (causal)."""
    # Create 70 rows; z for row 65 must equal manually computed rolling z
    # using rows [5..65] (60-window ending at row 65) — verifies causality.
    n = 70
    s = pd.Series(np.random.default_rng(42).normal(0, 1, n),
                  index=pd.date_range("2026-01-02", periods=n))
    z = _z60_causal(s)
    # Manually compute z for index 64 (the 65th row, 0-indexed)
    i = 64
    window = s.iloc[i - 59: i + 1]  # 60 rows ending at i (inclusive)
    expected_z = (s.iloc[i] - window.mean()) / window.std(ddof=1)
    assert abs(z.iloc[i] - expected_z) < 1e-9, (
        f"z60 causality failed: got {z.iloc[i]:.6f}, expected {expected_z:.6f}"
    )


def test_z60_min_periods_2():
    """z60 is defined at index 1 (min_periods=2), NaN at index 0."""
    s = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2026-06-02", periods=3))
    z = _z60_causal(s)
    assert pd.isna(z.iloc[0]), "z60 at index 0 must be NaN (only 1 obs)"
    assert not pd.isna(z.iloc[1]), "z60 at index 1 should be defined (2 obs)"


def test_z60_flat_series_is_nan():
    """z60 is NaN when std=0 (flat flow series)."""
    s = pd.Series([5.0] * 10, index=pd.date_range("2026-06-02", periods=10))
    z = _z60_causal(s)
    # With a flat series std=0 → division by zero → NaN (guarded by replace(0, NA))
    assert all(pd.isna(v) or v == 0 for v in z)


# ── broad_flows_wide ──────────────────────────────────────────────────────────


def test_broad_flows_wide_returns_none_when_empty(tmp_path):
    result = broad_flows_wide(tickers=(), _flows_dir=tmp_path)
    assert result is None


def test_broad_flows_wide_returns_none_when_files_absent(tmp_path):
    result = broad_flows_wide(tickers=("SPY", "QQQ"), _flows_dir=tmp_path)
    assert result is None


def test_broad_flows_wide_schema(tmp_path):
    for t in ("SPY", "QQQ"):
        _make_so_file(tmp_path, t, _flat_rows(5))
    result = broad_flows_wide(tickers=("SPY", "QQQ"), _flows_dir=tmp_path)
    assert result is not None
    assert "SPY_flow_mn" in result.columns
    assert "QQQ_flow_mn" in result.columns
    assert result.index.name == "date"
    # First row NaN for each ticker (diff)
    assert result["SPY_flow_mn"].isna().sum() == 1
    assert result["QQQ_flow_mn"].isna().sum() == 1


def test_broad_flows_wide_partial_tickers_ok(tmp_path):
    """Missing ticker files do not block available tickers."""
    _make_so_file(tmp_path, "SPY", _flat_rows(4))
    # QQQ file absent
    result = broad_flows_wide(tickers=("SPY", "QQQ"), _flows_dir=tmp_path)
    assert result is not None
    assert "SPY_flow_mn" in result.columns
    assert "QQQ_flow_mn" not in result.columns


def test_broad_flows_wide_jump_guard_applied(tmp_path):
    """SO jump >25% on day-2 produces NaN flow on that day."""
    rows = [
        {"date": pd.Timestamp("2026-06-02"), "nav": 400.0, "aum_mn": 40000.0, "so_mn": 100.0},
        {"date": pd.Timestamp("2026-06-03"), "nav": 400.0, "aum_mn": 40400.0, "so_mn": 101.0},  # +1%
        {"date": pd.Timestamp("2026-06-04"), "nav": 400.0, "aum_mn": 60400.0, "so_mn": 151.0},  # +50%
        {"date": pd.Timestamp("2026-06-05"), "nav": 400.0, "aum_mn": 60800.0, "so_mn": 152.0},  # +1%
    ]
    _make_so_file(tmp_path, "SPY", rows)
    result = broad_flows_wide(tickers=("SPY",), _flows_dir=tmp_path)
    assert result is not None
    flows = result["SPY_flow_mn"]
    assert pd.isna(flows.iloc[2]), "50% SO jump must be NaN"
    assert not pd.isna(flows.iloc[1]), "1% SO delta must be finite"
    assert not pd.isna(flows.iloc[3]), "normal row after jump must be finite"


# ── rebuild_broad ─────────────────────────────────────────────────────────────


def test_rebuild_broad_creates_parquet(tmp_path):
    for t in ("SPY", "QQQ"):
        _make_so_file(tmp_path, t, _flat_rows(5))
    proxy_path = tmp_path / "broad_flow_proxy.parquet"
    out = rebuild_broad(tickers=("SPY", "QQQ"), flows_dir=tmp_path,
                        proxy_path=proxy_path)
    assert out is not None
    assert proxy_path.exists()


def test_rebuild_broad_schema(tmp_path):
    for t in ("SPY", "QQQ"):
        _make_so_file(tmp_path, t, _flat_rows(5))
    proxy_path = tmp_path / "broad_flow_proxy.parquet"
    rebuild_broad(tickers=("SPY", "QQQ"), flows_dir=tmp_path,
                  proxy_path=proxy_path)
    df = pd.read_parquet(proxy_path)
    # Required columns
    assert "date" in df.columns
    assert "ticker" in df.columns
    assert "flow_mn" in df.columns
    assert "flow_z60" in df.columns
    # date is datetime
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    # Both tickers present
    assert set(df["ticker"].unique()) == {"SPY", "QQQ"}
    # dtype contract: flow_mn and flow_z60 must be float64 (not object).
    # pd.NA injected via .replace(0, pd.NA) forces object dtype — guard against
    # regression (review blocking item #2, RLT-R3).
    assert df["flow_mn"].dtype == np.float64, (
        f"flow_mn dtype must be float64, got {df['flow_mn'].dtype}"
    )
    assert df["flow_z60"].dtype == np.float64, (
        f"flow_z60 dtype must be float64, got {df['flow_z60'].dtype}"
    )


def test_rebuild_broad_z60_is_causal(tmp_path):
    """flow_z60 must not be defined at row 0 (single obs) per ticker."""
    for t in ("SPY",):
        _make_so_file(tmp_path, t, _flat_rows(10))
    proxy_path = tmp_path / "broad_flow_proxy.parquet"
    rebuild_broad(tickers=("SPY",), flows_dir=tmp_path, proxy_path=proxy_path)
    df = pd.read_parquet(proxy_path)
    spy = df[df["ticker"] == "SPY"].sort_values("date").reset_index(drop=True)
    # Row 0 has flow_mn=NaN (diff), so flow_z60 must also be NaN
    assert pd.isna(spy["flow_z60"].iloc[0]), (
        "z60 at first row must be NaN (flow_mn is NaN there)"
    )


def test_rebuild_broad_returns_none_when_no_data(tmp_path):
    proxy_path = tmp_path / "broad_flow_proxy.parquet"
    out = rebuild_broad(tickers=(), flows_dir=tmp_path, proxy_path=proxy_path)
    assert out is None


def test_rebuild_broad_idempotent(tmp_path):
    """Two consecutive rebuild_broad calls must not duplicate rows."""
    for t in ("SPY",):
        _make_so_file(tmp_path, t, _flat_rows(4))
    proxy_path = tmp_path / "broad_flow_proxy.parquet"
    rebuild_broad(tickers=("SPY",), flows_dir=tmp_path, proxy_path=proxy_path)
    rebuild_broad(tickers=("SPY",), flows_dir=tmp_path, proxy_path=proxy_path)
    df = pd.read_parquet(proxy_path)
    spy = df[df["ticker"] == "SPY"]
    assert len(spy) == 4, f"idempotent rebuild must not duplicate rows; got {len(spy)}"


def test_rebuild_broad_upsert_new_ticker(tmp_path):
    """Adding a second ticker in a subsequent rebuild preserves existing rows."""
    _make_so_file(tmp_path, "SPY", _flat_rows(3))
    proxy_path = tmp_path / "broad_flow_proxy.parquet"
    rebuild_broad(tickers=("SPY",), flows_dir=tmp_path, proxy_path=proxy_path)

    # Second run adds QQQ
    _make_so_file(tmp_path, "QQQ", _flat_rows(3))
    rebuild_broad(tickers=("SPY", "QQQ"), flows_dir=tmp_path, proxy_path=proxy_path)

    df = pd.read_parquet(proxy_path)
    assert set(df["ticker"].unique()) >= {"SPY", "QQQ"}
    spy_rows = df[df["ticker"] == "SPY"]
    assert len(spy_rows) == 3, f"SPY rows should be preserved; got {len(spy_rows)}"


def test_rebuild_broad_no_phantom_rows_disjoint_histories(tmp_path):
    """Disjoint ticker histories must not emit phantom NaN rows for each other.

    Regression test for the outer-join phantom-NaN issue (review blocking #1,
    RLT-R3): SPY with data on 06-02..06-04 and QQQ with data on 06-10..06-12
    must NOT produce phantom SPY rows on QQQ dates or vice versa.
    """
    spy_rows = [
        {"date": pd.Timestamp("2026-06-02"), "nav": 400.0, "aum_mn": 40000.0, "so_mn": 100.0},
        {"date": pd.Timestamp("2026-06-03"), "nav": 400.0, "aum_mn": 40400.0, "so_mn": 101.0},
        {"date": pd.Timestamp("2026-06-04"), "nav": 400.0, "aum_mn": 40800.0, "so_mn": 102.0},
    ]
    qqq_rows = [
        {"date": pd.Timestamp("2026-06-10"), "nav": 470.0, "aum_mn": 47000.0, "so_mn": 100.0},
        {"date": pd.Timestamp("2026-06-11"), "nav": 470.0, "aum_mn": 47470.0, "so_mn": 101.0},
        {"date": pd.Timestamp("2026-06-12"), "nav": 470.0, "aum_mn": 47940.0, "so_mn": 102.0},
    ]
    _make_so_file(tmp_path, "SPY", spy_rows)
    _make_so_file(tmp_path, "QQQ", qqq_rows)
    proxy_path = tmp_path / "broad_flow_proxy.parquet"
    rebuild_broad(tickers=("SPY", "QQQ"), flows_dir=tmp_path, proxy_path=proxy_path)

    df = pd.read_parquet(proxy_path)
    spy_df = df[df["ticker"] == "SPY"]
    qqq_df = df[df["ticker"] == "QQQ"]

    # SPY must have exactly 3 rows (its own dates only, not QQQ's dates)
    assert len(spy_df) == 3, (
        f"SPY must have 3 rows (no phantom rows from QQQ dates); got {len(spy_df)}"
    )
    # QQQ must have exactly 3 rows (its own dates only, not SPY's dates)
    assert len(qqq_df) == 3, (
        f"QQQ must have 3 rows (no phantom rows from SPY dates); got {len(qqq_df)}"
    )
    # SPY dates must only be within its own history
    spy_dates = set(spy_df["date"].dt.date.astype(str))
    assert spy_dates <= {"2026-06-02", "2026-06-03", "2026-06-04"}, (
        f"SPY has dates outside its history: {spy_dates}"
    )


# ── load_broad_proxy ──────────────────────────────────────────────────────────


def test_load_broad_proxy_none_when_absent(tmp_path):
    result = load_broad_proxy(proxy_path=tmp_path / "missing.parquet")
    assert result is None


def test_load_broad_proxy_reads_written_file(tmp_path):
    for t in ("SPY",):
        _make_so_file(tmp_path, t, _flat_rows(4))
    proxy_path = tmp_path / "broad_flow_proxy.parquet"
    rebuild_broad(tickers=("SPY",), flows_dir=tmp_path, proxy_path=proxy_path)
    df = load_broad_proxy(proxy_path=proxy_path)
    assert df is not None
    assert "ticker" in df.columns


# ── BROAD_ETFS constant ────────────────────────────────────────────────────────


def test_broad_etfs_constant_contains_expected_tickers():
    """BROAD_ETFS must contain the 5 tickers specified in RLT-R3."""
    expected = {"SPY", "QQQ", "IWM", "RSP", "DIA"}
    assert expected == set(BROAD_ETFS), f"BROAD_ETFS={BROAD_ETFS}"


# ── z60 sign sanity ────────────────────────────────────────────────────────────


def test_rebuild_broad_z60_positive_for_large_inflow(tmp_path):
    """A very large inflow on the last day should produce a positive z60."""
    # 59 rows with flow ~1 unit, then final row with flow ~100 units
    so = [100.0 + i * 0.01 for i in range(59)]  # slow accrual (flow ≈ 4/day)
    so.append(so[-1] + 25.0)                     # big jump on day 59 (flow ≈ 10000)
    dates = pd.date_range("2026-01-02", periods=len(so))
    rows = [{"date": d, "nav": 400.0, "aum_mn": s * 400, "so_mn": s}
            for d, s in zip(dates, so)]
    _make_so_file(tmp_path, "SPY", rows)
    proxy_path = tmp_path / "broad_flow_proxy.parquet"
    rebuild_broad(tickers=("SPY",), flows_dir=tmp_path, proxy_path=proxy_path)
    df = pd.read_parquet(proxy_path)
    spy = df[df["ticker"] == "SPY"].sort_values("date").reset_index(drop=True)
    last_z = spy["flow_z60"].iloc[-1]
    assert last_z > 1.0, f"large inflow should produce z60 > 1.0; got {last_z:.3f}"
