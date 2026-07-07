"""Unit tests for TSA throughput HTML parser and display field logic.

No network calls; all tests operate on saved fixtures or in-memory data.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from collectors.tsa_throughput import (
    compute_display_fields,
    parse_tsa_html,
    us_federal_holidays,
    _is_us_federal_holiday,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURE_HTML = FIXTURE_DIR / "tsa_sample.html"


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

def test_parse_fixture_row_count():
    """Parser extracts correct number of data rows from fixture."""
    html = FIXTURE_HTML.read_text()
    df = parse_tsa_html(html)
    assert len(df) == 8, f"Expected 8 rows, got {len(df)}"


def test_parse_fixture_columns():
    html = FIXTURE_HTML.read_text()
    df = parse_tsa_html(html)
    assert "passengers" in df.columns
    # pandas 2.x uses datetime64[s]; check kind not exact unit
    assert df.index.dtype.kind == "M", f"Expected datetime index, got {df.index.dtype}"


def test_parse_fixture_values():
    """Check a specific known value from fixture."""
    html = FIXTURE_HTML.read_text()
    df = parse_tsa_html(html)
    jan5 = df.loc["2026-01-05", "passengers"]
    assert jan5 == 2_512_000, f"Expected 2512000, got {jan5}"


def test_parse_skips_header_row():
    """Header row 'Date / Numbers' must not appear as a data row."""
    html = FIXTURE_HTML.read_text()
    df = parse_tsa_html(html)
    # No row should have passengers == 0 or NaN from parsing 'Numbers' as int
    assert df["passengers"].notna().all()
    assert (df["passengers"] > 0).all()


def test_parse_handles_blank_numbers_cell():
    """Rows with blank or non-numeric numbers cells are dropped (amendment A1)."""
    html = """<table>
    <tr><td>Date</td><td>Numbers</td></tr>
    <tr><td>3/1/2026</td><td>1,500,000</td></tr>
    <tr><td>3/2/2026</td><td></td></tr>
    <tr><td>3/3/2026</td><td>TBD</td></tr>
    </table>"""
    df = parse_tsa_html(html)
    assert len(df) == 1
    assert df.iloc[0]["passengers"] == 1_500_000


def test_parse_deduplicates():
    """Duplicate date rows: last value wins."""
    html = """<table>
    <tr><td>Date</td><td>Numbers</td></tr>
    <tr><td>6/1/2026</td><td>1,000,000</td></tr>
    <tr><td>6/1/2026</td><td>2,000,000</td></tr>
    </table>"""
    df = parse_tsa_html(html)
    assert len(df) == 1
    assert df.iloc[0]["passengers"] == 2_000_000


def test_parse_empty_html_raises():
    with pytest.raises(ValueError, match="No parseable rows"):
        parse_tsa_html("<html><body>No table here</body></html>")


def test_parse_sorted_ascending():
    """Output is sorted ascending by date regardless of input order."""
    html = FIXTURE_HTML.read_text()
    df = parse_tsa_html(html)
    assert df.index.is_monotonic_increasing


# ---------------------------------------------------------------------------
# Display field tests
# ---------------------------------------------------------------------------

def _make_series(start: str, n: int, base: int = 2_000_000) -> pd.DataFrame:
    """Helper: n days of constant passenger counts from start date."""
    idx = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({"passengers": [base] * n}, index=idx)


def test_avg7d_after_7_days():
    """After 7 full days, avg7d should equal passengers (constant series)."""
    df = _make_series("2026-01-01", 14)
    out = compute_display_fields(df)
    assert abs(out["avg7d"].iloc[-1] - 2_000_000) < 1


def test_avg7d_first_row_min_periods():
    """avg7d on the first row uses min_periods=1 (no NaN)."""
    df = _make_series("2026-01-01", 3)
    out = compute_display_fields(df)
    assert out["avg7d"].notna().all()


def test_yoy_pct_no_prior_year_is_nan():
    """Rows in first covered year have no YoY reference -> NaN."""
    df = _make_series("2019-01-01", 10)
    out = compute_display_fields(df)
    assert out["yoy_pct"].isna().all()


def test_yoy_pct_flat_series_is_zero():
    """Constant daily counts -> YoY % should be 0.0."""
    df = pd.concat([
        _make_series("2019-06-01", 30, base=1_500_000),
        _make_series("2020-06-01", 30, base=1_500_000),
    ])
    out = compute_display_fields(df)
    jun2020 = out.loc["2020-06-01":"2020-06-30", "yoy_pct"].dropna()
    assert len(jun2020) > 0
    assert (jun2020.abs() < 0.01).all(), f"Expected ~0 YoY, got: {jun2020.values}"


def test_vs2019_pct_no_2019_data_is_nan():
    """Without 2019 data, vs2019_pct should be NaN."""
    df = _make_series("2022-01-01", 10)
    out = compute_display_fields(df)
    assert out["vs2019_pct"].isna().all()


def test_vs2019_pct_flat_returns_zero():
    """Same count in 2019 and 2023 -> vs2019 should be 0."""
    df = pd.concat([
        _make_series("2019-03-01", 30, base=2_000_000),
        _make_series("2023-03-01", 30, base=2_000_000),
    ])
    out = compute_display_fields(df)
    mar2023 = out.loc["2023-03-01":"2023-03-30", "vs2019_pct"].dropna()
    assert len(mar2023) > 0
    # Weekday match may not always find exact 0; allow small residual (weekday drift)
    assert (mar2023.abs() < 0.5).all(), f"Expected ~0 vs2019, got max={mar2023.abs().max():.2f}"


def test_output_columns_present():
    df = _make_series("2019-01-01", 5)
    out = compute_display_fields(df)
    for col in ("passengers", "avg7d", "yoy_pct", "vs2019_pct"):
        assert col in out.columns, f"Missing column: {col}"


# ---------------------------------------------------------------------------
# Holiday exclusion tests (Amendment A3)
# ---------------------------------------------------------------------------

def test_us_federal_holidays_independence_day_2019():
    """Independence Day (Jul 4) must be in the 2019 federal holiday set."""
    from datetime import date
    holidays = us_federal_holidays(2019)
    assert date(2019, 7, 4) in holidays, "Independence Day 2019 not in holiday set"


def test_us_federal_holidays_observed_saturday():
    """When Jul 4 falls on Saturday, observed Friday must also be in the set."""
    from datetime import date
    # 2026: Jul 4 is Saturday -> observed Jul 3
    holidays = us_federal_holidays(2026)
    assert date(2026, 7, 3) in holidays, "Observed Jul 4 (Fri Jul 3 2026) not in holiday set"
    assert date(2026, 7, 4) in holidays, "Jul 4 2026 not in holiday set"


def test_vs2019_pct_holiday_target_returns_nan():
    """A target date that is a US federal holiday should return NaN vs2019_pct.

    Concrete case: 2026-07-04 (Independence Day) should be NaN because
    holiday counts are anomalously low and the comparison is not meaningful.
    """
    # Build a 2019 baseline and a July 2026 window that includes Jul 4
    base_2019 = pd.DataFrame(
        {"passengers": 2_200_000},
        index=pd.date_range("2019-06-25", "2019-07-10", freq="D"),
    )
    target_2026 = pd.DataFrame(
        {"passengers": 1_900_000},
        index=pd.date_range("2026-06-25", "2026-07-10", freq="D"),
    )
    df = pd.concat([base_2019, target_2026])
    out = compute_display_fields(df)
    # Jul 4 2026 is a federal holiday -> should be NaN
    assert pd.isna(out.loc["2026-07-04", "vs2019_pct"]), (
        f"Expected NaN for Jul 4 2026 (holiday), got {out.loc['2026-07-04', 'vs2019_pct']}"
    )


def test_vs2019_pct_excludes_holiday_candidate_in_2019():
    """The ±3-day candidate search must skip 2019 federal holidays.

    Concrete case: 2026-07-02 (Thursday) should NOT match 2019-07-04 (Thursday,
    Independence Day). After holiday exclusion, the function falls back to a
    non-holiday 2019 date rather than producing the spurious +39% artifact.
    """
    # Build a 2019 baseline: normal range around Jul 4
    # Set Jul 4 2019 anomalously low (holiday) and adjacent days at ~2.3M
    idx_2019 = pd.date_range("2019-06-25", "2019-07-10", freq="D")
    passengers_2019 = [2_300_000] * len(idx_2019)
    # Make Jul 4 (index position for 2019-07-04) anomalously low
    jul4_pos = list(idx_2019).index(pd.Timestamp("2019-07-04"))
    passengers_2019[jul4_pos] = 800_000  # anomalously low holiday count

    base_2019 = pd.DataFrame({"passengers": passengers_2019}, index=idx_2019)

    # Target: 2026-07-02 (Thursday) at a normal travel level
    target_2026 = pd.DataFrame(
        {"passengers": [2_900_000]},
        index=pd.DatetimeIndex(["2026-07-02"]),
    )
    df = pd.concat([base_2019, target_2026])
    out = compute_display_fields(df)

    vs2019_val = out.loc["2026-07-02", "vs2019_pct"]
    # With holiday exclusion, the match should NOT use the 800K holiday count.
    # The ratio 2900000/800000 - 1 = +262%, clearly wrong.
    # After exclusion, we should get a much more modest value vs a ~2.3M baseline.
    assert not pd.isna(vs2019_val), "Expected a non-NaN value for 2026-07-02"
    assert vs2019_val < 100, (
        f"vs2019_pct={vs2019_val:.1f}% looks like holiday-contaminated ratio "
        f"(expected < 100% after excluding the Jul 4 2019 holiday candidate)"
    )


def test_is_us_federal_holiday_non_holiday():
    """A regular weekday is not a federal holiday."""
    # 2019-07-02 is a Tuesday, not a holiday
    assert not _is_us_federal_holiday(pd.Timestamp("2019-07-02")), (
        "2019-07-02 should not be a federal holiday"
    )
