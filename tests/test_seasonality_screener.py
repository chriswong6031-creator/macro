"""W7 — the cross-symbol research browser, and the four refusals that keep it honest.

The tests that matter here are not the happy paths.  This module ships in place
of a screener that cannot exist yet (no point-in-time membership, no matured
forward grades), so the failure mode it guards against is not a wrong number —
it is a payload that READS like the calibrated screener:

* ``test_generic_interval_label_raises`` — an untyped uncertainty label is the
  cheapest way to turn a parameter CI into something a reader takes as a
  forecast range.  It must raise, not warn.
* ``test_no_fused_ranking_symbol_exists`` — greps the module namespace for the
  function this PR is defined by NOT having.  A later session adding
  ``top_patterns()`` would otherwise pass every other test in this file.
* ``test_machine_authority_consumer_refused_by_name`` — Synapse declares no
  machine consumer for this artifact, so a Neural Web or Prophet score path
  asking for it is a wiring mistake that must fail loudly and by name.
* ``test_user_filter_strips_inherited_claim`` — a cohort the reader composes
  spends budget nothing counted.  Carrying the unfiltered family's p-value into
  it is exactly how a browse becomes an unearned claim.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.seasonality import screener  # noqa: E402

ASOF = date(2026, 8, 6)


# --- fixtures / builders ----------------------------------------------------


def _multiplicity() -> dict:
    return screener.program_multiplicity(
        symbols_searched=180,
        windows_per_symbol=2645,
        family_id="calendar_windows_v1",
        correction="joint_max_t_westfall_young",
    )


def _costs() -> dict:
    return screener.costs_disclosure(
        round_trip_cost_bps=18.0,
        borrow_cost_included=False,
        slippage_model="static_bps_assumption",
        applied_to_estimate=False,
    )


def _freshness() -> dict:
    return screener.freshness_disclosure(artifact_asof=date(2026, 8, 5), asof=ASOF)


def _descriptive(
    symbol: str = "ABCD",
    *,
    row_id: str | None = None,
    up_years: int = 17,
    n_years: int = 23,
    start: int = 40,
    end: int = 70,
    baseline: float = 0.52,
    p_value: float = 0.21,
) -> screener.ResearchRow:
    return screener.descriptive_row(
        row_id=row_id or f"{symbol}:{start}-{end}",
        symbol=symbol,
        window_start_doy=start,
        window_end_doy=end,
        up_years=up_years,
        n_years=n_years,
        baseline_up_share=baseline,
        issuer_count=1,
        date_cluster_count=n_years,
        search_family="calendar_windows_v1",
        family_size=2645,
        multiplicity=_multiplicity(),
        family_adjusted_p_value=p_value,
        evidence_label="descriptive_only_no_forward_record",
        costs=_costs(),
        freshness=_freshness(),
    )


def _calibrated(symbol: str = "WXYZ") -> screener.ResearchRow:
    """A calibrated row is constructible in principle — nothing on this tier makes one."""
    return screener.build_row(
        row_id=f"{symbol}:calibrated",
        symbol=symbol,
        window_start_doy=40,
        window_end_doy=70,
        estimate_type=screener.ESTIMATE_CALIBRATED,
        calibrated_probability=0.61,
        calibrated_probability_baseline=0.5,
        calibrated_probability_edge=0.11,
        calibration_reference="oos_epoch:2027h1_walk_forward",
        uncertainty_semantics="predictive_interval",
        uncertainty_low=0.44,
        uncertainty_high=0.78,
        uncertainty_level=0.90,
        sample_size=140,
        issuer_count=1,
        date_cluster_count=140,
        search_family="calendar_windows_v1",
        family_size=2645,
        multiplicity=_multiplicity(),
        family_adjusted_p_value=0.02,
        evidence_label="graded_out_of_sample",
        costs=_costs(),
        oos_epoch="2027h1_walk_forward",
        freshness=_freshness(),
        extrapolation=False,
    )


# --- the honesty line -------------------------------------------------------


class TestNotACalibratedScreener:
    def test_module_declares_research_tier(self):
        assert screener.TIER == "research"
        assert screener.IS_CALIBRATED_SCREENER is False
        assert "not a calibrated screener" in screener.NOT_CALIBRATED_REASON
        assert screener.NOT_CALIBRATED_BLOCKERS  # the reason names the two blockers

    def test_every_row_declares_it(self):
        row = _descriptive().as_dict()
        assert row["tier"] == "research"
        assert row["is_calibrated_screener"] is False

    def test_result_set_declares_it_with_a_plain_word_reason(self):
        payload = screener.build_result_set(
            asof=ASOF,
            rows=[_descriptive()],
            consumer="human_research_browser",
            multiplicity=_multiplicity(),
            universe=screener.resolve_universe(ASOF),
        )
        assert payload["tier"] == "research"
        assert payload["is_calibrated_screener"] is False
        assert "does not forecast" in payload["not_calibrated_reason"]
        assert "forward_ledger_has_zero_matured_grades" in payload["not_calibrated_blockers"]

    def test_a_mutated_tier_declaration_is_refused_not_served(self, monkeypatch):
        # `TIER` and `IS_CALIBRATED_SCREENER` are read at CALL time by the result
        # set builder and by the API envelope, while every ROW compares against a
        # `False` literal and is immune. Reassigning the globals therefore used to
        # flip the artifact-level flag a consumer branches on while the rows kept
        # saying `research` / `False` — a payload contradicting itself.
        rows = [_descriptive()]
        universe = screener.resolve_universe(ASOF)
        monkeypatch.setattr(screener, "IS_CALIBRATED_SCREENER", True)
        with pytest.raises(screener.TierDeclarationError, match="contradicts its own rows"):
            screener.assert_research_tier_intact()
        with pytest.raises(screener.TierDeclarationError):
            screener.build_result_set(
                asof=ASOF,
                rows=rows,
                consumer="human_research_browser",
                multiplicity=_multiplicity(),
                universe=universe,
            )

    def test_a_mutated_tier_string_is_refused_too(self, monkeypatch):
        # Rows are built BEFORE the flip on purpose: a row's own `tier` default is
        # bound at class-definition time, so it fails closed by itself. The hole
        # was the artifact-level flag, which is read at call time.
        rows = [_descriptive()]
        universe = screener.resolve_universe(ASOF)
        monkeypatch.setattr(screener, "TIER", "production")
        with pytest.raises(screener.TierDeclarationError):
            screener.build_result_set(
                asof=ASOF,
                rows=rows,
                consumer="human_research_browser",
                multiplicity=_multiplicity(),
                universe=universe,
            )

    def test_a_result_set_may_not_carry_calibrated_rows(self):
        # `counts.estimate_types` saying "calibrated" inside an artifact whose
        # envelope says `is_calibrated_screener: False` is the same self-
        # contradiction, one level down. Nothing on this tier can mint a graded
        # epoch, so a calibrated row here is a wiring mistake.
        with pytest.raises(screener.ScreenerError, match="may not carry calibrated rows"):
            screener.build_result_set(
                asof=ASOF,
                rows=[_calibrated()],
                consumer="human_research_browser",
                multiplicity=_multiplicity(),
                universe=screener.resolve_universe(ASOF),
            )

    def test_row_may_not_claim_a_higher_tier(self):
        with pytest.raises(screener.ScreenerError):
            screener.ResearchRow(
                row_id="x",
                symbol="ABCD",
                window_start_doy=1,
                window_end_doy=2,
                estimate_type=screener.ESTIMATE_DESCRIPTIVE,
                abstained=True,
                abstention_reason="test",
                tier="display",
            )


class TestDescriptiveAndCalibratedNeverMix:
    def test_legs_are_separately_named_fields(self):
        assert not set(screener.DESCRIPTIVE_FIELDS) & set(screener.CALIBRATED_FIELDS)
        row = _descriptive().as_dict()
        assert row["historical_up_share"] is not None
        for name in screener.CALIBRATED_FIELDS:
            assert row[name] is None

    def test_descriptive_row_may_not_fill_a_calibrated_field(self):
        with pytest.raises(screener.ScreenerError, match="separately named"):
            screener.build_row(
                row_id="x",
                symbol="ABCD",
                window_start_doy=40,
                window_end_doy=70,
                estimate_type=screener.ESTIMATE_DESCRIPTIVE,
                calibrated_probability=0.7,
                abstained=True,
                abstention_reason="test",
            )

    def test_calibrated_row_must_name_a_graded_epoch(self):
        with pytest.raises(screener.ScreenerError, match="graded out-of-sample"):
            screener.build_row(
                row_id="x",
                symbol="ABCD",
                window_start_doy=40,
                window_end_doy=70,
                estimate_type=screener.ESTIMATE_CALIBRATED,
                calibrated_probability=0.7,
                abstained=True,
                abstention_reason="test",
            )

    def test_mixed_rows_cannot_share_one_score_axis(self):
        rows = [_descriptive(), _calibrated()]
        with pytest.raises(screener.MixedEstimateAxisError, match="different questions"):
            screener.order_rows(rows, sort_by="historical_up_share")
        with pytest.raises(screener.MixedEstimateAxisError):
            screener.order_rows(rows, sort_by="calibrated_probability")

    def test_a_calibration_reference_must_name_the_declared_epoch(self):
        # `calibration_reference` used to be truthiness-checked only and
        # `oos_epoch` was a free string, so a historical up-share could be served
        # under `calibrated_probability` with `calibration_reference="trust_me"`.
        fields = {
            **_calibrated().as_dict(),
            "calibration_reference": "trust_me_bro",
            "oos_epoch": "oos_2018_2025_graded",
        }
        with pytest.raises(screener.ScreenerError, match="does not name"):
            screener.build_row(**fields)

    def test_a_calibrated_row_may_not_declare_the_null_epoch(self):
        fields = {**_calibrated().as_dict(), "oos_epoch": screener.OOS_EPOCH_NONE}
        with pytest.raises(screener.ScreenerError, match="not a calibration"):
            screener.build_row(**fields)

    def test_grouping_is_the_supported_way_to_show_both(self):
        grouped = screener.group_by_estimate_type([_descriptive(), _calibrated()])
        assert len(grouped["descriptive"]) == 1
        assert len(grouped["calibrated"]) == 1
        # Sorting WITHIN a group is fine — one kind of number, one axis.
        assert screener.order_rows(grouped["descriptive"], sort_by="historical_up_share")


# --- refusal 1: a generic uncertainty label ---------------------------------


class TestTypedUncertainty:
    def test_generic_interval_label_raises(self):
        with pytest.raises(screener.UncertaintySemanticsError, match="generic uncertainty label"):
            screener.assert_uncertainty_semantics("interval")

    @pytest.mark.parametrize("label", ["interval", "CI", "confidence_interval", "band", "range", "uncertainty"])
    def test_every_generic_label_raises(self, label):
        with pytest.raises(screener.UncertaintySemanticsError):
            screener.assert_uncertainty_semantics(label)

    @pytest.mark.parametrize("label", screener.UNCERTAINTY_SEMANTICS)
    def test_the_three_typed_semantics_are_accepted(self, label):
        assert screener.assert_uncertainty_semantics(label) == label

    def test_a_row_with_a_generic_label_raises_even_when_abstaining(self):
        # A generic label is a SCHEMA defect, not a data gap: abstaining must not
        # let it through, or the untyped field ships on every incomplete row.
        with pytest.raises(screener.UncertaintySemanticsError):
            screener.build_row(
                row_id="x",
                symbol="ABCD",
                window_start_doy=40,
                window_end_doy=70,
                estimate_type=screener.ESTIMATE_DESCRIPTIVE,
                uncertainty_semantics="interval",
            )

    def test_wilson_is_labelled_a_parameter_ci(self):
        row = _descriptive()
        assert row.uncertainty_semantics == "parameter_ci"
        assert row.uncertainty_low <= row.historical_up_share <= row.uncertainty_high

    def test_wilson_interval_narrows_with_sample_size(self):
        wide = screener.wilson_interval(7, 10)
        narrow = screener.wilson_interval(70, 100)
        assert (wide[1] - wide[0]) > (narrow[1] - narrow[0])
        assert 0.0 <= narrow[0] <= 0.7 <= narrow[1] <= 1.0

    def test_wilson_refuses_an_empty_sample(self):
        with pytest.raises(screener.ScreenerError):
            screener.wilson_interval(0, 0)


# --- every row exposes all of it, or abstains -------------------------------


class TestDisclosureOrAbstain:
    def test_a_complete_row_exposes_every_disclosure(self):
        row = _descriptive().as_dict()
        for name in screener.COMMON_REQUIRED_FIELDS + screener.CLAIM_FIELDS:
            assert row[name] is not None, name
        for name in screener.DESCRIPTIVE_FIELDS:
            assert row[name] is not None, name
        assert row["abstained"] is False

    @pytest.mark.parametrize(
        "dropped", ["issuer_count", "date_cluster_count", "costs", "oos_epoch", "freshness", "family_size"]
    )
    def test_a_missing_disclosure_abstains_and_names_itself(self, dropped):
        kwargs = dict(
            row_id="ABCD:40-70",
            symbol="ABCD",
            window_start_doy=40,
            window_end_doy=70,
            estimate_type=screener.ESTIMATE_DESCRIPTIVE,
            historical_up_share=0.74,
            historical_up_share_baseline=0.52,
            historical_up_share_edge=0.22,
            uncertainty_semantics="parameter_ci",
            uncertainty_low=0.55,
            uncertainty_high=0.87,
            uncertainty_level=0.9,
            sample_size=23,
            issuer_count=1,
            date_cluster_count=23,
            search_family="calendar_windows_v1",
            family_size=2645,
            multiplicity=_multiplicity(),
            family_adjusted_p_value=0.21,
            evidence_label="descriptive_only_no_forward_record",
            costs=_costs(),
            oos_epoch=screener.OOS_EPOCH_NONE,
            freshness=_freshness(),
            extrapolation=False,
        )
        kwargs.pop(dropped)
        row = screener.build_row(**kwargs)
        assert row.abstained is True
        assert dropped in row.abstention_reason
        # The field is still PRESENT in the payload, just empty — an omitted key
        # is how a reader stops noticing that the disclosure was never supplied.
        assert dropped in row.as_dict()

    @pytest.mark.parametrize(
        "blank", ["evidence_label", "search_family", "oos_epoch", "multiplicity"]
    )
    def test_an_empty_disclosure_is_an_absence_not_a_value(self, blank):
        # Completeness tested `is None`, so `evidence_label=""` and
        # `multiplicity={}` counted as disclosure supplied.
        empty = {} if blank == "multiplicity" else ""
        row = screener.build_row(**{**_descriptive().as_dict(), blank: empty})
        assert row.abstained is True
        assert blank in row.abstention_reason

    @pytest.mark.parametrize(
        "label",
        ["validated", "已验证", "STRONG BUY", "tradeable_edge", "high_conviction", "descriptive"],
    )
    def test_an_unvetted_evidence_label_is_refused(self, label):
        # `evidence_label` is a claim in one word. The site-side CI guard on the
        # word "validated" scans templates and never sees an API body, so this
        # surface is the only place that can refuse it.
        with pytest.raises(screener.ScreenerError):
            screener.build_row(**{**_descriptive().as_dict(), "evidence_label": label})

    def test_an_empty_evidence_label_does_not_pass_as_disclosure(self):
        row = screener.build_row(**{**_descriptive().as_dict(), "evidence_label": ""})
        assert row.abstained is True
        assert "evidence_label" in row.abstention_reason

    @pytest.mark.parametrize("label", screener.DESCRIPTIVE_EVIDENCE_LABELS)
    def test_the_descriptive_labels_are_accepted(self, label):
        assert screener.assert_evidence_label(label, screener.ESTIMATE_DESCRIPTIVE) == label

    def test_a_label_may_not_cross_legs(self):
        with pytest.raises(screener.ScreenerError, match="other estimate leg"):
            screener.assert_evidence_label(
                "graded_out_of_sample", screener.ESTIMATE_DESCRIPTIVE
            )

    def test_a_row_cannot_be_complete_and_incomplete(self):
        with pytest.raises(screener.ScreenerError, match="did not abstain"):
            screener.ResearchRow(
                row_id="x",
                symbol="ABCD",
                window_start_doy=40,
                window_end_doy=70,
                estimate_type=screener.ESTIMATE_DESCRIPTIVE,
                historical_up_share=0.74,
            )

    def test_extrapolation_must_say_what_it_extrapolated(self):
        with pytest.raises(screener.ScreenerError, match="extrapolat"):
            screener.build_row(
                row_id="ABCD:40-70",
                symbol="ABCD",
                window_start_doy=40,
                window_end_doy=70,
                estimate_type=screener.ESTIMATE_DESCRIPTIVE,
                historical_up_share=0.74,
                historical_up_share_baseline=0.52,
                historical_up_share_edge=0.22,
                uncertainty_semantics="parameter_ci",
                uncertainty_low=0.55,
                uncertainty_high=0.87,
                uncertainty_level=0.9,
                sample_size=23,
                issuer_count=1,
                date_cluster_count=23,
                search_family="calendar_windows_v1",
                family_size=2645,
                multiplicity=_multiplicity(),
                family_adjusted_p_value=0.21,
                evidence_label="descriptive_only_no_forward_record",
                costs=_costs(),
                oos_epoch=screener.OOS_EPOCH_NONE,
                freshness=_freshness(),
                extrapolation=True,
            )


# --- refusal 2: sorting is the reader's, ranking is nobody's ----------------


class TestSortingIsNotRanking:
    def test_non_allowlisted_sort_by_raises(self):
        with pytest.raises(screener.SortKeyError, match="not sortable"):
            screener.order_rows([_descriptive()], sort_by="edge_score")

    def test_the_allowlist_is_explicit_and_carries_no_composite(self):
        joined = " ".join(screener.SORTABLE_COLUMNS)
        # "edge" belongs on this list: an edge is `share - baseline`, a DERIVED
        # fused quantity, and the roll-call in FORBIDDEN_RANKING_SYMBOLS only ever
        # looked for a fused ranker spelled as a FUNCTION.
        for banned in ("score", "rank", "conviction", "composite", "best", "edge"):
            assert banned not in joined

    def test_a_fused_edge_is_disclosed_but_never_a_sort_axis(self):
        # `order_rows(sort_by="*_edge", descending=True)` composed with a page size
        # IS top-N-by-fused-metric — the function this module is defined by not
        # having, assembled out of two permitted primitives. The edge still ships
        # on every row; it is simply not an axis.
        row = _descriptive().as_dict()
        for column in screener.FUSED_DISCLOSURE_ONLY_COLUMNS:
            assert column in row, column
            assert column not in screener.SORTABLE_COLUMNS, column
        assert row["historical_up_share_edge"] is not None
        assert not set(screener.SORTABLE_COLUMNS) & screener.FUSED_DISCLOSURE_ONLY_COLUMNS
        with pytest.raises(screener.SortKeyError, match="not sortable"):
            screener.order_rows([_descriptive()], sort_by="historical_up_share_edge")
        with pytest.raises(screener.SortKeyError):
            screener.order_rows([_descriptive()], sort_by="calibrated_probability_edge")

    def test_an_edge_carries_no_interval_of_its_own(self):
        # The published bounds are Wilson bounds on the SHARE. A UI pairing "the
        # sortable number" with "the interval" would mis-plot the edge by exactly
        # the baseline — which is why the edge is not sortable.
        row = _descriptive()
        assert row.uncertainty_low <= row.historical_up_share <= row.uncertainty_high
        assert row.historical_up_share_edge == pytest.approx(
            row.historical_up_share - row.historical_up_share_baseline, abs=1e-6
        )
        assert not (row.uncertainty_low <= row.historical_up_share_edge <= row.uncertainty_high)

    def test_sorting_a_rate_discloses_that_it_is_not_sample_weighted(self):
        # A one-of-one row can sit above an eighteen-of-twenty-five one. There is
        # no sample floor here on purpose (a floor is a promotion gate, not a
        # browse gate) — so the payload says it out loud instead.
        payload = screener.build_result_set(
            asof=ASOF,
            rows=[_descriptive("AAAA", up_years=1, n_years=1), _descriptive("BBBB")],
            consumer="human_research_browser",
            multiplicity=_multiplicity(),
            universe=screener.resolve_universe(ASOF),
            sort_by="historical_up_share",
            descending=True,
        )
        disclosure = payload["ordering"]["sample_disclosure"]
        assert disclosure["sample_weighted"] is False
        assert disclosure["min_sample_size"] == 1
        assert disclosure["max_sample_size"] == 23
        assert "one complete year" in disclosure["note"]
        # ...and no such block when the reader sorted by something that is not a rate.
        plain = screener.build_result_set(
            asof=ASOF,
            rows=[_descriptive()],
            consumer="human_research_browser",
            multiplicity=_multiplicity(),
            universe=screener.resolve_universe(ASOF),
            sort_by="symbol",
        )
        assert plain["ordering"]["sample_disclosure"] is None

    def test_the_other_legs_column_is_refused_not_silently_no_opped(self):
        # A calibrated column over an all-descriptive set resolves to None on
        # every row: the sort did nothing while `ordering.meaning` reported
        # `user_selected_column_sort`, and an unchanged order reads as flat data.
        rows = [_descriptive("AAAA", up_years=20), _descriptive("BBBB", up_years=5)]
        with pytest.raises(screener.MixedEstimateAxisError, match="empty on every row"):
            screener.order_rows(rows, sort_by="calibrated_probability", descending=True)
        with pytest.raises(screener.MixedEstimateAxisError):
            screener.order_rows([_calibrated()], sort_by="historical_up_share")

    def test_the_payload_names_the_columns_that_can_actually_sort(self):
        payload = screener.build_result_set(
            asof=ASOF,
            rows=[_descriptive()],
            consumer="human_research_browser",
            multiplicity=_multiplicity(),
            universe=screener.resolve_universe(ASOF),
        )
        ordering = payload["ordering"]
        assert ordering["sortable_columns"] == list(screener.SORTABLE_COLUMNS)
        applicable = ordering["sortable_columns_applicable"]
        for column in screener.CALIBRATED_FIELDS:
            assert column not in applicable, column
        assert "historical_up_share" in applicable
        assert ordering["disclosure_only_columns"] == sorted(
            screener.FUSED_DISCLOSURE_ONLY_COLUMNS
        )

    def test_nan_sorts_last_like_a_missing_value(self):
        # NaN compares False against everything, so it neither sorts nor raises:
        # the page is deterministic (the identity pre-sort fixes that) but NOT
        # monotonic — wrong while looking right.
        # The NaN row sorts FIRST by identity on purpose: an unguarded NaN simply
        # stays where the pre-sort left it, so a NaN that started last would look
        # handled. This one has to travel to the end.
        broken = screener.build_row(
            **{**_descriptive("AAAA").as_dict(), "historical_up_share": float("nan")}
        )
        rows = [broken, _descriptive("BBBB", up_years=20), _descriptive("CCCC", up_years=5)]
        for descending in (False, True):
            ordered = screener.order_rows(
                rows, sort_by="historical_up_share", descending=descending
            )
            assert ordered[-1].symbol == "AAAA", descending
            values = [
                row.historical_up_share
                for row in ordered
                if row.historical_up_share == row.historical_up_share
            ]
            assert values == sorted(values, reverse=descending)

    def test_there_is_no_default_best_ordering(self):
        assert screener.DEFAULT_SORT_BY is None
        rows = [_descriptive("BBBB", up_years=20), _descriptive("AAAA", up_years=5)]
        ordered = screener.order_rows(rows)
        assert [row.symbol for row in ordered] == ["AAAA", "BBBB"]  # identity, not merit
        payload = screener.build_result_set(
            asof=ASOF,
            rows=rows,
            consumer="human_research_browser",
            multiplicity=_multiplicity(),
            universe=screener.resolve_universe(ASOF),
        )
        assert payload["ordering"]["sort_by"] is None
        assert payload["ordering"]["is_engine_ranking"] is False
        assert payload["ordering"]["meaning"] == screener.IDENTITY_ORDER_LABEL

    def test_no_fused_ranking_symbol_exists(self):
        for name in screener.FORBIDDEN_RANKING_SYMBOLS:
            assert not hasattr(screener, name), f"{name!r} must not exist in this module"

    def test_no_callable_is_named_like_a_ranker(self):
        # The literal FORBIDDEN_RANKING_SYMBOLS list above is a fixed roll-call;
        # this is the open-ended version, so a differently-spelled fused ranker
        # (`best_windows_for`, `score_panel`, ...) cannot slip past it. Exception
        # classes are exempt: a refusal named *Error is the opposite of a ranker.
        pattern = re.compile(r"(^|_)(top|best|rank|score|conviction|screen)")
        offenders = [
            name
            for name in dir(screener)
            if not name.startswith("_")
            and callable(value := getattr(screener, name))
            and not (isinstance(value, type) and issubclass(value, BaseException))
            and pattern.search(name.lower())
        ]
        assert offenders == []

    def test_every_sortable_column_actually_resolves(self):
        # A column on the allowlist that resolves to None for every row sorts
        # NOTHING while looking like it sorted — the reader sees an unchanged
        # order and concludes the data is flat. Each leg's own columns must
        # resolve on a complete row of that leg.
        descriptive = _descriptive()
        for column in screener.SORTABLE_COLUMNS:
            if column in screener.CALIBRATED_FIELDS:
                continue
            assert getattr(descriptive, column, None) is not None, column

        calibrated = _calibrated()
        for column in screener.SORTABLE_COLUMNS:
            if column in screener.DESCRIPTIVE_FIELDS:
                continue
            assert getattr(calibrated, column, None) is not None, column

    def test_sorting_by_a_projected_column_orders_the_rows(self):
        cheap = _descriptive("AAAA")
        pricey = screener.build_row(
            **{
                **_descriptive("BBBB").as_dict(),
                "costs": screener.costs_disclosure(
                    round_trip_cost_bps=95.0,
                    borrow_cost_included=True,
                    slippage_model="static_bps_assumption",
                    applied_to_estimate=False,
                ),
            }
        )
        ordered = screener.order_rows([pricey, cheap], sort_by="round_trip_cost_bps")
        assert [row.symbol for row in ordered] == ["AAAA", "BBBB"]

    def test_user_sort_is_deterministic_and_repeatable(self):
        rows = [
            _descriptive("CCCC", up_years=12),
            _descriptive("AAAA", up_years=20),
            _descriptive("BBBB", up_years=20),
        ]
        first = screener.order_rows(rows, sort_by="historical_up_share", descending=True)
        second = screener.order_rows(list(reversed(rows)), sort_by="historical_up_share", descending=True)
        assert [row.identity for row in first] == [row.identity for row in second]
        # Ties break on identity, never on arrival order.
        assert [row.symbol for row in first] == ["AAAA", "BBBB", "CCCC"]

    def test_abstaining_rows_sort_last_in_both_directions(self):
        good = _descriptive("AAAA", up_years=20)
        blank = screener.build_row(
            row_id="ZZZZ:40-70",
            symbol="ZZZZ",
            window_start_doy=40,
            window_end_doy=70,
            estimate_type=screener.ESTIMATE_DESCRIPTIVE,
        )
        assert blank.abstained is True
        for descending in (False, True):
            ordered = screener.order_rows([blank, good], sort_by="historical_up_share", descending=descending)
            assert ordered[-1].symbol == "ZZZZ"

    def test_rows_without_a_unique_identity_refuse_to_order(self):
        row = _descriptive()
        with pytest.raises(screener.DeterminismError, match="pagination cannot be stable"):
            screener.order_rows([row, row])


# --- refusal 3: machine authority -------------------------------------------


class TestMachineAuthorityRefusal:
    @pytest.mark.parametrize(
        "consumer",
        [
            "neuralweb.state_consumer",
            "neural_web_score_consumer",
            "prophet_board_ranker",
            "prophet.overlay",
            "synapse_bus",
            "conviction_engine",
            "position_sizing_service",
        ],
    )
    def test_machine_authority_consumer_refused_by_name(self, consumer):
        with pytest.raises(screener.MachineAuthorityRefused) as excinfo:
            screener.assert_consumer_permitted(consumer)
        message = str(excinfo.value)
        assert screener.MACHINE_AUTHORITY_REFUSAL in message
        assert consumer in message  # refused BY NAME, not merely refused
        assert "Synapse declares no machine consumer" in message

    @pytest.mark.parametrize(
        "consumer",
        [
            "NeuralWeb.state_consumer",
            "Prophet-Board-Ranker",
            "PROPHET_OVERLAY",
            "SYNAPSE_BUS",
            "neural web ingest",
            "Risk Engine",
            "portfolio-optimizer",
            "alpha_model_v2",
            "backtester",
            "auto_trader",
        ],
    )
    def test_the_identity_fold_is_what_makes_the_refusal_by_name(self, consumer):
        # Every case in the roll-call above is already lowercase-and-underscore,
        # so deleting the fold at `screener.py` silently downgraded these callers
        # from a BY-NAME refusal to the anonymous "unknown consumer" bucket —
        # still refused, but the log stops saying which system asked, which is the
        # whole point of the rule.
        with pytest.raises(screener.MachineAuthorityRefused) as excinfo:
            screener.assert_consumer_permitted(consumer)
        message = str(excinfo.value)
        assert screener.MACHINE_AUTHORITY_REFUSAL in message
        assert consumer in message

    def test_no_machine_authority_token_is_dead_weight(self):
        # A hyphenated duplicate of an underscored token can never match anything
        # the underscored one does not — it reads as coverage that does not exist.
        folded = [token.replace("-", "_") for token in screener.MACHINE_AUTHORITY_TOKENS]
        assert len(set(folded)) == len(folded)
        for index, token in enumerate(folded):
            others = folded[:index] + folded[index + 1 :]
            assert not any(other in token and other != token for other in others), token

    @pytest.mark.parametrize(
        "consumer", ["  api_research_browser  ", "api_research_browser\n", "api_research browser"]
    )
    def test_a_whitespace_bearing_identity_is_refused_not_trimmed(self, consumer):
        # Trimming normalised a padded identity into a permitted one, and the
        # newline-bearing form then travelled verbatim into the `consumer` payload
        # field and every log line, where a newline forges a log record. The
        # message is pinned, not just the refusal: an identity refused as merely
        # "not on the allowlist" sends the reader hunting for a missing entry.
        with pytest.raises(screener.MachineAuthorityRefused) as excinfo:
            screener.assert_consumer_permitted(consumer)
        message = str(excinfo.value)
        assert screener.UNKNOWN_CONSUMER_REFUSAL in message
        assert "carries whitespace" in message

    def test_unknown_consumer_fails_closed(self):
        with pytest.raises(screener.MachineAuthorityRefused) as excinfo:
            screener.assert_consumer_permitted("some_new_service")
        assert screener.UNKNOWN_CONSUMER_REFUSAL in str(excinfo.value)

    def test_missing_consumer_fails_closed(self):
        with pytest.raises(screener.MachineAuthorityRefused):
            screener.assert_consumer_permitted(None)
        with pytest.raises(screener.MachineAuthorityRefused):
            screener.assert_consumer_permitted("  ")

    @pytest.mark.parametrize("consumer", sorted(screener.PERMITTED_CONSUMERS))
    def test_research_consumers_are_permitted(self, consumer):
        assert screener.assert_consumer_permitted(consumer) == consumer

    def test_result_set_refuses_a_machine_consumer(self):
        with pytest.raises(screener.MachineAuthorityRefused):
            screener.build_result_set(
                asof=ASOF,
                rows=[_descriptive()],
                consumer="prophet_score_consumer",
                multiplicity=_multiplicity(),
                universe=screener.resolve_universe(ASOF),
            )


# --- refusal 4: a user-composed cut inherits nothing ------------------------


class TestGlobalSelectionAccounting:
    def test_result_set_carries_the_program_level_budget(self):
        payload = screener.build_result_set(
            asof=ASOF,
            rows=[_descriptive()],
            consumer="human_research_browser",
            multiplicity=_multiplicity(),
            universe=screener.resolve_universe(ASOF),
        )
        block = payload["multiplicity"]
        assert block["scope"] == "program_level"
        assert block["hypotheses_total"] == 180 * 2645
        assert block["across_symbol_correction"].startswith("disclosed_as_program_level_rate")

    def test_a_result_set_without_a_program_budget_is_refused(self):
        with pytest.raises(screener.ScreenerError, match="program-level multiplicity"):
            screener.build_result_set(
                asof=ASOF,
                rows=[_descriptive()],
                consumer="human_research_browser",
                multiplicity={"scope": "per_symbol"},
                universe=screener.resolve_universe(ASOF),
            )

    @pytest.mark.parametrize(
        "forged",
        [
            {"scope": "program_level"},
            {"scope": "program_level", "note": "no correction applied"},
            {
                "scope": "program_level",
                "family_id": "calendar_v1",
                "symbols_searched": 0,
                "windows_per_symbol": 0,
                "hypotheses_total": 0,
                "across_symbol_correction": "none",
            },
            {
                "scope": "program_level",
                "family_id": "calendar_v1",
                "symbols_searched": 2,
                "windows_per_symbol": 3,
                "hypotheses_total": 6000,
                "across_symbol_correction": "none",
            },
        ],
    )
    def test_a_program_budget_reducible_to_a_scope_string_is_refused(self, forged):
        # The refusal used to check ONE key: `scope == "program_level"`. A block
        # with no counts in it, or counts that do not multiply, disclosed a
        # zero-hypothesis search and was served verbatim as the module's central
        # epistemic promise.
        with pytest.raises(screener.ScreenerError):
            screener.build_result_set(
                asof=ASOF,
                rows=[_descriptive()],
                consumer="human_research_browser",
                multiplicity=forged,
                universe=screener.resolve_universe(ASOF),
            )

    def test_a_program_budget_may_not_understate_the_symbols_it_is_showing(self):
        # Understating is the only direction that flatters the result: a 50-symbol
        # set disclosing `symbols_searched=1` prices a 132,250-hypothesis search
        # as a 2,645-hypothesis one.
        rows = [_descriptive(f"SYM{index:03d}") for index in range(12)]
        narrow = screener.program_multiplicity(
            symbols_searched=3,
            windows_per_symbol=2645,
            family_id="calendar_windows_v1",
            correction="joint_max_t_westfall_young",
        )
        with pytest.raises(screener.ScreenerError, match="understates the search"):
            screener.build_result_set(
                asof=ASOF,
                rows=rows,
                consumer="human_research_browser",
                multiplicity=narrow,
                universe=screener.resolve_universe(ASOF),
            )

    def test_user_filter_strips_inherited_claim(self):
        rows = [_descriptive("AAAA", up_years=20), _descriptive("BBBB", up_years=8)]
        assert all(row.family_adjusted_p_value is not None for row in rows)

        kept = screener.apply_user_filter(
            rows,
            filter_name="up_share_over_70pct",
            predicate=lambda row: (row.historical_up_share or 0) > 0.7,
        )
        assert len(kept) == 1
        cut = kept[0]
        assert cut.exploratory is True
        assert cut.family_adjusted_p_value is None
        assert cut.evidence_label is None
        assert cut.exploratory_budget["scope"] == "user_composed_exploratory"
        assert cut.exploratory_budget["inherits_program_budget"] is False
        assert cut.exploratory_budget["rows_considered"] == 2
        assert cut.abstained is False  # a stripped claim is not an incomplete row

    def test_a_user_cut_does_not_also_carry_the_program_budget_it_disclaims(self):
        # The budget said `inherits_program_budget: False` while the SAME row
        # carried the untouched program block: `multiplicity.scope` still read
        # `program_level`, so the row asserted and disclaimed the same
        # inheritance in two adjacent fields.
        kept = screener.apply_user_filter(
            [_descriptive("AAAA", up_years=20)],
            filter_name="everything",
            predicate=lambda row: True,
        )
        cut = kept[0]
        assert cut.exploratory_budget["inherits_program_budget"] is False
        assert cut.multiplicity["scope"] == screener.EXPLORATORY_MULTIPLICITY_SCOPE
        assert cut.multiplicity["corrected_for_this_cut"] is False
        # The program budget is still READABLE — demoted to provenance, not dropped.
        assert cut.multiplicity["inherited_program_multiplicity"]["scope"] == "program_level"
        assert (
            cut.multiplicity["inherited_program_multiplicity"]["hypotheses_total"] == 180 * 2645
        )

    def test_chained_cuts_accumulate_the_budget_instead_of_overwriting_it(self):
        # A second filter over already-exploratory rows REPLACED the first cut's
        # budget, so two cuts over three rows were disclosed as one two-row cut.
        rows = [
            _descriptive("AAAA", up_years=20),
            _descriptive("BBBB", up_years=19),
            _descriptive("CCCC", up_years=4),
        ]
        first = screener.apply_user_filter(
            rows, filter_name="cut1", predicate=lambda row: (row.historical_up_share or 0) > 0.7
        )
        assert len(first) == 2
        second = screener.apply_user_filter(
            first, filter_name="cut2", predicate=lambda row: True
        )
        budget = second[0].exploratory_budget
        assert budget["filter_name"] == "cut2"
        assert budget["cuts_applied"] == 2
        assert budget["rows_considered"] == 2
        assert budget["rows_considered_cumulative"] == 5  # 3 then 2, not 2
        assert [entry["filter_name"] for entry in budget["prior_cuts"]] == ["cut1"]
        assert budget["prior_cuts"][0]["rows_considered"] == 3

    def test_filtering_an_empty_set_is_not_a_cut(self):
        # A reader filtering an empty page used to get a ScreenerError out of
        # `exploratory_budget`, i.e. a 500-class error rather than an empty cohort.
        assert screener.apply_user_filter([], filter_name="f", predicate=lambda row: True) == []

    def test_an_exploratory_row_cannot_re_acquire_a_claim(self):
        cut = screener.mark_exploratory(
            _descriptive(), budget=screener.exploratory_budget(filter_name="f", rows_considered=1, rows_kept=1)
        )
        with pytest.raises(screener.ScreenerError, match="may not inherit"):
            screener.build_row(**{**cut.as_dict(), "family_adjusted_p_value": 0.01})

    def test_an_exploratory_row_cannot_carry_a_calibration_claim(self):
        with pytest.raises(screener.ScreenerError, match="cannot inherit a calibration"):
            screener.mark_exploratory(
                _calibrated(),
                budget=screener.exploratory_budget(filter_name="f", rows_considered=1, rows_kept=1),
            )

    def test_exploratory_rows_are_visible_in_the_result_counts(self):
        kept = screener.apply_user_filter(
            [_descriptive("AAAA", up_years=20)],
            filter_name="everything",
            predicate=lambda row: True,
        )
        payload = screener.build_result_set(
            asof=ASOF,
            rows=kept,
            consumer="human_research_browser",
            multiplicity=_multiplicity(),
            universe=screener.resolve_universe(ASOF),
        )
        assert payload["counts"]["exploratory"] == 1


# --- point-in-time membership -----------------------------------------------


class TestUniverseDisclosure:
    def test_default_resolver_is_unavailable_and_says_so(self):
        disclosure = screener.resolve_universe(ASOF)
        assert disclosure.point_in_time_available is False
        assert disclosure.basis == screener.UNIVERSE_CURRENT_VINTAGE
        assert disclosure.survivorship_biased is True
        assert "current-vintage, survivorship-biased" in disclosure.note
        assert disclosure.unavailable_reason == screener.NO_RESOLVER_REASON

    def test_an_available_resolver_upgrades_the_basis(self):
        def resolver(asof):
            return {"available": True, "snapshot_date": date(2026, 8, 1), "members": ("AAAA",)}

        disclosure = screener.resolve_universe(ASOF, membership_resolver=resolver)
        assert disclosure.point_in_time_available is True
        assert disclosure.basis == screener.UNIVERSE_POINT_IN_TIME
        assert disclosure.survivorship_biased is False
        assert disclosure.snapshot_date == date(2026, 8, 1)

    def test_todays_roster_is_never_silently_called_history(self):
        with pytest.raises(screener.ScreenerError, match="survivorship"):
            screener.UniverseDisclosure(
                asof=ASOF,
                basis=screener.UNIVERSE_CURRENT_VINTAGE,
                point_in_time_available=False,
                survivorship_biased=False,
                note="today's roster",
                unavailable_reason="whatever",
            )

    def test_pit_module_adapter_degrades_to_unavailable_on_an_empty_store(self, tmp_path):
        # The identity plane answers "unavailable" for anything before its first
        # snapshot. The adapter must pass that through, not fall back to a roster.
        answer = screener.universe_membership_resolver(date(2019, 1, 2), root=tmp_path)
        assert answer["available"] is False
        assert answer["unavailable_reason"]

        disclosure = screener.resolve_universe(
            date(2019, 1, 2),
            membership_resolver=lambda asof: screener.universe_membership_resolver(asof, root=tmp_path),
        )
        assert disclosure.basis == screener.UNIVERSE_CURRENT_VINTAGE
        assert disclosure.survivorship_biased is True

    def test_result_set_requires_a_real_disclosure_object(self):
        with pytest.raises(screener.ScreenerError, match="membership is never assumed"):
            screener.build_result_set(
                asof=ASOF,
                rows=[_descriptive()],
                consumer="human_research_browser",
                multiplicity=_multiplicity(),
                universe={"basis": "point_in_time"},
            )

    # --- the resolver is an INJECTED trust boundary --------------------------
    #
    # The shipped adapter is point-in-time correct. The hole was that
    # `resolve_universe` BELIEVED `available: True`: it never checked the
    # snapshot date against the asof, never required members, and stamped
    # `survivorship_biased=False` on the result — the disclosure asserting the
    # exact opposite of the truth.

    @pytest.mark.parametrize(
        "answer",
        [
            {"available": True},
            {"available": True, "snapshot_date": None, "members": ("AAAA",)},
            {"available": True, "snapshot_date": "2026-08-01", "members": ("AAAA",)},
            {"available": True, "snapshot_date": date(2026, 8, 1), "members": ()},
            {"available": True, "snapshot_date": date(2026, 8, 1)},
        ],
    )
    def test_an_unverifiable_point_in_time_claim_is_downgraded_not_believed(self, answer):
        disclosure = screener.resolve_universe(ASOF, membership_resolver=lambda asof: answer)
        assert disclosure.point_in_time_available is False
        assert disclosure.basis == screener.UNIVERSE_CURRENT_VINTAGE
        assert disclosure.survivorship_biased is True
        assert disclosure.unavailable_reason
        # And it still serialises — a string snapshot_date used to die with a bare
        # AttributeError inside `as_dict()`.
        assert disclosure.as_dict()["snapshot_date"] is None

    def test_a_snapshot_from_after_the_asof_is_refused_as_lookahead(self):
        def future(asof):
            return {"available": True, "snapshot_date": date(2030, 1, 1), "members": ("AAAA",)}

        with pytest.raises(screener.LookaheadError, match="survivorship bias"):
            screener.resolve_universe(date(2015, 1, 2), membership_resolver=future)

        with pytest.raises(screener.LookaheadError):
            screener.UniverseDisclosure(
                asof=ASOF,
                basis=screener.UNIVERSE_POINT_IN_TIME,
                point_in_time_available=True,
                survivorship_biased=False,
                note="from the future",
                snapshot_date=date(2030, 1, 1),
            )

    @pytest.mark.parametrize("bad", ["2026-08-01", 20260801, object()])
    def test_a_snapshot_date_that_is_not_a_date_is_refused_at_construction(self, bad):
        # Enforced on the INSTANCE, not only inside `resolve_universe`: a string
        # snapshot_date used to survive construction and then die with a bare
        # AttributeError inside `as_dict()`, at serialisation time.
        with pytest.raises(screener.ScreenerError, match="calendar date"):
            screener.UniverseDisclosure(
                asof=ASOF,
                basis=screener.UNIVERSE_CURRENT_VINTAGE,
                point_in_time_available=False,
                survivorship_biased=True,
                note="n",
                unavailable_reason="r",
                snapshot_date=bad,
            )

    def test_a_point_in_time_claim_must_name_its_snapshot(self):
        with pytest.raises(screener.ScreenerError, match="must name the snapshot"):
            screener.UniverseDisclosure(
                asof=ASOF,
                basis=screener.UNIVERSE_POINT_IN_TIME,
                point_in_time_available=True,
                survivorship_biased=False,
                note="trust me",
            )

    def test_a_partial_resolver_keeps_its_provenance(self):
        # `functools.partial` has no `__name__`, so the class-name fallback
        # recorded every wrapped resolver as "partial" — which destroys the
        # provenance the field exists to carry.
        from functools import partial

        bound = partial(screener.universe_membership_resolver, root=Path("/nonexistent"))
        disclosure = screener.resolve_universe(ASOF, membership_resolver=bound)
        assert disclosure.resolver == "partial(universe_membership_resolver)"

    def test_the_universe_must_be_asof_the_date_the_page_claims(self):
        # The payload asserted `asof=2026-08-06` while the membership disclosure
        # under it was from 2020, and both printed as authoritative in one set.
        with pytest.raises(screener.ScreenerError, match="membership the page says"):
            screener.build_result_set(
                asof=ASOF,
                rows=[_descriptive()],
                consumer="human_research_browser",
                multiplicity=_multiplicity(),
                universe=screener.resolve_universe(date(2020, 1, 1)),
            )


class TestSmallRefusals:
    def test_a_future_artifact_is_lookahead_not_fresh(self):
        # `age_days: -25, stale: False` read as maximally fresh, and
        # `freshness_age_days` is a sortable column, so a mis-stamped artifact
        # sorted to the top of "freshest first".
        with pytest.raises(screener.LookaheadError, match="from the future"):
            screener.freshness_disclosure(artifact_asof=date(2026, 9, 1), asof=ASOF)

    def test_freshness_refuses_a_timestamp(self):
        from datetime import datetime

        with pytest.raises(screener.ScreenerError, match="calendar dates"):
            screener.freshness_disclosure(
                artifact_asof=datetime(2026, 8, 5, 9, 30), asof=ASOF
            )

    @pytest.mark.parametrize("symbol", ["AAA\n", "AAA\r", "AAA\nBBB", "aaa", "", "-AAA"])
    def test_a_symbol_that_is_not_an_identity_is_refused(self, symbol):
        # `$` also matches immediately BEFORE a trailing newline, so `"AAA\n"`
        # passed and a newline-bearing symbol then travelled into the total-order
        # key, the payload, and every log line.
        with pytest.raises(screener.ScreenerError, match="usable identity"):
            screener.build_row(
                row_id="x",
                symbol=symbol,
                window_start_doy=40,
                window_end_doy=70,
                estimate_type=screener.ESTIMATE_DESCRIPTIVE,
                abstained=True,
                abstention_reason="test",
            )

    @pytest.mark.parametrize("level", [0.0, 1.0, -0.1, 1.5, 1 - 1e-17])
    def test_an_out_of_range_confidence_level_raises_in_this_modules_terms(self, level):
        # Not a bare ValueError out of `math.log` deep inside a statistics helper:
        # every refusal in this module is a ScreenerError a caller can catch.
        with pytest.raises(screener.ScreenerError):
            screener.wilson_interval(5, 10, level=level)

    def test_the_most_extreme_legal_level_still_returns_a_usable_interval(self):
        import math

        low, high = screener.wilson_interval(5, 10, level=math.nextafter(1.0, 0.0))
        assert 0.0 <= low <= 0.5 <= high <= 1.0

    def test_duplicate_detection_does_not_rescan_the_set_per_row(self):
        # The error path ran `identities.count(key)` inside a comprehension over
        # `identities` — O(n^2) on a cross-symbol browser. Counted rather than
        # timed, so the assertion pins the algorithm instead of the machine.
        class _CountingKey(tuple):
            comparisons = 0

            def __eq__(self, other):
                _CountingKey.comparisons += 1
                return tuple.__eq__(self, other)

            def __hash__(self):
                return tuple.__hash__(self)

        class _CountingRow(screener.ResearchRow):
            @property
            def identity(self):
                return _CountingKey(
                    (self.symbol, self.window_start_doy, self.window_end_doy, self.row_id)
                )

        size = 400
        rows = [
            _CountingRow(**{**_descriptive(f"SYM{index:03d}").as_dict()}) for index in range(size)
        ]
        rows.append(_CountingRow(**{**_descriptive("SYM000").as_dict()}))  # one collision

        _CountingKey.comparisons = 0
        with pytest.raises(screener.DeterminismError, match="pagination cannot be stable"):
            screener.order_rows(rows)
        # Linear detection touches each key about once; the quadratic form costs
        # ~n^2 (160,000+ here).
        assert _CountingKey.comparisons < 10 * size, _CountingKey.comparisons


class TestPackageSurface:
    def test_the_package_publishes_no_ungated_ranking_primitive(self):
        # `build_result_set` is the only function that takes a consumer identity
        # and runs `assert_consumer_permitted`. Re-exporting `order_rows` and the
        # row builders at package level made "import the package, call
        # order_rows" a supported way around the only gate this artifact has.
        import engine.seasonality as package

        for name in (
            "order_rows",
            "apply_user_filter",
            "mark_exploratory",
            "group_by_estimate_type",
            "build_research_row",
            "descriptive_research_row",
        ):
            assert not hasattr(package, name), name
            assert name not in package.__all__, name
        assert hasattr(package, "build_research_result_set")
        assert set(package.__all__) <= set(dir(package))
