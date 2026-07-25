"""research_vault.excerpt — the PUBLIC first-pages excerpt for the SEO pages.

This is the "flexible sampling lead-in": a verbatim, plain-text sample of a
report's OPENING pages, published OUTSIDE the paywall on
``site/research/<slug>.html`` so an exact-quote Google search — someone pasting a
sentence a news blog lifted from the PDF — matches our page. A one-line catalog
teaser can never match those queries; only the report's own words can.

The dial constants below are the entire risk surface: they trade SEO reach
against how much of a THIRD PARTY's copyrighted research we redistribute for
free. Raising them is an OPERATOR decision, never a builder default — the values
here publish a lead-in (cover + roughly the first body page), not the report.

Two halves, both never-raise:
  * ``derive()`` — pure: pdftotext body text → cleaned paragraph list;
  * ``snapshot()`` + ``write_repo_snapshot()`` — corpus.sqlite → the repo-committed
    ``data/research_vault/excerpts.json`` that the nightly render reads.

Why the repo snapshot: the corpus (and every PDF) lives ONLY in R2, and the
render path must stay R2-free. So the hourly ingest job snapshots excerpts into
git exactly like it snapshots catalog.json. Serialization is deterministic and
TIMESTAMP-FREE so that hourly job only produces a git diff when the CONTENT
changed — a stamped payload would commit-churn 24×/day. stdlib only.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger("research_vault.excerpt")

# --- the dials (OPERATOR decisions — see the module docstring) ---------------
# Total published characters per report. ~4200 ≈ a page and a half of prose: big
# enough that a quoted sentence from the opening usually lands inside it, small
# enough to stay a lead-in rather than a redistribution of the report.
EXCERPT_MAX_CHARS = 4200
# How many leading PDF pages we sample from at all.
EXCERPT_MAX_PAGES = 2
# Bank cover pages are often a logo + three words of text, so the first
# EXCERPT_MAX_PAGES pages can clean down to almost nothing. When they do, extend
# the window one page at a time (never past SPARSE_MAX_PAGES) so those reports
# still get a usable excerpt instead of an empty one.
SPARSE_MIN_CHARS = 400
SPARSE_MAX_PAGES = 4
# Below this, a "paragraph" is a header/footer/caption/figure label, not prose.
MIN_PARA_CHARS = 30

# pdftotext writes a form feed between pages.
_PAGE_SEP = "\f"

_EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
_URL_RE = re.compile(r"https?://\S+")
_WWW_RE = re.compile(r"www\.\S+")
# Phone-like runs — ≥9 chars of digits/separators — are contact-block furniture.
# This is only the CANDIDATE matcher: the same character shape also covers dates,
# so whether a candidate is actually stripped is decided by a DIGIT floor in
# _clean_candidate, not by this length floor alone.
_PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{7,}\d")
_WS_RE = re.compile(r"\s+")
_PARA_SPLIT_RE = re.compile(r"\n\s*\n")
# Bare page numbers / rules / bullets left over as their own "paragraph". Kept
# even though MIN_PARA_CHARS already drops anything this short — the two dials
# move independently, and this one encodes WHAT furniture looks like.
_FURNITURE_RE = re.compile(r"[0-9ivxlcIVXLC\s.·—-]{1,8}")
_TRAIL_PUNCT = " ,;:·—-"


def _clean_candidate(raw: str) -> str:
    """One paragraph candidate → publishable plain text.

    Emails, URLs and phone numbers go first (a cover-page contact block and its
    disclaimer links are what every bank ships, and none of it is prose we want
    indexed — stripping only the email would still publish the analyst's direct
    line), then all whitespace runs — pdftotext ``-layout`` leaves column
    padding — collapse to single spaces. Phones run BEFORE that collapse so a
    number broken across the layout's own spacing is still one match.

    ``_PHONE_RE`` only PROPOSES a match; it is stripped only when it carries ≥9
    digits. A real phone number carries 10-11+ (country/area code plus the line),
    while the same shape of digits-and-separators is also how a report writes the
    figures it is ABOUT: an ISO date (``2026-07-25``) has 8 digits and a year
    range (``2025-2026``) has 8, so both survive verbatim. The floor is set where
    nothing above it could be a prose figure — verbatim fidelity is the entire
    point of the excerpt, so an over-eager strip is the worse failure.
    """
    c = _EMAIL_RE.sub(" ", raw)
    c = _URL_RE.sub(" ", c)
    c = _WWW_RE.sub(" ", c)
    c = _PHONE_RE.sub(
        lambda m: " " if sum(ch.isdigit() for ch in m.group()) >= 9 else m.group(0), c)
    return _WS_RE.sub(" ", c).strip()


def _paragraphs(pages: list[str]) -> list[str]:
    """Cleaned, publishable paragraphs across ``pages`` (in reading order)."""
    out: list[str] = []
    for page in pages:
        for raw in _PARA_SPLIT_RE.split(page):
            c = _clean_candidate(raw)
            if len(c) < MIN_PARA_CHARS:
                continue
            if _FURNITURE_RE.fullmatch(c):
                continue
            out.append(c)
    return out


def derive(body_text: str | None, max_chars: int = EXCERPT_MAX_CHARS) -> list[str]:
    """pdftotext body text → the public excerpt as a list of paragraphs.

    Pure + never-raises: returns ``[]`` for None/empty/whitespace-only input and
    for any body that cleans down to nothing (scanned PDFs with no text layer).
    The last paragraph is truncated at a word boundary and marked with "…" so the
    excerpt visibly stops mid-report rather than pretending to be complete.
    """
    try:
        body = (body_text or "").replace("\r\n", "\n")
        if not body.strip():
            return []

        pages = body.split(_PAGE_SEP)
        window = max(1, min(EXCERPT_MAX_PAGES, len(pages)))
        paras = _paragraphs(pages[:window])
        ceiling = min(SPARSE_MAX_PAGES, len(pages))
        # Text-sparse cover pages: widen the window until the sample is usable.
        while sum(len(p) for p in paras) < SPARSE_MIN_CHARS and window < ceiling:
            window += 1
            paras = _paragraphs(pages[:window])

        out: list[str] = []
        total = 0
        for p in paras:
            if total + len(p) <= max_chars:
                out.append(p)
                total += len(p)
                continue
            room = max_chars - total
            if room > 0:
                cut = p[:room].rsplit(" ", 1)[0].rstrip(_TRAIL_PUNCT)
                if cut:
                    out.append(cut + "…")
            break
        return out
    except Exception as exc:  # noqa: BLE001 — an excerpt is never worth a failure
        log.warning("research_vault: excerpt derive failed: %s", exc)
        return []


def snapshot(conn, catalog_ids) -> dict[str, list[str]]:
    """Derive excerpts for every catalog document present in the corpus.

    ``conn`` is a sqlite3 connection to corpus.sqlite (``documents(doc_id, body)``
    — see corpus.py). ``catalog_ids`` is the set of ids in the PUBLIC catalog, so
    a doc that was pulled from the catalog stops being excerpted too. Documents
    whose derivation is empty (scanned/image-only PDFs) are omitted entirely
    rather than stored as ``[]`` — the render treats absent and empty the same,
    and omitting keeps the committed file small.

    Keys are emitted in sorted id order (deterministic diffs). Never raises: any
    sqlite trouble degrades to ``{}``, which ``write_repo_snapshot`` then refuses
    to publish over a good committed snapshot.
    """
    try:
        ids = set(catalog_ids or ())
        if not ids:
            return {}
        rows = conn.execute("SELECT doc_id, body FROM documents").fetchall()
    except Exception as exc:  # noqa: BLE001
        log.warning("research_vault: excerpt snapshot query failed: %s", exc)
        return {}

    pairs: list[tuple[str, list[str]]] = []
    for row in rows:
        # Index access works for both sqlite3.Row and the default tuple factory.
        doc_id = row[0]
        if not doc_id or doc_id not in ids:
            continue
        paras = derive(row[1])
        if paras:
            pairs.append((doc_id, paras))
    return {doc_id: paras for doc_id, paras in sorted(pairs, key=lambda kv: kv[0])}


def write_repo_snapshot(excerpts: dict[str, list[str]], path) -> bool:
    """Write the repo-committed excerpts snapshot. Returns True when written.

    REFUSES an empty dict (same protective idiom as ``ingest._restore_corpus``):
    a fresh runner, a failed corpus restore, or an empty read would otherwise
    clobber a good committed snapshot with ``{}`` and blank the excerpt on every
    SEO page. Losing an hour of new excerpts is cheap; losing all of them is not.

    The payload is sorted + indented + carries NO timestamp, so an hour that
    changed nothing serializes byte-identically and produces no git diff.
    Never raises.
    """
    if not excerpts:
        log.warning("research_vault: excerpt snapshot is empty — refusing to write "
                    "(protects the committed snapshot)")
        return False
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"schema": 1, "excerpts": excerpts},
                             ensure_ascii=False, sort_keys=True, indent=1) + "\n"
        p.write_text(payload, encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("research_vault: excerpt snapshot write failed: %s", exc)
        return False
