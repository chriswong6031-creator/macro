"""engine.marketing.authority — Growth authority ladder G0..G7.

Independent from Neural Web's analytical authority ladder.
Pure predicates over dicts — no I/O, no side-effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Enum
# ─────────────────────────────────────────────────────────────────────────────

class GrowthAuthority(Enum):
    """G0..G7 growth authority levels (docket §9.1)."""

    G0 = 0
    G1 = 1
    G2 = 2
    G3 = 3
    G4 = 4
    G5 = 5
    G6 = 6
    G7 = 7

    @property
    def level(self) -> int:
        return self.value

    @property
    def label(self) -> str:
        _labels = {
            "G0": "Observe",
            "G1": "Create",
            "G2": "Shadow",
            "G3": "Publish",
            "G4": "Engage",
            "G5": "Allocate",
            "G6": "Organize",
            "G7": "Root",
        }
        return _labels[self.name]

    @property
    def desc(self) -> str:
        _descs = {
            "G0": (
                "Read and diagnose — crawl site, inspect funnels, "
                "monitor trends."
            ),
            "G1": (
                "Create drafts and prototypes — copy, scripts, "
                "landing pages, mock reports."
            ),
            "G2": (
                "Run against live inputs without external effect — "
                "simulated campaign, private preview, dry-run partner research."
            ),
            "G3": (
                "Publish through owned, approved lanes — site, "
                "newsletter, established social formats."
            ),
            "G4": (
                "Interact and transact inside standard terms — "
                "replies, partner provisioning, affiliate offers."
            ),
            "G5": (
                "Move spend and resources inside caps — "
                "paid tests, creator economics, model budgets."
            ),
            "G6": (
                "Create/merge/retire departments and rewrite playbooks — "
                "new regional desk, channel closure, model change."
            ),
            "G7": (
                "Change legal-entity commitments or root credentials — "
                "bank, binding signature, registration, identity proof."
            ),
        }
        return _descs[self.name]


# ─────────────────────────────────────────────────────────────────────────────
# Ladder list (serializable)
# ─────────────────────────────────────────────────────────────────────────────

LADDER: list[dict] = [
    {"level": ga.name, "name": ga.label, "desc": ga.desc}
    for ga in GrowthAuthority
]


# ─────────────────────────────────────────────────────────────────────────────
# Pure predicate helpers
# ─────────────────────────────────────────────────────────────────────────────

def can_earn(record: dict[str, Any]) -> bool:
    """Return True if the record has satisfied the authority-earn prerequisites.

    Prerequisites (all from docket §9.2):
    - passed_shadow: bool
    - clean_receipts: bool
    - within_cost_cap: bool
    - positive_incremental_impact: bool
    - no_unresolved_corrections: bool
    - survived_red_team: bool
    - reliable_rollback: bool

    Any missing key is treated as False (conservative default).
    """
    required = (
        "passed_shadow",
        "clean_receipts",
        "within_cost_cap",
        "positive_incremental_impact",
        "no_unresolved_corrections",
        "survived_red_team",
        "reliable_rollback",
    )
    return all(record.get(k, False) for k in required)


def should_narrow(signals: dict[str, Any]) -> bool:
    """Return True if autonomy should automatically narrow per §9.2 rules.

    Narrowing triggers (any True → narrow):
    - freshness_degraded
    - platform_warnings_increased
    - complaint_rate_elevated
    - correction_rate_elevated
    - low_retention_channel
    - exceeded_cost_cap
    - auditor_cannot_reproduce
    """
    triggers = (
        "freshness_degraded",
        "platform_warnings_increased",
        "complaint_rate_elevated",
        "correction_rate_elevated",
        "low_retention_channel",
        "exceeded_cost_cap",
        "auditor_cannot_reproduce",
    )
    return any(signals.get(k, False) for k in triggers)
