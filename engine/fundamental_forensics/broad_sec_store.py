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
* ``retrieved_at`` — when the collector received the bytes
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
POINTER_MAX_BYTES = 16 * 1024
MAX_UNIVERSE_ISSUERS = 2500
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
    issuers: tuple[Issuer, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "universe_id": self.universe_id,
            "content_sha256": self.content_sha256,
            "issuer_count": self.issuer_count,
            "unique_ticker_count": self.unique_ticker_count,
            "unique_cik_count": self.unique_cik_count,
        }


@dataclass
class PollClocks:
    poll_started_at: str
    poll_completed_at: str
    recorded_at: str
    selection_cutoff_at: str
    recovery_from: str | None = None


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
    return f"{PREFIX}/runs/{run_id}.json"


def latest_observation_key() -> str:
    return f"{PREFIX}/latest-observation.json"


def latest_complete_key() -> str:
    return f"{PREFIX}/latest-complete.json"


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
        head, frac = text[:-1].split(".", 1)
        text = head + "Z"
        del frac
    if not _ISO_Z_RE.fullmatch(text):
        return None
    return text


def _max_iso(values: list[str | None]) -> str | None:
    present = [item for item in values if item]
    if not present:
        return None
    return max(present)


def load_universe(path: Path) -> UniverseBinding:
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
    return UniverseBinding(
        path=UNIVERSE_RELATIVE_PATH,
        universe_id=UNIVERSE_ID,
        content_sha256=sha256(raw).hexdigest(),
        issuer_count=len(issuers),
        unique_ticker_count=len(ticker_to_cik),
        unique_cik_count=len(cik_to_ticker),
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
    """Return (admitted relevant filings, withheld after cutoff, historical_required)."""
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
        if not isinstance(accession_raw, str) or not _ACCESSION_RE.fullmatch(accession_raw):
            continue
        form = forms[index]
        if form not in RELEVANT_FORMS:
            continue
        accepted = _parse_acceptance(acceptances[index])
        if accepted:
            accept_times.append(accepted)
        filing_date = filing_dates[index] if isinstance(filing_dates[index], str) else None
        if filing_date and not _DATE_RE.fullmatch(filing_date):
            filing_date = None
        report_date = report_dates[index] if isinstance(report_dates[index], str) else None
        if report_date and not _DATE_RE.fullmatch(report_date):
            report_date = None
        row = {
            "cik": cik,
            "ticker": ticker,
            "accession_number": accession_raw,
            "form": form,
            "filing_date": filing_date,
            "report_date": report_date,
            "acceptance_datetime": accepted,
            "primary_document": primaries[index] if isinstance(primaries[index], str) else None,
            "is_xbrl": bool(xbrl[index]) if isinstance(xbrl[index], (int, bool)) else None,
            "is_inline_xbrl": bool(inline[index]) if isinstance(inline[index], (int, bool)) else None,
        }
        if accepted and accepted > selection_cutoff_at:
            withheld.append(row)
            continue
        if recovery_from and accepted and accepted < recovery_from:
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


def _put_immutable(store: BroadSecStore, key: str, data: bytes) -> None:
    existing = store.get_bytes_strict(key)
    if existing == data:
        return
    if existing is not None:
        raise BroadSecError("store_write_failure", f"immutable key already holds different bytes: {key}")
    try:
        written = store.put_bytes_strict_conditional(
            key, data, expected_version=None, content_type="application/json"
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
        "universe": universe.to_dict() if universe is not None else {
            "path": UNIVERSE_RELATIVE_PATH,
            "universe_id": UNIVERSE_ID,
            "content_sha256": None,
            "issuer_count": 0,
            "unique_ticker_count": 0,
            "unique_cik_count": 0,
        },
        "coverage": coverage,
        "change_summary": change_summary,
        "failures": failures,
        "storage": {
            "prefix": PREFIX,
            "run_key": run_key(run_id),
            "latest_observation_key": latest_observation_key(),
            "latest_complete_key": latest_complete_key(),
        },
        "companyfacts_as_of_policy": "current_observed_snapshot",
    }


def run_broad_sec_poll(
    *,
    store: BroadSecStore,
    universe_path: Path,
    fetch_submissions: FetchBytes,
    fetch_companyfacts: FetchBytes,
    clocks: PollClocks,
    mode: str = "incremental",
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
    _require_iso_z(clocks.poll_completed_at, field="poll_completed_at")
    _require_iso_z(clocks.recorded_at, field="recorded_at")
    _require_iso_z(clocks.selection_cutoff_at, field="selection_cutoff_at")
    if clocks.recovery_from:
        _require_iso_z(clocks.recovery_from, field="recovery_from")

    coverage = {
        "expected_issuers": 0,
        "observed_issuers": 0,
        "failed_issuers": 0,
        "companyfacts_fetched": 0,
        "companyfacts_skipped_unchanged": 0,
        "companyfacts_bytes_fetched": 0,
    }
    change_summary = {
        "new_relevant_accessions": 0,
        "affected_issuers": 0,
        "objects_admitted": 0,
        "manifests_admitted": 0,
    }

    try:
        universe = load_universe(universe_path)
    except BroadSecError as exc:
        run_id = _build_run_id(
            mode=mode, poll_started_at=clocks.poll_started_at, universe_sha="invalid"
        )
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
    source_accepts: list[str | None] = []
    pending_facts: list[tuple[Issuer, dict[str, Any], str, Mapping[str, str | None], list[dict[str, Any]], dict[str, Any] | None]] = []

    for issuer in universe.issuers:
        try:
            body, headers = fetch_submissions(issuer.cik)
            url = _bind_sec_url(headers.get("url"), cik=issuer.cik, endpoint="submissions")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise BroadSecError("invalid_sec_json", f"{issuer.ticker} Submissions is not JSON") from exc
            if not isinstance(payload, dict):
                raise BroadSecError("invalid_sec_json", f"{issuer.ticker} Submissions is not an object")
            admitted, _withheld, historical_required = parse_relevant_filings(
                payload,
                cik=issuer.cik,
                ticker=issuer.ticker,
                selection_cutoff_at=clocks.selection_cutoff_at,
                recovery_from=clocks.recovery_from,
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
            prior_accessions = []
            if prior_manifest is not None:
                prior_accessions = [
                    item["accession_number"]
                    for item in prior_manifest.get("relevant_filings", [])
                    if isinstance(item, dict) and "accession_number" in item
                ]
            current_accessions = [item["accession_number"] for item in admitted]
            relevant_changed = prior_manifest is None or current_accessions != prior_accessions
            if historical_required:
                raise BroadSecError(
                    "historical_submissions_required",
                    f"{issuer.ticker} recovery window predates current Submissions.recent",
                )
            new_accessions = [item for item in admitted if item["accession_number"] not in prior_accessions]
            if relevant_changed:
                pending_facts.append(
                    (issuer, payload, submissions_sha, headers, admitted, prior_manifest)
                )
                change_summary["new_relevant_accessions"] += len(new_accessions)
            else:
                coverage["companyfacts_skipped_unchanged"] += 1
                coverage["observed_issuers"] += 1
                if prior_manifest is not None:
                    source_accepts.append(prior_manifest.get("sec_accepted_at"))
            del url
        except BroadSecError as exc:
            failures.append(
                IssuerFailure(issuer.ticker, issuer.cik, exc.reason_code, exc.detail)
            )
            coverage["failed_issuers"] += 1
        except Exception as exc:
            reason = classify_fetch_error(exc)
            failures.append(IssuerFailure(issuer.ticker, issuer.cik, reason, str(exc)))
            coverage["failed_issuers"] += 1

    change_summary["affected_issuers"] = len(pending_facts)
    overflow = False
    if len(pending_facts) > max_affected_issuers:
        overflow = True
        failures.append(
            IssuerFailure(
                "",
                "",
                "queue_overflow",
                f"{len(pending_facts)} issuers need Company Facts; cap is {max_affected_issuers}",
            )
        )
        pending_facts = []

    facts_bytes = 0
    for issuer, _payload, submissions_sha, sub_headers, admitted, prior_manifest in pending_facts:
        try:
            facts_body, facts_headers = fetch_companyfacts(issuer.cik)
            _bind_sec_url(facts_headers.get("url"), cik=issuer.cik, endpoint="companyfacts")
            try:
                facts_payload = json.loads(facts_body)
            except json.JSONDecodeError as exc:
                raise BroadSecError("invalid_sec_json", f"{issuer.ticker} Company Facts is not JSON") from exc
            if not isinstance(facts_payload, dict):
                raise BroadSecError("invalid_sec_json", f"{issuer.ticker} Company Facts is not an object")
            if "as_of" in facts_payload or facts_headers.get("as_of"):
                raise BroadSecError(
                    "source_binding_failure",
                    "Company Facts must not be labelled historical as-of",
                )
            facts_bytes += len(facts_body)
            if facts_bytes > max_companyfacts_bytes_per_run:
                raise BroadSecError(
                    "queue_overflow",
                    f"Company Facts byte budget exceeded ({facts_bytes} > {max_companyfacts_bytes_per_run})",
                )
            facts_sha, facts_created = admit_source_bytes(store, facts_body)
            if facts_created:
                change_summary["objects_admitted"] += 1
            coverage["companyfacts_fetched"] += 1
            coverage["companyfacts_bytes_fetched"] = facts_bytes
            previous_id = prior_manifest["manifest_id"] if prior_manifest else None
            retrieved_at = sub_headers.get("retrieved_at") or clocks.recorded_at
            manifest = {
                "schema": MANIFEST_SCHEMA,
                "cik": issuer.cik,
                "ticker": issuer.ticker,
                "submissions_sha256": submissions_sha,
                "submissions_url": endpoint_url(issuer.cik, "submissions"),
                "submissions_object_key": object_key(submissions_sha),
                "companyfacts_sha256": facts_sha,
                "companyfacts_url": endpoint_url(issuer.cik, "companyfacts"),
                "companyfacts_object_key": object_key(facts_sha),
                "companyfacts_snapshot_kind": "current_observed",
                "relevant_filings": admitted,
                "previous_manifest_id": previous_id,
                "retrieved_at": retrieved_at,
                "recorded_at": clocks.recorded_at,
                "sec_accepted_at": _max_iso(
                    [item.get("acceptance_datetime") for item in admitted]
                ),
                "filed_on": max(
                    (item["filing_date"] for item in admitted if item.get("filing_date")),
                    default=None,
                ),
            }
            if "as_of" in manifest:
                raise BroadSecError("source_binding_failure", "issuer manifest must not carry as_of")
            manifest_id = issuer_source_identity(manifest)
            manifest["manifest_id"] = manifest_id
            encoded = canonical_json(manifest).encode("utf-8")
            _put_immutable(store, issuer_manifest_key(issuer.cik, manifest_id), encoded)
            change_summary["manifests_admitted"] += 1
            pointer = {
                "schema": "fundamental_forensics.broad_sec.issuer_latest.v1",
                "cik": issuer.cik,
                "ticker": issuer.ticker,
                "manifest_id": manifest_id,
                "manifest_key": issuer_manifest_key(issuer.cik, manifest_id),
                "submissions_sha256": submissions_sha,
                "companyfacts_sha256": facts_sha,
            }
            _put_pointer(store, issuer_latest_key(issuer.cik), pointer)
            coverage["observed_issuers"] += 1
            source_accepts.append(manifest.get("sec_accepted_at"))
        except BroadSecError as exc:
            if exc.reason_code == "queue_overflow":
                overflow = True
            failures.append(
                IssuerFailure(issuer.ticker, issuer.cik, exc.reason_code, exc.detail)
            )
            coverage["failed_issuers"] += 1
        except Exception as exc:
            reason = classify_fetch_error(exc)
            failures.append(IssuerFailure(issuer.ticker, issuer.cik, reason, str(exc)))
            coverage["failed_issuers"] += 1

    latest_source = _max_iso(source_accepts)
    complete = coverage["failed_issuers"] == 0 and not overflow and coverage["observed_issuers"] == universe.issuer_count
    if overflow and not any(item.reason_code == "queue_overflow" for item in failures):
        failures.append(
            IssuerFailure("", "", "queue_overflow", "Company Facts queue exceeded its hard bound")
        )
    if complete:
        status = "complete"
        reason_code = "complete"
        exit_code = 0
    elif coverage["observed_issuers"] > 0:
        status = "degraded"
        reason_code = failures[0].reason_code if failures else "store_write_failure"
        exit_code = 1
    else:
        status = "failed"
        reason_code = failures[0].reason_code if failures else "store_write_failure"
        exit_code = 1

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
    )
    encoded_receipt = canonical_json(receipt).encode("utf-8")
    try:
        _put_immutable(store, run_key(run_id), encoded_receipt)
        if complete:
            _put_pointer(store, latest_complete_key(), receipt)
        _put_pointer(store, latest_observation_key(), receipt)
    except BroadSecError as exc:
        receipt["status"] = "failed"
        receipt["reason_code"] = exc.reason_code
        receipt["failures"] = list(receipt["failures"]) + [
            {"ticker": "", "cik": "", "reason_code": exc.reason_code, "detail": exc.detail}
        ]
        try:
            _put_pointer(store, latest_observation_key(), receipt)
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
    retrieved_at: str,
) -> tuple[FetchBytes, FetchBytes]:
    from collectors.edgar_forensics import SecForensicsCollector
    from collectors.fundamental_forensics_companyfacts import SecCompanyFactsCollector

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
        meta = dict(headers)
        meta["retrieved_at"] = retrieved_at
        return body, meta

    def fetch_companyfacts(cik: str) -> tuple[bytes, Mapping[str, str | None]]:
        try:
            body, headers = facts.fetch(cik, max_response_bytes=MAX_COMPANYFACTS_BYTES)
        except Exception as exc:
            raise BroadSecError(classify_fetch_error(exc), str(exc)) from exc
        meta = dict(headers)
        meta["retrieved_at"] = retrieved_at
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
