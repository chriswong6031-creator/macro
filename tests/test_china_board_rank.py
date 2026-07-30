from __future__ import annotations

import pandas as pd
import pytest

from engine import china_board_rank


ASOF = "2026-07-29"


def _row(
    ticker: str,
    *,
    sector: str = "Industrials",
    stage: str | None = "ENTRY",
    extension_score: float = 0.0,
    extended: bool = False,
    coiled: dict | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "sector": sector,
        "stage": stage,
        "extension": {"score": extension_score, "extended": extended},
        "coiled": coiled or {},
        # These legacy fields are intentionally extreme: neither may affect v2 score.
        "setup": 999.0,
        "alpha": 999.0,
    }


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


def _entry(status: str = "buy_now") -> dict:
    return {"status": status}


def _micro(*, fillable=True, chase=False, as_of: str | None = ASOF) -> dict:
    out = {"fillable": fillable, "chase_veto": {"flag": chase}}
    if as_of is not None:
        out["as_of"] = as_of
    return out


def _score(
    rows: list[dict],
    *,
    verdict_by=None,
    profile_by=None,
    entry_by=None,
    rev_z_by=None,
) -> list[dict]:
    tickers = [row["ticker"] for row in rows]
    return china_board_rank.enrich_and_score_rows(
        rows,
        verdict_by=verdict_by or {ticker: _verdict() for ticker in tickers},
        profile_by=profile_by or {ticker: _profile() for ticker in tickers},
        entry_by=entry_by or {ticker: _entry() for ticker in tickers},
        rev_z_by=rev_z_by or {ticker: float(len(tickers) - i) for i, ticker in enumerate(tickers)},
        micro_by={ticker: _micro() for ticker in tickers},
        liquidity_by={ticker: {"adv_yi": 1.0} for ticker in tickers},
        micro_asof=ASOF,
        board_asof=ASOF,
    )


def test_stock_panel_asof_ignores_later_context_instruments():
    stock = pd.Series(
        [10.0, 10.5],
        index=pd.to_datetime(["2026-07-28", "2026-07-29"]),
    )
    context_etf = pd.Series(
        [3.0, 3.1],
        index=pd.to_datetime(["2026-07-29", "2026-07-30"]),
    )
    universe = [
        ("600001.SS", stock, None, "Stock", "Industrials"),
        ("510300.SS", context_etf, None, "CSI 300 ETF", "Index"),
    ]

    assert china_board_rank.stock_panel_asof(
        universe,
        {"600001.SS"},
    ) == pd.Timestamp("2026-07-29")


def test_signal_freshness_uses_daily_input_receipt_not_3b_bucket_label():
    fresh = _row("FRESH.SS")
    stale = _row("STALE.SS")
    lanes = china_board_rank.build_board_lanes(
        [fresh, stale],
        verdict_by={
            # A 3B indicator bucket may legitimately carry yesterday's label
            # while consuming today's close.
            "FRESH.SS": _verdict(asof="2026-07-28", input_asof=ASOF),
            # Conversely, a convenient bucket label cannot make stale daily
            # input look current.
            "STALE.SS": _verdict(asof=ASOF, input_asof="2026-07-28"),
        },
        profile_by={
            "FRESH.SS": _profile(),
            "STALE.SS": _profile(),
        },
        entry_by={
            "FRESH.SS": _entry(),
            "STALE.SS": _entry(),
        },
        micro_by={
            "FRESH.SS": _micro(),
            "STALE.SS": _micro(),
        },
        liquidity_by={
            "FRESH.SS": {"adv_yi": 1.0},
            "STALE.SS": {"adv_yi": 1.0},
        },
        board_asof=ASOF,
    )

    assert [row["ticker"] for row in lanes["featured"]] == ["FRESH.SS"]
    assert [row["ticker"] for row in lanes["more_actionable"]] == ["STALE.SS"]
    assert "signal_stale" in lanes["more_actionable"][0]["lane_reasons"]


def test_exact_score_math_and_zero_authority_fields():
    rows = [
        _row(
            "BEST.SS",
            extension_score=0.25,
            coiled={"star": True, "coiled": True, "washout_ctx": True},
        ),
        _row("PEER.SS"),
        _row("LOW.SS"),
        _row("LOWER.SS"),
        _row("LOWEST.SS"),
    ]
    scored = _score(
        rows,
        rev_z_by={
            "BEST.SS": 3.0,
            "PEER.SS": 2.0,
            "LOW.SS": 1.0,
            "LOWER.SS": 0.0,
            "LOWEST.SS": -1.0,
        },
    )
    best = next(row for row in scored if row["ticker"] == "BEST.SS")

    # signal 35 + entry 25 + runway 20*(.6*.5 + .4*.75) + bottom 10 + reversal 10
    assert best["prophet_score"] == pytest.approx(92.0)
    assert best["prophet_rank"]["components"]["runway"]["value"] == pytest.approx(0.6)
    assert best["prophet"]["version"] == china_board_rank.BOARD_DEFINITION
    assert best["prophet"]["components"]["runway"] == pytest.approx(0.6)
    assert best["adv_yi"] == pytest.approx(1.0)
    assert best["reversal_member"] is True
    assert best["rev_percentile"] == pytest.approx(1.0)
    assert "setup" in best["prophet_rank"]["zero_score_authority"]
    assert "residual_alpha" in best["prophet_rank"]["zero_score_authority"]

    changed = [dict(row, setup=-999.0, alpha=-999.0) for row in rows]
    changed_best = next(row for row in _score(changed) if row["ticker"] == "BEST.SS")
    assert changed_best["prophet_score"] == best["prophet_score"]


def test_context_etfs_and_indices_cannot_enter_stock_prophet():
    rows = [
        _row("STOCK.SZ", sector="Technology"),
        _row("ETF.SS", sector="Sector ETF"),
        _row("INDEX.SS", sector="Index"),
    ]

    scored = _score(rows)

    assert [row["ticker"] for row in scored] == ["STOCK.SZ"]


def test_future_dated_context_etf_cannot_advance_stock_board_date():
    stock_close = pd.Series(
        [10.0],
        index=pd.to_datetime(["2026-07-29"]),
    )
    future_etf_close = pd.Series(
        [2.0],
        index=pd.to_datetime(["2026-07-30"]),
    )
    universe = [
        ("STOCK.SZ", stock_close, None, "Stock", "Technology"),
        ("ETF.SS", future_etf_close, None, "ETF", "Sector ETF"),
    ]

    panel_asof = china_board_rank.stock_panel_asof(universe, {"STOCK.SZ"})

    assert str(pd.Timestamp(panel_asof).date()) == "2026-07-29"


def test_signal_modifiers_and_entry_status_values_are_deterministic():
    rows = [_row("T3.SS"), _row("T2.SS")]
    scored = _score(
        rows,
        verdict_by={
            "T3.SS": _verdict("T3", provisional=True, ticks=2, bars_to_cross=2),
            "T2.SS": _verdict("T2"),
        },
        entry_by={"T3.SS": _entry("watch"), "T2.SS": _entry("partial")},
        rev_z_by={"T3.SS": 0.0, "T2.SS": 0.0},
    )
    t3 = next(row for row in scored if row["ticker"] == "T3.SS")
    t2 = next(row for row in scored if row["ticker"] == "T2.SS")

    # ((.7 - .1) * .85 * .70) signal, and watch=.4 entry.
    assert t3["prophet_rank"]["components"]["signal"]["value"] == pytest.approx(0.357)
    assert t3["prophet_rank"]["components"]["entry"]["value"] == pytest.approx(0.4)
    assert t2["prophet_rank"]["components"]["signal"]["value"] == pytest.approx(1.0)
    assert t2["prophet_rank"]["components"]["entry"]["value"] == pytest.approx(0.9)
    assert t2["score_rank"] < t3["score_rank"]


def test_reversal_membership_is_deepest_twenty_percent_with_ticker_tiebreak():
    rows = [_row(ticker, sector="A") for ticker in ("A6", "A2", "A1", "A5", "A4", "A3")]
    rev = {"A1": 3.0, "A2": 3.0, "A3": 2.0, "A4": 1.0, "A5": 0.0, "A6": -1.0}
    scored = _score(rows, rev_z_by=rev)
    by_ticker = {row["ticker"]: row for row in scored}

    # The frozen engine convention is rank <= max(1, sector_n // 5).
    # Equal-z names resolve alphabetically, so only A1 is inside the 6-name floor quintile.
    assert {ticker for ticker, row in by_ticker.items() if row["reversal_member"]} == {"A1"}
    assert by_ticker["A1"]["reversal_sector_rank"] == 1
    assert by_ticker["A2"]["reversal_sector_rank"] == 2
    assert by_ticker["A6"]["rev_percentile"] == pytest.approx(0.0)


def test_authoritative_full_universe_reversal_membership_is_not_recomputed():
    rows = [_row("SUBSET_TOP", sector="A"), _row("FULL_MEMBER", sector="A")]
    tickers = [row["ticker"] for row in rows]
    scored = china_board_rank.enrich_and_score_rows(
        rows,
        verdict_by={ticker: _verdict() for ticker in tickers},
        profile_by={ticker: _profile() for ticker in tickers},
        entry_by={ticker: _entry() for ticker in tickers},
        # On this two-row subset SUBSET_TOP would win if the ranker recomputed
        # membership from rev_z. The authoritative full screened universe says
        # only FULL_MEMBER belongs to the deepest quintile.
        rev_z_by={"SUBSET_TOP": 3.0, "FULL_MEMBER": -1.0},
        reversal_by={
            "SUBSET_TOP": {
                "rev_z": 3.0, "ret_3m": -4.0, "sector_rank": 3, "sector_n": 10,
                "deepest_quintile": False,
            },
            "FULL_MEMBER": {
                "rev_z": -1.0, "ret_3m": -18.5, "sector_rank": 2, "sector_n": 10,
                "deepest_quintile": True,
            },
        },
        micro_by={ticker: _micro() for ticker in tickers},
        liquidity_by={ticker: {"adv_yi": 1.0} for ticker in tickers},
        micro_asof=ASOF,
        board_asof=ASOF,
    )
    by_ticker = {row["ticker"]: row for row in scored}
    assert by_ticker["SUBSET_TOP"]["reversal_member"] is False
    assert by_ticker["FULL_MEMBER"]["reversal_member"] is True
    assert by_ticker["FULL_MEMBER"]["ret_3m"] == pytest.approx(-18.5)
    assert by_ticker["FULL_MEMBER"]["reversal_sector_rank"] == 2
    assert by_ticker["FULL_MEMBER"]["reversal_sector_n"] == 10


def test_null_tier_legacy_and_t4_are_forming_not_actionable():
    rows = [_row("LEGACY.SS"), _row("T4.SS")]
    lanes = china_board_rank.build_board_lanes(
        rows,
        verdict_by={"LEGACY.SS": _verdict(None), "T4.SS": _verdict("T4")},
        profile_by={ticker: _profile() for ticker in ("LEGACY.SS", "T4.SS")},
        entry_by={ticker: _entry() for ticker in ("LEGACY.SS", "T4.SS")},
        rev_z_by={"LEGACY.SS": 1.0, "T4.SS": 0.0},
        micro_by={ticker: _micro() for ticker in ("LEGACY.SS", "T4.SS")},
        liquidity_by={ticker: {"adv_yi": 1.0} for ticker in ("LEGACY.SS", "T4.SS")},
        micro_asof=ASOF,
        board_asof=ASOF,
    )

    assert lanes["counts"] == {
        "featured": 0,
        "more_actionable": 0,
        "late_or_unfillable": 0,
        "forming": 2,
    }
    reasons = {row["ticker"]: row["lane_reasons"] for row in lanes["forming"]}
    assert reasons["LEGACY.SS"] == ["no_buyable_tier"]
    assert reasons["T4.SS"] == ["tier_t4_not_actionable"]


def test_execution_and_freshness_route_to_the_correct_lanes():
    tickers = (
        "CLEAR.SS", "SEALED.SS", "CHASE.SS", "MISSING.SS",
        "STALE.SS", "UNDATED.SS", "THIN.SS",
    )
    rows = [_row(ticker) for ticker in tickers]
    micro = {
        "CLEAR.SS": _micro(),
        "SEALED.SS": _micro(fillable=False, chase=True),
        "CHASE.SS": _micro(chase=True),
        # MISSING intentionally absent.
        "STALE.SS": _micro(as_of="2026-07-28"),
        # Yesterday/unknown execution flags may not become today's hard veto.
        "UNDATED.SS": _micro(fillable=False, chase=True, as_of=None),
        "THIN.SS": _micro(),
    }
    scored = china_board_rank.enrich_and_score_rows(
        rows,
        verdict_by={ticker: _verdict() for ticker in tickers},
        profile_by={ticker: _profile() for ticker in tickers},
        entry_by={ticker: _entry() for ticker in tickers},
        rev_z_by={ticker: float(i) for i, ticker in enumerate(tickers)},
        micro_by=micro,
        liquidity_by={
            **{ticker: {"adv_yi": 1.0} for ticker in tickers},
            "THIN.SS": {"adv_yi": 0.49},
        },
        micro_asof=ASOF,
        board_asof=ASOF,
    )
    lanes = china_board_rank.partition_board_rows(scored)

    assert [row["ticker"] for row in lanes["featured"]] == ["CLEAR.SS"]
    assert {row["ticker"] for row in lanes["more_actionable"]} == {
        "MISSING.SS", "STALE.SS", "UNDATED.SS",
    }
    assert {row["ticker"] for row in lanes["late_or_unfillable"]} == {
        "SEALED.SS",
        "CHASE.SS",
        "THIN.SS",
    }
    late_reasons = {
        row["ticker"]: set(row["lane_reasons"])
        for row in lanes["late_or_unfillable"]
    }
    assert {"unfillable", "chase_veto"} <= late_reasons["SEALED.SS"]
    assert late_reasons["CHASE.SS"] == {"chase_veto"}
    assert late_reasons["THIN.SS"] == {"liquidity_below_floor"}


def test_stale_signal_cannot_be_featured_by_fresh_raw_microstructure():
    row = _row("LAGGED.SS")
    scored = china_board_rank.enrich_and_score_rows(
        [row],
        verdict_by={
            "LAGGED.SS": _verdict(
                asof="2026-07-28",
                input_asof="2026-07-28",
            )
        },
        profile_by={"LAGGED.SS": _profile()},
        entry_by={"LAGGED.SS": _entry()},
        rev_z_by={"LAGGED.SS": 1.0},
        micro_by={"LAGGED.SS": _micro(as_of=ASOF)},
        liquidity_by={"LAGGED.SS": {"adv_yi": 1.0}},
        board_asof=ASOF,
    )

    lanes = china_board_rank.partition_board_rows(scored)

    assert lanes["featured"] == []
    assert [row["ticker"] for row in lanes["more_actionable"]] == ["LAGGED.SS"]
    assert "signal_stale" in lanes["more_actionable"][0]["lane_reasons"]
    coverage = china_board_rank.execution_coverage(scored)
    assert coverage["fresh_same_day_signal_count"] == 0
    assert coverage["stale_signal_count"] == 1


def test_execution_coverage_uses_actionable_denominator_and_strict_freshness():
    tickers = (
        "CLEAR.SS",
        "CHASE.SS",
        "UNFILL.SS",
        "INCOMPLETE.SS",
        "MISSING.SS",
        "STALE.SS",
        "FORM.SS",
        "INELIGIBLE.SS",
    )
    rows = [_row(ticker) for ticker in tickers]
    verdicts = {ticker: _verdict() for ticker in tickers}
    verdicts["FORM.SS"] = _verdict(None)
    verdicts["INELIGIBLE.SS"] = {"eligible": False, "tier_cascade": None}
    micro = {
        "CLEAR.SS": _micro(),
        "CHASE.SS": _micro(chase=True),
        "UNFILL.SS": _micro(fillable=False),
        "INCOMPLETE.SS": {"as_of": ASOF, "chase_veto": {"flag": False}},
        # MISSING intentionally absent.
        "STALE.SS": _micro(as_of="2026-07-28"),
        "FORM.SS": _micro(),
        "INELIGIBLE.SS": _micro(),
    }
    scored = china_board_rank.enrich_and_score_rows(
        rows,
        verdict_by=verdicts,
        profile_by={ticker: _profile() for ticker in tickers},
        entry_by={ticker: _entry() for ticker in tickers},
        rev_z_by={ticker: float(i) for i, ticker in enumerate(tickers)},
        micro_by=micro,
        liquidity_by={ticker: {"adv_yi": 1.0} for ticker in tickers},
        micro_asof=ASOF,
        board_asof=ASOF,
    )

    assert china_board_rank.execution_coverage(scored) == {
        "raw_eligible": 7,
        "actionable_t1_t3": 6,
        "fresh_same_day_signal_count": 6,
        "fresh_same_day_signal_rate_pct": 100.0,
        "unknown_signal_date_count": 0,
        "stale_signal_count": 0,
        "fresh_same_day_micro_count": 4,
        "fresh_same_day_micro_rate_pct": 66.7,
        "known_fillability_count": 3,
        "known_fillability_rate_pct": 50.0,
        "clear_count": 1,
        "clear_rate_pct": 16.7,
        "unknown_micro_count": 1,
        "stale_micro_count": 1,
        "fresh_but_incomplete_count": 1,
        "unknown_fillability_count": 3,
    }


def test_execution_coverage_empty_denominator_is_json_safe():
    coverage = china_board_rank.execution_coverage(
        [{"ticker": "FORM.SS", "signal": _verdict(None)}]
    )
    assert coverage["actionable_t1_t3"] == 0
    assert coverage["fresh_same_day_micro_rate_pct"] == 0.0
    assert coverage["known_fillability_rate_pct"] == 0.0
    assert coverage["clear_rate_pct"] == 0.0
    assert all(
        isinstance(value, (int, float)) and value == value
        for value in coverage.values()
    )


def test_reversal_input_coverage_fails_closed_on_date_mismatch():
    rows = _score([_row(f"R{i}.SS") for i in range(6)])
    mapping = {
        row["ticker"]: {"rev_z": 1.0}
        for row in rows
    }

    healthy = china_board_rank.reversal_coverage(
        rows,
        mapping,
        source_asof=ASOF,
        board_asof=ASOF,
    )
    mismatched = china_board_rank.reversal_coverage(
        rows,
        mapping,
        source_asof="2026-07-28",
        board_asof=ASOF,
    )

    assert healthy["actionable_coverage_rate_pct"] == 100.0
    assert healthy["degraded"] is False
    assert mismatched["exact_date"] is False
    assert mismatched["actionable_covered_count"] == 0
    assert mismatched["degraded"] is True


def test_unknown_extension_never_receives_best_case_runway_points():
    known = _row("KNOWN.SS")
    unknown = _row("UNKNOWN.SS")
    unknown.pop("extension")
    kwargs = {
        "verdict_by": {
            "KNOWN.SS": _verdict(),
            "UNKNOWN.SS": _verdict(),
        },
        "profile_by": {
            "KNOWN.SS": _profile(),
            "UNKNOWN.SS": _profile(),
        },
        "entry_by": {
            "KNOWN.SS": _entry(),
            "UNKNOWN.SS": _entry(),
        },
        "micro_by": {
            "KNOWN.SS": _micro(),
            "UNKNOWN.SS": _micro(),
        },
        "liquidity_by": {
            "KNOWN.SS": {"adv_yi": 1.0},
            "UNKNOWN.SS": {"adv_yi": 1.0},
        },
        "board_asof": ASOF,
    }
    scored = {
        row["ticker"]: row
        for row in china_board_rank.enrich_and_score_rows(
            [known, unknown],
            **kwargs,
        )
    }

    assert (
        scored["KNOWN.SS"]["prophet"]["points"]["runway"]
        > scored["UNKNOWN.SS"]["prophet"]["points"]["runway"]
    )
    assert (
        scored["KNOWN.SS"]["prophet"]["points"]["runway"]
        - scored["UNKNOWN.SS"]["prophet"]["points"]["runway"]
        == pytest.approx(8.0)
    )


def test_featured_and_sector_caps_are_lossless():
    rows = []
    for sector in range(7):
        for member in range(5):
            rows.append(_row(f"S{sector}-{member:02}.SS", sector=f"Sector {sector}"))
    tickers = [row["ticker"] for row in rows]
    lanes = china_board_rank.build_board_lanes(
        rows,
        verdict_by={ticker: _verdict() for ticker in tickers},
        profile_by={ticker: _profile() for ticker in tickers},
        entry_by={ticker: _entry() for ticker in tickers},
        rev_z_by={ticker: float(len(tickers) - i) for i, ticker in enumerate(tickers)},
        micro_by={ticker: _micro() for ticker in tickers},
        liquidity_by={ticker: {"adv_yi": 1.0} for ticker in tickers},
        micro_asof=ASOF,
        board_asof=ASOF,
    )

    assert len(lanes["featured"]) == china_board_rank.FEATURED_CAP
    per_sector = {}
    for row in lanes["featured"]:
        per_sector[row["sector"]] = per_sector.get(row["sector"], 0) + 1
    assert max(per_sector.values()) <= china_board_rank.SECTOR_CAP

    every_output = [
        row
        for name in ("featured", "more_actionable", "late_or_unfillable", "forming")
        for row in lanes[name]
    ]
    assert len(every_output) == len(rows)
    assert {row["ticker"] for row in every_output} == set(tickers)
    assert any("sector_cap" in row["lane_reasons"] for row in lanes["more_actionable"])
    assert any("featured_cap" in row["lane_reasons"] for row in lanes["more_actionable"])


def test_partition_is_disjoint_lossless_and_input_order_invariant():
    rows = [
        _row("Z.SS"),
        _row("A.SS"),
        _row("LATE.SS", stage="RAN_LATE"),
        _row("EXT.SS", extended=True),
        _row("FORM.SS"),
    ]
    tickers = [row["ticker"] for row in rows]
    kwargs = {
        "verdict_by": {
            **{ticker: _verdict() for ticker in tickers},
            "FORM.SS": _verdict(None),
        },
        "profile_by": {ticker: _profile() for ticker in tickers},
        "entry_by": {ticker: _entry() for ticker in tickers},
        "rev_z_by": {ticker: 1.0 for ticker in tickers},
        "micro_by": {ticker: _micro() for ticker in tickers},
        "liquidity_by": {ticker: {"adv_yi": 1.0} for ticker in tickers},
        "micro_asof": ASOF,
        "board_asof": ASOF,
    }
    forward = china_board_rank.build_board_lanes(rows, **kwargs)
    reverse = china_board_rank.build_board_lanes(list(reversed(rows)), **kwargs)
    names = ("featured", "more_actionable", "late_or_unfillable", "forming")

    assert {
        name: [row["ticker"] for row in forward[name]]
        for name in names
    } == {
        name: [row["ticker"] for row in reverse[name]]
        for name in names
    }

    all_rows = [row for name in names for row in forward[name]]
    assert len(all_rows) == len(rows)
    assert len({row["ticker"] for row in all_rows}) == len(rows)
    assert all(row["lane"] in names for row in all_rows)
    assert all(row["score_rank"] >= 1 and row["display_rank"] >= 1 for row in all_rows)
