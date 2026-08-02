from __future__ import annotations

from copy import deepcopy

import pytest

from engine.earnings_narrative.contracts import ContractError
from engine.earnings_narrative.digest import build_event_digest
from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.promotion import (
    build_promoted_story,
    build_promotion_decision,
    load_promotion_policy,
    validate_promotion_decision,
    validate_promotion_policy,
)
from engine.earnings_transcript_intake import canonical_body_sha256


def _body(*, sparse: bool = False) -> dict:
    segments = [
        {
            "speaker": "Chief Executive Officer",
            "role": "executive",
            "text": "Revenue grew 12% to 120 million, while gross margin reached 45%.",
        },
        {
            "speaker": "Chief Financial Officer",
            "role": "executive",
            "text": "For the full year, we expect revenue of 500 million and an operating margin of 20%.",
        },
        {
            "speaker": "Chief Executive Officer",
            "role": "executive",
            "text": "We will invest 50 million in capacity and continue our share repurchase program.",
        },
        {
            "speaker": "Research Analyst",
            "role": "analyst",
            "text": "Can you discuss customer demand and the 10% slowdown in Europe?",
        },
    ]
    if sparse:
        segments = [{
            "speaker": "Chief Executive Officer",
            "role": "executive",
            "text": "Revenue was 100 million.",
        }]
    return {
        "schema": "mastermind.tx/v1",
        "ticker": "AAPL",
        "id": "2026Q1",
        "period": "Q1 FY2026",
        "date": "2026-01-30",
        "title": "AAPL earnings call",
        "segments": segments,
    }


def _digest_for_body(body: dict) -> dict:
    body_sha = canonical_body_sha256(body)
    index = {
        "schema": "mastermind.tx-index/v1",
        "generated_at": "2026-02-01T00:00:00Z",
        "symbols": {"AAPL": ["2026Q1"]},
        "revisions": {"AAPL/2026Q1": body_sha},
        "dates": {"AAPL/2026Q1": "2026-01-30"},
        "body_count": 1,
        "symbol_count": 1,
    }
    fact_pack, claim_graph = build_evidence_pair(
        body,
        index_payload=index,
        indexed_body_sha256=body_sha,
        index_generated_at=index["generated_at"],
    )
    return build_event_digest(fact_pack, claim_graph, body)


def _digest(*, sparse: bool = False) -> dict:
    return _digest_for_body(_body(sparse=sparse))


def test_transcript_policy_replays_without_recursion_and_promotes_only_to_b() -> None:
    policy = load_promotion_policy()
    digest = _digest()
    decision = build_promotion_decision(digest, policy=policy)
    assert decision["tier"] == "B"
    assert decision["article_eligible"] is True
    assert "tier_a_transcript_only_blocked" in decision["reasons"]
    assert decision["metrics"]["numeric_receipt_count"] >= 3
    # This is deliberately a replay call.  It used to recurse through the
    # constructor; it must now compare one deterministic reconstruction.
    validate_promotion_decision(decision, digest=digest, policy=policy)
    decision_again = build_promotion_decision(digest, policy=policy)
    assert decision_again == decision

    replayed, story = build_promoted_story(digest, policy=policy)
    assert replayed == decision
    assert story["promotion"]["tier"] == "B"
    assert story["promotion"]["decision_source"] == "governed_triage"


def test_tier_c_is_the_deterministic_shortfall_and_tier_a_is_structurally_impossible() -> None:
    decision = build_promotion_decision(_digest(sparse=True), policy=load_promotion_policy())
    assert decision["tier"] == "C"
    assert decision["article_eligible"] is False
    assert "tier_a_transcript_only_blocked" in decision["reasons"]
    assert "tier_b_numeric_receipts_below_floor" in decision["reasons"]
    assert "tier_b_substantive_categories_below_floor" in decision["reasons"]

    invalid = deepcopy(load_promotion_policy())
    invalid["tiers"]["A"]["enabled"] = True
    with pytest.raises(ContractError, match="Tier A must be disabled"):
        validate_promotion_policy(invalid)


def test_analyst_questions_cannot_promote_as_issuer_management_facts() -> None:
    body = _body()
    body["segments"] = [{
        "speaker": "Research Analyst",
        "role": "analyst",
        "text": (
            "Can you discuss revenue of 500 million, 20% margin, 12% demand growth, "
            "50 million of capex, full-year guidance of 600 million, and the 10% risk?"
        ),
    }]
    decision = build_promotion_decision(_digest_for_body(body), policy=load_promotion_policy())
    assert decision["tier"] == "C"
    assert decision["metrics"]["management_fact_count"] == 0
    assert decision["metrics"]["numeric_receipt_count"] == 0
    assert "tier_b_management_facts_below_floor" in decision["reasons"]
