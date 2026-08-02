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
from .digest import DIGEST_SCHEMA, build_event_digest, validate_event_digest  # noqa: F401
from .story import (  # noqa: F401
    STORY_SCHEMA,
    article_receipt_floor,
    article_receipt_value,
    build_canonical_story,
    validate_canonical_story,
    validate_correction_against_prior,
)
from .promotion import (  # noqa: F401
    PROMOTION_DECISION_SCHEMA,
    PROMOTION_POLICY_SCHEMA,
    build_promoted_story,
    build_promotion_decision,
    load_promotion_policy,
    promotion_policy_sha256,
    validate_promotion_decision,
    validate_promotion_policy,
)
from .story_packets import (  # noqa: F401
    STORY_PACKET_MANIFEST_SCHEMA,
    STORY_PACKET_SCHEMA,
    build_story_packet,
    validate_story_packet,
    validate_story_packet_manifest,
)
