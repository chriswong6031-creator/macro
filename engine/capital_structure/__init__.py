"""Capital Structure Intelligence truth-plane primitives.

Wave 1 deliberately exposes only immutable source-event observations.  It does
not normalize instrument terms, calculate issuer state, fetch source material,
or grant trading authority.
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

__all__ = [
    "CLASSIFICATION_STATES",
    "DEFERRED_AMBIGUOUS_CONTENT",
    "DEFERRED_CONFLICT",
    "DEFERRED_LINKAGE",
    "DEFERRED_MISSING_DOCUMENT",
    "DEFERRED_UNSUPPORTED_MEDIA",
    "PARSER_VERSION",
    "append_event_versions_strict",
    "build_event_version",
    "build_review_queue",
    "current_events_as_of",
    "event_classification",
    "evidence_from_span",
    "link_registration_graph",
    "make_stable_span",
    "route_form",
]
