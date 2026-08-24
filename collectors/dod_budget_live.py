"""Live acquisition adapter for the DoD Comptroller FY P-1/R-1 exhibits.

This module supplies the piece ``collectors/dod_budget.py`` deliberately
leaves out: fetching the official PDF, writing+reading it back through the
canonical immutable object store, deriving the deterministic page text and
coordinate-word extraction the hermetic receipt/parse core consumes, the
production P-1/R-1 parsers (:func:`parse_official_p1_document` /
:func:`parse_official_r1_document`), and the CLI that runs the whole chain
and writes the receipt-bound triad.

Acquisition order is LAW (frozen design
``research/defense_intelligence/DEFENSE_D6A_BUDGET_RAIL_DESIGN_2026-08-24.md``
§4): fetch → sha256 → store PUT → strict bounded READBACK → byte/sha equality
→ only then may :func:`collectors.dod_budget.build_document_receipt` be
called. No receipt may exist for bytes that were not durably written and
verified. There is no fail-open local-store fallback anywhere in this
module's production path — a ``LocalStore`` is reachable only through an
explicit constructor argument a caller (a test) supplies directly.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pdfplumber

from collectors import dod_budget
from engine.research_vault.r2_store import BoundedStrictReadStore, R2Store, Store


# ---------------------------------------------------------------------------
# Frozen source constants — URLs live in code only, never CLI args or
# workflow inputs (research/defense_intelligence/DEFENSE_D6A_BUDGET_RAIL_DESIGN_2026-08-24.md §1).
# ---------------------------------------------------------------------------

DOD_BUDGET_CANARY_FISCAL_YEAR = 2027
DOD_BUDGET_P1_CANARY_URL = (
    "https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_p1.pdf"
)
DOD_BUDGET_R1_CANARY_URL = (
    "https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_r1.pdf"
)
DOD_BUDGET_CANARIES: tuple[dict[str, Any], ...] = (
    {"url": DOD_BUDGET_P1_CANARY_URL, "exhibit": "p1", "fiscal_year": DOD_BUDGET_CANARY_FISCAL_YEAR},
    {"url": DOD_BUDGET_R1_CANARY_URL, "exhibit": "r1", "fiscal_year": DOD_BUDGET_CANARY_FISCAL_YEAR},
)

# The production parser has not landed (Stage 2b, delivered separately); this
# constant is frozen now so every receipt this module produces already
# carries the exact version string the eventual parser will also record —
# receipts never need to be re-observed just because the parser landed later.
DOD_BUDGET_LIVE_PARSER_VERSION = "dod-budget-fy2027-official-text.v1"

_PDF_MAGIC = b"%PDF"
FETCH_TIMEOUT_SECONDS = 120.0
MAX_PDF_BYTES = 64 * 1024 * 1024  # 64 MiB hard acquisition cap
_FETCH_CHUNK_BYTES = 1024 * 1024

# Deterministic pdfplumber tolerances (fixed, not layout-adaptive). The
# production parser (Stage 2b) derives column intervals from header
# positions; the extractor itself must not vary run to run.
EXTRACT_TEXT_X_TOLERANCE = 2.0
EXTRACT_TEXT_Y_TOLERANCE = 2.0
EXTRACT_WORDS_X_TOLERANCE = 2.0
EXTRACT_WORDS_Y_TOLERANCE = 2.0
_WORD_COORDINATE_KEYS = ("text", "x0", "x1", "top", "bottom", "doctop")

EXTRACTOR_VERSION = f"pdfplumber-{pdfplumber.__version__}-text+words.v1"


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


class DodBudgetFetchRefused(RuntimeError):
    """The official PDF fetch failed a hermetic acquisition check."""


@dataclass(frozen=True)
class FetchedPdf:
    """Bytes acquired from one allowlisted official HTTPS URL, unstored."""

    source_url: str
    final_url: str
    content: bytes
    sha256: str


def fetch_official_pdf(
    url: str,
    *,
    session: Any = None,
    timeout: float = FETCH_TIMEOUT_SECONDS,
    max_bytes: int = MAX_PDF_BYTES,
) -> FetchedPdf:
    """GET one allowlisted official PDF with every hostile check fail-closed.

    Redirects are DISALLOWED outright (the host serves 200 directly; any 3xx
    response is refused, never followed). The response is streamed under a
    hard byte cap, TLS is verified, and the final content must start with the
    ``%PDF`` magic. ``final_url`` is re-validated through the same hermetic
    :func:`collectors.dod_budget._official_https_url` gate as ``source_url``.
    """
    checked_url = dod_budget._official_https_url(url)
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout <= 0
    ):
        raise ValueError("DoD budget fetch timeout must be a positive number")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("DoD budget fetch byte cap must be a positive integer")
    transport = session
    if transport is None:
        import requests as _requests

        transport = _requests
    try:
        response = transport.get(
            checked_url, timeout=timeout, allow_redirects=False, stream=True, verify=True,
        )
    except Exception as exc:  # noqa: BLE001 - any transport failure is a refusal
        raise DodBudgetFetchRefused(f"DoD budget PDF fetch failed: {exc}") from exc
    try:
        status = getattr(response, "status_code", None)
        if isinstance(status, bool) or not isinstance(status, int):
            raise DodBudgetFetchRefused("DoD budget PDF fetch returned no usable status code")
        if 300 <= status < 400:
            raise DodBudgetFetchRefused(
                f"DoD budget PDF fetch refused a redirect (status {status}); "
                "the official host must serve 200 directly"
            )
        if status != 200:
            raise DodBudgetFetchRefused(f"DoD budget PDF fetch returned status {status}")
        final_url = str(getattr(response, "url", None) or checked_url)
        if final_url != checked_url:
            raise DodBudgetFetchRefused(
                "DoD budget PDF fetch final URL diverged from the requested URL"
            )
        chunks: list[bytes] = []
        total = 0
        iter_content = getattr(response, "iter_content", None)
        if not callable(iter_content):
            raise DodBudgetFetchRefused("DoD budget PDF fetch response cannot be streamed")
        for chunk in iter_content(chunk_size=_FETCH_CHUNK_BYTES):
            if not chunk:
                continue
            if not isinstance(chunk, bytes):
                raise DodBudgetFetchRefused("DoD budget PDF fetch returned a non-bytes chunk")
            total += len(chunk)
            if total > max_bytes:
                raise DodBudgetFetchRefused(
                    f"DoD budget PDF exceeds the {max_bytes}-byte acquisition cap"
                )
            chunks.append(chunk)
        content = b"".join(chunks)
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
    if not content.startswith(_PDF_MAGIC):
        raise DodBudgetFetchRefused("DoD budget PDF fetch did not return a %PDF byte stream")
    digest = dod_budget._sha256(content)
    verified_final_url = dod_budget._official_https_url(final_url)
    return FetchedPdf(
        source_url=checked_url, final_url=verified_final_url, content=content, sha256=digest,
    )


# ---------------------------------------------------------------------------
# Immutable object store (models engine.capital_structure.source_store's
# ContentAddressedSourceStore fail-closed put→readback order, keyed under
# collectors.dod_budget.IMMUTABLE_R2_PREFIX instead of the SEC prefix).
# ---------------------------------------------------------------------------


class DodBudgetStoreUnavailable(RuntimeError):
    """No object store could be resolved; acquisition refuses without a receipt."""


class DodBudgetStoreWriteFailed(RuntimeError):
    """The object store rejected (or raised on) the PDF write."""


class DodBudgetStoreReadbackFailed(RuntimeError):
    """The strict bounded readback did not return the exact written bytes."""


def immutable_object_key_for_pdf(pdf_bytes: bytes) -> str:
    """Return the content-addressed key for *pdf_bytes* under the frozen prefix."""
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(_PDF_MAGIC):
        raise ValueError("DoD budget object is not a PDF byte stream")
    digest = dod_budget._sha256(pdf_bytes)
    return f"{dod_budget.IMMUTABLE_R2_PREFIX}{digest}.pdf"


def put_and_verify_pdf(
    store: Store, pdf_bytes: bytes, *, max_bytes: int = MAX_PDF_BYTES,
) -> str:
    """PUT one PDF and require an exact strict-bounded readback before trusting it.

    Order is law: PUT, then a bounded READBACK, then byte-for-byte AND
    sha256-for-sha256 equality — only then is the immutable object key
    returned. A key that already holds different bytes than what was just
    written (a store-level identity violation) fails the same equality check
    and is refused identically to any other readback mismatch.
    """
    key = immutable_object_key_for_pdf(pdf_bytes)
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < len(pdf_bytes):
        raise ValueError("DoD budget store byte cap must cover the exact PDF length")
    try:
        wrote = store.put_bytes(key, pdf_bytes, content_type="application/pdf")
    except Exception as exc:  # noqa: BLE001 - a raising backend is still a refusal
        raise DodBudgetStoreWriteFailed(f"DoD budget object write raised: {exc}") from exc
    if not wrote:
        raise DodBudgetStoreWriteFailed("DoD budget object store rejected the write")
    if not isinstance(store, BoundedStrictReadStore):
        raise DodBudgetStoreUnavailable(
            "DoD budget object store lacks bounded strict-read capability"
        )
    try:
        readback = store.get_bytes_strict_bounded(
            key, expected_byte_length=len(pdf_bytes), max_byte_length=max_bytes,
        )
    except Exception as exc:  # noqa: BLE001 - no fail-open readback fallback
        raise DodBudgetStoreReadbackFailed(
            f"DoD budget object readback raised: {exc}"
        ) from exc
    if (
        not isinstance(readback, bytes)
        or readback != pdf_bytes
        or dod_budget._sha256(readback) != dod_budget._sha256(pdf_bytes)
    ):
        raise DodBudgetStoreReadbackFailed(
            "DoD budget object readback did not match the written bytes"
        )
    return key


def _dod_budget_r2_client():
    """Construct the shared-account R2 client, or ``None`` when creds are absent."""
    endpoint = os.environ.get("R2_ENDPOINT")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (endpoint and access_key and secret_key):
        return None
    import boto3
    from botocore.config import Config

    kwargs = dict(
        region_name="auto",
        signature_version="s3v4",
        max_pool_connections=8,
        retries={"max_attempts": 5, "mode": "adaptive"},
        connect_timeout=15,
        read_timeout=120,
    )
    try:
        config = Config(
            **kwargs,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
    except TypeError:
        config = Config(**kwargs)
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=config,
    )


def build_default_store() -> Store | None:
    """Resolve the production immutable R2 store; never a local fallback.

    Only the standard ``R2_BUCKET``/``R2_ENDPOINT``/``R2_ACCESS_KEY_ID``/
    ``R2_SECRET_ACCESS_KEY`` env ladder is consulted. A ``LocalStore`` is
    reachable only through the explicit ``store`` argument a caller (a test)
    passes directly to :func:`acquire_official_document` — never selected
    here from an environment variable — so a misconfigured production run
    refuses cleanly instead of silently falling back to a local disk store
    nothing downstream will ever read (frozen design §4: "no fail-open local
    fallback in the production path").
    """
    bucket = os.environ.get("R2_BUCKET")
    if not bucket:
        return None
    store = R2Store(bucket, client=_dod_budget_r2_client())
    return store if store.available else None


# ---------------------------------------------------------------------------
# Deterministic extraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractedDocument:
    """Per-page plain-text renderings and words-with-coordinates from one PDF."""

    page_texts: tuple[str, ...]
    page_words: tuple[tuple[dict[str, Any], ...], ...]


def extract_pages(pdf_bytes: bytes) -> ExtractedDocument:
    """Render every page's plain text AND words-with-coordinates via pdfplumber.

    Both derive from the same bytes at fixed tolerances. The plain-text
    rendering is what receipts bind (``page_text_sha256s``); the
    words-with-coordinates rendering is the production parser's (Stage 2b)
    input and is never hashed into the receipt itself.
    """
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(_PDF_MAGIC):
        raise ValueError("DoD budget extraction input is not a PDF byte stream")
    page_texts: list[str] = []
    page_words: list[tuple[dict[str, Any], ...]] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(
                x_tolerance=EXTRACT_TEXT_X_TOLERANCE, y_tolerance=EXTRACT_TEXT_Y_TOLERANCE,
            ) or ""
            words = page.extract_words(
                x_tolerance=EXTRACT_WORDS_X_TOLERANCE, y_tolerance=EXTRACT_WORDS_Y_TOLERANCE,
            )
            page_texts.append(text)
            page_words.append(tuple(
                {key: word.get(key) for key in _WORD_COORDINATE_KEYS} for word in words
            ))
    return ExtractedDocument(page_texts=tuple(page_texts), page_words=tuple(page_words))


# ---------------------------------------------------------------------------
# Idempotence gate + receipt orchestration
# ---------------------------------------------------------------------------

_RECEIPT_IDENTITY_KEYS = (
    "source_url", "content_sha256", "extraction_semantic_sha256",
    "extractor_version", "parser_version",
)


def receipt_is_duplicate(
    existing_receipts: Iterable[Mapping[str, Any]], candidate: Mapping[str, Any],
) -> bool:
    """True when an existing receipt already covers this exact observation.

    Coverage is (source_url, content_sha256, extraction_semantic_sha256,
    extractor_version, parser_version) — the same bytes, extracted the same
    way, by the same parser generation, from the same URL. A match means: no
    new receipt, no new line versions, report a no-op.
    """
    candidate_key = tuple(candidate.get(key) for key in _RECEIPT_IDENTITY_KEYS)
    for row in existing_receipts:
        if tuple(row.get(key) for key in _RECEIPT_IDENTITY_KEYS) == candidate_key:
            return True
    return False


@dataclass(frozen=True)
class AcquisitionOutcome:
    """One acquisition attempt's result: the receipt, extraction, and novelty."""

    receipt: dict[str, Any]
    extracted: ExtractedDocument
    is_new_receipt: bool


def acquire_official_document(
    *,
    url: str,
    exhibit: str,
    fiscal_year: int,
    store: Store | None,
    existing_receipts: Sequence[Mapping[str, Any]] = (),
    session: Any = None,
    observed_at: str | datetime | None = None,
    timeout: float = FETCH_TIMEOUT_SECONDS,
    max_bytes: int = MAX_PDF_BYTES,
) -> AcquisitionOutcome:
    """Fetch → store (put+readback) → extract → receipt, in that fixed order.

    ``store`` must be pre-resolved by the caller (production:
    :func:`build_default_store`; tests: an injected fake or ``LocalStore``).
    ``store is None`` refuses immediately — no fetch is even attempted — so a
    misconfigured production run never spends a live HTTP request it cannot
    durably store the result of.
    """
    if store is None:
        raise DodBudgetStoreUnavailable(
            "DoD budget object store is unavailable; refusing acquisition without a receipt"
        )
    fetched = fetch_official_pdf(url, session=session, timeout=timeout, max_bytes=max_bytes)
    extracted = extract_pages(fetched.content)
    immutable_object_key = put_and_verify_pdf(store, fetched.content, max_bytes=max_bytes)
    receipt = dod_budget.build_document_receipt(
        source_url=fetched.source_url,
        final_url=fetched.final_url,
        pdf_bytes=fetched.content,
        pages=extracted.page_texts,
        fiscal_year=fiscal_year,
        exhibit=exhibit,
        observed_at=observed_at if observed_at is not None else datetime.now(timezone.utc),
        immutable_object_key=immutable_object_key,
        extractor_version=EXTRACTOR_VERSION,
        parser_version=DOD_BUDGET_LIVE_PARSER_VERSION,
    )
    is_new = not receipt_is_duplicate(existing_receipts, receipt)
    return AcquisitionOutcome(receipt=receipt, extracted=extracted, is_new_receipt=is_new)


# ---------------------------------------------------------------------------
# Production P-1/R-1 parser (Stage 2b).
#
# Algorithmic basis: the Stage 1/2a survey harness (scratchpad
# survey_common.py / survey_p1.py / survey_r1.py / survey_p1_reconcile.py /
# survey_scn_1611.py), proven against the real FY2027 exhibits: full 3-level
# reconciliation (24/24 BA-Summary-internal, 81/81 detail-close-vs-BA-summary,
# 24/24 appropriation-level), SCN(1611) typed-row-model closure exact to
# $0.00 on all 4 BAs, and (Stage 2b gate-zero) the SAME typed-model closure
# extended document-wide (81/81 P-1 BA groups, 103/103 R-1 BA subtotals,
# 28/28 R-1 appropriation totals) after fixing the harness's bare-minus
# sign-drop bug. §5b.1 gate-zero rulings (frozen in
# research/defense_intelligence/DEFENSE_D6A_BUDGET_RAIL_DESIGN_2026-08-24.md)
# are LAW for this parser: sign forms, zero-numbered-line partition
# exclusion, printed-addend grain (parent + additive-child records, never a
# sum), BA-slug line identity, R-1 0400D consolidated-only emission, and the
# "20 20" classification fix. Every emitted row goes through
# collectors.dod_budget's PUBLIC wrappers so every identity/semantic/state-
# hash invariant is enforced by the same hermetic code the fixture parser
# uses. Any row, page, or arithmetic shape this module cannot positively
# classify or reconcile REFUSES THE WHOLE DOCUMENT — there is no plausible
# partial-row fallback anywhere below.
# ---------------------------------------------------------------------------


class DodBudgetParseRefused(ValueError):
    """The document failed a hermetic P-1/R-1 parsing or reconciliation check."""


_NUM_TOKEN_RE = re.compile(r"^\(?-?[\d,]+(?:\.\d+)?\)?$")


def _is_numeric_token(tok: str) -> bool:
    return bool(_NUM_TOKEN_RE.match(tok.strip()))


def _parse_signed_number(tok: str) -> float:
    """Parse one printed numeric token under the frozen sign law (§5b.1 #1).

    Recognized forms only: plain (``123``), paren-negative (``(123)``),
    paren-AND-bare-minus (``(-123)``, never observed but defensive), and
    bare-minus (``-123`` — P-1 p.108 DON-Other/TTNT lines print exactly this
    form with no wrapping parens). Anything else refuses.
    """
    text = tok.strip()
    if not _is_numeric_token(text):
        raise DodBudgetParseRefused(f"unrecognized numeric token form: {tok!r}")
    neg = False
    core = text
    if core.startswith("(") and core.endswith(")"):
        neg = True
        core = core[1:-1]
    if core.startswith("-"):
        neg = True
        core = core[1:]
    core = core.replace(",", "")
    if core in ("", "-"):
        raise DodBudgetParseRefused(f"unrecognized numeric token form: {tok!r}")
    try:
        value = float(core)
    except ValueError as exc:
        raise DodBudgetParseRefused(f"unrecognized numeric token form: {tok!r}") from exc
    if not math.isfinite(value):
        raise DodBudgetParseRefused(f"unrecognized numeric token form: {tok!r}")
    return -value if neg else value


def _cluster_lines(words: Sequence[Mapping[str, Any]], tol: float = 2.2) -> list[list[dict[str, Any]]]:
    words_sorted = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    cur_top: float | None = None
    for w in words_sorted:
        if cur_top is None or abs(w["top"] - cur_top) <= tol:
            cur.append(w)
            cur_top = w["top"] if cur_top is None else min(cur_top, w["top"])
        else:
            cur.sort(key=lambda w: w["x0"])
            lines.append(cur)
            cur = [w]
            cur_top = w["top"]
    if cur:
        cur.sort(key=lambda w: w["x0"])
        lines.append(cur)
    return lines


def _line_text(words: Sequence[Mapping[str, Any]]) -> str:
    return " ".join(str(w["text"]) for w in words)


def _slug(value: Any) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", str(value).casefold()).strip("-")
    if not result:
        raise DodBudgetParseRefused("printed label cannot be normalized into an identifier")
    return result


def _strip_trailing_numeric_tail(text: str) -> str:
    """Strip a trailing run of printed numeric tokens (a row's own values,
    glued onto its label by the line-text space-join) leaving the label."""
    toks = text.split(" ")
    while toks and _is_numeric_token(toks[-1]):
        toks.pop()
    return " ".join(toks).strip()


def _unit_marker_present(page_text: str) -> bool:
    return "(Dollars in Thousands)" in page_text


# ---------------------------------------------------------------------------
# R-1 parser
# ---------------------------------------------------------------------------

_R1_COLS = (
    "fy25_actuals", "fy26_disc_enacted", "fy26_pl119_spend_plan",
    "fy26_total", "fy27_disc_request", "fy27_mandatory_request", "fy27_total",
)
_R1_VALUE_HEADER_WORDS = {"Actuals", "Enacted", "Plan", "Total", "Request"}

_R1_BA_TITLES = {
    "basic research", "applied research", "advanced technology development",
    "advanced component development and prototypes",
    "system development and demonstration", "management support",
    "operational system development",
    "software and digital technology pilot programs",
    # Golden Dome for America Fund (3007D) uses its own O&M/Procurement/RDTE-
    # style BA vocabulary, always with a trailing footnote asterisk (stripped
    # before matching); the 3 "Not Included In RDT&E Title" appropriations
    # each carry exactly one BA with this generic title.
    "operation and maintenance", "procurement", "research, dev, test & eval",
    "research, development, test, and evaluation",
}
_R1_FURNITURE_EXACT = {
    "UNCLASSIFIED", "THIS PAGE INTENTIONALLY LEFT BLANK",
    # Component/department furniture line. Usually "Department of X" (a
    # prefix match below) but "Defense-Wide" prints bare, with no "Department
    # of" prefix, for the Defense-Wide RDT&E appropriation (0400D) sections
    # (verified: FY2027 R-1 p.66).
    "Defense-Wide",
}
_R1_FURNITURE_PREFIXES = (
    "Department of", "FY 2027 President's Budget", "Exhibit R-1",
    "Total Obligational Authority", "Non RDTE Title", "(Dollars in Thousands)", "Page ",
    "Program FY", "Line Element FY", "No Number Item Act Sec",
    "FY 2026 FY 2026 PL FY 2027 FY 2027",
    "FY 2025 Discretionary 119-21 FY 2026 Discretionary Mandatory FY 2027",
    "Actuals Enacted Spend Plan Total", "Actuals Enacted Spend Plan Total*",
    "Appropriation Actuals Enacted Spend Plan Total", "RDT&E PROGRAMS (R-1)",
    "Department of War Budget", "Fiscal Year 2027", "April 2026",
    "Office of the Under Secretary of War (Comptroller)", "Preface",
)
_R1_SECTION_HEADER_PREFIXES = (
    "Summary Recap of Budget Activities", "Summary Recap of FYDP Programs",
    "Summary Recap of Non-FYDP Programs",
    "Other RDT&E Budget Activities Not Included",
    "TABLE OF CONTENTS",
)
_R1_FOOTNOTE_PREFIX = "*Budget activities unique to"
_R1_APPROP_HEADER_RE = re.compile(r"^Appropriation:\s*(\S+)\s+(.*)$")
_R1_GRAND_TOTAL_TEXTS = {
    "Total Research, Development, Test, & Evaluation",
    "Total Not in Research, Development, Test, & Evaluation",
}
_R1_APPROP_TOTAL_RE = re.compile(r"^Total\s+(.+)$")
_R1_LINE_START_RE = re.compile(r"^(\d{1,4})\s+(\d{7,9}[A-Z0-9]{0,3})\s+(.*)$")
_R1_BA_TITLES_SORTED = sorted(_R1_BA_TITLES, key=len, reverse=True)

DOD_BUDGET_R1_DEFENSE_WIDE_CODE = "0400D"
# The Defense-Wide RDT&E appropriation prints its own consolidated table
# (pp.66-83 in the FY2027 exhibit) followed by a NON-ADDITIVE per-agency
# re-itemization of the SAME money (pp.89+, §5b rule 9 / §5b.1 ruling 5).
# Pages are receipt-bound (numbered from the SAME extracted document), so
# this constant is bound to page NUMBER, not a fixed page-count assumption
# about future fiscal years — a future exhibit whose consolidated table runs
# past this boundary will simply refuse via the hard pp.89+-vs-consolidated
# check below rather than silently misclassifying pages.
DOD_BUDGET_R1_DEFENSE_WIDE_CONSOLIDATED_MAX_PAGE = 88


def _r1_find_value_anchors(lines: Sequence[Sequence[Mapping[str, Any]]]):
    best = None
    for idx, lw in enumerate(lines):
        matches = [w for w in lw if str(w["text"]).rstrip("*") in _R1_VALUE_HEADER_WORDS]
        if len(matches) == 7:
            texts = [str(w["text"]).rstrip("*") for w in sorted(matches, key=lambda w: w["x0"])]
            if texts == ["Actuals", "Enacted", "Plan", "Total", "Request", "Request", "Total"]:
                best = (idx, sorted(w["x1"] for w in matches))
    return best


def _r1_assign_to_column(x1: float, anchors: Sequence[float], tol: float = 28.0) -> int | None:
    best_i, best_d = None, None
    for i, a in enumerate(anchors):
        d = abs(x1 - a)
        if best_d is None or d < best_d:
            best_d, best_i = d, i
    if best_d is not None and best_d <= tol:
        return best_i
    return None


def _r1_classify_furniture(text: str) -> bool:
    if text in _R1_FURNITURE_EXACT:
        return True
    for p in _R1_FURNITURE_PREFIXES:
        if text.startswith(p):
            return True
    if text.startswith("Page ") and text.split()[-1].isdigit():
        return True
    return False


def _r1_extract_numeric_row(line_words, anchors, min_x0: float = 336.0):
    slots: list[float | None] = [None] * 7
    unassigned: list[tuple[str, float, float]] = []
    for w in line_words:
        tok = str(w["text"])
        if w["x0"] < min_x0 or not _is_numeric_token(tok):
            continue
        col = _r1_assign_to_column(w["x1"], anchors)
        if col is None:
            unassigned.append((tok, w["x0"], w["top"]))
            continue
        val = _parse_signed_number(tok)
        if slots[col] is not None:
            unassigned.append((tok, w["x0"], w["top"]))
            continue
        slots[col] = val
    return slots, unassigned


def _r1_classify_document(pages: Sequence[str], pages_words: Sequence[Sequence[Mapping[str, Any]]]):
    """Classify every R-1 page into the closed row taxonomy. Refuses on any
    row this classifier cannot positively identify."""
    detail_lines: list[dict[str, Any]] = []
    ba_subtotal_rows: list[dict[str, Any]] = []
    appropriation_total_rows: list[dict[str, Any]] = []

    current_department: str | None = None
    current_appropriation_code: str | None = None
    current_appropriation_name: str | None = None
    pending_item_row: dict[str, Any] | None = None
    event_seq = [0]

    def next_seq() -> int:
        event_seq[0] += 1
        return event_seq[0]

    for pno, (page_text, words) in enumerate(zip(pages, pages_words)):
        page_num = pno + 1
        if not words:
            continue
        lines = _cluster_lines(words)
        full_text = "\n".join(_line_text(l) for l in lines)

        if "THIS PAGE INTENTIONALLY LEFT BLANK" in full_text:
            continue
        if page_num == 1 and "RDT&E PROGRAMS (R-1)" in full_text:
            continue
        if full_text.strip().startswith("UNCLASSIFIED\nPreface"):
            continue
        if "TABLE OF CONTENTS" in full_text:
            continue

        anchor_result = _r1_find_value_anchors(lines)
        if anchor_result is None:
            raise DodBudgetParseRefused(f"R-1 page {page_num} has no recognizable 7-column header")
        header_row_idx, anchors = anchor_result
        is_detail_page = any(
            "No Number Item Act Sec" in _line_text(l) for l in lines[: header_row_idx + 1]
        )
        if not _unit_marker_present(page_text):
            raise DodBudgetParseRefused(f"R-1 page {page_num} table lacks the '(Dollars in Thousands)' unit marker")

        # The component/department furniture line is POSITIONAL, not a fixed
        # vocabulary: it always sits immediately after "UNCLASSIFIED" and
        # immediately before "FY 2027 President's Budget" on every page.
        # Usually "Department of X" (a component service branch) or the bare
        # "Defense-Wide" label, but the pp.89+ per-agency re-itemization
        # sections (verification-only, §5b.1 ruling 5) print the AGENCY name
        # itself in this exact slot ("Classified Organization", "Chemical
        # and Biological Defense Program", ... — the same vocabulary the
        # "Total <Agency>" closing rows use). Matching by position, not by a
        # closed name list, is required because that agency-name set is not
        # enumerable in advance.
        department_line_idx: int | None = None
        uncls_idx: int | None = None
        for idx, l in enumerate(lines[:8]):
            t = _line_text(l)
            if t == "UNCLASSIFIED":
                uncls_idx = idx
            elif t.startswith("FY 2027 President's Budget") and uncls_idx is not None:
                if idx == uncls_idx + 2:
                    department_line_idx = uncls_idx + 1
                break
        if department_line_idx is not None:
            current_department = _line_text(lines[department_line_idx]).strip()

        for idx, lw in enumerate(lines):
            if idx == department_line_idx:
                continue
            text = _line_text(lw)
            if not text.strip():
                continue
            if _r1_classify_furniture(text):
                continue
            if any(text.startswith(p) for p in _R1_SECTION_HEADER_PREFIXES):
                continue
            if text.startswith(_R1_FOOTNOTE_PREFIX):
                continue
            if idx == header_row_idx:
                continue

            m_appr = _R1_APPROP_HEADER_RE.match(text)
            if m_appr:
                if m_appr.group(1) != current_appropriation_code:
                    pending_item_row = None
                current_appropriation_code = m_appr.group(1)
                current_appropriation_name = m_appr.group(2).strip()
                continue

            m_line = _R1_LINE_START_RE.match(text)
            if m_line and is_detail_page:
                line_no, pe, rest = m_line.groups()
                slots, unassigned = _r1_extract_numeric_row(lw, anchors)
                if unassigned:
                    raise DodBudgetParseRefused(
                        f"R-1 page {page_num} detail line has an unassignable numeric token: {unassigned!r}"
                    )
                act = None
                sec = None
                name_tokens: list[str] = []
                for w in lw:
                    wt = str(w["text"])
                    if wt in (line_no, pe):
                        continue
                    if 283 <= w["x0"] <= 312 and re.fullmatch(r"\d{2}", wt):
                        act = wt
                        continue
                    if 312 <= w["x0"] <= 333 and re.fullmatch(r"[A-Z]", wt):
                        sec = wt
                        continue
                    if _is_numeric_token(wt) and w["x0"] >= 336.0:
                        continue
                    name_tokens.append(wt)
                if act is None:
                    raise DodBudgetParseRefused(
                        f"R-1 page {page_num} detail line {line_no}/{pe} has no budget-activity code"
                    )
                row = {
                    "page": page_num, "line_no": line_no, "pe": pe,
                    "name": " ".join(name_tokens), "act": act, "sec": sec,
                    "values": slots,
                    "appropriation_code": current_appropriation_code,
                    "appropriation_name": current_appropriation_name,
                    "department": current_department,
                    "_evseq": next_seq(),
                }
                detail_lines.append(row)
                pending_item_row = row
                continue

            has_value_numbers = any(
                _is_numeric_token(str(w["text"])) and w["x0"] >= 336.0 for w in lw
            )
            low = text.strip().casefold().replace("*", "")
            matched_title = None
            for t in _R1_BA_TITLES_SORTED:
                if low == t or low.startswith(t + " "):
                    matched_title = t
                    break
            if matched_title is not None and is_detail_page and has_value_numbers:
                slots, unassigned = _r1_extract_numeric_row(lw, anchors)
                if unassigned:
                    raise DodBudgetParseRefused(
                        f"R-1 page {page_num} BA subtotal has an unassignable numeric token: {unassigned!r}"
                    )
                ba_subtotal_rows.append({
                    "page": page_num, "title": matched_title, "values": slots,
                    "appropriation_code": current_appropriation_code,
                    "appropriation_name": current_appropriation_name,
                    "department": current_department,
                    "_evseq": next_seq(),
                })
                pending_item_row = None
                continue

            m_tot = _R1_APPROP_TOTAL_RE.match(text)
            if m_tot and is_detail_page and text not in _R1_GRAND_TOTAL_TEXTS:
                slots, unassigned = _r1_extract_numeric_row(lw, anchors)
                if unassigned:
                    raise DodBudgetParseRefused(
                        f"R-1 page {page_num} appropriation total has an unassignable numeric token: {unassigned!r}"
                    )
                appropriation_total_rows.append({
                    "page": page_num, "raw": text,
                    "closes_label": m_tot.group(1).strip(),
                    "values": slots,
                    "appropriation_code": current_appropriation_code,
                    "appropriation_name": current_appropriation_name,
                    "department": current_department,
                    "_evseq": next_seq(),
                })
                pending_item_row = None
                continue
            if m_tot and not is_detail_page:
                # Grand/section-recap total row on a summary page: evidence
                # only, never fed to reconciliation or publication.
                pending_item_row = None
                continue

            has_numbers = any(_is_numeric_token(str(w["text"])) and w["x0"] >= 336.0 for w in lw)
            if not has_numbers:
                xs = [w["x0"] for w in lw]
                if pending_item_row is not None and xs and min(xs) < 340 and min(xs) > 40:
                    pending_item_row["name"] = (pending_item_row["name"] + " " + text).strip()
                    continue
                # unrecognized label-only row: evidence-only on summary pages
                if not is_detail_page:
                    continue
                raise DodBudgetParseRefused(f"R-1 page {page_num} has an unclassified label-only row: {text!r}")

            if not is_detail_page:
                # numeric row on a summary/recap page carrying no recognized
                # shape: evidence only (never fed to reconciliation)
                pending_item_row = None
                continue

            raise DodBudgetParseRefused(
                f"R-1 page {page_num} has an unclassified numeric row on a detail page: {text!r}"
            )

    if not detail_lines:
        raise DodBudgetParseRefused("R-1 document produced no detail lines")
    return detail_lines, ba_subtotal_rows, appropriation_total_rows


def _r1_reconcile(detail_lines, ba_subtotal_rows, appropriation_total_rows) -> None:
    """Sequential-buffer reconciliation (proven Stage 1): every BA subtotal
    and appropriation total closes its immediately preceding run of detail
    lines/subtotals exactly. Any residual refuses."""
    merged = sorted(
        [("line", r) for r in detail_lines]
        + [("subtotal", r) for r in ba_subtotal_rows]
        + [("apprtotal", r) for r in appropriation_total_rows],
        key=lambda t: t[1]["_evseq"],
    )
    buf: list[dict[str, Any]] = []
    appr_buf: list[dict[str, Any]] = []
    for kind, row in merged:
        if kind == "line":
            buf.append(row)
        elif kind == "subtotal":
            sums = [0.0] * 7
            present = [False] * 7
            for r in buf:
                for c in range(7):
                    if r["values"][c] is not None:
                        sums[c] += r["values"][c]
                        present[c] = True
            expected = row["values"]
            for c in range(7):
                if expected[c] is None:
                    if present[c]:
                        raise DodBudgetParseRefused(
                            f"R-1 BA subtotal on page {row['page']} omits a populated column {_R1_COLS[c]}"
                        )
                    continue
                actual = sums[c] if present[c] else 0.0
                if not math.isclose(actual, expected[c], rel_tol=0.0, abs_tol=0.01):
                    raise DodBudgetParseRefused(
                        f"R-1 BA subtotal on page {row['page']} ({row['title']}) mismatch on {_R1_COLS[c]}: "
                        f"computed {actual} printed {expected[c]}"
                    )
            appr_buf.append(row)
            buf = []
        elif kind == "apprtotal":
            sums = [0.0] * 7
            present = [False] * 7
            for r in appr_buf:
                for c in range(7):
                    if r["values"][c] is not None:
                        sums[c] += r["values"][c]
                        present[c] = True
            expected = row["values"]
            for c in range(7):
                if expected[c] is None:
                    if present[c]:
                        raise DodBudgetParseRefused(
                            f"R-1 appropriation total on page {row['page']} omits a populated column {_R1_COLS[c]}"
                        )
                    continue
                actual = sums[c] if present[c] else 0.0
                if not math.isclose(actual, expected[c], rel_tol=0.0, abs_tol=0.01):
                    raise DodBudgetParseRefused(
                        f"R-1 appropriation total on page {row['page']} ({row['raw']}) mismatch on {_R1_COLS[c]}: "
                        f"computed {actual} printed {expected[c]}"
                    )
            if buf:
                raise DodBudgetParseRefused(
                    f"R-1 page {row['page']}: {len(buf)} detail line(s) never folded into a BA subtotal "
                    "before the appropriation total"
                )
            appr_buf = []
    if buf:
        raise DodBudgetParseRefused(
            f"R-1 document ends with {len(buf)} trailing detail line(s) never reaching a BA subtotal"
        )


def _r1_defense_wide_pp89_hard_check(appropriation_total_rows) -> None:
    """§5b.1 ruling 5: pp.89+ per-agency re-itemization totals must sum
    EXACTLY to the pp<89 consolidated appropriation total; else refuse."""
    consolidated = [
        r for r in appropriation_total_rows
        if r["appropriation_code"] == DOD_BUDGET_R1_DEFENSE_WIDE_CODE
        and r["page"] <= DOD_BUDGET_R1_DEFENSE_WIDE_CONSOLIDATED_MAX_PAGE
    ]
    peragency = [
        r for r in appropriation_total_rows
        if r["appropriation_code"] == DOD_BUDGET_R1_DEFENSE_WIDE_CODE
        and r["page"] > DOD_BUDGET_R1_DEFENSE_WIDE_CONSOLIDATED_MAX_PAGE
    ]
    if not consolidated and not peragency:
        return
    if len(consolidated) != 1:
        raise DodBudgetParseRefused(
            f"R-1 {DOD_BUDGET_R1_DEFENSE_WIDE_CODE} consolidated total is not exactly one printed row "
            f"(found {len(consolidated)})"
        )
    if not peragency:
        raise DodBudgetParseRefused(
            f"R-1 {DOD_BUDGET_R1_DEFENSE_WIDE_CODE} has a consolidated total but no per-agency pp.89+ sections"
        )
    expected = consolidated[0]["values"]
    sums = [0.0] * 7
    present = [False] * 7
    for r in peragency:
        for i in range(7):
            if r["values"][i] is not None:
                sums[i] += r["values"][i]
                present[i] = True
    for i in range(7):
        a = sums[i] if present[i] else None
        b = expected[i]
        if a is None and b is None:
            continue
        if a is None or b is None or not math.isclose(a, b, rel_tol=0.0, abs_tol=0.01):
            raise DodBudgetParseRefused(
                f"R-1 {DOD_BUDGET_R1_DEFENSE_WIDE_CODE} pp.89+ per-agency sum does not close vs the "
                f"consolidated total on {_R1_COLS[i]}: peragency={a} consolidated={b}"
            )


def parse_official_r1_document(
    extracted: ExtractedDocument, receipt: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse one real, receipt-bound R-1 exhibit into receipt-bound lines/totals.

    §5b.1 ruling 5: appropriation 0400D (Defense-Wide) emits lines ONLY from
    its consolidated listing (pp.<=88); the pp.89+ per-agency re-itemization
    is verification-only (hard-checked against the consolidated total, never
    published) — that is the ONLY exception to "every classified detail line
    publishes" in this exhibit; R-1 otherwise has no Less:/net-memo/additive-
    child machinery (that is P-1-only).
    """
    dod_budget.verify_extraction_manifest(extracted.page_texts, receipt)
    dod_budget.verify_document_header(
        extracted.page_texts, fiscal_year=int(receipt["fiscal_year"]), exhibit="r1",
    )
    detail_lines, ba_subtotal_rows, appropriation_total_rows = _r1_classify_document(
        extracted.page_texts, extracted.page_words,
    )
    _r1_reconcile(detail_lines, ba_subtotal_rows, appropriation_total_rows)
    _r1_defense_wide_pp89_hard_check(appropriation_total_rows)

    publishable = [
        r for r in detail_lines
        if not (
            r["appropriation_code"] == DOD_BUDGET_R1_DEFENSE_WIDE_CODE
            and r["page"] > DOD_BUDGET_R1_DEFENSE_WIDE_CONSOLIDATED_MAX_PAGE
        )
    ]
    publishable_ba_subtotals = [
        r for r in ba_subtotal_rows
        if not (
            r["appropriation_code"] == DOD_BUDGET_R1_DEFENSE_WIDE_CODE
            and r["page"] > DOD_BUDGET_R1_DEFENSE_WIDE_CONSOLIDATED_MAX_PAGE
        )
    ]

    fiscal_year = int(receipt["fiscal_year"])
    lines: list[dict[str, Any]] = []
    seen_line_keys: set[str] = set()
    for row in publishable:
        fields = {
            "component": row["department"] or "",
            "appropriation": row["appropriation_name"] or "",
            "appropriation_code": row["appropriation_code"] or "",
            "activity": row["act"] or "",
            "name": row["name"] or "",
            "pe": row["pe"],
            "actual": row["values"][0],
            "enacted": row["values"][3],
            "disc_request": row["values"][4],
            "recon_request": row["values"][5],
            "total_request": row["values"][6],
        }
        line_key, _family = dod_budget.line_identity(
            exhibit="r1", component=fields["component"], appropriation_code=fields["appropriation_code"],
            native_kind="program_element", native_value=fields["pe"], fiscal_year=fiscal_year,
            budget_activity=fields["activity"],
        )
        if line_key in seen_line_keys:
            raise DodBudgetParseRefused(f"R-1 duplicate derived line identity: {line_key}")
        seen_line_keys.add(line_key)
        lines.append(dod_budget.normalized_line_from_fields(
            fields=fields, receipt=receipt, page_number=row["page"],
            page_text=extracted.page_texts[row["page"] - 1], source_line_number=0,
        ))

    by_ba_key: dict[tuple[str, str], dict[str, Any]] = {}
    for r in publishable_ba_subtotals:
        key = (r["appropriation_code"], r["title"])
        if key in by_ba_key:
            raise DodBudgetParseRefused(f"R-1 duplicate BA-subtotal partition: {key}")
        by_ba_key[key] = r

    totals: list[dict[str, Any]] = []

    # reconcile_line_totals groups by (appropriation_code, budget_activity);
    # R-1's BA-subtotal rows key by TITLE, not the numeric act code the
    # detail lines carry as budget_activity, so build the totals list keyed
    # to match: one BA-subtotal row can close MULTIPLE act codes only if the
    # document prints them that way, which the earlier sequential
    # reconciliation already proved never happens (each BA subtotal closes
    # exactly the run of detail lines immediately preceding it).
    act_by_title_run: dict[tuple[str, str], set[str]] = {}
    buf_acts: set[str] = set()
    ordered = sorted(
        [("line", r) for r in publishable] + [("subtotal", r) for r in publishable_ba_subtotals],
        key=lambda t: t[1]["_evseq"],
    )
    for kind, row in ordered:
        if kind == "line":
            buf_acts.add(row["act"])
        else:
            act_by_title_run[(row["appropriation_code"], row["title"])] = set(buf_acts)
            buf_acts = set()

    for (appropriation_code, title), acts in act_by_title_run.items():
        row = by_ba_key[(appropriation_code, title)]
        if len(acts) != 1:
            raise DodBudgetParseRefused(
                f"R-1 BA subtotal ({appropriation_code}, {title!r}) closes {len(acts)} distinct "
                "budget-activity codes; expected exactly one"
            )
        (act,) = tuple(acts)
        fields = {
            "appropriation_code": appropriation_code, "activity": act,
            "actual": row["values"][0], "enacted": row["values"][3],
            "disc_request": row["values"][4], "recon_request": row["values"][5],
            "total_request": row["values"][6],
        }
        totals.append({
            "exhibit": "r1",
            "appropriation_code": appropriation_code,
            "budget_activity": act,
            "amounts": dod_budget.amounts_from_fields(fields, fiscal_year=fiscal_year),
            "page_number": row["page"],
            "page_text_sha256": dod_budget._sha256(extracted.page_texts[row["page"] - 1]),
        })

    dod_budget.reconcile_line_totals(lines, totals)
    return lines, totals


# ---------------------------------------------------------------------------
# P-1 parser
# ---------------------------------------------------------------------------

_P1_COLS = _R1_COLS
_P1_FURNITURE_EXACT = {
    "UNCLASSIFIED", "THIS PAGE INTENTIONALLY LEFT BLANK", "Apr 2026",
    "Defense-Wide",
    "27 Discretionary FY 2027 Mandatory",
    "Appropriation Summary", "Budget Activity",
}
_P1_FURNITURE_PREFIXES = (
    "Department of", "FY 2027 President's Budget", "Exhibit P-1",
    "Total Obligational Authority", "(Dollars in Thousands)", "Page ",
    "Line Ident", "No Item Nomenclature Code Sec",
    "PROCUREMENT PROGRAMS (P-1)", "Department of War Budget",
    "Fiscal Year 2027", "April 2026",
    "Office of the Under Secretary of War", "(Comptroller)", "Preface",
    "FY 2026", "FY 2025 Discretionary FY 2026 PL 119-21",
    "FY 2027 FY 2027", "Discretionary Mandatory",
)
_P1_FURNITURE_SUFFIXES = (
    "FY 2025 Actuals Enacted Plan FY 2026 Total",
    "Request Request FY 2027 Total",
)
_P1_CAPTION_RE = re.compile(
    r"^(?:(?P<code>\d{3,5}[A-Z]?) )?(?P<caption>Budget Activity Summary|Detail|DoW Component Summary|.+ Summary)(?: Apr 2026)?$"
)
_P1_APPROP_HEADER_RE = re.compile(r"^Appropriation:\s*(?:(\d{3,5}) )?(.+)$")
_P1_ORG_HEADER_RE = re.compile(r"^Organization:\s*(.+)$")
_P1_BA_HEADER_RE = re.compile(r"^Budget Activity (\d{2}): (.+)$")
_P1_BA_SUMMARY_ROW_RE = re.compile(r"^(\d{2})\.\s+(.+)$")
_P1_TOTAL_ROW_RE = re.compile(r"^Total\s+(.+)$")
_P1_GRAND_TOTAL_RE = re.compile(r"^Grand Total\s+(.+)$")
_P1_LESS_AP_PREFIX = "Less: Advance Procurement"
_P1_LESS_SFF_PREFIX = "Less: Subsequent Full Funding"
_P1_ADV_PROC_CY = "Advance Procurement (CY)"
_P1_SCHEDULE_RE = re.compile(r"^C \(FY \d{4} for FY \d{4}\) \(M\)")
_P1_COMPLETION_RE = re.compile(r"^(Completion PY Shipbuild for FY \d{4}|Subsequent Full Funding for FY \d{4})")
_P1_HEADER_TAIL_RE = re.compile(
    r"\s+(?:Actuals Enacted Spend Plan FY 2026 Total|Request Request FY 2027 Total)$"
)
_P1_HEADER_STOPWORD_RE = re.compile(
    r"^(?:FY|Discretionary|Mandatory|Request|Enacted|Actuals|Spend|Plan|"
    r"Total\*?|PL|119-21|\d+)$"
)
_P1_LESS_KINDS = frozenset({"less_advance_procurement", "less_subsequent_full_funding"})
_P1_ADDITIVE_CHILD_KINDS = frozenset({"advance_procurement_cy", "completion_subsequent_row"})
_P1_NEVER_ADDITIVE_KINDS = frozenset({"schedule_row", "memo_non_add_row"})
_P1_LEFT_COST_TO_COL = {1: 0, 3: 1, 5: 2, 7: 3}
_P1_RIGHT_COST_TO_COL = {0: 4, 2: 5, 4: 6}
_P1_LEFT_QTY_TO_COL = {0: 0, 2: 1, 4: 2, 6: 3}
_P1_RIGHT_QTY_TO_COL = {1: 5, 3: 6}

# §5b rule 7: pinned source-anomaly (exact match only, gated on the document
# sha256 AND page — a font/rendering glitch on the FY2027 P-1 duplicates
# every glyph of "Apr 2026" into "AApprr 22002266" on page 158's caption
# furniture; any OTHER unrecognized text refuses as normal).
_P1_PINNED_ANOMALY_DOC_SHA256 = "b8d5248257590856ee33ddb1b401ec2efcdfea219c05b5bc8ea1068d9000d0a6"
_P1_PINNED_ANOMALIES = {(_P1_PINNED_ANOMALY_DOC_SHA256, 158, "AApprr 22002266")}


def _p1_strip_header_tail(text: str) -> str:
    text = _P1_HEADER_TAIL_RE.sub("", text).strip()
    toks = text.split(" ")
    kept = []
    for t in toks:
        if _P1_HEADER_STOPWORD_RE.match(t):
            break
        kept.append(t)
    return " ".join(kept).strip()


def _p1_name_continuation_fragment(text: str) -> str | None:
    for s in _P1_FURNITURE_SUFFIXES:
        if text.endswith(s):
            frag = text[: -len(s)].strip()
            if frag.startswith("Appropriation:") or frag.startswith("Organization:"):
                return None
            return frag
    return None


def _p1_classify_furniture(text: str) -> bool:
    if text in _P1_FURNITURE_EXACT:
        return True
    for p in _P1_FURNITURE_PREFIXES:
        if text.startswith(p):
            return True
    for s in _P1_FURNITURE_SUFFIXES:
        if text.endswith(s):
            return True
    if text.startswith("Page ") and text.split()[-1].isdigit():
        return True
    return False


def _p1_find_qtycost_anchors(lines):
    best = None
    for idx, lw in enumerate(lines):
        toks = [w for w in lw if w["text"] in ("Qty", "Cost")]
        if len(toks) >= 3:
            toks_sorted = sorted(toks, key=lambda w: w["x0"])
            best = (idx, [(w["text"], w["x0"]) for w in toks_sorted])
    return best


def _p1_find_summary_anchors(lines):
    words_target = {"Actuals", "Enacted", "Plan", "Total", "Request"}
    best = None
    for idx, lw in enumerate(lines):
        toks = [w for w in lw if str(w["text"]).rstrip("*") in words_target]
        if len(toks) >= 2:
            toks_sorted = sorted(toks, key=lambda w: w["x0"])
            best = (idx, [(str(w["text"]).rstrip("*"), w["x0"]) for w in toks_sorted])
    return best


def _p1_calibrate_anchors(lines, header_row_idx, header_anchors, min_x0=336.0, gap=15.0):
    x1s = []
    for idx, lw in enumerate(lines):
        if idx <= header_row_idx:
            continue
        for w in lw:
            if w["x0"] >= min_x0 and _is_numeric_token(str(w["text"])):
                x1s.append(w["x1"])
    if not x1s:
        return header_anchors
    x1s.sort()
    clusters = [[x1s[0]]]
    for v in x1s[1:]:
        if v - clusters[-1][-1] <= gap:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    centroids = [sum(c) / len(c) for c in clusters]
    result = list(header_anchors)
    next_h = 0
    for cx in centroids:
        best_i, best_d = None, None
        for i in range(next_h, len(header_anchors)):
            d = abs(cx - header_anchors[i][1])
            if best_d is None or d < best_d:
                best_d, best_i = d, i
        if best_i is not None and best_d <= 60.0:
            result[best_i] = (header_anchors[best_i][0], cx)
            next_h = best_i + 1
    return result


def _p1_assign_numeric(line_words, anchors, min_x0=280.0, last_col_width=90.0):
    """Returns (slots, paren_slots, unassigned). ``paren_slots`` is the set
    of column indices whose VALUE-ZONE token was literally paren-wrapped
    (distinct from a bare-minus negative) — needed to detect a parenthesized
    own-row value that implies a resolving net-memo row (§5b rule 2 / §5b.1
    ruling: parenthesized values without resolution refuse), without
    confusing it with a parenthesized NUMBER inside the item's own printed
    name (observed: P-1 p.132 line 14 "Cancelled Account Adjustments (87)"
    — "(87)" sits left of the value zone and must never count)."""
    toks = []
    for w in line_words:
        if w["x0"] < min_x0 or not _is_numeric_token(str(w["text"])):
            continue
        toks.append(w)
    toks.sort(key=lambda w: w["x0"])
    bounds = [anchors[i + 1][1] for i in range(len(anchors) - 1)] + [anchors[-1][1] + last_col_width]
    slots: dict[int, float] = {}
    paren_slots: set[int] = set()
    unassigned = []
    for w in toks:
        col = None
        for i, (_, ax0) in enumerate(anchors):
            if ax0 <= w["x1"] < bounds[i]:
                col = i
                break
        if col is None or col in slots:
            unassigned.append((w["text"], w["x0"], w["top"]))
            continue
        text = str(w["text"])
        slots[col] = _parse_signed_number(text)
        if text.strip().startswith("(") and text.strip().endswith(")"):
            paren_slots.add(col)
    return slots, paren_slots, unassigned


def _p1_detail_line_nomenclature(text: str) -> str:
    """Strip a P-1 detail line's own printed values and Ident-Code/Sec
    trailer, leaving just the printed Item Nomenclature (e.g. "6 Virginia
    Class Submarine B U 1 (9,500,534) ..." -> "Virginia Class Submarine").

    Ident Code and Sec are always single printed letters immediately before
    the value zone; stripped only from the END, at most two, so a
    nomenclature that itself ends in a real word is never touched (an
    English program name never trails two bare single-letter tokens).
    """
    text = re.sub(r"^\d{1,4}\s+", "", text)
    text = _strip_trailing_numeric_tail(text)
    toks = text.split(" ")
    stripped = list(toks)
    for _ in range(2):
        if len(stripped) > 1 and re.fullmatch(r"[A-Z]", stripped[-1]):
            stripped.pop()
    # Never strip down to nothing: a nomenclature of literally 1-2 single
    # letters is vanishingly unlikely in a real program name, but if
    # stripping WOULD empty the label, keep the pre-strip text instead of
    # publishing an empty name.
    result = " ".join(stripped).strip()
    return result or " ".join(toks).strip()


def _p1_classify_document(pages: Sequence[str], pages_words, *, document_sha256: str):
    """Classify every P-1 page into the closed row taxonomy (§5b). Refuses
    on any row/page this classifier cannot positively identify."""
    detail_rows: list[dict[str, Any]] = []
    ba_summary_rows: list[dict[str, Any]] = []
    ba_total_rows: list[dict[str, Any]] = []
    appr_total_rows: list[dict[str, Any]] = []
    all_detail_total_rows: list[dict[str, Any]] = []

    current_department: str | None = None
    current_appropriation_code: str | None = None       # STRIPPED (Detail-native) form, join key only
    current_appropriation_code_full: str | None = None  # published field (caption form, e.g. "2031A")
    current_appropriation_name: str | None = None
    ba_code_by_side: dict[str, str | None] = {"left": None, "right": None}
    ba_name_by_side: dict[str, str | None] = {"left": None, "right": None}
    pending_item_row: dict[str, Any] | None = None
    event_seq = [0]

    def next_seq() -> int:
        event_seq[0] += 1
        return event_seq[0]

    for pno, (page_text, words) in enumerate(zip(pages, pages_words)):
        page_num = pno + 1
        if not words:
            continue
        lines = _cluster_lines(words)
        full_text = "\n".join(_line_text(l) for l in lines)

        if "THIS PAGE INTENTIONALLY LEFT BLANK" in full_text:
            continue
        if page_num == 1 and "PROCUREMENT PROGRAMS (P-1)" in full_text:
            continue
        if full_text.strip().startswith("UNCLASSIFIED\nPreface"):
            continue
        if "TABLE OF CONTENTS" in full_text:
            continue

        caption = None
        caption_code_full = None
        for l in lines[:8]:
            t = _line_text(l)
            m = _P1_CAPTION_RE.match(t)
            if m:
                caption = m.group("caption")
                caption_code_full = m.group("code")
                break
        if caption_code_full:
            stripped = caption_code_full[:-1] if caption_code_full[-1].isalpha() else caption_code_full
            current_appropriation_code = stripped
            current_appropriation_code_full = caption_code_full
        if caption is None and "Organization:" in full_text:
            caption = "Organization Breakdown"
        is_detail = caption == "Detail"
        is_ba_summary = caption == "Budget Activity Summary"
        is_org_breakdown = caption == "Organization Breakdown"
        is_dow_or_dept_summary = caption is not None and caption.endswith("Summary") and not is_ba_summary

        for l in lines[:6]:
            t = _line_text(l)
            if t.startswith("Department of"):
                current_department = t.replace("Department of", "").strip()

        if is_detail:
            anchor_result = _p1_find_qtycost_anchors(lines)
        elif is_ba_summary or is_dow_or_dept_summary or is_org_breakdown:
            anchor_result = _p1_find_summary_anchors(lines)
        else:
            anchor_result = None

        if caption is None or anchor_result is None:
            raise DodBudgetParseRefused(
                f"P-1 page {page_num} has no recognizable caption/column-header shape"
            )
        if not _unit_marker_present(page_text):
            raise DodBudgetParseRefused(f"P-1 page {page_num} table lacks the '(Dollars in Thousands)' unit marker")

        header_row_idx, anchor_list = anchor_result
        n_anchor = len(anchor_list)
        if is_detail:
            side = "left" if anchor_list[0][0] == "Qty" and n_anchor >= 7 else "right"
            # NOTE: anchor calibration (_p1_calibrate_anchors) is deliberately
            # NOT applied here. It exists (below) because it was explored
            # during the Stage 1 survey, but the survey's actual proven run
            # (81/81 document-wide typed-model closure, gate-zero (a)) never
            # wired it into its classification loop — it used the RAW
            # header-word anchors directly. Wiring calibration in DURING
            # Stage 2b regressed a real row (P-1 p.14 line 7, appropriation
            # 2031A): the empirical value-cluster centroids do not maintain
            # the same left-to-right ORDER as the header words in every case,
            # so greedy nearest-anchor calibration silently swapped a Cost
            # column's value into the following Qty column's slot with no
            # unassigned-token signal. Kept in the module (unused) as
            # evidence of what was tried and rejected, not as dead surface
            # area to prune blindly.
        else:
            side = "left" if any(lbl in ("Enacted",) for lbl, _ in anchor_list) or n_anchor == 4 else "right"
        current_ba_code = ba_code_by_side[side]
        current_ba_name = ba_name_by_side[side]

        footnote_active = False
        for idx, lw in enumerate(lines):
            text = _line_text(lw)
            if not text.strip():
                continue
            name_frag = _p1_name_continuation_fragment(text)
            if name_frag is not None:
                if name_frag and current_appropriation_name is not None:
                    current_appropriation_name = (current_appropriation_name + " " + name_frag).strip()
                continue
            if _p1_classify_furniture(text):
                continue
            if (document_sha256, page_num, text) in _P1_PINNED_ANOMALIES:
                continue
            is_footnote_start = bool(re.match(r"^\*+The FY27", text))
            if is_footnote_start:
                footnote_active = True
                continue
            if footnote_active:
                has_any_number = any(_is_numeric_token(str(w["text"])) for w in lw)
                if not has_any_number:
                    continue
                footnote_active = False

            m_appr = _P1_APPROP_HEADER_RE.match(text)
            if m_appr:
                code = m_appr.group(1)
                name = _p1_strip_header_tail(m_appr.group(2).strip())
                if code and code != current_appropriation_code:
                    pending_item_row = None
                current_appropriation_code = code or current_appropriation_code
                current_appropriation_name = name
                continue

            m_org = _P1_ORG_HEADER_RE.match(text)
            if m_org:
                current_appropriation_name = _p1_strip_header_tail(m_org.group(1).strip())
                continue

            if idx == header_row_idx:
                continue
            if _P1_CAPTION_RE.match(text):
                continue
            if text.strip() == "Budget Activity":
                continue

            m_ba = _P1_BA_HEADER_RE.match(text)
            if m_ba:
                current_ba_code, current_ba_name = m_ba.group(1), m_ba.group(2).strip()
                ba_code_by_side[side] = current_ba_code
                ba_name_by_side[side] = current_ba_name
                pending_item_row = None
                continue

            slots, paren_slots, unassigned = _p1_assign_numeric(lw, anchor_list)
            has_value_numbers = bool(slots)

            # §5b.1 ruling 6: a detail_line requires NON-NUMERIC nomenclature
            # text after the leading line number, or this classifies as
            # something else — kills the "20 20" false positive (P-1 p.121,
            # a bare two-number unlabeled_net_memo_row whose first token
            # happens to look like a plausible line number).
            m_line = re.match(r"^(\d{1,4})\s+(.*)$", text)
            if m_line:
                _line_no_candidate, _rest = m_line.groups()
                rest_tokens = _rest.split()
                has_nomenclature = any(not _is_numeric_token(tok) for tok in rest_tokens)
                if not has_nomenclature:
                    m_line = None

            if is_detail and m_line:
                line_no, _rest = m_line.groups()
                if unassigned:
                    raise DodBudgetParseRefused(
                        f"P-1 page {page_num} detail line {line_no} has an unassignable numeric token: {unassigned!r}"
                    )
                row = {
                    "page": page_num, "side": side, "line_no": line_no,
                    "raw": text, "slots": slots, "paren_slots": paren_slots,
                    "name": _p1_detail_line_nomenclature(text),
                    "appropriation_code": current_appropriation_code,
                    "appropriation_code_full": current_appropriation_code_full,
                    "ba_code": current_ba_code, "ba_name": current_ba_name,
                    "department": current_department,
                    "kind": "detail_line", "_evseq": next_seq(),
                }
                detail_rows.append(row)
                pending_item_row = row
                continue

            if is_detail and (text.startswith(_P1_LESS_AP_PREFIX) or text.startswith(_P1_LESS_SFF_PREFIX)):
                kind = "less_advance_procurement" if text.startswith(_P1_LESS_AP_PREFIX) else "less_subsequent_full_funding"
                if unassigned:
                    raise DodBudgetParseRefused(
                        f"P-1 page {page_num} Less: row has an unassignable numeric token: {unassigned!r}"
                    )
                detail_rows.append({
                    "page": page_num, "side": side, "raw": text, "slots": slots,
                    "appropriation_code": current_appropriation_code,
                    "appropriation_code_full": current_appropriation_code_full,
                    "ba_code": current_ba_code, "ba_name": current_ba_name,
                    "kind": kind, "_evseq": next_seq(),
                })
                continue

            if is_detail and text.startswith(_P1_ADV_PROC_CY):
                if unassigned:
                    raise DodBudgetParseRefused(
                        f"P-1 page {page_num} Advance Procurement (CY) row has an unassignable numeric token: {unassigned!r}"
                    )
                detail_rows.append({
                    "page": page_num, "side": side, "raw": text, "slots": slots,
                    "appropriation_code": current_appropriation_code,
                    "appropriation_code_full": current_appropriation_code_full,
                    "ba_code": current_ba_code, "ba_name": current_ba_name,
                    "kind": "advance_procurement_cy", "label": _P1_ADV_PROC_CY, "_evseq": next_seq(),
                })
                continue

            if is_detail and _P1_SCHEDULE_RE.match(text):
                if unassigned:
                    raise DodBudgetParseRefused(
                        f"P-1 page {page_num} schedule row has an unassignable numeric token: {unassigned!r}"
                    )
                detail_rows.append({
                    "page": page_num, "side": side, "raw": text, "slots": slots,
                    "appropriation_code": current_appropriation_code,
                    "appropriation_code_full": current_appropriation_code_full,
                    "ba_code": current_ba_code, "ba_name": current_ba_name,
                    "kind": "schedule_row", "_evseq": next_seq(),
                })
                continue

            m_completion = _P1_COMPLETION_RE.match(text) if is_detail else None
            if m_completion:
                if unassigned:
                    raise DodBudgetParseRefused(
                        f"P-1 page {page_num} completion/subsequent row has an unassignable numeric token: {unassigned!r}"
                    )
                detail_rows.append({
                    "page": page_num, "side": side, "raw": text, "slots": slots,
                    "appropriation_code": current_appropriation_code,
                    "appropriation_code_full": current_appropriation_code_full,
                    "ba_code": current_ba_code, "ba_name": current_ba_name,
                    "kind": "completion_subsequent_row", "label": m_completion.group(0), "_evseq": next_seq(),
                })
                continue

            m_tot = _P1_TOTAL_ROW_RE.match(text)
            if is_detail and m_tot and has_value_numbers:
                if unassigned:
                    raise DodBudgetParseRefused(
                        f"P-1 page {page_num} total row has an unassignable numeric token: {unassigned!r}"
                    )
                label = _strip_trailing_numeric_tail(m_tot.group(1))
                row = {
                    "page": page_num, "side": side, "raw": text, "label": label,
                    "slots": slots,
                    "appropriation_code": current_appropriation_code,
                    "appropriation_code_full": current_appropriation_code_full,
                    "ba_code": current_ba_code, "ba_name": current_ba_name,
                    "expected_appr_name": current_appropriation_name,
                    "_evseq": next_seq(),
                }
                all_detail_total_rows.append(row)
                pending_item_row = None
                continue

            if is_ba_summary:
                m_basrow = _P1_BA_SUMMARY_ROW_RE.match(text)
                if m_basrow:
                    if unassigned:
                        raise DodBudgetParseRefused(
                            f"P-1 page {page_num} BA-summary row has an unassignable numeric token: {unassigned!r}"
                        )
                    ba_summary_rows.append({
                        "page": page_num, "side": side, "ba_code": m_basrow.group(1),
                        "ba_name": _strip_trailing_numeric_tail(m_basrow.group(2)), "slots": slots,
                        "appropriation_name": current_appropriation_name,
                        "appropriation_code": current_appropriation_code,
                        "appropriation_code_full": current_appropriation_code_full,
                        "_evseq": next_seq(),
                    })
                    continue
                if m_tot:
                    if unassigned:
                        raise DodBudgetParseRefused(
                            f"P-1 page {page_num} BA-summary appropriation total has an unassignable numeric token: {unassigned!r}"
                        )
                    appr_total_rows.append({
                        "page": page_num, "side": side, "raw": text,
                        "label": _strip_trailing_numeric_tail(m_tot.group(1)), "slots": slots,
                        "appropriation_code": current_appropriation_code,
                        "appropriation_code_full": current_appropriation_code_full,
                        "kind": "ba_summary_page_appropriation_total",
                        "_evseq": next_seq(),
                    })
                    continue

            if is_dow_or_dept_summary or is_org_breakdown:
                m_grand = _P1_GRAND_TOTAL_RE.match(text)
                if m_grand:
                    continue  # DoW/grand-total row: evidence only, never fed to reconciliation
                if m_tot and has_value_numbers:
                    continue  # department/component grand total: evidence only
                if not m_tot:
                    continue  # appropriation-name row on a DoW/Dept summary page: evidence only

            if is_detail and not has_value_numbers:
                xs = [w["x0"] for w in lw]
                min_x0 = min(xs) if xs else None
                if min_x0 is not None and min_x0 < 55:
                    detail_rows.append({
                        "page": page_num, "side": side, "raw": text,
                        "appropriation_code": current_appropriation_code,
                        "appropriation_code_full": current_appropriation_code_full,
                        "ba_code": current_ba_code, "ba_name": current_ba_name,
                        "kind": "group_label", "_evseq": next_seq(),
                    })
                    pending_item_row = None
                    continue
                if min_x0 is not None and 55 <= min_x0 < 340:
                    # Nomenclature wrap fragment: carries no numbers, never
                    # used for arithmetic. NOT merged into any row's name:
                    # a long Item Nomenclature can wrap either AFTER its own
                    # numbered line (a true continuation) OR BEFORE the
                    # FOLLOWING numbered line (observed: P-1 p.284
                    # "Battlefield Airborne Control Node" / "31 (BACN) ...")
                    # — this single forward scan cannot disambiguate which,
                    # and a wrong attribution (merging into the wrong line's
                    # name) is worse than an incomplete one. Named display-
                    # quality gap: a handful of P-1 program_name values are
                    # the trailing fragment only, never the full wrapped
                    # name; dollar amounts and identity are unaffected.
                    continue
                raise DodBudgetParseRefused(
                    f"P-1 page {page_num} has an unclassified label-only row: {text!r}"
                )

            if is_detail and has_value_numbers and "(MEMO NON ADD)" in text:
                if unassigned:
                    raise DodBudgetParseRefused(
                        f"P-1 page {page_num} MEMO NON ADD row has an unassignable numeric token: {unassigned!r}"
                    )
                detail_rows.append({
                    "page": page_num, "side": side, "raw": text, "slots": slots,
                    "appropriation_code": current_appropriation_code,
                    "appropriation_code_full": current_appropriation_code_full,
                    "ba_code": current_ba_code, "ba_name": current_ba_name,
                    "kind": "memo_non_add_row", "_evseq": next_seq(),
                })
                continue

            if is_detail and has_value_numbers and not m_line:
                if unassigned:
                    raise DodBudgetParseRefused(
                        f"P-1 page {page_num} net-memo row has an unassignable numeric token: {unassigned!r}"
                    )
                detail_rows.append({
                    "page": page_num, "side": side, "raw": text, "slots": slots,
                    "appropriation_code": current_appropriation_code,
                    "appropriation_code_full": current_appropriation_code_full,
                    "ba_code": current_ba_code, "ba_name": current_ba_name,
                    "kind": "unlabeled_net_memo_row", "_evseq": next_seq(),
                })
                continue

            raise DodBudgetParseRefused(
                f"P-1 page {page_num} has an unclassified numeric row: {text!r} (side={side}, caption={caption!r})"
            )

    # Post-pass: split all_detail_total_rows into appropriation-close vs
    # BA-close (proven Stage-1 positional/name-matching model).
    all_detail_total_rows.sort(key=lambda r: r["_evseq"])
    run: list[dict[str, Any]] = []
    run_code = object()

    def label_matches_target(label_cf: str, target: str) -> bool:
        if label_cf == target:
            return True
        if label_cf.replace(" ", "") == target.replace(" ", ""):
            return True
        shorter, longer = sorted((label_cf, target), key=len)
        if longer.startswith(shorter) and len(shorter) >= 0.80 * len(longer):
            return True
        return False

    def flush_run() -> None:
        if not run:
            return
        names = {r["expected_appr_name"] for r in run if r["expected_appr_name"]}
        target = next(iter(names)).casefold() if len(names) == 1 else None
        if target is not None:
            matches = [r for r in run if label_matches_target(r["label"].casefold(), target)]
            per_side_matches: dict[str, list] = {}
            for r in matches:
                per_side_matches.setdefault(r["side"], []).append(r)
            kept = []
            for side_rows in per_side_matches.values():
                side_rows.sort(key=lambda r: r["_evseq"])
                kept.append(side_rows[-1])
            if kept and len(kept) <= 2:
                matched_ids = {id(r) for r in kept}
                for r in run:
                    if id(r) in matched_ids:
                        r["kind"] = "appropriation_total_row"
                        appr_total_rows.append(r)
                    else:
                        r["kind"] = "ba_total_row"
                        ba_total_rows.append(r)
                return
        if len(run) < 1:
            return
        for r in run[:-1]:
            r["kind"] = "ba_total_row"
            ba_total_rows.append(r)
        last = run[-1]
        last["kind"] = "appropriation_total_row"
        appr_total_rows.append(last)

    for row in all_detail_total_rows:
        if row["appropriation_code"] != run_code:
            flush_run()
            run = []
            run_code = row["appropriation_code"]
        run.append(row)
    flush_run()

    if not detail_rows:
        raise DodBudgetParseRefused("P-1 document produced no detail rows")
    return detail_rows, ba_summary_rows, ba_total_rows, appr_total_rows


def _p1_cost_values(row: Mapping[str, Any]) -> list[float | None]:
    table = _P1_LEFT_COST_TO_COL if row["side"] == "left" else _P1_RIGHT_COST_TO_COL
    out: list[float | None] = [None] * 7
    for k, v in row.get("slots", {}).items():
        col = table.get(k)
        if col is not None:
            out[col] = v
    return out


def _p1_qty_values(row: Mapping[str, Any]) -> list[float | None]:
    table = _P1_LEFT_QTY_TO_COL if row["side"] == "left" else _P1_RIGHT_QTY_TO_COL
    out: list[float | None] = [None] * 7
    for k, v in row.get("slots", {}).items():
        col = table.get(k)
        if col is not None:
            out[col] = v
    return out


def _p1_amounts_close(a: Sequence[float | None], b: Sequence[float | None]) -> bool:
    for x, y in zip(a, b):
        if x is None and y is None:
            continue
        if x is None or y is None or not math.isclose(x, y, rel_tol=0.0, abs_tol=0.01):
            return False
    return True


def _p1_add7(acc: list[float | None], present: list[bool], vals: Sequence[float | None]) -> None:
    for i in range(7):
        if vals[i] is not None:
            acc[i] = (acc[i] or 0.0) + vals[i]
            present[i] = True


def _p1_emit_side(rows: Sequence[Mapping[str, Any]]):
    """Walk ONE (appropriation_code, ba_code, side) event-ordered stream.

    Returns (full_sum, publishable_records, publishable_sum): full_sum is
    the typed-row-model closure value INCLUDING orphaned additive rows (the
    hard document-wide gate, proven Stage 2b gate-zero (a)); publishable_
    records implements §5b.1 ruling 3 (printed-addend grain: a numbered
    parent's own record, plus one record per value-bearing additive child
    that has an identified parent — orphans are never published, never
    minted an identity).
    """
    full_sum: list[float | None] = [None] * 7
    full_present = [False] * 7
    pub_sum: list[float | None] = [None] * 7
    pub_present = [False] * 7
    records: list[dict[str, Any]] = []

    current_parent_line_no: str | None = None
    current_parent_page: int | None = None
    current_parent_name: str | None = None
    pending_own_values: list[float | None] | None = None
    pending_own_qty: list[float | None] | None = None
    pending_less_sum: list[float | None] = [None] * 7
    # A parent NEEDS a resolving net-memo row (§5b rule 2) when EITHER a
    # VALUE-BEARING Less:-child row was seen, OR the parent's own row prints
    # a PARENTHESIZED (not bare-minus) negative value — observed: P-1 p.117
    # line 8 "Standard Missile" prints negative parenthesized own-row values
    # with a BLANK "Less: Advance Procurement (PY)" row (no value at all)
    # yet is still resolved by a following bare net-memo row that flips the
    # sign; conversely P-1 p.108 lines 55-57 ("DON Other N (TTNT)") print
    # small BARE-MINUS negatives with no Less: row and no resolving net-memo
    # at all — those are plain own-row values, never expecting resolution.
    pending_needs_resolution = False
    pending_resolved = False

    def flush_parent() -> None:
        nonlocal pending_own_values, pending_own_qty, pending_less_sum, pending_needs_resolution, pending_resolved
        if current_parent_line_no is not None and pending_needs_resolution and not pending_resolved:
            # A Less:-child or a parenthesized negative own-row value implied
            # a resolving net-memo row, but no unlabeled_net_memo_row ever
            # arrived before the parent's own record would flush (a new
            # detail_line, group_label, or end of stream). Observed exactly
            # once in the real FY2027 exhibit (P-1 p.230 line 22 "E-7"): the
            # own row prints +200,000 and its Less: Advance Procurement (PY)
            # prints exactly -200,000 on the SAME columns — a genuine implied
            # net of exactly $0.00 that the document simply never prints a
            # redundant zero-value net-memo row for. That ONE shape is
            # accepted: own + Σ(less) closes to EXACTLY zero on every
            # populated column. Anything else (a non-zero unexplained
            # residual, or a parenthesized own value with nothing at all to
            # net it against) is a row shape this parser does not
            # understand and refuses rather than guessing.
            own = pending_own_values if pending_own_values is not None else [None] * 7
            implicit_net: list[float | None] = [None] * 7
            for i in range(7):
                if own[i] is None and pending_less_sum[i] is None:
                    continue
                implicit_net[i] = (own[i] or 0.0) + (pending_less_sum[i] or 0.0)
            if any(v is not None and not math.isclose(v, 0.0, rel_tol=0.0, abs_tol=0.01) for v in implicit_net):
                raise DodBudgetParseRefused(
                    f"P-1 line {current_parent_line_no} (page {current_parent_page}) needs a resolving "
                    "net-memo row but none followed, and its own value plus Less:-children do not net to zero"
                )
            qty = pending_own_qty if pending_own_qty is not None else [None] * 7
            zeroed = [0.0 if v is not None else None for v in implicit_net]
            _p1_add7(full_sum, full_present, zeroed)
            _p1_add7(pub_sum, pub_present, zeroed)
            records.append({
                "native_value": current_parent_line_no, "amounts": zeroed, "quantities": qty,
                "label": current_parent_name, "page": current_parent_page, "kind": "parent_implicit_zero_net",
            })
        elif current_parent_line_no is not None and not pending_resolved and not pending_needs_resolution:
            vals = pending_own_values if pending_own_values is not None else [None] * 7
            qty = pending_own_qty if pending_own_qty is not None else [None] * 7
            _p1_add7(full_sum, full_present, vals)
            _p1_add7(pub_sum, pub_present, vals)
            records.append({
                "native_value": current_parent_line_no, "amounts": vals, "quantities": qty,
                "label": current_parent_name, "page": current_parent_page, "kind": "parent_own_row",
            })
        pending_own_values = None
        pending_own_qty = None
        pending_less_sum = [None] * 7
        pending_needs_resolution = False
        pending_resolved = False

    for row in rows:
        kind = row["kind"]
        if kind == "detail_line":
            flush_parent()
            current_parent_line_no = row.get("line_no")
            current_parent_page = row["page"]
            current_parent_name = row.get("name") or None
            pending_own_values = _p1_cost_values(row)
            pending_own_qty = _p1_qty_values(row)
            pending_needs_resolution = bool(row.get("paren_slots"))
            pending_resolved = False
        elif kind in _P1_LESS_KINDS:
            # A Less: row that prints NO value at all (observed: P-1 p.145
            # line 10 "CVN Refueling Overhauls" — both Less: rows blank, the
            # real money for that line carried entirely by a subsequent
            # completion_subsequent_row child) deducts nothing on its own;
            # only a VALUE-BEARING Less: row (or a parenthesized own-row
            # value, see above) obliges a resolving net-memo row.
            less_vals = _p1_cost_values(row)
            if any(v is not None for v in less_vals):
                pending_needs_resolution = True
                for i in range(7):
                    if less_vals[i] is not None:
                        pending_less_sum[i] = (pending_less_sum[i] or 0.0) + less_vals[i]
        elif kind == "unlabeled_net_memo_row":
            if not pending_needs_resolution:
                # A bare parenthesized/signed net-memo-shaped row with no
                # Less:-pairing and no parenthesized own-row value it could
                # be resolving — this parser only understands this row shape
                # as a resolution; anything else is unattributable and
                # refuses rather than silently folding an unexplained amount
                # into the document-wide closure with no published record.
                raise DodBudgetParseRefused(
                    f"P-1 page {row['page']}: unlabeled net-memo-shaped row with nothing to resolve: "
                    f"{row['raw']!r}"
                )
            vals = _p1_cost_values(row)
            _p1_add7(full_sum, full_present, vals)
            qty = pending_own_qty if pending_own_qty is not None else [None] * 7
            _p1_add7(pub_sum, pub_present, vals)
            records.append({
                "native_value": current_parent_line_no, "amounts": vals, "quantities": qty,
                "label": current_parent_name, "page": current_parent_page, "kind": "parent_net_memo",
            })
            pending_resolved = True
        elif kind in _P1_ADDITIVE_CHILD_KINDS:
            vals = _p1_cost_values(row)
            _p1_add7(full_sum, full_present, vals)
            if any(v is not None for v in vals):
                if current_parent_line_no is None:
                    # Orphan: value-bearing additive row with no numbered
                    # parent (§5b.1 ruling 2, e.g. 1612N BA01's unnumbered
                    # "Subsequent Full Funding" row). Included in the full
                    # typed-model gate above; never published — no printed
                    # identity exists to bind it to.
                    pass
                else:
                    label = row["label"]
                    native_value = f"{current_parent_line_no}--{_slug(label)}"
                    qty = _p1_qty_values(row)
                    _p1_add7(pub_sum, pub_present, vals)
                    records.append({
                        "native_value": native_value, "amounts": vals, "quantities": qty,
                        "label": label, "page": row["page"], "kind": "child",
                    })
        elif kind in _P1_NEVER_ADDITIVE_KINDS:
            pass
        elif kind == "group_label":
            flush_parent()
            current_parent_line_no = None
            current_parent_page = None
            current_parent_name = None
        # memo/wrap-fragment kinds carry no numbers and never appear here
    flush_parent()
    return (
        [full_sum[i] if full_present[i] else None for i in range(7)],
        records,
        [pub_sum[i] if pub_present[i] else None for i in range(7)],
    )


def parse_official_p1_document(
    extracted: ExtractedDocument, receipt: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse one real, receipt-bound P-1 exhibit into receipt-bound lines/totals.

    §5b.1 rulings are LAW here: sign forms (ruling 1, via
    :func:`_parse_signed_number`), zero-numbered-line partition exclusion
    (ruling 2), printed-addend grain / parent+child records (ruling 3, via
    :func:`_p1_emit_side`), BA-slug line identity (ruling 4), and the "20 20"
    classification fix (ruling 6, in :func:`_p1_classify_document`).
    """
    dod_budget.verify_extraction_manifest(extracted.page_texts, receipt)
    dod_budget.verify_document_header(
        extracted.page_texts, fiscal_year=int(receipt["fiscal_year"]), exhibit="p1",
    )
    document_sha256 = str(receipt["content_sha256"])
    detail_rows, ba_summary_rows, ba_total_rows, appr_total_rows = _p1_classify_document(
        extracted.page_texts, extracted.page_words, document_sha256=document_sha256,
    )

    # ---- Merge left+right into 7-column groups (proven Stage-1 shape) ----
    def merge_summary_slots(rows_for_key: Sequence[Mapping[str, Any]]) -> list[float | None]:
        merged: list[float | None] = [None] * 7
        for r in rows_for_key:
            offset = 0 if r["side"] == "left" else 4
            for k, v in r["slots"].items():
                idx = k + offset
                if idx < 7:
                    merged[idx] = v
        return merged

    def merge_detail_total_slots(rows_for_key: Sequence[Mapping[str, Any]]) -> list[float | None]:
        merged: list[float | None] = [None] * 7
        for r in rows_for_key:
            table = _P1_LEFT_COST_TO_COL if r["side"] == "left" else _P1_RIGHT_COST_TO_COL
            for k, v in r["slots"].items():
                col = table.get(k)
                if col is not None:
                    merged[col] = v
        return merged

    by_code_ba_summary: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in ba_summary_rows:
        by_code_ba_summary.setdefault((r["appropriation_code"], r["ba_code"]), []).append(r)
    ba_summary_merged: dict[tuple[str, str], dict[str, Any]] = {}
    for key, rows_for_key in by_code_ba_summary.items():
        ba_summary_merged[key] = {
            "values": merge_summary_slots(rows_for_key),
            "ba_name": rows_for_key[0]["ba_name"],
            "appropriation_name": rows_for_key[0]["appropriation_name"],
            "appropriation_code_full": rows_for_key[0]["appropriation_code_full"],
            "page": rows_for_key[0]["page"],
        }

    appr_from_basummary = [r for r in appr_total_rows if r.get("kind") == "ba_summary_page_appropriation_total"]
    by_code_appr_basummary: dict[str, list[dict[str, Any]]] = {}
    for r in appr_from_basummary:
        by_code_appr_basummary.setdefault(r["appropriation_code"], []).append(r)
    appr_basummary_merged: dict[str, dict[str, Any]] = {}
    for code, rows_for_key in by_code_appr_basummary.items():
        appr_basummary_merged[code] = {"values": merge_summary_slots(rows_for_key), "label": rows_for_key[0]["label"]}

    by_code_ba_detail_total: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in ba_total_rows:
        by_code_ba_detail_total.setdefault((r["appropriation_code"], r["ba_code"]), []).append(r)
    detail_close_merged: dict[tuple[str, str], list[float | None]] = {
        key: merge_detail_total_slots(rows_for_key) for key, rows_for_key in by_code_ba_detail_total.items()
    }

    appr_detail = [r for r in appr_total_rows if r.get("kind") == "appropriation_total_row"]
    by_code_appr_detail: dict[str, list[dict[str, Any]]] = {}
    for r in appr_detail:
        by_code_appr_detail.setdefault(r["appropriation_code"], []).append(r)
    appr_detail_merged: dict[str, list[float | None]] = {
        code: merge_detail_total_slots(rows_for_key) for code, rows_for_key in by_code_appr_detail.items()
    }

    # ---- Level 1/3 hard gates (proven Stage-1/2a aggregate hierarchy) ----
    if set(ba_summary_merged) and {k[0] for k in ba_summary_merged} - set(appr_basummary_merged):
        raise DodBudgetParseRefused("P-1 has BA-summary rows with no matching appropriation total")
    for code, agg in appr_basummary_merged.items():
        ba_keys = [k for k in ba_summary_merged if k[0] == code]
        summed: list[float | None] = [None] * 7
        present = [False] * 7
        for k in ba_keys:
            _p1_add7(summed, present, ba_summary_merged[k]["values"])
        summed = [summed[i] if present[i] else None for i in range(7)]
        if not _p1_amounts_close(summed, agg["values"]):
            raise DodBudgetParseRefused(
                f"P-1 appropriation {code}: BA-summary rows do not sum to the printed appropriation total"
            )
    if set(appr_detail_merged) != set(appr_basummary_merged):
        raise DodBudgetParseRefused(
            "P-1 Detail-page appropriation closes and BA-Summary-page appropriation totals cover different codes"
        )
    for code, detail_vals in appr_detail_merged.items():
        if not _p1_amounts_close(detail_vals, appr_basummary_merged[code]["values"]):
            raise DodBudgetParseRefused(
                f"P-1 appropriation {code}: Detail-page close does not match the BA-Summary-page total"
            )

    # ---- Per-BA typed-model closure (hard gate) + printed-addend emission ----
    by_key_side: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    for r in detail_rows:
        code = r.get("appropriation_code")
        ba = r.get("ba_code")
        side = r.get("side")
        if code is None or ba is None or side is None:
            continue
        by_key_side.setdefault((code, ba), {"left": [], "right": []}).setdefault(side, []).append(r)

    fiscal_year = int(receipt["fiscal_year"])
    lines: list[dict[str, Any]] = []
    totals: list[dict[str, Any]] = []
    seen_line_keys: set[str] = set()
    seen_derived_identity: set[tuple[str, str, str]] = set()

    if set(by_key_side) != set(detail_close_merged):
        raise DodBudgetParseRefused("P-1 detail-row (appropriation,BA) groups do not match printed BA-close rows")

    for key in sorted(by_key_side):
        appropriation_code, ba_code = key
        sides = by_key_side[key]
        full_merged: list[float | None] = [None] * 7
        pub_merged: list[float | None] = [None] * 7
        records_by_native: dict[str, dict[str, Any]] = {}
        parent_names_by_side: dict[str, dict[str, str | None]] = {"left": {}, "right": {}}
        for side in ("left", "right"):
            side_rows = sorted(sides.get(side, []), key=lambda r: r["_evseq"])
            full_side, side_records, pub_side = _p1_emit_side(side_rows)
            table = _P1_LEFT_COST_TO_COL if side == "left" else _P1_RIGHT_COST_TO_COL
            for col in set(table.values()):
                full_merged[col] = full_side[col]
                pub_merged[col] = pub_side[col]
            for rec in side_records:
                if rec["kind"] in ("parent_own_row", "parent_net_memo", "parent_implicit_zero_net"):
                    parent_names_by_side[side][rec["native_value"]] = rec["label"]
                merged_rec = records_by_native.setdefault(rec["native_value"], {
                    "native_value": rec["native_value"], "amounts": [None] * 7, "quantities": [None] * 7,
                    "label": rec["label"], "page": rec["page"], "kind": rec["kind"],
                })
                for i in range(7):
                    if rec["amounts"][i] is not None:
                        if merged_rec["amounts"][i] is not None:
                            raise DodBudgetParseRefused(
                                f"P-1 {key} {rec['native_value']}: left/right sides both print column {_P1_COLS[i]}"
                            )
                        merged_rec["amounts"][i] = rec["amounts"][i]
                    if rec["quantities"][i] is not None:
                        merged_rec["quantities"][i] = rec["quantities"][i]

        # Page-pair join: the SAME numbered line's repeated Item Nomenclature
        # must match (whitespace-normalized) across the left/right page
        # halves; any mismatch is a join failure this parser refuses rather
        # than silently picking one side's name.
        for line_no, left_name in parent_names_by_side["left"].items():
            right_name = parent_names_by_side["right"].get(line_no)
            if right_name is None or left_name is None:
                continue
            if " ".join(left_name.split()).casefold() != " ".join(right_name.split()).casefold():
                raise DodBudgetParseRefused(
                    f"P-1 {key} line {line_no}: left/right page-pair nomenclature mismatch "
                    f"({left_name!r} vs {right_name!r})"
                )

        expected = detail_close_merged[key]
        if not _p1_amounts_close(full_merged, expected):
            raise DodBudgetParseRefused(
                f"P-1 appropriation {appropriation_code} BA {ba_code}: typed-row-model closure does not match "
                f"the printed Detail-close total (computed={full_merged} printed={expected})"
            )
        ba_summary_agg = ba_summary_merged.get(key)
        if ba_summary_agg is None:
            raise DodBudgetParseRefused(
                f"P-1 appropriation {appropriation_code} BA {ba_code} has no matching BA-Summary row"
            )
        if not _p1_amounts_close(expected, ba_summary_agg["values"]):
            raise DodBudgetParseRefused(
                f"P-1 appropriation {appropriation_code} BA {ba_code}: Detail-close does not match the "
                "BA-Summary page's own row"
            )

        appropriation_code_full = ba_summary_agg["appropriation_code_full"] or appropriation_code
        appropriation_name = ba_summary_agg["appropriation_name"] or ""
        department = next(
            (r["department"] for r in (sides.get("left") or []) + (sides.get("right") or []) if r.get("department")),
            None,
        ) or ""

        for rec in records_by_native.values():
            derived_key = (appropriation_code_full, ba_code, rec["native_value"])
            if derived_key in seen_derived_identity:
                raise DodBudgetParseRefused(f"P-1 duplicate derived line identity: {derived_key}")
            seen_derived_identity.add(derived_key)
            fields = {
                "component": department,
                "appropriation": appropriation_name,
                "appropriation_code": appropriation_code_full,
                "activity": ba_code,
                "name": rec["label"] if rec["label"] is not None else ba_summary_agg["ba_name"],
                "line": rec["native_value"],
                "actual": rec["amounts"][0], "enacted": rec["amounts"][3],
                "disc_request": rec["amounts"][4], "recon_request": rec["amounts"][5],
                "total_request": rec["amounts"][6],
                "actual_quantity": rec["quantities"][0], "enacted_quantity": rec["quantities"][3],
                "disc_request_quantity": rec["quantities"][4], "recon_request_quantity": rec["quantities"][5],
                "total_request_quantity": rec["quantities"][6],
            }
            line_key, _family = dod_budget.line_identity(
                exhibit="p1", component=fields["component"], appropriation_code=fields["appropriation_code"],
                native_kind="p1_line_item", native_value=fields["line"], fiscal_year=fiscal_year,
                budget_activity=fields["activity"],
            )
            if line_key in seen_line_keys:
                raise DodBudgetParseRefused(f"P-1 duplicate derived line identity: {line_key}")
            seen_line_keys.add(line_key)
            lines.append(dod_budget.normalized_line_from_fields(
                fields=fields, receipt=receipt, page_number=rec["page"],
                page_text=extracted.page_texts[rec["page"] - 1], source_line_number=0,
            ))

        # §5b.1 ruling 2: totals fed to reconcile_line_totals reflect only
        # what is PUBLISHABLE for this partition. When every additive
        # contribution had an identified parent, pub_merged == full_merged
        # == the printed BA-Summary row and this is a no-op; a partition
        # with an unnumbered, unpublishable contribution (e.g. 1612N BA01)
        # is fed its ADJUSTED total instead, so the hermetic reconciliation
        # matches what was actually published — while the typed-model gate
        # above (full_merged vs the printed total) already hard-verified the
        # document's OWN arithmetic is internally consistent including the
        # unpublishable amount. Named product gap (§5b.1 ruling 2): NSBDF-
        # style unnumbered full-funding rows are not represented at line
        # grain. A partition with ZERO numbered lines published at all
        # (every printed row here was an orphan) is excluded from the
        # hermetic reconcile_line_totals input entirely, per ruling 2 —
        # its arithmetic was still hard-verified above via full_merged.
        if not records_by_native:
            continue
        fields = {
            "appropriation_code": appropriation_code_full, "activity": ba_code,
            "actual": pub_merged[0], "enacted": pub_merged[3],
            "disc_request": pub_merged[4], "recon_request": pub_merged[5], "total_request": pub_merged[6],
        }
        totals.append({
            "exhibit": "p1",
            "appropriation_code": appropriation_code_full,
            "budget_activity": ba_code,
            "amounts": dod_budget.amounts_from_fields(fields, fiscal_year=fiscal_year),
            "page_number": ba_summary_agg["page"],
            "page_text_sha256": dod_budget._sha256(extracted.page_texts[ba_summary_agg["page"] - 1]),
        })

    dod_budget.reconcile_line_totals(lines, totals)
    return lines, totals


# ---------------------------------------------------------------------------
# CLI — acquire both canaries, parse, and durably publish the receipt-bound
# triad (data/government_revenue/dod_budget_{line_snapshots,collection_
# receipts}.jsonl + dod_budget_projection_state.json).
# ---------------------------------------------------------------------------

_TRIAD_LINES_FILENAME = "dod_budget_line_snapshots.jsonl"
_TRIAD_RECEIPTS_FILENAME = "dod_budget_collection_receipts.jsonl"
_TRIAD_STATE_FILENAME = "dod_budget_projection_state.json"


def _dod_budget_atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Replace one triad artifact atomically; never expose a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding=encoding) as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _read_dod_budget_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        value = json.loads(stripped)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number} is not a JSON object")
        rows.append(value)
    return rows


def run_dod_budget_acquisition(
    *,
    root: Path,
    store: Store | None,
    session: Any = None,
    observed_at: str | datetime | None = None,
    canaries: Sequence[Mapping[str, Any]] = DOD_BUDGET_CANARIES,
) -> int:
    """Acquire, parse, and durably publish BOTH P-1/R-1 canaries as one
    receipt-bound triad. All-or-nothing: any refusal on EITHER exhibit
    writes NOTHING — the previously-committed triad, if any, is left byte-
    for-byte untouched.
    """
    data_dir = root / "data" / "government_revenue"
    lines_path = data_dir / _TRIAD_LINES_FILENAME
    receipts_path = data_dir / _TRIAD_RECEIPTS_FILENAME
    state_path = data_dir / _TRIAD_STATE_FILENAME

    try:
        existing_lines = _read_dod_budget_jsonl(lines_path)
        existing_receipts = _read_dod_budget_jsonl(receipts_path)
    except (OSError, ValueError) as exc:
        print(f"::error title=dod-budget-existing-triad-unreadable::{exc}", flush=True)
        return 1

    if store is None:
        print(
            "::error title=dod-budget-store-unavailable::DoD budget object store is "
            "unavailable (R2_BUCKET/R2_ENDPOINT/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY); "
            "refusing acquisition without a receipt",
            flush=True,
        )
        return 1

    parsers = {"p1": parse_official_p1_document, "r1": parse_official_r1_document}
    results: list[dict[str, Any]] = []
    for canary in canaries:
        exhibit = str(canary["exhibit"])
        try:
            outcome = acquire_official_document(
                url=str(canary["url"]), exhibit=exhibit, fiscal_year=int(canary["fiscal_year"]),
                store=store, existing_receipts=existing_receipts, session=session, observed_at=observed_at,
            )
            parse_fn = parsers[exhibit]
            new_lines, new_totals = parse_fn(outcome.extracted, outcome.receipt)
        except Exception as exc:  # noqa: BLE001 - ANY failure anywhere refuses this exhibit, and the whole run
            print(f"::error title=dod-budget-{exhibit}-refused::{exc}", flush=True)
            return 1
        results.append({"exhibit": exhibit, "outcome": outcome, "lines": new_lines, "totals": new_totals})

    # Every exhibit acquired+parsed cleanly. Publish as ONE all-or-nothing triad.
    # A NOOP exhibit (receipt_is_duplicate: same source_url/content_sha256/
    # extraction_semantic_sha256/extractor_version/parser_version as an
    # already-retained receipt) contributes NEITHER a new receipt NOR new
    # line versions — re-observing identical bytes at a later acquisition
    # clock still stamps a genuinely later observed_at on its receipt (and
    # would stamp later known_at/effective_at on every one of its lines),
    # so feeding a NOOP exhibit through merge_receipts/append_line_snapshot_
    # versions unconditionally would silently double the ledger on every
    # idempotent re-run.
    try:
        all_new_lines = [line for r in results if r["outcome"].is_new_receipt for line in r["lines"]]
        all_new_receipts = [r["outcome"].receipt for r in results if r["outcome"].is_new_receipt]
        merged_receipts = dod_budget.merge_receipts(existing_receipts, all_new_receipts)
        merged_lines = dod_budget.append_line_snapshot_versions(existing_lines, all_new_lines)
        state = dod_budget.budget_projection_state(merged_lines, merged_receipts)
    except ValueError as exc:
        print(f"::error title=dod-budget-triad-assembly-refused::{exc}", flush=True)
        return 1

    lines_raw = "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in merged_lines) + "\n"
    receipts_raw = "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in merged_receipts) + "\n"
    state_raw = json.dumps(state, sort_keys=True, separators=(",", ":"))
    try:
        _dod_budget_atomic_write_text(lines_path, lines_raw)
        _dod_budget_atomic_write_text(receipts_path, receipts_raw)
        _dod_budget_atomic_write_text(state_path, state_raw)
    except OSError as exc:
        print(f"::error title=dod-budget-triad-write-failed::{exc}", flush=True)
        return 1

    print(
        f"DoD budget acquisition wrote {len(merged_lines)} line snapshot(s), "
        f"{len(merged_receipts)} receipt(s); projection_generation_id={state['projection_generation_id']}",
        flush=True,
    )
    for r in results:
        receipt = r["outcome"].receipt
        novelty = "NEW" if r["outcome"].is_new_receipt else "NOOP (duplicate observation)"
        print(
            f"  {r['exhibit']}: receipt_id={receipt['receipt_id']} content_sha256={receipt['content_sha256']} "
            f"object_key={receipt['immutable_object_key']} lines={len(r['lines'])} totals={len(r['totals'])} "
            f"{novelty}",
            flush=True,
        )
    return 0


def acquire(argv: list[str] | None = None) -> int:
    """CLI entrypoint: ``python -m collectors.dod_budget_live acquire``.

    Resolves the production R2 store (:func:`build_default_store`; a local
    store is reachable only via :func:`run_dod_budget_acquisition`'s explicit
    ``store`` argument, never from an environment variable here), then runs
    the full fetch → store → extract → parse → idempotence → triad-write
    chain for both canaries. Exits nonzero on ANY refusal.
    """
    parser = argparse.ArgumentParser(
        description="DoD budget live acquisition (fetch/store/extract/parse/publish)",
    )
    parser.add_argument("command", choices=["acquire"], help="the only supported command")
    parser.parse_args(argv)
    store = build_default_store()
    return run_dod_budget_acquisition(root=Path.cwd(), store=store)


def main(argv: list[str] | None = None) -> int:
    return acquire(argv)


if __name__ == "__main__":
    raise SystemExit(main())
