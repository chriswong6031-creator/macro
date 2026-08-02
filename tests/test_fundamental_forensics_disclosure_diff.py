"""Offline contract tests for the filing disclosure corpus and redline engine."""
from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from engine.fundamental_forensics import (
    compare_filings,
    load_disclosure_diff_registry,
    normalize_filing,
)
from engine.fundamental_forensics import disclosure_diff as disclosure_diff_module


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "fundamental_forensics" / "disclosure_diff"


def _source(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _documents() -> tuple[dict[str, str], dict[str, str]]:
    return (
        {
            "entity_cik": "0000000001",
            "accession": "0000000001-25-000001",
            "form": "10-K",
            "filed_at": "2025-02-15",
            "report_date": "2024-12-31",
            "source_url": "https://example.test/prior-10k.htm",
            "content_type": "html",
            "content": _source("prior_10k.html"),
        },
        {
            "entity_cik": "0000000001",
            "accession": "0000000001-26-000001",
            "form": "10-K",
            "filed_at": "2026-02-15",
            "report_date": "2025-12-31",
            "source_url": "https://example.test/current-10k.htm",
            "content_type": "html",
            "content": _source("current_10k.html"),
        },
    )


def _comparison():
    prior, current = _documents()
    return compare_filings(prior, current)


def _finding(result, detector_id: str):
    return next(item for item in result.findings if item.detector_id == detector_id)


def test_fixture_triggers_every_requested_detector_with_exact_receipts() -> None:
    result = _comparison()
    assert result.schema == "fundamental_forensics.disclosure_diff/v1"
    assert {item.detector_id: item.state.value for item in result.findings} == {
        "kpi_disappearance": "triggered",
        "risk_factor_wording_change": "triggered",
        "revenue_recognition_policy_change": "triggered",
        "auditor_change": "triggered",
        "icfr_material_weakness_change": "triggered",
    }
    for finding in result.findings:
        assert finding.applicability.value == "applicable"
        assert finding.priority == "high"
        assert finding.review_level == "manual_review"
        assert dict(finding.labels)["en"]
        assert dict(finding.labels)["zh-Hans"]
        assert finding.label_key.startswith("disclosure.finding.")
        assert finding.evidence_receipts
        for receipt in finding.evidence_receipts:
            assert receipt.source_url and receipt.source_url.startswith("https://example.test/")
            assert len(receipt.source_sha256) == 64
            assert receipt.source_span.char_start < receipt.source_span.char_end
            assert receipt.source_excerpt


def test_source_spans_are_exact_and_table_cells_retain_their_own_receipts() -> None:
    prior, _ = _documents()
    normalized = normalize_filing(prior)
    kpi = next(block for block in normalized.blocks if "Monthly Active Users" in block.text)
    raw_fragment = normalized.raw_source[kpi.source_span.char_start:kpi.source_span.char_end]
    assert kpi.text in raw_fragment
    assert kpi.source_span.byte_start == len(normalized.raw_source[:kpi.source_span.char_start].encode("utf-8"))

    table = next(block for block in normalized.blocks if block.table is not None)
    cell = table.table.rows[1][1]
    cell_fragment = normalized.raw_source[cell.source_span.char_start:cell.source_span.char_end]
    assert "100" in cell_fragment
    assert cell.text == "100"


def test_large_one_line_inline_table_uses_sparse_locator_with_exact_utf8_offsets() -> None:
    rows = "".join(f"<tr><td>Row {index}</td><td>{index}</td></tr>" for index in range(1_400))
    source = "<html><body><div>" + ("中x" * 450_000) + "</div><table>" + rows + "</table></body></html>"
    started = perf_counter()
    normalized = normalize_filing(
        {"accession": "0004-25-000001", "form": "10-K", "content_type": "html", "content": source}
    )
    elapsed = perf_counter() - started
    table = next(block for block in normalized.blocks if block.table is not None)
    cell = table.table.rows[-1][1]
    assert cell.source_span.byte_start == len(source[:cell.source_span.char_start].encode("utf-8"))
    assert cell.source_span.line_start == cell.source_span.line_end == 1
    assert normalized.source_locator.checkpoint_chars <= 256
    assert len(normalized.source_locator.byte_prefixes) > 3_000
    # This fixture would perform multi-gigabyte prefix copies with the old
    # per-span implementation. The sparse locator completes comfortably below
    # this loose CI-safe bound while keeping exact byte coordinates.
    assert elapsed < 4.0


def test_fuzzy_alignment_similarity_calls_are_bounded_for_many_changed_blocks(monkeypatch) -> None:
    count = 500
    prior_rows = "".join(
        f"<p>Risk factor {index} requires customer concentration analysis and contractual controls for operations in the annual period.</p>"
        for index in range(count)
    )
    current_rows = "".join(
        f"<p>Risk factor {index} requires customer concentration and regulatory analysis, revised contractual controls, supply chain oversight, and liquidity contingency actions for operations in the annual period.</p>"
        for index in range(count)
    )
    calls = 0
    original = disclosure_diff_module._block_similarity

    def counted(prior_block, current_block):
        nonlocal calls
        calls += 1
        return original(prior_block, current_block)

    monkeypatch.setattr(disclosure_diff_module, "_block_similarity", counted)
    result = compare_filings(
        {"accession": "0005-25-000001", "form": "10-K", "content_type": "html", "content": f"<h1>Item 1A. Risk Factors</h1>{prior_rows}"},
        {"accession": "0005-26-000001", "form": "10-K", "content_type": "html", "content": f"<h1>Item 1A. Risk Factors</h1>{current_rows}"},
    )
    assert calls <= count * disclosure_diff_module._MAX_FUZZY_CANDIDATES_PER_BLOCK
    assert calls < count * count
    assert _finding(result, "risk_factor_wording_change").state.value == "triggered"
    assert sum(item.relation == "modified" for item in result.comparisons) >= count - 2


def test_sec_like_hidden_inline_xbrl_and_paragraph_item_headings_are_fast_and_visible_only() -> None:
    hidden_marker = "NON_VISIBLE_INLINE_XBRL_METADATA"
    hidden_payload = hidden_marker * 2_000
    prior_prose = (
        "Customer concentration, contract cancellations, and delayed renewals could reduce revenue and "
        "liquidity while increasing customer concentration risk to operating cash flow and earnings materially. "
    ) * 1_000
    current_prose = (
        "Supplier disruption, export controls, and cybersecurity incidents could affect revenue and liquidity "
        "while increasing supply-chain risk to operating cash flow and earnings materially. "
    ) * 1_000

    def sec_like_html(visible_prose: str) -> str:
        return (
            "<html><body>"
            "<ix:header><ix:hidden><div><div>"
            + hidden_payload
            + "</div></div></ix:hidden><ix:references>"
            + hidden_marker
            + "</ix:references><ix:resources><xbrli:context>"
            + hidden_marker
            + "</xbrli:context></ix:resources></ix:header>"
            "<p class='toc-heading'>Item 1A. Risk Factors</p>"
            f"<p>{visible_prose}</p>"
            "</body></html>"
        )

    prior_source = sec_like_html(prior_prose)
    current_source = sec_like_html(current_prose)
    prior = {"accession": "0006-25-000001", "form": "10-K", "content_type": "html", "content": prior_source}
    current = {"accession": "0006-26-000001", "form": "10-K", "content_type": "html", "content": current_source}

    normalized = normalize_filing(prior)
    visible_start = prior_source.index("<p class='toc-heading'>")
    heading = next(block for block in normalized.blocks if "Item 1A. Risk Factors" in block.text)
    assert heading.kind.value == "heading"
    assert heading.section_key == "risk_factors"
    assert heading.source_span.char_start >= visible_start
    assert all(hidden_marker not in block.text for block in normalized.blocks)
    assert all(block.source_span.char_start >= visible_start for block in normalized.blocks)

    started = perf_counter()
    result = compare_filings(prior, current)
    elapsed = perf_counter() - started
    redline = next(
        item
        for item in result.redline_ops
        if item.operation == "modified" and item.section_key == "risk_factors"
    )
    # This was formerly a char-level, autojunk-disabled diff over repeated
    # prose.  The coarse redline is deliberate, bounded, and still linked to
    # the exact whole-block source span.
    assert elapsed < 4.0
    assert redline.prior_receipt and redline.prior_receipt.source_span.char_start >= visible_start
    assert redline.inline_edits and redline.inline_edits[0].truncated is True
    assert len(redline.inline_edits[0].prior_text) <= disclosure_diff_module._COARSE_EDIT_CHARS
    assert _finding(result, "risk_factor_wording_change").state.value == "triggered"


def test_same_inputs_are_byte_stable_even_when_mapping_key_order_changes() -> None:
    prior, current = _documents()
    reordered_prior = {key: prior[key] for key in reversed(tuple(prior))}
    reordered_current = {key: current[key] for key in reversed(tuple(current))}
    first = compare_filings(prior, current).canonical_json()
    second = compare_filings(reordered_prior, reordered_current).canonical_json()
    assert first == second
    assert json.dumps(compare_filings(prior, current).to_dict(), ensure_ascii=False)


def test_moved_paragraph_is_one_move_not_a_delete_and_add_pair() -> None:
    result = _comparison()
    moved = next(item for item in result.comparisons if item.relation == "moved")
    prior_block = next(block for block in result.prior.blocks if block.block_id == moved.prior_block_id)
    current_block = next(block for block in result.current.blocks if block.block_id == moved.current_block_id)
    assert prior_block.text == current_block.text == "Our platform serves regulated customers through a recurring subscription model."
    assert all(
        not (
            item.relation in {"added", "removed"}
            and (
                item.prior_block_id == moved.prior_block_id
                or item.current_block_id == moved.current_block_id
            )
        )
        for item in result.comparisons
    )


def test_boilerplate_is_suppressed_without_hiding_numeric_table_edits() -> None:
    result = _comparison()
    boilerplate = [item for item in result.redline_ops if item.operation == "suppressed_boilerplate"]
    assert boilerplate and all(item.suppressed for item in boilerplate)
    assert not any(
        item.operation in {"added", "removed", "modified"}
        and item.prior_receipt
        and "Forward-looking statements" in item.prior_receipt.source_excerpt
        for item in result.redline_ops
    )
    numeric = [item for item in result.redline_ops if item.operation == "table_cell_changed"]
    assert numeric
    assert any(item.numeric_changed and any(edit.contains_numeric for edit in item.inline_edits) for item in numeric)
    assert any("100" in edit.prior_text and "120" in edit.current_text for item in numeric for edit in item.inline_edits)


def test_plain_text_10q_common_sections_and_required_only_smoke() -> None:
    prior = {
        "accession": "0002-25-000001",
        "form": "10-Q",
        "content": """PART I\n\nITEM 1. Financial Statements\n\nRevenue was 100.\n\nITEM 2. Management's Discussion and Analysis\n\nOperations were stable.\n\nITEM 4. Controls and Procedures\n\nInternal control over financial reporting was effective.""",
    }
    current = {
        "accession": "0002-25-000002",
        "form": "10-Q",
        "content": """PART I\n\nITEM 1. Financial Statements\n\nRevenue was 120.\n\nITEM 2. Management's Discussion and Analysis\n\nOperations were stable.\n\nITEM 4. Controls and Procedures\n\nInternal control over financial reporting was effective.""",
    }
    normalized = normalize_filing(prior)
    assert {section.key for section in normalized.sections} >= {"financial_statements", "mda", "controls"}
    result = compare_filings(prior, current)
    assert result.prior.filed_at is None and result.current.report_date is None
    assert len(result.findings) == 5


def test_not_applicable_and_not_evaluable_are_explicit_not_silent() -> None:
    prior = {"accession": "0003-25-000001", "form": "10-K", "content": "Item 1. Business\n\nA simple business description."}
    current = {"accession": "0003-25-000002", "form": "10-K", "content": "Item 1. Business\n\nAn updated business description."}
    result = compare_filings(prior, current)
    kpi = _finding(result, "kpi_disappearance")
    risk = _finding(result, "risk_factor_wording_change")
    policy = _finding(result, "revenue_recognition_policy_change")
    auditor = _finding(result, "auditor_change")
    controls = _finding(result, "icfr_material_weakness_change")
    assert (kpi.state.value, kpi.applicability.value, kpi.review_level) == ("clear", "not_applicable", "not_applicable")
    assert (policy.state.value, policy.applicability.value) == ("clear", "not_applicable")
    for finding in (risk, auditor, controls):
        assert (finding.state.value, finding.applicability.value, finding.review_level) == (
            "not_evaluable", "not_evaluable", "insufficient_evidence"
        )
        assert finding.evidence_receipts


def test_clear_cases_and_negated_material_weakness_are_not_overflagged() -> None:
    prior, current = _documents()
    current["content"] = (
        current["content"]
        .replace("Deloitte &amp; Touche LLP", "PricewaterhouseCoopers LLP")
        .replace(
            "Management identified a material weakness in internal control over financial reporting and concluded that controls were not effective.",
            "Management concluded that internal control over financial reporting was effective. No material weaknesses were identified.",
        )
    )
    result = compare_filings(prior, current)
    assert _finding(result, "auditor_change").state.value == "clear"
    assert _finding(result, "icfr_material_weakness_change").state.value == "clear"


def test_risk_and_policy_clear_when_relevant_language_is_unchanged() -> None:
    prior, current = _documents()
    current["content"] = current["content"].replace(
        "Customer concentration and government procurement delays could reduce revenue if a limited number of enterprise customers cancel purchases, defer renewals, or renegotiate prices. A loss of a major customer could materially harm liquidity, operating results, and future cash flows.",
        "Customer concentration could reduce revenue if a limited number of enterprise customers cancel or delay purchases. A loss of a major customer may materially harm our operating results and cash flows.",
    ).replace(
        "We recognize revenue when customers obtain control after product shipment or service acceptance. Subscription revenue is recognized ratably over the contractual term, including implementation services when distinct.",
        "We recognize revenue when control of promised goods or services transfers to customers. Subscription revenue is recognized ratably over the contractual term.",
    )
    result = compare_filings(prior, current)
    assert _finding(result, "risk_factor_wording_change").state.value == "clear"
    assert _finding(result, "revenue_recognition_policy_change").state.value == "clear"


def test_unregistered_item_heading_ends_risk_section_and_prevents_scope_bleed() -> None:
    prior = {
        "accession": "0008-25-000001",
        "form": "10-K",
        "content": """Item 1A. Risk Factors

Cybersecurity incidents could materially disrupt operations and liquidity.

Item 1B. Unresolved Staff Comments

There were no unresolved staff comments.""",
    }
    current = {
        "accession": "0008-26-000001",
        "form": "10-K",
        "content": """Item 1A. Risk Factors

Cybersecurity incidents could materially disrupt operations and liquidity.

Item 1B. Unresolved Staff Comments

One unrelated staff comment concerns a changed administrative filing process with many new words.""",
    }

    normalized = normalize_filing(current)
    item_1b = next(block for block in normalized.blocks if block.text.startswith("Item 1B."))
    changed_comment = next(block for block in normalized.blocks if block.text.startswith("One unrelated"))
    assert item_1b.section_key == changed_comment.section_key == "item_1b"
    assert changed_comment.section_key != "risk_factors"

    result = compare_filings(prior, current)
    risk = _finding(result, "risk_factor_wording_change")
    assert risk.state.value == "clear"
    assert dict(risk.why_flagged)["changed_paragraph_count"] == "0"


def test_revenue_policy_scope_does_not_bleed_through_later_note_paragraphs() -> None:
    # SEC Inline XBRL often encodes subheadings as styled paragraphs.  The
    # corpus intentionally preserves a canonical section until it encounters
    # another known SEC heading, so generic section membership would wrongly
    # carry every later note paragraph into the revenue-policy detector.
    prior = {
        "accession": "0007-25-000001",
        "form": "10-K",
        "content_type": "html",
        "content": """<html><body>
<p>Revenue Recognition</p>
<p>We recognize revenue when control transfers to the customer.</p>
<p>Inventories</p>
<p>Inventory is carried at cost, and historical component availability was stable.</p>
</body></html>""",
    }
    current = {
        "accession": "0007-26-000001",
        "form": "10-K",
        "content_type": "html",
        "content": """<html><body>
<p>Revenue Recognition</p>
<p>We recognize revenue when control transfers to the customer.</p>
<p>Inventories</p>
<p>Inventory is subject to export controls, supplier disruption, obsolescence, and significant write-down risk.</p>
</body></html>""",
    }
    registry = load_disclosure_diff_registry()
    normalized = normalize_filing(prior, registry=registry)
    inventory = next(block for block in normalized.blocks if block.text == "Inventories")
    inventory_detail = next(block for block in normalized.blocks if block.text.startswith("Inventory is carried"))
    assert inventory.kind.value == "paragraph"
    assert inventory.section_key == inventory_detail.section_key == "revenue_recognition"

    scoped = disclosure_diff_module._revenue_policy_scope_blocks(
        normalized,
        registry.detector("revenue_recognition_policy_change"),
    )
    assert inventory.block_id not in {block.block_id for block in scoped}
    assert inventory_detail.block_id not in {block.block_id for block in scoped}

    result = compare_filings(prior, current, registry=registry)
    finding = _finding(result, "revenue_recognition_policy_change")
    assert finding.state.value == "clear"
    assert dict(finding.why_flagged)["changed_policy_block_count"] == "0"
    assert "policy_scope_uses_direct_rules_and_bounded_heading_neighbors" in finding.limitations


def test_source_body_is_off_by_default_and_opt_in_export_is_bounded() -> None:
    result = _comparison()
    default = result.to_dict()
    assert "source_text" not in default["prior_document"]
    bounded = result.to_dict(include_source_text=True, max_source_chars=17)
    assert len(bounded["prior_document"]["source_text"]) == 17
    assert bounded["prior_document"]["source_text_truncated"] is True
    prior, current = _documents()
    adapter_bounded = compare_filings(prior, current, include_source_text=True, max_source_chars=11)
    assert len(adapter_bounded.to_dict()["prior_document"]["source_text"]) == 11


def test_registry_has_machine_safe_bilingual_labels_and_no_runtime_network_input() -> None:
    registry = load_disclosure_diff_registry()
    assert registry.version == "filing-disclosure-diff/v1"
    assert all({"en", "zh-Hans"}.issubset(dict(item.labels)) for item in registry.sections)
    assert all({"en", "zh-Hans"}.issubset(dict(item.labels)) for item in registry.detectors)
    source = (ROOT / "engine" / "fundamental_forensics" / "disclosure_diff.py").read_text(encoding="utf-8")
    assert "requests.get(" not in source and "urlopen(" not in source
    lower = source.casefold()
    assert all(token not in lower for token in ("openai", "anthropic", "chatcompletion", "language model"))
