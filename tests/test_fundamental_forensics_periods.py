"""Typed-period, Q4, TTM, availability, and lineage contracts."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, localcontext
from itertools import count, repeat

import pytest

from engine.fundamental_forensics.periods import (
    CalendarKind,
    FlowDerivationKind,
    PeriodKind,
    PeriodObservation,
    TypedPeriod,
    annual_period,
    derive_q4,
    derive_ttm,
    direct_q4_period,
    fiscal_quarter_period,
    instant_period,
    stub_period,
    ytd_period,
)
from engine.fundamental_forensics.raw_ledger import AvailabilityStatus, TemporalClocks


def _clocks(
    *,
    accepted: str = "2025-02-01T12:00:00Z",
    recorded: str = "2025-02-02T12:00:00Z",
) -> TemporalClocks:
    return TemporalClocks(accepted_at=accepted, recorded_at=recorded)


def _obs(
    period: TypedPeriod,
    value: str | int,
    *,
    name: str | None = None,
    unit: str = "USD",
    dimensions=None,
    revision_basis: str | None = "latest-source-v1",
    clocks: TemporalClocks | None = None,
) -> PeriodObservation:
    return PeriodObservation(
        entity_id="0000320193",
        metric="revenue",
        unit=unit,
        value=value,
        period=period,
        clocks=clocks or _clocks(),
        dimensions=dimensions or {"us-gaap:StatementBusinessSegmentsAxis": "us-gaap:ConsolidationItemsMember"},
        source_occurrence_ids=(f"source-{name}",) if name else (),
        revision_basis=revision_basis,
    )


def _derive_q4_inputs(*, clocks: TemporalClocks | None = None):
    annual = _obs(
        annual_period("2024-01-01", "2024-12-31", fiscal_year=2024, fiscal_year_weeks=52),
        "100",
        name="annual-2024",
        clocks=clocks,
    )
    ytd = _obs(
        ytd_period("2024-01-01", "2024-09-30", fiscal_year=2024, through_quarter=3, week_count=39),
        "70",
        name="ytd-q3-2024",
        clocks=clocks,
    )
    return annual, ytd


def _derive_q4(annual, ytd, **kwargs):
    clocks = {
        "mapping_available_at": "2025-02-02T12:00:00Z",
        "computed_at": "2025-02-03T12:00:00Z",
        "published_at": "2025-02-03T12:05:00Z",
    }
    clocks.update(kwargs)
    return derive_q4(annual, ytd, **clocks)


def test_derived_observation_identity_binds_availability_clocks() -> None:
    annual, ytd = _derive_q4_inputs()
    first = _derive_q4(annual, ytd)
    later = _derive_q4(
        annual,
        ytd,
        computed_at="2025-05-03T12:00:00Z",
        published_at="2025-05-03T12:05:00Z",
    )

    assert first.status is AvailabilityStatus.AVAILABLE
    assert later.status is AvailabilityStatus.AVAILABLE
    assert first.observation is not None and later.observation is not None
    assert first.observation.value == later.observation.value
    assert first.observation.observation_id != later.observation.observation_id


def test_period_observation_identity_is_recomputed_and_self_validating() -> None:
    observation = _quarters_2024()[0]

    restored = replace(observation, observation_id=observation.observation_id)

    assert restored.observation_id == observation.observation_id
    with pytest.raises(ValueError, match="canonical observation content"):
        replace(observation, value="999")


def _quarters_2024(*, q4: TypedPeriod | None = None, clocks: TemporalClocks | None = None):
    return (
        _obs(
            fiscal_quarter_period("2024-01-01", "2024-03-31", fiscal_year=2024, fiscal_quarter=1, week_count=13),
            "10",
            name="q1-2024",
            clocks=clocks,
        ),
        _obs(
            fiscal_quarter_period("2024-04-01", "2024-06-30", fiscal_year=2024, fiscal_quarter=2, week_count=13),
            "20",
            name="q2-2024",
            clocks=clocks,
        ),
        _obs(
            fiscal_quarter_period("2024-07-01", "2024-09-30", fiscal_year=2024, fiscal_quarter=3, week_count=13),
            "30",
            name="q3-2024",
            clocks=clocks,
        ),
        _obs(
            q4
            or direct_q4_period("2024-10-01", "2024-12-31", fiscal_year=2024, week_count=13),
            "40",
            name="q4-2024",
            clocks=clocks,
        ),
    )


def _derive_ttm(quarters, **kwargs):
    clocks = {
        "mapping_available_at": "2025-02-02T12:00:00Z",
        "computed_at": "2025-02-03T12:00:00Z",
        "published_at": "2025-02-03T12:05:00Z",
    }
    clocks.update(kwargs)
    return derive_ttm(quarters, **clocks)


def test_typed_periods_make_instant_duration_q_ytd_annual_stub_and_53_week_explicit() -> None:
    instant = instant_period("2024-12-31")
    quarter = fiscal_quarter_period(
        "2024-01-01", "2024-03-31", fiscal_year=2024, fiscal_quarter=1, week_count=13
    )
    ytd = ytd_period(
        "2024-01-01", "2024-09-30", fiscal_year=2024, through_quarter=3, week_count=39
    )
    annual = annual_period(
        "2023-01-29", "2024-02-03", fiscal_year=2024, fiscal_year_weeks=53
    )
    stub = stub_period("2024-01-01", "2024-04-30", fiscal_year=2024)

    assert instant.kind is PeriodKind.INSTANT and instant.is_instant
    assert quarter.kind is PeriodKind.FISCAL_QUARTER and quarter.is_discrete_quarter
    assert ytd.kind is PeriodKind.YTD and ytd.fiscal_quarter == 3
    assert annual.kind is PeriodKind.ANNUAL and annual.is_53_week
    assert "53_week" in annual.semantics
    assert stub.kind is PeriodKind.STUB and stub.is_stub


def test_period_validation_refuses_ambiguous_or_incoherent_semantics() -> None:
    with pytest.raises(ValueError, match="instant period cannot have start"):
        TypedPeriod(kind="instant", start="2024-01-01", end="2024-12-31")
    with pytest.raises(ValueError, match="YTD is reserved"):
        ytd_period("2024-01-01", "2024-12-31", fiscal_year=2024, through_quarter=4)
    with pytest.raises(ValueError, match="direct_q4 requires"):
        TypedPeriod(
            kind="direct_q4",
            start="2024-01-01",
            end="2024-03-31",
            fiscal_year=2024,
            fiscal_quarter=1,
        )
    with pytest.raises(ValueError, match="stub calendar"):
        TypedPeriod(
            kind="annual",
            start="2024-01-01",
            end="2024-12-31",
            fiscal_year=2024,
            calendar_kind="stub",
        )


def test_valid_q4_derivation_has_exact_value_typed_period_clocks_and_lineage() -> None:
    annual, ytd = _derive_q4_inputs()
    result = _derive_q4(annual, ytd, rule_id="rules/q4/v1")

    assert result.status is AvailabilityStatus.AVAILABLE
    assert result.derivation_kind is FlowDerivationKind.DERIVED_Q4
    assert result.observation.value == Decimal("30")
    assert result.observation.period.kind is PeriodKind.DERIVED_Q4
    assert result.observation.period.start.isoformat() == "2024-10-01"
    assert result.observation.period.end.isoformat() == "2024-12-31"
    assert result.observation.clocks.accepted_at == annual.accepted_at
    assert result.observation.clocks.published_at.isoformat().startswith("2025-02-03T12:05:00")
    assert set(result.observation.lineage_ids) >= {
        annual.observation_id,
        ytd.observation_id,
        "rules/q4/v1",
    }
    assert set(result.observation.source_occurrence_ids) == {"source-annual-2024", "source-ytd-q3-2024"}


def test_q4_derivation_is_not_available_for_missing_evidence_and_not_evaluable_for_bad_basis() -> None:
    annual, ytd = _derive_q4_inputs()
    missing = _derive_q4(annual, None)
    incompatible_unit = _derive_q4(annual, _obs(ytd.period, "70", name="ytd-other-unit", unit="shares"))
    wrong_ytd = _derive_q4(
        annual,
        _obs(
            ytd_period("2024-01-01", "2024-06-30", fiscal_year=2024, through_quarter=2),
            "50",
            name="ytd-q2-2024",
        ),
    )

    assert missing.status is AvailabilityStatus.NOT_AVAILABLE
    assert "missing required ytd" in missing.reasons[0]
    assert incompatible_unit.status is AvailabilityStatus.NOT_EVALUABLE
    assert "unit" in incompatible_unit.reasons[0]
    assert wrong_ytd.status is AvailabilityStatus.NOT_EVALUABLE
    assert "Q3 cumulative" in wrong_ytd.reasons[0]


def test_q4_derivation_rejects_stub_changed_year_and_known_revision_mismatch() -> None:
    annual, ytd = _derive_q4_inputs()
    stub_annual = _obs(stub_period("2024-01-01", "2024-12-31", fiscal_year=2024), "100", name="stub")
    revision_mismatch = _obs(ytd.period, "70", name="different-revision", revision_basis="original-v1")

    assert _derive_q4(stub_annual, ytd).status is AvailabilityStatus.NOT_EVALUABLE
    result = _derive_q4(annual, revision_mismatch)
    assert result.status is AvailabilityStatus.NOT_EVALUABLE
    assert "revision_basis" in result.reasons[0]


def test_53_week_derived_q4_requires_explicit_39_week_ytd_and_creates_14_week_q4() -> None:
    annual = _obs(
        annual_period("2023-01-29", "2024-02-03", fiscal_year=2024, fiscal_year_weeks=53),
        "530",
        name="annual-53",
    )
    ytd = _obs(
        ytd_period("2023-01-29", "2023-10-28", fiscal_year=2024, through_quarter=3, week_count=39),
        "390",
        name="ytd-39",
    )
    result = _derive_q4(annual, ytd)

    assert result.status is AvailabilityStatus.AVAILABLE
    assert result.observation.value == Decimal("140")
    assert result.observation.period.inferred_week_count == 14
    assert result.observation.period.is_53_week
    with pytest.raises(ValueError, match="conflicts with date interval"):
        ytd_period(
            "2023-01-29", "2023-10-28", fiscal_year=2024, through_quarter=3, week_count=38
        )


def test_q4_derivation_respects_source_and_system_cutoffs_without_future_leakage() -> None:
    late_clocks = _clocks(accepted="2025-03-01T12:00:00Z", recorded="2025-03-02T12:00:00Z")
    annual, ytd = _derive_q4_inputs(clocks=late_clocks)
    before_source = _derive_q4(annual, ytd, as_of="2025-02-15T00:00:00Z", clock="source_event")
    after_source = _derive_q4(
        annual,
        ytd,
        mapping_available_at="2025-03-02T12:00:00Z",
        computed_at="2025-03-03T12:00:00Z",
        published_at="2025-03-03T12:05:00Z",
        as_of="2025-03-15T00:00:00Z",
        clock="source_event",
    )

    assert before_source.status is AvailabilityStatus.NOT_AVAILABLE
    assert before_source.input_observation_ids == ()
    assert after_source.status is AvailabilityStatus.AVAILABLE


def test_future_period_inputs_are_observationally_opaque() -> None:
    cutoff = "2025-02-15T00:00:00Z"
    first_clocks = _clocks(
        accepted="2025-03-01T12:00:00Z",
        recorded="2025-03-02T12:00:00Z",
    )
    second_clocks = _clocks(
        accepted="2026-09-01T12:00:00Z",
        recorded="2026-09-02T12:00:00Z",
    )
    first_annual, first_ytd = _derive_q4_inputs(clocks=first_clocks)
    second_annual, second_ytd = _derive_q4_inputs(clocks=second_clocks)
    first = _derive_q4(first_annual, first_ytd, as_of=cutoff, clock="source_event")
    second = _derive_q4(second_annual, second_ytd, as_of=cutoff, clock="source_event")

    assert first.to_dict() == second.to_dict()
    assert first.input_observation_ids == ()


def test_partial_and_overfull_future_period_inputs_cannot_bypass_opacity() -> None:
    cutoff = "2025-02-15T00:00:00Z"
    first_clocks = _clocks(
        accepted="2025-03-01T12:00:00Z",
        recorded="2025-03-02T12:00:00Z",
    )
    second_clocks = _clocks(
        accepted="2027-03-01T12:00:00Z",
        recorded="2027-03-02T12:00:00Z",
    )
    _, first_ytd = _derive_q4_inputs(clocks=first_clocks)
    _, second_ytd = _derive_q4_inputs(clocks=second_clocks)
    first_missing = _derive_q4(None, first_ytd, as_of=cutoff, clock="source_event")
    second_missing = _derive_q4(None, second_ytd, as_of=cutoff, clock="source_event")
    first_quarters = _quarters_2024(clocks=first_clocks)
    second_quarters = _quarters_2024(clocks=second_clocks)
    first_partial = _derive_ttm(first_quarters[:3], as_of=cutoff, clock="source_event")
    second_partial = _derive_ttm(second_quarters[:3], as_of=cutoff, clock="source_event")
    first_overfull = _derive_ttm(repeat(first_quarters[0]), as_of=cutoff, clock="source_event")
    second_overfull = _derive_ttm(repeat(second_quarters[0]), as_of=cutoff, clock="source_event")

    assert first_missing.to_dict() == second_missing.to_dict()
    assert first_partial.to_dict() == second_partial.to_dict()
    assert first_overfull.to_dict() == second_overfull.to_dict()
    assert first_missing.input_observation_ids == ()
    assert first_partial.input_observation_ids == ()
    assert first_overfull.input_observation_ids == ()


def test_ttm_sums_exactly_four_consecutive_compatible_discrete_quarters() -> None:
    quarters = _quarters_2024()
    result = _derive_ttm(quarters)

    assert result.status is AvailabilityStatus.AVAILABLE
    assert result.derivation_kind is FlowDerivationKind.TTM
    assert result.observation.value == Decimal("100")
    assert result.observation.period.kind is PeriodKind.TTM
    assert result.observation.period.fiscal_year == 2024
    assert result.observation.period.inferred_week_count == 52
    assert result.observation.period.calendar_kind is CalendarKind.WEEK_52
    assert set(result.observation.lineage_ids) >= {
        item.observation_id for item in quarters
    }


def test_ttm_accepts_derived_q4_and_keeps_it_distinct_from_direct_q4() -> None:
    annual, ytd = _derive_q4_inputs()
    q4_result = _derive_q4(annual, ytd)
    q1, q2, q3, _ = _quarters_2024()
    result = _derive_ttm(
        (q1, q2, q3, q4_result.observation),
        computed_at="2025-02-04T12:00:00Z",
        published_at="2025-02-04T12:05:00Z",
    )

    assert q4_result.observation.period.kind is PeriodKind.DERIVED_Q4
    assert result.status is AvailabilityStatus.AVAILABLE
    assert result.observation.value == Decimal("90")
    assert q4_result.observation.observation_id in result.observation.lineage_ids


def test_ttm_rejects_partial_nonconsecutive_overlapping_and_incompatible_inputs() -> None:
    q1, q2, q3, q4 = _quarters_2024()
    partial = _derive_ttm((q1, q2, q3))
    overfull = _derive_ttm((q1, q2, q3, q4, q1))
    nonconsecutive = _derive_ttm((q1, q2, q4, _obs(
        fiscal_quarter_period("2025-01-01", "2025-03-31", fiscal_year=2025, fiscal_quarter=1),
        "50",
        name="q1-2025",
    )))
    overlapping_q2 = _obs(
        fiscal_quarter_period("2024-03-15", "2024-06-30", fiscal_year=2024, fiscal_quarter=2),
        "20",
        name="q2-overlap",
    )
    overlap = _derive_ttm((q1, overlapping_q2, q3, q4))
    bad_unit = _obs(q4.period, "40", name="q4-shares", unit="shares")
    incompatible = _derive_ttm((q1, q2, q3, bad_unit))

    assert partial.status is AvailabilityStatus.NOT_AVAILABLE
    assert overfull.status is AvailabilityStatus.NOT_EVALUABLE
    assert nonconsecutive.status is AvailabilityStatus.NOT_EVALUABLE
    assert overlap.status is AvailabilityStatus.NOT_EVALUABLE
    assert incompatible.status is AvailabilityStatus.NOT_EVALUABLE


def test_ttm_bounds_iterable_materialization() -> None:
    q1 = _quarters_2024()[0]

    result = _derive_ttm(repeat(q1))

    assert result.status is AvailabilityStatus.NOT_EVALUABLE
    assert "more than four" in result.reasons[0]


def test_period_arithmetic_is_independent_of_ambient_decimal_context() -> None:
    annual, ytd = _derive_q4_inputs()
    precise_annual = _obs(
        annual.period,
        "123456789012345678901234567890.123456",
        name="precise-annual",
    )
    precise_ytd = _obs(
        ytd.period,
        "111111111111111111111111111111.111111",
        name="precise-ytd",
    )

    with localcontext() as context:
        context.prec = 6
        low_precision = _derive_q4(precise_annual, precise_ytd)
    with localcontext() as context:
        context.prec = 80
        high_precision = _derive_q4(precise_annual, precise_ytd)

    assert low_precision.status is AvailabilityStatus.AVAILABLE
    assert high_precision.status is AvailabilityStatus.AVAILABLE
    assert low_precision.observation.value == high_precision.observation.value
    assert low_precision.observation.observation_id == high_precision.observation.observation_id


def test_period_arithmetic_overflow_fails_closed() -> None:
    annual, ytd = _derive_q4_inputs()
    huge_annual = _obs(annual.period, "9e6144", name="huge-annual")
    huge_negative_ytd = _obs(ytd.period, "-9e6144", name="huge-ytd")

    result = _derive_q4(huge_annual, huge_negative_ytd)

    assert result.status is AvailabilityStatus.NOT_EVALUABLE
    assert "fixed decimal contract" in result.reasons[0]


def test_period_observation_rejects_unsafe_decimal_wire_shapes_before_formatting() -> None:
    period = fiscal_quarter_period(
        "2024-01-01",
        "2024-03-31",
        fiscal_year=2024,
        fiscal_quarter=1,
    )

    with pytest.raises(ValueError, match="period decimal contract"):
        _obs(period, Decimal("1e-1000000000"), name="hostile-exponent")
    with pytest.raises(ValueError, match="coefficient safety limit|text safety limit"):
        _obs(period, "9" * 9000, name="hostile-coefficient")


def test_period_observation_bounds_attacker_controlled_iterables() -> None:
    observation = _quarters_2024()[0]

    with pytest.raises(ValueError, match="dimensions exceeds the item safety limit"):
        replace(
            observation,
            observation_id=None,
            dimensions=((f"axis-{index}", "member") for index in count()),
        )
    with pytest.raises(ValueError, match="source_occurrence_id exceeds the item safety limit"):
        replace(
            observation,
            observation_id=None,
            source_occurrence_ids=(f"source-{index}" for index in count()),
        )
    with pytest.raises(ValueError, match="quality_flag exceeds the item safety limit"):
        replace(
            observation,
            observation_id=None,
            quality_flags=(f"flag-{index}" for index in count()),
        )


def test_typed_period_bounds_semantic_tag_iterables() -> None:
    with pytest.raises(ValueError, match="period semantic tags exceeds the item safety limit"):
        TypedPeriod(
            kind=PeriodKind.DURATION,
            start="2024-01-01",
            end="2024-03-31",
            semantics=(f"tag-{index}" for index in count()),
        )


def test_53_week_ttm_is_only_labelled_when_component_metadata_proves_it() -> None:
    quarters = (
        _obs(
            fiscal_quarter_period("2023-01-29", "2023-04-29", fiscal_year=2024, fiscal_quarter=1, week_count=13),
            "10",
            name="53-q1",
        ),
        _obs(
            fiscal_quarter_period("2023-04-30", "2023-07-29", fiscal_year=2024, fiscal_quarter=2, week_count=13),
            "20",
            name="53-q2",
        ),
        _obs(
            fiscal_quarter_period("2023-07-30", "2023-10-28", fiscal_year=2024, fiscal_quarter=3, week_count=13),
            "30",
            name="53-q3",
        ),
        _obs(
            direct_q4_period(
                "2023-10-29", "2024-02-03", fiscal_year=2024,
                calendar_kind=CalendarKind.WEEK_53, week_count=14,
            ),
            "40",
            name="53-q4",
        ),
    )
    result = _derive_ttm(quarters)

    assert result.status is AvailabilityStatus.AVAILABLE
    assert result.observation.period.is_53_week
    assert result.observation.period.inferred_week_count == 53


def test_ttm_cutoff_blocks_a_future_system_publication() -> None:
    annual, ytd = _derive_q4_inputs()
    q4 = _derive_q4(
        annual,
        ytd,
        computed_at="2025-03-03T12:00:00Z",
        published_at="2025-03-04T12:00:00Z",
    ).observation
    q1, q2, q3, _ = _quarters_2024()
    early = _derive_ttm(
        (q1, q2, q3, q4),
        computed_at="2025-03-05T12:00:00Z",
        published_at="2025-03-05T12:05:00Z",
        as_of="2025-03-03T00:00:00Z",
        clock="system",
    )
    late = _derive_ttm(
        (q1, q2, q3, q4),
        computed_at="2025-03-05T12:00:00Z",
        published_at="2025-03-05T12:05:00Z",
        as_of="2025-03-05T12:06:00Z",
        clock="system",
    )

    assert early.status is AvailabilityStatus.NOT_AVAILABLE
    assert late.status is AvailabilityStatus.AVAILABLE


def test_system_replay_blocks_future_q4_and_ttm_artifact_publication() -> None:
    annual, ytd = _derive_q4_inputs()
    q4 = _derive_q4(
        annual,
        ytd,
        as_of="2025-02-02T12:00:00Z",
        clock="system",
    )
    q1, q2, q3, q4_direct = _quarters_2024()
    ttm = _derive_ttm(
        (q1, q2, q3, q4_direct),
        as_of="2025-02-02T12:00:00Z",
        clock="system",
    )

    assert q4.status is AvailabilityStatus.NOT_AVAILABLE
    assert "unavailable at requested system cutoff" in q4.reasons[0]
    assert ttm.status is AvailabilityStatus.NOT_AVAILABLE
    assert "unavailable at requested system cutoff" in ttm.reasons[0]


def test_future_period_governance_is_opaque_before_semantic_evaluation() -> None:
    annual, ytd = _derive_q4_inputs()
    incompatible_ytd = _obs(ytd.period, "70", name="future-governance-shares", unit="shares")
    future_clocks = {
        "mapping_available_at": "2027-04-01T00:00:00Z",
        "computed_at": "2027-03-01T00:00:00Z",
        "published_at": "2028-01-01T00:00:00Z",
        "as_of": "2025-02-15T00:00:00Z",
        "clock": "system",
    }

    compatible = _derive_q4(annual, ytd, **future_clocks)
    incompatible = _derive_q4(annual, incompatible_ytd, **future_clocks)

    assert compatible.to_dict() == incompatible.to_dict()
    assert compatible.input_observation_ids == ()


def test_q4_requires_real_annual_and_nine_month_ytd_geometry() -> None:
    short_annual = _obs(
        annual_period("2024-01-01", "2024-06-30", fiscal_year=2024),
        "100",
        name="short-annual",
    )
    short_ytd = _obs(
        ytd_period("2024-01-01", "2024-03-31", fiscal_year=2024, through_quarter=3),
        "70",
        name="short-ytd",
    )
    annual, _ = _derive_q4_inputs()
    short_ytd_geometry = _obs(
        ytd_period("2024-01-01", "2024-09-23", fiscal_year=2024, through_quarter=3),
        "70",
        name="38-week-ytd",
    )

    assert _derive_q4(short_annual, short_ytd).status is AvailabilityStatus.NOT_EVALUABLE
    result = _derive_q4(annual, short_ytd_geometry)
    assert result.status is AvailabilityStatus.NOT_EVALUABLE
    assert "39 weeks" in result.reasons[0]


def test_ttm_requires_adjacent_calendar_intervals_not_just_consecutive_fiscal_labels() -> None:
    gapped = (
        _obs(
            fiscal_quarter_period("2024-01-01", "2024-03-31", fiscal_year=2024, fiscal_quarter=1),
            "10",
            name="gap-q1",
        ),
        _obs(
            fiscal_quarter_period("2024-07-01", "2024-09-29", fiscal_year=2024, fiscal_quarter=2),
            "20",
            name="gap-q2",
        ),
        _obs(
            fiscal_quarter_period("2025-01-01", "2025-03-31", fiscal_year=2024, fiscal_quarter=3),
            "30",
            name="gap-q3",
        ),
        _obs(
            direct_q4_period("2025-07-01", "2025-09-29", fiscal_year=2024),
            "40",
            name="gap-q4",
        ),
    )

    result = _derive_ttm(gapped)
    assert result.status is AvailabilityStatus.NOT_EVALUABLE
    assert "adjacent" in result.reasons[0]


def test_week_metadata_must_match_dates_before_53_week_semantics_can_be_used() -> None:
    with pytest.raises(ValueError, match="week_count=14 conflicts"):
        direct_q4_period(
            "2024-10-01",
            "2024-12-31",
            fiscal_year=2024,
            calendar_kind=CalendarKind.WEEK_53,
            week_count=14,
        )
    with pytest.raises(ValueError, match="conflicts with date interval"):
        annual_period("2024-01-01", "2024-12-31", fiscal_year=2024, fiscal_year_weeks=53)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"fiscal_year": True, "fiscal_quarter": 1}, "fiscal_year must be"),
        ({"fiscal_year": 2024, "fiscal_quarter": True}, "fiscal_quarter must be"),
        (
            {"fiscal_year": 2024, "fiscal_quarter": 1, "fiscal_year_weeks": True},
            "fiscal_year_weeks must be",
        ),
        ({"fiscal_year": 2024, "fiscal_quarter": 1, "week_count": True}, "week_count must be"),
    ],
)
def test_period_integer_metadata_rejects_booleans(overrides: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        TypedPeriod(
            kind=PeriodKind.FISCAL_QUARTER,
            start="2024-01-01",
            end="2024-03-31",
            **overrides,
        )


def test_q4_and_ttm_require_a_common_explicit_revision_basis() -> None:
    annual, ytd = _derive_q4_inputs()
    annual_without_basis = _obs(annual.period, "100", name="annual-no-basis", revision_basis=None)
    ytd_without_basis = _obs(ytd.period, "70", name="ytd-no-basis", revision_basis=None)
    derived_q4 = _derive_q4(annual_without_basis, ytd_without_basis)

    assert derived_q4.status is AvailabilityStatus.NOT_EVALUABLE
    assert "explicit common revision_basis" in derived_q4.reasons[0]

    quarters = tuple(
        _obs(item.period, item.value, name=f"no-basis-{index}", revision_basis=None)
        for index, item in enumerate(_quarters_2024(), start=1)
    )
    result = _derive_ttm(quarters)
    assert result.status is AvailabilityStatus.NOT_EVALUABLE
    assert "explicit common revision_basis" in result.reasons[0]


def test_period_observations_reject_binary_float_values() -> None:
    with pytest.raises(ValueError, match="binary float"):
        _obs(
            fiscal_quarter_period("2024-01-01", "2024-03-31", fiscal_year=2024, fiscal_quarter=1),
            0.1 + 0.2,
            name="float-q1",
        )
