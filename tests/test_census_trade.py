"""tests/test_census_trade.py — Tests for collectors/census_trade.py (TIL W8).

Coverage:
  - config/trade_flow_codes.yml schema: HS-code format, theme IDs resolve against
    crosswalk, expected_direction enum, required fields
  - Normalizer on synthetic API-response fixtures
  - Missing-month fall-through (regression: 2026-07-09 DOL 404-break incident):
    newest month absent → older months still ingested
  - Per-code failure isolation: one bad code's HTTP error does not void others
  - No-key honest null (CENSUS_API_KEY absent → no-op return, exit 0)
  - Parquet upsert dedup (PIT law: existing (hs_code, stat_month) not overwritten)
  - State file round-trip
  - Month-range generation edge cases
  - Banned words check (no 'validated' in output artifacts)
  - API key required (verified 2026-07-09; keyless returns 302)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest
import yaml

# ---------------------------------------------------------------------------
# Config schema tests
# ---------------------------------------------------------------------------

class TestTradeFlowCodesConfig:
    """Validate config/trade_flow_codes.yml schema and content."""

    @pytest.fixture(scope="class")
    def codes_cfg(self):
        path = Path(__file__).resolve().parent.parent / "config" / "trade_flow_codes.yml"
        with open(path) as fh:
            return yaml.safe_load(fh)

    def test_file_loads(self, codes_cfg):
        assert codes_cfg is not None

    def test_has_version(self, codes_cfg):
        assert codes_cfg.get("version") == 1

    def test_has_codes_list(self, codes_cfg):
        assert isinstance(codes_cfg.get("codes"), list)
        assert len(codes_cfg["codes"]) >= 25, (
            f"Expected ≥25 codes, got {len(codes_cfg['codes'])}"
        )
        assert len(codes_cfg["codes"]) <= 45, (
            f"Expected ≤45 codes, got {len(codes_cfg['codes'])}"
        )

    def test_hs_code_format(self, codes_cfg):
        """HS codes must be 6-digit strings (WCO standard, as used in COMM_LVL=HS6)."""
        for entry in codes_cfg["codes"]:
            hs = str(entry["hs_code"]).strip()
            assert len(hs) == 6, (
                f"hs_code {hs!r} for theme {entry.get('theme_id')} "
                f"is not 6 digits (got {len(hs)})"
            )
            assert hs.isdigit(), f"hs_code {hs!r} contains non-digit characters"

    def test_required_fields_present(self, codes_cfg):
        required = {"hs_code", "label_en", "label_zh", "theme_id", "expected_direction", "rationale"}
        for entry in codes_cfg["codes"]:
            missing = required - set(entry.keys())
            assert not missing, (
                f"Code {entry.get('hs_code')} missing required fields: {missing}"
            )

    def test_expected_direction_enum(self, codes_cfg):
        valid = {"rising_imports_confirms", "falling_imports_confirms"}
        for entry in codes_cfg["codes"]:
            d = entry.get("expected_direction")
            assert d in valid, (
                f"Code {entry['hs_code']} has invalid expected_direction {d!r}"
            )

    def test_theme_ids_resolve_against_crosswalk(self, codes_cfg):
        """All theme_id values must exist in config/theme_crosswalk.yml."""
        crosswalk_path = (
            Path(__file__).resolve().parent.parent / "config" / "theme_crosswalk.yml"
        )
        with open(crosswalk_path) as fh:
            cw = yaml.safe_load(fh)
        valid_ids = {t["id"] for t in cw.get("themes", [])}

        for entry in codes_cfg["codes"]:
            tid = entry.get("theme_id")
            assert tid in valid_ids, (
                f"Code {entry['hs_code']}: theme_id {tid!r} not in theme_crosswalk.yml"
            )

    def test_themes_covered(self, codes_cfg):
        """Required themes must have at least one code each."""
        required_themes = {
            "rare_earth_critical_min",
            "solar",
            "ai_semiconductors",
            "semicap_equipment",
            "grid_electrification",
            "nuclear_power",
            "copper_steel_electrify",
            "glp1_obesity",
            "diagnostics_lifesci",
            "defense_aerospace",
        }
        covered = {entry["theme_id"] for entry in codes_cfg["codes"]}
        missing = required_themes - covered
        assert not missing, f"Required themes missing from trade_flow_codes.yml: {missing}"

    def test_no_duplicate_hs_codes(self, codes_cfg):
        """Same HS code should not appear twice (would cause double-counting)."""
        seen: dict[str, str] = {}
        for entry in codes_cfg["codes"]:
            hs = str(entry["hs_code"])
            assert hs not in seen, (
                f"Duplicate hs_code {hs}: appears in {seen[hs]} and {entry['theme_id']}"
            )
            seen[hs] = entry["theme_id"]

    def test_label_zh_not_empty(self, codes_cfg):
        for entry in codes_cfg["codes"]:
            assert entry.get("label_zh", "").strip(), (
                f"Code {entry['hs_code']} has empty label_zh"
            )

    def test_no_validated_in_labels(self, codes_cfg):
        """Banned word 'validated' must not appear in any label or rationale."""
        for entry in codes_cfg["codes"]:
            for field in ("label_en", "label_zh", "rationale"):
                text = str(entry.get(field, "")).lower()
                assert "validated" not in text, (
                    f"Banned word 'validated' found in code {entry['hs_code']} field {field!r}"
                )


# ---------------------------------------------------------------------------
# Collector import and structure tests
# ---------------------------------------------------------------------------

class TestCensusTradeImports:

    def test_module_importable(self):
        import collectors.census_trade  # noqa: F401

    def test_store_cols_defined(self):
        from collectors.census_trade import STORE_COLS
        assert "hs_code" in STORE_COLS
        assert "stat_month" in STORE_COLS
        assert "value_usd" in STORE_COLS
        assert "ingested_at" in STORE_COLS

    def test_collect_function_exists(self):
        from collectors.census_trade import collect
        assert callable(collect)

    def test_load_codes_works(self):
        from collectors.census_trade import _load_codes
        codes = _load_codes()
        assert isinstance(codes, list)
        assert len(codes) >= 25


# ---------------------------------------------------------------------------
# No-key honest null
# ---------------------------------------------------------------------------

class TestNoKeyHonestNull:

    def test_collect_no_key_returns_no_op(self, monkeypatch):
        """With no CENSUS_API_KEY, collect() returns no-op dict without raising."""
        monkeypatch.delenv("CENSUS_API_KEY", raising=False)
        from collectors.census_trade import collect
        result = collect()
        assert result["no_op"] is True
        assert result["codes_attempted"] == 0
        assert result["rows_added"] == 0
        assert "CENSUS_API_KEY" in (result.get("error") or "")

    def test_collect_empty_key_returns_no_op(self, monkeypatch):
        """Empty string key also triggers no-op."""
        monkeypatch.setenv("CENSUS_API_KEY", "")
        from collectors.census_trade import collect
        result = collect()
        assert result["no_op"] is True


# ---------------------------------------------------------------------------
# Month range generation
# ---------------------------------------------------------------------------

class TestMonthRange:

    def test_basic_range(self):
        from collectors.census_trade import _month_range
        months = _month_range("2024-01", "2024-03")
        assert months == ["2024-01", "2024-02", "2024-03"]

    def test_same_month(self):
        from collectors.census_trade import _month_range
        months = _month_range("2024-06", "2024-06")
        assert months == ["2024-06"]

    def test_inverted_range_empty(self):
        from collectors.census_trade import _month_range
        months = _month_range("2024-06", "2024-01")
        assert months == []

    def test_multi_year_range(self):
        from collectors.census_trade import _month_range
        months = _month_range("2023-11", "2024-02")
        assert months == ["2023-11", "2023-12", "2024-01", "2024-02"]


# ---------------------------------------------------------------------------
# API response normalizer (synthetic fixtures)
# ---------------------------------------------------------------------------

class TestFetchOneNormalizer:
    """
    Test _fetch_one parsing logic using mocked HTTP responses.

    Census API response shape (verified 2026-07-09 against variables.json):
    [["GEN_VAL_MO","GEN_QY1_MO","UNIT_QY1","I_COMMODITY","time"],
     ["1234567890","5000","KG","854231","2024-01"]]
    """

    def _make_mock_response(self, status_code: int, json_data=None, redirect: bool = False):
        resp = mock.Mock()
        resp.status_code = status_code
        if json_data is not None:
            resp.json.return_value = json_data
        resp.raise_for_status = mock.Mock()
        if status_code >= 400:
            import requests
            resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status_code}")
        return resp

    def test_parses_single_row(self):
        """Standard single-row response parses into dict with correct fields."""
        from collectors.census_trade import _fetch_one
        import requests

        mock_resp = self._make_mock_response(200, [
            ["GEN_VAL_MO", "GEN_QY1_MO", "UNIT_QY1", "I_COMMODITY", "time"],
            ["5000000", "10000", "KG", "854231", "2024-01"],
        ])

        session = mock.Mock(spec=requests.Session)
        session.get.return_value = mock_resp

        result = _fetch_one("854231", "2024-01", "testkey", session)
        assert result is not None
        assert result["hs_code"] == "854231"
        assert result["stat_month"] == "2024-01"
        assert result["value_usd"] == 5_000_000
        assert result["quantity"] == 10_000
        assert result["quantity_unit"] == "KG"

    def test_404_returns_none(self):
        """404 response (month not yet published) returns None without raising."""
        from collectors.census_trade import _fetch_one
        import requests

        mock_resp = self._make_mock_response(404)
        session = mock.Mock(spec=requests.Session)
        session.get.return_value = mock_resp

        result = _fetch_one("854231", "2026-06", "testkey", session)
        assert result is None

    def test_empty_data_returns_none(self):
        """API returns header-only (no data rows) → None."""
        from collectors.census_trade import _fetch_one
        import requests

        mock_resp = self._make_mock_response(200, [
            ["GEN_VAL_MO", "GEN_QY1_MO", "UNIT_QY1", "I_COMMODITY", "time"],
        ])
        session = mock.Mock(spec=requests.Session)
        session.get.return_value = mock_resp

        result = _fetch_one("854231", "2024-01", "testkey", session)
        assert result is None

    def test_multi_row_sums_value(self):
        """Multi-row response (multiple country origins) sums value and quantity."""
        from collectors.census_trade import _fetch_one
        import requests

        mock_resp = self._make_mock_response(200, [
            ["GEN_VAL_MO", "GEN_QY1_MO", "UNIT_QY1", "I_COMMODITY", "time"],
            ["1000000", "2000", "KG", "854231", "2024-01"],
            ["3000000", "5000", "KG", "854231", "2024-01"],
        ])
        session = mock.Mock(spec=requests.Session)
        session.get.return_value = mock_resp

        result = _fetch_one("854231", "2024-01", "testkey", session)
        assert result is not None
        assert result["value_usd"] == 4_000_000
        assert result["quantity"] == 7_000

    def test_302_raises_http_error(self):
        """302 redirect (missing key) raises HTTPError."""
        from collectors.census_trade import _fetch_one
        import requests

        mock_resp = self._make_mock_response(302)
        session = mock.Mock(spec=requests.Session)
        session.get.return_value = mock_resp

        with pytest.raises(requests.HTTPError, match="key"):
            _fetch_one("854231", "2024-01", "badkey", session)

    def test_null_value_rows(self):
        """Rows with null values are handled without crashing."""
        from collectors.census_trade import _fetch_one
        import requests

        mock_resp = self._make_mock_response(200, [
            ["GEN_VAL_MO", "GEN_QY1_MO", "UNIT_QY1", "I_COMMODITY", "time"],
            ["null", "null", "KG", "854231", "2024-01"],
        ])
        session = mock.Mock(spec=requests.Session)
        session.get.return_value = mock_resp

        result = _fetch_one("854231", "2024-01", "testkey", session)
        # Null value → both value_usd and quantity should be None
        assert result is not None
        assert result["value_usd"] is None
        assert result["quantity"] is None


# ---------------------------------------------------------------------------
# Missing-month fall-through regression test
# (2026-07-09 DOL 404-break incident: newest month absent must not stop older months)
# ---------------------------------------------------------------------------

class TestMissingMonthFallThrough:

    def test_newest_month_404_does_not_stop_older_months(self, monkeypatch, tmp_path):
        """
        Regression: if the newest month returns 404 (not yet published),
        older months must still be ingested.

        Setup: codes = 1 code; mock HTTP where:
          - 2024-03 → 404 (newest, not published)
          - 2024-02 → 200 with data
          - 2024-01 → 200 with data
        Assert: 2 rows ingested (NOT 0).
        """
        import requests as req_lib
        from collectors import census_trade

        monkeypatch.setenv("CENSUS_API_KEY", "testkey123")
        monkeypatch.setenv("TRADE_FLOWS_STORE", str(tmp_path))

        # Patch codes to a single test code
        single_code = [{
            "hs_code": "854231",
            "label_en": "Test GPU Code",
            "label_zh": "测试GPU代码",
            "theme_id": "ai_semiconductors",
            "expected_direction": "rising_imports_confirms",
            "rationale": "test",
        }]

        response_map = {
            "2024-03": (404, None),
            "2024-02": (200, [
                ["GEN_VAL_MO", "GEN_QY1_MO", "UNIT_QY1", "I_COMMODITY", "time"],
                ["2000000", "3000", "KG", "854231", "2024-02"],
            ]),
            "2024-01": (200, [
                ["GEN_VAL_MO", "GEN_QY1_MO", "UNIT_QY1", "I_COMMODITY", "time"],
                ["1500000", "2500", "KG", "854231", "2024-01"],
            ]),
        }

        def fake_get(url, params=None, timeout=None):
            stat_month = (params or {}).get("time", "")
            status, data = response_map.get(stat_month, (404, None))
            resp = mock.Mock()
            resp.status_code = status
            if data is not None:
                resp.json.return_value = data
            resp.raise_for_status = mock.Mock()
            if status >= 400:
                resp.raise_for_status.side_effect = req_lib.HTTPError(f"HTTP {status}")
            return resp

        with (
            mock.patch.object(census_trade, "_load_codes", return_value=single_code),
            mock.patch.object(census_trade, "_month_range", return_value=["2024-01", "2024-02", "2024-03"]),
            mock.patch("requests.Session") as MockSession,
        ):
            mock_sess = mock.Mock()
            mock_sess.get.side_effect = fake_get
            mock_sess.headers = mock.MagicMock()
            MockSession.return_value = mock_sess

            result = census_trade.collect(full_history=False)

        # 2 months of data ingested despite 2024-03 returning 404
        assert result["months_fetched"] == 2, (
            f"Expected 2 months fetched, got {result['months_fetched']}. "
            "Newest-month 404 must not stop ingestion of older months."
        )
        assert result["rows_added"] >= 2
        assert result["no_op"] is False


# ---------------------------------------------------------------------------
# Per-code failure isolation
# ---------------------------------------------------------------------------

class TestPerCodeFailureIsolation:

    def test_one_bad_code_does_not_void_others(self, monkeypatch, tmp_path):
        """
        A 500 error on one HS code must not prevent other codes from being ingested.
        """
        import requests as req_lib
        from collectors import census_trade

        monkeypatch.setenv("CENSUS_API_KEY", "testkey123")
        monkeypatch.setenv("TRADE_FLOWS_STORE", str(tmp_path))

        two_codes = [
            {
                "hs_code": "280530",  # will get 500 error
                "label_en": "Rare earths",
                "label_zh": "稀土",
                "theme_id": "rare_earth_critical_min",
                "expected_direction": "rising_imports_confirms",
                "rationale": "test",
            },
            {
                "hs_code": "854231",  # will succeed
                "label_en": "Processors",
                "label_zh": "处理器",
                "theme_id": "ai_semiconductors",
                "expected_direction": "rising_imports_confirms",
                "rationale": "test",
            },
        ]

        def fake_get(url, params=None, timeout=None):
            hs = (params or {}).get("I_COMMODITY", "")
            resp = mock.Mock()
            if hs == "280530":
                resp.status_code = 500
                resp.raise_for_status.side_effect = req_lib.HTTPError("HTTP 500 Server Error")
            else:
                resp.status_code = 200
                resp.json.return_value = [
                    ["GEN_VAL_MO", "GEN_QY1_MO", "UNIT_QY1", "I_COMMODITY", "time"],
                    ["5000000", "10000", "KG", "854231", "2024-01"],
                ]
                resp.raise_for_status = mock.Mock()
            return resp

        with (
            mock.patch.object(census_trade, "_load_codes", return_value=two_codes),
            mock.patch.object(census_trade, "_month_range", return_value=["2024-01"]),
            mock.patch("requests.Session") as MockSession,
        ):
            mock_sess = mock.Mock()
            mock_sess.get.side_effect = fake_get
            mock_sess.headers = mock.MagicMock()
            MockSession.return_value = mock_sess

            result = census_trade.collect(full_history=False)

        # Code 280530 failed, code 854231 succeeded
        assert result["codes_failed"] >= 1, "Expected at least 1 failed code"
        assert result["months_fetched"] >= 1, "Expected at least 1 successful month from second code"
        assert result["rows_added"] >= 1


# ---------------------------------------------------------------------------
# Parquet upsert / PIT dedup
# ---------------------------------------------------------------------------

class TestParquetUpsert:

    def test_first_write(self, tmp_path):
        from collectors.census_trade import _upsert_parquet, STORE_COLS
        rows = [
            {"hs_code": "854231", "stat_month": "2024-01", "value_usd": 1000000,
             "quantity": 500, "quantity_unit": "KG", "ingested_at": "2024-02-01T00:00:00+00:00"},
        ]
        added = _upsert_parquet(tmp_path, rows)
        assert added == 1
        df = pd.read_parquet(tmp_path / "imports_monthly.parquet")
        assert len(df) == 1

    def test_dedup_existing_month_not_overwritten(self, tmp_path):
        """PIT LAW: second write with same (hs_code, stat_month) adds 0 rows."""
        from collectors.census_trade import _upsert_parquet
        rows = [
            {"hs_code": "854231", "stat_month": "2024-01", "value_usd": 1000000,
             "quantity": 500, "quantity_unit": "KG", "ingested_at": "2024-02-01T00:00:00+00:00"},
        ]
        _upsert_parquet(tmp_path, rows)

        # Write again — same key, different value
        rows2 = [
            {"hs_code": "854231", "stat_month": "2024-01", "value_usd": 9999999,
             "quantity": 999, "quantity_unit": "KG", "ingested_at": "2024-03-01T00:00:00+00:00"},
        ]
        added = _upsert_parquet(tmp_path, rows2)
        assert added == 0, "PIT LAW: existing (hs_code, stat_month) pair must not be overwritten"

        df = pd.read_parquet(tmp_path / "imports_monthly.parquet")
        assert len(df) == 1
        assert df.iloc[0]["value_usd"] == 1000000  # original value preserved

    def test_new_month_appended(self, tmp_path):
        """New month for same code is appended."""
        from collectors.census_trade import _upsert_parquet
        rows1 = [
            {"hs_code": "854231", "stat_month": "2024-01", "value_usd": 1000000,
             "quantity": 500, "quantity_unit": "KG", "ingested_at": "2024-02-01T00:00:00+00:00"},
        ]
        _upsert_parquet(tmp_path, rows1)

        rows2 = [
            {"hs_code": "854231", "stat_month": "2024-02", "value_usd": 1200000,
             "quantity": 600, "quantity_unit": "KG", "ingested_at": "2024-03-01T00:00:00+00:00"},
        ]
        added = _upsert_parquet(tmp_path, rows2)
        assert added == 1

        df = pd.read_parquet(tmp_path / "imports_monthly.parquet")
        assert len(df) == 2


# ---------------------------------------------------------------------------
# State file round-trip
# ---------------------------------------------------------------------------

class TestStateFile:

    def test_state_roundtrip(self, tmp_path):
        from collectors.census_trade import _load_state, _save_state
        state = {"854231": "2024-03", "280530": "2024-02"}
        _save_state(tmp_path, state)
        loaded = _load_state(tmp_path)
        assert loaded == state

    def test_absent_state_returns_empty(self, tmp_path):
        from collectors.census_trade import _load_state
        result = _load_state(tmp_path / "nonexistent")
        assert result == {}


# ---------------------------------------------------------------------------
# Banned words in collect() output
# ---------------------------------------------------------------------------

class TestBannedWords:

    def test_no_validated_in_collect_output(self, monkeypatch):
        """'validated' must not appear in collect() return dict."""
        monkeypatch.delenv("CENSUS_API_KEY", raising=False)
        from collectors.census_trade import collect
        result = collect()
        result_str = json.dumps(result)
        assert "validated" not in result_str.lower(), (
            "Banned word 'validated' found in collect() output"
        )
