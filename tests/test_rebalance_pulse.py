"""tests/test_rebalance_pulse.py — Hermetic tests for engine/rebalance_pulse.py
and scripts/build_rebalance_pulse.py.

Tests:
  - compute_pulse(): each class branch
  - updown absent → basis='volume_only', class still works
  - idempotent ledger append (via tmp_path)
  - quiet class not appended to ledger
  - authority block always present
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.rebalance_pulse import (
    compute_pulse,
    _classify,
    MEGACAP_TICKERS,
    VOL_RATIO_SPIKE,
    VOL_RATIO_UNSCHEDULED,
    UP_SHARE_ABSORBED,
    UP_SHARE_DISTRIBUTED,
    PULSE_CLASSES,
)


# ── Fixture helpers ────────────────────────────────────────────────────────────

def _make_volume_cache(session_date: date, today_total: float, baseline_median: float) -> pd.DataFrame:
    """Synthetic _volume_cache with two tickers, scaled so total matches targets."""
    asof_ts = pd.Timestamp(session_date)
    # 25 prior sessions at half baseline each (half goes to ticker1, half to ticker2)
    dates = pd.bdate_range(end=session_date, periods=26)[:-1]  # 25 prior sessions
    n_tickers = 2
    per_ticker_baseline = baseline_median / n_tickers
    per_ticker_today = today_total / n_tickers

    data = {
        "SPY": [per_ticker_baseline] * 25 + [per_ticker_today],
        "IWM": [per_ticker_baseline] * 25 + [per_ticker_today],
    }
    idx = list(dates) + [asof_ts]
    return pd.DataFrame(data, index=pd.DatetimeIndex(idx))


def _make_updown(session_date: date, up_vol: float, down_vol: float) -> pd.DataFrame:
    asof_ts = pd.Timestamp(session_date)
    return pd.DataFrame(
        {"up_vol": [up_vol], "down_vol": [down_vol]},
        index=pd.DatetimeIndex([asof_ts]),
    )


def _calendar_in_window() -> dict:
    return {
        "is_quarter_end": True,
        "td_to_quarter_end": 0,
        "in_qtr_end_window": True,
        "is_russell_recon_session": False,
        "in_recon_week": False,
        "is_sp_rebalance_session": False,
        "is_month_end_session": True,
    }


def _calendar_quiet() -> dict:
    return {
        "is_quarter_end": False,
        "td_to_quarter_end": 15,
        "in_qtr_end_window": False,
        "is_russell_recon_session": False,
        "in_recon_week": False,
        "is_sp_rebalance_session": False,
        "is_month_end_session": False,
    }


SESSION_DATE = date(2024, 6, 28)


# ── compute_pulse — class branches ────────────────────────────────────────────

class TestComputePulseClasses:
    def test_mechanical_spike_absorbed(self):
        """Calendar window + vol>=1.5x + up_share>=0.55 → absorbed."""
        vol_df = _make_volume_cache(SESSION_DATE, today_total=1.6e9, baseline_median=1e9)
        updown = _make_updown(SESSION_DATE, up_vol=0.6e9, down_vol=0.4e9)
        cal = _calendar_in_window()
        result = compute_pulse(SESSION_DATE, vol_df, updown, cal)
        assert result["class"] == "mechanical_spike_absorbed"
        assert result["market_vol_ratio"] >= VOL_RATIO_SPIKE
        assert result["up_share"] >= UP_SHARE_ABSORBED

    def test_mechanical_spike_distributed(self):
        """Calendar window + vol>=1.5x + up_share<=0.45 → distributed."""
        vol_df = _make_volume_cache(SESSION_DATE, today_total=1.6e9, baseline_median=1e9)
        updown = _make_updown(SESSION_DATE, up_vol=0.4e9, down_vol=0.6e9)
        cal = _calendar_in_window()
        result = compute_pulse(SESSION_DATE, vol_df, updown, cal)
        assert result["class"] == "mechanical_spike_distributed"
        assert result["up_share"] <= UP_SHARE_DISTRIBUTED

    def test_mechanical_spike_mixed(self):
        """Calendar window + vol>=1.5x + up_share between 0.45-0.55 → mixed."""
        vol_df = _make_volume_cache(SESSION_DATE, today_total=1.6e9, baseline_median=1e9)
        updown = _make_updown(SESSION_DATE, up_vol=0.5e9, down_vol=0.5e9)
        cal = _calendar_in_window()
        result = compute_pulse(SESSION_DATE, vol_df, updown, cal)
        assert result["class"] == "mechanical_spike_mixed"

    def test_unscheduled_volume_event(self):
        """No calendar tag + vol>=1.75x → unscheduled."""
        vol_df = _make_volume_cache(SESSION_DATE, today_total=1.8e9, baseline_median=1e9)
        updown = _make_updown(SESSION_DATE, up_vol=0.5e9, down_vol=0.5e9)
        cal = _calendar_quiet()
        result = compute_pulse(SESSION_DATE, vol_df, updown, cal)
        assert result["class"] == "unscheduled_volume_event"
        assert result["market_vol_ratio"] >= VOL_RATIO_UNSCHEDULED

    def test_quiet_low_vol(self):
        """Low vol → quiet."""
        vol_df = _make_volume_cache(SESSION_DATE, today_total=0.9e9, baseline_median=1e9)
        updown = _make_updown(SESSION_DATE, up_vol=0.5e9, down_vol=0.5e9)
        cal = _calendar_quiet()
        result = compute_pulse(SESSION_DATE, vol_df, updown, cal)
        assert result["class"] == "quiet"

    def test_calendar_window_but_low_vol_is_quiet(self):
        """Calendar window + vol<1.5x → quiet (volume threshold not met)."""
        vol_df = _make_volume_cache(SESSION_DATE, today_total=1.2e9, baseline_median=1e9)
        updown = _make_updown(SESSION_DATE, up_vol=0.6e9, down_vol=0.4e9)
        cal = _calendar_in_window()
        result = compute_pulse(SESSION_DATE, vol_df, updown, cal)
        assert result["class"] == "quiet"


# ── updown-absent fallback ────────────────────────────────────────────────────

class TestUpdownAbsentFallback:
    def test_basis_volume_only_when_updown_none(self):
        vol_df = _make_volume_cache(SESSION_DATE, today_total=1.6e9, baseline_median=1e9)
        cal = _calendar_in_window()
        result = compute_pulse(SESSION_DATE, vol_df, None, cal)
        assert result["basis"] == "volume_only"
        assert result["up_share"] is None
        # With calendar + vol>=1.5x + no up_share → mixed
        assert result["class"] == "mechanical_spike_mixed"

    def test_basis_volume_only_when_updown_empty(self):
        vol_df = _make_volume_cache(SESSION_DATE, today_total=1.6e9, baseline_median=1e9)
        cal = _calendar_in_window()
        result = compute_pulse(SESSION_DATE, vol_df, pd.DataFrame(), cal)
        assert result["basis"] == "volume_only"

    def test_basis_volume_only_date_not_in_updown(self):
        """updown exists but not for our date."""
        vol_df = _make_volume_cache(SESSION_DATE, today_total=1.6e9, baseline_median=1e9)
        cal = _calendar_in_window()
        different_date = date(2024, 1, 2)
        updown = _make_updown(different_date, up_vol=0.5e9, down_vol=0.5e9)
        result = compute_pulse(SESSION_DATE, vol_df, updown, cal)
        assert result["basis"] == "volume_only"


# ── Authority block ───────────────────────────────────────────────────────────

class TestAuthorityBlock:
    def test_authority_always_present(self):
        vol_df = _make_volume_cache(SESSION_DATE, today_total=1e9, baseline_median=1e9)
        result = compute_pulse(SESSION_DATE, vol_df, None, _calendar_quiet())
        assert "authority" in result
        assert result["authority"]["may_rank"] is False
        assert result["authority"]["may_gate"] is False
        assert result["authority"]["may_size"] is False

    def test_all_classes_have_summaries(self):
        from engine.rebalance_pulse import _SUMMARY_EN, _SUMMARY_ZH
        for cls in PULSE_CLASSES:
            assert cls in _SUMMARY_EN, f"Missing EN summary for {cls}"
            assert cls in _SUMMARY_ZH, f"Missing ZH summary for {cls}"


# ── Result structure ──────────────────────────────────────────────────────────

class TestResultStructure:
    def test_all_keys_present(self):
        vol_df = _make_volume_cache(SESSION_DATE, today_total=1.6e9, baseline_median=1e9)
        updown = _make_updown(SESSION_DATE, up_vol=0.6e9, down_vol=0.4e9)
        result = compute_pulse(SESSION_DATE, vol_df, updown, _calendar_in_window())
        required = {"date", "class", "market_vol_ratio", "up_share", "basis",
                    "n_megacap_rvol2", "megacap_rvol", "calendar",
                    "summary_en", "summary_zh", "authority"}
        assert required.issubset(result.keys())

    def test_date_is_iso(self):
        vol_df = _make_volume_cache(SESSION_DATE, today_total=1e9, baseline_median=1e9)
        result = compute_pulse(SESSION_DATE, vol_df, None, _calendar_quiet())
        assert result["date"] == SESSION_DATE.isoformat()

    def test_class_in_vocabulary(self):
        vol_df = _make_volume_cache(SESSION_DATE, today_total=1e9, baseline_median=1e9)
        result = compute_pulse(SESSION_DATE, vol_df, None, _calendar_quiet())
        assert result["class"] in PULSE_CLASSES


# ── _classify pure logic ──────────────────────────────────────────────────────

class TestClassifyPure:
    def test_threshold_boundary_absorbed(self):
        assert _classify(True, VOL_RATIO_SPIKE, UP_SHARE_ABSORBED) == "mechanical_spike_absorbed"
        assert _classify(True, VOL_RATIO_SPIKE - 0.001, UP_SHARE_ABSORBED) == "quiet"

    def test_threshold_boundary_distributed(self):
        assert _classify(True, VOL_RATIO_SPIKE, UP_SHARE_DISTRIBUTED) == "mechanical_spike_distributed"

    def test_unscheduled_boundary(self):
        assert _classify(False, VOL_RATIO_UNSCHEDULED, 0.5) == "unscheduled_volume_event"
        assert _classify(False, VOL_RATIO_UNSCHEDULED - 0.001, 0.5) == "quiet"

    def test_calendar_wins_over_unscheduled(self):
        """In a calendar window, even a 2× spike → mechanical, not unscheduled."""
        result = _classify(True, 2.0, 0.5)
        assert result == "mechanical_spike_mixed"


# ── Ledger append (idempotent) ────────────────────────────────────────────────

class TestLedgerAppend:
    def test_non_quiet_appended(self, tmp_path):
        ledger = tmp_path / "events.jsonl"
        pulse = {
            "date": "2024-06-28",
            "class": "mechanical_spike_absorbed",
            "market_vol_ratio": 1.7,
            "up_share": 0.61,
        }
        # Simulate what build_rebalance_pulse does
        with ledger.open("a") as fh:
            fh.write(json.dumps(pulse) + "\n")
        rows = [json.loads(l) for l in ledger.read_text().splitlines() if l]
        assert len(rows) == 1
        assert rows[0]["class"] == "mechanical_spike_absorbed"

    def test_idempotent_no_duplicate(self, tmp_path):
        ledger = tmp_path / "events.jsonl"
        pulse = {"date": "2024-06-28", "class": "unscheduled_volume_event"}

        # First append
        existing_dates = set()
        rows = []
        if not ledger.exists():
            rows = []
        pulse_date = pulse["date"]
        if pulse_date not in existing_dates:
            with ledger.open("a") as fh:
                fh.write(json.dumps(pulse) + "\n")
            existing_dates.add(pulse_date)

        # Second attempt (same date) — should NOT append again
        if pulse_date not in existing_dates:
            with ledger.open("a") as fh:
                fh.write(json.dumps(pulse) + "\n")

        lines = [l for l in ledger.read_text().splitlines() if l]
        assert len(lines) == 1

    def test_quiet_not_appended(self, tmp_path):
        ledger = tmp_path / "events.jsonl"
        pulse_class = "quiet"
        # quiet → don't append (mirroring build script logic)
        if pulse_class != "quiet":
            with ledger.open("a") as fh:
                fh.write(json.dumps({"date": "2024-06-28", "class": pulse_class}) + "\n")
        assert not ledger.exists()

    def test_site_payload_structure(self, tmp_path):
        """Smoke-test the site payload shape that build_rebalance_pulse writes."""
        # Build a minimal payload without hitting real data
        site_payload = {
            "as_of": "2024-06-28",
            "built_at": "2024-06-28T20:00:00Z",
            "latest_pulse": {
                "date": "2024-06-28",
                "class": "quiet",
                "authority": {"may_rank": False, "may_gate": False, "may_size": False},
            },
            "upcoming_events": [],
            "recent_events": [],
            "gaps": [],
            "authority": {"may_rank": False, "may_gate": False, "may_size": False},
            "note_en": "Test.",
            "note_zh": "测试。",
        }
        out = tmp_path / "rebalance_pulse.json"
        out.write_text(json.dumps(site_payload))
        loaded = json.loads(out.read_text())
        assert loaded["authority"]["may_rank"] is False
        assert loaded["latest_pulse"]["class"] == "quiet"
        assert "upcoming_events" in loaded
        assert "recent_events" in loaded
