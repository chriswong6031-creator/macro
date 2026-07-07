"""MRI PR-I — tests for market-implied join, surprise distribution,
sensitivity chip, quirk flags, ledger additive fields, scoreboard gating.

Run:
    python -m pytest tests/test_mri_pr_i.py -v

All tests use synthetic data / tmp directories. No real parquet files required.
No real network calls. No committed data artifacts written.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    """Minimal repo-shaped temp root."""
    (tmp_path / "data" / "release_forecast").mkdir(parents=True)
    (tmp_path / "data" / "prediction_markets").mkdir(parents=True)
    (tmp_path / "data" / "cleveland_nowcast").mkdir(parents=True)
    (tmp_path / "data" / "regime").mkdir(parents=True)
    (tmp_path / "data" / "fred_vintage").mkdir(parents=True)
    (tmp_path / "site" / "macrodata").mkdir(parents=True)
    return tmp_path


def _make_kalshi_parquet(root: Path, rows: list[dict]) -> None:
    """Write a synthetic kalshi_releases.parquet."""
    df = pd.DataFrame(rows)
    path = root / "data" / "prediction_markets" / "kalshi_releases.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


# ---------------------------------------------------------------------------
# 1. Kalshi parquet join (_read_market_implied)
# ---------------------------------------------------------------------------

from scripts.build_release_forecast import _read_market_implied

TODAY = date(2026, 7, 7)


def _summary_row(
    asof_date: str,
    release_type: str,
    period: str,
    implied_median: float | None,
) -> dict:
    return {
        "asof_date": asof_date,
        "release_type": release_type,
        "period": period,
        "strike": float("nan"),
        "p_survival": None,
        "price_type": "summary",
        "is_summary": True,
        "implied_median": implied_median,
        "p_above_lowest_strike": 0.7,
        "monotonicity_corrected": False,
        "n_brackets": 5,
        "event_ticker": "KXCPI-26JUN",
        "close_time": None,
    }


class TestReadMarketImplied:
    def test_cpi_headline_present(self, tmp_root: Path) -> None:
        """CPI headline: matching summary row → returns value as-is (pct_mom)."""
        _make_kalshi_parquet(tmp_root, [
            _summary_row("2026-07-06", "cpi", "2026-06", 0.30),
        ])
        val = _read_market_implied(tmp_root, "cpi_headline", "2026-06", TODAY)
        assert val == pytest.approx(0.30, abs=1e-6)

    def test_cpi_core_always_none(self, tmp_root: Path) -> None:
        """cpi_core has no Kalshi market → always None, even if file present."""
        _make_kalshi_parquet(tmp_root, [
            _summary_row("2026-07-06", "cpi", "2026-06", 0.30),
        ])
        val = _read_market_implied(tmp_root, "cpi_core", "2026-06", TODAY)
        assert val is None

    def test_absent_file(self, tmp_root: Path) -> None:
        """No parquet file → None (fail-open)."""
        val = _read_market_implied(tmp_root, "cpi_headline", "2026-06", TODAY)
        assert val is None

    def test_no_matching_row(self, tmp_root: Path) -> None:
        """Parquet present but no row for this (release_type, period) → None."""
        _make_kalshi_parquet(tmp_root, [
            _summary_row("2026-07-06", "cpi", "2026-05", 0.25),  # different period
        ])
        val = _read_market_implied(tmp_root, "cpi_headline", "2026-06", TODAY)
        assert val is None

    def test_null_implied_median(self, tmp_root: Path) -> None:
        """Summary row present but implied_median is None → None."""
        _make_kalshi_parquet(tmp_root, [
            _summary_row("2026-07-06", "cpi", "2026-06", None),
        ])
        val = _read_market_implied(tmp_root, "cpi_headline", "2026-06", TODAY)
        assert val is None

    def test_stale_period_not_returned(self, tmp_root: Path) -> None:
        """Summary row asof_date > today → not returned (PIT-safe)."""
        _make_kalshi_parquet(tmp_root, [
            _summary_row("2026-07-08", "cpi", "2026-06", 0.35),  # future
        ])
        val = _read_market_implied(tmp_root, "cpi_headline", "2026-06", TODAY)
        assert val is None

    def test_latest_row_selected(self, tmp_root: Path) -> None:
        """Multiple rows → latest asof_date <= today is selected."""
        _make_kalshi_parquet(tmp_root, [
            _summary_row("2026-07-05", "cpi", "2026-06", 0.28),
            _summary_row("2026-07-06", "cpi", "2026-06", 0.31),
        ])
        val = _read_market_implied(tmp_root, "cpi_headline", "2026-06", TODAY)
        assert val == pytest.approx(0.31, abs=1e-6)

    def test_nfp_normalized_to_thousands(self, tmp_root: Path) -> None:
        """NFP: implied_median in raw job count (e.g. 180000) → normalized to 180.0k."""
        _make_kalshi_parquet(tmp_root, [
            _summary_row("2026-07-06", "nfp", "2026-06", 180000.0),
        ])
        val = _read_market_implied(tmp_root, "nfp", "2026-06", TODAY)
        # 180000 / 1000 = 180.0
        assert val == pytest.approx(180.0, abs=1e-4)

    def test_claims_normalized_to_thousands(self, tmp_root: Path) -> None:
        """Claims: implied_median in raw count (e.g. 220000) → normalized to 220.0k."""
        _make_kalshi_parquet(tmp_root, [
            _summary_row("2026-07-06", "claims", "2026-07-05", 220000.0),
        ])
        val = _read_market_implied(tmp_root, "claims", "2026-07-05", TODAY)
        assert val == pytest.approx(220.0, abs=1e-4)

    def test_cpi_not_divided(self, tmp_root: Path) -> None:
        """CPI: implied_median is in pct MoM → NOT divided by 1000."""
        _make_kalshi_parquet(tmp_root, [
            _summary_row("2026-07-06", "cpi", "2026-06", 0.30),
        ])
        val = _read_market_implied(tmp_root, "cpi_headline", "2026-06", TODAY)
        # Must not be 0.0003 (i.e. not divided)
        assert val is not None and val > 0.1


# ---------------------------------------------------------------------------
# 2. Surprise distribution (_compute_surprise_distribution)
# ---------------------------------------------------------------------------

from scripts.build_release_forecast import _compute_surprise_distribution


class TestSurpriseDistribution:
    def _make_residuals(self, n: int = 30) -> list[float]:
        """Symmetric residuals around 0, std≈1."""
        rng = np.random.default_rng(42)
        return rng.standard_normal(n).tolist()

    def test_returns_three_probs(self) -> None:
        """p_hot, p_cold, p_inline are all present and non-negative."""
        res = self._make_residuals(30)
        bs = {"naive_prior": 0.30, "trailing_3m": 0.28, "ar_model": 0.29}
        out = _compute_surprise_distribution(0.32, bs, res)
        assert out is not None
        assert "p_hot" in out and "p_cold" in out and "p_inline" in out
        assert out["p_hot"] >= 0
        assert out["p_cold"] >= 0
        assert out["p_inline"] >= 0

    def test_probs_sum_to_one(self) -> None:
        """p_hot + p_cold + p_inline == 1.0 (within rounding tolerance)."""
        res = self._make_residuals(40)
        bs = {"naive_prior": 0.30, "trailing_3m": 0.28, "ar_model": 0.29}
        out = _compute_surprise_distribution(0.32, bs, res)
        assert out is not None
        total = round(out["p_hot"] + out["p_cold"] + out["p_inline"], 1)
        assert total == pytest.approx(1.0, abs=0.05)

    def test_suppressed_for_none_point(self) -> None:
        """benchmark_only or projection failed (point=None) → None."""
        res = self._make_residuals(30)
        bs = {"naive_prior": 0.30}
        assert _compute_surprise_distribution(None, bs, res) is None

    def test_suppressed_for_too_few_residuals(self) -> None:
        """Fewer than 24 residuals → None."""
        res = self._make_residuals(10)
        bs = {"naive_prior": 0.30}
        assert _compute_surprise_distribution(0.30, bs, res) is None

    def test_suppressed_for_no_residuals(self) -> None:
        """No residuals → None."""
        bs = {"naive_prior": 0.30}
        assert _compute_surprise_distribution(0.30, bs, None) is None

    def test_suppressed_for_all_null_benchmarks(self) -> None:
        """All benchmark values null → None (no bench_median)."""
        res = self._make_residuals(30)
        bs = {"naive_prior": None, "trailing_3m": None}
        assert _compute_surprise_distribution(0.30, bs, res) is None

    def test_determinism(self) -> None:
        """Same inputs → same outputs."""
        rng = np.random.default_rng(99)
        res = rng.standard_normal(30).tolist()
        bs = {"naive_prior": 0.25}
        out1 = _compute_surprise_distribution(0.30, bs, res)
        out2 = _compute_surprise_distribution(0.30, bs, res)
        assert out1 == out2

    def test_hot_dominant_when_point_much_above_benchmark(self) -> None:
        """When point is far above benchmark_median, p_hot should dominate."""
        # Residuals centered around 0
        res = np.zeros(40).tolist()  # zero residuals → all mass at point
        # Gaussian residuals with small std
        rng = np.random.default_rng(7)
        res = (rng.standard_normal(40) * 0.01).tolist()
        # point = 1.0, bench_median = 0.0 → point is far above → p_hot high
        bs = {"naive_prior": 0.0}
        out = _compute_surprise_distribution(1.0, bs, res)
        assert out is not None
        assert out["p_hot"] > out["p_cold"]


# ---------------------------------------------------------------------------
# 3. Quirk flags (engine/release_quirks.py)
# ---------------------------------------------------------------------------

from engine.release_quirks import (
    compute_quirk_flags,
    _nfp_five_week_gap,
    _claims_is_holiday_week,
    _thanksgiving,
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


# ---------------------------------------------------------------------------
# 4. Sensitivity chip (_compute_sensitivity)
# ---------------------------------------------------------------------------

from scripts.build_release_forecast import _compute_sensitivity


class TestSensitivity:
    def test_cpi_returns_medium(self, tmp_root: Path) -> None:
        """CPI sensitivity tag = 'medium' based on playbook thresholds."""
        # Use actual playbook file from repo
        sens = _compute_sensitivity(_REPO, "cpi_headline", {})
        if sens is not None:  # playbook exists
            assert sens["tag"] in ("low", "medium", "high")
            assert sens["tag"] == "medium"

    def test_nfp_returns_high(self, tmp_root: Path) -> None:
        """NFP sensitivity tag = 'high' based on playbook thresholds."""
        sens = _compute_sensitivity(_REPO, "nfp", {})
        if sens is not None:
            assert sens["tag"] == "high"

    def test_claims_returns_none(self, tmp_root: Path) -> None:
        """claims has no playbook data → None (fail-open)."""
        sens = _compute_sensitivity(_REPO, "claims", {})
        assert sens is None

    def test_absent_playbook_returns_none(self, tmp_root: Path) -> None:
        """No playbook file in root → None (fail-open).

        The function uses a module-level cache; reset it so the tmp_root
        (which has no playbook file) exercises the real file-not-found path.
        """
        import scripts.build_release_forecast as _brf
        _orig = _brf._playbook_cache
        try:
            _brf._playbook_cache = None  # bust cache so tmp_root is queried fresh
            sens = _compute_sensitivity(tmp_root, "cpi_headline", {})
            assert sens is None
        finally:
            _brf._playbook_cache = _orig  # restore so other tests are unaffected

    def test_returns_required_keys(self, tmp_root: Path) -> None:
        """When playbook present, returned dict has tag, basis, note."""
        sens = _compute_sensitivity(_REPO, "nfp", {})
        if sens is not None:
            assert "tag" in sens and "basis" in sens and "note" in sens

    def test_note_is_weather_framing(self, tmp_root: Path) -> None:
        """Note contains weather-report language, not equity-direction language."""
        sens = _compute_sensitivity(_REPO, "cpi_headline", {})
        if sens is not None:
            note = sens.get("note", "").lower()
            # Weather framing check
            assert "not investment advice" in note
            # Ensure no equity-direction language (MRI-R1)
            forbidden = ["buy", "sell", "long", "short", "bullish", "bearish"]
            for word in forbidden:
                assert word not in note, f"forbidden word '{word}' in sensitivity note"


# ---------------------------------------------------------------------------
# 5. Ledger row additive fields
# ---------------------------------------------------------------------------

from scripts.build_release_forecast import _build_projection_ledger_rows


def _make_upcoming_item(
    release_type: str = "cpi_headline",
    period_str: str = "2026-06",
    release_date: str = "2026-07-15",
    market_implied: float | None = 0.30,
    surprise_dist: dict | None = None,
    sensitivity: dict | None = None,
    quirk_flags: list | None = None,
) -> dict:
    return {
        "release": "cpi",
        "release_type": release_type,
        "period": period_str,
        "release_date": release_date,
        "days_to": 8,
        "target": "mom_sa_pct",
        "projection": {"point": 0.28, "p10": 0.13, "p25": 0.21, "p50": 0.28, "p75": 0.35, "p90": 0.44},
        "confidence": 0.62,
        "input_completeness": 0.78,
        "benchmark_set": {
            "naive_prior": 0.24,
            "trailing_3m": 0.26,
            "ar_model": 0.27,
            "cleveland_nowcast": 0.31,
            "market_implied": market_implied,
        },
        "surprise_skew": {"sigma": 0.4, "tag": "hotter"},
        "surprise_distribution": surprise_dist,
        "sensitivity": sensitivity,
        "quirk_flags": quirk_flags or [],
        "pit": {"inputs_hash": "abc123"},
        "regime_axis": "inflation",
        "policy_backdrop": {"fed_stance": "hawkish"},
    }


class TestLedgerAdditiveFields:
    def test_benchmark_market_implied_frozen(self, tmp_root: Path) -> None:
        """benchmark_market_implied is frozen on the ledger row."""
        today = date(2026, 7, 7)
        item = _make_upcoming_item(market_implied=0.305)
        rows = _build_projection_ledger_rows(today, [item], {"fed_stance": "hawkish"})
        assert len(rows) == 1
        assert rows[0]["benchmark_market_implied"] == pytest.approx(0.305)

    def test_benchmark_market_implied_null_when_absent(self, tmp_root: Path) -> None:
        """benchmark_market_implied is None when market_implied is null."""
        today = date(2026, 7, 7)
        item = _make_upcoming_item(market_implied=None)
        rows = _build_projection_ledger_rows(today, [item], {})
        assert rows[0]["benchmark_market_implied"] is None

    def test_p_hot_cold_inline_frozen(self, tmp_root: Path) -> None:
        """p_hot, p_cold, p_inline are frozen on the ledger row."""
        today = date(2026, 7, 7)
        dist = {"p_hot": 0.35, "p_cold": 0.20, "p_inline": 0.45}
        item = _make_upcoming_item(surprise_dist=dist)
        rows = _build_projection_ledger_rows(today, [item], {})
        assert rows[0]["p_hot"] == pytest.approx(0.35)
        assert rows[0]["p_cold"] == pytest.approx(0.20)
        assert rows[0]["p_inline"] == pytest.approx(0.45)

    def test_p_values_null_when_no_dist(self, tmp_root: Path) -> None:
        """p_hot/cold/inline are None when surprise_distribution is absent."""
        today = date(2026, 7, 7)
        item = _make_upcoming_item(surprise_dist=None)
        rows = _build_projection_ledger_rows(today, [item], {})
        assert rows[0]["p_hot"] is None
        assert rows[0]["p_cold"] is None
        assert rows[0]["p_inline"] is None

    def test_sensitivity_tag_frozen(self, tmp_root: Path) -> None:
        """sensitivity_tag is frozen on the ledger row."""
        today = date(2026, 7, 7)
        sens = {"tag": "medium", "basis": [], "note": "test"}
        item = _make_upcoming_item(sensitivity=sens)
        rows = _build_projection_ledger_rows(today, [item], {})
        assert rows[0]["sensitivity_tag"] == "medium"

    def test_quirk_flag_codes_frozen_as_json(self, tmp_root: Path) -> None:
        """quirk_flag_codes is a JSON array string on the ledger row."""
        today = date(2026, 7, 7)
        flags = [{"code": "cpi_weight_update", "en": "x", "zh": "x", "cite": "y"}]
        item = _make_upcoming_item(quirk_flags=flags)
        rows = _build_projection_ledger_rows(today, [item], {})
        codes_raw = rows[0]["quirk_flag_codes"]
        codes = json.loads(codes_raw)
        assert codes == ["cpi_weight_update"]

    def test_quirk_flag_codes_empty_list_when_no_flags(self, tmp_root: Path) -> None:
        """Empty quirk_flags → quirk_flag_codes is '[]'."""
        today = date(2026, 7, 7)
        item = _make_upcoming_item(quirk_flags=[])
        rows = _build_projection_ledger_rows(today, [item], {})
        assert rows[0]["quirk_flag_codes"] == "[]"


# ---------------------------------------------------------------------------
# 6. Scoreboard market_implied gating (MRI-R16)
# ---------------------------------------------------------------------------

from scripts.build_release_forecast import _build_scoreboard


def _make_scored_row(
    release: str,
    period: str,
    actual: float,
    frozen_proj_point: float | None = None,
    frozen_mi: float | None = None,
) -> dict:
    """Synthetic scored row + a companion projection row with frozen_mi."""
    scored = {
        "schema": 2,
        "row_type": "scored",
        "asof_night": "2026-07-10",
        "release": release,
        "period": period,
        "release_date": "2026-07-10",
        "actual": actual,
        "actual_first": actual,
        "frozen_asof_night": "2026-07-09",
        "frozen_projection_point": frozen_proj_point,
        "frozen_projection_p10": None,
        "frozen_projection_p90": None,
        "our_surprise": None,
        "surprise_vs_naive": None,
        "surprise_vs_trailing": None,
        "surprise_vs_ar": None,
        "surprise_vs_cleveland": None,
        "interval_hit": None,
        "skew_hit": None,
        "projection_mode": None,
        "benchmark_trailing_key": "trailing_3m",
    }
    proj = {
        "schema": 2,
        "row_type": "projection",
        "asof_night": "2026-07-09",
        "release": release,
        "period": period,
        "release_date": "2026-07-10",
        "benchmark_market_implied": frozen_mi,
    }
    return scored, proj


class TestScoreboardMarketImplied:
    def test_mae_market_implied_graded_when_frozen_non_null(self) -> None:
        """mae_market_implied computed when frozen benchmark_market_implied non-null."""
        scored, proj = _make_scored_row("cpi_headline", "2026-06", 0.32, frozen_mi=0.30)
        ledger = [scored, proj]
        sb = _build_scoreboard(ledger, "2026-07-01")
        rt_entry = sb["by_release"].get("cpi_headline")
        assert rt_entry is not None
        mae = rt_entry.get("mae_market_implied")
        assert mae is not None
        assert mae == pytest.approx(abs(0.32 - 0.30), abs=1e-4)
        assert rt_entry["n_market_implied"] == 1

    def test_mae_market_implied_null_when_frozen_null(self) -> None:
        """mae_market_implied = None when frozen benchmark_market_implied was null."""
        scored, proj = _make_scored_row("cpi_headline", "2026-06", 0.32, frozen_mi=None)
        ledger = [scored, proj]
        sb = _build_scoreboard(ledger, "2026-07-01")
        rt_entry = sb["by_release"].get("cpi_headline")
        assert rt_entry is not None
        assert rt_entry.get("mae_market_implied") is None
        assert rt_entry["n_market_implied"] == 0

    def test_mae_market_implied_multi_row(self) -> None:
        """mae_market_implied averages over multiple non-null rows."""
        scored1, proj1 = _make_scored_row("nfp", "2026-05", 180.0, frozen_mi=175.0)
        scored2, proj2 = _make_scored_row("nfp", "2026-04", 200.0, frozen_mi=195.0)
        # Give different periods so they don't clash
        ledger = [scored1, proj1, scored2, proj2]
        sb = _build_scoreboard(ledger, "2026-01-01")
        rt_entry = sb["by_release"].get("nfp")
        assert rt_entry is not None
        expected_mae = (abs(180.0 - 175.0) + abs(200.0 - 195.0)) / 2
        assert rt_entry.get("mae_market_implied") == pytest.approx(expected_mae, abs=1e-4)
        assert rt_entry["n_market_implied"] == 2

    def test_n_market_implied_present_in_scoreboard_entry(self) -> None:
        """n_market_implied key always present in scoreboard entry."""
        scored, proj = _make_scored_row("claims", "2026-07-10", 220.0)
        ledger = [scored, proj]
        sb = _build_scoreboard(ledger, "2026-01-01")
        rt_entry = sb["by_release"].get("claims")
        assert rt_entry is not None
        assert "n_market_implied" in rt_entry


# ---------------------------------------------------------------------------
# 7. Template sync sanity
# ---------------------------------------------------------------------------

from scripts.check_template_site_sync import main as sync_check_main


class TestTemplateSiteSync:
    def test_sync_passes(self) -> None:
        """check_template_site_sync must pass after PR-I UI changes."""
        rc = sync_check_main(["--check"])
        assert rc == 0, "template↔site sync check failed"
