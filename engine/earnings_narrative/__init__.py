"""Deterministic, receipt-backed earnings narrative evidence.

This package intentionally contains no inference client or provider adapter.
It turns the Terminal's immutable transcript body contract into bounded,
context-only facts and claims that can be verified without a model.
"""

from .contracts import (  # noqa: F401
    AUTHORITY,
    CLAIM_GRAPH_SCHEMA,
    FACT_PACK_SCHEMA,
    MANIFEST_SCHEMA,
    ContractError,
)
