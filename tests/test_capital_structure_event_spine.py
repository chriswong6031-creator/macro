"""Pure routing, evidence, immutable-version and review-queue contracts."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.capital_structure.event_spine import (
    CLASSIFIED,
    DEFERRED_AMBIGUOUS_CONTENT,
    DEFERRED_MISSING_DOCUMENT,
    DEFERRED_LINKAGE,
    NOT_APPLICABLE,
    append_event_versions_strict,
    build_event_version,
    build_review_queue,
    event_classification,
    make_stable_span,
    route_form,
)


ROOT = Path(__file__).resolve().parent.parent
HASH = "a" * 64


def _observation(**updates):
    row = {
        "source_system": "sec_edgar",
        "source_id": "0000000001-26-000001",
        "manifest_id": "manifest:1",
        "accession": "0000000001-26-000001",
        "issuer_id": "issuer:0000000001",
        "cik": "1",
        "ticker": "ABC",
        "aliases": ["ABC Corp"],
        "form": "S-3",
        "file_number": "333-123",
        "filing_date": "2026-08-01",
        "accepted_at": "2026-08-01T10:00:00Z",
        "first_seen_at": "2026-08-01T10:00:03Z",
        "primary_document_url": "https://www.sec.gov/Archives/abc.htm",
        "exhibit_urls": [],
        "content_hashes": [HASH],
    }
    row.update(updates)
    return row


def _span(text="Registration statement"):
    return make_stable_span("manifest:1", text, locator_type="dom", locator="html/body[1]")


@pytest.mark.parametrize(("form", "family", "lifecycle", "state"), [
    ("S-3", "shelf", "filed", CLASSIFIED),
    ("S-3/A", "shelf", "amended", CLASSIFIED),
    ("EFFECT", "other", "effective", CLASSIFIED),
    ("RW", "other", "withdrawn", CLASSIFIED),
    ("1-A", "reg_a", "filed", CLASSIFIED),
    ("1-K/A", "reg_a", "unknown", NOT_APPLICABLE),
    ("424B5", "other", "filed", DEFERRED_AMBIGUOUS_CONTENT),
    ("6-K", "other", "filed", DEFERRED_AMBIGUOUS_CONTENT),
    ("DEF 14A", "corporate_action", "filed", DEFERRED_AMBIGUOUS_CONTENT),
    ("10-Q", "other", "unknown", NOT_APPLICABLE),
    ("SC 13D", "other", "unknown", NOT_APPLICABLE),
])
def test_form_router_is_deterministic_and_never_guesses(form, family, lifecycle, state):
    route = route_form(form)
    assert route.family == family
    assert route.lifecycle_state == lifecycle
    assert route.classification_state == state


def test_8k_items_narrow_candidate_but_remain_content_deferred():
    sale = route_form("8-K", "Items 1.01, 3.02 and 9.01")
    assert sale.subtype == "unregistered_equity_sale_candidate"
    assert sale.classification_state == DEFERRED_AMBIGUOUS_CONTENT

    vote = route_form("8-K", ["5.07", "9.01"])
    assert vote.family == "corporate_action"
    assert vote.subtype == "shareholder_vote_candidate"
    assert vote.classification_state == DEFERRED_AMBIGUOUS_CONTENT


def test_424b5_never_becomes_atm_or_priced_from_form_alone():
    route = route_form("424B5")
    assert route.subtype == "prospectus_event"
    assert route.lifecycle_state == "filed"
    assert route.defer_reason and "content" in route.defer_reason


def test_stable_span_binds_manifest_locator_and_exact_text():
    span = make_stable_span("manifest:1", "exact  text", locator_type="text_range", locator="10:21")
    assert span["text_sha256"] == hashlib.sha256(b"exact  text").hexdigest()
    assert span == make_stable_span("manifest:1", "exact  text", locator_type="text_range", locator="10:21")
    assert span["span_id"] != make_stable_span(
        "manifest:1", "exact text", locator_type="text_range", locator="10:21"
    )["span_id"]
    assert span["span_id"] != make_stable_span(
        "manifest:1", "exact  text", locator_type="text_range", locator="11:22"
    )["span_id"]


def test_build_event_is_strict_schema_valid_context_only_and_deterministic():
    event = build_event_version(_observation(), [_span()])
    schema = json.loads((ROOT / "contracts" / "capital_structure_event.schema.json").read_text())
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(event))
    assert not errors, "\n".join(error.message for error in errors)
    assert event == build_event_version(_observation(), [_span()])
    assert event["point_in_time"]["available_at"] == "2026-08-01T10:00:03Z"
    assert event["point_in_time"]["available_at"] != event["filing"]["accepted_at"]
    assert event["version"] == {
        "immutable_record": True, "correction_version": 1, "correction_of": None,
    }
    assert event["authority"]["rank_authority"] is False
    assert event["source"]["manifest_ids"] == ["manifest:1"]
    assert event["classification"] == {"state": CLASSIFIED, "defer_reason": None}
    assert event["point_in_time"] == {
        "first_seen_at": "2026-08-01T10:00:03Z",
        "public_available_at": "2026-08-01T10:00:00Z",
        "system_available_at": "2026-08-01T10:00:03Z",
        "available_at": "2026-08-01T10:00:03Z",
    }
    assert "normalized_terms" not in event


def test_deferred_event_uses_schema_deferred_states_and_explicit_route_receipt():
    event = build_event_version(_observation(form="424B5"), [_span("ambiguous prospectus")])
    assert event["extraction"]["method"] == "deferred"
    assert event["extraction"]["review_status"] == "deferred"
    assert event["reconciliation"]["state"] == "deferred"
    assert event["classification"] == {
        "state": DEFERRED_AMBIGUOUS_CONTENT,
        "defer_reason": "prospectus_requires_content_to_distinguish_pricing_atm_resale_or_rights",
    }
    assert event_classification(event) == {
        "classification_state": DEFERRED_AMBIGUOUS_CONTENT,
        "defer_reason": "prospectus_requires_content_to_distinguish_pricing_atm_resale_or_rights",
        "registration_family": None,
        "relationship": None,
    }


def test_collector_can_escalate_form_defer_to_specific_missing_document_state():
    event = build_event_version(
        _observation(
            form="424B5",
            classification_state=DEFERRED_MISSING_DOCUMENT,
            defer_reason="primary_document_not_stored",
        ),
        [_span("root manifest locator")],
    )
    assert event["classification"] == {
        "state": DEFERRED_MISSING_DOCUMENT,
        "defer_reason": "primary_document_not_stored",
    }
    assert build_review_queue([event])[0]["classification_state"] == DEFERRED_MISSING_DOCUMENT


def test_invalid_or_reasonless_defer_state_is_rejected():
    with pytest.raises(ValueError, match="unsupported classification_state"):
        build_event_version(_observation(classification_state="maybe"), [_span()])
    with pytest.raises(ValueError, match="requires defer_reason"):
        build_event_version(
            _observation(classification_state=DEFERRED_MISSING_DOCUMENT, defer_reason=""),
            [_span()],
        )


def test_correction_is_new_version_and_does_not_mutate_original():
    original = build_event_version(_observation(), [_span()])
    frozen = copy.deepcopy(original)
    correction = build_event_version(
        _observation(first_seen_at="2026-08-02T09:00:00Z"),
        [_span("corrected source interpretation")],
        correction_version=2,
        correction_of=original["event_id"],
    )
    assert original == frozen
    assert correction["event_id"] != original["event_id"]
    assert correction["version"]["correction_of"] == original["event_id"]
    assert correction["relationships"] == {
        "amendment_of": None,
        "supersedes": [original["event_id"]],
    }


def test_strict_append_is_idempotent_but_rejects_hash_identity_collision():
    event = build_event_version(_observation(), [_span()])
    assert append_event_versions_strict([], [event, copy.deepcopy(event)]) == [event]
    corrupt = copy.deepcopy(event)
    corrupt["issuer"]["ticker"] = "XYZ"
    with pytest.raises(ValueError, match="immutable event collision"):
        append_event_versions_strict([event], [corrupt])


def test_event_builder_rejects_missing_evidence_naive_time_and_bad_hash():
    with pytest.raises(ValueError, match="stable evidence"):
        build_event_version(_observation(), [])
    with pytest.raises(ValueError, match="timezone"):
        build_event_version(_observation(first_seen_at="2026-08-01T10:00:03"), [_span()])
    with pytest.raises(ValueError, match="content_hashes"):
        build_event_version(_observation(content_hashes=["not-a-hash"]), [_span()])


def test_review_queue_contains_only_current_deferred_events():
    safe = build_event_version(_observation(), [_span()])
    ambiguous = build_event_version(
        _observation(
            accession="0000000001-26-000002", source_id="0000000001-26-000002",
            form="424B5", first_seen_at="2026-08-02T10:00:00Z",
        ),
        [_span("prospectus")],
    )
    queue = build_review_queue([safe, ambiguous])
    assert len(queue) == 1
    assert queue[0]["event_id"] == ambiguous["event_id"]
    assert queue[0]["classification_state"] == DEFERRED_AMBIGUOUS_CONTENT
    assert queue[0]["review_state"] == "pending"
