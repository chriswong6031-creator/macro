"""Parser-result → RawFactLedger adapter for golden SEC iXBRL packages.

This module does not parse XML. It consumes ``parse_sec_filing_document(...)``
output plus already-admitted filing-package metadata and emits canonical
``RawFactOccurrence`` events for the existing query kernel.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from collectors.sec_filing_parser import SecFilingParseError, parse_sec_filing_document

from .financial_intelligence_packet import load_core_registry
from .query import FilingMetadata
from .query_service import (
    CanonicalEntityBinding,
    FinancialQueryAdmissionError,
    FinancialQueryDataset,
    FinancialQueryUnavailableError,
)
from .raw_ledger import (
    FactContext,
    FactEventType,
    FactUnit,
    RawFactLedger,
    RawFactOccurrence,
    SourceIdentity,
    canonical_json,
    make_raw_fact,
)
from .sec_document_spine import archive_document_url, canonical_cik, sec_document_id
from .statement_graph import (
    GOLDEN_AAPL_FIXTURES,
    GoldenFilingPackage,
    StatementGraphError,
    load_golden_aapl_package,
)
from .statement_service import _bind_data_os_issuer

_GOLDEN_ENTITY_ID = "ISS:US-XNAS-AAPL"
_GOLDEN_LISTING_KEY = "US-XNAS-AAPL"
_ISO4217_NS = "http://www.xbrl.org/2003/iso4217"
_XBRLI_NS = "http://www.xbrl.org/2003/instance"
_UNIT_MEASURE_PREFIX = {
    _ISO4217_NS: "iso4217",
    _XBRLI_NS: "xbrli",
}
_AAPL_DELIVERY = MappingProxyType(
    {
        "kind": "committed_golden_fixture",
        "attested": False,
        "production_issuer_service": False,
    }
)


class IxbrlRawLedgerError(ValueError):
    """A parsed filing cannot be converted into the canonical raw ledger."""


@dataclass(frozen=True)
class FilingConversionReceipt:
    accession: str
    parser_numeric_fact_count: int
    ledger_occurrence_count: int
    represented_count: int
    excluded: Mapping[str, int]
    source_namespace_families: tuple[str, ...]


@dataclass(frozen=True)
class ConversionReport:
    filings: tuple[FilingConversionReceipt, ...]
    ledger_sha256: str
    source_namespace_families: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "filings": [
                {
                    "accession": item.accession,
                    "parser_numeric_fact_count": item.parser_numeric_fact_count,
                    "ledger_occurrence_count": item.ledger_occurrence_count,
                    "represented_count": item.represented_count,
                    "excluded": dict(item.excluded),
                    "source_namespace_families": list(item.source_namespace_families),
                }
                for item in self.filings
            ],
            "ledger_sha256": self.ledger_sha256,
            "source_namespace_families": list(self.source_namespace_families),
        }


def _taxonomy_namespace_policy() -> Mapping[str, str]:
    from .filing_attestation import TAXONOMY_NAMESPACE_POLICY

    return TAXONOMY_NAMESPACE_POLICY


def _unit_policy() -> Mapping[tuple[tuple[str, ...], tuple[str, ...]], str]:
    from .filing_attestation import UNIT_POLICY

    return UNIT_POLICY


def _clark_parts(value: str) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value.startswith("{") or "}" not in value:
        return None
    namespace, local = value[1:].split("}", 1)
    if not namespace or not local:
        return None
    return namespace, local


def canonicalize_clark_qname(value: str) -> str:
    """Map recognized standard namespace families to ``taxonomy:concept``.

    Unknown and issuer/custom namespaces keep their source Clark identity.
    Local names never imply a standard taxonomy.
    """
    parts = _clark_parts(value)
    if parts is None:
        return value
    namespace, local = parts
    prefix = _taxonomy_namespace_policy().get(namespace)
    if prefix is not None:
        return f"{prefix}:{local}"
    unit_prefix = _UNIT_MEASURE_PREFIX.get(namespace)
    if unit_prefix is not None:
        return f"{unit_prefix}:{local}"
    return value


def _canonical_measures(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(canonicalize_clark_qname(str(item)) for item in values)


def _fact_unit(unit: Mapping[str, Any] | None) -> FactUnit | None:
    if unit is None:
        return None
    unit_id = unit.get("unit_id")
    numerator = unit.get("numerator_measures")
    denominator = unit.get("denominator_measures")
    if not isinstance(unit_id, str) or not isinstance(numerator, list):
        return None
    if not isinstance(denominator, list):
        denominator = []
    if not all(isinstance(item, str) for item in numerator + denominator):
        return None
    policy_key = (tuple(numerator), tuple(denominator))
    mapped = _unit_policy().get(policy_key)
    if mapped == "USD":
        return FactUnit(unit_id, ["iso4217:USD"])
    if mapped == "shares":
        return FactUnit(unit_id, ["xbrli:shares"])
    if mapped == "pure":
        return FactUnit(unit_id, ["xbrli:pure"])
    if mapped == "USD/shares":
        return FactUnit(unit_id, ["iso4217:USD"], ["xbrli:shares"])
    return FactUnit(unit_id, list(_canonical_measures(numerator)), list(_canonical_measures(denominator)))


def _lexical_date(value: Any, *, field_name: str) -> date:
    if not isinstance(value, str) or len(value) < 10:
        raise IxbrlRawLedgerError(f"{field_name} is not a lexical period date")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise IxbrlRawLedgerError(f"{field_name} is not a lexical period date") from exc


def _period_kwargs(period: Mapping[str, Any] | None) -> dict[str, date] | None:
    if not isinstance(period, Mapping):
        return None
    kind = period.get("kind")
    if kind == "forever":
        return None
    if kind == "instant":
        return {"instant": _lexical_date(period.get("instant_date"), field_name="instant_date")}
    if kind == "duration":
        return {
            "start": _lexical_date(period.get("start_date"), field_name="start_date"),
            "end": _lexical_date(period.get("end_date"), field_name="end_date"),
        }
    raise IxbrlRawLedgerError("context period kind is not representable")


def _dimensions_known(context: Mapping[str, Any]) -> bool:
    return (
        context.get("segment_content_status") == "complete"
        and context.get("scenario_content_status") == "complete"
    )


def _dimension_maps(context: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    explicit: dict[str, str] = {}
    typed: dict[str, str] = {}
    for item in context.get("dimensions") or []:
        if not isinstance(item, Mapping):
            continue
        axis = canonicalize_clark_qname(str(item.get("dimension_qname") or ""))
        if not axis:
            continue
        if item.get("kind") == "explicit":
            member = item.get("member_qname")
            if isinstance(member, str) and member:
                explicit[axis] = canonicalize_clark_qname(member)
        elif item.get("kind") == "typed":
            typed_xml = item.get("typed_value_xml")
            if isinstance(typed_xml, str) and typed_xml:
                typed[axis] = typed_xml
    return explicit, typed


def _source_span(raw: Any) -> tuple[int, int] | None:
    if not isinstance(raw, Mapping):
        return None
    start = raw.get("start")
    end = raw.get("end")
    if type(start) is not int or type(end) is not int:
        return None
    return (start, end)


def _namespace_family(concept_qname: str) -> str:
    parts = _clark_parts(concept_qname)
    if parts is None:
        if ":" in concept_qname:
            return concept_qname.split(":", 1)[0]
        return "unqualified"
    return parts[0]


def _primary_member(package: GoldenFilingPackage) -> dict[str, Any]:
    primary = package.manifest["primary_document"]
    for item in package.manifest.get("members") or []:
        if (
            isinstance(item, dict)
            and item.get("name") == primary
            and item.get("state") == "stored"
        ):
            return item
    raise IxbrlRawLedgerError("golden AAPL primary document is not retained")


def _contexts_by_id(parsed: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for item in parsed.get("contexts") or []:
        if not isinstance(item, Mapping):
            continue
        context_id = item.get("context_id")
        if isinstance(context_id, str) and context_id:
            out[context_id] = item
    return out


def _units_by_id(parsed: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for item in parsed.get("units") or []:
        if not isinstance(item, Mapping):
            continue
        unit_id = item.get("unit_id")
        if isinstance(unit_id, str) and unit_id:
            out[unit_id] = item
    return out


def _admit_entity_identity(parsed: Mapping[str, Any], package: GoldenFilingPackage) -> str:
    cik = canonical_cik(package.manifest["cik"])
    entity_ids = []
    for context in parsed.get("contexts") or []:
        if not isinstance(context, Mapping):
            continue
        ident = ((context.get("entity") or {}).get("identifier"))
        if ident:
            entity_ids.append(str(ident))
    unique = sorted(set(entity_ids))
    if unique != [cik]:
        raise IxbrlRawLedgerError("XBRL entity identifier is not the source-native AAPL CIK")
    return cik


def convert_parsed_filing(
    *,
    parsed: Mapping[str, Any],
    package: GoldenFilingPackage,
) -> tuple[tuple[RawFactOccurrence, ...], FilingMetadata, FilingConversionReceipt]:
    """Convert one strict-parser result into raw occurrences. Does not parse XML."""
    cik = _admit_entity_identity(parsed, package)
    accession = str(package.manifest["accession"])
    primary = str(package.manifest["primary_document"])
    member = _primary_member(package)
    body_sha256 = str(member["content_sha256"])
    document_id = sec_document_id(cik, accession, "primary", primary)
    source_url = archive_document_url(cik, accession, primary)
    accepted_at = package.manifest["source_accepted_at"]
    recorded_at = package.manifest["fixture_recorded_at"]
    contexts = _contexts_by_id(parsed)
    units = _units_by_id(parsed)
    families: set[str] = set()
    excluded: Counter[str] = Counter()
    occurrences: list[RawFactOccurrence] = []
    parser_numeric = 0

    for fact in parsed.get("facts") or []:
        if not isinstance(fact, Mapping):
            continue
        concept_qname = fact.get("concept_qname")
        if isinstance(concept_qname, str) and concept_qname:
            families.add(_namespace_family(concept_qname))
        kind = fact.get("kind")
        if kind != "numeric":
            if kind == "fraction":
                excluded["fraction"] += 1
            elif kind == "nonnumeric":
                excluded["nonnumeric"] += 1
            else:
                excluded["unsupported_kind"] += 1
            continue
        parser_numeric += 1
        context_ref = fact.get("context_ref")
        context = contexts.get(str(context_ref or ""))
        if context is None:
            excluded["missing_context"] += 1
            continue
        period = _period_kwargs(context.get("period"))
        if period is None:
            excluded["forever_period"] += 1
            continue
        is_nil = bool(fact.get("nil"))
        parsed_value = fact.get("normalized_value")
        status = fact.get("status")
        if not is_nil and (status != "available" or parsed_value is None):
            excluded[str(status) if status and status != "available" else "unnormalized_numeric"] += 1
            continue
        unit = _fact_unit(units.get(str(fact.get("unit_ref") or "")))
        if parsed_value is not None and unit is None:
            excluded["missing_unit"] += 1
            continue
        entity = context.get("entity") or {}
        identifier = str(entity.get("identifier") or "")
        scheme = str(entity.get("scheme") or "")
        if identifier != cik:
            raise IxbrlRawLedgerError("XBRL entity identifier is not the source-native AAPL CIK")
        explicit, typed = _dimension_maps(context)
        fact_id = fact.get("fact_id")
        try:
            occurrence = make_raw_fact(
                source=SourceIdentity(
                    source="sec-edgar",
                    entity_id=cik,
                    accession=accession,
                    document_id=document_id,
                    body_sha256=body_sha256,
                    source_url=source_url,
                ),
                concept_qname=canonicalize_clark_qname(str(concept_qname)),
                context=FactContext(
                    context_id=str(context.get("context_id") or context_ref),
                    entity_scheme=scheme,
                    entity_identifier=identifier,
                    explicit_dimensions=explicit,
                    typed_dimensions=typed,
                    **period,
                ),
                accepted_at=accepted_at,
                recorded_at=recorded_at,
                unit=unit,
                dimensions_known=_dimensions_known(context),
                source_occurrence_key=str(fact_id) if fact_id else None,
                raw_token=None if fact.get("raw_value") is None else str(fact.get("raw_value")),
                parsed_value=None if is_nil else parsed_value,
                is_nil=is_nil,
                xml_lang=fact.get("lang"),
                decimals=fact.get("decimals"),
                precision=fact.get("precision"),
                inline_format=fact.get("format"),
                inline_sign=fact.get("sign"),
                inline_scale=fact.get("scale"),
                hidden=bool(fact.get("hidden")),
                source_span=_source_span(fact.get("source_span")),
                event_type=FactEventType.FILED,
            )
        except (TypeError, ValueError) as exc:
            raise IxbrlRawLedgerError("numeric iXBRL occurrence is not representable") from exc
        occurrences.append(occurrence)

    represented = len(occurrences)
    if represented + sum(count for reason, count in excluded.items() if reason not in {"nonnumeric", "fraction", "unsupported_kind"}) != parser_numeric:
        raise IxbrlRawLedgerError("numeric iXBRL occurrence vanished without a typed exclusion")

    metadata = FilingMetadata(
        accession=accession,
        document_id=document_id,
        source_body_sha256=body_sha256,
        available_at=recorded_at,
        form=str(package.manifest.get("form") or ""),
        filed_at=str(package.manifest.get("filing_date") or ""),
    )
    receipt = FilingConversionReceipt(
        accession=accession,
        parser_numeric_fact_count=parser_numeric,
        ledger_occurrence_count=represented,
        represented_count=represented,
        excluded=MappingProxyType(dict(sorted(excluded.items()))),
        source_namespace_families=tuple(sorted(families)),
    )
    return tuple(occurrences), metadata, receipt


def convert_parsed_filings(
    pairs: Sequence[tuple[GoldenFilingPackage, Mapping[str, Any]]],
) -> tuple[RawFactLedger, dict[str, FilingMetadata], ConversionReport]:
    events: list[RawFactOccurrence] = []
    metadata: dict[str, FilingMetadata] = {}
    receipts: list[FilingConversionReceipt] = []
    families: set[str] = set()
    for package, parsed in pairs:
        filing_events, filing_metadata, receipt = convert_parsed_filing(
            parsed=parsed, package=package
        )
        events.extend(filing_events)
        metadata[filing_metadata.accession] = filing_metadata
        receipts.append(receipt)
        families.update(receipt.source_namespace_families)
    ledger = RawFactLedger(events)
    report = ConversionReport(
        filings=tuple(receipts),
        ledger_sha256=sha256(canonical_json(ledger.to_dict()).encode("utf-8")).hexdigest(),
        source_namespace_families=tuple(sorted(families)),
    )
    return ledger, metadata, report


def parse_and_convert_golden_packages(
    packages: Sequence[GoldenFilingPackage],
) -> tuple[RawFactLedger, dict[str, FilingMetadata], ConversionReport]:
    pairs: list[tuple[GoldenFilingPackage, Mapping[str, Any]]] = []
    for package in packages:
        primary = package.manifest["primary_document"]
        try:
            parsed = parse_sec_filing_document(package.members[primary], document_name=primary)
        except SecFilingParseError as exc:
            raise IxbrlRawLedgerError("golden AAPL primary document cannot be parsed") from exc
        pairs.append((package, parsed))
    return convert_parsed_filings(pairs)


class GoldenAaplFinancialQueryProvider:
    """Serves governed query over the committed AAPL golden filing set only."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
        self._dataset: FinancialQueryDataset | None = None
        self._report: ConversionReport | None = None

    def conversion_report(self) -> ConversionReport:
        self.resolve(_GOLDEN_ENTITY_ID)
        if self._report is None:
            raise FinancialQueryUnavailableError()
        return self._report

    def resolve(self, entity_id: str) -> FinancialQueryDataset:
        if entity_id != _GOLDEN_ENTITY_ID:
            raise FinancialQueryAdmissionError(400, "unknown entity")
        if self._dataset is not None:
            return self._dataset
        try:
            binding_row = _bind_data_os_issuer(self.repo_root, entity_id)
            if binding_row.get("listing_key") != _GOLDEN_LISTING_KEY:
                raise FinancialQueryUnavailableError()
            packages = [
                load_golden_aapl_package(self.repo_root, accession=accession)
                for accession in GOLDEN_AAPL_FIXTURES
            ]
            ledger, filing_metadata, report = parse_and_convert_golden_packages(packages)
            ticker = _GOLDEN_LISTING_KEY.rsplit("-", 1)[-1]
            dataset = FinancialQueryDataset(
                binding=CanonicalEntityBinding(
                    entity_id=binding_row["entity_id"],
                    cik=binding_row["cik"],
                    ticker=ticker,
                    source_entity_id=binding_row["cik"],
                ),
                ledger=ledger,
                filing_metadata=filing_metadata,
                registry=load_core_registry(self.repo_root),
                delivery=dict(_AAPL_DELIVERY),
            )
        except FinancialQueryAdmissionError:
            raise
        except FinancialQueryUnavailableError:
            raise
        except (StatementGraphError, IxbrlRawLedgerError, OSError, ValueError):
            raise FinancialQueryUnavailableError() from None
        self._dataset = dataset
        self._report = report
        return dataset


__all__ = [
    "ConversionReport",
    "FilingConversionReceipt",
    "GoldenAaplFinancialQueryProvider",
    "IxbrlRawLedgerError",
    "canonicalize_clark_qname",
    "convert_parsed_filing",
    "convert_parsed_filings",
    "parse_and_convert_golden_packages",
]
