"""Temporal parity between live Prophet origination and the Arena shadows.

The Arena may change only a registered challenger policy.  Board freshness, the
entry-price clock and tier-native signal provenance are champion mechanics and must be
identical for C0, C6 and every shadow policy.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine import prophet_arena as pa
from engine import prophet_bridge as pb
from scripts import build_prophet as bp


class FakePrices:
    def __init__(self, rows: dict[str, pd.Series | None] | None = None) -> None:
        self.rows = rows or {}

    def get(self, ticker: str) -> pd.Series | None:
        return self.rows.get(str(ticker))


def _tier_row(
    ticker: str,
    tier: str,
    *,
    formation_date: str,
    event_date: str | None,
    observed_date: str,
    provisional: bool,
    last: dict | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "dir": "up",
        "prophet": {"version": "us_prophet_v1", "score": 80.0},
        "conviction": {"score": 75.0, "band": "high"},
        "entry_signal": {
            "act_level": 3,
            "status": "buy_now",
            "spot": 100.0,
            "atr_pct": 5.0,
            "chase_above": None,
        },
        "hold": {"anchor": formation_date, "invalidation": 90.0},
        "signal": {
            "tier_cascade": tier,
            "tier_event_date": event_date,
            "tier_observed_date": observed_date,
            "tier_observation_provisional": provisional,
            "last": last,
        },
    }


@pytest.mark.parametrize(
    "standouts_asof,recorded_asof,mixed_vintage,error_text",
    [
        (
            "2026-07-31",
            "2026-08-03",
            False,
            "stale boards cannot originate plans",
        ),
        (
            "2026-08-03",
            "2026-08-03",
            True,
            "mixed-vintage boards cannot originate plans",
        ),
    ],
)
def test_c0_and_c6_fail_closed_on_the_same_stale_or_mixed_board_as_live(
    standouts_asof: str,
    recorded_asof: str,
    mixed_vintage: bool,
    error_text: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _tier_row(
        "CLOCK",
        "T1",
        formation_date="2026-07-01",
        event_date=standouts_asof,
        observed_date=standouts_asof,
        provisional=False,
    )
    # A current wrapper stamp must not launder an older ranked-price watermark.
    standouts = {
        "as_of": recorded_asof,
        "gate_go": True,
        "buy": [row],
        "staleness": {
            "price_through": standouts_asof,
            "delayed": False,
            "unknown": False,
            "basis": "panel_majority",
            "inputs": {"panel": {"mixed_vintage": mixed_vintage}},
        },
    }
    monkeypatch.setattr(
        "engine.prophet_doors.door_w_candidates",
        lambda root=None: {"candidates": [], "disclosure": {}},
        raising=True,
    )

    board = pa.run_arena(
        standouts,
        asof=recorded_asof,
        existing_ids=set(),
        live_plan_ids=set(),
        repo_root=tmp_path,
        write=False,
        tilt_inputs=None,
    )

    tonight = board["tonight"]["policies"]
    for policy_key in (pa.CHAMPION_KEY, "C6_time_stop_21"):
        assert tonight[policy_key]["n_plans"] == 0
        receipt = tonight[policy_key]["origination"]
        assert receipt["skipped_clock_provenance"] == 1
        assert any(
            error_text in error
            for failure in receipt["validation_failures"]
            for error in failure["errors"]
        )
    assert board["harness_validity"]["harness_ok"] is True


@pytest.mark.parametrize(
    "source_basis,originates",
    [("panel_majority", True), ("board_asof", False), (None, False)],
)
def test_ranked_price_basis_must_be_explicit_panel_majority(
    source_basis: str | None,
    originates: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _tier_row(
        "BASIS",
        "T1",
        formation_date="2026-04-01",
        event_date="2026-05-01",
        observed_date="2026-05-01",
        provisional=False,
    )
    standouts = {
        "as_of": "2026-05-02",
        "gate_go": True,
        "buy": [row],
        "staleness": {
            "price_through": "2026-05-01",
            "delayed": False,
            "unknown": False,
            "basis": source_basis,
            "inputs": {"panel": {"mixed_vintage": False}},
        },
    }
    monkeypatch.setattr(
        "engine.prophet_doors.door_w_candidates",
        lambda root=None: {"candidates": [], "disclosure": {}},
        raising=True,
    )
    live_ids = {"BASIS-BULL-20260401"} if originates else set()
    board = pa.run_arena(
        standouts,
        asof="2026-05-02",
        existing_ids=set(),
        live_plan_ids=live_ids,
        repo_root=tmp_path,
        write=False,
        tilt_inputs=None,
    )

    result = board["tonight"]["policies"][pa.CHAMPION_KEY]
    receipt = result["origination"]
    assert bool(result["n_plans"]) is originates
    assert board["harness_validity"]["harness_ok"] is True
    if originates:
        assert receipt["validation_failures"] == []
        assert receipt["price_basis_date"] == "2026-05-01"
    else:
        assert receipt["skipped_clock_provenance"] == 1
        assert any(
            "staleness.basis must be 'panel_majority'" in error
            for failure in receipt["validation_failures"]
            for error in failure["errors"]
        )


def test_nontrivial_t1_t2_dates_and_stage_tilt_match_live_price_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    t1 = _tier_row(
        "TIER1",
        "T1",
        formation_date="2026-04-01",
        event_date="2026-04-28",
        observed_date="2026-05-01",
        provisional=False,
        last={
            "type": "buy",
            "date": "2026-04-21",
            "signal_date": "2026-04-28",
            "confirmed_date": "2026-04-30",
        },
    )
    t2 = _tier_row(
        "TIER2",
        "T2",
        formation_date="2026-03-15",
        event_date="2026-04-29",
        observed_date="2026-05-01",
        provisional=False,
        # An unrelated marker must not donate its confirmation to a native T2 cross.
        last={
            "type": "buy",
            "date": "2026-04-10",
            "signal_date": "2026-04-11",
            "confirmed_date": "2026-04-15",
        },
    )
    tilt_clocks: list[tuple[str, str | None]] = []

    def fake_tilt(*, ticker: str, entry_date: str | None, tilt_inputs: dict):
        tilt_clocks.append((ticker, entry_date))
        return 56, {"leash": 1.25}

    monkeypatch.setattr(pb, "_compute_stage_tilt", fake_tilt)
    plans, receipt = pa.originate_shadow_plans(
        pa.CHAMPION_KEY,
        [t1, t2],
        asof="2026-05-02",  # Saturday publication; Friday supplied both entry prices.
        standouts_asof="2026-05-02",
        price_through="2026-05-01",
        source_delayed=False,
        source_unknown=False,
        source_basis="panel_majority",
        existing_ids=set(),
        active_keys=None,
        prices=FakePrices(),
        tilt_inputs={"present": True},
    )

    assert receipt["validation_failures"] == []
    by_ticker = {plan["asset"]: plan for plan in plans}
    p1 = by_ticker["TIER1"]
    assert p1["id"] == "TIER1-BULL-20260401"
    assert p1["formation_date"] == "2026-04-01"
    assert p1["signal_date"] == "2026-04-28"
    assert p1["confirmed_date"] == "2026-04-30"
    assert p1["observed_date"] == "2026-05-01"
    assert p1["source_marker_date"] == "2026-04-21"
    assert p1["signal_tier"] == "T1"
    assert p1["signal_date_basis"] == "tier_event_date"

    p2 = by_ticker["TIER2"]
    assert p2["id"] == "TIER2-BULL-20260315"
    assert p2["signal_date"] == "2026-04-29"
    assert p2["confirmed_date"] is None
    assert p2["source_marker_date"] == "2026-04-10"
    assert p2["signal_tier"] == "T2"

    for plan in plans:
        assert plan["price_basis_date"] == "2026-05-01"
        assert plan["entry_date"] == "2026-05-01"
        assert plan["recorded_at"] == "2026-05-02"
        assert plan["horizon_days"] == 56
    assert tilt_clocks == [
        ("TIER1", "2026-05-01"),
        ("TIER2", "2026-05-01"),
    ]


def test_t3_null_signal_date_and_price_clock_survive_the_forward_ledger() -> None:
    row = _tier_row(
        "TIER3",
        "T3",
        formation_date="2026-04-01",
        event_date=None,
        observed_date="2026-05-01",
        provisional=True,
        last={"type": "buy", "date": "2026-04-21"},
    )
    prices = FakePrices({
        "TIER3": pd.Series(
            [100.0, 116.0],
            index=pd.to_datetime(["2026-05-01", "2026-05-04"]),
        )
    })
    plans, receipt = pa.originate_shadow_plans(
        pa.CHAMPION_KEY,
        [row],
        asof="2026-05-02",
        standouts_asof="2026-05-02",
        price_through="2026-05-01",
        source_delayed=False,
        source_unknown=False,
        source_basis="panel_majority",
        existing_ids=set(),
        active_keys=None,
        prices=prices,
        tilt_inputs=None,
    )

    assert receipt["validation_failures"] == []
    plan = plans[0]
    assert plan["id"] == "TIER3-BULL-20260401"
    assert plan["signal_tier"] == "T3"
    assert plan["signal_date"] is None
    assert plan["confirmed_date"] is None
    assert plan["observed_date"] == "2026-05-01"
    assert plan["signal_date_basis"] == "tier_observation"
    assert plan["signal_provisional"] is True
    assert plan["price_basis_date"] == "2026-05-01"

    opened = pa.open_row(pa.CHAMPION_KEY, plan, arena_night="2026-05-02")
    for field in (
        "formation_date",
        "signal_date",
        "confirmed_date",
        "observed_date",
        "signal_tier",
        "signal_date_basis",
        "signal_provisional",
        "source_marker_date",
        "price_basis_date",
        "entry_date",
        "recorded_at",
    ):
        assert opened[field] == plan[field]

    policy = next(policy for policy in pa.POLICIES if policy.key == pa.CHAMPION_KEY)
    closures = pa.grade_open_plans(
        policy,
        {plan["id"]: {"open": opened, "close": None}},
        asof="2026-05-04",
        prices=prices,
    )
    assert len(closures) == 1
    assert closures[0]["outcome"] == "T1_HIT"
    assert closures[0]["signal_date"] is None
    assert closures[0]["price_basis_date"] == "2026-05-01"
    assert closures[0]["days_held"] == 3


def test_unconfirmed_trigger_is_no_entry_with_null_pnl_in_live_and_arena() -> None:
    plan = {
        "id": "WAIT-BULL-20260401",
        "asset": "WAIT",
        "direction": "BULL",
        "entry": 100.0,
        "trigger": 110.0,
        "invalidation": 90.0,
        "targets": [115.0, 130.0],
        "horizon_days": 3,
        "price_basis_date": "2026-05-01",
        "entry_date": "2026-05-01",
        "signal_date": "2026-04-28",
    }
    frame = pd.DataFrame(
        {"close": [100.0, 105.0, 109.0]},
        index=pd.to_datetime(["2026-05-01", "2026-05-04", "2026-05-05"]),
    )

    live = bp._determine_outcome(plan, frame, "2026-05-05")
    shadow = pa.replay_closure(plan, frame["close"])

    assert live == ("NO_ENTRY", None, None, 3)
    assert shadow is not None
    assert shadow["outcome"] == live[0]
    assert shadow["stock_result_pct"] is live[1] is None
    assert shadow["close_price"] is None
    assert shadow["days_held"] == live[3] == 3


def test_v1_formation_clock_ledgers_are_sealed_outside_the_active_scoreboard(
    tmp_path: Path,
) -> None:
    legacy = pa.legacy_ledger_path(pa.CHAMPION_KEY, tmp_path)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy_rows = [
        {
            "schema": "prophet_arena.ledger/v1",
            "kind": "open",
            "policy": pa.CHAMPION_KEY,
            "id": "OLD-BULL-20260101",
            "asset": "OLD",
            "signal_date": "2026-01-01",
            "entry": 100,
        },
        {
            "schema": "prophet_arena.ledger/v1",
            "kind": "close",
            "policy": pa.CHAMPION_KEY,
            "id": "OLD-BULL-20260101",
            "asset": "OLD",
            "signal_date": "2026-01-01",
            "outcome": "T1_HIT",
            "stock_result_pct": 999,
        },
    ]
    legacy.write_text(
        "# sealed v1\n"
        + "\n".join(json.dumps(row, sort_keys=True) for row in legacy_rows)
        + "\n",
        encoding="utf-8",
    )

    plan = {
        "id": "NEW-BULL-20260401",
        "asset": "NEW",
        "direction": "BULL",
        "formation_date": "2026-04-01",
        "signal_date": "2026-04-28",
        "confirmed_date": None,
        "observed_date": "2026-05-01",
        "signal_tier": "T2",
        "signal_date_basis": "tier_event_date",
        "signal_provisional": False,
        "source_marker_date": None,
        "price_basis_date": "2026-05-01",
        "entry_date": "2026-05-01",
        "recorded_at": "2026-05-02",
        "entry": 100.0,
        "trigger": 100.0,
        "invalidation": 90.0,
        "targets": [115.0, 130.0],
        "horizon_days": 45,
    }
    opened = pa.open_row(pa.CHAMPION_KEY, plan, arena_night="2026-05-02")
    closed = pa.close_row(
        pa.CHAMPION_KEY,
        plan,
        {
            "outcome": "INVALIDATED",
            "close_date": "2026-05-04",
            "stock_result_pct": -10.0,
            "days_held": 3,
            "sessions_held": 1,
        },
        asof="2026-05-04",
    )
    assert pa.append_rows(pa.CHAMPION_KEY, [opened, closed], tmp_path, force=True) == 2

    board = pa.build_scoreboard(asof="2026-05-04", root=tmp_path)
    champion = next(
        policy for policy in board["policies"] if policy["policy"] == pa.CHAMPION_KEY
    )
    assert pa.ledger_path(pa.CHAMPION_KEY, tmp_path).parent.name == pa.LEDGER_ERA
    assert champion["n_closed"] == 1
    assert champion["avg_pct"] == -10.0
    sealed = board["historical_boundary"]["sealed_prior"]
    assert sealed["open_rows"] == 1
    assert sealed["close_rows"] == 1
    assert sealed["status"] == "sealed_read_only_excluded"
