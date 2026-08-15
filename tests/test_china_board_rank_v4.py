"""China Prophet V4 — "rank by interestingness, gate by entry" contract pins.

Companion to ``tests/test_china_board_rank_v3.py`` (which pins the v3 ADMISSION rules
V4 deliberately preserves) and ``tests/test_china_intel_interest.py`` (which pins the
board-independence of the ordering input).

What V4 changed, and therefore what this file pins:

* the live definition and the displaced-v3 ordering shadow;
* the ordering key: measured interest first, v3 ``prophet_score`` second, ticker third;
* the FALLBACK: a name with no measurable intelligence keeps its v3 priority and is
  never scored zero;
* the caps binding on the NEW order, so interest decides the last shelf slot;
* what V4 did NOT change: the score, the admission gates, the lossless partition.
"""
from __future__ import annotations

from engine import china_board_rank, china_standout_track, cn_v3_tripwires


ASOF = "2026-08-15"


def _row(ticker: str, *, sector: str = "Industrials", stage: str | None = "ENTRY") -> dict:
    return {
        "ticker": ticker,
        "sector": sector,
        "stage": stage,
        "extension": {"score": 0.0, "extended": False},
        "coiled": {},
    }


def _verdict(**overrides) -> dict:
    return {"eligible": True, "tier_cascade": "T2", "asof": ASOF,
            "input_asof": ASOF, **overrides}


def _micro() -> dict:
    return {"fillable": True, "chase_veto": {"flag": False}, "as_of": ASOF}


def _measured(score: float) -> dict:
    return {"definition": "cn_intel_interest_v1", "basis": "measured",
            "score": score, "drivers": ["synthetic"], "signal_core": 0.5,
            "edge_remaining": 0.5, "gap": 0}


def _unavailable() -> dict:
    return {"definition": "cn_intel_interest_v1", "basis": "fallback_v3",
            "score": None, "unavailable_reason": "no_desk_evidence", "drivers": []}


def _scored(rows: list[dict], *, intel_by=None, fuel_by=None, **kwargs) -> list[dict]:
    tickers = [row["ticker"] for row in rows]
    fuel_by = fuel_by or {}
    return china_board_rank.enrich_and_score_rows(
        rows,
        verdict_by={t: _verdict() for t in tickers},
        profile_by={t: {"potential": {"components": {"fuel": fuel_by.get(t, 0.5)}}}
                    for t in tickers},
        entry_by={t: {"status": "bounce_wait"} for t in tickers},
        rev_z_by={t: 1.0 for t in tickers},
        micro_by={t: _micro() for t in tickers},
        liquidity_by={t: {"adv_yi": 1.0} for t in tickers},
        intel_by=intel_by,
        micro_asof=ASOF,
        board_asof=ASOF,
        **kwargs,
    )


# ── Definitions ───────────────────────────────────────────────────────────── #

def test_live_definition_is_v4_and_v3_is_the_ordering_shadow():
    assert china_board_rank.BOARD_DEFINITION == "cn_prophet_v4"
    assert china_board_rank.V3_SHADOW_DEFINITION == "cn_prophet_v3_shadow"
    # v2's admission shadow is untouched by the ordering change.
    assert china_board_rank.V2_SHADOW_DEFINITION == "cn_prophet_v2_shadow"


def test_both_shadows_are_watch_definitions_and_never_own_the_headline_grade():
    assert china_board_rank.V3_SHADOW_DEFINITION in china_standout_track.WATCH_DEFINITIONS
    assert china_board_rank.V2_SHADOW_DEFINITION in china_standout_track.WATCH_DEFINITIONS
    assert china_board_rank.BOARD_DEFINITION not in china_standout_track.WATCH_DEFINITIONS


def test_tripwire_live_definition_tracks_the_board():
    """A spec pointing at a retired stamp matches zero rows and reads as 'no breach'.

    Pinning them equal is what makes the next definition bump fail HERE rather than
    silently disarming every R1-R3 alarm.
    """
    assert cn_v3_tripwires.LIVE_BOARD_DEFINITION == china_board_rank.BOARD_DEFINITION


def test_v4_ordering_race_has_a_named_tripwire_with_a_revert_action():
    """G0.8: every ratified direct wiring ships shadow + named tripwire + revert path."""
    spec = cn_v3_tripwires.tripwire_by_id("cn_v4_vs_v3_order_shadow_excess")
    assert spec is not None
    assert spec["treatment"]["board_definition"] == china_board_rank.BOARD_DEFINITION
    assert spec["control"]["board_definition"] == china_board_rank.V3_SHADOW_DEFINITION
    assert spec["min_matured"] == 60
    assert spec["action"].startswith("emit ::warning ")
    # The evidence field must not claim a measured edge this wiring does not have.
    assert "NO forward evidence" in spec["evidence"]


# ── The score did NOT change ──────────────────────────────────────────────── #

def test_intel_adds_no_score():
    """Same rows, with and without intelligence: identical prophet_score."""
    without = _scored([_row("A.SS"), _row("B.SS")])
    with_intel = _scored(
        [_row("A.SS"), _row("B.SS")],
        intel_by={"A.SS": _measured(99.0), "B.SS": _measured(0.0)},
    )
    assert ({r["ticker"]: r["prophet_score"] for r in without}
            == {r["ticker"]: r["prophet_score"] for r in with_intel})


def test_score_weights_and_zero_authority_are_untouched_by_v4():
    assert sum(china_board_rank.SCORE_WEIGHTS.values()) == 100.0
    assert "sector_turn" in china_board_rank.ZERO_SCORE_AUTHORITY
    row = _scored([_row("A.SS")])[0]
    assert row["prophet"]["score_basis"] == "cn_prophet_v3_score"
    assert row["prophet"]["order_basis"] == china_board_rank.INTEL_INTEREST_ORDER


# ── The ordering key ──────────────────────────────────────────────────────── #

def test_interest_outranks_a_higher_v3_score():
    """The whole point: a great entry cannot carry an uninteresting name to the top."""
    scored = _scored(
        [_row("BORING.SS"), _row("INTERESTING.SS")],
        fuel_by={"BORING.SS": 1.0, "INTERESTING.SS": 0.0},   # BORING wins on v3
        intel_by={"BORING.SS": _measured(1.0), "INTERESTING.SS": _measured(90.0)},
    )
    by_ticker = {r["ticker"]: r for r in scored}
    assert by_ticker["BORING.SS"]["prophet_score"] > by_ticker["INTERESTING.SS"]["prophet_score"]
    assert by_ticker["BORING.SS"]["score_rank"] < by_ticker["INTERESTING.SS"]["score_rank"]
    # ...and the v4 board order inverts it.
    assert by_ticker["INTERESTING.SS"]["board_rank"] < by_ticker["BORING.SS"]["board_rank"]


def test_v3_score_breaks_ties_between_equal_interest():
    scored = _scored(
        [_row("LOW.SS"), _row("HIGH.SS")],
        fuel_by={"HIGH.SS": 1.0, "LOW.SS": 0.0},
        intel_by={"LOW.SS": _measured(50.0), "HIGH.SS": _measured(50.0)},
    )
    order = [r["ticker"] for r in sorted(scored, key=lambda r: r["board_rank"])]
    assert order == ["HIGH.SS", "LOW.SS"]


def test_ticker_breaks_a_total_tie_deterministically():
    scored = _scored(
        [_row("BBB.SS"), _row("AAA.SS")],
        intel_by={"BBB.SS": _measured(10.0), "AAA.SS": _measured(10.0)},
    )
    order = [r["ticker"] for r in sorted(scored, key=lambda r: r["board_rank"])]
    assert order == ["AAA.SS", "BBB.SS"]


# ── The fallback is not a zero ────────────────────────────────────────────── #

def test_unavailable_intel_keeps_its_v3_priority_rather_than_sinking_to_zero():
    """A name the desks never saw must not be buried beneath a measured 1.0."""
    scored = _scored(
        [_row("UNSEEN.SS"), _row("DULL.SS")],
        fuel_by={"UNSEEN.SS": 1.0, "DULL.SS": 0.0},
        intel_by={"UNSEEN.SS": _unavailable(), "DULL.SS": _measured(1.0)},
    )
    by_ticker = {r["ticker"]: r for r in scored}
    assert by_ticker["UNSEEN.SS"]["intel_interest_basis"] == "fallback_v3"
    assert by_ticker["UNSEEN.SS"]["intel_interest_score"] is None
    # Its v3 score (high) is the substituted key, so it stays above the dull name.
    assert by_ticker["UNSEEN.SS"]["board_rank"] < by_ticker["DULL.SS"]["board_rank"]


def test_missing_intel_map_leaves_board_order_identical_to_v3_order():
    """Total evidence failure degrades to v3 ordering — never to a dark or random board."""
    scored = _scored([_row(f"T{i}.SS") for i in range(6)],
                     fuel_by={f"T{i}.SS": i / 10 for i in range(6)})
    assert all(r["intel_interest_basis"] == "fallback_v3" for r in scored)
    assert all(r["board_rank"] == r["score_rank"] for r in scored)


def test_malformed_intel_record_is_treated_as_unavailable_not_as_zero():
    for broken in ({"basis": "measured", "score": None}, {"basis": "measured"},
                   {"score": 50.0}, "not-a-mapping", None):
        scored = _scored([_row("X.SS")], intel_by={"X.SS": broken})
        assert scored[0]["intel_interest_basis"] == "fallback_v3", broken
        assert scored[0]["intel_interest_score"] is None, broken


def test_out_of_range_intel_score_is_clamped_not_trusted():
    scored = _scored([_row("A.SS"), _row("B.SS")],
                     intel_by={"A.SS": _measured(9999.0), "B.SS": _measured(-50.0)})
    by_ticker = {r["ticker"]: r for r in scored}
    assert by_ticker["A.SS"]["intel_interest_score"] == 100.0
    assert by_ticker["B.SS"]["intel_interest_score"] == 0.0


# ── The caps bind on the NEW order ────────────────────────────────────────── #

def test_featured_cap_admits_the_most_interesting_qualifying_names():
    rows = [_row(f"N{i}.SS", sector=f"S{i}") for i in range(5)]
    # v3 order is the reverse of the interest order.
    fuel_by = {f"N{i}.SS": (5 - i) / 10 for i in range(5)}
    intel_by = {f"N{i}.SS": _measured(float(i * 10)) for i in range(5)}
    scored = _scored(rows, fuel_by=fuel_by, intel_by=intel_by)
    lanes = china_board_rank.partition_board_rows(scored, featured_cap=2, sector_cap=4)

    assert [r["ticker"] for r in lanes["featured"]] == ["N4.SS", "N3.SS"]
    # The displaced v3 ORDER would have taken the other end of the board.
    shadow = china_board_rank.v3_shadow_featured(scored, featured_cap=2, sector_cap=4)
    assert [r["ticker"] for r in shadow] == ["N0.SS", "N1.SS"]


def test_sector_cap_also_binds_on_interest():
    rows = [_row(f"S{i}.SS", sector="Tech") for i in range(4)]
    scored = _scored(
        rows,
        fuel_by={f"S{i}.SS": (4 - i) / 10 for i in range(4)},
        intel_by={f"S{i}.SS": _measured(float(i * 10)) for i in range(4)},
    )
    lanes = china_board_rank.partition_board_rows(scored, featured_cap=24, sector_cap=2)
    assert [r["ticker"] for r in lanes["featured"]] == ["S3.SS", "S2.SS"]


def test_lane_display_order_follows_board_rank():
    rows = [_row(f"D{i}.SS", sector=f"S{i}") for i in range(3)]
    scored = _scored(
        rows,
        fuel_by={f"D{i}.SS": (3 - i) / 10 for i in range(3)},
        intel_by={f"D{i}.SS": _measured(float(i * 10)) for i in range(3)},
    )
    lanes = china_board_rank.partition_board_rows(scored)
    assert [r["display_rank"] for r in lanes["featured"]] == [1, 2, 3]
    assert [r["ticker"] for r in lanes["featured"]] == ["D2.SS", "D1.SS", "D0.SS"]


# ── The shadows ───────────────────────────────────────────────────────────── #

def test_v3_shadow_stamps_its_own_definition_and_leaves_live_rows_untouched():
    scored = _scored([_row("A.SS", sector="X"), _row("B.SS", sector="Y")],
                     fuel_by={"A.SS": 1.0, "B.SS": 0.0},
                     intel_by={"A.SS": _measured(0.0), "B.SS": _measured(90.0)})
    live = china_board_rank.partition_board_rows(scored)
    shadow = china_board_rank.v3_shadow_featured(scored)

    assert [r["ticker"] for r in live["featured"]] == ["B.SS", "A.SS"]
    assert [r["ticker"] for r in shadow] == ["A.SS", "B.SS"]
    assert all(r["board_definition"] == "cn_prophet_v3_shadow" for r in shadow)
    assert all(r["board_definition"] == "cn_prophet_v4" for r in live["featured"])


def test_v2_admission_shadow_still_isolates_the_admission_rule():
    """The v2 race must not be confounded by the v4 ordering change."""
    rows = [_row("PATIENCE.SS", sector="X"), _row("CONFIRMED.SS", sector="Y")]
    tickers = [r["ticker"] for r in rows]
    scored = china_board_rank.enrich_and_score_rows(
        rows,
        verdict_by={"PATIENCE.SS": _verdict(), "CONFIRMED.SS": _verdict(ticks=5)},
        profile_by={t: {"potential": {"components": {"fuel": 0.5}}} for t in tickers},
        entry_by={"PATIENCE.SS": {"status": "bounce_wait"},
                  "CONFIRMED.SS": {"status": "buy_now"}},
        rev_z_by={t: 1.0 for t in tickers},
        micro_by={t: _micro() for t in tickers},
        liquidity_by={t: {"adv_yi": 1.0} for t in tickers},
        intel_by={"PATIENCE.SS": _measured(1.0), "CONFIRMED.SS": _measured(99.0)},
        micro_asof=ASOF,
        board_asof=ASOF,
    )
    live = china_board_rank.partition_board_rows(scored)
    v2_shadow = china_board_rank.v2_shadow_featured(scored)

    # v4 features the patience row (v3's prime-window rule, unchanged).
    assert {r["ticker"] for r in live["featured"]} == {"PATIENCE.SS"}
    # v2's rule admits the confirmed-late row instead — the admission difference.
    assert {r["ticker"] for r in v2_shadow} == {"CONFIRMED.SS"}


# ── What V4 did NOT change ────────────────────────────────────────────────── #

def test_partition_stays_lossless_under_the_new_order():
    rows = [_row(f"L{i}.SS", sector=f"S{i % 3}") for i in range(12)]
    scored = _scored(rows, intel_by={f"L{i}.SS": _measured(float(i)) for i in range(12)})
    lanes = china_board_rank.partition_board_rows(scored, featured_cap=3, sector_cap=1)
    assert sum(lanes["counts"].values()) == len(scored)


def test_admission_gates_are_order_independent():
    """An unfillable name stays out of featured no matter how interesting it is."""
    tickers = ["BLOCKED.SS"]
    scored = china_board_rank.enrich_and_score_rows(
        [_row("BLOCKED.SS")],
        verdict_by={t: _verdict() for t in tickers},
        profile_by={t: {"potential": {"components": {"fuel": 0.5}}} for t in tickers},
        entry_by={t: {"status": "bounce_wait"} for t in tickers},
        rev_z_by={t: 1.0 for t in tickers},
        micro_by={"BLOCKED.SS": {"fillable": False, "chase_veto": {"flag": False},
                                 "as_of": ASOF}},
        liquidity_by={t: {"adv_yi": 1.0} for t in tickers},
        intel_by={"BLOCKED.SS": _measured(100.0)},
        micro_asof=ASOF,
        board_asof=ASOF,
    )
    lanes = china_board_rank.partition_board_rows(scored)
    assert lanes["featured"] == []
    assert [r["ticker"] for r in lanes["late_or_unfillable"]] == ["BLOCKED.SS"]
    assert "unfillable" in lanes["late_or_unfillable"][0]["lane_reasons"]


def test_intel_receipt_rides_the_row_for_the_card_and_the_ledger():
    scored = _scored([_row("R.SS")], intel_by={"R.SS": _measured(42.5)})
    row = scored[0]
    assert row["intel"]["score"] == 42.5
    assert row["intel"]["basis"] == "measured"
    assert row["intel"]["drivers"] == ["synthetic"]
    lanes = china_board_rank.partition_board_rows(scored)
    assert lanes["featured"][0]["intel"]["score"] == 42.5
