"""engine.marketing.experiments — Experiment dataclass + trial variant constants.

The three trial variants are experimentable (docket §14.1 / spec §45).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

TRIAL_VARIANTS: list[str] = [
    "7_trading_days",
    "14_calendar_days",
    "value_moment_limited",
]


# ─────────────────────────────────────────────────────────────────────────────
# Dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Experiment:
    experiment_id: str
    hypothesis: str
    unit: str                          # visitor | cohort | account | geo
    holdout: float                     # 0.0–1.0 fraction
    primary_metric: str
    guardrails: list[str] = field(default_factory=list)
    start_at: str | None = None
    stop_at: str | None = None
    result: dict | None = None
    status: str = "planned"            # planned | running | completed | killed
    trial_variant: str | None = None
    mode: str = "shadow"

    def as_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "hypothesis": self.hypothesis,
            "unit": self.unit,
            "holdout": self.holdout,
            "primary_metric": self.primary_metric,
            "guardrails": list(self.guardrails),
            "start_at": self.start_at,
            "stop_at": self.stop_at,
            "result": self.result,
            "status": self.status,
            "trial_variant": self.trial_variant,
            "mode": self.mode,
        }
