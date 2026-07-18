"""engine.marketing — Marketing lobe: sovereign business-growth lobe.

Display-tier, off the scored path.  Deterministic Growth-OS substrate:
CMO portfolio, 10 department scorecards, growth-authority ladder, desk network,
campaign/opportunity/publication/experiment pipeline, provenance & claims,
economics, and wave status.

Public entry point
------------------
    from engine.marketing import build_state
    state = build_state(root=None, cfg=None)

Never-raise contract: build_state() returns best-effort dict on any error.
"""
from __future__ import annotations

from engine.marketing.state import build_state  # noqa: F401

__all__ = ["build_state"]
