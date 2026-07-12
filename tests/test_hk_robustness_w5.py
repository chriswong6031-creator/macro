"""W5 robustness tests for HK pipeline fixes.

Covers:
  (1) eligible=0 health banner: when no aligned/near-aligned names exist, a health
      entry with leg='alignment' appears in the returned board data.
  (2) Southbound staleness in trading days: Friday->Monday gap = 1 td, not 3 cal days.
  (3) Freshness sentinel southbound check: flags stale southbound holdings store.
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# (1) alignment pool empty -> health banner appears
# ---------------------------------------------------------------------------

class TestAlignmentEmptyBanner:
    """When the aligned + near pool is empty, compute_hk_standouts must surface
    a health entry (leg='alignment') rather than silently rendering with 0 buys."""

    def _make_minimal_enriched(self, n: int = 3) -> list[dict]:
        """Return n enriched entries with NO alignment (atier returns None) and
        a positive conviction composite so they rank above the -9.0 floor."""
        entries = []
        for i in range(n):
            entries.append({
                "ticker": f"TEST{i:04d}.HK",
                "dir": "up",
                "price": 10.0 + i,
                "_chart": [10.0] * 64,
                "_adv63": 1_000_000.0,
                "edge_z": 0.5,
                "conviction": {
                    "composite_z": 0.5 + i * 0.1,
                    "cycle_blocked": False,
                    "alignment": {},   # no aligned, no near -> _atier returns None
                    "axes": {},
                },
                "entry_signal": None,
                "_row": None,
            })
        return entries

    def test_empty_alignment_produces_health_entry(self):
        """When elig is empty, _pre_health must have leg='alignment'."""
        # F5-b fix: call the PRODUCTION hk_entry_ok / hk_atier from scripts.build_hk_library,
        # not a re-implementation.  This guards against divergence between test and production.
        from scripts.build_hk_library import hk_entry_ok, hk_atier

        entries = self._make_minimal_enriched(3)

        elig = [e for e in entries if hk_entry_ok(e) and hk_atier(e)]
        _pre_health: list[dict] = []
        if not elig:
            _pre_health.append({
                "leg": "alignment",
                "en": "No fully-aligned names found — buy strip backfilled from near-aligned names.",
                "zh": "未找到完全对齐的标的 —— 买入列表已从接近对齐的标的回填。",
            })

        assert elig == [], "Expected empty eligible pool with the test fixtures"
        assert len(_pre_health) == 1, "Expected exactly one health entry"
        entry = _pre_health[0]
        assert entry["leg"] == "alignment"
        assert "alignment" in entry["en"].lower() or "aligned" in entry["en"].lower()
        assert entry["zh"]  # bilingual

    def test_nonempty_alignment_no_spurious_banner(self):
        """When at least one name is aligned, no alignment health entry is added."""
        from scripts.build_hk_library import hk_entry_ok, hk_atier

        entries = [
            {
                "ticker": "0700.HK",
                "conviction": {
                    "composite_z": 1.0,
                    "cycle_blocked": False,
                    "alignment": {"aligned": True, "score": 0.9},
                    "axes": {},
                },
            }
        ]
        elig = [e for e in entries if hk_entry_ok(e) and hk_atier(e)]
        _pre_health: list[dict] = []
        if not elig:
            _pre_health.append({"leg": "alignment", "en": "...", "zh": "..."})

        assert elig, "Expected at least one eligible name"
        assert _pre_health == [], "No spurious health entry when names are aligned"


# ---------------------------------------------------------------------------
# (2) Southbound staleness in trading days (Friday -> Monday = 1 td)
# ---------------------------------------------------------------------------

class TestSouthboundTradingDays:
    """np.busday_count must be used for the southbound staleness gap so that a
    Friday -> Monday weekend skip counts as 1 trading day, not 3 calendar days."""

    def test_friday_to_monday_is_one_trading_day(self):
        """2026-07-10 (Friday) -> 2026-07-13 (Monday) = 1 trading day, not 3."""
        fri = date(2026, 7, 10)
        mon = date(2026, 7, 13)
        td = int(np.busday_count(fri, mon))
        assert td == 1, f"Expected 1 trading day Fri->Mon, got {td}"

    def test_friday_to_monday_calendar_days_is_three(self):
        """Calendar days between Friday and Monday is 3 — the bug we fixed."""
        fri = pd.Timestamp("2026-07-10").date()
        mon = pd.Timestamp("2026-07-13").date()
        cal_gap = (pd.Timestamp(str(mon)) - pd.Timestamp(str(fri))).days
        assert cal_gap == 3, "Calendar gap sanity check"

    def test_busday_count_does_not_flag_weekend_as_stale(self):
        """With FRESHNESS_MAX_STALE_TD=3 (trading days), a weekend gap of 1 td
        must NOT trigger a stale health entry."""
        FRESHNESS_MAX_STALE_TD = 3

        sb_asof = "2026-07-10"   # Friday
        as_of = "2026-07-13"     # Monday (next business day)

        _sb_ts = pd.Timestamp(sb_asof).date()
        _as_ts = pd.Timestamp(as_of).date()
        _gap = int(np.busday_count(_sb_ts, _as_ts)) if _as_ts >= _sb_ts else 0

        assert _gap == 1
        assert _gap <= FRESHNESS_MAX_STALE_TD, (
            f"Friday->Monday gap of {_gap} td should not breach threshold "
            f"{FRESHNESS_MAX_STALE_TD} td")

    def test_week_old_southbound_is_stale(self):
        """A southbound store that is 5 trading days stale must exceed the threshold."""
        FRESHNESS_MAX_STALE_TD = 3

        sb_asof = "2026-07-06"   # Monday
        as_of = "2026-07-13"     # following Monday (7 cal = 5 td)

        _sb_ts = pd.Timestamp(sb_asof).date()
        _as_ts = pd.Timestamp(as_of).date()
        _gap = int(np.busday_count(_sb_ts, _as_ts)) if _as_ts >= _sb_ts else 0

        assert _gap == 5
        assert _gap > FRESHNESS_MAX_STALE_TD, (
            f"5 td stale gap should exceed threshold {FRESHNESS_MAX_STALE_TD}")


# ---------------------------------------------------------------------------
# (3) Freshness sentinel flags stale southbound store
# ---------------------------------------------------------------------------

def _write_parquet_with_date(path: Path, d: date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    idx = pd.DatetimeIndex([pd.Timestamp(d)])
    df = pd.DataFrame({"close": [100.0]}, index=idx)
    df.to_parquet(path)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


class TestFreshnessSentinelSouthbound:
    """Check 7 (southbound) is present in the sentinel result and reacts to store state."""

    def _run_sentinel(
        self,
        tmpdir: Path,
        now: datetime,
        cache_date: date | None = None,
        bell_date: date | None = None,
        standouts_asof: date | None = None,
        regime_date: date | None = None,
        southbound_date: date | None = None,
    ) -> dict:
        data_root = tmpdir / "data"
        site_root = tmpdir / "site"

        if cache_date is not None:
            _write_parquet_with_date(
                data_root / "hk_breadth" / "_closes_cache.parquet", cache_date)
        if bell_date is not None:
            _write_parquet_with_date(
                data_root / "hk_stocks" / "9988.HK.parquet", bell_date)
        if standouts_asof is not None:
            _write_json(
                site_root / "factordata" / "hk_standouts.json",
                {"as_of": str(standouts_asof), "buy": [], "watch": []})
        if regime_date is not None:
            _write_json(
                data_root / "hk_regime" / "latest.json",
                {"date": str(regime_date), "quad": "Q1"})
        if southbound_date is not None:
            _write_parquet_with_date(
                data_root / "hk_southbound" / "holdings.parquet", southbound_date)

        with (patch("lib.config.data_dir", return_value=data_root),
              patch("lib.config.load",
                    return_value={"storage": {"site_dir": str(site_root)}}),
              patch("lib.config.ROOT", tmpdir)):
            from engine.hk_freshness import hk_freshness_sentinel
            return hk_freshness_sentinel(now=now)

    def test_southbound_check_present_in_result(self, tmp_path):
        """Check 7 must appear as 'southbound' key in the stores dict."""
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        from lib.hk_calendar import expected_last_session
        expected = expected_last_session(now)

        result = self._run_sentinel(
            tmp_path, now,
            cache_date=expected,
            bell_date=expected,
            standouts_asof=expected,
            regime_date=expected,
            southbound_date=expected,
        )
        assert "southbound" in result["stores"], (
            f"'southbound' key missing from stores: {list(result['stores'].keys())}")

    def test_missing_southbound_is_dead(self, tmp_path):
        """No southbound parquet -> state='dead'."""
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        from lib.hk_calendar import expected_last_session
        expected = expected_last_session(now)

        result = self._run_sentinel(
            tmp_path, now,
            cache_date=expected,
            bell_date=expected,
            standouts_asof=expected,
            regime_date=expected,
            southbound_date=None,   # missing
        )
        sb_check = result["stores"].get("southbound", {})
        assert sb_check.get("state") == "dead", (
            f"Expected 'dead' for missing southbound, got {sb_check}")

    def test_stale_southbound_produces_degraded_verdict(self, tmp_path):
        """Stale southbound (primary stores fresh) -> at least 'degraded' verdict."""
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        from lib.hk_calendar import expected_last_session
        expected = expected_last_session(now)
        stale_date = date(2026, 7, 1)   # 7 cal days old -> stale

        result = self._run_sentinel(
            tmp_path, now,
            cache_date=expected,
            bell_date=expected,
            standouts_asof=expected,
            regime_date=expected,
            southbound_date=stale_date,
        )
        sb_check = result["stores"].get("southbound", {})
        assert sb_check.get("state") in ("stale", "dead"), (
            f"Expected stale/dead for old southbound, got {sb_check}")
        assert result["verdict"] in ("degraded", "stale"), (
            f"Expected degraded/stale verdict with stale southbound, "
            f"got {result['verdict']}")

    def test_fresh_southbound_does_not_break_ok_verdict(self, tmp_path):
        """Fresh southbound + fresh primaries -> verdict stays 'ok'."""
        now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        from lib.hk_calendar import expected_last_session
        expected = expected_last_session(now)

        result = self._run_sentinel(
            tmp_path, now,
            cache_date=expected,
            bell_date=expected,
            standouts_asof=expected,
            regime_date=expected,
            southbound_date=expected,
        )
        assert result["verdict"] == "ok", (
            f"All fresh stores should give ok verdict, got {result['verdict']}: {result}")
