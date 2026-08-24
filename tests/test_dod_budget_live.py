"""Hostile suite for the DoD budget live acquisition adapter.

Every test uses an injected fake transport (never real network) and an
injected fake/local store (never real R2). Network and R2 credentials are
neither required nor consulted; a live-network test belongs on the runner
dispatched separately by PR #6378, not here.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

import pytest

from collectors import dod_budget, dod_budget_live as live
from engine.research_vault.r2_store import LocalStore


# ---------------------------------------------------------------------------
# Deterministic tiny-PDF builder (no external dependency; produces real bytes
# pdfplumber can open) — mirrors how a genuine %PDF text-layer document is
# laid out, at a fraction of the real exhibits' size.
# ---------------------------------------------------------------------------


def _make_pdf(pages_text: list[str]) -> bytes:
    objects: list[str] = []
    n_pages = len(pages_text)
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pages))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for text in pages_text:
        y = 700
        content_lines = []
        for line in text.split("\n"):
            escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            content_lines.append(f"BT /F1 12 Tf 72 {y} Td ({escaped}) Tj ET")
            y -= 18
        stream = "\n".join(content_lines)
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        content_object_number = len(objects)  # 1-based index of the stream just appended
        objects.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_object_number} 0 R >>"
        )
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{index} 0 obj\n".encode())
        out.write(obj.encode("latin-1"))
        out.write(b"\nendobj\n")
    xref_start = out.tell()
    count = len(objects) + 1
    out.write(f"xref\n0 {count}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode())
    return out.getvalue()


_P1_HEADER = "PROCUREMENT PROGRAMS (P-1)\nFiscal Year 2027\nCOMPTROLLER"
_P1_DETAIL = "Line 10  Virginia Class Submarine  Ident B  123,456"


def _p1_pdf(*, extra_pages: list[str] | None = None) -> bytes:
    pages = [_P1_HEADER, _P1_DETAIL, *(extra_pages or [])]
    return _make_pdf(pages)


# ---------------------------------------------------------------------------
# Fake HTTP transport
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, *, status_code, body=b"", url=None, chunk_size_hint=None):
        self.status_code = status_code
        self._body = body
        self.url = url
        self.closed = False
        self._chunk_size_hint = chunk_size_hint

    def iter_content(self, chunk_size=1024 * 1024):
        size = self._chunk_size_hint or chunk_size
        for start in range(0, len(self._body), size):
            yield self._body[start : start + size]

    def close(self):
        self.closed = True


class _FakeSession:
    """Records every call so a refused request path can prove it never fired."""

    def __init__(self, response_factory):
        self._response_factory = response_factory
        self.calls: list[dict] = []

    def get(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self._response_factory(url, **kwargs)


def _ok_session(pdf_bytes: bytes, *, final_url: str | None = None) -> _FakeSession:
    def factory(url, **kwargs):
        return _FakeResponse(status_code=200, body=pdf_bytes, url=final_url or url)

    return _FakeSession(factory)


# ---------------------------------------------------------------------------
# Fake object stores
# ---------------------------------------------------------------------------


class _WriteFailStore:
    """A Store whose put_bytes always reports failure."""

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        return False

    def get_bytes_strict_bounded(self, key, *, expected_byte_length, max_byte_length):
        raise AssertionError("readback must never be attempted after a failed write")

    def get_bytes(self, key):
        return None

    def list_prefix(self, prefix):
        return []

    def exists(self, key):
        return False

    def upload_time(self, key):
        return None


class _ReadbackMismatchStore:
    """A Store that accepts the write but returns different bytes on readback.

    Models both an ordinary readback corruption AND a same-key different-bytes
    collision (a store that already held something else under this content
    address) — from the caller's point of view they are indistinguishable and
    must be refused identically.
    """

    def __init__(self, wrong_bytes: bytes = b"%PDF-not-what-was-written"):
        self._wrong_bytes = wrong_bytes
        self.put_calls = 0

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        self.put_calls += 1
        return True

    def get_bytes_strict_bounded(self, key, *, expected_byte_length, max_byte_length):
        return self._wrong_bytes

    def get_bytes(self, key):
        return self._wrong_bytes

    def list_prefix(self, prefix):
        return []

    def exists(self, key):
        return True

    def upload_time(self, key):
        return None


class _ReadbackRaisesStore:
    """A Store whose bounded readback raises instead of returning bytes."""

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        return True

    def get_bytes_strict_bounded(self, key, *, expected_byte_length, max_byte_length):
        raise RuntimeError("simulated backend outage during readback")

    def get_bytes(self, key):
        return None

    def list_prefix(self, prefix):
        return []

    def exists(self, key):
        return False

    def upload_time(self, key):
        return None


# ---------------------------------------------------------------------------
# fetch_official_pdf hostile tests
# ---------------------------------------------------------------------------


def test_unallowlisted_host_refused() -> None:
    session = _ok_session(_p1_pdf())
    with pytest.raises(ValueError, match="allowlisted"):
        live.fetch_official_pdf("https://example.test/p1.pdf", session=session)
    assert session.calls == []  # the hermetic URL gate runs before any network call


def test_redirect_refused() -> None:
    def factory(url, **kwargs):
        return _FakeResponse(status_code=302, body=b"", url=url)

    session = _FakeSession(factory)
    with pytest.raises(live.DodBudgetFetchRefused, match="redirect"):
        live.fetch_official_pdf(live.DOD_BUDGET_P1_CANARY_URL, session=session)


def test_oversize_refused() -> None:
    big = _p1_pdf(extra_pages=["padding " * 200])
    assert len(big) > 64
    session = _ok_session(big)
    with pytest.raises(live.DodBudgetFetchRefused, match="cap"):
        live.fetch_official_pdf(live.DOD_BUDGET_P1_CANARY_URL, session=session, max_bytes=64)


def test_non_pdf_refused() -> None:
    session = _ok_session(b"<html>not a pdf</html>")
    with pytest.raises(live.DodBudgetFetchRefused, match="%PDF"):
        live.fetch_official_pdf(live.DOD_BUDGET_P1_CANARY_URL, session=session)


def test_final_url_diverging_from_requested_url_refused() -> None:
    session = _ok_session(_p1_pdf(), final_url=live.DOD_BUDGET_R1_CANARY_URL)
    with pytest.raises(live.DodBudgetFetchRefused, match="diverged"):
        live.fetch_official_pdf(live.DOD_BUDGET_P1_CANARY_URL, session=session)


def test_fetch_happy_path_returns_hashed_bytes() -> None:
    pdf_bytes = _p1_pdf()
    session = _ok_session(pdf_bytes)
    fetched = live.fetch_official_pdf(live.DOD_BUDGET_P1_CANARY_URL, session=session)
    assert fetched.content == pdf_bytes
    assert fetched.sha256 == dod_budget._sha256(pdf_bytes)
    assert fetched.source_url == fetched.final_url == live.DOD_BUDGET_P1_CANARY_URL


# ---------------------------------------------------------------------------
# Store write/readback hostile tests
# ---------------------------------------------------------------------------


def test_write_failed_no_receipt(tmp_path: Path) -> None:
    session = _ok_session(_p1_pdf())
    with pytest.raises(live.DodBudgetStoreWriteFailed):
        live.acquire_official_document(
            url=live.DOD_BUDGET_P1_CANARY_URL, exhibit="p1", fiscal_year=2027,
            store=_WriteFailStore(), session=session,
        )


def test_readback_wrong_bytes_refused() -> None:
    session = _ok_session(_p1_pdf())
    with pytest.raises(live.DodBudgetStoreReadbackFailed, match="did not match"):
        live.acquire_official_document(
            url=live.DOD_BUDGET_P1_CANARY_URL, exhibit="p1", fiscal_year=2027,
            store=_ReadbackMismatchStore(), session=session,
        )


def test_readback_exception_refused() -> None:
    session = _ok_session(_p1_pdf())
    with pytest.raises(live.DodBudgetStoreReadbackFailed, match="raised"):
        live.acquire_official_document(
            url=live.DOD_BUDGET_P1_CANARY_URL, exhibit="p1", fiscal_year=2027,
            store=_ReadbackRaisesStore(), session=session,
        )


def test_existing_key_holds_different_bytes_refused() -> None:
    """A key that already resolves to different content is refused, not silently trusted."""
    pdf_bytes = _p1_pdf()
    store = _ReadbackMismatchStore(wrong_bytes=b"%PDF-1.4\nsome-other-prior-document")
    session = _ok_session(pdf_bytes)
    with pytest.raises(live.DodBudgetStoreReadbackFailed):
        live.acquire_official_document(
            url=live.DOD_BUDGET_P1_CANARY_URL, exhibit="p1", fiscal_year=2027,
            store=store, session=session,
        )
    assert store.put_calls == 1  # the write was attempted; only the readback proof failed


def test_store_unavailable_refused_no_receipt_and_no_network_call() -> None:
    session = _ok_session(_p1_pdf())
    with pytest.raises(live.DodBudgetStoreUnavailable):
        live.acquire_official_document(
            url=live.DOD_BUDGET_P1_CANARY_URL, exhibit="p1", fiscal_year=2027,
            store=None, session=session,
        )
    assert session.calls == []  # refused before any fetch was attempted


def test_put_and_verify_pdf_rejects_a_non_pdf_payload() -> None:
    with pytest.raises(ValueError, match="PDF byte stream"):
        live.put_and_verify_pdf(_ReadbackMismatchStore(), b"not a pdf at all")


# ---------------------------------------------------------------------------
# Idempotence gate
# ---------------------------------------------------------------------------


def test_idempotent_noop_on_same_url_sha_and_versions(tmp_path: Path) -> None:
    pdf_bytes = _p1_pdf()
    store = LocalStore(tmp_path / "store")
    session = _ok_session(pdf_bytes)
    first = live.acquire_official_document(
        url=live.DOD_BUDGET_P1_CANARY_URL, exhibit="p1", fiscal_year=2027,
        store=store, session=session, observed_at="2026-08-24T12:00:00+00:00",
    )
    assert first.is_new_receipt is True

    session2 = _ok_session(pdf_bytes)  # identical bytes, same URL, later observation
    second = live.acquire_official_document(
        url=live.DOD_BUDGET_P1_CANARY_URL, exhibit="p1", fiscal_year=2027,
        store=store, session=session2, existing_receipts=[first.receipt],
        observed_at="2026-08-25T12:00:00+00:00",
    )
    assert second.is_new_receipt is False
    assert second.receipt["content_sha256"] == first.receipt["content_sha256"]
    assert second.receipt["extraction_semantic_sha256"] == first.receipt["extraction_semantic_sha256"]


def test_receipt_is_duplicate_matches_on_the_five_identity_fields() -> None:
    base = {
        "source_url": "https://comptroller.war.gov/x.pdf", "content_sha256": "a" * 64,
        "extraction_semantic_sha256": "b" * 64, "extractor_version": "pdfplumber-1-text+words.v1",
        "parser_version": "dod-budget-fy2027-official-text.v1",
    }
    assert live.receipt_is_duplicate([dict(base)], dict(base)) is True
    changed_sha = dict(base, content_sha256="c" * 64)
    assert live.receipt_is_duplicate([dict(base)], changed_sha) is False
    changed_extractor = dict(base, extractor_version="pdfplumber-2-text+words.v1")
    assert live.receipt_is_duplicate([dict(base)], changed_extractor) is False


def test_new_bytes_same_url_appends_new_observation_prior_retained(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    first_bytes = _p1_pdf()
    second_bytes = _p1_pdf(extra_pages=["Line 11  A Different Submarine  Ident C  1"])

    first = live.acquire_official_document(
        url=live.DOD_BUDGET_P1_CANARY_URL, exhibit="p1", fiscal_year=2027,
        store=store, session=_ok_session(first_bytes),
        observed_at="2026-08-24T12:00:00+00:00",
    )
    second = live.acquire_official_document(
        url=live.DOD_BUDGET_P1_CANARY_URL, exhibit="p1", fiscal_year=2027,
        store=store, session=_ok_session(second_bytes),
        existing_receipts=[first.receipt], observed_at="2026-08-25T12:00:00+00:00",
    )
    assert first.receipt["content_sha256"] != second.receipt["content_sha256"]
    assert second.is_new_receipt is True

    merged = dod_budget.merge_receipts([first.receipt], [second.receipt])
    assert merged == [first.receipt, second.receipt]  # prior observation stays replayable

    # a byte-identical re-observation of the SECOND document is still a no-op
    replay = live.acquire_official_document(
        url=live.DOD_BUDGET_P1_CANARY_URL, exhibit="p1", fiscal_year=2027,
        store=store, session=_ok_session(second_bytes),
        existing_receipts=merged, observed_at="2026-08-26T12:00:00+00:00",
    )
    assert replay.is_new_receipt is False


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def test_extract_pages_returns_text_and_coordinate_words() -> None:
    pdf_bytes = _p1_pdf()
    extracted = live.extract_pages(pdf_bytes)
    assert len(extracted.page_texts) == 2
    assert "PROCUREMENT PROGRAMS (P-1)" in extracted.page_texts[0]
    assert "COMPTROLLER" in extracted.page_texts[0]
    assert extracted.page_words[0]  # non-empty on the header page
    first_word = extracted.page_words[0][0]
    assert set(first_word) == {"text", "x0", "x1", "top", "bottom", "doctop"}
    assert isinstance(first_word["x0"], (int, float))


def test_extract_pages_rejects_non_pdf_bytes() -> None:
    with pytest.raises(ValueError, match="PDF byte stream"):
        live.extract_pages(b"definitely not a pdf")


# ---------------------------------------------------------------------------
# Receipt wiring / publisher / parser-version stability
# ---------------------------------------------------------------------------


def test_receipt_wiring_end_to_end_via_acquire_official_document(tmp_path: Path) -> None:
    pdf_bytes = _p1_pdf()
    store = LocalStore(tmp_path / "store")
    outcome = live.acquire_official_document(
        url=live.DOD_BUDGET_P1_CANARY_URL, exhibit="p1", fiscal_year=2027,
        store=store, session=_ok_session(pdf_bytes),
        observed_at=datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc),
    )
    receipt = outcome.receipt
    dod_budget.validate_document_receipt(receipt)
    assert receipt["publisher"] == "Office of the Under Secretary of War (Comptroller)"
    assert receipt["extractor_version"] == live.EXTRACTOR_VERSION
    assert receipt["extractor_version"].startswith("pdfplumber-")
    assert receipt["parser_version"] == live.DOD_BUDGET_LIVE_PARSER_VERSION
    assert receipt["parser_version"] == "dod-budget-fy2027-official-text.v1"
    assert receipt["immutable_object_key"] == (
        f"{dod_budget.IMMUTABLE_R2_PREFIX}{dod_budget._sha256(pdf_bytes)}.pdf"
    )
    assert receipt["raw_response_bodies_persisted"] is False
    # the stored object really is durably readable independent of this call
    key = receipt["immutable_object_key"]
    assert store.get_bytes(key) == pdf_bytes


def test_publisher_string_round_trips_through_the_live_receipt(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    outcome = live.acquire_official_document(
        url=live.DOD_BUDGET_R1_CANARY_URL, exhibit="r1", fiscal_year=2027,
        store=store, session=_ok_session(_make_pdf(["RDT&E PROGRAMS (R-1)\nFiscal Year 2027\nCOMPTROLLER"])),
    )
    assert outcome.receipt["publisher"] == dod_budget.PUBLISHER
    stale = dict(outcome.receipt)
    stale["publisher"] = "Office of the Under Secretary of Defense (Comptroller)"
    with pytest.raises(ValueError, match="publisher"):
        dod_budget.validate_document_receipt(stale)


# ---------------------------------------------------------------------------
# CLI refusal
# ---------------------------------------------------------------------------


def test_cli_refuses_naming_the_pending_parser() -> None:
    with pytest.raises(NotImplementedError, match="parser"):
        live.main([])


def test_cli_accepts_no_url_argument() -> None:
    """URLs live in code only — the CLI must not expose an injectable URL flag."""
    with pytest.raises(SystemExit):
        live.main(["--url", "https://comptroller.war.gov/evil.pdf"])


def test_module_constants_match_the_frozen_canary_design() -> None:
    assert live.DOD_BUDGET_P1_CANARY_URL == (
        "https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_p1.pdf"
    )
    assert live.DOD_BUDGET_R1_CANARY_URL == (
        "https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_r1.pdf"
    )
    assert {c["exhibit"] for c in live.DOD_BUDGET_CANARIES} == {"p1", "r1"}
    assert all(c["fiscal_year"] == 2027 for c in live.DOD_BUDGET_CANARIES)
