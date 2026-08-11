"""Pure, inert W7 audit proving that no Market Memory feature can promote.

This module projects the frozen canonical feature registry into one negative
evidence artifact. It does not read evidence, write state, evaluate a feature,
register a feature, make a promotion decision, or connect to any runtime. The
v1 grammar can express only failed or not-run gates and zero authority.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn

from engine.neuralweb.market_memory import (
    CANONICAL_FEATURE_REGISTRY,
    FEATURE_REGISTRY_VERSION,
)
from engine.neuralweb.market_memory_forward import AUTHORITY

FEATURE_PROMOTION_AUDIT_SCHEMA = "market_memory.feature_promotion_audit.v1"

_AUDIT_ID = re.compile(r"mmpromotionaudit_[a-f0-9]{64}\Z")
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_MAX_JSON_BYTES = 256 * 1024
_MAX_JSON_DEPTH = 16
_MAX_JSON_NODES = 4096
_EVIDENCE_CHECKPOINT_DATE = "2026-08-11"

_CANONICAL_FEATURE_IDS = tuple(sorted(CANONICAL_FEATURE_REGISTRY))
_MACRO_FEATURE_ID = "macro.regime_state"
_GATE_IDS = (
    "g0_temporal_data_integrity",
    "g1_reproducibility",
    "g2_conceptual_soundness",
    "g3_predictive_validity",
    "g4_leakage_selection_control",
    "g5_robustness_incremental_value",
    "g6_shadow_forward",
    "g7_bounded_feature_promotion",
)
_ABSENT_EVIDENCE = (
    "operational_forward_n",
    "calibration_evidence",
    "clustered_dependence_intervals",
    "incremental_value_after_prophet",
    "shadow_forward_evidence",
)
_EXCLUDED_CONSTRUCTS = (
    "action_authority",
    "feature_pass_state",
    "promotion_eligibility",
    "promotion_decision",
    "runtime_integration",
    "synapse_registration",
    "training_consumption",
)
_PRIVATE_LIMITATIONS = (
    {
        "lane": "private_technical_ratio",
        "status": "insufficient",
        "finding": (
            "price.raw_close_ratio_20_sessions is an unadjusted current-tip ratio, "
            "not canonical price.ret_20d or historical operational evidence"
        ),
    },
    {
        "lane": "private_breadth",
        "status": "insufficient",
        "finding": (
            "current-tip breadth is degraded partial coverage with current-membership "
            "survivor bias and no repaired operational history"
        ),
    },
    {
        "lane": "private_option_oi",
        "status": "insufficient",
        "finding": (
            "one bounded first page proves source availability only, not a complete "
            "dated or atomic options open-interest state"
        ),
    },
)
_WAVE_EVIDENCE = (
    {"wave": "W2", "status": "synthetic_only"},
    {"wave": "W4", "status": "synthetic_only"},
    {"wave": "W5", "status": "not_shipped"},
    {"wave": "W6", "status": "not_shipped"},
)
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "audit_id",
        "audited_at",
        "feature_registry_version",
        "features",
        "counts",
        "private_limitations",
        "wave_evidence",
        "absent_evidence",
        "excluded_constructs",
        "authority_granted",
        "authority",
    }
)


class MarketMemoryPromotionAuditContractError(ValueError):
    """A W7 no-promotion audit is malformed or exceeds its authority."""


def _fail(message: str) -> NoReturn:
    raise MarketMemoryPromotionAuditContractError(message)


def canonical_json_bytes(value: object) -> bytes:
    """Return the one finite canonical JSON representation admitted by W7."""

    try:
        body = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise MarketMemoryPromotionAuditContractError(
            "feature-promotion audit is not finite canonical JSON"
        ) from exc
    if not body or len(body) > _MAX_JSON_BYTES:
        _fail("feature-promotion audit exceeds its canonical byte bound")
    return body


def _detached(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(canonical_json_bytes(dict(value)))


def _exact_timestamp(value: object) -> str:
    if type(value) is not str or not _TIMESTAMP.fullmatch(value):
        _fail("audited_at must be exact microsecond RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketMemoryPromotionAuditContractError(
            "audited_at is not a real timestamp"
        ) from exc
    if parsed.utcoffset() != timedelta(0):  # pragma: no cover - regex fixes UTC
        _fail("audited_at must be UTC")
    if not 1970 <= parsed.astimezone(timezone.utc).year <= 2100:
        _fail("audited_at year is outside the bounded audit window")
    if parsed.date().isoformat() != _EVIDENCE_CHECKPOINT_DATE:
        _fail("audited_at must remain on the frozen 2026-08-11 evidence checkpoint")
    return value


def _walk_json(value: object, *, depth: int = 0) -> int:
    if depth > _MAX_JSON_DEPTH:
        _fail("feature-promotion audit exceeds its JSON depth bound")
    nodes = 1
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                _fail("feature-promotion audit object keys must be strings")
            nodes += _walk_json(child, depth=depth + 1)
    elif type(value) is list:
        for child in value:
            nodes += _walk_json(child, depth=depth + 1)
    if nodes > _MAX_JSON_NODES:
        _fail("feature-promotion audit exceeds its JSON node bound")
    return nodes


def _feature_row(feature_id: str) -> dict[str, Any]:
    spec = CANONICAL_FEATURE_REGISTRY[feature_id]
    is_macro = feature_id == _MACRO_FEATURE_ID
    gates = [
        {
            "gate_id": gate_id,
            "status": "failed" if index == 0 else "not_run",
        }
        for index, gate_id in enumerate(_GATE_IDS)
    ]
    return {
        "feature_id": feature_id,
        "domain": spec.domain,
        "registry_state": "current_degraded" if is_macro else "missing",
        "blocking_reason": (
            "component_receipts_unauthenticated" if is_macro else "feature_missing"
        ),
        "gates": gates,
        "eligible": False,
        "promoted": False,
        "authority_granted": False,
    }


def _payload(*, audited_at: str) -> dict[str, Any]:
    if len(_CANONICAL_FEATURE_IDS) != 18:
        _fail("canonical feature registry is not the frozen 18-feature v1")
    features = [_feature_row(feature_id) for feature_id in _CANONICAL_FEATURE_IDS]
    payload: dict[str, Any] = {
        "schema": FEATURE_PROMOTION_AUDIT_SCHEMA,
        "audit_id": "",
        "audited_at": audited_at,
        "feature_registry_version": FEATURE_REGISTRY_VERSION,
        "features": features,
        "counts": {
            "feature_count": 18,
            "missing_count": 17,
            "current_degraded_count": 1,
            "failed_gate_count": 18,
            "not_run_gate_count": 126,
            "eligible_count": 0,
            "promoted_count": 0,
        },
        "private_limitations": copy.deepcopy(list(_PRIVATE_LIMITATIONS)),
        "wave_evidence": copy.deepcopy(list(_WAVE_EVIDENCE)),
        "absent_evidence": list(_ABSENT_EVIDENCE),
        "excluded_constructs": list(_EXCLUDED_CONSTRUCTS),
        "authority_granted": False,
        "authority": copy.deepcopy(dict(AUTHORITY)),
    }
    semantic = copy.deepcopy(payload)
    semantic.pop("audit_id")
    payload["audit_id"] = (
        "mmpromotionaudit_" + hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    )
    return payload


def validate_feature_promotion_audit(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one exact negative W7 artifact and return a detached copy."""

    if type(value) is not dict or set(value) != _TOP_LEVEL_FIELDS:
        _fail("feature-promotion audit fields are not canonical")
    _walk_json(value)
    audit_id = value.get("audit_id")
    if type(audit_id) is not str or not _AUDIT_ID.fullmatch(audit_id):
        _fail("feature-promotion audit_id is malformed")
    audited_at = _exact_timestamp(value.get("audited_at"))
    expected = _payload(audited_at=audited_at)
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        _fail("feature-promotion audit differs from the frozen negative projection")
    return _detached(expected)


def build_feature_promotion_audit(*, audited_at: str) -> dict[str, Any]:
    """Build all 18 failed/not-run feature rows without promotion authority."""

    clean_time = _exact_timestamp(audited_at)
    return validate_feature_promotion_audit(_payload(audited_at=clean_time))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            _fail("feature-promotion audit JSON contains duplicate object keys")
        value[key] = child
    return value


def load_feature_promotion_audit_json(raw: bytes) -> dict[str, Any]:
    """Load exact canonical bytes with duplicate, depth, node, and size bounds."""

    if type(raw) is not bytes:
        _fail("feature-promotion audit JSON must be exact bytes")
    if not raw or len(raw) > _MAX_JSON_BYTES:
        _fail("feature-promotion audit JSON exceeds its input byte bound")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except MarketMemoryPromotionAuditContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MarketMemoryPromotionAuditContractError(
            "feature-promotion audit JSON is malformed"
        ) from exc
    if type(value) is not dict:
        _fail("feature-promotion audit JSON root must be an object")
    _walk_json(value)
    if canonical_json_bytes(value) != raw:
        _fail("feature-promotion audit JSON is not exact canonical bytes")
    return validate_feature_promotion_audit(value)


__all__ = [
    "FEATURE_PROMOTION_AUDIT_SCHEMA",
    "MarketMemoryPromotionAuditContractError",
    "build_feature_promotion_audit",
    "canonical_json_bytes",
    "load_feature_promotion_audit_json",
    "validate_feature_promotion_audit",
]
