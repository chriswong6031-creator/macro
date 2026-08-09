"""Tests for the W3-C sponsor -> ticker reviewed map.

The map is a bounded, curated, PR-reviewed lookup, not an inferred join and not
a point-in-time identity service.  These tests pin the review semantics that
are the whole point of the lane:

* no row may be admitted WITHOUT attributed human authority — an admitted row
  must carry a complete operator attestation (named reviewer, timestamp, and
  the authorizing ruling bound by path and content digest), so a model cannot
  promote its own suggestion into an authoritative link;
* the reader resolves ``reviewed_admitted`` rows and refuses everything else
  with a REASON instead of a guess;
* ambiguity is queued with its competing candidates recorded, never picked, and
  a blanket authorization does not resolve it;
* an admitted row says whether its ticker is the sponsor itself or the
  sponsor's PARENT, so a subsidiary row cannot read as an issuer row; and
* the effective interval is mandatory, so a rename or ticker reuse opens a new
  interval instead of rewriting history.

The 29 candidate rows were admitted by the repository operator on 2026-08-07
under ``research/BIOCATALYST_OPERATOR_RULING_2026-08-07.md`` (Ruling 2).  The 20
ambiguous rows stayed queued: a blanket "yes" cannot answer a
subsidiary-versus-parent or joint-venture question.

Ruling 3 (2026-08-08) then answered ONE of those questions per-case: the four
``subsidiary_of_listed_issuer`` rows were admitted to their listed parents, and
the other **16 stay queued**.  ``test_the_sixteen_still_ambiguous_rows_were_left_exactly_as_they_were``
holds those 16 byte-identical to the base branch, so an admission the operator
did authorize cannot quietly carry along one they did not.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from engine.biocatalyst.sponsor_identity import (
    ADMITTED_MAP_STATE,
    ATTESTATION_FIELDS,
    BASKET_MEMBERSHIP_PATH,
    CANDIDATE_ONLY_STATE,
    HEALTHCARE_BASKETS,
    ISSUER_RELATIONSHIPS,
    PARENT_OF_SUBSIDIARY_SPONSOR,
    RESOLVABLE_REVIEW_STATES,
    REVIEW_STATES,
    SPONSOR_TICKER_MAP_CONTRACT_ID,
    SPONSOR_TICKER_MAP_PATH,
    UNAVAILABLE_AMBIGUOUS,
    UNAVAILABLE_AWAITING_REVIEW,
    UNAVAILABLE_OUTSIDE_INTERVAL,
    UNAVAILABLE_SPONSOR_UNKNOWN,
    healthcare_universe_tickers,
    load_sponsor_ticker_map,
    normalized_sponsor_key,
    resolve_sponsor,
    review_queue,
    sponsor_ticker_map_semantic_issues,
    validate_sponsor_ticker_map,
)
from engine.sector_intelligence.contracts import ContractValidationError


ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / SPONSOR_TICKER_MAP_PATH
MODULE_PATH = ROOT / "engine" / "biocatalyst" / "sponsor_identity.py"
AS_OF = "2026-09-01"

RULING_REF = "research/BIOCATALYST_OPERATOR_RULING_2026-08-07.md"
RULING_SHA256 = "6d6fe5771b70a2c3f6eacab4b2b1bb270331a1bc8c121064293905846d98a530"
ADMITTED_ROW_COUNT = 33
QUEUED_ROW_COUNT = 16

# Ruling 2 admitted 29 rows on 2026-08-07; Ruling 3 admitted the four
# subsidiary rows on 2026-08-08.  Both dates are pinned, per cohort, so an
# attestation cannot silently drift onto a third date.
RULING_2_REVIEWED_DATE = "2026-08-07"
RULING_3_REVIEWED_DATE = "2026-08-08"
RULING_3_SUBSIDIARY_ADMISSIONS = {
    "Cepheid": "DHR",
    "Genentech, Inc.": "RHHBY",
    "Janssen Research & Development, LLC": "JNJ",
    "Merck Sharp & Dohme LLC": "MRK",
}
STILL_QUEUED_SNAPSHOT = (
    ROOT
    / "tests"
    / "fixtures"
    / "biocatalyst"
    / "sponsor_map_still_queued_rows_2026-08-07.yml.txt"
)


def _raw_row_blocks() -> dict[str, str]:
    """Split the committed map's ``rows:`` section into raw per-row TEXT.

    Byte-level, deliberately: the point of the still-queued snapshot is that a
    row the operator did not decide is unchanged down to its punctuation, and a
    parse-then-compare would forgive a reworded note or a re-quoted string.
    """

    lines = MAP_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.rstrip("\n") == "rows:") + 1
    end = next(i for i, line in enumerate(lines) if line.startswith("unmapped_universe_tickers:"))
    blocks: dict[str, str] = {}
    name, buffer = None, []
    for line in lines[start:end]:
        if line.startswith("  - sponsor_name: "):
            if name is not None:
                blocks[name] = "".join(buffer)
            name = line.split(": ", 1)[1].strip().strip('"')
            buffer = [line]
        else:
            buffer.append(line)
    blocks[name] = "".join(buffer)
    return blocks


@pytest.fixture(scope="module")
def document() -> dict:
    return load_sponsor_ticker_map(ROOT)


@pytest.fixture(scope="module")
def universe() -> tuple[str, ...]:
    return healthcare_universe_tickers(ROOT)


def _codes(error: ContractValidationError) -> set[str]:
    return {issue.code for issue in error.issues}


def _expect_issue(document: dict, code: str) -> None:
    with pytest.raises(ContractValidationError) as caught:
        validate_sponsor_ticker_map(document, repo_root=ROOT)
    assert code in _codes(caught.value), sorted(_codes(caught.value))


def _admitted(row: dict, *, ticker: str) -> dict:
    admitted = copy.deepcopy(row)
    admitted.pop("ambiguity_reason", None)
    admitted["ticker"] = ticker
    admitted["review_state"] = "reviewed_admitted"
    admitted["issuer_relationship"] = "direct_issuer"
    admitted["confidence_class"] = "strong_candidate"
    admitted["provenance"]["kind"] = "human_reviewed_source"
    admitted["review"] = {
        "reviewed_by": "test reviewer",
        "reviewed_at": "2026-08-08T00:00:00Z",
        "review_reference": "hypothetical review, tests only",
        "ruling_ref": RULING_REF,
        "ruling_sha256": RULING_SHA256,
    }
    return admitted


def _as_candidate(row: dict) -> dict:
    """Return the pre-admission form of a row: suggested, never reviewed."""

    candidate = copy.deepcopy(row)
    candidate["review_state"] = "candidate_unreviewed"
    candidate.pop("issuer_relationship", None)
    candidate["provenance"]["kind"] = "model_suggested_candidate"
    candidate["review"] = {
        "reviewed_by": None,
        "reviewed_at": None,
        "review_reference": None,
    }
    return candidate


def _an_admitted_row(document: dict) -> dict:
    return next(row for row in document["rows"] if row["review_state"] == "reviewed_admitted")


def _rebuilt(document: dict, rows: list[dict], *, state: str) -> dict:
    rebuilt = copy.deepcopy(document)
    rebuilt["rows"] = rows
    rebuilt["state"] = state
    claimed = {row["ticker"] for row in rows if row.get("ticker")}
    rebuilt["unmapped_universe_tickers"] = sorted(set(healthcare_universe_tickers(ROOT)) - claimed)
    return rebuilt


# --------------------------------------------------------------------------
# The committed file
# --------------------------------------------------------------------------


def test_committed_map_validates_against_its_contract(document: dict) -> None:
    assert document["contract_id"] == SPONSOR_TICKER_MAP_CONTRACT_ID
    assert document["schema"] == SPONSOR_TICKER_MAP_CONTRACT_ID
    assert document["owner"] == "biocatalyst"
    assert document["authority"] == "facts_and_context_only"
    assert document["authority_ceiling"] == "A1_EXPLAIN"
    assert document["purpose"] == "post_selection_context_only"
    assert sponsor_ticker_map_semantic_issues(document, repo_root=ROOT) == []


def test_every_admitted_row_carries_an_operator_attestation_so_a_model_cannot_self_promote(
    document: dict,
) -> None:
    # The lane's non-negotiable, in its stronger form.  The old fence was
    # "nothing may be admitted".  The fence now is "nothing may be admitted
    # WITHOUT attributed human authority": a model can write any of these
    # strings, but it cannot make a ruling document exist at a digest it does
    # not control, and it cannot name a human authorizer it did not have.
    assert document["state"] == ADMITTED_MAP_STATE
    assert document["review_policy"]["model_may_admit"] is False
    assert document["review_policy"]["admission_authority"] == "named_human_pull_request_review_only"
    assert document["review_policy"]["default_review_state"] == "candidate_unreviewed"
    assert list(document["review_policy"]["resolvable_review_states"]) == ["reviewed_admitted"]

    ruling = document["operator_ruling"]
    assert ruling["reference"] == RULING_REF
    assert ruling["sha256"] == RULING_SHA256
    assert ruling["ruled_at"].startswith("2026-08-07")
    assert "operator" in ruling["authorizing_operator"].lower()

    admitted = [row for row in document["rows"] if row["review_state"] == "reviewed_admitted"]
    assert len(admitted) == ADMITTED_ROW_COUNT
    for row in admitted:
        review = row["review"]
        for field in ATTESTATION_FIELDS:
            assert isinstance(review.get(field), str) and review[field].strip(), (
                row["sponsor_name"],
                field,
            )
        assert review["ruling_ref"] == RULING_REF
        assert review["ruling_sha256"] == RULING_SHA256
        # Two rulings, two dates.  Each cohort is pinned to its OWN date rather
        # than the file to one date, so neither can drift and no third date can
        # appear.
        assert review["reviewed_at"].startswith(
            RULING_3_REVIEWED_DATE
            if row["sponsor_name"] in RULING_3_SUBSIDIARY_ADMISSIONS
            else RULING_2_REVIEWED_DATE
        ), (row["sponsor_name"], review["reviewed_at"])
        # Admission is not source verification: the link is still one a model
        # suggested, and the row keeps saying so.
        assert row["provenance"]["kind"] == "model_suggested_candidate"
        assert "Unverified against a live" in row["provenance"]["note"]


def test_a_row_admitted_without_an_attestation_fails(document: dict) -> None:
    forged = copy.deepcopy(document)
    row = next(r for r in forged["rows"] if r["review_state"] == "reviewed_admitted")
    row["review"] = {
        "reviewed_by": None,
        "reviewed_at": None,
        "review_reference": None,
        "ruling_ref": None,
        "ruling_sha256": None,
    }
    _expect_issue(forged, "sponsor_map.admitted_attestation")

    # Partial attestations fail one field at a time, including the two that
    # bind the authorizing document.
    for field in ATTESTATION_FIELDS:
        partial = copy.deepcopy(document)
        target = next(r for r in partial["rows"] if r["review_state"] == "reviewed_admitted")
        target["review"][field] = None
        _expect_issue(partial, "sponsor_map.admitted_attestation")


def test_an_admitted_row_may_not_cite_a_ruling_the_document_does_not_declare(
    document: dict,
) -> None:
    strayed = copy.deepcopy(document)
    row = next(r for r in strayed["rows"] if r["review_state"] == "reviewed_admitted")
    row["review"]["ruling_sha256"] = "0" * 64
    _expect_issue(strayed, "sponsor_map.admission_ruling_binding")

    orphaned = copy.deepcopy(document)
    orphaned.pop("operator_ruling")
    _expect_issue(orphaned, "sponsor_map.admission_ruling")


def test_the_declared_ruling_digest_matches_the_committed_ruling_document() -> None:
    # An enablement that only names a document proves nothing; the digest binds
    # the exact bytes.  The ruling may still be in flight on its own branch, in
    # which case there is nothing on disk to compare and the digest stands as
    # the claim this map is committing to.
    ruling = ROOT / RULING_REF
    if not ruling.is_file():
        pytest.skip(f"{RULING_REF} is not committed on this branch")
    assert hashlib.sha256(ruling.read_bytes()).hexdigest() == RULING_SHA256


def test_a_ruling_document_edited_after_the_fact_invalidates_the_admissions(
    document: dict, tmp_path: Path
) -> None:
    # The digest is the whole point of citing the ruling by content: if the
    # authorizing document changes, the admissions no longer carry the
    # authorization they claim.  Exercised against a temporary root so it runs
    # whether or not the ruling has landed on this branch yet.
    root = tmp_path / "repo"
    (root / "research").mkdir(parents=True)
    (root / "data" / "baskets").mkdir(parents=True)
    (root / "data" / "baskets" / "membership.json").write_bytes(
        (ROOT / BASKET_MEMBERSHIP_PATH).read_bytes()
    )

    (root / RULING_REF).write_text("the ruling, exactly as cited", encoding="utf-8")
    honest = copy.deepcopy(document)
    honest["operator_ruling"]["sha256"] = hashlib.sha256(
        b"the ruling, exactly as cited"
    ).hexdigest()
    for row in honest["rows"]:
        if row["review_state"] == "reviewed_admitted":
            row["review"]["ruling_sha256"] = honest["operator_ruling"]["sha256"]
    assert [
        issue.code
        for issue in sponsor_ticker_map_semantic_issues(honest, repo_root=root)
        if issue.code.startswith("sponsor_map.admission")
    ] == []

    (root / RULING_REF).write_text("the ruling, quietly rewritten", encoding="utf-8")
    codes = {issue.code for issue in sponsor_ticker_map_semantic_issues(honest, repo_root=root)}
    assert "sponsor_map.admission_ruling_digest" in codes, sorted(codes)


def test_the_sixteen_still_ambiguous_rows_were_left_exactly_as_they_were(document: dict) -> None:
    # Ruling 3 answered ONE ambiguity group per-case.  It did not answer the
    # rest, and an authorized admission must not carry an unauthorized one
    # along with it.  These 16 are held byte-identical to the base branch:
    # tests/fixtures/biocatalyst/sponsor_map_still_queued_rows_2026-08-07.yml.txt
    # is the raw text of those rows as claude/bio-execute-operator-ruling
    # committed them, so a reclassification, a reworded note, or a re-dated
    # interval on any of them fails here even if it still parses and validates.
    queued = [row for row in document["rows"] if row["review_state"] == "ambiguous_queued"]
    assert len(queued) == QUEUED_ROW_COUNT
    assert len(review_queue(document)) == QUEUED_ROW_COUNT
    assert not (
        {row["sponsor_name"] for row in queued} & set(RULING_3_SUBSIDIARY_ADMISSIONS)
    ), "Ruling 3 admitted the four subsidiary rows; they are not queued any more"

    for row in queued:
        assert row["ticker"] is None
        assert row["confidence_class"] == "unresolved"
        assert row["ambiguity_reason"]
        assert row["ambiguity_reason"] != "subsidiary_of_listed_issuer"
        assert "issuer_relationship" not in row
        assert row["provenance"]["kind"] == "model_suggested_candidate"
        assert row["review"] == {
            "reviewed_by": None,
            "reviewed_at": None,
            "review_reference": None,
        }

    blocks = _raw_row_blocks()
    frozen = STILL_QUEUED_SNAPSHOT.read_text(encoding="utf-8")
    frozen_body = "".join(
        line for line in frozen.splitlines(keepends=True) if not line.startswith("#")
    )
    live_body = "".join(blocks[row["sponsor_name"]] for row in queued)
    assert live_body == frozen_body


def test_the_committed_rows_are_exactly_the_admitted_and_the_still_queued(document: dict) -> None:
    counts: dict[str, int] = {}
    for row in document["rows"]:
        counts[row["review_state"]] = counts.get(row["review_state"], 0) + 1
    assert counts == {
        "reviewed_admitted": ADMITTED_ROW_COUNT,
        "ambiguous_queued": QUEUED_ROW_COUNT,
    }


def test_the_four_admitted_subsidiary_rows_say_the_ticker_is_the_parent(document: dict) -> None:
    # Ruling 3's substance is a MODELLING CHOICE with a visible consequence: a
    # Genentech trial surfaces under Roche.  A reader must be able to tell that
    # from a trial Roche sponsored itself, so the row records the relationship
    # rather than leaving it to be inferred from the name.
    by_name = {row["sponsor_name"]: row for row in document["rows"]}
    for sponsor, parent in RULING_3_SUBSIDIARY_ADMISSIONS.items():
        row = by_name[sponsor]
        assert row["review_state"] == "reviewed_admitted", sponsor
        assert row["ticker"] == parent, sponsor
        assert row["issuer_relationship"] == PARENT_OF_SUBSIDIARY_SPONSOR, sponsor
        assert "ambiguity_reason" not in row, sponsor
        assert "PARENT" in row["note"], sponsor
        assert "Ruling 3" in row["review"]["review_reference"], sponsor

        # The reader carries the relationship out with the answer, so a caller
        # never has to re-open the row to learn the ticker is not the sponsor.
        resolution = resolve_sponsor(sponsor, as_of=AS_OF, document=document)
        assert resolution.status == "resolved"
        assert resolution.ticker == parent
        assert resolution.issuer_relationship == PARENT_OF_SUBSIDIARY_SPONSOR
        assert resolution.ticker_is_the_parent_of_a_subsidiary_sponsor is True

    # The other 29 are the issuer itself, and say so.  Silence is not allowed on
    # either side: every admitted row answers the question.
    admitted = [row for row in document["rows"] if row["review_state"] == "reviewed_admitted"]
    assert len(admitted) == ADMITTED_ROW_COUNT
    relationships = {row["issuer_relationship"] for row in admitted}
    assert relationships == set(ISSUER_RELATIONSHIPS)
    direct = [row for row in admitted if row["issuer_relationship"] == "direct_issuer"]
    assert len(direct) == ADMITTED_ROW_COUNT - len(RULING_3_SUBSIDIARY_ADMISSIONS)
    for row in direct:
        assert resolve_sponsor(
            row["sponsor_name"], as_of=AS_OF, document=document
        ).ticker_is_the_parent_of_a_subsidiary_sponsor is False


def test_an_admitted_row_that_does_not_say_whose_ticker_it_names_is_rejected(
    document: dict,
) -> None:
    silent = copy.deepcopy(document)
    next(r for r in silent["rows"] if r["review_state"] == "reviewed_admitted").pop(
        "issuer_relationship"
    )
    _expect_issue(silent, "sponsor_map.admitted_issuer_relationship")

    # An unknown word is not an answer either.
    invented = copy.deepcopy(document)
    next(r for r in invented["rows"] if r["review_state"] == "reviewed_admitted")[
        "issuer_relationship"
    ] = "affiliate_of_something"
    _expect_issue(invented, "sponsor_map.admitted_issuer_relationship")

    # And a row that resolves nothing may not claim a relationship to an issuer.
    strayed = copy.deepcopy(document)
    next(r for r in strayed["rows"] if r["review_state"] == "ambiguous_queued")[
        "issuer_relationship"
    ] = "direct_issuer"
    _expect_issue(strayed, "sponsor_map.issuer_relationship_scope")


def test_no_admitted_row_names_a_ticker_outside_the_declared_universe(
    document: dict, universe: tuple[str, ...]
) -> None:
    # Admission widens what the map answers; it may never widen WHAT IT MAY
    # NAME.  The four parents Ruling 3 admitted are inside the declared 70 —
    # checked against the basket file, not against a list written here.
    universe_set = set(universe)
    assert len(universe_set) == 70
    for row in document["rows"]:
        if row["review_state"] != "reviewed_admitted":
            continue
        assert row["ticker"] in universe_set, (row["sponsor_name"], row["ticker"])
    for sponsor, parent in RULING_3_SUBSIDIARY_ADMISSIONS.items():
        assert parent in universe_set, sponsor


def test_all_thirty_three_admitted_rows_bind_the_same_current_ruling_digest(
    document: dict,
) -> None:
    # Ruling 3 was written into the SAME document Ruling 2 lives in, so amending
    # it moved the digest that all 29 earlier rows attest to.  Every admitted
    # row must carry the NEW digest, and that digest must be the ruling on disk
    # right now — a row still citing the pre-amendment bytes is attesting to an
    # authorization that no longer exists in that form.
    admitted = [row for row in document["rows"] if row["review_state"] == "reviewed_admitted"]
    assert len(admitted) == ADMITTED_ROW_COUNT

    digests = {row["review"]["ruling_sha256"] for row in admitted}
    refs = {row["review"]["ruling_ref"] for row in admitted}
    assert digests == {document["operator_ruling"]["sha256"]}, sorted(digests)
    assert refs == {document["operator_ruling"]["reference"]}, sorted(refs)

    ruling = ROOT / RULING_REF
    assert ruling.is_file(), f"{RULING_REF} must be committed alongside the admissions it binds"
    live = hashlib.sha256(ruling.read_bytes()).hexdigest()
    assert digests == {live}, (sorted(digests), live)

    # The amendment is what the four new rows were admitted under, so it has to
    # actually be in the bytes being hashed.
    text = ruling.read_text(encoding="utf-8")
    assert "Ruling 3" in text
    for sponsor, parent in RULING_3_SUBSIDIARY_ADMISSIONS.items():
        assert sponsor in text, sponsor
        assert parent in text, parent


def test_committed_map_declares_the_full_forbidden_use_list(document: dict) -> None:
    prohibited = set(document["prohibited_uses"])
    assert {
        "originate_signal",
        "rank_security",
        "reorder_candidate",
        "select_security",
        "size_position",
        "gate_decision",
        "score",
        "prophet_authority",
        "neural_web_authority",
        "fuzzy_name_matching",
    } <= prohibited


# --------------------------------------------------------------------------
# The universe is derived, never hardcoded
# --------------------------------------------------------------------------


def test_universe_is_derived_from_the_basket_file_at_read_time(universe: tuple[str, ...]) -> None:
    payload = json.loads((ROOT / BASKET_MEMBERSHIP_PATH).read_text(encoding="utf-8"))
    expected = sorted(
        {
            member["ticker"]
            for basket in HEALTHCARE_BASKETS
            for member in payload["baskets"][basket]["members"]
        }
    )
    assert list(universe) == expected
    assert len(universe) == 70


def test_map_source_carries_no_hardcoded_ticker_roster() -> None:
    # The declared universe must come from data/baskets/membership.json, so a
    # basket edit cannot leave the reader silently honouring a departed name.
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert BASKET_MEMBERSHIP_PATH in source
    for ticker in ("AMGN", "LLY", "PFE", "MRNA", "UNH"):
        assert f'"{ticker}"' not in source


def test_declared_universe_count_must_match_the_derived_universe(document: dict) -> None:
    drifted = copy.deepcopy(document)
    drifted["universe"]["distinct_ticker_count"] = 69
    _expect_issue(drifted, "sponsor_map.universe_count")


def test_a_ticker_outside_the_declared_universe_is_rejected(document: dict) -> None:
    strayed = copy.deepcopy(document)
    for row in strayed["rows"]:
        if row["review_state"] == "reviewed_admitted":
            row["ticker"] = "NVDA"
            break
    strayed["unmapped_universe_tickers"] = sorted(
        set(healthcare_universe_tickers(ROOT))
        - {row["ticker"] for row in strayed["rows"] if row.get("ticker")}
    )
    _expect_issue(strayed, "sponsor_map.ticker_universe")


def test_unmapped_universe_tickers_is_the_exact_unclaimed_complement(document: dict) -> None:
    claimed = {row["ticker"] for row in document["rows"] if row.get("ticker")}
    assert list(document["unmapped_universe_tickers"]) == sorted(
        set(healthcare_universe_tickers(ROOT)) - claimed
    )
    assert claimed, "the map must carry at least one candidate link"
    assert document["unmapped_universe_tickers"], "coverage is not the goal; absence must stay visible"

    hidden = copy.deepcopy(document)
    hidden["unmapped_universe_tickers"] = hidden["unmapped_universe_tickers"][:-1]
    _expect_issue(hidden, "sponsor_map.unmapped_complement")


# --------------------------------------------------------------------------
# The reader resolves the admitted and refuses everything else
# --------------------------------------------------------------------------


def test_reader_resolves_admitted_rows_and_refuses_the_still_queued(document: dict) -> None:
    assert RESOLVABLE_REVIEW_STATES == frozenset({"reviewed_admitted"})
    for row in document["rows"]:
        resolution = resolve_sponsor(row["sponsor_name"], as_of=AS_OF, document=document)
        if row["review_state"] == "reviewed_admitted":
            assert resolution.status == "resolved"
            assert resolution.available is True
            assert resolution.ticker == row["ticker"]
            assert resolution.review_state == "reviewed_admitted"
        else:
            assert resolution.status == "unavailable"
            assert resolution.available is False
            assert resolution.ticker is None
            assert resolution.reason == UNAVAILABLE_AMBIGUOUS


def test_a_candidate_unreviewed_row_does_not_resolve_but_its_admitted_twin_does(document: dict) -> None:
    admitted_row = _an_admitted_row(document)
    candidate = _as_candidate(admitted_row)
    sponsor = candidate["sponsor_name"]
    ticker = candidate["ticker"]

    unreviewed = _rebuilt(document, [copy.deepcopy(candidate)], state=CANDIDATE_ONLY_STATE)
    validate_sponsor_ticker_map(unreviewed, repo_root=ROOT)
    refused = resolve_sponsor(sponsor, as_of=AS_OF, document=unreviewed)
    assert (refused.status, refused.reason, refused.ticker) == (
        "unavailable",
        UNAVAILABLE_AWAITING_REVIEW,
        None,
    )

    reviewed = _rebuilt(
        document,
        [_admitted(candidate, ticker=ticker)],
        state="reviewed_map_contains_admitted_rows",
    )
    validate_sponsor_ticker_map(reviewed, repo_root=ROOT)
    resolved = resolve_sponsor(sponsor, as_of=AS_OF, document=reviewed)
    assert resolved.status == "resolved"
    assert resolved.available is True
    assert resolved.ticker == ticker
    assert resolved.review_state == "reviewed_admitted"


def test_an_unknown_sponsor_is_unavailable_with_a_reason_not_a_nearest_match(document: dict) -> None:
    resolution = resolve_sponsor("Northstar Biopharma", as_of=AS_OF, document=document)
    assert resolution.status == "unavailable"
    assert resolution.reason == UNAVAILABLE_SPONSOR_UNKNOWN
    assert resolution.ticker is None
    assert resolution.candidate_tickers == ()

    # A case/whitespace variant of a real row is still unknown: the lookup is an
    # exact string match and never a fuzzy one.
    known = document["rows"][0]["sponsor_name"]
    variant = resolve_sponsor(f"  {known.upper()}  ", as_of=AS_OF, document=document)
    assert variant.reason == UNAVAILABLE_SPONSOR_UNKNOWN


def test_ambiguous_rows_record_competing_candidates_and_never_resolve(document: dict) -> None:
    queued = [row for row in document["rows"] if row["review_state"] == "ambiguous_queued"]
    assert queued, "the map must show its ambiguities rather than guess them"
    reasons = {row["ambiguity_reason"] for row in queued}
    assert {
        "renamed_entity",
        "multiple_matching_issuers",
        "issuer_outside_declared_universe",
        "joint_venture",
        "contract_research_organization_sponsor",
    } <= reasons
    # Ruling 3 emptied exactly one group and left the rest.  The map must not
    # still be queuing a question the operator answered, nor have quietly
    # answered one they did not.
    assert "subsidiary_of_listed_issuer" not in reasons
    for row in queued:
        assert row["ticker"] is None
        assert row["confidence_class"] == "unresolved"
        resolution = resolve_sponsor(row["sponsor_name"], as_of=AS_OF, document=document)
        assert resolution.reason == UNAVAILABLE_AMBIGUOUS
        assert resolution.ambiguity_reason == row["ambiguity_reason"]
        assert list(resolution.candidate_tickers) == list(row["candidate_tickers"])


def test_an_ambiguous_row_may_not_carry_a_resolved_ticker(document: dict) -> None:
    forced = copy.deepcopy(document)
    row = next(row for row in forced["rows"] if row["review_state"] == "ambiguous_queued")
    row["ticker"] = row["candidate_tickers"][0] if row["candidate_tickers"] else "MRK"
    forced["unmapped_universe_tickers"] = sorted(
        set(healthcare_universe_tickers(ROOT))
        - {item["ticker"] for item in forced["rows"] if item.get("ticker")}
    )
    _expect_issue(forced, "sponsor_map.ambiguous_ticker")


def test_an_unreviewed_row_may_not_forge_a_review_block(document: dict) -> None:
    candidate = _as_candidate(_an_admitted_row(document))
    candidate["review"]["reviewed_by"] = "a model, which is not a reviewer"
    forged = _rebuilt(document, [candidate], state=CANDIDATE_ONLY_STATE)
    _expect_issue(forged, "sponsor_map.unreviewed_review_block")

    # The two fields that bind the authorizing ruling are part of the same
    # fence: an unreviewed row may not carry them either.
    forged_ruling = _as_candidate(_an_admitted_row(document))
    forged_ruling["review"]["ruling_sha256"] = RULING_SHA256
    _expect_issue(
        _rebuilt(document, [forged_ruling], state=CANDIDATE_ONLY_STATE),
        "sponsor_map.unreviewed_review_block",
    )


def test_a_queued_row_may_not_forge_a_review_block(document: dict) -> None:
    forged = copy.deepcopy(document)
    row = next(row for row in forged["rows"] if row["review_state"] == "ambiguous_queued")
    row["review"]["reviewed_by"] = "a model, which is not a reviewer"
    _expect_issue(forged, "sponsor_map.queued_review_block")


def test_a_candidate_only_map_may_not_contain_an_admitted_row(document: dict) -> None:
    candidate = _as_candidate(_an_admitted_row(document))
    self_promoted = _rebuilt(
        document,
        [_admitted(candidate, ticker=candidate["ticker"])],
        state=CANDIDATE_ONLY_STATE,
    )
    _expect_issue(self_promoted, "sponsor_map.self_promotion")


# --------------------------------------------------------------------------
# Corporate-action awareness
# --------------------------------------------------------------------------


def test_a_row_outside_its_effective_interval_is_unavailable(document: dict) -> None:
    row = document["rows"][0]
    before = resolve_sponsor(row["sponsor_name"], as_of="2020-01-01", document=document)
    assert before.status == "unavailable"
    assert before.reason == UNAVAILABLE_OUTSIDE_INTERVAL


def test_overlapping_intervals_for_one_sponsor_are_rejected(document: dict) -> None:
    candidate = _as_candidate(_an_admitted_row(document))
    first = copy.deepcopy(candidate)
    first["valid_to"] = "2027-01-01"
    second = copy.deepcopy(candidate)
    second["valid_from"] = "2026-12-01"
    overlapping = _rebuilt(document, [first, second], state=CANDIDATE_ONLY_STATE)
    _expect_issue(overlapping, "sponsor_map.interval_overlap")

    second["valid_from"] = "2027-01-01"
    adjacent = _rebuilt(document, [first, second], state=CANDIDATE_ONLY_STATE)
    validate_sponsor_ticker_map(adjacent, repo_root=ROOT)


def test_ticker_reuse_cannot_rewrite_the_earlier_interval(document: dict) -> None:
    candidate = _as_candidate(_an_admitted_row(document))
    universe = healthcare_universe_tickers(ROOT)
    successor_ticker = next(t for t in universe if t != candidate["ticker"])

    first = _admitted(candidate, ticker=candidate["ticker"])
    first["valid_to"] = "2027-01-01"
    second = _admitted(candidate, ticker=successor_ticker)
    second["valid_from"] = "2027-01-01"
    document_pair = _rebuilt(document, [first, second], state="reviewed_map_contains_admitted_rows")
    validate_sponsor_ticker_map(document_pair, repo_root=ROOT)

    sponsor = candidate["sponsor_name"]
    assert resolve_sponsor(sponsor, as_of="2026-09-01", document=document_pair).ticker == candidate["ticker"]
    assert resolve_sponsor(sponsor, as_of="2027-06-01", document=document_pair).ticker == successor_ticker


def test_a_model_suggested_row_may_not_backdate_its_interval(document: dict) -> None:
    backdated = copy.deepcopy(document)
    backdated["rows"][0]["valid_from"] = "2019-01-01"
    _expect_issue(backdated, "sponsor_map.no_backdating")


def test_rows_stay_uniquely_keyed_and_sorted(document: dict) -> None:
    keys = [(row["sponsor_name"], row["valid_from"]) for row in document["rows"]]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)

    shuffled = copy.deepcopy(document)
    shuffled["rows"] = list(reversed(shuffled["rows"]))
    _expect_issue(shuffled, "sponsor_map.row_order")


def test_two_rows_that_normalize_alike_may_not_claim_different_tickers(document: dict) -> None:
    candidate = _as_candidate(_an_admitted_row(document))
    universe = healthcare_universe_tickers(ROOT)
    twin = copy.deepcopy(candidate)
    twin["sponsor_name"] = candidate["sponsor_name"].upper() + " "
    twin["ticker"] = next(t for t in universe if t != candidate["ticker"])
    rows = sorted(
        [copy.deepcopy(candidate), twin],
        key=lambda row: (row["sponsor_name"], row["valid_from"]),
    )
    collided = _rebuilt(document, rows, state=CANDIDATE_ONLY_STATE)
    _expect_issue(collided, "sponsor_map.normalized_collision")
    assert normalized_sponsor_key(twin["sponsor_name"]) == normalized_sponsor_key(
        candidate["sponsor_name"]
    )


# --------------------------------------------------------------------------
# Boundaries
# --------------------------------------------------------------------------


def test_review_states_are_exactly_the_four_declared_states() -> None:
    assert REVIEW_STATES == (
        "candidate_unreviewed",
        "reviewed_admitted",
        "reviewed_rejected",
        "ambiguous_queued",
    )
    schema = json.loads(
        (
            ROOT
            / "contracts"
            / "biocatalyst"
            / "biocatalyst_sponsor_ticker_map.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        tuple(schema["$defs"]["row"]["properties"]["review_state"]["enum"]) == REVIEW_STATES
    )


def test_the_map_is_wired_to_no_scoring_prophet_or_route_path() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    imports = [
        line.strip()
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
    ]
    for line in imports:
        lowered = line.lower()
        for forbidden in ("prophet", "fastapi", "starlette", "requests", "neuralweb", "boto3"):
            assert forbidden not in lowered, line

    # Nothing outside this lane's own test may import the reader: no Prophet
    # path, no Neural Web path, no scoring path, and no route.
    referencing = sorted(
        path.relative_to(ROOT).as_posix()
        for directory in ("engine", "scripts", "app", "admin", "tests")
        for path in (ROOT / directory).rglob("*.py")
        if path != MODULE_PATH
        and any(
            marker in path.read_text(encoding="utf-8", errors="ignore")
            for marker in (
                "engine.biocatalyst.sponsor_identity",
                "biocatalyst import sponsor_identity",
                "from .sponsor_identity",
            )
        )
    )
    assert referencing == ["tests/test_biocatalyst_sponsor_ticker_map.py"], referencing


def test_the_config_is_yaml_the_repo_can_round_trip() -> None:
    parsed = yaml.safe_load(MAP_PATH.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    assert parsed["contract_id"] == SPONSOR_TICKER_MAP_CONTRACT_ID
