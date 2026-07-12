"""tests/test_imf_weo.py — Hermetic unit tests for collectors/imf_weo.py (IRD-W1).

All tests use canned JSON fixtures and monkeypatched HTTP — zero network calls.

Coverage:
  1. parse_single_indicator   — fetch_indicator() parses the canonical API shape
  2. missing_country_skipped  — country absent from response is silently skipped
  3. null_values_skipped       — null year-values are excluded from Series
  4. bad_http_returns_empty    — non-200 responses → empty dict (fail-open)
  5. adapter_stores_parquets   — ImfWeoAdapter.fetch() calls store.upsert per (indicator, iso3)
  6. adapter_returns_summary   — fetch() return value contains 'imf_weo_runs' key
  7. all_fail_raises           — fetch() raises when all indicators return no data
  8. disabled_raises           — fetch() raises when imf_weo.enabled=False in config
  9. date_index_dec31          — index timestamps are Dec-31 of each year
  10. alias_column_name         — output Series column = alias from config, not raw indicator id
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.imf_weo import ImfWeoAdapter, fetch_indicator  # noqa: E402

# ---------------------------------------------------------------------------
# Canned JSON fixtures
# ---------------------------------------------------------------------------

_INDICATOR = "GGXWDG_NGDP"
_BASE_URL = "https://www.imf.org/external/datamapper/api/v1"

_CANONICAL_RESPONSE = {
    "values": {
        _INDICATOR: {
            "USA": {"2022": 121.4, "2023": 122.1, "2024": 123.5},
            "DEU": {"2022": 66.0, "2023": 63.5, "2024": 62.0},
        }
    }
}

_RESPONSE_WITH_NULLS = {
    "values": {
        _INDICATOR: {
            "USA": {"2022": None, "2023": "", "2024": "null", "2025": 124.0},
        }
    }
}

_EMPTY_RESPONSE = {"values": {_INDICATOR: {}}}


def _mock_response(json_body: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    return resp


# ---------------------------------------------------------------------------
# 1. parse_single_indicator
# ---------------------------------------------------------------------------

class TestParseCanonical:
    def test_two_countries_returned(self):
        with patch("requests.get", return_value=_mock_response(_CANONICAL_RESPONSE)):
            result = fetch_indicator(_BASE_URL, _INDICATOR, ["USA", "DEU"])
        assert set(result.keys()) == {"USA", "DEU"}

    def test_usa_series_length(self):
        with patch("requests.get", return_value=_mock_response(_CANONICAL_RESPONSE)):
            result = fetch_indicator(_BASE_URL, _INDICATOR, ["USA", "DEU"])
        assert len(result["USA"]) == 3

    def test_usa_values(self):
        with patch("requests.get", return_value=_mock_response(_CANONICAL_RESPONSE)):
            result = fetch_indicator(_BASE_URL, _INDICATOR, ["USA", "DEU"])
        assert result["USA"].iloc[0] == pytest.approx(121.4)
        assert result["USA"].iloc[1] == pytest.approx(122.1)
        assert result["USA"].iloc[2] == pytest.approx(123.5)


# ---------------------------------------------------------------------------
# 2. missing_country_skipped
# ---------------------------------------------------------------------------

class TestMissingCountrySkipped:
    def test_country_not_in_response_excluded(self):
        with patch("requests.get", return_value=_mock_response(_CANONICAL_RESPONSE)):
            result = fetch_indicator(_BASE_URL, _INDICATOR, ["USA", "BRA"])
        assert "BRA" not in result
        assert "USA" in result


# ---------------------------------------------------------------------------
# 3. null_values_skipped
# ---------------------------------------------------------------------------

class TestNullValuesSkipped:
    def test_null_years_excluded(self):
        with patch("requests.get", return_value=_mock_response(_RESPONSE_WITH_NULLS)):
            result = fetch_indicator(_BASE_URL, _INDICATOR, ["USA"])
        # Only 2025 has a real value
        assert len(result["USA"]) == 1
        assert result["USA"].iloc[0] == pytest.approx(124.0)


# ---------------------------------------------------------------------------
# 4. bad_http_returns_empty
# ---------------------------------------------------------------------------

class TestBadHttpReturnsEmpty:
    def test_non_200_returns_empty_dict(self):
        with patch("requests.get", return_value=_mock_response({}, status_code=429)):
            result = fetch_indicator(_BASE_URL, _INDICATOR, ["USA"], retries=1)
        assert result == {}

    def test_network_exception_returns_empty(self):
        with patch("requests.get", side_effect=ConnectionError("timeout")):
            result = fetch_indicator(_BASE_URL, _INDICATOR, ["USA"], retries=1)
        assert result == {}


# ---------------------------------------------------------------------------
# 5. adapter_stores_parquets (store.upsert mock)
# ---------------------------------------------------------------------------

_MINIMAL_CONFIG = {
    "imf_weo": {
        "enabled": True,
        "base_url": _BASE_URL,
        "retries": 1,
        "timeout": 5,
        "indicators": {_INDICATOR: "gross_debt_pct_gdp"},
        "countries": ["USA", "DEU"],
    }
}


class TestAdapterStoresParquets:
    def test_upsert_called_per_indicator_country(self):
        with (
            patch("collectors.imf_weo.config.load", return_value=_MINIMAL_CONFIG),
            patch("requests.get", return_value=_mock_response(_CANONICAL_RESPONSE)),
            patch("collectors.imf_weo.store.upsert") as mock_upsert,
        ):
            adapter = ImfWeoAdapter()
            adapter.fetch()

        # Two countries × one indicator = 2 calls
        assert mock_upsert.call_count == 2
        keys_called = {call.args[1] for call in mock_upsert.call_args_list}
        assert f"{_INDICATOR}_USA" in keys_called
        assert f"{_INDICATOR}_DEU" in keys_called

    def test_upsert_group_is_imf_weo(self):
        with (
            patch("collectors.imf_weo.config.load", return_value=_MINIMAL_CONFIG),
            patch("requests.get", return_value=_mock_response(_CANONICAL_RESPONSE)),
            patch("collectors.imf_weo.store.upsert") as mock_upsert,
        ):
            adapter = ImfWeoAdapter()
            adapter.fetch()

        for call in mock_upsert.call_args_list:
            assert call.args[0] == "imf_weo"


# ---------------------------------------------------------------------------
# 6. adapter_returns_summary
# ---------------------------------------------------------------------------

class TestAdapterReturnsSummary:
    def test_return_has_imf_weo_runs_key(self):
        with (
            patch("collectors.imf_weo.config.load", return_value=_MINIMAL_CONFIG),
            patch("requests.get", return_value=_mock_response(_CANONICAL_RESPONSE)),
            patch("collectors.imf_weo.store.upsert"),
        ):
            adapter = ImfWeoAdapter()
            result = adapter.fetch()

        assert "imf_weo_runs" in result
        assert isinstance(result["imf_weo_runs"], pd.DataFrame)

    def test_summary_series_ok_count(self):
        with (
            patch("collectors.imf_weo.config.load", return_value=_MINIMAL_CONFIG),
            patch("requests.get", return_value=_mock_response(_CANONICAL_RESPONSE)),
            patch("collectors.imf_weo.store.upsert"),
        ):
            adapter = ImfWeoAdapter()
            result = adapter.fetch()

        assert result["imf_weo_runs"]["series_ok"].iloc[0] == 2  # USA + DEU


# ---------------------------------------------------------------------------
# 7. all_fail_raises
# ---------------------------------------------------------------------------

class TestAllFailRaises:
    def test_raises_when_no_data_at_all(self):
        empty_resp = {"values": {_INDICATOR: {}}}
        with (
            patch("collectors.imf_weo.config.load", return_value=_MINIMAL_CONFIG),
            patch("requests.get", return_value=_mock_response(empty_resp)),
            patch("collectors.imf_weo.store.upsert"),
        ):
            adapter = ImfWeoAdapter()
            with pytest.raises(RuntimeError, match="all indicators"):
                adapter.fetch()


# ---------------------------------------------------------------------------
# 8. disabled_raises
# ---------------------------------------------------------------------------

class TestDisabledRaises:
    def test_raises_when_disabled(self):
        cfg = {**_MINIMAL_CONFIG, "imf_weo": {**_MINIMAL_CONFIG["imf_weo"], "enabled": False}}
        with (
            patch("collectors.imf_weo.config.load", return_value=cfg),
        ):
            adapter = ImfWeoAdapter()
            with pytest.raises(RuntimeError, match="disabled"):
                adapter.fetch()


# ---------------------------------------------------------------------------
# 9. date_index_dec31
# ---------------------------------------------------------------------------

class TestDateIndexDec31:
    def test_index_is_dec31(self):
        with patch("requests.get", return_value=_mock_response(_CANONICAL_RESPONSE)):
            result = fetch_indicator(_BASE_URL, _INDICATOR, ["USA"])
        for ts in result["USA"].index:
            assert ts.month == 12, f"Expected month=12, got {ts}"
            assert ts.day == 31, f"Expected day=31, got {ts}"

    def test_years_sorted_ascending(self):
        with patch("requests.get", return_value=_mock_response(_CANONICAL_RESPONSE)):
            result = fetch_indicator(_BASE_URL, _INDICATOR, ["USA"])
        years = [ts.year for ts in result["USA"].index]
        assert years == sorted(years)


# ---------------------------------------------------------------------------
# 10. alias_column_name
# ---------------------------------------------------------------------------

class TestAliasColumnName:
    def test_df_column_is_alias_not_indicator_id(self):
        """store.upsert receives a DataFrame whose column is the alias, not the raw id."""
        captured: list[pd.DataFrame] = []

        def capture_upsert(_group, _key, df):
            captured.append(df)

        with (
            patch("collectors.imf_weo.config.load", return_value=_MINIMAL_CONFIG),
            patch("requests.get", return_value=_mock_response(_CANONICAL_RESPONSE)),
            patch("collectors.imf_weo.store.upsert", side_effect=capture_upsert),
        ):
            adapter = ImfWeoAdapter()
            adapter.fetch()

        for df in captured:
            assert "gross_debt_pct_gdp" in df.columns, (
                f"Expected alias column 'gross_debt_pct_gdp', got {df.columns.tolist()}"
            )
            assert _INDICATOR not in df.columns
