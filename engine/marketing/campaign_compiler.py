"""engine.marketing.campaign_compiler — Campaign compilation + distinctness check.

Pure functions.  No I/O, no LLM calls, no randomness.

One opportunity → per-channel / per-account variant plan.
Distinctness = token-Jaccard over variant text; flags any pair above 0.7.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Campaign:
    campaign_id: str
    opportunity_id: str
    objective: str
    audience: str
    promise: str
    proof: str
    destination_product: str
    offer: str
    channels: list[str]
    asset_plan: list[dict]
    experiment_id: str | None
    budget_envelope: dict
    authority_level: str
    start_at: str | None
    stop_at: str | None
    rollback: str
    owner_department: str
    mode: str = "shadow"

    def as_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "opportunity_id": self.opportunity_id,
            "objective": self.objective,
            "audience": self.audience,
            "promise": self.promise,
            "proof": self.proof,
            "destination_product": self.destination_product,
            "offer": self.offer,
            "channels": list(self.channels),
            "asset_plan": list(self.asset_plan),
            "experiment_id": self.experiment_id,
            "budget_envelope": dict(self.budget_envelope),
            "authority_level": self.authority_level,
            "start_at": self.start_at,
            "stop_at": self.stop_at,
            "rollback": self.rollback,
            "owner_department": self.owner_department,
            "mode": self.mode,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Distinctness
# ─────────────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> frozenset[str]:
    """Lower-case word token set from text."""
    return frozenset(text.lower().split())


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def distinctness(variants: list[str]) -> dict[str, Any]:
    """Compute cross-variant similarity.

    Returns:
        {"max_similarity": float, "flags": int, "flagged_pairs": list}

    A pair is flagged when Jaccard > 0.7.
    """
    if len(variants) < 2:
        return {"max_similarity": 0.0, "flags": 0, "flagged_pairs": []}

    tokens = [_tokenize(v) for v in variants]
    max_sim = 0.0
    flags = 0
    flagged_pairs: list[tuple[int, int, float]] = []

    for i in range(len(tokens)):
        for j in range(i + 1, len(tokens)):
            sim = _jaccard(tokens[i], tokens[j])
            if sim > max_sim:
                max_sim = sim
            if sim > 0.7:
                flags += 1
                flagged_pairs.append((i, j, round(sim, 4)))

    return {
        "max_similarity": round(max_sim, 4),
        "flags": flags,
        "flagged_pairs": flagged_pairs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Compile
# ─────────────────────────────────────────────────────────────────────────────

def compile(
    opportunity: dict[str, Any],
    accounts: list[dict[str, Any]],
) -> Campaign:
    """Produce a Campaign from an opportunity dict + account list.

    Each account in accounts produces one asset_plan entry with a distinct
    variant promise tailored to that account's corpus and beat.

    Pure function — never raises, returns shadow-mode Campaign on error.
    """
    try:
        opp_id = opportunity.get("opportunity_id", "unknown")
        campaign_id = f"cmp-{opp_id}"

        channels = list({
            acct.get("kind", "generic"): acct.get("id")
            for acct in accounts
        }.values())

        # Build per-account asset variants
        asset_plan: list[dict] = []
        for acct in accounts:
            beat = acct.get("beat", "")
            promise = opportunity.get("problem_or_desire", "")
            # Tailor the promise to the account's beat (deterministic transformation)
            variant = f"[{acct.get('id','?')}] {beat}: {promise}"
            asset_plan.append({
                "account_id": acct.get("id"),
                "kind": acct.get("kind"),
                "variant_promise": variant,
                "corpus": acct.get("corpus", "full"),
                "status": "draft",
            })

        return Campaign(
            campaign_id=campaign_id,
            opportunity_id=opp_id,
            objective=opportunity.get("problem_or_desire", ""),
            audience=opportunity.get("audience_hypothesis", ""),
            promise=opportunity.get("problem_or_desire", ""),
            proof=str(opportunity.get("evidence_available", False)),
            destination_product="What Changed",
            offer="free_public_value",
            channels=channels,
            asset_plan=asset_plan,
            experiment_id=None,
            budget_envelope={"total_usd": 0, "spent_usd": 0},
            authority_level=opportunity.get("consequence_class", "G1"),
            start_at=None,
            stop_at=None,
            rollback="unpublish_via_takedown_method",
            owner_department=opportunity.get("owner_department", "studio"),
            mode="shadow",
        )
    except Exception:
        return Campaign(
            campaign_id="cmp-error",
            opportunity_id="",
            objective="",
            audience="",
            promise="",
            proof="",
            destination_product="",
            offer="",
            channels=[],
            asset_plan=[],
            experiment_id=None,
            budget_envelope={"total_usd": 0, "spent_usd": 0},
            authority_level="G1",
            start_at=None,
            stop_at=None,
            rollback="",
            owner_department="studio",
            mode="shadow",
        )
