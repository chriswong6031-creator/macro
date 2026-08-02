"""Adversarial contract tests for the strict offline SEC filing parser."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import builtins
import re
import socket

import pytest

import collectors.sec_filing_parser as parser_module

from collectors.sec_filing_parser import (
    PARSER_LIMITS,
    SEC_FILING_PARSER_PROFILE,
    SEC_FILING_PARSER_SCHEMA,
    SEC_FILING_PARSER_VERSION,
    SUPPORTED_TRANSFORMS,
    SecFilingParseError,
    parse_sec_filing_document,
    validate_sec_filing_parse_result,
)


FIXTURES = Path(__file__).parent / "fixtures" / "sec_filings"
XBRLI = "http://www.xbrl.org/2003/instance"
IX = "http://www.xbrl.org/2013/inlineXBRL"
TRR3 = "http://www.xbrl.org/inlineXBRL/transformation/2015-02-26"
TRR4 = "http://www.xbrl.org/inlineXBRL/transformation/2020-02-12"


def _instance(body: str, *, resources: str | None = None) -> bytes:
    resource_xml = resources or """
      <xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
      <xbrli:unit id="u"><xbrli:measure>ex:USD</xbrli:measure></xbrli:unit>
    """
    return f'''<xbrli:xbrl xmlns:xbrli="{XBRLI}" xmlns:ex="urn:example">{resource_xml}{body}</xbrli:xbrl>'''.encode()


def _inline(body: str, *, continuations: str = "", resources: str | None = None) -> bytes:
    resource_xml = resources or f"""
      <xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
      <xbrli:unit id="u"><xbrli:measure>ex:USD</xbrli:measure></xbrli:unit>
    """
    # Keep all positive fixtures on the SEC-realistic Inline XBRL 1.1 path:
    # one header in the XHTML body, with resources as its direct child.
    # Negative tests below deliberately construct illegal placements.
    return f'''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:ix="{IX}" xmlns:xbrli="{XBRLI}" xmlns:ex="urn:example" xmlns:i3="{TRR3}" xmlns:i4="{TRR4}"><head></head><body><ix:header><ix:resources>{resource_xml}</ix:resources></ix:header>{body}{continuations}</body></html>'''.encode()


def test_public_contract_and_transform_registry_are_fixed():
    assert SEC_FILING_PARSER_SCHEMA == "fundamental_forensics.sec_filing_parser/v1"
    assert SEC_FILING_PARSER_PROFILE == "strict_offline_ixbrl/v1"
    assert SEC_FILING_PARSER_VERSION == "1"
    assert set(SUPPORTED_TRANSFORMS) == {
        f"{{{TRR3}}}numdotdecimal",
        f"{{{TRR3}}}numcommadecimal",
        f"{{{TRR3}}}zerodash",
        f"{{{TRR3}}}nocontent",
        f"{{{TRR4}}}num-dot-decimal",
        f"{{{TRR4}}}num-comma-decimal",
        f"{{{TRR4}}}fixed-zero",
        f"{{{TRR4}}}fixed-empty",
    }


def test_pure_instance_context_units_dimensions_and_exact_multibyte_spans():
    content = (FIXTURES / "minimal_instance.xml").read_bytes()
    result = parse_sec_filing_document(content, document_name="minimal_instance.xml")

    assert set(result) == {
        "schema", "parser", "source", "document", "contexts", "units",
        "continuations", "facts", "diagnostics", "coverage",
    }
    assert result["document"]["kind"] == "xbrl_instance"
    assert [context["period"]["kind"] for context in result["contexts"]] == ["instant", "duration"]
    assert result["contexts"][0]["dimensions"][0]["kind"] == "explicit"
    typed = result["contexts"][1]["dimensions"][0]
    assert typed["kind"] == "typed"
    assert typed["typed_value_xml"] == "<ex:Channel>Direct</ex:Channel>"
    assert result["units"][1]["denominator_measures"] == ["{https://example.test/taxonomy}shares"]
    label = next(fact for fact in result["facts"] if fact["concept_qname"].endswith("}Label"))
    assert label["normalized_value"] == "Café"
    text_span = label["text_spans"][0]
    assert content[text_span["start"] : text_span["end"]] == "Café".encode()
    assert label["source_span"]["start"] == content.index(b"<ex:Label")
    validate_sec_filing_parse_result(result, source_content=content)


def test_inline_hidden_exclude_scale_sign_nil_fraction_continuation_and_unknown_transform():
    content = (FIXTURES / "minimal_inline.xhtml").read_bytes()
    result = parse_sec_filing_document(content, document_name="minimal_inline.xhtml")
    facts = {fact["fact_id"]: fact for fact in result["facts"]}

    assert result["document"]["kind"] == "inline_xbrl"
    assert facts["scaled"]["raw_value"] == "1,234.5"
    assert facts["scaled"]["normalized_value"] == "-1234500"
    assert facts["scaled"]["hidden"] is True
    assert facts["scaled"]["excluded_text_spans"] == []
    assert facts["label"]["normalized_value"] == "Café"
    assert facts["nil"]["status"] == "nil"
    assert facts["ratio"]["fraction"] == {
        "numerator_raw": "1", "denominator_raw": "3",
        "numerator_normalized": "1", "denominator_normalized": "3",
    }
    assert facts["ratio"]["normalized_value"] is None
    assert facts["unknown"]["status"] == "unsupported_transform"
    assert facts["unknown"]["normalized_value"] is None
    assert result["coverage"]["canonical_value_complete"] is False
    assert result["diagnostics"] == [{
        "code": "unsupported_transform",
        "fact_start": facts["unknown"]["source_span"]["start"],
        "format": "{https://example.test/taxonomy}mystery",
    }]


@pytest.mark.parametrize(
    ("format_value", "raw", "normalized"),
    [
        ("i3:numdotdecimal", "1,234.50", "1234.5"),
        ("i3:numcommadecimal", "1.234,50", "1234.5"),
        ("i3:zerodash", "-", "0"),
        ("i4:num-dot-decimal", "2,500.25", "2500.25"),
        ("i4:num-comma-decimal", "2.500,25", "2500.25"),
        ("i4:fixed-zero", "", "0"),
    ],
)
def test_pinned_transform_vectors(format_value, raw, normalized):
    content = _inline(
        f'<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" format="{format_value}">{raw}</ix:nonFraction>'
    )
    fact = parse_sec_filing_document(content, document_name="transform.xhtml")["facts"][0]
    assert fact["normalized_value"] == normalized
    assert fact["status"] == "available"


@pytest.mark.parametrize(
    ("format_value", "raw", "normalized"),
    [
        ("i3:numdotdecimal", "1 234.50", "1234.5"),
        ("i3:numdotdecimal", "1\u00a0234.50", "1234.5"),
        ("i3:numcommadecimal", "1 234,50", "1234.5"),
        ("i3:numcommadecimal", "1\u00a0234,50", "1234.5"),
        ("i4:num-dot-decimal", ". 5", "0.5"),
        ("i4:num-comma-decimal", ", 5", "0.5"),
    ],
)
def test_registry_permitted_space_nbsp_and_missing_integer_vectors(
    format_value, raw, normalized
):
    content = _inline(
        f'<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" '
        f'format="{format_value}">{raw}</ix:nonFraction>'
    )
    fact = parse_sec_filing_document(content, document_name="registry-edge.xhtml")["facts"][0]
    assert fact["status"] == "available"
    assert fact["normalized_value"] == normalized


@pytest.mark.parametrize("format_value", ["i3:nocontent", "i4:fixed-empty"])
def test_pinned_nonnumeric_empty_transform_vectors(format_value):
    fact = parse_sec_filing_document(
        _inline(f'<ix:nonNumeric name="ex:F" contextRef="c" format="{format_value}">ignored</ix:nonNumeric>'),
        document_name="text-transform.xhtml",
    )["facts"][0]
    assert fact["transformed_value"] == ""
    assert fact["normalized_value"] == ""
    assert fact["status"] == "available"


def test_nested_inline_facts_are_each_preserved():
    content = _inline(
        '<ix:nonNumeric id="outer" name="ex:Outer" contextRef="c">before '
        '<ix:nonNumeric id="inner" name="ex:Inner" contextRef="c">inside</ix:nonNumeric> after</ix:nonNumeric>'
    )
    facts = parse_sec_filing_document(content, document_name="nested.xhtml")["facts"]
    assert [fact["fact_id"] for fact in facts] == ["outer", "inner"]
    assert facts[0]["raw_value"] == "before inside after"
    assert facts[1]["raw_value"] == "inside"


def test_forever_context_and_unknown_scenario_are_explicit_partial():
    resources = f'''<xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:forever /></xbrli:period><xbrli:scenario><ex:VendorExtension>opaque</ex:VendorExtension></xbrli:scenario></xbrli:context>'''
    result = parse_sec_filing_document(_instance("", resources=resources), document_name="partial.xml")
    assert result["contexts"][0]["period"]["kind"] == "forever"
    assert result["contexts"][0]["scenario_content_status"] == "partial"
    assert result["coverage"]["unknown_scenario_content_count"] == 1


@pytest.mark.parametrize(
    "payload,match",
    [
        (b'<!DOCTYPE r [<!ENTITY x "lol">]><r>&x;</r>', "DTD"),
        (b'<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>', "DTD"),
        (b'<r xmlns:xi="http://www.w3.org/2001/XInclude"><xi:include href="file:///etc/passwd"/></r>', "XInclude"),
        (b'<r><a></r>', "malformed"),
        (b'<r a="1" a="2"/>', "malformed"),
        (b'<r><p:x/></r>', "malformed"),
        (b'\xff\xfe<r/>', "UTF-8"),
        ('<?xml version="1.0" encoding="ISO-8859-1"?><r>Café</r>'.encode(), "UTF-8"),
        (b'<r>\x00</r>', "NUL"),
    ],
)
def test_unsafe_or_malformed_xml_is_rejected_without_recovery(payload, match):
    with pytest.raises(SecFilingParseError, match=match):
        parse_sec_filing_document(payload, document_name="unsafe.xml")


def test_qname_valued_attributes_must_be_bound():
    content = _inline('<ix:nonNumeric name="missing:Fact" contextRef="c">x</ix:nonNumeric>')
    with pytest.raises(SecFilingParseError, match="unbound QName"):
        parse_sec_filing_document(content, document_name="unbound.xhtml")


@pytest.mark.parametrize(
    ("body", "continuations", "match"),
    [
        ('<ix:nonNumeric name="ex:F" contextRef="c" continuedAt="missing">x</ix:nonNumeric>', "", "missing continuation"),
        ('<ix:nonNumeric name="ex:F" contextRef="c" continuedAt="a">x</ix:nonNumeric>', '<ix:continuation id="a" continuedAt="a">a</ix:continuation>', "cycle"),
        ('<ix:nonNumeric name="ex:F" contextRef="c" continuedAt="a">x</ix:nonNumeric><ix:nonNumeric name="ex:G" contextRef="c" continuedAt="a">y</ix:nonNumeric>', '<ix:continuation id="a">a</ix:continuation>', "shared"),
        ('<ix:nonNumeric name="ex:F" contextRef="c">x</ix:nonNumeric>', '<ix:continuation id="a">a</ix:continuation>', "orphan"),
        ('<ix:nonNumeric name="ex:F" contextRef="c" continuedAt="a">x</ix:nonNumeric>', '<ix:continuation id="a" continuedAt="missing">a</ix:continuation>', "missing continuation"),
        ('<ix:nonNumeric name="ex:F" contextRef="missing">x</ix:nonNumeric>', "", "missing context"),
        ('<ix:nonFraction name="ex:F" contextRef="c" unitRef="missing">1</ix:nonFraction>', "", "missing unit"),
    ],
)
def test_invalid_references_and_continuation_graphs_fail_closed(body, continuations, match):
    with pytest.raises(SecFilingParseError, match=match):
        parse_sec_filing_document(_inline(body, continuations=continuations), document_name="refs.xhtml")


def test_duplicate_context_unit_continuation_and_fact_ids_are_rejected():
    duplicate_context = _instance("", resources='''
      <xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period></xbrli:context>
      <xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period></xbrli:context>''')
    with pytest.raises(SecFilingParseError, match="duplicate context"):
        parse_sec_filing_document(duplicate_context, document_name="duplicate.xml")

    duplicate_unit = _instance("", resources='''
      <xbrli:unit id="u"><xbrli:measure>ex:USD</xbrli:measure></xbrli:unit>
      <xbrli:unit id="u"><xbrli:measure>ex:shares</xbrli:measure></xbrli:unit>''')
    with pytest.raises(SecFilingParseError, match="duplicate unit"):
        parse_sec_filing_document(duplicate_unit, document_name="duplicate-unit.xml")

    duplicate_continuation = _inline(
        '<ix:nonNumeric name="ex:F" contextRef="c" continuedAt="a">x</ix:nonNumeric>',
        continuations='<ix:continuation id="a">a</ix:continuation><ix:continuation id="a">b</ix:continuation>',
    )
    with pytest.raises(SecFilingParseError, match="duplicate"):
        parse_sec_filing_document(duplicate_continuation, document_name="duplicate.xhtml")

    content = _instance('<ex:F id="same" contextRef="c">x</ex:F><ex:G id="same" contextRef="c">y</ex:G>')
    # Expat does not type ID attributes without a DTD, so the independent result
    # validator is the final local-identity boundary.
    with pytest.raises(SecFilingParseError, match="duplicate fact"):
        parse_sec_filing_document(content, document_name="facts.xml")


@pytest.mark.parametrize(
    ("limit", "value", "content", "match"),
    [
        ("max_bytes", 10, b"<root>12345</root>", "byte limit"),
        ("max_nodes", 1, b"<root><child/></root>", "node limit"),
        ("max_depth", 1, b"<root><child/></root>", "depth limit"),
        ("max_attributes_per_element", 1, b'<root a="1" b="2"/>', "attribute limit"),
        ("max_total_attributes", 1, b'<root a="1"><child b="2"/></root>', "attribute limit"),
        ("max_text_bytes", 2, b"<root>abc</root>", "text limit"),
        ("max_contexts", 1, _instance("", resources='''<xbrli:context id="a"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period></xbrli:context><xbrli:context id="b"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period></xbrli:context>'''), "context limit"),
        ("max_units", 1, _instance("", resources='<xbrli:unit id="a"><xbrli:measure>ex:USD</xbrli:measure></xbrli:unit><xbrli:unit id="b"><xbrli:measure>ex:shares</xbrli:measure></xbrli:unit>'), "unit limit"),
        ("max_facts", 1, _instance('<ex:F contextRef="c">x</ex:F><ex:G contextRef="c">y</ex:G>'), "fact limit"),
        ("max_continuations", 1, _inline('<ix:nonNumeric name="ex:F" contextRef="c" continuedAt="a">x</ix:nonNumeric><ix:nonNumeric name="ex:G" contextRef="c" continuedAt="b">y</ix:nonNumeric>', continuations='<ix:continuation id="a">a</ix:continuation><ix:continuation id="b">b</ix:continuation>'), "continuation limit"),
        ("max_dimensions_per_context", 1, _instance("", resources='''<xbrli:context xmlns:xbrldi="http://xbrl.org/2006/xbrldi" id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="ex:A">ex:X</xbrldi:explicitMember><xbrldi:explicitMember dimension="ex:B">ex:Y</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period></xbrli:context>'''), "dimension limit"),
        ("max_abs_scale", 2, _inline('<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" scale="3">1</ix:nonFraction>'), "scale"),
        ("max_output_bytes", 16, b"<root/>", "output byte limit"),
    ],
)
def test_hard_caps_are_fail_closed(monkeypatch, limit, value, content, match):
    lowered = dict(PARSER_LIMITS)
    lowered[limit] = value
    monkeypatch.setattr(parser_module, "PARSER_LIMITS", lowered)
    with pytest.raises(SecFilingParseError, match=match):
        parse_sec_filing_document(content, document_name="cap.xml")


def test_continuation_chain_depth_cap(monkeypatch):
    lowered = dict(PARSER_LIMITS)
    lowered["max_continuation_chain"] = 1
    monkeypatch.setattr(parser_module, "PARSER_LIMITS", lowered)
    content = _inline(
        '<ix:nonNumeric name="ex:F" contextRef="c" continuedAt="a">x</ix:nonNumeric>',
        continuations='<ix:continuation id="a" continuedAt="b">a</ix:continuation><ix:continuation id="b">b</ix:continuation>',
    )
    with pytest.raises(SecFilingParseError, match="chain limit"):
        parse_sec_filing_document(content, document_name="deep.xhtml")


def test_validator_rejects_shape_order_reference_coverage_and_value_forgeries():
    content = _instance('<ex:F contextRef="c" unitRef="u" decimals="0">10</ex:F>')
    result = parse_sec_filing_document(content, document_name="canonical.xml")
    mutations = []
    extra = deepcopy(result); extra["invented"] = True; mutations.append(extra)
    order = deepcopy(result); order["facts"][0]["source_span"]["end"] = order["facts"][0]["source_span"]["start"]; mutations.append(order)
    reference = deepcopy(result); reference["facts"][0]["context_ref"] = "missing"; mutations.append(reference)
    coverage = deepcopy(result); coverage["coverage"]["fact_count"] = 99; mutations.append(coverage)
    value = deepcopy(result); value["facts"][0]["normalized_value"] = "11"; mutations.append(value)
    registry = deepcopy(result); registry["parser"]["transform_registry"].reverse(); mutations.append(registry)
    for forged in mutations:
        with pytest.raises(SecFilingParseError):
            validate_sec_filing_parse_result(forged)


def test_source_replay_rejects_canonical_result_forgery_and_wrong_bytes():
    content = _instance('<ex:F contextRef="c">truth</ex:F>')
    result = parse_sec_filing_document(content, document_name="replay.xml")
    forged = deepcopy(result)
    forged["facts"][0]["raw_value"] = "lie"
    forged["facts"][0]["transformed_value"] = "lie"
    forged["facts"][0]["normalized_value"] = "lie"
    # It is locally self-consistent, but exact-byte replay defeats the forgery.
    validate_sec_filing_parse_result(forged)
    with pytest.raises(SecFilingParseError, match="canonical source replay"):
        validate_sec_filing_parse_result(forged, source_content=content)
    with pytest.raises(SecFilingParseError, match="source witness"):
        validate_sec_filing_parse_result(result, source_content=content + b" ")


def test_parser_performs_no_open_or_socket_calls(monkeypatch):
    content = _instance('<ex:F contextRef="c">offline</ex:F>')

    def forbidden(*_args, **_kwargs):
        raise AssertionError("I/O attempted")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    result = parse_sec_filing_document(content, document_name="offline.xml")
    assert result["facts"][0]["normalized_value"] == "offline"


# ---------------------------------------------------------------------------
# Structural XBRL / Inline XBRL regressions.  These are intentionally not
# convenience-parser tests: a filing which cannot meet the narrow evidence
# contract must fail closed (or advertise incomplete coverage), not be
# accepted by descendant scans and labelled complete.


@pytest.mark.parametrize(
    "resources",
    [
        # entity and period must be direct, ordered children of context.
        '''<xbrli:context id="c"><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity></xbrli:context>''',
        '''<xbrli:context id="c"><ex:wrapper><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity></ex:wrapper><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>''',
        # identifier is direct to entity; a descendant search must not rescue it.
        '''<xbrli:context id="c"><xbrli:entity><ex:wrapper><xbrli:identifier scheme="s">1</xbrli:identifier></ex:wrapper></xbrli:entity><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>''',
        # scenario follows period and cannot be a nested surprise element.
        '''<xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:scenario/><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>''',
        '''<xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><ex:wrapper><xbrli:instant>2025-12-31</xbrli:instant></ex:wrapper></xbrli:period></xbrli:context>''',
        # Period content is an exact choice, with valid dates and chronology.
        '''<xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>not-a-date</xbrli:instant></xbrli:period></xbrli:context>''',
        '''<xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-12-31</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>''',
    ],
)
def test_context_grammar_is_direct_ordered_and_temporally_valid(resources):
    with pytest.raises(SecFilingParseError):
        parse_sec_filing_document(_instance("", resources=resources), document_name="bad-context.xml")


@pytest.mark.parametrize(
    "resources",
    [
        # A segment may only appear under entity, after the direct identifier.
        '''<xbrli:context id="c"><xbrli:entity><xbrli:segment/><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period></xbrli:context>''',
        # Typed dimensions carry exactly one element child and no free text.
        '''<xbrli:context xmlns:xbrldi="http://xbrl.org/2006/xbrldi" id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier><xbrli:segment><xbrldi:typedMember dimension="ex:A">stray<ex:One/><ex:Two/></xbrldi:typedMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period></xbrli:context>''',
    ],
)
def test_context_segment_and_dimension_grammar_is_not_descendant_based(resources):
    with pytest.raises(SecFilingParseError):
        parse_sec_filing_document(_instance("", resources=resources), document_name="bad-dimension.xml")


def test_nested_dimension_is_not_promoted_and_makes_its_container_partial():
    resources = '''<xbrli:context xmlns:xbrldi="http://xbrl.org/2006/xbrldi" id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier><xbrli:segment><ex:wrap><xbrldi:explicitMember dimension="ex:A">ex:M</xbrldi:explicitMember></ex:wrap></xbrli:segment></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period></xbrli:context>'''
    result = parse_sec_filing_document(
        _instance("", resources=resources), document_name="nested-dimension.xml"
    )
    context = result["contexts"][0]
    assert context["dimensions"] == []
    assert context["segment_content_status"] == "partial"
    assert result["coverage"]["unknown_segment_content_count"] == 1


def test_opaque_segment_and_scenario_content_is_explicitly_partial_not_complete():
    resources = '''
      <xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier><xbrli:segment><ex:OpaqueSegment>vendor data</ex:OpaqueSegment></xbrli:segment></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period><xbrli:scenario><ex:OpaqueScenario>vendor data</ex:OpaqueScenario></xbrli:scenario></xbrli:context>
    '''
    result = parse_sec_filing_document(_instance("", resources=resources), document_name="opaque-context.xml")
    context = result["contexts"][0]
    assert context["segment_content_status"] == "partial"
    assert context["scenario_content_status"] == "partial"
    assert result["coverage"]["unknown_segment_content_count"] == 1
    assert result["coverage"]["unknown_scenario_content_count"] == 1


@pytest.mark.parametrize(
    "unit_xml",
    [
        '<xbrli:unit id="u"><ex:wrapper><xbrli:measure>ex:USD</xbrli:measure></ex:wrapper></xbrli:unit>',
        '<xbrli:unit id="u"><xbrli:measure>ex:USD</xbrli:measure><xbrli:divide><xbrli:unitNumerator><xbrli:measure>ex:shares</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>ex:days</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>',
        '<xbrli:unit id="u"><xbrli:divide><xbrli:unitNumerator><ex:wrapper><xbrli:measure>ex:USD</xbrli:measure></ex:wrapper></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>ex:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>',
        '<xbrli:unit id="u"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>ex:USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>ex:USD</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>',
    ],
)
def test_unit_and_divide_grammar_is_exact_and_cannot_cancel_measures(unit_xml):
    with pytest.raises(SecFilingParseError):
        parse_sec_filing_document(_instance("", resources=unit_xml), document_name="bad-unit.xml")


@pytest.mark.parametrize(
    "lexical",
    ["ex:bad:name", "ex:bad!", ":Fact", "ex:"],
)
def test_qname_valued_fields_require_lexically_valid_single_colon_qnames(lexical):
    content = _inline(f'<ix:nonNumeric name="{lexical}" contextRef="c">x</ix:nonNumeric>')
    with pytest.raises(SecFilingParseError):
        parse_sec_filing_document(content, document_name="bad-qname.xhtml")


@pytest.mark.parametrize("bad_id", ["1starts-with-digit", "contains space", ""])
def test_local_xbrl_ids_are_xml_id_lexical_values_not_just_trimmed_text(bad_id):
    resources = f'''<xbrli:context id="{bad_id}"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period></xbrli:context>'''
    with pytest.raises(SecFilingParseError):
        parse_sec_filing_document(_instance("", resources=resources), document_name="bad-id.xml")


def test_mixed_inline_versions_and_invalid_header_resource_hidden_placement_fail_closed():
    mixed = f'''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:ix="{IX}" xmlns:old="http://www.xbrl.org/2008/inlineXBRL" xmlns:xbrli="{XBRLI}" xmlns:ex="urn:example"><head></head><body><ix:header><ix:resources><xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period></xbrli:context></ix:resources></ix:header><old:nonNumeric name="ex:F" contextRef="c">x</old:nonNumeric></body></html>'''.encode()
    resources_in_body = f'''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:ix="{IX}" xmlns:xbrli="{XBRLI}" xmlns:ex="urn:example"><head></head><body><ix:resources><xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period></xbrli:context></ix:resources><ix:nonNumeric name="ex:F" contextRef="c">x</ix:nonNumeric></body></html>'''.encode()
    hidden_in_body = _inline('<ix:hidden><ix:nonNumeric name="ex:F" contextRef="c">x</ix:nonNumeric></ix:hidden>')
    for content in (mixed, resources_in_body, hidden_in_body):
        with pytest.raises(SecFilingParseError):
            parse_sec_filing_document(content, document_name="bad-inline-placement.xhtml")


def test_inline_profile_requires_xhtml_root_and_rejects_unmodeled_ix_semantics():
    non_xhtml_root = _inline(
        '<ix:nonNumeric name="ex:F" contextRef="c">x</ix:nonNumeric>'
    ).replace(
        b'<html xmlns="http://www.w3.org/1999/xhtml"',
        b'<root xmlns="urn:not-xhtml"',
        1,
    ).replace(b"</html>", b"</root>", 1)
    unknown_ix = _inline(
        '<ix:mystery/><ix:nonNumeric name="ex:F" contextRef="c">x</ix:nonNumeric>'
    )
    misplaced_references = _inline(
        '<ix:references/><ix:nonNumeric name="ex:F" contextRef="c">x</ix:nonNumeric>'
    )

    for content in (non_xhtml_root, unknown_ix, misplaced_references):
        with pytest.raises(SecFilingParseError):
            parse_sec_filing_document(content, document_name="unsupported-inline.xhtml")


def test_native_negative_fact_is_canonical_but_inline_value_attributes_are_rejected():
    negative = _instance('<ex:F contextRef="c" unitRef="u" decimals="0">-1</ex:F>')
    result = parse_sec_filing_document(negative, document_name="native-negative.xml")
    assert result["facts"][0]["normalized_value"] == "-1"
    assert result["facts"][0]["status"] == "available"
    assert result["coverage"]["fact_inventory_complete"] is False

    for attrs in ('sign="-"', 'scale="3"', 'format="ex:made-up"'):
        transformed_native = _instance(f'<ex:F contextRef="c" unitRef="u" decimals="0" {attrs}>1</ex:F>')
        with pytest.raises(SecFilingParseError):
            parse_sec_filing_document(transformed_native, document_name="native-inline-attribute.xml")


def test_non_xbrl_xml_and_native_xbrl_do_not_overclaim_inventory_or_reference_coverage():
    other = parse_sec_filing_document(b"<root><child/></root>", document_name="other.xml")
    assert other["document"]["kind"] == "other_xml"
    assert other["coverage"]["fact_inventory_complete"] is False
    assert other["coverage"]["context_references_complete"] is False
    assert other["coverage"]["unit_references_complete"] is False
    assert other["coverage"]["taxonomy_validation_complete"] is False

    native = parse_sec_filing_document(_instance('<ex:Text contextRef="c">reported</ex:Text>'), document_name="native.xml")
    assert native["document"]["kind"] == "xbrl_instance"
    assert native["coverage"]["fact_inventory_complete"] is False
    assert native["coverage"]["taxonomy_validation_complete"] is False


@pytest.mark.parametrize("raw", ["1,2", "1,2,3", "1 2", "1\u00a02"])
def test_unformatted_inline_numeric_does_not_guess_grouping_or_whitespace(raw):
    fact = parse_sec_filing_document(
        _inline(f'<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0">{raw}</ix:nonFraction>'),
        document_name="identity-numeric.xhtml",
    )["facts"][0]
    assert fact["status"] == "invalid_value"
    assert fact["transformed_value"] is None
    assert fact["normalized_value"] is None


@pytest.mark.parametrize("raw", ["١٢٣", "１２３"])
def test_numeric_lexical_profiles_do_not_widen_ascii_digits(raw):
    fact = parse_sec_filing_document(
        _inline(
            f'<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0">'
            f"{raw}</ix:nonFraction>"
        ),
        document_name="unicode-digits.xhtml",
    )["facts"][0]
    assert fact["status"] == "invalid_value"
    assert fact["normalized_value"] is None


@pytest.mark.parametrize(
    ("format_value", "raw"),
    [
        ("i3:numdotdecimal", "12,34.5"),
        ("i3:numdotdecimal", "1,234,56.7"),
        ("i3:numcommadecimal", "12.34,5"),
        ("i4:num-dot-decimal", "1.234,5"),
        ("i4:num-comma-decimal", "1,234.5"),
        ("i4:num-dot-decimal", "1\u202f234.5"),
        ("i4:num-comma-decimal", "1\u202f234,5"),
    ],
)
def test_numeric_transform_grouping_and_decimal_separators_are_not_guessed(format_value, raw):
    fact = parse_sec_filing_document(
        _inline(f'<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" format="{format_value}">{raw}</ix:nonFraction>'),
        document_name="bad-transform.xhtml",
    )["facts"][0]
    assert fact["status"] == "invalid_value"
    assert fact["normalized_value"] is None


@pytest.mark.parametrize("format_value", ["i3:nocontent", "i4:fixed-empty"])
def test_string_empty_transforms_never_release_a_numeric_fact_without_a_value(format_value):
    fact = parse_sec_filing_document(
        _inline(
            f'<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" '
            f'format="{format_value}">ignored</ix:nonFraction>'
        ),
        document_name="numeric-empty-transform.xhtml",
    )["facts"][0]
    assert fact["status"] == "invalid_value"
    assert fact["transformed_value"] is None
    assert fact["normalized_value"] is None


@pytest.mark.parametrize("raw", ["", "\u2212", "not-a-dash"])
def test_trr3_zerodash_is_the_exact_registry_dash_set(raw):
    fact = parse_sec_filing_document(
        _inline(f'<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" format="i3:zerodash">{raw}</ix:nonFraction>'),
        document_name="bad-zerodash.xhtml",
    )["facts"][0]
    assert fact["status"] == "invalid_value"
    assert fact["normalized_value"] is None


def test_trr3_zerodash_accepts_figure_dash_and_fixed_transforms_accept_any_text():
    figure_dash = parse_sec_filing_document(
        _inline('<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" format="i3:zerodash">‒</ix:nonFraction>'),
        document_name="figure-dash.xhtml",
    )["facts"][0]
    assert figure_dash["normalized_value"] == "0"

    zero = parse_sec_filing_document(
        _inline('<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" format="i4:fixed-zero">anything at all</ix:nonFraction>'),
        document_name="fixed-zero.xhtml",
    )["facts"][0]
    empty = parse_sec_filing_document(
        _inline('<ix:nonNumeric name="ex:F" contextRef="c" format="i4:fixed-empty">anything at all</ix:nonNumeric>'),
        document_name="fixed-empty.xhtml",
    )["facts"][0]
    no_content = parse_sec_filing_document(
        _inline('<ix:nonNumeric name="ex:F" contextRef="c" format="i3:nocontent">anything at all</ix:nonNumeric>'),
        document_name="no-content.xhtml",
    )["facts"][0]
    assert zero["normalized_value"] == "0"
    assert empty["normalized_value"] == ""
    assert no_content["normalized_value"] == ""


def test_inline_sign_is_only_negative_not_plus():
    content = _inline('<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" sign="+">1</ix:nonFraction>')
    with pytest.raises(SecFilingParseError):
        parse_sec_filing_document(content, document_name="plus-sign.xhtml")


@pytest.mark.parametrize(
    "body,continuations",
    [
        ('<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" continuedAt="a">1</ix:nonFraction>', '<ix:continuation id="a">x</ix:continuation>'),
        ('<ix:fraction name="ex:F" contextRef="c" unitRef="u" continuedAt="a"><ix:numerator>1</ix:numerator><ix:denominator>2</ix:denominator></ix:fraction>', '<ix:continuation id="a">x</ix:continuation>'),
        ('<ix:nonNumeric name="ex:F" contextRef="c" continuedAt="a">x</ix:nonNumeric>', '<ix:hidden><ix:continuation id="a">x</ix:continuation></ix:hidden>'),
    ],
)
def test_only_nonnumeric_facts_can_continue_and_continuations_cannot_be_hidden(body, continuations):
    with pytest.raises(SecFilingParseError):
        parse_sec_filing_document(_inline(body, continuations=continuations), document_name="bad-continuation.xhtml")


def test_exclude_is_owner_relative_so_a_nested_fact_retains_its_own_text():
    content = _inline(
        '<ix:nonNumeric id="outer" name="ex:Outer" contextRef="c">before '
        '<ix:exclude>drop <ix:nonNumeric id="inner" name="ex:Inner" contextRef="c">inner</ix:nonNumeric></ix:exclude>'
        ' after</ix:nonNumeric>'
    )
    facts = {fact["fact_id"]: fact for fact in parse_sec_filing_document(content, document_name="owner-exclude.xhtml")["facts"]}
    assert facts["outer"]["raw_value"] == "before  after"
    assert facts["inner"]["raw_value"] == "inner"


@pytest.mark.parametrize(
    "body",
    [
        '<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" xsi:nil="true">1</ix:nonFraction>',
        '<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" xsi:nil="true"/>',
        '<ix:nonFraction name="ex:F" contextRef="c" unitRef="u">1</ix:nonFraction>',
        '<ix:nonNumeric name="ex:F" contextRef="c" decimals="0">text</ix:nonNumeric>',
        '<ix:nonNumeric name="ex:F" contextRef="c" unitRef="u">text</ix:nonNumeric>',
        '<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" precision="0">1</ix:nonFraction>',
    ],
)
def test_nil_accuracy_and_nonnumeric_attribute_combinations_fail_closed(body):
    content = _inline(
        body,
        resources=f'''<xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context><xbrli:unit id="u"><xbrli:measure>ex:USD</xbrli:measure></xbrli:unit>''',
    )
    # Add xsi only to this intentionally local helper construction.
    content = content.replace(b'xmlns:i4=', b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:i4=', 1)
    with pytest.raises(SecFilingParseError):
        parse_sec_filing_document(content, document_name="bad-nil.xhtml")


@pytest.mark.parametrize("parent_attrs", [' format="i3:numdotdecimal"', ' scale="2"', ' sign="-"'])
def test_fraction_level_numeric_attributes_are_not_silently_applied(parent_attrs):
    body = f'<ix:fraction name="ex:F" contextRef="c" unitRef="u"{parent_attrs}><ix:numerator>1</ix:numerator><ix:denominator>2</ix:denominator></ix:fraction>'
    with pytest.raises(SecFilingParseError):
        parse_sec_filing_document(_inline(body), document_name="bad-fraction.xhtml")


def test_fraction_component_transforms_are_explicitly_rejected_until_they_have_a_canonical_contract():
    content = _inline(
        '<ix:fraction id="f" name="ex:F" contextRef="c" unitRef="u">'
        '<ix:numerator format="i3:numdotdecimal" scale="2" sign="-">1,234</ix:numerator>'
        '<ix:denominator format="i4:num-dot-decimal">2</ix:denominator>'
        '</ix:fraction>'
    )
    # A profile may later add component-level transform support, but it must
    # do so as a separately specified wire contract.  Silently treating these
    # values as identity numerics is worse than rejecting the member.
    with pytest.raises(SecFilingParseError):
        parse_sec_filing_document(content, document_name="fraction-components.xhtml")


def test_validator_rejects_forged_sign_accuracy_and_numeric_status_combinations():
    content = _inline('<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0">1</ix:nonFraction>')
    canonical = parse_sec_filing_document(content, document_name="validator-value.xhtml")
    forged_sign = deepcopy(canonical)
    forged_sign["facts"][0].update({"sign": "x", "status": "invalid_value", "transformed_value": None, "normalized_value": None})
    forged_accuracy = deepcopy(canonical)
    forged_accuracy["facts"][0]["precision"] = "0"
    forged_value = deepcopy(canonical)
    forged_value["facts"][0].update({"raw_value": "1,2", "transformed_value": "12", "normalized_value": "12"})
    for forged in (forged_sign, forged_accuracy, forged_value):
        with pytest.raises(SecFilingParseError):
            validate_sec_filing_parse_result(forged)


def test_validation_separates_observed_runtime_patch_provenance_from_semantic_fingerprint():
    content = _instance('<ex:F contextRef="c" unitRef="u" decimals="0">1</ex:F>')
    canonical = parse_sec_filing_document(content, document_name="runtime-provenance.xml")
    assert re.fullmatch(r"[a-f0-9]{64}", canonical["parser"]["algorithm_fingerprint"])

    observed_runtime_drift = deepcopy(canonical)
    observed_runtime_drift["parser"]["library_version"] = "python-99.99.99"
    observed_runtime_drift["parser"]["xml_library_version"] = "expat_99.99.99"
    # These fields identify the observed local runtime only.  They are useful
    # provenance, but cannot redefine the deterministic parser contract.
    validate_sec_filing_parse_result(observed_runtime_drift)
    validate_sec_filing_parse_result(observed_runtime_drift, source_content=content)

    semantic_drift = deepcopy(canonical)
    semantic_drift["parser"]["algorithm_fingerprint"] = "0" * 64
    with pytest.raises(SecFilingParseError):
        validate_sec_filing_parse_result(semantic_drift)
    with pytest.raises(SecFilingParseError):
        validate_sec_filing_parse_result(semantic_drift, source_content=content)


def test_namespace_declarations_count_against_attribute_admission_caps(monkeypatch):
    lowered = dict(PARSER_LIMITS)
    lowered["max_attributes_per_element"] = 32
    lowered["max_total_attributes"] = 32
    monkeypatch.setattr(parser_module, "PARSER_LIMITS", lowered)
    namespaces = " ".join(f'xmlns:p{index}="urn:example:{index}"' for index in range(100))
    with pytest.raises(SecFilingParseError, match="attribute|namespace declaration"):
        parse_sec_filing_document(f"<root {namespaces}/>".encode(), document_name="namespace-cap.xml")


def test_declared_text_event_cap_is_fail_closed(monkeypatch):
    if "max_text_events" not in PARSER_LIMITS:
        pytest.skip("text event count is not part of the public parser admission profile")
    lowered = dict(PARSER_LIMITS)
    lowered["max_text_events"] = 2
    monkeypatch.setattr(parser_module, "PARSER_LIMITS", lowered)
    with pytest.raises(SecFilingParseError, match="text event"):
        parse_sec_filing_document(b"<root>a<child/>b<child/>c</root>", document_name="text-event-cap.xml")


def test_header_uses_the_ixbrl11_body_placement_and_ordered_direct_content_model():
    fact = '<ix:nonNumeric name="ex:F" contextRef="c">x</ix:nonNumeric>'
    header_in_head = _inline(fact).replace(
        b"<head></head><body><ix:header>", b"<head><ix:header>", 1
    ).replace(b"</ix:header><ix:nonNumeric", b"</ix:header></head><body><ix:nonNumeric", 1)
    duplicate_hidden = _inline(fact).replace(
        b"<ix:header><ix:resources>",
        b'<ix:header><ix:hidden><ix:nonNumeric name="ex:H" contextRef="c">one</ix:nonNumeric></ix:hidden>'
        b'<ix:hidden><ix:nonNumeric name="ex:I" contextRef="c">two</ix:nonNumeric></ix:hidden><ix:resources>',
        1,
    )
    duplicate_resources = _inline(fact).replace(
        b"<ix:header><ix:resources>", b"<ix:header><ix:resources></ix:resources><ix:resources>", 1
    )
    resources_before_hidden = _inline(fact).replace(
        b"</ix:resources></ix:header>",
        b'</ix:resources><ix:hidden><ix:nonNumeric name="ex:H" contextRef="c">h</ix:nonNumeric></ix:hidden></ix:header>',
        1,
    )
    for index, content in enumerate((header_in_head, duplicate_hidden, duplicate_resources, resources_before_hidden)):
        with pytest.raises(SecFilingParseError):
            parse_sec_filing_document(content, document_name=f"bad-header-{index}.xhtml")


@pytest.mark.parametrize(
    "body",
    [
        '<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0">1<ix:nonFraction name="ex:G" contextRef="c" unitRef="u" decimals="0">2</ix:nonFraction></ix:nonFraction>',
        '<ix:fraction name="ex:F" contextRef="c" unitRef="u"><ix:numerator><ix:nonFraction name="ex:G" contextRef="c" unitRef="u" decimals="0">1</ix:nonFraction></ix:numerator><ix:denominator>2</ix:denominator></ix:fraction>',
        '<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0">1<b xmlns="http://www.w3.org/1999/xhtml">2</b></ix:nonFraction>',
    ],
)
def test_numeric_facts_do_not_concatenate_nested_fact_or_foreign_markup_values(body):
    with pytest.raises(SecFilingParseError, match="nested|child elements"):
        parse_sec_filing_document(_inline(body), document_name="nested-numeric.xhtml")


def test_exclude_is_limited_to_nonnumeric_and_continuation_owners():
    fact = '<ix:nonNumeric id="f" name="ex:F" contextRef="c" continuedAt="a">A</ix:nonNumeric>'
    continuation = '<ix:continuation id="a">B<ix:exclude>drop</ix:exclude>C</ix:continuation>'
    content = _inline(fact, continuations=continuation)
    result = parse_sec_filing_document(content, document_name="continuation-exclude.xhtml")
    parsed = result["facts"][0]
    assert parsed["raw_value"] == "ABC"
    excluded = parsed["excluded_text_spans"]
    assert len(excluded) == 1
    assert b"".join(content[span["start"] : span["end"]] for span in excluded) == b"drop"

    invalid = (
        '<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0">1<ix:exclude>x</ix:exclude></ix:nonFraction>',
        '<ix:fraction name="ex:F" contextRef="c" unitRef="u"><ix:numerator>1<ix:exclude>x</ix:exclude></ix:numerator><ix:denominator>2</ix:denominator></ix:fraction>',
        '<ix:exclude>x</ix:exclude>',
    )
    for index, body in enumerate(invalid):
        with pytest.raises(SecFilingParseError, match="exclude"):
            parse_sec_filing_document(_inline(body), document_name=f"invalid-exclude-{index}.xhtml")


def test_inline_document_id_namespace_covers_context_unit_fact_continuation_and_markup():
    duplicate_context_unit = _inline(
        '<ix:nonNumeric name="ex:F" contextRef="c">x</ix:nonNumeric>',
        resources='''<xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:forever/></xbrli:period></xbrli:context><xbrli:unit id="c"><xbrli:measure>ex:USD</xbrli:measure></xbrli:unit>''',
    )
    duplicate_fact_continuation = _inline(
        '<ix:nonNumeric id="dup" name="ex:F" contextRef="c" continuedAt="dup">x</ix:nonNumeric>',
        continuations='<ix:continuation id="dup">y</ix:continuation>',
    )
    duplicate_markup_context = _inline('<div id="c">presentation</div><ix:nonNumeric name="ex:F" contextRef="c">x</ix:nonNumeric>')
    for index, content in enumerate((duplicate_context_unit, duplicate_fact_continuation, duplicate_markup_context)):
        with pytest.raises(SecFilingParseError, match="duplicate"):
            parse_sec_filing_document(content, document_name=f"duplicate-global-id-{index}.xhtml")


def test_continuation_preceding_fact_preserves_logical_value_and_witness_order():
    fact = '<ix:nonNumeric id="f" name="ex:F" contextRef="c" continuedAt="a">A</ix:nonNumeric>'
    continuation = '<ix:continuation id="a">B<ix:exclude>X</ix:exclude>C</ix:continuation>'
    content = _inline(fact, continuations=continuation).replace(
        (fact + continuation).encode(), (continuation + fact).encode(), 1
    )
    result = parse_sec_filing_document(content, document_name="continuation-before-fact.xhtml")
    parsed = result["facts"][0]
    assert parsed["raw_value"] == "ABC"
    assert "".join(content[span["start"] : span["end"]].decode() for span in parsed["text_spans"]) == "ABC"
    assert "".join(content[span["start"] : span["end"]].decode() for span in parsed["excluded_text_spans"]) == "X"
    validate_sec_filing_parse_result(result)


def test_continuation_chain_cannot_nest_an_owner_or_link_inside_another_link():
    content = _inline(
        '<ix:nonNumeric name="ex:F" contextRef="c" continuedAt="a">A<ix:continuation id="a">B</ix:continuation></ix:nonNumeric>'
    )
    with pytest.raises(SecFilingParseError, match="ancestor/descendant"):
        parse_sec_filing_document(content, document_name="nested-continuation.xhtml")


@pytest.mark.parametrize("attribute", ["precision", "scale"])
def test_huge_numeric_control_lexicals_fail_closed_without_runtime_integer_leaks(attribute):
    value = "9" * 5000
    content = _inline(
        f'<ix:nonFraction name="ex:F" contextRef="c" unitRef="u" decimals="0" {attribute}="{value}">1</ix:nonFraction>'
    )
    with pytest.raises(SecFilingParseError):
        parse_sec_filing_document(content, document_name=f"huge-{attribute}.xhtml")


def test_validator_replays_accuracy_nil_and_identity_invariants_without_source_bytes():
    numeric = parse_sec_filing_document(
        _inline('<ix:nonFraction id="f" name="ex:F" contextRef="c" unitRef="u" decimals="0">1</ix:nonFraction>'),
        document_name="validator-controls.xhtml",
    )
    nil = parse_sec_filing_document(
        _inline('<ix:nonFraction id="n" name="ex:F" contextRef="c" unitRef="u" xsi:nil="true"/>').replace(
            b"xmlns:i4=", b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:i4=', 1
        ),
        document_name="validator-nil.xhtml",
    )
    bad_decimals = deepcopy(numeric); bad_decimals["facts"][0]["decimals"] = "oops"
    bad_precision = deepcopy(numeric); bad_precision["facts"][0]["decimals"] = None; bad_precision["facts"][0]["precision"] = "0"
    bad_nil = deepcopy(nil); bad_nil["facts"][0]["raw_value"] = "smuggled"
    bad_root = deepcopy(numeric); bad_root["document"]["root_qname"] = "{urn:fake}root"
    for forged in (bad_decimals, bad_precision, bad_nil, bad_root):
        with pytest.raises(SecFilingParseError):
            validate_sec_filing_parse_result(forged)
