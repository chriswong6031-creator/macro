"""Incremental broad SEC source plane for Filing Forensics (FF-1).

Discovers relevant 10-K/10-Q (and existing 20-F/40-F) changes from the official
EDGAR full-index master ZIP, then fetches Submissions only for affected issuers
in ``data/edgar/fundamentals.parquet``. Admits exact SEC bytes into a private
content-addressed store and fetches Company Facts only when that issuer's
relevant periodic filing state actually changes.

This module is source truth only.  It does not rebuild workbench state, run
detectors, or publish findings.  A rerender cannot make the source current:
object identity is the SHA-256 of exact SEC bytes, and poll clocks never enter
that identity.

Clocks stay separate:

* ``poll_started_at`` / ``poll_completed_at`` — operational observation
* ``sec_accepted_at`` — SEC ``acceptanceDateTime``
* ``filed_on`` — SEC filing date
* ``submissions_retrieved_at`` / ``companyfacts_retrieved_at`` — after exact bytes
* ``recorded_at`` — when a verified receipt crossed durable storage

Company Facts is a current observed snapshot.  It is never labelled as-of the
poll clock.  Callers inject every clock; this kernel does not sample wall time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import gzip
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlparse

from collectors.edgar_forensics import (
    SecResponseTooLarge,
    _canonical_cik,
    endpoint_url,
    full_master_index_url,
)
from collectors.fundamental_forensics_companyfacts import (
    CompanyFactsAcquisitionError,
    CompanyFactsResponseTooLarge,
)
from engine.fundamental_forensics.models import canonical_json
from engine.research_vault.r2_store import (
    LocalStore,
    VersionedBytes,
)

PREFIX = "fundamental_forensics/broad-sec/v1"
STORE_PREFIX = PREFIX
UNIVERSE_ID = "edgar.fundamentals"
UNIVERSE_RELATIVE_PATH = "data/edgar/fundamentals.parquet"
RUN_SCHEMA = "fundamental_forensics.broad_sec.run.v1"
MANIFEST_SCHEMA = "fundamental_forensics.broad_sec.issuer_manifest.v1"
HEAD_SCHEMA = "fundamental_forensics.broad_sec.head.v1"
OBSERVATION_SCHEMA = "fundamental_forensics.broad_sec.issuer_observations.v1"
CONTINUATION_SCHEMA = "fundamental_forensics.broad_sec.recovery_continuation.v1"
POINTER_MAX_BYTES = 16 * 1024
# Bind fence for the canonical parquet, not a crawl target. Live
# data/edgar/fundamentals.parquet measured 2837 unique issuers on 2026-08-18
# (run 32097495749, universe_invalid at 2500). 4000 admits that census with
# growth room and still fail-closes an accidental full-EDGAR dump.
MAX_UNIVERSE_ISSUERS = 4000
MAX_SUBMISSIONS_BYTES = 8 * 1024 * 1024
MAX_COMPANYFACTS_BYTES = 64 * 1024 * 1024
MAX_AFFECTED_ISSUERS = 64
MAX_COMPANYFACTS_BYTES_PER_RUN = 32 * 1024 * 1024
# Live 2026 Q3 master.zip canary 2026-08-18: 2132920 compressed / 15184383
# uncompressed. These bounds keep substantial growth room and fail closed
# rather than silently rising.
MAX_MASTER_INDEX_ZIP_BYTES = 16 * 1024 * 1024
MAX_MASTER_INDEX_MEMBER_BYTES = 64 * 1024 * 1024
MASTER_INDEX_MEMBER_NAME = "master.idx"
MASTER_INDEX_HEADER = "CIK|Company Name|Form Type|Date Filed|Filename"
INDEX_SOURCE_KIND = "sec_edgar_full_master_index"
INDEX_SNAPSHOT_SCHEMA = "fundamental_forensics.broad_sec.index_snapshot.v1"
PREVIOUS_QUARTER_RECONCILIATION_CADENCE = "weekly"
RELEVANT_FORMS = frozenset(
    {
        "10-K",
        "10-K/A",
        "10-Q",
        "10-Q/A",
        "20-F",
        "20-F/A",
        "40-F",
        "40-F/A",
    }
)
REASON_CODES = frozenset(
    {
        "universe_invalid",
        "sec_429_exhausted",
        "sec_5xx_exhausted",
        "sec_timeout_exhausted",
        "response_too_large",
        "invalid_sec_json",
        "source_binding_failure",
        "store_write_failure",
        "store_readback_failure",
        "issuer_manifest_invalid",
        "queue_overflow",
        "historical_submissions_required",
        "edgar_index_unavailable",
        "edgar_index_too_large",
        "edgar_index_invalid",
        "edgar_index_member_missing",
        "edgar_index_cik_mismatch",
        "edgar_index_gap",
        "edgar_index_correction_requires_reconciliation",
        "edgar_index_event_not_causally_admitted",
        "recovery_plan_required",
    }
)
_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_INDEX_FILENAME_RE = re.compile(
    r"^edgar/data/([0-9]+)/([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt$"
)
_ISO_Z_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"
)
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

NowFn = Callable[[], str]


class BroadSecError(RuntimeError):
    def __init__(self, reason_code: str, detail: str = "") -> None:
        if reason_code not in REASON_CODES:
            raise ValueError(f"unknown broad-SEC reason_code: {reason_code}")
        super().__init__(detail or reason_code)
        self.reason_code = reason_code
        self.detail = detail or reason_code


class BroadSecStore(Protocol):
    def get_bytes_strict(self, key: str) -> bytes | None: ...

    def get_bytes_strict_bounded(self, key: str, maximum_bytes: int) -> bytes | None: ...

    def get_bytes_strict_bounded_versioned(
        self, key: str, maximum_bytes: int
    ) -> VersionedBytes: ...

    def put_bytes_strict_conditional(
        self,
        key: str,
        data: bytes,
        *,
        expected_version: str | None,
        content_type: str = "application/octet-stream",
    ) -> bool: ...

    def list_prefix(self, prefix: str) -> list[str]: ...


FetchBytes = Callable[[str], tuple[bytes, Mapping[str, str | None]]]
FetchIndex = Callable[[int, int], tuple[bytes, Mapping[str, str | None]]]
ProgressFn = Callable[[str, Mapping[str, Any]], None]


@dataclass(frozen=True)
class Issuer:
    ticker: str
    cik: str


@dataclass(frozen=True)
class UniverseBinding:
    path: str
    universe_id: str
    content_sha256: str
    issuer_count: int
    unique_ticker_count: int
    unique_cik_count: int
    canonical: bool
    issuers: tuple[Issuer, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "universe_id": self.universe_id,
            "content_sha256": self.content_sha256,
            "issuer_count": self.issuer_count,
            "unique_ticker_count": self.unique_ticker_count,
            "unique_cik_count": self.unique_cik_count,
            "canonical": self.canonical,
        }


@dataclass
class PollClocks:
    poll_started_at: str
    selection_cutoff_at: str
    recovery_from: str | None = None
    recorded_at: str | None = None
    poll_completed_at: str | None = None


@dataclass
class IssuerFailure:
    ticker: str
    cik: str
    reason_code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "ticker": self.ticker,
            "cik": self.cik,
            "reason_code": self.reason_code,
            "detail": self.detail,
        }


@dataclass
class PollResult:
    receipt: dict[str, Any]
    exit_code: int


def object_key(digest: str) -> str:
    return f"{PREFIX}/objects/sha256/{digest[:2]}/{digest}.json.gz"


def issuer_manifest_key(cik: str, manifest_id: str) -> str:
    return f"{PREFIX}/issuers/{cik}/manifests/{manifest_id}.json"


def issuer_latest_key(cik: str) -> str:
    return f"{PREFIX}/issuers/{cik}/latest.json"


def run_key(run_id: str) -> str:
    return f"{PREFIX}/runs/{run_id}/receipt.json"


def issuer_observations_key(run_id: str) -> str:
    return f"{PREFIX}/runs/{run_id}/issuer-observations.json.gz"


def latest_observation_key() -> str:
    return f"{PREFIX}/latest-observation.json"


def latest_complete_key() -> str:
    return f"{PREFIX}/latest-complete.json"


def recovery_continuation_pointer_key() -> str:
    return f"{PREFIX}/recovery/continuation.json"


def recovery_continuation_object_key(digest: str) -> str:
    return f"{PREFIX}/recovery/objects/{digest[:2]}/{digest}.json.gz"


def index_object_key(digest: str) -> str:
    return f"{PREFIX}/indexes/objects/sha256/{digest[:2]}/{digest}.idx.gz"


def index_snapshot_key(quarter_id: str, snapshot_id: str) -> str:
    return f"{PREFIX}/indexes/quarters/{quarter_id}/snapshots/{snapshot_id}.json"


def index_latest_key(quarter_id: str) -> str:
    return f"{PREFIX}/indexes/quarters/{quarter_id}/latest.json"


def calendar_quarter(iso_z: str) -> tuple[int, int]:
    stamp = _require_iso_z(iso_z, field="quarter_clock")
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)
    quarter = (parsed.month - 1) // 3 + 1
    return parsed.year, quarter


def quarter_id(year: int, quarter: int) -> str:
    return f"{year}-Q{quarter}"


def previous_quarter(year: int, quarter: int) -> tuple[int, int]:
    if quarter == 1:
        return year - 1, 4
    return year, quarter - 1


def previous_quarter_reconciliation_due(
    *,
    poll_started_at: str,
    last_reconciled_at: str | None = None,
) -> bool:
    """SPEC_ONLY / NOT_BUILT: weekly previous-quarter reconciliation.

    Current-quarter rebuilt-index corrections are implemented in this discovery
    plane. Previous-quarter weekly crawling is not built and is required before
    FF-1 can be called globally correction-safe. Cadence remains
    ``PREVIOUS_QUARTER_RECONCILIATION_CADENCE`` ('weekly'). This function
    returns False until that engine is commissioned (FF-1R / final closure).
    """
    del poll_started_at, last_reconciled_at
    return False


def _gzip_bytes(content: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(content)
    return buffer.getvalue()


def _ungzip_bytes(payload: bytes) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as handle:
        return handle.read()


def _require_iso_z(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not _ISO_Z_RE.fullmatch(value):
        raise BroadSecError("source_binding_failure", f"{field} must be an ISO-8601 UTC Z timestamp")
    return value


def _parse_acceptance(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    elif text.endswith("Z"):
        pass
    else:
        return None
    if "T" not in text:
        return None
    if "." in text:
        head, _frac = text[:-1].split(".", 1)
        text = head + "Z"
    if not _ISO_Z_RE.fullmatch(text):
        return None
    return text


def _max_iso(values: list[str | None]) -> str | None:
    present = [item for item in values if item]
    if not present:
        return None
    return max(present)


def load_universe(path: Path, *, repo_root: Path | None = None) -> UniverseBinding:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - CI install line carries pandas
        raise BroadSecError("universe_invalid", "pandas is required to bind the EDGAR universe") from exc

    if not path.is_file():
        raise BroadSecError("universe_invalid", f"universe parquet missing: {path}")
    raw = path.read_bytes()
    if not raw:
        raise BroadSecError("universe_invalid", "universe parquet is empty")
    try:
        frame = pd.read_parquet(path, columns=["cik"])
    except Exception as exc:
        raise BroadSecError("universe_invalid", f"universe parquet unreadable: {exc}") from exc
    if frame.empty:
        raise BroadSecError("universe_invalid", "universe is empty")

    issuers: list[Issuer] = []
    ticker_to_cik: dict[str, str] = {}
    cik_to_ticker: dict[str, str] = {}
    for ticker_raw, row in frame.iterrows():
        ticker = str(ticker_raw).strip().upper()
        if not ticker or ticker == "NAN":
            raise BroadSecError("universe_invalid", "universe row is missing a ticker")
        cik_value = row.get("cik") if hasattr(row, "get") else row["cik"]
        try:
            if cik_value is None or (hasattr(pd, "isna") and pd.isna(cik_value)):
                raise ValueError("missing")
            cik = _canonical_cik(cik_value)
        except (TypeError, ValueError) as exc:
            raise BroadSecError(
                "universe_invalid", f"malformed CIK for {ticker}"
            ) from exc
        prior_cik = ticker_to_cik.get(ticker)
        if prior_cik is not None and prior_cik != cik:
            raise BroadSecError(
                "universe_invalid",
                f"duplicate ticker {ticker} maps to {prior_cik} and {cik}",
            )
        prior_ticker = cik_to_ticker.get(cik)
        if prior_ticker is not None and prior_ticker != ticker:
            raise BroadSecError(
                "universe_invalid",
                f"duplicate CIK {cik} maps to {prior_ticker} and {ticker}",
            )
        if ticker in ticker_to_cik:
            continue
        ticker_to_cik[ticker] = cik
        cik_to_ticker[cik] = ticker
        issuers.append(Issuer(ticker=ticker, cik=cik))

    if not issuers:
        raise BroadSecError("universe_invalid", "universe is empty")
    if len(issuers) > MAX_UNIVERSE_ISSUERS:
        raise BroadSecError(
            "universe_invalid",
            f"universe has {len(issuers)} issuers; hard max is {MAX_UNIVERSE_ISSUERS}",
        )
    canonical = False
    recorded_path = str(path)
    universe_id = f"{UNIVERSE_ID}.noncanonical"
    if repo_root is not None:
        canonical_path = (repo_root / UNIVERSE_RELATIVE_PATH).resolve()
        if path.resolve() == canonical_path:
            canonical = True
            recorded_path = UNIVERSE_RELATIVE_PATH
            universe_id = UNIVERSE_ID
    return UniverseBinding(
        path=recorded_path,
        universe_id=universe_id,
        content_sha256=sha256(raw).hexdigest(),
        issuer_count=len(issuers),
        unique_ticker_count=len(ticker_to_cik),
        unique_cik_count=len(cik_to_ticker),
        canonical=canonical,
        issuers=tuple(issuers),
    )


def _bind_sec_url(url: str | None, *, cik: str, endpoint: str) -> str:
    expected = endpoint_url(cik, endpoint)
    if not isinstance(url, str) or url != expected:
        raise BroadSecError(
            "source_binding_failure",
            f"{endpoint} URL {url!r} does not bind CIK {cik}",
        )
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "data.sec.gov":
        raise BroadSecError("source_binding_failure", f"refusing non-SEC URL {url!r}")
    return url


def classify_fetch_error(exc: BaseException) -> str:
    if isinstance(exc, BroadSecError):
        return exc.reason_code
    if isinstance(exc, (SecResponseTooLarge, CompanyFactsResponseTooLarge)):
        return "response_too_large"
    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, json.JSONDecodeError) or "json" in lowered and "expecting" in lowered:
        return "invalid_sec_json"
    if "does not match" in lowered or "redirect" in lowered:
        return "source_binding_failure"
    if "429" in text:
        return "sec_429_exhausted"
    if any(code in text for code in ("500", "502", "503", "504")):
        return "sec_5xx_exhausted"
    if "timed out" in lowered or "timeout" in lowered:
        return "sec_timeout_exhausted"
    if isinstance(exc, CompanyFactsAcquisitionError):
        return "sec_5xx_exhausted"
    return "source_binding_failure"


def parse_relevant_filings(
    payload: Mapping[str, Any],
    *,
    cik: str,
    ticker: str,
    selection_cutoff_at: str,
    recovery_from: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Return (baseline relevant filings, withheld/unevaluable, historical_required).

    Recovery does not drop pre-vintage rows from the baseline.  The recovery
    delta is computed by the caller as admitted rows with
    ``acceptance_datetime >= recovery_from``.
    """
    filings = payload.get("filings")
    if not isinstance(filings, Mapping):
        raise BroadSecError("invalid_sec_json", f"{ticker} Submissions.filings is not an object")
    recent = filings.get("recent")
    if not isinstance(recent, Mapping):
        raise BroadSecError("invalid_sec_json", f"{ticker} filings.recent is not an object")
    accessions = recent.get("accessionNumber")
    if not isinstance(accessions, list):
        raise BroadSecError("invalid_sec_json", f"{ticker} accessionNumber is not an array")
    n = len(accessions)

    def column(name: str) -> list[Any]:
        value = recent.get(name)
        if value is None:
            return [None] * n
        if not isinstance(value, list) or len(value) != n:
            raise BroadSecError(
                "invalid_sec_json",
                f"{ticker} filings.recent.{name} length does not match accessionNumber",
            )
        return value

    forms = column("form")
    filing_dates = column("filingDate")
    report_dates = column("reportDate")
    acceptances = column("acceptanceDateTime")
    primaries = column("primaryDocument")
    xbrl = column("isXBRL")
    inline = column("isInlineXBRL")

    admitted: list[dict[str, Any]] = []
    withheld: list[dict[str, Any]] = []
    accept_times: list[str] = []
    for index, accession_raw in enumerate(accessions):
        form = forms[index]
        if form not in RELEVANT_FORMS:
            continue
        filing_date = filing_dates[index] if isinstance(filing_dates[index], str) else None
        if filing_date and not _DATE_RE.fullmatch(filing_date):
            filing_date = None
        report_date = report_dates[index] if isinstance(report_dates[index], str) else None
        if report_date and not _DATE_RE.fullmatch(report_date):
            report_date = None
        row = {
            "cik": cik,
            "ticker": ticker,
            "accession_number": accession_raw if isinstance(accession_raw, str) else None,
            "form": form,
            "filing_date": filing_date,
            "report_date": report_date,
            "acceptance_datetime": None,
            "primary_document": primaries[index] if isinstance(primaries[index], str) else None,
            "is_xbrl": bool(xbrl[index]) if isinstance(xbrl[index], (int, bool)) else None,
            "is_inline_xbrl": bool(inline[index]) if isinstance(inline[index], (int, bool)) else None,
        }
        if not isinstance(accession_raw, str) or not _ACCESSION_RE.fullmatch(accession_raw):
            row["withheld_reason"] = "invalid_sec_json"
            row["withheld_cause"] = "malformed_accession"
            withheld.append(row)
            continue
        accepted = _parse_acceptance(acceptances[index])
        row["acceptance_datetime"] = accepted
        if not accepted:
            row["withheld_reason"] = "source_binding_failure"
            row["withheld_cause"] = "unevaluable_acceptance"
            withheld.append(row)
            continue
        accept_times.append(accepted)
        if accepted > selection_cutoff_at:
            row["withheld_reason"] = "source_binding_failure"
            row["withheld_cause"] = "after_selection_cutoff"
            withheld.append(row)
            continue
        admitted.append(row)

    files = filings.get("files")
    historical_required = False
    if recovery_from and isinstance(files, list) and files:
        oldest = min(accept_times) if accept_times else None
        if oldest is None or oldest > recovery_from:
            historical_required = True
    return admitted, withheld, historical_required


def issuer_source_identity(manifest: Mapping[str, Any]) -> str:
    body = {
        "cik": manifest["cik"],
        "ticker": manifest["ticker"],
        "submissions_sha256": manifest["submissions_sha256"],
        "companyfacts_sha256": manifest.get("companyfacts_sha256"),
        "relevant_accessions": [
            item["accession_number"] for item in manifest.get("relevant_filings", [])
        ],
        "cumulative_relevant_accessions": list(
            manifest.get("cumulative_relevant_accessions") or []
        ),
        "previous_manifest_id": manifest.get("previous_manifest_id"),
    }
    return sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _read_json(store: BroadSecStore, key: str, *, maximum_bytes: int) -> dict[str, Any] | None:
    raw = store.get_bytes_strict_bounded(key, maximum_bytes)
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BroadSecError("issuer_manifest_invalid", f"{key} is not JSON") from exc
    if not isinstance(payload, dict):
        raise BroadSecError("issuer_manifest_invalid", f"{key} is not an object")
    return payload


def _put_immutable(store: BroadSecStore, key: str, data: bytes, *, content_type: str = "application/json") -> None:
    existing = store.get_bytes_strict(key)
    if existing == data:
        return
    if existing is not None:
        raise BroadSecError("store_write_failure", f"immutable key already holds different bytes: {key}")
    try:
        written = store.put_bytes_strict_conditional(
            key, data, expected_version=None, content_type=content_type
        )
    except Exception as exc:
        raise BroadSecError("store_write_failure", str(exc)) from exc
    if not written:
        raced = store.get_bytes_strict(key)
        if raced == data:
            return
        raise BroadSecError("store_write_failure", f"conditional create rejected for {key}")
    readback = store.get_bytes_strict(key)
    if readback != data:
        raise BroadSecError("store_readback_failure", f"readback mismatch for {key}")


def _put_pointer(store: BroadSecStore, key: str, payload: Mapping[str, Any]) -> None:
    data = canonical_json(payload).encode("utf-8")
    if len(data) > POINTER_MAX_BYTES:
        raise BroadSecError("store_write_failure", f"pointer {key} exceeds {POINTER_MAX_BYTES} bytes")
    try:
        current: VersionedBytes = store.get_bytes_strict_bounded_versioned(
            key, POINTER_MAX_BYTES
        )
        written = store.put_bytes_strict_conditional(
            key,
            data,
            expected_version=current.version,
            content_type="application/json",
        )
    except Exception as exc:
        raise BroadSecError("store_write_failure", str(exc)) from exc
    if not written:
        raise BroadSecError("store_write_failure", f"CAS rejected for {key}")
    readback = store.get_bytes_strict_bounded(key, POINTER_MAX_BYTES)
    if readback != data:
        raise BroadSecError("store_readback_failure", f"pointer readback mismatch for {key}")


def admit_source_bytes(store: BroadSecStore, content: bytes) -> tuple[str, bool]:
    if not isinstance(content, (bytes, bytearray)):
        raise BroadSecError("invalid_sec_json", "SEC body is not bytes")
    digest = sha256(content).hexdigest()
    key = object_key(digest)
    packed = _gzip_bytes(bytes(content))
    existing = store.get_bytes_strict(key)
    if existing is not None:
        try:
            if sha256(_ungzip_bytes(existing)).hexdigest() == digest:
                return digest, False
        except OSError as exc:
            raise BroadSecError("store_readback_failure", f"corrupt object {key}") from exc
        raise BroadSecError("store_write_failure", f"object {key} already holds different bytes")
    try:
        written = store.put_bytes_strict_conditional(
            key, packed, expected_version=None, content_type="application/gzip"
        )
    except Exception as exc:
        raise BroadSecError("store_write_failure", str(exc)) from exc
    if not written:
        raced = store.get_bytes_strict(key)
        if raced is not None and sha256(_ungzip_bytes(raced)).hexdigest() == digest:
            return digest, False
        raise BroadSecError("store_write_failure", f"conditional create rejected for {key}")
    readback = store.get_bytes_strict(key)
    if readback is None or sha256(_ungzip_bytes(readback)).hexdigest() != digest:
        raise BroadSecError("store_readback_failure", f"object readback mismatch for {key}")
    return digest, True


def _progress(callback: ProgressFn | None, phase: str, **counts: Any) -> None:
    if callback is None:
        return
    callback(phase, dict(counts))


def _event_tuple(row: Mapping[str, str]) -> dict[str, str]:
    return {
        "cik": row["cik"],
        "accession": row["accession"],
        "form": row["form"],
        "filed_on": row["filed_on"],
        "filename": row["filename"],
    }


def _event_key(row: Mapping[str, str]) -> tuple[str, str, str, str, str]:
    return (row["cik"], row["accession"], row["form"], row["filed_on"], row["filename"])


def _bind_index_url(url: str | None, *, year: int, quarter: int) -> str:
    expected = full_master_index_url(year, quarter)
    if not isinstance(url, str) or url != expected:
        raise BroadSecError(
            "source_binding_failure",
            f"index URL {url!r} does not bind {year} Q{quarter}",
        )
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "www.sec.gov":
        raise BroadSecError("source_binding_failure", f"refusing non-SEC index URL {url!r}")
    return url


def parse_master_index_archive(
    archive: bytes,
    *,
    canonical_ciks: set[str],
) -> dict[str, Any]:
    """Validate an untrusted EDGAR master ZIP and return canonical relevant rows."""
    if not isinstance(archive, (bytes, bytearray)):
        raise BroadSecError("edgar_index_invalid", "index archive is not bytes")
    archive_bytes = bytes(archive)
    if len(archive_bytes) > MAX_MASTER_INDEX_ZIP_BYTES:
        raise BroadSecError(
            "edgar_index_too_large",
            f"index ZIP {len(archive_bytes)} exceeds {MAX_MASTER_INDEX_ZIP_BYTES}",
        )
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as handle:
            infos = list(handle.infolist())
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise BroadSecError("edgar_index_invalid", "duplicate ZIP member names")
            if any(bool(info.flag_bits & 0x1) for info in infos):
                raise BroadSecError("edgar_index_invalid", "encrypted ZIP member")
            for name in names:
                if name.startswith("/") or name.startswith("\\") or ":" in name.split("/")[0]:
                    raise BroadSecError("edgar_index_invalid", f"absolute ZIP member {name!r}")
                if ".." in Path(name).parts:
                    raise BroadSecError("edgar_index_invalid", f"traversal ZIP member {name!r}")
            masters = [info for info in infos if info.filename == MASTER_INDEX_MEMBER_NAME]
            if not masters:
                raise BroadSecError("edgar_index_member_missing", "master.idx is missing")
            if len(masters) != 1:
                raise BroadSecError("edgar_index_invalid", "duplicate master.idx member")
            info = masters[0]
            if int(info.file_size) > MAX_MASTER_INDEX_MEMBER_BYTES:
                raise BroadSecError(
                    "edgar_index_too_large",
                    f"master.idx {info.file_size} exceeds {MAX_MASTER_INDEX_MEMBER_BYTES}",
                )
            try:
                member = handle.read(info.filename)
            except Exception as exc:
                raise BroadSecError("edgar_index_invalid", "ZIP CRC/read failed") from exc
    except BroadSecError:
        raise
    except zipfile.BadZipFile as exc:
        raise BroadSecError("edgar_index_invalid", "malformed ZIP") from exc
    except Exception as exc:
        raise BroadSecError("edgar_index_invalid", f"ZIP open failed: {exc}") from exc

    if len(member) > MAX_MASTER_INDEX_MEMBER_BYTES:
        raise BroadSecError(
            "edgar_index_too_large",
            f"master.idx {len(member)} exceeds {MAX_MASTER_INDEX_MEMBER_BYTES}",
        )
    text = None
    encoding = None
    for candidate in ("utf-8", "latin-1"):
        try:
            text = member.decode(candidate)
            encoding = candidate
            break
        except UnicodeDecodeError:
            continue
    if text is None or encoding is None:
        raise BroadSecError("edgar_index_invalid", "master.idx did not decode")

    lines = text.splitlines()
    header_at = None
    for index, line in enumerate(lines):
        if line.strip() == MASTER_INDEX_HEADER:
            header_at = index
            break
    if header_at is None:
        raise BroadSecError("edgar_index_invalid", "master.idx header is missing")
    data_start = header_at + 1
    if data_start < len(lines) and set(lines[data_start].strip()) <= {"-"}:
        data_start += 1

    all_rows: list[dict[str, str]] = []
    relevant: list[dict[str, str]] = []
    for line in lines[data_start:]:
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) != 5:
            raise BroadSecError("edgar_index_invalid", "malformed master.idx line")
        cik_raw, _name, form, filed, filename = [part.strip() for part in parts]
        digits = "".join(ch for ch in cik_raw if ch.isdigit())
        if not digits:
            raise BroadSecError("edgar_index_invalid", "master.idx CIK is missing")
        cik = f"{int(digits):010d}"
        if not _DATE_RE.fullmatch(filed):
            raise BroadSecError("edgar_index_invalid", f"invalid filing date {filed!r}")
        try:
            datetime.strptime(filed, "%Y-%m-%d")
        except ValueError as exc:
            raise BroadSecError("edgar_index_invalid", f"invalid filing date {filed!r}") from exc
        path = _INDEX_FILENAME_RE.fullmatch(filename)
        if path is None:
            if form in RELEVANT_FORMS and cik in canonical_ciks:
                raise BroadSecError(
                    "edgar_index_invalid",
                    f"malformed accession path for canonical CIK {cik}",
                )
            continue
        path_cik = f"{int(path.group(1)):010d}"
        accession = path.group(2)
        if path_cik != cik:
            raise BroadSecError(
                "edgar_index_cik_mismatch",
                f"path CIK {path_cik} does not match row CIK {cik}",
            )
        row = {
            "cik": cik,
            "form": form,
            "filed_on": filed,
            "filename": filename,
            "accession": accession,
        }
        all_rows.append(row)
        if cik in canonical_ciks and form in RELEVANT_FORMS:
            relevant.append(_event_tuple(row))

    if not all_rows:
        raise BroadSecError("edgar_index_gap", "master.idx contains no filing rows")

    relevant.sort(key=_event_key)
    latest_filed = max((row["filed_on"] for row in all_rows), default=None)
    relevant_digest = sha256(
        canonical_json({"rows": relevant}).encode("utf-8")
    ).hexdigest()
    return {
        "member_name": MASTER_INDEX_MEMBER_NAME,
        "member": member,
        "member_bytes": len(member),
        "member_sha256": sha256(member).hexdigest(),
        "member_encoding": encoding,
        "parsed_row_count": len(all_rows),
        "latest_filing_date": latest_filed,
        "canonical_row_count": sum(1 for row in all_rows if row["cik"] in canonical_ciks),
        "relevant_rows": relevant,
        "relevant_set_sha256": relevant_digest,
        "relevant_ciks": sorted({row["cik"] for row in relevant}),
    }


def diff_relevant_sets(
    prior_rows: list[Mapping[str, str]],
    current_rows: list[Mapping[str, str]],
) -> dict[str, list[dict[str, str]]]:
    prior_map = {_event_key(row): dict(row) for row in prior_rows}
    current_map = {_event_key(row): dict(row) for row in current_rows}
    new_rows = [current_map[key] for key in current_map if key not in prior_map]
    removed_rows = [prior_map[key] for key in prior_map if key not in current_map]
    unchanged_rows = [current_map[key] for key in current_map if key in prior_map]
    new_rows.sort(key=_event_key)
    removed_rows.sort(key=_event_key)
    unchanged_rows.sort(key=_event_key)
    return {"new": new_rows, "removed": removed_rows, "unchanged": unchanged_rows}


def _index_identity_body(
    *,
    year: int,
    quarter: int,
    universe_sha: str,
    member_sha256: str,
    member_bytes: int,
    archive_sha256: str,
    relevant_rows: list[dict[str, str]],
    relevant_set_sha256: str,
    latest_filing_date: str | None,
    parsed_row_count: int,
    canonical_row_count: int,
) -> dict[str, Any]:
    return {
        "schema": INDEX_SNAPSHOT_SCHEMA,
        "year": year,
        "quarter": quarter,
        "quarter_id": quarter_id(year, quarter),
        "universe_sha256": universe_sha,
        "member_sha256": member_sha256,
        "member_bytes": member_bytes,
        "archive_sha256": archive_sha256,
        "relevant_set": relevant_rows,
        "relevant_set_sha256": relevant_set_sha256,
        "latest_filing_date": latest_filing_date,
        "parsed_row_count": parsed_row_count,
        "canonical_row_count": canonical_row_count,
        "relevant_row_count": len(relevant_rows),
    }


def _load_index_snapshot(store: BroadSecStore, year: int, quarter: int) -> dict[str, Any] | None:
    pointer = _read_json(store, index_latest_key(quarter_id(year, quarter)), maximum_bytes=POINTER_MAX_BYTES)
    if pointer is None:
        return None
    snapshot_key = pointer.get("snapshot_key")
    snapshot_id = pointer.get("snapshot_id")
    if not isinstance(snapshot_key, str) or not isinstance(snapshot_id, str):
        raise BroadSecError("issuer_manifest_invalid", "index latest pointer is missing snapshot_key")
    snapshot = _read_json(store, snapshot_key, maximum_bytes=MAX_MASTER_INDEX_MEMBER_BYTES)
    if snapshot is None:
        raise BroadSecError("issuer_manifest_invalid", "index snapshot missing")
    identity = {key: snapshot.get(key) for key in (
        "schema",
        "year",
        "quarter",
        "quarter_id",
        "universe_sha256",
        "member_sha256",
        "member_bytes",
        "archive_sha256",
        "relevant_set",
        "relevant_set_sha256",
        "latest_filing_date",
        "parsed_row_count",
        "canonical_row_count",
        "relevant_row_count",
    )}
    computed = sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    if computed != snapshot_id or snapshot.get("snapshot_id") != snapshot_id:
        raise BroadSecError("store_readback_failure", "index snapshot identity mismatch")
    return snapshot


def count_source_objects(store: BroadSecStore) -> int:
    return len(
        [
            key
            for key in store.list_prefix(f"{PREFIX}/objects/")
            if key.endswith(".json.gz")
        ]
    )


def _build_run_id(*, mode: str, poll_started_at: str, universe_sha: str) -> str:
    payload = canonical_json(
        {"mode": mode, "poll_started_at": poll_started_at, "universe": universe_sha}
    ).encode("utf-8")
    return "run_" + sha256(payload).hexdigest()[:20]


def _empty_universe_dict() -> dict[str, Any]:
    return {
        "path": UNIVERSE_RELATIVE_PATH,
        "universe_id": UNIVERSE_ID,
        "content_sha256": None,
        "issuer_count": 0,
        "unique_ticker_count": 0,
        "unique_cik_count": 0,
        "canonical": False,
    }


def _empty_receipt(
    *,
    run_id: str,
    mode: str,
    status: str,
    reason_code: str,
    clocks: PollClocks,
    universe: UniverseBinding | None,
    coverage: dict[str, int],
    change_summary: dict[str, int],
    latest_relevant_sec_accepted_at: str | None,
    failures: list[dict[str, str]],
    observation_key: str | None = None,
    observation_sha256: str | None = None,
    observation_row_count: int = 0,
    index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "mode": mode,
        "status": status,
        "reason_code": reason_code,
        "poll_started_at": clocks.poll_started_at,
        "poll_completed_at": clocks.poll_completed_at,
        "recorded_at": clocks.recorded_at,
        "selection_cutoff_at": clocks.selection_cutoff_at,
        "recovery_from": clocks.recovery_from,
        "latest_relevant_sec_accepted_at": latest_relevant_sec_accepted_at,
        "universe": universe.to_dict() if universe is not None else _empty_universe_dict(),
        "coverage": coverage,
        "change_summary": change_summary,
        "failures": failures,
        "index": index,
        "storage": {
            "prefix": PREFIX,
            "run_key": run_key(run_id),
            "observation_key": observation_key or issuer_observations_key(run_id),
            "observation_sha256": observation_sha256,
            "observation_row_count": observation_row_count,
            "latest_observation_key": latest_observation_key(),
            "latest_complete_key": latest_complete_key(),
        },
        "companyfacts_as_of_policy": "current_observed_snapshot",
    }


def _compact_head(
    receipt: Mapping[str, Any],
    *,
    observation_key: str,
    observation_sha256: str | None,
) -> dict[str, Any]:
    return {
        "schema": HEAD_SCHEMA,
        "run_id": receipt["run_id"],
        "run_key": receipt["storage"]["run_key"],
        "run_receipt_sha256": sha256(canonical_json(receipt).encode("utf-8")).hexdigest(),
        "status": receipt["status"],
        "poll_completed_at": receipt["poll_completed_at"],
        "universe_sha256": receipt["universe"].get("content_sha256"),
        "observation_key": observation_key,
        "observation_sha256": observation_sha256,
    }


def _prior_ledger(prior_manifest: Mapping[str, Any] | None) -> list[str]:
    if prior_manifest is None:
        return []
    ledger = prior_manifest.get("cumulative_relevant_accessions")
    if isinstance(ledger, list) and all(isinstance(item, str) for item in ledger):
        seen: dict[str, None] = {}
        for item in ledger:
            seen.setdefault(item, None)
        return list(seen)
    accessions: list[str] = []
    for item in prior_manifest.get("relevant_filings", []):
        if isinstance(item, dict) and isinstance(item.get("accession_number"), str):
            accessions.append(item["accession_number"])
    return accessions


def _load_continuation(
    store: BroadSecStore,
    *,
    recovery_from: str,
    universe_sha: str,
    index_snapshot_sha256: str | None = None,
) -> dict[str, Any] | None:
    pointer = _read_json(store, recovery_continuation_pointer_key(), maximum_bytes=POINTER_MAX_BYTES)
    if pointer is None:
        return None
    if pointer.get("recovery_from") != recovery_from or pointer.get("universe_sha256") != universe_sha:
        return None
    if index_snapshot_sha256 is not None:
        bound = pointer.get("index_snapshot_sha256")
        if bound is not None and bound != index_snapshot_sha256:
            raise BroadSecError(
                "edgar_index_invalid",
                "recovery continuation index_snapshot_sha256 mismatch",
            )
    object_ref = pointer.get("object_key")
    digest = pointer.get("sha256")
    if not isinstance(object_ref, str) or not isinstance(digest, str):
        return None
    packed = store.get_bytes_strict(object_ref)
    if packed is None:
        return None
    payload = json.loads(_ungzip_bytes(packed))
    if not isinstance(payload, dict):
        return None
    if sha256(canonical_json(payload).encode("utf-8")).hexdigest() != digest:
        raise BroadSecError("store_readback_failure", "recovery continuation digest mismatch")
    return payload


def _write_continuation(
    store: BroadSecStore,
    *,
    recovery_from: str,
    universe_sha: str,
    pending_ciks: list[str],
    completed_ciks: list[str],
    index_snapshot_sha256: str | None = None,
) -> None:
    body = {
        "schema": CONTINUATION_SCHEMA,
        "recovery_from": recovery_from,
        "universe_sha256": universe_sha,
        "index_snapshot_sha256": index_snapshot_sha256,
        "pending_ciks": pending_ciks,
        "completed_ciks": completed_ciks,
    }
    raw = canonical_json(body).encode("utf-8")
    digest = sha256(raw).hexdigest()
    key = recovery_continuation_object_key(digest)
    _put_immutable(store, key, _gzip_bytes(raw), content_type="application/gzip")
    _put_pointer(
        store,
        recovery_continuation_pointer_key(),
        {
            "schema": "fundamental_forensics.broad_sec.recovery_continuation_head.v1",
            "recovery_from": recovery_from,
            "universe_sha256": universe_sha,
            "index_snapshot_sha256": index_snapshot_sha256,
            "object_key": key,
            "sha256": digest,
            "pending_count": len(pending_ciks),
            "completed_count": len(completed_ciks),
        },
    )


def _stamp_after_fetch(headers: Mapping[str, str | None], *, now: NowFn) -> dict[str, str | None]:
    meta = dict(headers)
    meta["retrieved_at"] = _require_iso_z(now(), field="retrieved_at")
    return meta


def run_broad_sec_poll(
    *,
    store: BroadSecStore,
    universe_path: Path,
    fetch_submissions: FetchBytes,
    fetch_companyfacts: FetchBytes,
    clocks: PollClocks,
    now: NowFn,
    mode: str = "incremental",
    repo_root: Path | None = None,
    max_affected_issuers: int = MAX_AFFECTED_ISSUERS,
    max_companyfacts_bytes_per_run: int = MAX_COMPANYFACTS_BYTES_PER_RUN,
    fetch_master_index: FetchIndex | None = None,
    on_progress: ProgressFn | None = None,
) -> PollResult:
    if mode not in {"incremental", "recovery"}:
        raise ValueError("mode must be incremental or recovery")
    if mode == "recovery":
        clocks.poll_completed_at = clocks.poll_completed_at or now()
        clocks.recorded_at = clocks.recorded_at or now()
        run_id = _build_run_id(
            mode=mode,
            poll_started_at=clocks.poll_started_at,
            universe_sha="recovery_not_commissioned",
        )
        receipt = _empty_receipt(
            run_id=run_id,
            mode=mode,
            status="failed",
            reason_code="recovery_plan_required",
            clocks=clocks,
            universe=None,
            coverage={
                "expected_issuers": 0,
                "observed_issuers": 0,
                "failed_issuers": 0,
                "companyfacts_fetched": 0,
                "companyfacts_skipped_unchanged": 0,
                "companyfacts_bytes_fetched": 0,
                "companyfacts_deferred": 0,
                "recovery_backlog": 0,
            },
            change_summary={
                "new_relevant_accessions": 0,
                "affected_issuers": 0,
                "objects_admitted": 0,
                "manifests_admitted": 0,
            },
            latest_relevant_sec_accepted_at=None,
            failures=[
                {
                    "ticker": "",
                    "cik": "",
                    "reason_code": "recovery_plan_required",
                    "detail": (
                        "Index-driven discovery is live, but large-scale recovery "
                        "is not commissioned on this build."
                    ),
                }
            ],
        )
        return PollResult(receipt=receipt, exit_code=1)
    if mode == "incremental" and clocks.recovery_from:
        raise BroadSecError("universe_invalid", "incremental mode cannot carry a recovery window")
    if fetch_master_index is None:
        raise BroadSecError("edgar_index_unavailable", "fetch_master_index is required")
    _require_iso_z(clocks.poll_started_at, field="poll_started_at")
    _require_iso_z(clocks.selection_cutoff_at, field="selection_cutoff_at")
    if clocks.recovery_from:
        _require_iso_z(clocks.recovery_from, field="recovery_from")
    if clocks.recorded_at:
        _require_iso_z(clocks.recorded_at, field="recorded_at")
    if clocks.poll_completed_at:
        _require_iso_z(clocks.poll_completed_at, field="poll_completed_at")

    coverage = {
        "expected_issuers": 0,
        "observed_issuers": 0,
        "failed_issuers": 0,
        "companyfacts_fetched": 0,
        "companyfacts_skipped_unchanged": 0,
        "companyfacts_bytes_fetched": 0,
        "companyfacts_deferred": 0,
        "recovery_backlog": 0,
    }
    change_summary = {
        "new_relevant_accessions": 0,
        "affected_issuers": 0,
        "objects_admitted": 0,
        "manifests_admitted": 0,
    }

    try:
        universe = load_universe(universe_path, repo_root=repo_root)
    except BroadSecError as exc:
        run_id = _build_run_id(
            mode=mode, poll_started_at=clocks.poll_started_at, universe_sha="invalid"
        )
        clocks.poll_completed_at = clocks.poll_completed_at or now()
        clocks.recorded_at = clocks.recorded_at or now()
        receipt = _empty_receipt(
            run_id=run_id,
            mode=mode,
            status="failed",
            reason_code=exc.reason_code,
            clocks=clocks,
            universe=None,
            coverage=coverage,
            change_summary=change_summary,
            latest_relevant_sec_accepted_at=None,
            failures=[{"ticker": "", "cik": "", "reason_code": exc.reason_code, "detail": exc.detail}],
        )
        return PollResult(receipt=receipt, exit_code=1)

    run_id = _build_run_id(
        mode=mode,
        poll_started_at=clocks.poll_started_at,
        universe_sha=universe.content_sha256,
    )
    coverage["expected_issuers"] = universe.issuer_count
    year, quarter = calendar_quarter(clocks.selection_cutoff_at)
    canonical_ciks = {issuer.cik for issuer in universe.issuers}

    def _fail_index(exc: BroadSecError) -> PollResult:
        clocks.poll_completed_at = clocks.poll_completed_at or now()
        clocks.recorded_at = clocks.recorded_at or now()
        receipt = _empty_receipt(
            run_id=run_id,
            mode=mode,
            status="failed",
            reason_code=exc.reason_code,
            clocks=clocks,
            universe=universe,
            coverage=coverage,
            change_summary=change_summary,
            latest_relevant_sec_accepted_at=None,
            failures=[{"ticker": "", "cik": "", "reason_code": exc.reason_code, "detail": exc.detail}],
        )
        return PollResult(receipt=receipt, exit_code=1)

    _progress(on_progress, "index_fetch", year=year, quarter=quarter)
    try:
        archive, index_headers = fetch_master_index(year, quarter)
        index_headers = _stamp_after_fetch(index_headers, now=now)
        url = _bind_index_url(index_headers.get("url"), year=year, quarter=quarter)
        if len(archive) > MAX_MASTER_INDEX_ZIP_BYTES:
            raise BroadSecError(
                "edgar_index_too_large",
                f"index ZIP {len(archive)} exceeds {MAX_MASTER_INDEX_ZIP_BYTES}",
            )
        parsed = parse_master_index_archive(archive, canonical_ciks=canonical_ciks)
    except BroadSecError as exc:
        return _fail_index(exc)
    except SecResponseTooLarge as exc:
        return _fail_index(BroadSecError("edgar_index_too_large", str(exc)))
    except Exception as exc:
        reason = classify_fetch_error(exc)
        mapped = "edgar_index_unavailable"
        if reason == "response_too_large":
            mapped = "edgar_index_too_large"
        elif reason == "source_binding_failure":
            mapped = "source_binding_failure"
        return _fail_index(BroadSecError(mapped, str(exc)))

    _progress(
        on_progress,
        "index_parse",
        rows=parsed["parsed_row_count"],
        relevant=len(parsed["relevant_rows"]),
        canonical=universe.issuer_count,
    )
    if previous_quarter_reconciliation_due(poll_started_at=clocks.poll_started_at):
        raise BroadSecError(
            "edgar_index_unavailable",
            "weekly previous-quarter reconciliation is frozen; not implemented in this PR",
        )
    archive_sha = sha256(archive).hexdigest()
    if index_headers.get("archive_sha256") and index_headers["archive_sha256"] != archive_sha:
        return _fail_index(BroadSecError("edgar_index_invalid", "archive SHA-256 mismatch"))

    identity = _index_identity_body(
        year=year,
        quarter=quarter,
        universe_sha=universe.content_sha256,
        member_sha256=parsed["member_sha256"],
        member_bytes=parsed["member_bytes"],
        archive_sha256=archive_sha,
        relevant_rows=parsed["relevant_rows"],
        relevant_set_sha256=parsed["relevant_set_sha256"],
        latest_filing_date=parsed["latest_filing_date"],
        parsed_row_count=parsed["parsed_row_count"],
        canonical_row_count=parsed["canonical_row_count"],
    )
    snapshot_id = sha256(canonical_json(identity).encode("utf-8")).hexdigest()

    try:
        prior_snapshot = _load_index_snapshot(store, year, quarter)
    except BroadSecError as exc:
        return _fail_index(exc)
    baseline = prior_snapshot is None and mode == "incremental"
    prior_rows = list(prior_snapshot.get("relevant_set") or []) if prior_snapshot else []
    if baseline:
        diff = {"new": [], "removed": [], "unchanged": list(parsed["relevant_rows"])}
    else:
        diff = diff_relevant_sets(prior_rows, parsed["relevant_rows"])
    _progress(
        on_progress,
        "index_diff",
        new=len(diff["new"]),
        unchanged=len(diff["unchanged"]),
        corrections=len(diff["removed"]),
        baseline=int(baseline),
    )

    new_by_cik: dict[str, list[dict[str, str]]] = {}
    removed_by_cik: dict[str, list[dict[str, str]]] = {}
    relevant_by_cik: dict[str, list[dict[str, str]]] = {}
    for row in parsed["relevant_rows"]:
        relevant_by_cik.setdefault(row["cik"], []).append(row)
    for row in diff["new"]:
        new_by_cik.setdefault(row["cik"], []).append(row)
    for row in diff["removed"]:
        removed_by_cik.setdefault(row["cik"], []).append(row)

    continuation = None
    if mode == "recovery" and clocks.recovery_from:
        continuation = _load_continuation(
            store,
            recovery_from=clocks.recovery_from,
            universe_sha=universe.content_sha256,
            index_snapshot_sha256=snapshot_id,
        )
    continuation_completed = set(continuation.get("completed_ciks", []) if continuation else [])
    continuation_pending = set(continuation.get("pending_ciks", []) if continuation else [])

    recovery_date = None
    if clocks.recovery_from:
        recovery_date = clocks.recovery_from[:10]

    if mode == "recovery":
        if continuation is not None:
            work_ciks = set(continuation_pending)
        else:
            work_ciks = {
                row["cik"]
                for row in parsed["relevant_rows"]
                if recovery_date and row["filed_on"] >= recovery_date
            }
    elif baseline:
        work_ciks = set()
    else:
        work_ciks = set(new_by_cik) | set(removed_by_cik)

    work_ciks &= canonical_ciks
    _progress(on_progress, "affected_submissions", affected=len(work_ciks))

    failures: list[IssuerFailure] = []
    observations: list[dict[str, Any]] = []
    prepared: list[dict[str, Any]] = []
    source_accepts: list[str | None] = []

    def _blank_observation(issuer: Issuer) -> dict[str, Any]:
        return {
            "ticker": issuer.ticker,
            "cik": issuer.cik,
            "outcome": "failed",
            "reason_code": None,
            "submissions_sha256": None,
            "submissions_object_key": None,
            "submissions_retrieved_at": None,
            "manifest_id": None,
            "manifest_key": None,
            "companyfacts_fetched": False,
            "companyfacts_sha256": None,
            "companyfacts_object_key": None,
            "companyfacts_retrieved_at": None,
            "cumulative_manifest_id": None,
            "withheld_count": 0,
            "discovery_source": INDEX_SOURCE_KIND,
            "index_snapshot_sha256": snapshot_id,
            "relevant_event_count": len(relevant_by_cik.get(issuer.cik, [])),
            "new_event_count": len(new_by_cik.get(issuer.cik, [])),
            "correction_event_count": len(removed_by_cik.get(issuer.cik, [])),
            "submissions_fetched": False,
        }

    for issuer in universe.issuers:
        observation = _blank_observation(issuer)
        if issuer.cik not in work_ciks:
            observation["outcome"] = "observed_no_relevant_change"
            if baseline:
                observation["new_event_count"] = 0
                observation["correction_event_count"] = 0
            observations.append(observation)
            coverage["observed_issuers"] += 1
            continue
        try:
            body, headers = fetch_submissions(issuer.cik)
            headers = _stamp_after_fetch(headers, now=now)
            url = _bind_sec_url(headers.get("url"), cik=issuer.cik, endpoint="submissions")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise BroadSecError("invalid_sec_json", f"{issuer.ticker} Submissions is not JSON") from exc
            if not isinstance(payload, dict):
                raise BroadSecError("invalid_sec_json", f"{issuer.ticker} Submissions is not an object")
            admitted, withheld, historical_required = parse_relevant_filings(
                payload,
                cik=issuer.cik,
                ticker=issuer.ticker,
                selection_cutoff_at=clocks.selection_cutoff_at,
                recovery_from=clocks.recovery_from,
            )
            if historical_required:
                raise BroadSecError(
                    "historical_submissions_required",
                    f"{issuer.ticker} recovery window predates current Submissions.recent",
                )
            submissions_sha, created = admit_source_bytes(store, body)
            if created:
                change_summary["objects_admitted"] += 1
            prior_pointer = _read_json(store, issuer_latest_key(issuer.cik), maximum_bytes=POINTER_MAX_BYTES)
            prior_manifest = None
            if prior_pointer is not None:
                manifest_key = prior_pointer.get("manifest_key")
                if not isinstance(manifest_key, str):
                    raise BroadSecError("issuer_manifest_invalid", f"{issuer.ticker} latest pointer is missing manifest_key")
                prior_manifest = _read_json(store, manifest_key, maximum_bytes=POINTER_MAX_BYTES)
                if prior_manifest is None:
                    raise BroadSecError("issuer_manifest_invalid", f"{issuer.ticker} prior manifest missing")
            prior_ledger = _prior_ledger(prior_manifest)
            current_accessions = [
                item["accession_number"]
                for item in admitted
                if isinstance(item.get("accession_number"), str)
            ]
            index_new_accessions = {row["accession"] for row in new_by_cik.get(issuer.cik, [])}
            if mode == "recovery":
                new_accessions = [acc for acc in current_accessions if acc not in prior_ledger]
            else:
                new_accessions = [
                    acc
                    for acc in current_accessions
                    if acc in index_new_accessions and acc not in prior_ledger
                ]
            recovery_delta = [
                item
                for item in admitted
                if clocks.recovery_from
                and isinstance(item.get("acceptance_datetime"), str)
                and item["acceptance_datetime"] >= clocks.recovery_from
            ]
            if mode == "recovery":
                needs_facts = bool(recovery_delta) or issuer.cik in continuation_pending
                if issuer.cik in continuation_completed and not new_accessions:
                    needs_facts = False
            else:
                needs_facts = bool(new_accessions)
            withheld_by_acc = {
                row["accession_number"]: row
                for row in withheld
                if isinstance(row.get("accession_number"), str)
            }
            unresolved_new: list[tuple[str, str]] = []
            for row in new_by_cik.get(issuer.cik, []):
                acc = row["accession"]
                if acc in set(current_accessions):
                    continue
                withheld_row = withheld_by_acc.get(acc)
                cause = (
                    str(withheld_row.get("withheld_cause") or "unevaluable")
                    if withheld_row is not None
                    else "missing_from_submissions"
                )
                unresolved_new.append((acc, cause))
            if unresolved_new:
                needs_facts = False
                observation["reason_code"] = "edgar_index_event_not_causally_admitted"
            change_summary["new_relevant_accessions"] += len(
                recovery_delta if mode == "recovery" else new_accessions
            )
            observation.update(
                {
                    "outcome": "observed",
                    "submissions_sha256": submissions_sha,
                    "submissions_object_key": object_key(submissions_sha),
                    "submissions_retrieved_at": headers.get("retrieved_at"),
                    "withheld_count": len(withheld),
                    "submissions_fetched": True,
                }
            )
            prepared.append(
                {
                    "issuer": issuer,
                    "submissions_sha": submissions_sha,
                    "submissions_headers": headers,
                    "admitted": admitted,
                    "withheld": withheld,
                    "prior_manifest": prior_manifest,
                    "prior_ledger": prior_ledger,
                    "new_accessions": new_accessions,
                    "recovery_delta": recovery_delta,
                    "needs_facts": needs_facts,
                    "observation": observation,
                    "index_removed": removed_by_cik.get(issuer.cik, []),
                    "unresolved_new": unresolved_new,
                }
            )
            del url
        except BroadSecError as exc:
            observation["reason_code"] = exc.reason_code
            observations.append(observation)
            failures.append(IssuerFailure(issuer.ticker, issuer.cik, exc.reason_code, exc.detail))
            coverage["failed_issuers"] += 1
        except Exception as exc:
            reason = classify_fetch_error(exc)
            observation["reason_code"] = reason
            observations.append(observation)
            failures.append(IssuerFailure(issuer.ticker, issuer.cik, reason, str(exc)))
            coverage["failed_issuers"] += 1

    for item in prepared:
        unresolved = item.get("unresolved_new") or []
        if not unresolved:
            continue
        issuer = item["issuer"]
        causes = ", ".join(f"{acc}:{cause}" for acc, cause in unresolved)
        failures.append(
            IssuerFailure(
                issuer.ticker,
                issuer.cik,
                "edgar_index_event_not_causally_admitted",
                f"{issuer.ticker} index event(s) not causally admitted ({causes})",
            )
        )
        coverage["failed_issuers"] += 1

    facts_candidates = [item for item in prepared if item["needs_facts"]]
    facts_candidates.sort(key=lambda item: (item["issuer"].ticker, item["issuer"].cik))
    change_summary["affected_issuers"] = len(facts_candidates)
    overflow = False
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    if mode == "incremental" and len(facts_candidates) > max_affected_issuers:
        overflow = True
        deferred = list(facts_candidates)
        failures.append(
            IssuerFailure(
                "",
                "",
                "queue_overflow",
                (
                    f"incremental cap is {max_affected_issuers}"
                ),
            )
        )
    elif len(facts_candidates) > max_affected_issuers:
        overflow = True
        selected = facts_candidates[:max_affected_issuers]
        deferred = facts_candidates[max_affected_issuers:]
        failures.append(
            IssuerFailure(
                "",
                "",
                "queue_overflow",
                f"{len(facts_candidates)} issuers need Company Facts; processing {len(selected)} this run",
            )
        )
    else:
        selected = list(facts_candidates)
    selected_ciks = {item["issuer"].cik for item in selected}
    coverage["companyfacts_deferred"] = len(deferred)
    coverage["recovery_backlog"] = len(deferred)

    _progress(on_progress, "companyfacts", candidates=len(facts_candidates), selected=len(selected))
    facts_bytes = 0
    stop_facts_network = False
    for item in prepared:
        issuer = item["issuer"]
        observation = item["observation"]
        fetch_this = item["needs_facts"] and issuer.cik in selected_ciks and not stop_facts_network
        facts_sha = None
        facts_retrieved_at = None
        snapshot_kind = "not_fetched"
        try:
            if fetch_this:
                remaining = max_companyfacts_bytes_per_run - facts_bytes
                if remaining <= 0:
                    stop_facts_network = True
                    overflow = True
                    fetch_this = False
                    deferred.append(item)
                    coverage["companyfacts_deferred"] += 1
                    coverage["recovery_backlog"] = len(
                        {row["issuer"].cik for row in deferred}
                    )
                else:
                    facts_body, facts_headers = fetch_companyfacts(issuer.cik)
                    facts_headers = _stamp_after_fetch(facts_headers, now=now)
                    if len(facts_body) > remaining:
                        stop_facts_network = True
                        overflow = True
                        fetch_this = False
                        deferred.append(item)
                        coverage["companyfacts_deferred"] += 1
                        coverage["recovery_backlog"] = len(
                            {row["issuer"].cik for row in deferred}
                        )
                        failures.append(
                            IssuerFailure(
                                issuer.ticker,
                                issuer.cik,
                                "queue_overflow",
                                "Company Facts byte budget exhausted; body not admitted",
                            )
                        )
                    else:
                        _bind_sec_url(facts_headers.get("url"), cik=issuer.cik, endpoint="companyfacts")
                        try:
                            facts_payload = json.loads(facts_body)
                        except json.JSONDecodeError as exc:
                            raise BroadSecError(
                                "invalid_sec_json", f"{issuer.ticker} Company Facts is not JSON"
                            ) from exc
                        if not isinstance(facts_payload, dict):
                            raise BroadSecError(
                                "invalid_sec_json", f"{issuer.ticker} Company Facts is not an object"
                            )
                        if "as_of" in facts_payload or facts_headers.get("as_of"):
                            raise BroadSecError(
                                "source_binding_failure",
                                "Company Facts must not be labelled historical as-of",
                            )
                        facts_bytes += len(facts_body)
                        facts_sha, facts_created = admit_source_bytes(store, facts_body)
                        if facts_created:
                            change_summary["objects_admitted"] += 1
                        coverage["companyfacts_fetched"] += 1
                        coverage["companyfacts_bytes_fetched"] = facts_bytes
                        facts_retrieved_at = facts_headers.get("retrieved_at")
                        snapshot_kind = "current_observed"
                        observation["companyfacts_fetched"] = True
                        observation["companyfacts_sha256"] = facts_sha
                        observation["companyfacts_object_key"] = object_key(facts_sha)
                        observation["companyfacts_retrieved_at"] = facts_retrieved_at
            if not fetch_this:
                prior = item["prior_manifest"]
                if prior and prior.get("companyfacts_snapshot_kind") == "current_observed":
                    facts_sha = prior.get("companyfacts_sha256")
                    snapshot_kind = "current_observed"
                    facts_retrieved_at = prior.get("companyfacts_retrieved_at")
                    observation["companyfacts_sha256"] = facts_sha
                    observation["companyfacts_object_key"] = (
                        object_key(facts_sha) if isinstance(facts_sha, str) else None
                    )
                    observation["companyfacts_retrieved_at"] = facts_retrieved_at
                if item["needs_facts"] and issuer.cik not in selected_ciks:
                    coverage["companyfacts_skipped_unchanged"] += 0
                elif not item["needs_facts"]:
                    coverage["companyfacts_skipped_unchanged"] += 1

            prior_manifest = item["prior_manifest"]
            submissions_unchanged = (
                prior_manifest is not None
                and prior_manifest.get("submissions_sha256") == item["submissions_sha"]
                and not item["new_accessions"]
                and snapshot_kind == prior_manifest.get("companyfacts_snapshot_kind")
                and facts_sha == prior_manifest.get("companyfacts_sha256")
                and not item["index_removed"]
            )
            if submissions_unchanged:
                observation["manifest_id"] = prior_manifest["manifest_id"]
                observation["manifest_key"] = issuer_manifest_key(issuer.cik, prior_manifest["manifest_id"])
                observation["cumulative_manifest_id"] = prior_manifest["manifest_id"]
                observation["outcome"] = "observed"
                observations.append(observation)
                coverage["observed_issuers"] += 1
                source_accepts.append(prior_manifest.get("sec_accepted_at"))
                continue

            cumulative: list[str] = []
            seen: dict[str, None] = {}

            def _remember(accession: str) -> None:
                if accession not in seen:
                    seen[accession] = None
                    cumulative.append(accession)

            for acc in item["prior_ledger"]:
                _remember(acc)
            for acc in item["admitted"]:
                number = acc.get("accession_number")
                if isinstance(number, str):
                    _remember(number)
            for removed in item["index_removed"]:
                accession = removed.get("accession")
                if isinstance(accession, str):
                    _remember(accession)
            previous_id = prior_manifest["manifest_id"] if prior_manifest else None
            manifest = {
                "schema": MANIFEST_SCHEMA,
                "cik": issuer.cik,
                "ticker": issuer.ticker,
                "submissions_sha256": item["submissions_sha"],
                "submissions_url": endpoint_url(issuer.cik, "submissions"),
                "submissions_object_key": object_key(item["submissions_sha"]),
                "submissions_retrieved_at": item["submissions_headers"].get("retrieved_at"),
                "companyfacts_sha256": facts_sha,
                "companyfacts_url": endpoint_url(issuer.cik, "companyfacts") if facts_sha else None,
                "companyfacts_object_key": object_key(facts_sha) if facts_sha else None,
                "companyfacts_retrieved_at": facts_retrieved_at,
                "companyfacts_snapshot_kind": snapshot_kind,
                "relevant_filings": [
                    {key: value for key, value in row.items() if not key.startswith("withheld_")}
                    for row in item["admitted"]
                ],
                "withheld_filings": item["withheld"],
                "cumulative_relevant_accessions": cumulative,
                "previous_manifest_id": previous_id,
                "recorded_at": None,
                "sec_accepted_at": _max_iso(
                    [row.get("acceptance_datetime") for row in item["admitted"]]
                ),
                "filed_on": max(
                    (row["filing_date"] for row in item["admitted"] if row.get("filing_date")),
                    default=None,
                ),
            }
            item["manifest"] = manifest
            item["cumulative"] = cumulative
            item["snapshot_kind"] = snapshot_kind
            item["facts_sha"] = facts_sha
        except BroadSecError as exc:
            if exc.reason_code == "queue_overflow":
                overflow = True
            observation["outcome"] = "failed"
            observation["reason_code"] = exc.reason_code
            observations.append(observation)
            failures.append(IssuerFailure(issuer.ticker, issuer.cik, exc.reason_code, exc.detail))
            coverage["failed_issuers"] += 1
            item["failed"] = True
        except Exception as exc:
            reason = classify_fetch_error(exc)
            observation["outcome"] = "failed"
            observation["reason_code"] = reason
            observations.append(observation)
            failures.append(IssuerFailure(issuer.ticker, issuer.cik, reason, str(exc)))
            coverage["failed_issuers"] += 1
            item["failed"] = True

    clocks.recorded_at = clocks.recorded_at or now()
    _progress(on_progress, "publish", prepared=len(prepared), observed=coverage["observed_issuers"])
    index_pointer = None
    try:
        _put_immutable(
            store,
            index_object_key(parsed["member_sha256"]),
            _gzip_bytes(parsed["member"]),
            content_type="application/gzip",
        )
        stored_snapshot = {
            **identity,
            "snapshot_id": snapshot_id,
            "previous_snapshot_id": prior_snapshot.get("snapshot_id") if prior_snapshot else None,
        }
        _put_immutable(
            store,
            index_snapshot_key(identity["quarter_id"], snapshot_id),
            canonical_json(stored_snapshot).encode("utf-8"),
        )
        index_pointer = {
            "schema": "fundamental_forensics.broad_sec.index_latest.v1",
            "quarter_id": identity["quarter_id"],
            "snapshot_id": snapshot_id,
            "snapshot_key": index_snapshot_key(identity["quarter_id"], snapshot_id),
            "member_sha256": parsed["member_sha256"],
            "relevant_set_sha256": parsed["relevant_set_sha256"],
        }
    except BroadSecError as exc:
        failures.append(IssuerFailure("", "", exc.reason_code, exc.detail))
        index_pointer = None

    for item in prepared:
        if item.get("failed") or "manifest" not in item:
            continue
        issuer = item["issuer"]
        observation = item["observation"]
        manifest = item["manifest"]
        manifest["recorded_at"] = clocks.recorded_at
        if "as_of" in manifest:
            raise BroadSecError("source_binding_failure", "issuer manifest must not carry as_of")
        manifest_id = issuer_source_identity(manifest)
        manifest["manifest_id"] = manifest_id
        encoded = canonical_json(manifest).encode("utf-8")
        try:
            _put_immutable(store, issuer_manifest_key(issuer.cik, manifest_id), encoded)
            change_summary["manifests_admitted"] += 1
            pointer = {
                "schema": "fundamental_forensics.broad_sec.issuer_latest.v1",
                "cik": issuer.cik,
                "ticker": issuer.ticker,
                "manifest_id": manifest_id,
                "manifest_key": issuer_manifest_key(issuer.cik, manifest_id),
                "submissions_sha256": item["submissions_sha"],
                "companyfacts_sha256": item.get("facts_sha"),
            }
            _put_pointer(store, issuer_latest_key(issuer.cik), pointer)
            observation["manifest_id"] = manifest_id
            observation["manifest_key"] = issuer_manifest_key(issuer.cik, manifest_id)
            observation["cumulative_manifest_id"] = manifest_id
            observation["outcome"] = "observed"
            observations.append(observation)
            coverage["observed_issuers"] += 1
            source_accepts.append(manifest.get("sec_accepted_at"))
        except BroadSecError as exc:
            observation["outcome"] = "failed"
            observation["reason_code"] = exc.reason_code
            observations.append(observation)
            failures.append(IssuerFailure(issuer.ticker, issuer.cik, exc.reason_code, exc.detail))
            coverage["failed_issuers"] += 1

    if mode == "recovery" and clocks.recovery_from:
        pending_ciks = sorted(
            {
                item["issuer"].cik
                for item in prepared
                if item.get("needs_facts")
                and not item["observation"].get("companyfacts_fetched")
            }
            | (work_ciks - {item["issuer"].cik for item in prepared} - continuation_completed)
        )
        completed_ciks = sorted(
            (
                continuation_completed
                | {
                    item["issuer"].cik
                    for item in prepared
                    if item["observation"].get("companyfacts_fetched")
                    or (
                        not item.get("needs_facts")
                        and item["observation"].get("outcome") == "observed"
                    )
                }
            )
            - set(pending_ciks)
        )
        coverage["recovery_backlog"] = len(pending_ciks)
        try:
            _write_continuation(
                store,
                recovery_from=clocks.recovery_from,
                universe_sha=universe.content_sha256,
                pending_ciks=pending_ciks,
                completed_ciks=completed_ciks,
                index_snapshot_sha256=snapshot_id,
            )
        except BroadSecError as exc:
            failures.append(IssuerFailure("", "", exc.reason_code, exc.detail))
        if pending_ciks:
            overflow = True

    clocks.poll_completed_at = clocks.poll_completed_at or now()
    latest_source = _max_iso(source_accepts)
    backlog_remaining = coverage["recovery_backlog"] > 0
    complete = (
        coverage["failed_issuers"] == 0
        and not overflow
        and not backlog_remaining
        and coverage["observed_issuers"] == universe.issuer_count
        and universe.canonical
    )
    poll_complete = (
        coverage["failed_issuers"] == 0
        and not overflow
        and not backlog_remaining
        and coverage["observed_issuers"] == universe.issuer_count
    )
    if complete or (poll_complete and not universe.canonical):
        status = "complete"
        reason_code = "complete"
        exit_code = 0 if universe.canonical else 1
        if not universe.canonical:
            status = "degraded"
            reason_code = "universe_invalid"
            failures.append(
                IssuerFailure(
                    "",
                    "",
                    "universe_invalid",
                    "noncanonical universe cannot advance the complete broad census",
                )
            )
            exit_code = 1
            poll_complete = False
    elif coverage["observed_issuers"] > 0:
        status = "degraded"
        reason_code = failures[0].reason_code if failures else "store_write_failure"
        exit_code = 1
    else:
        status = "failed"
        reason_code = failures[0].reason_code if failures else "store_write_failure"
        exit_code = 1

    observations.sort(key=lambda row: (row["ticker"], row["cik"]))
    observation_payload = {
        "schema": OBSERVATION_SCHEMA,
        "run_id": run_id,
        "row_count": len(observations),
        "issuers": observations,
    }
    observation_raw = canonical_json(observation_payload).encode("utf-8")
    observation_sha = sha256(observation_raw).hexdigest()
    observation_key = issuer_observations_key(run_id)
    index_receipt = {
        "source_kind": INDEX_SOURCE_KIND,
        "index_url": full_master_index_url(year, quarter),
        "year": year,
        "quarter": quarter,
        "archive_sha256": archive_sha,
        "archive_bytes": len(archive),
        "archive_retrieved_at": index_headers.get("retrieved_at"),
        "http_etag": index_headers.get("http_etag"),
        "http_last_modified": index_headers.get("http_last_modified"),
        "member_name": MASTER_INDEX_MEMBER_NAME,
        "member_sha256": parsed["member_sha256"],
        "member_bytes": parsed["member_bytes"],
        "latest_filing_date": parsed["latest_filing_date"],
        "snapshot_sha256": snapshot_id,
        "relevant_set_sha256": parsed["relevant_set_sha256"],
        "new_events": 0 if baseline else len(diff["new"]),
        "unchanged_events": len(diff["unchanged"]),
        "correction_events": 0 if baseline else len(diff["removed"]),
        "baseline": baseline,
    }
    receipt = _empty_receipt(
        run_id=run_id,
        mode=mode,
        status=status,
        reason_code=reason_code,
        clocks=clocks,
        universe=universe,
        coverage=coverage,
        change_summary=change_summary,
        latest_relevant_sec_accepted_at=latest_source,
        failures=[item.to_dict() for item in failures],
        observation_key=observation_key,
        observation_sha256=observation_sha,
        observation_row_count=len(observations),
        index=index_receipt,
    )
    encoded_receipt = canonical_json(receipt).encode("utf-8")
    census_complete = status == "complete" and universe.canonical and exit_code == 0
    _progress(on_progress, "finalize", status=status, complete=int(census_complete))
    try:
        _put_immutable(
            store,
            observation_key,
            _gzip_bytes(observation_raw),
            content_type="application/gzip",
        )
        _put_immutable(store, run_key(run_id), encoded_receipt)
        _put_pointer(store, latest_observation_key(), _compact_head(
            receipt, observation_key=observation_key, observation_sha256=observation_sha
        ))
        if census_complete:
            _put_pointer(store, latest_complete_key(), _compact_head(
                receipt, observation_key=observation_key, observation_sha256=observation_sha
            ))
        if index_pointer is not None and census_complete:
            existing_index = _read_json(
                store, index_latest_key(identity["quarter_id"]), maximum_bytes=POINTER_MAX_BYTES
            )
            if existing_index is None or existing_index.get("snapshot_id") != snapshot_id:
                _put_pointer(store, index_latest_key(identity["quarter_id"]), index_pointer)
    except BroadSecError as exc:
        receipt["status"] = "failed"
        receipt["reason_code"] = exc.reason_code
        receipt["failures"] = list(receipt["failures"]) + [
            {"ticker": "", "cik": "", "reason_code": exc.reason_code, "detail": exc.detail}
        ]
        try:
            failed_head = _compact_head(
                receipt, observation_key=observation_key, observation_sha256=observation_sha
            )
            failed_head["status"] = "failed"
            _put_pointer(store, latest_observation_key(), failed_head)
        except BroadSecError:
            pass
        return PollResult(receipt=receipt, exit_code=1)
    return PollResult(receipt=receipt, exit_code=exit_code)


def live_fetchers(
    *,
    user_agent: str,
    scratch_root: Path,
    submissions_session: Any = None,
    companyfacts_fetcher: Any = None,
    retrieved_at: str | None = None,
) -> tuple[FetchBytes, FetchBytes, FetchIndex]:
    from collectors.edgar_forensics import SecForensicsCollector
    from collectors.fundamental_forensics_companyfacts import SecCompanyFactsCollector

    del retrieved_at
    submissions = SecForensicsCollector(
        scratch_root,
        user_agent=user_agent,
        session=submissions_session,
        max_response_bytes=MAX_SUBMISSIONS_BYTES,
    )
    facts = SecCompanyFactsCollector(
        user_agent=user_agent,
        fetcher=companyfacts_fetcher,
        max_attempts=4,
    )

    def fetch_submissions(cik: str) -> tuple[bytes, Mapping[str, str | None]]:
        try:
            body, headers = submissions.retrieve_current(
                cik, "submissions", max_response_bytes=MAX_SUBMISSIONS_BYTES
            )
        except Exception as exc:
            raise BroadSecError(classify_fetch_error(exc), str(exc)) from exc
        return body, dict(headers)

    def fetch_companyfacts(cik: str) -> tuple[bytes, Mapping[str, str | None]]:
        try:
            body, headers = facts.fetch(cik, max_response_bytes=MAX_COMPANYFACTS_BYTES)
        except Exception as exc:
            raise BroadSecError(classify_fetch_error(exc), str(exc)) from exc
        meta = dict(headers)
        if "as_of" in meta:
            raise BroadSecError("source_binding_failure", "Company Facts headers must not carry as_of")
        return body, meta

    def fetch_master_index(year: int, quarter: int) -> tuple[bytes, Mapping[str, str | None]]:
        dest = Path(scratch_root) / f"master-{year}-Q{quarter}.zip"
        try:
            body, headers = submissions.retrieve_full_master_index(
                year,
                quarter,
                dest_path=dest,
                max_archive_bytes=MAX_MASTER_INDEX_ZIP_BYTES,
            )
        except SecResponseTooLarge as exc:
            raise BroadSecError("edgar_index_too_large", str(exc)) from exc
        except Exception as exc:
            reason = classify_fetch_error(exc)
            mapped = "edgar_index_unavailable"
            if reason == "response_too_large":
                mapped = "edgar_index_too_large"
            elif reason == "source_binding_failure":
                mapped = "source_binding_failure"
            raise BroadSecError(mapped, str(exc)) from exc
        return body, dict(headers)

    return fetch_submissions, fetch_companyfacts, fetch_master_index


def open_store(local_dir: Path | None) -> BroadSecStore:
    if local_dir is not None:
        return LocalStore(local_dir)
    from engine.research_vault.r2_store import build_store

    store = build_store()
    if store is None:
        raise BroadSecError("store_write_failure", "no private store configured")
    return store  # type: ignore[return-value]
