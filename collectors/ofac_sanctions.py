"""Official OFAC Sanctions List Service acquisition with immutable receipts.

This module is deliberately a narrow source adapter. It owns no scheduler, database,
screening logic, country ontology, or product state.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping


SLS_HOST = "sanctionslistservice.ofac.treas.gov"
SLS_REDIRECT_HOST = "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com"
TREASURY_HOST = "www.treasury.gov"

CURRENT_CATALOG_URL = f"https://{SLS_HOST}/api/PublicationPreview/SdnList"
CURRENT_XML_URL = f"https://{SLS_HOST}/api/PublicationPreview/exports/SDN.XML"
CURRENT_XSD_URL = f"https://{SLS_HOST}/api/PublicationPreview/exports/XML.xsd"
DELTA_CATALOG_URL = f"https://{SLS_HOST}/api/PublicationPreview/GetDeltaFileArchive"
DELTA_DOWNLOAD_URL = f"https://{SLS_HOST}/api/download/delta"
DELTA_XSD_URL = "https://www.treasury.gov/ofac/downloads/sanctions/1.0/DeltaFile.xsd"

CURRENT_SCHEMA_REVISION = f"https://{SLS_HOST}/api/PublicationPreview/exports/XML"
DELTA_SCHEMA_REVISION = "https://www.treasury.gov/ofac/DeltaFile/1.0"
PARSER_REVISION = "ofac-sanctions-v1.0.3"
RIGHTS_URL = "https://ofac.treasury.gov/sanctions-list-service"
DEFAULT_MAX_RESPONSE_BYTES = 50_000_000

_DELTA_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_delta\.xml$")
_YEAR_RE = re.compile(r"^\d{4}$")


class SourceIntegrityError(RuntimeError):
    """The bytes do not agree with official integrity metadata."""


class SourceUnavailableError(RuntimeError):
    """The reviewed official acquisition route was unavailable."""


@dataclass(frozen=True)
class HttpPayload:
    payload: bytes
    headers: Mapping[str, str]
    final_url: str


def _single_query(parsed: urllib.parse.ParseResult) -> dict[str, str]:
    values = urllib.parse.parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    if any(len(items) != 1 for items in values.values()):
        raise ValueError("duplicate query parameter")
    return {key: items[0] for key, items in values.items()}


def validate_source_url(url: str, *, redirect: bool = False) -> None:
    """Fail closed unless *url* is one reviewed OFAC/Treasury acquisition route."""

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("source URL must be credential-free HTTPS")
    if parsed.port not in (None, 443) or parsed.fragment:
        raise ValueError("source URL has an unreviewed port or fragment")

    host = parsed.hostname.lower()
    path = urllib.parse.unquote(parsed.path)

    if redirect:
        if host != SLS_REDIRECT_HOST:
            raise ValueError(f"unreviewed redirect host: {host}")
        if path.startswith("/Published/") and path.endswith(("/SDN.XML", "/XML.xsd")):
            return
        if path == "/Export-XSDs/XML.xsd":
            return
        if path.startswith("/DeltaArchive/") and _DELTA_FILE_RE.fullmatch(path.rsplit("/", 1)[-1]):
            return
        raise ValueError(f"unreviewed redirect path: {path}")

    if host == TREASURY_HOST and path == "/ofac/downloads/sanctions/1.0/DeltaFile.xsd" and not parsed.query:
        return
    if host != SLS_HOST:
        raise ValueError(f"unreviewed source host: {host}")

    if path in {
        "/api/PublicationPreview/SdnList",
        "/api/PublicationPreview/exports/SDN.XML",
        "/api/PublicationPreview/exports/XML.xsd",
    } and not parsed.query:
        return
    if path == "/api/PublicationPreview/GetDeltaFileArchive":
        query = _single_query(parsed)
        if set(query) == {"year"} and _YEAR_RE.fullmatch(query["year"]):
            return
    if path == "/api/download/delta":
        query = _single_query(parsed)
        filename = query.get("filename", "")
        if set(query) == {"filename"} and filename.startswith("DeltaArchive/"):
            leaf = filename.removeprefix("DeltaArchive/")
            if "/" not in leaf and _DELTA_FILE_RE.fullmatch(leaf):
                return
    raise ValueError(f"unreviewed source path/query: {path}")


def _scrub_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _catalog_hashes(catalog_entry: Mapping[str, Any] | None) -> dict[str, str]:
    if not catalog_entry:
        return {}
    raw = catalog_entry.get("hashCodes")
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SourceIntegrityError("catalog hash metadata is not valid JSON") from exc
    if not isinstance(raw, Mapping):
        raise SourceIntegrityError("catalog hash metadata is not an object")
    return {str(key).upper(): str(value).lower() for key, value in raw.items()}


def _digest_header_sha256(headers: Mapping[str, str] | None) -> str | None:
    if not headers:
        return None
    lower = {str(key).lower(): str(value).strip() for key, value in headers.items()}
    checksum = lower.get("x-amz-checksum-sha256")
    if checksum:
        try:
            return base64.b64decode(checksum).hex()
        except (ValueError, TypeError):
            raise SourceIntegrityError("invalid x-amz-checksum-sha256 header")
    digest = lower.get("digest", "")
    match = re.search(r"sha-256\s*=?\s*:?\s*([A-Za-z0-9+/=]{40,})", digest, re.I)
    if match:
        token = match.group(1)
        if re.fullmatch(r"[0-9a-fA-F]{64}", token):
            return token.lower()
        try:
            return base64.b64decode(token).hex()
        except (ValueError, TypeError):
            raise SourceIntegrityError("invalid Digest SHA-256 header")
    return None


def make_receipt(
    *,
    source_key: str,
    requested_url: str,
    final_url: str,
    payload: bytes,
    acquired_at: str,
    published_at: str | None,
    schema_revision: str,
    rights_url: str,
    format_name: str = "xml",
    catalog_entry: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    delta_relation: str | None = None,
) -> dict[str, Any]:
    """Create a receipt and verify every available authoritative digest."""

    validate_source_url(requested_url)
    if final_url != requested_url:
        validate_source_url(final_url, redirect=True)
    actual_hash = hashlib.sha256(payload).hexdigest()
    actual_bytes = len(payload)
    hashes = _catalog_hashes(catalog_entry)
    catalog_hash = hashes.get("SHA-256")
    catalog_bytes = catalog_entry.get("size") if catalog_entry else None
    server_hash = _digest_header_sha256(headers)

    if catalog_hash and catalog_hash != actual_hash:
        raise SourceIntegrityError("catalog SHA-256 does not match acquired bytes")
    if server_hash and server_hash != actual_hash:
        raise SourceIntegrityError("server SHA-256 does not match acquired bytes")
    # Some archive rows expose a stale size without a digest. Preserve that mismatch
    # visibly, but do not let unauthenticated size metadata veto hashable official bytes.
    if catalog_hash and catalog_bytes is not None and int(catalog_bytes) != actual_bytes:
        raise SourceIntegrityError("catalog byte count does not match acquired bytes")

    source_name = catalog_entry.get("fileName") if catalog_entry else requested_url.rsplit("/", 1)[-1]
    receipt: dict[str, Any] = {
        "source_key": source_key,
        "source_url": requested_url,
        "source_name": source_name,
        "source_file_name": source_name,
        "format": format_name,
        "schema_revision": schema_revision,
        "acquired_at": acquired_at,
        "published_at": published_at,
        "source_published_at": published_at,
        "raw_sha256": actual_hash,
        "actual_bytes": actual_bytes,
        "raw_bytes": actual_bytes,
        "parser_revision": PARSER_REVISION,
        "source_revision": f"sha256:{actual_hash}",
        "list_identity": "OFAC_SDN",
        "entry_identity": "ofac_numeric_uid_within_list",
        "program_tag_semantics": "published_program_list",
        "entity_type_semantics": "published_sdn_type",
        "address_semantics": "published_address_fields_only",
        "resolved_url": _scrub_url(final_url),
        "catalog_sha256": catalog_hash,
        "catalog_bytes": int(catalog_bytes) if catalog_bytes is not None else None,
        "catalog_size_match": catalog_bytes is None or int(catalog_bytes) == actual_bytes,
        "server_sha256": server_hash,
        "source_health": "CURRENT",
        "rights_class": "official_public",
        "rights": "official_government_public_information",
        "rights_url": rights_url,
    }
    if delta_relation:
        receipt["delta_relation"] = delta_relation
    return receipt


class _ReviewingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        validate_source_url(newurl, redirect=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_bytes(
    url: str,
    *,
    method: str = "GET",
    timeout: int = 60,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> HttpPayload:
    validate_source_url(url)
    if not 1 <= max_bytes <= 100_000_000:
        raise ValueError("source response bound is outside the reviewed range")
    body = b"{}" if method == "POST" else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Accept": "application/json, application/xml, text/xml", "User-Agent": "MastermindX-OFAC-Receipt/1"},
    )
    opener = urllib.request.build_opener(_ReviewingRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            if final_url != url:
                validate_source_url(final_url, redirect=True)
            payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise SourceIntegrityError(f"official response exceeds {max_bytes} byte bound")
            return HttpPayload(payload, dict(response.headers.items()), final_url)
    except (OSError, ValueError) as exc:
        raise SourceUnavailableError(
            f"official OFAC acquisition failed for {_scrub_url(url)} ({type(exc).__name__})"
        ) from exc


def _catalog(url: str) -> tuple[list[dict[str, Any]], HttpPayload]:
    response = fetch_bytes(url, method="POST")
    try:
        value = json.loads(response.payload)
    except json.JSONDecodeError as exc:
        raise SourceIntegrityError("OFAC catalog response is not valid JSON") from exc
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise SourceIntegrityError("OFAC catalog response is not a list of records")
    return value, response


def _catalog_item(rows: list[dict[str, Any]], filename: str) -> dict[str, Any]:
    matches = [row for row in rows if row.get("fileName") == filename]
    if len(matches) != 1:
        raise SourceIntegrityError(f"expected one catalog record for {filename}, found {len(matches)}")
    return matches[0]


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _catalog_published(row: Mapping[str, Any]) -> str | None:
    return row.get("lastUpdated") or row.get("publishDisplayDate") or row.get("datePublished")


def acquire_bundle(
    *,
    now: datetime | None = None,
    delta_days: int = 30,
    max_delta_files: int = 64,
) -> dict[str, Any]:
    """Acquire the current SDN list, both schemas, and a bounded recent delta window."""

    if not 1 <= delta_days <= 366 or not 1 <= max_delta_files <= 128:
        raise ValueError("delta acquisition bounds are outside the reviewed range")
    now = now or datetime.now(timezone.utc)
    acquired_at = _iso_z(now)

    current_catalog, current_catalog_response = _catalog(CURRENT_CATALOG_URL)
    current_item = _catalog_item(current_catalog, "SDN.XML")
    xsd_item = _catalog_item(current_catalog, "XML.xsd")
    current = fetch_bytes(CURRENT_XML_URL)
    current_xsd = fetch_bytes(CURRENT_XSD_URL)

    years = {now.year, (now - timedelta(days=delta_days)).year}
    catalog_receipts = [
        make_receipt(
            source_key="ofac_sdn_publication_catalog",
            requested_url=CURRENT_CATALOG_URL,
            final_url=current_catalog_response.final_url,
            payload=current_catalog_response.payload,
            acquired_at=acquired_at,
            published_at=None,
            schema_revision="ofac-sls-publication-catalog-v1",
            rights_url=RIGHTS_URL,
            format_name="json",
            headers=current_catalog_response.headers,
        )
    ]
    delta_rows: list[dict[str, Any]] = []
    for year in sorted(years, reverse=True):
        catalog_url = f"{DELTA_CATALOG_URL}?year={year}"
        rows, response = _catalog(catalog_url)
        delta_rows.extend(rows)
        catalog_receipts.append(
            make_receipt(
                source_key=f"ofac_sdn_delta_catalog_{year}",
                requested_url=catalog_url,
                final_url=response.final_url,
                payload=response.payload,
                acquired_at=acquired_at,
                published_at=None,
                schema_revision="ofac-sls-delta-catalog-v1",
                rights_url=RIGHTS_URL,
                format_name="json",
                headers=response.headers,
            )
        )
    cutoff = now.date() - timedelta(days=delta_days)
    selected: list[tuple[date, dict[str, Any]]] = []
    for row in delta_rows:
        filename = str(row.get("fileName") or "")
        if not _DELTA_FILE_RE.fullmatch(filename):
            continue
        day = date.fromisoformat(filename[:10])
        if cutoff <= day <= now.date():
            selected.append((day, row))
    selected.sort(key=lambda item: (item[0], item[1]["fileName"]), reverse=True)
    if len(selected) > max_delta_files:
        raise SourceIntegrityError("recent OFAC delta file count exceeds reviewed bound")

    delta_documents: list[dict[str, Any]] = []
    for day, row in selected:
        filename = row["fileName"]
        relation = f"official_delta_for={day.isoformat()}"
        url = f"{DELTA_DOWNLOAD_URL}?{urllib.parse.urlencode({'filename': f'DeltaArchive/{filename}'})}"
        fetched = fetch_bytes(url)
        delta_documents.append(
            {
                "payload": fetched.payload,
                "receipt": make_receipt(
                    source_key=f"ofac_sdn_delta_{day.isoformat()}",
                    requested_url=url,
                    final_url=fetched.final_url,
                    payload=fetched.payload,
                    acquired_at=acquired_at,
                    published_at=_catalog_published(row),
                    schema_revision=DELTA_SCHEMA_REVISION,
                    rights_url=RIGHTS_URL,
                    catalog_entry=row,
                    headers=fetched.headers,
                    delta_relation=relation,
                ),
            }
        )

    delta_xsd = fetch_bytes(DELTA_XSD_URL)
    return {
        "current_xml": current.payload,
        "current_receipt": make_receipt(
            source_key="ofac_sdn_current",
            requested_url=CURRENT_XML_URL,
            final_url=current.final_url,
            payload=current.payload,
            acquired_at=acquired_at,
            published_at=_catalog_published(current_item),
            schema_revision=CURRENT_SCHEMA_REVISION,
            rights_url=RIGHTS_URL,
            catalog_entry=current_item,
            headers=current.headers,
        ),
        "schema_receipts": [
            make_receipt(
                source_key="ofac_sdn_current_xsd",
                requested_url=CURRENT_XSD_URL,
                final_url=current_xsd.final_url,
                payload=current_xsd.payload,
                acquired_at=acquired_at,
                published_at=_catalog_published(xsd_item),
                schema_revision=CURRENT_SCHEMA_REVISION,
                rights_url=RIGHTS_URL,
                catalog_entry=xsd_item,
                headers=current_xsd.headers,
            ),
            make_receipt(
                source_key="ofac_sdn_delta_xsd",
                requested_url=DELTA_XSD_URL,
                final_url=delta_xsd.final_url,
                payload=delta_xsd.payload,
                acquired_at=acquired_at,
                published_at=None,
                schema_revision=DELTA_SCHEMA_REVISION,
                rights_url=RIGHTS_URL,
                headers=delta_xsd.headers,
            ),
        ],
        "catalog_receipts": catalog_receipts,
        "delta_documents": delta_documents,
    }
