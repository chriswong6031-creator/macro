"""engine.marketing.opportunity_bus — Opportunity scoring.

Pure functions — no I/O, no side-effects, no randomness.
Score = expected_value × originality × freshness_decay(half_life_class).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Half-life classes (docket §13.9)
# ─────────────────────────────────────────────────────────────────────────────

_HALF_LIFE_HOURS: dict[str, float] = {
    "breaking_event": 2.0,     # minutes to hours → 2h
    "earnings_follow_up": 24.0,
    "weekly_signal": 7 * 24.0,
    "evergreen_comparison": 90 * 24.0,
    "category_positioning": 365 * 24.0,
}

_DEFAULT_HALF_LIFE_HOURS: float = 7 * 24.0


def half_life_class(source_type: str) -> str:
    """Map source_type string to a half-life class name."""
    _map = {
        "breaking_event": "breaking_event",
        "market_event": "breaking_event",
        "earnings": "earnings_follow_up",
        "earnings_follow_up": "earnings_follow_up",
        "weekly_signal": "weekly_signal",
        "weekly": "weekly_signal",
        "evergreen": "evergreen_comparison",
        "evergreen_comparison": "evergreen_comparison",
        "seo": "evergreen_comparison",
        "positioning": "category_positioning",
        "category": "category_positioning",
    }
    return _map.get(source_type, "weekly_signal")


def _freshness_decay(hlc: str, age_hours: float) -> float:
    """Exponential decay: value remaining = 0.5 ^ (age / half_life)."""
    hl = _HALF_LIFE_HOURS.get(hlc, _DEFAULT_HALF_LIFE_HOURS)
    if hl <= 0:
        return 0.0
    return math.pow(0.5, age_hours / hl)


# ─────────────────────────────────────────────────────────────────────────────
# Dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Opportunity:
    opportunity_id: str
    detected_at: str                   # ISO-8601 UTC
    source_type: str
    source_refs: list[str] = field(default_factory=list)
    audience_hypothesis: str = ""
    problem_or_desire: str = ""
    attention_half_life: str = "weekly_signal"
    expected_value: float = 0.0        # 0.0–1.0 expected retained contribution proxy
    originality: float = 1.0           # 0.0–1.0; 1 = fully original
    evidence_available: bool = False
    possible_products: list[str] = field(default_factory=list)
    possible_channels: list[str] = field(default_factory=list)
    consequence_class: str = "market_education"
    owner_department: str = "intelligence"
    status: str = "open"
    mode: str = "live"


# ─────────────────────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────────────────────

def score(opp: Opportunity, now: datetime | None = None) -> float:
    """Score = expected_value × originality × freshness_decay(half_life_class).

    Returns float in [0, 1].  Clamps all inputs; never raises.
    """
    try:
        ev = max(0.0, min(1.0, float(opp.expected_value)))
        orig = max(0.0, min(1.0, float(opp.originality)))
        hlc = half_life_class(opp.source_type)

        # Compute age from detected_at
        _now = now or datetime.now(timezone.utc)
        try:
            det = datetime.fromisoformat(opp.detected_at.replace("Z", "+00:00"))
            age_h = (_now - det).total_seconds() / 3600.0
        except Exception:
            age_h = 0.0

        decay = _freshness_decay(hlc, max(0.0, age_h))
        return round(ev * orig * decay, 6)
    except Exception:
        return 0.0


def score_dict(opp_dict: dict[str, Any], now: datetime | None = None) -> float:
    """Convenience: score from a plain dict (e.g. from JSONL ledger)."""
    try:
        opp = Opportunity(
            opportunity_id=opp_dict.get("opportunity_id", ""),
            detected_at=opp_dict.get("detected_at", ""),
            source_type=opp_dict.get("source_type", "weekly_signal"),
            expected_value=float(opp_dict.get("expected_value", 0.0)),
            originality=float(opp_dict.get("originality", 1.0)),
            problem_or_desire=opp_dict.get("problem_or_desire", ""),
            status=opp_dict.get("status", "open"),
        )
        return score(opp, now=now)
    except Exception:
        return 0.0
