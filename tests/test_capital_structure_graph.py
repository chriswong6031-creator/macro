"""Unique-only amendment/EFFECT/withdrawal graph behavior."""
from __future__ import annotations

import copy

from engine.capital_structure.event_spine import (
    DEFERRED_LINKAGE,
    build_event_version,
    build_review_queue,
    link_registration_graph,
    make_stable_span,
)


HASH = "b" * 64


def _event(accession: str, form: str, seen: str, **extra):
    accepted = extra.pop("accepted_at", seen)
    observation = {
        "manifest_id": f"manifest:{accession}",
        "accession": accession,
        "source_id": accession,
        "issuer_id": "issuer:0000000001",
        "cik": "1",
        "ticker": "ABC",
        "form": form,
        "file_number": extra.pop("file_number", None),
        "filing_date": seen[:10],
        "accepted_at": accepted,
        "first_seen_at": seen,
        "primary_document_url": "https://www.sec.gov/Archives/example.htm",
        "content_hashes": [HASH],
    }
    observation.update(extra)
    span = make_stable_span(observation["manifest_id"], form, locator="document")
    return build_event_version(observation, [span])


def test_explicit_accession_link_is_exact_and_does_not_mutate_parent():
    parent = _event("0000000001-26-000001", "S-3", "2026-08-01T10:00:00Z")
    child = _event("0000000001-26-000002", "S-3/A", "2026-08-02T10:00:00Z")
    parent_before = copy.deepcopy(parent)
    graph = link_registration_graph(
        [parent, child],
        {child["event_id"]: {"explicit_accession": parent["filing"]["accession"]}},
    )
    assert parent == parent_before
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert edge["from_event_id"] == child["event_id"]
    assert edge["to_event_id"] == parent["event_id"]
    assert edge["relationship"] == "amendment_of"
    assert edge["link_method"] == "explicit_accession"
    assert edge["immutable_record"] is True
    assert graph["unresolved"] == []


def test_exact_keys_and_chronology_link_effect_to_unique_latest_registration():
    original = _event("0000000001-26-000001", "S-3", "2026-08-01T10:00:00Z")
    amendment = _event("0000000001-26-000002", "S-3/A", "2026-08-02T10:00:00Z")
    effect = _event("0000000001-26-000003", "EFFECT", "2026-08-03T10:00:00Z")
    linkage = {
        original["event_id"]: {"file_number": "333-123", "registration_family": "registration_s3"},
        amendment["event_id"]: {"file_number": "333-123", "registration_family": "registration_s3"},
        effect["event_id"]: {"file_number": "333-123", "registration_family": "registration_s3"},
    }
    graph = link_registration_graph([original, amendment, effect], linkage)
    by_child = {edge["from_event_id"]: edge for edge in graph["edges"]}
    assert by_child[amendment["event_id"]]["to_event_id"] == original["event_id"]
    assert by_child[effect["event_id"]]["to_event_id"] == amendment["event_id"]
    assert by_child[effect["event_id"]]["relationship"] == "effectuates"
    assert graph["unresolved"] == []
    assert build_review_queue([original, amendment, effect], graph) == []
    assert amendment["classification"] == {"state": "classified", "defer_reason": None}
    assert effect["classification"] == {"state": "classified", "defer_reason": None}


def test_intervening_prospectus_cannot_become_registration_amendment_parent():
    original = _event("0000000001-26-000001", "S-3", "2026-08-01T10:00:00Z")
    prospectus = _event("0000000001-26-000002", "424B5", "2026-08-02T10:00:00Z")
    amendment = _event("0000000001-26-000003", "S-3/A", "2026-08-03T10:00:00Z")
    linkage = {
        event["event_id"]: {
            "file_number": "333-123", "registration_family": "registration_s3",
        }
        for event in (original, prospectus, amendment)
    }
    graph = link_registration_graph([original, prospectus, amendment], linkage)
    amendment_edge = next(
        edge for edge in graph["edges"] if edge["from_event_id"] == amendment["event_id"]
    )
    assert amendment_edge["to_event_id"] == original["event_id"]
    assert amendment_edge["to_event_id"] != prospectus["event_id"]
    assert amendment["classification"] == {"state": "classified", "defer_reason": None}
    assert build_review_queue([original, prospectus, amendment], graph) == [
        item for item in build_review_queue([prospectus])
    ]


def test_prospectus_is_never_parent_for_any_registration_state_relationship():
    expected = {
        "S-3/A": "amendment_of",
        "POS AM": "amendment_of",
        "EFFECT": "effectuates",
        "RW": "withdraws",
    }
    for offset, (child_form, relationship) in enumerate(expected.items(), start=3):
        original = _event("0000000001-26-000001", "S-3", "2026-08-01T10:00:00Z")
        prospectus = _event("0000000001-26-000002", "424B5", "2026-08-02T10:00:00Z")
        child = _event(
            f"0000000001-26-{offset:06d}", child_form, f"2026-08-{offset:02d}T10:00:00Z"
        )
        linkage = {
            event["event_id"]: {
                "file_number": "333-123", "registration_family": "registration_s3",
            }
            for event in (original, prospectus, child)
        }
        graph = link_registration_graph([original, prospectus, child], linkage)
        edge = next(item for item in graph["edges"] if item["from_event_id"] == child["event_id"])
        assert edge["relationship"] == relationship
        assert edge["to_event_id"] == original["event_id"]


def test_unresolved_relationship_is_graph_deferred_without_poisoning_event_classification():
    amendment = _event("0000000001-26-000002", "S-3/A", "2026-08-02T10:00:00Z")
    graph = link_registration_graph([amendment])
    assert amendment["classification"] == {"state": "classified", "defer_reason": None}
    queue = build_review_queue([amendment], graph)
    assert queue[0]["classification_state"] == DEFERRED_LINKAGE
    assert queue[0]["defer_reason"] == "missing_exact_linkage_keys"


def test_same_run_backfill_uses_acceptance_chronology_but_edge_availability_is_system_clock():
    seen = "2026-08-05T12:00:00Z"
    original = _event(
        "0000000001-20-000001", "S-3", seen,
        accepted_at="2020-01-02T15:30:00Z",
    )
    amendment = _event(
        "0000000001-20-000002", "S-3/A", seen,
        accepted_at="2020-01-03T15:30:00Z",
    )
    linkage = {
        event["event_id"]: {
            "file_number": "333-123", "registration_family": "registration_s3",
        }
        for event in (original, amendment)
    }
    graph = link_registration_graph([original, amendment], linkage)
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["to_event_id"] == original["event_id"]
    assert graph["edges"][0]["observed_at"] == seen


def test_late_retained_parent_resolves_prospectively_at_parent_system_clock():
    child = _event(
        "0000000001-20-000002", "EFFECT", "2026-08-01T12:00:00Z",
        accepted_at="2020-01-03T15:30:00Z",
    )
    parent = _event(
        "0000000001-20-000001", "S-3", "2026-08-02T12:00:00Z",
        accepted_at="2020-01-02T15:30:00Z",
    )
    linkage = {
        event["event_id"]: {
            "file_number": "333-123", "registration_family": "registration_s3",
        }
        for event in (parent, child)
    }

    graph = link_registration_graph([child, parent], linkage)

    assert graph["unresolved"] == []
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["to_event_id"] == parent["event_id"]
    assert graph["edges"][0]["observed_at"] == "2026-08-02T12:00:00Z"


def test_missing_public_chronology_is_deferred_instead_of_using_system_order():
    original = _event(
        "0000000001-20-000001", "S-3", "2026-08-01T10:00:00Z",
        accepted_at=None,
    )
    amendment = _event(
        "0000000001-20-000002", "S-3/A", "2026-08-02T10:00:00Z",
    )
    linkage = {
        event["event_id"]: {
            "file_number": "333-123", "registration_family": "registration_s3",
        }
        for event in (original, amendment)
    }
    graph = link_registration_graph([original, amendment], linkage)
    assert graph["edges"] == []
    assert graph["unresolved"][0]["defer_reason"] == "no_unique_link_target"


def test_same_cik_and_file_number_but_wrong_registration_family_never_links():
    s1 = _event("0000000001-26-000001", "S-1", "2026-08-01T10:00:00Z")
    s3_amend = _event("0000000001-26-000002", "S-3/A", "2026-08-02T10:00:00Z")
    linkage = {
        s1["event_id"]: {"file_number": "333-123", "registration_family": "registration_s1"},
        s3_amend["event_id"]: {"file_number": "333-123", "registration_family": "registration_s3"},
    }
    graph = link_registration_graph([s1, s3_amend], linkage)
    assert graph["edges"] == []
    assert graph["unresolved"][0]["classification_state"] == DEFERRED_LINKAGE
    assert graph["unresolved"][0]["defer_reason"] == "no_unique_link_target"


def test_equal_chronology_candidates_are_ambiguous_not_guessed():
    left = _event("0000000001-26-000001", "S-3", "2026-08-01T10:00:00Z")
    right = _event("0000000001-26-000009", "S-3", "2026-08-01T10:00:00Z")
    effect = _event("0000000001-26-000010", "EFFECT", "2026-08-02T10:00:00Z")
    linkage = {
        event["event_id"]: {"file_number": "333-123", "registration_family": "registration_s3"}
        for event in (left, right, effect)
    }
    graph = link_registration_graph([left, right, effect], linkage)
    assert graph["edges"] == []
    unresolved = graph["unresolved"][0]
    assert unresolved["defer_reason"] == "ambiguous_link_target"
    assert set(unresolved["candidate_event_ids"]) == {left["event_id"], right["event_id"]}


def test_missing_linkage_keys_flow_into_review_queue():
    amendment = _event("0000000001-26-000002", "S-3/A", "2026-08-02T10:00:00Z")
    graph = link_registration_graph([amendment])
    assert graph["edges"] == []
    assert graph["unresolved"][0]["defer_reason"] == "missing_exact_linkage_keys"
    queue = build_review_queue([amendment], graph["unresolved"])
    assert queue[0]["defer_reason"] == "missing_exact_linkage_keys"


def test_correction_uses_separate_supersedes_edge():
    original = _event("0000000001-26-000001", "S-3", "2026-08-01T10:00:00Z")
    observation = {
        "manifest_id": "manifest:corrected",
        "accession": original["filing"]["accession"],
        "source_id": original["source"]["source_id"],
        "issuer_id": "issuer:0000000001", "cik": "1", "ticker": "ABC", "form": "S-3",
        "file_number": "333-123",
        "filing_date": "2026-08-01", "accepted_at": "2026-08-01T10:00:00Z",
        "first_seen_at": "2026-08-04T10:00:00Z", "content_hashes": [HASH],
    }
    correction = build_event_version(
        observation,
        [make_stable_span("manifest:corrected", "corrected", locator="document")],
        correction_version=2,
        correction_of=original["event_id"],
    )
    graph = link_registration_graph([original, correction])
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["relationship"] == "supersedes"
    assert graph["edges"][0]["to_event_id"] == original["event_id"]


def _correction(event, *, seen: str, text: str):
    filing = event["filing"]
    issuer = event["issuer"]
    observation = {
        "manifest_id": f"manifest:{text}",
        "accession": filing["accession"],
        "source_id": event["source"]["source_id"],
        "issuer_id": issuer["issuer_id"],
        "cik": issuer["cik"],
        "ticker": issuer["ticker"],
        "form": filing["form"],
        "file_number": filing["file_number"],
        "filing_date": filing["filing_date"],
        "accepted_at": filing["accepted_at"],
        "first_seen_at": seen,
        "content_hashes": [HASH],
    }
    return build_event_version(
        observation,
        [make_stable_span(f"manifest:{text}", text, locator="document")],
        correction_version=int(event["version"]["correction_version"]) + 1,
        correction_of=event["event_id"],
    )


def test_parent_correction_never_retargets_existing_child_lifecycle_edge():
    parent = _event("0000000001-26-000001", "S-3", "2026-08-01T10:00:00Z")
    child = _event("0000000001-26-000002", "EFFECT", "2026-08-02T10:00:00Z")
    linkage = {
        event["event_id"]: {
            "file_number": "333-123", "registration_family": "registration_s3",
        }
        for event in (parent, child)
    }
    first = link_registration_graph([parent, child], linkage)
    lifecycle = next(edge for edge in first["edges"] if edge["relationship"] == "effectuates")

    parent_correction = _correction(
        parent, seen="2026-08-03T10:00:00Z", text="parent-correction"
    )
    linkage[parent_correction["event_id"]] = {
        "file_number": "333-123", "registration_family": "registration_s3",
    }
    second = link_registration_graph(
        [parent, child, parent_correction], linkage, existing_edges=first["edges"]
    )

    lifecycle_edges = [edge for edge in second["edges"] if edge["relationship"] == "effectuates"]
    assert lifecycle_edges == [lifecycle]
    assert any(
        edge["from_event_id"] == parent_correction["event_id"]
        and edge["relationship"] == "supersedes"
        for edge in second["edges"]
    )


def test_child_correction_can_link_to_latest_parent_version_without_retargeting_old_child():
    parent = _event("0000000001-26-000001", "S-3", "2026-08-01T10:00:00Z")
    child = _event("0000000001-26-000002", "EFFECT", "2026-08-02T10:00:00Z")
    linkage = {
        event["event_id"]: {
            "file_number": "333-123", "registration_family": "registration_s3",
        }
        for event in (parent, child)
    }
    first = link_registration_graph([parent, child], linkage)
    parent_correction = _correction(
        parent, seen="2026-08-03T10:00:00Z", text="parent-correction"
    )
    child_correction = _correction(
        child, seen="2026-08-04T10:00:00Z", text="child-correction"
    )
    for event in (parent_correction, child_correction):
        linkage[event["event_id"]] = {
            "file_number": "333-123", "registration_family": "registration_s3",
        }

    graph = link_registration_graph(
        [parent, child, parent_correction, child_correction],
        linkage,
        existing_edges=first["edges"],
    )

    by_child = [
        edge for edge in graph["edges"]
        if edge["relationship"] == "effectuates"
    ]
    assert len(by_child) == 2
    old_edge = next(edge for edge in by_child if edge["from_event_id"] == child["event_id"])
    new_edge = next(
        edge for edge in by_child if edge["from_event_id"] == child_correction["event_id"]
    )
    assert old_edge["to_event_id"] == parent["event_id"]
    assert new_edge["to_event_id"] == parent_correction["event_id"]
    assert new_edge["observed_at"] == "2026-08-04T10:00:00Z"
