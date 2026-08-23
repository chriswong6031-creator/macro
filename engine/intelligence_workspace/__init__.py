"""Typed, read-only field addressability over canonical Macro data owners.

This package owns neither source facts nor a value store.  It validates the
frozen W1-A catalog and deterministically wraps owner-returned facts.
"""

from .contracts import (
    AdapterResult,
    CanonicalEntity,
    EntityRequest,
    OwnerResolutionRequest,
    ResolutionRequest,
)
from .registry import DatapointRegistry, FieldSpec, load_registry
from .resolver import DatapointResolver, RequestValidationError

__all__ = [
    "AdapterResult",
    "CanonicalEntity",
    "DatapointRegistry",
    "DatapointResolver",
    "EntityRequest",
    "FieldSpec",
    "OwnerResolutionRequest",
    "RequestValidationError",
    "ResolutionRequest",
    "load_registry",
]
