"""Tests for engine/washout_counter_read.py — RC-R11 washout counter-read chip.

Covers:
  (1) test_fire_condition_p90_boundary        — growth scare at exactly 90 fires; at 89.9 does not
  (2) test_ihm_washout_turn_path              — IHM SPY depth_pctile ≤ 10 fires with basis "ihm_washout_turn"
  (3) test_ihm_recent_event_path              — IHM recent_events has a washout_turn bull event within 5 days
  (4) test_drawdown_fallback_path             — when IHM absent, uses price series fallback
  (5) test_no_fire_quiet_state                — growth scare at 50, no firing
  (6) test_append_only_ledger                 — calling append_ledger twice with same as_of produces two rows
  (7) test_display_only_stamps                — output contains is_context_only=True
  (8) test_scare_absent                       — no "growth" entry in scares → fired=False, no crash
  (9) test_depth_extreme_required             — scare ≥ 90 but depth not extreme → fired=False

All tests are network-free (synthetic fixture data only).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.washout_counter_read as WCR


# ---------------------------------------------------------------------------
# Helpers: synthetic fixture builders
# ---------------------------------------------------------------------------

def _risk_radar(growth_score: float | None = None, other_scares: list | None = None) -> dict:
    """Build a minimal risk_radar dict with a growth scare score."""
    scares = []
    if growth_score is not None:
        scares.append({
            "scare": "growth",
            "score": growth_score,
            "band": "caution" if growth_score < 70 else ("elevated" if growth_score < 85 else "risk-off"),
            "tier": "A",
            "label_en": "growth scare",
            "label_zh": "增长恐慌",
            "firing_legs": [],
            "lead_weighted": growth_score / 100.0,
        })
    if other_scares:
        scares.extend(other_scares)
    return {
        "state": "caution",
        "top_score": growth_score,
        "scares": scares,
    }


def _ihm_with_depth(depth_pctile: float | None) -> dict:
    """Build a minimal index_momentum dict with SPY depth_pctile set."""
    grid_1d: dict = {}
    if depth_pctile is not None:
        grid_1d["depth_pctile"] = depth_pctile
    return {
        "indices": {
            "SPY": {
                "grids": {
                    "1D": grid_1d
                }
            }
        }
    }


def _ihm_with_recent_event(quality_tag: str, direction: str, date_str: str,
                            depth_pctile: float | None = 5.0) -> dict:
    """Build a minimal index_momentum dict with a recent event."""
    event: dict = {
        "quality_tag": quality_tag,
        "direction": direction,
        "date": date_str,
    }
    if depth_pctile is not None:
        event["depth_pctile"] = depth_pctile
    return {
        "indices": {
            "SPY": {
                "grids": {
                    "1D": {
                        "depth_pctile": None,
                        "recent_events": [event],
                    }
                }
            }
        }
    }


def _spy_price_series(n: int = 300, final_drawdown_pct: float = -0.15) -> pd.Series:
    """Build a synthetic SPY close series where the final bar has a specific drawdown.

    final_drawdown_pct: negative float, e.g. -0.15 = 15% below rolling 63d max.
    At p90 depth, current DD must be worse than 90% of historical DDs.
    """
    rng = np.random.default_rng(42)
    # Build a series where most bars are near the rolling max (shallow drawdown)
    # but the last bar is deeply below it
    prices = np.ones(n) * 100.0
    # Random walk around 100 for most of the series (small drawdowns)
    for i in range(1, n - 1):
        prices[i] = prices[i - 1] * (1 + rng.normal(0, 0.005))
    # Force last bar to be deeply below its rolling max
    # We need current price to be at a deep drawdown vs 63d max
    rolling_max_approx = max(prices[max(0, n - 63):n - 1])
    prices[n - 1] = rolling_max_approx * (1 + final_drawdown_pct)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(prices, index=idx)


def _spy_flat_series(n: int = 300) -> pd.Series:
    """Build a series with near-zero drawdown (no depth extreme)."""
    prices = np.ones(n) * 100.0
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(prices, index=idx)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFireConditionBoundary:
    """(1) Growth scare at exactly 90 fires; at 89.9 does not."""

    def test_exactly_90_fires(self):
        rr = _risk_radar(growth_score=90.0)
        ihm = _ihm_with_depth(depth_pctile=5.0)  # deep enough
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is True
        assert result["scare_pctile"] == 90.0

    def test_89_9_does_not_fire(self):
        rr = _risk_radar(growth_score=89.9)
        ihm = _ihm_with_depth(depth_pctile=5.0)
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False
        assert result["scare_pctile"] == 89.9

    def test_91_fires(self):
        """The 06-26 labeled pattern: growth-scare-91."""
        rr = _risk_radar(growth_score=91.0)
        ihm = _ihm_with_depth(depth_pctile=3.0)
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is True


class TestIhmWashoutTurnPath:
    """(2) IHM depth_pctile ≤ 10 fires with basis "ihm_washout_turn"."""

    def test_depth_pctile_at_10_fires(self):
        rr = _risk_radar(growth_score=95.0)
        ihm = _ihm_with_depth(depth_pctile=10.0)
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is True
        assert result["depth_basis"] == "ihm_washout_turn"
        assert result["depth_value"] == 10.0
        assert result["index"] == "SPY"

    def test_depth_pctile_at_5_fires(self):
        rr = _risk_radar(growth_score=91.0)
        ihm = _ihm_with_depth(depth_pctile=5.0)
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is True
        assert result["depth_basis"] == "ihm_washout_turn"
        assert result["depth_value"] == 5.0

    def test_depth_pctile_at_11_does_not_fire(self):
        """depth_pctile 11 is not extreme enough."""
        rr = _risk_radar(growth_score=95.0)
        ihm = _ihm_with_depth(depth_pctile=11.0)
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False

    def test_depth_pctile_none_falls_to_events_check(self):
        """When depth_pctile is None, fallback to recent_events check."""
        rr = _risk_radar(growth_score=95.0)
        ihm = _ihm_with_depth(depth_pctile=None)
        # No recent events either → no fire
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False


class TestIhmRecentEventPath:
    """(3) IHM recent_events has a washout_turn bull event within 5 days."""

    def test_recent_washout_turn_bull_fires(self):
        rr = _risk_radar(growth_score=91.0)
        # Event 2 calendar days ago (well within 5 trading days)
        ihm = _ihm_with_recent_event(
            quality_tag="washout_turn",
            direction="bull",
            date_str="2026-06-24",  # 2 days before 2026-06-26
            depth_pctile=7.0,
        )
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is True
        assert result["depth_basis"] == "ihm_washout_turn"
        assert result["depth_value"] == 7.0
        assert result["index"] == "SPY"

    def test_wrong_quality_tag_does_not_fire(self):
        rr = _risk_radar(growth_score=91.0)
        ihm = _ihm_with_recent_event(
            quality_tag="bull_cross",  # not washout_turn
            direction="bull",
            date_str="2026-06-25",
        )
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False

    def test_bear_direction_does_not_fire(self):
        rr = _risk_radar(growth_score=91.0)
        ihm = _ihm_with_recent_event(
            quality_tag="washout_turn",
            direction="bear",  # not bull
            date_str="2026-06-25",
        )
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False

    def test_stale_event_beyond_window(self):
        """Event from 30 days ago (beyond 5 trading days) should not fire."""
        rr = _risk_radar(growth_score=91.0)
        ihm = _ihm_with_recent_event(
            quality_tag="washout_turn",
            direction="bull",
            date_str="2026-05-27",  # ~30 days before 2026-06-26
        )
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False


class TestDrawdownFallbackPath:
    """(4) When IHM absent, uses price series fallback."""

    def test_deep_drawdown_fires_fallback(self):
        """A 15% drawdown should land in p90+ of a mostly-shallow history."""
        rr = _risk_radar(growth_score=92.0)
        prices = _spy_price_series(n=300, final_drawdown_pct=-0.15)
        result = WCR.compute(rr, None, price_fallback=prices, as_of="2026-06-26")
        assert result["fired"] is True
        assert result["depth_basis"] == "drawdown_63d_pctile"
        assert result["depth_value"] is not None
        assert result["depth_value"] >= 90.0
        assert result["index"] == "SPY"

    def test_flat_series_does_not_fire(self):
        """No drawdown → pctile near 0 → no fire."""
        rr = _risk_radar(growth_score=92.0)
        prices = _spy_flat_series(n=300)
        result = WCR.compute(rr, None, price_fallback=prices, as_of="2026-06-26")
        assert result["fired"] is False

    def test_no_fallback_provided_does_not_fire(self):
        """IHM absent AND no price_fallback → no fire."""
        rr = _risk_radar(growth_score=95.0)
        result = WCR.compute(rr, None, price_fallback=None, as_of="2026-06-26")
        assert result["fired"] is False


class TestNoFireQuietState:
    """(5) Growth scare at 50, no firing."""

    def test_low_scare_does_not_fire(self):
        rr = _risk_radar(growth_score=50.0)
        ihm = _ihm_with_depth(depth_pctile=5.0)
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False
        assert result["scare_pctile"] == 50.0

    def test_zero_scare_does_not_fire(self):
        rr = _risk_radar(growth_score=0.0)
        ihm = _ihm_with_depth(depth_pctile=1.0)
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False


class TestAppendOnlyLedger:
    """(6) Calling append_ledger twice with same as_of produces two rows (no dedup law)."""

    def test_two_appends_produce_two_rows(self, tmp_path: Path):
        block = {
            "schema": "washout_counter_read.v1",
            "as_of": "2026-06-26",
            "fired": True,
            "scare_pctile": 91.0,
            "depth_basis": "ihm_washout_turn",
            "depth_value": 5.0,
            "index": "SPY",
            "is_context_only": True,
        }
        WCR.append_ledger(block, tmp_path)
        WCR.append_ledger(block, tmp_path)

        ledger_path = tmp_path / "washout_counter_read" / "ledger.jsonl"
        assert ledger_path.exists()
        lines = ledger_path.read_text().strip().split("\n")
        assert len(lines) == 2
        # Each line must parse as JSON
        for line in lines:
            parsed = json.loads(line)
            assert parsed["as_of"] == "2026-06-26"
            assert parsed["fired"] is True

    def test_ledger_dir_created_if_absent(self, tmp_path: Path):
        block = {
            "schema": "washout_counter_read.v1",
            "as_of": "2026-07-01",
            "fired": True,
            "scare_pctile": 90.0,
            "depth_basis": "drawdown_63d_pctile",
            "depth_value": 91.5,
            "index": "SPY",
            "is_context_only": True,
        }
        new_dir = tmp_path / "nonexistent_subdir"
        WCR.append_ledger(block, new_dir)
        assert (new_dir / "washout_counter_read" / "ledger.jsonl").exists()


class TestDisplayOnlyStamps:
    """(7) Output always contains is_context_only=True."""

    def test_fired_has_context_only(self):
        rr = _risk_radar(growth_score=91.0)
        ihm = _ihm_with_depth(depth_pctile=5.0)
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result.get("is_context_only") is True

    def test_not_fired_has_context_only(self):
        rr = _risk_radar(growth_score=50.0)
        result = WCR.compute(rr, None, as_of="2026-06-26")
        assert result.get("is_context_only") is True

    def test_schema_field_present(self):
        result = WCR.compute(None, None, as_of="2026-06-26")
        assert result.get("schema") == "washout_counter_read.v1"

    def test_as_of_field_present(self):
        result = WCR.compute(None, None, as_of="2026-06-26")
        assert result.get("as_of") == "2026-06-26"


class TestScareAbsent:
    """(8) No "growth" entry in scares → fired=False, no crash."""

    def test_empty_scares_list(self):
        rr = {"state": "caution", "top_score": 91, "scares": []}
        ihm = _ihm_with_depth(depth_pctile=5.0)
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False
        assert result["scare_pctile"] is None

    def test_no_growth_scare_in_list(self):
        rr = {
            "state": "elevated",
            "top_score": 88,
            "scares": [
                {"scare": "liquidity", "score": 88.0, "band": "elevated", "tier": "A",
                 "label_en": "liquidity", "label_zh": "流动性", "firing_legs": [], "lead_weighted": 0.88},
            ],
        }
        ihm = _ihm_with_depth(depth_pctile=5.0)
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False
        assert result["scare_pctile"] is None

    def test_none_risk_radar(self):
        result = WCR.compute(None, None, as_of="2026-06-26")
        assert result["fired"] is False
        assert result["scare_pctile"] is None

    def test_none_index_momentum_no_crash(self):
        rr = _risk_radar(growth_score=95.0)
        result = WCR.compute(rr, None, as_of="2026-06-26")
        # fired=False because no depth extreme was found
        assert result["fired"] is False


class TestDepthExtremeRequired:
    """(9) Scare ≥ 90 but depth not extreme → fired=False."""

    def test_scare_high_but_depth_not_extreme(self):
        rr = _risk_radar(growth_score=95.0)
        ihm = _ihm_with_depth(depth_pctile=50.0)  # not extreme
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False
        assert result["scare_pctile"] == 95.0
        assert result["depth_basis"] is None

    def test_ihm_no_spy_key(self):
        """IHM exists but has no SPY entry → no fire."""
        rr = _risk_radar(growth_score=95.0)
        ihm = {
            "indices": {
                "QQQ": {"grids": {"1D": {"depth_pctile": 5.0}}}
            }
        }
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False

    def test_ihm_malformed_does_not_crash(self):
        """Malformed IHM → no crash, fired=False."""
        rr = _risk_radar(growth_score=95.0)
        ihm = {"indices": "not_a_dict"}
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is False

    def test_completely_empty_ihm(self):
        rr = _risk_radar(growth_score=95.0)
        result = WCR.compute(rr, {}, as_of="2026-06-26")
        assert result["fired"] is False


class TestSchemaFields:
    """Additional schema integrity checks."""

    def test_all_schema_fields_present_when_not_fired(self):
        result = WCR.compute(None, None, as_of="2026-06-15")
        assert "schema" in result
        assert "as_of" in result
        assert "fired" in result
        assert "scare_pctile" in result
        assert "depth_basis" in result
        assert "depth_value" in result
        assert "index" in result
        assert "is_context_only" in result

    def test_all_schema_fields_present_when_fired(self):
        rr = _risk_radar(growth_score=91.0)
        ihm = _ihm_with_depth(depth_pctile=5.0)
        result = WCR.compute(rr, ihm, as_of="2026-06-26")
        assert result["fired"] is True
        assert "schema" in result
        assert "as_of" in result
        assert "scare_pctile" in result
        assert "depth_basis" in result
        assert "depth_value" in result
        assert "index" in result
        assert "is_context_only" in result


class TestEndToEndTemplateVisible:
    """End-to-end: fired WCR block placed in fixture regime latest reaches
    market_state_snapshot(...)['radar']['washout_counter_read'] — the
    template-visible path.  Verifies Fix 1 producer→consumer wiring."""

    def test_fired_block_reaches_radar_key(self):
        """A fired WCR block in latest['washout_counter_read'] propagates to
        market_state_snapshot output at radar['washout_counter_read']."""
        import engine.market_state as MS

        # Build a fired WCR block (as run.py would set it)
        fired_wcr = WCR.compute(
            _risk_radar(growth_score=91.0),
            _ihm_with_depth(depth_pctile=5.0),
            as_of="2026-06-26",
        )
        assert fired_wcr["fired"] is True  # positive-control: fixture fires

        # Build a minimal latest dict with enough keys to avoid None returns.
        # The US profile _radar_override reads latest["risk_radar"] and
        # latest["washout_counter_read"]; we also need latest["conditions"] to
        # avoid AttributeError inside the confluence amplification path.
        latest = {
            "date": "2026-06-26",
            "risk_radar": _risk_radar(growth_score=91.0),
            "index_momentum": None,
            "washout_counter_read": fired_wcr,
            "conditions": {},
            "turning_point": None,
            "quad_name": "Growth", "confidence": 0.7,
            "liquidity_overlay": "neutral", "cycle_tag": "mid",
            "transition_state": "STABLE",
        }

        snap = MS.market_state_snapshot(latest)
        assert snap is not None, "market_state_snapshot returned None — fixture insufficient"
        radar = snap.get("radar")
        assert radar is not None, "radar key missing from snapshot"
        # The key must be present (Fix 4 — _calm_radar and _radar_to_rd both carry it)
        assert "washout_counter_read" in radar, (
            "washout_counter_read key absent from radar — _radar_override or _calm_radar missing it"
        )
        # And it must carry the fired block (not None)
        wcr_out = radar["washout_counter_read"]
        assert wcr_out is not None, (
            "washout_counter_read is None in radar — block not propagated from latest"
        )
        assert wcr_out.get("fired") is True, (
            f"fired flag not True in propagated block: {wcr_out}"
        )
        assert wcr_out.get("schema") == "washout_counter_read.v1"

    def test_null_wcr_in_latest_carries_key_in_radar(self):
        """When latest['washout_counter_read'] is None (unfired night), the radar
        dict still carries the key (Fix 4 invariant) so templates can guard on it."""
        import engine.market_state as MS

        latest = {
            "date": "2026-06-26",
            "risk_radar": _risk_radar(growth_score=40.0),
            "index_momentum": None,
            "washout_counter_read": None,
            "conditions": {},
            "turning_point": None,
            "quad_name": "Growth", "confidence": 0.6,
            "liquidity_overlay": "neutral", "cycle_tag": "mid",
            "transition_state": "STABLE",
        }

        snap = MS.market_state_snapshot(latest)
        if snap is None:
            # snapshot can return None if components are empty — just check _calm_radar
            from engine.market_state import _calm_radar
            assert "washout_counter_read" in _calm_radar(), (
                "_calm_radar missing washout_counter_read key (Fix 4)"
            )
            return
        radar = snap.get("radar", {})
        assert "washout_counter_read" in radar, (
            "washout_counter_read key absent from radar on unfired night"
        )
