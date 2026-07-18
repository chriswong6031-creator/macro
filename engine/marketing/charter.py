"""engine.marketing.charter — CMO mandate constants + lobe charter text.

The positioning constants are sourced from config/marketing.yml at runtime
(see state.py).  The defaults here are the frozen seed values from the spec §5
and strategy doctrine (Fable 2026-07-18).
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Category and promise (frozen defaults; overridden by config/marketing.yml)
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY: str = "Accountable AI market intelligence"

PROMISE: str = "Know what changed, why it matters, and what to watch next."

PROOF: str = (
    "Every important conclusion carries evidence, invalidation, "
    "timestamp, and outcome history."
)

ICP: str = (
    "Self-directed, research-intensive swing/position investors "
    "following 10–100 names."
)

FIRST_PAID_JOB: str = (
    "Continuously monitor what matters to my holdings/watchlist "
    "and tell me when the causal picture changes."
)

# ─────────────────────────────────────────────────────────────────────────────
# Lobe charter text
# ─────────────────────────────────────────────────────────────────────────────

LOBE_NAME: str = "Marketing"
LOBE_ID: str = "marketing"

CHARTER_SUMMARY: str = (
    "Sovereign business-growth lobe. Owns category positioning, "
    "department lifecycle, growth authority, campaign pipeline, "
    "distribution network, lifecycle/conversion, creator/partner "
    "infrastructure, growth science, and independent audit. "
    "Connects to Neural Web as an evidence consumer and bridge, "
    "not as a scored-path participant. "
    "Display-tier; originates no market signal."
)

CHARTER_MANDATE: str = (
    "Maximize durable contribution profit and strategic distribution power. "
    "Guerrilla before paid, value before ask, proof before promise, "
    "a governed footprint before a large one. "
    "Build the Growth OS substrate before scaling any channel."
)

# ─────────────────────────────────────────────────────────────────────────────
# Mandate dict (used by state.py)
# ─────────────────────────────────────────────────────────────────────────────

def mandate(cfg: dict | None = None) -> dict:
    """Return the CMO mandate dict, overriding from cfg if provided."""
    positioning = (cfg or {}).get("positioning", {})
    return {
        "category": positioning.get("category", CATEGORY),
        "promise": positioning.get("promise", PROMISE),
        "proof": positioning.get("proof", PROOF),
        "icp": positioning.get("icp", ICP),
        "first_paid_job": positioning.get("first_paid_job", FIRST_PAID_JOB),
    }
