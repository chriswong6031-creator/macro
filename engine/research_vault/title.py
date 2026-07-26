"""research_vault.title — recover a report's REAL title from a PDF FILENAME one.

Some upstream desks hand us a sidecar whose ``title`` is just the source PDF's
filename, prettified: ``2026_07_24_Rearming_Britains_Supply_Side_en.pdf`` arrives
as ``"2026 07 24 Rearming Britain's Supply Side en"``. That title is a *valid*
sidecar field — ``needs_metadata`` stays False — so the ingest ladder in
``sidecar.normalize`` has nothing to fall back FROM; the bad title is simply
believed. It then flows to ``templates/research_report.html.j2`` as the
``<title>``/``<h1>``/``og:title`` of the report's SEO landing page, which is the
one thing those pages exist to get right: someone Googling the exact report title
must land on us, and a prettified filename matches nothing anyone ever types.

So this module adds a rung to the ladder that distrusts a *shape* rather than an
absence — the same move ``sidecar._looks_truncated`` already makes for MarketDesk's
dropped ``.EX)`` suffix:

  1. :func:`clean` strips filename furniture (leading date stamps, trailing
     language tokens + document ids, ``(1)`` duplicate-download markers). A title
     that cleans to itself was never filename-derived — that is exactly what
     :func:`looks_filename_derived` reports, so detector and repair can never
     drift apart.
  2. :func:`recover` looks the cleaned title up in the report's own first page
     (the body text ingest already extracts with ``pdftotext``) and returns the
     properly punctuated, properly cased headline the PDF prints.

Recovery is ANCHORED, never generative: it only ever returns a span of a line that
starts with the cleaned title's own words, in order. It cannot invent a headline —
the worst it can do is return the words we already had. Every gate below fails
CLOSED to the cleaned title, which is still strictly better than the filename.

Pure + stdlib-only (no I/O, no PDF library) so both callers share one algorithm:
``ingest._ingest_one`` for new documents, and ``ingest._repair_titles`` for the
ones already in the catalog — which is the only way a fix reaches them, since
ingest skips every PDF that already has a receipt.
"""
from __future__ import annotations

import re

# Bare ISO-639-1 tokens desks append to filenames — matched CASE-SENSITIVELY and
# only in the trailing run. Both restrictions carry weight: "IT", "HK" and "NO"
# are ordinary title words that collide with language codes, and a filename slug
# writes its language lowercase ("…_supply_side_en.pdf") while a title writes
# those words in caps. A desk that ships "_EN_" simply keeps its suffix — the
# safe way for this to be wrong.
_LANG = {"en", "de", "fr", "it", "es", "pt", "nl", "sv", "da", "no", "fi",
         "pl", "ru", "tr", "zh", "cn", "tw", "jp", "ja", "ko", "hk"}

# A leading date stamp: "2026 07 24 …", "26 07 24 …", "260723 …", "20260724 …".
_LEAD_DATE_RE = re.compile(r"^\s*(?:\d{4}|\d{2})[\s._-]+\d{1,2}[\s._-]+\d{1,2}(?=[\s._-])[\s._-]+")
_LEAD_COMPACT_RE = re.compile(r"^\s*\d{6}(?:\d{2})?(?=[\s._-])[\s._-]+")

# Chrome, Safari & co. mark a re-download as "(1)" — with or without a space.
_DUP_RE = re.compile(r"\s*\((\d{1,2})\)\s*$")

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_SPLIT_RE = re.compile(r"[\s._-]+")

# Recovery gates.
_MIN_ANCHOR_TOKENS = 3      # 1-2 words anchor nothing — keep the cleaned title
_MIN_TITLE_CHARS = 8
_MAX_TITLE_CHARS = 200
_MAX_CANDIDATES = 80        # the headline is at the top of page 1 or nowhere
_MAX_BRACKET_REACH = 40     # chars we will scan forward to balance a "("


def _tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")]


def _is_year(tok: str) -> bool:
    return len(tok) == 4 and tok.isdigit() and 1900 <= int(tok) <= 2099


def _is_doc_id(tok: str) -> bool:
    """A desk's internal document number — 5+ digits, or 4 digits that are no year."""
    return tok.isdigit() and (len(tok) >= 5 or (len(tok) == 4 and not _is_year(tok)))


def _strip_trailing_run(text: str) -> str:
    """Peel a trailing "… en 1663849 1" / "… 2026 07 24 5381087" run off ``text``.

    Tokens are peeled from the right while each is a language token or a bare
    number, and the peel is COMMITTED only on positive evidence — a language
    token or a document id somewhere in what was peeled. Without that floor,
    "US Econ Notes July 24" would lose its "24" and "…AI Strategy July 2026" its
    year; with it, both are left alone because a lone small number or a lone year
    is never enough to call a tail furniture.
    """
    toks = [t for t in _SPLIT_RE.split(text) if t]
    cut = len(toks)
    evidence = False
    while cut > 0:
        tok = toks[cut - 1]
        if tok in _LANG:                  # case-sensitive: "en" yes, "IT"/"HK" no
            evidence = True
        elif tok.isdigit():
            evidence = evidence or _is_doc_id(tok)
        else:
            break
        cut -= 1
    if not evidence or cut == 0:
        return text
    # Cut the ORIGINAL string (not " ".join(toks)) so the kept part stays verbatim.
    kept = 0
    for m in list(_SPLIT_RE.finditer(text)):
        kept += 1
        if kept == cut:
            return text[: m.start()]
    return text


def clean(title: str) -> str:
    """Strip filename furniture from ``title``; return it unchanged when there is none.

    Only LEADING date stamps and TRAILING language/id runs are touched, so a date
    or number inside a real title ("China 2026 Outlook", "Recap 7 24 26") survives
    verbatim. Never raises; a title that cleans away to nothing returns ''.
    """
    t = (title or "").strip()
    if not t:
        return ""

    prev = None
    while prev != t:                      # dates and "(1)" can stack
        prev = t
        t = _LEAD_DATE_RE.sub("", t, count=1)
        t = _LEAD_COMPACT_RE.sub("", t, count=1)
        t = _DUP_RE.sub("", t, count=1)
        t = t.strip()

    t = _strip_trailing_run(t)
    return t.strip(" -_·|,")


def looks_filename_derived(title: str) -> bool:
    """True when ``title`` carries filename furniture (i.e. :func:`clean` changes it)."""
    t = (title or "").strip()
    return bool(t) and clean(t) != t


def _first_page(body_text: str) -> str:
    """Page 1 of pdftotext output (form-feed separated), or the leading text."""
    body = (body_text or "").replace("\r\n", "\n")
    return body.split("\f")[0] if "\f" in body else body[:6000]


def _candidates(body_text: str) -> list[str]:
    """Ordered headline candidates from page 1 — one per non-empty line.

    Blank-line-joined paragraphs are accepted too (a caller may pass the cleaned
    first-pages excerpt instead of raw pdftotext, where the headline and the
    byline under it have already collapsed onto one line). The trailing-span trim
    in :func:`recover` removes that byline either way.
    """
    out: list[str] = []
    for raw in _first_page(body_text).split("\n"):
        line = " ".join(raw.split())
        if line:
            out.append(line)
        if len(out) >= _MAX_CANDIDATES:
            break
    return out


def _span(anchor: list[str], line: str) -> str:
    """The span of ``line`` covering ``anchor``'s tokens in order, or ''.

    The line must START with the anchor (no unmatched leading tokens): a headline
    begins with its own words, whereas a body sentence that happens to contain
    them does not. That single rule is what keeps recovery from wandering into
    prose. The span runs to the END of the last anchor token, which is how the
    analyst byline printed after the headline gets dropped.
    """
    marks = list(_TOKEN_RE.finditer(line))
    if len(marks) < len(anchor):
        return ""
    end = 0
    for i, m in enumerate(marks[: len(anchor)]):
        if m.group(0).lower() != anchor[i]:
            return ""                # not this line's opening words
        end = m.end()
    span = line[: end]

    # "Carrefour (CARR.PA)" — the anchor ends inside a bracket the span opened.
    # Reach forward a bounded distance to close it rather than shipping "(CARR".
    if span.count("(") > span.count(")"):
        tail = line[end: end + _MAX_BRACKET_REACH]
        close = tail.find(")")
        if close < 0:
            return ""
        span = line[: end + close + 1]
    return span.strip()


def recover(cleaned_title: str, body_text: str) -> str:
    """The report's printed headline for ``cleaned_title``, or '' when not found.

    Anchored on the cleaned title's own tokens, so the return value always says
    the same words the filename did — only with the punctuation and casing the PDF
    actually prints ("Pmi Fall Seven Times" → "PMI: FALL SEVEN TIMES"). Anything
    the line continues with past those words is dropped, because a byline and a
    subtitle look identical from here and inventing an author into a title is the
    worse error. Never raises.
    """
    try:
        anchor = _tokens(cleaned_title)
        if len(anchor) < _MIN_ANCHOR_TOKENS:
            return ""
        for line in _candidates(body_text):
            span = _span(anchor, line)
            if not span or not (_MIN_TITLE_CHARS <= len(span) <= _MAX_TITLE_CHARS):
                continue
            if _tokens(span)[: len(anchor)] != anchor:
                continue
            return span
        return ""
    except Exception:  # noqa: BLE001 — a title is never worth failing an ingest
        return ""


def resolve(title: str, body_text: str = "") -> tuple[str, str]:
    """``(title, source)`` for a possibly filename-derived ``title``.

    ``source`` ∈ ``sidecar`` (not filename-shaped — returned untouched) |
    ``pdf`` (recovered from the report's first page) | ``filename`` (furniture
    stripped, but the headline could not be found — the operator-visible case).

    The id is deliberately NOT re-derived from a repaired title: ids key receipts,
    vault objects and excerpt rows, so their stability outranks their prettiness.
    """
    t = (title or "").strip()
    if not t or not looks_filename_derived(t):
        return t, "sidecar"
    cleaned = clean(t) or t
    found = recover(cleaned, body_text)
    if found:
        return found, "pdf"
    return cleaned, "filename"
