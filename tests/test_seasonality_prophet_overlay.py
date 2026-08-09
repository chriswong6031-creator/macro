"""W6 — the seasonality → Prophet overlay bridge.

The point of this suite is the hard invariant: attaching seasonality context to
a frozen Prophet candidate list must leave every plan byte-identical.  Everything
else here guards the ways that invariant is usually lost — a default overlay
standing in for a missing state, a calendar construction capping confidence, a
join that guesses an identity, or a wall clock making the output irreproducible.
"""
from __future__ import annotations

import copy
import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest

from engine.options_structure import ProphetTradePlan, validate_trade_plan
from engine.seasonality import prophet_bridge as bridge
from engine.seasonality.contracts import (
    NEURALWEB_STATE_SCHEMA,
    PROPHET_OVERLAY_SCHEMA,
    ContractError,
    build_neuralweb_state,
    validate_prophet_overlay,
)

ASOF = "2026-08-03T12:00:00Z"
PLAN_ASOF = "2026-08-03"
_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64


# ---------------------------------------------------------------------------
# fixtures — real shapes, not invented ones
# ---------------------------------------------------------------------------


def _plan(
    *,
    plan_id: str = "BIO-BULL-XBI-2026-08-03",
    asset: str = "XBI",
    horizon_days: int = 30,
    source_engines: list[str] | None = None,
    direction: str = "BULL",
) -> ProphetTradePlan:
    """A realistic, contract-valid ``prophet.trade_plan/v1`` envelope."""
    plan = ProphetTradePlan(
        id=plan_id,
        asof=PLAN_ASOF,
        asset=asset,
        direction=direction,
        thesis="Base breakout with expanding participation; manage against the shelf.",
        source_engines=list(source_engines or ["neural_web"]),
        trigger=94.25,
        entry=94.60,
        invalidation=88.10,
        targets=[103.5, 112.0],
        horizon_days=horizon_days,
        min_hold_days=5,
        tranche=1,
        option_contract={
            "right": "C",
            "strike": 95.0,
            "expiry": "2026-09-18",
            "entry_premium": 4.35,
        },
        management_ref=f"prophet/state/{plan_id}.json",
    )
    if plan_id:
        # The fixture must be a REAL plan, not a shape this suite invented.
        assert validate_trade_plan(dataclasses.asdict(plan)) == []
    return plan


def _state(
    *,
    symbol: str = "XBI",
    horizon_td: int = 20,
    occurrence_end_date: str = "2026-08-31",
    abstain: bool = False,
    available_at: str = "2026-08-03T00:00:00Z",
    expires_at: str = "2026-08-04T00:00:00Z",
    asof: str = PLAN_ASOF,
) -> dict:
    """A ``neuralweb.biopharma_seasonality_state.v1`` in the shape state.py emits."""
    return build_neuralweb_state(
        artifact_id="biopharma-seasonality-state",
        entity={"type": "etf", "id": f"ticker:{symbol}", "ticker": symbol},
        asof=asof,
        available_at=available_at,
        expires_at=expires_at,
        clock={
            "type": "calendar",
            "phase": "inside_window",
            "pattern_id": f"cal:{symbol}:200-243",
            "start_doy": 200,
            "end_doy": 243,
            "occurrence_end_date": occurrence_end_date,
            "days_to_window_end": 28,
            "window_source": "default",
        },
        forecast={
            "target": "excess_return_gt_0",
            "horizon_td": horizon_td,
            "p": 0.62,
            "p_baseline": 0.51,
            "edge": 0.11,
            "ci90": [0.44, 0.78],
        },
        evidence={"n_independent": 18, "n_issuers": 1, "n_date_clusters": 18, "live_n": 3},
        uncertainty={"abstain": abstain, "flags": ["forward_sample_thin"]},
        provenance={
            "model_version": "seasonality-state/v1",
            "pattern_spec_hash": _HASH_A,
            "data_snapshot": _HASH_B,
        },
        tier="shadow",
    )


#: The date ``RECYCLED`` stopped meaning one company and started meaning another.
RECYCLE_DATE = "2026-08-02"


def _resolver(symbol: str, asof: str) -> str:
    """A stand-in for the reviewed PIT identity plane.

    A real plane returns a PERMANENT identity that is stable across dates —
    that is what makes it an identity plane rather than an echo of the ticker.
    It is asof-sensitive only where the ticker itself changed meaning, so
    ``RECYCLED`` resolves to a different company either side of
    :data:`RECYCLE_DATE`.  A resolver keyed ``f"cid:{symbol}:{asof}"`` would be
    neither: it would make every join require two exactly-equal asofs and would
    still be a bijection of the ticker.
    """
    if symbol == "RECYCLED":
        return "cid:RECYCLED-B" if asof >= RECYCLE_DATE else "cid:RECYCLED-A"
    return f"cid:{symbol}"


def _run(plans, states, *, asof=ASOF, resolve_identity=_resolver):
    return bridge.build_overlays_for_plans(
        plans, states, asof=asof, resolve_identity=resolve_identity
    )


def _skip_reasons(result) -> list[str]:
    return [entry["reason"] for entry in result["skipped"]]


# ---------------------------------------------------------------------------
# THE HARD INVARIANT
# ---------------------------------------------------------------------------


def test_overlay_cannot_change_any_plan_number():
    """With and without the overlay set, the frozen plan list is byte-identical."""
    plans = [
        _plan(plan_id="BIO-BULL-XBI-2026-08-03", asset="XBI"),
        _plan(plan_id="BIO-BEAR-IBB-2026-08-03", asset="IBB", direction="BEAR", horizon_days=45),
        _plan(plan_id="BIO-BULL-XLV-2026-08-03", asset="XLV", horizon_days=20),
    ]
    states = [_state(symbol="XBI"), _state(symbol="IBB"), _state(symbol="XLV")]

    before = json.dumps([dataclasses.asdict(plan) for plan in plans], sort_keys=True)

    result = _run(plans, states)

    after = json.dumps([dataclasses.asdict(plan) for plan in plans], sort_keys=True)
    assert after == before

    # Step 5 — without this the four steps above pass for a no-op function.
    assert result["overlays"], "the invariant test must exercise a non-empty overlay set"
    assert len(result["overlays"]) == 3
    assert [overlay["plan_id"] for overlay in result["overlays"]] == [
        "BIO-BULL-XBI-2026-08-03",
        "BIO-BEAR-IBB-2026-08-03",
        "BIO-BULL-XLV-2026-08-03",
    ]


def test_result_carries_no_plan_object_and_no_plan_geometry():
    plans = [_plan()]
    result = _run(plans, [_state()])
    blob = json.dumps(result, sort_keys=True)

    for leaked in ("thesis", "trigger", "invalidation", "targets", "option_contract", "94.25", "88.1"):
        assert leaked not in blob
    assert result["overlays"][0]["plan_id"] == "BIO-BULL-XBI-2026-08-03"
    assert not any(isinstance(item, ProphetTradePlan) for item in result["overlays"])


def test_inputs_are_not_reordered_or_consumed():
    plans = [_plan(plan_id="P-A", asset="XBI"), _plan(plan_id="P-B", asset="IBB")]
    states = [_state(symbol="IBB"), _state(symbol="XBI")]
    plans_snapshot = [dataclasses.asdict(plan) for plan in plans]
    states_snapshot = copy.deepcopy(states)

    result = _run(plans, states)

    assert [dataclasses.asdict(plan) for plan in plans] == plans_snapshot
    assert states == states_snapshot
    # Overlay order follows the frozen plan order, never the state order.
    assert [overlay["plan_id"] for overlay in result["overlays"]] == ["P-A", "P-B"]


# ---------------------------------------------------------------------------
# the default is NO overlays
# ---------------------------------------------------------------------------


def test_default_resolve_identity_emits_no_overlays():
    result = bridge.build_overlays_for_plans([_plan()], [_state()], asof=ASOF)
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_IDENTITY_UNRESOLVED]
    assert result["counts"]["overlays"] == 0


def test_explicit_none_resolver_is_the_same_as_the_default():
    result = bridge.build_overlays_for_plans(
        [_plan()], [_state()], asof=ASOF, resolve_identity=None
    )
    assert result["overlays"] == []
    assert bridge.no_identity("XBI", PLAN_ASOF) is None


# ---------------------------------------------------------------------------
# absence / expiry / invalidity == no overlay, never a default
# ---------------------------------------------------------------------------


def test_expired_state_yields_no_overlay_and_a_named_skip():
    state = _state(available_at="2026-08-01T00:00:00Z", expires_at="2026-08-02T00:00:00Z")
    result = _run([_plan()], [state])
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_STATE_EXPIRED, bridge.SKIP_NO_MATCHING_STATE]
    assert result["skipped"][0]["state_ref"].startswith("biopharma-seasonality-state|ticker:XBI|")


def test_contract_invalid_state_yields_no_overlay_and_a_named_skip():
    broken = _state()
    broken["authority"]["may_rank"] = True  # forbidden write capability
    result = _run([_plan()], [broken])
    assert result["overlays"] == []
    assert _skip_reasons(result) == [
        bridge.SKIP_STATE_CONTRACT_INVALID,
        bridge.SKIP_NO_MATCHING_STATE,
    ]
    assert "may_rank" in result["skipped"][0]["detail"]


def test_non_object_state_is_skipped_not_crashed():
    result = _run([_plan()], ["not-a-state"])
    assert result["overlays"] == []
    assert _skip_reasons(result)[0] == bridge.SKIP_STATE_CONTRACT_INVALID


def test_abstaining_state_yields_no_overlay_and_a_named_skip():
    result = _run([_plan()], [_state(abstain=True)])
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_STATE_ABSTAINING, bridge.SKIP_NO_MATCHING_STATE]


def test_state_available_after_asof_is_look_ahead_and_is_skipped():
    state = _state(available_at="2026-08-03T18:00:00Z", expires_at="2026-08-04T18:00:00Z")
    result = _run([_plan()], [state])
    assert result["overlays"] == []
    assert _skip_reasons(result)[0] == bridge.SKIP_STATE_NOT_YET_AVAILABLE


def test_absent_state_is_not_a_neutral_overlay():
    result = _run([_plan()], [])
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_NO_MATCHING_STATE]
    assert result["counts"]["by_action"] == {"ATTEND": 0, "NARRATE": 0, "NONE": 0}


def test_plan_without_id_cannot_be_keyed():
    result = _run([_plan(plan_id="")], [_state()])
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_PLAN_MISSING_ID]


def test_unreadable_plan_asof_refuses_to_guess_the_join_key():
    plan = dataclasses.asdict(_plan())
    plan["asof"] = "sometime in August"
    result = _run([plan], [_state()])
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_PLAN_ASOF_UNREADABLE]


def test_ambiguous_identity_match_refuses_to_pick_one():
    twin = _state(symbol="XBI", occurrence_end_date="2026-09-30")
    result = _run([_plan()], [_state(symbol="XBI"), twin])
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_AMBIGUOUS_STATE_MATCH]
    assert "2 eligible states" in result["skipped"][0]["detail"]


def test_duplicate_plan_id_is_refused_rather_than_fanned_out():
    """An overlay is keyed to plan_id, so a repeat would be a 1:N join for a consumer."""
    plans = [_plan(plan_id="P-DUP", asset="XBI"), _plan(plan_id="P-DUP", asset="XBI")]
    result = _run(plans, [_state(symbol="XBI")])
    assert len(result["overlays"]) == 1
    assert [overlay["plan_id"] for overlay in result["overlays"]] == ["P-DUP"]
    assert _skip_reasons(result) == [bridge.SKIP_PLAN_DUPLICATE_ID]
    assert result["counts"]["overlays"] == 1


@pytest.mark.parametrize("horizon_days", [None, 0, -5, 30.0, "30", True])
def test_unreadable_plan_horizon_is_skipped_not_scored_as_a_scale_mismatch(horizon_days):
    """A horizon that cannot be read is not the same claim as a horizon that mismatched."""
    plan = dataclasses.asdict(_plan())
    plan["horizon_days"] = horizon_days
    result = _run([plan], [_state()])
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_PLAN_HORIZON_UNREADABLE]


@pytest.mark.parametrize("engines", [None, 3, {"a": 1}])
def test_unreadable_source_engines_is_skipped_rather_than_read_as_no_overlap(engines):
    plan = dataclasses.asdict(_plan())
    plan["source_engines"] = engines
    result = _run([plan], [_state()])
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_PLAN_SOURCE_ENGINES_UNREADABLE]


@pytest.mark.parametrize(
    "engines",
    [
        {"neural_web", "stock_seasonality"},              # a set
        frozenset({"neural_web", "stock_seasonality"}),   # a frozenset
        ("neural_web", "stock_seasonality"),              # a tuple
        "stock_seasonality",                              # a bare string
    ],
)
def test_double_count_suppression_survives_an_unusual_source_engines_container(engines):
    """``validate_trade_plan`` only asks that source_engines be non-empty.

    A set or a bare string is therefore a contract-valid plan, and reading it as
    "no engines declared" would fail OPEN — the seasonality-bearing plan would
    get the seasonality overlay the suppression exists to withhold.
    """
    plan = dataclasses.asdict(_plan())
    plan["source_engines"] = engines
    result = _run([plan], [_state()])
    assert len(result["overlays"]) == 1
    overlay = result["overlays"][0]
    assert overlay["overlap_with_existing_features"] is True
    assert overlay["action"] == bridge.ACTION_NONE
    assert overlay["reason_codes"] == [bridge.REASON_ALREADY_IN_PLAN_FEATURES]


# ---------------------------------------------------------------------------
# a missing FIELD on a valid state is also an absence, not a default
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("occurrence_end", [None, "", "August 31st", "2026-13-01", 20260831])
def test_unreadable_occurrence_end_is_skipped_not_narrated(occurrence_end):
    """``clock.occurrence_end_date`` is not required by the state contract.

    Reading its absence as ``event_inside_plan_horizon=False`` would emit a
    NARRATE overlay whose reason code claims the window closes OUTSIDE the plan
    horizon — a display-tier claim about a date nobody has.  A producer key
    rename would silently downgrade every ATTEND with no skip entry at all.
    """
    state = _state()
    if occurrence_end is None:
        del state["clock"]["occurrence_end_date"]
    else:
        state["clock"]["occurrence_end_date"] = occurrence_end

    # The same state WITH the field is an ATTEND, so the gate is the field.
    assert _run([_plan()], [_state()])["overlays"][0]["action"] == bridge.ACTION_ATTEND

    result = _run([_plan()], [state])
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_STATE_OCCURRENCE_END_UNREADABLE]
    assert result["counts"]["by_action"] == {"ATTEND": 0, "NARRATE": 0, "NONE": 0}


def test_unreadable_state_asof_is_skipped_because_identity_resolves_at_it():
    state = _state()
    state["asof"] = "whenever"
    result = _run([_plan()], [state])
    assert result["overlays"] == []
    assert _skip_reasons(result) == [
        bridge.SKIP_STATE_ASOF_UNREADABLE,
        bridge.SKIP_NO_MATCHING_STATE,
    ]


# ---------------------------------------------------------------------------
# the identity join is a PIT plane, never a ticker string
# ---------------------------------------------------------------------------


def test_a_ticker_rename_still_joins_because_the_join_is_on_identity():
    """OLDCO renamed to NEWCO: different tickers, one company, one overlay.

    Without this, a join written as ``state.symbol == plan.asset`` passes the
    whole suite — every other resolver here is a bijection of the ticker.
    """
    def rename_resolver(symbol: str, asof: str) -> str:
        return "cid:ACME" if symbol in {"OLDCO", "NEWCO"} else f"cid:{symbol}"

    result = _run(
        [_plan(plan_id="P-RENAME", asset="NEWCO")],
        [_state(symbol="OLDCO")],
        resolve_identity=rename_resolver,
    )
    assert _skip_reasons(result) == []
    assert len(result["overlays"]) == 1
    assert result["overlays"][0]["plan_id"] == "P-RENAME"
    assert result["overlays"][0]["seasonality_state_ref"].startswith(
        "biopharma-seasonality-state|ticker:OLDCO|"
    )


def test_a_reused_ticker_does_not_inherit_its_predecessors_context():
    """One ticker, two companies across the two asofs -> no join, no overlay.

    The state was measured on 2026-08-01, while ``ZZZZ`` still meant the
    predecessor; the plan was frozen on 2026-08-03, after the reuse.  Resolving
    BOTH sides at the plan's asof would hide this and print the predecessor's
    seasonality on the successor's plan.
    """
    def zombie_resolver(symbol: str, asof: str) -> str:
        if symbol != "ZZZZ":
            return f"cid:{symbol}:{asof}"
        return "cid:SUCCESSOR" if asof >= "2026-08-02" else "cid:PREDECESSOR"

    stale_state = _state(
        symbol="ZZZZ", asof="2026-08-01", available_at="2026-08-01T00:00:00Z"
    )
    result = _run(
        [_plan(plan_id="P-ZOMBIE", asset="ZZZZ")],
        [stale_state],
        resolve_identity=zombie_resolver,
    )
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_NO_MATCHING_STATE]

    # ...and the SAME state measured after the reuse does join, so the skip
    # above is the identity change and not the dates.
    fresh_state = _state(
        symbol="ZZZZ", asof="2026-08-03", available_at="2026-08-03T00:00:00Z"
    )
    joined = _run(
        [_plan(plan_id="P-ZOMBIE", asset="ZZZZ")],
        [fresh_state],
        resolve_identity=zombie_resolver,
    )
    assert len(joined["overlays"]) == 1


def test_plan_identity_is_resolved_at_the_plan_asof_not_the_run_asof():
    """``RECYCLED`` means company A on the plan's date and company B on the run's.

    Resolving the plan side at the RUN asof would ask the identity plane about a
    company the plan never referred to, and the (correct) state would stop
    joining.
    """
    plan = dataclasses.asdict(_plan(plan_id="P-ERA", asset="RECYCLED"))
    plan["asof"] = "2026-08-01"  # before RECYCLE_DATE -> company A
    state = _state(
        symbol="RECYCLED",
        asof="2026-08-01",
        available_at="2026-08-01T00:00:00Z",
        expires_at="2026-08-06T00:00:00Z",
        occurrence_end_date="2026-08-25",
    )
    assert _resolver("RECYCLED", "2026-08-01") != _resolver("RECYCLED", "2026-08-05")

    result = _run([plan], [state], asof="2026-08-05T12:00:00Z")  # run in company B's era
    assert _skip_reasons(result) == []
    assert len(result["overlays"]) == 1
    assert result["overlays"][0]["plan_id"] == "P-ERA"


def test_identity_is_resolved_once_per_symbol_and_asof():
    """A reviewed PIT plane is an IO lookup, not a dictionary."""
    calls: list[tuple[str, str]] = []

    def counting_resolver(symbol: str, asof: str) -> str:
        calls.append((symbol, asof))
        return f"cid:{symbol}:{asof}"

    plans = [_plan(plan_id=f"P-{i}", asset="XBI") for i in range(4)]
    states = [_state(symbol=name) for name in ("XBI", "IBB", "XLV")]
    _run(plans, states, resolve_identity=counting_resolver)

    assert len(calls) == len(set(calls)), "the identity plane was asked the same question twice"
    assert set(calls) == {(name, PLAN_ASOF) for name in ("XBI", "IBB", "XLV")}


# ---------------------------------------------------------------------------
# point-in-time: the plan's own asof, not the batch's
# ---------------------------------------------------------------------------


def test_a_state_born_after_the_plan_is_look_ahead_even_when_the_run_is_later():
    """Screening only at the batch asof lets a state colour a plan that predates it."""
    plan = _plan()  # asof 2026-08-03
    late_state = _state(
        asof="2026-08-04",
        available_at="2026-08-04T18:00:00Z",
        expires_at="2026-08-06T18:00:00Z",
    )
    result = _run([plan], [late_state], asof="2026-08-05T12:00:00Z")
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_STATE_NOT_AVAILABLE_AT_PLAN_ASOF]
    assert result["counts"]["states_eligible"] == 1, "it IS eligible at the run asof"


def test_a_plan_stamped_after_the_run_asof_is_refused():
    plan = dataclasses.asdict(_plan())
    plan["asof"] = "2026-09-01"
    result = _run([plan], [_state()])
    assert result["overlays"] == []
    assert _skip_reasons(result) == [bridge.SKIP_PLAN_ASOF_AFTER_ASOF]


def test_the_event_window_is_measured_from_the_plan_asof_not_the_run_asof():
    """Plan frozen weeks before the run; the window must be read from the plan.

    Measuring from the run asof would turn this NARRATE into a fabricated
    ATTEND — a display-tier attention marker built from a date the plan never
    saw.
    """
    plan = dataclasses.asdict(_plan(horizon_days=30))
    plan["asof"] = "2026-07-01"  # window [2026-07-01, 2026-07-31]
    state = _state(
        asof="2026-07-01",
        occurrence_end_date="2026-08-31",  # outside the PLAN horizon, inside a run-anchored one
        available_at="2026-06-01T00:00:00Z",
        expires_at="2026-09-01T00:00:00Z",
        horizon_td=20,
    )
    result = _run([plan], [state], asof="2026-08-31T12:00:00Z")
    overlay = result["overlays"][0]
    assert overlay["event_inside_plan_horizon"] is False
    assert overlay["action"] == bridge.ACTION_NARRATE
    assert overlay["plan_asof"] == "2026-07-01"
    assert overlay["asof"] == "2026-08-31T12:00:00Z"
    assert overlay["plan_asof"] != overlay["asof"]


def test_an_offset_bearing_plan_asof_normalises_to_one_utc_date():
    """A bare date and the same instant with an offset must not split the join.

    ``_parse_date_or_none`` would slice ``[:10]`` and take the offset-LOCAL day
    while every other moment in this module is UTC, so an evening timestamp
    would shift the horizon window a whole day and mint a second identity key
    for one plan date.
    """
    seen: list[str] = []

    def recording_resolver(symbol: str, asof: str) -> str:
        seen.append(asof)
        return f"cid:{symbol}"

    plan = dataclasses.asdict(_plan())
    plan["asof"] = "2026-08-03T20:30:00-04:00"  # = 2026-08-04T00:30Z
    state = _state(asof="2026-08-04", available_at="2026-08-04T00:00:00Z",
                   expires_at="2026-08-05T00:00:00Z")
    result = _run([plan], [state], asof="2026-08-04T12:00:00Z",
                  resolve_identity=recording_resolver)

    assert len(result["overlays"]) == 1
    assert result["overlays"][0]["plan_asof"] == "2026-08-04"
    assert set(seen) == {"2026-08-04"}, "the identity plane must see one canonical date"


# ---------------------------------------------------------------------------
# the three boolean rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "plan_days, state_td, expected",
    [
        (30, 20, True),      # ratio 0.67
        (30, 15, True),      # ratio 0.50 -> the closed lower bound
        (30, 14, False),     # ratio 0.47 -> just outside it
        (30, 60, True),      # ratio 2.00 -> the closed upper bound
        (30, 61, False),     # ratio 2.03 -> just outside it
        (30, 200, False),    # a whole different time scale
        (45, 60, True),      # ratio 1.33
        (45, 15, False),     # ratio 0.33
        (None, 20, False),   # unknown horizon is never a match
        (30, None, False),
        (0, 20, False),
        (30, -5, False),
        (True, 20, False),   # bool is not an int here
    ],
)
def test_horizon_match_rule(plan_days, state_td, expected):
    assert bridge.horizon_match(plan_days, state_td) is expected


def test_horizon_match_band_is_symmetric_in_log_space():
    """Half the plan horizon and twice it are both matches; the band is [0.5x, 2x]."""
    for plan_days in (10, 30, 90, 200):  # even, so plan_days // 2 is exactly 0.5x
        assert bridge.horizon_match(plan_days, plan_days) is True
        assert bridge.horizon_match(plan_days, plan_days // 2) is True
        assert bridge.horizon_match(plan_days, plan_days * 2) is True
        assert bridge.horizon_match(plan_days, plan_days * 2 + 1) is False
    # No unit conversion is applied: the ratio is state_td / plan_days exactly.
    assert bridge.horizon_match(30, 15) is True and bridge.horizon_match(30, 14) is False
    assert bridge.horizon_match(30, 60) is True and bridge.horizon_match(30, 61) is False


def test_the_producer_really_emits_horizon_td_in_calendar_days():
    """Pin the PREMISE the band rests on, not just the band.

    ``horizon_match`` compares ``forecast.horizon_td`` to ``plan.horizon_days``
    raw, which is only correct because the sole producer of
    ``neuralweb.biopharma_seasonality_state.v1`` emits ``horizon_td`` as a
    difference of two ``datetime.date`` objects — i.e. CALENDAR days, despite
    the ``_td`` name.  An earlier version of the bridge asserted the opposite in
    a comment and applied a 252/365 conversion, which skewed the band to
    ``[0.345, 1.38]``.  If the producer ever switches to true trading days this
    test fails first, and the bridge must be revisited with it.
    """
    from engine.seasonality import state as season_state

    source = Path(season_state.__file__).read_text(encoding="utf-8")
    assert "horizon_td = max(1, (end_date - asof_date).days)" in source, (
        "the producer's horizon_td unit changed; engine/seasonality/prophet_bridge.py "
        "compares it to plan.horizon_days without conversion"
    )
    # date - date is a calendar-day timedelta, and nothing else.
    assert (date(2026, 8, 31) - date(2026, 8, 3)).days == 28


@pytest.mark.parametrize(
    "occurrence_end, expected",
    [
        ("2026-08-31", True),    # inside [2026-08-03, 2026-09-02]
        ("2026-08-03", True),    # closed lower bound
        ("2026-09-02", True),    # closed upper bound
        ("2026-09-03", False),   # one day past the horizon
        ("2026-08-02", False),   # already closed before the plan
        (None, False),           # unknown date is never inside
    ],
)
def test_event_inside_plan_horizon_rule(occurrence_end, expected):
    plan_asof = date(2026, 8, 3)
    end = date.fromisoformat(occurrence_end) if occurrence_end else None
    assert bridge.event_inside_plan_horizon(plan_asof, 30, end) is expected


def test_event_inside_plan_horizon_needs_a_plan_asof_and_horizon():
    assert bridge.event_inside_plan_horizon(None, 30, date(2026, 8, 31)) is False
    assert bridge.event_inside_plan_horizon(date(2026, 8, 3), None, date(2026, 8, 31)) is False


@pytest.mark.parametrize(
    "engines, expected",
    [
        (["neural_web"], False),
        (["neural_web", "stock_seasonality"], True),
        (["Factor-Seasonality"], True),          # normalised
        ([" seasonality_shadow "], True),
        ([], False),
        ([None, 3], False),                       # non-strings ignored, never crash
    ],
)
def test_overlap_with_existing_features_rule(engines, expected):
    assert bridge.overlap_with_existing_features(engines) is expected


def test_booleans_are_real_and_reach_the_emitted_overlay():
    result = _run([_plan(horizon_days=30)], [_state(horizon_td=20, occurrence_end_date="2026-08-31")])
    overlay = result["overlays"][0]
    assert overlay["horizon_match"] is True
    assert overlay["event_inside_plan_horizon"] is True
    assert overlay["overlap_with_existing_features"] is False
    assert overlay["action"] == bridge.ACTION_ATTEND

    outside = _run([_plan(horizon_days=30)], [_state(horizon_td=20, occurrence_end_date="2026-11-30")])
    assert outside["overlays"][0]["event_inside_plan_horizon"] is False
    assert outside["overlays"][0]["action"] == bridge.ACTION_NARRATE

    mismatched = _run([_plan(horizon_days=30)], [_state(horizon_td=200)])
    assert mismatched["overlays"][0]["horizon_match"] is False
    assert mismatched["overlays"][0]["action"] == bridge.ACTION_NONE

    overlapping = _run(
        [_plan(horizon_days=30, source_engines=["neural_web", "stock_seasonality"])],
        [_state(horizon_td=20)],
    )
    assert overlapping["overlays"][0]["overlap_with_existing_features"] is True
    assert overlapping["overlays"][0]["action"] == bridge.ACTION_NONE
    assert overlapping["overlays"][0]["reason_codes"] == [bridge.REASON_ALREADY_IN_PLAN_FEATURES]


# ---------------------------------------------------------------------------
# CAP_CONFIDENCE is unreachable — DNR:KILL-CALENDAR-GATED-RISK
# ---------------------------------------------------------------------------


def test_cap_confidence_is_not_in_the_action_codomain():
    assert "CAP_CONFIDENCE" not in bridge.ALLOWED_ACTIONS
    assert "CAP_CONFIDENCE" in bridge.FORBIDDEN_ACTIONS


def test_no_boolean_combination_reaches_cap_confidence():
    seen = set()
    for matched_horizon in (True, False):
        for event_inside in (True, False):
            for overlaps in (True, False):
                action, reasons = bridge.decide_action(
                    matched_horizon=matched_horizon,
                    event_inside=event_inside,
                    overlaps=overlaps,
                )
                assert action in bridge.ALLOWED_ACTIONS
                assert action != "CAP_CONFIDENCE"
                assert reasons and all(isinstance(code, str) and code for code in reasons)
                seen.add(action)
    assert seen == {bridge.ACTION_NONE, bridge.ACTION_NARRATE, bridge.ACTION_ATTEND}


def test_no_end_to_end_input_reaches_cap_confidence():
    """Sweep the real inputs that produce each boolean, not just the booleans."""
    actions = set()
    for horizon_days in (5, 20, 30, 45, 400):
        for occurrence_end in ("2026-08-01", "2026-08-31", "2026-12-31"):
            for engines in (["neural_web"], ["neural_web", "stock_seasonality"]):
                for horizon_td in (1, 20, 250):
                    result = _run(
                        [_plan(horizon_days=horizon_days, source_engines=engines)],
                        [_state(horizon_td=horizon_td, occurrence_end_date=occurrence_end)],
                    )
                    for overlay in result["overlays"]:
                        assert overlay["action"] in bridge.ALLOWED_ACTIONS
                        assert overlay["confidence_cap"] is None
                        assert overlay["adverse_event"] is False
                        assert overlay["deescalation_gate_passed"] is False
                        actions.add(overlay["action"])
    assert actions == {bridge.ACTION_NONE, bridge.ACTION_NARRATE, bridge.ACTION_ATTEND}


def test_guard_raises_if_anything_tries_to_emit_cap_confidence():
    with pytest.raises(ContractError, match="DNR:KILL-CALENDAR-GATED-RISK"):
        bridge.assert_action_allowed("CAP_CONFIDENCE")
    with pytest.raises(ContractError, match="not in"):
        bridge.assert_action_allowed("BOOST_CONFIDENCE")


def test_a_decider_that_returns_cap_confidence_raises_instead_of_shipping(monkeypatch):
    monkeypatch.setattr(
        bridge,
        "decide_action",
        lambda **_: ("CAP_CONFIDENCE", ["binary_event_hazard"]),
    )
    with pytest.raises(ContractError, match="DNR:KILL-CALENDAR-GATED-RISK"):
        _run([_plan()], [_state()])


# ---------------------------------------------------------------------------
# ATTEND is a UI marker only — documented, and carrying no machine authority
# ---------------------------------------------------------------------------


def test_attend_carries_no_write_authority():
    result = _run([_plan()], [_state()])
    overlay = result["overlays"][0]
    assert overlay["action"] == bridge.ACTION_ATTEND
    assert overlay["authority"] == {
        "may_originate": False,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "may_rewrite_geometry": False,
        "may_boost_confidence": False,
    }
    assert not any(overlay["authority"].values())
    assert overlay["attention_only"] is True


def test_module_docstring_states_the_attend_boundary():
    doc = bridge.__doc__ or ""
    lowered = doc.lower()
    for phrase in ("machine queue", "candidate prompt", "plan ordering", "retraining set", "feature store"):
        assert phrase in lowered
    assert "cap_confidence" in lowered
    assert "kill-calendar-gated-risk" in lowered


# ---------------------------------------------------------------------------
# contract validity, version snapshot, envelope shape
# ---------------------------------------------------------------------------


def test_every_overlay_revalidates_against_its_own_contract():
    result = _run(
        [_plan(plan_id="P-A", asset="XBI"), _plan(plan_id="P-B", asset="IBB")],
        [_state(symbol="XBI"), _state(symbol="IBB")],
    )
    assert len(result["overlays"]) == 2
    for overlay in result["overlays"]:
        assert overlay["schema"] == PROPHET_OVERLAY_SCHEMA
        assert validate_prophet_overlay(overlay) == overlay


#: Every key an emitted overlay is allowed to carry.  Pinned as a CLOSED set
#: because ``validate_prophet_overlay`` builds its result with ``dict(...)`` and
#: accepts unknown keys — schema validity is not evidence that nothing extra
#: rode along.
_OVERLAY_KEYS = {
    "action",
    "adverse_event",
    "asof",
    "attention_only",
    "authority",
    "confidence_cap",
    "deescalation_gate_passed",
    "event_inside_plan_horizon",
    "expires_at",
    "horizon_match",
    "overlap_with_existing_features",
    "plan_asof",
    "plan_id",
    "reason_codes",
    "schema",
    "seasonality_state_ref",
    "versions",
}


def test_the_overlay_key_set_is_closed():
    """A future edit that stamps a rank or a size must fail here, not ship.

    ``validate_prophet_overlay`` would accept ``{"rank": 1, "size_multiplier": 3.0}``
    riding on an otherwise-valid overlay and pass them straight through.
    """
    result = _run(
        [_plan(plan_id="P-A", asset="XBI"), _plan(plan_id="P-B", asset="IBB", horizon_days=45)],
        [_state(symbol="XBI"), _state(symbol="IBB", horizon_td=200)],
    )
    assert len(result["overlays"]) == 2
    for overlay in result["overlays"]:
        assert set(overlay) == _OVERLAY_KEYS
        assert not bridge.FORBIDDEN_OVERLAY_FIELDS.intersection(overlay)
        assert set(overlay["reason_codes"]) <= bridge.OVERLAY_REASON_CODES
    # The pin is real: the validator itself would have let those keys through.
    smuggled = {**result["overlays"][0], "rank": 1, "size_multiplier": 3.0}
    assert validate_prophet_overlay(smuggled)["rank"] == 1


def test_an_overlay_that_grew_an_authority_field_raises_instead_of_shipping(monkeypatch):
    real_validate = bridge.validate_prophet_overlay

    def leaky_validate(payload):
        return {**real_validate(payload), "rank": 1}

    monkeypatch.setattr(bridge, "validate_prophet_overlay", leaky_validate)
    with pytest.raises(ContractError, match="may never carry"):
        _run([_plan()], [_state()])


def test_an_overlay_reason_code_outside_the_closed_set_raises(monkeypatch):
    monkeypatch.setattr(
        bridge, "decide_action", lambda **_: (bridge.ACTION_ATTEND, ["seasonal_conviction_boost"])
    )
    with pytest.raises(ContractError, match="OVERLAY_REASON_CODES"):
        _run([_plan()], [_state()])


def test_overlay_snapshots_the_exact_versions():
    result = _run([_plan()], [_state()])
    versions = result["overlays"][0]["versions"]
    assert versions == {
        "overlay_schema": PROPHET_OVERLAY_SCHEMA,
        "overlay_set_schema": bridge.OVERLAY_SET_SCHEMA,
        "bridge_version": bridge.BRIDGE_VERSION,
        "state_schema": NEURALWEB_STATE_SCHEMA,
        "state_artifact_id": "biopharma-seasonality-state",
        "state_asof": PLAN_ASOF,
        "state_model_version": "seasonality-state/v1",
        "state_pattern_spec_hash": _HASH_A,
        "state_data_snapshot": _HASH_B,
    }


def test_overlay_never_outlives_its_state():
    state = _state(expires_at="2026-08-03T20:00:00Z")
    result = _run([_plan()], [state])
    assert result["overlays"][0]["expires_at"] == "2026-08-03T20:00:00Z"


def test_envelope_shape_and_counts():
    plans = [_plan(plan_id="P-A", asset="XBI"), _plan(plan_id="P-B", asset="IBB")]
    states = [_state(symbol="XBI"), _state(symbol="ZZZ", abstain=True)]
    result = _run(plans, states)

    assert result["schema"] == "seasonality.prophet_overlay_set.v1"
    assert result["asof"] == ASOF
    assert set(result) == {"schema", "asof", "overlays", "skipped", "counts"}
    assert result["counts"] == {
        "plans_in": 2,
        "states_in": 2,
        "states_eligible": 1,
        "overlays": 1,
        "skipped": 2,
        "by_action": {"ATTEND": 1, "NARRATE": 0, "NONE": 0},
        "by_skip_reason": {
            bridge.SKIP_NO_MATCHING_STATE: 1,
            bridge.SKIP_STATE_ABSTAINING: 1,
        },
    }
    for entry in result["skipped"]:
        assert set(entry) == {"kind", "plan_id", "state_ref", "reason", "detail"}
        assert entry["reason"] and entry["detail"]


def test_every_skip_reason_comes_from_the_closed_set():
    """``skipped[].reason`` is a vocabulary a consumer has to understand.

    Unlike ``action`` it had no closed check, so a future literal-string skip
    would pass every behavioural test in this file.
    """
    reasons_seen: set[str] = set()
    scenarios = [
        ([_plan()], []),
        ([_plan(plan_id="")], [_state()]),
        ([_plan(), _plan()], [_state()]),
        ([_plan()], [_state(abstain=True)]),
        ([_plan()], ["not-a-state"]),
        ([_plan()], [_state(expires_at="2026-08-03T06:00:00Z")]),
        ([_plan()], [_state(symbol="XBI"), _state(symbol="XBI")]),
    ]
    for plans, states in scenarios:
        result = _run(plans, states)
        for entry in result["skipped"]:
            assert entry["reason"] in bridge.SKIP_REASONS
            reasons_seen.add(entry["reason"])
        assert set(result["counts"]["by_skip_reason"]) <= bridge.SKIP_REASONS
    assert reasons_seen  # the sweep actually produced skips

    with pytest.raises(ContractError, match="is not in"):
        bridge._skip_entry(
            kind="plan", plan_id="P", state_ref=None, reason="looked_wrong", detail="d"
        )


def test_skip_reason_constants_are_all_exported_and_all_registered():
    exported = {name for name in bridge.__all__ if name.startswith("SKIP_")}
    constants = {
        name
        for name in dir(bridge)
        if name.startswith("SKIP_") and isinstance(getattr(bridge, name), str)
    }
    assert constants <= exported
    assert {getattr(bridge, name) for name in constants} == set(bridge.SKIP_REASONS)


def test_plans_may_be_mappings_as_well_as_dataclasses():
    as_mapping = dataclasses.asdict(_plan())
    result = _run([as_mapping], [_state()])
    assert result["overlays"][0]["plan_id"] == "BIO-BULL-XBI-2026-08-03"
    assert as_mapping == dataclasses.asdict(_plan())


def test_a_duck_typed_plan_may_key_itself_on_plan_id():
    """The ``plan_id`` fallback was unreachable for non-mapping, non-dataclass plans.

    ``_plan_view`` built its source from a fixed field tuple that did not
    contain ``plan_id``, so the fallback could only ever read ``None``.
    """
    class DuckPlan:
        plan_id = "DUCK-1"
        asof = PLAN_ASOF
        asset = "XBI"
        horizon_days = 30
        source_engines = ["neural_web"]

    result = _run([DuckPlan()], [_state()])
    assert [overlay["plan_id"] for overlay in result["overlays"]] == ["DUCK-1"]


def test_bare_date_asof_is_read_as_midnight_utc():
    state = _state(available_at="2026-08-02T00:00:00Z", expires_at="2026-08-03T06:00:00Z")
    # asof midnight 2026-08-03 is before the 06:00 expiry -> still live.
    live = _run([_plan()], [state], asof="2026-08-03")
    assert len(live["overlays"]) == 1
    # ...and by noon it has expired.
    dead = _run([_plan()], [state], asof=ASOF)
    assert dead["overlays"] == []


def test_naive_asof_is_refused_rather_than_guessed():
    with pytest.raises(ContractError, match="timezone"):
        _run([_plan()], [_state()], asof="2026-08-03T12:00:00")


@pytest.mark.parametrize("bad", ["2026-13-01", "2026-02-30", "not-a-date", "0000-00-00"])
def test_a_ten_character_non_date_asof_raises_contracterror_not_valueerror(bad):
    """The bare-date fast path is exactly ten characters wide.

    ``datetime.fromisoformat("2026-13-01")`` raises a bare ``ValueError``; a
    caller catching this module's documented failure mode would not catch it.
    """
    assert len(bad) == 10
    with pytest.raises(ContractError, match="ISO-8601 date"):
        _run([_plan()], [_state()], asof=bad)


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


def test_module_reads_no_wall_clock_and_draws_no_sample():
    source = Path(bridge.__file__).read_text(encoding="utf-8")
    banned = (
        "datetime.now",
        "date.today",
        "utcnow",
        "time.time",
        "random",
        "uuid",
        "os.environ",
        "getenv",
    )
    for token in banned:
        assert token not in source, f"{token!r} would make the bridge irreproducible"


def test_same_inputs_produce_identical_output():
    plans = [_plan(plan_id="P-A", asset="XBI"), _plan(plan_id="P-B", asset="IBB")]
    states = [_state(symbol="XBI"), _state(symbol="IBB")]
    first = _run(plans, states)
    second = _run(plans, states)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_asof_is_explicit_and_moves_the_result():
    state = _state(available_at="2026-08-03T00:00:00Z", expires_at="2026-08-04T00:00:00Z")
    assert len(_run([_plan()], [state], asof="2026-08-03T12:00:00Z")["overlays"]) == 1
    assert _run([_plan()], [state], asof="2026-08-05T12:00:00Z")["overlays"] == []


def test_package_exports_the_bridge():
    import engine.seasonality as pkg

    assert pkg.OVERLAY_SET_SCHEMA == "seasonality.prophet_overlay_set.v1"
    assert pkg.build_overlays_for_plans is bridge.build_overlays_for_plans
    assert "build_overlays_for_plans" in pkg.__all__
