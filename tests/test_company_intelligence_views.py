from __future__ import annotations

import pytest

from engine.company_intelligence.contracts import ContractError
from engine.company_intelligence.views import build_bundle, build_company_contexts
from scripts.build_company_intelligence import _quarantine_invalid_history


def _row(*, quarter: int, call_date: str, sentiment: float, tags: str, updated_at: str = "2026-02-01T00:00:00Z", **extra):
    return {
        "document_ticker": "AAPL",
        "fiscal_year": 2026,
        "fiscal_quarter": quarter,
        "call_date": call_date,
        "updated_at": updated_at,
        "earnings_call_sent": sentiment,
        "earnings_call_perf": sentiment / 2,
        "management_confidence_score": sentiment + 0.1,
        "earnings_call_combined": sentiment / 3,
        "level1_tags": tags,
        "positive_highlights": "demand held; services grew; ignored fourth",
        "negative_highlights": "fx headwind",
        "raw_source_url": "https://example.test/document",
        **extra,
    }


def _tx(*quarters: int) -> dict:
    return {
        "schema": "mastermind.tx-index/v1",
        "generation_id": "t" * 24,
        "documents": [
            {"ticker": "AAPL", "fiscal_year": 2026, "fiscal_quarter": quarter, "present": True, "source_hash": f"hash-{quarter}"}
            for quarter in quarters
        ],
    }


def test_dedupe_correction_keeps_stable_event_and_newest_row() -> None:
    old = _row(quarter=1, call_date="2026-01-29", sentiment=0.2, tags="iphone", updated_at="2026-01-30T00:00:00Z", summary="old")
    corrected = _row(quarter=1, call_date="2026-01-29", sentiment=0.6, tags="iphone", updated_at="2026-02-01T00:00:00Z", summary="corrected")
    context = build_company_contexts([old, corrected], tx_index=_tx(1), as_of="2026-02-02")["AAPL"]
    assert len(context["history"]) == 1
    assert context["latest_event"]["summary"] == "corrected"
    assert context["latest_event_id"] == context["history"][0]["event_id"]


def test_date_correction_revises_the_same_fiscal_event_deterministically() -> None:
    old = _row(quarter=1, call_date="2026-01-29", sentiment=0.2, tags="iphone", updated_at="2026-01-30T00:00:00Z", summary="old")
    corrected = _row(quarter=1, call_date="2026-01-30", sentiment=0.6, tags="iphone", updated_at="2026-02-01T00:00:00Z", summary="corrected")
    first = build_company_contexts([old, corrected], tx_index=_tx(1), as_of="2026-02-02")["AAPL"]
    second = build_company_contexts([corrected, old], tx_index=_tx(1), as_of="2026-02-02")["AAPL"]
    assert len(first["history"]) == 1
    assert first["latest_event"]["call_date"] == "2026-01-30"
    assert first == second


def test_score_overlay_is_exact_period_only_and_cannot_replace_history() -> None:
    history = _row(quarter=1, call_date="2026-01-29", sentiment=0.2, tags="iphone", summary="source summary")
    score = {"ticker": "AAPL", "year": 2026, "quarter": "Q1", "sentiment": 0.9, "summary": "degraded score row", "tags": "services"}
    unmatched = {"ticker": "AAPL", "year": 2026, "quarter": "Q2", "sentiment": 0.1}
    context = build_company_contexts([history], [score, unmatched], tx_index=_tx(1), as_of="2026-02-02")["AAPL"]
    event = context["latest_event"]
    assert event["metrics"]["sentiment"] == 0.9
    assert event["summary"] == "source summary"
    assert event["tags"] == ["iphone", "services"]
    assert len(event["sources"]) == 3
    assert event["field_lineage"]["summary"] == "earnings_history"
    assert event["field_lineage"]["metrics"]["sentiment"] == "score_overlay"
    assert event["field_lineage"]["tags"] == {"iphone": "earnings_history", "services": "score_overlay"}
    assert event["field_lineage"]["positive_highlights"] == ["earnings_history"] * len(event["positive_highlights"])


def test_actual_history_metric_aliases_keep_percentage_units_and_overlay_summary() -> None:
    history = _row(
        quarter=1,
        call_date="2026-01-29",
        sentiment=0.2,
        tags="iphone",
        summary=None,
        call_positivity_score=0.61,
        management_confidence_score=0.72,
        analyst_criticism_score=0.11,
        future_outlook_score=0.48,
        revenue_growth=8.0,
        eps_growth=12.5,
        gross_margin=38.7,
    )
    score = {"ticker": "AAPL", "year": 2026, "quarter": 1, "summary": "score-authored summary"}
    event = build_company_contexts([history], [score], tx_index=_tx(1), as_of="2026-02-02")["AAPL"]["latest_event"]
    assert event["summary"] == "score-authored summary"
    assert event["metrics"] == {
        "sentiment": 0.2, "performance": 0.1, "confidence": 0.72, "combined": 0.06666666666666667,
        "call_positivity": 0.61, "management_confidence": 0.72, "analyst_criticism": 0.11,
        "future_outlook": 0.48, "revenue_growth_pct": 8, "eps_growth_pct": 12.5,
        "gross_margin_pct": 38.7, "analysts_count": None, "questions_count": None,
    }


def test_multiline_highlights_preserve_commas_and_strip_number_prefixes() -> None:
    row = _row(
        quarter=1,
        call_date="2026-01-29",
        sentiment=0.2,
        tags="iphone",
        positive_highlights="1. Demand rose for iPhone, Mac, and iPad.\n2. Services reached a record.",
        negative_highlights="1. FX, memory, and freight pressured margin.\n2. Supply stayed tight.",
    )
    event = build_company_contexts([row], tx_index=_tx(1), as_of="2026-02-02")["AAPL"]["latest_event"]
    assert event["positive_highlights"] == ["Demand rose for iPhone, Mac, and iPad.", "Services reached a record."]
    assert event["negative_highlights"] == ["FX, memory, and freight pressured margin.", "Supply stayed tight."]


def test_score_only_ticker_is_explicitly_not_covered_not_a_synthetic_event() -> None:
    score = {"ticker": "MSFT", "year": 2026, "quarter": "Q1", "sentiment": 0.9}
    context = build_company_contexts([], [score], tx_index=_tx(), as_of="2026-02-02")["MSFT"]
    assert context["status"] == "not_covered"
    assert context["history"] == [] and context["latest_event"] is None
    assert context["source_completeness"]["earnings_history"]["status"] == "missing"


def test_previous_event_deltas_and_topic_lifecycle_are_explicit() -> None:
    q1 = _row(quarter=1, call_date="2026-01-29", sentiment=0.2, tags="iphone, margins")
    q2 = _row(quarter=2, call_date="2026-04-29", sentiment=0.5, tags="iphone, services")
    context = build_company_contexts([q1, q2], tx_index=_tx(1, 2), as_of="2026-05-01")["AAPL"]
    latest = context["latest_event"]
    assert latest["previous_event_deltas"]["sentiment"] == 0.3
    assert context["topics"]["added"] == ["services"]
    assert context["topics"]["dropped"] == ["margins"]
    assert context["topics"]["persistent"] == ["iphone"]


def test_transcript_presence_is_document_level_not_claim_span() -> None:
    row = _row(quarter=1, call_date="2026-01-29", sentiment=0.2, tags="iphone")
    present = build_company_contexts([row], tx_index=_tx(1), as_of="2026-02-02")["AAPL"]["latest_event"]
    transcript = present["sources"][-1]
    assert transcript["status"] == "present"
    assert transcript["citation_precision"] == "document"
    assert transcript["url"] == "/data/tx/AAPL/2026Q1.json.gz"
    assert present["claim_citations_pending"] is True
    missing = build_company_contexts([row], tx_index=_tx(), as_of="2026-02-02")["AAPL"]["latest_event"]
    assert missing["sources"][-1]["status"] == "missing"


def test_production_terminal_symbols_index_marks_document_presence() -> None:
    row = _row(quarter=1, call_date="2026-01-29", sentiment=0.2, tags="iphone")
    production_index = {
        "schema": "mastermind.tx-index/v1",
        "generated_at": "2026-02-02T00:00:00Z",
        "symbols": {"AAPL": ["2026Q1", "bad-period"], "../NO": ["2026Q1"]},
    }
    context = build_company_contexts([row], tx_index=production_index, as_of="2026-02-02")["AAPL"]
    transcript = context["latest_event"]["sources"][-1]
    assert transcript["status"] == "present"
    assert transcript["url"] == "/data/tx/AAPL/2026Q1.json.gz"
    tx_lineage = context["transport_lineage"]["tx_index"]
    assert len(tx_lineage["generation_id"]) == 24
    assert set(tx_lineage["generation_id"]) <= set("0123456789abcdef")


def test_real_manifest_built_and_unversioned_tx_index_have_stable_lineage() -> None:
    row = _row(quarter=1, call_date="2026-01-29", sentiment=0.2, tags="iphone", exchange="NASDAQ")
    earnings_manifest = {"schema": "earnings_intelligence_manifest.v3", "built": "2026-02-02T01:02:03Z"}
    tx = {"schema": "mastermind.tx-index/v1", "generated_at": "2026-02-02T01:02:03Z", "symbols": {"AAPL": ["2026Q1"]}}
    context = build_company_contexts([row], tx_index=tx, earnings_manifest=earnings_manifest, as_of="2026-02-02")["AAPL"]
    assert context["company"]["exchange"] is None
    assert context["generated_at"] == "2026-02-02T01:02:03Z"
    assert len(context["transport_lineage"]["earnings_manifest"]["generation_id"]) == 24
    assert len(context["transport_lineage"]["tx_index"]["generation_id"]) == 24


def test_metadata_only_history_and_stale_state_are_honest() -> None:
    row = _row(quarter=1, call_date="2025-01-29", sentiment=0.2, tags="iphone")
    row.pop("raw_source_url")
    context = build_company_contexts([row], tx_index=_tx(), as_of="2026-08-01")["AAPL"]
    assert context["status"] == "stale"
    assert context["source_completeness"]["earnings_history"]["status"] == "metadata_only"
    assert "earnings_history_raw_source" in context["missing_sources"]


def test_emitted_source_and_display_fields_obey_terminal_bounds() -> None:
    row = _row(
        quarter=1,
        call_date="2026-01-29",
        sentiment=0.2,
        tags="x" * 400,
        raw_source_url="http://unsafe.example/document",
        company_name="A" * 400,
        source_record_id="r" * 400,
        source_sha256="not-a-sha",
    )
    context = build_company_contexts([row], tx_index=_tx(), as_of="2026-02-02")["AAPL"]
    source = context["latest_event"]["sources"][0]
    assert context["company"]["display_name"] == "A" * 240
    assert source["status"] == "metadata_only" and source["url"] is None
    assert source["receipt"]["record_id"] == "r" * 160
    assert "source_hash" not in source["receipt"]
    assert len(context["latest_event"]["tags"][0]) <= 96


def test_leading_punctuation_topic_tags_are_normalized_without_rejecting_generation() -> None:
    row = _row(
        quarter=1,
        call_date="2026-01-29",
        sentiment=0.2,
        tags=".com, -pricing, _web_update",
    )
    context = build_company_contexts([row], tx_index=_tx(), as_of="2026-02-02")["AAPL"]
    assert context["latest_event"]["tags"] == ["com", "pricing", "web_update"]


def test_same_inputs_produce_same_generation_and_context_bytes() -> None:
    rows = [_row(quarter=1, call_date="2026-01-29", sentiment=0.2, tags="iphone")]
    first_contexts, first_manifest = build_bundle(rows, tx_index=_tx(1), as_of="2026-02-02")
    second_contexts, second_manifest = build_bundle(rows, tx_index=_tx(1), as_of="2026-02-02")
    assert first_manifest["generation_id"] == second_manifest["generation_id"]
    assert first_contexts == second_contexts


def test_operational_metadata_is_generation_addressed_and_cannot_mutate_after_id(tmp_path) -> None:
    rows = [_row(quarter=1, call_date="2026-01-29", sentiment=0.2, tags="iphone")]
    contexts, baseline = build_bundle(rows, tx_index=_tx(1), as_of="2026-02-02")
    _, warned = build_bundle(rows, tx_index=_tx(1), as_of="2026-02-02", operational_warnings=["upstream_timeout"])
    _, rejected = build_bundle(rows, tx_index=_tx(1), as_of="2026-02-02", history_rows_rejected=1)
    assert len({baseline["generation_id"], warned["generation_id"], rejected["generation_id"]}) == 3
    baseline["warnings"] = ["illegal_post_id_mutation"]
    from engine.company_intelligence.views import write_generation
    with pytest.raises(ContractError, match="warnings invalid|immutable semantic content"):
        write_generation(tmp_path, contexts, baseline)


def test_completeness_counts_only_the_returned_history_cap() -> None:
    rows = [
        _row(quarter=quarter, call_date=f"202{quarter}-01-29", sentiment=0.2, tags="iphone")
        for quarter in (1, 2, 3, 4)
    ]
    # Distinguish fiscal years to avoid each quarter becoming four rows from the
    # same year in this compact fixture.
    for index, row in enumerate(rows):
        row["fiscal_year"] = 2023 + index
    scores = [{"ticker": "AAPL", "year": row["fiscal_year"], "quarter": row["fiscal_quarter"], "sentiment": 0.5} for row in rows]
    context = build_company_contexts(rows, scores, tx_index=_tx(1, 2, 3, 4), as_of="2026-02-02", max_history=2)["AAPL"]
    assert len(context["history"]) == 2
    assert context["source_completeness"]["earnings_history"]["event_count"] == 2
    assert context["source_completeness"]["score_overlay"] == {"status": "metadata_only", "event_count": 2}
    assert context["source_completeness"]["transcripts"]["event_count"] <= 2


@pytest.mark.parametrize("field,value", [("fiscal_quarter", 5), ("fiscal_year", 1800), ("document_ticker", "../AAPL")])
def test_invalid_event_identity_fails_closed(field: str, value: object) -> None:
    row = _row(quarter=1, call_date="2026-01-29", sentiment=0.2, tags="iphone")
    row[field] = value
    with pytest.raises(ContractError):
        build_company_contexts([row], tx_index=_tx(1), as_of="2026-02-02")


def test_operational_batch_quarantines_one_bad_identity_without_mutating_good_rows() -> None:
    healthy = _row(quarter=1, call_date="2026-01-29", sentiment=0.2, tags="iphone")
    corrupt = {**healthy, "fiscal_year": 2925}
    valid, rejected = _quarantine_invalid_history([healthy, corrupt])
    assert valid == [healthy]
    assert rejected == 1
