"""Bounded SEC Company Facts evidence intake for Capital Structure Intelligence.

This is a source-plane collector, deliberately separate from the filing-document
``capital_structure.source_manifest/v1``.  It admits an issuer only after a
verified Capital Structure *complete-submission* manifest anchors that CIK,
retains one exact Company Facts JSON response by SHA-256, and publishes a
telemetry-last coverage receipt.  It does not parse facts into observations or
write the share-count ledger; that later consumer must bind this manifest.

The scheduler serializes this adapter with the other SEC adapters.  A local
100ms floor remains here as a second, process-local fair-access guard.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import logging
import math
import os
from pathlib import Path
import time
from typing import Any

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from engine.capital_structure.source_identity import (
    validate_manifest_identity,
    validate_manifest_ledger,
)
from engine.capital_structure.source_store import object_key_for_sha256


log = logging.getLogger(__name__)

GROUP = "capital_structure"
POLICY_VERSION = "capital-structure-companyfacts-intake/1.0.0"
SEC_DATA_ORIGIN = "https://data.sec.gov"
MAX_CIKS_PER_RUN = 24
HARD_MAX_CIKS_PER_RUN = 64
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
HARD_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
REFRESH_AFTER = timedelta(days=7)
RETRY_AFTER = timedelta(hours=1)
DEFER_AFTER = timedelta(hours=24)
PACE_SECONDS = 0.12
MAX_ATTEMPTS = 3

SOURCE_MANIFEST_SCHEMA = "capital_structure.companyfacts_source_manifest/v1"
COVERAGE_ROW_SCHEMA = "capital_structure.companyfacts_coverage_row/v1"
COVERAGE_RECEIPT_SCHEMA = "capital_structure.companyfacts_coverage_receipt/v1"

_SOURCE_MANIFEST_COLUMNS = [
    "schema", "manifest_id", "source_system", "source_id", "issuer", "anchor",
    "request", "retrieval", "content", "storage", "rights", "privacy", "parser",
    "spans", "authority",
]
_COVERAGE_COLUMNS = [
    "schema", "coverage_id", "cik", "anchor_manifest_id", "anchor_first_seen_at",
    "attempted_at", "attempt_count", "queue_reason", "state", "retry_after", "error",
    "result",
]

_NONCLAIMS = [
    "No Company Facts value is interpreted, normalized, or added to a share-count ledger by this intake lane.",
    "No outstanding-share, public-float, fully-diluted-share, capacity, or dilution estimate is produced.",
    "No instrument, shelf, ATM, warrant, convertible, cash-runway, or financing-state assertion is produced.",
    "No risk score, offering probability, rank, sizing, entry, exit, alert, or Prophet authority is granted.",
    "A Company Facts response is current-source evidence, not historical SEC availability or point-in-time share-count proof.",
    "Only CIKs with verified Capital Structure complete-submission anchors are in scope; this is not market-wide Company Facts coverage.",
]


class CompanyFactsIntakeError(RuntimeError):
    """The bounded Company Facts source intake cannot safely continue."""


class CompanyFactsResponseTooLarge(CompanyFactsIntakeError):
    """The SEC response exceeded its declared or streamed byte ceiling."""


class CompanyFactsDeferred(CompanyFactsIntakeError):
    """A data-level error should remain visible and retry later, not become a fact."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _data_root() -> Path:
    from lib import config

    return config.data_dir() / GROUP / "companyfacts"


def _ua() -> str:
    try:
        from collectors.edgar import _cfg

        return _cfg()["user_agent"]
    except Exception:  # noqa: BLE001
        return "Macro Dashboard research longr2512@gmail.com"


def canonical_cik(value: object) -> str:
    """Return a strict zero-padded SEC CIK without consulting any universe."""
    raw = str(value or "").strip()
    if not raw.isdigit() or len(raw) > 10:
        raise CompanyFactsDeferred(f"invalid CIK: {value!r}")
    return raw.zfill(10)


def companyfacts_url(cik: object) -> str:
    return f"{SEC_DATA_ORIGIN}/api/xbrl/companyfacts/CIK{canonical_cik(cik)}.json"


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _native(value: Any) -> Any:
    """Normalize Parquet nested values before identity/hash comparisons."""
    if isinstance(value, Mapping):
        return {str(key): _native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_native(item) for item in value]
    tolist = getattr(value, "tolist", None)
    if callable(tolist) and not isinstance(value, (str, bytes, bytearray)):
        try:
            return _native(tolist())
        except Exception:  # noqa: BLE001
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes, bytearray)):
        try:
            return item()
        except Exception:  # noqa: BLE001
            pass
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [_native(record) for record in frame.to_dict(orient="records")]


def _read_ledger(path: Path, columns: Sequence[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(columns))
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        raise CompanyFactsIntakeError(f"unreadable Company Facts ledger {path}: {exc}") from exc
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise CompanyFactsIntakeError(f"Company Facts ledger {path} lacks columns: {', '.join(missing)}")
    return frame[list(columns)]


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _encoded_parquet(frame: pd.DataFrame, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{time.time_ns()}.tmp")
    frame.to_parquet(temporary, index=False)
    # Ensure no partial/unsupported serializer result is published.
    pd.read_parquet(temporary)
    return temporary


def _write_ledger_pair(
    *, source_manifests: pd.DataFrame, coverage: pd.DataFrame, root: Path, receipt_path: Path, receipt: dict[str, Any]
) -> None:
    """Publish both ledgers before the receipt; no stale receipt can survive a failed pair."""
    manifest_path = root / "source_manifest.parquet"
    coverage_path = root / "coverage.parquet"
    receipt_path.unlink(missing_ok=True)
    manifest_tmp = _encoded_parquet(source_manifests, manifest_path)
    coverage_tmp = _encoded_parquet(coverage, coverage_path)
    try:
        os.replace(manifest_tmp, manifest_path)
        os.replace(coverage_tmp, coverage_path)
    finally:
        manifest_tmp.unlink(missing_ok=True)
        coverage_tmp.unlink(missing_ok=True)
    # Read the published pair back before writing the consumer-visible receipt.
    published_manifests = _read_ledger(manifest_path, _SOURCE_MANIFEST_COLUMNS)
    published_coverage = _read_ledger(coverage_path, _COVERAGE_COLUMNS)
    expected_manifests = receipt["companyfacts_manifest_ledger"]
    expected_coverage = receipt["coverage_ledger"]
    if _ledger_receipt(_records(published_manifests)) != expected_manifests:
        raise CompanyFactsIntakeError("published Company Facts manifest ledger read-back mismatch")
    if _ledger_receipt(_records(published_coverage)) != expected_coverage:
        raise CompanyFactsIntakeError("published Company Facts coverage ledger read-back mismatch")
    _atomic_write_bytes(receipt_path, _canonical_bytes(receipt) + b"\n")
    if receipt_path.read_bytes() != _canonical_bytes(receipt) + b"\n":
        raise CompanyFactsIntakeError("Company Facts coverage receipt read-back mismatch")


def _ledger_receipt(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Hash an immutable logical prefix in canonical identity order."""
    canonical = sorted(_canonical_bytes(dict(record)) for record in records)
    digest = sha256(b"".join(chunk + b"\n" for chunk in canonical)).hexdigest()
    return {"record_count": len(canonical), "prefix_sha256": digest, "immutable_prefix": True}


def _authority() -> dict[str, bool]:
    return {
        "is_context_only": True,
        "share_count_ledger_authority": False,
        "instrument_authority": False,
        "capacity_authority": False,
        "runway_authority": False,
        "risk_authority": False,
        "rank_authority": False,
        "sizing_authority": False,
        "entry_authority": False,
        "prophet_authority": False,
    }


def _validate_contract(record: Mapping[str, Any], filename: str, *, label: str) -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    schema_path = Path(__file__).resolve().parents[1] / "contracts" / filename
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record),
        key=lambda error: list(error.path),
    )
    if errors:
        joined = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:5]
        )
        raise CompanyFactsIntakeError(f"{label} contract violation: {joined}")


def _source_manifest_id(record: Mapping[str, Any]) -> str:
    material = {key: value for key, value in record.items() if key != "manifest_id"}
    return "manifest:cs-companyfacts:" + sha256(_canonical_bytes(material)).hexdigest()


def _coverage_id(record: Mapping[str, Any]) -> str:
    material = {key: value for key, value in record.items() if key != "coverage_id"}
    return "coverage:cs-companyfacts:" + sha256(_canonical_bytes(material)).hexdigest()


def _receipt_id(record: Mapping[str, Any]) -> str:
    material = {key: value for key, value in record.items() if key != "receipt_id"}
    return "receipt:cs-companyfacts:" + sha256(_canonical_bytes(material)).hexdigest()


def _parse_stamp(value: object, *, field: str) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise CompanyFactsIntakeError(f"invalid {field}: {value!r}")
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _verified_complete_submission_anchors(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Collapse only verified complete-submission manifests to one anchor per CIK."""
    if records:
        # Existing filing manifests retain their own strict immutable identity law.
        validate_manifest_ledger([dict(record) for record in records])
    candidates: list[dict[str, Any]] = []
    for raw in records:
        record = _native(raw)
        issuer = record.get("issuer") if isinstance(record.get("issuer"), Mapping) else {}
        document = record.get("document") if isinstance(record.get("document"), Mapping) else {}
        retrieval = record.get("retrieval") if isinstance(record.get("retrieval"), Mapping) else {}
        storage = record.get("storage") if isinstance(record.get("storage"), Mapping) else {}
        parser = record.get("parser") if isinstance(record.get("parser"), Mapping) else {}
        if document.get("document_role") != "complete_submission":
            continue
        if retrieval.get("transport_status") != "retrieved":
            continue
        if parser.get("eligibility") != "eligible" or parser.get("corruption_state") != "clean":
            continue
        digest = str(document.get("content_sha256") or "").lower()
        if len(digest) != 64 or document.get("root_locator") != f"sha256:{digest}":
            continue
        if storage.get("content_addressed") is not True or storage.get("retention_state") != "retained":
            continue
        if storage.get("object_key") != object_key_for_sha256(digest):
            continue
        try:
            cik = canonical_cik(issuer.get("cik"))
            first_seen = _parse_stamp(retrieval.get("first_seen_at"), field="anchor first_seen_at")
        except CompanyFactsDeferred:
            continue
        manifest_id = str(record.get("manifest_id") or "")
        source_id = str(record.get("source_id") or "")
        if not manifest_id or not source_id:
            continue
        validate_manifest_identity(record)
        candidates.append({
            "cik": cik,
            "manifest_id": manifest_id,
            "source_id": source_id,
            "content_sha256": digest,
            "first_seen_at": first_seen,
            "ticker": issuer.get("ticker") if isinstance(issuer.get("ticker"), str) else None,
            "aliases": sorted({str(value) for value in issuer.get("aliases", []) if str(value)}),
        })
    anchors: dict[str, dict[str, Any]] = {}
    for candidate in sorted(candidates, key=lambda item: (item["cik"], item["first_seen_at"], item["manifest_id"])):
        anchors.setdefault(candidate["cik"], candidate)
    return anchors


def _latest_coverage(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for raw in records:
        record = _native(raw)
        _validate_contract(record, "capital_structure_companyfacts_coverage_row.schema.json", label="coverage row")
        cik = str(record["cik"])
        rank = (_parse_stamp(record["attempted_at"], field="coverage attempted_at"), str(record["coverage_id"]))
        prior = latest.get(cik)
        if prior is None or rank > (_parse_stamp(prior["attempted_at"], field="coverage attempted_at"), str(prior["coverage_id"])):
            latest[cik] = record
    return latest


def select_companyfacts_queue(
    anchors: Mapping[str, Mapping[str, Any]],
    coverage_records: Sequence[Mapping[str, Any]],
    *, now: datetime,
    max_ciks: int,
) -> tuple[list[dict[str, Any]], int, int]:
    """Return deterministic bounded work, delayed backlogs, and fresh captures.

    The two non-selected counters are deliberately separate: a still-fresh
    retrieved response is not backlog, while a retry/defer clock or the hard
    per-run cap is a visible deferred work item.
    """
    if isinstance(max_ciks, bool) or not isinstance(max_ciks, int) or not 0 <= max_ciks <= HARD_MAX_CIKS_PER_RUN:
        raise ValueError(f"max_ciks must be an integer from 0 to {HARD_MAX_CIKS_PER_RUN}")
    stamp = _parse_stamp(now, field="queue now")
    latest = _latest_coverage(coverage_records)
    candidates: list[dict[str, Any]] = []
    deferred = 0
    skipped_fresh = 0
    for cik in sorted(anchors):
        anchor = dict(anchors[cik])
        prior = latest.get(cik)
        reason: str | None = None
        priority = 2
        if prior is None:
            reason, priority = "new_anchor", 1
        elif prior["state"] in {"retry", "deferred"}:
            retry_after = _parse_stamp(prior["retry_after"], field="coverage retry_after")
            if retry_after <= stamp:
                reason, priority = "retry_due", 0
            else:
                deferred += 1
        elif prior["state"] == "retrieved":
            attempted = _parse_stamp(prior["attempted_at"], field="coverage attempted_at")
            if attempted + REFRESH_AFTER <= stamp:
                reason, priority = "refresh_due", 2
            else:
                skipped_fresh += 1
        else:  # Contract excludes this, preserve a fail-closed queue.
            raise CompanyFactsIntakeError(f"unknown coverage state for {cik}")
        if reason:
            candidates.append({
                "cik": cik,
                "anchor": anchor,
                "queue_reason": reason,
                "priority": priority,
                "attempt_count": int(prior["attempt_count"]) + 1 if prior else 1,
            })
    candidates.sort(key=lambda item: (item["priority"], item["anchor"]["first_seen_at"], item["cik"]))
    deferred += max(0, len(candidates) - max_ciks)
    return candidates[:max_ciks], deferred, skipped_fresh


def _response_content_length(headers: Any, *, url: str, limit: int) -> None:
    if not isinstance(headers, Mapping):
        return
    declared = headers.get("Content-Length", headers.get("content-length"))
    if declared is None:
        return
    try:
        value = int(str(declared).strip())
    except (TypeError, ValueError):
        return
    if value < 0 or value > limit:
        raise CompanyFactsResponseTooLarge(f"SEC Company Facts response exceeds bounded ingest limit for {url}")


def stream_companyfacts_response(response: Any, *, cik: str, url: str, limit: int) -> bytes:
    """Read a single response with cap enforcement before JSON/CIK admission."""
    _response_content_length(getattr(response, "headers", {}), url=url, limit=limit)
    iterator = getattr(response, "iter_content", None)
    if not callable(iterator):
        raise CompanyFactsIntakeError("SEC response does not support bounded iter_content")
    chunks: list[bytes] = []
    total = 0
    for chunk in iterator(chunk_size=64 * 1024):
        if not isinstance(chunk, bytes):
            raise CompanyFactsIntakeError("SEC response stream yielded non-bytes")
        if not chunk:
            continue
        total += len(chunk)
        if total > limit:
            raise CompanyFactsResponseTooLarge(f"SEC Company Facts response exceeds bounded ingest limit for {url}")
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        raise CompanyFactsDeferred("SEC Company Facts response is empty")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanyFactsDeferred("SEC Company Facts response is not UTF-8 JSON") from exc
    if not isinstance(payload, Mapping) or canonical_cik(payload.get("cik")) != cik:
        raise CompanyFactsDeferred("SEC Company Facts JSON CIK does not match requested CIK")
    if not isinstance(payload.get("facts"), Mapping):
        raise CompanyFactsDeferred("SEC Company Facts JSON has no facts object")
    return raw


def _response_error_class(exc: Exception) -> tuple[str, timedelta]:
    if isinstance(exc, (CompanyFactsResponseTooLarge, CompanyFactsDeferred, ValueError)):
        return "deferred", DEFER_AFTER
    return "retry", RETRY_AFTER


class SecCapitalStructureCompanyFactsAdapter(Adapter):
    """Fetch bounded, anchored SEC Company Facts source evidence only."""

    name = "sec_capital_structure_companyfacts"
    group = GROUP
    stale_after_days = 4

    def __init__(
        self,
        *,
        source_store=None,
        now_fn: Callable[[], datetime] = _utc_now,
        fetcher: Callable[..., Any] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        max_ciks_per_run: int = MAX_CIKS_PER_RUN,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        self._injected_source_store = source_store
        self._now_fn = now_fn
        self._fetcher = fetcher or requests.get
        self._sleep = sleeper
        self._monotonic = monotonic
        self._last_request_at: float | None = None
        self.max_ciks_per_run = int(max_ciks_per_run)
        self.max_response_bytes = int(max_response_bytes)
        if not 0 <= self.max_ciks_per_run <= HARD_MAX_CIKS_PER_RUN:
            raise ValueError(f"max_ciks_per_run must be from 0 to {HARD_MAX_CIKS_PER_RUN}")
        if not 1 <= self.max_response_bytes <= HARD_MAX_RESPONSE_BYTES:
            raise ValueError(f"max_response_bytes must be from 1 to {HARD_MAX_RESPONSE_BYTES}")

    def _source_store(self):
        if self._injected_source_store is not None:
            return self._injected_source_store
        from engine.capital_structure.source_store import build_source_store

        return build_source_store()

    def _pace(self) -> None:
        if self._last_request_at is None:
            return
        remaining = PACE_SECONDS - (self._monotonic() - self._last_request_at)
        if remaining > 0:
            self._sleep(remaining)

    @staticmethod
    def _close(response: Any) -> None:
        closer = getattr(response, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass

    def _fetch_companyfacts(self, cik: str) -> bytes:
        url = companyfacts_url(cik)
        headers = {"User-Agent": _ua(), "Accept-Encoding": "gzip, deflate"}
        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            response = None
            try:
                self._pace()
                response = self._fetcher(url, headers=headers, timeout=45, stream=True)
                self._last_request_at = self._monotonic()
                status = getattr(response, "status_code", None)
                if not isinstance(status, int):
                    raise CompanyFactsIntakeError("SEC response has no integer HTTP status")
                if status in {429, 500, 502, 503, 504}:
                    raise requests.HTTPError(f"HTTP {status}", response=response)
                if status != 200:
                    raise CompanyFactsDeferred(f"SEC Company Facts HTTP {status}")
                return stream_companyfacts_response(
                    response, cik=cik, url=url, limit=self.max_response_bytes
                )
            except (CompanyFactsDeferred, CompanyFactsResponseTooLarge):
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt + 1 >= MAX_ATTEMPTS or not (
                    is_connection_error(exc) or isinstance(exc, requests.RequestException)
                ):
                    raise
                self._sleep(0.5 * (attempt + 1))
            finally:
                if response is not None:
                    self._close(response)
        raise last_error or CompanyFactsIntakeError("Company Facts fetch failed")

    @staticmethod
    def _source_manifest(*, cik: str, anchor: Mapping[str, Any], raw: bytes, receipt: Any, retained_at: str) -> dict[str, Any]:
        digest = sha256(raw).hexdigest()
        if (
            getattr(receipt, "sha256", None) != digest
            or getattr(receipt, "byte_length", None) != len(raw)
            or getattr(receipt, "object_key", None) != object_key_for_sha256(digest)
            or getattr(receipt, "media_type", None) != "application/json"
        ):
            raise CompanyFactsIntakeError("source-store receipt does not bind exact Company Facts bytes")
        ticker = anchor.get("ticker") if isinstance(anchor.get("ticker"), str) else None
        aliases = [str(value) for value in anchor.get("aliases", []) if str(value)]
        record: dict[str, Any] = {
            "schema": SOURCE_MANIFEST_SCHEMA,
            "source_system": "sec_edgar_companyfacts",
            "source_id": f"sec-companyfacts:{cik}:{digest}",
            "issuer": {"issuer_id": f"sec:cik:{cik}", "cik": cik, "ticker": ticker, "aliases": sorted(set(aliases))},
            "anchor": {
                "capital_structure_manifest_id": anchor["manifest_id"],
                "capital_structure_source_id": anchor["source_id"],
                "complete_submission_sha256": anchor["content_sha256"],
                "first_seen_at": _iso(anchor["first_seen_at"]),
            },
            "request": {"canonical_url": companyfacts_url(cik), "endpoint": "companyfacts", "method": "GET"},
            "retrieval": {"retrieved_at": retained_at, "first_seen_at": retained_at, "transport_status": "retrieved"},
            "content": {"media_type": "application/json", "byte_length": len(raw), "content_sha256": digest, "root_locator": f"sha256:{digest}"},
            "storage": {"backend": receipt.backend, "store_id": receipt.store_id, "object_key": receipt.object_key, "content_addressed": True, "retention_state": "retained"},
            "rights": {"redistribution_class": "public_source_link", "attribution_required": True, "license_note": "United States SEC EDGAR public Company Facts response"},
            "privacy": {"classification": "public", "contains_personal_data": False},
            "parser": {"eligibility": "eligible", "corruption_state": "clean", "parser_version": "companyfacts-json-cik-validator/1.0.0"},
            "spans": [{"span_id": f"root:{digest}", "locator_type": "document", "locator": f"bytes:0-{len(raw)}", "text_sha256": digest}],
            "authority": _authority(),
        }
        record["manifest_id"] = _source_manifest_id(record)
        _validate_contract(record, "capital_structure_companyfacts_source_manifest.schema.json", label="Company Facts source manifest")
        return record

    @staticmethod
    def _coverage_row(
        *, item: Mapping[str, Any], attempted_at: str, state: str, error: str | None, retry_after: str | None,
        manifest: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        content = manifest.get("content") if isinstance(manifest, Mapping) else None
        record: dict[str, Any] = {
            "schema": COVERAGE_ROW_SCHEMA,
            "cik": item["cik"],
            "anchor_manifest_id": item["anchor"]["manifest_id"],
            "anchor_first_seen_at": _iso(item["anchor"]["first_seen_at"]),
            "attempted_at": attempted_at,
            "attempt_count": item["attempt_count"],
            "queue_reason": item["queue_reason"],
            "state": state,
            "retry_after": retry_after,
            "error": error,
            "result": {
                "source_manifest_id": manifest.get("manifest_id") if manifest else None,
                "content_sha256": content.get("content_sha256") if isinstance(content, Mapping) else None,
                "byte_length": content.get("byte_length") if isinstance(content, Mapping) else None,
            },
        }
        record["coverage_id"] = _coverage_id(record)
        _validate_contract(record, "capital_structure_companyfacts_coverage_row.schema.json", label="Company Facts coverage row")
        return record

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Collect at most one current Company Facts response per eligible anchored CIK.

        ``full_history`` only bypasses the seven-day freshness gate. It never expands
        beyond the current verified filing-manifest CIK set or the hard queue ceiling.
        """
        root = _data_root()
        anchor_path = root.parent / "source_manifest.parquet"
        manifests_path = root / "source_manifest.parquet"
        coverage_path = root / "coverage.parquet"
        receipt_path = root / "coverage_receipt.json"
        anchor_frame = _read_ledger(anchor_path, [
            "schema", "manifest_id", "source_system", "source_id", "issuer", "filing", "document",
            "retrieval", "storage", "rights", "privacy", "parser", "spans",
        ])
        anchor_records = _records(anchor_frame)
        anchors = _verified_complete_submission_anchors(anchor_records)
        manifests = _read_ledger(manifests_path, _SOURCE_MANIFEST_COLUMNS)
        coverage = _read_ledger(coverage_path, _COVERAGE_COLUMNS)
        existing_manifests = _records(manifests)
        for record in existing_manifests:
            _validate_contract(record, "capital_structure_companyfacts_source_manifest.schema.json", label="retained Company Facts source manifest")
        coverage_records = _records(coverage)
        now = self._now_fn().astimezone(timezone.utc)
        if full_history:
            # Preserve the universe/cap boundary; force due rows only by making previous
            # successful captures old for this selection, never by discovering new CIKs.
            rewritten: list[dict[str, Any]] = []
            for record in coverage_records:
                clone = dict(record)
                if clone.get("state") == "retrieved":
                    clone["attempted_at"] = _iso(now - REFRESH_AFTER - timedelta(seconds=1))
                rewritten.append(clone)
            queue_records = rewritten
        else:
            queue_records = coverage_records
        queue, deferred_queue_count, skipped_fresh_count = select_companyfacts_queue(
            anchors, queue_records, now=now, max_ciks=self.max_ciks_per_run
        )
        source_store = self._source_store()
        fresh_manifests: list[dict[str, Any]] = []
        fresh_coverage: list[dict[str, Any]] = []
        counts = {"retrieved": 0, "retry": 0, "deferred": 0}
        for item in queue:
            attempted = self._now_fn().astimezone(timezone.utc)
            attempted_at = _iso(attempted)
            try:
                if source_store is None:
                    raise RuntimeError("content-addressed source store unavailable")
                raw = self._fetch_companyfacts(item["cik"])
                receipt = source_store.put_verified(raw, media_type="application/json")
                if receipt is None:
                    raise RuntimeError("source-store write/readback verification failed")
                retained_at = _iso(self._now_fn().astimezone(timezone.utc))
                manifest = self._source_manifest(
                    cik=item["cik"], anchor=item["anchor"], raw=raw, receipt=receipt, retained_at=retained_at
                )
                fresh_manifests.append(manifest)
                fresh_coverage.append(self._coverage_row(
                    item=item, attempted_at=attempted_at, state="retrieved", error=None, retry_after=None, manifest=manifest
                ))
                counts["retrieved"] += 1
            except Exception as exc:  # noqa: BLE001
                state, delay = _response_error_class(exc)
                retry_after = _iso(attempted + delay)
                error = f"{type(exc).__name__}: {exc}"[:500]
                log.warning("sec_capital_structure_companyfacts: %s %s: %s", item["cik"], state, error)
                fresh_coverage.append(self._coverage_row(
                    item=item, attempted_at=attempted_at, state=state, error=error, retry_after=retry_after, manifest=None
                ))
                counts[state] += 1

        combined_manifests = _append_immutable(
            existing_manifests, fresh_manifests, key="manifest_id", label="Company Facts source manifest"
        )
        combined_coverage = _append_immutable(
            coverage_records, fresh_coverage, key="coverage_id", label="Company Facts coverage row"
        )
        manifest_frame = pd.DataFrame(combined_manifests, columns=_SOURCE_MANIFEST_COLUMNS)
        coverage_frame = pd.DataFrame(combined_coverage, columns=_COVERAGE_COLUMNS)
        receipt = _coverage_receipt(
            now=now,
            anchor_records=anchor_records,
            source_records=combined_manifests,
            coverage_records=combined_coverage,
            eligible_ciks=len(anchors),
            queue=queue,
            max_ciks=self.max_ciks_per_run,
            deferred_queue_count=deferred_queue_count,
            skipped_fresh_count=skipped_fresh_count,
            counts=counts,
        )
        _validate_contract(receipt, "capital_structure_companyfacts_coverage_receipt.schema.json", label="Company Facts coverage receipt")
        _write_ledger_pair(
            source_manifests=manifest_frame, coverage=coverage_frame, root=root,
            receipt_path=receipt_path, receipt=receipt,
        )
        heartbeat = pd.DataFrame({
            "eligible_ciks": [len(anchors)], "selected": [len(queue)], "retrieved": [counts["retrieved"]],
            "retry": [counts["retry"]], "deferred": [counts["deferred"] + deferred_queue_count],
        }, index=[pd.Timestamp(now.date())])
        return {"sec_companyfacts_intake": heartbeat}


def _append_immutable(
    prior: Sequence[Mapping[str, Any]], fresh: Sequence[Mapping[str, Any]], *, key: str, label: str
) -> list[dict[str, Any]]:
    """Append exact records only; a collision with different bytes is fatal.

    Physical prior-row order is preserved (then only new rows are appended) so
    operational readers can retain a monotone ledger view.  The receipt itself
    hashes canonical identity order and is therefore not sensitive to Parquet
    row ordering.
    """
    seen: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for raw in [*prior, *fresh]:
        record = _native(raw)
        identity = str(record.get(key) or "")
        if not identity:
            raise CompanyFactsIntakeError(f"{label} has no {key}")
        previous = seen.get(identity)
        if previous is not None and _canonical_bytes(previous) != _canonical_bytes(record):
            raise CompanyFactsIntakeError(f"{label} immutable identity collision: {identity}")
        if previous is None:
            seen[identity] = record
            out.append(record)
    return out


def _coverage_receipt(
    *, now: datetime, anchor_records: Sequence[Mapping[str, Any]], source_records: Sequence[Mapping[str, Any]],
    coverage_records: Sequence[Mapping[str, Any]], eligible_ciks: int, queue: Sequence[Mapping[str, Any]], max_ciks: int,
    deferred_queue_count: int, skipped_fresh_count: int, counts: Mapping[str, int],
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema": COVERAGE_RECEIPT_SCHEMA,
        "as_of": _iso(now),
        "policy_version": POLICY_VERSION,
        "status": "ok" if eligible_ciks else "no_eligible_anchors",
        "anchor_manifest_ledger": _ledger_receipt(anchor_records),
        "companyfacts_manifest_ledger": _ledger_receipt(source_records),
        "coverage_ledger": _ledger_receipt(coverage_records),
        "queue": {
            "max_ciks": max_ciks,
            "eligible_ciks": eligible_ciks,
            "selected_ciks": len(queue),
            "deferred_ciks": deferred_queue_count,
            "priority_order": [str(item["cik"]) for item in queue],
        },
        "counts": {
            "retrieved": int(counts["retrieved"]), "retry": int(counts["retry"]),
            "deferred": int(counts["deferred"]), "skipped_fresh": skipped_fresh_count,
        },
        "nonclaims": _NONCLAIMS,
        "authority": _authority(),
    }
    record["receipt_id"] = _receipt_id(record)
    return record


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    SecCapitalStructureCompanyFactsAdapter().fetch()
