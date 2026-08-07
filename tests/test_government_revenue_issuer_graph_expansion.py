"""Wave 9D — the fences on exact-identifier issuer graph expansion.

WHAT THIS SUITE IS FOR.  Wave 9D widens the reviewed recipient graph beyond its
single issuer.  The whole value of that widening is that it does NOT come from
the cheap association already sitting in the repo: every one of the 21 companies
in `data/government_revenue/latest.json` carries
`entity_match.method == "curated_fuzzy_name"`, and a fuzzy name is not issuer
attribution.  So this suite's job is to pin the refusals, not the arithmetic.

An edge is admissible only when an EXACT identifier (SAM UEI or CAGE) on an
official USAspending recipient record is tied to a legal entity name appearing
verbatim in the issuer's own SEC Exhibit 21, under case/whitespace/punctuation
normalization plus at most one trailing legal-form suffix.  Everything else --
`discovery_query_ticker`, name similarity, web-search snippets, an LLM assertion,
and any name needing a transformation beyond that -- is recorded as a rejection.

No test here touches the network.  A module-wide socket fence makes that a
property of the suite rather than a promise in a docstring, and the collector's
retrieval is exercised through its injectable `fetch` against committed
fixtures.

Run: python3 -m pytest tests/test_government_revenue_issuer_graph_expansion.py -q
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import socket

import pandas as pd
import pytest

from collectors import issuer_evidence
from collectors.issuer_evidence import (
    MAX_RECIPIENT_QUERY_FORMS,
    SEC_MIN_INTERVAL_SECONDS,
    USASPENDING_MIN_INTERVAL_SECONDS,
    IssuerEvidenceCollector,
    append_issuer_evidence_receipts,
    build_evidence_receipt,
    evidence_store_path,
    parse_exhibit21_names,
    parse_recipient_records,
    parse_ticker_cik_map,
    read_verified_evidence,
    recipient_query_forms,
    select_exhibit21_document,
    select_latest_10k,
    store_evidence_document,
)
from engine.government_revenue import point_in_time
from engine.government_revenue.candidates import build_candidate_observations
from engine.government_revenue.entity_resolution import load_recipient_entity_graph
from engine.government_revenue.issuer_graph_expansion import (
    PROPOSED_STATE,
    REVIEWED_STATES,
    ExpansionInputError,
    ProposalAuthorityError,
    assert_unreviewed,
    build_issuer_coverage,
    build_proposal_ledger,
    evidence_receipt_is_valid,
    is_attributable_at,
    name_match_tier,
    normalize_legal_name,
    proposal_ledger_as_graph,
    resolve_issuer_edges,
    verify_evidence_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "issuer_evidence"

# Clocks. Every one is explicit: the module fails closed on a missing clock, and
# a test that leaned on "now" would stop meaning anything the day after it ran.
ENTITY_VALID_FROM = "2025-12-31T00:00:00+00:00"
RECORD_VALID_FROM = "2026-01-15T00:00:00+00:00"
EVIDENCE_KNOWN_AT = "2026-07-01T00:00:00+00:00"
LEDGER_KNOWN_AT = "2026-08-01T00:00:00+00:00"
EVENT_AT = "2026-08-02T00:00:00+00:00"
ANALYSIS_AS_OF = "2026-08-03"
GENERATED_AT = "2026-08-03T07:00:00+00:00"

SHA_10K = "a" * 64
SHA_EX21 = "b" * 64
SHA_AWARD = "c" * 64
SHA_ACTION = "d" * 64

EXHIBIT_NAME = "Vanguard Defense Systems, Inc."
RECIPIENT_UEI = "ABCDEFGHJKLM"


# ─────────────────────────────────────────────────────────────────────────────
# Gate 7: the suite may not reach the network.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse every outbound socket for the whole module.

    The collector's real rails are SEC EDGAR and USAspending; both are live
    services with rate limits and a User-Agent requirement.  Retrieval is
    exercised only through the injectable ``fetch`` against committed fixtures,
    and this fence is what makes "no network" checkable instead of asserted.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "Wave 9D tests must not touch the network; drive the collector's "
            "injectable fetch against tests/fixtures/issuer_evidence/ instead."
        )

    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def test_collector_has_no_module_level_network_client_and_no_default_fetch() -> None:
    """Retrieval is opt-in by injection; importing the module opens nothing."""
    assert issuer_evidence.__dict__.get("requests") is None
    assert IssuerEvidenceCollector().fetch is None


def test_the_network_fence_actually_bites() -> None:
    """Non-vacuity for the fixture above: prove the fence is live in this module."""
    with pytest.raises(AssertionError, match="must not touch the network"):
        socket.create_connection(("api.usaspending.gov", 443))


# ─────────────────────────────────────────────────────────────────────────────
# Scenario builders.
# ─────────────────────────────────────────────────────────────────────────────

def _issuer(**overrides: object) -> dict:
    return {
        "ticker": "VGD",
        "cik": "0001368622",
        "company_id": "issuer:vgd",
        "registrant_name": "Vanguard Defense Holdings, Inc.",
        "evidence_refs": ["evidence:vgd-sec-10k"],
        **overrides,
    }


def _exhibit_entity(name: str = EXHIBIT_NAME, **overrides: object) -> dict:
    return {
        "legal_name": name,
        "entity_id": "entity:vgd-defense-systems",
        "entity_role": "subsidiary",
        "evidence_refs": ["evidence:vgd-sec-ex21"],
        "valid_from": ENTITY_VALID_FROM,
        "valid_to": None,
        "known_at": EVIDENCE_KNOWN_AT,
        **overrides,
    }


def _recipient(name: str = EXHIBIT_NAME, **overrides: object) -> dict:
    return {
        "legal_name": name,
        "uei": RECIPIENT_UEI,
        "evidence_refs": ["evidence:vgd-usaspending-recipient"],
        "valid_from": RECORD_VALID_FROM,
        "valid_to": None,
        "known_at": EVIDENCE_KNOWN_AT,
        **overrides,
    }


def _evidence_rows() -> list[dict]:
    """Evidence in the recipient-graph row shape, so only review state can fail.

    The graph loader enforces a closed field set, an https URL on the
    publisher's own host, and a digest-derived ``source_ref``.  Building these
    rows correctly is what lets the proposed-vs-reviewed tests below isolate the
    review state as the single thing standing between this artifact and a
    candidate.
    """
    return [
        {
            "evidence_id": "evidence:vgd-sec-10k",
            "source_ref": f"recipient-evidence:sha256:{SHA_10K}",
            "publisher": "SEC",
            "evidence_class": "official_filing",
            "record_id": "sec:1368622:000110465926000001:vgd-20251231x10k.htm",
            "url": "https://www.sec.gov/Archives/edgar/data/1368622/000110465926000001/vgd-20251231x10k.htm",
            "content_sha256": SHA_10K,
            "byte_length": 4303986,
            "retrieved_at": EVIDENCE_KNOWN_AT,
            "claim_scopes": ["public_company", "legal_entity", "ownership"],
            "known_at": EVIDENCE_KNOWN_AT,
            "valid_from": ENTITY_VALID_FROM,
            "valid_to": None,
        },
        {
            "evidence_id": "evidence:vgd-sec-ex21",
            "source_ref": f"recipient-evidence:sha256:{SHA_EX21}",
            "publisher": "SEC",
            "evidence_class": "official_filing",
            "record_id": "sec:1368622:000110465926000001:vgd-20251231xex21d1.htm",
            "url": "https://www.sec.gov/Archives/edgar/data/1368622/000110465926000001/vgd-20251231xex21d1.htm",
            "content_sha256": SHA_EX21,
            "byte_length": 12265,
            "retrieved_at": EVIDENCE_KNOWN_AT,
            "claim_scopes": ["legal_entity", "ownership"],
            "known_at": EVIDENCE_KNOWN_AT,
            "valid_from": ENTITY_VALID_FROM,
            "valid_to": None,
        },
        {
            "evidence_id": "evidence:vgd-usaspending-recipient",
            "source_ref": f"recipient-evidence:sha256:{SHA_AWARD}",
            "publisher": "USAspending.gov",
            "evidence_class": "official_award",
            "record_id": "usaspending:recipient:ABCDEFGHJKLM",
            "url": "https://api.usaspending.gov/api/v2/recipient/",
            "content_sha256": SHA_AWARD,
            "byte_length": 6603,
            "retrieved_at": EVIDENCE_KNOWN_AT,
            "claim_scopes": ["legal_entity", "exact_identifier", "ownership"],
            "known_at": EVIDENCE_KNOWN_AT,
            "valid_from": RECORD_VALID_FROM,
            "valid_to": None,
        },
    ]


def _resolve(
    *,
    issuer: dict | None = None,
    entities: list[dict] | None = None,
    recipients: list[dict] | None = None,
) -> dict:
    return resolve_issuer_edges(
        issuer=issuer if issuer is not None else _issuer(),
        exhibit_entities=entities if entities is not None else [_exhibit_entity()],
        recipient_records=recipients if recipients is not None else [_recipient()],
    )


def _ledger(resolution: dict | None = None) -> dict:
    resolved = resolution if resolution is not None else _resolve()
    return build_proposal_ledger(
        generated_at=LEDGER_KNOWN_AT,
        known_at=LEDGER_KNOWN_AT,
        issuers=[{"issuer": _issuer(), "resolution": resolved, "coverage": None}],
        evidence=_evidence_rows(),
    )


def _reviewed(graph: dict) -> dict:
    """Promote every review state in a graph -- the operator's act, simulated.

    This is deliberately the ONLY difference between the graph that must not
    produce a candidate and the graph that must.  It lives in the test, never in
    the pipeline: `assert_unreviewed` exists to stop the pipeline doing it.
    """
    promoted = deepcopy(graph)
    for key in ("companies", "legal_entities", "identifiers", "ownership_edges"):
        for row in promoted[key]:
            if row.get("verification_state") == PROPOSED_STATE:
                row["verification_state"] = "reviewed"
    return promoted


def _award_event(proposal: dict) -> dict:
    """An award event that CLAIMS a reviewed link to the proposal's own path.

    The event JSON asserting `reviewed` is precisely the forgery the second
    admission boundary exists to refuse; the graph, not the event, decides.
    """
    return {
        "kind": "award_change",
        "event_id": "govawd-vgd-001",
        "record_id": "CONT_AWD_VGD_0001",
        "change": {
            "type": "obligation",
            "effective_at": EVENT_AT,
            "known_at": EVENT_AT,
            "what_changed_en": "Official obligation increase observed",
        },
        "award_change": {
            "event_type": "obligation",
            "source_rail": "usaspending_award_action",
            "source_identity": {"id": "action:1", "version": "1", "content_sha256": SHA_ACTION},
            "is_late_discovery": False,
        },
        "primary_amount_id": "amount:obligation",
        "amounts": [
            {
                "id": "amount:obligation",
                "value": 88000000.0,
                "currency": "USD",
                "semantic": "federal_action_obligation_delta",
                "as_of": EVENT_AT,
                "source_ref": "receipt:action:1",
            }
        ],
        "listed_company_impacts": [
            {
                "ticker": "VGD",
                "company_name": "Vanguard Defense Holdings, Inc.",
                "issuer_company_id": "issuer:vgd",
                "relation_semantic": "reviewed",
                "resolution_state": "reviewed",
                "ownership_path": deepcopy(proposal["ownership_path"]),
                "evidence_refs": list(proposal["evidence_refs"]),
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
                    "record_id": "CONT_AWD_VGD_0001",
                    "url": "https://api.usaspending.gov/api/v2/transactions/",
                    "effective_at": EVENT_AT,
                    "known_at": EVENT_AT,
                    "retrieved_at": EVENT_AT,
                    "content_sha256": SHA_ACTION,
                }
            ],
        },
    }


def _latest_payload(event: dict) -> dict:
    return {
        "as_of": ANALYSIS_AS_OF,
        "known_at": EVENT_AT,
        "companies": [
            {"ticker": "VGD", "name": "Vanguard Defense Holdings, Inc.",
             "entity_match": {"method": "curated_fuzzy_name"}},
        ],
        "procurement_workspace": {
            "bundle_id": "grw2-vgd0000000000000000000",
            "freshness": {"award_events": {"status": "ok"}},
            "events": [event],
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Gate 1a: the positive control. An exact pair IS admitted.
# ─────────────────────────────────────────────────────────────────────────────

def test_exact_identifier_plus_verbatim_exhibit_name_proposes_one_edge() -> None:
    """Every refusal below is only meaningful against a case that succeeds.

    Without this, a resolver that returned zero edges for everything would pass
    the entire rejection half of this suite.
    """
    result = _resolve()

    assert len(result["proposals"]) == 1
    assert result["rejections"] == []
    assert result["ambiguous"] == []
    proposal = result["proposals"][0]
    assert proposal["admission"]["tier"] == "exact_verbatim_name"
    assert proposal["admission"]["rule"] == "exact_identifier_plus_verbatim_issuer_exhibit_name"
    assert proposal["identifiers"] == [
        {
            "identifier_id": "identifier:entity:vgd-defense-systems:sam_uei:abcdefghjklm",
            "entity_id": "entity:vgd-defense-systems",
            "namespace": "sam_uei",
            "value": RECIPIENT_UEI,
            "verification_state": PROPOSED_STATE,
        }
    ]
    assert proposal["review_status"] == PROPOSED_STATE
    assert proposal["issuer_attribution"] == "not_asserted"
    assert proposal["candidate_eligibility"]["is_eligible"] is False


@pytest.mark.parametrize(
    ("recipient_name", "why"),
    [
        ("VANGUARD DEFENSE SYSTEMS, INC.", "case only"),
        ("vanguard   defense   systems inc", "whitespace and punctuation only"),
        ("Vanguard Defense Systems Inc.", "punctuation only"),
    ],
)
def test_orthographic_difference_alone_is_still_the_same_verbatim_name(
    recipient_name: str, why: str
) -> None:
    """Case, whitespace, and punctuation are the permitted normalization tier."""
    result = _resolve(recipients=[_recipient(recipient_name)])

    assert len(result["proposals"]) == 1, why
    assert result["proposals"][0]["admission"]["tier"] == "exact_verbatim_name"


# ─────────────────────────────────────────────────────────────────────────────
# Gate 1b: a name needing more than orthography + one legal suffix is refused.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("recipient_name", "transformation"),
    [
        ("Systems Defense Vanguard, Inc.", "token reordering"),
        ("Vanguard Systems, Inc.", "token deletion"),
        ("Vanguard Defense Systems Group, Inc.", "token insertion"),
        ("Vanguard Def. Systems, Inc.", "abbreviation expansion"),
        ("Vanguard Defence Systems, Inc.", "one-character edit distance"),
        ("VDS, Inc.", "acronym expansion"),
        ("Vanguard Armaments Systems, Inc.", "synonym substitution"),
        ("Vanguard Defense Systems of Delaware, Inc.", "substring containment"),
        ("Vanguard Defense", "prefix containment"),
    ],
)
def test_a_name_needing_more_than_orthography_cannot_become_an_edge(
    recipient_name: str, transformation: str
) -> None:
    """Every one of these is a *similarity* judgement. None may produce an edge.

    The rejection is RECORDED with its reason, not silently dropped: an issuer
    whose evidence did not support attribution has to be visibly unattributed,
    otherwise a thin graph is indistinguishable from a broken one.
    """
    result = _resolve(recipients=[_recipient(recipient_name)])

    assert result["proposals"] == [], f"{transformation} produced an edge"
    assert [row["reason_code"] for row in result["rejections"]] == [
        "name_not_in_issuer_exhibit"
    ]
    assert result["rejections"][0]["recipient_legal_name"] == recipient_name
    assert result["rejections"][0]["issuer_attribution"] == "not_asserted"


def test_dropping_one_legal_form_suffix_is_the_second_admissible_tier() -> None:
    """The shape the suffix tier exists for, and the only shape it admits.

    USAspending registers plenty of recipients without the designator the
    issuer's exhibit spells out. Bridging that is orthography; bridging two
    DIFFERENT designators is not (see below).
    """
    result = _resolve(recipients=[_recipient("Vanguard Defense Systems")])

    assert len(result["proposals"]) == 1
    assert result["proposals"][0]["admission"]["tier"] == "exact_suffix_normalized_name"


@pytest.mark.parametrize(
    ("exhibit_name", "recipient_name"),
    [
        ("L3Harris Technologies Limited", "L3HARRIS TECHNOLOGIES, INC"),
        ("Vanguard Defense Systems, Inc.", "Vanguard Defense Systems LLC"),
        ("Vanguard Defense Systems GmbH", "Vanguard Defense Systems Pty"),
    ],
)
def test_two_different_legal_forms_are_two_different_legal_persons(
    exhibit_name: str, recipient_name: str
) -> None:
    """Regression from the live 2026-08-07 collection run.

    A two-sided suffix rule proposed `L3Harris Technologies Limited` -- the UK
    subsidiary named in LHX's own Exhibit 21 -- as the same entity as recipient
    `L3HARRIS TECHNOLOGIES, INC`, the US parent. It was the only edge that run
    produced, and it was wrong. A legal-form designator is part of the entity's
    identity, not decoration.
    """
    assert name_match_tier(exhibit_name, recipient_name) is None

    result = _resolve(
        entities=[_exhibit_entity(exhibit_name)],
        recipients=[_recipient(recipient_name)],
    )
    assert result["proposals"] == []
    assert [row["reason_code"] for row in result["rejections"]] == [
        "name_not_in_issuer_exhibit"
    ]


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Systems Defense Vanguard Inc", "Vanguard Defense Systems, Inc."),
        ("Vanguard Defence Systems Inc", "Vanguard Defense Systems, Inc."),
        ("Vanguard Def Systems Inc", "Vanguard Defense Systems, Inc."),
        ("Vanguard Defense", "Vanguard Defense Systems, Inc."),
    ],
)
def test_the_matcher_itself_offers_no_third_looser_tier(left: str, right: str) -> None:
    """`name_match_tier` returns a tier or None. There is no partial credit.

    Pinned separately from the resolver because the two are different fences.
    The resolver ADMITS through its name buckets; `name_match_tier` is the
    pairwise re-derivation that a bucket hit must survive. Loosening only the
    matcher adds no edges (measured: it moves one assertion in this file);
    loosening only the buckets adds edges the re-derivation then throws out.
    Both have to be pinned, because a change that loosens both -- which is what
    someone "fixing" a bucket that stopped matching would write -- is the one
    that ships wrong edges.
    """
    assert name_match_tier(left, right) is None


def test_normalization_is_symmetric_and_does_not_reorder() -> None:
    """The one permitted transformation, pinned as a property.

    Two names that normalize equal differ ONLY in case, spacing, and
    punctuation -- so normalization can never be the thing that makes two
    different names look like one.
    """
    assert normalize_legal_name("Vanguard  Defense-Systems, Inc.") == "vanguard defense systems inc"
    assert normalize_legal_name("VANGUARD DEFENSE SYSTEMS INC") == "vanguard defense systems inc"
    assert normalize_legal_name("Systems Defense Vanguard Inc") != "vanguard defense systems inc"
    assert normalize_legal_name("   ") is None


# ─────────────────────────────────────────────────────────────────────────────
# Gate 1c: forbidden provenance is refused at the door, on every row kind.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        ({"discovery_query_ticker": "VGD"}, "forbidden_provenance_key_present"),
        ({"query_ticker": "VGD"}, "forbidden_provenance_key_present"),
        ({"similarity": 0.97}, "forbidden_provenance_key_present"),
        ({"similarity_score": 0.97}, "forbidden_provenance_key_present"),
        ({"name_similarity": 0.97}, "forbidden_provenance_key_present"),
        ({"match_score": 0.97}, "forbidden_provenance_key_present"),
        ({"fuzzy_score": 0.97}, "forbidden_provenance_key_present"),
        ({"confidence_score": 0.97}, "forbidden_provenance_key_present"),
        ({"search_snippet": "Vanguard is a defense prime"}, "forbidden_provenance_key_present"),
        ({"web_snippet": "Vanguard is a defense prime"}, "forbidden_provenance_key_present"),
        ({"llm_rationale": "I know this company"}, "forbidden_provenance_key_present"),
        ({"model_rationale": "I know this company"}, "forbidden_provenance_key_present"),
        ({"association_method": "discovery_query_ticker"}, "fuzzy_association_input_forbidden"),
        ({"association_method": "curated_fuzzy_name"}, "fuzzy_association_input_forbidden"),
        ({"association_method": "fuzzy_name"}, "fuzzy_association_input_forbidden"),
        ({"association_method": "name_similarity"}, "fuzzy_association_input_forbidden"),
        ({"association_method": "web_search"}, "fuzzy_association_input_forbidden"),
        ({"association_method": "llm_assertion"}, "fuzzy_association_input_forbidden"),
        ({"association_method": "analyst_recollection"}, "fuzzy_association_input_forbidden"),
        ({"match_method": "LLM"}, "fuzzy_association_input_forbidden"),
    ],
)
def test_a_recipient_row_with_non_exact_provenance_is_refused_and_recorded(
    overrides: dict, expected_reason: str
) -> None:
    """A row whose NAME matches exactly is still refused on its provenance.

    This is the load-bearing shape of the test: the name is the admissible one,
    so the only thing that can be rejecting the row is the forbidden input.
    """
    result = _resolve(recipients=[_recipient(**overrides)])

    assert result["proposals"] == []
    assert [row["reason_code"] for row in result["rejections"]] == [expected_reason]


def test_discovery_query_ticker_on_the_issuer_row_stops_the_whole_resolution() -> None:
    """The ticker that found a recipient may never be the reason it is attributed.

    SEC's own ticker->CIK map is the one place a ticker is allowed to act, and
    that is a lookup of the registrant, not of a recipient.
    """
    result = _resolve(issuer=_issuer(discovery_query_ticker="VGD"))

    assert result["proposals"] == []
    assert result["rejections"][0]["reason_code"] == "forbidden_provenance_key_present"


def test_an_exhibit_row_carrying_a_similarity_score_is_refused() -> None:
    """The refusal covers the issuer's side of the join too, not just recipients."""
    result = _resolve(entities=[_exhibit_entity(similarity_score=0.99)])

    assert result["proposals"] == []
    # Two recorded refusals, both correct: the exhibit row is refused on its
    # provenance, and the recipient then has no admissible exhibit name to meet.
    assert {row["reason_code"] for row in result["rejections"]} == {
        "forbidden_provenance_key_present",
        "name_not_in_issuer_exhibit",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Gate 1d: exactness of the identifier, and ambiguity in either direction.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        ({"uei": None}, "recipient_identifier_absent"),
        ({"uei": "TOOSHORT"}, "recipient_identifier_invalid"),
        ({"uei": "ABCDEFGHJKL!"}, "recipient_identifier_invalid"),
        ({"uei": None, "cage": "12AB"}, "recipient_identifier_invalid"),
    ],
)
def test_a_name_match_without_a_valid_exact_identifier_is_not_an_edge(
    overrides: dict, expected_reason: str
) -> None:
    """A verbatim name alone is not admissible. The identifier is the join key."""
    result = _resolve(recipients=[_recipient(**overrides)])

    assert result["proposals"] == []
    assert [row["reason_code"] for row in result["rejections"]] == [expected_reason]


def test_a_name_matching_two_exhibit_entities_is_ambiguous_not_a_coin_flip() -> None:
    """Two subsidiaries whose names collapse to one core cannot be told apart.

    The honest output is `ambiguous` -- a first-class recorded state -- not a
    pick of whichever row the parser happened to see first.
    """
    result = _resolve(
        entities=[
            _exhibit_entity("Vanguard Defense Systems, Inc.", entity_id="entity:a"),
            _exhibit_entity("Vanguard Defense Systems LLC", entity_id="entity:b"),
        ],
        recipients=[_recipient("Vanguard Defense Systems Corporation")],
    )

    assert result["proposals"] == []
    assert [row["reason_code"] for row in result["ambiguous"]] == [
        "ambiguous_name_matches_multiple_issuer_entities"
    ]


def test_two_recipients_sharing_one_name_are_ambiguous_in_the_other_direction() -> None:
    """Uniqueness is required on BOTH sides; two UEIs for one name is a tie."""
    result = _resolve(
        recipients=[
            _recipient("Vanguard Defense Systems Corporation", uei=RECIPIENT_UEI),
            _recipient("Vanguard Defense Systems Company", uei="NOPQRSTUVWXY"),
        ],
    )

    assert result["proposals"] == []
    assert {row["reason_code"] for row in result["ambiguous"]} == {
        "ambiguous_name_matches_multiple_recipients"
    }


def test_evidence_is_required_on_both_sides_of_every_edge() -> None:
    """An edge with nothing to re-open is not reviewable, so it is not proposed."""
    without_recipient_evidence = _resolve(recipients=[_recipient(evidence_refs=[])])
    without_exhibit_evidence = _resolve(entities=[_exhibit_entity(evidence_refs=[])])

    assert without_recipient_evidence["proposals"] == []
    assert [row["reason_code"] for row in without_recipient_evidence["rejections"]] == [
        "recipient_evidence_missing"
    ]
    assert without_exhibit_evidence["proposals"] == []
    assert "issuer_evidence_missing" in {
        row["reason_code"] for row in without_exhibit_evidence["rejections"]
    }


def test_every_recipient_record_lands_in_exactly_one_outcome_bucket() -> None:
    """Nothing is dropped. A thin graph must be explained row by row."""
    recipients = [
        _recipient(EXHIBIT_NAME),
        _recipient("Systems Defense Vanguard, Inc.", uei="NOPQRSTUVWXY"),
        _recipient("Vanguard Defense Systems, Inc.", uei=None, cage=None,
                   evidence_refs=["evidence:vgd-usaspending-recipient"]),
        _recipient("Unrelated Holdings, Inc.", uei="ZYXWVUTSRQPN",
                   discovery_query_ticker="VGD"),
    ]

    result = _resolve(recipients=recipients)

    total = len(result["proposals"]) + len(result["rejections"]) + len(result["ambiguous"])
    assert total == len(recipients)
    assert len(result["proposals"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Gate 2: point in time. A 2026 mapping cannot reach a 2023 award.
# ─────────────────────────────────────────────────────────────────────────────

def _pit_edge() -> dict:
    return _resolve()["proposals"][0]["ownership_path"][0]


def test_a_mapping_first_valid_in_2026_does_not_attribute_a_2023_award() -> None:
    """The core PIT claim, at the edge level.

    `valid_from` is compared against the award's EFFECTIVE date, not against the
    day the query runs, so learning an ownership fact today can never reach
    backward over an obligation that predates the evidence for it.
    """
    edge = _pit_edge()
    assert edge["valid_from"] == RECORD_VALID_FROM

    assert is_attributable_at(
        edge, effective_at="2023-06-15T00:00:00+00:00", known_at="2026-08-06T00:00:00+00:00"
    ) is False
    assert is_attributable_at(
        edge, effective_at="2026-05-01T00:00:00+00:00", known_at="2026-08-06T00:00:00+00:00"
    ) is True


def test_the_pit_join_takes_the_2026_award_and_leaves_the_2023_one() -> None:
    """The same claim as a join, and its counterfactual in the same test.

    The last assertion is the non-vacuity half: it shows that a join which reads
    the CURRENT mapping instead of the edge's validity window sweeps up both
    awards.  Without it, `["award-2026"]` would also be the answer if the 2023
    row had simply been missing from the frame.
    """
    edge = _pit_edge()
    awards = pd.DataFrame(
        [
            {"award_id": "award-2023", "recipient_uei": RECIPIENT_UEI,
             "action_date": "2023-06-15T00:00:00+00:00", "known_at": "2023-07-01T00:00:00+00:00"},
            {"award_id": "award-2026", "recipient_uei": RECIPIENT_UEI,
             "action_date": "2026-05-01T00:00:00+00:00", "known_at": "2026-05-15T00:00:00+00:00"},
        ]
    )

    visible = point_in_time.filter_dual_clock(
        awards, knowledge_cutoff="2026-08-06", effective_cutoff="2026-08-06"
    )
    attributed = [
        row["award_id"]
        for _, row in visible.iterrows()
        if is_attributable_at(
            edge, effective_at=row["_pit_effective_at"], known_at="2026-08-06T00:00:00+00:00"
        )
    ]

    assert attributed == ["award-2026"]
    # Counterfactual: ignoring the edge window is what would attribute both.
    assert list(visible["award_id"]) == ["award-2023", "award-2026"]


def test_an_edge_learned_after_the_replay_clock_is_invisible_to_that_replay() -> None:
    """The knowledge clock is separate from the effective clock and also binds."""
    edge = _pit_edge()

    assert is_attributable_at(
        edge, effective_at="2026-05-01T00:00:00+00:00", known_at="2026-06-01T00:00:00+00:00"
    ) is False


def test_a_retired_edge_stops_attributing_after_its_valid_to() -> None:
    """A divested subsidiary must stop being the issuer's, on the award's clock."""
    result = _resolve(
        entities=[_exhibit_entity(valid_to="2026-06-30T00:00:00+00:00")],
        recipients=[_recipient(valid_to="2026-06-30T00:00:00+00:00")],
    )
    edge = result["proposals"][0]["ownership_path"][0]

    assert edge["valid_to"] == "2026-06-30T00:00:00+00:00"
    assert is_attributable_at(
        edge, effective_at="2026-05-01T00:00:00+00:00", known_at="2026-08-06T00:00:00+00:00"
    ) is True
    assert is_attributable_at(
        edge, effective_at="2026-07-15T00:00:00+00:00", known_at="2026-08-06T00:00:00+00:00"
    ) is False


@pytest.mark.parametrize(
    "clock_overrides",
    [
        {"known_at": None},
        {"valid_from": None},
    ],
)
def test_a_missing_clock_fails_closed_rather_than_defaulting(clock_overrides: dict) -> None:
    """No clock means no window, which means no edge -- never "assume always"."""
    edge = {**_pit_edge(), **clock_overrides}

    assert is_attributable_at(
        edge, effective_at="2026-05-01T00:00:00+00:00", known_at="2026-08-06T00:00:00+00:00"
    ) is False


def test_the_validity_window_starts_at_the_LATER_of_the_two_evidence_dates() -> None:
    """Both sides must support the claim; the weaker clock governs.

    The exhibit proves ownership as of its period of report and the recipient
    record proves the identifier as of its own observation.  Taking the earlier
    of the two would back-date a mapping onto evidence that did not yet exist.
    """
    result = _resolve(
        entities=[_exhibit_entity(valid_from="2024-01-01T00:00:00+00:00")],
        recipients=[_recipient(valid_from="2026-03-01T00:00:00+00:00")],
    )

    assert result["proposals"][0]["valid_from"] == "2026-03-01T00:00:00+00:00"


def test_an_inverted_window_is_a_recorded_rejection_not_a_repaired_edge() -> None:
    result = _resolve(
        entities=[_exhibit_entity(valid_to="2024-01-01T00:00:00+00:00")],
        recipients=[_recipient(valid_from="2026-03-01T00:00:00+00:00")],
    )

    assert result["proposals"] == []
    assert [row["reason_code"] for row in result["rejections"]] == [
        "validity_window_unsupported"
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Gate 3: a proposed edge cannot become a candidate, through the real path.
# ─────────────────────────────────────────────────────────────────────────────

def test_the_proposal_artifact_is_rejected_by_the_graph_loader_as_unreviewed() -> None:
    """Shaped exactly like a recipient graph, and refused on review state alone."""
    graph = proposal_ledger_as_graph(_ledger())

    loaded = load_recipient_entity_graph(graph, as_of=ANALYSIS_AS_OF)

    assert loaded["status"] == "invalid"
    assert set(loaded["error_codes"]) == {
        "company_not_reviewed",
        "entity_not_reviewed",
        "identifier_not_reviewed",
        "ownership_not_reviewed",
    }


def test_a_proposed_edge_produces_no_candidate_through_the_real_engine() -> None:
    """Gate 3, driven through `engine.government_revenue.candidates` itself.

    The award event is receipt-bound, its ownership path is copied verbatim from
    the proposal, and its JSON claims `resolution_state: reviewed`.  The only
    thing wrong with it is that the graph says `proposed`.
    """
    resolution = _resolve()
    ledger = _ledger(resolution)
    event = _award_event(resolution["proposals"][0])

    candidates = build_candidate_observations(
        _latest_payload(event), proposal_ledger_as_graph(ledger), generated_at=GENERATED_AT
    )

    assert candidates == []


def test_the_same_event_becomes_a_candidate_once_an_operator_reviews_the_graph() -> None:
    """Non-vacuity for the test above -- the single-variable control.

    If this failed, the empty result above would prove nothing: a malformed
    fixture returns [] just as convincingly as an enforced fence.  The ONLY
    difference between the two graphs is the review state.
    """
    resolution = _resolve()
    ledger = _ledger(resolution)
    event = _award_event(resolution["proposals"][0])
    graph = proposal_ledger_as_graph(ledger)

    assert load_recipient_entity_graph(_reviewed(graph), as_of=ANALYSIS_AS_OF)["status"] == "ready"
    candidates = build_candidate_observations(
        _latest_payload(event), _reviewed(graph), generated_at=GENERATED_AT
    )

    assert len(candidates) == 1
    assert candidates[0]["ticker"] == "VGD"
    assert candidates[0]["authority"]["can_originate_signal"] is False
    assert candidates[0]["authority"]["can_add_candidates"] is False


@pytest.mark.parametrize(
    ("row_kind", "expected_error"),
    [
        ("companies", "company_not_reviewed"),
        ("legal_entities", "entity_not_reviewed"),
        ("identifiers", "identifier_not_reviewed"),
        ("ownership_edges", "ownership_not_reviewed"),
    ],
)
def test_demoting_any_single_row_to_proposed_kills_the_candidate(
    row_kind: str, expected_error: str
) -> None:
    """Each row kind carries its own fence, so no one of them can be skipped.

    A composite "is the graph reviewed" check would pass this suite while
    leaving three of the four row types unguarded.
    """
    resolution = _resolve()
    event = _award_event(resolution["proposals"][0])
    graph = _reviewed(proposal_ledger_as_graph(_ledger(resolution)))
    for row in graph[row_kind]:
        row["verification_state"] = PROPOSED_STATE

    loaded = load_recipient_entity_graph(graph, as_of=ANALYSIS_AS_OF)
    candidates = build_candidate_observations(
        _latest_payload(event), graph, generated_at=GENERATED_AT
    )

    assert loaded["status"] == "invalid"
    assert expected_error in loaded["error_codes"]
    assert candidates == []


def test_the_proposal_ledger_says_out_loud_that_nothing_is_candidate_eligible() -> None:
    ledger = _ledger()

    assert ledger["counts"]["reviewed_edges"] == 0
    assert ledger["counts"]["proposed_edges"] == 1
    assert ledger["issuers"][0]["candidate_eligibility"] == {
        "is_eligible": False,
        "reason_code": "edges_awaiting_operator_review",
        "explanation": (
            "Exact edges are proposed with complete evidence and remain "
            "ineligible for candidate attribution until an operator reviews them."
        ),
    }
    assert ledger["authority"]["can_add_candidates"] is False
    assert ledger["authority"]["can_originate_signal"] is False
    assert ledger["authority"]["tier"] == "display"


# ─────────────────────────────────────────────────────────────────────────────
# Gate 4: `assert_unreviewed` fires.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("state", sorted(REVIEWED_STATES))
def test_assert_unreviewed_raises_on_every_state_that_means_an_operator_looked(
    state: str,
) -> None:
    """Constructed ledger carrying a reviewed state -> ProposalAuthorityError."""
    ledger = _ledger()
    ledger["issuers"][0]["proposed_edges"][0]["review_status"] = state

    with pytest.raises(ProposalAuthorityError, match="may only emit 'proposed'"):
        assert_unreviewed(ledger)


def test_assert_unreviewed_reaches_a_reviewed_state_nested_in_an_ownership_edge() -> None:
    """The check walks the whole payload; burying the claim does not hide it."""
    ledger = _ledger()
    ledger["issuers"][0]["proposed_edges"][0]["ownership_path"][0]["verification_state"] = "confirmed"

    with pytest.raises(ProposalAuthorityError, match="may only emit 'proposed'"):
        assert_unreviewed(ledger)


def test_naming_a_reviewer_is_itself_the_forbidden_act() -> None:
    """Review is the operator's act; a pipeline cannot self-attest to it."""
    ledger = _ledger()
    ledger["issuers"][0]["proposed_edges"][0]["reviewer"] = "government-revenue-bot"

    with pytest.raises(ProposalAuthorityError, match="cannot be self-asserted"):
        assert_unreviewed(ledger)


def test_an_unknown_review_state_is_refused_rather_than_treated_as_harmless() -> None:
    ledger = _ledger()
    ledger["issuers"][0]["proposed_edges"][0]["review_status"] = "probably_fine"

    with pytest.raises(ProposalAuthorityError, match="unknown review state"):
        assert_unreviewed(ledger)


def test_build_proposal_ledger_runs_the_fence_on_its_own_output() -> None:
    """The fence is wired, not merely available.

    A resolution that arrived carrying a reviewed state raises instead of
    shipping -- this is the difference between a helper that exists and a
    helper that runs.
    """
    resolution = _resolve()
    resolution["proposals"][0]["verification_state"] = "analyst_approved"

    with pytest.raises(ProposalAuthorityError):
        _ledger(resolution)


def test_the_ledger_that_does_ship_carries_only_proposed_states() -> None:
    ledger = _ledger()

    assert assert_unreviewed(ledger) is None
    assert ledger["review_status"] == PROPOSED_STATE
    assert ledger["issuers"][0]["proposed_edges"][0]["verification_state"] == PROPOSED_STATE


# ─────────────────────────────────────────────────────────────────────────────
# Gate 5: coverage. Two ratios, two inputs, and an honest `partial`.
# ─────────────────────────────────────────────────────────────────────────────

def test_dollar_coverage_and_entity_coverage_are_computed_from_separate_inputs() -> None:
    """One exact edge can carry nearly all the money and almost none of the entities.

    AeroVironment's live 2026 exhibit is the shape this exists for: a table that
    yields one clean legal name and collapses twenty-three more into a single
    cell.  Reporting 97% of dollars as though it were 97% of the company is the
    error; both numbers are reported, neither substitutes for the other.
    """
    coverage = build_issuer_coverage(
        issuer_ticker="VGD",
        exhibit_entity_names=[
            "Vanguard Defense Systems, Inc.",
            "Vanguard Space & Sensing LLC",
            "Vanguard International Holdings Limited",
            "Vanguard Robotics, Inc.",
        ],
        proposed_entity_names=["Vanguard Defense Systems, Inc."],
        recipient_award_amounts={"sam_uei:ABCDEFGHJKLM": 970.0, "sam_uei:NOPQRSTUVWXY": 30.0},
        proposed_identifiers=["sam_uei:ABCDEFGHJKLM"],
    )

    assert coverage["entity_coverage"]["covered"] == 1
    assert coverage["entity_coverage"]["total"] == 4
    assert coverage["entity_coverage"]["ratio"] == 0.25
    assert coverage["award_dollar_coverage"]["ratio"] == 0.97
    assert coverage["coverage_state"] == "partial"
    assert coverage["is_complete"] is False


@pytest.mark.parametrize(
    ("proposed_names", "proposed_identifiers", "unresolved", "why"),
    [
        (["Vanguard Defense Systems, Inc."], ["sam_uei:ABCDEFGHJKLM"], 0, "entities short"),
        (["Vanguard Defense Systems, Inc.", "Vanguard Space & Sensing LLC"],
         ["sam_uei:ABCDEFGHJKLM"], 0, "dollars short"),
        (["Vanguard Defense Systems, Inc.", "Vanguard Space & Sensing LLC"],
         ["sam_uei:ABCDEFGHJKLM", "sam_uei:NOPQRSTUVWXY"], 1, "an unresolved row remains"),
    ],
)
def test_an_issuer_can_be_exactly_partial_and_is_never_reported_complete(
    proposed_names: list[str], proposed_identifiers: list[str], unresolved: int, why: str
) -> None:
    """`complete` requires BOTH ratios at exactly 1.0 and nothing unresolved."""
    coverage = build_issuer_coverage(
        issuer_ticker="VGD",
        exhibit_entity_names=["Vanguard Defense Systems, Inc.", "Vanguard Space & Sensing LLC"],
        proposed_entity_names=proposed_names,
        recipient_award_amounts={"sam_uei:ABCDEFGHJKLM": 600.0, "sam_uei:NOPQRSTUVWXY": 400.0},
        proposed_identifiers=proposed_identifiers,
        unresolved_count=unresolved,
    )

    assert coverage["coverage_state"] == "partial", why
    assert coverage["is_complete"] is False, why


def test_complete_is_reachable_so_partial_is_a_measurement_not_a_constant() -> None:
    """Non-vacuity: a function that never says `complete` would pass the above."""
    coverage = build_issuer_coverage(
        issuer_ticker="VGD",
        exhibit_entity_names=["Vanguard Defense Systems, Inc."],
        proposed_entity_names=["VANGUARD DEFENSE SYSTEMS INC"],
        recipient_award_amounts={"sam_uei:ABCDEFGHJKLM": 600.0},
        proposed_identifiers=["sam_uei:ABCDEFGHJKLM"],
    )

    assert coverage["coverage_state"] == "complete"
    assert coverage["is_complete"] is True


def test_an_issuer_with_no_exact_edge_reports_none_rather_than_a_silent_zero() -> None:
    coverage = build_issuer_coverage(
        issuer_ticker="VGD",
        exhibit_entity_names=["Vanguard Defense Systems, Inc."],
        proposed_entity_names=[],
        recipient_award_amounts={"sam_uei:ABCDEFGHJKLM": 600.0},
        proposed_identifiers=[],
    )

    assert coverage["coverage_state"] == "none"
    assert coverage["entity_coverage"]["ratio"] == 0.0
    assert coverage["award_dollar_coverage"]["ratio"] == 0.0


def test_a_proposed_name_outside_the_exhibit_cannot_inflate_entity_coverage() -> None:
    """Coverage is measured against the issuer's own filing, not against itself."""
    coverage = build_issuer_coverage(
        issuer_ticker="VGD",
        exhibit_entity_names=["Vanguard Defense Systems, Inc."],
        proposed_entity_names=["Vanguard Defense Systems, Inc.", "Some Other Corporation"],
        recipient_award_amounts={"sam_uei:ABCDEFGHJKLM": 600.0},
        proposed_identifiers=["sam_uei:ABCDEFGHJKLM"],
    )

    assert coverage["entity_coverage"]["covered"] == 1
    assert coverage["entity_coverage"]["total"] == 1


def test_no_observed_award_dollars_is_a_null_ratio_not_a_complete_issuer() -> None:
    """A null is printed as a null; it must not read as full coverage."""
    coverage = build_issuer_coverage(
        issuer_ticker="VGD",
        exhibit_entity_names=["Vanguard Defense Systems, Inc."],
        proposed_entity_names=["Vanguard Defense Systems, Inc."],
        recipient_award_amounts={},
        proposed_identifiers=["sam_uei:ABCDEFGHJKLM"],
    )

    assert coverage["award_dollar_coverage"]["ratio"] is None
    assert coverage["is_complete"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Gate 6: evidence integrity. A stored document is re-hashed, and tampering fails.
# ─────────────────────────────────────────────────────────────────────────────

def test_a_stored_evidence_document_is_re_verified_and_tampering_fails(tmp_path: Path) -> None:
    """The re-verification contract, exercised on a committed exhibit fixture.

    An edge that rests on a document nobody can reproduce is not reviewable, so
    the store is content-addressed and the read re-hashes rather than trusting
    the filename it was given.
    """
    body = (FIXTURES / "exhibit21_sample.htm").read_bytes()
    receipt = build_evidence_receipt(
        evidence_id="evidence:vgd-sec-ex21",
        publisher="SEC",
        evidence_class="official_filing",
        record_id="sec:1368622:000110465926000001:vgd-20251231xex21d1.htm",
        url="https://www.sec.gov/Archives/edgar/data/1368622/000110465926000001/vgd-20251231xex21d1.htm",
        body=body,
        retrieved_at=EVIDENCE_KNOWN_AT,
        valid_from=ENTITY_VALID_FROM,
        claim_scopes=["legal_entity", "ownership"],
    )
    digest = receipt["content_sha256"]
    path = store_evidence_document(tmp_path, body)

    assert evidence_receipt_is_valid(receipt)
    assert verify_evidence_bytes(receipt, body) is True
    assert read_verified_evidence(tmp_path, digest) == body
    assert path == evidence_store_path(tmp_path, digest)

    path.write_bytes(body.replace(b"Vanguard Defense Systems", b"Vanguard Offense Systems"))

    assert verify_evidence_bytes(receipt, path.read_bytes()) is False
    with pytest.raises(RuntimeError, match="does not match its content address"):
        read_verified_evidence(tmp_path, digest)


def test_a_single_flipped_byte_breaks_the_receipt() -> None:
    """Content addressing, not a length or a name check."""
    body = (FIXTURES / "exhibit21_sample.htm").read_bytes()
    receipt = build_evidence_receipt(
        evidence_id="evidence:vgd-sec-ex21", publisher="SEC",
        evidence_class="official_filing", record_id="sec:1:1:ex21.htm",
        url="https://www.sec.gov/Archives/edgar/data/1/1/ex21.htm", body=body,
        retrieved_at=EVIDENCE_KNOWN_AT, valid_from=ENTITY_VALID_FROM,
        claim_scopes=["legal_entity"],
    )
    tampered = bytearray(body)
    tampered[0] = tampered[0] ^ 0x01

    assert verify_evidence_bytes(receipt, bytes(tampered)) is False
    assert len(tampered) == receipt["byte_length"]


@pytest.mark.parametrize(
    "mutation",
    [
        {"content_sha256": "0" * 64},
        {"source_ref": "recipient-evidence:sha256:" + "0" * 64},
        {"byte_length": 0},
        {"url": "http://www.sec.gov/insecure.htm"},
        {"claim_scopes": []},
        {"retrieved_at": None},
        {"record_id": None},
    ],
)
def test_a_receipt_that_is_not_content_addressed_and_clock_bound_is_invalid(
    mutation: dict,
) -> None:
    body = (FIXTURES / "exhibit21_sample.htm").read_bytes()
    receipt = build_evidence_receipt(
        evidence_id="evidence:vgd-sec-ex21", publisher="SEC",
        evidence_class="official_filing", record_id="sec:1:1:ex21.htm",
        url="https://www.sec.gov/Archives/edgar/data/1/1/ex21.htm", body=body,
        retrieved_at=EVIDENCE_KNOWN_AT, valid_from=ENTITY_VALID_FROM,
        claim_scopes=["legal_entity"],
    )

    assert evidence_receipt_is_valid({**receipt, **mutation}) is False


def test_the_proposal_ledger_refuses_evidence_that_is_not_hash_bound() -> None:
    rows = _evidence_rows()
    rows[0]["content_sha256"] = "not-a-digest"

    with pytest.raises(ExpansionInputError, match="not content-addressed"):
        build_proposal_ledger(
            generated_at=LEDGER_KNOWN_AT, known_at=LEDGER_KNOWN_AT,
            issuers=[{"issuer": _issuer(), "resolution": _resolve(), "coverage": None}],
            evidence=rows,
        )


def test_the_receipt_ledger_is_append_only_and_fails_closed_on_a_corrupt_history(
    tmp_path: Path,
) -> None:
    """Receipt history is the audit trail; overwriting it would erase the audit."""
    body = (FIXTURES / "exhibit21_sample.htm").read_bytes()
    receipt = build_evidence_receipt(
        evidence_id="evidence:vgd-sec-ex21", publisher="SEC",
        evidence_class="official_filing", record_id="sec:1:1:ex21.htm",
        url="https://www.sec.gov/Archives/edgar/data/1/1/ex21.htm", body=body,
        retrieved_at=EVIDENCE_KNOWN_AT, valid_from=ENTITY_VALID_FROM,
        claim_scopes=["legal_entity"],
    )
    path = tmp_path / "issuer_evidence_receipts.jsonl"

    first = append_issuer_evidence_receipts([receipt], path)
    second = append_issuer_evidence_receipts([receipt], path)

    assert first["new_receipts_this_run"] == 1
    assert second["new_receipts_this_run"] == 0
    assert second["receipts_total"] == 1

    path.write_text("{not json\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        append_issuer_evidence_receipts([receipt], path)


# ─────────────────────────────────────────────────────────────────────────────
# The collector's pure parsers, against committed fixtures only.
# ─────────────────────────────────────────────────────────────────────────────

def test_exhibit21_names_are_read_verbatim_from_the_committed_fixture() -> None:
    parsed = parse_exhibit21_names((FIXTURES / "exhibit21_sample.htm").read_bytes())

    assert parsed["status"] == "parsed"
    assert parsed["names"] == [
        "Vanguard Defense Systems, Inc.",
        "Vanguard Space & Sensing LLC",
        "Vanguard International Holdings Limited",
    ]


def test_an_unparseable_exhibit_yields_zero_names_not_a_guessed_list() -> None:
    """"No subsidiaries found" and "no subsidiaries" are different facts."""
    parsed = parse_exhibit21_names((FIXTURES / "exhibit21_unparseable.htm").read_bytes())

    assert parsed["status"] == "unparseable"
    assert parsed["names"] == []
    assert parsed["reason_code"] == "no_entity_table_rows"


def test_exhibit21_selection_reads_the_filer_declared_type_from_the_header() -> None:
    """Regression: the declared exhibit TYPE lives in the dissemination header.

    Selection previously read the directory listing `index.json`, whose `type`
    key holds the web server's icon name (`text.gif`) and never an exhibit type.
    Against the latest 10-K of LMT, LHX, AVAV, VSAT, and PLTR -- all five of
    which declare an EX-21 -- that returned None every time, so the collector
    could not reach a single subsidiary list.
    """
    document = select_exhibit21_document((FIXTURES / "edgar_index_headers.html").read_bytes())

    assert document == {"name": "vgd-20251231xex21d1.htm", "type": "EX-21.1"}


def test_the_directory_listing_type_key_is_not_an_exhibit_type() -> None:
    """Pins the wrong source, so a revert to it cannot read as working.

    Both payloads describe the SAME filing. One declares EX-21.1; the other
    reports `text.gif` for every document in it.
    """
    directory = json.loads((FIXTURES / "edgar_directory_index.json").read_text(encoding="utf-8"))
    declared_types = {item["type"] for item in directory["directory"]["item"]}

    assert declared_types == {"text.gif", "image2.gif", "compressed.gif"}
    assert not declared_types & {"EX-21", "EX-21.1"}
    assert any(item["name"].endswith("xex21d1.htm") for item in directory["directory"]["item"])


def test_a_filing_declaring_no_exhibit21_selects_nothing_by_filename() -> None:
    """The fixture holds an EX-4.2 whose FILENAME contains "ex21".

    A filename fallback picks it. Reading the declared type refuses, which is
    the correct answer: that filing published no subsidiary list.
    """
    assert select_exhibit21_document(
        (FIXTURES / "edgar_index_headers_no_exhibit21.html").read_bytes()
    ) is None


def test_character_references_are_resolved_inside_a_verbatim_legal_name() -> None:
    """Regression: an unresolved `&#224;` refuses a match between identical names.

    The recipient record spells the entity `Sàrl`. Leaving the exhibit's
    `S&#224;rl` unresolved makes the two normalize differently, so the exact
    match this wave rests on is refused for a name that is in fact the same.
    """
    parsed = parse_exhibit21_names((FIXTURES / "exhibit21_edgar_shapes.htm").read_bytes())

    assert "Vanguard Technologies Geneva Sàrl" in parsed["names"]
    assert "Vanguard Comunicações do Brasil, Ltda." in parsed["names"]
    assert not any("&" in name and ";" in name for name in parsed["names"])
    assert name_match_tier(
        "Vanguard Technologies Geneva Sàrl", "VANGUARD TECHNOLOGIES GENEVA SARL"
    ) is None
    assert name_match_tier(
        "Vanguard Technologies Geneva Sàrl", "Vanguard Technologies Geneva Sàrl"
    ) == "exact_verbatim_name"


def test_a_zero_width_spacer_cell_does_not_swallow_the_name_beside_it() -> None:
    """Regression: EDGAR typesets spacer cells out of `&#8203;`.

    The scan stops at the first non-empty cell. A spacer that survives cleaning
    ends the scan on itself and silently drops the legal name in the next cell,
    which reads downstream as "the issuer has no such subsidiary".
    """
    parsed = parse_exhibit21_names((FIXTURES / "exhibit21_edgar_shapes.htm").read_bytes())

    assert "Vanguard Defense Systems, Inc." in parsed["names"]


def test_many_names_crammed_into_one_cell_are_refused_rather_than_split() -> None:
    """AeroVironment's live 2026 exhibit does exactly this with 23 subsidiaries.

    Splitting invents entity boundaries -- the inference this wave forbids. The
    contract is an honest partial: the cell contributes nothing, and the missing
    entities show up as missing entity coverage rather than as invented names.
    """
    parsed = parse_exhibit21_names((FIXTURES / "exhibit21_edgar_shapes.htm").read_bytes())

    assert len(parsed["names"]) == 3
    assert not any("Vanguard Robotics" in name for name in parsed["names"])
    assert not any("Vanguard Maritime" in name for name in parsed["names"])


def test_the_sec_ticker_map_is_the_only_place_a_ticker_may_act() -> None:
    """An official SEC lookup of the REGISTRANT, never a guess at a recipient."""
    mapping = parse_ticker_cik_map(
        {
            "0": {"cik_str": 1368622, "ticker": "vgd", "title": "Vanguard Defense Holdings"},
            "1": {"cik_str": 936468, "ticker": "LMT", "title": "Lockheed Martin Corp"},
            "2": {"cik_str": "not-a-cik", "ticker": "BAD", "title": "Malformed"},
        }
    )

    assert mapping == {"VGD": "0001368622", "LMT": "0000936468"}


def test_only_a_10k_is_accepted_as_the_source_of_an_exhibit_21() -> None:
    """No other form substitutes; the newest 10-K wins on filing date."""
    submissions = {
        "filings": {
            "recent": {
                "form": ["10-Q", "10-K", "10-K", "8-K"],
                "accessionNumber": [
                    "0001104659-26-000009", "0001104659-25-000001",
                    "0001104659-26-000001", "0001104659-26-000008",
                ],
                "reportDate": ["2026-03-31", "2024-12-31", "2025-12-31", "2026-02-01"],
                "filingDate": ["2026-05-01", "2025-01-29", "2026-01-29", "2026-02-02"],
            }
        }
    }

    assert select_latest_10k(submissions) == {
        "accession": "0001104659-26-000001",
        "accession_plain": "000110465926000001",
        "report_date": "2025-12-31",
        "filing_date": "2026-01-29",
    }
    assert select_latest_10k({"filings": {"recent": {"form": ["10-Q"], "accessionNumber": ["x"]}}}) is None


def test_usaspending_search_results_are_an_enumeration_not_an_assertion() -> None:
    """The endpoint ranks by relevance and returns wholly unrelated recipients.

    Measured against the live API while building this wave: querying an exact
    Lockheed subsidiary name returned state health departments in the top five.
    Nothing here decides a mapping -- admission is the resolver's job.
    """
    rows = parse_recipient_records(
        {
            "results": [
                {"name": "VANGUARD DEFENSE SYSTEMS, INC.", "uei": RECIPIENT_UEI,
                 "recipient_level": "R", "id": "abc-R", "amount": 12345.0},
                {"name": "HEALTH CARE SERVICES, CALIFORNIA DEPARTMENT OF",
                 "uei": "JE73CDQUAPA7", "recipient_level": "R", "id": "def-R",
                 "amount": 116233514292.9},
                {"name": "ARCTURUS UAV, INC.", "uei": None, "recipient_level": "R",
                 "id": "ghi-R", "amount": 0.0},
            ]
        }
    )

    assert [row["legal_name"] for row in rows] == [
        "VANGUARD DEFENSE SYSTEMS, INC.",
        "HEALTH CARE SERVICES, CALIFORNIA DEPARTMENT OF",
        "ARCTURUS UAV, INC.",
    ]
    assert all("issuer" not in row for row in rows)
    # The unrelated recipient is enumerated, and the resolver refuses it.
    refused = _resolve(recipients=[_recipient(rows[1]["legal_name"], uei=rows[1]["uei"])])
    assert refused["proposals"] == []
    assert refused["rejections"][0]["reason_code"] == "name_not_in_issuer_exhibit"


def test_a_recipient_with_no_registered_uei_survives_to_be_refused_by_name() -> None:
    """`recipient_identifier_absent` has to be reachable from real data.

    USAspending publishes recipients carrying no UEI at all; AeroVironment's
    `ARCTURUS UAV, INC.` is one, measured 2026-08-07. Dropping those at the
    collector would make that refusal dead code in production and would shrink
    the coverage denominator to the rows that were already admissible -- an
    issuer would look better covered precisely because evidence was missing.
    """
    rows = parse_recipient_records(
        {"results": [{"name": "ARCTURUS UAV, INC.", "uei": None, "id": "x-R", "amount": 0.0}]}
    )
    assert rows[0]["uei"] is None

    result = _resolve(
        entities=[_exhibit_entity("Arcturus UAV, Inc.")],
        recipients=[_recipient("ARCTURUS UAV, INC.", uei=None)],
    )

    assert result["proposals"] == []
    assert [row["reason_code"] for row in result["rejections"]] == [
        "recipient_identifier_absent"
    ]


def test_the_recipient_query_filters_on_keyword_and_carries_the_exhibit_name() -> None:
    """Regression: `/api/v2/recipient/` IGNORES an unrecognised filter key.

    Sending `search_text` returned page_metadata.total == 18,292,357 -- the
    entire recipient universe -- and therefore the same global top-100 by dollar
    amount for every query, while `keyword` returned 3 for the same name. An
    ignored filter is the worst shape of wrong here: the caller still gets a
    plausible list of real federal recipients, so an enumeration that knows
    nothing about the issuer reads exactly like one that does.

    The test also pins the other half of the rule: the query text comes from the
    issuer's own Exhibit 21, never from a ticker.

    And it pins the union AT THE SAME SITE, because `keyword` being literal is
    also why one spelling is not enough: the exhibit name is queried verbatim
    FIRST and punctuation-stripped SECOND, both as `keyword`, never as
    `search_text`. The two forms here return the same single recipient, so the
    pooled result is ONE row -- the dedupe is what keeps a recipient found twice
    from being resolved twice into two identical proposals.
    """
    sent: list[dict] = []

    def fetch(url: str, body: dict | None) -> tuple[int, bytes]:
        sent.append(dict(body or {}))
        return 200, json.dumps(
            {
                "results": [
                    {"name": "VANGUARD DEFENSE SYSTEMS, INC.", "uei": RECIPIENT_UEI,
                     "recipient_level": "R", "id": "abc-R", "amount": 12345.0}
                ],
                "page_metadata": {"hasNext": False},
            }
        ).encode("utf-8")

    result = IssuerEvidenceCollector(fetch=fetch).recipient_records(EXHIBIT_NAME)

    assert sent[0]["keyword"] == EXHIBIT_NAME
    assert sent[1]["keyword"] == "Vanguard Defense Systems Inc"
    assert "search_text" not in sent[0]
    assert "search_text" not in sent[1]
    assert result["query_forms"] == [EXHIBIT_NAME, "Vanguard Defense Systems Inc"]
    assert result["search_text"] == EXHIBIT_NAME
    assert result["pages_read"] == 2
    assert len(result["records"]) == 1
    assert result["records"][0]["uei"] == RECIPIENT_UEI
    assert len(result["receipts"]) == 2
    assert all(evidence_receipt_is_valid(receipt) for receipt in result["receipts"])
    # Each form's receipt names the query that produced it, so the ledger can
    # show that the second spelling was actually asked and what it answered.
    assert [receipt["record_id"] for receipt in result["receipts"]] == [
        f"usaspending:recipient-search:{EXHIBIT_NAME}:page-1",
        "usaspending:recipient-search:Vanguard Defense Systems Inc:page-1",
    ]
    assert result["receipts"][0]["evidence_id"] != result["receipts"][1]["evidence_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Union retrieval: `keyword` is literal, so ONE spelling is not enough.
#
# The retrieval is unioned, never normalized -- the verbatim exhibit name AND a
# punctuation-stripped form are both asked, and the answers are POOLED into one
# candidate list.  That widens what is LOOKED AT.  Nothing below may widen what
# is ADMITTED, and `engine/government_revenue/issuer_graph_expansion.py` is
# untouched by this change, which is the strongest evidence of that: the
# resolver counts DISTINCT recipients per normalized name, so pooling both forms
# into one list gets the correct tie behaviour from the rule that was already
# there.
# ─────────────────────────────────────────────────────────────────────────────

class _FakeUSAspendingRecipientSearch:
    """`/api/v2/recipient/` as measured: `keyword` is a literal substring test.

    THE MATCH RULE HERE IS THE OBSERVED ONE, not a convenience.  `keyword` does
    a literal, case-insensitive SUBSTRING match against the registered recipient
    name.  It does not fold punctuation and it does not tokenize.  That single
    rule reproduces both facts measured against the live API on 2026-08-07,
    without either being special-cased:

        "palantir usg, inc."  is NOT a substring of  "PALANTIR USG INC"  ->  0
        "palantir usg inc"    IS  a substring of     "PALANTIR USG INC"  ->  1
        "calzoni s.r.l."      IS  a substring of     "CALZONI S.R.L."    ->  1
        "calzoni s r l"       is NOT a substring of  "CALZONI S.R.L."    ->  0

    Those two rows point in OPPOSITE directions, which is the whole reason the
    retrieval unions instead of picking a normalization.

    Every `keyword` asked for is appended to `.keywords`, so a test can count
    requests as well as read results.

    A registry entry is `(name, uei)`, or `(name, uei, recipient_id, amount)`
    when a test needs to control the row identity -- the shape that matters is
    the SAME recipient published at two aggregation levels with different `id`s.
    `recipient_level` is read off the id's trailing token (`abc-R` -> `R`,
    `abc-P` -> `P`), which is how USAspending's own ids are suffixed.
    """

    def __init__(self, registry: list[tuple]) -> None:
        self.registry: list[tuple[str, str | None, str, float]] = []
        for entry in registry:
            name, uei = entry[0], entry[1]
            recipient_id = entry[2] if len(entry) > 2 else f"{(uei or name).casefold()}-R"
            amount = entry[3] if len(entry) > 3 else 1000.0
            self.registry.append((name, uei, recipient_id, amount))
        self.keywords: list[str] = []

    def __call__(self, url: str, body: dict | None) -> tuple[int, bytes]:
        keyword = (body or {}).get("keyword")
        self.keywords.append(keyword)
        needle = str(keyword).casefold()
        results = [
            {
                "name": name,
                "uei": uei,
                "recipient_level": recipient_id.rsplit("-", 1)[-1].upper(),
                "id": recipient_id,
                "amount": amount,
            }
            for name, uei, recipient_id, amount in self.registry
            if needle in name.casefold()
        ]
        return 200, json.dumps(
            {"results": results, "page_metadata": {"hasNext": False}}
        ).encode("utf-8")


def _as_recipient_records(rows: list[dict]) -> list[dict]:
    """Carry pooled collector rows into the resolver's record shape, verbatim.

    Only the registered legal name and the identifier travel; the clocks and
    evidence refs come from the shared builder, so the ONLY thing that can vary
    between these tests is what the retrieval found.
    """
    return [_recipient(row["legal_name"], uei=row["uei"]) for row in rows]


def test_the_union_finds_a_recipient_the_verbatim_spelling_alone_misses() -> None:
    """Gate 1: `Palantir USG, Inc.` reaches `HNN4F9JZWDY8` only via the union.

    Measured 2026-08-07: the exhibit spelling returns 0 recipients and the
    punctuation-stripped spelling returns the real one.  The pooled list holds
    exactly one row, and it is admitted at `exact_verbatim_name` -- the resolver
    compares the recipient's REGISTERED name against the issuer's own exhibit
    name, and the stripped string was only ever a retrieval key.

    The two controls below are the non-vacuity half: the same pooled row is
    refused when its exact identifier is missing, and refused again when its
    name differs beyond orthography.  Both prove the edge above exists because
    an exact UEI met an exact verbatim name, not because the pool got wider.
    """
    backend = _FakeUSAspendingRecipientSearch([("PALANTIR USG INC", "HNN4F9JZWDY8")])
    collector = IssuerEvidenceCollector(fetch=backend)
    exhibit_name = "Palantir USG, Inc."

    verbatim_only = collector._recipient_records_for_query(exhibit_name)
    stripped_only = collector._recipient_records_for_query("Palantir USG Inc")
    pooled = collector.recipient_records(exhibit_name)

    assert verbatim_only["records"] == []
    assert [row["uei"] for row in stripped_only["records"]] == ["HNN4F9JZWDY8"]
    assert [row["uei"] for row in pooled["records"]] == ["HNN4F9JZWDY8"]
    assert pooled["query_forms"] == [exhibit_name, "Palantir USG Inc"]

    resolved = _resolve(
        entities=[_exhibit_entity(exhibit_name)],
        recipients=_as_recipient_records(pooled["records"]),
    )

    assert len(resolved["proposals"]) == 1
    proposal = resolved["proposals"][0]
    assert proposal["admission"]["tier"] == "exact_verbatim_name"
    assert [row["value"] for row in proposal["identifiers"]] == ["HNN4F9JZWDY8"]

    # (a) No exact identifier on the pooled row -> no edge, refusal recorded.
    no_identifier = _resolve(
        entities=[_exhibit_entity(exhibit_name)],
        recipients=[_recipient("PALANTIR USG INC", uei=None)],
    )
    assert no_identifier["proposals"] == []
    assert [row["reason_code"] for row in no_identifier["rejections"]] == [
        "recipient_identifier_absent"
    ]

    # (b) Same UEI, name differing by more than orthography -> no edge.
    renamed = _resolve(
        entities=[_exhibit_entity(exhibit_name)],
        recipients=[_recipient("PALANTIR USG HOLDINGS INC", uei="HNN4F9JZWDY8")],
    )
    assert renamed["proposals"] == []
    assert [row["reason_code"] for row in renamed["rejections"]] == [
        "name_not_in_issuer_exhibit"
    ]


def test_the_union_reveals_a_tie_instead_of_loosening_admission() -> None:
    """Gate 2: a wider pool can only turn an edge into `ambiguous`, never into an edge.

    Two DIFFERENT recipients answer the two forms of one exhibit name, and both
    normalize to `palantir usg inc`.  Under verbatim-only retrieval this
    resolution would have produced a clean edge to `AAAAAAAAAAAA` -- the second
    recipient was invisible, so nothing looked contested.  The union makes the
    tie visible, and a tie is never a pick: both rows land in `ambiguous` and
    zero proposals survive.

    That is a STRENGTHENING, and it is the direction this wave's rule requires.
    Losing a would-be edge because the evidence turned out to be contested is
    the rule working, not a regression in it.  Both identifiers must appear in
    the recorded rows: an ambiguity that silently drops one of the two claimants
    is not a recorded ambiguity, it is a quiet pick with a different label.
    """
    backend = _FakeUSAspendingRecipientSearch([
        ("PALANTIR USG, INC.", "AAAAAAAAAAAA"),
        ("PALANTIR USG INC", "HNN4F9JZWDY8"),
    ])
    collector = IssuerEvidenceCollector(fetch=backend)
    exhibit_name = "Palantir USG, Inc."

    verbatim_only = collector._recipient_records_for_query(exhibit_name)
    pooled = collector.recipient_records(exhibit_name)

    # The premise: verbatim-only sees exactly one of the two, the union sees both.
    assert [row["uei"] for row in verbatim_only["records"]] == ["AAAAAAAAAAAA"]
    # THE DEDUPE MUST NOT COLLAPSE THESE TWO.  Both names normalize to
    # `palantir usg inc`, so a key that dropped the identifier -- or any future
    # tightening toward name-only -- would silently turn this contested pair
    # into one row and hand back the edge the tie is supposed to refuse.  The
    # key is loose enough to collapse ONE recipient seen twice
    # (test_one_recipient_returned_at_two_aggregation_levels_is_one_edge) and
    # tight enough to keep TWO recipients apart, which is this assertion.
    assert len(pooled["records"]) == 2
    assert sorted(row["uei"] for row in pooled["records"]) == [
        "AAAAAAAAAAAA", "HNN4F9JZWDY8"
    ]

    would_have_been = _resolve(
        entities=[_exhibit_entity(exhibit_name)],
        recipients=_as_recipient_records(verbatim_only["records"]),
    )
    assert [
        row["value"]
        for proposal in would_have_been["proposals"]
        for row in proposal["identifiers"]
    ] == ["AAAAAAAAAAAA"]

    resolved = _resolve(
        entities=[_exhibit_entity(exhibit_name)],
        recipients=_as_recipient_records(pooled["records"]),
    )

    assert resolved["proposals"] == []
    assert {row["reason_code"] for row in resolved["ambiguous"]} == {
        "ambiguous_name_matches_multiple_recipients"
    }
    assert {row["recipient_identifier"] for row in resolved["ambiguous"]} == {
        "sam_uei:AAAAAAAAAAAA", "sam_uei:HNN4F9JZWDY8"
    }


def test_one_recipient_returned_at_two_aggregation_levels_is_one_edge() -> None:
    """The real duplicate shape: one recipient, two rows, two `id`s, one edge.

    MEASURED AGAINST THE LIVE API, 2026-08-07.  Querying PLTR's exhibit name
    `Palantir USG, Inc.` returned 0 records for the verbatim form and TWO for
    the stripped form `Palantir USG Inc`, and both rows were the same recipient:

        PALANTIR USG INC  [HNN4F9JZWDY8]
        PALANTIR USG INC  [HNN4F9JZWDY8]

    USAspending publishes a recipient at more than one aggregation level
    (`recipient_level` R and P) with DIFFERENT `id` values, so a dedupe key
    carrying the id lets both rows through and the resolver proposes the same
    edge twice -- one piece of evidence counted twice in the edge count. That is
    reachable from a SINGLE query form, so it is not created by the union; the
    union only makes it more likely, and the dedupe's own docstring claims to
    prevent it, so the key is `(normalized legal name, exact identifier)`.

    The fixture below is that observed shape, not an invented one: same name,
    same UEI, different ids, different amounts.
    """
    backend = _FakeUSAspendingRecipientSearch([
        ("PALANTIR USG INC", "HNN4F9JZWDY8", "abc-R", 4_000_000.0),
        ("PALANTIR USG INC", "HNN4F9JZWDY8", "abc-P", 1_250_000.0),
    ])
    collector = IssuerEvidenceCollector(fetch=backend)
    exhibit_name = "Palantir USG, Inc."

    stripped_only = collector._recipient_records_for_query("Palantir USG Inc")
    pooled = collector.recipient_records(exhibit_name)

    # The premise: the endpoint really does hand back the same recipient twice.
    assert [row["usaspending_recipient_id"] for row in stripped_only["records"]] == [
        "abc-R", "abc-P"
    ]
    assert len(pooled["records"]) == 1
    assert pooled["records"][0]["uei"] == "HNN4F9JZWDY8"
    # First-seen wins, so one recipient's dollars enter coverage once.
    assert pooled["records"][0]["observed_award_amount"] == 4_000_000.0

    resolved = _resolve(
        entities=[_exhibit_entity(exhibit_name)],
        recipients=_as_recipient_records(pooled["records"]),
    )

    assert len(resolved["proposals"]) == 1
    assert [row["value"] for row in resolved["proposals"][0]["identifiers"]] == [
        "HNN4F9JZWDY8"
    ]


def test_the_union_does_not_regress_the_punctuation_bearing_name() -> None:
    """Gate 3: `Calzoni S.r.l.` is the case that only the VERBATIM form finds.

    Measured 2026-08-07 in the opposite direction from Palantir: the exhibit
    spelling returns the recipient and the stripped spelling returns nothing.
    So the union has to leave this one exactly as it was -- same single row,
    same single edge -- and the dedupe must not turn one recipient seen once
    into anything other than one row.
    """
    backend = _FakeUSAspendingRecipientSearch([("CALZONI S.R.L.", "RBVAKLPTAJU3")])
    collector = IssuerEvidenceCollector(fetch=backend)
    exhibit_name = "Calzoni S.r.l."

    verbatim_only = collector._recipient_records_for_query(exhibit_name)
    stripped_only = collector._recipient_records_for_query("Calzoni S r l")
    pooled = collector.recipient_records(exhibit_name)

    assert [row["uei"] for row in verbatim_only["records"]] == ["RBVAKLPTAJU3"]
    assert stripped_only["records"] == []
    assert pooled["records"] == verbatim_only["records"]

    resolved = _resolve(
        entities=[_exhibit_entity(exhibit_name)],
        recipients=_as_recipient_records(pooled["records"]),
    )

    assert len(resolved["proposals"]) == 1
    assert resolved["proposals"][0]["admission"]["tier"] == "exact_verbatim_name"
    assert [row["value"] for row in resolved["proposals"][0]["identifiers"]] == [
        "RBVAKLPTAJU3"
    ]


def test_the_union_is_monotone_over_a_corpus_that_has_no_contested_name() -> None:
    """Gate 3: every edge verbatim-only retrieval produced still exists, plus one.

    THE HONEST CAVEAT, stated rather than asserted away: the proposal COUNT is
    not universally monotone, and this test does not claim it is.  A wider pool
    can reveal a second recipient registered under the same normalized name, and
    the resolver then records `ambiguous_name_matches_multiple_recipients`
    instead of the edge verbatim-only retrieval would have proposed -- exactly
    the case pinned in `test_the_union_reveals_a_tie_instead_of_loosening_admission`.
    That is a strengthening, not a regression: the union did not break an edge,
    it revealed that the evidence for it was contested all along.

    So the corpus here is chosen so that no name in it is contested -- each of
    the three registry names is reachable by exactly one query form of exactly
    one exhibit name -- and what is asserted is the containment that holds in
    that case: the verbatim-only proposal set is a SUBSET of the union's, and
    the union strictly adds the PLTR edge that no single spelling could reach.
    """
    corpus = ["Palantir USG, Inc.", "Calzoni S.r.l.", "Vanguard Defense Systems, Inc."]
    registry = [
        ("PALANTIR USG INC", "HNN4F9JZWDY8"),        # only the stripped form finds it
        ("CALZONI S.R.L.", "RBVAKLPTAJU3"),          # only the verbatim form finds it
        ("VANGUARD DEFENSE SYSTEMS, INC.", RECIPIENT_UEI),  # only the verbatim form
    ]
    entities = [
        _exhibit_entity(name, entity_id=f"entity:corpus-{index}")
        for index, name in enumerate(corpus)
    ]

    collector = IssuerEvidenceCollector(fetch=_FakeUSAspendingRecipientSearch(registry))
    verbatim_rows = [
        row
        for name in corpus
        for row in collector._recipient_records_for_query(name)["records"]
    ]
    union_rows = [
        row for name in corpus for row in collector.recipient_records(name)["records"]
    ]

    old = _resolve(entities=entities, recipients=_as_recipient_records(verbatim_rows))
    new = _resolve(entities=entities, recipients=_as_recipient_records(union_rows))

    old_ids = {proposal["proposal_id"] for proposal in old["proposals"]}
    new_ids = {proposal["proposal_id"] for proposal in new["proposals"]}

    assert old_ids <= new_ids
    assert len(old_ids) == 2 and len(new_ids) == 3
    added = new_ids - old_ids
    assert len(added) == 1
    gained = next(p for p in new["proposals"] if p["proposal_id"] in added)
    assert [row["value"] for row in gained["identifiers"]] == ["HNN4F9JZWDY8"]
    assert new["ambiguous"] == []


def test_the_query_forms_are_bounded_and_the_stripper_is_unicode_aware() -> None:
    """Gate 4: at most two forms, and two requests, per name -- accents intact.

    The stripper drops PUNCTUATION, not non-ASCII.  `Palantir Technologies
    Geneva Sàrl` is a real Palantir subsidiary and carries no punctuation at
    all, so it must produce ONE form; an ASCII-only class would mangle it into
    `Palantir Technologies Geneva S rl`, a spelling no recipient carries, and
    spend a second request asking for it.
    """
    assert MAX_RECIPIENT_QUERY_FORMS == 2

    unpunctuated = "Vanguard Defense Systems LLC"
    assert recipient_query_forms(unpunctuated) == [unpunctuated]
    one_form = _FakeUSAspendingRecipientSearch([])
    IssuerEvidenceCollector(fetch=one_form).recipient_records(unpunctuated)
    assert one_form.keywords == [unpunctuated]

    punctuated = "Helicopter Support, Inc."
    assert recipient_query_forms(punctuated) == [punctuated, "Helicopter Support Inc"]
    two_forms = _FakeUSAspendingRecipientSearch([])
    IssuerEvidenceCollector(fetch=two_forms).recipient_records(punctuated)
    assert two_forms.keywords == [punctuated, "Helicopter Support Inc"]

    accented = "Palantir Technologies Geneva Sàrl"
    assert recipient_query_forms(accented) == [accented]
    accented_backend = _FakeUSAspendingRecipientSearch([])
    IssuerEvidenceCollector(fetch=accented_backend).recipient_records(accented)
    assert accented_backend.keywords == [accented]

    for name in (
        unpunctuated,
        punctuated,
        accented,
        "Palantir USG, Inc.",
        "Calzoni S.r.l.",
        "ComPetro Comunicações Holdings do Brasil, Ltda.",
        "L3Harris Technologies, Inc. (U.K.) -- Bristol",
        "",
    ):
        assert len(recipient_query_forms(name)) <= MAX_RECIPIENT_QUERY_FORMS


def test_the_politeness_floors_are_unchanged_and_still_bite() -> None:
    """Gate 4: unioning doubles the requests, so the rate floor must still hold.

    The floors are pinned by value first, because the whole risk of a second
    query form is that someone "makes room" for it by lowering them.

    The floor is then proven DIRECTLY through `_throttle` rather than through
    the fixture path, because injecting `fetch` bypasses `_http` entirely -- the
    injected fetcher is called instead, so no test ever sleeps and no test can
    observe the throttle by counting requests.  Calling `_throttle` twice for
    the same host class is the honest way to show the floor is live: both query
    forms POST under `host_class="usaspending"`, so the SECOND form's request is
    paced by the same per-host-class clock as the first, with no second rate
    limiter anywhere in the union path.
    """
    assert USASPENDING_MIN_INTERVAL_SECONDS == 1.0
    assert SEC_MIN_INTERVAL_SECONDS == 0.35

    waits: list[float] = []
    collector = IssuerEvidenceCollector(sleep=waits.append)
    assert collector.usaspending_min_interval == USASPENDING_MIN_INTERVAL_SECONDS
    assert collector.sec_min_interval == SEC_MIN_INTERVAL_SECONDS

    collector._throttle("usaspending", collector.usaspending_min_interval)
    assert waits == []  # nothing to wait for on the first request
    collector._throttle("usaspending", collector.usaspending_min_interval)

    assert len(waits) == 1
    assert 0.9 <= waits[0] <= 1.0


def test_both_query_forms_survive_into_the_durable_receipt_ledger(tmp_path: Path) -> None:
    """The ledger must be able to prove the SECOND spelling was asked.

    THE ZERO-RESULT CASE IS THE ONE THAT MATTERS MOST, and it is the ordinary
    case: when both forms of a name find nothing, both responses are
    byte-identical.  "We asked and there was nothing" is exactly the fact the
    receipt ledger exists to preserve -- it is the difference between a recipient
    that does not exist under either spelling and a query that was never sent.

    `receipt_id` is the ledger's append-only key, so deriving it from the
    response body ALONE would collapse those two receipts into one and drop the
    stripped spelling's record from durable history -- a union that cannot be
    audited afterwards.  Keying it on `record_id` + the body digest keeps the id
    retrieval-distinct while leaving it content-bound, which is what the first
    two assertions below pin.

    The re-append at the end is the non-vacuity control: distinctness must come
    from the retrieval identity, not from having quietly broken the append-only
    dedupe.  A true repeat of the same retrieval still adds nothing.
    """
    exhibit_name = "Palantir USG, Inc."
    backend = _FakeUSAspendingRecipientSearch([])  # every keyword answers zero rows
    result = IssuerEvidenceCollector(fetch=backend).recipient_records(exhibit_name)

    assert backend.keywords == [exhibit_name, "Palantir USG Inc"]
    receipts = result["receipts"]
    assert len(receipts) == 2
    # Byte-identical answers -- the collision case, reproduced rather than assumed.
    assert receipts[0]["content_sha256"] == receipts[1]["content_sha256"]
    # ...and still two distinct ledger keys.
    assert receipts[0]["receipt_id"] != receipts[1]["receipt_id"]

    ledger = tmp_path / "issuer_evidence_receipts.jsonl"
    appended = append_issuer_evidence_receipts(receipts, ledger)

    assert appended["new_receipts_this_run"] == 2
    persisted = [
        json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert {row["record_id"] for row in persisted} == {
        f"usaspending:recipient-search:{exhibit_name}:page-1",
        "usaspending:recipient-search:Palantir USG Inc:page-1",
    }

    # Non-vacuity: the append-only dedupe still refuses a true repeat.
    again = append_issuer_evidence_receipts(receipts, ledger)
    assert again["new_receipts_this_run"] == 0
    assert again["receipts_total"] == 2


def test_an_issuer_with_zero_enumerated_recipients_reports_none_not_complete() -> None:
    """An open recall limitation, pinned so it cannot be mistaken for a result.

    `keyword` is a literal, punctuation-sensitive substring match on the
    registered name, and no single normalization fixes it: measured 2026-08-07,
    `Palantir USG, Inc.` returns 0 while `Palantir USG Inc` returns the real
    recipient, and `Calzoni S.r.l.` returns 1 while `Calzoni S r l` returns 0.
    So an exhibit spelling can miss a recipient that exists -- PLTR enumerated
    zero recipients across all 31 of its exhibit names even though its two
    reviewed UEIs are reachable under a looser query.  That measurement was
    taken under VERBATIM-ONLY retrieval; the collector now unions both
    spellings (see the union tests above), which narrows the gap without
    closing it -- a name whose registered spelling differs from the exhibit's
    by more than punctuation is still unreachable by any literal `keyword`.

    The safety property that must hold regardless is this one: an issuer we
    found nothing for is reported `none`, never `complete`. "Not found yet" and
    "not there" are different facts, and only the first one is what we know.
    """
    coverage = build_issuer_coverage(
        issuer_ticker="PLTR",
        exhibit_entity_names=["Palantir USG, Inc.", "Palantir Technologies Holdings LLC"],
        proposed_entity_names=[],
        recipient_award_amounts={},
        proposed_identifiers=[],
    )

    assert coverage["coverage_state"] == "none"
    assert coverage["is_complete"] is False
    assert coverage["award_dollar_coverage"]["ratio"] is None
    assert any("not against the" in note for note in coverage["limitations"])


def test_the_whole_exhibit_pipeline_runs_offline_through_the_injected_fetch() -> None:
    """End-to-end retrieval with zero sockets: the module-wide fence is active.

    This is the shape gate 7 asks for -- live calls are reachable only by
    injecting a fetcher, and the test injects a fixture reader instead.
    """
    fixtures = {
        "https://data.sec.gov/submissions/CIK0001368622.json": json.dumps(
            {
                "filings": {
                    "recent": {
                        "form": ["10-K"],
                        "accessionNumber": ["0001104659-26-000001"],
                        "reportDate": ["2025-12-31"],
                        "filingDate": ["2026-01-29"],
                    }
                }
            }
        ).encode("utf-8"),
        "https://www.sec.gov/Archives/edgar/data/1368622/000110465926000001/0001104659-26-000001-index-headers.html": (
            FIXTURES / "edgar_index_headers.html"
        ).read_bytes(),
        "https://www.sec.gov/Archives/edgar/data/1368622/000110465926000001/vgd-20251231xex21d1.htm": (
            FIXTURES / "exhibit21_sample.htm"
        ).read_bytes(),
    }
    seen: list[str] = []

    def fetch(url: str, body: dict | None) -> tuple[int, bytes]:
        seen.append(url)
        return (200, fixtures[url]) if url in fixtures else (404, b"")

    collector = IssuerEvidenceCollector(fetch=fetch)
    result = collector.issuer_exhibit21("VGD", cik="0001368622")

    assert result["status"] == "ok"
    assert result["names"] == [
        "Vanguard Defense Systems, Inc.",
        "Vanguard Space & Sensing LLC",
        "Vanguard International Holdings Limited",
    ]
    assert len(seen) == 3
    assert seen[1].endswith("-index-headers.html")
    receipt = result["receipts"][0]
    assert evidence_receipt_is_valid(receipt)
    assert receipt["valid_from"] == "2025-12-31T00:00:00+00:00"
    assert receipt["raw_response_body_persisted"] is False


def test_a_filing_without_an_exhibit21_is_reported_not_worked_around() -> None:
    fixtures = {
        "https://data.sec.gov/submissions/CIK0001368622.json": json.dumps(
            {
                "filings": {
                    "recent": {
                        "form": ["10-K"],
                        "accessionNumber": ["0001104659-26-000002"],
                        "reportDate": ["2025-12-31"],
                        "filingDate": ["2026-01-29"],
                    }
                }
            }
        ).encode("utf-8"),
        "https://www.sec.gov/Archives/edgar/data/1368622/000110465926000002/0001104659-26-000002-index-headers.html": (
            FIXTURES / "edgar_index_headers_no_exhibit21.html"
        ).read_bytes(),
    }

    collector = IssuerEvidenceCollector(fetch=lambda url, body: (200, fixtures[url]))
    result = collector.issuer_exhibit21("VGD", cik="0001368622")

    assert result["status"] == "no_exhibit21_declared"
    assert result["names"] == []
    assert result["receipts"] == []


# ─────────────────────────────────────────────────────────────────────────────
# The finding this wave exists to act on.
# ─────────────────────────────────────────────────────────────────────────────

def test_the_shipped_mapping_backlog_is_entirely_curated_fuzzy_name() -> None:
    """The backlog is not a shortcut to attribution -- it is the thing refused.

    All 21 companies in the shipped artifact associate a ticker to a company by
    `curated_fuzzy_name`. That association is exactly what this wave's
    admissibility rule rejects, so the backlog can seed which issuers to LOOK at
    and can never supply the mapping itself.
    """
    latest = json.loads(
        (ROOT / "data/government_revenue/latest.json").read_text(encoding="utf-8")
    )
    methods = {
        (company.get("entity_match") or {}).get("method") for company in latest["companies"]
    }

    assert len(latest["companies"]) == 21
    assert methods == {"curated_fuzzy_name"}

    # And a row carrying that exact method, with an otherwise admissible name
    # and a valid UEI, is refused on the method alone.
    refused = _resolve(recipients=[_recipient(association_method="curated_fuzzy_name")])
    assert refused["proposals"] == []
    assert [row["reason_code"] for row in refused["rejections"]] == [
        "fuzzy_association_input_forbidden"
    ]
