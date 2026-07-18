"""engine.marketing.provenance — Provenance modes + SourcePacket.

Three modes (docket §10.3):
- neural_web: faithfully packages a governed output from the signal bus.
- marketing_original: Marketing lobe performed the research / formed the view.
- hybrid: Neural Web evidence combined with Marketing research or editorial judgment.

Provenance is for learning and reuse — not a permission gate on editorial content.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

MODES: tuple[str, ...] = ("neural_web", "marketing_original", "hybrid")


# ─────────────────────────────────────────────────────────────────────────────
# Dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SourcePacket:
    packet_id: str
    provenance_mode: str                   # one of MODES
    source_artifact_refs: list[str] = field(default_factory=list)
    created_by: str = ""
    created_at: str = ""
    as_of: str = ""
    freshness: str = "fresh"               # fresh | stale | expired
    evidence_class: str = "general_research"
    claims: list[str] = field(default_factory=list)
    counter_case: str = ""
    falsifier: str = ""
    horizon: str = ""
    allowed_attributions: list[str] = field(default_factory=list)
    public_rights: str = "mastermind_brand"
    sensitive_fields: list[str] = field(default_factory=list)
    expiry: str | None = None
    correction_parent: str | None = None

    def as_dict(self) -> dict:
        return {
            "packet_id": self.packet_id,
            "provenance_mode": self.provenance_mode,
            "source_artifact_refs": list(self.source_artifact_refs),
            "created_by": self.created_by,
            "created_at": self.created_at,
            "as_of": self.as_of,
            "freshness": self.freshness,
            "evidence_class": self.evidence_class,
            "claims": list(self.claims),
            "counter_case": self.counter_case,
            "falsifier": self.falsifier,
            "horizon": self.horizon,
            "allowed_attributions": list(self.allowed_attributions),
            "public_rights": self.public_rights,
            "sensitive_fields": list(self.sensitive_fields),
            "expiry": self.expiry,
            "correction_parent": self.correction_parent,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Validator
# ─────────────────────────────────────────────────────────────────────────────

def validate(packet: SourcePacket) -> list[str]:
    """Return a list of validation problems.  Empty = valid."""
    problems: list[str] = []
    if packet.provenance_mode not in MODES:
        problems.append(
            f"provenance_mode {packet.provenance_mode!r} not in {MODES}"
        )
    if not packet.packet_id:
        problems.append("packet_id is empty")
    if not packet.created_at:
        problems.append("created_at is empty")
    return problems
