"""lib.warn_fuzzy — Employer→ticker fuzzy matching shared utility.

Extracted from scripts/w2044_warn_intensity_phase0.py so that both the
backtest study (w2044) and the nightly theme_warn engine share the same
matching logic without circular imports.

Matching contract:
  * Word-boundary token match on employer_raw (case-insensitive).  A pattern
    must appear as a complete word (or phrase) in the employer string — raw
    substring matching ("apple" in "Applebee's") is prevented by requiring the
    match to start and end on a word boundary.
  * Longest pattern wins (specificity rule).
  * Validity-window check (valid_from / valid_to columns, inclusive ISO dates).
  * Entries whose pattern starts with '#' are comments — skipped.
  * Entries whose ticker is blank are private/exclusions — skipped.
  * Short but specific patterns (e.g. "GM", "F", "T", "KLA", "UPS") ARE
    matched — the map is curated with validity windows, so the false-positive
    risk from short single-token patterns is managed by the map itself, not by
    a length floor.  Only whole-pattern generic tokens (see _BANNED_GENERIC)
    are blocked.

The ticker map CSV has columns:
  employer_name_pattern, ticker, valid_from, valid_to, confidence, notes

This module is import-safe at any path; no side-effects on import.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Minimum pattern length guard.
# Set to 1 — length alone is not a reliable guard (short but specific tickers
# like "GM", "F", "T", "KLA", "UPS" are valid map entries).  Broad single-
# token patterns are blocked via _BANNED_GENERIC instead.  Callers may still
# pass min_pattern_len to override for tests.
# ---------------------------------------------------------------------------
MIN_PATTERN_LEN: int = 1

# Generic words that must NOT appear as the ENTIRE pattern — they match too
# broadly across employers.
_BANNED_GENERIC = frozenset({
    "systems", "group", "inc", "corp", "co.", "company", "holdings",
    "services", "solutions", "technologies", "technology", "industries",
    "international", "enterprises", "management", "partners", "capital",
    "global", "national", "american", "united", "general",
})


def _is_generic(pattern: str) -> bool:
    """Return True if `pattern` (lowercased, stripped) is a banned generic token."""
    return pattern.strip().rstrip(".").lower() in _BANNED_GENERIC


def load_ticker_map(map_path: Path) -> list[dict]:
    """Load employer→ticker map from a CSV file.

    Skips comment rows (pattern starts with '#') and private/exclusion
    entries (blank ticker field).  Returns a list of row dicts with at
    minimum the keys: ``employer_name_pattern``, ``ticker``,
    ``valid_from``, ``valid_to``.

    Returns an empty list when the file does not exist or is unreadable.
    """
    if not map_path.exists():
        return []
    rows: list[dict] = []
    try:
        with open(map_path, encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                pat = r.get("employer_name_pattern", "").strip()
                if not pat or pat.startswith("#"):
                    continue
                ticker = r.get("ticker", "").strip()
                if not ticker:
                    continue  # private / exclude entry
                rows.append(r)
    except OSError:
        pass
    return rows


def _word_boundary_match(pat: str, text: str) -> bool:
    """Return True if *pat* appears in *text* at a word boundary.

    Uses ``re.search`` with ``\\b`` anchors so that short but specific patterns
    like "GM", "F", "KLA", "UPS" match "General Motors (GM)" and "Ford Motor Co"
    but "apple" does NOT match "Applebee's Grill and Bar".

    The pattern is treated as a literal string (not a regex).
    """
    # Escape regex metacharacters in pat, then wrap in word boundaries.
    escaped = re.escape(pat)
    return bool(re.search(r"\b" + escaped + r"\b", text))


def match_ticker(
    employer_raw: str,
    ticker_rows: list[dict],
    notice_date: str,
    *,
    min_pattern_len: int = MIN_PATTERN_LEN,
) -> Optional[str]:
    """Return the best ticker match for *employer_raw* at *notice_date*.

    Strategy: word-boundary token match (case-insensitive); longest pattern
    wins (specificity).  Generic single-token patterns and patterns below
    *min_pattern_len* are skipped.  Short but specific patterns (e.g. "GM",
    "F", "UPS") are retained — the curated map controls their validity windows.

    Parameters
    ----------
    employer_raw:
        The raw employer string from the WARN notice.
    ticker_rows:
        Output of ``load_ticker_map()``.
    notice_date:
        ISO date string ``YYYY-MM-DD`` of the notice (used for validity window).
    min_pattern_len:
        Minimum length of a pattern to be considered (default 1).

    Returns
    -------
    str or None
        Matched ticker symbol, or ``None`` when no match found.
    """
    emp = employer_raw.lower().strip()
    if not emp:
        return None
    # Remove common legal suffixes before matching so "Apple Inc." still hits "apple"
    emp_clean = re.sub(
        r"\b(inc\.?|corp\.?|llc\.?|ltd\.?|co\.?|plc\.?|lp\.?)\s*$",
        "",
        emp,
    ).strip()

    best_ticker: Optional[str] = None
    best_len: int = 0

    for r in ticker_rows:
        pat = r.get("employer_name_pattern", "").lower().strip()
        if not pat or pat.startswith("#"):
            continue
        if len(pat) < min_pattern_len:
            continue
        if _is_generic(pat):
            continue

        # Validity window (inclusive ISO date strings)
        vf = (r.get("valid_from") or "").strip() or "1900-01-01"
        vt = (r.get("valid_to") or "").strip() or "2099-12-31"
        try:
            if notice_date < vf or notice_date > vt:
                continue
        except Exception:  # noqa: BLE001
            pass

        # Word-boundary match against either the raw or the suffix-stripped form.
        # This prevents "apple" from matching "Applebee's" while still matching
        # "Apple Inc." and "Apple Computer".
        if not _word_boundary_match(pat, emp) and not _word_boundary_match(pat, emp_clean):
            continue

        if len(pat) > best_len:
            best_len = len(pat)
            best_ticker = r["ticker"].strip()

    return best_ticker


def match_ticker_to_baskets(
    employer_raw: str,
    notice_date: str,
    ticker_rows: list[dict],
    basket_members: dict[str, list[str]],
    *,
    min_pattern_len: int = MIN_PATTERN_LEN,
) -> Optional[str]:
    """Match employer to a ticker and return the basket_id it belongs to.

    Parameters
    ----------
    basket_members:
        ``{basket_id: [ticker, ...]}`` — the basket membership map.

    Returns
    -------
    str or None
        ``basket_id`` of the first basket that contains the matched ticker,
        or ``None`` when the employer cannot be matched or the ticker does not
        belong to any basket.
    """
    ticker = match_ticker(
        employer_raw, ticker_rows, notice_date, min_pattern_len=min_pattern_len
    )
    if ticker is None:
        return None
    for bid, members in basket_members.items():
        if ticker in members:
            return bid
    return None
