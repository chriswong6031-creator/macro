"""Hostile suite for the DoD budget live acquisition adapter.

Every test uses an injected fake transport (never real network) and an
injected fake/local store (never real R2). Network and R2 credentials are
neither required nor consulted; a live-network test belongs on the runner
dispatched separately by PR #6378, not here.
"""
from __future__ import annotations

import io
import json
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


def _make_pdf_words(pages: list[list[tuple[float, float, str]]]) -> bytes:
    """Build a real %PDF whose words land at EXACT (x, y) coordinates.

    Unlike ``_make_pdf`` (one left-flowing ``Tj`` per line, font-metric-
    dependent word positions), each ``(x, y, text)`` triple here is placed
    via an absolute text matrix (``Tm``), giving column-accurate control —
    required to exercise the production P-1/R-1 parser's boundary-bucket
    column assignment and header-anchor logic with synthetic fixtures that
    do not depend on the real (uncommitted) 6MB exhibits.
    """
    objects: list[str] = []
    n_pages = len(pages)
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pages))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>")
    # WinAnsiEncoding pinned explicitly: PDF's Standard font encoding maps
    # code 0x27 to U+2019 (curly quoteright), not the ASCII apostrophe, which
    # would silently break every literal "President's Budget" furniture
    # match in the classifier against straight-apostrophe extracted text.
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for words in pages:
        content_lines = []
        for x, y, text in words:
            escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            content_lines.append(f"BT /F1 12 Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({escaped}) Tj ET")
        stream = "\n".join(content_lines)
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        content_object_number = len(objects)
        objects.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1600 792] "
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


# Column x0 positions modeled on the real FY2027 R-1 layout (survey-derived,
# scratchpad survey_common.py VALUE_HEADER_WORDS / find_value_anchors): 7
# value columns, header words right-aligned near these x1 positions; body
# tokens right-aligned to roughly the same column.
_R1_COL_X = [400.0, 460.0, 520.0, 580.0, 640.0, 700.0, 760.0]
_R1_HEADER_WORDS = ["Actuals", "Enacted", "Plan", "Total", "Request", "Request", "Total"]
_R1_ACT_X = 290.0  # within the classifier's Act window (283 <= x0 <= 312)
_R1_SEC_X = 320.0  # within the classifier's Sec window (312 <= x0 <= 333)


def _r1_row(
    y: float, *, line_no: str, pe: str, name: str, act: str = "01", sec: str = "U",
    values: list[str | None], extra_prefix: list[tuple[float, str]] | None = None,
) -> list[tuple[float, float, str]]:
    """One R-1 physical detail row: Line No/PE/Item/Act/Sec at fixed x
    positions matching the production classifier's expected windows, then
    up to 7 values at the fixed column positions (None = blank cell)."""
    words = [
        (72.0, y, line_no), (100.0, y, pe), (180.0, y, name),
        (_R1_ACT_X, y, act), (_R1_SEC_X, y, sec),
    ]
    for x, text in extra_prefix or []:
        words.append((x, y, text))
    for col, value in enumerate(values):
        if value is not None:
            words.append((_R1_COL_X[col] - 7.0 * len(value), y, value))
    return words


def _r1_golden_page(
    *, line_no: str = "1", pe: str = "0601102A", name: str = "Test Program",
    values: list[str | None] | None = None,
) -> list[tuple[float, float, str]]:
    """One complete, self-reconciling R-1 Detail page: one detail line closed
    by a matching BA subtotal ("Basic research") and appropriation total
    ("Total Test Appropriation Army"), all three
    carrying the SAME values so the document reconciles exactly."""
    values = values if values is not None else ["1000", "1100", None, "1100", "1200", None, "1200"]
    header_rows = [
        (72.0, 700.0, "UNCLASSIFIED"),
        (72.0, 685.0, "Department of the Navy"),
        (72.0, 670.0, "FY 2027 President's Budget"),
        (72.0, 655.0, "Exhibit R-1"),
        (72.0, 640.0, "Total Obligational Authority"),
        (72.0, 625.0, "(Dollars in Thousands)"),
        (72.0, 610.0, "Appropriation: 2040A Test Appropriation Army"),
        (72.0, 595.0, "No Number Item Act Sec"),
    ]
    header_words = [(_R1_COL_X[i] - 6.0 * len(w), 580.0, w) for i, w in enumerate(_R1_HEADER_WORDS)]
    detail = _r1_row(565.0, line_no=line_no, pe=pe, name=name, values=values)
    ba_subtotal = [(72.0, 550.0, "Basic research")] + [
        (_R1_COL_X[c] - 7.0 * len(v), 550.0, v) for c, v in enumerate(values) if v is not None
    ]
    appr_total = [(72.0, 535.0, "Total Test Appropriation Army")] + [
        (_R1_COL_X[c] - 7.0 * len(v), 535.0, v) for c, v in enumerate(values) if v is not None
    ]
    return header_rows + header_words + detail + ba_subtotal + appr_total


_R1_TITLE_PAGE = [(72.0, 700.0, "RDT&E PROGRAMS (R-1)"), (72.0, 680.0, "Fiscal Year 2027"), (72.0, 660.0, "COMPTROLLER")]


def _r1_pdf(*pages: list[tuple[float, float, str]]) -> bytes:
    """Synthetic R-1 document: title page + each caller-supplied page."""
    return _make_pdf_words([_R1_TITLE_PAGE, *pages])


_P1_HEADER = "PROCUREMENT PROGRAMS (P-1)\nFiscal Year 2027\nCOMPTROLLER"
_P1_DETAIL = "Line 10  Virginia Class Submarine  Ident B  123,456"


def _p1_pdf(*, extra_pages: list[str] | None = None) -> bytes:
    pages = [_P1_HEADER, _P1_DETAIL, *(extra_pages or [])]
    return _make_pdf(pages)


# ---------------------------------------------------------------------------
# P-1 production-parser synthetic fixtures (column-accurate, real vocabulary,
# modeled on the real FY2027 layout survey — scratchpad survey_p1.py).
# ---------------------------------------------------------------------------

_P1_TITLE_PAGE = [(72.0, 700.0, "PROCUREMENT PROGRAMS (P-1)"), (72.0, 680.0, "Fiscal Year 2027"), (72.0, 660.0, "COMPTROLLER")]
# Anchors start well above _p1_assign_numeric's min_x0=280.0 floor (a value
# whose own x0 falls under that floor is invisible to the classifier — not
# even reported as unassigned, just silently excluded from the candidate
# scan) with wide (150pt) gaps so even a 10-character value's LEFT edge
# never crosses back under the floor after being right-aligned to a bucket.
_P1_LEFT_ANCHORS = [
    ("Qty", 450.0), ("Cost", 600.0), ("Qty", 750.0), ("Cost", 900.0), ("Qty", 1050.0),
    ("Cost", 1200.0), ("Qty", 1350.0), ("Cost", 1500.0), ("Qty", 1650.0),
]
_P1_RIGHT_ANCHORS = [("Cost", 450.0), ("Qty", 600.0), ("Cost", 750.0), ("Qty", 900.0), ("Cost", 1050.0)]
_P1_LEFT_SUMMARY_WORDS = [("Actuals", 450.0), ("Enacted", 600.0), ("Plan", 750.0), ("Total", 900.0)]
_P1_RIGHT_SUMMARY_WORDS = [("Request", 450.0), ("Request", 600.0), ("Total", 750.0)]


def _p1_value_word(anchors: list[tuple[str, float]], col: int, text: str, y: float) -> tuple[float, float, str]:
    """Place `text` so its RIGHT edge lands inside column `col`'s exact
    boundary-bucket [anchors[col].x0, anchors[col+1].x0) (or +90 for the
    last column) — matching _p1_assign_numeric's zero-tolerance rule."""
    left = anchors[col][1]
    right = anchors[col + 1][1] if col + 1 < len(anchors) else left + 90.0
    x1_target = left + 30.0
    x0 = x1_target - 7.0 * len(text)
    assert x0 >= 300.0, f"fixture value {text!r} at col {col} would fall under the classifier's min_x0 floor"
    assert x1_target < right, f"fixture value {text!r} at col {col} overruns its own bucket"
    return (x0, y, text)


def _p1_summary_word(words: list[tuple[str, float]], idx: int, text: str, y: float) -> tuple[float, float, str]:
    x1_target = words[idx][1] + 30.0
    x0 = x1_target - 7.0 * len(text)
    assert x0 >= 300.0, f"fixture summary value {text!r} at idx {idx} would fall under the classifier's min_x0 floor"
    return (x0, y, text)


def _p1_detail_row(
    y: float, *, anchors: list[tuple[str, float]], line_no: str, name: str,
    ident: str = "B", sec: str = "U", slots: dict[int, str] | None = None,
) -> list[tuple[float, float, str]]:
    """One P-1 detail-page physical row (Qty/Cost interleaved value grid)."""
    words = [(40.0, y, line_no), (60.0, y, name), (245.0, y, ident), (273.0, y, sec)]
    for col, text in (slots or {}).items():
        words.append(_p1_value_word(anchors, col, text, y))
    return words


def _p1_less_row(y: float, *, anchors: list[tuple[str, float]], prefix: str, slots: dict[int, str] | None = None) -> list[tuple[float, float, str]]:
    words = [(60.0, y, prefix)]
    for col, text in (slots or {}).items():
        words.append(_p1_value_word(anchors, col, text, y))
    return words


def _p1_detail_page(
    *, appropriation_code: str = "2031A", appropriation_name: str = "Test Procurement Army",
    ba_code: str = "01", ba_name: str = "Test Activity", side: str,
    rows: list[list[tuple[float, float, str]]], ba_close_slots: dict[int, str],
    appr_close_slots: dict[int, str],
) -> list[tuple[float, float, str]]:
    anchors = _P1_LEFT_ANCHORS if side == "left" else _P1_RIGHT_ANCHORS
    words: list[tuple[float, float, str]] = [
        (72.0, 700.0, "UNCLASSIFIED"), (72.0, 685.0, "Department of the Army"),
        (72.0, 670.0, "FY 2027 President's Budget"), (72.0, 655.0, "Exhibit P-1"),
        (72.0, 640.0, "Total Obligational Authority"),
        (72.0, 625.0, f"{appropriation_code} Detail Apr 2026"),
        (72.0, 610.0, "(Dollars in Thousands)"),
        (72.0, 595.0, f"Appropriation: {appropriation_code[:-1]} {appropriation_name}"),
    ]
    if side == "left":
        words.append((72.0, 580.0, "Line Ident"))
        words.append((72.0, 565.0, "No Item Nomenclature Code Sec Qty Cost Qty Cost Qty Cost Qty Cost Qty"))
    else:
        words.append((72.0, 580.0, "Line Ident"))
        words.append((72.0, 565.0, "No Item Nomenclature Code Sec Cost Qty Cost Qty Cost"))
    for label, x in anchors:
        words.append((x, 550.0, label))
    words.append((72.0, 535.0, f"Budget Activity {ba_code}: {ba_name}"))
    y = 520.0
    for row in rows:
        words.extend([(x, y, text) for x, _orig_y, text in row])
        y -= 15.0
    ba_close = [(72.0, y, f"Total {ba_name}")]
    for col, text in ba_close_slots.items():
        ba_close.append(_p1_value_word(anchors, col, text, y))
    words.extend(ba_close)
    y -= 15.0
    appr_close = [(72.0, y, f"Total {appropriation_name}")]
    for col, text in appr_close_slots.items():
        appr_close.append(_p1_value_word(anchors, col, text, y))
    words.extend(appr_close)
    return words


def _p1_ba_summary_page(
    *, appropriation_code: str = "2031A", appropriation_name: str = "Test Procurement Army",
    ba_code: str = "01", ba_name: str = "Test Activity", side: str, ba_slots: dict[int, str],
    appr_slots: dict[int, str],
) -> list[tuple[float, float, str]]:
    summary_words = _P1_LEFT_SUMMARY_WORDS if side == "left" else _P1_RIGHT_SUMMARY_WORDS
    words: list[tuple[float, float, str]] = [
        (72.0, 700.0, "UNCLASSIFIED"), (72.0, 685.0, "Department of the Army"),
        (72.0, 670.0, "FY 2027 President's Budget"), (72.0, 655.0, "Exhibit P-1"),
        (72.0, 640.0, "Total Obligational Authority"),
        (72.0, 625.0, f"{appropriation_code} Budget Activity Summary Apr 2026"),
        (72.0, 610.0, "(Dollars in Thousands)"),
        (72.0, 595.0, f"Appropriation: {appropriation_name}"),
        (72.0, 580.0, "Budget Activity"),
    ]
    for label, x in summary_words:
        words.append((x, 565.0, label))
    ba_row = [(72.0, 550.0, f"{ba_code}. {ba_name}")]
    for idx, text in ba_slots.items():
        ba_row.append(_p1_summary_word(summary_words, idx, text, 550.0))
    words.extend(ba_row)
    appr_row = [(72.0, 535.0, f"Total {appropriation_name}")]
    for idx, text in appr_slots.items():
        appr_row.append(_p1_summary_word(summary_words, idx, text, 535.0))
    words.extend(appr_row)
    return words


def _p1_golden_pages(
    *, line_no: str = "10", name: str = "Test Widget",
    left_values: dict[int, str] | None = None, right_values: dict[int, str] | None = None,
) -> list[list[tuple[float, float, str]]]:
    """A complete, self-reconciling minimal P-1 document: LEFT+RIGHT Detail
    pages carrying ONE numbered line (rule 1, no Less-children) plus
    matching LEFT+RIGHT BA-Summary pages. left_values/right_values key by
    Cost-slot index (LEFT: 1,3,5,7 map to fy25/26disc/26pl119/26total;
    RIGHT: 0,2,4 map to fy27disc/27mand/27total)."""
    left_values = left_values if left_values is not None else {1: "1,000", 7: "1,000"}
    right_values = right_values if right_values is not None else {0: "1,200", 4: "1,200"}
    left_detail_row = _p1_detail_row(520.0, anchors=_P1_LEFT_ANCHORS, line_no=line_no, name=name, slots=left_values)
    right_detail_row = _p1_detail_row(520.0, anchors=_P1_RIGHT_ANCHORS, line_no=line_no, name=name, slots=right_values)
    left_page = _p1_detail_page(side="left", rows=[left_detail_row], ba_close_slots=left_values, appr_close_slots=left_values)
    right_page = _p1_detail_page(side="right", rows=[right_detail_row], ba_close_slots=right_values, appr_close_slots=right_values)
    # BA-Summary slots: LEFT idx 0..3 = Actuals/Enacted/Plan/Total; map from
    # Cost-slot values (1,3,5,7) -> summary idx (0,1,2,3); RIGHT idx 0..2 =
    # Request/Request/Total from Cost-slot (0,2,4) -> summary idx (0,1,2).
    left_summary_map = {1: 0, 3: 1, 5: 2, 7: 3}
    right_summary_map = {0: 0, 2: 1, 4: 2}
    left_ba_slots = {left_summary_map[k]: v for k, v in left_values.items() if k in left_summary_map}
    right_ba_slots = {right_summary_map[k]: v for k, v in right_values.items() if k in right_summary_map}
    left_summary = _p1_ba_summary_page(side="left", ba_slots=left_ba_slots, appr_slots=left_ba_slots)
    right_summary = _p1_ba_summary_page(side="right", ba_slots=right_ba_slots, appr_slots=right_ba_slots)
    return [left_page, right_page, left_summary, right_summary]


def _p1_pdf_words(*pages: list[tuple[float, float, str]]) -> bytes:
    return _make_pdf_words([_P1_TITLE_PAGE, *pages])


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


def test_cli_requires_the_acquire_subcommand() -> None:
    """The production parser has landed; the CLI now requires an explicit
    ``acquire`` subcommand (argparse SystemExit on a missing/unknown one),
    superseding the old "parser pending" NotImplementedError contract."""
    with pytest.raises(SystemExit):
        live.main([])
    with pytest.raises(SystemExit):
        live.main(["bogus-command"])


def test_cli_accepts_no_url_argument() -> None:
    """URLs live in code only — the CLI must not expose an injectable URL flag."""
    with pytest.raises(SystemExit):
        live.main(["--url", "https://comptroller.war.gov/evil.pdf"])


def test_cli_refuses_cleanly_with_no_store_configured(monkeypatch) -> None:
    """python -m collectors.dod_budget_live acquire with no R2 env vars set
    exits nonzero and raises nothing (a clean refusal, not a crash)."""
    for key in ("R2_BUCKET", "R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert live.main(["acquire"]) != 0


def test_module_constants_match_the_frozen_canary_design() -> None:
    assert live.DOD_BUDGET_P1_CANARY_URL == (
        "https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_p1.pdf"
    )
    assert live.DOD_BUDGET_R1_CANARY_URL == (
        "https://comptroller.war.gov/Portals/45/Documents/defbudget/FY2027/FY2027_r1.pdf"
    )
    assert {c["exhibit"] for c in live.DOD_BUDGET_CANARIES} == {"p1", "r1"}
    assert all(c["fiscal_year"] == 2027 for c in live.DOD_BUDGET_CANARIES)


# ---------------------------------------------------------------------------
# Production parser hostile suite (§5b, §5b.1 gate-zero rulings). All
# fixtures are synthetic, built from _p1_pdf_words/_r1_pdf (no dependency on
# the real, uncommitted 6MB exhibits).
# ---------------------------------------------------------------------------


def _receipt_for(pdf_bytes: bytes, *, exhibit: str, fiscal_year: int = 2027) -> dict:
    pages = live.extract_pages(pdf_bytes).page_texts
    sha = dod_budget._sha256(pdf_bytes)
    url = live.DOD_BUDGET_P1_CANARY_URL if exhibit == "p1" else live.DOD_BUDGET_R1_CANARY_URL
    return dod_budget.build_document_receipt(
        source_url=url, final_url=url, pdf_bytes=pdf_bytes, pages=pages,
        fiscal_year=fiscal_year, exhibit=exhibit, observed_at="2026-08-24T12:00:00Z",
        immutable_object_key=f"{dod_budget.IMMUTABLE_R2_PREFIX}{sha}.pdf",
        extractor_version=live.EXTRACTOR_VERSION, parser_version=live.DOD_BUDGET_LIVE_PARSER_VERSION,
    )


def _parse_r1(pdf_bytes: bytes, *, fiscal_year: int = 2027):
    extracted = live.extract_pages(pdf_bytes)
    receipt = _receipt_for(pdf_bytes, exhibit="r1", fiscal_year=fiscal_year)
    return live.parse_official_r1_document(extracted, receipt)


def _parse_p1(pdf_bytes: bytes, *, fiscal_year: int = 2027):
    extracted = live.extract_pages(pdf_bytes)
    receipt = _receipt_for(pdf_bytes, exhibit="p1", fiscal_year=fiscal_year)
    return live.parse_official_p1_document(extracted, receipt)


# --- R-1 ---------------------------------------------------------------


def test_r1_golden_fixture_parses_and_reconciles_cleanly() -> None:
    pdf_bytes = _r1_pdf(_r1_golden_page())
    lines, totals = _parse_r1(pdf_bytes)
    assert len(lines) == 1 and len(totals) == 1
    amounts = {a["semantic"]: a["amount_usd"] for a in lines[0]["amounts"]}
    assert amounts["historical_actual"] == 1_000_000.0
    assert amounts["prior_year_enacted_reference"] == 1_100_000.0
    assert amounts["discretionary_request"] == 1_200_000.0
    assert amounts["reconciliation_request"] is None
    assert amounts["president_budget_request_total"] == 1_200_000.0


def test_r1_bare_minus_negative_value_parses_with_correct_sign() -> None:
    """§5b.1 ruling 1: a bare-minus token (no wrapping parens) is negative."""
    pdf_bytes = _r1_pdf(_r1_golden_page(values=["-37", "1100", None, "1100", "1200", None, "1200"]))
    lines, _totals = _parse_r1(pdf_bytes)
    amounts = {a["semantic"]: a["amount_usd"] for a in lines[0]["amounts"]}
    assert amounts["historical_actual"] == -37_000.0


def test_r1_unrecognized_numeric_token_form_refused() -> None:
    """§5b.1 ruling 1: only plain/(paren)/(paren-minus)/bare-minus are
    recognized; an unbalanced paren (e.g. "(123", missing its close) looks
    numeric-shaped enough to reach the number parser but is not one of the
    four recognized forms, and refuses rather than silently guessing."""
    pdf_bytes = _r1_pdf(_r1_golden_page(values=["(37", "1100", None, "1100", "1200", None, "1200"]))
    with pytest.raises(ValueError, match="unrecognized numeric token"):
        _parse_r1(pdf_bytes)


def test_r1_blank_cell_is_none_never_coerced_to_zero() -> None:
    pdf_bytes = _r1_pdf(_r1_golden_page(values=["1000", "1100", None, "1100", "1200", None, "1200"]))
    lines, _totals = _parse_r1(pdf_bytes)
    amounts = {a["semantic"]: a["amount_usd"] for a in lines[0]["amounts"]}
    assert amounts["reconciliation_request"] is None
    assert 0.0 not in (amounts["reconciliation_request"],) or amounts["reconciliation_request"] is None


def test_r1_missing_unit_marker_refused() -> None:
    page = [w for w in _r1_golden_page() if w[2] != "(Dollars in Thousands)"]
    pdf_bytes = _r1_pdf(page)
    with pytest.raises(live.DodBudgetParseRefused, match="Dollars in Thousands"):
        _parse_r1(pdf_bytes)


def test_r1_unrecognized_header_layout_refused_whole_document() -> None:
    """A header-layout mutation (missing value-column header words) refuses
    the WHOLE document — no plausible partial rows."""
    page = [w for w in _r1_golden_page() if w[2] not in ("Actuals", "Enacted", "Plan", "Total")]
    pdf_bytes = _r1_pdf(page)
    with pytest.raises(live.DodBudgetParseRefused, match="7-column header"):
        _parse_r1(pdf_bytes)


def test_r1_boundary_bucket_violation_refused() -> None:
    """A numeric token that lands outside every column's boundary bucket
    refuses rather than guessing the nearest column."""
    page = list(_r1_golden_page())
    page.append((250.0, 550.5, "9999"))  # x0=250 < min_x0=336.0 value-zone floor is fine,
    # so place it INSIDE the value zone but between real bucket boundaries instead:
    page = [w for w in _r1_golden_page()]
    page.append((900.0, 565.0, "9999"))  # far right of every real column x1+tol
    pdf_bytes = _r1_pdf(page)
    with pytest.raises(live.DodBudgetParseRefused, match="unassignable"):
        _parse_r1(pdf_bytes)


def test_r1_duplicate_line_key_within_one_document_refused() -> None:
    """Two detail lines with the identical (component, appropriation_code,
    PE, budget_activity) derived identity — a genuine duplicate — refuses."""
    page = _r1_golden_page()
    dup_row = _r1_row(519.0, line_no="2", pe="0601102A", name="Test Program",
                       values=["1000", "1100", None, "1100", "1200", None, "1200"])
    # Insert as its own BA-subtotal-closed run so classification succeeds
    # before the duplicate-identity check fires.
    page = page + dup_row + [(72.0, 504.0, "Basic research")] + [
        (_R1_COL_X[c] - 7.0 * len(v), 504.0, v)
        for c, v in enumerate(["1000", "1100", None, "1100", "1200", None, "1200"]) if v is not None
    ]
    pdf_bytes = _r1_pdf(page)
    with pytest.raises(live.DodBudgetParseRefused, match="duplicate"):
        _parse_r1(pdf_bytes)


def test_r1_0400d_consolidated_only_lines_emit_pp89_verification_only_and_hard_checks() -> None:
    """§5b.1 ruling 5: 0400D emits lines ONLY from the consolidated table
    (page < 89); a pp.89+ per-agency section contributes no published line,
    but its own total must still close against the consolidated total."""
    consolidated_header = [
        (72.0, 700.0, "UNCLASSIFIED"), (72.0, 685.0, "Defense-Wide"),
        (72.0, 670.0, "FY 2027 President's Budget"), (72.0, 655.0, "Exhibit R-1"),
        (72.0, 640.0, "Total Obligational Authority"),
        (72.0, 625.0, "(Dollars in Thousands)"),
        (72.0, 610.0, "Appropriation: 0400D Defense-Wide RDTE"),
        (72.0, 595.0, "No Number Item Act Sec"),
    ]
    header_words = [(_R1_COL_X[i] - 6.0 * len(w), 580.0, w) for i, w in enumerate(_R1_HEADER_WORDS)]
    values = ["1000", "1100", None, "1100", "1200", None, "1200"]
    detail = _r1_row(565.0, line_no="1", pe="0601102A", name="Consolidated", values=values)
    ba_subtotal = [(72.0, 550.0, "Basic research")] + [
        (_R1_COL_X[c] - 7.0 * len(v), 550.0, v) for c, v in enumerate(values) if v is not None
    ]
    appr_total = [(72.0, 535.0, "Total Defense-Wide RDTE")] + [
        (_R1_COL_X[c] - 7.0 * len(v), 535.0, v) for c, v in enumerate(values) if v is not None
    ]
    consolidated_page = consolidated_header + header_words + detail + ba_subtotal + appr_total

    peragency_header = [
        (72.0, 700.0, "UNCLASSIFIED"), (72.0, 685.0, "Classified Organization"),
        (72.0, 670.0, "FY 2027 President's Budget"), (72.0, 655.0, "Exhibit R-1"),
        (72.0, 640.0, "Total Obligational Authority"),
        (72.0, 625.0, "(Dollars in Thousands)"),
        (72.0, 610.0, "Appropriation: 0400D Defense-Wide RDTE"),
        (72.0, 595.0, "No Number Item Act Sec"),
    ]
    peragency_detail = _r1_row(565.0, line_no="999", pe="999999999", name="Classified", values=values)
    peragency_ba = [(72.0, 550.0, "Basic research")] + [
        (_R1_COL_X[c] - 7.0 * len(v), 550.0, v) for c, v in enumerate(values) if v is not None
    ]
    peragency_total = [(72.0, 535.0, "Total Classified Organization")] + [
        (_R1_COL_X[c] - 7.0 * len(v), 535.0, v) for c, v in enumerate(values) if v is not None
    ]
    peragency_page = peragency_header + header_words + peragency_detail + peragency_ba + peragency_total

    # Pad with blank pages so the per-agency page number exceeds 88 (title
    # page = 1, so 87 filler pages puts the consolidated page at 2 and the
    # per-agency page at 90).
    filler = [(72.0, 700.0, "UNCLASSIFIED"), (72.0, 685.0, "THIS PAGE INTENTIONALLY LEFT BLANK")]
    pages = [consolidated_page] + [filler] * 87 + [peragency_page]
    pdf_bytes = _r1_pdf(*pages)
    lines, totals = _parse_r1(pdf_bytes)
    assert len(lines) == 1  # only the consolidated line publishes
    assert lines[0]["native_identifier"]["value"] == "0601102A"
    assert lines[0]["provenance"]["page_number"] == 2

    # Now corrupt the per-agency detail/BA-subtotal/total TOGETHER (so the
    # per-agency page stays internally self-consistent and ONLY the
    # cross-page pp.89+-vs-consolidated hard check can catch this): the
    # hard check must refuse.
    bad_values = ["1000", "1100", None, "1100", "9999", None, "9999"]
    peragency_detail_bad = _r1_row(565.0, line_no="999", pe="999999999", name="Classified", values=bad_values)
    peragency_ba_bad = [(72.0, 550.0, "Basic research")] + [
        (_R1_COL_X[c] - 7.0 * len(v), 550.0, v) for c, v in enumerate(bad_values) if v is not None
    ]
    peragency_total_bad = [(72.0, 535.0, "Total Classified Organization")] + [
        (_R1_COL_X[c] - 7.0 * len(v), 535.0, v) for c, v in enumerate(bad_values) if v is not None
    ]
    peragency_page_bad = peragency_header + header_words + peragency_detail_bad + peragency_ba_bad + peragency_total_bad
    pdf_bytes_bad = _r1_pdf(*([consolidated_page] + [filler] * 87 + [peragency_page_bad]))
    with pytest.raises(live.DodBudgetParseRefused, match="does not close"):
        _parse_r1(pdf_bytes_bad)


def test_r1_fiscal_year_and_exhibit_mismatch_refused_through_parser() -> None:
    """verify_document_header (hermetic, already tested in
    tests/test_dod_budget_collector.py) is proven to also gate the LIVE
    parser path: a fiscal-year mismatch refuses before any row is read."""
    pdf_bytes = _r1_pdf(_r1_golden_page())
    with pytest.raises(ValueError, match="fiscal year"):
        _parse_r1(pdf_bytes, fiscal_year=2026)


# --- P-1 -----------------------------------------------------------------


def test_p1_golden_fixture_parses_and_reconciles_cleanly() -> None:
    pdf_bytes = _p1_pdf_words(*_p1_golden_pages())
    lines, totals = _parse_p1(pdf_bytes)
    assert len(lines) == 1 and len(totals) == 1
    assert lines[0]["native_identifier"] == {"kind": "p1_line_item", "value": "10"}


def test_p1_value_bearing_additive_child_publishes_its_own_record() -> None:
    """§5b.1 ruling 3: an Advance Procurement (CY) child publishes as its
    OWN record, native value "<parent line no>--<slugged child label>"."""
    left_values = {1: "1,000", 7: "1,000"}
    right_values = {0: "1,200", 4: "1,200"}
    left_row = _p1_detail_row(520.0, anchors=_P1_LEFT_ANCHORS, line_no="10", name="Test Widget", slots={})
    right_row = _p1_detail_row(520.0, anchors=_P1_RIGHT_ANCHORS, line_no="10", name="Test Widget", slots={})
    left_ap = [(60.0, 505.0, "Advance Procurement (CY)"), _p1_value_word(_P1_LEFT_ANCHORS, 1, "1,000", 505.0),
               _p1_value_word(_P1_LEFT_ANCHORS, 7, "1,000", 505.0)]
    right_ap = [(60.0, 505.0, "Advance Procurement (CY)"), _p1_value_word(_P1_RIGHT_ANCHORS, 0, "1,200", 505.0),
                _p1_value_word(_P1_RIGHT_ANCHORS, 4, "1,200", 505.0)]
    left_page = _p1_detail_page(side="left", rows=[left_row, left_ap], ba_close_slots=left_values, appr_close_slots=left_values)
    right_page = _p1_detail_page(side="right", rows=[right_row, right_ap], ba_close_slots=right_values, appr_close_slots=right_values)
    left_summary = _p1_ba_summary_page(side="left", ba_slots={0: "1,000", 3: "1,000"}, appr_slots={0: "1,000", 3: "1,000"})
    right_summary = _p1_ba_summary_page(side="right", ba_slots={0: "1,200", 2: "1,200"}, appr_slots={0: "1,200", 2: "1,200"})
    pdf_bytes = _p1_pdf_words(left_page, right_page, left_summary, right_summary)
    lines, totals = _parse_p1(pdf_bytes)
    natives = {l["native_identifier"]["value"] for l in lines}
    assert "10" in natives
    child = [l for l in natives if l.startswith("10--")]
    assert child == ["10--advance-procurement-cy"]
    child_line = next(l for l in lines if l["native_identifier"]["value"] == child[0])
    assert child_line["program_name"] == "Advance Procurement (CY)"
    amounts = {a["semantic"]: a["amount_usd"] for a in child_line["amounts"]}
    assert amounts["historical_actual"] == 1_000_000.0
    assert amounts["discretionary_request"] == 1_200_000.0


def test_p1_duplicate_child_derived_identity_refused() -> None:
    """Two value-bearing additive children under the SAME parent with the
    SAME printed label derive the SAME identity ("10--advance-procurement-
    cy") and cannot both be merged into one published record — refused
    (surfaces as the same column-collision guard that also protects a
    genuine left/right double-print of one column)."""
    left_row = _p1_detail_row(520.0, anchors=_P1_LEFT_ANCHORS, line_no="10", name="Test Widget", slots={})
    ap1 = [(60.0, 505.0, "Advance Procurement (CY)"), _p1_value_word(_P1_LEFT_ANCHORS, 1, "1,000", 505.0)]
    ap2 = [(60.0, 490.0, "Advance Procurement (CY)"), _p1_value_word(_P1_LEFT_ANCHORS, 1, "500", 490.0)]
    left_page = _p1_detail_page(side="left", rows=[left_row, ap1, ap2], ba_close_slots={1: "1,500"}, appr_close_slots={1: "1,500"})
    right_row = _p1_detail_row(520.0, anchors=_P1_RIGHT_ANCHORS, line_no="10", name="Test Widget", slots={})
    right_page = _p1_detail_page(side="right", rows=[right_row], ba_close_slots={}, appr_close_slots={})
    left_summary = _p1_ba_summary_page(side="left", ba_slots={0: "1,500"}, appr_slots={0: "1,500"})
    right_summary = _p1_ba_summary_page(side="right", ba_slots={}, appr_slots={})
    pdf_bytes = _p1_pdf_words(left_page, right_page, left_summary, right_summary)
    with pytest.raises(live.DodBudgetParseRefused, match="both print column"):
        _parse_p1(pdf_bytes)


def test_p1_bare_two_number_row_never_misclassified_as_a_numbered_line() -> None:
    """§5b.1 ruling 6: a bare two-number row (no non-numeric nomenclature
    after the leading digit run) is never mistaken for a numbered detail
    line, even when its first token could look like a plausible Line No —
    it is read as an unlabeled net-memo row instead (P-1 p.121 "20 20")."""
    left_line = _p1_detail_row(520.0, anchors=_P1_LEFT_ANCHORS, line_no="24", name="Test Missile", slots={1: "(500)"})
    left_less = _p1_less_row(505.0, anchors=_P1_LEFT_ANCHORS, prefix="Less: Advance Procurement (PY)", slots={1: "(480)"})
    left_netmemo = [_p1_value_word(_P1_LEFT_ANCHORS, 1, "20", 490.0)]  # bare "20" alone, net = -(-500)+(-480)=20
    left_next = _p1_detail_row(475.0, anchors=_P1_LEFT_ANCHORS, line_no="20", name="Genuinely Line Twenty", slots={1: "50"})
    left_page = _p1_detail_page(
        side="left", rows=[left_line, left_less, left_netmemo, left_next],
        ba_close_slots={1: "70"}, appr_close_slots={1: "70"},
    )
    right_row = _p1_detail_row(520.0, anchors=_P1_RIGHT_ANCHORS, line_no="24", name="Test Missile", slots={})
    right_next = _p1_detail_row(505.0, anchors=_P1_RIGHT_ANCHORS, line_no="20", name="Genuinely Line Twenty", slots={})
    right_page = _p1_detail_page(side="right", rows=[right_row, right_next], ba_close_slots={}, appr_close_slots={})
    left_summary = _p1_ba_summary_page(side="left", ba_slots={0: "70"}, appr_slots={0: "70"})
    right_summary = _p1_ba_summary_page(side="right", ba_slots={}, appr_slots={})
    pdf_bytes = _p1_pdf_words(left_page, right_page, left_summary, right_summary)
    lines, _totals = _parse_p1(pdf_bytes)
    natives = {l["native_identifier"]["value"]: l for l in lines}
    assert set(natives) == {"24", "20"}
    resolved = {a["semantic"]: a["amount_usd"] for a in natives["24"]["amounts"]}
    assert resolved["historical_actual"] == 20_000.0  # the net-memo value, not the -500 own row
    assert natives["20"]["program_name"] == "Genuinely Line Twenty"


def test_p1_less_row_without_resolving_net_memo_refused() -> None:
    """A value-bearing Less: row with NO following net-memo row before the
    next line/group boundary refuses (§5b rule 2 unresolved pairing)."""
    left_line = _p1_detail_row(520.0, anchors=_P1_LEFT_ANCHORS, line_no="24", name="Test Missile", slots={1: "(500)"})
    left_less = _p1_less_row(505.0, anchors=_P1_LEFT_ANCHORS, prefix="Less: Advance Procurement (PY)", slots={1: "(480)"})
    left_next = _p1_detail_row(490.0, anchors=_P1_LEFT_ANCHORS, line_no="25", name="Unrelated Line", slots={1: "10"})
    left_page = _p1_detail_page(
        side="left", rows=[left_line, left_less, left_next], ba_close_slots={1: "10"}, appr_close_slots={1: "10"},
    )
    right_row = _p1_detail_row(520.0, anchors=_P1_RIGHT_ANCHORS, line_no="24", name="Test Missile", slots={})
    right_page = _p1_detail_page(side="right", rows=[right_row], ba_close_slots={}, appr_close_slots={})
    left_summary = _p1_ba_summary_page(side="left", ba_slots={0: "10"}, appr_slots={0: "10"})
    right_summary = _p1_ba_summary_page(side="right", ba_slots={}, appr_slots={})
    pdf_bytes = _p1_pdf_words(left_page, right_page, left_summary, right_summary)
    with pytest.raises(live.DodBudgetParseRefused, match="resolving"):
        _parse_p1(pdf_bytes)


def test_p1_zero_numbered_line_partition_excludes_orphan_from_hermetic_totals() -> None:
    """§5b.1 ruling 2: a value-bearing additive row with NO numbered parent
    (an orphan, e.g. NSBDF-style unnumbered full-funding) is included in the
    parser's own document-wide typed-model gate but excluded from what is
    published and from the hermetic reconcile_line_totals input."""
    orphan = [(60.0, 520.0, "Subsequent Full Funding for FY 2024"), _p1_value_word(_P1_LEFT_ANCHORS, 1, "300", 520.0)]
    numbered = _p1_detail_row(505.0, anchors=_P1_LEFT_ANCHORS, line_no="2", name="Test Ship", slots={1: "700"})
    left_page = _p1_detail_page(side="left", rows=[orphan, numbered], ba_close_slots={1: "1,000"}, appr_close_slots={1: "1,000"})
    right_row = _p1_detail_row(520.0, anchors=_P1_RIGHT_ANCHORS, line_no="2", name="Test Ship", slots={})
    right_page = _p1_detail_page(side="right", rows=[right_row], ba_close_slots={}, appr_close_slots={})
    left_summary = _p1_ba_summary_page(side="left", ba_slots={0: "1,000"}, appr_slots={0: "1,000"})
    right_summary = _p1_ba_summary_page(side="right", ba_slots={}, appr_slots={})
    pdf_bytes = _p1_pdf_words(left_page, right_page, left_summary, right_summary)
    lines, totals = _parse_p1(pdf_bytes)
    assert len(lines) == 1
    assert lines[0]["native_identifier"]["value"] == "2"
    amounts = {a["semantic"]: a["amount_usd"] for a in lines[0]["amounts"]}
    assert amounts["historical_actual"] == 700_000.0  # only the numbered line's own value publishes
    # the totals entry fed to reconcile_line_totals is the ADJUSTED (700)
    # amount, not the raw printed 1,000 total -- reconcile_line_totals only
    # succeeded (no exception above) because of that adjustment.
    total_amounts = {a["semantic"]: a["amount_usd"] for a in totals[0]["amounts"]}
    assert total_amounts["historical_actual"] == 700_000.0


def test_p1_zero_numbered_line_partition_still_hard_gates_full_document_arithmetic() -> None:
    """The SAME orphan scenario, but the printed BA-close total does NOT
    match (numbered line + orphan) -- the parser's own typed-model gate
    (which INCLUDES the orphan) must still refuse."""
    orphan = [(60.0, 520.0, "Subsequent Full Funding for FY 2024"), _p1_value_word(_P1_LEFT_ANCHORS, 1, "300", 520.0)]
    numbered = _p1_detail_row(505.0, anchors=_P1_LEFT_ANCHORS, line_no="2", name="Test Ship", slots={1: "700"})
    # printed BA close omits the orphan's 300 entirely (says 700, not 1,000)
    left_page = _p1_detail_page(side="left", rows=[orphan, numbered], ba_close_slots={1: "700"}, appr_close_slots={1: "700"})
    right_row = _p1_detail_row(520.0, anchors=_P1_RIGHT_ANCHORS, line_no="2", name="Test Ship", slots={})
    right_page = _p1_detail_page(side="right", rows=[right_row], ba_close_slots={}, appr_close_slots={})
    left_summary = _p1_ba_summary_page(side="left", ba_slots={0: "700"}, appr_slots={0: "700"})
    right_summary = _p1_ba_summary_page(side="right", ba_slots={}, appr_slots={})
    pdf_bytes = _p1_pdf_words(left_page, right_page, left_summary, right_summary)
    with pytest.raises(live.DodBudgetParseRefused, match="typed-row-model closure"):
        _parse_p1(pdf_bytes)


def test_p1_page_pair_nomenclature_mismatch_refused() -> None:
    """The SAME numbered line must print the SAME (whitespace-normalized)
    Item Nomenclature on both the left and right page halves."""
    left_row = _p1_detail_row(520.0, anchors=_P1_LEFT_ANCHORS, line_no="10", name="Test Widget", slots={1: "1,000", 7: "1,000"})
    right_row = _p1_detail_row(520.0, anchors=_P1_RIGHT_ANCHORS, line_no="10", name="A Totally Different Widget", slots={0: "1,200", 4: "1,200"})
    left_page = _p1_detail_page(side="left", rows=[left_row], ba_close_slots={1: "1,000", 7: "1,000"}, appr_close_slots={1: "1,000", 7: "1,000"})
    right_page = _p1_detail_page(side="right", rows=[right_row], ba_close_slots={0: "1,200", 4: "1,200"}, appr_close_slots={0: "1,200", 4: "1,200"})
    left_summary = _p1_ba_summary_page(side="left", ba_slots={0: "1,000", 3: "1,000"}, appr_slots={0: "1,000", 3: "1,000"})
    right_summary = _p1_ba_summary_page(side="right", ba_slots={0: "1,200", 2: "1,200"}, appr_slots={0: "1,200", 2: "1,200"})
    pdf_bytes = _p1_pdf_words(left_page, right_page, left_summary, right_summary)
    with pytest.raises(live.DodBudgetParseRefused, match="nomenclature mismatch"):
        _parse_p1(pdf_bytes)


def test_p1_unclassified_numeric_row_refused() -> None:
    """A numeric-bearing row on a BA-Summary page matching NEITHER the
    "NN. <name>" BA-summary-row shape NOR the "Total <name>" shape is a row
    this parser cannot positively classify — refuses the whole document."""
    left_row = _p1_detail_row(520.0, anchors=_P1_LEFT_ANCHORS, line_no="10", name="Test Widget", slots={1: "1,000", 7: "1,000"})
    left_page = _p1_detail_page(side="left", rows=[left_row], ba_close_slots={1: "1,000", 7: "1,000"}, appr_close_slots={1: "1,000", 7: "1,000"})
    right_row = _p1_detail_row(520.0, anchors=_P1_RIGHT_ANCHORS, line_no="10", name="Test Widget", slots={0: "1,200", 4: "1,200"})
    right_page = _p1_detail_page(side="right", rows=[right_row], ba_close_slots={0: "1,200", 4: "1,200"}, appr_close_slots={0: "1,200", 4: "1,200"})
    left_summary = _p1_ba_summary_page(side="left", ba_slots={0: "1,000", 3: "1,000"}, appr_slots={0: "1,000", 3: "1,000"})
    junk = [(72.0, 520.0, "%%% Not A Real Row Shape")] + [_p1_summary_word(_P1_LEFT_SUMMARY_WORDS, 0, "99", 520.0)]
    left_summary = left_summary + junk
    right_summary = _p1_ba_summary_page(side="right", ba_slots={0: "1,200", 2: "1,200"}, appr_slots={0: "1,200", 2: "1,200"})
    pdf_bytes = _p1_pdf_words(left_page, right_page, left_summary, right_summary)
    with pytest.raises(live.DodBudgetParseRefused, match="unclassified numeric row"):
        _parse_p1(pdf_bytes)


def test_p1_missing_unit_marker_refused() -> None:
    pages = _p1_golden_pages()
    pages[0] = [w for w in pages[0] if w[2] != "(Dollars in Thousands)"]
    pdf_bytes = _p1_pdf_words(*pages)
    with pytest.raises(live.DodBudgetParseRefused, match="Dollars in Thousands"):
        _parse_p1(pdf_bytes)


def test_p1_fiscal_year_and_exhibit_mismatch_refused_through_parser() -> None:
    pdf_bytes = _p1_pdf_words(*_p1_golden_pages())
    with pytest.raises(ValueError, match="fiscal year"):
        _parse_p1(pdf_bytes, fiscal_year=2026)


# --- CLI: local-store end-to-end (idempotence, all-or-nothing) -----------


class _FixtureTransport:
    """Serves fixed synthetic P-1/R-1 bytes for both canary URLs."""

    def __init__(self, *, p1_bytes: bytes, r1_bytes: bytes):
        self._p1_bytes = p1_bytes
        self._r1_bytes = r1_bytes

    def get(self, url, **kwargs):
        body = self._p1_bytes if "p1.pdf" in url else self._r1_bytes
        return _FakeResponse(status_code=200, body=body, url=url)


def test_cli_local_run_writes_triad_and_is_idempotent(tmp_path: Path) -> None:
    p1_bytes = _p1_pdf_words(*_p1_golden_pages())
    r1_bytes = _r1_pdf(_r1_golden_page())
    store = LocalStore(tmp_path / "r2store")
    transport = _FixtureTransport(p1_bytes=p1_bytes, r1_bytes=r1_bytes)

    rc1 = live.run_dod_budget_acquisition(
        root=tmp_path, store=store, session=transport, observed_at="2026-08-24T15:00:00+00:00",
    )
    assert rc1 == 0
    data_dir = tmp_path / "data" / "government_revenue"
    lines_before = (data_dir / "dod_budget_line_snapshots.jsonl").read_bytes()
    receipts_before = (data_dir / "dod_budget_collection_receipts.jsonl").read_bytes()
    lines = [json.loads(l) for l in lines_before.decode().splitlines() if l.strip()]
    assert len(lines) == 2  # one P-1 line + one R-1 line

    rc2 = live.run_dod_budget_acquisition(
        root=tmp_path, store=store, session=transport, observed_at="2026-08-24T16:00:00+00:00",
    )
    assert rc2 == 0
    assert (data_dir / "dod_budget_line_snapshots.jsonl").read_bytes() == lines_before
    assert (data_dir / "dod_budget_collection_receipts.jsonl").read_bytes() == receipts_before


def test_cli_partial_failure_on_one_exhibit_writes_nothing(tmp_path: Path) -> None:
    """All-or-nothing: if R-1 refuses, the P-1 half is not written either,
    and any PRE-EXISTING triad is left byte-for-byte untouched."""
    p1_bytes = _p1_pdf_words(*_p1_golden_pages())
    broken_r1 = _r1_pdf([w for w in _r1_golden_page() if w[2] != "(Dollars in Thousands)"])
    store = LocalStore(tmp_path / "r2store")
    transport = _FixtureTransport(p1_bytes=p1_bytes, r1_bytes=broken_r1)

    rc = live.run_dod_budget_acquisition(root=tmp_path, store=store, session=transport)
    assert rc != 0
    data_dir = tmp_path / "data" / "government_revenue"
    assert not (data_dir / "dod_budget_line_snapshots.jsonl").exists()
    assert not (data_dir / "dod_budget_collection_receipts.jsonl").exists()
    assert not (data_dir / "dod_budget_projection_state.json").exists()
