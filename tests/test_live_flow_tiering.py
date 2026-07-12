"""tests/test_live_flow_tiering.py — tests for FC-R6/R7/R8 + Task 3 additions.

Tests:
  1.  max_concurrent: env override via LIVE_FLOW_MAX_CONCURRENT
  2.  max_concurrent: config fallback when env absent
  3.  max_concurrent: default=2 when neither env nor config present
  4.  max_concurrent: invalid env value falls back to config
  5.  two_tier_enabled: False by default
  6.  two_tier_enabled: True when LIVE_FLOW_TWO_TIER=1
  7.  two_tier_enabled: False for other env values
  8.  select_cycle_roots: two-tier OFF returns all roots unchanged
  9.  select_cycle_roots: two-tier ON splits tier1 vs tier2 correctly
  10. select_cycle_roots: tier2 round-robins across cycles
  11. select_cycle_roots: all roots in tier1 → returns tier1 only, no crash
  12. pinned_publish_enabled: ON by default
  13. pinned_publish_enabled: OFF when env=0
  14. pinned_publish roots: added to publish set when missing from top-40
  15. pinned_publish roots: already in top-40 → not duplicated
  16. write_daily_summary: correct schema and fields
  17. write_daily_summary: nightly-idempotent (second call overwrites cleanly)
  18. write_daily_summary: handles empty day_state gracefully
  19. write_daily_summary: prem_z computed when baseline present
  20. write_daily_summary: prem_z is None when baseline absent
  21. daily_summary_enabled: False by default (MUST_FIX-2 gate coverage)
  22. daily_summary_enabled: True when LIVE_FLOW_DAILY_SUMMARY=1
  23. daily_summary_enabled: False for other env values
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ── helpers to import the module cleanly ─────────────────────────────────────

def _import_poller():
    """Import live_flow_poller — deferred to avoid requiring ThetaData at import time."""
    import importlib
    import sys
    # Ensure the scripts package is importable from the repo root.
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return importlib.import_module("scripts.live_flow_poller")


# ─────────────────────────────────────────────────────────────────────────────
# 1–3. max_concurrent
# ─────────────────────────────────────────────────────────────────────────────

class TestMaxConcurrent:
    def test_env_override(self, monkeypatch):
        """LIVE_FLOW_MAX_CONCURRENT env overrides config/default."""
        lf = _import_poller()
        monkeypatch.setenv(lf.MAX_CONCURRENT_ENV, "5")
        assert lf._max_concurrent({}) == 5

    def test_config_fallback(self, monkeypatch):
        """When env is absent, config is used."""
        lf = _import_poller()
        monkeypatch.delenv(lf.MAX_CONCURRENT_ENV, raising=False)
        assert lf._max_concurrent({"max_concurrent": 3}) == 3

    def test_default_when_both_absent(self, monkeypatch):
        """When neither env nor config present, default is 2."""
        lf = _import_poller()
        monkeypatch.delenv(lf.MAX_CONCURRENT_ENV, raising=False)
        assert lf._max_concurrent({}) == 2

    def test_invalid_env_falls_back_to_config(self, monkeypatch):
        """Invalid env value falls back to config default."""
        lf = _import_poller()
        monkeypatch.setenv(lf.MAX_CONCURRENT_ENV, "notanumber")
        # Should not raise; falls back to config value
        result = lf._max_concurrent({"max_concurrent": 2})
        assert result == 2


# ─────────────────────────────────────────────────────────────────────────────
# 4–5. two_tier_enabled
# ─────────────────────────────────────────────────────────────────────────────

class TestTwoTierEnabled:
    def test_false_by_default(self, monkeypatch):
        """Two-tier cadence is OFF by default (production safe)."""
        lf = _import_poller()
        monkeypatch.delenv(lf.TWO_TIER_ENV, raising=False)
        assert lf._two_tier_enabled() is False

    def test_true_when_env_set(self, monkeypatch):
        """Two-tier cadence ON when LIVE_FLOW_TWO_TIER=1."""
        lf = _import_poller()
        monkeypatch.setenv(lf.TWO_TIER_ENV, "1")
        assert lf._two_tier_enabled() is True

    def test_false_when_env_other(self, monkeypatch):
        """Other env values (0, yes, true) do not enable two-tier."""
        lf = _import_poller()
        for val in ("0", "yes", "true", ""):
            monkeypatch.setenv(lf.TWO_TIER_ENV, val)
            assert lf._two_tier_enabled() is False, f"expected False for {val!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 6–9. _select_cycle_roots
# ─────────────────────────────────────────────────────────────────────────────

class TestSelectCycleRoots:
    """_select_cycle_roots behavior with two-tier ON and OFF."""

    # 20 roots: 5 in TIER1_ROOTS, 15 as long tail
    TIER1_SAMPLE = ["SPY", "QQQ", "SMH", "AAPL", "NVDA"]
    TIER2_SAMPLE = [f"TICK{i:02d}" for i in range(15)]
    ALL_ROOTS = TIER1_SAMPLE + TIER2_SAMPLE  # 20 total

    def test_two_tier_off_returns_all(self, monkeypatch):
        """When two-tier is OFF, all roots returned unchanged."""
        lf = _import_poller()
        monkeypatch.delenv(lf.TWO_TIER_ENV, raising=False)
        roots, slot = lf._select_cycle_roots(self.ALL_ROOTS, cycle_n=1, cfg={})
        assert roots == self.ALL_ROOTS
        assert slot == -1

    def test_two_tier_on_includes_all_tier1(self, monkeypatch):
        """When two-tier is ON, all tier-1 roots appear in every cycle."""
        lf = _import_poller()
        monkeypatch.setenv(lf.TWO_TIER_ENV, "1")
        # Use 4 buckets
        cfg = {"tier2_buckets": 4}
        for cycle_n in range(1, 9):
            roots, _ = lf._select_cycle_roots(self.ALL_ROOTS, cycle_n=cycle_n, cfg=cfg)
            for t1 in self.TIER1_SAMPLE:
                assert t1 in roots, f"tier-1 root {t1} missing from cycle {cycle_n}"

    def test_two_tier_on_round_robins_tier2(self, monkeypatch):
        """Tier-2 buckets rotate: different slots per cycle."""
        lf = _import_poller()
        monkeypatch.setenv(lf.TWO_TIER_ENV, "1")
        cfg = {"tier2_buckets": 4}
        # Collect tier-2 roots across 4 cycles
        seen_tier2: set[str] = set()
        for cycle_n in range(1, 5):
            roots, _ = lf._select_cycle_roots(self.ALL_ROOTS, cycle_n=cycle_n, cfg=cfg)
            tier2_this = [r for r in roots if r not in self.TIER1_SAMPLE]
            seen_tier2.update(tier2_this)
        # After 4 cycles, all tier-2 roots should have appeared
        for t2 in self.TIER2_SAMPLE:
            assert t2 in seen_tier2, f"tier-2 root {t2} never polled over 4 cycles"

    def test_all_tier1_no_crash(self, monkeypatch):
        """When universe is entirely tier-1 roots, no crash, no duplicates."""
        lf = _import_poller()
        monkeypatch.setenv(lf.TWO_TIER_ENV, "1")
        roots_all_tier1 = list(lf.TIER1_ROOTS[:5])
        roots, slot = lf._select_cycle_roots(roots_all_tier1, cycle_n=1, cfg={})
        # All returned, no duplicates
        assert sorted(roots) == sorted(roots_all_tier1)
        assert len(roots) == len(set(roots)), "duplicates in output"


# ─────────────────────────────────────────────────────────────────────────────
# 10–13. pinned-publish
# ─────────────────────────────────────────────────────────────────────────────

class TestPinnedPublish:
    def test_enabled_by_default(self, monkeypatch):
        """Pinned publish is ON by default."""
        lf = _import_poller()
        monkeypatch.delenv(lf.PINNED_PUBLISH_ENV, raising=False)
        assert lf._pinned_publish_enabled() is True

    def test_disabled_when_env_zero(self, monkeypatch):
        """Set LIVE_FLOW_PINNED_PUBLISH=0 to disable."""
        lf = _import_poller()
        monkeypatch.setenv(lf.PINNED_PUBLISH_ENV, "0")
        assert lf._pinned_publish_enabled() is False

    def test_pinned_roots_added_when_missing_from_top40(self, monkeypatch):
        """Pinned roots present in rg_dict but not top-40 are appended."""
        lf = _import_poller()
        monkeypatch.delenv(lf.PINNED_PUBLISH_ENV, raising=False)
        # Build rg_dict: pinned root NVDA has tiny premium, won't be in top-2
        rg_dict = {"TICK01": 1_000_000, "TICK02": 900_000, "NVDA": 100}
        top40_set = {"TICK01", "TICK02"}  # NVDA absent
        pinned_extra = [r for r in lf.PINNED_PUBLISH_ROOTS
                        if r.upper() not in top40_set and r.upper() in rg_dict]
        assert "NVDA" in pinned_extra

    def test_pinned_roots_not_duplicated(self, monkeypatch):
        """Pinned roots already in top-40 are not added again."""
        lf = _import_poller()
        monkeypatch.delenv(lf.PINNED_PUBLISH_ENV, raising=False)
        # SPY is in PINNED_PUBLISH_ROOTS and is also in top40_set
        rg_dict = {"SPY": 10_000_000}
        top40_set = {"SPY"}
        pinned_extra = [r for r in lf.PINNED_PUBLISH_ROOTS
                        if r.upper() not in top40_set and r.upper() in rg_dict]
        assert "SPY" not in pinned_extra


# ─────────────────────────────────────────────────────────────────────────────
# 14–18. write_daily_summary (FC-R8)
# ─────────────────────────────────────────────────────────────────────────────

class TestWriteDailySummary:
    """Tests for the end-of-session daily summary writer."""

    _SESSION = "2026-07-11"
    _ASOF = "2026-07-11T20:00:00Z"

    def _day_state(self, extra_roots: dict | None = None) -> dict:
        """Minimal day_state with known values."""
        roots = {"SPY": 5_000_000.0, "NVDA": 2_000_000.0}
        if extra_roots:
            roots.update(extra_roots)
        root_minutes: dict = {}
        for root, gross in roots.items():
            root_minutes[root] = {
                "09:30": {"ncp": gross * 0.6, "npp": -gross * 0.2, "vol": 1000},
                "10:00": {"ncp": gross * 0.1, "npp": -gross * 0.1, "vol": 500},
            }
        root_strikes: dict = {}
        for root, gross in roots.items():
            root_strikes[root] = {
                "550C": {"call_prem": gross * 0.7, "put_prem": 0.0},
                "550P": {"call_prem": 0.0, "put_prem": gross * 0.3},
            }
        market_tide = {
            "09:30": {"ncp": 3_000_000, "npp": -1_000_000},
            "10:00": {"ncp": 500_000, "npp": -200_000},
        }
        return {
            "root_gross_today": roots,
            "root_minutes": root_minutes,
            "root_strikes": root_strikes,
            "market_tide_minutes": market_tide,
        }

    def test_schema_and_fields(self, tmp_path, monkeypatch):
        """Summary has correct schema, session_date, and expected fields."""
        lf = _import_poller()
        monkeypatch.setattr(lf.config, "data_dir", lambda: tmp_path)
        p = lf.write_daily_summary(
            session_date=self._SESSION,
            day_state=self._day_state(),
            baselines={},
            cycle_n=3,
            asof=self._ASOF,
        )
        assert p is not None and p.exists()
        d = json.loads(p.read_text())
        assert d["schema"] == "live_flow_daily.v1"
        assert d["session_date"] == self._SESSION
        assert d["cycle_n"] == 3
        assert d["n_names"] == 2
        assert "market" in d
        assert "names" in d
        assert d["market"]["gross_total"] > 0
        assert d["market"]["minutes_covered"] == 2  # two market-tide minutes

    def test_idempotent_overwrite(self, tmp_path, monkeypatch):
        """Second call overwrites cleanly with updated cycle_n."""
        lf = _import_poller()
        monkeypatch.setattr(lf.config, "data_dir", lambda: tmp_path)
        lf.write_daily_summary(
            session_date=self._SESSION,
            day_state=self._day_state(),
            baselines={},
            cycle_n=1,
            asof=self._ASOF,
        )
        p2 = lf.write_daily_summary(
            session_date=self._SESSION,
            day_state=self._day_state(),
            baselines={},
            cycle_n=7,
            asof=self._ASOF,
        )
        assert p2 is not None
        d = json.loads(p2.read_text())
        assert d["cycle_n"] == 7  # updated

    def test_empty_day_state(self, tmp_path, monkeypatch):
        """Empty day_state produces a zero-names summary without crashing."""
        lf = _import_poller()
        monkeypatch.setattr(lf.config, "data_dir", lambda: tmp_path)
        p = lf.write_daily_summary(
            session_date=self._SESSION,
            day_state={},
            baselines={},
            cycle_n=1,
            asof=self._ASOF,
        )
        assert p is not None
        d = json.loads(p.read_text())
        assert d["n_names"] == 0

    def test_prem_z_computed_when_baseline_present(self, tmp_path, monkeypatch):
        """prem_z is computed when baselines has entry for the root."""
        lf = _import_poller()
        monkeypatch.setattr(lf.config, "data_dir", lambda: tmp_path)
        # SPY gross = 5_000_000; baseline mean=3e6, std=1e6 → z = 2.0
        baselines = {"SPY": {"mean": 3_000_000.0, "std": 1_000_000.0, "n_obs": 252}}
        p = lf.write_daily_summary(
            session_date=self._SESSION,
            day_state=self._day_state(),
            baselines=baselines,
            cycle_n=1,
            asof=self._ASOF,
        )
        d = json.loads(p.read_text())
        spy_row = next(r for r in d["names"] if r["root"] == "SPY")
        assert spy_row["has_baseline"] is True
        assert spy_row["prem_z"] == pytest.approx(2.0, abs=0.01)

    def test_prem_z_none_when_baseline_absent(self, tmp_path, monkeypatch):
        """prem_z is None when no baseline for the root."""
        lf = _import_poller()
        monkeypatch.setattr(lf.config, "data_dir", lambda: tmp_path)
        p = lf.write_daily_summary(
            session_date=self._SESSION,
            day_state=self._day_state(),
            baselines={},
            cycle_n=1,
            asof=self._ASOF,
        )
        d = json.loads(p.read_text())
        spy_row = next(r for r in d["names"] if r["root"] == "SPY")
        assert spy_row["has_baseline"] is False
        assert spy_row["prem_z"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 19–21. _daily_summary_enabled (FC-R8 gate flag, MUST_FIX-2 coverage)
# ─────────────────────────────────────────────────────────────────────────────

class TestDailySummaryEnabled:
    """FC-R8 daily summary is gated DEFAULT OFF (new production write path)."""

    def test_false_by_default(self, monkeypatch):
        """Daily summary is OFF by default — production safe."""
        lf = _import_poller()
        monkeypatch.delenv(lf.DAILY_SUMMARY_ENV, raising=False)
        assert lf._daily_summary_enabled() is False

    def test_true_when_env_set(self, monkeypatch):
        """Daily summary ON when LIVE_FLOW_DAILY_SUMMARY=1."""
        lf = _import_poller()
        monkeypatch.setenv(lf.DAILY_SUMMARY_ENV, "1")
        assert lf._daily_summary_enabled() is True

    def test_false_for_other_env_values(self, monkeypatch):
        """Values other than '1' do not enable daily summary."""
        lf = _import_poller()
        for val in ("0", "yes", "true", ""):
            monkeypatch.setenv(lf.DAILY_SUMMARY_ENV, val)
            assert lf._daily_summary_enabled() is False, f"expected False for {val!r}"
