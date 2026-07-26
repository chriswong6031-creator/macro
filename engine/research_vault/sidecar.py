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


# ---------------------------------------------------------------------------
# filename-shaped title repair
# ---------------------------------------------------------------------------
# The upstream MarketDesk uploader supplies ``sidecar.title`` for every document,
# so our own filename fallback (below) almost never fires — but for some sources
# the title IT supplies is itself a de-slugified source filename:
#
#   "2026 07 24 Pmi Fall Seven Times Get Up Eight en"   (TS Lombard)
#   "Blog en 1663820 1"                                 (UBS: lang + doc no. + dup)
#   "260723 ECB slightly hawkish hold all eyes..."      (yymmdd prefix)
#
# Those strings become the <title>/<h1>/JSON-LD headline of a public /research/
# SEO page, which is the whole point of the page. We can't fix the uploader from
# this repo, so we repair the shape here (ingest, for every new document) and at
# render (scripts/build_research_pages.py, so already-catalogued rows heal too).
#
# The bar is DO NO HARM: every rule below fires only on an unambiguous filename
# artefact, and a title that trips nothing is returned byte-identical.

# Trailing language codes emitted by document-management exports.
_FILE_LANG = {"en", "zh", "cn", "de", "fr", "it", "es", "ja", "jp", "pt", "ru", "kr"}

# Uppercased only inside a repaired title (a de-slugified stem loses its casing).
# Deliberately excludes words that are also ordinary English ("us", "it", "in"…).
_ACRONYMS = {
    "pmi", "cpi", "ppi", "gdp", "ecb", "boj", "boe", "fomc", "fx", "eps", "etf",
    "ipo", "opec", "ai", "eu", "em", "dm", "oecd", "nato", "sarb", "rba", "rbi",
    "pboc", "ubs", "usd", "eur", "jpy", "cny", "gbp", "nav", "ytd", "reit",
    "esg", "qe", "qt", "hy", "ig",
}

# Separator punctuation trimmed off a repaired edge. '.' is NOT in this set:
# "Alcon Inc. (ALCC" must repair to "Alcon Inc.", not "Alcon Inc".
_EDGE_TRIM = " ,;:-–—_"


def _is_md(mm: int, dd: int) -> bool:
    return 1 <= mm <= 12 and 1 <= dd <= 31


def _strip_lead_date(t: str) -> tuple[str, bool]:
    """Drop a leading filename date stamp ('2026 07 24 ', '260723 ', '26-07-24 ').

    Two-digit years are accepted only in 20–40 so a leading A-share code like
    "600519 Kweichow Moutai" is never mistaken for a 60-05-19 date stamp.
    """
    for pat, four_digit_year in (
        (r"^((?:19|20)\d{2})[ _.-](\d{2})[ _.-](\d{2})[ _.-]+(?=\S)", True),
        (r"^(\d{2})[ _.-](\d{2})[ _.-](\d{2})[ _.-]+(?=\S)", False),
        (r"^((?:19|20)\d{2})(\d{2})(\d{2})[ _.-]+(?=\S)", True),
        (r"^(\d{2})(\d{2})(\d{2})[ _.-]+(?=\S)", False),
    ):
        m = re.match(pat, t)
        if m and _is_md(int(m.group(2)), int(m.group(3))) \
                and (four_digit_year or 20 <= int(m.group(1)) <= 40):
            return t[m.end():], True
    return t, False


def _strip_file_tail(t: str) -> tuple[str, bool]:
    """Drop a trailing export tail: language code, document number, date, dup counter.

    Pops tokens right-to-left but only COMMITS when a strong marker (language
    code, 5+ digit document number, or a spaced YYYY MM DD triple) was seen —
    so a bare trailing number is never eaten. A trailing year survives too:
    "Outlook 2026" keeps its year because 2026 alone is no marker.
    """
    toks = t.split()
    i, strong = len(toks), False
    while i > 0:
        if (i >= 3 and re.fullmatch(r"(?:19|20)\d{2}", toks[i - 3])
                and re.fullmatch(r"\d{2}", toks[i - 2])
                and re.fullmatch(r"\d{2}", toks[i - 1])
                and _is_md(int(toks[i - 2]), int(toks[i - 1]))):
            i -= 3
            strong = True
            continue
        w = toks[i - 1]
        if w.lower() in _FILE_LANG or re.fullmatch(r"\d{5,}", w):
            i -= 1
            strong = True
            continue
        if re.fullmatch(r"\d{1,2}", w):     # dup counter / stray date piece
            i -= 1
            continue
        break
    return (" ".join(toks[:i]), True) if strong and i else (t, False)


def _strip_dup_marker(t: str) -> tuple[str, bool]:
    """Drop a browser duplicate-download marker: 'Report (1)' / 'Report(2)'."""
    m = re.search(r"\s*\(\d{1,2}\)$", t)
    return (t[:m.start()], True) if m else (t, False)


def _close_dangling_paren(t: str) -> tuple[str, bool]:
    """CLOSE a truncated trailing '(FRAGMENT' — "Repsol (REP" -> "Repsol (REP)".

    Only for the unbalanced case :func:`_looks_truncated` detects, and only when
    the PDF /Title recovery in normalize() could not supply a fuller title.

    Closing beats dropping on both axes that matter here: the ticker root is real
    and is exactly what an exact-title search matches on (the exchange suffix is
    unknowable and must never be invented), and closing leaves the URL slug byte
    identical because slug() strips non-alphanumerics — so this repair alone can
    never orphan an already-indexed /research/ page. A fragment with no content
    at all ("Foo (") is dropped instead, since there is nothing to close around.
    """
    if not _looks_truncated(t):
        return t, False
    cut = t.rfind("(")
    if t[cut + 1:].strip():
        return t + ")", True
    return (t[:cut].rstrip(_EDGE_TRIM) or t), bool(t[:cut].strip())


def repair_title(title: str) -> tuple[str, bool]:
    """Repair a de-slugified-filename title. Returns ``(title, was_repaired)``.

    A title that carries no filename artefact is returned unchanged with
    ``False`` — callers use that flag to decide whether the document still needs
    real metadata. Idempotent: repairing a repaired title is a no-op. Pure; never
    raises.
    """
    original = " ".join(str(title or "").split())
    if not original:
        return "", False

    out, repaired = original, False
    for step in (_strip_dup_marker, _close_dangling_paren,
                 _strip_lead_date, _strip_file_tail):
        candidate, hit = step(out)
        candidate = candidate.strip(_EDGE_TRIM)
        if hit and candidate:               # never repair a title down to nothing
            out, repaired = candidate, True

    # An all-lowercase multi-word title is a raw filename stem — no institution
    # writes one. Sentence-case it rather than leaving an <h1> starting lowercase.
    if not repaired and len(out.split()) >= 3 and not any(c.isupper() for c in out):
        repaired = True

    if not repaired:
        return original, False

    out = re.sub(r"\b[A-Za-z]{2,5}\b",
                 lambda m: m.group(0).upper() if m.group(0).lower() in _ACRONYMS
                 else m.group(0), out)
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return out, True


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
    # Whatever rung supplied it, the title may still BE a de-slugified filename
    # (the upstream uploader does this for some sources). Repair the shape, and
    # flag the doc: a filename-shaped title means real metadata never arrived.
    title, title_repaired = repair_title(title)
    needs_metadata = needs_metadata or title_repaired

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
