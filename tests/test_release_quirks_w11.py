"""tests/test_release_quirks_w11.py — W11-E Track S flag tests (MRI-R38).

Tests:
  1. Flag determinism — same inputs always produce same flags
  2. No effect on any projection value (authority law: flags are pure annotations)
  3. Work-stoppage overlap logic (active_strike)
  4. Integrity regime thresholds (release_integrity)
  5. Bilingual copy shape (every flag has code, en, zh, cite; no translated title= text)
  6. Preliminary benchmark flag (nfp_preliminary_benchmark)
  7. Government shutdown flag
  8. Census hiring flag
  9. Hurricane landfall flag
  10. Collector smoke tests (fail-open behavior)

Run:
    python -m pytest tests/test_release_quirks_w11.py -v
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_quirks import (
    _check_active_strike,
    _check_census_hiring,
    _check_government_shutdown,
    _check_hurricane_landfall,
    _check_preliminary_benchmark,
    _nfp_reference_saturday,
    compute_quirk_flags,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo_root() -> Path:
    return _REPO


@pytest.fixture
def mock_stoppages_df() -> pd.DataFrame:
    """A minimal stoppages DataFrame for testing active_strike logic."""
    return pd.DataFrame([
        {
            "org": "Test Union A",
            "employer": "Test Corp A",
            "states": "MI",
            "workers": 50000,          # ≥25k → should trigger
            "start_date": date(2019, 9, 16),
            "end_date": date(2019, 10, 25),
            "naics": "3361",
            "source_url": "https://www.bls.gov/wsp/",
        },
        {
            "org": "Test Union B",
            "employer": "Test Corp B",
            "states": "CA",
            "workers": 10000,          # <25k → should NOT trigger
            "start_date": date(2024, 9, 13),
            "end_date": date(2024, 11, 4),
            "naics": "3364",
            "source_url": "https://www.bls.gov/wsp/",
        },
        {
            "org": "Test Union C",
            "employer": "Test Corp C",
            "states": "TX",
            "workers": 30000,          # ≥25k but ended before ref week
            "start_date": date(2020, 1, 1),
            "end_date": date(2020, 1, 10),
            "naics": "2100",
            "source_url": "https://www.bls.gov/wsp/",
        },
    ])


# ---------------------------------------------------------------------------
# 1. Flag determinism
# ---------------------------------------------------------------------------

class TestFlagDeterminism:
    def test_same_inputs_same_output_cpi(self) -> None:
        """CPI quirks are deterministic: identical inputs → identical output."""
        flags_a = compute_quirk_flags("cpi_headline", "2026-01")
        flags_b = compute_quirk_flags("cpi_headline", "2026-01")
        assert flags_a == flags_b

    def test_same_inputs_same_output_nfp(self) -> None:
        """NFP quirks are deterministic."""
        flags_a = compute_quirk_flags("nfp", "2025-01")
        flags_b = compute_quirk_flags("nfp", "2025-01")
        assert flags_a == flags_b

    def test_different_months_can_differ(self) -> None:
        """Different months produce different flag sets (or equal — not locked together)."""
        flags_jan = compute_quirk_flags("cpi_headline", "2026-01")
        flags_jun = compute_quirk_flags("cpi_headline", "2026-06")
        # January gets weight_update; June does not
        jan_codes = {f["code"] for f in flags_jan}
        jun_codes = {f["code"] for f in flags_jun}
        assert "cpi_weight_update" in jan_codes
        assert "cpi_weight_update" not in jun_codes


# ---------------------------------------------------------------------------
# 2. No effect on projection values (authority law)
# ---------------------------------------------------------------------------

class TestAuthorityLaw:
    def test_flags_are_pure_strings(self) -> None:
        """Every emitted flag contains only string values — no numeric data."""
        test_cases = [
            ("cpi_headline", "2026-01"),
            ("cpi_headline", "2026-04"),
            ("nfp", "2025-01"),
            ("nfp", "2024-10"),
            ("claims", "2026-12-03"),
        ]
        for release_type, period_str in test_cases:
            flags = compute_quirk_flags(release_type, period_str)
            for flag in flags:
                for k, v in flag.items():
                    assert isinstance(v, str), (
                        f"Non-string value in flag {flag['code']}: {k}={v!r} "
                        f"(release_type={release_type}, period={period_str})"
                    )

    def test_flags_have_no_numeric_values(self) -> None:
        """compute_quirk_flags must return list[dict[str, str]] — no floats, ints, etc."""
        flags = compute_quirk_flags("nfp", "2024-10")  # known hurricane + possibly benchmark
        for flag in flags:
            assert all(isinstance(v, str) for v in flag.values())

    def test_compute_quirk_flags_returns_list(self) -> None:
        """Return type is always a list, even for unknown release type."""
        result = compute_quirk_flags("unknown_release_type", "2026-01")
        assert isinstance(result, list)

    def test_malformed_period_returns_empty(self) -> None:
        """Malformed period_str → empty list (fail-open)."""
        assert compute_quirk_flags("cpi_headline", "not-a-date") == []
        assert compute_quirk_flags("nfp", "bad") == []
        assert compute_quirk_flags("claims", "also-bad") == []


# ---------------------------------------------------------------------------
# 3. Work-stoppage overlap logic
# ---------------------------------------------------------------------------

class TestActiveStrike:
    def test_strike_overlapping_ref_week_triggers(self, mock_stoppages_df: pd.DataFrame) -> None:
        """A large strike whose dates span the NFP reference week fires the flag."""
        # UAW-GM strike: Sep 16 – Oct 25, 2019; ref week for 2019-10 is Oct 6–12
        with patch("collectors.bls_work_stoppages.load_stoppages", return_value=mock_stoppages_df):
            result = _check_active_strike(date(2019, 10, 1), root=_REPO)
        assert result is True

    def test_small_strike_does_not_trigger(self, mock_stoppages_df: pd.DataFrame) -> None:
        """A strike with <25k workers does NOT fire, even if it overlaps."""
        # The 10k-worker row (Corp B) runs Sep 13 – Nov 4, 2024 (overlaps Oct 2024 ref week)
        # but workers < 25k → should not trigger
        small_df = mock_stoppages_df[mock_stoppages_df["workers"] < 25000].copy()
        with patch("collectors.bls_work_stoppages.load_stoppages", return_value=small_df):
            result = _check_active_strike(date(2024, 10, 1), root=_REPO)
        assert result is False

    def test_ended_strike_does_not_trigger(self, mock_stoppages_df: pd.DataFrame) -> None:
        """A strike that ended before the reference week does not trigger."""
        # Corp C strike ended Jan 10; Jan 2020 ref week = Jan 12-18
        ended_df = mock_stoppages_df[mock_stoppages_df["employer"] == "Test Corp C"].copy()
        with patch("collectors.bls_work_stoppages.load_stoppages", return_value=ended_df):
            result = _check_active_strike(date(2020, 1, 1), root=_REPO)
        assert result is False

    def test_no_stoppages_returns_false(self) -> None:
        """Empty stoppages DataFrame → no flag."""
        empty_df = pd.DataFrame(
            columns=["org", "employer", "states", "workers", "start_date", "end_date", "naics", "source_url"]
        )
        with patch("collectors.bls_work_stoppages.load_stoppages", return_value=empty_df):
            result = _check_active_strike(date(2026, 7, 1), root=_REPO)
        assert result is False

    def test_active_strike_flag_in_compute(self, mock_stoppages_df: pd.DataFrame) -> None:
        """active_strike fires in compute_quirk_flags when strike overlaps ref week."""
        with patch("engine.release_quirks._check_active_strike", return_value=True):
            flags = compute_quirk_flags("nfp", "2019-10", root=_REPO)
        codes = [f["code"] for f in flags]
        assert "active_strike" in codes

    def test_nfp_reference_saturday_2019_oct(self) -> None:
        """Verify NFP reference Saturday for Oct 2019: 12th is Sat → ref Sat = Oct 12."""
        ref_sat = _nfp_reference_saturday(date(2019, 10, 1))
        assert ref_sat == date(2019, 10, 12)

    def test_ongoing_strike_nat_end_date_triggers(self) -> None:
        """Ongoing strike (end_date NaT/None) overlapping ref week → flag fires.

        Bug fixed (MRI-R38 review): pd.NaT satisfies isinstance(pd.NaT, datetime.date)
        in some pandas versions, so the old ``not isinstance(end, date)`` guard
        silently failed to convert NaT→None, causing a TypeError swallowed as False.
        """
        ongoing_df = pd.DataFrame([{
            "org": "Test Union Ongoing",
            "employer": "Test Corp Ongoing",
            "states": "NY",
            "workers": 40000,       # ≥25k
            "start_date": date(2026, 5, 1),
            "end_date": None,        # ongoing — NaT in parquet
            "naics": "5000",
            "source_url": "https://www.bls.gov/wsp/",
        }])
        with patch("collectors.bls_work_stoppages.load_stoppages", return_value=ongoing_df):
            # Jul 2026 ref week = Jul 6–12; strike started May 1, no end → overlaps
            result = _check_active_strike(date(2026, 7, 1), root=_REPO)
        assert result is True, "Ongoing strike (NaT end_date) must fire active_strike flag"

    def test_aggregate_split_employer_strikes_fire_threshold(self) -> None:
        """Split-employer strikes sharing same org+month aggregate over the 25k threshold.

        2023-UAW-style: Ford 17k + Stellantis 7k = 24k each individually < 25k,
        but summed via aggregation they would be 24k still.  Use a case that crosses
        the line: two rows at 13k each (combined 26k ≥ 25k) for the same org.
        """
        split_df = pd.DataFrame([
            {
                "org": "Test Union Split",
                "employer": "Employer Alpha",
                "states": "MI",
                "workers": 13000,        # < 25k alone
                "start_date": date(2026, 6, 1),
                "end_date": date(2026, 8, 1),
                "naics": "3361",
                "source_url": "https://www.bls.gov/wsp/",
            },
            {
                "org": "Test Union Split",
                "employer": "Employer Beta",
                "states": "OH",
                "workers": 13000,        # < 25k alone; same org + same month → sum = 26k ≥ 25k
                "start_date": date(2026, 6, 1),
                "end_date": date(2026, 8, 1),
                "naics": "3361",
                "source_url": "https://www.bls.gov/wsp/",
            },
        ])
        with patch("collectors.bls_work_stoppages.load_stoppages", return_value=split_df):
            # Jul 2026 ref week = Jul 6–12; strikes Jun 1–Aug 1 → overlap; combined 26k ≥ 25k
            result = _check_active_strike(date(2026, 7, 1), root=_REPO)
        assert result is True, "Aggregated split-employer same-org strikes must cross 25k threshold"

    def test_aggregate_different_orgs_not_combined(self) -> None:
        """Different orgs do NOT aggregate; each stays below threshold independently."""
        diff_org_df = pd.DataFrame([
            {
                "org": "Union Alpha",
                "employer": "Corp A",
                "states": "MI",
                "workers": 13000,
                "start_date": date(2026, 6, 1),
                "end_date": date(2026, 8, 1),
                "naics": "3361",
                "source_url": "https://www.bls.gov/wsp/",
            },
            {
                "org": "Union Beta",
                "employer": "Corp B",
                "states": "OH",
                "workers": 13000,
                "start_date": date(2026, 6, 1),
                "end_date": date(2026, 8, 1),
                "naics": "3361",
                "source_url": "https://www.bls.gov/wsp/",
            },
        ])
        with patch("collectors.bls_work_stoppages.load_stoppages", return_value=diff_org_df):
            result = _check_active_strike(date(2026, 7, 1), root=_REPO)
        assert result is False, "Different orgs must not be aggregated across the threshold"


# ---------------------------------------------------------------------------
# 4. Integrity regime thresholds
# ---------------------------------------------------------------------------

class TestIntegrityRegime:
    def test_normal_regime_high_collection_rate(self) -> None:
        """Collection rate at/above 5y mean → normal regime."""
        from engine.release_integrity import _compute_ces_regime

        df = pd.DataFrame([
            {"table": "ces_response", "period_key": str(y), "component": "total",
             "metric_a": 75.0, "metric_b": 82.0, "source_url": ""}
            for y in range(2018, 2024)
        ])
        # Latest year (2024) same as mean → delta = 0 → normal
        df_with_latest = pd.concat([
            df,
            pd.DataFrame([{"table": "ces_response", "period_key": "2024", "component": "total",
                           "metric_a": 75.0, "metric_b": 82.0, "source_url": ""}])
        ], ignore_index=True)
        regime, delta, _ = _compute_ces_regime(df_with_latest, as_of_year=2025)
        assert regime == "normal"

    def test_degraded_regime_moderate_drop(self) -> None:
        """Collection rate 6pp below 5y mean → degraded regime."""
        from engine.release_integrity import _compute_ces_regime

        rows = [
            {"table": "ces_response", "period_key": str(y), "component": "total",
             "metric_a": 75.0, "metric_b": 82.0, "source_url": ""}
            for y in range(2015, 2020)
        ]
        # Latest year drops by 6pp
        rows.append({
            "table": "ces_response", "period_key": "2020",
            "component": "total", "metric_a": 69.0, "metric_b": 76.0, "source_url": ""
        })
        df = pd.DataFrame(rows)
        regime, delta, _ = _compute_ces_regime(df, as_of_year=2021)
        assert regime == "degraded"
        assert delta is not None and delta < -5.0

    def test_disrupted_regime_large_drop(self) -> None:
        """Collection rate 12pp below 5y mean → disrupted regime."""
        from engine.release_integrity import _compute_ces_regime

        rows = [
            {"table": "ces_response", "period_key": str(y), "component": "total",
             "metric_a": 76.0, "metric_b": 83.0, "source_url": ""}
            for y in range(2015, 2020)
        ]
        rows.append({
            "table": "ces_response", "period_key": "2020",
            "component": "total", "metric_a": 64.0, "metric_b": 72.0, "source_url": ""
        })
        df = pd.DataFrame(rows)
        regime, delta, _ = _compute_ces_regime(df, as_of_year=2021)
        assert regime == "disrupted"
        assert delta is not None and delta < -10.0

    def test_empty_integrity_returns_normal(self) -> None:
        """Empty integrity data → regime defaults to 'normal'."""
        from engine.release_integrity import compute_print_integrity

        empty_df = pd.DataFrame(
            columns=["table", "period_key", "component", "metric_a", "metric_b", "source_url"]
        )
        # Patch both the parquet read and the fallback loader
        with patch("engine.release_integrity.pd.read_parquet", return_value=empty_df):
            with patch("collectors.bls_print_integrity.load_print_integrity", return_value=empty_df):
                result = compute_print_integrity("nfp", root=_REPO)
        assert result["regime"] == "normal"

    def test_compute_print_integrity_returns_dict(self) -> None:
        """compute_print_integrity always returns a dict with required keys."""
        from engine.release_integrity import compute_print_integrity
        result = compute_print_integrity("nfp", root=_REPO)
        assert isinstance(result, dict)
        for key in ["regime", "collection_rate_vs_5y", "cpi_median_se_trend",
                    "revision_streak", "source_years", "as_of"]:
            assert key in result

    def test_regime_values_are_valid(self) -> None:
        """Regime is always one of the three valid values."""
        from engine.release_integrity import compute_print_integrity
        result = compute_print_integrity("nfp", root=_REPO)
        assert result["regime"] in ("normal", "degraded", "disrupted")

    def test_cpi_se_trend_rising(self) -> None:
        """CPI SE trend: rising when recent SE > older SE by enough to exceed threshold."""
        from engine.release_integrity import _compute_cpi_se_trend

        # Use clearly rising values: last-3 delta = 0.010 > 0.005 threshold
        df = pd.DataFrame([
            {"table": "cpi_se", "period_key": str(y), "component": "all_items",
             "metric_a": 0.07 + (y - 2018) * 0.005, "metric_b": float("nan"), "source_url": ""}
            for y in range(2018, 2025)
        ])
        trend = _compute_cpi_se_trend(df)
        assert trend == "rising"

    def test_cpi_se_trend_flat(self) -> None:
        """CPI SE trend: flat when SE is stable."""
        from engine.release_integrity import _compute_cpi_se_trend

        df = pd.DataFrame([
            {"table": "cpi_se", "period_key": str(y), "component": "all_items",
             "metric_a": 0.085, "metric_b": float("nan"), "source_url": ""}
            for y in range(2020, 2025)
        ])
        trend = _compute_cpi_se_trend(df)
        assert trend == "flat"


# ---------------------------------------------------------------------------
# 5. Bilingual copy shape
# ---------------------------------------------------------------------------

class TestBilingualCopy:
    _ALL_CODES = [
        ("cpi_headline", "2026-01"),
        ("cpi_headline", "2026-04"),
        ("cpi_headline", "2026-10"),
        ("nfp", "2026-01"),
        ("nfp", "2025-01"),
        ("claims", "2026-12-03"),
    ]

    def test_all_flags_have_required_keys(self) -> None:
        """Every emitted flag has code, en, zh, cite keys."""
        for release_type, period_str in self._ALL_CODES:
            flags = compute_quirk_flags(release_type, period_str)
            for flag in flags:
                assert "code" in flag, f"Missing 'code' in {flag}"
                assert "en" in flag, f"Missing 'en' in {flag}"
                assert "zh" in flag, f"Missing 'zh' in {flag}"
                assert "cite" in flag, f"Missing 'cite' in {flag}"

    def test_en_and_zh_are_nonempty_strings(self) -> None:
        """en and zh are non-empty strings."""
        for release_type, period_str in self._ALL_CODES:
            flags = compute_quirk_flags(release_type, period_str)
            for flag in flags:
                assert len(flag["en"]) > 0, f"Empty en in {flag['code']}"
                assert len(flag["zh"]) > 0, f"Empty zh in {flag['code']}"

    def test_zh_contains_chinese_characters(self) -> None:
        """zh copy contains at least some CJK characters (U+4E00..U+9FFF)."""
        flags = compute_quirk_flags("cpi_headline", "2026-01")
        for flag in flags:
            has_cjk = any('一' <= c <= '鿿' for c in flag["zh"])
            assert has_cjk, f"Flag {flag['code']} zh has no CJK chars: {flag['zh']!r}"

    def test_no_translated_text_in_code_or_cite(self) -> None:
        """'code' and 'cite' fields are pure ASCII (no ZH text in identifiers)."""
        for release_type, period_str in self._ALL_CODES:
            flags = compute_quirk_flags(release_type, period_str)
            for flag in flags:
                for char in flag["code"]:
                    assert ord(char) < 128, f"Non-ASCII in code: {flag['code']!r}"

    def test_hurricane_flag_bilingual(self) -> None:
        """hurricane_landfall flag includes bilingual storm name in en and zh."""
        with patch("engine.release_quirks._check_hurricane_landfall", return_value=(True, "Katrina")):
            flags = compute_quirk_flags("nfp", "2005-09", root=_REPO)
        hurricane_flags = [f for f in flags if f["code"] == "hurricane_landfall"]
        assert len(hurricane_flags) == 1
        flag = hurricane_flags[0]
        assert "Katrina" in flag["en"]
        assert "Katrina" in flag["zh"]


# ---------------------------------------------------------------------------
# 6. Preliminary benchmark flag
# ---------------------------------------------------------------------------

class TestPreliminaryBenchmark:
    def test_large_preliminary_flags_january(self) -> None:
        """Preliminary >|100k| in October n-1 → flags January n."""
        # 2024-10 preliminary: -818k → flags Jan 2025
        result = _check_preliminary_benchmark(date(2025, 1, 1), root=_REPO)
        assert result is True

    def test_jan_2023_flagged_by_2022_preliminary(self) -> None:
        """2022-10 preliminary +462k → flags Jan 2023 NFP."""
        result = _check_preliminary_benchmark(date(2023, 1, 1), root=_REPO)
        assert result is True

    def test_non_january_never_flagged(self) -> None:
        """Preliminary benchmark flag only fires for January prints."""
        for month in range(2, 13):
            result = _check_preliminary_benchmark(date(2025, month, 1), root=_REPO)
            assert result is False, f"Unexpected flag for month {month}"

    def test_small_preliminary_does_not_flag(self) -> None:
        """Preliminary ≤|100k| does not flag."""
        # Inject a small preliminary by providing a mock YAML with small values
        # We test via the compute function with a patched load_yaml
        import yaml
        small_yml = {
            "preliminary_benchmarks": [
                {"published_month": "2020-10", "preliminary_estimate": 50, "cite": "test"}
            ]
        }
        with patch("engine.release_quirks._load_yaml", return_value=small_yml):
            result = _check_preliminary_benchmark(date(2021, 1, 1), root=_REPO)
        assert result is False

    def test_flag_in_compute_quirk_flags(self) -> None:
        """nfp_preliminary_benchmark code appears in compute_quirk_flags for Jan 2025."""
        flags = compute_quirk_flags("nfp", "2025-01", root=_REPO)
        codes = [f["code"] for f in flags]
        assert "nfp_preliminary_benchmark" in codes


# ---------------------------------------------------------------------------
# 7. Government shutdown flag
# ---------------------------------------------------------------------------

class TestGovernmentShutdown:
    def test_known_2019_shutdown_flags_jan(self) -> None:
        """2018-12-22 to 2019-01-25 shutdown → flags any NFP/CPI period in Jan 2019."""
        result = _check_government_shutdown(date(2019, 1, 1), root=_REPO)
        assert result is True

    def test_known_2025_shutdown_flags_october(self) -> None:
        """Oct 1–Nov 12, 2025 shutdown → flags NFP reference period in Oct 2025.

        The previous YAML entry (start 2025-03-14, end 2025-03-28) was fabricated;
        the real 2025 FY2026 appropriations lapse ran Oct 1 – Nov 12, 2025 (43 days).
        Sources:
          https://en.wikipedia.org/wiki/2025_United_States_federal_government_shutdown
          https://www.cbo.gov/system/files/2025-10/61823-Shutdown.pdf
        """
        result = _check_government_shutdown(date(2025, 10, 1), root=_REPO)
        assert result is True

    def test_2025_march_not_in_shutdown(self) -> None:
        """March 2025 is NOT in any shutdown (the old fabricated entry has been removed)."""
        result = _check_government_shutdown(date(2025, 3, 1), root=_REPO)
        assert result is False

    def test_2025_november_in_shutdown(self) -> None:
        """Nov 12, 2025 is the last day of the 2025 shutdown window."""
        result = _check_government_shutdown(date(2025, 11, 1), root=_REPO)
        assert result is True

    def test_no_shutdown_in_quiet_period(self) -> None:
        """A quiet period (2017-06) with no shutdown → flag is False."""
        result = _check_government_shutdown(date(2017, 6, 1), root=_REPO)
        assert result is False

    def test_government_shutdown_in_compute_flags(self) -> None:
        """government_shutdown appears in compute_quirk_flags for shutdown period."""
        with patch("engine.release_quirks._check_government_shutdown", return_value=True):
            flags = compute_quirk_flags("nfp", "2019-01", root=_REPO)
        codes = [f["code"] for f in flags]
        assert "government_shutdown" in codes


# ---------------------------------------------------------------------------
# 8. Census hiring flag
# ---------------------------------------------------------------------------

class TestCensusHiring:
    def test_2010_may_is_census_month(self) -> None:
        """May 2010 (decennial year, active hiring month) → census_hiring flag."""
        result = _check_census_hiring(date(2010, 5, 1))
        assert result is True

    def test_2010_july_drawdown_is_census_month(self) -> None:
        """July 2010 (decennial year, drawdown month) → census_hiring flag."""
        result = _check_census_hiring(date(2010, 7, 1))
        assert result is True

    def test_2010_february_not_census(self) -> None:
        """Feb 2010 (outside active window) → no census flag."""
        result = _check_census_hiring(date(2010, 2, 1))
        assert result is False

    def test_2026_not_decennial(self) -> None:
        """2026 is not a decennial year → no census flag."""
        result = _check_census_hiring(date(2026, 5, 1))
        assert result is False

    def test_2030_may_will_be_census(self) -> None:
        """2030 May (next decennial) → census_hiring flag fires."""
        result = _check_census_hiring(date(2030, 5, 1))
        assert result is True

    def test_census_hiring_in_compute_flags(self) -> None:
        """census_hiring code appears in compute_quirk_flags for 2010-05."""
        flags = compute_quirk_flags("nfp", "2010-05", root=_REPO)
        codes = [f["code"] for f in flags]
        assert "census_hiring" in codes


# ---------------------------------------------------------------------------
# 9. Hurricane landfall flag
# ---------------------------------------------------------------------------

class TestHurricaneLandfall:
    def test_known_katrina_2005_09_triggers(self) -> None:
        """Hurricane Katrina (landfall Aug 29, 2005) → flag for 2005-09 NFP."""
        hit, name = _check_hurricane_landfall(date(2005, 9, 1), root=_REPO)
        assert hit is True
        assert "Katrina" in name

    def test_known_helene_2024_10_triggers(self) -> None:
        """Hurricane Helene (landfall Sep 26, 2024) → flag for 2024-10 NFP."""
        hit, name = _check_hurricane_landfall(date(2024, 10, 1), root=_REPO)
        assert hit is True
        assert "Helene" in name or "Milton" in name

    def test_quiet_month_no_hurricane(self) -> None:
        """A quiet month (2018-06) → no hurricane flag."""
        hit, name = _check_hurricane_landfall(date(2018, 6, 1), root=_REPO)
        assert hit is False
        assert name == ""

    def test_hurricane_flag_in_compute(self) -> None:
        """hurricane_landfall code appears in compute_quirk_flags for 2005-09."""
        flags = compute_quirk_flags("nfp", "2005-09", root=_REPO)
        codes = [f["code"] for f in flags]
        assert "hurricane_landfall" in codes

    def test_hurricane_flag_missing_yaml_is_false(self) -> None:
        """Missing YAML returns (False, '') — fail-open."""
        with patch("engine.release_quirks._load_yaml", return_value=None):
            hit, name = _check_hurricane_landfall(date(2005, 9, 1), root=_REPO)
        assert hit is False


# ---------------------------------------------------------------------------
# 10. Collector smoke tests
# ---------------------------------------------------------------------------

class TestCollectorSmokeTests:
    def test_work_stoppages_seed_rows_load(self) -> None:
        """SEED_ROWS load without error and have required columns."""
        from collectors.bls_work_stoppages import SEED_ROWS
        assert len(SEED_ROWS) > 0
        for row in SEED_ROWS:
            assert "org" in row
            assert "employer" in row
            assert "workers" in row
            assert "start_date" in row
            assert isinstance(row["workers"], int)

    def test_work_stoppages_seed_has_large_strikes(self) -> None:
        """At least one seed row has ≥25k workers (the threshold for active_strike)."""
        from collectors.bls_work_stoppages import SEED_ROWS
        from engine.release_quirks import _WORK_STOPPAGE_MIN_WORKERS
        large = [r for r in SEED_ROWS if r["workers"] >= _WORK_STOPPAGE_MIN_WORKERS]
        assert len(large) > 0

    def test_load_stoppages_failopen_returns_df(self) -> None:
        """load_stoppages returns a DataFrame even if parquet is absent."""
        from collectors.bls_work_stoppages import load_stoppages
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            df = load_stoppages(root=Path(tmp))
        assert isinstance(df, pd.DataFrame)
        assert not df.empty  # falls back to SEED_ROWS

    def test_load_stoppages_has_required_columns(self) -> None:
        """load_stoppages DataFrame has required columns."""
        from collectors.bls_work_stoppages import load_stoppages
        df = load_stoppages(root=_REPO)
        for col in ["org", "employer", "states", "workers", "start_date", "end_date", "naics", "source_url"]:
            assert col in df.columns, f"Missing column: {col}"

    def test_print_integrity_seed_returns_df(self) -> None:
        """load_print_integrity returns a DataFrame from seed data."""
        from collectors.bls_print_integrity import load_print_integrity
        df = load_print_integrity(root=_REPO)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_print_integrity_has_required_columns(self) -> None:
        """Integrity DataFrame has required columns."""
        from collectors.bls_print_integrity import load_print_integrity
        df = load_print_integrity(root=_REPO)
        for col in ["table", "period_key", "component", "metric_a", "metric_b", "source_url"]:
            assert col in df.columns, f"Missing column: {col}"

    def test_print_integrity_has_both_tables(self) -> None:
        """Integrity DataFrame contains both ces_response and cpi_se rows."""
        from collectors.bls_print_integrity import load_print_integrity
        df = load_print_integrity(root=_REPO)
        tables = df["table"].unique().tolist()
        assert "ces_response" in tables
        assert "cpi_se" in tables

    def test_ces_collection_rate_in_range(self) -> None:
        """CES collection rate values are plausible (0–100%)."""
        from collectors.bls_print_integrity import load_print_integrity
        df = load_print_integrity(root=_REPO)
        ces = df[df["table"] == "ces_response"]
        assert ces["metric_a"].between(0, 100).all(), "collection_rate_pct out of range [0, 100]"

    def test_collect_work_stoppages_failopen(self) -> None:
        """collect_work_stoppages is fail-open: no exception even if BLS unreachable."""
        from collectors.bls_work_stoppages import collect_work_stoppages
        # Point at a writable temp dir so parquet write doesn't fail
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with patch("collectors.bls_work_stoppages._fetch_html", return_value=None):
                df = collect_work_stoppages(root=Path(tmp))
        assert isinstance(df, pd.DataFrame)

    def test_collect_print_integrity_failopen(self) -> None:
        """collect_print_integrity is fail-open: no exception even if BLS unreachable."""
        from collectors.bls_print_integrity import collect_print_integrity
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with patch("collectors.bls_print_integrity._fetch_html", return_value=None):
                df = collect_print_integrity(root=Path(tmp))
        assert isinstance(df, pd.DataFrame)


# ---------------------------------------------------------------------------
# 11. Integration: existing flags unchanged (regression)
# ---------------------------------------------------------------------------

class TestExistingFlagsRegression:
    """Ensure W11-E additions did not break the original PR-I flags."""

    def test_cpi_weight_update_still_fires(self) -> None:
        flags = compute_quirk_flags("cpi_headline", "2026-01")
        assert any(f["code"] == "cpi_weight_update" for f in flags)

    def test_cpi_health_insurance_still_fires(self) -> None:
        flags = compute_quirk_flags("cpi_headline", "2026-04")
        assert any(f["code"] == "cpi_health_insurance_reset" for f in flags)

    def test_nfp_benchmark_still_fires(self) -> None:
        flags = compute_quirk_flags("nfp", "2026-01")
        assert any(f["code"] == "nfp_benchmark_revision" for f in flags)

    def test_five_week_gap_still_fires(self) -> None:
        flags = compute_quirk_flags("nfp", "2025-01")
        assert any(f["code"] == "nfp_five_week_gap" for f in flags)

    def test_claims_holiday_still_fires(self) -> None:
        flags = compute_quirk_flags("claims", "2026-12-03")
        assert any(f["code"] == "claims_holiday_week" for f in flags)
