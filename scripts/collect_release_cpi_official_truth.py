"""Collect immutable archived CPI Table 1 editions from bounded BLS sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.release_cpi_official_truth import (
    ARCHIVE_SEQUENCE,
    ARCHIVED_TABLE1_ACTUAL_BASIS,
    FIRST_PRINT_STATUS,
    USER_AGENT,
    CpiOfficialTruthError,
    CpiSourceSpec,
    build_cpi_not_published_truth,
    build_cpi_official_truth,
    canonical_json_bytes,
    rebuild_cpi_official_truth_receipt,
    validate_nonpublication_spec,
    validate_source_spec,
)

DEFAULT_TRUTH_ROOT = _ROOT / "data" / "release_forecast" / "cpi_truth"
DEFAULT_PREREGISTERED_SAMPLE = DEFAULT_TRUTH_ROOT / "preregistered_sample.json"
DEFAULT_STORE = DEFAULT_TRUTH_ROOT / "official_table1_archive"
DEFAULT_RECEIPTS = DEFAULT_TRUTH_ROOT / "official_table1_receipts.jsonl"
DEFAULT_COLLECTION_MANIFEST = DEFAULT_TRUTH_ROOT / "official_table1_collection.json"
DEFAULT_BUILD_COMPLETION = DEFAULT_TRUTH_ROOT / "build_completion.json"
MAX_TRANSPORT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class FetchResult:
    status: int
    body: bytes
    url: str


def default_fetcher(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
) -> FetchResult:
    """Fetch one exact official object without following an unvalidated redirect."""
    response = requests.get(
        url,
        headers=headers,
        timeout=timeout,
        allow_redirects=False,
        stream=True,
    )
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=1024 * 1024):
        if not chunk:
            continue
        size += len(chunk)
        if size > MAX_TRANSPORT_BYTES:
            raise CpiOfficialTruthError("source body exceeds transport limit")
        chunks.append(chunk)
    return FetchResult(
        status=response.status_code, body=b"".join(chunks), url=response.url
    )


def _fetch_source(
    url: str,
    *,
    fetcher: Callable[..., FetchResult | bytes] | None,
    timeout: float,
) -> FetchResult:
    run_fetcher = fetcher or default_fetcher
    result = run_fetcher(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/zip,application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet,application/vnd.ms-excel"
            ),
        },
        timeout=timeout,
    )
    if isinstance(result, bytes):
        fetched = FetchResult(status=200, body=result, url=url)
    elif isinstance(result, FetchResult):
        fetched = result
    else:
        raise CpiOfficialTruthError("fetcher must return FetchResult or bytes")
    if fetched.status != 200:
        raise CpiOfficialTruthError(f"official source returned HTTP {fetched.status}")
    if fetched.url != url:
        raise CpiOfficialTruthError("official source redirected outside the pinned URL")
    if not fetched.body:
        raise CpiOfficialTruthError("official source returned an empty body")
    if len(fetched.body) > MAX_TRANSPORT_BYTES:
        raise CpiOfficialTruthError("source body exceeds transport limit")
    return fetched


def collect_cpi_official_truth(
    *,
    spec: CpiSourceSpec,
    store_root: str | Path = DEFAULT_STORE,
    fetcher: Callable[..., FetchResult | bytes] | None = None,
    timeout: float = 30.0,
    retrieved_at: str | None = None,
    expected_transport_sha256: str | None = None,
    expected_transport_bytes: int | None = None,
    expected_document_sha256: str | None = None,
    expected_document_bytes: int | None = None,
    retain_transport: bool = True,
) -> dict[str, Any]:
    """Fetch, parse, and retain one content-addressed archived-edition receipt."""
    validate_source_spec(spec)
    fetched = _fetch_source(spec.url, fetcher=fetcher, timeout=timeout)
    _verify_raw_binding(
        fetched.body,
        expected_sha256=expected_transport_sha256,
        expected_bytes=expected_transport_bytes,
        label="transport",
    )

    build = build_cpi_official_truth(fetched.body, spec=spec)
    receipt = build.receipt
    _require_display_only_rails(receipt)
    _verify_expected_integrity(
        receipt,
        expected_transport_sha256=expected_transport_sha256,
        expected_transport_bytes=expected_transport_bytes,
        expected_document_sha256=expected_document_sha256,
        expected_document_bytes=expected_document_bytes,
    )
    root = Path(store_root)
    source = receipt["source"]

    transport_rel: Path | None = None
    if retain_transport:
        transport_rel = Path("objects") / "sha256" / source["transport_sha256"]
        _store_content_addressed(root / transport_rel, build.transport_bytes)
    document_rel: Path | None = None
    if build.document_bytes:
        document_rel = (
            Path("documents")
            / "sha256"
            / (source["document_sha256"] + build.document_extension)
        )
        _store_content_addressed(root / document_rel, build.document_bytes)

    receipt_body = canonical_json_bytes(receipt)
    receipt_token = receipt["receipt_id"].split(":", 1)[1]
    receipt_rel = Path("receipts") / "sha256" / f"{receipt_token}.json"
    _store_content_addressed(root / receipt_rel, receipt_body)

    canonical_rel: Path | None = None
    canonical_id: str | None = None
    if receipt["status"] != "ok":
        status = "attempt_recorded"
    else:
        canonical_rel = Path("canonical") / f"{spec.period}.json"
        canonical_path = root / canonical_rel
        canonical_created = _create_keep_first(canonical_path, receipt_body)
        canonical_receipt = _load_receipt(canonical_path)
        canonical_id = canonical_receipt.get("receipt_id")
        if canonical_created:
            status = "written"
        elif canonical_id == receipt["receipt_id"]:
            status = "idempotent"
        else:
            status = "conflict_keep_first"

    observed = retrieved_at or _utc_now()
    return {
        "schema": "release_cpi_official_collection.v1",
        "status": status,
        "truth_status": receipt["status"],
        "period": spec.period,
        "release_date": spec.release_date,
        "retrieved_at": observed,
        "receipt_id": receipt["receipt_id"],
        "canonical_receipt_id": canonical_id,
        "keep_first_preserved": status == "conflict_keep_first",
        "paths": {
            "transport_object": transport_rel.as_posix() if transport_rel else None,
            "document_object": document_rel.as_posix() if document_rel else None,
            "receipt": receipt_rel.as_posix(),
            "canonical": canonical_rel.as_posix() if canonical_rel else None,
        },
        "receipt": receipt,
    }


def collect_cpi_not_published_truth(
    *,
    case_id: str,
    source_id: str,
    period: str,
    reason: str,
    source_url: str,
    evidence_statement: str,
    store_root: str | Path = DEFAULT_STORE,
    fetcher: Callable[..., FetchResult | bytes] | None = None,
    timeout: float = 30.0,
    retrieved_at: str | None = None,
    expected_evidence_sha256: str | None = None,
    expected_evidence_bytes: int | None = None,
    expected_receipt_id: str | None = None,
    expected_declaration_sha256: str | None = None,
    expected_declaration_bytes: int | None = None,
    retain_transport: bool = True,
) -> dict[str, Any]:
    """Collect a source-bound official BLS nonpublication statement."""
    validate_nonpublication_spec(
        case_id=case_id,
        source_id=source_id,
        period=period,
        reason=reason,
        source_url=source_url,
        evidence_statement=evidence_statement,
    )
    fetched = _fetch_source(source_url, fetcher=fetcher, timeout=timeout)
    _verify_raw_binding(
        fetched.body,
        expected_sha256=expected_evidence_sha256,
        expected_bytes=expected_evidence_bytes,
        label="evidence",
    )
    build = build_cpi_not_published_truth(
        fetched.body,
        case_id=case_id,
        source_id=source_id,
        period=period,
        reason=reason,
        source_url=source_url,
        evidence_statement=evidence_statement,
    )
    receipt = build.receipt
    _require_display_only_rails(receipt)
    source = receipt["source"]
    pinned = {
        "evidence_sha256": (
            expected_evidence_sha256,
            source.get("document_sha256"),
        ),
        "evidence_bytes": (expected_evidence_bytes, source.get("document_bytes")),
        "receipt_id": (expected_receipt_id, receipt.get("receipt_id")),
        "declaration_sha256": (
            expected_declaration_sha256,
            source.get("declaration_sha256"),
        ),
        "declaration_bytes": (
            expected_declaration_bytes,
            source.get("declaration_bytes"),
        ),
    }
    for field, (expected, actual) in pinned.items():
        if expected is not None and actual != expected:
            raise CpiOfficialTruthError(f"pinned nonpublication {field} mismatch")

    root = Path(store_root)
    transport_rel: Path | None = None
    if retain_transport:
        transport_rel = Path("objects") / "sha256" / source["transport_sha256"]
        _store_content_addressed(root / transport_rel, build.transport_bytes)
    document_rel = (
        Path("documents")
        / "sha256"
        / (source["document_sha256"] + build.document_extension)
    )
    _store_content_addressed(root / document_rel, build.document_bytes)

    receipt_body = canonical_json_bytes(receipt)
    receipt_token = receipt["receipt_id"].split(":", 1)[1]
    receipt_rel = Path("receipts") / "sha256" / f"{receipt_token}.json"
    _store_content_addressed(root / receipt_rel, receipt_body)

    canonical_rel = Path("canonical") / f"{period}.json"
    canonical_path = root / canonical_rel
    canonical_created = _create_keep_first(canonical_path, receipt_body)
    canonical_receipt = _load_receipt(canonical_path)
    canonical_id = canonical_receipt.get("receipt_id")
    if canonical_created:
        status = "written"
    elif canonical_id == receipt["receipt_id"]:
        status = "idempotent"
    else:
        status = "conflict_keep_first"

    return {
        "schema": "release_cpi_official_collection.v1",
        "status": status,
        "truth_status": receipt["status"],
        "period": period,
        "release_date": None,
        "retrieved_at": retrieved_at or _utc_now(),
        "receipt_id": receipt["receipt_id"],
        "canonical_receipt_id": canonical_id,
        "keep_first_preserved": status == "conflict_keep_first",
        "paths": {
            "transport_object": transport_rel.as_posix() if transport_rel else None,
            "document_object": document_rel.as_posix(),
            "receipt": receipt_rel.as_posix(),
            "canonical": canonical_rel.as_posix(),
        },
        "receipt": receipt,
    }


def load_preregistered_specs(path: str | Path) -> list[dict[str, Any]]:
    """Load and validate the frozen CPI parity intake contract without fetching."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CpiOfficialTruthError("preregistered sample is unreadable") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "release_cpi_truth_preregistered_sample.v1"
    ):
        raise CpiOfficialTruthError("preregistered sample schema mismatch")
    sources = payload.get("sources")
    cases = payload.get("cases")
    if not isinstance(sources, dict) or not isinstance(cases, list):
        raise CpiOfficialTruthError("preregistered sample sources/cases are malformed")

    normalized: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    periods: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise CpiOfficialTruthError("preregistered sample case is malformed")
        case_id = str(case.get("case_id") or "")
        period = str(case.get("period") or "")
        if not case_id or case_id in case_ids:
            raise CpiOfficialTruthError(
                "preregistered case_id is missing or duplicated"
            )
        if not period or period in periods:
            raise CpiOfficialTruthError("preregistered period is missing or duplicated")
        case_ids.add(case_id)
        periods.add(period)
        if case.get("publication_status") == "not_published":
            if not str(case.get("reason") or ""):
                raise CpiOfficialTruthError("not-published case is not explicit")
            source_id = str(case.get("source_id") or "")
            source = sources.get(source_id)
            if not isinstance(source, dict):
                raise CpiOfficialTruthError(
                    "not-published case has no bound source object"
                )
            if (
                source.get("publisher") != "U.S. Bureau of Labor Statistics"
                or source.get("host") != "www.bls.gov"
                or source.get("content_type") != "text/html"
                or source.get("url") != case.get("release_page_url")
            ):
                raise CpiOfficialTruthError(
                    "not-published source publisher/host contract mismatch"
                )
            normalized_gap = validate_nonpublication_spec(
                case_id=case_id,
                source_id=source_id,
                period=period,
                reason=str(case.get("reason")),
                source_url=str(source.get("url") or ""),
                evidence_statement=str(case.get("evidence_statement") or ""),
            )
            evidence_sha256 = _required_sha256(
                source.get("container_sha256"), "evidence container_sha256"
            )
            evidence_bytes = _required_positive_int(
                source.get("container_bytes"), "evidence container_bytes"
            )
            source_sha256 = _required_sha256(case.get("source_sha256"), "source_sha256")
            if source_sha256 != evidence_sha256:
                raise CpiOfficialTruthError(
                    "not-published source/evidence SHA-256 mismatch"
                )
            if (
                case.get("evidence_sha256") != evidence_sha256
                or case.get("evidence_bytes") != evidence_bytes
            ):
                raise CpiOfficialTruthError(
                    "not-published per-case evidence binding mismatch"
                )
            receipt_id = str(case.get("receipt_id") or "")
            if (
                not receipt_id.startswith("cpi_official_truth:")
                or len(receipt_id) != 51
            ):
                raise CpiOfficialTruthError(
                    "not-published receipt_id binding is invalid"
                )
            normalized.append(
                {
                    **normalized_gap,
                    "classification": case.get("classification"),
                    "publication_status": "not_published",
                    "release_page_url": normalized_gap["source_url"],
                    "expected_evidence_sha256": evidence_sha256,
                    "expected_evidence_bytes": evidence_bytes,
                    "expected_receipt_id": receipt_id,
                    "expected_declaration_sha256": _required_sha256(
                        case.get("declaration_sha256"), "declaration_sha256"
                    ),
                    "expected_declaration_bytes": _required_positive_int(
                        case.get("declaration_bytes"), "declaration_bytes"
                    ),
                }
            )
            continue
        if case.get("publication_status") != "published":
            raise CpiOfficialTruthError("case publication_status is unsupported")
        source_id = case.get("source_id")
        source = sources.get(source_id)
        if not isinstance(source, dict):
            raise CpiOfficialTruthError("published case has no bound source")
        spec = CpiSourceSpec(
            period=period,
            release_date=str(case.get("release_date") or ""),
            url=str(source.get("url") or ""),
            member=case.get("member"),
        )
        validate_source_spec(spec)
        transport_sha256 = _required_sha256(
            source.get("container_sha256"), "container_sha256"
        )
        transport_bytes = _required_positive_int(
            source.get("container_bytes"), "container_bytes"
        )
        document_sha256 = _required_sha256(case.get("member_sha256"), "member_sha256")
        document_bytes = _required_positive_int(
            case.get("member_bytes"), "member_bytes"
        )
        normalized.append(
            {
                "case_id": case_id,
                "period": period,
                "classification": case.get("classification"),
                "publication_status": "published",
                "source_id": source_id,
                "release_page_url": case.get("release_page_url"),
                "spec": spec,
                "expected_transport_sha256": transport_sha256,
                "expected_transport_bytes": transport_bytes,
                "expected_document_sha256": document_sha256,
                "expected_document_bytes": document_bytes,
            }
        )
    published = sum(row["publication_status"] == "published" for row in normalized)
    gaps = sum(row["publication_status"] == "not_published" for row in normalized)
    gate = payload.get("gate") if isinstance(payload.get("gate"), dict) else {}
    if published != gate.get("published_cases_required") or gaps != gate.get(
        "explicit_gap_cases_required"
    ):
        raise CpiOfficialTruthError("preregistered sample case-count gate mismatch")
    return normalized


def _required_sha256(value: Any, field: str) -> str:
    normalized = str(value or "").lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise CpiOfficialTruthError(f"preregistered {field} is not SHA-256")
    return normalized


def _required_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CpiOfficialTruthError(f"preregistered {field} is not a positive integer")
    return value


def collect_preregistered_sample(
    *,
    sample_path: str | Path = DEFAULT_PREREGISTERED_SAMPLE,
    store_root: str | Path = DEFAULT_STORE,
    receipts_path: str | Path = DEFAULT_RECEIPTS,
    collection_manifest_path: str | Path = DEFAULT_COLLECTION_MANIFEST,
    build_completion_path: str | Path | None = None,
    fetcher: Callable[..., FetchResult | bytes] | None = None,
    timeout: float = 30.0,
    retrieved_at: str | None = None,
    manifest_writer: Callable[[Path, bytes], None] | None = None,
) -> dict[str, Any]:
    """Collect the frozen parity panel with one fetch per missing source URL."""
    sample_file = Path(sample_path)
    try:
        sample_body = sample_file.read_bytes()
    except OSError as exc:
        raise CpiOfficialTruthError("preregistered sample is unreadable") from exc
    cases = load_preregistered_specs(sample_file)
    root = Path(store_root)
    receipts: list[dict[str, Any] | None] = [None] * len(cases)
    dispositions: list[str | None] = [None] * len(cases)
    pending_by_url: dict[str, list[int]] = {}

    for index, case in enumerate(cases):
        if case["publication_status"] == "not_published":
            reusable = _load_reusable_gap_receipt(case, root)
            if reusable is not None:
                receipts[index] = reusable
                dispositions[index] = "reused"
            else:
                pending_by_url.setdefault(case["source_url"], []).append(index)
            continue
        reusable = _load_reusable_receipt(case, root)
        if reusable is not None:
            receipts[index] = reusable
            dispositions[index] = "reused"
            continue
        spec: CpiSourceSpec = case["spec"]
        pending_by_url.setdefault(spec.url, []).append(index)

    fetched_sources = {
        url: _fetch_source(url, fetcher=fetcher, timeout=timeout)
        for url in pending_by_url
    }
    # Governed batch inputs are hash/length pinned. Verify the raw transport
    # before any ZIP extraction, workbook inflation, XML parse, or HTML parse.
    for url, indexes in pending_by_url.items():
        fetched_body = fetched_sources[url].body
        for index in indexes:
            case = cases[index]
            if case["publication_status"] == "not_published":
                _verify_raw_binding(
                    fetched_body,
                    expected_sha256=case["expected_evidence_sha256"],
                    expected_bytes=case["expected_evidence_bytes"],
                    label="evidence",
                )
            else:
                _verify_raw_binding(
                    fetched_body,
                    expected_sha256=case["expected_transport_sha256"],
                    expected_bytes=case["expected_transport_bytes"],
                    label="transport",
                )
    for url, indexes in pending_by_url.items():
        fetched = fetched_sources[url]
        for index in indexes:
            case = cases[index]
            if case["publication_status"] == "not_published":
                result = collect_cpi_not_published_truth(
                    case_id=case["case_id"],
                    source_id=case["source_id"],
                    period=case["period"],
                    reason=case["reason"],
                    source_url=case["source_url"],
                    evidence_statement=case["evidence_statement"],
                    store_root=root,
                    fetcher=lambda requested_url, _fetched=fetched, **_kwargs: (
                        FetchResult(
                            _fetched.status,
                            _fetched.body,
                            requested_url,
                        )
                    ),
                    timeout=timeout,
                    retrieved_at=retrieved_at,
                    expected_evidence_sha256=case["expected_evidence_sha256"],
                    expected_evidence_bytes=case["expected_evidence_bytes"],
                    expected_receipt_id=case["expected_receipt_id"],
                    expected_declaration_sha256=case["expected_declaration_sha256"],
                    expected_declaration_bytes=case["expected_declaration_bytes"],
                    retain_transport=False,
                )
                if result["status"] == "conflict_keep_first":
                    raise CpiOfficialTruthError(
                        f"canonical receipt conflicts for {case['case_id']}"
                    )
                receipts[index] = result["receipt"]
                dispositions[index] = "fetched"
                continue
            spec = case["spec"]
            result = collect_cpi_official_truth(
                spec=spec,
                store_root=root,
                fetcher=lambda requested_url, _fetched=fetched, **_kwargs: FetchResult(
                    _fetched.status,
                    _fetched.body,
                    requested_url,
                ),
                timeout=timeout,
                retrieved_at=retrieved_at,
                expected_transport_sha256=case["expected_transport_sha256"],
                expected_transport_bytes=case["expected_transport_bytes"],
                expected_document_sha256=case["expected_document_sha256"],
                expected_document_bytes=case["expected_document_bytes"],
                retain_transport=False,
            )
            if result["truth_status"] != "ok":
                raise CpiOfficialTruthError(
                    f"preregistered case {case['case_id']} is unavailable: "
                    f"{result['receipt'].get('reason')}"
                )
            if result["status"] == "conflict_keep_first":
                raise CpiOfficialTruthError(
                    f"canonical receipt conflicts for {case['case_id']}"
                )
            receipts[index] = result["receipt"]
            dispositions[index] = "fetched"

    if any(receipt is None for receipt in receipts):
        raise CpiOfficialTruthError("preregistered collection is incomplete")
    completed_receipts = [receipt for receipt in receipts if receipt is not None]
    for receipt in completed_receipts:
        _require_display_only_rails(receipt)
    receipt_body = b"".join(
        canonical_json_bytes(receipt) for receipt in completed_receipts
    )
    receipts_file = Path(receipts_path)
    published_count = sum(
        receipt.get("status") == "ok" for receipt in completed_receipts
    )
    gap_count = sum(
        receipt.get("status") == "not_published" for receipt in completed_receipts
    )
    sample_payload = json.loads(sample_body)
    gate = sample_payload.get("gate", {})
    if published_count != gate.get("published_cases_required") or gap_count != gate.get(
        "explicit_gap_cases_required"
    ):
        raise CpiOfficialTruthError("collected receipt-count gate mismatch")

    sample_binding = {
        "path": _display_path(sample_file),
        "sha256": hashlib.sha256(sample_body).hexdigest(),
        "bytes": len(sample_body),
    }
    archive_binding = {
        "path": _display_path(root),
        "transport_retention": "hash_and_length_only",
        "document_retention": "exact_content_addressed_bytes",
    }
    receipt_binding = {
        "path": _display_path(receipts_file),
        "sha256": hashlib.sha256(receipt_body).hexdigest(),
        "bytes": len(receipt_body),
        "count": len(completed_receipts),
    }
    distinct_source_urls = len(
        {
            (
                case["source_url"]
                if case["publication_status"] == "not_published"
                else case["spec"].url
            )
            for case in cases
        }
    )
    case_bindings = [
        {
            "case_id": case["case_id"],
            "period": case["period"],
            "publication_status": case["publication_status"],
            "truth_status": completed_receipts[index]["status"],
            "receipt_id": completed_receipts[index]["receipt_id"],
            "source": {
                "url": completed_receipts[index]["source"]["url"],
                "member": completed_receipts[index]["source"].get("member"),
                "transport_sha256": completed_receipts[index]["source"][
                    "transport_sha256"
                ],
                "transport_bytes": completed_receipts[index]["source"][
                    "transport_bytes"
                ],
                "document_sha256": completed_receipts[index]["source"][
                    "document_sha256"
                ],
                "document_bytes": completed_receipts[index]["source"]["document_bytes"],
                "document_object": (
                    Path("documents")
                    / "sha256"
                    / (
                        completed_receipts[index]["source"]["document_sha256"]
                        + completed_receipts[index]["source"]["document_extension"]
                    )
                ).as_posix(),
            },
        }
        for index, case in enumerate(cases)
    ]
    collection_manifest_file = Path(collection_manifest_path)
    downstream_completion_file = (
        Path(build_completion_path)
        if build_completion_path is not None
        else collection_manifest_file.with_name("build_completion.json")
    )
    if all(disposition == "reused" for disposition in dispositions):
        reusable_manifest = _load_reusable_collection_manifest(
            collection_manifest_file,
            receipts_file=receipts_file,
            receipt_body=receipt_body,
            sample_binding=sample_binding,
            archive_binding=archive_binding,
            receipt_binding=receipt_binding,
            case_bindings=case_bindings,
            published_count=published_count,
            gap_count=gap_count,
            distinct_source_urls=distinct_source_urls,
        )
        if reusable_manifest is not None:
            return _with_run_telemetry(
                reusable_manifest,
                dispositions=dispositions,
                fetched_source_count=len(fetched_sources),
                checked_at=retrieved_at or _utc_now(),
            )

    completion_clock = (
        _prior_manifest_clock_for_same_evidence(
            collection_manifest_file,
            sample_binding=sample_binding,
            archive_binding=archive_binding,
            receipt_binding=receipt_binding,
            case_bindings=case_bindings,
            published_count=published_count,
            gap_count=gap_count,
            distinct_source_urls=distinct_source_urls,
        )
        or retrieved_at
        or _utc_now()
    )
    # Downstream completion binds this collection manifest. Invalidate it first
    # so no crash point can leave stale downstream authority over new evidence.
    _invalidate_completion_marker(downstream_completion_file)
    _invalidate_completion_marker(collection_manifest_file)
    _atomic_replace_if_changed(receipts_file, receipt_body)
    manifest: dict[str, Any] = {
        "schema": "release_cpi_official_collection_manifest.v1",
        "status": "complete",
        "completed_at": completion_clock,
        "preregistered_sample": sample_binding,
        "archive": archive_binding,
        "receipts": receipt_binding,
        "counts": {
            "published": published_count,
            "not_published": gap_count,
            "distinct_source_urls": distinct_source_urls,
        },
        "cases": case_bindings,
    }
    write_manifest = manifest_writer or _atomic_replace
    write_manifest(collection_manifest_file, canonical_json_bytes(manifest))
    return _with_run_telemetry(
        manifest,
        dispositions=dispositions,
        fetched_source_count=len(fetched_sources),
        checked_at=retrieved_at or _utc_now(),
    )


def _load_reusable_gap_receipt(
    case: dict[str, Any],
    store_root: Path,
) -> dict[str, Any] | None:
    canonical_path = store_root / "canonical" / f"{case['period']}.json"
    document_path = (
        store_root / "documents" / "sha256" / f"{case['expected_evidence_sha256']}.html"
    )
    try:
        canonical_body = canonical_path.read_bytes()
        receipt = json.loads(canonical_body)
        document_body = document_path.read_bytes()
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(receipt, dict) or canonical_body != canonical_json_bytes(receipt):
        return None
    if (
        len(document_body) != case["expected_evidence_bytes"]
        or hashlib.sha256(document_body).hexdigest() != case["expected_evidence_sha256"]
    ):
        return None
    try:
        rebuilt = build_cpi_not_published_truth(
            document_body,
            case_id=case["case_id"],
            source_id=case["source_id"],
            period=case["period"],
            reason=case["reason"],
            source_url=case["source_url"],
            evidence_statement=case["evidence_statement"],
        ).receipt
    except CpiOfficialTruthError:
        return None
    source = rebuilt["source"]
    if (
        rebuilt != receipt
        or receipt.get("authority") is not False
        or receipt.get("display_only") is not True
        or receipt.get("receipt_id") != case["expected_receipt_id"]
        or receipt.get("source_sha256") != case["expected_evidence_sha256"]
        or source.get("declaration_sha256") != case["expected_declaration_sha256"]
        or source.get("declaration_bytes") != case["expected_declaration_bytes"]
    ):
        return None
    if not _receipt_object_matches(store_root, receipt, canonical_body):
        return None
    return receipt


def _load_reusable_receipt(
    case: dict[str, Any],
    store_root: Path,
) -> dict[str, Any] | None:
    spec: CpiSourceSpec = case["spec"]
    canonical_path = store_root / "canonical" / f"{spec.period}.json"
    expected_extension = Path(spec.member or spec.url).suffix.lower()
    document_path = (
        store_root
        / "documents"
        / "sha256"
        / f"{case['expected_document_sha256']}{expected_extension}"
    )
    try:
        canonical_body = canonical_path.read_bytes()
        receipt = json.loads(canonical_body)
        document_body = document_path.read_bytes()
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(receipt, dict)
        or canonical_body != canonical_json_bytes(receipt)
        or len(document_body) != case["expected_document_bytes"]
        or hashlib.sha256(document_body).hexdigest() != case["expected_document_sha256"]
    ):
        return None
    try:
        rebuilt = rebuild_cpi_official_truth_receipt(
            document_body,
            spec=spec,
            transport_sha256=case["expected_transport_sha256"],
            transport_bytes=case["expected_transport_bytes"],
        )
    except CpiOfficialTruthError:
        return None
    if (
        rebuilt != receipt
        or receipt.get("status") != "ok"
        or receipt.get("authority") is not False
        or receipt.get("display_only") is not True
        or receipt.get("sequence") != ARCHIVE_SEQUENCE
        or receipt.get("first_print_status") != FIRST_PRINT_STATUS
        or receipt.get("actual_basis") != ARCHIVED_TABLE1_ACTUAL_BASIS
        or not _receipt_object_matches(store_root, receipt, canonical_body)
    ):
        return None
    return receipt


def _load_reusable_collection_manifest(
    path: Path,
    *,
    receipts_file: Path,
    receipt_body: bytes,
    sample_binding: dict[str, Any],
    archive_binding: dict[str, Any],
    receipt_binding: dict[str, Any],
    case_bindings: list[dict[str, Any]],
    published_count: int,
    gap_count: int,
    distinct_source_urls: int,
) -> dict[str, Any] | None:
    try:
        manifest_body = path.read_bytes()
        manifest = json.loads(manifest_body)
        retained_receipts = receipts_file.read_bytes()
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(manifest, dict)
        or manifest_body != canonical_json_bytes(manifest)
        or retained_receipts != receipt_body
        or set(manifest)
        != {
            "schema",
            "status",
            "completed_at",
            "preregistered_sample",
            "archive",
            "receipts",
            "counts",
            "cases",
        }
        or manifest.get("schema") != "release_cpi_official_collection_manifest.v1"
        or manifest.get("status") != "complete"
        or not isinstance(manifest.get("completed_at"), str)
        or manifest.get("preregistered_sample") != sample_binding
        or manifest.get("archive") != archive_binding
        or manifest.get("receipts") != receipt_binding
    ):
        return None
    try:
        datetime.fromisoformat(str(manifest["completed_at"]).replace("Z", "+00:00"))
    except ValueError:
        return None

    counts = manifest.get("counts")
    if (
        not isinstance(counts, dict)
        or counts.get("published") != published_count
        or counts.get("not_published") != gap_count
        or counts.get("distinct_source_urls") != distinct_source_urls
        or set(counts) != {"published", "not_published", "distinct_source_urls"}
    ):
        return None
    actual_cases = manifest.get("cases")
    if not isinstance(actual_cases, list) or len(actual_cases) != len(case_bindings):
        return None
    for actual, expected in zip(actual_cases, case_bindings, strict=True):
        if not isinstance(actual, dict) or actual != expected:
            return None
    return manifest


def _prior_manifest_clock_for_same_evidence(
    path: Path,
    *,
    sample_binding: dict[str, Any],
    archive_binding: dict[str, Any],
    receipt_binding: dict[str, Any],
    case_bindings: list[dict[str, Any]],
    published_count: int,
    gap_count: int,
    distinct_source_urls: int,
) -> str | None:
    """Preserve completion time only while repairing the same bound corpus."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "release_cpi_official_collection_manifest.v1"
        or payload.get("status") != "complete"
        or payload.get("preregistered_sample") != sample_binding
        or payload.get("archive") != archive_binding
        or payload.get("receipts") != receipt_binding
        or payload.get("cases") != case_bindings
        or payload.get("counts")
        != {
            "published": published_count,
            "not_published": gap_count,
            "distinct_source_urls": distinct_source_urls,
        }
    ):
        return None
    candidate = payload.get("completed_at") or payload.get("retrieved_at")
    if not isinstance(candidate, str):
        return None
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None
    return candidate


def _with_run_telemetry(
    manifest: dict[str, Any],
    *,
    dispositions: list[str | None],
    fetched_source_count: int,
    checked_at: str,
) -> dict[str, Any]:
    result = dict(manifest)
    result["run"] = {
        "checked_at": checked_at,
        "fetched_cases": dispositions.count("fetched"),
        "reused_cases": dispositions.count("reused"),
        "fetched_source_urls": fetched_source_count,
        "case_dispositions": list(dispositions),
    }
    return result


def _atomic_replace_if_changed(path: Path, body: bytes) -> bool:
    try:
        if path.read_bytes() == body:
            return False
    except OSError:
        pass
    _atomic_replace(path, body)
    return True


def _invalidate_completion_marker(path: Path) -> None:
    """Remove stale completion authority before changing aggregate evidence."""
    try:
        path.unlink()
    except FileNotFoundError:
        return
    _fsync_directory(path.parent)


def _receipt_object_matches(
    store_root: Path,
    receipt: dict[str, Any],
    expected_body: bytes,
) -> bool:
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id.startswith(
        "cpi_official_truth:"
    ):
        return False
    token = receipt_id.split(":", 1)[1]
    if len(token) != 32:
        return False
    try:
        return (
            store_root / "receipts" / "sha256" / f"{token}.json"
        ).read_bytes() == expected_body
    except OSError:
        return False


def _require_display_only_rails(receipt: dict[str, Any]) -> None:
    if receipt.get("authority") is not False or receipt.get("display_only") is not True:
        raise CpiOfficialTruthError(
            "official archive receipt must remain display-only and non-authoritative"
        )


def _atomic_replace(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", dir=path.parent, delete=False
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _verify_expected_integrity(
    receipt: dict[str, Any],
    *,
    expected_transport_sha256: str | None,
    expected_transport_bytes: int | None,
    expected_document_sha256: str | None,
    expected_document_bytes: int | None,
) -> None:
    source = receipt.get("source") if isinstance(receipt.get("source"), dict) else {}
    expected = {
        "transport_sha256": expected_transport_sha256,
        "transport_bytes": expected_transport_bytes,
        "document_sha256": expected_document_sha256,
        "document_bytes": expected_document_bytes,
    }
    for field, value in expected.items():
        if value is not None and source.get(field) != value:
            raise CpiOfficialTruthError(f"pinned {field} mismatch")


def _verify_raw_binding(
    body: bytes,
    *,
    expected_sha256: str | None,
    expected_bytes: int | None,
    label: str,
) -> None:
    if expected_bytes is not None and len(body) != expected_bytes:
        raise CpiOfficialTruthError(f"pinned {label}_bytes mismatch")
    if (
        expected_sha256 is not None
        and hashlib.sha256(body).hexdigest() != expected_sha256
    ):
        raise CpiOfficialTruthError(f"pinned {label}_sha256 mismatch")


def _store_content_addressed(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise CpiOfficialTruthError(
                f"content-addressed object mismatch: {path.name}"
            )
        return
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", dir=path.parent, delete=False
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        try:
            os.link(temp_path, path)
        except FileExistsError:
            if path.read_bytes() != body:
                raise CpiOfficialTruthError(
                    f"content-addressed object mismatch: {path.name}"
                )
        _fsync_directory(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _create_keep_first(path: Path, body: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return False
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", dir=path.parent, delete=False
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        try:
            os.link(temp_path, path)
            created = True
        except FileExistsError:
            created = False
        _fsync_directory(path.parent)
        return created
    finally:
        temp_path.unlink(missing_ok=True)


def _load_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CpiOfficialTruthError("canonical receipt is unreadable") from exc
    if not isinstance(payload, dict) or not payload.get("receipt_id"):
        raise CpiOfficialTruthError("canonical receipt is invalid")
    return payload


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period")
    parser.add_argument("--release-date")
    parser.add_argument("--url")
    parser.add_argument("--member")
    parser.add_argument(
        "--preregistered-sample",
        type=Path,
        default=DEFAULT_PREREGISTERED_SAMPLE,
    )
    parser.add_argument("--store-root", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--receipts-path", type=Path, default=DEFAULT_RECEIPTS)
    parser.add_argument(
        "--collection-manifest-path",
        type=Path,
        default=DEFAULT_COLLECTION_MANIFEST,
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        single_values = (args.period, args.release_date, args.url)
        if any(single_values):
            if not all(single_values):
                raise CpiOfficialTruthError(
                    "single-source mode requires --period, --release-date, and --url"
                )
            result = collect_cpi_official_truth(
                spec=CpiSourceSpec(
                    period=args.period,
                    release_date=args.release_date,
                    url=args.url,
                    member=args.member,
                ),
                store_root=args.store_root,
                timeout=args.timeout,
            )
        elif args.member:
            raise CpiOfficialTruthError("--member is only valid in single-source mode")
        else:
            result = collect_preregistered_sample(
                sample_path=args.preregistered_sample,
                store_root=args.store_root,
                receipts_path=args.receipts_path,
                collection_manifest_path=args.collection_manifest_path,
                timeout=args.timeout,
            )
    except (CpiOfficialTruthError, requests.RequestException) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_BUILD_COMPLETION",
    "DEFAULT_COLLECTION_MANIFEST",
    "DEFAULT_PREREGISTERED_SAMPLE",
    "DEFAULT_RECEIPTS",
    "DEFAULT_STORE",
    "FetchResult",
    "collect_cpi_official_truth",
    "collect_preregistered_sample",
    "default_fetcher",
    "load_preregistered_specs",
    "main",
]
