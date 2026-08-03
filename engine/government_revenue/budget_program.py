"""Projection of receipt-bound DoD budget lines into a display-only evidence graph.

This is intentionally a small graph substrate.  It creates source-native
budget-line -> program-node edges automatically, but program -> award edges
exist only in the reviewed JSON input and have no economic weight.  Issuer
resolution is deliberately outside this module: a later integration must use
the existing time-valid recipient graph rather than a name match.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote, urlsplit

from collectors.dod_budget import (
    ALLOWED_SOURCE_HOSTS,
    DOD_BUDGET_SNAPSHOT_CONTRACT,
    _canonical_json,
    _extraction_semantic_sha256,
    _line_state_sha256,
    _official_https_url,
    _sha256,
    _utc_iso,
    projection_state_matches,
    validate_document_receipt,
)


BUDGET_PROGRAM_GRAPH_CONTRACT = "government_budget_program_graph.v1"
BUDGET_PROGRAM_GRAPH_SCHEMA_VERSION = "1.0.0"
BUDGET_PROGRAM_GRAPH_CONTENT_PREFIX = "grbg1-"
BUDGET_EDGE_CONTRACT = "government_budget_edge.v1"
BUDGET_EDGE_REVIEW_SET_CONTRACT = "government_budget_reviewed_edges.v1"

AUTHORITY: dict[str, Any] = {
    "tier": "display",
    "context_only": True,
    "can_rank": False,
    "can_size": False,
    "can_gate": False,
    "can_originate_signal": False,
    "can_add_candidates": False,
    "can_escalate": False,
}
_REVIEWED_STATES = {"reviewed", "confirmed"}
_AWARD_HOSTS = {"api.usaspending.gov"}


def _root(root: Path | None) -> Path:
    return Path(root).resolve() if root is not None else Path.cwd().resolve()


def _text(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"missing {label}")
    return text


def _slug(value: Any) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", str(value).casefold()).strip("-")
    if not result:
        raise ValueError("graph identifier cannot be normalized")
    return result


def _instant(value: Any, *, label: str) -> str:
    try:
        return _utc_iso(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"missing or invalid {label}") from exc


def _official_award_url(value: Any, *, award_key: str) -> str:
    text = _text(value, label="award source URL")
    parsed = urlsplit(text)
    if not award_key.startswith("generated:"):
        raise ValueError("reviewed budget edge award lacks a source-generated identity")
    generated_award_id = award_key.removeprefix("generated:")
    expected_path = f"/api/v2/awards/{generated_award_id}/"
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.hostname.lower() not in _AWARD_HOSTS
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or unquote(parsed.path) != expected_path
    ):
        raise ValueError("reviewed budget edge award evidence is not the exact official USAspending award URL")
    return text


def _latest_lines(lines: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Choose latest known version per line without rewriting the source ledger."""
    latest: dict[str, tuple[str, int, dict[str, Any]]] = {}
    for index, raw in enumerate(lines):
        row = dict(raw)
        if row.get("contract") != DOD_BUDGET_SNAPSHOT_CONTRACT:
            raise ValueError("budget graph source has invalid line contract")
        key = _text(row.get("line_key"), label="line key")
        known_at = _instant(row.get("known_at"), label="line known_at")
        prior = latest.get(key)
        if prior is None or (known_at, index) >= (prior[0], prior[1]):
            latest[key] = (known_at, index, row)
    return [item[2] for item in sorted(latest.values(), key=lambda value: value[2]["line_key"])]


def _program_from_line(line: Mapping[str, Any]) -> dict[str, Any]:
    native = line.get("native_identifier")
    if not isinstance(native, Mapping):
        raise ValueError("budget line native identifier is malformed")
    kind = _text(native.get("kind"), label="native identifier kind")
    native_value = _text(native.get("value"), label="native identifier value")
    if kind == "p1_line_item":
        program_kind = "procurement_line_item"
    elif kind == "program_element":
        program_kind = "rdte_program_element"
    else:
        raise ValueError("budget line native identifier kind is unsupported")
    program_key = ":".join((
        "dod-program", program_kind, _slug(line.get("component")),
        _slug(line.get("appropriation_code")), _slug(native_value),
    ))
    return {
        "program_key": program_key,
        "kind": program_kind,
        "native_identifier": native_value,
        "name": _text(line.get("program_name"), label="program name"),
        "line_keys": [_text(line.get("line_key"), label="line key")],
    }


def _line_program_edge(line: Mapping[str, Any], program: Mapping[str, Any]) -> dict[str, Any]:
    source = line.get("source")
    provenance = line.get("provenance")
    if not isinstance(source, Mapping) or not isinstance(provenance, Mapping):
        raise ValueError("budget line source provenance is malformed")
    fingerprint = {
        "from": line["line_key"],
        "to": program["program_key"],
        "source": source["document_sha256"],
    }
    return {
        "contract": BUDGET_EDGE_CONTRACT,
        "edge_id": "budget-edge:" + hashlib.sha256(_canonical_json(fingerprint).encode("utf-8")).hexdigest()[:24],
        "from_type": "budget_line",
        "from_id": line["line_key"],
        "to_type": "program",
        "to_id": program["program_key"],
        "edge_type": "source_native_identifier",
        "review_state": "official",
        "economic_weight": None,
        "effective_at": line["effective_at"],
        "known_at": line["known_at"],
        "evidence": [{
            "kind": "budget_line",
            "ref_id": line["line_key"],
            "document_sha256": source["document_sha256"],
            "page_number": provenance["page_number"],
            "page_text_sha256": provenance["page_text_sha256"],
            "note": "Exact source-native budget identifier.",
        }],
    }


def _reviewed_edge(
    raw: Mapping[str, Any],
    *,
    lines_by_key: Mapping[str, Mapping[str, Any]],
    program_by_line: Mapping[str, str],
    program_keys: set[str],
    award_keys: set[str],
) -> dict[str, Any]:
    """Materialize one manual program -> award link or reject it entirely."""
    if not isinstance(raw, Mapping):
        raise ValueError("reviewed budget edge is malformed")
    if str(raw.get("from_type") or "") != "program" or str(raw.get("to_type") or "") != "award":
        raise ValueError("reviewed budget edge must link a program to an award")
    from_id = _text(raw.get("from_id"), label="reviewed edge program")
    to_id = _text(raw.get("to_id"), label="reviewed edge award")
    if from_id not in program_keys:
        raise ValueError("reviewed budget edge program is not source-native")
    if not award_keys or to_id not in award_keys:
        raise ValueError("reviewed budget edge award is not present in the exact award set")
    if raw.get("edge_type") != "reviewed_documentary":
        raise ValueError("reviewed budget edge cannot use a derived edge type")
    review_state = str(raw.get("review_state") or "").casefold()
    if review_state not in _REVIEWED_STATES:
        raise ValueError("reviewed budget edge lacks a reviewed state")
    if raw.get("economic_weight") is not None:
        raise ValueError("reviewed budget edge must not assert an economic weight")
    evidence = raw.get("evidence")
    if not isinstance(evidence, list) or len(evidence) < 2:
        raise ValueError("reviewed budget edge requires budget and award evidence")
    budget_evidence = []
    award_evidence = []
    normalized_evidence: list[dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, Mapping):
            raise ValueError("reviewed budget edge evidence is malformed")
        kind = str(item.get("kind") or "")
        ref_id = _text(item.get("ref_id"), label="reviewed edge evidence ref")
        candidate = {"kind": kind, "ref_id": ref_id}
        if kind == "budget_line":
            line = lines_by_key.get(ref_id)
            if line is None:
                raise ValueError("reviewed budget edge evidence does not cite a retained line")
            if program_by_line.get(ref_id) != from_id:
                raise ValueError("reviewed budget edge line evidence does not belong to the source program")
            source = line.get("source")
            provenance = line.get("provenance")
            if not isinstance(source, Mapping) or not isinstance(provenance, Mapping):
                raise ValueError("reviewed budget edge retained line provenance is malformed")
            expected = {
                "document_sha256": source.get("document_sha256"),
                "page_number": provenance.get("page_number"),
                "page_text_sha256": provenance.get("page_text_sha256"),
            }
            for field in ("document_sha256", "page_number", "page_text_sha256"):
                if item.get(field) != expected[field]:
                    raise ValueError("reviewed budget edge budget evidence does not match the retained line")
                candidate[field] = expected[field]
            budget_evidence.append(candidate)
        elif kind == "award":
            if ref_id != to_id:
                raise ValueError("reviewed budget edge award evidence does not match edge target")
            candidate["source_url"] = _official_award_url(item.get("source_url"), award_key=to_id)
            award_evidence.append(candidate)
        else:
            raise ValueError("reviewed budget edge evidence kind is unsupported")
        candidate["note"] = _text(item.get("note"), label="reviewed edge evidence note")
        normalized_evidence.append(candidate)
    if not budget_evidence or not award_evidence:
        raise ValueError("reviewed budget edge needs one budget-line and one award evidence record")
    effective_at = _instant(raw.get("effective_at"), label="reviewed edge effective_at")
    known_at = _instant(raw.get("known_at"), label="reviewed edge known_at")
    fingerprint = {
        "from_id": from_id,
        "to_id": to_id,
        "review_state": review_state,
        "effective_at": effective_at,
        "known_at": known_at,
        "evidence": normalized_evidence,
    }
    expected_id = "budget-edge:" + hashlib.sha256(_canonical_json(fingerprint).encode("utf-8")).hexdigest()[:24]
    supplied_id = raw.get("edge_id")
    if supplied_id not in {None, "", expected_id}:
        raise ValueError("reviewed budget edge identity does not match its evidence")
    return {
        "contract": BUDGET_EDGE_CONTRACT,
        "edge_id": expected_id,
        "from_type": "program",
        "from_id": from_id,
        "to_type": "award",
        "to_id": to_id,
        "edge_type": "reviewed_documentary",
        "review_state": review_state,
        "economic_weight": None,
        "effective_at": effective_at,
        "known_at": known_at,
        "evidence": normalized_evidence,
    }


def load_reviewed_edges(root: Path | None = None) -> dict[str, Any]:
    path = _root(root) / "config" / "government_revenue" / "budget_program_reviewed_edges.v1.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("reviewed budget edge input is unavailable or invalid") from exc
    if (
        not isinstance(value, dict)
        or value.get("contract") != BUDGET_EDGE_REVIEW_SET_CONTRACT
        or value.get("schema_version") != BUDGET_PROGRAM_GRAPH_SCHEMA_VERSION
        or not isinstance(value.get("edges"), list)
    ):
        raise ValueError("reviewed budget edge input contract is invalid")
    return value


def budget_program_graph_content_id(payload: Mapping[str, Any]) -> str | None:
    try:
        fingerprint = {
            key: value
            for key, value in payload.items()
            if key not in {"content_id", "generated_at"}
        }
        return BUDGET_PROGRAM_GRAPH_CONTENT_PREFIX + _sha256(_canonical_json(fingerprint))[:24]
    except (TypeError, ValueError):
        return None


def _document_projection(receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    seen_receipts: set[str] = set()
    for receipt in receipts:
        validate_document_receipt(receipt)
        receipt_id = str(receipt["receipt_id"])
        if receipt_id in seen_receipts:
            raise ValueError("budget graph source receipt bundle has a duplicate receipt")
        seen_receipts.add(receipt_id)
        documents.append({
            "receipt_id": receipt_id,
            "fiscal_year": receipt["fiscal_year"],
            "exhibit": receipt["exhibit"],
            "source_url": receipt["final_url"],
            "content_sha256": receipt["content_sha256"],
            "page_count": receipt["page_count"],
            "page_text_sha256s": list(receipt["page_text_sha256s"]),
            "extraction_semantic_sha256": receipt["extraction_semantic_sha256"],
            "extractor_version": receipt["extractor_version"],
            "parser_version": receipt["parser_version"],
            "observed_at": receipt["observed_at"],
        })
    return sorted(documents, key=lambda row: (row["fiscal_year"], row["exhibit"], row["receipt_id"]))


def build_budget_program_graph(
    *,
    lines: Sequence[Mapping[str, Any]],
    receipts: Sequence[Mapping[str, Any]],
    projection_state: Mapping[str, Any],
    as_of: str,
    reviewed_edge_set: Mapping[str, Any] | None = None,
    award_keys: Iterable[str] = (),
    generated_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Build a content-addressed, precomputed-only budget/program graph."""
    if not projection_state_matches(projection_state, lines, receipts):
        raise ValueError("DoD budget source projection state does not match immutable ledger")
    documents = _document_projection(receipts)
    selected_lines = _latest_lines(lines)
    if not selected_lines:
        raise ValueError("DoD budget graph has no retained source lines")
    programs_by_key: dict[str, dict[str, Any]] = {}
    program_by_line: dict[str, str] = {}
    edges: list[dict[str, Any]] = []
    for line in selected_lines:
        program = _program_from_line(line)
        existing = programs_by_key.get(program["program_key"])
        if existing is None:
            programs_by_key[program["program_key"]] = program
        else:
            if existing["name"] != program["name"] or existing["native_identifier"] != program["native_identifier"]:
                raise ValueError("source-native program identity is ambiguous")
            existing["line_keys"].extend(program["line_keys"])
        program_by_line[str(line["line_key"])] = str(program["program_key"])
        edges.append(_line_program_edge(line, program))
    programs = []
    for program in programs_by_key.values():
        program["line_keys"] = sorted(set(program["line_keys"]))
        programs.append(program)
    programs.sort(key=lambda row: row["program_key"])
    edge_set = reviewed_edge_set if reviewed_edge_set is not None else {"contract": BUDGET_EDGE_REVIEW_SET_CONTRACT, "schema_version": BUDGET_PROGRAM_GRAPH_SCHEMA_VERSION, "edges": []}
    if (
        not isinstance(edge_set, Mapping)
        or edge_set.get("contract") != BUDGET_EDGE_REVIEW_SET_CONTRACT
        or edge_set.get("schema_version") != BUDGET_PROGRAM_GRAPH_SCHEMA_VERSION
        or not isinstance(edge_set.get("edges"), list)
    ):
        raise ValueError("reviewed budget edge input contract is invalid")
    lines_by_key = {str(line["line_key"]): line for line in selected_lines}
    if len(lines_by_key) != len(selected_lines):
        raise ValueError("DoD budget graph has duplicate retained line identities")
    program_keys = set(programs_by_key)
    exact_award_keys = {str(value) for value in award_keys if str(value).strip()}
    if edge_set["edges"] and not exact_award_keys:
        raise ValueError("reviewed budget edges require a nonempty exact award set")
    for raw in edge_set["edges"]:
        edges.append(_reviewed_edge(
            raw,
            lines_by_key=lines_by_key,
            program_by_line=program_by_line,
            program_keys=program_keys,
            award_keys=exact_award_keys,
        ))
    if len({edge["edge_id"] for edge in edges}) != len(edges):
        raise ValueError("budget program graph has duplicate evidence edges")
    known_values = [str(line["known_at"]) for line in selected_lines]
    document_years = {int(doc["fiscal_year"]) for doc in documents}
    line_years = {int(line["fiscal_year"]) for line in selected_lines}
    paired_exhibits = bool(document_years) and document_years == line_years and all(
        {doc["exhibit"] for doc in documents if doc["fiscal_year"] == fiscal_year} == {"p1", "r1"}
        and {line["exhibit"] for line in selected_lines if line["fiscal_year"] == fiscal_year} == {"p1", "r1"}
        for fiscal_year in document_years
    )
    request_status = "ok" if paired_exhibits else "partial"
    reviewed_count = len(edge_set["edges"])
    graph = {
        "contract": BUDGET_PROGRAM_GRAPH_CONTRACT,
        "schema_version": BUDGET_PROGRAM_GRAPH_SCHEMA_VERSION,
        "content_id": "",
        "as_of": str(as_of),
        "known_at": max(known_values) if known_values else None,
        "generated_at": _instant(generated_at or datetime.now(timezone.utc), label="generated_at"),
        "authority": dict(AUTHORITY),
        "source_coverage": {
            "president_budget_request": {
                "status": request_status,
                "reason": "Receipt-bound P-1/R-1 President's Budget source documents only.",
            },
            "authorization": {"status": "uncollected", "reason": "Congressional authorization sources are outside Wave 8."},
            "appropriation_enacted": {"status": "uncollected", "reason": "No direct enacted-appropriation source is collected in Wave 8."},
            "execution": {"status": "uncollected", "reason": "Budget execution is not inferred from P-1/R-1 request exhibits."},
            "reviewed_award_edges": {
                "status": "ok" if reviewed_count else "partial",
                "reason": "Only documentary program-to-award edges are present; an empty set is an honest unresolved result." if not reviewed_count else "Every program-to-award edge is manually reviewed and evidence-bound.",
            },
        },
        "documents": documents,
        "lines": selected_lines,
        "programs": programs,
        "edges": sorted(edges, key=lambda row: row["edge_id"]),
        "limitations": [
            "Wave 8 supplies a fixture-only parser contract; no live PDF acquisition or real-layout extraction is activated for publication.",
            "P-1/R-1 President's Budget request evidence is not authorization, enacted appropriation, execution, obligation, award value, backlog, or revenue.",
            "Program-to-award paths require exact reviewed documentary evidence; program names and semantic similarity do not create edges.",
            "Economic weight is null in Wave 8, so this graph does not allocate a budget line to an issuer.",
            "Issuer attribution is not projected here and must remain governed by the existing time-valid recipient entity graph.",
        ],
    }
    content_id = budget_program_graph_content_id(graph)
    if content_id is None:
        raise ValueError("budget program graph cannot be represented as canonical JSON")
    graph["content_id"] = content_id
    if not is_valid_budget_program_graph(graph):
        raise ValueError("budget program graph violates its published contract")
    return graph


def _schema_registry(root: Path | None = None):
    from referencing import Registry, Resource

    contracts = _root(root) / "contracts" / "government_revenue"
    registry = Registry()
    for name in (
        "government_budget_line.v1.schema.json",
        "government_budget_edge.v1.schema.json",
        "government_budget_program_graph.v1.schema.json",
    ):
        value = json.loads((contracts / name).read_text(encoding="utf-8"))
        registry = registry.with_resource(value["$id"], Resource.from_contents(value))
    return registry


def _validate_graph_semantics(value: Mapping[str, Any]) -> None:
    documents = value.get("documents")
    lines = value.get("lines")
    programs = value.get("programs")
    edges = value.get("edges")
    if not all(isinstance(item, list) for item in (documents, lines, programs, edges)):
        raise ValueError("budget graph collections are malformed")

    documents_by_receipt: dict[str, Mapping[str, Any]] = {}
    for document in documents:
        if not isinstance(document, Mapping):
            raise ValueError("budget graph document is malformed")
        receipt_id = _text(document.get("receipt_id"), label="document receipt ID")
        hashes = document.get("page_text_sha256s")
        if (
            receipt_id in documents_by_receipt
            or not isinstance(hashes, list)
            or len(hashes) != document.get("page_count")
            or document.get("extraction_semantic_sha256") != _extraction_semantic_sha256(hashes)
        ):
            raise ValueError("budget graph document extraction binding is malformed")
        if _official_https_url(document.get("source_url")) != document.get("source_url"):
            raise ValueError("budget graph document source URL is not an official stable URL")
        documents_by_receipt[receipt_id] = document

    lines_by_key: dict[str, Mapping[str, Any]] = {}
    program_by_line: dict[str, str] = {}
    for line in lines:
        if not isinstance(line, Mapping):
            raise ValueError("budget graph line is malformed")
        line_key = _text(line.get("line_key"), label="line key")
        source = line.get("source")
        provenance = line.get("provenance")
        if line_key in lines_by_key or not isinstance(source, Mapping) or not isinstance(provenance, Mapping):
            raise ValueError("budget graph line identity or provenance is malformed")
        document = documents_by_receipt.get(str(source.get("receipt_id") or ""))
        page_number = provenance.get("page_number")
        if (
            document is None
            or source.get("source_url") != document.get("source_url")
            or _official_https_url(source.get("source_url")) != source.get("source_url")
            or source.get("document_sha256") != document.get("content_sha256")
            or line.get("fiscal_year") != document.get("fiscal_year")
            or line.get("exhibit") != document.get("exhibit")
            or provenance.get("parser_version") != document.get("parser_version")
            or isinstance(page_number, bool)
            or not isinstance(page_number, int)
            or not 1 <= page_number <= document.get("page_count", 0)
            or provenance.get("page_text_sha256") != document["page_text_sha256s"][page_number - 1]
            or line.get("line_state_sha256") != _line_state_sha256(line)
        ):
            raise ValueError("budget graph line does not reconcile to its document")
        for field, key in (("amounts", "semantic"), ("quantities", "semantic")):
            cells = line.get(field)
            semantics = [cell.get(key) for cell in cells] if isinstance(cells, list) and all(isinstance(cell, Mapping) for cell in cells) else []
            if len(semantics) != len(cells or []) or len(semantics) != len(set(semantics)):
                raise ValueError("budget graph line has duplicate or malformed source column semantics")
        lines_by_key[line_key] = line

    programs_by_key: dict[str, Mapping[str, Any]] = {}
    for program in programs:
        if not isinstance(program, Mapping):
            raise ValueError("budget graph program is malformed")
        program_key = _text(program.get("program_key"), label="program key")
        line_keys = program.get("line_keys")
        if program_key in programs_by_key or not isinstance(line_keys, list) or any(key not in lines_by_key for key in line_keys):
            raise ValueError("budget graph program line membership is malformed")
        programs_by_key[program_key] = program
        for line_key in line_keys:
            if line_key in program_by_line:
                raise ValueError("budget graph line belongs to multiple programs")
            expected_program = _program_from_line(lines_by_key[line_key])
            if expected_program["program_key"] != program_key or expected_program["name"] != program.get("name"):
                raise ValueError("budget graph program does not match its source-native line identity")
            program_by_line[line_key] = program_key
    if set(program_by_line) != set(lines_by_key):
        raise ValueError("budget graph does not map every line to exactly one program")

    source_edges: dict[str, Mapping[str, Any]] = {}
    reviewed_edges: list[Mapping[str, Any]] = []
    edge_ids: set[str] = set()
    for edge in edges:
        if not isinstance(edge, Mapping) or edge.get("edge_id") in edge_ids:
            raise ValueError("budget graph edge identity is malformed")
        edge_ids.add(str(edge["edge_id"]))
        if edge.get("edge_type") == "source_native_identifier":
            line_key = str(edge.get("from_id") or "")
            if line_key in source_edges or line_key not in lines_by_key:
                raise ValueError("budget graph source-native edge is malformed")
            expected = _line_program_edge(lines_by_key[line_key], programs_by_key[program_by_line[line_key]])
            if _canonical_json(dict(edge)) != _canonical_json(expected):
                raise ValueError("budget graph source-native edge does not reconcile")
            source_edges[line_key] = edge
        elif edge.get("edge_type") == "reviewed_documentary":
            reviewed_edges.append(edge)
        else:
            raise ValueError("budget graph edge type is unsupported")
    if set(source_edges) != set(lines_by_key):
        raise ValueError("budget graph lacks an exact source-native edge for every line")
    award_keys = {str(edge.get("to_id") or "") for edge in reviewed_edges}
    for edge in reviewed_edges:
        normalized = _reviewed_edge(
            edge,
            lines_by_key=lines_by_key,
            program_by_line=program_by_line,
            program_keys=set(programs_by_key),
            award_keys=award_keys,
        )
        if _canonical_json(dict(edge)) != _canonical_json(normalized):
            raise ValueError("budget graph reviewed edge does not reconcile")

    years = {int(document["fiscal_year"]) for document in documents}
    paired = bool(years) and years == {int(line["fiscal_year"]) for line in lines} and all(
        {document["exhibit"] for document in documents if document["fiscal_year"] == year} == {"p1", "r1"}
        and {line["exhibit"] for line in lines if line["fiscal_year"] == year} == {"p1", "r1"}
        for year in years
    )
    expected_status = "ok" if paired else "partial"
    if value.get("source_coverage", {}).get("president_budget_request", {}).get("status") != expected_status:
        raise ValueError("budget graph source coverage does not match retained line evidence")


def is_valid_budget_program_graph(value: Any, *, root: Path | None = None) -> bool:
    try:
        from jsonschema import Draft202012Validator, FormatChecker

        contracts = _root(root) / "contracts" / "government_revenue"
        schema = json.loads((contracts / "government_budget_program_graph.v1.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, registry=_schema_registry(root), format_checker=FormatChecker())
        validator.validate(value)
        _validate_graph_semantics(value)
        return (
            isinstance(value, Mapping)
            and budget_program_graph_content_id(value) == value.get("content_id")
            and value.get("authority") == AUTHORITY
        )
    except Exception:  # malformed external artifacts must fail closed for callers
        return False


__all__ = [
    "AUTHORITY",
    "BUDGET_EDGE_CONTRACT",
    "BUDGET_EDGE_REVIEW_SET_CONTRACT",
    "BUDGET_PROGRAM_GRAPH_CONTRACT",
    "budget_program_graph_content_id",
    "build_budget_program_graph",
    "is_valid_budget_program_graph",
    "load_reviewed_edges",
]
