"""tests/test_cb_desk.py — Hermetic contract tests for engine/cb_desk.py

All inputs are SYNTHETIC and deterministic — no live data dependency.
Store reads are monkeypatched; calendar YAML is monkeypatched.

Coverage:
  1.  snapshot_structure          — snapshot() returns required top-level keys
  2.  snapshot_fail_open          — all stores absent → valid dict with gaps, no raise
  3.  snapshot_has_cbs            — with synthetic data, cbs list is populated
  4.  last_change_detection       — step series → last_change detected with correct direction/bp
  5.  last_change_cut_direction   — rate cut → direction='cut'
  6.  trend_3m_hiking             — rate rising → trend='hiking'
  7.  trend_3m_easing             — rate falling → trend='easing'
  8.  trend_3m_hold               — rate flat → trend='hold'
  9.  bs_impulse_present          — WALCL series → bs_impulse populated with 13w/52w
  10. bs_impulse_null_when_absent — no BS series configured → bs_impulse=None
  11. next_meeting_populated      — calendar has future dates → next_meeting.days >= 0
  12. no_predictions_in_output    — output contains no prediction language
  13. irdr7_note_present          — irdr7_note key with IRD-R7 text present
  14. determinism                 — two calls identical
  15. stale_flagged               — old series (>12 days old) → stale=True
  16. bs unit/magnitude consistency — published level is normalized into the
      published bs_unit via bs_unit_mult (2026-09-04 units-defect regression:
      raw FRED-native levels were published under billions/trillions labels)
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, mock_open
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cb_desk import snapshot, _last_change, _trend_3m, _bs_impulse


# ---------------------------------------------------------------------------
# Synthetic data builders
# ---------------------------------------------------------------------------

def _bdate_index(n: int, start: str = "2022-01-03") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _flat_rate(n: int, val: float, col: str = "fed_funds") -> pd.DataFrame:
    """Flat rate series."""
    idx = _bdate_index(n)
    return pd.DataFrame({col: np.ones(n) * val}, index=idx)


def _step_rate(n: int, step_at: int, before: float, after: float,
               col: str = "fed_funds") -> pd.DataFrame:
    """Rate series with a step change at step_at."""
    idx = _bdate_index(n)
    vals = np.where(np.arange(n) < step_at, before, after)
    return pd.DataFrame({col: vals}, index=idx)


def _rising_rate(n: int, start: float, end: float, col: str = "fed_funds") -> pd.DataFrame:
    idx = _bdate_index(n)
    return pd.DataFrame({col: np.linspace(start, end, n)}, index=idx)


def _bs_series(n: int, start: float = 8500.0, col: str = "walcl_bn") -> pd.DataFrame:
    """Synthetic balance-sheet series (weekly)."""
    idx = pd.bdate_range("2022-01-03", periods=n)
    return pd.DataFrame({col: np.linspace(start, start * 1.1, n)}, index=idx)


def _none_store(*args, **kwargs):
    return None


def _make_store(overrides: dict[tuple, Any]):
    def _read(group: str, name: str) -> pd.DataFrame | None:
        v = overrides.get((group, name))
        if v is None:
            return None
        return v() if callable(v) else v
    return _read


def _fake_calendar(future_date_str: str | None = None) -> dict:
    """Minimal calendar YAML dict with one bank."""
    from datetime import date
    today = date.today()
    if future_date_str is None:
        nxt = today + timedelta(days=30)
        future_date_str = str(nxt)
    return {
        "banks": {
            "FOMC": {
                "name_en": "Federal Open Market Committee",
                "country": "US",
                "dates": [future_date_str],
            },
            "ECB": {"name_en": "ECB", "country": "XM", "dates": []},
            "BoJ": {"name_en": "BoJ", "country": "JP", "dates": []},
            "BoE": {"name_en": "BoE", "country": "GB", "dates": []},
            "SNB": {"name_en": "SNB", "country": "CH", "dates": []},
            "BoC": {"name_en": "BoC", "country": "CA", "dates": []},
            "RBA": {"name_en": "RBA", "country": "AU", "dates": []},
        }
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSnapshotStructure:
    def test_required_keys_present(self):
        """snapshot() returns all required top-level keys."""
        with patch("engine.cb_desk.store.read", _none_store), \
             patch("engine.cb_desk._load_calendar", return_value=_fake_calendar()):
            result = snapshot()
        required = {"cbs", "n_cbs", "gaps", "as_of", "built",
                    "bs_note", "irdr7_note"}
        assert required.issubset(set(result.keys()))

    def test_cbs_is_list(self):
        with patch("engine.cb_desk.store.read", _none_store), \
             patch("engine.cb_desk._load_calendar", return_value=_fake_calendar()):
            result = snapshot()
        assert isinstance(result["cbs"], list)

    def test_gaps_is_list(self):
        with patch("engine.cb_desk.store.read", _none_store), \
             patch("engine.cb_desk._load_calendar", return_value=_fake_calendar()):
            result = snapshot()
        assert isinstance(result["gaps"], list)

    def test_irdr7_note_present(self):
        """IRD-R7 descriptive note must be present."""
        with patch("engine.cb_desk.store.read", _none_store), \
             patch("engine.cb_desk._load_calendar", return_value=_fake_calendar()):
            result = snapshot()
        assert "IRD-R7" in result["irdr7_note"]
        assert "DESCRIPTIVE" in result["irdr7_note"]


class TestFailOpen:
    def test_all_stores_absent_no_raise(self):
        """All stores absent → snapshot() returns valid dict without raising."""
        with patch("engine.cb_desk.store.read", _none_store), \
             patch("engine.cb_desk._load_calendar", return_value=_fake_calendar()):
            result = snapshot()
        assert isinstance(result, dict)
        assert result["n_cbs"] == 0

    def test_missing_calendar_no_raise(self):
        """Calendar load fails → snapshot returns valid dict."""
        with patch("engine.cb_desk.store.read", _none_store), \
             patch("engine.cb_desk._load_calendar", return_value={}):
            result = snapshot()
        assert isinstance(result, dict)


class TestCBRows:
    def _basic_store(self) -> dict[tuple, Any]:
        """Store with Fed DFF series (flat at 5.5% — in actual % units as DFF stores it)."""
        return {
            ("fred", "DFF"): _flat_rate(600, 5.5, col="fed_funds"),
        }

    def test_fed_row_present(self):
        """With DFF series, FED row appears in cbs."""
        with patch("engine.cb_desk.store.read", _make_store(self._basic_store())), \
             patch("engine.cb_desk._load_calendar", return_value=_fake_calendar()):
            result = snapshot()
        cb_ids = [cb["id"] for cb in result["cbs"]]
        assert "FED" in cb_ids

    def test_fed_policy_rate_value(self):
        """FED policy_rate matches last value in DFF series (in % units)."""
        with patch("engine.cb_desk.store.read", _make_store(self._basic_store())), \
             patch("engine.cb_desk._load_calendar", return_value=_fake_calendar()):
            result = snapshot()
        fed_row = next((cb for cb in result["cbs"] if cb["id"] == "FED"), None)
        assert fed_row is not None
        assert fed_row["policy_rate"] is not None
        # DFF stored in % (5.5 = 5.5%)
        assert abs(fed_row["policy_rate"] - 5.5) < 0.01

    def test_cb_row_structure(self):
        """Each CB row has required fields."""
        with patch("engine.cb_desk.store.read", _make_store(self._basic_store())), \
             patch("engine.cb_desk._load_calendar", return_value=_fake_calendar()):
            result = snapshot()
        for cb in result["cbs"]:
            assert "id" in cb
            assert "name_en" in cb
            assert "policy_rate" in cb
            assert "trend_3m" in cb
            assert "asof" in cb
            assert "stale" in cb
            assert "last_change" in cb
            assert "bs_impulse" in cb
            assert "next_meeting" in cb
            assert "source" in cb


class TestLastChangeDetection:
    def test_hike_detected(self):
        """Step up → direction='hike', bp positive.

        Rates are stored in actual % units (e.g., 5.0 = 5.0%), matching real FRED series.
        A 25bp hike: 5.0 → 5.25 (diff = 0.25pp; threshold = 1bp/100 = 0.01pp).
        """
        s = _step_rate(600, 300, 5.0, 5.25)["fed_funds"]
        result = _last_change(s, min_bp=1.0)
        assert result is not None, "Expected hike detected but got None"
        assert result["direction"] == "hike"
        # 5.25 - 5.0 = 0.25pp = 25bp (stored in % so * 100)
        assert result["bp"] is not None
        assert abs(result["bp"] - 25.0) < 2.0

    def test_cut_detected(self):
        """Step down → direction='cut', bp negative."""
        s = _step_rate(600, 300, 5.25, 5.0)["fed_funds"]
        result = _last_change(s, min_bp=1.0)
        assert result is not None, "Expected cut detected but got None"
        assert result["direction"] == "cut"
        assert result["bp"] is not None
        assert result["bp"] < 0

    def test_no_change_returns_none(self):
        """Flat rate → no changes → _last_change returns None."""
        s = _flat_rate(600, 5.0)["fed_funds"]
        result = _last_change(s, min_bp=1.0)
        assert result is None

    def test_change_date_correct(self):
        """Change date matches the step position."""
        n = 600
        step_at = 400
        s = _step_rate(n, step_at, 5.0, 5.25)["fed_funds"]
        result = _last_change(s, min_bp=1.0)
        assert result is not None, "Expected change detected"
        assert result["date"] is not None
        # Date should be at the step position
        step_date = str(s.index[step_at].date())
        assert result["date"] == step_date


class TestTrend3m:
    def test_hiking(self):
        """Rising rate → 'hiking'."""
        s = _rising_rate(600, 0.0, 0.055)["fed_funds"]
        result = _trend_3m(s)
        assert result == "hiking"

    def test_easing(self):
        """Falling rate → 'easing'."""
        s = _rising_rate(600, 0.055, 0.0)["fed_funds"]
        result = _trend_3m(s)
        assert result == "easing"

    def test_hold(self):
        """Flat rate → 'hold'."""
        s = _flat_rate(600, 0.055)["fed_funds"]
        result = _trend_3m(s)
        assert result == "hold"

    def test_none_on_empty(self):
        """Empty series → None."""
        result = _trend_3m(None)
        assert result is None


class TestBSImpulse:
    def _spec_with_bs(self) -> dict:
        return {
            "id": "FED",
            "bs_series": "WALCL",
            "bs_store": "fred",
            "bs_unit": "USD billions",
        }

    def _spec_without_bs(self) -> dict:
        return {
            "id": "BOE",
            "bs_series": None,
            "bs_store": None,
            "bs_unit": None,
        }

    def test_impulse_populated_when_series_present(self):
        """WALCL series → bs_impulse has impulse_13w, impulse_52w."""
        gaps = []
        walcl = _bs_series(400)
        with patch("engine.cb_desk.store.read", _make_store({("fred", "WALCL"): walcl})):
            result = _bs_impulse(self._spec_with_bs(), gaps)
        assert result is not None
        assert "impulse_13w" in result
        assert "impulse_52w" in result
        assert "level" in result
        assert "asof" in result

    def test_impulse_null_when_no_bs_series(self):
        """No bs_series configured → None."""
        gaps = []
        result = _bs_impulse(self._spec_without_bs(), gaps)
        assert result is None

    def test_impulse_null_when_store_absent(self):
        """bs_series configured but not in store → None + gap noted."""
        gaps = []
        with patch("engine.cb_desk.store.read", _none_store):
            result = _bs_impulse(self._spec_with_bs(), gaps)
        assert result is None
        assert len(gaps) > 0


class TestNextMeeting:
    def test_next_meeting_days_positive(self):
        """Future calendar date → next_meeting.days >= 0."""
        from engine.cb_desk import _next_meeting
        today = date.today()
        nxt = today + timedelta(days=14)
        cal = {
            "banks": {
                "FOMC": {"name_en": "FOMC", "dates": [str(nxt)]}
            }
        }
        result = _next_meeting("FOMC", cal, today)
        assert result is not None
        assert result["days"] >= 0
        assert result["date"] == str(nxt)

    def test_next_meeting_past_dates_skipped(self):
        """Only past dates in calendar → next_meeting=None."""
        from engine.cb_desk import _next_meeting
        today = date.today()
        past = today - timedelta(days=30)
        cal = {
            "banks": {
                "FOMC": {"name_en": "FOMC", "dates": [str(past)]}
            }
        }
        result = _next_meeting("FOMC", cal, today)
        assert result is None

    def test_next_meeting_missing_key(self):
        """Calendar key absent → None."""
        from engine.cb_desk import _next_meeting
        result = _next_meeting("FOMC", {"banks": {}}, date.today())
        assert result is None


class TestNoPredictionLanguage:
    # Check for forward-looking claims in CB data fields (not in metadata notes)
    # The irdr7_note is a caveat note and may use terms like "projection"
    _PREDICTION_WORDS = [
        "will hike", "will cut", "expected to raise", "expected to cut",
        "likely to raise", "likely to cut",
    ]

    def test_no_predictions_in_output(self):
        """Output dict serialized to string should contain no prediction language."""
        import json
        with patch("engine.cb_desk.store.read", _none_store), \
             patch("engine.cb_desk._load_calendar", return_value=_fake_calendar()):
            result = snapshot()
        result_str = json.dumps(result).lower()
        for word in self._PREDICTION_WORDS:
            assert word.lower() not in result_str, f"Prediction word '{word}' found in output"


class TestStaleFlagging:
    def test_stale_when_old_data(self):
        """Series with last observation > 12 days ago → stale=True."""
        n = 100
        # Make index end 20 days ago
        end_date = pd.Timestamp.today() - pd.Timedelta(days=20)
        idx = pd.bdate_range(end=end_date, periods=n)
        old_series = pd.DataFrame({"fed_funds": np.ones(n) * 0.055}, index=idx)
        store_map = {("fred", "DFF"): old_series}
        with patch("engine.cb_desk.store.read", _make_store(store_map)), \
             patch("engine.cb_desk._load_calendar", return_value=_fake_calendar()):
            result = snapshot()
        fed_row = next((cb for cb in result["cbs"] if cb["id"] == "FED"), None)
        if fed_row is not None:
            assert fed_row["stale"] is True


class TestTrend3mCadenceAware:
    """IRD review finding: monthly series must use 3-obs lookback, not 63."""

    def test_monthly_flat_24m_after_hike_reads_hold(self):
        """Monthly IR3TIB series flat for 24 months after an old hike → 'hold'.

        With the OLD cadence-unaware logic (n=63 on a monthly series = ~5y lookback),
        BoJ/BoE/SNB/BoC/RBA show 'hiking' while the rate has been flat for 2 years.
        With cadence='monthly', n=3 → only the last 3 months are compared → 'hold'.
        """
        # Monthly series: one hike 24 months ago (jump from 0 to 0.25), then flat
        n = 36   # 36 months of history
        idx = pd.date_range("2022-01-01", periods=n, freq="MS")
        # First 12 months: 0.0; then hike to 0.25 at month 12; then flat 24 months
        values = np.where(np.arange(n) < 12, 0.0, 0.25)
        s = pd.Series(values, index=idx)

        # OLD behavior (cadence="daily" / no cadence param): reads "hiking"
        trend_old = _trend_3m(s, cadence="daily")
        assert trend_old == "hiking", (
            "Sanity: daily cadence on monthly series should misread as 'hiking' "
            f"(got {trend_old!r})"
        )

        # FIXED behavior (cadence="monthly"): last 3 monthly obs are all 0.25 → 'hold'
        trend_fixed = _trend_3m(s, cadence="monthly")
        assert trend_fixed == "hold", (
            f"Monthly cadence: 24m flat after old hike should read 'hold', got {trend_fixed!r}"
        )

    def test_monthly_recent_hike_still_reads_hiking(self):
        """Monthly series with recent hike within 3 months → 'hiking' with cadence='monthly'."""
        n = 24
        idx = pd.date_range("2024-01-01", periods=n, freq="MS")
        # Hike 2 months ago: 0.0 → 0.25
        values = np.where(np.arange(n) < n - 2, 0.0, 0.25)
        s = pd.Series(values, index=idx)

        trend = _trend_3m(s, cadence="monthly")
        assert trend == "hiking", f"Recent monthly hike should read 'hiking', got {trend!r}"

    def test_daily_cadence_default_unchanged(self):
        """Default cadence='daily' is backward-compatible: rising daily series → 'hiking'."""
        s = _rising_rate(600, 0.0, 0.055)["fed_funds"]
        result = _trend_3m(s)   # no cadence arg → default "daily"
        assert result == "hiking"


class TestDeterminism:
    def test_snapshot_deterministic(self):
        """Two calls with same data return identical results."""
        store_map = {
            ("fred", "DFF"): _flat_rate(600, 5.5 / 100, col="fed_funds"),
        }
        with patch("engine.cb_desk.store.read", _make_store(store_map)), \
             patch("engine.cb_desk._load_calendar", return_value=_fake_calendar()):
            r1 = snapshot()
        with patch("engine.cb_desk.store.read", _make_store(store_map)), \
             patch("engine.cb_desk._load_calendar", return_value=_fake_calendar()):
            r2 = snapshot()

        assert r1["n_cbs"] == r2["n_cbs"]
        for cb1, cb2 in zip(r1["cbs"], r2["cbs"]):
            assert cb1["id"] == cb2["id"]
            assert cb1["policy_rate"] == cb2["policy_rate"]
            assert cb1["trend_3m"] == cb2["trend_3m"]


class TestBSUnitMagnitudeConsistency:
    """Regression for the 2026-09-04 units defect.

    cb_desk used to publish raw FRED-native levels under wrong unit labels:
    WALCL (native MILLIONS of USD, ~6,737,204) as "USD billions";
    ECBASSETSW (native MILLIONS of EUR) as "EUR billions";
    JPNASSETS (native 100-MILLION JPY) as "JPY trillions" (off by 10^4).
    The fix wires the specs' bs_unit_mult so the published level is in the
    published bs_unit. These tests run the REAL _CB_SPECS entries against
    synthetic series at the verified FRED-native magnitudes.
    """

    # (series, FRED-native last obs as verified in the parquet store
    #  2026-09-04, expected published unit, expected published level)
    _NATIVE = {
        "FED": ("WALCL", 6_737_204.0, "USD billions", 6_737.2),
        "ECB": ("ECBASSETSW", 5_915_343.0, "EUR billions", 5_915.3),
        "BOJ": ("JPNASSETS", 6_446_620.0, "JPY billions", 644_662.0),
    }

    @staticmethod
    def _native_series(last_value: float, n: int = 120) -> pd.DataFrame:
        idx = pd.bdate_range("2024-01-05", periods=n)
        return pd.DataFrame({"v": np.linspace(last_value * 0.95, last_value, n)},
                            index=idx)

    @staticmethod
    def _real_spec(cb_id: str) -> dict:
        from engine.cb_desk import _CB_SPECS
        return next(s for s in _CB_SPECS if s["id"] == cb_id)

    @pytest.mark.parametrize("cb_id", ["FED", "ECB", "BOJ"])
    def test_level_published_in_labeled_unit(self, cb_id):
        """FRED-native magnitude in → level comes out in the labeled unit."""
        series, native_last, want_unit, want_level = self._NATIVE[cb_id]
        spec = self._real_spec(cb_id)
        df = self._native_series(native_last)
        gaps: list = []
        with patch("engine.cb_desk.store.read",
                   _make_store({("fred", series): df})):
            bs = _bs_impulse(spec, gaps)
        assert bs is not None
        assert bs["unit"] == want_unit
        assert bs["level"] == pytest.approx(want_level, abs=0.11)

    @pytest.mark.parametrize("cb_id", ["FED", "ECB", "BOJ"])
    def test_billions_label_magnitude_plausible(self, cb_id):
        """A level labeled 'billions' must be plausible at that scale.

        Raw FRED-native magnitudes are 10^3–10^4 too large for the label;
        if bs_unit_mult is ever dropped or mis-set, this trips.
        (Caps: no G-SIFI balance sheet exceeds $50T/€50T or ¥2,000T.)
        """
        series, native_last, _, _ = self._NATIVE[cb_id]
        spec = self._real_spec(cb_id)
        df = self._native_series(native_last)
        with patch("engine.cb_desk.store.read",
                   _make_store({("fred", series): df})):
            bs = _bs_impulse(spec, [])
        assert bs is not None
        assert "billion" in (bs["unit"] or "").lower(), (
            f"{cb_id}: bs_unit {bs['unit']!r} no longer labeled in billions")
        cap = 2_000_000.0 if "JPY" in bs["unit"] else 50_000.0
        assert abs(bs["level"]) <= cap, (
            f"{cb_id}: level {bs['level']:g} implausible for unit {bs['unit']!r} "
            "— raw store magnitude leaking through (units-defect regression)")

    def test_every_configured_bs_series_declares_unit_and_mult(self):
        """Spec contract: any CB with a bs_series must declare a billions
        bs_unit and an explicit bs_unit_mult (no implicit ×1 pass-through)."""
        from engine.cb_desk import _CB_SPECS
        for spec in _CB_SPECS:
            if not spec.get("bs_series"):
                continue
            assert spec.get("bs_unit"), f"{spec['id']}: bs_unit missing"
            assert "billion" in spec["bs_unit"].lower(), (
                f"{spec['id']}: bs_unit {spec['bs_unit']!r} not in billions")
            assert spec.get("bs_unit_mult"), (
                f"{spec['id']}: bs_unit_mult missing — raw FRED level would "
                "be published under a billions label")

    def test_impulses_scale_invariant(self):
        """bs_unit_mult must rescale the level ONLY — %-change impulses are
        identical whatever the multiplier."""
        series, native_last, _, _ = self._NATIVE["FED"]
        spec_scaled = self._real_spec("FED")
        spec_raw = {**spec_scaled, "bs_unit_mult": 1.0}
        df = self._native_series(native_last)
        store_map = {("fred", series): df}
        with patch("engine.cb_desk.store.read", _make_store(store_map)):
            bs_scaled = _bs_impulse(spec_scaled, [])
            bs_raw = _bs_impulse(spec_raw, [])
        assert bs_scaled["impulse_13w"] == bs_raw["impulse_13w"]
        assert bs_scaled["impulse_52w"] == bs_raw["impulse_52w"]
        assert bs_scaled["level"] == pytest.approx(bs_raw["level"] * 1e-3, abs=0.11)
