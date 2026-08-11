"""Focused contract tests for the Options Prophet shadow projection."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import plistlib
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from scripts import build_prophet_marks as prophet_marks
from scripts import build_prophet_option_shadow_lifecycle as option_lifecycle
from scripts import mirror_flow_idx
from scripts.build_options_prophet import SCHEMA, build_from_disk, build_payload
from scripts.mirror_flow_idx import OPTIONS_PROPHET_R2_KEY


def _flow_payload() -> dict:
    common = {
        "signing_source": "tape",
        "recurrence_count": 6,
        "net_prem_norm_abs": 1.25,
        "flow_z": 2.1,
        "days_since_inflection": 1,
        "oi_confirmed": True,
        "zerodte_dominated": False,
        "gamma_regime": "short",
        "K_a": 3,
        "n_avail_a": 5,
        "K_b": 2,
        "n_avail_b": 4,
        "de_escalation": {"earnings_window": False},
    }
    return {
        "schema": "flow_leaders.v1",
        "session_date": "2026-08-07",
        "as_of": "2026-08-08T01:00:00+00:00",
        "stale": False,
        "cold_start": False,
        "board_a": [
            {**common, "ticker": "AAA", "fire_a": False, "fire_b": False},
            {**common, "ticker": "DUP", "fire_a": False, "fire_b": False},
        ],
        "board_b": [
            {**common, "ticker": "DUP", "fire_a": False, "fire_b": True},
            {**common, "ticker": "BBB", "fire_a": False, "fire_b": False},
        ],
    }


def _scoreboard(engine_id: str) -> dict:
    return {
        "engine_id": engine_id,
        "name_en": engine_id,
        "name_zh": f"zh-{engine_id}",
        "status": "ACCRUING",
        "authority": "display_only",
        "ruler": "21d_spy_excess",
        "n_fires": 3,
        "n_open": 1,
        "n_distinct_fire_dates": 2,
        "months_span": 0.4,
        "h5_n": 2,
        "h5_wr_abs": 0.5,
        "h5_wr_exc": 0.5,
        "h5_med_exc": 0.01,
        "h10_n": 1,
        "h21_n": 0,
        "h63_n": 0,
        "path25_n": 1,
        "path25_med_mfe": 0.04,
        "path63_n": 0,
    }


def _pick_payload() -> dict:
    return {
        "as_of": "2026-08-07",
        "built_at": "2026-08-08T11:20:33+00:00",
        "authority": "display_only",
        "books": {
            "plab_flow_leader": {
                "engine_id": "plab_flow_leader",
                "picks_today": [
                    {
                        "ticker": "AAA",
                        "rank": 1,
                        "fire_date": "2026-08-07",
                        "sector": "Tech",
                        "close_at_fire": 100.0,
                        "why": ["flow_recur", "fire_a"],
                        "features": {"signing_source": "tape"},
                    }
                ]
            },
            "plab_flow_washout": {
                "engine_id": "plab_flow_washout",
                "picks_today": [],
            },
        },
        "scoreboard": [
            _scoreboard("plab_flow_leader"),
            _scoreboard("plab_flow_washout"),
        ],
    }


def _failed_signing_gate() -> dict:
    return {
        "direction_reliable": False,
        "net_sign_recovery": 0.41,
        "bar": 0.7,
        "thetadata_tape": {
            "direction_reliable_tape": False,
            "production_ready": False,
            "sessions_n": 3,
            "production_ready_criteria": {"sessions_ok_needed": 5},
            "suspend_reason": "calibration failed",
        },
    }


def _coverage_payload() -> dict:
    return {
        "schema": "options_entry_coverage.v1",
        "as_of": "2026-08-07",
        "absent_stores": [],
        "feature_coverage": {
            "n_rows": 419,
            "n_features": 31,
            "features": [
                {
                    "feature": "iv_rank_252",
                    "n_nonnull": 0,
                    "n_total": 419,
                    "share_nonnull": 0.0,
                },
                {
                    "feature": "vanna_hedge_5d",
                    "n_nonnull": 14,
                    "n_total": 419,
                    "share_nonnull": 0.0334,
                },
            ],
        },
        "structural_nulls": {
            "iv_rank_252": {
                "null_share": 1.0,
                "root_cause": "IV backfill not yet attached",
            }
        },
    }


def test_projection_preserves_source_order_and_exports_only_pick_lab_fires():
    payload = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        signing_gate=_failed_signing_gate(),
        options_entry_gate={
            "schema": "options_entry.gate.v3",
            "status": "signal",
            "scored": False,
            "weight": 0.0,
        },
        options_entry_coverage=_coverage_payload(),
        dislocation_gate={
            "schema": "options_dislocation.gate.v1",
            "status": "insufficient_history",
            "scored": False,
            "scored_primitives": [],
        },
        built_at="2026-08-08T12:00:00Z",
    )

    assert payload["schema"] == SCHEMA
    assert [row["symbol"] for row in payload["watchlist"]] == ["AAA", "DUP", "BBB"]
    duplicate = payload["watchlist"][1]
    assert duplicate["lanes"] == ["flow_leader", "flow_washout"]
    assert duplicate["source_positions"] == {"board_a": 2, "board_b": 1}
    assert duplicate["fire_lanes"] == ["flow_washout"]

    # A source-board fire does not become an opportunity unless Pick Lab actually
    # admitted and ledgered it after its lockout/liquidity rules.
    assert [row["symbol"] for row in payload["opportunities"]] == ["AAA"]
    assert payload["opportunities"][0]["authority"] == "display_only"
    assert payload["opportunities"][0]["direction_reliable"] is False
    assert "score" not in payload["opportunities"][0]
    assert "confidence" not in payload["opportunities"][0]


def test_failed_signing_and_zero_authority_gates_are_explicitly_not_ready():
    payload = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        signing_gate=_failed_signing_gate(),
        options_entry_gate={"scored": False, "weight": 0.0},
        options_entry_coverage=_coverage_payload(),
        dislocation_gate={"scored": False, "scored_primitives": []},
        built_at="2026-08-08T12:00:00Z",
    )

    components = payload["readiness"]["components"]
    assert components["information"]["ready"] is False
    assert components["signed_flow"]["ready"] is False
    assert payload["direction"]["reliable"] is False
    assert payload["direction"]["value"] is None

    assert components["positioning"]["context_available"] is True
    assert components["positioning"]["promotion_ready"] is False
    assert components["positioning"]["ready"] is False
    assert components["positioning"]["authority"]["weight"] == 0.0
    coverage = components["positioning"]["evidence"]["coverage"]
    assert coverage["n_rows"] == 419
    assert coverage["n_features"] == 31
    assert coverage["feature_highlights"][0]["feature"] == "iv_rank_252"
    assert coverage["feature_highlights"][1]["feature"] == "vanna_hedge_5d"
    assert coverage["structural_null_highlights"][0] == {
        "feature": "iv_rank_252",
        "null_share": 1.0,
        "note": "IV backfill not yet attached",
    }

    assert components["execution"]["ready"] is False
    assert components["execution"]["context_available"] is False
    assert payload["trajectory"]["status"] == "withheld"
    assert payload["trajectory"]["take_profit"] is None
    assert payload["macro_feedback"] == {
        "enabled": False,
        "weight": 0.0,
        "mode": "shadow_only",
        "reason": (
            "No paired incremental-attribution gate has earned options weight in "
            "Macro Prophet ranking."
        ),
    }


def test_forward_flow_books_are_projected_without_claiming_incremental_attribution():
    payload = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        signing_gate=_failed_signing_gate(),
        built_at="2026-08-08T12:00:00Z",
    )

    ledgers = payload["forward_ledgers"]
    assert [row["engine_id"] for row in ledgers["books"]] == [
        "plab_flow_leader",
        "plab_flow_washout",
    ]
    assert ledgers["books"][0]["horizons"]["h5"]["n"] == 2
    assert ledgers["books"][0]["paths"]["path25"]["median_mfe"] == 0.04
    assert ledgers["books"][0]["name_en"] == "plab_flow_leader"
    assert ledgers["books"][0]["name_zh"] == "zh-plab_flow_leader"
    assert ledgers["incremental_options_attribution"]["available"] is False
    assert payload["readiness"]["gates"]["forward_sample"]["pass"] is False


def test_pit_execution_and_event_outcome_accrual_are_explicit_and_separate():
    payload = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        signing_gate=_failed_signing_gate(),
        built_at="2026-08-08T22:00:00-04:00",
    )

    assert payload["decision_at"] is None
    assert payload["available_at"] == "2026-08-09T02:00:00Z"
    assert payload["pit_provenance"] == {
        "clock": "UTC",
        "decision_at_required_for_issued_portfolio": True,
        "decision_at_status": "not_available_in_current_pick_lab_contract",
        "available_at_status": "exact_projection_publication_time",
        "source_available_at": {
            "flow_leaders": "2026-08-08T01:00:00Z",
            "pick_lab": "2026-08-08T11:20:33Z",
        },
        "promotion_ready": False,
        "reason": (
            "An issued position requires exact decision_at and available_at on "
            "every fire. Current Pick Lab fires expose exact artifact availability "
            "when present but not an exact decision clock."
        ),
    }
    fire = payload["opportunities"][0]
    assert fire["decision_at"] is None
    assert fire["available_at"] == "2026-08-08T11:20:33Z"
    assert fire["execution"] == {
        "status": "withheld",
        "executable": False,
        "contract": {
            "occ_symbol": None,
            "right": None,
            "strike": None,
            "expiry": None,
        },
        "entry": {"type": None, "price": None, "quote_at": None},
        "stop": None,
        "targets": [],
        "take_profit_management": None,
        "reason": (
            "No point-in-time contract selection, executable quote/fill, or managed "
            "exit lifecycle is attached."
        ),
    }

    accrual = payload["accrual"]
    assert accrual["events"]["unit"] == "immutable_options_originated_fire"
    assert accrual["events"]["published_now"] == 1
    assert accrual["events"]["timestamp_coverage"] == {
        "n_published": 1,
        "n_exact_decision_at": 0,
        "n_exact_available_at": 1,
    }
    assert list(accrual["outcomes"]["horizons"]) == [
        "1h",
        "eod",
        "1d",
        "3d",
        "5d",
        "10d",
        "expiry",
    ]
    assert accrual["outcomes"]["horizons"]["1h"]["instrumented"] is False
    assert accrual["outcomes"]["horizons"]["5d"]["instrumented"] is True
    assert accrual["outcomes"]["horizons"]["5d"]["pit_exact"] is False
    assert payload["selection_policy"]["style"] == "abstention_first"
    assert payload["selection_policy"]["capacity_enforced_by_projection"] is False
    assert payload["portfolio_boundary"]["operator_reviewed_issue_desk"] is False
    assert payload["portfolio_boundary"]["issued_model_portfolio"] is False
    assert payload["portfolio_boundary"]["managed_positions"] is False

    exact_pick = _pick_payload()
    exact_pick["books"]["plab_flow_leader"]["picks_today"][0].update(
        {
            "decision_at": "2026-08-07T15:42:00-04:00",
            "available_at": "2026-08-07T19:42:07Z",
        }
    )
    exact = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=exact_pick,
        built_at="2026-08-09T00:00:00Z",
    )["opportunities"][0]
    assert exact["decision_at"] == "2026-08-07T19:42:00Z"
    assert exact["available_at"] == "2026-08-07T19:42:07Z"

    reversed_pick = _pick_payload()
    reversed_pick["books"]["plab_flow_leader"]["picks_today"][0].update(
        {
            "decision_at": "2026-08-07T19:43:00Z",
            "available_at": "2026-08-07T19:42:07Z",
        }
    )
    assert build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=reversed_pick,
        built_at="2026-08-09T00:00:00Z",
    )["opportunities"] == []

    future_row = _pick_payload()
    future_row["books"]["plab_flow_leader"]["picks_today"][0]["available_at"] = (
        "2026-08-08T12:01:00Z"
    )
    assert build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=future_row,
        built_at="2026-08-08T12:00:00Z",
    )["opportunities"] == []


def test_konseki_market_memory_seam_is_context_only_and_zero_weight():
    missing = build_payload(built_at="2026-08-08T12:00:00Z")
    assert missing["context_inputs"]["konseki_market_memory"] == {
        "expected_schema": "konseki.market_memory/v1",
        "connected": False,
        "authority": "context_only",
        "weight": 0.0,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "decision_at": None,
        "available_at": None,
        "receipt": None,
        "reason": "No governed Konseki Market Memory receipt is connected.",
    }

    connected = build_payload(
        konseki_context={
            "schema": "konseki.market_memory/v1",
            "authority": "context_only",
            "memory_id": "km-20260808-001",
            "decision_at": "2026-08-08T19:00:00-04:00",
            "available_at": "2026-08-08T23:01:00Z",
            "context_tags": ["post-earnings-drift", "risk-on"],
            "score": 99,
            "weight": 1,
        },
        built_at="2026-08-09T00:00:00Z",
    )["context_inputs"]["konseki_market_memory"]
    assert connected["connected"] is True
    assert connected["authority"] == "context_only"
    assert connected["weight"] == 0
    assert connected["decision_at"] == "2026-08-08T23:00:00Z"
    assert connected["available_at"] == "2026-08-08T23:01:00Z"
    assert connected["receipt"] == {
        "memory_id": "km-20260808-001",
        "context_tags": ["post-earnings-drift", "risk-on"],
    }
    assert "score" not in connected

    wrong_authority = build_payload(
        konseki_context={
            "schema": "konseki.market_memory/v1",
            "authority": "ranking",
            "available_at": "2026-08-08T23:01:00Z",
        },
        built_at="2026-08-09T00:00:00Z",
    )["context_inputs"]["konseki_market_memory"]
    assert wrong_authority["connected"] is False
    assert wrong_authority["weight"] == 0

    for unsafe in (
        {
            "schema": "konseki.market_memory/v1",
            "authority": "context_only",
            "memory_id": "km-missing-decision",
            "available_at": "2026-08-08T23:01:00Z",
        },
        {
            "schema": "konseki.market_memory/v1",
            "authority": "context_only",
            "decision_at": "2026-08-08T23:00:00Z",
            "available_at": "2026-08-08T23:01:00Z",
        },
        {
            "schema": "konseki.market_memory/v1",
            "authority": "context_only",
            "memory_id": "km-clock-reversed",
            "decision_at": "2026-08-08T23:02:00Z",
            "available_at": "2026-08-08T23:01:00Z",
        },
    ):
        receipt = build_payload(
            konseki_context=unsafe,
            built_at="2026-08-09T00:00:00Z",
        )["context_inputs"]["konseki_market_memory"]
        assert receipt["connected"] is False
        assert receipt["receipt"] is None

    future_context = build_payload(
        konseki_context={
            "schema": "konseki.market_memory/v1",
            "authority": "context_only",
            "memory_id": "km-from-the-future",
            "decision_at": "2026-08-08T23:00:00Z",
            "available_at": "2026-08-08T23:01:00Z",
        },
        built_at="2026-08-08T12:00:00Z",
    )["context_inputs"]["konseki_market_memory"]
    assert future_context["connected"] is False
    assert future_context["receipt"] is None


def test_accrual_never_turns_missing_counts_into_measured_zero():
    pick_lab = _pick_payload()
    pick_lab["scoreboard"][0].pop("h5_n")
    pick_lab["scoreboard"][0].pop("n_distinct_fire_dates")
    accrual = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=pick_lab,
        built_at="2026-08-08T12:00:00Z",
    )["accrual"]

    assert accrual["events"]["books"] == []
    assert accrual["outcomes"]["horizons"]["5d"] == {
        "instrumented": False,
        "status": "not_instrumented",
        "authority": "none",
        "books": [],
        "pit_exact": False,
        "reason": (
            "No complete governed nonnegative sample count is available for "
            "every registered outcome book at this horizon."
        ),
    }

    fractional = _pick_payload()
    fractional["scoreboard"][0]["h5_n"] = 0.6
    fractional_accrual = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=fractional,
        built_at="2026-08-08T12:00:00Z",
    )["accrual"]
    assert fractional_accrual["outcomes"]["horizons"]["5d"]["instrumented"] is False
    assert fractional_accrual["outcomes"]["horizons"]["5d"]["books"] == []

    malformed_book = _pick_payload()
    malformed_book["scoreboard"][0]["n_fires"] = -1
    ledgers = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=malformed_book,
        built_at="2026-08-08T12:00:00Z",
    )["forward_ledgers"]
    assert [book["engine_id"] for book in ledgers["books"]] == [
        "plab_flow_washout"
    ]


def test_passing_signing_gate_never_turns_projection_into_directional_opportunity():
    signing_gate = {
        "direction_reliable": True,
        "thetadata_tape": {
            "direction_reliable_tape": True,
            "production_ready": True,
        },
    }
    payload = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        signing_gate=signing_gate,
        built_at="2026-08-09T00:00:00Z",
    )

    assert payload["direction"]["signing_gate_passed"] is True
    assert payload["direction"]["reliable"] is False
    assert payload["readiness"]["components"]["information"]["ready"] is True
    assert payload["readiness"]["components"]["information"]["promotion_ready"] is False
    assert payload["direction"]["value"] is None
    assert payload["opportunities"][0]["source_signing_reliable"] is True
    assert payload["opportunities"][0]["direction_reliable"] is False
    assert payload["watchlist"][0]["source_signing_reliable"] is True
    assert payload["watchlist"][0]["direction_reliable"] is False
    assert payload["macro_feedback"]["enabled"] is False


def test_string_why_is_one_reason_and_upstream_authority_cannot_escape():
    pick_lab = _pick_payload()
    pick_lab["books"]["plab_flow_leader"]["picks_today"][0]["why"] = "fire_a"
    pick_lab["scoreboard"][0]["authority"] = "rank_and_gate"

    payload = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=pick_lab,
        signing_gate=_failed_signing_gate(),
        built_at="2026-08-08T12:00:00Z",
    )

    assert payload["opportunities"][0]["why"] == ["fire_a"]
    assert payload["forward_ledgers"]["books"][0]["authority"] == "display_only"


def test_pick_lab_fire_must_belong_to_the_declared_session():
    pick_lab = _pick_payload()
    pick_lab["books"]["plab_flow_leader"]["picks_today"][0]["fire_date"] = (
        "2026-08-06"
    )

    payload = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=pick_lab,
        signing_gate=_failed_signing_gate(),
        built_at="2026-08-08T12:00:00Z",
    )

    assert payload["opportunities"] == []


def test_unknown_signing_source_fails_closed_even_when_known_source_gates_pass():
    flow = _flow_payload()
    for board_name in ("board_a", "board_b"):
        for row in flow[board_name]:
            row["signing_source"] = "mystery_feed"
    pick_lab = _pick_payload()
    pick_lab["books"]["plab_flow_leader"]["picks_today"][0]["features"] = {
        "signing_source": "mystery_feed"
    }
    payload = build_payload(
        flow_leaders=flow,
        pick_lab=pick_lab,
        signing_gate={
            "direction_reliable": True,
            "thetadata_tape": {
                "direction_reliable_tape": True,
                "production_ready": True,
            },
        },
        built_at="2026-08-08T12:00:00Z",
    )

    assert payload["opportunities"][0]["source_signing_reliable"] is False
    assert payload["watchlist"][0]["source_signing_reliable"] is False
    assert payload["direction"]["signing_gate_passed"] is False
    assert payload["readiness"]["components"]["information"]["ready"] is False


def test_missing_signing_source_blocks_mixed_source_information_readiness():
    flow = _flow_payload()
    flow["board_b"][1]["signing_source"] = None
    payload = build_payload(
        flow_leaders=flow,
        pick_lab=_pick_payload(),
        signing_gate={
            "direction_reliable": True,
            "thetadata_tape": {
                "direction_reliable_tape": True,
                "production_ready": True,
            },
        },
        built_at="2026-08-08T12:00:00Z",
    )

    assert payload["watchlist"][-1]["source_signing_reliable"] is False
    assert payload["direction"]["signing_gate_passed"] is False
    assert payload["readiness"]["components"]["information"]["ready"] is False


def test_nonempty_error_shaped_gate_does_not_claim_positioning_context():
    payload = build_payload(
        options_entry_gate={"error": "upstream read failed"},
        built_at="2026-08-08T12:00:00Z",
    )

    positioning = payload["readiness"]["components"]["positioning"]
    assert positioning["context_available"] is False
    assert positioning["ready"] is False


def test_foreign_stale_or_misaligned_sources_cannot_project_rows():
    foreign_flow = _flow_payload()
    foreign_flow["schema"] = "flow_leaders.future"
    payload = build_payload(
        flow_leaders=foreign_flow,
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )
    assert payload["watchlist"] == []
    assert payload["opportunities"] == []
    assert payload["readiness"]["gates"]["source_freshness"]["pass"] is False
    assert (
        payload["readiness"]["gates"]["source_freshness"]["scope"]
        == "flow_leaders_freshness_and_pick_lab_contract"
    )

    undated_flow = _flow_payload()
    undated_flow.pop("session_date")
    payload = build_payload(
        flow_leaders=undated_flow,
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )
    assert payload["watchlist"] == []
    assert payload["opportunities"] == []
    assert payload["readiness"]["components"]["flow_leaders"]["ready"] is False
    assert payload["readiness"]["gates"]["source_freshness"]["pass"] is False

    stale_flow = _flow_payload()
    stale_flow["stale"] = True
    payload = build_payload(
        flow_leaders=stale_flow,
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )
    assert payload["watchlist"] == []
    assert payload["opportunities"] == []

    future_flow = _flow_payload()
    future_flow["as_of"] = "2026-08-08T12:01:00Z"
    payload = build_payload(
        flow_leaders=future_flow,
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )
    assert payload["watchlist"] == []
    assert payload["opportunities"] == []
    assert payload["readiness"]["components"]["flow_leaders"]["ready"] is False

    future_picks = _pick_payload()
    future_picks["built_at"] = "2026-08-08T12:01:00Z"
    payload = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=future_picks,
        built_at="2026-08-08T12:00:00Z",
    )
    assert payload["opportunities"] == []
    assert payload["forward_ledgers"]["books"] == []
    assert payload["readiness"]["components"]["pick_lab"]["ready"] is False

    untrusted_picks = _pick_payload()
    untrusted_picks["authority"] = "rank_and_gate"
    payload = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=untrusted_picks,
        built_at="2026-08-08T12:00:00Z",
    )
    assert payload["opportunities"] == []
    assert payload["forward_ledgers"]["books"] == []
    assert payload["as_of"] == "2026-08-07"

    foreign_book = _pick_payload()
    foreign_book["books"]["plab_flow_leader"]["engine_id"] = "other_engine"
    payload = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=foreign_book,
        built_at="2026-08-08T12:00:00Z",
    )
    assert payload["opportunities"] == []
    assert payload["readiness"]["components"]["pick_lab"]["ready"] is False

    misaligned_picks = _pick_payload()
    misaligned_picks["as_of"] = "2026-08-06"
    payload = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=misaligned_picks,
        built_at="2026-08-08T12:00:00Z",
    )
    assert payload["opportunities"] == []
    alignment = payload["readiness"]["gates"]["source_alignment"]
    assert alignment["pass"] is False
    assert alignment["scope"] == "flow_leaders_and_pick_lab_only"


def test_nonfinite_upstream_values_become_strict_json_null():
    flow = _flow_payload()
    flow["board_a"][0]["gamma_regime"] = math.nan
    payload = build_payload(
        flow_leaders=flow,
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )

    # allow_nan=False follows the browser JSON boundary; this must never raise.
    encoded = json.dumps(payload, allow_nan=False)
    assert "NaN" not in encoded
    assert payload["watchlist"][0]["observations"]["gamma_regime"] is None


def test_disk_builder_writes_explicit_degraded_artifact_when_inputs_are_absent(tmp_path: Path):
    output = tmp_path / "site" / "options_prophet" / "index.json"
    payload = build_from_disk(
        flow_leaders_path=tmp_path / "missing-flow.json",
        pick_lab_path=tmp_path / "missing-picks.json",
        signing_gate_path=tmp_path / "missing-signing.json",
        options_entry_gate_path=tmp_path / "missing-entry.json",
        options_entry_coverage_path=tmp_path / "missing-coverage.json",
        dislocation_gate_path=tmp_path / "missing-dislocation.json",
        output_path=output,
        built_at="2026-08-08T12:00:00Z",
    )

    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert payload["opportunities"] == []
    assert payload["watchlist"] == []
    assert payload["readiness"]["components"]["execution"]["ready"] is False
    assert payload["provenance"]["flow_leaders"]["error"] == "missing"
    assert payload["provenance"]["pick_lab"]["error"] == "missing"
    assert payload["provenance"]["options_entry_coverage"]["error"] == "missing"


def test_disk_builder_consumes_optional_konseki_receipt_without_authority(tmp_path: Path):
    context = tmp_path / "konseki.json"
    context.write_text(
        json.dumps(
            {
                "schema": "konseki.market_memory/v1",
                "authority": "context_only",
                "memory_id": "km-1",
                "decision_at": "2026-08-08T23:00:00Z",
                "available_at": "2026-08-08T23:01:00Z",
                "context_tags": ["risk-on"],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "site" / "options_prophet" / "index.json"
    payload = build_from_disk(
        flow_leaders_path=tmp_path / "missing-flow.json",
        pick_lab_path=tmp_path / "missing-picks.json",
        signing_gate_path=tmp_path / "missing-signing.json",
        options_entry_gate_path=tmp_path / "missing-entry.json",
        options_entry_coverage_path=tmp_path / "missing-coverage.json",
        dislocation_gate_path=tmp_path / "missing-dislocation.json",
        konseki_context_path=context,
        output_path=output,
        built_at="2026-08-09T00:00:00Z",
    )

    receipt = payload["context_inputs"]["konseki_market_memory"]
    assert receipt["connected"] is True
    assert receipt["authority"] == "context_only"
    assert receipt["weight"] == 0
    assert payload["provenance"]["konseki_market_memory"]["path"] == str(context)


def test_daily_dag_synapse_and_r2_contract_are_wired():
    root = Path(__file__).resolve().parents[1]
    daily = (root / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    dag = (root / "config" / "dag.yml").read_text(encoding="utf-8")
    synapse_path = root / "config" / "synapse.yml"
    synapse = synapse_path.read_text(encoding="utf-8")
    artifacts = yaml.safe_load(synapse)["artifacts"]

    pick_call = 'run_py "pick lab nightly runner (build_pick_lab)" scripts.build_pick_lab'
    prophet_call = (
        'run_py "options prophet shadow (build_options_prophet)" '
        "scripts.build_options_prophet"
    )
    assert daily.index(prophet_call) > daily.index(pick_call)
    assert daily.index(prophet_call) - daily.index(pick_call) < 800
    assert "python -m scripts.mirror_flow_idx --options-prophet --strict" in daily
    assert "id: build_options_prophet" in dag
    assert "path: site/options_prophet/index.json" in synapse
    assert "schema: options.prophet_shadow/v1" in synapse
    for source_id in (
        "site-flow-leaders",
        "pick-lab-entry-ledger",
        "options-flow-signing-gate",
        "options-entry-gate",
        "options-entry-coverage",
        "options-dislocation-gate",
    ):
        assert "scripts/build_options_prophet.py" in artifacts[source_id]["consumers"]
    assert artifacts["options-entry-gate"]["schema"] == "options_entry.gate.v3"
    assert artifacts["options-prophet-shadow"]["storage"] == "git+r2"
    assert OPTIONS_PROPHET_R2_KEY == "options_prophet/index.json"


def test_options_prophet_mirror_selects_the_canonical_r2_key(tmp_path, monkeypatch):
    source = tmp_path / "site" / "options_prophet" / "index.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"schema":"options.prophet_shadow/v1"}', encoding="utf-8")
    fake_client = object()
    calls = []

    monkeypatch.setattr(mirror_flow_idx, "OPTIONS_PROPHET_PATH", source)
    monkeypatch.setattr(mirror_flow_idx, "_r2_client", lambda: fake_client)
    monkeypatch.setattr(
        mirror_flow_idx,
        "_upload",
        lambda client, path, key, bucket: (
            calls.append((client, path, key, bucket)) or True
        ),
    )
    monkeypatch.setenv("R2_BUCKET", "fixture-bucket")
    monkeypatch.setattr(
        sys, "argv", ["mirror_flow_idx", "--options-prophet"]
    )

    assert mirror_flow_idx.main() == 0
    assert calls == [
        (fake_client, source, "options_prophet/index.json", "fixture-bucket")
    ]


def test_options_prophet_strict_mirror_reports_publication_failure(
    tmp_path, monkeypatch
):
    source = tmp_path / "site" / "options_prophet" / "index.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"schema":"options.prophet_shadow/v1"}', encoding="utf-8")

    monkeypatch.setattr(mirror_flow_idx, "OPTIONS_PROPHET_PATH", source)
    monkeypatch.setattr(mirror_flow_idx, "_r2_client", lambda: object())
    monkeypatch.setattr(mirror_flow_idx, "_upload", lambda *_args: False)
    monkeypatch.setattr(
        sys, "argv", ["mirror_flow_idx", "--options-prophet", "--strict"]
    )

    assert mirror_flow_idx.main() == 1


def test_options_prophet_strict_mirror_rejects_nonfinite_json(tmp_path, monkeypatch):
    source = tmp_path / "site" / "options_prophet" / "index.json"
    source.parent.mkdir(parents=True)
    source.write_text(
        '{"schema":"options.prophet_shadow/v1","authority":"display_only",'
        '"mode":"shadow","watchlist":[{"flow_z":NaN}]}',
        encoding="utf-8",
    )

    monkeypatch.setattr(mirror_flow_idx, "OPTIONS_PROPHET_PATH", source)
    monkeypatch.setattr(
        mirror_flow_idx,
        "_r2_client",
        lambda: (_ for _ in ()).throw(AssertionError("must not build client")),
    )
    monkeypatch.setattr(
        sys, "argv", ["mirror_flow_idx", "--options-prophet", "--strict"]
    )

    assert mirror_flow_idx.main() == 1


def test_options_prophet_strict_mirror_rejects_incomplete_or_unsafe_contract(
    tmp_path, monkeypatch
):
    source = tmp_path / "site" / "options_prophet" / "index.json"
    source.parent.mkdir(parents=True)
    source.write_text(
        '{"schema":"options.prophet_shadow/v1","authority":"display_only",'
        '"mode":"shadow"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(mirror_flow_idx, "OPTIONS_PROPHET_PATH", source)
    monkeypatch.setattr(
        mirror_flow_idx,
        "_r2_client",
        lambda: (_ for _ in ()).throw(AssertionError("must not build client")),
    )
    monkeypatch.setattr(
        sys, "argv", ["mirror_flow_idx", "--options-prophet", "--strict"]
    )

    assert mirror_flow_idx.main() == 1

    crossed = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )
    crossed["opportunities"][0]["lane"] = "flow_washout"
    source.write_text(json.dumps(crossed), encoding="utf-8")
    assert mirror_flow_idx.main() == 1

    future_child = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )
    future_child["opportunities"][0]["available_at"] = "2026-08-08T12:01:00Z"
    source.write_text(json.dumps(future_child), encoding="utf-8")
    assert mirror_flow_idx.main() == 1

    future_source = build_payload(built_at="2026-08-08T12:00:00Z")
    future_source["pit_provenance"]["source_available_at"]["pick_lab"] = (
        "2026-08-08T12:01:00Z"
    )
    source.write_text(json.dumps(future_source), encoding="utf-8")
    assert mirror_flow_idx.main() == 1

    conflated_accrual = build_payload(built_at="2026-08-08T12:00:00Z")
    conflated_accrual["accrual"]["outcomes"][
        "separate_from_event_accrual"
    ] = False
    source.write_text(json.dumps(conflated_accrual), encoding="utf-8")
    assert mirror_flow_idx.main() == 1

    manufactured_zero = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )
    manufactured_zero["accrual"]["outcomes"]["horizons"]["5d"]["books"][0][
        "n"
    ] = None
    source.write_text(json.dumps(manufactured_zero), encoding="utf-8")
    assert mirror_flow_idx.main() == 1

    fractional_count = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )
    fractional_count["accrual"]["outcomes"]["horizons"]["5d"]["books"][0][
        "n"
    ] = 0.6
    source.write_text(json.dumps(fractional_count), encoding="utf-8")
    assert mirror_flow_idx.main() == 1

    duplicate_book = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )
    books = duplicate_book["accrual"]["outcomes"]["horizons"]["5d"]["books"]
    books.append(dict(books[0]))
    source.write_text(json.dumps(duplicate_book), encoding="utf-8")
    assert mirror_flow_idx.main() == 1

    malformed_ledger_count = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )
    malformed_ledger_count["forward_ledgers"]["books"][0]["n_fires"] = 0.6
    source.write_text(json.dumps(malformed_ledger_count), encoding="utf-8")
    assert mirror_flow_idx.main() == 1

    duplicate_ledger = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )
    ledger_books = duplicate_ledger["forward_ledgers"]["books"]
    ledger_books.append(dict(ledger_books[0]))
    source.write_text(json.dumps(duplicate_ledger), encoding="utf-8")
    assert mirror_flow_idx.main() == 1

    unsafe_konseki = build_payload(built_at="2026-08-08T12:00:00Z")
    unsafe_konseki["context_inputs"]["konseki_market_memory"] = {
        "expected_schema": "konseki.market_memory/v1",
        "connected": True,
        "authority": "context_only",
        "weight": 0,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "decision_at": None,
        "available_at": "2026-08-08T23:01:00Z",
        "receipt": {"memory_id": None, "context_tags": []},
    }
    source.write_text(json.dumps(unsafe_konseki), encoding="utf-8")
    assert mirror_flow_idx.main() == 1

    future_konseki = build_payload(built_at="2026-08-08T12:00:00Z")
    future_konseki["context_inputs"]["konseki_market_memory"] = {
        "expected_schema": "konseki.market_memory/v1",
        "connected": True,
        "authority": "context_only",
        "weight": 0,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "decision_at": "2026-08-08T12:00:30Z",
        "available_at": "2026-08-08T12:01:00Z",
        "receipt": {"memory_id": "km-future", "context_tags": []},
    }
    source.write_text(json.dumps(future_konseki), encoding="utf-8")
    assert mirror_flow_idx.main() == 1

    required_shape = build_payload(
        flow_leaders=_flow_payload(),
        pick_lab=_pick_payload(),
        built_at="2026-08-08T12:00:00Z",
    )
    for remove in (
        lambda item: item.pop("decision_at"),
        lambda item: item["selection_policy"].pop("target_batch_size"),
        lambda item: item["forward_ledgers"].pop(
            "incremental_options_attribution"
        ),
        lambda item: item["accrual"]["events"].pop("timestamp_coverage"),
        lambda item: item.pop("provenance"),
    ):
        malformed = json.loads(json.dumps(required_shape))
        remove(malformed)
        source.write_text(json.dumps(malformed), encoding="utf-8")
        assert mirror_flow_idx.main() == 1

    blank_symbol = json.loads(json.dumps(required_shape))
    blank_symbol["opportunities"][0]["symbol"] = "  "
    source.write_text(json.dumps(blank_symbol), encoding="utf-8")
    assert mirror_flow_idx.main() == 1


def test_options_prophet_strict_mirror_verifies_uploaded_object(tmp_path, monkeypatch):
    source = tmp_path / "site" / "options_prophet" / "index.json"
    source.parent.mkdir(parents=True)
    source.write_text(
        json.dumps(build_payload(built_at="2026-08-08T12:00:00Z")),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self):
            self.uploads = []
            self.heads = []

        def upload_file(self, path, bucket, key, ExtraArgs):
            self.uploads.append((path, bucket, key, ExtraArgs))

        def head_object(self, *, Bucket, Key):
            self.heads.append((Bucket, Key))
            return {
                "ContentLength": source.stat().st_size,
                "Metadata": {
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest()
                },
            }

    client = FakeClient()
    monkeypatch.setattr(mirror_flow_idx, "OPTIONS_PROPHET_PATH", source)
    monkeypatch.setattr(mirror_flow_idx, "_r2_client", lambda: client)
    monkeypatch.setattr(
        sys, "argv", ["mirror_flow_idx", "--options-prophet", "--strict"]
    )

    assert mirror_flow_idx.main() == 0
    assert client.heads == [("mastermindx", "options_prophet/index.json")]


def test_options_prophet_strict_mirror_rejects_remote_receipt_mismatch(
    tmp_path, monkeypatch
):
    source = tmp_path / "site" / "options_prophet" / "index.json"
    source.parent.mkdir(parents=True)
    payload = build_payload(built_at="2026-08-08T12:00:00Z")
    source.write_text(json.dumps(payload), encoding="utf-8")

    class StaleClient:
        def upload_file(self, *_args, **_kwargs):
            return None

        def head_object(self, **_kwargs):
            return {"ContentLength": 1, "Metadata": {"sha256": "stale"}}

    monkeypatch.setattr(mirror_flow_idx, "OPTIONS_PROPHET_PATH", source)
    monkeypatch.setattr(mirror_flow_idx, "_r2_client", lambda: StaleClient())
    monkeypatch.setattr(
        sys, "argv", ["mirror_flow_idx", "--options-prophet", "--strict"]
    )

    assert mirror_flow_idx.main() == 1


def test_prophet_marks_runner_uses_the_checkout_that_owns_it():
    """The M1 launcher must not jump to a workstation-only repository path."""
    repo = Path(__file__).resolve().parents[1]
    runner = (repo / "ops/launchd/run_prophet_marks_loop.sh").read_text(
        encoding="utf-8"
    )

    assert 'REPO_ROOT="/Users/' not in runner
    assert 'SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)' in runner
    assert 'REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)' in runner
    assert '"$PYTHON" -m "$MARKS_MODULE" --publish' in runner
    assert (
        '"$PYTHON" -m "$LIFECYCLE_MODULE" '
        "--sync-current-main-ledger --advance"
        in runner
    )
    assert runner.index('"$PYTHON" -m "$MARKS_MODULE" --publish') < runner.index(
        '"$PYTHON" -m "$LIFECYCLE_MODULE" --sync-current-main-ledger --advance'
    )

    plist_path = repo / "ops/launchd/com.mastermind.prophetmarks.plist"
    plist_text = plist_path.read_text(encoding="utf-8")
    assert "/Users/chriswong/Documents/Cluade/Macro Dashboard" not in plist_text
    assert plist_text.count("<string>/Users/chriswong/flow-ops-wt</string>") == 2


def test_prophet_marks_launchd_cadence_is_host_timezone_neutral():
    """The Vancouver M1 must not interpret a 09:25 calendar hour as ET."""
    repo = Path(__file__).resolve().parents[1]
    plist_path = repo / "ops/launchd/com.mastermind.prophetmarks.plist"
    payload = plistlib.loads(plist_path.read_bytes())

    assert payload["StartInterval"] == 300
    assert "StartCalendarInterval" not in payload
    assert payload["KeepAlive"] is False


def test_prophet_marks_runner_uses_et_window_on_vancouver_host(tmp_path):
    """Admission boundaries stay ET even when the host environment is Vancouver."""
    repo = Path(__file__).resolve().parents[1]
    source = repo / "ops/launchd/run_prophet_marks_loop.sh"
    fake_repo = tmp_path / "repo"
    fake_runner = fake_repo / "ops/launchd/run_prophet_marks_loop.sh"
    fake_runner.parent.mkdir(parents=True)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_date = fake_bin / "date"
    fake_date.write_text(
        """#!/bin/sh
test "$TZ" = "America/New_York" || exit 91
case "$1" in
  +%H) printf '%s\\n' "$FAKE_ET_HOUR" ;;
  +%M) printf '%s\\n' "$FAKE_ET_MINUTE" ;;
  *) printf '%s\\n' '2026-08-11T09:25:00-0400' ;;
esac
""",
        encoding="utf-8",
    )
    fake_date.chmod(0o755)

    fake_python = fake_bin / "python"
    fake_python.write_text(
        "#!/bin/sh\nprintf 'FAKE_PYTHON %s\\n' \"$*\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    runner_text = source.read_text(encoding="utf-8").replace(
        "/opt/homebrew/Caskroom/miniconda/base/bin/python",
        str(fake_python),
    )
    fake_runner.write_text(runner_text, encoding="utf-8")
    fake_runner.chmod(0o755)

    def _run(hour: int, minute: int) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "TZ": "America/Vancouver",
                "FAKE_ET_HOUR": f"{hour:02d}",
                "FAKE_ET_MINUTE": f"{minute:02d}",
                "PATH": f"{fake_bin}:/usr/bin:/bin",
            }
        )
        return subprocess.run(
            ["/bin/sh", str(fake_runner)],
            cwd=fake_repo,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    before = _run(9, 24)
    at_open = _run(9, 25)
    before_close = _run(16, 4)
    at_close = _run(16, 5)

    assert before.returncode == 0
    assert "FAKE_PYTHON" not in before.stdout
    assert "outside 09:25–16:05 ET window" in before.stdout
    assert at_open.returncode == 0
    assert "FAKE_PYTHON -m scripts.build_prophet_marks --publish" in at_open.stdout
    assert (
        "FAKE_PYTHON -m scripts.build_prophet_option_shadow_lifecycle "
        "--sync-current-main-ledger --advance"
        in at_open.stdout
    )
    assert "PROPHET_LEDGER_PATH" in runner_text
    assert "PROPHET_LEDGER_RECEIPT_PATH" in runner_text
    assert before_close.returncode == 0
    assert "FAKE_PYTHON -m scripts.build_prophet_marks --publish" in before_close.stdout
    assert (
        "FAKE_PYTHON -m scripts.build_prophet_option_shadow_lifecycle "
        "--sync-current-main-ledger --advance"
        in before_close.stdout
    )
    assert at_close.returncode == 0
    assert "FAKE_PYTHON" not in at_close.stdout
    assert "outside 09:25–16:05 ET window" in at_close.stdout


def test_prophet_marks_publish_uses_canonical_r2_and_tombstones_empty(monkeypatch):
    """A stale operations checkout cannot keep an obsolete contract alive."""
    published: list[tuple[dict, dict]] = []
    index = {
        "schema": "prophet.index/v1",
        "asof": "2026-08-11",
        "recorded_at": "2026-08-11",
        "plans": [],
    }

    monkeypatch.setattr(prophet_marks, "_is_rth_now", lambda: True)
    monkeypatch.setattr(prophet_marks, "_load_index_r2", lambda: index)
    monkeypatch.setattr(
        prophet_marks,
        "_load_index_local",
        lambda: (_ for _ in ()).throw(AssertionError("local index must not be read")),
    )
    monkeypatch.setattr(
        prophet_marks,
        "_fetch_contract_quote",
        lambda *_args: (_ for _ in ()).throw(AssertionError("no quote is required")),
    )
    monkeypatch.setattr(
        prophet_marks,
        "_publish_r2",
        lambda payload, **kwargs: published.append((payload, kwargs)) or payload,
    )

    payload = prophet_marks.build_marks(publish=True)

    assert payload is not None
    assert payload["marks"] == {}
    assert payload["coverage"]["active_option_plan_count"] == 0
    assert len(published) == 1
    assert published[0][0]["marks"] == {}
    assert published[0][1]["index"] is index
    assert published[0][1]["evidence_rows"] == []


def test_prophet_marks_publish_refuses_local_fallback_when_r2_index_is_unavailable(
    monkeypatch,
):
    """Missing canonical state must not resurrect a stale local plan set."""
    monkeypatch.setattr(prophet_marks, "_is_rth_now", lambda: True)
    monkeypatch.setattr(prophet_marks, "_load_index_r2", lambda: None)
    monkeypatch.setattr(
        prophet_marks,
        "_load_index_local",
        lambda: (_ for _ in ()).throw(AssertionError("local index must not be read")),
    )
    monkeypatch.setattr(
        prophet_marks,
        "_publish_r2",
        lambda _body: (_ for _ in ()).throw(AssertionError("must not publish")),
    )

    assert prophet_marks.build_marks(publish=True) is None


def test_prophet_marks_publish_failure_is_a_build_failure(monkeypatch):
    """A failed write cannot be reported as a successful fresh marks cycle."""
    monkeypatch.setattr(prophet_marks, "_is_rth_now", lambda: True)
    monkeypatch.setattr(
        prophet_marks,
        "_load_index_r2",
        lambda: {
            "schema": "prophet.index/v1",
            "asof": "2026-08-11",
            "recorded_at": "2026-08-11",
            "plans": [],
        },
    )
    monkeypatch.setattr(prophet_marks, "_publish_r2", lambda *_args, **_kwargs: None)

    assert prophet_marks.build_marks(publish=True) is None


def _option_mark_plan(
    plan_id: str = "SOFI-BULL-20260803",
    *,
    phase: str = "pre_trigger",
    entry_premium: float | None = 1.8,
) -> dict:
    return {
        "id": plan_id,
        "asset": "SOFI",
        "phase": phase,
        "closed": False,
        "plan_asof": "2026-08-03",
        "recorded_at": "2026-08-03",
        "entry_date": "2026-08-03",
        "option_contract": {
            "right": "C",
            "strike": 16.0,
            "expiry": "2026-10-16",
            "entry_premium": entry_premium,
            "freshness": "EOD mark",
        },
    }


def _option_mark_index(plans: list[dict] | None = None) -> dict:
    return {
        "schema": "prophet.index/v1",
        "asof": "2026-08-11",
        "recorded_at": "2026-08-11",
        "plans": plans if plans is not None else [_option_mark_plan()],
    }


def _available_option_quote() -> dict:
    return {
        "bid": 2.91,
        "ask": 3.05,
        "last": 2.91,
        "quote_ts_utc": "2026-08-11T13:45:43.000000+00:00",
        "trade_ts_utc": "2026-08-11T13:45:45.000000+00:00",
        "source_sequence": 8,
    }


def test_prophet_option_mark_observation_is_schema_clean_and_not_pnl():
    from jsonschema import Draft202012Validator, FormatChecker

    repo = Path(__file__).resolve().parents[1]
    schema = json.loads(
        (
            repo
            / "contracts/options/prophet.option_mark_observation.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    index = _option_mark_index()
    plan = index["plans"][0]
    contract, contract_reason = prophet_marks._plan_contract(
        plan, session_date=date(2026, 8, 11)
    )
    quote, quote_reason = prophet_marks._validated_quote(
        _available_option_quote(),
        observed_at=datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc),
        session_date=date(2026, 8, 11),
    )
    row = prophet_marks._plan_evidence_row(
        plan,
        contract=contract,
        contract_reason=contract_reason,
        quote=quote,
        quote_reason=quote_reason,
    )
    coverage = prophet_marks._evidence_coverage(
        index=index, rows=[row], source_call_count=1
    )
    observation = prophet_marks._build_observation(
        index=index,
        observed_at_utc="2026-08-11T14:00:00+00:00",
        session_date="2026-08-11",
        rows=[row],
        coverage=coverage,
        previous=None,
    )

    errors = sorted(validator.iter_errors(observation), key=lambda e: list(e.path))
    assert errors == []
    assert row["mark_change_from_plan_pct"] == 65.5556
    assert row["plan_state_context"] == {
        "state": "watch_only_pre_trigger",
        "position_assumed": False,
    }
    assert row["quote"]["label"] == "trade_paired_bid_ask"
    assert row["quote"]["quote_age_seconds"] == 857
    assert row["quote"]["trade_age_seconds"] == 855
    assert row["quote"]["source_sequence"] == 8
    assert observation["storage"] == {
        "visibility": "host_private",
        "public_discovery": False,
        "public_redistribution": False,
    }
    assert observation["source"]["provider"] == "licensed_options_history_feed"
    assert observation["source"]["size_retained"] is False
    assert observation["source"]["venue_retained"] is False
    assert observation["source"]["condition_retained"] is False
    assert not any(observation["authority"].values())
    assert observation["limitations"]["not_trade_pnl"] is True
    assert observation["limitations"]["not_lifecycle_outcome"] is True
    assert observation["limitations"]["no_provider_observed_entry_or_exit"] is True
    assert observation["limitations"]["prospective_from_first_observation_only"] is True
    pointer = prophet_marks._observation_pointer(observation)
    assert pointer["key"].endswith(f"/{observation['observation_id']}.json")
    assert pointer["sha256"] == hashlib.sha256(
        prophet_marks._canonical_json_bytes(observation)
    ).hexdigest()


def test_prophet_option_mark_change_requires_an_explicit_eod_entry_basis():
    plan = _option_mark_plan()
    plan["option_contract"]["freshness"] = "unknown"
    contract, contract_reason = prophet_marks._plan_contract(
        plan, session_date=date(2026, 8, 11)
    )
    quote, quote_reason = prophet_marks._validated_quote(
        _available_option_quote(),
        observed_at=datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc),
        session_date=date(2026, 8, 11),
    )

    row = prophet_marks._plan_evidence_row(
        plan,
        contract=contract,
        contract_reason=contract_reason,
        quote=quote,
        quote_reason=quote_reason,
    )

    assert row["quote_status"] == "available"
    assert row["plan_entry_mark"] is None
    assert row["mark_change_status"] == "unavailable"
    assert row["mark_change_reason"] == "ENTRY_MARK_BASIS_UNVERIFIED"
    assert row["mark_change_from_plan_pct"] is None


def test_prophet_marks_accounts_for_abstentions_and_deduplicates_contract_calls(
    monkeypatch,
):
    fixed = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is None else fixed.astimezone(tz)

    plans = [
        _option_mark_plan("SOFI-BULL-A", phase="pre_trigger"),
        _option_mark_plan("SOFI-BULL-B", phase="triggered_pre_t1"),
        {
            **_option_mark_plan("SOFI-BULL-BAD"),
            "option_contract": {
                "right": "C",
                "strike": 16.0005,
                "expiry": "2026-10-16",
                "entry_premium": 1.8,
            },
        },
        {
            **_option_mark_plan("SOFI-BULL-EMPTY"),
            "option_contract": {},
        },
    ]
    calls: list[tuple] = []
    monkeypatch.setattr(prophet_marks, "datetime", FixedDateTime)
    monkeypatch.setattr(prophet_marks, "_is_rth_now", lambda: True)
    monkeypatch.setattr(
        prophet_marks, "_load_index", lambda **_kwargs: _option_mark_index(plans)
    )

    def fetch(*args):
        calls.append(args)
        return _available_option_quote()

    monkeypatch.setattr(prophet_marks, "_fetch_contract_quote", fetch)
    payload = prophet_marks.build_marks(dry_run=True)

    assert payload is not None
    assert len(calls) == 1
    assert list(payload["marks"]) == ["SOFI  261016C00016000"]
    assert payload["coverage"] == {
        "index_plan_count": 4,
        "active_option_plan_count": 4,
        "unique_contract_count": 1,
        "source_call_count": 1,
        "available_quote_plan_count": 2,
        "abstained_quote_plan_count": 2,
        "available_mark_change_plan_count": 2,
        "all_active_option_plans_accounted": True,
    }


def test_prophet_marks_quote_guard_rejects_wrong_clock_and_bad_market_shape():
    observed = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
    session = date(2026, 8, 11)
    cases = [
        (
            {
                **_available_option_quote(),
                "quote_ts_utc": "2026-08-11T14:00:01+00:00",
                "trade_ts_utc": "2026-08-11T14:00:01+00:00",
            },
            "QUOTE_AFTER_OBSERVATION",
        ),
        (
            {
                **_available_option_quote(),
                "trade_ts_utc": "2026-08-11T14:00:01+00:00",
            },
            "TRADE_AFTER_OBSERVATION",
        ),
        (
            {
                **_available_option_quote(),
                "quote_ts_utc": "2026-08-11T13:50:00+00:00",
                "trade_ts_utc": "2026-08-11T13:49:59+00:00",
            },
            "QUOTE_AFTER_TRADE",
        ),
        (
            {
                **_available_option_quote(),
                "quote_ts_utc": "2026-08-10T19:59:00+00:00",
                "trade_ts_utc": "2026-08-10T19:59:01+00:00",
            },
            "QUOTE_WRONG_SESSION",
        ),
        (
            {
                **_available_option_quote(),
                "quote_ts_utc": "2026-08-11T13:29:59+00:00",
                "trade_ts_utc": "2026-08-11T13:29:59+00:00",
            },
            "QUOTE_OUTSIDE_RTH",
        ),
        ({**_available_option_quote(), "bid": 4.0, "ask": 3.0}, "QUOTE_SHAPE_INVALID"),
        ({**_available_option_quote(), "bid": float("inf")}, "QUOTE_SHAPE_INVALID"),
    ]
    for raw, reason in cases:
        quote, actual = prophet_marks._validated_quote(
            raw, observed_at=observed, session_date=session
        )
        assert quote is None
        assert actual == reason

    too_old, too_old_reason = prophet_marks._validated_quote(
        _available_option_quote(),
        observed_at=datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc),
        session_date=session,
    )
    assert too_old is None
    assert too_old_reason == "QUOTE_TOO_OLD"

    wrong_trade_session, wrong_trade_reason = prophet_marks._validated_quote(
        {
            **_available_option_quote(),
            "trade_ts_utc": "2026-08-12T13:45:45+00:00",
        },
        observed_at=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
        session_date=session,
    )
    assert wrong_trade_session is None
    assert wrong_trade_reason == "TRADE_WRONG_SESSION"


def test_prophet_marks_selects_latest_trade_paired_quote_deterministically(
    monkeypatch,
):
    assert prophet_marks._source_sequence("-1") == -1

    class FakeFrame:
        empty = False

        def __init__(self, rows):
            self.rows = rows

        def to_dict(self, *, orient):
            assert orient == "records"
            return list(self.rows)

    rows = [
        {
            "quote_timestamp": "2026-08-11T09:45:42.900",
            "trade_timestamp": "2026-08-11T09:45:45.100",
            "sequence": 99,
            "bid": 2.8,
            "ask": 2.9,
            "price": 2.85,
        },
        {
            "quote_timestamp": "2026-08-11T09:45:43.000",
            "trade_timestamp": "2026-08-11T09:45:45.000",
            "sequence": 7,
            "bid": 2.91,
            "ask": 3.05,
            "price": 2.91,
        },
        {
            "quote_timestamp": "2026-08-11T09:45:43.000",
            "trade_timestamp": "2026-08-11T09:45:45.000",
            "sequence": 8,
            "bid": 2.92,
            "ask": 3.06,
            "price": 2.93,
        },
    ]

    import collectors

    class FakeThetaData:
        @staticmethod
        def trade_quote(**_kwargs):
            return FakeFrame(reversed(rows))

    monkeypatch.setattr(collectors, "thetadata", FakeThetaData, raising=False)
    selected = prophet_marks._fetch_contract_quote(
        "SOFI", "C", "2026-10-16", 16.0, date(2026, 8, 11)
    )

    assert selected == {
        "bid": 2.92,
        "ask": 3.06,
        "last": 2.93,
        "quote_ts_utc": "2026-08-11T13:45:43.000000+00:00",
        "trade_ts_utc": "2026-08-11T13:45:45.000000+00:00",
        "source_sequence": 8,
    }

    legacy_rows = [
        {key: value for key, value in row.items() if key != "sequence"}
        for row in rows[:2]
    ]

    class LegacyThetaData:
        @staticmethod
        def trade_quote(**_kwargs):
            return FakeFrame(reversed(legacy_rows))

    monkeypatch.setattr(collectors, "thetadata", LegacyThetaData, raising=False)
    legacy_selected = prophet_marks._fetch_contract_quote(
        "SOFI", "C", "2026-10-16", 16.0, date(2026, 8, 11)
    )
    assert legacy_selected == {
        "bid": 2.91,
        "ask": 3.05,
        "last": 2.91,
        "quote_ts_utc": "2026-08-11T13:45:43.000000+00:00",
        "trade_ts_utc": "2026-08-11T13:45:45.000000+00:00",
        "source_sequence": None,
    }

    class ConflictingThetaData:
        @staticmethod
        def trade_quote(**_kwargs):
            return FakeFrame(
                [
                    rows[-1],
                    {**rows[-1], "bid": 9.99},
                ]
            )

    monkeypatch.setattr(
        collectors,
        "thetadata",
        ConflictingThetaData,
        raising=False,
    )
    assert (
        prophet_marks._fetch_contract_quote(
            "SOFI", "C", "2026-10-16", 16.0, date(2026, 8, 11)
        )
        is None
    )

    class ConflictingLegacyThetaData:
        @staticmethod
        def trade_quote(**_kwargs):
            return FakeFrame(
                [
                    {key: value for key, value in rows[-1].items() if key != "sequence"},
                    {
                        key: value
                        for key, value in {**rows[-1], "bid": 9.99}.items()
                        if key != "sequence"
                    },
                ]
            )

    monkeypatch.setattr(
        collectors,
        "thetadata",
        ConflictingLegacyThetaData,
        raising=False,
    )
    assert (
        prophet_marks._fetch_contract_quote(
            "SOFI", "C", "2026-10-16", 16.0, date(2026, 8, 11)
        )
        is None
    )


class _MarkR2Error(RuntimeError):
    def __init__(self, code: str, status: int):
        super().__init__(code)
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }


class _FakeMarkR2:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.puts: list[dict] = []

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise _MarkR2Error("NoSuchKey", 404)
        body = self.objects[Key]
        return {
            "Body": io.BytesIO(body),
            "ContentLength": len(body),
            "ETag": '"' + hashlib.sha256(body).hexdigest() + '"',
        }

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        body = bytes(kwargs["Body"])
        self.puts.append(dict(kwargs))
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise _MarkR2Error("PreconditionFailed", 412)
        if "IfMatch" in kwargs:
            if key not in self.objects:
                raise _MarkR2Error("PreconditionFailed", 412)
            actual = '"' + hashlib.sha256(self.objects[key]).hexdigest() + '"'
            if kwargs["IfMatch"] != actual:
                raise _MarkR2Error("PreconditionFailed", 412)
        self.objects[key] = body
        return {}


def _published_mark_payload(at: str) -> dict:
    return {
        "schema": "prophet.live_marks/v1",
        "asof_utc": at,
        "session_date": "2026-08-11",
        "marks": {
            "SOFI  261016C00016000": {
                "bid": 2.91,
                "ask": 3.05,
                "mid": 2.98,
                "last": 2.91,
                "ts_utc": "2026-08-11T13:45:43.000000+00:00",
                "trade_ts_utc": "2026-08-11T13:45:45.000000+00:00",
            }
        },
        "coverage": {
            "index_plan_count": 1,
            "active_option_plan_count": 1,
            "unique_contract_count": 1,
            "source_call_count": 1,
            "available_quote_plan_count": 1,
            "abstained_quote_plan_count": 0,
            "available_mark_change_plan_count": 1,
            "all_active_option_plans_accounted": True,
        },
    }


def _published_mark_row() -> dict:
    index = _option_mark_index()
    plan = index["plans"][0]
    contract, contract_reason = prophet_marks._plan_contract(
        plan, session_date=date(2026, 8, 11)
    )
    quote, quote_reason = prophet_marks._validated_quote(
        _available_option_quote(),
        observed_at=datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc),
        session_date=date(2026, 8, 11),
    )
    return prophet_marks._plan_evidence_row(
        plan,
        contract=contract,
        contract_reason=contract_reason,
        quote=quote,
        quote_reason=quote_reason,
    )


def _private_mark_head(root: Path) -> tuple[dict, dict, Path]:
    head = json.loads((root / "current.json").read_bytes())
    pointer = head["evidence"]
    observation_path = root / pointer["key"]
    observation = json.loads(observation_path.read_bytes())
    return pointer, observation, observation_path


def test_prophet_marks_publication_keeps_backwards_linked_evidence_host_private(
    monkeypatch,
    tmp_path,
):
    client = _FakeMarkR2()
    index = _option_mark_index()
    rows = [_published_mark_row()]
    private_root = tmp_path / "private-option-marks"
    monkeypatch.setenv(
        "PROPHET_OPTION_EVIDENCE_STATE_ROOT",
        str(private_root),
    )
    monkeypatch.setattr(prophet_marks, "_r2_client", lambda: client)

    first = prophet_marks._publish_r2(
        _published_mark_payload("2026-08-11T14:00:00+00:00"),
        index=index,
        evidence_rows=rows,
    )
    assert first is not None
    assert "evidence" not in first
    assert len(client.puts) == 1
    assert client.puts[0]["Key"] == prophet_marks.R2_KEY
    assert "IfNoneMatch" not in client.puts[0]
    assert "IfMatch" not in client.puts[0]
    assert b"evidence" not in client.objects[prophet_marks.R2_KEY]
    assert b"thetadata" not in client.objects[prophet_marks.R2_KEY].lower()

    first_pointer, first_observation, first_path = _private_mark_head(private_root)
    assert first_observation["previous"] is None
    assert first_observation["storage"]["visibility"] == "host_private"
    assert first_observation["storage"]["public_redistribution"] is False
    assert private_root.stat().st_mode & 0o777 == 0o700
    assert (private_root / "observations").stat().st_mode & 0o777 == 0o700
    assert first_path.parent.stat().st_mode & 0o777 == 0o700
    assert (private_root / "current.json").stat().st_mode & 0o777 == 0o600
    assert first_path.stat().st_mode & 0o777 == 0o600

    second = prophet_marks._publish_r2(
        _published_mark_payload("2026-08-11T14:05:00+00:00"),
        index=index,
        evidence_rows=rows,
    )
    assert second is not None
    assert "evidence" not in second
    assert len(client.puts) == 2
    assert all(item["Key"] == prophet_marks.R2_KEY for item in client.puts)
    second_pointer, second_observation, _second_path = _private_mark_head(private_root)
    assert second_pointer["observation_id"] != first_pointer["observation_id"]
    assert second_observation["previous"] == first_pointer
    assert "evidence" not in json.loads(client.objects[prophet_marks.R2_KEY])


def test_prophet_marks_refuses_a_corrupt_private_chain_head(monkeypatch, tmp_path):
    client = _FakeMarkR2()
    private_root = tmp_path / "private-option-marks"
    monkeypatch.setenv(
        "PROPHET_OPTION_EVIDENCE_STATE_ROOT",
        str(private_root),
    )
    monkeypatch.setattr(prophet_marks, "_r2_client", lambda: client)
    assert prophet_marks._publish_r2(
        _published_mark_payload("2026-08-11T13:55:00+00:00"),
        index=_option_mark_index(),
        evidence_rows=[_published_mark_row()],
    ) is not None
    original = client.objects[prophet_marks.R2_KEY]
    put_count = len(client.puts)
    _pointer, _observation, observation_path = _private_mark_head(private_root)
    observation_path.write_bytes(observation_path.read_bytes() + b"tamper")

    assert (
        prophet_marks._publish_r2(
            _published_mark_payload("2026-08-11T14:00:00+00:00"),
            index=_option_mark_index(),
            evidence_rows=[_published_mark_row()],
        )
        is None
    )
    assert client.objects[prophet_marks.R2_KEY] == original
    assert len(client.puts) == put_count


def test_prophet_marks_refuses_a_forged_private_content_identity(
    monkeypatch,
    tmp_path,
):
    client = _FakeMarkR2()
    index = _option_mark_index()
    row = _published_mark_row()
    private_root = tmp_path / "private-option-marks"
    monkeypatch.setenv(
        "PROPHET_OPTION_EVIDENCE_STATE_ROOT",
        str(private_root),
    )
    monkeypatch.setattr(prophet_marks, "_r2_client", lambda: client)
    assert prophet_marks._publish_r2(
        _published_mark_payload("2026-08-11T13:55:00+00:00"),
        index=index,
        evidence_rows=[row],
    ) is not None
    original = client.objects[prophet_marks.R2_KEY]
    put_count = len(client.puts)
    pointer, observation, observation_path = _private_mark_head(private_root)
    observation["rows"][0]["mark_change_from_plan_pct"] = 99.0
    body = prophet_marks._canonical_json_bytes(observation)
    observation_path.write_bytes(body)
    pointer["sha256"] = hashlib.sha256(body).hexdigest()
    pointer["bytes"] = len(body)
    (private_root / "current.json").write_bytes(
        prophet_marks._canonical_json_bytes(
            {
                "schema": prophet_marks.EVIDENCE_HEAD_SCHEMA,
                "evidence": pointer,
            }
        )
    )

    assert (
        prophet_marks._publish_r2(
            _published_mark_payload("2026-08-11T14:00:00+00:00"),
            index=index,
            evidence_rows=[row],
        )
        is None
    )
    assert client.objects[prophet_marks.R2_KEY] == original
    assert len(client.puts) == put_count


def test_prophet_marks_runtime_schema_failure_prevents_any_publication(
    monkeypatch,
    tmp_path,
):
    client = _FakeMarkR2()
    private_root = tmp_path / "private-option-marks"
    monkeypatch.setenv(
        "PROPHET_OPTION_EVIDENCE_STATE_ROOT",
        str(private_root),
    )
    monkeypatch.setenv(
        "PROPHET_OPTION_EVIDENCE_SCHEMA_PATH",
        str(tmp_path / "missing-observation-schema.json"),
    )
    monkeypatch.setattr(prophet_marks, "_EVIDENCE_VALIDATOR", None)
    monkeypatch.setattr(prophet_marks, "_r2_client", lambda: client)

    assert prophet_marks._publish_r2(
        _published_mark_payload("2026-08-11T14:00:00+00:00"),
        index=_option_mark_index(),
        evidence_rows=[_published_mark_row()],
    ) is None
    assert client.puts == []
    assert prophet_marks.R2_KEY not in client.objects
    assert not (private_root / "current.json").exists()
    assert not (private_root / "observations").exists()


def test_prophet_marks_refuses_a_non_private_state_directory(monkeypatch, tmp_path):
    client = _FakeMarkR2()
    private_root = tmp_path / "world-readable-option-marks"
    private_root.mkdir(mode=0o755)
    private_root.chmod(0o755)
    monkeypatch.setenv(
        "PROPHET_OPTION_EVIDENCE_STATE_ROOT",
        str(private_root),
    )
    monkeypatch.setattr(prophet_marks, "_r2_client", lambda: client)

    assert prophet_marks._publish_r2(
        _published_mark_payload("2026-08-11T14:00:00+00:00"),
        index=_option_mark_index(),
        evidence_rows=[_published_mark_row()],
    ) is None
    assert client.puts == []
    assert list(private_root.iterdir()) == []


def _lifecycle_private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _lifecycle_emit_mark(
    monkeypatch,
    mark_root: Path,
    *,
    observed_at: str,
    session_date: str,
    phase: str,
    available: bool = True,
    mid: float = 3.0,
    strike: float = 16.0,
    plan_id: str = "SOFI-BULL-20260803",
) -> tuple[dict, dict]:
    monkeypatch.setenv("PROPHET_OPTION_EVIDENCE_STATE_ROOT", str(mark_root))
    plan = _option_mark_plan(plan_id, phase=phase)
    plan["option_contract"]["strike"] = strike
    plan["option_contract"]["expiry"] = "2026-10-16"
    index = {
        "schema": "prophet.index/v1",
        "asof": session_date,
        "recorded_at": session_date,
        "plans": [plan],
    }
    session = date.fromisoformat(session_date)
    contract, contract_reason = prophet_marks._plan_contract(
        plan, session_date=session
    )
    if available:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        quote_clock = observed - timedelta(minutes=1)
        raw_quote = {
            "bid": round(mid - 0.05, 4),
            "ask": round(mid + 0.05, 4),
            "last": round(mid, 4),
            "quote_ts_utc": quote_clock.isoformat(),
            "trade_ts_utc": (quote_clock + timedelta(seconds=1)).isoformat(),
            "source_sequence": 7,
        }
        quote, quote_reason = prophet_marks._validated_quote(
            raw_quote,
            observed_at=observed,
            session_date=session,
        )
    else:
        quote, quote_reason = None, "SOURCE_UNAVAILABLE"
    row = prophet_marks._plan_evidence_row(
        plan,
        contract=contract,
        contract_reason=contract_reason,
        quote=quote,
        quote_reason=quote_reason,
    )
    coverage = prophet_marks._evidence_coverage(
        index=index,
        rows=[row],
        source_call_count=1,
    )
    pointer = prophet_marks._publish_private_observation(
        index=index,
        payload={
            "schema": "prophet.live_marks/v1",
            "asof_utc": observed_at,
            "session_date": session_date,
            "marks": {},
            "coverage": coverage,
        },
        evidence_rows=[row],
    )
    return pointer, row


def _lifecycle_ledger(path: Path) -> Path:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text("# canonical test ledger\n", encoding="utf-8")
    path.chmod(0o600)
    _lifecycle_refresh_ledger_receipt(path)
    return path


def _lifecycle_receipt_path(path: Path) -> Path:
    return path.parent / "receipt.json"


def _lifecycle_refresh_ledger_receipt(
    path: Path,
    *,
    source_commit: str = "a" * 40,
) -> dict:
    body = path.read_bytes()
    row_count = sum(
        bool(line.strip()) and not line.lstrip().startswith(b"#")
        for line in body.splitlines()
    )
    receipt = {
        "schema": option_lifecycle.LEDGER_SNAPSHOT_RECEIPT_SCHEMA,
        "source_repository": option_lifecycle.CANONICAL_LEDGER_REPOSITORY,
        "source_ref": option_lifecycle.CANONICAL_LEDGER_REF,
        "source_commit": source_commit,
        "source_path": option_lifecycle.CANONICAL_LEDGER_SOURCE_PATH,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "row_count": row_count,
    }
    receipt_path = _lifecycle_receipt_path(path)
    receipt_path.write_bytes(option_lifecycle._canonical_json_bytes(receipt))
    receipt_path.chmod(0o600)
    return receipt


def _lifecycle_append_close(
    path: Path,
    *,
    plan_id: str = "SOFI-BULL-20260803",
    close_date: str = "2026-08-11",
    outcome: str = "T1_HIT",
    option_result_pct=None,
) -> dict:
    row = {
        "schema": "prophet.ledger/v1",
        "id": plan_id,
        "close_date": close_date,
        "outcome": outcome,
        "asof": close_date,
        "option_result_pct": option_result_pct,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, allow_nan=False) + "\n")
    _lifecycle_refresh_ledger_receipt(path)
    return row


def _lifecycle_state(root: Path) -> dict:
    return json.loads((root / "current.json").read_text(encoding="utf-8"))


def _lifecycle_events(root: Path) -> list[dict]:
    state = _lifecycle_state(root)
    pointer = state["lifecycle_head"]
    backwards = []
    while pointer is not None:
        event = option_lifecycle._load_event(root, pointer)
        backwards.append(event)
        pointer = event["previous"]
    backwards.reverse()
    return backwards


def _prepare_enrolled_lifecycle(
    monkeypatch,
    tmp_path: Path,
    *,
    session_date: str = "2026-08-11",
) -> tuple[Path, Path, Path, dict]:
    mark_root = tmp_path / "private-marks"
    lifecycle_root = _lifecycle_private_dir(tmp_path / "private-lifecycle")
    ledger_path = _lifecycle_ledger(tmp_path / "ledger.jsonl")
    day = date.fromisoformat(session_date)
    boundary_at = datetime(
        day.year, day.month, day.day, 14, 0, tzinfo=timezone.utc
    ).isoformat()
    enrollment_at = datetime(
        day.year, day.month, day.day, 14, 5, tzinfo=timezone.utc
    ).isoformat()
    _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at=boundary_at,
        session_date=session_date,
        phase="triggered_pre_t1",
        mid=2.9,
    )
    activated = option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    assert activated["status"] == "activated"
    enrollment_pointer, _row = _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at=enrollment_at,
        session_date=session_date,
        phase="triggered_pre_t1",
        mid=3.0,
    )
    advanced = option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    assert advanced["enrollment_count"] == 1
    return mark_root, lifecycle_root, ledger_path, enrollment_pointer


def test_option_shadow_lifecycle_is_prospective_and_enrolls_once(
    monkeypatch,
    tmp_path,
):
    mark_root = tmp_path / "private-marks"
    lifecycle_root = _lifecycle_private_dir(tmp_path / "private-lifecycle")
    ledger_path = _lifecycle_ledger(tmp_path / "ledger.jsonl")

    boundary_pointer, _ = _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:00:00+00:00",
        session_date="2026-08-11",
        phase="triggered_pre_t1",
        mid=2.9,
    )
    activated = option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    assert activated["status"] == "activated"
    assert _lifecycle_state(lifecycle_root)["enrollments"] == {}

    _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:05:00+00:00",
        session_date="2026-08-11",
        phase="pre_trigger",
        mid=3.0,
    )
    pretrigger = option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    assert pretrigger["enrollment_count"] == 0

    _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:10:00+00:00",
        session_date="2026-08-11",
        phase="triggered_pre_t1",
        available=False,
    )
    stale = option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    assert stale["enrollment_count"] == 0

    first_fresh_pointer, _ = _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:15:00+00:00",
        session_date="2026-08-11",
        phase="triggered_pre_t1",
        mid=3.1,
    )
    enrolled = option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    assert enrolled["enrollment_count"] == 1

    second_fresh_pointer, _ = _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:20:00+00:00",
        session_date="2026-08-11",
        phase="triggered_pre_t1",
        mid=3.2,
    )
    repeated = option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    assert repeated["enrollment_count"] == 0
    state = _lifecycle_state(lifecycle_root)
    assert len(state["enrollments"]) == 1
    latest = state["latest_marks"]["SOFI-BULL-20260803"]
    assert latest["sessions"]["2026-08-11"] == second_fresh_pointer

    events = _lifecycle_events(lifecycle_root)
    assert [event["event_kind"] for event in events] == [
        "activation_boundary",
        "enrollment",
    ]
    assert events[0]["payload"]["mark_boundary"] == boundary_pointer
    enrollment = events[1]
    assert enrollment["payload"]["mark_observation"] == first_fresh_pointer
    assert enrollment["payload"]["plan"]["phase"] == "triggered_pre_t1"
    assert enrollment["payload"]["position_assumed"] is False
    assert enrollment["payload"]["provider_observed_entry"] is False
    assert not any(enrollment["authority"].values())
    assert enrollment["limitations"]["not_trade_pnl"] is True
    assert enrollment["limitations"]["never_populates_option_result_pct"] is True

    assert lifecycle_root.stat().st_mode & 0o777 == 0o700
    for node in lifecycle_root.rglob("*"):
        expected = 0o700 if node.is_dir() else 0o600
        assert node.stat().st_mode & 0o777 == expected


def test_option_shadow_terminal_uses_latest_same_session_mid_without_writing_ledger(
    monkeypatch,
    tmp_path,
):
    mark_root, lifecycle_root, ledger_path, _ = _prepare_enrolled_lifecycle(
        monkeypatch, tmp_path
    )
    latest_pointer, _ = _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:10:00+00:00",
        session_date="2026-08-11",
        phase="triggered_pre_t1",
        mid=3.3,
    )
    source_row = _lifecycle_append_close(ledger_path)
    ledger_before = ledger_path.read_bytes()

    summary = option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    assert summary["terminal_count"] == 1
    assert ledger_path.read_bytes() == ledger_before
    assert source_row["option_result_pct"] is None

    events = _lifecycle_events(lifecycle_root)
    assert [event["event_kind"] for event in events] == [
        "activation_boundary",
        "enrollment",
        "terminal",
    ]
    terminal = events[-1]
    payload = terminal["payload"]
    assert payload["terminal_mark"]["status"] == "available"
    assert payload["terminal_mark"]["mark"]["mark_observation"] == latest_pointer
    assert payload["shadow_return"] == {
        "status": "available",
        "basis": "shadow_mid_to_mid_research_only",
        "shadow_mark_to_mark_return_pct": 10.0,
        "unavailable_reason": None,
        "trade_pnl": False,
    }
    assert payload["provider_observed_exit"] is False
    assert payload["position_assumed"] is False
    assert payload["canonical_close"]["source_option_result_pct_was_null"] is True
    assert not any(terminal["authority"].values())
    assert _lifecycle_state(lifecycle_root)["latest_marks"] == {}

    duplicate = option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    assert duplicate["status"] == "unchanged"
    assert duplicate["terminal_count"] == 0
    assert len(list((lifecycle_root / "events").rglob("posle_*.json"))) == 3


@pytest.mark.parametrize(
    ("scenario", "expected_reason"),
    [
        ("missing_same_session", "NO_SAME_SESSION_ADMITTED_MARK"),
        ("contract_drift", "CONTRACT_DRIFT"),
        ("no_entry", "CANONICAL_NO_ENTRY"),
        ("close_predates", "CANONICAL_CLOSE_PREDATES_ENROLLMENT"),
    ],
)
def test_option_shadow_terminal_unavailable_reasons_are_immutable(
    monkeypatch,
    tmp_path,
    scenario,
    expected_reason,
):
    enrollment_session = "2026-08-12" if scenario == "close_predates" else "2026-08-11"
    mark_root, lifecycle_root, ledger_path, _ = _prepare_enrolled_lifecycle(
        monkeypatch,
        tmp_path,
        session_date=enrollment_session,
    )
    close_date = "2026-08-12" if scenario == "missing_same_session" else "2026-08-11"
    outcome = "NO_ENTRY" if scenario == "no_entry" else "T1_HIT"
    if scenario == "contract_drift":
        _lifecycle_emit_mark(
            monkeypatch,
            mark_root,
            observed_at="2026-08-11T14:10:00+00:00",
            session_date="2026-08-11",
            phase="triggered_pre_t1",
            mid=3.2,
            strike=17.0,
        )
    _lifecycle_append_close(
        ledger_path,
        close_date=close_date,
        outcome=outcome,
    )

    summary = option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    assert summary["terminal_count"] == 1
    terminal = _lifecycle_events(lifecycle_root)[-1]
    assert terminal["event_kind"] == "terminal"
    assert terminal["payload"]["terminal_mark"] == {
        "status": "unavailable",
        "reason": expected_reason,
        "mark": None,
    }
    assert terminal["payload"]["shadow_return"] == {
        "status": "unavailable",
        "basis": "shadow_mid_to_mid_research_only",
        "shadow_mark_to_mark_return_pct": None,
        "unavailable_reason": expected_reason,
        "trade_pnl": False,
    }


def test_option_shadow_lifecycle_refuses_ledger_rewrite_and_option_result_claim(
    monkeypatch,
    tmp_path,
):
    mark_root = tmp_path / "private-marks"
    lifecycle_root = _lifecycle_private_dir(tmp_path / "private-lifecycle")
    ledger_path = _lifecycle_ledger(tmp_path / "ledger.jsonl")
    _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:00:00+00:00",
        session_date="2026-08-11",
        phase="pre_trigger",
    )
    option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    state_before = (lifecycle_root / "current.json").read_bytes()
    ledger_path.write_text("# rewritten ledger prefix\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match its receipt|no longer extends"):
        option_lifecycle.advance_lifecycle(
            lifecycle_root=lifecycle_root,
            mark_root=mark_root,
            ledger_path=ledger_path,
        )
    assert (lifecycle_root / "current.json").read_bytes() == state_before

    other_root = _lifecycle_private_dir(tmp_path / "private-lifecycle-claim")
    claimed_ledger = _lifecycle_ledger(tmp_path / "claimed-ledger.jsonl")
    _lifecycle_append_close(claimed_ledger, option_result_pct=12.3)
    with pytest.raises(ValueError, match="already claims or lacks"):
        option_lifecycle.advance_lifecycle(
            lifecycle_root=other_root,
            mark_root=mark_root,
            ledger_path=claimed_ledger,
        )
    assert not (other_root / "current.json").exists()


def test_option_shadow_lifecycle_refuses_a_non_ancestor_mark_cursor(
    monkeypatch,
    tmp_path,
):
    mark_root = tmp_path / "private-marks"
    lifecycle_root = _lifecycle_private_dir(tmp_path / "private-lifecycle")
    ledger_path = _lifecycle_ledger(tmp_path / "ledger.jsonl")
    _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:00:00+00:00",
        session_date="2026-08-11",
        phase="pre_trigger",
    )
    option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:05:00+00:00",
        session_date="2026-08-11",
        phase="pre_trigger",
    )
    state = _lifecycle_state(lifecycle_root)
    fake_id = "pom_obs_" + "a" * 64
    state["mark_cursor"] = {
        "schema": prophet_marks.EVIDENCE_POINTER_SCHEMA,
        "observation_id": fake_id,
        "key": f"observations/2026-08-11/{fake_id}.json",
        "sha256": "b" * 64,
        "bytes": 1,
    }
    state["state_id"] = option_lifecycle._state_identity(state)
    forged_state = option_lifecycle._canonical_json_bytes(state)
    (lifecycle_root / "current.json").write_bytes(forged_state)
    (lifecycle_root / "current.json").chmod(0o600)

    with pytest.raises(ValueError, match="missing|not an ancestor"):
        option_lifecycle.advance_lifecycle(
            lifecycle_root=lifecycle_root,
            mark_root=mark_root,
            ledger_path=ledger_path,
        )
    assert (lifecycle_root / "current.json").read_bytes() == forged_state


def test_option_shadow_lifecycle_runtime_schema_failure_precedes_event_write(
    monkeypatch,
    tmp_path,
):
    mark_root = tmp_path / "private-marks"
    lifecycle_root = _lifecycle_private_dir(tmp_path / "private-lifecycle")
    ledger_path = _lifecycle_ledger(tmp_path / "ledger.jsonl")
    _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:00:00+00:00",
        session_date="2026-08-11",
        phase="triggered_pre_t1",
    )
    repo = Path(__file__).resolve().parents[1]
    schema = json.loads(
        (
            repo
            / "contracts/options/prophet.option_shadow_lifecycle_event.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    schema["properties"]["event_kind"] = {"const": "never_valid"}
    bad_schema = tmp_path / "bad-lifecycle-schema.json"
    bad_schema.write_text(json.dumps(schema), encoding="utf-8")
    monkeypatch.setenv(
        "PROPHET_OPTION_SHADOW_LIFECYCLE_SCHEMA_PATH",
        str(bad_schema),
    )

    with pytest.raises(ValueError, match="schema check failed"):
        option_lifecycle.advance_lifecycle(
            lifecycle_root=lifecycle_root,
            mark_root=mark_root,
            ledger_path=ledger_path,
        )
    assert not (lifecycle_root / "current.json").exists()
    assert not (lifecycle_root / "events").exists()


def test_option_shadow_lifecycle_crash_retry_adopts_identical_event(
    monkeypatch,
    tmp_path,
):
    mark_root = tmp_path / "private-marks"
    lifecycle_root = _lifecycle_private_dir(tmp_path / "private-lifecycle")
    ledger_path = _lifecycle_ledger(tmp_path / "ledger.jsonl")
    _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:00:00+00:00",
        session_date="2026-08-11",
        phase="triggered_pre_t1",
    )
    original_write_state = option_lifecycle._write_state

    def fail_state(*_args, **_kwargs):
        raise OSError("injected state swap failure")

    monkeypatch.setattr(option_lifecycle, "_write_state", fail_state)
    with pytest.raises(OSError, match="injected"):
        option_lifecycle.advance_lifecycle(
            lifecycle_root=lifecycle_root,
            mark_root=mark_root,
            ledger_path=ledger_path,
        )
    orphan_files = list((lifecycle_root / "events").rglob("posle_*.json"))
    assert len(orphan_files) == 1
    original_body = orphan_files[0].read_bytes()
    original_event = json.loads(original_body)
    assert not (lifecycle_root / "current.json").exists()

    # The source head may advance before the retry. The durable activation marker
    # freezes the original boundary, so retry still adopts exactly the orphaned event.
    _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:05:00+00:00",
        session_date="2026-08-11",
        phase="pre_trigger",
    )

    monkeypatch.setattr(option_lifecycle, "_write_state", original_write_state)
    recovered = option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
    )
    assert recovered["status"] == "activated"
    event_files = list((lifecycle_root / "events").rglob("posle_*.json"))
    assert len(event_files) == 1
    assert event_files[0].read_bytes() == original_body
    assert recovered["mark_cursor"] == original_event["payload"]["mark_boundary"][
        "observation_id"
    ]
    option_lifecycle._validate_event_chain(
        lifecycle_root,
        _lifecycle_state(lifecycle_root),
    )


def test_option_shadow_sync_installs_exact_current_main_receipt_before_activation(
    monkeypatch,
    tmp_path,
):
    lifecycle_root = _lifecycle_private_dir(tmp_path / "private-lifecycle")
    source_ledger = _lifecycle_ledger(tmp_path / "source-ledger" / "ledger.jsonl")
    _lifecycle_append_close(source_ledger, plan_id="ALREADY-CLOSED")
    source_body = source_ledger.read_bytes()
    source_commit = "c" * 40
    monkeypatch.setattr(
        option_lifecycle,
        "_resolve_current_main_commit",
        lambda: source_commit,
    )
    monkeypatch.setattr(
        option_lifecycle,
        "_download_current_main_ledger",
        lambda commit: source_body if commit == source_commit else b"",
    )

    synced = option_lifecycle.sync_canonical_ledger(
        lifecycle_root=lifecycle_root,
    )
    ledger_path = lifecycle_root / "canonical_ledger" / "ledger.jsonl"
    receipt_path = lifecycle_root / "canonical_ledger" / "receipt.json"
    assert synced == {
        "status": "installed",
        "source_commit": source_commit,
        "sha256": hashlib.sha256(source_body).hexdigest(),
        "row_count": 1,
    }
    assert ledger_path.read_bytes() == source_body
    assert ledger_path.stat().st_mode & 0o777 == 0o600
    assert receipt_path.stat().st_mode & 0o777 == 0o600
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["source_commit"] == source_commit
    assert receipt["source_path"] == "data/prophet/ledger.jsonl"
    assert receipt["source_ref"] == "refs/heads/main"

    mark_root = tmp_path / "private-marks"
    _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:00:00+00:00",
        session_date="2026-08-11",
        phase="pre_trigger",
    )
    activated = option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
    )
    assert activated["status"] == "activated"
    activation = _lifecycle_events(lifecycle_root)[0]
    assert activation["payload"]["ledger_boundary"] == receipt


def test_option_shadow_sync_refuses_current_main_ledger_rewrite_without_replacing_snapshot(
    monkeypatch,
    tmp_path,
):
    lifecycle_root = _lifecycle_private_dir(tmp_path / "private-lifecycle")
    source_ledger = _lifecycle_ledger(tmp_path / "source-ledger" / "ledger.jsonl")
    _lifecycle_append_close(source_ledger, plan_id="ALREADY-CLOSED")
    original_body = source_ledger.read_bytes()
    source_commit = "d" * 40
    monkeypatch.setattr(
        option_lifecycle,
        "_resolve_current_main_commit",
        lambda: source_commit,
    )
    monkeypatch.setattr(
        option_lifecycle,
        "_download_current_main_ledger",
        lambda _commit: original_body,
    )
    option_lifecycle.sync_canonical_ledger(lifecycle_root=lifecycle_root)

    mark_root = tmp_path / "private-marks"
    _lifecycle_emit_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:00:00+00:00",
        session_date="2026-08-11",
        phase="pre_trigger",
    )
    option_lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
    )
    ledger_path = lifecycle_root / "canonical_ledger" / "ledger.jsonl"
    receipt_path = lifecycle_root / "canonical_ledger" / "receipt.json"
    receipt_before = receipt_path.read_bytes()

    rewritten = original_body.replace(b'"outcome": "T1_HIT"', b'"outcome": "EXPIRED"')
    assert rewritten != original_body
    monkeypatch.setattr(
        option_lifecycle,
        "_resolve_current_main_commit",
        lambda: "e" * 40,
    )
    monkeypatch.setattr(
        option_lifecycle,
        "_download_current_main_ledger",
        lambda _commit: rewritten,
    )
    with pytest.raises(ValueError, match="no longer extends"):
        option_lifecycle.sync_canonical_ledger(lifecycle_root=lifecycle_root)
    assert ledger_path.read_bytes() == original_body
    assert receipt_path.read_bytes() == receipt_before


def test_option_shadow_cli_never_advances_when_current_main_sync_fails(monkeypatch):
    advanced = []

    def fail_sync():
        raise ValueError("injected current-main outage")

    monkeypatch.setattr(option_lifecycle, "sync_canonical_ledger", fail_sync)
    monkeypatch.setattr(
        option_lifecycle,
        "advance_lifecycle",
        lambda: advanced.append(True),
    )
    assert (
        option_lifecycle.main(["--sync-current-main-ledger", "--advance"])
        == 1
    )
    assert advanced == []
    assert option_lifecycle.main(["--advance"]) == 1
    assert advanced == []


def test_option_shadow_lifecycle_has_no_public_writer_or_ledger_mutator():
    source = Path(option_lifecycle.__file__).read_text(encoding="utf-8")
    assert "put_object(" not in source
    assert "upload_file(" not in source
    assert "_append_ledger_row" not in source
    assert "option_result_pct\"] =" not in source
    assert option_lifecycle._limitations_block()["public_redistribution"] is False
    assert not any(option_lifecycle._authority_block().values())
