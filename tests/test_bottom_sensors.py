"""tests/test_bottom_sensors.py — Unit tests for engine/neuralweb/bottom_sensors.py

Amendment 1, Lane B0, PR-1.  Tests cover:
  1. Label-precedence for every state in the frozen labels_v1 decision table.
  2. Three adversarial cases from the amendment review:
     (a) launched name with a new fresh fire
     (b) ticks > 2 with tiny dist_21d_low
     (c) washout with 21d-low reclaimed yesterday
  3. Schema determinism test (assemble() returns stable column set).
  4. Earnings per-row staleness test (passed dates dropped, blackout window correct).
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.neuralweb.bottom_sensors import (  # noqa: E402
    _classify_labels_v1,
    _dist_21d_low_pct,
    _dist_126d_high_pct,
    _earnings_info,
    _sponsorship_state,
    _SPONSORSHIP_STALE_TRADING_DAYS,
    LABELS_VERSION,
    IS_DISPLAY_ONLY,
    _ALIGN_KNIFE_BLOCK,
)
from engine.neuralweb.sector_map import SectorMapping


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

TODAY = datetime.date(2026, 7, 5)


def _cls(**kwargs) -> str:
    """Thin wrapper with safe defaults so tests only override what they care about."""
    defaults = dict(
        hold_state=None,
        hold_days_basing=None,
        hold_ret=None,
        trigger_tier=None,
        ticks=None,
        coiled=False,
        dist_21d_low=None,
        dist_126d_high=None,
        bars_to_cross=None,
        knife_score=None,
        knife_available=False,
    )
    defaults.update(kwargs)
    return _classify_labels_v1(**defaults)


def _bdate(n: int, start: str = "2020-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def _price_series(values, start: str = "2020-01-02") -> pd.Series:
    idx = _bdate(len(values), start=start)
    return pd.Series(values, index=idx, dtype=float)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Label-precedence unit tests — every state
# ═══════════════════════════════════════════════════════════════════════════════

class TestLabelPrecedence:

    # ── HOLD_LAUNCHED ─────────────────────────────────────────────────────────

    def test_hold_launched_beats_everything(self):
        """HOLD_LAUNCHED is highest precedence — even with fresh fire + COILED."""
        state = _cls(
            hold_state="launched",
            trigger_tier="T1", ticks=0,
            coiled=True, dist_21d_low=5.0,
        )
        assert state == "HOLD_LAUNCHED"

    def test_hold_launched_beats_chase(self):
        """HOLD_LAUNCHED overrides what would otherwise be CHASE_RISK."""
        state = _cls(
            hold_state="launched",
            trigger_tier="T2", ticks=5,  # stale → would be CHASE_RISK otherwise
            dist_21d_low=20.0,
        )
        assert state == "HOLD_LAUNCHED"

    # ── FRESH_FIRE_DURABLE_CAND ──────────────────────────────────────────────

    def test_fresh_fire_durable_cand_basic(self):
        """T1, ticks=0, coiled=True, dist_21d_low=5% → FRESH_FIRE_DURABLE_CAND."""
        state = _cls(
            trigger_tier="T1", ticks=0,
            coiled=True, dist_21d_low=5.0,
            dist_126d_high=-20.0,
        )
        assert state == "FRESH_FIRE_DURABLE_CAND"

    def test_fresh_fire_durable_cand_t3(self):
        """T3 is also in T1-T3 fresh range."""
        state = _cls(
            trigger_tier="T3", ticks=1,
            coiled=True, dist_21d_low=11.9,
        )
        assert state == "FRESH_FIRE_DURABLE_CAND"

    def test_fresh_fire_durable_cand_boundary(self):
        """Exactly at dist_21d_low = 12.0 (<=12 is inclusive)."""
        state = _cls(
            trigger_tier="T2", ticks=2,
            coiled=True, dist_21d_low=12.0,
        )
        assert state == "FRESH_FIRE_DURABLE_CAND"

    def test_fresh_fire_durable_cand_requires_coiled(self):
        """Without COILED, fresh T1 + dist <= 12 → FRESH_FIRE_TACTICAL, not DURABLE."""
        state = _cls(
            trigger_tier="T1", ticks=0,
            coiled=False, dist_21d_low=5.0,
        )
        assert state == "FRESH_FIRE_TACTICAL"

    # ── FRESH_FIRE_TACTICAL ───────────────────────────────────────────────────

    def test_fresh_fire_tactical_basic(self):
        """T1, ticks=1, coiled=False, dist=8% → FRESH_FIRE_TACTICAL."""
        state = _cls(
            trigger_tier="T1", ticks=1,
            coiled=False, dist_21d_low=8.0,
        )
        assert state == "FRESH_FIRE_TACTICAL"

    def test_fresh_fire_tactical_t2(self):
        """T2 fresh with no COILED → TACTICAL."""
        state = _cls(
            trigger_tier="T2", ticks=0,
            coiled=False, dist_21d_low=3.0,
        )
        assert state == "FRESH_FIRE_TACTICAL"

    # ── CHASE_RISK ────────────────────────────────────────────────────────────

    def test_chase_risk_stale_ticks(self):
        """T1 with ticks=3 (stale) → CHASE_RISK."""
        state = _cls(
            trigger_tier="T1", ticks=3,
            coiled=False, dist_21d_low=5.0,
        )
        assert state == "CHASE_RISK"

    def test_chase_risk_dist_too_far(self):
        """T2 fresh but dist > 12% → CHASE_RISK."""
        state = _cls(
            trigger_tier="T2", ticks=1,
            dist_21d_low=13.0,
        )
        assert state == "CHASE_RISK"

    def test_chase_risk_both_conditions(self):
        """Ticks=4 AND dist=25% → CHASE_RISK."""
        state = _cls(
            trigger_tier="T3", ticks=4,
            dist_21d_low=25.0,
        )
        assert state == "CHASE_RISK"

    def test_chase_risk_t4_excluded(self):
        """T4 is NOT in T1-T3 so does not produce CHASE_RISK via stale-tick path."""
        state = _cls(
            trigger_tier="T4", ticks=10,
            dist_21d_low=25.0,
        )
        # T4 with drawdown and bars_to_cross missing → WATCH
        assert state == "WATCH"

    # ── DEAD_MONEY_RISK ───────────────────────────────────────────────────────

    def test_dead_money_risk_basic(self):
        """Intact hold, 20 days basing, maxup < 4% → DEAD_MONEY_RISK."""
        state = _cls(
            hold_state="intact",
            hold_days_basing=20,
            hold_ret=2.5,
            trigger_tier=None, ticks=None,
        )
        assert state == "DEAD_MONEY_RISK"

    def test_dead_money_risk_at_boundary(self):
        """days_basing=15 (lower bound, inclusive)."""
        state = _cls(
            hold_state="intact",
            hold_days_basing=15,
            hold_ret=1.0,
        )
        assert state == "DEAD_MONEY_RISK"

    def test_dead_money_risk_upper_boundary(self):
        """days_basing=40 (upper bound, inclusive)."""
        state = _cls(
            hold_state="intact",
            hold_days_basing=40,
            hold_ret=3.9,
        )
        assert state == "DEAD_MONEY_RISK"

    def test_dead_money_risk_too_many_days(self):
        """days_basing=41 → not DEAD_MONEY_RISK (falls through to WATCH)."""
        state = _cls(
            hold_state="intact",
            hold_days_basing=41,
            hold_ret=1.0,
        )
        assert state != "DEAD_MONEY_RISK"

    def test_dead_money_risk_ret_too_large(self):
        """ret=4.0 (not < 4%) → not DEAD_MONEY_RISK."""
        state = _cls(
            hold_state="intact",
            hold_days_basing=20,
            hold_ret=4.0,  # must be < 4%, not <=
        )
        assert state != "DEAD_MONEY_RISK"

    # ── EARLY_WATCH ───────────────────────────────────────────────────────────

    def test_early_watch_basic(self):
        """Drawdown >= 15%, bars_to_cross <= 2, no fresh tier → EARLY_WATCH."""
        state = _cls(
            trigger_tier="T4",  # T4 = not a fresh tier (T1-T3)
            ticks=0,
            dist_126d_high=-16.0,
            bars_to_cross=1.5,
        )
        assert state == "EARLY_WATCH"

    def test_early_watch_requires_drawdown(self):
        """bars_to_cross=1 but drawdown < 15% → not EARLY_WATCH."""
        state = _cls(
            trigger_tier=None,
            dist_126d_high=-10.0,  # < 15%
            bars_to_cross=1.0,
        )
        assert state != "EARLY_WATCH"

    def test_early_watch_bars_too_large(self):
        """bars_to_cross=3 > 2 → not EARLY_WATCH."""
        state = _cls(
            trigger_tier=None,
            dist_126d_high=-20.0,
            bars_to_cross=3.0,
        )
        assert state != "EARLY_WATCH"

    # ── KNIFE_RISK ────────────────────────────────────────────────────────────

    def test_knife_risk_bound_field(self):
        """knife_score >= 0.7 with knife_available=True → KNIFE_RISK."""
        state = _cls(
            trigger_tier=None,
            knife_score=0.7,
            knife_available=True,
        )
        assert state == "KNIFE_RISK"

    def test_knife_risk_below_threshold(self):
        """knife_score < 0.7 → not KNIFE_RISK from bound field."""
        state = _cls(
            trigger_tier=None,
            knife_score=0.5,
            knife_available=True,
        )
        assert state != "KNIFE_RISK"

    def test_knife_risk_fallback(self):
        """knife_available=False, drawdown >= 15%, dist_21d_low <= 0 → KNIFE_RISK fallback."""
        state = _cls(
            trigger_tier=None,
            knife_available=False,
            dist_126d_high=-18.0,
            dist_21d_low=-1.5,  # below 21d low
        )
        assert state == "KNIFE_RISK"

    def test_knife_risk_fallback_not_below_21d_low(self):
        """Fallback: drawdown >= 15% BUT close is above 21d low → not KNIFE_RISK."""
        state = _cls(
            trigger_tier=None,
            knife_available=False,
            dist_126d_high=-18.0,
            dist_21d_low=0.1,  # marginally above 21d low
        )
        assert state != "KNIFE_RISK"

    # ── WATCH (default) ───────────────────────────────────────────────────────

    def test_watch_default_no_signals(self):
        """No signals, no hold, no knife → WATCH."""
        state = _cls()
        assert state == "WATCH"

    def test_watch_broken_hold_falls_through(self):
        """Broken hold is not mapped to any state — falls through to WATCH."""
        state = _cls(
            hold_state="broken",
            trigger_tier=None,
        )
        assert state == "WATCH"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Adversarial cases from the amendment review
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdversarialCases:

    def test_adversarial_a_launched_with_fresh_fire(self):
        """(a) Launched name with a NEW fresh fire: HOLD_LAUNCHED must win.

        Even if there is a fresh T1 fire + COILED + small dist, the launched hold
        takes precedence.  The envelope NEVER recomputes a fire-anchored variant
        (Amendment §C2 bind law — two anchors ⇒ two contradictory chips on one board).
        """
        state = _cls(
            hold_state="launched",
            trigger_tier="T1", ticks=0,   # brand-new fire same day
            coiled=True,
            dist_21d_low=3.0,             # very close to 21d low
            dist_126d_high=-25.0,
        )
        assert state == "HOLD_LAUNCHED", (
            "HOLD_LAUNCHED must take highest precedence even when a fresh fire coexists"
        )

    def test_adversarial_b_stale_ticks_tiny_dist(self):
        """(b) ticks > 2 with tiny dist_21d_low: must be CHASE_RISK not FRESH_FIRE.

        ticks=3 crosses the FRESH threshold even though the name is close to its low.
        The spec says: ticks > 2 → CHASE_RISK regardless of dist.
        """
        state = _cls(
            trigger_tier="T1", ticks=3,   # ONE tick past the fresh window
            coiled=True,
            dist_21d_low=0.5,             # almost at the 21d low
        )
        assert state == "CHASE_RISK", (
            "ticks=3 must flip to CHASE_RISK even with minimal dist_21d_low"
        )

    def test_adversarial_d_missing_dist_fresh_t1_not_chase_risk(self):
        """(d) Amendment §C2 binding law: dist_21d_low=None + fresh T1 must NOT be CHASE_RISK.

        When the price parquet is absent, dist_21d_low_pct is None.  The prior bug
        treated None as "far from the low" and fabricated CHASE_RISK.  The fix:
        dist_far requires dist to be KNOWN and > 12%, so a missing dist degrades
        gracefully to WATCH, not CHASE_RISK.
        """
        # Fresh T1, ticks=0 (not stale) — the only issue is missing dist data
        state = _cls(
            trigger_tier="T1", ticks=0,
            coiled=True,
            dist_21d_low=None,     # unavailable (no price parquet)
            dist_126d_high=None,   # unavailable
        )
        assert state != "CHASE_RISK", (
            "dist_21d_low=None must NOT produce CHASE_RISK (Amendment §C2: "
            "unavailable input must degrade gracefully, not invent a risk verdict)"
        )
        # With no dist data and no hold/knife/drawdown data, should land on WATCH
        assert state == "WATCH", f"Expected WATCH with all dist=None, got {state!r}"

    def test_adversarial_e_missing_dist_stale_ticks_is_chase_risk(self):
        """(e) Stale ticks (>2) produce CHASE_RISK even when dist is None.

        The ticks_stale branch (not the dist_far branch) drives CHASE_RISK here.
        The fix must not suppress CHASE_RISK when ticks are genuinely stale.
        """
        state = _cls(
            trigger_tier="T1", ticks=5,   # stale
            dist_21d_low=None,             # unavailable — but ticks drive it
        )
        assert state == "CHASE_RISK", (
            "Stale ticks (>2) must still produce CHASE_RISK even with dist=None"
        )

    def test_adversarial_c_washout_21d_low_reclaimed_yesterday(self):
        """(c) Washout with 21d-low reclaimed yesterday.

        dist_21d_low = 0.8% (just above the 21d rolling low).
        No T1-T3 tier.  No hold.  Not coiled.  Knife_available=True but score < 0.7.
        Expected: WATCH (the name has reclaimed the low but no fresh tier fires).
        """
        state = _cls(
            trigger_tier=None,
            ticks=None,
            coiled=False,
            dist_21d_low=0.8,       # just above 21d low (reclaimed yesterday)
            dist_126d_high=-22.0,   # well off the 126d high
            knife_score=0.4,        # below KNIFE_BLOCK
            knife_available=True,
        )
        assert state == "WATCH", (
            "Washout with 21d-low just reclaimed but no tier fire → WATCH "
            "(no KNIFE_RISK because score < 0.7; no KNIFE fallback because dist_21d_low > 0)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Schema determinism test
# ═══════════════════════════════════════════════════════════════════════════════

EXPECTED_SCHEMA_COLS = {
    # ── Schema v1 (Amendment §C2) ──────────────────────────────────────────
    "symbol",           # index or column
    "as_of",            # source data vintage (signal_gate anchor), NOT computed_at
    "computed_at",      # wall-clock date this row was assembled
    "region",
    "trigger_tier",
    "trigger_age_ticks",
    "coiled",
    "star",
    "coiled_fire",
    "donor_state",
    "dist_21d_low_pct",
    "dist_126d_high_pct",
    "entry_quality_band",
    "squeeze_state",
    "hold_state",
    "earnings_next_date",
    "earnings_days_to",
    "rs_repair_state",
    "sponsorship_state",
    "bottom_state",
    "overlay_flags",
    "labels_version",
    "source_artifacts",
    "is_display_only",
    # ── Auxiliary bind-provenance columns (not in Amendment schema line) ───
    # These are included in the public artifact for traceability and are pinned
    # here so schema drift is caught in CI.
    "hold_days_basing",
    "hold_maxup_pct",
    "knife_score",
    "bars_to_cross",
}


class TestSchemaConsistency:

    def test_rolling_dist_21d(self):
        """dist_21d_low_pct returns correct value and handles edge cases."""
        vals = [100.0] * 20 + [80.0] + [90.0]
        s = _price_series(vals)
        d = _dist_21d_low_pct(s)
        # 21-bar window at last bar: the min in the last 21 bars is 80.
        # Last close is 90.  dist = (90/80 - 1)*100 = 12.5
        assert d is not None
        assert abs(d - 12.5) < 0.1

    def test_rolling_dist_21d_short_series(self):
        """Returns None when fewer than 21 bars."""
        s = _price_series([100.0] * 20)
        assert _dist_21d_low_pct(s) is None

    def test_rolling_dist_126d(self):
        """dist_126d_high_pct is negative when close < 126d high."""
        vals = [100.0] * 125 + [120.0] + [90.0]
        s = _price_series(vals)
        d = _dist_126d_high_pct(s)
        # 126-bar window: max = 120 (one bar ago); last close = 90
        # dist = (90/120 - 1)*100 = -25%
        assert d is not None
        assert abs(d - (-25.0)) < 0.1

    def test_rolling_dist_126d_short_series(self):
        """Returns None when fewer than 126 bars."""
        s = _price_series([100.0] * 125)
        assert _dist_126d_high_pct(s) is None

    def test_rolling_dist_at_high(self):
        """When close equals the 126d high, dist_126d_high_pct = 0.0."""
        vals = [100.0] * 126
        s = _price_series(vals)
        d = _dist_126d_high_pct(s)
        assert d is not None
        assert abs(d) < 0.01

    def test_labels_version_constant(self):
        """LABELS_VERSION is frozen to 'labels_v1'."""
        assert LABELS_VERSION == "labels_v1"

    def test_is_display_only_constant(self):
        """IS_DISPLAY_ONLY is True."""
        assert IS_DISPLAY_ONLY is True

    def test_knife_block_constant(self):
        """_ALIGN_KNIFE_BLOCK == 0.7 (mirrors engine/cycles.py)."""
        assert _ALIGN_KNIFE_BLOCK == 0.7

    def test_assemble_schema_with_mock_sources(self, tmp_path):
        """assemble() returns all required columns when given mock input sources."""
        from engine.neuralweb.bottom_sensors import assemble, _repo_root

        # Build a minimal mock signal_gate.json
        sg = {
            "as_of": "2026-07-02",
            "verdicts": {
                "AAPL": {"tier_cascade": "T1", "ticks": 0, "bars_to_cross": None,
                         "eligible": True, "tier_sub": None, "provisional": False},
                "FAKE": {"tier_cascade": None, "ticks": 8, "bars_to_cross": None,
                         "eligible": False, "tier_sub": None, "provisional": False},
            },
        }
        # Build a minimal mock us_standouts.json
        us = {
            "as_of": "2026-07-02",
            "donor": {"state": "intact", "donor_sector": "Technology"},
            "buy": [
                {
                    "ticker": "AAPL",
                    "coiled": {"coiled": True, "star": False, "fire": True,
                               "fire_ticks": 1, "fire_src": "m1d",
                               "washout_ctx": True, "bonus": 0.25, "div": False, "cohort": 0.4},
                    "hold": {"state": "intact", "days_basing": 5, "maxup_pct": 1.0,
                             "anchor": "2026-07-01", "anchor_src": "take",
                             "invalidation": 140.0, "ob_persist": False, "provisional": False},
                    "signal": {"tier_cascade": "T1", "ticks": 0, "bars_to_cross": None,
                               "eligible": True, "tier_sub": None, "provisional": False,
                               "state": "long-bias", "above200": True, "weekly_bull": True,
                               "early_now": True, "asof": "2026-07-02", "last": None,
                               "weight": 1.0, "fresh_bars": 0, "tier": None, "sub": None,
                               "reason": None},
                    "conviction": {
                        "vol_squeeze": {"state": "COILED", "coiled": True,
                                        "days_compressed": 8, "bbwp": 2.0, "hv_pctile": 10.0,
                                        "bias": "up", "box_hi": 200.0, "box_lo": 190.0,
                                        "pos": None, "to_upper_pct": None, "to_lower_pct": None,
                                        "fired_dir": None, "volume_confirmed": None,
                                        "coverage": "close", "caveat": "", "caveat_zh": ""},
                        "potential": {"band": "high", "tier": "primed"},
                        "alignment": {"knife": 0.1, "blocked": False, "tier": "PRIME"},
                    },
                }
            ],
            "watch": [],
            "laggards": [],
        }
        # Build a minimal earnings parquet
        import pandas as pd
        import datetime
        today = datetime.date(2026, 7, 5)
        edf = pd.DataFrame({
            "next_date": ["2026-07-07", "2026-07-15"],
            "as_of": ["2026-06-19"] * 2,
        }, index=pd.Index(["AAPL", "FAKE"], name="ticker"))

        # Write mock files into tmp_path
        import json
        fd = tmp_path / "site" / "factordata"
        fd.mkdir(parents=True)
        (fd / "signal_gate.json").write_text(json.dumps(sg))
        (fd / "us_standouts.json").write_text(json.dumps(us))
        de = tmp_path / "data" / "earnings"
        de.mkdir(parents=True)
        edf.to_parquet(de / "earnings.parquet")

        # Run assemble with no price data (tmp_path has no data/stocks/)
        df = assemble(root=tmp_path, today=today)

        assert not df.empty, "assemble() must return non-empty df for 2 mock tickers"
        assert len(df) == 2

        # Check required columns present (plus index is symbol)
        actual_cols = set(df.reset_index().columns)
        for col in EXPECTED_SCHEMA_COLS:
            assert col in actual_cols, f"Missing column: {col!r}"

        # AAPL: fresh T1, coiled=True, but dist_21d_low=None (no price file).
        # Amendment §C2 binding law: unavailable dist must NOT fabricate CHASE_RISK.
        # within_12_of_low = False (dist is None), so FRESH_FIRE_DURABLE_CAND/TACTICAL
        # both fail.  dist_far = (None is not None and ...) = False, so CHASE_RISK
        # does NOT fire on the dist branch; ticks=0 (not stale) → ticks_stale=False.
        # Neither branch fires → falls through to DEAD_MONEY_RISK (no hold),
        # EARLY_WATCH (no drawdown data), KNIFE_RISK (knife=0.1 < 0.7) → WATCH.
        aapl_state = df.loc["AAPL", "bottom_state"]
        # With dist unavailable, WATCH is the correct degraded state (not CHASE_RISK)
        assert aapl_state == "WATCH", (
            f"dist_21d_low=None must NOT produce CHASE_RISK (got {aapl_state!r}); "
            "Amendment §C2 binding law requires graceful degradation to WATCH"
        )

        # labels_version and is_display_only stamped on every row
        assert (df["labels_version"] == "labels_v1").all()
        assert (df["is_display_only"] == True).all()  # noqa: E712

        # rs_repair_state and sponsorship_state unavailable
        assert (df["rs_repair_state"] == "unavailable").all()
        assert (df["sponsorship_state"] == "unavailable").all()

        # AAPL EVENT_BLACKOUT: earnings in 2 days
        aapl_overlay = df.loc["AAPL", "overlay_flags"] or ""
        assert "EVENT_BLACKOUT" in aapl_overlay

        # FAKE: no event blackout (earnings in 10 days)
        # overlay_flags may be None or NaN when no overlays apply
        fake_overlay_raw = df.loc["FAKE", "overlay_flags"]
        fake_overlay = str(fake_overlay_raw) if (
            fake_overlay_raw is not None
            and not (isinstance(fake_overlay_raw, float) and fake_overlay_raw != fake_overlay_raw)
        ) else ""
        assert "EVENT_BLACKOUT" not in fake_overlay


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Earnings per-row staleness test
# ═══════════════════════════════════════════════════════════════════════════════

class TestEarningsFreshness:

    def _make_earnings_df(self, rows: list[tuple]) -> pd.DataFrame:
        """rows = [(ticker, next_date_str, as_of_str)]"""
        tickers, dates, asofs = zip(*rows)
        return pd.DataFrame(
            {"next_date": list(dates), "as_of": list(asofs)},
            index=pd.Index(list(tickers), name="ticker"),
        )

    def test_future_date_no_blackout(self):
        """next_date 10 days out → not in blackout window."""
        edf = self._make_earnings_df([("AAPL", "2026-07-15", "2026-07-01")])
        nd, days, blackout = _earnings_info("AAPL", edf, TODAY)
        assert nd == "2026-07-15"
        assert days == 10
        assert blackout is False

    def test_blackout_window_1_day(self):
        """next_date tomorrow → EVENT_BLACKOUT."""
        edf = self._make_earnings_df([("AAPL", "2026-07-06", "2026-07-01")])
        nd, days, blackout = _earnings_info("AAPL", edf, TODAY)
        assert days == 1
        assert blackout is True

    def test_blackout_window_exactly_3_days(self):
        """next_date 3 days out → at the boundary (<=3), blackout=True."""
        edf = self._make_earnings_df([("AAPL", "2026-07-08", "2026-07-01")])
        nd, days, blackout = _earnings_info("AAPL", edf, TODAY)
        assert days == 3
        assert blackout is True

    def test_blackout_window_4_days(self):
        """next_date 4 days out → just outside window, blackout=False."""
        edf = self._make_earnings_df([("AAPL", "2026-07-09", "2026-07-01")])
        nd, days, blackout = _earnings_info("AAPL", edf, TODAY)
        assert days == 4
        assert blackout is False

    def test_passed_date_dropped(self):
        """Per-row fresh rule: next_date <= today → (None, None, False)."""
        edf = self._make_earnings_df([("AAPL", "2026-07-04", "2026-07-01")])  # yesterday
        nd, days, blackout = _earnings_info("AAPL", edf, TODAY)
        assert nd is None
        assert days is None
        assert blackout is False

    def test_same_day_dropped(self):
        """next_date == today → also dropped (per-row fresh rule: must be AFTER today)."""
        edf = self._make_earnings_df([("AAPL", "2026-07-05", "2026-07-01")])
        nd, days, blackout = _earnings_info("AAPL", edf, TODAY)
        assert nd is None

    def test_ticker_not_in_earnings(self):
        """Missing ticker → (None, None, False)."""
        edf = self._make_earnings_df([("AAPL", "2026-07-15", "2026-07-01")])
        nd, days, blackout = _earnings_info("GOOG", edf, TODAY)
        assert nd is None
        assert blackout is False

    def test_empty_earnings_df(self):
        """Empty earnings df → (None, None, False)."""
        nd, days, blackout = _earnings_info("AAPL", pd.DataFrame(), TODAY)
        assert nd is None
        assert blackout is False

    def test_stale_row_age_does_not_affect_per_row(self):
        """Row-age stamp: the file-age (as_of) is NOT used to drop rows — only next_date matters.
        This verifies we implement the PER-ROW fresh rule, not file-level staleness.
        """
        # as_of is a month old, but next_date is in the future → should return valid
        edf = self._make_earnings_df([("AAPL", "2026-07-15", "2026-06-01")])
        nd, days, blackout = _earnings_info("AAPL", edf, TODAY)
        assert nd == "2026-07-15"
        assert days is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. STATE LABEL precedence completeness: T4 tier handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestT4TierHandling:

    def test_t4_with_bars_to_cross_triggers_early_watch(self):
        """T4 (approaching) with bars_to_cross <=2 and drawdown >=15% → EARLY_WATCH.
        T4 is NOT in T1-T3 so is not 'fresh', allowing EARLY_WATCH to fire.
        """
        state = _cls(
            trigger_tier="T4",
            ticks=0,
            dist_126d_high=-16.0,
            bars_to_cross=1.0,
        )
        assert state == "EARLY_WATCH"

    def test_t4_no_drawdown_is_watch(self):
        """T4 without 15% drawdown → WATCH."""
        state = _cls(
            trigger_tier="T4",
            ticks=0,
            dist_126d_high=-5.0,
            bars_to_cross=1.0,
        )
        assert state == "WATCH"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Sponsorship state — Amendment §C3 connector (PR-3)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_panel(node: str, date: str, vel_1m: float, accel: float) -> pd.DataFrame:
    """Build a minimal oracle-panel-shaped DataFrame for one node/date row."""
    idx = pd.MultiIndex.from_tuples(
        [(node, pd.Timestamp(date))], names=["node", "date"]
    )
    return pd.DataFrame(
        {"vel_1m": [vel_1m], "accel": [accel]},
        index=idx,
    )


def _make_panel_stale(node: str, days_ago: int) -> pd.DataFrame:
    """Panel with a single row that is `days_ago` calendar days in the past."""
    stale_date = (pd.Timestamp(TODAY) - pd.Timedelta(days=days_ago)).strftime("%Y-%m-%d")
    return _make_panel(node, stale_date, 1.0, 1.0)  # positive signs but stale


class TestSponsorshipState:
    """Tests for _sponsorship_state() — the §C3 frozen definition connector.

    Display-only: these tests confirm the connector is correctly wired and
    degrades gracefully.  They do NOT test any threshold tuning (there is none).
    """

    # ── Tailwind / headwind / neutral ─────────────────────────────────────────

    def test_tailwind_both_positive(self):
        """vel > 0 AND accel > 0 → tailwind."""
        mapping = SectorMapping(sector_node="XLK", subsector_node=None)
        panel = _make_panel("XLK", "2026-07-02", vel_1m=0.5, accel=0.1)
        state = _sponsorship_state("AAPL", mapping, panel, None, TODAY)
        assert state == "tailwind"

    def test_headwind_both_negative(self):
        """vel < 0 AND accel < 0 → headwind."""
        mapping = SectorMapping(sector_node="XLK", subsector_node=None)
        panel = _make_panel("XLK", "2026-07-02", vel_1m=-0.3, accel=-0.1)
        state = _sponsorship_state("AAPL", mapping, panel, None, TODAY)
        assert state == "headwind"

    def test_neutral_mixed_vel_pos_accel_neg(self):
        """vel > 0 AND accel < 0 → neutral."""
        mapping = SectorMapping(sector_node="XLK", subsector_node=None)
        panel = _make_panel("XLK", "2026-07-02", vel_1m=0.5, accel=-0.1)
        state = _sponsorship_state("AAPL", mapping, panel, None, TODAY)
        assert state == "neutral"

    def test_neutral_mixed_vel_neg_accel_pos(self):
        """vel < 0 AND accel > 0 → neutral."""
        mapping = SectorMapping(sector_node="XLK", subsector_node=None)
        panel = _make_panel("XLK", "2026-07-02", vel_1m=-0.3, accel=0.2)
        state = _sponsorship_state("AAPL", mapping, panel, None, TODAY)
        assert state == "neutral"

    # ── Stale / unavailable ───────────────────────────────────────────────────

    def test_unavailable_no_mapping(self):
        """mapping=None → unavailable."""
        panel = _make_panel("XLK", "2026-07-02", 0.5, 0.1)
        state = _sponsorship_state("UNKNOWN", None, panel, None, TODAY)
        assert state == "unavailable"

    def test_unavailable_both_nodes_none(self):
        """sector_node=None AND subsector_node=None → unavailable."""
        mapping = SectorMapping(sector_node=None, subsector_node=None)
        panel = _make_panel("XLK", "2026-07-02", 0.5, 0.1)
        state = _sponsorship_state("UNKNOWN", mapping, panel, None, TODAY)
        assert state == "unavailable"

    def test_unavailable_panel_none(self):
        """Mapped ticker but both panels are None → unavailable."""
        mapping = SectorMapping(sector_node="XLK", subsector_node=None)
        state = _sponsorship_state("AAPL", mapping, None, None, TODAY)
        assert state == "unavailable"

    def test_unavailable_node_not_in_panel(self):
        """Node mapping exists but node not present in panel index → unavailable."""
        mapping = SectorMapping(sector_node="XLK", subsector_node=None)
        panel = _make_panel("XLB", "2026-07-02", 0.5, 0.1)  # XLB, not XLK
        state = _sponsorship_state("AAPL", mapping, panel, None, TODAY)
        assert state == "unavailable"

    def test_stale_panel_over_threshold(self):
        """Panel row older than 5 trading days → stale.
        We use 10 calendar days which guarantees >= 7 trading days.
        """
        mapping = SectorMapping(sector_node="XLK", subsector_node=None)
        panel = _make_panel_stale("XLK", days_ago=10)
        state = _sponsorship_state("AAPL", mapping, panel, None, TODAY)
        assert state == "stale"

    def test_unavailable_null_vel_fresh_row(self):
        """vel_1m is NaN on a fresh (date-current) row → unavailable (data-absence, not date-staleness)."""
        mapping = SectorMapping(sector_node="XLK", subsector_node=None)
        panel = _make_panel("XLK", "2026-07-02", vel_1m=float("nan"), accel=0.1)
        state = _sponsorship_state("AAPL", mapping, panel, None, TODAY)
        assert state == "unavailable"

    def test_unavailable_null_accel_fresh_row(self):
        """accel is NaN on a fresh (date-current) row → unavailable (data-absence, not date-staleness)."""
        mapping = SectorMapping(sector_node="XLK", subsector_node=None)
        panel = _make_panel("XLK", "2026-07-02", vel_1m=0.5, accel=float("nan"))
        state = _sponsorship_state("AAPL", mapping, panel, None, TODAY)
        assert state == "unavailable"

    # ── Sector arm → subsector arm fallback ──────────────────────────────────

    def test_falls_back_to_subsector_when_sector_missing(self):
        """sector_node set but not in panel → fall through to subsector."""
        mapping = SectorMapping(sector_node="XLK", subsector_node="ai_infra")
        sector_panel = _make_panel("XLB", "2026-07-02", 0.5, 0.1)  # XLB only, no XLK
        subsector_panel = _make_panel("ai_infra", "2026-07-02", -0.2, -0.1)  # headwind
        state = _sponsorship_state("NVDA", mapping, sector_panel, subsector_panel, TODAY)
        assert state == "headwind"  # subsector arm used

    def test_sector_arm_wins_over_subsector(self):
        """Sector arm found → subsector arm is not consulted."""
        mapping = SectorMapping(sector_node="XLK", subsector_node="ai_infra")
        sector_panel = _make_panel("XLK", "2026-07-02", 0.8, 0.3)   # tailwind
        subsector_panel = _make_panel("ai_infra", "2026-07-02", -0.5, -0.2)  # headwind
        state = _sponsorship_state("NVDA", mapping, sector_panel, subsector_panel, TODAY)
        assert state == "tailwind"  # sector arm wins

    def test_subsector_only_mapping(self):
        """Only subsector_node mapped (sector_node=None) → subsector arm used."""
        mapping = SectorMapping(sector_node=None, subsector_node="ai_infra")
        panel_m = _make_panel("ai_infra", "2026-07-02", 0.6, 0.2)
        state = _sponsorship_state("NVDA", mapping, None, panel_m, TODAY)
        assert state == "tailwind"

    # ── Stale threshold constant ───────────────────────────────────────────────

    def test_stale_threshold_constant(self):
        """_SPONSORSHIP_STALE_TRADING_DAYS == 5 (Amendment §C3 frozen)."""
        assert _SPONSORSHIP_STALE_TRADING_DAYS == 5

    # ── Integration: sponsorship in assemble() schema ─────────────────────────

    def test_sponsorship_state_in_assemble_schema(self, tmp_path):
        """assemble() includes sponsorship_state column (may be unavailable when
        oracle panels absent — graceful degradation is correct behaviour here).
        """
        import json as _json
        import datetime as _dt

        sg = {
            "as_of": "2026-07-02",
            "verdicts": {
                "AAPL": {"tier_cascade": "T1", "ticks": 0, "bars_to_cross": None,
                         "eligible": True, "tier_sub": None, "provisional": False},
            },
        }
        us = {
            "as_of": "2026-07-02",
            "donor": {},
            "buy": [], "watch": [], "laggards": [],
        }
        fd = tmp_path / "site" / "factordata"
        fd.mkdir(parents=True)
        (fd / "signal_gate.json").write_text(_json.dumps(sg))
        (fd / "us_standouts.json").write_text(_json.dumps(us))
        de = tmp_path / "data" / "earnings"
        de.mkdir(parents=True)
        pd.DataFrame({"next_date": [], "as_of": []},
                     index=pd.Index([], name="ticker")).to_parquet(de / "earnings.parquet")

        from engine.neuralweb.bottom_sensors import assemble
        df = assemble(root=tmp_path, today=_dt.date(2026, 7, 5))

        assert "sponsorship_state" in df.columns
        # With no sector mapping files in tmp_path, all states are "unavailable"
        assert df["sponsorship_state"].iloc[0] == "unavailable"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Wiring conformance: daily.yml + dag.yml presence assertions
# ═══════════════════════════════════════════════════════════════════════════════

class TestWiringConformance:
    """Plain text-presence assertions: build_bottom_sensors is wired into
    daily.yml and has a dag.yml entry consistent with neighbouring NW producers.
    """

    ROOT = Path(__file__).resolve().parents[1]
    DAILY_YML = ROOT / ".github" / "workflows" / "daily.yml"
    DAG_YML = ROOT / "config" / "dag.yml"

    def test_daily_yml_contains_build_bottom_sensors(self):
        text = self.DAILY_YML.read_text()
        assert "scripts.build_bottom_sensors" in text, (
            "scripts.build_bottom_sensors must be invoked in daily.yml "
            "(feat/nw-bottom-sensors-wiring wiring assertion)"
        )

    def test_dag_yml_contains_build_bottom_sensors(self):
        text = self.DAG_YML.read_text()
        assert "build_bottom_sensors" in text, (
            "build_bottom_sensors must have a dag.yml entry "
            "(feat/nw-bottom-sensors-wiring wiring assertion)"
        )
