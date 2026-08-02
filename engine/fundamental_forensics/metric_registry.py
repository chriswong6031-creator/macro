"""Governed, versioned contracts for the first core GAAP metric registry.

This module deliberately does *not* normalize facts or calculate formulas.  It
loads the immutable rules that later lanes must obey.  A bad catalog is rejected
at load time rather than being interpreted as an implicit fallback at runtime.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import hmac
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import yaml

from .models import canonical_json, parse_utc, utc_text


CATALOG_SCHEMA = "fundamental_forensics.metric_catalog/v1"
MAPPINGS_SCHEMA = "fundamental_forensics.metric_mappings/v1"
FORMULAS_SCHEMA = "fundamental_forensics.metric_formulas/v1"
GOVERNANCE_BUNDLE_SCHEMA = "fundamental_forensics.governance_bundle/v1"
GOVERNANCE_BUNDLE_PROJECTION_VERSION = "1.0.0"
CORE_V1_CATALOG_ID = "fundamental_forensics_core_gaap_metrics"
CORE_V1_METRIC_COUNT = 50
CORE_V1_DIRECT_METRIC_COUNT = 40
CORE_V1_FORMULA_METRIC_COUNT = 10
ALLOWED_CONFIDENCE = frozenset({"A", "B", "C", "D"})
ALLOWED_UNITS = frozenset({"USD", "shares", "USD/shares", "ratio"})
ALLOWED_PERIOD_KINDS = frozenset({"duration", "instant"})
ALLOWED_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})
ALLOWED_TAXONOMIES = frozenset({"us-gaap", "dei"})
ALLOWED_STATEMENTS = frozenset(
    {"income_statement", "cash_flow_statement", "balance_sheet", "derived"}
)
ALLOWED_ALIGNMENTS = frozenset({"same_period", "ending_instant_to_duration"})
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_CONCEPT = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

# Governance bundles are an authenticated query receipt, not a bulk registry
# transport.  The v1 registry itself has exactly 50 metrics; the other limits
# leave room for append-only future rules while making a public receipt parser
# bounded before it turns decoded JSON lists into tuples or graphs.
MAX_GOVERNANCE_BUNDLE_METRICS = CORE_V1_METRIC_COUNT
MAX_GOVERNANCE_BUNDLE_MAPPINGS = 256
MAX_GOVERNANCE_BUNDLE_FORMULAS = CORE_V1_METRIC_COUNT
MAX_GOVERNANCE_BUNDLE_ALIASES_PER_MAPPING = 32
MAX_GOVERNANCE_BUNDLE_DEPENDENCIES = CORE_V1_METRIC_COUNT
MAX_GOVERNANCE_BUNDLE_WIRE_TEXT_CHARS = 4096
MAX_GOVERNANCE_BUNDLE_WIRE_BYTES = 1_000_000
MAX_GOVERNANCE_BUNDLE_WIRE_DEPTH = 12
MAX_GOVERNANCE_BUNDLE_WIRE_OBJECT_FIELDS = 32


@dataclass(frozen=True)
class ImmutableRule:
    """An addressable policy rule; changing it requires a new rule/version."""

    rule_id: str
    version: str
    available_at: datetime
    confidence: str


@dataclass(frozen=True)
class KnownConcept:
    """Pinned standard concept metadata, not an issuer-specific inference."""

    taxonomy: str
    concept: str
    taxonomy_version_start: int
    taxonomy_version_end: int
    period_kind: str
    contract_units: tuple[str, ...]


def _known_concepts(
    taxonomy: str,
    concepts: Sequence[str],
    *,
    period_kind: str,
    contract_units: tuple[str, ...],
    taxonomy_version_start: int = 2009,
    taxonomy_version_end: int = 2026,
) -> dict[tuple[str, str], KnownConcept]:
    return {
        (taxonomy, concept): KnownConcept(
            taxonomy=taxonomy,
            concept=concept,
            taxonomy_version_start=taxonomy_version_start,
            taxonomy_version_end=taxonomy_version_end,
            period_kind=period_kind,
            contract_units=contract_units,
        )
        for concept in concepts
    }


# This is intentionally closed-world.  New aliases require a deliberate code
# review of their taxonomy period type and unit class before a config can use
# them.  It is not a heuristic extension allowlist.
KNOWN_CONCEPT_ALLOWLIST: dict[tuple[str, str], KnownConcept] = {}
KNOWN_CONCEPT_ALLOWLIST.update(
    _known_concepts(
        "us-gaap",
        (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "CostOfRevenue",
            "CostOfGoodsAndServicesSold",
            "GrossProfit",
            "OperatingExpenses",
            "OperatingIncomeLoss",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeTaxExpenseBenefit",
            "NetIncomeLoss",
            "ResearchAndDevelopmentExpense",
            "ShareBasedCompensation",
            "DepreciationDepletionAndAmortization",
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInInvestingActivities",
            "NetCashProvidedByUsedInFinancingActivities",
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsOfDividendsCommonStock",
            "PaymentsForRepurchaseOfCommonStock",
        ),
        period_kind="duration",
        contract_units=("USD",),
    )
)
KNOWN_CONCEPT_ALLOWLIST.update(
    _known_concepts(
        "us-gaap",
        ("SalesRevenueNet",),
        period_kind="duration",
        contract_units=("USD",),
        taxonomy_version_start=2009,
        taxonomy_version_end=2017,
    )
)
KNOWN_CONCEPT_ALLOWLIST.update(
    _known_concepts(
        "us-gaap",
        (
            "CashAndCashEquivalentsAtCarryingValue",
            "ShortTermInvestments",
            "MarketableSecuritiesCurrent",
            "AccountsReceivableNetCurrent",
            "InventoryNet",
            "AccountsPayableCurrent",
            "AssetsCurrent",
            "LiabilitiesCurrent",
            "PropertyPlantAndEquipmentNet",
            "OperatingLeaseRightOfUseAsset",
            "Goodwill",
            "FiniteLivedIntangibleAssetsNet",
            "Assets",
            "ShortTermBorrowings",
            "LongTermDebtCurrent",
            "LongTermDebtNoncurrent",
            "Liabilities",
            "StockholdersEquity",
            "RetainedEarningsAccumulatedDeficit",
        ),
        period_kind="instant",
        contract_units=("USD",),
    )
)
KNOWN_CONCEPT_ALLOWLIST.update(
    _known_concepts(
        "us-gaap",
        (
            "WeightedAverageNumberOfSharesOutstandingBasic",
            "WeightedAverageNumberOfDilutedSharesOutstanding",
        ),
        period_kind="duration",
        contract_units=("shares",),
    )
)
KNOWN_CONCEPT_ALLOWLIST.update(
    _known_concepts(
        "us-gaap",
        ("EarningsPerShareBasic", "EarningsPerShareDiluted"),
        period_kind="duration",
        contract_units=("USD/shares",),
    )
)
KNOWN_CONCEPT_ALLOWLIST.update(
    _known_concepts(
        "dei",
        ("EntityCommonStockSharesOutstanding",),
        period_kind="instant",
        contract_units=("shares",),
    )
)


@dataclass(frozen=True)
class PeriodConstraints:
    kind: str
    allowed_forms: tuple[str, ...]
    min_duration_days: int | None = None
    max_duration_days: int | None = None


@dataclass(frozen=True)
class DimensionalProfile:
    mode: str
    allowed_axes: tuple[str, ...]
    require_dimensions: bool
    allow_member_selection: bool


@dataclass(frozen=True)
class PresentationConstraints:
    statement: str
    sign_convention: str
    display_scale: str
    comparability: str


@dataclass(frozen=True)
class ReviewPolicy:
    required: bool
    triggers: tuple[str, ...]


@dataclass(frozen=True)
class NoResultPolicy:
    mode: str
    codes: tuple[str, ...]


@dataclass(frozen=True)
class ConceptAlias:
    taxonomy: str
    concept: str
    priority: int
    taxonomy_version_start: int
    taxonomy_version_end: int


@dataclass(frozen=True)
class MappingRule:
    metric_id: str
    rule: ImmutableRule
    taxonomy_concept_aliases: tuple[ConceptAlias, ...]


@dataclass(frozen=True)
class FormulaRule:
    metric_id: str
    rule: ImmutableRule
    expression: str
    dependencies: tuple[str, ...]
    output_unit: str
    dependency_period_alignment: str


@dataclass(frozen=True)
class MetricContract:
    """Complete no-fallback contract for one normalized metric."""

    metric_id: str
    label: str
    category: str
    rule: ImmutableRule
    units: tuple[str, ...]
    period_constraints: PeriodConstraints
    dimensional_profile: DimensionalProfile
    presentation_constraints: PresentationConstraints
    review: ReviewPolicy
    no_result: NoResultPolicy
    declared_formula_dependencies: tuple[str, ...]
    mappings: tuple[MappingRule, ...]
    formula: FormulaRule | None

    @property
    def rule_id(self) -> str:
        return self.rule.rule_id

    @property
    def version(self) -> str:
        return self.rule.version

    @property
    def available_at(self) -> datetime:
        return self.rule.available_at

    @property
    def confidence(self) -> str:
        return self.rule.confidence

    @property
    def taxonomy_concept_aliases(self) -> tuple[ConceptAlias, ...]:
        return tuple(alias for mapping in self.mappings for alias in mapping.taxonomy_concept_aliases)

    @property
    def formula_dependencies(self) -> tuple[str, ...]:
        return self.formula.dependencies if self.formula else self.declared_formula_dependencies


@dataclass(frozen=True)
class MetricRegistry:
    catalog_id: str
    catalog_version: str
    available_at: datetime
    catalog_content_sha256: str
    mapping_pack_id: str
    mapping_pack_version: str
    mapping_pack_available_at: datetime
    mapping_pack_content_sha256: str
    formula_pack_id: str
    formula_pack_version: str
    formula_pack_available_at: datetime
    formula_pack_content_sha256: str
    contracts: tuple[MetricContract, ...]

    def __post_init__(self) -> None:
        # ``dataclasses.replace`` is used by replay fixtures and callers that
        # append future governance. It must not be an escape hatch for moving
        # a lane-inception clock past definitions that already existed.
        validate_metric_registry(self)

    def metric(self, metric_id: str) -> MetricContract:
        for contract in self.contracts:
            if contract.metric_id == metric_id:
                return contract
        raise KeyError(f"unknown metric: {metric_id}")

    @property
    def metric_ids(self) -> tuple[str, ...]:
        return tuple(contract.metric_id for contract in self.contracts)

    def governance_bundle_at(self, recorded_at: str | datetime) -> "GovernanceBundle":
        """Return the complete, immutable governance view visible at a cutoff.

        The three top-level ``available_at`` values are lane-inception clocks,
        not revision clocks.  A later mapping or metric therefore appears only
        when its own rule clock is visible, without rewriting a prior bundle.
        """
        cutoff = parse_utc(recorded_at, field="recorded_at")
        if cutoff is None:  # pragma: no cover - required public argument
            raise ValueError("recorded_at is required")

        catalog_visible = self.available_at <= cutoff
        mapping_pack_visible = catalog_visible and self.mapping_pack_available_at <= cutoff
        formula_pack_visible = catalog_visible and self.formula_pack_available_at <= cutoff
        contracts: list[MetricContract] = []
        for contract in sorted(self.contracts, key=lambda item: item.metric_id):
            if not catalog_visible or contract.rule.available_at > cutoff:
                continue
            mappings = tuple(
                sorted(
                    (
                        mapping
                        for mapping in contract.mappings
                        if mapping_pack_visible and mapping.rule.available_at <= cutoff
                    ),
                    key=lambda item: (item.rule.rule_id, item.rule.version),
                )
            )
            formula = contract.formula
            if not (
                formula_pack_visible
                and formula is not None
                and formula.rule.available_at <= cutoff
            ):
                formula = None
            contracts.append(replace(contract, mappings=mappings, formula=formula))

        return GovernanceBundle(
            schema=GOVERNANCE_BUNDLE_SCHEMA,
            recorded_at=cutoff,
            catalog=(
                GovernanceLane(
                    lane="catalog",
                    identifier=self.catalog_id,
                    version=GOVERNANCE_BUNDLE_PROJECTION_VERSION,
                    available_at=self.available_at,
                )
                if catalog_visible
                else None
            ),
            mapping_pack=(
                GovernanceLane(
                    lane="mapping_pack",
                    identifier=self.mapping_pack_id,
                    version=GOVERNANCE_BUNDLE_PROJECTION_VERSION,
                    available_at=self.mapping_pack_available_at,
                )
                if mapping_pack_visible
                else None
            ),
            formula_pack=(
                GovernanceLane(
                    lane="formula_pack",
                    identifier=self.formula_pack_id,
                    version=GOVERNANCE_BUNDLE_PROJECTION_VERSION,
                    available_at=self.formula_pack_available_at,
                )
                if formula_pack_visible
                else None
            ),
            contracts=tuple(contracts),
        )


@dataclass(frozen=True)
class GovernanceLane:
    """A visible registry lane's immutable inception identity.

    ``version`` is the canonical projection format version, deliberately not
    the mutable latest YAML pack version. A future append must not rewrite a
    prior cutoff bundle merely because the current pack was re-versioned.
    """

    lane: str
    identifier: str
    version: str
    available_at: datetime

    def __post_init__(self) -> None:
        if self.lane not in {"catalog", "mapping_pack", "formula_pack"}:
            raise ValueError("governance lane is unsupported")
        object.__setattr__(self, "identifier", _identifier(self.identifier, field=f"{self.lane}.identifier"))
        object.__setattr__(self, "version", _version(self.version, field=f"{self.lane}.version"))
        available_at = parse_utc(self.available_at, field=f"{self.lane}.available_at")
        if available_at is None:  # pragma: no cover - required typed field
            raise ValueError(f"{self.lane}.available_at is required")
        object.__setattr__(self, "available_at", available_at)

    def to_dict(self) -> dict[str, str]:
        return {
            "lane": self.lane,
            "identifier": self.identifier,
            "version": self.version,
            "available_at": utc_text(self.available_at),
        }


@dataclass(frozen=True)
class GovernanceBundle:
    """Canonical cutoff-visible metric governance with a self-verifying ID.

    ``contracts`` contains frozen domain contracts with only visible mappings
    and formulas attached.  The wire projection keeps those complete contract,
    mapping, and formula definitions as separate canonical lists so consumers
    can validate a receipt without importing the query kernel.
    """

    schema: str
    recorded_at: datetime
    catalog: GovernanceLane | None
    mapping_pack: GovernanceLane | None
    formula_pack: GovernanceLane | None
    contracts: tuple[MetricContract, ...]
    content_id: str = ""

    def __post_init__(self) -> None:
        if self.schema != GOVERNANCE_BUNDLE_SCHEMA:
            raise ValueError(f"governance bundle schema must equal {GOVERNANCE_BUNDLE_SCHEMA}")
        recorded_at = parse_utc(self.recorded_at, field="governance_bundle.recorded_at")
        if recorded_at is None:  # pragma: no cover - required typed field
            raise ValueError("governance_bundle.recorded_at is required")
        object.__setattr__(self, "recorded_at", recorded_at)
        _validate_governance_bundle_lanes(self, recorded_at)
        if not isinstance(self.contracts, tuple):
            raise TypeError("governance_bundle.contracts must be a tuple")
        if len(self.contracts) > MAX_GOVERNANCE_BUNDLE_METRICS:
            raise ValueError("governance_bundle exceeds the metric receipt limit")
        if any(not isinstance(contract, MetricContract) for contract in self.contracts):
            raise TypeError("governance_bundle.contracts must contain MetricContract values")
        frozen_contracts: list[MetricContract] = []
        for index, contract in enumerate(self.contracts):
            base = _metric_contract_from_payload(
                _contract_payload(contract), field=f"governance_bundle.metrics[{index}]"
            )
            mappings = tuple(
                _mapping_from_payload(
                    _mapping_payload(mapping), field=f"governance_bundle.mappings[{index}]"
                )
                for mapping in contract.mappings
            )
            formula = (
                _formula_from_payload(
                    _formula_payload(contract.formula), field=f"governance_bundle.formulas[{index}]"
                )
                if contract.formula is not None
                else None
            )
            frozen_contracts.append(replace(base, mappings=mappings, formula=formula))
        ordered = tuple(sorted(frozen_contracts, key=lambda item: item.metric_id))
        object.__setattr__(self, "contracts", ordered)
        _validate_governance_bundle_contracts(self)
        expected = _governance_bundle_content_id(self._content_payload())
        if self.content_id and not hmac.compare_digest(self.content_id, expected):
            raise ValueError("governance bundle content_id does not match canonical content")
        object.__setattr__(self, "content_id", expected)

    def metric(self, metric_id: str) -> MetricContract:
        for contract in self.contracts:
            if contract.metric_id == metric_id:
                return contract
        raise KeyError(f"metric is not visible in governance bundle: {metric_id}")

    def mappings_for(self, metric_id: str) -> tuple[MappingRule, ...]:
        try:
            return self.metric(metric_id).mappings
        except KeyError:
            return ()

    def formula_for(self, metric_id: str) -> FormulaRule | None:
        try:
            return self.metric(metric_id).formula
        except KeyError:
            return None

    def _content_payload(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "recorded_at": utc_text(self.recorded_at),
            "catalog": self.catalog.to_dict() if self.catalog else None,
            "mapping_pack": self.mapping_pack.to_dict() if self.mapping_pack else None,
            "formula_pack": self.formula_pack.to_dict() if self.formula_pack else None,
            "metrics": [_contract_payload(contract) for contract in self.contracts],
            "mappings": [
                _mapping_payload(mapping)
                for contract in self.contracts
                for mapping in contract.mappings
            ],
            "formulas": [
                _formula_payload(contract.formula)
                for contract in self.contracts
                if contract.formula is not None
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._content_payload()
        payload["content_id"] = self.content_id
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GovernanceBundle":
        """Decode a bounded canonical wire bundle and verify its content ID."""
        return _governance_bundle_from_dict(value)


def _require_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _require_list(value: Any, *, field: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _identifier(value: Any, *, field: str) -> str:
    text = _text(value, field=field)
    if not _IDENTIFIER.fullmatch(text):
        raise ValueError(f"{field} must be a lower_snake_case identifier: {text!r}")
    return text


def _version(value: Any, *, field: str) -> str:
    text = _text(value, field=field)
    if not _SEMVER.fullmatch(text):
        raise ValueError(f"{field} must be a semantic version: {text!r}")
    return text


def _utc(value: Any, *, field: str) -> datetime:
    parsed = parse_utc(_text(value, field=field), field=field)
    if parsed is None:  # pragma: no cover - _text makes this impossible
        raise ValueError(f"{field} is required")
    return parsed


def _rule(value: Any, *, field: str) -> ImmutableRule:
    raw = _require_mapping(value, field=field)
    _exact_keys(
        raw,
        field=field,
        required=frozenset({"rule_id", "version", "available_at", "confidence"}),
    )
    rule_id = _text(raw.get("rule_id"), field=f"{field}.rule_id")
    version = _version(raw.get("version"), field=f"{field}.version")
    expected_suffix = f"/v{version.split('.', 1)[0]}"
    if not rule_id.endswith(expected_suffix) or any(char.isspace() for char in rule_id):
        raise ValueError(
            f"{field}.rule_id must encode its immutable major version ({expected_suffix})"
        )
    available_at = _utc(raw.get("available_at"), field=f"{field}.available_at")
    confidence = _text(raw.get("confidence"), field=f"{field}.confidence")
    if confidence not in ALLOWED_CONFIDENCE:
        raise ValueError(f"{field}.confidence must be one of A/B/C/D")
    return ImmutableRule(rule_id, version, available_at, confidence)


def _period_constraints(value: Any, *, field: str) -> PeriodConstraints:
    raw = _require_mapping(value, field=field)
    kind = _text(raw.get("kind"), field=f"{field}.kind")
    if kind not in ALLOWED_PERIOD_KINDS:
        raise ValueError(f"{field}.kind must be one of {sorted(ALLOWED_PERIOD_KINDS)}")
    forms = tuple(_text(item, field=f"{field}.allowed_forms") for item in _require_list(
        raw.get("allowed_forms"), field=f"{field}.allowed_forms"
    ))
    if not forms or len(set(forms)) != len(forms) or not set(forms).issubset(ALLOWED_FORMS):
        raise ValueError(f"{field}.allowed_forms must be unique SEC annual or quarterly forms")
    minimum = raw.get("min_duration_days")
    maximum = raw.get("max_duration_days")
    if kind == "instant":
        if minimum is not None or maximum is not None:
            raise ValueError(f"{field} instant metrics cannot carry duration bounds")
        return PeriodConstraints(kind=kind, allowed_forms=forms)
    if not isinstance(minimum, int) or not isinstance(maximum, int) or minimum < 1 or maximum < minimum:
        raise ValueError(f"{field} duration metrics require valid min/max duration days")
    return PeriodConstraints(kind=kind, allowed_forms=forms, min_duration_days=minimum, max_duration_days=maximum)


def _dimensional_profile(value: Any, *, field: str) -> DimensionalProfile:
    raw = _require_mapping(value, field=field)
    mode = _text(raw.get("mode"), field=f"{field}.mode")
    axes = tuple(_text(item, field=f"{field}.allowed_axes") for item in _require_list(
        raw.get("allowed_axes"), field=f"{field}.allowed_axes"
    ))
    required = raw.get("require_dimensions")
    member_selection = raw.get("allow_member_selection")
    if mode != "consolidated_only" or axes or required is not False or member_selection is not False:
        raise ValueError(
            f"{field} only supports explicit consolidated-only, dimensionless contracts in v1"
        )
    return DimensionalProfile(mode, axes, required, member_selection)


def _presentation(value: Any, *, field: str) -> PresentationConstraints:
    raw = _require_mapping(value, field=field)
    statement = _text(raw.get("statement"), field=f"{field}.statement")
    if statement not in ALLOWED_STATEMENTS:
        raise ValueError(f"{field}.statement is not a supported presentation")
    sign = _text(raw.get("sign_convention"), field=f"{field}.sign_convention")
    if sign not in {"as_reported", "formula_defined"}:
        raise ValueError(f"{field}.sign_convention must be as_reported or formula_defined")
    scale = _text(raw.get("display_scale"), field=f"{field}.display_scale")
    comparison = _text(raw.get("comparability"), field=f"{field}.comparability")
    if scale != "native" or comparison != "same_unit_same_period":
        raise ValueError(f"{field} must preserve native values and same-unit/same-period comparison")
    return PresentationConstraints(statement, sign, scale, comparison)


def _review(value: Any, *, field: str) -> ReviewPolicy:
    raw = _require_mapping(value, field=field)
    required = raw.get("required")
    triggers = tuple(_identifier(item, field=f"{field}.triggers") for item in _require_list(
        raw.get("triggers"), field=f"{field}.triggers"
    ))
    if not isinstance(required, bool) or not triggers or len(set(triggers)) != len(triggers):
        raise ValueError(f"{field} must provide a boolean required flag and unique review triggers")
    return ReviewPolicy(required, triggers)


def _no_result(value: Any, *, field: str) -> NoResultPolicy:
    raw = _require_mapping(value, field=field)
    mode = _text(raw.get("mode"), field=f"{field}.mode")
    codes = tuple(_identifier(item, field=f"{field}.codes") for item in _require_list(
        raw.get("codes"), field=f"{field}.codes"
    ))
    if mode != "withhold" or not codes or len(set(codes)) != len(codes):
        raise ValueError(f"{field} must fail closed with unique no-result codes")
    return NoResultPolicy(mode, codes)


def _units(value: Any, *, field: str) -> tuple[str, ...]:
    units = tuple(_text(item, field=field) for item in _require_list(value, field=field))
    if not units or len(set(units)) != len(units) or not set(units).issubset(ALLOWED_UNITS):
        raise ValueError(f"{field} contains an unsupported or duplicate unit")
    return units


def _dependencies(value: Any, *, field: str) -> tuple[str, ...]:
    dependencies = tuple(_identifier(item, field=field) for item in _require_list(value, field=field))
    if len(set(dependencies)) != len(dependencies):
        raise ValueError(f"{field} cannot contain duplicate dependencies")
    return dependencies


def _exact_keys(
    value: Mapping[str, Any],
    *,
    field: str,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    """Reject silent wire/schema extensions, including supersession fields."""
    if type(value) is not dict:
        raise ValueError(f"{field} must be a concrete object")
    unknown = set(value) - required - optional
    missing = required - set(value)
    if unknown:
        raise ValueError(f"{field} contains unsupported field(s): {', '.join(sorted(map(str, unknown)))}")
    if missing:
        raise ValueError(f"{field} omits required field(s): {', '.join(sorted(missing))}")


def _bounded_wire_list(value: Any, *, field: str, maximum: int) -> list[Any]:
    """Admit only decoded JSON lists and reject oversize data before copying it."""
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if len(value) > maximum:
        raise ValueError(f"{field} exceeds the bounded governance receipt limit ({maximum})")
    return value


def _bounded_governance_wire(value: Any, *, field: str) -> dict[str, Any]:
    """Copy only a small decoded-JSON tree before any schema traversal.

    This precedes every ``_exact_keys`` call in ``GovernanceBundle.from_dict``;
    hostile Mapping implementations therefore never get an unbounded key
    iteration or a chance to lie about their length.
    """
    budget = [MAX_GOVERNANCE_BUNDLE_WIRE_BYTES]

    def consume(amount: int, *, item_field: str) -> None:
        budget[0] -= amount
        if budget[0] < 0:
            raise ValueError(f"{item_field} exceeds the governance bundle wire-byte limit")

    def copy(item: Any, *, item_field: str, depth: int) -> Any:
        if depth > MAX_GOVERNANCE_BUNDLE_WIRE_DEPTH:
            raise ValueError(f"{item_field} exceeds the governance bundle nesting limit")
        if type(item) is dict:
            if len(item) > MAX_GOVERNANCE_BUNDLE_WIRE_OBJECT_FIELDS:
                raise ValueError(f"{item_field} exceeds the governance bundle object-field limit")
            out: dict[str, Any] = {}
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError(f"{item_field} object keys must be strings")
                key_bytes = len(key.encode("utf-8"))
                if key_bytes > MAX_GOVERNANCE_BUNDLE_WIRE_TEXT_CHARS:
                    raise ValueError(f"{item_field} object key exceeds the governance text limit")
                consume(key_bytes, item_field=item_field)
                out[key] = copy(child, item_field=f"{item_field}.{key}", depth=depth + 1)
            return out
        if type(item) is list:
            if len(item) > MAX_GOVERNANCE_BUNDLE_MAPPINGS:
                raise ValueError(f"{item_field} exceeds the governance bundle list limit")
            return [
                copy(child, item_field=f"{item_field}[{index}]", depth=depth + 1)
                for index, child in enumerate(item)
            ]
        if isinstance(item, str):
            encoded = item.encode("utf-8")
            if len(encoded) > MAX_GOVERNANCE_BUNDLE_WIRE_TEXT_CHARS:
                raise ValueError(f"{item_field} exceeds the governance text limit")
            consume(len(encoded), item_field=item_field)
            return item
        if item is None or isinstance(item, (bool, int)):
            consume(len(str(item)), item_field=item_field)
            return item
        if isinstance(item, Mapping):
            raise ValueError(f"{item_field} must be a concrete object")
        raise ValueError(f"{item_field} must contain only decoded JSON values")

    out = copy(value, item_field=field, depth=0)
    if type(out) is not dict:
        raise ValueError(f"{field} must be a concrete object")
    return out


def _rule_payload(rule: ImmutableRule) -> dict[str, str]:
    return {
        "rule_id": rule.rule_id,
        "version": rule.version,
        "available_at": utc_text(rule.available_at),
        "confidence": rule.confidence,
    }


def _contract_payload(contract: MetricContract) -> dict[str, Any]:
    period = contract.period_constraints
    dimensions = contract.dimensional_profile
    presentation = contract.presentation_constraints
    return {
        "metric_id": contract.metric_id,
        "label": contract.label,
        "category": contract.category,
        "rule": _rule_payload(contract.rule),
        "units": list(contract.units),
        "period_constraints": {
            "kind": period.kind,
            "allowed_forms": list(period.allowed_forms),
            "min_duration_days": period.min_duration_days,
            "max_duration_days": period.max_duration_days,
        },
        "dimensional_profile": {
            "mode": dimensions.mode,
            "allowed_axes": list(dimensions.allowed_axes),
            "require_dimensions": dimensions.require_dimensions,
            "allow_member_selection": dimensions.allow_member_selection,
        },
        "presentation_constraints": {
            "statement": presentation.statement,
            "sign_convention": presentation.sign_convention,
            "display_scale": presentation.display_scale,
            "comparability": presentation.comparability,
        },
        "review": {
            "required": contract.review.required,
            "triggers": list(contract.review.triggers),
        },
        "no_result": {
            "mode": contract.no_result.mode,
            "codes": list(contract.no_result.codes),
        },
        "declared_formula_dependencies": list(contract.declared_formula_dependencies),
    }


def _mapping_payload(mapping: MappingRule) -> dict[str, Any]:
    aliases = sorted(
        mapping.taxonomy_concept_aliases,
        key=lambda item: (
            item.priority,
            item.taxonomy,
            item.concept,
            item.taxonomy_version_start,
            item.taxonomy_version_end,
        ),
    )
    return {
        "metric_id": mapping.metric_id,
        "rule": _rule_payload(mapping.rule),
        "taxonomy_concept_aliases": [
            {
                "taxonomy": alias.taxonomy,
                "concept": alias.concept,
                "priority": alias.priority,
                "taxonomy_version_start": alias.taxonomy_version_start,
                "taxonomy_version_end": alias.taxonomy_version_end,
            }
            for alias in aliases
        ],
    }


def _formula_payload(formula: FormulaRule) -> dict[str, Any]:
    return {
        "metric_id": formula.metric_id,
        "rule": _rule_payload(formula.rule),
        "expression": formula.expression,
        "dependencies": list(formula.dependencies),
        "output_unit": formula.output_unit,
        "dependency_period_alignment": formula.dependency_period_alignment,
    }


def _metric_contract_from_payload(value: Mapping[str, Any], *, field: str) -> MetricContract:
    raw = _require_mapping(value, field=field)
    _exact_keys(
        raw,
        field=field,
        required=frozenset(
            {
                "metric_id", "label", "category", "rule", "units", "period_constraints",
                "dimensional_profile", "presentation_constraints", "review", "no_result",
                "declared_formula_dependencies",
            }
        ),
    )
    _bounded_wire_list(raw["units"], field=f"{field}.units", maximum=len(ALLOWED_UNITS))
    _bounded_wire_list(
        raw["declared_formula_dependencies"],
        field=f"{field}.declared_formula_dependencies",
        maximum=MAX_GOVERNANCE_BUNDLE_DEPENDENCIES,
    )
    period_raw = _require_mapping(raw["period_constraints"], field=f"{field}.period_constraints")
    _bounded_wire_list(
        period_raw.get("allowed_forms"), field=f"{field}.period_constraints.allowed_forms", maximum=len(ALLOWED_FORMS)
    )
    dimensions_raw = _require_mapping(raw["dimensional_profile"], field=f"{field}.dimensional_profile")
    _bounded_wire_list(
        dimensions_raw.get("allowed_axes"), field=f"{field}.dimensional_profile.allowed_axes", maximum=16
    )
    review_raw = _require_mapping(raw["review"], field=f"{field}.review")
    _bounded_wire_list(review_raw.get("triggers"), field=f"{field}.review.triggers", maximum=32)
    no_result_raw = _require_mapping(raw["no_result"], field=f"{field}.no_result")
    _bounded_wire_list(no_result_raw.get("codes"), field=f"{field}.no_result.codes", maximum=32)
    return MetricContract(
        metric_id=_identifier(raw["metric_id"], field=f"{field}.metric_id"),
        label=_text(raw["label"], field=f"{field}.label"),
        category=_identifier(raw["category"], field=f"{field}.category"),
        rule=_rule(raw["rule"], field=f"{field}.rule"),
        units=_units(raw["units"], field=f"{field}.units"),
        period_constraints=_period_constraints(raw["period_constraints"], field=f"{field}.period_constraints"),
        dimensional_profile=_dimensional_profile(raw["dimensional_profile"], field=f"{field}.dimensional_profile"),
        presentation_constraints=_presentation(raw["presentation_constraints"], field=f"{field}.presentation_constraints"),
        review=_review(raw["review"], field=f"{field}.review"),
        no_result=_no_result(raw["no_result"], field=f"{field}.no_result"),
        declared_formula_dependencies=_dependencies(
            raw["declared_formula_dependencies"], field=f"{field}.declared_formula_dependencies"
        ),
        mappings=(),
        formula=None,
    )


def _mapping_from_payload(value: Mapping[str, Any], *, field: str) -> MappingRule:
    raw = _require_mapping(value, field=field)
    _exact_keys(
        raw,
        field=field,
        required=frozenset({"metric_id", "rule", "taxonomy_concept_aliases"}),
    )
    aliases_raw = _bounded_wire_list(
        raw["taxonomy_concept_aliases"],
        field=f"{field}.taxonomy_concept_aliases",
        maximum=MAX_GOVERNANCE_BUNDLE_ALIASES_PER_MAPPING,
    )
    aliases: list[ConceptAlias] = []
    priorities: set[int] = set()
    for index, item in enumerate(aliases_raw):
        alias = _require_mapping(item, field=f"{field}.taxonomy_concept_aliases[{index}]")
        _exact_keys(
            alias,
            field=f"{field}.taxonomy_concept_aliases[{index}]",
            required=frozenset(
                {"taxonomy", "concept", "priority", "taxonomy_version_start", "taxonomy_version_end"}
            ),
        )
        taxonomy = _text(alias["taxonomy"], field=f"{field}.taxonomy_concept_aliases[{index}].taxonomy")
        concept = _text(alias["concept"], field=f"{field}.taxonomy_concept_aliases[{index}].concept")
        priority = alias["priority"]
        taxonomy_version_start = alias["taxonomy_version_start"]
        taxonomy_version_end = alias["taxonomy_version_end"]
        if taxonomy not in ALLOWED_TAXONOMIES:
            raise ValueError(f"issuer-extension or unsupported taxonomy mapping is prohibited: {taxonomy}")
        if not _CONCEPT.fullmatch(concept):
            raise ValueError(f"taxonomy concept must be a standard local-name: {concept!r}")
        if not isinstance(priority, int) or priority < 1 or priority in priorities:
            raise ValueError("taxonomy concept aliases require unique positive priorities")
        if (
            type(taxonomy_version_start) is not int
            or type(taxonomy_version_end) is not int
            or taxonomy_version_start > taxonomy_version_end
        ):
            raise ValueError("taxonomy applicability must be an ordered integer range")
        priorities.add(priority)
        aliases.append(
            ConceptAlias(taxonomy, concept, priority, taxonomy_version_start, taxonomy_version_end)
        )
    if not aliases:
        raise ValueError(f"{field} must provide standard taxonomy aliases")
    return MappingRule(
        metric_id=_identifier(raw["metric_id"], field=f"{field}.metric_id"),
        rule=_rule(raw["rule"], field=f"{field}.rule"),
        taxonomy_concept_aliases=tuple(aliases),
    )


def _formula_from_payload(value: Mapping[str, Any], *, field: str) -> FormulaRule:
    raw = _require_mapping(value, field=field)
    _exact_keys(
        raw,
        field=field,
        required=frozenset(
            {"metric_id", "rule", "expression", "dependencies", "output_unit", "dependency_period_alignment"}
        ),
    )
    _bounded_wire_list(raw["dependencies"], field=f"{field}.dependencies", maximum=MAX_GOVERNANCE_BUNDLE_DEPENDENCIES)
    metric_id = _identifier(raw["metric_id"], field=f"{field}.metric_id")
    dependencies = _dependencies(raw["dependencies"], field=f"{field}.dependencies")
    if not dependencies:
        raise ValueError(f"formula {metric_id} must declare dependencies")
    expression = _text(raw["expression"], field=f"{field}.expression")
    _parse_formula_expression(expression, dependencies, field=f"{field}.expression")
    output_unit = _text(raw["output_unit"], field=f"{field}.output_unit")
    if output_unit not in ALLOWED_UNITS:
        raise ValueError(f"formula {metric_id} has unsupported output unit")
    alignment = _text(raw["dependency_period_alignment"], field=f"{field}.dependency_period_alignment")
    if alignment not in ALLOWED_ALIGNMENTS:
        raise ValueError(f"formula {metric_id} has unsupported period alignment")
    return FormulaRule(metric_id, _rule(raw["rule"], field=f"{field}.rule"), expression, dependencies, output_unit, alignment)


def _governance_bundle_content_id(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _validate_governance_bundle_lanes(bundle: GovernanceBundle, cutoff: datetime) -> None:
    lane_specs = (
        ("catalog", bundle.catalog, "catalog"),
        ("mapping_pack", bundle.mapping_pack, "mapping_pack"),
        ("formula_pack", bundle.formula_pack, "formula_pack"),
    )
    for field, lane, expected_lane in lane_specs:
        if lane is not None:
            if not isinstance(lane, GovernanceLane) or lane.lane != expected_lane:
                raise ValueError(f"governance_bundle.{field} has an invalid lane identity")
            if lane.available_at > cutoff:
                raise ValueError(f"governance_bundle.{field} is hidden at recorded_at")
    if bundle.catalog is None and (bundle.mapping_pack is not None or bundle.formula_pack is not None or bundle.contracts):
        raise ValueError("governance bundle cannot expose child lanes or definitions before its catalog")
    if bundle.mapping_pack is not None and bundle.catalog is None:
        raise ValueError("mapping pack cannot be visible without its catalog")
    if bundle.formula_pack is not None and bundle.catalog is None:
        raise ValueError("formula pack cannot be visible without its catalog")


def _validate_governance_bundle_contracts(bundle: GovernanceBundle) -> None:
    if bundle.catalog is None:
        if bundle.contracts:
            raise ValueError("governance bundle cannot expose metrics before its catalog")
        return
    metric_ids: set[str] = set()
    rule_ids: set[str] = set()
    rule_versions: set[tuple[str, str]] = set()
    aliases_seen: dict[tuple[str, str], str] = {}
    mappings_total = 0
    formulas_total = 0

    def claim_rule(rule: ImmutableRule, *, field: str) -> None:
        key = (rule.rule_id, rule.version)
        if key in rule_versions:
            raise ValueError(f"duplicate immutable rule/version in governance bundle: {rule.rule_id}@{rule.version}")
        if rule.rule_id in rule_ids:
            raise ValueError(f"rule replacement/supersession is unsupported: {rule.rule_id}")
        rule_versions.add(key)
        rule_ids.add(rule.rule_id)

    contracts_by_metric: dict[str, MetricContract] = {}
    for contract in bundle.contracts:
        # Reparse the canonical primitive representation to freeze nested
        # collections and prove the entire semantic contract is still valid.
        frozen_base = _metric_contract_from_payload(
            _contract_payload(contract), field=f"governance_bundle.metrics[{contract.metric_id}]"
        )
        if frozen_base != replace(contract, mappings=(), formula=None):
            raise ValueError(f"governance bundle metric contract is not canonical: {contract.metric_id}")
        if contract.metric_id in metric_ids:
            raise ValueError(f"duplicate metric in governance bundle: {contract.metric_id}")
        if contract.rule.available_at > bundle.recorded_at:
            raise ValueError(f"metric {contract.metric_id} is hidden at recorded_at")
        if contract.rule.available_at < bundle.catalog.available_at:
            raise ValueError(f"metric {contract.metric_id} predates catalog lane inception")
        metric_ids.add(contract.metric_id)
        contracts_by_metric[contract.metric_id] = contract
        claim_rule(contract.rule, field=f"metric {contract.metric_id}")

    for contract in bundle.contracts:
        if not isinstance(contract.mappings, tuple):
            raise TypeError(f"metric {contract.metric_id} mappings must be a tuple")
        if len(contract.mappings) > MAX_GOVERNANCE_BUNDLE_MAPPINGS:
            raise ValueError(f"metric {contract.metric_id} exceeds mapping receipt limit")
        if contract.mappings and bundle.mapping_pack is None:
            raise ValueError(f"mapping for {contract.metric_id} is visible while mapping pack is hidden")
        if contract.formula is not None and bundle.formula_pack is None:
            raise ValueError(f"formula for {contract.metric_id} is visible while formula pack is hidden")
        if contract.mappings and contract.formula is not None:
            raise ValueError(f"metric {contract.metric_id} cannot mix direct mappings and formula rules")
        for mapping in contract.mappings:
            mappings_total += 1
            if mappings_total > MAX_GOVERNANCE_BUNDLE_MAPPINGS:
                raise ValueError("governance bundle exceeds mapping receipt limit")
            frozen_mapping = _mapping_from_payload(
                _mapping_payload(mapping), field=f"governance_bundle.mappings[{mappings_total - 1}]"
            )
            if frozen_mapping != mapping:
                raise ValueError(f"mapping for {contract.metric_id} is not canonical")
            if mapping.metric_id != contract.metric_id:
                raise ValueError(f"mapping metric does not match its visible contract: {mapping.metric_id}")
            if mapping.rule.available_at > bundle.recorded_at:
                raise ValueError(f"mapping rule for {contract.metric_id} is hidden at recorded_at")
            assert bundle.mapping_pack is not None
            if mapping.rule.available_at < max(bundle.mapping_pack.available_at, contract.rule.available_at):
                raise ValueError(f"mapping rule for {contract.metric_id} predates its lane or metric contract")
            if mapping.rule.confidence != contract.rule.confidence:
                raise ValueError(f"mapping rule confidence must match metric contract confidence for {contract.metric_id}")
            claim_rule(mapping.rule, field=f"mapping {contract.metric_id}")
            for alias in mapping.taxonomy_concept_aliases:
                known = KNOWN_CONCEPT_ALLOWLIST.get((alias.taxonomy, alias.concept))
                if known is None:
                    raise ValueError(f"taxonomy concept is not in the governed known-concept allowlist: {alias.taxonomy}:{alias.concept}")
                if (
                    alias.taxonomy_version_start < known.taxonomy_version_start
                    or alias.taxonomy_version_end > known.taxonomy_version_end
                ):
                    raise ValueError(f"taxonomy applicability for {alias.taxonomy}:{alias.concept} is outside governed range")
                if (
                    contract.period_constraints.kind != known.period_kind
                    or contract.units != known.contract_units
                ):
                    raise ValueError(
                        f"taxonomy concept {alias.taxonomy}:{alias.concept} does not match {contract.metric_id} period or unit contract"
                    )
                key = (alias.taxonomy, alias.concept)
                if key in aliases_seen:
                    raise ValueError(f"duplicate standard concept alias {alias.taxonomy}:{alias.concept}")
                aliases_seen[key] = contract.metric_id

        formula = contract.formula
        if formula is None:
            continue
        formulas_total += 1
        if formulas_total > MAX_GOVERNANCE_BUNDLE_FORMULAS:
            raise ValueError("governance bundle exceeds formula receipt limit")
        frozen_formula = _formula_from_payload(
            _formula_payload(formula), field=f"governance_bundle.formulas[{formulas_total - 1}]"
        )
        if frozen_formula != formula:
            raise ValueError(f"formula for {contract.metric_id} is not canonical")
        if formula.metric_id != contract.metric_id:
            raise ValueError(f"formula metric does not match its visible contract: {formula.metric_id}")
        if formula.rule.available_at > bundle.recorded_at:
            raise ValueError(f"formula rule for {contract.metric_id} is hidden at recorded_at")
        assert bundle.formula_pack is not None
        if formula.rule.available_at < max(bundle.formula_pack.available_at, contract.rule.available_at):
            raise ValueError(f"formula rule for {contract.metric_id} predates its lane or metric contract")
        if formula.rule.confidence != contract.rule.confidence:
            raise ValueError(f"formula rule confidence must match metric contract confidence for {contract.metric_id}")
        if formula.dependencies != contract.declared_formula_dependencies:
            raise ValueError(f"formula dependencies for {contract.metric_id} do not match metric declaration")
        if formula.output_unit not in contract.units:
            raise ValueError(f"formula {contract.metric_id} output unit must be governed by its metric contract")
        dependency_dimensions = {
            dependency: _unit_dimension(contracts_by_metric[dependency].units[0])
            for dependency in formula.dependencies
            if dependency in contracts_by_metric and len(contracts_by_metric[dependency].units) == 1
        }
        if set(dependency_dimensions) != set(formula.dependencies):
            raise ValueError(f"formula {contract.metric_id} has unknown or multi-unit dependencies")
        expression = _parse_formula_expression(
            formula.expression, formula.dependencies, field=f"formula {contract.metric_id}"
        )
        if _infer_formula_dimension(expression, dependency_dimensions, field=f"formula {contract.metric_id}") != _unit_dimension(formula.output_unit):
            raise ValueError(f"formula {contract.metric_id} unit algebra does not match declared output unit")
        dependency_kinds = tuple(
            contracts_by_metric[dependency].period_constraints.kind for dependency in formula.dependencies
        )
        if formula.dependency_period_alignment == "same_period" and any(
            kind != contract.period_constraints.kind for kind in dependency_kinds
        ):
            raise ValueError(f"formula {contract.metric_id} same_period alignment requires matching dependency period kinds")
        if formula.dependency_period_alignment == "ending_instant_to_duration" and (
            contract.period_constraints.kind != "duration" or sorted(dependency_kinds) != ["duration", "instant"]
        ):
            raise ValueError(
                f"formula {contract.metric_id} ending_instant_to_duration alignment requires one instant and one duration dependency"
            )
        if not contract.review.required:
            raise ValueError(f"derived metric {contract.metric_id} must require review")
        required = {"missing_dependency", "incompatible_dependencies", "division_by_zero"}
        if not required.issubset(contract.no_result.codes):
            raise ValueError(f"metric {contract.metric_id} omits required fail-closed no-result codes")
        claim_rule(formula.rule, field=f"formula {contract.metric_id}")

    if formulas_total > MAX_GOVERNANCE_BUNDLE_FORMULAS:
        raise ValueError("governance bundle exceeds formula receipt limit")
    _validate_bundle_formula_graph_and_clocks(bundle, contracts_by_metric)


def _validate_bundle_formula_graph_and_clocks(
    bundle: GovernanceBundle,
    contracts_by_metric: Mapping[str, MetricContract],
) -> None:
    """Prove formula readiness using definitions visible at each formula clock."""
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(metric_id: str) -> None:
        if metric_id in visited:
            return
        if metric_id in visiting:
            raise ValueError(f"formula dependency graph contains a cycle at {metric_id}")
        visiting.add(metric_id)
        formula = contracts_by_metric[metric_id].formula
        if formula is not None:
            for dependency in formula.dependencies:
                if dependency not in contracts_by_metric:
                    raise ValueError(f"formula {metric_id} depends on unknown metric {dependency}")
                visit(dependency)
        visiting.remove(metric_id)
        visited.add(metric_id)

    for metric_id in sorted(contracts_by_metric):
        visit(metric_id)

    def ready_at(metric_id: str, cutoff: datetime) -> datetime | None:
        contract = contracts_by_metric[metric_id]
        if contract.rule.available_at > cutoff:
            return None
        formula = contract.formula
        if formula is not None:
            if bundle.formula_pack is None or formula.rule.available_at > cutoff:
                return None
            dependencies = [ready_at(dependency, formula.rule.available_at) for dependency in formula.dependencies]
            if any(value is None for value in dependencies):
                return None
            return max(bundle.catalog.available_at, bundle.formula_pack.available_at, contract.rule.available_at, formula.rule.available_at)
        if bundle.mapping_pack is None:
            return None
        visible = [mapping for mapping in contract.mappings if mapping.rule.available_at <= cutoff]
        if not visible:
            return None
        return max(
            bundle.catalog.available_at,
            bundle.mapping_pack.available_at,
            contract.rule.available_at,
            *(mapping.rule.available_at for mapping in visible),
        )

    for contract in contracts_by_metric.values():
        formula = contract.formula
        if formula is None:
            continue
        dependency_ready = [ready_at(dependency, formula.rule.available_at) for dependency in formula.dependencies]
        if any(value is None for value in dependency_ready) or formula.rule.available_at < max(dependency_ready):
            raise ValueError(
                f"formula {contract.metric_id} cannot predate dependency definitions visible at its availability"
            )


def _governance_bundle_from_dict(value: Mapping[str, Any]) -> GovernanceBundle:
    raw = _bounded_governance_wire(value, field="governance_bundle")
    _exact_keys(
        raw,
        field="governance_bundle",
        required=frozenset(
            {"schema", "recorded_at", "catalog", "mapping_pack", "formula_pack", "metrics", "mappings", "formulas", "content_id"}
        ),
    )
    schema = _text(raw["schema"], field="governance_bundle.schema")
    recorded_at = _utc(raw["recorded_at"], field="governance_bundle.recorded_at")

    def lane(value: Any, *, field: str, lane_name: str) -> GovernanceLane | None:
        if value is None:
            return None
        lane_raw = _require_mapping(value, field=field)
        _exact_keys(
            lane_raw,
            field=field,
            required=frozenset({"lane", "identifier", "version", "available_at"}),
        )
        out = GovernanceLane(
            lane=_text(lane_raw["lane"], field=f"{field}.lane"),
            identifier=_text(lane_raw["identifier"], field=f"{field}.identifier"),
            version=_text(lane_raw["version"], field=f"{field}.version"),
            available_at=_utc(lane_raw["available_at"], field=f"{field}.available_at"),
        )
        if out.lane != lane_name:
            raise ValueError(f"{field}.lane must equal {lane_name}")
        return out

    catalog = lane(raw["catalog"], field="governance_bundle.catalog", lane_name="catalog")
    mapping_pack = lane(raw["mapping_pack"], field="governance_bundle.mapping_pack", lane_name="mapping_pack")
    formula_pack = lane(raw["formula_pack"], field="governance_bundle.formula_pack", lane_name="formula_pack")
    metrics_raw = _bounded_wire_list(raw["metrics"], field="governance_bundle.metrics", maximum=MAX_GOVERNANCE_BUNDLE_METRICS)
    mappings_raw = _bounded_wire_list(raw["mappings"], field="governance_bundle.mappings", maximum=MAX_GOVERNANCE_BUNDLE_MAPPINGS)
    formulas_raw = _bounded_wire_list(raw["formulas"], field="governance_bundle.formulas", maximum=MAX_GOVERNANCE_BUNDLE_FORMULAS)
    contracts = [
        _metric_contract_from_payload(_require_mapping(item, field=f"governance_bundle.metrics[{index}]"), field=f"governance_bundle.metrics[{index}]")
        for index, item in enumerate(metrics_raw)
    ]
    mapping_items = [
        _mapping_from_payload(_require_mapping(item, field=f"governance_bundle.mappings[{index}]"), field=f"governance_bundle.mappings[{index}]")
        for index, item in enumerate(mappings_raw)
    ]
    formula_items = [
        _formula_from_payload(_require_mapping(item, field=f"governance_bundle.formulas[{index}]"), field=f"governance_bundle.formulas[{index}]")
        for index, item in enumerate(formulas_raw)
    ]
    mappings_by_metric: dict[str, list[MappingRule]] = {contract.metric_id: [] for contract in contracts}
    for mapping in mapping_items:
        if mapping.metric_id not in mappings_by_metric:
            raise ValueError(f"mapping references metric absent from visible bundle: {mapping.metric_id}")
        mappings_by_metric[mapping.metric_id].append(mapping)
    formulas_by_metric: dict[str, FormulaRule] = {}
    for formula in formula_items:
        if formula.metric_id not in mappings_by_metric:
            raise ValueError(f"formula references metric absent from visible bundle: {formula.metric_id}")
        if formula.metric_id in formulas_by_metric:
            raise ValueError(f"duplicate formula metric in governance bundle: {formula.metric_id}")
        formulas_by_metric[formula.metric_id] = formula
    projected = tuple(
        replace(
            contract,
            mappings=tuple(sorted(mappings_by_metric[contract.metric_id], key=lambda item: (item.rule.rule_id, item.rule.version))),
            formula=formulas_by_metric.get(contract.metric_id),
        )
        for contract in contracts
    )
    content_id = _text(raw["content_id"], field="governance_bundle.content_id")
    if not _SHA256.fullmatch(content_id):
        raise ValueError("governance_bundle.content_id must be a lowercase SHA-256 digest")
    return GovernanceBundle(
        schema=schema,
        recorded_at=recorded_at,
        catalog=catalog,
        mapping_pack=mapping_pack,
        formula_pack=formula_pack,
        contracts=projected,
        content_id=content_id,
    )


def _content_digest(raw: Mapping[str, Any]) -> str:
    """Hash the parsed config, excluding only its pinned self-digest field."""
    content = dict(raw)
    content.pop("content_sha256", None)
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


def _verify_content_digest(raw: Mapping[str, Any], *, field: str) -> str:
    declared = _text(raw.get("content_sha256"), field=f"{field}.content_sha256")
    if not _SHA256.fullmatch(declared):
        raise ValueError(f"{field}.content_sha256 must be a lowercase SHA-256 digest")
    actual = _content_digest(raw)
    if not hmac.compare_digest(declared, actual):
        raise ValueError(f"{field}.content_sha256 does not match immutable content")
    return declared


def _parse_formula_expression(
    expression: str,
    dependencies: tuple[str, ...],
    *,
    field: str,
) -> ast.AST:
    """Accept a deliberately tiny arithmetic language and bind its inputs."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"{field} must be a valid restricted arithmetic expression") from exc

    names: set[str] = set()

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.Name):
            if not isinstance(node.ctx, ast.Load) or not _IDENTIFIER.fullmatch(node.id):
                raise ValueError(f"{field} has an invalid identifier")
            names.add(node.id)
            return
        if isinstance(node, ast.BinOp):
            if not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                raise ValueError(f"{field} permits only +, -, *, and / arithmetic")
            visit(node.left)
            visit(node.right)
            return
        raise ValueError(f"{field} contains an unsupported expression construct")

    visit(tree.body)
    if names != set(dependencies):
        raise ValueError(f"{field} identifiers must exactly equal declared dependencies")
    return tree.body


def _unit_dimension(unit: str) -> tuple[tuple[str, int], ...]:
    """Return the closed v1 unit algebra as canonical base exponents."""
    dimensions = {
        "USD": {"USD": 1},
        "shares": {"shares": 1},
        "USD/shares": {"USD": 1, "shares": -1},
        "ratio": {},
    }
    try:
        value = dimensions[unit]
    except KeyError as exc:  # pragma: no cover - units are validated earlier
        raise ValueError(f"unsupported unit in formula algebra: {unit}") from exc
    return tuple(sorted(value.items()))


def _combine_dimensions(
    left: tuple[tuple[str, int], ...],
    right: tuple[tuple[str, int], ...],
    *,
    subtract: bool = False,
) -> tuple[tuple[str, int], ...]:
    result = dict(left)
    direction = -1 if subtract else 1
    for base, exponent in right:
        result[base] = result.get(base, 0) + direction * exponent
        if result[base] == 0:
            del result[base]
    return tuple(sorted(result.items()))


def _infer_formula_dimension(
    node: ast.AST,
    dependency_dimensions: Mapping[str, tuple[tuple[str, int], ...]],
    *,
    field: str,
) -> tuple[tuple[str, int], ...]:
    if isinstance(node, ast.Name):
        return dependency_dimensions[node.id]
    if not isinstance(node, ast.BinOp):  # pragma: no cover - restricted parser guards this
        raise ValueError(f"{field} contains an unsupported unit expression")
    left = _infer_formula_dimension(node.left, dependency_dimensions, field=field)
    right = _infer_formula_dimension(node.right, dependency_dimensions, field=field)
    if isinstance(node.op, (ast.Add, ast.Sub)):
        if left != right:
            raise ValueError(f"{field} unit algebra requires matching units for + or -")
        return left
    if isinstance(node.op, ast.Mult):
        return _combine_dimensions(left, right)
    if isinstance(node.op, ast.Div):
        return _combine_dimensions(left, right, subtract=True)
    raise ValueError(f"{field} contains an unsupported unit operator")  # pragma: no cover


def _load_yaml(path: str | Path, *, label: str) -> Mapping[str, Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return _require_mapping(raw, field=label)


def metric_registry_from_dicts(
    catalog_raw: Mapping[str, Any],
    mappings_raw: Mapping[str, Any],
    formulas_raw: Mapping[str, Any],
) -> MetricRegistry:
    """Create and validate a registry from parsed YAML objects."""
    if catalog_raw.get("schema") != CATALOG_SCHEMA:
        raise ValueError(f"catalog.schema must equal {CATALOG_SCHEMA}")
    if mappings_raw.get("schema") != MAPPINGS_SCHEMA:
        raise ValueError(f"mappings.schema must equal {MAPPINGS_SCHEMA}")
    if formulas_raw.get("schema") != FORMULAS_SCHEMA:
        raise ValueError(f"formulas.schema must equal {FORMULAS_SCHEMA}")

    catalog_id = _identifier(catalog_raw.get("catalog_id"), field="catalog.catalog_id")
    if catalog_id != CORE_V1_CATALOG_ID:
        raise ValueError(f"catalog.catalog_id must equal {CORE_V1_CATALOG_ID}")
    catalog_version = _version(catalog_raw.get("catalog_version"), field="catalog.catalog_version")
    if catalog_version.split(".", 1)[0] != "1":
        raise ValueError("metric catalog schema v1 only admits major catalog version 1")
    catalog_available = _utc(catalog_raw.get("available_at"), field="catalog.available_at")
    catalog_digest = _verify_content_digest(catalog_raw, field="catalog")
    mapping_pack_id = _identifier(mappings_raw.get("mapping_pack_id"), field="mappings.mapping_pack_id")
    mapping_pack_version = _version(
        mappings_raw.get("mapping_pack_version"), field="mappings.mapping_pack_version"
    )
    mapping_pack_available = _utc(mappings_raw.get("available_at"), field="mappings.available_at")
    mapping_pack_digest = _verify_content_digest(mappings_raw, field="mappings")
    formula_pack_id = _identifier(formulas_raw.get("formula_pack_id"), field="formulas.formula_pack_id")
    formula_pack_version = _version(
        formulas_raw.get("formula_pack_version"), field="formulas.formula_pack_version"
    )
    formula_pack_available = _utc(formulas_raw.get("available_at"), field="formulas.available_at")
    formula_pack_digest = _verify_content_digest(formulas_raw, field="formulas")
    if mapping_pack_available < catalog_available or formula_pack_available < catalog_available:
        raise ValueError("mapping and formula packs cannot predate the catalog they govern")

    metric_entries = _require_list(catalog_raw.get("metrics"), field="catalog.metrics")
    if "expected_metric_count" in catalog_raw:
        raise ValueError("catalog.expected_metric_count is forbidden; v1 count is schema-governed")
    if len(metric_entries) != CORE_V1_METRIC_COUNT:
        raise ValueError(f"metric catalog v1 requires exactly {CORE_V1_METRIC_COUNT} contracts")

    base_contracts: dict[str, dict[str, Any]] = {}
    rule_keys: set[tuple[str, str]] = set()
    rule_ids: set[str] = set()

    def claim_rule(rule: ImmutableRule) -> None:
        key = (rule.rule_id, rule.version)
        if key in rule_keys:
            raise ValueError(f"duplicate immutable rule/version: {rule.rule_id}@{rule.version}")
        if rule.rule_id in rule_ids:
            raise ValueError(f"rule replacement/supersession is unsupported: {rule.rule_id}")
        rule_keys.add(key)
        rule_ids.add(rule.rule_id)

    for index, item in enumerate(metric_entries):
        raw = _require_mapping(item, field=f"catalog.metrics[{index}]")
        _exact_keys(
            raw,
            field=f"catalog.metrics[{index}]",
            required=frozenset(
                {
                    "metric_id", "label", "category", "rule", "units", "period_constraints",
                    "dimensional_profile", "presentation_constraints", "review", "no_result",
                    "formula_dependencies",
                }
            ),
        )
        metric_id = _identifier(raw.get("metric_id"), field=f"catalog.metrics[{index}].metric_id")
        if metric_id in base_contracts:
            raise ValueError(f"duplicate metric_id: {metric_id}")
        rule = _rule(raw.get("rule"), field=f"catalog.metrics[{index}].rule")
        claim_rule(rule)
        if rule.available_at < catalog_available:
            raise ValueError(f"metric {metric_id} cannot predate catalog availability")
        base_contracts[metric_id] = {
            "label": _text(raw.get("label"), field=f"catalog.metrics[{index}].label"),
            "category": _identifier(raw.get("category"), field=f"catalog.metrics[{index}].category"),
            "rule": rule,
            "units": _units(raw.get("units"), field=f"catalog.metrics[{index}].units"),
            "period_constraints": _period_constraints(
                raw.get("period_constraints"), field=f"catalog.metrics[{index}].period_constraints"
            ),
            "dimensional_profile": _dimensional_profile(
                raw.get("dimensional_profile"), field=f"catalog.metrics[{index}].dimensional_profile"
            ),
            "presentation_constraints": _presentation(
                raw.get("presentation_constraints"),
                field=f"catalog.metrics[{index}].presentation_constraints",
            ),
            "review": _review(raw.get("review"), field=f"catalog.metrics[{index}].review"),
            "no_result": _no_result(raw.get("no_result"), field=f"catalog.metrics[{index}].no_result"),
            "declared_formula_dependencies": _dependencies(
                raw.get("formula_dependencies"),
                field=f"catalog.metrics[{index}].formula_dependencies",
            ),
        }

    mapping_by_metric: dict[str, list[MappingRule]] = {metric_id: [] for metric_id in base_contracts}
    seen_aliases: dict[tuple[str, str], str] = {}
    mapping_entries = _require_list(mappings_raw.get("mappings"), field="mappings.mappings")
    default_taxonomy_version_start = mappings_raw.get("default_taxonomy_version_start")
    default_taxonomy_version_end = mappings_raw.get("default_taxonomy_version_end")
    if (
        type(default_taxonomy_version_start) is not int
        or type(default_taxonomy_version_end) is not int
        or default_taxonomy_version_start > default_taxonomy_version_end
    ):
        raise ValueError("mappings default taxonomy applicability must be an ordered integer range")
    for index, item in enumerate(mapping_entries):
        raw = _require_mapping(item, field=f"mappings.mappings[{index}]")
        _exact_keys(
            raw,
            field=f"mappings.mappings[{index}]",
            required=frozenset({"metric_id", "rule", "taxonomy_concept_aliases"}),
        )
        metric_id = _identifier(raw.get("metric_id"), field=f"mappings.mappings[{index}].metric_id")
        if metric_id not in base_contracts:
            raise ValueError(f"mapping references unknown metric: {metric_id}")
        rule = _rule(raw.get("rule"), field=f"mappings.mappings[{index}].rule")
        claim_rule(rule)
        metric_rule = base_contracts[metric_id]["rule"]
        if rule.available_at < mapping_pack_available or rule.available_at < metric_rule.available_at:
            raise ValueError(f"mapping rule for {metric_id} cannot predate its pack or metric rule")
        if rule.confidence != metric_rule.confidence:
            raise ValueError(f"mapping rule confidence must match metric contract confidence for {metric_id}")
        aliases: list[ConceptAlias] = []
        priorities: set[int] = set()
        for alias_index, alias_item in enumerate(_require_list(
            raw.get("taxonomy_concept_aliases"),
            field=f"mappings.mappings[{index}].taxonomy_concept_aliases",
        )):
            alias_raw = _require_mapping(
                alias_item, field=f"mappings.mappings[{index}].taxonomy_concept_aliases[{alias_index}]"
            )
            _exact_keys(
                alias_raw,
                field=f"mappings.mappings[{index}].taxonomy_concept_aliases[{alias_index}]",
                required=frozenset({"taxonomy", "concept", "priority"}),
                optional=frozenset({"taxonomy_version_start", "taxonomy_version_end"}),
            )
            taxonomy = _text(alias_raw.get("taxonomy"), field="taxonomy_concept_aliases.taxonomy")
            concept = _text(alias_raw.get("concept"), field="taxonomy_concept_aliases.concept")
            priority = alias_raw.get("priority")
            taxonomy_version_start = alias_raw.get(
                "taxonomy_version_start", default_taxonomy_version_start
            )
            taxonomy_version_end = alias_raw.get("taxonomy_version_end", default_taxonomy_version_end)
            if taxonomy not in ALLOWED_TAXONOMIES:
                raise ValueError(
                    f"issuer-extension or unsupported taxonomy mapping is prohibited: {taxonomy}"
                )
            if not _CONCEPT.fullmatch(concept):
                raise ValueError(f"taxonomy concept must be a standard local-name: {concept!r}")
            known_concept = KNOWN_CONCEPT_ALLOWLIST.get((taxonomy, concept))
            if known_concept is None:
                raise ValueError(f"taxonomy concept is not in the governed known-concept allowlist: {taxonomy}:{concept}")
            if (
                type(taxonomy_version_start) is not int
                or type(taxonomy_version_end) is not int
                or taxonomy_version_start > taxonomy_version_end
                or taxonomy_version_start < known_concept.taxonomy_version_start
                or taxonomy_version_end > known_concept.taxonomy_version_end
            ):
                raise ValueError(
                    f"taxonomy applicability for {taxonomy}:{concept} must stay within its governed version range"
                )
            metric_period = base_contracts[metric_id]["period_constraints"].kind
            metric_units = base_contracts[metric_id]["units"]
            if metric_period != known_concept.period_kind or metric_units != known_concept.contract_units:
                raise ValueError(
                    f"taxonomy concept {taxonomy}:{concept} does not match {metric_id} period or unit contract"
                )
            if not isinstance(priority, int) or priority < 1 or priority in priorities:
                raise ValueError("taxonomy concept aliases require unique positive priorities")
            priorities.add(priority)
            existing = seen_aliases.get((taxonomy, concept))
            if existing is not None:
                raise ValueError(
                    f"duplicate standard concept alias {taxonomy}:{concept}; "
                    f"already governed by {existing}"
                )
            seen_aliases[(taxonomy, concept)] = metric_id
            aliases.append(
                ConceptAlias(
                    taxonomy,
                    concept,
                    priority,
                    taxonomy_version_start,
                    taxonomy_version_end,
                )
            )
        if not aliases:
            raise ValueError(f"mapping for {metric_id} must provide standard taxonomy aliases")
        mapping_by_metric[metric_id].append(MappingRule(metric_id, rule, tuple(aliases)))

    formula_by_metric: dict[str, FormulaRule] = {}
    formula_entries = _require_list(formulas_raw.get("formulas"), field="formulas.formulas")
    for index, item in enumerate(formula_entries):
        raw = _require_mapping(item, field=f"formulas.formulas[{index}]")
        _exact_keys(
            raw,
            field=f"formulas.formulas[{index}]",
            required=frozenset(
                {"metric_id", "rule", "expression", "dependencies", "output_unit", "dependency_period_alignment"}
            ),
        )
        metric_id = _identifier(raw.get("metric_id"), field=f"formulas.formulas[{index}].metric_id")
        if metric_id not in base_contracts:
            raise ValueError(f"formula references unknown metric: {metric_id}")
        if metric_id in formula_by_metric:
            raise ValueError(f"duplicate formula metric: {metric_id}")
        rule = _rule(raw.get("rule"), field=f"formulas.formulas[{index}].rule")
        claim_rule(rule)
        metric_rule = base_contracts[metric_id]["rule"]
        if rule.available_at < formula_pack_available or rule.available_at < metric_rule.available_at:
            raise ValueError(f"formula rule for {metric_id} cannot predate its pack or metric rule")
        if rule.confidence != metric_rule.confidence:
            raise ValueError(f"formula rule confidence must match metric contract confidence for {metric_id}")
        expression = _text(raw.get("expression"), field=f"formulas.formulas[{index}].expression")
        dependencies = _dependencies(raw.get("dependencies"), field=f"formulas.formulas[{index}].dependencies")
        if not dependencies:
            raise ValueError(f"formula {metric_id} must declare dependencies")
        unknown = sorted(set(dependencies) - set(base_contracts))
        if unknown:
            raise ValueError(f"formula {metric_id} has unknown dependencies: {', '.join(unknown)}")
        if metric_id in dependencies:
            raise ValueError(f"formula {metric_id} cannot depend on itself")
        expression_node = _parse_formula_expression(
            expression,
            dependencies,
            field=f"formulas.formulas[{index}].expression",
        )
        output_unit = _text(raw.get("output_unit"), field=f"formulas.formulas[{index}].output_unit")
        if output_unit not in base_contracts[metric_id]["units"]:
            raise ValueError(f"formula {metric_id} output unit must be one of the metric contract units")
        dependency_dimensions: dict[str, tuple[tuple[str, int], ...]] = {}
        for dependency in dependencies:
            dependency_units = base_contracts[dependency]["units"]
            if len(dependency_units) != 1:
                raise ValueError(
                    f"formula {metric_id} dependency {dependency} must have exactly one governed unit"
                )
            dependency_dimensions[dependency] = _unit_dimension(dependency_units[0])
        inferred_dimension = _infer_formula_dimension(
            expression_node,
            dependency_dimensions,
            field=f"formula {metric_id}",
        )
        if inferred_dimension != _unit_dimension(output_unit):
            raise ValueError(
                f"formula {metric_id} unit algebra does not match declared output unit {output_unit}"
            )
        alignment = _text(
            raw.get("dependency_period_alignment"),
            field=f"formulas.formulas[{index}].dependency_period_alignment",
        )
        if alignment not in ALLOWED_ALIGNMENTS:
            raise ValueError(f"formula {metric_id} has unsupported period alignment")
        formula_by_metric[metric_id] = FormulaRule(
            metric_id, rule, expression, dependencies, output_unit, alignment
        )

    contracts: list[MetricContract] = []
    for metric_id in sorted(base_contracts):
        base = base_contracts[metric_id]
        formula = formula_by_metric.get(metric_id)
        declared = base["declared_formula_dependencies"]
        if formula is not None and declared != formula.dependencies:
            raise ValueError(
                f"formula dependencies for {metric_id} must exactly match its metric contract declaration"
            )
        if formula is None and declared:
            raise ValueError(f"metric {metric_id} declares formula dependencies without a formula rule")
        if formula is None and not mapping_by_metric[metric_id]:
            raise ValueError(f"metric {metric_id} has neither standard mapping nor formula")
        if formula is not None and mapping_by_metric[metric_id]:
            raise ValueError(f"metric {metric_id} cannot mix direct mappings and formula rules in v1")
        if formula is None:
            required_no_result_codes = {
                "missing_standard_fact",
                "outside_period_constraint",
                "disallowed_dimension",
            }
        else:
            if not base["review"].required:
                raise ValueError(f"derived metric {metric_id} must require review")
            required_no_result_codes = {
                "missing_dependency",
                "incompatible_dependencies",
                "division_by_zero",
            }
        missing_no_result_codes = required_no_result_codes - set(base["no_result"].codes)
        if missing_no_result_codes:
            raise ValueError(
                f"metric {metric_id} omits required fail-closed no-result codes: "
                f"{', '.join(sorted(missing_no_result_codes))}"
            )
        contracts.append(
            MetricContract(
                metric_id=metric_id,
                label=base["label"],
                category=base["category"],
                rule=base["rule"],
                units=base["units"],
                period_constraints=base["period_constraints"],
                dimensional_profile=base["dimensional_profile"],
                presentation_constraints=base["presentation_constraints"],
                review=base["review"],
                no_result=base["no_result"],
                declared_formula_dependencies=declared,
                mappings=tuple(sorted(mapping_by_metric[metric_id], key=lambda item: item.rule.rule_id)),
                formula=formula,
            )
        )

    direct_count = sum(contract.formula is None for contract in contracts)
    formula_count = sum(contract.formula is not None for contract in contracts)
    if (
        direct_count != CORE_V1_DIRECT_METRIC_COUNT
        or formula_count != CORE_V1_FORMULA_METRIC_COUNT
    ):
        raise ValueError(
            "metric catalog v1 requires exactly "
            f"{CORE_V1_DIRECT_METRIC_COUNT} direct and "
            f"{CORE_V1_FORMULA_METRIC_COUNT} formula contracts"
        )

    contracts_by_metric = {contract.metric_id: contract for contract in contracts}

    def materialized_available_at(contract: MetricContract, *, cutoff: datetime) -> datetime | None:
        """Return governance readiness using only definitions known at ``cutoff``.

        A new mapping rule can be appended years after a formula was admitted.
        It must not make the old formula retroactively impossible: readiness is
        therefore evaluated at the formula rule's own availability clock.
        """
        if contract.rule.available_at > cutoff:
            return None
        clocks = [catalog_available, contract.rule.available_at]
        if contract.formula is not None:
            if contract.formula.rule.available_at > cutoff:
                return None
            clocks.extend((formula_pack_available, contract.formula.rule.available_at))
        else:
            visible_mappings = tuple(
                mapping for mapping in contract.mappings if mapping.rule.available_at <= cutoff
            )
            if not visible_mappings:
                return None
            clocks.append(mapping_pack_available)
            clocks.extend(mapping.rule.available_at for mapping in visible_mappings)
        return max(clocks)

    for contract in contracts:
        if contract.formula is None:
            continue
        dependency_period_kinds = tuple(
            contracts_by_metric[dependency].period_constraints.kind
            for dependency in contract.formula.dependencies
        )
        if contract.formula.dependency_period_alignment == "same_period":
            if any(kind != contract.period_constraints.kind for kind in dependency_period_kinds):
                raise ValueError(
                    f"formula {contract.metric_id} same_period alignment requires matching dependency period kinds"
                )
        elif (
            contract.formula.dependency_period_alignment == "ending_instant_to_duration"
            and (
                contract.period_constraints.kind != "duration"
                or sorted(dependency_period_kinds) != ["duration", "instant"]
            )
        ):
            raise ValueError(
                f"formula {contract.metric_id} ending_instant_to_duration alignment requires one instant and one duration dependency"
            )
        for dependency in contract.formula.dependencies:
            dependency_ready = materialized_available_at(
                contracts_by_metric[dependency], cutoff=contract.formula.rule.available_at
            )
            if (
                dependency_ready is None
                or contract.formula.rule.available_at < dependency_ready
            ):
                raise ValueError(
                    f"formula {contract.metric_id} cannot predate dependency availability visible at its availability for {dependency}"
                )

    registry = MetricRegistry(
        catalog_id=catalog_id,
        catalog_version=catalog_version,
        available_at=catalog_available,
        catalog_content_sha256=catalog_digest,
        mapping_pack_id=mapping_pack_id,
        mapping_pack_version=mapping_pack_version,
        mapping_pack_available_at=mapping_pack_available,
        mapping_pack_content_sha256=mapping_pack_digest,
        formula_pack_id=formula_pack_id,
        formula_pack_version=formula_pack_version,
        formula_pack_available_at=formula_pack_available,
        formula_pack_content_sha256=formula_pack_digest,
        contracts=tuple(contracts),
    )
    validate_metric_registry(registry)
    return registry


def validate_metric_registry(registry: MetricRegistry) -> None:
    """Validate immutable lane clocks and graph properties after construction.

    This intentionally admits a future definition whose detailed source-config
    review has not happened yet: it can never affect a cutoff before its own
    rule clock. It does *not* admit moving a lane's inception clock past an
    existing child definition, nor a replacement of an immutable rule ID.
    """
    if not isinstance(registry.contracts, tuple):
        raise TypeError("registry contracts must be a tuple")
    if any(not isinstance(contract, MetricContract) for contract in registry.contracts):
        raise TypeError("registry contracts must contain MetricContract values")
    known = set(registry.metric_ids)
    if len(known) != len(registry.contracts):
        raise ValueError("registry contains duplicate metric contracts")
    if registry.mapping_pack_available_at < registry.available_at:
        raise ValueError("mapping pack lane cannot predate catalog lane inception")
    if registry.formula_pack_available_at < registry.available_at:
        raise ValueError("formula pack lane cannot predate catalog lane inception")

    rule_ids: set[str] = set()
    rule_versions: set[tuple[str, str]] = set()

    def claim_rule(rule: ImmutableRule) -> None:
        if not isinstance(rule, ImmutableRule):
            raise TypeError("registry definitions must use ImmutableRule clocks")
        key = (rule.rule_id, rule.version)
        if key in rule_versions:
            raise ValueError(f"duplicate immutable rule/version: {rule.rule_id}@{rule.version}")
        if rule.rule_id in rule_ids:
            raise ValueError(f"rule replacement/supersession is unsupported: {rule.rule_id}")
        rule_versions.add(key)
        rule_ids.add(rule.rule_id)

    for contract in registry.contracts:
        if contract.rule.available_at < registry.available_at:
            raise ValueError(f"metric {contract.metric_id} predates catalog lane inception")
        claim_rule(contract.rule)
        if not isinstance(contract.mappings, tuple):
            raise TypeError(f"metric {contract.metric_id} mappings must be a tuple")
        if contract.mappings and contract.formula is not None:
            raise ValueError(f"metric {contract.metric_id} cannot mix direct mappings and formula rules")
        for mapping in contract.mappings:
            if not isinstance(mapping, MappingRule) or mapping.metric_id != contract.metric_id:
                raise ValueError(f"mapping does not belong to metric contract {contract.metric_id}")
            if mapping.rule.available_at < max(registry.mapping_pack_available_at, contract.rule.available_at):
                raise ValueError(f"mapping rule for {contract.metric_id} predates its lane or metric contract")
            claim_rule(mapping.rule)
        if contract.formula is not None:
            formula = contract.formula
            if not isinstance(formula, FormulaRule) or formula.metric_id != contract.metric_id:
                raise ValueError(f"formula does not belong to metric contract {contract.metric_id}")
            if formula.rule.available_at < max(registry.formula_pack_available_at, contract.rule.available_at):
                raise ValueError(f"formula rule for {contract.metric_id} predates its lane or metric contract")
            if formula.dependencies != contract.declared_formula_dependencies:
                raise ValueError(f"formula dependencies for {contract.metric_id} must match metric contract declaration")
            claim_rule(formula.rule)

    formula_by_metric = {contract.metric_id: contract.formula for contract in registry.contracts if contract.formula}

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(metric_id: str) -> None:
        if metric_id in visited:
            return
        if metric_id in visiting:
            raise ValueError(f"formula dependency graph contains a cycle at {metric_id}")
        visiting.add(metric_id)
        formula = formula_by_metric.get(metric_id)
        if formula:
            for dependency in formula.dependencies:
                if dependency not in known:
                    raise ValueError(f"formula {metric_id} depends on unknown metric {dependency}")
                visit(dependency)
        visiting.remove(metric_id)
        visited.add(metric_id)

    for metric_id in sorted(formula_by_metric):
        visit(metric_id)

    contracts_by_metric = {contract.metric_id: contract for contract in registry.contracts}

    def ready_at(contract: MetricContract, *, cutoff: datetime) -> datetime | None:
        if contract.rule.available_at > cutoff:
            return None
        if contract.formula is not None:
            if contract.formula.rule.available_at > cutoff:
                return None
            return max(
                registry.available_at,
                registry.formula_pack_available_at,
                contract.rule.available_at,
                contract.formula.rule.available_at,
            )
        visible_mappings = tuple(
            mapping for mapping in contract.mappings if mapping.rule.available_at <= cutoff
        )
        if not visible_mappings:
            return None
        return max(
            registry.available_at,
            registry.mapping_pack_available_at,
            contract.rule.available_at,
            *(mapping.rule.available_at for mapping in visible_mappings),
        )

    for contract in registry.contracts:
        formula = contract.formula
        if formula is None:
            continue
        for dependency in formula.dependencies:
            dependency_ready = ready_at(
                contracts_by_metric[dependency], cutoff=formula.rule.available_at
            )
            # A construction-time future fixture may omit every dependency
            # definition visible at this formula's own clock. That makes the
            # formula non-evaluable at query time; it is not proof that a
            # future-only append has rewritten the old formula. When a visible
            # definition exists, however, its readiness is a hard floor.
            if dependency_ready is not None and formula.rule.available_at < dependency_ready:
                raise ValueError(
                    f"formula {contract.metric_id} cannot predate dependency availability visible at its availability for {dependency}"
                )


def load_metric_registry(
    catalog_path: str | Path,
    mappings_path: str | Path,
    formulas_path: str | Path,
) -> MetricRegistry:
    return metric_registry_from_dicts(
        _load_yaml(catalog_path, label="catalog"),
        _load_yaml(mappings_path, label="mappings"),
        _load_yaml(formulas_path, label="formulas"),
    )


def load_core_metric_registry(root: str | Path | None = None) -> MetricRegistry:
    """Load the repository's governed v1 core registry without caller path glue."""
    repo = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    metric_root = repo / "config" / "fundamental_forensics" / "metrics" / "v1"
    return load_metric_registry(
        metric_root / "metric_catalog.yaml",
        metric_root / "mappings" / "core.yaml",
        metric_root / "formulas" / "core.yaml",
    )
