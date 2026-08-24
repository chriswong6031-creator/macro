"""FIF-3A4R research-only AAPL A1↔A2 logical-key overlap census.

Replay tool. Not a runtime provider. Does not import into engine/.
Reads accepted golden packages through parse_and_convert_golden_packages
and classifies every raw-ledger logical_key using existing duplicate-consistency
helpers. Does not mint revision_of, does not query, does not write engine state.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.fundamental_forensics.financial_intelligence_packet import load_core_registry
from engine.fundamental_forensics.ixbrl_raw_ledger import (
    GOLDEN_AAPL_QUERY_ACCESSIONS,
    parse_and_convert_golden_packages,
)
from engine.fundamental_forensics.raw_ledger import (
    RawFactOccurrence,
    _canonical_duplicate_representative,
    _duplicates_agree,
    canonical_json,
    utc_text,
)
from engine.fundamental_forensics.statement_graph import load_golden_aapl_package

A1 = "0000320193-25-000079"
A2 = "0000320193-26-000020"
EXPECTED_LEDGER_SHA = "ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8"
CORE_TAXONOMIES = frozenset({"us-gaap", "dei"})
CLASS_ORDER = (
    "incomplete_dimensional_scope",
    "custom_unmapped_taxonomy",
    "ambiguous_duplicate_group",
    "multiple_possible_parent",
    "nil_state_difference",
    "changed_value",
    "precision_different_value_consistent",
    "exact_complete_confirmation_candidate",
    "unit_context_concept_mismatch",
    "no_relation",
)


def _iso_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _taxonomy(concept_qname: str) -> str:
    if ":" not in concept_qname:
        return ""
    return concept_qname.split(":", 1)[0]


def _period(event: RawFactOccurrence) -> dict[str, str]:
    ctx = event.context
    if ctx.instant is not None:
        return {"kind": "instant", "end": ctx.instant.isoformat()}
    return {
        "kind": "duration",
        "start": ctx.start.isoformat() if ctx.start else "",
        "end": ctx.end.isoformat() if ctx.end else "",
    }


def _period_token(event: RawFactOccurrence) -> tuple[str, ...]:
    ctx = event.context
    if ctx.instant is not None:
        return ("instant", ctx.instant.isoformat())
    return (
        "duration",
        ctx.start.isoformat() if ctx.start else "",
        ctx.end.isoformat() if ctx.end else "",
    )


def _unit_payload(event: RawFactOccurrence) -> dict[str, Any] | None:
    if event.unit is None:
        return None
    return event.unit.to_dict()


def _decimal_text(value: Decimal | str | int | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _occurrence_payload(event: RawFactOccurrence) -> dict[str, Any]:
    return {
        "occurrence_id": event.occurrence_id,
        "logical_key": event.logical_key,
        "duplicate_group_key": event.duplicate_group_key,
        "accession": event.source.accession,
        "document_id": event.source.document_id,
        "body_sha256": event.source.body_sha256,
        "parser_fact_id": event.source_occurrence_key,
        "source_span": list(event.source_span) if event.source_span is not None else None,
        "concept_qname": event.concept_qname,
        "taxonomy": _taxonomy(event.concept_qname),
        "context_id": event.context.context_id,
        "context_semantic_key": event.context.semantic_key,
        "period": _period(event),
        "explicit_dimensions": [list(pair) for pair in event.context.explicit_dimensions],
        "typed_dimensions": [list(pair) for pair in event.context.typed_dimensions],
        "dimensions_known": event.dimensions_known,
        "unit": _unit_payload(event),
        "xml_lang": event.xml_lang,
        "is_nil": event.is_nil,
        "parsed_value": _decimal_text(event.parsed_value),
        "raw_token": event.raw_token,
        "decimals": event.decimals,
        "precision": event.precision,
        "event_type": event.event_type.value,
        "revision_of": event.revision_of,
        "accepted_at": utc_text(event.accepted_at),
        "recorded_at": utc_text(event.recorded_at),
        "source_ready_at": utc_text(event.clocks.source_ready_at),
        "system_ready_at": utc_text(event.clocks.system_ready_at),
    }


def _side_state(events: Sequence[RawFactOccurrence]) -> dict[str, Any]:
    groups: dict[str, list[RawFactOccurrence]] = {}
    for event in events:
        groups.setdefault(event.duplicate_group_key, []).append(event)
    ambiguous = False
    representatives: list[RawFactOccurrence] = []
    for key in sorted(groups):
        group = tuple(groups[key])
        if not _duplicates_agree(group):
            ambiguous = True
        representatives.append(_canonical_duplicate_representative(group))
    if len(representatives) > 1 and not _duplicates_agree(representatives):
        ambiguous = True
    return {
        "groups": groups,
        "representatives": representatives,
        "ambiguous": ambiguous,
        "multiple_groups": len(groups) > 1,
        "occurrence_count": len(events),
    }


def _exact_numeric_equality(left: RawFactOccurrence, right: RawFactOccurrence) -> bool:
    if left.is_nil != right.is_nil:
        return False
    if left.is_nil:
        return True
    if left.parsed_value is None or right.parsed_value is None:
        return False
    if Decimal(left.parsed_value) != Decimal(right.parsed_value):
        return False
    return left.decimals == right.decimals and left.precision == right.precision


def _classify_overlap(
    a1_events: Sequence[RawFactOccurrence],
    a2_events: Sequence[RawFactOccurrence],
) -> tuple[str, str]:
    sample = a1_events[0]
    a1 = _side_state(a1_events)
    a2 = _side_state(a2_events)
    all_events = [*a1_events, *a2_events]
    if any(not item.dimensions_known for item in all_events):
        return "incomplete_dimensional_scope", "at least one overlapping occurrence has dimensions_known=false"
    if _taxonomy(sample.concept_qname) not in CORE_TAXONOMIES:
        return "custom_unmapped_taxonomy", "overlapping concept is outside us-gaap/dei"
    if a1["ambiguous"] or a2["ambiguous"]:
        return "ambiguous_duplicate_group", "within-filing duplicate group fails existing _duplicates_agree"
    if a1["multiple_groups"] or a2["multiple_groups"]:
        return "multiple_possible_parent", "more than one duplicate_group_key remains on a side after collapse"
    a1_rep: RawFactOccurrence = a1["representatives"][0]
    a2_rep: RawFactOccurrence = a2["representatives"][0]
    if a1_rep.concept_qname != a2_rep.concept_qname or a1_rep.context.semantic_key != a2_rep.context.semantic_key:
        return "unit_context_concept_mismatch", "logical_key collision with divergent concept or context"
    if (a1_rep.unit.semantic_key if a1_rep.unit else None) != (a2_rep.unit.semantic_key if a2_rep.unit else None):
        return "unit_context_concept_mismatch", "logical_key collision with divergent unit"
    if a1_rep.is_nil != a2_rep.is_nil or (a1_rep.parsed_value is None) != (a2_rep.parsed_value is None):
        return "nil_state_difference", "nil/numeric state differs across filings"
    if not _duplicates_agree((a1_rep, a2_rep)):
        return "changed_value", "A1 and A2 representatives fail existing duplicate-consistency law"
    if not _exact_numeric_equality(a1_rep, a2_rep):
        return (
            "precision_different_value_consistent",
            "representatives agree under _duplicates_agree but parsed_value or decimals/precision tokens differ",
        )
    return (
        "exact_complete_confirmation_candidate",
        "same filer family, same logical_key, complete dimensions, unique parent/child, exact numeric equality at declared accuracy",
    )


def _compact_overlap(
    *,
    class_name: str,
    reason: str,
    a1_events: Sequence[RawFactOccurrence],
    a2_events: Sequence[RawFactOccurrence],
    mapped: Mapping[str, tuple[str, ...]],
) -> dict[str, Any]:
    sample = a1_events[0]
    a1_rep = _canonical_duplicate_representative(a1_events)
    a2_rep = _canonical_duplicate_representative(a2_events)
    empty_dimensions = (
        not sample.context.explicit_dimensions and not sample.context.typed_dimensions
    )
    return {
        "class": class_name,
        "reason": reason,
        "logical_key": sample.logical_key,
        "concept_qname": sample.concept_qname,
        "taxonomy": _taxonomy(sample.concept_qname),
        "empty_dimensions": empty_dimensions,
        "period": _period(sample),
        "unit_semantic_key": sample.unit.semantic_key if sample.unit else None,
        "mapped_metric_ids": list(mapped.get(sample.concept_qname, ())),
        "a1_occurrence_ids": sorted(item.occurrence_id for item in a1_events),
        "a2_occurrence_ids": sorted(item.occurrence_id for item in a2_events),
        "a1_parser_fact_ids": sorted(item.source_occurrence_key or "" for item in a1_events),
        "a2_parser_fact_ids": sorted(item.source_occurrence_key or "" for item in a2_events),
        "a1_parsed_value": _decimal_text(a1_rep.parsed_value),
        "a2_parsed_value": _decimal_text(a2_rep.parsed_value),
        "a1_decimals": a1_rep.decimals,
        "a2_decimals": a2_rep.decimals,
        "a1_precision": a1_rep.precision,
        "a2_precision": a2_rep.precision,
        "a1_is_nil": a1_rep.is_nil,
        "a2_is_nil": a2_rep.is_nil,
        "a1_document_id": a1_rep.source.document_id,
        "a2_document_id": a2_rep.source.document_id,
    }


def _representative_pack(
    a1_events: Sequence[RawFactOccurrence],
    a2_events: Sequence[RawFactOccurrence],
) -> dict[str, Any]:
    return {
        "a1": [_occurrence_payload(item) for item in sorted(a1_events, key=lambda item: item.occurrence_id)],
        "a2": [_occurrence_payload(item) for item in sorted(a2_events, key=lambda item: item.occurrence_id)],
    }


def _concept_map(repo_root: Path, recorded_at: datetime) -> dict[str, tuple[str, ...]]:
    bundle = load_core_registry(repo_root).governance_bundle_at(recorded_at)
    mapping: dict[str, list[str]] = {}
    for contract in bundle.contracts:
        for rule in contract.mappings:
            for alias in rule.taxonomy_concept_aliases:
                mapping.setdefault(f"{alias.taxonomy}:{alias.concept}", []).append(contract.metric_id)
    return {key: tuple(values) for key, values in mapping.items()}


def _weak_mismatch_class(
    a1: RawFactOccurrence,
    a2: RawFactOccurrence,
) -> str | None:
    if a1.concept_qname != a2.concept_qname:
        return "concept"
    same_period = _period_token(a1) == _period_token(a2)
    if not same_period:
        return None
    same_unit = (a1.unit.semantic_key if a1.unit else None) == (a2.unit.semantic_key if a2.unit else None)
    same_context = a1.context.semantic_key == a2.context.semantic_key
    if not same_unit and same_context:
        return "unit"
    if same_unit and not same_context:
        return "context"
    if not same_unit and not same_context:
        return "unit_and_context"
    return None


def main() -> int:
    packages = [load_golden_aapl_package(ROOT, accession=item) for item in GOLDEN_AAPL_QUERY_ACCESSIONS]
    ledger, metadata, report = parse_and_convert_golden_packages(packages)
    if report.ledger_sha256 != EXPECTED_LEDGER_SHA:
        raise SystemExit(f"A3 ledger SHA drifted: {report.ledger_sha256}")
    recorded_at = max(event.recorded_at for event in ledger.events)
    mapped = _concept_map(ROOT, recorded_at)

    by_accession: dict[str, list[RawFactOccurrence]] = {A1: [], A2: []}
    for event in ledger.events:
        by_accession[event.source.accession].append(event)
    a1_by_key: dict[str, list[RawFactOccurrence]] = defaultdict(list)
    a2_by_key: dict[str, list[RawFactOccurrence]] = defaultdict(list)
    for event in by_accession[A1]:
        a1_by_key[event.logical_key].append(event)
    for event in by_accession[A2]:
        a2_by_key[event.logical_key].append(event)

    overlap_keys = sorted(set(a1_by_key) & set(a2_by_key))
    a1_only = sorted(set(a1_by_key) - set(a2_by_key))
    a2_only = sorted(set(a2_by_key) - set(a1_by_key))

    class_counts: Counter[str] = Counter()
    compact_by_class: dict[str, list[dict[str, Any]]] = {name: [] for name in CLASS_ORDER}
    representatives: dict[str, list[dict[str, Any]]] = {name: [] for name in CLASS_ORDER}
    control_assets = None

    for key in overlap_keys:
        a1_events = tuple(a1_by_key[key])
        a2_events = tuple(a2_by_key[key])
        class_name, reason = _classify_overlap(a1_events, a2_events)
        class_counts[class_name] += 1
        row = _compact_overlap(
            class_name=class_name,
            reason=reason,
            a1_events=a1_events,
            a2_events=a2_events,
            mapped=mapped,
        )
        compact_by_class[class_name].append(row)
        sample = a1_events[0]
        if (
            sample.concept_qname == "us-gaap:Assets"
            and sample.context.instant is not None
            and sample.context.instant.isoformat() == "2025-09-27"
            and not sample.context.explicit_dimensions
            and not sample.context.typed_dimensions
        ):
            control_assets = {
                "class": class_name,
                "reason": reason,
                **_representative_pack(a1_events, a2_events),
            }

    for class_name, rows in compact_by_class.items():
        rows.sort(key=lambda item: (item["concept_qname"], json.dumps(item["period"], sort_keys=True), item["logical_key"]))
        chosen = rows[:3]
        if class_name == "exact_complete_confirmation_candidate":
            for row in rows:
                if row["concept_qname"] == "us-gaap:Assets" and row["period"].get("end") == "2025-09-27":
                    if row not in chosen:
                        chosen.append(row)
                    break
        for row in chosen:
            representatives[class_name].append(
                {
                    "compact": row,
                    "occurrences": _representative_pack(a1_by_key[row["logical_key"]], a2_by_key[row["logical_key"]]),
                }
            )

    mismatch_counts: Counter[str] = Counter()
    a1_index: dict[tuple[str, tuple[str, ...]], list[RawFactOccurrence]] = defaultdict(list)
    for event in by_accession[A1]:
        a1_index[(event.concept_qname, _period_token(event))].append(event)
    for event in by_accession[A2]:
        peers = a1_index.get((event.concept_qname, _period_token(event))) or ()
        if not peers:
            continue
        if event.logical_key in a1_by_key:
            continue
        kinds = {item for peer in peers if (item := _weak_mismatch_class(peer, event))}
        if not kinds:
            continue
        if "unit" in kinds and "context" in kinds:
            mismatch_counts["unit_and_context"] += 1
        elif "unit" in kinds:
            mismatch_counts["unit"] += 1
        elif "context" in kinds:
            mismatch_counts["context"] += 1
        elif "concept" in kinds:
            mismatch_counts["concept"] += 1

    class_counts["unit_context_concept_mismatch"] = 0
    class_counts["no_relation"] = len(a1_only) + len(a2_only)

    exact_rows = compact_by_class["exact_complete_confirmation_candidate"]
    mapped_confirmation = [row for row in exact_rows if row["mapped_metric_ids"]]
    empty_exact = [row for row in exact_rows if row["empty_dimensions"]]
    query_relevant = [
        row
        for row in empty_exact
        if row["mapped_metric_ids"] and not row["a1_is_nil"] and not row["a2_is_nil"]
    ]
    confirmation_metric_counts: Counter[str] = Counter()
    for row in mapped_confirmation:
        for metric_id in row["mapped_metric_ids"]:
            confirmation_metric_counts[metric_id] += 1

    receipt = {
        "schema": "fif3a4r.aapl_overlap_census/v1",
        "research_only": True,
        "not_a_runtime_provider": True,
        "base_main": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "a1_accession": A1,
        "a2_accession": A2,
        "ledger_sha256": report.ledger_sha256,
        "a1_document_id": metadata[A1].document_id,
        "a2_document_id": metadata[A2].document_id,
        "a1_occurrence_count": len(by_accession[A1]),
        "a2_occurrence_count": len(by_accession[A2]),
        "logical_key_counts": {
            "a1": len(a1_by_key),
            "a2": len(a2_by_key),
            "overlap": len(overlap_keys),
            "a1_only": len(a1_only),
            "a2_only": len(a2_only),
        },
        "class_counts": {name: int(class_counts.get(name, 0)) for name in CLASS_ORDER},
        "weak_non_logical_mismatch_fact_counts": dict(sorted(mismatch_counts.items())),
        "core_mapped_exact_confirmation_count": len(mapped_confirmation),
        "core_mapped_exact_confirmation_by_metric": dict(sorted(confirmation_metric_counts.items())),
        "exact_confirmation_empty_dimension_count": len(empty_exact),
        "exact_confirmation_dimensioned_count": len(exact_rows) - len(empty_exact),
        "query_relevant_consolidated_mapped_exact_count": len(query_relevant),
        "query_relevant_consolidated_mapped_exact": query_relevant,
        "duration_overlap_count": sum(
            1 for key in overlap_keys if a1_by_key[key][0].context.instant is None
        ),
        "control_total_assets_instant_2025_09_27": control_assets,
        "source_namespace_families": list(report.source_namespace_families),
        "conversion_receipts": [item.to_dict() if hasattr(item, "to_dict") else {
            "accession": item.accession,
            "parser_numeric_fact_count": item.parser_numeric_fact_count,
            "ledger_occurrence_count": item.ledger_occurrence_count,
            "represented_count": item.represented_count,
            "excluded": dict(item.excluded),
            "source_namespace_families": list(item.source_namespace_families),
        } for item in report.filings],
        "representatives": representatives,
        "overlap_rows": {name: compact_by_class[name] for name in CLASS_ORDER if name not in {"no_relation", "unit_context_concept_mismatch"}},
        "no_relation_counts_only": True,
        "classification_law": {
            "overlap_identity": "RawFactOccurrence.logical_key",
            "duplicate_consistency": "engine.fundamental_forensics.raw_ledger._duplicates_agree",
            "v1_confirmation": "exact parsed_value and identical decimals/precision tokens; complete dimensions_known; unique parent/child; us-gaap or dei",
            "precision_class": "reuses _duplicates_agree; does not invent a second tolerance",
            "default_relation": "NO_RELATION",
        },
    }
    encoded = canonical_json(receipt)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    receipt["census_sha256"] = digest
    encoded = canonical_json(receipt)
    out = Path(__file__).with_name("FIF_3A4R_AAPL_OVERLAP_CENSUS.json")
    out.write_text(encoded + "\n", encoding="utf-8")
    print(json.dumps({
        "ledger_sha256": report.ledger_sha256,
        "census_path": str(out.relative_to(ROOT)),
        "census_payload_sha256": digest,
        "census_file_sha256": hashlib.sha256((encoded + "\n").encode("utf-8")).hexdigest(),
        "class_counts": receipt["class_counts"],
        "logical_key_counts": receipt["logical_key_counts"],
        "core_mapped_exact_confirmation_count": receipt["core_mapped_exact_confirmation_count"],
        "query_relevant_consolidated_mapped_exact_count": receipt["query_relevant_consolidated_mapped_exact_count"],
        "exact_confirmation_empty_dimension_count": receipt["exact_confirmation_empty_dimension_count"],
        "control_class": None if control_assets is None else control_assets["class"],
        "weak_non_logical_mismatch_fact_counts": receipt["weak_non_logical_mismatch_fact_counts"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
