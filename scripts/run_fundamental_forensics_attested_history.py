"""Read-only preflight for one sealed Fundamental Forensics history packet.

This is deliberately *not* a publisher.  It requires a version-controlled
packet which names every immutable ``ffqs_`` and ``ffsecsrc_`` dependency,
builds the existing B4D materialization graph offline, and may construct a
private B4A candidate only in memory.  It never discovers a latest pointer,
collects from SEC, renders state, writes R2, or invokes the B4 publisher.

The CLI has no production default packet.  A packet is introduced separately
only after an operator has sealed every source path and reviewed its inventory.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
# Re-exported for callers and tests that recompute a child credential's derived
# secret against this module's namespace; the signing itself now lives in
# engine.fundamental_forensics.attested_history_credentials.
from hashlib import sha256  # noqa: F401
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# The R2 child-credential primitives moved into engine/ so the long-running
# receipt API can reuse them without importing from scripts/.  They are bound
# at module scope here so every unqualified call below still resolves, a
# monkeypatch of this module's ``mint_r2_temporary_credentials`` still affects
# this module's callers, and callers/tests may keep importing them from here.
# Only the two names this module actually uses. The minting primitives moved to
# the engine so the long-running API never imports scripts/; re-exporting the
# other nine here would be dead surface with no consumer in the repo, and it
# would imply a compatibility contract nothing is asking for. Import them from
# engine.fundamental_forensics.attested_history_credentials directly.
from engine.fundamental_forensics.attested_history_credentials import (
    R2TemporaryCredentialError,
    mint_r2_temporary_credentials,
    value_free_credential_error,
)  # noqa: E402
from engine.fundamental_forensics.attested_history_materializer import (
    B4D_REJECTION_REASON_CODES,
    AttestedBindingReport,
    enumerate_attested_binding_candidates,
)  # noqa: E402
from engine.fundamental_forensics.attested_query_snapshots import (
    AttestationMaterial,
    PreparedAttestedQuerySnapshot,
    _verified_base_snapshot,
    prepare_attested_query_snapshot,
)  # noqa: E402
from engine.fundamental_forensics.companyfacts_ledger import (
    CompanyFactsConversionSourceBundle,
    CompanyFactsLedgerConversion,
    CompanyFactsLedgerConversionConfig,
    PinnedSubmissionsSource,
    load_companyfacts_ledger_from_pinned_source,
)  # noqa: E402
from engine.fundamental_forensics.filing_attestation import (
    CompanyFactsSourcePaths,
    FilingAttestation,
    PinnedSourceAuthority,
    build_filing_attestation,
    gzip_stored_byte_ceiling,
)  # noqa: E402
from engine.fundamental_forensics.filing_package import (
    FilingPackage,
    PinnedFilingPackageDescriptor,
    materialize_filing_package_from_pinned_source,
)  # noqa: E402
from engine.fundamental_forensics.ixbrl_extraction import (
    IxbrlExtraction,
    build_ixbrl_extraction,
)  # noqa: E402
from engine.fundamental_forensics.models import parse_utc, utc_text  # noqa: E402
from engine.fundamental_forensics.query_snapshots import QuerySnapshot  # noqa: E402
from engine.fundamental_forensics.source_sync import build_private_source_store  # noqa: E402
from engine.research_vault.r2_store import R2Store, StrictBoundedReadStore  # noqa: E402


OPERATOR_SCHEMA = "fundamental_forensics.attested_history_operator/v1"
RECEIPT_SCHEMA = "fundamental_forensics.attested_history_preflight_receipt/v1"
MAX_SPEC_BYTES = 2 * 1024 * 1024
MAX_RECEIPT_BYTES = 256 * 1024
MAX_OPERATOR_MEMBER_STATES = 4_096
MAX_RECEIPT_COVERAGE_ROWS = 2_048
MAX_RECEIPT_REJECTION_REASONS = len(B4D_REJECTION_REASON_CODES)
MAX_RECEIPT_REJECTION_REASON_COUNT = 250_000
CANONICAL_OPERATOR_PACKET_RELATIVE_PATH = Path(
    "config/fundamental_forensics/attested_history_operator.v1.json"
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_FAILURE_PHASES = frozenset(
    {
        "packet_admission",
        "packet_read",
        "store_initialization",
        "materialization",
        "binding_plan",
        "candidate_prepare",
        "receipt_write",
    }
)
_REJECTION_REASON_CODES = B4D_REJECTION_REASON_CODES
_FFQS_RE = re.compile(r"^ffqs_[a-f0-9]{64}$")
_FFSECSRC_RE = re.compile(r"^ffsecsrc_[a-f0-9]{64}$")
_CIK_RE = re.compile(r"^[0-9]{10}$")
_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_MANIFEST_RE = re.compile(r"^ffsec_manifest_[a-f0-9]{64}$")
_PATH_FORBIDDEN_RE = re.compile(r"(^|/)(?:latest(?:\.json)?)(?:/|$)", re.IGNORECASE)


class OperatorPreflightError(RuntimeError):
    """A sealed operator packet cannot be consumed safely."""


class ReadOnlyWriteAttempt(OperatorPreflightError):
    """A supposedly read-only dependency attempted a storage mutation."""

    def __init__(self, message: str, *, write_attempts: int) -> None:
        super().__init__(message)
        self.write_attempts = write_attempts


@dataclass(frozen=True)
class OperatorPacket:
    cik: str
    accession: str
    manifest_id: str
    archive_index_document: Mapping[str, Any]
    member_states: Mapping[str, Any] | tuple[Mapping[str, Any], ...]
    policy_profile: str
    policy_version: str
    ixbrl_document_name: str
    companyfacts_paths: CompanyFactsSourcePaths
    submissions_recorded_at: str
    recent_submissions: PinnedSubmissionsSource
    older_submissions: tuple[PinnedSubmissionsSource, ...]
    conversion_config: CompanyFactsLedgerConversionConfig


@dataclass(frozen=True)
class OperatorSpec:
    base_query_snapshot_id: str
    source_snapshot_id: str
    packet: OperatorPacket


@dataclass(frozen=True)
class MaterializedOperatorInputs:
    base_snapshot: QuerySnapshot
    package: FilingPackage
    extraction: IxbrlExtraction
    attestation: FilingAttestation
    material: AttestationMaterial
    conversion: CompanyFactsLedgerConversion


class ReadOnlyStrictStore:
    """A strict reader that makes any storage mutation observable and fatal.

    The wrapped store is deliberately not exposed.  The class still implements
    the legacy ``Store`` method names because ``StrictBoundedReadStore`` is a
    runtime protocol which inherits them.  Methods outside exact bounded reads
    fail rather than opening a discovery or legacy-read side channel.
    """

    def __init__(self, backing: StrictBoundedReadStore) -> None:
        if not isinstance(backing, StrictBoundedReadStore):
            raise OperatorPreflightError(
                "read-only preflight requires a StrictBoundedReadStore"
            )
        self._backing = backing
        self.write_attempts = 0

    def get_bytes_strict_bounded(self, key: str, maximum_bytes: int) -> bytes | None:
        return self._backing.get_bytes_strict_bounded(key, maximum_bytes)

    def get_bytes_strict(self, key: str) -> bytes | None:
        del key
        raise OperatorPreflightError("read-only preflight forbids unbounded strict reads")

    def get_bytes(self, key: str) -> bytes | None:
        del key
        raise OperatorPreflightError("read-only preflight forbids legacy unbounded reads")

    def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> bool:
        del key, data, content_type
        self.write_attempts += 1
        raise ReadOnlyWriteAttempt(
            "read-only preflight attempted a storage write",
            write_attempts=self.write_attempts,
        )

    def put_bytes_strict_conditional(
        self,
        key: str,
        data: bytes,
        *,
        expected_version: str | None,
        content_type: str = "application/octet-stream",
    ) -> bool:
        del key, data, expected_version, content_type
        self.write_attempts += 1
        raise ReadOnlyWriteAttempt(
            "read-only preflight attempted a conditional storage write",
            write_attempts=self.write_attempts,
        )

    def list_prefix(self, prefix: str) -> list[str]:
        del prefix
        raise OperatorPreflightError("read-only preflight forbids storage discovery")

    def exists(self, key: str) -> bool:
        del key
        raise OperatorPreflightError("read-only preflight forbids storage discovery")

    def upload_time(self, key: str) -> str | None:
        del key
        raise OperatorPreflightError("read-only preflight forbids storage discovery")

    def delete(self, key: str) -> None:
        del key
        self.write_attempts += 1
        raise ReadOnlyWriteAttempt(
            "read-only preflight attempted a storage delete",
            write_attempts=self.write_attempts,
        )


def _object(value: Any, *, field: str, required: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise OperatorPreflightError(f"{field} must be an object")
    if set(value) != required:
        raise OperatorPreflightError(f"{field} has unsupported or missing fields")
    return value


def _array(value: Any, *, field: str, maximum: int) -> list[Any]:
    if type(value) is not list or len(value) > maximum:
        raise OperatorPreflightError(f"{field} must be a bounded array")
    return value


def _text(value: Any, *, field: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise OperatorPreflightError(f"{field} must be bounded non-empty text")
    return value


def _identifier(value: Any, *, field: str, pattern: re.Pattern[str]) -> str:
    text = _text(value, field=field, maximum=160)
    if pattern.fullmatch(text) is None:
        raise OperatorPreflightError(f"{field} is invalid")
    return text


def _source_path(value: Any, *, field: str) -> str:
    text = _text(value, field=field, maximum=2_048)
    if (
        text.startswith(("/", "\\"))
        or "\\" in text
        or "//" in text
        or ".." in text.split("/")
        or _PATH_FORBIDDEN_RE.search(text) is not None
    ):
        raise OperatorPreflightError(f"{field} is not an immutable relative source path")
    return text


def _repository_path() -> Path:
    """Return the real repository root without accepting a caller-owned root."""
    try:
        root = REPOSITORY_ROOT.resolve(strict=True)
    except OSError as exc:
        raise OperatorPreflightError("operator repository root is unavailable") from exc
    if not root.is_dir():
        raise OperatorPreflightError("operator repository root is invalid")
    return root


def _admit_production_packet_path(path: str | Path) -> tuple[Path, str]:
    """Admit only the canonical packet path on the production R2 path.

    A local-store invocation is the explicit hermetic-test escape hatch.  The
    production reader must not turn an arbitrary runner-local JSON file into a
    provenance receipt merely because its contents happen to be well formed.
    The subsequent byte reader binds the captured file descriptor bytes to the
    exact HEAD and index blobs before those bytes are parsed.
    """
    root = _repository_path()
    canonical = root / CANONICAL_OPERATOR_PACKET_RELATIVE_PATH
    try:
        candidate = Path(os.path.abspath(os.fspath(path)))
    except OSError as exc:
        raise OperatorPreflightError("production operator packet is unavailable") from exc
    if candidate != canonical:
        raise OperatorPreflightError("production operator packet must use the canonical tracked path")
    try:
        info = canonical.lstat()
    except OSError as exc:
        raise OperatorPreflightError("production operator packet is unavailable") from exc
    if stat.S_ISLNK(info.st_mode):
        raise OperatorPreflightError("production operator packet cannot be a symlink")
    return canonical, CANONICAL_OPERATOR_PACKET_RELATIVE_PATH.as_posix()


def _read_regular_file_bounded(location: Path, *, maximum_bytes: int) -> bytes:
    """Read one local packet with descriptor-bound type and byte ceilings.

    The packet is a local ingress boundary on a self-hosted runner.  Never
    check a pathname and then reopen it through ``Path.read_bytes``: an attacker
    could replace it with a symlink or grow it in the gap.  The file descriptor
    is opened once with ``O_NOFOLLOW`` and is checked before *and* after a
    max+1 byte read.
    """
    if not isinstance(maximum_bytes, int) or isinstance(maximum_bytes, bool) or maximum_bytes < 1:
        raise OperatorPreflightError("operator packet byte ceiling is invalid")
    if not hasattr(os, "O_NOFOLLOW"):
        raise OperatorPreflightError("operator platform lacks no-follow packet reads")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(os.fspath(location), flags)
    except OSError as exc:
        raise OperatorPreflightError("operator packet cannot be opened safely") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size < 0 or before.st_size > maximum_bytes:
            raise OperatorPreflightError("operator packet is not a bounded regular file")
        remaining = maximum_bytes + 1
        chunks: list[bytes] = []
        while remaining:
            try:
                chunk = os.read(descriptor, min(65_536, remaining))
            except OSError as exc:
                raise OperatorPreflightError("operator packet cannot be read safely") from exc
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        len(content) > maximum_bytes
        or len(content) != before.st_size
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    ):
        raise OperatorPreflightError("operator packet changed or exceeded its byte limit while read")
    return content


def _read_git_blob_bounded(*, root: Path, object_name: str, maximum_bytes: int) -> bytes:
    """Read one Git blob without assuming SHA-1/SHA-256 object-id format.

    ``git cat-file blob <tree-ish:path>`` works for both supported Git object
    formats. Its stdout is read max+1 bytes, never through an unbounded
    ``communicate`` buffer, so a corrupt config blob is not an allocation path.
    """
    if not isinstance(maximum_bytes, int) or isinstance(maximum_bytes, bool) or maximum_bytes < 1:
        raise OperatorPreflightError("Git packet byte ceiling is invalid")
    try:
        process = subprocess.Popen(
            ("git", "-C", os.fspath(root), "cat-file", "blob", object_name),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise OperatorPreflightError("production operator packet Git blob cannot be read") from exc
    stream = process.stdout
    if stream is None:
        try:
            process.kill()
            process.wait(timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
        raise OperatorPreflightError("production operator packet Git blob stream is unavailable")
    try:
        remaining = maximum_bytes + 1
        chunks: list[bytes] = []
        while remaining:
            chunk = stream.read(min(65_536, remaining))
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise OperatorPreflightError("production operator packet Git blob is not bytes")
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > maximum_bytes:
            raise OperatorPreflightError("production operator packet Git blob exceeds its byte limit")
        try:
            return_code = process.wait(timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            raise OperatorPreflightError("production operator packet Git blob did not complete") from exc
        if return_code != 0:
            raise OperatorPreflightError("production operator packet Git blob is unavailable")
        return content
    except OSError as exc:
        raise OperatorPreflightError("production operator packet Git blob cannot be streamed") from exc
    finally:
        try:
            stream.close()
        except OSError:
            pass
        if process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=10)
            except (OSError, subprocess.SubprocessError):
                pass


def _production_packet_bytes(path: str | Path) -> bytes:
    """Capture one packet and bind those exact bytes to HEAD and index blobs."""
    location, relative = _admit_production_packet_path(path)
    captured = _read_regular_file_bounded(location, maximum_bytes=MAX_SPEC_BYTES)
    root = _repository_path()
    head = _read_git_blob_bounded(
        root=root,
        object_name=f"HEAD:{relative}",
        maximum_bytes=MAX_SPEC_BYTES,
    )
    index = _read_git_blob_bounded(
        root=root,
        object_name=f":{relative}",
        maximum_bytes=MAX_SPEC_BYTES,
    )
    if captured != head or captured != index:
        raise OperatorPreflightError("production operator packet does not exactly match HEAD and index")
    return captured


def _paths_overlap(first: str | Path, second: str | Path) -> bool:
    """Whether two resolved local roots are equal or one contains the other."""
    try:
        left = Path(first).resolve(strict=False)
        right = Path(second).resolve(strict=False)
    except OSError as exc:
        raise OperatorPreflightError("operator local paths cannot be resolved") from exc
    return left == right or left in right.parents or right in left.parents


def _reject_local_artifact_overlap(*, output_dir: str | Path, local_store: str | Path | None) -> None:
    if local_store is not None and _paths_overlap(output_dir, local_store):
        raise OperatorPreflightError("receipt output directory cannot overlap the local source store")


def _no_latest(value: Any, *, field: str, depth: int = 0) -> None:
    if depth > 32:
        raise OperatorPreflightError(f"{field} exceeds nesting limit")
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise OperatorPreflightError(f"{field} has a non-text key")
            _no_latest(item, field=field, depth=depth + 1)
    elif type(value) is list:
        for item in value:
            _no_latest(item, field=field, depth=depth + 1)
    elif isinstance(value, str) and _PATH_FORBIDDEN_RE.search(value) is not None:
        raise OperatorPreflightError(f"{field} cannot name a latest pointer")


def _canonical_json_object(value: Any, *, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise OperatorPreflightError(f"{field} must be an object")
    try:
        # A JSON round trip strips no information, but ensures later domain
        # adapters receive only plain, finite JSON-shaped containers.
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError, OverflowError) as exc:
        raise OperatorPreflightError(f"{field} is not finite JSON") from exc


def _parse_submissions_source(value: Any, *, field: str, older: bool) -> PinnedSubmissionsSource:
    item = _object(
        value,
        field=field,
        required=frozenset({"source_name", "receipt_path", "object_path", "is_older"}),
    )
    if item["is_older"] is not older:
        raise OperatorPreflightError(f"{field}.is_older conflicts with its packet position")
    return PinnedSubmissionsSource(
        source_name=_text(item["source_name"], field=f"{field}.source_name"),
        receipt_path=_source_path(item["receipt_path"], field=f"{field}.receipt_path"),
        object_path=_source_path(item["object_path"], field=f"{field}.object_path"),
        is_older=older,
    )


def _parse_conversion_limits(value: Any) -> CompanyFactsLedgerConversionConfig:
    item = _object(
        value,
        field="packet.companyfacts.conversion_limits",
        required=frozenset(
            {
                "max_occurrences",
                "max_payload_bytes",
                "max_total_input_bytes",
                "max_submission_rows",
                "max_older_submissions_files",
                "max_revision_evidence",
                "max_revision_evidence_bytes",
            }
        ),
    )
    if any(type(number) is not int or isinstance(number, bool) for number in item.values()):
        raise OperatorPreflightError("packet.companyfacts.conversion_limits must contain integers")
    try:
        return CompanyFactsLedgerConversionConfig(**item)
    except (TypeError, ValueError) as exc:
        raise OperatorPreflightError("packet.companyfacts.conversion_limits are invalid") from exc


def spec_from_dict(value: Any) -> OperatorSpec:
    """Validate an exact sealed packet before the first store read."""
    root = _object(
        value,
        field="operator packet",
        required=frozenset({"schema", "base_query_snapshot_id", "source_snapshot_id", "packet"}),
    )
    if root["schema"] != OPERATOR_SCHEMA:
        raise OperatorPreflightError("operator packet schema is unsupported")
    packet = _object(
        root["packet"],
        field="packet",
        required=frozenset({"cik", "filing", "ixbrl_document_name", "companyfacts"}),
    )
    cik = _identifier(packet["cik"], field="packet.cik", pattern=_CIK_RE)
    filing = _object(
        packet["filing"],
        field="packet.filing",
        required=frozenset(
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
    archive_index_document = _canonical_json_object(
        filing["archive_index_document"], field="packet.filing.archive_index_document"
    )
    member_states_raw = filing["member_states"]
    if type(member_states_raw) is dict:
        if len(member_states_raw) > MAX_OPERATOR_MEMBER_STATES:
            raise OperatorPreflightError("packet.filing.member_states exceeds its limit")
        member_states: Mapping[str, Any] | tuple[Mapping[str, Any], ...] = _canonical_json_object(
            member_states_raw, field="packet.filing.member_states"
        )
    elif type(member_states_raw) is list:
        rows = _array(
            member_states_raw,
            field="packet.filing.member_states",
            maximum=MAX_OPERATOR_MEMBER_STATES,
        )
        copied_rows: list[Mapping[str, Any]] = []
        for index, row in enumerate(rows):
            copied_rows.append(
                _canonical_json_object(row, field=f"packet.filing.member_states[{index}]")
            )
        member_states = tuple(copied_rows)
    else:
        raise OperatorPreflightError("packet.filing.member_states must be an object or array")
    _no_latest(archive_index_document, field="packet.filing.archive_index_document")
    _no_latest(member_states, field="packet.filing.member_states")

    companyfacts = _object(
        packet["companyfacts"],
        field="packet.companyfacts",
        required=frozenset(
            {
                "manifest_path",
                "capture_path",
                "response_path",
                "submissions_recorded_at",
                "recent_submissions",
                "older_submissions",
                "conversion_limits",
            }
        ),
    )
    paths = CompanyFactsSourcePaths(
        manifest_path=_source_path(companyfacts["manifest_path"], field="packet.companyfacts.manifest_path"),
        capture_path=_source_path(companyfacts["capture_path"], field="packet.companyfacts.capture_path"),
        response_path=_source_path(companyfacts["response_path"], field="packet.companyfacts.response_path"),
    )
    older = tuple(
        _parse_submissions_source(item, field=f"packet.companyfacts.older_submissions[{index}]", older=True)
        for index, item in enumerate(
            _array(
                companyfacts["older_submissions"],
                field="packet.companyfacts.older_submissions",
                maximum=512,
            )
        )
    )
    recorded_at = _text(
        companyfacts["submissions_recorded_at"],
        field="packet.companyfacts.submissions_recorded_at",
        maximum=64,
    )
    try:
        parsed_recorded = parse_utc(recorded_at, field="packet.companyfacts.submissions_recorded_at")
    except ValueError as exc:
        raise OperatorPreflightError("packet.companyfacts.submissions_recorded_at is invalid") from exc
    if parsed_recorded is None:
        raise OperatorPreflightError("packet.companyfacts.submissions_recorded_at is required")

    return OperatorSpec(
        base_query_snapshot_id=_identifier(
            root["base_query_snapshot_id"],
            field="base_query_snapshot_id",
            pattern=_FFQS_RE,
        ),
        source_snapshot_id=_identifier(
            root["source_snapshot_id"],
            field="source_snapshot_id",
            pattern=_FFSECSRC_RE,
        ),
        packet=OperatorPacket(
            cik=cik,
            accession=_identifier(filing["accession"], field="packet.filing.accession", pattern=_ACCESSION_RE),
            manifest_id=_identifier(filing["manifest_id"], field="packet.filing.manifest_id", pattern=_MANIFEST_RE),
            archive_index_document=archive_index_document,
            member_states=member_states,
            policy_profile=_text(filing["policy_profile"], field="packet.filing.policy_profile"),
            policy_version=_text(filing["policy_version"], field="packet.filing.policy_version"),
            ixbrl_document_name=_text(packet["ixbrl_document_name"], field="packet.ixbrl_document_name"),
            companyfacts_paths=paths,
            submissions_recorded_at=utc_text(parsed_recorded) or "",
            recent_submissions=_parse_submissions_source(
                companyfacts["recent_submissions"],
                field="packet.companyfacts.recent_submissions",
                older=False,
            ),
            older_submissions=older,
            conversion_config=_parse_conversion_limits(companyfacts["conversion_limits"]),
        ),
    )


def _operator_spec_from_bytes(content: bytes) -> OperatorSpec:
    """Parse only already-captured bounded packet bytes."""
    if not isinstance(content, bytes) or len(content) > MAX_SPEC_BYTES:
        raise OperatorPreflightError("operator packet bytes are outside the bounded range")

    def reject_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise OperatorPreflightError("operator packet has duplicate JSON keys")
            result[key] = item
        return result

    def reject_constant(value: str) -> None:
        raise OperatorPreflightError(f"operator packet has non-finite JSON token {value!r}")

    def reject_float(_value: str) -> None:
        raise OperatorPreflightError("operator packet cannot use JSON floats")

    try:
        raw = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
            parse_float=reject_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperatorPreflightError("operator packet is not valid UTF-8 JSON") from exc
    return spec_from_dict(raw)


def operator_spec_from_bytes(content: bytes) -> OperatorSpec:
    """Admit canonical packet bytes through the production 2 MiB boundary."""
    return _operator_spec_from_bytes(content)


def load_operator_spec(path: str | Path) -> OperatorSpec:
    """Load an arbitrary hermetic-test packet through the fd-safe reader."""
    return _operator_spec_from_bytes(
        _read_regular_file_bounded(Path(path), maximum_bytes=MAX_SPEC_BYTES)
    )


def load_production_operator_spec(path: str | Path) -> OperatorSpec:
    """Load only the exact bytes that match both production Git authorities."""
    return _operator_spec_from_bytes(_production_packet_bytes(path))


def _operator_clock(value: str | datetime) -> str:
    try:
        parsed = parse_utc(value, field="operator_verification_observed_at")
    except ValueError as exc:
        raise OperatorPreflightError("operator_verification_observed_at is invalid") from exc
    if parsed is None:
        raise OperatorPreflightError("operator_verification_observed_at is required")
    return utc_text(parsed) or ""


def build_readonly_operator_store(*, local_dir: str | Path | None = None) -> StrictBoundedReadStore:
    """Build the operator reader without the Research Vault credential fallback.

    The historic private-store constructor intentionally permits a shared R2
    fallback for older ingestion jobs. This operator must never make that
    choice: production requires all four dedicated ``FF_ATTESTED_R2_READONLY``
    variables. ``local_dir`` remains the hermetic test adapter.
    """
    if local_dir is not None:
        store = build_private_source_store(local_dir=local_dir)
        if not isinstance(store, StrictBoundedReadStore):
            raise OperatorPreflightError("local operator store lacks strict bounded reads")
        return store
    names = (
        "FF_ATTESTED_R2_READONLY_ENDPOINT",
        "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID",
        "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY",
        "FF_ATTESTED_R2_READONLY_BUCKET",
    )
    values = {name: os.environ.get(name, "") for name in names}
    if any(not value for value in values.values()):
        raise OperatorPreflightError("dedicated read-only R2 credential is unavailable")
    try:
        temporary = mint_r2_temporary_credentials(
            endpoint=values["FF_ATTESTED_R2_READONLY_ENDPOINT"],
            parent_access_key_id=values["FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID"],
            parent_secret_access_key=values[
                "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY"
            ],
            bucket=values["FF_ATTESTED_R2_READONLY_BUCKET"],
            scope="object-read-only",
            actions=("GetObject", "HeadObject"),
        )
    except R2TemporaryCredentialError as exc:
        raise OperatorPreflightError(
            "dedicated read-only R2 parent rejected: "
            + value_free_credential_error(exc)
        ) from exc
    finally:
        # The workflow already scopes parent secrets to this process step. Drop
        # the in-process copies immediately after local signing as defense in
        # depth; the boto client receives only the short-lived child values.
        os.environ.pop("FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID", None)
        os.environ.pop("FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY", None)
        values["FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID"] = ""
        values["FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY"] = ""
    try:
        import boto3
        from botocore.config import Config

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
        # Older botocore versions lack the checksum keyword arguments but still
        # support the same GET/HEAD-only read surface.
        config = Config(
            region_name="auto",
            signature_version="s3v4",
            max_pool_connections=8,
            retries={"max_attempts": 3, "mode": "adaptive"},
            connect_timeout=15,
            read_timeout=60,
        )
    except ImportError as exc:
        raise OperatorPreflightError("boto3 is unavailable for the read-only operator") from exc
    client = boto3.client(
        "s3",
        endpoint_url=values["FF_ATTESTED_R2_READONLY_ENDPOINT"],
        aws_access_key_id=temporary.access_key_id,
        aws_secret_access_key=temporary.secret_access_key,
        aws_session_token=temporary.session_token,
        config=config,
    )
    store = R2Store(values["FF_ATTESTED_R2_READONLY_BUCKET"], client=client)
    if not isinstance(store, StrictBoundedReadStore):  # defensive runtime contract guard
        raise OperatorPreflightError("read-only operator store lacks strict bounded reads")
    return store


def _selected_member_bytes(
    *, package: FilingPackage, authority: PinnedSourceAuthority, document_name: str
) -> bytes:
    inventory = package.to_dict().get("inventory")
    if type(inventory) is not list:
        raise OperatorPreflightError("materialized filing package inventory is invalid")
    selected = next(
        (
            item
            for item in inventory
            if type(item) is dict and item.get("document_name") == document_name
        ),
        None,
    )
    if type(selected) is not dict or selected.get("state") != "stored":
        raise OperatorPreflightError("named iXBRL member is absent or not stored")
    try:
        byte_length = selected["byte_length"]
        retrieval = selected["retrieval"]
        storage_key = selected["storage_key"]
        if type(byte_length) is not int or isinstance(byte_length, bool) or type(retrieval) is not dict:
            raise TypeError("invalid selected member fields")
        read = authority.read_archive_document(
            storage_key=storage_key,
            expected_receipt=retrieval,
            maximum_bytes=byte_length,
            maximum_stored_bytes=gzip_stored_byte_ceiling(byte_length),
        )
    except Exception as exc:  # exact component details can expose private paths
        raise OperatorPreflightError("named iXBRL member cannot be re-read from the pinned source") from exc
    return read.content


def materialize_operator_inputs(
    *, spec: OperatorSpec, store: StrictBoundedReadStore, observed_at: str
) -> MaterializedOperatorInputs:
    """Build the B4D/B2/B3 graph only from named immutable source members."""
    read_only = store if type(store) is ReadOnlyStrictStore else ReadOnlyStrictStore(store)
    # B4's bounded v1 reader is deliberately reused rather than the legacy
    # QuerySnapshot reader, whose strict-store contract predates pre-read caps.
    base = _verified_base_snapshot(read_only, spec.base_query_snapshot_id)
    authority = PinnedSourceAuthority(store=read_only, snapshot_id=spec.source_snapshot_id)
    packet = spec.packet
    package = materialize_filing_package_from_pinned_source(
        PinnedFilingPackageDescriptor(
            cik=packet.cik,
            accession=packet.accession,
            manifest_id=packet.manifest_id,
            archive_index_document=packet.archive_index_document,
            member_states=packet.member_states,
        ),
        authority=authority,
        assembled_at=observed_at,
        policy_profile=packet.policy_profile,
        policy_version=packet.policy_version,
    )
    extraction = build_ixbrl_extraction(
        package,
        packet.ixbrl_document_name,
        _selected_member_bytes(
            package=package,
            authority=authority,
            document_name=packet.ixbrl_document_name,
        ),
        computed_at=observed_at,
    )
    attestation = build_filing_attestation(
        package,
        extraction,
        authority=authority,
        companyfacts_paths=packet.companyfacts_paths,
        attested_at=observed_at,
    )
    conversion = load_companyfacts_ledger_from_pinned_source(
        authority=authority,
        source_bundle=CompanyFactsConversionSourceBundle(
            cik=packet.cik,
            companyfacts_manifest_path=packet.companyfacts_paths.manifest_path,
            companyfacts_capture_path=packet.companyfacts_paths.capture_path,
            companyfacts_response_path=packet.companyfacts_paths.response_path,
            recent_submissions=packet.recent_submissions,
            older_submissions=packet.older_submissions,
        ),
        submissions_recorded_at=packet.submissions_recorded_at,
        config=packet.conversion_config,
    )
    material = AttestationMaterial(
        attestation=attestation,
        package=package,
        extraction=extraction,
        authority=authority,
        companyfacts_paths=packet.companyfacts_paths,
    )
    return MaterializedOperatorInputs(
        base_snapshot=base,
        package=package,
        extraction=extraction,
        attestation=attestation,
        material=material,
        conversion=conversion,
    )


def _coverage_projection(report: AttestedBindingReport) -> list[dict[str, Any]]:
    if len(report.coverage) > MAX_RECEIPT_COVERAGE_ROWS:
        raise OperatorPreflightError("preflight coverage exceeds its receipt projection limit")
    return [
        {
            "root_cell_id": item.root_cell_id,
            "status": item.status,
            "selected_leaf_count": len(item.selected_leaf_occurrence_ids),
            "eligible_leaf_count": len(item.eligible_leaf_occurrence_ids),
            "candidate_leaf_count": len(item.candidate_leaf_occurrence_ids),
            "auto_bound_leaf_count": len(item.auto_bound_occurrence_ids),
        }
        for item in report.coverage
    ]


def _rejection_reason_counts(report: AttestedBindingReport) -> dict[str, int]:
    """Return a compact diagnostic without retaining rejected source leaves."""
    counts: dict[str, int] = {}
    for leaf in report.leaves:
        for reason in leaf.rejection_reasons:
            if reason not in _REJECTION_REASON_CODES:
                raise OperatorPreflightError("preflight rejection reason is invalid")
            counts[reason] = counts.get(reason, 0) + 1
            if len(counts) > MAX_RECEIPT_REJECTION_REASONS:
                raise OperatorPreflightError("preflight rejection reasons exceed receipt projection limit")
            if counts[reason] > MAX_RECEIPT_REJECTION_REASON_COUNT:
                raise OperatorPreflightError("preflight rejection reason count exceeds receipt projection limit")
    return {reason: counts[reason] for reason in sorted(counts)}


def _receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    try:
        encoded = json.dumps(
            receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise OperatorPreflightError("preflight receipt is not finite JSON") from exc
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise OperatorPreflightError("preflight receipt exceeds its byte budget")
    return encoded


def _base_receipt(*, observed_at: str, status: str, write_attempts: int) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "status": status,
        "operator_verification_observed_at": observed_at,
        "publication": {
            "publication_performed": False,
            "pointer_advanced": False,
            "immutable_objects_written": False,
            "storage_write_attempts": write_attempts,
        },
        "redaction": {
            "raw_source_payloads_included": False,
            "storage_paths_included": False,
            "storage_endpoints_included": False,
            "storage_credentials_included": False,
            "error_messages_included": False,
        },
        "nonclaims": [
            "not_published",
            "not_a_freshness_claim",
            "not_a_filing_completeness_claim",
            "not_investment_or_trading_authority",
        ],
    }


def run_readonly_preflight(
    *,
    spec: OperatorSpec,
    store: StrictBoundedReadStore,
    operator_verification_observed_at: str | datetime,
    phase_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Prepare one private candidate in memory and return a bounded receipt.

    ``prepared`` means B4A preparation/replay completed in memory.  It never
    means that immutable objects were stored or that a latest pointer moved.
    """
    observed_at = _operator_clock(operator_verification_observed_at)
    read_only = ReadOnlyStrictStore(store)
    if phase_callback is not None:
        phase_callback("materialization")
    inputs = materialize_operator_inputs(spec=spec, store=read_only, observed_at=observed_at)
    if phase_callback is not None:
        phase_callback("binding_plan")
    report = enumerate_attested_binding_candidates(
        query_snapshot=inputs.base_snapshot,
        companyfacts_conversion=inputs.conversion,
        attestation_materials=(inputs.material,),
    )
    candidate: PreparedAttestedQuerySnapshot | None = None
    if report.bindings:
        if phase_callback is not None:
            phase_callback("candidate_prepare")
        candidate = prepare_attested_query_snapshot(
            store=read_only,
            query_snapshot_id=spec.base_query_snapshot_id,
            attestation_materials=(inputs.material,),
            companyfacts_conversion=inputs.conversion,
            occurrence_bindings=report.bindings,
            operator_verification_observed_at=observed_at,
            # This remains a candidate manifest field only.  A future
            # publisher must prepare again with its real publication clock.
            published_at=observed_at,
        )
    status = "prepared" if candidate is not None else "non_publishable"
    receipt = _base_receipt(
        observed_at=observed_at,
        status=status,
        write_attempts=read_only.write_attempts,
    )
    receipt.update(
        {
            "inputs": {
                "base_query_snapshot_id": spec.base_query_snapshot_id,
                "source_snapshot_id": spec.source_snapshot_id,
                "cik": spec.packet.cik,
                "accession": spec.packet.accession,
                "filing_manifest_id": spec.packet.manifest_id,
            },
            "materialization": {
                "filing_package_id": inputs.package.package_id,
                "ixbrl_extraction_id": inputs.extraction.extraction_id,
                "filing_attestation_id": inputs.attestation.attestation_id,
                "companyfacts_conversion_receipt_id": inputs.conversion.receipt.receipt_id,
            },
            "binding_plan": {
                "binding_count": len(report.bindings),
                "candidate_leaf_count": sum(1 for leaf in report.leaves if leaf.candidates),
                "rejected_leaf_count": sum(1 for leaf in report.leaves if leaf.rejection_reasons),
                "rejection_reason_counts": _rejection_reason_counts(report),
                "coverage": _coverage_projection(report),
            },
            "candidate": {
                "prepared_in_memory": candidate is not None,
                "candidate_snapshot_id": candidate.snapshot_id if candidate is not None else None,
                "candidate_published_at_is_not_an_actual_publication": candidate is not None,
            },
        }
    )
    if read_only.write_attempts != 0:
        raise ReadOnlyWriteAttempt(
            "read-only preflight observed a storage write attempt",
            write_attempts=read_only.write_attempts,
        )
    _receipt_bytes(receipt)
    return receipt


def failed_receipt(
    *, observed_at: str, phase: str, error: BaseException, write_attempts: int = 0
) -> dict[str, Any]:
    """Emit a diagnostic code without leaking error messages or source paths."""
    if phase not in _FAILURE_PHASES:
        raise OperatorPreflightError("preflight failure phase is invalid")
    receipt = _base_receipt(observed_at=observed_at, status="failed", write_attempts=write_attempts)
    receipt["failure"] = {"phase": phase, "error_type": type(error).__name__}
    _receipt_bytes(receipt)
    return receipt


def write_private_receipt(output_dir: str | Path, receipt: Mapping[str, Any]) -> Path:
    """Atomically write the sole local artifact for Actions artifact upload."""
    destination = Path(output_dir)
    if destination.exists() and destination.is_symlink():
        raise OperatorPreflightError("receipt output directory cannot be a symlink")
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise OperatorPreflightError("receipt output directory is invalid")
    payload = _receipt_bytes(receipt)
    final = destination / "attested_history_preflight_receipt.json"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".attested_history_preflight_", suffix=".tmp", dir=destination
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, final)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return final


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="sealed JSON operator packet")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="local review-only, noncanonical artifact directory",
    )
    parser.add_argument(
        "--operator-verification-observed-at",
        required=True,
        help="explicit UTC observation clock; never sampled by this CLI",
    )
    parser.add_argument(
        "--local-store",
        help="explicit LocalStore root for hermetic tests only; production must use a read-only R2 role",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        observed_at = _operator_clock(args.operator_verification_observed_at)
    except OperatorPreflightError:
        # An invalid clock cannot safely be replaced with wall time.
        return 2
    try:
        _reject_local_artifact_overlap(output_dir=args.output_dir, local_store=args.local_store)
    except OperatorPreflightError:
        # Never write the diagnostic artifact into the source store that the
        # command just proved overlaps its output target.
        return 2
    phase = "packet_admission"
    try:
        if args.local_store is None:
            captured = _production_packet_bytes(args.config)
            phase = "packet_read"
            spec = _operator_spec_from_bytes(captured)
        else:
            phase = "packet_read"
            spec = load_operator_spec(args.config)
        phase = "store_initialization"
        store = build_readonly_operator_store(local_dir=args.local_store)

        def record_preflight_phase(value: str) -> None:
            nonlocal phase
            if value not in _FAILURE_PHASES:
                raise OperatorPreflightError("preflight phase is invalid")
            phase = value

        receipt = run_readonly_preflight(
            spec=spec,
            store=store,
            operator_verification_observed_at=observed_at,
            phase_callback=record_preflight_phase,
        )
        phase = "receipt_write"
        write_private_receipt(args.output_dir, receipt)
    except Exception as exc:  # receipt contents intentionally retain only a type code.
        try:
            write_private_receipt(
                args.output_dir,
                failed_receipt(
                    observed_at=observed_at,
                    phase=phase,
                    error=exc,
                    write_attempts=getattr(exc, "write_attempts", 0),
                ),
            )
        except Exception:
            pass
        print(
            f"::error title=fundamental_forensics_attested_history::{phase} failed",
            flush=True,
        )
        return 1
    del receipt
    print(
        "::notice title=fundamental_forensics_attested_history::read-only preflight completed; retrieve the review-only receipt artifact",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
