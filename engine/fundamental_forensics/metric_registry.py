"""Governed, versioned contracts for the first core GAAP metric registry.

This module deliberately does *not* normalize facts or calculate formulas.  It
loads the immutable rules that later lanes must obey.  A bad catalog is rejected
at load time rather than being interpreted as an implicit fallback at runtime.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import yaml

from .models import canonical_json, parse_utc


CATALOG_SCHEMA = "fundamental_forensics.metric_catalog/v1"
MAPPINGS_SCHEMA = "fundamental_forensics.metric_mappings/v1"
FORMULAS_SCHEMA = "fundamental_forensics.metric_formulas/v1"
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
    mapping_pack_version: str
    mapping_pack_available_at: datetime
    mapping_pack_content_sha256: str
    formula_pack_version: str
    formula_pack_available_at: datetime
    formula_pack_content_sha256: str
    contracts: tuple[MetricContract, ...]

    def metric(self, metric_id: str) -> MetricContract:
        for contract in self.contracts:
            if contract.metric_id == metric_id:
                return contract
        raise KeyError(f"unknown metric: {metric_id}")

    @property
    def metric_ids(self) -> tuple[str, ...]:
        return tuple(contract.metric_id for contract in self.contracts)


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
    _identifier(mappings_raw.get("mapping_pack_id"), field="mappings.mapping_pack_id")
    mapping_pack_version = _version(
        mappings_raw.get("mapping_pack_version"), field="mappings.mapping_pack_version"
    )
    mapping_pack_available = _utc(mappings_raw.get("available_at"), field="mappings.available_at")
    mapping_pack_digest = _verify_content_digest(mappings_raw, field="mappings")
    _identifier(formulas_raw.get("formula_pack_id"), field="formulas.formula_pack_id")
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
    for index, item in enumerate(metric_entries):
        raw = _require_mapping(item, field=f"catalog.metrics[{index}]")
        metric_id = _identifier(raw.get("metric_id"), field=f"catalog.metrics[{index}].metric_id")
        if metric_id in base_contracts:
            raise ValueError(f"duplicate metric_id: {metric_id}")
        rule = _rule(raw.get("rule"), field=f"catalog.metrics[{index}].rule")
        if (rule.rule_id, rule.version) in rule_keys:
            raise ValueError(f"duplicate immutable rule/version: {rule.rule_id}@{rule.version}")
        rule_keys.add((rule.rule_id, rule.version))
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
        metric_id = _identifier(raw.get("metric_id"), field=f"mappings.mappings[{index}].metric_id")
        if metric_id not in base_contracts:
            raise ValueError(f"mapping references unknown metric: {metric_id}")
        rule = _rule(raw.get("rule"), field=f"mappings.mappings[{index}].rule")
        if (rule.rule_id, rule.version) in rule_keys:
            raise ValueError(f"duplicate immutable rule/version: {rule.rule_id}@{rule.version}")
        rule_keys.add((rule.rule_id, rule.version))
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
        metric_id = _identifier(raw.get("metric_id"), field=f"formulas.formulas[{index}].metric_id")
        if metric_id not in base_contracts:
            raise ValueError(f"formula references unknown metric: {metric_id}")
        if metric_id in formula_by_metric:
            raise ValueError(f"duplicate formula metric: {metric_id}")
        rule = _rule(raw.get("rule"), field=f"formulas.formulas[{index}].rule")
        if (rule.rule_id, rule.version) in rule_keys:
            raise ValueError(f"duplicate immutable rule/version: {rule.rule_id}@{rule.version}")
        rule_keys.add((rule.rule_id, rule.version))
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

    def materialized_available_at(contract: MetricContract) -> datetime:
        clocks = [contract.rule.available_at]
        clocks.extend(mapping.rule.available_at for mapping in contract.mappings)
        if contract.formula is not None:
            clocks.append(contract.formula.rule.available_at)
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
            dependency_ready = materialized_available_at(contracts_by_metric[dependency])
            if contract.formula.rule.available_at < dependency_ready:
                raise ValueError(
                    f"formula {contract.metric_id} cannot predate dependency availability for {dependency}"
                )

    registry = MetricRegistry(
        catalog_id=catalog_id,
        catalog_version=catalog_version,
        available_at=catalog_available,
        catalog_content_sha256=catalog_digest,
        mapping_pack_version=mapping_pack_version,
        mapping_pack_available_at=mapping_pack_available,
        mapping_pack_content_sha256=mapping_pack_digest,
        formula_pack_version=formula_pack_version,
        formula_pack_available_at=formula_pack_available,
        formula_pack_content_sha256=formula_pack_digest,
        contracts=tuple(contracts),
    )
    validate_metric_registry(registry)
    return registry


def validate_metric_registry(registry: MetricRegistry) -> None:
    """Validate graph properties that need the fully joined contract set."""
    known = set(registry.metric_ids)
    if len(known) != len(registry.contracts):
        raise ValueError("registry contains duplicate metric contracts")
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
