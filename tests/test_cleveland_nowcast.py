"""Unit tests for the Cleveland Fed inflation nowcast collector (MRI-PR-A).

No network access: parse fixtures are inline. Tests cover:
  - happy-path parse: correct rows, correct values, correct series names
  - fail-open: garbage payload returns {} without raising
  - upsert idempotency: running the same day twice does not duplicate rows
  - partial blank: charts with no non-empty values are silently skipped
  - Jan chart year rollover: Dec dates in a Jan chart get year-1
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.cleveland_nowcast import _parse_payload, _upsert_parquet  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _make_chart(subcaption: str, dates: list[str], series_data: dict[str, list]) -> dict:
    """Build a minimal chart object matching the Cleveland JSON structure.

    `dates` is a list of 'MM/DD' strings.
    `series_data` maps series_name -> list of value strings ('' for blank).
    """
    category = [{"label": d} for d in dates]
    dataset = []
    for sname, vals in series_data.items():
        dataset.append({
            "seriesname": sname,
            "data": [{"value": v} for v in vals],
        })
    return {
        "chart": {"subcaption": subcaption, "_comment": "2026-07-06 00:00"},
        "categories": [{"category": category}],
        "dataset": dataset,
    }


def _june_chart():
    """A simple 2026-06 chart with 2 dates and all 4 nowcast series populated."""
    return _make_chart(
        subcaption="2026-6",
        dates=["06/10", "06/11"],
        series_data={
            "CPI Inflation":      ["0.28", "0.31"],
            "Core CPI Inflation": ["0.22", "0.24"],
            "PCE Inflation":      ["0.14", "0.15"],
            "Core PCE Inflation": ["0.19", "0.20"],
            "Actual CPI Inflation":      ["", ""],   # post-release actuals: skip
            "Actual Core CPI Inflation": ["", ""],
            "Actual PCE Inflation":      ["", ""],
            "Actual Core PCE Inflation": ["", ""],
        },
    )


def _july_partial_chart():
    """2026-07 chart with only 1 date populated (early in the month)."""
    return _make_chart(
        subcaption="2026-7",
        dates=["07/01"],
        series_data={
            "CPI Inflation":      ["-0.21"],
            "Core CPI Inflation": ["0.23"],
            "PCE Inflation":      ["0.01"],
            "Core PCE Inflation": ["0.28"],
        },
    )


def _blank_chart():
    """A chart with all blank values (future month not yet nowcast)."""
    return _make_chart(
        subcaption="2026-8",
        dates=["08/01"],
        series_data={
            "CPI Inflation":      [""],
            "Core CPI Inflation": [""],
            "PCE Inflation":      [""],
            "Core PCE Inflation": [""],
        },
    )


def _jan_chart():
    """A Jan chart that may have Dec dates (year rollover check)."""
    return _make_chart(
        subcaption="2026-1",
        dates=["12/15", "01/02"],
        series_data={
            "CPI Inflation":      ["0.25", "0.26"],
            "Core CPI Inflation": ["0.20", "0.21"],
            "PCE Inflation":      ["0.12", "0.13"],
            "Core PCE Inflation": ["0.18", "0.19"],
        },
    )


def _vline_chart():
    """A chart with a vline event marker interspersed between date labels."""
    return {
        "chart": {"subcaption": "2026-6"},
        "categories": [{"category": [
            {"label": "06/10"},
            {"label": "CPI May", "vline": "true", "lineposition": "0"},
            {"label": "06/11"},
        ]}],
        "dataset": [{
            "seriesname": "CPI Inflation",
            "data": [
                {"value": "0.28"},
                {"value": ""},        # vline position — no data point for vline
                {"value": "0.31"},
            ],
        }],
    }


# ---------------------------------------------------------------------------
# Parse tests
# ---------------------------------------------------------------------------

def test_parse_happy_path_row_count():
    """Each date × series combination with a non-empty value yields one row."""
    payload = [_june_chart()]
    df = _parse_payload(payload, asof_date="2026-07-07")
    # 2 dates × 4 series = 8 rows
    assert len(df) == 8


def test_parse_correct_series_names():
    """Series names are mapped to their canonical column names."""
    payload = [_june_chart()]
    df = _parse_payload(payload, asof_date="2026-07-07")
    assert set(df["series"].unique()) == {"cpi_mom", "core_cpi_mom", "pce_mom", "core_pce_mom"}


def test_parse_correct_values():
    """Numeric values match the fixture strings."""
    payload = [_june_chart()]
    df = _parse_payload(payload, asof_date="2026-07-07")
    row = df[(df["series"] == "cpi_mom") & (df["obs_date"] == "2026-06-11")]
    assert len(row) == 1
    assert abs(row.iloc[0]["value"] - 0.31) < 1e-9


def test_parse_correct_target_period():
    """target_period is YYYY-MM-01 derived from the subcaption."""
    payload = [_june_chart()]
    df = _parse_payload(payload, asof_date="2026-07-07")
    assert (df["target_period"] == "2026-06-01").all()


def test_parse_asof_date_propagated():
    """first_seen_asof is written into every row from the argument."""
    payload = [_june_chart()]
    df = _parse_payload(payload, asof_date="2026-07-07")
    assert (df["first_seen_asof"] == "2026-07-07").all()


def test_parse_blank_chart_produces_no_rows():
    """A chart where all values are blank is silently skipped."""
    payload = [_blank_chart()]
    df = _parse_payload(payload, asof_date="2026-07-07")
    assert df.empty


def test_parse_multi_chart():
    """Multiple charts in one payload each yield their own rows."""
    payload = [_june_chart(), _july_partial_chart()]
    df = _parse_payload(payload, asof_date="2026-07-07")
    periods = set(df["target_period"].unique())
    assert "2026-06-01" in periods
    assert "2026-07-01" in periods


def test_parse_vline_skipped():
    """Vline markers (event labels like 'CPI May') are skipped; adjacent dates parsed."""
    payload = [_vline_chart()]
    df = _parse_payload(payload, asof_date="2026-07-07")
    # vline position has empty value anyway; positions 0 and 2 in cats are 06/10 and 06/11
    # data indices: data[0] -> cats[0]='06/10', data[2] -> cats[2]='06/11'
    obs_dates = set(df["obs_date"].unique())
    assert "2026-06-10" in obs_dates
    assert "2026-06-11" in obs_dates
    # no row for the vline label 'CPI May'
    assert not any("May" in s for s in df["obs_date"].tolist())


def test_parse_jan_chart_dec_dates_get_prior_year():
    """Dec dates in a Jan chart (subcaption 2026-1) receive year 2025."""
    payload = [_jan_chart()]
    df = _parse_payload(payload, asof_date="2026-01-05")
    obs_dates = set(df["obs_date"].unique())
    assert "2025-12-15" in obs_dates   # Dec dates in Jan chart -> year-1
    assert "2026-01-02" in obs_dates


def test_parse_garbage_payload_returns_empty():
    """A payload that isn't a list of chart objects yields an empty DataFrame."""
    # Not a list of dicts with expected keys
    df = _parse_payload([{"bogus": "data"}], asof_date="2026-07-07")
    assert df.empty


def test_parse_actual_series_excluded():
    """Actual * series (post-release actuals) are not included in the output."""
    chart = _make_chart(
        subcaption="2026-5",
        dates=["05/01"],
        series_data={
            "CPI Inflation": ["0.30"],
            "Actual CPI Inflation": ["0.32"],  # should be skipped
        },
    )
    df = _parse_payload([chart], asof_date="2026-07-07")
    assert "cpi_mom" in df["series"].values
    # Only 1 row (from CPI Inflation), not 2
    assert len(df) == 1


# ---------------------------------------------------------------------------
# Upsert / idempotency tests
# ---------------------------------------------------------------------------

def _make_rows(asof: str, target: str, series: str, obs: str, value: float) -> pd.DataFrame:
    return pd.DataFrame([{
        "first_seen_asof": asof,
        "target_period": target,
        "series": series,
        "obs_date": obs,
        "value": value,
    }])


def test_upsert_creates_file(tmp_path):
    """First upsert creates the parquet file."""
    path = tmp_path / "nowcast.parquet"
    rows = _make_rows("2026-07-07", "2026-07-01", "cpi_mom", "2026-07-06", 0.28)
    result = _upsert_parquet(path, rows)
    assert path.exists()
    assert len(result) == 1


def test_upsert_appends_new_obs(tmp_path):
    """A later collection with a NEW obs_date appends a row; re-served old
    obs_dates do not duplicate (first-seen key is (target, series, obs_date))."""
    path = tmp_path / "nowcast.parquet"
    rows1 = _make_rows("2026-07-06", "2026-07-01", "cpi_mom", "2026-07-05", 0.27)
    day2 = pd.concat([
        _make_rows("2026-07-07", "2026-07-01", "cpi_mom", "2026-07-05", 0.27),  # re-served
        _make_rows("2026-07-07", "2026-07-01", "cpi_mom", "2026-07-06", 0.28),  # new obs
    ], ignore_index=True)
    _upsert_parquet(path, rows1)
    result = _upsert_parquet(path, day2)
    assert len(result) == 2
    # the re-served obs keeps its original first_seen_asof
    old = result[result["obs_date"] == "2026-07-05"].iloc[0]
    assert old["first_seen_asof"] == "2026-07-06"


def test_upsert_idempotent_same_day(tmp_path):
    """Running the same collection twice does not duplicate rows."""
    path = tmp_path / "nowcast.parquet"
    rows = _make_rows("2026-07-07", "2026-07-01", "cpi_mom", "2026-07-06", 0.28)
    _upsert_parquet(path, rows)
    result = _upsert_parquet(path, rows)   # same data again
    assert len(result) == 1


def test_upsert_first_seen_wins(tmp_path):
    """If the same key re-arrives with a different value, the FIRST recorded
    value is kept — the store is a first-seen vintage record, never rewritten."""
    path = tmp_path / "nowcast.parquet"
    rows_old = _make_rows("2026-07-07", "2026-07-01", "cpi_mom", "2026-07-06", 0.28)
    rows_new = _make_rows("2026-07-08", "2026-07-01", "cpi_mom", "2026-07-06", 0.31)
    _upsert_parquet(path, rows_old)
    result = _upsert_parquet(path, rows_new)
    assert len(result) == 1
    assert abs(result.iloc[0]["value"] - 0.28) < 1e-9


def test_upsert_result_is_sorted(tmp_path):
    """Output is sorted by the key columns."""
    path = tmp_path / "nowcast.parquet"
    rows = pd.concat([
        _make_rows("2026-07-07", "2026-07-01", "pce_mom",     "2026-07-06", 0.12),
        _make_rows("2026-07-07", "2026-07-01", "cpi_mom",     "2026-07-06", 0.28),
        _make_rows("2026-07-06", "2026-07-01", "cpi_mom",     "2026-07-05", 0.27),
    ], ignore_index=True)
    result = _upsert_parquet(path, rows)
    key_cols = ["target_period", "series", "obs_date"]
    sorted_df = result.sort_values(key_cols).reset_index(drop=True)
    pd.testing.assert_frame_equal(result, sorted_df)


# ---------------------------------------------------------------------------
# Fail-open: collector.fetch() must not raise on garbage
# ---------------------------------------------------------------------------

def test_fetch_failopen_on_bad_json(monkeypatch):
    """fetch() returns {} and does not raise when the response is not valid JSON."""
    from collectors.cleveland_nowcast import ClevelandNowcastAdapter

    adapter = ClevelandNowcastAdapter()

    class _BadResp:
        text = "<html>error page</html>"

    monkeypatch.setattr(adapter, "http_get", lambda *a, **kw: _BadResp())
    result = adapter.fetch()
    assert result == {}


def test_fetch_failopen_on_connection_error(monkeypatch):
    """fetch() returns {} and does not raise on a network error."""
    from collectors.cleveland_nowcast import ClevelandNowcastAdapter
    import requests

    adapter = ClevelandNowcastAdapter()
    monkeypatch.setattr(adapter, "http_get",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            requests.exceptions.ConnectionError("timeout")))
    result = adapter.fetch()
    assert result == {}


def test_fetch_failopen_on_empty_list(monkeypatch):
    """fetch() returns {} when the JSON parses to an empty list."""
    from collectors.cleveland_nowcast import ClevelandNowcastAdapter

    adapter = ClevelandNowcastAdapter()

    class _EmptyResp:
        text = "[]"

    monkeypatch.setattr(adapter, "http_get", lambda *a, **kw: _EmptyResp())
    result = adapter.fetch()
    assert result == {}
