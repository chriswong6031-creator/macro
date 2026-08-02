"""Closed, deterministic routing for transcript-backed earnings stories.

This module is intentionally less clever than it looks.  It turns an already
verified event digest into a *distribution tier*, never a security view, score,
recommendation, market-reaction interpretation, or theme/trading input.  A
Tier B result is merely eligible to enter the existing cited-brief staging rail.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from .contracts import AUTHORITY, EXECUTION_RECEIPT, ContractError, canonical_json_bytes, canonical_json_sha256, event_key
from .digest import DIGEST_SCHEMA, validate_event_digest
from .story import article_receipt_value, build_canonical_story, validate_canonical_story, validate_story_against_digest


PROMOTION_POLICY_SCHEMA = "earnings.story_promotion/v1"
PROMOTION_DECISION_SCHEMA = "earnings.story_promotion_decision/v1"

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = _ROOT / "config" / "earnings_story_promotion.yml"

_POLICY_KEYS = frozenset({"schema", "authority", "version", "decision_source", "source", "tiers", "forbidden_inputs"})
_SOURCE_KEYS = frozenset({"required_kind", "required_completeness"})
_COMPLETENESS_KEYS = frozenset({"release", "filing", "transcript", "slides", "consensus"})
_TIER_KEYS = frozenset({"A", "B", "C"})
_TIER_A_KEYS = frozenset({"enabled", "reason_code"})
_TIER_B_KEYS = frozenset({
    "enabled", "min_management_facts", "min_press_countable_numeric_receipts", "min_substantive_categories",
    "min_material_categories", "substantive_categories", "material_categories",
})
_TIER_C_KEYS = frozenset({"enabled", "reason_code"})
_DECISION_KEYS = frozenset({
    "schema", "authority", "event_key", "digest_id", "policy_schema", "policy_sha256",
    "tier", "article_eligible", "reasons", "metrics", "execution",
})
_METRIC_KEYS = frozenset({
    "management_fact_count", "numeric_receipt_count",
    "substantive_categories", "material_categories",
})

_REQUIRED_COMPLETENESS = {
    "release": "not_ingested",
    "filing": "not_ingested",
    "transcript": "present",
    "slides": "not_ingested",
    "consensus": "unlicensed_absent",
}
_FORBIDDEN_INPUTS = ["consensus", "market_data", "market_reaction", "theme_context", "trading_action"]


def _mapping(value: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    return value


def _keys(value: Mapping[str, Any], expected: frozenset[str], *, name: str) -> None:
    if set(value) != expected:
        raise ContractError(
            f"{name} fields mismatch (missing={sorted(expected - set(value))}, "
            f"unsupported={sorted(set(value) - expected)})"
        )


def _code(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 120 or any(char.isspace() for char in value):
        raise ContractError(f"{field} must be a stable non-space code")
    return value


def _nonnegative_int(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{field} invalid")
    return value


def _codes(value: object, *, field: str, allowed: set[str] | None = None) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{field} must be a list of codes")
    if value != sorted(set(value)):
        raise ContractError(f"{field} must be sorted and unique")
    if allowed is not None and not set(value) <= allowed:
        raise ContractError(f"{field} contains unsupported category")
    return list(value)


def validate_promotion_policy(payload: object) -> dict[str, Any]:
    """Validate the exact R2 transcript-only promotion law and return a copy."""
    row = _mapping(payload, name="earnings_story_promotion")
    _keys(row, _POLICY_KEYS, name="earnings_story_promotion")
    if row.get("schema") != PROMOTION_POLICY_SCHEMA or row.get("authority") != AUTHORITY:
        raise ContractError("earnings_story_promotion schema or authority mismatch")
    if row.get("version") != "1.0.0" or row.get("decision_source") != "governed_triage":
        raise ContractError("earnings_story_promotion version or decision source mismatch")

    source = _mapping(row.get("source"), name="earnings_story_promotion.source")
    _keys(source, _SOURCE_KEYS, name="earnings_story_promotion.source")
    if source.get("required_kind") != "transcript":
        raise ContractError("earnings_story_promotion requires transcript source")
    completeness = _mapping(source.get("required_completeness"), name="earnings_story_promotion.source.required_completeness")
    _keys(completeness, _COMPLETENESS_KEYS, name="earnings_story_promotion.source.required_completeness")
    if dict(completeness) != _REQUIRED_COMPLETENESS:
        raise ContractError("earnings_story_promotion source completeness must match transcript-only R2")

    tiers = _mapping(row.get("tiers"), name="earnings_story_promotion.tiers")
    _keys(tiers, _TIER_KEYS, name="earnings_story_promotion.tiers")
    tier_a = _mapping(tiers.get("A"), name="earnings_story_promotion.tiers.A")
    _keys(tier_a, _TIER_A_KEYS, name="earnings_story_promotion.tiers.A")
    if tier_a.get("enabled") is not False or _code(tier_a.get("reason_code"), field="tiers.A.reason_code") != "tier_a_transcript_only_blocked":
        raise ContractError("earnings_story_promotion Tier A must be disabled for transcript-only evidence")
    tier_b = _mapping(tiers.get("B"), name="earnings_story_promotion.tiers.B")
    _keys(tier_b, _TIER_B_KEYS, name="earnings_story_promotion.tiers.B")
    if tier_b.get("enabled") is not True:
        raise ContractError("earnings_story_promotion Tier B must be enabled")
    if _nonnegative_int(tier_b.get("min_management_facts"), field="tiers.B.min_management_facts", minimum=1) != 2:
        raise ContractError("earnings_story_promotion Tier B management fact floor is frozen at 2")
    if _nonnegative_int(tier_b.get("min_press_countable_numeric_receipts"), field="tiers.B.min_press_countable_numeric_receipts", minimum=1) != 3:
        raise ContractError("earnings_story_promotion Tier B numeric receipt floor is frozen at 3")
    if _nonnegative_int(tier_b.get("min_substantive_categories"), field="tiers.B.min_substantive_categories", minimum=1) != 2:
        raise ContractError("earnings_story_promotion Tier B substantive category floor is frozen at 2")
    if _nonnegative_int(tier_b.get("min_material_categories"), field="tiers.B.min_material_categories", minimum=1) != 1:
        raise ContractError("earnings_story_promotion Tier B material category floor is frozen at 1")
    known = {
        "guidance", "performance", "margins", "demand", "capital_allocation", "risks",
        "management_commitments", "segment_changes", "q_and_a",
    }
    substantive = _codes(tier_b.get("substantive_categories"), field="tiers.B.substantive_categories", allowed=known)
    material = _codes(tier_b.get("material_categories"), field="tiers.B.material_categories", allowed=known)
    if substantive != [
        "capital_allocation", "demand", "guidance", "management_commitments", "margins",
        "performance", "risks", "segment_changes",
    ]:
        raise ContractError("earnings_story_promotion Tier B substantive categories are frozen")
    if material != ["capital_allocation", "demand", "guidance", "margins", "performance", "risks"]:
        raise ContractError("earnings_story_promotion Tier B material categories are frozen")
    tier_c = _mapping(tiers.get("C"), name="earnings_story_promotion.tiers.C")
    _keys(tier_c, _TIER_C_KEYS, name="earnings_story_promotion.tiers.C")
    if tier_c.get("enabled") is not True or _code(tier_c.get("reason_code"), field="tiers.C.reason_code") != "tier_c_default_hold":
        raise ContractError("earnings_story_promotion Tier C must remain default hold")
    if _codes(row.get("forbidden_inputs"), field="earnings_story_promotion.forbidden_inputs") != _FORBIDDEN_INPUTS:
        raise ContractError("earnings_story_promotion forbidden input fence mismatch")
    return {str(key): value for key, value in row.items()}


def load_promotion_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    """Load a policy file only after its complete closed contract validates."""
    policy_path = Path(path)
    try:
        payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"cannot load earnings story promotion policy: {exc}") from exc
    return validate_promotion_policy(payload)


def promotion_policy_sha256(policy: object) -> str:
    """Content address the semantic policy document, never its YAML comments."""
    return canonical_json_sha256(validate_promotion_policy(policy))


def _promotion_metrics(digest: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    numeric_values: set[str] = set()
    present_categories: set[str] = set()
    management_fact_count = 0
    for fact in digest["facts"]:
        # Analyst questions are useful context in a dossier, but they are not
        # issuer claims and cannot promote or seed a Press article.  The digest
        # records management attribution as a deterministic selection receipt.
        if "management_role" not in fact["selection_reasons"]:
            continue
        management_fact_count += 1
        present_categories.update(str(category) for category in fact["categories"])
        for evidence in fact["evidence"]:
            if evidence["kind"] != "numeric":
                continue
            value = article_receipt_value(str(evidence["text"]))
            if value is not None:
                numeric_values.add(str(value))
    tier_b = policy["tiers"]["B"]
    substantive = sorted(present_categories & set(tier_b["substantive_categories"]))
    material = sorted(present_categories & set(tier_b["material_categories"]))
    return {
        "management_fact_count": management_fact_count,
        "numeric_receipt_count": len(numeric_values),
        "substantive_categories": substantive,
        "material_categories": material,
    }


def build_promotion_decision(digest: object, *, policy: object | None = None) -> dict[str, Any]:
    """Route one digest to deterministic Tier B or Tier C.

    Tier A is never considered in R2.  Reasons are stable machine codes, so a
    digest cannot smuggle free-form promotion language into a later story.
    """
    validate_event_digest(digest)
    assert isinstance(digest, Mapping)
    resolved_policy = load_promotion_policy() if policy is None else validate_promotion_policy(policy)
    if digest["schema"] != DIGEST_SCHEMA or digest["authority"] != AUTHORITY:
        raise ContractError("event digest schema or authority mismatch")
    if digest["source"].get("source_kind") != resolved_policy["source"]["required_kind"]:
        raise ContractError("event digest source kind cannot enter promotion")
    if dict(digest["source_completeness"]) != dict(resolved_policy["source"]["required_completeness"]):
        raise ContractError("event digest completeness cannot enter transcript-only promotion")
    # These fields are direct non-input proof rather than a best-effort policy
    # label.  A future join must use a new policy/schema.
    if digest["market_reaction"]["status"] != "not_joined" or digest["theme_context"]:
        raise ContractError("market or theme context is forbidden in earnings story promotion")

    metrics = _promotion_metrics(digest, resolved_policy)
    tier_b = resolved_policy["tiers"]["B"]
    reasons = [str(resolved_policy["tiers"]["A"]["reason_code"])]
    failures: list[str] = []
    if digest["quality"]["status"] != "ready" or digest["citation_coverage"] != 1.0:
        failures.append("tier_b_digest_not_ready")
    if metrics["management_fact_count"] < tier_b["min_management_facts"]:
        failures.append("tier_b_management_facts_below_floor")
    if metrics["numeric_receipt_count"] < tier_b["min_press_countable_numeric_receipts"]:
        failures.append("tier_b_numeric_receipts_below_floor")
    if len(metrics["substantive_categories"]) < tier_b["min_substantive_categories"]:
        failures.append("tier_b_substantive_categories_below_floor")
    if len(metrics["material_categories"]) < tier_b["min_material_categories"]:
        failures.append("tier_b_material_categories_below_floor")
    if failures:
        tier = "C"
        reasons.extend(failures)
        reasons.append(str(resolved_policy["tiers"]["C"]["reason_code"]))
    else:
        tier = "B"
        reasons.extend([
            "tier_b_digest_ready",
            "tier_b_management_facts_met",
            "tier_b_numeric_receipts_met",
            "tier_b_substantive_categories_met",
            "tier_b_material_categories_met",
        ])
    payload = {
        "schema": PROMOTION_DECISION_SCHEMA,
        "authority": AUTHORITY,
        "event_key": event_key(digest["event"]),
        "digest_id": str(digest["digest_id"]),
        "policy_schema": PROMOTION_POLICY_SCHEMA,
        "policy_sha256": promotion_policy_sha256(resolved_policy),
        "tier": tier,
        "article_eligible": tier == "B",
        "reasons": sorted(set(reasons)),
        "metrics": metrics,
        "execution": dict(EXECUTION_RECEIPT),
    }
    # Structural validation only here.  Passing ``digest`` would ask the
    # validator to rebuild this decision and recurse through this constructor.
    validate_promotion_decision(payload)
    return payload


def validate_promotion_decision(
    payload: object,
    *,
    digest: object | None = None,
    policy: object | None = None,
) -> None:
    """Verify a decision and, when supplied, replay it against exact inputs."""
    row = _mapping(payload, name="earnings_story_promotion_decision")
    _keys(row, _DECISION_KEYS, name="earnings_story_promotion_decision")
    if row.get("schema") != PROMOTION_DECISION_SCHEMA or row.get("authority") != AUTHORITY:
        raise ContractError("earnings_story_promotion_decision schema or authority mismatch")
    if not isinstance(row.get("event_key"), str) or "/" not in row["event_key"]:
        raise ContractError("earnings_story_promotion_decision event_key invalid")
    if not isinstance(row.get("digest_id"), str) or not row["digest_id"].startswith("digest_"):
        raise ContractError("earnings_story_promotion_decision digest_id invalid")
    if row.get("policy_schema") != PROMOTION_POLICY_SCHEMA or not isinstance(row.get("policy_sha256"), str) or len(row["policy_sha256"]) != 64:
        raise ContractError("earnings_story_promotion_decision policy receipt invalid")
    if row.get("tier") not in {"B", "C"} or row.get("article_eligible") is not (row["tier"] == "B"):
        raise ContractError("earnings_story_promotion_decision tier invalid")
    _codes(row.get("reasons"), field="earnings_story_promotion_decision.reasons")
    metrics = _mapping(row.get("metrics"), name="earnings_story_promotion_decision.metrics")
    _keys(metrics, _METRIC_KEYS, name="earnings_story_promotion_decision.metrics")
    _nonnegative_int(metrics.get("numeric_receipt_count"), field="earnings_story_promotion_decision.metrics.numeric_receipt_count")
    _nonnegative_int(metrics.get("management_fact_count"), field="earnings_story_promotion_decision.metrics.management_fact_count")
    for key in ("substantive_categories", "material_categories"):
        _codes(metrics.get(key), field=f"earnings_story_promotion_decision.metrics.{key}")
    if dict(row.get("execution") or {}) != EXECUTION_RECEIPT:
        raise ContractError("earnings_story_promotion_decision execution must remain token-free")
    if digest is not None:
        validate_event_digest(digest)
        assert isinstance(digest, Mapping)
        resolved_policy = load_promotion_policy() if policy is None else validate_promotion_policy(policy)
        expected = build_promotion_decision(digest, policy=resolved_policy)
        if canonical_json_bytes(row) != canonical_json_bytes(expected):
            raise ContractError("earnings_story_promotion_decision does not replay from digest and policy")


def build_promoted_story(
    digest: object,
    *,
    policy: object | None = None,
    prior_story: object | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile the closed canonical story using only a replayable decision."""
    decision = build_promotion_decision(digest, policy=policy)
    story = build_canonical_story(
        digest,
        tier=str(decision["tier"]),
        reasons=list(decision["reasons"]),
        decision_source="governed_triage",
        prior_story=prior_story,
    )
    validate_canonical_story(story)
    validate_story_against_digest(story, digest)
    if story["promotion"]["tier"] != decision["tier"] or story["promotion"]["reasons"] != decision["reasons"]:
        raise ContractError("canonical story promotion differs from deterministic decision")
    return decision, story
