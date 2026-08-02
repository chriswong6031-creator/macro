"""Bounded, offline disclosure-comparison projections for Filing Forensics.

The projection sits between the immutable SEC source cache and the compact
private workbench state.  It intentionally does *not* fetch documents, walk
the web, or infer a clock from the machine.  A caller supplies three explicit
clocks, then this module:

* verifies the cached ``submissions`` snapshot retained by
  :mod:`collectors.edgar_forensics`;
* reconciles it with checksum-bound, already-cached primary-document manifests;
* selects the latest two retained 10-K and 10-Q report periods at an SEC
  acceptance-time cutoff; and
* projects the full structural comparison into a small receipt-rich record
  suitable for the private state transport.

The full primary filings remain content-addressed in the archive cache.  This
module only carries bounded excerpts and exact source coordinates, so a
workbench consumer can show why a review prompt exists without silently
turning the browser payload into a document warehouse.
"""
from __future__ import annotations

import gzip
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Iterable, Mapping

from collectors.sec_document_spine import (
    ArchiveStoreError,
    read_filing_manifest,
    read_primary_document,
)

from .models import canonical_json, parse_utc, stable_id, utc_text
from .sec_document_spine import (
    FilingManifestError,
    build_filing_manifests,
    canonical_cik,
    select_periodic_comparables,
    validate_manifest,
)


DISCLOSURE_PROJECTION_SCHEMA = "fundamental_forensics.disclosure_projection/v1"
DEFAULT_DISCLOSURE_PROJECTION_RELATIVE = Path("data/fundamental_forensics/private/disclosures")
MAX_SUBMISSIONS_BYTES = 32 * 1024 * 1024
MAX_REDLINES_PER_TRACK = 72
MAX_FINDINGS_PER_TRACK = 24
MAX_RECEIPTS_PER_FINDING = 6
MAX_INLINE_EDITS_PER_REDLINE = 6
MAX_INLINE_TEXT_CHARS = 240
MAX_EXCERPT_CHARS = 420
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")
_FORMS = ("10-K", "10-Q")
_TRACK_STATUS = {"ready", "not_evaluable"}


class DisclosureProjectionError(ValueError):
    """A cached disclosure projection or one of its source receipts is unsafe."""


def _normalized_clock(value: str | None, *, field: str, required: bool = True) -> str | None:
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise DisclosureProjectionError(str(exc)) from exc
    if parsed is None:
        if required:
            raise DisclosureProjectionError(f"{field} is required")
        return None
    return utc_text(parsed)


def _normalized_ticker(value: str) -> str:
    ticker = str(value or "").strip().upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise DisclosureProjectionError(f"invalid ticker: {value!r}")
    return ticker


def _normalized_cik(value: int | str) -> str:
    try:
        return canonical_cik(value)
    except FilingManifestError as exc:
        raise DisclosureProjectionError(str(exc)) from exc


def _safe_relative(root: Path, relative: str | Path) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise DisclosureProjectionError(f"unsafe cache path: {relative!r}")
    root_path = root.resolve()
    candidate = (root_path / relative_path).resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise DisclosureProjectionError(f"cache path escapes root: {relative!r}") from exc
    return candidate


def _bounded_text(value: Any, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1] + "…"


class _ExcerptTextExtractor(HTMLParser):
    """Render a bounded SEC HTML fragment as inert human-readable text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _display_excerpt(value: Any) -> str:
    """Strip filing markup without asking the browser to parse untrusted HTML.

    ``source_excerpt`` remains the exact bounded source fragment tied to the
    hash/span receipt.  This companion is presentation-only and prevents raw
    Inline XBRL tags and style attributes from overwhelming the evidence pane.
    """
    raw = _bounded_text(value, MAX_EXCERPT_CHARS)
    if not raw:
        return ""
    parser = _ExcerptTextExtractor()
    try:
        parser.feed(raw)
        parser.close()
    except (ValueError, AssertionError):  # malformed bounded fragments remain fail-soft
        return _bounded_text(re.sub(r"\s+", " ", raw).strip(), MAX_EXCERPT_CHARS)
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    return _bounded_text(text or raw, MAX_EXCERPT_CHARS)


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
        # Some mounted object-store filesystems do not implement directory fsync.
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


def _submission_receipt(raw_root: Path, cik: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a verified retained submissions payload and its portable receipt."""
    latest_path = _safe_relative(raw_root, Path(cik) / "submissions" / "latest.json")
    try:
        receipt = json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DisclosureProjectionError(f"missing or invalid submissions pointer for CIK {cik}") from exc
    if not isinstance(receipt, Mapping):
        raise DisclosureProjectionError("submissions pointer must be an object")
    required = {"schema", "cik", "endpoint", "url", "retrieved_at", "sha256", "bytes", "object_path"}
    if not required.issubset(receipt):
        raise DisclosureProjectionError("submissions pointer is incomplete")
    if receipt.get("schema") != "fundamental_forensics_retrieval.v1":
        raise DisclosureProjectionError("unsupported submissions receipt schema")
    if receipt.get("endpoint") != "submissions":
        raise DisclosureProjectionError("receipt does not describe the submissions endpoint")
    if _normalized_cik(str(receipt.get("cik"))) != cik:
        raise DisclosureProjectionError("submissions receipt CIK does not match requested CIK")
    digest = str(receipt.get("sha256") or "")
    if not _SHA256_RE.fullmatch(digest):
        raise DisclosureProjectionError("submissions receipt has invalid SHA-256")
    byte_length = receipt.get("bytes")
    if isinstance(byte_length, bool) or not isinstance(byte_length, int) or byte_length < 0:
        raise DisclosureProjectionError("submissions receipt has invalid byte length")
    if byte_length > MAX_SUBMISSIONS_BYTES:
        raise DisclosureProjectionError("submissions source exceeds bounded projection input")
    source_path = _safe_relative(raw_root, str(receipt["object_path"]))
    if source_path.suffix != ".gz":
        raise DisclosureProjectionError("submissions source object must be gzip-compressed")
    try:
        with gzip.open(source_path, "rb") as handle:
            content = handle.read(MAX_SUBMISSIONS_BYTES + 1)
    except (OSError, EOFError) as exc:
        raise DisclosureProjectionError("submissions source object is unreadable") from exc
    if len(content) > MAX_SUBMISSIONS_BYTES:
        raise DisclosureProjectionError("submissions source exceeds bounded projection input")
    if len(content) != byte_length or hashlib.sha256(content).hexdigest() != digest:
        raise DisclosureProjectionError("submissions source checksum or length mismatch")
    try:
        document = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DisclosureProjectionError("submissions source is not UTF-8 JSON") from exc
    if not isinstance(document, dict):
        raise DisclosureProjectionError("submissions source must be an object")
    response_cik = document.get("cik")
    if response_cik is not None and _normalized_cik(str(response_cik)) != cik:
        raise DisclosureProjectionError("submissions body CIK does not match receipt")
    portable = {
        "schema": str(receipt["schema"]),
        "cik": cik,
        "endpoint": "submissions",
        "url": str(receipt["url"]),
        "retrieved_at": _normalized_clock(str(receipt["retrieved_at"]), field="submissions.retrieved_at"),
        "content_sha256": digest,
        "byte_length": byte_length,
        "object_path": str(receipt["object_path"]),
        "http_etag": receipt.get("http_etag"),
        "http_last_modified": receipt.get("http_last_modified"),
    }
    return document, portable


def _primary_document(manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    return next(
        (dict(item) for item in manifest.get("documents", []) if item.get("role") == "primary"),
        None,
    )


def _manifest_version_key(manifest: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str((manifest.get("clocks") or {}).get("accepted_at") or ""),
        str((manifest.get("clocks") or {}).get("recorded_at") or ""),
        str(manifest.get("manifest_id") or ""),
    )


def _source_compatible(source: Mapping[str, Any], archived: Mapping[str, Any]) -> bool:
    source_filing = source.get("filing") or {}
    archived_filing = archived.get("filing") or {}
    source_clock = source.get("clocks") or {}
    archived_clock = archived.get("clocks") or {}
    return (
        source.get("issuer", {}).get("cik") == archived.get("issuer", {}).get("cik")
        and source_filing.get("accession") == archived_filing.get("accession")
        and source_filing.get("form") == archived_filing.get("form")
        and source_filing.get("base_form") == archived_filing.get("base_form")
        and source_filing.get("report_date") == archived_filing.get("report_date")
        and source_clock.get("accepted_at") == archived_clock.get("accepted_at")
        and source_clock.get("filed_on") == archived_clock.get("filed_on")
    )


def _stored_manifest_versions(archive_root: Path, cik: str) -> tuple[dict[str, Any], ...]:
    base = _safe_relative(archive_root, Path("manifests") / cik)
    if not base.is_dir():
        return ()
    records: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*.json")):
        relative = path.relative_to(archive_root).as_posix()
        try:
            record = read_filing_manifest(archive_root, relative)
        except (ArchiveStoreError, FilingManifestError) as exc:
            raise DisclosureProjectionError(f"invalid cached filing manifest: {relative}") from exc
        if str(record["issuer"]["cik"]) != cik:
            raise DisclosureProjectionError(f"filing manifest escaped CIK namespace: {relative}")
        records.append(record)
    return tuple(records)


def _filing_reference(manifest: Mapping[str, Any]) -> dict[str, Any]:
    primary = _primary_document(manifest)
    if primary is None:
        raise DisclosureProjectionError("selected filing has no primary document")
    retrieval = primary.get("retrieval")
    receipt: dict[str, Any] | None = None
    if isinstance(retrieval, Mapping):
        receipt = {
            key: retrieval.get(key)
            for key in (
                "schema", "receipt_id", "status", "document_id", "archive_url", "retrieved_at",
                "content_sha256", "byte_length", "storage_key", "http_etag", "http_last_modified",
            )
            if key in retrieval
        }
    return {
        "manifest_id": str(manifest["manifest_id"]),
        "filing_id": str(manifest["filing_id"]),
        "accession": str(manifest["filing"]["accession"]),
        "form": manifest["filing"].get("form"),
        "base_form": manifest["filing"].get("base_form"),
        "report_date": manifest["filing"].get("report_date"),
        # Flat aliases are intentional: the UI timeline needs to show the
        # filing pair without reverse-engineering the immutable manifest.
        # ``filed_at`` remains the SEC acceptance clock, never a local fetch
        # time, and ``source_url`` is the exact retained primary-document URL.
        "filed_at": manifest["clocks"].get("accepted_at"),
        "source_url": primary.get("archive_url"),
        "clocks": {
            "accepted_at": manifest["clocks"].get("accepted_at"),
            "filed_on": manifest["clocks"].get("filed_on"),
            "recorded_at": manifest["clocks"].get("recorded_at"),
        },
        "lineage": dict(manifest.get("lineage") or {}),
        "primary_document": {
            "document_id": primary.get("document_id"),
            "document_name": primary.get("document_name"),
            "archive_url": primary.get("archive_url"),
            "availability": primary.get("availability"),
            "content_sha256": primary.get("content_sha256"),
            "byte_length": primary.get("byte_length"),
            "source_spans": list(primary.get("source_spans") or []),
            "retrieval": receipt,
        },
    }


def _source_input(manifest: Mapping[str, Any], content: bytes) -> dict[str, Any]:
    primary = _primary_document(manifest)
    if primary is None:
        raise DisclosureProjectionError("selected filing has no primary document")
    expected = str(primary.get("content_sha256") or "")
    actual = hashlib.sha256(content).hexdigest()
    if not _SHA256_RE.fullmatch(expected) or actual != expected:
        raise DisclosureProjectionError("verified primary-document checksum mismatch")
    try:
        source = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DisclosureProjectionError(
            f"primary document is not UTF-8; no text projection emitted for {manifest['filing']['accession']}"
        ) from exc
    # The normalizer's source coordinates are based on its UTF-8 text.  Fail
    # closed if decoding/re-encoding would detach those coordinates from the
    # immutable archive bytes.
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != expected:
        raise DisclosureProjectionError("primary text cannot preserve archive byte provenance")
    document_name = str(primary.get("document_name") or "").casefold()
    content_type = "html" if document_name.endswith((".htm", ".html", ".xhtml")) else "text"
    return {
        "accession": str(manifest["filing"]["accession"]),
        "form": manifest["filing"].get("form"),
        "entity_cik": manifest["issuer"].get("cik"),
        "filed_at": manifest["clocks"].get("accepted_at"),
        "report_date": manifest["filing"].get("report_date"),
        "source_url": primary.get("archive_url"),
        "content_type": content_type,
        "content": source,
    }


def _bounded_receipt(raw: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    span = raw.get("source_span")
    safe_span = dict(span) if isinstance(span, Mapping) else None
    source_excerpt = _bounded_text(raw.get("source_excerpt"), MAX_EXCERPT_CHARS)
    return {
        "accession": raw.get("accession"),
        "form": raw.get("form"),
        "source_url": raw.get("source_url"),
        "source_sha256": raw.get("source_sha256"),
        "source_span": safe_span,
        "source_excerpt": source_excerpt,
        "display_excerpt": _display_excerpt(source_excerpt),
        "block_id": raw.get("block_id"),
        "section_id": raw.get("section_id"),
        "cell_id": raw.get("cell_id"),
    }


def _receipt_identity(raw: Mapping[str, Any]) -> tuple[str, ...]:
    span = raw.get("source_span")
    span = span if isinstance(span, Mapping) else {}
    return (
        str(raw.get("accession") or ""),
        str(raw.get("source_sha256") or ""),
        str(span.get("char_start") or ""),
        str(span.get("char_end") or ""),
        str(raw.get("block_id") or ""),
        str(raw.get("cell_id") or ""),
    )


def _balanced_finding_receipts(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Select bounded evidence without truncating away one side of the filing pair."""
    receipts = [
        item for item in list(raw.get("evidence_receipts") or []) if isinstance(item, Mapping)
    ]
    unique: list[Mapping[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for receipt in receipts:
        identity = _receipt_identity(receipt)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(receipt)

    prior_accession = str(raw.get("prior_accession") or "")
    current_accession = str(raw.get("current_accession") or "")
    groups = {
        "current": [item for item in unique if str(item.get("accession") or "") == current_accession],
        "prior": [item for item in unique if str(item.get("accession") or "") == prior_accession],
    }
    used = {id(item) for items in groups.values() for item in items}
    groups["other"] = [item for item in unique if id(item) not in used]
    selected: list[tuple[str, Mapping[str, Any]]] = []
    # Alternate current/prior first. SEC redline construction can naturally
    # group hundreds of removals before additions; naive [:6] then shows only
    # one filing and defeats the comparison contract.
    index = 0
    while len(selected) < MAX_RECEIPTS_PER_FINDING and (
        index < len(groups["current"]) or index < len(groups["prior"])
    ):
        for role in ("current", "prior"):
            if index < len(groups[role]) and len(selected) < MAX_RECEIPTS_PER_FINDING:
                selected.append((role, groups[role][index]))
        index += 1
    for item in groups["other"]:
        if len(selected) >= MAX_RECEIPTS_PER_FINDING:
            break
        selected.append(("other", item))
    # If one filing had fewer receipts, use remaining bounded evidence from the
    # other side instead of leaving the inspector artificially sparse.
    selected_ids = {id(item) for _, item in selected}
    for role in ("current", "prior"):
        for item in groups[role]:
            if len(selected) >= MAX_RECEIPTS_PER_FINDING:
                break
            if id(item) not in selected_ids:
                selected.append((role, item))
                selected_ids.add(id(item))

    output: list[dict[str, Any]] = []
    for role, receipt in selected:
        projected = _bounded_receipt(receipt)
        if projected is None:
            continue
        projected["filing_role"] = role
        output.append(projected)
    return output


def _bounded_finding(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": raw.get("finding_id"),
        "detector_id": raw.get("detector_id"),
        "detector_version": raw.get("detector_version"),
        "label_key": raw.get("label_key"),
        "labels": dict(raw.get("labels") or {}),
        "state": raw.get("state"),
        "applicability": raw.get("applicability"),
        "priority": raw.get("priority"),
        "review_level": raw.get("review_level"),
        "prior_accession": raw.get("prior_accession"),
        "current_accession": raw.get("current_accession"),
        "prior_section_ids": list(raw.get("prior_section_ids") or []),
        "current_section_ids": list(raw.get("current_section_ids") or []),
        "evidence_receipts": _balanced_finding_receipts(raw),
        "why_flagged": dict(raw.get("why_flagged") or {}),
        "benign_explanation": _bounded_text(raw.get("benign_explanation"), MAX_EXCERPT_CHARS),
        "limitations": [_bounded_text(item, 180) for item in list(raw.get("limitations") or [])[:8]],
        "display_only": True,
        "authority": "review_priority_only",
    }


def _bounded_redline(raw: Mapping[str, Any]) -> dict[str, Any]:
    edits: list[dict[str, Any]] = []
    for edit in list(raw.get("inline_edits") or [])[:MAX_INLINE_EDITS_PER_REDLINE]:
        if not isinstance(edit, Mapping):
            continue
        edits.append(
            {
                "operation": edit.get("operation"),
                "prior_text": _bounded_text(edit.get("prior_text"), MAX_INLINE_TEXT_CHARS),
                "current_text": _bounded_text(edit.get("current_text"), MAX_INLINE_TEXT_CHARS),
                "contains_numeric": bool(edit.get("contains_numeric")),
                # A coarse long-document redline is intentionally a bounded
                # review aid; preserve that fact through the private transport
                # so a UI never presents an excerpt as the full edit.
                "truncated": bool(edit.get("truncated")),
            }
        )
    return {
        "op_id": raw.get("op_id"),
        "operation": raw.get("operation"),
        "comparison_id": raw.get("comparison_id"),
        "section_key": raw.get("section_key"),
        "prior_block_id": raw.get("prior_block_id"),
        "current_block_id": raw.get("current_block_id"),
        "prior_receipt": _bounded_receipt(raw.get("prior_receipt")),
        "current_receipt": _bounded_receipt(raw.get("current_receipt")),
        "changed_token_ratio": raw.get("changed_token_ratio"),
        "changed_token_count": raw.get("changed_token_count"),
        "numeric_changed": bool(raw.get("numeric_changed")),
        "inline_edits": edits,
        "suppressed": bool(raw.get("suppressed")),
        "parent_op_id": raw.get("parent_op_id"),
    }


def _comparison_projection(comparison: Any) -> dict[str, Any]:
    """Project only bounded comparison nodes, never every normalized block.

    ``DisclosureComparison.to_dict`` intentionally contains the full normalized
    filing corpus for offline export.  Calling it here would transiently expand
    a large SEC filing into the state build even though this transport needs
    only sections, detector receipts, and selected redlines.
    """
    raw_redlines = [item.to_dict() for item in comparison.redline_ops]
    raw_findings = [item.to_dict() for item in comparison.findings]
    redlines = [item for item in raw_redlines if not item.get("suppressed")]
    findings = list(raw_findings)
    findings.sort(
        key=lambda item: (
            0 if item.get("state") == "triggered" else 1,
            0 if item.get("priority") == "high" else 1,
            str(item.get("detector_id") or ""),
            str(item.get("finding_id") or ""),
        )
    )
    bounded_findings = [_bounded_finding(item) for item in findings[:MAX_FINDINGS_PER_TRACK]]

    def receipt_block_ids(value: Mapping[str, Any]) -> set[str]:
        output: set[str] = set()
        for key in ("prior_receipt", "current_receipt"):
            receipt = value.get(key)
            if isinstance(receipt, Mapping) and receipt.get("block_id"):
                output.add(str(receipt["block_id"]))
        return output

    def generic_redline_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            0 if item.get("numeric_changed") else 1,
            -int(item.get("changed_token_count") or 0),
            str(item.get("section_key") or ""),
            str(item.get("op_id") or ""),
        )

    # Reserve up to two concrete matched redlines for each triggered detector
    # before filling the rest of the 72-row exploration budget. A pure
    # magnitude sort can otherwise retain unrelated giant table edits while a
    # finding's exact evidence blocks disappear from the browser projection.
    priority_ids: list[str] = []
    for finding in bounded_findings:
        if finding.get("state") != "triggered":
            continue
        evidence_ids = {
            str(receipt.get("block_id"))
            for receipt in list(finding.get("evidence_receipts") or [])
            if isinstance(receipt, Mapping) and receipt.get("block_id")
        }
        if not evidence_ids:
            continue
        matches = sorted(
            (item for item in redlines if receipt_block_ids(item) & evidence_ids),
            key=generic_redline_key,
        )
        for item in matches[:2]:
            op_id = str(item.get("op_id") or "")
            if op_id and op_id not in priority_ids:
                priority_ids.append(op_id)
    priority_rank = {op_id: index for index, op_id in enumerate(priority_ids)}
    redlines.sort(
        key=lambda item: (
            0 if str(item.get("op_id") or "") in priority_rank else 1,
            priority_rank.get(str(item.get("op_id") or ""), len(priority_rank)),
            *generic_redline_key(item),
        )
    )
    counts_by_operation: dict[str, int] = {}
    for item in raw_redlines:
        operation = str(item.get("operation") or "unknown")
        counts_by_operation[operation] = counts_by_operation.get(operation, 0) + 1
    sections: dict[str, list[dict[str, Any]]] = {}
    for side in ("prior", "current"):
        document = comparison.prior if side == "prior" else comparison.current
        records = [item.to_dict() for item in document.sections]
        sections[side] = [
            {
                "section_id": item.get("section_id"),
                "key": item.get("key"),
                "label_key": item.get("label_key"),
                "labels": dict(item.get("labels") or {}),
                "source_order": item.get("source_order"),
            }
            for item in records
            if isinstance(item, Mapping)
        ]
    return {
        "schema": comparison.schema,
        "comparison_id": comparison.comparison_id,
        "engine_version": comparison.engine_version,
        "coverage": {
            "alignments_total": len(comparison.comparisons),
            "redlines_total": len(raw_redlines),
            "redlines_non_suppressed": len(redlines),
            "redlines_embedded": min(len(redlines), MAX_REDLINES_PER_TRACK),
            "findings_total": len(findings),
            "findings_embedded": min(len(findings), MAX_FINDINGS_PER_TRACK),
            "redlines_by_operation": dict(sorted(counts_by_operation.items())),
        },
        "sections": sections,
        "findings": bounded_findings,
        "redlines": [_bounded_redline(item) for item in redlines[:MAX_REDLINES_PER_TRACK]],
        "limitations": [_bounded_text(item, 220) for item in list(comparison.limitations)[:16]],
    }


def _ready_track(
    *,
    form: str,
    prior: Mapping[str, Any],
    current: Mapping[str, Any],
    archive_root: Path,
    as_of: str,
) -> dict[str, Any]:
    try:
        prior_bytes = read_primary_document(archive_root, prior)
        current_bytes = read_primary_document(archive_root, current)
        prior_input = _source_input(prior, prior_bytes)
        current_input = _source_input(current, current_bytes)
    except (ArchiveStoreError, DisclosureProjectionError) as exc:
        return {
            "form": form,
            "status": "not_evaluable",
            "reason": "cached_primary_document_unavailable_or_unverifiable",
            "detail": _bounded_text(exc, 220),
            "as_of": as_of,
            "prior_filing": _filing_reference(prior),
            "current_filing": _filing_reference(current),
            "comparison": None,
        }
    try:
        # Deliberately lazy: the disclosure engine can evolve independently of
        # the immutable-cache lane, while this boundary remains narrow and
        # explicit.
        from .disclosure_diff import compare_filings  # noqa: PLC0415

        comparison = compare_filings(
            prior_input,
            current_input,
            metadata={
                "selection_basis": "latest_two_cached_periodic_filings_by_sec_acceptance_time",
                "as_of": as_of,
            },
            include_source_text=False,
        )
        projected = _comparison_projection(comparison)
    except (TypeError, ValueError, UnicodeError) as exc:
        return {
            "form": form,
            "status": "not_evaluable",
            "reason": "disclosure_normalization_failed",
            "detail": _bounded_text(exc, 220),
            "as_of": as_of,
            "prior_filing": _filing_reference(prior),
            "current_filing": _filing_reference(current),
            "comparison": None,
        }
    return {
        "form": form,
        "status": "ready",
        "reason": None,
        "as_of": as_of,
        "prior_filing": _filing_reference(prior),
        "current_filing": _filing_reference(current),
        "comparison": projected,
    }


def _not_evaluable_track(
    *,
    form: str,
    as_of: str,
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    materialized = list(candidates)
    refs = [_filing_reference(item) for item in materialized[:2]]
    return {
        "form": form,
        "status": "not_evaluable",
        "reason": "fewer_than_two_cached_primary_documents_at_acceptance_cutoff",
        "as_of": as_of,
        "available_filing_count": len(materialized),
        "candidate_filings": refs,
        "comparison": None,
    }


def _projection_id_for(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("projection_id", None)
    return stable_id("ffdisclosure_projection", body)


def validate_disclosure_projection(value: Mapping[str, Any]) -> None:
    """Validate the compact projection enough to reject torn or substituted data."""
    if not isinstance(value, Mapping):
        raise DisclosureProjectionError("disclosure projection must be an object")
    if value.get("schema") != DISCLOSURE_PROJECTION_SCHEMA:
        raise DisclosureProjectionError("unsupported disclosure projection schema")
    issuer = value.get("issuer")
    if not isinstance(issuer, Mapping):
        raise DisclosureProjectionError("projection issuer is missing")
    _normalized_ticker(str(issuer.get("ticker") or ""))
    _normalized_cik(str(issuer.get("cik") or ""))
    clocks = value.get("clocks")
    if not isinstance(clocks, Mapping):
        raise DisclosureProjectionError("projection clocks are missing")
    as_of = _normalized_clock(str(clocks.get("as_of") or ""), field="as_of")
    recorded_at = _normalized_clock(str(clocks.get("recorded_at") or ""), field="recorded_at")
    computed_at = _normalized_clock(str(clocks.get("computed_at") or ""), field="computed_at")
    assert as_of is not None and recorded_at is not None and computed_at is not None
    if computed_at < recorded_at:
        raise DisclosureProjectionError("computed_at precedes recorded_at")
    tracks = value.get("tracks")
    if not isinstance(tracks, list) or [item.get("form") for item in tracks if isinstance(item, Mapping)] != list(_FORMS):
        raise DisclosureProjectionError("projection must have canonical 10-K and 10-Q tracks")
    for track in tracks:
        if not isinstance(track, Mapping) or track.get("status") not in _TRACK_STATUS:
            raise DisclosureProjectionError("projection track is malformed")
        if track.get("status") == "ready":
            prior = track.get("prior_filing") or {}
            current = track.get("current_filing") or {}
            if prior.get("accession") == current.get("accession"):
                raise DisclosureProjectionError("comparison cannot use the same accession twice")
            if not isinstance(track.get("comparison"), Mapping):
                raise DisclosureProjectionError("ready comparison is missing its projection")
    expected = _projection_id_for(value)
    actual = value.get("projection_id")
    if not isinstance(actual, str) or actual != expected:
        raise DisclosureProjectionError("disclosure projection identity mismatch")


def build_disclosure_projection(
    *,
    raw_root: Path,
    archive_root: Path,
    ticker: str,
    cik: int | str,
    as_of: str,
    computed_at: str,
) -> dict[str, Any]:
    """Build one bounded company projection from verified *local* source caches.

    ``as_of`` is the SEC acceptance-time cutoff; ``recorded_at`` comes from the
    immutable retained submissions receipt; and ``computed_at`` is supplied by
    the caller.  There is intentionally no ``now()`` fallback.
    """
    ticker_text = _normalized_ticker(ticker)
    cik_text = _normalized_cik(cik)
    as_of_text = _normalized_clock(as_of, field="as_of")
    computed_text = _normalized_clock(computed_at, field="computed_at")
    assert as_of_text is not None and computed_text is not None
    submissions, submissions_receipt = _submission_receipt(Path(raw_root), cik_text)
    recorded_at = str(submissions_receipt["retrieved_at"])
    if computed_text < recorded_at:
        raise DisclosureProjectionError("computed_at precedes retained submissions receipt")
    try:
        source_manifests = build_filing_manifests(
            submissions,
            cik=cik_text,
            ticker=ticker_text,
            recorded_at=recorded_at,
        )
    except FilingManifestError as exc:
        raise DisclosureProjectionError("cached submissions cannot form filing manifests") from exc
    source_by_accession = {item["filing"]["accession"]: item for item in source_manifests}
    archive_versions = _stored_manifest_versions(Path(archive_root), cik_text)
    chosen_by_accession: dict[str, dict[str, Any]] = {}
    for archived in archive_versions:
        validate_manifest(archived)
        accession = str(archived["filing"]["accession"])
        source = source_by_accession.get(accession)
        primary = _primary_document(archived)
        if source is None or primary is None or primary.get("availability") != "stored":
            continue
        if not isinstance(primary.get("retrieval"), Mapping) or not _source_compatible(source, archived):
            continue
        existing = chosen_by_accession.get(accession)
        if existing is None or _manifest_version_key(archived) > _manifest_version_key(existing):
            chosen_by_accession[accession] = archived

    tracks: list[dict[str, Any]] = []
    for form in _FORMS:
        candidates = list(
            select_periodic_comparables(
                chosen_by_accession.values(),
                form=form,
                as_of=as_of_text,
                count=max(1, len(chosen_by_accession)),
            )
        )
        if len(candidates) < 2:
            tracks.append(_not_evaluable_track(form=form, as_of=as_of_text, candidates=candidates))
            continue
        tracks.append(
            _ready_track(
                form=form,
                current=candidates[0],
                prior=candidates[1],
                archive_root=Path(archive_root),
                as_of=as_of_text,
            )
        )

    ready = sum(track["status"] == "ready" for track in tracks)
    value: dict[str, Any] = {
        "schema": DISCLOSURE_PROJECTION_SCHEMA,
        "projection_id": "",
        "issuer": {"ticker": ticker_text, "cik": cik_text},
        "clocks": {
            "as_of": as_of_text,
            "recorded_at": recorded_at,
            "computed_at": computed_text,
        },
        "source": {
            "submissions_snapshot": submissions_receipt,
            "selection_basis": "latest_two_cached_periodic_filings_by_sec_acceptance_time",
            "knowledge_clock": "source_event_acceptance_time",
            "archive_requirement": "checksum_bound_cached_primary_document",
        },
        "coverage": {
            "source_periodic_manifests": sum(
                item["filing"].get("base_form") in _FORMS for item in source_manifests
            ),
            "cached_primary_manifest_versions": len(archive_versions),
            "cached_primary_accessions": len(chosen_by_accession),
            "tracks_ready": ready,
            "tracks_not_evaluable": len(tracks) - ready,
        },
        "tracks": tracks,
        "limitations": [
            "Only already-retained primary documents are compared; missing cache coverage is explicit rather than treated as unchanged disclosure.",
            "Selection uses SEC acceptance time at the supplied cutoff; retained-source and archive-retrieval clocks remain visible separately.",
            "Text changes are deterministic review prompts, not a legal-materiality finding, management-intent claim, rating, or trading authority.",
            "The full filing bytes remain in the checksum-bound archive cache; this projection embeds bounded source excerpts only.",
        ],
    }
    value["projection_id"] = _projection_id_for(value)
    validate_disclosure_projection(value)
    return value


def disclosure_projection_path(root: Path, ticker: str) -> Path:
    """Return the private, ticker-scoped projection path after strict normalization."""
    return Path(root) / DEFAULT_DISCLOSURE_PROJECTION_RELATIVE / f"{_normalized_ticker(ticker)}.json"


def write_disclosure_projection(root: Path, projection: Mapping[str, Any]) -> Path:
    """Atomically persist a canonical private projection and verify its identity."""
    validate_disclosure_projection(projection)
    ticker = _normalized_ticker(str((projection.get("issuer") or {}).get("ticker") or ""))
    path = disclosure_projection_path(Path(root), ticker)
    encoded = canonical_json(dict(projection)).encode("utf-8")
    _atomic_write(path, encoded)
    loaded = read_disclosure_projection(path)
    if canonical_json(loaded) != canonical_json(dict(projection)):  # pragma: no cover - fs corruption
        raise DisclosureProjectionError(f"failed to verify disclosure projection: {path}")
    return path


def read_disclosure_projection(path: Path) -> dict[str, Any]:
    """Read one canonical bounded projection, rejecting torn or noncanonical JSON."""
    try:
        content = Path(path).read_bytes()
        value = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DisclosureProjectionError(f"invalid disclosure projection: {path}") from exc
    if not isinstance(value, dict):
        raise DisclosureProjectionError("disclosure projection must be an object")
    validate_disclosure_projection(value)
    if canonical_json(value).encode("utf-8") != content:
        raise DisclosureProjectionError("disclosure projection is not canonically encoded")
    return value


def read_disclosure_projection_directory(root: Path) -> dict[str, dict[str, Any]]:
    """Read every canonical private projection, keyed by ticker, in stable order."""
    directory = Path(root) / DEFAULT_DISCLOSURE_PROJECTION_RELATIVE
    if not directory.is_dir():
        return {}
    output: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        value = read_disclosure_projection(path)
        ticker = _normalized_ticker(str(value["issuer"]["ticker"]))
        if ticker in output:
            raise DisclosureProjectionError(f"duplicate disclosure projection for {ticker}")
        output[ticker] = value
    return output


__all__ = [
    "DEFAULT_DISCLOSURE_PROJECTION_RELATIVE",
    "DISCLOSURE_PROJECTION_SCHEMA",
    "DisclosureProjectionError",
    "build_disclosure_projection",
    "disclosure_projection_path",
    "read_disclosure_projection",
    "read_disclosure_projection_directory",
    "validate_disclosure_projection",
    "write_disclosure_projection",
]
