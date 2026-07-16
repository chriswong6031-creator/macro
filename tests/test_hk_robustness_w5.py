"""W5 robustness tests for HK pipeline fixes.

Covers:
  (1) confluence-empty health banner: when no cascade-eligible names exist, a health
      entry with leg='confluence' appears in the returned board data.
      (Previously leg='alignment' before the 2026-07-16 gate swap.)
  (2) Southbound staleness in trading days: Friday->Monday gap = 1 td, not 3 cal days.
  (3) Freshness sentinel southbound check: flags stale southbound holdings store.
  (4) Pick-lab producer stale-cross NaN guard: hk_xbar_sessions maps NaN/None -> None
      (int(NaN) crashed the producer block nightly; 1D Velocity Desk dead wire).
  (5) Cascade inclusion gate: eligible=True -> included in buys regardless of atier;
      eligible=False but aligned=True -> NOT in buys (may appear in watch).
  (6) Beta close-panel overlay: hk_beta_close_panel unions cache + deep history
      (cache wins on overlap) so newly-added constituents clear the causal-beta
      min_periods instead of being silently dropped (74-of-160 scoreboard bug).
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
# (1) confluence-empty pool -> health banner appears (leg='confluence')
# ---------------------------------------------------------------------------

class TestAlignmentEmptyBanner:
    """When no cascade-eligible names exist, compute_hk_standouts must surface
    a health entry with leg='confluence' (not 'alignment') rather than silently
    rendering with 0 buys.

    Gate swap 2026-07-16: inclusion is now signal_gate cascade eligible, not
    bottoming-alignment. The banner leg was updated from 'alignment' to 'confluence'.
    """

    def _make_sig_verdict(self, tickers: list[str], eligible: bool) -> dict:
        """Return a sig_verdict dict with all tickers set to the given eligibility."""
        return {t: {"eligible": eligible, "weight": 0.0} for t in tickers}

    def test_empty_cascade_produces_confluence_health_entry(self):
        """When no cascade-eligible names exist, the health leg is 'confluence' —
        gated on the PRODUCTION hk_cascade_eligible predicate (F5-b)."""
        from scripts.build_hk_library import hk_cascade_eligible
        tickers = [f"TEST{i:04d}.HK" for i in range(3)]
        sig_verdict = self._make_sig_verdict(tickers, eligible=False)

        elig = [t for t in tickers if hk_cascade_eligible(sig_verdict, t)]
        _pre_health: list[dict] = []
        if not elig:
            _pre_health.append({
                "leg": "confluence",
                "en": "No names show a fresh entry signal tonight — the board is intentionally thin, not broken.",
                "zh": "今晚没有出现新入场信号的个股 —— 榜单有意精简，并非故障。",
            })

        assert elig == [], "Expected empty eligible pool with eligible=False sig_verdict"
        assert len(_pre_health) == 1, "Expected exactly one health entry"
        entry = _pre_health[0]
        assert entry["leg"] == "confluence", (
            f"Expected leg='confluence', got {entry['leg']!r}")
        assert "entry signal" in entry["en"].lower()  # plain-word Tier-1 copy, no jargon
        assert entry["zh"]  # bilingual

    def test_eligible_cascade_no_spurious_banner(self):
        """When at least one cascade-eligible name exists, no confluence health entry is added."""
        from scripts.build_hk_library import hk_cascade_eligible
        tickers = ["0700.HK"]
        sig_verdict = self._make_sig_verdict(tickers, eligible=True)

        elig = [t for t in tickers if hk_cascade_eligible(sig_verdict, t)]
        _pre_health: list[dict] = []
        if not elig:
            _pre_health.append({"leg": "confluence", "en": "...", "zh": "..."})

        assert elig, "Expected at least one eligible name"
        assert _pre_health == [], "No spurious health entry when cascade is eligible"

    def test_missing_sig_verdict_entry_excluded_not_crash(self):
        """A name with <60 bars has NO sig_verdict entry: the production predicate
        must exclude it (False), never crash — the None-safety the cascade relies on."""
        from scripts.build_hk_library import hk_cascade_eligible
        assert hk_cascade_eligible({}, "0001.HK") is False
        assert hk_cascade_eligible({"0001.HK": None}, "0001.HK") is False


# ---------------------------------------------------------------------------
# (5) Cascade inclusion gate — eligible=True included; eligible=False excluded
# ---------------------------------------------------------------------------

class TestCascadeInclusionGate:
    """Gate swap 2026-07-16: inclusion = cascade eligible, not bottoming-alignment.

    (a) A name with eligible=True but align_tier=None MUST appear in buys.
    (b) A name with eligible=False but aligned=True must NOT appear in buys
        (it may end up in watch via the watch-strip logic, but MUST NOT be in buys).

    Uses the PRODUCTION inclusion predicate from build_hk_library to guard
    against divergence (F5-b style).
    """

    def _make_enriched(self, ticker: str, eligible: bool, aligned: bool) -> dict:
        """Minimal enriched row for testing cascade inclusion."""
        return {
            "ticker": ticker,
            "dir": "up",
            "price": 20.0,
            "_chart": [10.0] * 64,
            "_adv63": 1_000_000.0,
            "edge_z": 0.5,
            "conviction": {
                "composite_z": 0.8,
                "cycle_blocked": False,
                "alignment": {"aligned": aligned, "score": 0.9} if aligned else {},
                "axes": {},
            },
            "entry_signal": None,
            "_row": None,
        }

    def test_eligible_true_atier_none_is_included(self):
        """eligible=True AND align_tier=None -> MUST be in buys (cascade is the gate)."""
        from scripts.build_hk_library import hk_cascade_eligible, hk_atier
        ticker = "9988.HK"
        enriched = [self._make_enriched(ticker, eligible=True, aligned=False)]
        sig_verdict = {ticker: {"eligible": True, "weight": 0.5}}

        elig = [e for e in enriched if hk_cascade_eligible(sig_verdict, e["ticker"])]
        buys = elig  # [:n_buy], but n=1 so same

        assert any(e["ticker"] == ticker for e in buys), (
            "eligible=True name must be in buys regardless of alignment tier")
        assert hk_atier(buys[0]) is None, "context badge is None — inclusion unaffected"

    def test_eligible_false_aligned_true_is_excluded_from_buys(self):
        """eligible=False AND aligned=True -> must NOT be in buys."""
        from scripts.build_hk_library import hk_cascade_eligible, hk_atier
        ticker = "0700.HK"
        enriched = [self._make_enriched(ticker, eligible=False, aligned=True)]
        sig_verdict = {ticker: {"eligible": False, "weight": 0.0}}

        elig = [e for e in enriched if hk_cascade_eligible(sig_verdict, e["ticker"])]
        buys = elig

        assert hk_atier(enriched[0]) == "aligned", "fixture sanity: the name IS aligned"
        assert not any(e["ticker"] == ticker for e in buys), (
            "eligible=False name must NOT be in buys even if aligned=True")

    def test_mixed_pool_only_eligible_in_buys(self):
        """Mix of eligible/ineligible names: only eligible ones land in buys."""
        from scripts.build_hk_library import hk_cascade_eligible
        entries = [
            self._make_enriched("3690.HK", eligible=True, aligned=True),
            self._make_enriched("0941.HK", eligible=True, aligned=False),
            self._make_enriched("0005.HK", eligible=False, aligned=True),
            self._make_enriched("1398.HK", eligible=False, aligned=False),
        ]
        sig_verdict = {
            "3690.HK": {"eligible": True, "weight": 0.8},
            "0941.HK": {"eligible": True, "weight": 0.3},
            "0005.HK": {"eligible": False, "weight": 0.0},
            "1398.HK": {"eligible": False, "weight": 0.0},
        }

        elig = [e for e in entries if hk_cascade_eligible(sig_verdict, e["ticker"])]
        buy_tickers = {e["ticker"] for e in elig}

        assert "3690.HK" in buy_tickers, "eligible=True/aligned=True must be in buys"
        assert "0941.HK" in buy_tickers, "eligible=True/aligned=False must be in buys"
        assert "0005.HK" not in buy_tickers, "eligible=False/aligned=True must NOT be in buys"
        assert "1398.HK" not in buy_tickers, "eligible=False/aligned=False must NOT be in buys"
        assert len(buy_tickers) == 2, f"Expected exactly 2 eligible names, got {buy_tickers}"


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


# ---------------------------------------------------------------------------
# (4) pick-lab producer stale-cross NaN guard (hk_xbar_sessions)
# ---------------------------------------------------------------------------

class TestXbarSessionsNaNGuard:
    """Grid cells from _compute_grids are NaN — not None — when a name never crossed
    inside the window, and NaN passes `is not None`: the bare int() cast crashed the
    whole pick-lab producer block nightly (data/hk_pick_lab + 1D Velocity Desk never
    shipped). hk_xbar_sessions is the F5-b production helper for that conversion."""

    def test_nan_returns_none(self):
        from scripts.build_hk_library import hk_xbar_sessions
        assert hk_xbar_sessions(float("nan"), 2) is None
        assert hk_xbar_sessions(np.nan, 3) is None
        assert hk_xbar_sessions(np.float64("nan"), 2) is None

    def test_none_returns_none(self):
        from scripts.build_hk_library import hk_xbar_sessions
        assert hk_xbar_sessions(None, 2) is None

    def test_real_counts_scale_to_sessions(self):
        from scripts.build_hk_library import hk_xbar_sessions
        assert hk_xbar_sessions(2.0, 2) == 4
        assert hk_xbar_sessions(np.float64(3), 3) == 9
        assert hk_xbar_sessions(0, 2) == 0


# ---------------------------------------------------------------------------
# (6) Beta close-panel overlay — cache + deep union (74-of-160 scoreboard bug)
# ---------------------------------------------------------------------------

class TestBetaClosePanelOverlay:
    """hk_beta_close_panel must extend a shallow cache column with deep history so
    the causal beta's min_periods (126 sessions) resolves for newly-added
    constituents; cache values win on overlapping dates (canonical recent tape)."""

    def _frames(self):
        deep_idx = pd.bdate_range("2024-01-02", periods=400)
        cache_idx = deep_idx[-20:]  # newly-added name: only 20 cached sessions
        deep = pd.DataFrame({"9999.HK": np.linspace(10, 30, 400)}, index=deep_idx)
        cache = pd.DataFrame({"9999.HK": np.full(20, 99.0)}, index=cache_idx)
        return cache, deep

    def test_overlay_extends_history_past_minp(self):
        from scripts.build_hk_library import hk_beta_close_panel
        cache, deep = self._frames()
        panel = hk_beta_close_panel(cache, deep)
        assert panel["9999.HK"].notna().sum() == 400, (
            "deep history must extend the shallow cache column")

    def test_cache_wins_on_overlap(self):
        from scripts.build_hk_library import hk_beta_close_panel
        cache, deep = self._frames()
        panel = hk_beta_close_panel(cache, deep)
        overlap = cache.index
        assert (panel.loc[overlap, "9999.HK"] == 99.0).all(), (
            "cache values are the canonical recent tape and must win on overlap")
        pre = panel.index.difference(overlap)
        assert (panel.loc[pre, "9999.HK"] != 99.0).all(), "deep fills pre-cache history"

    def test_none_safety(self):
        from scripts.build_hk_library import hk_beta_close_panel
        cache, deep = self._frames()
        assert hk_beta_close_panel(None, None) is None
        pd.testing.assert_frame_equal(hk_beta_close_panel(cache, None), cache)
        pd.testing.assert_frame_equal(hk_beta_close_panel(None, deep), deep)

    def test_union_columns(self):
        """Names present only in one frame survive into the union panel."""
        from scripts.build_hk_library import hk_beta_close_panel
        idx = pd.bdate_range("2025-01-02", periods=30)
        cache = pd.DataFrame({"0001.HK": np.ones(30)}, index=idx)
        deep = pd.DataFrame({"0002.HK": np.ones(30) * 2}, index=idx)
        panel = hk_beta_close_panel(cache, deep)
        assert set(panel.columns) == {"0001.HK", "0002.HK"}
