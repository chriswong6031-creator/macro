"""Immutable SEC filing-archive cache for Fundamental Forensics.

This module deliberately does not discover an unbounded filing universe and is
never imported by a render builder.  Callers supply a filing manifest item,
which yields one exact SEC archive URL, then retain the returned byte stream by
content hash.  The offline engine can later select a point-in-time filing and
read the verified bytes without a network dependency.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import requests

from engine.fundamental_forensics.sec_document_spine import (
    ARCHIVE_RECEIPT_SCHEMA,
    FilingManifestError,
    HARD_MAX_ARCHIVE_DOCUMENT_BYTES,
    HARD_MAX_FILING_MANIFEST_BYTES,
    HARD_MAX_HTTP_METADATA_BYTES,
    manifest_from_json_bytes,
    manifest_json_bytes,
    parse_json_int64,
    validate_manifest,
    with_document_retrievals,
)
from engine.fundamental_forensics.models import canonical_json, parse_utc, stable_id, utc_text


_STREAM_CHUNK_BYTES = 64 * 1024
# Keep the archive transport bound compatible with the bounded acquisition
# contract.  A collector constructed directly must not silently become an
# unbounded archive mirror.
HARD_MAX_DOCUMENT_BYTES = HARD_MAX_ARCHIVE_DOCUMENT_BYTES
DEFAULT_MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
HARD_MAX_ARCHIVE_RECEIPT_BYTES = 64 * 1024
_MANIFEST_STORAGE_KEY_RE = re.compile(
    r"^manifests/[0-9]{10}/[0-9]{10}-[0-9]{2}-[0-9]{6}/"
    r"ffsec_manifest_[a-f0-9]{64}\.json$"
)


def _byte_limit(value: int | None, *, field: str) -> int:
    if value is None:
        return DEFAULT_MAX_DOCUMENT_BYTES
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > HARD_MAX_DOCUMENT_BYTES
    ):
        raise ValueError(
            f"{field} must be a positive integer no larger than {HARD_MAX_DOCUMENT_BYTES}"
        )
    return value


def _reject_declared_oversize(headers: Any, limit: int, *, url: str) -> None:
    """Fail before persistence when SEC declares a response over the caller cap."""
    if not isinstance(headers, Mapping):
        return
    raw = headers.get("Content-Length") or headers.get("content-length")
    if raw is None:
        return
    try:
        declared = int(str(raw).strip())
    except (TypeError, ValueError):
        return
    if declared < 0:
        raise ArchiveResponseTooLarge(f"SEC archive response has invalid Content-Length for {url}")
    if declared > limit:
        raise ArchiveResponseTooLarge(
            f"SEC archive response exceeds bounded ingest limit ({declared} > {limit}) for {url}"
        )


def _response_header(headers: Any, name: str) -> str | None:
    """Read a transport header without assuming a particular response wrapper."""
    if not isinstance(headers, Mapping):
        return None
    value = headers.get(name)
    if value is None:
        value = headers.get(name.lower())
    if value is None:
        return None
    return _http_metadata(value, field=name)


def _http_metadata(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or any(char in value for char in ("\x00", "\r", "\n")):
        raise ArchiveStoreError(f"SEC archive {field} metadata is invalid")
    try:
        if len(value.encode("utf-8")) > HARD_MAX_HTTP_METADATA_BYTES:
            raise ArchiveStoreError(f"SEC archive {field} metadata exceeds byte safety limit")
    except UnicodeError as exc:
        raise ArchiveStoreError(f"SEC archive {field} metadata is not valid UTF-8") from exc
    return value


def _stream_response_bytes(response: Any, limit: int, *, url: str) -> bytes:
    """Read an archive body without retaining more than the caller's cap plus one.

    ``requests`` honours ``chunk_size`` for normal HTTP responses; retaining only
    the remaining permitted prefix additionally protects the cache boundary when
    a response adapter or test double returns a larger chunk.  The extra byte is
    sufficient to prove an over-limit response and is never persisted.
    """
    chunk_size = min(_STREAM_CHUNK_BYTES, limit + 1)
    chunks: list[bytes] = []
    retained = 0
    try:
        iterator = response.iter_content(chunk_size=chunk_size)
        for chunk in iterator:
            if not isinstance(chunk, bytes):
                raise ArchiveStoreError("SEC archive response stream yielded non-bytes")
            if not chunk:
                continue
            remaining = limit + 1 - retained
            if remaining <= 0:
                raise ArchiveResponseTooLarge(
                    f"SEC archive response exceeds bounded ingest limit ({limit + 1} > {limit}) for {url}"
                )
            retained_chunk = chunk[:remaining]
            chunks.append(retained_chunk)
            retained += len(retained_chunk)
            if retained > limit:
                raise ArchiveResponseTooLarge(
                    f"SEC archive response exceeds bounded ingest limit ({retained} > {limit}) for {url}"
                )
    except ArchiveStoreError:
        raise
    except Exception as exc:
        raise ArchiveStoreError("SEC archive response stream failed") from exc
    return b"".join(chunks)


def _close_response(response: Any) -> ArchiveStoreError | None:
    """Release an HTTP response before any source bytes can be persisted."""
    close = getattr(response, "close", None)
    if not callable(close):
        return ArchiveStoreError("SEC archive response has no close method")
    try:
        close()
    except Exception:
        return ArchiveStoreError("SEC archive response close failed")
    return None


class ArchiveStoreError(OSError):
    """An immutable archive object or its receipt failed integrity checks."""


class ChecksumMismatch(ArchiveStoreError):
    """The bytes returned by a source do not match a caller-supplied checksum."""


class ArchiveResponseTooLarge(ArchiveStoreError):
    """An archive response exceeded the caller's explicit bounded-ingest budget."""


@dataclass(frozen=True)
class ArchiveReceipt:
    """A checksum-bound receipt for one exact archive-document retrieval."""

    schema: str
    receipt_id: str
    status: str
    document_id: str
    archive_url: str
    retrieved_at: str
    content_sha256: str
    byte_length: int
    storage_key: str
    http_etag: str | None
    http_last_modified: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_text(value: str | datetime, *, field: str) -> str:
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise ArchiveStoreError(str(exc)) from exc
    if parsed is None:  # pragma: no cover - required argument contract
        raise ArchiveStoreError(f"{field} is required")
    return utc_text(parsed) or ""  # pragma: no cover - parsed is non-null


def content_storage_key(content_sha256: str) -> str:
    if not isinstance(content_sha256, str) or len(content_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in content_sha256
    ):
        raise ArchiveStoreError("content_sha256 must be lowercase SHA-256 hex")
    return f"objects/sha256/{content_sha256[:2]}/{content_sha256}.bin.gz"


def receipt_storage_key(receipt_id: str) -> str:
    if not receipt_id.startswith("sec_archive_receipt_"):
        raise ArchiveStoreError("invalid archive receipt id")
    digest = receipt_id.removeprefix("sec_archive_receipt_")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ArchiveStoreError("invalid archive receipt id")
    return f"receipts/sha256/{digest[:2]}/{digest}.json"


def manifest_storage_key(manifest: Mapping[str, Any]) -> str:
    validate_manifest(manifest)
    cik = str(manifest["issuer"]["cik"])
    accession = str(manifest["filing"]["accession"])
    manifest_id = str(manifest["manifest_id"])
    return f"manifests/{cik}/{accession}/{manifest_id}.json"


def _temp_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")


def _sync_parent(path: Path) -> None:
    try:
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        # Directory fsync is unavailable on a few mounted object-store filesystems.
        pass


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temp_sibling(path)
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_parent(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_bounded_file(path: Path, *, maximum: int, label: str) -> bytes:
    """Read one metadata artifact with a finite cap before JSON decoding."""
    with path.open("rb") as handle:
        content = handle.read(maximum + 1)
    if len(content) > maximum:
        raise ArchiveStoreError(f"{label} exceeds byte safety limit: {path}")
    return content


def _gzip_bytes(content: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(content)
    return buffer.getvalue()


def _read_object(path: Path, expected_sha256: str, expected_length: int) -> bytes:
    if (
        isinstance(expected_length, bool)
        or not isinstance(expected_length, int)
        or expected_length < 0
        or expected_length > HARD_MAX_DOCUMENT_BYTES
    ):
        raise ArchiveStoreError(
            "SEC archive receipt byte_length must be a non-negative integer "
            f"no larger than {HARD_MAX_DOCUMENT_BYTES}"
        )
    try:
        with gzip.open(path, "rb") as handle:
            # Never use an unbounded gzip read: a receipt's byte_length is the
            # trusted decompression budget, and one extra byte detects a bomb.
            content = handle.read(expected_length + 1)
    except (OSError, EOFError, OverflowError, ValueError) as exc:
        raise ArchiveStoreError(f"corrupt compressed SEC archive object: {path}") from exc
    if len(content) > expected_length:
        raise ArchiveStoreError(f"SEC archive byte length exceeds trusted receipt: {path}")
    digest = hashlib.sha256(content).hexdigest()
    if digest != expected_sha256:
        raise ArchiveStoreError(f"SEC archive checksum mismatch: {path}")
    if len(content) != expected_length:
        raise ArchiveStoreError(f"SEC archive byte length mismatch: {path}")
    return content


def _object_matches(path: Path, content: bytes) -> bool:
    try:
        return _read_object(path, hashlib.sha256(content).hexdigest(), len(content)) == content
    except ArchiveStoreError:
        return False


def _receipt_id(body: Mapping[str, Any]) -> str:
    return stable_id("sec_archive_receipt", body)


def _receipt_bytes(receipt: ArchiveReceipt) -> bytes:
    content = canonical_json(receipt.to_dict()).encode("utf-8")
    if len(content) > HARD_MAX_ARCHIVE_RECEIPT_BYTES:
        raise ArchiveStoreError("archive receipt exceeds byte safety limit")
    return content


def _decode_receipt(content: bytes) -> ArchiveReceipt:
    if not isinstance(content, bytes) or len(content) > HARD_MAX_ARCHIVE_RECEIPT_BYTES:
        raise ArchiveStoreError("archive receipt exceeds byte safety limit")
    try:
        value = json.loads(content.decode("utf-8"), parse_int=parse_json_int64)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ArchiveStoreError("archive receipt is not UTF-8 JSON") from exc
    fields = set(ArchiveReceipt.__dataclass_fields__)
    if not isinstance(value, dict) or set(value) != fields:
        raise ArchiveStoreError("archive receipt shape is invalid")
    try:
        receipt = ArchiveReceipt(**value)
    except TypeError as exc:
        raise ArchiveStoreError("archive receipt shape is invalid") from exc
    body = receipt.to_dict()
    actual = body.pop("receipt_id")
    expected = _receipt_id(body)
    if actual != expected:
        raise ArchiveStoreError("archive receipt identity mismatch")
    if receipt.schema != ARCHIVE_RECEIPT_SCHEMA or receipt.status != "retrieved":
        raise ArchiveStoreError("unsupported archive receipt")
    if (
        isinstance(receipt.byte_length, bool)
        or not isinstance(receipt.byte_length, int)
        or receipt.byte_length < 0
        or receipt.byte_length > HARD_MAX_DOCUMENT_BYTES
    ):
        raise ArchiveStoreError(
            "archive receipt byte_length must be a non-negative integer "
            f"no larger than {HARD_MAX_DOCUMENT_BYTES}"
        )
    if content_storage_key(receipt.content_sha256) != receipt.storage_key:
        raise ArchiveStoreError("archive receipt storage key does not bind checksum")
    if _utc_text(receipt.retrieved_at, field="retrieved_at") != receipt.retrieved_at:
        raise ArchiveStoreError("archive receipt retrieved_at is not UTC-normalized")
    _http_metadata(receipt.http_etag, field="ETag")
    _http_metadata(receipt.http_last_modified, field="Last-Modified")
    if _receipt_bytes(receipt) != content:
        raise ArchiveStoreError("archive receipt is not canonically encoded")
    return receipt


def persist_archive_document(
    cache_root: Path,
    document: Mapping[str, Any],
    content: bytes,
    *,
    retrieved_at: str | datetime,
    expected_sha256: str | None = None,
    http_etag: str | None = None,
    http_last_modified: str | None = None,
) -> ArchiveReceipt:
    """Atomically retain a document and immutable checksum/transport receipt.

    Existing hash-named objects are decompressed and re-verified before reuse.
    A truncated or checksum-mismatched object is replaced atomically, while a
    caller-supplied expected checksum fails before any bytes are written.
    """
    if not isinstance(content, bytes):
        raise ArchiveStoreError("SEC archive content must be bytes")
    if len(content) > HARD_MAX_DOCUMENT_BYTES:
        raise ArchiveResponseTooLarge(
            "SEC archive content exceeds bounded ingest limit "
            f"({len(content)} > {HARD_MAX_DOCUMENT_BYTES})"
        )
    document_id = document.get("document_id")
    archive_url = document.get("archive_url")
    if not isinstance(document_id, str) or not document_id:
        raise ArchiveStoreError("document metadata is missing document_id")
    if not isinstance(archive_url, str) or not archive_url.startswith(
        "https://www.sec.gov/Archives/"
    ):
        raise ArchiveStoreError("document metadata has a non-SEC archive URL")
    digest = hashlib.sha256(content).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ChecksumMismatch(f"expected {expected_sha256}, received {digest}")
    stored_at = _utc_text(retrieved_at, field="retrieved_at")
    http_etag = _http_metadata(http_etag, field="ETag")
    http_last_modified = _http_metadata(http_last_modified, field="Last-Modified")
    storage_key = content_storage_key(digest)
    body = {
        "schema": ARCHIVE_RECEIPT_SCHEMA,
        "status": "retrieved",
        "document_id": document_id,
        "archive_url": archive_url,
        "retrieved_at": stored_at,
        "content_sha256": digest,
        "byte_length": len(content),
        "storage_key": storage_key,
        "http_etag": http_etag,
        "http_last_modified": http_last_modified,
    }
    receipt = ArchiveReceipt(receipt_id=_receipt_id(body), **body)
    # Complete and cap all receipt metadata before the first durable write.
    encoded = _receipt_bytes(receipt)
    object_path = Path(cache_root) / storage_key
    if not _object_matches(object_path, content):
        _atomic_write(object_path, _gzip_bytes(content))
        _read_object(object_path, digest, len(content))
    receipt_path = Path(cache_root) / receipt_storage_key(receipt.receipt_id)
    try:
        same = _decode_receipt(
            _read_bounded_file(
                receipt_path,
                maximum=HARD_MAX_ARCHIVE_RECEIPT_BYTES,
                label="SEC archive receipt",
            )
        ) == receipt
    except (OSError, ArchiveStoreError):
        same = False
    if not same:
        _atomic_write(receipt_path, encoded)
        if _decode_receipt(
            _read_bounded_file(
                receipt_path,
                maximum=HARD_MAX_ARCHIVE_RECEIPT_BYTES,
                label="SEC archive receipt",
            )
        ) != receipt:  # pragma: no cover
            raise ArchiveStoreError(f"failed to verify SEC archive receipt: {receipt_path}")
    return receipt


def read_archive_document(cache_root: Path, receipt: ArchiveReceipt | Mapping[str, Any]) -> bytes:
    """Read verified cached bytes; corrupted/missing objects fail closed."""
    if not isinstance(receipt, ArchiveReceipt):
        try:
            receipt = ArchiveReceipt(**dict(receipt))
        except (TypeError, ValueError) as exc:
            raise ArchiveStoreError("invalid archive receipt mapping") from exc
    encoded = _receipt_bytes(receipt)
    decoded = _decode_receipt(encoded)
    receipt_path = Path(cache_root) / receipt_storage_key(decoded.receipt_id)
    try:
        persisted = _decode_receipt(
            _read_bounded_file(
                receipt_path,
                maximum=HARD_MAX_ARCHIVE_RECEIPT_BYTES,
                label="SEC archive receipt",
            )
        )
    except ArchiveStoreError:
        raise
    except OSError as exc:
        raise ArchiveStoreError(f"missing archive receipt: {receipt_path}") from exc
    if persisted != decoded:
        raise ArchiveStoreError("archive receipt differs from immutable stored receipt")
    return _read_object(
        Path(cache_root) / decoded.storage_key,
        decoded.content_sha256,
        decoded.byte_length,
    )


def read_primary_document(cache_root: Path, manifest: Mapping[str, Any]) -> bytes:
    """Read a selected manifest's retained primary bytes without any network call."""
    validate_manifest(manifest)
    primary = next(
        (item for item in manifest["documents"] if item.get("role") == "primary"),
        None,
    )
    if primary is None:
        raise ArchiveStoreError("filing manifest has no primary document")
    if primary.get("availability") != "stored" or not isinstance(primary.get("retrieval"), Mapping):
        raise ArchiveStoreError("primary document is not retained in the archive cache")
    return read_archive_document(cache_root, primary["retrieval"])


def persist_filing_manifest(cache_root: Path, manifest: Mapping[str, Any]) -> str:
    """Retain one immutable canonical manifest version and return its storage key."""
    content = manifest_json_bytes(manifest)
    key = manifest_storage_key(manifest)
    target = Path(cache_root) / key
    try:
        existing = _read_bounded_file(
            target,
            maximum=HARD_MAX_FILING_MANIFEST_BYTES,
            label="SEC filing manifest",
        )
        same = manifest_from_json_bytes(existing) == manifest
    except (OSError, FilingManifestError):
        same = False
    if not same:
        _atomic_write(target, content)
    # A second parse protects against an interrupted/corrupt replacement.
    if manifest_from_json_bytes(
        _read_bounded_file(
            target,
            maximum=HARD_MAX_FILING_MANIFEST_BYTES,
            label="SEC filing manifest",
        )
    ) != manifest:
        raise ArchiveStoreError(f"failed to verify filing manifest: {target}")
    return key


def read_filing_manifest(cache_root: Path, storage_key: str) -> dict[str, Any]:
    if not isinstance(storage_key, str) or not _MANIFEST_STORAGE_KEY_RE.fullmatch(storage_key):
        raise ArchiveStoreError("invalid filing manifest storage key")
    try:
        content = _read_bounded_file(
            Path(cache_root) / storage_key,
            maximum=HARD_MAX_FILING_MANIFEST_BYTES,
            label="SEC filing manifest",
        )
    except OSError as exc:
        if isinstance(exc, ArchiveStoreError):
            raise
        raise ArchiveStoreError(f"missing filing manifest: {storage_key}") from exc
    try:
        manifest = manifest_from_json_bytes(content)
    except FilingManifestError as exc:
        raise ArchiveStoreError(f"invalid filing manifest: {storage_key}") from exc
    if manifest_storage_key(manifest) != storage_key:
        raise ArchiveStoreError("filing manifest storage key does not bind its identity")
    return manifest


def missing_document_receipt(
    document: Mapping[str, Any],
    *,
    retrieved_at: str | datetime,
    http_status: int = 404,
) -> dict[str, Any]:
    """Return an explicit non-byte receipt; a 404 never masquerades as no filing."""
    document_id = document.get("document_id")
    archive_url = document.get("archive_url")
    if not isinstance(document_id, str) or not isinstance(archive_url, str):
        raise ArchiveStoreError("document metadata is incomplete")
    return {
        "schema": ARCHIVE_RECEIPT_SCHEMA,
        "status": "missing",
        "document_id": document_id,
        "archive_url": archive_url,
        "retrieved_at": _utc_text(retrieved_at, field="retrieved_at"),
        "http_status": int(http_status),
        "reason": "sec_archive_document_missing",
    }


class SecFilingArchiveCollector:
    """Paced bounded-retry archive client; it has no discovery or render entrypoint."""

    def __init__(
        self,
        cache_root: Path,
        *,
        user_agent: str,
        min_interval_seconds: float = 0.12,
        timeout_seconds: float = 30.0,
        max_attempts: int = 4,
        max_document_bytes: int | None = None,
        session: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if "@" not in user_agent:
            raise ValueError("SEC user agent must identify an application and contact email")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.cache_root = Path(cache_root)
        self.user_agent = user_agent
        self.min_interval_seconds = max(0.1, float(min_interval_seconds))
        self.timeout_seconds = float(timeout_seconds)
        self.max_attempts = int(max_attempts)
        self.max_document_bytes = _byte_limit(max_document_bytes, field="max_document_bytes")
        self.session = session or requests.Session()
        self._sleep = sleeper
        self._monotonic = monotonic
        self._last_request_at = 0.0

    def _pace(self) -> None:
        wait = self.min_interval_seconds - (self._monotonic() - self._last_request_at)
        if wait > 0:
            self._sleep(wait)

    def fetch_document(
        self,
        document: Mapping[str, Any],
        *,
        retrieved_at: str | datetime | None = None,
        expected_sha256: str | None = None,
        max_document_bytes: int | None = None,
    ) -> ArchiveReceipt | dict[str, Any]:
        """Fetch/persist exactly ``document.archive_url`` with retryable SEC pacing."""
        url = document.get("archive_url")
        if not isinstance(url, str) or not url.startswith("https://www.sec.gov/Archives/"):
            raise ArchiveStoreError("document must carry an exact SEC archive URL")
        stamp = _utc_text(retrieved_at or _utc_now(), field="retrieved_at")
        limit = self.max_document_bytes
        if max_document_bytes is not None:
            limit = _byte_limit(max_document_bytes, field="max_document_bytes")
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            self._pace()
            response = None
            try:
                try:
                    response = self.session.get(
                        url,
                        headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"},
                        timeout=self.timeout_seconds,
                        stream=True,
                        allow_redirects=False,
                    )
                except TypeError as exc:
                    # Never fall back to a legacy adapter that materializes
                    # ``response.content`` before this collector can enforce a cap.
                    raise ArchiveStoreError(
                        "SEC archive session must support streamed responses"
                    ) from exc
                try:
                    # From the instant a response exists, every subsequent
                    # operation is inside the close guard—including injected
                    # clocks used by deterministic tests and operators.
                    self._last_request_at = self._monotonic()
                    status = int(response.status_code)
                    final_url = getattr(response, "url", None)
                    if not isinstance(final_url, str) or final_url != url:
                        raise ArchiveStoreError(
                            "SEC archive response URL does not match the requested source"
                        )
                    if 300 <= status < 400:
                        raise ArchiveStoreError("SEC archive redirects are refused")
                    if status == 404:
                        missing = missing_document_receipt(
                            document, retrieved_at=stamp, http_status=status
                        )
                        content = None
                    else:
                        if status in {429, 500, 502, 503, 504}:
                            raise requests.HTTPError(f"SEC transient HTTP {status}")
                        response.raise_for_status()
                        _reject_declared_oversize(response.headers, limit, url=url)
                        content = _stream_response_bytes(response, limit, url=url)
                        missing = None
                    etag = _response_header(response.headers, "ETag")
                    last_modified = _response_header(response.headers, "Last-Modified")
                except BaseException:
                    # Preserve the causal transport/size error; a secondary
                    # close failure cannot turn an oversize response into a
                    # misleading close error, and no bytes reach persistence.
                    _close_response(response)
                    raise
                close_error = _close_response(response)
                if close_error is not None:
                    raise close_error
                if missing is not None:
                    return missing
                if content is None:  # pragma: no cover - status branches are exhaustive
                    raise ArchiveStoreError("SEC archive response has no body")
                return persist_archive_document(
                    self.cache_root,
                    document,
                    content,
                    retrieved_at=stamp,
                    expected_sha256=expected_sha256,
                    http_etag=etag,
                    http_last_modified=last_modified,
                )
            except ArchiveResponseTooLarge:
                raise
            except (requests.RequestException, ArchiveStoreError) as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    self._sleep(min(2**attempt, 4))
        raise ArchiveStoreError(f"SEC archive fetch failed after retries for {url}: {last_error}")

    def fetch_primary_document(
        self,
        manifest: Mapping[str, Any],
        *,
        retrieved_at: str | datetime | None = None,
        expected_sha256: str | None = None,
        max_document_bytes: int | None = None,
    ) -> dict[str, Any]:
        """Fetch/persist the declared primary document and return a new manifest version."""
        validate_manifest(manifest)
        primary = next(
            (item for item in manifest["documents"] if item.get("role") == "primary"),
            None,
        )
        if primary is None:
            raise ArchiveStoreError("filing manifest has no declared primary document")
        receipt = self.fetch_document(
            primary,
            retrieved_at=retrieved_at,
            expected_sha256=expected_sha256,
            max_document_bytes=max_document_bytes,
        )
        result = receipt.to_dict() if isinstance(receipt, ArchiveReceipt) else receipt
        return with_document_retrievals(
            manifest, {str(primary["document_id"]): result}
        )


__all__ = [
    "ARCHIVE_RECEIPT_SCHEMA",
    "ArchiveResponseTooLarge",
    "ArchiveReceipt",
    "ArchiveStoreError",
    "ChecksumMismatch",
    "DEFAULT_MAX_DOCUMENT_BYTES",
    "HARD_MAX_ARCHIVE_RECEIPT_BYTES",
    "HARD_MAX_DOCUMENT_BYTES",
    "HARD_MAX_HTTP_METADATA_BYTES",
    "SecFilingArchiveCollector",
    "content_storage_key",
    "document_with_retrieval",
    "manifest_storage_key",
    "missing_document_receipt",
    "persist_archive_document",
    "persist_filing_manifest",
    "read_archive_document",
    "read_primary_document",
    "read_filing_manifest",
    "receipt_storage_key",
]
