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
import base64
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
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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
FROZEN_LIFECYCLE_SCHEMA_PATH = (
    ROOT / "contracts/options/prophet.option_shadow_lifecycle_event.v1.schema.json"
)
FROZEN_MARK_SCHEMA_PATH = (
    ROOT / "contracts/options/prophet.option_mark_observation.v1.schema.json"
)
FROZEN_LIFECYCLE_BUILDER_PATH = (
    ROOT / "scripts/build_prophet_option_shadow_lifecycle.py"
)
FROZEN_MARK_BUILDER_PATH = ROOT / "scripts/build_prophet_marks.py"

PRODUCER_CONTRACT: dict[str, Any] = {
    "schema": "options.sparse_selector_evidence_producer_contract/v1",
    "lifecycle_builder": {
        "path": "scripts/build_prophet_option_shadow_lifecycle.py",
        "bytes": 86_565,
        "sha256": "a5710b6ba5aedcd605541794aa7343c6f10d9af834848a95b2f8eb46b024c281",
    },
    "lifecycle_event_schema": {
        "path": "contracts/options/prophet.option_shadow_lifecycle_event.v1.schema.json",
        "bytes": 14_919,
        "sha256": "047721a1a86d7ef920a2c9a5fd035ab95f2e407453b33842dbfc6ca54e433a8f",
    },
    "mark_builder": {
        "path": "scripts/build_prophet_marks.py",
        "bytes": 54_446,
        "sha256": "04eb6636303c223ce88a22c8f224612f33ba6d97f95095fdd09a2c2851896de6",
    },
    "mark_schema": {
        "path": "contracts/options/prophet.option_mark_observation.v1.schema.json",
        "bytes": 13_088,
        "sha256": "22e9a2fc6d0b4d9de5788d54b8f4413e8c96c081fd18a53596c1ce3243605f7c",
    },
    "ledger": {
        "schema": "prophet.canonical_ledger_snapshot_receipt/v1",
        "source_repository": lifecycle.CANONICAL_LEDGER_REPOSITORY,
        "source_ref": lifecycle.CANONICAL_LEDGER_REF,
        "source_path": lifecycle.CANONICAL_LEDGER_SOURCE_PATH,
        "cursor_fields": [
            "schema",
            "source_repository",
            "source_ref",
            "source_commit",
            "source_path",
            "bytes",
            "sha256",
            "row_count",
        ],
    },
}

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
EVIDENCE_AUDIT_NAMESPACE = "evidence_audit"
EVIDENCE_EVENT_SEEN_DOMAIN = "selector.evidence_event_seen/v1"
EVIDENCE_EVENT_ENROLLMENT_DOMAIN = "selector.evidence_event_enrollments/v1"
EVIDENCE_EVENT_TERMINAL_DOMAIN = "selector.evidence_event_terminals/v1"
EVIDENCE_STATE_ENROLLMENT_DOMAIN = "selector.evidence_state_enrollments/v1"
EVIDENCE_STATE_TERMINAL_DOMAIN = "selector.evidence_state_terminals/v1"
EVIDENCE_MARK_SEEN_DOMAIN = "selector.evidence_mark_seen/v1"
EVIDENCE_STATE_LATEST_DOMAIN = "selector.evidence_state_latest/v1"
EVIDENCE_DERIVED_LATEST_DOMAIN = "selector.evidence_derived_latest/v1"
EVIDENCE_LEDGER_ROW_DOMAIN = "selector.evidence_ledger_rows/v1"
EVIDENCE_LEDGER_TERMINAL_DOMAIN = "selector.evidence_ledger_terminals/v1"
EVIDENCE_BOUNDARY_DOMAIN = "selector.evidence_lifecycle_boundaries/v1"
OCCURRENCE_STAGES = (
    "LEDGER_CAPTURE",
    "LIVE_MARK_BACKWALK",
    "COLD_ACTIVATION",
    "LEDGER_ROWS",
    "EDGE_INIT",
    "EDGE_MARK_BACKWALK",
    "EDGE_MARK_ROWS",
    "EDGE_TERMINALS",
    "EDGE_FINALIZE",
    "DONE",
)
HEAD_FILE = "HEAD.json"
INTENT_FILE = "ADVANCE_INTENT.json"
INTENT_ATTEMPT_FILE = "ADVANCE_INTENT.attempt.json"
INTENT_PREPARE_FILE = ".ADVANCE_INTENT.json.prepare"
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
MAX_INTENT_BYTES = MAX_SOURCE_INTENT_BYTES
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
# A selector settlement may inspect only one manifested prefix.  The producer
# chains remain fully authenticated, but contract/session material retained by
# the selector is limited to the exact candidates being settled.  These caps
# are input/read budgets, not eligibility or lifetime limits.
MAX_EVIDENCE_SOURCE_READS = 2_048
MAX_EVIDENCE_SOURCE_BYTES = 32 * 1024 * 1024
EVIDENCE_LEDGER_CHUNK_BYTES = 512 * 1024
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
        "options.sparse_selector_evidence_source_snapshot/v1",
        "options.sparse_selector_evidence_high_water/v1",
        "options.sparse_selector_evidence_replay_state/v1",
        "options.sparse_selector_evidence_ledger_chunk/v1",
        "options.sparse_selector_konseki_evidence/v1",
        "options.sparse_selector_mark_evidence/v1",
        "options.sparse_selector_lifecycle_evidence/v1",
    }
)

_SHA256_RE = re.compile(r"[a-f0-9]{64}\Z")
_COMMIT_RE = re.compile(r"[a-f0-9]{40,64}\Z")
_CAMPAIGN_ID_RE = re.compile(r"ocam_[a-f0-9]{24}\Z")
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
_RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z"
)
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


_PRODUCER_FORMAT_CHECKER = FormatChecker()


@_PRODUCER_FORMAT_CHECKER.checks("date-time", raises=(TypeError, ValueError))
def _is_producer_rfc3339_datetime(value: object) -> bool:
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        return False
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


@_PRODUCER_FORMAT_CHECKER.checks("date", raises=(TypeError, ValueError))
def _is_producer_rfc3339_date(value: object) -> bool:
    return _is_rfc3339_date(value)


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


def _source_rfc3339(value: object, *, label: str) -> datetime:
    """Parse one producer timestamp without rewriting its authenticated bytes."""

    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        _fail(f"{label} must be RFC3339 with an explicit offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SparseSelectorError(
            f"{label} must be RFC3339 with an explicit offset"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(f"{label} must be RFC3339 with an explicit offset")
    return parsed.astimezone(timezone.utc)


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


def _frozen_producer_validator(
    path: Path, receipt: Mapping[str, Any], *, label: str
) -> Draft202012Validator:
    body = path.read_bytes()
    if len(body) != receipt["bytes"] or _sha256(body) != receipt["sha256"]:
        _fail(f"selector frozen {label} receipt drifted")
    schema = strict_json(body, label=f"selector frozen {label}")
    if not isinstance(schema, Mapping):
        _fail(f"selector frozen {label} is not an object")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=_PRODUCER_FORMAT_CHECKER)


def _verify_frozen_producer_contract() -> None:
    for path, field in (
        (FROZEN_LIFECYCLE_BUILDER_PATH, "lifecycle_builder"),
        (FROZEN_MARK_BUILDER_PATH, "mark_builder"),
    ):
        body = path.read_bytes()
        receipt = PRODUCER_CONTRACT[field]
        if len(body) != receipt["bytes"] or _sha256(body) != receipt["sha256"]:
            _fail(f"selector frozen {field.replace('_', ' ')} receipt drifted")


def _validate_frozen_lifecycle_event(value: Mapping[str, Any]) -> dict[str, Any]:
    clean = copy.deepcopy(dict(value))
    errors = sorted(
        _FROZEN_LIFECYCLE_EVENT_VALIDATOR.iter_errors(clean),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        where = ".".join(str(part) for part in errors[0].absolute_path) or "<root>"
        _fail(
            "selector frozen lifecycle event schema validation failed at "
            f"{where}: {errors[0].message}"
        )
    try:
        pointer = lifecycle._event_pointer(clean)
    except (TypeError, ValueError, KeyError) as exc:
        raise SparseSelectorError(
            "selector frozen lifecycle event identity drifted"
        ) from exc
    if pointer["event_id"] != clean.get("event_id"):
        _fail("selector frozen lifecycle event identity drifted")
    return clean


def _validate_frozen_mark_observation(
    value: Mapping[str, Any], pointer: Mapping[str, Any]
) -> dict[str, Any]:
    clean = copy.deepcopy(dict(value))
    errors = sorted(
        _FROZEN_MARK_OBSERVATION_VALIDATOR.iter_errors(clean),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        where = ".".join(str(part) for part in errors[0].absolute_path) or "<root>"
        _fail(
            "selector frozen mark observation schema validation failed at "
            f"{where}: {errors[0].message}"
        )
    try:
        expected = mark_chain._observation_pointer(clean)
        checked = mark_chain._validate_pointer(pointer)
    except (TypeError, ValueError, KeyError) as exc:
        raise SparseSelectorError(
            "selector frozen mark observation identity drifted"
        ) from exc
    if expected != checked:
        _fail("selector frozen mark observation pointer drifted")
    return clean


_RUNTIME_SCHEMA = _runtime_schema()
_SCHEMA_VALIDATOR = _validator(_RUNTIME_SCHEMA)
_FROZEN_LIFECYCLE_EVENT_VALIDATOR = _frozen_producer_validator(
    FROZEN_LIFECYCLE_SCHEMA_PATH,
    PRODUCER_CONTRACT["lifecycle_event_schema"],
    label="lifecycle event schema",
)
_FROZEN_MARK_OBSERVATION_VALIDATOR = _frozen_producer_validator(
    FROZEN_MARK_SCHEMA_PATH,
    PRODUCER_CONTRACT["mark_schema"],
    label="mark observation schema",
)
_verify_frozen_producer_contract()
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
        elif schema == "options.sparse_selector_evidence_source_snapshot/v1":
            state = lifecycle._validate_state_shape(clean["lifecycle_state"])
            activation_boundary = lifecycle._validate_activation_boundary(
                clean["activation_boundary"]
            )
            mark_chain._validate_pointer(clean["live_mark_head"])
            lifecycle._validate_ledger_receipt(clean["live_ledger_receipt"])
            if (
                clean["snapshot_id"]
                != _content_id("osess_", clean, field="snapshot_id")
                or clean["state_sha256"] != _sha256(canonical_bytes(state))
                or clean["producer_contract"] != PRODUCER_CONTRACT
                or set(clean["producer_roots"]) != {"mark", "lifecycle"}
                or int(activation_boundary["ledger_boundary"]["bytes"])
                > int(state["ledger_cursor"]["bytes"])
                or len(canonical_bytes(clean)) > MAX_SOURCE_INTENT_BYTES
            ):
                _fail(f"{label} evidence source snapshot binding drifted")
        elif schema == "options.sparse_selector_evidence_replay_state/v1":
            state = lifecycle._validate_state_shape(clean["state"])
            if (
                clean["replay_id"]
                != _content_id("osers_", clean, field="replay_id")
                or clean["producer_contract"] != PRODUCER_CONTRACT
                or clean["state_id"] != state["state_id"]
                or len(canonical_bytes(clean)) > MAX_SOURCE_INTENT_BYTES
            ):
                _fail(f"{label} evidence replay state binding drifted")
        elif schema == "options.sparse_selector_evidence_ledger_chunk/v1":
            try:
                raw = base64.b64decode(clean["body_base64"], validate=True)
            except (ValueError, TypeError) as exc:
                raise SparseSelectorError(
                    f"{label} evidence ledger chunk encoding drifted"
                ) from exc
            if (
                clean["ledger_chunk_id"]
                != _content_id("oselc_", clean, field="ledger_chunk_id")
                or clean["producer_contract"] != PRODUCER_CONTRACT
                or clean["last_byte"] - clean["first_byte"] != len(raw)
                or not 0 < len(raw) <= EVIDENCE_LEDGER_CHUNK_BYTES
                or clean["body_sha256"] != _sha256(raw)
            ):
                _fail(f"{label} evidence ledger chunk binding drifted")
        elif schema == "options.sparse_selector_evidence_high_water/v1":
            roots = {
                "event_seen_index": EVIDENCE_EVENT_SEEN_DOMAIN,
                "event_enrollment_index": EVIDENCE_EVENT_ENROLLMENT_DOMAIN,
                "event_terminal_index": EVIDENCE_EVENT_TERMINAL_DOMAIN,
                "state_enrollment_index": EVIDENCE_STATE_ENROLLMENT_DOMAIN,
                "state_terminal_index": EVIDENCE_STATE_TERMINAL_DOMAIN,
                "mark_seen_index": EVIDENCE_MARK_SEEN_DOMAIN,
                "state_latest_index": EVIDENCE_STATE_LATEST_DOMAIN,
                "derived_latest_index": EVIDENCE_DERIVED_LATEST_DOMAIN,
                "ledger_row_index": EVIDENCE_LEDGER_ROW_DOMAIN,
                "ledger_terminal_index": EVIDENCE_LEDGER_TERMINAL_DOMAIN,
                "boundary_index": EVIDENCE_BOUNDARY_DOMAIN,
            }
            for field, domain in roots.items():
                private_auth_dict.validate_sharded_root(clean[field], domain=domain)
            legacy_roots = (
                "event_seen_index",
                "event_terminal_index",
                "state_enrollment_index",
                "state_terminal_index",
                "state_latest_index",
                "derived_latest_index",
                "ledger_terminal_index",
            )
            if (
                clean["high_water_id"]
                != _content_id("osehw_", clean, field="high_water_id")
                or clean["source_state_id"] == ""
                or clean["producer_contract"] != PRODUCER_CONTRACT
                or (clean["replay_state"] is None)
                != (clean["replay_state_id"] is None)
                or (clean["replay_state"] is None)
                != (clean["replay_lifecycle_head"] is None)
                or (clean["replay_state"] is None)
                != (clean["replay_mark_cursor"] is None)
                or (clean["replay_state"] is None)
                != (clean["replay_ledger_cursor"] is None)
                or (clean["base_state_id"] is None)
                != (clean["base_lifecycle_head"] is None)
                or (clean["base_state_id"] is None)
                != (clean["base_mark_cursor"] is None)
                or (clean["base_state_id"] is None)
                != (clean["base_ledger_cursor"] is None)
                or clean["occurrence_stage"] not in OCCURRENCE_STAGES
                or clean["ledger_capture_bytes"]
                > clean["captured_ledger_receipt"].get("bytes", -1)
                or clean["ledger_replay_bytes"]
                > clean["ledger_cursor"].get("bytes", -1)
                or clean["ledger_replay_rows"]
                > clean["ledger_cursor"].get("row_count", -1)
                or clean["ledger_cursor_bytes"] != 0
                or clean["ledger_row_count"] != clean["ledger_replay_rows"]
                or clean["event_cursor"] is not None
                or clean["event_count"] != 0
                or clean["state_enrollment_cursor"] != 0
                or clean["state_terminal_cursor"] != 0
                or clean["state_latest_cursor"] != 0
                or clean["mark_scan_cursor"] is not None
                or clean["mark_row_cursor"] != 0
                or clean["mark_count"] != 0
                or clean["derived_latest_active_count"] != 0
                or clean["ledger_terminal_match_count"] != 0
                or any(clean[field]["entry_count"] for field in legacy_roots)
                or (
                    clean["phase"] == "AUDIT_PINNED"
                    and (
                        clean["live_mark_scan_cursor"]
                        != clean["captured_mark_head"]
                        or clean["live_mark_reverse_ordinal"] != 0
                        or clean["base_state_id"] is not None
                        or clean["base_lifecycle_head"] is not None
                        or clean["base_mark_cursor"] is not None
                        or clean["base_ledger_cursor"] is not None
                        or clean["occurrence_stage"] != "LEDGER_CAPTURE"
                        or clean["current_boundary"] is not None
                        or clean["boundary_mark_cursor"] is not None
                        or clean["boundary_mark_row_cursor"] != 0
                        or clean["boundary_mark_ordinal"] != 0
                        or clean["boundary_ledger_row_cursor"] != 0
                        or clean["boundary_ledger_byte_cursor"] != 0
                        or clean["boundary_event_cursor"] != 0
                        or clean["boundary_terminal_cursor"] != 0
                        or clean["event_enrollment_index"]["entry_count"] != 0
                        or clean["mark_seen_index"]["entry_count"] != 0
                        or (
                            clean["previous_complete"] is None
                            and (
                                clean["ledger_capture_bytes"] != 0
                                or clean["ledger_replay_bytes"] != 0
                                or clean["ledger_replay_rows"] != 0
                                or clean["replay_state"] is not None
                                or clean["boundary_index"]["entry_count"] != 0
                                or clean["ledger_chunks"]
                                or clean["ledger_row_index"]["entry_count"] != 0
                            )
                        )
                        or (
                            clean["previous_complete"] is not None
                            and clean["replay_state"] is None
                        )
                    )
                )
            ):
                _fail(f"{label} evidence high-water binding drifted")
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

    @property
    def receipt(self) -> dict[str, Any]:
        pointer = self.pointer
        return {
            "id": pointer["id"],
            "key": self.key,
            "sha256": pointer["sha256"],
            "bytes": pointer["bytes"],
        }


@dataclass(frozen=True)
class CyclePlan:
    expected_head_id: str | None
    objects: tuple[PlannedObject, ...]
    head: dict[str, Any]
    intent: dict[str, Any]
    evidence_inputs: EvidenceInputs = EvidenceInputs()


def _transition_footprint_bytes(
    intent: Mapping[str, Any], objects: Sequence[PlannedObject]
) -> int:
    """Conservative authority-record plus every immutable transition body."""

    return (
        len(canonical_bytes(intent))
        + len(_intent_seal_body(intent))
        + sum(len(item.body) for item in objects)
    )


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
        "snapshot_id",
        "high_water_id",
        "replay_id",
        "ledger_chunk_id",
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
        expected_end = prior_end + len(canonical_bytes(item["row"])) + 1
        if (
            item["ordinal"] != expected_row
            or type(item["end_byte"]) is not int
            or item["end_byte"] != expected_end
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


@dataclass(frozen=True)
class _AnchoredEvidenceSources:
    mark: _SelectorLane
    lifecycle: _SelectorLane
    mark_lock_fd: int
    lifecycle_lock_fd: int
    producer_roots: Mapping[str, Mapping[str, str]]
    root_bindings: Mapping[str, Mapping[str, str]]
    authority: "_EvidenceAuthorityBoundary"


@dataclass
class _EvidenceAuthorityBoundary:
    granted: bool = False


@dataclass
class _StagedWrite:
    parent_fd: int
    parent_identity: tuple[int, int]
    temporary_name: str
    target_name: str
    closed: bool = False


@dataclass
class _ImmutableBatchParent:
    path: Path
    descriptor: int
    identity: tuple[int, int]
    closed: bool = False


_ACTIVE_SELECTOR_LANE: ContextVar[_SelectorLane | None] = ContextVar(
    "options_sparse_selector_lane", default=None
)
_ACTIVE_EVIDENCE_SOURCES: ContextVar[_AnchoredEvidenceSources | None] = ContextVar(
    "options_sparse_selector_evidence_sources", default=None
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
def _open_selector_lane(
    root: Path,
    *,
    create: bool,
    skip_final_identity_check: Callable[[], bool] | None = None,
) -> Iterator[_SelectorLane]:
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
        if skip_final_identity_check is None or not skip_final_identity_check():
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


def _lane_path_receipt(lane: _SelectorLane) -> dict[str, str]:
    """Persist only the normalized producer path under the local trust model."""

    return {"path_sha256": _sha256(os.fsencode(str(lane.root)))}


def _lane_binding_identity(lane: _SelectorLane) -> dict[str, str]:
    """Transaction-local root/ancestor identity used only for anti-ABA fencing."""

    ancestry = [
        {
            "component": name,
            "device": str(device),
            "inode": str(inode),
        }
        for _parent_fd, name, device, inode in lane.bindings
    ]
    root_metadata = os.fstat(lane.root_fd)
    return {
        "path_sha256": _sha256(os.fsencode(str(lane.root))),
        "binding_sha256": _sha256(canonical_bytes(ancestry)),
        "device": str(root_metadata.st_dev),
        "inode": str(root_metadata.st_ino),
    }


def _require_disjoint_evidence_lanes(*lanes: _SelectorLane) -> None:
    for index, left in enumerate(lanes):
        left_metadata = os.fstat(left.root_fd)
        for right in lanes[index + 1 :]:
            right_metadata = os.fstat(right.root_fd)
            if (
                left.root == right.root
                or left.root in right.root.parents
                or right.root in left.root.parents
                or (left_metadata.st_dev, left_metadata.st_ino)
                == (right_metadata.st_dev, right_metadata.st_ino)
            ):
                _fail("selector and producer roots must be distinct and non-nested")


def _assert_evidence_lock_identity(lane: _SelectorLane, descriptor: int) -> None:
    _assert_lane_identity(lane)
    opened = os.fstat(descriptor)
    try:
        bound = os.stat(
            ".ledger.lock", dir_fd=lane.root_fd, follow_symlinks=False
        )
    except FileNotFoundError as exc:
        raise SparseSelectorError("selector producer lock was renamed") from exc
    for metadata in (opened, bound):
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _fail("selector producer lock metadata is unsafe")
    if (opened.st_dev, opened.st_ino) != (bound.st_dev, bound.st_ino):
        _fail("selector producer lock path no longer names the locked inode")


@contextmanager
def _anchored_evidence_lock(
    lane: _SelectorLane, authority: _EvidenceAuthorityBoundary
) -> Iterator[int]:
    try:
        descriptor = os.open(
            ".ledger.lock",
            os.O_RDWR
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=lane.root_fd,
        )
    except OSError as exc:
        raise SparseSelectorError(
            "selector existing producer lock cannot be opened safely"
        ) from exc
    locked = False
    try:
        _assert_evidence_lock_identity(lane, descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        _assert_evidence_lock_identity(lane, descriptor)
        yield descriptor
        if not authority.granted:
            _assert_evidence_lock_identity(lane, descriptor)
    finally:
        try:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


@contextmanager
def _anchored_evidence_sources(
    mark_root: Path,
    lifecycle_root: Path,
    *,
    selector_lane: _SelectorLane | None = None,
) -> Iterator[_AnchoredEvidenceSources]:
    """Open and lock both existing producer roots without following paths again."""

    mark_root = _absolute_private_path(mark_root)
    lifecycle_root = _absolute_private_path(lifecycle_root)
    authority = _EvidenceAuthorityBoundary()
    with _open_selector_lane(
        mark_root,
        create=False,
        skip_final_identity_check=lambda: authority.granted,
    ) as mark_lane:
        with _open_selector_lane(
            lifecycle_root,
            create=False,
            skip_final_identity_check=lambda: authority.granted,
        ) as lifecycle_lane:
            _require_disjoint_evidence_lanes(
                *(
                    (mark_lane, lifecycle_lane)
                    if selector_lane is None
                    else (selector_lane, mark_lane, lifecycle_lane)
                )
            )
            receipts = {
                "mark": _lane_path_receipt(mark_lane),
                "lifecycle": _lane_path_receipt(lifecycle_lane),
            }
            bindings = {
                "mark": _lane_binding_identity(mark_lane),
                "lifecycle": _lane_binding_identity(lifecycle_lane),
            }
            with _anchored_evidence_lock(mark_lane, authority) as mark_lock_fd:
                with _anchored_evidence_lock(
                    lifecycle_lane, authority
                ) as lifecycle_lock_fd:
                    _assert_lane_identity(mark_lane)
                    _assert_lane_identity(lifecycle_lane)
                    yield _AnchoredEvidenceSources(
                        mark=mark_lane,
                        lifecycle=lifecycle_lane,
                        mark_lock_fd=mark_lock_fd,
                        lifecycle_lock_fd=lifecycle_lock_fd,
                        producer_roots=receipts,
                        root_bindings=bindings,
                        authority=authority,
                    )
                    if not authority.granted:
                        _assert_lane_identity(mark_lane)
                        _assert_lane_identity(lifecycle_lane)


@contextmanager
def _open_anchored_parent(
    lane: _SelectorLane, key: str
) -> Iterator[tuple[int, str]]:
    parts = key.split("/")
    if (
        not parts
        or any(part in {"", ".", ".."} or "\\" in part for part in parts)
        or any("/" in part for part in parts)
    ):
        _fail("selector producer object key is unsafe")
    descriptors: list[int] = []
    current = os.dup(lane.root_fd)
    descriptors.append(current)
    bindings: list[tuple[int, str, int, int]] = []
    try:
        for index, part in enumerate(parts[:-1]):
            child = _open_directory_component(
                current,
                part,
                create=False,
                private=True,
                label=f"{lane.root.name}:{'/'.join(parts[: index + 1])}",
            )
            metadata = os.fstat(child)
            bindings.append((current, part, metadata.st_dev, metadata.st_ino))
            descriptors.append(child)
            current = child
        yield current, parts[-1]
        _assert_lane_identity(lane)
        for parent_fd, name, device, inode in bindings:
            rebound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(rebound.st_mode) or (rebound.st_dev, rebound.st_ino) != (
                device,
                inode,
            ):
                _fail("selector producer object directory was rebound")
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_anchored_file(
    lane: _SelectorLane,
    key: str,
    *,
    limit: int,
    required: bool = True,
    label: str,
) -> bytes | None:
    try:
        with _open_anchored_parent(lane, key) as (parent_fd, name):
            body = _read_regular_at(
                parent_fd,
                name,
                limit=limit,
                required=required,
                label=label,
            )
            if required and not body:
                _fail(f"{label} is empty")
            return body
    except _PrivateDirectoryMissing:
        if required:
            _fail(f"{label} is missing")
        return None


def _stat_anchored_file(
    lane: _SelectorLane, key: str, *, limit: int, label: str
) -> os.stat_result:
    with _open_anchored_parent(lane, key) as (parent_fd, name):
        try:
            checked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise SparseSelectorError(f"{label} cannot be opened safely") from exc
        try:
            opened = os.fstat(descriptor)
            rebound = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            for metadata in (checked, opened, rebound):
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                    or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                    or metadata.st_size > limit
                ):
                    _fail(f"{label} metadata is unsafe")
            if any(
                (metadata.st_dev, metadata.st_ino)
                != (opened.st_dev, opened.st_ino)
                for metadata in (checked, rebound)
            ):
                _fail(f"{label} changed during secure open")
            return opened
        finally:
            os.close(descriptor)


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
    path: Path,
    body: bytes,
    *,
    root: Path,
    limit: int,
    temporary_name: str | None = None,
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
        temporary_name = temporary_name or f".{name}.{os.getpid()}.{uuid4().hex}.tmp"
        if "/" in temporary_name or temporary_name in {"", ".", ".."}:
            _fail("selector atomic temporary name is unsafe")
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        try:
            os.fchmod(descriptor, 0o600)
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


def _recover_prestage_temp(
    parent_fd: int, name: str, *, sync_parent: bool = True
) -> bool:
    """Remove the one reserved non-authoritative temp after proving its inode."""

    temporary_name = f".{name}.prestage"
    try:
        temporary = os.stat(
            temporary_name, dir_fd=parent_fd, follow_symlinks=False
        )
    except FileNotFoundError:
        return False
    if (
        stat.S_ISLNK(temporary.st_mode)
        or not stat.S_ISREG(temporary.st_mode)
        or temporary.st_uid != os.getuid()
        or stat.S_IMODE(temporary.st_mode) != 0o600
    ):
        _fail("selector prestage temporary metadata is unsafe")
    try:
        installed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        installed = None
    if installed is not None and (
        stat.S_ISLNK(installed.st_mode)
        or not stat.S_ISREG(installed.st_mode)
        or installed.st_uid != os.getuid()
        or stat.S_IMODE(installed.st_mode) != 0o600
    ):
        _fail("selector prestaged immutable metadata is unsafe")
    if installed is not None and (
        installed.st_dev,
        installed.st_ino,
    ) == (temporary.st_dev, temporary.st_ino):
        if installed.st_nlink != 2 or temporary.st_nlink != 2:
            _fail("selector prestage linked inode has an unknown alias")
    elif temporary.st_nlink != 1:
        _fail("selector prestage temporary has an unknown alias")
    os.unlink(temporary_name, dir_fd=parent_fd)
    if sync_parent:
        os.fsync(parent_fd)
    return True


def _prestage_immutable(path: Path, body: bytes, *, root: Path) -> None:
    """Install complete orphan-safe bytes without ever exposing a partial final.

    A staged object is not authority until a parent-bound intent and HEAD name
    it.  The temporary file is fully written, file-fsynced, and read back before
    a no-replace hard link can make the content-addressed final path visible.
    A crash can therefore leave only an ignorable temporary orphan or a complete
    exact final object; a retry adopts and directory-fsyncs the latter.
    """

    if not body or len(body) > MAX_OBJECT_BYTES:
        _fail("selector prestaged immutable object exceeds its bound")
    with _open_private_parent(root, path, create=True) as (lane, parent_fd, name):
        _recover_prestage_temp(parent_fd, name)
        existing = _read_regular_at(
            parent_fd,
            name,
            limit=MAX_OBJECT_BYTES,
            required=False,
            label="selector prestaged immutable object",
        )
        if existing is not None:
            if existing != body:
                _fail("selector immutable object conflicts with existing bytes")
            os.fsync(parent_fd)
            _assert_lane_identity(lane)
            return

        temporary_name = f".{name}.prestage"
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        try:
            os.fchmod(descriptor, 0o600)
            _write_all(descriptor, body)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            staged = _read_regular_at(
                parent_fd,
                temporary_name,
                limit=MAX_OBJECT_BYTES,
                required=True,
                label="selector prestaged temporary object",
            )
            if staged != body:
                _fail("selector prestaged immutable object readback mismatch")
            try:
                os.link(
                    temporary_name,
                    name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                installed = _read_regular_at(
                    parent_fd,
                    name,
                    limit=MAX_OBJECT_BYTES,
                    required=True,
                    label="selector prestaged immutable object",
                )
                if installed != body:
                    _fail("selector immutable object conflicts with existing bytes")
            os.fsync(parent_fd)
            os.unlink(temporary_name, dir_fd=parent_fd)
            os.fsync(parent_fd)
            installed = _read_regular_at(
                parent_fd,
                name,
                limit=MAX_OBJECT_BYTES,
                required=True,
                label="selector prestaged immutable object",
            )
            if installed != body:
                _fail("selector prestaged immutable object install drifted")
        finally:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except FileNotFoundError:
                pass
        _assert_lane_identity(lane)


def _sync_immutable_parent(path: Path, *, root: Path) -> None:
    """Durably publish a batch of fsynced immutable files before HEAD."""

    with _open_private_parent(root, path, create=False) as (lane, parent_fd, _name):
        os.fsync(parent_fd)
        _assert_lane_identity(lane)


def _remember_immutable_batch_parent(
    parents: dict[Path, _ImmutableBatchParent],
    *,
    path: Path,
    parent_fd: int,
) -> None:
    parent_path = path.parent
    metadata = os.fstat(parent_fd)
    _validate_directory_metadata(metadata, private=True)
    identity = (metadata.st_dev, metadata.st_ino)
    existing = parents.get(parent_path)
    if existing is not None:
        if existing.closed or existing.identity != identity:
            _fail("selector immutable batch parent identity drifted")
        return
    if any(item.identity == identity for item in parents.values()):
        _fail("selector immutable batch aliases a parent directory")
    descriptor = os.dup(parent_fd)
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino) != identity:
        os.close(descriptor)
        _fail("selector immutable batch parent changed during retention")
    parents[parent_path] = _ImmutableBatchParent(
        path=parent_path,
        descriptor=descriptor,
        identity=identity,
    )


def _close_immutable_batch_parents(
    parents: Mapping[Path, _ImmutableBatchParent],
) -> None:
    for parent in parents.values():
        if not parent.closed:
            os.close(parent.descriptor)
            parent.closed = True


def _fsync_immutable_batch_parents(
    root: Path,
    parents: Mapping[Path, _ImmutableBatchParent],
    *,
    hook: Callable[[str], None] | None,
) -> None:
    if hook is not None:
        hook("before_batch_parent_fsync")
    for path in sorted(parents, key=str):
        parent = parents[path]
        if parent.closed:
            _fail("selector immutable batch parent closed before durability")
        retained = os.fstat(parent.descriptor)
        if (retained.st_dev, retained.st_ino) != parent.identity:
            _fail("selector immutable batch retained parent identity drifted")
        _validate_directory_metadata(retained, private=True)
        with _open_private_directory(root, path, create=False) as (
            lane,
            rebound_fd,
        ):
            rebound = os.fstat(rebound_fd)
            if (rebound.st_dev, rebound.st_ino) != parent.identity:
                _fail("selector immutable batch parent was rebound")
            os.fsync(parent.descriptor)
            durable = os.fstat(parent.descriptor)
            rebound_after = os.fstat(rebound_fd)
            if (
                (durable.st_dev, durable.st_ino) != parent.identity
                or (rebound_after.st_dev, rebound_after.st_ino)
                != parent.identity
            ):
                _fail("selector immutable batch parent drifted during fsync")
            _assert_lane_identity(lane)
    if hook is not None:
        hook("after_batch_parent_fsync")


def _prestage_immutable_batch(
    root: Path,
    objects: Sequence[PlannedObject],
    *,
    hook: Callable[[str], None] | None = None,
) -> dict[Path, tuple[int, int]]:
    """Publish one transition's immutable bodies behind one directory barrier."""

    parents: dict[Path, _ImmutableBatchParent] = {}
    seen: set[Path] = set()
    try:
        for item in objects:
            path = _object_path(root, item.key)
            if path in seen:
                _fail("selector immutable batch repeats an object path")
            seen.add(path)
            body = item.body
            if not body or len(body) > MAX_OBJECT_BYTES:
                _fail("selector prestaged immutable object exceeds its bound")
            with _open_private_parent(root, path, create=True) as (
                lane,
                parent_fd,
                name,
            ):
                _remember_immutable_batch_parent(
                    parents, path=path, parent_fd=parent_fd
                )
                _recover_prestage_temp(parent_fd, name, sync_parent=False)
                existing = _read_regular_at(
                    parent_fd,
                    name,
                    limit=MAX_OBJECT_BYTES,
                    required=False,
                    label="selector prestaged immutable object",
                )
                if existing is not None:
                    if existing != body:
                        _fail(
                            "selector immutable object conflicts with existing bytes"
                        )
                    _assert_lane_identity(lane)
                    continue

                temporary_name = f".{name}.prestage"
                descriptor = os.open(
                    temporary_name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=parent_fd,
                )
                try:
                    os.fchmod(descriptor, 0o600)
                    created = os.fstat(descriptor)
                    if (
                        not stat.S_ISREG(created.st_mode)
                        or created.st_nlink != 1
                        or created.st_uid != os.getuid()
                        or stat.S_IMODE(created.st_mode) != 0o600
                    ):
                        _fail("selector prestaged temporary metadata is unsafe")
                    _write_all(descriptor, body)
                    if hook is not None:
                        hook("before_batch_file_fsync")
                    os.fsync(descriptor)
                    if hook is not None:
                        hook("after_batch_file_fsync")
                    fsynced = os.fstat(descriptor)
                    if (
                        (fsynced.st_dev, fsynced.st_ino)
                        != (created.st_dev, created.st_ino)
                        or fsynced.st_nlink != 1
                        or fsynced.st_size != len(body)
                    ):
                        _fail("selector prestaged temporary changed during fsync")
                finally:
                    os.close(descriptor)
                try:
                    staged = _read_regular_at(
                        parent_fd,
                        temporary_name,
                        limit=MAX_OBJECT_BYTES,
                        required=True,
                        label="selector prestaged temporary object",
                    )
                    if staged != body:
                        _fail(
                            "selector prestaged immutable object readback mismatch"
                        )
                    staged_metadata = os.stat(
                        temporary_name,
                        dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                    linked = False
                    if hook is not None:
                        hook("before_batch_object_link")
                    try:
                        os.link(
                            temporary_name,
                            name,
                            src_dir_fd=parent_fd,
                            dst_dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                        linked = True
                    except FileExistsError:
                        installed = _read_regular_at(
                            parent_fd,
                            name,
                            limit=MAX_OBJECT_BYTES,
                            required=True,
                            label="selector prestaged immutable object",
                        )
                        if installed != body:
                            _fail(
                                "selector immutable object conflicts with existing bytes"
                            )
                    if linked:
                        installed_metadata = os.stat(
                            name, dir_fd=parent_fd, follow_symlinks=False
                        )
                        temporary_metadata = os.stat(
                            temporary_name,
                            dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                        expected_inode = (
                            staged_metadata.st_dev,
                            staged_metadata.st_ino,
                        )
                        if (
                            (installed_metadata.st_dev, installed_metadata.st_ino)
                            != expected_inode
                            or (
                                temporary_metadata.st_dev,
                                temporary_metadata.st_ino,
                            )
                            != expected_inode
                            or installed_metadata.st_nlink != 2
                            or temporary_metadata.st_nlink != 2
                        ):
                            _fail(
                                "selector prestaged immutable link identity drifted"
                            )
                        if hook is not None:
                            hook("after_batch_object_link")
                finally:
                    _recover_prestage_temp(
                        parent_fd, name, sync_parent=False
                    )
                installed = _read_regular_at(
                    parent_fd,
                    name,
                    limit=MAX_OBJECT_BYTES,
                    required=True,
                    label="selector prestaged immutable object",
                )
                if installed != body:
                    _fail("selector prestaged immutable object install drifted")
                _assert_lane_identity(lane)
        _fsync_immutable_batch_parents(root, parents, hook=hook)
        return {path: parent.identity for path, parent in parents.items()}
    finally:
        _close_immutable_batch_parents(parents)


def _reprove_immutable_batch(
    root: Path,
    objects: Sequence[PlannedObject],
    *,
    label: str,
    expected_parent_identities: Mapping[Path, tuple[int, int]] | None = None,
) -> None:
    """Exact metadata/byte reproof without redundant durability syscalls."""

    seen: set[Path] = set()
    object_parents = {
        _object_path(root, item.key).parent for item in objects
    }
    if (
        expected_parent_identities is not None
        and set(expected_parent_identities) != object_parents
    ):
        _fail(f"{label} parent set differs from its durability batch")
    for item in objects:
        path = _object_path(root, item.key)
        if path in seen:
            _fail(f"{label} repeats an immutable object path")
        seen.add(path)
        with _open_private_parent(root, path, create=False) as (
            lane,
            parent_fd,
            name,
        ):
            if expected_parent_identities is not None:
                expected_identity = expected_parent_identities[path.parent]
                parent_metadata = os.fstat(parent_fd)
                if (parent_metadata.st_dev, parent_metadata.st_ino) != (
                    expected_identity
                ):
                    _fail(f"{label} parent was rebound after durability")
            body = _read_regular_at(
                parent_fd,
                name,
                limit=MAX_OBJECT_BYTES,
                required=True,
                label=label,
            )
            if body != item.body:
                _fail(f"{label} differs from durable bytes")
            if expected_parent_identities is not None:
                parent_after = os.fstat(parent_fd)
                if (parent_after.st_dev, parent_after.st_ino) != (
                    expected_parent_identities[path.parent]
                ):
                    _fail(f"{label} parent drifted during reproof")
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
            EVIDENCE_AUDIT_NAMESPACE,
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


_PointerObjectCache = dict[
    str,
    tuple[dict[str, Any], dict[str, Any], bytes],
]


def _full_pointer(
    pointer: Mapping[str, Any], *, label: str
) -> tuple[str, dict[str, Any]]:
    if (
        not isinstance(pointer, Mapping)
        or set(pointer) != {"id", "key", "sha256", "bytes"}
        or not isinstance(pointer.get("id"), str)
    ):
        _fail(f"{label} pointer is malformed")
    return str(pointer["id"]), copy.deepcopy(dict(pointer))


def _load_pointer_cached(
    root: Path,
    pointer: Mapping[str, Any],
    *,
    label: str,
    cache: _PointerObjectCache,
) -> tuple[dict[str, Any], bytes]:
    identity, clean_pointer = _full_pointer(pointer, label=label)
    cached = cache.get(identity)
    if cached is not None:
        cached_pointer, cached_value, cached_body = cached
        if cached_pointer != clean_pointer:
            _fail(f"{label} cached full pointer drifted")
        return cached_value, cached_body
    value = _load_pointer(root, clean_pointer, label=label)
    body = canonical_bytes(value)
    cache[identity] = (clean_pointer, value, body)
    return value, body


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
                "campaign_id": candidate["campaign_id"],
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


def _load_evidence_high_water(
    root: Path, pointer: Mapping[str, Any]
) -> dict[str, Any]:
    value = _load_pointer(root, pointer, label="selector evidence high-water")
    clean = validate_runtime_object(value, label="selector evidence high-water")
    if (
        clean.get("schema") != "options.sparse_selector_evidence_high_water/v1"
        or pointer["key"]
        != f"{EVIDENCE_AUDIT_NAMESPACE}/{clean['high_water_id']}.json"
    ):
        _fail("selector evidence high-water namespace drifted")
    snapshot = _load_pointer(
        root, clean["snapshot"], label="selector evidence source snapshot"
    )
    snapshot = validate_runtime_object(
        snapshot, label="selector evidence source snapshot"
    )
    if (
        snapshot.get("schema")
        != "options.sparse_selector_evidence_source_snapshot/v1"
        or clean["snapshot"]["key"]
        != f"{EVIDENCE_AUDIT_NAMESPACE}/{snapshot['snapshot_id']}.json"
        or snapshot["lifecycle_state"]["state_id"] != clean["source_state_id"]
        or snapshot["producer_contract"] != clean["producer_contract"]
        or snapshot["lifecycle_state"]["activation"] != clean["activation"]
        or snapshot["lifecycle_state"]["lifecycle_head"]
        != clean["lifecycle_head"]
        or snapshot["lifecycle_state"]["mark_cursor"] != clean["mark_cursor"]
        or snapshot["lifecycle_state"]["ledger_cursor"] != clean["ledger_cursor"]
        or snapshot["live_mark_head"] != clean["captured_mark_head"]
        or snapshot["live_ledger_receipt"] != clean["captured_ledger_receipt"]
    ):
        _fail("selector evidence high-water escaped its source snapshot")
    previous = clean["previous_complete"]
    prior: dict[str, Any] | None = None
    if previous is not None:
        prior = _load_pointer(
            root, previous, label="selector prior complete evidence high-water"
        )
        prior = validate_runtime_object(
            prior, label="selector prior complete evidence high-water"
        )
        if (
            prior.get("schema")
            != "options.sparse_selector_evidence_high_water/v1"
            or prior.get("phase") != "COMPLETE"
            or previous["key"]
            != f"{EVIDENCE_AUDIT_NAMESPACE}/{prior.get('high_water_id')}.json"
        ):
            _fail("selector evidence high-water parent is not exact and complete")
    if clean["replay_state"] is not None:
        replay = _load_pointer(
            root, clean["replay_state"], label="selector evidence replay state"
        )
        replay = validate_runtime_object(
            replay, label="selector evidence replay state"
        )
        inherited_replay = (
            prior is not None
            and clean["replay_state"] == prior.get("replay_state")
            and replay.get("snapshot") == prior.get("snapshot")
        )
        if (
            replay.get("schema")
            != "options.sparse_selector_evidence_replay_state/v1"
            or clean["replay_state"]["key"]
            != f"{EVIDENCE_AUDIT_NAMESPACE}/{replay.get('replay_id')}.json"
            or (
                replay.get("snapshot") != clean["snapshot"]
                and not inherited_replay
            )
        ):
            _fail("selector evidence replay state escaped its high-water")
        state = replay["state"]
        if (
            state["state_id"] != clean["replay_state_id"]
            or state["lifecycle_head"] != clean["replay_lifecycle_head"]
            or state["mark_cursor"] != clean["replay_mark_cursor"]
            or state["ledger_cursor"] != clean["replay_ledger_cursor"]
        ):
            _fail("selector evidence replay state receipt drifted")
    return clean


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
    if raw_head["evidence_high_water"] is not None:
        _load_evidence_high_water(root, raw_head["evidence_high_water"])
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


def _authenticate_store_wal_preflight(root: Path) -> None:
    """Reject mutable or rolled-back authority state without repairing it."""

    for name, limit in (
        (INTENT_FILE, MAX_INTENT_BYTES),
        (INTENT_ATTEMPT_FILE, 1024 * 1024),
        (INTENT_PREPARE_FILE, MAX_INTENT_BYTES),
    ):
        if _read_private_file(
            root / name, root=root, limit=limit, required=False
        ) is not None:
            _fail("selector authentication found an unresolved durable WAL")
    head = _load_head(root)
    parent = "genesis" if head is None else head["head_id"]
    if _read_private_file(
        _object_path(root, f"{INTENT_SEAL_NAMESPACE}/{parent}.json"),
        root=root,
        limit=1024 * 1024,
        required=False,
    ) is not None:
        _fail("selector current HEAD has a surviving child intent seal")


def _authenticate_sharded_root_graph(
    root: Path,
    receipt: Mapping[str, Any],
    *,
    domain: str,
) -> list[dict[str, Any]]:
    """Authenticate every reachable directory/bucket and return exact entries."""

    clean = private_auth_dict.validate_sharded_root(receipt, domain=domain)
    pointer = clean["root"]
    if pointer is None:
        if clean["entry_count"] != 0:
            _fail("selector evidence auth root lost its entries")
        return []
    directory = private_auth_dict.validate_node(
        _load_pointer(root, pointer, label="selector evidence auth directory"),
        domain=domain,
    )
    if (
        private_auth_dict.pointer(directory) != pointer
        or directory["kind"] != "directory"
        or directory["entry_count"] != clean["entry_count"]
    ):
        _fail("selector evidence auth directory drifted")
    entries: list[dict[str, Any]] = []
    for shard_index, bucket_pointer in enumerate(directory["buckets"]):
        if bucket_pointer is None:
            continue
        bucket = private_auth_dict.validate_node(
            _load_pointer(
                root, bucket_pointer, label="selector evidence auth bucket"
            ),
            domain=domain,
        )
        if (
            private_auth_dict.pointer(bucket) != bucket_pointer
            or bucket["kind"] != "bucket"
            or bucket["shard"] != f"{shard_index:02x}"
        ):
            _fail("selector evidence auth bucket drifted")
        entries.extend(copy.deepcopy(bucket["entries"]))
    if len(entries) != clean["entry_count"]:
        _fail("selector evidence auth entry count drifted")
    return entries

def _auth_entry_receipts(
    entries: Sequence[Mapping[str, Any]],
) -> list[bytes]:
    """Return a canonical, order-independent receipt for authenticated entries."""

    return sorted(
        canonical_bytes(
            {
                "logical_key": copy.deepcopy(entry["logical_key"]),
                "binding": copy.deepcopy(entry["binding"]),
            }
        )
        for entry in entries
    )


def _authenticate_replayed_ledger_index(
    root: Path,
    high: Mapping[str, Any],
    *,
    entries: Sequence[Mapping[str, Any]],
    inherited_chunks: Sequence[Mapping[str, Any]] = (),
    prior_high: Mapping[str, Any] | None = None,
    prior_entries: Sequence[Mapping[str, Any]] = (),
) -> None:
    """Reparse the captured prefix and require its exact authenticated index."""

    byte_cursor = (
        0 if prior_high is None else int(prior_high["ledger_replay_bytes"])
    )
    row_cursor = (
        0 if prior_high is None else int(prior_high["ledger_replay_rows"])
    )
    expected: list[dict[str, Any]] = [
        copy.deepcopy(dict(entry)) for entry in prior_entries
    ]
    seen_plans: set[str] = {
        str(entry["logical_key"][1])
        for entry in prior_entries
        if isinstance(entry.get("logical_key"), list)
        and len(entry["logical_key"]) == 2
        and entry["logical_key"][0] == "plan"
    }
    boundary = {"bytes": int(high["ledger_replay_bytes"])}
    while byte_cursor < boundary["bytes"]:
        next_byte, rows = _captured_ledger_rows(
            root,
            high["ledger_chunks"],
            snapshot=high["snapshot"],
            inherited_pointers=inherited_chunks,
            byte_cursor=byte_cursor,
            row_cursor=row_cursor,
            boundary=boundary,
            row_limit=256,
        )
        if next_byte <= byte_cursor:
            _fail("selector replay ledger authentication made no progress")
        for ordinal, row in rows:
            binding = _ledger_row_binding(row, ordinal)
            plan_id = binding["plan_id"]
            if plan_id in seen_plans:
                _fail("selector replay ledger repeats a plan id")
            seen_plans.add(plan_id)
            expected.extend(
                (
                    {"logical_key": ["plan", plan_id], "binding": binding},
                    {"logical_key": ["ordinal", ordinal], "binding": binding},
                )
            )
        byte_cursor = next_byte
        row_cursor += len(rows)
    if (
        byte_cursor != int(high["ledger_replay_bytes"])
        or row_cursor != int(high["ledger_replay_rows"])
        or len(expected) != 2 * row_cursor
        or _auth_entry_receipts(entries) != _auth_entry_receipts(expected)
    ):
        _fail("selector replay ledger index differs from captured ledger bytes")

def _authenticate_cold_occurrence_source_path(
    lifecycle_root: Path,
    mark_root: Path,
    *,
    snapshot: Mapping[str, Any],
    boundary_entries: Sequence[Mapping[str, Any]],
) -> None:
    """Authenticate the exact activation-to-target producer occurrence path."""

    target = snapshot["lifecycle_state"]
    activation_boundary = snapshot["activation_boundary"]
    activation_mark = _load_frozen_mark_observation(
        mark_root, activation_boundary["mark_boundary"]
    )
    expected_activation = _frozen_activation_event(
        activation_boundary, activation_mark
    )
    actual_activation = _load_frozen_lifecycle_event(
        lifecycle_root, target["activation"]
    )
    if (
        actual_activation != expected_activation
        or lifecycle._event_pointer(actual_activation) != target["activation"]
    ):
        _fail("selector activation event is not its exact frozen occurrence")

    activation_state = lifecycle._make_state(
        activation=target["activation"],
        lifecycle_head=target["activation"],
        mark_cursor=activation_boundary["mark_boundary"],
        ledger_cursor=activation_boundary["ledger_boundary"],
        enrollments={},
        terminals={},
        latest_marks={},
    )
    state_id = activation_state["state_id"]
    lifecycle_head = copy.deepcopy(activation_state["lifecycle_head"])
    mark_cursor = copy.deepcopy(activation_state["mark_cursor"])
    ledger_cursor = copy.deepcopy(activation_state["ledger_cursor"])
    expected_entries: list[dict[str, Any]] = [
        {
            "logical_key": ["activation", activation_boundary["boundary_id"]],
            "binding": _activation_boundary_receipt(activation_boundary),
        }
    ]
    seen_states: set[str] = set()
    # The authenticated root cardinality bounds the source walk.  It also
    # prevents an outgoing crash boundary after the pinned target from being
    # mistaken for an accepted occurrence.
    while state_id != target["state_id"]:
        if state_id in seen_states or len(expected_entries) > len(boundary_entries):
            _fail("selector occurrence boundary path is cyclic or incomplete")
        seen_states.add(state_id)
        boundary, receipt = _load_exact_advance_boundary(
            lifecycle_root, state_id
        )
        expected_entries.append(
            {
                "logical_key": ["advance", state_id],
                "binding": receipt,
            }
        )
        previous = copy.deepcopy(lifecycle_head)
        for event_pointer in boundary["event_pointers"]:
            event = _load_frozen_lifecycle_event(
                lifecycle_root, event_pointer
            )
            if event.get("previous") != previous:
                _fail("selector occurrence boundary event chain is not contiguous")
            previous = copy.deepcopy(event_pointer)
        if previous != boundary["candidate_lifecycle_head"]:
            _fail("selector occurrence boundary event tail drifted")
        state_id = boundary["candidate_state_id"]
        lifecycle_head = copy.deepcopy(boundary["candidate_lifecycle_head"])
        mark_cursor = copy.deepcopy(boundary["mark_boundary"])
        ledger_cursor = copy.deepcopy(boundary["ledger_boundary"])

    if (
        lifecycle_head != target["lifecycle_head"]
        or mark_cursor != target["mark_cursor"]
        or ledger_cursor != target["ledger_cursor"]
        or _auth_entry_receipts(boundary_entries)
        != _auth_entry_receipts(expected_entries)
    ):
        _fail("selector occurrence boundary index differs from its exact source path")


def _authenticate_incremental_occurrence_source_path(
    lifecycle_root: Path,
    *,
    target: Mapping[str, Any],
    prior_high: Mapping[str, Any],
    prior_entries: Sequence[Mapping[str, Any]],
    boundary_entries: Sequence[Mapping[str, Any]],
) -> None:
    """Authenticate only the exact suffix after a prior COMPLETE occurrence."""

    state_id = str(prior_high["source_state_id"])
    lifecycle_head = copy.deepcopy(prior_high["lifecycle_head"])
    mark_cursor = copy.deepcopy(prior_high["mark_cursor"])
    ledger_cursor = copy.deepcopy(prior_high["ledger_cursor"])
    expected_entries = [copy.deepcopy(dict(entry)) for entry in prior_entries]
    seen_states: set[str] = set()
    while state_id != target["state_id"]:
        if state_id in seen_states or len(expected_entries) > len(boundary_entries):
            _fail("selector incremental occurrence path is cyclic or incomplete")
        seen_states.add(state_id)
        boundary, receipt = _load_exact_advance_boundary(
            lifecycle_root, state_id
        )
        expected_entries.append(
            {
                "logical_key": ["advance", state_id],
                "binding": receipt,
            }
        )
        previous = copy.deepcopy(lifecycle_head)
        for event_pointer in boundary["event_pointers"]:
            event = _load_frozen_lifecycle_event(
                lifecycle_root, event_pointer
            )
            if event.get("previous") != previous:
                _fail("selector incremental boundary events are not contiguous")
            previous = copy.deepcopy(event_pointer)
        if previous != boundary["candidate_lifecycle_head"]:
            _fail("selector incremental boundary event tail drifted")
        state_id = boundary["candidate_state_id"]
        lifecycle_head = copy.deepcopy(boundary["candidate_lifecycle_head"])
        mark_cursor = copy.deepcopy(boundary["mark_boundary"])
        ledger_cursor = copy.deepcopy(boundary["ledger_boundary"])
    if (
        lifecycle_head != target["lifecycle_head"]
        or mark_cursor != target["mark_cursor"]
        or ledger_cursor != target["ledger_cursor"]
        or _auth_entry_receipts(boundary_entries)
        != _auth_entry_receipts(expected_entries)
    ):
        _fail("selector incremental boundary index differs from its exact suffix")


def _authenticate_evidence_high_water_graph(
    root: Path,
    pointer: Mapping[str, Any],
    *,
    evidence_inputs: EvidenceInputs | None,
) -> dict[str, Any]:
    high = _load_evidence_high_water(root, pointer)
    prior_high: dict[str, Any] | None = None
    prior_entries: dict[str, list[dict[str, Any]]] = {}
    inherited_chunks: Sequence[Mapping[str, Any]] = ()
    if high["previous_complete"] is not None:
        prior_high = _authenticate_evidence_high_water_graph(
            root,
            high["previous_complete"],
            evidence_inputs=evidence_inputs,
        )
        if (
            prior_high["phase"] != "COMPLETE"
            or prior_high["producer_contract"] != high["producer_contract"]
        ):
            _fail("selector incremental evidence parent drifted")
        inherited_chunks = tuple(prior_high["ledger_chunks"])
    snapshot = validate_runtime_object(
        _load_pointer(
            root, high["snapshot"], label="selector evidence source snapshot"
        ),
        label="selector evidence source snapshot",
    )
    stage = high["occurrence_stage"]
    target = snapshot["lifecycle_state"]
    no_base = all(
        high[field] is None
        for field in (
            "base_state_id",
            "base_lifecycle_head",
            "base_mark_cursor",
            "base_ledger_cursor",
        )
    )
    has_base = all(
        high[field] is not None
        for field in (
            "base_state_id",
            "base_lifecycle_head",
            "base_mark_cursor",
            "base_ledger_cursor",
        )
    )
    incremental = prior_high is not None
    if (
        (high["phase"] == "AUDIT_PINNED" and stage != "LEDGER_CAPTURE")
        or (high["phase"] == "COMPLETE") != (stage == "DONE")
        or (
            stage in {"LEDGER_CAPTURE", "LIVE_MARK_BACKWALK", "COLD_ACTIVATION"}
            and (
                (
                    not incremental
                    and (
                        high["replay_state"] is not None
                        or high["ledger_replay_bytes"] != 0
                        or high["ledger_replay_rows"] != 0
                    )
                )
                or high["current_boundary"] is not None
                or not no_base
            )
        )
        or (
            stage == "LEDGER_CAPTURE"
            and (
                high["live_mark_scan_cursor"] != high["captured_mark_head"]
                or high["live_mark_reverse_ordinal"] != 0
            )
        )
        or (
            stage in {"LIVE_MARK_BACKWALK", "COLD_ACTIVATION"}
            and high["ledger_capture_bytes"]
            != int(snapshot["live_ledger_receipt"]["bytes"])
        )
        or (
            stage == "COLD_ACTIVATION"
            and high["live_mark_scan_cursor"] != target["mark_cursor"]
        )
        or (
            stage == "LEDGER_ROWS"
            and (
                high["replay_state"] is None
                or high["current_boundary"] is None
                or not (
                    no_base
                    if high["current_boundary"]["kind"] == "activation"
                    else has_base
                )
                or high["ledger_replay_bytes"]
                > int(high["current_boundary"]["ledger_boundary"]["bytes"])
                or high["ledger_replay_rows"]
                > int(high["current_boundary"]["ledger_boundary"]["row_count"])
            )
        )
        or (
            stage == "EDGE_INIT"
            and (
                high["replay_state"] is None
                or high["current_boundary"] is not None
                or not no_base
                or high["boundary_mark_cursor"] is not None
                or any(
                    high[field] != 0
                    for field in (
                        "boundary_mark_row_cursor",
                        "boundary_mark_ordinal",
                        "boundary_event_cursor",
                        "boundary_terminal_cursor",
                    )
                )
            )
        )
        or (
            stage
            in {
                "EDGE_MARK_BACKWALK",
                "EDGE_MARK_ROWS",
                "EDGE_TERMINALS",
                "EDGE_FINALIZE",
            }
            and (
                high["replay_state"] is None
                or high["current_boundary"] is None
                or high["current_boundary"]["kind"] != "advance"
                or not has_base
            )
        )
        or (
            stage in {"EDGE_TERMINALS", "EDGE_FINALIZE"}
            and (
                high["boundary_mark_cursor"] is not None
                or high["boundary_mark_ordinal"] != 0
                or high["boundary_mark_row_cursor"] != 0
            )
        )
        or (stage == "DONE" and high["replay_state"] is None)
    ):
        _fail("selector evidence high-water occurrence stage drifted")
    roots = {
        "boundary_index": EVIDENCE_BOUNDARY_DOMAIN,
        "mark_seen_index": EVIDENCE_MARK_SEEN_DOMAIN,
        "ledger_row_index": EVIDENCE_LEDGER_ROW_DOMAIN,
        "event_enrollment_index": EVIDENCE_EVENT_ENROLLMENT_DOMAIN,
        "event_seen_index": EVIDENCE_EVENT_SEEN_DOMAIN,
        "event_terminal_index": EVIDENCE_EVENT_TERMINAL_DOMAIN,
        "state_enrollment_index": EVIDENCE_STATE_ENROLLMENT_DOMAIN,
        "state_terminal_index": EVIDENCE_STATE_TERMINAL_DOMAIN,
        "state_latest_index": EVIDENCE_STATE_LATEST_DOMAIN,
        "derived_latest_index": EVIDENCE_DERIVED_LATEST_DOMAIN,
        "ledger_terminal_index": EVIDENCE_LEDGER_TERMINAL_DOMAIN,
    }
    authenticated_entries = {
        field: _authenticate_sharded_root_graph(
            root, high[field], domain=domain
        )
        for field, domain in roots.items()
    }
    if prior_high is not None:
        prior_entries = {
            "boundary_index": _authenticate_sharded_root_graph(
                root,
                prior_high["boundary_index"],
                domain=EVIDENCE_BOUNDARY_DOMAIN,
            ),
            "ledger_row_index": _authenticate_sharded_root_graph(
                root,
                prior_high["ledger_row_index"],
                domain=EVIDENCE_LEDGER_ROW_DOMAIN,
            ),
        }

    captured = 0
    for ordinal, chunk_pointer in enumerate(high["ledger_chunks"], start=1):
        chunk, raw = _load_evidence_ledger_chunk(
            root,
            chunk_pointer,
            snapshot=high["snapshot"],
            inherited_pointers=inherited_chunks,
            ordinal=ordinal,
            first_byte=captured,
        )
        captured = chunk["last_byte"]
        if captured > high["ledger_capture_bytes"] or not raw:
            _fail("selector evidence ledger chunk escaped its capture cursor")
    if captured != high["ledger_capture_bytes"]:
        _fail("selector evidence ledger capture cursor omitted a chunk")
    if captured == int(snapshot["live_ledger_receipt"]["bytes"]):
        _authenticate_captured_ledger(
            root,
            high["ledger_chunks"],
            snapshot=high["snapshot"],
            inherited_pointers=inherited_chunks,
            receipt=snapshot["live_ledger_receipt"],
        )

    if high["replay_state"] is not None:
        replay = validate_runtime_object(
            _load_pointer(
                root, high["replay_state"], label="selector evidence replay state"
            ),
            label="selector evidence replay state",
        )
        if replay["state"]["state_id"] != high["replay_state_id"]:
            _fail("selector replay state escaped its high-water")

    if high["ledger_row_index"]["entry_count"] != 2 * high["ledger_replay_rows"]:
        _fail("selector replay ledger index cardinality drifted")
    _authenticate_replayed_ledger_index(
        root,
        high,
        entries=authenticated_entries["ledger_row_index"],
        inherited_chunks=inherited_chunks,
        prior_high=prior_high,
        prior_entries=prior_entries.get("ledger_row_index", ()),
    )

    if evidence_inputs is None or (
        evidence_inputs.mark_root is None
        or evidence_inputs.lifecycle_root is None
    ):
        if high["phase"] == "COMPLETE":
            _fail("selector complete evidence high-water requires producer roots")
    else:
        mark_root = Path(evidence_inputs.mark_root).expanduser()
        lifecycle_root = Path(evidence_inputs.lifecycle_root).expanduser()
        with _selector_lane(root, create=False) as selector_lane:
            with _anchored_evidence_sources(
                mark_root, lifecycle_root, selector_lane=selector_lane
            ) as sources:
                if sources.producer_roots != snapshot["producer_roots"]:
                    _fail("selector evidence producer roots drifted")
                token = _ACTIVE_EVIDENCE_SOURCES.set(sources)
                try:
                    if (
                        _read_anchored_activation_boundary(sources.lifecycle)
                        != snapshot["activation_boundary"]
                    ):
                        _fail("selector activation boundary receipt drifted")
                    if prior_high is not None:
                        prior_snapshot = validate_runtime_object(
                            _load_pointer(
                                root,
                                prior_high["snapshot"],
                                label="selector prior source snapshot",
                            ),
                            label="selector prior source snapshot",
                        )
                        if (
                            prior_snapshot["producer_roots"]
                            != snapshot["producer_roots"]
                        ):
                            _fail("selector incremental producer roots drifted")
                        _anchored_mark_chain_contains(
                            sources.mark,
                            snapshot["live_mark_head"],
                            (
                                target["mark_cursor"],
                                prior_snapshot["live_mark_head"],
                            ),
                        )
                        _anchored_ledger_extends(
                            sources.lifecycle,
                            prior_snapshot["live_ledger_receipt"],
                        )
                    if high["phase"] == "COMPLETE":
                        if prior_high is None:
                            _authenticate_cold_occurrence_source_path(
                                lifecycle_root,
                                mark_root,
                                snapshot=snapshot,
                                boundary_entries=authenticated_entries[
                                    "boundary_index"
                                ],
                            )
                        else:
                            _authenticate_incremental_occurrence_source_path(
                                lifecycle_root,
                                target=target,
                                prior_high=prior_high,
                                prior_entries=prior_entries["boundary_index"],
                                boundary_entries=authenticated_entries[
                                    "boundary_index"
                                ],
                            )
                    else:
                        for entry in authenticated_entries["boundary_index"]:
                            logical_key = entry["logical_key"]
                            binding = entry["binding"]
                            if (
                                isinstance(logical_key, list)
                                and len(logical_key) == 2
                                and logical_key[0] == "activation"
                                and binding
                                == _activation_boundary_receipt(
                                    snapshot["activation_boundary"]
                                )
                            ):
                                continue
                            if (
                                isinstance(logical_key, list)
                                and len(logical_key) == 2
                                and logical_key[0] == "advance"
                                and logical_key[1]
                                == binding.get("base_state_id")
                            ):
                                _load_boundary_from_receipt(
                                    lifecycle_root, binding
                                )
                                continue
                            _fail(
                                "selector boundary index contains a foreign key"
                            )
                    for entry in authenticated_entries["mark_seen_index"]:
                        _load_frozen_mark_observation(mark_root, entry["binding"])
                    for entry in authenticated_entries["event_enrollment_index"]:
                        event = _load_frozen_lifecycle_event(
                            lifecycle_root, entry["binding"]
                        )
                        if event.get("event_kind") != "enrollment":
                            _fail("selector generated-enrollment index drifted")
                finally:
                    _ACTIVE_EVIDENCE_SOURCES.reset(token)

    if high["phase"] == "COMPLETE":
        replay = validate_runtime_object(
            _load_pointer(
                root, high["replay_state"], label="selector evidence replay state"
            ),
            label="selector evidence replay state",
        )
        target = snapshot["lifecycle_state"]
        if (
            high["occurrence_stage"] != "DONE"
            or replay["state"] != target
            or high["replay_state_id"] != target["state_id"]
            or high["ledger_capture_bytes"]
            != int(snapshot["live_ledger_receipt"]["bytes"])
            or high["ledger_replay_bytes"] != int(target["ledger_cursor"]["bytes"])
            or high["ledger_replay_rows"]
            != int(target["ledger_cursor"]["row_count"])
            or high["live_mark_scan_cursor"] != target["mark_cursor"]
            or high["current_boundary"] is not None
            or any(
                high[field] is not None
                for field in (
                    "base_state_id",
                    "base_lifecycle_head",
                    "base_mark_cursor",
                    "base_ledger_cursor",
                    "boundary_mark_cursor",
                )
            )
            or any(
                high[field] != 0
                for field in (
                    "boundary_mark_row_cursor",
                    "boundary_mark_ordinal",
                    "boundary_ledger_row_cursor",
                    "boundary_ledger_byte_cursor",
                    "boundary_event_cursor",
                    "boundary_terminal_cursor",
                )
            )
        ):
            _fail("selector complete evidence replay is not exact")
    return high


def authenticate_store(
    root: Path,
    *,
    evidence_inputs: EvidenceInputs | None = None,
    _allow_durable_intent: bool = False,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], bytes]:
    if not _allow_durable_intent:
        _authenticate_store_wal_preflight(root)
    state = _authenticate_selector_state(root)
    if state is None:
        return None, [], b""
    head, pending, cycle, _last_candidate, _last_decision = state
    if head["evidence_high_water"] is not None:
        _authenticate_evidence_high_water_graph(
            root,
            head["evidence_high_water"],
            evidence_inputs=evidence_inputs,
        )
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
    candidate_index_cache = private_auth_dict.ShardedLookupCache.empty(
        CANDIDATE_INDEX_DOMAIN
    )
    for receipt in candidate_receipts:
        membership = _candidate_index_lookup(
            root,
            head["candidate_index"],
            receipt["campaign_id"],
            node_cache=candidate_index_cache,
        )
        if membership.binding != {
            "campaign_id": receipt["campaign_id"],
            "candidate_id": receipt["candidate_id"],
            "candidate": receipt["pointer"],
        }:
            _fail("selector candidate index does not bind its complete chain")

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
    proposal_session: str | None = None
    proposal_count = 0
    previous_available: datetime | None = None
    by_decision_id: dict[str, dict[str, Any]] = {}
    generation_sessions: dict[str, set[str]] = {}
    generation_pointers: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        generation_pointer = decision["evidence"]["generation"]
        generation_identity, clean_generation_pointer = _full_pointer(
            generation_pointer, label="authenticated evidence generation"
        )
        prior_generation_pointer = generation_pointers.get(generation_identity)
        if (
            prior_generation_pointer is not None
            and prior_generation_pointer != clean_generation_pointer
        ):
            _fail("authenticated evidence generation cached full pointer drifted")
        generation_pointers[generation_identity] = clean_generation_pointer
        generation_sessions.setdefault(generation_identity, set()).add(
            _utc(
                decision["decision_event_at"],
                label="authenticated evidence session",
            )
            .astimezone(ET)
            .date()
            .isoformat()
        )
    generation_snapshots: dict[str, EvidenceSnapshot] = {}
    generation_cache: _PointerObjectCache = {}
    manifest_cache: _PointerObjectCache = {}
    source_cache: _PointerObjectCache = {}
    w1a_cache: _W1APublicationCache = {}
    w1a_seen: dict[str, dict[str, Any]] = {}
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
        generation_pointer = decision["evidence"]["generation"]
        generation_identity, _clean_generation_pointer = _full_pointer(
            generation_pointer, label="authenticated evidence generation"
        )
        generation, _generation_body = _load_pointer_cached(
            root,
            generation_pointer,
            label="authenticated evidence generation",
            cache=generation_cache,
        )
        compact_present = any(
            decision["evidence"][slot] is not None
            for slot in ("konseki", "mark", "lifecycle")
        )
        evidence_snapshot: EvidenceSnapshot | None = None
        if compact_present:
            if evidence_inputs is None:
                _fail(
                    "selector compact evidence lacks trusted producer inputs"
                )
            evidence_snapshot = generation_snapshots.get(generation_identity)
            if evidence_snapshot is None:
                settled_manifest, _settled_manifest_body = _load_pointer_cached(
                    root,
                    generation["settled_manifest"],
                    label="authenticated evidence settled manifest",
                    cache=manifest_cache,
                )
                scoped_candidates = tuple(
                    _load_pointer(
                        root,
                        pointer,
                        label="authenticated evidence candidate",
                    )
                    for pointer in settled_manifest["candidates"]
                )
                evidence_snapshot = _evidence_snapshot_from_generation(
                    generation,
                    evidence_inputs,
                    root=root,
                    candidates=scoped_candidates,
                    session_dates=frozenset(
                        generation_sessions[generation_identity]
                    ),
                    generation_already_validated=True,
                    manifest_cache=manifest_cache,
                    source_cache=source_cache,
                    w1a_cache=w1a_cache,
                )
                generation_snapshots[generation_identity] = evidence_snapshot
        _validate_decision_evidence_objects(
            root,
            decision,
            candidate=candidate,
            evidence_inputs=evidence_inputs or EvidenceInputs(),
            generation_cache=generation_cache,
            manifest_cache=manifest_cache,
            source_cache=source_cache,
            w1a_cache=w1a_cache,
            evidence_snapshot=evidence_snapshot,
        )
        source_pointer = generation["w1a_source_receipt"]
        if source_pointer is not None:
            source_identity, clean_source_pointer = _full_pointer(
                source_pointer,
                label="authenticated selector W1A source receipt",
            )
            seen_source_pointer = w1a_seen.get(source_identity)
            if (
                seen_source_pointer is not None
                and seen_source_pointer != clean_source_pointer
            ):
                _fail("authenticated selector W1A cached full pointer drifted")
            source_receipt, _source_body = _load_pointer_cached(
                root,
                source_pointer,
                label="authenticated selector W1A source receipt",
                cache=source_cache,
            )
            if seen_source_pointer is None:
                reconstructed_w1a_high_water = _advance_w1a_high_water(
                    reconstructed_w1a_high_water, source_receipt
                )
                w1a_seen[source_identity] = clean_source_pointer
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
        session = decision["decision_nyse_session_date"]
        if session is not None:
            parsed_session = date.fromisoformat(session)
            if not nyse_calendar.is_session(parsed_session):
                _fail("selector decision session is not a NYSE session")
            if proposal_session is None:
                proposal_session = session
                proposal_count = 0
            elif session < proposal_session:
                _fail("selector proposal session moved backward")
            elif session > proposal_session:
                prior_session = date.fromisoformat(proposal_session)
                transitions = nyse_calendar.sessions_between(
                    prior_session + timedelta(days=1), parsed_session
                )
                if not transitions or transitions[-1] != parsed_session:
                    _fail("selector proposal counter reset off-session")
                proposal_session = session
                proposal_count = 0
        if decision["action"] == "propose":
            if (
                session is None
                or session != proposal_session
                or proposal_count >= PROPOSAL_CAP
                or decision["proposal_ordinal"] != proposal_count + 1
            ):
                _fail("selector proposal ordinal escaped its session cap")
            proposal_count += 1
        by_decision_id[decision["decision_id"]] = decision

    for ordinals in proposed_by_session.values():
        if (
            ordinals != list(range(1, len(ordinals) + 1))
            or len(ordinals) > PROPOSAL_CAP
        ):
            _fail("selector proposal ordinals or per-session cap drifted")
    if (
        head["proposal_session_date"] != proposal_session
        or head["proposal_session_count"] != proposal_count
    ):
        _fail("selector HEAD proposal session state drifted")
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
        settled, _settled_body = _load_pointer_cached(
            root,
            settled_pointer,
            label="settled manifest",
            cache=manifest_cache,
        )
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
    generation_cache: _PointerObjectCache | None = None,
    manifest_cache: _PointerObjectCache | None = None,
    source_cache: _PointerObjectCache | None = None,
    w1a_cache: _W1APublicationCache | None = None,
    evidence_snapshot: EvidenceSnapshot | None = None,
) -> set[str]:
    def load(
        pointer: Mapping[str, Any],
        *,
        label: str,
        cache: _PointerObjectCache | None = None,
    ) -> tuple[Mapping[str, Any], bytes]:
        planned = None if planned_by_key is None else planned_by_key.get(pointer["key"])
        if planned is not None:
            if planned.pointer != pointer:
                _fail(f"{label} differs from planned bytes")
            return planned.value, planned.body
        if cache is not None:
            return _load_pointer_cached(
                root, pointer, label=label, cache=cache
            )
        value = _load_pointer(root, pointer, label=label)
        return value, canonical_bytes(value)

    def validated(
        value: Mapping[str, Any], *, label: str
    ) -> Mapping[str, Any]:
        # Authenticated store reads pass through _load_pointer(), which already
        # performs runtime-schema validation before an object can enter a
        # call-local cache.  Planned recovery objects still require the
        # explicit validation below because they may not have been disk-loaded.
        if planned_by_key is None:
            return value
        return validate_runtime_object(value, label=label)

    generation_pointer = decision["evidence"].get("generation")
    if not isinstance(generation_pointer, Mapping):
        _fail("selector decision lacks its evidence generation")
    generation_value, generation_body = load(
        generation_pointer,
        label="decision evidence generation",
        cache=generation_cache,
    )
    generation = validated(
        generation_value, label="decision evidence generation"
    )
    settled_manifest_value, _settled_manifest_body = load(
        generation["settled_manifest"],
        label="decision evidence settled manifest",
        cache=manifest_cache,
    )
    settled_manifest = validated(
        settled_manifest_value, label="decision evidence settled manifest"
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
            source_pointer,
            label="decision W1A source receipt",
            cache=source_cache,
        )
        source_receipt = validated(
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
        w1a_publication = _cached_w1a_publication(
            source_pointer, cache=w1a_cache
        )
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
            w1a_publication = _authenticate_historical_w1a_source_cached(
                source_pointer,
                source_receipt,
                receipt_root=Path(evidence_inputs.w1a_receipt_root),
                manifest=settled_manifest,
                candidate_rows=candidate_rows,
                cache=w1a_cache,
            )
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
        value = validated(value, label=f"decision {slot} evidence")
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
                if evidence_snapshot is not None:
                    matches = [
                        item
                        for item in evidence_snapshot.enrollments_by_contract.get(
                            _campaign_contract_key(candidate["campaign_row"]), ()
                        )
                        if item[0] == plan_id
                        and item[2] == value["enrollment_pointer"]
                    ]
                    if len(matches) != 1:
                        _fail("selector lifecycle evidence source binding drifted")
                    enrollment = matches[0][1]
                    if (
                        not _contract_matches_campaign(
                            enrollment["payload"]["contract"],
                            candidate["campaign_row"],
                        )
                        or not _all_false_mapping(enrollment.get("authority"))
                        or (
                            decision["contract"] is not None
                            and _nbbo_contract(enrollment["payload"]["contract"])
                            != decision["contract"]
                        )
                    ):
                        _fail("selector lifecycle evidence source binding drifted")
                elif evidence_inputs is not None and evidence_inputs.lifecycle_root is not None:
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
                if evidence_snapshot is not None:
                    admitted = evidence_snapshot.mark_rows_by_plan_session.get(
                        (plan_id, session_date)
                    )
                    if admitted is None:
                        _fail("selector mark evidence source binding drifted")
                    mark_pointer, observation, row = admitted
                    if (
                        mark_pointer != value["mark_pointer"]
                        or value["selected_row_sha256"]
                        != _sha256(canonical_bytes(row))
                        or not _all_false_mapping(observation.get("authority"))
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
                elif evidence_inputs is not None and evidence_inputs.mark_root is not None:
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
    *,
    episode_ids: frozenset[str] | None = None,
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
            if (
                owner["schema"] == "options.signal_episode/v1"
                and (episode_ids is None or owner["id"] in episode_ids)
            ):
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


_W1APublicationCache = dict[
    str,
    tuple[dict[str, Any], _W1APublication],
]


def _cached_w1a_publication(
    source_pointer: Mapping[str, Any],
    *,
    cache: _W1APublicationCache | None,
) -> _W1APublication | None:
    if cache is None:
        return None
    identity, clean_pointer = _full_pointer(
        source_pointer, label="historical selector W1A source"
    )
    cached = cache.get(identity)
    if cached is None:
        return None
    cached_pointer, publication = cached
    if cached_pointer != clean_pointer:
        _fail("historical selector W1A cached full pointer drifted")
    return publication


def _authenticate_historical_w1a_source_cached(
    source_pointer: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    receipt_root: Path,
    manifest: Mapping[str, Any],
    candidate_rows: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    cache: _W1APublicationCache | None,
) -> _W1APublication:
    if cache is None:
        return _authenticate_historical_w1a_source(
            receipt,
            receipt_root=receipt_root,
            manifest=manifest,
            candidate_rows=candidate_rows,
        )
    identity, clean_pointer = _full_pointer(
        source_pointer, label="historical selector W1A source"
    )
    cached = _cached_w1a_publication(source_pointer, cache=cache)
    if cached is not None:
        return cached
    publication = _authenticate_historical_w1a_source(
        receipt,
        receipt_root=receipt_root,
        manifest=manifest,
        candidate_rows=candidate_rows,
    )
    cache[identity] = (clean_pointer, publication)
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


def _campaign_occ_symbol(campaign: Mapping[str, Any]) -> str:
    group = campaign["group"]
    root = str(group["ticker"])
    right = str(group["right"])
    expiry = date.fromisoformat(str(group["expiration"]))
    strike_millis = Decimal(_canonical_strike_text(group["strike_key"])) * Decimal(
        1000
    )
    if (
        not re.fullmatch(r"[A-Z0-9]{1,6}", root)
        or right not in {"C", "P"}
        or strike_millis != strike_millis.to_integral_value()
        or not 1 <= int(strike_millis) <= 99_999_999
    ):
        _fail("selector evidence scope contains a malformed OCC contract")
    return (
        f"{root:<6}{expiry.strftime('%y%m%d')}{right}{int(strike_millis):08d}"
    )


@dataclass
class _EvidenceReadBudget:
    reads: int = 0
    bytes: int = 0

    def add_pointer(self, pointer: Mapping[str, Any], *, label: str) -> None:
        size = pointer.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise EvidenceGenerationDrift(f"{label} pointer size is malformed")
        self.reads += 1
        self.bytes += size
        if (
            self.reads > MAX_EVIDENCE_SOURCE_READS
            or self.bytes > MAX_EVIDENCE_SOURCE_BYTES
        ):
            raise EvidenceGenerationDrift(
                "selector evidence generation exceeds its fixed source-read budget"
            )

    def add_body(self, body: bytes, *, label: str) -> None:
        if not body:
            raise EvidenceGenerationDrift(f"{label} is empty")
        self.reads += 1
        self.bytes += len(body)
        if (
            self.reads > MAX_EVIDENCE_SOURCE_READS
            or self.bytes > MAX_EVIDENCE_SOURCE_BYTES
        ):
            raise EvidenceGenerationDrift(
                "selector evidence generation exceeds its fixed source-read budget"
            )


def _evidence_scope(
    candidates: Sequence[Mapping[str, Any]] | None,
    *,
    session_dates: frozenset[str] | None,
) -> tuple[
    frozenset[str],
    frozenset[tuple[str, str, str, str]],
    Mapping[str, tuple[str, str, str, str]],
    frozenset[str],
]:
    rows = tuple(candidates or ())
    if len(rows) > MAX_CANDIDATES_PER_MANIFEST:
        raise EvidenceGenerationDrift(
            "selector evidence scope exceeds the manifested candidate bound"
        )
    episodes: set[str] = set()
    contracts: set[tuple[str, str, str, str]] = set()
    occ_to_contract: dict[str, tuple[str, str, str, str]] = {}
    for candidate in rows:
        try:
            episode_id = candidate["final_episode_row"]["episode_id"]
            campaign = candidate["campaign_row"]
            contract_key = _campaign_contract_key(campaign)
            occ = _campaign_occ_symbol(campaign)
        except (KeyError, TypeError, ValueError, SparseSelectorError) as exc:
            raise EvidenceGenerationDrift(
                "selector manifested evidence scope is malformed"
            ) from exc
        if not isinstance(episode_id, str) or not episode_id:
            raise EvidenceGenerationDrift(
                "selector manifested evidence episode identity is malformed"
            )
        prior = occ_to_contract.setdefault(occ, contract_key)
        if prior != contract_key:
            raise EvidenceGenerationDrift(
                "selector manifested OCC symbol aliases distinct contracts"
            )
        episodes.add(episode_id)
        contracts.add(contract_key)
    sessions = frozenset(session_dates or ())
    for session_text in sessions:
        try:
            if date.fromisoformat(session_text).isoformat() != session_text:
                raise ValueError
        except ValueError as exc:
            raise EvidenceGenerationDrift(
                "selector evidence session scope is malformed"
            ) from exc
    return frozenset(episodes), frozenset(contracts), occ_to_contract, sessions


def _bounded_mark_chain(
    mark_root: Path,
    *,
    current: Mapping[str, Any],
    cursor: Mapping[str, Any],
    budget: _EvidenceReadBudget,
) -> tuple[
    tuple[tuple[Mapping[str, Any], Mapping[str, Any]], ...],
    Mapping[str, tuple[Mapping[str, Any], Mapping[str, Any]]],
]:
    pointer: Mapping[str, Any] | None = mark_chain._validate_pointer(dict(current))
    target = mark_chain._validate_pointer(dict(cursor))
    newest_first: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    seen: set[str] = set()
    while pointer is not None:
        observation_id = str(pointer["observation_id"])
        if observation_id in seen:
            raise EvidenceGenerationDrift(
                "selector evidence mark chain contains a cycle"
            )
        seen.add(observation_id)
        budget.add_pointer(pointer, label="selector mark observation")
        observation = lifecycle._load_mark_observation(mark_root, pointer)
        newest_first.append((copy.deepcopy(dict(pointer)), observation))
        if pointer == target:
            break
        previous = observation.get("previous")
        pointer = (
            None
            if previous is None
            else mark_chain._validate_pointer(previous)
        )
    else:
        raise EvidenceGenerationDrift(
            "selector evidence mark cursor is not on its authenticated chain"
        )
    if newest_first[-1][0] != target:
        raise EvidenceGenerationDrift(
            "selector evidence mark cursor is not on its authenticated chain"
        )
    ordered = tuple(reversed(newest_first))
    by_pointer = {
        canonical_bytes(pointer).decode("utf-8"): (pointer, observation)
        for pointer, observation in ordered
    }
    if len(by_pointer) != len(ordered):
        raise EvidenceGenerationDrift(
            "selector evidence mark chain repeats a pointer"
        )
    return ordered, by_pointer


def _validate_selected_enrollment_source(
    *,
    enrollment: Mapping[str, Any],
    plan_id: str,
    mark_chain_rows: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    mark_by_pointer: Mapping[
        str, tuple[Mapping[str, Any], Mapping[str, Any]]
    ],
    latest: Mapping[str, Any],
) -> None:
    payload = enrollment["payload"]
    entry_pointer = mark_chain._validate_pointer(payload["mark_observation"])
    entry_key = canonical_bytes(entry_pointer).decode("utf-8")
    entry_pair = mark_by_pointer.get(entry_key)
    if entry_pair is None:
        raise EvidenceGenerationDrift(
            "selector enrollment mark is outside the authenticated producer chain"
        )
    entry_observation = entry_pair[1]
    entry_row = lifecycle._row_for_plan(entry_observation, plan_id)
    if (
        entry_observation.get("session_date")
        != enrollment["event_session_date"]
        or lifecycle._plan_from_mark_row(entry_row) != payload["plan"]
        or entry_row.get("contract") != payload["contract"]
        or entry_row.get("quote_status") != "available"
        or entry_row["plan"].get("phase") not in lifecycle.POST_TRIGGER_PHASES
        or payload["shadow_entry_mark"]
        != lifecycle._shadow_mark(
            entry_row,
            entry_pointer,
            basis="first_fresh_post_trigger_trade_paired_mid",
        )
    ):
        raise EvidenceGenerationDrift(
            f"selector enrollment source binding drifted for {plan_id}"
        )

    entry_index = next(
        (
            index
            for index, (pointer, _observation) in enumerate(mark_chain_rows)
            if pointer == entry_pointer
        ),
        None,
    )
    if entry_index is None:
        raise EvidenceGenerationDrift(
            "selector enrollment mark is outside the authenticated producer chain"
        )
    enrolled_identity = lifecycle._stable_plan_identity(payload["plan"])
    sessions: dict[str, Mapping[str, Any]] = {}
    contract_drift = False
    plan_identity_drift = False
    for pointer, observation in mark_chain_rows[entry_index:]:
        row = lifecycle._optional_row_for_plan(observation, plan_id)
        if row is None:
            continue
        row_contract = row.get("contract")
        if isinstance(row_contract, Mapping) and row_contract != payload["contract"]:
            contract_drift = True
        identity_matches = (
            lifecycle._stable_plan_identity(row.get("plan")) == enrolled_identity
        )
        if not identity_matches:
            plan_identity_drift = True
        plan = row.get("plan")
        if (
            isinstance(plan, Mapping)
            and identity_matches
            and plan.get("phase") in lifecycle.POST_TRIGGER_PHASES
            and row.get("quote_status") == "available"
            and isinstance(row.get("quote"), Mapping)
            and row_contract == payload["contract"]
        ):
            sessions[str(observation["session_date"])] = copy.deepcopy(dict(pointer))
    if (
        latest.get("contract_occ_symbol") != payload["contract"]["occ_symbol"]
        or latest.get("contract_drift") is not contract_drift
        or latest.get("plan_identity_drift") is not plan_identity_drift
        or latest.get("sessions") != sessions
    ):
        raise EvidenceGenerationDrift(
            f"selector latest mark source binding drifted for {plan_id}"
        )


def _build_evidence_snapshot(
    inputs: EvidenceInputs,
    *,
    candidates: Sequence[Mapping[str, Any]] | None = None,
    session_dates: frozenset[str] | None = None,
    _captured_state: Mapping[str, Any] | None = None,
) -> EvidenceSnapshot:
    episode_ids, contract_keys, occ_to_contract, sessions = _evidence_scope(
        candidates, session_dates=session_dates
    )
    (
        w1a_head,
        w1a_audit,
        w1a_references,
        w1a_root_path_sha256,
        by_episode,
        w1a_error,
    ) = _w1a_snapshot(
        inputs.w1a_receipt_root,
        episode_ids=episode_ids,
    )
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
            current_state = lifecycle._load_state(lifecycle_root)
            if current_state is None:
                _fail("lifecycle state is absent")
            state = (
                current_state
                if _captured_state is None
                else lifecycle._validate_state_shape(dict(_captured_state))
            )
            if not candidates and state["enrollments"]:
                raise EvidenceGenerationDrift(
                    "selector evidence generation lacks a manifested candidate scope"
                )
            if set(state["latest_marks"]) != (
                set(state["enrollments"]) - set(state["terminals"])
            ):
                raise EvidenceGenerationDrift(
                    "selector lifecycle state lacks an exact open-plan index"
                )
            budget = _EvidenceReadBudget()
            state_body = canonical_bytes(state)
            budget.add_body(state_body, label="selector lifecycle state")
            event_pointers = [
                state["activation"],
                *state["enrollments"].values(),
                *state["terminals"].values(),
            ]
            unique_event_pointers = {
                canonical_bytes(pointer).decode("utf-8"): pointer
                for pointer in event_pointers
            }
            for pointer in unique_event_pointers.values():
                budget.add_pointer(pointer, label="selector lifecycle event")
            if (
                len(state.get("enrollments", {}))
                + len(state.get("terminals", {}))
                + len(state.get("latest_marks", {}))
                > MAX_EVIDENCE_SNAPSHOT_RECORDS
                or len(state_body) > MAX_EVIDENCE_SNAPSHOT_BYTES
            ):
                _fail("selector lifecycle snapshot exceeds its bounded index")
            lifecycle._validate_event_chain(lifecycle_root, state)
            budget.add_pointer(
                state["activation"], label="selector lifecycle activation"
            )
            lifecycle._validate_activation_boundary_against_state(
                lifecycle_root, state
            )
            activation = lifecycle._load_event(lifecycle_root, state["activation"])
            activation_mark = mark_chain._validate_pointer(
                activation["payload"]["mark_boundary"]
            )
            mark_chain_rows, mark_by_pointer = _bounded_mark_chain(
                mark_root,
                current=state["mark_cursor"],
                cursor=activation_mark,
                budget=budget,
            )
            snapshot_bytes = len(state_body)
            enrollments: dict[
                tuple[str, str, str, str],
                list[tuple[str, Mapping[str, Any], Mapping[str, Any]]],
            ] = {}
            for plan_id, terminal_pointer in state["terminals"].items():
                budget.add_pointer(
                    terminal_pointer, label="selector terminal lifecycle event"
                )
                terminal = lifecycle._load_event(lifecycle_root, terminal_pointer)
                terminal_key = _lifecycle_contract_key(terminal["payload"]["contract"])
                if terminal_key in contract_keys:
                    enrollments.setdefault(terminal_key, []).append(
                        (
                            plan_id,
                            copy.deepcopy(terminal),
                            copy.deepcopy(terminal_pointer),
                        )
                    )

            selected_open_plans = [
                plan_id
                for plan_id, latest in state["latest_marks"].items()
                if latest.get("contract_occ_symbol") in occ_to_contract
            ]
            if len(selected_open_plans) > MAX_CANDIDATES_PER_MANIFEST * 2:
                raise EvidenceGenerationDrift(
                    "selector evidence scope contains too many matching open plans"
                )
            rows: dict[
                tuple[str, str],
                tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]],
            ] = {}
            for plan_id in selected_open_plans:
                pointer = state["enrollments"][plan_id]
                budget.add_pointer(pointer, label="selector scoped enrollment")
                enrollment = lifecycle._load_enrollment(
                    lifecycle_root, pointer, plan_id
                )
                snapshot_bytes += len(canonical_bytes(enrollment))
                if snapshot_bytes > MAX_EVIDENCE_SNAPSHOT_BYTES:
                    _fail("selector evidence snapshot exceeds its aggregate byte bound")
                key = _lifecycle_contract_key(enrollment["payload"]["contract"])
                if key not in contract_keys:
                    raise EvidenceGenerationDrift(
                        "selector lifecycle OCC index aliases another contract"
                    )
                latest = state["latest_marks"][plan_id]
                _validate_selected_enrollment_source(
                    enrollment=enrollment,
                    plan_id=plan_id,
                    mark_chain_rows=mark_chain_rows,
                    mark_by_pointer=mark_by_pointer,
                    latest=latest,
                )
                enrollments.setdefault(key, []).append(
                    (
                        plan_id,
                        copy.deepcopy(enrollment),
                        copy.deepcopy(pointer),
                    )
                )
                for session_date in sessions:
                    session_pointer = latest.get("sessions", {}).get(session_date)
                    if session_pointer is None:
                        continue
                    pointer_key = canonical_bytes(session_pointer).decode("utf-8")
                    pair = mark_by_pointer.get(pointer_key)
                    if pair is None:
                        raise EvidenceGenerationDrift(
                            "selector scoped mark is outside its authenticated chain"
                        )
                    loaded_pointer, observation = pair
                    row = lifecycle._row_for_plan(observation, plan_id)
                    row_key = (plan_id, session_date)
                    if row_key in rows:
                        _fail("lifecycle snapshot repeats a plan/session mark")
                    rows[row_key] = (
                        copy.deepcopy(loaded_pointer),
                        copy.deepcopy(observation),
                        copy.deepcopy(row),
                    )
            # Re-read the mutable state only after all referenced immutable
            # evidence validated under the lifecycle lock. Any changed HEAD is
            # a concurrent snapshot and must be retried, never mixed.
            if (
                (
                    _captured_state is None
                    and lifecycle._load_state(lifecycle_root) != state
                )
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
    except (OSError, ValueError, KeyError, TypeError, SparseSelectorError) as exc:
        raise EvidenceGenerationDrift(
            "selector lifecycle evidence generation is invalid or drifted"
        ) from exc


def _evidence_snapshot_from_generation(
    generation: Mapping[str, Any],
    inputs: EvidenceInputs,
    *,
    root: Path,
    candidates: Sequence[Mapping[str, Any]],
    session_dates: frozenset[str],
    planned_by_key: Mapping[str, PlannedObject] | None = None,
    generation_already_validated: bool = False,
    manifest_cache: _PointerObjectCache | None = None,
    source_cache: _PointerObjectCache | None = None,
    w1a_cache: _W1APublicationCache | None = None,
) -> EvidenceSnapshot:
    """Rebuild one captured generation from exact immutable producer bytes."""

    clean_generation = (
        generation
        if generation_already_validated
        else validate_runtime_object(
            generation, label="captured selector evidence generation"
        )
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
            if source_cache is None:
                source_value = _load_pointer(
                    root,
                    source_pointer,
                    label="captured selector W1A source receipt",
                )
            else:
                source_value, _source_body = _load_pointer_cached(
                    root,
                    source_pointer,
                    label="captured selector W1A source receipt",
                    cache=source_cache,
                )
        else:
            if source_item.pointer != source_pointer:
                _fail("captured selector W1A source pointer differs from planned bytes")
            source_value = source_item.value
        if manifest_cache is None:
            manifest = _load_pointer(
                root,
                clean_generation["settled_manifest"],
                label="captured selector W1A settled manifest",
            )
        else:
            manifest, _manifest_body = _load_pointer_cached(
                root,
                clean_generation["settled_manifest"],
                label="captured selector W1A settled manifest",
                cache=manifest_cache,
            )
        candidate_rows = [
            (
                copy.deepcopy(dict(pointer)),
                _load_pointer(root, pointer, label="captured W1A manifested candidate"),
            )
            for pointer in manifest["candidates"]
        ]
        if [candidate for _pointer, candidate in candidate_rows] != list(candidates):
            _fail("captured selector W1A candidates differ from replay scope")
        publication = _authenticate_historical_w1a_source_cached(
            source_pointer,
            source_value,
            receipt_root=Path(inputs.w1a_receipt_root),
            manifest=manifest,
            candidate_rows=candidate_rows,
            cache=w1a_cache,
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
        episode_ids, _contracts, _occ, _sessions = _evidence_scope(
            candidates, session_dates=session_dates
        )
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for reference in w1a_references:
            owner = reference["owner"]
            if (
                owner["schema"] == "options.signal_episode/v1"
                and owner["id"] in episode_ids
            ):
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
    if inputs.mark_root is None or inputs.lifecycle_root is None:
        _fail("captured selector lifecycle generation lacks trusted producer roots")
    replay_inputs = EvidenceInputs(
        w1a_receipt_root=None,
        mark_root=inputs.mark_root,
        lifecycle_root=inputs.lifecycle_root,
    )
    snapshot = _build_evidence_snapshot(
        replay_inputs,
        candidates=candidates,
        session_dates=session_dates,
        _captured_state=state,
    )
    if (
        snapshot.lifecycle_state != state
        or snapshot.mark_error != clean_generation["mark_error"]
        or snapshot.lifecycle_error != clean_generation["lifecycle_error"]
    ):
        _fail("captured selector evidence generation cannot be replayed exactly")
    return EvidenceSnapshot(
        w1a_head=w1a_head,
        w1a_audit=w1a_audit,
        w1a_references=w1a_references,
        w1a_root_path_sha256=w1a_root_path_sha256,
        w1a_by_episode=by_episode,
        lifecycle_state=snapshot.lifecycle_state,
        enrollments_by_contract=snapshot.enrollments_by_contract,
        mark_rows_by_plan_session=snapshot.mark_rows_by_plan_session,
        w1a_error=w1a_error,
        mark_error=snapshot.mark_error,
        lifecycle_error=snapshot.lifecycle_error,
        lifecycle_publishable=snapshot.lifecycle_publishable,
        lifecycle_unpublishable_contracts=(
            snapshot.lifecycle_unpublishable_contracts
        ),
        mark_unpublishable_plan_sessions=(
            snapshot.mark_unpublishable_plan_sessions
        ),
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
        # Episode-owned W1A receipts retain their owner contract phase.  The
        # candidate's campaign phase is independently prospective and must not
        # be substituted for this literal owner value.
        or owner["evidence_phase"] != "decision_time_actual_output"
        or query["subject"] != expected_subject
        or query["identity_config_sha256"] != identity["identity_config_sha256"]
        or query["event_time"] != episode["event_time"]
        or query["as_known_at"] != episode["available_at"]
        or query["mode"] != "operational_pit"
        or query["fallback_policy"] != "exact_no_fallback"
        or reference["authority"]
        != dict(context_bridge.market_memory.AUTHORITY)
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
        _source_rfc3339(
            observation.get("observed_at_utc"), label="mark observation clock"
        )
        _source_rfc3339(row["quote"].get("quote_ts_utc"), label="mark quote clock")
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
            _source_rfc3339(
                observation.get("observed_at_utc"), label="mark observation clock"
            )
            _source_rfc3339(
                row["quote"].get("quote_ts_utc"), label="mark quote clock"
            )
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
    evidence_session_date: str,
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
        evidence_snapshot = _build_evidence_snapshot(
            evidence_inputs,
            candidates=tuple(candidate for _pointer, candidate in candidate_rows),
            session_dates=frozenset({evidence_session_date}),
        )
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
                quote_at = _source_rfc3339(
                    mark_object.value["selected_plan_row"]["quote"]["quote_ts_utc"],
                    label="selected mark quote clock",
                )
                observed_at = _source_rfc3339(
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


def _empty_evidence_audit_index(domain: str) -> dict[str, Any]:
    if domain not in {
        EVIDENCE_EVENT_SEEN_DOMAIN,
        EVIDENCE_EVENT_ENROLLMENT_DOMAIN,
        EVIDENCE_EVENT_TERMINAL_DOMAIN,
        EVIDENCE_STATE_ENROLLMENT_DOMAIN,
        EVIDENCE_STATE_TERMINAL_DOMAIN,
        EVIDENCE_MARK_SEEN_DOMAIN,
        EVIDENCE_STATE_LATEST_DOMAIN,
        EVIDENCE_DERIVED_LATEST_DOMAIN,
        EVIDENCE_LEDGER_ROW_DOMAIN,
        EVIDENCE_LEDGER_TERMINAL_DOMAIN,
        EVIDENCE_BOUNDARY_DOMAIN,
    }:
        _fail("selector evidence audit index domain is foreign")
    return private_auth_dict.sharded_root_receipt(
        domain=domain, root=None, entry_count=0
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
    if len(ordered) + 1 > MAX_SOURCE_OBJECTS_PER_CYCLE:
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
        "objects": [item.receipt for item in ordered],
        "next_head": copy.deepcopy(dict(next_head)),
    }
    intent["intent_sha256"] = _content_id("", intent, field="intent_sha256")
    if (
        len(canonical_bytes(intent)) > MAX_SOURCE_INTENT_BYTES
        or _transition_footprint_bytes(intent, ordered) > MAX_SOURCE_INTENT_BYTES
    ):
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
        "evidence_high_water": (
            None if head is None else copy.deepcopy(head["evidence_high_water"])
        ),
        "w1a_publication_high_water": (
            None
            if head is None
            else copy.deepcopy(head["w1a_publication_high_water"])
        ),
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
        "digests": dict(DIGESTS),
        "authority": dict(FALSE_AUTHORITY),
    }
    next_head["head_id"] = _content_id("ossh_", next_head, field="head_id")
    return validate_runtime_object(next_head, label="selector source HEAD")


def _read_lifecycle_state_bytes(
    lifecycle_lane: _SelectorLane,
) -> tuple[bytes, dict[str, Any]]:
    body = _read_anchored_file(
        lifecycle_lane,
        "current.json",
        limit=2 * 1024 * 1024,
        label="selector lifecycle current state",
    )
    if body is None or len(body) > 2 * 1024 * 1024:
        _fail("selector lifecycle current state is absent or oversized")
    value = strict_json(body, label="selector lifecycle current state")
    if (
        not isinstance(value, dict)
        or lifecycle._canonical_json_bytes(value) != body
    ):
        _fail("selector lifecycle current state is not canonical")
    try:
        state = lifecycle._validate_state_shape(value)
    except (TypeError, ValueError, KeyError) as exc:
        raise EvidenceGenerationDrift(
            "selector lifecycle current state is malformed"
        ) from exc
    return body, state


def _load_anchored_frozen_mark_observation(
    lane: _SelectorLane, pointer: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        checked = mark_chain._validate_pointer(dict(pointer))
        body = _read_anchored_file(
            lane,
            checked["key"],
            limit=2 * 1024 * 1024,
            label="selector frozen mark observation",
        )
        if (
            body is None
            or len(body) != checked["bytes"]
            or _sha256(body) != checked["sha256"]
        ):
            _fail("selector frozen mark observation receipt drifted")
        value = strict_json(body, label="selector frozen mark observation")
        if (
            not isinstance(value, Mapping)
            or mark_chain._canonical_json_bytes(dict(value)) != body
        ):
            _fail("selector frozen mark observation is not canonical")
        return _validate_frozen_mark_observation(value, checked)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        if isinstance(exc, SparseSelectorError):
            raise
        raise EvidenceGenerationDrift(
            "selector frozen mark observation is unavailable"
        ) from exc


def _load_anchored_frozen_lifecycle_event(
    lane: _SelectorLane, pointer: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        checked = lifecycle._validate_event_pointer(dict(pointer))
        body = _read_anchored_file(
            lane,
            checked["key"],
            limit=2 * 1024 * 1024,
            label="selector frozen lifecycle event",
        )
        if (
            body is None
            or len(body) != checked["bytes"]
            or _sha256(body) != checked["sha256"]
        ):
            _fail("selector frozen lifecycle event receipt drifted")
        value = strict_json(body, label="selector frozen lifecycle event")
        if (
            not isinstance(value, Mapping)
            or lifecycle._canonical_json_bytes(dict(value)) != body
        ):
            _fail("selector frozen lifecycle event is not canonical")
        clean = _validate_frozen_lifecycle_event(value)
        if lifecycle._event_pointer(clean) != checked:
            _fail("selector frozen lifecycle event pointer drifted")
        return clean
    except (OSError, TypeError, ValueError, KeyError) as exc:
        if isinstance(exc, SparseSelectorError):
            raise
        raise EvidenceGenerationDrift(
            "selector frozen lifecycle event is unavailable"
        ) from exc


def _read_anchored_activation_boundary(lane: _SelectorLane) -> dict[str, Any]:
    body = _read_anchored_file(
        lane,
        "activation_boundary.json",
        limit=2 * 1024 * 1024,
        label="selector lifecycle activation boundary",
    )
    value = strict_json(body, label="selector lifecycle activation boundary")
    if (
        not isinstance(value, Mapping)
        or lifecycle._canonical_json_bytes(dict(value)) != body
    ):
        _fail("selector lifecycle activation boundary is not canonical")
    try:
        return lifecycle._validate_activation_boundary(dict(value))
    except (TypeError, ValueError, KeyError) as exc:
        raise EvidenceGenerationDrift(
            "selector lifecycle activation boundary is malformed"
        ) from exc


def _read_anchored_mark_head(lane: _SelectorLane) -> dict[str, Any]:
    body = _read_anchored_file(
        lane,
        "current.json",
        limit=2 * 1024 * 1024,
        label="selector live mark HEAD",
    )
    value = strict_json(body, label="selector live mark HEAD")
    if (
        not isinstance(value, Mapping)
        or set(value) != {"schema", "evidence"}
        or value.get("schema") != mark_chain.EVIDENCE_HEAD_SCHEMA
        or mark_chain._canonical_json_bytes(dict(value)) != body
    ):
        _fail("selector live mark HEAD is malformed")
    pointer = mark_chain._validate_pointer(value["evidence"])
    _load_anchored_frozen_mark_observation(lane, pointer)
    return pointer


def _read_anchored_ledger_receipt(lane: _SelectorLane) -> dict[str, Any]:
    # Ambient producer ledger path overrides are not part of the frozen contract.
    body = _read_anchored_file(
        lane,
        "canonical_ledger/receipt.json",
        limit=lifecycle.MAX_RECEIPT_BYTES,
        label="selector canonical ledger receipt",
    )
    value = strict_json(body, label="selector captured ledger receipt")
    if (
        not isinstance(value, Mapping)
        or lifecycle._canonical_json_bytes(dict(value)) != body
    ):
        _fail("selector captured ledger receipt is not canonical")
    receipt = lifecycle._validate_ledger_receipt(dict(value))
    ledger_metadata = _stat_anchored_file(
        lane,
        "canonical_ledger/ledger.jsonl",
        limit=lifecycle.MAX_LEDGER_BYTES,
        label="selector canonical ledger",
    )
    if ledger_metadata.st_size != int(receipt["bytes"]):
        _fail("selector canonical ledger size differs from its live receipt")
    return receipt


def _require_distinct_evidence_roots(mark_root: Path, lifecycle_root: Path) -> None:
    """Compatibility fence for the unfinished occurrence planner."""

    mark_root = _absolute_private_path(mark_root)
    lifecycle_root = _absolute_private_path(lifecycle_root)
    if (
        mark_root == lifecycle_root
        or mark_root in lifecycle_root.parents
        or lifecycle_root in mark_root.parents
    ):
        _fail("selector producer roots must be distinct and non-nested")
    mark_metadata = os.stat(mark_root, follow_symlinks=False)
    lifecycle_metadata = os.stat(lifecycle_root, follow_symlinks=False)
    if (mark_metadata.st_dev, mark_metadata.st_ino) == (
        lifecycle_metadata.st_dev,
        lifecycle_metadata.st_ino,
    ):
        _fail("selector producer roots must be distinct and non-nested")


def _verify_capture_source_prefixes(
    *,
    sources: _AnchoredEvidenceSources,
    state: Mapping[str, Any],
    expected_mark_head: Mapping[str, Any] | None = None,
    expected_ledger_receipt: Mapping[str, Any] | None = None,
    prior_snapshot: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Authenticate the pinned cursors without scanning their lifetime chains."""

    try:
        _load_anchored_frozen_lifecycle_event(
            sources.lifecycle, state["lifecycle_head"]
        )
        _load_anchored_frozen_mark_observation(sources.mark, state["mark_cursor"])
        activation_boundary = _read_anchored_activation_boundary(
            sources.lifecycle
        )
        if prior_snapshot is None:
            activation_event = _load_anchored_frozen_lifecycle_event(
                sources.lifecycle, state["activation"]
            )
            activation_mark = _load_anchored_frozen_mark_observation(
                sources.mark, activation_boundary["mark_boundary"]
            )
            if (
                activation_event
                != _frozen_activation_event(activation_boundary, activation_mark)
                or state["activation"] != lifecycle._event_pointer(activation_event)
            ):
                _fail("selector lifecycle activation occurrence drifted")
        elif (
            activation_boundary != prior_snapshot["activation_boundary"]
            or state["activation"]
            != prior_snapshot["lifecycle_state"]["activation"]
        ):
            _fail("selector incremental activation receipt drifted")
        live_mark_head = _read_anchored_mark_head(sources.mark)
        live_ledger_receipt = _read_anchored_ledger_receipt(sources.lifecycle)
        if (
            int(live_ledger_receipt["bytes"])
            < int(state["ledger_cursor"]["bytes"])
            or int(live_ledger_receipt["row_count"])
            < int(state["ledger_cursor"]["row_count"])
        ):
            _fail("selector captured ledger receipt precedes the lifecycle cursor")
        if expected_mark_head is not None and live_mark_head != expected_mark_head:
            raise EvidenceGenerationDrift(
                "selector live mark head changed before PIN authority"
            )
        if (
            expected_ledger_receipt is not None
            and live_ledger_receipt != expected_ledger_receipt
        ):
            raise EvidenceGenerationDrift(
                "selector live ledger receipt changed before PIN authority"
            )
        return (
            copy.deepcopy(live_mark_head),
            copy.deepcopy(live_ledger_receipt),
            copy.deepcopy(activation_boundary),
        )
    except (OSError, TypeError, ValueError, KeyError) as exc:
        raise EvidenceGenerationDrift(
            "selector evidence capture source cursors are not authentic prefixes"
        ) from exc


def _anchored_mark_chain_contains(
    lane: _SelectorLane,
    live_head: Mapping[str, Any],
    required: Sequence[Mapping[str, Any]],
) -> None:
    """Prove each required pointer occurs in the captured live mark chain."""

    remaining = {
        canonical_bytes(mark_chain._validate_pointer(dict(pointer)))
        for pointer in required
    }
    pointer: dict[str, Any] | None = mark_chain._validate_pointer(dict(live_head))
    seen: set[str] = set()
    for _ in range(lifecycle.MAX_CHAIN_DEPTH):
        if pointer is None:
            break
        remaining.discard(canonical_bytes(pointer))
        observation_id = str(pointer["observation_id"])
        if observation_id in seen:
            _fail("selector captured live mark chain contains a cycle")
        seen.add(observation_id)
        observation = _load_anchored_frozen_mark_observation(lane, pointer)
        if not remaining:
            return
        previous = observation.get("previous")
        pointer = (
            None
            if previous is None
            else mark_chain._validate_pointer(previous)
        )
    _fail("selector captured live mark chain omitted a required ancestor")


def _anchored_ledger_extends(
    lane: _SelectorLane, prior_receipt: Mapping[str, Any]
) -> None:
    """Prove the live canonical ledger exact-prefix-extends a prior capture."""

    checked = lifecycle._validate_ledger_receipt(dict(prior_receipt))
    body = _read_anchored_file(
        lane,
        "canonical_ledger/ledger.jsonl",
        limit=lifecycle.MAX_LEDGER_BYTES,
        label="selector canonical ledger",
    )
    size = int(checked["bytes"])
    if (
        len(body) < size
        or _sha256(body[:size]) != checked["sha256"]
        or (body[:size] and not body[:size].endswith(b"\n"))
    ):
        _fail("selector canonical ledger rolled back or forked before PIN")


def _incremental_target_descends(
    lifecycle_root: Path,
    *,
    prior_state_id: str,
    target_state_id: str,
) -> None:
    """Prove a pinned target is on the immutable forward-boundary suffix."""

    cursor = prior_state_id
    seen: set[str] = set()
    for _ in range(lifecycle.MAX_CHAIN_DEPTH):
        if cursor == target_state_id:
            return
        if cursor in seen:
            break
        seen.add(cursor)
        boundary, _receipt = _load_exact_advance_boundary(
            lifecycle_root, cursor
        )
        cursor = boundary["candidate_state_id"]
    _fail("selector incremental target is not a descendant of prior COMPLETE")


def _load_frozen_mark_observation(
    root: Path, pointer: Mapping[str, Any]
) -> dict[str, Any]:
    active = _ACTIVE_EVIDENCE_SOURCES.get()
    if active is not None:
        if _absolute_private_path(root) != active.mark.root:
            _fail("selector frozen mark read escaped its anchored root")
        return _load_anchored_frozen_mark_observation(active.mark, pointer)
    try:
        checked = mark_chain._validate_pointer(dict(pointer))
        path = mark_chain._private_observation_path(
            root, checked, create_parents=False
        )
        body = mark_chain._read_private_file(path)
        if (
            body is None
            or len(body) != checked["bytes"]
            or _sha256(body) != checked["sha256"]
        ):
            _fail("selector frozen mark observation receipt drifted")
        value = strict_json(body, label="selector frozen mark observation")
        if (
            not isinstance(value, Mapping)
            or mark_chain._canonical_json_bytes(dict(value)) != body
        ):
            _fail("selector frozen mark observation is not canonical")
        return _validate_frozen_mark_observation(value, checked)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        if isinstance(exc, SparseSelectorError):
            raise
        raise EvidenceGenerationDrift(
            "selector frozen mark observation is unavailable"
        ) from exc


def _load_frozen_lifecycle_event(
    root: Path, pointer: Mapping[str, Any]
) -> dict[str, Any]:
    active = _ACTIVE_EVIDENCE_SOURCES.get()
    if active is not None:
        if _absolute_private_path(root) != active.lifecycle.root:
            _fail("selector frozen lifecycle read escaped its anchored root")
        return _load_anchored_frozen_lifecycle_event(active.lifecycle, pointer)
    try:
        checked = lifecycle._validate_event_pointer(dict(pointer))
        body = mark_chain._read_private_file(
            lifecycle._event_path(root, checked, create_parents=False)
        )
        if (
            body is None
            or len(body) != checked["bytes"]
            or _sha256(body) != checked["sha256"]
        ):
            _fail("selector frozen lifecycle event receipt drifted")
        value = strict_json(body, label="selector frozen lifecycle event")
        if (
            not isinstance(value, Mapping)
            or lifecycle._canonical_json_bytes(dict(value)) != body
        ):
            _fail("selector frozen lifecycle event is not canonical")
        clean = _validate_frozen_lifecycle_event(value)
        if lifecycle._event_pointer(clean) != checked:
            _fail("selector frozen lifecycle event pointer drifted")
        return clean
    except (OSError, TypeError, ValueError, KeyError) as exc:
        if isinstance(exc, SparseSelectorError):
            raise
        raise EvidenceGenerationDrift(
            "selector frozen lifecycle event is unavailable"
        ) from exc


def _frozen_lifecycle_event(
    *,
    kind: str,
    session_date: str,
    payload: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": lifecycle.EVENT_SCHEMA,
        "event_id": "",
        "event_kind": kind,
        "event_session_date": session_date,
        "storage": {
            "visibility": "host_private",
            "public_discovery": False,
            "public_redistribution": False,
        },
        "previous": None if previous is None else copy.deepcopy(dict(previous)),
        "payload": copy.deepcopy(dict(payload)),
        "limitations": lifecycle._limitations_block(),
        "authority": lifecycle._authority_block(),
    }
    identity = copy.deepcopy(value)
    identity.pop("event_id")
    value["event_id"] = (
        "posle_" + _sha256(lifecycle._canonical_json_bytes(identity))
    )
    return _validate_frozen_lifecycle_event(value)


def _frozen_activation_event(
    boundary: Mapping[str, Any], observation: Mapping[str, Any]
) -> dict[str, Any]:
    if observation.get("observed_at_utc") != boundary["mark_boundary_observed_at_utc"]:
        _fail("selector activation boundary mark clock drifted")
    return _frozen_lifecycle_event(
        kind="activation_boundary",
        session_date=str(observation["session_date"]),
        previous=None,
        payload={
            "kind": "activation_boundary",
            "mark_boundary": copy.deepcopy(boundary["mark_boundary"]),
            "mark_boundary_observed_at_utc": boundary[
                "mark_boundary_observed_at_utc"
            ],
            "ledger_boundary": copy.deepcopy(boundary["ledger_boundary"]),
            "prospective_after_boundary": True,
        },
    )


def _frozen_enrollment_event(
    *,
    row: Mapping[str, Any],
    mark_pointer: Mapping[str, Any],
    observation: Mapping[str, Any],
    previous: Mapping[str, Any],
) -> dict[str, Any]:
    plan = lifecycle._plan_from_mark_row(dict(row))
    contract = row.get("contract")
    if plan["phase"] not in lifecycle.POST_TRIGGER_PHASES or not isinstance(
        contract, Mapping
    ):
        _fail("selector replay enrollment source is ineligible")
    return _frozen_lifecycle_event(
        kind="enrollment",
        session_date=str(observation["session_date"]),
        previous=previous,
        payload={
            "kind": "enrollment",
            "plan": plan,
            "contract": copy.deepcopy(dict(contract)),
            "mark_observation": copy.deepcopy(dict(mark_pointer)),
            "shadow_entry_mark": lifecycle._shadow_mark(
                dict(row),
                dict(mark_pointer),
                basis="first_fresh_post_trigger_trade_paired_mid",
            ),
            "position_assumed": False,
            "provider_observed_entry": False,
        },
    )


def _frozen_terminal_event(
    *,
    lifecycle_root: Path,
    mark_root: Path,
    plan_id: str,
    ledger_row: Mapping[str, Any],
    ledger_row_ordinal: int,
    ledger_receipt: Mapping[str, Any],
    enrollment_pointer: Mapping[str, Any],
    mark_chain_head: Mapping[str, Any],
    latest_state: Mapping[str, Any],
    previous: Mapping[str, Any],
    row_semantic_sha256: str | None = None,
) -> dict[str, Any]:
    enrollment = _load_frozen_lifecycle_event(lifecycle_root, enrollment_pointer)
    if (
        enrollment.get("event_kind") != "enrollment"
        or enrollment["payload"]["plan"]["id"] != plan_id
    ):
        _fail(f"selector replay enrollment pointer is wrong for {plan_id}")
    enrollment_payload = enrollment["payload"]
    close_date = str(ledger_row["close_date"])
    reason: str | None = None
    terminal_mark: dict[str, Any] | None = None
    if ledger_row["outcome"] == "NO_ENTRY":
        reason = "CANONICAL_NO_ENTRY"
    elif date.fromisoformat(close_date) < date.fromisoformat(
        str(enrollment["event_session_date"])
    ):
        reason = "CANONICAL_CLOSE_PREDATES_ENROLLMENT"
    elif latest_state.get("plan_identity_drift") is True:
        reason = "PLAN_IDENTITY_DRIFT"
    elif latest_state.get("contract_drift") is True:
        reason = "CONTRACT_DRIFT"
    else:
        sessions = latest_state.get("sessions")
        mark_pointer = sessions.get(close_date) if isinstance(sessions, Mapping) else None
        if mark_pointer is None:
            reason = "NO_SAME_SESSION_ADMITTED_MARK"
        else:
            observation = _load_frozen_mark_observation(mark_root, mark_pointer)
            row = lifecycle._row_for_plan(observation, plan_id)
            if lifecycle._stable_plan_identity(row.get("plan")) != (
                lifecycle._stable_plan_identity(enrollment_payload["plan"])
            ):
                reason = "PLAN_IDENTITY_DRIFT"
            elif row.get("contract") != enrollment_payload["contract"]:
                reason = "CONTRACT_DRIFT"
            elif observation.get("session_date") != close_date:
                _fail("selector replay terminal mark session drifted")
            else:
                terminal_mark = lifecycle._shadow_mark(
                    row,
                    mark_pointer,
                    basis="latest_admitted_same_session_trade_paired_mid",
                )
    if terminal_mark is None:
        terminal_wrapper = {"status": "unavailable", "reason": reason, "mark": None}
        shadow_return = {
            "status": "unavailable",
            "basis": "shadow_mid_to_mid_research_only",
            "shadow_mark_to_mark_return_pct": None,
            "unavailable_reason": reason,
            "trade_pnl": False,
        }
    else:
        entry = Decimal(str(enrollment_payload["shadow_entry_mark"]["mid"]))
        terminal = Decimal(str(terminal_mark["mid"]))
        if entry <= 0 or terminal <= 0:
            _fail("selector replay terminal mark is non-positive")
        value = ((terminal / entry) - Decimal("1")) * Decimal("100")
        terminal_wrapper = {"status": "available", "reason": None, "mark": terminal_mark}
        shadow_return = {
            "status": "available",
            "basis": "shadow_mid_to_mid_research_only",
            "shadow_mark_to_mark_return_pct": float(
                value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            ),
            "unavailable_reason": None,
            "trade_pnl": False,
        }
    canonical_close = {
        "schema": "prophet.ledger/v1",
        "plan_id": plan_id,
        "close_date": close_date,
        "outcome": ledger_row["outcome"],
        "asof": ledger_row["asof"],
        "row_ordinal": ledger_row_ordinal,
        "row_semantic_sha256": (
            row_semantic_sha256
            or _sha256(lifecycle._canonical_json_bytes(dict(ledger_row)))
        ),
        "ledger_receipt": copy.deepcopy(dict(ledger_receipt)),
        "source_option_result_pct_was_null": True,
    }
    return _frozen_lifecycle_event(
        kind="terminal",
        session_date=close_date,
        previous=previous,
        payload={
            "kind": "terminal",
            "plan_id": plan_id,
            "contract": copy.deepcopy(enrollment_payload["contract"]),
            "enrollment_event": copy.deepcopy(dict(enrollment_pointer)),
            "mark_chain_head": copy.deepcopy(dict(mark_chain_head)),
            "shadow_entry_mark": copy.deepcopy(enrollment_payload["shadow_entry_mark"]),
            "canonical_close": canonical_close,
            "terminal_mark": terminal_wrapper,
            "shadow_return": shadow_return,
            "position_assumed": False,
            "provider_observed_exit": False,
        },
    )


def _make_evidence_source_snapshot(
    *,
    state: Mapping[str, Any],
    live_mark_head: Mapping[str, Any],
    live_ledger_receipt: Mapping[str, Any],
    activation_boundary: Mapping[str, Any],
    producer_roots: Mapping[str, Mapping[str, str]],
    captured_at: str,
) -> PlannedObject:
    value: dict[str, Any] = {
        "schema": "options.sparse_selector_evidence_source_snapshot/v1",
        "snapshot_id": "",
        "captured_at": captured_at,
        "state_sha256": _sha256(canonical_bytes(state)),
        "producer_contract": copy.deepcopy(PRODUCER_CONTRACT),
        "producer_roots": copy.deepcopy(dict(producer_roots)),
        "activation_boundary": copy.deepcopy(dict(activation_boundary)),
        "lifecycle_state": copy.deepcopy(dict(state)),
        "live_mark_head": copy.deepcopy(dict(live_mark_head)),
        "live_ledger_receipt": copy.deepcopy(dict(live_ledger_receipt)),
        "authority": dict(FALSE_AUTHORITY),
    }
    value["snapshot_id"] = _content_id("osess_", value, field="snapshot_id")
    clean = validate_runtime_object(value, label="selector evidence source snapshot")
    return PlannedObject(
        key=f"{EVIDENCE_AUDIT_NAMESPACE}/{clean['snapshot_id']}.json",
        value=clean,
    )


def _make_evidence_replay_state(
    *, snapshot: Mapping[str, Any], state: Mapping[str, Any]
) -> PlannedObject:
    checked_state = lifecycle._validate_state_shape(dict(state))
    value: dict[str, Any] = {
        "schema": "options.sparse_selector_evidence_replay_state/v1",
        "replay_id": "",
        "snapshot": copy.deepcopy(dict(snapshot)),
        "producer_contract": copy.deepcopy(PRODUCER_CONTRACT),
        "state_id": checked_state["state_id"],
        "state": checked_state,
        "authority": dict(FALSE_AUTHORITY),
    }
    value["replay_id"] = _content_id("osers_", value, field="replay_id")
    clean = validate_runtime_object(value, label="selector evidence replay state")
    return PlannedObject(
        key=f"{EVIDENCE_AUDIT_NAMESPACE}/{clean['replay_id']}.json",
        value=clean,
    )


def _load_evidence_replay_state(
    root: Path, pointer: Mapping[str, Any], *, snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    value = _load_pointer(root, pointer, label="selector evidence replay state")
    clean = validate_runtime_object(value, label="selector evidence replay state")
    if (
        clean.get("schema")
        != "options.sparse_selector_evidence_replay_state/v1"
        or pointer["key"]
        != f"{EVIDENCE_AUDIT_NAMESPACE}/{clean['replay_id']}.json"
        or clean["snapshot"] != dict(snapshot)
    ):
        _fail("selector evidence replay state escaped its high-water")
    return clean


def _evidence_auth_nodes(
    root: Path,
    *,
    prior: Mapping[str, Any],
    domain: str,
    entries: Sequence[tuple[Any, Any]],
) -> tuple[dict[str, Any], tuple[PlannedObject, ...]]:
    def load_node(pointer: Mapping[str, Any]) -> Mapping[str, Any]:
        value = _load_pointer(root, pointer, label="selector evidence auth node")
        return private_auth_dict.validate_node(value, domain=domain)

    try:
        receipt, nodes = private_auth_dict.sharded_insert_many(
            prior,
            entries,
            domain=domain,
            load_node=load_node,
            cache=private_auth_dict.ShardedLookupCache.empty(domain),
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc
    planned = tuple(
        PlannedObject(
            key=f"{private_auth_dict.NAMESPACE}/{node['node_id']}.json",
            value=node,
        )
        for node in nodes
    )
    return receipt, planned


def _activation_boundary_receipt(boundary: Mapping[str, Any]) -> dict[str, Any]:
    checked = lifecycle._validate_activation_boundary(dict(boundary))
    body = lifecycle._canonical_json_bytes(checked)
    return {
        "kind": "activation",
        "boundary_id": checked["boundary_id"],
        "sha256": _sha256(body),
        "bytes": len(body),
        "mark_boundary": copy.deepcopy(checked["mark_boundary"]),
        "ledger_boundary": copy.deepcopy(checked["ledger_boundary"]),
    }


def _load_exact_advance_boundary(
    lifecycle_root: Path, base_state_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    if re.fullmatch(r"posls_[a-f0-9]{64}", base_state_id) is None:
        _fail("selector replay base state id is malformed")
    key = f"advance_boundaries/{base_state_id}.json"
    active = _ACTIVE_EVIDENCE_SOURCES.get()
    if active is not None:
        if _absolute_private_path(lifecycle_root) != active.lifecycle.root:
            _fail("selector advance boundary read escaped its anchored root")
        body = _read_anchored_file(
            active.lifecycle,
            key,
            limit=2 * 1024 * 1024,
            required=False,
            label="selector replay advance boundary",
        )
    else:
        path = lifecycle_root / "advance_boundaries" / f"{base_state_id}.json"
        body = mark_chain._read_private_file(path, required=False)
    if body is None:
        _fail("selector replay advance boundary is missing before pinned state")
    value = strict_json(body, label="selector replay advance boundary")
    if (
        not isinstance(value, Mapping)
        or lifecycle._canonical_json_bytes(dict(value)) != body
    ):
        _fail("selector replay advance boundary is not canonical")
    try:
        boundary = lifecycle._validate_advance_boundary(dict(value))
    except (TypeError, ValueError, KeyError) as exc:
        raise SparseSelectorError(
            "selector replay advance boundary is malformed"
        ) from exc
    if boundary["base_state_id"] != base_state_id:
        _fail("selector replay advance boundary base drifted")
    receipt = {
        "kind": "advance",
        "boundary_id": boundary["boundary_id"],
        "base_state_id": boundary["base_state_id"],
        "candidate_state_id": boundary["candidate_state_id"],
        "sha256": _sha256(body),
        "bytes": len(body),
        "mark_boundary": copy.deepcopy(boundary["mark_boundary"]),
        "ledger_boundary": copy.deepcopy(boundary["ledger_boundary"]),
        "candidate_lifecycle_head": copy.deepcopy(
            boundary["candidate_lifecycle_head"]
        ),
        "event_count": len(boundary["event_pointers"]),
    }
    return boundary, receipt


def _load_boundary_from_receipt(
    lifecycle_root: Path, receipt: Mapping[str, Any]
) -> dict[str, Any]:
    boundary, exact = _load_exact_advance_boundary(
        lifecycle_root, str(receipt.get("base_state_id"))
    )
    if exact != dict(receipt):
        _fail("selector replay advance boundary receipt drifted")
    return boundary


def _fixed_new_mark_observations(
    mark_root: Path,
    current: Mapping[str, Any],
    cursor: Mapping[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    checked_current = mark_chain._validate_pointer(dict(current))
    checked_cursor = mark_chain._validate_pointer(dict(cursor))
    if checked_current == checked_cursor:
        _load_frozen_mark_observation(mark_root, checked_cursor)
        return []
    backwards: list[tuple[dict[str, Any], dict[str, Any]]] = []
    pointer: dict[str, Any] | None = checked_current
    seen: set[str] = set()
    for _ in range(lifecycle.MAX_CHAIN_DEPTH):
        if pointer is None:
            break
        if pointer == checked_cursor:
            _load_frozen_mark_observation(mark_root, checked_cursor)
            backwards.reverse()
            return backwards
        identity = str(pointer["observation_id"])
        if identity in seen:
            _fail("selector replay mark chain contains a cycle")
        seen.add(identity)
        observation = _load_frozen_mark_observation(mark_root, pointer)
        backwards.append((pointer, observation))
        previous = observation.get("previous")
        pointer = (
            None
            if previous is None
            else mark_chain._validate_pointer(previous)
        )
    _fail("selector replay mark cursor is not an ancestor of its boundary")


def _replay_high_water_object(
    parent: Mapping[str, Any], **updates: Any
) -> PlannedObject:
    value = copy.deepcopy(dict(parent))
    value.update(copy.deepcopy(updates))
    value["high_water_id"] = ""
    value["high_water_id"] = _content_id(
        "osehw_", value, field="high_water_id"
    )
    clean = validate_runtime_object(value, label="selector replay high-water")
    return PlannedObject(
        key=f"{EVIDENCE_AUDIT_NAMESPACE}/{clean['high_water_id']}.json",
        value=clean,
    )


def _replay_state_fields(replay: PlannedObject) -> dict[str, Any]:
    state = replay.value["state"]
    return {
        "replay_state": replay.pointer,
        "replay_state_id": state["state_id"],
        "replay_lifecycle_head": copy.deepcopy(state["lifecycle_head"]),
        "replay_mark_cursor": copy.deepcopy(state["mark_cursor"]),
        "replay_ledger_cursor": copy.deepcopy(state["ledger_cursor"]),
    }


def _replay_actual_event(
    lifecycle_root: Path,
    boundary: Mapping[str, Any],
    ordinal: int,
    expected: Mapping[str, Any],
) -> None:
    pointers = boundary["event_pointers"]
    if ordinal >= len(pointers):
        _fail("selector replay generated an orphan lifecycle event")
    pointer = pointers[ordinal]
    actual = _load_frozen_lifecycle_event(lifecycle_root, pointer)
    if actual != dict(expected) or lifecycle._event_pointer(dict(expected)) != pointer:
        _fail("selector replay lifecycle event differs from boundary order")


def _ledger_at_boundary(
    lifecycle_root: Path, receipt: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ledger_path, receipt_path = lifecycle._ledger_paths(
        lifecycle_root,
        ledger_path=None,
        ledger_receipt_path=None,
        create=False,
    )
    live_body, _live_rows, _live_receipt = lifecycle._read_ledger_snapshot(
        ledger_path, receipt_path
    )
    _prefix, rows, checked = lifecycle._ledger_snapshot_at_receipt(
        live_body, dict(receipt)
    )
    return [copy.deepcopy(row) for row in rows], copy.deepcopy(checked)


def _ledger_row_binding(row: Mapping[str, Any], ordinal: int) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "plan_id": str(row["id"]),
        "close_date": str(row["close_date"]),
        "outcome": str(row["outcome"]),
        "asof": str(row["asof"]),
        "option_result_pct": None,
        "row_semantic_sha256": _sha256(
            lifecycle._canonical_json_bytes(dict(row))
        ),
    }


def _evidence_auth_lookup(
    root: Path,
    receipt: Mapping[str, Any],
    *,
    domain: str,
    logical_key: Any,
) -> private_auth_dict.Lookup:
    def load_node(pointer: Mapping[str, Any]) -> Mapping[str, Any]:
        value = _load_pointer(root, pointer, label="selector evidence auth node")
        return private_auth_dict.validate_node(value, domain=domain)

    try:
        return private_auth_dict.sharded_lookup(
            receipt,
            logical_key,
            domain=domain,
            load_node=load_node,
            cache=private_auth_dict.ShardedLookupCache.empty(domain),
        )
    except private_auth_dict.AuthDictError as exc:
        raise SparseSelectorError(str(exc)) from exc


def _ledger_plan_binding(
    root: Path, receipt: Mapping[str, Any], plan_id: str
) -> dict[str, Any] | None:
    found = _evidence_auth_lookup(
        root,
        receipt,
        domain=EVIDENCE_LEDGER_ROW_DOMAIN,
        logical_key=["plan", plan_id],
    )
    return None if not found.found else copy.deepcopy(found.binding)


def _ledger_ordinal_binding(
    root: Path, receipt: Mapping[str, Any], ordinal: int
) -> dict[str, Any]:
    found = _evidence_auth_lookup(
        root,
        receipt,
        domain=EVIDENCE_LEDGER_ROW_DOMAIN,
        logical_key=["ordinal", ordinal],
    )
    if not found.found or not isinstance(found.binding, Mapping):
        _fail("selector replay ledger ordinal is absent")
    return copy.deepcopy(dict(found.binding))


def _boundary_mark_pointer(
    root: Path,
    receipt: Mapping[str, Any],
    boundary_id: str,
    reverse_ordinal: int,
) -> dict[str, Any]:
    found = _evidence_auth_lookup(
        root,
        receipt,
        domain=EVIDENCE_MARK_SEEN_DOMAIN,
        logical_key=["boundary", boundary_id, "reverse", reverse_ordinal],
    )
    if not found.found or not isinstance(found.binding, Mapping):
        _fail("selector occurrence mark index is incomplete")
    try:
        return mark_chain._validate_pointer(dict(found.binding))
    except (TypeError, ValueError, KeyError) as exc:
        raise SparseSelectorError(
            "selector occurrence mark index binding drifted"
        ) from exc


def _live_mark_pointer(
    root: Path,
    receipt: Mapping[str, Any],
    reverse_ordinal: int,
) -> dict[str, Any]:
    found = _evidence_auth_lookup(
        root,
        receipt,
        domain=EVIDENCE_MARK_SEEN_DOMAIN,
        logical_key=["live", "reverse", reverse_ordinal],
    )
    if not found.found or not isinstance(found.binding, Mapping):
        _fail("selector captured live mark index is incomplete")
    try:
        return mark_chain._validate_pointer(dict(found.binding))
    except (TypeError, ValueError, KeyError) as exc:
        raise SparseSelectorError(
            "selector captured live mark index binding drifted"
        ) from exc


def _read_pinned_ledger_slice(
    lifecycle_root: Path, *, first_byte: int, last_byte: int
) -> bytes:
    active = _ACTIVE_EVIDENCE_SOURCES.get()
    if active is not None:
        if _absolute_private_path(lifecycle_root) != active.lifecycle.root:
            _fail("selector ledger read escaped its anchored root")
        with _open_anchored_parent(
            active.lifecycle, "canonical_ledger/ledger.jsonl"
        ) as (parent_fd, name):
            fd = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_fd,
            )
            try:
                info = os.fstat(fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1
                    or not 0 <= first_byte < last_byte <= info.st_size
                ):
                    _fail("selector pinned ledger metadata or slice is unsafe")
                body = os.pread(fd, last_byte - first_byte, first_byte)
                if len(body) != last_byte - first_byte:
                    _fail("selector pinned ledger slice changed length")
                after = os.fstat(fd)
                if (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                ) != (
                    info.st_dev,
                    info.st_ino,
                    info.st_size,
                    info.st_mtime_ns,
                ):
                    _fail("selector pinned ledger changed during bounded read")
                return body
            finally:
                os.close(fd)
    ledger_path, _receipt_path = lifecycle._ledger_paths(
        lifecycle_root,
        ledger_path=None,
        ledger_receipt_path=None,
        create=False,
    )
    fd = os.open(ledger_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or not 0 <= first_byte < last_byte <= info.st_size
        ):
            _fail("selector pinned ledger metadata or slice is unsafe")
        body = os.pread(fd, last_byte - first_byte, first_byte)
        if len(body) != last_byte - first_byte:
            _fail("selector pinned ledger slice changed length")
        after = os.fstat(fd)
        if (
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        ):
            _fail("selector pinned ledger changed during bounded read")
        return body
    finally:
        os.close(fd)


def _make_evidence_ledger_chunk(
    *,
    snapshot: Mapping[str, Any],
    ordinal: int,
    first_byte: int,
    raw: bytes,
) -> PlannedObject:
    value: dict[str, Any] = {
        "schema": "options.sparse_selector_evidence_ledger_chunk/v1",
        "ledger_chunk_id": "",
        "snapshot": copy.deepcopy(dict(snapshot)),
        "producer_contract": copy.deepcopy(PRODUCER_CONTRACT),
        "ordinal": ordinal,
        "first_byte": first_byte,
        "last_byte": first_byte + len(raw),
        "body_sha256": _sha256(raw),
        "body_base64": base64.b64encode(raw).decode("ascii"),
        "authority": dict(FALSE_AUTHORITY),
    }
    value["ledger_chunk_id"] = _content_id(
        "oselc_", value, field="ledger_chunk_id"
    )
    clean = validate_runtime_object(value, label="selector evidence ledger chunk")
    return PlannedObject(
        key=f"{EVIDENCE_AUDIT_NAMESPACE}/{clean['ledger_chunk_id']}.json",
        value=clean,
    )


def _load_evidence_ledger_chunk(
    root: Path,
    pointer: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any],
    inherited_pointers: Sequence[Mapping[str, Any]] = (),
    ordinal: int,
    first_byte: int,
) -> tuple[dict[str, Any], bytes]:
    value = _load_pointer(root, pointer, label="selector evidence ledger chunk")
    clean = validate_runtime_object(value, label="selector evidence ledger chunk")
    if (
        clean.get("schema")
        != "options.sparse_selector_evidence_ledger_chunk/v1"
        or pointer["key"]
        != f"{EVIDENCE_AUDIT_NAMESPACE}/{clean['ledger_chunk_id']}.json"
        or (
            clean["snapshot"] != dict(snapshot)
            and dict(pointer) not in [dict(item) for item in inherited_pointers]
        )
        or clean["ordinal"] != ordinal
        or clean["first_byte"] != first_byte
    ):
        _fail("selector evidence ledger chunk chain drifted")
    raw = base64.b64decode(clean["body_base64"], validate=True)
    return clean, raw


def _ledger_chunk_stream(
    root: Path,
    pointers: Sequence[Mapping[str, Any]],
    *,
    snapshot: Mapping[str, Any],
    inherited_pointers: Sequence[Mapping[str, Any]] = (),
) -> Iterator[bytes]:
    cursor = 0
    for ordinal, pointer in enumerate(pointers, start=1):
        chunk, raw = _load_evidence_ledger_chunk(
            root,
            pointer,
            snapshot=snapshot,
            inherited_pointers=inherited_pointers,
            ordinal=ordinal,
            first_byte=cursor,
        )
        cursor = chunk["last_byte"]
        yield raw


def _authenticate_captured_ledger(
    root: Path,
    pointers: Sequence[Mapping[str, Any]],
    *,
    snapshot: Mapping[str, Any],
    inherited_pointers: Sequence[Mapping[str, Any]] = (),
    receipt: Mapping[str, Any],
) -> None:
    digest = hashlib.sha256()
    size = 0
    last = b""
    for raw in _ledger_chunk_stream(
        root,
        pointers,
        snapshot=snapshot,
        inherited_pointers=inherited_pointers,
    ):
        digest.update(raw)
        size += len(raw)
        if raw:
            last = raw[-1:]
    if (
        size != receipt["bytes"]
        or digest.hexdigest() != receipt["sha256"]
        or last != b"\n"
    ):
        _fail("selector captured ledger does not match its pinned receipt")


def _captured_ledger_range(
    root: Path,
    pointers: Sequence[Mapping[str, Any]],
    *,
    snapshot: Mapping[str, Any],
    inherited_pointers: Sequence[Mapping[str, Any]] = (),
    first_byte: int,
    last_byte: int,
) -> bytes:
    if not 0 <= first_byte <= last_byte:
        _fail("selector captured ledger range is malformed")
    result = bytearray()
    cursor = 0
    for raw in _ledger_chunk_stream(
        root,
        pointers,
        snapshot=snapshot,
        inherited_pointers=inherited_pointers,
    ):
        next_cursor = cursor + len(raw)
        if next_cursor > first_byte and cursor < last_byte:
            start = max(first_byte, cursor) - cursor
            end = min(last_byte, next_cursor) - cursor
            result.extend(raw[start:end])
        cursor = next_cursor
        if cursor >= last_byte:
            break
    if len(result) != last_byte - first_byte:
        _fail("selector captured ledger range is incomplete")
    return bytes(result)


def _captured_ledger_rows(
    root: Path,
    pointers: Sequence[Mapping[str, Any]],
    *,
    snapshot: Mapping[str, Any],
    inherited_pointers: Sequence[Mapping[str, Any]] = (),
    byte_cursor: int,
    row_cursor: int,
    boundary: Mapping[str, Any],
    row_limit: int,
) -> tuple[int, list[tuple[int, dict[str, Any]]]]:
    boundary_bytes = int(boundary["bytes"])
    if not 0 <= byte_cursor <= boundary_bytes:
        _fail("selector captured ledger byte cursor drifted")
    position = byte_cursor
    chunk_index = byte_cursor // EVIDENCE_LEDGER_CHUNK_BYTES
    line = bytearray()
    parsed: list[tuple[int, dict[str, Any]]] = []
    while position < boundary_bytes and len(parsed) < row_limit:
        if chunk_index >= len(pointers):
            _fail("selector captured ledger chunks end before their boundary")
        first = chunk_index * EVIDENCE_LEDGER_CHUNK_BYTES
        _chunk, raw = _load_evidence_ledger_chunk(
            root,
            pointers[chunk_index],
            snapshot=snapshot,
            inherited_pointers=inherited_pointers,
            ordinal=chunk_index + 1,
            first_byte=first,
        )
        local = position - first
        available = raw[local : min(len(raw), boundary_bytes - first)]
        while available and len(parsed) < row_limit:
            newline = available.find(b"\n")
            if newline < 0:
                line.extend(available)
                position += len(available)
                available = b""
                break
            line.extend(available[:newline])
            position += newline + 1
            available = available[newline + 1 :]
            stripped = bytes(line).strip()
            line.clear()
            if not stripped or stripped.startswith(b"#"):
                continue
            value = strict_json(stripped, label="selector captured ledger row")
            try:
                row = lifecycle._validate_ledger_row(
                    value, ordinal=row_cursor + len(parsed) + 1
                )
            except (TypeError, ValueError, KeyError) as exc:
                raise SparseSelectorError(
                    "selector captured ledger row is invalid"
                ) from exc
            parsed.append((row_cursor + len(parsed) + 1, row))
        if position >= first + len(raw):
            chunk_index += 1
    if position == boundary_bytes and line:
        _fail("selector captured ledger boundary cuts a line")
    return position, parsed


def _make_pinned_evidence_high_water(
    *,
    snapshot: PlannedObject,
    previous_complete: Mapping[str, Any] | None,
    prior_high: Mapping[str, Any] | None = None,
) -> PlannedObject:
    state = snapshot.value["lifecycle_state"]
    incremental = previous_complete is not None
    if incremental != (prior_high is not None):
        _fail("selector incremental PIN parent is incomplete")
    if prior_high is not None and (
        prior_high.get("phase") != "COMPLETE"
        or prior_high.get("producer_contract") != PRODUCER_CONTRACT
        or prior_high.get("activation") != state["activation"]
    ):
        _fail("selector incremental PIN parent contract drifted")
    value: dict[str, Any] = {
        "schema": "options.sparse_selector_evidence_high_water/v1",
        "high_water_id": "",
        "phase": "AUDIT_PINNED",
        "snapshot": snapshot.pointer,
        "previous_complete": (
            None if previous_complete is None else copy.deepcopy(dict(previous_complete))
        ),
        "producer_contract": copy.deepcopy(PRODUCER_CONTRACT),
        "replay_state": (
            None if prior_high is None else copy.deepcopy(prior_high["replay_state"])
        ),
        "replay_state_id": (
            None if prior_high is None else prior_high["replay_state_id"]
        ),
        "replay_lifecycle_head": (
            None
            if prior_high is None
            else copy.deepcopy(prior_high["replay_lifecycle_head"])
        ),
        "replay_mark_cursor": (
            None
            if prior_high is None
            else copy.deepcopy(prior_high["replay_mark_cursor"])
        ),
        "replay_ledger_cursor": (
            None
            if prior_high is None
            else copy.deepcopy(prior_high["replay_ledger_cursor"])
        ),
        "base_state_id": None,
        "base_lifecycle_head": None,
        "base_mark_cursor": None,
        "base_ledger_cursor": None,
        "occurrence_stage": "LEDGER_CAPTURE",
        "current_boundary": None,
        "boundary_mark_cursor": None,
        "boundary_mark_row_cursor": 0,
        "boundary_mark_ordinal": 0,
        "boundary_ledger_row_cursor": 0,
        "boundary_ledger_byte_cursor": 0,
        "boundary_event_cursor": 0,
        "boundary_terminal_cursor": 0,
        "boundary_index": (
            _empty_evidence_audit_index(EVIDENCE_BOUNDARY_DOMAIN)
            if prior_high is None
            else copy.deepcopy(prior_high["boundary_index"])
        ),
        "source_state_id": state["state_id"],
        "activation": copy.deepcopy(state["activation"]),
        "lifecycle_head": copy.deepcopy(state["lifecycle_head"]),
        "mark_cursor": copy.deepcopy(state["mark_cursor"]),
        "ledger_cursor": copy.deepcopy(state["ledger_cursor"]),
        "captured_mark_head": copy.deepcopy(snapshot.value["live_mark_head"]),
        "captured_ledger_receipt": copy.deepcopy(
            snapshot.value["live_ledger_receipt"]
        ),
        "ledger_capture_bytes": (
            0 if prior_high is None else prior_high["ledger_capture_bytes"]
        ),
        "ledger_replay_bytes": (
            0 if prior_high is None else prior_high["ledger_replay_bytes"]
        ),
        "ledger_replay_rows": (
            0 if prior_high is None else prior_high["ledger_replay_rows"]
        ),
        "live_mark_scan_cursor": copy.deepcopy(snapshot.value["live_mark_head"]),
        "live_mark_reverse_ordinal": 0,
        "event_cursor": None,
        "event_count": 0,
        "event_seen_index": _empty_evidence_audit_index(
            EVIDENCE_EVENT_SEEN_DOMAIN
        ),
        "event_enrollment_index": _empty_evidence_audit_index(
            EVIDENCE_EVENT_ENROLLMENT_DOMAIN
        ),
        "event_terminal_index": _empty_evidence_audit_index(
            EVIDENCE_EVENT_TERMINAL_DOMAIN
        ),
        "state_enrollment_cursor": 0,
        "state_terminal_cursor": 0,
        "state_enrollment_index": _empty_evidence_audit_index(
            EVIDENCE_STATE_ENROLLMENT_DOMAIN
        ),
        "state_terminal_index": _empty_evidence_audit_index(
            EVIDENCE_STATE_TERMINAL_DOMAIN
        ),
        "state_latest_cursor": 0,
        "state_latest_index": _empty_evidence_audit_index(
            EVIDENCE_STATE_LATEST_DOMAIN
        ),
        "mark_scan_cursor": None,
        "mark_row_cursor": 0,
        "mark_count": 0,
        "mark_seen_index": _empty_evidence_audit_index(
            EVIDENCE_MARK_SEEN_DOMAIN
        ),
        "derived_latest_index": _empty_evidence_audit_index(
            EVIDENCE_DERIVED_LATEST_DOMAIN
        ),
        "derived_latest_active_count": 0,
        "ledger_cursor_bytes": 0,
        "ledger_chunks": (
            [] if prior_high is None else copy.deepcopy(prior_high["ledger_chunks"])
        ),
        "ledger_row_count": (
            0 if prior_high is None else prior_high["ledger_row_count"]
        ),
        "ledger_row_index": (
            _empty_evidence_audit_index(EVIDENCE_LEDGER_ROW_DOMAIN)
            if prior_high is None
            else copy.deepcopy(prior_high["ledger_row_index"])
        ),
        "ledger_terminal_match_count": 0,
        "ledger_terminal_index": _empty_evidence_audit_index(
            EVIDENCE_LEDGER_TERMINAL_DOMAIN
        ),
        "authority": dict(FALSE_AUTHORITY),
    }
    value["high_water_id"] = _content_id("osehw_", value, field="high_water_id")
    clean = validate_runtime_object(value, label="selector pinned evidence high-water")
    return PlannedObject(
        key=f"{EVIDENCE_AUDIT_NAMESPACE}/{clean['high_water_id']}.json",
        value=clean,
    )


def _evidence_audit_head(
    *, head: Mapping[str, Any], high_water: PlannedObject, advanced_at: str
) -> dict[str, Any]:
    next_head = copy.deepcopy(dict(head))
    next_head.update(
        {
            "head_id": "",
            "generation": head["generation"] + 1,
            "previous_head_id": head["head_id"],
            "advanced_at": advanced_at,
            "evidence_high_water": high_water.pointer,
        }
    )
    next_head["head_id"] = _content_id("ossh_", next_head, field="head_id")
    return validate_runtime_object(next_head, label="selector evidence audit HEAD")


def _evidence_audit_transition_intent(
    *,
    head: Mapping[str, Any],
    next_head: Mapping[str, Any],
    objects: Sequence[PlannedObject],
    audit_window: Mapping[str, Any],
    evidence_inputs: EvidenceInputs,
) -> CyclePlan:
    ordered = tuple(sorted(objects, key=lambda item: item.key))
    intent: dict[str, Any] = {
        "schema": "options.sparse_selector_evidence_audit_intent/v1",
        "intent_sha256": "",
        "expected_head_id": head["head_id"],
        "expected_advanced_at": head["advanced_at"],
        "expected_source_state": _source_expected_state(head),
        "expected_runtime_state": _runtime_expected_state(head),
        "expected_evidence_high_water": copy.deepcopy(
            head["evidence_high_water"]
        ),
        "audit_window": copy.deepcopy(dict(audit_window)),
        "objects": [item.receipt for item in ordered],
        "next_head": copy.deepcopy(dict(next_head)),
    }
    intent["intent_sha256"] = _content_id("", intent, field="intent_sha256")
    if (
        len(ordered) + 1 > MAX_SOURCE_OBJECTS_PER_CYCLE
        or len(canonical_bytes(intent)) > MAX_SOURCE_INTENT_BYTES
        or _transition_footprint_bytes(intent, ordered) > MAX_SOURCE_INTENT_BYTES
    ):
        _fail("selector evidence audit transition exceeds its bounds")
    return CyclePlan(
        expected_head_id=head["head_id"],
        objects=ordered,
        head=copy.deepcopy(dict(next_head)),
        intent=intent,
        evidence_inputs=evidence_inputs,
    )


def _plan_evidence_capture_transition(
    *,
    root: Path,
    head: Mapping[str, Any],
    evidence_inputs: EvidenceInputs,
    clock: Callable[[], datetime],
) -> CyclePlan:
    if evidence_inputs.mark_root is None or evidence_inputs.lifecycle_root is None:
        _fail("selector evidence capture requires both producer roots")
    previous = head["evidence_high_water"]
    prior: dict[str, Any] | None = None
    prior_snapshot: dict[str, Any] | None = None
    if previous is not None:
        prior = _authenticate_evidence_high_water_graph(
            root, previous, evidence_inputs=evidence_inputs
        )
        if prior["phase"] != "COMPLETE":
            _fail("selector cannot repin over an incomplete evidence audit")
        prior_snapshot = validate_runtime_object(
            _load_pointer(
                root, prior["snapshot"], label="selector prior source snapshot"
            ),
            label="selector prior source snapshot",
        )
    mark_root = Path(evidence_inputs.mark_root).expanduser()
    lifecycle_root = Path(evidence_inputs.lifecycle_root).expanduser()
    with _open_selector_lane(root, create=False) as selector_lane:
        with _anchored_evidence_sources(
            mark_root, lifecycle_root, selector_lane=selector_lane
        ) as sources:
            state_body, state = _read_lifecycle_state_bytes(sources.lifecycle)
            live_mark_head, live_ledger_receipt, activation_boundary = (
                _verify_capture_source_prefixes(
                    sources=sources,
                    state=state,
                    prior_snapshot=prior_snapshot,
                )
            )
            if prior is not None:
                assert prior_snapshot is not None
                if (
                    prior["producer_contract"] != PRODUCER_CONTRACT
                    or prior_snapshot["producer_roots"] != sources.producer_roots
                ):
                    _fail("selector incremental producer contract or roots drifted")
                _anchored_mark_chain_contains(
                    sources.mark,
                    live_mark_head,
                    (
                        state["mark_cursor"],
                        prior_snapshot["live_mark_head"],
                    ),
                )
                _anchored_ledger_extends(
                    sources.lifecycle, prior_snapshot["live_ledger_receipt"]
                )
                token = _ACTIVE_EVIDENCE_SOURCES.set(sources)
                try:
                    _incremental_target_descends(
                        lifecycle_root,
                        prior_state_id=prior["source_state_id"],
                        target_state_id=state["state_id"],
                    )
                finally:
                    _ACTIVE_EVIDENCE_SOURCES.reset(token)
            if _read_anchored_file(
                sources.lifecycle,
                "current.json",
                limit=2 * 1024 * 1024,
                label="selector lifecycle current state",
            ) != state_body:
                raise EvidenceGenerationDrift(
                    "selector lifecycle state changed during capture planning"
                )
            producer_roots = copy.deepcopy(dict(sources.producer_roots))
    captured = _aware_utc(clock(), label="selector evidence capture clock")
    if captured < _utc(head["advanced_at"], label="selector prior HEAD clock"):
        _fail("selector evidence capture clock moved backward")
    captured_at = utc_text(captured)
    snapshot = _make_evidence_source_snapshot(
        state=state,
        live_mark_head=live_mark_head,
        live_ledger_receipt=live_ledger_receipt,
        activation_boundary=activation_boundary,
        producer_roots=producer_roots,
        captured_at=captured_at,
    )
    high_water = _make_pinned_evidence_high_water(
        snapshot=snapshot,
        previous_complete=previous,
        prior_high=prior,
    )
    next_head = _evidence_audit_head(
        head=head, high_water=high_water, advanced_at=captured_at
    )
    return _evidence_audit_transition_intent(
        head=head,
        next_head=next_head,
        objects=(snapshot, high_water),
        audit_window={
            "stage": "PIN",
            "snapshot": snapshot.pointer,
            "high_water": high_water.pointer,
        },
        evidence_inputs=evidence_inputs,
    )


def _plan_evidence_occurrence_transition_core(
    *,
    root: Path,
    head: Mapping[str, Any],
    evidence_inputs: EvidenceInputs,
    clock: Callable[[], datetime],
    row_limit: int = 64,
) -> CyclePlan:
    """Advance one bounded, non-consumable producer-occurrence audit step."""

    if not 1 <= row_limit <= 128:
        _fail("selector occurrence replay row bound is malformed")
    if evidence_inputs.mark_root is None or evidence_inputs.lifecycle_root is None:
        _fail("selector occurrence replay requires producer roots")
    if head.get("evidence_high_water") is None:
        _fail("selector occurrence replay lacks a pinned high-water")
    mark_root = Path(evidence_inputs.mark_root).expanduser()
    lifecycle_root = Path(evidence_inputs.lifecycle_root).expanduser()
    high = _load_evidence_high_water(root, head["evidence_high_water"])
    prior_high = (
        None
        if high["previous_complete"] is None
        else _load_evidence_high_water(root, high["previous_complete"])
    )
    inherited_chunks: Sequence[Mapping[str, Any]] = (
        () if prior_high is None else tuple(prior_high["ledger_chunks"])
    )
    snapshot = _load_pointer(
        root, high["snapshot"], label="selector occurrence source snapshot"
    )
    snapshot = validate_runtime_object(
        snapshot, label="selector occurrence source snapshot"
    )
    target = snapshot["lifecycle_state"]
    advanced = _aware_utc(clock(), label="selector occurrence replay clock")
    if advanced < _utc(head["advanced_at"], label="selector occurrence parent clock"):
        _fail("selector occurrence replay clock moved backward")
    advanced_at = utc_text(advanced)

    def finish(
        next_high: PlannedObject,
        objects: Sequence[PlannedObject],
        *,
        stage: str,
    ) -> CyclePlan:
        next_head = _evidence_audit_head(
            head=head, high_water=next_high, advanced_at=advanced_at
        )
        return _evidence_audit_transition_intent(
            head=head,
            next_head=next_head,
            objects=(*objects, next_high),
            audit_window={
                "stage": stage,
                "prior_high_water": copy.deepcopy(head["evidence_high_water"]),
                "next_high_water": next_high.pointer,
                "row_limit": row_limit,
            },
            evidence_inputs=evidence_inputs,
        )

    if high["phase"] == "AUDIT_PINNED":
        if high["occurrence_stage"] != "LEDGER_CAPTURE":
            _fail("selector pinned occurrence stage drifted")
        receipt = snapshot["live_ledger_receipt"]
        first_byte = int(high["ledger_capture_bytes"])
        if first_byte == int(receipt["bytes"]):
            next_high = _replay_high_water_object(
                high,
                phase="AUDIT_OCCURRENCES",
                occurrence_stage="LIVE_MARK_BACKWALK",
            )
            return finish(
                next_high, (), stage="OCCURRENCE_LEDGER_CAPTURE"
            )
        replace_tail = first_byte % EVIDENCE_LEDGER_CHUNK_BYTES != 0
        chunk_first = (
            first_byte - (first_byte % EVIDENCE_LEDGER_CHUNK_BYTES)
            if replace_tail
            else first_byte
        )
        last_byte = min(
            int(receipt["bytes"]), chunk_first + EVIDENCE_LEDGER_CHUNK_BYTES
        )
        raw = _read_pinned_ledger_slice(
            lifecycle_root, first_byte=chunk_first, last_byte=last_byte
        )
        chunk = _make_evidence_ledger_chunk(
            snapshot=high["snapshot"],
            ordinal=(len(high["ledger_chunks"]) if replace_tail else len(high["ledger_chunks"]) + 1),
            first_byte=chunk_first,
            raw=raw,
        )
        chunks = (
            [*high["ledger_chunks"][:-1], chunk.pointer]
            if replace_tail
            else [*high["ledger_chunks"], chunk.pointer]
        )
        next_high = _replay_high_water_object(
            high,
            phase="AUDIT_OCCURRENCES",
            ledger_chunks=chunks,
            ledger_capture_bytes=last_byte,
        )
        return finish(
            next_high, (chunk,), stage="OCCURRENCE_LEDGER_CAPTURE"
        )

    if high["phase"] not in {"AUDIT_OCCURRENCES", "COMPLETE"}:
        _fail("selector occurrence replay phase is unsupported")
    if high["phase"] == "COMPLETE":
        _fail("selector occurrence replay is already complete")
    stage = high["occurrence_stage"]
    if stage == "LEDGER_CAPTURE":
        receipt = snapshot["live_ledger_receipt"]
        first_byte = high["ledger_capture_bytes"]
        if first_byte < int(receipt["bytes"]):
            replace_tail = first_byte % EVIDENCE_LEDGER_CHUNK_BYTES != 0
            chunk_first = (
                first_byte - (first_byte % EVIDENCE_LEDGER_CHUNK_BYTES)
                if replace_tail
                else first_byte
            )
            last_byte = min(
                int(receipt["bytes"]), chunk_first + EVIDENCE_LEDGER_CHUNK_BYTES
            )
            raw = _read_pinned_ledger_slice(
                lifecycle_root, first_byte=chunk_first, last_byte=last_byte
            )
            chunk = _make_evidence_ledger_chunk(
                snapshot=high["snapshot"],
                ordinal=(len(high["ledger_chunks"]) if replace_tail else len(high["ledger_chunks"]) + 1),
                first_byte=chunk_first,
                raw=raw,
            )
            chunks = (
                [*high["ledger_chunks"][:-1], chunk.pointer]
                if replace_tail
                else [*high["ledger_chunks"], chunk.pointer]
            )
            next_high = _replay_high_water_object(
                high,
                ledger_chunks=chunks,
                ledger_capture_bytes=last_byte,
            )
            return finish(
                next_high, (chunk,), stage="OCCURRENCE_LEDGER_CAPTURE"
            )
        _authenticate_captured_ledger(
            root,
            high["ledger_chunks"],
            snapshot=high["snapshot"],
            inherited_pointers=inherited_chunks,
            receipt=receipt,
        )
        next_high = _replay_high_water_object(
            high,
            occurrence_stage="LIVE_MARK_BACKWALK",
        )
        return finish(
            next_high, (), stage="OCCURRENCE_LEDGER_CAPTURE"
        )

    if stage == "LIVE_MARK_BACKWALK":
        pointer = high["live_mark_scan_cursor"]
        count = high["live_mark_reverse_ordinal"]
        entries: list[tuple[Any, Any]] = []
        for _ in range(row_limit):
            if pointer == target["mark_cursor"]:
                break
            if pointer is None:
                _fail("selector live mark head forked before the pinned cursor")
            observation = _load_frozen_mark_observation(mark_root, pointer)
            count += 1
            entries.append((["live", "reverse", count], copy.deepcopy(pointer)))
            previous = observation.get("previous")
            pointer = (
                None
                if previous is None
                else mark_chain._validate_pointer(previous)
            )
        mark_index, nodes = _evidence_auth_nodes(
            root,
            prior=high["mark_seen_index"],
            domain=EVIDENCE_MARK_SEEN_DOMAIN,
            entries=entries,
        )
        done = pointer == target["mark_cursor"]
        if done:
            _load_frozen_mark_observation(mark_root, target["mark_cursor"])
        next_high = _replay_high_water_object(
            high,
            mark_seen_index=mark_index,
            live_mark_scan_cursor=(
                copy.deepcopy(target["mark_cursor"]) if done else pointer
            ),
            live_mark_reverse_ordinal=count,
            occurrence_stage=(
                (
                    "EDGE_INIT"
                    if done and prior_high is not None
                    else "COLD_ACTIVATION"
                    if done
                    else "LIVE_MARK_BACKWALK"
                )
            ),
        )
        return finish(
            next_high, nodes, stage="OCCURRENCE_LIVE_MARK_BACKWALK"
        )

    if stage == "COLD_ACTIVATION":
        _authenticate_captured_ledger(
            root,
            high["ledger_chunks"],
            snapshot=high["snapshot"],
            inherited_pointers=inherited_chunks,
            receipt=snapshot["live_ledger_receipt"],
        )
        boundary = lifecycle._validate_activation_boundary(
            snapshot["activation_boundary"]
        )
        active_sources = _ACTIVE_EVIDENCE_SOURCES.get()
        if active_sources is None:
            _fail("selector occurrence activation lacks anchored sources")
        if _read_anchored_activation_boundary(active_sources.lifecycle) != boundary:
            _fail("selector captured activation boundary drifted before replay")
        activation_prefix = _captured_ledger_range(
            root,
            high["ledger_chunks"],
            snapshot=high["snapshot"],
            first_byte=0,
            last_byte=int(boundary["ledger_boundary"]["bytes"]),
        )
        if _sha256(activation_prefix) != boundary["ledger_boundary"]["sha256"]:
            _fail("selector activation ledger boundary drifted")
        mark = _load_frozen_mark_observation(mark_root, boundary["mark_boundary"])
        activation_event = _frozen_activation_event(boundary, mark)
        if (
            lifecycle._event_pointer(activation_event) != target["activation"]
            or _load_frozen_lifecycle_event(lifecycle_root, target["activation"])
            != activation_event
        ):
            _fail("selector activation event is not its exact frozen occurrence")
        activation_state = lifecycle._make_state(
            activation=target["activation"],
            lifecycle_head=target["activation"],
            mark_cursor=boundary["mark_boundary"],
            ledger_cursor=boundary["ledger_boundary"],
            enrollments={}, terminals={}, latest_marks={},
        )
        replay = _make_evidence_replay_state(
            snapshot=high["snapshot"], state=activation_state
        )
        activation_receipt = _activation_boundary_receipt(boundary)
        boundary_index, auth_nodes = _evidence_auth_nodes(
            root,
            prior=high["boundary_index"],
            domain=EVIDENCE_BOUNDARY_DOMAIN,
            entries=(([
                "activation", boundary["boundary_id"]
            ], activation_receipt),),
        )
        next_high = _replay_high_water_object(
            high,
            occurrence_stage="LEDGER_ROWS",
            current_boundary=activation_receipt,
            boundary_index=boundary_index,
            ledger_replay_rows=0,
            ledger_replay_bytes=0,
            **_replay_state_fields(replay),
        )
        return finish(
            next_high, (*auth_nodes, replay), stage="OCCURRENCE_ACTIVATION"
        )

    replay_value = validate_runtime_object(
        _load_pointer(
            root, high["replay_state"], label="selector evidence replay state"
        ),
        label="selector evidence replay state",
    )
    state = copy.deepcopy(replay_value["state"])

    if stage == "LEDGER_ROWS":
        if high["current_boundary"] is None:
            _fail("selector occurrence ledger stage lacks its boundary")
        receipt = high["current_boundary"]["ledger_boundary"]
        byte_cursor, selected = _captured_ledger_rows(
            root,
            high["ledger_chunks"],
            snapshot=high["snapshot"],
            inherited_pointers=inherited_chunks,
            byte_cursor=high["ledger_replay_bytes"],
            row_cursor=high["ledger_replay_rows"],
            boundary=receipt,
            row_limit=row_limit,
        )
        entries: list[tuple[Any, Any]] = []
        seen_plans: set[str] = set()
        for ordinal, row in selected:
            binding = _ledger_row_binding(row, ordinal)
            if binding["plan_id"] in seen_plans or _ledger_plan_binding(
                root, high["ledger_row_index"], binding["plan_id"]
            ) is not None:
                _fail("selector captured ledger repeats a plan id")
            seen_plans.add(binding["plan_id"])
            entries.extend(
                ((["plan", binding["plan_id"]], binding), (["ordinal", ordinal], binding))
            )
        ledger_index, nodes = _evidence_auth_nodes(
            root,
            prior=high["ledger_row_index"],
            domain=EVIDENCE_LEDGER_ROW_DOMAIN,
            entries=entries,
        )
        next_cursor = high["ledger_replay_rows"] + len(selected)
        done = byte_cursor == int(receipt["bytes"])
        if done and next_cursor != int(receipt["row_count"]):
            _fail("selector activation ledger row count drifted")
        updates: dict[str, Any] = {
            "ledger_row_index": ledger_index,
            "ledger_row_count": next_cursor,
            "ledger_replay_rows": next_cursor,
            "ledger_replay_bytes": byte_cursor,
        }
        if done:
            if high["current_boundary"]["kind"] == "activation":
                updates["current_boundary"] = None
                updates["occurrence_stage"] = "EDGE_INIT"
            else:
                updates.update(
                    occurrence_stage="EDGE_MARK_BACKWALK",
                    boundary_mark_cursor=copy.deepcopy(
                        high["current_boundary"]["mark_boundary"]
                    ),
                    boundary_mark_ordinal=0,
                    boundary_mark_row_cursor=0,
                )
        next_high = _replay_high_water_object(high, **updates)
        return finish(next_high, nodes, stage="OCCURRENCE_LEDGER_ROWS")

    if stage == "EDGE_INIT":
        # The target equality check precedes the boundary lookup deliberately:
        # a producer crash may leave an outgoing orphan edge after current.json.
        if state["state_id"] == target["state_id"]:
            if state != target:
                _fail("selector replay target state identity collided")
            if (
                high["ledger_capture_bytes"]
                != int(snapshot["live_ledger_receipt"]["bytes"])
                or high["ledger_replay_bytes"]
                != int(target["ledger_cursor"]["bytes"])
                or high["ledger_replay_rows"]
                != int(target["ledger_cursor"]["row_count"])
                or high["live_mark_scan_cursor"] != target["mark_cursor"]
                or high["current_boundary"] is not None
                or any(
                    high[field] is not None
                    for field in (
                        "base_state_id",
                        "base_lifecycle_head",
                        "base_mark_cursor",
                        "base_ledger_cursor",
                        "boundary_mark_cursor",
                    )
                )
                or any(
                    high[field] != 0
                    for field in (
                        "boundary_mark_row_cursor",
                        "boundary_mark_ordinal",
                        "boundary_ledger_row_cursor",
                        "boundary_ledger_byte_cursor",
                        "boundary_event_cursor",
                        "boundary_terminal_cursor",
                    )
                )
            ):
                _fail("selector occurrence target is not completely replayed")
            next_high = _replay_high_water_object(
                high, phase="COMPLETE", occurrence_stage="DONE"
            )
            return finish(next_high, (), stage="OCCURRENCE_COMPLETE")
        boundary, receipt = _load_exact_advance_boundary(
            lifecycle_root, state["state_id"]
        )
        mark = _load_frozen_mark_observation(mark_root, boundary["mark_boundary"])
        if mark.get("observed_at_utc") != boundary["mark_boundary_observed_at_utc"]:
            _fail("selector replay advance mark clock drifted")
        ledger_receipt = boundary["ledger_boundary"]
        if (
            int(ledger_receipt["bytes"])
            > int(target["ledger_cursor"]["bytes"])
            or int(ledger_receipt["row_count"])
            > int(target["ledger_cursor"]["row_count"])
        ):
            _fail("selector replay advance boundary passed its pinned target")
        boundary_prefix = _captured_ledger_range(
            root,
            high["ledger_chunks"],
            snapshot=high["snapshot"],
            inherited_pointers=inherited_chunks,
            first_byte=0,
            last_byte=int(ledger_receipt["bytes"]),
        )
        base_prefix = boundary_prefix[: int(state["ledger_cursor"]["bytes"])]
        if (
            int(ledger_receipt["bytes"]) < int(state["ledger_cursor"]["bytes"])
            or int(ledger_receipt["row_count"])
            < int(state["ledger_cursor"]["row_count"])
            or _sha256(boundary_prefix) != ledger_receipt["sha256"]
            or _sha256(base_prefix) != state["ledger_cursor"]["sha256"]
            or (
                base_prefix
                and not base_prefix.endswith(b"\n")
            )
        ):
            _fail("selector replay advance ledger moved backward")
        boundary_index, nodes = _evidence_auth_nodes(
            root,
            prior=high["boundary_index"],
            domain=EVIDENCE_BOUNDARY_DOMAIN,
            entries=(([
                "advance", boundary["base_state_id"]
            ], receipt),),
        )
        next_high = _replay_high_water_object(
            high,
            occurrence_stage="LEDGER_ROWS",
            current_boundary=receipt,
            boundary_index=boundary_index,
            base_state_id=state["state_id"],
            base_lifecycle_head=copy.deepcopy(state["lifecycle_head"]),
            base_mark_cursor=copy.deepcopy(state["mark_cursor"]),
            base_ledger_cursor=copy.deepcopy(state["ledger_cursor"]),
            boundary_mark_cursor=None,
            boundary_mark_ordinal=0,
            boundary_mark_row_cursor=0,
            boundary_event_cursor=0,
            boundary_terminal_cursor=0,
        )
        return finish(next_high, nodes, stage="OCCURRENCE_EDGE_INIT")

    if high["current_boundary"] is None:
        _fail("selector occurrence edge stage lacks its boundary")
    boundary = _load_boundary_from_receipt(
        lifecycle_root, high["current_boundary"]
    )
    if boundary["base_state_id"] != high["base_state_id"]:
        _fail("selector occurrence edge escaped its base state")

    if stage == "EDGE_MARK_BACKWALK":
        pointer = high["boundary_mark_cursor"]
        count = high["boundary_mark_ordinal"]
        entries: list[tuple[Any, Any]] = []
        for _ in range(128):
            if pointer == high["base_mark_cursor"]:
                break
            if pointer is None:
                _fail("selector occurrence mark boundary forked before its base")
            observation = _load_frozen_mark_observation(mark_root, pointer)
            count += 1
            entries.append(
                (
                    ["boundary", boundary["boundary_id"], "reverse", count],
                    copy.deepcopy(pointer),
                )
            )
            previous = observation.get("previous")
            pointer = (
                None
                if previous is None
                else mark_chain._validate_pointer(previous)
            )
        mark_index, nodes = _evidence_auth_nodes(
            root,
            prior=high["mark_seen_index"],
            domain=EVIDENCE_MARK_SEEN_DOMAIN,
            entries=entries,
        )
        done = pointer == high["base_mark_cursor"]
        if done:
            _load_frozen_mark_observation(mark_root, high["base_mark_cursor"])
        oldest_pointer = None if count == 0 else (
            copy.deepcopy(entries[-1][1])
            if entries
            else _boundary_mark_pointer(
                root,
                high["mark_seen_index"],
                boundary["boundary_id"],
                count,
            )
        )
        next_high = _replay_high_water_object(
            high,
            mark_seen_index=mark_index,
            occurrence_stage=(
                "EDGE_MARK_ROWS" if done else "EDGE_MARK_BACKWALK"
            ),
            boundary_mark_cursor=(
                oldest_pointer if done else pointer
            ),
            boundary_mark_ordinal=count,
            boundary_mark_row_cursor=0,
        )
        return finish(
            next_high, nodes, stage="OCCURRENCE_EDGE_MARK_BACKWALK"
        )

    if stage == "EDGE_MARK_ROWS":
        enrollments = copy.deepcopy(state["enrollments"])
        terminals = copy.deepcopy(state["terminals"])
        latest = copy.deepcopy(state["latest_marks"])
        lifecycle_head = copy.deepcopy(state["lifecycle_head"])
        event_cursor = high["boundary_event_cursor"]
        generated_entries: list[tuple[Any, Any]] = []
        current_pointer = high["boundary_mark_cursor"]
        mark_ordinal = high["boundary_mark_ordinal"]
        remaining = row_limit
        row_cursor = high["boundary_mark_row_cursor"]
        while mark_ordinal > 0 and remaining:
            if current_pointer is None:
                _fail("selector occurrence mark row cursor is absent")
            mark_pointer = _boundary_mark_pointer(
                root,
                high["mark_seen_index"],
                boundary["boundary_id"],
                mark_ordinal,
            )
            if mark_pointer != current_pointer:
                _fail("selector occurrence mark row cursor escaped its index")
            observation = _load_frozen_mark_observation(mark_root, mark_pointer)
            raw_rows = observation.get("rows")
            if not isinstance(raw_rows, list) or any(
                not isinstance(item, Mapping) for item in raw_rows
            ):
                _fail("selector occurrence mark rows are malformed")
            ordered_rows = sorted(
                (dict(item) for item in raw_rows),
                key=lambda item: str((item.get("plan") or {}).get("id") or ""),
            )
            if row_cursor > len(ordered_rows):
                _fail("selector occurrence mark row cursor moved past its object")
            take = min(remaining, len(ordered_rows) - row_cursor)
            for row in ordered_rows[row_cursor : row_cursor + take]:
                plan = row.get("plan")
                contract = row.get("contract")
                if not isinstance(plan, Mapping):
                    _fail("selector occurrence mark plan is malformed")
                plan_id = str(plan.get("id") or "")
                if not plan_id:
                    _fail("selector occurrence mark plan id is missing")
                if plan_id in terminals:
                    continue
                identity_matches = True
                if plan_id in enrollments:
                    enrolled = _load_frozen_lifecycle_event(
                        lifecycle_root, enrollments[plan_id]
                    )
                    identity_matches = lifecycle._stable_plan_identity(plan) == (
                        lifecycle._stable_plan_identity(enrolled["payload"]["plan"])
                    )
                    if plan_id not in latest:
                        _fail("selector occurrence open enrollment lacks latest state")
                    if not identity_matches:
                        latest[plan_id]["plan_identity_drift"] = True
                    if isinstance(contract, Mapping) and dict(contract) != enrolled[
                        "payload"
                    ]["contract"]:
                        latest[plan_id]["contract_drift"] = True
                closed = _ledger_plan_binding(
                    root, high["ledger_row_index"], plan_id
                )
                close_date = (
                    None
                    if closed is None
                    or closed["ordinal"]
                    <= int(high["base_ledger_cursor"]["row_count"])
                    else closed["close_date"]
                )
                eligible = (
                    (plan_id in enrollments or closed is None)
                    and identity_matches
                    and (
                        close_date is None
                        or str(observation["session_date"]) <= close_date
                    )
                    and plan.get("phase") in lifecycle.POST_TRIGGER_PHASES
                    and row.get("quote_status") == "available"
                    and isinstance(row.get("quote"), Mapping)
                    and isinstance(contract, Mapping)
                )
                if not eligible:
                    continue
                if plan_id not in enrollments:
                    event = _frozen_enrollment_event(
                        row=row,
                        mark_pointer=mark_pointer,
                        observation=observation,
                        previous=lifecycle_head,
                    )
                    _replay_actual_event(
                        lifecycle_root, boundary, event_cursor, event
                    )
                    event_pointer = lifecycle._event_pointer(event)
                    event_cursor += 1
                    lifecycle_head = event_pointer
                    enrollments[plan_id] = event_pointer
                    generated_entries.append(
                        (
                            ["boundary", boundary["boundary_id"], "enrollment", plan_id],
                            event_pointer,
                        )
                    )
                    latest[plan_id] = {
                        "contract_occ_symbol": contract["occ_symbol"],
                        "contract_drift": False,
                        "plan_identity_drift": False,
                        "sessions": {},
                    }
                enrolled = _load_frozen_lifecycle_event(
                    lifecycle_root, enrollments[plan_id]
                )
                if dict(contract) != enrolled["payload"]["contract"]:
                    latest[plan_id]["contract_drift"] = True
                    continue
                latest[plan_id]["sessions"][str(observation["session_date"])] = (
                    copy.deepcopy(mark_pointer)
                )
            remaining -= take
            row_cursor += take
            if row_cursor == len(ordered_rows):
                mark_ordinal -= 1
                row_cursor = 0
                current_pointer = (
                    None
                    if mark_ordinal == 0
                    else _boundary_mark_pointer(
                        root,
                        high["mark_seen_index"],
                        boundary["boundary_id"],
                        mark_ordinal,
                    )
                )
            elif take == 0:
                _fail("selector occurrence mark replay made no progress")
        intermediate = lifecycle._make_state(
            activation=state["activation"],
            lifecycle_head=lifecycle_head,
            mark_cursor=high["base_mark_cursor"],
            ledger_cursor=high["base_ledger_cursor"],
            enrollments=enrollments,
            terminals=terminals,
            latest_marks=latest,
        )
        replay = _make_evidence_replay_state(
            snapshot=high["snapshot"], state=intermediate
        )
        enrollment_index, enrollment_nodes = _evidence_auth_nodes(
            root,
            prior=high["event_enrollment_index"],
            domain=EVIDENCE_EVENT_ENROLLMENT_DOMAIN,
            entries=generated_entries,
        )
        done = mark_ordinal == 0
        next_high = _replay_high_water_object(
            high,
            occurrence_stage=(
                "EDGE_TERMINALS" if done else "EDGE_MARK_ROWS"
            ),
            boundary_mark_cursor=(None if done else current_pointer),
            boundary_mark_ordinal=mark_ordinal,
            boundary_mark_row_cursor=row_cursor,
            boundary_event_cursor=event_cursor,
            event_enrollment_index=enrollment_index,
            **_replay_state_fields(replay),
        )
        return finish(
            next_high,
            (*enrollment_nodes, replay),
            stage="OCCURRENCE_EDGE_MARK_ROWS",
        )

    if stage == "EDGE_TERMINALS":
        enrollments = copy.deepcopy(state["enrollments"])
        terminals = copy.deepcopy(state["terminals"])
        latest = copy.deepcopy(state["latest_marks"])
        lifecycle_head = copy.deepcopy(state["lifecycle_head"])
        event_cursor = high["boundary_event_cursor"]
        delta_count = int(boundary["ledger_boundary"]["row_count"]) - int(
            high["base_ledger_cursor"]["row_count"]
        )
        terminal_cursor = high["boundary_terminal_cursor"]
        for offset in range(
            terminal_cursor, min(delta_count, terminal_cursor + row_limit)
        ):
            ordinal = int(high["base_ledger_cursor"]["row_count"]) + offset + 1
            binding = _ledger_ordinal_binding(
                root, high["ledger_row_index"], ordinal
            )
            plan_id = binding["plan_id"]
            generated = _evidence_auth_lookup(
                root,
                high["event_enrollment_index"],
                domain=EVIDENCE_EVENT_ENROLLMENT_DOMAIN,
                logical_key=[
                    "boundary", boundary["boundary_id"], "enrollment", plan_id
                ],
            )
            if (
                plan_id not in enrollments
                or generated.found
                or plan_id in terminals
            ):
                continue
            if plan_id not in latest:
                _fail("selector occurrence durable enrollment lacks latest state")
            event = _frozen_terminal_event(
                lifecycle_root=lifecycle_root,
                mark_root=mark_root,
                plan_id=plan_id,
                ledger_row=binding,
                ledger_row_ordinal=ordinal,
                ledger_receipt=boundary["ledger_boundary"],
                enrollment_pointer=enrollments[plan_id],
                mark_chain_head=boundary["mark_boundary"],
                latest_state=latest[plan_id],
                previous=lifecycle_head,
                row_semantic_sha256=binding["row_semantic_sha256"],
            )
            _replay_actual_event(lifecycle_root, boundary, event_cursor, event)
            pointer = lifecycle._event_pointer(event)
            event_cursor += 1
            lifecycle_head = pointer
            terminals[plan_id] = pointer
            latest.pop(plan_id)
        next_terminal = min(delta_count, terminal_cursor + row_limit)
        done = next_terminal == delta_count
        intermediate = lifecycle._make_state(
            activation=state["activation"],
            lifecycle_head=lifecycle_head,
            mark_cursor=high["base_mark_cursor"],
            ledger_cursor=high["base_ledger_cursor"],
            enrollments=enrollments,
            terminals=terminals,
            latest_marks=latest,
        )
        replay = _make_evidence_replay_state(
            snapshot=high["snapshot"], state=intermediate
        )
        next_high = _replay_high_water_object(
            high,
            **_replay_state_fields(replay),
            occurrence_stage=(
                "EDGE_FINALIZE" if done else "EDGE_TERMINALS"
            ),
            boundary_event_cursor=event_cursor,
            boundary_terminal_cursor=next_terminal,
        )
        return finish(
            next_high, (replay,), stage="OCCURRENCE_EDGE_TERMINALS"
        )

    if stage == "EDGE_FINALIZE":
        if high["boundary_terminal_cursor"] != (
            int(boundary["ledger_boundary"]["row_count"])
            - int(high["base_ledger_cursor"]["row_count"])
        ):
            _fail("selector occurrence terminal cursor skipped its edge")
        if high["boundary_event_cursor"] != len(boundary["event_pointers"]):
            _fail("selector occurrence boundary omitted or added lifecycle events")
        if state["lifecycle_head"] != boundary["candidate_lifecycle_head"]:
            _fail("selector occurrence boundary lifecycle head drifted")
        candidate = lifecycle._make_state(
            activation=state["activation"],
            lifecycle_head=state["lifecycle_head"],
            mark_cursor=boundary["mark_boundary"],
            ledger_cursor=boundary["ledger_boundary"],
            enrollments=state["enrollments"],
            terminals=state["terminals"],
            latest_marks=state["latest_marks"],
        )
        if candidate["state_id"] != boundary["candidate_state_id"]:
            _fail("selector occurrence boundary candidate state drifted")
        replay = _make_evidence_replay_state(
            snapshot=high["snapshot"], state=candidate
        )
        next_high = _replay_high_water_object(
            high,
            **_replay_state_fields(replay),
            occurrence_stage="EDGE_INIT",
            current_boundary=None,
            base_state_id=None,
            base_lifecycle_head=None,
            base_mark_cursor=None,
            base_ledger_cursor=None,
            boundary_mark_cursor=None,
            boundary_mark_ordinal=0,
            boundary_mark_row_cursor=0,
            boundary_ledger_row_cursor=0,
            boundary_ledger_byte_cursor=0,
            boundary_event_cursor=0,
            boundary_terminal_cursor=0,
        )
        return finish(
            next_high, (replay,), stage="OCCURRENCE_EDGE_FINALIZE"
        )

    _fail("selector occurrence edge stage is unsupported")


def _plan_evidence_occurrence_transition(
    *,
    root: Path,
    head: Mapping[str, Any],
    evidence_inputs: EvidenceInputs,
    clock: Callable[[], datetime],
    row_limit: int = 64,
) -> CyclePlan:
    """Plan one occurrence step with every producer read rooted in locked dirfds."""

    if evidence_inputs.mark_root is None or evidence_inputs.lifecycle_root is None:
        _fail("selector occurrence replay requires producer roots")
    mark_root = Path(evidence_inputs.mark_root).expanduser()
    lifecycle_root = Path(evidence_inputs.lifecycle_root).expanduser()
    with _selector_lane(root, create=False) as selector_lane:
        with _anchored_evidence_sources(
            mark_root, lifecycle_root, selector_lane=selector_lane
        ) as sources:
            if head.get("evidence_high_water") is None:
                _fail("selector occurrence replay lacks a pinned high-water")
            high = _load_evidence_high_water(root, head["evidence_high_water"])
            snapshot = _load_pointer(
                root, high["snapshot"], label="selector occurrence source snapshot"
            )
            snapshot = validate_runtime_object(
                snapshot, label="selector occurrence source snapshot"
            )
            if snapshot["producer_roots"] != sources.producer_roots:
                _fail("selector occurrence replay producer roots drifted")
            token = _ACTIVE_EVIDENCE_SOURCES.set(sources)
            try:
                return _plan_evidence_occurrence_transition_core(
                    root=root,
                    head=head,
                    evidence_inputs=evidence_inputs,
                    clock=clock,
                    row_limit=row_limit,
                )
            finally:
                _ACTIVE_EVIDENCE_SOURCES.reset(token)


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
    _sealed_recovery: bool = False,
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
    producer_roots_present = (
        evidence_inputs.mark_root is not None,
        evidence_inputs.lifecycle_root is not None,
    )
    if producer_roots_present[0] is not producer_roots_present[1]:
        _fail("selector evidence capture requires both producer roots")
    if head["pending_manifest"] is not None and all(producer_roots_present):
        high_pointer = head["evidence_high_water"]
        if high_pointer is None:
            return _plan_evidence_capture_transition(
                root=private_root,
                head=head,
                evidence_inputs=evidence_inputs,
                clock=clock,
            )
        high = _load_evidence_high_water(private_root, high_pointer)
        if high["phase"] != "COMPLETE":
            return _plan_evidence_occurrence_transition(
                root=private_root,
                head=head,
                evidence_inputs=evidence_inputs,
                clock=clock,
            )
        manifest = _load_pointer(
            private_root, head["pending_manifest"], label="pending manifest"
        )
        snapshot = validate_runtime_object(
            _load_pointer(
                private_root,
                high["snapshot"],
                label="selector COMPLETE evidence snapshot",
            ),
            label="selector COMPLETE evidence snapshot",
        )
        if (
            _utc(snapshot["captured_at"], label="evidence capture clock")
            < _utc(manifest["frozen_at"], label="manifest freeze clock")
            or (
                not _sealed_recovery
                and not _complete_evidence_is_live(
                    private_root, high_pointer, evidence_inputs
                )
            )
        ):
            return _plan_evidence_capture_transition(
                root=private_root,
                head=head,
                evidence_inputs=evidence_inputs,
                clock=clock,
            )
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
                evidence_session_date=scheduled.astimezone(ET).date().isoformat(),
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
        "evidence_high_water": copy.deepcopy(head["evidence_high_water"]),
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
    if len(ordered_objects) + 1 > MAX_SOURCE_OBJECTS_PER_CYCLE:
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
        "objects": [item.receipt for item in ordered_objects],
        "next_head": next_head,
    }
    intent["intent_sha256"] = _content_id("", intent, field="intent_sha256")
    if (
        len(canonical_bytes(intent)) > MAX_SOURCE_INTENT_BYTES
        or _transition_footprint_bytes(intent, ordered_objects)
        > MAX_SOURCE_INTENT_BYTES
    ):
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
            "evidence_high_water": None,
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
        "evidence_high_water": copy.deepcopy(head["evidence_high_water"]),
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


def _replay_largest_fitting_advance(
    *,
    root: Path,
    source: SourceSnapshot,
    evidence_inputs: EvidenceInputs,
    scheduled_at: str,
    replay_values: Sequence[datetime],
    evidence_snapshot: EvidenceSnapshot | None,
    _sealed_recovery: bool = False,
) -> tuple[CyclePlan, int]:
    """Replay the planner's exact max-first backoff, never a saved prefix cap."""

    if not replay_values:
        _fail("selector intent replay carries no authenticated clocks")
    settlement_cache: dict[str, Any] = {}
    admission_cap = MAX_CANDIDATES_PER_MANIFEST
    while True:
        replay_index = 0

        def replay_clock() -> datetime:
            nonlocal replay_index
            # A terminal settlement-only plan does not retain the extra manifest
            # freeze/completion sample consumed by a larger overflowing attempt.
            # Repeating its authenticated completion is causal and cannot change
            # object counts or canonical byte lengths, which are the only facts
            # needed to prove that the larger prefix did not fit.
            value = (
                replay_values[replay_index]
                if replay_index < len(replay_values)
                else replay_values[-1]
            )
            replay_index += 1
            return value

        try:
            plan = _plan_cycle_once(
                root=root,
                source=source,
                evidence_inputs=evidence_inputs,
                scheduled_at=scheduled_at,
                clock=replay_clock,
                runtime_armed=True,
                admission_cap=admission_cap,
                settlement_cache=settlement_cache,
                evidence_snapshot=evidence_snapshot,
                _sealed_recovery=_sealed_recovery,
            )
            return plan, replay_index
        except _AdvanceBoundExceeded as exc:
            if admission_cap == 0:
                raise SparseSelectorError(
                    "selector recovered settlement cannot fit its authenticated bounds"
                ) from exc
            if admission_cap == 1:
                if settlement_cache:
                    admission_cap = 0
                    continue
                raise SparseSelectorError(
                    "selector recovered admission cannot fit one ordered candidate"
                ) from exc
            admission_cap = max(1, admission_cap // 2)


def _planned_object_from_receipt(
    root: Path,
    receipt: object,
    *,
    label: str,
) -> PlannedObject:
    """Load one pre-staged immutable object from its exact compact receipt."""

    if not isinstance(receipt, Mapping) or set(receipt) != {
        "id",
        "key",
        "sha256",
        "bytes",
    }:
        _fail(f"{label} receipt is malformed")
    item_id = receipt.get("id")
    key = receipt.get("key")
    digest = receipt.get("sha256")
    size = receipt.get("bytes")
    if (
        not isinstance(item_id, str)
        or not item_id
        or not isinstance(key, str)
        or not isinstance(digest, str)
        or _SHA256_RE.fullmatch(digest) is None
        or type(size) is not int
        or not 0 < size <= MAX_OBJECT_BYTES
    ):
        _fail(f"{label} receipt fields are malformed")
    body = _read_private_file(
        _object_path(root, key),
        root=root,
        limit=MAX_OBJECT_BYTES,
        required=True,
    )
    if len(body) != size or _sha256(body) != digest:
        _fail(f"{label} receipt differs from prestaged bytes")
    value = strict_json(body, label=label)
    if not isinstance(value, dict) or canonical_bytes(value) != body:
        _fail(f"{label} object is not canonical JSON")
    item = PlannedObject(key=key, value=value)
    if item.receipt != dict(receipt):
        _fail(f"{label} identity differs from its receipt")
    return item


def _plan_evidence_audit_from_intent(
    root: Path,
    intent: Mapping[str, Any],
    *,
    evidence_inputs: EvidenceInputs | None = None,
) -> CyclePlan:
    expected_fields = {
        "schema",
        "intent_sha256",
        "expected_head_id",
        "expected_advanced_at",
        "expected_source_state",
        "expected_runtime_state",
        "expected_evidence_high_water",
        "audit_window",
        "objects",
        "next_head",
    }
    if set(intent) != expected_fields:
        _fail("selector evidence audit intent fields are malformed")
    clean = copy.deepcopy(dict(intent))
    receipt_keys = (
        [receipt.get("key") for receipt in clean["objects"]]
        if isinstance(clean.get("objects"), list)
        and all(isinstance(receipt, Mapping) for receipt in clean["objects"])
        else []
    )
    if (
        clean["schema"] != "options.sparse_selector_evidence_audit_intent/v1"
        or clean["intent_sha256"]
        != _content_id("", clean, field="intent_sha256")
        or not isinstance(clean["objects"], list)
        or len(clean["objects"]) + 1 > MAX_SOURCE_OBJECTS_PER_CYCLE
        or len(canonical_bytes(clean)) > MAX_SOURCE_INTENT_BYTES
        or len(receipt_keys) != len(clean["objects"])
        or any(not isinstance(key, str) for key in receipt_keys)
        or receipt_keys != sorted(receipt_keys)
    ):
        _fail("selector evidence audit intent identity or bounds drifted")
    objects = tuple(
        _planned_object_from_receipt(
            root, receipt, label="selector evidence audit intent object"
        )
        for receipt in clean["objects"]
    )
    if _transition_footprint_bytes(clean, objects) > MAX_SOURCE_INTENT_BYTES:
        _fail("selector evidence audit intent hides an oversized projection")
    if len({item.key for item in objects}) != len(objects):
        _fail("selector evidence audit intent repeats an object key")
    for item in objects:
        schema = item.value.get("schema")
        if schema in {
            "options.sparse_selector_evidence_source_snapshot/v1",
            "options.sparse_selector_evidence_high_water/v1",
            "options.sparse_selector_evidence_replay_state/v1",
            "options.sparse_selector_evidence_ledger_chunk/v1",
        }:
            validate_runtime_object(item.value, label="selector evidence audit object")
            expected_key = (
                f"{EVIDENCE_AUDIT_NAMESPACE}/{object_identity(item.value)}.json"
            )
        elif schema == private_auth_dict.SCHEMA:
            domain = item.value.get("domain")
            if domain not in {
                EVIDENCE_EVENT_SEEN_DOMAIN,
                EVIDENCE_EVENT_ENROLLMENT_DOMAIN,
                EVIDENCE_EVENT_TERMINAL_DOMAIN,
                EVIDENCE_STATE_ENROLLMENT_DOMAIN,
                EVIDENCE_STATE_TERMINAL_DOMAIN,
                EVIDENCE_MARK_SEEN_DOMAIN,
                EVIDENCE_STATE_LATEST_DOMAIN,
                EVIDENCE_DERIVED_LATEST_DOMAIN,
                EVIDENCE_LEDGER_ROW_DOMAIN,
                EVIDENCE_LEDGER_TERMINAL_DOMAIN,
                EVIDENCE_BOUNDARY_DOMAIN,
            }:
                _fail("selector evidence audit intent contains a foreign auth node")
            private_auth_dict.validate_node(item.value, domain=domain)
            expected_key = (
                f"{private_auth_dict.NAMESPACE}/{item.value['node_id']}.json"
            )
        else:
            _fail("selector evidence audit intent contains a foreign object")
        if item.key != expected_key:
            _fail("selector evidence audit object namespace drifted")

    next_head = validate_runtime_object(
        clean["next_head"], label="selector evidence audit next HEAD"
    )
    expected_head_id = clean["expected_head_id"]
    prior = _load_head(root)
    prior_id = None if prior is None else prior["head_id"]
    if prior_id not in {expected_head_id, next_head["head_id"]}:
        _fail("selector evidence audit intent parent drifted")
    if expected_head_id is None:
        _fail("selector evidence audit cannot initialize source state")
    source_fields = set(_source_expected_state(next_head))
    runtime_fields = set(_runtime_expected_state(next_head))
    if (
        not isinstance(clean["expected_source_state"], Mapping)
        or set(clean["expected_source_state"]) != source_fields
        or not isinstance(clean["expected_runtime_state"], Mapping)
        or set(clean["expected_runtime_state"]) != runtime_fields
        or clean["expected_evidence_high_water"]
        != clean["expected_runtime_state"]["evidence_high_water"]
        or not isinstance(clean["expected_advanced_at"], str)
    ):
        _fail("selector evidence audit parent state receipt is malformed")
    if prior_id == expected_head_id and (
        prior is None
        or _source_expected_state(prior) != clean["expected_source_state"]
        or _runtime_expected_state(prior) != clean["expected_runtime_state"]
        or prior["advanced_at"] != clean["expected_advanced_at"]
    ):
        _fail("selector evidence audit live parent state drifted")
    if _source_expected_state(next_head) != clean["expected_source_state"]:
        _fail("selector evidence audit changed source state")
    next_runtime = _runtime_expected_state(next_head)
    for field in runtime_fields - {"evidence_high_water"}:
        if next_runtime[field] != clean["expected_runtime_state"][field]:
            _fail("selector evidence audit changed runtime state")
    if (
        next_head["previous_head_id"] != expected_head_id
        or next_head["evidence_high_water"]
        == clean["expected_evidence_high_water"]
        or (
            prior_id == expected_head_id
            and prior is not None
            and next_head["generation"] != prior["generation"] + 1
        )
    ):
        _fail("selector evidence audit HEAD transition is not monotone")

    window = clean["audit_window"]
    if not isinstance(window, Mapping):
        _fail("selector evidence audit recovery window is malformed")
    if window.get("stage") != "PIN":
        if (
            not isinstance(window.get("stage"), str)
            or not window["stage"].startswith("OCCURRENCE_")
            or set(window)
            != {"stage", "prior_high_water", "next_high_water", "row_limit"}
            or window["prior_high_water"]
            != clean["expected_evidence_high_water"]
            or next_head["evidence_high_water"] != window["next_high_water"]
            or type(window["row_limit"]) is not int
            or not 1 <= window["row_limit"] <= 128
        ):
            _fail("selector occurrence recovery window is malformed")
        high_waters = [
            item
            for item in objects
            if item.value.get("schema")
            == "options.sparse_selector_evidence_high_water/v1"
        ]
        if (
            len(high_waters) != 1
            or high_waters[0].pointer != window["next_high_water"]
            or high_waters[0].value["snapshot"]
            != _load_evidence_high_water(
                root, window["prior_high_water"]
            )["snapshot"]
        ):
            _fail("selector occurrence recovery high-water is not exact")
        replay_inputs = evidence_inputs or EvidenceInputs()
        if replay_inputs.mark_root is None or replay_inputs.lifecycle_root is None:
            _fail("selector occurrence recovery lacks producer roots")
        synthetic_parent = copy.deepcopy(next_head)
        synthetic_parent.update(copy.deepcopy(clean["expected_source_state"]))
        synthetic_parent.update(copy.deepcopy(clean["expected_runtime_state"]))
        synthetic_parent.update(
            {
                "head_id": expected_head_id,
                "generation": next_head["generation"] - 1,
                "previous_head_id": None,
                "advanced_at": clean["expected_advanced_at"],
            }
        )
        exact = _plan_evidence_occurrence_transition(
            root=root,
            head=synthetic_parent,
            evidence_inputs=replay_inputs,
            clock=lambda: _utc(
                next_head["advanced_at"], label="selector occurrence recovery clock"
            ),
            row_limit=window["row_limit"],
        )
        if (
            exact.expected_head_id != expected_head_id
            or exact.objects != objects
            or exact.head != next_head
            or exact.intent != clean
        ):
            _fail("selector occurrence recovery transition is not exact")
        return exact
    if set(window) != {"stage", "snapshot", "high_water"}:
        _fail("selector evidence PIN window fields are malformed")
    snapshots = [
        item
        for item in objects
        if item.value.get("schema")
        == "options.sparse_selector_evidence_source_snapshot/v1"
    ]
    high_waters = [
        item
        for item in objects
        if item.value.get("schema")
        == "options.sparse_selector_evidence_high_water/v1"
    ]
    if (
        len(objects) != 2
        or len(snapshots) != 1
        or len(high_waters) != 1
        or snapshots[0].pointer != window["snapshot"]
        or high_waters[0].pointer != window["high_water"]
        or high_waters[0].value["phase"] != "AUDIT_PINNED"
        or high_waters[0].value["snapshot"] != snapshots[0].pointer
        or snapshots[0].value["captured_at"] != next_head["advanced_at"]
        or _utc(next_head["advanced_at"], label="evidence audit advance")
        < _utc(clean["expected_advanced_at"], label="evidence audit parent")
        or high_waters[0].value["previous_complete"]
        != clean["expected_evidence_high_water"]
        or next_head["evidence_high_water"] != high_waters[0].pointer
    ):
        _fail("selector evidence PIN transition is not exact")
    previous = high_waters[0].value["previous_complete"]
    if previous is not None:
        prior_high_water = _load_evidence_high_water(root, previous)
        if prior_high_water["phase"] != "COMPLETE":
            _fail("selector evidence PIN parent is not a complete high-water")
    return CyclePlan(
        expected_head_id=expected_head_id,
        objects=objects,
        head=next_head,
        intent=clean,
    )


def _plan_from_intent(
    root: Path,
    intent: Mapping[str, Any],
    *,
    evidence_inputs: EvidenceInputs | None = None,
    _sealed_recovery: bool = False,
) -> CyclePlan:
    if (
        isinstance(intent, Mapping)
        and intent.get("schema")
        == "options.sparse_selector_evidence_audit_intent/v1"
    ):
        return _plan_evidence_audit_from_intent(
            root, intent, evidence_inputs=evidence_inputs
        )
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
            or len(clean["objects"]) + 1 > MAX_SOURCE_OBJECTS_PER_CYCLE
            or len(canonical_bytes(clean)) > MAX_SOURCE_INTENT_BYTES
        ):
            _fail("selector source recovery intent exceeds its bounds")
        objects: list[PlannedObject] = []
        by_pointer_id: dict[str, PlannedObject] = {}
        object_keys: set[str] = set()
        for receipt in clean["objects"]:
            item = _planned_object_from_receipt(
                root, receipt, label="selector source intent object"
            )
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
        or len(clean["objects"]) + 1 > MAX_SOURCE_OBJECTS_PER_CYCLE
        or len(canonical_bytes(clean)) > MAX_SOURCE_INTENT_BYTES
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
        item = _planned_object_from_receipt(
            root, receipt, label="selector advance intent object"
        )
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
    manifest_cache: _PointerObjectCache = {}
    w1a_cache: _W1APublicationCache = {}
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
                manifest_cache=manifest_cache,
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
            settled_manifest = _load_pointer(
                root,
                generation_item.value["settled_manifest"],
                label="selector intent replay settled manifest",
            )
            replay_candidates = tuple(
                _load_pointer(
                    root,
                    pointer,
                    label="selector intent replay evidence candidate",
                )
                for pointer in settled_manifest["candidates"]
            )
            replay_sessions = frozenset(
                _utc(
                    item.value["decision_event_at"],
                    label="selector intent replay evidence session",
                )
                .astimezone(ET)
                .date()
                .isoformat()
                for item in decision_objects
            )
            replay_snapshot = _evidence_snapshot_from_generation(
                generation_item.value,
                evidence_inputs,
                root=root,
                planned_by_key=planned_by_key,
                candidates=replay_candidates,
                session_dates=replay_sessions,
            )
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
        replayed, replay_index = _replay_largest_fitting_advance(
            root=root,
            source=pinned_source,
            evidence_inputs=evidence_inputs,
            scheduled_at=cycle["scheduled_at"],
            replay_values=replay_values,
            evidence_snapshot=replay_snapshot,
            _sealed_recovery=_sealed_recovery,
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


def _validated_intent_attempt(body: bytes) -> dict[str, Any]:
    value = strict_json(body, label="selector advance intent attempt")
    if (
        not isinstance(value, dict)
        or canonical_bytes(value) != body
        or set(value)
        != {
            "schema",
            "expected_head_id",
            "intent_sha256",
            "intent_bytes",
            "recovery_allowed",
        }
        or value.get("schema")
        != "options.sparse_selector_advance_intent_attempt/v1"
        or value.get("recovery_allowed") is not False
        or not isinstance(value.get("intent_sha256"), str)
        or _SHA256_RE.fullmatch(value["intent_sha256"]) is None
        or type(value.get("intent_bytes")) is not int
        or not 0 < value["intent_bytes"] <= MAX_INTENT_BYTES
        or (
            value.get("expected_head_id") is not None
            and (
                not isinstance(value["expected_head_id"], str)
                or re.fullmatch(
                    r"ossh_[a-f0-9]{64}", value["expected_head_id"]
                )
                is None
            )
        )
    ):
        _fail("selector advance intent attempt is malformed")
    return value


def _discard_intent_prepare(root: Path, *, attempt: Mapping[str, Any] | None) -> None:
    lane = _ACTIVE_SELECTOR_LANE.get()
    assert lane is not None
    try:
        metadata = os.stat(
            INTENT_PREPARE_FILE,
            dir_fd=lane.root_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
    ):
        _fail("selector prepared intent metadata is unsafe")
    if attempt is not None:
        prepared = _read_private_file(
            root / INTENT_PREPARE_FILE,
            root=root,
            limit=MAX_INTENT_BYTES,
            required=True,
        )
        if (
            len(prepared) != attempt["intent_bytes"]
            or _sha256(prepared) != attempt["intent_sha256"]
        ):
            _fail("selector prepared intent differs from its durable attempt")
    os.unlink(INTENT_PREPARE_FILE, dir_fd=lane.root_fd)
    os.fsync(lane.root_fd)


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
    if body is None:
        live = _load_head(root)
        parent = "genesis" if live is None else live["head_id"]
        orphan_seal = _read_private_file(
            _object_path(root, f"{INTENT_SEAL_NAMESPACE}/{parent}.json"),
            root=root,
            limit=1024 * 1024,
            required=False,
        )
        if orphan_seal is not None:
            _fail("selector current parent has an orphan authoritative intent seal")
    if body is None and attempt_body is None:
        _discard_intent_prepare(root, attempt=None)
        return None
    if body is None:
        assert attempt_body is not None
        attempt = _validated_intent_attempt(attempt_body)
        live = _load_head(root)
        live_id = None if live is None else live["head_id"]
        if live_id != attempt["expected_head_id"]:
            _fail("selector attempt-only recovery parent changed")
        _discard_intent_prepare(root, attempt=attempt)
        lane = _ACTIVE_SELECTOR_LANE.get()
        assert lane is not None
        os.unlink(INTENT_ATTEMPT_FILE, dir_fd=lane.root_fd)
        os.fsync(lane.root_fd)
        return None
    value = strict_json(body, label="selector advance intent")
    if not isinstance(value, dict) or canonical_bytes(value) != body:
        _fail("selector advance intent is not canonical")
    seal_path = _object_path(root, _intent_seal_key(value))
    expected_attempt = _intent_attempt_body(body)
    if attempt_body is not None and attempt_body != expected_attempt:
        _fail("selector advance intent publication attempt drifted")
    expected_seal = _intent_seal_body(value)
    seal_body = _read_private_file(
        seal_path, root=root, limit=1024 * 1024, required=False
    )
    if seal_body is None:
        if attempt_body != expected_attempt:
            _fail("selector advance intent lacks its publication attempt and seal")
        expected_parent = value.get("expected_head_id")
        live = _load_head(root)
        live_id = None if live is None else live["head_id"]
        if live_id != expected_parent:
            _fail("selector unsealed durable intent is stale")
        # A mutable intent and attempt are never recovery authority.  If the
        # immutable parent seal did not land, abandon them only against the
        # exact unchanged parent and let a fresh plan sample current sources.
        lane = _ACTIVE_SELECTOR_LANE.get()
        assert lane is not None
        os.unlink(INTENT_FILE, dir_fd=lane.root_fd)
        os.unlink(INTENT_ATTEMPT_FILE, dir_fd=lane.root_fd)
        os.fsync(lane.root_fd)
        return None
    if seal_body != expected_seal:
        _fail("selector advance intent differs from its durable recovery seal")
    return value


def _intent_attempt_body(intent_body: bytes) -> bytes:
    value = strict_json(intent_body, label="selector attempted advance intent")
    expected_head_id = value.get("expected_head_id") if isinstance(value, Mapping) else None
    if not isinstance(value, Mapping) or (
        expected_head_id is not None
        and (
            not isinstance(expected_head_id, str)
            or re.fullmatch(r"ossh_[a-f0-9]{64}", expected_head_id) is None
        )
    ):
        _fail("selector attempted advance intent parent is malformed")
    return canonical_bytes(
        {
            "schema": "options.sparse_selector_advance_intent_attempt/v1",
            "expected_head_id": expected_head_id,
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


def _publish_advance_intent(
    root: Path,
    intent: Mapping[str, Any],
    *,
    hook: Callable[[str], None] | None = None,
    pre_authority_check: Callable[[], None] | None = None,
    authority_granted: Callable[[], None] | None = None,
) -> None:
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
        temporary_name=INTENT_PREPARE_FILE,
    )
    try:
        _atomic_write(
            attempt_path,
            _intent_attempt_body(intent_body),
            root=root,
            limit=1024 * 1024,
        )
        if hook is not None:
            hook("after_intent_attempt")
        if pre_authority_check is not None:
            pre_authority_check()
        # If rename or its directory fsync has an uncertain outcome, the
        # already-durable attempt remains and all future recovery fails closed.
        _install_staged_write(
            intent_path,
            temporary,
            intent_body,
            root=root,
            limit=MAX_INTENT_BYTES,
        )
        if hook is not None:
            hook("after_intent_before_seal")
        if pre_authority_check is not None:
            pre_authority_check()
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
        if pre_authority_check is not None:
            pre_authority_check()
        # Publish a parent-keyed immutable seal before granting recovery
        # authority.  It remains for the store lifetime, so an alternate
        # self-consistent intent for the same parent cannot replace history.
        _prestage_immutable(
            _object_path(root, _intent_seal_key(intent)),
            _intent_seal_body(intent),
            root=root,
        )
        if authority_granted is not None:
            authority_granted()
        if hook is not None:
            hook("after_intent_seal")
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


def _is_evidence_pin_plan(plan: CyclePlan | None) -> bool:
    if plan is None or plan.intent.get("schema") != (
        "options.sparse_selector_evidence_audit_intent/v1"
    ):
        return False
    window = plan.intent.get("audit_window")
    return isinstance(window, Mapping) and window.get("stage") == "PIN"


def _is_evidence_settlement_plan(plan: CyclePlan | None) -> bool:
    if (
        plan is None
        or plan.intent.get("schema")
        != "options.sparse_selector_advance_intent/v1"
    ):
        return False
    before = plan.intent.get("expected_decision_count")
    after = plan.head.get("decision_count")
    return (
        type(before) is int
        and type(after) is int
        and after > before
        and plan.head.get("evidence_high_water") is not None
    )


def _validate_live_complete_evidence(
    root: Path,
    high_pointer: Mapping[str, Any],
    evidence_inputs: EvidenceInputs,
    sources: _AnchoredEvidenceSources,
) -> None:
    """Fence a COMPLETE evidence generation against all mutable producer heads."""

    high = _load_evidence_high_water(root, high_pointer)
    if high["phase"] != "COMPLETE":
        _fail("selector settlement evidence high-water is incomplete")
    snapshot = validate_runtime_object(
        _load_pointer(
            root, high["snapshot"], label="selector settlement source snapshot"
        ),
        label="selector settlement source snapshot",
    )
    if sources.producer_roots != snapshot["producer_roots"]:
        raise EvidenceGenerationDrift(
            "selector settlement producer roots changed"
        )
    state_body, state = _read_lifecycle_state_bytes(sources.lifecycle)
    expected_state = snapshot["lifecycle_state"]
    if (
        state != expected_state
        or state_body != lifecycle._canonical_json_bytes(expected_state)
        or _read_anchored_mark_head(sources.mark) != snapshot["live_mark_head"]
        or _read_anchored_ledger_receipt(sources.lifecycle)
        != snapshot["live_ledger_receipt"]
        or _read_anchored_activation_boundary(sources.lifecycle)
        != snapshot["activation_boundary"]
    ):
        raise EvidenceGenerationDrift(
            "selector COMPLETE evidence moved before settlement authority"
        )
    _assert_evidence_lock_identity(sources.mark, sources.mark_lock_fd)
    _assert_evidence_lock_identity(
        sources.lifecycle, sources.lifecycle_lock_fd
    )


def _complete_evidence_is_live(
    root: Path,
    high_pointer: Mapping[str, Any],
    evidence_inputs: EvidenceInputs,
) -> bool:
    if evidence_inputs.mark_root is None or evidence_inputs.lifecycle_root is None:
        _fail("selector settlement requires producer roots")
    mark_root = Path(evidence_inputs.mark_root).expanduser()
    lifecycle_root = Path(evidence_inputs.lifecycle_root).expanduser()
    try:
        with _selector_lane(root, create=False) as selector_lane:
            with _anchored_evidence_sources(
                mark_root, lifecycle_root, selector_lane=selector_lane
            ) as sources:
                _validate_live_complete_evidence(
                    root, high_pointer, evidence_inputs, sources
                )
        return True
    except EvidenceGenerationDrift:
        return False


def _validate_live_evidence_pin(
    root: Path,
    plan: CyclePlan,
    evidence_inputs: EvidenceInputs,
    sources: _AnchoredEvidenceSources,
) -> None:
    snapshots = [
        item
        for item in plan.objects
        if item.value.get("schema")
        == "options.sparse_selector_evidence_source_snapshot/v1"
    ]
    if len(snapshots) != 1:
        _fail("selector evidence PIN lacks one exact source snapshot")
    high_waters = [
        item
        for item in plan.objects
        if item.value.get("schema")
        == "options.sparse_selector_evidence_high_water/v1"
    ]
    if len(high_waters) != 1:
        _fail("selector evidence PIN lacks one exact high-water")
    if evidence_inputs.mark_root is None or evidence_inputs.lifecycle_root is None:
        _fail("selector evidence PIN recovery lacks producer roots")
    previous = high_waters[0].value["previous_complete"]
    prior: dict[str, Any] | None = None
    prior_snapshot: dict[str, Any] | None = None
    if previous is not None:
        prior = _load_evidence_high_water(root, previous)
        prior_snapshot = validate_runtime_object(
            _load_pointer(
                root, prior["snapshot"], label="selector prior source snapshot"
            ),
            label="selector prior source snapshot",
        )
    _assert_evidence_lock_identity(sources.mark, sources.mark_lock_fd)
    _assert_evidence_lock_identity(
        sources.lifecycle, sources.lifecycle_lock_fd
    )
    if sources.producer_roots != snapshots[0].value["producer_roots"]:
        raise EvidenceGenerationDrift(
            "selector producer roots changed before PIN authority"
        )
    state_body, live_state = _read_lifecycle_state_bytes(sources.lifecycle)
    expected_state = snapshots[0].value["lifecycle_state"]
    if (
        state_body != lifecycle._canonical_json_bytes(expected_state)
        or live_state != expected_state
    ):
        raise EvidenceGenerationDrift(
            "selector lifecycle state changed before PIN authority"
        )
    live_mark_head, live_ledger_receipt, activation_boundary = _verify_capture_source_prefixes(
        sources=sources,
        state=expected_state,
        expected_mark_head=snapshots[0].value["live_mark_head"],
        expected_ledger_receipt=snapshots[0].value["live_ledger_receipt"],
        prior_snapshot=prior_snapshot,
    )
    if (
        live_mark_head != snapshots[0].value["live_mark_head"]
        or live_ledger_receipt != snapshots[0].value["live_ledger_receipt"]
        or activation_boundary != snapshots[0].value["activation_boundary"]
    ):
        raise EvidenceGenerationDrift(
            "selector evidence source changed before PIN authority"
        )
    if previous is not None:
        assert prior is not None and prior_snapshot is not None
        if (
            prior["phase"] != "COMPLETE"
            or prior["producer_contract"] != PRODUCER_CONTRACT
            or prior_snapshot["producer_roots"] != sources.producer_roots
        ):
            _fail("selector incremental PIN parent drifted before authority")
        _anchored_mark_chain_contains(
            sources.mark,
            live_mark_head,
            (
                expected_state["mark_cursor"],
                prior_snapshot["live_mark_head"],
            ),
        )
        _anchored_ledger_extends(
            sources.lifecycle, prior_snapshot["live_ledger_receipt"]
        )
        token = _ACTIVE_EVIDENCE_SOURCES.set(sources)
        try:
            _incremental_target_descends(
                Path(evidence_inputs.lifecycle_root).expanduser(),
                prior_state_id=prior["source_state_id"],
                target_state_id=expected_state["state_id"],
            )
        finally:
            _ACTIVE_EVIDENCE_SOURCES.reset(token)
    if _read_anchored_file(
        sources.lifecycle,
        "current.json",
        limit=2 * 1024 * 1024,
        label="selector lifecycle current state",
    ) != state_body:
        raise EvidenceGenerationDrift(
            "selector lifecycle state changed at PIN authority boundary"
        )
    _assert_evidence_lock_identity(sources.mark, sources.mark_lock_fd)
    _assert_evidence_lock_identity(
        sources.lifecycle, sources.lifecycle_lock_fd
    )


def _commit_cycle_locked(
    root: Path,
    plan: CyclePlan | None,
    *,
    evidence_inputs: EvidenceInputs | None = None,
    hook: Callable[[str], None] | None = None,
    trusted_internal_plan: bool = False,
    _w1a_fence_held: bool = False,
    _producer_locks_held: bool = False,
    _producer_sources: _AnchoredEvidenceSources | None = None,
    _objects_batch_durable: bool = False,
    _objects_batch_parent_identities: Mapping[
        Path, tuple[int, int]
    ] | None = None,
) -> dict[str, Any]:
    """Commit or recover one intent while the caller owns the store lock."""

    private_root = root
    existing_intent = _read_intent(private_root)
    batch_parent_identities = _objects_batch_parent_identities
    if existing_intent is not None:
        active = _plan_from_intent(
            private_root,
            existing_intent,
            evidence_inputs=evidence_inputs or EvidenceInputs(),
            _sealed_recovery=True,
        )
        current_head = _load_head(private_root)
        current_id = None if current_head is None else current_head["head_id"]
        if current_id not in {active.expected_head_id, active.head["head_id"]}:
            _fail("selector durable intent is stale before immutable publication")
    else:
        if plan is None:
            _fail("selector has no transition to commit or recover")
        plan_evidence_inputs = evidence_inputs or plan.evidence_inputs
        if (
            len(canonical_bytes(plan.intent)) > MAX_SOURCE_INTENT_BYTES
            or len(plan.objects) + 1 > MAX_SOURCE_OBJECTS_PER_CYCLE
            or _transition_footprint_bytes(plan.intent, plan.objects)
            > MAX_SOURCE_INTENT_BYTES
            or plan.intent.get("objects") != [item.receipt for item in plan.objects]
        ):
            _fail("selector plan does not bind its exact compact object receipts")
        active = plan
        current_head = _load_head(private_root)
        current_head_id = current_head["head_id"] if current_head is not None else None
        evidence_audit = active.intent.get("schema") == (
            "options.sparse_selector_evidence_audit_intent/v1"
        )
        if evidence_audit:
            parent_drifted = (
                current_head_id != active.expected_head_id
                or current_head is None
                or _source_expected_state(current_head)
                != active.intent["expected_source_state"]
                or _runtime_expected_state(current_head)
                != active.intent["expected_runtime_state"]
                or current_head["evidence_high_water"]
                != active.intent["expected_evidence_high_water"]
            )
        else:
            parent_drifted = (
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
            )
        if parent_drifted:
            _fail("selector plan parent changed before intent publication")

        # All content-addressed bodies become durable orphan-safe bytes before
        # the intent grants them authority.  A crash here cannot expose a
        # partial final object and cannot advance HEAD; a retry may exact-adopt
        # complete staged objects.
        if not _objects_batch_durable:
            batch_parent_identities = _prestage_immutable_batch(
                private_root,
                active.objects,
                hook=hook,
            )
        elif batch_parent_identities is None:
            _fail("selector durable object batch lacks its parent identities")

        if not trusted_internal_plan:
            # Once exact bodies are durable, a caller-provided plan must be
            # reconstructed entirely from its parent-bound receipt-only intent.
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

        requires_producer_fence = _is_evidence_pin_plan(
            active
        ) or _is_evidence_settlement_plan(active)
        if requires_producer_fence and not _producer_locks_held:
            if (
                plan_evidence_inputs.mark_root is None
                or plan_evidence_inputs.lifecycle_root is None
            ):
                _fail("selector evidence transition lacks producer roots")
            selector_lane = _ACTIVE_SELECTOR_LANE.get()
            if selector_lane is None:
                _fail("selector evidence transition lacks its anchored store root")
            pin_high: Mapping[str, Any] | None = None
            if _is_evidence_pin_plan(active):
                pin_high = next(
                    item.value
                    for item in active.objects
                    if item.value.get("schema")
                    == "options.sparse_selector_evidence_high_water/v1"
                )
                if pin_high["previous_complete"] is not None:
                    _authenticate_evidence_high_water_graph(
                        private_root,
                        pin_high["previous_complete"],
                        evidence_inputs=plan_evidence_inputs,
                    )
            else:
                assert active.head["evidence_high_water"] is not None
                _authenticate_evidence_high_water_graph(
                    private_root,
                    active.head["evidence_high_water"],
                    evidence_inputs=plan_evidence_inputs,
                )
            mark_root = Path(plan_evidence_inputs.mark_root).expanduser()
            lifecycle_root = Path(
                plan_evidence_inputs.lifecycle_root
            ).expanduser()
            # Receipt-only replay and exact comparison above are complete before
            # any external source lock is taken.  Hold the selector store lock,
            # then W1A, mark, and lifecycle in that order only for the repeated
            # live pre-seal fences and authority boundary.
            with _w1a_commit_fence(
                private_root, active, plan_evidence_inputs
            ):
                with _anchored_evidence_sources(
                    mark_root,
                    lifecycle_root,
                    selector_lane=selector_lane,
                ) as sources:
                    if pin_high is not None:
                        _validate_live_evidence_pin(
                            private_root,
                            active,
                            plan_evidence_inputs,
                            sources,
                        )
                    else:
                        _validate_live_complete_evidence(
                            private_root,
                            active.head["evidence_high_water"],
                            plan_evidence_inputs,
                            sources,
                        )
                    return _commit_cycle_locked(
                        private_root,
                        active,
                        evidence_inputs=plan_evidence_inputs,
                        hook=hook,
                        trusted_internal_plan=True,
                        _w1a_fence_held=True,
                        _producer_locks_held=True,
                        _producer_sources=sources,
                        _objects_batch_durable=True,
                        _objects_batch_parent_identities=batch_parent_identities,
                    )

        if hook is not None:
            hook("after_prestage")

        if _is_evidence_pin_plan(active):
            if not _producer_locks_held or _producer_sources is None:
                _fail("selector evidence PIN lost its producer locks")
            _validate_live_evidence_pin(
                private_root,
                active,
                plan_evidence_inputs,
                _producer_sources,
            )
        elif _is_evidence_settlement_plan(active):
            if not _producer_locks_held or _producer_sources is None:
                _fail("selector settlement lost its producer locks")
            _validate_live_complete_evidence(
                private_root,
                active.head["evidence_high_water"],
                plan_evidence_inputs,
                _producer_sources,
            )
        pre_authority_check: Callable[[], None] | None = None
        authority_granted: Callable[[], None] | None = None
        if _is_evidence_pin_plan(active):
            assert _producer_sources is not None

            def pre_authority_check() -> None:
                _validate_live_evidence_pin(
                    private_root,
                    active,
                    plan_evidence_inputs,
                    _producer_sources,
                )

            def authority_granted() -> None:
                _producer_sources.authority.granted = True

        elif _is_evidence_settlement_plan(active):
            assert _producer_sources is not None

            def pre_authority_check() -> None:
                _validate_live_complete_evidence(
                    private_root,
                    active.head["evidence_high_water"],
                    plan_evidence_inputs,
                    _producer_sources,
                )

            def authority_granted() -> None:
                _producer_sources.authority.granted = True

        def publish_intent() -> None:
            # The batch durability barrier completed before this authority
            # boundary.  Re-read every final name immediately before the WAL
            # publication so a namespace rebind cannot substitute another
            # inode after the batched parent fsyncs.
            _reprove_immutable_batch(
                private_root,
                active.objects,
                label="selector prestaged transition",
                expected_parent_identities=batch_parent_identities,
            )
            _publish_advance_intent(
                private_root,
                active.intent,
                hook=hook,
                pre_authority_check=pre_authority_check,
                authority_granted=authority_granted,
            )

        if _w1a_fence_held:
            publish_intent()
        else:
            with _w1a_commit_fence(
                private_root, active, plan_evidence_inputs
            ):
                publish_intent()
        if hook is not None:
            hook("after_intent")

    current_head = _load_head(private_root)
    if current_head is not None and current_head["head_id"] == active.head["head_id"]:
        # Crash-after-HEAD recovery is adoption, not another publication.  Prove
        # every immutable byte and the complete authenticated graph, then clear
        # only the durable intent.  No object or HEAD write is permitted here.
        _reprove_immutable_batch(
            private_root,
            active.objects,
            label="selector adopted intent object",
        )
        authenticated, _decisions, _body = authenticate_store(
            private_root,
            evidence_inputs=evidence_inputs or active.evidence_inputs,
            _allow_durable_intent=True,
        )
        if authenticated != active.head:
            _fail("selector adopted intent HEAD does not authenticate exactly")
        _clear_advance_intent(private_root, active.intent)
        return active.head

    # An authoritative intent may reference only complete, already durable
    # content-addressed bodies.  Reprove them; never create or rewrite here.
    _reprove_immutable_batch(
        private_root,
        active.objects,
        label="selector prestaged intent object",
    )
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


def status(
    private_root: Path,
    *,
    evidence_inputs: EvidenceInputs | None = None,
) -> dict[str, Any]:
    root = _absolute_private_path(private_root)
    if not root.exists():
        return {
            "runtime_armed": SELECTOR_RUNTIME_ARMED,
            "initialized": False,
            "head": None,
            "recovery_intent": False,
        }
    root = validate_private_root(root, create=False)
    trusted_inputs = evidence_inputs or EvidenceInputs()
    with _store_lock(root):
        intent = _read_intent(root)
        if intent is not None:
            plan = _plan_from_intent(
                root,
                intent,
                evidence_inputs=trusted_inputs,
                _sealed_recovery=True,
            )
            return {
                "runtime_armed": SELECTOR_RUNTIME_ARMED,
                "initialized": True,
                "head": _load_head(root),
                "recovery_intent": True,
                "intent_next_head_id": plan.head["head_id"],
            }
        head, _decisions, _body = authenticate_store(
            root,
            evidence_inputs=trusted_inputs,
        )
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
