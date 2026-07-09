"""lib.warn_fuzzy — Employer→ticker fuzzy matching shared utility.

Extracted from scripts/w2044_warn_intensity_phase0.py so that both the
backtest study (w2044) and the nightly theme_warn engine share the same
matching logic without circular imports.

Matching contract:
  * Case-insensitive substring match on employer_raw.
  * Longest pattern wins (specificity rule).
  * Validity-window check (valid_from / valid_to columns, inclusive ISO dates).
  * Entries whose pattern starts with '#' are comments — skipped.
  * Entries whose ticker is blank are private/exclusions — skipped.

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
# Minimum pattern length guard: single-word generic terms that would
# match anything (e.g. "systems", "group", "inc") are rejected even if
# present in the map.  Callers can lower this for unit tests.
# ---------------------------------------------------------------------------
MIN_PATTERN_LEN: int = 5

# Generic words that must NOT appear as the ENTIRE pattern (even if long
# enough) — they match too broadly across employers.
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


def match_ticker(
    employer_raw: str,
    ticker_rows: list[dict],
    notice_date: str,
    *,
    min_pattern_len: int = MIN_PATTERN_LEN,
) -> Optional[str]:
    """Return the best ticker match for *employer_raw* at *notice_date*.

    Strategy: case-insensitive substring; longest pattern wins (specificity).
    Generic single-token patterns and patterns below *min_pattern_len* are
    skipped to prevent false positives.

    Parameters
    ----------
    employer_raw:
        The raw employer string from the WARN notice.
    ticker_rows:
        Output of ``load_ticker_map()``.
    notice_date:
        ISO date string ``YYYY-MM-DD`` of the notice (used for validity window).
    min_pattern_len:
        Minimum length of a pattern to be considered (default 5).

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

        # Substring match against either the raw or the suffix-stripped form
        if pat not in emp and pat not in emp_clean:
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
