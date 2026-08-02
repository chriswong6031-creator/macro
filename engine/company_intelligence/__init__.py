"""Deterministic, context-only Company Intelligence publication helpers.

This package projects existing earnings-call records into a transport-safe
per-company view.  It deliberately has no signal, ranking, or LLM authority.
"""

from .contracts import (
    CONTEXT_SCHEMA,
    MANIFEST_SCHEMA,
    ContractError,
    canonical_json_bytes,
    safe_ticker,
    stable_event_id,
)
from .health import build_health, enforce_shrink_floor, validate_generation
from .views import build_bundle, build_company_contexts, write_generation

__all__ = [
    "CONTEXT_SCHEMA",
    "MANIFEST_SCHEMA",
    "ContractError",
    "build_bundle",
    "build_company_contexts",
    "build_health",
    "canonical_json_bytes",
    "enforce_shrink_floor",
    "safe_ticker",
    "stable_event_id",
    "validate_generation",
    "write_generation",
]
