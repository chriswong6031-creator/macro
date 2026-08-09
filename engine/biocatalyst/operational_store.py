"""Inert, single-writer operational persistence for BioCatalyst (BC-O1a + O1b).

This module is a durable home for operational bookkeeping and for the forward
evidence ledger: immutable source-run and soak receipts, identity and
endpoint-alignment review queue items, review decisions, correction lineage and
replay metadata (BC-O1a), plus feature snapshots, forecast snapshots, outcome
observations, model registrations, evaluation manifests, contribution traces
and family-clock activation receipts (BC-O1b).  It does not collect, connect to
a source, publish a route, advance a public pointer, run a model, or originate a
probability, a ranking, a score, or a security-identity join.  O1b adds record
kinds to the same single writer; it does not add a second write path.

The substrate mirrors BioCatalyst's own durable idiom rather than importing a
SQL engine: content-addressed immutable objects written with atomic
temp-write + fsync + rename (``publication.atomic_write``) and confirmed by a
SHA-256 readback before the small pointer is moved last
(``storage.mirror_bytes_verified``).  ``append`` is the only way to create a
record; ``rebuild_index`` re-derives lost pointers from those objects and can
never create one.

The state root is always injectable so every test runs under ``tmp_path``.  It
is never created implicitly: an unprovisioned, missing, or unwritable root is a
distinct, catchable UNAVAILABLE failure, not a silent ``mkdir``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping, Sequence

from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
    ValidationIssue,
    canonical_json_bytes,
    canonical_json_sha256,
)


OPERATIONAL_RECORD_CONTRACT_ID = "biocatalyst_operational_record.v1"

# A bump means the on-disk layout changed.  Drift is reported, never guessed at.
STORE_SCHEMA_VERSION = 1
CURRENT_RECORD_SCHEMA_VERSION = "1.0.0"
SUPPORTED_RECORD_SCHEMA_VERSIONS = frozenset({"1.0.0"})

# Production default only.  Nothing in this module creates it.
DEFAULT_PRODUCTION_STATE_ROOT = Path("/var/lib/macro-biocatalyst/state/operational")

STORE_META_FILENAME = "store_meta.json"
OBJECTS_DIRNAME = "objects"
KEYS_DIRNAME = "keys"
INDEX_DIRNAME = "index"

O1A_RECORD_KINDS: tuple[str, ...] = (
    "source_run_receipt",
    "soak_receipt",
    "identity_review_queue_item",
    "endpoint_alignment_review_queue_item",
    "correction_lineage",
    "review_decision",
    "replay_metadata",
)
# BC-O1b: the forward evidence ledger.  Same writer, same idempotency, same
# correction lineage, same replay semantics — only the record kinds are new.
O1B_RECORD_KINDS: tuple[str, ...] = (
    "feature_snapshot",
    "forecast_snapshot",
    "outcome_observation",
    "model_registration",
    "evaluation_manifest",
    "contribution_trace",
    "family_clock_activation",
)
RECORD_KINDS: tuple[str, ...] = O1A_RECORD_KINDS + O1B_RECORD_KINDS

# Receipts, lineage, frozen registrations, pre-registrations and activation
# receipts are facts about something that already happened; they are append-only
# and may never be superseded through the API.
IMMUTABLE_RECORD_KINDS = frozenset(
    {
        "source_run_receipt",
        "soak_receipt",
        "correction_lineage",
        "replay_metadata",
        "model_registration",
        "evaluation_manifest",
        "contribution_trace",
        "family_clock_activation",
    }
)
# Review state, feature snapshots, forecast snapshots and outcome observations
# are corrigible: a correction is a NEW record naming its predecessor.  The
# predecessor object is never rewritten.
CORRIGIBLE_RECORD_KINDS = frozenset(RECORD_KINDS) - IMMUTABLE_RECORD_KINDS

# Near-miss names that are NOT record kinds.  They are enumerated so a caller
# reaching for "forecast" or "prediction" fails closed with a specific code
# instead of being quietly accepted as an unknown kind, and so no future edit
# can introduce a second, differently spelled home for the same evidence.
RESERVED_RECORD_KIND_ALIASES = frozenset(
    {
        "forecast",
        "forecast_record",
        "outcome",
        "outcome_label",
        "evaluation",
        "evaluation_result",
        "prediction",
        "score",
    }
)

# Authority fence: a record carries facts and bookkeeping, never a ranking, a
# size, an escalation, or a security identity join.  Keys are checked as
# substrings so a nested "peer_rank" or "issuer_cik" is refused too.
FORBIDDEN_PAYLOAD_KEY_TOKENS: tuple[str, ...] = (
    "alert",
    "cik",
    "confidence",
    "conviction",
    "cusip",
    "escalat",
    "evaluation",
    "expected_value",
    "figi",
    "forecast",
    "isin",
    "issuer",
    "model_id",
    "position",
    "predict",
    "probabilit",
    "rank",
    "score",
    "sedol",
    "signal",
    "sizing",
    "sponsor",
    "target_price",
    "ticker",
    "weight",
)

# NCT-only fence.  These tokens name a security, an issuer, or a sponsor join
# and are refused in EVERY record kind.  No per-kind allowance may exempt them:
# NCT-keyed facts never authorize an issuer, ticker, or sponsor join by
# inference, so the store must not be able to hold one.
NEVER_ALLOWED_PAYLOAD_KEY_TOKENS = frozenset(
    {"cik", "cusip", "figi", "isin", "issuer", "sedol", "sponsor", "ticker"}
)

# A forecast ledger has to be able to say "forecast".  The allowance is scoped
# to the kinds that structurally need it and covers ONLY that word: probability,
# score, rank, sizing, escalation and identity tokens stay forbidden everywhere,
# in every kind, so an O1b record can name a forward window but can never carry
# a ranking, a size, or an issuer.
KIND_SCOPED_PAYLOAD_KEY_ALLOWANCES: Mapping[str, frozenset[str]] = {
    "forecast_snapshot": frozenset({"forecast"}),
    "evaluation_manifest": frozenset({"evaluation"}),
}

# Payload documents for these kinds are validated against their own contract in
# addition to the record contract, so the forward-ledger shape lives in one
# place instead of being restated inside the record schema.
PAYLOAD_CONTRACT_BY_RECORD_KIND: Mapping[str, str] = {
    "forecast_snapshot": "biocatalyst_forecast_record.v1",
    "outcome_observation": "biocatalyst_outcome_record.v1",
    "family_clock_activation": "biocatalyst_family_clock_activation.v1",
}

# The M0a correction grammar links a revision through ``revision_of``; the O1a
# store links it through ``corrects_record_id``.  For the corrigible O1b kinds
# the two must name the same predecessor, so a revision can never be recorded
# with a lineage the store cannot see.
REVISION_LINKED_RECORD_KINDS = frozenset({"forecast_snapshot", "outcome_observation"})

MAX_QUERY_LIMIT = 200
PAYLOAD_MAX_BYTES = 4096
RECORD_MAX_BYTES = 8192
PAYLOAD_MAX_DEPTH = 6
POINTER_MAX_BYTES = 1024
STORE_META_MAX_BYTES = 1024

_RECORD_ID_RE = re.compile(r"^bcop_[a-f0-9]{32}$", re.ASCII)
_IDEMPOTENCY_KEY_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$", re.ASCII)
_CURSOR_RE = re.compile(r"^[0-9]{8}T[0-9]{12}Z__bcop_[a-f0-9]{32}$", re.ASCII)
_RECORDED_AT_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$", re.ASCII
)

_PAYLOAD_INTERVALS: tuple[tuple[str, str], ...] = (
    ("started_at", "finished_at"),
    ("window_start", "window_end"),
)

# The known-at clock, made executable.  Every pair is "earlier field must not be
# later than the later field", parsed as instants rather than compared as
# strings so a second-precision stamp and a microsecond stamp order correctly.
_PAYLOAD_CLOCK_ORDERS: Mapping[str, tuple[tuple[str, str], ...]] = {
    # M0a ordering_rule: effective_at <= known_at <= observed_at.
    "outcome_observation": (("effective_at", "known_at"), ("known_at", "observed_at")),
    "feature_snapshot": (("evidence_asof", "asof"),),
    "forecast_snapshot": (
        ("evidence_asof", "forecast_made_at"),
        ("forecast_made_at", "resolves_after"),
    ),
    # A clock may start when it is opened or later; never earlier.  An accrual
    # start before the evaluation instant is a backfilled first-seen.
    "family_clock_activation": (("evaluated_at", "accrual_start_known_at"),),
}

# A payload field that may never be later than the record's own recorded_at: a
# fact cannot be observed after it was written down, and a forecast cannot be
# made after it was recorded.
_PAYLOAD_NOT_AFTER_RECORDED_AT: Mapping[str, tuple[str, ...]] = {
    "outcome_observation": ("effective_at", "known_at", "observed_at"),
    "feature_snapshot": ("evidence_asof", "asof"),
    "forecast_snapshot": ("evidence_asof", "forecast_made_at"),
    "model_registration": ("registered_at",),
    "evaluation_manifest": ("preregistered_at",),
    "contribution_trace": ("traced_at",),
    "family_clock_activation": ("evaluated_at",),
}

# A payload field that must be strictly LATER than the record's recorded_at.
# This is the anti-look-ahead fence: a forward window may not be recorded after
# it has already begun to resolve, and a clock may not start before it is
# opened.
_PAYLOAD_AFTER_RECORDED_AT: Mapping[str, tuple[str, ...]] = {
    "forecast_snapshot": ("resolves_after",),
}

# M0a censoring grammar: exactly one rule resolves an outcome, and only that one
# is terminal.  The store refuses any other pairing.
_TERMINAL_CENSORING_STATES = frozenset({"not_censored_terminal_event"})


class OperationalStoreError(RuntimeError):
    """A deliberately bounded operational-store failure code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OperationalStoreUnavailableError(OperationalStoreError):
    """The state root is missing, unprovisioned, or unwritable."""


class OperationalStoreSchemaVersionError(OperationalStoreError):
    """An on-disk store or record declares a schema version this build cannot read."""


class OperationalStoreConflictError(OperationalStoreError):
    """An idempotency key or a content-addressed object was reused for other bytes."""


class OperationalStoreCorruptionError(OperationalStoreError):
    """An on-disk object does not match its own content address."""


@dataclass(frozen=True)
class AppendReceipt:
    """The outcome of one ``append`` call."""

    record_id: str
    record_kind: str
    cursor: str
    record_sha256: str
    created: bool


@dataclass(frozen=True)
class QueryPage:
    """One bounded page of records; ``next_cursor`` is None at the end."""

    records: tuple[dict[str, Any], ...]
    next_cursor: str | None


@dataclass(frozen=True)
class RebuildReport:
    """Counts from re-deriving pointers and index entries from objects."""

    object_count: int
    index_entries_written: int
    key_pointers_written: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise OperationalStoreError("OPERATIONAL_CLOCK_INVALID")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, payload: bytes) -> None:
    """Durably create a file without ever exposing partial bytes.

    This is the module's only writer.  A failure between the temp write and the
    rename leaves the temp file unlinked and the destination absent, so a
    partially written record is never visible to a reader.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def forbidden_payload_key_tokens_for(record_kind: Any) -> tuple[str, ...]:
    """Return the tokens refused in one record kind's payload keys.

    A kind-scoped allowance may exempt a token only if it is not in
    ``NEVER_ALLOWED_PAYLOAD_KEY_TOKENS``; the identity-join tokens cannot be
    switched off by any allowance, present or future.
    """

    allowed = KIND_SCOPED_PAYLOAD_KEY_ALLOWANCES.get(record_kind, frozenset())
    effective = allowed - NEVER_ALLOWED_PAYLOAD_KEY_TOKENS
    return tuple(
        token for token in FORBIDDEN_PAYLOAD_KEY_TOKENS if token not in effective
    )


def _forbidden_key_tokens(
    value: Any, tokens: Sequence[str], depth: int = 0
) -> tuple[list[str], bool]:
    """Return forbidden key tokens found, and whether the depth cap was hit."""

    if depth > PAYLOAD_MAX_DEPTH:
        return [], True
    found: list[str] = []
    too_deep = False
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str):
                lowered = key.lower()
                found.extend(token for token in tokens if token in lowered)
            nested_found, nested_deep = _forbidden_key_tokens(nested, tokens, depth + 1)
            found.extend(nested_found)
            too_deep = too_deep or nested_deep
    elif isinstance(value, list):
        for nested in value:
            nested_found, nested_deep = _forbidden_key_tokens(nested, tokens, depth + 1)
            found.extend(nested_found)
            too_deep = too_deep or nested_deep
    return found, too_deep


def _instant(value: Any) -> datetime | None:
    """Parse one UTC Z timestamp, or return None when it is not one."""

    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _clock_issues(
    record_kind: Any, payload: Mapping[str, Any], recorded_at: Any
) -> list[ValidationIssue]:
    """Return every known-at clock violation for one payload.

    These are the look-ahead fences: a fact may not be known before it was
    knowable, observed after it was written down, or forecast for a window that
    has already begun to resolve.
    """

    issues: list[ValidationIssue] = []
    for earlier, later in _PAYLOAD_CLOCK_ORDERS.get(record_kind, ()):
        first = _instant(payload.get(earlier))
        second = _instant(payload.get(later))
        if first is not None and second is not None and first > second:
            issues.append(
                _issue(
                    f"$.payload.{later}",
                    "operational_record.clock_order",
                    f"{earlier} must not be later than {later}",
                )
            )
    written = _instant(recorded_at)
    if written is None:
        return issues
    for field in _PAYLOAD_NOT_AFTER_RECORDED_AT.get(record_kind, ()):
        stamp = _instant(payload.get(field))
        if stamp is not None and stamp > written:
            issues.append(
                _issue(
                    f"$.payload.{field}",
                    "operational_record.clock_after_recorded_at",
                    f"{field} must not be later than recorded_at",
                )
            )
    for field in _PAYLOAD_AFTER_RECORDED_AT.get(record_kind, ()):
        stamp = _instant(payload.get(field))
        if stamp is not None and stamp <= written:
            issues.append(
                _issue(
                    f"$.payload.{field}",
                    "operational_record.window_already_resolving",
                    f"{field} must be later than recorded_at; a forward window may "
                    "not be recorded once it has begun to resolve",
                )
            )
    return issues


def _o1b_semantic_issues(
    record_kind: Any, payload: Mapping[str, Any], document: Mapping[str, Any]
) -> list[ValidationIssue]:
    """Return the forward-ledger semantics the record schema cannot express."""

    issues: list[ValidationIssue] = []

    if record_kind in REVISION_LINKED_RECORD_KINDS:
        # M0a links a revision through revision_of; O1a links it through
        # corrects_record_id.  A revision the store cannot see is not a revision.
        if payload.get("revision_of") != document.get("corrects_record_id"):
            issues.append(
                _issue(
                    "$.payload.revision_of",
                    "operational_record.revision_link",
                    "revision_of must name the same predecessor as corrects_record_id",
                )
            )

    if record_kind == "outcome_observation":
        censoring_state = payload.get("censoring_state")
        terminality = payload.get("terminality")
        if isinstance(censoring_state, str) and isinstance(terminality, str):
            expected = (
                "terminal"
                if censoring_state in _TERMINAL_CENSORING_STATES
                else "non_terminal"
            )
            if terminality != expected:
                issues.append(
                    _issue(
                        "$.payload.terminality",
                        "operational_record.censoring_terminality",
                        "only a terminal source statement is terminal; a censored "
                        "observation is never a resolved outcome",
                    )
                )

    if record_kind == "family_clock_activation":
        clock_state = payload.get("clock_state")
        blockers = payload.get("blockers")
        unsatisfied = payload.get("unsatisfied_preconditions")
        started = payload.get("accrual_start_known_at")
        if clock_state == "opened":
            if blockers or unsatisfied:
                issues.append(
                    _issue(
                        "$.payload.clock_state",
                        "operational_record.clock_opened_with_blockers",
                        "a clock may not be recorded open while a precondition is "
                        "unsatisfied or a blocker stands",
                    )
                )
            if started is None:
                issues.append(
                    _issue(
                        "$.payload.accrual_start_known_at",
                        "operational_record.clock_open_without_start",
                        "an open clock must record the known-at instant it starts accruing from",
                    )
                )
        elif clock_state == "closed":
            if not blockers:
                issues.append(
                    _issue(
                        "$.payload.blockers",
                        "operational_record.clock_closed_without_blocker",
                        "a closed clock must name at least one blocker",
                    )
                )
            if started is not None:
                issues.append(
                    _issue(
                        "$.payload.accrual_start_known_at",
                        "operational_record.closed_clock_accrual_start",
                        "a closed clock accrues nothing and may not claim a start",
                    )
                )
    return issues


def operational_record_identity_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical payload the record id is derived from."""

    return {key: value for key, value in document.items() if key != "record_id"}


def operational_record_id(document: Mapping[str, Any]) -> str:
    """Derive the content-addressed record id for one operational record."""

    digest = canonical_json_sha256(operational_record_identity_payload(document))
    return f"bcop_{digest[:32]}"


def operational_record_semantic_issues(
    document: Mapping[str, Any],
) -> list[ValidationIssue]:
    """Return deterministic semantic failures for one operational record."""

    if not isinstance(document, Mapping):
        return [_issue("$", "operational_record.document", "record must be a JSON object")]
    issues: list[ValidationIssue] = []

    record_kind = document.get("record_kind")
    if record_kind in RESERVED_RECORD_KIND_ALIASES:
        issues.append(
            _issue(
                "$.record_kind",
                "operational_record.reserved_alias",
                "that name is a reserved alias, not a record kind; use the canonical "
                "O1b kind so one kind of evidence has exactly one home",
            )
        )
    elif record_kind not in RECORD_KINDS:
        issues.append(
            _issue(
                "$.record_kind",
                "operational_record.kind",
                "record_kind must be one of the declared O1a or O1b kinds",
            )
        )

    version = document.get("record_schema_version")
    if version not in SUPPORTED_RECORD_SCHEMA_VERSIONS:
        issues.append(
            _issue(
                "$.record_schema_version",
                "operational_record.record_schema_version",
                f"record_schema_version must be one of {sorted(SUPPORTED_RECORD_SCHEMA_VERSIONS)}",
            )
        )

    corrects = document.get("corrects_record_id")
    if corrects is not None:
        if record_kind not in CORRIGIBLE_RECORD_KINDS:
            issues.append(
                _issue(
                    "$.corrects_record_id",
                    "operational_record.immutable_kind",
                    "receipt and lineage kinds are append-only and may not be corrected",
                )
            )
        if document.get("record_id") == corrects:
            issues.append(
                _issue(
                    "$.corrects_record_id",
                    "operational_record.self_correction",
                    "a record may not correct itself",
                )
            )

    if not isinstance(document.get("idempotency_key"), str) or not _IDEMPOTENCY_KEY_RE.fullmatch(
        str(document.get("idempotency_key"))
    ):
        issues.append(
            _issue(
                "$.idempotency_key",
                "operational_record.idempotency_key",
                "idempotency_key must be a bounded lowercase ASCII token",
            )
        )

    recorded_at = document.get("recorded_at")
    if not isinstance(recorded_at, str) or not _RECORDED_AT_RE.fullmatch(recorded_at):
        issues.append(
            _issue(
                "$.recorded_at",
                "operational_record.recorded_at",
                "recorded_at must be a microsecond UTC Z timestamp",
            )
        )

    payload = document.get("payload")
    if not isinstance(payload, Mapping):
        issues.append(
            _issue("$.payload", "operational_record.payload", "payload must be a JSON object")
        )
        return sorted(set(issues))

    forbidden_tokens, too_deep = _forbidden_key_tokens(
        payload, forbidden_payload_key_tokens_for(record_kind)
    )
    if too_deep:
        issues.append(
            _issue(
                "$.payload",
                "operational_record.payload_depth",
                f"payload must not nest deeper than {PAYLOAD_MAX_DEPTH} levels",
            )
        )
    forbidden = sorted(set(forbidden_tokens))
    if forbidden:
        issues.append(
            _issue(
                "$.payload",
                "operational_record.authority_fence",
                "payload keys may not name scores, rankings, sizing, forecasts, or security identity: "
                + ", ".join(forbidden),
            )
        )

    for first, second in _PAYLOAD_INTERVALS:
        start = payload.get(first)
        end = payload.get(second)
        if isinstance(start, str) and isinstance(end, str) and start > end:
            issues.append(
                _issue(
                    f"$.payload.{second}",
                    "operational_record.interval",
                    f"{first} must not be later than {second}",
                )
            )

    issues.extend(_clock_issues(record_kind, payload, recorded_at))
    issues.extend(_o1b_semantic_issues(record_kind, payload, document))

    try:
        payload_bytes = canonical_json_bytes(payload)
        record_bytes = canonical_json_bytes(document)
    except Exception:
        return sorted(
            set(
                issues
                + [
                    _issue(
                        "$",
                        "operational_record.canonical_payload",
                        "record must be finite canonical JSON",
                    )
                ]
            )
        )
    if len(payload_bytes) > PAYLOAD_MAX_BYTES:
        issues.append(
            _issue(
                "$.payload",
                "operational_record.payload_bytes",
                f"payload must not exceed {PAYLOAD_MAX_BYTES} canonical bytes",
            )
        )
    if len(record_bytes) > RECORD_MAX_BYTES:
        issues.append(
            _issue(
                "$",
                "operational_record.record_bytes",
                f"record must not exceed {RECORD_MAX_BYTES} canonical bytes",
            )
        )

    if document.get("record_id") != operational_record_id(document):
        issues.append(
            _issue(
                "$.record_id",
                "operational_record.identity",
                "record_id must be the content address of the canonical payload excluding record_id",
            )
        )
    return sorted(set(issues))


def validate_operational_record(
    document: Any, *, repo_root: Path | str | None = None
) -> None:
    """Fail closed unless schema and BC-O1a semantic controls both hold."""

    registry = ContractRegistry(repo_root)
    schema_issues = list(registry.issues(OPERATIONAL_RECORD_CONTRACT_ID, document))
    semantic_issues = (
        operational_record_semantic_issues(document)
        if isinstance(document, Mapping)
        else [_issue("$", "operational_record.document", "record must be a JSON object")]
    )
    if isinstance(document, Mapping):
        payload_contract_id = PAYLOAD_CONTRACT_BY_RECORD_KIND.get(
            document.get("record_kind")
        )
        if payload_contract_id is not None:
            payload = document.get("payload")
            for issue in registry.issues(payload_contract_id, payload):
                # Re-root the payload contract's paths so one failure report
                # names the field inside the record it was written to.
                semantic_issues.append(
                    _issue(
                        "$.payload" + issue.path.lstrip("$"),
                        issue.code,
                        issue.message,
                    )
                )
    issues = tuple(sorted(set(schema_issues + semantic_issues)))
    if issues:
        raise ContractValidationError(OPERATIONAL_RECORD_CONTRACT_ID, issues)


def build_operational_record(
    record_kind: str,
    payload: Mapping[str, Any],
    *,
    idempotency_key: str,
    recorded_at: str,
    corrects_record_id: str | None = None,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Construct and validate one operational record without persisting it."""

    if not isinstance(payload, Mapping) or type(payload) is not dict:
        # A dict subclass can make get/items disagree; take a plain snapshot.
        try:
            payload = json.loads(canonical_json_bytes(payload).decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - bounded, code-only surface
            raise OperationalStoreError("OPERATIONAL_PAYLOAD_INVALID") from exc
        if type(payload) is not dict:
            raise OperationalStoreError("OPERATIONAL_PAYLOAD_INVALID")
    document: dict[str, Any] = {
        "contract_id": OPERATIONAL_RECORD_CONTRACT_ID,
        "schema_version": "1.0.0",
        "record_schema_version": CURRENT_RECORD_SCHEMA_VERSION,
        "record_kind": record_kind,
        "idempotency_key": idempotency_key,
        "recorded_at": recorded_at,
        "corrects_record_id": corrects_record_id,
        "authority": "facts_and_context_only",
        "payload": dict(payload),
        "hash_scope": "canonical_payload_excluding_record_id",
    }
    document["record_id"] = operational_record_id(document)
    validate_operational_record(document, repo_root=repo_root)
    return document


def cursor_for(document: Mapping[str, Any]) -> str:
    """Return the deterministic total-order cursor for one record.

    ISO timestamps sort lexicographically, so ``<compact recorded_at>__<record
    id>`` gives a stable chronological order with a content-addressed tiebreak
    and needs no writer-held counter.
    """

    recorded_at = document.get("recorded_at")
    record_id = document.get("record_id")
    if not isinstance(recorded_at, str) or not _RECORDED_AT_RE.fullmatch(recorded_at):
        raise OperationalStoreError("OPERATIONAL_RECORD_INVALID")
    if not isinstance(record_id, str) or not _RECORD_ID_RE.fullmatch(record_id):
        raise OperationalStoreError("OPERATIONAL_RECORD_INVALID")
    compact = recorded_at.replace("-", "").replace(":", "").replace(".", "").replace("Z", "")
    return f"{compact}Z__{record_id}"


def _store_meta_bytes() -> bytes:
    return canonical_json_bytes(
        {
            "store": "biocatalyst_operational_store",
            "store_schema_version": STORE_SCHEMA_VERSION,
            "record_contract_id": OPERATIONAL_RECORD_CONTRACT_ID,
            "authority": "facts_and_context_only",
        }
    )


def provision_operational_store(state_root: Path | str) -> Path:
    """Create one empty operational state root.

    Provisioning is an explicit, separate act.  ``OperationalStore`` never
    creates its root, so a production process pointed at a missing or
    unmounted path fails closed instead of silently starting an empty ledger.
    """

    root = Path(state_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        for name in (OBJECTS_DIRNAME, KEYS_DIRNAME, INDEX_DIRNAME):
            (root / name).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OperationalStoreUnavailableError("OPERATIONAL_STATE_ROOT_UNWRITABLE") from exc
    _atomic_write(root / STORE_META_FILENAME, _store_meta_bytes())
    return root.resolve()


def _read_bounded_json(path: Path, limit: int, *, code: str) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise OperationalStoreError(code) from exc
    if size > limit:
        raise OperationalStoreError(code)

    def reject_constant(_: str) -> None:
        raise ValueError("non-finite JSON number")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, value in pairs:
            if key in payload:
                raise ValueError("duplicate JSON object key")
            payload[key] = value
        return payload

    try:
        parsed = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise OperationalStoreError(code) from exc
    if type(parsed) is not dict:
        raise OperationalStoreError(code)
    return parsed


class OperationalStore:
    """The single writer and bounded reader for the BC-O1a operational root.

    ``append`` is the only way a record object is created.  There is no update,
    overwrite, or delete method, and none may be added: receipts are append-only
    and corrigible kinds are superseded by NEW records that name a predecessor.
    """

    def __init__(
        self,
        state_root: Path | str,
        *,
        now_fn: Callable[[], datetime] | None = None,
        repo_root: Path | str | None = None,
    ) -> None:
        self._state_root = Path(state_root)
        self._now_fn = now_fn if now_fn is not None else _utc_now
        self._repo_root = repo_root

    @property
    def state_root(self) -> Path:
        return self._state_root

    # ---- availability -------------------------------------------------

    def _available_root(self, *, for_write: bool) -> Path:
        root = self._state_root
        if not root.is_dir():
            raise OperationalStoreUnavailableError("OPERATIONAL_STATE_ROOT_MISSING")
        meta_path = root / STORE_META_FILENAME
        if not meta_path.is_file():
            raise OperationalStoreUnavailableError("OPERATIONAL_STATE_ROOT_NOT_PROVISIONED")
        meta = _read_bounded_json(
            meta_path, STORE_META_MAX_BYTES, code="OPERATIONAL_STATE_META_UNREADABLE"
        )
        declared = meta.get("store_schema_version")
        if declared != STORE_SCHEMA_VERSION:
            raise OperationalStoreSchemaVersionError("STORE_SCHEMA_VERSION_DRIFT")
        if meta.get("record_contract_id") != OPERATIONAL_RECORD_CONTRACT_ID:
            raise OperationalStoreSchemaVersionError("STORE_RECORD_CONTRACT_DRIFT")
        if for_write and not os.access(root, os.W_OK | os.X_OK):
            raise OperationalStoreUnavailableError("OPERATIONAL_STATE_ROOT_UNWRITABLE")
        return root

    # ---- paths --------------------------------------------------------

    def _object_path(self, root: Path, record_kind: str, record_id: str) -> Path:
        return root / OBJECTS_DIRNAME / record_kind / record_id[5:7] / f"{record_id}.json"

    def _key_pointer_path(self, root: Path, record_kind: str, idempotency_key: str) -> Path:
        digest = sha256(idempotency_key.encode("utf-8")).hexdigest()
        return root / KEYS_DIRNAME / record_kind / digest[:2] / f"{digest}.json"

    def _index_path(self, root: Path, record_kind: str, cursor: str) -> Path:
        return root / INDEX_DIRNAME / record_kind / f"{cursor}.json"

    # ---- reads --------------------------------------------------------

    def _load_record(self, path: Path) -> dict[str, Any]:
        document = _read_bounded_json(
            path, RECORD_MAX_BYTES, code="OPERATIONAL_RECORD_UNREADABLE"
        )
        version = document.get("record_schema_version")
        if version not in SUPPORTED_RECORD_SCHEMA_VERSIONS:
            raise OperationalStoreSchemaVersionError("RECORD_SCHEMA_VERSION_UNSUPPORTED")
        if document.get("record_id") != operational_record_id(document):
            raise OperationalStoreCorruptionError("RECORD_OBJECT_CORRUPT")
        return document

    def get(self, record_kind: str, record_id: str) -> dict[str, Any]:
        """Return one record by its content address, or fail closed."""

        root = self._available_root(for_write=False)
        if record_kind not in RECORD_KINDS:
            raise OperationalStoreError("OPERATIONAL_RECORD_KIND_UNKNOWN")
        if not isinstance(record_id, str) or not _RECORD_ID_RE.fullmatch(record_id):
            raise OperationalStoreError("OPERATIONAL_RECORD_ID_INVALID")
        path = self._object_path(root, record_kind, record_id)
        if not path.is_file():
            raise OperationalStoreError("OPERATIONAL_RECORD_NOT_FOUND")
        return self._load_record(path)

    def read(
        self, record_kind: str, *, limit: int, cursor: str | None = None
    ) -> QueryPage:
        """Return one bounded page of records after ``cursor``.

        ``limit`` is required and capped: there is no unbounded read.
        """

        root = self._available_root(for_write=False)
        if record_kind not in RECORD_KINDS:
            raise OperationalStoreError("OPERATIONAL_RECORD_KIND_UNKNOWN")
        if type(limit) is not int or not 1 <= limit <= MAX_QUERY_LIMIT:
            raise OperationalStoreError("OPERATIONAL_QUERY_LIMIT_INVALID")
        if cursor is not None and (
            not isinstance(cursor, str) or not _CURSOR_RE.fullmatch(cursor)
        ):
            raise OperationalStoreError("OPERATIONAL_QUERY_CURSOR_INVALID")
        cursors = self._cursors(root, record_kind)
        remaining = [entry for entry in cursors if cursor is None or entry > cursor]
        page = remaining[:limit]
        records = tuple(
            self._load_record(self._object_path(root, record_kind, entry.split("__", 1)[1]))
            for entry in page
        )
        next_cursor = page[-1] if page and len(remaining) > len(page) else None
        return QueryPage(records=records, next_cursor=next_cursor)

    def _cursors(self, root: Path, record_kind: str) -> tuple[str, ...]:
        directory = root / INDEX_DIRNAME / record_kind
        if not directory.is_dir():
            return ()
        entries = []
        for path in directory.iterdir():
            if path.suffix != ".json" or not path.is_file():
                continue
            stem = path.name[: -len(".json")]
            if _CURSOR_RE.fullmatch(stem):
                entries.append(stem)
        return tuple(sorted(entries))

    def replay_digest(
        self, record_kind: str, *, limit: int, cursor: str | None = None
    ) -> str:
        """Return a deterministic digest of one bounded replay window."""

        page = self.read(record_kind, limit=limit, cursor=cursor)
        return canonical_json_sha256(
            [
                [cursor_for(document), document["record_id"]]
                for document in page.records
            ]
        )

    # ---- the single write path ----------------------------------------

    def _put_record_object(self, path: Path, payload: bytes, digest: str) -> bool:
        """Create one immutable record object; verify by SHA-256 readback.

        Returns True when this call created the object, False when a
        byte-identical object was already present.  Different bytes at the same
        content address is a hard conflict.
        """

        if path.is_file():
            existing = path.read_bytes()
            if existing != payload or sha256(existing).hexdigest() != digest:
                raise OperationalStoreConflictError("IMMUTABLE_OBJECT_COLLISION")
            return False
        _atomic_write(path, payload)
        readback = path.read_bytes()
        if readback != payload or sha256(readback).hexdigest() != digest:
            raise OperationalStoreCorruptionError("OPERATIONAL_RECORD_READBACK_FAILED")
        return True

    def _put_pointer(self, path: Path, payload: bytes) -> bool:
        """Create one derived pointer (index entry or idempotency key)."""

        if path.is_file():
            return False
        _atomic_write(path, payload)
        return True

    def append(
        self,
        record_kind: str,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str,
        corrects_record_id: str | None = None,
        recorded_at: str | None = None,
    ) -> AppendReceipt:
        """Append one operational record.  This is the only record writer.

        Writing the same logical record twice is a no-op that returns the same
        content-addressed id.  Writing different bytes under an already-used
        idempotency key fails closed.
        """

        root = self._available_root(for_write=True)
        if record_kind in RESERVED_RECORD_KIND_ALIASES:
            raise OperationalStoreError("OPERATIONAL_RECORD_KIND_RESERVED_ALIAS")
        if record_kind not in RECORD_KINDS:
            raise OperationalStoreError("OPERATIONAL_RECORD_KIND_UNKNOWN")
        if not isinstance(idempotency_key, str) or not _IDEMPOTENCY_KEY_RE.fullmatch(
            idempotency_key
        ):
            raise OperationalStoreError("OPERATIONAL_IDEMPOTENCY_KEY_INVALID")

        if corrects_record_id is not None:
            if record_kind not in CORRIGIBLE_RECORD_KINDS:
                raise OperationalStoreError("OPERATIONAL_RECORD_KIND_NOT_CORRIGIBLE")
            if not isinstance(corrects_record_id, str) or not _RECORD_ID_RE.fullmatch(
                corrects_record_id
            ):
                raise OperationalStoreError("OPERATIONAL_RECORD_ID_INVALID")
            predecessor = self._object_path(root, record_kind, corrects_record_id)
            if not predecessor.is_file():
                raise OperationalStoreError("OPERATIONAL_CORRECTION_PREDECESSOR_MISSING")

        stamp = recorded_at if recorded_at is not None else _iso(self._now_fn())
        document = build_operational_record(
            record_kind,
            payload,
            idempotency_key=idempotency_key,
            recorded_at=stamp,
            corrects_record_id=corrects_record_id,
            repo_root=self._repo_root,
        )
        record_id = document["record_id"]
        record_bytes = canonical_json_bytes(document)
        digest = sha256(record_bytes).hexdigest()
        cursor = cursor_for(document)

        key_path = self._key_pointer_path(root, record_kind, idempotency_key)
        if key_path.is_file():
            pointer = _read_bounded_json(
                key_path, POINTER_MAX_BYTES, code="OPERATIONAL_POINTER_UNREADABLE"
            )
            if pointer.get("record_id") != record_id:
                raise OperationalStoreConflictError("OPERATIONAL_IDEMPOTENCY_KEY_CONFLICT")

        created = self._put_record_object(
            self._object_path(root, record_kind, record_id), record_bytes, digest
        )
        self._put_pointer(
            self._index_path(root, record_kind, cursor),
            canonical_json_bytes({"record_id": record_id, "record_kind": record_kind}),
        )
        # The small idempotency pointer moves last, so an interrupted append is
        # retried into the same content address rather than a second record.
        self._put_pointer(
            key_path,
            canonical_json_bytes(
                {
                    "record_id": record_id,
                    "record_kind": record_kind,
                    "record_sha256": digest,
                }
            ),
        )
        return AppendReceipt(
            record_id=record_id,
            record_kind=record_kind,
            cursor=cursor,
            record_sha256=digest,
            created=created,
        )

    # ---- derived-state recovery ---------------------------------------

    def rebuild_index(self) -> RebuildReport:
        """Re-derive index entries and key pointers from the objects tree.

        This never creates, mutates, or removes a record object; it only
        reconstructs the derived pointers a reader needs, so a store rebuilt
        from its own on-disk objects yields identical reads.
        """

        root = self._available_root(for_write=True)
        objects = 0
        index_written = 0
        keys_written = 0
        for record_kind in RECORD_KINDS:
            directory = root / OBJECTS_DIRNAME / record_kind
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*.json")):
                if not path.is_file():
                    continue
                document = self._load_record(path)
                objects += 1
                if self._put_pointer(
                    self._index_path(root, record_kind, cursor_for(document)),
                    canonical_json_bytes(
                        {"record_id": document["record_id"], "record_kind": record_kind}
                    ),
                ):
                    index_written += 1
                if self._put_pointer(
                    self._key_pointer_path(root, record_kind, document["idempotency_key"]),
                    canonical_json_bytes(
                        {
                            "record_id": document["record_id"],
                            "record_kind": record_kind,
                            "record_sha256": sha256(
                                canonical_json_bytes(document)
                            ).hexdigest(),
                        }
                    ),
                ):
                    keys_written += 1
        return RebuildReport(
            object_count=objects,
            index_entries_written=index_written,
            key_pointers_written=keys_written,
        )


def replay_sequence(
    store: OperationalStore, appends: Sequence[Mapping[str, Any]]
) -> tuple[str, ...]:
    """Apply an append sequence in order and return the record ids produced.

    Replaying the same sequence into a fresh root is deterministic: record ids
    are content addresses, so identical inputs give identical ids and cursors.
    """

    produced: list[str] = []
    for entry in appends:
        receipt = store.append(
            entry["record_kind"],
            entry["payload"],
            idempotency_key=entry["idempotency_key"],
            corrects_record_id=entry.get("corrects_record_id"),
            recorded_at=entry.get("recorded_at"),
        )
        produced.append(receipt.record_id)
    return tuple(produced)
