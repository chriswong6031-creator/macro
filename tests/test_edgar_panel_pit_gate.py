"""Tests for PIT gate in collectors/edgar.py _join_statements_fields().

Blocker from PR #1633 review: the original join inherited the panel's calendar-year
period_end proxy as the asof_date for joined capex, causing look-ahead for non-Dec-FYE
filers and FY-mismatch cases.  The fix reads statements.period_end and gates each joined
value on:
    statements.period_end + reporting_lag_days <= panel.asof_date

These tests verify:
  1. Values whose stmt period_end + lag > panel asof_date are NaN-ed (look-ahead gate).
  2. Values whose stmt period_end + lag <= panel asof_date are retained.
  3. Rows where statements has no period_end (NaT) are accepted without gating.
  4. The panel's own period_end and asof_date columns are not mutated by the join.
  5. After the gate, no joined capex row violates PIT (stmt asof > panel asof).
  6. PPL-like extreme case: stmt period_end 3 years after panel period_end.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.edgar as edgar  # noqa: E402
from lib import config as lib_config  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_panel(*rows) -> pd.DataFrame:
    """Build a minimal panel DataFrame from (ticker, fy, period_end, asof_date) tuples."""
    records = [
        {
            "ticker": ticker,
            "fy": fy,
            "period_end": pd.Timestamp(period_end),
            "asof_date": pd.Timestamp(asof_date),
            "assets": 1000.0,
        }
        for ticker, fy, period_end, asof_date in rows
    ]
    return pd.DataFrame(records)


def _run_join(tmp_path: Path, panel: pd.DataFrame, stmt_rows, lag: int = 120) -> pd.DataFrame:
    """Write mock statements.parquet, patch lib.config.data_dir, run _join_statements_fields.

    stmt_rows: list of (ticker, fy, period_end_str_or_None, capex_float)
    """
    edgar_dir = tmp_path / "edgar"
    edgar_dir.mkdir(parents=True, exist_ok=True)

    records = [
        {
            "ticker": ticker,
            "fy": fy,
            "period_end": pd.NaT if period_end is None else pd.Timestamp(period_end),
            "capex": float(capex),
        }
        for ticker, fy, period_end, capex in stmt_rows
    ]
    pd.DataFrame(records).to_parquet(edgar_dir / "statements.parquet")

    original_data_dir = lib_config.data_dir

    def _fake():
        return tmp_path

    lib_config.data_dir = _fake
    try:
        return edgar._join_statements_fields(panel.copy(), ["capex"], reporting_lag_days=lag)
    finally:
        lib_config.data_dir = original_data_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_lookahead_row_is_nulled(tmp_path):
    """Non-Dec-FYE: stmt period_end is 1 year after panel period_end → NaN."""
    # Panel proxy: Dec 2021 FYE → asof 2022-04-30
    # Statements true FYE: 2022-12-31 → stmt_asof 2023-04-30 > panel_asof → gate
    panel = _make_panel(("A", 2021, "2021-12-31", "2022-04-30"))
    result = _run_join(tmp_path, panel, [
        ("A", 2021, "2022-12-31", 500_000.0),
    ])
    val = result.loc[0, "capex"]
    assert val != val, f"Expected NaN for look-ahead row, got {val}"


def test_valid_pit_row_retained(tmp_path):
    """Stmt period_end + lag <= panel asof → value is kept."""
    # AAPL fy2022: true period_end=2022-09-24, stmt_asof=2023-01-22 <= panel_asof=2023-01-22
    panel = _make_panel(("AAPL", 2022, "2022-09-24", "2023-01-22"))
    result = _run_join(tmp_path, panel, [
        ("AAPL", 2022, "2022-09-24", 10_708_000_000.0),
    ])
    assert result.loc[0, "capex"] == pytest.approx(10_708_000_000.0)


def test_missing_period_end_accepted(tmp_path):
    """Rows without period_end in statements skip the PIT gate and are accepted."""
    panel = _make_panel(("FOX", 2022, "2022-06-30", "2022-10-28"))
    result = _run_join(tmp_path, panel, [
        ("FOX", 2022, None, 307_000_000.0),  # period_end=None → no gate
    ])
    assert result.loc[0, "capex"] == pytest.approx(307_000_000.0)


def test_panel_period_end_not_mutated(tmp_path):
    """The join must not overwrite the panel's period_end or asof_date."""
    panel = _make_panel(
        ("A", 2021, "2021-10-31", "2022-02-28"),
        ("A", 2022, "2022-10-31", "2023-02-28"),
    )
    original_pe = panel["period_end"].copy()
    original_asof = panel["asof_date"].copy()

    result = _run_join(tmp_path, panel, [
        ("A", 2021, "2021-10-31", 119_000_000.0),
        ("A", 2022, "2022-10-31", 188_000_000.0),
    ])
    pd.testing.assert_series_equal(
        result["period_end"].reset_index(drop=True),
        original_pe.reset_index(drop=True),
        check_names=False,
    )
    pd.testing.assert_series_equal(
        result["asof_date"].reset_index(drop=True),
        original_asof.reset_index(drop=True),
        check_names=False,
    )


def test_no_temp_columns_in_output(tmp_path):
    """The _stmt_asof and period_end_stmt helper columns must not leak into the output."""
    panel = _make_panel(("DEC", 2020, "2020-12-31", "2021-04-30"))
    result = _run_join(tmp_path, panel, [
        ("DEC", 2020, "2020-12-31", 80_000_000.0),
    ])
    assert "_stmt_asof" not in result.columns
    assert "period_end_stmt" not in result.columns


def test_dec_fye_rows_pass_gate(tmp_path):
    """Standard Dec-FYE rows where stmt period_end equals panel period_end pass the gate."""
    panel = _make_panel(
        ("DEC", 2020, "2020-12-31", "2021-04-30"),
        ("DEC", 2021, "2021-12-31", "2022-04-30"),
    )
    result = _run_join(tmp_path, panel, [
        ("DEC", 2020, "2020-12-31", 80_000_000.0),
        ("DEC", 2021, "2021-12-31", 90_000_000.0),
    ])
    assert result["capex"].notna().all()
    assert result.loc[0, "capex"] == pytest.approx(80_000_000.0)
    assert result.loc[1, "capex"] == pytest.approx(90_000_000.0)


def test_mixed_dec_and_nondec(tmp_path):
    """Non-Dec FYE rows are gated; Dec FYE rows in the same call pass through."""
    panel = _make_panel(
        ("NONDEC", 2020, "2020-12-31", "2021-04-30"),
        ("NONDEC", 2021, "2021-12-31", "2022-04-30"),
        ("DEC",    2020, "2020-12-31", "2021-04-30"),
        ("DEC",    2021, "2021-12-31", "2022-04-30"),
    )
    result = _run_join(tmp_path, panel, [
        ("NONDEC", 2020, "2021-06-30", 50_000_000.0),   # stmt_asof 2021-10-27 > 2021-04-30 → gate
        ("NONDEC", 2021, "2022-06-30", 60_000_000.0),   # stmt_asof 2022-10-27 > 2022-04-30 → gate
        ("DEC",    2020, "2020-12-31", 80_000_000.0),   # valid
        ("DEC",    2021, "2021-12-31", 90_000_000.0),   # valid
    ])

    nondec = result[result["ticker"] == "NONDEC"]
    dec    = result[result["ticker"] == "DEC"]

    assert nondec["capex"].isna().all(), (
        f"NONDEC capex should be NaN but got: {nondec['capex'].tolist()}"
    )
    assert dec["capex"].notna().all(), (
        f"DEC capex should be present but got: {dec['capex'].tolist()}"
    )


def test_extreme_lookahead_nulled(tmp_path):
    """PPL-like case: stmt period_end is 3 years after panel period_end (max 1096d)."""
    # PPL fy2021: panel period_end=2021-12-31 (Dec proxy), stmt period_end=2024-12-31
    panel = _make_panel(("PPL", 2021, "2021-12-31", "2022-04-30"))
    result = _run_join(tmp_path, panel, [
        ("PPL", 2021, "2024-12-31", 500_000_000.0),  # 3 years look-ahead
    ])
    val = result.loc[0, "capex"]
    assert val != val, f"Expected NaN for PPL extreme look-ahead, got {val}"


def test_no_match_gives_nan(tmp_path):
    """If no statement entry exists for (ticker, fy), capex is NaN."""
    panel = _make_panel(("MISSING", 2021, "2021-12-31", "2022-04-30"))
    result = _run_join(tmp_path, panel, [])  # empty statements
    assert result.loc[0, "capex"] != result.loc[0, "capex"]  # NaN


def test_lag_boundary_exact(tmp_path):
    """Exact boundary: stmt_asof == panel_asof → value should be KEPT (<=, not <)."""
    # panel asof = 2022-04-30; stmt period_end = 2022-01-01; lag=120 → stmt_asof = 2022-05-01
    # 2022-05-01 > 2022-04-30 → gate (look-ahead by 1 day)
    panel = _make_panel(("BNDRY", 2021, "2021-12-31", "2022-04-30"))
    result_late = _run_join(tmp_path, panel, [
        ("BNDRY", 2021, "2022-01-01", 10.0),  # stmt_asof = 2022-05-01 > panel_asof = gate
    ])
    assert result_late.loc[0, "capex"] != result_late.loc[0, "capex"]  # NaN

    # Exact match: stmt period_end + 120 = 2022-04-30 → 2021-12-31 is 120 days before
    # Actually 2021-12-31 + 120d = 2022-04-30 (exact) → should be kept
    panel2 = _make_panel(("BNDRY2", 2021, "2021-12-31", "2022-04-30"))
    result_exact = _run_join(tmp_path, panel2, [
        ("BNDRY2", 2021, "2021-12-31", 20.0),  # stmt_asof = 2022-04-30 = panel_asof → ok
    ])
    assert result_exact.loc[0, "capex"] == pytest.approx(20.0)
