"""Contract and multiplicity tests for the clean-room seasonality foundation."""
from __future__ import annotations

import importlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from engine.seasonality.contracts import (
    BIOTEMPORAL_EVENT_SCHEMA,
    BIOTEMPORAL_EVENT_V2_SCHEMA,
    EVENT_STATUS_ALLOWLIST_V2,
    EVENT_TYPE_ALLOWLIST_V2,
    ContractError,
    build_bitemporal_event_v2,
    build_neuralweb_state,
    build_prophet_overlay,
    build_source_temporal,
    canonical_event_v2_bytes,
    downgrade_event_v2_to_v1,
    event_v2_content_hash,
    event_v2_pit_leakage_is_checkable,
    source_temporal_day,
    source_temporal_exact,
    source_temporal_is_study_eligible,
    source_temporal_month,
    source_temporal_quarter,
    source_temporal_range,
    source_temporal_span_seconds,
    source_temporal_unavailable,
    source_temporal_unparsed,
    source_temporal_year,
    upgrade_event_v1_to_v2,
    validate_bitemporal_event,
    validate_bitemporal_event_v2,
    validate_source_temporal,
)
from engine.seasonality.foundation import (
    SELECTION_CONTROL_SYMBOLS,
    build_methodology_manifest,
)
from engine.seasonality.multiplicity import benjamini_yekutieli, max_t_adjusted_p_values
from scripts.build_biopharma_seasonality import build

_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64


def _event() -> dict:
    return {
        "schema": BIOTEMPORAL_EVENT_SCHEMA,
        "event_id": "evt:issuer-1:pdufa-2027-01",
        "issuer_id": "issuer:1",
        "event_type": "fda_pdufa",
        "status": "scheduled",
        "date_precision": "exact_date",
        "scheduled_start": "2027-01-15T00:00:00Z",
        "scheduled_end": "2027-01-15T23:59:59Z",
        "actual_at": None,
        "certainty": 0.9,
        "published_at": "2026-07-30T20:00:00Z",
        "ingested_at": "2026-07-30T20:05:00Z",
        "known_at": "2026-07-30T20:05:00Z",
        "effective_at": "2027-01-15T00:00:00Z",
        "source_class": "issuer_filing",
        "source_url": "https://example.test/filing",
        "source_hash": _HASH_A,
    }


def _state() -> dict:
    return build_neuralweb_state(
        artifact_id="biopharma-seasonality-state",
        entity={"type": "issuer", "id": "issuer:1", "ticker": "BIO"},
        asof="2026-08-01",
        available_at="2026-08-01T21:30:00Z",
        expires_at="2026-08-02T21:30:00Z",
        clock={"type": "event", "phase": "pre_event_20d", "event_id": "evt:1"},
        forecast={
            "target": "excess_return_gt_0",
            "horizon_td": 20,
            "p": 0.58,
            "p_baseline": 0.51,
            "edge": 0.07,
            "ci90": [0.48, 0.65],
        },
        evidence={
            "n_independent": 74,
            "n_issuers": 31,
            "n_date_clusters": 48,
            "live_n": 18,
            "q_by": 0.07,
            "p_max_t": None,
            "spa_p": 0.03,
        },
        uncertainty={"abstain": False, "flags": ["forward_sample_thin"]},
        provenance={
            "model_version": "seasonality-2026q3",
            "pattern_spec_hash": _HASH_A,
            "data_snapshot": _HASH_B,
        },
    )


def test_bitemporal_event_accepts_future_effective_date():
    validated = validate_bitemporal_event(_event())
    assert validated["effective_at"].startswith("2027-")


def test_bitemporal_event_rejects_knowledge_before_ingestion():
    event = _event()
    event["known_at"] = "2026-07-30T20:01:00Z"
    with pytest.raises(ContractError, match="known_at cannot precede ingested_at"):
        validate_bitemporal_event(event)


def test_neuralweb_state_is_context_only_and_cannot_rank():
    state = _state()
    assert state["is_context_only"] is True
    assert state["authority"]["may_rank"] is False
    assert state["authority"]["may_originate"] is False
    assert state["authority"]["may_boost_confidence"] is False


def test_neuralweb_state_rejects_probability_edge_mismatch():
    with pytest.raises(ContractError, match="forecast.edge must equal"):
        build_neuralweb_state(
            artifact_id="biopharma-seasonality-state",
            entity={"type": "issuer", "id": "issuer:1"},
            asof="2026-08-01",
            available_at="2026-08-01T00:00:00Z",
            expires_at="2026-08-02T00:00:00Z",
            clock={"type": "calendar", "phase": "august"},
            forecast={
                "target": "excess_return_gt_0",
                "horizon_td": 20,
                "p": 0.6,
                "p_baseline": 0.5,
                "edge": 0.2,
                "ci90": [0.4, 0.7],
            },
            evidence={"n_independent": 12, "n_issuers": 1, "n_date_clusters": 12, "live_n": 0},
            uncertainty={"abstain": True, "flags": ["not_forward_validated"]},
            provenance={"model_version": "test", "pattern_spec_hash": _HASH_A, "data_snapshot": _HASH_B},
        )


def test_prophet_overlay_cannot_cap_on_positive_context():
    with pytest.raises(ContractError, match="requires adverse_event=true"):
        build_prophet_overlay(
            plan_id="BIO-BULL-2026-08-01",
            seasonality_state_ref="sha256:state",
            horizon_match=True,
            event_inside_plan_horizon=True,
            overlap_with_existing_features=False,
            action="CAP_CONFIDENCE",
            reason_codes=["calendar_tailwind"],
            expires_at="2026-08-02T00:00:00Z",
            adverse_event=False,
            deescalation_gate_passed=True,
            confidence_cap=0.6,
        )


def test_prophet_adverse_cap_requires_separate_gate():
    with pytest.raises(ContractError, match="separately passed"):
        build_prophet_overlay(
            plan_id="BIO-BULL-2026-08-01",
            seasonality_state_ref="sha256:state",
            horizon_match=True,
            event_inside_plan_horizon=True,
            overlap_with_existing_features=False,
            action="CAP_CONFIDENCE",
            reason_codes=["binary_event_hazard"],
            expires_at="2026-08-02T00:00:00Z",
            adverse_event=True,
            deescalation_gate_passed=False,
            confidence_cap=0.6,
        )


def test_prophet_adverse_cap_stays_shrink_only_after_gate():
    overlay = build_prophet_overlay(
        plan_id="BIO-BULL-2026-08-01",
        seasonality_state_ref="sha256:state",
        horizon_match=True,
        event_inside_plan_horizon=True,
        overlap_with_existing_features=False,
        action="CAP_CONFIDENCE",
        reason_codes=["binary_event_hazard"],
        expires_at="2026-08-02T00:00:00Z",
        adverse_event=True,
        deescalation_gate_passed=True,
        confidence_cap=0.6,
    )
    assert overlay["confidence_cap"] == 0.6
    assert not any(overlay["authority"].values())


def test_benjamini_yekutieli_known_panel_and_order():
    adjusted = benjamini_yekutieli([0.20, 0.01, 0.02])
    assert adjusted == pytest.approx([0.3666666667, 0.055, 0.055])


def test_max_t_uses_family_maximum_and_finite_sample_correction():
    adjusted = max_t_adjusted_p_values(
        [2.0, 0.5],
        [[1.0, 1.5], [2.1, 0.1], [0.3, 0.4]],
    )
    assert adjusted == pytest.approx([0.5, 0.75])


def test_methodology_manifest_admits_no_live_forecasts():
    """The status names the tranche that IS live; the absences stay absent.

    The status moved from ``foundation_contracts_live`` to ``calendar_clock_live``
    when the Lane 1/2/4 calendar clock shipped, because a manifest that still
    claimed only contracts were live would have been understating — and a
    manifest nobody may change is a manifest nobody keeps true. What must never
    move is the list of things that do not exist.
    """
    manifest = build_methodology_manifest(date(2026, 8, 1))
    assert manifest["status"] == "calendar_clock_live"
    assert manifest["availability"]["live_calendar_clock"] is True
    assert manifest["availability"]["live_selection_correction"] is True
    assert manifest["availability"]["live_forecasts"] is False
    assert manifest["availability"]["live_screener"] is False
    assert manifest["availability"]["live_event_graph"] is False
    assert manifest["authority"]["may_rank"] is False


def test_every_declared_selection_control_resolves_to_a_defined_symbol():
    """A declared control that no symbol implements is a claim about nothing.

    The manifest shipped ``spa_reality_check`` for months while
    ``engine/validation.py`` defined ``reality_check`` and ``spa_test`` and no
    such name at all — a public statement about a correction that could not run.
    Two halves are pinned so the pair cannot drift apart again: the map is TOTAL
    over the declared list (neither side may grow alone), and every dotted target
    still imports.
    """
    manifest = build_methodology_manifest(date(2026, 8, 1))
    declared = manifest["validation"]["selection_controls"]
    assert len(declared) == len(set(declared)), f"duplicate selection control: {declared}"
    assert set(declared) == set(SELECTION_CONTROL_SYMBOLS)

    for control, dotted in SELECTION_CONTROL_SYMBOLS.items():
        module_name, _, symbol = dotted.rpartition(".")
        assert module_name, f"{control}: {dotted!r} is not a dotted path"
        module = importlib.import_module(module_name)
        resolved = getattr(module, symbol, None)
        assert resolved is not None, f"{control}: {dotted} does not exist"
        assert callable(resolved), f"{control}: {dotted} is not callable"


def test_build_writes_public_methodology_manifest(tmp_path):
    output = build(root=tmp_path, as_of=date(2026, 8, 1))
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert output == tmp_path / "site" / "seasonalitydata" / "methodology.json"
    assert payload["schema"] == "biopharma_seasonality.methodology.v1"
    assert payload["as_of"] == "2026-08-01"


def test_methodology_manifest_is_in_reviewed_public_boundary():
    root = Path(__file__).resolve().parents[1]
    policy = yaml.safe_load((root / "config" / "site_access.yml").read_text(encoding="utf-8"))
    path = "/seasonalitydata/methodology.json"
    assert path in policy["public"]["exact"]
    assert path in (root / "app" / "deploy" / "Caddyfile").read_text(encoding="utf-8")


# --- biopharma.event.v2 temporal contract ---------------------------------
#
# The bijection is restated here rather than imported so the test pins the
# contract instead of echoing it.
_PRECISION_TO_RULES = {
    "exact_time": {"exact_instant"},
    "exact_date": {"day_span"},
    "month": {"month_span"},
    "quarter": {"quarter_span"},
    "year": {"year_span"},
    "range": {"source_declared_range"},
    "unknown": {"unavailable", "unparsed"},
}
_BOUND_RULES = {rule for rules in _PRECISION_TO_RULES.values() for rule in rules}


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _event_v1_exact() -> dict:
    """A v1 event whose declared precision matches the instants it stores."""
    event = _event()
    event["event_type"] = "pdufa_date"
    event["date_precision"] = "exact_time"
    return event


def _event_v2(**overrides) -> dict:
    kwargs = {
        "event_id": "evt:issuer-1:pdufa-2027-01",
        "issuer_id": "issuer:1",
        "event_type": "pdufa_date",
        "status": "scheduled",
        "source_class": "issuer_filing",
        "source_url": "https://example.test/filing",
        "source_hash": _HASH_A,
        "known_at": "2026-07-30T20:05:00Z",
        "ingested_at": "2026-07-30T20:05:00Z",
        "source_published": source_temporal_exact("2026-07-30T20:00:00Z"),
        "source_effective": source_temporal_day("2027-01-15"),
        "scheduled_window": source_temporal_quarter(2027, 1),
        "actual": source_temporal_unavailable("event has not occurred yet"),
        "certainty": 0.9,
        "revision": {"revision_id": "rev:1", "revision_index": 0, "supersedes": None},
    }
    kwargs.update(overrides)
    return build_bitemporal_event_v2(**kwargs)


def test_source_temporal_carries_a_span_and_never_an_instant():
    month = source_temporal_month(2025, 3)
    assert "value" not in month
    assert month["precision"] == "month"
    assert month["bound_rule"] == "month_span"
    assert _utc(month["lower_bound"]) == _utc("2025-03-01T00:00:00Z")
    assert _utc(month["upper_bound"]) == _utc("2025-03-31T23:59:59.999999Z")


def test_source_temporal_accepts_every_imprecise_shape_the_sources_emit():
    shapes = [
        source_temporal_exact("2025-03-01T13:30:00Z"),
        source_temporal_day("2025-03-01"),
        source_temporal_month(2025, 3),
        source_temporal_quarter(2025, 3),
        source_temporal_year(2025),
        source_temporal_range(
            "2025-03-01T00:00:00Z", "2025-06-30T23:59:59Z", original_value="Q2 2025 (Mar-Jun)"
        ),
        source_temporal_unparsed("mid-2025 (H1)"),
        source_temporal_unavailable("source published no date"),
    ]
    for shape in shapes:
        assert validate_source_temporal(shape) == shape


def test_source_temporal_year_precision_is_v2_only():
    """v2 adds ``year``; the v1 frozenset must be left exactly as it was."""
    year = source_temporal_year(2025)
    assert year["precision"] == "year"
    event = _event()
    event["date_precision"] = "year"
    with pytest.raises(ContractError, match="date_precision must be one of"):
        validate_bitemporal_event(event)


def test_source_temporal_rejects_every_precision_bound_rule_mispairing():
    for precision, allowed in _PRECISION_TO_RULES.items():
        for bound_rule in sorted(_BOUND_RULES - allowed):
            with pytest.raises(ContractError, match="is not the bound rule for precision"):
                build_source_temporal(
                    available=True,
                    precision=precision,
                    bound_rule=bound_rule,
                    lower_bound="2025-03-01T00:00:00Z",
                    upper_bound="2025-03-31T23:59:59Z",
                )


def test_source_temporal_rejects_unordered_bounds():
    with pytest.raises(ContractError, match="upper_bound cannot precede"):
        source_temporal_range(
            "2025-06-30T00:00:00Z", "2025-03-01T00:00:00Z", original_value="backwards"
        )


def test_source_temporal_exact_time_requires_collapsed_bounds():
    with pytest.raises(ContractError, match="exact_time requires lower_bound to equal upper_bound"):
        build_source_temporal(
            available=True,
            precision="exact_time",
            bound_rule="exact_instant",
            lower_bound="2025-03-01T00:00:00Z",
            upper_bound="2025-03-01T00:00:01Z",
        )


def test_source_temporal_unavailable_cannot_smuggle_a_bound():
    with pytest.raises(ContractError, match="bounds must be null when available is false"):
        build_source_temporal(
            available=False,
            precision="unknown",
            bound_rule="unavailable",
            unavailable_reason="source published no date",
            lower_bound="2025-03-01T00:00:00Z",
        )


def test_source_temporal_unavailable_cannot_carry_an_original_value():
    with pytest.raises(ContractError, match="original_value must be null when available is false"):
        build_source_temporal(
            available=False,
            precision="unknown",
            bound_rule="unavailable",
            unavailable_reason="source published no date",
            original_value="2025-Q3",
        )


def test_source_temporal_unavailable_requires_a_stated_reason():
    with pytest.raises(ContractError, match="unavailable_reason must be a non-empty string"):
        build_source_temporal(available=False, precision="unknown", bound_rule="unavailable")


def test_source_temporal_available_cannot_carry_an_unavailable_reason():
    with pytest.raises(ContractError, match="unavailable_reason must be null when available"):
        build_source_temporal(
            available=True,
            precision="exact_time",
            bound_rule="exact_instant",
            unavailable_reason="not really",
            lower_bound="2025-03-01T00:00:00Z",
            upper_bound="2025-03-01T00:00:00Z",
        )


def test_source_temporal_unparsed_keeps_the_words_without_bounds():
    unparsed = source_temporal_unparsed("first half, subject to enrolment")
    assert unparsed["available"] is True
    assert unparsed["original_value"] == "first half, subject to enrolment"
    assert unparsed["lower_bound"] is None and unparsed["upper_bound"] is None
    with pytest.raises(ContractError, match="bounds must be null when the source value is unparsed"):
        build_source_temporal(
            available=True,
            precision="unknown",
            bound_rule="unparsed",
            original_value="first half",
            lower_bound="2025-01-01T00:00:00Z",
            upper_bound="2025-06-30T00:00:00Z",
        )


def test_source_temporal_rejects_a_smuggled_single_instant_key():
    temporal = source_temporal_month(2025, 3)
    temporal["value"] = "2025-03-15T00:00:00Z"
    with pytest.raises(ContractError, match="unsupported keys"):
        validate_source_temporal(temporal)


def test_source_temporal_month_span_tracks_the_leap_day():
    assert _utc(source_temporal_month(2024, 2)["upper_bound"]) == _utc("2024-02-29T23:59:59.999999Z")
    assert _utc(source_temporal_month(2025, 2)["upper_bound"]) == _utc("2025-02-28T23:59:59.999999Z")


def test_source_temporal_quarter_span_covers_its_three_whole_months():
    q1 = source_temporal_quarter(2025, 1)
    assert _utc(q1["lower_bound"]) == _utc("2025-01-01T00:00:00Z")
    assert _utc(q1["upper_bound"]) == _utc("2025-03-31T23:59:59.999999Z")
    q4 = source_temporal_quarter(2024, 4)
    assert _utc(q4["lower_bound"]) == _utc("2024-10-01T00:00:00Z")
    assert _utc(q4["upper_bound"]) == _utc("2024-12-31T23:59:59.999999Z")


def test_source_temporal_year_span_covers_the_whole_calendar_year():
    year = source_temporal_year(2025)
    assert _utc(year["lower_bound"]) == _utc("2025-01-01T00:00:00Z")
    assert _utc(year["upper_bound"]) == _utc("2025-12-31T23:59:59.999999Z")


def test_source_temporal_span_honours_a_declared_source_timezone():
    """A New York March is the New York calendar month, shifted into UTC."""
    local = source_temporal_month(2025, 3, source_timezone="America/New_York")
    utc = source_temporal_month(2025, 3)
    assert local["source_timezone"] == "America/New_York"
    assert utc["source_timezone"] is None
    # 2025-03-01 is EST (-05:00); 2025-03-31 is EDT (-04:00) after the DST shift.
    assert _utc(local["lower_bound"]) == _utc("2025-03-01T05:00:00Z")
    assert _utc(local["upper_bound"]) == _utc("2025-04-01T03:59:59.999999Z")
    assert (_utc(local["lower_bound"]) - _utc(utc["lower_bound"])).total_seconds() == 5 * 3600


def test_source_temporal_study_eligibility_admits_imprecision_not_absence():
    assert source_temporal_is_study_eligible(source_temporal_month(2025, 3)) is True
    assert source_temporal_is_study_eligible(source_temporal_quarter(2025, 3)) is True
    assert source_temporal_is_study_eligible(source_temporal_unparsed("soon")) is False
    assert source_temporal_is_study_eligible(source_temporal_unavailable("no date")) is False


def test_source_temporal_span_seconds_measures_width_or_returns_none():
    assert source_temporal_span_seconds(source_temporal_exact("2025-03-01T00:00:00Z")) == 0.0
    assert source_temporal_span_seconds(source_temporal_day("2025-03-01")) == pytest.approx(
        86399.999999
    )
    assert source_temporal_span_seconds(source_temporal_unavailable("no date")) is None
    assert source_temporal_span_seconds(source_temporal_unparsed("soon")) is None


def test_bitemporal_event_v2_accepts_a_future_effective_span():
    event = _event_v2()
    assert event["schema"] == BIOTEMPORAL_EVENT_V2_SCHEMA
    assert event["source_effective"]["lower_bound"].startswith("2027-")
    assert validate_bitemporal_event_v2(event) == event


def test_bitemporal_event_v2_mirrors_source_effective_precision():
    event = _event_v2()
    assert event["date_precision"] == event["source_effective"]["precision"] == "exact_date"
    event["date_precision"] = "exact_time"
    with pytest.raises(ContractError, match="date_precision must mirror source_effective"):
        validate_bitemporal_event_v2(event)


def test_bitemporal_event_v2_rejects_knowledge_before_ingestion():
    with pytest.raises(ContractError, match="known_at cannot precede ingested_at"):
        _event_v2(known_at="2026-07-30T20:04:00Z")


def test_bitemporal_event_v2_rejects_ingestion_before_earliest_publication():
    with pytest.raises(ContractError, match="ingested_at cannot precede source_published"):
        _event_v2(source_published=source_temporal_month(2026, 9))


def test_bitemporal_event_v2_allows_a_late_ingest_of_an_old_document():
    """Only the lower bound is constrained: a March filing is ingested in June."""
    event = _event_v2(
        source_published=source_temporal_month(2026, 3),
        ingested_at="2026-06-01T00:00:00Z",
        known_at="2026-06-01T00:00:00Z",
    )
    assert event["source_published"]["precision"] == "month"


def test_bitemporal_event_v2_rejects_unknown_event_type():
    with pytest.raises(ContractError, match="event_type must be one of"):
        _event_v2(event_type="fda_pdufa")


def test_bitemporal_event_v2_rejects_unknown_status():
    with pytest.raises(ContractError, match="status must be one of"):
        _event_v2(status="active")


def test_bitemporal_event_v2_allowlists_are_closed_sets():
    assert "other" not in EVENT_TYPE_ALLOWLIST_V2
    assert "other" not in EVENT_STATUS_ALLOWLIST_V2
    assert "unknown" in EVENT_STATUS_ALLOWLIST_V2
    assert "unknown" not in EVENT_TYPE_ALLOWLIST_V2


def test_bitemporal_event_v2_rejects_a_self_superseding_revision():
    with pytest.raises(ContractError, match="supersedes must differ from"):
        _event_v2(revision={"revision_id": "rev:2", "revision_index": 1, "supersedes": "rev:2"})


def test_upgrade_v1_to_v2_preserves_every_instant_as_a_collapsed_span():
    upgraded = upgrade_event_v1_to_v2(_event_v1_exact())
    assert upgraded["schema"] == BIOTEMPORAL_EVENT_V2_SCHEMA
    assert upgraded["source_published"]["bound_rule"] == "exact_instant"
    assert upgraded["source_published"]["lower_bound"] == upgraded["source_published"]["upper_bound"]
    assert upgraded["scheduled_window"]["precision"] == "range"
    assert upgraded["actual"] is None
    assert upgraded["revision"] == {
        "revision_id": "evt:issuer-1:pdufa-2027-01",
        "revision_index": 0,
        "supersedes": None,
    }


def test_upgrade_records_the_precision_v1_declared_not_the_instant_v1_forced():
    """v1's instant is the manufactured field; ``date_precision`` is the honest one."""
    event = _event()
    event["event_type"] = "pdufa_date"
    upgraded = upgrade_event_v1_to_v2(event)
    assert event["date_precision"] == "exact_date"
    assert upgraded["date_precision"] == "exact_date"
    assert upgraded["source_effective"]["bound_rule"] == "day_span"
    assert _utc(upgraded["source_effective"]["lower_bound"]) == _utc("2027-01-15T00:00:00Z")
    assert _utc(upgraded["source_effective"]["upper_bound"]) == _utc(
        "2027-01-15T23:59:59.999999Z"
    )


def test_upgrade_never_ratchets_a_coarse_v1_row_into_a_certified_instant():
    """A Q3 midpoint is the fabrication v1 forced — the upgrade must not bless it."""
    event = _event()
    event["event_type"] = "pdufa_date"
    event["date_precision"] = "quarter"
    event["effective_at"] = "2025-08-15T12:00:00Z"  # the Q3-2025 midpoint v1 demanded
    event["scheduled_start"] = None
    event["scheduled_end"] = None
    upgraded = upgrade_event_v1_to_v2(event)
    assert upgraded["date_precision"] == "quarter"
    assert upgraded["source_effective"]["bound_rule"] == "quarter_span"
    assert _utc(upgraded["source_effective"]["lower_bound"]) == _utc("2025-07-01T00:00:00Z")
    assert _utc(upgraded["source_effective"]["upper_bound"]) == _utc(
        "2025-09-30T23:59:59.999999Z"
    )
    # The widening is auditable: the instant v1 stored is kept verbatim.
    assert upgraded["source_effective"]["original_value"] == "2025-08-15T12:00:00Z"
    assert source_temporal_span_seconds(upgraded["source_effective"]) > 0.0
    # ... and the round trip cannot launder it back out through the downgrade.
    with pytest.raises(ContractError, match="source_effective cannot be downgraded"):
        downgrade_event_v2_to_v1(upgraded)


def test_upgrade_lifts_a_width_v1_cannot_carry_as_unparsed_not_as_bounds():
    for precision in ("range", "unknown"):
        event = _event()
        event["event_type"] = "pdufa_date"
        event["date_precision"] = precision
        upgraded = upgrade_event_v1_to_v2(event)
        temporal = upgraded["source_effective"]
        assert temporal["bound_rule"] == "unparsed"
        assert temporal["original_value"] == "2027-01-15T00:00:00Z"
        assert temporal["lower_bound"] is None and temporal["upper_bound"] is None
        assert source_temporal_is_study_eligible(temporal) is False


def test_upgrade_keeps_publication_exact_because_v1_asserts_it_exactly():
    """``date_precision`` describes the event date, never the document timestamp."""
    event = _event()
    event["event_type"] = "pdufa_date"
    event["date_precision"] = "quarter"
    upgraded = upgrade_event_v1_to_v2(event)
    assert upgraded["source_published"]["precision"] == "exact_time"
    assert upgraded["source_published"]["original_value"] == "2026-07-30T20:00:00Z"


def test_upgrade_records_the_v1_pair_that_declared_the_scheduled_window():
    upgraded = upgrade_event_v1_to_v2(_event_v1_exact())
    assert upgraded["scheduled_window"]["bound_rule"] == "source_declared_range"
    assert (
        upgraded["scheduled_window"]["original_value"]
        == "2027-01-15T00:00:00Z/2027-01-15T23:59:59Z"
    )


def test_upgrade_writes_a_zero_width_v1_schedule_as_an_instant_not_a_range():
    event = _event_v1_exact()
    event["scheduled_end"] = event["scheduled_start"]
    upgraded = upgrade_event_v1_to_v2(event)
    assert upgraded["scheduled_window"]["bound_rule"] == "exact_instant"


def test_upgrade_refuses_an_event_type_outside_the_v2_allowlist():
    with pytest.raises(ContractError, match="event_type must be one of"):
        upgrade_event_v1_to_v2(_event())


def test_upgrade_refuses_a_status_outside_the_v2_allowlist():
    event = _event_v1_exact()
    event["status"] = "active"
    with pytest.raises(ContractError, match="status must be one of"):
        upgrade_event_v1_to_v2(event)


def test_v1_to_v2_to_v1_round_trip_is_lossless_for_an_exact_v1_event():
    """Only an event whose v1 fields matched its declared precision round-trips.

    A coarser v1 row widens on the way up (see the ratchet test above) and is
    then refused on the way down, which is the point: v1's fabricated instant is
    not re-fabricated.
    """
    original = _event_v1_exact()
    assert downgrade_event_v2_to_v1(upgrade_event_v1_to_v2(original)) == original


def test_downgrade_refuses_an_imprecise_event_and_names_the_field():
    event = _event_v2(source_effective=source_temporal_month(2027, 1))
    with pytest.raises(ContractError, match="source_effective cannot be downgraded"):
        downgrade_event_v2_to_v1(event)


def test_downgrade_refuses_an_unavailable_temporal():
    event = _event_v2(source_published=source_temporal_unavailable("no publication date"))
    with pytest.raises(ContractError, match="source_published cannot be downgraded"):
        downgrade_event_v2_to_v1(event)


def test_canonical_hash_ignores_equivalent_timestamp_spellings():
    zulu = _event_v2(source_published=source_temporal_exact("2026-07-30T20:00:00Z"))
    offset = _event_v2(source_published=source_temporal_exact("2026-07-30T20:00:00+00:00"))
    shifted = _event_v2(source_published=source_temporal_exact("2026-07-30T16:00:00-04:00"))
    assert zulu["source_published"]["lower_bound"] != offset["source_published"]["lower_bound"]
    assert event_v2_content_hash(zulu) == event_v2_content_hash(offset)
    assert event_v2_content_hash(zulu) == event_v2_content_hash(shifted)


def test_canonical_hash_changes_on_a_semantic_change():
    baseline = event_v2_content_hash(_event_v2())
    assert event_v2_content_hash(_event_v2(status="confirmed")) != baseline
    assert event_v2_content_hash(_event_v2(certainty=0.8)) != baseline
    assert event_v2_content_hash(_event_v2(source_effective=source_temporal_day("2027-01-16"))) != baseline


def test_event_v2_replay_is_byte_deterministic():
    assert canonical_event_v2_bytes(_event_v2()) == canonical_event_v2_bytes(_event_v2())
    assert event_v2_content_hash(_event_v2()).startswith("sha256:")
    assert len(event_v2_content_hash(_event_v2())) == len("sha256:") + 64


# --- calendar spans in zones whose offset moves at midnight -----------------


def test_calendar_span_keeps_the_last_local_hour_when_clocks_go_back_at_midnight():
    """Cairo ends DST at 00:00, so naming the upper edge ``23:59:59`` loses an hour."""
    day = source_temporal_day("2025-10-30", source_timezone="Africa/Cairo")
    next_day = source_temporal_day("2025-10-31", source_timezone="Africa/Cairo")
    upper = _utc(day["upper_bound"])
    assert upper == _utc("2025-10-30T21:59:59.999999Z")
    # Contiguous: the span ends exactly one microsecond before the next begins.
    assert (_utc(next_day["lower_bound"]) - upper).total_seconds() == pytest.approx(1e-06)
    assert (upper - _utc(day["lower_bound"])).total_seconds() == pytest.approx(
        25 * 3600 - 1e-06
    )
    # A real 23:30 local instant on the second pass falls inside its own day.
    late = datetime(2025, 10, 30, 23, 30, tzinfo=ZoneInfo("Africa/Cairo"), fold=1)
    assert _utc(day["lower_bound"]) <= late.astimezone(timezone.utc) <= upper


def test_calendar_month_spans_are_contiguous_across_a_midnight_transition():
    october = source_temporal_month(2024, 10, source_timezone="Africa/Cairo")
    november = source_temporal_month(2024, 11, source_timezone="Africa/Cairo")
    assert (
        _utc(november["lower_bound"]) - _utc(october["upper_bound"])
    ).total_seconds() == pytest.approx(1e-06)


def test_calendar_span_records_a_wall_time_the_zone_actually_had():
    """Cairo skips 00:00 on 2025-04-25; the stored lower bound must not assert it."""
    day = source_temporal_day("2025-04-25", source_timezone="Africa/Cairo")
    assert day["lower_bound"].startswith("2025-04-25T01:00:00+03:00")
    assert _utc(day["lower_bound"]) == _utc("2025-04-24T22:00:00Z")


# --- bound rules are checked, not merely labelled ---------------------------


def test_source_temporal_refuses_a_month_span_collapsed_to_one_instant():
    with pytest.raises(ContractError, match="not the month_span they claim"):
        build_source_temporal(
            available=True,
            precision="month",
            bound_rule="month_span",
            lower_bound="2025-03-15T12:00:00Z",
            upper_bound="2025-03-15T12:00:00Z",
        )


def test_source_temporal_refuses_calendar_bounds_that_do_not_match_their_rule():
    mismatches = [
        # a day_span covering four years
        ("exact_date", "day_span", "2022-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        # a quarter_span that does not start on a quarter
        ("quarter", "quarter_span", "2025-08-14T06:12:00Z", "2025-08-14T06:13:00Z"),
        # an exclusive upper end for a day
        ("exact_date", "day_span", "2025-09-17T00:00:00Z", "2025-09-18T00:00:00Z"),
        # a year_span spanning a century
        ("year", "year_span", "1970-01-01T00:00:00Z", "2099-12-31T00:00:00Z"),
        # a month_span one day short of its month
        ("month", "month_span", "2025-03-01T00:00:00Z", "2025-03-30T23:59:59.999999Z"),
    ]
    for precision, bound_rule, lower, upper in mismatches:
        with pytest.raises(ContractError, match=f"not the {bound_rule} they claim"):
            build_source_temporal(
                available=True,
                precision=precision,
                bound_rule=bound_rule,
                lower_bound=lower,
                upper_bound=upper,
            )


def test_source_temporal_refuses_bounds_that_contradict_the_declared_zone():
    tokyo_bounds = source_temporal_day("2025-09-17", source_timezone="Asia/Tokyo")
    with pytest.raises(ContractError, match="not the day_span they claim"):
        build_source_temporal(
            available=True,
            precision="exact_date",
            bound_rule="day_span",
            lower_bound=tokyo_bounds["lower_bound"],
            upper_bound=tokyo_bounds["upper_bound"],
            source_timezone="America/New_York",
        )


def test_source_temporal_accepts_an_equivalent_spelling_of_a_calendar_span():
    """The rule check compares instants, so a UTC re-spelling still validates."""
    local = source_temporal_month(2025, 3, source_timezone="America/New_York")
    respelled = build_source_temporal(
        available=True,
        precision="month",
        bound_rule="month_span",
        lower_bound="2025-03-01T05:00:00Z",
        upper_bound="2025-04-01T03:59:59.999999Z",
        source_timezone="America/New_York",
    )
    assert _utc(respelled["lower_bound"]) == _utc(local["lower_bound"])
    assert _utc(respelled["upper_bound"]) == _utc(local["upper_bound"])


# --- timezones, keys, and evidence ------------------------------------------


def test_source_temporal_rejects_an_unknown_iana_timezone_on_both_paths():
    with pytest.raises(ContractError, match="must be a known IANA timezone"):
        source_temporal_month(2025, 3, source_timezone="Mars/Olympus")
    temporal = source_temporal_month(2025, 3, source_timezone="America/New_York")
    temporal["source_timezone"] = "Mars/Olympus"
    with pytest.raises(ContractError, match="must be a known IANA timezone"):
        validate_source_temporal(temporal)


def test_source_temporal_rejects_an_unknown_timezone_on_a_non_calendar_rule():
    """The calendar check resolves the zone anyway; every other rule does not.

    A silent fallback here would leave ``source_timezone`` asserting a zone the
    payload was never evaluated in — the inference the module promises never to
    make.
    """
    with pytest.raises(ContractError, match="must be a known IANA timezone"):
        source_temporal_range(
            "2025-01-01T00:00:00Z",
            "2025-06-30T00:00:00Z",
            original_value="H1 2025",
            source_timezone="Mars/Olympus",
        )
    with pytest.raises(ContractError, match="must be a known IANA timezone"):
        build_source_temporal(
            available=True,
            precision="exact_time",
            bound_rule="exact_instant",
            lower_bound="2025-03-01T00:00:00Z",
            upper_bound="2025-03-01T00:00:00Z",
            source_timezone="Mars/Olympus",
        )
    with pytest.raises(ContractError, match="must be a known IANA timezone"):
        build_source_temporal(
            available=True,
            precision="unknown",
            bound_rule="unparsed",
            original_value="first half",
            source_timezone="Mars/Olympus",
        )


def test_source_temporal_rejects_a_missing_key_with_a_contract_error():
    """A hand-authored or deserialised dict is the realistic malformed input."""
    temporal = source_temporal_month(2025, 3)
    temporal.pop("bound_rule")
    with pytest.raises(ContractError, match="missing required keys"):
        validate_source_temporal(temporal)
    with pytest.raises(ContractError, match="missing required keys"):
        validate_source_temporal({})


def test_source_declared_range_requires_the_words_the_source_declared():
    with pytest.raises(ContractError, match="original_value must be a non-empty string"):
        build_source_temporal(
            available=True,
            precision="range",
            bound_rule="source_declared_range",
            lower_bound="2025-01-01T00:00:00Z",
            upper_bound="2025-12-31T23:59:59Z",
        )


def test_source_declared_range_cannot_collapse_to_a_single_instant():
    with pytest.raises(ContractError, match="collapsed to one instant"):
        source_temporal_range(
            "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z", original_value="H1 2025"
        )


def test_source_temporal_day_requires_a_zero_padded_calendar_date():
    with pytest.raises(ContractError, match="ISO-8601 calendar date"):
        source_temporal_day("2025-3-9")
    assert source_temporal_day("2025-03-09")["original_value"] == "2025-03-09"


def test_calendar_builders_raise_contract_errors_on_unrepresentable_years():
    for call in (
        lambda: source_temporal_year(0),
        lambda: source_temporal_year(10000),
        lambda: source_temporal_month(0, 1),
        lambda: source_temporal_quarter(99999, 1),
    ):
        with pytest.raises(ContractError, match=r"year must be an integer in \[1, 9999\]"):
            call()


# --- the v2 event key set, lineage, and PIT invariants ----------------------


def test_bitemporal_event_v2_rejects_a_smuggled_top_level_instant():
    event = _event_v2(source_effective=source_temporal_quarter(2027, 1))
    event["effective_at"] = "2027-02-14T12:00:00Z"
    with pytest.raises(ContractError, match="unsupported keys"):
        validate_bitemporal_event_v2(event)
    with pytest.raises(ContractError, match="unsupported keys"):
        canonical_event_v2_bytes(event)


def test_bitemporal_event_v2_rejects_a_missing_key():
    event = _event_v2()
    event.pop("certainty")
    with pytest.raises(ContractError, match="missing required keys"):
        validate_bitemporal_event_v2(event)


def test_bitemporal_event_v2_rejects_authority_shaped_revision_keys():
    with pytest.raises(ContractError, match="revision carries unsupported keys"):
        _event_v2(
            revision={
                "revision_id": "rev:1",
                "revision_index": 0,
                "supersedes": None,
                "may_rank": True,
            }
        )


def test_bitemporal_event_v2_rejects_a_malformed_revision_index():
    for index in (-3, "first", 1.5, True):
        with pytest.raises(ContractError, match="revision.revision_index"):
            _event_v2(revision={"revision_id": "rev:1", "revision_index": index, "supersedes": None})
    with pytest.raises(ContractError, match="revision.revision_id"):
        _event_v2(revision={"revision_id": "", "revision_index": 0, "supersedes": None})


def test_bitemporal_event_v2_rejects_an_actual_that_precedes_nothing_we_knew():
    """An event cannot be known five years before the window it occurred in."""
    with pytest.raises(ContractError, match="known_at cannot precede actual"):
        _event_v2(status="occurred", actual=source_temporal_year(2030))


def test_bitemporal_event_v2_allows_a_coarse_actual_that_extends_past_known_at():
    event = _event_v2(
        status="occurred",
        known_at="2026-07-30T20:05:00Z",
        actual=source_temporal_month(2026, 7),
    )
    assert event["actual"]["precision"] == "month"


def test_pit_leakage_marker_reports_when_the_publication_check_could_not_run():
    assert event_v2_pit_leakage_is_checkable(_event_v2()) is True
    unparsed = _event_v2(source_published=source_temporal_unparsed("published sometime in 2026"))
    assert event_v2_pit_leakage_is_checkable(unparsed) is False
    unavailable = _event_v2(source_published=source_temporal_unavailable("no publication date"))
    assert event_v2_pit_leakage_is_checkable(unavailable) is False


# --- what the replay hash actually covers -----------------------------------


def _shuffled(payload):
    """Re-insert every key in reverse order, recursively."""
    if isinstance(payload, dict):
        return {key: _shuffled(payload[key]) for key in sorted(payload, reverse=True)}
    return payload


def test_canonical_hash_is_stable_under_key_insertion_order():
    event = _event_v2()
    permuted = _shuffled(event)
    assert list(permuted) != list(event)
    assert list(permuted["source_effective"]) != list(event["source_effective"])
    assert canonical_event_v2_bytes(permuted) == canonical_event_v2_bytes(event)


def test_canonical_hash_covers_revision_lineage():
    baseline = event_v2_content_hash(_event_v2())
    superseding = _event_v2(
        revision={"revision_id": "rev:2", "revision_index": 1, "supersedes": "rev:1"}
    )
    assert event_v2_content_hash(superseding) != baseline


def test_canonical_hash_covers_every_field_the_payload_carries():
    event = _event_v2()
    canonical = json.loads(canonical_event_v2_bytes(event).decode("utf-8"))
    assert set(canonical) == set(event)
    baseline = event_v2_content_hash(event)
    variants = {
        "event_id": {"event_id": "evt:issuer-1:pdufa-2027-02"},
        "issuer_id": {"issuer_id": "issuer:2"},
        "event_type": {"event_type": "advisory_committee"},
        "source_class": {"source_class": "press_aggregator"},
        "source_url": {"source_url": "https://example.test/other"},
        "source_hash": {"source_hash": _HASH_B},
        "known_at": {"known_at": "2026-07-30T21:05:00Z"},
        "ingested_at": {
            "ingested_at": "2026-07-30T20:06:00Z",
            "known_at": "2026-07-30T20:06:00Z",
        },
        "scheduled_window": {"scheduled_window": source_temporal_quarter(2027, 2)},
        "actual": {"actual": source_temporal_unavailable("still pending")},
    }
    for field, overrides in variants.items():
        assert event_v2_content_hash(_event_v2(**overrides)) != baseline, field


# --- downgrading an honestly absent optional field --------------------------


def test_downgrade_maps_an_unavailable_optional_field_to_v1_null():
    """v1's ``actual_at`` is nullable, so recorded absence maps losslessly."""
    event = _event_v2(
        source_effective=source_temporal_exact("2027-01-15T00:00:00Z"),
        scheduled_window=None,
        actual=source_temporal_unavailable("event has not occurred yet"),
    )
    downgraded = downgrade_event_v2_to_v1(event)
    assert downgraded["actual_at"] is None
    assert downgraded["scheduled_start"] is None and downgraded["scheduled_end"] is None


def test_downgrade_still_refuses_an_unparsed_optional_field():
    """Absence maps to null; words the source did say have nowhere to go in v1."""
    event = _event_v2(
        source_effective=source_temporal_exact("2027-01-15T00:00:00Z"),
        scheduled_window=None,
        actual=source_temporal_unparsed("shortly after the readout"),
    )
    with pytest.raises(ContractError, match="actual cannot be downgraded"):
        downgrade_event_v2_to_v1(event)
