"""engine.marketing.cmo — Self-improving CMO logic.

Pure functions over dicts — no I/O, no LLM calls, no randomness.

Entry points:
    portfolio(departments) -> dict
    department_formation_gate(queue) -> dict
    improvement_loop_state(...) -> dict
    self_deception_checks() -> list[{name, status, note}]
    org_simulator(scenario) -> dict
"""
from __future__ import annotations

from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Self-deception checks (docket §16.4 / strategy §7.5)
# ─────────────────────────────────────────────────────────────────────────────

_DECEPTION_CHECKS: list[dict[str, str]] = [
    {
        "name": "no_training_on_unverified_attribution",
        "desc": (
            "The lobe does not train on its own unverified attribution as truth. "
            "Only holdout-validated incrementality results may update the model."
        ),
        "status": "enforced",
        "note": "Growth Science department owns attribution; publishing depts are consumers only.",
    },
    {
        "name": "no_delete_losing_cells",
        "desc": (
            "Losing experiment cells are never deleted. "
            "Append-only ledgers are the enforcement mechanism."
        ),
        "status": "enforced",
        "note": "All ledgers are JSONL append-only; the auditor samples for deletions.",
    },
    {
        "name": "no_relabel_failed_metric_as_success",
        "desc": (
            "A failed primary metric cannot be relabeled as a success after the fact. "
            "Pre-registered primary metric stays fixed for the experiment lifecycle."
        ),
        "status": "enforced",
        "note": "Experiment registry records hypothesis+primary_metric before any result is written.",
    },
    {
        "name": "no_self_grading_by_publishing_dept",
        "desc": (
            "A publishing department may not grade its own work alone. "
            "Attribution and scoring live in Growth Science."
        ),
        "status": "enforced",
        "note": "Scorecard writes are gated to growth_science and office_cmo departments.",
    },
    {
        "name": "no_engagement_as_revenue_proxy",
        "desc": (
            "Engagement (likes, views, clicks) may not claim revenue impact "
            "without holdout-validated evidence."
        ),
        "status": "enforced",
        "note": "Incrementality holdout required before any engagement metric enters budget allocation.",
    },
    {
        "name": "no_creator_payout_ignoring_refunds",
        "desc": (
            "Creator/referral conversions include payout, refund, and chargeback costs "
            "in retained_contribution before credit is assigned."
        ),
        "status": "enforced",
        "note": "Economics formula always subtracts payouts and refunds before attribution.",
    },
    {
        "name": "no_marketing_response_changes_market_scores",
        "desc": (
            "Marketing response (clicks, subs, revenue) cannot change a "
            "Neural Web market-engine score or signal."
        ),
        "status": "enforced",
        "note": "Typed boundary between marketing control plane and scored-path surfaces.",
    },
    {
        "name": "no_authority_widening_on_anomalous_win",
        "desc": (
            "Authority is not widened based on a single anomalous win. "
            "Minimum sample size and holdout validation are required."
        ),
        "status": "enforced",
        "note": "Authority ladder gates: passed_shadow + clean_receipts + no_unresolved_corrections + survived_red_team.",
    },
]


def self_deception_checks() -> list[dict[str, str]]:
    """Return the list of self-deception guardrails."""
    return [dict(c) for c in _DECEPTION_CHECKS]


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio
# ─────────────────────────────────────────────────────────────────────────────

def portfolio(departments: list[dict[str, Any]]) -> dict[str, Any]:
    """Build CMO portfolio view: allocations ranked by scorecard experiment_velocity."""
    if not departments:
        return {"allocations": [], "total_envelope_usd": 0}

    # Rank by experiment_velocity descending (seed: all 0 → stable-sort by id)
    ranked = sorted(
        departments,
        key=lambda d: (
            -d.get("scorecard", {}).get("experiment_velocity", 0),
            d.get("id", ""),
        ),
    )
    n = len(ranked)
    total = sum(d.get("budget", {}).get("envelope_usd", 0) for d in ranked)
    weight = round(1.0 / n, 6) if n else 0.0

    allocations = [
        {"department": d.get("id", ""), "weight": weight, "rank": i + 1}
        for i, d in enumerate(ranked)
    ]
    return {"allocations": allocations, "total_envelope_usd": total}


# ─────────────────────────────────────────────────────────────────────────────
# Department formation gate
# ─────────────────────────────────────────────────────────────────────────────

def department_formation_gate(queue: list[dict[str, Any]]) -> dict[str, Any]:
    """Check whether items in queue satisfy the formation prerequisites.

    Prerequisites (docket §6.3 / §7.3):
    - distinct_objective: bool
    - no_existing_dept_can_absorb: bool
    - positive_expected_option_value: bool
    - no_unresolved_conflict: bool
    - has_budget_assigned: bool
    - has_retirement_test: bool

    Returns {"approved": [...], "rejected": [...], "pending": [...]}.
    """
    approved, rejected, pending = [], [], []
    required_keys = (
        "distinct_objective",
        "no_existing_dept_can_absorb",
        "positive_expected_option_value",
        "no_unresolved_conflict",
        "has_budget_assigned",
        "has_retirement_test",
    )
    for item in queue:
        missing = [k for k in required_keys if k not in item]
        if missing:
            pending.append({"id": item.get("id", ""), "missing": missing})
        elif all(item.get(k, False) for k in required_keys):
            approved.append(item.get("id", ""))
        else:
            failed = [k for k in required_keys if not item.get(k, False)]
            rejected.append({"id": item.get("id", ""), "failed": failed})
    return {"approved": approved, "rejected": rejected, "pending": pending}


# ─────────────────────────────────────────────────────────────────────────────
# Improvement loop state
# ─────────────────────────────────────────────────────────────────────────────

def improvement_loop_state(
    loop_state: str = "observing",
    open_hypotheses: list[dict] | None = None,
    last_review: str | None = None,
    next_review: str = "2026-07-25",
) -> dict[str, Any]:
    """Return the CMO self-improvement loop state dict."""
    return {
        "loop_state": loop_state,
        "open_hypotheses": open_hypotheses or [],
        "last_review": last_review,
        "next_review": next_review,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Org simulator (deterministic what-if)
# ─────────────────────────────────────────────────────────────────────────────

def org_simulator(scenario: dict[str, Any]) -> dict[str, Any]:
    """Deterministic what-if simulation.

    Inputs:
        scenario: dict with optional keys:
            - add_department: {id, budget_usd}
            - retire_department: id
            - change_authority: {id, new_level}
            - scale_budget: {id, multiplier}

    Returns a summary of projected changes.  Never modifies actual state.
    """
    changes: list[dict] = []
    if "add_department" in scenario:
        d = scenario["add_department"]
        changes.append({
            "action": "add_department",
            "id": d.get("id", ""),
            "projected_budget_usd": d.get("budget_usd", 0),
            "note": "chartered shadow mode; no external effect until G3",
        })
    if "retire_department" in scenario:
        changes.append({
            "action": "retire_department",
            "id": scenario["retire_department"],
            "note": "ledger preserved; budget reallocated to CMO office",
        })
    if "change_authority" in scenario:
        c = scenario["change_authority"]
        changes.append({
            "action": "change_authority",
            "id": c.get("id", ""),
            "new_level": c.get("new_level", "G1"),
            "note": "requires auditor review if upgrading past G3",
        })
    if "scale_budget" in scenario:
        s = scenario["scale_budget"]
        changes.append({
            "action": "scale_budget",
            "id": s.get("id", ""),
            "multiplier": s.get("multiplier", 1.0),
            "note": "requires mature cohort evidence for >2x scaling",
        })
    if not changes:
        changes.append({"action": "no_op", "note": "no scenario parameters provided"})
    return {"scenario": scenario, "projected_changes": changes}
