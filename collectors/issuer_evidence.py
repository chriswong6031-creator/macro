"""Immutable official-evidence collection for issuer graph expansion (Wave 9D).

Retrieves the two document classes that can justify an ``issuer -> legal entity
-> UEI/CAGE`` edge, and binds each retrieval to a content-addressed receipt:

    SEC Exhibit 21  the registrant's own "Subsidiaries of the Registrant"
                    exhibit, reached from EDGAR by the official ticker -> CIK
                    map and the registrant's own 10-K accession.  This is the
                    only admissible source of exact subsidiary legal names.
    USAspending     official recipient records carrying exact SAM UEI / CAGE
                    and the recipient's registered legal name.

Receipt handling deliberately mirrors ``collectors/usaspending_awards.py``:
append-only JSONL, fail-closed on an unreadable ledger, atomic replace, and
hash binding rather than persisting raw response bodies for the large filings.
Exhibit 21 bodies are small and *are* cached to a content-addressed store so an
edge stays re-verifiable offline; large 10-K bodies are receipt-bound only and
re-fetched from their immutable EDGAR archive URL.

POLITENESS.  SEC requires a declared User-Agent and 403s without one; both
rails are rate-limited by a minimum inter-request interval, retried a bounded
number of times, and capped by an explicit page/document budget.  Nothing in
this module runs during tests -- every test drives the pure parsers and the
receipt helpers against committed fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urljoin

from engine.government_revenue.issuer_graph_expansion import (
    ExpansionInputError,
    evidence_source_ref,
    normalize_legal_name,
)


ISSUER_EVIDENCE_RECEIPT_SCHEMA = "government_revenue.issuer_evidence_receipt.v1"
ISSUER_EVIDENCE_RECEIPTS_FILENAME = "issuer_evidence_receipts.jsonl"
ISSUER_EVIDENCE_STORE_DIRNAME = "issuer_evidence"

SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
USASPENDING_RECIPIENT_SEARCH_URL = "https://api.usaspending.gov/api/v2/recipient/"
USASPENDING_RECIPIENT_DETAIL_URL = "https://api.usaspending.gov/api/v2/recipient/{recipient_id}/"

#: SEC requires a declared, contactable User-Agent; requests without one are 403ed.
DEFAULT_USER_AGENT = "MastermindX Government Revenue Foresight contact@mastermind-x.com"

#: SEC asks for <= 10 requests/second.  We stay an order of magnitude under it.
SEC_MIN_INTERVAL_SECONDS = 0.35
USASPENDING_MIN_INTERVAL_SECONDS = 1.0

#: Hard budgets.  A collection that would exceed one stops and says so.
MAX_FILINGS_PER_ISSUER = 2
MAX_RECIPIENT_PAGES = 5
MAX_RECIPIENT_PAGE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 45
MAX_ATTEMPTS = 3

#: Exhibit 21 documents are small; anything larger is not an exhibit.
MAX_EXHIBIT_BYTES = 4_000_000

_ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

#: Exhibit 21 filenames vary widely; match on the EDGAR-declared exhibit TYPE,
#: which is a structured field, rather than guessing from the document name.
_EXHIBIT21_TYPES = frozenset({"EX-21", "EX-21.1", "EX-21.01", "EX-211", "EX-21.2"})

#: The dissemination header serves each document as an SGML ``<DOCUMENT>`` block
#: whose angle brackets arrive HTML-escaped.  These read TYPE/FILENAME out of it.
_HEADER_DOCUMENT = re.compile(r"&lt;DOCUMENT&gt;(.*?)&lt;/DOCUMENT&gt;", re.IGNORECASE | re.DOTALL)
_HEADER_TYPE = re.compile(r"&lt;TYPE&gt;([^\r\n<]+)", re.IGNORECASE)
_HEADER_FILENAME = re.compile(r"&lt;FILENAME&gt;([^\r\n<]+)", re.IGNORECASE)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _safe_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:400]}"


# ---------------------------------------------------------------------------
# Pure parsers.  These are what the test suite exercises.
# ---------------------------------------------------------------------------


def parse_ticker_cik_map(payload: Mapping[str, Any] | Sequence[Any]) -> dict[str, str]:
    """Return ``{TICKER: zero-padded CIK}`` from SEC's official company_tickers.json.

    This mapping is published by the SEC itself, so ticker -> registrant is an
    exact official lookup rather than a name guess.  It is the only place a
    ticker is permitted to influence anything in this wave.
    """
    rows: Iterable[Any]
    if isinstance(payload, Mapping):
        rows = payload.values()
    else:
        rows = payload
    result: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        ticker = _text(row.get("ticker"))
        cik = row.get("cik_str", row.get("cik"))
        if ticker is None or cik is None:
            continue
        try:
            cik_int = int(str(cik).strip())
        except (TypeError, ValueError):
            continue
        result[ticker.upper()] = f"{cik_int:010d}"
    return result


def select_latest_10k(submissions: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the most recent 10-K accession from an EDGAR submissions payload.

    Returns ``None`` rather than falling back to a different form type: a 10-K
    is what carries Exhibit 21, and no other filing substitutes for it.
    """
    recent = ((submissions or {}).get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    report_dates = recent.get("reportDate") or []
    filing_dates = recent.get("filingDate") or []
    best: dict[str, Any] | None = None
    for index, form in enumerate(forms):
        if _text(form) != "10-K":
            continue
        accession = _text(accessions[index]) if index < len(accessions) else None
        if accession is None or _ACCESSION.fullmatch(accession) is None:
            continue
        row = {
            "accession": accession,
            "accession_plain": accession.replace("-", ""),
            "report_date": _text(report_dates[index]) if index < len(report_dates) else None,
            "filing_date": _text(filing_dates[index]) if index < len(filing_dates) else None,
        }
        if best is None or (row["filing_date"] or "") > (best["filing_date"] or ""):
            best = row
    return best


def select_exhibit21_document(index_headers: bytes | str) -> dict[str, Any] | None:
    """Return the Exhibit 21 document declared by an EDGAR dissemination header.

    Selection is by EDGAR's declared exhibit ``<TYPE>``, a structured field.  A
    filing that declares no EX-21 returns ``None`` -- there is no filename
    heuristic fallback, because guessing which document is the subsidiary list
    is exactly the kind of inference this wave forbids.

    THE SOURCE MATTERS.  This reads ``<accession>-index-headers.html``, which
    republishes the submission's SGML header verbatim (HTML-escaped), so each
    ``<DOCUMENT>`` block carries the filer-declared ``<TYPE>`` next to its
    ``<FILENAME>``.  It deliberately does NOT read the directory listing
    ``index.json``: that payload also has a ``type`` key, but it holds the
    web-server's icon name (``text.gif``, ``image2.gif``, ``compressed.gif``),
    never an exhibit type.  Matching EX-21 against it silently returns ``None``
    for every real filing -- measured 2026-08-07 against the latest 10-K of LMT,
    LHX, AVAV, VSAT, and PLTR, all five of which declare an EX-21 (``EX-21`` for
    LMT/LHX, ``EX-21.1`` for AVAV/VSAT/PLTR) and none of which this function
    could find while it read ``index.json``.
    """
    if isinstance(index_headers, (bytes, bytearray)):
        try:
            text = bytes(index_headers).decode("utf-8")
        except UnicodeDecodeError:
            text = bytes(index_headers).decode("latin-1", errors="replace")
    else:
        text = index_headers or ""

    for block in _HEADER_DOCUMENT.findall(text):
        declared_match = _HEADER_TYPE.search(block)
        if declared_match is None:
            continue
        declared = (_text(declared_match.group(1)) or "").upper()
        if declared not in _EXHIBIT21_TYPES:
            continue
        filename_match = _HEADER_FILENAME.search(block)
        name = _text(filename_match.group(1)) if filename_match else None
        if name:
            return {"name": name, "type": declared}
    return None


def parse_exhibit21_names(body: bytes | str) -> dict[str, Any]:
    """Extract verbatim subsidiary legal names from an Exhibit 21 document.

    Exhibit 21 layouts vary by filer.  This parser is deliberately conservative:
    it reads the leading cell of each table row and returns ``status="parsed"``
    only when it finds a plausible table of names.  When it cannot, it returns
    ``status="unparseable"`` with zero names -- an honest partial, never a
    guessed list.  Callers must treat ``unparseable`` as "no edges for this
    issuer", not as "no subsidiaries".
    """
    if isinstance(body, bytes):
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            text = body.decode("latin-1", errors="replace")
    else:
        text = body

    rows: list[str] = []
    for match in re.finditer(r"<tr[^>]*>(.*?)</tr>", text, flags=re.IGNORECASE | re.DOTALL):
        cells = re.findall(
            r"<t[dh][^>]*>(.*?)</t[dh]>", match.group(1), flags=re.IGNORECASE | re.DOTALL
        )
        if not cells:
            continue
        for cell in cells:
            cleaned = _clean_cell(cell)
            if cleaned is not None:
                rows.append(cleaned)
                break

    names = [name for name in rows if _looks_like_entity_name(name)]
    # Preserve first-seen order while dropping exact orthographic duplicates.
    unique: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = normalize_legal_name(name)
        if key is None or key in seen:
            continue
        seen.add(key)
        unique.append(name)

    if len(unique) < 1:
        return {"status": "unparseable", "names": [], "reason_code": "no_entity_table_rows"}
    return {"status": "parsed", "names": unique, "reason_code": None}


#: Zero-width, soft-hyphen, and bidi marks are HTML layout artifacts, not name
#: text.  A spacer cell built only from them must read as EMPTY: the leading-cell
#: scan stops at the first non-empty cell, so a surviving `​` would end the
#: scan on the spacer and silently drop the legal name in the next cell.
_INVISIBLE = re.compile(r"[\xad\u200b-\u200f\u2028\u2029\u2060\ufeff]")


def _clean_cell(cell: str) -> str | None:
    """Strip markup to the cell's plain text, resolving every character reference.

    ``html.unescape`` rather than a hand-listed replacement table, because the
    entities that actually appear in subsidiary names are the accented ones a
    short list never covers -- measured 2026-08-07 on the live exhibits, an
    eight-entity table left ``Palantir Technologies Geneva S&#224;rl`` and
    ``ComPetro Comunica&ccedil;&otilde;es Holdings do Brasil, Ltda.`` in the
    "verbatim" name.  That is not cosmetic here: the recipient record spells the
    same entity ``Sàrl``, the two normalize differently, and the exact match
    this whole wave rests on is refused for a name that is in fact identical.
    """
    text = _TAG.sub(" ", cell)
    text = html.unescape(text)
    text = _INVISIBLE.sub("", text).replace("\xa0", " ")
    text = _WS.sub(" ", text).strip()
    return text or None


_HEADER_WORDS = frozenset({
    "name", "names", "subsidiary", "subsidiaries", "entity", "jurisdiction",
    "state", "country", "incorporation", "organization", "ownership", "percent",
    "percentage", "of", "the", "registrant", "list", "exhibit",
})


def _looks_like_entity_name(name: str) -> bool:
    """Reject table headers, jurisdictions, and footnotes; keep entity names."""
    normal = normalize_legal_name(name)
    if normal is None:
        return False
    tokens = normal.split()
    if not (2 <= len(tokens) <= 14):
        return False
    if len(name) > 160:
        return False
    if all(token in _HEADER_WORDS for token in tokens):
        return False
    if normal.startswith("exhibit") or normal.startswith("subsidiaries of"):
        return False
    return True


def parse_recipient_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalize USAspending recipient search results to exact-identifier rows.

    The search endpoint ranks by relevance and returns unrelated recipients, so
    its output is an *enumeration* only.  Admission still requires the exact
    identifier plus a verbatim Exhibit 21 name, decided in
    ``engine.government_revenue.issuer_graph_expansion``.  Nothing here asserts
    a mapping.

    A RECORD WITH NO UEI IS STILL A RECORD.  USAspending publishes recipients
    that carry no registered UEI at all -- ``ARCTURUS UAV, INC.`` (AeroVironment's
    subsidiary) is one, measured 2026-08-07.  Dropping those here would make
    them invisible to the resolver, so its ``recipient_identifier_absent``
    refusal could never fire on real data and the coverage denominator would
    quietly shrink to only the rows that were already admissible.  They are
    carried through with ``uei=None`` and refused where refusals are RECORDED.
    """
    results = (payload or {}).get("results") or []
    rows: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, Mapping):
            continue
        name = _text(result.get("name"))
        uei = _text(result.get("uei"))
        if name is None:
            continue
        rows.append({
            "legal_name": name,
            "uei": uei.upper() if uei is not None else None,
            "recipient_level": _text(result.get("recipient_level")),
            "usaspending_recipient_id": _text(result.get("id")),
            "observed_award_amount": (
                float(result["amount"])
                if isinstance(result.get("amount"), (int, float))
                and not isinstance(result.get("amount"), bool)
                else None
            ),
        })
    return rows


# ---------------------------------------------------------------------------
# Receipts and the content-addressed store.
# ---------------------------------------------------------------------------


def build_evidence_receipt(
    *,
    evidence_id: str,
    publisher: str,
    evidence_class: str,
    record_id: str,
    url: str,
    body: bytes,
    retrieved_at: str,
    valid_from: str,
    claim_scopes: Sequence[str],
    valid_to: str | None = None,
) -> dict[str, Any]:
    """Bind one retrieval to a content-addressed, clock-stamped receipt.

    ``content_sha256`` is taken over the exact response bytes, and
    ``source_ref`` is derived from it, so the pair cannot disagree.  A
    downstream consumer re-verifies by re-hashing the stored or re-fetched body.
    """
    if not isinstance(body, (bytes, bytearray)):
        raise ExpansionInputError("evidence body must be bytes")
    body = bytes(body)
    if not body:
        raise ExpansionInputError("refusing to receipt an empty response body")
    digest = _sha256_bytes(body)
    return {
        "schema_version": ISSUER_EVIDENCE_RECEIPT_SCHEMA,
        "receipt_id": f"issuer-evidence:{digest[:24]}",
        "evidence_id": evidence_id,
        "source_ref": evidence_source_ref(digest),
        "publisher": publisher,
        "evidence_class": evidence_class,
        "record_id": record_id,
        "url": url,
        "content_sha256": digest,
        "byte_length": len(body),
        "retrieved_at": retrieved_at,
        "known_at": retrieved_at,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "claim_scopes": list(claim_scopes),
        "raw_response_body_persisted": False,
    }


def evidence_store_path(root: Path, content_sha256: str) -> Path:
    """Return the content-addressed path for a cached evidence document."""
    digest = (_text(content_sha256) or "").lower()
    if re.fullmatch(r"[a-f0-9]{64}", digest) is None:
        raise ExpansionInputError("content_sha256 must be a sha-256 hex digest")
    return Path(root) / ISSUER_EVIDENCE_STORE_DIRNAME / digest[:2] / f"{digest}.bin"


def store_evidence_document(root: Path, body: bytes) -> Path:
    """Write a document to the content-addressed store and return its path.

    The filename *is* the hash, so a tampered document cannot occupy the path
    of the document it replaced.
    """
    digest = _sha256_bytes(bytes(body))
    path = evidence_store_path(root, digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and _sha256_bytes(path.read_bytes()) == digest:
        return path
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(bytes(body))
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def read_verified_evidence(root: Path, content_sha256: str) -> bytes:
    """Read a stored document, failing closed when its hash no longer matches."""
    path = evidence_store_path(root, content_sha256)
    body = path.read_bytes()
    actual = _sha256_bytes(body)
    if actual != (_text(content_sha256) or "").lower():
        raise RuntimeError(
            f"stored evidence document does not match its content address: {path} "
            f"(expected {content_sha256}, found {actual})"
        )
    return body


def append_issuer_evidence_receipts(receipts: Sequence[Mapping[str, Any]], path: Path) -> dict[str, Any]:
    """Append-only receipt ledger, failing closed on unreadable history.

    Mirrors ``collectors/usaspending_awards.py::_append_collection_receipts`` so
    Government Revenue has one receipt idiom, not two.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = ""
    existing_ids: set[str] = set()
    if path.exists():
        try:
            existing_text = path.read_text(encoding="utf-8")
            for raw_line in existing_text.splitlines():
                if not raw_line.strip():
                    continue
                row = json.loads(raw_line)
                if not isinstance(row, dict) or not isinstance(row.get("receipt_id"), str):
                    raise ValueError("missing receipt_id")
                existing_ids.add(row["receipt_id"])
        except Exception as exc:  # noqa: BLE001 - preserve immutable receipt history
            raise RuntimeError(
                f"refusing to overwrite unreadable issuer evidence receipt ledger: "
                f"{path}: {_safe_error(exc)}"
            ) from exc

    new_lines: list[str] = []
    for receipt in receipts:
        receipt_id = receipt.get("receipt_id")
        if not isinstance(receipt_id, str) or not receipt_id:
            raise ValueError("issuer evidence receipt missing receipt_id")
        if receipt_id in existing_ids:
            continue
        new_lines.append(json.dumps(dict(receipt), sort_keys=True, separators=(",", ":")))
        existing_ids.add(receipt_id)

    if new_lines:
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            separator = "" if not existing_text or existing_text.endswith("\n") else "\n"
            tmp.write_text(
                existing_text + separator + "\n".join(new_lines) + "\n", encoding="utf-8"
            )
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()
    return {
        "schema_version": ISSUER_EVIDENCE_RECEIPT_SCHEMA,
        "path": ISSUER_EVIDENCE_RECEIPTS_FILENAME,
        "receipts_this_run": len(receipts),
        "new_receipts_this_run": len(new_lines),
        "receipts_total": len(existing_ids),
    }


# ---------------------------------------------------------------------------
# Bounded, polite retrieval.
# ---------------------------------------------------------------------------


@dataclass
class IssuerEvidenceCollector:
    """Bounded official-document retrieval for one or more issuers.

    ``fetch`` is injectable so nothing in the test suite touches the network;
    the default performs a real, rate-limited, retried HTTPS GET/POST.
    """

    user_agent: str = DEFAULT_USER_AGENT
    max_filings_per_issuer: int = MAX_FILINGS_PER_ISSUER
    max_recipient_pages: int = MAX_RECIPIENT_PAGES
    sec_min_interval: float = SEC_MIN_INTERVAL_SECONDS
    usaspending_min_interval: float = USASPENDING_MIN_INTERVAL_SECONDS
    fetch: Callable[..., tuple[int, bytes]] | None = None
    sleep: Callable[[float], None] = time.sleep
    _last_call: dict[str, float] = field(default_factory=dict, repr=False)
    requests_made: int = field(default=0, repr=False)

    def _throttle(self, host_class: str, minimum: float) -> None:
        last = self._last_call.get(host_class)
        now = time.monotonic()
        if last is not None:
            wait = minimum - (now - last)
            if wait > 0:
                self.sleep(wait)
        self._last_call[host_class] = time.monotonic()

    def _http(
        self, url: str, *, host_class: str, minimum: float, body: Mapping[str, Any] | None = None
    ) -> bytes:
        import requests  # imported lazily so the pure parsers need no network stack

        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        last_error: str | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._throttle(host_class, minimum)
            self.requests_made += 1
            try:
                if body is None:
                    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
                else:
                    response = requests.post(
                        url, headers={**headers, "Content-Type": "application/json"},
                        json=dict(body), timeout=REQUEST_TIMEOUT_SECONDS,
                    )
            except Exception as exc:  # noqa: BLE001 - retried, then surfaced
                last_error = _safe_error(exc)
                self.sleep(min(2.0 * attempt, 8.0))
                continue
            if response.status_code == 200:
                return response.content
            last_error = f"HTTP {response.status_code}"
            # 403 from SEC means the User-Agent was rejected; retrying is futile.
            if response.status_code in (400, 401, 403, 404):
                break
            self.sleep(min(2.0 * attempt, 8.0))
        raise RuntimeError(f"issuer evidence fetch failed for {url}: {last_error}")

    def _get(self, url: str, *, host_class: str, minimum: float) -> bytes:
        if self.fetch is not None:
            status, body = self.fetch(url, None)
            if status != 200:
                raise RuntimeError(f"issuer evidence fetch failed for {url}: HTTP {status}")
            return body
        return self._http(url, host_class=host_class, minimum=minimum)

    def _post(self, url: str, body: Mapping[str, Any], *, host_class: str, minimum: float) -> bytes:
        if self.fetch is not None:
            status, payload = self.fetch(url, dict(body))
            if status != 200:
                raise RuntimeError(f"issuer evidence fetch failed for {url}: HTTP {status}")
            return payload
        return self._http(url, host_class=host_class, minimum=minimum, body=body)

    # -- SEC ---------------------------------------------------------------

    def ticker_cik_map(self) -> dict[str, str]:
        body = self._get(SEC_TICKER_MAP_URL, host_class="sec", minimum=self.sec_min_interval)
        return parse_ticker_cik_map(json.loads(body.decode("utf-8")))

    def issuer_exhibit21(self, ticker: str, *, cik: str) -> dict[str, Any]:
        """Retrieve the latest 10-K Exhibit 21 for one issuer, with receipts.

        Returns ``{"status": ..., "names": [...], "receipts": [...]}``.  Every
        non-``ok`` status names a reason code and produces zero names.
        """
        cik_plain = str(int(cik))
        submissions_body = self._get(
            SEC_SUBMISSIONS_URL.format(cik=f"{int(cik):010d}"),
            host_class="sec", minimum=self.sec_min_interval,
        )
        submissions = json.loads(submissions_body.decode("utf-8"))
        filing = select_latest_10k(submissions)
        if filing is None:
            return {"status": "no_10k_filing", "names": [], "receipts": [], "filing": None}

        index_url = urljoin(
            SEC_ARCHIVE_BASE.format(cik=cik_plain, accession=filing["accession_plain"]),
            f"{filing['accession']}-index-headers.html",
        )
        index_body = self._get(index_url, host_class="sec", minimum=self.sec_min_interval)
        document = select_exhibit21_document(index_body)
        if document is None:
            return {
                "status": "no_exhibit21_declared", "names": [], "receipts": [], "filing": filing,
            }

        exhibit_url = urljoin(
            SEC_ARCHIVE_BASE.format(cik=cik_plain, accession=filing["accession_plain"]),
            document["name"],
        )
        exhibit_body = self._get(exhibit_url, host_class="sec", minimum=self.sec_min_interval)
        if len(exhibit_body) > MAX_EXHIBIT_BYTES:
            return {
                "status": "exhibit_exceeds_size_budget", "names": [], "receipts": [],
                "filing": filing,
            }
        parsed = parse_exhibit21_names(exhibit_body)
        retrieved_at = _now()
        period = filing.get("report_date") or filing.get("filing_date")
        receipt = build_evidence_receipt(
            evidence_id=f"evidence:{ticker.casefold()}-sec-{filing['accession']}-ex21",
            publisher="SEC",
            evidence_class="official_filing",
            record_id=f"sec:{cik_plain}:{filing['accession_plain']}:{document['name']}",
            url=exhibit_url,
            body=exhibit_body,
            retrieved_at=retrieved_at,
            valid_from=f"{period}T00:00:00+00:00" if period else retrieved_at,
            claim_scopes=["legal_entity", "ownership"],
        )
        return {
            "status": "ok" if parsed["status"] == "parsed" else "exhibit_unparseable",
            "names": parsed["names"],
            "reason_code": parsed.get("reason_code"),
            "filing": filing,
            "receipts": [receipt],
            "body": exhibit_body,
        }

    # -- USAspending -------------------------------------------------------

    def recipient_records(self, search_text: str) -> dict[str, Any]:
        """Enumerate official recipient records for one exact legal name.

        ``search_text`` comes from the issuer's own Exhibit 21, never from a
        ticker.  The endpoint ranks by relevance and returns unrelated
        recipients, so this is enumeration only -- admission is decided later
        by exact identifier plus verbatim name.
        """
        records: list[dict[str, Any]] = []
        receipts: list[dict[str, Any]] = []
        pages_read = 0
        has_next = False
        for page in range(1, self.max_recipient_pages + 1):
            # `keyword`, NOT `search_text`.  /api/v2/recipient/ silently IGNORES an
            # unknown filter key and answers with the unfiltered recipient
            # universe: measured 2026-08-07, `search_text` returned
            # page_metadata.total == 18,292,357 and the same global top-100 by
            # dollar amount for every query, while `keyword` returned total == 3
            # for the same name.  An ignored filter is the worst possible failure
            # here -- the caller still receives a plausible list of real federal
            # recipients, so the enumeration looks like evidence about the issuer
            # when it is actually the leaderboard.
            body = {
                "keyword": search_text,
                "limit": MAX_RECIPIENT_PAGE_SIZE,
                "page": page,
                "order": "desc",
                "sort": "amount",
            }
            raw = self._post(
                USASPENDING_RECIPIENT_SEARCH_URL, body,
                host_class="usaspending", minimum=self.usaspending_min_interval,
            )
            payload = json.loads(raw.decode("utf-8"))
            pages_read += 1
            page_rows = parse_recipient_records(payload)
            retrieved_at = _now()
            receipts.append(build_evidence_receipt(
                evidence_id=(
                    f"evidence:usaspending-recipient-"
                    f"{_sha256_json({'q': search_text, 'page': page})[:16]}"
                ),
                publisher="USAspending.gov",
                evidence_class="official_award",
                record_id=f"usaspending:recipient-search:{search_text}:page-{page}",
                url=USASPENDING_RECIPIENT_SEARCH_URL,
                body=raw,
                retrieved_at=retrieved_at,
                valid_from=retrieved_at,
                claim_scopes=["legal_entity", "exact_identifier"],
            ))
            records.extend(page_rows)
            has_next = bool(((payload or {}).get("page_metadata") or {}).get("hasNext"))
            if not has_next or not page_rows:
                break
        return {
            "records": records,
            "receipts": receipts,
            "pages_read": pages_read,
            "stopped_at_page_cap": has_next and pages_read >= self.max_recipient_pages,
            "search_text": search_text,
        }
