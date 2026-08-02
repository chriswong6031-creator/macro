"""Bounded, receipt-rich SEC Company Facts snapshots for Filing Forensics.

This is a source-plane collector only.  It has no historical Company Facts API
to query and therefore does *not* accept an ``as_of`` or claim point-in-time
eligibility.  A caller supplies ``source_snapshot_at`` only to label the
current source snapshot being retained; it must be contemporaneous with the
actual acquisition and recording clocks.  Individual SEC fact ``filed`` dates
are retained exactly in the byte-faithful response, but are not used as an
acceptance-time cutoff.

The raw namespace is intentionally independent of the pre-existing generic
``edgar_forensics`` source contract.  The flow is:

1. stream a bounded Company Facts response into memory;
2. retain those exact decoded JSON bytes under a response checksum;
3. retain an append-only capture receipt plus a separate canonical logical
   checksum/occurrence inventory;
4. write and verify an immutable issuer manifest; then
5. atomically publish a *verified manifest pointer* as the only latest source
   consumers may trust.

Pacing is per collector process.  The scheduler must still enforce the SEC's
aggregate per-IP request limit when more than one process or runner can fire.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import gzip
from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Iterable, Iterator, Mapping

import requests

from collectors.fundamental_forensics_acquisition import (
    AcquisitionError,
    AcquisitionTarget,
    normalize_targets,
)
from engine.fundamental_forensics.models import canonical_json, parse_utc, utc_text
from engine.fundamental_forensics.sec_document_spine import FilingManifestError, canonical_cik


COMPANYFACTS_RUN_SCHEMA = "fundamental_forensics.sec_companyfacts_run/v2"
COMPANYFACTS_TICKER_SCHEMA = "fundamental_forensics.sec_companyfacts_ticker_receipt/v2"
COMPANYFACTS_CAPTURE_SCHEMA = "fundamental_forensics.sec_companyfacts_capture/v2"
COMPANYFACTS_MANIFEST_SCHEMA = "fundamental_forensics.sec_companyfacts_manifest/v2"
COMPANYFACTS_POINTER_SCHEMA = "fundamental_forensics.sec_companyfacts_manifest_pointer/v2"
COMPANYFACTS_ENDPOINT = "companyfacts"
SEC_DATA_ORIGIN = "https://data.sec.gov"

# Do not share a directory, receipt schema, or latest pointer with
# collectors.edgar_forensics.  That collector owns <CIK>/companyfacts/.
COMPANYFACTS_RAW_NAMESPACE = "companyfacts_v3"
COMPANYFACTS_ARCHIVE_NAMESPACE = Path("wave3_companyfacts")
COMPANYFACTS_MANIFEST_ROOT = COMPANYFACTS_ARCHIVE_NAMESPACE / "manifests"
COMPANYFACTS_TICKER_RECEIPT_ROOT = COMPANYFACTS_ARCHIVE_NAMESPACE / "ticker_receipts"
COMPANYFACTS_RUN_ROOT = COMPANYFACTS_ARCHIVE_NAMESPACE / "runs"

# The request is deliberately bounded.  Company Facts responses can be larger
# than Submissions, but this lane must never turn into a universe mirror.
HARD_MAX_TICKERS = 32
HARD_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
HARD_MAX_TICKER_BYTES = 64 * 1024 * 1024
HARD_MAX_TOTAL_BYTES = 512 * 1024 * 1024

DEFAULT_MAX_TICKERS = 12
DEFAULT_MAX_RESPONSE_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_TICKER_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 256 * 1024 * 1024

# A snapshot label may be a few seconds before/after the durable recording
# clock, but never an arbitrary historical or future backtest cutoff.
SNAPSHOT_CLOCK_TOLERANCE_SECONDS = 5

OPERATOR_CONSTRAINTS = (
    "SEC pacing is enforced per collector process at no more than 10 requests per second; "
    "the scheduler must enforce the aggregate per-IP limit across concurrent processes/runners.",
)

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_CAPTURE_ID_RE = re.compile(r"^ffseccfc_[a-f0-9]{64}$")
_MANIFEST_ID_RE = re.compile(r"^ffseccfm_[a-f0-9]{64}$")
_POINTER_ID_RE = re.compile(r"^ffseccfp_[a-f0-9]{64}$")
_TICKER_RECEIPT_ID_RE = re.compile(r"^ffseccft_[a-f0-9]{64}$")
_RUN_ID_RE = re.compile(r"^ffseccfr_[a-f0-9]{64}$")
_REQUEST_ID_RE = re.compile(r"^ffseccfq_[a-f0-9]{64}$")
_ERROR_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


class CompanyFactsAcquisitionError(RuntimeError):
    """An explicit Company Facts acquisition is invalid or unsafe."""


class CompanyFactsResponseTooLarge(CompanyFactsAcquisitionError):
    """An SEC Company Facts response exceeded the admitted byte budget."""


class _RetainedResponseVerificationError(CompanyFactsAcquisitionError):
    """Read-back failed after a response had crossed the durable boundary."""

    def __init__(self, message: str, *, response_bytes: int) -> None:
        super().__init__(message)
        self.response_bytes = response_bytes


class _TransientSecError(RuntimeError):
    """Internal retryable SEC response failure."""


Fetcher = Callable[..., Any]
UtcNow = Callable[[], datetime]


@dataclass(frozen=True)
class CompanyFactsCapture:
    """Append-only receipt for one byte-faithful SEC Company Facts response."""

    schema: str
    capture_id: str
    cik: str
    endpoint: str
    url: str
    clocks: Mapping[str, str]
    response: Mapping[str, Any]
    logical: Mapping[str, Any]
    http: Mapping[str, str | None]
    object_repaired: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "capture_id": self.capture_id,
            "cik": self.cik,
            "endpoint": self.endpoint,
            "url": self.url,
            "clocks": dict(self.clocks),
            "response": dict(self.response),
            "logical": dict(self.logical),
            "http": dict(self.http),
            "object_repaired": self.object_repaired,
        }


def _normalized_clock(value: str | datetime, *, field: str) -> str:
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise CompanyFactsAcquisitionError(str(exc)) from exc
    if parsed is None:  # pragma: no cover - required by the public signatures
        raise CompanyFactsAcquisitionError(f"{field} is required")
    return utc_text(parsed) or ""  # pragma: no cover - parsed is non-null


def _clock_datetime(value: str | datetime, *, field: str) -> datetime:
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise CompanyFactsAcquisitionError(str(exc)) from exc
    if parsed is None:  # pragma: no cover - required by the public signatures
        raise CompanyFactsAcquisitionError(f"{field} is required")
    return parsed


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _observed_clock(now: UtcNow, *, field: str) -> tuple[datetime, str]:
    value = now()
    parsed = _clock_datetime(value, field=field)
    return parsed, utc_text(parsed) or ""  # pragma: no cover - parsed is non-null


def _normalized_cik(value: int | str) -> str:
    try:
        return canonical_cik(value)
    except FilingManifestError as exc:
        raise CompanyFactsAcquisitionError(str(exc)) from exc


def _normalized_ticker(value: str) -> str:
    ticker = str(value or "").strip().upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise CompanyFactsAcquisitionError(f"invalid ticker: {value!r}")
    return ticker


def _validated_user_agent(value: str) -> str:
    text = str(value or "").strip()
    if not text or "\r" in text or "\n" in text:
        raise CompanyFactsAcquisitionError(
            "SEC user agent must identify an application and contact email"
        )
    parts = text.rsplit(None, 1)
    if len(parts) != 2 or not parts[0].strip() or not _EMAIL_RE.fullmatch(parts[1]):
        raise CompanyFactsAcquisitionError(
            "SEC user agent must identify an application and contact email"
        )
    return text


def companyfacts_url(cik: int | str) -> str:
    """Return the canonical SEC Company Facts endpoint for one CIK."""
    cik10 = _normalized_cik(cik)
    return f"{SEC_DATA_ORIGIN}/api/xbrl/companyfacts/CIK{cik10}.json"


def _positive_limit(value: int, *, field: str, ceiling: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CompanyFactsAcquisitionError(f"{field} must be a positive integer")
    if value > ceiling:
        raise CompanyFactsAcquisitionError(f"{field} exceeds hard safety ceiling {ceiling}")
    return value


def _validate_limits(
    *,
    max_tickers: int,
    max_response_bytes: int,
    max_ticker_bytes: int,
    max_total_bytes: int,
) -> dict[str, int]:
    limits = {
        "max_tickers": _positive_limit(
            max_tickers, field="max_tickers", ceiling=HARD_MAX_TICKERS
        ),
        "max_response_bytes": _positive_limit(
            max_response_bytes,
            field="max_response_bytes",
            ceiling=HARD_MAX_RESPONSE_BYTES,
        ),
        "max_ticker_bytes": _positive_limit(
            max_ticker_bytes,
            field="max_ticker_bytes",
            ceiling=HARD_MAX_TICKER_BYTES,
        ),
        "max_total_bytes": _positive_limit(
            max_total_bytes,
            field="max_total_bytes",
            ceiling=HARD_MAX_TOTAL_BYTES,
        ),
    }
    if limits["max_ticker_bytes"] < limits["max_response_bytes"]:
        raise CompanyFactsAcquisitionError(
            "max_ticker_bytes must be at least max_response_bytes"
        )
    if limits["max_total_bytes"] < limits["max_ticker_bytes"]:
        raise CompanyFactsAcquisitionError(
            "max_total_bytes must be at least max_ticker_bytes"
        )
    return limits


def _safe_relative(value: str | Path) -> Path:
    text = str(value)
    relative = Path(text)
    if (
        not text
        or "\\" in text
        or "\x00" in text
        or relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise CompanyFactsAcquisitionError(f"unsafe local source path: {value!r}")
    return relative


def _safe_child(root: Path, relative: str | Path) -> Path:
    checked_root = Path(root).resolve()
    child = (checked_root / _safe_relative(relative)).resolve()
    try:
        child.relative_to(checked_root)
    except ValueError as exc:
        raise CompanyFactsAcquisitionError(
            f"source path escapes root: {relative!r}"
        ) from exc
    return child


def _checked_root(value: Path, *, field: str) -> Path:
    root = Path(value)
    if root.is_symlink():
        raise CompanyFactsAcquisitionError(f"{field} cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():  # pragma: no cover - mkdir normally raises first
        raise CompanyFactsAcquisitionError(f"{field} is not a directory")
    return root.resolve()


def _temp_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temp_sibling(path)
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            pass
    finally:
        temporary.unlink(missing_ok=True)


def _gzip_bytes(content: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(content)
    return buffer.getvalue()


def _read_gzip_limited(path: Path, *, maximum: int) -> bytes:
    try:
        with gzip.open(path, "rb") as handle:
            content = handle.read(maximum + 1)
    except (OSError, EOFError) as exc:
        raise CompanyFactsAcquisitionError("Company Facts source object is unreadable") from exc
    if len(content) > maximum:
        raise CompanyFactsAcquisitionError("Company Facts source object exceeds bounded read limit")
    return content


def _write_and_verify_json(path: Path, value: Mapping[str, Any], *, label: str) -> None:
    encoded = canonical_json(dict(value)).encode("utf-8")
    _atomic_write(path, encoded)
    try:
        observed = path.read_bytes()
        parsed = json.loads(observed.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanyFactsAcquisitionError(f"failed to read back {label}") from exc
    if observed != encoded or parsed != dict(value):
        raise CompanyFactsAcquisitionError(f"{label} read-back mismatch")


def _write_immutable_json(path: Path, value: Mapping[str, Any], *, label: str) -> None:
    encoded = canonical_json(dict(value)).encode("utf-8")
    if path.exists():
        try:
            observed = path.read_bytes()
        except OSError as exc:
            raise CompanyFactsAcquisitionError(f"cannot read existing {label}") from exc
        if observed != encoded:
            raise CompanyFactsAcquisitionError(f"immutable {label} identity is corrupted")
    else:
        _atomic_write(path, encoded)
    try:
        observed = path.read_bytes()
        parsed = json.loads(observed.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanyFactsAcquisitionError(f"failed to read back {label}") from exc
    if observed != encoded or parsed != dict(value):
        raise CompanyFactsAcquisitionError(f"{label} read-back mismatch")


def _header(headers: Any, name: str) -> str | None:
    if not isinstance(headers, Mapping):
        return None
    value = headers.get(name)
    if value is None:
        value = headers.get(name.lower())
    if value is None:
        return None
    return str(value)


def _reject_declared_oversize(headers: Any, limit: int, *, url: str) -> None:
    raw = _header(headers, "Content-Length")
    if raw is None:
        return
    try:
        declared = int(raw.strip())
    except ValueError:
        return
    if declared < 0:
        raise CompanyFactsResponseTooLarge(
            f"SEC Company Facts response has invalid Content-Length for {url}"
        )
    if declared > limit:
        raise CompanyFactsResponseTooLarge(
            "SEC Company Facts response exceeds bounded ingest limit "
            f"({declared} > {limit}) for {url}"
        )


def _default_fetcher(
    url: str, *, headers: Mapping[str, str], timeout: float, stream: bool
) -> Any:
    return requests.get(url, headers=dict(headers), timeout=timeout, stream=stream)


class SecCompanyFactsCollector:
    """Paced SEC Company Facts client with streamed, bounded response admission.

    The 100ms floor applies to this one process only.  ``OPERATOR_CONSTRAINTS``
    records the required cross-process aggregate limit for the scheduler.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        min_interval_seconds: float = 0.12,
        timeout_seconds: float = 30.0,
        max_attempts: int = 4,
        fetcher: Fetcher | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.user_agent = _validated_user_agent(user_agent)
        try:
            interval = float(min_interval_seconds)
            timeout = float(timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise CompanyFactsAcquisitionError("SEC pacing and timeout must be numeric") from exc
        if not math.isfinite(interval) or interval < 0:
            raise CompanyFactsAcquisitionError(
                "min_interval_seconds must be finite and non-negative"
            )
        if not math.isfinite(timeout) or timeout <= 0:
            raise CompanyFactsAcquisitionError("timeout_seconds must be finite and positive")
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or max_attempts < 1
            or max_attempts > 8
        ):
            raise CompanyFactsAcquisitionError("max_attempts must be an integer from 1 to 8")
        self.min_interval_seconds = max(0.1, interval)
        self.timeout_seconds = timeout
        self.max_attempts = max_attempts
        self.fetcher = fetcher or _default_fetcher
        self._sleep = sleeper
        self._monotonic = monotonic
        self._last_request_at: float | None = None

    def _pace(self) -> None:
        if self._last_request_at is None:
            return
        wait = self.min_interval_seconds - (self._monotonic() - self._last_request_at)
        if wait > 0:
            self._sleep(wait)

    @staticmethod
    def _close_response(response: Any) -> None:
        closer = getattr(response, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass

    @staticmethod
    def _stream_body(response: Any, *, limit: int, url: str) -> bytes:
        response_headers = getattr(response, "headers", {})
        _reject_declared_oversize(response_headers, limit, url=url)
        iterator = getattr(response, "iter_content", None)
        if not callable(iterator):
            raise CompanyFactsAcquisitionError(
                "SEC fetcher must provide iter_content for bounded streaming"
            )
        chunks: list[bytes] = []
        total = 0
        try:
            stream = iterator(chunk_size=64 * 1024)
            for chunk in stream:
                if not isinstance(chunk, bytes):
                    raise CompanyFactsAcquisitionError(
                        "SEC Company Facts response stream yielded non-bytes"
                    )
                if not chunk:
                    continue
                total += len(chunk)
                if total > limit:
                    raise CompanyFactsResponseTooLarge(
                        "SEC Company Facts response exceeds bounded ingest limit "
                        f"({total} > {limit}) for {url}"
                    )
                chunks.append(chunk)
        except CompanyFactsResponseTooLarge:
            raise
        except requests.RequestException:
            raise
        except Exception as exc:
            raise CompanyFactsAcquisitionError(
                "SEC Company Facts response stream failed"
            ) from exc
        return b"".join(chunks)

    def fetch(self, cik: int | str, *, max_response_bytes: int) -> tuple[bytes, dict[str, str | None]]:
        """Fetch one response with a cap enforced during streamed body reading."""
        cik10 = _normalized_cik(cik)
        limit = _positive_limit(
            max_response_bytes,
            field="max_response_bytes",
            ceiling=HARD_MAX_RESPONSE_BYTES,
        )
        url = companyfacts_url(cik10)
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        last_error: BaseException | None = None
        for attempt in range(self.max_attempts):
            self._pace()
            response: Any | None = None
            try:
                response = self.fetcher(
                    url,
                    headers=headers,
                    timeout=self.timeout_seconds,
                    stream=True,
                )
                self._last_request_at = self._monotonic()
                status = getattr(response, "status_code", None)
                if isinstance(status, bool) or not isinstance(status, int):
                    raise CompanyFactsAcquisitionError(
                        "SEC fetcher returned no integer status_code"
                    )
                if status in {429, 500, 502, 503, 504}:
                    raise _TransientSecError(f"SEC transient HTTP {status}")
                if status < 200 or status >= 300:
                    raise CompanyFactsAcquisitionError(f"SEC Company Facts HTTP {status}")
                content = self._stream_body(response, limit=limit, url=url)
                response_headers = getattr(response, "headers", {})
                return content, {
                    "url": url,
                    "http_etag": _header(response_headers, "ETag"),
                    "http_last_modified": _header(response_headers, "Last-Modified"),
                }
            except CompanyFactsResponseTooLarge:
                raise
            except (_TransientSecError, requests.RequestException) as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    self._sleep(min(2**attempt, 4))
            finally:
                if response is not None:
                    self._close_response(response)
        raise CompanyFactsAcquisitionError(
            f"SEC Company Facts fetch failed after retries for {url}: {last_error}"
        )


def iter_companyfacts_occurrences(payload: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield every SEC unit-array entry without deduplicating vintage rows."""
    facts = payload.get("facts")
    if not isinstance(facts, Mapping):
        raise CompanyFactsAcquisitionError("Company Facts payload.facts must be an object")
    for taxonomy in sorted(facts, key=lambda item: str(item)):
        concepts = facts[taxonomy]
        if not isinstance(concepts, Mapping):
            raise CompanyFactsAcquisitionError("Company Facts taxonomy must be an object")
        for concept in sorted(concepts, key=lambda item: str(item)):
            definition = concepts[concept]
            if not isinstance(definition, Mapping):
                raise CompanyFactsAcquisitionError("Company Facts concept must be an object")
            units = definition.get("units", {})
            if units is None:
                units = {}
            if not isinstance(units, Mapping):
                raise CompanyFactsAcquisitionError("Company Facts concept.units must be an object")
            for unit in sorted(units, key=lambda item: str(item)):
                entries = units[unit]
                if not isinstance(entries, list):
                    raise CompanyFactsAcquisitionError("Company Facts unit must be an array")
                for entry_index, entry in enumerate(entries):
                    if not isinstance(entry, Mapping):
                        raise CompanyFactsAcquisitionError(
                            "Company Facts unit entry must be an object"
                        )
                    yield {
                        "taxonomy": str(taxonomy),
                        "concept": str(concept),
                        "unit": str(unit),
                        "entry_index": entry_index,
                        "sec_fact": dict(entry),
                    }


def _occurrence_summary(payload: Mapping[str, Any]) -> tuple[int, str]:
    digest = sha256()
    count = 0
    for occurrence in iter_companyfacts_occurrences(payload):
        digest.update(canonical_json(occurrence).encode("utf-8"))
        count += 1
    return count, digest.hexdigest()


def _validated_payload(
    response_content: bytes, *, expected_cik: str
) -> tuple[dict[str, Any], bytes, int, str]:
    try:
        payload = json.loads(response_content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanyFactsAcquisitionError(
            "SEC Company Facts response is not UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise CompanyFactsAcquisitionError("SEC Company Facts response must be a JSON object")
    if _normalized_cik(payload.get("cik")) != expected_cik:
        raise CompanyFactsAcquisitionError("SEC Company Facts payload CIK does not match target")
    occurrence_count, occurrence_sha256 = _occurrence_summary(payload)
    try:
        canonical = canonical_json(payload).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CompanyFactsAcquisitionError(
            "SEC Company Facts payload cannot be canonicalized"
        ) from exc
    return payload, canonical, occurrence_count, occurrence_sha256


def _source_object_relative(cik: str, response_digest: str) -> Path:
    if not _SHA256_RE.fullmatch(response_digest):
        raise CompanyFactsAcquisitionError("response checksum must be lowercase SHA-256")
    return (
        Path(cik)
        / COMPANYFACTS_RAW_NAMESPACE
        / "objects"
        / response_digest[:2]
        / f"{response_digest}.json.gz"
    )


def _capture_key(cik: str, capture_id: str) -> str:
    if not _CAPTURE_ID_RE.fullmatch(capture_id):
        raise CompanyFactsAcquisitionError("invalid Company Facts capture id")
    return (
        Path(cik) / COMPANYFACTS_RAW_NAMESPACE / "captures" / f"{capture_id}.json"
    ).as_posix()


def _capture_id(record: Mapping[str, Any]) -> str:
    body = dict(record)
    body.pop("capture_id", None)
    return "ffseccfc_" + sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _manifest_id(record: Mapping[str, Any]) -> str:
    body = dict(record)
    body.pop("manifest_id", None)
    return "ffseccfm_" + sha256(canonical_json(body).encode("utf-8")).hexdigest()


def manifest_id_for(record: Mapping[str, Any]) -> str:
    """Return the issuer-manifest identity binding every field except itself."""
    return _manifest_id(record)


def _pointer_id(record: Mapping[str, Any]) -> str:
    body = dict(record)
    body.pop("pointer_id", None)
    return "ffseccfp_" + sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _ticker_receipt_id(record: Mapping[str, Any]) -> str:
    body = dict(record)
    body.pop("ticker_receipt_id", None)
    return "ffseccft_" + sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _run_id(record: Mapping[str, Any]) -> str:
    body = dict(record)
    body.pop("run_id", None)
    return "ffseccfr_" + sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _manifest_key(manifest: Mapping[str, Any]) -> str:
    issuer = manifest.get("issuer")
    manifest_id = str(manifest.get("manifest_id") or "")
    if not isinstance(issuer, Mapping) or not _MANIFEST_ID_RE.fullmatch(manifest_id):
        raise CompanyFactsAcquisitionError("invalid Company Facts manifest identity")
    cik = _normalized_cik(issuer.get("cik"))
    return (COMPANYFACTS_MANIFEST_ROOT / cik / f"{manifest_id}.json").as_posix()


def _manifest_pointer_key(cik: str) -> str:
    return (COMPANYFACTS_MANIFEST_ROOT / cik / "latest.json").as_posix()


def _ticker_receipt_key(receipt: Mapping[str, Any]) -> str:
    target = receipt.get("target")
    receipt_id = str(receipt.get("ticker_receipt_id") or "")
    if not isinstance(target, Mapping) or not _TICKER_RECEIPT_ID_RE.fullmatch(receipt_id):
        raise CompanyFactsAcquisitionError("invalid Company Facts ticker receipt identity")
    cik = _normalized_cik(target.get("cik"))
    return (COMPANYFACTS_TICKER_RECEIPT_ROOT / cik / f"{receipt_id}.json").as_posix()


def _run_key(run: Mapping[str, Any]) -> str:
    run_id = str(run.get("run_id") or "")
    if not _RUN_ID_RE.fullmatch(run_id):
        raise CompanyFactsAcquisitionError("invalid Company Facts run identity")
    return (COMPANYFACTS_RUN_ROOT / f"{run_id}.json").as_posix()


def _validate_capture(record: Mapping[str, Any]) -> CompanyFactsCapture:
    required = {
        "schema",
        "capture_id",
        "cik",
        "endpoint",
        "url",
        "clocks",
        "response",
        "logical",
        "http",
        "object_repaired",
    }
    if set(record) != required or record.get("schema") != COMPANYFACTS_CAPTURE_SCHEMA:
        raise CompanyFactsAcquisitionError("Company Facts capture shape is invalid")
    capture_id = str(record.get("capture_id") or "")
    if not _CAPTURE_ID_RE.fullmatch(capture_id) or capture_id != _capture_id(record):
        raise CompanyFactsAcquisitionError("Company Facts capture identity mismatch")
    cik = _normalized_cik(record.get("cik"))
    if record.get("endpoint") != COMPANYFACTS_ENDPOINT or record.get("url") != companyfacts_url(cik):
        raise CompanyFactsAcquisitionError("Company Facts capture endpoint is invalid")
    clocks = record.get("clocks")
    response = record.get("response")
    logical = record.get("logical")
    http = record.get("http")
    if not all(isinstance(item, Mapping) for item in (clocks, response, logical, http)):
        raise CompanyFactsAcquisitionError("Company Facts capture sections must be objects")
    if set(clocks) != {
        "acquisition_started_at",
        "captured_at",
        "recorded_at",
        "source_snapshot_at",
    }:
        raise CompanyFactsAcquisitionError("Company Facts capture clocks are invalid")
    parsed_clocks: dict[str, datetime] = {}
    for field, value in clocks.items():
        parsed = _clock_datetime(str(value or ""), field=f"capture.{field}")
        if value != utc_text(parsed):
            raise CompanyFactsAcquisitionError("Company Facts capture clocks are not UTC-normalized")
        parsed_clocks[field] = parsed
    if parsed_clocks["captured_at"] < parsed_clocks["acquisition_started_at"]:
        raise CompanyFactsAcquisitionError("Company Facts capture precedes acquisition start")
    if parsed_clocks["recorded_at"] < parsed_clocks["acquisition_started_at"]:
        raise CompanyFactsAcquisitionError("Company Facts recorded_at predates acquisition")
    normalized_snapshot, normalized_recorded = _validate_temporal_contract(
        source_snapshot_at=str(clocks["source_snapshot_at"]),
        recorded_at=str(clocks["recorded_at"]),
        acquisition_started_at=parsed_clocks["acquisition_started_at"],
        captured_at=parsed_clocks["captured_at"],
    )
    if (
        normalized_snapshot != clocks["source_snapshot_at"]
        or normalized_recorded != clocks["recorded_at"]
    ):
        raise CompanyFactsAcquisitionError(
            "Company Facts capture clocks are not acquisition-normalized"
        )
    expected_response = {"sha256", "bytes", "object_path"}
    if set(response) != expected_response:
        raise CompanyFactsAcquisitionError("Company Facts capture response shape is invalid")
    response_sha = str(response.get("sha256") or "")
    response_bytes = response.get("bytes")
    if not _SHA256_RE.fullmatch(response_sha):
        raise CompanyFactsAcquisitionError("Company Facts capture response checksum is invalid")
    if isinstance(response_bytes, bool) or not isinstance(response_bytes, int) or response_bytes < 1:
        raise CompanyFactsAcquisitionError("Company Facts capture response length is invalid")
    if response.get("object_path") != _source_object_relative(cik, response_sha).as_posix():
        raise CompanyFactsAcquisitionError("Company Facts capture object path is invalid")
    expected_logical = {
        "sha256",
        "bytes",
        "fact_occurrence_count",
        "fact_occurrence_sha256",
        "occurrence_fields",
    }
    if set(logical) != expected_logical:
        raise CompanyFactsAcquisitionError("Company Facts capture logical shape is invalid")
    logical_sha = str(logical.get("sha256") or "")
    logical_bytes = logical.get("bytes")
    occurrence_count = logical.get("fact_occurrence_count")
    occurrence_sha = str(logical.get("fact_occurrence_sha256") or "")
    if not _SHA256_RE.fullmatch(logical_sha) or not _SHA256_RE.fullmatch(occurrence_sha):
        raise CompanyFactsAcquisitionError("Company Facts capture logical checksum is invalid")
    if isinstance(logical_bytes, bool) or not isinstance(logical_bytes, int) or logical_bytes < 1:
        raise CompanyFactsAcquisitionError("Company Facts capture logical length is invalid")
    if isinstance(occurrence_count, bool) or not isinstance(occurrence_count, int) or occurrence_count < 0:
        raise CompanyFactsAcquisitionError("Company Facts capture occurrence count is invalid")
    if logical.get("occurrence_fields") != [
        "accn",
        "filed",
        "form",
        "fy",
        "fp",
        "frame",
        "end",
        "start",
    ]:
        raise CompanyFactsAcquisitionError("Company Facts capture occurrence contract is invalid")
    if set(http) != {"etag", "last_modified"} or any(
        value is not None and not isinstance(value, str) for value in http.values()
    ):
        raise CompanyFactsAcquisitionError("Company Facts capture HTTP metadata is invalid")
    if not isinstance(record.get("object_repaired"), bool):
        raise CompanyFactsAcquisitionError("Company Facts capture repair flag is invalid")
    return CompanyFactsCapture(
        schema=COMPANYFACTS_CAPTURE_SCHEMA,
        capture_id=capture_id,
        cik=cik,
        endpoint=COMPANYFACTS_ENDPOINT,
        url=companyfacts_url(cik),
        clocks=dict(clocks),
        response=dict(response),
        logical=dict(logical),
        http=dict(http),
        object_repaired=bool(record["object_repaired"]),
    )


def _persist_response_object(
    raw_root: Path, *, cik: str, response_content: bytes
) -> tuple[str, int, str, bool]:
    response_sha = sha256(response_content).hexdigest()
    object_path = _source_object_relative(cik, response_sha)
    target = _safe_child(raw_root, object_path)
    repaired = False
    durable_response = False
    try:
        if target.exists():
            try:
                existing = _read_gzip_limited(target, maximum=len(response_content))
            except CompanyFactsAcquisitionError:
                existing = b""
            if existing != response_content:
                repaired = True
                _atomic_write(target, _gzip_bytes(response_content))
            # Either the byte-identical object was already verified readable
            # or a replacement has crossed os.replace().
            durable_response = True
        else:
            _atomic_write(target, _gzip_bytes(response_content))
            durable_response = True
    except Exception as exc:
        # ``os.replace`` can succeed just before a later filesystem operation
        # reports an error.  Do not let that rare post-replace failure make a
        # durable admitted response invisible to byte accounting.  Conversely,
        # only charge after a bounded exact read proves the object exists.
        try:
            observed_after_error = _read_gzip_limited(
                target,
                maximum=len(response_content),
            )
        except CompanyFactsAcquisitionError:
            raise
        if (
            observed_after_error == response_content
            and sha256(observed_after_error).hexdigest() == response_sha
        ):
            raise _RetainedResponseVerificationError(
                "Company Facts response write reported failure after durable persistence",
                response_bytes=len(response_content),
            ) from exc
        raise
    try:
        observed = _read_gzip_limited(target, maximum=len(response_content))
        if observed != response_content or sha256(observed).hexdigest() != response_sha:
            raise CompanyFactsAcquisitionError(
                "Company Facts response checksum mismatch after persistence"
            )
    except CompanyFactsAcquisitionError as exc:
        if durable_response:
            raise _RetainedResponseVerificationError(
                "Company Facts response read-back failed after durable persistence",
                response_bytes=len(response_content),
            ) from exc
        raise
    return response_sha, len(response_content), object_path.as_posix(), repaired


def _build_capture(
    *,
    cik: str,
    response_sha256: str,
    response_bytes: int,
    response_object_path: str,
    logical_content: bytes,
    occurrence_count: int,
    occurrence_sha256: str,
    acquisition_started_at: str,
    captured_at: str,
    recorded_at: str,
    source_snapshot_at: str,
    http_etag: str | None,
    http_last_modified: str | None,
    object_repaired: bool,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema": COMPANYFACTS_CAPTURE_SCHEMA,
        "capture_id": "",
        "cik": cik,
        "endpoint": COMPANYFACTS_ENDPOINT,
        "url": companyfacts_url(cik),
        "clocks": {
            "acquisition_started_at": acquisition_started_at,
            "captured_at": captured_at,
            "recorded_at": recorded_at,
            "source_snapshot_at": source_snapshot_at,
        },
        "response": {
            "sha256": response_sha256,
            "bytes": response_bytes,
            "object_path": response_object_path,
        },
        "logical": {
            "sha256": sha256(logical_content).hexdigest(),
            "bytes": len(logical_content),
            "fact_occurrence_count": occurrence_count,
            "fact_occurrence_sha256": occurrence_sha256,
            "occurrence_fields": [
                "accn",
                "filed",
                "form",
                "fy",
                "fp",
                "frame",
                "end",
                "start",
            ],
        },
        "http": {"etag": http_etag, "last_modified": http_last_modified},
        "object_repaired": object_repaired,
    }
    record["capture_id"] = _capture_id(record)
    _validate_capture(record)
    return record


def _persist_capture(raw_root: Path, capture: Mapping[str, Any]) -> str:
    normalized = _validate_capture(capture)
    key = _capture_key(normalized.cik, normalized.capture_id)
    _write_immutable_json(
        _safe_child(raw_root, key), normalized.to_dict(), label="Company Facts capture receipt"
    )
    return key


def _read_capture(raw_root: Path, storage_key: str) -> dict[str, Any]:
    key = _safe_relative(storage_key)
    # Verify namespace structurally after parse/identity validation, not by a
    # broad string allow-list that could accidentally admit a sibling source.
    if COMPANYFACTS_RAW_NAMESPACE not in key.parts or "captures" not in key.parts:
        raise CompanyFactsAcquisitionError("capture key is outside Company Facts raw namespace")
    path = _safe_child(Path(raw_root), key)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanyFactsAcquisitionError("missing or invalid Company Facts capture receipt") from exc
    if not isinstance(value, dict):
        raise CompanyFactsAcquisitionError("Company Facts capture receipt must be an object")
    capture = _validate_capture(value)
    if _capture_key(capture.cik, capture.capture_id) != key.as_posix():
        raise CompanyFactsAcquisitionError("Company Facts capture key does not match identity")
    return capture.to_dict()


def _validate_acquisition_inputs(
    *,
    source_snapshot_at: str | datetime,
    recorded_at: str | datetime,
    acquisition_started_at: datetime,
) -> tuple[str, datetime]:
    """Validate contemporaneous caller samples before a live acquisition.

    The caller's ``recorded_at`` is only an admission-time lower bound.  It is
    not a public retained-source clock: the response may not exist until well
    after the request starts.
    """
    caller_snapshot = _clock_datetime(
        source_snapshot_at,
        field="source_snapshot_at",
    )
    caller_recorded = _clock_datetime(recorded_at, field="recorded_at")
    tolerance = timedelta(seconds=SNAPSHOT_CLOCK_TOLERANCE_SECONDS)
    if abs(caller_recorded - acquisition_started_at) > tolerance:
        raise CompanyFactsAcquisitionError(
            "recorded_at must be contemporaneous with acquisition; Company Facts has no historical cutoff API"
        )
    if (
        caller_snapshot + tolerance < acquisition_started_at
        or caller_snapshot > acquisition_started_at + tolerance
    ):
        raise CompanyFactsAcquisitionError(
            "source_snapshot_at must be contemporaneous with acquisition; Company Facts has no historical cutoff API"
        )
    if abs(caller_snapshot - caller_recorded) > tolerance:
        raise CompanyFactsAcquisitionError(
            "source_snapshot_at must be contemporaneous with recorded_at; Company Facts has no historical cutoff API"
        )
    # This is a current-state endpoint, so a contemporaneous caller sample is
    # input evidence, not authority to backdate the observed source snapshot.
    snapshot = max(caller_snapshot, acquisition_started_at)
    return utc_text(snapshot) or "", max(caller_recorded, acquisition_started_at)


def _validate_temporal_contract(
    *,
    source_snapshot_at: str | datetime,
    recorded_at: str | datetime,
    acquisition_started_at: datetime,
    captured_at: datetime | None = None,
) -> tuple[str, str]:
    """Validate public clocks after source retention has actually occurred."""
    snapshot = max(
        _clock_datetime(source_snapshot_at, field="source_snapshot_at"),
        acquisition_started_at,
    )
    recorded = _clock_datetime(recorded_at, field="recorded_at")
    tolerance = timedelta(seconds=SNAPSHOT_CLOCK_TOLERANCE_SECONDS)
    if captured_at is not None:
        if captured_at < acquisition_started_at:
            raise CompanyFactsAcquisitionError("Company Facts capture precedes acquisition start")
        if recorded < captured_at:
            raise CompanyFactsAcquisitionError(
                "recorded_at predates durable Company Facts capture"
            )
        if recorded > captured_at + tolerance or snapshot > captured_at + tolerance:
            raise CompanyFactsAcquisitionError(
                "source_snapshot_at and recorded_at must not postdate observed capture"
            )
    elif recorded < acquisition_started_at:
        raise CompanyFactsAcquisitionError(
            "recorded_at predates acquisition"
        )
    return utc_text(snapshot) or "", utc_text(recorded) or ""


def _build_manifest(
    *, target: AcquisitionTarget, payload: Mapping[str, Any], capture: Mapping[str, Any]
) -> dict[str, Any]:
    source_capture = _validate_capture(capture)
    if source_capture.cik != target.cik:
        raise CompanyFactsAcquisitionError("capture CIK does not match manifest target")
    capture_key = _capture_key(target.cik, source_capture.capture_id)
    temporal_scope = {
        "kind": "current_sec_companyfacts_snapshot",
        "point_in_time_eligible": False,
        "acceptance_joined": False,
        "fact_filed_dates_preserved": True,
    }
    record: dict[str, Any] = {
        "schema": COMPANYFACTS_MANIFEST_SCHEMA,
        "manifest_id": "",
        "issuer": {
            "ticker": target.ticker,
            "cik": target.cik,
            "entity_name": str(payload.get("entityName") or "").strip(),
        },
        "clocks": {
            "source_snapshot_at": source_capture.clocks["source_snapshot_at"],
            "recorded_at": source_capture.clocks["recorded_at"],
            "acquisition_started_at": source_capture.clocks["acquisition_started_at"],
            "captured_at": source_capture.clocks["captured_at"],
        },
        "temporal_scope": temporal_scope,
        "source": {
            "capture_id": source_capture.capture_id,
            "capture_receipt_key": capture_key,
            "response_sha256": source_capture.response["sha256"],
            "response_bytes": source_capture.response["bytes"],
            "response_object_path": source_capture.response["object_path"],
            "logical_sha256": source_capture.logical["sha256"],
            "logical_bytes": source_capture.logical["bytes"],
            "fact_occurrence_count": source_capture.logical["fact_occurrence_count"],
            "fact_occurrence_sha256": source_capture.logical["fact_occurrence_sha256"],
        },
    }
    record["manifest_id"] = _manifest_id(record)
    validate_companyfacts_manifest(record)
    return record


def validate_companyfacts_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate a manifest that binds an immutable capture without PIT claims."""
    required = {"schema", "manifest_id", "issuer", "clocks", "temporal_scope", "source"}
    if set(manifest) != required or manifest.get("schema") != COMPANYFACTS_MANIFEST_SCHEMA:
        raise CompanyFactsAcquisitionError("Company Facts manifest shape is invalid")
    manifest_id = str(manifest.get("manifest_id") or "")
    if not _MANIFEST_ID_RE.fullmatch(manifest_id) or manifest_id != _manifest_id(manifest):
        raise CompanyFactsAcquisitionError("Company Facts manifest identity mismatch")
    issuer = manifest.get("issuer")
    clocks = manifest.get("clocks")
    temporal_scope = manifest.get("temporal_scope")
    source = manifest.get("source")
    if not all(isinstance(value, Mapping) for value in (issuer, clocks, temporal_scope, source)):
        raise CompanyFactsAcquisitionError("Company Facts manifest sections must be objects")
    cik = _normalized_cik(issuer.get("cik"))
    ticker = _normalized_ticker(issuer.get("ticker"))
    if issuer.get("cik") != cik or issuer.get("ticker") != ticker:
        raise CompanyFactsAcquisitionError("Company Facts manifest issuer is not normalized")
    if not isinstance(issuer.get("entity_name"), str):
        raise CompanyFactsAcquisitionError("Company Facts manifest entity_name must be a string")
    expected_clocks = {
        "source_snapshot_at",
        "recorded_at",
        "acquisition_started_at",
        "captured_at",
    }
    if set(clocks) != expected_clocks:
        raise CompanyFactsAcquisitionError("Company Facts manifest clocks are invalid")
    parsed: dict[str, datetime] = {}
    for field, value in clocks.items():
        clock = _clock_datetime(str(value or ""), field=f"manifest.{field}")
        if value != utc_text(clock):
            raise CompanyFactsAcquisitionError("Company Facts manifest clocks are not UTC-normalized")
        parsed[field] = clock
    if parsed["recorded_at"] < parsed["acquisition_started_at"]:
        raise CompanyFactsAcquisitionError("Company Facts manifest recorded_at predates acquisition")
    if parsed["captured_at"] < parsed["acquisition_started_at"]:
        raise CompanyFactsAcquisitionError("Company Facts manifest capture predates acquisition")
    normalized_snapshot, normalized_recorded = _validate_temporal_contract(
        source_snapshot_at=str(clocks["source_snapshot_at"]),
        recorded_at=str(clocks["recorded_at"]),
        acquisition_started_at=parsed["acquisition_started_at"],
        captured_at=parsed["captured_at"],
    )
    if (
        normalized_snapshot != clocks["source_snapshot_at"]
        or normalized_recorded != clocks["recorded_at"]
    ):
        raise CompanyFactsAcquisitionError(
            "Company Facts manifest clocks are not acquisition-normalized"
        )
    if temporal_scope != {
        "kind": "current_sec_companyfacts_snapshot",
        "point_in_time_eligible": False,
        "acceptance_joined": False,
        "fact_filed_dates_preserved": True,
    }:
        raise CompanyFactsAcquisitionError("Company Facts manifest temporal scope is invalid")
    expected_source = {
        "capture_id",
        "capture_receipt_key",
        "response_sha256",
        "response_bytes",
        "response_object_path",
        "logical_sha256",
        "logical_bytes",
        "fact_occurrence_count",
        "fact_occurrence_sha256",
    }
    if set(source) != expected_source:
        raise CompanyFactsAcquisitionError("Company Facts manifest source shape is invalid")
    capture_id = str(source.get("capture_id") or "")
    if not _CAPTURE_ID_RE.fullmatch(capture_id):
        raise CompanyFactsAcquisitionError("Company Facts manifest capture identity is invalid")
    if source.get("capture_receipt_key") != _capture_key(cik, capture_id):
        raise CompanyFactsAcquisitionError("Company Facts manifest capture key is invalid")
    response_sha = str(source.get("response_sha256") or "")
    logical_sha = str(source.get("logical_sha256") or "")
    occurrence_sha = str(source.get("fact_occurrence_sha256") or "")
    if not all(_SHA256_RE.fullmatch(item) for item in (response_sha, logical_sha, occurrence_sha)):
        raise CompanyFactsAcquisitionError("Company Facts manifest checksum is invalid")
    for field in ("response_bytes", "logical_bytes", "fact_occurrence_count"):
        value = source.get(field)
        minimum = 0 if field == "fact_occurrence_count" else 1
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise CompanyFactsAcquisitionError("Company Facts manifest source size is invalid")
    if source.get("response_object_path") != _source_object_relative(cik, response_sha).as_posix():
        raise CompanyFactsAcquisitionError("Company Facts manifest response path is invalid")


def persist_companyfacts_manifest(archive_root: Path, manifest: Mapping[str, Any]) -> str:
    """Write an immutable manifest.  Publishing latest is a separate commit."""
    record = dict(manifest)
    validate_companyfacts_manifest(record)
    key = _manifest_key(record)
    _write_immutable_json(
        _safe_child(Path(archive_root), key), record, label="Company Facts manifest"
    )
    return key


def read_companyfacts_manifest(archive_root: Path, storage_key: str) -> dict[str, Any]:
    """Read an immutable manifest and ensure its storage key matches its identity."""
    key = _safe_relative(storage_key)
    prefix = COMPANYFACTS_MANIFEST_ROOT.as_posix() + "/"
    if not key.as_posix().startswith(prefix):
        raise CompanyFactsAcquisitionError("storage key is outside Company Facts manifest root")
    try:
        value = json.loads(_safe_child(Path(archive_root), key).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanyFactsAcquisitionError("missing or invalid Company Facts manifest") from exc
    if not isinstance(value, dict):
        raise CompanyFactsAcquisitionError("Company Facts manifest must be an object")
    validate_companyfacts_manifest(value)
    if _manifest_key(value) != key.as_posix():
        raise CompanyFactsAcquisitionError("Company Facts manifest storage key does not match identity")
    return value


def _build_manifest_pointer(manifest: Mapping[str, Any], *, manifest_key: str) -> dict[str, Any]:
    validate_companyfacts_manifest(manifest)
    issuer = manifest["issuer"]
    clocks = manifest["clocks"]
    source = manifest["source"]
    record: dict[str, Any] = {
        "schema": COMPANYFACTS_POINTER_SCHEMA,
        "pointer_id": "",
        "cik": issuer["cik"],
        "manifest_id": manifest["manifest_id"],
        "manifest_key": manifest_key,
        "capture_id": source["capture_id"],
        "response_sha256": source["response_sha256"],
        "logical_sha256": source["logical_sha256"],
        "source_snapshot_at": clocks["source_snapshot_at"],
        "recorded_at": clocks["recorded_at"],
    }
    record["pointer_id"] = _pointer_id(record)
    _validate_manifest_pointer(record)
    return record


def _validate_manifest_pointer(pointer: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "pointer_id",
        "cik",
        "manifest_id",
        "manifest_key",
        "capture_id",
        "response_sha256",
        "logical_sha256",
        "source_snapshot_at",
        "recorded_at",
    }
    if set(pointer) != required or pointer.get("schema") != COMPANYFACTS_POINTER_SCHEMA:
        raise CompanyFactsAcquisitionError("Company Facts manifest pointer shape is invalid")
    pointer_id = str(pointer.get("pointer_id") or "")
    if not _POINTER_ID_RE.fullmatch(pointer_id) or pointer_id != _pointer_id(pointer):
        raise CompanyFactsAcquisitionError("Company Facts manifest pointer identity mismatch")
    cik = _normalized_cik(pointer.get("cik"))
    if pointer.get("cik") != cik:
        raise CompanyFactsAcquisitionError("Company Facts manifest pointer CIK is not normalized")
    manifest_id = str(pointer.get("manifest_id") or "")
    if not _MANIFEST_ID_RE.fullmatch(manifest_id):
        raise CompanyFactsAcquisitionError("Company Facts manifest pointer manifest id is invalid")
    if not _CAPTURE_ID_RE.fullmatch(str(pointer.get("capture_id") or "")):
        raise CompanyFactsAcquisitionError("Company Facts manifest pointer capture id is invalid")
    for field in ("response_sha256", "logical_sha256"):
        if not _SHA256_RE.fullmatch(str(pointer.get(field) or "")):
            raise CompanyFactsAcquisitionError("Company Facts manifest pointer checksum is invalid")
    for field in ("source_snapshot_at", "recorded_at"):
        parsed = _clock_datetime(str(pointer.get(field) or ""), field=f"pointer.{field}")
        if pointer.get(field) != utc_text(parsed):
            raise CompanyFactsAcquisitionError("Company Facts manifest pointer clock is invalid")
    key = str(pointer.get("manifest_key") or "")
    expected_key = (
        COMPANYFACTS_MANIFEST_ROOT / cik / f"{manifest_id}.json"
    ).as_posix()
    if key != expected_key:
        raise CompanyFactsAcquisitionError("Company Facts manifest pointer key is invalid")


@contextmanager
def _manifest_publish_lock(archive_root: Path) -> Iterator[None]:
    """Serialize latest-pointer decisions across local collector processes."""
    lock_path = _safe_child(
        Path(archive_root), COMPANYFACTS_ARCHIVE_NAMESPACE / ".manifest_publish.lock"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _manifest_capture_time(manifest: Mapping[str, Any]) -> datetime:
    clocks = manifest.get("clocks")
    if not isinstance(clocks, Mapping):  # pragma: no cover - validated callers
        raise CompanyFactsAcquisitionError("Company Facts manifest clocks are invalid")
    return _clock_datetime(str(clocks.get("captured_at") or ""), field="manifest.captured_at")


def _restore_manifest_pointer(path: Path, previous: bytes | None) -> None:
    """Restore a prior verified pointer if post-publication verification fails."""
    if previous is None:
        path.unlink(missing_ok=True)
        try:
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            pass
        return
    _atomic_write(path, previous)


def publish_verified_manifest_pointer(archive_root: Path, manifest_key: str) -> dict[str, Any]:
    """Publish a verified manifest without exposing a bad or older ``latest``.

    The manifest/capture records are immutable and may arrive out of order. A
    file lock covers the read/compare/replace sequence; a candidate whose
    capture time is not newer cannot rewind the latest verified source.
    """
    manifest = read_companyfacts_manifest(archive_root, manifest_key)
    pointer = _build_manifest_pointer(manifest, manifest_key=manifest_key)
    archive_path = Path(archive_root)
    cik = str(manifest["issuer"]["cik"])
    path = _safe_child(archive_path, _manifest_pointer_key(cik))
    with _manifest_publish_lock(archive_path):
        previous: bytes | None = None
        if path.exists():
            # Do not overwrite a malformed existing pointer.  A caller must
            # repair that explicitly rather than silently losing forensic
            # history.
            current_manifest = read_latest_companyfacts_manifest(archive_path, cik)
            previous = path.read_bytes()
            if _manifest_capture_time(manifest) <= _manifest_capture_time(current_manifest):
                return _build_manifest_pointer(
                    current_manifest,
                    manifest_key=_manifest_key(current_manifest),
                )
        try:
            _write_and_verify_json(path, pointer, label="verified Company Facts manifest pointer")
            # This second read checks both pointer identity and pointer-to-manifest binding.
            if read_latest_companyfacts_manifest(archive_path, cik) != manifest:
                raise CompanyFactsAcquisitionError(
                    "published Company Facts manifest pointer read-back mismatch"
                )
        except Exception:
            try:
                _restore_manifest_pointer(path, previous)
            except Exception as rollback_error:
                raise CompanyFactsAcquisitionError(
                    "failed to roll back Company Facts manifest pointer after publication error"
                ) from rollback_error
            raise
    return pointer


def read_latest_companyfacts_manifest(archive_root: Path, cik: int | str) -> dict[str, Any]:
    """Read the only latest pointer consumers may trust, then verify its target."""
    cik10 = _normalized_cik(cik)
    path = _safe_child(Path(archive_root), _manifest_pointer_key(cik10))
    try:
        pointer = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanyFactsAcquisitionError(
            f"missing or invalid verified Company Facts manifest pointer for CIK {cik10}"
        ) from exc
    if not isinstance(pointer, dict):
        raise CompanyFactsAcquisitionError("Company Facts manifest pointer must be an object")
    _validate_manifest_pointer(pointer)
    if pointer["cik"] != cik10:
        raise CompanyFactsAcquisitionError("Company Facts manifest pointer CIK does not match request")
    manifest = read_companyfacts_manifest(archive_root, str(pointer["manifest_key"]))
    source = manifest["source"]
    clocks = manifest["clocks"]
    expected = {
        "manifest_id": manifest["manifest_id"],
        "capture_id": source["capture_id"],
        "response_sha256": source["response_sha256"],
        "logical_sha256": source["logical_sha256"],
        "source_snapshot_at": clocks["source_snapshot_at"],
        "recorded_at": clocks["recorded_at"],
    }
    if any(pointer[key] != value for key, value in expected.items()):
        raise CompanyFactsAcquisitionError("Company Facts manifest pointer does not bind its manifest")
    return manifest


def read_verified_companyfacts(
    raw_root: Path,
    archive_root: Path,
    cik: int | str,
    *,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read current data only through a verified manifest-pointer commit."""
    limit = _positive_limit(max_bytes, field="max_bytes", ceiling=HARD_MAX_RESPONSE_BYTES)
    cik10 = _normalized_cik(cik)
    manifest = read_latest_companyfacts_manifest(archive_root, cik10)
    source = manifest["source"]
    if int(source["response_bytes"]) > limit:
        raise CompanyFactsAcquisitionError("Company Facts manifest exceeds bounded input limit")
    capture = _read_capture(raw_root, str(source["capture_receipt_key"]))
    capture_response = capture["response"]
    capture_logical = capture["logical"]
    if capture["cik"] != cik10 or capture["clocks"] != manifest["clocks"]:
        raise CompanyFactsAcquisitionError(
            "Company Facts manifest clocks or CIK differ from its capture receipt"
        )
    if any(
        capture_response[key] != source[f"response_{key}"]
        for key in ("sha256", "bytes", "object_path")
    ):
        raise CompanyFactsAcquisitionError("Company Facts manifest source differs from capture receipt")
    if any(
        capture_logical[key] != source[f"logical_{key}"]
        for key in ("sha256", "bytes")
    ) or capture_logical["fact_occurrence_count"] != source["fact_occurrence_count"] or capture_logical[
        "fact_occurrence_sha256"
    ] != source["fact_occurrence_sha256"]:
        raise CompanyFactsAcquisitionError("Company Facts manifest logical inventory differs from capture")
    response_path = _safe_child(Path(raw_root), str(source["response_object_path"]))
    response_content = _read_gzip_limited(response_path, maximum=limit)
    if len(response_content) != source["response_bytes"] or sha256(response_content).hexdigest() != source[
        "response_sha256"
    ]:
        raise CompanyFactsAcquisitionError("Company Facts response checksum or length mismatch")
    payload, logical_content, occurrence_count, occurrence_sha = _validated_payload(
        response_content, expected_cik=cik10
    )
    if sha256(logical_content).hexdigest() != source["logical_sha256"] or len(logical_content) != source[
        "logical_bytes"
    ]:
        raise CompanyFactsAcquisitionError("Company Facts logical checksum or length mismatch")
    if occurrence_count != source["fact_occurrence_count"] or occurrence_sha != source[
        "fact_occurrence_sha256"
    ]:
        raise CompanyFactsAcquisitionError("Company Facts occurrence inventory mismatch")
    return payload, manifest


def _failure(stage: str, exc: BaseException) -> dict[str, str]:
    message = " ".join(str(exc).replace("\x00", "").split())
    return {
        "stage": stage,
        "error_type": type(exc).__name__,
        "message": message[:480] if message else type(exc).__name__,
    }


def _validated_receipt_limits(value: Any) -> dict[str, int]:
    expected = {
        "max_tickers",
        "max_response_bytes",
        "max_ticker_bytes",
        "max_total_bytes",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise CompanyFactsAcquisitionError(
            "Company Facts receipt limits are invalid"
        )
    normalized = _validate_limits(
        max_tickers=value.get("max_tickers"),
        max_response_bytes=value.get("max_response_bytes"),
        max_ticker_bytes=value.get("max_ticker_bytes"),
        max_total_bytes=value.get("max_total_bytes"),
    )
    if dict(value) != normalized:
        raise CompanyFactsAcquisitionError(
            "Company Facts receipt limits are not canonical"
        )
    return normalized


def _validated_receipt_target(value: Any) -> AcquisitionTarget:
    if not isinstance(value, Mapping) or set(value) != {"ticker", "cik"}:
        raise CompanyFactsAcquisitionError(
            "Company Facts receipt target is invalid"
        )
    normalized = AcquisitionTarget(
        _normalized_ticker(str(value.get("ticker") or "")),
        _normalized_cik(value.get("cik")),
    )
    if dict(value) != normalized.to_dict():
        raise CompanyFactsAcquisitionError(
            "Company Facts receipt target is not normalized"
        )
    return normalized


def _validated_receipt_clocks(
    value: Any,
    *,
    include_captured: bool,
    label: str,
) -> dict[str, str | None]:
    expected_fields = (
        "source_snapshot_at",
        "recorded_at",
        "acquisition_started_at",
    ) + (("captured_at",) if include_captured else ())
    if not isinstance(value, Mapping) or set(value) != set(expected_fields):
        raise CompanyFactsAcquisitionError(
            f"{label} clocks have invalid schema"
        )
    clocks = dict(value)
    started = _clock_datetime(
        clocks["acquisition_started_at"],
        field=f"{label}.acquisition_started_at",
    )
    captured_value = clocks.get("captured_at") if include_captured else None
    captured = (
        _clock_datetime(captured_value, field=f"{label}.captured_at")
        if captured_value not in (None, "")
        else None
    )
    snapshot, recorded = _validate_temporal_contract(
        source_snapshot_at=clocks["source_snapshot_at"],
        recorded_at=clocks["recorded_at"],
        acquisition_started_at=started,
        captured_at=captured,
    )
    if snapshot != clocks["source_snapshot_at"] or recorded != clocks["recorded_at"]:
        raise CompanyFactsAcquisitionError(
            f"{label} clocks are not normalized"
        )
    if utc_text(started) != clocks["acquisition_started_at"]:
        raise CompanyFactsAcquisitionError(
            f"{label} acquisition clock is not normalized"
        )
    if captured is not None and utc_text(captured) != captured_value:
        raise CompanyFactsAcquisitionError(
            f"{label} capture clock is not normalized"
        )
    return clocks


def _validate_failure_records(value: Any, *, required: bool) -> None:
    if not isinstance(value, list) or (required and not value):
        raise CompanyFactsAcquisitionError(
            "Company Facts ticker receipt failures are invalid"
        )
    for record in value:
        if not isinstance(record, Mapping) or set(record) != {
            "stage",
            "error_type",
            "message",
        }:
            raise CompanyFactsAcquisitionError(
                "Company Facts ticker failure record is invalid"
            )
        for field in ("stage", "error_type", "message"):
            text = record.get(field)
            if not isinstance(text, str) or not text or "\x00" in text:
                raise CompanyFactsAcquisitionError(
                    "Company Facts ticker failure record is invalid"
                )
        if record["stage"] != "companyfacts" or not _ERROR_TYPE_RE.fullmatch(
            record["error_type"]
        ):
            raise CompanyFactsAcquisitionError(
                "Company Facts ticker failure record is invalid"
            )
        if " ".join(record["message"].split()) != record["message"]:
            raise CompanyFactsAcquisitionError(
                "Company Facts ticker failure message is not normalized"
            )
        if len(record["message"]) > 480:
            raise CompanyFactsAcquisitionError(
                "Company Facts ticker failure message exceeds bounded length"
            )


def _build_ticker_receipt(
    *,
    request_id: str,
    target: AcquisitionTarget,
    source_snapshot_at: str,
    recorded_at: str,
    acquisition_started_at: str,
    captured_at: str | None,
    limits: Mapping[str, int],
    status: str,
    capture_id: str | None,
    capture_receipt_key: str | None,
    manifest_key: str | None,
    bytes_retained: int,
    failures: list[dict[str, str]],
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema": COMPANYFACTS_TICKER_SCHEMA,
        "ticker_receipt_id": "",
        "request_id": request_id,
        "target": target.to_dict(),
        "clocks": {
            "source_snapshot_at": source_snapshot_at,
            "recorded_at": recorded_at,
            "acquisition_started_at": acquisition_started_at,
            "captured_at": captured_at,
        },
        "limits": dict(limits),
        "operator_constraints": list(OPERATOR_CONSTRAINTS),
        "status": status,
        "capture_id": capture_id,
        "capture_receipt_key": capture_receipt_key,
        "manifest_key": manifest_key,
        "bytes_retained": bytes_retained,
        "failures": list(failures),
    }
    record["ticker_receipt_id"] = _ticker_receipt_id(record)
    _validate_ticker_receipt(record)
    return record


def _validate_ticker_receipt(receipt: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "ticker_receipt_id",
        "request_id",
        "target",
        "clocks",
        "limits",
        "operator_constraints",
        "status",
        "capture_id",
        "capture_receipt_key",
        "manifest_key",
        "bytes_retained",
        "failures",
    }
    if set(receipt) != required or receipt.get("schema") != COMPANYFACTS_TICKER_SCHEMA:
        raise CompanyFactsAcquisitionError("Company Facts ticker receipt shape is invalid")
    receipt_id = str(receipt.get("ticker_receipt_id") or "")
    if not _TICKER_RECEIPT_ID_RE.fullmatch(receipt_id) or receipt_id != _ticker_receipt_id(receipt):
        raise CompanyFactsAcquisitionError("Company Facts ticker receipt identity mismatch")
    request_id = receipt.get("request_id")
    if not isinstance(request_id, str) or not _REQUEST_ID_RE.fullmatch(request_id):
        raise CompanyFactsAcquisitionError(
            "Company Facts ticker receipt request id is invalid"
        )
    target = _validated_receipt_target(receipt.get("target"))
    clocks = _validated_receipt_clocks(
        receipt.get("clocks"),
        include_captured=True,
        label="ticker_receipt",
    )
    limits = _validated_receipt_limits(receipt.get("limits"))
    if receipt.get("operator_constraints") != list(OPERATOR_CONSTRAINTS):
        raise CompanyFactsAcquisitionError("Company Facts ticker receipt operator constraints are invalid")
    if receipt.get("status") not in {"complete", "failed"}:
        raise CompanyFactsAcquisitionError("Company Facts ticker receipt status is invalid")
    if (
        isinstance(receipt.get("bytes_retained"), bool)
        or not isinstance(receipt.get("bytes_retained"), int)
        or receipt["bytes_retained"] < 0
        or receipt["bytes_retained"] > limits["max_response_bytes"]
        or receipt["bytes_retained"] > limits["max_ticker_bytes"]
    ):
        raise CompanyFactsAcquisitionError("Company Facts ticker receipt bytes are invalid")
    complete = receipt["status"] == "complete"
    _validate_failure_records(receipt.get("failures"), required=not complete)
    capture_id = receipt.get("capture_id")
    capture_key = receipt.get("capture_receipt_key")
    manifest_key = receipt.get("manifest_key")
    has_capture = capture_id is not None or capture_key is not None
    if has_capture:
        if (
            not isinstance(capture_id, str)
            or not _CAPTURE_ID_RE.fullmatch(capture_id)
            or capture_key != _capture_key(target.cik, capture_id)
        ):
            raise CompanyFactsAcquisitionError(
                "Company Facts ticker receipt capture evidence is invalid"
            )
    if manifest_key is not None:
        if not has_capture or not isinstance(manifest_key, str):
            raise CompanyFactsAcquisitionError(
                "Company Facts ticker receipt manifest evidence is invalid"
            )
        relative = _safe_relative(manifest_key)
        if (
            relative.parent != COMPANYFACTS_MANIFEST_ROOT / target.cik
            or relative.suffix != ".json"
            or not _MANIFEST_ID_RE.fullmatch(relative.stem)
        ):
            raise CompanyFactsAcquisitionError(
                "Company Facts ticker receipt manifest evidence is invalid"
            )
    if has_capture and clocks.get("captured_at") in (None, ""):
        raise CompanyFactsAcquisitionError(
            "Company Facts ticker receipt capture clock is missing"
        )
    if has_capture and receipt["bytes_retained"] < 1:
        raise CompanyFactsAcquisitionError(
            "Company Facts ticker receipt capture has no retained bytes"
        )
    if complete:
        if (
            not has_capture
            or manifest_key is None
            or receipt["bytes_retained"] < 1
            or receipt["failures"]
        ):
            raise CompanyFactsAcquisitionError("complete Company Facts ticker receipt is incomplete")
    elif manifest_key is not None and not has_capture:
        raise CompanyFactsAcquisitionError("failed Company Facts ticker receipt is invalid")


def _persist_ticker_receipt(archive_root: Path, receipt: Mapping[str, Any]) -> str:
    _validate_ticker_receipt(receipt)
    key = _ticker_receipt_key(receipt)
    _write_immutable_json(
        _safe_child(Path(archive_root), key), dict(receipt), label="Company Facts ticker receipt"
    )
    return key


def _request_id(
    *,
    targets: tuple[AcquisitionTarget, ...],
    source_snapshot_at: str,
    acquisition_started_at: str,
    limits: Mapping[str, int],
) -> str:
    body = {
        "schema": COMPANYFACTS_RUN_SCHEMA,
        "targets": [target.to_dict() for target in targets],
        "source_snapshot_at": source_snapshot_at,
        "acquisition_started_at": acquisition_started_at,
        "limits": dict(limits),
    }
    return "ffseccfq_" + sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _persist_run(archive_root: Path, run: Mapping[str, Any]) -> str:
    _validate_run(run)
    key = _run_key(run)
    _write_immutable_json(_safe_child(Path(archive_root), key), dict(run), label="Company Facts run receipt")
    return key


def _validate_run(run: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "run_id",
        "request_id",
        "clocks",
        "targets",
        "limits",
        "operator_constraints",
        "bytes_retained",
        "status",
        "ticker_receipts",
        "ticker_receipt_keys",
    }
    if set(run) != required or run.get("schema") != COMPANYFACTS_RUN_SCHEMA:
        raise CompanyFactsAcquisitionError("Company Facts run shape is invalid")
    limits = _validated_receipt_limits(run.get("limits"))
    clocks = _validated_receipt_clocks(
        run.get("clocks"),
        include_captured=False,
        label="run",
    )
    raw_targets = run.get("targets")
    if not isinstance(raw_targets, list):
        raise CompanyFactsAcquisitionError("Company Facts run targets are invalid")
    parsed_targets = tuple(
        _validated_receipt_target(value) for value in raw_targets
    )
    try:
        normalized_targets = normalize_targets(
            parsed_targets,
            max_tickers=limits["max_tickers"],
        )
    except AcquisitionError as exc:
        raise CompanyFactsAcquisitionError(str(exc)) from exc
    if parsed_targets != normalized_targets:
        raise CompanyFactsAcquisitionError(
            "Company Facts run targets are not canonical/unique"
        )
    request_id = run.get("request_id")
    expected_request_id = _request_id(
        targets=normalized_targets,
        source_snapshot_at=clocks["source_snapshot_at"],
        acquisition_started_at=clocks["acquisition_started_at"],
        limits=limits,
    )
    if (
        not isinstance(request_id, str)
        or not _REQUEST_ID_RE.fullmatch(request_id)
        or request_id != expected_request_id
    ):
        raise CompanyFactsAcquisitionError("Company Facts run request id is invalid")
    run_id = str(run.get("run_id") or "")
    if not _RUN_ID_RE.fullmatch(run_id) or run_id != _run_id(run):
        raise CompanyFactsAcquisitionError("Company Facts run identity mismatch")
    if run.get("operator_constraints") != list(OPERATOR_CONSTRAINTS):
        raise CompanyFactsAcquisitionError("Company Facts run operator constraints are invalid")
    if run.get("status") not in {"complete", "partial"}:
        raise CompanyFactsAcquisitionError("Company Facts run status is invalid")
    if not isinstance(run.get("ticker_receipts"), list) or not isinstance(run.get("ticker_receipt_keys"), list):
        raise CompanyFactsAcquisitionError("Company Facts run ticker receipts are invalid")
    if (
        len(run["ticker_receipts"]) != len(run["ticker_receipt_keys"])
        or len(run["ticker_receipts"]) != len(normalized_targets)
    ):
        raise CompanyFactsAcquisitionError("Company Facts run receipt/key count mismatch")
    if (
        isinstance(run.get("bytes_retained"), bool)
        or not isinstance(run.get("bytes_retained"), int)
        or run["bytes_retained"] < 0
        or run["bytes_retained"] > limits["max_total_bytes"]
    ):
        raise CompanyFactsAcquisitionError("Company Facts run retained bytes are invalid")
    for target, receipt, key in zip(
        normalized_targets,
        run["ticker_receipts"],
        run["ticker_receipt_keys"],
    ):
        if not isinstance(receipt, Mapping) or not isinstance(key, str):
            raise CompanyFactsAcquisitionError("Company Facts run ticker receipt item is invalid")
        _validate_ticker_receipt(receipt)
        if _ticker_receipt_key(receipt) != key:
            raise CompanyFactsAcquisitionError("Company Facts run ticker receipt key mismatch")
        if receipt["request_id"] != request_id:
            raise CompanyFactsAcquisitionError(
                "Company Facts child receipt request id differs from run"
            )
        if receipt["target"] != target.to_dict():
            raise CompanyFactsAcquisitionError(
                "Company Facts child receipt target/order differs from run"
            )
        if receipt["limits"] != limits:
            raise CompanyFactsAcquisitionError(
                "Company Facts child receipt limits differ from run"
            )
        for field in ("source_snapshot_at", "acquisition_started_at"):
            if receipt["clocks"][field] != clocks[field]:
                raise CompanyFactsAcquisitionError(
                    "Company Facts child receipt clocks differ from run"
                )
        child_recorded = _clock_datetime(
            receipt["clocks"]["recorded_at"],
            field="ticker_receipt.recorded_at",
        )
        run_recorded = _clock_datetime(
            clocks["recorded_at"],
            field="run.recorded_at",
        )
        if child_recorded > run_recorded:
            raise CompanyFactsAcquisitionError(
                "Company Facts child receipt recorded_at postdates run retention"
            )
    if run["bytes_retained"] != sum(
        receipt["bytes_retained"] for receipt in run["ticker_receipts"]
    ):
        raise CompanyFactsAcquisitionError(
            "Company Facts run retained bytes differ from child receipts"
        )
    expected_status = (
        "complete"
        if all(
            receipt["status"] == "complete"
            for receipt in run["ticker_receipts"]
        )
        else "partial"
    )
    if run["status"] != expected_status:
        raise CompanyFactsAcquisitionError(
            "Company Facts run status differs from child receipts"
        )


def acquire_companyfacts(
    *,
    targets: Iterable[str | AcquisitionTarget | tuple[str, int | str]],
    raw_root: Path,
    archive_root: Path,
    user_agent: str,
    source_snapshot_at: str | datetime,
    recorded_at: str | datetime,
    max_tickers: int = DEFAULT_MAX_TICKERS,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    max_ticker_bytes: int = DEFAULT_MAX_TICKER_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    min_interval_seconds: float = 0.12,
    timeout_seconds: float = 30.0,
    max_attempts: int = 4,
    fetcher: Fetcher | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    utc_now: UtcNow = _utc_now,
) -> dict[str, Any]:
    """Acquire current, byte-faithful Company Facts snapshots for explicit CIKs.

    ``source_snapshot_at`` names a contemporary retained snapshot, not a
    historical cutoff.  Company Facts lacks the acceptance-time history needed
    to safely filter a past cutoff, so every returned manifest explicitly says
    it is not point-in-time eligible.
    """
    limits = _validate_limits(
        max_tickers=max_tickers,
        max_response_bytes=max_response_bytes,
        max_ticker_bytes=max_ticker_bytes,
        max_total_bytes=max_total_bytes,
    )
    try:
        normalized_targets = normalize_targets(targets, max_tickers=limits["max_tickers"])
    except AcquisitionError as exc:
        raise CompanyFactsAcquisitionError(str(exc)) from exc
    acquisition_started_dt, acquisition_started = _observed_clock(
        utc_now, field="acquisition_started_at"
    )
    snapshot, caller_recorded_lower_bound = _validate_acquisition_inputs(
        source_snapshot_at=source_snapshot_at,
        recorded_at=recorded_at,
        acquisition_started_at=acquisition_started_dt,
    )
    raw_path = _checked_root(Path(raw_root), field="raw_root")
    archive_path = _checked_root(Path(archive_root), field="archive_root")
    client = SecCompanyFactsCollector(
        user_agent=user_agent,
        min_interval_seconds=min_interval_seconds,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        fetcher=fetcher,
        sleeper=sleeper,
        monotonic=monotonic,
    )
    request_id = _request_id(
        targets=normalized_targets,
        source_snapshot_at=snapshot,
        acquisition_started_at=acquisition_started,
        limits=limits,
    )
    total_bytes = 0
    ticker_receipts: list[dict[str, Any]] = []
    ticker_receipt_keys: list[str] = []
    ticker_outcomes: list[dict[str, Any]] = []
    for target in normalized_targets:
        failures: list[dict[str, str]] = []
        capture_id: str | None = None
        capture_receipt_key: str | None = None
        manifest_key: str | None = None
        bytes_retained = 0
        captured_at: str | None = None
        retention_recorded_at: str | None = None
        status = "failed"
        try:
            available = min(
                limits["max_response_bytes"],
                limits["max_ticker_bytes"],
                limits["max_total_bytes"] - total_bytes,
            )
            if available < 1:
                raise CompanyFactsAcquisitionError(
                    "run byte budget exhausted before Company Facts fetch"
                )
            response_content, response_meta = client.fetch(
                target.cik, max_response_bytes=available
            )
            if len(response_content) > available:
                raise CompanyFactsResponseTooLarge(
                    "Company Facts response exceeded caller byte budget before persistence"
                )
            payload, logical_content, occurrence_count, occurrence_sha = _validated_payload(
                response_content, expected_cik=target.cik
            )
            response_sha, response_bytes, object_path, object_repaired = _persist_response_object(
                raw_path, cik=target.cik, response_content=response_content
            )
            # Charge the run budget at the first durable-retention boundary.
            # Later manifest/pointer failures must not make these bytes vanish
            # from accounting or allow another ticker to reuse their budget.
            bytes_retained = response_bytes
            total_bytes += response_bytes
            captured_dt, captured_at = _observed_clock(utc_now, field="captured_at")
            _, retention_recorded_at = _validate_temporal_contract(
                source_snapshot_at=snapshot,
                # The caller's sample may make replay more conservative, but
                # can never pull this public source clock before persistence.
                recorded_at=max(captured_dt, caller_recorded_lower_bound),
                acquisition_started_at=acquisition_started_dt,
                captured_at=captured_dt,
            )
            capture = _build_capture(
                cik=target.cik,
                response_sha256=response_sha,
                response_bytes=response_bytes,
                response_object_path=object_path,
                logical_content=logical_content,
                occurrence_count=occurrence_count,
                occurrence_sha256=occurrence_sha,
                acquisition_started_at=acquisition_started,
                captured_at=captured_at,
                recorded_at=retention_recorded_at,
                source_snapshot_at=snapshot,
                http_etag=response_meta["http_etag"],
                http_last_modified=response_meta["http_last_modified"],
                object_repaired=object_repaired,
            )
            capture_receipt_key = _persist_capture(raw_path, capture)
            capture_id = str(capture["capture_id"])
            manifest = _build_manifest(target=target, payload=payload, capture=capture)
            manifest_key = persist_companyfacts_manifest(archive_path, manifest)
            if read_companyfacts_manifest(archive_path, manifest_key) != manifest:
                raise CompanyFactsAcquisitionError(
                    "persisted Company Facts manifest differs on read-back"
                )
            # This is the only publication operation.  It follows capture and
            # manifest verification, so a failed issuer cannot expose its
            # newly acquired raw object through a latest pointer.
            publish_verified_manifest_pointer(archive_path, manifest_key)
            status = "complete"
        except _RetainedResponseVerificationError as exc:
            # The object helper only raises this after an admitted response
            # crossed its durable write boundary.  Charge it before the
            # ordinary per-ticker failure path so a later target cannot reuse
            # the run budget merely because verification/capture failed.
            bytes_retained = exc.response_bytes
            total_bytes += exc.response_bytes
            failures.append(_failure("companyfacts", exc))
        except Exception as exc:  # per-issuer continuation is intentional
            failures.append(_failure("companyfacts", exc))
        ticker_outcomes.append(
            {
                "target": target,
                "captured_at": captured_at,
                "recorded_at": retention_recorded_at,
                "status": status,
                "capture_id": capture_id,
                "capture_receipt_key": capture_receipt_key,
                "manifest_key": manifest_key,
                "bytes_retained": bytes_retained,
                "failures": failures,
            }
        )

    run_finalized_dt, _ = _observed_clock(utc_now, field="run_finalized_at")
    retained_clock_values = [
        _clock_datetime(item["recorded_at"], field="ticker_receipt.recorded_at")
        for item in ticker_outcomes
        if item["recorded_at"] is not None
    ]
    run_recorded_dt = max(
        acquisition_started_dt,
        caller_recorded_lower_bound,
        run_finalized_dt,
        *retained_clock_values,
    )
    recorded = utc_text(run_recorded_dt) or ""
    for outcome in ticker_outcomes:
        ticker_receipt = _build_ticker_receipt(
            request_id=request_id,
            target=outcome["target"],
            source_snapshot_at=snapshot,
            recorded_at=outcome["recorded_at"] or recorded,
            acquisition_started_at=acquisition_started,
            captured_at=outcome["captured_at"],
            limits=limits,
            status=outcome["status"],
            capture_id=outcome["capture_id"],
            capture_receipt_key=outcome["capture_receipt_key"],
            manifest_key=outcome["manifest_key"],
            bytes_retained=outcome["bytes_retained"],
            failures=outcome["failures"],
        )
        ticker_receipt_keys.append(_persist_ticker_receipt(archive_path, ticker_receipt))
        ticker_receipts.append(ticker_receipt)

    run: dict[str, Any] = {
        "schema": COMPANYFACTS_RUN_SCHEMA,
        "run_id": "",
        "request_id": request_id,
        "clocks": {
            "source_snapshot_at": snapshot,
            "recorded_at": recorded,
            "acquisition_started_at": acquisition_started,
        },
        "targets": [target.to_dict() for target in normalized_targets],
        "limits": dict(limits),
        "operator_constraints": list(OPERATOR_CONSTRAINTS),
        "bytes_retained": total_bytes,
        "status": "complete" if all(item["status"] == "complete" for item in ticker_receipts) else "partial",
        "ticker_receipts": ticker_receipts,
        "ticker_receipt_keys": ticker_receipt_keys,
    }
    run["run_id"] = _run_id(run)
    run_key = _persist_run(archive_path, run)
    # The persisted receipt has a closed, content-addressed schema. Return an
    # explicit envelope so its storage location is never mistaken for a field
    # in the immutable receipt identity.
    return {"run": run, "run_key": run_key}


acquire_bounded_companyfacts = acquire_companyfacts


__all__ = [
    "COMPANYFACTS_ARCHIVE_NAMESPACE",
    "COMPANYFACTS_CAPTURE_SCHEMA",
    "COMPANYFACTS_ENDPOINT",
    "COMPANYFACTS_MANIFEST_ROOT",
    "COMPANYFACTS_MANIFEST_SCHEMA",
    "COMPANYFACTS_POINTER_SCHEMA",
    "COMPANYFACTS_RAW_NAMESPACE",
    "COMPANYFACTS_RUN_ROOT",
    "COMPANYFACTS_RUN_SCHEMA",
    "COMPANYFACTS_TICKER_RECEIPT_ROOT",
    "COMPANYFACTS_TICKER_SCHEMA",
    "CompanyFactsAcquisitionError",
    "CompanyFactsCapture",
    "CompanyFactsResponseTooLarge",
    "DEFAULT_MAX_RESPONSE_BYTES",
    "DEFAULT_MAX_TICKER_BYTES",
    "DEFAULT_MAX_TICKERS",
    "DEFAULT_MAX_TOTAL_BYTES",
    "HARD_MAX_RESPONSE_BYTES",
    "OPERATOR_CONSTRAINTS",
    "SNAPSHOT_CLOCK_TOLERANCE_SECONDS",
    "SecCompanyFactsCollector",
    "acquire_bounded_companyfacts",
    "acquire_companyfacts",
    "companyfacts_url",
    "iter_companyfacts_occurrences",
    "manifest_id_for",
    "persist_companyfacts_manifest",
    "publish_verified_manifest_pointer",
    "read_companyfacts_manifest",
    "read_latest_companyfacts_manifest",
    "read_verified_companyfacts",
    "validate_companyfacts_manifest",
]
