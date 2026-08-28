"""E3-B canonical qa_exchange.v1 adapter — AAPL fixture + hostile mutations."""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from engine.company_intelligence.event_workspace import (
    FLAGSHIP_EVENT_ID,
    WORKSPACE_KEYS,
    WorkspaceError,
    validate_event_workspace,
)
from engine.company_intelligence.qa_exchange import (
    ACCEPTED_QA_TRANSCRIPT_SHA256,
    TAXONOMY_HASH,
    TAXONOMY_VERSION,
    accepted_qa_exchanges_for_transcript,
    source_clock_payload,
    validate_qa_exchange,
    validate_qa_exchanges,
    validate_source_clock,
)
from tests.test_company_intelligence_event_workspace import _build_flagship

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/company_intelligence/aapl_fy2026_q3.json.gz"
EVENT_ID = FLAGSHIP_EVENT_ID
DOCUMENT_ID = "tx:AAPL/2026Q3"


def _segments() -> tuple[list[dict], str]:
    raw = gzip.decompress(FIXTURE.read_bytes())
    sha = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)["segments"], sha


def _accepted() -> list[dict]:
    segments, sha = _segments()
    assert sha == ACCEPTED_QA_TRANSCRIPT_SHA256
    return accepted_qa_exchanges_for_transcript(
        event_id=EVENT_ID,
        document_id=DOCUMENT_ID,
        document_sha256=sha,
        segments=segments,
    )


def test_accepted_aapl_canonical_parity() -> None:
    exchanges = _accepted()
    assert len(exchanges) == 7
    assert sum(len(item["question_spans"]) for item in exchanges) == 32
    assert sum(len(item["answer_spans"]) for item in exchanges) == 36
    assert sum(len(item["respondents"]) for item in exchanges) == 26
    first = exchanges[0]
    assert first["schema"] == "qa_exchange.v1"
    assert first["exchange_id"] == f"qx_{EVENT_ID}_{ACCEPTED_QA_TRANSCRIPT_SHA256[:12]}_00"
    assert first["questioner"]["name"] == "Amit Daryanani"
    assert first["questioner"]["affiliation"] == "Evercore"
    assert [row["name"] for row in first["respondents"]] == ["Kevan Parekh", "Tim Cook", "Tim Cook"]
    assert all(item["topics"] == ["unavailable"] for item in exchanges)
    assert all(item["taxonomy_version"] == TAXONOMY_VERSION for item in exchanges)
    assert all(item["taxonomy_hash"] == TAXONOMY_HASH for item in exchanges)
    assert all(item["provenance"]["provider"] is None for item in exchanges)
    assert all(item["provenance"]["model"] is None for item in exchanges)
    assert all(item["provenance"]["prompt_version"] is None for item in exchanges)
    assert all(item["validation"]["replayed"] is True for item in exchanges)
    replayed = 0
    for item in exchanges:
        replayed += len(item["question_spans"]) + len(item["answer_spans"])
        for span in item["question_spans"] + item["answer_spans"]:
            assert span["schema"] == "source_span.v1"
            assert span["receipt_state"] == "byte_replayed"
            assert span["receipt"]["source_sha256"] == ACCEPTED_QA_TRANSCRIPT_SHA256
    assert replayed == 68
    operator = first["question_spans"][0]
    assert (operator.get("locator") or {}).get("speaker") == "Operator"
    assert first["questioner"]["name"] != "Operator"


def test_sha_mismatch_publishes_nothing() -> None:
    segments, _sha = _segments()
    empty = accepted_qa_exchanges_for_transcript(
        event_id=EVENT_ID,
        document_id=DOCUMENT_ID,
        document_sha256="ab" * 32,
        segments=segments,
    )
    assert empty == []


def test_flagship_workspace_publishes_seven_exchanges() -> None:
    payload = _build_flagship()
    public = {key: payload[key] for key in WORKSPACE_KEYS}
    validate_event_workspace({**public, "generation_id": "0" * 24})
    assert len(payload["qa_exchanges"]) == 7
    assert "questions_count_unstructured" not in payload["warnings"]
    assert payload["prophet_flags"] == {
        "may_rank": False,
        "may_size": False,
        "may_gate": False,
        "prophet_authority": False,
    }
    for delta in payload["deltas"]:
        assert "beat" not in delta and "miss" not in delta and "beat_miss" not in delta
        assert delta.get("basis_match") is not True


@pytest.mark.parametrize(
    "mutator, match",
    [
        (lambda item: item.__setitem__("extra", "nope"), "keys mismatch"),
        (lambda item: item.__setitem__("event_id", "evt_cik0000320193_2026q2_results"), "event_id"),
        (lambda item: item.__setitem__("document_sha256", "cd" * 32), "document_sha256"),
        (lambda item: item.__setitem__("exchange_id", "qx_wrong"), "exchange_id"),
        (lambda item: item.__setitem__("taxonomy_hash", "00" * 32), "taxonomy"),
        (lambda item: item.__setitem__("topics", ["demand"]), "unavailable-only"),
        (lambda item: item["respondents"][0]["span_indexes"].__setitem__(0, 99), "out of range"),
        (lambda item: item["respondents"].__setitem__(1, {**item["respondents"][0], "span_indexes": item["respondents"][0]["span_indexes"]}), "owned exactly once"),
        (lambda item: item["respondents"].pop(), "owned exactly once"),
        (lambda item: item["provenance"].__setitem__("model", "qwen"), "provider or model"),
        (lambda item: item["provenance"].__setitem__("taxonomy_hash", "x") if False else item.__setitem__("prophet", True), "forbidden"),
        (lambda item: item["provenance"].__setitem__("source_available_at", "2026-08-16T18:00:00Z"), "cannot claim source_available_at"),
        (lambda item: item.__setitem__("generated_at", "2026-08-16T18:00:00Z"), "keys mismatch"),
        (lambda item: item["questioner"].__setitem__("name_state", "inferred"), "source-supported"),
        (lambda item: item["respondents"][0].__setitem__("identity_state", "inferred"), "source-supported"),
        (lambda item: item["question_spans"].append(copy.deepcopy(item["question_spans"][0])), "not unique"),
    ],
)
def test_validator_rejects_hostile_mutations(mutator, match) -> None:
    item = copy.deepcopy(_accepted()[0])
    try:
        mutator(item)
    except Exception:
        pytest.fail("mutator should only edit the payload")
    with pytest.raises(WorkspaceError, match=match):
        validate_qa_exchange(
            item,
            event_id=EVENT_ID,
            document_id=DOCUMENT_ID,
            document_sha256=ACCEPTED_QA_TRANSCRIPT_SHA256,
        )


def test_empty_qa_list_remains_valid() -> None:
    assert validate_qa_exchanges([], event_id=EVENT_ID, document_id=DOCUMENT_ID, document_sha256=ACCEPTED_QA_TRANSCRIPT_SHA256) == []


def test_source_clock_omits_when_system_recorded_at_missing() -> None:
    assert source_clock_payload(
        document_id=DOCUMENT_ID,
        source_sha256=ACCEPTED_QA_TRANSCRIPT_SHA256,
        source_available_at="2026-07-30T20:30:28Z",
        system_recorded_at=None,
    ) is None


def test_source_clock_unknown_cannot_claim_availability() -> None:
    payload = source_clock_payload(
        document_id=DOCUMENT_ID,
        source_sha256=ACCEPTED_QA_TRANSCRIPT_SHA256,
        source_available_at=None,
        system_recorded_at="2026-08-16T18:00:00Z",
    )
    assert payload is not None
    assert payload["clock_state"] == "unknown"
    assert payload["source_available_at"] is None
    with pytest.raises(WorkspaceError, match="cannot claim"):
        validate_source_clock(
            {**payload, "source_available_at": payload["system_recorded_at"]},
            document_id=DOCUMENT_ID,
            source_sha256=ACCEPTED_QA_TRANSCRIPT_SHA256,
        )
    with pytest.raises(WorkspaceError, match="keys mismatch"):
        validate_source_clock(
            {**payload, "generated_at": payload["system_recorded_at"]},
            document_id=DOCUMENT_ID,
            source_sha256=ACCEPTED_QA_TRANSCRIPT_SHA256,
        )


def test_question_answer_span_overlap_is_rejected() -> None:
    item = copy.deepcopy(_accepted()[0])
    question = item["question_spans"][0]
    answer = item["answer_spans"][0]
    locator = copy.deepcopy(question["locator"])
    locator["span_end_byte"] = int(locator["span_end_byte"]) - 1
    answer["locator"] = locator
    with pytest.raises(WorkspaceError, match="overlap"):
        validate_qa_exchange(
            item,
            event_id=EVENT_ID,
            document_id=DOCUMENT_ID,
            document_sha256=ACCEPTED_QA_TRANSCRIPT_SHA256,
        )


def test_workspace_binds_qa_provenance_to_transcript_clock_or_owner_gap() -> None:
    payload = _build_flagship()
    public = {key: payload[key] for key in WORKSPACE_KEYS}
    validate_event_workspace({**public, "generation_id": "0" * 24})
    assert all(
        item["provenance"]["clock_state"] == "unknown"
        and item["provenance"]["source_available_at"] is None
        for item in payload["qa_exchanges"]
    )
    sources = copy.deepcopy(payload["sources"])
    transcript = next(row for row in sources if row["kind"] == "transcript")
    transcript["source_clock"] = {
        "schema": "event_source_clock.v1",
        "document_id": transcript["document_id"],
        "source_sha256": transcript["source_sha256"],
        "source_available_at": "2026-07-30T20:30:28Z",
        "system_recorded_at": "2026-08-16T18:00:00Z",
        "clock_state": "known",
        "rights_profile": "rp_public_primary_v1",
        "session_phase": "unknown",
    }
    with pytest.raises(WorkspaceError, match="does not match transcript source clock"):
        validate_event_workspace({**public, "generation_id": "0" * 24, "sources": sources})
    matched = copy.deepcopy(payload["qa_exchanges"])
    for item in matched:
        item["provenance"]["clock_state"] = "known"
        item["provenance"]["source_available_at"] = "2026-07-30T20:30:28Z"
    validate_event_workspace({
        **public,
        "generation_id": "0" * 24,
        "sources": sources,
        "qa_exchanges": matched,
    })


def test_homebuilder_without_matching_sha_stays_empty() -> None:
    segments, _sha = _segments()
    empty = accepted_qa_exchanges_for_transcript(
        event_id="evt_cik0000882184_2026q3_results",
        document_id="tx:DHI/2026Q3",
        document_sha256="11" * 32,
        segments=segments,
    )
    assert empty == []
