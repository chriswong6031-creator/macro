"""Tests for the W3-C sponsor -> ticker reviewed candidate map.

The map is a bounded, curated, PR-reviewed lookup, not an inferred join and not
a point-in-time identity service.  These tests pin the review semantics that
are the whole point of the lane:

* the committed file contains NO admitted row, so a model cannot promote its
  own suggestion into an authoritative link;
* the reader refuses to resolve anything that is not ``reviewed_admitted`` and
  returns unavailable WITH A REASON instead of a guess;
* ambiguity is queued with its competing candidates recorded, never picked; and
* the effective interval is mandatory, so a rename or ticker reuse opens a new
  interval instead of rewriting history.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from engine.biocatalyst.sponsor_identity import (
    BASKET_MEMBERSHIP_PATH,
    CANDIDATE_ONLY_STATE,
    HEALTHCARE_BASKETS,
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
    admitted["confidence_class"] = "strong_candidate"
    admitted["provenance"]["kind"] = "human_reviewed_source"
    admitted["review"] = {
        "reviewed_by": "test reviewer",
        "reviewed_at": "2026-08-08T00:00:00Z",
        "review_reference": "hypothetical review, tests only",
    }
    return admitted


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


def test_committed_map_carries_no_admitted_row_so_a_model_cannot_self_promote(document: dict) -> None:
    # The lane's non-negotiable: a model suggests, a human admits.  If this
    # ever fails, an LLM-authored link has been given authority it never earned.
    assert document["state"] == CANDIDATE_ONLY_STATE
    assert document["review_policy"]["model_may_admit"] is False
    assert document["review_policy"]["admission_authority"] == "named_human_pull_request_review_only"
    assert document["review_policy"]["default_review_state"] == "candidate_unreviewed"
    assert list(document["review_policy"]["resolvable_review_states"]) == ["reviewed_admitted"]

    admitted = [row for row in document["rows"] if row["review_state"] == "reviewed_admitted"]
    assert admitted == [], f"{len(admitted)} row(s) self-promoted to reviewed_admitted"
    for row in document["rows"]:
        assert row["review_state"] in {"candidate_unreviewed", "ambiguous_queued"}
        assert row["provenance"]["kind"] == "model_suggested_candidate"
        assert row["review"] == {
            "reviewed_by": None,
            "reviewed_at": None,
            "review_reference": None,
        }


def test_every_committed_row_is_still_in_the_review_queue(document: dict) -> None:
    assert len(review_queue(document)) == len(document["rows"])
    assert document["rows"], "the map must actually carry candidates to review"


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
        if row["review_state"] == "candidate_unreviewed":
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
# The reader refuses everything that has not been reviewed
# --------------------------------------------------------------------------


def test_reader_refuses_every_committed_row_and_never_returns_a_ticker(document: dict) -> None:
    assert RESOLVABLE_REVIEW_STATES == frozenset({"reviewed_admitted"})
    for row in document["rows"]:
        resolution = resolve_sponsor(row["sponsor_name"], as_of=AS_OF, document=document)
        assert resolution.status == "unavailable"
        assert resolution.available is False
        assert resolution.ticker is None
        expected = (
            UNAVAILABLE_AWAITING_REVIEW
            if row["review_state"] == "candidate_unreviewed"
            else UNAVAILABLE_AMBIGUOUS
        )
        assert resolution.reason == expected


def test_a_candidate_unreviewed_row_does_not_resolve_but_its_admitted_twin_does(document: dict) -> None:
    candidate = next(row for row in document["rows"] if row["review_state"] == "candidate_unreviewed")
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
        "subsidiary_of_listed_issuer",
        "renamed_entity",
        "multiple_matching_issuers",
        "issuer_outside_declared_universe",
    } <= reasons
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
    forged = copy.deepcopy(document)
    row = next(row for row in forged["rows"] if row["review_state"] == "candidate_unreviewed")
    row["review"]["reviewed_by"] = "a model, which is not a reviewer"
    _expect_issue(forged, "sponsor_map.unreviewed_review_block")


def test_a_candidate_only_map_may_not_contain_an_admitted_row(document: dict) -> None:
    candidate = next(row for row in document["rows"] if row["review_state"] == "candidate_unreviewed")
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
    candidate = next(row for row in document["rows"] if row["review_state"] == "candidate_unreviewed")
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
    candidate = next(row for row in document["rows"] if row["review_state"] == "candidate_unreviewed")
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
    candidate = next(row for row in document["rows"] if row["review_state"] == "candidate_unreviewed")
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
