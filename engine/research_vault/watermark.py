"""research_vault.watermark — per-user footer stamp on downloaded PDFs (RV W2).

``stamp(pdf_bytes, text)`` overlays a faint one-line footer (``text``) on every
page and returns the new PDF bytes. The footer carries the buyer's identity +
date + a not-for-redistribution notice, so a leaked copy is traceable to the
account that downloaded it (masterplan §2 traceability; §9 download route).

HARD RULE — never raise, never block a paid download:
    A watermark is a nice-to-have on a download the user has already paid for and
    passed the quota gate for. If reportlab or pypdf is absent, or ANYTHING goes
    wrong building/merging the overlay, we return the ORIGINAL ``pdf_bytes``
    unchanged and log a debug note. A failed stamp must degrade to an un-stamped
    (but still access-controlled + attachment-dispositioned) download, never a
    500 or a withheld file. The red-team probes exactly this: libs-present and
    libs-absent must BOTH return a body.

Both libs are declared as SOFT deps in requirements (commented). This module is
the only place they are imported, and always lazily inside ``try``.
"""
from __future__ import annotations

import io
import logging

log = logging.getLogger("research_vault.watermark")

# Footer typography — deliberately faint + small so it doesn't obscure content.
_FONT = "Helvetica"
_FONT_SIZE = 7
_MARGIN_PT = 18  # distance from the bottom-left corner, in points
_GREY = 0.55     # 0=black .. 1=white; a light grey footer


def _make_overlay_page(text: str, width: float, height: float):
    """Build a single-page reportlab overlay canvas sized to (width, height).

    Returns a ``pypdf.PageObject`` for the overlay, or raises on any failure
    (the caller catches and degrades). Kept per-size because PDF pages in one
    document can have different media boxes.
    """
    from reportlab.pdfgen import canvas  # noqa: PLC0415 — soft dep, lazy

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setFont(_FONT, _FONT_SIZE)
    c.setFillGray(_GREY)
    # Draw near the bottom-left; a long line simply clips at the right margin.
    c.drawString(_MARGIN_PT, _MARGIN_PT, text)
    c.save()
    buf.seek(0)

    from pypdf import PdfReader  # noqa: PLC0415 — soft dep, lazy

    return PdfReader(buf).pages[0]


def stamp(pdf_bytes: bytes, text: str) -> bytes:
    """Overlay ``text`` as a faint footer on every page of ``pdf_bytes``.

    Returns the watermarked PDF bytes, or the ORIGINAL ``pdf_bytes`` unchanged if
    pypdf/reportlab are absent or on ANY error. Never raises.
    """
    if not pdf_bytes:
        return pdf_bytes
    text = (text or "").strip()
    if not text:
        return pdf_bytes

    try:
        from pypdf import PdfReader, PdfWriter  # noqa: PLC0415 — soft dep, lazy

        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()

        # Cache overlays by (rounded w,h) so a many-page doc builds each size once.
        overlay_cache: dict[tuple[int, int], object] = {}

        for page in reader.pages:
            try:
                w = float(page.mediabox.width)
                h = float(page.mediabox.height)
                key = (round(w), round(h))
                ov = overlay_cache.get(key)
                if ov is None:
                    ov = _make_overlay_page(text, w, h)
                    overlay_cache[key] = ov
                page.merge_page(ov)
            except Exception as exc:  # noqa: BLE001 — one bad page: keep it un-stamped
                log.debug("research_vault watermark: page stamp skipped (%s)", exc)
            writer.add_page(page)

        out = io.BytesIO()
        writer.write(out)
        result = out.getvalue()
        # Defensive: an empty writer output is worse than the original — fall back.
        return result or pdf_bytes
    except Exception as exc:  # noqa: BLE001 — lib absent / parse error: degrade
        log.debug("research_vault watermark: unavailable, returning original (%s)", exc)
        return pdf_bytes
