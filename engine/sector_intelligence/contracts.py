"""Discovery, validation, and hashing for sector-intelligence contracts.

The registry is deliberately fail-closed: only schemas in the two owned
contract directories are discoverable, contract identifiers are the explicit
``properties.contract_id.const`` values, and duplicate identifiers abort the
entire registry build.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


_SCHEMA_DIRECTORIES = (
    Path("contracts/sector_intelligence"),
    Path("contracts/biocatalyst"),
)
_DRAFT_2020_12_URIS = frozenset(
    (
        "https://json-schema.org/draft/2020-12/schema",
        "https://json-schema.org/draft/2020-12/schema#",
    )
)
_CONTRACT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)*\.v[1-9][0-9]*$")
_JSON_PATH_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PACKET_CONTRACT_ID = "sector_intelligence_packet.v1"
_ONTOLOGY_CONTRACT_ID = "biocatalyst_ontology.v1"
_CTGOV_FETCH_RUN_CONTRACT_ID = "ctgov_fetch_run.v1"
_CTGOV_WATERMARK_CONTRACT_ID = "ctgov_watermark.v1"
_PAGE_RECEIPT_CONTRACT_ID = "source_page_receipt.v1"
_TRIAL_SOURCE_SNAPSHOT_CONTRACT_ID = "trial_source_snapshot.v1"
_TRIAL_OBSERVATION_CONTRACT_ID = "trial_snapshot_observation.v1"
_TRIAL_SNAPSHOT_CONTRACT_ID = "trial_snapshot.v1"
_TRIAL_DIFF_CONTRACT_ID = "trial_version_diff.v1"
_TRIAL_COVERAGE_CONTRACT_ID = "trial_coverage_epoch.v1"
_SOURCE_RECORD_CONTRACT_ID = "source_record.v1"
_EVIDENCE_CLAIM_CONTRACT_ID = "evidence_claim.v1"
_FEATURE_SNAPSHOT_CONTRACT_ID = "feature_snapshot.v1"
_PREDICTION_CONTRACT_ID = "prediction.v1"
_OUTCOME_LABEL_CONTRACT_ID = "outcome_label.v1"
_AUTHORITY_MANIFEST_CONTRACT_ID = "authority_manifest.v1"
_FACT_ONLY_ACTIONS = frozenset(("observe", "explain"))
_FACT_ONLY_AUTHORITIES = frozenset(("A0_OBSERVE", "A1_EXPLAIN"))
_REQUIRED_PACKET_DENIALS = frozenset(
    (
        "originate_signal",
        "raise_authority_from_llm",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
    )
)
_KNOWLEDGE_CUTOFF_SUCCESSORS = (
    "as_of",
    "computed_at",
    "generated_at",
    "issued_at",
    "resolved_at",
    "started_at",
)
_BIOPHARMA_OUTCOME_TYPE_PATTERN = re.compile(
    r"^(study_conduct|endpoint_result|regulatory_disposition|asset_program_state)\."
)
_AUTHORITY_LEVEL_RANK = {
    "A0_OBSERVE": 0,
    "A1_EXPLAIN": 1,
    "A2_ATTEND": 2,
    "A3_DE_ESCALATE": 3,
    "A4_QUARANTINE": 4,
    "A5_GOVERN_TIERS": 5,
    "A6_TUNE": 6,
}
_ACTION_MIN_AUTHORITY = {
    "observe": "A0_OBSERVE",
    "explain": "A1_EXPLAIN",
    "attend": "A2_ATTEND",
    "de_escalate": "A3_DE_ESCALATE",
    "quarantine": "A4_QUARANTINE",
    "govern_tiers": "A5_GOVERN_TIERS",
    "tune": "A6_TUNE",
}
_TRIAL_FACT_JSON_PATHS = {
    "brief_title": "/protocolSection/identificationModule/briefTitle",
    "official_title": "/protocolSection/identificationModule/officialTitle",
    "overall_status": "/protocolSection/statusModule/overallStatus",
    "study_type": "/protocolSection/designModule/studyType",
    "phases": "/protocolSection/designModule/phases",
    "sponsor": "/protocolSection/sponsorCollaboratorsModule/leadSponsor",
    "enrollment": "/protocolSection/designModule/enrollmentInfo",
    "start_date": "/protocolSection/statusModule/startDateStruct",
    "primary_completion_date": (
        "/protocolSection/statusModule/primaryCompletionDateStruct"
    ),
    "completion_date": "/protocolSection/statusModule/completionDateStruct",
    "conditions": "/protocolSection/conditionsModule/conditions",
    "interventions": "/protocolSection/armsInterventionsModule/interventions",
    "primary_outcomes": "/protocolSection/outcomesModule/primaryOutcomes",
    "secondary_outcomes": "/protocolSection/outcomesModule/secondaryOutcomes",
    "locations": "/protocolSection/contactsLocationsModule/locations",
}


_FORMAT_CHECKER = FormatChecker()


@_FORMAT_CHECKER.checks("date")
def _is_jsonschema_date(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


@_FORMAT_CHECKER.checks("date-time")
def _is_jsonschema_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})",
        value,
    ):
        return False
    normalized = value[:-1] + "+00:00" if value[-1] in "Zz" else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


@_FORMAT_CHECKER.checks("uri")
def _is_jsonschema_uri(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if (
        any(character.isspace() or ord(character) < 32 for character in value)
        or "\\" in value
        or re.search(r"%(?![0-9A-Fa-f]{2})", value)
    ):
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return False
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*", parsed.scheme):
        return False
    if parsed.scheme.lower() in {"http", "https"}:
        return (
            bool(parsed.netloc and hostname)
            and parsed.username is None
            and parsed.password is None
        )
    return True


@_FORMAT_CHECKER.checks("ctgov-data-timestamp")
def _is_ctgov_data_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:Z|[+-][0-9]{2}:[0-9]{2})?",
        value,
    ):
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


class ContractError(ValueError):
    """Base class for fail-closed contract errors."""


class ContractRegistryError(ContractError):
    """Raised when schema discovery cannot build an unambiguous registry."""


class UnsupportedContractError(ContractError):
    """Raised when a contract identifier is unsafe or not registered."""


@dataclass(frozen=True, order=True)
class ValidationIssue:
    """A deterministic, machine-sortable validation issue."""

    path: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: [{self.code}] {self.message}"


class ContractValidationError(ContractError):
    """Raised when a document violates its JSON Schema or semantic rules."""

    def __init__(self, contract_id: str, issues: Iterable[ValidationIssue]) -> None:
        self.contract_id = contract_id
        self.issues = tuple(sorted(issues))
        details = "; ".join(str(issue) for issue in self.issues)
        super().__init__(f"contract {contract_id!r} failed validation: {details}")


@dataclass(frozen=True)
class _SchemaRecord:
    contract_id: str
    schema_uri: str
    path: Path
    schema: Mapping[str, Any]


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _load_schema(path: Path, root: Path) -> _SchemaRecord:
    shown = _display_path(path, root)
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractRegistryError(f"cannot load schema {shown}: {exc}") from exc
    if not isinstance(schema, dict):
        raise ContractRegistryError(f"schema {shown} must contain a JSON object")
    if schema.get("$schema") not in _DRAFT_2020_12_URIS:
        raise ContractRegistryError(f"schema {shown} must declare JSON Schema Draft 2020-12")

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ContractRegistryError(f"invalid Draft 2020-12 schema {shown}: {exc}") from exc

    properties = schema.get("properties")
    contract_definition = properties.get("contract_id") if isinstance(properties, dict) else None
    contract_id = (
        contract_definition.get("const")
        if isinstance(contract_definition, dict)
        else None
    )
    if not isinstance(contract_id, str) or not _CONTRACT_ID_PATTERN.fullmatch(contract_id):
        raise ContractRegistryError(
            f"schema {shown} must declare a safe properties.contract_id.const"
        )

    schema_uri = schema.get("$id")
    if not isinstance(schema_uri, str) or not _is_jsonschema_uri(schema_uri):
        raise ContractRegistryError(f"schema {shown} must declare an absolute URI in $id")
    if not urlsplit(schema_uri).scheme:
        raise ContractRegistryError(f"schema {shown} must declare an absolute URI in $id")
    return _SchemaRecord(contract_id, schema_uri, path, schema)


def _discover_records(repo_root: Path | str | None = None) -> dict[str, _SchemaRecord]:
    root = Path(repo_root) if repo_root is not None else _default_repo_root()
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise ContractRegistryError(f"repository root is unavailable: {root}") from exc
    if not root.is_dir():
        raise ContractRegistryError(f"repository root is not a directory: {root}")

    candidates: list[Path] = []
    for relative in _SCHEMA_DIRECTORIES:
        declared_directory = root / relative
        try:
            directory = declared_directory.resolve(strict=True)
        except OSError as exc:
            raise ContractRegistryError(
                f"required schema directory is unavailable: {relative.as_posix()}"
            ) from exc
        if not directory.is_dir() or not _is_relative_to(directory, root):
            raise ContractRegistryError(
                f"schema directory escapes repository root: {relative.as_posix()}"
            )
        for candidate in sorted(declared_directory.rglob("*.schema.json")):
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise ContractRegistryError(
                    f"cannot resolve schema {_display_path(candidate, root)}"
                ) from exc
            if (
                candidate.is_symlink()
                or not resolved.is_file()
                or not _is_relative_to(resolved, directory)
            ):
                raise ContractRegistryError(
                    f"unsafe schema path: {_display_path(candidate, root)}"
                )
            candidates.append(resolved)

    if not candidates:
        raise ContractRegistryError("no contract schemas were discovered")

    records: dict[str, _SchemaRecord] = {}
    uri_paths: dict[str, Path] = {}
    for path in sorted(candidates, key=lambda item: _display_path(item, root)):
        record = _load_schema(path, root)
        if record.contract_id in records:
            first = _display_path(records[record.contract_id].path, root)
            second = _display_path(record.path, root)
            raise ContractRegistryError(
                f"duplicate contract_id {record.contract_id!r}: {first}, {second}"
            )
        if record.schema_uri in uri_paths:
            first = _display_path(uri_paths[record.schema_uri], root)
            second = _display_path(record.path, root)
            raise ContractRegistryError(
                f"duplicate schema $id {record.schema_uri!r}: {first}, {second}"
            )
        records[record.contract_id] = record
        uri_paths[record.schema_uri] = record.path
    return records


def discover_contract_schemas(
    repo_root: Path | str | None = None,
) -> dict[str, Mapping[str, Any]]:
    """Return all owned schemas keyed by their document ``contract_id``."""

    return {
        contract_id: record.schema
        for contract_id, record in sorted(_discover_records(repo_root).items())
    }


def _validate_requested_id(contract_id: object) -> str:
    if not isinstance(contract_id, str) or not _CONTRACT_ID_PATTERN.fullmatch(contract_id):
        raise UnsupportedContractError(f"unsafe contract_id: {contract_id!r}")
    return contract_id


def _json_path(parts: Sequence[object]) -> str:
    rendered = "$"
    for part in parts:
        if isinstance(part, int):
            rendered += f"[{part}]"
        elif isinstance(part, str) and _JSON_PATH_KEY_PATTERN.fullmatch(part):
            rendered += f".{part}"
        else:
            rendered += f"[{json.dumps(part, ensure_ascii=False)}]"
    return rendered


def _parse_temporal(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            parsed_date = date.fromisoformat(value)
            return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ordered_pair_issue(
    document: Mapping[str, Any],
    path: tuple[object, ...],
    first_key: str,
    second_key: str,
    code: str,
    *,
    strict: bool = True,
) -> ValidationIssue | None:
    first = _parse_temporal(document.get(first_key))
    second = _parse_temporal(document.get(second_key))
    if first is None or second is None:
        return None
    invalid = first >= second if strict else first > second
    if invalid:
        relation = "greater than" if strict else "greater than or equal to"
        return ValidationIssue(
            _json_path((*path, second_key)),
            code,
            f"{second_key} must be {relation} {first_key}",
        )
    return None


def _interval_issues(value: Any, path: tuple[object, ...] = ()) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(value, Mapping):
        for first, second, code in (
            ("valid_from", "valid_to", "interval.valid"),
            ("transaction_from", "transaction_to", "interval.transaction"),
            ("started_at", "finished_at", "interval.run"),
        ):
            issue = _ordered_pair_issue(value, path, first, second, code)
            if issue is not None:
                issues.append(issue)

        cutoff = _parse_temporal(value.get("knowledge_cutoff"))
        if cutoff is not None:
            for successor_key in _KNOWLEDGE_CUTOFF_SUCCESSORS:
                successor = _parse_temporal(value.get(successor_key))
                if successor is not None and cutoff > successor:
                    issues.append(
                        ValidationIssue(
                            _json_path((*path, "knowledge_cutoff")),
                            "interval.knowledge_cutoff",
                            f"knowledge_cutoff must not be later than {successor_key}",
                        )
                    )

        for key in sorted(value, key=lambda item: str(item)):
            issues.extend(_interval_issues(value[key], (*path, key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_interval_issues(item, (*path, index)))
    return issues


def _packet_authority_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    caps = document.get("authority_caps")
    if not isinstance(caps, Mapping):
        return []  # JSON Schema reports the structural failure.

    issues: list[ValidationIssue] = []
    if caps.get("max_authority") not in _FACT_ONLY_AUTHORITIES:
        issues.append(
            ValidationIssue(
                "$.authority_caps.max_authority",
                "authority.facts_only",
                "facts-only packets may not exceed A1_EXPLAIN",
            )
        )

    allowed = caps.get("allowed_actions")
    if isinstance(allowed, list):
        prohibited_allowed = sorted(
            action
            for action in allowed
            if isinstance(action, str) and action not in _FACT_ONLY_ACTIONS
        )
        if prohibited_allowed:
            issues.append(
                ValidationIssue(
                    "$.authority_caps.allowed_actions",
                    "authority.facts_only",
                    "facts-only packets may allow only observe and explain; prohibited: "
                    + ", ".join(prohibited_allowed),
                )
            )

    forbidden = caps.get("forbidden_actions")
    if isinstance(forbidden, list):
        denied = {item for item in forbidden if isinstance(item, str)}
        missing = sorted(_REQUIRED_PACKET_DENIALS - denied)
        if missing:
            issues.append(
                ValidationIssue(
                    "$.authority_caps.forbidden_actions",
                    "authority.facts_only",
                    "facts-only packets must explicitly forbid: " + ", ".join(missing),
                )
            )

    if caps.get("llm_may_originate_signals") is not False:
        issues.append(
            ValidationIssue(
                "$.authority_caps.llm_may_originate_signals",
                "authority.signal_origination",
                "facts-only packets must forbid LLM signal origination",
            )
        )
    return issues


def _content_hash_issue(
    document: Mapping[str, Any],
    *,
    hash_field: str,
    excluded_fields: frozenset[str],
    code: str,
) -> ValidationIssue | None:
    expected = document.get(hash_field)
    if not isinstance(expected, str):
        return None  # JSON Schema reports the structural failure.
    payload = {key: value for key, value in document.items() if key not in excluded_fields}
    actual = canonical_json_sha256(payload)
    if expected == actual:
        return None
    return ValidationIssue(
        _json_path((hash_field,)),
        code,
        f"declared hash {expected} does not match canonical payload hash {actual}",
    )


def _timestamp_order_issue(
    document: Mapping[str, Any], first_key: str, second_key: str, code: str
) -> ValidationIssue | None:
    return _ordered_pair_issue(document, (), first_key, second_key, code, strict=False)


def _trial_source_snapshot_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    canonical_study = document.get("canonical_study")
    declared_hash = document.get("canonical_content_sha256")
    if isinstance(canonical_study, Mapping) and isinstance(declared_hash, str):
        actual_hash = canonical_json_sha256(canonical_study)
        if actual_hash != declared_hash:
            issues.append(
                ValidationIssue(
                    "$.canonical_content_sha256",
                    "source_snapshot.hash",
                    f"canonical study hash is {actual_hash}, not {declared_hash}",
                )
            )

        protocol_section = canonical_study.get("protocolSection")
        identification = (
            protocol_section.get("identificationModule")
            if isinstance(protocol_section, Mapping)
            else None
        )
        source_nct = identification.get("nctId") if isinstance(identification, Mapping) else None
        if source_nct != document.get("nct_id"):
            issues.append(
                ValidationIssue(
                    "$.canonical_study.protocolSection.identificationModule.nctId",
                    "source_snapshot.identity",
                    "source NCT ID must match wrapper nct_id",
                )
            )

    raw_object_key = document.get("raw_object_key")
    nct_id = document.get("nct_id")
    if (
        isinstance(raw_object_key, str)
        and isinstance(nct_id, str)
        and isinstance(declared_hash, str)
        and not raw_object_key.endswith(f"/{nct_id}/{declared_hash}.json")
    ):
        issues.append(
            ValidationIssue(
                "$.raw_object_key",
                "source_snapshot.object_key",
                "raw object key must be content-addressed by wrapper NCT ID and canonical hash",
            )
        )
    if isinstance(nct_id, str) and isinstance(declared_hash, str):
        expected_source_record_ref = f"src:ctgov:{nct_id}:sha256:{declared_hash}"
        if document.get("source_record_ref") != expected_source_record_ref:
            issues.append(
                ValidationIssue(
                    "$.source_record_ref",
                    "source_snapshot.content_address",
                    "source record reference must bind the NCT ID and canonical hash",
                )
            )

    for first, second, code in (
        ("first_seen_at", "retrieved_at", "observation.first_seen"),
        ("retrieved_at", "transaction_from", "observation.transaction"),
    ):
        issue = _timestamp_order_issue(document, first, second, code)
        if issue is not None:
            issues.append(issue)
    published = _parse_temporal(document.get("source_published_at"))
    retrieved = _parse_temporal(document.get("retrieved_at"))
    if published is not None and retrieved is not None and published > retrieved:
        issues.append(
            ValidationIssue(
                "$.source_published_at",
                "observation.source_published",
                "source_published_at cannot be later than retrieved_at",
            )
        )
    if document.get("source_published_at") != document.get("source_last_update_posted_at"):
        issues.append(
            ValidationIssue(
                "$.source_published_at",
                "observation.source_published",
                "ClinicalTrials.gov source publication time is the last-update-posted value",
            )
        )
    canonical_last_update = _resolve_json_pointer(
        canonical_study,
        "/protocolSection/statusModule/lastUpdatePostDateStruct/date",
    )
    expected_last_update = (
        None if canonical_last_update is _MISSING else canonical_last_update
    )
    if (
        not isinstance(expected_last_update, (str, type(None)))
        or document.get("source_last_update_posted_at") != expected_last_update
    ):
        issues.append(
            ValidationIssue(
                "$.source_last_update_posted_at",
                "source_snapshot.publication_binding",
                "last-update-posted time must exactly match the hashed canonical study",
            )
        )
    return issues


def _trial_observation_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    prior_ref = document.get("prior_source_snapshot_ref")
    prior_hash = document.get("prior_canonical_content_sha256")
    current_hash = document.get("canonical_content_sha256")
    changed = document.get("source_state_changed")
    same = document.get("same_content_as_prior")
    interval = document.get("observed_interval")

    if (prior_ref is None) != (prior_hash is None):
        issues.append(
            ValidationIssue(
                "$.prior_source_snapshot_ref",
                "observation.prior_pair",
                "prior snapshot reference and prior content hash must both be null "
                "or both be present",
            )
        )
    if prior_ref is None:
        if changed is not False or same is not False:
            issues.append(
                ValidationIssue(
                    "$.source_state_changed",
                    "observation.initial_state",
                    "an initial observation is neither a change nor same-as-prior",
                )
            )
        if isinstance(interval, Mapping) and interval.get("after") is not None:
            issues.append(
                ValidationIssue(
                    "$.observed_interval.after",
                    "observation.initial_interval",
                    "an initial observation has no prior lower bound",
                )
            )
    elif isinstance(prior_hash, str) and isinstance(current_hash, str):
        expected_changed = prior_hash != current_hash
        if changed is not expected_changed or same is expected_changed:
            issues.append(
                ValidationIssue(
                    "$.source_state_changed",
                    "observation.hash_state",
                    "change and same-as-prior flags must agree with the two content hashes",
                )
            )

    if isinstance(interval, Mapping):
        issue = _ordered_pair_issue(
            interval, ("observed_interval",), "after", "at_or_before", "interval.observed"
        )
        if issue is not None:
            issues.append(issue)
    issue = _timestamp_order_issue(
        document, "first_seen_at", "retrieved_at", "observation.first_seen"
    )
    if issue is not None:
        issues.append(issue)
    return issues


def _trial_diff_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    hash_issue = _content_hash_issue(
        document,
        hash_field="diff_payload_sha256",
        excluded_fields=frozenset(("diff_payload_sha256",)),
        code="trial_diff.hash",
    )
    if hash_issue is not None:
        issues.append(hash_issue)
    before_hash = document.get("before_content_sha256")
    after_hash = document.get("after_content_sha256")
    if isinstance(before_hash, str) and before_hash == after_hash:
        issues.append(
            ValidationIssue(
                "$.after_content_sha256",
                "trial_diff.noop_hash",
                "a diff must connect two different canonical source hashes",
            )
        )

    operations = document.get("operations")
    if isinstance(operations, list):
        paths = [item.get("json_path") for item in operations if isinstance(item, Mapping)]
        if len(paths) != len(set(paths)):
            issues.append(
                ValidationIssue(
                    "$.operations",
                    "trial_diff.duplicate_path",
                    "each JSON path may appear only once",
                )
            )
        if all(isinstance(path, str) for path in paths) and paths != sorted(paths):
            issues.append(
                ValidationIssue(
                    "$.operations",
                    "trial_diff.order",
                    "diff operations must be ordered lexicographically by JSON path",
                )
            )
        for index, operation in enumerate(operations):
            if not isinstance(operation, Mapping):
                continue
            op = operation.get("op")
            before_state = operation.get("before_state")
            after_state = operation.get("after_state")
            expected_states = {
                "add": ("missing", "present"),
                "remove": ("present", "missing"),
                "replace": ("present", "present"),
            }.get(op)
            if expected_states is not None and (before_state, after_state) != expected_states:
                issues.append(
                    ValidationIssue(
                        f"$.operations[{index}]",
                        "trial_diff.operation_state",
                        f"{op} requires before/after states {expected_states}",
                    )
                )
            if before_state == "missing" and operation.get("before_value") is not None:
                issues.append(
                    ValidationIssue(
                        f"$.operations[{index}].before_value",
                        "trial_diff.missing_value",
                        "a missing before state must carry a null placeholder",
                    )
                )
            if after_state == "missing" and operation.get("after_value") is not None:
                issues.append(
                    ValidationIssue(
                        f"$.operations[{index}].after_value",
                        "trial_diff.missing_value",
                        "a missing after state must carry a null placeholder",
                    )
                )
            if (
                op == "replace"
                and _canonical_json_equal(
                    operation.get("before_value"), operation.get("after_value")
                )
            ):
                issues.append(
                    ValidationIssue(
                        f"$.operations[{index}]",
                        "trial_diff.noop_operation",
                        "replace must change the JSON value",
                    )
                )

    interval = document.get("observed_interval")
    if isinstance(interval, Mapping):
        issue = _ordered_pair_issue(
            interval, ("observed_interval",), "after", "at_or_before", "interval.observed"
        )
        if issue is not None:
            issues.append(issue)
    return issues


def _ctgov_fetch_run_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    manifest = document.get("query_manifest")
    counts = document.get("counts")
    published_refs = document.get("published_source_record_refs")
    configured_ids = (
        manifest.get("configured_nct_ids") if isinstance(manifest, Mapping) else None
    )
    if isinstance(manifest, Mapping) and isinstance(counts, Mapping):
        if isinstance(configured_ids, list) and counts.get("configured") != len(configured_ids):
            issues.append(
                ValidationIssue(
                    "$.counts.configured",
                    "fetch_run.counts",
                    "configured count must equal the query-manifest NCT count",
                )
            )
        query_hash = manifest.get("query_sha256")
        if isinstance(query_hash, str) and query_hash != ctgov_query_manifest_sha256(
            manifest
        ):
            issues.append(
                ValidationIssue(
                    "$.query_manifest.query_sha256",
                    "fetch_run.query_manifest_hash",
                    "query hash must bind the complete canonical query manifest",
                )
            )
        page_cap = manifest.get("page_cap")
        pages_attempted = counts.get("pages_attempted")
        if (
            isinstance(page_cap, int)
            and isinstance(pages_attempted, int)
            and pages_attempted > page_cap
        ):
            issues.append(
                ValidationIssue(
                    "$.counts.pages_attempted",
                    "fetch_run.page_cap",
                    "pages attempted cannot exceed the declared query page cap",
                )
            )
        integer_counts = all(
            isinstance(counts.get(key), int)
            for key in (
                "pages_attempted",
                "pages_succeeded",
                "studies_fetched",
                "studies_unique",
                "studies_duplicate",
                "studies_published",
                "errors",
            )
        )
        if integer_counts:
            if counts["pages_succeeded"] > counts["pages_attempted"]:
                issues.append(
                    ValidationIssue(
                        "$.counts.pages_succeeded",
                        "fetch_run.counts",
                        "successful pages cannot exceed attempted pages",
                    )
                )
            if counts["studies_unique"] + counts["studies_duplicate"] != counts["studies_fetched"]:
                issues.append(
                    ValidationIssue(
                        "$.counts.studies_fetched",
                        "fetch_run.counts",
                        "fetched studies must reconcile to unique plus duplicate studies",
                    )
                )
            if counts["studies_published"] > counts["studies_unique"]:
                issues.append(
                    ValidationIssue(
                        "$.counts.studies_published",
                        "fetch_run.counts",
                        "published studies cannot exceed unique studies",
                    )
                )
        if isinstance(published_refs, list):
            if counts.get("studies_published") != len(published_refs):
                issues.append(
                    ValidationIssue(
                        "$.published_source_record_refs",
                        "fetch_run.publication_manifest",
                        "published-study count must equal the publication manifest length",
                    )
                )
            if all(isinstance(reference, str) for reference in published_refs) and (
                published_refs != sorted(published_refs)
            ):
                issues.append(
                    ValidationIssue(
                        "$.published_source_record_refs",
                        "fetch_run.publication_manifest",
                        "publication manifest references must be lexicographically ordered",
                    )
                )
            published_nct_ids = {
                parts[2]
                for reference in published_refs
                if isinstance(reference, str)
                and len(parts := reference.split(":")) == 5
            }
            if (
                isinstance(configured_ids, list)
                and all(isinstance(nct_id, str) for nct_id in configured_ids)
                and not published_nct_ids.issubset(set(configured_ids))
            ):
                issues.append(
                    ValidationIssue(
                        "$.published_source_record_refs",
                        "fetch_run.publication_manifest",
                        "publication manifest NCT IDs must belong to the configured universe",
                    )
                )

    if document.get("run_state") == "complete":
        receipt_refs = document.get("receipt_refs")
        terminal_receipt_ref = document.get("terminal_receipt_ref")
        finished_at = _parse_temporal(document.get("finished_at"))
        transaction_from = _parse_temporal(document.get("transaction_from"))
        watermark_before = _parse_temporal(document.get("watermark_before"))
        watermark_after = _parse_temporal(document.get("watermark_after"))
        complete_requirements = (
            document.get("completeness_state") == "reconciled"
            and finished_at is not None
            and transaction_from is not None
            and transaction_from >= finished_at
            and isinstance(document.get("source_dataset_timestamp_before_raw"), str)
            and isinstance(document.get("source_dataset_timestamp_after_raw"), str)
            and document.get("source_dataset_timestamp_before_raw")
            == document.get("source_dataset_timestamp_after_raw")
            and isinstance(counts, Mapping)
            and counts.get("errors") == 0
            and isinstance(counts.get("configured"), int)
            and counts.get("configured") > 0
            and counts.get("studies_unique") == counts.get("configured")
            and counts.get("studies_published") == counts.get("studies_unique")
            and isinstance(published_refs, list)
            and all(isinstance(reference, str) for reference in published_refs)
            and len(published_refs) == counts.get("studies_published")
            and isinstance(configured_ids, list)
            and all(isinstance(nct_id, str) for nct_id in configured_ids)
            and {
                reference.split(":")[2]
                for reference in published_refs
                if isinstance(reference, str) and len(reference.split(":")) == 5
            }
            == set(configured_ids)
            and isinstance(counts.get("pages_attempted"), int)
            and counts.get("pages_attempted") > 0
            and counts.get("pages_attempted") == counts.get("pages_succeeded")
            and isinstance(receipt_refs, list)
            and len(receipt_refs) > 0
            and len(receipt_refs) == counts.get("pages_succeeded")
            and terminal_receipt_ref == receipt_refs[-1]
            and isinstance(document.get("receipt_payloads_sha256"), str)
            and watermark_after is not None
            and (watermark_before is None or watermark_after > watermark_before)
        )
        if not complete_requirements:
            issues.append(
                ValidationIssue(
                    "$.run_state",
                    "fetch_run.complete",
                    "complete runs require stable source version, reconciled counts, "
                    "full publication coverage, no errors, terminal pagination, and an "
                    "advanced watermark candidate",
                )
            )
    else:
        if document.get("watermark_after") != document.get("watermark_before"):
            issues.append(
                ValidationIssue(
                    "$.watermark_after",
                    "fetch_run.watermark",
                    "an incomplete run cannot advance its watermark candidate",
                )
            )
        if published_refs:
            issues.append(
                ValidationIssue(
                    "$.published_source_record_refs",
                    "fetch_run.publication_manifest",
                    "an incomplete run cannot publish source records",
                )
            )
    return issues


def _ctgov_watermark_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    advanced = document.get("advance_state") == "advanced"
    complete = document.get("candidate_run_state") == "complete"
    if advanced and (
        not complete
        or document.get("advance_reason") != "complete_run_reconciled"
        or document.get("successful_run_ref") != document.get("candidate_run_ref")
        or document.get("successful_source_dataset_timestamp_raw") is None
        or document.get("successful_retrieved_at") is None
    ):
        issues.append(
            ValidationIssue(
                "$.advance_state",
                "watermark.advance",
                "only a reconciled complete candidate may become the successful watermark",
            )
        )
    if not advanced and document.get("advance_reason") == "complete_run_reconciled":
        issues.append(
            ValidationIssue(
                "$.advance_reason",
                "watermark.hold",
                "a held watermark cannot claim a reconciled-complete advance",
            )
        )
    return issues


def _trial_projection_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    hash_issue = _content_hash_issue(
        document,
        hash_field="projection_sha256",
        excluded_fields=frozenset(("projection_sha256",)),
        code="trial_snapshot.hash",
    )
    if hash_issue is not None:
        issues.append(hash_issue)
    attribution = document.get("source_attribution")
    nct_id = document.get("nct_id")
    if isinstance(attribution, Mapping) and isinstance(nct_id, str):
        uri = attribution.get("source_uri")
        if isinstance(uri, str) and not uri.endswith(f"/{nct_id}"):
            issues.append(
                ValidationIssue(
                    "$.source_attribution.source_uri",
                    "trial_snapshot.identity",
                    "source URI must identify the wrapper nct_id",
                )
            )
        source_record_ref = document.get("source_record_ref")
        if isinstance(source_record_ref, str) and f":{nct_id}:" not in source_record_ref:
            issues.append(
                ValidationIssue(
                    "$.source_record_ref",
                    "trial_snapshot.identity",
                    "source record reference must identify the wrapper nct_id",
                )
            )
    for first, second, code in (
        ("first_seen_at", "retrieved_at", "observation.first_seen"),
        ("retrieved_at", "knowledge_cutoff", "observation.knowledge_cutoff"),
        ("knowledge_cutoff", "transaction_from", "observation.transaction"),
    ):
        issue = _timestamp_order_issue(document, first, second, code)
        if issue is not None:
            issues.append(issue)
    source_published = _parse_temporal(document.get("source_published_at"))
    retrieved = _parse_temporal(document.get("retrieved_at"))
    if source_published is not None and retrieved is not None and source_published > retrieved:
        issues.append(
            ValidationIssue(
                "$.source_published_at",
                "observation.source_published",
                "source_published_at cannot be later than retrieved_at",
            )
        )
    return issues


def _trial_coverage_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for first, second, code in (
        ("coverage_started_at", "coverage_ended_at", "interval.coverage"),
        ("coverage_started_at", "last_observed_at", "interval.coverage_observed"),
    ):
        issue = _timestamp_order_issue(document, first, second, code)
        if issue is not None:
            issues.append(issue)
    return issues


def _provenance_chronology_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for first, second, code in (
        ("first_seen_at", "retrieved_at", "provenance.first_seen"),
        ("retrieved_at", "transaction_from", "provenance.transaction"),
    ):
        issue = _timestamp_order_issue(document, first, second, code)
        if issue is not None:
            issues.append(issue)
    published = _parse_temporal(document.get("source_published_at"))
    retrieved = _parse_temporal(document.get("retrieved_at"))
    if published is not None and retrieved is not None and published > retrieved:
        issues.append(
            ValidationIssue(
                "$.source_published_at",
                "provenance.source_published",
                "source_published_at cannot be later than retrieved_at",
            )
        )
    return issues


def _source_record_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues = _provenance_chronology_issues(document)
    if document.get("source_system") != "clinicaltrials_gov_v2":
        return issues

    required_values = {
        "license_class": "us_government_source_facts",
        "redistribution_allowed": False,
    }
    for field, expected in required_values.items():
        if document.get(field) != expected:
            issues.append(
                ValidationIssue(
                    f"$.{field}",
                    "rights.clinicaltrials_gov",
                    f"ClinicalTrials.gov source records require {field}={expected!r}",
                )
            )
    if not document.get("rights_note"):
        issues.append(
            ValidationIssue(
                "$.rights_note",
                "rights.clinicaltrials_gov",
                "ClinicalTrials.gov source records require an explicit rights note",
            )
        )
    source_uri = document.get("source_uri")
    external_id = document.get("external_id")
    if not isinstance(external_id, str) or not re.fullmatch(r"NCT[0-9]{8}", external_id):
        issues.append(
            ValidationIssue(
                "$.external_id",
                "source_record.identity",
                "ClinicalTrials.gov external IDs must be canonical NCT identifiers",
            )
        )
    if source_uri != f"https://clinicaltrials.gov/study/{external_id}":
        issues.append(
            ValidationIssue(
                "$.source_uri",
                "rights.clinicaltrials_gov",
                "ClinicalTrials.gov source URI must match the external NCT ID",
            )
        )
    object_uri = document.get("object_uri")
    content_hash = document.get("content_sha256")
    if (
        not isinstance(object_uri, str)
        or not object_uri.startswith("r2://")
        or not isinstance(content_hash, str)
        or not object_uri.endswith(f"/{content_hash}.json")
    ):
        issues.append(
            ValidationIssue(
                "$.object_uri",
                "rights.private_raw",
                "ClinicalTrials.gov raw source records must use a private "
                "content-addressed R2 URI",
            )
        )
    expected_record_id = f"src:ctgov:{external_id}:sha256:{content_hash}"
    if document.get("record_id") != expected_record_id:
        issues.append(
            ValidationIssue(
                "$.record_id",
                "source_record.content_address",
                "ClinicalTrials.gov record ID must bind the NCT ID and content hash",
            )
        )
    return issues


def _evidence_claim_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues = _provenance_chronology_issues(document)
    source_refs = document.get("source_record_refs")
    if isinstance(source_refs, list) and any(
        isinstance(ref, str) and ref.startswith("src:ctgov:") for ref in source_refs
    ):
        if document.get("license_class") != "us_government_source_facts":
            issues.append(
                ValidationIssue(
                    "$.license_class",
                    "rights.clinicaltrials_gov",
                    "claims from ClinicalTrials.gov records require the registered license class",
                )
            )
    return issues


def _feature_snapshot_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    values = document.get("values")
    if not isinstance(values, list):
        return issues
    knowledge_cutoff = _parse_temporal(document.get("knowledge_cutoff"))
    as_of = _parse_temporal(document.get("as_of"))
    counts = {"present": 0, "missing": 0, "stale": 0}
    for index, feature in enumerate(values):
        if not isinstance(feature, Mapping):
            continue
        missingness = feature.get("missingness")
        value = feature.get("value")
        observed_at = feature.get("observed_at")
        stale = feature.get("stale")
        source_refs = feature.get("source_claim_refs")
        if missingness == "observed":
            counts["present"] += 1
            valid = (
                value is not None
                and isinstance(observed_at, str)
                and stale is False
                and isinstance(source_refs, list)
                and len(source_refs) > 0
            )
        elif missingness == "stale":
            counts["stale"] += 1
            valid = (
                value is not None
                and isinstance(observed_at, str)
                and stale is True
                and isinstance(source_refs, list)
                and len(source_refs) > 0
            )
        else:
            counts["missing"] += 1
            valid = value is None and observed_at is None and stale is False
        if not valid:
            issues.append(
                ValidationIssue(
                    f"$.values[{index}]",
                    "feature.missingness",
                    "feature value, evidence time, and stale flag must agree with missingness",
                )
            )
        observation_time = _parse_temporal(observed_at)
        if observation_time is not None and (
            (knowledge_cutoff is not None and observation_time > knowledge_cutoff)
            or (as_of is not None and observation_time > as_of)
        ):
            issues.append(
                ValidationIssue(
                    f"$.values[{index}].observed_at",
                    "feature.point_in_time",
                    "feature observations cannot postdate knowledge_cutoff or as_of",
                )
            )

    summary = document.get("missingness_summary")
    if isinstance(summary, Mapping) and any(
        summary.get(key) != count for key, count in counts.items()
    ):
        issues.append(
            ValidationIssue(
                "$.missingness_summary",
                "feature.missingness_summary",
                "missingness summary must reconcile to feature value states",
            )
        )
    staleness = document.get("staleness")
    if isinstance(staleness, Mapping):
        state = staleness.get("state")
        if (counts["stale"] > 0 and state != "stale") or (
            counts["stale"] == 0 and state == "stale"
        ):
            issues.append(
                ValidationIssue(
                    "$.staleness.state",
                    "feature.staleness",
                    "overall staleness state must agree with stale feature values",
                )
            )
    return issues


def _prediction_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    horizon = document.get("horizon")
    if isinstance(horizon, Mapping):
        issue = _ordered_pair_issue(
            horizon, ("horizon",), "starts_at", "ends_at", "prediction.horizon"
        )
        if issue is not None:
            issues.append(issue)

    scenarios = document.get("scenarios")
    probabilities: list[float] = []
    if isinstance(scenarios, list):
        scenario_ids: list[str] = []
        for index, scenario in enumerate(scenarios):
            if not isinstance(scenario, Mapping):
                continue
            scenario_id = scenario.get("scenario_id")
            if isinstance(scenario_id, str):
                scenario_ids.append(scenario_id)
            probability = scenario.get("probability")
            lower = scenario.get("lower_bound")
            upper = scenario.get("upper_bound")
            if isinstance(probability, (int, float)):
                probabilities.append(float(probability))
            if all(isinstance(value, (int, float)) for value in (lower, probability, upper)):
                if not float(lower) <= float(probability) <= float(upper):
                    issues.append(
                        ValidationIssue(
                            f"$.scenarios[{index}]",
                            "prediction.bounds",
                            "scenario probability must lie within lower and upper bounds",
                        )
                    )
            elif any(value is not None for value in (lower, probability, upper)):
                issues.append(
                    ValidationIssue(
                        f"$.scenarios[{index}]",
                        "prediction.bounds",
                        "scenario probability and bounds must be all numeric or all null",
                    )
                )
        if len(scenario_ids) != len(set(scenario_ids)):
            issues.append(
                ValidationIssue(
                    "$.scenarios",
                    "prediction.scenario_id",
                    "scenario IDs must be unique",
                )
            )
        if probabilities and (
            len(probabilities) != len(scenarios) or abs(sum(probabilities) - 1.0) > 1e-9
        ):
            issues.append(
                ValidationIssue(
                    "$.scenarios",
                    "prediction.probability_mass",
                    "numeric scenario probabilities must be complete and sum to one",
                )
            )

    model = document.get("model")
    training_cutoff = _parse_temporal(
        model.get("training_cutoff") if isinstance(model, Mapping) else None
    )
    knowledge_cutoff = _parse_temporal(document.get("knowledge_cutoff"))
    if (
        training_cutoff is not None
        and knowledge_cutoff is not None
        and training_cutoff > knowledge_cutoff
    ):
        issues.append(
            ValidationIssue(
                "$.model.training_cutoff",
                "prediction.training_cutoff",
                "training cutoff cannot be later than the prediction knowledge cutoff",
            )
        )

    target = document.get("target")
    outcome_type = target.get("outcome_type") if isinstance(target, Mapping) else None
    if (
        document.get("sector") == "biopharma"
        and isinstance(outcome_type, str)
        and not _BIOPHARMA_OUTCOME_TYPE_PATTERN.match(outcome_type)
    ):
        issues.append(
            ValidationIssue(
                "$.target.outcome_type",
                "prediction.outcome_layer",
                "biopharma outcome types must begin with a registered outcome layer",
            )
        )

    promoted = document.get("publication_tier") in {"CONFIRMER", "SCORED"}
    if promoted and (
        not document.get("promotion_evidence_refs")
        or not document.get("governance_decision_refs")
    ):
        issues.append(
            ValidationIssue(
                "$.publication_tier",
                "authority.promotion_evidence",
                "promoted predictions require evidence and governance decision references",
            )
        )
    if document.get("originator_type") == "llm_assisted" and (
        document.get("publication_tier") not in {"DISPLAY", "SHADOW"}
        or document.get("decision_authority") is not False
    ):
        issues.append(
            ValidationIssue(
                "$.originator_type",
                "authority.llm_prediction",
                "LLM-assisted predictions are non-authoritative DISPLAY or SHADOW artifacts",
            )
        )
    return issues


def _outcome_label_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    window = document.get("observation_window")
    if isinstance(window, Mapping):
        issue = _ordered_pair_issue(
            window,
            ("observation_window",),
            "starts_at",
            "ends_at",
            "outcome.observation_window",
        )
        if issue is not None:
            issues.append(issue)
    for first, second, code in (
        ("knowledge_cutoff", "resolved_at", "outcome.knowledge_cutoff"),
        ("resolved_at", "transaction_from", "outcome.transaction"),
    ):
        issue = _timestamp_order_issue(document, first, second, code)
        if issue is not None:
            issues.append(issue)
    outcome = document.get("outcome")
    if isinstance(outcome, Mapping):
        kind = outcome.get("kind")
        value = outcome.get("value")
        valid_kind = (
            (kind in {"censored", "unknown"} and value is None)
            or (
                kind == "numeric"
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            )
            or (kind == "boolean" and isinstance(value, bool))
            or (kind == "categorical" and isinstance(value, str) and bool(value))
        )
        if not valid_kind:
            issues.append(
                ValidationIssue(
                    "$.outcome",
                    "outcome.value_kind",
                    "outcome value must agree with its declared kind",
                )
            )
        window_end = _parse_temporal(
            window.get("ends_at") if isinstance(window, Mapping) else None
        )
        resolved_at = _parse_temporal(document.get("resolved_at"))
        if (
            document.get("status") == "final"
            and kind == "censored"
            and window_end is not None
            and resolved_at is not None
            and resolved_at < window_end
        ):
            issues.append(
                ValidationIssue(
                    "$.resolved_at",
                    "outcome.censoring_window",
                    "a final censored outcome cannot resolve before its window closes",
                )
            )
    if document.get("status") == "revised" and (
        not document.get("prior_label_ref") or not document.get("revision_reason")
    ):
        issues.append(
            ValidationIssue(
                "$.status",
                "outcome.revision",
                "revised outcomes require a prior label and revision reason",
            )
        )
    outcome_type = document.get("outcome_type")
    if (
        document.get("sector") == "biopharma"
        and isinstance(outcome_type, str)
        and not _BIOPHARMA_OUTCOME_TYPE_PATTERN.match(outcome_type)
    ):
        issues.append(
            ValidationIssue(
                "$.outcome_type",
                "outcome.layer",
                "biopharma outcome types must begin with a registered outcome layer",
            )
        )
    return issues


def _authority_manifest_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    denials = document.get("denied_actions")
    if isinstance(denials, list) and "originate_signal" not in denials:
        issues.append(
            ValidationIssue(
                "$.denied_actions",
                "authority.origination",
                "every sector artifact must explicitly deny signal origination",
            )
        )
    elevated = document.get("max_authority") not in {"A0_OBSERVE", "A1_EXPLAIN"}
    if elevated and not document.get("governance_decision_refs"):
        issues.append(
            ValidationIssue(
                "$.governance_decision_refs",
                "authority.governance_evidence",
                "authority above A1 requires a governance decision reference",
            )
        )
    max_authority = document.get("max_authority")
    max_rank = _AUTHORITY_LEVEL_RANK.get(max_authority)
    actions = document.get("allowed_actions")
    if max_rank is not None and isinstance(actions, list):
        escalated = sorted(
            action
            for action in actions
            if isinstance(action, str)
            and _AUTHORITY_LEVEL_RANK.get(
                _ACTION_MIN_AUTHORITY.get(action, "A6_TUNE"),
                len(_AUTHORITY_LEVEL_RANK),
            )
            > max_rank
        )
        if escalated:
            issues.append(
                ValidationIssue(
                    "$.allowed_actions",
                    "authority.action_cap",
                    f"{max_authority} cannot grant actions: " + ", ".join(escalated),
                )
            )
    return issues


def _contract_semantic_issues(
    contract_id: str, document: Mapping[str, Any]
) -> list[ValidationIssue]:
    if contract_id == _PACKET_CONTRACT_ID:
        issue = _content_hash_issue(
            document,
            hash_field="packet_hash",
            excluded_fields=frozenset(("packet_hash",)),
            code="packet.hash",
        )
        return [issue] if issue is not None else []
    if contract_id == _ONTOLOGY_CONTRACT_ID:
        issue = _content_hash_issue(
            document,
            hash_field="content_sha256",
            excluded_fields=frozenset(("content_sha256",)),
            code="ontology.hash",
        )
        return [issue] if issue is not None else []
    if contract_id == _TRIAL_SOURCE_SNAPSHOT_CONTRACT_ID:
        return _trial_source_snapshot_issues(document)
    if contract_id == _TRIAL_OBSERVATION_CONTRACT_ID:
        return _trial_observation_issues(document)
    if contract_id == _TRIAL_DIFF_CONTRACT_ID:
        return _trial_diff_issues(document)
    if contract_id == _CTGOV_FETCH_RUN_CONTRACT_ID:
        return _ctgov_fetch_run_issues(document)
    if contract_id == _CTGOV_WATERMARK_CONTRACT_ID:
        return _ctgov_watermark_issues(document)
    if contract_id == _TRIAL_SNAPSHOT_CONTRACT_ID:
        return _trial_projection_issues(document)
    if contract_id == _TRIAL_COVERAGE_CONTRACT_ID:
        return _trial_coverage_issues(document)
    if contract_id == _PAGE_RECEIPT_CONTRACT_ID:
        response = document.get("response")
        issues: list[ValidationIssue] = []
        received = _parse_temporal(
            response.get("received_at") if isinstance(response, Mapping) else None
        )
        transaction = _parse_temporal(document.get("transaction_from"))
        if received is not None and transaction is not None and received > transaction:
            issues.append(
                ValidationIssue(
                    "$.transaction_from",
                    "receipt.transaction",
                    "transaction_from must be at or after response.received_at",
                )
            )
        if isinstance(response, Mapping):
            response_hash = response.get("exact_response_sha256")
            raw_key = response.get("raw_response_object_key")
            if (
                isinstance(response_hash, str)
                and isinstance(raw_key, str)
                and not raw_key.endswith(f"/{response_hash}.json")
            ):
                issues.append(
                    ValidationIssue(
                        "$.response.raw_response_object_key",
                        "receipt.object_key",
                        "raw response object key must be content-addressed by exact response hash",
                    )
                )
        run_id = document.get("run_id")
        page_ordinal = document.get("page_ordinal")
        receipt_key = document.get("receipt_object_key")
        if (
            isinstance(run_id, str)
            and isinstance(page_ordinal, int)
            and isinstance(receipt_key, str)
            and not receipt_key.endswith(f"/{run_id}/{page_ordinal}.json")
        ):
            issues.append(
                ValidationIssue(
                    "$.receipt_object_key",
                    "receipt.object_key",
                    "receipt object key must match run_id and page_ordinal",
                )
            )
        return issues
    if contract_id == _SOURCE_RECORD_CONTRACT_ID:
        return _source_record_issues(document)
    if contract_id == _EVIDENCE_CLAIM_CONTRACT_ID:
        return _evidence_claim_issues(document)
    if contract_id == _FEATURE_SNAPSHOT_CONTRACT_ID:
        return _feature_snapshot_issues(document)
    if contract_id == _PREDICTION_CONTRACT_ID:
        return _prediction_issues(document)
    if contract_id == _OUTCOME_LABEL_CONTRACT_ID:
        return _outcome_label_issues(document)
    if contract_id == _AUTHORITY_MANIFEST_CONTRACT_ID:
        return _authority_manifest_issues(document)
    return []


class ContractRegistry:
    """An immutable view of the repository's owned JSON Schema contracts."""

    def __init__(self, repo_root: Path | str | None = None) -> None:
        self.repo_root = (
            Path(repo_root).resolve() if repo_root is not None else _default_repo_root().resolve()
        )
        self._records = _discover_records(self.repo_root)
        resources = [
            (record.schema_uri, Resource.from_contents(record.schema))
            for record in self._records.values()
        ]
        self._reference_registry = Registry().with_resources(resources)

    @property
    def contract_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    def schema_for(self, contract_id: str) -> Mapping[str, Any]:
        requested = _validate_requested_id(contract_id)
        try:
            return self._records[requested].schema
        except KeyError as exc:
            supported = ", ".join(self.contract_ids)
            raise UnsupportedContractError(
                f"unsupported contract_id {requested!r}; supported: {supported}"
            ) from exc

    def issues(self, contract_id: str, document: Any) -> tuple[ValidationIssue, ...]:
        requested = _validate_requested_id(contract_id)
        schema = self.schema_for(requested)
        validator = Draft202012Validator(
            schema,
            registry=self._reference_registry,
            format_checker=_FORMAT_CHECKER,
        )
        issues = [
            ValidationIssue(_json_path(tuple(error.absolute_path)), "schema", error.message)
            for error in validator.iter_errors(document)
        ]
        issues.extend(_interval_issues(document))
        if requested == _PACKET_CONTRACT_ID and isinstance(document, Mapping):
            issues.extend(_packet_authority_issues(document))
        if isinstance(document, Mapping):
            issues.extend(_contract_semantic_issues(requested, document))
        return tuple(sorted(set(issues)))

    def validate(self, contract_id: str, document: Any) -> None:
        requested = _validate_requested_id(contract_id)
        if isinstance(document, Mapping):
            embedded = document.get("contract_id")
            if embedded is not None and embedded != requested:
                raise ContractValidationError(
                    requested,
                    (
                        ValidationIssue(
                            "$.contract_id",
                            "contract_id.mismatch",
                            f"embedded contract_id {embedded!r} does not match requested "
                            f"{requested!r}",
                        ),
                    ),
                )
        issues = self.issues(requested, document)
        if issues:
            raise ContractValidationError(requested, issues)


def validate_contract(
    contract_or_document: str | Mapping[str, Any],
    document: Any | None = None,
    *,
    contract_id: str | None = None,
    repo_root: Path | str | None = None,
) -> None:
    """Validate a document, inferring its ID or accepting an explicit ID.

    Both ``validate_contract(document)`` and
    ``validate_contract("source_record.v1", document)`` are supported. The
    keyword ``contract_id`` form is available when inference is undesirable.
    """

    if document is None:
        if not isinstance(contract_or_document, Mapping):
            raise UnsupportedContractError("a contract document must be a JSON object")
        payload: Any = contract_or_document
        inferred_id = payload.get("contract_id")
        requested = contract_id if contract_id is not None else inferred_id
    else:
        if contract_id is not None:
            raise TypeError("contract_id cannot be supplied twice")
        requested = contract_or_document
        payload = document
    registry = ContractRegistry(repo_root)
    registry.validate(_validate_requested_id(requested), payload)


def canonical_json_bytes(value: Any) -> bytes:
    """Encode JSON deterministically, sorting object keys but not arrays."""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return encoded.encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise ContractError(f"value is not canonicalizable JSON: {exc}") from exc


def canonical_json_sha256(value: Any) -> str:
    """Return the lowercase SHA-256 hex digest of canonical JSON bytes."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def ctgov_query_manifest_sha256(manifest: Mapping[str, Any]) -> str:
    """Hash a CT.gov query manifest without its self-declared digest."""

    payload = {key: value for key, value in manifest.items() if key != "query_sha256"}
    return canonical_json_sha256(payload)


def _canonical_json_equal(first: Any, second: Any) -> bool:
    """Compare JSON values without Python's bool/int or int/float coercion."""

    return canonical_json_bytes(first) == canonical_json_bytes(second)


def _pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _pointer(parts: Sequence[str | int]) -> str:
    return "/" + "/".join(_pointer_escape(str(part)) for part in parts)


def _change_family(
    json_path: str,
    before_document: Any | None = None,
    after_document: Any | None = None,
) -> str:
    if json_path.endswith("/overallStatus"):
        return "registry_status"
    if json_path.endswith("/enrollmentInfo/type"):
        return "enrollment_type"
    if json_path.endswith("/enrollmentInfo") or "/enrollmentInfo/count" in json_path:
        enrollment_type_path = "/protocolSection/designModule/enrollmentInfo/type"
        observed_types = {
            value
            for document in (before_document, after_document)
            if isinstance(document, Mapping)
            for value in [_resolve_json_pointer(document, enrollment_type_path)]
            if isinstance(value, str)
        }
        if "ACTUAL" in observed_types:
            return "enrollment_actual"
        if observed_types == {"ESTIMATED"}:
            return "enrollment_target"
        return "enrollment_count"
    if "/primaryCompletionDateStruct" in json_path:
        return "primary_completion_date"
    if "/completionDateStruct" in json_path:
        return "completion_date"
    if "/contactsLocationsModule/locations" in json_path:
        return "site_set"
    if (
        "/outcomesModule/primaryOutcomes" in json_path
        or "/outcomesModule/secondaryOutcomes" in json_path
    ):
        return "endpoint_record"
    return "other"


def exact_json_diff(before: Any, after: Any) -> list[dict[str, Any]]:
    """Return a deterministic exact JSON diff with source arrays kept atomic."""

    operations: list[dict[str, Any]] = []

    def walk(old: Any, new: Any, parts: tuple[str | int, ...]) -> None:
        if _canonical_json_equal(old, new):
            return
        if isinstance(old, Mapping) and isinstance(new, Mapping):
            old_keys = set(old)
            new_keys = set(new)
            for key in sorted(old_keys - new_keys):
                path = _pointer((*parts, str(key)))
                operations.append(
                    {
                        "op": "remove",
                        "json_path": path,
                        "change_family": _change_family(path, before, after),
                        "before_state": "present",
                        "before_value": old[key],
                        "after_state": "missing",
                        "after_value": None,
                    }
                )
            for key in sorted(new_keys - old_keys):
                path = _pointer((*parts, str(key)))
                operations.append(
                    {
                        "op": "add",
                        "json_path": path,
                        "change_family": _change_family(path, before, after),
                        "before_state": "missing",
                        "before_value": None,
                        "after_state": "present",
                        "after_value": new[key],
                    }
                )
            for key in sorted(old_keys & new_keys):
                walk(old[key], new[key], (*parts, str(key)))
            return

        path = _pointer(parts)
        operations.append(
            {
                "op": "replace",
                "json_path": path,
                "change_family": _change_family(path, before, after),
                "before_state": "present",
                "before_value": old,
                "after_state": "present",
                "after_value": new,
            }
        )

    walk(before, after, ())
    return sorted(operations, key=lambda operation: operation["json_path"])


_MISSING = object()


def _resolve_json_pointer(document: Any, json_pointer: str) -> Any:
    current = document
    if not json_pointer.startswith("/"):
        return _MISSING
    for encoded in json_pointer[1:].split("/"):
        key = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping) and key in current:
            current = current[key]
        else:
            return _MISSING
    return current


def receipt_payloads_sha256(receipts: Sequence[Mapping[str, Any]]) -> str:
    """Hash an ordered set of sanitized page-receipt payloads."""

    return canonical_json_sha256(list(receipts))


class _DuplicateJSONKeyError(ValueError):
    """Raised when an archived source response contains an ambiguous object."""


def _strict_json_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKeyError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value!r}")


def _strict_json_float(value: str) -> float:
    try:
        exact = Decimal(value)
        parsed = float(value)
        round_tripped = Decimal(repr(parsed))
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise ValueError(f"invalid JSON number {value!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number {value!r}")
    if round_tripped != exact:
        raise ValueError(
            f"JSON number {value!r} is not losslessly representable as binary64"
        )
    return parsed


def validate_source_page_receipt_against_raw_response(
    receipt: Mapping[str, Any],
    raw_page_body: bytes | bytearray | memoryview,
    *,
    repo_root: Path | str | None = None,
) -> Mapping[str, Any]:
    """Verify one sanitized receipt against the exact archived response bytes."""

    registry = ContractRegistry(repo_root)
    registry.validate(_PAGE_RECEIPT_CONTRACT_ID, receipt)
    issues: list[ValidationIssue] = []
    if not isinstance(raw_page_body, (bytes, bytearray, memoryview)):
        issues.append(
            ValidationIssue(
                "$.response.raw_response_object_key",
                "receipt.raw_response_type",
                "raw page evidence must be supplied as exact bytes",
            )
        )
        raise ContractValidationError(_PAGE_RECEIPT_CONTRACT_ID, issues)

    raw_bytes = bytes(raw_page_body)
    response = receipt.get("response")
    response = response if isinstance(response, Mapping) else {}
    actual_hash = hashlib.sha256(raw_bytes).hexdigest()
    if response.get("exact_response_sha256") != actual_hash:
        issues.append(
            ValidationIssue(
                "$.response.exact_response_sha256",
                "receipt.raw_response_hash",
                f"archived response bytes hash to {actual_hash}",
            )
        )
    if response.get("byte_count") != len(raw_bytes):
        issues.append(
            ValidationIssue(
                "$.response.byte_count",
                "receipt.raw_response_length",
                f"archived response contains {len(raw_bytes)} bytes",
            )
        )
    headers = response.get("headers")
    content_length = headers.get("content-length") if isinstance(headers, Mapping) else None
    content_length_is_valid = (
        isinstance(content_length, str)
        and len(content_length) <= 20
        and re.fullmatch(r"[0-9]+", content_length) is not None
        and int(content_length) == len(raw_bytes)
    )
    if content_length is not None and not content_length_is_valid:
        issues.append(
            ValidationIssue(
                "$.response.headers.content-length",
                "receipt.raw_response_length",
                "content-length header must match the archived response byte count",
            )
        )

    parsed: Any = _MISSING
    try:
        parsed = json.loads(
            raw_bytes.decode("utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_nonfinite_json_constant,
            parse_float=_strict_json_float,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        issues.append(
            ValidationIssue(
                "$.response.raw_response_object_key",
                "receipt.raw_response_json",
                f"archived response must be unambiguous UTF-8 JSON: {exc}",
            )
        )

    studies: Any = None
    if parsed is not _MISSING and not isinstance(parsed, Mapping):
        issues.append(
            ValidationIssue(
                "$.response.raw_response_object_key",
                "receipt.raw_response_shape",
                "ClinicalTrials.gov page response must be a JSON object",
            )
        )
    elif isinstance(parsed, Mapping):
        try:
            canonical_json_bytes(parsed)
        except ContractError as exc:
            issues.append(
                ValidationIssue(
                    "$.response.raw_response_object_key",
                    "receipt.raw_response_json",
                    f"archived response contains unsupported JSON values: {exc}",
                )
            )
        studies = parsed.get("studies")
        if not isinstance(studies, list):
            issues.append(
                ValidationIssue(
                    "$.response.study_count",
                    "receipt.raw_response_shape",
                    "ClinicalTrials.gov page response must contain a studies array",
                )
            )
        elif response.get("study_count") != len(studies):
            issues.append(
                ValidationIssue(
                    "$.response.study_count",
                    "receipt.raw_response_study_count",
                    f"archived response contains {len(studies)} studies",
                )
            )
        if isinstance(studies, list):
            non_object_indexes = [
                index for index, study in enumerate(studies) if not isinstance(study, Mapping)
            ]
            if non_object_indexes:
                issues.append(
                    ValidationIssue(
                        "$.response.study_count",
                        "receipt.raw_response_study_shape",
                        "every studies entry must be a JSON object; invalid indexes: "
                        + ", ".join(str(index) for index in non_object_indexes[:10]),
                    )
                )

        raw_next_token = parsed.get("nextPageToken")
        expected_token_hash: str | None = None
        if raw_next_token is not None:
            if not isinstance(raw_next_token, str) or not raw_next_token:
                issues.append(
                    ValidationIssue(
                        "$.response.next_page_token_sha256",
                        "receipt.raw_pagination_token",
                        "raw nextPageToken must be a non-empty string or absent",
                    )
                )
            else:
                try:
                    encoded_next_token = raw_next_token.encode("utf-8")
                except UnicodeEncodeError:
                    issues.append(
                        ValidationIssue(
                            "$.response.next_page_token_sha256",
                            "receipt.raw_pagination_token",
                            "raw nextPageToken must contain valid Unicode scalar values",
                        )
                    )
                else:
                    expected_token_hash = hashlib.sha256(encoded_next_token).hexdigest()
        if response.get("next_page_token_sha256") != expected_token_hash:
            issues.append(
                ValidationIssue(
                    "$.response.next_page_token_sha256",
                    "receipt.raw_pagination_token",
                    "pagination-token hash must match the exact archived response",
                )
            )

    if issues:
        raise ContractValidationError(_PAGE_RECEIPT_CONTRACT_ID, issues)
    assert isinstance(parsed, Mapping)
    return parsed


def validate_ctgov_fetch_run_against_receipts(
    run: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    *,
    repo_root: Path | str | None = None,
) -> None:
    """Bind a ClinicalTrials.gov run to its complete ordered receipt chain."""

    registry = ContractRegistry(repo_root)
    registry.validate(_CTGOV_FETCH_RUN_CONTRACT_ID, run)
    for receipt in receipts:
        registry.validate(_PAGE_RECEIPT_CONTRACT_ID, receipt)

    issues: list[ValidationIssue] = []
    receipt_ids = [receipt.get("receipt_id") for receipt in receipts]
    ordinals = [receipt.get("page_ordinal") for receipt in receipts]
    expected_ordinals = list(range(len(receipts)))
    if ordinals != expected_ordinals:
        issues.append(
            ValidationIssue(
                "$.receipt_refs",
                "fetch_run.receipt_order",
                "receipt payloads must be ordered by contiguous zero-based page ordinal",
            )
        )
    if run.get("receipt_refs") != receipt_ids:
        issues.append(
            ValidationIssue(
                "$.receipt_refs",
                "fetch_run.receipt_binding",
                "receipt references must exactly match the supplied ordered receipts",
            )
        )
    if run.get("receipt_payloads_sha256") != receipt_payloads_sha256(receipts):
        issues.append(
            ValidationIssue(
                "$.receipt_payloads_sha256",
                "fetch_run.receipt_hash",
                "receipt payload hash must match the supplied ordered receipts",
            )
        )

    manifest = run.get("query_manifest")
    query_hash = manifest.get("query_sha256") if isinstance(manifest, Mapping) else None
    source_timestamp = run.get("source_dataset_timestamp_before_raw")
    started_at = _parse_temporal(run.get("started_at"))
    finished_at = _parse_temporal(run.get("finished_at"))
    run_transaction = _parse_temporal(run.get("transaction_from"))
    previous_next_token: Any = None
    seen_request_tokens: set[str] = set()
    total_studies = 0
    for index, receipt in enumerate(receipts):
        request = receipt.get("request")
        response = receipt.get("response")
        request_token = (
            request.get("page_token_sha256") if isinstance(request, Mapping) else None
        )
        next_token = (
            response.get("next_page_token_sha256")
            if isinstance(response, Mapping)
            else None
        )
        if receipt.get("run_id") != run.get("run_id"):
            issues.append(
                ValidationIssue(
                    f"$.receipt_refs[{index}]",
                    "fetch_run.receipt_binding",
                    "receipt run_id must match the fetch run",
                )
            )
        if receipt.get("source_id") != run.get("source_id"):
            issues.append(
                ValidationIssue(
                    f"$.receipt_refs[{index}]",
                    "fetch_run.receipt_binding",
                    "receipt source_id must match the fetch run",
                )
            )
        if isinstance(request, Mapping) and request.get("query_sha256") != query_hash:
            issues.append(
                ValidationIssue(
                    f"$.receipt_refs[{index}]",
                    "fetch_run.query_binding",
                    "receipt query hash must match the run query manifest",
                )
            )
        if receipt.get("source_dataset_timestamp_raw") != source_timestamp:
            issues.append(
                ValidationIssue(
                    f"$.receipt_refs[{index}]",
                    "fetch_run.source_version_binding",
                    "receipt source dataset timestamp must match the stable run version",
                )
            )
        if receipt.get("source_api_version") != run.get("source_api_version"):
            issues.append(
                ValidationIssue(
                    f"$.receipt_refs[{index}]",
                    "fetch_run.source_version_binding",
                    "receipt API version must match the fetch run",
                )
            )
        receipt_transaction = _parse_temporal(receipt.get("transaction_from"))
        if (
            receipt_transaction is not None
            and run_transaction is not None
            and receipt_transaction > run_transaction
        ):
            issues.append(
                ValidationIssue(
                    f"$.receipt_refs[{index}]",
                    "fetch_run.receipt_transaction",
                    "receipt transaction time cannot postdate the completed run transaction",
                )
            )
        if request_token != previous_next_token:
            issues.append(
                ValidationIssue(
                    f"$.receipt_refs[{index}]",
                    "fetch_run.pagination_chain",
                    "each request token must match the prior page's next-token hash",
                )
            )
        if isinstance(request_token, str) and request_token in seen_request_tokens:
            issues.append(
                ValidationIssue(
                    f"$.receipt_refs[{index}]",
                    "fetch_run.pagination_cycle",
                    "pagination request-token hashes may not repeat within a run",
                )
            )
        if isinstance(next_token, str) and (
            next_token == request_token or next_token in seen_request_tokens
        ):
            issues.append(
                ValidationIssue(
                    f"$.receipt_refs[{index}]",
                    "fetch_run.pagination_cycle",
                    "pagination next-token hash would create a repeated-token cycle",
                )
            )
        if index < len(receipts) - 1 and next_token is None:
            issues.append(
                ValidationIssue(
                    f"$.receipt_refs[{index}]",
                    "fetch_run.pagination_chain",
                    "only the final receipt may terminate pagination",
                )
            )
        if isinstance(request_token, str):
            seen_request_tokens.add(request_token)
        previous_next_token = next_token

        if isinstance(response, Mapping):
            status_code = response.get("status_code")
            if run.get("run_state") == "complete" and not (
                isinstance(status_code, int) and 200 <= status_code < 300
            ):
                issues.append(
                    ValidationIssue(
                        f"$.receipt_refs[{index}]",
                        "fetch_run.receipt_status",
                        "complete runs require successful page responses",
                    )
                )
            study_count = response.get("study_count")
            if isinstance(study_count, int):
                total_studies += study_count
            received_at = _parse_temporal(response.get("received_at"))
            if (
                received_at is not None
                and started_at is not None
                and received_at < started_at
            ) or (
                received_at is not None
                and finished_at is not None
                and received_at > finished_at
            ):
                issues.append(
                    ValidationIssue(
                        f"$.receipt_refs[{index}]",
                        "fetch_run.receipt_time",
                        "receipt response time must fall within the fetch-run interval",
                    )
                )

    counts = run.get("counts")
    if isinstance(counts, Mapping) and total_studies != counts.get("studies_fetched"):
        issues.append(
            ValidationIssue(
                "$.counts.studies_fetched",
                "fetch_run.receipt_count",
                "studies_fetched must equal the sum of receipt study counts",
            )
        )
    if run.get("run_state") == "complete":
        terminal_ref = receipt_ids[-1] if receipt_ids else None
        if run.get("terminal_receipt_ref") != terminal_ref or previous_next_token is not None:
            issues.append(
                ValidationIssue(
                    "$.terminal_receipt_ref",
                    "fetch_run.terminal_receipt",
                    "complete runs require the final referenced receipt to end pagination",
                )
            )

    if issues:
        raise ContractValidationError(_CTGOV_FETCH_RUN_CONTRACT_ID, issues)


def validate_evidence_claim_against_source_records(
    claim: Mapping[str, Any],
    source_records: Sequence[Mapping[str, Any]],
    *,
    repo_root: Path | str | None = None,
) -> None:
    """Bind an evidence claim to existing source records and their rights class."""

    registry = ContractRegistry(repo_root)
    registry.validate(_EVIDENCE_CLAIM_CONTRACT_ID, claim)
    for source_record in source_records:
        registry.validate(_SOURCE_RECORD_CONTRACT_ID, source_record)

    issues: list[ValidationIssue] = []
    record_ids = [record.get("record_id") for record in source_records]
    if len(record_ids) != len(set(record_ids)):
        issues.append(
            ValidationIssue(
                "$.source_record_refs",
                "evidence.source_binding",
                "supplied source records must have unique record IDs",
            )
        )
    if set(claim.get("source_record_refs", ())) != set(record_ids):
        issues.append(
            ValidationIssue(
                "$.source_record_refs",
                "evidence.source_binding",
                "claim references must exactly match the supplied source records",
            )
        )
    license_classes = {record.get("license_class") for record in source_records}
    if len(license_classes) != 1 or claim.get("license_class") not in license_classes:
        issues.append(
            ValidationIssue(
                "$.license_class",
                "evidence.rights_binding",
                "one claim cannot combine or relabel source-record rights classes",
            )
        )
    claim_transaction = _parse_temporal(claim.get("transaction_from"))
    for index, source_record in enumerate(source_records):
        source_transaction = _parse_temporal(source_record.get("transaction_from"))
        if (
            claim_transaction is not None
            and source_transaction is not None
            and claim_transaction < source_transaction
        ):
            issues.append(
                ValidationIssue(
                    "$.transaction_from",
                    "evidence.transaction_binding",
                    f"claim transaction cannot precede source record {index}",
                )
            )
    if claim.get("evidence_class") == "primary_source_observation" and len(
        source_records
    ) == 1:
        source_record = source_records[0]
        for field in (
            "source_published_at",
            "source_effective_at",
            "retrieved_at",
            "first_seen_at",
        ):
            if claim.get(field) != source_record.get(field):
                issues.append(
                    ValidationIssue(
                        f"$.{field}",
                        "evidence.provenance_binding",
                        f"primary-source claim {field} must match its source record",
                    )
                )
    if issues:
        raise ContractValidationError(_EVIDENCE_CLAIM_CONTRACT_ID, issues)


def _validate_ctgov_raw_run_evidence(
    run: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    raw_page_bodies_by_receipt: Mapping[
        str, bytes | bytearray | memoryview
    ],
    *,
    repo_root: Path | str | None = None,
) -> tuple[dict[str, Mapping[str, Any]], tuple[str, ...]]:
    """Validate every raw page and derive the run's counts and publication refs."""

    validate_ctgov_fetch_run_against_receipts(run, receipts, repo_root=repo_root)
    receipt_ids = [receipt.get("receipt_id") for receipt in receipts]
    expected_receipt_ids = {
        receipt_id for receipt_id in receipt_ids if isinstance(receipt_id, str)
    }
    if set(raw_page_bodies_by_receipt) != expected_receipt_ids:
        raise ContractValidationError(
            _CTGOV_FETCH_RUN_CONTRACT_ID,
            (
                ValidationIssue(
                    "$.receipt_refs",
                    "raw_run.raw_page_coverage",
                    "raw page bodies must exactly cover the run's receipt IDs",
                ),
            ),
        )

    parsed_pages: dict[str, Mapping[str, Any]] = {}
    for receipt in receipts:
        receipt_id = receipt["receipt_id"]
        parsed_pages[receipt_id] = validate_source_page_receipt_against_raw_response(
            receipt,
            raw_page_bodies_by_receipt[receipt_id],
            repo_root=repo_root,
        )

    issues: list[ValidationIssue] = []
    hashes_by_nct: dict[str, set[str]] = {}
    derived_fetched = 0
    for receipt_id, page in parsed_pages.items():
        studies = page["studies"]
        for study_index, study in enumerate(studies):
            derived_fetched += 1
            nct_id = _resolve_json_pointer(
                study, "/protocolSection/identificationModule/nctId"
            )
            path = f"$.raw_pages.{receipt_id}.studies[{study_index}]"
            if not isinstance(nct_id, str) or not re.fullmatch(
                r"NCT[0-9]{8}", nct_id
            ):
                issues.append(
                    ValidationIssue(
                        path,
                        "raw_run.study_identity",
                        "every raw study must carry a canonical NCT ID",
                    )
                )
                continue
            try:
                content_hash = canonical_json_sha256(study)
            except ContractError as exc:
                issues.append(
                    ValidationIssue(
                        path,
                        "raw_run.study_content",
                        f"raw study is not canonicalizable: {exc}",
                    )
                )
                continue
            hashes_by_nct.setdefault(nct_id, set()).add(content_hash)

    divergent_nct_ids = sorted(
        nct_id for nct_id, hashes in hashes_by_nct.items() if len(hashes) != 1
    )
    if divergent_nct_ids:
        issues.append(
            ValidationIssue(
                "$.counts.studies_duplicate",
                "raw_run.divergent_duplicate",
                "one run cannot contain divergent bodies for the same NCT ID: "
                + ", ".join(divergent_nct_ids),
            )
        )

    configured_nct_ids = run["query_manifest"]["configured_nct_ids"]
    if set(hashes_by_nct) != set(configured_nct_ids):
        issues.append(
            ValidationIssue(
                "$.query_manifest.configured_nct_ids",
                "raw_run.nct_coverage",
                "raw pages must cover exactly the configured NCT universe",
            )
        )

    derived_unique = len(hashes_by_nct)
    derived_duplicate = derived_fetched - derived_unique
    counts = run["counts"]
    for field, expected in (
        ("studies_fetched", derived_fetched),
        ("studies_unique", derived_unique),
        ("studies_duplicate", derived_duplicate),
    ):
        if counts.get(field) != expected:
            issues.append(
                ValidationIssue(
                    f"$.counts.{field}",
                    "raw_run.derived_counts",
                    f"{field} must equal the raw-page-derived value {expected}",
                )
            )

    derived_refs = tuple(
        sorted(
            f"src:ctgov:{nct_id}:sha256:{next(iter(hashes))}"
            for nct_id, hashes in hashes_by_nct.items()
            if len(hashes) == 1
        )
    )
    if run.get("run_state") == "complete" and run[
        "published_source_record_refs"
    ] != list(derived_refs):
        issues.append(
            ValidationIssue(
                "$.published_source_record_refs",
                "raw_run.derived_manifest",
                "publication manifest must be derived from the exact raw studies",
            )
        )
    if issues:
        raise ContractValidationError(_CTGOV_FETCH_RUN_CONTRACT_ID, issues)
    return parsed_pages, derived_refs


def _validate_trial_source_snapshot_against_validated_pages(
    source_snapshot: Mapping[str, Any],
    run: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    parsed_pages: Mapping[str, Mapping[str, Any]],
) -> None:
    """Bind one schema-valid snapshot to an already validated raw page set."""

    issues: list[ValidationIssue] = []
    if run.get("run_state") != "complete" or run.get("completeness_state") != "reconciled":
        issues.append(
            ValidationIssue(
                "$.run_ref",
                "source_snapshot.complete_run",
                "publishable source snapshots require a reconciled complete fetch run",
            )
        )

    receipt_by_id = {receipt.get("receipt_id"): receipt for receipt in receipts}
    receipt_ref = source_snapshot.get("page_receipt_ref")
    selected_receipt = receipt_by_id.get(receipt_ref)
    if source_snapshot.get("run_ref") != run.get("run_id"):
        issues.append(
            ValidationIssue(
                "$.run_ref",
                "source_snapshot.run_binding",
                "source snapshot run reference must resolve to the supplied fetch run",
            )
        )
    published_refs = run.get("published_source_record_refs")
    if (
        not isinstance(published_refs, list)
        or source_snapshot.get("source_record_ref") not in published_refs
    ):
        issues.append(
            ValidationIssue(
                "$.source_record_ref",
                "source_snapshot.publication_manifest",
                "source snapshot must be present in the run publication manifest",
            )
        )

    manifest = run.get("query_manifest")
    configured_nct_ids = (
        manifest.get("configured_nct_ids") if isinstance(manifest, Mapping) else None
    )
    if (
        not isinstance(configured_nct_ids, list)
        or source_snapshot.get("nct_id") not in configured_nct_ids
    ):
        issues.append(
            ValidationIssue(
                "$.nct_id",
                "source_snapshot.query_binding",
                "source snapshot NCT ID must belong to the run's configured universe",
            )
        )

    if selected_receipt is None:
        issues.append(
            ValidationIssue(
                "$.page_receipt_ref",
                "source_snapshot.receipt_binding",
                "source snapshot page receipt must resolve inside the fetch run",
            )
        )
    else:
        raw_page = parsed_pages[selected_receipt["receipt_id"]]
        response = selected_receipt.get("response")
        response_hash = (
            response.get("exact_response_sha256")
            if isinstance(response, Mapping)
            else None
        )
        received_at = (
            response.get("received_at") if isinstance(response, Mapping) else None
        )
        for actual, expected, path in (
            (
                source_snapshot.get("exact_response_sha256"),
                response_hash,
                "$.exact_response_sha256",
            ),
            (
                source_snapshot.get("source_dataset_timestamp_raw"),
                selected_receipt.get("source_dataset_timestamp_raw"),
                "$.source_dataset_timestamp_raw",
            ),
            (
                source_snapshot.get("retrieved_at"),
                received_at,
                "$.retrieved_at",
            ),
        ):
            if actual != expected:
                issues.append(
                    ValidationIssue(
                        path,
                        "source_snapshot.receipt_binding",
                        "source snapshot and selected page receipt must agree",
                    )
                )

        studies = raw_page.get("studies")
        study_index = source_snapshot.get("source_page_study_index")
        extracted_study: Any = _MISSING
        if (
            isinstance(studies, list)
            and isinstance(study_index, int)
            and not isinstance(study_index, bool)
            and 0 <= study_index < len(studies)
        ):
            extracted_study = studies[study_index]
        if extracted_study is _MISSING:
            issues.append(
                ValidationIssue(
                    "$.source_page_study_index",
                    "source_snapshot.extraction_binding",
                    "study index must resolve inside the exact archived page response",
                )
            )
        elif not isinstance(extracted_study, Mapping) or not _canonical_json_equal(
            extracted_study, source_snapshot.get("canonical_study")
        ):
            issues.append(
                ValidationIssue(
                    "$.canonical_study",
                    "source_snapshot.extraction_binding",
                    "canonical study must exactly equal the indexed archived page study",
                )
            )

    source_transaction = _parse_temporal(source_snapshot.get("transaction_from"))
    run_transaction = _parse_temporal(run.get("transaction_from"))
    receipt_transaction = _parse_temporal(
        selected_receipt.get("transaction_from")
        if isinstance(selected_receipt, Mapping)
        else None
    )
    if (
        source_transaction is not None
        and receipt_transaction is not None
        and source_transaction < receipt_transaction
    ) or (
        source_transaction is not None
        and run_transaction is not None
        and source_transaction > run_transaction
    ):
        issues.append(
            ValidationIssue(
                "$.transaction_from",
                "source_snapshot.transaction_binding",
                "source snapshot transaction must follow its receipt and precede the run commit",
            )
        )

    if issues:
        raise ContractValidationError(_TRIAL_SOURCE_SNAPSHOT_CONTRACT_ID, issues)


def validate_trial_source_snapshot_against_fetch_evidence(
    source_snapshot: Mapping[str, Any],
    run: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    *,
    raw_page_bodies_by_receipt: Mapping[
        str, bytes | bytearray | memoryview
    ],
    repo_root: Path | str | None = None,
) -> None:
    """Bind a snapshot to a published study inside exact archived page bytes."""

    registry = ContractRegistry(repo_root)
    registry.validate(_TRIAL_SOURCE_SNAPSHOT_CONTRACT_ID, source_snapshot)
    parsed_pages, _ = _validate_ctgov_raw_run_evidence(
        run,
        receipts,
        raw_page_bodies_by_receipt,
        repo_root=repo_root,
    )
    _validate_trial_source_snapshot_against_validated_pages(
        source_snapshot,
        run,
        receipts,
        parsed_pages,
    )


def validate_ctgov_publication_bundle(
    run: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    raw_page_bodies_by_receipt: Mapping[
        str, bytes | bytearray | memoryview
    ],
    source_snapshots: Sequence[Mapping[str, Any]],
    *,
    repo_root: Path | str | None = None,
) -> None:
    """Prove complete-run coverage from every raw page through every snapshot."""

    registry = ContractRegistry(repo_root)
    parsed_pages, derived_refs = _validate_ctgov_raw_run_evidence(
        run,
        receipts,
        raw_page_bodies_by_receipt,
        repo_root=repo_root,
    )
    if run.get("run_state") != "complete" or run.get("completeness_state") != "reconciled":
        raise ContractValidationError(
            _CTGOV_FETCH_RUN_CONTRACT_ID,
            (
                ValidationIssue(
                    "$.run_state",
                    "publication_bundle.complete_run",
                    "publication bundles require a reconciled complete run",
                ),
            ),
        )
    for source_snapshot in source_snapshots:
        registry.validate(_TRIAL_SOURCE_SNAPSHOT_CONTRACT_ID, source_snapshot)

    issues: list[ValidationIssue] = []
    configured_nct_ids = run["query_manifest"]["configured_nct_ids"]
    counts = run["counts"]
    snapshot_refs = [snapshot["source_record_ref"] for snapshot in source_snapshots]
    snapshot_nct_ids = [snapshot["nct_id"] for snapshot in source_snapshots]
    snapshot_ids = [snapshot["source_snapshot_id"] for snapshot in source_snapshots]
    snapshot_receipt_refs = [
        snapshot["page_receipt_ref"] for snapshot in source_snapshots
    ]
    if tuple(sorted(snapshot_refs)) != derived_refs or len(snapshot_refs) != len(
        set(snapshot_refs)
    ):
        issues.append(
            ValidationIssue(
                "$.published_source_record_refs",
                "publication_bundle.snapshot_coverage",
                "source snapshots must exactly match the raw-derived publication manifest",
            )
        )
    if set(snapshot_nct_ids) != set(configured_nct_ids) or len(
        snapshot_nct_ids
    ) != len(set(snapshot_nct_ids)):
        issues.append(
            ValidationIssue(
                "$.query_manifest.configured_nct_ids",
                "publication_bundle.snapshot_nct_coverage",
                "source snapshots must cover every configured NCT exactly once",
            )
        )
    if len(snapshot_ids) != len(set(snapshot_ids)):
        issues.append(
            ValidationIssue(
                "$.published_source_record_refs",
                "publication_bundle.snapshot_identity",
                "source snapshot IDs must be unique within a publication bundle",
            )
        )
    expected_receipt_ids = {receipt["receipt_id"] for receipt in receipts}
    if not set(snapshot_receipt_refs).issubset(expected_receipt_ids):
        issues.append(
            ValidationIssue(
                "$.receipt_refs",
                "publication_bundle.snapshot_receipt",
                "every source snapshot must resolve to a receipt in this run",
            )
        )
    if counts.get("studies_published") != len(source_snapshots):
        issues.append(
            ValidationIssue(
                "$.counts.studies_published",
                "publication_bundle.snapshot_count",
                "published-study count must equal the source snapshot count",
            )
        )
    if issues:
        raise ContractValidationError(_CTGOV_FETCH_RUN_CONTRACT_ID, issues)

    for source_snapshot in source_snapshots:
        _validate_trial_source_snapshot_against_validated_pages(
            source_snapshot,
            run,
            receipts,
            parsed_pages,
        )


def validate_trial_observation_against_source_evidence(
    observation: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    run: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    *,
    raw_page_bodies_by_receipt: Mapping[
        str, bytes | bytearray | memoryview
    ],
    repo_root: Path | str | None = None,
) -> None:
    """Bind one trial observation to its source snapshot, run, and page receipt."""

    registry = ContractRegistry(repo_root)
    registry.validate(_TRIAL_OBSERVATION_CONTRACT_ID, observation)
    validate_trial_source_snapshot_against_fetch_evidence(
        source_snapshot,
        run,
        receipts,
        raw_page_bodies_by_receipt=raw_page_bodies_by_receipt,
        repo_root=repo_root,
    )

    issues: list[ValidationIssue] = []
    receipt_by_id = {receipt.get("receipt_id"): receipt for receipt in receipts}
    receipt_ref = observation.get("page_receipt_ref")
    selected_receipt = receipt_by_id.get(receipt_ref)
    bindings = (
        (observation.get("nct_id"), source_snapshot.get("nct_id"), "$.nct_id"),
        (
            observation.get("source_snapshot_ref"),
            source_snapshot.get("source_snapshot_id"),
            "$.source_snapshot_ref",
        ),
        (
            observation.get("canonical_content_sha256"),
            source_snapshot.get("canonical_content_sha256"),
            "$.canonical_content_sha256",
        ),
        (observation.get("run_ref"), run.get("run_id"), "$.run_ref"),
        (
            source_snapshot.get("run_ref"),
            run.get("run_id"),
            "$.source_snapshot_ref",
        ),
        (
            source_snapshot.get("page_receipt_ref"),
            receipt_ref,
            "$.page_receipt_ref",
        ),
        (
            observation.get("source_last_update_posted_at"),
            source_snapshot.get("source_last_update_posted_at"),
            "$.source_last_update_posted_at",
        ),
        (
            observation.get("source_dataset_timestamp_raw"),
            source_snapshot.get("source_dataset_timestamp_raw"),
            "$.source_dataset_timestamp_raw",
        ),
        (
            observation.get("retrieved_at"),
            source_snapshot.get("retrieved_at"),
            "$.retrieved_at",
        ),
        (
            observation.get("first_seen_at"),
            source_snapshot.get("first_seen_at"),
            "$.first_seen_at",
        ),
    )
    for actual, expected, path in bindings:
        if actual != expected:
            issues.append(
                ValidationIssue(
                    path,
                    "observation.source_binding",
                    "observation, source snapshot, and run provenance must agree",
                )
            )

    manifest = run.get("query_manifest")
    configured_nct_ids = (
        manifest.get("configured_nct_ids") if isinstance(manifest, Mapping) else None
    )
    if (
        not isinstance(configured_nct_ids, list)
        or observation.get("nct_id") not in configured_nct_ids
    ):
        issues.append(
            ValidationIssue(
                "$.nct_id",
                "observation.query_binding",
                "observed NCT ID must belong to the run's configured universe",
            )
        )

    if selected_receipt is None:
        issues.append(
            ValidationIssue(
                "$.page_receipt_ref",
                "observation.receipt_binding",
                "page receipt reference must resolve inside the validated fetch run",
            )
        )
    else:
        response = selected_receipt.get("response")
        response_hash = (
            response.get("exact_response_sha256")
            if isinstance(response, Mapping)
            else None
        )
        received_at = (
            response.get("received_at") if isinstance(response, Mapping) else None
        )
        for actual, expected, path in (
            (
                source_snapshot.get("page_receipt_ref"),
                selected_receipt.get("receipt_id"),
                "$.page_receipt_ref",
            ),
            (
                source_snapshot.get("exact_response_sha256"),
                response_hash,
                "$.source_snapshot_ref",
            ),
            (
                source_snapshot.get("source_dataset_timestamp_raw"),
                selected_receipt.get("source_dataset_timestamp_raw"),
                "$.source_dataset_timestamp_raw",
            ),
            (
                source_snapshot.get("retrieved_at"),
                received_at,
                "$.retrieved_at",
            ),
        ):
            if actual != expected:
                issues.append(
                    ValidationIssue(
                        path,
                        "observation.receipt_binding",
                        "source snapshot and selected page receipt must agree",
                    )
                )

    observation_transaction = _parse_temporal(observation.get("transaction_from"))
    for source_transaction_raw in (
        source_snapshot.get("transaction_from"),
        selected_receipt.get("transaction_from")
        if isinstance(selected_receipt, Mapping)
        else None,
    ):
        source_transaction = _parse_temporal(source_transaction_raw)
        if (
            observation_transaction is not None
            and source_transaction is not None
            and observation_transaction < source_transaction
        ):
            issues.append(
                ValidationIssue(
                    "$.transaction_from",
                    "observation.transaction_binding",
                    "observation transaction cannot precede source evidence",
                )
            )

    if issues:
        raise ContractValidationError(_TRIAL_OBSERVATION_CONTRACT_ID, issues)


def validate_trial_projection_against_source(
    projection: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    *,
    run: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    raw_page_bodies_by_receipt: Mapping[
        str, bytes | bytearray | memoryview
    ],
    repo_root: Path | str | None = None,
) -> None:
    """Bind a read projection to complete fetch evidence and exact source facts."""

    validate_trial_source_snapshot_against_fetch_evidence(
        source_snapshot,
        run,
        receipts,
        raw_page_bodies_by_receipt=raw_page_bodies_by_receipt,
        repo_root=repo_root,
    )
    registry = ContractRegistry(repo_root)
    registry.validate(_TRIAL_SNAPSHOT_CONTRACT_ID, projection)
    issues: list[ValidationIssue] = []

    for projection_key, source_key, path in (
        ("nct_id", "nct_id", "$.nct_id"),
        ("source_snapshot_ref", "source_snapshot_id", "$.source_snapshot_ref"),
        ("source_record_ref", "source_record_ref", "$.source_record_ref"),
        ("canonical_content_sha256", "canonical_content_sha256", "$.canonical_content_sha256"),
        ("source_published_at", "source_published_at", "$.source_published_at"),
        ("source_effective_at", "source_effective_at", "$.source_effective_at"),
        ("retrieved_at", "retrieved_at", "$.retrieved_at"),
        ("first_seen_at", "first_seen_at", "$.first_seen_at"),
        ("valid_from", "valid_from", "$.valid_from"),
        ("valid_to", "valid_to", "$.valid_to"),
        ("parser_version", "canonicalizer_version", "$.parser_version"),
        ("source_schema_version", "source_schema_version", "$.source_schema_version"),
        ("license_class", "license_class", "$.license_class"),
    ):
        expected = source_snapshot.get(source_key)
        if projection_key == "parser_version":
            expected = "clinicaltrials_v2_parser.v1"
        if projection.get(projection_key) != expected:
            issues.append(
                ValidationIssue(
                    path,
                    "trial_snapshot.source_binding",
                    f"{projection_key} must match source snapshot {source_key}",
                )
            )

    attribution = projection.get("source_attribution")
    if isinstance(attribution, Mapping):
        for attribution_key, source_key in (
            ("source_uri", "source_uri"),
            ("source_processed_at_raw", "source_dataset_timestamp_raw"),
            ("source_last_update_posted_at", "source_last_update_posted_at"),
        ):
            if attribution.get(attribution_key) != source_snapshot.get(source_key):
                issues.append(
                    ValidationIssue(
                        f"$.source_attribution.{attribution_key}",
                        "trial_snapshot.provenance_binding",
                        f"{attribution_key} must match source snapshot {source_key}",
                    )
                )

    projection_transaction = _parse_temporal(projection.get("transaction_from"))
    source_transaction = _parse_temporal(source_snapshot.get("transaction_from"))
    if (
        projection_transaction is not None
        and source_transaction is not None
        and projection_transaction < source_transaction
    ):
        issues.append(
            ValidationIssue(
                "$.transaction_from",
                "trial_snapshot.transaction_binding",
                "projection transaction cannot precede its source snapshot",
            )
        )

    source_document = source_snapshot.get("canonical_study")
    facts = projection.get("facts")
    if isinstance(source_document, Mapping) and isinstance(facts, Mapping):
        for fact_name, fact in sorted(facts.items()):
            if not isinstance(fact, Mapping):
                continue
            expected_path = _TRIAL_FACT_JSON_PATHS.get(fact_name)
            if fact.get("source_json_path") != expected_path:
                issues.append(
                    ValidationIssue(
                        f"$.facts.{fact_name}.source_json_path",
                        "trial_snapshot.fact_path",
                        "fact must use its registered ClinicalTrials.gov JSON path",
                    )
                )
                continue
            source_value = _resolve_json_pointer(
                source_document, expected_path
            )
            state = fact.get("state")
            value = fact.get("value")
            if source_value is _MISSING:
                expected_state, expected_value = "source_missing", None
            elif source_value is None:
                expected_state, expected_value = "source_null", None
            else:
                expected_state, expected_value = "observed", source_value
            if state != expected_state or not _canonical_json_equal(value, expected_value):
                issues.append(
                    ValidationIssue(
                        f"$.facts.{fact_name}",
                        "trial_snapshot.fact_binding",
                        "fact state/value must match its source JSON path",
                    )
                )

    if issues:
        raise ContractValidationError(_TRIAL_SNAPSHOT_CONTRACT_ID, issues)


def validate_trial_diff_against_snapshots(
    diff: Mapping[str, Any],
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    before_observation: Mapping[str, Any],
    after_observation: Mapping[str, Any],
    *,
    before_run: Mapping[str, Any],
    before_receipts: Sequence[Mapping[str, Any]],
    before_raw_page_bodies_by_receipt: Mapping[
        str, bytes | bytearray | memoryview
    ],
    after_run: Mapping[str, Any],
    after_receipts: Sequence[Mapping[str, Any]],
    after_raw_page_bodies_by_receipt: Mapping[
        str, bytes | bytearray | memoryview
    ],
    repo_root: Path | str | None = None,
) -> None:
    """Recompute and bind an exact diff to source snapshots and observations."""

    validate_trial_observation_against_source_evidence(
        before_observation,
        before_snapshot,
        before_run,
        before_receipts,
        raw_page_bodies_by_receipt=before_raw_page_bodies_by_receipt,
        repo_root=repo_root,
    )
    validate_trial_observation_against_source_evidence(
        after_observation,
        after_snapshot,
        after_run,
        after_receipts,
        raw_page_bodies_by_receipt=after_raw_page_bodies_by_receipt,
        repo_root=repo_root,
    )
    registry = ContractRegistry(repo_root)
    registry.validate(_TRIAL_SOURCE_SNAPSHOT_CONTRACT_ID, before_snapshot)
    registry.validate(_TRIAL_SOURCE_SNAPSHOT_CONTRACT_ID, after_snapshot)
    registry.validate(_TRIAL_OBSERVATION_CONTRACT_ID, before_observation)
    registry.validate(_TRIAL_OBSERVATION_CONTRACT_ID, after_observation)
    registry.validate(_TRIAL_DIFF_CONTRACT_ID, diff)
    issues: list[ValidationIssue] = []

    bindings = (
        ("nct_id", before_snapshot.get("nct_id"), "$.nct_id"),
        (
            "before_source_snapshot_ref",
            before_snapshot.get("source_snapshot_id"),
            "$.before_source_snapshot_ref",
        ),
        (
            "after_source_snapshot_ref",
            after_snapshot.get("source_snapshot_id"),
            "$.after_source_snapshot_ref",
        ),
        (
            "before_content_sha256",
            before_snapshot.get("canonical_content_sha256"),
            "$.before_content_sha256",
        ),
        (
            "after_content_sha256",
            after_snapshot.get("canonical_content_sha256"),
            "$.after_content_sha256",
        ),
        (
            "before_observation_ref",
            before_observation.get("observation_id"),
            "$.before_observation_ref",
        ),
        (
            "after_observation_ref",
            after_observation.get("observation_id"),
            "$.after_observation_ref",
        ),
        (
            "observed_interval",
            after_observation.get("observed_interval"),
            "$.observed_interval",
        ),
        (
            "source_last_update_posted_at",
            after_snapshot.get("source_last_update_posted_at"),
            "$.source_last_update_posted_at",
        ),
        (
            "source_published_at",
            after_snapshot.get("source_published_at"),
            "$.source_published_at",
        ),
        (
            "source_effective_at",
            after_snapshot.get("source_effective_at"),
            "$.source_effective_at",
        ),
        ("valid_from", after_snapshot.get("valid_from"), "$.valid_from"),
        ("valid_to", after_snapshot.get("valid_to"), "$.valid_to"),
    )
    for field, expected, path in bindings:
        if diff.get(field) != expected:
            code = (
                "trial_diff.observation_binding"
                if "observation" in field or field == "observed_interval"
                else "trial_diff.source_binding"
            )
            issues.append(
                ValidationIssue(
                    path,
                    code,
                    f"{field} must match its referenced source snapshot",
                )
            )

    relational_bindings = (
        (
            after_snapshot.get("nct_id"),
            before_snapshot.get("nct_id"),
            "$.after_source_snapshot_ref",
            "both source snapshots must identify the same NCT ID",
        ),
        (
            before_observation.get("nct_id"),
            before_snapshot.get("nct_id"),
            "$.before_observation_ref",
            "before observation must identify the before snapshot's NCT ID",
        ),
        (
            after_observation.get("nct_id"),
            after_snapshot.get("nct_id"),
            "$.after_observation_ref",
            "after observation must identify the after snapshot's NCT ID",
        ),
        (
            before_observation.get("source_snapshot_ref"),
            before_snapshot.get("source_snapshot_id"),
            "$.before_observation_ref",
            "before observation must bind the before source snapshot",
        ),
        (
            after_observation.get("source_snapshot_ref"),
            after_snapshot.get("source_snapshot_id"),
            "$.after_observation_ref",
            "after observation must bind the after source snapshot",
        ),
        (
            before_observation.get("canonical_content_sha256"),
            before_snapshot.get("canonical_content_sha256"),
            "$.before_observation_ref",
            "before observation must bind the before source hash",
        ),
        (
            after_observation.get("canonical_content_sha256"),
            after_snapshot.get("canonical_content_sha256"),
            "$.after_observation_ref",
            "after observation must bind the after source hash",
        ),
        (
            after_observation.get("prior_source_snapshot_ref"),
            before_snapshot.get("source_snapshot_id"),
            "$.after_observation_ref",
            "after observation must identify the prior source snapshot",
        ),
        (
            after_observation.get("prior_canonical_content_sha256"),
            before_snapshot.get("canonical_content_sha256"),
            "$.after_observation_ref",
            "after observation must identify the prior source hash",
        ),
        (
            before_observation.get("retrieved_at"),
            before_snapshot.get("retrieved_at"),
            "$.before_observation_ref",
            "before observation time must match before source retrieval",
        ),
        (
            after_observation.get("retrieved_at"),
            after_snapshot.get("retrieved_at"),
            "$.after_observation_ref",
            "after observation time must match after source retrieval",
        ),
    )
    for actual, expected, path, message in relational_bindings:
        if actual != expected:
            issues.append(
                ValidationIssue(path, "trial_diff.observation_binding", message)
            )

    observed_interval = after_observation.get("observed_interval")
    if isinstance(observed_interval, Mapping):
        if observed_interval.get("after") != before_observation.get("retrieved_at"):
            issues.append(
                ValidationIssue(
                    "$.observed_interval.after",
                    "trial_diff.observation_binding",
                    "diff lower bound must be the prior observation retrieval time",
                )
            )
        if observed_interval.get("at_or_before") != after_observation.get("retrieved_at"):
            issues.append(
                ValidationIssue(
                    "$.observed_interval.at_or_before",
                    "trial_diff.observation_binding",
                    "diff upper bound must be the current observation retrieval time",
                )
            )
    if (
        after_observation.get("source_state_changed") is not True
        or after_observation.get("same_content_as_prior") is not False
    ):
        issues.append(
            ValidationIssue(
                "$.after_observation_ref",
                "trial_diff.observation_binding",
                "a diff requires an observation that records a source-state change",
            )
        )

    diff_transaction = _parse_temporal(diff.get("transaction_from"))
    observation_transaction = _parse_temporal(after_observation.get("transaction_from"))
    if (
        diff_transaction is not None
        and observation_transaction is not None
        and diff_transaction < observation_transaction
    ):
        issues.append(
            ValidationIssue(
                "$.transaction_from",
                "trial_diff.observation_binding",
                "diff transaction time cannot precede its after observation",
            )
        )

    expected_source_records = {
        before_snapshot.get("source_record_ref"),
        after_snapshot.get("source_record_ref"),
    }
    if set(diff.get("source_record_refs", ())) != expected_source_records:
        issues.append(
            ValidationIssue(
                "$.source_record_refs",
                "trial_diff.source_binding",
                "source record references must match both source snapshots",
            )
        )

    expected_operations = exact_json_diff(
        before_snapshot.get("canonical_study"), after_snapshot.get("canonical_study")
    )
    if diff.get("operations") != expected_operations:
        issues.append(
            ValidationIssue(
                "$.operations",
                "trial_diff.exactness",
                "operations do not equal the deterministic diff of the referenced snapshots",
            )
        )
    if issues:
        raise ContractValidationError(_TRIAL_DIFF_CONTRACT_ID, issues)
