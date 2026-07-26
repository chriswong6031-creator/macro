"""research_vault.sidecar — parse + normalize a sidecar to the v1 contract.

Implements the ``research_vault.sidecar.v1`` contract (masterplan §5). The
ingester is DEFENSIVE: every field except the PDF itself has a fallback, and a
sidecar that fails JSON parse is still ingested with all-fallback metadata and
flagged ``needs_metadata=True`` — a document is NEVER dropped.

Pure + stdlib-only → unit-testable in isolation. No I/O here; callers pass in the
already-loaded sidecar bytes/dict plus the fallbacks they were able to recover
(PDF-embedded title, R2 upload time, source filename).
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

SCHEMA = "research_vault.sidecar.v1"

# side ∈ buy | sell | independent; default sell (§5).
_SIDES = {"buy", "sell", "independent"}
_DEFAULT_SIDE = "sell"

_UNKNOWN_INSTITUTION = "Unknown"

# summary bullets: 3–8 short bullets is the contract; we clamp to a sane ceiling
# but never fabricate — an empty/short list stays as-is (row shows "Summary pending").
_MAX_SUMMARY_POINTS = 8


# ---------------------------------------------------------------------------
# slug / id derivation
# ---------------------------------------------------------------------------

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slug(text: str, max_len: int = 60) -> str:
    """Lowercase ASCII slug: strip accents, collapse non-alnum runs to '-'.

    Empty / all-punctuation input → ''. Never raises.
    """
    if not text:
        return ""
    # Fold accents to ASCII (é -> e) so slugs are stable + url-safe.
    norm = unicodedata.normalize("NFKD", str(text))
    norm = norm.encode("ascii", "ignore").decode("ascii")
    s = _SLUG_STRIP.sub("-", norm.lower()).strip("-")
    if max_len and len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s


def _date_part(published_at: str) -> str:
    """YYYY-MM-DD prefix of an ISO-8601 timestamp; '' when unparseable."""
    if not published_at:
        return ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(published_at))
    return m.group(1) if m else ""


def derive_id(institution: str, published_at: str, title: str) -> str:
    """Derive a stable id ``slug(inst)-YYYY-MM-DD-slug(title)[:40]`` (§5).

    Missing parts degrade gracefully: an absent institution → 'unknown', an
    unparseable date → 'undated', an empty title → 'untitled'. Always returns a
    non-empty, url-safe id.
    """
    inst = slug(institution) or "unknown"
    date = _date_part(published_at) or "undated"
    ttl = slug(title, max_len=40) or "untitled"
    return f"{inst}-{date}-{ttl}"


# ---------------------------------------------------------------------------
# field coercion helpers
# ---------------------------------------------------------------------------

def _as_str(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _as_str_list(v: Any) -> list[str]:
    """Coerce to a list of non-empty trimmed strings (drop non-str members)."""
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for item in v:
        s = item.strip() if isinstance(item, str) else ""
        if s:
            out.append(s)
    return out


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "yes"}
    return bool(v) if isinstance(v, (int, float)) else False


def _as_int(v: Any) -> int | None:
    if isinstance(v, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


# ---------------------------------------------------------------------------
# parse + normalize
# ---------------------------------------------------------------------------

def parse_json(raw: bytes | str | None) -> tuple[dict, bool]:
    """Load sidecar JSON. Returns ``(dict, bad_json)``.

    ``bad_json`` is True when the bytes were present but did not parse to a dict
    (→ the caller flags needs_metadata + uses all fallbacks). Absent sidecar
    (raw is None/empty) → ``({}, False)`` (not an error — just no metadata yet).
    """
    if raw is None:
        return {}, False
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8")
        except Exception:  # noqa: BLE001 — undecodable bytes == bad json
            return {}, True
    if not str(raw).strip():
        return {}, False
    try:
        obj = json.loads(raw)
    except Exception:  # noqa: BLE001 — malformed JSON: fall back, never drop
        return {}, True
    if not isinstance(obj, dict):
        return {}, True
    return obj, False


def _looks_truncated(title: str) -> bool:
    """True when a title has more '(' than ')' — the fingerprint of MarketDesk
    dropping a Reuters ".EX)" exchange suffix (e.g. "Alcon Inc. (ALCC")."""
    return title.count("(") > title.count(")")


def heal_truncated_title(title: str) -> str:
    """Cut the dangling "(FRAGMENT" tail off a MarketDesk-truncated title.

    This is a DISPLAY-tier repair, deliberately not applied by :func:`normalize`.
    The lossless repair is the PDF-/Title/ recovery in the title ladder below, and
    it is triggered by :func:`_looks_truncated` — so the stored record must keep
    its unbalanced-paren fingerprint or a later re-ingest carrying a good PDF
    /Title could no longer repair it. Callers project, they do not rewrite.

    Cutting at the first UNMATCHED "(" leaves a clean, balanced name:

        "Alcon Inc. (ALCC"    -> "Alcon Inc."
        "Repsol (REP"         -> "Repsol"
        "Carrefour (CARR(1)"  -> "Carrefour"   (inner "(1)" is a dedupe artifact)

    Lossy by construction — the exchange suffix is not recoverable from the string
    — but an unbalanced paren in <title>/og:title is the worse of the two on pages
    whose whole purpose is exact-title search match. A balanced title is returned
    untouched, so a good title is never rewritten, and a title that is *only* a
    fragment is returned as-is rather than blanked.
    """
    if not isinstance(title, str) or not _looks_truncated(title):
        return title
    depth = 0
    cut = None
    for i, ch in enumerate(title):
        if ch == "(":
            if depth == 0:
                cut = i  # outermost "(" of this group — the dangling candidate
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
            if depth == 0:
                cut = None  # the group closed; it was not the unmatched one
    if cut is None:
        return title
    return title[:cut].strip(" \t-–—:,;") or title


def normalize(
    sidecar: dict | None,
    *,
    bad_json: bool = False,
    fallback_title_pdf: str = "",
    fallback_title_filename: str = "",
    fallback_institution: str = "",
    fallback_published_at: str = "",
    fallback_source_filename: str = "",
) -> dict:
    """Normalize a (possibly empty/partial) sidecar dict to the v1 item shape.

    Fallback ladders (§5):
      - title: sidecar.title → PDF-embedded title → filename → 'Untitled research'.
      - institution: sidecar.institution → caller fallback → 'Unknown' (+needs_metadata).
      - published_at: sidecar.published_at → R2 upload time (caller) → '' (no crash).
      - summary_points: sidecar list → [] ("Summary pending").
      - side: sidecar.side (validated) → 'sell'.
      - id: sidecar.id → derived slug id.

    ``needs_metadata`` is set when JSON was bad OR the institution had to fall
    back to 'Unknown' OR the title had to fall back to the filename/placeholder.
    Unknown sidecar fields are ignored (not preserved on the public item).
    Never raises.
    """
    sc = sidecar if isinstance(sidecar, dict) else {}
    needs_metadata = bool(bad_json)

    # --- title ladder ------------------------------------------------------
    title = _as_str(sc.get("title"))
    # Recover a MarketDesk-truncated title from the PDF's embedded /Title. MarketDesk
    # drops the Reuters ".EX)" exchange suffix off its own name, so "Alcon Inc. (ALCC.US)"
    # arrives as "Alcon Inc. (ALCC" (the tell is an unbalanced "("). When that happens and
    # the PDF carries a fuller, balanced /Title, prefer it — never regressing a good title.
    if title and _looks_truncated(title):
        pdf_title = _as_str(fallback_title_pdf)
        if pdf_title and not _looks_truncated(pdf_title) and len(pdf_title) >= len(title):
            title = pdf_title
    if not title:
        title = _as_str(fallback_title_pdf)
        if title:
            needs_metadata = True
    if not title:
        title = _as_str(fallback_title_filename)
        if title:
            needs_metadata = True
    if not title:
        title = "Untitled research"
        needs_metadata = True

    # --- institution facet -------------------------------------------------
    institution = _as_str(sc.get("institution"))
    if not institution:
        institution = _as_str(fallback_institution)
    if not institution:
        institution = _UNKNOWN_INSTITUTION
        needs_metadata = True

    # --- side --------------------------------------------------------------
    side = _as_str(sc.get("side")).lower()
    if side not in _SIDES:
        side = _DEFAULT_SIDE

    # --- published_at ------------------------------------------------------
    published_at = _as_str(sc.get("published_at")) or _as_str(fallback_published_at)

    # --- summary / tags / tickers -----------------------------------------
    summary_points = _as_str_list(sc.get("summary_points"))[:_MAX_SUMMARY_POINTS]
    tags = _as_str_list(sc.get("tags"))
    tickers = [t.upper() for t in _as_str_list(sc.get("tickers"))]

    # --- misc optional -----------------------------------------------------
    desk = _as_str(sc.get("desk"))
    pages = _as_int(sc.get("pages"))
    language = _as_str(sc.get("language")) or "en"
    source_filename = _as_str(sc.get("source_filename")) or _as_str(fallback_source_filename)
    top_pick = _as_bool(sc.get("top_pick"))

    # --- id ----------------------------------------------------------------
    item_id = slug(_as_str(sc.get("id")), max_len=120)
    if not item_id:
        item_id = derive_id(institution, published_at, title)

    return {
        "id": item_id,
        "title": title,
        "institution": institution,
        "side": side,
        "desk": desk,
        "published_at": published_at,
        "summary_points": summary_points,
        "tags": tags,
        "tickers": tickers,
        "top_pick": top_pick,
        "pages": pages,
        "language": language,
        "source_filename": source_filename,
        "needs_metadata": needs_metadata,
    }


def from_bytes(
    raw: bytes | str | None,
    **fallbacks: str,
) -> dict:
    """Convenience: parse raw sidecar bytes then normalize with fallbacks.

    Accepts the same ``fallback_*`` kwargs as :func:`normalize`. Never raises;
    bad JSON → all-fallback item flagged ``needs_metadata=True``.
    """
    sc, bad_json = parse_json(raw)
    return normalize(sc, bad_json=bad_json, **fallbacks)
