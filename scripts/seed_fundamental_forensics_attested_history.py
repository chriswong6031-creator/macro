"""Manually seed one bounded AAPL B4 attested-history candidate.

This is a deliberately narrow, one-issuer bootstrap—not a scheduler, a
backfill, or a generic SEC collector.  It obtains exactly AAPL / CIK
0000320193, retains the current SEC Submissions response plus every historical
Submissions member named by that response, captures one current Company Facts
response, and selects one latest eligible 10-K.  The selected filing's complete
archive ``index.json`` inventory is sealed, while only its declared primary
document is retained; every other member is explicitly ``not_requested``.

The command requires a distinct write-capable seed credential in production.
It never falls back to the existing Research Vault variables or to the
read-only attested-history credential. Once the v1 base receipt is sealed
without moving either global ``latest`` pointer,
the candidate is independently rematerialized through the read-only operator
store. Its GitHub Actions artifacts are review-only: they are neither
confidential nor canonical publication. Raw SEC payloads and object-store
locations are never printed to logs.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any, Callable, Mapping, Sequence

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from collectors.edgar_forensics import RetrievalReceipt, SecForensicsCollector  # noqa: E402
from collectors.fundamental_forensics_companyfacts import (
    acquire_companyfacts,
    read_companyfacts_manifest,
)  # noqa: E402
from collectors.sec_document_spine import (
    ArchiveReceipt,
    SecFilingArchiveCollector,
    persist_filing_manifest,
    read_archive_document,
)  # noqa: E402
from engine.fundamental_forensics.attested_history_credentials import (
    R2TemporaryCredentialError,
    mint_r2_temporary_credentials,
    value_free_credential_error,
)  # noqa: E402
from engine.fundamental_forensics.attested_history_pilot import (
    prepare_attested_history_base_candidate,
)  # noqa: E402
from engine.fundamental_forensics.companyfacts_ledger import (
    CompanyFactsConversionSourceBundle,
    CompanyFactsLedgerConversionConfig,
    DEFAULT_MAX_OLDER_SUBMISSIONS_FILES,
    PinnedSubmissionsSource,
    load_companyfacts_ledger_from_pinned_source,
)  # noqa: E402
from engine.fundamental_forensics.filing_attestation import (
    CompanyFactsSourcePaths,
    PinnedSourceAuthority,
    build_filing_attestation,
)  # noqa: E402
from engine.fundamental_forensics.filing_package import (
    PinnedFilingPackageDescriptor,
    materialize_filing_package_from_pinned_source,
)  # noqa: E402
from engine.fundamental_forensics.ixbrl_extraction import build_ixbrl_extraction  # noqa: E402
from engine.fundamental_forensics.models import canonical_json, parse_utc, utc_text  # noqa: E402
from engine.fundamental_forensics.query_snapshots import publish_query_snapshot  # noqa: E402
from engine.fundamental_forensics.sec_document_spine import (
    archive_index_document,
    build_filing_manifests,
    document_with_retrieval,
    documents_from_archive_index,
    select_periodic_comparables,
    with_archive_documents,
    with_document_retrievals,
)  # noqa: E402
from engine.fundamental_forensics.source_sync import sync_source_roots  # noqa: E402
from engine.research_vault.r2_store import (
    LocalStore,
    R2Store,
    StrictBoundedReadStore,
    StrictConditionalWriteStore,
)  # noqa: E402
from scripts.run_fundamental_forensics_attested_history import (
    MAX_SPEC_BYTES as MAX_OPERATOR_PACKET_BYTES,
    build_readonly_operator_store,
    operator_spec_from_bytes,
    run_readonly_preflight,
    write_private_receipt,
)  # noqa: E402


AAPL_TICKER = "AAPL"
AAPL_CIK = "0000320193"
SEED_SCHEMA = "fundamental_forensics.attested_history_aapl_seed/v1"
SEED_PACKET_FILENAME = "attested_history_operator_packet.json"
SEED_RECEIPT_FILENAME = "attested_history_seed_receipt.json"
SEED_BUNDLE_RECEIPT_FILENAME = "attested_history_seed_bundle_receipt.json"
SEED_BUNDLE_SCHEMA = "fundamental_forensics.attested_history_aapl_seed_bundle/v1"
SEED_POLICY_PROFILE = "attested_history_aapl_seed/v1"
SEED_POLICY_VERSION = "1"
MAX_SUBMISSIONS_BYTES = 32 * 1024 * 1024
MAX_COMPANYFACTS_BYTES = 64 * 1024 * 1024
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_SOURCE_FILES = 2_048
MAX_SOURCE_TOTAL_BYTES = 256 * 1024 * 1024
MAX_OLDER_SUBMISSIONS_FILES = DEFAULT_MAX_OLDER_SUBMISSIONS_FILES
MAX_ARCHIVE_INVENTORY_MEMBERS = 4_096
MAX_STORAGE_CONTROL_BYTES = 512
STORAGE_CONTROL_PREFIX = "fundamental_forensics/attested-history-seed-control/v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY_LOCK_RELATIVE_PATH = Path(
    "requirements/attested-history-macos-arm64-py312.lock"
)
MAX_DEPENDENCY_LOCK_BYTES = 64 * 1024
EXPECTED_GITHUB_REPOSITORY = "mastermindx-market-intelligence/macro"
EXPECTED_GITHUB_REF = "refs/heads/main"
EXPECTED_GITHUB_ENVIRONMENT = "attested-history-seed"
EXPECTED_GITHUB_WORKFLOW = "attested-history-aapl-seed"
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_GITHUB_SHA_RE = re.compile(r"^[a-f0-9]{40}$")
_POSITIVE_DECIMAL_RE = re.compile(r"^[1-9][0-9]*$")

_OLDER_SUBMISSIONS_RE = re.compile(r"^CIK([0-9]{10})-submissions-([0-9]{3})\.json$")


class AttestedHistorySeedError(RuntimeError):
    """The bounded AAPL bootstrap cannot establish its explicit evidence graph.

    Every message raised as this type is authored to be value-free: a static
    sentence, one interpolating a ``{field}`` NAME, or a credential-minter
    reason admitted by ``value_free_credential_error``. That is what makes it
    safe to print verbatim in the operator annotation, so a new raise site must
    keep the invariant — name the field, never the value. Any *other* exception
    can carry an endpoint, bucket, object key, or local source path in its
    message, and only its class name is ever surfaced.
    """


MAX_ANNOTATION_MESSAGE_CHARS = 200


def _annotation_message(text: str) -> str:
    """Flatten one value-free sentence onto the annotation's single line.

    GitHub parses ``::error`` only while it owns its whole line, so an embedded
    newline would both truncate the annotation and spill its remainder into the
    raw log.  No current raise site contains one; this keeps that true for the
    next one.
    """
    flattened = " ".join(str(text).split())
    if len(flattened) > MAX_ANNOTATION_MESSAGE_CHARS:
        flattened = flattened[:MAX_ANNOTATION_MESSAGE_CHARS] + "..."
    return flattened or "no message"


def validate_production_environment_boundary() -> None:
    """Validate the two parent roles before any production I/O or local signing.

    Distinct parent key IDs are necessary role separation, but are not proof of
    their Cloudflare IAM policies.  Runtime child JWTs and the storage-control
    probe establish the narrower operation boundary actually used by the seed.
    """
    names = (
        "FF_ATTESTED_R2_SEED_ENDPOINT",
        "FF_ATTESTED_R2_SEED_ACCESS_KEY_ID",
        "FF_ATTESTED_R2_SEED_SECRET_ACCESS_KEY",
        "FF_ATTESTED_R2_SEED_BUCKET",
        "FF_ATTESTED_R2_READONLY_ENDPOINT",
        "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID",
        "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY",
        "FF_ATTESTED_R2_READONLY_BUCKET",
    )
    values = {name: os.environ.get(name, "") for name in names}
    if any(not value for value in values.values()):
        raise AttestedHistorySeedError(
            "dedicated attested-history parent credentials are unavailable"
        )
    if values["FF_ATTESTED_R2_SEED_ENDPOINT"] != values[
        "FF_ATTESTED_R2_READONLY_ENDPOINT"
    ] or values["FF_ATTESTED_R2_SEED_BUCKET"] != values[
        "FF_ATTESTED_R2_READONLY_BUCKET"
    ]:
        raise AttestedHistorySeedError(
            "writer and read-only parents must bind the same endpoint and bucket"
        )
    if values["FF_ATTESTED_R2_SEED_ACCESS_KEY_ID"] == values[
        "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID"
    ]:
        raise AttestedHistorySeedError(
            "writer and read-only parent access key IDs must be distinct"
        )


def production_run_provenance() -> dict[str, Any]:
    """Admit only the exact non-secret GitHub context of the production seed."""
    values = {
        "repository": os.environ.get("FF_ATTESTED_GITHUB_REPOSITORY", ""),
        "sha": os.environ.get("FF_ATTESTED_GITHUB_SHA", ""),
        "ref": os.environ.get("FF_ATTESTED_GITHUB_REF", ""),
        "run_id": os.environ.get("FF_ATTESTED_GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("FF_ATTESTED_GITHUB_RUN_ATTEMPT", ""),
        "environment": os.environ.get("FF_ATTESTED_GITHUB_ENVIRONMENT", ""),
        "workflow": os.environ.get("FF_ATTESTED_GITHUB_WORKFLOW", ""),
    }
    if (
        values["repository"] != EXPECTED_GITHUB_REPOSITORY
        or values["ref"] != EXPECTED_GITHUB_REF
        or values["environment"] != EXPECTED_GITHUB_ENVIRONMENT
        or values["workflow"] != EXPECTED_GITHUB_WORKFLOW
        or _GITHUB_SHA_RE.fullmatch(values["sha"]) is None
        or _POSITIVE_DECIMAL_RE.fullmatch(values["run_id"]) is None
        or _POSITIVE_DECIMAL_RE.fullmatch(values["run_attempt"]) is None
    ):
        raise AttestedHistorySeedError("GitHub seed run provenance is invalid")
    return {
        "repository": values["repository"],
        "sha": values["sha"],
        "ref": values["ref"],
        "run_id": int(values["run_id"]),
        "run_attempt": int(values["run_attempt"]),
        "environment": values["environment"],
        "workflow": values["workflow"],
    }


def dependency_lock_sha256() -> str:
    """Hash only the committed, target-specific dependency lock."""
    path = REPOSITORY_ROOT / DEPENDENCY_LOCK_RELATIVE_PATH
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise AttestedHistorySeedError("dependency lock is not a regular file")
        if not 0 < metadata.st_size <= MAX_DEPENDENCY_LOCK_BYTES:
            raise AttestedHistorySeedError("dependency lock exceeds its byte boundary")
        content = path.read_bytes()
    except AttestedHistorySeedError:
        raise
    except OSError as exc:
        raise AttestedHistorySeedError("dependency lock is unavailable") from exc
    if len(content) != metadata.st_size:
        raise AttestedHistorySeedError("dependency lock changed during bounded read")
    return sha256(content).hexdigest()


def production_dependency_lock_sha256() -> str:
    """Admit the digest of the exact GITHUB_SHA lock copy pip installed."""
    digest = os.environ.get("FF_ATTESTED_DEPENDENCY_LOCK_SHA256", "")
    if _SHA256_RE.fullmatch(digest) is None:
        raise AttestedHistorySeedError("installed dependency lock digest is invalid")
    return digest


def _clock(value: str | datetime, *, field: str) -> str:
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise AttestedHistorySeedError(f"{field} is invalid") from exc
    if parsed is None:
        raise AttestedHistorySeedError(f"{field} is required")
    return utc_text(parsed) or ""  # pragma: no cover - parsed is non-null


def _utc_now() -> str:
    # Preserve sub-second order: Company Facts capture receipts retain
    # microseconds, so truncation could make a later wall-clock sample appear
    # to predate retained evidence from the same second.
    return utc_text(datetime.now(timezone.utc)) or ""


def _clock_not_before(value: str, *lower_bounds: str, field: str) -> str:
    admitted = _clock(value, field=field)
    parsed = parse_utc(admitted, field=field)
    assert parsed is not None  # _clock already proves this.
    for index, lower in enumerate(lower_bounds):
        bound = parse_utc(_clock(lower, field=f"{field}_lower_bound_{index}"))
        assert bound is not None
        if parsed < bound:
            raise AttestedHistorySeedError(f"{field} predates retained evidence")
    return admitted


def _latest_clock(*values: str, field: str) -> str:
    if not values:
        raise AttestedHistorySeedError(f"{field} requires at least one clock")
    normalized = tuple(_clock(value, field=f"{field}_{index}") for index, value in enumerate(values))
    return max(
        normalized,
        key=lambda item: parse_utc(item, field=field) or datetime.min.replace(tzinfo=timezone.utc),
    )


def _receipt_path(object_path: str) -> str:
    path = Path(object_path)
    if path.suffix != ".gz" or path.suffixes[-2:] != [".json", ".gz"]:
        raise AttestedHistorySeedError("Submissions object path is not a gzip JSON member")
    return path.with_suffix(".receipt.json").as_posix()


def _receipt_dict(receipt: RetrievalReceipt | ArchiveReceipt | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(receipt, (RetrievalReceipt, ArchiveReceipt)):
        return asdict(receipt)
    if isinstance(receipt, Mapping):
        return dict(receipt)
    raise AttestedHistorySeedError("SEC collector returned an invalid receipt")


def read_current_submissions_receipt(
    raw_root: Path,
    receipt: RetrievalReceipt,
    *,
    max_bytes: int = MAX_SUBMISSIONS_BYTES,
) -> dict[str, Any]:
    """Read the exact immutable object returned by the current fetch.

    The mutable ``latest.json`` convenience pointer is deliberately ignored;
    another process sharing the staging root may advance it immediately after
    this seed's fetch. The returned receipt must bind the current AAPL endpoint
    and its content-addressed object is revalidated by exact length and digest.
    """
    if not isinstance(receipt, RetrievalReceipt):
        raise AttestedHistorySeedError("current Submissions receipt is invalid")
    if (
        receipt.schema != "fundamental_forensics_retrieval.v1"
        or receipt.cik != AAPL_CIK
        or receipt.endpoint != "submissions"
        or receipt.url
        != "https://data.sec.gov/submissions/CIK0000320193.json"
        or _SHA256_RE.fullmatch(receipt.sha256) is None
        or isinstance(receipt.bytes, bool)
        or not isinstance(receipt.bytes, int)
        or not 0 < receipt.bytes <= max_bytes
        or receipt.object_path
        != f"{AAPL_CIK}/submissions/{receipt.sha256}.json.gz"
    ):
        raise AttestedHistorySeedError("current Submissions receipt identity is invalid")
    root = Path(raw_root).resolve()
    source = root / receipt.object_path
    try:
        resolved = source.resolve(strict=True)
        resolved.relative_to(root)
        if resolved != source.absolute() or source.is_symlink() or not source.is_file():
            raise AttestedHistorySeedError("current Submissions object is unavailable")
        with gzip.open(source, "rb") as handle:
            content = handle.read(max_bytes + 1)
    except AttestedHistorySeedError:
        raise
    except (OSError, EOFError, ValueError) as exc:
        raise AttestedHistorySeedError("current Submissions object is unreadable") from exc
    if len(content) != receipt.bytes or sha256(content).hexdigest() != receipt.sha256:
        raise AttestedHistorySeedError("current Submissions object identity mismatch")
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttestedHistorySeedError("current Submissions object is not UTF-8 JSON") from exc
    body_cik = str(payload.get("cik") or "") if isinstance(payload, dict) else ""
    if not isinstance(payload, dict) or not body_cik.isdigit() or body_cik.zfill(10) != AAPL_CIK:
        raise AttestedHistorySeedError("current Submissions body does not bind AAPL")
    return payload


def declared_older_submissions_names(submissions: Mapping[str, Any], *, cik: str = AAPL_CIK) -> tuple[str, ...]:
    """Return every exact historical Submissions filename declared by current SEC data."""
    if not isinstance(submissions, Mapping):
        raise AttestedHistorySeedError("current Submissions response must be an object")
    filings = submissions.get("filings")
    if not isinstance(filings, Mapping):
        raise AttestedHistorySeedError("current Submissions response has no filings object")
    files = filings.get("files")
    if not isinstance(files, list):
        raise AttestedHistorySeedError("current Submissions response has no historical-files inventory")
    names: list[str] = []
    for item in files:
        if not isinstance(item, Mapping) or set(item) - {"name", "filingCount", "filingFrom", "filingTo"}:
            raise AttestedHistorySeedError("historical Submissions inventory member is invalid")
        name = item.get("name")
        if not isinstance(name, str):
            raise AttestedHistorySeedError("historical Submissions filename is invalid")
        match = _OLDER_SUBMISSIONS_RE.fullmatch(name)
        if match is None or match.group(1) != cik:
            raise AttestedHistorySeedError("historical Submissions filename does not bind AAPL CIK")
        names.append(name)
    if len(set(names)) != len(names):
        raise AttestedHistorySeedError("historical Submissions inventory contains duplicate filenames")
    if len(names) > MAX_OLDER_SUBMISSIONS_FILES:
        raise AttestedHistorySeedError(
            "historical Submissions inventory exceeds the exact file cap"
        )
    return tuple(sorted(names))


def select_latest_aapl_10k(
    submissions: Mapping[str, Any], *, recorded_at: str, as_of: str
) -> dict[str, Any]:
    """Select precisely one latest eligible AAPL 10-K from the retained response."""
    manifests = build_filing_manifests(
        submissions, cik=AAPL_CIK, ticker=AAPL_TICKER, recorded_at=recorded_at
    )
    selected = select_periodic_comparables(
        manifests, form="10-K", ticker=AAPL_TICKER, as_of=as_of, count=1
    )
    if len(selected) != 1:
        raise AttestedHistorySeedError("AAPL has no single eligible latest 10-K at the seed clock")
    manifest = selected[0]
    if (
        manifest["issuer"]["cik"] != AAPL_CIK
        or manifest["issuer"]["ticker"] != AAPL_TICKER
        or manifest["filing"]["base_form"] != "10-K"
    ):
        raise AttestedHistorySeedError("latest filing selection did not remain bound to AAPL 10-K")
    return manifest


def _archive_inventory_names(payload: Mapping[str, Any]) -> tuple[str, ...]:
    directory = payload.get("directory") if isinstance(payload, Mapping) else None
    items = directory.get("item") if isinstance(directory, Mapping) else None
    if not isinstance(items, list) or not items:
        raise AttestedHistorySeedError("selected filing archive index has no member inventory")
    if len(items) > MAX_ARCHIVE_INVENTORY_MEMBERS:
        raise AttestedHistorySeedError(
            "selected filing archive index exceeds the exact member cap"
        )
    names: list[str] = []
    for item in items:
        name = item.get("name") if isinstance(item, Mapping) else None
        if not isinstance(name, str) or not name or "/" in name or "\\" in name or name in {".", ".."}:
            raise AttestedHistorySeedError("selected filing archive index has an unsafe member name")
        names.append(name)
    if len(names) != len(set(names)):
        raise AttestedHistorySeedError("selected filing archive index has duplicate member names")
    return tuple(sorted(names))


def retain_selected_filing(
    *,
    archive_root: Path,
    manifest: Mapping[str, Any],
    user_agent: str,
    retrieved_at: str | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any], str]:
    """Retain the index and primary document, leaving all other members explicitly unrequested."""
    collector = SecFilingArchiveCollector(
        archive_root,
        user_agent=user_agent,
        max_document_bytes=MAX_DOCUMENT_BYTES,
    )
    index = archive_index_document(manifest)
    index_receipt = _receipt_dict(
        collector.fetch_document(
            index, retrieved_at=retrieved_at, max_document_bytes=MAX_DOCUMENT_BYTES
        )
    )
    if index_receipt.get("status") != "retrieved":
        raise AttestedHistorySeedError("selected filing archive index was not retained")
    index_document = document_with_retrieval(index, index_receipt)
    index_content = read_archive_document(archive_root, index_receipt)
    try:
        index_payload = json.loads(index_content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttestedHistorySeedError("selected filing archive index is not UTF-8 JSON") from exc
    inventory_names = _archive_inventory_names(index_payload)
    expanded = with_archive_documents(manifest, documents_from_archive_index(manifest, index_payload))
    primary = next(
        (item for item in expanded["documents"] if item.get("role") == "primary"), None
    )
    if not isinstance(primary, Mapping) or primary.get("document_name") not in inventory_names:
        raise AttestedHistorySeedError("selected AAPL primary document is absent from its archive index")
    primary_receipt = _receipt_dict(
        collector.fetch_document(
            primary, retrieved_at=retrieved_at, max_document_bytes=MAX_DOCUMENT_BYTES
        )
    )
    if primary_receipt.get("status") != "retrieved":
        raise AttestedHistorySeedError("selected AAPL primary document was not retained")
    materialized = with_document_retrievals(
        expanded, {str(primary["document_id"]): primary_receipt}
    )
    manifest_key = persist_filing_manifest(archive_root, materialized)
    member_states: dict[str, Any] = {name: "not_requested" for name in inventory_names}
    member_states[str(primary["document_name"])] = {
        "state": "stored",
        "content_sha256": primary_receipt["content_sha256"],
        "byte_length": primary_receipt["byte_length"],
        "storage_key": primary_receipt["storage_key"],
        "retrieval": primary_receipt,
        "policy_reason": None,
    }
    return materialized, manifest_key, index_document, member_states, str(primary["document_name"])


def _submissions_source(*, source_name: str, receipt: RetrievalReceipt, is_older: bool) -> PinnedSubmissionsSource:
    if receipt.cik != AAPL_CIK or receipt.endpoint != "submissions":
        raise AttestedHistorySeedError("retained Submissions receipt does not bind AAPL")
    return PinnedSubmissionsSource(
        source_name=source_name,
        receipt_path=_receipt_path(receipt.object_path),
        object_path=receipt.object_path,
        is_older=is_older,
    )


def build_seed_store(*, local_dir: str | Path | None = None) -> StrictConditionalWriteStore:
    """Return a prefix/action-scoped temporary seed writer.

    The parent token can carry Cloudflare's broader dashboard permission set;
    boto receives only the locally signed 30-minute child session.
    """
    if local_dir is not None:
        return LocalStore(local_dir)
    names = (
        "FF_ATTESTED_R2_SEED_ENDPOINT",
        "FF_ATTESTED_R2_SEED_ACCESS_KEY_ID",
        "FF_ATTESTED_R2_SEED_SECRET_ACCESS_KEY",
        "FF_ATTESTED_R2_SEED_BUCKET",
    )
    values = {name: os.environ.get(name, "") for name in names}
    if any(not value for value in values.values()):
        raise AttestedHistorySeedError("dedicated attested-history seed credential is unavailable")
    try:
        temporary = mint_r2_temporary_credentials(
            endpoint=values["FF_ATTESTED_R2_SEED_ENDPOINT"],
            parent_access_key_id=values["FF_ATTESTED_R2_SEED_ACCESS_KEY_ID"],
            parent_secret_access_key=values["FF_ATTESTED_R2_SEED_SECRET_ACCESS_KEY"],
            bucket=values["FF_ATTESTED_R2_SEED_BUCKET"],
            scope="object-read-write",
            actions=("GetObject", "HeadObject", "PutObject"),
        )
    except R2TemporaryCredentialError as exc:
        raise AttestedHistorySeedError(
            "dedicated seed parent rejected: " + value_free_credential_error(exc)
        ) from exc
    finally:
        os.environ.pop("FF_ATTESTED_R2_SEED_ACCESS_KEY_ID", None)
        os.environ.pop("FF_ATTESTED_R2_SEED_SECRET_ACCESS_KEY", None)
        values["FF_ATTESTED_R2_SEED_ACCESS_KEY_ID"] = ""
        values["FF_ATTESTED_R2_SEED_SECRET_ACCESS_KEY"] = ""
    try:
        import boto3
        from botocore.config import Config

        try:
            config = Config(
                region_name="auto",
                signature_version="s3v4",
                max_pool_connections=8,
                retries={"max_attempts": 3, "mode": "adaptive"},
                connect_timeout=15,
                read_timeout=60,
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            )
        except TypeError:
            config = Config(
                region_name="auto",
                signature_version="s3v4",
                max_pool_connections=8,
                retries={"max_attempts": 3, "mode": "adaptive"},
                connect_timeout=15,
                read_timeout=60,
            )
        client = boto3.client(
            "s3",
            endpoint_url=values["FF_ATTESTED_R2_SEED_ENDPOINT"],
            aws_access_key_id=temporary.access_key_id,
            aws_secret_access_key=temporary.secret_access_key,
            aws_session_token=temporary.session_token,
            config=config,
        )
    except ImportError as exc:
        raise AttestedHistorySeedError("boto3 is unavailable for the seed writer") from exc
    return R2Store(values["FF_ATTESTED_R2_SEED_BUCKET"], client=client)


def build_operator_packet(
    *,
    base_query_snapshot_id: str,
    source_snapshot_id: str,
    manifest: Mapping[str, Any],
    archive_index_document_value: Mapping[str, Any],
    member_states: Mapping[str, Any],
    ixbrl_document_name: str,
    companyfacts_paths: CompanyFactsSourcePaths,
    submissions_recorded_at: str,
    recent_submissions: PinnedSubmissionsSource,
    older_submissions: tuple[PinnedSubmissionsSource, ...],
    conversion_config: CompanyFactsLedgerConversionConfig,
) -> dict[str, Any]:
    """Compile the private exact packet accepted by the read-only operator schema."""
    return {
        "schema": "fundamental_forensics.attested_history_operator/v1",
        "base_query_snapshot_id": base_query_snapshot_id,
        "source_snapshot_id": source_snapshot_id,
        "packet": {
            "cik": AAPL_CIK,
            "ixbrl_document_name": ixbrl_document_name,
            "filing": {
                "accession": manifest["filing"]["accession"],
                "manifest_id": manifest["manifest_id"],
                "archive_index_document": dict(archive_index_document_value),
                "member_states": dict(member_states),
                "policy_profile": SEED_POLICY_PROFILE,
                "policy_version": SEED_POLICY_VERSION,
            },
            "companyfacts": {
                "manifest_path": companyfacts_paths.manifest_path,
                "capture_path": companyfacts_paths.capture_path,
                "response_path": companyfacts_paths.response_path,
                "submissions_recorded_at": submissions_recorded_at,
                "recent_submissions": {
                    "source_name": recent_submissions.source_name,
                    "receipt_path": recent_submissions.receipt_path,
                    "object_path": recent_submissions.object_path,
                    "is_older": False,
                },
                "older_submissions": [
                    {
                        "source_name": item.source_name,
                        "receipt_path": item.receipt_path,
                        "object_path": item.object_path,
                        "is_older": True,
                    }
                    for item in older_submissions
                ],
                "conversion_limits": conversion_config.conversion_kwargs(),
            },
        },
    }


def _ensure_empty_directory(path: Path, *, field: str) -> Path:
    candidate = Path(path)
    if candidate.exists() and candidate.is_symlink():
        raise AttestedHistorySeedError(f"{field} cannot be a symlink")
    candidate.mkdir(parents=True, exist_ok=True)
    if not candidate.is_dir() or any(candidate.iterdir()):
        raise AttestedHistorySeedError(f"{field} must be an empty directory")
    return candidate.resolve()


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _private_json(path: Path, value: Mapping[str, Any]) -> None:
    _private_bytes(path, canonical_json(dict(value)).encode("utf-8"))


def _private_bytes(path: Path, content: bytes) -> None:
    if not isinstance(content, bytes):
        raise AttestedHistorySeedError("review artifact content must be bytes")
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _artifact_digest(path: Path, *, maximum_bytes: int = 4 * 1024 * 1024) -> dict[str, Any]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise AttestedHistorySeedError("review artifact is not a regular file")
        if not 0 < metadata.st_size <= maximum_bytes:
            raise AttestedHistorySeedError("review artifact exceeds its byte boundary")
        content = path.read_bytes()
    except AttestedHistorySeedError:
        raise
    except OSError as exc:
        raise AttestedHistorySeedError("review artifact is unavailable") from exc
    if len(content) != metadata.st_size:
        raise AttestedHistorySeedError("review artifact changed during bounded read")
    return {
        "filename": path.name,
        "sha256": sha256(content).hexdigest(),
        "bytes": len(content),
    }


def _storage_control_key(token: str | None = None) -> str:
    """Build one opaque, bounded control object key without discovery I/O."""
    value = secrets.token_hex(16) if token is None else token
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise AttestedHistorySeedError("storage control token is invalid")
    return f"{STORAGE_CONTROL_PREFIX}/{value}"


def run_storage_control_probe(
    *,
    writer_store: StrictConditionalWriteStore,
    readonly_store: StrictBoundedReadStore,
    token: str | None = None,
) -> dict[str, Any]:
    """Prove CAS and cross-role reads before acquiring or writing SEC evidence.

    The probe is deliberately a create-once control object—not a discoverable
    prefix, a cleanup routine, or a generic object-store health check.  It
    establishes the exact semantics relied on by immutable snapshot writes:
    absence-only creation, exact-version replacement, and stale-writer
    rejection.  A separately supplied read-only client must then read the
    final bytes from the shared bucket.  No list, delete, or fail-open store
    primitive is permitted in this boundary.
    """
    if not isinstance(writer_store, StrictConditionalWriteStore):
        raise AttestedHistorySeedError(
            "seed writer lacks strict conditional-write capability"
        )
    if not isinstance(readonly_store, StrictBoundedReadStore):
        raise AttestedHistorySeedError("storage control reader lacks strict bounded reads")
    if writer_store is readonly_store:
        raise AttestedHistorySeedError("storage control reader must be separately supplied")

    key = _storage_control_key(token)
    initial_payload = b"fundamental-forensics/attested-history-seed-control/v1:initial"
    conflict_payload = b"fundamental-forensics/attested-history-seed-control/v1:conflict"
    final_payload = b"fundamental-forensics/attested-history-seed-control/v1:final"
    if max(len(initial_payload), len(conflict_payload), len(final_payload)) > MAX_STORAGE_CONTROL_BYTES:
        raise AttestedHistorySeedError("storage control payload exceeds its byte boundary")

    try:
        writer_store.validate_strict_conditional_write_capability()

        absent = writer_store.get_bytes_strict_bounded_versioned(
            key, MAX_STORAGE_CONTROL_BYTES
        )
        if absent.data is not None or absent.version is not None:
            raise AttestedHistorySeedError("storage control key was unexpectedly present")

        if not writer_store.put_bytes_strict_conditional(
            key,
            initial_payload,
            expected_version=None,
            content_type="application/octet-stream",
        ):
            raise AttestedHistorySeedError("storage control absent create was rejected")
        initial = writer_store.get_bytes_strict_bounded_versioned(
            key, MAX_STORAGE_CONTROL_BYTES
        )
        if initial.data != initial_payload or initial.version is None:
            raise AttestedHistorySeedError("storage control initial readback was not exact")

        if writer_store.put_bytes_strict_conditional(
            key,
            conflict_payload,
            expected_version=None,
            content_type="application/octet-stream",
        ):
            raise AttestedHistorySeedError("storage control conflicting create was accepted")
        conflict_readback = writer_store.get_bytes_strict_bounded_versioned(
            key, MAX_STORAGE_CONTROL_BYTES
        )
        if (
            conflict_readback.data != initial_payload
            or conflict_readback.version != initial.version
        ):
            raise AttestedHistorySeedError("storage control conflicting create changed the object")

        if not writer_store.put_bytes_strict_conditional(
            key,
            final_payload,
            expected_version=initial.version,
            content_type="application/octet-stream",
        ):
            raise AttestedHistorySeedError("storage control exact-version advance was rejected")
        advanced = writer_store.get_bytes_strict_bounded_versioned(
            key, MAX_STORAGE_CONTROL_BYTES
        )
        if (
            advanced.data != final_payload
            or advanced.version is None
            or advanced.version == initial.version
        ):
            raise AttestedHistorySeedError("storage control advanced readback was not exact")

        if writer_store.put_bytes_strict_conditional(
            key,
            conflict_payload,
            expected_version=initial.version,
            content_type="application/octet-stream",
        ):
            raise AttestedHistorySeedError("storage control stale version was accepted")
        final_readback = writer_store.get_bytes_strict_bounded_versioned(
            key, MAX_STORAGE_CONTROL_BYTES
        )
        if final_readback.data != final_payload or final_readback.version != advanced.version:
            raise AttestedHistorySeedError("storage control stale write changed the object")

        readonly_final = readonly_store.get_bytes_strict_bounded(key, len(final_payload))
        if readonly_final != final_payload:
            raise AttestedHistorySeedError("storage control read-only final readback was not exact")
    except AttestedHistorySeedError:
        raise
    except Exception as exc:
        raise AttestedHistorySeedError("storage control probe failed") from exc

    return {
        "key": key,
        "final_sha256": sha256(final_payload).hexdigest(),
        "outcomes": {
            "absent_before_create": True,
            "absent_create_succeeded": True,
            "conflicting_absent_create_rejected": True,
            "exact_version_advance_succeeded": True,
            "stale_version_advance_rejected": True,
            "readonly_final_readback_verified": True,
        },
    }


def run_seed_preflight(
    *, packet_bytes: bytes, readonly_store: StrictBoundedReadStore, observed_at: str
) -> dict[str, Any]:
    """Run the seed packet only through the distinct read-only client."""
    spec = operator_spec_from_bytes(packet_bytes)
    preflight = run_readonly_preflight(
        spec=spec,
        store=readonly_store,
        operator_verification_observed_at=observed_at,
    )
    if preflight["status"] != "prepared" or preflight["publication"]["storage_write_attempts"] != 0:
        raise AttestedHistorySeedError("read-only preflight did not produce a zero-write prepared candidate")
    return preflight


def run_aapl_seed(
    *,
    work_dir: str | Path,
    output_dir: str | Path,
    user_agent: str,
    writer_store: StrictConditionalWriteStore,
    readonly_store: StrictBoundedReadStore,
    now: Callable[[], str] = _utc_now,
    run_provenance: Mapping[str, Any] | None = None,
    dependency_lock_digest: str | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute the full seed graph and return compact, non-raw private metadata.

    Tests pass a local store and mocked collectors; production supplies separate
    R2 writer/read-only stores.  Any missing source member, non-primary archive
    retrieval, parser failure, no-binding result, or preflight write attempt
    aborts before a success receipt is emitted. The seed writes only named
    immutable source/base objects; it never advances a global latest pointer,
    including on any partial/failing path.

    ``on_stage`` receives the static name of each phase as it is entered, so a
    failure the CLI cannot describe can still be localised.  It is diagnostics
    only: the names are code literals, it observes nothing about the evidence,
    and it never changes what is acquired, written, or emitted.
    """

    def _stage(name: str) -> None:
        if on_stage is not None:
            on_stage(name)

    if not isinstance(writer_store, StrictConditionalWriteStore):
        raise AttestedHistorySeedError("seed writer lacks strict conditional-write capability")
    if not isinstance(readonly_store, StrictBoundedReadStore):
        raise AttestedHistorySeedError("read-only preflight store lacks strict bounded reads")
    if run_provenance is None:
        admitted_run_provenance: dict[str, Any] = {"mode": "hermetic_local"}
    else:
        admitted_run_provenance = dict(run_provenance)
        if set(admitted_run_provenance) != {
            "repository",
            "sha",
            "ref",
            "run_id",
            "run_attempt",
            "environment",
            "workflow",
        } or (
            admitted_run_provenance.get("repository") != EXPECTED_GITHUB_REPOSITORY
            or admitted_run_provenance.get("ref") != EXPECTED_GITHUB_REF
            or admitted_run_provenance.get("environment") != EXPECTED_GITHUB_ENVIRONMENT
            or admitted_run_provenance.get("workflow") != EXPECTED_GITHUB_WORKFLOW
            or not isinstance(admitted_run_provenance.get("sha"), str)
            or _GITHUB_SHA_RE.fullmatch(admitted_run_provenance["sha"]) is None
            or isinstance(admitted_run_provenance.get("run_id"), bool)
            or not isinstance(admitted_run_provenance.get("run_id"), int)
            or admitted_run_provenance["run_id"] < 1
            or isinstance(admitted_run_provenance.get("run_attempt"), bool)
            or not isinstance(admitted_run_provenance.get("run_attempt"), int)
            or admitted_run_provenance["run_attempt"] < 1
        ):
            raise AttestedHistorySeedError("seed run provenance is invalid")
    lock_digest = dependency_lock_digest or dependency_lock_sha256()
    if not isinstance(lock_digest, str) or _SHA256_RE.fullmatch(lock_digest) is None:
        raise AttestedHistorySeedError("dependency lock digest is invalid")
    if "@" not in str(user_agent):
        raise AttestedHistorySeedError("SEC user agent must identify an application and contact email")
    work = _ensure_empty_directory(Path(work_dir), field="work_dir")
    output = _ensure_empty_directory(Path(output_dir), field="output_dir")
    if _paths_overlap(work, output):
        raise AttestedHistorySeedError("work_dir and review output_dir cannot overlap")
    _stage("storage-control-probe")
    storage_control_probe = run_storage_control_probe(
        writer_store=writer_store,
        readonly_store=readonly_store,
    )
    raw_root = work / "raw"
    archive_root = work / "archive"
    raw_root.mkdir()
    archive_root.mkdir()

    _stage("acquire-submissions")
    submissions_collector = SecForensicsCollector(
        raw_root, user_agent=user_agent, max_response_bytes=MAX_SUBMISSIONS_BYTES
    )
    recent_receipt = submissions_collector.fetch(
        AAPL_CIK,
        "submissions",
        max_response_bytes=MAX_SUBMISSIONS_BYTES,
    )
    current_submissions = read_current_submissions_receipt(
        raw_root, recent_receipt, max_bytes=MAX_SUBMISSIONS_BYTES
    )
    older_names = declared_older_submissions_names(current_submissions)
    older_receipts = tuple(
        submissions_collector.fetch_historical_submissions_file(
            AAPL_CIK,
            name,
            max_response_bytes=MAX_SUBMISSIONS_BYTES,
        )
        for name in older_names
    )
    recent_source = _submissions_source(
        source_name="recent", receipt=recent_receipt, is_older=False
    )
    older_sources = tuple(
        _submissions_source(source_name=name, receipt=receipt, is_older=True)
        for name, receipt in zip(older_names, older_receipts, strict=True)
    )

    submissions_recorded_at = _latest_clock(
        recent_receipt.retrieved_at,
        *(receipt.retrieved_at for receipt in older_receipts),
        field="submissions_recorded_at",
    )
    selected_manifest = select_latest_aapl_10k(
        current_submissions,
        recorded_at=submissions_recorded_at,
        as_of=submissions_recorded_at,
    )
    _stage("acquire-filing")
    final_manifest, _manifest_key, index_document, member_states, primary_name = retain_selected_filing(
        archive_root=archive_root,
        manifest=selected_manifest,
        user_agent=user_agent,
    )

    # Company Facts requires an observed, near-contemporaneous capture clock;
    # do not reuse the potentially older Submissions acquisition clock.
    companyfacts_clock = _clock_not_before(
        now(),
        submissions_recorded_at,
        field="companyfacts_source_snapshot_at",
    )
    _stage("acquire-companyfacts")
    companyfacts_result = acquire_companyfacts(
        targets=((AAPL_TICKER, AAPL_CIK),),
        raw_root=raw_root,
        archive_root=archive_root,
        user_agent=user_agent,
        source_snapshot_at=companyfacts_clock,
        recorded_at=companyfacts_clock,
        max_tickers=1,
        max_response_bytes=MAX_COMPANYFACTS_BYTES,
        max_ticker_bytes=MAX_COMPANYFACTS_BYTES,
        max_total_bytes=MAX_COMPANYFACTS_BYTES,
    )
    ticker_receipts = companyfacts_result.get("run", {}).get("ticker_receipts", [])
    if not isinstance(ticker_receipts, list) or len(ticker_receipts) != 1:
        raise AttestedHistorySeedError("AAPL Company Facts acquisition did not return one receipt")
    companyfacts_receipt = ticker_receipts[0]
    if not isinstance(companyfacts_receipt, Mapping) or companyfacts_receipt.get("status") != "complete":
        raise AttestedHistorySeedError("AAPL Company Facts acquisition is incomplete")
    manifest_key = companyfacts_receipt.get("manifest_key")
    if not isinstance(manifest_key, str):
        raise AttestedHistorySeedError("AAPL Company Facts receipt omitted its manifest key")
    companyfacts_manifest = read_companyfacts_manifest(archive_root, manifest_key)
    companyfacts_paths = CompanyFactsSourcePaths(
        manifest_path=manifest_key,
        capture_path=companyfacts_manifest["source"]["capture_receipt_key"],
        response_path=companyfacts_manifest["source"]["response_object_path"],
    )

    index_retrieval = index_document.get("retrieval")
    primary_retrieval = member_states.get(primary_name)
    if not isinstance(index_retrieval, Mapping) or not isinstance(primary_retrieval, Mapping):
        raise AttestedHistorySeedError("archive retrieval clocks are unavailable")
    primary_retrieval_value = primary_retrieval.get("retrieval")
    if not isinstance(primary_retrieval_value, Mapping):
        raise AttestedHistorySeedError("primary retrieval clock is unavailable")
    companyfacts_clocks = companyfacts_receipt.get("clocks")
    companyfacts_recorded_at = (
        companyfacts_clocks.get("recorded_at")
        if isinstance(companyfacts_clocks, Mapping)
        else None
    )
    if not isinstance(companyfacts_recorded_at, str):
        raise AttestedHistorySeedError("Company Facts receipt omitted its retention clock")
    source_snapshot_at = _clock_not_before(
        now(),
        submissions_recorded_at,
        str(index_retrieval.get("retrieved_at") or ""),
        str(primary_retrieval_value.get("retrieved_at") or ""),
        companyfacts_recorded_at,
        field="source_snapshot_at",
    )
    _stage("source-snapshot")
    source_snapshot = sync_source_roots(
        raw_root=raw_root,
        archive_root=archive_root,
        store=writer_store,
        snapshot_at=source_snapshot_at,
        max_files=MAX_SOURCE_FILES,
        max_file_bytes=MAX_COMPANYFACTS_BYTES,
        max_total_bytes=MAX_SOURCE_TOTAL_BYTES,
        publish_latest=False,
    )
    _stage("base-candidate")
    authority = PinnedSourceAuthority(store=writer_store, snapshot_id=source_snapshot.snapshot_id)
    conversion_config = CompanyFactsLedgerConversionConfig()
    conversion = load_companyfacts_ledger_from_pinned_source(
        authority=authority,
        source_bundle=CompanyFactsConversionSourceBundle(
            cik=AAPL_CIK,
            companyfacts_manifest_path=companyfacts_paths.manifest_path,
            companyfacts_capture_path=companyfacts_paths.capture_path,
            companyfacts_response_path=companyfacts_paths.response_path,
            recent_submissions=recent_source,
            older_submissions=older_sources,
        ),
        submissions_recorded_at=submissions_recorded_at,
        config=conversion_config,
    )
    package = materialize_filing_package_from_pinned_source(
        PinnedFilingPackageDescriptor(
            cik=AAPL_CIK,
            accession=str(final_manifest["filing"]["accession"]),
            manifest_id=str(final_manifest["manifest_id"]),
            archive_index_document=index_document,
            member_states=member_states,
        ),
        authority=authority,
        assembled_at=source_snapshot_at,
        policy_profile=SEED_POLICY_PROFILE,
        policy_version=SEED_POLICY_VERSION,
    )
    selected = next(
        item for item in package.to_dict()["inventory"] if item["document_name"] == primary_name
    )
    member = authority.read_archive_document(
        storage_key=selected["storage_key"],
        expected_receipt=selected["retrieval"],
        maximum_bytes=selected["byte_length"],
    )
    extraction = build_ixbrl_extraction(
        package, primary_name, member.content, computed_at=source_snapshot_at
    )
    attestation = build_filing_attestation(
        package,
        extraction,
        authority=authority,
        companyfacts_paths=companyfacts_paths,
        attested_at=source_snapshot_at,
    )
    prepared_base = prepare_attested_history_base_candidate(
        conversion=conversion,
        attestation=attestation,
        ticker=AAPL_TICKER,
        source_snapshot_at=source_snapshot_at,
        recorded_at=source_snapshot_at,
        computed_at=source_snapshot_at,
        published_at=source_snapshot_at,
    )
    base_snapshot = publish_query_snapshot(
        writer_store,
        prepared_base.prepared,
        publish_latest=False,
    )
    packet = build_operator_packet(
        base_query_snapshot_id=base_snapshot.snapshot_id,
        source_snapshot_id=source_snapshot.snapshot_id,
        manifest=final_manifest,
        archive_index_document_value=index_document,
        member_states=member_states,
        ixbrl_document_name=primary_name,
        companyfacts_paths=companyfacts_paths,
        submissions_recorded_at=submissions_recorded_at,
        recent_submissions=recent_source,
        older_submissions=older_sources,
        conversion_config=conversion_config,
    )
    packet_bytes = canonical_json(dict(packet)).encode("utf-8")
    if len(packet_bytes) > MAX_OPERATOR_PACKET_BYTES:
        raise AttestedHistorySeedError("operator packet exceeds its byte boundary")
    # This run emits a review copy. A later committed packet is still required
    # before the production CLI's Git-bound operator admission.
    operator_verification_observed_at = _clock_not_before(
        now(), source_snapshot_at, field="operator_verification_observed_at"
    )
    _stage("preflight")
    preflight = run_seed_preflight(
        packet_bytes=packet_bytes,
        readonly_store=readonly_store,
        observed_at=operator_verification_observed_at,
    )
    preflight_completed_at = _clock_not_before(
        now(), operator_verification_observed_at, field="preflight_completed_at"
    )
    _stage("review-artifacts")
    packet_path = output / SEED_PACKET_FILENAME
    preflight_path = output / "attested_history_preflight_receipt.json"
    seed_path = output / SEED_RECEIPT_FILENAME
    _private_bytes(packet_path, packet_bytes)
    write_private_receipt(output, preflight)
    packet_artifact = _artifact_digest(
        packet_path, maximum_bytes=MAX_OPERATOR_PACKET_BYTES
    )
    preflight_artifact = _artifact_digest(preflight_path)
    seed_receipt = {
        "schema": SEED_SCHEMA,
        "status": "prepared",
        "ticker": AAPL_TICKER,
        "cik": AAPL_CIK,
        "source_snapshot_id": source_snapshot.snapshot_id,
        "base_query_snapshot_id": base_snapshot.snapshot_id,
        "clocks": {
            "source_snapshot_at": source_snapshot_at,
            "operator_verification_observed_at": operator_verification_observed_at,
            "preflight_completed_at": preflight_completed_at,
        },
        "dependency_lock": {
            "path": DEPENDENCY_LOCK_RELATIVE_PATH.as_posix(),
            "sha256": lock_digest,
            "target": "CPython 3.12 macOS arm64",
        },
        "run_provenance": admitted_run_provenance,
        "selected_occurrence_id": prepared_base.selected_occurrence_id,
        "selected_match_id": prepared_base.selected_match_id,
        "declared_older_submissions_count": len(older_sources),
        "archive_inventory_member_count": len(member_states),
        "archive_stored_member_count": 1,
        "archive_not_requested_member_count": len(member_states) - 1,
        "storage_control_probe": storage_control_probe,
        "preflight": {
            "status": preflight["status"],
            "storage_write_attempts": preflight["publication"]["storage_write_attempts"],
        },
        "review_artifacts": {
            "operator_packet": packet_artifact,
            "preflight_receipt": preflight_artifact,
        },
        "nonclaims": [
            "not_a_complete_filing_archive",
            "not_a_dimensions_identity_claim",
            "not_a_freshness_claim_after_preflight",
            "not_investment_or_trading_authority",
        ],
    }
    _private_json(seed_path, seed_receipt)
    seed_artifact = _artifact_digest(seed_path)
    bundle_assembled_at = _clock_not_before(
        now(), preflight_completed_at, field="bundle_assembled_at"
    )
    bundle_receipt = {
        "schema": SEED_BUNDLE_SCHEMA,
        "status": "prepared",
        "run_provenance": admitted_run_provenance,
        "dependency_lock": {
            "path": DEPENDENCY_LOCK_RELATIVE_PATH.as_posix(),
            "sha256": lock_digest,
        },
        "files": {
            SEED_PACKET_FILENAME: packet_artifact,
            "attested_history_preflight_receipt.json": preflight_artifact,
            SEED_RECEIPT_FILENAME: seed_artifact,
        },
        "assembled_at": bundle_assembled_at,
        "nonclaims": [
            "review_artifact_not_canonical_publication",
            "credential_separation_not_parent_iam_proof",
        ],
    }
    _private_json(output / SEED_BUNDLE_RECEIPT_FILENAME, bundle_receipt)
    return seed_receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-aapl-seed", action="store_true", help="required explicit one-shot authority")
    parser.add_argument("--work-dir", required=True, help="new empty local SEC staging directory")
    parser.add_argument("--output-dir", required=True, help="new empty review-artifact directory")
    parser.add_argument("--sec-user-agent", required=True, help="SEC-required application and contact email")
    parser.add_argument("--local-store", help="hermetic test-only private store; production requires separate R2 credentials")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.enable_aapl_seed:
        print("::error title=fundamental_forensics_attested_history_seed::explicit AAPL seed enablement is required", flush=True)
        return 2
    # The runner's RUNNER_TEMP working directories are wiped between jobs and
    # this command writes nothing before full success, so the annotation below
    # is the ONLY operator-facing evidence a failing run ever produces. It used
    # to discard the safe signal along with the unsafe detail and point at
    # "protected runner diagnostics" that have never existed. Stage names are
    # code literals, so they localise an opaque failure without leaking.
    stage = "startup"

    def _enter(name: str) -> None:
        nonlocal stage
        stage = name

    try:
        _enter("environment-boundary")
        if args.local_store is None:
            # This production authority boundary must precede filesystem,
            # network, object-store, and credential-mint I/O.
            validate_production_environment_boundary()
            _enter("run-provenance")
            run_provenance = production_run_provenance()
        else:
            run_provenance = None
        _enter("dependency-lock")
        lock_digest = (
            production_dependency_lock_sha256()
            if args.local_store is None
            else dependency_lock_sha256()
        )
        _enter("writer-store")
        writer = build_seed_store(local_dir=args.local_store)
        _enter("readonly-store")
        readonly = (
            LocalStore(args.local_store)
            if args.local_store is not None
            else build_readonly_operator_store()
        )
        _enter("seed-inputs")
        run_aapl_seed(
            work_dir=args.work_dir,
            output_dir=args.output_dir,
            user_agent=args.sec_user_agent,
            writer_store=writer,
            readonly_store=readonly,
            run_provenance=run_provenance,
            dependency_lock_digest=lock_digest,
            on_stage=_enter,
        )
    except AttestedHistorySeedError as exc:
        # Value-free by construction — see AttestedHistorySeedError. Every raise
        # site was audited (2026-08-09): static sentences, or a {field} NAME.
        print(f"::error title=fundamental_forensics_attested_history_seed::seed failed at stage {stage}: {_annotation_message(str(exc))}", flush=True)
        return 1
    except Exception as exc:
        # Anything else can carry source paths or remote endpoint detail in its
        # message, so ONLY the class name crosses the boundary — never the
        # message, never the traceback. The review artifact is still emitted
        # only after full success.
        print(f"::error title=fundamental_forensics_attested_history_seed::seed failed at stage {stage}: unexpected {type(exc).__name__} (detail suppressed)", flush=True)
        return 1
    print("::notice title=fundamental_forensics_attested_history_seed::AAPL seed and zero-write preflight completed; retrieve review artifacts", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
