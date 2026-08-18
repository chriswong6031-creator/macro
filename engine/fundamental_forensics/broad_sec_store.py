"""Incremental broad SEC source plane for Filing Forensics (FF-1).

Polls Submissions for every issuer in ``data/edgar/fundamentals.parquet``,
admits exact SEC bytes into a private content-addressed store, and fetches
Company Facts only when that issuer's relevant periodic filing state changes.

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
from hashlib import sha256
import gzip
import io
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlparse

from collectors.edgar_forensics import (
    SecResponseTooLarge,
    _canonical_cik,
    endpoint_url,
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
    }
)
_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
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
) -> dict[str, Any] | None:
    pointer = _read_json(store, recovery_continuation_pointer_key(), maximum_bytes=POINTER_MAX_BYTES)
    if pointer is None:
        return None
    if pointer.get("recovery_from") != recovery_from or pointer.get("universe_sha256") != universe_sha:
        return None
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
) -> None:
    body = {
        "schema": CONTINUATION_SCHEMA,
        "recovery_from": recovery_from,
        "universe_sha256": universe_sha,
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
) -> PollResult:
    if mode not in {"incremental", "recovery"}:
        raise ValueError("mode must be incremental or recovery")
    if mode == "recovery" and not clocks.recovery_from:
        raise BroadSecError("universe_invalid", "recovery requires recovery_from")
    if mode == "incremental" and clocks.recovery_from:
        raise BroadSecError("universe_invalid", "incremental mode cannot carry a recovery window")
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
    failures: list[IssuerFailure] = []
    observations: list[dict[str, Any]] = []
    prepared: list[dict[str, Any]] = []
    source_accepts: list[str | None] = []
    continuation = None
    continuation_pointer = _read_json(
        store, recovery_continuation_pointer_key(), maximum_bytes=POINTER_MAX_BYTES
    )
    outstanding_backlog = (
        continuation_pointer is not None
        and continuation_pointer.get("universe_sha256") == universe.content_sha256
        and int(continuation_pointer.get("pending_count") or 0) > 0
    )
    if mode == "recovery" and clocks.recovery_from:
        continuation = _load_continuation(
            store, recovery_from=clocks.recovery_from, universe_sha=universe.content_sha256
        )
    continuation_completed = set(continuation.get("completed_ciks", []) if continuation else [])
    continuation_pending = set(continuation.get("pending_ciks", []) if continuation else [])

    for issuer in universe.issuers:
        observation: dict[str, Any] = {
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
        }
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
            new_accessions = [acc for acc in current_accessions if acc not in prior_ledger]
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
                needs_facts = prior_manifest is not None and bool(new_accessions)
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

    facts_candidates = [item for item in prepared if item["needs_facts"]]
    facts_candidates.sort(key=lambda item: (item["issuer"].ticker, item["issuer"].cik))
    change_summary["affected_issuers"] = len(facts_candidates)
    overflow = False
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    if mode == "incremental" and (
        len(facts_candidates) > max_affected_issuers or outstanding_backlog
    ):
        overflow = True
        deferred = list(facts_candidates)
        failures.append(
            IssuerFailure(
                "",
                "",
                "queue_overflow",
                (
                    f"{len(facts_candidates)} issuers need Company Facts; "
                    f"incremental cap is {max_affected_issuers}"
                    + ("; recovery continuation is outstanding" if outstanding_backlog else "")
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
    if mode == "incremental" and outstanding_backlog:
        coverage["recovery_backlog"] = max(
            coverage["recovery_backlog"],
            int(continuation_pointer.get("pending_count") or 0),
        )

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

            cumulative = list(dict.fromkeys([*item["prior_ledger"], *item["new_accessions"]]))
            if not cumulative:
                cumulative = [
                    row["accession_number"]
                    for row in item["admitted"]
                    if isinstance(row.get("accession_number"), str)
                ]
            else:
                for acc in item["admitted"]:
                    number = acc.get("accession_number")
                    if isinstance(number, str) and number not in cumulative:
                        cumulative.append(number)
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
            prepared_ok = item
            del prepared_ok
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
        )
        completed_ciks = sorted(
            (
                continuation_completed
                | {
                    item["issuer"].cik
                    for item in prepared
                    if item["observation"].get("companyfacts_fetched")
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
    )
    encoded_receipt = canonical_json(receipt).encode("utf-8")
    census_complete = status == "complete" and universe.canonical and exit_code == 0
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
) -> tuple[FetchBytes, FetchBytes]:
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

    return fetch_submissions, fetch_companyfacts


def open_store(local_dir: Path | None) -> BroadSecStore:
    if local_dir is not None:
        return LocalStore(local_dir)
    from engine.research_vault.r2_store import build_store

    store = build_store()
    if store is None:
        raise BroadSecError("store_write_failure", "no private store configured")
    return store  # type: ignore[return-value]
