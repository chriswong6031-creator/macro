"""China Prophet V3 "Relay Engine" — R1/R2/R3 contract pins.

Companion to tests/test_china_board_rank.py, which keeps the v2-era invariants
that V3 does NOT change (execution safeguards, lossless partition, caps, coverage
reporting).  Everything here pins something the ratified slate MOVED, so a silent
regression to v2 behaviour fails loudly:

* R1 — the measured entry ladder, the prime-window featured set, and the
  confirmed-late demotion.
* R2 — theme_timing's bounded authority: the four values, the weights summing to
  100, and the inverse of the retired W2-B order-invariance assertion (raw heat
  level alone must NOT move the score; sector_turn stays zero-authority).
* R3 — the relay ladder and the relay_late demotion (PR #4506), plus the absence
  of the refuted naked-chase/theme-split construction.
* G0.8 — the v2 shadow definition, its WATCH_DEFINITIONS isolation, and the
  tripwire specs.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine import china_board_rank, china_standout_track, cn_v3_tripwires


ASOF = "2026-08-04"


def _row(
    ticker: str,
    *,
    sector: str = "Industrials",
    stage: str | None = "ENTRY",
    extension_score: float = 0.0,
    extended: bool = False,
    coiled: dict | None = None,
    narrative: dict | None = None,
    basket_cycle: dict | None = None,
    chase: dict | None = None,
    relay: dict | None = None,
) -> dict:
    row = {
        "ticker": ticker,
        "sector": sector,
        "stage": stage,
        "extension": {"score": extension_score, "extended": extended},
        "coiled": coiled or {},
        "setup": 999.0,
        "alpha": 999.0,
    }
    for key, value in (
        ("narrative", narrative),
        ("basket_cycle", basket_cycle),
        ("chase", chase),
        ("relay", relay),
    ):
        if value is not None:
            row[key] = value
    return row


def _verdict(tier: str | None = "T2", **overrides) -> dict:
    return {
        "eligible": True,
        "tier_cascade": tier,
        "asof": ASOF,
        "input_asof": ASOF,
        **overrides,
    }


def _profile(fuel: float = 0.5) -> dict:
    return {"potential": {"components": {"fuel": fuel}}}


def _entry(status: str = "bounce_wait") -> dict:
    return {"status": status}


def _micro(*, fillable=True, chase=False, as_of: str | None = ASOF) -> dict:
    out = {"fillable": fillable, "chase_veto": {"flag": chase}}
    if as_of is not None:
        out["as_of"] = as_of
    return out


def _lanes(rows: list[dict], *, verdict_by=None, entry_by=None, **kwargs) -> dict:
    """Score + partition a row list under full execution safeguards."""
    tickers = [row["ticker"] for row in rows]
    return china_board_rank.build_board_lanes(
        rows,
        verdict_by=verdict_by or {ticker: _verdict() for ticker in tickers},
        profile_by={ticker: _profile() for ticker in tickers},
        entry_by=entry_by or {ticker: _entry() for ticker in tickers},
        rev_z_by={ticker: 1.0 for ticker in tickers},
        micro_by={ticker: _micro() for ticker in tickers},
        liquidity_by={ticker: {"adv_yi": 1.0} for ticker in tickers},
        micro_asof=ASOF,
        board_asof=ASOF,
        **kwargs,
    )


def _scored(rows: list[dict], *, entry_by=None, verdict_by=None, **kwargs) -> list[dict]:
    tickers = [row["ticker"] for row in rows]
    return china_board_rank.enrich_and_score_rows(
        rows,
        verdict_by=verdict_by or {ticker: _verdict() for ticker in tickers},
        profile_by={ticker: _profile() for ticker in tickers},
        entry_by=entry_by or {ticker: _entry() for ticker in tickers},
        rev_z_by={ticker: 1.0 for ticker in tickers},
        micro_by={ticker: _micro() for ticker in tickers},
        liquidity_by={ticker: {"adv_yi": 1.0} for ticker in tickers},
        micro_asof=ASOF,
        board_asof=ASOF,
        **kwargs,
    )


# ── R1: the measured entry ladder ─────────────────────────────────────────────

def test_entry_map_is_the_measured_order_not_the_v2_order():
    """§2.3: patience statuses were the era's BEST cohort, action statuses the worst.

    v2 ranked buy_now 1.0 above wait_pullback 0.55 and bounce_wait 0.35 — exactly
    upside down. Pin the ordering, not just the numbers, so a partial revert that
    keeps the values but reshuffles them still fails.
    """
    values = china_board_rank._ENTRY_VALUE
    assert values["bounce_wait"] == 1.0
    assert values["wait_pullback"] == 0.95
    assert values["hold"] == 0.8
    assert values["buy_now"] == 0.7
    assert values["partial"] == 0.6
    assert values["later"] == 0.5
    assert values["await"] == 0.45
    assert values["await_confluence"] == 0.45
    assert values["watch"] == 0.4
    assert values["buy_soon"] == 0.35
    assert values["extended"] == 0.3
    for terminal in ("topping", "blocked", "exit", "avoid"):
        assert values[terminal] == 0.0

    # The measured inversion, stated as an ordering.
    assert values["bounce_wait"] > values["wait_pullback"] > values["hold"]
    assert values["hold"] > values["buy_now"] > values["partial"] > values["buy_soon"]


def test_featured_entry_statuses_are_the_prime_window():
    assert china_board_rank._FEATURED_ENTRY_STATUSES == frozenset(
        {"bounce_wait", "wait_pullback", "hold", "buy_now", "partial"}
    )
    # The public alias the builder's ranking contract reads must be the same object.
    assert (
        china_board_rank.FEATURED_ENTRY_STATUSES
        is china_board_rank._FEATURED_ENTRY_STATUSES
    )


def test_bounce_wait_is_featured_admissible_under_full_safeguards():
    """The v2 shelf routed bounce_wait to more_actionable; v3 features it."""
    lanes = _lanes([_row("PATIENT.SS")], entry_by={"PATIENT.SS": _entry("bounce_wait")})

    assert [row["ticker"] for row in lanes["featured"]] == ["PATIENT.SS"]
    assert "prime_entry_window" in lanes["featured"][0]["lane_reasons"]


@pytest.mark.parametrize("status", ["bounce_wait", "wait_pullback", "hold"])
def test_patience_statuses_skip_the_ticks_test(status):
    """Only buy_now/partial carry the confirmed-late test — the patience statuses
    are the early window BY CONSTRUCTION (§2.11), so a high tick count on them is
    not the confirmed-late defect."""
    lanes = _lanes(
        [_row("EARLY.SS")],
        verdict_by={"EARLY.SS": _verdict(ticks=5)},
        entry_by={"EARLY.SS": _entry(status)},
    )

    assert [row["ticker"] for row in lanes["featured"]] == ["EARLY.SS"]


@pytest.mark.parametrize("status", ["buy_now", "partial"])
def test_confirmed_late_buy_now_and_partial_are_demoted(status):
    lanes = _lanes(
        [_row("LATE.SS")],
        verdict_by={"LATE.SS": _verdict(ticks=2)},
        entry_by={"LATE.SS": _entry(status)},
    )

    assert lanes["featured"] == []
    assert [row["ticker"] for row in lanes["more_actionable"]] == ["LATE.SS"]
    assert "confirmed_late" in lanes["more_actionable"][0]["lane_reasons"]


@pytest.mark.parametrize("status", ["buy_now", "partial"])
def test_early_buy_now_and_partial_still_feature(status):
    lanes = _lanes(
        [_row("FRESH.SS")],
        verdict_by={"FRESH.SS": _verdict(ticks=1)},
        entry_by={"FRESH.SS": _entry(status)},
    )

    assert [row["ticker"] for row in lanes["featured"]] == ["FRESH.SS"]


def test_unknown_tick_count_is_not_evidence_of_lateness():
    """``ticks is None`` reads as fresh, matching signal_gate.gate() and _signal_value.

    Pinned deliberately: this is the one fail-OPEN choice in the R1 gate, and a
    future change to fail closed should have to move this test on purpose.
    """
    lanes = _lanes(
        [_row("UNKNOWN.SS")],
        verdict_by={"UNKNOWN.SS": _verdict()},
        entry_by={"UNKNOWN.SS": _entry("buy_now")},
    )

    assert [row["ticker"] for row in lanes["featured"]] == ["UNKNOWN.SS"]


def test_board_definition_stamp_is_the_live_definition_on_rows_and_lanes():
    """The live stamp moved v3 -> v4 (ordering change); the v3 SCORE is unchanged.

    Pinned against the module constant rather than a literal so the stamp is proven
    consistent across rows, lanes and the ``prophet`` block wherever it points, while
    ``test_china_board_rank_v4.py`` owns pinning the literal itself.
    """
    live = china_board_rank.BOARD_DEFINITION
    assert live == "cn_prophet_v4"
    lanes = _lanes([_row("STAMP.SS")])
    row = lanes["featured"][0]

    assert lanes["board_definition"] == live
    assert row["board_definition"] == live
    assert row["prophet"]["version"] == live
    # The v3 SCORE survives the definition bump untouched.
    assert row["prophet"]["score_basis"] == "cn_prophet_v3_score"


# ── R2: theme_timing's bounded authority ──────────────────────────────────────

def test_score_weights_sum_to_one_hundred_with_theme_timing_fifteen():
    assert china_board_rank.SCORE_WEIGHTS == {
        "signal": 30.0,
        "entry": 20.0,
        "runway": 15.0,
        "bottom_quality": 10.0,
        "reversal_member": 10.0,
        "theme_timing": 15.0,
    }
    assert sum(china_board_rank.SCORE_WEIGHTS.values()) == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("narrative", "basket_cycle", "expected"),
    [
        # 1.0 — WARMING member, or an early basket cycle turning up.
        ({"theme": "Semis", "level": "WARMING"}, None, 1.0),
        (None, {"phase": "Trough", "osc_up": True}, 1.0),
        (None, {"phase": "Recovery", "osc_up": True}, 1.0),
        ({"theme": "Semis", "level": "HOT"}, {"phase": "Trough", "osc_up": True}, 1.0),
        # 0.0 — a fading basket, or HOT into a rolling-over late cycle.
        (None, {"phase": "Downturn", "osc_up": False}, 0.0),
        ({"theme": "Semis", "level": "HOT"}, {"phase": "Peak", "osc_up": False}, 0.0),
        # 0.6 — any other member, INCLUDING raw HOT with no timing state.
        ({"theme": "Semis", "level": "HOT"}, None, 0.6),
        ({"theme": "Semis", "level": None}, None, 0.6),
        (None, {"phase": "Expansion", "osc_up": True}, 0.6),
        (None, {"phase": None, "osc_up": None}, 0.6),
        # 0.25 — genuine non-membership only.
        (None, None, 0.25),
        ({"theme": None, "level": "HOT"}, None, 0.25),
    ],
)
def test_theme_timing_ladder(narrative, basket_cycle, expected):
    value = china_board_rank._theme_timing_value(
        _row("T.SS", narrative=narrative, basket_cycle=basket_cycle)
    )
    assert value == pytest.approx(expected)


def test_theme_timing_only_ever_takes_four_values():
    seen = set()
    for level in (None, "WARMING", "HOT", "COLD"):
        for phase in (None, "Trough", "Recovery", "Expansion", "Peak", "Downturn"):
            for osc_up in (True, False):
                for theme in (None, "Semis"):
                    narrative = {"theme": theme, "level": level}
                    cycle = None if phase is None else {"phase": phase, "osc_up": osc_up}
                    seen.add(
                        china_board_rank._theme_timing_value(
                            _row("T.SS", narrative=narrative, basket_cycle=cycle)
                        )
                    )
    assert seen <= {0.0, 0.25, 0.6, 1.0}


def test_theme_timing_is_null_tolerant_on_malformed_payloads():
    for payload in ("not-a-dict", 7, [], {}):
        value = china_board_rank._theme_timing_value(
            {"ticker": "X.SS", "narrative": payload, "basket_cycle": payload}
        )
        assert value == pytest.approx(0.25)


def test_theme_timing_is_the_only_channel_narrative_has():
    """The INVERSE of the retired W2-B order-invariance assertion.

    v2 asserted at build time that narrative left the board byte-identical. V3
    asserts the bounded form instead: raw heat LEVEL alone must not change the
    score away from the neutral member value, and sector_turn must still change
    nothing at all.
    """
    base = _row("A.SS", narrative={"theme": "Semis", "level": "HOT"})
    neutral = _row("A.SS", narrative={"theme": "Semis", "level": None})
    hot_score = _scored([base])[0]["prophet_score"]
    neutral_score = _scored([neutral])[0]["prophet_score"]

    # Heat level with no timing state buys nothing over a neutral member.
    assert hot_score == pytest.approx(neutral_score)
    assert _scored([base])[0]["prophet"]["components"]["theme_timing"] == pytest.approx(0.6)

    # sector_turn keeps ZERO authority: an extreme value changes no score.
    with_turn = _scored(
        [_row("A.SS", narrative={"theme": "Semis", "level": "HOT"})],
        sector_turn_by={"A.SS": {"state": "bottoming", "osc_slope": 99.0}},
    )[0]
    assert with_turn["prophet_score"] == pytest.approx(hot_score)
    assert "theme_timing" in with_turn["prophet"]["components"]
    assert "sector_turn" not in with_turn["prophet"]["components"]


def test_zero_score_authority_drops_narrative_and_keeps_the_rest():
    assert china_board_rank._ZERO_SCORE_AUTHORITY == (
        "residual_alpha",
        "setup",
        "sector_turn",
        "quality",
        "low_vol",
        "risk_sizing",
    )
    assert "narrative" not in china_board_rank._ZERO_SCORE_AUTHORITY
    row = _scored([_row("A.SS")])[0]
    assert "narrative" not in row["prophet"]["zero_score_authority"]
    assert "sector_turn" in row["prophet"]["zero_score_authority"]


def test_theme_timing_moves_the_score_by_exactly_its_weight():
    """A member in an early turning basket outscores a non-member by 15 * (1 - .25).

    The two rows sit in DIFFERENT sectors on purpose: reversal membership is a
    within-sector quintile, so a same-sector pair would hand +10 to whichever
    ticker sorted first and confound the delta under test.
    """
    member = _row("M.SS", sector="Tech", basket_cycle={"phase": "Trough", "osc_up": True})
    outsider = _row("O.SS", sector="Utilities")
    scored = {row["ticker"]: row for row in _scored([member, outsider])}

    assert scored["M.SS"]["prophet_score"] - scored["O.SS"]["prophet_score"] == (
        pytest.approx(15.0 * (1.0 - 0.25))
    )


def test_exact_v3_score_math():
    """signal 30 + entry 20 + runway 15*(.6*.5 + .4*.75) + bottom 10 + reversal 10
    + theme_timing 15*1.0, with the entry leg on the measured bounce_wait 1.0."""
    row = _row(
        "BEST.SS",
        extension_score=0.25,
        coiled={"star": True},
        basket_cycle={"phase": "Trough", "osc_up": True},
    )
    scored = _scored([row], entry_by={"BEST.SS": _entry("bounce_wait")})[0]

    assert scored["prophet_rank"]["components"]["runway"]["value"] == pytest.approx(0.6)
    # 30 + 20 + 9 + 10 + 10 + 15
    assert scored["prophet_score"] == pytest.approx(94.0)


# ── R3: the relay ladder (PR #4506) ───────────────────────────────────────────

@pytest.mark.parametrize(
    ("count", "expected"),
    [(None, None), (0, "early"), (1, "early"), (2, "mid"), (3, "mid"), (4, "late"), (9, "late")],
)
def test_relay_position_ladder(count, expected):
    assert china_board_rank.relay_position(count) == expected
    assert china_board_rank.relay_state(count) == {
        "count_3d": None if count is None else int(count),
        "position": expected,
    }


def test_relay_count_of_zero_is_early_not_unpositioned():
    """A basket member whose peers printed nothing is EARLY in its relay; a name in
    no basket has no relay at all. Collapsing the two would let non-members inherit
    a position they cannot have."""
    assert china_board_rank.relay_position(0) == "early"
    assert china_board_rank.relay_position(None) is None


def test_relay_ladder_from_a_three_name_basket_fixture():
    """A 3-member basket where the two OTHER members limit-close inside 3 sessions
    puts the candidate at count 2 / position mid — the builder's join, reproduced
    on the engine's side of the contract."""
    basket_members = ["A.SS", "B.SS", "C.SS"]
    limit_recent = {"B.SS", "C.SS"}
    peers = {t for t in basket_members if t != "A.SS"}
    state = china_board_rank.relay_state(len(peers & limit_recent))

    assert state == {"count_3d": 2, "position": "mid"}
    # And the same basket one session later, with two more names printing.
    late = china_board_rank.relay_state(
        len({"B.SS", "C.SS", "D.SS", "E.SS"} & {"B.SS", "C.SS", "D.SS", "E.SS"})
    )
    assert late["position"] == "late"


def test_chase_composite_fires_on_each_leg_and_never_on_missing_data():
    fires = [
        {"limit_close_day": True, "trail_21": None, "run_5d": None},
        {"limit_close_day": False, "trail_21": 0.25, "run_5d": None},
        {"limit_close_day": False, "trail_21": None, "run_5d": 0.15},
    ]
    for chase in fires:
        assert china_board_rank._chase_composite(_row("C.SS", chase=chase)) is True

    quiet = [
        None,
        {"limit_close_day": False, "trail_21": 0.24, "run_5d": 0.149},
        {"limit_close_day": None, "trail_21": None, "run_5d": None},
    ]
    for chase in quiet:
        assert china_board_rank._chase_composite(_row("C.SS", chase=chase)) is False


def test_relay_late_chase_row_demotes_to_more_actionable_not_late_lane():
    """The demotion is ordering-grade, so it is a featured SHORTFALL — the row keeps
    its place among live signals rather than being routed to late_or_unfillable."""
    lanes = _lanes(
        [
            _row(
                "LATERELAY.SS",
                chase={"limit_close_day": True, "trail_21": None, "run_5d": None},
                relay={"count_3d": 5, "position": "late"},
            )
        ]
    )

    assert lanes["featured"] == []
    assert lanes["late_or_unfillable"] == []
    assert [row["ticker"] for row in lanes["more_actionable"]] == ["LATERELAY.SS"]
    assert "relay_late" in lanes["more_actionable"][0]["lane_reasons"]


@pytest.mark.parametrize("position", ["early", "mid"])
def test_early_and_mid_relay_chase_rows_still_feature(position):
    lanes = _lanes(
        [
            _row(
                "RELAY.SS",
                chase={"limit_close_day": True, "trail_21": 0.4, "run_5d": 0.3},
                relay={"count_3d": 1 if position == "early" else 3, "position": position},
            )
        ]
    )

    assert [row["ticker"] for row in lanes["featured"]] == ["RELAY.SS"]


def test_relay_late_without_a_chase_fire_is_not_demoted():
    """Position alone is not the cohort — the demotion needs the chase composite too."""
    lanes = _lanes(
        [
            _row(
                "QUIET.SS",
                chase={"limit_close_day": False, "trail_21": 0.05, "run_5d": 0.01},
                relay={"count_3d": 6, "position": "late"},
            )
        ]
    )

    assert [row["ticker"] for row in lanes["featured"]] == ["QUIET.SS"]


def test_chase_and_relay_are_display_fields_with_no_score_authority():
    plain = _row("P.SS")
    chased = _row(
        "P.SS",
        chase={"limit_close_day": True, "trail_21": 0.9, "run_5d": 0.5},
        relay={"count_3d": 7, "position": "late"},
    )

    assert (
        _scored([chased])[0]["prophet_score"]
        == pytest.approx(_scored([plain])[0]["prophet_score"])
    )
    # ...and they survive onto the row so W0 can grade every branch nightly.
    lanes = _lanes([chased])
    row = (lanes["featured"] + lanes["more_actionable"])[0]
    assert row["chase"]["limit_close_day"] is True
    assert row["relay"]["position"] == "late"


def test_the_refuted_chase_constructions_are_gone():
    """PR #4506 refuted both the blanket chase demote and the theme-heat split.

    Neither may come back through the module surface, and a chase fire with no
    theme behind it must NOT be demoted on that basis alone.
    """
    assert not hasattr(china_board_rank, "naked_chase")
    assert not isinstance(getattr(china_board_rank, "relay", None), type(lambda: None))

    lanes = _lanes(
        [
            _row(
                "NOTHEME.SS",
                chase={"limit_close_day": True, "trail_21": 0.9, "run_5d": 0.5},
                relay=china_board_rank.relay_state(None),
            )
        ]
    )
    assert [row["ticker"] for row in lanes["featured"]] == ["NOTHEME.SS"]
    every_reason = {
        reason
        for lane in ("featured", "more_actionable", "late_or_unfillable", "forming")
        for row in lanes[lane]
        for reason in row["lane_reasons"]
    }
    assert "naked_chase" not in every_reason


# ── G0.8: the shadow race and the tripwires ───────────────────────────────────

def test_v2_shadow_shelf_applies_the_displaced_rule_to_the_same_scored_rows():
    rows = [
        _row("PATIENCE.SS"),                                    # bounce_wait
        _row("CONFIRMED.SS"),                                   # buy_now, ticks 2
        _row("FRESHBUY.SS"),                                    # buy_now, ticks 1
    ]
    scored = _scored(
        rows,
        verdict_by={
            "PATIENCE.SS": _verdict(),
            "CONFIRMED.SS": _verdict(ticks=2),
            "FRESHBUY.SS": _verdict(ticks=1),
        },
        entry_by={
            "PATIENCE.SS": _entry("bounce_wait"),
            "CONFIRMED.SS": _entry("buy_now"),
            "FRESHBUY.SS": _entry("buy_now"),
        },
    )
    live = china_board_rank.partition_board_rows(scored)
    shadow = china_board_rank.v2_shadow_featured(scored)

    # v3 features the patience row and the early buy; v2 features both buys.
    assert {row["ticker"] for row in live["featured"]} == {
        "PATIENCE.SS", "FRESHBUY.SS",
    }
    assert {row["ticker"] for row in shadow} == {"CONFIRMED.SS", "FRESHBUY.SS"}
    assert all(row["board_definition"] == "cn_prophet_v2_shadow" for row in shadow)
    # The live rows are untouched by the shadow run (it deep-copies).
    assert all(row["board_definition"] == china_board_rank.BOARD_DEFINITION
               for row in live["featured"])


def test_v2_shadow_definition_is_a_watch_definition():
    assert china_board_rank.V2_SHADOW_DEFINITION == "cn_prophet_v2_shadow"
    assert "cn_prophet_v2_shadow" in china_standout_track.WATCH_DEFINITIONS


def test_v2_shadow_can_never_own_the_headline_definition():
    """Appended AFTER the live rows on the same date, the shadow must still lose the
    headline-definition resolution — otherwise the accruing record would silently
    become the challenger's."""
    frame = pd.DataFrame(
        [
            {"date": "2026-08-04", "ticker": "A.SS", "board_definition": "cn_prophet_v3"},
            {"date": "2026-08-04", "ticker": "B.SS", "board_definition": "cn_prophet_v3"},
            {"date": "2026-08-04", "ticker": "A.SS",
             "board_definition": "cn_prophet_v2_shadow"},
        ]
    )
    graded, definition = china_standout_track._latest_definition_frame(frame)

    assert definition == "cn_prophet_v3"
    assert set(graded["board_definition"]) == {"cn_prophet_v3"}
    assert len(graded) == 2


def test_tripwire_specs_cover_the_four_slate_items():
    specs = cn_v3_tripwires.tripwire_specs()

    # R4 is the V4 ordering race (see test_china_board_rank_v4.py).
    assert {spec["slate_item"] for spec in specs} == {"R1", "R2", "R3", "R4"}
    assert len({spec["id"] for spec in specs}) == len(specs)
    for spec in specs:
        assert spec["min_matured"] == 60
        assert spec["direction"] in {
            "treatment_higher", "treatment_lower", "control_higher", "control_lower",
        }
        assert spec["action"].startswith("emit ::warning ")
        assert spec["evidence"]

    r1 = cn_v3_tripwires.tripwire_by_id("cn_v3_vs_v2_shadow_winrate")
    assert r1["threshold"] == 5.0
    assert r1["treatment"]["board_definition"] == china_board_rank.BOARD_DEFINITION
    assert r1["control"]["board_definition"] == china_board_rank.V2_SHADOW_DEFINITION

    r2 = cn_v3_tripwires.tripwire_by_id("cn_v3_theme_timing_strata")
    assert r2["treatment"]["theme_timing"] == 1.0
    assert r2["control"]["theme_timing"] == 0.25

    r3 = cn_v3_tripwires.tripwire_by_id("cn_v3_relay_late_demote")
    assert r3["treatment"]["lane_reason"] == "relay_late"
    assert r3["treatment"]["lane"] == "more_actionable"

    assert cn_v3_tripwires.tripwire_by_id("nope") is None
