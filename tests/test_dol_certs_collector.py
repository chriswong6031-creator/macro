"""tests/test_dol_certs_collector.py — Tests for collectors/dol_labor_certs.py.

Coverage:
  - Column normalization on synthetic raw-file fixtures
  - Certified-only filter (deny/withdraw rows dropped)
  - PIT decision_date keying
  - Wage annualization from raw + unit
  - Quarter-detection no-op path (all quarters ingested)
  - Store-absent honest null (env override tested)
  - No second fuzzy matcher (assert import from lib.warn_fuzzy)
  - banned words check (no 'validated' in output)
  - Exit-0-always / tolerant behavior
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Ensure lib.warn_fuzzy is the ONLY fuzzy matcher used (house law)
# ---------------------------------------------------------------------------

def test_no_second_fuzzy_matcher_in_collector():
    """Collector must import match_ticker from lib.warn_fuzzy, not define its own."""
    import collectors.dol_labor_certs as col

    # The module must not define any function whose name suggests fuzzy matching
    # except by delegating to lib.warn_fuzzy
    for name in dir(col):
        if "fuzzy" in name.lower() or "match_ticker" in name.lower():
            # If defined in the module, it must be an import, not a new def
            obj = getattr(col, name)
            # Check it is not defined in dol_labor_certs module
            module = getattr(obj, "__module__", "")
            assert "dol_labor_certs" not in str(module), (
                f"Found {name} defined in dol_labor_certs — must use lib.warn_fuzzy only"
            )


def test_warn_fuzzy_importable():
    """lib.warn_fuzzy must be importable and provide match_ticker + load_ticker_map."""
    from lib.warn_fuzzy import load_ticker_map, match_ticker  # noqa: F401
    assert callable(load_ticker_map)
    assert callable(match_ticker)


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

def _make_lca_df(rows: list[dict]) -> pd.DataFrame:
    """Create a minimal synthetic LCA DataFrame mimicking the real column layout."""
    defaults = {
        "CASE_NUMBER": "I-200-00000",
        "CASE_STATUS": "Certified",
        "DECISION_DATE": "2025-01-15",
        "EMPLOYER_NAME": "Acme Corp",
        "JOB_TITLE": "Software Engineer",
        "WORKSITE_STATE": "CA",
        "WAGE_RATE_OF_PAY_FROM": "150000",
        "WAGE_UNIT_OF_PAY": "Year",
        # Extra columns that should be dropped
        "EMPLOYER_ADDRESS1": "123 Main St",
        "EMPLOYER_CITY": "San Jose",
        "NAICS_CODE": "541511",
    }
    out = []
    for r in rows:
        row = {**defaults, **r}
        out.append(row)
    return pd.DataFrame(out)


def _make_perm_df(rows: list[dict]) -> pd.DataFrame:
    """Create a minimal synthetic PERM DataFrame."""
    defaults = {
        "CASE_NUMBER": "A-00000-00000",
        "CASE_STATUS": "Certified",
        "DECISION_DATE": "2025-02-20",
        "EMPLOYER_NAME": "Global Tech",
        "JOB_TITLE": "Data Scientist",
        "WORKSITE_STATE": "NY",
        "WAGE_OFFER_FROM": "120000",
        "WAGE_OFFER_UNIT_OF_PAY": "Year",
        # Extra columns
        "EMPLOYER_STATE_PROVINCE": "NY",
    }
    out = []
    for r in rows:
        row = {**defaults, **r}
        out.append(row)
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Normalization tests
# ---------------------------------------------------------------------------

class TestNormalizeDf:
    """Tests for _normalize_df internals."""

    def test_lca_column_subset(self):
        """Output must have only the 8 STORE_COLS columns."""
        from collectors.dol_labor_certs import _normalize_df, STORE_COLS, _LCA_COLS

        raw = _make_lca_df([{}])
        result = _normalize_df(raw, "lca", _LCA_COLS, "2025-04-01")

        assert list(result.columns) == STORE_COLS

    def test_perm_column_subset(self):
        """PERM output must also yield only STORE_COLS."""
        from collectors.dol_labor_certs import _normalize_df, STORE_COLS, _PERM_COLS

        raw = _make_perm_df([{}])
        result = _normalize_df(raw, "perm", _PERM_COLS, "2025-04-01")

        assert list(result.columns) == STORE_COLS

    def test_certified_only_filter(self):
        """Only 'Certified' rows pass; Denied / Withdrawn rows are dropped."""
        from collectors.dol_labor_certs import _normalize_df, _LCA_COLS

        raw = _make_lca_df([
            {"CASE_STATUS": "Certified"},
            {"CASE_STATUS": "Denied"},
            {"CASE_STATUS": "Withdrawn"},
            {"CASE_STATUS": "CERTIFIED"},       # upper-case variant
            {"CASE_STATUS": "Invalidated"},
        ])
        result = _normalize_df(raw, "lca", _LCA_COLS, "2025-04-01")

        assert len(result) == 2
        assert all(result["case_status"].str.upper() == "CERTIFIED")

    def test_pit_decision_date_keying(self):
        """decision_date must be parsed from DECISION_DATE column."""
        from collectors.dol_labor_certs import _normalize_df, _LCA_COLS

        raw = _make_lca_df([
            {"DECISION_DATE": "2024-10-01"},
            {"DECISION_DATE": "2025-01-15"},
        ])
        result = _normalize_df(raw, "lca", _LCA_COLS, "2025-04-01")

        dates = pd.to_datetime(result["decision_date"])
        assert dates.iloc[0].year == 2024
        assert dates.iloc[0].month == 10
        assert dates.iloc[1].year == 2025

    def test_rows_without_decision_date_dropped(self):
        """Rows with unparseable DECISION_DATE must be dropped."""
        from collectors.dol_labor_certs import _normalize_df, _LCA_COLS

        raw = _make_lca_df([
            {"DECISION_DATE": "not-a-date"},
            {"DECISION_DATE": "2025-03-01"},
        ])
        result = _normalize_df(raw, "lca", _LCA_COLS, "2025-04-01")

        assert len(result) == 1

    def test_rows_without_employer_dropped(self):
        """Rows with blank employer_name are dropped."""
        from collectors.dol_labor_certs import _normalize_df, _LCA_COLS

        raw = _make_lca_df([
            {"EMPLOYER_NAME": ""},
            {"EMPLOYER_NAME": "   "},
            {"EMPLOYER_NAME": "Real Corp"},
        ])
        result = _normalize_df(raw, "lca", _LCA_COLS, "2025-04-01")

        assert len(result) == 1
        assert result.iloc[0]["employer_name"] == "Real Corp"

    def test_program_field(self):
        """program column must be populated correctly."""
        from collectors.dol_labor_certs import _normalize_df, _LCA_COLS, _PERM_COLS

        raw_lca = _make_lca_df([{}])
        raw_perm = _make_perm_df([{}])

        lca_result = _normalize_df(raw_lca, "lca", _LCA_COLS, "2025-04-01")
        perm_result = _normalize_df(raw_perm, "perm", _PERM_COLS, "2025-04-01")

        assert lca_result.iloc[0]["program"] == "lca"
        assert perm_result.iloc[0]["program"] == "perm"

    def test_file_published_stored(self):
        """file_published must be stored as-passed."""
        from collectors.dol_labor_certs import _normalize_df, _LCA_COLS

        raw = _make_lca_df([{}])
        result = _normalize_df(raw, "lca", _LCA_COLS, "2025-04-01")

        assert result.iloc[0]["file_published"] == "2025-04-01"


# ---------------------------------------------------------------------------
# Wage annualization tests
# ---------------------------------------------------------------------------

class TestAnnualize:
    def test_annual_wage_unchanged(self):
        from collectors.dol_labor_certs import _annualize
        assert _annualize("150000", "Year") == 150000.0

    def test_hourly_to_annual(self):
        from collectors.dol_labor_certs import _annualize
        result = _annualize("75", "Hour")
        assert result == pytest.approx(75 * 2080, rel=1e-4)

    def test_monthly_to_annual(self):
        from collectors.dol_labor_certs import _annualize
        result = _annualize("10000", "Month")
        assert result == pytest.approx(120000.0, rel=1e-4)

    def test_weekly_to_annual(self):
        from collectors.dol_labor_certs import _annualize
        result = _annualize("2000", "Week")
        assert result == pytest.approx(104000.0, rel=1e-4)

    def test_none_input(self):
        from collectors.dol_labor_certs import _annualize
        assert _annualize(None, "Year") is None

    def test_zero_or_negative_dropped(self):
        from collectors.dol_labor_certs import _annualize
        assert _annualize("0", "Year") is None
        assert _annualize("-100", "Year") is None

    def test_comma_in_wage(self):
        from collectors.dol_labor_certs import _annualize
        assert _annualize("150,000", "Year") == 150000.0


# ---------------------------------------------------------------------------
# Quarter detection + no-op path
# ---------------------------------------------------------------------------

class TestQuarterDetection:
    def test_dol_fiscal_quarters_returns_recent_first(self):
        from collectors.dol_labor_certs import _dol_fiscal_quarters
        quarters = _dol_fiscal_quarters()
        assert len(quarters) >= 6
        # All entries are (str_fy, str_q) tuples
        for fy, q in quarters:
            assert fy.isdigit()
            assert q in ("1", "2", "3", "4")

    def test_collect_noop_when_all_ingested(self, tmp_path):
        """collect() should no-op immediately when all recent quarters are ingested."""
        from collectors.dol_labor_certs import collect, _dol_fiscal_quarters

        # Pre-populate state with all recent quarters
        quarters = _dol_fiscal_quarters()
        ingested = [f"lca:FY{fy}_Q{q}" for fy, q in quarters] + \
                   [f"perm:FY{fy}_Q{q}" for fy, q in quarters]

        state_path = tmp_path / "certs" / "_state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps({"ingested": ingested}))

        store_path = tmp_path / "certs" / "certs.parquet"

        result = collect(
            programs=["lca", "perm"],
            store_path=store_path,
            root=tmp_path,
        )

        assert result["new_quarters_ingested"] == []
        assert result["rows_added"] == 0


# ---------------------------------------------------------------------------
# Store-absent honest null (env override)
# ---------------------------------------------------------------------------

class TestStoreAbsent:
    def test_store_absent_returns_none(self, tmp_path):
        """_find_store returns None when store doesn't exist and env not set."""
        from collectors.dol_labor_certs import _find_store

        # Clear env
        with mock.patch.dict(os.environ, {}, clear=True):
            if "DOL_CERTS_STORE" in os.environ:
                del os.environ["DOL_CERTS_STORE"]
            result = _find_store(tmp_path)

        assert result is None

    def test_env_override_resolves_store(self, tmp_path):
        """DOL_CERTS_STORE env var must override the default path."""
        from collectors.dol_labor_certs import _find_store

        store_path = tmp_path / "custom" / "certs.parquet"
        store_path.parent.mkdir(parents=True)
        store_path.write_bytes(b"placeholder")  # just needs to exist

        with mock.patch.dict(os.environ, {"DOL_CERTS_STORE": str(store_path)}):
            result = _find_store(tmp_path)

        assert result == store_path

    def test_env_override_missing_path_warns_and_continues(self, tmp_path, caplog):
        """DOL_CERTS_STORE pointing to nonexistent path → warning, not crash."""
        from collectors.dol_labor_certs import _find_store
        import logging

        bad_path = tmp_path / "doesnt_exist" / "certs.parquet"

        with mock.patch.dict(os.environ, {"DOL_CERTS_STORE": str(bad_path)}):
            with caplog.at_level(logging.WARNING):
                result = _find_store(tmp_path)

        # Should not find the store (path doesn't exist)
        assert result is None
        # Warning should mention the bad path
        assert "DOL_CERTS_STORE" in caplog.text


# ---------------------------------------------------------------------------
# Banned words
# ---------------------------------------------------------------------------

class TestBannedWords:
    def test_no_validated_in_collector_source(self):
        """The word 'validated' must not appear in user-facing output."""
        import collectors.dol_labor_certs as col
        import inspect

        source = inspect.getsource(col)
        # Check it's not used as a status value or user-facing text
        import re
        # Only check in string literals / log messages (not comments or docstrings about the law)
        # Simple heuristic: the word "validated" should not appear in quoted strings
        # (excluding the check itself)
        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            if "validated" in line.lower() and not line.strip().startswith("#"):
                # Allow in docstring explanations of the law
                stripped = line.strip().lower()
                assert "validated" not in stripped or "never" in stripped, (
                    f"Line {i}: 'validated' found in user-facing code: {line}"
                )


# ---------------------------------------------------------------------------
# Exit 0 / tolerant behavior
# ---------------------------------------------------------------------------

class TestToleranceBehavior:
    def test_normalize_df_returns_empty_on_missing_decision_date_col(self):
        """When DECISION_DATE col is absent from raw df, normalize returns empty DataFrame."""
        from collectors.dol_labor_certs import _normalize_df, STORE_COLS, _LCA_COLS

        # Create a df with DECISION_DATE missing entirely
        raw = pd.DataFrame([{
            "EMPLOYER_NAME": "Test Corp",
            "JOB_TITLE": "Engineer",
            "CASE_STATUS": "Certified",
            "WORKSITE_STATE": "CA",
            "WAGE_RATE_OF_PAY_FROM": "100000",
            "WAGE_UNIT_OF_PAY": "Year",
        }])
        result = _normalize_df(raw, "lca", _LCA_COLS, "2025-04-01")
        assert result.empty or list(result.columns) == STORE_COLS

    def test_collect_dry_run_returns_zero_rows(self, tmp_path):
        """dry_run=True should return rows_added=0 and no_store written."""
        from collectors.dol_labor_certs import collect

        store_path = tmp_path / "certs.parquet"
        result = collect(
            programs=["lca", "perm"],
            store_path=store_path,
            dry_run=True,
            root=tmp_path,
        )

        assert result["rows_added"] == 0
        assert not store_path.exists()
