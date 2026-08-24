"""Live acquisition adapter for the DoD Comptroller FY P-1/R-1 exhibits.

This module supplies the piece ``collectors/dod_budget.py`` deliberately
leaves out: fetching the official PDF, writing+reading it back through the
canonical immutable object store, and deriving the deterministic page text
and coordinate-word extraction the hermetic receipt/parse core consumes.

Acquisition order is LAW (frozen design
``research/defense_intelligence/DEFENSE_D6A_BUDGET_RAIL_DESIGN_2026-08-24.md``
§4): fetch → sha256 → store PUT → strict bounded READBACK → byte/sha equality
→ only then may :func:`collectors.dod_budget.build_document_receipt` be
called. No receipt may exist for bytes that were not durably written and
verified. There is no fail-open local-store fallback anywhere in this
module's production path — a ``LocalStore`` is reachable only through an
explicit constructor argument a caller (a test) supplies directly.

The production P-1/R-1 parser (Stage 2b, delivered separately) is NOT part
of this module. :func:`main` / :func:`acquire` intentionally refuse until
that parser lands; everything else here — fetch, store, extract, receipt
wiring, and the idempotence gate — is implemented and tested now.
"""
from __future__ import annotations

import argparse
import io
import os
from dataclasses import dataclass
from datetime import datetime, timezone
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
# CLI — intentionally unwired until the production parser (Stage 2b) lands.
# ---------------------------------------------------------------------------


def acquire(argv: list[str] | None = None) -> int:
    """CLI entrypoint placeholder — refuses until the production parser lands.

    ``fetch_official_pdf``, ``put_and_verify_pdf``, ``extract_pages``, and the
    idempotence gate (``receipt_is_duplicate`` / ``acquire_official_document``)
    are implemented and covered by ``tests/test_dod_budget_live.py``. Only the
    production P-1/R-1 parser (Stage 2b, delivered separately in a different
    worker's packet) and the CLI wiring that would call it are pending; no
    live acquisition runs from this entrypoint yet.
    """
    parser = argparse.ArgumentParser(
        description=(
            "DoD budget live acquisition (fetch/store/extract only; the "
            "production P-1/R-1 parser has not landed)"
        )
    )
    parser.parse_args(argv)
    raise NotImplementedError(
        "DoD budget live acquisition CLI is intentionally unwired: the production "
        "P-1/R-1 parser (Stage 2b) is pending. fetch_official_pdf/put_and_verify_pdf/"
        "extract_pages/acquire_official_document in this module are implemented and "
        "tested; scripts/build_government_revenue.py and "
        "DOD_BUDGET_PRODUCTION_ACTIVATION_ENABLED remain untouched until that parser "
        "and its hostile suite land in a follow-up packet."
    )


def main(argv: list[str] | None = None) -> int:
    return acquire(argv)


if __name__ == "__main__":
    raise SystemExit(main())
