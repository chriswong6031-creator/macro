"""China Prophet V4 — "rank by interestingness, gate by entry" contract pins.

Companion to ``tests/test_china_board_rank_v3.py`` (which pins the v3 ADMISSION rules
V4 deliberately preserves) and ``tests/test_china_intel_interest.py`` (which pins the
board-independence of the ordering input).

What V4 changed, and therefore what this file pins:

* the live definition and the displaced-v3 ordering shadow;
* the ordering key: measured interest first, v3 ``prophet_score`` second, ticker third;
* coverage-atomic fallback: if even one ranked name lacks valid Intelligence
  interest, the entire bake orders by v3 ``score_rank`` — never mixed scales;
* a measured interest of 0.0 is valid coverage and does not trigger fallback;
* the caps binding on the effective order;
* what V4 did NOT change: the score, the admission gates, the lossless partition.
* R4 treatment accrues only when intelligence ordering actually ran.
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
    # Fallback bakes keep board_definition=cn_prophet_v4; treatment requires
    # that intelligence ordering actually ran.
    assert spec["treatment"]["lane"] == "featured"
    assert spec["treatment"]["effective_order_basis"] == (
        china_board_rank.INTEL_INTEREST_ORDER
    )


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
    row = _scored([_row("A.SS")], intel_by={"A.SS": _measured(10.0)})[0]
    assert row["prophet"]["score_basis"] == china_board_rank.V3_SCORE_ORDER
    assert row["prophet"]["requested_order_basis"] == china_board_rank.INTEL_INTEREST_ORDER
    assert row["prophet"]["effective_order_basis"] == china_board_rank.INTEL_INTEREST_ORDER
    assert row["prophet"]["order_basis"] == china_board_rank.INTEL_INTEREST_ORDER
    assert row["prophet"]["order_mode"] == china_board_rank.ORDER_MODE_INTELLIGENCE
    assert row["prophet"].get("fallback_reason") is None


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


# ── Coverage-atomic fallback ──────────────────────────────────────────────── #

def test_unavailable_row_reverts_the_whole_board_to_v3_order():
    """One uncovered name disables intelligence authority for the bake.

    Mixed-scale ranking (interest for covered names, v3 score for uncovered
    names, compared in the same slot) is the path this hardening forbids.
    Intelligence observations on the covered name stay on the row.
    """
    scored = _scored(
        [_row("UNSEEN.SS"), _row("DULL.SS")],
        fuel_by={"UNSEEN.SS": 1.0, "DULL.SS": 0.0},
        intel_by={"UNSEEN.SS": _unavailable(), "DULL.SS": _measured(1.0)},
    )
    by_ticker = {r["ticker"]: r for r in scored}
    assert by_ticker["UNSEEN.SS"]["intel_interest_basis"] == "fallback_v3"
    assert by_ticker["UNSEEN.SS"]["intel_interest_score"] is None
    assert by_ticker["DULL.SS"]["intel_interest_basis"] == "measured"
    assert by_ticker["DULL.SS"]["intel_interest_score"] == 1.0
    assert all(r["board_rank"] == r["score_rank"] for r in scored)
    assert scored[0]["order_mode"] == china_board_rank.ORDER_MODE_V3_FALLBACK
    assert scored[0]["effective_order_basis"] == china_board_rank.V3_SCORE_ORDER
    assert scored[0]["requested_order_basis"] == china_board_rank.INTEL_INTEREST_ORDER
    assert scored[0]["fallback_reason"] == (
        china_board_rank.FALLBACK_REASON_INCOMPLETE_COVERAGE
    )


def test_missing_intel_map_leaves_board_order_identical_to_v3_order():
    """Total evidence failure degrades to v3 ordering — never to a dark or random board."""
    scored = _scored([_row(f"T{i}.SS") for i in range(6)],
                     fuel_by={f"T{i}.SS": i / 10 for i in range(6)})
    assert all(r["intel_interest_basis"] == "fallback_v3" for r in scored)
    assert all(r["board_rank"] == r["score_rank"] for r in scored)
    assert scored[0]["order_mode"] == china_board_rank.ORDER_MODE_V3_FALLBACK
    assert scored[0]["effective_order_basis"] == china_board_rank.V3_SCORE_ORDER


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


# ── Coverage-atomic mutations (A–H) ───────────────────────────────────────── #

def test_complete_coverage_preserves_v4_intelligence_order():
    """A. 100% coverage: live == intelligence order, shadow == v3 order."""
    scored = _scored(
        [_row("BORING.SS", sector="X"), _row("INTERESTING.SS", sector="Y")],
        fuel_by={"BORING.SS": 1.0, "INTERESTING.SS": 0.0},
        intel_by={"BORING.SS": _measured(1.0), "INTERESTING.SS": _measured(90.0)},
    )
    live = china_board_rank.partition_board_rows(scored)
    shadow = china_board_rank.v3_shadow_featured(scored)
    assert [r["ticker"] for r in live["featured"]] == ["INTERESTING.SS", "BORING.SS"]
    assert [r["ticker"] for r in shadow] == ["BORING.SS", "INTERESTING.SS"]
    assert scored[0]["order_mode"] == china_board_rank.ORDER_MODE_INTELLIGENCE
    assert scored[0]["effective_order_basis"] == china_board_rank.INTEL_INTEREST_ORDER
    assert scored[0]["intel_order_active"] is True


def test_one_missing_row_triggers_whole_board_v3_order_not_mixed_scale():
    """B. 99 measured + 1 unavailable → live order == score_rank, not mixed keys.

    The mixed-scale path would let a measured-90 name outrank an uncovered
    high-v3 name because 90 (interest) > 50 (substituted v3). Atomic fallback
    compares both on v3 score instead.
    """
    rows = [_row(f"M{i:02d}.SS", sector=f"S{i}") for i in range(99)]
    rows.append(_row("UNSEEN.SS", sector="Z"))
    fuel_by = {f"M{i:02d}.SS": 0.0 for i in range(99)}
    fuel_by["UNSEEN.SS"] = 1.0
    intel_by = {f"M{i:02d}.SS": _measured(90.0) for i in range(99)}
    intel_by["UNSEEN.SS"] = _unavailable()
    scored = _scored(rows, fuel_by=fuel_by, intel_by=intel_by)
    by_ticker = {r["ticker"]: r for r in scored}
    assert all(r["board_rank"] == r["score_rank"] for r in scored)
    assert by_ticker["UNSEEN.SS"]["board_rank"] == 1
    assert by_ticker["UNSEEN.SS"]["intel_interest_basis"] == "fallback_v3"
    assert by_ticker["M00.SS"]["intel_interest_score"] == 90.0
    assert scored[0]["order_mode"] == china_board_rank.ORDER_MODE_V3_FALLBACK
    # Mixed-scale ranking would have put a measured-90 name first.
    assert by_ticker["M00.SS"]["board_rank"] > 1


def test_featured_and_sector_caps_revert_atomically_to_the_v3_shadow():
    """C. Incomplete coverage: live featured set == v3-shadow featured set."""
    rows = [_row(f"N{i}.SS", sector=f"S{i}") for i in range(5)]
    fuel_by = {f"N{i}.SS": (5 - i) / 10 for i in range(5)}
    intel_by = {f"N{i}.SS": _measured(float(i * 10)) for i in range(4)}
    intel_by["N4.SS"] = _unavailable()
    scored = _scored(rows, fuel_by=fuel_by, intel_by=intel_by)
    live = china_board_rank.partition_board_rows(scored, featured_cap=2, sector_cap=4)
    shadow = china_board_rank.v3_shadow_featured(scored, featured_cap=2, sector_cap=4)
    assert [r["ticker"] for r in live["featured"]] == [r["ticker"] for r in shadow]
    assert [r["ticker"] for r in live["featured"]] == ["N0.SS", "N1.SS"]


def test_measured_zero_is_valid_coverage_and_does_not_trigger_fallback():
    """D. basis=measured, score=0.0 counts as covered."""
    scored = _scored(
        [_row("ZERO.SS", sector="X"), _row("HIGH.SS", sector="Y")],
        fuel_by={"ZERO.SS": 1.0, "HIGH.SS": 0.0},
        intel_by={"ZERO.SS": _measured(0.0), "HIGH.SS": _measured(90.0)},
    )
    assert china_board_rank.intel_coverage_complete(scored)
    assert all(r["intel_interest_basis"] == "measured" for r in scored)
    assert {r["ticker"]: r["intel_interest_score"] for r in scored}["ZERO.SS"] == 0.0
    assert scored[0]["order_mode"] == china_board_rank.ORDER_MODE_INTELLIGENCE
    assert [r["ticker"] for r in sorted(scored, key=lambda r: r["board_rank"])] == [
        "HIGH.SS", "ZERO.SS",
    ]
    live = china_board_rank.partition_board_rows(scored)
    shadow = china_board_rank.v3_shadow_featured(scored)
    assert [r["ticker"] for r in live["featured"]] == ["HIGH.SS", "ZERO.SS"]
    assert [r["ticker"] for r in shadow] == ["ZERO.SS", "HIGH.SS"]


def test_total_intelligence_failure_falls_back_to_v3_with_explicit_provenance():
    """E. All Intelligence unavailable: live order == v3, fallback provenance."""
    scored = _scored(
        [_row(f"T{i}.SS") for i in range(4)],
        fuel_by={f"T{i}.SS": i / 10 for i in range(4)},
    )
    assert all(r["intel_interest_basis"] == "fallback_v3" for r in scored)
    assert all(r["board_rank"] == r["score_rank"] for r in scored)
    assert scored[0]["requested_order_basis"] == china_board_rank.INTEL_INTEREST_ORDER
    assert scored[0]["effective_order_basis"] == china_board_rank.V3_SCORE_ORDER
    assert scored[0]["order_mode"] == china_board_rank.ORDER_MODE_V3_FALLBACK
    assert scored[0]["fallback_reason"] == (
        china_board_rank.FALLBACK_REASON_INCOMPLETE_COVERAGE
    )
    assert scored[0]["intel_order_active"] is False


def test_next_complete_bake_resumes_intelligence_ordering_with_no_sticky_state():
    """F. Partial then complete: the second bake immediately uses intelligence."""
    partial = _scored(
        [_row("A.SS", sector="X"), _row("B.SS", sector="Y")],
        fuel_by={"A.SS": 1.0, "B.SS": 0.0},
        intel_by={"A.SS": _unavailable(), "B.SS": _measured(90.0)},
    )
    assert partial[0]["order_mode"] == china_board_rank.ORDER_MODE_V3_FALLBACK
    complete = _scored(
        [_row("A.SS", sector="X"), _row("B.SS", sector="Y")],
        fuel_by={"A.SS": 1.0, "B.SS": 0.0},
        intel_by={"A.SS": _measured(1.0), "B.SS": _measured(90.0)},
    )
    assert complete[0]["order_mode"] == china_board_rank.ORDER_MODE_INTELLIGENCE
    assert [r["ticker"] for r in sorted(complete, key=lambda r: r["board_rank"])] == [
        "B.SS", "A.SS",
    ]


def test_prophet_score_is_immutable_under_intelligence_and_fallback():
    """G. prophet_score(with intelligence) == prophet_score(without intelligence)."""
    rows = [_row("A.SS"), _row("B.SS")]
    without = _scored(rows)
    with_intel = _scored(
        rows,
        intel_by={"A.SS": _measured(99.0), "B.SS": _unavailable()},
    )
    assert ({r["ticker"]: r["prophet_score"] for r in without}
            == {r["ticker"]: r["prophet_score"] for r in with_intel})


def test_incomplete_coverage_emits_line_start_partial_warning(capsys):
    """Unavailable rows warn. Measured zeros do not."""
    _scored(
        [_row("A.SS"), _row("B.SS")],
        intel_by={"A.SS": _measured(0.0), "B.SS": _unavailable()},
    )
    err = capsys.readouterr()
    out = err.out + err.err
    assert out.startswith("::warning title=cn-prophet-v4-intel-partial::") or (
        "::warning title=cn-prophet-v4-intel-partial::" in out.splitlines()[0]
        if out else False
    )
    lines = [ln for ln in out.splitlines() if ln.startswith("::warning ")]
    assert lines, out
    assert lines[0].startswith("::warning title=cn-prophet-v4-intel-partial::")
    assert "1/2" in lines[0]
    assert "entire board reverted to v3 ordering" in lines[0]


def test_measured_zeros_do_not_emit_coverage_warning(capsys):
    _scored(
        [_row("A.SS"), _row("B.SS")],
        intel_by={"A.SS": _measured(0.0), "B.SS": _measured(0.0)},
    )
    out = capsys.readouterr().out
    assert "::warning title=cn-prophet-v4-intel-partial::" not in out
    assert "cn-prophet-v4-intel-blind" not in out


# ── R4 treatment exclusion ────────────────────────────────────────────────── #

def _featured_episode(scored_rows: list[dict]) -> dict:
    lanes = china_board_rank.partition_board_rows(scored_rows)
    assert lanes["featured"], "fixture produced no featured row"
    row = lanes["featured"][0]
    return {
        "board_definition": row["board_definition"],
        "lane": row["lane"],
        "effective_order_basis": row["effective_order_basis"],
        "order_mode": row["order_mode"],
        "intel_order_active": row["intel_order_active"],
        "intel_coverage_complete": row["intel_coverage_complete"],
    }


def test_complete_coverage_featured_episode_is_r4_treatment_eligible():
    scored = _scored(
        [_row("A.SS", sector="X"), _row("B.SS", sector="Y")],
        intel_by={"A.SS": _measured(10.0), "B.SS": _measured(90.0)},
    )
    episode = _featured_episode(scored)
    assert cn_v3_tripwires.r4_treatment_eligible(episode)
    shadow = china_board_rank.v3_shadow_featured(scored)
    assert shadow
    assert not cn_v3_tripwires.r4_treatment_eligible({
        "board_definition": shadow[0]["board_definition"],
        "lane": "featured",
        "effective_order_basis": china_board_rank.INTEL_INTEREST_ORDER,
    })


def test_fallback_featured_episode_is_not_r4_treatment_eligible():
    scored = _scored(
        [_row("A.SS", sector="X"), _row("B.SS", sector="Y")],
        fuel_by={"A.SS": 1.0, "B.SS": 0.0},
        intel_by={"A.SS": _unavailable(), "B.SS": _measured(90.0)},
    )
    episode = _featured_episode(scored)
    assert episode["board_definition"] == "cn_prophet_v4"
    assert episode["lane"] == "featured"
    assert episode["order_mode"] == china_board_rank.ORDER_MODE_V3_FALLBACK
    assert not cn_v3_tripwires.r4_treatment_eligible(episode)
    # Shadow bookkeeping is intact on the same bake.
    shadow = china_board_rank.v3_shadow_featured(scored)
    assert [r["ticker"] for r in shadow] == [
        r["ticker"] for r in china_board_rank.partition_board_rows(scored)["featured"]
    ]
    assert all(r["board_definition"] == "cn_prophet_v3_shadow" for r in shadow)


def test_returning_to_full_coverage_resumes_r4_treatment_accrual():
    fallback = _scored(
        [_row("A.SS", sector="X"), _row("B.SS", sector="Y")],
        intel_by={"A.SS": _unavailable(), "B.SS": _measured(90.0)},
    )
    recovered = _scored(
        [_row("A.SS", sector="X"), _row("B.SS", sector="Y")],
        intel_by={"A.SS": _measured(1.0), "B.SS": _measured(90.0)},
    )
    assert not cn_v3_tripwires.r4_treatment_eligible(_featured_episode(fallback))
    assert cn_v3_tripwires.r4_treatment_eligible(_featured_episode(recovered))
