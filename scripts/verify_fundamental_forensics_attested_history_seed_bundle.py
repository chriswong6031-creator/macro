"""Independently admit one production AAPL attested-history seed bundle.

The seed workflow creates review artifacts; it does not make them canonical.
This verifier is deliberately separate from the producer.  It re-reads every
artifact through bounded regular-file ingress, recomputes all byte lengths and
SHA-256 digests, validates the reviewed GitHub run and dependency-lock
provenance, and cross-checks the packet, seed receipt, and zero-write preflight.

It never opens an object-store client and never accepts credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.fundamental_forensics.models import canonical_json
from scripts.run_fundamental_forensics_attested_history import (
    MAX_SPEC_BYTES,
    OperatorPreflightError,
    operator_spec_from_bytes,
)

PACKET_FILENAME = "attested_history_operator_packet.json"
PREFLIGHT_FILENAME = "attested_history_preflight_receipt.json"
SEED_FILENAME = "attested_history_seed_receipt.json"
BUNDLE_FILENAME = "attested_history_seed_bundle_receipt.json"
EXPECTED_FILES = frozenset(
    {PACKET_FILENAME, PREFLIGHT_FILENAME, SEED_FILENAME, BUNDLE_FILENAME}
)
DEPENDENCY_LOCK_PATH = "requirements/attested-history-macos-arm64-py312.lock"
EXPECTED_REPOSITORY = "mastermindx-market-intelligence/macro"
EXPECTED_REF = "refs/heads/main"
EXPECTED_WORKFLOW = "attested-history-aapl-seed"
EXPECTED_ENVIRONMENT = "attested-history-seed"
EXPECTED_CIK = "0000320193"
EXPECTED_TICKER = "AAPL"
MAX_REVIEW_RECEIPT_BYTES = 4 * 1024 * 1024
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
_UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z$"
)
_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_STORAGE_CONTROL_RE = re.compile(
    r"^fundamental_forensics/attested-history-seed-control/v1/[a-f0-9]{32}$"
)
_FINAL_CONTROL_SHA256 = sha256(
    b"fundamental-forensics/attested-history-seed-control/v1:final"
).hexdigest()


class SeedBundleVerificationError(ValueError):
    """The review bundle is not admissible as production evidence."""


@dataclass(frozen=True)
class ExpectedRun:
    repository: str
    sha: str
    ref: str
    run_id: int
    run_attempt: int
    environment: str
    workflow: str
    dependency_lock_sha256: str

    def as_provenance(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "sha": self.sha,
            "ref": self.ref,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
            "environment": self.environment,
            "workflow": self.workflow,
        }


def _fail(message: str) -> None:
    raise SeedBundleVerificationError(message)


def _exact_object(value: Any, *, field: str, keys: frozenset[str]) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail(f"{field} must be an object")
    actual = frozenset(value)
    if actual != keys:
        _fail(f"{field} fields are not exact")
    return value


def _text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{field} must be non-empty text")
    return value


def _integer(value: Any, *, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(f"{field} must be an integer >= {minimum}")
    return value


def _identifier(value: Any, *, field: str, pattern: re.Pattern[str]) -> str:
    text = _text(value, field=field)
    if pattern.fullmatch(text) is None:
        _fail(f"{field} is invalid")
    return text


def _utc(value: Any, *, field: str) -> datetime:
    text = _identifier(value, field=field, pattern=_UTC_RE)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:  # pragma: no cover - regex normally catches it
        raise SeedBundleVerificationError(f"{field} is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        _fail(f"{field} must be UTC")
    return parsed


def _read_regular_file_bounded(path: Path, *, maximum_bytes: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SeedBundleVerificationError(
            f"{path.name} cannot be opened safely"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum_bytes:
            _fail(f"{path.name} is not a bounded regular file")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                _fail(f"{path.name} changed during bounded read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail(f"{path.name} grew during bounded read")
        after = os.fstat(descriptor)
        stable = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        if not stable:
            _fail(f"{path.name} changed during bounded read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _json(content: bytes, *, field: str, trailing_newline: bool) -> Mapping[str, Any]:
    def reject_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                _fail(f"{field} has duplicate JSON keys")
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        _fail(f"{field} has a non-finite JSON token")

    def reject_float(_value: str) -> None:
        _fail(f"{field} cannot use JSON floats")

    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
            parse_float=reject_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SeedBundleVerificationError(f"{field} is not valid UTF-8 JSON") from exc
    if type(value) is not dict:
        _fail(f"{field} must be a JSON object")
    canonical = canonical_json(value).encode("utf-8")
    if not trailing_newline:
        canonical = canonical.removesuffix(b"\n")
    if canonical != content:
        _fail(f"{field} is not byte-exact canonical JSON")
    return value


def _artifact_record(value: Any, *, field: str, filename: str, content: bytes) -> None:
    record = _exact_object(
        value,
        field=field,
        keys=frozenset({"filename", "sha256", "bytes"}),
    )
    if record["filename"] != filename:
        _fail(f"{field}.filename does not match")
    if record["sha256"] != sha256(content).hexdigest():
        _fail(f"{field}.sha256 does not match recomputed bytes")
    if record["bytes"] != len(content):
        _fail(f"{field}.bytes does not match recomputed length")


def _dependency_lock(
    value: Any, *, field: str, expected: ExpectedRun, target: bool
) -> None:
    keys = {"path", "sha256"}
    if target:
        keys.add("target")
    item = _exact_object(value, field=field, keys=frozenset(keys))
    if item["path"] != DEPENDENCY_LOCK_PATH:
        _fail(f"{field}.path is invalid")
    if item["sha256"] != expected.dependency_lock_sha256:
        _fail(f"{field}.sha256 does not bind the reviewed commit")
    if target and item["target"] != "CPython 3.12 macOS arm64":
        _fail(f"{field}.target is invalid")


def _run_provenance(value: Any, *, field: str, expected: ExpectedRun) -> None:
    provenance = _exact_object(
        value,
        field=field,
        keys=frozenset(expected.as_provenance()),
    )
    if provenance != expected.as_provenance():
        _fail(f"{field} does not match the reviewed GitHub run")


def _validate_expected(expected: ExpectedRun) -> None:
    if expected.repository != EXPECTED_REPOSITORY:
        _fail("expected repository is not the production repository")
    _identifier(expected.sha, field="expected sha", pattern=_COMMIT_RE)
    if expected.ref != EXPECTED_REF:
        _fail("expected ref is not main")
    _integer(expected.run_id, field="expected run id", minimum=1)
    _integer(expected.run_attempt, field="expected run attempt", minimum=1)
    if expected.environment != EXPECTED_ENVIRONMENT:
        _fail("expected environment is invalid")
    if expected.workflow != EXPECTED_WORKFLOW:
        _fail("expected workflow is invalid")
    _identifier(
        expected.dependency_lock_sha256,
        field="expected dependency lock sha256",
        pattern=_SHA256_RE,
    )


def _validate_bundle_receipt(
    bundle: Mapping[str, Any],
    *,
    contents: Mapping[str, bytes],
    expected: ExpectedRun,
) -> datetime:
    item = _exact_object(
        bundle,
        field="bundle receipt",
        keys=frozenset(
            {
                "schema",
                "status",
                "run_provenance",
                "dependency_lock",
                "files",
                "assembled_at",
                "nonclaims",
            }
        ),
    )
    if item["schema"] != "fundamental_forensics.attested_history_aapl_seed_bundle/v1":
        _fail("bundle receipt schema is unsupported")
    if item["status"] != "prepared":
        _fail("bundle receipt is not prepared")
    _run_provenance(
        item["run_provenance"], field="bundle run provenance", expected=expected
    )
    _dependency_lock(
        item["dependency_lock"],
        field="bundle dependency lock",
        expected=expected,
        target=False,
    )
    files = _exact_object(
        item["files"],
        field="bundle files",
        keys=frozenset({PACKET_FILENAME, PREFLIGHT_FILENAME, SEED_FILENAME}),
    )
    for filename in (PACKET_FILENAME, PREFLIGHT_FILENAME, SEED_FILENAME):
        _artifact_record(
            files[filename],
            field=f"bundle files.{filename}",
            filename=filename,
            content=contents[filename],
        )
    if item["nonclaims"] != [
        "review_artifact_not_canonical_publication",
        "credential_separation_not_parent_iam_proof",
    ]:
        _fail("bundle nonclaims are not exact")
    return _utc(item["assembled_at"], field="bundle assembled_at")


def _validate_packet(packet_bytes: bytes, packet: Mapping[str, Any]) -> dict[str, str]:
    try:
        operator_spec_from_bytes(packet_bytes)
    except OperatorPreflightError as exc:
        raise SeedBundleVerificationError(
            "operator packet fails production admission"
        ) from exc
    root = _exact_object(
        packet,
        field="operator packet",
        keys=frozenset(
            {"schema", "base_query_snapshot_id", "source_snapshot_id", "packet"}
        ),
    )
    body = _exact_object(
        root["packet"],
        field="operator packet.packet",
        keys=frozenset({"cik", "filing", "ixbrl_document_name", "companyfacts"}),
    )
    filing = _exact_object(
        body["filing"],
        field="operator packet.packet.filing",
        keys=frozenset(
            {
                "accession",
                "manifest_id",
                "archive_index_document",
                "member_states",
                "policy_profile",
                "policy_version",
            }
        ),
    )
    if body["cik"] != EXPECTED_CIK:
        _fail("operator packet does not bind AAPL's CIK")
    return {
        "cik": EXPECTED_CIK,
        "accession": _identifier(
            filing["accession"],
            field="operator packet accession",
            pattern=_ACCESSION_RE,
        ),
        "manifest_id": _identifier(
            filing["manifest_id"],
            field="operator packet manifest id",
            pattern=re.compile(r"^ffsec_manifest_[a-f0-9]{64}$"),
        ),
        "base_query_snapshot_id": _identifier(
            root["base_query_snapshot_id"],
            field="operator packet base query snapshot id",
            pattern=re.compile(r"^ffqs_[a-f0-9]{64}$"),
        ),
        "source_snapshot_id": _identifier(
            root["source_snapshot_id"],
            field="operator packet source snapshot id",
            pattern=re.compile(r"^ffsecsrc_[a-f0-9]{64}$"),
        ),
    }


def _validate_preflight(
    receipt: Mapping[str, Any],
    *,
    packet_ids: Mapping[str, str],
) -> tuple[datetime, dict[str, str]]:
    item = _exact_object(
        receipt,
        field="preflight receipt",
        keys=frozenset(
            {
                "schema",
                "status",
                "operator_verification_observed_at",
                "publication",
                "redaction",
                "nonclaims",
                "inputs",
                "materialization",
                "binding_plan",
                "candidate",
            }
        ),
    )
    if item["schema"] != "fundamental_forensics.attested_history_preflight_receipt/v1":
        _fail("preflight receipt schema is unsupported")
    if item["status"] != "prepared":
        _fail("preflight receipt is not prepared")
    observed_at = _utc(
        item["operator_verification_observed_at"],
        field="preflight operator_verification_observed_at",
    )
    publication = _exact_object(
        item["publication"],
        field="preflight publication",
        keys=frozenset(
            {
                "publication_performed",
                "pointer_advanced",
                "immutable_objects_written",
                "storage_write_attempts",
            }
        ),
    )
    if publication != {
        "publication_performed": False,
        "pointer_advanced": False,
        "immutable_objects_written": False,
        "storage_write_attempts": 0,
    }:
        _fail("preflight publication is not exactly zero-write")
    redaction = _exact_object(
        item["redaction"],
        field="preflight redaction",
        keys=frozenset(
            {
                "raw_source_payloads_included",
                "storage_paths_included",
                "storage_endpoints_included",
                "storage_credentials_included",
                "error_messages_included",
            }
        ),
    )
    if any(value is not False for value in redaction.values()):
        _fail("preflight redaction boundary is not exact")
    if item["nonclaims"] != [
        "not_published",
        "not_a_freshness_claim",
        "not_a_filing_completeness_claim",
        "not_investment_or_trading_authority",
    ]:
        _fail("preflight nonclaims are not exact")
    inputs = _exact_object(
        item["inputs"],
        field="preflight inputs",
        keys=frozenset(
            {
                "base_query_snapshot_id",
                "source_snapshot_id",
                "cik",
                "accession",
                "filing_manifest_id",
            }
        ),
    )
    expected_inputs = {
        "base_query_snapshot_id": packet_ids["base_query_snapshot_id"],
        "source_snapshot_id": packet_ids["source_snapshot_id"],
        "cik": packet_ids["cik"],
        "accession": packet_ids["accession"],
        "filing_manifest_id": packet_ids["manifest_id"],
    }
    if inputs != expected_inputs:
        _fail("preflight inputs do not bind the exact operator packet")
    materialization = _exact_object(
        item["materialization"],
        field="preflight materialization",
        keys=frozenset(
            {
                "filing_package_id",
                "ixbrl_extraction_id",
                "filing_attestation_id",
                "companyfacts_conversion_receipt_id",
            }
        ),
    )
    patterns = {
        "filing_package_id": r"^ffpkg_[a-f0-9]{64}$",
        "ixbrl_extraction_id": r"^ffxbrl_[a-f0-9]{64}$",
        "filing_attestation_id": r"^ffatt_[a-f0-9]{64}$",
        "companyfacts_conversion_receipt_id": r"^cffledger_[a-f0-9]{64}$",
    }
    materialization_ids: dict[str, str] = {}
    for name, pattern in patterns.items():
        materialization_ids[name] = _identifier(
            materialization[name],
            field=f"preflight materialization.{name}",
            pattern=re.compile(pattern),
        )
    binding = _exact_object(
        item["binding_plan"],
        field="preflight binding plan",
        keys=frozenset(
            {
                "binding_count",
                "candidate_leaf_count",
                "rejected_leaf_count",
                "rejection_reason_counts",
                "coverage",
            }
        ),
    )
    _integer(binding["binding_count"], field="preflight binding count", minimum=1)
    _integer(binding["candidate_leaf_count"], field="preflight candidate leaf count")
    _integer(binding["rejected_leaf_count"], field="preflight rejected leaf count")
    rejection_counts = binding["rejection_reason_counts"]
    if type(rejection_counts) is not dict or len(rejection_counts) > 8:
        _fail("preflight rejection reason counts must be an object")
    allowed_reasons = frozenset(
        {
            "not_sec_companyfacts",
            "dimensions_known",
            "selected_occurrence_not_in_companyfacts_conversion",
            "conversion_occurrence_differs_from_selected_leaf",
            "no_b3_attestation_binds_companyfacts_conversion",
            "no_exact_b3_match",
            "ambiguous_exact_b3_matches",
            "exact_b3_match_shared_by_selected_leaves",
        }
    )
    if not frozenset(rejection_counts).issubset(allowed_reasons):
        _fail("preflight rejection reason is invalid")
    for reason, count in rejection_counts.items():
        _integer(count, field=f"preflight rejection reason {reason}")
    coverage = binding["coverage"]
    if not isinstance(coverage, list) or len(coverage) > 2_048:
        _fail("preflight coverage must be a list")
    coverage_keys = frozenset(
        {
            "root_cell_id",
            "status",
            "selected_leaf_count",
            "eligible_leaf_count",
            "candidate_leaf_count",
            "auto_bound_leaf_count",
        }
    )
    for index, raw_coverage in enumerate(coverage):
        coverage_item = _exact_object(
            raw_coverage,
            field=f"preflight coverage[{index}]",
            keys=coverage_keys,
        )
        _identifier(
            coverage_item["root_cell_id"],
            field=f"preflight coverage[{index}].root_cell_id",
            pattern=re.compile(r"^metric_cell_[a-f0-9]{64}$"),
        )
        if coverage_item["status"] not in {
            "not_evaluable",
            "all_leaves_attested",
            "partially_attested",
            "not_attested",
        }:
            _fail(f"preflight coverage[{index}].status is invalid")
        for count_name in (
            "selected_leaf_count",
            "eligible_leaf_count",
            "candidate_leaf_count",
            "auto_bound_leaf_count",
        ):
            _integer(
                coverage_item[count_name],
                field=f"preflight coverage[{index}].{count_name}",
            )
    candidate = _exact_object(
        item["candidate"],
        field="preflight candidate",
        keys=frozenset(
            {
                "prepared_in_memory",
                "candidate_snapshot_id",
                "candidate_published_at_is_not_an_actual_publication",
            }
        ),
    )
    if candidate["prepared_in_memory"] is not True:
        _fail("preflight candidate was not prepared in memory")
    candidate_id = _identifier(
        candidate["candidate_snapshot_id"],
        field="preflight candidate snapshot id",
        pattern=re.compile(r"^ffqsv2_[a-f0-9]{64}$"),
    )
    if candidate["candidate_published_at_is_not_an_actual_publication"] is not True:
        _fail("preflight candidate publication nonclaim is absent")
    materialization_ids["candidate_snapshot_id"] = candidate_id
    return observed_at, materialization_ids


def _validate_seed_receipt(
    receipt: Mapping[str, Any],
    *,
    contents: Mapping[str, bytes],
    expected: ExpectedRun,
    packet_ids: Mapping[str, str],
    preflight_observed_at: datetime,
    bundle_assembled_at: datetime,
) -> None:
    item = _exact_object(
        receipt,
        field="seed receipt",
        keys=frozenset(
            {
                "schema",
                "status",
                "ticker",
                "cik",
                "source_snapshot_id",
                "base_query_snapshot_id",
                "clocks",
                "dependency_lock",
                "run_provenance",
                "selected_occurrence_id",
                "selected_match_id",
                "declared_older_submissions_count",
                "archive_inventory_member_count",
                "archive_stored_member_count",
                "archive_not_requested_member_count",
                "storage_control_probe",
                "preflight",
                "review_artifacts",
                "nonclaims",
            }
        ),
    )
    if item["schema"] != "fundamental_forensics.attested_history_aapl_seed/v1":
        _fail("seed receipt schema is unsupported")
    if (
        item["status"] != "prepared"
        or item["ticker"] != EXPECTED_TICKER
        or item["cik"] != EXPECTED_CIK
    ):
        _fail("seed receipt does not bind the prepared AAPL issuer")
    if item["source_snapshot_id"] != packet_ids["source_snapshot_id"]:
        _fail("seed source snapshot id does not match the packet")
    if item["base_query_snapshot_id"] != packet_ids["base_query_snapshot_id"]:
        _fail("seed base query snapshot id does not match the packet")
    clocks = _exact_object(
        item["clocks"],
        field="seed clocks",
        keys=frozenset(
            {
                "source_snapshot_at",
                "operator_verification_observed_at",
                "preflight_completed_at",
            }
        ),
    )
    source_at = _utc(clocks["source_snapshot_at"], field="seed source_snapshot_at")
    operator_at = _utc(
        clocks["operator_verification_observed_at"],
        field="seed operator_verification_observed_at",
    )
    completed_at = _utc(
        clocks["preflight_completed_at"], field="seed preflight_completed_at"
    )
    if operator_at != preflight_observed_at:
        _fail("seed and preflight operator clocks do not match")
    if not source_at <= operator_at <= completed_at <= bundle_assembled_at:
        _fail("seed and bundle clocks are not monotonic")
    _dependency_lock(
        item["dependency_lock"],
        field="seed dependency lock",
        expected=expected,
        target=True,
    )
    _run_provenance(
        item["run_provenance"], field="seed run provenance", expected=expected
    )
    _identifier(
        item["selected_occurrence_id"],
        field="seed selected occurrence id",
        pattern=re.compile(r"^rawfact_[a-f0-9]{64}$"),
    )
    _identifier(
        item["selected_match_id"],
        field="seed selected match id",
        pattern=re.compile(r"^ffatt_match_[a-f0-9]{64}$"),
    )
    older_count = _integer(
        item["declared_older_submissions_count"],
        field="seed declared older submissions count",
    )
    del older_count  # bounded by the producer; presence and type are reviewed here
    inventory_count = _integer(
        item["archive_inventory_member_count"],
        field="seed archive inventory member count",
        minimum=1,
    )
    stored_count = _integer(
        item["archive_stored_member_count"],
        field="seed archive stored member count",
        minimum=1,
    )
    not_requested_count = _integer(
        item["archive_not_requested_member_count"],
        field="seed archive not-requested member count",
    )
    if stored_count != 1 or stored_count + not_requested_count != inventory_count:
        _fail("seed archive inventory partition is invalid")
    probe = _exact_object(
        item["storage_control_probe"],
        field="seed storage control probe",
        keys=frozenset({"key", "final_sha256", "outcomes"}),
    )
    _identifier(
        probe["key"], field="seed storage control key", pattern=_STORAGE_CONTROL_RE
    )
    if probe["final_sha256"] != _FINAL_CONTROL_SHA256:
        _fail("seed storage control final digest is invalid")
    outcomes = _exact_object(
        probe["outcomes"],
        field="seed storage control outcomes",
        keys=frozenset(
            {
                "absent_before_create",
                "absent_create_succeeded",
                "conflicting_absent_create_rejected",
                "exact_version_advance_succeeded",
                "stale_version_advance_rejected",
                "readonly_final_readback_verified",
            }
        ),
    )
    if any(value is not True for value in outcomes.values()):
        _fail("seed storage control probe did not prove every outcome")
    preflight = _exact_object(
        item["preflight"],
        field="seed preflight summary",
        keys=frozenset({"status", "storage_write_attempts"}),
    )
    if preflight != {"status": "prepared", "storage_write_attempts": 0}:
        _fail("seed preflight summary is not zero-write prepared")
    artifacts = _exact_object(
        item["review_artifacts"],
        field="seed review artifacts",
        keys=frozenset({"operator_packet", "preflight_receipt"}),
    )
    _artifact_record(
        artifacts["operator_packet"],
        field="seed review artifacts.operator_packet",
        filename=PACKET_FILENAME,
        content=contents[PACKET_FILENAME],
    )
    _artifact_record(
        artifacts["preflight_receipt"],
        field="seed review artifacts.preflight_receipt",
        filename=PREFLIGHT_FILENAME,
        content=contents[PREFLIGHT_FILENAME],
    )
    if item["nonclaims"] != [
        "not_a_complete_filing_archive",
        "not_a_dimensions_identity_claim",
        "not_a_freshness_claim_after_preflight",
        "not_investment_or_trading_authority",
    ]:
        _fail("seed nonclaims are not exact")


def verify_seed_bundle(
    artifact_dir: str | Path, *, expected: ExpectedRun
) -> dict[str, Any]:
    """Verify one downloaded production artifact directory and return safe evidence."""
    _validate_expected(expected)
    root = Path(artifact_dir)
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise SeedBundleVerificationError("artifact directory is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("artifact directory must be a non-symlink directory")
    try:
        names = frozenset(entry.name for entry in os.scandir(root))
    except OSError as exc:
        raise SeedBundleVerificationError(
            "artifact directory cannot be enumerated"
        ) from exc
    if names != EXPECTED_FILES:
        _fail("artifact directory must contain exactly the four reviewed files")
    contents: dict[str, bytes] = {}
    for filename in sorted(EXPECTED_FILES):
        maximum = (
            MAX_SPEC_BYTES if filename == PACKET_FILENAME else MAX_REVIEW_RECEIPT_BYTES
        )
        contents[filename] = _read_regular_file_bounded(
            root / filename, maximum_bytes=maximum
        )
    parsed = {
        filename: _json(
            content,
            field=filename,
            trailing_newline=filename != PREFLIGHT_FILENAME,
        )
        for filename, content in contents.items()
    }
    bundle_assembled_at = _validate_bundle_receipt(
        parsed[BUNDLE_FILENAME], contents=contents, expected=expected
    )
    packet_ids = _validate_packet(contents[PACKET_FILENAME], parsed[PACKET_FILENAME])
    preflight_observed_at, materialization_ids = _validate_preflight(
        parsed[PREFLIGHT_FILENAME], packet_ids=packet_ids
    )
    _validate_seed_receipt(
        parsed[SEED_FILENAME],
        contents=contents,
        expected=expected,
        packet_ids=packet_ids,
        preflight_observed_at=preflight_observed_at,
        bundle_assembled_at=bundle_assembled_at,
    )
    return {
        "status": "verified",
        "repository": expected.repository,
        "sha": expected.sha,
        "ref": expected.ref,
        "run_id": expected.run_id,
        "run_attempt": expected.run_attempt,
        "environment": expected.environment,
        "workflow": expected.workflow,
        "issuer": {"ticker": EXPECTED_TICKER, "cik": packet_ids["cik"]},
        "accession": packet_ids["accession"],
        "object_ids": {
            **{
                key: packet_ids[key]
                for key in (
                    "source_snapshot_id",
                    "base_query_snapshot_id",
                    "manifest_id",
                )
            },
            **materialization_ids,
        },
        "dependency_lock_sha256": expected.dependency_lock_sha256,
        "artifacts": {
            filename: {
                "bytes": len(contents[filename]),
                "sha256": sha256(contents[filename]).hexdigest(),
            }
            for filename in sorted(EXPECTED_FILES)
        },
        "zero_write_preflight": True,
        "all_nonclaims_exact": True,
    }


def _git_output(repo_root: Path, *args: str, maximum_bytes: int = 128 * 1024) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise SeedBundleVerificationError(
            "git is unavailable for provenance verification"
        ) from exc
    if result.returncode != 0 or len(result.stdout) > maximum_bytes:
        _fail("reviewed Git provenance is unavailable")
    return result.stdout


def _verified_github_run_identity(
    value: Any,
    *,
    expected_run_id: int,
    expected_sha: str,
    expected_run_attempt: int,
) -> None:
    if type(value) is not dict:
        _fail("GitHub run metadata must be an object")
    head_repository = value.get("head_repository")
    if type(head_repository) is not dict:
        _fail("GitHub run head repository is unavailable")
    expected = {
        "id": expected_run_id,
        "status": "completed",
        "conclusion": "success",
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": expected_sha,
        "run_attempt": expected_run_attempt,
        "path": ".github/workflows/attested-history-aapl-seed.yml",
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            _fail(f"GitHub run {field} does not match the reviewed successful seed")
    if head_repository.get("full_name") != EXPECTED_REPOSITORY:
        _fail("GitHub run did not execute from the production repository")


def _github_run_metadata(run_id: int) -> Mapping[str, Any]:
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{EXPECTED_REPOSITORY}/actions/runs/{run_id}",
            ],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise SeedBundleVerificationError(
            "GitHub CLI is unavailable for run verification"
        ) from exc
    if (
        result.returncode != 0
        or not result.stdout
        or len(result.stdout) > 2 * 1024 * 1024
    ):
        _fail("GitHub run metadata is unavailable")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SeedBundleVerificationError("GitHub run metadata is invalid") from exc
    if type(value) is not dict:
        _fail("GitHub run metadata must be an object")
    return value


def _verify_production_origin(repo_root: Path) -> None:
    try:
        origin = (
            _git_output(repo_root, "remote", "get-url", "origin", maximum_bytes=4096)
            .decode("utf-8")
            .strip()
        )
    except UnicodeDecodeError as exc:
        raise SeedBundleVerificationError("origin URL is invalid") from exc
    normalized = origin.removesuffix(".git").removesuffix("/")
    accepted = {
        f"https://github.com/{EXPECTED_REPOSITORY}",
        f"git@github.com:{EXPECTED_REPOSITORY}",
        f"ssh://git@github.com/{EXPECTED_REPOSITORY}",
    }
    if normalized not in accepted:
        _fail("origin does not identify the production repository")


def expected_run_from_git(
    *,
    repo_root: str | Path,
    sha: str,
    run_id: int,
    run_attempt: int,
) -> ExpectedRun:
    """Bind the expected run to an exact commit reachable from origin/main."""
    root = Path(repo_root).resolve()
    _verify_production_origin(root)
    _identifier(sha, field="expected sha", pattern=_COMMIT_RE)
    _git_output(
        root, "merge-base", "--is-ancestor", sha, "origin/main", maximum_bytes=1
    )
    lock_bytes = _git_output(root, "show", f"{sha}:{DEPENDENCY_LOCK_PATH}")
    if not lock_bytes or len(lock_bytes) > 64 * 1024:
        _fail("reviewed dependency lock is outside its byte boundary")
    return ExpectedRun(
        repository=EXPECTED_REPOSITORY,
        sha=sha,
        ref=EXPECTED_REF,
        run_id=run_id,
        run_attempt=run_attempt,
        environment=EXPECTED_ENVIRONMENT,
        workflow=EXPECTED_WORKFLOW,
        dependency_lock_sha256=sha256(lock_bytes).hexdigest(),
    )


def expected_run_from_github(
    *,
    repo_root: str | Path,
    sha: str,
    run_id: int,
    run_attempt: int,
) -> ExpectedRun:
    """Cross-check operator-supplied identity against the live Actions run."""
    metadata = _github_run_metadata(run_id)
    _verified_github_run_identity(
        metadata,
        expected_run_id=run_id,
        expected_sha=sha,
        expected_run_attempt=run_attempt,
    )
    return expected_run_from_git(
        repo_root=repo_root,
        sha=sha,
        run_id=run_id,
        run_attempt=run_attempt,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-dir",
        required=True,
        help="downloaded four-file seed artifact directory",
    )
    parser.add_argument(
        "--repo-root", default=str(_ROOT), help="fetched production repository checkout"
    )
    parser.add_argument(
        "--sha", required=True, help="full 40-character Actions head SHA"
    )
    parser.add_argument(
        "--run-id", required=True, type=int, help="Actions run database ID"
    )
    parser.add_argument(
        "--run-attempt", required=True, type=int, help="Actions run attempt"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        expected = expected_run_from_github(
            repo_root=args.repo_root,
            sha=args.sha,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
        )
        result = verify_seed_bundle(args.artifact_dir, expected=expected)
    except SeedBundleVerificationError as exc:
        print(f"seed bundle verification failed: {exc}", file=sys.stderr)
        return 1
    print(canonical_json(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
