"""Hermetic validation for the dark BioCatalyst B1S1 fixed cohort.

This module deliberately describes an immutable membership boundary only. It
does not collect, connect to a source, persist an artifact, expose a route, or
start a process. Candidate admission intersects already-declared membership;
it never discovers or adds members.
"""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping, Sequence

import yaml

from engine.sector_intelligence.contracts import (
    ContractError,
    ContractRegistry,
    ContractValidationError,
    ValidationIssue,
    canonical_json_bytes,
    canonical_json_sha256,
)


FIXED_COHORT_CONTRACT_ID = "ctgov_fixed_cohort.v1"
FIXED_COHORT_SOURCE_ID = "clinicaltrials_gov_v2"
FIXED_COHORT_CONTROL_REGISTRATION = "b1s1_fixed_cohort_control"
FIXED_COHORT_REGISTRY_REF = "config/biocatalyst_sources.yml"
FIXED_COHORT_HASH_SCOPE = "canonical_payload_excluding_cohort_payload_sha256"
FIXED_COHORT_MAX_NCT_IDS = 25
FIXED_COHORT_MAX_QUERY_BYTES = 299

# These caps deliberately fit a tiny, reviewable fixture instead of a general
# purpose document reader. Exact limits are public to make boundary tests clear.
FIXTURE_MAX_BYTES = 16 * 1024
FIXTURE_MAX_JSON_DEPTH = 12
FIXTURE_MAX_JSON_NODES = 256
FIXTURE_MAX_JSON_CONTAINER_ITEMS = 32
FIXTURE_MAX_JSON_STRING_BYTES = 512
FIXTURE_MAX_JSON_NUMBER_TOKEN_BYTES = 32
REGISTRY_MAX_BYTES = 64 * 1024
ADMISSION_SNAPSHOT_MAX_BYTES = 8 * 1024

_NCT_ID_RE = re.compile(r"^NCT[0-9]{8}$", re.ASCII)
_FIXTURE_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$", re.ASCII)
_PROHIBITED = (
    "dynamic_cohort_expansion", "live_ingestion", "identity_mapping", "scoring",
    "prediction", "prophet_authority", "neural_web_authority", "ranking",
    "sizing", "alerts",
)
_DARK_CONTROL = {
    "state": "validation_only_fixed_cohort_control",
    "live_network_allowed": False,
    "worker_mode_available": False,
    "storage_publication_allowed": False,
    "public_projection_allowed": False,
    "api_exposure_allowed": False,
    "default_enabled": False,
    "consumers": [],
    "authority": "facts_and_context_only",
}
_REGISTRATION_EXPECTED = {
    "source_id": FIXED_COHORT_SOURCE_ID,
    "implementation_state": "validation_only_fixed_cohort_control",
    "universe_mode": "fixed_explicit_nct_cohort",
    "membership_authority": "fixed_cohort_only",
    "candidate_admission_policy": "candidate_subset_only",
    "minimum_nct_ids": 1,
    "maximum_nct_ids": FIXED_COHORT_MAX_NCT_IDS,
    "maximum_query_bytes": FIXED_COHORT_MAX_QUERY_BYTES,
    "default_enabled": False,
    "live_network_allowed": False,
    "worker_mode_available": False,
    "public_projection_allowed": False,
    "api_exposure_allowed": False,
    "storage_publication_allowed": False,
    "consumers": [],
    "authority": "facts_and_context_only",
    "allowed_contracts": [FIXED_COHORT_CONTRACT_ID],
    "prohibited_claims": list(_PROHIBITED),
    "prohibited_uses": list(_PROHIBITED),
}


class FixedCohortFixtureError(ContractError):
    """A fixture path or its bounded canonical JSON bytes are unsafe."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = tuple(sorted(set(issues)))
        super().__init__("; ".join(str(issue) for issue in self.issues))


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _repo_root(repo_root: Path | str | None) -> Path:
    return Path(repo_root).resolve() if repo_root is not None else _default_repo_root()


def _canonical_nct_ids(nct_ids: Sequence[str]) -> tuple[str, ...]:
    if type(nct_ids) not in (list, tuple):
        raise ValueError("nct_ids must be a sequence of NCT identifiers")
    if not 1 <= len(nct_ids) <= FIXED_COHORT_MAX_NCT_IDS:
        raise ValueError(f"nct_ids must contain 1-{FIXED_COHORT_MAX_NCT_IDS} identifiers")
    values = tuple(nct_ids)
    if any(not isinstance(value, str) or not _NCT_ID_RE.fullmatch(value) for value in values):
        raise ValueError("nct_ids must contain canonical ASCII NCT######## identifiers")
    if tuple(sorted(values)) != values:
        raise ValueError("nct_ids must be sorted")
    if len(set(values)) != len(values):
        raise ValueError("nct_ids must be unique")
    return values


def query_id_byte_issues(query_id: object) -> tuple[ValidationIssue, ...]:
    """Return the UTF-8 byte-limit issue for one query identifier, if any."""

    if not isinstance(query_id, str):
        return (_issue("$.query_id", "fixed_cohort.query_type", "query_id must be a string"),)
    if len(query_id) > FIXED_COHORT_MAX_QUERY_BYTES:
        return (_issue("$.query_id", "fixed_cohort.query_bytes", f"query_id must be at most {FIXED_COHORT_MAX_QUERY_BYTES} UTF-8 bytes"),)
    try:
        byte_count = len(query_id.encode("utf-8"))
    except UnicodeEncodeError:
        return (_issue("$.query_id", "fixed_cohort.query_utf8", "query_id must encode as UTF-8"),)
    if byte_count > FIXED_COHORT_MAX_QUERY_BYTES:
        return (_issue("$.query_id", "fixed_cohort.query_bytes", f"query_id must be at most {FIXED_COHORT_MAX_QUERY_BYTES} UTF-8 bytes"),)
    return ()


def fixed_cohort_identity_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return the independently hashed identity payload for a cohort document."""

    return {key: value for key, value in document.items() if key not in {"cohort_id", "cohort_payload_sha256"}}


def _registry_bytes_and_control(repo_root: Path | str | None) -> tuple[bytes, Mapping[str, Any]]:
    try:
        raw = _safe_read_relative_fixture(
            _repo_root(repo_root),
            FIXED_COHORT_REGISTRY_REF,
            max_bytes=REGISTRY_MAX_BYTES,
            label="$.source_registry_ref",
        )
        loaded = yaml.safe_load(raw.decode("utf-8"))
    except (FixedCohortFixtureError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot load fixed-cohort source registry: {exc}") from exc
    if not isinstance(loaded, Mapping):
        raise ValueError("fixed-cohort source registry must be a mapping")
    control = loaded.get(FIXED_COHORT_CONTROL_REGISTRATION)
    if not isinstance(control, Mapping):
        raise ValueError("fixed-cohort control registration is absent or malformed")
    return raw, control


def _registration_issues(document: Mapping[str, Any], *, repo_root: Path | str | None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if document.get("source_registry_ref") != FIXED_COHORT_REGISTRY_REF:
        issues.append(_issue("$.source_registry_ref", "fixed_cohort.registry_ref", "source_registry_ref must be the literal committed BioCatalyst registry path"))
    try:
        registry_bytes, registration = _registry_bytes_and_control(repo_root)
    except ValueError as exc:
        issues.append(_issue("$.source_registry_ref", "fixed_cohort.registry_unavailable", str(exc)))
        return issues
    registry_sha256 = hashlib.sha256(registry_bytes).hexdigest()
    if document.get("source_registry_sha256") != registry_sha256:
        issues.append(_issue("$.source_registry_sha256", "fixed_cohort.registry_hash", "source_registry_sha256 must bind the exact committed registry bytes"))
    for field, expected in _REGISTRATION_EXPECTED.items():
        if registration.get(field) != expected:
            issues.append(_issue(f"$.control_registration.{field}", "fixed_cohort.registration", f"registered control field {field!r} must equal {expected!r}"))

    expected_document_fields = {
        "source_id": registration.get("source_id"),
        "universe_mode": registration.get("universe_mode"),
        "membership_authority": registration.get("membership_authority"),
        "candidate_admission_policy": registration.get("candidate_admission_policy"),
        "prohibited_claims": registration.get("prohibited_claims"),
        "prohibited_uses": registration.get("prohibited_uses"),
    }
    for field, expected in expected_document_fields.items():
        if document.get(field) != expected:
            issues.append(_issue(f"$.{field}", "fixed_cohort.registration_binding", f"{field} must exactly bind the registered fixed-cohort control"))
    control = document.get("control")
    if not isinstance(control, Mapping):
        return issues
    registration_control = {
        "state": registration.get("implementation_state"),
        "live_network_allowed": registration.get("live_network_allowed"),
        "worker_mode_available": registration.get("worker_mode_available"),
        "storage_publication_allowed": registration.get("storage_publication_allowed"),
        "public_projection_allowed": registration.get("public_projection_allowed"),
        "api_exposure_allowed": registration.get("api_exposure_allowed"),
        "default_enabled": registration.get("default_enabled"),
        "consumers": registration.get("consumers"),
        "authority": registration.get("authority"),
    }
    for field, expected in registration_control.items():
        if control.get(field) != expected:
            issues.append(_issue(f"$.control.{field}", "fixed_cohort.dark_control", f"{field} must exactly bind the registered dark control"))
    return issues


def _provenance_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    provenance = document.get("provenance")
    if not isinstance(provenance, Mapping):
        return []
    if len(provenance) > 3:
        return [_issue("$.provenance", "fixed_cohort.provenance", "provenance may contain at most one exclusive arm")]
    expected_keys = {
        "hermetic_fixture": {"kind", "fixture_id"},
        "registered_control": {"kind", "control_registration", "source_registry_ref"},
    }
    kind = provenance.get("kind")
    if kind not in expected_keys or set(provenance) != expected_keys[kind]:
        return [_issue("$.provenance", "fixed_cohort.provenance", "provenance must be exactly one exclusive hermetic_fixture or registered_control arm")]
    return []


def _bounded_provenance(provenance: Mapping[str, Any]) -> dict[str, str]:
    """Copy only one small, explicit provenance arm before canonical hashing."""

    if not isinstance(provenance, Mapping) or len(provenance) > 3:
        raise ValueError("provenance must be one small exclusive provenance arm")
    kind = provenance.get("kind")
    if kind == "hermetic_fixture":
        fixture_id = provenance.get("fixture_id")
        if (
            len(provenance) != 2
            or not isinstance(fixture_id, str)
            or not _FIXTURE_ID_RE.fullmatch(fixture_id)
        ):
            raise ValueError("hermetic_fixture provenance must contain only a bounded fixture_id")
        return {"kind": kind, "fixture_id": fixture_id}
    if kind == "registered_control":
        registration = provenance.get("control_registration")
        registry_ref = provenance.get("source_registry_ref")
        if (
            len(provenance) != 3
            or registration != FIXED_COHORT_CONTROL_REGISTRATION
            or registry_ref != FIXED_COHORT_REGISTRY_REF
        ):
            raise ValueError("registered_control provenance must bind the fixed control registration")
        return {
            "kind": kind,
            "control_registration": FIXED_COHORT_CONTROL_REGISTRATION,
            "source_registry_ref": FIXED_COHORT_REGISTRY_REF,
        }
    raise ValueError("provenance kind must be hermetic_fixture or registered_control")


def fixed_cohort_contract_semantic_issues(document: Mapping[str, Any], *, repo_root: Path | str | None = None) -> list[ValidationIssue]:
    """Return deterministic semantic failures for a B1S1 cohort document."""

    if not isinstance(document, Mapping):
        return [_issue("$", "fixed_cohort.document", "fixed cohort must be a JSON object")]
    issues: list[ValidationIssue] = []
    nct_ids = document.get("nct_ids")
    if isinstance(nct_ids, list):
        if not 1 <= len(nct_ids) <= FIXED_COHORT_MAX_NCT_IDS:
            issues.append(_issue("$.nct_ids", "fixed_cohort.nct_count", "nct_ids must contain 1-25 identifiers"))
        elif not all(isinstance(value, str) for value in nct_ids):
            issues.append(_issue("$.nct_ids", "fixed_cohort.nct_id", "nct_ids must be canonical ASCII NCT######## identifiers"))
        elif any(not _NCT_ID_RE.fullmatch(value) for value in nct_ids):
            issues.append(_issue("$.nct_ids", "fixed_cohort.nct_id", "nct_ids must be canonical ASCII NCT######## identifiers"))
        else:
            if len(set(nct_ids)) != len(nct_ids):
                issues.append(_issue("$.nct_ids", "fixed_cohort.nct_unique", "nct_ids must be unique"))
            if nct_ids != sorted(nct_ids):
                issues.append(_issue("$.nct_ids", "fixed_cohort.nct_order", "nct_ids must be sorted"))
            if document.get("query_id") != ",".join(nct_ids):
                issues.append(_issue("$.query_id", "fixed_cohort.query_binding", "query_id must be the exact comma-join of nct_ids"))
    issues.extend(query_id_byte_issues(document.get("query_id")))
    issues.extend(_provenance_issues(document))
    issues.extend(_registration_issues(document, repo_root=repo_root))
    try:
        identity_sha256 = canonical_json_sha256(fixed_cohort_identity_payload(document))
        content_sha256 = canonical_json_sha256({key: value for key, value in document.items() if key != "cohort_payload_sha256"})
    except ContractError:
        return issues + [_issue("$", "fixed_cohort.canonical_payload", "fixed cohort must be finite canonical JSON")]
    if document.get("cohort_id") != f"ctgov_fixed_cohort_{identity_sha256[:24]}":
        issues.append(_issue("$.cohort_id", "fixed_cohort.identity", "cohort_id must derive from canonical identity excluding cohort_id and cohort_payload_sha256"))
    if document.get("cohort_payload_sha256") != content_sha256:
        issues.append(_issue("$.cohort_payload_sha256", "fixed_cohort.hash", "cohort_payload_sha256 must hash the canonical payload excluding only itself"))
    return sorted(set(issues))


def validate_fixed_cohort(document: Any, *, repo_root: Path | str | None = None) -> None:
    """Fail closed unless schema and B1S1 semantic controls both hold."""

    root = _repo_root(repo_root)
    registry = ContractRegistry(root)
    schema_issues = list(registry.issues(FIXED_COHORT_CONTRACT_ID, document))
    semantic_issues = fixed_cohort_contract_semantic_issues(document, repo_root=root) if isinstance(document, Mapping) else [_issue("$", "fixed_cohort.document", "fixed cohort must be a JSON object")]
    issues = tuple(sorted(set(schema_issues + semantic_issues)))
    if issues:
        raise ContractValidationError(FIXED_COHORT_CONTRACT_ID, issues)


def build_fixed_cohort(nct_ids: Sequence[str], *, provenance: Mapping[str, Any], repo_root: Path | str | None = None) -> dict[str, Any]:
    """Construct one dark cohort after binding the caller's declared provenance."""

    canonical_ids = _canonical_nct_ids(nct_ids)
    canonical_provenance = _bounded_provenance(provenance)
    registry_bytes, _ = _registry_bytes_and_control(repo_root)
    document: dict[str, Any] = {
        "contract_id": FIXED_COHORT_CONTRACT_ID,
        "schema_version": "1.0.0",
        "source_id": FIXED_COHORT_SOURCE_ID,
        "universe_mode": "fixed_explicit_nct_cohort",
        "membership_authority": "fixed_cohort_only",
        "candidate_admission_policy": "candidate_subset_only",
        "nct_ids": list(canonical_ids),
        "query_id": ",".join(canonical_ids),
        "control_registration": FIXED_COHORT_CONTROL_REGISTRATION,
        "control": {**_DARK_CONTROL, "consumers": []},
        "source_registry_ref": FIXED_COHORT_REGISTRY_REF,
        "source_registry_sha256": hashlib.sha256(registry_bytes).hexdigest(),
        "prohibited_claims": list(_PROHIBITED),
        "prohibited_uses": list(_PROHIBITED),
        "provenance": canonical_provenance,
        "hash_scope": FIXED_COHORT_HASH_SCOPE,
    }
    document["cohort_id"] = f"ctgov_fixed_cohort_{canonical_json_sha256(fixed_cohort_identity_payload(document))[:24]}"
    document["cohort_payload_sha256"] = canonical_json_sha256(document)
    validate_fixed_cohort(document, repo_root=repo_root)
    return document


def _detached_admission_snapshot(cohort: object) -> dict[str, Any]:
    """Detach one finite cohort snapshot before validation and membership use.

    A ``dict`` subclass can make ``get``/``items`` and ``__getitem__`` disagree.
    Canonical serialization followed by parsing makes one plain JSON tree, so
    validation and the returned membership necessarily use identical content.
    """

    try:
        raw = canonical_json_bytes(cohort)
    except Exception as exc:
        raise ValueError("cohort must be a finite canonical JSON object") from exc
    if len(raw) > ADMISSION_SNAPSHOT_MAX_BYTES:
        raise ValueError("cohort snapshot exceeds the admission byte limit")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("cohort cannot be detached into canonical JSON") from exc
    if type(parsed) is not dict:
        raise ValueError("cohort must detach to a JSON object")
    return parsed


def admit_fixed_cohort_candidates(cohort: Mapping[str, Any], candidates: Sequence[str], *, repo_root: Path | str | None = None) -> tuple[str, ...]:
    """Return only fixed members nominated by candidates, in canonical cohort order."""

    snapshot = _detached_admission_snapshot(cohort)
    validate_fixed_cohort(snapshot, repo_root=repo_root)
    if type(candidates) not in (list, tuple):
        raise ValueError("candidates must be a list or tuple of NCT identifiers")
    if len(candidates) > FIXED_COHORT_MAX_NCT_IDS:
        raise ValueError("candidates may contain at most 25 NCT identifiers")
    if any(not isinstance(candidate, str) or not _NCT_ID_RE.fullmatch(candidate) for candidate in candidates):
        raise ValueError("candidates must contain canonical ASCII NCT######## identifiers")
    if len(set(candidates)) != len(candidates):
        raise ValueError("candidates must be unique")
    nominated = set(candidates)
    nct_ids = snapshot["nct_ids"]
    assert isinstance(nct_ids, list)
    unknown = nominated - set(nct_ids)
    if unknown:
        raise ValueError("candidates may not enlarge fixed-cohort membership")
    return tuple(nct_id for nct_id in nct_ids if nct_id in nominated)


def _bounded_parse_int(token: str) -> int:
    if len(token.lstrip("-")) > FIXTURE_MAX_JSON_NUMBER_TOKEN_BYTES:
        raise ValueError("JSON integer token exceeds fixture limit")
    return int(token)


def _bounded_parse_float(token: str) -> float:
    if len(token) > FIXTURE_MAX_JSON_NUMBER_TOKEN_BYTES:
        raise ValueError("JSON number token exceeds fixture limit")
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("JSON number must be finite")
    return value


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-standard JSON constant {token!r}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


def _check_json_tree(value: Any, *, depth: int = 0, seen: list[int] | None = None) -> None:
    if seen is None:
        seen = [0]
    seen[0] += 1
    if seen[0] > FIXTURE_MAX_JSON_NODES:
        raise ValueError("JSON document exceeds fixture node limit")
    if depth > FIXTURE_MAX_JSON_DEPTH:
        raise ValueError("JSON document exceeds fixture nesting-depth limit")
    if isinstance(value, str):
        if _utf8_size(value) > FIXTURE_MAX_JSON_STRING_BYTES:
            raise ValueError("JSON string exceeds fixture byte limit")
        return
    if value is None or isinstance(value, bool) or isinstance(value, (int, float)):
        return
    if isinstance(value, list):
        if len(value) > FIXTURE_MAX_JSON_CONTAINER_ITEMS:
            raise ValueError("JSON array exceeds fixture item limit")
        for item in value:
            _check_json_tree(item, depth=depth + 1, seen=seen)
        return
    if isinstance(value, dict):
        if len(value) > FIXTURE_MAX_JSON_CONTAINER_ITEMS:
            raise ValueError("JSON object exceeds fixture item limit")
        for key, item in value.items():
            if _utf8_size(key) > FIXTURE_MAX_JSON_STRING_BYTES:
                raise ValueError("JSON object key exceeds fixture byte limit")
            _check_json_tree(item, depth=depth + 1, seen=seen)
        return
    raise ValueError(f"unsupported JSON value {type(value).__name__}")


def _parse_bounded_canonical_json(raw: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys, parse_int=_bounded_parse_int, parse_float=_bounded_parse_float, parse_constant=_reject_json_constant)
        _check_json_tree(parsed)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_json", f"invalid bounded JSON: {exc}"),)) from exc
    if not isinstance(parsed, Mapping):
        raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_shape", "fixture must encode a JSON object"),))
    try:
        canonical = canonical_json_bytes(parsed)
    except ContractError as exc:
        raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_canonical", "fixture must be finite canonical JSON"),)) from exc
    # Repository fixtures are source text and use precisely one terminal LF.
    # The no-LF canonical payload and every other byte representation fail.
    if raw != canonical + b"\n":
        raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_noncanonical", "fixture bytes must be canonical JSON followed by one terminal LF"),))
    return parsed


def _open_absolute_directory(root: Path, *, label: str) -> int:
    if not root.is_absolute() or any(part in {"", ".", ".."} for part in root.parts[1:]):
        raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_root", "fixture root must be an absolute path without relative components"),))
    if any(not hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")):
        raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_platform", "fixture loading requires descriptor-relative no-follow support"),))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current_fd = -1
    try:
        current_fd = os.open(os.path.sep, flags)
        for component in root.parts[1:]:
            try:
                next_fd = os.open(component, flags, dir_fd=current_fd)
            except OSError as exc:
                code = "fixed_cohort.fixture_symlink" if exc.errno == errno.ELOOP else "fixed_cohort.fixture_root"
                raise FixedCohortFixtureError((_issue(label, code, f"fixture root is unavailable or unsafe: {exc}"),)) from exc
            try:
                if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                    raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_root", "every fixture-root component must be a real directory"),))
            except BaseException:
                os.close(next_fd)
                raise
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        if current_fd >= 0:
            os.close(current_fd)
        raise


def _safe_read_relative_fixture(
    root: Path,
    relative_path: Path | str,
    *,
    max_bytes: int = FIXTURE_MAX_BYTES,
    label: str = "$.fixture",
) -> bytes:
    relative = Path(relative_path)
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_path", "fixture path escapes its approved root"),))
    root_fd = _open_absolute_directory(root, label="$.fixture_root")
    parent_fd = -1
    descriptor = -1
    try:
        parent_fd = os.dup(root_fd)
        for component in relative.parts[:-1]:
            try:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
            except OSError as exc:
                code = "fixed_cohort.fixture_symlink" if exc.errno == errno.ELOOP else "fixed_cohort.fixture_path"
                raise FixedCohortFixtureError((_issue(label, code, f"fixture parent is unavailable or unsafe: {exc}"),)) from exc
            try:
                if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                    raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_path", "fixture parent must be a real directory"),))
            except BaseException:
                os.close(next_fd)
                raise
            os.close(parent_fd)
            parent_fd = next_fd
        try:
            descriptor = os.open(relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
        except OSError as exc:
            code = "fixed_cohort.fixture_symlink" if exc.errno == errno.ELOOP else "fixed_cohort.fixture_open"
            raise FixedCohortFixtureError((_issue(label, code, f"cannot safely open fixture: {exc}"),)) from exc
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_file", "fixture must be a single-link regular file"),))
        if before.st_size < 1 or before.st_size > max_bytes:
            raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_size", f"fixture must be 1-{max_bytes} bytes"),))
        remaining = before.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(4096, remaining))
            if not chunk:
                raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_read", "fixture changed during bounded read"),))
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        signature_before = (before.st_dev, before.st_ino, before.st_mode, before.st_nlink, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        signature_after = (after.st_dev, after.st_ino, after.st_mode, after.st_nlink, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if signature_before != signature_after:
            raise FixedCohortFixtureError((_issue(label, "fixed_cohort.fixture_toctou", "fixture changed while being read"),))
        return b"".join(chunks)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_fd >= 0:
            os.close(parent_fd)
        os.close(root_fd)


def load_bounded_canonical_json_fixture(fixture_root: Path | str, relative_path: Path | str) -> Mapping[str, Any]:
    """Load only bounded canonical JSON beneath an approved absolute root."""

    return _parse_bounded_canonical_json(_safe_read_relative_fixture(Path(fixture_root), relative_path), label="$.fixture")


def load_fixed_cohort_fixture(fixture_root: Path | str, relative_path: Path | str = "ctgov_fixed_cohort.v1.valid.json", *, repo_root: Path | str | None = None) -> Mapping[str, Any]:
    """Load and validate one hermetic fixed-cohort fixture."""

    document = load_bounded_canonical_json_fixture(fixture_root, relative_path)
    validate_fixed_cohort(document, repo_root=repo_root)
    return document
