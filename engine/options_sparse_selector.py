"""Prospective, host-private sparse exact-option selector runtime.

The executable rule was frozen by
``research/options_estate/sparse_selector_preregistration_receipt_v1.json``.
This module implements that rule without granting signal, issue, score, rank,
size, trade, publication, training, Prophet, Neural Web, or completion
authority.  ``propose`` means only a private research-review proposal.

The production registry remains deliberately unarmed in this change.  Tests
exercise the complete private planner/transaction harness directly; every
public planning and write entry point stays inert until a later reviewed code
change flips the constant after the deployment receipts exist.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import heapq
import json
import os
import re
import stat
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, NoReturn
from uuid import uuid4
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator, FormatChecker, ValidationError, validators

from engine import options_market_memory_context as context_bridge
from engine import options_market_memory_receipt_store as context_store
from engine import options_signal_campaign as campaign_contract
from engine import private_auth_dict
from lib import nyse_calendar
from scripts import build_options_sparse_selector_prereg as prereg
from scripts import build_prophet_marks as mark_chain
from scripts import build_prophet_option_shadow_lifecycle as lifecycle

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts/options/options.sparse_selector_runtime.v1.schema.json"

RULE_ID = "sparse_exact_option_truth_gate/v1"
BENCHMARK_DIGEST = "20e6c19f691cf9a07381288d6bdb33c6d74c8957b074ceefcdaf0ab8da1b1f42"
BENCHMARK_EFFECTIVE_FREEZE_AT = "2026-08-11T15:47:06Z"
SELECTOR_EFFECTIVE_FREEZE_AT = "2026-08-12T13:30:00Z"
SELECTOR_RULE_SHA256 = (
    "a98d3b92e1ebe069c141d5f79ee9260eeb2b8eeee4f90f574ef0069c062ad20b"
)
CANDIDATE_MANIFEST_RULE_SHA256 = (
    "70e1bec30bde9764a5e88dfec6aa01a654b9eece65ee3b7d20fa57e1c87444a6"
)
DECISION_RULE_SHA256 = (
    "734d742723f650a05b321131079c1329ff608e9e72bf5bcc1d1276b718fdc79c"
)
EVIDENCE_RULE_SHA256 = (
    "518ae9a36cf60e400933c07e46ce885955b720cc71c59a39e328800e86ac91af"
)
SOURCE_CAMPAIGN_RULE_SHA256 = (
    "6ff5cc16a74bf27807b3c8540b31794a6d9c54aec8fc152edc02602d646ad7f6"
)
LIFECYCLE_RULE_SHA256 = (
    "072aa402484eb920293e43fe0625bb694460381280bf439325786da2efab2eb4"
)

# Code-only arming.  No environment value, marker file, host config, first
# observation, or CLI argument may turn this on.
SELECTOR_RUNTIME_ARMED = False

CAMPAIGNS_PATH = "data/options_signal_campaign/campaigns.jsonl"
EPISODES_PATH = "data/options_signal_episode/episodes.jsonl"
CAMPAIGN_CHECKPOINT_PATH = "data/options_signal_campaign/checkpoint.json"
CAMPAIGN_CHECKPOINT_COMMIT = "481fecc70f299f3b480176b050b9dbae298a15c2"
HANDOFF_QUEUE_NAMESPACE = "handoff_queue"
SOURCE_PROJECTION_NAMESPACE = "source_projection"
CANDIDATE_INDEX_DOMAIN = "selector.candidates/v1"
SOURCE_CANDIDATE_INDEX_DOMAIN = "selector.source_candidates/v1"
SOURCE_CAMPAIGN_HISTORY_DOMAIN = "selector.source_campaign_history/v1"
SOURCE_EPISODE_IDENTITY_DOMAIN = "selector.source_episode_identity/v1"
SOURCE_EPISODE_GROUP_DOMAIN = "selector.source_episode_groups/v1"
HEAD_FILE = "HEAD.json"
INTENT_FILE = "ADVANCE_INTENT.json"
INTENT_ATTEMPT_FILE = "ADVANCE_INTENT.attempt.json"
INTENT_SEAL_NAMESPACE = "intent_seals"
LOCK_FILE = ".store.lock"
LEGACY_SELECTOR_FILES = (
    "decisions.jsonl",
    "candidates.jsonl",
    "cycles.jsonl",
    "manifests.jsonl",
    "handoff_queue.jsonl",
)

# A bounded queue walk protects one importer invocation, but the authenticated
# store itself has no lifetime row/cycle ceiling.  Evidence gates are allowed to
# accrue for as long as needed without a later code migration.
QUEUE_WALK_TEST_HORIZON = 9_828
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_OBJECT_BYTES = 16 * 1024 * 1024
MAX_HEAD_BYTES = 1 * 1024 * 1024
MAX_SOURCE_INTENT_BYTES = 4 * 1024 * 1024
MAX_INTENT_BYTES = 32 * 1024 * 1024
# Import work is bounded per invocation, not over the lifetime of the queue.
# One selector cycle is itself bounded by MAX_INTENT_BYTES, so a valid oldest
# cycle can always be consumed even after an arbitrarily long importer outage.
MAX_HANDOFF_IMPORT_RECORDS = 64
MAX_HANDOFF_IMPORT_BYTES = MAX_INTENT_BYTES
# This is a publication-segment size, not an eligibility or lifetime cap.  A
# receipted source cursor advances over every row and carries the remainder into
# later cycles until the audited Git blob is exhausted.
# A manifest must remain settleable in one bounded recovery intent even when
# every candidate carries three distinct evidence objects. 128 leaves room for
# the decision chain, next admission prefix, sharded index nodes, cycle, queue,
# and controls without weakening the lifetime/global ordering rule.
MAX_CANDIDATES_PER_MANIFEST = 128
# Evidence is optional truth input, never permission to consume the entire
# transaction. These per-component envelopes preserve ample room for normal
# validated upstream rows while reserving a strict worst-case settlement
# budget: 128 candidates * 3 * 4KiB plus decisions/controls stays below 4MiB.
MAX_EVIDENCE_OBJECT_BYTES = 4 * 1024
MAX_EVIDENCE_GENERATION_BYTES = 16 * 1024 * 1024
MAX_EVIDENCE_SNAPSHOT_BYTES = 32 * 1024 * 1024
MAX_EVIDENCE_SNAPSHOT_RECORDS = 16_384
MAX_W1A_HEAD_BYTES = 16 * 1024
MAX_W1A_AUDIT_BYTES = 64 * 1024
MAX_W1A_REFERENCE_SET_OBJECT_BYTES = 8 * 1024 * 1024 + 16 * 1024
MAX_W1A_SOURCE_RECEIPT_BYTES = 1 * 1024 * 1024
# Source projection work is segmented independently from candidate admission.
# This bounds a single scheduled transaction without imposing a lifetime/source
# ceiling or forcing the same immutable Git blobs to be rescanned.
MAX_SOURCE_ROWS_PER_CYCLE = 1_024
MAX_CAMPAIGN_SOURCE_ROWS_PER_CYCLE = 96
MAX_SOURCE_OBJECTS_PER_CYCLE = 1_024
MAX_RUN_ROWS = 4_096
MAX_RUN_BYTES = 4 * 1024 * 1024
MAX_RUN_MANIFESTS = 256
MAX_RUN_MANIFEST_BYTES = 32 * 1024 * 1024
MAX_MERGE_FAN_IN = 32
PROPOSAL_CAP = 3

ABSTENTION_REASON_CODES = tuple(prereg.ABSTENTION_REASON_CODES)
_REASON_ORDER = {
    reason: ordinal for ordinal, reason in enumerate(ABSTENTION_REASON_CODES)
}

FALSE_AUTHORITY: dict[str, bool] = {
    "may_claim_sparse_gate": False,
    "may_compute_option_pnl": False,
    "may_feed_neural_web": False,
    "may_issue": False,
    "may_originate_signal": False,
    "may_publish_pick": False,
    "may_rank": False,
    "may_score": False,
    "may_select": False,
    "may_size": False,
    "may_trade": False,
    "may_train_prophet": False,
}

DIGESTS: dict[str, str] = {
    "benchmark_digest_sha256": BENCHMARK_DIGEST,
    "selector_rule_sha256": SELECTOR_RULE_SHA256,
    "candidate_manifest_rule_sha256": CANDIDATE_MANIFEST_RULE_SHA256,
    "decision_rule_sha256": DECISION_RULE_SHA256,
    "evidence_rule_sha256": EVIDENCE_RULE_SHA256,
    "source_campaign_rule_sha256": SOURCE_CAMPAIGN_RULE_SHA256,
}

RUNTIME_OBJECT_SCHEMAS = frozenset(
    {
        "options.sparse_selector_candidate/v1",
        "options.sparse_selector_candidate_manifest/v1",
        "options.sparse_selector_decision/v1",
        "options.sparse_selector_cycle_receipt/v1",
        "options.sparse_selector_handoff_queue_item/v1",
        "options.sparse_selector_head/v1",
        "options.sparse_selector_w1a_source_receipt/v1",
        "options.sparse_selector_evidence_generation/v1",
        "options.sparse_selector_konseki_evidence/v1",
        "options.sparse_selector_mark_evidence/v1",
        "options.sparse_selector_lifecycle_evidence/v1",
    }
)

_SHA256_RE = re.compile(r"[a-f0-9]{64}\Z")
_COMMIT_RE = re.compile(r"[a-f0-9]{40,64}\Z")
_CAMPAIGN_ID_RE = re.compile(r"ocam_[a-f0-9]{24}\Z")
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
ET = ZoneInfo("America/New_York")

# ``jsonschema`` treats an unknown format as annotation-only.  That made
# ``date-time: nonsense`` pass when the optional format packages were absent
# from the sealed runtime.  Register the exact canonical-UTC grammar we use,
# backed only by the standard library, so schema behavior cannot change with
# the installed wheel set.
_FORMAT_CHECKER = FormatChecker()


@_FORMAT_CHECKER.checks("date-time", raises=(TypeError, ValueError))
def _is_rfc3339_datetime(value: object) -> bool:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        return False
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


@_FORMAT_CHECKER.checks("date", raises=(TypeError, ValueError))
def _is_rfc3339_date(value: object) -> bool:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        return False
    return date.fromisoformat(value).isoformat() == value


class SparseSelectorError(ValueError):
    """A source, private store, evidence object, or transition is unsafe."""


class SparseSelectorUnarmed(SparseSelectorError):
    """The executable runtime has not received its reviewed code-only arm."""


class EvidenceGenerationDrift(SparseSelectorError):
    """A mutable evidence head changed while an immutable snapshot was built."""


class _AdvanceBoundExceeded(SparseSelectorError):
    """A read-only admission attempt needs a smaller globally ordered prefix."""


def _fail(message: str) -> NoReturn:
    raise SparseSelectorError(message)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SparseSelectorError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def strict_json(raw: bytes | str, *, label: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                SparseSelectorError(f"non-standard JSON constant {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SparseSelectorError(f"{label} is not strict JSON") from exc


def canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise SparseSelectorError(
            "selector value is not finite canonical JSON"
        ) from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + _sha256(canonical_bytes(core))


def _handoff_queue_key(ordinal: int) -> str:
    if type(ordinal) is not int or ordinal < 1:
        _fail("selector handoff queue ordinal is malformed")
    return f"{HANDOFF_QUEUE_NAMESPACE}/{ordinal:020d}.json"


def _handoff_queue_item_id(value: Mapping[str, Any]) -> str:
    """Bind the full queue row, including its exact predecessor pointer."""

    return _content_id("ossq_", value, field="queue_item_id")


def utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        _fail("selector clock is naive")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        _fail(f"{label} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise SparseSelectorError(f"{label} must be canonical UTC") from exc
    canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if canonical != value:
        _fail(f"{label} must be canonical UTC")
    return parsed


def _aware_utc(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        _fail(f"{label} is naive")
    return value.astimezone(timezone.utc)


def _jsonschema_equality_key(value: object) -> tuple[Any, ...]:
    """Hash strict JSON with Draft 2020-12 equality, including numeric equality."""

    if value is None:
        return ("null",)
    if type(value) is bool:
        return ("boolean", value)
    if type(value) is int:
        return ("number", value, 1)
    if type(value) is float:
        try:
            numerator, denominator = value.as_integer_ratio()
        except (ValueError, OverflowError) as exc:
            raise SparseSelectorError(
                "selector uniqueItems value is not finite JSON"
            ) from exc
        return ("number", numerator, denominator)
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, list):
        return (
            "array",
            tuple(_jsonschema_equality_key(item) for item in value),
        )
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            _fail("selector uniqueItems object key is not a string")
        return (
            "object",
            tuple(
                (key, _jsonschema_equality_key(item))
                for key, item in sorted(value.items())
            ),
        )
    _fail("selector uniqueItems value is not strict JSON")


def _linear_unique_items(validator, enabled, instance, schema):
    """O(n) uniqueness with the stock Draft 2020-12 JSON equality relation."""

    del validator, schema
    if not enabled or not isinstance(instance, list):
        return
    seen: set[tuple[Any, ...]] = set()
    for item in instance:
        key = _jsonschema_equality_key(item)
        if key in seen:
            yield ValidationError(f"{instance!r} has non-unique elements")
            return
        seen.add(key)


_SelectorSchemaValidator = validators.extend(
    Draft202012Validator, {"uniqueItems": _linear_unique_items}
)


def _runtime_schema() -> dict[str, Any]:
    schema = strict_json(SCHEMA_PATH.read_bytes(), label="selector runtime schema")
    if not isinstance(schema, dict):
        _fail("selector runtime schema is not an object")
    Draft202012Validator.check_schema(schema)
    return schema


def _validator(schema: Mapping[str, Any]) -> Draft202012Validator:
    return _SelectorSchemaValidator(schema, format_checker=_FORMAT_CHECKER)


def runtime_schema_validator() -> Draft202012Validator:
    """Return the sealed-runtime validator with deterministic stdlib formats."""

    return _SCHEMA_VALIDATOR


_RUNTIME_SCHEMA = _runtime_schema()
_SCHEMA_VALIDATOR = _validator(_RUNTIME_SCHEMA)
_SCHEMA_VALIDATORS_BY_NAME: dict[str, Draft202012Validator] = {}
for _definition_name, _definition in _RUNTIME_SCHEMA["$defs"].items():
    if not isinstance(_definition, Mapping):
        continue
    _schema_name = _definition.get("properties", {}).get("schema", {}).get("const")
    if not isinstance(_schema_name, str):
        continue
    if not any(
        branch.get("$ref") == f"#/$defs/{_definition_name}"
        for branch in _RUNTIME_SCHEMA["oneOf"]
    ):
        continue
    _SCHEMA_VALIDATORS_BY_NAME[_schema_name] = _validator(
        {
            "$schema": _RUNTIME_SCHEMA["$schema"],
            "$defs": _RUNTIME_SCHEMA["$defs"],
            "$ref": f"#/$defs/{_definition_name}",
        }
    )


def validate_runtime_object(value: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label} must be an object")
    clean = copy.deepcopy(dict(value))
    object_validator = _SCHEMA_VALIDATORS_BY_NAME.get(
        clean.get("schema"), _SCHEMA_VALIDATOR
    )
    errors = sorted(object_validator.iter_errors(clean), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        where = ".".join(str(part) for part in error.path) or "<root>"
        _fail(f"{label} schema validation failed at {where}: {error.message}")
    if clean.get("authority") != FALSE_AUTHORITY:
        _fail(f"{label} authority drifted")
    if "digests" in clean and clean["digests"] != DIGESTS:
        _fail(f"{label} frozen digests drifted")
    schema = clean.get("schema")
    try:
        if schema == "options.sparse_selector_candidate/v1":
            campaign = clean["campaign_row"]
            episode = clean["final_episode_row"]
            previous_candidate = clean["previous_candidate"]
            campaign_contract.validate_campaign(campaign)
            campaign_contract.validate_episode(episode)
            effective = max(
                _utc(BENCHMARK_EFFECTIVE_FREEZE_AT, label="benchmark freeze"),
                _utc(SELECTOR_EFFECTIVE_FREEZE_AT, label="selector freeze"),
            )
            expected_eligible = (
                campaign["evidence_phase"] == "prospective_after_rule_freeze"
                and _utc(campaign["formed_at"], label="campaign formed_at")
                >= effective
            )
            if (
                clean["candidate_id"] != _candidate_id(clean["campaign_id"])
                or (clean["ordinal"] == 1) != (previous_candidate is None)
                or (
                    previous_candidate is not None
                    and (
                        not str(previous_candidate["id"]).startswith("ossc_")
                        or not str(previous_candidate["key"]).startswith("candidates/")
                    )
                )
                or clean["campaign_id"] != campaign["campaign_id"]
                or clean["campaign_revision_id"] != campaign["campaign_revision_id"]
                or clean["campaign_row_sha256"] != _sha256(canonical_bytes(campaign))
                or clean["final_episode_row_sha256"]
                != _sha256(canonical_bytes(episode))
                or clean["campaign_prefix"]["records"]
                < clean["campaign_row_number"]
                or clean["episode_prefix"]["records"]
                != campaign["source_episode_prefix"]["records"]
                or clean["episode_prefix"]["sha256"]
                != campaign["source_episode_prefix"]["prefix_sha256"]
                or clean["source_checkpoint"]["campaign_records"]
                != clean["campaign_prefix"]["records"]
                or clean["source_checkpoint"]["campaign_sha256"]
                != clean["campaign_prefix"]["sha256"]
                or clean["source_checkpoint"]["episode_records"]
                < clean["episode_prefix"]["records"]
                or campaign["members"][-1]["episode_id"] != episode["episode_id"]
                or campaign["members"][-1]["source_row_sha256"]
                != clean["final_episode_row_sha256"]
                or campaign["formed_at"] != clean["source_available_at"]
                or clean["eligible_for_manifest"] is not True
                or expected_eligible is not True
                or _utc(clean["candidate_available_at"], label="candidate availability")
                < _utc(
                    clean["source_available_at"], label="candidate source availability"
                )
            ):
                _fail(f"{label} candidate semantic binding drifted")
        elif schema == "options.sparse_selector_candidate_manifest/v1":
            if clean["manifest_id"] != _content_id(
                "ossm_", clean, field="manifest_id"
            ) or not 1 <= clean["candidate_count"] <= MAX_CANDIDATES_PER_MANIFEST or clean[
                "candidate_count"
            ] != len(clean["candidates"]) or (
                clean["source_checkpoint"]["campaign_records"]
                != clean["source_campaign_prefix"]["records"]
            ) or (
                clean["source_checkpoint"]["episode_records"]
                != clean["source_episode_prefix"]["records"]
            ):
                _fail(f"{label} manifest identity or count drifted")
        elif schema == "options.sparse_selector_evidence_generation/v1":
            source_receipt = clean["w1a_source_receipt"]
            state = clean["lifecycle_state"]
            if state is not None:
                lifecycle._validate_state_shape(state)
            if (
                clean["generation_id"]
                != _content_id("osseg_", clean, field="generation_id")
                or clean["w1a_error"] != (source_receipt is None)
                or clean["lifecycle_error"] != (state is None)
                or (clean["mark_error"] and state is not None)
                or len(canonical_bytes(clean)) > MAX_EVIDENCE_GENERATION_BYTES
            ):
                _fail(f"{label} evidence generation binding drifted")
        elif schema == "options.sparse_selector_decision/v1":
            previous_decision = clean["previous_decision"]
            truth_complete = all(
                clean["evidence"].get(name) is not None
                for name in (
                    "options",
                    "generation",
                    "konseki",
                    "mark",
                    "lifecycle",
                )
            )
            if (
                clean["decision_id"]
                != _content_id("ossd_", clean, field="decision_id")
                or (clean["ordinal"] == 1) != (previous_decision is None)
                or (
                    previous_decision is not None
                    and (
                        not str(previous_decision["id"]).startswith("ossd_")
                        or not str(previous_decision["key"]).startswith("decisions/")
                    )
                )
                or (
                    clean["action"] == "propose"
                    and (
                        clean["reason_codes"]
                        or not truth_complete
                        or clean["proposal_ordinal"] is None
                        or clean["decision_nyse_session_date"] is None
                        or clean["contract"] is None
                        or clean["plan_id"] is None
                    )
                )
                or (
                    clean["action"] == "abstain"
                    and (
                        not clean["reason_codes"]
                        or clean["proposal_ordinal"] is not None
                    )
                )
                or (
                    (
                        clean["evidence"].get("mark") is None
                        or clean["evidence"].get("lifecycle") is None
                    )
                    and (clean["contract"] is not None or clean["plan_id"] is not None)
                )
                or not (
                    _utc(clean["decision_event_at"], label="decision event")
                    <= _utc(clean["evidence_verified_at"], label="evidence verified")
                    <= _utc(clean["decision_available_at"], label="decision available")
                )
            ):
                _fail(f"{label} decision identity drifted")
        elif schema == "options.sparse_selector_cycle_receipt/v1":
            if clean["cycle_id"] != _cycle_id(
                ordinal=clean["ordinal"],
                scheduled_at=clean["scheduled_at"],
                started_at=clean["started_at"],
                source_commit=clean["source_commit"],
                previous_head_id=clean["previous_head_id"],
            ):
                _fail(f"{label} cycle identity drifted")
            if (
                clean["decision_count"] != len(clean["decision_ids"])
                or clean["decision_count"] != len(clean["decision_pointers"])
                or clean["decision_count"] > MAX_CANDIDATES_PER_MANIFEST
                or clean["candidate_count_after"] - clean["candidate_count_before"]
                != len(clean["candidate_pointers"])
                or len(clean["candidate_pointers"])
                > MAX_CANDIDATES_PER_MANIFEST
                or clean["decision_count_after"] - clean["decision_count_before"]
                != clean["decision_count"]
                or (clean["candidate_count_before"] == 0)
                != (clean["previous_candidate"] is None)
                or (clean["candidate_count_after"] == 0)
                != (clean["last_candidate"] is None)
                or (clean["decision_count_before"] == 0)
                != (clean["previous_decision"] is None)
                or (clean["decision_count_after"] == 0)
                != (clean["last_decision"] is None)
                or (
                    bool(clean["candidate_pointers"])
                    and clean["last_candidate"] != clean["candidate_pointers"][-1]
                )
                or (
                    not clean["candidate_pointers"]
                    and clean["last_candidate"] != clean["previous_candidate"]
                )
                or (
                    bool(clean["decision_pointers"])
                    and clean["last_decision"] != clean["decision_pointers"][-1]
                )
                or (
                    not clean["decision_pointers"]
                    and clean["last_decision"] != clean["previous_decision"]
                )
                or clean["decision_count"]
                != clean["abstain_count"] + clean["propose_count"]
                or [pointer["id"] for pointer in clean["decision_pointers"]]
                != clean["decision_ids"]
                or any(
                    pointer["key"] != f"decisions/{pointer['id']}.json"
                    for pointer in clean["decision_pointers"]
                )
                or (clean["ordinal"] == 1) != (clean["previous_cycle"] is None)
                or clean["source_campaign_prefix"]["path"] != CAMPAIGNS_PATH
                or clean["source_episode_prefix"]["path"] != EPISODES_PATH
                or clean["source_checkpoint"]["campaign_sha256"]
                != clean["source_campaign_prefix"]["sha256"]
                or clean["source_checkpoint"]["episode_sha256"]
                != clean["source_episode_prefix"]["sha256"]
                or not (
                    0
                    <= clean["source_campaign_cursor_before"]
                    <= clean["source_campaign_cursor_after"]
                    <= clean["source_campaign_prefix"]["records"]
                )
                or _utc(clean["source_observed_at"], label="cycle source observation")
                > _utc(clean["started_at"], label="cycle start")
            ):
                _fail(f"{label} cycle decision reconciliation drifted")
        elif schema == "options.sparse_selector_handoff_queue_item/v1":
            cycle_pointer = clean["selector_cycle"]
            previous_cycle = clean["previous_cycle"]
            previous_queue_item = clean["previous_queue_item"]
            expected_previous_id = (
                None if previous_queue_item is None else previous_queue_item["id"]
            )
            if (
                clean["queue_item_id"] != _handoff_queue_item_id(clean)
                or (clean["ordinal"] == 1) != (clean["previous_queue_item_id"] is None)
                or clean["previous_queue_item_id"] != expected_previous_id
                or (clean["ordinal"] == 1) != (previous_queue_item is None)
                or (clean["ordinal"] == 1) != (previous_cycle is None)
                or (
                    previous_queue_item is not None
                    and previous_queue_item["key"]
                    != _handoff_queue_key(clean["ordinal"] - 1)
                )
                or not str(cycle_pointer["id"]).startswith("oscy_")
                or cycle_pointer["key"] != f"cycles/{cycle_pointer['id']}.json"
                or clean["producer_rule_sha256"] != SELECTOR_RULE_SHA256
            ):
                _fail(f"{label} handoff queue binding drifted")
            skips = clean["skip_queue_items"]
            expected_levels = 0 if clean["ordinal"] == 1 else (clean["ordinal"] - 1).bit_length()
            if len(skips) != expected_levels or (
                skips and skips[0] != previous_queue_item
            ):
                _fail(f"{label} handoff queue skip index drifted")
            for level, pointer in enumerate(skips):
                ancestor_ordinal = clean["ordinal"] - (1 << level)
                if pointer["key"] != _handoff_queue_key(ancestor_ordinal):
                    _fail(f"{label} handoff queue skip ordinal drifted")
        elif schema == "options.sparse_selector_head/v1":
            candidate_index = private_auth_dict.validate_sharded_root(
                clean["candidate_index"], domain=CANDIDATE_INDEX_DOMAIN
            )
            source_candidate_index = private_auth_dict.validate_sharded_root(
                clean["source_candidate_index"],
                domain=SOURCE_CANDIDATE_INDEX_DOMAIN,
            )
            campaign_history_index = private_auth_dict.validate_sharded_root(
                clean["source_campaign_history_index"],
                domain=SOURCE_CAMPAIGN_HISTORY_DOMAIN,
            )
            episode_identity_index = private_auth_dict.validate_sharded_root(
                clean["source_episode_identity_index"],
                domain=SOURCE_EPISODE_IDENTITY_DOMAIN,
            )
            episode_group_index = private_auth_dict.validate_sharded_root(
                clean["source_episode_group_index"],
                domain=SOURCE_EPISODE_GROUP_DOMAIN,
            )
            if (
                clean["head_id"] != _content_id("ossh_", clean, field="head_id")
                or clean["generation"] < clean["cycle_count"]
                or (clean["generation"] == 1) != (clean["previous_head_id"] is None)
                or clean["handoff_queue_count"] != clean["cycle_count"]
                or (clean["cycle_count"] == 0) != (clean["last_cycle"] is None)
                or (clean["cycle_count"] == 0)
                != (clean["last_handoff_queue"] is None)
                or (clean["candidate_count"] == 0)
                != (clean["last_candidate"] is None)
                or candidate_index["entry_count"] != clean["candidate_count"]
                or (
                    clean["source_phase"] in {"READY", "DRAINED"}
                    and source_candidate_index["entry_count"]
                    != clean["source_ready_count"]
                )
                or episode_identity_index["entry_count"]
                != clean["source_episode_cursor_records"] * 2
                or episode_group_index["entry_count"]
                != clean["source_episode_cursor_records"]
                + clean["source_episode_group_count"]
                or campaign_history_index["entry_count"]
                != clean["source_campaign_cursor_records"] * 2
                or (clean["decision_count"] == 0)
                != (clean["last_decision"] is None)
                or clean["source_campaign_prefix"]["path"] != CAMPAIGNS_PATH
                or clean["source_episode_prefix"]["path"] != EPISODES_PATH
                or clean["source_checkpoint"]["campaign_records"]
                != clean["source_campaign_prefix"]["records"]
                or clean["source_checkpoint"]["campaign_sha256"]
                != clean["source_campaign_prefix"]["sha256"]
                or clean["source_checkpoint"]["episode_records"]
                != clean["source_episode_prefix"]["records"]
                or clean["source_checkpoint"]["episode_sha256"]
                != clean["source_episode_prefix"]["sha256"]
                or not (
                    0
                    <= clean["source_campaign_cursor_records"]
                    <= clean["source_campaign_prefix"]["records"]
                )
                or not (
                    0
                    <= clean["source_campaign_cursor_bytes"]
                    <= clean["source_campaign_prefix"]["bytes"]
                )
                or not (
                    0
                    <= clean["source_episode_cursor_records"]
                    <= clean["source_episode_prefix"]["records"]
                )
                or not (
                    0
                    <= clean["source_episode_cursor_bytes"]
                    <= clean["source_episode_prefix"]["bytes"]
                )
                or len(clean["source_run_cursors"])
                != len(clean["source_run_manifests"])
                or not 0 <= clean["source_ready_cursor"] <= clean["source_ready_count"]
                or (clean["source_ready_cursor"] < clean["source_ready_count"])
                != (clean["source_ready_run"] is not None)
                or (clean["source_phase"] == "AUDITING")
                != (clean["source_audit_stage"] != "COMPLETE")
                or (
                    clean["source_audit_stage"] == "CAMPAIGNS"
                    and (
                        clean["source_episode_cursor_records"]
                        != clean["source_episode_prefix"]["records"]
                        or clean["source_episode_cursor_bytes"]
                        != clean["source_episode_prefix"]["bytes"]
                    )
                )
                or (
                    clean["source_phase"] in {"READY", "DRAINED"}
                    and clean["source_campaign_cursor_records"]
                    != clean["source_campaign_prefix"]["records"]
                )
                or (
                    clean["source_phase"] in {"RUNS_READY", "MERGING", "READY", "DRAINED"}
                    and clean["source_campaign_cursor_bytes"]
                    != clean["source_campaign_prefix"]["bytes"]
                )
                or (
                    clean["source_phase"] == "DRAINED"
                    and clean["source_ready_cursor"] != clean["source_ready_count"]
                )
                or _utc(clean["source_observed_at"], label="HEAD source observation")
                > _utc(clean["advanced_at"], label="HEAD advance")
                or (
                    clean["proposal_session_date"] is None
                    and clean["proposal_session_count"] != 0
                )
                or (
                    clean["proposal_session_date"] is not None
                    and not nyse_calendar.is_session(
                        date.fromisoformat(clean["proposal_session_date"])
                    )
                )
            ):
                _fail(f"{label} HEAD identity drifted")
            next_row = 1
            next_byte = 0
            for reference in clean["source_episode_chunks"]:
                if (
                    reference["first_row"] != next_row
                    or reference["first_byte"] != next_byte
                    or reference["last_row"] < reference["first_row"]
                    or reference["last_byte"] <= reference["first_byte"]
                ):
                    _fail(f"{label} episode chunk index is not contiguous")
                next_row = reference["last_row"] + 1
                next_byte = reference["last_byte"]
            if (
                next_row - 1 != clean["source_episode_cursor_records"]
                or next_byte != clean["source_episode_cursor_bytes"]
            ):
                _fail(f"{label} episode chunk cursor drifted")
        elif schema == "options.sparse_selector_w1a_source_receipt/v1":
            head = context_store.validate_head(clean["head"])
            head_body = canonical_bytes(head)
            descriptors = clean["descriptors"]
            ordinals = [item["descriptor_ordinal"] for item in descriptors]
            candidate_ids = [item["candidate_id"] for item in descriptors]
            candidate_pointers = [item["candidate"] for item in descriptors]
            reference_ordinals = [
                item["reference_ordinal"]
                for item in descriptors
                if item["reference_ordinal"] is not None
            ]
            if (
                clean["receipt_id"]
                != _content_id("ossw_", clean, field="receipt_id")
                or clean["head_sha256"] != _sha256(head_body)
                or clean["head_bytes"] != len(head_body)
                or clean["audit_id"] != head["audit_id"]
                or clean["audit_object_key"] != head["audit_object_key"]
                or clean["audit_sha256"] != head["audit_sha256"]
                or clean["reference_set_object_key"]
                != head["reference_set_object_key"]
                or clean["reference_set_object_sha256"]
                != head["reference_set_object_sha256"]
                or clean["reference_set_sha256"] != head["reference_set_sha256"]
                or clean["reference_count"] != head["reference_count"]
                or ordinals != list(range(1, len(descriptors) + 1))
                or len(candidate_ids) != len(set(candidate_ids))
                or len({canonical_bytes(item) for item in candidate_pointers})
                != len(candidate_pointers)
                or len(reference_ordinals) != len(set(reference_ordinals))
                or any(
                    item["candidate"]["id"] != item["candidate_id"]
                    or (
                        item["reference_ordinal"] is None
                        and (
                            item["reference_id"] is not None
                            or item["reference_sha256"] is not None
                        )
                    )
                    or (
                        item["reference_ordinal"] is not None
                        and (
                            item["reference_id"] is None
                            or item["reference_sha256"] is None
                            or item["reference_ordinal"] > clean["reference_count"]
                        )
                    )
                    for item in descriptors
                )
                or _utc(clean["captured_at"], label="W1A source capture")
                < _utc(head["published_at"], label="W1A publication")
                or len(canonical_bytes(clean)) > MAX_W1A_SOURCE_RECEIPT_BYTES
            ):
                _fail(f"{label} W1A source receipt binding drifted")
    except (KeyError, TypeError, campaign_contract.CampaignContractError) as exc:
        raise SparseSelectorError(f"{label} semantic validation failed") from exc
    return clean


@dataclass(frozen=True)
class JsonlRow:
    ordinal: int
    value: dict[str, Any]
    raw: bytes
    first_eligible_revision: bool = False


@dataclass(frozen=True)
class SourceSnapshot:
    commit: str
    campaigns_raw: bytes | None
    episodes_raw: bytes | None
    observed_at: str
    campaigns_blob_oid: str | None = None
    episodes_blob_oid: str | None = None
    checkpoint_raw: bytes | None = None
    checkpoint_blob_oid: str | None = None


@dataclass(frozen=True)
class _EpisodePrefixView:
    """Constant-space source receipt accepted by campaign payload derivation."""

    label: str
    count: int
    raw: bytes = b""


@dataclass(frozen=True)
class SourceProjectionBatch:
    campaigns: tuple[JsonlRow, ...]
    episodes: tuple[JsonlRow, ...]
    episode_receipts: Mapping[int, Mapping[str, Any]]
    row_pointers: Mapping[int, Mapping[str, Any]]
    next_by_ordinal: Mapping[int, Mapping[str, Any] | None]
    objects: tuple["PlannedObject", ...]


@dataclass(frozen=True)
class EvidenceInputs:
    w1a_receipt_root: Path | None = None
    mark_root: Path | None = None
    lifecycle_root: Path | None = None


@dataclass(frozen=True)
class EvidenceSnapshot:
    w1a_head: Mapping[str, Any] | None
    w1a_audit: Mapping[str, Any] | None
    w1a_references: tuple[Mapping[str, Any], ...]
    w1a_root_path_sha256: str | None
    w1a_by_episode: Mapping[str, tuple[Mapping[str, Any], ...]]
    lifecycle_state: Mapping[str, Any] | None
    enrollments_by_contract: Mapping[
        tuple[str, str, str, str], tuple[tuple[str, Mapping[str, Any], Mapping[str, Any]], ...]
    ]
    mark_rows_by_plan_session: Mapping[
        tuple[str, str],
        tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]],
    ]
    w1a_error: bool = False
    mark_error: bool = False
    lifecycle_error: bool = False
    lifecycle_publishable: bool = False
    lifecycle_unpublishable_contracts: frozenset[
        tuple[str, str, str, str]
    ] = frozenset()
    mark_unpublishable_plan_sessions: frozenset[tuple[str, str]] = frozenset()


@dataclass(frozen=True)
class PlannedObject:
    key: str
    value: dict[str, Any]

    @property
    def body(self) -> bytes:
        return canonical_bytes(self.value)

    @property
    def pointer(self) -> dict[str, Any]:
        return {
            "id": object_identity(self.value),
            "key": self.key,
            "sha256": _sha256(self.body),
            "bytes": len(self.body),
        }


@dataclass(frozen=True)
class CyclePlan:
    expected_head_id: str | None
    objects: tuple[PlannedObject, ...]
    head: dict[str, Any]
    intent: dict[str, Any]
    evidence_inputs: EvidenceInputs = EvidenceInputs()


def object_identity(value: Mapping[str, Any]) -> str:
    if value.get("schema") in {
        "options.sparse_selector_konseki_evidence/v1",
        "options.sparse_selector_mark_evidence/v1",
        "options.sparse_selector_lifecycle_evidence/v1",
    }:
        return "obj_" + _sha256(canonical_bytes(value))
    if value.get("schema") == private_auth_dict.SCHEMA:
        node_id = value.get("node_id")
        if isinstance(node_id, str) and node_id:
            return node_id
    if value.get("schema") == "options.sparse_selector_decision/v1":
        decision_id = value.get("decision_id")
        if isinstance(decision_id, str) and decision_id:
            return decision_id
    if value.get("schema") == "options.sparse_selector_source_projection_row/v1":
        projection_id = value.get("projection_id")
        if isinstance(projection_id, str) and projection_id:
            return projection_id
    for field in (
        "chunk_id",
        "seed_id",
        "run_id",
        "candidate_id",
        "manifest_id",
        "generation_id",
        "decision_id",
        "cycle_id",
        "queue_item_id",
        "reference_id",
        "observation_id",
        "event_id",
        "state_id",
        "receipt_id",
    ):
        item = value.get(field)
        if isinstance(item, str) and item:
            return item
    return "obj_" + _sha256(canonical_bytes(value))


def _decode_jsonl(raw: bytes, *, label: str, limit: int) -> list[JsonlRow]:
    if len(raw) > limit:
        _fail(f"{label} exceeds its byte cap")
    if raw and not raw.endswith(b"\n"):
        _fail(f"{label} has a torn final row")
    rows: list[JsonlRow] = []
    for ordinal, line in enumerate(raw.splitlines(), start=1):
        if not line:
            _fail(f"{label} has a blank row")
        value = strict_json(line, label=f"{label} row {ordinal}")
        if not isinstance(value, dict) or canonical_bytes(value) != line:
            _fail(f"{label} row {ordinal} is not canonical")
        rows.append(JsonlRow(ordinal=ordinal, value=value, raw=line))
    return rows


def _decode_jsonl_window(
    raw: bytes,
    *,
    label: str,
    start_byte: int,
    start_record: int,
    max_rows: int = MAX_SOURCE_ROWS_PER_CYCLE,
    max_bytes: int = MAX_INTENT_BYTES // 2,
) -> tuple[list[JsonlRow], int]:
    """Parse one resumable JSONL window without splitting the full source."""

    if (
        type(start_byte) is not int
        or type(start_record) is not int
        or not 0 <= start_byte <= len(raw)
        or start_record < 0
        or (start_byte and raw[start_byte - 1 : start_byte] != b"\n")
        or type(max_rows) is not int
        or not 1 <= max_rows <= MAX_SOURCE_ROWS_PER_CYCLE
        or type(max_bytes) is not int
        or max_bytes < 1
    ):
        _fail(f"{label} resumable cursor is malformed")
    rows: list[JsonlRow] = []
    cursor = start_byte
    parsed_bytes = 0
    while cursor < len(raw) and len(rows) < max_rows:
        newline = raw.find(b"\n", cursor)
        if newline < 0:
            _fail(f"{label} has a torn final row")
        line = raw[cursor:newline]
        if not line:
            _fail(f"{label} has a blank row")
        row_bytes = newline + 1 - cursor
        if rows and parsed_bytes + row_bytes > max_bytes:
            break
        if row_bytes > MAX_OBJECT_BYTES:
            _fail(f"{label} row exceeds its object cap")
        ordinal = start_record + len(rows) + 1
        value = strict_json(line, label=f"{label} row {ordinal}")
        if not isinstance(value, dict) or canonical_bytes(value) != line:
            _fail(f"{label} row {ordinal} is not canonical")
        rows.append(JsonlRow(ordinal=ordinal, value=value, raw=line))
        cursor = newline + 1
        parsed_bytes += row_bytes
    return rows, cursor


def _git_blob_oid(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    digest = hashlib.sha1()  # noqa: S324 - Git object ID
    digest.update(header)
    digest.update(raw)
    return digest.hexdigest()


def _source_blob_oid(raw: bytes, claimed: str | None, *, label: str) -> str:
    if claimed is None:
        return _git_blob_oid(raw)
    if not re.fullmatch(r"[a-f0-9]{40,64}", claimed):
        _fail(f"{label} Git blob object id is malformed")
    return claimed


def _source_receipt(
    raw: bytes,
    *,
    path: str,
    records: int,
    git_blob_oid: str,
) -> dict[str, Any]:
    return {
        "path": path,
        "records": records,
        "bytes": len(raw),
        "sha256": _sha256(raw),
        "git_blob_oid": git_blob_oid,
    }


def _validate_campaign_checkpoint(
    source: SourceSnapshot,
    *,
    campaign_prefix: Mapping[str, Any],
    episode_prefix: Mapping[str, Any],
    previous_checkpoint: Mapping[str, Any] | None,
) -> dict[str, Any]:
    raw = source.checkpoint_raw
    if raw is None:
        if previous_checkpoint is None:
            _fail("selector source checkpoint is absent")
        if source.checkpoint_blob_oid != previous_checkpoint.get("git_blob_oid"):
            _fail("bodyless selector checkpoint object id drifted")
        return copy.deepcopy(dict(previous_checkpoint))
    if len(raw) > MAX_OBJECT_BYTES or not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        _fail("selector source checkpoint framing is malformed")
    checkpoint = strict_json(raw[:-1], label="selector source checkpoint")
    if not isinstance(checkpoint, dict) or canonical_bytes(checkpoint) + b"\n" != raw:
        _fail("selector source checkpoint is not canonical")
    try:
        campaign_contract.validate_checkpoint(checkpoint)
    except campaign_contract.CampaignContractError as exc:
        raise SparseSelectorError("selector source checkpoint is invalid") from exc
    campaign_receipt = checkpoint["outputs"]["campaigns"]
    episode_receipt = checkpoint["sources"]["episodes"]
    if (
        campaign_receipt.get("path") != CAMPAIGNS_PATH
        or campaign_receipt.get("records") != campaign_prefix.get("records")
        or campaign_receipt.get("prefix_sha256") != campaign_prefix.get("sha256")
        or episode_receipt.get("path") != EPISODES_PATH
        or episode_receipt.get("records") != episode_prefix.get("records")
        or episode_receipt.get("prefix_sha256") != episode_prefix.get("sha256")
    ):
        _fail("selector source checkpoint does not bind exact ledgers")
    oid = _source_blob_oid(raw, source.checkpoint_blob_oid, label="campaign checkpoint")
    if source.checkpoint_blob_oid is not None and _git_blob_oid(raw) != oid:
        _fail("campaign checkpoint bytes differ from their Git blob object id")
    receipt = {
        "path": CAMPAIGN_CHECKPOINT_PATH,
        "bytes": len(raw),
        "sha256": _sha256(raw),
        "git_blob_oid": oid,
        "source_commit": source.commit,
        "checkpoint_id": checkpoint["checkpoint_id"],
        "campaign_records": campaign_receipt["records"],
        "campaign_sha256": campaign_receipt["prefix_sha256"],
        "episode_records": episode_receipt["records"],
        "episode_sha256": episode_receipt["prefix_sha256"],
    }
    if previous_checkpoint is not None:
        if (
            previous_checkpoint.get("campaign_records", 0) > receipt["campaign_records"]
            or previous_checkpoint.get("episode_records", 0) > receipt["episode_records"]
        ):
            _fail("selector source checkpoint rolled back")
        if (
            previous_checkpoint.get("campaign_records") == receipt["campaign_records"]
            and previous_checkpoint.get("campaign_sha256") != receipt["campaign_sha256"]
        ):
            _fail("selector source checkpoint rewrote its campaign prefix")
        if (
            previous_checkpoint.get("episode_records") == receipt["episode_records"]
            and previous_checkpoint.get("episode_sha256") != receipt["episode_sha256"]
        ):
            _fail("selector source checkpoint rewrote its episode prefix")
    return receipt


def _validate_previous_prefix(
    raw: bytes, receipt: Mapping[str, Any] | None, *, path: str
) -> tuple[int, int]:
    if receipt is None:
        return 0, 0
    size = receipt.get("bytes")
    records = receipt.get("records")
    digest = receipt.get("sha256")
    if (
        receipt.get("path") != path
        or type(size) is not int
        or type(records) is not int
        or size < 0
        or records < 0
        or not isinstance(digest, str)
        or not _SHA256_RE.fullmatch(digest)
        or len(raw) < size
        or _sha256(raw[:size]) != digest
        or (size > 0 and raw[size - 1 : size] != b"\n")
    ):
        _fail(f"source ledger did not preserve the prior exact prefix: {path}")
    return records, size


def validate_source_snapshot(
    source: SourceSnapshot,
    *,
    previous_campaign_prefix: Mapping[str, Any] | None = None,
    previous_episode_prefix: Mapping[str, Any] | None = None,
    previous_checkpoint: Mapping[str, Any] | None = None,
    previous_campaign_cursor_records: int | None = None,
) -> tuple[
    list[JsonlRow],
    list[JsonlRow],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    if not isinstance(source.commit, str) or not _COMMIT_RE.fullmatch(source.commit):
        _fail("source commit is malformed")
    _utc(source.observed_at, label="source observation clock")
    if (previous_campaign_prefix is None) != (previous_episode_prefix is None):
        _fail("selector source cursors are only valid as an exact pair")
    if previous_campaign_prefix is None:
        if previous_campaign_cursor_records not in (None, 0):
            _fail("selector initial source cursor is malformed")
        campaign_cursor_records = 0
    else:
        campaign_cursor_records = (
            previous_campaign_prefix["records"]
            if previous_campaign_cursor_records is None
            else previous_campaign_cursor_records
        )
        if (
            type(campaign_cursor_records) is not int
            or not 0 <= campaign_cursor_records <= previous_campaign_prefix["records"]
        ):
            _fail("selector source campaign cursor is malformed")
    if (source.campaigns_raw is None) != (source.episodes_raw is None):
        _fail("selector source bodies are only valid as an exact pair")
    if source.campaigns_raw is None:
        if (
            previous_campaign_prefix is None
            or previous_episode_prefix is None
            or source.campaigns_blob_oid != previous_campaign_prefix.get("git_blob_oid")
            or source.episodes_blob_oid != previous_episode_prefix.get("git_blob_oid")
            or campaign_cursor_records != previous_campaign_prefix.get("records")
        ):
            _fail("bodyless source object ids do not match a completed authenticated cursor")
        checkpoint = _validate_campaign_checkpoint(
            source,
            campaign_prefix=previous_campaign_prefix,
            episode_prefix=previous_episode_prefix,
            previous_checkpoint=previous_checkpoint,
        )
        return (
            [],
            [],
            copy.deepcopy(dict(previous_campaign_prefix)),
            copy.deepcopy(dict(previous_episode_prefix)),
            checkpoint,
        )
    assert source.episodes_raw is not None
    if (
        len(source.campaigns_raw) > MAX_SOURCE_BYTES
        or len(source.episodes_raw) > MAX_SOURCE_BYTES
    ):
        _fail("selector source exceeds its byte cap")

    campaign_oid = _source_blob_oid(
        source.campaigns_raw, source.campaigns_blob_oid, label="campaign source"
    )
    episode_oid = _source_blob_oid(
        source.episodes_raw, source.episodes_blob_oid, label="episode source"
    )
    if source.campaigns_blob_oid is not None and _git_blob_oid(
        source.campaigns_raw
    ) != campaign_oid:
        _fail("campaign source bytes differ from their Git blob object id")
    if source.episodes_blob_oid is not None and _git_blob_oid(
        source.episodes_raw
    ) != episode_oid:
        _fail("episode source bytes differ from their Git blob object id")
    unchanged = (
        previous_campaign_prefix is not None
        and previous_episode_prefix is not None
        and previous_campaign_prefix.get("git_blob_oid") == campaign_oid
        and previous_episode_prefix.get("git_blob_oid") == episode_oid
        and previous_campaign_prefix.get("bytes") == len(source.campaigns_raw)
        and previous_episode_prefix.get("bytes") == len(source.episodes_raw)
    )
    if unchanged and campaign_cursor_records == previous_campaign_prefix["records"]:
        checkpoint = _validate_campaign_checkpoint(
            source,
            campaign_prefix=previous_campaign_prefix,
            episode_prefix=previous_episode_prefix,
            previous_checkpoint=previous_checkpoint,
        )
        return (
            [],
            [],
            copy.deepcopy(dict(previous_campaign_prefix)),
            copy.deepcopy(dict(previous_episode_prefix)),
            checkpoint,
        )

    # A new Git object is audited as a complete immutable source pair. This is
    # the only path that semantically scans historical source rows; unchanged
    # Git object IDs take the constant-work path above.
    previous_campaign_records, _previous_campaign_bytes = _validate_previous_prefix(
        source.campaigns_raw, previous_campaign_prefix, path=CAMPAIGNS_PATH
    )
    previous_episode_records, _previous_episode_bytes = _validate_previous_prefix(
        source.episodes_raw, previous_episode_prefix, path=EPISODES_PATH
    )
    campaign_snapshot = campaign_contract._snapshot_from_raw(
        Path(CAMPAIGNS_PATH), CAMPAIGNS_PATH, source.campaigns_raw
    )
    episode_snapshot = campaign_contract._snapshot_from_raw(
        Path(EPISODES_PATH), EPISODES_PATH, source.episodes_raw
    )
    episode_groups = campaign_contract._validated_episode_groups(episode_snapshot)
    campaign_contract._campaign_history(
        campaign_snapshot,
        episode_snapshot,
        groups=episode_groups,
    )
    if (
        previous_campaign_records > campaign_snapshot.count
        or previous_episode_records > episode_snapshot.count
    ):
        _fail("selector source shrank behind its authenticated cursor")
    effective = max(
        _utc(BENCHMARK_EFFECTIVE_FREEZE_AT, label="benchmark freeze"),
        _utc(SELECTOR_EFFECTIVE_FREEZE_AT, label="selector freeze"),
    )
    first_eligible_revision_ids: set[str] = set()
    eligible_campaign_ids: set[str] = set()
    for item in campaign_snapshot.rows:
        campaign = item.value
        formed = _utc(campaign["formed_at"], label="campaign formed_at")
        eligible = (
            campaign["evidence_phase"] == "prospective_after_rule_freeze"
            and formed >= effective
        )
        if eligible and campaign["campaign_id"] not in eligible_campaign_ids:
            eligible_campaign_ids.add(campaign["campaign_id"])
            first_eligible_revision_ids.add(campaign["campaign_revision_id"])
    if campaign_cursor_records > campaign_snapshot.count:
        _fail("selector campaign cursor exceeds the audited source")
    campaigns = [
        JsonlRow(
            item.ordinal,
            copy.deepcopy(item.value),
            item.raw,
            item.value["campaign_revision_id"] in first_eligible_revision_ids,
        )
        for item in campaign_snapshot.rows[campaign_cursor_records:]
    ]
    # Candidate-owner joins may legitimately refer to an episode admitted in a
    # prior selector cycle: the producer publishes the two ledgers in separate
    # commits.  Full semantic audit already parsed the changed blob, so retain
    # the complete authenticated episode projection for exact row lookup.
    episodes = [
        JsonlRow(item.ordinal, copy.deepcopy(item.value), item.raw)
        for item in episode_snapshot.rows
    ]
    campaign_receipt = _source_receipt(
        source.campaigns_raw,
        path=CAMPAIGNS_PATH,
        records=campaign_snapshot.count,
        git_blob_oid=campaign_oid,
    )
    episode_receipt = _source_receipt(
        source.episodes_raw,
        path=EPISODES_PATH,
        records=episode_snapshot.count,
        git_blob_oid=episode_oid,
    )
    checkpoint = _validate_campaign_checkpoint(
        source,
        campaign_prefix=campaign_receipt,
        episode_prefix=episode_receipt,
        previous_checkpoint=previous_checkpoint,
    )
    return (
        campaigns,
        episodes,
        campaign_receipt,
        episode_receipt,
        checkpoint,
    )


def _source_projection_id(value: Mapping[str, Any]) -> str:
    return _content_id("ossp_", value, field="projection_id")


def _validate_source_projection_row(
    value: Mapping[str, Any],
    *,
    expected_commit: str | None = None,
    expected_observed_at: str | None = None,
    expected_campaign_prefix: Mapping[str, Any] | None = None,
    expected_episode_prefix: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected_fields = {
        "schema",
        "projection_id",
        "source_commit",
        "source_observed_at",
        "source_campaign_prefix",
        "source_episode_prefix",
        "campaign_row_number",
        "campaign_row",
        "campaign_row_sha256",
        "first_eligible_revision",
        "final_episode_row_number",
        "final_episode_row",
        "final_episode_row_sha256",
        "episode_prefix",
        "next_projection",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        _fail("selector source projection row fields are malformed")
    clean = copy.deepcopy(dict(value))
    campaign = clean["campaign_row"]
    campaign_contract.validate_campaign(campaign)
    if (
        clean["schema"] != "options.sparse_selector_source_projection_row/v1"
        or clean["projection_id"] != _source_projection_id(clean)
        or not isinstance(clean["source_commit"], str)
        or not _COMMIT_RE.fullmatch(clean["source_commit"])
        or clean["authority"] != FALSE_AUTHORITY
        or type(clean["campaign_row_number"]) is not int
        or clean["campaign_row_number"] < 1
        or clean["campaign_row_sha256"] != _sha256(canonical_bytes(campaign))
        or type(clean["first_eligible_revision"]) is not bool
        or clean["source_campaign_prefix"].get("path") != CAMPAIGNS_PATH
        or clean["source_episode_prefix"].get("path") != EPISODES_PATH
        or clean["campaign_row_number"]
        > clean["source_campaign_prefix"].get("records", -1)
    ):
        _fail("selector source projection row binding drifted")
    _utc(clean["source_observed_at"], label="source projection observation")
    if expected_commit is not None and clean["source_commit"] != expected_commit:
        _fail("selector source projection commit drifted")
    if (
        expected_observed_at is not None
        and clean["source_observed_at"] != expected_observed_at
    ):
        _fail("selector source projection observation drifted")
    if (
        expected_campaign_prefix is not None
        and clean["source_campaign_prefix"] != dict(expected_campaign_prefix)
    ):
        _fail("selector source projection campaign prefix drifted")
    if (
        expected_episode_prefix is not None
        and clean["source_episode_prefix"] != dict(expected_episode_prefix)
    ):
        _fail("selector source projection episode prefix drifted")
    next_pointer = clean["next_projection"]
    if next_pointer is not None:
        _object_path(Path("/"), str(next_pointer.get("key", "")))
        if not str(next_pointer.get("key", "")).startswith(
            f"{SOURCE_PROJECTION_NAMESPACE}/"
        ):
            _fail("selector source projection successor namespace drifted")

    final_episode = clean["final_episode_row"]
    episode_receipt = clean["episode_prefix"]
    if not clean["first_eligible_revision"]:
        if any(
            item is not None
            for item in (
                clean["final_episode_row_number"],
                final_episode,
                clean["final_episode_row_sha256"],
                episode_receipt,
            )
        ):
            _fail("ineligible source projection row carries owner evidence")
        return clean

    effective = max(
        _utc(BENCHMARK_EFFECTIVE_FREEZE_AT, label="benchmark freeze"),
        _utc(SELECTOR_EFFECTIVE_FREEZE_AT, label="selector freeze"),
    )
    if (
        campaign["evidence_phase"] != "prospective_after_rule_freeze"
        or _utc(campaign["formed_at"], label="campaign formed_at") < effective
        or not isinstance(final_episode, Mapping)
        or not isinstance(episode_receipt, Mapping)
        or type(clean["final_episode_row_number"]) is not int
        or clean["final_episode_row_number"] < 1
        or clean["final_episode_row_sha256"]
        != _sha256(canonical_bytes(final_episode))
        or episode_receipt.get("path") != EPISODES_PATH
        or episode_receipt.get("records")
        != campaign["source_episode_prefix"]["records"]
        or episode_receipt.get("sha256")
        != campaign["source_episode_prefix"]["prefix_sha256"]
        or episode_receipt.get("git_blob_oid")
        != clean["source_episode_prefix"].get("git_blob_oid")
        or clean["final_episode_row_number"]
        != campaign["members"][-1]["source_row"]
        or clean["final_episode_row_sha256"]
        != campaign["members"][-1]["source_row_sha256"]
    ):
        _fail("selector source projection owner binding drifted")
    campaign_contract.validate_episode(final_episode)
    return clean


def _build_source_projection(
    *,
    source: SourceSnapshot,
    campaigns: Sequence[JsonlRow],
    episodes: Sequence[JsonlRow],
    campaign_prefix: Mapping[str, Any],
    episode_prefix: Mapping[str, Any],
) -> SourceProjectionBatch:
    _fail("legacy segment-local source projection is permanently deauthorized")
    episode_by_ordinal = {row.ordinal: row for row in episodes}
    episode_end: dict[int, int] = {}
    offset = 0
    for row in episodes:
        if row.ordinal != len(episode_end) + 1:
            _fail("selector audited episode projection is not contiguous")
        offset += len(row.raw) + 1
        episode_end[row.ordinal] = offset
    if source.episodes_raw is None:
        _fail("selector cannot construct a source projection without audited bytes")

    next_pointer: dict[str, Any] | None = None
    objects_newest_first: list[PlannedObject] = []
    row_pointers: dict[int, Mapping[str, Any]] = {}
    next_by_ordinal: dict[int, Mapping[str, Any] | None] = {}
    projected_episodes: dict[int, JsonlRow] = {}
    episode_receipts: dict[int, Mapping[str, Any]] = {}
    for item in reversed(campaigns):
        campaign = item.value
        final_episode: JsonlRow | None = None
        receipt: dict[str, Any] | None = None
        final_row_number: int | None = None
        final_row_sha256: str | None = None
        if item.first_eligible_revision:
            source_records = campaign["source_episode_prefix"]["records"]
            final_row_number = campaign["members"][-1]["source_row"]
            final_episode = episode_by_ordinal.get(final_row_number)
            end = episode_end.get(source_records)
            if final_episode is None or end is None:
                _fail("selector source projection owner row is unavailable")
            receipt = {
                "path": EPISODES_PATH,
                "records": source_records,
                "bytes": end,
                "sha256": _sha256(source.episodes_raw[:end]),
                "git_blob_oid": episode_prefix["git_blob_oid"],
            }
            if (
                receipt["sha256"]
                != campaign["source_episode_prefix"]["prefix_sha256"]
            ):
                _fail("selector source projection episode receipt drifted")
            final_row_sha256 = _sha256(final_episode.raw)
            projected_episodes[final_episode.ordinal] = final_episode
            episode_receipts[source_records] = receipt
        value: dict[str, Any] = {
            "schema": "options.sparse_selector_source_projection_row/v1",
            "projection_id": "",
            "source_commit": source.commit,
            "source_observed_at": source.observed_at,
            "source_campaign_prefix": copy.deepcopy(dict(campaign_prefix)),
            "source_episode_prefix": copy.deepcopy(dict(episode_prefix)),
            "campaign_row_number": item.ordinal,
            "campaign_row": copy.deepcopy(campaign),
            "campaign_row_sha256": _sha256(item.raw),
            "first_eligible_revision": item.first_eligible_revision,
            "final_episode_row_number": final_row_number,
            "final_episode_row": (
                None if final_episode is None else copy.deepcopy(final_episode.value)
            ),
            "final_episode_row_sha256": final_row_sha256,
            "episode_prefix": receipt,
            "next_projection": copy.deepcopy(next_pointer),
            "authority": dict(FALSE_AUTHORITY),
        }
        value["projection_id"] = _source_projection_id(value)
        value = _validate_source_projection_row(value)
        planned = PlannedObject(
            key=f"{SOURCE_PROJECTION_NAMESPACE}/{value['projection_id']}.json",
            value=value,
        )
        if len(planned.body) > MAX_OBJECT_BYTES:
            _fail("selector source projection row exceeds its object bound")
        row_pointers[item.ordinal] = planned.pointer
        next_by_ordinal[item.ordinal] = copy.deepcopy(next_pointer)
        next_pointer = planned.pointer
        objects_newest_first.append(planned)
    return SourceProjectionBatch(
        campaigns=tuple(campaigns),
        episodes=tuple(projected_episodes[key] for key in sorted(projected_episodes)),
        episode_receipts=episode_receipts,
        row_pointers=row_pointers,
        next_by_ordinal=next_by_ordinal,
        objects=tuple(reversed(objects_newest_first)),
    )


def _load_source_projection_batch(
    root: Path,
    pointer: Mapping[str, Any],
    *,
    source_commit: str,
    source_observed_at: str,
    campaign_prefix: Mapping[str, Any],
    episode_prefix: Mapping[str, Any],
    first_ordinal: int,
) -> SourceProjectionBatch:
    _fail("legacy segment-local source projection is permanently deauthorized")
    campaigns: list[JsonlRow] = []
    episodes: dict[int, JsonlRow] = {}
    episode_receipts: dict[int, Mapping[str, Any]] = {}
    row_pointers: dict[int, Mapping[str, Any]] = {}
    next_by_ordinal: dict[int, Mapping[str, Any] | None] = {}
    current: Mapping[str, Any] | None = copy.deepcopy(dict(pointer))
    expected_ordinal = first_ordinal
    seen: set[str] = set()
    while current is not None and len(campaigns) < MAX_SOURCE_ROWS_PER_CYCLE:
        if current.get("id") in seen:
            _fail("selector source projection contains a cycle")
        seen.add(str(current.get("id")))
        value = _load_pointer(root, current, label="selector source projection row")
        clean = _validate_source_projection_row(
            value,
            expected_commit=source_commit,
            expected_observed_at=source_observed_at,
            expected_campaign_prefix=campaign_prefix,
            expected_episode_prefix=episode_prefix,
        )
        if clean["campaign_row_number"] != expected_ordinal:
            _fail("selector source projection row ordinal drifted")
        raw = canonical_bytes(clean["campaign_row"])
        if _sha256(raw) != clean["campaign_row_sha256"]:
            _fail("selector source projection campaign bytes drifted")
        campaigns.append(
            JsonlRow(
                ordinal=expected_ordinal,
                value=copy.deepcopy(clean["campaign_row"]),
                raw=raw,
                first_eligible_revision=clean["first_eligible_revision"],
            )
        )
        if clean["final_episode_row"] is not None:
            episode_raw = canonical_bytes(clean["final_episode_row"])
            episode_row = JsonlRow(
                ordinal=clean["final_episode_row_number"],
                value=copy.deepcopy(clean["final_episode_row"]),
                raw=episode_raw,
            )
            prior = episodes.get(episode_row.ordinal)
            if prior is not None and prior.raw != episode_row.raw:
                _fail("selector source projection repeats a conflicting owner row")
            episodes[episode_row.ordinal] = episode_row
            source_records = clean["episode_prefix"]["records"]
            prior_receipt = episode_receipts.get(source_records)
            if prior_receipt is not None and prior_receipt != clean["episode_prefix"]:
                _fail("selector source projection repeats a conflicting receipt")
            episode_receipts[source_records] = copy.deepcopy(clean["episode_prefix"])
        row_pointers[expected_ordinal] = copy.deepcopy(dict(current))
        next_by_ordinal[expected_ordinal] = copy.deepcopy(clean["next_projection"])
        current = clean["next_projection"]
        expected_ordinal += 1
    return SourceProjectionBatch(
        campaigns=tuple(campaigns),
        episodes=tuple(episodes[key] for key in sorted(episodes)),
        episode_receipts=episode_receipts,
        row_pointers=row_pointers,
        next_by_ordinal=next_by_ordinal,
        objects=(),
    )


def _source_projection_after(
    batch: SourceProjectionBatch,
    *,
    processed_campaign_records: int,
) -> Mapping[str, Any] | None:
    _fail("legacy segment-local source projection is permanently deauthorized")
    for item in batch.campaigns:
        if item.ordinal > processed_campaign_records:
            return copy.deepcopy(dict(batch.row_pointers[item.ordinal]))
        if item.ordinal == processed_campaign_records:
            successor = batch.next_by_ordinal[item.ordinal]
            return None if successor is None else copy.deepcopy(dict(successor))
    _fail("selector source projection did not cover its resulting cursor")


def _source_seed_id(value: Mapping[str, Any]) -> str:
    return _content_id("osss_", value, field="seed_id")


def _episode_chunk_id(value: Mapping[str, Any]) -> str:
    return _content_id("osec_", value, field="chunk_id")


def _validate_episode_chunk(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema",
        "chunk_id",
        "source_commit",
        "source_observed_at",
        "source_checkpoint",
        "first_row",
        "last_row",
        "first_byte",
        "last_byte",
        "rows",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        _fail("selector episode chunk fields are malformed")
    clean = copy.deepcopy(dict(value))
    rows = clean["rows"]
    if (
        clean["schema"] != "options.sparse_selector_episode_chunk/v1"
        or clean["chunk_id"] != _episode_chunk_id(clean)
        or clean["authority"] != FALSE_AUTHORITY
        or not isinstance(clean["source_commit"], str)
        or _COMMIT_RE.fullmatch(clean["source_commit"]) is None
        or type(clean["first_row"]) is not int
        or type(clean["last_row"]) is not int
        or type(clean["first_byte"]) is not int
        or type(clean["last_byte"]) is not int
        or clean["first_row"] < 1
        or clean["last_row"] < clean["first_row"]
        or clean["first_byte"] < 0
        or clean["last_byte"] <= clean["first_byte"]
        or not isinstance(rows, list)
        or len(rows) != clean["last_row"] - clean["first_row"] + 1
        or len(rows) > MAX_SOURCE_ROWS_PER_CYCLE
    ):
        _fail("selector episode chunk binding drifted")
    _utc(clean["source_observed_at"], label="episode chunk source observation")
    expected_row = clean["first_row"]
    prior_end = clean["first_byte"]
    for item in rows:
        if not isinstance(item, Mapping) or set(item) != {
            "ordinal",
            "end_byte",
            "row",
            "row_sha256",
        }:
            _fail("selector episode chunk row is malformed")
        if (
            item["ordinal"] != expected_row
            or type(item["end_byte"]) is not int
            or item["end_byte"] <= prior_end
            or item["row_sha256"] != _sha256(canonical_bytes(item["row"]))
        ):
            _fail("selector episode chunk row binding drifted")
        try:
            campaign_contract.validate_episode(item["row"])
        except campaign_contract.CampaignContractError as exc:
            raise SparseSelectorError("selector episode chunk row is invalid") from exc
        expected_row += 1
        prior_end = item["end_byte"]
    if prior_end != clean["last_byte"] or len(canonical_bytes(clean)) > MAX_RUN_BYTES:
        _fail("selector episode chunk size or terminal offset drifted")
    return clean


def _make_episode_chunk(
    *,
    source: SourceSnapshot,
    source_checkpoint: Mapping[str, Any],
    rows: Sequence[JsonlRow],
    first_byte: int,
    last_byte: int,
) -> PlannedObject:
    if not rows:
        _fail("selector cannot create an empty episode chunk")
    offsets: list[int] = []
    cursor = first_byte
    for row in rows:
        cursor += len(row.raw) + 1
        offsets.append(cursor)
    if cursor != last_byte:
        _fail("selector episode chunk byte offsets drifted")
    value: dict[str, Any] = {
        "schema": "options.sparse_selector_episode_chunk/v1",
        "chunk_id": "",
        "source_commit": source.commit,
        "source_observed_at": source.observed_at,
        "source_checkpoint": copy.deepcopy(dict(source_checkpoint)),
        "first_row": rows[0].ordinal,
        "last_row": rows[-1].ordinal,
        "first_byte": first_byte,
        "last_byte": last_byte,
        "rows": [
            {
                "ordinal": row.ordinal,
                "end_byte": end_byte,
                "row": copy.deepcopy(row.value),
                "row_sha256": _sha256(row.raw),
            }
            for row, end_byte in zip(rows, offsets, strict=True)
        ],
        "authority": dict(FALSE_AUTHORITY),
    }
    value["chunk_id"] = _episode_chunk_id(value)
    clean = _validate_episode_chunk(value)
    return PlannedObject(
        key=f"{SOURCE_PROJECTION_NAMESPACE}/{clean['chunk_id']}.json", value=clean
    )


def _load_episode_chunk(
    root: Path,
    reference: Mapping[str, Any],
    *,
    source_commit: str,
    source_observed_at: str,
    source_checkpoint: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(reference, Mapping) or set(reference) != {
        "pointer",
        "first_row",
        "last_row",
        "first_byte",
        "last_byte",
    }:
        _fail("selector episode chunk reference is malformed")
    clean = _validate_episode_chunk(
        _load_pointer(root, reference["pointer"], label="selector episode chunk")
    )
    if (
        clean["source_commit"] != source_commit
        or clean["source_observed_at"] != source_observed_at
        or clean["source_checkpoint"] != dict(source_checkpoint)
        or any(clean[field] != reference[field] for field in (
            "first_row",
            "last_row",
            "first_byte",
            "last_byte",
        ))
    ):
        _fail("selector episode chunk reference crossed source epochs")
    return clean


def _episode_rows_for_ordinals(
    root: Path,
    references: Sequence[Mapping[str, Any]],
    *,
    ordinals: set[int],
    source_commit: str,
    source_observed_at: str,
    source_checkpoint: Mapping[str, Any],
    chunk_cache: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[int, JsonlRow], dict[int, int]]:
    rows: dict[int, JsonlRow] = {}
    end_bytes: dict[int, int] = {}
    remaining = set(ordinals)
    for reference in references:
        needed = {
            ordinal
            for ordinal in remaining
            if reference["first_row"] <= ordinal <= reference["last_row"]
        }
        if not needed:
            continue
        pointer_id = str(reference["pointer"].get("id"))
        chunk = None if chunk_cache is None else chunk_cache.get(pointer_id)
        if chunk is None:
            chunk = _load_episode_chunk(
                root,
                reference,
                source_commit=source_commit,
                source_observed_at=source_observed_at,
                source_checkpoint=source_checkpoint,
            )
            if chunk_cache is not None:
                chunk_cache[pointer_id] = chunk
        for item in chunk["rows"]:
            ordinal = item["ordinal"]
            if ordinal in needed:
                rows[ordinal] = JsonlRow(
                    ordinal=ordinal,
                    value=copy.deepcopy(item["row"]),
                    raw=canonical_bytes(item["row"]),
                )
                end_bytes[ordinal] = item["end_byte"]
                remaining.remove(ordinal)
    if remaining:
        _fail("selector episode index is missing a referenced owner row")
    return rows, end_bytes


def _episode_source_from_chunks(
    root: Path,
    references: Sequence[Mapping[str, Any]],
    *,
    source_commit: str,
    source_observed_at: str,
    source_checkpoint: Mapping[str, Any],
    source_prefix: Mapping[str, Any],
) -> bytes:
    """Reconstruct and authenticate the exact pinned episode ledger."""

    parts: list[bytes] = []
    expected_row = 1
    expected_byte = 0
    for reference in references:
        if (
            reference.get("first_row") != expected_row
            or reference.get("first_byte") != expected_byte
        ):
            _fail("selector episode chunk chain is not contiguous")
        chunk = _load_episode_chunk(
            root,
            reference,
            source_commit=source_commit,
            source_observed_at=source_observed_at,
            source_checkpoint=source_checkpoint,
        )
        for item in chunk["rows"]:
            raw = canonical_bytes(item["row"])
            if (
                item["ordinal"] != expected_row
                or item["row_sha256"] != _sha256(raw)
            ):
                _fail("selector episode chunk reconstruction drifted")
            parts.append(raw + b"\n")
            expected_row += 1
            expected_byte += len(raw) + 1
            if item["end_byte"] != expected_byte:
                _fail("selector episode chunk byte chain drifted")
        if (
            chunk["last_row"] != expected_row - 1
            or chunk["last_byte"] != expected_byte
        ):
            _fail("selector episode chunk terminal receipt drifted")
    body = b"".join(parts)
    if (
        expected_row - 1 != source_prefix["records"]
        or expected_byte != source_prefix["bytes"]
        or _sha256(body) != source_prefix["sha256"]
        or _git_blob_oid(body) != source_prefix["git_blob_oid"]
    ):
        _fail("selector episode chunks do not reconstruct their pinned Git blob")
    return body


def _validate_campaign_against_episode_index(
    root: Path,
    campaign: Mapping[str, Any],
    episode_chunks: Sequence[Mapping[str, Any]],
    *,
    source_commit: str,
    source_observed_at: str,
    source_checkpoint: Mapping[str, Any],
    episodes_raw: bytes,
    prefix_digest_cache: dict[int, str],
    episode_group_index: Mapping[str, Any],
    episode_chunk_cache: dict[str, dict[str, Any]],
    group_node_cache: private_auth_dict.ShardedLookupCache,
) -> None:
    """Rebuild every source-derived campaign field from authenticated members."""

    source_records = campaign["source_episode_prefix"]["records"]
    if not 1 <= source_records <= source_checkpoint["episode_records"]:
        _fail("selector campaign episode prefix is outside its checkpoint")
    rows_by_ordinal, end_bytes = _episode_rows_for_ordinals(
        root,
        episode_chunks,
        ordinals={item["source_row"] for item in campaign["members"]} | {source_records},
        source_commit=source_commit,
        source_observed_at=source_observed_at,
        source_checkpoint=source_checkpoint,
        chunk_cache=episode_chunk_cache,
    )
    prefix_end = end_bytes[source_records]
    prefix_digest = prefix_digest_cache.get(source_records)
    if prefix_digest is None:
        prefix_digest = (
            source_checkpoint["episode_sha256"]
            if source_records == source_checkpoint["episode_records"]
            else _sha256(memoryview(episodes_raw)[:prefix_end])
        )
        prefix_digest_cache[source_records] = prefix_digest
    if prefix_digest != campaign["source_episode_prefix"]["prefix_sha256"]:
        _fail("selector campaign episode prefix digest drifted")
    ledger_rows: list[campaign_contract.LedgerRow] = []
    for member in campaign["members"]:
        row = rows_by_ordinal.get(member["source_row"])
        if row is None or _sha256(row.raw) != member["source_row_sha256"]:
            _fail("selector campaign member row digest drifted")
        ledger_rows.append(
            campaign_contract.LedgerRow(
                value=copy.deepcopy(row.value),
                ordinal=row.ordinal,
                raw=row.raw,
                sha256=_sha256(row.raw),
            )
        )
    ledger_rows.sort(
        key=lambda item: (
            _utc(item.value["available_at"], label="campaign member availability"),
            item.value["episode_id"],
        )
    )
    try:
        group = campaign_contract._group_from_payload(campaign["group"])
        group_parts = [str(item) for item in group]
        latest = _source_episode_group_lookup(
            root,
            episode_group_index,
            _source_episode_group_latest_key(group_parts),
            node_cache=group_node_cache,
        )
        if not latest.found:
            _fail("selector campaign group is absent from authenticated episodes")
        authenticated_members: list[dict[str, Any]] = []
        for ordinal in range(1, latest.binding["member_count"] + 1):
            member = _source_episode_group_lookup(
                root,
                episode_group_index,
                _source_episode_group_member_key(group_parts, ordinal),
                node_cache=group_node_cache,
            )
            if not member.found:
                _fail("selector campaign group member index is incomplete")
            if member.binding["source_row"] <= source_records:
                authenticated_members.append(member.binding)
        authenticated_bindings = {
            (
                item["episode_id"],
                item["source_row"],
                item["source_row_sha256"],
            )
            for item in authenticated_members
        }
        campaign_bindings = {
            (item["episode_id"], item["source_row"], item["source_row_sha256"])
            for item in campaign["members"]
        }
        if (
            len(authenticated_bindings) != len(authenticated_members)
            or authenticated_bindings != campaign_bindings
        ):
            _fail("selector campaign omits or adds an authenticated group member")
        if any(campaign_contract._group_key(item.value) != group for item in ledger_rows):
            _fail("selector campaign members do not share their declared group")
        expected = campaign_contract._campaign_payload(
            group,
            ledger_rows,
            _EpisodePrefixView(EPISODES_PATH, source_records),  # type: ignore[arg-type]
            None,
        )
        expected["source_episode_prefix"] = copy.deepcopy(
            campaign["source_episode_prefix"]
        )
    except campaign_contract.CampaignContractError as exc:
        raise SparseSelectorError(
            "selector campaign does not derive from its authenticated episodes"
        ) from exc
    for field in (
        "schema",
        "campaign_id",
        "campaign_revision_id",
        "formed_at",
        "policies",
        "group",
        "members",
        "descriptive",
        "intent",
        "source_episode_prefix",
        "disposition",
        "role",
        "evidence_phase",
        "training_eligible",
        "authority",
    ):
        if campaign[field] != expected[field]:
            _fail(f"selector campaign source-derived field drift: {field}")


def _episode_prefix_digests(
    episodes_raw: bytes,
    record_counts: Sequence[int] | set[int],
    *,
    source_checkpoint: Mapping[str, Any],
) -> dict[int, str]:
    """Hash every requested JSONL prefix in one monotone byte pass."""

    targets = sorted(set(record_counts))
    if not targets:
        return {}
    final_records = source_checkpoint["episode_records"]
    if targets[0] < 1 or targets[-1] > final_records:
        _fail("selector campaign prefix request exceeds its episode checkpoint")
    result: dict[int, str] = {}
    pending = [target for target in targets if target != final_records]
    if final_records in targets:
        result[final_records] = source_checkpoint["episode_sha256"]
    if not pending:
        return result
    digest = hashlib.sha256()
    view = memoryview(episodes_raw)
    offset = 0
    ordinal = 0
    pending_index = 0
    terminal_target = pending[-1]
    while ordinal < terminal_target:
        newline = episodes_raw.find(b"\n", offset)
        if newline < 0:
            _fail("selector episode JSONL ended before a campaign prefix")
        digest.update(view[offset : newline + 1])
        offset = newline + 1
        ordinal += 1
        if ordinal == pending[pending_index]:
            result[ordinal] = digest.hexdigest()
            pending_index += 1
            if pending_index == len(pending):
                break
    return result


def _validate_source_seed(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema",
        "seed_id",
        "candidate_id",
        "candidate_available_at",
        "source_available_at",
        "source_commit",
        "source_observed_at",
        "source_campaign_prefix",
        "source_episode_prefix",
        "source_checkpoint",
        "campaign_row_number",
        "campaign_row",
        "campaign_row_sha256",
        "final_episode_row",
        "final_episode_row_sha256",
        "episode_prefix",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        _fail("selector source seed fields are malformed")
    clean = copy.deepcopy(dict(value))
    campaign_contract.validate_campaign(clean["campaign_row"])
    campaign_contract.validate_episode(clean["final_episode_row"])
    if (
        clean["schema"] != "options.sparse_selector_source_seed/v1"
        or clean["seed_id"] != _source_seed_id(clean)
        or clean["candidate_id"] != _candidate_id(clean["campaign_row"]["campaign_id"])
        or clean["candidate_available_at"] != clean["source_observed_at"]
        or clean["authority"] != FALSE_AUTHORITY
        or clean["campaign_row_sha256"]
        != _sha256(canonical_bytes(clean["campaign_row"]))
        or clean["final_episode_row_sha256"]
        != _sha256(canonical_bytes(clean["final_episode_row"]))
        or clean["campaign_row"]["members"][-1]["source_row_sha256"]
        != clean["final_episode_row_sha256"]
        or clean["campaign_row"]["members"][-1]["episode_id"]
        != clean["final_episode_row"]["episode_id"]
        or clean["source_checkpoint"]["campaign_records"]
        != clean["source_campaign_prefix"]["records"]
        or clean["source_checkpoint"]["campaign_sha256"]
        != clean["source_campaign_prefix"]["sha256"]
        or clean["source_checkpoint"]["episode_records"]
        != clean["source_episode_prefix"]["records"]
        or clean["source_checkpoint"]["episode_sha256"]
        != clean["source_episode_prefix"]["sha256"]
    ):
        _fail("selector source seed binding drifted")
    _utc(clean["candidate_available_at"], label="source seed availability")
    _utc(clean["source_observed_at"], label="source seed observation")
    _utc(clean["source_available_at"], label="source seed source availability")
    return clean


def _source_run_id(value: Mapping[str, Any]) -> str:
    return _content_id("ossr_", value, field="run_id")


def _validate_source_run(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema",
        "run_id",
        "level",
        "source_commit",
        "source_observed_at",
        "source_checkpoint",
        "first_source_row",
        "last_source_row",
        "entry_count",
        "entries",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        _fail("selector source run fields are malformed")
    clean = copy.deepcopy(dict(value))
    entries = clean["entries"]
    if (
        clean["schema"] != "options.sparse_selector_source_run/v1"
        or clean["run_id"] != _source_run_id(clean)
        or type(clean["level"]) is not int
        or clean["level"] < 0
        or clean["authority"] != FALSE_AUTHORITY
        or not isinstance(entries, list)
        or len(entries) != clean["entry_count"]
        or len(entries) > MAX_RUN_ROWS
    ):
        _fail("selector source run binding drifted")
    _utc(clean["source_observed_at"], label="source run observation")
    keys: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {
            "candidate_available_at",
            "candidate_id",
            "source_row",
            "seed",
        }:
            _fail("selector source run entry is malformed")
        key = (entry["candidate_available_at"], entry["candidate_id"])
        _utc(key[0], label="source run candidate availability")
        if entry["candidate_id"] in seen:
            _fail("selector source run repeats a candidate")
        seen.add(entry["candidate_id"])
        keys.append(key)
        if not str(entry["seed"].get("key", "")).startswith(
            f"{SOURCE_PROJECTION_NAMESPACE}/"
        ):
            _fail("selector source run seed pointer escaped its namespace")
    if keys != sorted(keys):
        _fail("selector source run is not globally ordered")
    if len(canonical_bytes(clean)) > MAX_RUN_BYTES:
        _fail("selector source run exceeds its byte cap")
    return clean


def _make_source_run(
    *,
    level: int,
    source: SourceSnapshot,
    source_checkpoint: Mapping[str, Any],
    first_source_row: int,
    last_source_row: int,
    entries: Sequence[Mapping[str, Any]],
) -> PlannedObject:
    ordered = sorted(
        (copy.deepcopy(dict(entry)) for entry in entries),
        key=lambda entry: (entry["candidate_available_at"], entry["candidate_id"]),
    )
    value: dict[str, Any] = {
        "schema": "options.sparse_selector_source_run/v1",
        "run_id": "",
        "level": level,
        "source_commit": source.commit,
        "source_observed_at": source.observed_at,
        "source_checkpoint": copy.deepcopy(dict(source_checkpoint)),
        "first_source_row": first_source_row,
        "last_source_row": last_source_row,
        "entry_count": len(ordered),
        "entries": ordered,
        "authority": dict(FALSE_AUTHORITY),
    }
    value["run_id"] = _source_run_id(value)
    clean = _validate_source_run(value)
    return PlannedObject(
        key=f"{SOURCE_PROJECTION_NAMESPACE}/{clean['run_id']}.json", value=clean
    )


def _load_source_run(root: Path, pointer: Mapping[str, Any]) -> dict[str, Any]:
    return _validate_source_run(
        _load_pointer(root, pointer, label="selector source run")
    )


def _source_seed_from_row(
    *,
    source: SourceSnapshot,
    row: JsonlRow,
    episode_by_ordinal: Mapping[int, JsonlRow],
    episode_end_bytes: Mapping[int, int],
    campaign_prefix: Mapping[str, Any],
    episode_prefix: Mapping[str, Any],
    source_checkpoint: Mapping[str, Any],
) -> PlannedObject:
    campaign = row.value
    source_records = campaign["source_episode_prefix"]["records"]
    final_row_number = campaign["members"][-1]["source_row"]
    final_episode = episode_by_ordinal.get(final_row_number)
    if final_episode is None:
        _fail("selector source seed owner row is unavailable")
    prefix_bytes = episode_end_bytes.get(source_records)
    if type(prefix_bytes) is not int or prefix_bytes < 1:
        _fail("selector source seed episode prefix offset is unavailable")
    receipt = {
        "path": EPISODES_PATH,
        "records": source_records,
        "bytes": prefix_bytes,
        "sha256": campaign["source_episode_prefix"]["prefix_sha256"],
        "git_blob_oid": episode_prefix["git_blob_oid"],
    }
    value: dict[str, Any] = {
        "schema": "options.sparse_selector_source_seed/v1",
        "seed_id": "",
        "candidate_id": _candidate_id(campaign["campaign_id"]),
        "candidate_available_at": source.observed_at,
        "source_available_at": campaign["formed_at"],
        "source_commit": source.commit,
        "source_observed_at": source.observed_at,
        "source_campaign_prefix": copy.deepcopy(dict(campaign_prefix)),
        "source_episode_prefix": copy.deepcopy(dict(episode_prefix)),
        "source_checkpoint": copy.deepcopy(dict(source_checkpoint)),
        "campaign_row_number": row.ordinal,
        "campaign_row": copy.deepcopy(campaign),
        "campaign_row_sha256": _sha256(row.raw),
        "final_episode_row": copy.deepcopy(final_episode.value),
        "final_episode_row_sha256": _sha256(final_episode.raw),
        "episode_prefix": receipt,
        "authority": dict(FALSE_AUTHORITY),
    }
    value["seed_id"] = _source_seed_id(value)
    clean = _validate_source_seed(value)
    item = PlannedObject(
        key=f"{SOURCE_PROJECTION_NAMESPACE}/{clean['seed_id']}.json", value=clean
    )
    if len(item.body) > MAX_OBJECT_BYTES:
        _fail("selector source seed exceeds its object cap")
    return item


def _candidate_from_seed(
    seed: Mapping[str, Any],
    *,
    ordinal: int,
    previous_candidate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    clean = _validate_source_seed(seed)
    candidate = {
        "schema": "options.sparse_selector_candidate/v1",
        "candidate_id": clean["candidate_id"],
        "ordinal": ordinal,
        "previous_candidate": (
            copy.deepcopy(dict(previous_candidate))
            if previous_candidate is not None
            else None
        ),
        "campaign_id": clean["campaign_row"]["campaign_id"],
        "campaign_revision_id": clean["campaign_row"]["campaign_revision_id"],
        "campaign_row": copy.deepcopy(clean["campaign_row"]),
        "campaign_row_number": clean["campaign_row_number"],
        "campaign_row_sha256": clean["campaign_row_sha256"],
        "candidate_available_at": clean["candidate_available_at"],
        "source_available_at": clean["source_available_at"],
        "source_commit": clean["source_commit"],
        "campaign_prefix": copy.deepcopy(clean["source_campaign_prefix"]),
        "episode_prefix": copy.deepcopy(clean["episode_prefix"]),
        "source_checkpoint": copy.deepcopy(clean["source_checkpoint"]),
        "final_episode_row": copy.deepcopy(clean["final_episode_row"]),
        "final_episode_row_sha256": clean["final_episode_row_sha256"],
        "eligible_for_manifest": True,
        "digests": dict(DIGESTS),
        "authority": dict(FALSE_AUTHORITY),
    }
    return validate_runtime_object(candidate, label="selector candidate from run")


def _candidate_id(campaign_id: str) -> str:
    if not _CAMPAIGN_ID_RE.fullmatch(campaign_id):
        _fail("candidate campaign id is malformed")
    identity = canonical_bytes([RULE_ID, BENCHMARK_DIGEST, campaign_id])
    return "ossc_" + _sha256(identity)


def _candidate_from_row(
    source: SourceSnapshot,
    campaign_row: JsonlRow,
    episode_by_ordinal: Mapping[int, JsonlRow],
    *,
    campaign_prefix: Mapping[str, Any],
    episode_prefix: Mapping[str, Any],
    source_checkpoint: Mapping[str, Any],
    ordinal: int,
    previous_candidate: Mapping[str, Any] | None,
    eligible_for_manifest: bool,
) -> dict[str, Any]:
    _fail("legacy segment-local candidate admission is permanently deauthorized")
    campaign = campaign_row.value
    final_member = campaign["members"][-1]
    source_records = campaign["source_episode_prefix"]["records"]
    if (
        episode_prefix["records"] != source_records
        or episode_prefix["sha256"]
        != campaign["source_episode_prefix"]["prefix_sha256"]
    ):
        _fail("campaign episode prefix receipt drifted")
    row_number = final_member["source_row"]
    if not 1 <= row_number <= source_records:
        _fail("campaign final episode row is outside its source prefix")
    final_episode = episode_by_ordinal.get(row_number)
    if final_episode is None:
        _fail("new campaign first revision does not bind an appended episode row")
    if _sha256(final_episode.raw) != final_member["source_row_sha256"]:
        _fail("campaign final episode row digest drifted")
    episode = final_episode.value
    group = campaign["group"]
    if (
        final_member["episode_id"] != episode["episode_id"]
        or final_member["available_at"] != episode["available_at"]
        or campaign["formed_at"] != episode["available_at"]
        or group["session_date"] != episode["session_date"]
        or group["ticker"] != episode["ticker"]
        or group["right"] != episode["contract"]["right"]
        or group["expiration"] != episode["contract"]["expiration"]
        or campaign_contract.canonical_strike(group["strike"])
        != campaign_contract.canonical_strike(episode["contract"]["strike"])
        or group["strike_key"] != campaign_contract.canonical_strike(group["strike"])
    ):
        _fail("campaign final episode owner join drifted")
    candidate = {
        "schema": "options.sparse_selector_candidate/v1",
        "candidate_id": _candidate_id(campaign["campaign_id"]),
        "ordinal": ordinal,
        "previous_candidate": (
            copy.deepcopy(dict(previous_candidate))
            if previous_candidate is not None
            else None
        ),
        "campaign_id": campaign["campaign_id"],
        "campaign_revision_id": campaign["campaign_revision_id"],
        "campaign_row": copy.deepcopy(campaign),
        "campaign_row_number": campaign_row.ordinal,
        "campaign_row_sha256": _sha256(campaign_row.raw),
        "candidate_available_at": source.observed_at,
        "source_available_at": campaign["formed_at"],
        "source_commit": source.commit,
        "campaign_prefix": copy.deepcopy(dict(campaign_prefix)),
        "episode_prefix": copy.deepcopy(dict(episode_prefix)),
        "source_checkpoint": copy.deepcopy(dict(source_checkpoint)),
        "final_episode_row": copy.deepcopy(episode),
        "final_episode_row_sha256": _sha256(final_episode.raw),
        "eligible_for_manifest": eligible_for_manifest,
        "digests": dict(DIGESTS),
        "authority": dict(FALSE_AUTHORITY),
    }
    return validate_runtime_object(candidate, label="selector candidate")


def plan_new_candidates(
    root: Path,
    source: SourceSnapshot,
    campaigns: Sequence[JsonlRow],
    episodes: Sequence[JsonlRow],
    *,
    campaign_prefix: Mapping[str, Any],
    current_episode_prefix: Mapping[str, Any],
    source_checkpoint: Mapping[str, Any],
    previous_episode_prefix: Mapping[str, Any] | None,
    previous_candidate: Mapping[str, Any] | None,
    candidate_count: int,
    previous_campaign_cursor_records: int,
    candidate_index: Mapping[str, Any],
    projected_episode_receipts: Mapping[int, Mapping[str, Any]] | None = None,
) -> tuple[
    list[PlannedObject],
    list[PlannedObject],
    dict[str, Any] | None,
    int,
    int,
]:
    _fail("legacy segment-local candidate admission is permanently deauthorized")
    effective = max(
        _utc(BENCHMARK_EFFECTIVE_FREEZE_AT, label="benchmark freeze"),
        _utc(SELECTOR_EFFECTIVE_FREEZE_AT, label="selector freeze"),
    )
    observed = _utc(source.observed_at, label="source observation clock")
    episode_by_ordinal = {item.ordinal: item for item in episodes}
    previous_episode_records = (
        0 if previous_episode_prefix is None else previous_episode_prefix["records"]
    )
    episode_prefix_cache: dict[int, dict[str, Any]] = {}
    seen_campaigns: set[str] = set()
    all_new: list[PlannedObject] = []
    eligible: list[PlannedObject] = []
    tail = copy.deepcopy(dict(previous_candidate)) if previous_candidate else None
    next_count = candidate_count
    processed_campaign_records = previous_campaign_cursor_records
    for item in campaigns:
        row = item.value
        campaign_id = row["campaign_id"]
        candidate_id = _candidate_id(campaign_id)
        if campaign_id in seen_campaigns:
            processed_campaign_records = item.ordinal
            continue
        formed = _utc(row["formed_at"], label="campaign formed_at")
        final_available = _utc(
            row["members"][-1]["available_at"], label="campaign final availability"
        )
        is_eligible = (
            row["evidence_phase"] == "prospective_after_rule_freeze"
            and formed == final_available
            and formed >= effective
        )
        if not is_eligible:
            # Source cursor advancement is not candidate admission. A
            # retrospective/pre-effective revision burns no deterministic
            # candidate path; the first prospectively eligible revision does.
            processed_campaign_records = item.ordinal
            continue
        if not item.first_eligible_revision:
            # A later eligible revision is globally known not to be first. It
            # advances the source cursor but can never create another candidate.
            processed_campaign_records = item.ordinal
            continue
        if len(eligible) >= MAX_CANDIDATES_PER_MANIFEST:
            # Leave this exact first-eligible row behind the authenticated
            # campaign cursor. The next cycle rereads the immutable Git blob
            # and admits it as the first row of the next manifest segment.
            break
        key = f"candidates/{candidate_id}.json"
        membership = _candidate_index_lookup(root, candidate_index, campaign_id)
        existing_body = _read_private_file(
            _object_path(root, key), root=root, limit=MAX_OBJECT_BYTES, required=False
        )
        if membership.found:
            # This can only be a replay behind a stale source cursor. Exact
            # authenticated membership makes it idempotent; any missing or
            # conflicting deterministic cache is UNKNOWN and fails closed.
            binding = membership.binding
            if (
                not isinstance(binding, Mapping)
                or binding.get("candidate_id") != candidate_id
                or binding.get("candidate") is None
                or existing_body is None
            ):
                _fail("authenticated candidate membership lacks exact bytes")
            existing = _load_pointer(
                root, binding["candidate"], label="indexed selector candidate"
            )
            if existing["campaign_id"] != campaign_id:
                _fail("authenticated candidate membership conflicts")
            processed_campaign_records = item.ordinal
            seen_campaigns.add(campaign_id)
            continue
        if existing_body is not None:
            _fail("first eligible candidate path exists without a membership witness")
        seen_campaigns.add(campaign_id)
        if observed < formed:
            _fail("selector observed a source campaign before it was available")
        source_records = row["source_episode_prefix"]["records"]
        episode_receipt = episode_prefix_cache.get(source_records)
        if episode_receipt is None:
            projected = (
                None
                if projected_episode_receipts is None
                else projected_episode_receipts.get(source_records)
            )
            if projected is not None:
                episode_receipt = copy.deepcopy(dict(projected))
            else:
                prefix_rows = [
                    episode for episode in episodes if episode.ordinal <= source_records
                ]
                if (
                    source.episodes_raw is None
                    or not prefix_rows
                    or prefix_rows[-1].ordinal != source_records
                    or [episode.ordinal for episode in prefix_rows]
                    != list(range(1, source_records + 1))
                ):
                    _fail(
                        "campaign episode prefix is not inside the authenticated ledger"
                    )
                prefix_bytes = sum(len(episode.raw) + 1 for episode in prefix_rows)
                episode_receipt = {
                    "path": EPISODES_PATH,
                    "records": source_records,
                    "bytes": prefix_bytes,
                    "sha256": _sha256(source.episodes_raw[:prefix_bytes]),
                    "git_blob_oid": current_episode_prefix["git_blob_oid"],
                }
            if (
                episode_receipt.get("path") != EPISODES_PATH
                or episode_receipt.get("records") != source_records
                or episode_receipt.get("git_blob_oid")
                != current_episode_prefix["git_blob_oid"]
                or
                episode_receipt["sha256"]
                != row["source_episode_prefix"]["prefix_sha256"]
            ):
                _fail("campaign episode prefix digest differs from appended bytes")
            episode_prefix_cache[source_records] = episode_receipt
        next_count += 1
        candidate = _candidate_from_row(
            source,
            item,
            episode_by_ordinal,
            campaign_prefix=campaign_prefix,
            episode_prefix=episode_receipt,
            source_checkpoint=source_checkpoint,
            ordinal=next_count,
            previous_candidate=tail,
            eligible_for_manifest=is_eligible,
        )
        planned = PlannedObject(key=key, value=candidate)
        all_new.append(planned)
        tail = planned.pointer
        eligible.append(planned)
        processed_campaign_records = item.ordinal
    eligible.sort(
        key=lambda item: (
            item.value["candidate_available_at"],
            item.value["candidate_id"],
        )
    )
    return all_new, eligible, tail, next_count, processed_campaign_records


_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)


class _PrivateDirectoryMissing(SparseSelectorError):
    pass


@dataclass(frozen=True)
class _SelectorLane:
    root: Path
    descriptors: tuple[int, ...]
    bindings: tuple[tuple[int, str, int, int], ...]

    @property
    def root_fd(self) -> int:
        return self.descriptors[-1]


@dataclass
class _StagedWrite:
    parent_fd: int
    parent_identity: tuple[int, int]
    temporary_name: str
    target_name: str
    closed: bool = False


_ACTIVE_SELECTOR_LANE: ContextVar[_SelectorLane | None] = ContextVar(
    "options_sparse_selector_lane", default=None
)


def _absolute_private_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(path.expanduser()))
    if not absolute.is_absolute() or absolute.anchor != "/":
        _fail("selector private path must be absolute")
    return absolute


def _validate_directory_metadata(metadata: os.stat_result, *, private: bool) -> None:
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("selector private directory cannot follow a symlink")
    if private and (
        stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.getuid()
    ):
        _fail("selector private root must be caller-owned 0700")


def _open_directory_component(
    parent_fd: int,
    name: str,
    *,
    create: bool,
    private: bool,
    label: str,
) -> int:
    if name in {"", ".", ".."} or "/" in name or "\\" in name:
        _fail("selector private path component is unsafe")
    created = False
    try:
        checked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        if not create:
            raise _PrivateDirectoryMissing(
                f"selector private directory is missing: {label}"
            ) from None
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
            created = True
        except FileExistsError:
            pass
        try:
            checked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise SparseSelectorError(
                f"selector private directory vanished during create: {label}"
            ) from exc
    _validate_directory_metadata(checked, private=private or created)
    try:
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise SparseSelectorError(
            f"selector private directory cannot be opened safely: {label}"
        ) from exc
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino) != (checked.st_dev, checked.st_ino):
        os.close(descriptor)
        _fail(f"selector private directory changed during open: {label}")
    _validate_directory_metadata(opened, private=private or created)
    return descriptor


@contextmanager
def _open_selector_lane(root: Path, *, create: bool) -> Iterator[_SelectorLane]:
    root = _absolute_private_path(root)
    if root == Path("/") or root == Path.home().resolve():
        _fail("selector private root is too broad")
    repository = ROOT.resolve()
    if root == repository or repository in root.parents:
        _fail("selector private root cannot be inside the repository")
    descriptors: list[int] = []
    bindings: list[tuple[int, str, int, int]] = []
    try:
        anchor = os.open("/", _DIRECTORY_FLAGS)
        descriptors.append(anchor)
        current = anchor
        rendered: list[str] = []
        for index, part in enumerate(root.parts[1:]):
            rendered.append(part)
            child = _open_directory_component(
                current,
                part,
                create=create,
                private=index == len(root.parts[1:]) - 1,
                label="/" + "/".join(rendered),
            )
            metadata = os.fstat(child)
            bindings.append((current, part, metadata.st_dev, metadata.st_ino))
            descriptors.append(child)
            current = child
        lane = _SelectorLane(root, tuple(descriptors), tuple(bindings))
        _assert_lane_identity(lane)
        yield lane
        _assert_lane_identity(lane)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _assert_lane_identity(lane: _SelectorLane) -> None:
    for parent_fd, name, device, inode in lane.bindings:
        try:
            bound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise SparseSelectorError(
                "selector private root was renamed during transaction"
            ) from exc
        if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (
            device,
            inode,
        ):
            _fail("selector private root or ancestor was rebound during transaction")
    root_metadata = os.fstat(lane.root_fd)
    _validate_directory_metadata(root_metadata, private=True)


@contextmanager
def _selector_lane(root: Path, *, create: bool) -> Iterator[_SelectorLane]:
    root = _absolute_private_path(root)
    active = _ACTIVE_SELECTOR_LANE.get()
    if active is not None:
        if active.root != root:
            _fail("selector active lane is bound to another private root")
        _assert_lane_identity(active)
        yield active
        _assert_lane_identity(active)
        return
    with _open_selector_lane(root, create=create) as lane:
        yield lane


@contextmanager
def _open_private_directory(
    root: Path, path: Path, *, create: bool
) -> Iterator[tuple[_SelectorLane, int]]:
    root = _absolute_private_path(root)
    path = _absolute_private_path(path)
    if path != root and root not in path.parents:
        _fail("selector private directory escaped its root")
    relative = path.relative_to(root)
    with _selector_lane(root, create=create) as lane:
        descriptors: list[int] = []
        bindings: list[tuple[int, str, int, int]] = []
        current = os.dup(lane.root_fd)
        descriptors.append(current)
        try:
            for part in relative.parts:
                child = _open_directory_component(
                    current,
                    part,
                    create=create,
                    private=True,
                    label=str(relative),
                )
                metadata = os.fstat(child)
                bindings.append((current, part, metadata.st_dev, metadata.st_ino))
                descriptors.append(child)
                current = child
            for parent_fd, name, device, inode in bindings:
                bound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (
                    device,
                    inode,
                ):
                    _fail("selector private namespace changed during secure open")
            yield lane, current
            _assert_lane_identity(lane)
            for parent_fd, name, device, inode in bindings:
                bound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (
                    device,
                    inode,
                ):
                    _fail("selector private namespace was rebound during operation")
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)


@contextmanager
def _open_private_parent(
    root: Path, path: Path, *, create: bool
) -> Iterator[tuple[_SelectorLane, int, str]]:
    if not path.name or path.name in {".", ".."}:
        _fail("selector private file name is unsafe")
    with _open_private_directory(root, path.parent, create=create) as (lane, parent_fd):
        yield lane, parent_fd, path.name


def validate_private_root(path: Path, *, create: bool) -> Path:
    root = _absolute_private_path(path)
    with _open_selector_lane(root, create=create):
        pass
    return root


def _require_private_directory(path: Path, *, root: Path, create: bool) -> Path:
    with _open_private_directory(root, path, create=create):
        pass
    return path


def _read_regular_at(
    parent_fd: int, name: str, *, limit: int, required: bool, label: str
) -> bytes | None:
    try:
        checked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        if required:
            _fail(f"{label} is missing: {name}")
        return None
    if (
        stat.S_ISLNK(checked.st_mode)
        or not stat.S_ISREG(checked.st_mode)
        or checked.st_nlink != 1
        or stat.S_IMODE(checked.st_mode) != 0o600
        or checked.st_uid != os.getuid()
        or checked.st_size > limit
    ):
        if stat.S_ISLNK(checked.st_mode):
            _fail(f"{label} is a symlink: {name}")
        _fail(f"{label} metadata is unsafe: {name}")
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise SparseSelectorError(f"{label} cannot be opened safely") from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (checked.st_dev, checked.st_ino):
            _fail(f"{label} changed during secure open")
        body = bytearray()
        while len(body) <= limit:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        after = os.fstat(descriptor)
        rebound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            len(body) > limit
            or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
            or stat.S_ISLNK(rebound.st_mode)
            or (rebound.st_dev, rebound.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            _fail(f"{label} changed during secure read")
        return bytes(body)
    finally:
        os.close(descriptor)


def _read_private_file(
    path: Path, *, root: Path, limit: int, required: bool
) -> bytes | None:
    try:
        with _open_private_parent(root, path, create=False) as (_lane, parent_fd, name):
            return _read_regular_at(
                parent_fd,
                name,
                limit=limit,
                required=required,
                label="selector private file",
            )
    except _PrivateDirectoryMissing:
        if required:
            _fail(f"selector private file is missing: {path.name}")
        return None


def _fsync_directory(path: Path) -> None:
    active = _ACTIVE_SELECTOR_LANE.get()
    if active is not None and (path == active.root or active.root in path.parents):
        with _open_private_directory(active.root, path, create=False) as (_lane, descriptor):
            os.fsync(descriptor)
        return
    absolute = _absolute_private_path(path)
    descriptors: list[int] = []
    try:
        current = os.open("/", _DIRECTORY_FLAGS)
        descriptors.append(current)
        for part in absolute.parts[1:]:
            current = _open_directory_component(
                current,
                part,
                create=False,
                private=False,
                label=str(absolute),
            )
            descriptors.append(current)
        os.fsync(current)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _write_all(descriptor: int, body: bytes) -> None:
    view = memoryview(body)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            _fail("selector private write was short")
        view = view[written:]


def _stage_atomic_write(
    path: Path, body: bytes, *, root: Path, limit: int
) -> _StagedWrite:
    if len(body) > limit:
        _fail(f"selector atomic write exceeds cap: {path.name}")
    with _open_private_parent(root, path, create=True) as (lane, parent_fd, name):
        _read_regular_at(
            parent_fd,
            name,
            limit=limit,
            required=False,
            label="selector atomic target",
        )
        temporary_name = f".{name}.{os.getpid()}.{uuid4().hex}.tmp"
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        try:
            _write_all(descriptor, body)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _assert_lane_identity(lane)
        held_parent = os.dup(parent_fd)
        metadata = os.fstat(held_parent)
        return _StagedWrite(
            held_parent,
            (metadata.st_dev, metadata.st_ino),
            temporary_name,
            name,
        )


def _discard_staged_write(staged: _StagedWrite) -> None:
    if staged.closed:
        return
    try:
        try:
            os.unlink(staged.temporary_name, dir_fd=staged.parent_fd)
            os.fsync(staged.parent_fd)
        except FileNotFoundError:
            pass
    finally:
        os.close(staged.parent_fd)
        staged.closed = True


def _install_staged_write(
    path: Path, temporary: _StagedWrite, body: bytes, *, root: Path, limit: int
) -> None:
    del root
    if temporary.closed or path.name != temporary.target_name:
        _fail("selector staged write target drifted")
    metadata = os.fstat(temporary.parent_fd)
    if (metadata.st_dev, metadata.st_ino) != temporary.parent_identity:
        _fail("selector staged parent identity drifted")
    try:
        os.replace(
            temporary.temporary_name,
            temporary.target_name,
            src_dir_fd=temporary.parent_fd,
            dst_dir_fd=temporary.parent_fd,
        )
        os.fsync(temporary.parent_fd)
        readback = _read_regular_at(
            temporary.parent_fd,
            temporary.target_name,
            limit=limit,
            required=True,
            label="selector atomic target",
        )
        if readback != body:
            _fail("selector atomic write readback mismatch")
    finally:
        _discard_staged_write(temporary)


def _atomic_write(path: Path, body: bytes, *, root: Path, limit: int) -> None:
    temporary = _stage_atomic_write(path, body, root=root, limit=limit)
    _install_staged_write(path, temporary, body, root=root, limit=limit)


def _reprove_exact_private_file(
    path: Path,
    body: bytes,
    *,
    root: Path,
    limit: int,
    label: str,
) -> None:
    if len(body) > limit:
        _fail(f"{label} exact bytes are outside their bound")
    with _open_private_parent(root, path, create=False) as (lane, parent_fd, name):
        observed = _read_regular_at(
            parent_fd, name, limit=limit, required=True, label=label
        )
        if observed != body:
            _fail(f"{label} conflicts with existing bytes")
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        try:
            opened = os.fstat(descriptor)
            os.fsync(descriptor)
            rebound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(rebound.st_mode) or (rebound.st_dev, rebound.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                _fail(f"{label} was rebound during durability reproof")
        finally:
            os.close(descriptor)
        os.fsync(parent_fd)
        _assert_lane_identity(lane)


def _write_immutable(
    path: Path, body: bytes, *, root: Path, sync_parent: bool = True
) -> None:
    if not body or len(body) > MAX_OBJECT_BYTES:
        _fail("selector immutable object exceeds its bound")
    with _open_private_parent(root, path, create=True) as (lane, parent_fd, name):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(name, flags, 0o600, dir_fd=parent_fd)
        except FileExistsError:
            existing = _read_regular_at(
                parent_fd,
                name,
                limit=MAX_OBJECT_BYTES,
                required=True,
                label="selector immutable object",
            )
            if existing != body:
                _fail("selector immutable object conflicts with existing bytes")
            if sync_parent:
                os.fsync(parent_fd)
            _assert_lane_identity(lane)
            return
        try:
            _write_all(descriptor, body)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if sync_parent:
            os.fsync(parent_fd)
        if _read_regular_at(
            parent_fd,
            name,
            limit=MAX_OBJECT_BYTES,
            required=True,
            label="selector immutable object",
        ) != body:
            _fail("selector immutable object readback mismatch")
        _assert_lane_identity(lane)


def _sync_immutable_parent(path: Path, *, root: Path) -> None:
    """Durably publish a batch of fsynced immutable files before HEAD."""

    with _open_private_parent(root, path, create=False) as (lane, parent_fd, _name):
        os.fsync(parent_fd)
        _assert_lane_identity(lane)


def _assert_store_lock_identity(lane: _SelectorLane, descriptor: int) -> None:
    _assert_lane_identity(lane)
    opened = os.fstat(descriptor)
    try:
        bound = os.stat(LOCK_FILE, dir_fd=lane.root_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise SparseSelectorError("selector store lock was renamed") from exc
    for metadata in (opened, bound):
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _fail("selector store lock metadata is unsafe")
    if (opened.st_dev, opened.st_ino) != (bound.st_dev, bound.st_ino):
        _fail("selector store lock path no longer names the locked inode")


@contextmanager
def _store_lock(root: Path) -> Iterator[None]:
    root = _absolute_private_path(root)
    if _ACTIVE_SELECTOR_LANE.get() is not None:
        _fail("selector store lock cannot be nested")
    with _open_selector_lane(root, create=True) as lane:
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(LOCK_FILE, flags, 0o600, dir_fd=lane.root_fd)
        except OSError as exc:
            raise SparseSelectorError(
                "selector store lock cannot be opened safely"
            ) from exc
        locked = False
        token = None
        try:
            _assert_store_lock_identity(lane, descriptor)
            os.fsync(descriptor)
            os.fsync(lane.root_fd)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            locked = True
            _assert_store_lock_identity(lane, descriptor)
            token = _ACTIVE_SELECTOR_LANE.set(lane)
            yield
            _assert_store_lock_identity(lane, descriptor)
        finally:
            if token is not None:
                _ACTIVE_SELECTOR_LANE.reset(token)
            try:
                if locked:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _object_path(root: Path, key: str) -> Path:
    parts = key.split("/")
    if (
        len(parts) != 2
        or parts[0]
        not in {
            "candidates",
            "manifests",
            "decisions",
            "cycles",
            "evidence",
            INTENT_SEAL_NAMESPACE,
            HANDOFF_QUEUE_NAMESPACE,
            SOURCE_PROJECTION_NAMESPACE,
            private_auth_dict.NAMESPACE,
        }
        or not re.fullmatch(r"[A-Za-z0-9_.-]+\.json", parts[1])
    ):
        _fail("selector object key is malformed")
    return root.joinpath(*parts)


def _pointer_for(key: str, value: Mapping[str, Any]) -> dict[str, Any]:
    return PlannedObject(key=key, value=dict(value)).pointer


def _load_pointer(
    root: Path, pointer: Mapping[str, Any], *, label: str
) -> dict[str, Any]:
    if not isinstance(pointer, Mapping) or set(pointer) != {
        "id",
        "key",
        "sha256",
        "bytes",
    }:
        _fail(f"{label} pointer is malformed")
    path = _object_path(root, str(pointer["key"]))
    body = _read_private_file(path, root=root, limit=MAX_OBJECT_BYTES, required=True)
    assert body is not None
    if len(body) != pointer["bytes"] or _sha256(body) != pointer["sha256"]:
        _fail(f"{label} pointer bytes drifted")
    value = strict_json(body, label=label)
    if not isinstance(value, dict) or canonical_bytes(value) != body:
        _fail(f"{label} object is not canonical")
    if object_identity(value) != pointer["id"]:
        _fail(f"{label} object identity drifted")
    if value.get("schema") in RUNTIME_OBJECT_SCHEMAS:
        validate_runtime_object(value, label=label)
    return value


def _load_candidate_index_node(
    root: Path, pointer: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        value = _load_pointer(root, pointer, label="selector candidate index node")
        return private_auth_dict.validate_node(value, domain=CANDIDATE_INDEX_DOMAIN)
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc


def _candidate_index_key(campaign_id: str) -> list[str]:
    return ["selector_candidate", RULE_ID, campaign_id]


def _candidate_index_lookup(
    root: Path,
    index: Mapping[str, Any],
    campaign_id: str,
    *,
    node_cache: private_auth_dict.ShardedLookupCache | None = None,
) -> private_auth_dict.Lookup:
    try:
        return private_auth_dict.sharded_lookup(
            index,
            _candidate_index_key(campaign_id),
            domain=CANDIDATE_INDEX_DOMAIN,
            load_node=lambda pointer: _load_candidate_index_node(root, pointer),
            cache=node_cache,
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc


def _load_source_candidate_index_node(
    root: Path, pointer: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        value = _load_pointer(
            root, pointer, label="selector source candidate index node"
        )
        return private_auth_dict.validate_node(
            value, domain=SOURCE_CANDIDATE_INDEX_DOMAIN
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc


def _source_candidate_index_key(campaign_id: str) -> list[str]:
    return ["selector_source_candidate", RULE_ID, campaign_id]


def _source_candidate_index_lookup(
    root: Path,
    index: Mapping[str, Any],
    campaign_id: str,
    *,
    node_cache: private_auth_dict.ShardedLookupCache | None = None,
) -> private_auth_dict.Lookup:
    try:
        return private_auth_dict.sharded_lookup(
            index,
            _source_candidate_index_key(campaign_id),
            domain=SOURCE_CANDIDATE_INDEX_DOMAIN,
            load_node=lambda pointer: _load_source_candidate_index_node(root, pointer),
            cache=node_cache,
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc


def _load_source_campaign_history_node(
    root: Path, pointer: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        value = _load_pointer(
            root, pointer, label="selector source campaign history node"
        )
        return private_auth_dict.validate_node(
            value, domain=SOURCE_CAMPAIGN_HISTORY_DOMAIN
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc


def _source_campaign_revision_key(revision_id: str) -> list[str]:
    return ["selector_source_campaign_revision", RULE_ID, revision_id]


def _source_campaign_latest_key(campaign_id: str, revision_number: int) -> list[str]:
    return [
        "selector_source_campaign_revision_number",
        RULE_ID,
        campaign_id,
        str(revision_number),
    ]


def _source_campaign_history_lookup(
    root: Path,
    index: Mapping[str, Any],
    key: Sequence[str],
    *,
    node_cache: private_auth_dict.ShardedLookupCache,
) -> private_auth_dict.Lookup:
    try:
        return private_auth_dict.sharded_lookup(
            index,
            list(key),
            domain=SOURCE_CAMPAIGN_HISTORY_DOMAIN,
            load_node=lambda pointer: _load_source_campaign_history_node(root, pointer),
            cache=node_cache,
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc


def _load_source_episode_identity_node(
    root: Path, pointer: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        value = _load_pointer(
            root, pointer, label="selector source episode identity node"
        )
        return private_auth_dict.validate_node(
            value, domain=SOURCE_EPISODE_IDENTITY_DOMAIN
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc


def _source_episode_id_key(episode_id: str) -> list[str]:
    return ["selector_source_episode_id", RULE_ID, episode_id]


def _source_episode_event_key(source: str, source_event_id: str) -> list[str]:
    return ["selector_source_episode_event", RULE_ID, source, source_event_id]


def _load_source_episode_group_node(
    root: Path, pointer: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        value = _load_pointer(
            root, pointer, label="selector source episode group node"
        )
        return private_auth_dict.validate_node(
            value, domain=SOURCE_EPISODE_GROUP_DOMAIN
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc


def _source_episode_group_parts(row: Mapping[str, Any]) -> list[str]:
    group = campaign_contract._group_key(dict(row))
    return [str(item) for item in group]


def _source_episode_group_latest_key(group: Sequence[str]) -> list[str]:
    return ["selector_source_episode_group_latest", RULE_ID, *group]


def _source_episode_group_member_key(
    group: Sequence[str], member_ordinal: int
) -> list[str]:
    return [
        "selector_source_episode_group_member",
        RULE_ID,
        *group,
        str(member_ordinal),
    ]


def _source_episode_group_lookup(
    root: Path,
    index: Mapping[str, Any],
    key: Sequence[str],
    *,
    node_cache: private_auth_dict.ShardedLookupCache,
) -> private_auth_dict.Lookup:
    try:
        return private_auth_dict.sharded_lookup(
            index,
            list(key),
            domain=SOURCE_EPISODE_GROUP_DOMAIN,
            load_node=lambda pointer: _load_source_episode_group_node(root, pointer),
            cache=node_cache,
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc


def _load_head(root: Path) -> dict[str, Any] | None:
    body = _read_private_file(
        root / HEAD_FILE, root=root, limit=MAX_HEAD_BYTES, required=False
    )
    if body is None:
        with _selector_lane(root, create=False) as lane:
            for legacy_name in LEGACY_SELECTOR_FILES:
                try:
                    os.stat(
                        legacy_name,
                        dir_fd=lane.root_fd,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    continue
                _fail(
                    "selector legacy evidence exists without a reviewed migration receipt"
                )
        return None
    value = strict_json(body, label="selector HEAD")
    if not isinstance(value, dict) or canonical_bytes(value) != body:
        _fail("selector HEAD is not canonical")
    clean = validate_runtime_object(value, label="selector HEAD")
    expected = _content_id("ossh_", clean, field="head_id")
    if clean["head_id"] != expected:
        _fail("selector HEAD content identity drifted")
    return clean


def authenticate_handoff_head(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    """Authenticate only HEAD, its tail queue item, and its exact last cycle."""

    head = _load_head(root)
    if head is None:
        return None
    if head["cycle_count"] == 0:
        _fail("selector HEAD has no handoff cycle yet")
    if head["handoff_queue_count"] != head["cycle_count"]:
        _fail("selector HEAD cycle counters drifted")
    cycle = _load_pointer(root, head["last_cycle"], label="last selector cycle")
    queue_item = _load_pointer(
        root, head["last_handoff_queue"], label="last selector handoff queue item"
    )
    if (
        cycle["ordinal"] != head["cycle_count"]
        or queue_item["ordinal"] != head["handoff_queue_count"]
        or queue_item["selector_cycle"] != head["last_cycle"]
        or queue_item["previous_cycle"] != cycle["previous_cycle"]
        or head["last_handoff_queue"]["key"]
        != _handoff_queue_key(head["handoff_queue_count"])
        or queue_item["runtime_armed"] is not True
        or cycle["runtime_armed"] is not True
        or cycle["last_candidate"] != head["last_candidate"]
        or cycle["candidate_count_after"] != head["candidate_count"]
        or cycle["last_decision"] != head["last_decision"]
        or cycle["decision_count_after"] != head["decision_count"]
    ):
        _fail("selector HEAD does not authenticate its last cycle and queue item")
    return head, queue_item, cycle


def _walk_immutable_chain(
    root: Path,
    *,
    tail: Mapping[str, Any] | None,
    count: int,
    schema: str,
    previous_field: str,
    namespace: str,
    label: str,
) -> list[dict[str, Any]]:
    if (count == 0) != (tail is None):
        _fail(f"selector {label} tail/count alignment drifted")
    pointer = copy.deepcopy(dict(tail)) if tail is not None else None
    newest_first: list[dict[str, Any]] = []
    expected = count
    while expected:
        assert pointer is not None
        item = _load_pointer(root, pointer, label=f"selector {label} {expected}")
        if (
            item.get("schema") != schema
            or item.get("ordinal") != expected
            or not str(pointer["key"]).startswith(f"{namespace}/")
        ):
            _fail(f"selector {label} chain ordinal or namespace drifted")
        newest_first.append(item)
        predecessor = item.get(previous_field)
        if (expected == 1) != (predecessor is None):
            _fail(f"selector {label} chain ended at the wrong ordinal")
        pointer = (
            copy.deepcopy(dict(predecessor)) if predecessor is not None else None
        )
        expected -= 1
    if pointer is not None:
        _fail(f"selector {label} chain exceeded its authenticated count")
    newest_first.reverse()
    return newest_first


def _walk_candidate_chain_receipts(
    root: Path,
    *,
    tail: Mapping[str, Any] | None,
    count: int,
) -> list[dict[str, Any]]:
    """Authenticate the candidate chain while retaining only compact receipts."""

    pointer = copy.deepcopy(dict(tail)) if tail is not None else None
    newest_first: list[dict[str, Any]] = []
    expected = count
    while expected:
        assert pointer is not None
        candidate = _load_pointer(root, pointer, label=f"selector candidate {expected}")
        if (
            candidate.get("schema") != "options.sparse_selector_candidate/v1"
            or candidate.get("ordinal") != expected
            or pointer["key"] != f"candidates/{candidate['candidate_id']}.json"
        ):
            _fail("selector candidate chain ordinal or namespace drifted")
        newest_first.append(
            {
                "ordinal": expected,
                "candidate_id": candidate["candidate_id"],
                "candidate_available_at": candidate["candidate_available_at"],
                "pointer": copy.deepcopy(pointer),
            }
        )
        predecessor = candidate.get("previous_candidate")
        if (expected == 1) != (predecessor is None):
            _fail("selector candidate chain ended at the wrong ordinal")
        pointer = copy.deepcopy(dict(predecessor)) if predecessor is not None else None
        expected -= 1
    if pointer is not None:
        _fail("selector candidate chain exceeded its authenticated count")
    newest_first.reverse()
    order = [
        (item["candidate_available_at"], item["candidate_id"])
        for item in newest_first
    ]
    if order != sorted(order):
        _fail("selector candidate chain is not globally ordered")
    return newest_first


def _authenticate_selector_state(
    root: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any] | None,
    dict[str, Any] | None,
] | None:
    raw_head = _load_head(root)
    if raw_head is None:
        return None
    if raw_head["cycle_count"] == 0:
        if any(
            raw_head[field] is not None
            for field in ("pending_manifest", "last_cycle", "last_handoff_queue")
        ):
            _fail("audit-only selector HEAD carries runtime objects")
        # HEAD validation authenticates all content-addressed roots, cursor
        # cardinalities, counts, and immutable tails.  Full historical object
        # traversal is intentionally reserved for authenticate_store(); doing
        # it after every bounded source commit turns crash recovery quadratic.
        return raw_head, None, None, None, None
    handoff = authenticate_handoff_head(root)
    assert handoff is not None
    head, _queue_item, cycle = handoff
    pending = (
        None
        if head["pending_manifest"] is None
        else _load_pointer(root, head["pending_manifest"], label="pending manifest")
    )
    last_candidate = (
        None
        if head["last_candidate"] is None
        else _load_pointer(root, head["last_candidate"], label="last selector candidate")
    )
    last_decision = (
        None
        if head["last_decision"] is None
        else _load_pointer(root, head["last_decision"], label="last selector decision")
    )
    if (
        cycle["next_manifest"] != head["pending_manifest"]
        or (
            last_candidate is not None
            and last_candidate["ordinal"] != head["candidate_count"]
        )
        or (
            last_decision is not None
            and last_decision["ordinal"] != head["decision_count"]
        )
    ):
        _fail("selector HEAD, state tails, cycle, and pending manifest drifted")
    if last_candidate is not None:
        membership = _candidate_index_lookup(
            root, head["candidate_index"], last_candidate["campaign_id"]
        )
        if membership.binding != {
            "campaign_id": last_candidate["campaign_id"],
            "candidate_id": last_candidate["candidate_id"],
            "candidate": head["last_candidate"],
        }:
            _fail("selector HEAD candidate index does not bind its tail")
    return head, pending, cycle, last_candidate, last_decision


def authenticate_store(
    root: Path,
    *,
    evidence_inputs: EvidenceInputs | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], bytes]:
    state = _authenticate_selector_state(root)
    if state is None:
        return None, [], b""
    head, pending, cycle, _last_candidate, _last_decision = state
    if head["cycle_count"] == 0:
        for reference in head["source_episode_chunks"]:
            _load_episode_chunk(
                root,
                reference,
                source_commit=head["source_commit"],
                source_observed_at=head["source_observed_at"],
                source_checkpoint=head["source_checkpoint"],
            )
        total_ready = 0
        first_unconsumed: Mapping[str, Any] | None = None
        for pointer, cursor in zip(
            head["source_run_manifests"], head["source_run_cursors"], strict=True
        ):
            run = _load_source_run(root, pointer)
            if (
                run["source_commit"] != head["source_commit"]
                or run["source_checkpoint"] != head["source_checkpoint"]
                or cursor > run["entry_count"]
            ):
                _fail("selector audit run escaped its source epoch")
            if cursor < run["entry_count"] and first_unconsumed is None:
                first_unconsumed = pointer
            total_ready += run["entry_count"]
        if head["source_phase"] in {"READY", "DRAINED"} and (
            head["source_ready_count"] != total_ready
            or head["source_ready_cursor"] != sum(head["source_run_cursors"])
            or head["source_ready_run"] != first_unconsumed
        ):
            _fail("selector ready run cursor drifted")
        return head, [], b""
    assert cycle is not None
    candidate_receipts = _walk_candidate_chain_receipts(
        root,
        tail=head["last_candidate"],
        count=head["candidate_count"],
    )
    decisions = _walk_immutable_chain(
        root,
        tail=head["last_decision"],
        count=head["decision_count"],
        schema="options.sparse_selector_decision/v1",
        previous_field="previous_decision",
        namespace="decisions",
        label="decision",
    )
    candidates_by_id = {
        receipt["candidate_id"]: receipt["pointer"] for receipt in candidate_receipts
    }
    if len(candidates_by_id) != len(candidate_receipts):
        _fail("selector candidate chain repeats an identity")

    if pending is not None:
        pending_ids: list[str] = []
        pending_order: list[tuple[str, str]] = []
        for pointer in pending["candidates"]:
            candidate = _load_pointer(root, pointer, label="pending candidate")
            candidate_id = candidate["candidate_id"]
            chained_pointer = candidates_by_id.get(candidate_id)
            if (
                chained_pointer is None
                or chained_pointer != pointer
                or candidate["eligible_for_manifest"] is not True
            ):
                _fail("pending manifest candidate is not the frozen chained object")
            pending_ids.append(candidate_id)
            pending_order.append(
                (candidate["candidate_available_at"], candidate["candidate_id"])
            )
        if (
            len(pending_ids) != pending["candidate_count"]
            or len(set(pending_ids)) != len(pending_ids)
            or pending_order != sorted(pending_order)
        ):
            _fail("pending manifest identity or order drifted")

    proposed_by_session: dict[str, list[int]] = {}
    previous_available: datetime | None = None
    by_decision_id: dict[str, dict[str, Any]] = {}
    w1a_cache: dict[str, _W1APublication] = {}
    w1a_seen: set[str] = set()
    reconstructed_w1a_high_water: Mapping[str, Any] | None = None
    for decision in decisions:
        candidate_pointer = decision["candidate"]
        candidate = _load_pointer(root, candidate_pointer, label="decided candidate")
        candidate_id = candidate["candidate_id"]
        chained_pointer = candidates_by_id.get(candidate_id)
        if (
            chained_pointer is None
            or chained_pointer != candidate_pointer
        ):
            _fail("decision candidate is not the frozen chained object")
        if decision["evidence"]["options"] != candidate_pointer:
            _fail("selector decision options evidence drifted")
        _validate_decision_evidence_objects(
            root,
            decision,
            candidate=candidate,
            evidence_inputs=evidence_inputs or EvidenceInputs(),
            w1a_cache=w1a_cache,
        )
        generation = _load_pointer(
            root,
            decision["evidence"]["generation"],
            label="authenticated selector evidence generation",
        )
        source_pointer = generation["w1a_source_receipt"]
        if source_pointer is not None and source_pointer["key"] not in w1a_seen:
            source_receipt = _load_pointer(
                root,
                source_pointer,
                label="authenticated selector W1A source receipt",
            )
            reconstructed_w1a_high_water = _advance_w1a_high_water(
                reconstructed_w1a_high_water, source_receipt
            )
            w1a_seen.add(source_pointer["key"])
        available = _utc(
            decision["decision_available_at"], label="decision chain availability"
        )
        if previous_available is not None and available < previous_available:
            _fail("selector decision ledger clock moved backward")
        previous_available = available
        if decision["action"] == "propose":
            session = decision["decision_nyse_session_date"]
            proposed_by_session.setdefault(session, []).append(
                decision["proposal_ordinal"]
            )
        by_decision_id[decision["decision_id"]] = decision

    for ordinals in proposed_by_session.values():
        if (
            ordinals != list(range(1, len(ordinals) + 1))
            or len(ordinals) > PROPOSAL_CAP
        ):
            _fail("selector proposal ordinals or per-session cap drifted")
    if reconstructed_w1a_high_water != head["w1a_publication_high_water"]:
        _fail("selector W1A publication high-water does not reconcile")
    if pending is None and head["source_phase"] == "DRAINED":
        candidate_pointers = [receipt["pointer"] for receipt in candidate_receipts]
        if (
            head["decision_count"] != head["candidate_count"]
            or [decision["candidate"] for decision in decisions]
            != candidate_pointers
        ):
            _fail("selector drained decision ledger is not one-to-one with candidates")
    cycle_decisions = [by_decision_id.get(item) for item in cycle["decision_ids"]]
    if any(item is None for item in cycle_decisions):
        _fail("last selector cycle points to an unknown decision")
    if cycle["decision_count"]:
        if decisions[-cycle["decision_count"] :] != cycle_decisions:
            _fail("last selector cycle does not bind the decision-chain suffix")
    elif cycle_decisions:
        _fail("zero-decision cycle carries decision identities")
    if cycle["decision_pointers"] != [
        _pointer_for(f"decisions/{decision['decision_id']}.json", decision)
        for decision in cycle_decisions
    ]:
        _fail("last selector cycle decision pointers drifted")
    settled_pointer = cycle["settled_manifest"]
    if settled_pointer is None:
        if cycle_decisions:
            _fail("selector initial cycle settlement drifted")
    else:
        settled = _load_pointer(root, settled_pointer, label="settled manifest")
        if (
            len(cycle_decisions) != settled["candidate_count"]
            or any(
                decision["manifest_id"] != settled["manifest_id"]
                for decision in cycle_decisions
            )
            or [decision["candidate"] for decision in cycle_decisions]
            != settled["candidates"]
        ):
            _fail("selector cycle did not reconcile its settled manifest exactly")
    return head, decisions, b""


def _clean_handoff_cursor_pointer(
    value: Mapping[str, Any] | None,
    *,
    identity: str | None,
    prefix: str,
    key: str,
    label: str,
) -> dict[str, Any]:
    if (
        not isinstance(identity, str)
        or not re.fullmatch(rf"{prefix}_[a-f0-9]{{64}}", identity)
        or not isinstance(value, Mapping)
        or set(value) != {"id", "key", "sha256", "bytes"}
        or value.get("id") != identity
        or value.get("key") != key
        or not isinstance(value.get("sha256"), str)
        or not _SHA256_RE.fullmatch(str(value["sha256"]))
        or type(value.get("bytes")) is not int
        or not 0 < value["bytes"] <= MAX_OBJECT_BYTES
    ):
        _fail(f"selector handoff cursor {label} is malformed")
    return copy.deepcopy(dict(value))


def authenticated_pending_handoff_queue(
    root: Path,
    head: Mapping[str, Any],
    *,
    after_ordinal: int,
    after_cycle_id: str | None,
    after_cycle_pointer: Mapping[str, Any] | None,
    after_queue_item_id: str | None,
    after_queue_item_pointer: Mapping[str, Any] | None,
    max_records: int = MAX_HANDOFF_IMPORT_RECORDS,
) -> list[dict[str, Any]]:
    """Return a bounded authenticated oldest-first prefix after ``cursor``.

    The immutable queue nodes carry binary-lifting ancestor pointers.  Start at
    the authenticated HEAD tail, jump to ``cursor + max_records`` in logarithmic
    reads, then walk only that bounded prefix back to the exact cursor.  Queue
    history therefore cannot strand the importer behind a lifetime byte cap.
    """

    clean_head = validate_runtime_object(head, label="selector handoff-queue HEAD")
    authenticated_tail = authenticate_handoff_head(root)
    if authenticated_tail is None or authenticated_tail[0] != clean_head:
        _fail("selector handoff queue requested for a noncurrent HEAD")
    _current_head, tail_item, tail_cycle = authenticated_tail
    if (
        type(after_ordinal) is not int
        or not 0 <= after_ordinal <= clean_head["handoff_queue_count"]
    ):
        _fail("selector handoff cursor ordinal is malformed")
    if (
        type(max_records) is not int
        or not 1 <= max_records <= MAX_HANDOFF_IMPORT_RECORDS
    ):
        _fail("selector handoff import batch bound is malformed")
    if after_ordinal == 0:
        if any(
            item is not None
            for item in (
                after_cycle_id,
                after_cycle_pointer,
                after_queue_item_id,
                after_queue_item_pointer,
            )
        ):
            _fail("selector initial handoff cursor carries prior queue state")
        prior_cycle: dict[str, Any] | None = None
        prior_queue: dict[str, Any] | None = None
    else:
        prior_cycle = _clean_handoff_cursor_pointer(
            after_cycle_pointer,
            identity=after_cycle_id,
            prefix="oscy",
            key=f"cycles/{after_cycle_id}.json",
            label="cycle receipt",
        )
        prior_queue = _clean_handoff_cursor_pointer(
            after_queue_item_pointer,
            identity=after_queue_item_id,
            prefix="ossq",
            key=_handoff_queue_key(after_ordinal),
            label="queue item",
        )

    if after_ordinal == clean_head["handoff_queue_count"]:
        if (
            prior_cycle != clean_head["last_cycle"]
            or prior_queue != clean_head["last_handoff_queue"]
        ):
            _fail("selector terminal handoff cursor does not match the current HEAD")
        return []

    target_ordinal = min(
        clean_head["handoff_queue_count"], after_ordinal + max_records
    )
    expected_queue = copy.deepcopy(clean_head["last_handoff_queue"])
    expected_ordinal = clean_head["handoff_queue_count"]
    item = tail_item

    # Authenticate a logarithmic path from the current tail to the newest node
    # in this bounded oldest-first batch.  Each jump pointer is inside the
    # content-addressed node that was authenticated by the preceding step.
    while expected_ordinal > target_ordinal:
        distance = expected_ordinal - target_ordinal
        level = distance.bit_length() - 1
        skips = item["skip_queue_items"]
        if level >= len(skips):
            _fail("selector handoff queue skip index ended before its target")
        expected_queue = copy.deepcopy(skips[level])
        expected_ordinal -= 1 << level
        item = _load_pointer(
            root,
            expected_queue,
            label=f"authenticated selector queue jump {expected_ordinal}",
        )
        if (
            item.get("schema")
            != "options.sparse_selector_handoff_queue_item/v1"
            or item["ordinal"] != expected_ordinal
            or expected_queue["key"] != _handoff_queue_key(expected_ordinal)
            or item["queue_item_id"] != expected_queue["id"]
        ):
            _fail("selector handoff queue skip target drifted")

    expected_cycle = copy.deepcopy(item["selector_cycle"])
    newest_first: list[dict[str, Any]] = []
    while expected_ordinal > after_ordinal:
        if expected_ordinal == clean_head["handoff_queue_count"]:
            cycle = tail_cycle
        else:
            cycle = _load_pointer(
                root,
                expected_cycle,
                label=f"authenticated selector cycle {expected_ordinal}",
            )
        record_bytes = expected_queue["bytes"] + expected_cycle["bytes"]
        if (
            item.get("schema") != "options.sparse_selector_handoff_queue_item/v1"
            or item["ordinal"] != expected_ordinal
            or expected_queue["key"] != _handoff_queue_key(expected_ordinal)
            or item["selector_cycle"] != expected_cycle
            or item["queue_item_id"] != expected_queue["id"]
            or cycle.get("schema") != "options.sparse_selector_cycle_receipt/v1"
            or cycle["ordinal"] != expected_ordinal
            or cycle["previous_cycle"] != item["previous_cycle"]
        ):
            _fail("selector HEAD-tail handoff queue chain drifted")
        decisions: list[dict[str, Any]] = []
        for pointer in cycle["decision_pointers"]:
            decision = _load_pointer(
                root,
                pointer,
                label=f"authenticated selector decision {pointer['id']}",
            )
            decisions.append(decision)
            record_bytes += pointer["bytes"]
        if record_bytes > MAX_HANDOFF_IMPORT_BYTES:
            _fail("selector queued cycle exceeds its publication bound")
        if (
            [decision["decision_id"] for decision in decisions] != cycle["decision_ids"]
            or len(decisions) != cycle["decision_count"]
            or sum(decision["action"] == "propose" for decision in decisions)
            != cycle["propose_count"]
            or sum(decision["action"] == "abstain" for decision in decisions)
            != cycle["abstain_count"]
        ):
            _fail("selector queued cycle decision pointers drifted")
        newest_first.append(
            {
                "item": item,
                "pointer": copy.deepcopy(expected_queue),
                "cycle": cycle,
                "decisions": decisions,
            }
        )
        if expected_ordinal == after_ordinal + 1:
            if (
                item["previous_cycle"] != prior_cycle
                or item["previous_queue_item"] != prior_queue
                or item["previous_queue_item_id"]
                != (None if prior_queue is None else prior_queue["id"])
            ):
                _fail("selector handoff queue does not descend from its exact cursor")
            break
        if item["previous_queue_item"] is None or item["previous_cycle"] is None:
            _fail("selector handoff queue chain ended before its cursor")
        expected_queue = copy.deepcopy(item["previous_queue_item"])
        expected_cycle = copy.deepcopy(item["previous_cycle"])
        expected_ordinal -= 1
        item = _load_pointer(
            root,
            expected_queue,
            label=f"authenticated selector queue item {expected_ordinal}",
        )

    newest_first.reverse()
    return newest_first


def read_next_handoff_queue_item(
    root: Path,
    head: Mapping[str, Any],
    *,
    after_ordinal: int,
    after_cycle_id: str | None,
    after_cycle_pointer: Mapping[str, Any] | None,
    after_queue_item_id: str | None,
    after_queue_item_pointer: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Compatibility single-item view over the authenticated pending chain."""

    pending = authenticated_pending_handoff_queue(
        root,
        head,
        after_ordinal=after_ordinal,
        after_cycle_id=after_cycle_id,
        after_cycle_pointer=after_cycle_pointer,
        after_queue_item_id=after_queue_item_id,
        after_queue_item_pointer=after_queue_item_pointer,
        max_records=1,
    )
    return None if not pending else pending[0]["item"]


def _evidence_object(value: Mapping[str, Any]) -> PlannedObject:
    body = canonical_bytes(value)
    digest = _sha256(body)
    return PlannedObject(key=f"evidence/{digest}.json", value=dict(value))


def _make_evidence_generation(
    *,
    snapshot: EvidenceSnapshot,
    w1a_source_receipt: PlannedObject | None,
    manifest_pointer: Mapping[str, Any],
    fenced_at: str,
) -> PlannedObject:
    value: dict[str, Any] = {
        "schema": "options.sparse_selector_evidence_generation/v1",
        "generation_id": "",
        "settled_manifest": copy.deepcopy(dict(manifest_pointer)),
        "fenced_at": fenced_at,
        "w1a_source_receipt": (
            None
            if w1a_source_receipt is None
            else copy.deepcopy(w1a_source_receipt.pointer)
        ),
        "lifecycle_state": (
            None
            if snapshot.lifecycle_state is None
            else copy.deepcopy(dict(snapshot.lifecycle_state))
        ),
        "w1a_error": snapshot.w1a_error,
        "mark_error": snapshot.mark_error,
        "lifecycle_error": snapshot.lifecycle_error,
        "digests": dict(DIGESTS),
        "authority": dict(FALSE_AUTHORITY),
    }
    value["generation_id"] = _content_id(
        "osseg_", value, field="generation_id"
    )
    clean = validate_runtime_object(value, label="selector evidence generation")
    item = _evidence_object(clean)
    if len(item.body) > MAX_EVIDENCE_GENERATION_BYTES:
        _fail("selector evidence generation exceeds its transport bound")
    return item


def _compact_konseki_evidence(
    *,
    full: PlannedObject | None,
    snapshot: EvidenceSnapshot,
    generation_pointer: Mapping[str, Any],
    candidate_pointer: Mapping[str, Any],
) -> PlannedObject | None:
    if full is None:
        return None
    if snapshot.w1a_head is None:
        _fail("selector Konseki evidence lacks its W1A source publication")
    reference = full.value["reference"]
    matches = [
        index
        for index, item in enumerate(snapshot.w1a_references)
        if canonical_bytes(item) == canonical_bytes(reference)
    ]
    if len(matches) != 1:
        _fail("selector Konseki evidence is not unique in its generation")
    item = _evidence_object(
        {
            "schema": "options.sparse_selector_konseki_evidence/v1",
            "generation": copy.deepcopy(dict(generation_pointer)),
            "candidate": copy.deepcopy(dict(candidate_pointer)),
            "reference_ordinal": matches[0] + 1,
            "reference_id": reference["reference_id"],
            "reference_sha256": _sha256(canonical_bytes(reference)),
            "authority": dict(FALSE_AUTHORITY),
        }
    )
    if len(item.body) > MAX_EVIDENCE_OBJECT_BYTES:
        _fail("selector compact Konseki evidence exceeds its bound")
    return item


def _compact_mark_evidence(
    *,
    full: PlannedObject | None,
    generation_pointer: Mapping[str, Any],
    candidate_pointer: Mapping[str, Any],
    session_date: str,
) -> PlannedObject | None:
    if full is None:
        return None
    row = full.value["selected_plan_row"]
    item = _evidence_object(
        {
            "schema": "options.sparse_selector_mark_evidence/v1",
            "generation": copy.deepcopy(dict(generation_pointer)),
            "candidate": copy.deepcopy(dict(candidate_pointer)),
            "plan_id": row["plan"]["id"],
            "session_date": session_date,
            "mark_pointer": copy.deepcopy(full.value["mark_pointer"]),
            "selected_row_sha256": _sha256(canonical_bytes(row)),
            "authority": dict(FALSE_AUTHORITY),
        }
    )
    if len(item.body) > MAX_EVIDENCE_OBJECT_BYTES:
        _fail("selector compact mark evidence exceeds its bound")
    return item


def _compact_lifecycle_evidence(
    *,
    full: PlannedObject | None,
    generation_pointer: Mapping[str, Any],
    candidate_pointer: Mapping[str, Any],
) -> PlannedObject | None:
    if full is None:
        return None
    enrollment = full.value["enrollment"]
    item = _evidence_object(
        {
            "schema": "options.sparse_selector_lifecycle_evidence/v1",
            "generation": copy.deepcopy(dict(generation_pointer)),
            "candidate": copy.deepcopy(dict(candidate_pointer)),
            "plan_id": enrollment["payload"]["plan"]["id"],
            "enrollment_pointer": copy.deepcopy(
                full.value["enrollment_pointer"]
            ),
            "authority": dict(FALSE_AUTHORITY),
        }
    )
    if len(item.body) > MAX_EVIDENCE_OBJECT_BYTES:
        _fail("selector compact lifecycle evidence exceeds its bound")
    return item


def _bounded_evidence_object(
    item: PlannedObject | None,
    *,
    reason: str,
    reasons: list[str],
) -> PlannedObject | None:
    if item is not None and len(item.body) > MAX_EVIDENCE_OBJECT_BYTES:
        reasons.append(reason)
        return None
    return item


def _validate_decision_evidence_objects(
    root: Path,
    decision: Mapping[str, Any],
    *,
    planned_by_key: Mapping[str, PlannedObject] | None = None,
    candidate: Mapping[str, Any] | None = None,
    evidence_inputs: EvidenceInputs | None = None,
    w1a_cache: dict[str, _W1APublication] | None = None,
) -> set[str]:
    def load(pointer: Mapping[str, Any], *, label: str) -> tuple[Mapping[str, Any], bytes]:
        planned = None if planned_by_key is None else planned_by_key.get(pointer["key"])
        if planned is not None:
            if planned.pointer != pointer:
                _fail(f"{label} differs from planned bytes")
            return planned.value, planned.body
        value = _load_pointer(root, pointer, label=label)
        return value, canonical_bytes(value)

    generation_pointer = decision["evidence"].get("generation")
    if not isinstance(generation_pointer, Mapping):
        _fail("selector decision lacks its evidence generation")
    generation_value, generation_body = load(
        generation_pointer, label="decision evidence generation"
    )
    generation = validate_runtime_object(
        generation_value, label="decision evidence generation"
    )
    settled_manifest = _load_pointer(
        root,
        generation["settled_manifest"],
        label="decision evidence settled manifest",
    )
    if (
        generation.get("schema")
        != "options.sparse_selector_evidence_generation/v1"
        or generation_pointer["key"] != f"evidence/{_sha256(generation_body)}.json"
        or settled_manifest.get("schema")
        != "options.sparse_selector_candidate_manifest/v1"
        or generation["settled_manifest"]["id"] != decision["manifest_id"]
        or settled_manifest["manifest_id"] != decision["manifest_id"]
        or _utc(generation["fenced_at"], label="evidence generation fence")
        > _utc(decision["decision_event_at"], label="decision event")
    ):
        _fail("selector decision evidence generation binding drifted")
    source_pointer = generation["w1a_source_receipt"]
    source_receipt: Mapping[str, Any] | None = None
    w1a_publication: _W1APublication | None = None
    used: set[str] = {generation_pointer["key"]}
    if source_pointer is not None:
        if evidence_inputs is None or evidence_inputs.w1a_receipt_root is None:
            _fail("selector decision W1A source lacks its trusted receipt root")
        source_value, source_body = load(
            source_pointer, label="decision W1A source receipt"
        )
        source_receipt = validate_runtime_object(
            source_value, label="decision W1A source receipt"
        )
        if (
            source_pointer["key"] != f"evidence/{_sha256(source_body)}.json"
            or source_receipt["settled_manifest"] != generation["settled_manifest"]
            or _utc(source_receipt["captured_at"], label="W1A capture")
            > _utc(generation["fenced_at"], label="evidence generation fence")
        ):
            _fail("selector decision W1A source binding drifted")
        used.add(source_pointer["key"])
        cache = {} if w1a_cache is None else w1a_cache
        w1a_publication = cache.get(source_pointer["key"])
        if w1a_publication is None:
            candidate_rows = [
                (
                    copy.deepcopy(dict(pointer)),
                    _load_pointer(
                        root, pointer, label="W1A source manifested candidate"
                    ),
                )
                for pointer in settled_manifest["candidates"]
            ]
            w1a_publication = _authenticate_historical_w1a_source(
                source_receipt,
                receipt_root=Path(evidence_inputs.w1a_receipt_root),
                manifest=settled_manifest,
                candidate_rows=candidate_rows,
            )
            cache[source_pointer["key"]] = w1a_publication
    elif generation["w1a_error"] is not True:
        _fail("selector decision W1A absence is not fail-closed")
    expected_schemas = {
        "konseki": "options.sparse_selector_konseki_evidence/v1",
        "mark": "options.sparse_selector_mark_evidence/v1",
        "lifecycle": "options.sparse_selector_lifecycle_evidence/v1",
    }
    for slot, schema in expected_schemas.items():
        pointer = decision["evidence"][slot]
        if pointer is None:
            continue
        value, body = load(pointer, label=f"decision {slot} evidence")
        value = validate_runtime_object(value, label=f"decision {slot} evidence")
        if (
            len(body) > MAX_EVIDENCE_OBJECT_BYTES
            or value.get("schema") != schema
            or value.get("authority") != FALSE_AUTHORITY
            or pointer["key"] != f"evidence/{_sha256(body)}.json"
            or value.get("generation") != generation_pointer
            or value.get("candidate") != decision["candidate"]
        ):
            _fail("selector decision evidence slot binding drifted")
        used.add(pointer["key"])
        if candidate is not None and slot == "konseki":
            try:
                ordinal = value["reference_ordinal"]
                if (
                    source_receipt is None
                    or w1a_publication is None
                    or generation["w1a_error"] is not False
                    or type(ordinal) is not int
                    or not 1 <= ordinal <= len(w1a_publication.references)
                ):
                    _fail("selector Konseki evidence generation is unavailable")
                reference = context_bridge.validate_context_reference(
                    w1a_publication.references[ordinal - 1]
                )
                owner = reference["owner"]
                if (
                    value["reference_id"] != reference["reference_id"]
                    or value["reference_sha256"]
                    != _sha256(canonical_bytes(reference))
                    or owner["record_sha256"]
                    != candidate["final_episode_row_sha256"]
                    or owner["ticker"] != candidate["final_episode_row"]["ticker"]
                    or owner["event_time"]
                    != candidate["final_episode_row"]["event_time"]
                ):
                    _fail("selector Konseki evidence escaped its candidate")
            except (KeyError, TypeError) as exc:
                raise SparseSelectorError(
                    "selector Konseki evidence binding is malformed"
                ) from exc
        if candidate is not None and slot == "lifecycle":
            try:
                state = generation["lifecycle_state"]
                plan_id = value["plan_id"]
                if (
                    state is None
                    or generation["lifecycle_error"] is not False
                    or state["enrollments"].get(plan_id)
                    != value["enrollment_pointer"]
                    or (
                        decision["plan_id"] is not None
                        and plan_id != decision["plan_id"]
                    )
                ):
                    _fail("selector lifecycle evidence escaped its decision")
                if evidence_inputs is not None and evidence_inputs.lifecycle_root is not None:
                    enrollment = lifecycle._load_enrollment(
                        Path(evidence_inputs.lifecycle_root),
                        value["enrollment_pointer"],
                        plan_id,
                    )
                    if (
                        not _contract_matches_campaign(
                            enrollment["payload"]["contract"],
                            candidate["campaign_row"],
                        )
                        or (
                            decision["contract"] is not None
                            and _nbbo_contract(enrollment["payload"]["contract"])
                            != decision["contract"]
                        )
                    ):
                        _fail("selector lifecycle evidence source binding drifted")
            except (KeyError, TypeError) as exc:
                raise SparseSelectorError(
                    "selector lifecycle evidence binding is malformed"
                ) from exc
        if candidate is not None and slot == "mark":
            try:
                state = generation["lifecycle_state"]
                plan_id = value["plan_id"]
                session_date = value["session_date"]
                if (
                    state is None
                    or generation["mark_error"] is not False
                    or state["latest_marks"][plan_id]["sessions"].get(session_date)
                    != value["mark_pointer"]
                    or (
                        decision["plan_id"] is not None
                        and plan_id != decision["plan_id"]
                    )
                ):
                    _fail("selector mark evidence escaped its decision")
                if evidence_inputs is not None and evidence_inputs.mark_root is not None:
                    observation = lifecycle._load_mark_observation(
                        Path(evidence_inputs.mark_root), value["mark_pointer"]
                    )
                    row = lifecycle._row_for_plan(observation, plan_id)
                    if (
                        value["selected_row_sha256"]
                        != _sha256(canonical_bytes(row))
                        or not _contract_matches_campaign(
                            row["contract"], candidate["campaign_row"]
                        )
                        or (
                            decision["contract"] is not None
                            and _nbbo_contract(row["contract"])
                            != decision["contract"]
                        )
                    ):
                        _fail("selector mark evidence source binding drifted")
            except (KeyError, TypeError) as exc:
                raise SparseSelectorError(
                    "selector mark evidence binding is malformed"
                ) from exc
    return used


@dataclass(frozen=True)
class _W1ALane:
    root: Path
    descriptors: tuple[int, ...]
    bindings: tuple[tuple[int, str, int, int], ...]

    @property
    def root_fd(self) -> int:
        return self.descriptors[-1]


@dataclass(frozen=True)
class _W1APublication:
    root_path_sha256: str
    head: Mapping[str, Any]
    head_body: bytes
    audit: Mapping[str, Any]
    references: tuple[Mapping[str, Any], ...]


def _assert_w1a_lane_identity(lane: _W1ALane) -> None:
    for parent_fd, name, device, inode in lane.bindings:
        try:
            bound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise SparseSelectorError(
                "W1A receipt root was renamed during authenticated read"
            ) from exc
        if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (
            device,
            inode,
        ):
            _fail("W1A receipt root or ancestor was rebound during authenticated read")
    _validate_directory_metadata(os.fstat(lane.root_fd), private=True)


@contextmanager
def _open_w1a_lane(root: Path) -> Iterator[_W1ALane]:
    """Open a W1A root by anchored components without touching selector lane state."""

    absolute = _absolute_private_path(Path(root))
    if absolute in {Path("/"), Path.home().resolve()}:
        _fail("W1A receipt root is too broad")
    repository = ROOT.resolve()
    if absolute == repository or repository in absolute.parents:
        _fail("W1A receipt root cannot be inside the repository")
    descriptors: list[int] = []
    bindings: list[tuple[int, str, int, int]] = []
    try:
        current = os.open("/", _DIRECTORY_FLAGS)
        descriptors.append(current)
        rendered: list[str] = []
        for index, part in enumerate(absolute.parts[1:]):
            rendered.append(part)
            child = _open_directory_component(
                current,
                part,
                create=False,
                private=index == len(absolute.parts[1:]) - 1,
                label="/" + "/".join(rendered),
            )
            metadata = os.fstat(child)
            bindings.append((current, part, metadata.st_dev, metadata.st_ino))
            descriptors.append(child)
            current = child
        lane = _W1ALane(absolute, tuple(descriptors), tuple(bindings))
        _assert_w1a_lane_identity(lane)
        yield lane
        _assert_w1a_lane_identity(lane)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


@contextmanager
def _open_w1a_directory(
    lane: _W1ALane, parts: Sequence[str]
) -> Iterator[int]:
    descriptors: list[int] = []
    bindings: list[tuple[int, str, int, int]] = []
    current = os.dup(lane.root_fd)
    descriptors.append(current)
    try:
        for part in parts:
            child = _open_directory_component(
                current,
                part,
                create=False,
                private=True,
                label="W1A receipt namespace",
            )
            metadata = os.fstat(child)
            bindings.append((current, part, metadata.st_dev, metadata.st_ino))
            descriptors.append(child)
            current = child
        yield current
        _assert_w1a_lane_identity(lane)
        for parent_fd, name, device, inode in bindings:
            bound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(bound.st_mode) or (bound.st_dev, bound.st_ino) != (
                device,
                inode,
            ):
                _fail("W1A receipt namespace was rebound during authenticated read")
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_w1a_key(
    lane: _W1ALane, key: str, *, limit: int, label: str
) -> tuple[dict[str, Any], bytes]:
    parts = key.split("/")
    if len(parts) != 3 or parts[0] not in {"audits", "reference_sets"}:
        _fail(f"{label} key is malformed")
    digest = parts[2].removesuffix(".json")
    if (
        not re.fullmatch(r"[a-f0-9]{2}", parts[1])
        or not _SHA256_RE.fullmatch(digest)
        or parts[1] != digest[:2]
        or parts[2] != f"{digest}.json"
    ):
        _fail(f"{label} key is not content addressed")
    with _open_w1a_directory(lane, parts[:2]) as parent_fd:
        body = _read_regular_at(
            parent_fd,
            parts[2],
            limit=limit,
            required=True,
            label=label,
        )
    assert body is not None
    value = strict_json(body, label=label)
    if not isinstance(value, dict) or canonical_bytes(value) != body:
        _fail(f"{label} is not canonical")
    return value, body


def _read_w1a_head(lane: _W1ALane) -> tuple[dict[str, Any], bytes]:
    body = _read_regular_at(
        lane.root_fd,
        "HEAD.json",
        limit=MAX_W1A_HEAD_BYTES,
        required=True,
        label="W1A receipt HEAD",
    )
    assert body is not None
    value = strict_json(body, label="W1A receipt HEAD")
    if not isinstance(value, dict) or canonical_bytes(value) != body:
        _fail("W1A receipt HEAD is not canonical")
    return context_store.validate_head(value), body


def _authenticate_w1a_head(
    lane: _W1ALane, head: Mapping[str, Any], head_body: bytes
) -> _W1APublication:
    clean_head = context_store.validate_head(head)
    if canonical_bytes(clean_head) != head_body:
        _fail("W1A historical HEAD bytes are not exact canonical bytes")
    audit_value, audit_body = _read_w1a_key(
        lane,
        clean_head["audit_object_key"],
        limit=MAX_W1A_AUDIT_BYTES,
        label="W1A historical audit object",
    )
    reference_value, reference_body = _read_w1a_key(
        lane,
        clean_head["reference_set_object_key"],
        limit=MAX_W1A_REFERENCE_SET_OBJECT_BYTES,
        label="W1A historical reference-set object",
    )
    if (
        _sha256(audit_body) != clean_head["audit_sha256"]
        or _sha256(reference_body)
        != clean_head["reference_set_object_sha256"]
    ):
        _fail("W1A historical object differs from its HEAD")
    try:
        reference_set = context_store._validate_reference_set_object(reference_value)
        references = tuple(
            context_bridge.validate_context_reference(item)
            for item in reference_set["references"]
        )
        audit = context_bridge.validate_audit_receipt(
            audit_value, references=references
        )
    except (
        context_bridge.OptionsMarketMemoryContextError,
        context_store.OptionsMarketMemoryReceiptStoreError,
    ) as exc:
        raise SparseSelectorError("W1A historical publication is invalid") from exc
    if (
        audit["audit_id"] != clean_head["audit_id"]
        or audit["audited_at"] != clean_head["published_at"]
        or reference_set["reference_set_sha256"]
        != clean_head["reference_set_sha256"]
        or reference_set["reference_count"] != clean_head["reference_count"]
    ):
        _fail("W1A historical publication does not reconcile to its HEAD")
    return _W1APublication(
        root_path_sha256=_sha256(os.fsencode(str(lane.root))),
        head=clean_head,
        head_body=head_body,
        audit=audit,
        references=references,
    )


def _assert_w1a_lock_identity(lane: _W1ALane, descriptor: int) -> None:
    _assert_w1a_lane_identity(lane)
    opened = os.fstat(descriptor)
    try:
        bound = os.stat(".publish.lock", dir_fd=lane.root_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise SparseSelectorError("W1A publication lock was renamed") from exc
    for metadata in (opened, bound):
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _fail("W1A publication lock metadata is unsafe")
    if (opened.st_dev, opened.st_ino) != (bound.st_dev, bound.st_ino):
        _fail("W1A publication lock path no longer names the locked inode")


@contextmanager
def _locked_w1a_publication(root: Path) -> Iterator[_W1APublication]:
    """Authenticate one current W1A publication under its existing lock."""

    with _open_w1a_lane(root) as lane:
        try:
            descriptor = os.open(
                ".publish.lock",
                os.O_RDWR
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=lane.root_fd,
            )
        except OSError as exc:
            raise SparseSelectorError(
                "W1A publication lock must already exist"
            ) from exc
        locked = False
        try:
            _assert_w1a_lock_identity(lane, descriptor)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            locked = True
            _assert_w1a_lock_identity(lane, descriptor)
            head, head_body = _read_w1a_head(lane)
            publication = _authenticate_w1a_head(lane, head, head_body)
            yield publication
            _assert_w1a_lock_identity(lane, descriptor)
            final_head, final_body = _read_w1a_head(lane)
            final_publication = _authenticate_w1a_head(
                lane, final_head, final_body
            )
            if final_publication != publication:
                raise EvidenceGenerationDrift(
                    "W1A publication changed during selector capture"
                )
        finally:
            try:
                if locked:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _w1a_snapshot(
    receipt_root: Path | None,
) -> tuple[
    Mapping[str, Any] | None,
    Mapping[str, Any] | None,
    tuple[Mapping[str, Any], ...],
    str | None,
    Mapping[str, tuple[Mapping[str, Any], ...]],
    bool,
]:
    if receipt_root is None:
        return None, None, (), None, {}, True
    with _locked_w1a_publication(Path(receipt_root)) as publication:
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for reference in publication.references:
            owner = reference["owner"]
            if owner["schema"] == "options.signal_episode/v1":
                grouped.setdefault(owner["id"], []).append(reference)
        return (
            copy.deepcopy(dict(publication.head)),
            copy.deepcopy(dict(publication.audit)),
            tuple(copy.deepcopy(dict(item)) for item in publication.references),
            publication.root_path_sha256,
            {key: tuple(value) for key, value in grouped.items()},
            False,
        )


def _w1a_descriptors(
    candidate_rows: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    references: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_owner: dict[tuple[str, str], tuple[int, Mapping[str, Any]]] = {}
    for ordinal, raw in enumerate(references, start=1):
        reference = context_bridge.validate_context_reference(raw)
        owner = reference["owner"]
        key = (owner["schema"], owner["id"])
        if key in by_owner:
            _fail("W1A reference set repeats an owner identity")
        by_owner[key] = (ordinal, reference)
    descriptors: list[dict[str, Any]] = []
    for descriptor_ordinal, (pointer, candidate) in enumerate(
        candidate_rows, start=1
    ):
        clean_candidate = validate_runtime_object(
            candidate, label="W1A manifested selector candidate"
        )
        if pointer != _pointer_for(
            f"candidates/{clean_candidate['candidate_id']}.json", clean_candidate
        ):
            _fail("W1A descriptor candidate pointer differs from exact bytes")
        episode = clean_candidate["final_episode_row"]
        owner_key = ("options.signal_episode/v1", episode["episode_id"])
        found = by_owner.get(owner_key)
        descriptor: dict[str, Any] = {
            "descriptor_ordinal": descriptor_ordinal,
            "candidate": copy.deepcopy(dict(pointer)),
            "candidate_id": clean_candidate["candidate_id"],
            "owner_schema": owner_key[0],
            "owner_id": owner_key[1],
            "owner_record_sha256": clean_candidate["final_episode_row_sha256"],
            "reference_ordinal": None,
            "reference_id": None,
            "reference_sha256": None,
        }
        if found is not None:
            reference_ordinal, reference = found
            descriptor.update(
                {
                    "reference_ordinal": reference_ordinal,
                    "reference_id": reference["reference_id"],
                    "reference_sha256": _sha256(canonical_bytes(reference)),
                }
            )
        descriptors.append(descriptor)
    return descriptors


def _make_w1a_source_receipt(
    *,
    snapshot: EvidenceSnapshot,
    manifest_pointer: Mapping[str, Any],
    candidate_rows: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    captured_at: str,
) -> PlannedObject | None:
    if snapshot.w1a_error:
        if any(
            item is not None
            for item in (
                snapshot.w1a_head,
                snapshot.w1a_audit,
                snapshot.w1a_root_path_sha256,
            )
        ) or snapshot.w1a_references:
            _fail("unavailable W1A snapshot retains publication truth")
        return None
    if (
        snapshot.w1a_head is None
        or snapshot.w1a_audit is None
        or snapshot.w1a_root_path_sha256 is None
    ):
        _fail("W1A snapshot lacks its authenticated publication")
    head = context_store.validate_head(snapshot.w1a_head)
    head_body = canonical_bytes(head)
    value: dict[str, Any] = {
        "schema": "options.sparse_selector_w1a_source_receipt/v1",
        "receipt_id": "",
        "captured_at": captured_at,
        "root_path_sha256": snapshot.w1a_root_path_sha256,
        "settled_manifest": copy.deepcopy(dict(manifest_pointer)),
        "head": copy.deepcopy(head),
        "head_sha256": _sha256(head_body),
        "head_bytes": len(head_body),
        "audit_id": head["audit_id"],
        "audit_object_key": head["audit_object_key"],
        "audit_sha256": head["audit_sha256"],
        "reference_set_object_key": head["reference_set_object_key"],
        "reference_set_object_sha256": head["reference_set_object_sha256"],
        "reference_set_sha256": head["reference_set_sha256"],
        "reference_count": head["reference_count"],
        "descriptors": _w1a_descriptors(candidate_rows, snapshot.w1a_references),
        "authority": dict(FALSE_AUTHORITY),
    }
    value["receipt_id"] = _content_id("ossw_", value, field="receipt_id")
    clean = validate_runtime_object(value, label="selector W1A source receipt")
    item = _evidence_object(clean)
    if len(item.body) > MAX_W1A_SOURCE_RECEIPT_BYTES:
        _fail("selector W1A source receipt exceeds its compact bound")
    return item


def _w1a_high_water_from_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    clean = validate_runtime_object(receipt, label="selector W1A high-water source")
    return {
        "root_path_sha256": clean["root_path_sha256"],
        "published_at": clean["head"]["published_at"],
        "publication_id": clean["head"]["publication_id"],
        "head_sha256": clean["head_sha256"],
    }


def _advance_w1a_high_water(
    prior: Mapping[str, Any] | None,
    receipt: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if receipt is None:
        return None if prior is None else copy.deepcopy(dict(prior))
    next_value = _w1a_high_water_from_receipt(receipt)
    if prior is None:
        return next_value
    if prior["root_path_sha256"] != next_value["root_path_sha256"]:
        _fail("selector W1A receipt root changed after its first publication")
    prior_clock = _utc(prior["published_at"], label="prior W1A high-water")
    next_clock = _utc(next_value["published_at"], label="next W1A high-water")
    if next_clock < prior_clock or (next_clock == prior_clock and dict(prior) != next_value):
        _fail("selector W1A publication rolled back or forked at its high-water")
    return next_value


def _authenticate_historical_w1a_source(
    receipt: Mapping[str, Any],
    *,
    receipt_root: Path,
    manifest: Mapping[str, Any],
    candidate_rows: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> _W1APublication:
    clean = validate_runtime_object(receipt, label="historical selector W1A source")
    if clean["settled_manifest"] != _pointer_for(
        f"manifests/{manifest['manifest_id']}.json", manifest
    ):
        _fail("selector W1A source escaped its settled manifest")
    with _open_w1a_lane(receipt_root) as lane:
        if _sha256(os.fsencode(str(lane.root))) != clean["root_path_sha256"]:
            _fail("selector W1A source root differs from its configuration binding")
        head = context_store.validate_head(clean["head"])
        head_body = canonical_bytes(head)
        publication = _authenticate_w1a_head(lane, head, head_body)
    expected_descriptors = _w1a_descriptors(candidate_rows, publication.references)
    if (
        clean["head_sha256"] != _sha256(publication.head_body)
        or clean["head_bytes"] != len(publication.head_body)
        or clean["descriptors"] != expected_descriptors
        or clean["audit_id"] != publication.audit["audit_id"]
        or clean["reference_count"] != len(publication.references)
    ):
        _fail("selector W1A source does not rederive from historical publication")
    return publication


def _lifecycle_contract_key(contract: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(contract.get("root")),
        str(contract.get("right")),
        str(contract.get("expiry")),
        _canonical_strike_text(contract.get("strike")),
    )


def _campaign_contract_key(campaign: Mapping[str, Any]) -> tuple[str, str, str, str]:
    group = campaign["group"]
    return (
        str(group["ticker"]),
        str(group["right"]),
        str(group["expiration"]),
        _canonical_strike_text(group["strike_key"]),
    )


def _assert_evidence_roots_distinct(
    selector_root: Path, inputs: EvidenceInputs
) -> None:
    configured = [
        ("selector", _absolute_private_path(selector_root)),
        *[
            (label, _absolute_private_path(Path(value)))
            for label, value in (
                ("W1A", inputs.w1a_receipt_root),
                ("mark", inputs.mark_root),
                ("lifecycle", inputs.lifecycle_root),
            )
            if value is not None
        ],
    ]
    identities: dict[tuple[int, int], str] = {}
    for index, (label, path) in enumerate(configured):
        for other_label, other_path in configured[index + 1 :]:
            if (
                path == other_path
                or path in other_path.parents
                or other_path in path.parents
            ):
                _fail(
                    f"selector evidence roots are not pairwise separate: "
                    f"{label}/{other_label}"
                )
        try:
            metadata = os.stat(path, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail(f"selector {label} evidence root is not a directory")
        identity = (metadata.st_dev, metadata.st_ino)
        prior = identities.get(identity)
        if prior is not None:
            _fail(f"selector evidence root aliases {prior} and {label}")
        identities[identity] = label


def _build_evidence_snapshot(inputs: EvidenceInputs) -> EvidenceSnapshot:
    (
        w1a_head,
        w1a_audit,
        w1a_references,
        w1a_root_path_sha256,
        by_episode,
        w1a_error,
    ) = _w1a_snapshot(inputs.w1a_receipt_root)
    empty = EvidenceSnapshot(
        w1a_head=w1a_head,
        w1a_audit=w1a_audit,
        w1a_references=w1a_references,
        w1a_root_path_sha256=w1a_root_path_sha256,
        w1a_by_episode=by_episode,
        lifecycle_state=None,
        enrollments_by_contract={},
        mark_rows_by_plan_session={},
        w1a_error=w1a_error,
        mark_error=inputs.mark_root is None,
        lifecycle_error=True,
        lifecycle_publishable=False,
        lifecycle_unpublishable_contracts=frozenset(),
        mark_unpublishable_plan_sessions=frozenset(),
    )
    if inputs.mark_root is None or inputs.lifecycle_root is None:
        return empty
    mark_root = Path(inputs.mark_root).expanduser()
    lifecycle_root = Path(inputs.lifecycle_root).expanduser()
    try:
        lifecycle._validate_private_root_location(
            mark_root, label="private option mark evidence"
        )
        lifecycle._validate_private_root_location(
            lifecycle_root, label="private lifecycle state"
        )
        mark_chain._require_private_directory(mark_root)
        mark_chain._require_private_directory(lifecycle_root)
        # Fixed acquisition order is mark then lifecycle.  Both mutable heads
        # are sampled under both locks and re-read after every immutable
        # reference is authenticated, so a decision never mixes generations.
        with mark_chain._private_ledger_lock(mark_root), mark_chain._private_ledger_lock(
            lifecycle_root
        ):
            mark_head_before = mark_chain._load_previous_pointer(mark_root)
            ledger_path, receipt_path = lifecycle._ledger_paths(
                lifecycle_root,
                ledger_path=None,
                ledger_receipt_path=None,
                create=False,
            )
            ledger_body, ledger_rows, _ledger_receipt = lifecycle._read_ledger_snapshot(
                ledger_path, receipt_path
            )
            state = lifecycle._load_state(lifecycle_root)
            if state is None:
                _fail("lifecycle state is absent")
            lifecycle._validate_event_chain(lifecycle_root, state)
            lifecycle._validate_activation_boundary_against_state(
                lifecycle_root, state
            )
            lifecycle._validate_source_references(
                lifecycle_root=lifecycle_root,
                mark_root=mark_root,
                state=state,
                ledger_body=ledger_body,
                ledger_rows=ledger_rows,
            )
            snapshot_bytes = len(canonical_bytes(state))
            if (
                len(state.get("enrollments", {}))
                + len(state.get("terminals", {}))
                + len(state.get("latest_marks", {}))
                > MAX_EVIDENCE_SNAPSHOT_RECORDS
                or len(canonical_bytes(state)) > MAX_EVIDENCE_SNAPSHOT_BYTES
            ):
                _fail("selector lifecycle snapshot exceeds its bounded index")
            enrollments: dict[
                tuple[str, str, str, str],
                list[tuple[str, Mapping[str, Any], Mapping[str, Any]]],
            ] = {}
            for plan_id, pointer in state["enrollments"].items():
                enrollment = lifecycle._load_enrollment(
                    lifecycle_root, pointer, plan_id
                )
                snapshot_bytes += len(canonical_bytes(enrollment))
                if snapshot_bytes > MAX_EVIDENCE_SNAPSHOT_BYTES:
                    _fail("selector evidence snapshot exceeds its aggregate byte bound")
                key = _lifecycle_contract_key(enrollment["payload"]["contract"])
                enrollments.setdefault(key, []).append(
                    (
                        plan_id,
                        copy.deepcopy(enrollment),
                        copy.deepcopy(pointer),
                    )
                )
            rows: dict[
                tuple[str, str],
                tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]],
            ] = {}
            observations: dict[str, Mapping[str, Any]] = {}
            for plan_id, latest in state["latest_marks"].items():
                for session_date, pointer in latest.get("sessions", {}).items():
                    pointer_key = canonical_bytes(pointer).decode("utf-8")
                    observation = observations.get(pointer_key)
                    if observation is None:
                        observation = lifecycle._load_mark_observation(
                            mark_root, pointer
                        )
                        snapshot_bytes += len(canonical_bytes(observation))
                        if snapshot_bytes > MAX_EVIDENCE_SNAPSHOT_BYTES:
                            _fail(
                                "selector evidence snapshot exceeds its aggregate byte bound"
                            )
                        observations[pointer_key] = observation
                    if len(canonical_bytes(observation)) > MAX_EVIDENCE_SNAPSHOT_BYTES:
                        _fail("selector mark observation exceeds its snapshot bound")
                    row = lifecycle._row_for_plan(observation, plan_id)
                    key = (plan_id, session_date)
                    if key in rows:
                        _fail("lifecycle snapshot repeats a plan/session mark")
                    rows[key] = (
                        copy.deepcopy(pointer),
                        copy.deepcopy(observation),
                        copy.deepcopy(row),
                    )
            # Re-read the mutable state only after all referenced immutable
            # evidence validated under the lifecycle lock. Any changed HEAD is
            # a concurrent snapshot and must be retried, never mixed.
            if (
                lifecycle._load_state(lifecycle_root) != state
                or mark_chain._load_previous_pointer(mark_root) != mark_head_before
            ):
                raise EvidenceGenerationDrift(
                    "lifecycle state changed during selector evidence snapshot"
                )
            return EvidenceSnapshot(
                w1a_head=w1a_head,
                w1a_audit=w1a_audit,
                w1a_references=w1a_references,
                w1a_root_path_sha256=w1a_root_path_sha256,
                w1a_by_episode=by_episode,
                lifecycle_state=copy.deepcopy(state),
                enrollments_by_contract={
                    key: tuple(value) for key, value in enrollments.items()
                },
                mark_rows_by_plan_session=rows,
                w1a_error=w1a_error,
                mark_error=False,
                lifecycle_error=False,
                lifecycle_publishable=True,
                lifecycle_unpublishable_contracts=frozenset(),
                mark_unpublishable_plan_sessions=frozenset(),
            )
    except EvidenceGenerationDrift:
        raise
    except (OSError, ValueError, KeyError, TypeError, SparseSelectorError):
        return empty


def _evidence_snapshot_from_generation(
    generation: Mapping[str, Any],
    inputs: EvidenceInputs,
    *,
    root: Path,
    planned_by_key: Mapping[str, PlannedObject] | None = None,
) -> EvidenceSnapshot:
    """Rebuild one captured evidence generation from immutable producer bytes.

    Recovery must not substitute whichever mutable producer heads happen to be
    current later.  The generation carries the validated W1A export and exact
    lifecycle state; producer roots are used only to re-authenticate the
    immutable enrollment, mark, event-chain, and ledger-prefix objects named by
    that captured state.
    """

    clean_generation = validate_runtime_object(
        generation, label="captured selector evidence generation"
    )
    source_pointer = clean_generation["w1a_source_receipt"]
    w1a_head: Mapping[str, Any] | None = None
    w1a_audit: Mapping[str, Any] | None = None
    w1a_references: tuple[Mapping[str, Any], ...] = ()
    w1a_root_path_sha256: str | None = None
    by_episode: dict[str, tuple[Mapping[str, Any], ...]] = {}
    w1a_error = source_pointer is None
    if w1a_error != clean_generation["w1a_error"]:
        _fail("captured selector W1A generation availability drifted")
    if source_pointer is not None:
        if inputs.w1a_receipt_root is None:
            _fail("captured selector W1A generation lacks its trusted source root")
        source_item = (
            None
            if planned_by_key is None
            else planned_by_key.get(source_pointer["key"])
        )
        if source_item is None:
            source_value = _load_pointer(
                root, source_pointer, label="captured selector W1A source receipt"
            )
        else:
            if source_item.pointer != source_pointer:
                _fail("captured selector W1A source pointer differs from planned bytes")
            source_value = source_item.value
        manifest = _load_pointer(
            root,
            clean_generation["settled_manifest"],
            label="captured selector W1A settled manifest",
        )
        candidate_rows = [
            (
                copy.deepcopy(dict(pointer)),
                _load_pointer(root, pointer, label="captured W1A manifested candidate"),
            )
            for pointer in manifest["candidates"]
        ]
        publication = _authenticate_historical_w1a_source(
            source_value,
            receipt_root=Path(inputs.w1a_receipt_root),
            manifest=manifest,
            candidate_rows=candidate_rows,
        )
        source = validate_runtime_object(
            source_value, label="captured selector W1A source receipt"
        )
        if _utc(source["captured_at"], label="W1A capture") > _utc(
            clean_generation["fenced_at"], label="evidence generation fence"
        ):
            _fail("captured selector W1A source follows its generation fence")
        w1a_head = copy.deepcopy(dict(publication.head))
        w1a_audit = copy.deepcopy(dict(publication.audit))
        w1a_references = tuple(
            copy.deepcopy(dict(item)) for item in publication.references
        )
        w1a_root_path_sha256 = publication.root_path_sha256
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for reference in w1a_references:
            owner = reference["owner"]
            if owner["schema"] == "options.signal_episode/v1":
                grouped.setdefault(owner["id"], []).append(reference)
        by_episode = {key: tuple(value) for key, value in grouped.items()}
    state = clean_generation["lifecycle_state"]
    if state is None:
        if not clean_generation["lifecycle_error"]:
            _fail("captured selector lifecycle absence is inconsistent")
        return EvidenceSnapshot(
            w1a_head=w1a_head,
            w1a_audit=w1a_audit,
            w1a_references=w1a_references,
            w1a_root_path_sha256=w1a_root_path_sha256,
            w1a_by_episode=by_episode,
            lifecycle_state=None,
            enrollments_by_contract={},
            mark_rows_by_plan_session={},
            w1a_error=w1a_error,
            mark_error=clean_generation["mark_error"],
            lifecycle_error=True,
            lifecycle_publishable=False,
        )
    current_snapshot = _build_evidence_snapshot(inputs)
    if (
        current_snapshot.lifecycle_state == state
        and current_snapshot.mark_error == clean_generation["mark_error"]
        and current_snapshot.lifecycle_error == clean_generation["lifecycle_error"]
    ):
        return EvidenceSnapshot(
            w1a_head=w1a_head,
            w1a_audit=w1a_audit,
            w1a_references=w1a_references,
            w1a_root_path_sha256=w1a_root_path_sha256,
            w1a_by_episode=by_episode,
            lifecycle_state=current_snapshot.lifecycle_state,
            enrollments_by_contract=current_snapshot.enrollments_by_contract,
            mark_rows_by_plan_session=current_snapshot.mark_rows_by_plan_session,
            w1a_error=w1a_error,
            mark_error=current_snapshot.mark_error,
            lifecycle_error=current_snapshot.lifecycle_error,
            lifecycle_publishable=current_snapshot.lifecycle_publishable,
            lifecycle_unpublishable_contracts=(
                current_snapshot.lifecycle_unpublishable_contracts
            ),
            mark_unpublishable_plan_sessions=(
                current_snapshot.mark_unpublishable_plan_sessions
            ),
        )
    if inputs.mark_root is None or inputs.lifecycle_root is None:
        _fail("captured selector lifecycle generation lacks trusted producer roots")
    mark_root = Path(inputs.mark_root).expanduser()
    lifecycle_root = Path(inputs.lifecycle_root).expanduser()
    lifecycle._validate_private_root_location(
        mark_root, label="private option mark evidence"
    )
    lifecycle._validate_private_root_location(
        lifecycle_root, label="private lifecycle state"
    )
    mark_chain._require_private_directory(mark_root)
    mark_chain._require_private_directory(lifecycle_root)
    with mark_chain._private_ledger_lock(mark_root), mark_chain._private_ledger_lock(
        lifecycle_root
    ):
        ledger_path, receipt_path = lifecycle._ledger_paths(
            lifecycle_root,
            ledger_path=None,
            ledger_receipt_path=None,
            create=False,
        )
        ledger_body, ledger_rows, _ledger_receipt = lifecycle._read_ledger_snapshot(
            ledger_path, receipt_path
        )
        clean_state = lifecycle._validate_state_shape(state)
        lifecycle._validate_event_chain(lifecycle_root, clean_state)
        lifecycle._validate_activation_boundary_against_state(
            lifecycle_root, clean_state
        )
        lifecycle._validate_source_references(
            lifecycle_root=lifecycle_root,
            mark_root=mark_root,
            state=clean_state,
            ledger_body=ledger_body,
            ledger_rows=ledger_rows,
        )
        snapshot_bytes = len(canonical_bytes(clean_state))
        enrollments: dict[
            tuple[str, str, str, str],
            list[tuple[str, Mapping[str, Any], Mapping[str, Any]]],
        ] = {}
        for plan_id, pointer in clean_state["enrollments"].items():
            enrollment = lifecycle._load_enrollment(
                lifecycle_root, pointer, plan_id
            )
            snapshot_bytes += len(canonical_bytes(enrollment))
            if snapshot_bytes > MAX_EVIDENCE_SNAPSHOT_BYTES:
                _fail("captured selector evidence generation exceeds its byte bound")
            key = _lifecycle_contract_key(enrollment["payload"]["contract"])
            enrollments.setdefault(key, []).append(
                (plan_id, copy.deepcopy(enrollment), copy.deepcopy(pointer))
            )
        rows: dict[
            tuple[str, str],
            tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]],
        ] = {}
        observations: dict[str, Mapping[str, Any]] = {}
        for plan_id, latest in clean_state["latest_marks"].items():
            for session_date, pointer in latest.get("sessions", {}).items():
                pointer_key = canonical_bytes(pointer).decode("utf-8")
                observation = observations.get(pointer_key)
                if observation is None:
                    observation = lifecycle._load_mark_observation(mark_root, pointer)
                    snapshot_bytes += len(canonical_bytes(observation))
                    if snapshot_bytes > MAX_EVIDENCE_SNAPSHOT_BYTES:
                        _fail(
                            "captured selector evidence generation exceeds its byte bound"
                        )
                    observations[pointer_key] = observation
                row = lifecycle._row_for_plan(observation, plan_id)
                key = (plan_id, session_date)
                if key in rows:
                    _fail("captured selector generation repeats a plan/session mark")
                rows[key] = (
                    copy.deepcopy(pointer),
                    copy.deepcopy(observation),
                    copy.deepcopy(row),
                )
    return EvidenceSnapshot(
        w1a_head=w1a_head,
        w1a_audit=w1a_audit,
        w1a_references=w1a_references,
        w1a_root_path_sha256=w1a_root_path_sha256,
        w1a_by_episode=by_episode,
        lifecycle_state=copy.deepcopy(clean_state),
        enrollments_by_contract={key: tuple(value) for key, value in enrollments.items()},
        mark_rows_by_plan_session=rows,
        w1a_error=w1a_error,
        mark_error=clean_generation["mark_error"],
        lifecycle_error=False,
        lifecycle_publishable=True,
    )


def _reference_for_candidate(
    candidate: Mapping[str, Any],
    snapshot: EvidenceSnapshot | None,
    *,
    evidence_available_at: datetime,
) -> tuple[PlannedObject | None, list[str]]:
    if snapshot is None or snapshot.w1a_head is None:
        return None, ["KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED"]
    clean = snapshot.w1a_head
    matching = list(
        snapshot.w1a_by_episode.get(
            candidate["final_episode_row"]["episode_id"], ()
        )
    )
    if _utc(clean["published_at"], label="W1A publication clock") > evidence_available_at:
        return None, ["KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED"]
    episode = candidate["final_episode_row"]
    if len(matching) != 1:
        return None, ["KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED"]
    reference = matching[0]
    owner = reference["owner"]
    query = reference["query"]
    identity = prereg.SELECTOR_RULE["required_truth_receipts"]["konseki"][
        "subject_identity"
    ]
    expected_subject = {
        "subject_id": identity["subject_id"],
        "instrument_id": identity["instrument_id"],
    }
    if (
        candidate["campaign_row"]["group"]["ticker"] != "SPY"
        or owner["record_sha256"] != candidate["final_episode_row_sha256"]
        or owner["ticker"] != episode["ticker"]
        or owner["event_time"] != episode["event_time"]
        or owner["requested_as_of"] != episode["available_at"]
        or owner["requested_as_of_basis"] != "durable_available_at"
        or owner["evidence_phase"]
        != candidate["campaign_row"]["evidence_phase"]
        or query["subject"] != expected_subject
        or query["identity_config_sha256"] != identity["identity_config_sha256"]
        or query["event_time"] != episode["event_time"]
        or query["as_known_at"] != episode["available_at"]
        or query["mode"] != "operational_pit"
        or query["fallback_policy"] != "exact_no_fallback"
        or reference["authority"].get("may_select_options_candidate") is not False
        or any(
            value is not False
            for key, value in reference["authority"].items()
            if isinstance(value, bool)
        )
    ):
        return None, ["KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED"]
    evidence = _evidence_object(
        {
            "schema": "options.sparse_selector_konseki_evidence/v1",
            "source_publication_id": clean["publication_id"],
            "reference": reference,
            "authority": dict(FALSE_AUTHORITY),
        }
    )
    if reference["disposition"] != "bound" or reference["context"] is None:
        if reference.get("reason") == "exact_requested_as_of_context_absent":
            return evidence, ["KONSEKI_EXACT_ASOF_CONTEXT_ABSENT"]
        return evidence, ["KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED"]
    return evidence, []


def _canonical_strike_text(value: object) -> str:
    if isinstance(value, bool):
        _fail("option strike is boolean")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SparseSelectorError("option strike is malformed") from exc
    if not number.is_finite() or number <= 0:
        _fail("option strike is non-positive")
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _contract_matches_campaign(
    contract: Mapping[str, Any], campaign: Mapping[str, Any]
) -> bool:
    group = campaign["group"]
    return (
        contract.get("root") == group["ticker"]
        and contract.get("right") == group["right"]
        and contract.get("expiry") == group["expiration"]
        and _canonical_strike_text(contract.get("strike")) == group["strike_key"]
    )


def _nbbo_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    strike = _canonical_strike_text(contract["strike"])
    millis_decimal = Decimal(strike) * Decimal(1000)
    if millis_decimal != millis_decimal.to_integral_value():
        _fail("lifecycle strike does not have an exact millistrike")
    millis = int(millis_decimal)
    if millis != contract["strike_millis"]:
        _fail("lifecycle strike and millistrike disagree")
    occ = contract["occ_symbol"]
    if not isinstance(occ, str) or not re.fullmatch(
        r"[A-Z0-9 ]{6}[0-9]{6}[CP][0-9]{8}", occ
    ):
        _fail("lifecycle OCC symbol is malformed")
    return {
        "root": contract["root"],
        "expiration": contract["expiry"],
        "right": "call" if contract["right"] == "C" else "put",
        "strike": strike,
        "strike_millis": millis,
        "occ_symbol": occ,
    }


def _all_false_mapping(value: object) -> bool:
    return isinstance(value, Mapping) and all(item is False for item in value.values())


def _lifecycle_evidence(
    candidate: Mapping[str, Any],
    inputs: EvidenceInputs | EvidenceSnapshot,
    *,
    decision_event_at: datetime,
) -> tuple[
    PlannedObject | None,
    PlannedObject | None,
    dict[str, Any] | None,
    str | None,
    list[str],
]:
    if isinstance(inputs, EvidenceSnapshot):
        reasons: list[str] = []
        if inputs.mark_error:
            reasons.append("MARK_RECEIPT_MISSING_OR_MISMATCHED")
        if inputs.lifecycle_error or inputs.lifecycle_state is None:
            reasons.append("LIFECYCLE_RECEIPT_MISSING_OR_MISMATCHED")
        if reasons:
            return None, None, None, None, reasons
        state = inputs.lifecycle_state
        contract_key = _campaign_contract_key(candidate["campaign_row"])
        matches = list(
            inputs.enrollments_by_contract.get(
                contract_key, ()
            )
        )
        terminal_matches = [item for item in matches if item[0] in state["terminals"]]
        open_matches = [item for item in matches if item[0] not in state["terminals"]]
        if terminal_matches:
            # Any terminal is final, even if a corrupt state also exposes an
            # open enrollment for the same exact contract.
            return (
                None,
                None,
                None,
                None,
                [
                    "EXACT_OCC_CONTRACT_MISSING_OR_INVALID",
                    "LIFECYCLE_RECEIPT_MISSING_OR_MISMATCHED",
                    "LIFECYCLE_ALREADY_TERMINAL",
                ],
            )
        if len(open_matches) != 1:
            return (
                None,
                None,
                None,
                None,
                [
                    "EXACT_OCC_CONTRACT_MISSING_OR_INVALID",
                    "LIFECYCLE_RECEIPT_MISSING_OR_MISMATCHED",
                ],
            )
        plan_id, enrollment, enrollment_pointer = open_matches[0]
        latest = state["latest_marks"].get(plan_id)
        if (
            not isinstance(latest, Mapping)
            or latest.get("contract_drift") is not False
            or latest.get("plan_identity_drift") is not False
            or latest.get("contract_occ_symbol")
            != enrollment["payload"]["contract"]["occ_symbol"]
        ):
            return (
                None,
                None,
                None,
                None,
                ["LIFECYCLE_NOT_DURABLE_OR_IDENTITY_DRIFT"],
            )
        session_text = decision_event_at.astimezone(ET).date().isoformat()
        admitted = inputs.mark_rows_by_plan_session.get((plan_id, session_text))
        lifecycle_evidence = _evidence_object(
            {
                "schema": "options.sparse_selector_lifecycle_evidence/v1",
                "state": state,
                "enrollment": enrollment,
                "enrollment_pointer": enrollment_pointer,
                "authority": dict(FALSE_AUTHORITY),
            }
        )
        if admitted is None:
            return (
                None,
                lifecycle_evidence,
                None,
                plan_id,
                ["MARK_NOT_ADMITTED_OR_STALE"],
            )
        mark_pointer, observation, row = admitted
        if (
            row.get("quote_status") != "available"
            or not isinstance(row.get("quote"), Mapping)
            or row.get("contract") != enrollment["payload"]["contract"]
            or lifecycle._stable_plan_identity(row.get("plan"))
            != lifecycle._stable_plan_identity(enrollment["payload"]["plan"])
        ):
            return (
                None,
                None,
                None,
                plan_id,
                ["MARK_RECEIPT_MISSING_OR_MISMATCHED"],
            )
        _utc(observation.get("observed_at_utc"), label="mark observation clock")
        _utc(row["quote"].get("quote_ts_utc"), label="mark quote clock")
        if not _all_false_mapping(enrollment.get("authority")) or not _all_false_mapping(
            observation.get("authority")
        ):
            reasons.append("ANY_UPSTREAM_AUTHORITY_TRUE")
        contract = _nbbo_contract(enrollment["payload"]["contract"])
        mark_evidence = _evidence_object(
            {
                "schema": "options.sparse_selector_mark_evidence/v1",
                "mark_pointer": mark_pointer,
                "observation": observation,
                "selected_plan_row": row,
                "authority": dict(FALSE_AUTHORITY),
            }
        )
        return mark_evidence, lifecycle_evidence, contract, plan_id, reasons

    if inputs.mark_root is None:
        return None, None, None, None, ["MARK_RECEIPT_MISSING_OR_MISMATCHED"]
    if inputs.lifecycle_root is None:
        return None, None, None, None, ["LIFECYCLE_RECEIPT_MISSING_OR_MISMATCHED"]
    mark_root = Path(inputs.mark_root).expanduser()
    lifecycle_root = Path(inputs.lifecycle_root).expanduser()
    reasons: list[str] = []
    try:
        lifecycle._validate_private_root_location(
            mark_root, label="private option mark evidence"
        )
        lifecycle._validate_private_root_location(
            lifecycle_root, label="private lifecycle state"
        )
        mark_chain._require_private_directory(mark_root)
        mark_chain._require_private_directory(lifecycle_root)
        with mark_chain._private_ledger_lock(lifecycle_root):
            ledger_path, receipt_path = lifecycle._ledger_paths(
                lifecycle_root,
                ledger_path=None,
                ledger_receipt_path=None,
                create=False,
            )
            ledger_body, ledger_rows, _ledger_receipt = lifecycle._read_ledger_snapshot(
                ledger_path, receipt_path
            )
            state = lifecycle._load_state(lifecycle_root)
            if state is None:
                _fail("lifecycle state is absent")
            lifecycle._validate_event_chain(lifecycle_root, state)
            lifecycle._validate_activation_boundary_against_state(lifecycle_root, state)
            lifecycle._validate_source_references(
                lifecycle_root=lifecycle_root,
                mark_root=mark_root,
                state=state,
                ledger_body=ledger_body,
                ledger_rows=ledger_rows,
            )
            matches: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
            for plan_id, pointer in state["enrollments"].items():
                enrollment = lifecycle._load_enrollment(
                    lifecycle_root, pointer, plan_id
                )
                contract = enrollment["payload"]["contract"]
                if _contract_matches_campaign(contract, candidate["campaign_row"]):
                    matches.append((plan_id, enrollment, pointer))
            terminal_matches = [
                item for item in matches if item[0] in state["terminals"]
            ]
            open_matches = [
                item for item in matches if item[0] not in state["terminals"]
            ]
            if terminal_matches:
                reasons.append("LIFECYCLE_ALREADY_TERMINAL")
                # The frozen selector rule abstains on any existing exact-
                # contract terminal.  A simultaneous open match is ambiguity,
                # never permission to propose another lifecycle.
                reasons.extend(
                    [
                        "EXACT_OCC_CONTRACT_MISSING_OR_INVALID",
                        "LIFECYCLE_RECEIPT_MISSING_OR_MISMATCHED",
                    ]
                )
                return None, None, None, None, reasons
            if len(open_matches) != 1:
                reasons.extend(
                    [
                        "EXACT_OCC_CONTRACT_MISSING_OR_INVALID",
                        "LIFECYCLE_RECEIPT_MISSING_OR_MISMATCHED",
                    ]
                )
                return None, None, None, None, reasons
            plan_id, enrollment, enrollment_pointer = open_matches[0]
            latest = state["latest_marks"].get(plan_id)
            if (
                not isinstance(latest, Mapping)
                or latest.get("contract_drift") is not False
                or latest.get("plan_identity_drift") is not False
                or latest.get("contract_occ_symbol")
                != enrollment["payload"]["contract"]["occ_symbol"]
            ):
                reasons.append("LIFECYCLE_NOT_DURABLE_OR_IDENTITY_DRIFT")
                return None, None, None, None, reasons
            session_text = decision_event_at.astimezone(ET).date().isoformat()
            mark_pointer = latest.get("sessions", {}).get(session_text)
            if not isinstance(mark_pointer, Mapping):
                reasons.append("MARK_NOT_ADMITTED_OR_STALE")
                lifecycle_evidence = _evidence_object(
                    {
                        "schema": "options.sparse_selector_lifecycle_evidence/v1",
                        "state": state,
                        "enrollment": enrollment,
                        "enrollment_pointer": enrollment_pointer,
                        "authority": dict(FALSE_AUTHORITY),
                    }
                )
                return None, lifecycle_evidence, None, plan_id, reasons
            observation = lifecycle._load_mark_observation(mark_root, mark_pointer)
            row = lifecycle._row_for_plan(observation, plan_id)
            if (
                row.get("quote_status") != "available"
                or not isinstance(row.get("quote"), Mapping)
                or row.get("contract") != enrollment["payload"]["contract"]
                or lifecycle._stable_plan_identity(row.get("plan"))
                != lifecycle._stable_plan_identity(enrollment["payload"]["plan"])
            ):
                reasons.append("MARK_RECEIPT_MISSING_OR_MISMATCHED")
                return None, None, None, plan_id, reasons
            _utc(observation.get("observed_at_utc"), label="mark observation clock")
            _utc(row["quote"].get("quote_ts_utc"), label="mark quote clock")
            if not _all_false_mapping(
                enrollment.get("authority")
            ) or not _all_false_mapping(observation.get("authority")):
                reasons.append("ANY_UPSTREAM_AUTHORITY_TRUE")
            contract = _nbbo_contract(enrollment["payload"]["contract"])
            mark_evidence = _evidence_object(
                {
                    "schema": "options.sparse_selector_mark_evidence/v1",
                    "mark_pointer": mark_pointer,
                    "observation": observation,
                    "selected_plan_row": row,
                    "authority": dict(FALSE_AUTHORITY),
                }
            )
            lifecycle_evidence = _evidence_object(
                {
                    "schema": "options.sparse_selector_lifecycle_evidence/v1",
                    "state": state,
                    "enrollment": enrollment,
                    "enrollment_pointer": enrollment_pointer,
                    "authority": dict(FALSE_AUTHORITY),
                }
            )
            return mark_evidence, lifecycle_evidence, contract, plan_id, reasons
    except (OSError, ValueError, KeyError, TypeError, SparseSelectorError):
        return (
            None,
            None,
            None,
            None,
            [
                "MARK_RECEIPT_MISSING_OR_MISMATCHED",
                "LIFECYCLE_RECEIPT_MISSING_OR_MISMATCHED",
            ],
        )


def _candidate_source_is_current(
    candidate: Mapping[str, Any],
    campaign_prefix: Mapping[str, Any],
    episode_prefix: Mapping[str, Any],
) -> bool:
    try:
        frozen_campaign = candidate["campaign_prefix"]
        frozen_episode = candidate["episode_prefix"]
        return (
            frozen_campaign["path"] == campaign_prefix["path"] == CAMPAIGNS_PATH
            and frozen_episode["path"] == episode_prefix["path"] == EPISODES_PATH
            and frozen_campaign["records"] <= campaign_prefix["records"]
            and frozen_campaign["bytes"] <= campaign_prefix["bytes"]
            and frozen_episode["records"] <= episode_prefix["records"]
            and frozen_episode["bytes"] <= episode_prefix["bytes"]
            and candidate["campaign_row_number"] <= campaign_prefix["records"]
            and candidate["campaign_row"]["members"][-1]["source_row"]
            <= episode_prefix["records"]
        )
    except (KeyError, IndexError, TypeError, SparseSelectorError):
        return False


def _ordered_reasons(reasons: Sequence[str]) -> list[str]:
    unknown = set(reasons) - set(ABSTENTION_REASON_CODES)
    if unknown:
        _fail(f"selector attempted an unregistered reason code: {sorted(unknown)}")
    return sorted(set(reasons), key=lambda reason: _REASON_ORDER[reason])


def _make_decision(
    *,
    ordinal: int,
    previous_decision: Mapping[str, Any] | None,
    manifest_id: str,
    candidate_pointer: Mapping[str, Any],
    action: str,
    reasons: Sequence[str],
    decision_event_at: str,
    evidence_verified_at: str,
    decision_available_at: str,
    session_date: str | None,
    proposal_ordinal: int | None,
    contract: Mapping[str, Any] | None,
    plan_id: str | None,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    decision: dict[str, Any] = {
        "schema": "options.sparse_selector_decision/v1",
        "decision_id": "",
        "ordinal": ordinal,
        "previous_decision": (
            copy.deepcopy(dict(previous_decision))
            if previous_decision is not None
            else None
        ),
        "manifest_id": manifest_id,
        "candidate": dict(candidate_pointer),
        "action": action,
        "reason_codes": _ordered_reasons(reasons),
        "decision_event_at": decision_event_at,
        "evidence_verified_at": evidence_verified_at,
        "decision_available_at": decision_available_at,
        "decision_nyse_session_date": session_date,
        "proposal_ordinal": proposal_ordinal,
        "proposal_cap": PROPOSAL_CAP,
        "contract": copy.deepcopy(contract),
        "plan_id": plan_id,
        "evidence": copy.deepcopy(dict(evidence)),
        "digests": dict(DIGESTS),
        "authority": dict(FALSE_AUTHORITY),
    }
    decision["decision_id"] = _content_id("ossd_", decision, field="decision_id")
    return validate_runtime_object(decision, label="selector decision")


def _settle_manifest(
    *,
    root: Path,
    manifest_pointer: Mapping[str, Any],
    campaign_prefix: Mapping[str, Any],
    episode_prefix: Mapping[str, Any],
    source_checkpoint: Mapping[str, Any],
    evidence_inputs: EvidenceInputs,
    previous_decision: Mapping[str, Any] | None,
    decision_count: int,
    proposal_session_date: str | None,
    proposal_session_count: int,
    clock: Callable[[], datetime],
    evidence_snapshot: EvidenceSnapshot | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[PlannedObject],
    dict[str, Any] | None,
    int,
    str | None,
    int,
]:
    manifest = _load_pointer(root, manifest_pointer, label="pending manifest")
    if manifest.get("schema") != "options.sparse_selector_candidate_manifest/v1":
        _fail("pending selector object is not a candidate manifest")
    if (
        manifest["source_campaign_prefix"]["records"] > campaign_prefix["records"]
        or manifest["source_campaign_prefix"]["bytes"] > campaign_prefix["bytes"]
        or manifest["source_episode_prefix"]["records"] > episode_prefix["records"]
        or manifest["source_episode_prefix"]["bytes"] > episode_prefix["bytes"]
        or manifest["source_checkpoint"] != dict(source_checkpoint)
    ):
        _fail("pending selector manifest escaped the authenticated source cursor")
    candidate_pointers = manifest["candidates"]
    if len(candidate_pointers) != manifest["candidate_count"]:
        _fail("pending selector manifest count drifted")
    candidate_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for pointer in candidate_pointers:
        candidate = _load_pointer(root, pointer, label="manifested candidate")
        if candidate.get("schema") != "options.sparse_selector_candidate/v1":
            _fail("manifest points outside the selector candidate contract")
        candidate_rows.append((dict(pointer), candidate))
    expected_order = sorted(
        candidate_rows,
        key=lambda pair: (pair[1]["candidate_available_at"], pair[1]["candidate_id"]),
    )
    if candidate_rows != expected_order:
        _fail("pending selector manifest candidate order drifted")
    if len(
        {candidate["candidate_id"] for _pointer, candidate in candidate_rows}
    ) != len(candidate_rows):
        _fail("pending selector manifest repeats a candidate")

    decisions: list[dict[str, Any]] = []
    objects: dict[str, PlannedObject] = {}
    decision_tail = (
        copy.deepcopy(dict(previous_decision))
        if previous_decision is not None
        else None
    )
    next_decision_count = decision_count
    session_state = proposal_session_date
    session_proposals = proposal_session_count
    if (
        type(session_proposals) is not int
        or not 0 <= session_proposals <= PROPOSAL_CAP
        or (session_state is None and session_proposals != 0)
    ):
        _fail("selector proposal session state is malformed")
    if evidence_snapshot is None:
        _assert_evidence_roots_distinct(root, evidence_inputs)
        evidence_snapshot = _build_evidence_snapshot(evidence_inputs)
    generation_fenced = _aware_utc(clock(), label="evidence generation fence")
    w1a_source_receipt = _make_w1a_source_receipt(
        snapshot=evidence_snapshot,
        manifest_pointer=manifest_pointer,
        candidate_rows=candidate_rows,
        captured_at=utc_text(generation_fenced),
    )
    if w1a_source_receipt is not None:
        objects[w1a_source_receipt.key] = w1a_source_receipt
    generation_object = _make_evidence_generation(
        snapshot=evidence_snapshot,
        w1a_source_receipt=w1a_source_receipt,
        manifest_pointer=manifest_pointer,
        fenced_at=utc_text(generation_fenced),
    )
    objects[generation_object.key] = generation_object
    for candidate_pointer, candidate in candidate_rows:
        decision_event = _aware_utc(clock(), label="decision event clock")
        if decision_event < generation_fenced:
            _fail("selector decision predates its evidence generation")
        event_text = utc_text(decision_event)
        reasons: list[str] = []
        if not _candidate_source_is_current(
            candidate, campaign_prefix, episode_prefix
        ):
            reasons.extend(
                [
                    "CAMPAIGN_PREFIX_RECEIPT_INVALID",
                    "OPTIONS_EVIDENCE_MISSING_OR_MISMATCHED",
                ]
            )
        if candidate.get("digests") != DIGESTS:
            reasons.append("BENCHMARK_DIGEST_MISSING_OR_MISMATCHED")
        if (
            candidate["campaign_row"].get("authority")
            != campaign_contract.FALSE_AUTHORITY
        ):
            reasons.append("ANY_UPSTREAM_AUTHORITY_TRUE")

        (
            mark_object,
            lifecycle_object,
            contract,
            plan_id,
            lifecycle_reasons,
        ) = _lifecycle_evidence(
            candidate,
            evidence_snapshot,
            decision_event_at=decision_event,
        )
        reasons.extend(lifecycle_reasons)
        if mark_object is None or lifecycle_object is None:
            contract = None
            plan_id = None
        # This clock is sampled only after the lifecycle/mark snapshot has been
        # read under its lock. It is the availability fence for every evidence
        # object used by this decision.
        evidence_probe_clock = _aware_utc(clock(), label="evidence probe clock")
        if (
            decision_event
            < _utc(candidate["candidate_available_at"], label="candidate availability")
            or evidence_probe_clock < decision_event
        ):
            _fail("selector decision or evidence clock is noncausal")
        konseki_object, konseki_reasons = _reference_for_candidate(
            candidate,
            evidence_snapshot,
            evidence_available_at=evidence_probe_clock,
        )
        reasons.extend(konseki_reasons)
        decision_available = _aware_utc(clock(), label="decision availability clock")
        if decision_available < evidence_probe_clock:
            _fail("selector decision availability precedes its evidence probe")
        available_text = utc_text(decision_available)
        if mark_object is not None:
            try:
                quote_at = _utc(
                    mark_object.value["selected_plan_row"]["quote"]["quote_ts_utc"],
                    label="selected mark quote clock",
                )
                observed_at = _utc(
                    mark_object.value["observation"]["observed_at_utc"],
                    label="selected mark observation clock",
                )
                if (
                    observed_at > evidence_probe_clock
                    or quote_at > observed_at
                ):
                    reasons.append("MARK_RECEIPT_MISSING_OR_MISMATCHED")
                    mark_object = None
            except (KeyError, TypeError, SparseSelectorError):
                reasons.append("MARK_RECEIPT_MISSING_OR_MISMATCHED")
                mark_object = None

        konseki_object = _compact_konseki_evidence(
            full=konseki_object,
            snapshot=evidence_snapshot,
            generation_pointer=generation_object.pointer,
            candidate_pointer=candidate_pointer,
        )
        mark_object = _compact_mark_evidence(
            full=mark_object,
            generation_pointer=generation_object.pointer,
            candidate_pointer=candidate_pointer,
            session_date=decision_event.astimezone(ET).date().isoformat(),
        )
        lifecycle_object = _compact_lifecycle_evidence(
            full=lifecycle_object,
            generation_pointer=generation_object.pointer,
            candidate_pointer=candidate_pointer,
        )

        session_date: str | None = None
        try:
            session_date = prereg.validate_proposal_decision_clock(
                decision_event_at=event_text,
                decision_available_at=available_text,
            )
        except prereg.RegistrationError:
            reasons.append("DECISION_OUTSIDE_NYSE_RTH")

        if session_date is not None:
            parsed_session = date.fromisoformat(session_date)
            if not nyse_calendar.is_session(parsed_session):
                _fail("selector proposal bucket is not a verified NYSE session")
            if session_state is None:
                session_state = session_date
                session_proposals = 0
            elif session_date < session_state:
                _fail("selector proposal session clock moved backward")
            elif session_date > session_state:
                prior_session = date.fromisoformat(session_state)
                transitions = nyse_calendar.sessions_between(
                    prior_session + timedelta(days=1), parsed_session
                )
                if not transitions or transitions[-1] != parsed_session:
                    _fail("selector proposal counter reset without a NYSE transition")
                session_state = session_date
                session_proposals = 0

        for item in (konseki_object, mark_object, lifecycle_object):
            if item is not None:
                objects[item.key] = item
        evidence = {
            "options": dict(candidate_pointer),
            "generation": generation_object.pointer,
            "konseki": konseki_object.pointer if konseki_object is not None else None,
            "mark": mark_object.pointer if mark_object is not None else None,
            "lifecycle": (
                lifecycle_object.pointer if lifecycle_object is not None else None
            ),
        }
        if any(evidence[name] is None for name in ("konseki", "mark", "lifecycle")):
            if (
                evidence["konseki"] is None
                and "KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED" not in reasons
            ):
                reasons.append("KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED")
            if (
                evidence["mark"] is None
                and "MARK_RECEIPT_MISSING_OR_MISMATCHED" not in reasons
            ):
                reasons.append("MARK_RECEIPT_MISSING_OR_MISMATCHED")
            if (
                evidence["lifecycle"] is None
                and "LIFECYCLE_RECEIPT_MISSING_OR_MISMATCHED" not in reasons
            ):
                reasons.append("LIFECYCLE_RECEIPT_MISSING_OR_MISMATCHED")
        if evidence["mark"] is None or evidence["lifecycle"] is None:
            contract = None
            plan_id = None

        action = "abstain"
        proposal_ordinal: int | None = None
        if not reasons and session_date is not None:
            if session_state != session_date:
                _fail("selector proposal session state did not advance exactly")
            if session_proposals >= PROPOSAL_CAP:
                reasons.append("SESSION_PROPOSAL_CAP_REACHED")
            else:
                proposal_ordinal = session_proposals + 1
                session_proposals = proposal_ordinal
                action = "propose"
        next_decision_count += 1
        decision = _make_decision(
            ordinal=next_decision_count,
            previous_decision=decision_tail,
            manifest_id=manifest["manifest_id"],
            candidate_pointer=candidate_pointer,
            action=action,
            reasons=reasons,
            decision_event_at=event_text,
            evidence_verified_at=utc_text(evidence_probe_clock),
            decision_available_at=available_text,
            session_date=session_date,
            proposal_ordinal=proposal_ordinal,
            contract=contract,
            plan_id=plan_id,
            evidence=evidence,
        )
        decisions.append(decision)
        decision_object = PlannedObject(
            key=f"decisions/{decision['decision_id']}.json", value=decision
        )
        objects[decision_object.key] = decision_object
        decision_tail = decision_object.pointer
    if len(decisions) != manifest["candidate_count"]:
        _fail("selector failed exact one-to-one decision reconciliation")
    return (
        decisions,
        list(objects.values()),
        decision_tail,
        next_decision_count,
        session_state,
        session_proposals,
    )


def _cycle_id(
    *,
    ordinal: int,
    scheduled_at: str,
    started_at: str,
    source_commit: str,
    previous_head_id: str | None,
) -> str:
    return "oscy_" + _sha256(
        canonical_bytes(
            {
                "rule_id": RULE_ID,
                "ordinal": ordinal,
                "scheduled_at": scheduled_at,
                "started_at": started_at,
                "source_commit": source_commit,
                "previous_head_id": previous_head_id,
            }
        )
    )


def _make_handoff_queue_item(
    *,
    root: Path,
    ordinal: int,
    previous_queue_item: Mapping[str, Any] | None,
    previous_queue_value: Mapping[str, Any] | None,
    previous_cycle: Mapping[str, Any] | None,
    cycle_object: PlannedObject,
) -> dict[str, Any]:
    cycle = validate_runtime_object(
        cycle_object.value, label="selector handoff queue cycle"
    )
    if cycle.get("schema") != "options.sparse_selector_cycle_receipt/v1":
        _fail("selector handoff queue source is not a cycle")
    if cycle["runtime_armed"] is not True:
        _fail("selector cannot queue a code-unarmed cycle")
    cycle_pointer = cycle_object.pointer
    prior_pointer = (
        copy.deepcopy(dict(previous_cycle)) if previous_cycle is not None else None
    )
    prior_queue_pointer = (
        copy.deepcopy(dict(previous_queue_item))
        if previous_queue_item is not None
        else None
    )
    skips: list[dict[str, Any]] = []
    if prior_queue_pointer is not None:
        if previous_queue_value is None:
            _fail("selector queue skip index lacks its predecessor value")
        skips.append(prior_queue_pointer)
        # Node n's 2**k ancestor is node (n-2**(k-1))'s own 2**(k-1)
        # ancestor. Resolve only logarithmically many immutable nodes.
        source_value = previous_queue_value
        for level in range(1, (ordinal - 1).bit_length()):
            source_pointer = skips[level - 1]
            source_value = _load_pointer(
                root,
                source_pointer,
                label="selector queue skip ancestor",
            )
            skips.append(
                copy.deepcopy(dict(source_value["skip_queue_items"][level - 1]))
            )
    item: dict[str, Any] = {
        "schema": "options.sparse_selector_handoff_queue_item/v1",
        "queue_item_id": "",
        "ordinal": ordinal,
        "previous_queue_item_id": (
            None if prior_queue_pointer is None else prior_queue_pointer["id"]
        ),
        "previous_queue_item": prior_queue_pointer,
        "skip_queue_items": skips,
        "previous_cycle": prior_pointer,
        "selector_cycle": cycle_pointer,
        "runtime_armed": True,
        "producer_rule_sha256": SELECTOR_RULE_SHA256,
        "authority": dict(FALSE_AUTHORITY),
    }
    item["queue_item_id"] = _handoff_queue_item_id(item)
    return validate_runtime_object(item, label="selector handoff queue item")


def _make_manifest(
    *,
    cycle_id: str,
    frozen_at: str,
    source: SourceSnapshot,
    campaign_prefix: Mapping[str, Any],
    episode_prefix: Mapping[str, Any],
    source_checkpoint: Mapping[str, Any],
    candidates: Sequence[PlannedObject],
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema": "options.sparse_selector_candidate_manifest/v1",
        "manifest_id": "",
        "cycle_id": cycle_id,
        "frozen_at": frozen_at,
        "source_commit": source.commit,
        "source_campaign_prefix": dict(campaign_prefix),
        "source_episode_prefix": dict(episode_prefix),
        "source_checkpoint": dict(source_checkpoint),
        "candidate_count": len(candidates),
        "candidates": [candidate.pointer for candidate in candidates],
        "digests": dict(DIGESTS),
        "authority": dict(FALSE_AUTHORITY),
    }
    manifest["manifest_id"] = _content_id("ossm_", manifest, field="manifest_id")
    return validate_runtime_object(manifest, label="selector candidate manifest")


def _empty_candidate_index() -> dict[str, Any]:
    return private_auth_dict.sharded_root_receipt(
        domain=CANDIDATE_INDEX_DOMAIN, root=None, entry_count=0
    )


def _empty_source_candidate_index() -> dict[str, Any]:
    return private_auth_dict.sharded_root_receipt(
        domain=SOURCE_CANDIDATE_INDEX_DOMAIN, root=None, entry_count=0
    )


def _empty_source_campaign_history_index() -> dict[str, Any]:
    return private_auth_dict.sharded_root_receipt(
        domain=SOURCE_CAMPAIGN_HISTORY_DOMAIN, root=None, entry_count=0
    )


def _empty_source_episode_identity_index() -> dict[str, Any]:
    return private_auth_dict.sharded_root_receipt(
        domain=SOURCE_EPISODE_IDENTITY_DOMAIN, root=None, entry_count=0
    )


def _empty_source_episode_group_index() -> dict[str, Any]:
    return private_auth_dict.sharded_root_receipt(
        domain=SOURCE_EPISODE_GROUP_DOMAIN, root=None, entry_count=0
    )


def _make_campaign_source_window(
    *,
    source: SourceSnapshot,
    source_checkpoint: Mapping[str, Any],
    campaign_prefix: Mapping[str, Any],
    episode_prefix: Mapping[str, Any],
    rows: Sequence[JsonlRow],
    first_byte: int,
) -> dict[str, Any]:
    if not rows or len(rows) > 128:
        _fail("selector campaign recovery window row count is outside its bound")
    cursor = first_byte
    payload_rows: list[dict[str, Any]] = []
    for row in rows:
        cursor += len(row.raw) + 1
        payload_rows.append(
            {
                "ordinal": row.ordinal,
                "end_byte": cursor,
                "row": copy.deepcopy(row.value),
                "row_sha256": _sha256(row.raw),
            }
        )
    window: dict[str, Any] = {
        "schema": "options.sparse_selector_campaign_window/v1",
        "window_id": "",
        "source_commit": source.commit,
        "source_observed_at": source.observed_at,
        "source_checkpoint": copy.deepcopy(dict(source_checkpoint)),
        "source_campaign_prefix": copy.deepcopy(dict(campaign_prefix)),
        "source_episode_prefix": copy.deepcopy(dict(episode_prefix)),
        "first_row": rows[0].ordinal,
        "last_row": rows[-1].ordinal,
        "first_byte": first_byte,
        "last_byte": cursor,
        "rows": payload_rows,
        "authority": dict(FALSE_AUTHORITY),
    }
    window["window_id"] = _content_id("oscw_", window, field="window_id")
    return _validate_campaign_source_window(window)


def _validate_campaign_source_window(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "schema",
        "window_id",
        "source_commit",
        "source_observed_at",
        "source_checkpoint",
        "source_campaign_prefix",
        "source_episode_prefix",
        "first_row",
        "last_row",
        "first_byte",
        "last_byte",
        "rows",
        "authority",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        _fail("selector campaign recovery window fields are malformed")
    clean = copy.deepcopy(dict(value))
    rows = clean["rows"]
    if (
        clean["schema"] != "options.sparse_selector_campaign_window/v1"
        or clean["window_id"] != _content_id("oscw_", clean, field="window_id")
        or clean["authority"] != FALSE_AUTHORITY
        or not isinstance(clean["source_commit"], str)
        or _COMMIT_RE.fullmatch(clean["source_commit"]) is None
        or type(clean["first_row"]) is not int
        or type(clean["last_row"]) is not int
        or type(clean["first_byte"]) is not int
        or type(clean["last_byte"]) is not int
        or clean["first_row"] < 1
        or clean["last_row"] < clean["first_row"]
        or clean["first_byte"] < 0
        or clean["last_byte"] <= clean["first_byte"]
        or not isinstance(rows, list)
        or not rows
        or len(rows) > MAX_CAMPAIGN_SOURCE_ROWS_PER_CYCLE
        or len(rows) != clean["last_row"] - clean["first_row"] + 1
    ):
        _fail("selector campaign recovery window binding drifted")
    _utc(clean["source_observed_at"], label="campaign window observation")
    prior_end = clean["first_byte"]
    expected_row = clean["first_row"]
    for item in rows:
        if not isinstance(item, Mapping) or set(item) != {
            "ordinal",
            "end_byte",
            "row",
            "row_sha256",
        }:
            _fail("selector campaign recovery window row is malformed")
        raw = canonical_bytes(item["row"])
        if (
            item["ordinal"] != expected_row
            or type(item["end_byte"]) is not int
            or item["end_byte"] <= prior_end
            or item["row_sha256"] != _sha256(raw)
            or item["end_byte"] - prior_end != len(raw) + 1
        ):
            _fail("selector campaign recovery window row binding drifted")
        try:
            campaign_contract.validate_campaign(item["row"])
        except campaign_contract.CampaignContractError as exc:
            raise SparseSelectorError(
                "selector campaign recovery window row is invalid"
            ) from exc
        prior_end = item["end_byte"]
        expected_row += 1
    if prior_end != clean["last_byte"]:
        _fail("selector campaign recovery window terminal offset drifted")
    return clean


def _source_transition_intent(
    *,
    head: Mapping[str, Any] | None,
    next_head: Mapping[str, Any],
    objects: Sequence[PlannedObject],
    source_window: Mapping[str, Any],
) -> CyclePlan:
    ordered = tuple(sorted(objects, key=lambda item: item.key))
    if len(ordered) > MAX_SOURCE_OBJECTS_PER_CYCLE:
        _fail("selector source transition exceeds its object cap")
    previous_head_id = None if head is None else head["head_id"]
    expected_source_state = None if head is None else _source_expected_state(head)
    intent: dict[str, Any] = {
        "schema": "options.sparse_selector_source_intent/v1",
        "intent_sha256": "",
        "expected_head_id": previous_head_id,
        "expected_last_handoff_queue": (
            None if head is None else copy.deepcopy(head["last_handoff_queue"])
        ),
        "expected_last_candidate": (
            None if head is None else copy.deepcopy(head["last_candidate"])
        ),
        "expected_candidate_count": 0 if head is None else head["candidate_count"],
        "expected_candidate_index": (
            _empty_candidate_index()
            if head is None
            else copy.deepcopy(head["candidate_index"])
        ),
        "expected_last_decision": (
            None if head is None else copy.deepcopy(head["last_decision"])
        ),
        "expected_decision_count": 0 if head is None else head["decision_count"],
        "expected_source_state": expected_source_state,
        "expected_runtime_state": _runtime_expected_state(head),
        "source_window": copy.deepcopy(dict(source_window)),
        "objects": [
            {
                "key": item.key,
                "sha256": _sha256(item.body),
                "bytes": len(item.body),
                "value": item.value,
            }
            for item in ordered
        ],
        "next_head": copy.deepcopy(dict(next_head)),
    }
    intent["intent_sha256"] = _content_id("", intent, field="intent_sha256")
    if len(canonical_bytes(intent)) > MAX_SOURCE_INTENT_BYTES:
        _fail("selector source intent exceeds its recovery bound")
    return CyclePlan(
        expected_head_id=previous_head_id,
        objects=ordered,
        head=copy.deepcopy(dict(next_head)),
        intent=intent,
    )


def _base_source_head(
    *,
    head: Mapping[str, Any] | None,
    advanced_at: str,
    source: SourceSnapshot,
    campaign_prefix: Mapping[str, Any],
    episode_prefix: Mapping[str, Any],
    source_checkpoint: Mapping[str, Any],
    phase: str,
    audit_stage: str,
    audit_cursor: int,
    campaign_cursor_bytes: int,
    episode_cursor_records: int,
    episode_cursor_bytes: int,
    episode_chunks: Sequence[Mapping[str, Any]],
    episode_identity_index: Mapping[str, Any],
    episode_group_index: Mapping[str, Any],
    episode_group_count: int,
    run_manifests: Sequence[Mapping[str, Any]],
    run_cursors: Sequence[int],
    source_candidate_index: Mapping[str, Any],
    source_campaign_history_index: Mapping[str, Any],
    ready_run: Mapping[str, Any] | None,
    ready_count: int,
    ready_cursor: int,
) -> dict[str, Any]:
    next_head: dict[str, Any] = {
        "schema": "options.sparse_selector_head/v1",
        "head_id": "",
        "generation": 1 if head is None else head["generation"] + 1,
        "previous_head_id": None if head is None else head["head_id"],
        "advanced_at": advanced_at,
        "source_observed_at": source.observed_at,
        "source_commit": source.commit,
        "source_campaign_prefix": copy.deepcopy(dict(campaign_prefix)),
        "source_episode_prefix": copy.deepcopy(dict(episode_prefix)),
        "source_checkpoint": copy.deepcopy(dict(source_checkpoint)),
        "source_phase": phase,
        "source_audit_stage": audit_stage,
        "source_campaign_cursor_records": audit_cursor,
        "source_campaign_cursor_bytes": campaign_cursor_bytes,
        "source_episode_cursor_records": episode_cursor_records,
        "source_episode_cursor_bytes": episode_cursor_bytes,
        "source_episode_chunks": [
            copy.deepcopy(dict(item)) for item in episode_chunks
        ],
        "source_episode_identity_index": copy.deepcopy(
            dict(episode_identity_index)
        ),
        "source_episode_group_index": copy.deepcopy(dict(episode_group_index)),
        "source_episode_group_count": episode_group_count,
        "source_projection_next": (
            copy.deepcopy(dict(ready_run))
            if ready_run is not None and ready_cursor < ready_count
            else None
        ),
        "source_run_manifests": [copy.deepcopy(dict(item)) for item in run_manifests],
        "source_run_cursors": list(run_cursors),
        "source_candidate_index": copy.deepcopy(dict(source_candidate_index)),
        "source_campaign_history_index": copy.deepcopy(
            dict(source_campaign_history_index)
        ),
        "source_ready_run": (
            None if ready_run is None else copy.deepcopy(dict(ready_run))
        ),
        "source_ready_count": ready_count,
        "source_ready_cursor": ready_cursor,
        "pending_manifest": None if head is None else copy.deepcopy(head["pending_manifest"]),
        "last_cycle": None if head is None else copy.deepcopy(head["last_cycle"]),
        "cycle_count": 0 if head is None else head["cycle_count"],
        "handoff_queue_count": 0 if head is None else head["handoff_queue_count"],
        "last_handoff_queue": (
            None if head is None else copy.deepcopy(head["last_handoff_queue"])
        ),
        "last_candidate": None if head is None else copy.deepcopy(head["last_candidate"]),
        "candidate_count": 0 if head is None else head["candidate_count"],
        "candidate_index": (
            _empty_candidate_index()
            if head is None
            else copy.deepcopy(head["candidate_index"])
        ),
        "last_decision": None if head is None else copy.deepcopy(head["last_decision"]),
        "decision_count": 0 if head is None else head["decision_count"],
        "proposal_session_date": (
            None if head is None else head["proposal_session_date"]
        ),
        "proposal_session_count": (
            0 if head is None else head["proposal_session_count"]
        ),
        "w1a_publication_high_water": (
            None
            if head is None
            else copy.deepcopy(head["w1a_publication_high_water"])
        ),
        "digests": dict(DIGESTS),
        "authority": dict(FALSE_AUTHORITY),
    }
    next_head["head_id"] = _content_id("ossh_", next_head, field="head_id")
    return validate_runtime_object(next_head, label="selector source HEAD")


def _merge_source_runs(
    *,
    root: Path,
    source: SourceSnapshot,
    source_checkpoint: Mapping[str, Any],
    pointers: Sequence[Mapping[str, Any]],
    planned: Mapping[str, PlannedObject] | None = None,
) -> PlannedObject:
    if not pointers or len(pointers) > MAX_MERGE_FAN_IN:
        _fail("selector source merge fan-in is outside its bound")
    entries: list[Mapping[str, Any]] = []
    levels: list[int] = []
    first_rows: list[int] = []
    last_rows: list[int] = []
    seen: set[str] = set()
    for pointer in pointers:
        item = None if planned is None else planned.get(str(pointer.get("id")))
        run = (
            _validate_source_run(item.value)
            if item is not None and item.pointer == pointer
            else _load_source_run(root, pointer)
        )
        if (
            run["source_commit"] != source.commit
            or run["source_observed_at"] != source.observed_at
            or run["source_checkpoint"] != dict(source_checkpoint)
        ):
            _fail("selector source merge crossed epochs")
        for entry in run["entries"]:
            if entry["candidate_id"] in seen:
                _fail("selector source merge repeats a candidate")
            seen.add(entry["candidate_id"])
            entries.append(entry)
        levels.append(run["level"])
        first_rows.append(run["first_source_row"])
        last_rows.append(run["last_source_row"])
    return _make_source_run(
        level=max(levels) + 1,
        source=source,
        source_checkpoint=source_checkpoint,
        first_source_row=min(first_rows),
        last_source_row=max(last_rows),
        entries=entries,
    )


def _pin_source_epoch(
    source: SourceSnapshot,
    *,
    previous_campaign_prefix: Mapping[str, Any] | None,
    previous_episode_prefix: Mapping[str, Any] | None,
    previous_checkpoint: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], int, int]:
    """Authenticate immutable Git bytes once, without parsing their backlog."""

    if not isinstance(source.commit, str) or _COMMIT_RE.fullmatch(source.commit) is None:
        _fail("source commit is malformed")
    _utc(source.observed_at, label="source observation clock")
    campaigns_raw = source.campaigns_raw
    episodes_raw = source.episodes_raw
    if campaigns_raw is None or episodes_raw is None or source.checkpoint_raw is None:
        _fail("new selector source epoch requires exact Git object bytes")
    if len(campaigns_raw) + len(episodes_raw) > MAX_SOURCE_BYTES:
        _fail("selector source pair exceeds its byte cap")
    for raw, label in ((campaigns_raw, "campaign"), (episodes_raw, "episode")):
        if raw and not raw.endswith(b"\n"):
            _fail(f"selector {label} source has a torn final row")
    campaign_oid = _source_blob_oid(
        campaigns_raw, source.campaigns_blob_oid, label="campaign source"
    )
    episode_oid = _source_blob_oid(
        episodes_raw, source.episodes_blob_oid, label="episode source"
    )
    if _git_blob_oid(campaigns_raw) != campaign_oid:
        _fail("campaign source bytes differ from their Git blob object id")
    if _git_blob_oid(episodes_raw) != episode_oid:
        _fail("episode source bytes differ from their Git blob object id")
    campaign_prefix = _source_receipt(
        campaigns_raw,
        path=CAMPAIGNS_PATH,
        records=campaigns_raw.count(b"\n"),
        git_blob_oid=campaign_oid,
    )
    episode_prefix = _source_receipt(
        episodes_raw,
        path=EPISODES_PATH,
        records=episodes_raw.count(b"\n"),
        git_blob_oid=episode_oid,
    )
    previous_records, previous_bytes = _validate_previous_prefix(
        campaigns_raw, previous_campaign_prefix, path=CAMPAIGNS_PATH
    )
    _validate_previous_prefix(
        episodes_raw, previous_episode_prefix, path=EPISODES_PATH
    )
    checkpoint = _validate_campaign_checkpoint(
        source,
        campaign_prefix=campaign_prefix,
        episode_prefix=episode_prefix,
        previous_checkpoint=previous_checkpoint,
    )
    return (
        campaign_prefix,
        episode_prefix,
        checkpoint,
        previous_records,
        previous_bytes,
    )


def _pinned_audit_source(
    source: SourceSnapshot,
    head: Mapping[str, Any],
) -> tuple[bytes, bytes]:
    """Check an audit continuation against the pinned epoch in constant space."""

    campaigns_raw = source.campaigns_raw
    episodes_raw = source.episodes_raw
    if campaigns_raw is None or episodes_raw is None:
        _fail("selector source audit continuation requires ledger bytes")
    if (
        source.commit != head["source_commit"]
        or source.observed_at != head["source_observed_at"]
        or len(campaigns_raw) != head["source_campaign_prefix"]["bytes"]
        or len(episodes_raw) != head["source_episode_prefix"]["bytes"]
        or source.campaigns_blob_oid not in (
            None,
            head["source_campaign_prefix"]["git_blob_oid"],
        )
        or source.episodes_blob_oid not in (
            None,
            head["source_episode_prefix"]["git_blob_oid"],
        )
        or source.checkpoint_blob_oid not in (
            None,
            head["source_checkpoint"]["git_blob_oid"],
        )
        or len(campaigns_raw) + len(episodes_raw) > MAX_SOURCE_BYTES
    ):
        _fail("selector source audit continuation changed its pinned epoch")
    if source.checkpoint_raw is not None and (
        _sha256(source.checkpoint_raw) != head["source_checkpoint"]["sha256"]
        or _git_blob_oid(source.checkpoint_raw)
        != head["source_checkpoint"]["git_blob_oid"]
    ):
        _fail("selector source checkpoint changed during its audit")
    if (
        _sha256(campaigns_raw) != head["source_campaign_prefix"]["sha256"]
        or _git_blob_oid(campaigns_raw)
        != head["source_campaign_prefix"]["git_blob_oid"]
        or _sha256(episodes_raw) != head["source_episode_prefix"]["sha256"]
        or _git_blob_oid(episodes_raw)
        != head["source_episode_prefix"]["git_blob_oid"]
    ):
        _fail("selector source audit bytes changed under their pinned receipts")
    return campaigns_raw, episodes_raw


def _verify_completed_source_epoch(
    campaigns_raw: bytes,
    episodes_raw: bytes,
    *,
    campaign_prefix: Mapping[str, Any],
    episode_prefix: Mapping[str, Any],
) -> None:
    """Recheck the full immutable receipts before any candidate can be admitted."""

    if (
        _sha256(campaigns_raw) != campaign_prefix["sha256"]
        or _git_blob_oid(campaigns_raw) != campaign_prefix["git_blob_oid"]
        or _sha256(episodes_raw) != episode_prefix["sha256"]
        or _git_blob_oid(episodes_raw) != episode_prefix["git_blob_oid"]
    ):
        _fail("selector source changed before its bounded audit completed")


def _plan_source_audit_transition(
    *,
    root: Path,
    head: Mapping[str, Any] | None,
    source: SourceSnapshot,
    clock: Callable[[], datetime],
) -> CyclePlan:
    if head is not None and head["source_phase"] not in {"AUDITING", "DRAINED"}:
        _fail("selector source audit phase drifted")
    new_epoch = head is None or head["source_phase"] == "DRAINED"
    if new_epoch:
        if head is not None:
            if _utc(
                source.observed_at, label="new source epoch observation clock"
            ) <= _utc(
                head["source_observed_at"], label="prior source epoch observation clock"
            ):
                _fail("new selector source epoch did not advance its observation clock")
            if head["last_candidate"] is not None:
                tail = _load_pointer(
                    root,
                    head["last_candidate"],
                    label="prior source epoch candidate tail",
                )
                if source.observed_at <= tail["candidate_available_at"]:
                    _fail("new selector source epoch does not sort after its candidate tail")
        (
            campaign_prefix,
            episode_prefix,
            source_checkpoint,
            campaign_cursor,
            campaign_cursor_bytes,
        ) = _pin_source_epoch(
            source,
            previous_campaign_prefix=(
                None if head is None else head["source_campaign_prefix"]
            ),
            previous_episode_prefix=(
                None if head is None else head["source_episode_prefix"]
            ),
            previous_checkpoint=None if head is None else head["source_checkpoint"],
        )
        # Every immutable checkpoint epoch receives its own authenticated
        # indexes and chunks.  An append relation is a rollback guard, not
        # authority to skip re-auditing the new checkpoint's prefix.
        campaign_cursor = 0
        campaign_cursor_bytes = 0
        assert source.campaigns_raw is not None and source.episodes_raw is not None
        campaigns_raw = source.campaigns_raw
        episodes_raw = source.episodes_raw
        episode_cursor = 0
        episode_cursor_bytes = 0
        episode_chunks: list[dict[str, Any]] = []
        run_pointers: list[dict[str, Any]] = []
        run_cursors: list[int] = []
        source_candidate_index = _empty_source_candidate_index()
        source_campaign_history_index = _empty_source_campaign_history_index()
        episode_identity_index = _empty_source_episode_identity_index()
        episode_group_index = _empty_source_episode_group_index()
        episode_group_count = 0
        audit_stage = "EPISODES" if episode_prefix["records"] else "CAMPAIGNS"
    else:
        assert head is not None
        campaigns_raw, episodes_raw = _pinned_audit_source(source, head)
        campaign_prefix = copy.deepcopy(dict(head["source_campaign_prefix"]))
        episode_prefix = copy.deepcopy(dict(head["source_episode_prefix"]))
        source_checkpoint = copy.deepcopy(dict(head["source_checkpoint"]))
        campaign_cursor = head["source_campaign_cursor_records"]
        campaign_cursor_bytes = head["source_campaign_cursor_bytes"]
        episode_cursor = head["source_episode_cursor_records"]
        episode_cursor_bytes = head["source_episode_cursor_bytes"]
        episode_chunks = [
            copy.deepcopy(dict(item)) for item in head["source_episode_chunks"]
        ]
        run_pointers = [
            copy.deepcopy(dict(item)) for item in head["source_run_manifests"]
        ]
        run_cursors = list(head["source_run_cursors"])
        source_candidate_index = private_auth_dict.validate_sharded_root(
            head["source_candidate_index"], domain=SOURCE_CANDIDATE_INDEX_DOMAIN
        )
        source_campaign_history_index = private_auth_dict.validate_sharded_root(
            head["source_campaign_history_index"],
            domain=SOURCE_CAMPAIGN_HISTORY_DOMAIN,
        )
        episode_identity_index = private_auth_dict.validate_sharded_root(
            head["source_episode_identity_index"],
            domain=SOURCE_EPISODE_IDENTITY_DOMAIN,
        )
        episode_group_index = private_auth_dict.validate_sharded_root(
            head["source_episode_group_index"],
            domain=SOURCE_EPISODE_GROUP_DOMAIN,
        )
        episode_group_count = head["source_episode_group_count"]
        audit_stage = head["source_audit_stage"]

    objects: dict[str, PlannedObject] = {}
    source_window: dict[str, Any] = {"stage": "NONE"}
    if audit_stage == "EPISODES":
        rows, next_byte = _decode_jsonl_window(
            episodes_raw,
            label="selector episode source",
            start_byte=episode_cursor_bytes,
            start_record=episode_cursor,
            max_rows=128,
        )
        for row in rows:
            try:
                campaign_contract.validate_episode(row.value)
            except campaign_contract.CampaignContractError as exc:
                raise SparseSelectorError("selector episode source row is invalid") from exc
        if rows:
            identity_entries = [
                entry
                for row in rows
                for entry in (
                    (
                        _source_episode_id_key(row.value["episode_id"]),
                        {"episode_id": row.value["episode_id"], "source_row": row.ordinal},
                    ),
                    (
                        _source_episode_event_key(
                            row.value["source"], row.value["source_event_id"]
                        ),
                        {
                            "source": row.value["source"],
                            "source_event_id": row.value["source_event_id"],
                            "episode_id": row.value["episode_id"],
                            "source_row": row.ordinal,
                        },
                    ),
                )
            ]
            try:
                    episode_identity_index, identity_nodes = (
                        private_auth_dict.sharded_insert_many(
                        episode_identity_index,
                        identity_entries,
                        domain=SOURCE_EPISODE_IDENTITY_DOMAIN,
                        load_node=lambda pointer: _load_source_episode_identity_node(
                            root, pointer
                        ),
                    )
                )
            except private_auth_dict.AuthDictError as exc:
                raise SparseSelectorError(
                    "selector episode source repeats an identity"
                ) from exc
            for node in identity_nodes:
                item = PlannedObject(
                    key=f"{private_auth_dict.NAMESPACE}/{node['node_id']}.json",
                    value=node,
                )
                objects[item.key] = item
            group_latest: dict[tuple[str, ...], dict[str, Any]] = {}
            group_members: list[tuple[Sequence[str], Mapping[str, Any]]] = []
            new_group_count = 0
            group_node_cache = private_auth_dict.ShardedLookupCache.empty(
                SOURCE_EPISODE_GROUP_DOMAIN
            )
            for row in rows:
                group = tuple(_source_episode_group_parts(row.value))
                latest = group_latest.get(group)
                if latest is None:
                    lookup = _source_episode_group_lookup(
                        root,
                        episode_group_index,
                        _source_episode_group_latest_key(group),
                        node_cache=group_node_cache,
                    )
                    latest = (
                        {"member_count": 0, "last_source_row": 0}
                        if not lookup.found
                        else copy.deepcopy(dict(lookup.binding))
                    )
                    if not lookup.found:
                        new_group_count += 1
                member_ordinal = latest["member_count"] + 1
                if row.ordinal <= latest["last_source_row"]:
                    _fail("selector episode group source order moved backward")
                group_members.append(
                    (
                        _source_episode_group_member_key(group, member_ordinal),
                        {
                            "episode_id": row.value["episode_id"],
                            "source_row": row.ordinal,
                            "source_row_sha256": _sha256(row.raw),
                        },
                    )
                )
                group_latest[group] = {
                    "member_count": member_ordinal,
                    "last_source_row": row.ordinal,
                }
            group_entries = group_members + [
                (_source_episode_group_latest_key(group), binding)
                for group, binding in sorted(group_latest.items())
            ]
            try:
                episode_group_index, group_nodes = (
                    private_auth_dict.sharded_insert_many(
                        episode_group_index,
                        group_entries,
                        domain=SOURCE_EPISODE_GROUP_DOMAIN,
                        load_node=lambda pointer: _load_source_episode_group_node(
                            root, pointer
                        ),
                        replace_existing=lambda key: (
                            isinstance(key, list)
                            and bool(key)
                            and key[0] == "selector_source_episode_group_latest"
                        ),
                        cache=group_node_cache,
                    )
                )
            except private_auth_dict.AuthDictError as exc:
                raise SparseSelectorError(
                    "selector episode group index is inconsistent"
                ) from exc
            for node in group_nodes:
                item = PlannedObject(
                    key=f"{private_auth_dict.NAMESPACE}/{node['node_id']}.json",
                    value=node,
                )
                objects[item.key] = item
            episode_group_count += new_group_count
        if rows:
            chunk = _make_episode_chunk(
                source=source,
                source_checkpoint=source_checkpoint,
                rows=rows,
                first_byte=episode_cursor_bytes,
                last_byte=next_byte,
            )
            objects[chunk.key] = chunk
            episode_chunks.append(
                {
                    "pointer": chunk.pointer,
                    "first_row": chunk.value["first_row"],
                    "last_row": chunk.value["last_row"],
                    "first_byte": chunk.value["first_byte"],
                    "last_byte": chunk.value["last_byte"],
                }
            )
            source_window = {"stage": "EPISODES", "chunk": chunk.pointer}
            episode_cursor += len(rows)
            episode_cursor_bytes = next_byte
        if episode_cursor == episode_prefix["records"]:
            if episode_cursor_bytes != episode_prefix["bytes"]:
                _fail("selector episode source count/byte receipt drifted")
            audit_stage = "CAMPAIGNS"
    elif audit_stage == "CAMPAIGNS":
        rows, _window_end = _decode_jsonl_window(
            campaigns_raw,
            label="selector campaign source",
            start_byte=campaign_cursor_bytes,
            start_record=campaign_cursor,
            max_rows=MAX_CAMPAIGN_SOURCE_ROWS_PER_CYCLE,
        )
        effective = max(
            _utc(BENCHMARK_EFFECTIVE_FREEZE_AT, label="benchmark freeze"),
            _utc(SELECTOR_EFFECTIVE_FREEZE_AT, label="selector freeze"),
        )
        selected: list[tuple[JsonlRow, str]] = []
        selected_campaign_ids: set[str] = set()
        source_index_cache = private_auth_dict.ShardedLookupCache.empty(
            SOURCE_CANDIDATE_INDEX_DOMAIN
        )
        history_index_cache = private_auth_dict.ShardedLookupCache.empty(
            SOURCE_CAMPAIGN_HISTORY_DOMAIN
        )
        history_entries: list[tuple[Sequence[str], Mapping[str, Any]]] = []
        local_latest: dict[str, dict[str, Any]] = {}
        local_revisions: set[str] = set()
        prefix_digest_cache = _episode_prefix_digests(
            episodes_raw,
            {
                row.value["source_episode_prefix"]["records"]
                for row in rows
            },
            source_checkpoint=source_checkpoint,
        )
        episode_chunk_cache: dict[str, dict[str, Any]] = {}
        group_node_cache = private_auth_dict.ShardedLookupCache.empty(
            SOURCE_EPISODE_GROUP_DOMAIN
        )
        candidate_index_cache = private_auth_dict.ShardedLookupCache.empty(
            CANDIDATE_INDEX_DOMAIN
        )
        for row in rows:
            try:
                campaign_contract.validate_campaign(row.value)
            except campaign_contract.CampaignContractError as exc:
                raise SparseSelectorError("selector campaign source row is invalid") from exc
            _validate_campaign_against_episode_index(
                root,
                row.value,
                episode_chunks,
                source_commit=source.commit,
                source_observed_at=source.observed_at,
                source_checkpoint=source_checkpoint,
                episodes_raw=episodes_raw,
                prefix_digest_cache=prefix_digest_cache,
                episode_group_index=episode_group_index,
                episode_chunk_cache=episode_chunk_cache,
                group_node_cache=group_node_cache,
            )
            campaign_id = row.value["campaign_id"]
            revision_id = row.value["campaign_revision_id"]
            if revision_id in local_revisions or _source_campaign_history_lookup(
                root,
                source_campaign_history_index,
                _source_campaign_revision_key(revision_id),
                node_cache=history_index_cache,
            ).found:
                _fail("selector source campaign repeats a revision")
            prior = local_latest.get(campaign_id)
            if prior is None:
                expected_prior_number = row.value["revision_number"] - 1
                prior_lookup = _source_campaign_history_lookup(
                    root,
                    source_campaign_history_index,
                    _source_campaign_latest_key(campaign_id, expected_prior_number),
                    node_cache=history_index_cache,
                )
                prior = prior_lookup.binding if prior_lookup.found else None
            if prior is None:
                if (
                    row.value["revision_number"] != 1
                    or row.value["supersedes_revision_id"] is not None
                ):
                    _fail("selector first campaign revision has invalid lineage")
            else:
                prior_ids = prior["member_ids"]
                member_ids = [item["episode_id"] for item in row.value["members"]]
                first_new = (
                    row.value["members"][len(prior_ids)]
                    if len(member_ids) > len(prior_ids)
                    else None
                )
                if (
                    row.value["revision_number"] != prior["revision_number"] + 1
                    or row.value["supersedes_revision_id"] != prior["revision_id"]
                    or len(member_ids) <= len(prior_ids)
                    or member_ids[: len(prior_ids)] != prior_ids
                    or first_new is None
                    or first_new["source_row"] <= prior["episode_records"]
                    or row.value["source_episode_prefix"]["records"]
                    <= prior["episode_records"]
                ):
                    _fail("selector campaign revision is not a strict prefix extension")
            history_entries.extend(
                (
                    (
                        _source_campaign_revision_key(revision_id),
                        {
                            "campaign_id": campaign_id,
                            "revision_id": revision_id,
                            "source_row": row.ordinal,
                        },
                    ),
                    (
                        _source_campaign_latest_key(
                            campaign_id, row.value["revision_number"]
                        ),
                        {
                            "campaign_id": campaign_id,
                            "revision_id": revision_id,
                            "revision_number": row.value["revision_number"],
                            "member_ids": [
                                item["episode_id"] for item in row.value["members"]
                            ],
                            "episode_records": row.value["source_episode_prefix"][
                                "records"
                            ],
                        },
                    ),
                )
            )
            local_revisions.add(revision_id)
            local_latest[campaign_id] = copy.deepcopy(history_entries[-1][1])
            candidate_id = _candidate_id(campaign_id)
            eligible = (
                row.value["evidence_phase"] == "prospective_after_rule_freeze"
                and _utc(row.value["formed_at"], label="campaign formed_at") >= effective
            )
            if eligible and campaign_id not in selected_campaign_ids:
                source_membership = _source_candidate_index_lookup(
                    root,
                    source_candidate_index,
                    campaign_id,
                    node_cache=source_index_cache,
                )
                membership = _candidate_index_lookup(
                    root,
                    _empty_candidate_index() if head is None else head["candidate_index"],
                    campaign_id,
                    node_cache=candidate_index_cache,
                )
                if not source_membership.found and not membership.found:
                    selected.append((row, candidate_id))
                    selected_campaign_ids.add(campaign_id)
        owner_ordinals = {
            ordinal
            for row, _candidate_id_value in selected
            for ordinal in (
                row.value["members"][-1]["source_row"],
                row.value["source_episode_prefix"]["records"],
            )
        }
        episode_by_ordinal, episode_end_bytes = _episode_rows_for_ordinals(
            root,
            episode_chunks,
            ordinals=owner_ordinals,
            source_commit=source.commit,
            source_observed_at=source.observed_at,
            source_checkpoint=source_checkpoint,
            chunk_cache=episode_chunk_cache,
        )
        selected_by_ordinal = {row.ordinal: candidate_id for row, candidate_id in selected}
        entries: list[dict[str, Any]] = []
        # Seed bytes are followed by a content-addressed run and Patricia
        # insertion nodes in the same recovery intent. Keep a conservative
        # quarter-intent budget for source rows so the authenticated index and
        # HEAD always fit without an unbounded retry/reparse.
        projection_budget = max(1, MAX_SOURCE_INTENT_BYTES // 4)
        projected_bytes = 0
        first_source_row = campaign_cursor + 1
        first_campaign_byte = campaign_cursor_bytes
        processed = 0
        for row in rows:
            seed: PlannedObject | None = None
            if row.ordinal in selected_by_ordinal:
                seed = _source_seed_from_row(
                    source=source,
                    row=row,
                    episode_by_ordinal=episode_by_ordinal,
                    episode_end_bytes=episode_end_bytes,
                    campaign_prefix=campaign_prefix,
                    episode_prefix=episode_prefix,
                    source_checkpoint=source_checkpoint,
                )
                if processed and projected_bytes + len(seed.body) > projection_budget:
                    break
            processed += 1
            campaign_cursor = row.ordinal
            campaign_cursor_bytes += len(row.raw) + 1
            if seed is not None:
                objects[seed.key] = seed
                projected_bytes += len(seed.body)
                entries.append(
                    {
                        "candidate_available_at": seed.value["candidate_available_at"],
                        "candidate_id": seed.value["candidate_id"],
                        "source_row": row.ordinal,
                        "seed": seed.pointer,
                    }
                )
        if rows and processed == 0:
            _fail("selector campaign row cannot fit its bounded audit transition")
        if processed:
            source_window = {
                "stage": "CAMPAIGNS",
                "window": _make_campaign_source_window(
                    source=source,
                    source_checkpoint=source_checkpoint,
                    campaign_prefix=campaign_prefix,
                    episode_prefix=episode_prefix,
                    rows=rows[:processed],
                    first_byte=first_campaign_byte,
                ),
            }
        committed_history_entries = history_entries[: processed * 2]
        if committed_history_entries:
            try:
                source_campaign_history_index, history_nodes = (
                    private_auth_dict.sharded_insert_many(
                        source_campaign_history_index,
                        committed_history_entries,
                        domain=SOURCE_CAMPAIGN_HISTORY_DOMAIN,
                        load_node=lambda pointer: _load_source_campaign_history_node(
                            root, pointer
                        ),
                        cache=history_index_cache,
                    )
                )
            except private_auth_dict.AuthDictError as exc:
                raise SparseSelectorError(str(exc)) from exc
            for node in history_nodes:
                item = PlannedObject(
                    key=f"{private_auth_dict.NAMESPACE}/{node['node_id']}.json",
                    value=node,
                )
                objects[item.key] = item
        if entries:
            run = _make_source_run(
                level=0,
                source=source,
                source_checkpoint=source_checkpoint,
                first_source_row=first_source_row,
                last_source_row=campaign_cursor,
                entries=entries,
            )
            objects[run.key] = run
            run_pointers.append(run.pointer)
            run_cursors.append(0)
            if len(run_pointers) > MAX_RUN_MANIFESTS:
                _fail("selector source requires too many bounded run manifests")
            source_index_entries = [
                (
                    _source_candidate_index_key(item.value["campaign_row"]["campaign_id"]),
                    {
                        "campaign_id": item.value["campaign_row"]["campaign_id"],
                        "candidate_id": item.value["candidate_id"],
                        "seed": item.pointer,
                    },
                )
                for item in objects.values()
                if item.value.get("schema") == "options.sparse_selector_source_seed/v1"
            ]
            try:
                source_candidate_index, source_index_nodes = (
                    private_auth_dict.sharded_insert_many(
                    source_candidate_index,
                    source_index_entries,
                    domain=SOURCE_CANDIDATE_INDEX_DOMAIN,
                    load_node=lambda pointer: _load_source_candidate_index_node(
                        root, pointer
                    ),
                    cache=source_index_cache,
                    )
                )
            except private_auth_dict.AuthDictError as exc:
                raise SparseSelectorError(str(exc)) from exc
            for node in source_index_nodes:
                item = PlannedObject(
                    key=f"{private_auth_dict.NAMESPACE}/{node['node_id']}.json",
                    value=node,
                )
                objects[item.key] = item
    else:
        _fail("selector source audit stage drifted")

    phase = "AUDITING"
    if (
        audit_stage == "CAMPAIGNS"
        and campaign_cursor == campaign_prefix["records"]
    ):
        if campaign_cursor_bytes != campaign_prefix["bytes"]:
            _fail("selector campaign source count/byte receipt drifted")
        _verify_completed_source_epoch(
            campaigns_raw,
            episodes_raw,
            campaign_prefix=campaign_prefix,
            episode_prefix=episode_prefix,
        )
        audit_stage = "COMPLETE"
        phase = "RUNS_READY"
    advanced = _aware_utc(clock(), label="selector source transition clock")
    if _utc(source.observed_at, label="source observation clock") > advanced:
        _fail("selector source transition predates source observation")
    if head is not None and _utc(head["advanced_at"], label="prior HEAD clock") > advanced:
        _fail("selector source transition clock moved backward")
    next_head = _base_source_head(
        head=head,
        advanced_at=utc_text(advanced),
        source=source,
        campaign_prefix=campaign_prefix,
        episode_prefix=episode_prefix,
        source_checkpoint=source_checkpoint,
        phase=phase,
        audit_stage=audit_stage,
        audit_cursor=campaign_cursor,
        campaign_cursor_bytes=campaign_cursor_bytes,
        episode_cursor_records=episode_cursor,
        episode_cursor_bytes=episode_cursor_bytes,
        episode_chunks=episode_chunks,
        episode_identity_index=episode_identity_index,
        episode_group_index=episode_group_index,
        episode_group_count=episode_group_count,
        run_manifests=run_pointers,
        run_cursors=run_cursors,
        source_candidate_index=source_candidate_index,
        source_campaign_history_index=source_campaign_history_index,
        ready_run=None,
        ready_count=0,
        ready_cursor=0,
    )
    return _source_transition_intent(
        head=head,
        next_head=next_head,
        objects=tuple(objects.values()),
        source_window=source_window,
    )


def _plan_source_merge_transition(
    *,
    root: Path,
    head: Mapping[str, Any],
    source: SourceSnapshot,
    clock: Callable[[], datetime],
) -> CyclePlan:
    if head["source_phase"] not in {"RUNS_READY", "MERGING"}:
        _fail("selector source merge phase drifted")
    if (
        source.commit != head["source_commit"]
        or source.observed_at != head["source_observed_at"]
        or source.campaigns_blob_oid not in (
            None,
            head["source_campaign_prefix"]["git_blob_oid"],
        )
        or source.episodes_blob_oid not in (
            None,
            head["source_episode_prefix"]["git_blob_oid"],
        )
        or source.checkpoint_blob_oid not in (
            None,
            head["source_checkpoint"]["git_blob_oid"],
        )
    ):
        _fail("selector source merge changed the pinned epoch")
    runs = [copy.deepcopy(item) for item in head["source_run_manifests"]]
    if len(runs) != len(head["source_run_cursors"]):
        _fail("selector source merge cursor cardinality drifted")
    ready_count = 0
    first_ready: Mapping[str, Any] | None = None
    for pointer, cursor in zip(runs, head["source_run_cursors"], strict=True):
        run = _load_source_run(root, pointer)
        if (
            run["source_commit"] != head["source_commit"]
            or run["source_checkpoint"] != head["source_checkpoint"]
            or cursor != 0
        ):
            _fail("selector source merge run crossed epochs or was pre-consumed")
        if run["entry_count"] and first_ready is None:
            first_ready = pointer
        ready_count += run["entry_count"]
    # Two authenticated barriers make crash recovery explicit.  Candidate
    # admission then performs a bounded k-way merge across these immutable
    # sorted runs, avoiding an oversized all-backlog projection object.
    phase = "MERGING" if head["source_phase"] == "RUNS_READY" else "READY"
    visible_count = ready_count if phase == "READY" else 0
    ready_run = first_ready if phase == "READY" else None
    advanced = _aware_utc(clock(), label="selector source merge clock")
    next_head = _base_source_head(
        head=head,
        advanced_at=utc_text(advanced),
        source=source,
        campaign_prefix=head["source_campaign_prefix"],
        episode_prefix=head["source_episode_prefix"],
        source_checkpoint=head["source_checkpoint"],
        phase=phase,
        audit_stage="COMPLETE",
        audit_cursor=head["source_campaign_cursor_records"],
        campaign_cursor_bytes=head["source_campaign_cursor_bytes"],
        episode_cursor_records=head["source_episode_cursor_records"],
        episode_cursor_bytes=head["source_episode_cursor_bytes"],
        episode_chunks=head["source_episode_chunks"],
        episode_identity_index=head["source_episode_identity_index"],
        episode_group_index=head["source_episode_group_index"],
        episode_group_count=head["source_episode_group_count"],
        run_manifests=runs,
        run_cursors=head["source_run_cursors"],
        source_candidate_index=head["source_candidate_index"],
        source_campaign_history_index=head["source_campaign_history_index"],
        ready_run=ready_run,
        ready_count=visible_count,
        ready_cursor=0,
    )
    return _source_transition_intent(
        head=head,
        next_head=next_head,
        objects=(),
        source_window={"stage": "NONE"},
    )


def _plan_cycle_once(
    *,
    root: Path,
    source: SourceSnapshot,
    evidence_inputs: EvidenceInputs,
    scheduled_at: str,
    clock: Callable[[], datetime],
    runtime_armed: bool,
    admission_cap: int,
    settlement_cache: dict[str, Any],
    evidence_snapshot: EvidenceSnapshot | None = None,
) -> CyclePlan:
    """Plan one exact transition without mutating the private store."""

    if SELECTOR_RUNTIME_ARMED is not True:
        raise SparseSelectorUnarmed(
            "sparse selector runtime is code-unarmed pending M1 deployment receipts"
        )

    private_root = validate_private_root(root, create=True)
    state = _authenticate_selector_state(private_root)
    head = None if state is None else state[0]
    if head is None or head["source_phase"] == "AUDITING":
        return _plan_source_audit_transition(
            root=private_root,
            head=head,
            source=source,
            clock=clock,
        )
    if head["source_phase"] in {"READY", "DRAINED"}:
        source_changed = False
        for body, claimed, receipt in (
            (source.campaigns_raw, source.campaigns_blob_oid, head["source_campaign_prefix"]),
            (source.episodes_raw, source.episodes_blob_oid, head["source_episode_prefix"]),
            (source.checkpoint_raw, source.checkpoint_blob_oid, head["source_checkpoint"]),
        ):
            source_changed = source_changed or (
                claimed is not None and claimed != receipt["git_blob_oid"]
            ) or (body is not None and _git_blob_oid(body) != receipt["git_blob_oid"])
        if source_changed:
            if head["source_phase"] == "DRAINED":
                return _plan_source_audit_transition(
                    root=private_root,
                    head=head,
                    source=source,
                    clock=clock,
                )
            source = SourceSnapshot(
                commit=head["source_commit"],
                campaigns_raw=None,
                episodes_raw=None,
                observed_at=head["source_observed_at"],
                campaigns_blob_oid=head["source_campaign_prefix"]["git_blob_oid"],
                episodes_blob_oid=head["source_episode_prefix"]["git_blob_oid"],
                checkpoint_raw=None,
                checkpoint_blob_oid=head["source_checkpoint"]["git_blob_oid"],
            )
    if head["source_phase"] in {"RUNS_READY", "MERGING"}:
        return _plan_source_merge_transition(
            root=private_root,
            head=head,
            source=source,
            clock=clock,
        )
    assert head is not None
    if head["source_phase"] not in {"READY", "DRAINED"}:
        _fail("selector source epoch is not ready for candidate admission")
    if _utc(source.observed_at, label="provided source observation") < _utc(
        head["source_observed_at"], label="pinned source observation"
    ):
        _fail("selector source observation clock moved backward")
    for body, claimed, receipt, label in (
        (source.campaigns_raw, source.campaigns_blob_oid, head["source_campaign_prefix"], "campaign"),
        (source.episodes_raw, source.episodes_blob_oid, head["source_episode_prefix"], "episode"),
        (source.checkpoint_raw, source.checkpoint_blob_oid, head["source_checkpoint"], "checkpoint"),
    ):
        if claimed is not None and claimed != receipt["git_blob_oid"]:
            _fail(f"selector {label} changed before source drain")
        if body is not None and _git_blob_oid(body) != receipt["git_blob_oid"]:
            _fail(f"selector {label} bytes changed before source drain")
    source = SourceSnapshot(
        commit=head["source_commit"],
        campaigns_raw=None,
        episodes_raw=None,
        observed_at=head["source_observed_at"],
        campaigns_blob_oid=head["source_campaign_prefix"]["git_blob_oid"],
        episodes_blob_oid=head["source_episode_prefix"]["git_blob_oid"],
        checkpoint_raw=None,
        checkpoint_blob_oid=head["source_checkpoint"]["git_blob_oid"],
    )
    campaign_prefix = copy.deepcopy(dict(head["source_campaign_prefix"]))
    episode_prefix = copy.deepcopy(dict(head["source_episode_prefix"]))
    source_checkpoint = copy.deepcopy(dict(head["source_checkpoint"]))
    previous_campaign_cursor_records = head["source_campaign_cursor_records"]
    ready_entries: list[Mapping[str, Any]] = []
    ready_runs: list[dict[str, Any]] = []
    run_cursors_after = list(head["source_run_cursors"])
    merge_heap: list[tuple[str, str, int]] = []
    total_ready = 0
    for index, (pointer, cursor) in enumerate(
        zip(head["source_run_manifests"], run_cursors_after, strict=True)
    ):
        run = _load_source_run(private_root, pointer)
        if (
            run["source_commit"] != head["source_commit"]
            or run["source_checkpoint"] != head["source_checkpoint"]
            or cursor > run["entry_count"]
        ):
            _fail("selector ready run escaped its epoch or cursor")
        ready_runs.append(run)
        total_ready += run["entry_count"]
        if cursor < run["entry_count"]:
            entry = run["entries"][cursor]
            heapq.heappush(
                merge_heap,
                (entry["candidate_available_at"], entry["candidate_id"], index),
            )
    if total_ready != head["source_ready_count"]:
        _fail("selector ready run total drifted")
    while merge_heap and len(ready_entries) < admission_cap:
        _available_at, _candidate_id_value, index = heapq.heappop(merge_heap)
        cursor = run_cursors_after[index]
        entry = ready_runs[index]["entries"][cursor]
        ready_entries.append(entry)
        cursor += 1
        run_cursors_after[index] = cursor
        if cursor < ready_runs[index]["entry_count"]:
            successor = ready_runs[index]["entries"][cursor]
            heapq.heappush(
                merge_heap,
                (
                    successor["candidate_available_at"],
                    successor["candidate_id"],
                    index,
                ),
            )
    started = _aware_utc(clock(), label="selector cycle start clock")
    scheduled = _utc(scheduled_at, label="selector scheduled clock")
    source_observed = _utc(source.observed_at, label="source observation clock")
    if started < scheduled:
        _fail("selector cycle began before its scheduled slot")
    if source_observed > started:
        _fail("selector source observation follows its cycle start")
    if (
        head is not None
        and _utc(head["advanced_at"], label="prior HEAD clock") > started
    ):
        _fail("selector cycle start precedes its prior HEAD")
    if head is not None and source_observed < _utc(
        head["source_observed_at"], label="prior source observation clock"
    ):
        _fail("selector source observation clock moved backward")
    if head["cycle_count"]:
        prior_cycle_value = _load_pointer(
            private_root, head["last_cycle"], label="prior scheduled selector cycle"
        )
        prior_scheduled = _utc(
            prior_cycle_value["scheduled_at"], label="prior selector scheduled clock"
        )
        if scheduled <= prior_scheduled:
            _fail("selector scheduled slot did not advance strictly")
    previous_head_id = head["head_id"]
    previous_cycle = copy.deepcopy(head["last_cycle"])
    ordinal = head["cycle_count"] + 1
    cycle_id = _cycle_id(
        ordinal=ordinal,
        scheduled_at=scheduled_at,
        started_at=utc_text(started),
        source_commit=source.commit,
        previous_head_id=previous_head_id,
    )

    objects: dict[str, PlannedObject] = {}
    decisions: list[dict[str, Any]] = []
    settled_manifest_pointer: dict[str, Any] | None = None
    previous_candidate = (
        copy.deepcopy(head["last_candidate"]) if head is not None else None
    )
    candidate_count_before = 0 if head is None else head["candidate_count"]
    candidate_index_before = (
        private_auth_dict.sharded_root_receipt(
            domain=CANDIDATE_INDEX_DOMAIN, root=None, entry_count=0
        )
        if head is None
        else private_auth_dict.validate_sharded_root(
            head["candidate_index"], domain=CANDIDATE_INDEX_DOMAIN
        )
    )
    previous_decision = (
        copy.deepcopy(head["last_decision"]) if head is not None else None
    )
    decision_count_before = 0 if head is None else head["decision_count"]
    last_decision = copy.deepcopy(previous_decision)
    decision_count_after = decision_count_before
    proposal_session_date = (
        None if head is None else head["proposal_session_date"]
    )
    proposal_session_count = 0 if head is None else head["proposal_session_count"]
    w1a_publication_high_water = copy.deepcopy(
        head["w1a_publication_high_water"]
    )
    if head["pending_manifest"] is not None:
        settled_manifest_pointer = copy.deepcopy(head["pending_manifest"])
        if settlement_cache:
            if settlement_cache.get("manifest") != settled_manifest_pointer:
                _fail("selector admission retry changed its settled manifest")
            for _unused in range(settlement_cache["clock_calls"]):
                clock()
            settlement = copy.deepcopy(settlement_cache["result"])
        else:
            settlement_clock_calls = 0

            def settlement_clock() -> datetime:
                nonlocal settlement_clock_calls
                settlement_clock_calls += 1
                return clock()

            settlement = _settle_manifest(
                root=private_root,
                manifest_pointer=head["pending_manifest"],
                campaign_prefix=campaign_prefix,
                episode_prefix=episode_prefix,
                source_checkpoint=source_checkpoint,
                evidence_inputs=evidence_inputs,
                previous_decision=previous_decision,
                decision_count=decision_count_before,
                proposal_session_date=proposal_session_date,
                proposal_session_count=proposal_session_count,
                clock=settlement_clock,
                evidence_snapshot=evidence_snapshot,
            )
            settlement_cache.update(
                {
                    "manifest": copy.deepcopy(settled_manifest_pointer),
                    "clock_calls": settlement_clock_calls,
                    "result": copy.deepcopy(settlement),
                }
            )
        (
            decisions,
            settled_objects,
            last_decision,
            decision_count_after,
            proposal_session_date,
            proposal_session_count,
        ) = settlement
        for item in settled_objects:
            objects[item.key] = item
        source_receipts = [
            item.value
            for item in settled_objects
            if item.value.get("schema")
            == "options.sparse_selector_w1a_source_receipt/v1"
        ]
        if len(source_receipts) > 1:
            _fail("selector settlement repeats its W1A source receipt")
        w1a_publication_high_water = _advance_w1a_high_water(
            w1a_publication_high_water,
            None if not source_receipts else source_receipts[0],
        )

    new_candidate_objects: list[PlannedObject] = []
    pending_candidate_objects: list[PlannedObject] = []
    last_candidate = copy.deepcopy(previous_candidate)
    candidate_count_after = candidate_count_before
    candidate_index_cache = private_auth_dict.ShardedLookupCache.empty(
        CANDIDATE_INDEX_DOMAIN
    )
    for entry in ready_entries:
        seed = _validate_source_seed(
            _load_pointer(private_root, entry["seed"], label="ready source seed")
        )
        if (
            seed["candidate_id"] != entry["candidate_id"]
            or seed["candidate_available_at"] != entry["candidate_available_at"]
            or seed["source_checkpoint"] != source_checkpoint
        ):
            _fail("selector ready source entry differs from its seed")
        membership = _candidate_index_lookup(
            private_root,
            candidate_index_before,
            seed["campaign_row"]["campaign_id"],
            node_cache=candidate_index_cache,
        )
        if membership.found:
            _fail("selector ready run attempted duplicate candidate admission")
        candidate_count_after += 1
        candidate = _candidate_from_seed(
            seed,
            ordinal=candidate_count_after,
            previous_candidate=last_candidate,
        )
        item = PlannedObject(
            key=f"candidates/{candidate['candidate_id']}.json", value=candidate
        )
        new_candidate_objects.append(item)
        pending_candidate_objects.append(item)
        last_candidate = item.pointer
    ready_cursor_after = sum(run_cursors_after)
    if ready_cursor_after != head["source_ready_cursor"] + len(ready_entries):
        _fail("selector ready merge cursor did not advance exactly")
    if ready_cursor_after > head["source_ready_count"]:
        _fail("selector ready source cursor exceeded its run")
    # Consuming the final source entry is not terminal while its manifest is
    # pending. The following settlement-only cycle clears that manifest and is
    # the sole READY -> DRAINED transition.
    source_phase_after = (
        "DRAINED"
        if ready_cursor_after == head["source_ready_count"]
        and not pending_candidate_objects
        else "READY"
    )
    ready_run_after = next(
        (
            pointer
            for pointer, run, cursor in zip(
                head["source_run_manifests"],
                ready_runs,
                run_cursors_after,
                strict=True,
            )
            if cursor < run["entry_count"]
        ),
        None,
    )
    campaign_cursor_after = campaign_prefix["records"]
    projection_after: Mapping[str, Any] | None = (
        None
        if source_phase_after == "DRAINED"
        else copy.deepcopy(ready_run_after)
    )
    for item in new_candidate_objects:
        objects[item.key] = item
    candidate_index_entries = [
        (
            _candidate_index_key(item.value["campaign_id"]),
            {
                "campaign_id": item.value["campaign_id"],
                "candidate_id": item.value["candidate_id"],
                "candidate": item.pointer,
            },
        )
        for item in new_candidate_objects
    ]
    try:
        candidate_index_after, candidate_index_nodes = (
            private_auth_dict.sharded_insert_many(
            candidate_index_before,
            candidate_index_entries,
            domain=CANDIDATE_INDEX_DOMAIN,
            load_node=lambda pointer: _load_candidate_index_node(
                private_root, pointer
            ),
            cache=candidate_index_cache,
            )
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc
    for node in candidate_index_nodes:
        item = PlannedObject(
            key=f"{private_auth_dict.NAMESPACE}/{node['node_id']}.json",
            value=node,
        )
        if item.pointer != private_auth_dict.pointer(node):
            _fail("selector candidate index node pointer drifted")
        objects[item.key] = item
    if candidate_index_after["entry_count"] != candidate_count_after:
        _fail("selector candidate index count drifted")

    manifest_object: PlannedObject | None = None
    if pending_candidate_objects:
        manifest_frozen_clock = _aware_utc(clock(), label="manifest freeze clock")
        if manifest_frozen_clock < started or any(
            _utc(row["decision_available_at"], label="decision availability")
            > manifest_frozen_clock
            for row in decisions
        ):
            _fail("selector manifest freeze clock is nonmonotonic")
        manifest_frozen_at = utc_text(manifest_frozen_clock)
        manifest = _make_manifest(
            cycle_id=cycle_id,
            frozen_at=manifest_frozen_at,
            source=source,
            campaign_prefix=campaign_prefix,
            episode_prefix=episode_prefix,
            source_checkpoint=source_checkpoint,
            candidates=pending_candidate_objects,
        )
        manifest_object = PlannedObject(
            key=f"manifests/{manifest['manifest_id']}.json", value=manifest
        )
        objects[manifest_object.key] = manifest_object
        completed = _aware_utc(clock(), label="selector cycle completion clock")
    else:
        # A manifest-free cycle has no separately published freeze event.  Use
        # its one authenticated completion sample for both internal fences so
        # recovery can replay the exact clock vector without inventing an
        # otherwise-unobservable timestamp.
        completed = _aware_utc(clock(), label="selector cycle completion clock")
        manifest_frozen_clock = completed
    if completed < manifest_frozen_clock:
        _fail("selector cycle completion precedes its start")
    if runtime_armed and completed >= scheduled + timedelta(seconds=300):
        _fail("selector cycle crossed its frozen five-minute slot")
    cycle: dict[str, Any] = {
        "schema": "options.sparse_selector_cycle_receipt/v1",
        "cycle_id": cycle_id,
        "ordinal": ordinal,
        "scheduled_at": scheduled_at,
        "started_at": utc_text(started),
        "completed_at": utc_text(completed),
        "source_observed_at": source.observed_at,
        "source_commit": source.commit,
        "source_campaign_prefix": dict(campaign_prefix),
        "source_episode_prefix": dict(episode_prefix),
        "source_checkpoint": dict(source_checkpoint),
        "source_campaign_cursor_before": previous_campaign_cursor_records,
        "source_campaign_cursor_after": campaign_cursor_after,
        "source_projection_after": copy.deepcopy(projection_after),
        "previous_head_id": previous_head_id,
        "previous_cycle": previous_cycle,
        "settled_manifest": settled_manifest_pointer,
        "next_manifest": (
            None if manifest_object is None else manifest_object.pointer
        ),
        "candidate_count_before": candidate_count_before,
        "candidate_count_after": candidate_count_after,
        "previous_candidate": previous_candidate,
        "candidate_pointers": [item.pointer for item in new_candidate_objects],
        "last_candidate": last_candidate,
        "decision_count_before": decision_count_before,
        "decision_count_after": decision_count_after,
        "previous_decision": previous_decision,
        "last_decision": last_decision,
        "decision_count": len(decisions),
        "abstain_count": sum(row["action"] == "abstain" for row in decisions),
        "propose_count": sum(row["action"] == "propose" for row in decisions),
        "decision_ids": [row["decision_id"] for row in decisions],
        "decision_pointers": [
            _pointer_for(f"decisions/{row['decision_id']}.json", row)
            for row in decisions
        ],
        "exactly_one_reconciled": True,
        "runtime_armed": runtime_armed,
        "digests": dict(DIGESTS),
        "authority": dict(FALSE_AUTHORITY),
    }
    cycle = validate_runtime_object(cycle, label="selector cycle receipt")
    cycle_object = PlannedObject(key=f"cycles/{cycle_id}.json", value=cycle)
    objects[cycle_object.key] = cycle_object

    previous_queue_value = None
    if head["cycle_count"]:
        previous_queue_value = _load_pointer(
            private_root,
            head["last_handoff_queue"],
            label="prior selector handoff queue item",
        )
    queue_item = _make_handoff_queue_item(
        root=private_root,
        ordinal=ordinal,
        previous_queue_item=head["last_handoff_queue"],
        previous_queue_value=previous_queue_value,
        previous_cycle=previous_cycle,
        cycle_object=cycle_object,
    )
    queue_object = PlannedObject(
        key=_handoff_queue_key(ordinal),
        value=queue_item,
    )
    objects[queue_object.key] = queue_object

    next_head: dict[str, Any] = {
        "schema": "options.sparse_selector_head/v1",
        "head_id": "",
        "generation": head["generation"] + 1,
        "previous_head_id": head["head_id"],
        "advanced_at": cycle["completed_at"],
        "source_observed_at": source.observed_at,
        "source_commit": source.commit,
        "source_campaign_prefix": dict(campaign_prefix),
        "source_episode_prefix": dict(episode_prefix),
        "source_checkpoint": dict(source_checkpoint),
        "source_phase": source_phase_after,
        "source_audit_stage": "COMPLETE",
        "source_campaign_cursor_records": campaign_cursor_after,
        "source_campaign_cursor_bytes": head["source_campaign_cursor_bytes"],
        "source_episode_cursor_records": head["source_episode_cursor_records"],
        "source_episode_cursor_bytes": head["source_episode_cursor_bytes"],
        "source_episode_chunks": copy.deepcopy(head["source_episode_chunks"]),
        "source_episode_identity_index": copy.deepcopy(
            head["source_episode_identity_index"]
        ),
        "source_episode_group_index": copy.deepcopy(
            head["source_episode_group_index"]
        ),
        "source_episode_group_count": head["source_episode_group_count"],
        "source_projection_next": copy.deepcopy(projection_after),
        "source_run_manifests": copy.deepcopy(head["source_run_manifests"]),
        "source_run_cursors": run_cursors_after,
        "source_candidate_index": copy.deepcopy(head["source_candidate_index"]),
        "source_campaign_history_index": copy.deepcopy(
            head["source_campaign_history_index"]
        ),
        "source_ready_run": copy.deepcopy(ready_run_after),
        "source_ready_count": head["source_ready_count"],
        "source_ready_cursor": ready_cursor_after,
        "pending_manifest": (
            None if manifest_object is None else manifest_object.pointer
        ),
        "last_cycle": cycle_object.pointer,
        "cycle_count": ordinal,
        "handoff_queue_count": ordinal,
        "last_handoff_queue": queue_object.pointer,
        "last_candidate": last_candidate,
        "candidate_count": candidate_count_after,
        "candidate_index": candidate_index_after,
        "last_decision": last_decision,
        "decision_count": decision_count_after,
        "proposal_session_date": proposal_session_date,
        "proposal_session_count": proposal_session_count,
        "w1a_publication_high_water": w1a_publication_high_water,
        "digests": dict(DIGESTS),
        "authority": dict(FALSE_AUTHORITY),
    }
    next_head["head_id"] = _content_id("ossh_", next_head, field="head_id")
    next_head = validate_runtime_object(next_head, label="selector HEAD")

    ordered_objects = tuple(objects[key] for key in sorted(objects))
    if len(ordered_objects) > MAX_SOURCE_OBJECTS_PER_CYCLE:
        raise _AdvanceBoundExceeded(
            "selector advance transition exceeds its object cap"
        )
    intent: dict[str, Any] = {
        "schema": "options.sparse_selector_advance_intent/v1",
        "intent_sha256": "",
        "expected_head_id": previous_head_id,
        "expected_last_handoff_queue": (
            copy.deepcopy(head["last_handoff_queue"])
        ),
        "expected_last_candidate": previous_candidate,
        "expected_candidate_count": candidate_count_before,
        "expected_candidate_index": candidate_index_before,
        "expected_last_decision": previous_decision,
        "expected_decision_count": decision_count_before,
        "objects": [
            {
                "key": item.key,
                "sha256": _sha256(item.body),
                "bytes": len(item.body),
                "value": item.value,
            }
            for item in ordered_objects
        ],
        "next_head": next_head,
    }
    intent["intent_sha256"] = _content_id("", intent, field="intent_sha256")
    if len(canonical_bytes(intent)) > MAX_INTENT_BYTES:
        raise _AdvanceBoundExceeded(
            "selector advance intent exceeds its recovery bound"
        )
    return CyclePlan(
        expected_head_id=previous_head_id,
        objects=ordered_objects,
        head=next_head,
        intent=intent,
        evidence_inputs=evidence_inputs,
    )


def _plan_cycle_internal(
    *,
    root: Path,
    source: SourceSnapshot,
    evidence_inputs: EvidenceInputs,
    scheduled_at: str,
    clock: Callable[[], datetime],
    runtime_armed: bool,
) -> CyclePlan:
    """Plan with deterministic complete-prefix backoff under exact bounds."""

    recorded_clocks: list[datetime] = []
    settlement_cache: dict[str, Any] = {}
    admission_cap = MAX_CANDIDATES_PER_MANIFEST
    while True:
        clock_index = 0

        def replay_clock() -> datetime:
            nonlocal clock_index
            if clock_index == len(recorded_clocks):
                recorded_clocks.append(clock())
            value = recorded_clocks[clock_index]
            clock_index += 1
            return value

        try:
            plan = _plan_cycle_once(
                root=root,
                source=source,
                evidence_inputs=evidence_inputs,
                scheduled_at=scheduled_at,
                clock=replay_clock,
                runtime_armed=runtime_armed,
                admission_cap=admission_cap,
                settlement_cache=settlement_cache,
            )
            if admission_cap != MAX_CANDIDATES_PER_MANIFEST:
                post_retry = _aware_utc(clock(), label="selector retry fence clock")
                if post_retry < _utc(
                    plan.head["advanced_at"], label="planned completion clock"
                ):
                    _fail("selector retry fence precedes its planned completion")
                if runtime_armed and post_retry >= _utc(
                    scheduled_at, label="selector scheduled clock"
                ) + timedelta(seconds=300):
                    _fail("selector admission retries crossed their frozen slot")
            return plan
        except _AdvanceBoundExceeded as exc:
            if admission_cap == 0:
                raise SparseSelectorError(
                    "selector cannot fit settlement under its recovery bounds"
                ) from exc
            if admission_cap == 1:
                if settlement_cache:
                    admission_cap = 0
                    continue
                raise SparseSelectorError(
                    "selector cannot fit one globally ordered admission under bounds"
                ) from exc
            admission_cap = max(1, admission_cap // 2)


def _source_epoch_tuple(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        value["source_commit"],
        value["source_observed_at"],
        value["source_checkpoint"],
        value["source_campaign_prefix"],
        value["source_episode_prefix"],
    )


def _source_epoch_object_matches(
    value: Mapping[str, Any], next_head: Mapping[str, Any]
) -> bool:
    return (
        value.get("source_commit") == next_head["source_commit"]
        and value.get("source_observed_at") == next_head["source_observed_at"]
        and value.get("source_checkpoint") == next_head["source_checkpoint"]
    )


def _replay_source_auth_batch(
    root: Path,
    *,
    domain: str,
    prior: Mapping[str, Any],
    expected_next: Mapping[str, Any],
    entries: Sequence[tuple[Any, Any]],
    planned_nodes: Sequence[PlannedObject],
    replace_keys: set[bytes] | None = None,
) -> None:
    """Replay one bounded semantic batch and require its exact emitted nodes."""

    if len(entries) > 256:
        _fail("selector source recovery auth batch exceeds 256 derived keys")
    planned_by_id = {item.value["node_id"]: item for item in planned_nodes}
    if len(planned_by_id) != len(planned_nodes):
        _fail("selector source recovery repeats an auth node identity")

    def load_old(pointer: Mapping[str, Any]) -> Mapping[str, Any]:
        value = _load_pointer(root, pointer, label="selector source prior auth node")
        try:
            return private_auth_dict.validate_node(value, domain=domain)
        except private_auth_dict.AuthDictError as exc:
            raise SparseSelectorError(str(exc)) from exc

    replace = replace_keys or set()
    try:
        recomputed, emitted = private_auth_dict.sharded_insert_many(
            prior,
            entries,
            domain=domain,
            load_node=load_old,
            replace_existing=lambda logical_key: (
                private_auth_dict.canonical_bytes(logical_key) in replace
            ),
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc
    emitted_by_id = {node["node_id"]: node for node in emitted}
    if (
        recomputed != expected_next
        or set(emitted_by_id) != set(planned_by_id)
        or any(
            planned_by_id[node_id].value != node
            or planned_by_id[node_id].pointer != private_auth_dict.pointer(node)
            for node_id, node in emitted_by_id.items()
        )
    ):
        _fail("selector source recovery auth transition is not exact")


def _source_expected_state(head: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_commit": head["source_commit"],
        "source_observed_at": head["source_observed_at"],
        "source_checkpoint": copy.deepcopy(head["source_checkpoint"]),
        "source_campaign_prefix": copy.deepcopy(head["source_campaign_prefix"]),
        "source_episode_prefix": copy.deepcopy(head["source_episode_prefix"]),
        "source_phase": head["source_phase"],
        "source_audit_stage": head["source_audit_stage"],
        "source_campaign_cursor_records": head["source_campaign_cursor_records"],
        "source_campaign_cursor_bytes": head["source_campaign_cursor_bytes"],
        "source_episode_cursor_records": head["source_episode_cursor_records"],
        "source_episode_cursor_bytes": head["source_episode_cursor_bytes"],
        "source_episode_chunks": copy.deepcopy(head["source_episode_chunks"]),
        "source_episode_group_count": head["source_episode_group_count"],
        "source_projection_next": copy.deepcopy(head["source_projection_next"]),
        "source_run_manifests": copy.deepcopy(head["source_run_manifests"]),
        "source_run_cursors": list(head["source_run_cursors"]),
        "source_ready_run": copy.deepcopy(head["source_ready_run"]),
        "source_ready_count": head["source_ready_count"],
        "source_ready_cursor": head["source_ready_cursor"],
        "source_candidate_index": copy.deepcopy(head["source_candidate_index"]),
        "source_campaign_history_index": copy.deepcopy(
            head["source_campaign_history_index"]
        ),
        "source_episode_identity_index": copy.deepcopy(
            head["source_episode_identity_index"]
        ),
        "source_episode_group_index": copy.deepcopy(
            head["source_episode_group_index"]
        ),
    }


def _runtime_expected_state(head: Mapping[str, Any] | None) -> dict[str, Any]:
    """Exact selector-owned state that a source-only transition must preserve."""

    if head is None:
        return {
            "pending_manifest": None,
            "last_cycle": None,
            "cycle_count": 0,
            "handoff_queue_count": 0,
            "last_handoff_queue": None,
            "last_candidate": None,
            "candidate_count": 0,
            "candidate_index": _empty_candidate_index(),
            "last_decision": None,
            "decision_count": 0,
            "proposal_session_date": None,
            "proposal_session_count": 0,
            "w1a_publication_high_water": None,
        }
    return {
        "pending_manifest": copy.deepcopy(head["pending_manifest"]),
        "last_cycle": copy.deepcopy(head["last_cycle"]),
        "cycle_count": head["cycle_count"],
        "handoff_queue_count": head["handoff_queue_count"],
        "last_handoff_queue": copy.deepcopy(head["last_handoff_queue"]),
        "last_candidate": copy.deepcopy(head["last_candidate"]),
        "candidate_count": head["candidate_count"],
        "candidate_index": copy.deepcopy(head["candidate_index"]),
        "last_decision": copy.deepcopy(head["last_decision"]),
        "decision_count": head["decision_count"],
        "proposal_session_date": head["proposal_session_date"],
        "proposal_session_count": head["proposal_session_count"],
        "w1a_publication_high_water": copy.deepcopy(
            head["w1a_publication_high_water"]
        ),
    }


def _advance_replay_clock_values(
    *,
    cycle: Mapping[str, Any],
    manifest: Mapping[str, Any] | None,
    decisions: Sequence[PlannedObject],
    planned_by_key: Mapping[str, PlannedObject],
) -> tuple[datetime, ...]:
    """Recover the exact planner clock vector carried by an advance intent."""

    values = [_utc(cycle["started_at"], label="intent replay cycle start")]
    if cycle["settled_manifest"] is not None:
        if not decisions:
            _fail("selector intent settled a manifest without decisions")
        generations = {
            canonical_bytes(item.value["evidence"]["generation"])
            for item in decisions
        }
        if len(generations) != 1:
            _fail("selector intent decisions do not share one evidence generation")
        generation_pointer = decisions[0].value["evidence"]["generation"]
        generation_item = planned_by_key.get(generation_pointer["key"])
        if generation_item is None or generation_item.pointer != generation_pointer:
            _fail("selector intent omits its shared evidence generation")
        generation = validate_runtime_object(
            generation_item.value, label="intent replay evidence generation"
        )
        if generation["settled_manifest"] != cycle["settled_manifest"]:
            _fail("selector intent evidence generation escaped its settled manifest")
        values.append(
            _utc(generation["fenced_at"], label="intent replay evidence fence")
        )
        for item in decisions:
            values.extend(
                (
                    _utc(
                        item.value["decision_event_at"],
                        label="intent replay decision event",
                    ),
                    _utc(
                        item.value["evidence_verified_at"],
                        label="intent replay evidence verified",
                    ),
                    _utc(
                        item.value["decision_available_at"],
                        label="intent replay decision available",
                    ),
                )
            )
    elif decisions:
        _fail("selector intent carries decisions without a settled manifest")
    if manifest is not None:
        values.append(_utc(manifest["frozen_at"], label="intent replay manifest freeze"))
    values.append(_utc(cycle["completed_at"], label="intent replay cycle completion"))
    return tuple(values)


def _plan_from_intent(
    root: Path,
    intent: Mapping[str, Any],
    *,
    evidence_inputs: EvidenceInputs | None = None,
) -> CyclePlan:
    if isinstance(intent, Mapping) and intent.get("schema") == "options.sparse_selector_source_intent/v1":
        expected_fields = {
            "schema",
            "intent_sha256",
            "expected_head_id",
            "expected_last_handoff_queue",
            "expected_last_candidate",
            "expected_candidate_count",
            "expected_candidate_index",
            "expected_last_decision",
            "expected_decision_count",
            "expected_source_state",
            "expected_runtime_state",
            "source_window",
            "objects",
            "next_head",
        }
        if set(intent) != expected_fields:
            _fail("selector source intent fields are malformed")
        clean = copy.deepcopy(dict(intent))
        if clean["intent_sha256"] != _content_id("", clean, field="intent_sha256"):
            _fail("selector source intent identity drifted")
        if (
            not isinstance(clean["objects"], list)
            or len(clean["objects"]) > MAX_SOURCE_OBJECTS_PER_CYCLE
            or len(canonical_bytes(clean)) > MAX_SOURCE_INTENT_BYTES
        ):
            _fail("selector source recovery intent exceeds its bounds")
        objects: list[PlannedObject] = []
        by_pointer_id: dict[str, PlannedObject] = {}
        object_keys: set[str] = set()
        for receipt in clean["objects"]:
            if not isinstance(receipt, Mapping) or set(receipt) != {
                "key",
                "sha256",
                "bytes",
                "value",
            }:
                _fail("selector source intent object receipt is malformed")
            item = PlannedObject(key=receipt["key"], value=receipt["value"])
            if len(item.body) != receipt["bytes"] or _sha256(item.body) != receipt["sha256"]:
                _fail("selector source intent object receipt drifted")
            if item.value.get("schema") == "options.sparse_selector_source_seed/v1":
                _validate_source_seed(item.value)
                expected_key = f"{SOURCE_PROJECTION_NAMESPACE}/{item.value['seed_id']}.json"
            elif item.value.get("schema") == "options.sparse_selector_source_run/v1":
                _validate_source_run(item.value)
                expected_key = f"{SOURCE_PROJECTION_NAMESPACE}/{item.value['run_id']}.json"
            elif item.value.get("schema") == "options.sparse_selector_episode_chunk/v1":
                _validate_episode_chunk(item.value)
                expected_key = f"{SOURCE_PROJECTION_NAMESPACE}/{item.value['chunk_id']}.json"
            elif item.value.get("schema") == private_auth_dict.SCHEMA:
                try:
                    if item.value.get("domain") not in {
                        SOURCE_CANDIDATE_INDEX_DOMAIN,
                        SOURCE_CAMPAIGN_HISTORY_DOMAIN,
                        SOURCE_EPISODE_IDENTITY_DOMAIN,
                        SOURCE_EPISODE_GROUP_DOMAIN,
                    }:
                        _fail("selector source intent contains a foreign auth node")
                    private_auth_dict.validate_node(
                        item.value, domain=item.value["domain"]
                    )
                    expected_key = (
                        f"{private_auth_dict.NAMESPACE}/{item.value['node_id']}.json"
                    )
                except private_auth_dict.AuthDictError as exc:
                    raise SparseSelectorError(str(exc)) from exc
            else:
                _fail("selector source intent contains a foreign object")
            if item.key != expected_key:
                _fail("selector source intent object namespace drifted")
            if item.pointer["id"] in by_pointer_id or item.key in object_keys:
                _fail("selector source intent repeats an object identity")
            by_pointer_id[item.pointer["id"]] = item
            object_keys.add(item.key)
            objects.append(item)
        next_head = validate_runtime_object(clean["next_head"], label="source intent next HEAD")
        prior = _load_head(root)
        prior_id = None if prior is None else prior["head_id"]
        if clean["expected_head_id"] != prior_id and prior_id != next_head["head_id"]:
            _fail("selector source intent parent drifted")
        expected_source_state = clean["expected_source_state"]
        expected_runtime_state = clean["expected_runtime_state"]
        expected_state_fields = {
            "source_commit",
            "source_observed_at",
            "source_checkpoint",
            "source_campaign_prefix",
            "source_episode_prefix",
            "source_phase",
            "source_audit_stage",
            "source_campaign_cursor_records",
            "source_campaign_cursor_bytes",
            "source_episode_cursor_records",
            "source_episode_cursor_bytes",
            "source_episode_chunks",
            "source_episode_group_count",
            "source_projection_next",
            "source_run_manifests",
            "source_run_cursors",
            "source_ready_run",
            "source_ready_count",
            "source_ready_cursor",
            "source_candidate_index",
            "source_campaign_history_index",
            "source_episode_identity_index",
            "source_episode_group_index",
        }
        if clean["expected_head_id"] is None:
            if expected_source_state is not None:
                _fail("selector initial source intent carries parent source state")
        elif (
            not isinstance(expected_source_state, Mapping)
            or set(expected_source_state) != expected_state_fields
        ):
            _fail("selector source intent parent source state is malformed")
        if (
            prior_id == clean["expected_head_id"]
            and prior is not None
            and expected_source_state != _source_expected_state(prior)
        ):
            _fail("selector source intent parent source state drifted")
        expected_runtime_fields = set(_runtime_expected_state(None))
        if (
            not isinstance(expected_runtime_state, Mapping)
            or set(expected_runtime_state) != expected_runtime_fields
        ):
            _fail("selector source intent parent runtime state is malformed")
        if (
            prior_id == clean["expected_head_id"]
            and expected_runtime_state != _runtime_expected_state(prior)
        ):
            _fail("selector source intent parent runtime state drifted")
        if any(
            next_head[field] != expected_runtime_state[field]
            for field in expected_runtime_fields
        ):
            _fail("selector source transition changed runtime state")
        if prior_id == next_head["head_id"]:
            expected_generation = next_head["generation"]
        elif prior is None:
            expected_generation = 1
        else:
            expected_generation = prior["generation"] + 1
            if (
                clean["expected_last_handoff_queue"] != prior["last_handoff_queue"]
                or clean["expected_last_candidate"] != prior["last_candidate"]
                or clean["expected_candidate_count"] != prior["candidate_count"]
                or clean["expected_candidate_index"] != prior["candidate_index"]
                or clean["expected_last_decision"] != prior["last_decision"]
                or clean["expected_decision_count"] != prior["decision_count"]
            ):
                _fail("selector source intent changed runtime tails")
        if next_head["generation"] != expected_generation:
            _fail("selector source intent generation is not monotone")
        reset_epoch = expected_source_state is None or (
            expected_source_state["source_phase"] == "DRAINED"
            and _source_epoch_tuple(expected_source_state)
            != _source_epoch_tuple(next_head)
        )
        prior_roots = {
            SOURCE_CANDIDATE_INDEX_DOMAIN: (
                _empty_source_candidate_index()
                if reset_epoch
                else expected_source_state["source_candidate_index"]
            ),
            SOURCE_CAMPAIGN_HISTORY_DOMAIN: (
                _empty_source_campaign_history_index()
                if reset_epoch
                else expected_source_state["source_campaign_history_index"]
            ),
            SOURCE_EPISODE_IDENTITY_DOMAIN: (
                _empty_source_episode_identity_index()
                if reset_epoch
                else expected_source_state["source_episode_identity_index"]
            ),
            SOURCE_EPISODE_GROUP_DOMAIN: (
                _empty_source_episode_group_index()
                if reset_epoch
                else expected_source_state["source_episode_group_index"]
            ),
        }
        next_roots = {
            SOURCE_CANDIDATE_INDEX_DOMAIN: next_head["source_candidate_index"],
            SOURCE_CAMPAIGN_HISTORY_DOMAIN: next_head[
                "source_campaign_history_index"
            ],
            SOURCE_EPISODE_IDENTITY_DOMAIN: next_head[
                "source_episode_identity_index"
            ],
            SOURCE_EPISODE_GROUP_DOMAIN: next_head["source_episode_group_index"],
        }
        planned_nodes_by_domain: dict[str, list[PlannedObject]] = {
            domain: [] for domain in prior_roots
        }
        for item in objects:
            if item.value.get("schema") == private_auth_dict.SCHEMA:
                planned_nodes_by_domain[item.value["domain"]].append(item)

        window = clean["source_window"]
        if not isinstance(window, Mapping) or window.get("stage") not in {
            "NONE",
            "EPISODES",
            "CAMPAIGNS",
        }:
            _fail("selector source recovery window is malformed")
        derived: dict[str, list[tuple[Any, Any]]] = {
            domain: [] for domain in prior_roots
        }
        expected_projection_keys: set[str] = set()
        expected_next_source_state: dict[str, Any] | None = None
        replace_group_keys: set[bytes] = set()
        expected_group_delta = 0
        if window["stage"] == "EPISODES":
            if set(window) != {"stage", "chunk"}:
                _fail("selector episode recovery window fields are malformed")
            chunk_item = by_pointer_id.get(str(window["chunk"].get("id")))
            if (
                chunk_item is None
                or chunk_item.pointer != window["chunk"]
                or chunk_item.value.get("schema")
                != "options.sparse_selector_episode_chunk/v1"
            ):
                _fail("selector episode recovery window lacks its exact chunk")
            chunk = _validate_episode_chunk(chunk_item.value)
            expected_projection_keys.add(chunk_item.key)
            if not _source_epoch_object_matches(chunk, next_head):
                _fail("selector episode recovery window crossed epochs")
            if len(chunk["rows"]) > 128:
                _fail("selector episode recovery window exceeds 128 rows")
            group_cache = private_auth_dict.ShardedLookupCache.empty(
                SOURCE_EPISODE_GROUP_DOMAIN
            )
            local_latest: dict[tuple[str, ...], dict[str, Any]] = {}
            for item in chunk["rows"]:
                row = item["row"]
                source_row = item["ordinal"]
                derived[SOURCE_EPISODE_IDENTITY_DOMAIN].extend(
                    [
                        (
                            _source_episode_id_key(row["episode_id"]),
                            {"episode_id": row["episode_id"], "source_row": source_row},
                        ),
                        (
                            _source_episode_event_key(
                                row["source"], row["source_event_id"]
                            ),
                            {
                                "source": row["source"],
                                "source_event_id": row["source_event_id"],
                                "episode_id": row["episode_id"],
                                "source_row": source_row,
                            },
                        ),
                    ]
                )
                group = tuple(_source_episode_group_parts(row))
                latest = local_latest.get(group)
                latest_key = _source_episode_group_latest_key(group)
                if latest is None:
                    try:
                        lookup = private_auth_dict.sharded_lookup(
                            prior_roots[SOURCE_EPISODE_GROUP_DOMAIN],
                            latest_key,
                            domain=SOURCE_EPISODE_GROUP_DOMAIN,
                            load_node=lambda pointer: _load_source_episode_group_node(
                                root, pointer
                            ),
                            cache=group_cache,
                        )
                    except private_auth_dict.AuthDictError as exc:
                        raise SparseSelectorError(str(exc)) from exc
                    latest = (
                        {"member_count": 0, "last_source_row": 0}
                        if not lookup.found
                        else copy.deepcopy(dict(lookup.binding))
                    )
                    if lookup.found:
                        replace_group_keys.add(
                            private_auth_dict.canonical_bytes(latest_key)
                        )
                    else:
                        expected_group_delta += 1
                member_ordinal = latest["member_count"] + 1
                derived[SOURCE_EPISODE_GROUP_DOMAIN].append(
                    (
                        _source_episode_group_member_key(group, member_ordinal),
                        {
                            "episode_id": row["episode_id"],
                            "source_row": source_row,
                            "source_row_sha256": item["row_sha256"],
                        },
                    )
                )
                local_latest[group] = {
                    "member_count": member_ordinal,
                    "last_source_row": source_row,
                }
            derived[SOURCE_EPISODE_GROUP_DOMAIN].extend(
                (
                    _source_episode_group_latest_key(group),
                    binding,
                )
                for group, binding in sorted(local_latest.items())
            )
            old_episode_cursor = (
                0
                if reset_epoch
                else expected_source_state["source_episode_cursor_records"]
            )
            if (
                chunk["first_row"] != old_episode_cursor + 1
                or chunk["last_row"]
                != next_head["source_episode_cursor_records"]
                or next_head["source_episode_group_count"]
                != (0 if reset_epoch else expected_source_state["source_episode_group_count"])
                + expected_group_delta
            ):
                _fail("selector episode recovery cursor/group delta drifted")
            prior_campaign_cursor = (
                0
                if reset_epoch
                else expected_source_state["source_campaign_cursor_records"]
            )
            prior_campaign_bytes = (
                0
                if reset_epoch
                else expected_source_state["source_campaign_cursor_bytes"]
            )
            prior_chunks = (
                []
                if reset_epoch
                else copy.deepcopy(expected_source_state["source_episode_chunks"])
            )
            prior_runs = (
                []
                if reset_epoch
                else copy.deepcopy(expected_source_state["source_run_manifests"])
            )
            prior_run_cursors = (
                [] if reset_epoch else list(expected_source_state["source_run_cursors"])
            )
            expected_audit_stage = (
                "CAMPAIGNS"
                if chunk["last_row"] == next_head["source_episode_prefix"]["records"]
                else "EPISODES"
            )
            episode_window_completes_epoch = (
                expected_audit_stage == "CAMPAIGNS"
                and prior_campaign_cursor
                == next_head["source_campaign_prefix"]["records"]
            )
            expected_next_source_state = {
                "source_commit": next_head["source_commit"],
                "source_observed_at": next_head["source_observed_at"],
                "source_checkpoint": copy.deepcopy(next_head["source_checkpoint"]),
                "source_campaign_prefix": copy.deepcopy(
                    next_head["source_campaign_prefix"]
                ),
                "source_episode_prefix": copy.deepcopy(
                    next_head["source_episode_prefix"]
                ),
                "source_phase": (
                    "RUNS_READY" if episode_window_completes_epoch else "AUDITING"
                ),
                "source_audit_stage": (
                    "COMPLETE"
                    if episode_window_completes_epoch
                    else expected_audit_stage
                ),
                "source_campaign_cursor_records": prior_campaign_cursor,
                "source_campaign_cursor_bytes": prior_campaign_bytes,
                "source_episode_cursor_records": chunk["last_row"],
                "source_episode_cursor_bytes": chunk["last_byte"],
                "source_episode_chunks": [
                    *prior_chunks,
                    {
                        "pointer": chunk_item.pointer,
                        "first_row": chunk["first_row"],
                        "last_row": chunk["last_row"],
                        "first_byte": chunk["first_byte"],
                        "last_byte": chunk["last_byte"],
                    },
                ],
                "source_episode_group_count": next_head[
                    "source_episode_group_count"
                ],
                "source_projection_next": None,
                "source_run_manifests": prior_runs,
                "source_run_cursors": prior_run_cursors,
                "source_ready_run": None,
                "source_ready_count": 0,
                "source_ready_cursor": 0,
                "source_candidate_index": copy.deepcopy(
                    next_roots[SOURCE_CANDIDATE_INDEX_DOMAIN]
                ),
                "source_campaign_history_index": copy.deepcopy(
                    next_roots[SOURCE_CAMPAIGN_HISTORY_DOMAIN]
                ),
                "source_episode_identity_index": copy.deepcopy(
                    next_roots[SOURCE_EPISODE_IDENTITY_DOMAIN]
                ),
                "source_episode_group_index": copy.deepcopy(
                    next_roots[SOURCE_EPISODE_GROUP_DOMAIN]
                ),
            }
        elif window["stage"] == "CAMPAIGNS":
            if set(window) != {"stage", "window"}:
                _fail("selector campaign recovery window fields are malformed")
            campaign_window = _validate_campaign_source_window(window["window"])
            prior_campaign_cursor = (
                0
                if reset_epoch
                else expected_source_state["source_campaign_cursor_records"]
            )
            prior_campaign_bytes = (
                0
                if reset_epoch
                else expected_source_state["source_campaign_cursor_bytes"]
            )
            if (
                _source_epoch_tuple(campaign_window)
                != _source_epoch_tuple(next_head)
                or campaign_window["first_row"] != prior_campaign_cursor + 1
                or campaign_window["first_byte"] != prior_campaign_bytes
                or campaign_window["last_row"]
                != next_head["source_campaign_cursor_records"]
                or campaign_window["last_byte"]
                != next_head["source_campaign_cursor_bytes"]
            ):
                _fail("selector campaign recovery window crossed epochs or cursor")

            actual_seeds = [
                item
                for item in objects
                if item.value.get("schema")
                == "options.sparse_selector_source_seed/v1"
            ]
            seeds_by_row = {
                item.value["campaign_row_number"]: item
                for item in actual_seeds
            }
            if len(seeds_by_row) != len(actual_seeds):
                _fail("selector campaign recovery repeats a source row seed")

            episodes_raw = _episode_source_from_chunks(
                root,
                next_head["source_episode_chunks"],
                source_commit=next_head["source_commit"],
                source_observed_at=next_head["source_observed_at"],
                source_checkpoint=next_head["source_checkpoint"],
                source_prefix=next_head["source_episode_prefix"],
            )
            source = SourceSnapshot(
                commit=next_head["source_commit"],
                campaigns_raw=None,
                episodes_raw=episodes_raw,
                observed_at=next_head["source_observed_at"],
                campaigns_blob_oid=next_head["source_campaign_prefix"]["git_blob_oid"],
                episodes_blob_oid=next_head["source_episode_prefix"]["git_blob_oid"],
                checkpoint_raw=None,
                checkpoint_blob_oid=next_head["source_checkpoint"]["git_blob_oid"],
            )
            source_index_cache = private_auth_dict.ShardedLookupCache.empty(
                SOURCE_CANDIDATE_INDEX_DOMAIN
            )
            history_index_cache = private_auth_dict.ShardedLookupCache.empty(
                SOURCE_CAMPAIGN_HISTORY_DOMAIN
            )
            candidate_index_cache = private_auth_dict.ShardedLookupCache.empty(
                CANDIDATE_INDEX_DOMAIN
            )
            group_node_cache = private_auth_dict.ShardedLookupCache.empty(
                SOURCE_EPISODE_GROUP_DOMAIN
            )
            prefix_digest_cache = _episode_prefix_digests(
                episodes_raw,
                {
                    item["row"]["source_episode_prefix"]["records"]
                    for item in campaign_window["rows"]
                },
                source_checkpoint=next_head["source_checkpoint"],
            )
            episode_chunk_cache: dict[str, dict[str, Any]] = {}
            local_latest: dict[str, dict[str, Any]] = {}
            local_revisions: set[str] = set()
            selected_campaign_ids: set[str] = set()
            selected: list[tuple[JsonlRow, str]] = []
            campaign_rows: list[JsonlRow] = []
            effective = max(
                _utc(BENCHMARK_EFFECTIVE_FREEZE_AT, label="benchmark freeze"),
                _utc(SELECTOR_EFFECTIVE_FREEZE_AT, label="selector freeze"),
            )
            for item in campaign_window["rows"]:
                row = item["row"]
                raw = canonical_bytes(row)
                if item["row_sha256"] != _sha256(raw):
                    _fail("selector campaign recovery row digest drifted")
                decoded = JsonlRow(ordinal=item["ordinal"], value=row, raw=raw)
                campaign_rows.append(decoded)
                try:
                    campaign_contract.validate_campaign(row)
                except campaign_contract.CampaignContractError as exc:
                    raise SparseSelectorError(
                        "selector campaign recovery row is invalid"
                    ) from exc
                _validate_campaign_against_episode_index(
                    root,
                    row,
                    next_head["source_episode_chunks"],
                    source_commit=next_head["source_commit"],
                    source_observed_at=next_head["source_observed_at"],
                    source_checkpoint=next_head["source_checkpoint"],
                    episodes_raw=episodes_raw,
                    prefix_digest_cache=prefix_digest_cache,
                    episode_group_index=prior_roots[
                        SOURCE_EPISODE_GROUP_DOMAIN
                    ],
                    episode_chunk_cache=episode_chunk_cache,
                    group_node_cache=group_node_cache,
                )
                campaign_id = row["campaign_id"]
                revision_id = row["campaign_revision_id"]
                if revision_id in local_revisions or _source_campaign_history_lookup(
                    root,
                    prior_roots[SOURCE_CAMPAIGN_HISTORY_DOMAIN],
                    _source_campaign_revision_key(revision_id),
                    node_cache=history_index_cache,
                ).found:
                    _fail("selector campaign recovery repeats a revision")
                prior_history = local_latest.get(campaign_id)
                if prior_history is None:
                    prior_lookup = _source_campaign_history_lookup(
                        root,
                        prior_roots[SOURCE_CAMPAIGN_HISTORY_DOMAIN],
                        _source_campaign_latest_key(
                            campaign_id, row["revision_number"] - 1
                        ),
                        node_cache=history_index_cache,
                    )
                    prior_history = (
                        copy.deepcopy(dict(prior_lookup.binding))
                        if prior_lookup.found
                        else None
                    )
                if prior_history is None:
                    if (
                        row["revision_number"] != 1
                        or row["supersedes_revision_id"] is not None
                    ):
                        _fail("selector campaign recovery first revision drifted")
                else:
                    prior_ids = prior_history["member_ids"]
                    member_ids = [member["episode_id"] for member in row["members"]]
                    first_new = (
                        row["members"][len(prior_ids)]
                        if len(member_ids) > len(prior_ids)
                        else None
                    )
                    if (
                        row["revision_number"]
                        != prior_history["revision_number"] + 1
                        or row["supersedes_revision_id"]
                        != prior_history["revision_id"]
                        or len(member_ids) <= len(prior_ids)
                        or member_ids[: len(prior_ids)] != prior_ids
                        or first_new is None
                        or first_new["source_row"]
                        <= prior_history["episode_records"]
                        or row["source_episode_prefix"]["records"]
                        <= prior_history["episode_records"]
                    ):
                        _fail("selector campaign recovery lineage drifted")
                derived[SOURCE_CAMPAIGN_HISTORY_DOMAIN].extend(
                    [
                        (
                            _source_campaign_revision_key(
                                row["campaign_revision_id"]
                            ),
                            {
                                "campaign_id": row["campaign_id"],
                                "revision_id": row["campaign_revision_id"],
                                "source_row": item["ordinal"],
                            },
                        ),
                        (
                            _source_campaign_latest_key(
                                row["campaign_id"], row["revision_number"]
                            ),
                            {
                                "campaign_id": row["campaign_id"],
                                "revision_id": row["campaign_revision_id"],
                                "revision_number": row["revision_number"],
                                "member_ids": [
                                    member["episode_id"] for member in row["members"]
                                ],
                                "episode_records": row["source_episode_prefix"][
                                    "records"
                                ],
                            },
                        ),
                    ]
                )
                local_revisions.add(revision_id)
                local_latest[campaign_id] = copy.deepcopy(
                    derived[SOURCE_CAMPAIGN_HISTORY_DOMAIN][-1][1]
                )
                eligible = (
                    row["evidence_phase"] == "prospective_after_rule_freeze"
                    and _utc(row["formed_at"], label="campaign formed_at")
                    >= effective
                )
                if eligible and campaign_id not in selected_campaign_ids:
                    source_membership = _source_candidate_index_lookup(
                        root,
                        prior_roots[SOURCE_CANDIDATE_INDEX_DOMAIN],
                        campaign_id,
                        node_cache=source_index_cache,
                    )
                    runtime_membership = _candidate_index_lookup(
                        root,
                        expected_runtime_state["candidate_index"],
                        campaign_id,
                        node_cache=candidate_index_cache,
                    )
                    if not source_membership.found and not runtime_membership.found:
                        selected.append((decoded, _candidate_id(campaign_id)))
                        selected_campaign_ids.add(campaign_id)

            owner_ordinals = {
                ordinal
                for row, _candidate_id_value in selected
                for ordinal in (
                    row.value["members"][-1]["source_row"],
                    row.value["source_episode_prefix"]["records"],
                )
            }
            episode_by_ordinal, episode_end_bytes = _episode_rows_for_ordinals(
                root,
                next_head["source_episode_chunks"],
                ordinals=owner_ordinals,
                source_commit=next_head["source_commit"],
                source_observed_at=next_head["source_observed_at"],
                source_checkpoint=next_head["source_checkpoint"],
                chunk_cache=episode_chunk_cache,
            )
            expected_seeds: dict[int, PlannedObject] = {}
            projected_bytes = 0
            selected_by_ordinal = {
                row.ordinal: candidate_id for row, candidate_id in selected
            }
            for processed, row in enumerate(campaign_rows):
                if row.ordinal not in selected_by_ordinal:
                    continue
                seed = _source_seed_from_row(
                    source=source,
                    row=row,
                    episode_by_ordinal=episode_by_ordinal,
                    episode_end_bytes=episode_end_bytes,
                    campaign_prefix=next_head["source_campaign_prefix"],
                    episode_prefix=next_head["source_episode_prefix"],
                    source_checkpoint=next_head["source_checkpoint"],
                )
                if (
                    processed > 0
                    and projected_bytes + len(seed.body)
                    > max(1, MAX_SOURCE_INTENT_BYTES // 4)
                ):
                    _fail("selector campaign recovery exceeded its planned prefix")
                projected_bytes += len(seed.body)
                expected_seeds[row.ordinal] = seed
            if set(seeds_by_row) != set(expected_seeds) or any(
                seeds_by_row[ordinal].value != seed.value
                or seeds_by_row[ordinal].pointer != seed.pointer
                for ordinal, seed in expected_seeds.items()
            ):
                _fail("selector campaign recovery omitted or changed an eligible seed")
            for row, _candidate_id_value in selected:
                seed = expected_seeds[row.ordinal]
                expected_projection_keys.add(seed.key)
                derived[SOURCE_CANDIDATE_INDEX_DOMAIN].append(
                    (
                        _source_candidate_index_key(row.value["campaign_id"]),
                        {
                            "campaign_id": row.value["campaign_id"],
                            "candidate_id": seed.value["candidate_id"],
                            "seed": seed.pointer,
                        },
                    )
                )
            expected_entries = [
                {
                    "candidate_available_at": expected_seeds[row.ordinal].value[
                        "candidate_available_at"
                    ],
                    "candidate_id": expected_seeds[row.ordinal].value["candidate_id"],
                    "source_row": row.ordinal,
                    "seed": expected_seeds[row.ordinal].pointer,
                }
                for row, _candidate_id_value in selected
            ]
            actual_runs = [
                item
                for item in objects
                if item.value.get("schema") == "options.sparse_selector_source_run/v1"
            ]
            prior_run_manifests = (
                []
                if reset_epoch
                else expected_source_state["source_run_manifests"]
            )
            prior_run_cursors = (
                [] if reset_epoch else expected_source_state["source_run_cursors"]
            )
            if expected_entries:
                expected_run = _make_source_run(
                    level=0,
                    source=source,
                    source_checkpoint=next_head["source_checkpoint"],
                    first_source_row=campaign_window["first_row"],
                    last_source_row=campaign_window["last_row"],
                    entries=expected_entries,
                )
                if (
                    len(actual_runs) != 1
                    or actual_runs[0].value != expected_run.value
                    or actual_runs[0].pointer != expected_run.pointer
                ):
                    _fail("selector campaign recovery run differs from its seeds")
                expected_projection_keys.add(expected_run.key)
                expected_run_manifests = [
                    *copy.deepcopy(prior_run_manifests),
                    expected_run.pointer,
                ]
                expected_run_cursors = [*prior_run_cursors, 0]
            else:
                if actual_runs:
                    _fail("selector campaign recovery emits a run without seeds")
                expected_run_manifests = copy.deepcopy(prior_run_manifests)
                expected_run_cursors = list(prior_run_cursors)
            if (
                next_head["source_run_manifests"] != expected_run_manifests
                or next_head["source_run_cursors"] != expected_run_cursors
            ):
                _fail("selector campaign recovery run list drifted")
            campaign_complete = (
                campaign_window["last_row"]
                == next_head["source_campaign_prefix"]["records"]
            )
            expected_next_source_state = {
                **copy.deepcopy(expected_source_state),
                "source_phase": "RUNS_READY" if campaign_complete else "AUDITING",
                "source_audit_stage": "COMPLETE" if campaign_complete else "CAMPAIGNS",
                "source_campaign_cursor_records": campaign_window["last_row"],
                "source_campaign_cursor_bytes": campaign_window["last_byte"],
                "source_projection_next": None,
                "source_run_manifests": expected_run_manifests,
                "source_run_cursors": expected_run_cursors,
                "source_ready_run": None,
                "source_ready_count": 0,
                "source_ready_cursor": 0,
                "source_candidate_index": copy.deepcopy(
                    next_roots[SOURCE_CANDIDATE_INDEX_DOMAIN]
                ),
                "source_campaign_history_index": copy.deepcopy(
                    next_roots[SOURCE_CAMPAIGN_HISTORY_DOMAIN]
                ),
            }
        else:
            if set(window) != {"stage"} or any(planned_nodes_by_domain.values()):
                _fail("selector source barrier carries auth updates")
            if expected_source_state is None:
                if (
                    next_head["source_campaign_prefix"]["records"] != 0
                    or next_head["source_episode_prefix"]["records"] != 0
                ):
                    _fail("selector initial source barrier skipped nonempty ledgers")
                expected_next_source_state = {
                    "source_commit": next_head["source_commit"],
                    "source_observed_at": next_head["source_observed_at"],
                    "source_checkpoint": copy.deepcopy(next_head["source_checkpoint"]),
                    "source_campaign_prefix": copy.deepcopy(
                        next_head["source_campaign_prefix"]
                    ),
                    "source_episode_prefix": copy.deepcopy(
                        next_head["source_episode_prefix"]
                    ),
                    "source_phase": "RUNS_READY",
                    "source_audit_stage": "COMPLETE",
                    "source_campaign_cursor_records": 0,
                    "source_campaign_cursor_bytes": 0,
                    "source_episode_cursor_records": 0,
                    "source_episode_cursor_bytes": 0,
                    "source_episode_chunks": [],
                    "source_episode_group_count": 0,
                    "source_projection_next": None,
                    "source_run_manifests": [],
                    "source_run_cursors": [],
                    "source_ready_run": None,
                    "source_ready_count": 0,
                    "source_ready_cursor": 0,
                    "source_candidate_index": _empty_source_candidate_index(),
                    "source_campaign_history_index": _empty_source_campaign_history_index(),
                    "source_episode_identity_index": _empty_source_episode_identity_index(),
                    "source_episode_group_index": _empty_source_episode_group_index(),
                }
            elif (
                expected_source_state["source_phase"] == "AUDITING"
                and expected_source_state["source_audit_stage"] == "CAMPAIGNS"
                and expected_source_state["source_campaign_cursor_records"]
                == expected_source_state["source_campaign_prefix"]["records"]
            ):
                expected_next_source_state = {
                    **copy.deepcopy(expected_source_state),
                    "source_phase": "RUNS_READY",
                    "source_audit_stage": "COMPLETE",
                }
            else:
                if expected_source_state["source_phase"] not in {
                    "RUNS_READY",
                    "MERGING",
                }:
                    _fail("selector source barrier lacks its exact parent phase")
                runs = [
                    _load_source_run(root, pointer)
                    for pointer in expected_source_state["source_run_manifests"]
                ]
                if any(
                    cursor != 0
                    for cursor in expected_source_state["source_run_cursors"]
                ):
                    _fail("selector source barrier observed a consumed run")
                ready_count = sum(run["entry_count"] for run in runs)
                first_ready = next(
                    (
                        pointer
                        for pointer, run in zip(
                            expected_source_state["source_run_manifests"],
                            runs,
                            strict=True,
                        )
                        if run["entry_count"]
                    ),
                    None,
                )
                becomes_ready = expected_source_state["source_phase"] == "MERGING"
                expected_next_source_state = {
                    **copy.deepcopy(expected_source_state),
                    "source_phase": "READY" if becomes_ready else "MERGING",
                    "source_projection_next": first_ready if becomes_ready else None,
                    "source_ready_run": first_ready if becomes_ready else None,
                    "source_ready_count": ready_count if becomes_ready else 0,
                    "source_ready_cursor": 0,
                }

        actual_projection_keys = {
            item.key
            for item in objects
            if item.value.get("schema")
            in {
                "options.sparse_selector_source_seed/v1",
                "options.sparse_selector_source_run/v1",
                "options.sparse_selector_episode_chunk/v1",
            }
        }
        if actual_projection_keys != expected_projection_keys:
            _fail("selector source recovery contains orphan projection objects")

        for domain, entries in derived.items():
            nodes = planned_nodes_by_domain[domain]
            if not entries:
                if nodes or next_roots[domain] != prior_roots[domain]:
                    _fail("selector source recovery changed an untouched auth root")
                continue
            _replay_source_auth_batch(
                root,
                domain=domain,
                prior=prior_roots[domain],
                expected_next=next_roots[domain],
                entries=entries,
                planned_nodes=nodes,
                replace_keys=(
                    replace_group_keys
                    if domain == SOURCE_EPISODE_GROUP_DOMAIN
                    else None
                ),
            )
        for item in objects:
            schema = item.value.get("schema")
            if schema in {
                "options.sparse_selector_source_seed/v1",
                "options.sparse_selector_source_run/v1",
                "options.sparse_selector_episode_chunk/v1",
            } and not _source_epoch_object_matches(item.value, next_head):
                _fail("selector source intent object crossed authenticated epochs")
        run_pointers = list(next_head["source_run_manifests"])
        if len({pointer["id"] for pointer in run_pointers}) != len(run_pointers):
            _fail("selector source HEAD repeats a run pointer")
        for pointer in run_pointers:
            planned = by_pointer_id.get(pointer["id"])
            if planned is not None:
                if planned.pointer != pointer or planned.value.get("schema") != "options.sparse_selector_source_run/v1":
                    _fail("selector source HEAD run pointer differs from planned bytes")
            else:
                run = _load_source_run(root, pointer)
                if not _source_epoch_object_matches(run, next_head):
                    _fail("selector source HEAD run crossed authenticated epochs")
        for reference in next_head["source_episode_chunks"]:
            pointer = reference["pointer"]
            planned = by_pointer_id.get(pointer["id"])
            if planned is not None:
                chunk = _validate_episode_chunk(planned.value)
                if planned.pointer != pointer:
                    _fail("selector episode chunk planned pointer drifted")
                if (
                    chunk["source_commit"] != next_head["source_commit"]
                    or chunk["source_observed_at"]
                    != next_head["source_observed_at"]
                    or chunk["source_checkpoint"] != next_head["source_checkpoint"]
                ):
                    _fail("selector episode chunk crossed its HEAD epoch")
                if any(
                    chunk[field] != reference[field]
                    for field in (
                        "first_row",
                        "last_row",
                        "first_byte",
                        "last_byte",
                    )
                ):
                    _fail("selector episode chunk reference drifted")
            else:
                _load_episode_chunk(
                    root,
                    reference,
                    source_commit=next_head["source_commit"],
                    source_observed_at=next_head["source_observed_at"],
                    source_checkpoint=next_head["source_checkpoint"],
                )
        if (
            expected_next_source_state is None
            or _source_expected_state(next_head) != expected_next_source_state
        ):
            _fail("selector source recovery next state is not the exact transition")
        ready_pointer = next_head["source_ready_run"]
        if ready_pointer is not None and all(ready_pointer != item for item in run_pointers):
            _fail("selector source HEAD ready run is absent from its manifests")
        return CyclePlan(
            expected_head_id=clean["expected_head_id"],
            objects=tuple(objects),
            head=next_head,
            intent=clean,
        )
    expected_fields = {
        "schema",
        "intent_sha256",
        "expected_head_id",
        "expected_last_handoff_queue",
        "expected_last_candidate",
        "expected_candidate_count",
        "expected_candidate_index",
        "expected_last_decision",
        "expected_decision_count",
        "objects",
        "next_head",
    }
    if not isinstance(intent, Mapping) or set(intent) != expected_fields:
        _fail("selector advance intent fields are malformed")
    clean = copy.deepcopy(dict(intent))
    if clean["schema"] != "options.sparse_selector_advance_intent/v1":
        _fail("selector advance intent schema drifted")
    if clean["intent_sha256"] != _content_id("", clean, field="intent_sha256"):
        _fail("selector advance intent identity drifted")
    if (
        not isinstance(clean["objects"], list)
        or len(clean["objects"]) > MAX_SOURCE_OBJECTS_PER_CYCLE
        or len(canonical_bytes(clean)) > MAX_INTENT_BYTES
    ):
        _fail("selector advance recovery intent exceeds its bounds")
    expected_head_id = clean["expected_head_id"]
    if expected_head_id is not None and not re.fullmatch(
        r"ossh_[a-f0-9]{64}", expected_head_id
    ):
        _fail("selector intent expected HEAD id is malformed")
    expected_last_queue = clean["expected_last_handoff_queue"]
    if expected_last_queue is not None and (
        expected_last_queue is not None
        and (
            not isinstance(expected_last_queue, Mapping)
            or set(expected_last_queue) != {"id", "key", "sha256", "bytes"}
            or not re.fullmatch(
                r"ossq_[a-f0-9]{64}", str(expected_last_queue.get("id"))
            )
        )
    ):
        _fail("selector intent expected queue parent is malformed")

    def validate_expected_tail(
        pointer: object, count: object, *, prefix: str, namespace: str, label: str
    ) -> None:
        if type(count) is not int or count < 0 or (count == 0) != (pointer is None):
            _fail(f"selector intent expected {label} count/tail is malformed")
        if pointer is not None and (
            not isinstance(pointer, Mapping)
            or set(pointer) != {"id", "key", "sha256", "bytes"}
            or not re.fullmatch(rf"{prefix}_[a-f0-9]{{64}}", str(pointer.get("id")))
            or not str(pointer.get("key", "")).startswith(f"{namespace}/")
        ):
            _fail(f"selector intent expected {label} pointer is malformed")

    validate_expected_tail(
        clean["expected_last_candidate"],
        clean["expected_candidate_count"],
        prefix="ossc",
        namespace="candidates",
        label="candidate",
    )
    try:
        expected_candidate_index = private_auth_dict.validate_sharded_root(
            clean["expected_candidate_index"], domain=CANDIDATE_INDEX_DOMAIN
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc
    if expected_candidate_index["entry_count"] != clean["expected_candidate_count"]:
        _fail("selector intent candidate index count drifted")
    validate_expected_tail(
        clean["expected_last_decision"],
        clean["expected_decision_count"],
        prefix="ossd",
        namespace="decisions",
        label="decision",
    )
    objects: list[PlannedObject] = []
    object_keys: set[str] = set()
    if not isinstance(clean["objects"], list):
        _fail("selector intent object list is malformed")
    for receipt in clean["objects"]:
        if not isinstance(receipt, Mapping) or set(receipt) != {
            "key",
            "sha256",
            "bytes",
            "value",
        }:
            _fail("selector intent object receipt is malformed")
        item = PlannedObject(key=receipt["key"], value=receipt["value"])
        if (
            len(item.body) != receipt["bytes"]
            or _sha256(item.body) != receipt["sha256"]
        ):
            _fail("selector intent object receipt differs from its value")
        schema = item.value.get("schema")
        if schema == "options.sparse_selector_candidate/v1":
            expected_key = f"candidates/{item.value.get('candidate_id')}.json"
        elif schema == "options.sparse_selector_candidate_manifest/v1":
            expected_key = f"manifests/{item.value.get('manifest_id')}.json"
        elif schema == "options.sparse_selector_decision/v1":
            expected_key = f"decisions/{item.value.get('decision_id')}.json"
        elif schema == "options.sparse_selector_cycle_receipt/v1":
            expected_key = f"cycles/{item.value.get('cycle_id')}.json"
        elif schema == "options.sparse_selector_handoff_queue_item/v1":
            expected_key = _handoff_queue_key(item.value.get("ordinal"))
        elif schema == private_auth_dict.SCHEMA:
            if item.value.get("domain") != CANDIDATE_INDEX_DOMAIN:
                _fail("selector advance intent contains a foreign auth node")
            expected_key = (
                f"{private_auth_dict.NAMESPACE}/{item.value.get('node_id')}.json"
            )
        elif schema == "options.sparse_selector_evidence_generation/v1":
            if len(item.body) > MAX_EVIDENCE_GENERATION_BYTES:
                _fail("selector advance intent evidence generation exceeds its envelope")
            validate_runtime_object(
                item.value, label="selector advance intent evidence generation"
            )
            expected_key = f"evidence/{_sha256(item.body)}.json"
        elif schema == "options.sparse_selector_w1a_source_receipt/v1":
            if len(item.body) > MAX_W1A_SOURCE_RECEIPT_BYTES:
                _fail("selector advance intent W1A source exceeds its compact bound")
            validate_runtime_object(
                item.value, label="selector advance intent W1A source receipt"
            )
            expected_key = f"evidence/{_sha256(item.body)}.json"
        elif schema in {
            "options.sparse_selector_konseki_evidence/v1",
            "options.sparse_selector_mark_evidence/v1",
            "options.sparse_selector_lifecycle_evidence/v1",
        }:
            if len(item.body) > MAX_EVIDENCE_OBJECT_BYTES:
                _fail("selector advance intent evidence exceeds its envelope")
            expected_key = f"evidence/{_sha256(item.body)}.json"
        else:
            _fail("selector advance intent contains a foreign object type")
        if item.key != expected_key:
            _fail("selector advance intent object namespace drifted")
        _object_path(root, item.key)
        if item.key in object_keys:
            _fail("selector intent repeats an immutable object key")
        object_keys.add(item.key)
        objects.append(item)
    next_head = validate_runtime_object(clean["next_head"], label="intent next HEAD")
    if next_head["head_id"] != _content_id("ossh_", next_head, field="head_id"):
        _fail("selector intent next HEAD identity drifted")
    planned_by_key = {item.key: item for item in objects}
    queue_pointer = next_head["last_handoff_queue"]
    queue_object = planned_by_key.get(queue_pointer["key"])
    queue_objects = [
        item for item in objects if item.key.startswith(f"{HANDOFF_QUEUE_NAMESPACE}/")
    ]
    if queue_object is None:
        _fail("selector intent omits its next immutable handoff queue object")
    queue_item = validate_runtime_object(
        queue_object.value, label="intent handoff queue item"
    )
    queued_cycle = planned_by_key.get(queue_item["selector_cycle"]["key"])
    if queued_cycle is None:
        _fail("selector intent queue omits its exact selector cycle object")
    cycle = validate_runtime_object(
        queued_cycle.value, label="intent queued selector cycle"
    )
    prior_head = _load_head(root)
    if prior_head is None or prior_head["head_id"] not in {
        expected_head_id,
        next_head["head_id"],
    }:
        _fail("selector advance intent parent HEAD is unavailable")
    expected_pending = cycle["settled_manifest"]
    parent_is_live = prior_head["head_id"] == expected_head_id
    if parent_is_live:
        expected_runtime_parent = {
            "expected_last_handoff_queue": prior_head["last_handoff_queue"],
            "expected_last_candidate": prior_head["last_candidate"],
            "expected_candidate_count": prior_head["candidate_count"],
            "expected_candidate_index": prior_head["candidate_index"],
            "expected_last_decision": prior_head["last_decision"],
            "expected_decision_count": prior_head["decision_count"],
        }
        if any(clean[field] != value for field, value in expected_runtime_parent.items()):
            _fail("selector advance intent changed its authenticated runtime parent")
        unchanged_source_fields = (
            "source_observed_at",
            "source_commit",
            "source_campaign_prefix",
            "source_episode_prefix",
            "source_checkpoint",
            "source_audit_stage",
            "source_campaign_cursor_records",
            "source_campaign_cursor_bytes",
            "source_episode_cursor_records",
            "source_episode_cursor_bytes",
            "source_episode_chunks",
            "source_episode_identity_index",
            "source_episode_group_index",
            "source_episode_group_count",
            "source_candidate_index",
            "source_campaign_history_index",
            "source_run_manifests",
            "source_ready_count",
        )
        if (
            prior_head["source_phase"] not in {"READY", "DRAINED"}
            or any(next_head[field] != prior_head[field] for field in unchanged_source_fields)
            or cycle["settled_manifest"] != prior_head["pending_manifest"]
            or cycle["previous_head_id"] != prior_head["head_id"]
            or cycle["previous_cycle"] != prior_head["last_cycle"]
            or next_head["previous_head_id"] != prior_head["head_id"]
            or next_head["generation"] != prior_head["generation"] + 1
            or next_head["cycle_count"] != prior_head["cycle_count"] + 1
            or next_head["handoff_queue_count"]
            != prior_head["handoff_queue_count"] + 1
            or cycle["source_campaign_cursor_before"]
            != prior_head["source_campaign_cursor_records"]
        ):
            _fail("selector advance intent changed its authenticated parent state")

    expected_ready: list[Mapping[str, Any]] = []
    replay_runs: list[Mapping[str, Any]] = []
    replay_cursors: list[int] = []
    if parent_is_live:
        replay_cursors = list(prior_head["source_run_cursors"])
        replay_heap: list[tuple[str, str, int]] = []
        total_ready = 0
        for index, (pointer, cursor) in enumerate(
            zip(
                prior_head["source_run_manifests"],
                replay_cursors,
                strict=True,
            )
        ):
            run = _load_source_run(root, pointer)
            if not _source_epoch_object_matches(run, prior_head):
                _fail("selector advance intent ready run crossed epochs")
            replay_runs.append(run)
            total_ready += run["entry_count"]
            if cursor < run["entry_count"]:
                entry = run["entries"][cursor]
                heapq.heappush(
                    replay_heap,
                    (entry["candidate_available_at"], entry["candidate_id"], index),
                )
        while replay_heap and len(expected_ready) < len(cycle["candidate_pointers"]):
            _available, _candidate_id_value, index = heapq.heappop(replay_heap)
            cursor = replay_cursors[index]
            entry = replay_runs[index]["entries"][cursor]
            expected_ready.append(entry)
            cursor += 1
            replay_cursors[index] = cursor
            if cursor < replay_runs[index]["entry_count"]:
                successor = replay_runs[index]["entries"][cursor]
                heapq.heappush(
                    replay_heap,
                    (
                        successor["candidate_available_at"],
                        successor["candidate_id"],
                        index,
                    ),
                )
        first_unconsumed = next(
            (
                pointer
                for pointer, run, cursor in zip(
                    prior_head["source_run_manifests"],
                    replay_runs,
                    replay_cursors,
                    strict=True,
                )
                if cursor < run["entry_count"]
            ),
            None,
        )
        expected_ready_cursor = sum(replay_cursors)
        expected_phase = (
            "DRAINED"
            if expected_ready_cursor == total_ready and not expected_ready
            else "READY"
        )
        if (
            total_ready != prior_head["source_ready_count"]
            or sum(prior_head["source_run_cursors"])
            != prior_head["source_ready_cursor"]
            or replay_cursors != next_head["source_run_cursors"]
            or expected_ready_cursor
            != prior_head["source_ready_cursor"] + len(expected_ready)
            or next_head["source_ready_cursor"] != expected_ready_cursor
            or next_head["source_ready_run"] != first_unconsumed
            or next_head["source_phase"] != expected_phase
            or next_head["source_projection_next"]
            != (None if expected_phase == "DRAINED" else first_unconsumed)
        ):
            _fail("selector advance intent skipped or reordered its ready prefix")
    pending_manifest = next_head["pending_manifest"]
    manifest_object: PlannedObject | None = None
    manifest: dict[str, Any] | None = None
    if pending_manifest is not None:
        manifest_object = planned_by_key.get(pending_manifest["key"])
        if manifest_object is None:
            _fail("selector intent omits its next pending manifest")
        manifest = validate_runtime_object(
            manifest_object.value, label="intent pending manifest"
        )

    candidate_objects: list[PlannedObject] = []
    candidate_predecessor = clean["expected_last_candidate"]
    candidate_ordinal = clean["expected_candidate_count"]
    for pointer in cycle["candidate_pointers"]:
        planned = planned_by_key.get(pointer["key"])
        if planned is None or planned.pointer != pointer:
            _fail("selector intent omits an exact chained candidate object")
        candidate = validate_runtime_object(
            planned.value, label="intent chained candidate"
        )
        candidate_ordinal += 1
        if (
            candidate["ordinal"] != candidate_ordinal
            or candidate["previous_candidate"] != candidate_predecessor
        ):
            _fail("selector intent candidate chain is not contiguous")
        candidate_objects.append(planned)
        candidate_predecessor = pointer
    if parent_is_live:
        if len(candidate_objects) != len(expected_ready):
            _fail("selector advance intent ready prefix cardinality drifted")
        exact_predecessor = clean["expected_last_candidate"]
        exact_ordinal = clean["expected_candidate_count"]
        for item, entry in zip(candidate_objects, expected_ready, strict=True):
            seed = _validate_source_seed(
                _load_pointer(root, entry["seed"], label="intent ready source seed")
            )
            exact_ordinal += 1
            expected_candidate = _candidate_from_seed(
                seed,
                ordinal=exact_ordinal,
                previous_candidate=exact_predecessor,
            )
            if (
                not _source_epoch_object_matches(seed, prior_head)
                or seed["candidate_id"] != entry["candidate_id"]
                or seed["candidate_available_at"] != entry["candidate_available_at"]
                or item.value != expected_candidate
            ):
                _fail("selector advance intent candidate differs from ready prefix")
            exact_predecessor = item.pointer

    decision_objects: list[PlannedObject] = []
    decision_predecessor = clean["expected_last_decision"]
    decision_ordinal = clean["expected_decision_count"]
    for pointer in cycle["decision_pointers"]:
        planned = planned_by_key.get(pointer["key"])
        if planned is None or planned.pointer != pointer:
            _fail("selector intent omits an exact chained decision object")
        decision = validate_runtime_object(
            planned.value, label="intent chained decision"
        )
        decision_ordinal += 1
        if (
            decision["ordinal"] != decision_ordinal
            or decision["previous_decision"] != decision_predecessor
        ):
            _fail("selector intent decision chain is not contiguous")
        decision_objects.append(planned)
        decision_predecessor = pointer

    used_evidence_keys: set[str] = set()
    w1a_cache: dict[str, _W1APublication] = {}
    planned_candidates_by_pointer = {
        canonical_bytes(item.pointer): item.value for item in candidate_objects
    }
    for item in decision_objects:
        candidate_pointer = item.value["candidate"]
        candidate = planned_candidates_by_pointer.get(canonical_bytes(candidate_pointer))
        if candidate is None:
            candidate = _load_pointer(
                root, candidate_pointer, label="intent decided candidate"
            )
        if item.value["evidence"]["options"] != candidate_pointer:
            _fail("selector intent decision options evidence drifted")
        used_evidence_keys.update(
            _validate_decision_evidence_objects(
                root,
                item.value,
                planned_by_key=planned_by_key,
                candidate=candidate,
                evidence_inputs=evidence_inputs,
                w1a_cache=w1a_cache,
            )
        )
    intent_evidence_keys = {
        item.key for item in objects if item.key.startswith("evidence/")
    }
    if intent_evidence_keys != used_evidence_keys:
        _fail("selector advance intent contains orphan or missing evidence")
    source_receipts = [
        item.value
        for item in objects
        if item.value.get("schema")
        == "options.sparse_selector_w1a_source_receipt/v1"
    ]
    if len(source_receipts) > 1:
        _fail("selector advance intent repeats its W1A source receipt")
    if parent_is_live:
        expected_w1a_high_water = _advance_w1a_high_water(
            prior_head["w1a_publication_high_water"],
            None if not source_receipts else source_receipts[0],
        )
        if next_head["w1a_publication_high_water"] != expected_w1a_high_water:
            _fail("selector advance intent W1A high-water is not monotone")

    if parent_is_live:
        proposal_session = prior_head["proposal_session_date"]
        proposal_count = prior_head["proposal_session_count"]
        for item in decision_objects:
            decision = item.value
            session = decision["decision_nyse_session_date"]
            if session is not None:
                parsed_session = date.fromisoformat(session)
                if not nyse_calendar.is_session(parsed_session):
                    _fail("selector intent decision session is not a NYSE session")
                if proposal_session is None:
                    proposal_session = session
                    proposal_count = 0
                elif session < proposal_session:
                    _fail("selector intent proposal session moved backward")
                elif session > proposal_session:
                    prior_session = date.fromisoformat(proposal_session)
                    transitions = nyse_calendar.sessions_between(
                        prior_session + timedelta(days=1), parsed_session
                    )
                    if not transitions or transitions[-1] != parsed_session:
                        _fail("selector intent proposal counter reset off-session")
                    proposal_session = session
                    proposal_count = 0
            if decision["action"] == "propose":
                if (
                    session is None
                    or session != proposal_session
                    or proposal_count >= PROPOSAL_CAP
                    or decision["proposal_ordinal"] != proposal_count + 1
                ):
                    _fail("selector intent proposal ordinal escaped its session cap")
                proposal_count += 1
        if (
            next_head["proposal_session_date"] != proposal_session
            or next_head["proposal_session_count"] != proposal_count
            or cycle["propose_count"]
            != sum(item.value["action"] == "propose" for item in decision_objects)
            or cycle["abstain_count"]
            != sum(item.value["action"] == "abstain" for item in decision_objects)
        ):
            _fail("selector intent proposal session state drifted")

    if expected_pending is not None:
        settled = _load_pointer(root, expected_pending, label="intent settled manifest")
        if (
            len(decision_objects) != settled["candidate_count"]
            or [item.value["manifest_id"] for item in decision_objects]
            != [settled["manifest_id"]] * settled["candidate_count"]
            or [item.value["candidate"] for item in decision_objects]
            != settled["candidates"]
        ):
            _fail("selector intent did not settle its prior manifest exactly")
    elif decision_objects:
        _fail("selector intent settles decisions without a pending manifest")

    intent_candidate_keys = {
        item.key for item in objects if item.key.startswith("candidates/")
    }
    intent_decision_keys = {
        item.key for item in objects if item.key.startswith("decisions/")
    }
    if intent_candidate_keys != {item.key for item in candidate_objects}:
        _fail("selector intent contains an orphan candidate object")
    if intent_decision_keys != {item.key for item in decision_objects}:
        _fail("selector intent contains an orphan decision object")
    index_objects = [
        item
        for item in objects
        if item.key.startswith(f"{private_auth_dict.NAMESPACE}/")
    ]
    for item in index_objects:
        try:
            node = private_auth_dict.validate_node(
                item.value, domain=CANDIDATE_INDEX_DOMAIN
            )
        except private_auth_dict.AuthDictError as exc:
            raise SparseSelectorError(str(exc)) from exc
        if item.pointer != private_auth_dict.pointer(node):
            _fail("selector intent candidate index node pointer drifted")
    index_by_id = {item.value["node_id"]: item.value for item in index_objects}

    def load_intent_index_node(pointer: Mapping[str, Any]) -> Mapping[str, Any]:
        planned = index_by_id.get(pointer.get("id"))
        if planned is not None:
            if private_auth_dict.pointer(planned) != pointer:
                _fail("selector intent index pointer differs from planned bytes")
            return planned
        return _load_candidate_index_node(root, pointer)

    try:
        recomputed_index, recomputed_nodes = private_auth_dict.sharded_insert_many(
            expected_candidate_index,
            [
                (
                    _candidate_index_key(item.value["campaign_id"]),
                    {
                        "campaign_id": item.value["campaign_id"],
                        "candidate_id": item.value["candidate_id"],
                        "candidate": item.pointer,
                    },
                )
                for item in candidate_objects
            ],
            domain=CANDIDATE_INDEX_DOMAIN,
            load_node=load_intent_index_node,
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc
    if (
        recomputed_index != next_head["candidate_index"]
        or {node["node_id"] for node in recomputed_nodes} != set(index_by_id)
    ):
        _fail("selector intent candidate index is not the exact batch transition")
    if manifest is None:
        if (
            candidate_objects
            or cycle["next_manifest"] is not None
            or any(item.key.startswith("manifests/") for item in objects)
        ):
            _fail("selector manifest-free intent admits candidates")
    elif (
        manifest["candidates"] != cycle["candidate_pointers"]
        or manifest["candidates"] != [item.pointer for item in candidate_objects]
        or len(
            [item for item in objects if item.key.startswith("manifests/")]
        )
        != 1
    ):
        _fail("selector intent manifest and candidate prefix differ")

    manifest_mismatch = (
        manifest is not None
        and manifest_object is not None
        and (
            manifest_object.pointer != pending_manifest
            or cycle["next_manifest"] != pending_manifest
            or manifest["source_campaign_prefix"]
            != next_head["source_campaign_prefix"]
            or manifest["source_episode_prefix"]
            != next_head["source_episode_prefix"]
            or manifest["source_checkpoint"] != next_head["source_checkpoint"]
            or manifest["cycle_id"] != cycle["cycle_id"]
            or manifest["source_commit"] != next_head["source_commit"]
        )
    )

    try:
        scheduled_clock = _utc(cycle["scheduled_at"], label="intent scheduled clock")
        started_clock = _utc(cycle["started_at"], label="intent started clock")
        completed_clock = _utc(cycle["completed_at"], label="intent completed clock")
        frozen_clock = (
            None
            if manifest is None
            else _utc(manifest["frozen_at"], label="intent manifest freeze clock")
        )
    except (KeyError, TypeError) as exc:
        raise SparseSelectorError("selector intent clocks are malformed") from exc
    if (
        started_clock < scheduled_clock
        or completed_clock < started_clock
        or completed_clock >= scheduled_clock + timedelta(seconds=300)
        or (frozen_clock is not None and not started_clock <= frozen_clock <= completed_clock)
        or next_head["advanced_at"] != cycle["completed_at"]
    ):
        _fail("selector intent cycle/manifest clocks are noncausal")
    if parent_is_live and prior_head["last_cycle"] is not None:
        prior_cycle = _load_pointer(
            root, prior_head["last_cycle"], label="intent prior selector cycle"
        )
        if scheduled_clock <= _utc(
            prior_cycle["scheduled_at"], label="intent prior scheduled clock"
        ):
            _fail("selector intent scheduled slot is not strictly monotone")

    if parent_is_live:
        previous_queue_value = (
            None
            if prior_head["last_handoff_queue"] is None
            else _load_pointer(
                root,
                prior_head["last_handoff_queue"],
                label="intent prior handoff queue item",
            )
        )
        expected_queue_item = _make_handoff_queue_item(
            root=root,
            ordinal=prior_head["handoff_queue_count"] + 1,
            previous_queue_item=prior_head["last_handoff_queue"],
            previous_queue_value=previous_queue_value,
            previous_cycle=prior_head["last_cycle"],
            cycle_object=queued_cycle,
        )
        if queue_item != expected_queue_item:
            _fail("selector intent handoff queue is not the exact parent transition")

    if (
        len(queue_objects) != 1
        or queue_object.pointer != queue_pointer
        or queue_object.key != _handoff_queue_key(next_head["handoff_queue_count"])
        or queue_item["ordinal"] != next_head["handoff_queue_count"]
        or queue_item["selector_cycle"] != next_head["last_cycle"]
        or queue_item["previous_queue_item"] != expected_last_queue
        or queue_item["previous_queue_item_id"]
        != (None if expected_last_queue is None else expected_last_queue["id"])
        or queued_cycle.pointer != queue_item["selector_cycle"]
        or cycle.get("schema") != "options.sparse_selector_cycle_receipt/v1"
        or cycle["ordinal"] != next_head["cycle_count"]
        or manifest_mismatch
        or cycle["previous_head_id"] != expected_head_id
        or cycle["source_campaign_prefix"] != next_head["source_campaign_prefix"]
        or cycle["source_episode_prefix"] != next_head["source_episode_prefix"]
        or cycle["source_checkpoint"] != next_head["source_checkpoint"]
        or cycle["source_observed_at"] != next_head["source_observed_at"]
        or cycle["source_commit"] != next_head["source_commit"]
        or cycle["source_campaign_cursor_after"]
        != next_head["source_campaign_cursor_records"]
        or cycle["source_projection_after"] != next_head["source_projection_next"]
        or cycle["previous_candidate"] != clean["expected_last_candidate"]
        or cycle["candidate_count_before"] != clean["expected_candidate_count"]
        or cycle["last_candidate"] != candidate_predecessor
        or cycle["candidate_count_after"] != candidate_ordinal
        or next_head["last_candidate"] != candidate_predecessor
        or next_head["candidate_count"] != candidate_ordinal
        or next_head["candidate_index"]["entry_count"] != candidate_ordinal
        or cycle["previous_decision"] != clean["expected_last_decision"]
        or cycle["decision_count_before"] != clean["expected_decision_count"]
        or cycle["last_decision"] != decision_predecessor
        or cycle["decision_count_after"] != decision_ordinal
        or next_head["last_decision"] != decision_predecessor
        or next_head["decision_count"] != decision_ordinal
        or len(candidate_objects)
        != cycle["candidate_count_after"] - cycle["candidate_count_before"]
        or len(decision_objects) != cycle["decision_count"]
        or queue_item["previous_cycle"] != cycle["previous_cycle"]
        or queue_item["runtime_armed"] is not True
        or cycle["runtime_armed"] is not True
    ):
        _fail("selector intent handoff queue does not match its next HEAD")
    replay_inputs = evidence_inputs or EvidenceInputs()
    if parent_is_live and evidence_inputs is not None:
        replay_values = _advance_replay_clock_values(
            cycle=cycle,
            manifest=manifest,
            decisions=decision_objects,
            planned_by_key=planned_by_key,
        )
        replay_snapshot: EvidenceSnapshot | None = None
        if decision_objects:
            generation_pointer = decision_objects[0].value["evidence"]["generation"]
            generation_item = planned_by_key.get(generation_pointer["key"])
            if generation_item is None or generation_item.pointer != generation_pointer:
                _fail("selector intent replay lacks its evidence generation")
            replay_snapshot = _evidence_snapshot_from_generation(
                generation_item.value,
                evidence_inputs,
                root=root,
                planned_by_key=planned_by_key,
            )
        replay_index = 0

        def replay_clock() -> datetime:
            nonlocal replay_index
            if replay_index >= len(replay_values):
                _fail("selector intent replay requested an unrecorded clock")
            value = replay_values[replay_index]
            replay_index += 1
            return value

        pinned_source = SourceSnapshot(
            commit=prior_head["source_commit"],
            campaigns_raw=None,
            episodes_raw=None,
            observed_at=prior_head["source_observed_at"],
            campaigns_blob_oid=prior_head["source_campaign_prefix"]["git_blob_oid"],
            episodes_blob_oid=prior_head["source_episode_prefix"]["git_blob_oid"],
            checkpoint_raw=None,
            checkpoint_blob_oid=prior_head["source_checkpoint"]["git_blob_oid"],
        )
        replayed = _plan_cycle_once(
            root=root,
            source=pinned_source,
            evidence_inputs=evidence_inputs,
            scheduled_at=cycle["scheduled_at"],
            clock=replay_clock,
            runtime_armed=True,
            admission_cap=len(cycle["candidate_pointers"]),
            settlement_cache={},
            evidence_snapshot=replay_snapshot,
        )
        if replay_index != len(replay_values):
            _fail("selector intent replay left authenticated clocks unused")
        if (
            replayed.expected_head_id != expected_head_id
            or replayed.objects != tuple(objects)
            or replayed.head != next_head
            or replayed.intent != clean
        ):
            _fail("selector advance intent differs from exact parent replay")
    return CyclePlan(
        expected_head_id=expected_head_id,
        objects=tuple(objects),
        head=next_head,
        intent=clean,
        evidence_inputs=replay_inputs,
    )


def _read_intent(root: Path) -> dict[str, Any] | None:
    attempt_body = _read_private_file(
        root / INTENT_ATTEMPT_FILE,
        root=root,
        limit=1024 * 1024,
        required=False,
    )
    body = _read_private_file(
        root / INTENT_FILE, root=root, limit=MAX_INTENT_BYTES, required=False
    )
    if body is None and attempt_body is None:
        return None
    if body is None:
        _fail("selector advance intent has an unclosed publication attempt")
    _reprove_exact_private_file(
        root / INTENT_FILE,
        body,
        root=root,
        limit=MAX_INTENT_BYTES,
        label="selector advance intent",
    )
    value = strict_json(body, label="selector advance intent")
    if not isinstance(value, dict) or canonical_bytes(value) != body:
        _fail("selector advance intent is not canonical")
    seal_path = _object_path(root, _intent_seal_key(value))
    seal_body = _read_private_file(
        seal_path, root=root, limit=1024 * 1024, required=True
    )
    if seal_body != _intent_seal_body(value):
        _fail("selector advance intent differs from its durable recovery seal")
    if attempt_body is not None and attempt_body != _intent_attempt_body(body):
        _fail("selector advance intent publication attempt drifted")
    return value


def _intent_attempt_body(intent_body: bytes) -> bytes:
    return canonical_bytes(
        {
            "schema": "options.sparse_selector_advance_intent_attempt/v1",
            "intent_sha256": _sha256(intent_body),
            "intent_bytes": len(intent_body),
            "recovery_allowed": False,
        }
    )


def _intent_seal_key(intent: Mapping[str, Any]) -> str:
    parent = intent.get("expected_head_id")
    if parent is None:
        parent = "genesis"
    if parent != "genesis" and (
        not isinstance(parent, str)
        or re.fullmatch(r"ossh_[0-9a-f]{64}", parent) is None
    ):
        _fail("selector advance intent seal parent is malformed")
    return f"{INTENT_SEAL_NAMESPACE}/{parent}.json"


def _intent_seal_body(intent: Mapping[str, Any]) -> bytes:
    intent_body = canonical_bytes(intent)
    next_head = intent.get("next_head")
    if not isinstance(next_head, Mapping):
        _fail("selector advance intent seal lacks its next HEAD")
    return canonical_bytes(
        {
            "schema": "options.sparse_selector_advance_intent_seal/v1",
            "parent_head_id": intent.get("expected_head_id"),
            "next_head_id": next_head.get("head_id"),
            "intent_sha256": _sha256(intent_body),
            "intent_bytes": len(intent_body),
        }
    )


def _clear_advance_intent(root: Path, intent: Mapping[str, Any]) -> None:
    """Remove an exact intent and its independent durable recovery seal."""

    intent_body = canonical_bytes(intent)
    durable_intent = _read_private_file(
        root / INTENT_FILE, root=root, limit=MAX_INTENT_BYTES, required=True
    )
    durable_seal = _read_private_file(
        _object_path(root, _intent_seal_key(intent)),
        root=root,
        limit=1024 * 1024,
        required=True,
    )
    if (
        durable_intent != intent_body
        or durable_seal != _intent_seal_body(intent)
    ):
        _fail("selector advance intent or recovery seal drifted before cleanup")
    attempt_body = _read_private_file(
        root / INTENT_ATTEMPT_FILE,
        root=root,
        limit=1024 * 1024,
        required=False,
    )
    if attempt_body is not None and attempt_body != _intent_attempt_body(intent_body):
        _fail("selector advance intent attempt drifted before cleanup")
    lane = _ACTIVE_SELECTOR_LANE.get()
    assert lane is not None
    os.unlink(INTENT_FILE, dir_fd=lane.root_fd)
    if attempt_body is not None:
        os.unlink(INTENT_ATTEMPT_FILE, dir_fd=lane.root_fd)
    os.fsync(lane.root_fd)


def _publish_advance_intent(root: Path, intent: Mapping[str, Any]) -> None:
    """Publish recovery authority only across a proven durable rename boundary."""

    intent_path = root / INTENT_FILE
    attempt_path = root / INTENT_ATTEMPT_FILE
    if (
        _read_private_file(
            intent_path, root=root, limit=MAX_INTENT_BYTES, required=False
        )
        is not None
    ):
        _fail("selector already has a durable advance intent")
    if (
        _read_private_file(attempt_path, root=root, limit=1024 * 1024, required=False)
        is not None
    ):
        _fail("selector advance intent has an unclosed publication attempt")

    intent_body = canonical_bytes(intent)
    temporary = _stage_atomic_write(
        intent_path,
        intent_body,
        root=root,
        limit=MAX_INTENT_BYTES,
    )
    try:
        _atomic_write(
            attempt_path,
            _intent_attempt_body(intent_body),
            root=root,
            limit=1024 * 1024,
        )
        # If rename or its directory fsync has an uncertain outcome, the
        # already-durable attempt remains and all future recovery fails closed.
        _install_staged_write(
            intent_path,
            temporary,
            intent_body,
            root=root,
            limit=MAX_INTENT_BYTES,
        )
        attempt_body = _read_private_file(
            attempt_path, root=root, limit=1024 * 1024, required=True
        )
        attempt_metadata = os.stat(
            INTENT_ATTEMPT_FILE,
            dir_fd=_ACTIVE_SELECTOR_LANE.get().root_fd,
            follow_symlinks=False,
        )
        if (
            attempt_body
            != _intent_attempt_body(intent_body)
            or stat.S_ISLNK(attempt_metadata.st_mode)
            or not stat.S_ISREG(attempt_metadata.st_mode)
            or attempt_metadata.st_nlink != 1
            or attempt_metadata.st_uid != os.getuid()
            or stat.S_IMODE(attempt_metadata.st_mode) != 0o600
        ):
            _fail("selector intent publication attempt metadata drifted")
        # Publish a parent-keyed immutable seal before granting recovery
        # authority.  It remains for the store lifetime, so an alternate
        # self-consistent intent for the same parent cannot replace history.
        _write_immutable(
            _object_path(root, _intent_seal_key(intent)),
            _intent_seal_body(intent),
            root=root,
        )
        lane = _ACTIVE_SELECTOR_LANE.get()
        assert lane is not None
        os.unlink(INTENT_ATTEMPT_FILE, dir_fd=lane.root_fd)
        os.fsync(lane.root_fd)
    finally:
        _discard_staged_write(temporary)


@contextmanager
def _w1a_commit_fence(
    root: Path, plan: CyclePlan, inputs: EvidenceInputs
) -> Iterator[None]:
    receipts = [
        item.value
        for item in plan.objects
        if item.value.get("schema")
        == "options.sparse_selector_w1a_source_receipt/v1"
    ]
    if not receipts:
        yield
        return
    if len(receipts) != 1 or inputs.w1a_receipt_root is None:
        _fail("selector transition lacks one trusted W1A source root")
    _assert_evidence_roots_distinct(root, inputs)
    receipt = validate_runtime_object(
        receipts[0], label="selector final W1A source fence"
    )
    with _locked_w1a_publication(Path(inputs.w1a_receipt_root)) as publication:
        manifest = _load_pointer(
            root,
            receipt["settled_manifest"],
            label="selector final W1A settled manifest",
        )
        candidate_rows = [
            (
                copy.deepcopy(dict(pointer)),
                _load_pointer(root, pointer, label="selector final W1A candidate"),
            )
            for pointer in manifest["candidates"]
        ]
        if (
            receipt["root_path_sha256"] != publication.root_path_sha256
            or receipt["head"] != publication.head
            or receipt["head_sha256"] != _sha256(publication.head_body)
            or receipt["head_bytes"] != len(publication.head_body)
            or receipt["audit_id"] != publication.audit["audit_id"]
            or receipt["reference_count"] != len(publication.references)
            or receipt["descriptors"]
            != _w1a_descriptors(candidate_rows, publication.references)
        ):
            raise EvidenceGenerationDrift(
                "W1A publication changed before selector intent seal"
            )
        # The durable intent and its parent-keyed seal are published while the
        # exact source HEAD remains locked and fully re-authenticated.
        yield


def _commit_cycle_locked(
    root: Path,
    plan: CyclePlan | None,
    *,
    evidence_inputs: EvidenceInputs | None = None,
    hook: Callable[[str], None] | None = None,
    trusted_internal_plan: bool = False,
) -> dict[str, Any]:
    """Commit or recover one intent while the caller owns the store lock."""

    private_root = root
    existing_intent = _read_intent(private_root)
    if existing_intent is not None:
        active = _plan_from_intent(
            private_root,
            existing_intent,
            evidence_inputs=evidence_inputs or EvidenceInputs(),
        )
        current_head = _load_head(private_root)
        current_id = None if current_head is None else current_head["head_id"]
        if current_id not in {active.expected_head_id, active.head["head_id"]}:
            _fail("selector durable intent is stale before immutable publication")
    else:
        if plan is None:
            _fail("selector has no transition to commit or recover")
        plan_evidence_inputs = evidence_inputs or plan.evidence_inputs
        if trusted_internal_plan:
            # advance() creates this plan inside the same exclusive store-lock
            # scope and never exposes a mutation boundary before publication.
            # Crash recovery still uses the independently sealed intent and the
            # full deterministic replay path above.
            active = plan
        else:
            # A caller-provided CyclePlan is never publication authority.
            reconstructed = _plan_from_intent(
                private_root,
                plan.intent,
                evidence_inputs=plan_evidence_inputs,
            )
            if (
                reconstructed.expected_head_id != plan.expected_head_id
                or reconstructed.objects != plan.objects
                or reconstructed.head != plan.head
                or reconstructed.intent != plan.intent
            ):
                _fail("selector supplied plan differs from its authenticated intent")
            active = reconstructed
        current_head = _load_head(private_root)
        current_head_id = current_head["head_id"] if current_head is not None else None
        if (
            current_head_id != active.expected_head_id
            or (
                current_head is None
                and (
                    active.intent["expected_candidate_count"] != 0
                    or active.intent["expected_decision_count"] != 0
                )
            )
            or (
                current_head is not None
                and (
                    current_head["last_candidate"]
                    != active.intent["expected_last_candidate"]
                    or current_head["candidate_count"]
                    != active.intent["expected_candidate_count"]
                    or current_head["candidate_index"]
                    != active.intent["expected_candidate_index"]
                    or current_head["last_decision"]
                    != active.intent["expected_last_decision"]
                    or current_head["decision_count"]
                    != active.intent["expected_decision_count"]
                    or current_head["last_handoff_queue"]
                    != active.intent["expected_last_handoff_queue"]
                )
            )
        ):
            _fail("selector plan parent changed before intent publication")
        with _w1a_commit_fence(
            private_root, active, plan_evidence_inputs
        ):
            _publish_advance_intent(private_root, active.intent)
        if hook is not None:
            hook("after_intent")

    current_head = _load_head(private_root)
    if current_head is not None and current_head["head_id"] == active.head["head_id"]:
        # Crash-after-HEAD recovery is adoption, not another publication.  Prove
        # every immutable byte and the complete authenticated graph, then clear
        # only the durable intent.  No object or HEAD write is permitted here.
        for item in active.objects:
            body = _read_private_file(
                _object_path(private_root, item.key),
                root=private_root,
                limit=MAX_OBJECT_BYTES,
                required=True,
            )
            if body != item.body:
                _fail("selector adopted intent object differs from durable bytes")
        authenticated, _decisions, _body = authenticate_store(
            private_root,
            evidence_inputs=evidence_inputs or active.evidence_inputs,
        )
        if authenticated != active.head:
            _fail("selector adopted intent HEAD does not authenticate exactly")
        _clear_advance_intent(private_root, active.intent)
        return active.head

    touched_parents: set[Path] = set()
    for item in active.objects:
        object_path = _object_path(private_root, item.key)
        _write_immutable(
            object_path,
            item.body,
            root=private_root,
            sync_parent=False,
        )
        touched_parents.add(object_path.parent)
    for parent in sorted(touched_parents, key=str):
        _sync_immutable_parent(parent / ".durability-probe", root=private_root)
    if hook is not None:
        hook("after_objects")
        hook("after_handoff_queue")
    if hook is not None:
        hook("after_ledger")

    current_head = _load_head(private_root)
    current_id = current_head["head_id"] if current_head is not None else None
    if current_id == active.expected_head_id:
        _atomic_write(
            private_root / HEAD_FILE,
            canonical_bytes(active.head),
            root=private_root,
            limit=MAX_HEAD_BYTES,
        )
    elif current_id == active.head["head_id"]:
        _reprove_exact_private_file(
            private_root / HEAD_FILE,
            canonical_bytes(active.head),
            root=private_root,
            limit=MAX_HEAD_BYTES,
            label="selector HEAD",
        )
    else:
        _fail("selector live HEAD is neither intent parent nor candidate")
    if hook is not None:
        hook("after_head")

    authenticated_state = _authenticate_selector_state(private_root)
    if authenticated_state is None or authenticated_state[0] != active.head:
        _fail("selector transition did not authenticate after publication")
    _clear_advance_intent(private_root, active.intent)
    return active.head


def _commit_cycle_internal(
    root: Path,
    plan: CyclePlan | None,
    *,
    evidence_inputs: EvidenceInputs | None = None,
    hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Commit or recover one intent with an exclusively locked exact transition."""

    if SELECTOR_RUNTIME_ARMED is not True:
        raise SparseSelectorUnarmed(
            "sparse selector runtime is code-unarmed pending M1 deployment receipts"
        )

    private_root = validate_private_root(root, create=True)
    with _store_lock(private_root):
        return _commit_cycle_locked(
            private_root,
            plan,
            evidence_inputs=evidence_inputs,
            hook=hook,
        )


def plan_cycle(
    *,
    root: Path,
    source: SourceSnapshot,
    evidence_inputs: EvidenceInputs,
    scheduled_at: str,
    clock: Callable[[], datetime],
) -> NoReturn:
    """Public planning is inert until the reviewed code constant is armed."""

    del root, source, evidence_inputs, scheduled_at, clock
    raise SparseSelectorUnarmed(
        "sparse selector runtime is code-unarmed pending M1 deployment receipts"
    )


def commit_cycle(
    root: Path,
    plan: CyclePlan | None,
    *,
    evidence_inputs: EvidenceInputs | None = None,
    hook: Callable[[str], None] | None = None,
) -> NoReturn:
    """Public writes are inert; advance owns the only production commit path."""

    del root, plan, evidence_inputs, hook
    raise SparseSelectorUnarmed(
        "sparse selector runtime is code-unarmed pending M1 deployment receipts"
    )


def advance(
    *,
    private_root: Path,
    source: SourceSnapshot,
    evidence_inputs: EvidenceInputs,
    scheduled_at: str,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Advance one production cycle only when the code-only registry is armed."""

    if SELECTOR_RUNTIME_ARMED is not True:
        raise SparseSelectorUnarmed(
            "sparse selector runtime is code-unarmed pending M1 deployment receipts"
        )
    root = validate_private_root(private_root, create=True)
    with _store_lock(root):
        if _read_intent(root) is not None:
            return _commit_cycle_locked(
                root,
                None,
                evidence_inputs=evidence_inputs,
                hook=hook,
            )
        state = _authenticate_selector_state(root)
        if state is not None:
            current_head, _pending, current_cycle, _candidate, _decision = state
            if current_cycle is not None:
                requested_slot = _utc(scheduled_at, label="selector scheduled clock")
                current_slot = _utc(
                    current_cycle["scheduled_at"], label="current selector scheduled clock"
                )
                if requested_slot == current_slot:
                    # A retry/racing runner adopts the one locked publication for
                    # this exact slot. It cannot create another cycle or orphan.
                    return current_head
                if requested_slot < current_slot:
                    _fail("selector scheduled slot precedes its current HEAD")
        plan = _plan_cycle_internal(
            root=root,
            source=source,
            evidence_inputs=evidence_inputs,
            scheduled_at=scheduled_at,
            clock=clock,
            runtime_armed=True,
        )
        return _commit_cycle_locked(
            root,
            plan,
            evidence_inputs=evidence_inputs,
            hook=hook,
            trusted_internal_plan=True,
        )


def status(private_root: Path) -> dict[str, Any]:
    root = _absolute_private_path(private_root)
    if not root.exists():
        return {
            "runtime_armed": SELECTOR_RUNTIME_ARMED,
            "initialized": False,
            "head": None,
            "recovery_intent": False,
        }
    root = validate_private_root(root, create=False)
    with _store_lock(root):
        intent = _read_intent(root)
        if intent is not None:
            plan = _plan_from_intent(root, intent)
            return {
                "runtime_armed": SELECTOR_RUNTIME_ARMED,
                "initialized": True,
                "head": _load_head(root),
                "recovery_intent": True,
                "intent_next_head_id": plan.head["head_id"],
            }
        state = _authenticate_selector_state(root)
        head = None if state is None else state[0]
        return {
            "runtime_armed": SELECTOR_RUNTIME_ARMED,
            "initialized": head is not None,
            "head": head,
            "recovery_intent": False,
        }


__all__ = [
    "ABSTENTION_REASON_CODES",
    "BENCHMARK_DIGEST",
    "CANDIDATE_MANIFEST_RULE_SHA256",
    "DECISION_RULE_SHA256",
    "DIGESTS",
    "EVIDENCE_RULE_SHA256",
    "FALSE_AUTHORITY",
    "HANDOFF_QUEUE_NAMESPACE",
    "LIFECYCLE_RULE_SHA256",
    "RULE_ID",
    "SELECTOR_RULE_SHA256",
    "SELECTOR_RUNTIME_ARMED",
    "SOURCE_CAMPAIGN_RULE_SHA256",
    "EvidenceInputs",
    "SourceSnapshot",
    "SparseSelectorError",
    "SparseSelectorUnarmed",
    "advance",
    "authenticate_handoff_head",
    "authenticate_store",
    "authenticated_pending_handoff_queue",
    "canonical_bytes",
    "commit_cycle",
    "plan_cycle",
    "read_next_handoff_queue_item",
    "status",
    "utc_text",
    "validate_runtime_object",
    "validate_source_snapshot",
]
