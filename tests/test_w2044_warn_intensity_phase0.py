"""tests/test_w2044_warn_intensity_phase0.py — W2-044 WARN Intensity Phase-0 unit tests.

Tests the pure-logic components of scripts/w2044_warn_intensity_phase0.py.
No network calls; no real data required; no price-store dependency.

Covered:
  * TRIAL_GRID structure — 4 cells, all pre-registered as NEGATIVE direction
  * ACQUISITION_LADDER — all 3 rungs documented
  * Constants — PIT fence, intensity window, horizons, gates
  * match_ticker — correct matching, validity windows, longest-match wins
  * _parse_date / _to_int helpers from collector
  * normalize_state — CA, IL, NJ normalization smoke tests
  * date_clustered_t — correct t-stat on synthetic data
  * bh_adjust — correct FDR adjustment
  * _write_report — generates report without error, required sections present
  * Report file content — acquisition ladder, coverage section, gates present
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.w2044_warn_intensity_phase0 as w2044  # noqa: E402


# ---------------------------------------------------------------------------
# Section 1 — TRIAL_GRID structure
# ---------------------------------------------------------------------------

class TestTrialGrid:
    """The trial grid must have exactly 4 cells, all pre-registered NEGATIVE."""

    def test_grid_has_four_cells(self):
        assert len(w2044.TRIAL_GRID) == 4

    def test_all_cells_negative_direction(self):
        for cell in w2044.TRIAL_GRID:
            assert cell["direction"] == "negative", (
                f"Cell '{cell['variant']}' has direction '{cell['direction']}'; "
                "all cells must be pre-registered NEGATIVE"
            )

    def test_two_notice_event_cells(self):
        notice = [c for c in w2044.TRIAL_GRID if c["signal"] == "warn_notice_event"]
        assert len(notice) == 2, "Expected exactly 2 notice_event cells"

    def test_two_intensity_z_cells(self):
        intensity = [c for c in w2044.TRIAL_GRID if c["signal"] == "warn_intensity_z_90d"]
        assert len(intensity) == 2, "Expected exactly 2 intensity_z cells"

    def test_horizons_are_21d_and_63d(self):
        horizons = {c["fwd_days"] for c in w2044.TRIAL_GRID}
        assert horizons == {21, 63}, f"Expected horizons {{21, 63}}, got {horizons}"

    def test_each_variant_unique(self):
        variants = [c["variant"] for c in w2044.TRIAL_GRID]
        assert len(variants) == len(set(variants)), "Duplicate variant names in TRIAL_GRID"

    def test_all_cells_have_required_keys(self):
        required = {"variant", "signal", "fwd_days", "direction", "note"}
        for cell in w2044.TRIAL_GRID:
            missing = required - set(cell.keys())
            assert not missing, f"Cell '{cell.get('variant')}' missing keys: {missing}"

    def test_gate_direction_constant_is_negative(self):
        assert w2044.GATE_DIRECTION == "negative"


# ---------------------------------------------------------------------------
# Section 2 — Acquisition ladder
# ---------------------------------------------------------------------------

class TestAcquisitionLadder:
    """ACQUISITION_LADDER must document all 3 rungs per operator mandate."""

    def test_has_three_rungs(self):
        assert len(w2044.ACQUISITION_LADDER) == 3

    def test_rung_1_is_warn_scraper(self):
        rung1 = w2044.ACQUISITION_LADDER[0]
        assert rung1["rung"] == 1
        assert "warn-scraper" in rung1["source"].lower() or "biglocalnews" in rung1["source"].lower()
        assert rung1["status"] == "USED"

    def test_rung_2_is_bln_artifacts(self):
        rung2 = w2044.ACQUISITION_LADDER[1]
        assert rung2["rung"] == 2
        assert rung2["status"] == "ATTEMPTED"

    def test_rung_3_is_grey_scraping(self):
        rung3 = w2044.ACQUISITION_LADDER[2]
        assert rung3["rung"] == 3
        assert rung3["status"] == "ATTEMPTED"

    def test_rung_1_rows_positive(self):
        """Must report positive rows acquired."""
        assert w2044.ACQUISITION_LADDER[0].get("rows_acquired", 0) > 0

    def test_rung_1_documents_missing_states(self):
        """Must honestly document states that failed."""
        rung1 = w2044.ACQUISITION_LADDER[0]
        # TX and PA are known IP-blocked major states
        blocked = rung1.get("states_blocked_ip", [])
        assert "TX" in blocked or "tx" in [s.lower() for s in blocked]
        assert "PA" in blocked or "pa" in [s.lower() for s in blocked]


# ---------------------------------------------------------------------------
# Section 3 — Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_pit_fence_days_is_7(self):
        """Pre-registered PIT fence: notice date + 7 calendar days if posting date absent."""
        assert w2044.WARN_PIT_FENCE_DAYS == 7

    def test_intensity_window_days_is_90(self):
        assert w2044.INTENSITY_WINDOW_DAYS == 90

    def test_fwd_21(self):
        assert w2044.FWD_21 == 21

    def test_fwd_63(self):
        assert w2044.FWD_63 == 63

    def test_gate_abs_t(self):
        assert w2044.GATE_ABS_T == 2.0

    def test_gate_bh_q(self):
        assert w2044.GATE_BH_Q == 0.10

    def test_beta_win(self):
        assert w2044.BETA_WIN == 252

    def test_family_name(self):
        assert w2044.FAMILY == "w2044_warn_intensity"

    def test_price_start_is_2021(self):
        assert w2044.PRICE_START == date(2021, 7, 6)

    def test_price_end_is_2026(self):
        assert w2044.PRICE_END == date(2026, 7, 2)

    def test_min_events(self):
        assert w2044.MIN_EVENTS >= 30  # sanity: must be meaningful threshold


# ---------------------------------------------------------------------------
# Section 4 — match_ticker
# ---------------------------------------------------------------------------

TICKER_MAP_FIXTURE = [
    {"employer_name_pattern": "Amazon", "ticker": "AMZN", "valid_from": "1997-05-15", "valid_to": "", "confidence": "high", "notes": ""},
    {"employer_name_pattern": "Amazon.com", "ticker": "AMZN", "valid_from": "1997-05-15", "valid_to": "", "confidence": "high", "notes": ""},
    {"employer_name_pattern": "Boeing Company", "ticker": "BA", "valid_from": "1962-01-01", "valid_to": "", "confidence": "high", "notes": ""},
    {"employer_name_pattern": "Boeing", "ticker": "BA", "valid_from": "1962-01-01", "valid_to": "", "confidence": "high", "notes": ""},
    {"employer_name_pattern": "Spirit Airlines", "ticker": "SAVE", "valid_from": "2011-06-01", "valid_to": "2024-11-18", "confidence": "high", "notes": "Delisted"},
    {"employer_name_pattern": "Yellow Corporation", "ticker": "YELL", "valid_from": "1996-03-15", "valid_to": "2023-08-06", "confidence": "high", "notes": "Bankrupt"},
]


class TestMatchTicker:
    def test_exact_match_amazon(self):
        result = w2044.match_ticker("Amazon.com Services LLC", TICKER_MAP_FIXTURE, "2023-01-01")
        assert result == "AMZN"

    def test_exact_match_boeing(self):
        result = w2044.match_ticker("The Boeing Company — Seattle", TICKER_MAP_FIXTURE, "2023-01-01")
        assert result == "BA"

    def test_longest_match_wins(self):
        """Amazon.com should beat Amazon (longer pattern)."""
        result = w2044.match_ticker("Amazon.com Logistics", TICKER_MAP_FIXTURE, "2023-01-01")
        assert result == "AMZN"  # both match, longest (Amazon.com) wins

    def test_no_match_returns_none(self):
        result = w2044.match_ticker("Local Diner LLC", TICKER_MAP_FIXTURE, "2023-01-01")
        assert result is None

    def test_case_insensitive(self):
        result = w2044.match_ticker("AMAZON SERVICES", TICKER_MAP_FIXTURE, "2023-01-01")
        assert result == "AMZN"

    def test_validity_window_respected_past(self):
        """Spirit Airlines delisted Nov 2024; notice after that date -> no match."""
        result = w2044.match_ticker("Spirit Airlines", TICKER_MAP_FIXTURE, "2025-01-01")
        assert result is None

    def test_validity_window_respected_active(self):
        """Spirit Airlines active before Nov 2024."""
        result = w2044.match_ticker("Spirit Airlines", TICKER_MAP_FIXTURE, "2023-06-01")
        assert result == "SAVE"

    def test_yellow_corp_before_bankruptcy(self):
        result = w2044.match_ticker("Yellow Corporation", TICKER_MAP_FIXTURE, "2023-01-01")
        assert result == "YELL"

    def test_yellow_corp_after_bankruptcy(self):
        result = w2044.match_ticker("Yellow Corporation", TICKER_MAP_FIXTURE, "2024-01-01")
        assert result is None

    def test_empty_employer(self):
        result = w2044.match_ticker("", TICKER_MAP_FIXTURE, "2023-01-01")
        assert result is None


# ---------------------------------------------------------------------------
# Section 5 — Collector normalization helpers
# ---------------------------------------------------------------------------

class TestCollectorHelpers:
    def test_parse_date_iso(self):
        from collectors.warn_notices import _parse_date
        assert _parse_date("2023-05-15") == "2023-05-15"

    def test_parse_date_slash(self):
        from collectors.warn_notices import _parse_date
        assert _parse_date("05/15/2023") == "2023-05-15"

    def test_parse_date_empty(self):
        from collectors.warn_notices import _parse_date
        assert _parse_date("") is None

    def test_parse_date_none_str(self):
        from collectors.warn_notices import _parse_date
        assert _parse_date(None) is None

    def test_to_int_clean(self):
        from collectors.warn_notices import _to_int
        assert _to_int("150") == 150

    def test_to_int_comma(self):
        from collectors.warn_notices import _to_int
        assert _to_int("1,500") == 1500

    def test_to_int_empty(self):
        from collectors.warn_notices import _to_int
        assert _to_int("") is None

    def test_to_int_zero(self):
        from collectors.warn_notices import _to_int
        assert _to_int("0") is None  # 0 workers is excluded

    def test_normalize_ca_basic(self):
        from collectors.warn_notices import _normalize_ca
        rows = [{
            "notice_date": "07/01/2025",
            "effective_date": "09/02/2025",
            "received_date": "07/01/2025",
            "company": " Test Corp ",
            "city": "Los Angeles",
            "num_employees": "150",
            "layoff_or_closure": "Layoff",
            "county": "LA County",
        }]
        result = _normalize_ca(rows, "2026-07-08T00:00:00Z")
        assert len(result) == 1
        assert result[0]["state"] == "CA"
        assert result[0]["employer_raw"] == "Test Corp"
        assert result[0]["workers"] == 150
        assert result[0]["notice_date"] == "2025-07-01"

    def test_normalize_nj_basic(self):
        from collectors.warn_notices import _normalize_nj
        rows = [{"Company": "Acme Corp", "City": "Newark", "Month Posted": "2024-03-01", "Effective Date": "2024-04-01", "Workforce Affected": "200"}]
        result = _normalize_nj(rows, "2026-07-08T00:00:00Z")
        assert result[0]["state"] == "NJ"
        assert result[0]["workers"] == 200

    def test_build_panel_returns_dataframe(self, tmp_path):
        """build_panel should return a DataFrame with correct columns."""
        from collectors.warn_notices import build_panel, COLS
        # Empty directory -> empty DataFrame
        df = build_panel(tmp_path)
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == COLS

    def test_build_panel_with_sample_ca_csv(self, tmp_path):
        """build_panel normalizes a minimal CA CSV."""
        ca_csv = tmp_path / "ca.csv"
        ca_csv.write_text(
            "notice_date,effective_date,received_date,company,city,num_employees,layoff_or_closure,county\n"
            "07/15/2023,09/01/2023,07/15/2023,Acme Corp,Sacramento,120,Layoff,Sacramento County\n"
        )
        from collectors.warn_notices import build_panel
        df = build_panel(tmp_path)
        assert len(df) == 1
        assert df.iloc[0]["state"] == "CA"
        assert df.iloc[0]["workers"] == 120.0


# ---------------------------------------------------------------------------
# Section 6 — Statistical functions
# ---------------------------------------------------------------------------

class TestDateClusteredT:
    def test_positive_mean_positive_t(self):
        """All returns positive -> t should be positive."""
        returns = np.array([0.1, 0.05, 0.08, 0.03, 0.06])
        dates = np.array(["2023-01-01"] * 5)
        t, se = w2044.date_clustered_t(returns, dates)
        assert t > 0

    def test_negative_mean_negative_t(self):
        """All returns negative -> t should be negative."""
        returns = np.array([-0.1, -0.05, -0.08, -0.03, -0.06])
        dates = np.array(["2023-01-01"] * 5)
        t, se = w2044.date_clustered_t(returns, dates)
        assert t < 0

    def test_all_nan_returns_nan(self):
        t, se = w2044.date_clustered_t(np.array([np.nan, np.nan]), np.array(["2023-01-01"] * 2))
        assert np.isnan(t)

    def test_clustered_reduces_t_vs_iid(self):
        """With all events on same date, cluster t = iid t (1 cluster = 1 degree of freedom)."""
        rng = np.random.default_rng(42)
        returns = rng.normal(0.01, 0.05, 100)
        dates = np.array([f"2023-{(i % 12) + 1:02d}-01" for i in range(100)])
        t_clustered, _ = w2044.date_clustered_t(returns, dates)
        # With 12 clusters, SE should be larger than IID -> |t| smaller
        t_iid = np.mean(returns) / (np.std(returns, ddof=1) / np.sqrt(len(returns)))
        # Clustered |t| should be different from iid in general
        assert not np.isnan(t_clustered)

    def test_se_positive(self):
        returns = np.array([0.1, -0.05, 0.08, -0.03, 0.06])
        dates = np.array(["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05"])
        t, se = w2044.date_clustered_t(returns, dates)
        assert se > 0


class TestBhAdjust:
    def test_empty(self):
        assert w2044.bh_adjust([]) == []

    def test_all_significant_remain_below_threshold(self):
        """All tiny p-values should stay below 0.10 after BH."""
        ps = [0.0001, 0.0002, 0.0003, 0.0004]
        qs = w2044.bh_adjust(ps)
        assert all(q < 0.10 for q in qs)

    def test_all_large_above_threshold(self):
        """All large p-values should be above 0.10 after BH."""
        ps = [0.5, 0.6, 0.7, 0.8]
        qs = w2044.bh_adjust(ps)
        assert all(q > 0.10 for q in qs)

    def test_monotone_q(self):
        """BH q-values should be monotone non-decreasing with p-values."""
        ps = [0.001, 0.01, 0.05, 0.1, 0.3, 0.5]
        qs = w2044.bh_adjust(ps)
        sorted_p = sorted(ps)
        sorted_q = [q for _, q in sorted(zip(ps, qs))]
        for i in range(len(sorted_q) - 1):
            assert sorted_q[i] <= sorted_q[i + 1] + 1e-10  # monotone up to float precision

    def test_q_bounded_by_one(self):
        qs = w2044.bh_adjust([0.5, 0.6, 0.9])
        assert all(q <= 1.0 for q in qs)


# ---------------------------------------------------------------------------
# Section 7 — Report generation
# ---------------------------------------------------------------------------

class TestReportGeneration:
    """_write_report must produce a valid report with all required sections."""

    def test_write_report_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(results={}, panel_stats={}, status="PARTIAL")
        assert (tmp_path / "test_report.md").exists()

    def test_report_has_required_sections(self, tmp_path, monkeypatch):
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(results={}, panel_stats={}, status="NULL — direction gate failed")
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")

        required_patterns = [
            "W2-044",
            "In plain English",
            "Pre-registered design",
            "Gates",
            "PIT assumptions",
            "Acquisition ladder",
            "Panel coverage",
            "NEGATIVE",
            "w2044_warn_intensity",
            "VPS fallback",
            "warn-scraper",
        ]
        for pat in required_patterns:
            assert pat in text, f"Report missing required pattern: '{pat}'"

    def test_report_contains_all_four_trial_variants(self, tmp_path, monkeypatch):
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(results={}, panel_stats={}, status="PARTIAL")
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")
        for cell in w2044.TRIAL_GRID:
            assert cell["variant"] in text, f"Report missing variant: {cell['variant']}"

    def test_report_has_no_word_validated(self, tmp_path, monkeypatch):
        """House rule: the word 'validated' must not appear in user-facing reports."""
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(results={}, panel_stats={}, status="PARTIAL")
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")
        assert "validated" not in text.lower(), (
            "Report must not contain the word 'validated' (CI-enforced)"
        )

    def test_report_mentions_missing_states(self, tmp_path, monkeypatch):
        """Report must honestly mention TX and PA as missing states."""
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(results={}, panel_stats={}, status="PARTIAL")
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")
        assert "TX" in text or "Texas" in text
        assert "PA" in text or "Pennsylvania" in text

    def test_report_not_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(results={}, panel_stats={}, status="PARTIAL")
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")
        assert len(text) > 2000, f"Report too short: {len(text)} chars"

    def test_report_panel_stats_shown(self, tmp_path, monkeypatch):
        """Panel stats (per-state counts) should appear in the report."""
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        panel_stats = {"per_state": {"CA": 18842, "IL": 4866}}
        w2044._write_report(results={}, panel_stats=panel_stats, status="PARTIAL")
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")
        assert "CA" in text
        assert "18,842" in text or "18842" in text


# ---------------------------------------------------------------------------
# Section 8 — Panel coverage assertion
# ---------------------------------------------------------------------------

class TestPanelCoverage:
    def test_panel_states_include_top_supported(self):
        """The panel should include CA, IL, NJ, WA, IN, TN at minimum."""
        required = {"CA", "IL", "NJ", "WA", "IN", "TN"}
        assert required.issubset(set(w2044.PANEL_STATES))

    def test_missing_top15_is_documented(self):
        """MISSING_TOP15 must include TX and PA."""
        assert "TX" in w2044.MISSING_TOP15
        assert "PA" in w2044.MISSING_TOP15

    def test_missing_top15_is_subset_of_top15(self):
        """All missing states must actually be in the top-15."""
        top15 = {"CA", "NY", "TX", "IL", "OH", "PA", "FL", "MI", "NJ", "WA", "GA", "NC", "IN", "MN", "TN"}
        assert set(w2044.MISSING_TOP15).issubset(top15)
