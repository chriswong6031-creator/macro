"""Discovery, validation, and hashing for sector-intelligence contracts.

The registry is deliberately fail-closed: only schemas in the two owned
contract directories are discoverable, contract identifiers are the explicit
``properties.contract_id.const`` values, and duplicate identifiers abort the
entire registry build.
"""

from __future__ import annotations

from collections import Counter
import binascii
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import copy
import hashlib
from html import unescape
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
_CTGOV_HISTORY_RECEIPT_CONTRACT_ID = "ctgov_history_receipt.v1"
_CTGOV_HISTORY_RUN_CONTRACT_ID = "ctgov_history_run.v1"
_TRIAL_HISTORY_SOURCE_SNAPSHOT_CONTRACT_ID = "trial_history_source_snapshot.v1"
_TRIAL_HISTORY_DIFF_CONTRACT_ID = "trial_history_exact_diff.v1"
_TRIAL_REGISTRY_CHANGE_FACT_CONTRACT_ID = "trial_registry_change_fact.v1"
_TRIAL_HISTORY_READ_MODEL_CONTRACT_ID = "trial_history_read_model.v1"
_BIOCATALYST_LAUNCH_SLO_MANIFEST_CONTRACT_ID = (
    "biocatalyst_launch_slo_manifest.v1"
)
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


# Draft 2020-12 self-checks cost ~20ms per schema and every registry consumer
# rebuilds a ContractRegistry per document, so byte-identical re-checks are
# remembered for the life of the process. check_schema is a pure function of
# the parsed bytes: files are still re-read and re-parsed on every discovery
# pass (an edited file re-checks under its new digest) and failures are never
# cached.
_CHECKED_SCHEMA_DIGESTS: set[bytes] = set()


def _load_schema(path: Path, root: Path) -> _SchemaRecord:
    shown = _display_path(path, root)
    try:
        raw = path.read_bytes()
        schema = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractRegistryError(f"cannot load schema {shown}: {exc}") from exc
    if not isinstance(schema, dict):
        raise ContractRegistryError(f"schema {shown} must contain a JSON object")
    if schema.get("$schema") not in _DRAFT_2020_12_URIS:
        raise ContractRegistryError(f"schema {shown} must declare JSON Schema Draft 2020-12")

    digest = hashlib.sha256(raw).digest()
    if digest not in _CHECKED_SCHEMA_DIGESTS:
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            raise ContractRegistryError(f"invalid Draft 2020-12 schema {shown}: {exc}") from exc
        _CHECKED_SCHEMA_DIGESTS.add(digest)

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


def _finite_decimal(value: object) -> Decimal | None:
    """Return one finite JSON number without lossy float coercion."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


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


def _interval_issues(
    value: Any,
    path: tuple[object, ...] = (),
    active_container_ids: set[int] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    is_container = isinstance(value, (Mapping, list))
    active = active_container_ids if active_container_ids is not None else set()
    container_id = id(value)
    if is_container and container_id in active:
        return [
            ValidationIssue(
                _json_path(path),
                "schema.cyclic_document",
                "contract documents must be acyclic JSON trees",
            )
        ]
    if is_container:
        active.add(container_id)
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
            issues.extend(_interval_issues(value[key], (*path, key), active))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_interval_issues(item, (*path, index), active))
    if is_container:
        active.remove(container_id)
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


def _biocatalyst_launch_slo_manifest_issues(
    document: Mapping[str, Any], repo_root: Path
) -> list[ValidationIssue]:
    """Validate the immutable launch policy against the canonical source registry.

    This is intentionally a read-only acceptance check.  The manifest can
    describe an eventual soak, but it cannot arm a source, alter rights, or
    convert absent telemetry into a release pass.
    """

    issues: list[ValidationIssue] = []
    hash_payload = {
        key: value
        for key, value in document.items()
        if key not in {"manifest_id", "content_sha256"}
    }
    try:
        actual_content_hash = canonical_json_sha256(hash_payload)
    except ContractError:
        issues.append(
            ValidationIssue(
                "$",
                "launch_slo.canonical_payload",
                "launch SLO manifests must be canonicalizable finite JSON",
            )
        )
        return issues
    declared_content_hash = document.get("content_sha256")
    if (
        isinstance(declared_content_hash, str)
        and declared_content_hash != actual_content_hash
    ):
        issues.append(
            ValidationIssue(
                "$.content_sha256",
                "launch_slo.hash",
                "content_sha256 must bind the canonical manifest payload excluding "
                "manifest_id and content_sha256",
            )
        )

    expected_manifest_id = f"biocatalyst_launch_slo_{actual_content_hash[:24]}"
    manifest_id = document.get("manifest_id")
    if isinstance(manifest_id, str) and manifest_id != expected_manifest_id:
        issues.append(
            ValidationIssue(
                "$.manifest_id",
                "launch_slo.identity",
                f"manifest_id must equal {expected_manifest_id!r}",
            )
        )
    if manifest_id is not None and document.get("supersedes_manifest_id") == manifest_id:
        issues.append(
            ValidationIssue(
                "$.supersedes_manifest_id",
                "launch_slo.self_supersession",
                "a launch SLO manifest cannot supersede itself",
            )
        )
    predecessor_id = document.get("supersedes_manifest_id")
    predecessor_hash = document.get("supersedes_manifest_content_sha256")
    if isinstance(predecessor_id, str) and isinstance(predecessor_hash, str):
        expected_predecessor_id = (
            f"biocatalyst_launch_slo_{predecessor_hash[:24]}"
        )
        if predecessor_id != expected_predecessor_id:
            issues.append(
                ValidationIssue(
                    "$.supersedes_manifest_content_sha256",
                    "launch_slo.predecessor_identity",
                    "the predecessor manifest ID must be derived from its full content SHA-256",
                )
            )

    registry_path = repo_root / "config" / "biocatalyst_sources.yml"
    source_registry: Mapping[str, Any] | None = None
    try:
        registry_bytes = registry_path.read_bytes()
        registry_sha256 = hashlib.sha256(registry_bytes).hexdigest()
        import yaml  # noqa: PLC0415 - only the BioCatalyst policy needs YAML.

        loaded_registry = yaml.safe_load(registry_bytes.decode("utf-8"))
        if isinstance(loaded_registry, Mapping):
            source_registry = loaded_registry
        else:
            raise ValueError("source registry must contain a mapping")
    except Exception as exc:  # noqa: BLE001 - a missing registry is a hard policy issue.
        issues.append(
            ValidationIssue(
                "$.source_registry_ref",
                "launch_slo.source_registry_unavailable",
                f"canonical source registry could not be loaded: {exc}",
            )
        )
        return issues

    if document.get("source_registry_sha256") != registry_sha256:
        issues.append(
            ValidationIssue(
                "$.source_registry_sha256",
                "launch_slo.source_registry_hash",
                "source_registry_sha256 must bind the exact committed registry bytes",
            )
        )

    registered_sources = source_registry.get("sources")
    if not isinstance(registered_sources, Mapping):
        issues.append(
            ValidationIssue(
                "$.source_registry_ref",
                "launch_slo.source_registry_shape",
                "source registry must expose a sources mapping",
            )
        )
        return issues

    launch_critical_ids = {
        str(source_id)
        for source_id, source in registered_sources.items()
        if isinstance(source, Mapping) and source.get("launch_critical") is True
    }
    rows = document.get("sources")
    manifest_rows = rows if isinstance(rows, list) else []
    manifest_ids = [
        str(row.get("source_id"))
        for row in manifest_rows
        if isinstance(row, Mapping) and isinstance(row.get("source_id"), str)
    ]
    duplicate_ids = sorted(
        source_id for source_id, count in Counter(manifest_ids).items() if count > 1
    )
    if duplicate_ids:
        issues.append(
            ValidationIssue(
                "$.sources",
                "launch_slo.duplicate_source",
                "source rows must be unique: " + ", ".join(duplicate_ids),
            )
        )
    actual_ids = set(manifest_ids)
    omitted = sorted(launch_critical_ids - actual_ids)
    unknown_or_noncritical = sorted(actual_ids - launch_critical_ids)
    if omitted:
        issues.append(
            ValidationIssue(
                "$.sources",
                "launch_slo.omitted_source",
                "every launch-critical source must appear exactly once: "
                + ", ".join(omitted),
            )
        )
    if unknown_or_noncritical:
        issues.append(
            ValidationIssue(
                "$.sources",
                "launch_slo.unknown_source",
                "manifest contains unknown or non-launch-critical sources: "
                + ", ".join(unknown_or_noncritical),
            )
        )

    required_telemetry = {
        "opportunity",
        "attempt",
        "fetch",
        "parse",
        "contract_validation",
        "completeness",
        "publication",
        "watermark_or_pointer",
        "freshness",
        "upstream_unavailable",
    }
    policies_by_source: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(manifest_rows):
        if not isinstance(row, Mapping):
            continue
        source_id = row.get("source_id")
        if not isinstance(source_id, str):
            continue
        policies_by_source[source_id] = row
        source = registered_sources.get(source_id)
        if not isinstance(source, Mapping):
            continue
        binding = row.get("registry_binding")
        if not isinstance(binding, Mapping):
            continue
        expected_bindings = {
            "launch_critical": source.get("launch_critical"),
            "production_ingest_allowed": source.get("production_ingest_allowed"),
            "collection_target": source.get("collection_target"),
            "opportunity_semantics": source.get("opportunity_semantics"),
            "completeness_semantics": source.get("completeness_semantics"),
            "freshness_slo_seconds": source.get("freshness_slo_seconds"),
            "maximum_consecutive_misses": source.get("maximum_consecutive_misses"),
        }
        for field, expected in expected_bindings.items():
            if binding.get(field) != expected:
                issues.append(
                    ValidationIssue(
                        f"$.sources[{index}].registry_binding.{field}",
                        "launch_slo.registry_mismatch",
                        f"must exactly match source registry value {expected!r}",
                    )
                )
        if row.get("owner") != source.get("owner"):
            issues.append(
                ValidationIssue(
                    f"$.sources[{index}].owner",
                    "launch_slo.owner_mismatch",
                    "source owner must exactly match the source registry",
                )
            )

        freshness = row.get("freshness")
        if (
            isinstance(freshness, Mapping)
            and freshness.get("maximum_seconds") != source.get("freshness_slo_seconds")
        ):
            issues.append(
                ValidationIssue(
                    f"$.sources[{index}].freshness.maximum_seconds",
                    "launch_slo.freshness_mismatch",
                    "freshness ceiling must equal the registered source SLO",
                )
            )
        opportunity = row.get("opportunity_rule")
        if isinstance(opportunity, Mapping):
            opened = opportunity.get("window_open_offset_seconds")
            closed = opportunity.get("window_close_offset_seconds")
            cadence = opportunity.get("cadence_seconds")
            if all(isinstance(value, int) and not isinstance(value, bool) for value in (opened, closed, cadence)):
                if not (0 <= opened < closed <= cadence):
                    issues.append(
                        ValidationIssue(
                            f"$.sources[{index}].opportunity_rule",
                            "launch_slo.opportunity_window",
                            "UTC opportunity offsets must satisfy 0 <= open < close <= cadence",
                        )
                    )
        telemetry = row.get("required_telemetry_streams")
        if (
            isinstance(telemetry, list)
            and all(isinstance(stream, str) for stream in telemetry)
            and set(telemetry) != required_telemetry
        ):
            issues.append(
                ValidationIssue(
                    f"$.sources[{index}].required_telemetry_streams",
                    "launch_slo.telemetry",
                    "all opportunity, stage, freshness, and upstream-outage streams are required",
                )
            )
        budget = row.get("error_budget")
        if isinstance(budget, Mapping):
            success_ratio = budget.get("minimum_opportunity_success_ratio")
            error_fraction = budget.get("maximum_error_budget_fraction")
            success_decimal = _finite_decimal(success_ratio)
            error_decimal = _finite_decimal(error_fraction)
            if (
                success_decimal is not None
                and error_decimal is not None
                and abs(success_decimal + error_decimal - Decimal("1"))
                > Decimal("1e-12")
            ):
                issues.append(
                    ValidationIssue(
                        f"$.sources[{index}].error_budget",
                        "launch_slo.error_budget",
                        "minimum success ratio and maximum error fraction must sum to 1",
                    )
                )

    state = document.get("state")
    soak = document.get("soak")
    if isinstance(soak, Mapping):
        raw_start = soak.get("window_start")
        raw_end = soak.get("window_end")
        start = _parse_temporal(raw_start)
        end = _parse_temporal(raw_end)
        window_states = {
            "soak_scheduled",
            "soak_complete_passed",
            "soak_complete_failed",
        }
        window_valid = bool(
            isinstance(raw_start, str)
            and isinstance(raw_end, str)
            and raw_start.endswith("Z")
            and raw_end.endswith("Z")
            and start is not None
            and end is not None
            and end - start == timedelta(days=14)
        )
        if state in window_states and not window_valid:
            issues.append(
                ValidationIssue(
                    "$.soak",
                    "launch_slo.soak_window",
                    "scheduled and completed soaks require canonical-Z bounds for one exact fourteen-day UTC window",
                )
            )
        if state in window_states:
            effective = _parse_temporal(document.get("effective_at"))
            if effective is not None and start is not None and effective > start:
                issues.append(
                    ValidationIssue(
                        "$.effective_at",
                        "launch_slo.effective_after_start",
                        "the frozen manifest must become effective no later than its soak start",
                    )
                )
            blockers = soak.get("scheduling_blockers")
            if isinstance(blockers, list) and blockers:
                issues.append(
                    ValidationIssue(
                        "$.soak.scheduling_blockers",
                        "launch_slo.active_soak_blockers",
                        "scheduled and completed soaks cannot retain unresolved scheduling blockers",
                    )
                )
        if state == "pre_soak_unarmed":
            if not soak.get("scheduling_blockers"):
                issues.append(
                    ValidationIssue(
                        "$.soak.scheduling_blockers",
                        "launch_slo.pre_soak_blockers",
                        "an unarmed pre-soak manifest must state why the window is not scheduled",
                    )
                )
            for index, row in enumerate(manifest_rows):
                if isinstance(row, Mapping) and row.get("activation_state") != "dark_unarmed":
                    issues.append(
                        ValidationIssue(
                            f"$.sources[{index}].activation_state",
                            "launch_slo.pre_soak_activation",
                            "pre-soak source rows must remain dark and unarmed",
                        )
                    )
        if state == "soak_complete_passed":
            for index, row in enumerate(manifest_rows):
                if isinstance(row, Mapping) and row.get("activation_state") != "armed":
                    issues.append(
                        ValidationIssue(
                            f"$.sources[{index}].activation_state",
                            "launch_slo.passed_soak_activation",
                            "a claimed completed pass requires every source row to have been armed",
                        )
                    )

        artifact_slots: tuple[tuple[str, object, str], ...] = (
            (
                "$.soak.telemetry_generation_ref",
                soak.get("telemetry_generation_ref"),
                "telemetry_generation",
            ),
            (
                "$.soak.ci_validation_receipt_ref",
                soak.get("ci_validation_receipt_ref"),
                "ci_validation",
            ),
        )
        artifact_lists: tuple[tuple[str, object, str], ...] = (
            (
                "$.soak.raw_telemetry_refs",
                soak.get("raw_telemetry_refs"),
                "raw_telemetry",
            ),
            (
                "$.soak.correction_replay_evidence_refs",
                soak.get("correction_replay_evidence_refs"),
                "correction_replay",
            ),
            (
                "$.soak.rollback_restore_evidence_refs",
                soak.get("rollback_restore_evidence_refs"),
                "rollback_restore",
            ),
        )
        artifacts: list[tuple[str, Mapping[str, Any], str]] = []
        for path, candidate, expected_kind in artifact_slots:
            if isinstance(candidate, Mapping):
                artifacts.append((path, candidate, expected_kind))
        for path, candidates, expected_kind in artifact_lists:
            if not isinstance(candidates, list):
                continue
            artifacts.extend(
                (f"{path}[{index}]", candidate, expected_kind)
                for index, candidate in enumerate(candidates)
                if isinstance(candidate, Mapping)
            )
        artifact_digest_paths: dict[str, str] = {}
        for path, artifact, expected_kind in artifacts:
            digest = artifact.get("content_sha256")
            artifact_id = artifact.get("artifact_id")
            object_ref = artifact.get("object_ref")
            if artifact.get("kind") != expected_kind:
                issues.append(
                    ValidationIssue(
                        f"{path}.kind",
                        "launch_slo.artifact_kind",
                        f"this evidence slot requires kind {expected_kind!r}",
                    )
                )
            if (
                artifact.get("scheduled_manifest_id") != predecessor_id
                or artifact.get("scheduled_manifest_content_sha256")
                != predecessor_hash
            ):
                issues.append(
                    ValidationIssue(
                        path,
                        "launch_slo.artifact_manifest_binding",
                        "every evidence artifact must bind the exact scheduled predecessor ID and full digest",
                    )
                )
            if (
                artifact.get("window_start") != raw_start
                or artifact.get("window_end") != raw_end
            ):
                issues.append(
                    ValidationIssue(
                        path,
                        "launch_slo.artifact_window_binding",
                        "every evidence artifact must bind the exact frozen soak window",
                    )
                )
            artifact_source_id = artifact.get("source_id")
            if (
                artifact_source_id is not None
                and artifact_source_id not in launch_critical_ids
            ):
                issues.append(
                    ValidationIssue(
                        f"{path}.source_id",
                        "launch_slo.artifact_source_binding",
                        "artifact source_id must be null for aggregate evidence or one launch-critical source",
                    )
                )
            if (
                isinstance(digest, str)
                and artifact_id != f"biocatalyst_artifact_{digest[:24]}"
            ):
                issues.append(
                    ValidationIssue(
                        f"{path}.artifact_id",
                        "launch_slo.artifact_identity",
                        "artifact_id must be derived from the declared content SHA-256",
                    )
                )
            if (
                isinstance(digest, str)
                and isinstance(object_ref, str)
                and digest not in object_ref
            ):
                issues.append(
                    ValidationIssue(
                        f"{path}.object_ref",
                        "launch_slo.artifact_object_ref",
                        "the immutable object reference must contain the full content SHA-256",
                    )
                )
            if isinstance(digest, str):
                prior_path = artifact_digest_paths.get(digest)
                if prior_path is not None:
                    issues.append(
                        ValidationIssue(
                            f"{path}.content_sha256",
                            "launch_slo.artifact_role_reuse",
                            f"evidence roles must bind distinct artifacts; digest already appears at {prior_path}",
                        )
                    )
                else:
                    artifact_digest_paths[digest] = path

        scheduled_opportunities: dict[str, int] = {}
        if window_valid and start is not None and end is not None:
            epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
            start_delta = start - epoch
            start_microseconds = (
                (start_delta.days * 86400 + start_delta.seconds) * 1_000_000
                + start_delta.microseconds
            )
            duration = end - start
            duration_seconds = duration.days * 86400 + duration.seconds
            for index, row in enumerate(manifest_rows):
                if not isinstance(row, Mapping) or not isinstance(row.get("source_id"), str):
                    continue
                opportunity = row.get("opportunity_rule")
                cadence = (
                    opportunity.get("cadence_seconds")
                    if isinstance(opportunity, Mapping)
                    else None
                )
                if not isinstance(cadence, int) or isinstance(cadence, bool) or cadence <= 0:
                    continue
                if (
                    start_microseconds % (cadence * 1_000_000) != 0
                    or duration_seconds % cadence != 0
                ):
                    issues.append(
                        ValidationIssue(
                            f"$.sources[{index}].opportunity_rule.cadence_seconds",
                            "launch_slo.schedule_alignment",
                            "the UTC soak bounds must align exactly to every source cadence",
                        )
                    )
                    continue
                scheduled_opportunities[row["source_id"]] = duration_seconds // cadence

        results = soak.get("source_results")
        source_results = results if isinstance(results, list) else []
        if state in {"soak_complete_passed", "soak_complete_failed"}:
            result_ids = {
                str(result.get("source_id"))
                for result in source_results
                if isinstance(result, Mapping)
            }
            if result_ids != launch_critical_ids or len(source_results) != len(result_ids):
                issues.append(
                    ValidationIssue(
                        "$.soak.source_results",
                        "launch_slo.result_source_set",
                        "completed soak results must cover every launch-critical source exactly once",
                    )
                )

        stage_names = (
            "fetch",
            "parse",
            "contract_validation",
            "completeness_reconciliation",
            "publication",
            "watermark_or_pointer",
        )
        computed_passes: list[bool] = []
        for index, result in enumerate(source_results):
            if not isinstance(result, Mapping):
                continue
            source_id = result.get("source_id")
            policy = policies_by_source.get(str(source_id))
            if policy is None:
                continue
            expected = result.get("expected_opportunities")
            maintenance = result.get("excluded_predeclared_maintenance")
            nonpublication = result.get("excluded_source_native_nonpublication")
            denominator = result.get("denominator")
            successful = result.get("successful_opportunities")
            misses = result.get("misses")
            integer_values = (
                expected,
                maintenance,
                nonpublication,
                denominator,
                successful,
                misses,
            )
            integers_valid = all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in integer_values
            )
            expected_from_schedule = scheduled_opportunities.get(str(source_id))
            schedule_matches = bool(
                isinstance(expected, int)
                and not isinstance(expected, bool)
                and expected_from_schedule is not None
                and expected == expected_from_schedule
            )
            if expected_from_schedule is not None and expected != expected_from_schedule:
                issues.append(
                    ValidationIssue(
                        f"$.soak.source_results[{index}].expected_opportunities",
                        "launch_slo.expected_opportunities",
                        f"expected opportunities must be derived from the frozen UTC schedule ({expected_from_schedule})",
                    )
                )

            denominator_policy = policy.get("denominator_policy")
            maintenance_supported = maintenance == 0
            if isinstance(maintenance, int) and not isinstance(maintenance, bool) and maintenance:
                issues.append(
                    ValidationIssue(
                        f"$.soak.source_results[{index}].excluded_predeclared_maintenance",
                        "launch_slo.maintenance_exclusion_unverifiable",
                        "v1 has no structured interval ledger, so maintenance exclusions must remain zero",
                    )
                )
            nonpublication_supported = nonpublication == 0
            treatment = (
                denominator_policy.get("source_nonpublication_treatment")
                if isinstance(denominator_policy, Mapping)
                else None
            )
            if (
                isinstance(nonpublication, int)
                and not isinstance(nonpublication, bool)
                and nonpublication
            ):
                code = (
                    "launch_slo.nonpublication_must_remain_in_denominator"
                    if treatment
                    == "retain_in_denominator_fetch_and_validate_unchanged_state"
                    else "launch_slo.nonpublication_exclusion_unverifiable"
                )
                issues.append(
                    ValidationIssue(
                        f"$.soak.source_results[{index}].excluded_source_native_nonpublication",
                        code,
                        "source-native nonpublication cannot leave the denominator without a structured predeclared evidence ledger",
                    )
                )

            reconciliation_matches = False
            if integers_valid:
                expected_denominator = expected - maintenance - nonpublication
                reconciliation_matches = bool(
                    denominator == expected_denominator
                    and successful + misses == denominator
                )
                if not reconciliation_matches:
                    issues.append(
                        ValidationIssue(
                            f"$.soak.source_results[{index}].denominator",
                            "launch_slo.denominator",
                            "denominator must equal schedule-derived opportunities minus only eligible exclusions, and successes plus misses must reconcile",
                        )
                    )

            upstream_unavailable = result.get("upstream_unavailable_observations")
            if (
                isinstance(upstream_unavailable, int)
                and not isinstance(upstream_unavailable, bool)
                and isinstance(misses, int)
                and not isinstance(misses, bool)
                and upstream_unavailable > misses
            ):
                issues.append(
                    ValidationIssue(
                        f"$.soak.source_results[{index}].upstream_unavailable_observations",
                        "launch_slo.upstream_outage",
                        "upstream-unavailable observations are denominator misses, never exclusions",
                    )
                )

            stage_successes = result.get("stage_successes")
            stage_counts_valid = isinstance(stage_successes, Mapping)
            if isinstance(stage_successes, Mapping):
                for stage in stage_names:
                    count = stage_successes.get(stage)
                    valid_count = isinstance(count, int) and not isinstance(count, bool)
                    stage_counts_valid = stage_counts_valid and valid_count
                    if (
                        valid_count
                        and isinstance(successful, int)
                        and not isinstance(successful, bool)
                        and count != successful
                    ):
                        stage_counts_valid = False
                        issues.append(
                            ValidationIssue(
                                f"$.soak.source_results[{index}].stage_successes.{stage}",
                                "launch_slo.stage_reconciliation",
                                "every required stage success count must reconcile to the end-to-end successful opportunities",
                            )
                        )
                    if (
                        valid_count
                        and isinstance(denominator, int)
                        and not isinstance(denominator, bool)
                        and count > denominator
                    ):
                        stage_counts_valid = False
                        issues.append(
                            ValidationIssue(
                                f"$.soak.source_results[{index}].stage_successes.{stage}",
                                "launch_slo.stage_denominator",
                                "a stage success count cannot exceed the opportunity denominator",
                            )
                        )

            max_misses_observed = result.get("maximum_consecutive_misses_observed")
            miss_run_valid = bool(
                isinstance(max_misses_observed, int)
                and not isinstance(max_misses_observed, bool)
                and isinstance(misses, int)
                and not isinstance(misses, bool)
                and (
                    (misses == 0 and max_misses_observed == 0)
                    or (misses > 0 and 1 <= max_misses_observed <= misses)
                )
            )
            if (
                isinstance(max_misses_observed, int)
                and not isinstance(max_misses_observed, bool)
                and isinstance(misses, int)
                and not isinstance(misses, bool)
                and not miss_run_valid
            ):
                issues.append(
                    ValidationIssue(
                        f"$.soak.source_results[{index}].maximum_consecutive_misses_observed",
                        "launch_slo.consecutive_misses",
                        "maximum consecutive misses must reconcile with the total miss count",
                    )
                )

            budget = policy.get("error_budget")
            freshness_policy = policy.get("freshness")
            completeness_policy = policy.get("completeness")
            registry_binding = policy.get("registry_binding")
            threshold = (
                _finite_decimal(budget.get("minimum_opportunity_success_ratio"))
                if isinstance(budget, Mapping)
                else None
            )
            ratio = (
                Decimal(successful) / Decimal(denominator)
                if isinstance(successful, int)
                and not isinstance(successful, bool)
                and isinstance(denominator, int)
                and not isinstance(denominator, bool)
                and denominator > 0
                else None
            )
            freshness_observed = _finite_decimal(result.get("freshness_p95_seconds"))
            freshness_limit = (
                _finite_decimal(freshness_policy.get("maximum_seconds"))
                if isinstance(freshness_policy, Mapping)
                else None
            )
            completeness_observed = _finite_decimal(
                result.get("minimum_completeness_ratio_observed")
            )
            prior_scope_observed = _finite_decimal(
                result.get("minimum_vs_prior_scope_ratio_observed")
            )
            completeness_limit = (
                _finite_decimal(completeness_policy.get("minimum_ratio"))
                if isinstance(completeness_policy, Mapping)
                else None
            )
            prior_scope_limit = (
                _finite_decimal(
                    completeness_policy.get("minimum_vs_prior_scope_ratio")
                )
                if isinstance(completeness_policy, Mapping)
                else None
            )
            maximum_misses = (
                registry_binding.get("maximum_consecutive_misses")
                if isinstance(registry_binding, Mapping)
                else None
            )
            critical_failures = result.get("critical_failure_types")
            computed_pass = bool(
                schedule_matches
                and maintenance_supported
                and nonpublication_supported
                and reconciliation_matches
                and stage_counts_valid
                and ratio is not None
                and threshold is not None
                and ratio >= threshold
                and miss_run_valid
                and isinstance(maximum_misses, int)
                and not isinstance(maximum_misses, bool)
                and isinstance(max_misses_observed, int)
                and max_misses_observed <= maximum_misses
                and freshness_observed is not None
                and freshness_limit is not None
                and freshness_observed <= freshness_limit
                and completeness_observed is not None
                and completeness_limit is not None
                and completeness_observed >= completeness_limit
                and prior_scope_observed is not None
                and prior_scope_limit is not None
                and prior_scope_observed >= prior_scope_limit
                and isinstance(critical_failures, list)
                and not critical_failures
            )
            computed_passes.append(computed_pass)
            if result.get("passed") is not computed_pass:
                issues.append(
                    ValidationIssue(
                        f"$.soak.source_results[{index}].passed",
                        "launch_slo.source_pass",
                        "declared source pass must equal the frozen schedule, every stage gate, thresholds, and unconditional-failure policy",
                    )
                )

        if source_results:
            aggregate_pass = bool(computed_passes) and all(computed_passes)
            if soak.get("aggregate_passed") is not aggregate_pass:
                issues.append(
                    ValidationIssue(
                        "$.soak.aggregate_passed",
                        "launch_slo.aggregate_pass",
                        "aggregate pass is true only when every launch-critical source passes",
                    )
                )
        if state == "soak_complete_passed":
            if not soak.get("aggregate_passed"):
                issues.append(
                    ValidationIssue(
                        "$.state",
                        "launch_slo.false_release_pass",
                        "soak_complete_passed requires an all-source pass",
                    )
                )
        claimed_source_pass = any(
            isinstance(result, Mapping) and result.get("passed") is True
            for result in source_results
        )
        if soak.get("aggregate_passed") is True or claimed_source_pass:
            issues.append(
                ValidationIssue(
                    "$.soak.aggregate_passed",
                    "launch_slo.trusted_evidence_verifier_unavailable",
                    "no lifecycle label can carry a pass until BC-O2 resolves content-addressed telemetry and recovery artifacts and recomputes every result",
                )
            )
    return issues


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
    version_evidence = document.get("version_evidence")
    # B0 fixtures intentionally predate immutable /version receipts.  Keep the
    # contract parseable for historical/replay fixtures, but when B1 evidence is
    # present bind both probes to the exact run state and to one ordered content
    # hash.  The live worker additionally requires this object and verifies the
    # referenced raw bytes before it can mirror or advance a pointer.
    if version_evidence is not None and isinstance(version_evidence, Mapping):
        before = version_evidence.get("before")
        after = version_evidence.get("after")
        if isinstance(before, Mapping) and isinstance(after, Mapping):
            expected_hash = version_receipt_payloads_sha256((before, after))
            if version_evidence.get("version_receipt_payloads_sha256") != expected_hash:
                issues.append(
                    ValidationIssue(
                        "$.version_evidence.version_receipt_payloads_sha256",
                        "fetch_run.version_receipt_hash",
                        "version-receipt payload hash must bind the ordered before/after receipts",
                    )
                )
            for phase, receipt in (("before", before), ("after", after)):
                prefix = f"$.version_evidence.{phase}"
                if receipt.get("phase") != phase:
                    issues.append(
                        ValidationIssue(
                            f"{prefix}.phase",
                            "fetch_run.version_receipt_binding",
                            "version receipt phase must match its before/after slot",
                        )
                    )
                if receipt.get("run_id") != document.get("run_id") or receipt.get("source_id") != document.get("source_id"):
                    issues.append(
                        ValidationIssue(
                            prefix,
                            "fetch_run.version_receipt_binding",
                            "version receipt must bind to the enclosing fetch run and source",
                        )
                    )
                expected_timestamp = document.get(
                    "source_dataset_timestamp_before_raw"
                    if phase == "before"
                    else "source_dataset_timestamp_after_raw"
                )
                if receipt.get("source_dataset_timestamp_raw") != expected_timestamp:
                    issues.append(
                        ValidationIssue(
                            f"{prefix}.source_dataset_timestamp_raw",
                            "fetch_run.source_version_binding",
                            "version receipt timestamp must match the stable run timestamp",
                        )
                    )
                expected_api_version = document.get("source_api_version")
                if phase == "after" and "source_api_version_after" in document:
                    expected_api_version = document.get("source_api_version_after")
                if receipt.get("source_api_version") != expected_api_version:
                    issues.append(
                        ValidationIssue(
                            f"{prefix}.source_api_version",
                            "fetch_run.source_version_binding",
                            "version receipt API version must match the fetch run",
                        )
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
        base_query_params = manifest.get("base_query_params")
        wire_keys = ("api_root", "request_path", "base_query_params")
        present_wire_keys = [key for key in wire_keys if key in manifest]
        if present_wire_keys and len(present_wire_keys) != len(wire_keys):
            issues.append(
                ValidationIssue(
                    "$.query_manifest",
                    "fetch_run.query_wire_binding",
                    "API root, request path, and base query parameters must appear together",
                )
            )
        if isinstance(base_query_params, Mapping) and isinstance(configured_ids, list):
            expected_params = {
                "query.id": ",".join(configured_ids),
                "format": "json",
                "pageSize": str(manifest.get("page_size")),
                "countTotal": "true",
            }
            if dict(base_query_params) != expected_params:
                issues.append(
                    ValidationIssue(
                        "$.query_manifest.base_query_params",
                        "fetch_run.query_wire_binding",
                        "base query parameters must be derived from configured IDs and page size",
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


_FDA_DATA_PAGE_URL = "https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files"
_FDA_ARCHIVE_URL = "https://www.fda.gov/media/89850/download?attachment="
_FDA_APPLICATION_TABLES = ("Applications.txt",)
_FDA_SUBMISSION_TABLES = (
    "Submissions.txt",
    "SubmissionClass_Lookup.txt",
    "SubmissionPropertyType.txt",
)
_FDA_EVENT_TABLES = (
    "Join_Submission_ActionTypes_Lookup.txt",
    "ActionTypes_Lookup.txt",
)
_FDA_DOSSIER_TABLES = (
    "Applications.txt",
    "Products.txt",
    "Submissions.txt",
    "Join_Submission_ActionTypes_Lookup.txt",
    "ActionTypes_Lookup.txt",
    "ApplicationDocs.txt",
    "MarketingStatus.txt",
    "MarketingStatus_Lookup.txt",
    "TE.txt",
    "SubmissionClass_Lookup.txt",
    "SubmissionPropertyType.txt",
    "ApplicationsDocsType_Lookup.txt",
)
_FDA_EVIDENCE_RELEASE_FIELDS = (
    "source_id",
    "release_id",
    "archive_sha256",
    "source_release_date",
    "source_release_time",
    "source_url",
    "observed_at",
    "parser_version",
    "source_schema_version",
    "license_class",
)


def _reviewed_fda_https_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and hostname in {"www.fda.gov", "www.accessdata.fda.gov"}
        and parsed.username is None
        and parsed.password is None
        and port in {None, 443}
        and not parsed.fragment
    )


def _fda_evidence_issues(
    evidence: Any, *, path: str, expected_tables: Sequence[str]
) -> list[ValidationIssue]:
    if not isinstance(evidence, Mapping):
        return []
    issues: list[ValidationIssue] = []
    archive = evidence.get("archive_sha256")
    expected_release = f"drugs_at_fda_release_{str(archive)[:24]}"
    if evidence.get("release_id") != expected_release:
        issues.append(ValidationIssue(path + ".release_id", "drugs_fda.evidence_release", "source evidence release ID must be derived from its archive SHA-256"))
    if evidence.get("source_url") != _FDA_DATA_PAGE_URL:
        issues.append(ValidationIssue(path + ".source_url", "drugs_fda.evidence_source", "source evidence must identify the reviewed official FDA data page"))
    manifest_ids = evidence.get("table_manifest_ids")
    expected_manifest_ids = [
        f"drugs_at_fda_table_{canonical_json_sha256({'archive': archive, 'table': table})[:24]}"
        for table in expected_tables
    ]
    if manifest_ids != expected_manifest_ids:
        issues.append(ValidationIssue(path + ".table_manifest_ids", "drugs_fda.evidence_manifests", "source evidence manifest IDs must exactly bind the required ordered table set"))
    return issues


def _fda_hash_and_id_issues(
    document: Mapping[str, Any], *, hash_field: str, id_field: str, prefix: str,
    identity: Mapping[str, Any], expected_tables: Sequence[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    expected_hash = canonical_json_sha256({key: value for key, value in document.items() if key != hash_field})
    if document.get(hash_field) != expected_hash:
        issues.append(ValidationIssue(f"$.{hash_field}", "drugs_fda.payload_hash", "payload hash does not bind canonical payload"))
    expected_id = f"{prefix}_{canonical_json_sha256(identity)[:24]}"
    if document.get(id_field) != expected_id:
        issues.append(ValidationIssue(f"$.{id_field}", "drugs_fda.derived_id", "ID must be derived from source-native identity and archive SHA-256"))
    issues.extend(_fda_evidence_issues(
        document.get("source_evidence"),
        path="$.source_evidence",
        expected_tables=expected_tables,
    ))
    return issues


def _fda_application_snapshot_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    evidence = document.get("source_evidence")
    archive = evidence.get("archive_sha256") if isinstance(evidence, Mapping) else None
    return _fda_hash_and_id_issues(
        document,
        hash_field="snapshot_payload_sha256", id_field="application_snapshot_id", prefix="fda_application",
        identity={"release": archive, "appl_no": document.get("application_number")},
        expected_tables=_FDA_APPLICATION_TABLES,
    )


def _fda_submission_observation_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    evidence = document.get("source_evidence")
    archive = evidence.get("archive_sha256") if isinstance(evidence, Mapping) else None
    issues = _fda_hash_and_id_issues(
        document,
        hash_field="observation_payload_sha256", id_field="submission_observation_id", prefix="fda_submission",
        identity={
            "release": archive, "appl_no": document.get("application_number"),
            "submission_type": str(document.get("submission_type_source_text", "")).rstrip(" "),
            "submission_no": document.get("submission_number"),
        },
        expected_tables=_FDA_SUBMISSION_TABLES,
    )
    expected_application_id = f"fda_application_{canonical_json_sha256({'release': archive, 'appl_no': document.get('application_number')})[:24]}"
    application_id = document.get("application_snapshot_id")
    orphan = document.get("source_native_orphan")
    if application_id is None:
        if orphan is not True:
            issues.append(ValidationIssue("$.source_native_orphan", "drugs_fda.submission_parent", "submission without an application snapshot must be source-native orphan"))
    elif application_id != expected_application_id or orphan is not False:
        issues.append(ValidationIssue("$.application_snapshot_id", "drugs_fda.submission_parent", "non-orphan submission must bind the deterministic application snapshot for this release"))
    return issues


def _fda_regulatory_event_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    evidence = document.get("source_evidence")
    archive = evidence.get("archive_sha256") if isinstance(evidence, Mapping) else None
    issues = _fda_hash_and_id_issues(
        document,
        hash_field="event_payload_sha256", id_field="regulatory_event_id", prefix="fda_submission_action",
        identity={"release": archive, "join_id": document.get("submission_action_join_id")},
        expected_tables=_FDA_EVENT_TABLES,
    )
    action_id = document.get("action_type_lookup_id")
    action_description = document.get("action_type_description_source_text")
    if action_id is None and action_description is not None:
        issues.append(ValidationIssue("$.action_type_description_source_text", "drugs_fda.event_action_parent", "event without an action lookup ID cannot carry an action description"))
    expected_orphan = (
        document.get("submission_observation_id") is None
        or action_description is None
    )
    if document.get("source_native_orphan") is not expected_orphan:
        issues.append(ValidationIssue("$.source_native_orphan", "drugs_fda.event_parent", "event orphan status must reflect missing submission or action-lookup evidence"))
    return issues


def _fda_nested_release_binding_issues(
    parent_evidence: Any, child_evidence: Any, *, path: str
) -> list[ValidationIssue]:
    if not isinstance(parent_evidence, Mapping) or not isinstance(child_evidence, Mapping):
        return []
    return [
        ValidationIssue(
            f"{path}.{field}",
            "drugs_fda.dossier_release_binding",
            "nested evidence must exactly bind the dossier release observation",
        )
        for field in _FDA_EVIDENCE_RELEASE_FIELDS
        if child_evidence.get(field) != parent_evidence.get(field)
    ]


def _fda_application_dossier_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    evidence = document.get("source_evidence")
    archive = evidence.get("archive_sha256") if isinstance(evidence, Mapping) else None
    application = document.get("application_snapshot")
    application_number = application.get("application_number") if isinstance(application, Mapping) else None
    issues = _fda_hash_and_id_issues(
        document,
        hash_field="dossier_payload_sha256", id_field="dossier_id", prefix="fda_dossier",
        identity={"release": archive, "appl_no": application_number},
        expected_tables=_FDA_DOSSIER_TABLES,
    )
    if isinstance(application, Mapping):
        issues.extend(_fda_application_snapshot_issues(application))
        issues.extend(_fda_nested_release_binding_issues(
            evidence,
            application.get("source_evidence"),
            path="$.application_snapshot.source_evidence",
        ))
    application_snapshot_id = application.get("application_snapshot_id") if isinstance(application, Mapping) else None
    submission_ids: set[str] = set()
    submission_keys: set[tuple[str, str]] = set()
    event_ids: set[str] = set()
    for index, submission in enumerate(document.get("submissions", [])):
        if isinstance(submission, Mapping):
            issues.extend(_fda_submission_observation_issues(submission))
            if submission.get("application_number") != application_number:
                issues.append(ValidationIssue(f"$.submissions[{index}].application_number", "drugs_fda.dossier_application", "nested submission must match dossier application"))
            issues.extend(_fda_nested_release_binding_issues(
                evidence,
                submission.get("source_evidence"),
                path=f"$.submissions[{index}].source_evidence",
            ))
            submission_id = submission.get("submission_observation_id")
            if isinstance(submission_id, str):
                if submission_id in submission_ids:
                    issues.append(ValidationIssue(f"$.submissions[{index}].submission_observation_id", "drugs_fda.dossier_duplicate", "dossier submission IDs must be unique"))
                submission_ids.add(submission_id)
            submission_keys.add((
                str(submission.get("submission_type_source_text", "")).rstrip(" "),
                str(submission.get("submission_number", "")),
            ))
            property_ids: set[str] = set()
            for property_index, property_fact in enumerate(submission.get("submission_properties", [])):
                if isinstance(property_fact, Mapping):
                    property_id = str(property_fact.get("property_type_id", ""))
                    if property_id in property_ids:
                        issues.append(ValidationIssue(f"$.submissions[{index}].submission_properties[{property_index}].property_type_id", "drugs_fda.dossier_duplicate", "submission property IDs must be unique within a submission"))
                    property_ids.add(property_id)
            if submission.get("application_snapshot_id") != application_snapshot_id or submission.get("source_native_orphan") is True:
                issues.append(ValidationIssue(f"$.submissions[{index}].application_snapshot_id", "drugs_fda.dossier_submission_parent", "dossier submission must bind its application snapshot and cannot be an application orphan"))
    for index, event in enumerate(document.get("submission_action_events", [])):
        if isinstance(event, Mapping):
            issues.extend(_fda_regulatory_event_issues(event))
            event_id = event.get("regulatory_event_id")
            if isinstance(event_id, str):
                if event_id in event_ids:
                    issues.append(ValidationIssue(f"$.submission_action_events[{index}].regulatory_event_id", "drugs_fda.dossier_duplicate", "dossier regulatory event IDs must be unique"))
                event_ids.add(event_id)
            if event.get("application_number") != application_number:
                issues.append(ValidationIssue(f"$.submission_action_events[{index}].application_number", "drugs_fda.dossier_application", "nested event must match dossier application"))
            issues.extend(_fda_nested_release_binding_issues(
                evidence,
                event.get("source_evidence"),
                path=f"$.submission_action_events[{index}].source_evidence",
            ))
            submission_id = event.get("submission_observation_id")
            if submission_id is None and event.get("source_native_orphan") is not True:
                issues.append(ValidationIssue(f"$.submission_action_events[{index}].source_native_orphan", "drugs_fda.event_parent", "event without a submission parent must be source-native orphan"))
            if submission_id is not None and submission_id not in submission_ids:
                issues.append(ValidationIssue(f"$.submission_action_events[{index}].submission_observation_id", "drugs_fda.event_parent", "event submission parent must be included in the dossier"))
    product_numbers: set[str] = set()
    for product_index, product in enumerate(document.get("products", [])):
        if not isinstance(product, Mapping):
            continue
        product_number = str(product.get("product_number", ""))
        if product_number in product_numbers:
            issues.append(ValidationIssue(f"$.products[{product_index}].product_number", "drugs_fda.dossier_duplicate", "product numbers must be unique within an application dossier"))
        product_numbers.add(product_number)
        marketing_ids: set[str] = set()
        for status_index, status in enumerate(product.get("marketing_statuses", [])):
            if not isinstance(status, Mapping):
                continue
            status_id = str(status.get("marketing_status_id", ""))
            if status_id in marketing_ids:
                issues.append(ValidationIssue(f"$.products[{product_index}].marketing_statuses[{status_index}].marketing_status_id", "drugs_fda.dossier_duplicate", "marketing status IDs must be unique within a product"))
            marketing_ids.add(status_id)
            expected_orphan = status.get("marketing_status_description_source_text") is None
            if status.get("source_native_orphan") is not expected_orphan:
                issues.append(ValidationIssue(f"$.products[{product_index}].marketing_statuses[{status_index}].source_native_orphan", "drugs_fda.marketing_parent", "marketing status orphan state must reflect missing lookup evidence"))
    document_ids: set[str] = set()
    for document_index, document_fact in enumerate(document.get("documents", [])):
        if not isinstance(document_fact, Mapping):
            continue
        document_id = str(document_fact.get("application_document_id", ""))
        if document_id in document_ids:
            issues.append(ValidationIssue(f"$.documents[{document_index}].application_document_id", "drugs_fda.dossier_duplicate", "application document IDs must be unique within a dossier"))
        document_ids.add(document_id)
        document_key = (
            str(document_fact.get("submission_type_source_text", "")).rstrip(" "),
            str(document_fact.get("submission_number", "")),
        )
        expected_orphan = document_key not in submission_keys
        if document_fact.get("source_native_orphan") is not expected_orphan:
            issues.append(ValidationIssue(f"$.documents[{document_index}].source_native_orphan", "drugs_fda.document_parent", "document orphan state must reflect a missing dossier submission parent"))
    return issues


def _contract_semantic_issues(
    contract_id: str, document: Mapping[str, Any], repo_root: Path
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
    if contract_id == _CTGOV_HISTORY_RECEIPT_CONTRACT_ID:
        return _history_receipt_issues(document)
    if contract_id == _CTGOV_HISTORY_RUN_CONTRACT_ID:
        return _history_run_issues(document)
    if contract_id == _TRIAL_HISTORY_SOURCE_SNAPSHOT_CONTRACT_ID:
        return _history_source_snapshot_issues(document)
    if contract_id == _TRIAL_HISTORY_DIFF_CONTRACT_ID:
        return _history_diff_issues(document)
    if contract_id == _TRIAL_REGISTRY_CHANGE_FACT_CONTRACT_ID:
        return _history_change_fact_issues(document)
    if contract_id == _TRIAL_HISTORY_READ_MODEL_CONTRACT_ID:
        return _history_read_model_issues(document)
    if contract_id == _BIOCATALYST_LAUNCH_SLO_MANIFEST_CONTRACT_ID:
        return _biocatalyst_launch_slo_manifest_issues(document, repo_root)
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
    if contract_id == "drugs_at_fda_release_receipt.v1":
        return _drugs_at_fda_release_receipt_issues(document)
    if contract_id == "drugs_at_fda_table_manifest.v1":
        return _drugs_at_fda_table_manifest_issues(document)
    if contract_id == "fda_application_snapshot.v1":
        return _fda_application_snapshot_issues(document)
    if contract_id == "fda_submission_observation.v1":
        return _fda_submission_observation_issues(document)
    if contract_id == "fda_regulatory_event.v1":
        return _fda_regulatory_event_issues(document)
    if contract_id == "fda_application_dossier.v1":
        return _fda_application_dossier_issues(document)
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
        try:
            issues = [
                ValidationIssue(
                    _json_path(tuple(error.absolute_path)), "schema", error.message
                )
                for error in validator.iter_errors(document)
            ]
        except (OverflowError, RecursionError, ValueError):
            issues = [
                ValidationIssue(
                    "$",
                    "schema.invalid_in_memory_document",
                    "contract documents must be finite acyclic JSON trees",
                )
            ]
        issues.extend(_interval_issues(document))
        if requested == _PACKET_CONTRACT_ID and isinstance(document, Mapping):
            issues.extend(_packet_authority_issues(document))
        if isinstance(document, Mapping):
            issues.extend(
                _contract_semantic_issues(requested, document, self.repo_root)
            )
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


def validate_biocatalyst_launch_slo_manifest(
    manifest: Mapping[str, Any],
    *,
    repo_root: Path | str | None = None,
) -> None:
    """Validate one immutable policy; BC-F0 intentionally rejects pass claims."""

    validate_contract(
        _BIOCATALYST_LAUNCH_SLO_MANIFEST_CONTRACT_ID,
        manifest,
        repo_root=repo_root,
    )


def validate_drugs_at_fda_release_receipt(
    receipt: Mapping[str, Any],
    *,
    raw_bodies_by_kind: Mapping[str, bytes | bytearray | memoryview] | None = None,
    repo_root: Path | str | None = None,
) -> None:
    """Validate a B4A release receipt beyond its JSON Schema shape.

    A release is content-addressed by its raw archive only.  The landing page,
    transport headers, and observed timestamps are descriptive evidence and
    must never become an alternate identity or a mutable re-fetch overwrite.
    """
    registry = ContractRegistry(repo_root)
    registry.validate("drugs_at_fda_release_receipt.v1", receipt)
    # ``registry.validate`` above invokes the same non-recursive semantic
    # helper used by generic ``validate_contract``.  Only byte binding is
    # intentionally left here because it requires external raw evidence.
    issues: list[ValidationIssue] = []
    _append_drugs_at_fda_receipt_raw_body_issues(
        issues,
        receipt,
        raw_bodies_by_kind=raw_bodies_by_kind,
    )
    if issues:
        raise ContractValidationError("drugs_at_fda_release_receipt.v1", issues)


def _drugs_at_fda_release_receipt_issues(
    receipt: Mapping[str, Any],
) -> list[ValidationIssue]:
    """Semantic receipt checks which are safe to call from the registry.

    This helper must not construct a ``ContractRegistry`` or call a public
    validator: ``ContractRegistry.issues`` dispatches to it directly.
    """
    issues: list[ValidationIssue] = []
    if receipt.get("source_url") != _FDA_DATA_PAGE_URL:
        issues.append(ValidationIssue("$.source_url", "drugs_fda.receipt_source", "receipt must identify the exact reviewed Drugs@FDA data page"))
    expected_hash = canonical_json_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_payload_sha256"}
    )
    if receipt.get("receipt_payload_sha256") != expected_hash:
        issues.append(ValidationIssue("$.receipt_payload_sha256", "drugs_fda.receipt_hash", "receipt hash does not bind its canonical payload"))
    archive_hash = receipt.get("archive_sha256")
    if receipt.get("release_id") != f"drugs_at_fda_release_{str(archive_hash)[:24]}":
        issues.append(ValidationIssue("$.release_id", "drugs_fda.release_identity", "release ID must be derived only from archive SHA-256"))
    rows = receipt.get("http_receipts")
    by_kind: dict[str, Mapping[str, Any]] = {}
    if isinstance(rows, list):
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                continue
            kind = row.get("kind")
            if not isinstance(kind, str) or kind in by_kind:
                issues.append(ValidationIssue(_json_path(("http_receipts", index, "kind")), "drugs_fda.receipt_kinds", "receipt kinds must be unique"))
            else:
                by_kind[kind] = row
    if set(by_kind) != {"landing_before", "archive", "landing_after"}:
        issues.append(ValidationIssue("$.http_receipts", "drugs_fda.receipt_kinds", "receipt must carry exactly landing_before, archive, landing_after"))
    archive = by_kind.get("archive")
    if isinstance(archive, Mapping):
        if archive.get("exact_response_sha256") != archive_hash:
            issues.append(ValidationIssue("$.http_receipts", "drugs_fda.archive_hash", "archive receipt hash must equal outer archive_sha256"))
        if archive.get("byte_count") != receipt.get("archive_byte_count"):
            issues.append(ValidationIssue("$.http_receipts", "drugs_fda.archive_length", "archive receipt byte count must equal outer archive_byte_count"))
    received_values: list[datetime] = []
    for kind in ("landing_before", "archive", "landing_after"):
        row = by_kind.get(kind)
        if isinstance(row, Mapping):
            expected_source_uri = _FDA_ARCHIVE_URL if kind == "archive" else _FDA_DATA_PAGE_URL
            if row.get("source_uri") != expected_source_uri:
                issues.append(ValidationIssue("$.http_receipts", "drugs_fda.source_uri", f"{kind} source URI must equal the reviewed endpoint"))
            if not _reviewed_fda_https_url(row.get("final_url")):
                issues.append(ValidationIssue("$.http_receipts", "drugs_fda.final_url", f"{kind} final URL must remain on an approved FDA HTTPS host"))
            raw_key = row.get("raw_object_key")
            response_hash = row.get("exact_response_sha256")
            suffix = ".zip" if kind == "archive" else ".html"
            expected_key = (
                f"biocatalyst/raw/drugs_at_fda/archive/{response_hash}.zip"
                if kind == "archive" and isinstance(response_hash, str)
                else f"biocatalyst/raw/drugs_at_fda/landing/{response_hash}.html"
                if kind in {"landing_before", "landing_after"} and isinstance(response_hash, str)
                else None
            )
            if raw_key != expected_key:
                issues.append(ValidationIssue("$.http_receipts", "drugs_fda.raw_key_binding", f"raw key must bind the {kind} directory, response SHA, and type"))
            parsed = _parse_temporal(row.get("received_at"))
            if parsed is not None:
                received_values.append(parsed)
    if len(received_values) == 3:
        before_time, archive_time, after_time = received_values
        observed_time = _parse_temporal(receipt.get("observed_at"))
        if not (before_time <= archive_time <= after_time and (observed_time is None or after_time <= observed_time)):
            issues.append(ValidationIssue("$.http_receipts", "drugs_fda.receipt_order", "landing-before, archive, landing-after, and observed times must be nondecreasing"))
    return issues


def _append_drugs_at_fda_receipt_raw_body_issues(
    issues: list[ValidationIssue],
    receipt: Mapping[str, Any],
    *,
    raw_bodies_by_kind: Mapping[str, bytes | bytearray | memoryview] | None,
) -> None:
    if raw_bodies_by_kind is None:
        return
    rows = receipt.get("http_receipts")
    if not isinstance(rows, list):
        return
    bodies: dict[str, bytes] = {}
    by_kind: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("kind"), str):
            continue
        kind = row["kind"]
        by_kind[kind] = row
        body = raw_bodies_by_kind.get(kind)
        if not isinstance(body, (bytes, bytearray, memoryview)):
            issues.append(ValidationIssue("$.http_receipts", "drugs_fda.raw_body", f"missing exact body for {kind}"))
            continue
        raw = bytes(body)
        bodies[kind] = raw
        if row.get("exact_response_sha256") != hashlib.sha256(raw).hexdigest() or row.get("byte_count") != len(raw):
            issues.append(ValidationIssue("$.http_receipts", "drugs_fda.raw_binding", f"receipt does not bind exact body for {kind}"))
    if set(bodies) != {"landing_before", "archive", "landing_after"}:
        return
    landing_dates: list[str] = []
    for kind in ("landing_before", "landing_after"):
        try:
            text = bodies[kind].decode("utf-8")
        except UnicodeDecodeError:
            issues.append(ValidationIssue("$.http_receipts", "drugs_fda.landing_release_date", f"{kind} must be UTF-8 FDA landing evidence"))
            continue
        visible = unescape(text)
        match = re.search(
            r"Data\s+Last\s+Updated:\s*([A-Za-z]+\s+[0-9]{1,2}(?:st|nd|rd|th)?\s*,?\s*[0-9]{4})",
            visible,
            flags=re.IGNORECASE,
        )
        if "<html" not in text.casefold() or _FDA_ARCHIVE_URL not in visible or match is None:
            issues.append(ValidationIssue("$.http_receipts", "drugs_fda.landing_release_date", f"{kind} must carry the reviewed archive link and source-reported release date"))
            continue
        raw_date = re.sub(r"(st|nd|rd|th)\b", "", match.group(1).strip(), flags=re.IGNORECASE)
        try:
            landing_dates.append(datetime.strptime(raw_date, "%B %d, %Y").date().isoformat())
        except ValueError:
            issues.append(ValidationIssue("$.http_receipts", "drugs_fda.landing_release_date", f"{kind} carries an invalid source-reported release date"))
    archive_headers = by_kind.get("archive", {}).get("response_headers", {})
    disposition = archive_headers.get("content-disposition", "") if isinstance(archive_headers, Mapping) else ""
    token = re.search(r"filename=(?:\"?)(?:dafdata)([0-9]{8})\.zip", str(disposition), flags=re.IGNORECASE)
    archive_date: str | None = None
    if token is not None:
        try:
            archive_date = datetime.strptime(token.group(1), "%Y%m%d").date().isoformat()
        except ValueError:
            archive_date = None
    if archive_date is None:
        issues.append(ValidationIssue("$.http_receipts", "drugs_fda.archive_release_date", "archive content-disposition must carry a valid dafdataYYYYMMDD.zip release token"))
    expected_date = receipt.get("source_release_date")
    if len(landing_dates) == 2 and (
        landing_dates[0] != landing_dates[1]
        or landing_dates[0] != expected_date
        or archive_date != expected_date
    ):
        issues.append(ValidationIssue("$.source_release_date", "drugs_fda.release_date_binding", "outer, landing-before, archive filename, and landing-after release dates must agree exactly"))


def validate_drugs_at_fda_table_manifest(
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    exact_member_bytes: bytes | bytearray | memoryview | None = None,
    repo_root: Path | str | None = None,
) -> None:
    """Bind one table manifest to one exact release/member without inference."""
    # Validate the parent receipt first.  A table can only have meaning inside
    # the exact archive transaction it claims to describe.
    validate_drugs_at_fda_release_receipt(receipt, repo_root=repo_root)
    registry = ContractRegistry(repo_root)
    registry.validate("drugs_at_fda_table_manifest.v1", manifest)
    issues: list[ValidationIssue] = []
    if manifest.get("release_id") != receipt.get("release_id") or manifest.get("archive_sha256") != receipt.get("archive_sha256"):
        issues.append(ValidationIssue("$.release_id", "drugs_fda.release_binding", "manifest release identity must equal validated receipt"))
    if exact_member_bytes is not None:
        payload = bytes(exact_member_bytes)
        expected_crc32 = f"{binascii.crc32(payload) & 0xffffffff:08x}"
        if (
            manifest.get("member_sha256") != hashlib.sha256(payload).hexdigest()
            or manifest.get("uncompressed_byte_count") != len(payload)
            or manifest.get("zip_crc32") != expected_crc32
        ):
            issues.append(ValidationIssue("$.member_sha256", "drugs_fda.member_binding", "manifest must bind exact uncompressed member bytes"))
        try:
            from collectors.biocatalyst.drugs_at_fda import _parse_tsv

            _rows, recomputed = _parse_tsv(
                table_name=str(manifest.get("table_name")),
                payload=payload,
                archive_sha256=str(manifest.get("archive_sha256")),
                compressed_byte_count=int(manifest.get("compressed_byte_count", 0)),
                uncompressed_byte_count=len(payload),
                crc32=binascii.crc32(payload) & 0xffffffff,
                retain_rows=False,
            )
            semantic_fields = (
                "member_sha256",
                "uncompressed_byte_count",
                "zip_crc32",
                "row_count",
                "header",
                "primary_key_fields",
                "encoding",
                "field_count_profile",
                "ordered_row_digest_sha256",
                "typed_row_semantic_digest_sha256",
                "row_shape_repairs",
            )
            if any(manifest.get(field) != recomputed.get(field) for field in semantic_fields):
                issues.append(ValidationIssue("$", "drugs_fda.member_semantics", "manifest row semantics must be recomputed from exact member bytes"))
        except (ImportError, RuntimeError, TypeError, ValueError) as exc:
            # Exact-member validation is an acceptance boundary.  Parser or
            # import failures become a validation issue, never an untyped
            # exception or a reason to trust the manifest's self-description.
            issues.append(ValidationIssue("$", "drugs_fda.member_semantics", f"exact member semantics could not be verified: {type(exc).__name__}"))
    if issues:
        raise ContractValidationError("drugs_at_fda_table_manifest.v1", issues)


def _drugs_at_fda_table_manifest_issues(
    manifest: Mapping[str, Any],
) -> list[ValidationIssue]:
    """Validate deterministic table semantics without a parent receipt.

    Imported parser constants are intentionally lazy so the contract registry
    stays dependency-light at process start; no collector import happens while
    this module itself is imported.
    """
    from collectors.biocatalyst.drugs_at_fda import (
        EXPECTED_HEADERS,
        PRIMARY_KEY_FIELDS,
        _APPDOCS_EMPTY_FIELD_EXCEPTION,
    )

    issues: list[ValidationIssue] = []
    expected_hash = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_payload_sha256"}
    )
    if manifest.get("manifest_payload_sha256") != expected_hash:
        issues.append(ValidationIssue("$.manifest_payload_sha256", "drugs_fda.manifest_hash", "manifest hash does not bind canonical payload"))
    table_name = manifest.get("table_name")
    archive_sha = manifest.get("archive_sha256")
    expected_id = f"drugs_at_fda_table_{canonical_json_sha256({'archive': archive_sha, 'table': table_name})[:24]}"
    if manifest.get("table_manifest_id") != expected_id:
        issues.append(ValidationIssue("$.table_manifest_id", "drugs_fda.manifest_identity", "manifest ID must bind archive SHA and table name"))
    if manifest.get("release_id") != f"drugs_at_fda_release_{str(archive_sha)[:24]}":
        issues.append(ValidationIssue("$.release_id", "drugs_fda.release_identity", "manifest release ID must be derived only from archive SHA-256"))
    if table_name not in EXPECTED_HEADERS:
        issues.append(ValidationIssue("$.table_name", "drugs_fda.table_set", "table must be one of the exact 12 Drugs@FDA members"))
        return issues
    if manifest.get("header") != list(EXPECTED_HEADERS[table_name]):
        issues.append(ValidationIssue("$.header", "drugs_fda.header", "table header must equal the exact source-native header"))
    if manifest.get("primary_key_fields") != list(PRIMARY_KEY_FIELDS[table_name]):
        issues.append(ValidationIssue("$.primary_key_fields", "drugs_fda.primary_key", "table primary-key fields must equal the parser contract"))
    profile = manifest.get("field_count_profile")
    row_count = manifest.get("row_count")
    if isinstance(profile, Mapping) and isinstance(row_count, int):
        try:
            profile_count = sum(value for value in profile.values() if isinstance(value, int))
        except TypeError:
            profile_count = -1
        if profile_count != row_count:
            issues.append(ValidationIssue("$.field_count_profile", "drugs_fda.field_profile", "field-count profile must reconcile exactly to row_count"))
    repairs = manifest.get("row_shape_repairs")
    if not isinstance(repairs, list):
        return issues
    expected_exception = _APPDOCS_EMPTY_FIELD_EXCEPTION
    expected_repair = {
        "rule": "application_docs_empty_field_before_date",
        "row_number": expected_exception["row_number"],
        "raw_row_sha256": expected_exception["raw_row_sha256"],
        "expected_field_count": len(EXPECTED_HEADERS[expected_exception["table"]]),
        "observed_field_count": len(EXPECTED_HEADERS[expected_exception["table"]]) + 1,
    }
    expected_repairs = (
        [expected_repair]
        if archive_sha == expected_exception["archive_sha256"]
        and table_name == expected_exception["table"]
        else []
    )
    if repairs != expected_repairs:
        issues.append(ValidationIssue("$.row_shape_repairs", "drugs_fda.pinned_repair", "row-shape repairs must equal the single reviewed archive/table/physical-row exception and otherwise be empty"))
    return issues


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


def exact_history_json_diff(before: Any, after: Any) -> list[dict[str, Any]]:
    """Return the B2 exact diff with history-plane change-family labels.

    The JSON operation semantics remain byte-for-byte identical to
    :func:`exact_json_diff`; only the closed family taxonomy is adapted for the
    historical change-fact plane.  This keeps B1's frozen contract untouched.
    """

    families: list[dict[str, Any]] = []
    for operation in exact_json_diff(before, after):
        normalized = copy.deepcopy(operation)
        path = normalized["json_path"]
        if path.endswith("/overallStatus"):
            family = "registry_status"
        elif "/enrollmentInfo" in path:
            family = "enrollment"
        elif "/statusModule/" in path and any(
            marker in path
            for marker in ("startDateStruct", "primaryCompletionDateStruct", "completionDateStruct")
        ):
            family = "study_date"
        elif "/contactsLocationsModule/locations" in path:
            family = "site_listing"
        elif any(
            marker in path
            for marker in (
                "/outcomesModule/primaryOutcomes",
                "/outcomesModule/secondaryOutcomes",
                "/outcomesModule/otherOutcomes",
            )
        ):
            family = "endpoint_record"
        elif "/sponsorCollaboratorsModule/leadSponsor" in path:
            family = "sponsor"
        elif "/armsInterventionsModule/interventions" in path:
            family = "intervention"
        else:
            family = "other"
        normalized["change_family"] = family
        families.append(normalized)
    return families


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


def version_receipt_payloads_sha256(
    receipts: Sequence[Mapping[str, Any]],
) -> str:
    """Hash the immutable CT.gov ``/version`` before/after receipt pair.

    The ordered pair is deliberately separate from page receipts: a source may
    serve perfectly parseable pages while changing the version metadata during
    a poll.  Recording the exact pair makes that race auditable rather than an
    unrepeatable boolean assertion.
    """

    if len(receipts) != 2:
        raise ValueError("version receipts must contain exactly before and after entries")
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
        if (
            isinstance(request, Mapping)
            and isinstance(manifest, Mapping)
            and manifest.get("request_path") is not None
            and request.get("path") != manifest.get("request_path")
        ):
            issues.append(
                ValidationIssue(
                    f"$.receipt_refs[{index}]",
                    "fetch_run.query_wire_binding",
                    "receipt request path must match the run query manifest",
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
    manifest = run.get("query_manifest")
    base_query_params = (
        manifest.get("base_query_params") if isinstance(manifest, Mapping) else None
    )
    total_count_requested = (
        isinstance(base_query_params, Mapping)
        and base_query_params.get("countTotal") == "true"
    )
    declared_total_count: int | None = None
    for page_index, (receipt_id, page) in enumerate(parsed_pages.items()):
        total_count = page.get("totalCount")
        total_count_valid = (
            isinstance(total_count, int)
            and not isinstance(total_count, bool)
            and total_count >= 0
        )
        if page_index == 0 and total_count_requested:
            if not total_count_valid:
                issues.append(
                    ValidationIssue(
                        f"$.raw_pages.{receipt_id}.totalCount",
                        "raw_run.total_count",
                        "the first page must carry a nonnegative integer totalCount when countTotal=true",
                    )
                )
            else:
                declared_total_count = total_count
        elif "totalCount" in page:
            if not total_count_valid:
                issues.append(
                    ValidationIssue(
                        f"$.raw_pages.{receipt_id}.totalCount",
                        "raw_run.total_count",
                        "totalCount must be a nonnegative integer when supplied",
                    )
                )
            elif (
                declared_total_count is not None
                and total_count != declared_total_count
            ):
                issues.append(
                    ValidationIssue(
                        f"$.raw_pages.{receipt_id}.totalCount",
                        "raw_run.total_count",
                        "later-page totalCount must equal the first-page declaration",
                    )
                )
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
    if declared_total_count is not None and declared_total_count != derived_unique:
        issues.append(
            ValidationIssue(
                "$.raw_pages.totalCount",
                "raw_run.total_count",
                "declared totalCount must equal the unique NCT count derived from all terminal pages",
            )
        )
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
    *,
    receipt_by_id: Mapping[Any, Mapping[str, Any]] | None = None,
    published_ref_set: frozenset[Any] | None = None,
    configured_nct_id_set: frozenset[Any] | None = None,
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

    if receipt_by_id is None:
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
    if published_ref_set is None and isinstance(published_refs, list):
        published_ref_set = frozenset(published_refs)
    if (
        published_ref_set is None
        or source_snapshot.get("source_record_ref") not in published_ref_set
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
    if configured_nct_id_set is None and isinstance(configured_nct_ids, list):
        configured_nct_id_set = frozenset(configured_nct_ids)
    if (
        configured_nct_id_set is None
        or source_snapshot.get("nct_id") not in configured_nct_id_set
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


@dataclass(frozen=True)
class ValidatedCtgovPublicationContext:
    """Validated, reusable CT.gov raw-page context for one publication batch.

    Constructing the context performs the expensive byte parsing and complete-run
    reconciliation exactly once.  Batch publishers can then enumerate studies and
    validate every source snapshot without re-reading all pages for each record.
    """

    _run: Mapping[str, Any]
    _receipts: tuple[Mapping[str, Any], ...]
    _parsed_pages: Mapping[str, Mapping[str, Any]]
    _receipt_by_id: Mapping[Any, Mapping[str, Any]]
    _published_ref_set: frozenset[Any]
    _configured_nct_id_set: frozenset[Any]
    derived_source_record_refs: tuple[str, ...]
    repo_root: Path | str | None = None

    @property
    def run(self) -> Mapping[str, Any]:
        """Return a defensive copy of the validated run."""

        return copy.deepcopy(self._run)

    @property
    def receipts(self) -> tuple[Mapping[str, Any], ...]:
        """Return defensive copies of the validated ordered receipts."""

        return tuple(copy.deepcopy(self._receipts))

    @property
    def parsed_pages(self) -> Mapping[str, Mapping[str, Any]]:
        """Return a defensive copy; internal validators retain the owned cache."""

        return copy.deepcopy(self._parsed_pages)

    def indexed_studies(self) -> Iterable[tuple[str, int, Mapping[str, Any]]]:
        """Yield ``(receipt_id, study_index, canonical_study)`` in page order."""

        for receipt in self._receipts:
            receipt_id = receipt["receipt_id"]
            for study_index, study in enumerate(self._parsed_pages[receipt_id]["studies"]):
                assert isinstance(study, Mapping)
                yield receipt_id, study_index, copy.deepcopy(study)

    def validate_source_snapshots(
        self, source_snapshots: Sequence[Mapping[str, Any]]
    ) -> None:
        """Validate complete one-to-one snapshot coverage using cached pages."""

        _validate_ctgov_source_snapshots_against_context(self, source_snapshots)


def build_ctgov_publication_context(
    run: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    raw_page_bodies_by_receipt: Mapping[str, bytes | bytearray | memoryview],
    *,
    repo_root: Path | str | None = None,
) -> ValidatedCtgovPublicationContext:
    """Validate raw run evidence once and return a reusable batch context."""

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
    return ValidatedCtgovPublicationContext(
        _run=copy.deepcopy(run),
        _receipts=tuple(copy.deepcopy(receipts)),
        _parsed_pages=copy.deepcopy(parsed_pages),
        _receipt_by_id={
            receipt.get("receipt_id"): copy.deepcopy(receipt) for receipt in receipts
        },
        _published_ref_set=frozenset(run.get("published_source_record_refs", ())),
        _configured_nct_id_set=frozenset(
            run.get("query_manifest", {}).get("configured_nct_ids", ())
        ),
        derived_source_record_refs=derived_refs,
        repo_root=repo_root,
    )


def _validate_ctgov_source_snapshots_against_context(
    context: ValidatedCtgovPublicationContext,
    source_snapshots: Sequence[Mapping[str, Any]],
) -> None:
    """Validate snapshot coverage and bindings against prevalidated raw pages."""

    run = context._run
    receipts = context._receipts
    registry = ContractRegistry(context.repo_root)
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
    if tuple(sorted(snapshot_refs)) != context.derived_source_record_refs or len(
        snapshot_refs
    ) != len(set(snapshot_refs)):
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
            context._parsed_pages,
            receipt_by_id=context._receipt_by_id,
            published_ref_set=context._published_ref_set,
            configured_nct_id_set=context._configured_nct_id_set,
        )


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

    context = build_ctgov_publication_context(
        run,
        receipts,
        raw_page_bodies_by_receipt,
        repo_root=repo_root,
    )
    context.validate_source_snapshots(source_snapshots)


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


def _history_receipt_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    hash_issue = _content_hash_issue(
        document,
        hash_field="receipt_payload_sha256",
        excluded_fields=frozenset(("receipt_payload_sha256",)),
        code="history_receipt.hash",
    )
    if hash_issue is not None:
        issues.append(hash_issue)
    resource_kind = document.get("resource_kind")
    source_version = document.get("source_version")
    request = document.get("request")
    response = document.get("response")
    nct_id = document.get("nct_id")
    if resource_kind == "history_index" and source_version is not None:
        issues.append(
            ValidationIssue(
                "$.source_version",
                "history_receipt.resource_binding",
                "a history-index receipt cannot name an individual source version",
            )
        )
    if resource_kind == "history_version" and (
        isinstance(source_version, bool) or not isinstance(source_version, int)
    ):
        issues.append(
            ValidationIssue(
                "$.source_version",
                "history_receipt.resource_binding",
                "a history-version receipt requires a non-boolean integer version",
            )
        )
    if isinstance(request, Mapping) and isinstance(nct_id, str):
        source_uri = request.get("source_uri")
        if isinstance(source_uri, str) and f"/studies/{nct_id}" not in source_uri:
            issues.append(
                ValidationIssue(
                    "$.request.source_uri",
                    "history_receipt.identity",
                    "request URI must identify the wrapper NCT ID",
                )
            )
        if resource_kind == "history_version" and isinstance(source_version, int):
            expected_suffix = f"/history/{source_version}"
            if isinstance(source_uri, str) and not source_uri.endswith(expected_suffix):
                issues.append(
                    ValidationIssue(
                        "$.request.source_uri",
                        "history_receipt.resource_binding",
                        "version request URI must end with the requested source version",
                    )
                )
    if isinstance(response, Mapping) and isinstance(nct_id, str):
        raw_key = response.get("raw_response_object_key")
        raw_hash = response.get("exact_response_sha256")
        if (
            isinstance(raw_key, str)
            and isinstance(raw_hash, str)
            and not raw_key.endswith(f"/{raw_hash}.json")
        ):
            issues.append(
                ValidationIssue(
                    "$.response.raw_response_object_key",
                    "history_receipt.object_key",
                    "raw response object key must be content-addressed by response hash",
                )
            )
        if isinstance(raw_key, str) and f"/{nct_id}/" not in raw_key:
            issues.append(
                ValidationIssue(
                    "$.response.raw_response_object_key",
                    "history_receipt.identity",
                    "raw response object key must identify the wrapper NCT ID",
                )
            )
    issue = _timestamp_order_issue(
        document, "transaction_from", "transaction_to", "history_receipt.transaction"
    )
    if issue is not None:
        issues.append(issue)
    if isinstance(response, Mapping):
        received = _parse_temporal(response.get("received_at"))
        transaction = _parse_temporal(document.get("transaction_from"))
        if received is not None and transaction is not None and transaction < received:
            issues.append(
                ValidationIssue(
                    "$.transaction_from",
                    "history_receipt.transaction",
                    "receipt transaction time cannot precede response receipt time",
                )
            )
    return issues


def _history_run_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    hash_issue = _content_hash_issue(
        document,
        hash_field="run_payload_sha256",
        excluded_fields=frozenset(("run_payload_sha256",)),
        code="history_run.hash",
    )
    if hash_issue is not None:
        issues.append(hash_issue)
    manifest = document.get("version_manifest")
    refs = document.get("history_version_receipt_refs")
    if isinstance(manifest, list):
        versions = [entry.get("source_version") for entry in manifest if isinstance(entry, Mapping)]
        displays = [entry.get("display_version") for entry in manifest if isinstance(entry, Mapping)]
        if versions != list(range(len(versions))):
            issues.append(
                ValidationIssue(
                    "$.version_manifest",
                    "history_run.version_sequence",
                    "history versions must be contiguous and zero-based",
                )
            )
        if displays != [version + 1 for version in versions if isinstance(version, int)]:
            issues.append(
                ValidationIssue(
                    "$.version_manifest",
                    "history_run.display_sequence",
                    "display versions must be exactly one greater than source versions",
                )
            )
    if document.get("run_state") == "complete":
        complete = (
            document.get("completeness_state") == "history_complete"
            and document.get("finished_at") is not None
            and isinstance(manifest, list)
            and isinstance(refs, list)
            and len(manifest) == len(refs)
            and len(refs) > 0
            and document.get("error_codes") == []
        )
        if not complete:
            issues.append(
                ValidationIssue(
                    "$.run_state",
                    "history_run.complete",
                    "complete history runs require full version receipt coverage and no errors",
                )
            )
        if (
            document.get("history_index_receipt_ref")
            == document.get("history_index_post_receipt_ref")
        ):
            issues.append(
                ValidationIssue(
                    "$.history_index_post_receipt_ref",
                    "history_run.index_receipt",
                    "complete history runs require distinct pre-index and post-index receipt references",
                )
            )
    elif document.get("completeness_state") == "history_complete":
        issues.append(
            ValidationIssue(
                "$.completeness_state",
                "history_run.incomplete",
                "only complete runs may claim a complete historical version chain",
            )
        )
    for first, second, code in (
        ("started_at", "finished_at", "history_run.interval"),
        ("started_at", "transaction_from", "history_run.transaction"),
    ):
        issue = _timestamp_order_issue(document, first, second, code)
        if issue is not None:
            issues.append(issue)
    return issues


def _history_source_snapshot_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    hash_issue = _content_hash_issue(
        document,
        hash_field="snapshot_payload_sha256",
        excluded_fields=frozenset(("snapshot_payload_sha256",)),
        code="history_snapshot.hash",
    )
    if hash_issue is not None:
        issues.append(hash_issue)
    canonical_study = document.get("canonical_study")
    nct_id = document.get("nct_id")
    content_hash = document.get("canonical_content_sha256")
    source_version = document.get("source_version")
    if isinstance(canonical_study, Mapping) and isinstance(content_hash, str):
        actual_hash = canonical_json_sha256(canonical_study)
        if content_hash != actual_hash:
            issues.append(
                ValidationIssue(
                    "$.canonical_content_sha256",
                    "history_snapshot.content_hash",
                    "canonical content hash must match the historical source study",
                )
            )
        source_nct = _resolve_json_pointer(
            canonical_study, "/protocolSection/identificationModule/nctId"
        )
        if source_nct != nct_id:
            issues.append(
                ValidationIssue(
                    "$.canonical_study.protocolSection.identificationModule.nctId",
                    "history_snapshot.identity",
                    "historical source study NCT ID must match wrapper NCT ID",
                )
            )
    if isinstance(nct_id, str) and isinstance(content_hash, str) and isinstance(source_version, int):
        expected_ref = f"src:ctgov-history:{nct_id}:version:{source_version}:sha256:{content_hash}"
        if document.get("source_record_ref") != expected_ref:
            issues.append(
                ValidationIssue(
                    "$.source_record_ref",
                    "history_snapshot.content_address",
                    "source record reference must bind NCT ID, history version, and content hash",
                )
            )
        if document.get("display_version") != source_version + 1:
            issues.append(
                ValidationIssue(
                    "$.display_version",
                    "history_snapshot.display_version",
                    "display version must be one greater than the zero-based source version",
                )
            )
    source_uri = document.get("source_uri")
    if isinstance(nct_id, str) and isinstance(source_version, int) and isinstance(source_uri, str):
        expected_uri = f"https://clinicaltrials.gov/study/{nct_id}?a={source_version + 1}&tab=history"
        if source_uri != expected_uri:
            issues.append(
                ValidationIssue(
                    "$.source_uri",
                    "history_snapshot.source_uri",
                    "source URI must identify the public record-history display version",
                )
            )
    for first, second, code in (
        ("retrieved_at", "transaction_from", "history_snapshot.transaction"),
    ):
        issue = _timestamp_order_issue(document, first, second, code)
        if issue is not None:
            issues.append(issue)
    return issues


def _history_diff_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    hash_issue = _content_hash_issue(
        document,
        hash_field="diff_payload_sha256",
        excluded_fields=frozenset(("diff_payload_sha256",)),
        code="history_diff.hash",
    )
    if hash_issue is not None:
        issues.append(hash_issue)
    before_hash = document.get("before_content_sha256")
    after_hash = document.get("after_content_sha256")
    if isinstance(before_hash, str) and before_hash == after_hash:
        issues.append(
            ValidationIssue(
                "$.after_content_sha256",
                "history_diff.noop_hash",
                "historical diff must connect two different canonical source hashes",
            )
        )
    if document.get("after_source_version") != document.get("before_source_version", -2) + 1:
        issues.append(
            ValidationIssue(
                "$.after_source_version",
                "history_diff.version_sequence",
                "exact historical diffs must connect consecutive source versions",
            )
        )
    operations = document.get("operations")
    if isinstance(operations, list):
        paths = [item.get("json_path") for item in operations if isinstance(item, Mapping)]
        if len(paths) != len(set(paths)) or (
            all(isinstance(path, str) for path in paths) and paths != sorted(paths)
        ):
            issues.append(
                ValidationIssue(
                    "$.operations",
                    "history_diff.order",
                    "historical diff operations must have unique lexicographically ordered paths",
                )
            )
        for index, operation in enumerate(operations):
            if not isinstance(operation, Mapping):
                continue
            expected = {"add": ("missing", "present"), "remove": ("present", "missing"), "replace": ("present", "present")}.get(operation.get("op"))
            if expected is not None and (operation.get("before_state"), operation.get("after_state")) != expected:
                issues.append(
                    ValidationIssue(
                        f"$.operations[{index}]",
                        "history_diff.operation_state",
                        "operation states must match the JSON patch operation",
                    )
                )
    return issues


def _history_change_fact_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    hash_issue = _content_hash_issue(
        document,
        hash_field="fact_payload_sha256",
        excluded_fields=frozenset(("fact_payload_sha256",)),
        code="history_change_fact.hash",
    )
    if hash_issue is not None:
        issues.append(hash_issue)
    if document.get("after_source_version") != document.get("before_source_version", -2) + 1:
        issues.append(
            ValidationIssue(
                "$.after_source_version",
                "history_change_fact.version_sequence",
                "change facts must bind consecutive historical versions",
            )
        )
    return issues


def _history_read_model_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    hash_issue = _content_hash_issue(
        document,
        hash_field="model_payload_sha256",
        excluded_fields=frozenset(("model_payload_sha256",)),
        code="history_read_model.hash",
    )
    if hash_issue is not None:
        issues.append(hash_issue)
    versions = document.get("versions")
    if isinstance(versions, list):
        display_versions = [entry.get("display_version") for entry in versions if isinstance(entry, Mapping)]
        if display_versions != sorted(display_versions) or len(display_versions) != len(set(display_versions)):
            issues.append(
                ValidationIssue(
                    "$.versions",
                    "history_read_model.version_order",
                    "public history versions must be unique and ordered by display version",
                )
            )
    private_key_fragments = (
        "raw",
        "hash",
        "sha256",
        "receipt",
        "ref",
        "objectkey",
        "path",
        "jsonpath",
        "provenance",
    )

    def walk(value: Any, path: tuple[str | int, ...]) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                normalized_key = (
                    key.casefold().replace("_", "") if isinstance(key, str) else ""
                )
                root_integrity_field = path == () and key in {
                    "model_payload_sha256",
                    "hash_scope",
                }
                if not root_integrity_field and (
                    not isinstance(key, str) or any(
                        fragment in normalized_key for fragment in private_key_fragments
                    )
                ):
                    issues.append(
                        ValidationIssue(
                            _json_path((*path, key)),
                            "history_read_model.private_provenance",
                            "public history model cannot expose private provenance or integrity keys",
                        )
                    )
                walk(nested, (*path, key))
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                walk(nested, (*path, index))

    walk(document, ())
    return issues


def derive_trial_registry_change_descriptors(
    before_study: Mapping[str, Any], after_study: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Derive the closed, decision-inert B2 fact projection from two studies.

    This is deliberately independent of a fact document: the validator uses it
    to make every fact's kind, paths, and values replayable from exact source
    snapshots rather than trust a rehashed semantic assertion.
    """

    def pointer_value(document: Mapping[str, Any], pointer: str) -> Any:
        return _resolve_json_pointer(document, pointer)

    def json_value(value: Any) -> Any:
        return None if value is _MISSING else value

    def object_list(value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []

    def normal_text(value: Any) -> str:
        return " ".join(value.casefold().split()) if isinstance(value, str) else ""

    def endpoint_items(study: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        module = "/protocolSection/outcomesModule/"
        return [
            (role, outcome)
            for role, field in (
                ("primary", "primaryOutcomes"),
                ("secondary", "secondaryOutcomes"),
                ("other", "otherOutcomes"),
            )
            for outcome in object_list(pointer_value(study, module + field))
        ]

    def exact_pairs(
        before: Sequence[Any], after: Sequence[Any]
    ) -> tuple[list[tuple[Any, Any]], list[Any], list[Any]]:
        after_by_hash: dict[str, list[Any]] = {}
        for item in after:
            item_value = item[1] if isinstance(item, tuple) else item
            after_by_hash.setdefault(canonical_json_sha256(item_value), []).append(item)
        pairs: list[tuple[Any, Any]] = []
        unmatched_before: list[Any] = []
        for item in before:
            item_value = item[1] if isinstance(item, tuple) else item
            candidates = after_by_hash.get(canonical_json_sha256(item_value), [])
            if candidates:
                pairs.append((item, candidates.pop(0)))
            else:
                unmatched_before.append(item)
        return pairs, unmatched_before, [item for values in after_by_hash.values() for item in values]

    def outcome_score(before: Mapping[str, Any], after: Mapping[str, Any]) -> float:
        before_measure, after_measure = normal_text(before.get("measure")), normal_text(after.get("measure"))
        if not before_measure or not after_measure:
            return 0.0
        return (
            0.65 * SequenceMatcher(None, before_measure, after_measure, autojunk=False).ratio()
            + 0.25
            * SequenceMatcher(
                None,
                normal_text(before.get("timeFrame")),
                normal_text(after.get("timeFrame")),
                autojunk=False,
            ).ratio()
            + 0.10
            * SequenceMatcher(
                None,
                normal_text(before.get("description")),
                normal_text(after.get("description")),
                autojunk=False,
            ).ratio()
        )

    def unique_outcome_pairs(
        before: Sequence[tuple[str, dict[str, Any]]], after: Sequence[tuple[str, dict[str, Any]]]
    ) -> tuple[
        list[tuple[tuple[str, dict[str, Any]], tuple[str, dict[str, Any]]]],
        list[tuple[str, dict[str, Any]]],
        list[tuple[str, dict[str, Any]]],
    ]:
        exact, unmatched_before, unmatched_after = exact_pairs(before, after)
        candidates: dict[tuple[int, int], float] = {}
        for before_index, (_, before_item) in enumerate(unmatched_before):
            for after_index, (_, after_item) in enumerate(unmatched_after):
                score = outcome_score(before_item, after_item)
                if score >= 0.80:
                    candidates[(before_index, after_index)] = score
        paired_before: set[int] = set()
        paired_after: set[int] = set()
        pairs = list(exact)
        for (before_index, after_index), score in sorted(
            candidates.items(), key=lambda item: (-item[1], item[0])
        ):
            if before_index in paired_before or after_index in paired_after:
                continue
            before_alternatives = [
                value
                for (index, candidate_after_index), value in candidates.items()
                if index == before_index and candidate_after_index != after_index
            ]
            after_alternatives = [
                value
                for (candidate_before_index, index), value in candidates.items()
                if index == after_index and candidate_before_index != before_index
            ]
            before_margin = score - max(before_alternatives, default=0.0)
            after_margin = score - max(after_alternatives, default=0.0)
            if before_margin < 0.10 or after_margin < 0.10:
                continue
            paired_before.add(before_index)
            paired_after.add(after_index)
            pairs.append((unmatched_before[before_index], unmatched_after[after_index]))
        plausible_before = {before_index for before_index, _ in candidates}
        plausible_after = {after_index for _, after_index in candidates}
        return (
            pairs,
            [
                item
                for index, item in enumerate(unmatched_before)
                if index not in paired_before and index not in plausible_before
            ],
            [
                item
                for index, item in enumerate(unmatched_after)
                if index not in paired_after and index not in plausible_after
            ],
        )

    def unique_intervention_pairs(
        before: Sequence[dict[str, Any]], after: Sequence[dict[str, Any]]
    ) -> tuple[
        list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]
    ]:
        exact, unmatched_before, unmatched_after = exact_pairs(before, after)
        candidates: dict[tuple[int, int], float] = {}
        for before_index, before_item in enumerate(unmatched_before):
            for after_index, after_item in enumerate(unmatched_after):
                before_name, after_name = normal_text(before_item.get("name")), normal_text(after_item.get("name"))
                if not before_name or not after_name:
                    continue
                name_score = SequenceMatcher(None, before_name, after_name, autojunk=False).ratio()
                type_score = (
                    1.0
                    if normal_text(before_item.get("type")) == normal_text(after_item.get("type"))
                    else 0.0
                )
                score = 0.8 * name_score + 0.2 * type_score
                if score >= 0.85:
                    candidates[(before_index, after_index)] = score
        paired_before: set[int] = set()
        paired_after: set[int] = set()
        pairs = list(exact)
        for (before_index, after_index), _score in sorted(
            candidates.items(), key=lambda item: (-item[1], item[0])
        ):
            if before_index in paired_before or after_index in paired_after:
                continue
            if (
                sum(1 for index, _ in candidates if index == before_index) != 1
                or sum(1 for _, index in candidates if index == after_index) != 1
            ):
                continue
            paired_before.add(before_index)
            paired_after.add(after_index)
            pairs.append((unmatched_before[before_index], unmatched_after[after_index]))
        plausible_before = {before_index for before_index, _ in candidates}
        plausible_after = {after_index for _, after_index in candidates}
        return (
            pairs,
            [
                item
                for index, item in enumerate(unmatched_before)
                if index not in paired_before and index not in plausible_before
            ],
            [
                item
                for index, item in enumerate(unmatched_after)
                if index not in paired_after and index not in plausible_after
            ],
        )

    descriptors: list[dict[str, Any]] = []

    def add(kind: str, paths: Sequence[str], before_value: Any, after_value: Any) -> None:
        descriptors.append(
            {
                "kind": kind,
                "source_json_paths": sorted(set(paths)),
                "before_value": before_value,
                "after_value": after_value,
            }
        )

    for kind, path in (
        ("registry_status_changed", "/protocolSection/statusModule/overallStatus"),
        ("enrollment_changed", "/protocolSection/designModule/enrollmentInfo"),
        ("study_date_changed", "/protocolSection/statusModule/startDateStruct"),
        ("study_date_changed", "/protocolSection/statusModule/primaryCompletionDateStruct"),
        ("study_date_changed", "/protocolSection/statusModule/completionDateStruct"),
        ("lead_sponsor_text_changed", "/protocolSection/sponsorCollaboratorsModule/leadSponsor"),
    ):
        before_value, after_value = json_value(pointer_value(before_study, path)), json_value(pointer_value(after_study, path))
        if canonical_json_bytes(before_value) != canonical_json_bytes(after_value):
            add(kind, [path], before_value, after_value)

    site_path = "/protocolSection/contactsLocationsModule/locations"
    before_sites, after_sites = object_list(pointer_value(before_study, site_path)), object_list(pointer_value(after_study, site_path))
    if canonical_json_bytes(before_sites) != canonical_json_bytes(after_sites):
        before_counts = Counter(canonical_json_sha256(item) for item in before_sites)
        after_counts = Counter(canonical_json_sha256(item) for item in after_sites)
        added_count = sum((after_counts - before_counts).values())
        removed_count = sum((before_counts - after_counts).values())
        add(
            "site_listing_changed",
            [site_path],
            {"count": len(before_sites), "added_count": added_count, "removed_count": removed_count},
            {"count": len(after_sites), "added_count": added_count, "removed_count": removed_count},
        )

    module_name = {
        "primary": "primaryOutcomes",
        "secondary": "secondaryOutcomes",
        "other": "otherOutcomes",
    }

    def endpoint_paths(before_role: str, after_role: str) -> list[str]:
        return sorted(
            {
                f"/protocolSection/outcomesModule/{module_name[before_role]}",
                f"/protocolSection/outcomesModule/{module_name[after_role]}",
            }
        )

    pairs, removed_outcomes, added_outcomes = unique_outcome_pairs(
        endpoint_items(before_study), endpoint_items(after_study)
    )
    for (before_role, before_outcome), (after_role, after_outcome) in pairs:
        paths = endpoint_paths(before_role, after_role)
        if before_role != after_role:
            add("endpoint_role_changed", paths, before_role, after_role)
        for kind, key in (
            ("endpoint_measure_changed", "measure"),
            ("endpoint_time_frame_changed", "timeFrame"),
            ("endpoint_description_changed", "description"),
        ):
            before_value, after_value = before_outcome.get(key), after_outcome.get(key)
            if canonical_json_bytes(before_value) != canonical_json_bytes(after_value):
                add(kind, paths, before_value, after_value)
    for role, outcome in removed_outcomes:
        add("endpoint_removed", endpoint_paths(role, role), {"role": role, "outcome": outcome}, None)
    for role, outcome in added_outcomes:
        add("endpoint_added", endpoint_paths(role, role), None, {"role": role, "outcome": outcome})

    intervention_path = "/protocolSection/armsInterventionsModule/interventions"
    pairs, removed_interventions, added_interventions = unique_intervention_pairs(
        object_list(pointer_value(before_study, intervention_path)),
        object_list(pointer_value(after_study, intervention_path)),
    )
    for before_intervention, after_intervention in pairs:
        if canonical_json_bytes(before_intervention) != canonical_json_bytes(after_intervention):
            add("intervention_changed", [intervention_path], before_intervention, after_intervention)
    for intervention in removed_interventions:
        add("intervention_removed", [intervention_path], intervention, None)
    for intervention in added_interventions:
        add("intervention_added", [intervention_path], None, intervention)
    return descriptors


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


def _history_study_from_payload(
    payload: Mapping[str, Any],
    *,
    nct_id: Any,
    path: str,
) -> tuple[Mapping[str, Any] | None, list[ValidationIssue]]:
    """Resolve the one CT.gov study and prove its NCT identity."""

    issues: list[ValidationIssue] = []
    study = payload.get("study")
    source_nct = (
        _resolve_json_pointer(study, "/protocolSection/identificationModule/nctId")
        if isinstance(study, Mapping)
        else _MISSING
    )
    if not isinstance(study, Mapping) or source_nct != nct_id:
        issues.append(
            ValidationIssue(
                path,
                "history_receipt.source_identity",
                "raw history response must contain the requested ClinicalTrials.gov study NCT ID",
            )
        )
        return None, issues
    return study, issues


def validate_ctgov_history_receipt_against_raw_response(
    receipt: Mapping[str, Any],
    raw_response_body: bytes | bytearray | memoryview,
    *,
    repo_root: Path | str | None = None,
) -> Mapping[str, Any]:
    """Replay one history receipt against its exact archived source bytes."""

    registry = ContractRegistry(repo_root)
    registry.validate(_CTGOV_HISTORY_RECEIPT_CONTRACT_ID, receipt)
    issues: list[ValidationIssue] = []
    if not isinstance(raw_response_body, (bytes, bytearray, memoryview)):
        raise ContractValidationError(
            _CTGOV_HISTORY_RECEIPT_CONTRACT_ID,
            (
                ValidationIssue(
                    "$.response.raw_response_object_key",
                    "history_receipt.raw_response_type",
                    "raw history evidence must be supplied as exact bytes",
                ),
            ),
        )
    raw_bytes = bytes(raw_response_body)
    response = receipt.get("response")
    response = response if isinstance(response, Mapping) else {}
    actual_hash = hashlib.sha256(raw_bytes).hexdigest()
    if response.get("exact_response_sha256") != actual_hash:
        issues.append(
            ValidationIssue(
                "$.response.exact_response_sha256",
                "history_receipt.raw_response_hash",
                "receipt response hash must equal the exact archived bytes",
            )
        )
    if response.get("byte_count") != len(raw_bytes):
        issues.append(
            ValidationIssue(
                "$.response.byte_count",
                "history_receipt.raw_response_length",
                "receipt byte count must equal the exact archived bytes",
            )
        )
    object_key = response.get("raw_response_object_key")
    if not isinstance(object_key, str) or not object_key.endswith(f"/{actual_hash}.json"):
        issues.append(
            ValidationIssue(
                "$.response.raw_response_object_key",
                "history_receipt.raw_response_object_identity",
                "raw response object key must terminate with the exact archived response SHA-256",
            )
        )
    headers = response.get("headers")
    content_length = headers.get("content-length") if isinstance(headers, Mapping) else None
    if content_length is not None and (
        not isinstance(content_length, str)
        or re.fullmatch(r"[0-9]+", content_length) is None
        or int(content_length) != len(raw_bytes)
    ):
        issues.append(
            ValidationIssue(
                "$.response.headers.content-length",
                "history_receipt.raw_response_length",
                "content-length must equal the archived response byte count when retained",
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
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        issues.append(
            ValidationIssue(
                "$.response.raw_response_object_key",
                "history_receipt.raw_response_json",
                f"raw history response must be unambiguous UTF-8 JSON: {exc}",
            )
        )
    if parsed is not _MISSING and not isinstance(parsed, Mapping):
        issues.append(
            ValidationIssue(
                "$.response.raw_response_object_key",
                "history_receipt.raw_response_shape",
                "raw history response must be a JSON object",
            )
        )
    if isinstance(parsed, Mapping):
        _study, identity_issues = _history_study_from_payload(
            parsed,
            nct_id=receipt.get("nct_id"),
            path="$.response.raw_response_object_key",
        )
        issues.extend(identity_issues)
        resource_kind = receipt.get("resource_kind")
        source_version = receipt.get("source_version")
        if resource_kind == "history_version":
            raw_version = parsed.get("studyVersion")
            if isinstance(raw_version, bool) or raw_version != source_version:
                issues.append(
                    ValidationIssue(
                        "$.source_version",
                        "history_receipt.version_binding",
                        "raw historical response studyVersion must equal the receipted source version",
                    )
                )
        if resource_kind == "history_index" and not isinstance(parsed.get("history"), Mapping):
            issues.append(
                ValidationIssue(
                    "$.response.raw_response_object_key",
                    "history_receipt.index_shape",
                    "raw history-index response must contain a history object",
                )
            )
    if issues:
        raise ContractValidationError(_CTGOV_HISTORY_RECEIPT_CONTRACT_ID, issues)
    assert isinstance(parsed, Mapping)
    return parsed


def _history_manifest_from_index_payload(
    payload: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[ValidationIssue]]:
    """Replay the exact bounded version manifest from a raw history index."""

    issues: list[ValidationIssue] = []
    history = payload.get("history")
    changes = history.get("changes") if isinstance(history, Mapping) else None
    if not isinstance(changes, list) or not changes:
        return [], [
            ValidationIssue(
                "$.history.changes",
                "history_run.index_manifest",
                "raw history index must contain a non-empty changes list",
            )
        ]
    manifest: list[dict[str, Any]] = []
    seen_versions: set[int] = set()
    for index, change in enumerate(changes):
        path = f"$.history.changes[{index}]"
        if not isinstance(change, Mapping):
            issues.append(
                ValidationIssue(path, "history_run.index_manifest", "history change must be an object")
            )
            continue
        source_version = change.get("version")
        if isinstance(source_version, bool) or not isinstance(source_version, int) or source_version < 0:
            issues.append(
                ValidationIssue(f"{path}.version", "history_run.index_manifest", "history version must be a non-negative integer")
            )
            continue
        if source_version in seen_versions:
            issues.append(
                ValidationIssue(f"{path}.version", "history_run.index_manifest", "history versions must be unique")
            )
            continue
        seen_versions.add(source_version)
        submitted = change.get("date")
        qc_at = change.get("lastUpdateSubmitQcDate")
        labels = change.get("moduleLabels")
        valid_date = isinstance(submitted, str)
        if valid_date:
            try:
                date.fromisoformat(submitted)
            except ValueError:
                valid_date = False
        valid_qc = qc_at is None or isinstance(qc_at, str)
        if isinstance(qc_at, str):
            try:
                date.fromisoformat(qc_at)
            except ValueError:
                valid_qc = False
        if not valid_date or not valid_qc:
            issues.append(
                ValidationIssue(path, "history_run.index_manifest", "history dates must be ISO calendar dates")
            )
            continue
        if not isinstance(labels, list) or any(
            not isinstance(label, str) or not label.strip() for label in labels
        ) or len(labels) != len(set(labels)):
            issues.append(
                ValidationIssue(f"{path}.moduleLabels", "history_run.index_manifest", "module labels must be unique non-empty strings")
            )
            continue
        if any(not isinstance(change.get(field), str) or not change[field] for field in ("status", "studyType")):
            issues.append(
                ValidationIssue(path, "history_run.index_manifest", "history change must retain status and studyType strings")
            )
            continue
        manifest.append(
            {
                "source_version": source_version,
                "display_version": source_version + 1,
                "source_submitted_at": submitted,
                "source_last_update_submit_qc_at": qc_at,
                "module_labels": list(labels),
            }
        )
    if [entry["source_version"] for entry in manifest] != list(range(len(manifest))):
        issues.append(
            ValidationIssue(
                "$.history.changes",
                "history_run.index_manifest",
                "history versions must be contiguous and zero-based in source order",
            )
        )
    return manifest, issues


def validate_ctgov_history_run_against_receipts(
    run: Mapping[str, Any],
    index_receipt: Mapping[str, Any],
    index_post_receipt: Mapping[str, Any],
    version_receipts: Sequence[Mapping[str, Any]],
    *,
    raw_bodies_by_receipt: Mapping[str, bytes | bytearray | memoryview],
    repo_root: Path | str | None = None,
) -> None:
    """Replay a complete history run from both index captures and all raw versions."""

    registry = ContractRegistry(repo_root)
    registry.validate(_CTGOV_HISTORY_RUN_CONTRACT_ID, run)
    supplied_receipts = [index_receipt, index_post_receipt, *version_receipts]
    for receipt in supplied_receipts:
        registry.validate(_CTGOV_HISTORY_RECEIPT_CONTRACT_ID, receipt)
    receipt_ids = [receipt.get("receipt_id") for receipt in supplied_receipts]
    expected_ids = {receipt_id for receipt_id in receipt_ids if isinstance(receipt_id, str)}
    if not isinstance(raw_bodies_by_receipt, Mapping) or set(raw_bodies_by_receipt) != expected_ids:
        raise ContractValidationError(
            _CTGOV_HISTORY_RUN_CONTRACT_ID,
            (
                ValidationIssue(
                    "$.history_version_receipt_refs",
                    "history_run.raw_coverage",
                    "raw bodies must exactly cover both index receipts and every version receipt",
                ),
            ),
        )
    if len(receipt_ids) != len(expected_ids):
        raise ContractValidationError(
            _CTGOV_HISTORY_RUN_CONTRACT_ID,
            (
                ValidationIssue(
                    "$.history_index_post_receipt_ref",
                    "history_run.receipt_identity",
                    "all complete-run receipts, including pre/post indexes, must be distinct",
                ),
            ),
        )
    parsed_by_receipt = {
        receipt["receipt_id"]: validate_ctgov_history_receipt_against_raw_response(
            receipt,
            raw_bodies_by_receipt[receipt["receipt_id"]],
            repo_root=repo_root,
        )
        for receipt in supplied_receipts
    }
    issues: list[ValidationIssue] = []
    nct_id = run.get("nct_id")
    if run.get("run_state") != "complete" or run.get("completeness_state") != "history_complete":
        issues.append(
            ValidationIssue(
                "$.run_state",
                "history_run.complete",
                "this validator accepts only complete history runs",
            )
        )
    for field, receipt, expected_kind in (
        ("history_index_receipt_ref", index_receipt, "history_index"),
        ("history_index_post_receipt_ref", index_post_receipt, "history_index"),
    ):
        if run.get(field) != receipt.get("receipt_id"):
            issues.append(
                ValidationIssue(f"$.{field}", "history_run.receipt_binding", f"{field} must match its supplied index receipt")
            )
        if receipt.get("resource_kind") != expected_kind:
            issues.append(
                ValidationIssue(f"$.{field}", "history_run.index_receipt", "both supplied index receipts must be history-index receipts")
            )
        if receipt.get("run_id") != run.get("run_id") or receipt.get("nct_id") != nct_id:
            issues.append(
                ValidationIssue(f"$.{field}", "history_run.receipt_binding", "index receipt must belong to this complete run and NCT ID")
            )
    if index_receipt.get("receipt_id") == index_post_receipt.get("receipt_id"):
        issues.append(
            ValidationIssue(
                "$.history_index_post_receipt_ref",
                "history_run.index_receipt",
                "pre-index and post-index receipts must be distinct captures",
            )
        )
    expected_refs = [receipt.get("receipt_id") for receipt in version_receipts]
    if run.get("history_version_receipt_refs") != expected_refs:
        issues.append(
            ValidationIssue(
                "$.history_version_receipt_refs",
                "history_run.receipt_binding",
                "version receipt references must exactly match the ordered supplied receipts",
            )
        )
    for index, receipt in enumerate(version_receipts):
        if receipt.get("resource_kind") != "history_version":
            issues.append(
                ValidationIssue(f"$.history_version_receipt_refs[{index}]", "history_run.version_receipt_kind", "every version receipt must identify a historical study version")
            )
        if receipt.get("run_id") != run.get("run_id") or receipt.get("nct_id") != nct_id:
            issues.append(
                ValidationIssue(f"$.history_version_receipt_refs[{index}]", "history_run.receipt_binding", "version receipt must belong to this complete run and NCT ID")
            )
    run_started = _parse_temporal(run.get("started_at"))
    run_finished = _parse_temporal(run.get("finished_at"))

    def receipt_time(receipt: Mapping[str, Any], field: str) -> datetime | None:
        if field == "received_at":
            response = receipt.get("response")
            value = response.get("received_at") if isinstance(response, Mapping) else None
        else:
            value = receipt.get(field)
        return _parse_temporal(value)

    if run_started is not None and run_finished is not None:
        receipt_times: dict[str, tuple[datetime | None, datetime | None]] = {}
        for receipt in supplied_receipts:
            receipt_id = receipt.get("receipt_id")
            if not isinstance(receipt_id, str):
                continue
            received_at = receipt_time(receipt, "received_at")
            transaction_from = receipt_time(receipt, "transaction_from")
            receipt_times[receipt_id] = (received_at, transaction_from)
            for field, value in (
                ("response.received_at", received_at),
                ("transaction_from", transaction_from),
            ):
                if value is None or not run_started <= value <= run_finished:
                    issues.append(
                        ValidationIssue(
                            "$.history_index_post_receipt_ref",
                            "history_run.receipt_chronology",
                            f"every receipt {field} must fall within the complete run interval",
                        )
                    )
        chronology_receipts = [index_receipt, *version_receipts, index_post_receipt]
        for field_index in (0, 1):
            chronology_values = [
                receipt_times.get(receipt.get("receipt_id"), (None, None))[field_index]
                for receipt in chronology_receipts
            ]
            if any(value is None for value in chronology_values) or any(
                earlier >= later
                for earlier, later in zip(chronology_values, chronology_values[1:])
                if earlier is not None and later is not None
            ):
                issues.append(
                    ValidationIssue(
                        "$.history_index_post_receipt_ref",
                        "history_run.receipt_chronology",
                        "pre-index, ordered version receipts, and post-index receipt must be strictly increasing in receipt and transaction time",
                    )
                )
        pre_received = receipt_times.get(index_receipt.get("receipt_id"), (None, None))[0]
        post_transaction = receipt_times.get(index_post_receipt.get("receipt_id"), (None, None))[1]
        run_transaction = _parse_temporal(run.get("transaction_from"))
        if (
            pre_received is None
            or post_transaction is None
            or run_transaction is None
            or not run_started < pre_received
            or post_transaction > run_finished
            or not run_finished < run_transaction
        ):
            issues.append(
                ValidationIssue(
                    "$.history_index_post_receipt_ref",
                    "history_run.receipt_chronology",
                    "complete run timing must strictly surround collection and advance its transaction time after the terminal receipt",
                )
            )
        for receipt_id, (received_at, transaction_from) in receipt_times.items():
            if received_at is None or transaction_from is None or received_at >= transaction_from:
                issues.append(
                    ValidationIssue(
                        "$.history_version_receipt_refs",
                        "history_run.receipt_chronology",
                        f"receipt {receipt_id} must record receipt time before its transaction time",
                    )
                )
    pre_manifest, pre_issues = _history_manifest_from_index_payload(
        parsed_by_receipt[index_receipt["receipt_id"]]
    )
    post_manifest, post_issues = _history_manifest_from_index_payload(
        parsed_by_receipt[index_post_receipt["receipt_id"]]
    )
    issues.extend(pre_issues)
    issues.extend(post_issues)
    if pre_manifest != post_manifest:
        issues.append(
            ValidationIssue(
                "$.history_index_post_receipt_ref",
                "history_run.index_roundtrip",
                "pre-index and post-index raw responses must replay to identical version manifests",
            )
        )
    if run.get("version_manifest") != pre_manifest:
        issues.append(
            ValidationIssue(
                "$.version_manifest",
                "history_run.index_manifest",
                "run version manifest must equal the replayed pre/post index manifest",
            )
        )
    if [receipt.get("source_version") for receipt in version_receipts] != [
        entry["source_version"] for entry in pre_manifest
    ]:
        issues.append(
            ValidationIssue(
                "$.history_version_receipt_refs",
                "history_run.version_receipt_order",
                "ordered version receipts must cover every replayed source version exactly once",
            )
        )
    if issues:
        raise ContractValidationError(_CTGOV_HISTORY_RUN_CONTRACT_ID, issues)


def validate_trial_history_snapshot_against_evidence(
    snapshot: Mapping[str, Any],
    run: Mapping[str, Any],
    index_receipt: Mapping[str, Any],
    index_post_receipt: Mapping[str, Any],
    version_receipt: Mapping[str, Any],
    *,
    all_version_receipts: Sequence[Mapping[str, Any]],
    raw_bodies_by_receipt: Mapping[str, bytes | bytearray | memoryview],
    repo_root: Path | str | None = None,
) -> None:
    """Bind one snapshot to the exact raw version response inside a complete run."""

    if not any(
        receipt.get("receipt_id") == version_receipt.get("receipt_id")
        for receipt in all_version_receipts
    ):
        raise ContractValidationError(
            _TRIAL_HISTORY_SOURCE_SNAPSHOT_CONTRACT_ID,
            (
                ValidationIssue(
                    "$.history_version_receipt_ref",
                    "history_snapshot.evidence_binding",
                    "the supplied version receipt must be included in complete run evidence",
                ),
            ),
        )
    validate_ctgov_history_run_against_receipts(
        run,
        index_receipt,
        index_post_receipt,
        all_version_receipts,
        raw_bodies_by_receipt=raw_bodies_by_receipt,
        repo_root=repo_root,
    )
    registry = ContractRegistry(repo_root)
    registry.validate(_TRIAL_HISTORY_SOURCE_SNAPSHOT_CONTRACT_ID, snapshot)
    raw_payload = validate_ctgov_history_receipt_against_raw_response(
        version_receipt,
        raw_bodies_by_receipt[version_receipt["receipt_id"]],
        repo_root=repo_root,
    )
    raw_study, raw_issues = _history_study_from_payload(
        raw_payload,
        nct_id=run.get("nct_id"),
        path="$.canonical_study",
    )
    issues: list[ValidationIssue] = list(raw_issues)
    manifest = run.get("version_manifest")
    source_version = snapshot.get("source_version")
    matching_manifest = next(
        (
            entry
            for entry in manifest
            if isinstance(entry, Mapping)
            and entry.get("source_version") == source_version
        ),
        None,
    ) if (
        isinstance(manifest, list)
        and isinstance(source_version, int)
        and not isinstance(source_version, bool)
    ) else None
    bindings = (
        ("nct_id", run.get("nct_id")),
        ("run_ref", run.get("run_id")),
        ("history_index_receipt_ref", index_receipt.get("receipt_id")),
        ("history_version_receipt_ref", version_receipt.get("receipt_id")),
        ("source_version", version_receipt.get("source_version")),
        ("retrieved_at", version_receipt.get("response", {}).get("received_at")),
    )
    for field, expected in bindings:
        if snapshot.get(field) != expected:
            issues.append(
                ValidationIssue(f"$.{field}", "history_snapshot.evidence_binding", f"{field} must match the complete history run evidence")
            )
    snapshot_seed = canonical_json_sha256(
        {
            "nct_id": run.get("nct_id"),
            "source_version": source_version,
            "canonical_content_sha256": snapshot.get("canonical_content_sha256"),
            "run_ref": run.get("run_id"),
        }
    )
    expected_snapshot_id = (
        f"ctgov_history_snapshot_{run.get('nct_id')}_{snapshot_seed[:24]}"
    )
    if snapshot.get("source_snapshot_id") != expected_snapshot_id:
        issues.append(
            ValidationIssue(
                "$.source_snapshot_id",
                "history_snapshot.deterministic_id",
                "source snapshot ID must be derived from its run-bound exact source content",
            )
        )
    if raw_study is not None and not _canonical_json_equal(raw_study, snapshot.get("canonical_study")):
        issues.append(
            ValidationIssue(
                "$.canonical_study",
                "history_snapshot.raw_replay",
                "canonical study must equal the study in the exact receipted version response",
            )
        )
    if isinstance(matching_manifest, Mapping):
        for field in ("display_version", "source_submitted_at", "source_last_update_submit_qc_at"):
            if snapshot.get(field) != matching_manifest.get(field):
                issues.append(
                    ValidationIssue(f"$.{field}", "history_snapshot.manifest_binding", f"{field} must match the source history manifest entry")
                )
    else:
        issues.append(
            ValidationIssue("$.source_version", "history_snapshot.manifest_binding", "source version must resolve to a manifest entry")
        )
    if issues:
        raise ContractValidationError(_TRIAL_HISTORY_SOURCE_SNAPSHOT_CONTRACT_ID, issues)


def validate_trial_history_diff_against_snapshots(
    diff: Mapping[str, Any],
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    *,
    repo_root: Path | str | None = None,
) -> None:
    """Replay and bind a historical exact diff from immutable source snapshots."""

    registry = ContractRegistry(repo_root)
    registry.validate(_TRIAL_HISTORY_DIFF_CONTRACT_ID, diff)
    registry.validate(_TRIAL_HISTORY_SOURCE_SNAPSHOT_CONTRACT_ID, before_snapshot)
    registry.validate(_TRIAL_HISTORY_SOURCE_SNAPSHOT_CONTRACT_ID, after_snapshot)
    issues: list[ValidationIssue] = []
    bindings = (
        ("nct_id", before_snapshot.get("nct_id")),
        ("before_source_snapshot_ref", before_snapshot.get("source_snapshot_id")),
        ("after_source_snapshot_ref", after_snapshot.get("source_snapshot_id")),
        ("before_source_version", before_snapshot.get("source_version")),
        ("after_source_version", after_snapshot.get("source_version")),
        ("before_content_sha256", before_snapshot.get("canonical_content_sha256")),
        ("after_content_sha256", after_snapshot.get("canonical_content_sha256")),
        ("retrieved_at", after_snapshot.get("retrieved_at")),
        ("transaction_from", after_snapshot.get("transaction_from")),
    )
    for field, expected in bindings:
        if diff.get(field) != expected:
            issues.append(
                ValidationIssue(
                    f"$.{field}",
                    "history_diff.snapshot_binding",
                    f"{field} must match the referenced historical source snapshot",
                )
            )
    if after_snapshot.get("nct_id") != before_snapshot.get("nct_id"):
        issues.append(
            ValidationIssue(
                "$.after_source_snapshot_ref",
                "history_diff.identity",
                "both historical source snapshots must identify the same NCT ID",
            )
        )
    if diff.get("source_record_refs") != [
        before_snapshot.get("source_record_ref"), after_snapshot.get("source_record_ref")
    ]:
        issues.append(
            ValidationIssue(
                "$.source_record_refs",
                "history_diff.snapshot_binding",
                "source record references must preserve before/after history order",
            )
        )
    diff_seed = canonical_json_sha256(
        {
            "before_source_snapshot_ref": before_snapshot.get("source_snapshot_id"),
            "after_source_snapshot_ref": after_snapshot.get("source_snapshot_id"),
            "before_content_sha256": before_snapshot.get("canonical_content_sha256"),
            "after_content_sha256": after_snapshot.get("canonical_content_sha256"),
        }
    )
    expected_diff_id = f"trial_history_diff_{before_snapshot.get('nct_id')}_{diff_seed[:24]}"
    if diff.get("diff_id") != expected_diff_id:
        issues.append(
            ValidationIssue(
                "$.diff_id",
                "history_diff.deterministic_id",
                "diff ID must be derived from its exact before/after snapshot bindings",
            )
        )
    expected_operations = exact_history_json_diff(
        before_snapshot.get("canonical_study"), after_snapshot.get("canonical_study")
    )
    if diff.get("operations") != expected_operations:
        issues.append(
            ValidationIssue(
                "$.operations",
                "history_diff.exactness",
                "operations must equal the deterministic diff of historical source snapshots",
            )
        )
    if issues:
        raise ContractValidationError(_TRIAL_HISTORY_DIFF_CONTRACT_ID, issues)


def validate_trial_registry_change_fact_against_diff(
    fact: Mapping[str, Any],
    diff: Mapping[str, Any],
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
    *,
    repo_root: Path | str | None = None,
) -> None:
    """Ensure a semantic fact remains a decision-inert view of an exact diff."""

    validate_trial_history_diff_against_snapshots(
        diff, before_snapshot, after_snapshot, repo_root=repo_root
    )
    registry = ContractRegistry(repo_root)
    registry.validate(_TRIAL_REGISTRY_CHANGE_FACT_CONTRACT_ID, fact)
    issues: list[ValidationIssue] = []
    bindings = (
        ("nct_id", diff.get("nct_id")),
        ("diff_ref", diff.get("diff_id")),
        ("before_source_snapshot_ref", diff.get("before_source_snapshot_ref")),
        ("after_source_snapshot_ref", diff.get("after_source_snapshot_ref")),
        ("before_source_version", diff.get("before_source_version")),
        ("after_source_version", diff.get("after_source_version")),
        ("transaction_from", after_snapshot.get("transaction_from")),
    )
    for field, expected in bindings:
        if fact.get(field) != expected:
            issues.append(
                ValidationIssue(
                    f"$.{field}",
                    "history_change_fact.diff_binding",
                    f"{field} must match the exact historical diff",
                )
            )
    fact_seed = canonical_json_sha256(
        {
            "diff_ref": diff.get("diff_id"),
            "kind": fact.get("kind"),
            "source_json_paths": fact.get("source_json_paths"),
            "before_value": fact.get("before_value"),
            "after_value": fact.get("after_value"),
        }
    )
    expected_fact_id = f"trial_registry_change_{diff.get('nct_id')}_{fact_seed[:24]}"
    if fact.get("change_fact_id") != expected_fact_id:
        issues.append(
            ValidationIssue(
                "$.change_fact_id",
                "history_change_fact.deterministic_id",
                "change fact ID must be derived from its exact diff projection",
            )
        )
    operation_paths = [
        operation.get("json_path")
        for operation in diff.get("operations", ())
        if isinstance(operation, Mapping) and isinstance(operation.get("json_path"), str)
    ]
    for path in fact.get("source_json_paths", ()):
        if not isinstance(path, str):
            continue
        supported = any(
            path == operation_path
            or path.startswith(operation_path + "/")
            or operation_path.startswith(path + "/")
            for operation_path in operation_paths
        )
        if not supported:
            issues.append(
                ValidationIssue(
                    "$.source_json_paths",
                    "history_change_fact.exact_support",
                    "every semantic source path must be supported by an exact diff operation",
                )
            )
            break
    before_study = before_snapshot.get("canonical_study")
    after_study = after_snapshot.get("canonical_study")
    if isinstance(before_study, Mapping) and isinstance(after_study, Mapping):
        expected_descriptors = derive_trial_registry_change_descriptors(
            before_study, after_study
        )
        fact_matches_exact_projection = any(
            descriptor["kind"] == fact.get("kind")
            and descriptor["source_json_paths"] == fact.get("source_json_paths")
            and _canonical_json_equal(descriptor["before_value"], fact.get("before_value"))
            and _canonical_json_equal(descriptor["after_value"], fact.get("after_value"))
            for descriptor in expected_descriptors
        )
        if not fact_matches_exact_projection:
            issues.append(
                ValidationIssue(
                    "$.kind",
                    "history_change_fact.semantic_replay",
                    "fact kind, source paths, and before/after values must equal a deterministic projection of the exact source snapshots",
                )
            )
    else:
        issues.append(
            ValidationIssue(
                "$.before_source_snapshot_ref",
                "history_change_fact.semantic_replay",
                "change facts require canonical before and after source studies for deterministic replay",
            )
        )
    fact_transaction = _parse_temporal(fact.get("transaction_from"))
    diff_transaction = _parse_temporal(diff.get("transaction_from"))
    if fact_transaction is not None and diff_transaction is not None and fact_transaction < diff_transaction:
        issues.append(
            ValidationIssue(
                "$.transaction_from",
                "history_change_fact.transaction",
                "change fact transaction time cannot precede its exact diff",
            )
        )
    if issues:
        raise ContractValidationError(_TRIAL_REGISTRY_CHANGE_FACT_CONTRACT_ID, issues)


def validate_trial_history_read_model(
    model: Mapping[str, Any],
    snapshots: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    *,
    repo_root: Path | str | None = None,
) -> None:
    """Bind the public-safe history model to internal snapshots and facts."""

    registry = ContractRegistry(repo_root)
    registry.validate(_TRIAL_HISTORY_READ_MODEL_CONTRACT_ID, model)
    for snapshot in snapshots:
        registry.validate(_TRIAL_HISTORY_SOURCE_SNAPSHOT_CONTRACT_ID, snapshot)
    for fact in facts:
        registry.validate(_TRIAL_REGISTRY_CHANGE_FACT_CONTRACT_ID, fact)
    ordered_snapshots = sorted(snapshots, key=lambda item: item["source_version"])
    ordered_facts = sorted(
        facts,
        key=lambda item: (
            item["after_source_version"], item["kind"], item["change_fact_id"]
        ),
    )
    issues: list[ValidationIssue] = []
    if model.get("available") is True and not ordered_snapshots:
        issues.append(
            ValidationIssue(
                "$.available",
                "history_read_model.snapshot_binding",
                "an available public history model requires historical source snapshots",
            )
        )
    if model.get("available") is False and (ordered_snapshots or ordered_facts):
        issues.append(
            ValidationIssue(
                "$.available",
                "history_read_model.unavailable_binding",
                "an unavailable public history model cannot carry snapshots or change facts",
            )
        )
    if ordered_snapshots:
        nct_id = ordered_snapshots[0].get("nct_id")
        if model.get("nct_id") != nct_id or any(
            snapshot.get("nct_id") != nct_id for snapshot in ordered_snapshots
        ):
            issues.append(
                ValidationIssue(
                    "$.nct_id",
                    "history_read_model.identity",
                    "public history model and all snapshots must identify one NCT ID",
                )
            )
        source_versions = [snapshot.get("source_version") for snapshot in ordered_snapshots]
        display_versions = [snapshot.get("display_version") for snapshot in ordered_snapshots]
        if source_versions != list(range(len(ordered_snapshots))) or display_versions != list(
            range(1, len(ordered_snapshots) + 1)
        ):
            issues.append(
                ValidationIssue(
                    "$.versions",
                    "history_read_model.snapshot_sequence",
                    "available public history models require the complete zero-based source version chain",
                )
            )
        expected_versions = [
            {
                "display_version": snapshot["display_version"],
                "source_submitted_at": snapshot["source_submitted_at"],
                "url": snapshot["source_uri"],
            }
            for snapshot in ordered_snapshots
        ]
        if model.get("versions") != expected_versions:
            issues.append(
                ValidationIssue(
                    "$.versions",
                    "history_read_model.snapshot_binding",
                    "public versions must be a private-provenance-free projection of source snapshots",
                )
            )
        if model.get("retrieved_at") != ordered_snapshots[-1].get("retrieved_at"):
            issues.append(
                ValidationIssue(
                    "$.retrieved_at",
                    "history_read_model.snapshot_binding",
                    "public history retrieval time must match the latest source snapshot",
                )
            )
    expected_fact_descriptors: list[dict[str, Any]] = []
    for before_snapshot, after_snapshot in zip(
        ordered_snapshots, ordered_snapshots[1:]
    ):
        before_version = before_snapshot.get("source_version")
        after_version = after_snapshot.get("source_version")
        if after_version != before_version + 1:
            issues.append(
                ValidationIssue(
                    "$.versions",
                    "history_read_model.snapshot_sequence",
                    "public history facts require every adjacent source snapshot version",
                )
            )
            continue
        before_study = before_snapshot.get("canonical_study")
        after_study = after_snapshot.get("canonical_study")
        if not isinstance(before_study, Mapping) or not isinstance(after_study, Mapping):
            issues.append(
                ValidationIssue(
                    "$.versions",
                    "history_read_model.fact_completeness",
                    "public history facts require canonical studies for every adjacent snapshot pair",
                )
            )
            continue
        diff_seed = canonical_json_sha256(
            {
                "before_source_snapshot_ref": before_snapshot.get("source_snapshot_id"),
                "after_source_snapshot_ref": after_snapshot.get("source_snapshot_id"),
                "before_content_sha256": before_snapshot.get("canonical_content_sha256"),
                "after_content_sha256": after_snapshot.get("canonical_content_sha256"),
            }
        )
        expected_diff_ref = f"trial_history_diff_{before_snapshot.get('nct_id')}_{diff_seed[:24]}"
        for descriptor in derive_trial_registry_change_descriptors(
            before_study, after_study
        ):
            expected_fact_descriptors.append(
                {
                    "nct_id": before_snapshot.get("nct_id"),
                    "diff_ref": expected_diff_ref,
                    "before_source_snapshot_ref": before_snapshot.get("source_snapshot_id"),
                    "after_source_snapshot_ref": after_snapshot.get("source_snapshot_id"),
                    "before_source_version": before_version,
                    "after_source_version": after_version,
                    "kind": descriptor["kind"],
                    "source_json_paths": descriptor["source_json_paths"],
                    "before_value": descriptor["before_value"],
                    "after_value": descriptor["after_value"],
                    "transaction_from": after_snapshot.get("transaction_from"),
                }
            )
    actual_fact_descriptors = [
        {
            "nct_id": fact.get("nct_id"),
            "diff_ref": fact.get("diff_ref"),
            "before_source_snapshot_ref": fact.get("before_source_snapshot_ref"),
            "after_source_snapshot_ref": fact.get("after_source_snapshot_ref"),
            "before_source_version": fact.get("before_source_version"),
            "after_source_version": fact.get("after_source_version"),
            "kind": fact.get("kind"),
            "source_json_paths": fact.get("source_json_paths"),
            "before_value": fact.get("before_value"),
            "after_value": fact.get("after_value"),
            "transaction_from": fact.get("transaction_from"),
        }
        for fact in ordered_facts
    ]
    if Counter(map(canonical_json_bytes, actual_fact_descriptors)) != Counter(
        map(canonical_json_bytes, expected_fact_descriptors)
    ):
        issues.append(
            ValidationIssue(
                "$.changes",
                "history_read_model.fact_completeness",
                "facts must be the exact non-duplicated deterministic projection of every adjacent source snapshot pair",
            )
        )
    expected_changes = [
        {
            "kind": fact["kind"],
            "before_display_version": fact["before_source_version"] + 1,
            "after_display_version": fact["after_source_version"] + 1,
            "before_value": fact["before_value"],
            "after_value": fact["after_value"],
        }
        for fact in ordered_facts
    ]
    if model.get("changes") != expected_changes:
        issues.append(
            ValidationIssue(
                "$.changes",
                "history_read_model.fact_binding",
                "public changes must be a private-provenance-free projection of change facts",
            )
        )
    if issues:
        raise ContractValidationError(_TRIAL_HISTORY_READ_MODEL_CONTRACT_ID, issues)
