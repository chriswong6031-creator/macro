"""Hermetic contract tests for the DoD P-1/R-1 evidence foundation."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from collectors import dod_budget


FIXTURES = Path(__file__).parent / "fixtures" / "dod_budget"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _receipt(name: str, *, observed_at: str = "2026-08-02T12:00:00+00:00") -> tuple[dict, dict]:
    fixture = _fixture(name)
    pdf_bytes = (b"%PDF-1.4\nfixture-" + name.encode("ascii"))
    sha = dod_budget._sha256(pdf_bytes)
    receipt = dod_budget.build_document_receipt(
        source_url=fixture["source_url"],
        final_url=fixture["final_url"],
        pdf_bytes=pdf_bytes,
        pages=fixture["pages"],
        fiscal_year=fixture["fiscal_year"],
        exhibit=fixture["exhibit"],
        observed_at=observed_at,
        immutable_object_key=f"{dod_budget.IMMUTABLE_R2_PREFIX}{sha}.pdf",
    )
    return fixture, receipt


def _source_bundle() -> tuple[list[dict], list[dict], dict]:
    lines: list[dict] = []
    receipts: list[dict] = []
    for name in ("fy2026_p1.json", "fy2026_r1.json"):
        fixture, receipt = _receipt(name)
        parsed, _ = dod_budget.parse_budget_document(fixture["pages"], receipt)
        lines.extend(parsed)
        receipts.append(receipt)
    state = dod_budget.budget_projection_state(lines, receipts)
    return lines, receipts, state


def test_receipt_is_content_addressed_hash_only_and_requires_immutable_storage() -> None:
    _, receipt = _receipt("fy2026_p1.json")

    assert receipt["receipt_id"].startswith("dod-budget:")
    assert len(receipt["receipt_id"].removeprefix("dod-budget:")) == 64
    assert receipt["response_sha256"] == receipt["content_sha256"]
    assert receipt["immutable_object_key"] == (
        f"government-revenue/dod-budget/pdf/sha256/{receipt['content_sha256']}.pdf"
    )
    assert receipt["raw_response_bodies_persisted"] is False
    assert receipt["document_stage"] == "president_budget_request"
    assert receipt["page_count"] == len(receipt["page_text_sha256s"])
    assert receipt["extraction_semantic_sha256"] == dod_budget._extraction_semantic_sha256(
        receipt["page_text_sha256s"]
    )

    invalid = dict(receipt)
    invalid["raw_response_body"] = "forbidden"
    with pytest.raises(ValueError, match="forbidden"):
        dod_budget.validate_document_receipt(invalid)

    invalid = dict(receipt)
    invalid["immutable_object_key"] = "mutable/path.pdf"
    with pytest.raises(ValueError, match="immutable"):
        dod_budget.validate_document_receipt(invalid)


def test_receipt_rejects_unofficial_url_and_header_mismatch() -> None:
    fixture = _fixture("fy2026_p1.json")
    pdf_bytes = b"%PDF-1.4\nfixture"
    sha = dod_budget._sha256(pdf_bytes)
    with pytest.raises(ValueError, match="allowlisted"):
        dod_budget.build_document_receipt(
            source_url="https://example.test/p1.pdf",
            final_url=fixture["final_url"],
            pdf_bytes=pdf_bytes,
            pages=fixture["pages"],
            fiscal_year=2026,
            exhibit="p1",
            observed_at="2026-08-02T12:00:00Z",
            immutable_object_key=f"{dod_budget.IMMUTABLE_R2_PREFIX}{sha}.pdf",
        )
    with pytest.raises(ValueError, match="header exhibit mismatch"):
        dod_budget.verify_document_header(fixture["pages"], fiscal_year=2026, exhibit="r1")
    with pytest.raises(ValueError, match="allowlisted"):
        dod_budget.build_document_receipt(
            source_url=fixture["source_url"] + "?sig=must-not-persist",
            final_url=fixture["final_url"],
            pdf_bytes=pdf_bytes,
            pages=fixture["pages"],
            fiscal_year=2026,
            exhibit="p1",
            observed_at="2026-08-02T12:00:00Z",
            immutable_object_key=f"{dod_budget.IMMUTABLE_R2_PREFIX}{sha}.pdf",
        )


def test_parser_preserves_exact_identity_page_hash_and_stage_semantics() -> None:
    p1, p1_receipt = _receipt("fy2026_p1.json")
    r1, r1_receipt = _receipt("fy2026_r1.json")
    p1_lines, _ = dod_budget.parse_budget_document(p1["pages"], p1_receipt)
    r1_lines, _ = dod_budget.parse_budget_document(r1["pages"], r1_receipt)

    p1_line = p1_lines[0]
    r1_line = r1_lines[0]
    assert p1_line["native_identifier"] == {"kind": "p1_line_item", "value": "10"}
    assert r1_line["native_identifier"] == {"kind": "program_element", "value": "0604800A"}
    assert p1_line["document_stage"] == r1_line["document_stage"] == "president_budget_request"
    assert p1_line["source"]["receipt_id"] == p1_receipt["receipt_id"]
    assert p1_line["provenance"]["page_number"] == 2
    assert p1_line["provenance"]["page_text_sha256"] == dod_budget._sha256(p1["pages"][1])
    amounts = {row["semantic"]: row["amount_usd"] for row in p1_line["amounts"]}
    assert amounts == {
        "historical_actual": 728_258_000.0,
        "prior_year_enacted_reference": 769_054_000.0,
        "discretionary_request": 732_060_000.0,
        "reconciliation_request": 0.0,
        "president_budget_request_total": 732_060_000.0,
    }
    assert "execution" not in p1_line
    assert "appropriation_enacted" not in p1_line
    assert {row["semantic"]: row["quantity"] for row in p1_line["quantities"]} == {
        "historical_actual": 26.0,
        "prior_year_enacted_reference": 26.0,
        "discretionary_request": 24.0,
        "reconciliation_request": None,
        "president_budget_request_total": 24.0,
    }


def test_parser_fails_closed_when_detail_does_not_reconcile_to_printed_total() -> None:
    fixture, receipt = _receipt("fy2026_p1.json")
    pages = list(fixture["pages"])
    pages[1] = pages[1].replace("total_request=732060", "total_request=700000", 1)
    pdf_bytes = b"%PDF-1.4\nreconciliation-mismatch"
    receipt = dod_budget.build_document_receipt(
        source_url=fixture["source_url"], final_url=fixture["final_url"],
        pdf_bytes=pdf_bytes, pages=pages, fiscal_year=fixture["fiscal_year"],
        exhibit=fixture["exhibit"], observed_at="2026-08-02T12:00:00Z",
        immutable_object_key=f"{dod_budget.IMMUTABLE_R2_PREFIX}{dod_budget._sha256(pdf_bytes)}.pdf",
    )
    with pytest.raises(ValueError, match="source total mismatch"):
        dod_budget.parse_budget_document(pages, receipt)


def test_parser_rejects_page_swap_or_count_drift_after_receipt() -> None:
    fixture, receipt = _receipt("fy2026_p1.json")
    tampered = list(fixture["pages"])
    tampered[1] = tampered[1].replace("732060", "999999")
    with pytest.raises(ValueError, match="extracted pages"):
        dod_budget.parse_budget_document(tampered, receipt)
    with pytest.raises(ValueError, match="extracted pages"):
        dod_budget.parse_budget_document([*fixture["pages"], "extra page"], receipt)


def test_receipt_merge_is_immutable_and_line_versions_keep_a_to_b_to_a() -> None:
    fixture, receipt = _receipt("fy2026_p1.json")
    lines, _ = dod_budget.parse_budget_document(fixture["pages"], receipt)
    first = lines[0]
    changed = copy.deepcopy(first)
    changed["amounts"][-1]["amount_usd"] += 1_000.0
    changed["first_seen_at"] = "2026-08-03T12:00:00+00:00"
    changed["line_state_sha256"] = dod_budget._line_state_sha256(changed)
    restored = copy.deepcopy(first)

    versions = dod_budget.append_line_snapshot_versions([], [first])
    versions = dod_budget.append_line_snapshot_versions(versions, [changed])
    versions = dod_budget.append_line_snapshot_versions(versions, [restored])
    assert len(versions) == 3
    assert versions[0]["line_state_sha256"] == versions[2]["line_state_sha256"]
    assert versions[1]["line_state_sha256"] != versions[0]["line_state_sha256"]
    assert versions[1]["first_seen_at"] == first["first_seen_at"]

    duplicate = dod_budget.merge_receipts([receipt], [dict(receipt)])
    assert duplicate == [receipt]
    _, later = _receipt("fy2026_p1.json", observed_at="2026-08-03T12:00:00+00:00")
    assert later["content_sha256"] == receipt["content_sha256"]
    assert later["receipt_id"] != receipt["receipt_id"]
    assert dod_budget.merge_receipts([receipt], [later]) == [receipt, later]

    conflict = dict(receipt)
    conflict["page_count"] = receipt["page_count"] + 1
    with pytest.raises(ValueError, match="page count|identity"):
        dod_budget.merge_receipts([receipt], [conflict])


def test_projection_state_binds_every_line_to_a_retained_exact_receipt() -> None:
    lines, receipts, state = _source_bundle()
    assert dod_budget.projection_state_matches(state, lines, receipts)
    assert state["projection_generation_id"].startswith("dod-budget-")

    invalid = copy.deepcopy(lines)
    invalid[0]["source"]["receipt_id"] = "dod-budget:" + "0" * 64
    with pytest.raises(ValueError, match="retained immutable receipt"):
        dod_budget.budget_projection_state(invalid, receipts)

    invalid = copy.deepcopy(lines)
    invalid[0]["known_at"] = "2099-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="provenance|state hash"):
        dod_budget.budget_projection_state(invalid, receipts)

    with pytest.raises(ValueError, match="unused document receipt"):
        dod_budget.budget_projection_state(
            [row for row in lines if row["exhibit"] == "p1"],
            receipts,
        )


def test_fixture_loader_stays_local_and_never_acquires_live_sources() -> None:
    docs = dod_budget.fixture_documents_from_directory(FIXTURES)
    assert {doc["exhibit"] for doc in docs} == {"p1", "r1"}
    assert dod_budget.main(["--fixture-dir", str(FIXTURES)]) == 0
