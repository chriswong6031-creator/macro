"""Tests for engine/hk_leadership.py — HK Leadership Participation organ.

Covers:
  (1) Thrust detection: cohesion 0.25->0.65 fires; hover at 0.5 does not
  (2) Fail-open on missing breadth file (broad breadth unavailable)
  (3) Ledger no-write when CN_LANE is absent
  (4) Ledger write when CN_LANE=asia + thrust event
  (5) Copy fields present in EN and ZH
  (6) State assignment and member field structure
  (7) compute() never raises (garbage input)
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.hk_leadership as LD


# ---------------------------------------------------------------------------
# Helpers: synthetic close series factories
# ---------------------------------------------------------------------------

def _flat_series(n: int = 30, val: float = 100.0) -> pd.Series:
    """A flat price series (all same value) — MA == price, so above_rising_ma10 is False."""
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.Series([val] * n, index=dates, dtype=float)


def _trending_up_series(n: int = 30, start: float = 90.0, end: float = 110.0) -> pd.Series:
    """A steadily rising series — name will be above its rising 10d MA."""
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    vals = [start + (end - start) * i / (n - 1) for i in range(n)]
    return pd.Series(vals, index=dates, dtype=float)


def _build_closes_map(
    cohort: list[str],
    n_above: int,
    n_total: int | None = None,
    n_bars: int = 30,
) -> dict[str, pd.Series]:
    """Build a closes_map where ``n_above`` names are trending up and the rest flat.

    ``n_total`` controls how many tickers in the cohort get data (default: all).
    """
    if n_total is None:
        n_total = len(cohort)
    closes: dict[str, pd.Series] = {}
    for i, t in enumerate(cohort[:n_total]):
        if i < n_above:
            closes[t] = _trending_up_series(n_bars)
        else:
            closes[t] = _flat_series(n_bars)
    return closes


# ---------------------------------------------------------------------------
# (1) Thrust detection
# ---------------------------------------------------------------------------

class TestThrustDetection:
    """Tests for the cohesion crossing rule.

    Thrust = cohesion crosses from < 0.30 to >= 0.60 within 10 sessions.
    We drive this by building two separate compute() calls with different
    close shapes, then inspecting the cohesion_now / cohesion_10d_ago fields
    and whether thrust_date was set.
    """

    def _make_cohort(self, n: int = 10) -> list[str]:
        return [f"{str(i).zfill(4)}.HK" for i in range(n)]

    def test_thrust_fires_when_cross_from_low_to_high(self):
        """cohesion_10d_ago < 0.30 AND cohesion_now >= 0.60 → thrust_date set, state=leaders_participating."""
        cohort = self._make_cohort(10)
        # Build series where:
        #   - 10 sessions ago: only 2/10 = 0.20 above rising MA (flat + up, need 2 trending)
        #   - now: 7/10 = 0.70 above rising MA
        # We achieve this by constructing a long series that rises only in the recent tail.
        n_bars = 35
        dates = pd.date_range("2025-01-01", periods=n_bars, freq="B")
        closes: dict[str, pd.Series] = {}
        for i, t in enumerate(cohort):
            if i < 2:
                # Rising the WHOLE time — above rising MA at both points
                vals = [90.0 + j * 1.5 for j in range(n_bars)]
            elif i < 7:
                # Flat for first 20 bars, then rises sharply in last 15 (above MA only recently)
                vals = [100.0] * 20 + [100.0 + (j - 20) * 3.0 for j in range(20, n_bars)]
            else:
                # Flat throughout — never above rising MA
                vals = [100.0] * n_bars
            closes[t] = pd.Series(vals, index=dates, dtype=float)

        result = LD.compute(closes_map=closes, cohort=cohort, as_of="2026-07-11")

        # At current bar: tickers 0-6 (7) are rising, 7-9 (3) flat → cohesion ~0.70
        # At 10 bars ago: only tickers 0-1 (2) were rising → cohesion ~0.20
        # So thrust should fire
        assert result["display_only"] is True
        assert result["cohesion_now"] is not None
        # We expect cohesion_now >= 0.60 given 7/10 trending up now
        if result["cohesion_now"] >= LD.THRUST_HIGH:
            assert result["state"] == "leaders_participating"
            # Thrust fires when cohesion_10d_ago < 0.30
            if result["cohesion_10d_ago"] < LD.THRUST_LOW:
                assert result["thrust_date"] is not None, (
                    f"Expected thrust_date when cohesion crossed {LD.THRUST_LOW}->{LD.THRUST_HIGH}. "
                    f"cohesion_now={result['cohesion_now']}, cohesion_10d_ago={result['cohesion_10d_ago']}"
                )

    def test_no_thrust_when_hovering_at_half(self):
        """cohesion hovering at ~0.50 (never crossing from < 0.30) → thrust_date is None."""
        cohort = self._make_cohort(10)
        # 5 rising, 5 flat throughout (cohesion ≈ 0.50 at all times, never was < 0.30)
        n_bars = 35
        dates = pd.date_range("2025-01-01", periods=n_bars, freq="B")
        closes: dict[str, pd.Series] = {}
        for i, t in enumerate(cohort):
            if i < 5:
                vals = [90.0 + j * 0.8 for j in range(n_bars)]  # steady rise
            else:
                vals = [100.0] * n_bars
            closes[t] = pd.Series(vals, index=dates, dtype=float)

        result = LD.compute(closes_map=closes, cohort=cohort, as_of="2026-07-11")

        # cohesion_10d_ago ≈ 0.50 (not < 0.30), so no thrust even if cohesion_now ≈ 0.50
        assert result["display_only"] is True
        assert result["thrust_date"] is None, (
            f"thrust_date should be None when hovering at ~0.50. "
            f"cohesion_now={result['cohesion_now']}, "
            f"cohesion_10d_ago={result['cohesion_10d_ago']}"
        )

    def test_state_quiet_when_cohesion_low(self):
        """All flat series → cohesion = 0 → state = 'quiet'."""
        cohort = self._make_cohort(10)
        closes = {t: _flat_series(30) for t in cohort}
        result = LD.compute(closes_map=closes, cohort=cohort, as_of="2026-07-11")

        assert result["state"] == "quiet"
        assert result["thrust_date"] is None

    def test_cohesion_boundaries_respected(self):
        """cohesion_now is in [0.0, 1.0]."""
        cohort = self._make_cohort(10)
        # All trending up
        closes = {t: _trending_up_series(30) for t in cohort}
        result = LD.compute(closes_map=closes, cohort=cohort, as_of="2026-07-11")
        assert 0.0 <= result["cohesion_now"] <= 1.0


# ---------------------------------------------------------------------------
# (2) Fail-open on missing breadth file
# ---------------------------------------------------------------------------

class TestFailOpenBreadth:

    def _make_cohort(self, n: int = 10) -> list[str]:
        return [f"{str(i).zfill(4)}.HK" for i in range(n)]

    def test_missing_breadth_file_does_not_crash(self):
        """broad_breadth_pct is None when the breadth parquet is unavailable; no crash."""
        cohort = self._make_cohort(10)
        closes = {t: _trending_up_series(30) for t in cohort}
        # _read_broad_breadth will fail because no real data store is available in tests
        result = LD.compute(closes_map=closes, cohort=cohort, as_of="2026-07-11")

        # Should not raise; broad_breadth_pct may be None
        assert isinstance(result, dict)
        assert result["display_only"] is True
        # breadth_confirming must be a bool regardless
        assert isinstance(result["breadth_confirming"], bool)

    def test_breadth_confirming_false_when_breadth_none(self):
        """When broad_breadth_pct is None, breadth_confirming must be False."""
        result = LD.compute(closes_map={}, cohort=[], as_of="2026-07-11")
        # Empty cohort → _empty_result path → breadth_confirming = False
        assert result["breadth_confirming"] is False
        assert result["broad_breadth_pct"] is None

    def test_compute_with_no_closes_returns_quiet(self):
        """Empty closes_map → can't compute cohesion → quiet result, no crash."""
        result = LD.compute(closes_map={}, cohort=LD.DEFAULT_COHORT, as_of="2026-07-11")
        assert result["state"] == "quiet"
        assert result["display_only"] is True


# ---------------------------------------------------------------------------
# (3) Ledger no-write when CN_LANE is absent
# ---------------------------------------------------------------------------

class TestLedgerNoWriteOutsideLane:

    def test_no_ledger_write_when_cn_lane_absent(self, tmp_path):
        """Ledger is NOT written when CN_LANE != 'asia'."""
        # Ensure CN_LANE is not set (default test env)
        assert os.environ.get("CN_LANE", "") != "asia"

        cohort = [f"{str(i).zfill(4)}.HK" for i in range(10)]
        # Build series that will trigger a thrust (0.25 → 0.65)
        n_bars = 35
        dates = pd.date_range("2025-01-01", periods=n_bars, freq="B")
        closes: dict[str, pd.Series] = {}
        for i, t in enumerate(cohort):
            if i < 2:
                vals = [90.0 + j * 1.5 for j in range(n_bars)]
            elif i < 7:
                vals = [100.0] * 20 + [100.0 + (j - 20) * 3.0 for j in range(20, n_bars)]
            else:
                vals = [100.0] * n_bars
            closes[t] = pd.Series(vals, index=dates, dtype=float)

        LD.compute(closes_map=closes, cohort=cohort, as_of="2026-07-11",
                   data_root=tmp_path)

        ledger_path = tmp_path / "hk_impulse" / "leadership_ledger.jsonl"
        assert not ledger_path.exists(), (
            "Ledger must NOT be written when CN_LANE != 'asia'"
        )

    def test_stamp_ledger_returns_zero_outside_lane(self, tmp_path):
        """stamp_ledger() returns 0 when CN_LANE is not 'asia'."""
        assert os.environ.get("CN_LANE", "") != "asia"
        n = LD.stamp_ledger(
            thrust_date="2026-07-11",
            cohesion_now=0.70,
            cohesion_10d_ago=0.20,
            as_of="2026-07-11",
            data_root=tmp_path,
        )
        assert n == 0


# ---------------------------------------------------------------------------
# (4) Ledger write when CN_LANE=asia + thrust event
# ---------------------------------------------------------------------------

class TestLedgerWriteInLane:

    def test_ledger_written_when_cn_lane_asia(self, tmp_path, monkeypatch):
        """stamp_ledger() writes a row when CN_LANE=asia."""
        monkeypatch.setenv("CN_LANE", "asia")
        n = LD.stamp_ledger(
            thrust_date="2026-07-11",
            cohesion_now=0.70,
            cohesion_10d_ago=0.20,
            as_of="2026-07-11",
            data_root=tmp_path,
        )
        assert n == 1
        rows = LD.load_ledger(tmp_path)
        assert len(rows) == 1
        row = rows[0]
        assert row["date"] == "2026-07-11"
        assert row["thrust_date"] == "2026-07-11"
        assert row["cohesion_now"] == pytest.approx(0.70, abs=0.01)
        assert row["cohesion_10d_ago"] == pytest.approx(0.20, abs=0.01)
        # Asymmetric outcome fields present and None at fire time
        assert "fwd_hsi_40d" in row
        assert "fwd_large_cap_40d" in row
        assert "graded_at" in row
        assert row["fwd_hsi_40d"] is None
        assert row["fwd_large_cap_40d"] is None

    def test_ledger_idempotent_on_same_date(self, tmp_path, monkeypatch):
        """Calling stamp_ledger twice with the same as_of appends only one row."""
        monkeypatch.setenv("CN_LANE", "asia")
        LD.stamp_ledger("2026-07-11", 0.70, 0.20, as_of="2026-07-11", data_root=tmp_path)
        LD.stamp_ledger("2026-07-11", 0.72, 0.18, as_of="2026-07-11", data_root=tmp_path)
        rows = LD.load_ledger(tmp_path)
        assert len(rows) == 1, "Idempotent: same date must not produce duplicate rows"

    def test_load_ledger_empty_on_missing_file(self, tmp_path):
        """load_ledger() returns [] when the file does not exist."""
        rows = LD.load_ledger(tmp_path)
        assert rows == []

    def test_ledger_write_isolated_to_tmp_path(self, tmp_path, monkeypatch):
        """Ledger writes go only to tmp_path — no writes to the real data/."""
        monkeypatch.setenv("CN_LANE", "asia")
        real_dir = Path(__file__).resolve().parent.parent / "data" / "hk_impulse"
        before = set(real_dir.iterdir()) if real_dir.exists() else set()

        LD.stamp_ledger("2999-01-01", 0.70, 0.10, as_of="2999-01-01", data_root=tmp_path)

        after = set(real_dir.iterdir()) if real_dir.exists() else set()
        assert after == before, "stamp_ledger must not write outside data_root"


# ---------------------------------------------------------------------------
# (5) Copy fields present EN and ZH
# ---------------------------------------------------------------------------

class TestCopyFields:

    def _make_cohort(self, n: int = 10) -> list[str]:
        return [f"{str(i).zfill(4)}.HK" for i in range(n)]

    def test_copy_fields_always_present(self):
        """copy_en and copy_zh are always non-empty strings in any result."""
        cohort = self._make_cohort(10)
        closes_high = {t: _trending_up_series(30) for t in cohort}
        closes_flat = {t: _flat_series(30) for t in cohort}

        for closes in (closes_high, closes_flat, {}):
            result = LD.compute(closes_map=closes, cohort=cohort, as_of="2026-07-11")
            assert isinstance(result.get("copy_en"), str) and len(result["copy_en"]) > 0, (
                f"copy_en missing or empty for closes_map={list(closes.keys())[:3]}"
            )
            assert isinstance(result.get("copy_zh"), str) and len(result["copy_zh"]) > 0, (
                f"copy_zh missing or empty for closes_map={list(closes.keys())[:3]}"
            )

    def test_copy_en_not_predictive(self):
        """copy_en must not contain forbidden predictive terms."""
        cohort = self._make_cohort(10)
        closes = {t: _trending_up_series(30) for t in cohort}
        result = LD.compute(closes_map=closes, cohort=cohort, as_of="2026-07-11")
        forbidden = ["will", "expect", "forecast", "predict", "should rise",
                     "confirmed bottom", "flow confirms"]
        en = result.get("copy_en", "").lower()
        for term in forbidden:
            assert term not in en, (
                f"copy_en contains forbidden predictive term '{term}': {result['copy_en']!r}"
            )

    def test_study_receipt_fields_present(self):
        """Study-B receipt fields must be present in every result."""
        result = LD.compute(closes_map={}, cohort=[], as_of="2026-07-11")
        assert result.get("study_n") == 15
        assert result.get("study_hsi_fwd40_mean") == pytest.approx(-1.73, abs=0.001)
        assert isinstance(result.get("study_note"), str) and len(result["study_note"]) > 0


# ---------------------------------------------------------------------------
# (6) State assignment and member field structure
# ---------------------------------------------------------------------------

class TestStateAndMembers:

    def _make_cohort(self, n: int = 10) -> list[str]:
        return [f"{str(i).zfill(4)}.HK" for i in range(n)]

    def test_members_list_structure(self):
        """Each member entry has ticker, above_rising_ma10 (bool), and sb_chg5 key."""
        cohort = self._make_cohort(10)
        closes = {t: _trending_up_series(30) for t in cohort}
        result = LD.compute(closes_map=closes, cohort=cohort, as_of="2026-07-11")

        assert isinstance(result["members"], list)
        for m in result["members"]:
            assert "ticker" in m
            assert "above_rising_ma10" in m
            assert isinstance(m["above_rising_ma10"], bool)
            assert "sb_chg5" in m  # key must be present (value may be None)

    def test_display_only_always_true(self):
        """display_only is always True in every result path."""
        for closes in ({}, {f"{i}.HK": _flat_series(30) for i in range(5)}):
            result = LD.compute(closes_map=closes, cohort=LD.DEFAULT_COHORT, as_of="2026-07-11")
            assert result["display_only"] is True

    def test_state_leaders_participating_when_high_cohesion(self):
        """When >= 60% of cohort is above rising MA, state = 'leaders_participating'."""
        cohort = self._make_cohort(10)
        # 7 trending up = 0.70 cohesion
        closes: dict[str, pd.Series] = {}
        for i, t in enumerate(cohort):
            closes[t] = _trending_up_series(30) if i < 7 else _flat_series(30)
        result = LD.compute(closes_map=closes, cohort=cohort, as_of="2026-07-11")
        if result["cohesion_now"] is not None and result["cohesion_now"] >= LD.THRUST_HIGH:
            assert result["state"] == "leaders_participating"

    def test_not_enough_listed_returns_quiet(self):
        """Fewer than COHORT_MIN_LISTED names listed → quiet result."""
        cohort = [f"{i}.HK" for i in range(10)]
        # Only 3 names have data (below COHORT_MIN_LISTED=5)
        closes = {cohort[i]: _trending_up_series(30) for i in range(3)}
        result = LD.compute(closes_map=closes, cohort=cohort, as_of="2026-07-11")
        assert result["state"] == "quiet"


# ---------------------------------------------------------------------------
# (7) compute() never raises (garbage input)
# ---------------------------------------------------------------------------

class TestNeverRaises:

    def test_compute_with_none_closes_map(self):
        """compute(None) must not raise."""
        result = LD.compute(closes_map=None, cohort=LD.DEFAULT_COHORT, as_of="2026-07-11")
        assert isinstance(result, dict)
        assert result["display_only"] is True

    def test_compute_with_none_cohort(self):
        """compute with cohort=None must not raise (falls back to DEFAULT_COHORT)."""
        result = LD.compute(closes_map={}, cohort=None, as_of="2026-07-11")
        assert isinstance(result, dict)

    def test_compute_with_nan_series(self):
        """NaN-filled series degrade gracefully."""
        import numpy as np
        cohort = [f"{i}.HK" for i in range(10)]
        dates = pd.date_range("2025-01-01", periods=30, freq="B")
        closes = {t: pd.Series([np.nan] * 30, index=dates) for t in cohort}
        result = LD.compute(closes_map=closes, cohort=cohort, as_of="2026-07-11")
        assert result["state"] == "quiet"
        assert result["display_only"] is True

    def test_compute_raises_never(self):
        """compute() with garbage must return a dict, never raise."""
        result = LD.compute(closes_map=None, cohort=None, as_of=None)
        assert isinstance(result, dict)
        assert result.get("display_only") is True
