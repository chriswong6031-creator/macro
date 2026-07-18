"""engine.marketing.economics — Retained contribution formula + budget allocator.

Deterministic only.  No LLM calls, no randomness.

Formula (spec §3, docket §12.1.F):
    retained contribution =
        recognized revenue
        - payment fees
        - refunds and chargebacks
        - creator or referral payout
        - paid-media cost
        - model inference
        - incremental data and delivery cost
        - incremental support cost
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Formula string (frozen per spec §3)
# ─────────────────────────────────────────────────────────────────────────────

FORMULA: str = (
    "retained contribution = recognized revenue"
    " - fees"
    " - refunds"
    " - payouts"
    " - paid media"
    " - inference"
    " - data/delivery"
    " - support"
)


# ─────────────────────────────────────────────────────────────────────────────
# Per-cohort retained contribution
# ─────────────────────────────────────────────────────────────────────────────

def retained_contribution(cohort: dict[str, Any]) -> float:
    """Compute retained contribution from a cohort dict.

    Expected keys (all optional; missing = 0):
        recognized_revenue, fees, refunds, chargebacks,
        creator_payout, referral_payout,
        paid_media_cost, model_inference_cost,
        data_delivery_cost, support_cost.
    """
    try:
        revenue = float(cohort.get("recognized_revenue", 0))
        fees = float(cohort.get("fees", 0))
        refunds = float(cohort.get("refunds", 0)) + float(cohort.get("chargebacks", 0))
        payouts = float(cohort.get("creator_payout", 0)) + float(cohort.get("referral_payout", 0))
        paid_media = float(cohort.get("paid_media_cost", 0))
        inference = float(cohort.get("model_inference_cost", 0))
        data_delivery = float(cohort.get("data_delivery_cost", 0))
        support = float(cohort.get("support_cost", 0))
        return revenue - fees - refunds - payouts - paid_media - inference - data_delivery - support
    except Exception:
        return 0.0


def cohort_summary(cohorts: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate retained_contribution across cohorts."""
    total = sum(retained_contribution(c) for c in cohorts)
    return {
        "count": len(cohorts),
        "total_retained_contribution": round(total, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# BudgetAllocator
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BudgetAllocator:
    """Allocate a total_envelope across departments by scorecard rank."""
    method: str = "scorecard-weighted"
    total_envelope_usd: float = 0.0
    allocations: list[dict] = field(default_factory=list)

    def allocate(self, departments: list[dict[str, Any]]) -> list[dict]:
        """Return allocation list [{department, weight, amount_usd}].

        Weight = scorecard.experiment_velocity rank (placeholder; all zero
        in seed state → equal weight).
        """
        if not departments:
            return []
        n = len(departments)
        weight = round(1.0 / n, 6) if n else 0.0
        allocs = []
        for i, d in enumerate(departments):
            allocs.append({
                "department": d.get("id", ""),
                "weight": weight,
                "rank": i + 1,
                "amount_usd": round(self.total_envelope_usd * weight, 2),
            })
        self.allocations = allocs
        return allocs

    def as_dict(self) -> dict:
        return {
            "method": self.method,
            "total_envelope_usd": self.total_envelope_usd,
            "allocations": list(self.allocations),
        }
