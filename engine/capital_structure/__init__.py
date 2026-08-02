"""Capital Structure Intelligence truth-plane primitives.

Wave 0-2A exposes immutable source-event observations plus a public-safe
observed-filing-state projection. It does not normalize instrument terms,
calculate numerical issuer state, fetch source material, or grant trading
authority.
"""

from .event_spine import (
    CLASSIFICATION_STATES,
    DEFERRED_AMBIGUOUS_CONTENT,
    DEFERRED_CONFLICT,
    DEFERRED_LINKAGE,
    DEFERRED_MISSING_DOCUMENT,
    DEFERRED_UNSUPPORTED_MEDIA,
    PARSER_VERSION,
    append_event_versions_strict,
    build_event_version,
    build_review_queue,
    current_events_as_of,
    event_classification,
    evidence_from_span,
    link_registration_graph,
    make_stable_span,
    route_form,
)
from .projection import (
    PROJECTION_BUNDLE_SCHEMA,
    PROJECTION_SCHEMA,
    PROJECTION_VERSION,
    build_projection_bundle,
    validate_projection_bundle,
)
from .document_terms import (
    DOCUMENT_TERM_SCHEMA,
    PARSER_VERSION as DOCUMENT_TERM_PARSER_VERSION,
    DocumentTermCompileDegraded,
    compile_document_term_records,
    current_document_terms_as_of,
    validate_observation_source_binding,
    validate_document_term_history,
)

__all__ = [
    "CLASSIFICATION_STATES",
    "DOCUMENT_TERM_PARSER_VERSION",
    "DOCUMENT_TERM_SCHEMA",
    "DEFERRED_AMBIGUOUS_CONTENT",
    "DEFERRED_CONFLICT",
    "DEFERRED_LINKAGE",
    "DEFERRED_MISSING_DOCUMENT",
    "DEFERRED_UNSUPPORTED_MEDIA",
    "DocumentTermCompileDegraded",
    "PARSER_VERSION",
    "PROJECTION_BUNDLE_SCHEMA",
    "PROJECTION_SCHEMA",
    "PROJECTION_VERSION",
    "append_event_versions_strict",
    "build_event_version",
    "compile_document_term_records",
    "build_review_queue",
    "build_projection_bundle",
    "current_events_as_of",
    "current_document_terms_as_of",
    "event_classification",
    "evidence_from_span",
    "link_registration_graph",
    "make_stable_span",
    "route_form",
    "validate_projection_bundle",
    "validate_observation_source_binding",
    "validate_document_term_history",
]
