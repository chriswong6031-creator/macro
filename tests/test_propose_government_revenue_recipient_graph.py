"""The Wave 9D proposal tool: offline, fail-closed, and never a publisher.

Every test here runs with ``urllib.request.urlopen`` replaced by a raiser, so a
URL template that drifts away from the committed fixtures fails loudly instead of
quietly reaching the SEC and passing.  The fixtures under
``tests/fixtures/govrev_issuer_evidence/`` encode five deliberately different
issuers:

``PLTR``  the positive control — its two reviewed UEIs must come back, and only those
``BA``    the leading-article control — "THE BOEING COMPANY" vs registrant "BOEING CO"
``GE``    the negative control — five collected recipients that are OTHER companies
``BWXT``  an upstream collection gap — an EX-21 exists, but nothing was collected
``IRDM``  a 10-K with no EX-21 attachment (and an ``index21.htm`` decoy in the listing)
``HII``   the extractor regression — REAL EX-21 bytes whose real subsidiary
          "Huntington Ingalls Incorporated" matches a real award recipient, and
          which an earlier revision discarded while reporting HII finished

BA and GE are a *pair*: the leading-article rule is the only rule in the
normalizer that deletes a token, and the pair proves it recovers Boeing without
also merging Marshall of Cambridge Aerospace into General Electric.

Two fixtures are VERBATIM SEC bytes rather than hand-written HTML, pinned by
sha256 — ``sec_ex21_hii_real.htm`` and ``sec_ex21_lmt_real.htm``.  Synthetic
exhibits are nine tidy lines and cannot fail the way EDGAR does; both of the
extractor bugs this suite now guards were invisible to hand-written markup.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import itertools
import json
from pathlib import Path
import urllib.request

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.government_revenue.entity_resolution import load_recipient_entity_graph
import scripts.propose_government_revenue_recipient_graph as proposal_module
from scripts.propose_government_revenue_recipient_graph import (
    CANDIDATE_GRAPH_FILENAME,
    CANDIDATE_GRAPH_ID_PREFIX,
    CANONICAL_GRAPH_PATH,
    MappingFetcher,
    NO_EDGE_CAUSES,
    WITHHELD_CAUSES,
    WORKSHEET_JSON_FILENAME,
    WORKSHEET_MARKDOWN_FILENAME,
    extract_ex21_lines,
    extract_ex21_names,
    guard_output_path,
    load_fixture_fetcher,
    main,
    normalize_legal_name,
    propose_recipient_graph,
    render_worksheet_markdown,
    select_ex21_filename,
    write_proposal,
)


ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "govrev_issuer_evidence"
CONTRACTS = ROOT / "contracts" / "government_revenue"
KNOWN_AT = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
FIRST_FETCH_AT = KNOWN_AT - timedelta(hours=2)
AS_OF = "2026-08-06"
SCOPE = ("PLTR", "GE", "BA", "BWXT", "IRDM")
PLTR_REVIEWED_UEIS = {"FSY4LVSBGWB7", "HNN4F9JZWDY8"}
USER_AGENT = "MastermindX Government Revenue test (contact: tests@example.com)"

PLTR_TENK_URL = (
    "https://www.sec.gov/Archives/edgar/data/1321655/000132165526000011/pltr-20251231.htm"
)
PLTR_EX21_URL = (
    "https://www.sec.gov/Archives/edgar/data/1321655/000132165526000011/a2025fyexhibit211.htm"
)
PLTR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0001321655.json"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Any real socket in this module is a test bug, not a slow test."""

    def _refuse(*args, **kwargs):  # pragma: no cover - only runs on a regression
        raise AssertionError(
            "this suite must never open a socket; all bytes come from the injected fetcher"
        )

    monkeypatch.setattr(urllib.request, "urlopen", _refuse)


def _award_rows() -> list[dict]:
    return json.loads((FIXTURES / "awards.json").read_text(encoding="utf-8"))


def _fetcher(**replacements: bytes) -> MappingFetcher:
    """The committed fixture corpus, optionally with individual documents swapped."""
    fetcher = load_fixture_fetcher(FIXTURES)
    fetcher.documents.update(replacements)
    return fetcher


def _fetch_clock(start=FIRST_FETCH_AT):
    """A deterministic stand-in for the wall clock that stamps each fetch.

    One distinct, increasing moment per call, so a test can tell WHICH document
    a ``retrieved_at`` belongs to — and the same sequence on every run, so the
    emitted bytes stay pinned.  All moments precede ``KNOWN_AT``, which is what a
    replay of an ``--as-of`` run looks like: the documents were read, then the
    graph was stamped.
    """
    counter = itertools.count()
    return lambda: start + timedelta(seconds=next(counter))


def _expected_retrieved_at(index: int) -> str:
    return (FIRST_FETCH_AT + timedelta(seconds=index)).isoformat()


def _propose(*, tickers=SCOPE, award_rows=None, fetcher=None, published_graph=None, now=None):
    return propose_recipient_graph(
        tickers=tickers,
        award_rows=_award_rows() if award_rows is None else award_rows,
        fetch=fetcher or _fetcher(),
        known_at=KNOWN_AT,
        published_graph=published_graph,
        now=now or _fetch_clock(),
    )


def _causes(proposal) -> dict[str, str]:
    return {
        row["ticker"]: row["cause"] for row in proposal.worksheet["issuers_without_edges"]
    }


def _ueis(proposal, ticker: str) -> set[str]:
    return {
        edge["proposed_uei"]
        for edge in proposal.worksheet["proposed_edges"]
        if edge["ticker"] == ticker
    }


# --- G1: the candidate must survive the real runtime admission gate ---------


def test_candidate_graph_loads_through_the_runtime_with_zero_admission_errors():
    """G1. A proposal an analyst cannot load is a proposal they cannot review.

    This asserts against the shipped ``load_recipient_entity_graph`` — the same
    function ``curate_graph`` calls — so the tool can never emit a document whose
    clocks, evidence receipts, claim scopes, or ownership topology would be
    refused at publish time.
    """
    loaded = load_recipient_entity_graph(_propose().graph, as_of=AS_OF)

    assert loaded["error_codes"] == []
    assert loaded["status"] == "ready"


def test_candidate_graph_validates_against_the_published_v1_contract():
    """The JSON Schema and the loader are two independent gates; pass both."""
    schema = json.loads(
        (CONTRACTS / "government_recipient_entity_graph.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(_propose().graph)


# --- G2: never a second writer of the canonical graph ----------------------


def test_a_full_run_never_writes_the_canonical_recipient_graph(tmp_path):
    """G2. ``curate_government_revenue_recipient_graph.py`` stays the sole writer.

    The canonical graph is registered in ``config/dag.yml`` and ``config/synapse.yml``
    with exactly one producer.  A discovery tool that could write it would make
    an unreviewed mapping indistinguishable from a reviewed one.
    """
    before = CANONICAL_GRAPH_PATH.read_bytes()

    paths = write_proposal(_propose(), tmp_path / "proposal")

    assert CANONICAL_GRAPH_PATH.read_bytes() == before
    assert sorted(path.name for path in paths.values()) == sorted(
        [CANDIDATE_GRAPH_FILENAME, WORKSHEET_JSON_FILENAME, WORKSHEET_MARKDOWN_FILENAME]
    )
    assert all(path.exists() for path in paths.values())
    assert CANONICAL_GRAPH_PATH.name not in {path.name for path in paths.values()}


@pytest.mark.parametrize(
    "destination",
    [
        CANONICAL_GRAPH_PATH,
        Path("data/government_revenue/recipient_entity_graph.json"),
        Path("recipient_entity_graph.json"),
    ],
)
def test_output_path_guard_refuses_the_canonical_name_anywhere(destination, tmp_path):
    """A candidate parked under the canonical file name is one ``cp`` from disaster."""
    with pytest.raises(ValueError, match="never writes the canonical"):
        guard_output_path(Path(destination))
    with pytest.raises(ValueError, match="never writes the canonical"):
        guard_output_path(tmp_path / Path(destination).name)


# --- G3: the PLTR positive control ----------------------------------------


def test_pltr_positive_control_proposes_exactly_the_two_reviewed_ueis():
    """G3. The one hand-curated mapping in production is reproduced, and nothing else.

    PLTR is the only issuer with a reviewed mapping today
    (``recipient-graph:reviewed:2026-08-03:pltr-v1``, UEIs FSY4LVSBGWB7 +
    HNN4F9JZWDY8).  If the tool proposes a third UEI for PLTR it has invented
    attribution; if it proposes fewer it has lost the join.
    """
    proposal = _propose()

    assert _ueis(proposal, "PLTR") == PLTR_REVIEWED_UEIS
    by_uei = {
        edge["proposed_uei"]: edge
        for edge in proposal.worksheet["proposed_edges"]
        if edge["ticker"] == "PLTR"
    }
    assert by_uei["FSY4LVSBGWB7"]["sec_source_role"] == "sec_registrant"
    assert by_uei["HNN4F9JZWDY8"]["sec_source_role"] == "ex21_subsidiary"
    assert by_uei["HNN4F9JZWDY8"]["sec_source_name"] == "Palantir USG, Inc."
    # Every proposed edge carries its own SEC document AND its own award receipt.
    for edge in by_uei.values():
        publishers = {source["publisher"] for source in edge["evidence"]}
        assert publishers == {"SEC", "USAspending.gov"}
        assert all(len(source["content_sha256"]) == 64 for source in edge["evidence"])


def test_published_identifiers_are_flagged_so_a_publish_merges_rather_than_replaces():
    """The analyst must not overwrite the reviewed PLTR rows with candidate copies."""
    published = json.loads(CANONICAL_GRAPH_PATH.read_text(encoding="utf-8"))

    proposal = _propose(published_graph=published)

    assert set(proposal.worksheet["already_published_identifiers"]) == PLTR_REVIEWED_UEIS


# --- G4: the negative control ---------------------------------------------


def test_ge_negative_control_proposes_zero_edges_from_other_companies_names():
    """G4. The normalizer must not merge distinct businesses.

    GE's collected recipients (Marshall of Cambridge Aerospace, Prestige
    Aerospace, ...) are genuinely other companies that a fuzzy discovery query
    swept in.  Zero is the correct answer.
    """
    proposal = _propose()

    assert _ueis(proposal, "GE") == set()
    assert _causes(proposal)["GE"] == "no_exact_match"
    assert "MARSHALLCAM1" not in {
        edge["proposed_uei"] for edge in proposal.worksheet["proposed_edges"]
    }
    assert "PRESTGEAERZ2" not in {
        edge["proposed_uei"] for edge in proposal.worksheet["proposed_edges"]
    }


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("MARSHALL OF CAMBRIDGE AEROSPACE LIMITED", "GENERAL ELECTRIC CO"),
        ("PRESTIGE AEROSPACE LLC", "GE Aerospace Holdings, LLC"),
        ("Palantir USG, Inc.", "Palantir Technologies Inc."),
        ("Lockheed Martin Corporation", "Lockheed Martin Services, LLC"),
        ("Boeing Capital Corporation", "BOEING CO"),
    ],
)
def test_normalizer_keeps_distinct_businesses_distinct(left, right):
    """No pair of genuinely different legal names may collapse to one key."""
    assert normalize_legal_name(left) != normalize_legal_name(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Palantir USG, Inc.", "PALANTIR USG INC"),
        ("Palantir Technologies Inc.", "PALANTIR TECHNOLOGIES INC."),
        ("THE BOEING COMPANY", "BOEING CO"),
        ("Lockheed Martin Corporation", "LOCKHEED MARTIN CORP"),
        ("Marshall of Cambridge Aerospace Limited", "MARSHALL OF CAMBRIDGE AEROSPACE LTD"),
    ],
)
def test_normalizer_reconciles_only_spelling_of_one_name(left, right):
    """Case, punctuation, corporate form, and a leading article — nothing else."""
    assert normalize_legal_name(left) == normalize_legal_name(right)


def test_leading_article_rule_is_paired_boeing_recovers_and_ge_stays_at_zero():
    """The one token-deleting rule earns its place, measured on both sides.

    Boeing's recipients are filed as "THE BOEING COMPANY" against a registrant
    named "BOEING CO"; without the article rule that edge is lost.  The same run
    must leave GE at zero, or the rule is buying recall with false positives.
    """
    proposal = _propose()

    assert _ueis(proposal, "BA") == {"BAENGCMPNY11"}
    assert _ueis(proposal, "GE") == set()
    boeing = next(
        edge for edge in proposal.worksheet["proposed_edges"] if edge["ticker"] == "BA"
    )
    assert boeing["usaspending_recipient_names"] == ["THE BOEING COMPANY"]
    assert boeing["sec_source_name"] == "BOEING CO"
    assert boeing["normalized_join_key"] == "boeing co"


# --- G5: named, separate causes -------------------------------------------


def test_no_edge_causes_are_reported_separately_and_never_as_mapping_needed():
    """G5. A zero with the wrong name sends an analyst on a hunt that cannot end.

    GE has *no exact issuer evidence* — a finished answer.  BWXT collected
    nothing at all — an upstream collection gap owned by the collector.  IRDM's
    10-K carries no EX-21 — a document gap.  Collapsing the three into
    "mapping_needed" (the mapping-backlog vocabulary) would hide two real
    upstream defects behind a to-do.
    """
    proposal = _propose()
    causes = _causes(proposal)

    assert causes["GE"] == "no_exact_match"
    assert causes["BWXT"] == "no_collected_recipients"
    assert causes["IRDM"] == "no_ex21_exhibit"
    assert len({causes["GE"], causes["BWXT"], causes["IRDM"]}) == 3
    assert set(causes.values()) <= set(NO_EDGE_CAUSES)
    assert "mapping_needed" not in json.dumps(proposal.worksheet)
    assert "mapping_needed" not in render_worksheet_markdown(proposal.worksheet)
    # Each cause carries a human sentence, not just a slug.
    for row in proposal.worksheet["issuers_without_edges"]:
        assert len(row["cause_detail"]) > 40


def test_unknown_ticker_is_a_registry_miss_not_a_matching_failure():
    proposal = _propose(tickers=("PLTR", "NOSUCHTKR"))

    assert _causes(proposal)["NOSUCHTKR"] == "ticker_not_in_sec_registry"


def test_award_receipt_must_itself_contain_the_identifier_it_is_cited_for():
    """Evidence that does not mention the UEI proves nothing about the UEI."""
    url = "https://api.usaspending.gov/api/v2/awards/CONT_AWD_W9128Z26FA001_9700_W519TC25D0039_9700/"
    hollowed = json.dumps({"generated_unique_award_id": "CONT_AWD_W9128Z26FA001", "recipient": {}})

    proposal = _propose(fetcher=_fetcher(**{url: hollowed.encode("utf-8")}))

    assert _ueis(proposal, "PLTR") == {"FSY4LVSBGWB7"}
    withheld = {row["uei"]: row["cause"] for row in proposal.worksheet["withheld_identifiers"]}
    assert withheld == {"HNN4F9JZWDY8": "award_receipt_missing_identifier"}
    assert set(withheld.values()) <= set(WITHHELD_CAUSES)


def test_one_uei_claimed_by_two_issuers_is_withheld_from_both():
    """A UEI is one external identity; two claimants is an analyst decision.

    Admitting both would produce ``ambiguous_exact_identifier_path`` and the
    graph would not load at all — so the choice is between a named withholding
    and an unpublishable document.
    """
    rows = _award_rows()
    rows.append(
        {
            "ticker": "BA",
            "recipient_name": "BOEING CO",
            "recipient_uei": "FSY4LVSBGWB7",
            "generated_award_id": "CONT_AWD_COLLIDE0001_9700_-NONE-_-NONE-",
            "start_date": "2024-03-01",
            "base_obligation_date": "2024-03-01",
        }
    )

    proposal = _propose(award_rows=rows)

    withheld = {row["uei"]: row for row in proposal.worksheet["withheld_identifiers"]}
    assert withheld["FSY4LVSBGWB7"]["cause"] == "identifier_claimed_by_multiple_issuers"
    assert withheld["FSY4LVSBGWB7"]["tickers"] == ["BA", "PLTR"]
    assert "FSY4LVSBGWB7" not in _ueis(proposal, "PLTR")
    assert "FSY4LVSBGWB7" not in _ueis(proposal, "BA")
    assert load_recipient_entity_graph(proposal.graph, as_of=AS_OF)["error_codes"] == []


def test_one_uei_matching_two_names_of_one_issuer_is_withheld():
    rows = _award_rows()
    rows.append(
        {
            "ticker": "PLTR",
            "recipient_name": "PALANTIR USG INC",
            "recipient_uei": "FSY4LVSBGWB7",
            "generated_award_id": "CONT_AWD_DOUBLE00001_9700_-NONE-_-NONE-",
            "start_date": "2024-03-01",
            "base_obligation_date": "2024-03-01",
        }
    )

    proposal = _propose(award_rows=rows)

    withheld = {row["uei"]: row["cause"] for row in proposal.worksheet["withheld_identifiers"]}
    assert withheld == {"FSY4LVSBGWB7": "identifier_maps_to_multiple_entities"}
    assert _ueis(proposal, "PLTR") == {"HNN4F9JZWDY8"}


def test_an_issuer_whose_every_match_is_withheld_gets_its_own_cause():
    rows = [row for row in _award_rows() if row["ticker"] != "PLTR"]
    rows.append(
        {
            "ticker": "PLTR",
            "recipient_name": "PALANTIR USG INC",
            "recipient_uei": "HNN4F9JZWDY8",
            "generated_award_id": "CONT_AWD_FUTURE00001_9700_-NONE-_-NONE-",
            "start_date": "2027-01-01",
            "base_obligation_date": "2027-01-01",
        }
    )

    proposal = _propose(award_rows=rows)

    assert _ueis(proposal, "PLTR") == set()
    assert _causes(proposal)["PLTR"] == "all_candidate_identifiers_withheld"
    assert proposal.worksheet["withheld_identifiers"][0]["cause"] == (
        "no_award_receipt_before_as_of"
    )


# --- G6: offline by construction ------------------------------------------


def test_every_byte_comes_from_the_injected_fetcher():
    """G6. The fetcher is the only source of bytes in the whole run.

    Three independent checks: the run's own fetch log matches what the fixture
    fetcher served (nothing bypassed the seam), every evidence URL in the emitted
    graph was one of those served documents, and the module-wide ``urlopen``
    raiser never fired.
    """
    fetcher = _fetcher()

    proposal = _propose(fetcher=fetcher)

    assert proposal.fetch_log == fetcher.served
    assert proposal.fetch_log, "the run must actually read documents"
    served = set(fetcher.served)
    assert {row["url"] for row in proposal.graph["evidence"]} <= served
    assert proposal.worksheet["counts"]["documents_fetched"] == len(fetcher.served)


def test_evidence_urls_never_use_the_lookup_only_host():
    """``data.sec.gov`` is not on the runtime's evidence allow-list.

    It is read for the submissions lookup, so a copy-paste of the lookup URL into
    an evidence row is a live risk; the loader would reject it as
    ``evidence_url_publisher_mismatch``.
    """
    proposal = _propose()

    for row in proposal.graph["evidence"]:
        assert row["url"].startswith("https://")
        assert "data.sec.gov" not in row["url"]
    assert any(
        "data.sec.gov" in url for url in proposal.fetch_log
    ), "the submissions API is still the lookup source"


def test_an_unknown_url_fails_loudly_instead_of_hashing_empty_bytes():
    with pytest.raises(FileNotFoundError):
        MappingFetcher({})("https://www.sec.gov/files/company_tickers.json")


# --- The candidate must not look published --------------------------------


def test_candidate_never_masquerades_as_a_published_reviewed_graph(tmp_path):
    """The contract has no ``proposed`` state, so candidate-ness lives elsewhere.

    Four carriers, each of which survives a copy: the candidate ``graph_id``
    namespace, the output file name, the worksheet's review state, and the
    refusal to write the canonical path.
    """
    proposal = _propose()

    assert proposal.graph["graph_id"].startswith(CANDIDATE_GRAPH_ID_PREFIX)
    assert ":reviewed:" not in proposal.graph["graph_id"]
    assert proposal.worksheet["review_state"] == "awaiting_analyst_review"
    assert proposal.worksheet["candidate_graph_is_unpublished"] is True
    assert proposal.worksheet["authority"]["tier"] == "display"
    assert proposal.worksheet["authority"]["can_originate_signal"] is False
    paths = write_proposal(proposal, tmp_path)
    assert paths["candidate_graph"].name == "recipient_graph_candidate.json"
    markdown = paths["worksheet_markdown"].read_text(encoding="utf-8")
    assert "CANDIDATE" in markdown
    assert "curate_government_revenue_recipient_graph" in markdown


def test_worksheet_shows_every_edge_with_its_evidence_and_every_zero_with_its_cause():
    """F. The worksheet is the artifact an analyst reads before publishing."""
    proposal = _propose()
    markdown = render_worksheet_markdown(proposal.worksheet)

    for edge in proposal.worksheet["proposed_edges"]:
        assert edge["proposed_uei"] in markdown
        assert edge["sec_source_name"] in markdown
        assert edge["evidence"], "an edge with no evidence is an assertion"
        for source in edge["evidence"]:
            assert source["url"] in markdown
    for row in proposal.worksheet["issuers_without_edges"]:
        assert row["cause"] in markdown
    assert "discovery_query_ticker" in markdown  # named as a forbidden input


def test_the_discovery_ticker_is_review_metadata_and_not_a_join_condition():
    """A recipient discovered under the wrong ticker still joins on its name.

    Making the discovery ticker a precondition would quietly re-import the fuzzy
    curated-name query that the reviewed graph exists to replace.
    """
    rows = _award_rows()
    for row in rows:
        if row["recipient_uei"] == "HNN4F9JZWDY8":
            row["ticker"] = "LMT"  # mis-attributed by the discovery query

    proposal = _propose(award_rows=rows)

    assert _ueis(proposal, "PLTR") == PLTR_REVIEWED_UEIS
    flagged = next(
        edge
        for edge in proposal.worksheet["proposed_edges"]
        if edge["proposed_uei"] == "HNN4F9JZWDY8"
    )
    assert flagged["discovery_tickers_on_matched_rows"] == ["LMT"]
    assert flagged["discovery_ticker_agrees_with_proposal"] is False


# --- Determinism and extraction -------------------------------------------


def test_output_bytes_are_deterministic_for_a_pinned_clock():
    first = json.dumps(_propose().graph, sort_keys=True)
    second = json.dumps(_propose().graph, sort_keys=True)

    assert first == second


def test_no_wall_clock_leaks_into_the_document_body():
    proposal = _propose()
    stamp = "2026-08-06T12:00:00+00:00"

    assert proposal.graph["graph_known_at"] == stamp
    assert proposal.graph["graph_effective_at"] == stamp
    for row in proposal.graph["evidence"]:
        assert row["known_at"] == stamp
        # retrieved_at is deliberately NOT the stamp — see the retrieved_at test.
        assert row["retrieved_at"] < stamp
    for key in ("companies", "legal_entities", "identifiers", "ownership_edges"):
        for row in proposal.graph[key]:
            assert row["known_at"] == stamp


def test_ex21_extraction_keeps_legal_names_and_drops_table_furniture():
    document = (FIXTURES / "sec_ex21_pltr.htm").read_text(encoding="utf-8")

    names = extract_ex21_names(document)

    assert "Palantir USG, Inc." in names
    assert "Palantir Technologies UK, Ltd." in names
    assert not any("Jurisdiction" in name for name in names)
    assert not any("Subsidiaries" in name for name in names)
    assert "Delaware" not in names


# The 2025 10-K archive listings of GE, BA, PLTR, and TXT, verbatim (EDGAR stamps
# every document ``text.gif``, so the file name is the only usable signal).
_REAL_LISTINGS = {
    # Textron is the adversarial one: EDGAR uses a bare ``x`` as the separator
    # between the exhibit word and its number, and files SEVEN sibling exhibits in
    # the same ``exx`` family.  The 2026-08-07 live run reported TXT as
    # ``no_ex21_exhibit`` — "Accession 000021734626000006 carries no EX-21
    # attachment" — because the separator class was ``[-_.]?`` and could not match
    # that ``x``.  Every Textron edge was lost and the worksheet asserted something
    # untrue.  This listing pins both halves: ``exx21`` must win, and exx1013,
    # exx23, exx24, exx311, exx312, exx321 and exx322 must all still lose.
    "TXT": (
        [
            "0000217346-26-000006-index.html",
            "q4202510k-exx1013.htm",
            "q4202510k-exx21.htm",
            "q4202510k-exx23.htm",
            "q4202510k-exx24.htm",
            "q4202510k-exx311.htm",
            "q4202510k-exx312.htm",
            "q4202510k-exx321.htm",
            "q4202510k-exx322.htm",
        ],
        "q4202510k-exx21.htm",
    ),
    "GE": (
        [
            "0000040545-26-000008-index.html",
            "ex10hformofdirectorindemni.htm",
            "ex21subsidiariesofregistra.htm",
            "ex22listofsubsidiaryguaran.htm",
            "ex23consentofindependentre.htm",
            "ex31acertificationpursuant.htm",
            "ex4ldescriptionoftheregist.htm",
            "ex99asupplementtopresentre.htm",
        ],
        "ex21subsidiariesofregistra.htm",
    ),
    "BA": (
        [
            "0001628280-26-004357-index.html",
            "a202512dec3110kex1012.htm",
            "a202512dec3110kex109.htm",
            "a202512dec3110kex21.htm",
            "a202512dec3110kex22.htm",
            "a202512dec3110kex321.htm",
        ],
        "a202512dec3110kex21.htm",
    ),
    "PLTR": (
        [
            "0001321655-26-000011-index.html",
            "R21.htm",
            "a2025fyexhibit211.htm",
            "a2025q4exhibit231.htm",
            "a2025q4exhibit311.htm",
            "a2025q4exhibit321.htm",
        ],
        "a2025fyexhibit211.htm",
    ),
}


@pytest.mark.parametrize("ticker", sorted(_REAL_LISTINGS))
def test_ex21_picker_finds_the_real_exhibit_in_a_real_edgar_listing(ticker):
    """Regression: GE files ``ex21subsidiariesofregistra.htm``.

    An earlier revision anchored the exhibit token to the file extension, which
    matched BA and PLTR but not GE — and reported GE as ``no_ex21_exhibit`` when
    the exhibit was sitting in the listing.  That is the worst shape of wrong
    answer here: it converts a finished "no exact issuer evidence" verdict into a
    phantom EDGAR errand.  Sibling exhibits (22, 23, 10.12, 3.2.1) must still lose.
    """
    names, expected = _REAL_LISTINGS[ticker]
    listing = {"directory": {"item": [{"name": name, "type": "text.gif"} for name in names]}}

    assert select_ex21_filename(listing) == expected


def test_ex21_picker_returns_none_when_the_filing_carries_no_exhibit():
    listing = {
        "directory": {
            "item": [
                {"name": "irdm-20251231.htm", "type": "text.gif"},
                {"name": "index21.htm", "type": "text.gif"},
                {"name": "R21.htm", "type": "text.gif"},
                {"name": "ex22listofsubsidiaryguaran.htm", "type": "text.gif"},
            ]
        }
    }

    assert select_ex21_filename(listing) is None


def test_an_edgar_index_page_is_never_mistaken_for_an_ex21_exhibit():
    """``index21.htm`` contains the substring ``ex21.htm``.

    IRDM's fixture listing carries that decoy and no real exhibit; parsing the
    decoy would produce a name-free document and report "this issuer has no
    subsidiaries" instead of "this filing has no EX-21".
    """
    proposal = _propose()

    assert _causes(proposal)["IRDM"] == "no_ex21_exhibit"
    assert not any(
        "index" in row["url"].rsplit("/", 1)[-1].lower() for row in proposal.graph["evidence"]
    )


# --- The content address IS the falsifiability -----------------------------


def test_every_evidence_digest_is_the_sha256_of_the_bytes_that_were_fetched():
    """Nothing else in this document can be checked without this.

    ``content_sha256`` is what lets a reader re-fetch a URL and prove the tool
    read what it says it read.  A digest computed over the wrong bytes — the
    empty string, the URL, a constant — is internally consistent with
    ``source_ref`` and passes every structural gate the runtime has, so it must
    be pinned to the FETCHER'S OWN bytes here or it is pinned nowhere.
    """
    fetcher = _fetcher()

    proposal = _propose(fetcher=fetcher)

    assert proposal.graph["evidence"], "a run with no receipts proves nothing"
    for row in proposal.graph["evidence"]:
        body = fetcher.documents[row["url"]]
        digest = hashlib.sha256(body).hexdigest()
        assert row["content_sha256"] == digest
        assert row["content_sha256"] == row["content_sha256"].lower()
        assert row["byte_length"] == len(body)
        assert row["source_ref"] == f"recipient-evidence:sha256:{digest}"
    # The worksheet copies the receipt for the analyst; the copy must agree.
    graph_rows = {row["evidence_id"]: row for row in proposal.graph["evidence"]}
    for edge in proposal.worksheet["proposed_edges"]:
        for source in edge["evidence"]:
            pinned = graph_rows[source["evidence_id"]]
            assert source["content_sha256"] == pinned["content_sha256"]
            assert source["byte_length"] == pinned["byte_length"]


def test_changing_one_documents_bytes_moves_that_documents_digest_and_no_other():
    """The digest tracks the bytes, not the URL, the position, or the run."""
    longer = (FIXTURES / "sec_ex21_pltr.htm").read_bytes() + b"<!-- one more comment -->"

    before = {
        row["evidence_id"]: (row["content_sha256"], row["byte_length"])
        for row in _propose().graph["evidence"]
    }
    after = {
        row["evidence_id"]: (row["content_sha256"], row["byte_length"])
        for row in _propose(fetcher=_fetcher(**{PLTR_EX21_URL: longer})).graph["evidence"]
    }

    assert set(before) == set(after)
    moved = {key for key in before if before[key] != after[key]}
    assert moved == {"evidence:pltr-sec-ex21"}
    assert after["evidence:pltr-sec-ex21"][1] == before["evidence:pltr-sec-ex21"][1] + 25
    assert after["evidence:pltr-sec-ex21"][0] == hashlib.sha256(longer).hexdigest()


def test_retrieved_at_records_when_each_document_arrived_not_the_run_stamp():
    """A receipt must not assert a retrieval that did not happen.

    ``--as-of`` pins the knowledge cutoff; deriving ``retrieved_at`` from it (as
    an earlier revision did) makes every receipt claim the documents were pulled
    at noon on the as-of date, whenever the run really happened.  It is the one
    field in the document a reader cannot check against the source.
    """
    fetcher = _fetcher()

    proposal = _propose(fetcher=fetcher)

    expected = {}
    for index, url in enumerate(fetcher.served):
        expected.setdefault(url, _expected_retrieved_at(index))
    stamps = {row["url"]: row["retrieved_at"] for row in proposal.graph["evidence"]}
    assert stamps
    assert stamps == {url: expected[url] for url in stamps}
    assert len(set(stamps.values())) > 1, "one shared value is a stamp, not an observation"
    for row in proposal.graph["evidence"]:
        assert row["retrieved_at"] < row["known_at"]


# --- Point-in-time and the state every row is asking for --------------------


def test_valid_from_is_the_documents_own_date_and_never_the_run_stamp():
    """Economic validity comes from the documents; knowledge comes from the run.

    Collapsing ``valid_from`` onto the stamp would silently redate every claim to
    the day the tool happened to run — a PIT violation that no structural gate
    can see, because the collapsed document still loads.
    """
    proposal = _propose()
    stamp = "2026-08-06T12:00:00+00:00"
    report_date = "2025-12-31T00:00:00+00:00"
    by_id = {row["evidence_id"]: row for row in proposal.graph["evidence"]}

    assert by_id["evidence:pltr-sec-10k"]["valid_from"] == report_date
    assert by_id["evidence:pltr-sec-ex21"]["valid_from"] == report_date
    # Award receipts carry the award's own start date, not the filing's.
    assert by_id["evidence:pltr-usaspending-fsy4lvsbgwb7"]["valid_from"] == (
        "2022-09-26T00:00:00+00:00"
    )
    assert by_id["evidence:pltr-usaspending-hnn4f9jzwdy8"]["valid_from"] == (
        "2025-10-15T00:00:00+00:00"
    )
    assert by_id["evidence:ba-usaspending-baengcmpny11"]["valid_from"] == (
        "2024-02-01T00:00:00+00:00"
    )
    for key in ("companies", "legal_entities", "identifiers", "ownership_edges"):
        assert proposal.graph[key]
        for row in proposal.graph[key]:
            assert row["valid_from"] == report_date
            assert row["valid_from"] != stamp


def test_every_row_records_the_assertion_being_asked_for_and_never_a_confirmation():
    """``reviewed`` is the whole candidate-vs-published argument in one field.

    The module docstring reads it as "the assertion the analyst is being asked to
    make".  If a row could quietly say ``confirmed`` — the contract's strongest
    state — an unreviewed proposal would claim more authority than the reviewed
    graph it is proposed against, and nothing else in the document would object.
    """
    proposal = _propose()

    for key in ("companies", "legal_entities", "identifiers", "ownership_edges"):
        assert proposal.graph[key]
        for row in proposal.graph[key]:
            assert row["verification_state"] == "reviewed"
    body = json.dumps(proposal.graph)
    assert '"confirmed"' not in body
    assert '"analyst_approved"' not in body


# --- One issuer's punctuation must not sink the whole artifact --------------


_SLUG_COLLIDING_EX21 = b"""<html><body>
<p>Exhibit 21.1</p>
<table>
<tr><td>Name</td><td>Jurisdiction of Incorporation</td></tr>
<tr><td>Alpha &amp; Beta LLC</td><td>Delaware</td></tr>
<tr><td>Alpha Beta LLC</td><td>Delaware</td></tr>
</table>
</body></html>"""


def _award_receipt(award_id: str, name: str, uei: str) -> bytes:
    return json.dumps(
        {
            "generated_unique_award_id": award_id,
            "recipient": {"recipient_name": name, "recipient_uei": uei},
        }
    ).encode("utf-8")


def test_two_names_that_slug_alike_get_distinct_edge_ids():
    """A duplicate ``edge_id`` makes the WHOLE candidate unloadable.

    "Alpha & Beta LLC" and "Alpha Beta LLC" are two distinct normalized names
    that slug to one string.  The entity ids are de-duplicated with a ``-2``
    suffix; an ``edge_id`` minted independently from the slug collides, and the
    blast radius is every issuer in the run, not the one with the ampersand.
    """
    rows = _award_rows()
    receipts = {}
    for name, uei, award_id in (
        ("ALPHA & BETA LLC", "ALPHABETA001", "CONT_AWD_ALPHAAMP0001_9700_-NONE-_-NONE-"),
        ("ALPHA BETA LLC", "ALPHABETA002", "CONT_AWD_ALPHAPLN0001_9700_-NONE-_-NONE-"),
    ):
        rows.append(
            {
                "ticker": "PLTR",
                "recipient_name": name,
                "recipient_uei": uei,
                "generated_award_id": award_id,
                "start_date": "2024-01-01",
                "base_obligation_date": "2024-01-01",
            }
        )
        receipts[f"https://api.usaspending.gov/api/v2/awards/{award_id}/"] = _award_receipt(
            award_id, name, uei
        )

    proposal = _propose(
        award_rows=rows,
        fetcher=_fetcher(**{PLTR_EX21_URL: _SLUG_COLLIDING_EX21}, **receipts),
    )

    entity_ids = [row["entity_id"] for row in proposal.graph["legal_entities"]]
    edge_ids = [row["edge_id"] for row in proposal.graph["ownership_edges"]]
    assert "legal:pltr:alpha-beta-llc" in entity_ids
    assert "legal:pltr:alpha-beta-llc-2" in entity_ids
    assert sorted(edge_ids) == sorted(set(edge_ids)), edge_ids
    assert "ownership:pltr:alpha-beta-llc-2" in edge_ids
    assert load_recipient_entity_graph(proposal.graph, as_of=AS_OF)["error_codes"] == []
    # The worksheet points the analyst at the row that actually exists.
    for edge in proposal.worksheet["proposed_edges"]:
        assert edge["graph_rows"]["ownership_edge_id"] in edge_ids
        assert edge["graph_rows"]["legal_entity_id"] in entity_ids


def test_a_blank_sec_registrant_name_is_a_named_lookup_failure_not_a_blank_row():
    """One unnamed registrant would fail admission for every OTHER issuer too."""
    submissions = json.loads((FIXTURES / "sec_submissions_pltr.json").read_text(encoding="utf-8"))
    submissions["name"] = "   "

    proposal = _propose(
        fetcher=_fetcher(**{PLTR_SUBMISSIONS_URL: json.dumps(submissions).encode("utf-8")})
    )

    assert _causes(proposal)["PLTR"] == "sec_lookup_failed"
    assert _ueis(proposal, "PLTR") == set()
    assert all(row["canonical_name"].strip() for row in proposal.graph["legal_entities"])
    assert load_recipient_entity_graph(proposal.graph, as_of=AS_OF)["error_codes"] == []
    # The other issuers in the same run are untouched.
    assert _ueis(proposal, "BA") == {"BAENGCMPNY11"}


def test_the_cited_10k_must_name_the_registrant_it_is_cited_for():
    """The SEC side gets the rule the award side already had.

    ``registrant_name`` is read from ``data.sec.gov/submissions`` — a host
    deliberately absent from the evidence allow-list, i.e. a lookup that is never
    cited.  The document that IS cited for ``public_company`` / ``legal_entity``
    / ``ownership`` is the 10-K, so a 10-K that does not contain the registrant
    is decoration on the highest-value edge the tool emits.
    """
    blank = b"<html><body><p>this document is about nothing at all</p></body></html>"

    proposal = _propose(fetcher=_fetcher(**{PLTR_TENK_URL: blank}))

    assert _causes(proposal)["PLTR"] == "registrant_name_not_in_filing"
    assert _ueis(proposal, "PLTR") == set()
    assert not [
        row for row in proposal.graph["evidence"] if row["evidence_id"].startswith("evidence:pltr")
    ]
    assert "PALANTIR" not in json.dumps(proposal.graph).upper()
    assert load_recipient_entity_graph(proposal.graph, as_of=AS_OF)["error_codes"] == []


def test_a_registrant_named_only_in_the_sec_registry_spelling_still_matches_its_filing():
    """The check must not invent a coverage hole where none existed.

    Real 10-K cover pages write "Lockheed Martin Corporation" where the registry
    says "LOCKHEED MARTIN CORP", and the registry appends a state suffix
    ("... /DE/") that no filing repeats.  Both are the same registrant.
    """
    filing = b"<html><body><p>Lockheed Martin Corporation, a Maryland corporation</p></body></html>"

    assert proposal_module._filing_names_the_registrant(filing, "LOCKHEED MARTIN CORP")
    assert proposal_module._filing_names_the_registrant(filing, "LOCKHEED MARTIN CORP /MD/")
    assert not proposal_module._filing_names_the_registrant(filing, "NORTHROP GRUMMAN CORP")
    assert not proposal_module._filing_names_the_registrant(filing, "")


# --- The CLI validates its own output ---------------------------------------


def _cli_argv(out_dir: Path, *tickers: str) -> list[str]:
    return [
        "--out-dir",
        str(out_dir),
        "--user-agent",
        USER_AGENT,
        "--tickers",
        *(tickers or ("PLTR", "BA")),
        "--awards",
        str(FIXTURES / "awards.json"),
        "--published-graph",
        str(CANONICAL_GRAPH_PATH),
        "--as-of",
        AS_OF,
    ]


def test_the_cli_writes_a_loadable_candidate_and_never_the_canonical_graph(tmp_path, capsys):
    before = CANONICAL_GRAPH_PATH.read_bytes()

    code = main(_cli_argv(tmp_path / "out"), fetch=_fetcher())

    assert code == 0
    assert (tmp_path / "out" / CANDIDATE_GRAPH_FILENAME).exists()
    assert (tmp_path / "out" / WORKSHEET_MARKDOWN_FILENAME).exists()
    assert CANONICAL_GRAPH_PATH.read_bytes() == before
    written = json.loads((tmp_path / "out" / CANDIDATE_GRAPH_FILENAME).read_text(encoding="utf-8"))
    assert load_recipient_entity_graph(written, as_of=written["graph_known_at"][:10])[
        "error_codes"
    ] == []
    assert "NOT PUBLISHED" in capsys.readouterr().out


def test_the_cli_refuses_to_write_a_candidate_that_fails_admission(tmp_path, monkeypatch, capsys):
    """A run that prints success over an unloadable document is the worst outcome.

    The analyst discovers it at curate time, days later, with no cause named.
    The tool applies the SAME gate the curate script will, before writing a byte.
    """
    monkeypatch.setattr(
        proposal_module,
        "load_recipient_entity_graph",
        lambda graph, **kwargs: {"status": "invalid", "error_codes": ["duplicate_edge_id"]},
    )
    out_dir = tmp_path / "out"

    code = main(_cli_argv(out_dir), fetch=_fetcher())

    assert code != 0
    assert not out_dir.exists(), "a refused candidate must leave nothing behind"
    printed = capsys.readouterr().out
    assert "duplicate_edge_id" in printed
    assert any(
        line.startswith("::error") for line in printed.splitlines()
    ), "an annotation routed anywhere but the start of a line is dropped by GitHub"


# --- The extractor reaches the legal forms the award panel really uses ------


@pytest.mark.parametrize(
    ("ex21_line", "award_recipient_name"),
    [
        # Both of these are verbatim from data/government_revenue/awards.parquet;
        # both were unreachable while the filters ran on the raw line.
        ("Huntington Ingalls Incorporated", "HUNTINGTON INGALLS INCORPORATED"),
        (
            "L3Harris Technologies Integrated Systems, L.P.",
            "L3HARRIS TECHNOLOGIES INTEGRATED SYSTEMS L.P.",
        ),
        ("Palantir USG, Inc.", "PALANTIR USG INC"),
        ("Marshall of Cambridge Aerospace Limited", "MARSHALL OF CAMBRIDGE AEROSPACE LTD"),
    ],
)
def test_ex21_extraction_reaches_the_legal_forms_the_award_panel_uses(
    ex21_line, award_recipient_name
):
    """"Incorporated" and a dotted "L.P." are legal forms, not table furniture.

    ``\\binc\\b`` cannot match "Incorporated" and ``\\blp\\b`` cannot match
    "L.P.", so testing the RAW line discards them — and a noise pattern anchored
    on ``incorporat\\w*$`` deleted the first one twice over.  Both filters now
    run on ``normalize_legal_name(line)``, which is the only spelling in which
    either form is visible at all.
    """
    document = (
        "<html><body><table>"
        f"<tr><td>{ex21_line}</td><td>Delaware</td></tr>"
        "</table></body></html>"
    )

    assert extract_ex21_names(document) == [ex21_line]
    assert normalize_legal_name(ex21_line) == normalize_legal_name(award_recipient_name)


def test_hii_proposes_its_real_edge_instead_of_a_false_finished_verdict():
    """The regression, end to end, on REAL bytes.

    HII's real EX-21 lists "Huntington Ingalls Incorporated"; the shipped award
    panel carries a recipient of exactly that name holding ``C3NLZNSMU254``; the
    two normalize identically.  The extractor discarded the line, and the tool
    then told the analyst — in the worksheet, in the markdown, in the JSON —
    "This is a finished answer, not an outstanding mapping task."  It was not a
    finished answer, and a zero asserted as final is worse than a zero.
    """
    proposal = _propose(tickers=("HII",))

    assert _ueis(proposal, "HII") == {"C3NLZNSMU254"}
    assert "HII" not in _causes(proposal)
    edge = proposal.worksheet["proposed_edges"][0]
    assert edge["sec_source_name"] == "Huntington Ingalls Incorporated"
    assert edge["sec_source_role"] == "ex21_subsidiary"
    assert edge["sec_source_document"] == "hii-ex211202510xk.htm"
    assert edge["usaspending_recipient_names"] == ["HUNTINGTON INGALLS INCORPORATED"]
    assert edge["normalized_join_key"] == "huntington ingalls inc"
    assert {source["publisher"] for source in edge["evidence"]} == {"SEC", "USAspending.gov"}
    assert load_recipient_entity_graph(proposal.graph, as_of=AS_OF)["error_codes"] == []


def test_a_zero_arrives_with_the_extractors_own_census_of_what_it_discarded():
    """A ``no_exact_match`` verdict is only checkable if the discards are printed."""
    proposal = _propose()

    ge = next(
        row for row in proposal.worksheet["issuers_without_edges"] if row["ticker"] == "GE"
    )
    assert ge["cause"] == "no_exact_match"
    assert ge["ex21_document"] == "ex21subsidiariesofregistra.htm"
    assert ge["ex21_lines_extracted"] == 2
    assert ge["ex21_lines_rejected"] == 5
    assert {sample["reason"] for sample in ge["ex21_rejected_samples"]} <= {
        "matched_noise_filter",
        "no_recognised_corporate_form_tail",
    }
    assert "Subsidiaries of the Registrant" in {
        sample["line"] for sample in ge["ex21_rejected_samples"]
    }
    # Every issuer whose exhibit was read is censused, not only the zeroes.
    census = {row["ticker"]: row for row in proposal.worksheet["ex21_extraction"]}
    assert set(census) == {"PLTR", "GE", "BA", "BWXT"}
    assert proposal.worksheet["counts"]["ex21_lines_extracted"] == sum(
        row["ex21_lines_extracted"] for row in census.values()
    )
    markdown = render_worksheet_markdown(proposal.worksheet)
    assert "EX-21 names kept / rejected" in markdown
    assert "discarded EX-21 line" in markdown


# --- Real EDGAR bytes, pinned ------------------------------------------------

LMT_EX21_SHA256 = "fc800bf2d92e55046d065894f271cb9cd8dedc5d4ed3345da3ede3eb511c37c2"
LMT_EX21_BYTES = 11648
LMT_EX21_SUBSIDIARIES = [
    "Astrolink International, LLC",
    "Helicopter Support, Inc.",
    "Lockheed Martin Australia Pty Limited",
    "Lockheed Martin Canada, Inc.",
    "Lockheed Martin Global, Inc.",
    "Lockheed Martin Investments, Inc.",
    "Lockheed Martin Overseas, LLC",
    "Lockheed Martin UK Ampthill Limited",
    "Lockheed Martin UK Limited",
    "Sikorsky Aircraft Corporation",
    "Sikorsky International Operations, Inc.",
    "Vibrant Star Insurance LLC",
    "Zeta Associates, Inc.",
]


def test_real_ex21_bytes_pin_both_halves_of_the_extractor():
    """Hand-written markup cannot fail the way EDGAR does.

    ``sec_ex21_lmt_real.htm`` is Lockheed Martin's 2025 EX-21 verbatim, sha256
    pinned so a "fixed" fixture cannot quietly become a synthetic one.  It pins
    the KEEP half (13 subsidiaries, including three "Limited" spellings the
    normalizer folds to ``ltd``) and the DROP half in the same assertion: its
    heading, "Subsidiaries of Lockheed Martin Corporation", ends in a corporate
    form and passes the tail test, so only the noise filter keeps it out of the
    join.  Delete that filter and this test is the one that notices.
    """
    body = (FIXTURES / "sec_ex21_lmt_real.htm").read_bytes()
    assert hashlib.sha256(body).hexdigest() == LMT_EX21_SHA256
    assert len(body) == LMT_EX21_BYTES

    extraction = extract_ex21_lines(body.decode("utf-8"))

    assert extraction.names == LMT_EX21_SUBSIDIARIES
    discarded = {row["line"]: row["reason"] for row in extraction.rejected}
    assert discarded["Subsidiaries of Lockheed Martin Corporation"] == "matched_noise_filter"
    assert discarded["Name of Subsidiary"] == "matched_noise_filter"
    assert discarded["Place of Formation"] == "matched_noise_filter"
    assert discarded["Delaware"] == "no_recognised_corporate_form_tail"
    assert not set(extraction.names) & set(discarded)


def test_the_real_hii_exhibit_keeps_the_name_the_award_panel_pays():
    """The same pin on the exhibit that carried the defect."""
    body = (FIXTURES / "sec_ex21_hii_real.htm").read_bytes()
    assert hashlib.sha256(body).hexdigest() == (
        "ea19325cf78305eaa8ef2cdf11860e63144ba855f20193c9901bf99047dfa0f2"
    )
    assert len(body) == 19400

    names = extract_ex21_names(body.decode("utf-8"))

    assert "Huntington Ingalls Incorporated" in names
    assert "HII Mission Technologies Corp." in names
    assert len(names) == 35
    assert not any("Subsidiar" in name for name in names)


def test_ownership_walk_gives_every_subsidiary_a_parent_that_reaches_the_issuer():
    proposal = _propose()
    companies = {row["company_id"] for row in proposal.graph["companies"]}
    entities = {row["entity_id"] for row in proposal.graph["legal_entities"]}
    parents = {
        row["child_entity_id"]: row.get("parent_entity_id") or row.get("parent_company_id")
        for row in proposal.graph["ownership_edges"]
    }

    assert entities == set(parents)
    for child, parent in parents.items():
        assert parent in companies | entities
        assert parent != child
    issuer_edges = [
        row for row in proposal.graph["ownership_edges"]
        if row["relationship"] == "issuer_legal_entity"
    ]
    assert {row["parent_company_id"] for row in issuer_edges} == companies
    assert all(row["economic_share"] == 1.0 for row in proposal.graph["ownership_edges"])
