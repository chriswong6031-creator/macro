"""tests/test_release_quirks.py — TestQuirkFlags for MRI-R20.

Ported from closed PR #1884 (claude/mri-pr-i:tests/test_mri_pr_i.py),
TestQuirkFlags class only.  All other test classes in that file are
superseded by #1883's own tests (tests/test_release_market_context.py).

Run:
    python -m pytest tests/test_release_quirks.py -v
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_quirks import (
    _nfp_five_week_gap,
    _thanksgiving,
    compute_quirk_flags,
)


class TestQuirkFlags:
    def test_cpi_january_gets_weight_update_flag(self) -> None:
        """January CPI print → cpi_weight_update flag."""
        flags = compute_quirk_flags("cpi_headline", "2026-01")
        codes = [f["code"] for f in flags]
        assert "cpi_weight_update" in codes

    def test_cpi_non_january_no_weight_update(self) -> None:
        """Non-January CPI → no cpi_weight_update."""
        flags = compute_quirk_flags("cpi_headline", "2026-03")
        codes = [f["code"] for f in flags]
        assert "cpi_weight_update" not in codes

    def test_cpi_april_health_insurance(self) -> None:
        """April CPI (since Oct 2023) → cpi_health_insurance_reset."""
        flags = compute_quirk_flags("cpi_headline", "2026-04")
        codes = [f["code"] for f in flags]
        assert "cpi_health_insurance_reset" in codes

    def test_cpi_october_health_insurance(self) -> None:
        """October CPI (since Oct 2023) → cpi_health_insurance_reset."""
        flags = compute_quirk_flags("cpi_headline", "2026-10")
        codes = [f["code"] for f in flags]
        assert "cpi_health_insurance_reset" in codes

    def test_cpi_health_insurance_not_before_oct_2023(self) -> None:
        """April 2023 (before the semiannual reset landed) → no health_insurance flag."""
        flags = compute_quirk_flags("cpi_headline", "2023-04")
        codes = [f["code"] for f in flags]
        assert "cpi_health_insurance_reset" not in codes

    def test_cpi_june_no_health_insurance(self) -> None:
        """Non-Apr/Oct month → no health_insurance flag."""
        flags = compute_quirk_flags("cpi_headline", "2026-06")
        codes = [f["code"] for f in flags]
        assert "cpi_health_insurance_reset" not in codes

    def test_nfp_january_benchmark_revision(self) -> None:
        """January NFP → nfp_benchmark_revision."""
        flags = compute_quirk_flags("nfp", "2026-01")
        codes = [f["code"] for f in flags]
        assert "nfp_benchmark_revision" in codes

    def test_nfp_non_january_no_benchmark_revision(self) -> None:
        """Non-January NFP → no benchmark revision flag."""
        flags = compute_quirk_flags("nfp", "2026-06")
        codes = [f["code"] for f in flags]
        assert "nfp_benchmark_revision" not in codes

    def test_nfp_five_week_gap_known_month(self) -> None:
        """A known 5-week-gap month → nfp_five_week_gap flag.

        Example: January 2025 (ref Sat Jan 18; Dec 2024 ref Sat Dec 14 → 35 days).
        """
        # Verify the 5-week gap computation first
        jan_2025 = date(2025, 1, 1)
        assert _nfp_five_week_gap(jan_2025)
        flags = compute_quirk_flags("nfp", "2025-01")
        codes = [f["code"] for f in flags]
        assert "nfp_five_week_gap" in codes

    def test_nfp_typical_month_no_five_week_gap(self) -> None:
        """A typical 4-week-gap month → no five_week_gap flag."""
        # June 2026 ref Sat: 12th = Fri, so ref Sat = June 13; May ref Sat: 12th = Tue,
        # so ref Sat = May 16. Gap = June 13 - May 16 = 28 days = 4 weeks.
        assert not _nfp_five_week_gap(date(2026, 6, 1))
        flags = compute_quirk_flags("nfp", "2026-06")
        codes = [f["code"] for f in flags]
        assert "nfp_five_week_gap" not in codes

    def test_claims_thanksgiving_week(self) -> None:
        """Claims week near Thanksgiving → claims_holiday_week.

        Thanksgiving 2026 = Nov 26. A Thursday of Nov 26 would mean period_end
        = Nov 26 - 5 = Nov 21 (Saturday). |Nov 21 - Nov 26| = 5 > 3, so not triggered.
        Use the Thursday AFTER Thanksgiving: Dec 3. period_end = Nov 28 (Saturday).
        |Nov 28 - Nov 26| = 2 <= 3 → triggered.
        """
        # Dec 3, 2026 Thursday
        flags = compute_quirk_flags("claims", "2026-12-03")
        codes = [f["code"] for f in flags]
        assert "claims_holiday_week" in codes

    def test_claims_christmas_week(self) -> None:
        """Claims week near Christmas (Dec 25) → claims_holiday_week.

        Thursday Dec 25, 2025: period_end = Dec 20. |Dec 20 - Dec 25| = 5 > 3 → not triggered.
        Thursday Jan 1, 2026: period_end = Dec 27. |Dec 27 - Dec 25| = 2 → triggered.
        """
        flags = compute_quirk_flags("claims", "2026-01-01")
        codes = [f["code"] for f in flags]
        assert "claims_holiday_week" in codes

    def test_claims_new_years_week(self) -> None:
        """Claims week near New Year's Day → claims_holiday_week.

        Thursday Jan 2, 2025: period_end = Dec 28, 2024. |Dec 28 - Jan 1| = 4 > 3 → not triggered.
        Thursday Jan 2, 2025 has period_end Dec 28 so check |Dec 28 - Jan 1 2025| = 4, not triggered.
        But Thursday Dec 26, 2024: period_end Dec 21. |Dec 21 - Dec 25| = 4, not triggered.
        Try Thursday Jan 3, 2019: period_end Dec 29. |Dec 29 - Jan 1 2019| = 3 → triggered.
        """
        flags = compute_quirk_flags("claims", "2019-01-03")
        codes = [f["code"] for f in flags]
        assert "claims_holiday_week" in codes

    def test_claims_normal_week_no_flags(self) -> None:
        """A mid-quarter claims week with no holiday → no quirk flags."""
        flags = compute_quirk_flags("claims", "2026-07-16")  # mid-July Thursday
        codes = [f["code"] for f in flags]
        assert "claims_holiday_week" not in codes

    def test_all_flags_have_required_keys(self) -> None:
        """Every emitted flag has code, en, zh, cite."""
        jan_flags = compute_quirk_flags("cpi_headline", "2026-01")
        for flag in jan_flags:
            assert "code" in flag and "en" in flag and "zh" in flag and "cite" in flag

    def test_flags_never_alter_point(self) -> None:
        """compute_quirk_flags returns only annotation list, no numeric data."""
        flags = compute_quirk_flags("cpi_headline", "2026-01")
        for flag in flags:
            # No numeric values in the flag dict (pure annotation)
            for k, v in flag.items():
                assert isinstance(v, str), f"non-string value in flag dict: {k}={v!r}"

    def test_cpi_core_same_quirks_as_headline(self) -> None:
        """cpi_core triggers same CPI quirk flags as cpi_headline."""
        hl = compute_quirk_flags("cpi_headline", "2026-01")
        core = compute_quirk_flags("cpi_core", "2026-01")
        assert [f["code"] for f in hl] == [f["code"] for f in core]

    def test_malformed_period_returns_empty(self) -> None:
        """Malformed period_str → empty list (fail-open)."""
        flags = compute_quirk_flags("cpi_headline", "not-a-date")
        assert flags == []

    def test_thanksgiving_helper(self) -> None:
        """Verify Thanksgiving helper for known years."""
        assert _thanksgiving(2026) == date(2026, 11, 26)  # 4th Thursday of Nov 2026
        assert _thanksgiving(2024) == date(2024, 11, 28)  # known 2024 Thanksgiving
