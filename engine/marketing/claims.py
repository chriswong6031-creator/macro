"""engine.marketing.claims — ClaimPassport dataclass + proof-graph helpers.

Every meaningful public claim becomes a durable internal object.
Pure in-memory — no I/O, no LLM calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ClaimPassport:
    claim_id: str
    exact_claim: str
    claim_type: str                     # factual | directional | causal | promotional
    authoring_system: str
    evidence_refs: list[str] = field(default_factory=list)
    counterevidence_refs: list[str] = field(default_factory=list)
    scope: str = ""
    horizon: str = ""
    jurisdiction: str = "global"
    audience: str = ""
    disclosure_class: str = "market_education"
    confidence_method: str = "editorial"
    falsifier: str = ""
    check_by: str | None = None
    outcome_refs: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    derivative_asset_ids: list[str] = field(default_factory=list)
    status: str = "open"               # open | resolved | corrected | expired
    mode: str = "live"

    def as_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "exact_claim": self.exact_claim,
            "claim_type": self.claim_type,
            "authoring_system": self.authoring_system,
            "evidence_refs": list(self.evidence_refs),
            "counterevidence_refs": list(self.counterevidence_refs),
            "scope": self.scope,
            "horizon": self.horizon,
            "jurisdiction": self.jurisdiction,
            "audience": self.audience,
            "disclosure_class": self.disclosure_class,
            "confidence_method": self.confidence_method,
            "falsifier": self.falsifier,
            "check_by": self.check_by,
            "outcome_refs": list(self.outcome_refs),
            "corrections": list(self.corrections),
            "derivative_asset_ids": list(self.derivative_asset_ids),
            "status": self.status,
            "mode": self.mode,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Proof-graph helpers
# ─────────────────────────────────────────────────────────────────────────────

def link_derivative(claim: ClaimPassport, asset_id: str) -> None:
    """Add asset_id to claim.derivative_asset_ids if not already present."""
    if asset_id not in claim.derivative_asset_ids:
        claim.derivative_asset_ids.append(asset_id)


def add_correction(claim: ClaimPassport, correction_id: str) -> None:
    """Record a correction id on the claim and flip status to corrected."""
    if correction_id not in claim.corrections:
        claim.corrections.append(correction_id)
    claim.status = "corrected"


# ─────────────────────────────────────────────────────────────────────────────
# Summarize
# ─────────────────────────────────────────────────────────────────────────────

def summarize(claims: list[dict[str, Any]]) -> dict[str, int]:
    """Return {total, open, resolved} from a list of claim dicts."""
    total = len(claims)
    open_ = sum(1 for c in claims if c.get("status") == "open")
    resolved = sum(1 for c in claims if c.get("status") in ("resolved", "corrected", "expired"))
    return {"total": total, "open": open_, "resolved": resolved}
