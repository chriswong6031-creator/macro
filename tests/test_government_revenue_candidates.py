from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

import pytest

from engine.government_revenue.candidates import (
    build_candidate_observations,
    build_candidate_queue,
    build_mapping_backlog,
    candidate_historical_suppression_activation,
    candidate_historical_suppression_entry,
    candidate_queue_content_id,
    historical_suppression_entry_key,
    is_valid_candidate_payload,
    is_valid_candidate_queue,
    load_candidate_issuance_correction_manifest,
)
from scripts.build_government_revenue import build_payload
from tests.government_revenue_candidate_fixture import (
    canonical_candidate_census,
    canonical_mapping_backlog_states,
    canonical_requested_issuer_tickers,
    canonical_reviewed_issuer_tickers,
    canonical_unreviewed_issuer_tickers,
)


ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 64
SHA_B = "b" * 64
KNOWN_AT = "2026-08-02T12:00:00+00:00"
EFFECTIVE_AT = "2026-08-01T12:00:00+00:00"
GENERATED_AT = "2026-08-03T07:00:00+00:00"


def _graph() -> dict:
    return {
        "contract": "government_recipient_entity_graph.v1",
        "schema_version": "1.1.0",
        "graph_id": "recipient-graph:test-noc",
        "graph_known_at": "2026-08-02T00:00:00+00:00",
        "graph_effective_at": "2026-08-02T00:00:00+00:00",
        "evidence": [
            {
                "evidence_id": "evidence:noc",
                "source_ref": f"recipient-evidence:sha256:{SHA_A}",
                "publisher": "SEC",
                "evidence_class": "official_filing",
                "record_id": "0000000000-26-000001",
                "url": "https://www.sec.gov/Archives/edgar/data/1/test.htm",
                "content_sha256": SHA_A,
                "byte_length": 100,
                "retrieved_at": "2026-08-01T00:00:00+00:00",
                "claim_scopes": [
                    "public_company", "legal_entity", "exact_identifier", "ownership",
                ],
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
            }
        ],
        "companies": [
            {
                "company_id": "issuer:noc",
                "ticker": "NOC",
                "verification_state": "reviewed",
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "legal_entities": [
            {
                "entity_id": "entity:noc",
                "canonical_name": "Northrop Grumman Systems Corporation",
                "verification_state": "reviewed",
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "identifiers": [
            {
                "identifier_id": "identifier:noc",
                "entity_id": "entity:noc",
                "namespace": "sam_uei",
                "value": "ABCDEFGHJKLM",
                "verification_state": "reviewed",
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "ownership_edges": [
            {
                "edge_id": "edge:noc",
                "child_entity_id": "entity:noc",
                "parent_company_id": "issuer:noc",
                "relationship": "wholly_owned",
                "economic_share": 1.0,
                "verification_state": "reviewed",
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "blocks": [],
        "conflicts": [],
        "overrides": [],
    }


def _ownership_path() -> list[dict]:
    return [
        {
            "edge_id": "edge:noc",
            "child_entity_id": "entity:noc",
            "parent_company_id": "issuer:noc",
            "relationship": "wholly_owned",
            "economic_share": 1.0,
            "known_at": "2026-08-01T00:00:00+00:00",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": None,
            "evidence_refs": ["evidence:noc"],
        }
    ]


def _award_event(*, event_type: str = "obligation", late: bool = False) -> dict:
    return {
        "kind": "award_change",
        "event_id": "govawd-noc-001",
        "record_id": "CONT_AWD_TEST_001",
        "change": {
            "type": event_type,
            "effective_at": EFFECTIVE_AT,
            "known_at": KNOWN_AT,
            "what_changed_en": "Official obligation increase observed",
        },
        "award_change": {
            "event_type": event_type,
            "source_rail": "usaspending_award_action",
            "source_identity": {"id": "action:1", "version": "1", "content_sha256": SHA_B},
            "is_late_discovery": late,
        },
        "primary_amount_id": "amount:obligation",
        "amounts": [
            {
                "id": "amount:obligation",
                "value": 125000000.0,
                "currency": "USD",
                "semantic": "federal_action_obligation_delta",
                "as_of": EFFECTIVE_AT,
                "source_ref": "receipt:action:1",
            }
        ],
        "listed_company_impacts": [
            {
                "ticker": "NOC",
                "company_name": "Northrop Grumman Corporation",
                "issuer_company_id": "issuer:noc",
                "relation_semantic": "reviewed",
                "resolution_state": "reviewed",
                "ownership_path": _ownership_path(),
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "evidence": {
            "source_class": "official_fact",
            "mapping_class": "reviewed",
            "conflicts": [],
            "receipts": [
                {
                    "ref_id": "receipt:action:1",
                    "publisher": "U.S. Treasury, USAspending.gov",
                    "record_id": "CONT_AWD_TEST_001",
                    "url": "https://api.usaspending.gov/api/v2/transactions/",
                    "effective_at": EFFECTIVE_AT,
                    "known_at": KNOWN_AT,
                    "retrieved_at": KNOWN_AT,
                    "content_sha256": SHA_B,
                }
            ],
        },
    }


def _payload(event: dict | None = None) -> dict:
    return {
        "as_of": "2026-08-03",
        "known_at": KNOWN_AT,
        "companies": [
            {
                "ticker": "NOC",
                "name": "Northrop Grumman Corporation",
                "entity_match": {"method": "curated_fuzzy_name"},
            },
            {
                "ticker": "LMT",
                "name": "Lockheed Martin Corporation",
                "entity_match": {"method": "curated_fuzzy_name"},
            },
        ],
        "procurement_workspace": {
            "bundle_id": "grw2-1234567890abcdef12345678",
            "freshness": {"award_events": {"status": "ok"}},
            "events": [event] if event is not None else [],
        },
    }


def test_current_source_truth_reconciles_against_the_ledger_and_the_correction() -> None:
    latest = json.loads((ROOT / "data/government_revenue/latest.json").read_text(encoding="utf-8"))
    graph = json.loads((ROOT / "data/government_revenue/recipient_entity_graph.json").read_text(encoding="utf-8"))
    status = json.loads(
        (ROOT / "data/government_revenue/candidate_projection_status.json").read_text(
            encoding="utf-8"
        )
    )
    corrections, _sha = load_candidate_issuance_correction_manifest(ROOT)

    queue = build_candidate_queue(latest, graph, generated_at=GENERATED_AT)

    # The pure source engine honestly sees every exact row that meets source
    # eligibility.  Active publication is a separate boundary: the
    # issuance-correction receipt quarantines the eight incident ledger rows
    # without teaching the source engine to erase or reinterpret official
    # evidence.  Those two boundaries are what this tripwire pins -- as an
    # identity between three artifacts written by three different code paths,
    # not as a census literal.  `== 8` was that literal, true of the 2026-08-09
    # vintage and false from 2026-08-12T23:50:04Z, when the award-action rail
    # resolved into the reviewed graph and fifteen forward candidates issued.
    # Nothing regressed there; that unlock is what the rail was built for, and
    # re-typing the new number would only schedule the next failure.
    #
    #   pure source total  ==  the append-only audit ledger      (facts kept)
    #   pure total - quarantined  ==  the published active count (facts scoped)
    assert queue["counts"]["total"] == canonical_candidate_census()
    assert queue["counts"]["exact_linked"] == queue["counts"]["total"]
    assert (
        queue["counts"]["total"] - len(corrections["entries"])
        == status["candidate_count"]
    )
    # Families are a partition of the same total, never a hand-copied tally.
    assert set(queue["counts"]["by_family"]) <= {
        "award_ceiling_change",
        "award_obligation_change",
    }
    assert sum(queue["counts"]["by_family"].values()) == queue["counts"]["total"]
    assert all(count > 0 for count in queue["counts"]["by_family"].values())
    # The backlog is a census of the REQUESTED issuer scope -- one row per
    # curated company -- so `== 21` was that scope's cardinality transcribed by
    # hand, not a contract.  Derived from `entities.json` (bound against the
    # payload it builds) so adding or retiring an issuer moves it by itself.
    # Keep #5518's derive-from-receipt approach over #5524's re-typed literal.
    assert queue["counts"]["mapping_needed"] == len(canonical_requested_issuer_tickers())


    assert len(queue["mapping_backlog"]) == len(canonical_requested_issuer_tickers())
    # Stronger than the count and equally derived: the backlog must cover the
    # curated scope exactly -- no issuer dropped, none invented.
    assert [row["ticker"] for row in queue["mapping_backlog"]] == list(
        canonical_requested_issuer_tickers()
    )
    # The award-event rail activated on 2026-08-08T18:30Z (activation_state=live)
    # after days of reporting unavailable, and Wave 9D published the reviewed
    # defense19 graph the same day. Current truth, re-verified empirically at this
    # merge (2026-08-09): the rail is read (award_events_status ok), ~500
    # award-change events are visible, every issuer the reviewed graph declares
    # is resolvable -- and eight exact snapshot rows now meet source eligibility.
    # They remain context-only and are quarantined by the separately reviewed
    # publication correction; this pure-engine tripwire must never pretend the
    # facts vanished.
    assert queue["freshness"]["award_events_status"] == "ok"
    assert queue["freshness"]["exact_candidate_availability"] == "available"
    assert queue["freshness"]["recipient_graph_status"] == "ready"
    # Coverage is a census of the published reviewed graph, so `== 19` and its
    # nineteen hand-listed tickers described exactly one vintage
    # (`recipient-graph:reviewed:2026-08-08:defense19-v1`) and would have to be
    # re-typed on every republish.  Derived from the graph's own declared roster
    # instead: this still pins the engine's resolved set ticker-for-ticker, but
    # now it pins it to what the graph publishes rather than to what a human
    # remembered.  A graph that declares an issuer reviewed while shipping no
    # reachable exact path for it still fails here -- that is the state BWXT was
    # in before its exact edges were reviewed.
    assert queue["coverage"]["reviewed_issuer_company_count"] == len(
        canonical_reviewed_issuer_tickers()
    )
    assert queue["coverage"]["reviewed_issuer_tickers"] == list(
        canonical_reviewed_issuer_tickers()
    )
    # The coverage frontier: every reviewed issuer is identifier-linked but its
    # discovery scope is incomplete, and the requested issuers carrying no
    # reviewed mapping at all -- GE (no_exact_match) and, on this vintage, BWXT
    # (no_collected_recipients) -- are finished answers rather than open tasks.
    # Derived as the set difference `requested - reviewed`, so an issuer that
    # gains reviewed exact edges crosses between the two states with no edit.
    assert (
        Counter(row["mapping_state"] for row in queue["mapping_backlog"])
        == canonical_mapping_backlog_states()
    )
    assert sorted(
        row["ticker"] for row in queue["mapping_backlog"]
        if row["mapping_state"] == "mapping_needed"
    ) == list(canonical_unreviewed_issuer_tickers())
    assert all(row["issuer_attribution"] == "not_asserted" for row in queue["mapping_backlog"])
    assert is_valid_candidate_queue(queue)


def _attributing_path_known_at(
    candidate: dict, ownership_edges_by_id: dict[str, dict]
) -> datetime:
    """The moment a candidate's FULL exact ownership path became attributable.

    ``ownership_path_refs`` (``candidates.py:1727``) names the exact graph
    ``ownership_edges`` rows the resolver walked -- every one of them has to
    exist for the exact path to resolve at all, so the path as a whole only
    became attributable once its YOUNGEST member edge was admitted.  This is
    row-level and graph-clock-independent: it does not move just because the
    graph document was republished, only when the SPECIFIC edges behind this
    candidate change.

    Deliberately fails loudly rather than excusing when a ref does not
    resolve -- an unresolvable reference is not evidence the row is new, and
    softening the gate on missing data is exactly the escape this replaces.
    """
    refs = candidate.get("ownership_path_refs") or []
    assert refs, (
        f"{candidate.get('candidate_id')} carries no ownership_path_refs; "
        "cannot derive a row-level attribution clock"
    )
    known_ats: list[datetime] = []
    for ref in refs:
        edge = ownership_edges_by_id.get(ref)
        assert edge is not None, (
            f"{candidate.get('candidate_id')} ownership_path_refs {ref!r} does not "
            "resolve against the current graph's ownership_edges"
        )
        known_ats.append(datetime.fromisoformat(edge["known_at"]))
    return max(known_ats)


def _suppression_identity(entry: dict) -> dict:
    """One tombstone minus the graph-clock-derived field.

    Built by EXCLUSION rather than from an allowlist, so a field added to the
    entry contract is compared by default instead of silently escaping the gate.
    """
    return {key: value for key, value in entry.items() if key != "observed_known_at"}


def test_reviewed_historical_cohort_rebuilds_byte_exact_and_nothing_escapes_review() -> None:
    """The reviewed eight are derived truth, not a hand-transcribed allowlist.

    The manifest governs the incident's quarantined identities, and only those.
    It was accidentally equal to *everything the source engine could see* while
    the eight were the only rows in existence, and this test read that accident
    as the contract -- so it red on 2026-08-12T23:50:04Z, when fifteen forward
    candidates issued on seven award records the review never touched.

    Regenerating the manifest to cover them would have auto-issued fifteen
    unreviewed ``do_not_backfill`` decisions and stamped a ``reviewed_at`` no
    human reviewed, against rows that were never suppression-eligible: they were
    issued forward, which is the correct disposition and the one the nightly
    already took (``candidate_projection_status`` ``status: ok``).  So partition
    the rebuild the way the engine itself partitions it -- quarantined vs active
    -- and hold the reviewed cohort to identity equality on its own terms.

    ``observed_known_at`` is excluded from that equality: it tracks
    ``graph_known_at`` and would red on every legitimate republish, inviting a
    regen that stamps observation after the review act.  The engine already
    binds by :func:`historical_suppression_entry_key` (graph/clock-independent)
    and substitutes the reviewed entry's clock before comparing a current row.
    The clock is still asserted present and offset-aware on both sides.

    The gate the count was standing in for is restored explicitly below: every
    row the source engine currently sees must be accounted for in the append-only
    audit ledger.  A first-seen candidate that is neither issued nor reviewed
    still fails here, which is the protection the manifest's own limitations
    clause promises.

    A DIFFERENT guard already covers a DIFFERENT failure mode and survives
    independently of the row-level discriminator below: the manifest loader
    itself (``candidates.py:315-324``,
    ``load_candidate_issuance_correction_manifest``) requires every entry's
    ``observed_known_at`` to sit at or before its own declared
    ``predecessor.projection_generated_at``, refusing to admit an entry that
    claims to have been observed AFTER the predecessor projection it is
    supposedly correcting.  That is the surviving forward-retiming guard for
    anything that actually reaches the manifest in this receipt-present
    regime; it says nothing about an unaccounted row that never reached the
    manifest at all, which is exactly the gap the ``escaped`` check below
    exists to close.
    """
    payload = build_payload(root=ROOT)
    graph = json.loads(
        (ROOT / "data/government_revenue/recipient_entity_graph.json").read_text(
            encoding="utf-8"
        )
    )
    rows = build_candidate_observations(
        payload,
        graph,
        generated_at=payload["generated_at"],
    )
    manifest = json.loads(
        (
            ROOT
            / "config/government_revenue/candidate_historical_suppressions.v1.json"
        ).read_text(encoding="utf-8")
    )
    corrections, _sha = load_candidate_issuance_correction_manifest(ROOT)
    quarantined = {entry["candidate_id"] for entry in corrections["entries"]}
    by_row = {
        row["candidate_id"]: candidate_historical_suppression_entry(row) for row in rows
    }
    # The partition below is keyed on candidate_id, so a collision would hide a
    # row from every gate that follows.
    assert len(by_row) == len(rows), "the rebuild yielded a duplicate candidate_id"
    reviewed_rows = [row for row in rows if row["candidate_id"] in quarantined]
    entries = sorted(
        (by_row[row["candidate_id"]] for row in reviewed_rows),
        key=historical_suppression_entry_key,
    )

    # The reviewed cohort rebuilds from live source in bijection with the
    # manifest.  A reviewed identity that stopped rebuilding, drifted a field,
    # or gained a sibling still fails.  Equality is the engine's
    # graph/clock-independent identity plus every other field; the clock is
    # asserted present rather than frozen to one graph vintage.
    assert len(entries) == len(manifest["entries"]) == len(quarantined)
    assert [historical_suppression_entry_key(entry) for entry in entries] == [
        historical_suppression_entry_key(entry) for entry in manifest["entries"]
    ]
    assert [_suppression_identity(entry) for entry in entries] == [
        _suppression_identity(entry) for entry in manifest["entries"]
    ]
    for entry in (*entries, *manifest["entries"]):
        observed_at = datetime.fromisoformat(entry["observed_known_at"])
        assert observed_at.tzinfo is not None
    assert {row["source_event"]["source_rail"] for row in reviewed_rows} == {
        "usaspending_award_snapshot"
    }
    # Nothing the source engine sees may escape review: the append-only ledger
    # is where an issued row is accounted for, and the manifest is where an
    # unissued historical row is.  A row in neither is a publication failure.
    ledger_ids = {
        json.loads(line)["candidate_id"]
        for line in (ROOT / "data/government_revenue/candidate_ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    unaccounted = set(by_row) - ledger_ids - quarantined
    # A reviewed-graph expansion can make a source row attributable AFTER the
    # committed projection froze, but candidate ``known_at`` folds the WHOLE
    # graph document's clock (``graph_known_at``), not the clock of the
    # specific rows that attribute this candidate.  Every candidate minted
    # against the current graph shares one ``known_at`` (measured 64/64), so
    # ``known_at > frozen_generated_at`` excuses every unaccounted row after
    # ANY republish -- including one attributed entirely through defense19-era
    # edges that existed well before the freeze.  That is precisely the
    # 2026-08-10 incident class this gate exists to catch, and the graph-level
    # discriminator would have waved it through.
    #
    # The row-level, graph-clock-independent replacement:
    # ``_attributing_path_known_at`` reads the SPECIFIC ownership edges named
    # in ``ownership_path_refs`` and takes the youngest of them -- the moment
    # this candidate's exact path actually became attributable, independent of
    # when the document containing it was last republished.  A row excused
    # here only because its attributing edges are new is a genuine
    # transitional state; a row whose attributing edges all predate the
    # freeze, unaccounted, is the incident class and fails hard.
    rows_by_id = {row["candidate_id"]: row for row in rows}
    ownership_edges_by_id = {
        edge["edge_id"]: edge for edge in graph.get("ownership_edges", [])
    }
    frozen_generated_at = datetime.fromisoformat(
        json.loads(
            (ROOT / "data/government_revenue/candidate_projection_state.json")
            .read_text(encoding="utf-8")
        )["generated_at"]
    )
    escaped = {
        candidate_id
        for candidate_id in unaccounted
        if _attributing_path_known_at(rows_by_id[candidate_id], ownership_edges_by_id)
        <= frozen_generated_at
    }
    assert not escaped, (
        "first-seen candidates whose ENTIRE attributing ownership path predates "
        "the frozen projection, with neither a ledger issuance nor a reviewed "
        "historical suppression -- the 2026-08-10 incident class: "
        f"{sorted(escaped)}"
    )


def test_row_level_discriminator_catches_the_2026_08_10_incident_class_and_excuses_only_genuinely_new_paths() -> None:
    """FIX-A: prove the replacement discriminator does what the graph-level one could not.

    The graph-level bound (``candidate known_at <= frozen_generated_at``) is
    vacuous: candidate ``known_at`` folds ``graph_known_at``, so it is
    identical across every candidate minted against one graph document
    (measured 64/64 on the live payload).  A republish moves it for every row
    at once, excusing an unaccounted candidate attributed ENTIRELY through
    edges that existed long before the freeze -- which is exactly what
    happened in the 2026-08-10 incident.

    ``_attributing_path_known_at`` reads the row's own ``ownership_path_refs``
    against the graph's ``ownership_edges`` and is blind to the document-level
    republish clock, so it tells the two cases apart correctly:

    * an unaccounted row attributed through a pre-freeze (defense19-era) edge
      -- the incident class -- must be caught (escaped == True);
    * an unaccounted row attributed through a freshly admitted edge -- a
      legitimate post-freeze graph expansion, the transitional state the
      surrounding test's comment describes -- must be excused (escaped == False).
    """
    payload = _payload(_award_event())

    # Case 1 -- the incident class: the candidate's one attributing edge
    # ("edge:noc") is defense19-vintage, admitted well before the freeze.
    incident_graph = _graph()
    incident_rows = build_candidate_observations(payload, incident_graph, generated_at=GENERATED_AT)
    assert len(incident_rows) == 1
    incident_row = incident_rows[0]
    assert incident_row["ownership_path_refs"] == ["edge:noc"]
    incident_edges_by_id = {
        edge["edge_id"]: edge for edge in incident_graph["ownership_edges"]
    }
    assert incident_edges_by_id["edge:noc"]["known_at"] == "2026-08-01T00:00:00+00:00"
    frozen_after_the_edge = datetime.fromisoformat("2026-08-01T12:00:00+00:00")
    incident_attributed_at = _attributing_path_known_at(incident_row, incident_edges_by_id)
    assert incident_attributed_at <= frozen_after_the_edge, (
        "the incident-class row's attributing edge must read as pre-freeze"
    )
    # This is the exact predicate the surrounding test applies to `unaccounted`
    # candidates -- an unaccounted row here would fail hard, as required.
    incident_would_escape = incident_attributed_at <= frozen_after_the_edge
    assert incident_would_escape, (
        "FIX-A must NOT excuse a row attributed entirely through a pre-freeze "
        "edge -- this is the 2026-08-10 incident class"
    )
    # The vacuous graph-level bound this replaces WOULD have excused it: the
    # candidate's own known_at sits after this freeze point regardless of how
    # old its attributing edge actually is, which is exactly what made the old
    # discriminator vacuous rather than merely imprecise.
    vacuous_bound_would_excuse = (
        datetime.fromisoformat(incident_row["known_at"]) > frozen_after_the_edge
    )
    assert vacuous_bound_would_excuse, (
        "the demonstration requires the OLD graph-level bound to actually excuse "
        "this incident-class row (candidate known_at after the freeze point) -- "
        "otherwise it proves nothing about the bound being vacuous"
    )

    # Case 2 -- a legitimate post-freeze graph expansion: the SAME candidate
    # shape, but its attributing edge was admitted AFTER the freeze point --
    # the same relative ordering as today's live BWXT rows, whose attributing
    # edges (known_at 2026-08-19T05:44:34) postdate the committed
    # candidate_projection_state freeze (2026-08-19T05:25:42). The edge's
    # new known_at must still satisfy the graph's own admission (<=
    # graph_known_at), so it moves within this fixture's existing clock
    # window rather than reusing the unrelated real BWXT timestamps.
    fresh_graph = _graph()
    fresh_graph["ownership_edges"][0]["known_at"] = "2026-08-01T18:00:00+00:00"
    fresh_rows = build_candidate_observations(payload, fresh_graph, generated_at=GENERATED_AT)
    assert len(fresh_rows) == 1
    fresh_row = fresh_rows[0]
    fresh_edges_by_id = {edge["edge_id"]: edge for edge in fresh_graph["ownership_edges"]}
    frozen_before_the_edge = datetime.fromisoformat("2026-08-01T06:00:00+00:00")
    fresh_attributed_at = _attributing_path_known_at(fresh_row, fresh_edges_by_id)
    assert fresh_attributed_at > frozen_before_the_edge, (
        "the demonstration requires the fresh edge to genuinely postdate this freeze point"
    )
    fresh_would_escape = fresh_attributed_at <= frozen_before_the_edge
    assert not fresh_would_escape, (
        "FIX-A must excuse a row whose attributing edge is genuinely new, exactly "
        "like today's live BWXT rows (grc1-2431cef9…, grc1-81a1a8df…)"
    )

    # Fail-closed: an unresolvable ownership_path_refs entry must never excuse
    # silently -- it is not evidence of anything, so softening the gate here
    # would reopen the exact hole this fix closes.
    tampered_row = dict(incident_row)
    tampered_row["ownership_path_refs"] = ["edge:does-not-exist"]
    with pytest.raises(AssertionError, match="does not resolve"):
        _attributing_path_known_at(tampered_row, incident_edges_by_id)
    empty_row = dict(incident_row)
    empty_row["ownership_path_refs"] = []
    with pytest.raises(AssertionError, match="no ownership_path_refs"):
        _attributing_path_known_at(empty_row, incident_edges_by_id)


def test_live_bwxt_candidates_are_excused_by_their_own_fresh_ownership_edges() -> None:
    """FIX-A verification (a): today's two BWXT rows, against the real payload.

    Confirms the row-level discriminator excuses ``grc1-2431cef9…`` and
    ``grc1-81a1a8df…`` because the five BWXT identifier/ownership rows they
    attribute through carry ``known_at`` 2026-08-19T05:44:34 -- after the
    committed ``candidate_projection_state.json`` freeze at
    2026-08-19T05:25:42 -- not because of anything document-level.
    """
    payload = build_payload(root=ROOT)
    graph = json.loads(
        (ROOT / "data/government_revenue/recipient_entity_graph.json").read_text(encoding="utf-8")
    )
    rows = build_candidate_observations(payload, graph, generated_at=payload["generated_at"])
    bwxt_rows = [row for row in rows if row["ticker"] == "BWXT"]
    assert {row["candidate_id"] for row in bwxt_rows} == {
        "grc1-2431cef9fbca1f209edb0f45",
        "grc1-81a1a8df4bdb97de3b1cdfa8",
    }
    ownership_edges_by_id = {edge["edge_id"]: edge for edge in graph["ownership_edges"]}
    frozen_generated_at = datetime.fromisoformat(
        json.loads(
            (ROOT / "data/government_revenue/candidate_projection_state.json").read_text(
                encoding="utf-8"
            )
        )["generated_at"]
    )
    for row in bwxt_rows:
        attributed_at = _attributing_path_known_at(row, ownership_edges_by_id)
        assert attributed_at > frozen_generated_at, (
            f"{row['candidate_id']} must be excused: its attributing BWXT edges "
            f"({row['ownership_path_refs']}) postdate the frozen projection"
        )


def test_exact_receipt_bound_reviewed_event_builds_one_context_candidate() -> None:
    candidate_rows = build_candidate_observations(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)

    assert len(candidate_rows) == 1
    candidate = candidate_rows[0]
    assert candidate["candidate_family"] == "award_obligation_change"
    assert candidate["ticker"] == "NOC"
    assert candidate["materiality"] == {
        "observed_event_amount": 125000000.0,
        "attributable_amount": 125000000.0,
        "economic_share": 1.0,
        "issuer_attributed_denominator": None,
        "materiality_ratio": None,
        "comparison_state": "not_comparable",
        "reason_code": "exact_issuer_attributed_denominator_not_available",
    }
    assert candidate["authority"]["can_originate_signal"] is False
    assert candidate["authority"]["can_add_candidates"] is False
    assert SHA_A in candidate["artifact_content_ids"]
    assert is_valid_candidate_payload(candidate)


@pytest.mark.parametrize(
    ("event_type", "expected_family", "expected_direction"),
    [
        ("obligation", "award_obligation_change", "possible_positive"),
        ("deobligation", "award_obligation_change", "possible_negative"),
        ("ceiling_changed", "award_ceiling_change", "possible_positive"),
        ("option_exercised", "option_exercise", "possible_positive"),
        ("new_award", "new_award", "possible_positive"),
    ],
)
def test_supported_event_families_have_exact_reviewed_candidate_mapping(
    event_type: str, expected_family: str, expected_direction: str
) -> None:
    candidate = build_candidate_observations(
        _payload(_award_event(event_type=event_type)), _graph(), generated_at=GENERATED_AT
    )[0]

    assert candidate["candidate_family"] == expected_family
    assert candidate["transmission_direction"] == expected_direction
    assert candidate["is_neuralweb_trade_candidate"] is False


@pytest.mark.parametrize(
    ("mutation", "description"),
    [
        (lambda event: event["evidence"].update({"mapping_class": "deterministic_inference"}), "fuzzy mapping"),
        (lambda event: event["evidence"].update({"receipts": []}), "missing receipt"),
        (lambda event: event["award_change"].update({"is_late_discovery": True}), "late new award"),
        (lambda event: event["listed_company_impacts"][0].update({"ownership_path": []}), "missing ownership path"),
    ],
)
def test_candidate_engine_fails_closed_when_exact_eligibility_breaks(mutation, description: str) -> None:
    event = _award_event(event_type="new_award")
    mutation(event)

    assert build_candidate_observations(_payload(event), _graph(), generated_at=GENERATED_AT) == [], description


def test_candidate_known_at_waits_for_every_graph_and_receipt_claim() -> None:
    graph = _graph()
    graph["graph_known_at"] = "2026-08-02T18:00:00+00:00"
    graph["companies"][0]["known_at"] = "2026-08-02T18:00:00+00:00"
    graph["ownership_edges"][0]["known_at"] = "2026-08-02T18:00:00+00:00"
    graph["legal_entities"][0]["known_at"] = "2026-08-02T18:00:00+00:00"
    graph["identifiers"][0]["known_at"] = "2026-08-02T18:00:00+00:00"
    graph["evidence"][0]["known_at"] = "2026-08-02T18:00:00+00:00"

    candidate = build_candidate_observations(
        _payload(_award_event()), graph, generated_at=GENERATED_AT
    )[0]

    assert candidate["source_event"]["known_at"] == KNOWN_AT
    assert candidate["known_at"] == "2026-08-02T18:00:00+00:00"


def test_candidate_rejects_unverified_impact_evidence_reference() -> None:
    event = _award_event()
    event["listed_company_impacts"][0]["evidence_refs"] = ["unverified-future-proof"]

    assert build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    ) == []


def test_candidate_known_at_waits_for_impact_specific_graph_evidence() -> None:
    event = _award_event()
    event["listed_company_impacts"][0]["evidence_refs"] = ["evidence:impact-later"]
    graph = _graph()
    graph["graph_known_at"] = "2026-08-02T18:00:00+00:00"
    graph["evidence"].append({
        "evidence_id": "evidence:impact-later",
        "source_ref": f"recipient-evidence:sha256:{SHA_B}",
        "publisher": "SEC",
        "evidence_class": "official_filing",
        "record_id": "0000000000-26-000002",
        "url": "https://www.sec.gov/Archives/edgar/data/1/impact-later.htm",
        "content_sha256": SHA_B,
        "byte_length": 101,
        "retrieved_at": "2026-08-02T18:00:00+00:00",
        "claim_scopes": ["public_company"],
        "known_at": "2026-08-02T18:00:00+00:00",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "valid_to": None,
    })

    candidate = build_candidate_observations(
        _payload(event), graph, generated_at=GENERATED_AT
    )[0]

    assert candidate["known_at"] == "2026-08-02T18:00:00+00:00"
    assert "evidence:impact-later" in candidate["issuer_resolution_ref"]["evidence_refs"]


def test_candidate_accepts_exact_official_receipt_url_as_impact_evidence() -> None:
    event = _award_event()
    receipt_url = event["evidence"]["receipts"][0]["url"]
    event["listed_company_impacts"][0]["evidence_refs"] = [receipt_url]

    candidate = build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    )[0]

    assert receipt_url in candidate["issuer_resolution_ref"]["evidence_refs"]


def test_graph_revision_creates_a_new_immutable_observation_identity() -> None:
    event = _award_event()
    first_graph = _graph()
    second_graph = _graph()
    second_graph["graph_id"] = "recipient-graph:test-noc-revised"
    second_graph["graph_known_at"] = "2026-08-02T18:00:00+00:00"
    second_graph["evidence"].append({
        "evidence_id": "evidence:noc-revision",
        "source_ref": f"recipient-evidence:sha256:{'c' * 64}",
        "publisher": "SEC",
        "evidence_class": "official_filing",
        "record_id": "0000000000-26-000003",
        "url": "https://www.sec.gov/Archives/edgar/data/1/revision.htm",
        "content_sha256": "c" * 64,
        "byte_length": 102,
        "retrieved_at": "2026-08-02T18:00:00+00:00",
        "claim_scopes": ["public_company"],
        "known_at": "2026-08-02T18:00:00+00:00",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "valid_to": None,
    })
    second_graph["companies"][0]["evidence_refs"].append("evidence:noc-revision")
    second_graph["companies"][0]["known_at"] = "2026-08-02T18:00:00+00:00"

    first = build_candidate_observations(_payload(event), first_graph, generated_at=GENERATED_AT)[0]
    second = build_candidate_observations(_payload(event), second_graph, generated_at=GENERATED_AT)[0]

    assert first["candidate_id"] == second["candidate_id"]
    assert first["observation_id"] != second["observation_id"]
    assert first["issuer_resolution_ref"]["graph_digest"] != second["issuer_resolution_ref"]["graph_digest"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda event: event["listed_company_impacts"][0]["ownership_path"][0].update(
            {"parent_company_id": "issuer:lmt"}
        ),
        lambda event: event["listed_company_impacts"][0]["ownership_path"][0].update(
            {"economic_share": 0.5}
        ),
        lambda event: event["evidence"]["receipts"][0].update(
            {"record_id": "UNRELATED_AWARD"}
        ),
        lambda event: event["award_change"]["source_identity"].update(
            {"content_sha256": "c" * 64}
        ),
        lambda event: event["amounts"][0].update(
            {"source_ref": "receipt:unrelated"}
        ),
    ],
)
def test_candidate_rechecks_graph_path_and_receipt_binding(mutation) -> None:
    event = _award_event()
    mutation(event)

    assert build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    ) == []


def test_mapping_backlog_keeps_fuzzy_discovery_out_of_issuer_attribution() -> None:
    backlog = build_mapping_backlog(_payload(), _graph())

    assert [row["ticker"] for row in backlog] == ["LMT", "NOC"]
    assert backlog[0]["source_association_method"] == "curated_fuzzy_name"
    assert backlog[0]["issuer_attribution"] == "not_asserted"
    assert "exact_identifier_mapping_required" in backlog[0]["reason_codes"]
    assert backlog[1]["mapping_state"] == "partial_identifier_coverage"
    assert backlog[1]["reason_codes"] == ["partial_identifier_coverage"]


def test_candidate_schema_rejects_trade_authority_or_borrowed_materiality_ratio() -> None:
    candidate = build_candidate_observations(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)[0]
    authority_mutation = deepcopy(candidate)
    authority_mutation["authority"]["can_gate"] = True
    ratio_mutation = deepcopy(candidate)
    ratio_mutation["materiality"]["materiality_ratio"] = 0.1

    assert not is_valid_candidate_payload(authority_mutation)
    assert not is_valid_candidate_payload(ratio_mutation)


def test_queue_is_deterministic_and_never_an_investment_rank() -> None:
    first = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    second = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)

    assert first == second
    assert first["counts"]["exact_linked"] == 1
    assert first["counts"]["mapping_needed"] == 2
    assert first["coverage"]["reviewed_issuer_tickers"] == ["NOC"]
    assert first["display_sort"]["is_investment_rank"] is False
    assert first["authority"]["can_rank"] is False


def test_queue_schema_keeps_committed_v1_compatible_and_admits_typed_suppression_receipt() -> None:
    legacy = build_candidate_queue(
        _payload(_award_event()),
        _graph(),
        generated_at=GENERATED_AT,
    )
    assert "historical_candidate_suppression" not in legacy["coverage"]
    assert is_valid_candidate_queue(legacy)

    manifest_path = (
        ROOT
        / "config/government_revenue/candidate_historical_suppressions.v1.json"
    )
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    typed = deepcopy(legacy)
    typed["coverage"]["historical_candidate_suppression"] = {
        "contract": "government_revenue.candidate_historical_suppression_application.v1",
        "manifest_sha256": sha256(manifest_raw).hexdigest(),
        "policy": "exact_source_identity_only",
        "decision": "do_not_backfill",
        "predecessor_queue_content_id": manifest["predecessor"]["queue_content_id"],
        "prior_frozen_at": manifest["predecessor"]["projection_generated_at"],
        "manifest_entry_count": len(manifest["entries"]),
        "matched_count": len(manifest["entries"]),
        "inactive_count": 0,
        "entries": deepcopy(manifest["entries"]),
        "activation": candidate_historical_suppression_activation(
            manifest,
            sha256(manifest_raw).hexdigest(),
            activated_at=manifest["reviewed_at"],
        ),
    }
    typed["source_content_ids"].append(
        "candidate-suppression-manifest-sha256:" + sha256(manifest_raw).hexdigest()
    )
    typed["source_content_ids"].sort()
    typed["content_id"] = candidate_queue_content_id(typed)
    assert is_valid_candidate_queue(typed)

    malformed = deepcopy(typed)
    del malformed["coverage"]["historical_candidate_suppression"]["entries"][0][
        "source_event_id"
    ]
    malformed["content_id"] = candidate_queue_content_id(malformed)
    assert not is_valid_candidate_queue(malformed)


def test_queue_content_id_excludes_delivery_clock_but_detects_data_mutation() -> None:
    queue = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    regenerated = deepcopy(queue)
    regenerated["generated_at"] = "2026-08-04T07:00:00+00:00"
    regenerated["candidates"][0]["generated_at"] = "2026-08-04T07:00:00+00:00"

    assert candidate_queue_content_id(regenerated) == queue["content_id"]
    assert is_valid_candidate_queue(regenerated)

    mutated = deepcopy(queue)
    mutated["candidates"][0]["ticker"] = "LMT"
    assert not is_valid_candidate_queue(mutated)


# --- Identity basis on the candidate --------------------------------------
#
# An action-rail candidate can only be exact-linked through the award's
# recipient of record. The link is exact, and the candidate says so out loud
# rather than letting a reader assume the transaction named its own recipient.


def test_candidate_carries_the_award_level_basis_in_provenance_and_limitations() -> None:
    event = _award_event()
    event["listed_company_impacts"][0]["identity_basis"] = "award_level_recipient_at_collection"

    candidate = build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    )[0]

    assert candidate["issuer_resolution_ref"]["identity_basis"] == (
        "award_level_recipient_at_collection"
    )
    assert candidate["coverage"]["exact_link_status"] == "exact_linked"
    assert any(
        "award's recipient of record as collected" in limitation
        for limitation in candidate["limitations"]
    )
    assert is_valid_candidate_payload(candidate)


def test_transaction_asserted_basis_carries_no_award_level_limitation() -> None:
    event = _award_event()
    event["listed_company_impacts"][0]["identity_basis"] = "source_record_recipient"

    candidate = build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    )[0]

    assert candidate["issuer_resolution_ref"]["identity_basis"] == "source_record_recipient"
    assert not any(
        "recipient of record as collected" in limitation
        for limitation in candidate["limitations"]
    )
    assert is_valid_candidate_payload(candidate)


def test_unnamed_basis_is_carried_as_null_and_an_unreadable_one_fails_closed() -> None:
    unnamed = build_candidate_observations(
        _payload(_award_event()), _graph(), generated_at=GENERATED_AT
    )[0]
    assert unnamed["issuer_resolution_ref"]["identity_basis"] is None
    assert is_valid_candidate_payload(unnamed)

    event = _award_event()
    event["listed_company_impacts"][0]["identity_basis"] = "trust_me"
    assert build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    ) == []


def test_candidate_contract_rejects_an_invented_identity_basis() -> None:
    event = _award_event()
    event["listed_company_impacts"][0]["identity_basis"] = "award_level_recipient_at_collection"
    candidate = build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    )[0]

    invented = deepcopy(candidate)
    invented["issuer_resolution_ref"]["identity_basis"] = "whatever"
    assert not is_valid_candidate_payload(invented)
# ---------------------------------------------------------------------------
# The snapshot rail's admitted families.
#
# The action rail carries no recipient UEI today, so the snapshot rail is the
# only rail whose events can reach an exact reviewed issuer at all.  These
# fixtures are curator-faithful: the terminal ownership edge is
# ``issuer_legal_entity`` (what the recipient-graph curator mints), and the
# events carry a prior and a current receipt exactly as a snapshot before/after
# event does.  They are deliberately scoped at the candidates layer, which does
# not re-validate the procurement-event schema, because that schema's
# ownership-path ``relationship`` enum is being widened for
# ``issuer_legal_entity`` in a sibling lane.
# ---------------------------------------------------------------------------

SHA_PRIOR = "d" * 64
SHA_CURRENT = "e" * 64
SNAPSHOT_AWARD_KEY = "CONT_AWD_SNAP_001"
SNAPSHOT_URL = f"https://api.usaspending.gov/api/v2/awards/{SNAPSHOT_AWARD_KEY}/"
PRIOR_KNOWN_AT = "2026-08-01T12:00:00+00:00"


def _issuer_legal_entity_graph() -> dict:
    """The curator's terminal edge shape: issuer legal entity, whole economics."""
    graph = _graph()
    graph["ownership_edges"][0]["relationship"] = "issuer_legal_entity"
    return graph


def _issuer_legal_entity_path() -> list[dict]:
    path = _ownership_path()
    path[0]["relationship"] = "issuer_legal_entity"
    return path


def _snapshot_amount(
    identifier: str, value: float, semantic: str
) -> dict:
    return {
        "id": identifier,
        "label_code": identifier,
        "value": value,
        "currency": "USD",
        "semantic": semantic,
        "as_of": EFFECTIVE_AT,
        "is_lower_bound": False,
        "source_ref": SNAPSHOT_URL,
    }


def _snapshot_event(
    *,
    event_type: str,
    amounts: list[dict],
    primary_amount_id: str,
    event_id: str = "govws-snapshot-obligation-1",
    late: bool = False,
) -> dict:
    """A receipt-bound snapshot-rail award-change event, before/after bound."""
    return {
        "kind": "award_change",
        "event_id": event_id,
        "record_id": f"award:{SNAPSHOT_AWARD_KEY}",
        "change": {
            "type": event_type,
            "effective_at": EFFECTIVE_AT,
            "known_at": KNOWN_AT,
            "what_changed_en": "Reported obligated balance changed",
        },
        "award_change": {
            "award_key": SNAPSHOT_AWARD_KEY,
            "generated_award_id": SNAPSHOT_AWARD_KEY,
            "piid": "PIID-SNAP-001",
            "event_type": event_type,
            "secondary_types": [],
            "source_rail": "usaspending_award_snapshot",
            "observation_kind": "snapshot",
            "source_identity": {
                "id": SNAPSHOT_AWARD_KEY,
                "version": "state-v2",
                "content_sha256": SHA_CURRENT,
            },
            "is_late_discovery": late,
        },
        "primary_amount_id": primary_amount_id,
        "amounts": amounts,
        "listed_company_impacts": [
            {
                "ticker": "NOC",
                "company_name": "Northrop Grumman Corporation",
                "issuer_company_id": "issuer:noc",
                "relation_semantic": "reviewed",
                "resolution_state": "reviewed",
                "ownership_path": _issuer_legal_entity_path(),
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "evidence": {
            "source_class": "official_fact",
            "mapping_class": "reviewed",
            "conflicts": [],
            "receipts": [
                {
                    "ref_id": "receipt:snapshot:current",
                    "publisher": "USAspending.gov",
                    "record_id": SNAPSHOT_AWARD_KEY,
                    "url": SNAPSHOT_URL,
                    "effective_at": EFFECTIVE_AT,
                    "known_at": KNOWN_AT,
                    "retrieved_at": KNOWN_AT,
                    "content_sha256": SHA_CURRENT,
                },
                {
                    "ref_id": "receipt:snapshot:prior",
                    "publisher": "USAspending.gov",
                    "record_id": SNAPSHOT_AWARD_KEY,
                    "url": SNAPSHOT_URL,
                    "effective_at": PRIOR_KNOWN_AT,
                    "known_at": PRIOR_KNOWN_AT,
                    "retrieved_at": PRIOR_KNOWN_AT,
                    "content_sha256": SHA_PRIOR,
                },
            ],
        },
    }


def _obligation_balance_event(delta: float = 75_000_000.0) -> dict:
    """The snapshot analogue of an action-rail obligation/deobligation."""
    return _snapshot_event(
        event_type="reported_obligation_balance_changed",
        primary_amount_id="delta_total_obligated_amount",
        amounts=[
            _snapshot_amount(
                "delta_total_obligated_amount",
                delta,
                "award_cumulative_delta_derived_from_official_before_after",
            ),
            _snapshot_amount("current_award_amount", 400_000_000.0, "official"),
            _snapshot_amount("potential_award_amount", 900_000_000.0, "official"),
            _snapshot_amount("total_obligated_amount", 300_000_000.0, "official"),
        ],
    )


def _compound_value_event(*, with_ceiling_component: bool = True) -> dict:
    """A compound move: BOTH award values changed on one snapshot revision."""
    amounts = [
        _snapshot_amount(
            "delta_current_award_amount",
            40_000_000.0,
            "award_current_value_delta_derived_from_official_before_after",
        ),
        _snapshot_amount("current_award_amount", 400_000_000.0, "official"),
        _snapshot_amount("potential_award_amount", 900_000_000.0, "official"),
    ]
    if with_ceiling_component:
        amounts.insert(
            1,
            _snapshot_amount(
                "delta_potential_award_amount",
                150_000_000.0,
                "award_ceiling_delta_derived_from_official_before_after",
            ),
        )
    return _snapshot_event(
        event_type="award_value_changed",
        primary_amount_id="delta_current_award_amount",
        amounts=amounts,
        event_id="govws-snapshot-value-1",
    )


def _multi_event_payload(events: list[dict]) -> dict:
    payload = _payload()
    payload["procurement_workspace"]["events"] = events
    return payload


def test_snapshot_rail_obligation_balance_change_is_an_obligation_candidate() -> None:
    """The snapshot rail's obligation semantic was excluded by accident.

    ``reported_obligation_balance_changed`` is the same economic fact the action
    rail publishes as ``obligation``, read off the award's reported cumulative
    balance.  Excluding it left the ONLY rail carrying exact recipient
    identifiers unable to emit a single candidate.
    """
    candidates = build_candidate_observations(
        _multi_event_payload([_obligation_balance_event()]),
        _issuer_legal_entity_graph(),
        generated_at=GENERATED_AT,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["candidate_family"] == "award_obligation_change"
    assert candidate["transmission_direction"] == "possible_positive"
    assert candidate["source_event"]["event_type"] == "reported_obligation_balance_changed"
    assert candidate["source_event"]["source_rail"] == "usaspending_award_snapshot"
    assert candidate["source_event"]["amount"]["amount_id"] == "delta_total_obligated_amount"
    assert candidate["source_event"]["amount"]["semantic"] == (
        "award_cumulative_delta_derived_from_official_before_after"
    )
    assert candidate["materiality"]["observed_event_amount"] == 75_000_000.0
    assert is_valid_candidate_payload(candidate)


@pytest.mark.parametrize(
    ("delta", "expected_direction"),
    [
        (75_000_000.0, "possible_positive"),
        (-75_000_000.0, "possible_negative"),
        (0.0, "unknown"),
    ],
)
def test_snapshot_obligation_direction_is_read_from_the_delta_sign(
    delta: float, expected_direction: str
) -> None:
    """One snapshot type carries both directions, so only the sign can say which.

    The action rail splits the two into ``obligation``/``deobligation``; reading
    the snapshot type alone would publish every balance CUT as a possible
    positive.
    """
    candidate = build_candidate_observations(
        _multi_event_payload([_obligation_balance_event(delta)]),
        _issuer_legal_entity_graph(),
        generated_at=GENERATED_AT,
    )[0]

    assert candidate["transmission_direction"] == expected_direction
    assert candidate["earnings_transmission"]["direction"] == expected_direction
    assert candidate["materiality"]["observed_event_amount"] == delta
    assert is_valid_candidate_payload(candidate)


def test_compound_value_change_is_admitted_as_its_contained_ceiling_change() -> None:
    """A ceiling change may not vanish because a second field moved with it.

    ``ceiling_changed`` (potential only) was admitted while ``award_value_
    changed`` (potential AND current) was dropped -- so a compound change that
    STRICTLY CONTAINS an admitted one produced nothing.  The candidate carries
    only the ceiling component; the current-value component stays on the event.
    """
    candidate = build_candidate_observations(
        _multi_event_payload([_compound_value_event()]),
        _issuer_legal_entity_graph(),
        generated_at=GENERATED_AT,
    )[0]

    assert candidate["candidate_family"] == "award_ceiling_change"
    assert candidate["source_event"]["event_type"] == "award_value_changed"
    assert candidate["source_event"]["source_rail"] == "usaspending_award_snapshot"
    # The event's own primary amount is the current-value delta.  The candidate
    # must NOT inherit it: that is a different economic claim.
    assert candidate["source_event"]["amount"]["amount_id"] == "delta_potential_award_amount"
    assert candidate["source_event"]["amount"]["semantic"] == (
        "award_ceiling_delta_derived_from_official_before_after"
    )
    assert candidate["source_event"]["amount"]["value"] == 150_000_000.0
    assert candidate["materiality"]["observed_event_amount"] == 150_000_000.0
    assert candidate["materiality"]["attributable_amount"] == 150_000_000.0
    assert 40_000_000.0 not in _numbers(candidate)
    assert is_valid_candidate_payload(candidate)


def test_compound_value_change_without_its_ceiling_component_emits_nothing() -> None:
    """Fail closed rather than fall back to the current-value delta."""
    graph = _issuer_legal_entity_graph()

    assert build_candidate_observations(
        _multi_event_payload([_compound_value_event(with_ceiling_component=False)]),
        graph,
        generated_at=GENERATED_AT,
    ) == []
    # Control: the SAME event with its ceiling component does emit, so the
    # refusal above is the missing amount and not some other eligibility break.
    assert len(build_candidate_observations(
        _multi_event_payload([_compound_value_event()]), graph, generated_at=GENERATED_AT
    )) == 1


def test_late_discovery_is_a_disclosure_state_not_an_admitted_family() -> None:
    """``award_discovered_late`` says WHEN we first saw an award, not what moved."""
    graph = _issuer_legal_entity_graph()
    amounts = [
        _snapshot_amount(
            "delta_total_obligated_amount",
            75_000_000.0,
            "award_cumulative_delta_derived_from_official_before_after",
        ),
        _snapshot_amount("current_award_amount", 400_000_000.0, "official"),
    ]
    late_event = _snapshot_event(
        event_type="award_discovered_late",
        primary_amount_id="delta_total_obligated_amount",
        amounts=amounts,
        event_id="govws-snapshot-late-1",
        late=True,
    )

    assert build_candidate_observations(
        _multi_event_payload([late_event]), graph, generated_at=GENERATED_AT
    ) == []
    # Control: the same event under an admitted type -- still late-discovered --
    # DOES emit, and carries the lateness as a disclosed FIELD.  So the refusal
    # above is the family decision, and lateness itself is not what refuses.
    admitted = deepcopy(late_event)
    admitted["award_change"]["event_type"] = "reported_obligation_balance_changed"
    admitted["change"]["type"] = "reported_obligation_balance_changed"
    disclosed = build_candidate_observations(
        _multi_event_payload([admitted]), graph, generated_at=GENERATED_AT
    )
    assert len(disclosed) == 1
    assert disclosed[0]["source_event"]["is_late_discovery"] is True


def _numbers(node) -> list[float]:
    """Every finite number anywhere in a payload, for aggregation tripwires."""
    if isinstance(node, bool):
        return []
    if isinstance(node, (int, float)):
        return [float(node)]
    if isinstance(node, dict):
        return [value for child in node.values() for value in _numbers(child)]
    if isinstance(node, list):
        return [value for child in node for value in _numbers(child)]
    return []


def test_queue_admits_both_snapshot_families_and_never_sums_across_rails() -> None:
    """The queue counts candidates; it never adds their amounts together.

    A snapshot ``total_obligated_amount`` move is a CUMULATIVE balance's delta
    and an action rail's ``federal_action_obligation`` is a single TRANSACTION.
    Adding them double-counts the same dollars, so the two must stay separately
    labelled and no published figure may be their sum.
    """
    action_event = _award_event()
    action_event["listed_company_impacts"][0]["ownership_path"] = _issuer_legal_entity_path()
    queue = build_candidate_queue(
        _multi_event_payload([action_event, _obligation_balance_event(), _compound_value_event()]),
        _issuer_legal_entity_graph(),
        generated_at=GENERATED_AT,
    )

    by_rail = {
        row["source_event"]["source_rail"]: row for row in queue["candidates"]
        if row["candidate_family"] == "award_obligation_change"
    }
    assert queue["counts"]["total"] == 3
    assert queue["counts"]["by_family"] == {
        "award_ceiling_change": 1,
        "award_obligation_change": 2,
    }
    assert queue["freshness"]["exact_candidate_availability"] == "available"
    assert set(by_rail) == {"usaspending_award_action", "usaspending_award_snapshot"}

    action = by_rail["usaspending_award_action"]
    snapshot = by_rail["usaspending_award_snapshot"]
    assert action["source_event"]["amount"]["semantic"] != snapshot["source_event"]["amount"]["semantic"]
    assert action["materiality"]["observed_event_amount"] == 125_000_000.0
    assert snapshot["materiality"]["observed_event_amount"] == 75_000_000.0
    # No published figure anywhere in the queue is the cross-rail sum, nor the
    # all-candidate sum: the queue aggregates COUNTS, never money.
    forbidden = {125_000_000.0 + 75_000_000.0, 125_000_000.0 + 75_000_000.0 + 150_000_000.0}
    assert forbidden.isdisjoint(set(_numbers(queue)))
    assert is_valid_candidate_queue(queue)
