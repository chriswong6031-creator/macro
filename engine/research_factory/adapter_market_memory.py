"""Pure Market Memory to Research Factory candidate-conformance adapter.

W6A converts one exact, owner-valid W2A trial-registration byte string into a
canonical ``research_factory.candidate.v1`` proposal. It does not read or write
files, register a trial family, execute retrieval, evaluate an experiment,
challenge a candidate, or advance any lifecycle. W4 retrieval and W5 evaluation
remain explicit deferred/null joins. Every authority, emission, training,
promotion, and action bit remains false.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn

from engine.neuralweb import market_memory_forward
from engine.research_factory import schema as research_factory_schema

MARKET_MEMORY_CANDIDATE_SOURCE = "market_memory"
MARKET_MEMORY_CANDIDATE_TYPE = "market_memory_candidate"
MARKET_MEMORY_CANDIDATE_DOMAIN = "market_memory"
MARKET_MEMORY_SPEC_SCHEMA = "research_factory.market_memory_candidate_spec.v1"
MARKET_MEMORY_CONFORMANCE_SCHEMA = (
    "research_factory.market_memory_candidate_conformance.v1"
)

_CREATED_AT = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_SPEC_ID = re.compile(r"mmrfspec_[a-f0-9]{64}\Z")
_CANDIDATE_ID = re.compile(r"rf-market-memory-[a-f0-9]{64}\Z")
_MAX_CANDIDATE_BYTES = 256 * 1024
_CANDIDATE_FIELDS = frozenset(
    {
        "schema",
        "authority",
        "candidate_id",
        "created_at",
        "source",
        "candidate_type",
        "domain",
        "status",
        "hypothesis",
        "mechanism",
        "claim_shape",
        "spec_ref",
        "expected_failure_modes",
        "decay_conditions",
        "falsifiers",
        "trial_accounting",
        "evaluation_plan",
        "lineage",
        "flags",
        "artifacts",
        "transition_log",
    }
)
_ACTION_AUTHORITY = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "may_trade": False,
    "may_originate": False,
    "may_select_options_candidate": False,
    "may_execute": False,
    "may_write_options_episode": False,
    "may_append_outcome": False,
    "may_train_prophet": False,
}


class MarketMemoryResearchFactoryContractError(ValueError):
    """A W6A candidate or its exact W2A source bytes are non-conforming."""


def _fail(message: str) -> NoReturn:
    raise MarketMemoryResearchFactoryContractError(message)


def _canonical_bytes(value: object) -> bytes:
    try:
        body = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise MarketMemoryResearchFactoryContractError(
            "Market Memory candidate is not finite canonical JSON"
        ) from exc
    if not body or len(body) > _MAX_CANDIDATE_BYTES:
        _fail("Market Memory candidate exceeds its canonical byte bound")
    return body


def _detached(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_canonical_bytes(dict(value)))


def _content_id(prefix: str, value: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_bytes(dict(value))).hexdigest()


def _exact_created_at(value: object, *, registered_at: str) -> str:
    if type(value) is not str or not _CREATED_AT.fullmatch(value):
        _fail("created_at must be exact microsecond RFC3339 UTC")
    try:
        created = datetime.fromisoformat(value.replace("Z", "+00:00"))
        registered = datetime.fromisoformat(registered_at.replace("Z", "+00:00"))
    except (
        ValueError
    ) as exc:  # pragma: no cover - owner already validates registered_at
        raise MarketMemoryResearchFactoryContractError(
            "created_at is not a real timestamp"
        ) from exc
    if created.utcoffset() != timedelta(0):  # pragma: no cover - regex fixes UTC
        _fail("created_at must be UTC")
    if created.astimezone(timezone.utc) < registered.astimezone(timezone.utc):
        _fail("candidate cannot be created before its W2A preregistration")
    return value


def _load_trial(exact_trial_registration_bytes: bytes) -> dict[str, Any]:
    try:
        trial = market_memory_forward.load_trial_registration_json(
            exact_trial_registration_bytes
        )
    except market_memory_forward.MarketMemoryForwardContractError as exc:
        raise MarketMemoryResearchFactoryContractError(
            "exact W2A trial registration failed its owner contract"
        ) from exc
    if (
        market_memory_forward.canonical_json_bytes(trial)
        != exact_trial_registration_bytes
    ):
        _fail("W2A trial registration bytes are not exact canonical owner bytes")
    return trial


def _trial_read_back(trial: Mapping[str, Any]) -> dict[str, Any]:
    """Read back the leakage, budget, and implementation controls verbatim."""

    return {
        "purge": copy.deepcopy(trial["purge"]),
        "embargo": copy.deepcopy(trial["embargo"]),
        "trial_budget": copy.deepcopy(trial["trial_budget"]),
        "implementation": copy.deepcopy(trial["implementation"]),
    }


def _candidate_payload(
    *, trial: Mapping[str, Any], exact_trial_registration_bytes: bytes, created_at: str
) -> dict[str, Any]:
    trial_sha256 = hashlib.sha256(exact_trial_registration_bytes).hexdigest()
    read_back = _trial_read_back(trial)
    spec = {
        "schema": MARKET_MEMORY_SPEC_SCHEMA,
        "trial_registration_id": trial["trial_registration_id"],
        "trial_registration_sha256": trial_sha256,
        "trial_registration_bytes": len(exact_trial_registration_bytes),
        "trial_read_back": read_back,
        "w4_retrieval_join": {
            "status": "deferred",
            "episode_set_id": None,
            "evidence_ref": None,
        },
        "w5_evaluation_join": {
            "status": "not_run",
            "evaluation_id": None,
            "evidence_ref": None,
        },
    }
    spec_ref = _content_id("mmrfspec_", spec)
    conformance = {
        "schema": MARKET_MEMORY_CONFORMANCE_SCHEMA,
        "spec": spec,
        "authority_granted": False,
        "challenge_completed": False,
        "challenge_ref": None,
        "emission_enabled": False,
        "training_eligible": False,
        "promotion_eligible": False,
        "action_authority": dict(_ACTION_AUTHORITY),
    }
    trial_key = trial["trial_key"]
    payload: dict[str, Any] = {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "candidate_id": "",
        "created_at": created_at,
        "source": MARKET_MEMORY_CANDIDATE_SOURCE,
        "candidate_type": MARKET_MEMORY_CANDIDATE_TYPE,
        "domain": MARKET_MEMORY_CANDIDATE_DOMAIN,
        "status": "proposed",
        "hypothesis": (
            f"Conformance candidate for frozen Market Memory trial {trial_key}; "
            "no retrieval or evaluation result is claimed."
        ),
        "mechanism": (
            "Read-only pointer to an exact W2A preregistration; W4 retrieval and "
            "W5 evaluation evidence are deferred."
        ),
        "claim_shape": None,
        "spec_ref": spec_ref,
        "expected_failure_modes": [
            "w4_retrieval_not_available",
            "w5_evaluation_not_run",
        ],
        "decay_conditions": [],
        "falsifiers": [],
        "trial_accounting": {
            "mode": "read_only",
            "family": None,
            "declared_at": None,
        },
        "evaluation_plan": {
            "status": "not_run",
            "primary_metric": None,
            "horizon_d": None,
            "min_n": None,
            "fdr_scope": None,
            "expected_half_life_d": None,
            "defaulted": False,
            "source": "market_memory_w2a_preregistration",
        },
        "lineage": {
            "respin_of": None,
            "superseded_by": None,
            "refinement_generation": 0,
        },
        "flags": [
            "market_memory_context_only",
            "w4_join_deferred",
            "w5_join_deferred",
        ],
        "artifacts": {"market_memory_conformance": conformance},
        "transition_log": [],
    }
    semantic = copy.deepcopy(payload)
    semantic.pop("candidate_id")
    semantic.pop("created_at")
    payload["candidate_id"] = _content_id("rf-market-memory-", semantic)
    return payload


def _validate_exact_candidate(
    value: Mapping[str, Any], *, exact_trial_registration_bytes: bytes
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _CANDIDATE_FIELDS:
        _fail("Market Memory candidate fields are not canonical")
    candidate_id = value.get("candidate_id")
    if type(candidate_id) is not str or not _CANDIDATE_ID.fullmatch(candidate_id):
        _fail("Market Memory candidate_id is malformed")
    spec_ref = value.get("spec_ref")
    if type(spec_ref) is not str or not _SPEC_ID.fullmatch(spec_ref):
        _fail("Market Memory spec_ref is malformed")
    trial = _load_trial(exact_trial_registration_bytes)
    created_at = _exact_created_at(
        value.get("created_at"), registered_at=trial["registered_at"]
    )
    expected = _candidate_payload(
        trial=trial,
        exact_trial_registration_bytes=exact_trial_registration_bytes,
        created_at=created_at,
    )
    if _canonical_bytes(value) != _canonical_bytes(expected):
        _fail("Market Memory candidate differs from its exact canonical projection")
    violations = research_factory_schema.validate_candidate(expected)
    if violations:
        _fail("Market Memory candidate fails canonical Research Factory validation")
    return _detached(expected)


def build_market_memory_candidate(
    *, exact_trial_registration_bytes: bytes, created_at: str
) -> dict[str, Any]:
    """Build one proposed, zero-authority canonical RF candidate."""

    trial = _load_trial(exact_trial_registration_bytes)
    clean_created_at = _exact_created_at(
        created_at, registered_at=trial["registered_at"]
    )
    candidate = _candidate_payload(
        trial=trial,
        exact_trial_registration_bytes=exact_trial_registration_bytes,
        created_at=clean_created_at,
    )
    return _validate_exact_candidate(
        candidate, exact_trial_registration_bytes=exact_trial_registration_bytes
    )


def validate_market_memory_candidate(
    value: Mapping[str, Any], *, exact_trial_registration_bytes: bytes
) -> dict[str, Any]:
    """Validate one candidate against the exact W2A bytes it claims to bind."""

    return _validate_exact_candidate(
        value, exact_trial_registration_bytes=exact_trial_registration_bytes
    )


__all__ = [
    "MARKET_MEMORY_CANDIDATE_DOMAIN",
    "MARKET_MEMORY_CANDIDATE_SOURCE",
    "MARKET_MEMORY_CANDIDATE_TYPE",
    "MARKET_MEMORY_CONFORMANCE_SCHEMA",
    "MARKET_MEMORY_SPEC_SCHEMA",
    "MarketMemoryResearchFactoryContractError",
    "build_market_memory_candidate",
    "validate_market_memory_candidate",
]
