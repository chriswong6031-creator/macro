"""research_vault.probe — deterministic facts MEASURED from a PDF (RV W1-A).

Everything in this module is computed from bytes we already hold at ingest time:
page count, content hash, text-layer density, and the PDF's own Info-dict
provenance. No LLM, no network, no judgment — a re-run on the same bytes returns
the same answer.

Why measured-not-claimed: the sidecar is written by an upstream engine outside
this repo, and its optional fields arrive empty in practice (``pages`` was null
for every one of the first 60 ingested documents even though the ingester was
holding the PDF). A fact we can compute locally must never depend on an upstream
promise.

Extraction ladder — each rung optional, none raising:
  1. ``hashlib``/``len`` over the bytes — always available.
  2. ``pypdf`` (SOFT dep, already in requirements for the download watermark) —
     page count + the whole Info dict in one parse.
  3. poppler ``pdfinfo`` (ships beside the ``pdftotext`` the ingester already
     requires) — page count + Creator/Producer/CreationDate/ModDate.
  4. all-unknown — every derived field stays None/'' and the caller carries on.

**Unknown is spelled None (or '' for strings), never 0 and never a guess** — a
null page count must not read as a zero-page document, and a missing text layer
must not read as an empty one.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile

log = logging.getLogger("research_vault.probe")

# A page with fewer than this many extracted characters is not a readable text
# layer — a scanned cover sheet or a chart-only deck lands here. Chosen so a
# sparse but real page (title + a few labels) stays "full": a typical research
# page runs 1500-4000 chars, a purely decorative one under 100.
THIN_CHARS_PER_PAGE = 200

# Absolute floor used when the page count is unknown (both probe rungs failed).
THIN_CHARS_ABSOLUTE = 500

# Cap on the retained page-1 text. The cover page is where the real title,
# author block, date and disclaimer live, so downstream extractors (author
# regex, topic classifier) read this instead of re-fetching the PDF from R2.
FIRST_PAGE_MAX_CHARS = 4_000

# pdftotext separates pages with a form feed.
_PAGE_BREAK = "\f"


# ---------------------------------------------------------------------------
# PDF date parsing
# ---------------------------------------------------------------------------

# PDF Info-dict dates: D:YYYYMMDDHHmmSSOHH'mm' (trailing parts all optional).
_PDF_DATE = re.compile(
    r"^D?:?"
    r"(?P<Y>\d{4})(?P<M>\d{2})?(?P<D>\d{2})?"
    r"(?P<h>\d{2})?(?P<m>\d{2})?(?P<s>\d{2})?"
    r"(?P<tz>[Zz+-]\d{2}'?\d{2}'?|[Zz])?"
)

# pdfinfo -isodates emits 2026-07-21T18:59:16+08 — a 2-digit offset ISO needs
# padding to +08:00 to be a valid RFC-3339 timestamp.
_SHORT_OFFSET = re.compile(r"([+-]\d{2})$")


def _pdf_date_to_iso(raw: str) -> str:
    """``D:20260721185916+08'00'`` → ``2026-07-21T18:59:16+08:00``.

    Returns '' for anything unparseable — a malformed date is a null, never a
    fabricated one. Already-ISO input (pdfinfo -isodates) passes through with a
    short offset padded. Never raises.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    # Already ISO-ish (pdfinfo -isodates).
    if re.match(r"^\d{4}-\d{2}-\d{2}T", s):
        return _SHORT_OFFSET.sub(r"\1:00", s)
    m = _PDF_DATE.match(s)
    if not m or not m.group("Y"):
        return ""
    g = m.groupdict()
    date = f"{g['Y']}-{g['M'] or '01'}-{g['D'] or '01'}"
    time = f"{g['h'] or '00'}:{g['m'] or '00'}:{g['s'] or '00'}"
    tz = (g["tz"] or "").replace("'", "")
    if tz in ("Z", "z"):
        tz = "+00:00"
    elif len(tz) == 5 and tz[0] in "+-":       # +0800
        tz = f"{tz[:3]}:{tz[3:]}"
    elif len(tz) == 3 and tz[0] in "+-":       # +08
        tz = f"{tz}:00"
    else:
        tz = ""
    return f"{date}T{time}{tz}"


# ---------------------------------------------------------------------------
# rung 2 — pypdf
# ---------------------------------------------------------------------------

def _probe_pypdf(pdf_bytes: bytes) -> dict:
    """Page count + Info dict via pypdf. Returns {} when unavailable.

    Each read is individually guarded: a PDF whose page tree parses but whose
    metadata does not (or vice versa) still contributes what it can.
    """
    out: dict = {}
    try:
        import io  # noqa: PLC0415 — local to the soft-dep path

        from pypdf import PdfReader  # noqa: PLC0415 — SOFT dep, imported lazily
    except Exception:  # noqa: BLE001 — pypdf absent: fall through to pdfinfo
        return out
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:  # noqa: BLE001 — unparseable: next rung
        log.debug("research_vault probe: pypdf open failed (%s)", exc)
        return out
    try:
        out["encrypted"] = bool(reader.is_encrypted)
    except Exception:  # noqa: BLE001
        pass
    try:
        out["pages"] = len(reader.pages)
    except Exception as exc:  # noqa: BLE001
        log.debug("research_vault probe: pypdf page count failed (%s)", exc)
    try:
        meta = dict(reader.metadata or {})
    except Exception:  # noqa: BLE001
        meta = {}
    if meta:
        out["pdf_creator"] = str(meta.get("/Creator") or "").strip()
        out["pdf_producer"] = str(meta.get("/Producer") or "").strip()
        out["pdf_created_at"] = _pdf_date_to_iso(str(meta.get("/CreationDate") or ""))
        out["pdf_modified_at"] = _pdf_date_to_iso(str(meta.get("/ModDate") or ""))
    return out


# ---------------------------------------------------------------------------
# rung 3 — poppler pdfinfo
# ---------------------------------------------------------------------------

def _pdfinfo_available() -> bool:
    return shutil.which("pdfinfo") is not None


def _run_pdfinfo(tmp_path: str) -> str | None:
    """``pdfinfo -isodates`` output, retrying without the flag on old poppler.

    Returns None when pdfinfo cannot be run at all. On the retry path the dates
    are locale-formatted and deliberately DROPPED rather than guessed.
    """
    for args in (["-isodates"], []):
        try:
            r = subprocess.run(["pdfinfo", *args, tmp_path],
                               capture_output=True, timeout=15)
        except Exception as exc:  # noqa: BLE001 — timeout / exec failure
            log.debug("research_vault probe: pdfinfo failed (%s)", exc)
            return None
        if r.returncode == 0:
            text = r.stdout.decode("utf-8", errors="replace")
            return text if args else _strip_dates(text)
    return None


def _strip_dates(text: str) -> str:
    """Drop date lines from non-ISO pdfinfo output (locale format → unparseable)."""
    keep = [ln for ln in text.splitlines()
            if not ln.startswith(("CreationDate:", "ModDate:"))]
    return "\n".join(keep)


def _probe_pdfinfo(pdf_bytes: bytes) -> dict:
    """Page count + provenance via poppler ``pdfinfo``. Returns {} on failure."""
    if not _pdfinfo_available():
        return {}
    out: dict = {}
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(pdf_bytes)
            text = _run_pdfinfo(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception as exc:  # noqa: BLE001 — tempfile failure: unknown, not fatal
        log.debug("research_vault probe: pdfinfo tempfile failed (%s)", exc)
        return {}
    if not text:
        return {}
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, _, val = line.partition(":")
        if _:
            fields[key.strip()] = val.strip()
    if fields.get("Pages", "").isdigit():
        out["pages"] = int(fields["Pages"])
    if "Encrypted" in fields:
        out["encrypted"] = not fields["Encrypted"].lower().startswith("no")
    out["pdf_creator"] = fields.get("Creator", "")
    out["pdf_producer"] = fields.get("Producer", "")
    out["pdf_created_at"] = _pdf_date_to_iso(fields.get("CreationDate", ""))
    out["pdf_modified_at"] = _pdf_date_to_iso(fields.get("ModDate", ""))
    return out


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def probe(pdf_bytes: bytes) -> dict:
    """Deterministic facts about ``pdf_bytes``. Never raises.

    Always populated (computed over the bytes themselves)::

        content_sha256  hex digest — exact-duplicate evidence
        byte_size       int

    Best-effort (None / '' when every rung failed)::

        pages           int | None
        encrypted       bool | None
        pdf_creator     str   ('' unknown)
        pdf_producer    str
        pdf_created_at  str   (ISO-8601, '' unknown)
        pdf_modified_at str

    ``content_sha256`` is EVIDENCE, not a gate: the caller reports collisions but
    must not skip on one — the same bytes legitimately re-arrive with a corrected
    sidecar, and skipping would freeze the bad metadata in place.
    """
    facts: dict = {
        "content_sha256": "",
        "byte_size": 0,
        "pages": None,
        "encrypted": None,
        "pdf_creator": "",
        "pdf_producer": "",
        "pdf_created_at": "",
        "pdf_modified_at": "",
    }
    if not pdf_bytes:
        return facts
    try:
        facts["content_sha256"] = hashlib.sha256(pdf_bytes).hexdigest()
        facts["byte_size"] = len(pdf_bytes)
    except Exception as exc:  # noqa: BLE001 — defensive; hashlib does not fail
        log.debug("research_vault probe: hash failed (%s)", exc)

    found = _probe_pypdf(pdf_bytes)
    if found.get("pages") is None:
        # pypdf absent or its page tree unreadable — try poppler for the rest too,
        # then let pypdf's values win where it did produce one.
        fallback = _probe_pdfinfo(pdf_bytes)
        fallback.update({k: v for k, v in found.items() if v not in (None, "")})
        found = fallback

    for key, val in found.items():
        if key in facts and val not in (None, ""):
            facts[key] = val
    return facts


def text_facts(body_text: str | None, pages: int | None = None) -> dict:
    """Classify the extracted text layer. Never raises.

    Returns::

        char_count  int | None   (None only when extraction was UNAVAILABLE)
        word_count  int | None
        text_layer  'full' | 'thin' | 'none' | 'unavailable'

    The four states are distinct on purpose:
      - ``unavailable`` — ``pdftotext`` is missing or crashed. We know nothing
        about the document; this is a TOOLING fault to fix on the host.
      - ``none``        — the extractor ran and found no text. The PDF is
        image-only, so body search is silently blind to it. A DOCUMENT fault.
      - ``thin``        — text present but below a readable density (scanned with
        a text cover sheet, or a chart-only deck).
      - ``full``        — a genuine text layer.

    Collapsing ``unavailable`` into ``none`` (which ``extract_pdf_text() or ""``
    does at the call site) would hide a broken host behind a plausible-looking
    document property.
    """
    if body_text is None:
        return {"char_count": None, "word_count": None, "text_layer": "unavailable"}
    text = body_text or ""
    chars = len(text)
    words = len(text.split())
    if chars == 0:
        layer = "none"
    elif pages and pages > 0:
        layer = "thin" if (chars / pages) < THIN_CHARS_PER_PAGE else "full"
    else:
        layer = "thin" if chars < THIN_CHARS_ABSOLUTE else "full"
    return {"char_count": chars, "word_count": words, "text_layer": layer}


def first_page(body_text: str | None, limit: int = FIRST_PAGE_MAX_CHARS) -> str:
    """Page-1 text from ``pdftotext`` output (form-feed delimited), capped.

    Free — reuses the extraction the ingester already ran, no second subprocess.
    Returns '' when there is no text. Never raises.
    """
    if not body_text:
        return ""
    head = body_text.split(_PAGE_BREAK, 1)[0]
    return head[:limit]
