"""Deterministic SEC filing/document manifests for Filing Forensics.

This is an *evidence* contract, not an interpretation layer.  It translates an
already-retained SEC Submissions response (and, optionally, an archive index)
into immutable filing manifests.  Every public clock is explicit:

* ``accepted_at`` is the SEC acceptance timestamp and the point-in-time source
  event clock;
* ``filed_on`` remains the SEC's date-only filing label and is never silently
  promoted into an intraday event clock; and
* ``recorded_at`` is when our source plane retained the manifest.

The SEC Submissions endpoint does not identify which exact prior accession an
``/A`` amends.  Where an unambiguous same-form/same-report-period predecessor
is available, we retain that relationship as an *inference*, not a claimed SEC
fact.  Otherwise the amendment remains explicitly unresolved.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import hmac
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from .models import canonical_json, parse_utc, stable_id, utc_text


FILING_MANIFEST_SCHEMA = "fundamental_forensics.sec_filing_manifest/v1"
MANIFEST_ID_PREFIX = "ffsec_manifest_"
ARCHIVE_ORIGIN = "https://www.sec.gov/Archives/edgar/data"

_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_CIK_RE = re.compile(r"^[0-9]{1,10}$")
_DOCUMENT_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_AVAILABILITY = {"declared", "stored", "missing"}
_RELATIONSHIP = {
    "original",
    "observed_accession",
    "inferred_same_form_report_period",
    "unresolved",
}


class FilingManifestError(ValueError):
    """A filing manifest is malformed or its identity was changed."""


def canonical_cik(value: int | str) -> str:
    """Return a positive SEC CIK in its canonical ten-digit ASCII spelling."""
    text = str(value).strip()
    # ``str.isdigit`` also accepts non-ASCII numerals.  Those are not legal
    # SEC identifiers and would otherwise be silently converted by ``int``.
    if not _CIK_RE.fullmatch(text) or int(text) == 0:
        raise FilingManifestError(f"invalid CIK: {value!r}")
    return f"{int(text):010d}"


def _optional_date(value: Any, *, field: str) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not _DATE_RE.fullmatch(text):
        raise FilingManifestError(f"invalid {field}: {value!r}")
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise FilingManifestError(f"invalid {field}: {value!r}") from exc
    return text


def _optional_clock(value: Any, *, field: str) -> str | None:
    if value is None or value == "":
        return None
    try:
        parsed = parse_utc(str(value), field=field)
    except ValueError as exc:
        raise FilingManifestError(str(exc)) from exc
    return utc_text(parsed)


def _form(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value).strip().upper() or None


def _ticker(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip().upper()
    if not text or any(char.isspace() for char in text):
        raise FilingManifestError(f"invalid ticker: {value!r}")
    return text


def base_form(form: str | None) -> str | None:
    """Return a periodic form family without claiming amendments are identical."""
    if not form:
        return None
    return form[:-2] if form.endswith("/A") else form


def _is_amendment(form: str | None) -> bool:
    return bool(form and form.endswith("/A"))


def archive_directory_url(cik: int | str, accession: str) -> str:
    cik10 = canonical_cik(cik)
    if not _ACCESSION_RE.fullmatch(accession):
        raise FilingManifestError(f"invalid accession: {accession!r}")
    return f"{ARCHIVE_ORIGIN}/{int(cik10)}/{accession.replace('-', '')}"


def archive_index_url(cik: int | str, accession: str) -> str:
    return archive_directory_url(cik, accession) + "/index.json"


def archive_document_url(cik: int | str, accession: str, document_name: str) -> str:
    _check_document_name(document_name)
    return archive_directory_url(cik, accession) + f"/{document_name}"


def _check_document_name(value: Any) -> str:
    name = str(value or "").strip()
    # SEC Submissions occasionally uses a safe relative primary-document path
    # (for example ``xslF345X03/edgar.xml``). Preserve that exact archive
    # identity while rejecting every form of traversal or URL mutation.
    segments = name.split("/")
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or "\x00" in name
        or "?" in name
        or "#" in name
        or any(
            not segment
            or segment in {".", ".."}
            or not _DOCUMENT_SEGMENT_RE.fullmatch(segment)
            for segment in segments
        )
    ):
        raise FilingManifestError(f"unsafe archive document name: {value!r}")
    return name


def _rows(submissions: Mapping[str, Any]) -> list[dict[str, Any]]:
    recent = ((submissions.get("filings") or {}).get("recent") or {})
    if not isinstance(recent, Mapping):
        raise FilingManifestError("submissions.filings.recent must be an object of arrays")
    accessions = recent.get("accessionNumber") or []
    if not isinstance(accessions, list):
        raise FilingManifestError("submissions.filings.recent.accessionNumber must be an array")
    rows: list[dict[str, Any]] = []
    for index, accession in enumerate(accessions):
        if accession is None or not str(accession).strip():
            continue
        row = {
            field: values[index] if isinstance(values, list) and index < len(values) else None
            for field, values in recent.items()
        }
        row["accessionNumber"] = str(accession).strip()
        rows.append(row)
    return rows


def _sort_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    # Null SEC acceptance time stays visible and sorts after known clocks.
    return (
        str(row.get("accepted_at") or "9999-12-31T23:59:59.999999Z"),
        str(row.get("filed_on") or "9999-12-31"),
        str(row["accession"]),
    )


def _primary_document(cik: str, accession: str, value: Any) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    name = _check_document_name(value)
    return {
        "document_id": stable_id("sec_document", cik, accession, "primary", name),
        "document_name": name,
        "document_type": None,
        "sequence": None,
        "role": "primary",
        "archive_url": archive_document_url(cik, accession, name),
        "availability": "declared",
        "content_sha256": None,
        "byte_length": None,
        "storage_key": None,
        "retrieval": None,
        "source_spans": [],
    }


def _manifest_id(record: Mapping[str, Any]) -> str:
    body = dict(record)
    body.pop("manifest_id", None)
    return MANIFEST_ID_PREFIX + hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def manifest_id_for(record: Mapping[str, Any]) -> str:
    """Return an ID committing to every persisted field except the ID itself."""
    return _manifest_id(record)


def validate_manifest_identity(record: Mapping[str, Any]) -> None:
    actual = record.get("manifest_id")
    expected = manifest_id_for(record)
    if not isinstance(actual, str) or not hmac.compare_digest(actual, expected):
        raise FilingManifestError(
            f"filing manifest identity mismatch: expected {expected}, got {actual!r}"
        )


def _source_span(document: Mapping[str, Any]) -> dict[str, str]:
    digest = document.get("content_sha256")
    length = document.get("byte_length")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise FilingManifestError("stored document must have a SHA-256 digest")
    if isinstance(length, bool) or not isinstance(length, int) or length < 0:
        raise FilingManifestError("stored document must have a non-negative byte_length")
    locator = f"bytes:0-{length}"
    text_digest = digest
    span_id = stable_id("sec_span", document["document_id"], locator, text_digest)
    return {
        "span_id": span_id,
        "locator_type": "byte_range",
        "locator": locator,
        "text_sha256": text_digest,
    }


def _validate_document(document: Mapping[str, Any], *, cik: str, accession: str) -> None:
    required = {
        "document_id", "document_name", "document_type", "sequence", "role", "archive_url",
        "availability", "content_sha256", "byte_length", "storage_key", "retrieval", "source_spans",
    }
    missing = required.difference(document)
    if missing:
        raise FilingManifestError(f"document metadata missing fields: {sorted(missing)}")
    name = _check_document_name(document["document_name"])
    if document["archive_url"] != archive_document_url(cik, accession, name):
        raise FilingManifestError("document archive_url is not canonical")
    availability = document["availability"]
    if availability not in _AVAILABILITY:
        raise FilingManifestError(f"invalid document availability: {availability!r}")
    expected_document_id = stable_id(
        "sec_document", cik, accession, document["role"], name
    )
    if document["document_id"] != expected_document_id:
        raise FilingManifestError("document_id does not bind its filing identity")
    if availability == "stored":
        span = _source_span(document)
        spans = document["source_spans"]
        if spans != [span]:
            raise FilingManifestError("stored document must retain its root source span")
        retrieval = document["retrieval"]
        if not isinstance(retrieval, Mapping) or retrieval.get("status") != "retrieved":
            raise FilingManifestError("stored document must retain a retrieved receipt")
        if retrieval.get("content_sha256") != document["content_sha256"]:
            raise FilingManifestError("document and receipt checksums differ")
        if retrieval.get("storage_key") != document["storage_key"]:
            raise FilingManifestError("document and receipt storage keys differ")
    else:
        if any(
            document[field] is not None
            for field in ("content_sha256", "byte_length", "storage_key")
        ):
            raise FilingManifestError("unretained document cannot claim stored bytes")
        if document["source_spans"]:
            raise FilingManifestError("unretained document cannot claim source spans")
        retrieval = document["retrieval"]
        if availability == "declared" and retrieval is not None:
            raise FilingManifestError("declared document cannot have a retrieval receipt")
        if availability == "missing":
            if not isinstance(retrieval, Mapping) or retrieval.get("status") != "missing":
                raise FilingManifestError("missing document must retain its missing receipt")


def validate_manifest(record: Mapping[str, Any]) -> None:
    """Validate identity, clocks, lineage and document/source-span invariants."""
    required = {
        "schema", "manifest_id", "filing_id", "issuer", "filing", "clocks", "lineage", "documents",
    }
    missing = required.difference(record)
    if missing:
        raise FilingManifestError(f"filing manifest missing fields: {sorted(missing)}")
    if record["schema"] != FILING_MANIFEST_SCHEMA:
        raise FilingManifestError(f"unsupported filing manifest schema: {record['schema']!r}")
    issuer = record["issuer"]
    filing = record["filing"]
    clocks = record["clocks"]
    lineage = record["lineage"]
    if not all(isinstance(item, Mapping) for item in (issuer, filing, clocks, lineage)):
        raise FilingManifestError("manifest issuer, filing, clocks and lineage must be objects")
    cik = canonical_cik(issuer.get("cik"))
    if issuer.get("ticker") != _ticker(issuer.get("ticker")):
        raise FilingManifestError("issuer ticker must be normalized or null")
    accession = str(filing.get("accession") or "")
    if not _ACCESSION_RE.fullmatch(accession):
        raise FilingManifestError(f"invalid accession: {accession!r}")
    if record["filing_id"] != stable_id("sec_filing", cik, accession):
        raise FilingManifestError("filing_id does not bind CIK/accession")
    accepted_at = _optional_clock(clocks.get("accepted_at"), field="accepted_at")
    recorded_at = _optional_clock(clocks.get("recorded_at"), field="recorded_at")
    if recorded_at is None:
        raise FilingManifestError("recorded_at is required")
    if clocks.get("accepted_at") != accepted_at or clocks.get("recorded_at") != recorded_at:
        raise FilingManifestError("manifest clocks must be normalized UTC timestamps")
    filed_on = _optional_date(clocks.get("filed_on"), field="filed_on")
    if clocks.get("filed_on") != filed_on:
        raise FilingManifestError("filed_on must be a normalized ISO date or null")
    form = _form(filing.get("form"))
    if filing.get("form") != form or filing.get("base_form") != base_form(form):
        raise FilingManifestError("filing form family is inconsistent")
    if filing.get("report_date") != _optional_date(filing.get("report_date"), field="report_date"):
        raise FilingManifestError("report_date must be a normalized ISO date or null")
    if lineage.get("relationship") not in _RELATIONSHIP:
        raise FilingManifestError("unknown amendment lineage relationship")
    is_amendment = _is_amendment(form)
    if bool(lineage.get("is_amendment")) != is_amendment:
        raise FilingManifestError("amendment flag does not match form")
    parent = lineage.get("amends_accession")
    if parent is not None and not _ACCESSION_RE.fullmatch(str(parent)):
        raise FilingManifestError("invalid parent amendment accession")
    if not is_amendment and (parent is not None or lineage.get("relationship") != "original"):
        raise FilingManifestError("original filing cannot claim an amendment parent")
    if is_amendment and parent is None and lineage.get("relationship") != "unresolved":
        raise FilingManifestError("amendment without parent must be explicit unresolved")
    documents = record["documents"]
    if not isinstance(documents, list):
        raise FilingManifestError("documents must be an array")
    for document in documents:
        if not isinstance(document, Mapping):
            raise FilingManifestError("document metadata must be an object")
        _validate_document(document, cik=cik, accession=accession)
    ordered = sorted(documents, key=_document_sort_key)
    if documents != ordered:
        raise FilingManifestError("documents must use canonical order")
    validate_manifest_identity(record)


def _document_sort_key(document: Mapping[str, Any]) -> tuple[int, str, str]:
    role_order = {"primary": 0, "exhibit": 1, "archive": 2}.get(str(document.get("role")), 9)
    return (
        role_order,
        str(document.get("sequence") or ""),
        str(document.get("document_name") or ""),
    )


def _document_metadata(
    cik: str,
    accession: str,
    *,
    name: str,
    role: str,
    sequence: str | None = None,
    document_type: str | None = None,
) -> dict[str, Any]:
    name = _check_document_name(name)
    role = str(role).strip().lower()
    if role not in {"primary", "exhibit", "archive"}:
        raise FilingManifestError(f"unsupported archive document role: {role!r}")
    return {
        "document_id": stable_id("sec_document", cik, accession, role, name),
        "document_name": name,
        "document_type": str(document_type).strip() if document_type else None,
        "sequence": (
            str(sequence).strip()
            if sequence is not None and str(sequence).strip()
            else None
        ),
        "role": role,
        "archive_url": archive_document_url(cik, accession, name),
        "availability": "declared",
        "content_sha256": None,
        "byte_length": None,
        "storage_key": None,
        "retrieval": None,
        "source_spans": [],
    }


def _row_record(cik: str, row: Mapping[str, Any], recorded_at: str) -> dict[str, Any]:
    accession = str(row["accessionNumber"]).strip()
    if not _ACCESSION_RE.fullmatch(accession):
        raise FilingManifestError(f"invalid accession: {accession!r}")
    form = _form(row.get("form"))
    return {
        "accession": accession,
        "form": form,
        "base_form": base_form(form),
        "report_date": _optional_date(row.get("reportDate"), field="reportDate"),
        "filed_on": _optional_date(row.get("filingDate"), field="filingDate"),
        "accepted_at": _optional_clock(row.get("acceptanceDateTime"), field="acceptanceDateTime"),
        "recorded_at": recorded_at,
        "primary_document": row.get("primaryDocument"),
        "is_xbrl": row.get("isXBRL"),
        "is_inline_xbrl": row.get("isInlineXBRL"),
        "items": str(row.get("items")).strip() if row.get("items") else None,
        "raw_amends_accession": row.get("amendsAccessionNumber"),
    }


def _lineage(records: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Derive a conservative direct parent relation for each amendment accession."""
    output: dict[str, dict[str, Any]] = {}
    for current in sorted(records, key=_sort_key):
        form = current["form"]
        accession = current["accession"]
        if not _is_amendment(form):
            output[accession] = {
                "is_amendment": False,
                "amends_accession": None,
                "relationship": "original",
            }
            continue
        explicit = current.get("raw_amends_accession")
        if explicit is not None and _ACCESSION_RE.fullmatch(str(explicit).strip()):
            output[accession] = {
                "is_amendment": True,
                "amends_accession": str(explicit).strip(),
                "relationship": "observed_accession",
            }
            continue
        predecessors = [
            candidate
            for candidate in records
            if candidate["accession"] != accession
            and candidate["base_form"] == current["base_form"]
            and candidate["report_date"] is not None
            and candidate["report_date"] == current["report_date"]
            and _sort_key(candidate) < _sort_key(current)
        ]
        if predecessors:
            parent = max(predecessors, key=_sort_key)
            output[accession] = {
                "is_amendment": True,
                "amends_accession": parent["accession"],
                "relationship": "inferred_same_form_report_period",
            }
        else:
            output[accession] = {
                "is_amendment": True,
                "amends_accession": None,
                "relationship": "unresolved",
            }
    return output


def build_filing_manifests(
    submissions: Mapping[str, Any],
    *,
    cik: int | str | None = None,
    ticker: str | None = None,
    recorded_at: str | datetime,
) -> tuple[dict[str, Any], ...]:
    """Build byte-stable manifests from a fetched SEC Submissions payload.

    The returned manifests intentionally contain declared primary documents only.
    ``documents_from_archive_index`` expands that declaration when an archive
    index has been retained, and the collector then replaces declarations with
    checksum-bound stored/missing receipts.
    """
    recorded = _optional_clock(recorded_at, field="recorded_at")
    if recorded is None:  # pragma: no cover - required positional keyword
        raise FilingManifestError("recorded_at is required")
    entity_cik = canonical_cik(cik if cik is not None else submissions.get("cik"))
    entity_name = str(submissions.get("name") or submissions.get("entityName") or "").strip()
    entity_ticker = _ticker(ticker)
    records = [_row_record(entity_cik, row, recorded) for row in _rows(submissions)]
    # Reject duplicate accession rows rather than arbitrarily trusting the first.
    by_accession: dict[str, dict[str, Any]] = {}
    for item in records:
        previous = by_accession.get(item["accession"])
        if previous is not None and canonical_json(previous) != canonical_json(item):
            raise FilingManifestError(f"divergent duplicate accession: {item['accession']}")
        by_accession[item["accession"]] = item
    records = sorted(by_accession.values(), key=_sort_key)
    lineage = _lineage(records)
    manifests: list[dict[str, Any]] = []
    for item in records:
        primary = _primary_document(entity_cik, item["accession"], item["primary_document"])
        record: dict[str, Any] = {
            "schema": FILING_MANIFEST_SCHEMA,
            "manifest_id": "",
            "filing_id": stable_id("sec_filing", entity_cik, item["accession"]),
            "issuer": {
                "cik": entity_cik,
                "name": entity_name or None,
                "ticker": entity_ticker,
            },
            "filing": {
                "accession": item["accession"],
                "form": item["form"],
                "base_form": item["base_form"],
                "report_date": item["report_date"],
                "is_xbrl": item["is_xbrl"],
                "is_inline_xbrl": item["is_inline_xbrl"],
                "items": item["items"],
                "archive_index_url": archive_index_url(entity_cik, item["accession"]),
            },
            "clocks": {
                "accepted_at": item["accepted_at"],
                "filed_on": item["filed_on"],
                "recorded_at": item["recorded_at"],
            },
            "lineage": lineage[item["accession"]],
            "documents": [primary] if primary else [],
        }
        record["manifest_id"] = manifest_id_for(record)
        validate_manifest(record)
        manifests.append(record)
    return tuple(manifests)


def documents_from_archive_index(
    manifest: Mapping[str, Any], payload: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Expand a manifest's declared document list from SEC archive ``index.json``.

    SEC archive indexes describe file names, not document types or XBRL roles.
    Those unknowns remain ``null``.  The primary-document designation comes from
    the retained Submissions record; every other readable archive file is an
    unclassified archive object until a later parser assigns an exhibit role.
    """
    validate_manifest(manifest)
    directory = payload.get("directory")
    items = directory.get("item") if isinstance(directory, Mapping) else None
    if not isinstance(items, list):
        raise FilingManifestError("archive index directory.item must be an array")
    cik = str(manifest["issuer"]["cik"])
    accession = str(manifest["filing"]["accession"])
    existing = {str(item["document_name"]): dict(item) for item in manifest["documents"]}
    primary_names = {
        item["document_name"]
        for item in manifest["documents"]
        if item["role"] == "primary"
    }
    for raw in items:
        if not isinstance(raw, Mapping) or raw.get("name") is None:
            continue
        name = _check_document_name(raw["name"])
        # SEC index rows include the JSON index itself and supporting XBRL files;
        # retain all file identities and let a downstream parser decide relevance.
        if name in existing:
            continue
        existing[name] = _document_metadata(
            cik,
            accession,
            name=name,
            role="primary" if name in primary_names else "archive",
            sequence=None,
            document_type=None,
        )
    return sorted(existing.values(), key=_document_sort_key)


def with_archive_documents(
    manifest: Mapping[str, Any], documents: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Return a new immutable manifest version with a canonical document inventory."""
    validate_manifest(manifest)
    out = json.loads(canonical_json(dict(manifest)))
    out["documents"] = sorted([dict(item) for item in documents], key=_document_sort_key)
    out["manifest_id"] = manifest_id_for(out)
    validate_manifest(out)
    return out


def document_with_retrieval(
    document: Mapping[str, Any],
    receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Bind a declared document to a cache receipt, or preserve an explicit miss."""
    out = json.loads(canonical_json(dict(document)))
    if receipt is None:
        return out
    status = receipt.get("status")
    if status == "missing":
        out.update(
            {
                "availability": "missing",
                "content_sha256": None,
                "byte_length": None,
                "storage_key": None,
                "retrieval": dict(receipt),
                "source_spans": [],
            }
        )
        return out
    if status != "retrieved":
        raise FilingManifestError(f"unsupported document retrieval status: {status!r}")
    digest = receipt.get("content_sha256")
    length = receipt.get("byte_length")
    storage_key = receipt.get("storage_key")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise FilingManifestError("retrieval receipt missing valid content_sha256")
    if isinstance(length, bool) or not isinstance(length, int) or length < 0:
        raise FilingManifestError("retrieval receipt missing valid byte_length")
    if not isinstance(storage_key, str) or not storage_key:
        raise FilingManifestError("retrieval receipt missing storage_key")
    out.update(
        {
            "availability": "stored",
            "content_sha256": digest,
            "byte_length": length,
            "storage_key": storage_key,
            "retrieval": dict(receipt),
            "source_spans": [],
        }
    )
    out["source_spans"] = [_source_span(out)]
    return out


def with_document_retrievals(
    manifest: Mapping[str, Any],
    receipts_by_document_id: Mapping[str, Mapping[str, Any] | None],
) -> dict[str, Any]:
    """Return a new manifest version after archive retrieval, never mutating input."""
    validate_manifest(manifest)
    documents = [
        document_with_retrieval(document, receipts_by_document_id.get(str(document["document_id"])))
        for document in manifest["documents"]
    ]
    return with_archive_documents(manifest, documents)


def select_periodic_comparables(
    manifests: Iterable[Mapping[str, Any]],
    *,
    form: str,
    ticker: str | None = None,
    as_of: str | datetime | None = None,
    count: int = 2,
) -> tuple[dict[str, Any], ...]:
    """Choose latest/prior comparable periodic filings entirely from manifests.

    The selection is point-in-time safe: a filing with no SEC acceptance clock,
    or one accepted after ``as_of``, is not eligible.  Amendments compete within
    their report period, so the latest eligible version of each period is
    returned before periods are ranked by report date.  This is deliberately a
    selector, not a network fetcher; callers then use the persisted document
    receipt to read exact verified bytes offline.
    """
    requested = _form(form)
    if requested not in {"10-K", "10-Q"}:
        raise FilingManifestError("comparable filing form must be 10-K or 10-Q")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise FilingManifestError("count must be a positive integer")
    requested_ticker = _ticker(ticker)
    cutoff = _optional_clock(as_of, field="as_of") if as_of is not None else None
    eligible: list[dict[str, Any]] = []
    for raw in manifests:
        validate_manifest(raw)
        record = json.loads(canonical_json(dict(raw)))
        if requested_ticker is not None and record["issuer"].get("ticker") != requested_ticker:
            continue
        if record["filing"]["base_form"] != requested:
            continue
        accepted_at = record["clocks"]["accepted_at"]
        report_date = record["filing"]["report_date"]
        if accepted_at is None or report_date is None:
            continue
        if cutoff is not None and accepted_at > cutoff:
            continue
        eligible.append(record)
    per_period: dict[str, dict[str, Any]] = {}
    for record in eligible:
        key = str(record["filing"]["report_date"])
        prior = per_period.get(key)
        if prior is None or (
            str(record["clocks"]["accepted_at"]), str(record["filing"]["accession"])
        ) > (
            str(prior["clocks"]["accepted_at"]), str(prior["filing"]["accession"])
        ):
            per_period[key] = record
    return tuple(
        per_period[period]
        for period in sorted(per_period, reverse=True)[:count]
    )


def manifest_json_bytes(manifest: Mapping[str, Any]) -> bytes:
    """Validate and encode a manifest in its deterministic on-disk form."""
    validate_manifest(manifest)
    return canonical_json(dict(manifest)).encode("utf-8")


def manifest_from_json_bytes(content: bytes) -> dict[str, Any]:
    try:
        record = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FilingManifestError("manifest bytes are not UTF-8 JSON") from exc
    if not isinstance(record, dict):
        raise FilingManifestError("manifest JSON must be an object")
    validate_manifest(record)
    if manifest_json_bytes(record) != content:
        raise FilingManifestError("manifest JSON is not canonically encoded")
    return record
