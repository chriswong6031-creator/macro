"""RED contract for Intraday Flow opportunity timing.

Operation: intraday-flow-opportunity-lifecycle-p0-20260905-sol-001
Architecture: research/INTRADAY_FLOW_OPPORTUNITY_OS_RULING_2026-09-05.md

The current implementation is expected to fail this suite because ``stance`` is a
memoryless confluence snapshot.  In particular, a recent washout plus an upturn and
no current reclaim can render ``get_ready`` even when the canonical entry gauge says
the setup is already active, already moving, failed, or blocked.

These tests intentionally exercise the public Python contract.  Browser parity is a
separate executed-JavaScript test required by the implementation plan.
"""
from __future__ import annotations

import math
from typing import Any

import pytest

from engine import intraday_flow as iflow


FORMING = ("buy_soon", "await_confluence", "watch", "bounce_wait")
ACTIVE_WINDOW = ("buy_now", "partial")
ALREADY_MOVING = ("hold", "extended", "wait_pullback", "topping")
FAILED_OR_BLOCKED = ("exit", "avoid", "blocked")


def _legs(**overrides: bool | None) -> iflow.ConfluenceLegs:
    values: dict[str, bool | None] = {
        "L1_washout_recent": None,
        "L2_reclaim": None,
        "L3_rvol_elevated": None,
        "L4_vol_durable": None,
        "L5_flow_bid": None,
        "L6_upturn_organ": None,
        "L7_leader_quality": None,
    }
    values.update(overrides)
    return iflow.ConfluenceLegs(**values)


def _get_ready_legs() -> iflow.ConfluenceLegs:
    """The exact structure that currently falls into Almost ready."""
    return _legs(
        L1_washout_recent=True,
        L2_reclaim=False,
        L6_upturn_organ=True,
        L7_leader_quality=True,
    )


def _act_legs() -> iflow.ConfluenceLegs:
    return _legs(
        L1_washout_recent=True,
        L2_reclaim=True,
        L3_rvol_elevated=True,
        L4_vol_durable=True,
        L5_flow_bid=False,
        L6_upturn_organ=True,
        L7_leader_quality=True,
    )


def _stance(
    entry_status: str | None,
    *,
    legs: iflow.ConfluenceLegs | None = None,
    current_price: float | None = 60.0,
    chase_above: float | None = 65.0,
    live_present: bool = True,
    **kwargs: Any,
) -> dict:
    legs = legs or _get_ready_legs()
    return iflow.stance(
        legs=legs,
        K=legs.K,
        entry_status=entry_status,
        current_price=current_price,
        chase_above=chase_above,
        live_present=live_present,
        **kwargs,
    )


def _assert_timing_shape(result: dict) -> None:
    assert result["timing_state"] in {
        "forming",
        "active_window",
        "already_moving",
        "failed_or_blocked",
        "unknown",
    }
    assert isinstance(result["timing_reason"], str) and result["timing_reason"]
    assert "already_started" in result
    assert isinstance(result["en"], str) and result["en"].strip()
    assert isinstance(result["zh"], str) and result["zh"].strip()


class TestPureTimingClassifier:
    def test_classifier_contract_is_public(self):
        assert hasattr(iflow, "classify_entry_timing"), (
            "P0 requires one pure timing classifier shared semantically by Python and browser"
        )

    @pytest.mark.parametrize("status", FORMING)
    def test_forming_mapping(self, status):
        result = iflow.classify_entry_timing(entry_status=status)
        assert result["state"] == "forming"
        assert result["get_ready_eligible"] is True
        assert result["already_started"] is False
        assert result["reason"] == "status_forming"

    @pytest.mark.parametrize("status", ACTIVE_WINDOW)
    def test_active_window_mapping(self, status):
        result = iflow.classify_entry_timing(entry_status=status)
        assert result["state"] == "active_window"
        assert result["get_ready_eligible"] is False
        assert result["already_started"] is True
        assert result["reason"] == "status_active_window"

    @pytest.mark.parametrize("status", ALREADY_MOVING)
    def test_already_moving_mapping(self, status):
        result = iflow.classify_entry_timing(entry_status=status)
        assert result["state"] == "already_moving"
        assert result["get_ready_eligible"] is False
        assert result["already_started"] is True
        assert result["reason"] == "status_already_moving"

    @pytest.mark.parametrize("status", FAILED_OR_BLOCKED)
    def test_failed_or_blocked_mapping(self, status):
        result = iflow.classify_entry_timing(entry_status=status)
        assert result["state"] == "failed_or_blocked"
        assert result["get_ready_eligible"] is False
        assert result["reason"] == "status_failed_or_blocked"

    @pytest.mark.parametrize("status", [None, "", "mystery", 123, {}, []])
    def test_missing_or_unknown_is_non_positive(self, status):
        result = iflow.classify_entry_timing(entry_status=status)
        assert result["state"] == "unknown"
        assert result["get_ready_eligible"] is False
        assert result["already_started"] is None
        assert result["reason"] in {"status_missing", "status_unknown"}

    def test_status_is_normalized_without_substring_matching(self):
        result = iflow.classify_entry_timing(entry_status="  BUY_NOW  ")
        assert result["state"] == "active_window"
        assert result["reason"] == "status_active_window"

    @pytest.mark.parametrize("forming_status", FORMING)
    def test_price_above_chase_overrides_forming(self, forming_status):
        result = iflow.classify_entry_timing(
            entry_status=forming_status,
            current_price=65.01,
            chase_above=65.0,
        )
        assert result["state"] == "already_moving"
        assert result["get_ready_eligible"] is False
        assert result["already_started"] is True
        assert result["reason"] == "above_chase"

    @pytest.mark.parametrize(
        ("current_price", "chase_above"),
        [
            (65.0, 65.0),       # equality is not above
            (64.99, 65.0),
            (None, 65.0),
            (65.01, None),
            (65.01, 0.0),
            (math.nan, 65.0),
            (65.01, math.nan),
            (math.inf, 65.0),
            (65.01, math.inf),
            (True, 65.0),
            (65.01, False),
        ],
    )
    def test_invalid_or_non_breached_boundary_does_not_override(
        self, current_price, chase_above
    ):
        result = iflow.classify_entry_timing(
            entry_status="buy_soon",
            current_price=current_price,
            chase_above=chase_above,
        )
        assert result["state"] == "forming"
        assert result["reason"] == "status_forming"


class TestStanceLifecycleGate:
    @pytest.mark.parametrize("status", FORMING)
    def test_explicit_forming_status_can_still_get_ready(self, status):
        result = _stance(status)
        assert result["key"] == "get_ready"
        assert result["timing_state"] == "forming"
        assert result["already_started"] is False
        _assert_timing_shape(result)

    @pytest.mark.parametrize("status", ACTIVE_WINDOW)
    def test_active_window_never_regresses_to_get_ready(self, status):
        result = _stance(status)
        assert result["key"] != "get_ready"
        assert result["timing_state"] == "active_window"
        assert result["already_started"] is True
        assert "almost ready" not in result["en"].lower()
        assert "底部已形成" not in result["zh"]
        _assert_timing_shape(result)

    @pytest.mark.parametrize("status", ALREADY_MOVING)
    def test_already_moving_uses_existing_watch_lane_and_anti_chase_copy(self, status):
        result = _stance(status)
        assert result["key"] == "watch"
        assert result["lane"] == "watch"
        assert result["timing_state"] == "already_moving"
        assert result["timing_reason"] == "status_already_moving"
        assert result["already_started"] is True
        assert result["en"] == "Already moving — wait for a reset; do not chase."
        assert result["zh"] == "行情已启动 — 等待重置，切勿追高。"
        _assert_timing_shape(result)

    @pytest.mark.parametrize("status", FAILED_OR_BLOCKED)
    def test_failed_or_blocked_uses_non_actionable_lane(self, status):
        result = _stance(status)
        assert result["key"] == "stand_aside"
        assert result["lane"] == "stand_aside"
        assert result["timing_state"] == "failed_or_blocked"
        assert result["en"] == "Setup is no longer actionable."
        assert result["zh"] == "该形态已不再可执行。"
        _assert_timing_shape(result)

    @pytest.mark.parametrize("status", [None, "", "mystery"])
    def test_unknown_timing_cannot_emit_positive_setup_claim(self, status):
        result = _stance(status)
        assert result["key"] == "stand_aside"
        assert result["lane"] == "stand_aside"
        assert result["timing_state"] == "unknown"
        assert result["already_started"] is None
        assert result["en"] == "Timing unavailable — no positive setup claim."
        assert result["zh"] == "时机数据不可用 — 不作正面形态判断。"
        _assert_timing_shape(result)

    def test_asts_like_card_cannot_return_to_almost_ready_after_start(self):
        """Regression named for the Chairman-observed ASTS symptom.

        The structure is still washout/upturn/no-current-reclaim, but the canonical
        entry gauge says HOLD and spot is above the anti-chase boundary.  The old
        memoryless ladder returns get_ready; the corrected board must not.
        """
        result = _stance(
            "hold",
            current_price=61.99,
            chase_above=60.50,
        )
        assert result["key"] == "watch"
        assert result["timing_state"] == "already_moving"
        assert result["timing_reason"] == "above_chase"
        assert "almost ready" not in result["en"].lower()
        assert "waiting for the open" not in result["en"].lower()
        assert "等待开盘" not in result["zh"]

    def test_forming_status_above_chase_is_already_moving(self):
        result = _stance(
            "buy_soon",
            current_price=65.01,
            chase_above=65.0,
        )
        assert result["key"] == "watch"
        assert result["timing_state"] == "already_moving"
        assert result["timing_reason"] == "above_chase"

    def test_forming_status_at_or_below_chase_can_remain_get_ready(self):
        at_boundary = _stance("buy_soon", current_price=65.0, chase_above=65.0)
        below = _stance("buy_soon", current_price=64.99, chase_above=65.0)
        assert at_boundary["key"] == "get_ready"
        assert below["key"] == "get_ready"
        assert at_boundary["timing_state"] == below["timing_state"] == "forming"

    @pytest.mark.parametrize("status", ["buy_now", "partial"])
    def test_active_window_can_still_act_when_live_action_gate_is_complete(self, status):
        result = _stance(
            status,
            legs=_act_legs(),
            current_price=60.0,
            chase_above=65.0,
            vwap_delta_pct=0.25,
        )
        assert result["key"] == "act"
        assert result["timing_state"] == "active_window"
        assert result["already_started"] is True

    def test_existing_take_profit_safety_rule_still_wins_for_late_setup(self):
        dealer = {
            "expected_move_daily_pct": 1.0,
            "call_wall_hard": False,
            "call_wall_dist_sigma": 2.0,
            "opex_days": 20,
            "regime": "long",
        }
        result = _stance(
            "hold",
            legs=_act_legs(),
            current_price=70.0,
            chase_above=65.0,
            vwap_delta_pct=1.6,
            dealer=dealer,
        )
        assert result["key"] == "take_profits"
        assert result["timing_state"] == "already_moving"
        assert result["timing_reason"] == "above_chase"

    @pytest.mark.parametrize("status", ACTIVE_WINDOW + ALREADY_MOVING)
    def test_off_hours_never_reopens_almost_ready_after_activation(self, status):
        result = _stance(status, live_present=False)
        assert result["key"] == "watch"
        assert result["timing_state"] in {"active_window", "already_moving"}
        assert "waiting for the open" not in result["en"].lower()
        assert "等待开盘" not in result["zh"]

    @pytest.mark.parametrize("status", FAILED_OR_BLOCKED)
    def test_off_hours_failed_or_blocked_remains_non_actionable(self, status):
        result = _stance(status, live_present=False)
        assert result["key"] == "stand_aside"
        assert result["timing_state"] == "failed_or_blocked"

    def test_off_hours_explicit_forming_can_use_waiting_for_open_copy(self):
        result = _stance("buy_soon", live_present=False)
        assert result["key"] == "get_ready"
        assert result["timing_state"] == "forming"
        assert result["en"] == "Base in place — waiting for the open."
        assert result["zh"] == "底部已形成 — 等待开盘。"

    def test_same_legs_only_forming_status_can_reenable_get_ready(self):
        statuses = FORMING + ACTIVE_WINDOW + ALREADY_MOVING + FAILED_OR_BLOCKED + (None,)
        results = {status: _stance(status)["key"] for status in statuses}
        assert {status for status, key in results.items() if key == "get_ready"} == set(FORMING)
