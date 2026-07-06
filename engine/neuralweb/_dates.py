"""engine.neuralweb._dates — Date normalisation helper (R5 §5.2).

Single exported function:

    to_iso(s) -> str | None

Converts the four date string formats observed in R5 source artifacts into
ISO-8601 date strings (YYYY-MM-DD), or returns None for null / unrecognised
inputs.  Never raises.

Observed formats
----------------
1. ISO date:          "2026-07-05"          → "2026-07-05"
2. Display string:    "Jul 05, 2026"        → "2026-07-05"
3. ISO datetime:      "2026-07-05T12:00:00Z" → "2026-07-05"
4. None / falsy:      None, "", ...         → None

The display-string format ("Jul 05, 2026") is the current asof encoding used
by data/forex/latest.json and data/commodity/latest.json — it will be replaced
with a proper "asof" ISO field in PR-E, but the normaliser must handle it in
the interim.
"""
from __future__ import annotations

import re

# Month abbreviation map (all-caps for case-insensitive lookup)
_MONTH_ABB: dict[str, str] = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}

# "Jul 05, 2026" — month-name, day, year
_DISPLAY_RE = re.compile(
    r"^([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})$"
)


def to_iso(s: object) -> str | None:
    """Normalise *s* to an ISO-8601 date string (YYYY-MM-DD) or None.

    Parameters
    ----------
    s:
        Input value — expected to be str, None, or another falsy type.

    Returns
    -------
    str | None
        "YYYY-MM-DD" on success, None on any failure or null input.
    """
    if not s or not isinstance(s, str):
        return None

    s = s.strip()
    if not s:
        return None

    # Fast path: already ISO (date or datetime prefix)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        # "2026-07-05" or "2026-07-05T..." or "2026-07-05 ..."
        candidate = s[:10]
        # Light sanity check: digits in expected positions
        if candidate[:4].isdigit() and candidate[5:7].isdigit() and candidate[8:10].isdigit():
            return candidate

    # Display string: "Jul 05, 2026"
    m = _DISPLAY_RE.match(s)
    if m:
        mon_str = m.group(1).upper()
        day = m.group(2).zfill(2)
        year = m.group(3)
        month = _MONTH_ABB.get(mon_str)
        if month:
            return f"{year}-{month}-{day}"

    return None
