"""Isolated governance for the B4 Company-Facts-to-iXBRL evidence bridge.

This module does not normalize a financial metric.  It creates one frozen,
single-concept query receipt whose only purpose is to select a
``dimensions_known=false`` SEC Company Facts occurrence for exact B3/B4 source
correspondence.  The contract is deliberately confidence-D, review-required,
formula-free, and isolated from the 50-metric core catalog.
"""
from __future__ import annotations

from datetime import datetime

from .metric_registry import (
    ATTESTED_OCCURRENCE_ALLOWED_FORMS,
    ATTESTED_OCCURRENCE_AVAILABLE_AT,
    ATTESTED_OCCURRENCE_CATALOG_ID,
    ATTESTED_OCCURRENCE_DIMENSIONAL_MODE,
    ATTESTED_OCCURRENCE_MAPPING_PACK_ID,
    ATTESTED_OCCURRENCE_METRIC_ID,
    ATTESTED_OCCURRENCE_NO_RESULT_CODES,
    KNOWN_CONCEPT_ALLOWLIST,
    ConceptAlias,
    DimensionalProfile,
    GovernanceBundle,
    GovernanceLane,
    ImmutableRule,
    MappingRule,
    MetricContract,
    NoResultPolicy,
    PeriodConstraints,
    PresentationConstraints,
    ReviewPolicy,
)
from .models import parse_utc
from .raw_ledger import RawFactOccurrence


ATTESTED_OCCURRENCE_GOVERNANCE_AVAILABLE_AT = ATTESTED_OCCURRENCE_AVAILABLE_AT


class AttestedOccurrenceGovernanceError(ValueError):
    """A raw occurrence cannot enter the isolated evidence bridge."""


def _canonical_unit(occurrence: RawFactOccurrence) -> str:
    unit = occurrence.unit
    if unit is None:
        raise AttestedOccurrenceGovernanceError("evidence occurrence requires a unit")
    numerator = tuple(str(item).strip() for item in unit.measures)
    denominator = tuple(str(item).strip() for item in unit.denominator_measures)
    usd = {"USD", "iso4217:USD"}
    shares = {"share", "shares", "xbrli:shares"}
    if len(numerator) == 1 and numerator[0] in usd and not denominator:
        return "USD"
    if len(numerator) == 1 and numerator[0] in shares and not denominator:
        return "shares"
    if (
        len(numerator) == 1
        and numerator[0] in usd
        and len(denominator) == 1
        and denominator[0] in shares
    ):
        return "USD/shares"
    raise AttestedOccurrenceGovernanceError(
        "evidence occurrence unit is outside the governed bridge"
    )


def build_attested_occurrence_governance_bundle(
    *, occurrence: RawFactOccurrence, recorded_at: str | datetime
) -> GovernanceBundle:
    """Freeze a one-concept, dimensions-unknown evidence selection contract."""
    if type(occurrence) is not RawFactOccurrence:
        raise AttestedOccurrenceGovernanceError(
            "occurrence must be an exact RawFactOccurrence"
        )
    if occurrence.source.source != "sec-companyfacts":
        raise AttestedOccurrenceGovernanceError(
            "evidence bridge accepts only SEC Company Facts occurrences"
        )
    if occurrence.dimensions_known is not False:
        raise AttestedOccurrenceGovernanceError(
            "evidence bridge requires dimensions_known=false"
        )
    if occurrence.context.explicit_dimensions or occurrence.context.typed_dimensions:
        raise AttestedOccurrenceGovernanceError(
            "dimensions-unknown occurrence cannot assert context members"
        )
    if occurrence.concept_qname.count(":") != 1:
        raise AttestedOccurrenceGovernanceError(
            "evidence occurrence concept must be a standard QName"
        )
    taxonomy, concept = occurrence.concept_qname.split(":", 1)
    known = KNOWN_CONCEPT_ALLOWLIST.get((taxonomy, concept))
    if known is None:
        raise AttestedOccurrenceGovernanceError(
            "evidence occurrence concept is outside the governed allowlist"
        )
    unit = _canonical_unit(occurrence)
    if known.contract_units != (unit,):
        raise AttestedOccurrenceGovernanceError(
            "evidence occurrence unit does not match governed concept metadata"
        )
    period_kind = "instant" if occurrence.context.instant is not None else "duration"
    if known.period_kind != period_kind:
        raise AttestedOccurrenceGovernanceError(
            "evidence occurrence period does not match governed concept metadata"
        )
    cutoff = parse_utc(recorded_at, field="recorded_at")
    available = parse_utc(
        ATTESTED_OCCURRENCE_GOVERNANCE_AVAILABLE_AT,
        field="attested_occurrence_governance_available_at",
    )
    if cutoff is None or available is None or cutoff < available:
        raise AttestedOccurrenceGovernanceError(
            "evidence governance is not visible at recorded_at"
        )
    metric_rule = ImmutableRule(
        rule_id="metric.attested_occurrence/v1",
        version="1.0.0",
        available_at=available,
        confidence="D",
    )
    mapping_rule = MappingRule(
        metric_id=ATTESTED_OCCURRENCE_METRIC_ID,
        rule=ImmutableRule(
            rule_id="mapping.attested_occurrence/v1",
            version="1.0.0",
            available_at=available,
            confidence="D",
        ),
        taxonomy_concept_aliases=(
            ConceptAlias(
                taxonomy=taxonomy,
                concept=concept,
                priority=1,
                taxonomy_version_start=known.taxonomy_version_start,
                taxonomy_version_end=known.taxonomy_version_end,
            ),
        ),
    )
    period = PeriodConstraints(
        kind=period_kind,
        allowed_forms=ATTESTED_OCCURRENCE_ALLOWED_FORMS,
        min_duration_days=1 if period_kind == "duration" else None,
        max_duration_days=400 if period_kind == "duration" else None,
    )
    contract = MetricContract(
        metric_id=ATTESTED_OCCURRENCE_METRIC_ID,
        label="Attested SEC source occurrence",
        category="evidence_bridge",
        rule=metric_rule,
        units=(unit,),
        period_constraints=period,
        dimensional_profile=DimensionalProfile(
            mode=ATTESTED_OCCURRENCE_DIMENSIONAL_MODE,
            allowed_axes=(),
            require_dimensions=False,
            allow_member_selection=False,
        ),
        presentation_constraints=PresentationConstraints(
            statement="derived",
            sign_convention="as_reported",
            display_scale="native",
            comparability="same_unit_same_period",
        ),
        review=ReviewPolicy(
            required=True,
            triggers=("unknown_dimension_scope", "source_correspondence_only"),
        ),
        no_result=NoResultPolicy(
            mode="withhold",
            codes=ATTESTED_OCCURRENCE_NO_RESULT_CODES,
        ),
        declared_formula_dependencies=(),
        mappings=(mapping_rule,),
        formula=None,
    )
    return GovernanceBundle(
        schema="fundamental_forensics.governance_bundle/v1",
        recorded_at=cutoff,
        catalog=GovernanceLane(
            lane="catalog",
            identifier=ATTESTED_OCCURRENCE_CATALOG_ID,
            version="1.0.0",
            available_at=available,
        ),
        mapping_pack=GovernanceLane(
            lane="mapping_pack",
            identifier=ATTESTED_OCCURRENCE_MAPPING_PACK_ID,
            version="1.0.0",
            available_at=available,
        ),
        formula_pack=None,
        contracts=(contract,),
    )


__all__ = [
    "ATTESTED_OCCURRENCE_GOVERNANCE_AVAILABLE_AT",
    "AttestedOccurrenceGovernanceError",
    "build_attested_occurrence_governance_bundle",
]
