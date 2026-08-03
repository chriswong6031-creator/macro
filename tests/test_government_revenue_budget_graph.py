"""Graph-level fail-closed tests for the Wave 8 DoD budget foundation."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from collectors import dod_budget
from engine.government_revenue import budget_program


FIXTURES = Path(__file__).parent / "fixtures" / "dod_budget"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _bundle() -> tuple[list[dict], list[dict], dict]:
    lines: list[dict] = []
    receipts: list[dict] = []
    for name in ("fy2026_p1.json", "fy2026_r1.json"):
        fixture = _fixture(name)
        pdf_bytes = b"%PDF-1.4\ngraph-" + name.encode("ascii")
        sha = dod_budget._sha256(pdf_bytes)
        receipt = dod_budget.build_document_receipt(
            source_url=fixture["source_url"],
            final_url=fixture["final_url"],
            pdf_bytes=pdf_bytes,
            pages=fixture["pages"],
            fiscal_year=fixture["fiscal_year"],
            exhibit=fixture["exhibit"],
            observed_at="2026-08-02T12:00:00+00:00",
            immutable_object_key=f"{dod_budget.IMMUTABLE_R2_PREFIX}{sha}.pdf",
        )
        parsed, _ = dod_budget.parse_budget_document(fixture["pages"], receipt)
        lines.extend(parsed)
        receipts.append(receipt)
    return lines, receipts, dod_budget.budget_projection_state(lines, receipts)


def _graph(*, reviewed_edge_set: dict | None = None, award_keys=()) -> dict:
    lines, receipts, state = _bundle()
    return budget_program.build_budget_program_graph(
        lines=lines,
        receipts=receipts,
        projection_state=state,
        as_of="2026-08-02",
        reviewed_edge_set=reviewed_edge_set,
        award_keys=award_keys,
        generated_at="2026-08-02T12:05:00+00:00",
    )


def _reviewed_edge(graph: dict, *, award_key: str = "generated:CONT_AWD_TEST") -> dict:
    line = graph["lines"][0]
    program_edge = next(edge for edge in graph["edges"] if edge["from_id"] == line["line_key"])
    return {
        "from_type": "program",
        "from_id": program_edge["to_id"],
        "to_type": "award",
        "to_id": award_key,
        "edge_type": "reviewed_documentary",
        "review_state": "reviewed",
        "economic_weight": None,
        "effective_at": "2026-08-02T00:00:00+00:00",
        "known_at": "2026-08-02T12:00:00+00:00",
        "evidence": [
            {
                "kind": "budget_line",
                "ref_id": line["line_key"],
                "document_sha256": line["source"]["document_sha256"],
                "page_number": line["provenance"]["page_number"],
                "page_text_sha256": line["provenance"]["page_text_sha256"],
                "note": "Exact P-1 line cited during documentary review.",
            },
            {
                "kind": "award",
                "ref_id": award_key,
                "source_url": "https://api.usaspending.gov/api/v2/awards/CONT_AWD_TEST/",
                "note": "Exact USAspending award identifier reviewed alongside the line evidence.",
            },
        ],
    }


def test_graph_is_content_addressed_display_only_and_keeps_stage_rails_separate() -> None:
    graph = _graph()

    assert graph["content_id"].startswith("grbg1-")
    assert budget_program.budget_program_graph_content_id(graph) == graph["content_id"]
    assert budget_program.is_valid_budget_program_graph(graph)
    assert graph["authority"] == budget_program.AUTHORITY
    assert graph["source_coverage"]["president_budget_request"]["status"] == "ok"
    assert graph["source_coverage"]["authorization"]["status"] == "uncollected"
    assert graph["source_coverage"]["appropriation_enacted"]["status"] == "uncollected"
    assert graph["source_coverage"]["execution"]["status"] == "uncollected"
    assert all(edge["edge_type"] == "source_native_identifier" for edge in graph["edges"])
    assert all(edge["economic_weight"] is None for edge in graph["edges"])

    later = _graph()
    assert later["content_id"] == graph["content_id"]
    assert {program["kind"] for program in graph["programs"]} == {
        "procurement_line_item", "rdte_program_element",
    }


def test_manual_program_to_award_edge_requires_exact_reviewed_evidence_and_award_membership() -> None:
    baseline = _graph()
    edge = _reviewed_edge(baseline)
    reviewed = {
        "contract": "government_budget_reviewed_edges.v1",
        "schema_version": "1.0.0",
        "edges": [edge],
    }
    graph = _graph(reviewed_edge_set=reviewed, award_keys={edge["to_id"]})
    linked = next(item for item in graph["edges"] if item["to_type"] == "award")

    assert linked["edge_type"] == "reviewed_documentary"
    assert linked["review_state"] == "reviewed"
    assert linked["economic_weight"] is None
    assert {item["kind"] for item in linked["evidence"]} == {"budget_line", "award"}
    assert budget_program.is_valid_budget_program_graph(graph)

    invalid = copy.deepcopy(reviewed)
    invalid["edges"][0]["economic_weight"] = 0.5
    with pytest.raises(ValueError, match="economic weight"):
        _graph(reviewed_edge_set=invalid, award_keys={edge["to_id"]})

    invalid = copy.deepcopy(reviewed)
    invalid["edges"][0]["edge_type"] = "semantic_candidate"
    with pytest.raises(ValueError, match="derived edge type"):
        _graph(reviewed_edge_set=invalid, award_keys={edge["to_id"]})

    with pytest.raises(ValueError, match="exact award set"):
        _graph(reviewed_edge_set=reviewed, award_keys={"generated:OTHER"})

    with pytest.raises(ValueError, match="nonempty exact award set|exact award set"):
        _graph(reviewed_edge_set=reviewed)

    invalid = copy.deepcopy(reviewed)
    invalid["edges"][0]["evidence"][0]["page_number"] = 999999
    with pytest.raises(ValueError, match="does not match the retained line"):
        _graph(reviewed_edge_set=invalid, award_keys={edge["to_id"]})

    invalid = copy.deepcopy(reviewed)
    invalid["edges"][0]["evidence"][1]["source_url"] = "https://api.usaspending.gov/"
    with pytest.raises(ValueError, match="exact official USAspending award URL"):
        _graph(reviewed_edge_set=invalid, award_keys={edge["to_id"]})


def test_graph_fails_closed_for_projection_state_or_authority_tampering() -> None:
    lines, receipts, state = _bundle()
    broken = dict(state)
    broken["semantic_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="projection state"):
        budget_program.build_budget_program_graph(
            lines=lines,
            receipts=receipts,
            projection_state=broken,
            as_of="2026-08-02",
            generated_at="2026-08-02T12:05:00+00:00",
        )

    graph = _graph()
    graph["authority"]["can_rank"] = True
    assert not budget_program.is_valid_budget_program_graph(graph)

    graph = _graph()
    graph["edges"][0]["to_type"] = "award"
    graph["content_id"] = budget_program.budget_program_graph_content_id(graph)
    assert not budget_program.is_valid_budget_program_graph(graph)

    graph = _graph()
    document = next(row for row in graph["documents"] if row["exhibit"] == "p1")
    document["source_url"] += "?sig=must-not-persist"
    for line in graph["lines"]:
        if line["source"]["receipt_id"] == document["receipt_id"]:
            line["source"]["source_url"] = document["source_url"]
            line["line_state_sha256"] = dod_budget._line_state_sha256(line)
    graph["content_id"] = budget_program.budget_program_graph_content_id(graph)
    assert not budget_program.is_valid_budget_program_graph(graph)

    graph = _graph()
    graph["lines"][0]["amounts"][1]["semantic"] = graph["lines"][0]["amounts"][0]["semantic"]
    graph["lines"][0]["line_state_sha256"] = dod_budget._line_state_sha256(graph["lines"][0])
    graph["content_id"] = budget_program.budget_program_graph_content_id(graph)
    assert not budget_program.is_valid_budget_program_graph(graph)


def test_review_set_loader_accepts_only_the_empty_seed_contract() -> None:
    loaded = budget_program.load_reviewed_edges(Path(__file__).parents[1])
    assert loaded == {
        "contract": "government_budget_reviewed_edges.v1",
        "schema_version": "1.0.0",
        "edges": [],
    }
