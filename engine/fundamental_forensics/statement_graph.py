"""FIF-3A1 filing-native statement graph.

Walks presentation/calculation/label linkbases and joins them to the strict
offline iXBRL parse. Deterministic. No network. No implicit now. No LLM.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree as ET

from collectors.sec_filing_parser import parse_sec_filing_document

LINK = "http://www.xbrl.org/2003/linkbase"
XLINK = "http://www.w3.org/1999/xlink"
XML = "http://www.w3.org/XML/1998/namespace"

LABEL_STANDARD = "http://www.xbrl.org/2003/role/label"
LABEL_TERSE = "http://www.xbrl.org/2003/role/terseLabel"
LABEL_PERIOD_START = "http://www.xbrl.org/2003/role/periodStartLabel"
LABEL_PERIOD_END = "http://www.xbrl.org/2003/role/periodEndLabel"

PRIMARY_STATEMENT_ROLES: dict[str, str] = {
    "income_statement": "http://www.apple.com/role/CONSOLIDATEDSTATEMENTSOFOPERATIONS",
    "balance_sheet": "http://www.apple.com/role/CONSOLIDATEDBALANCESHEETS",
    "cash_flow": "http://www.apple.com/role/CONSOLIDATEDSTATEMENTSOFCASHFLOWS",
}

STATEMENT_TITLES: dict[str, str] = {
    "income_statement": "CONSOLIDATED STATEMENTS OF OPERATIONS",
    "balance_sheet": "CONSOLIDATED BALANCE SHEETS",
    "cash_flow": "CONSOLIDATED STATEMENTS OF CASH FLOWS",
}

_ABSTRACT_TOKENS = (
    "Abstract",
    "Axis",
    "Domain",
    "Member",
    "Table",
    "LineItems",
)

_PREFIXES = (
    "us-gaap_",
    "srt_",
    "dei_",
    "ecd_",
    "country_",
    "apple_",
    "aapl_",
    "iso4217_",
)

_MAX_LINKBASE_BYTES = 8 * 1024 * 1024
_MAX_ARCS = 20_000
_FORBIDDEN_DECL = b"<!DOCTYPE", b"<!ENTITY"


class StatementGraphError(ValueError):
    """The filing package cannot yield an as-reported statement tree."""


@dataclass(frozen=True)
class GoldenFilingPackage:
    """Pinned AAPL 10-K members plus the complete archive inventory."""

    manifest: dict[str, Any]
    members: dict[str, bytes]


def load_golden_aapl_package(repo_root: Path) -> GoldenFilingPackage:
    """Load the committed FIF-3A1 fixture. Performs no network I/O."""
    fixture = Path(repo_root) / "tests" / "fixtures" / "fundamental_forensics" / "aapl_10k_2025"
    manifest_path = fixture / "package_manifest.json"
    if not manifest_path.is_file():
        raise StatementGraphError("golden AAPL package manifest is missing")
    raw = manifest_path.read_bytes()
    if _FORBIDDEN_DECL[0] in raw:
        raise StatementGraphError("golden AAPL package manifest is malformed")
    import json

    manifest = json.loads(raw.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise StatementGraphError("golden AAPL package manifest is malformed")
    members: dict[str, bytes] = {}
    for item in manifest.get("members", []):
        if not isinstance(item, dict) or item.get("state") != "stored":
            continue
        name = item.get("name")
        rel = item.get("path")
        if not isinstance(name, str) or not isinstance(rel, str):
            raise StatementGraphError("golden AAPL stored member is malformed")
        payload = (fixture / rel).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != item.get("content_sha256") or len(payload) != item.get("byte_length"):
            raise StatementGraphError(f"golden AAPL member digest mismatch: {name}")
        members[name] = payload
    if manifest.get("primary_document") not in members:
        raise StatementGraphError("golden AAPL primary document is not retained")
    return GoldenFilingPackage(manifest=manifest, members=members)


def _parse_xml(content: bytes, *, name: str) -> ET.Element:
    if not content or len(content) > _MAX_LINKBASE_BYTES:
        raise StatementGraphError(f"{name} exceeds linkbase bound")
    if b"\x00" in content:
        raise StatementGraphError(f"{name} contains NUL")
    upper = content.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise StatementGraphError(f"{name} declares a DTD or entity")
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise StatementGraphError(f"{name} is not well-formed XML") from exc


def _xlink(el: ET.Element, attr: str) -> str | None:
    return el.get(f"{{{XLINK}}}{attr}")


def concept_from_href(href: str) -> str:
    frag = href.rsplit("#", 1)[-1]
    for prefix in _PREFIXES:
        if frag.startswith(prefix):
            return f"{prefix[:-1]}:{frag[len(prefix):]}"
    if "_" in frag:
        head, rest = frag.split("_", 1)
        return f"{head}:{rest}"
    return frag


def _local_name(concept: str) -> str:
    if ":" in concept:
        return concept.split(":", 1)[1]
    if concept.startswith("{") and "}" in concept:
        return concept.split("}", 1)[1]
    return concept


def fact_matches_concept(concept_qname: str, concept: str) -> bool:
    local = _local_name(concept)
    if not concept_qname.endswith("}" + local) and concept_qname != local:
        return False
    prefix = concept.split(":", 1)[0] if ":" in concept else ""
    if not prefix:
        return True
    return prefix in concept_qname


def _is_abstract_concept(concept: str) -> bool:
    local = _local_name(concept)
    return any(token in local for token in _ABSTRACT_TOKENS)


def _parse_date(value: str | None) -> date | None:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _day_before(value: date) -> date:
    return value - timedelta(days=1)


def parse_presentation_tree(content: bytes, *, role_uri: str) -> list[dict[str, Any]]:
    root = _parse_xml(content, name="presentation linkbase")
    link = None
    for el in root.iter(f"{{{LINK}}}presentationLink"):
        if _xlink(el, "role") == role_uri:
            link = el
            break
    if link is None:
        raise StatementGraphError(f"presentation role is absent: {role_uri}")
    locs: dict[str, str] = {}
    for loc in link.findall(f"{{{LINK}}}loc"):
        label = _xlink(loc, "label")
        href = _xlink(loc, "href")
        if label and href:
            locs[label] = href
    children: dict[str, list[tuple[float, str, str | None, str | None]]] = {}
    parents: set[str] = set()
    targets: set[str] = set()
    arcs = list(link.findall(f"{{{LINK}}}presentationArc"))
    if len(arcs) > _MAX_ARCS:
        raise StatementGraphError("presentation arc limit exceeded")
    for arc in arcs:
        if arc.get("use") == "prohibited":
            continue
        frm = _xlink(arc, "from")
        to = _xlink(arc, "to")
        if not frm or not to:
            continue
        order_raw = arc.get("order") or "0"
        try:
            order = float(order_raw)
        except ValueError:
            order = 0.0
        children.setdefault(frm, []).append((order, to, arc.get("preferredLabel"), order_raw))
        parents.add(frm)
        targets.add(to)
    roots = sorted(p for p in parents if p not in targets)
    if len(roots) != 1:
        raise StatementGraphError(f"presentation role does not have a unique root: {role_uri}")
    rows: list[dict[str, Any]] = []

    def walk(label: str, depth: int, path: tuple[str, ...], preferred: str | None) -> None:
        href = locs.get(label)
        if href is None:
            raise StatementGraphError("presentation locator is missing")
        concept = concept_from_href(href)
        rows.append(
            {
                "order": len(rows),
                "depth": depth,
                "concept": concept,
                "href": href,
                "preferred_label_role": preferred,
                "presentation_path": list(path + (concept,)),
                "abstract": _is_abstract_concept(concept),
            }
        )
        kids = sorted(children.get(label, []), key=lambda item: (item[0], item[1]))
        for _order, child, pref, _raw in kids:
            walk(child, depth + 1, path + (concept,), pref)

    walk(roots[0], 0, (), None)
    return rows


def parse_labels(content: bytes) -> dict[tuple[str, str], str]:
    root = _parse_xml(content, name="label linkbase")
    out: dict[tuple[str, str], str] = {}
    for link in root.iter(f"{{{LINK}}}labelLink"):
        locs: dict[str, str] = {}
        resources: dict[str, list[tuple[str, str]]] = {}
        for loc in link.iter(f"{{{LINK}}}loc"):
            label = _xlink(loc, "label")
            href = _xlink(loc, "href")
            if label and href:
                locs[label] = concept_from_href(href)
        for lab in link.iter(f"{{{LINK}}}label"):
            key = _xlink(lab, "label")
            role = _xlink(lab, "role") or LABEL_STANDARD
            text = "".join(lab.itertext()).strip()
            if key and text:
                resources.setdefault(key, []).append((role, text))
        for arc in link.iter(f"{{{LINK}}}labelArc"):
            if arc.get("use") == "prohibited":
                continue
            frm = _xlink(arc, "from")
            to = _xlink(arc, "to")
            if frm not in locs or to not in resources:
                continue
            for role, text in resources[to]:
                out[(locs[frm], role)] = text
    return out


def parse_calculations(content: bytes) -> dict[str, tuple[tuple[str, str], ...]]:
    """Map parent concept -> ((child_concept, weight), ...) from calc arcs."""
    root = _parse_xml(content, name="calculation linkbase")
    by_parent: dict[str, list[tuple[str, str]]] = {}
    for link in root.iter(f"{{{LINK}}}calculationLink"):
        locs: dict[str, str] = {}
        for loc in link.findall(f"{{{LINK}}}loc"):
            label = _xlink(loc, "label")
            href = _xlink(loc, "href")
            if label and href:
                locs[label] = concept_from_href(href)
        for arc in link.findall(f"{{{LINK}}}calculationArc"):
            if arc.get("use") == "prohibited":
                continue
            frm = _xlink(arc, "from")
            to = _xlink(arc, "to")
            if frm not in locs or to not in locs:
                continue
            weight = arc.get("weight") or "1"
            by_parent.setdefault(locs[frm], []).append((locs[to], weight))
    frozen = {parent: tuple(children) for parent, children in by_parent.items()}
    return frozen


def resolve_label(labels: Mapping[tuple[str, str], str], concept: str, preferred: str | None) -> tuple[str, str]:
    for role in (preferred, LABEL_TERSE, LABEL_STANDARD):
        if role and (concept, role) in labels:
            return labels[(concept, role)], role
    return _local_name(concept), "concept_local_name"


def _undimensioned(context: Mapping[str, Any]) -> bool:
    dims = context.get("dimensions") or []
    return isinstance(dims, list) and len(dims) == 0


def _unit_label(units: Mapping[str, Any], unit_ref: str | None) -> str | None:
    if not unit_ref or unit_ref not in units:
        return None
    unit = units[unit_ref]
    nums = [m.rsplit("}", 1)[-1] for m in unit.get("numerator_measures") or []]
    dens = [m.rsplit("}", 1)[-1] for m in unit.get("denominator_measures") or []]
    if nums and dens:
        return f"{nums[0]}/{'*'.join(dens)}"
    if nums:
        return nums[0]
    return unit_ref


def _period_key(context: Mapping[str, Any]) -> tuple[str, str | None, str | None]:
    period = context.get("period") or {}
    kind = str(period.get("kind") or "")
    if kind == "instant":
        return ("instant", None, period.get("instant_date"))
    return ("duration", period.get("start_date"), period.get("end_date"))


def _discover_columns(
    *,
    statement_type: str,
    rows: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    contexts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    line_concepts = {row["concept"] for row in rows if not row["abstract"]}
    seen: dict[tuple[str, str | None, str | None], dict[str, Any]] = {}
    support: dict[tuple[str, str | None, str | None], set[str]] = {}
    for fact in facts:
        context = contexts.get(fact.get("context_ref") or "")
        if context is None or not _undimensioned(context):
            continue
        matched = [c for c in line_concepts if fact_matches_concept(str(fact.get("concept_qname") or ""), c)]
        if not matched:
            continue
        key = _period_key(context)
        if statement_type == "balance_sheet":
            if key[0] != "instant" or not key[2]:
                continue
            seen[key] = {
                "kind": "instant",
                "start": None,
                "end": key[2],
                "label": key[2],
            }
        else:
            if key[0] != "duration" or not key[1] or not key[2]:
                continue
            seen[key] = {
                "kind": "duration",
                "start": key[1],
                "end": key[2],
                "label": key[2],
            }
        support.setdefault(key, set()).update(matched)
    floor = 5
    columns = [col for key, col in seen.items() if len(support.get(key, ())) >= floor]
    columns.sort(key=lambda col: col["end"] or "", reverse=True)
    limit = 2 if statement_type == "balance_sheet" else 3
    return columns[:limit]


def _values_agree(left: str, right: str) -> bool:
    if left == right:
        return True
    try:
        return Decimal(left) == Decimal(right)
    except (InvalidOperation, ValueError):
        return False


def _select_facts(
    *,
    concept: str,
    column: Mapping[str, Any],
    preferred: str | None,
    facts: list[dict[str, Any]],
    contexts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    start = _parse_date(column.get("start"))
    end = _parse_date(column.get("end"))
    for fact in facts:
        if not fact_matches_concept(str(fact.get("concept_qname") or ""), concept):
            continue
        context = contexts.get(fact.get("context_ref") or "")
        if context is None or not _undimensioned(context):
            continue
        period = context.get("period") or {}
        kind = period.get("kind")
        if preferred == LABEL_PERIOD_START:
            instant = _parse_date(period.get("instant_date"))
            if kind != "instant" or start is None or instant is None:
                continue
            if instant not in {start, _day_before(start)}:
                continue
        elif preferred == LABEL_PERIOD_END or column.get("kind") == "instant":
            instant = _parse_date(period.get("instant_date"))
            if kind != "instant" or end is None or instant != end:
                continue
        else:
            if kind != "duration":
                continue
            if period.get("start_date") != column.get("start") or period.get("end_date") != column.get("end"):
                continue
        matched.append(fact)
    return matched


def _empty_cell(*, column: Mapping[str, Any], quality_state: str) -> dict[str, Any]:
    return {
        "period": dict(column),
        "value": None,
        "unit": None,
        "scale": None,
        "decimals": None,
        "dimensions": [],
        "direct_or_calculated": None,
        "quality_state": quality_state,
        "source_receipt": None,
    }


def _cell_from_facts(
    *,
    facts: list[dict[str, Any]],
    column: Mapping[str, Any],
    units: dict[str, Any],
    document_name: str,
    content_sha256: str,
    abstract: bool,
) -> dict[str, Any]:
    if abstract:
        return _empty_cell(column=column, quality_state="abstract")
    if not facts:
        return _empty_cell(column=column, quality_state="missing_fact")
    values = [f.get("normalized_value") for f in facts]
    comparable = [("" if v is None else str(v)) for v in values]
    representative = min(
        facts,
        key=lambda f: ((f.get("source_span") or {}).get("start", 0), str(f.get("fact_id") or "")),
    )
    disagree = any(
        not _values_agree(comparable[0], item) if comparable[0] != "" or item != "" else False
        for item in comparable[1:]
    )
    mixed_nil = any(bool(f.get("nil")) for f in facts) and not all(bool(f.get("nil")) for f in facts)
    mixed_presence = any(v is None for v in values) and any(v is not None for v in values)
    if disagree or mixed_nil or mixed_presence:
        return {
            "period": dict(column),
            "value": None,
            "unit": None,
            "scale": None,
            "decimals": None,
            "dimensions": [],
            "direct_or_calculated": None,
            "quality_state": "ambiguous",
            "source_receipt": {
                "document_name": document_name,
                "content_sha256": content_sha256,
                "occurrence_count": len(facts),
                "competing_fact_ids": sorted(str(f.get("fact_id")) for f in facts),
                "competing_values": comparable,
            },
        }
    if representative.get("nil") or representative.get("normalized_value") is None:
        cell = _empty_cell(column=column, quality_state="nil")
        cell["source_receipt"] = {
            "document_name": document_name,
            "content_sha256": content_sha256,
            "fact_id": representative.get("fact_id"),
            "concept_qname": representative.get("concept_qname"),
            "context_ref": representative.get("context_ref"),
            "unit_ref": representative.get("unit_ref"),
            "source_span": representative.get("source_span"),
            "occurrence_count": len(facts),
        }
        return cell
    span = representative.get("source_span")
    return {
        "period": dict(column),
        "value": representative.get("normalized_value"),
        "unit": _unit_label(units, representative.get("unit_ref")),
        "scale": representative.get("scale"),
        "decimals": representative.get("decimals"),
        "dimensions": [],
        "direct_or_calculated": "direct",
        "quality_state": "available",
        "source_receipt": {
            "document_name": document_name,
            "content_sha256": content_sha256,
            "fact_id": representative.get("fact_id"),
            "concept_qname": representative.get("concept_qname"),
            "context_ref": representative.get("context_ref"),
            "unit_ref": representative.get("unit_ref"),
            "source_span": span,
            "occurrence_count": len(facts),
        },
    }


def map_standardized_metric(concept: str, registry: Any) -> dict[str, Any]:
    local = _local_name(concept)
    prefix = concept.split(":", 1)[0] if ":" in concept else ""
    hits: list[str] = []
    contracts = getattr(registry, "contracts", None)
    if contracts is None:
        return {"metric_id": None, "mapping_state": "unmapped", "mapping_receipt": None}
    iterable = contracts.values() if isinstance(contracts, dict) else contracts
    for contract in iterable:
        for alias in getattr(contract, "taxonomy_concept_aliases", ()):
            if alias.concept == local and alias.taxonomy == prefix:
                hits.append(contract.metric_id)
    unique = sorted(set(hits))
    if len(unique) == 1:
        return {
            "metric_id": unique[0],
            "mapping_state": "mapped",
            "mapping_receipt": {
                "taxonomy": prefix,
                "concept": local,
                "metric_id": unique[0],
            },
        }
    if len(unique) > 1:
        return {
            "metric_id": None,
            "mapping_state": "ambiguous_mapping",
            "mapping_receipt": {"taxonomy": prefix, "concept": local, "metric_ids": unique},
        }
    return {"metric_id": None, "mapping_state": "unmapped", "mapping_receipt": None}


def reconstruct_statement(
    *,
    statement_type: str,
    package: GoldenFilingPackage,
    parsed_instance: Mapping[str, Any],
    registry: Any,
) -> dict[str, Any]:
    role_uri = PRIMARY_STATEMENT_ROLES[statement_type]
    pre = package.members["aapl-20250927_pre.xml"]
    lab = package.members["aapl-20250927_lab.xml"]
    cal = package.members["aapl-20250927_cal.xml"]
    rows_spec = parse_presentation_tree(pre, role_uri=role_uri)
    labels = parse_labels(lab)
    calcs = parse_calculations(cal)
    facts = list(parsed_instance.get("facts") or [])
    contexts = {c["context_id"]: c for c in parsed_instance.get("contexts") or []}
    units = {u["unit_id"]: u for u in parsed_instance.get("units") or []}
    primary = package.manifest["primary_document"]
    primary_sha = next(
        item["content_sha256"]
        for item in package.manifest["members"]
        if item.get("name") == primary and item.get("state") == "stored"
    )
    columns = _discover_columns(
        statement_type=statement_type,
        rows=rows_spec,
        facts=facts,
        contexts=contexts,
    )
    out_rows: list[dict[str, Any]] = []
    for spec in rows_spec:
        label, label_role = resolve_label(labels, spec["concept"], spec["preferred_label_role"])
        mapping = map_standardized_metric(spec["concept"], registry)
        children = calcs.get(spec["concept"])
        formula = None
        calc_status = "direct"
        if children:
            calc_status = "calculated"
            formula = [{"concept": child, "weight": weight} for child, weight in children]
        cells = []
        for column in columns:
            selected = _select_facts(
                concept=spec["concept"],
                column=column,
                preferred=spec["preferred_label_role"],
                facts=facts,
                contexts=contexts,
            )
            cell = _cell_from_facts(
                facts=selected,
                column=column,
                units=units,
                document_name=primary,
                content_sha256=primary_sha,
                abstract=spec["abstract"],
            )
            if not spec["abstract"] and cell["quality_state"] == "available":
                cell["direct_or_calculated"] = calc_status
            cells.append(cell)
        out_rows.append(
            {
                "order": spec["order"],
                "depth": spec["depth"],
                "concept": spec["concept"],
                "abstract": spec["abstract"],
                "as_reported_label": label,
                "preferred_label_role": spec["preferred_label_role"],
                "label_role_used": label_role,
                "presentation_path": spec["presentation_path"],
                "standardized_metric_id": mapping["metric_id"],
                "mapping_state": mapping["mapping_state"],
                "mapping_receipt": mapping["mapping_receipt"],
                "formula_dependencies": formula,
                "cells": cells,
            }
        )
    return {
        "statement_type": statement_type,
        "role_uri": role_uri,
        "title": STATEMENT_TITLES[statement_type],
        "columns": columns,
        "row_count": len(out_rows),
        "rows": out_rows,
    }


def reconstruct_primary_statements(
    *,
    package: GoldenFilingPackage,
    registry: Any,
) -> dict[str, Any]:
    primary = package.manifest["primary_document"]
    parsed = parse_sec_filing_document(package.members[primary], document_name=primary)
    entity_ids = []
    for context in parsed.get("contexts") or []:
        ident = ((context.get("entity") or {}).get("identifier"))
        if ident:
            entity_ids.append(str(ident))
    unique_entities = sorted(set(entity_ids))
    if unique_entities != [package.manifest["cik"]]:
        raise StatementGraphError("XBRL entity identifier is not the source-native AAPL CIK")
    statements = [
        reconstruct_statement(
            statement_type=kind,
            package=package,
            parsed_instance=parsed,
            registry=registry,
        )
        for kind in ("income_statement", "balance_sheet", "cash_flow")
    ]
    return {
        "parsed_document_kind": (parsed.get("document") or {}).get("kind"),
        "fact_count": len(parsed.get("facts") or []),
        "context_count": len(parsed.get("contexts") or []),
        "statements": statements,
    }


__all__ = [
    "GoldenFilingPackage",
    "PRIMARY_STATEMENT_ROLES",
    "STATEMENT_TITLES",
    "StatementGraphError",
    "concept_from_href",
    "fact_matches_concept",
    "load_golden_aapl_package",
    "parse_calculations",
    "parse_labels",
    "parse_presentation_tree",
    "map_standardized_metric",
    "reconstruct_primary_statements",
    "reconstruct_statement",
]
