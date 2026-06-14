"""ALFRED point-in-time FRED vintages (Phase B / Step 1, macro half).

The live FRED store keeps the latest-revised value per date, so a macro backtest
reading it sees numbers nobody had in real time (payrolls revised for years; NFCI
re-revised weekly). collectors.fred stores the INITIAL RELEASE per period stamped
with its first-publish date; as_of_series(date) returns what was knowable then.
These tests pin the leak-free property on a synthetic vintage matrix (no network).
"""
from __future__ import annotations

import pandas as pd

from collectors.fred import as_of_series, initial_release


def _vintages() -> pd.DataFrame:
    # PAYEMS-like: period 2008-09 first published 2008-10-03 at 137318 (initial release).
    # A later period (2009-01) wasn't published until 2009-02-06.
    rows = [
        {"series": "PAYEMS", "period": "2008-09-01", "value": 137318.0,
         "realtime_start": "2008-10-03", "realtime_end": "9999-12-31"},
        {"series": "PAYEMS", "period": "2008-12-01", "value": 135000.0,
         "realtime_start": "2009-01-09", "realtime_end": "9999-12-31"},
        {"series": "PAYEMS", "period": "2009-01-01", "value": 133500.0,
         "realtime_start": "2009-02-06", "realtime_end": "9999-12-31"},
    ]
    v = pd.DataFrame(rows)
    for c in ("period", "realtime_start", "realtime_end"):
        v[c] = pd.to_datetime(v[c])
    return v


def test_as_of_excludes_not_yet_published_periods():
    v = _vintages()
    # On 2009-01-15: 2008-09 and 2008-12 are out, but 2009-01 (pub 2009-02-06) is NOT
    s = as_of_series("PAYEMS", "2009-01-15", v)
    assert pd.Timestamp("2008-12-01") in s.index
    assert pd.Timestamp("2009-01-01") not in s.index


def test_as_of_before_first_release_is_empty():
    v = _vintages()
    assert as_of_series("PAYEMS", "2008-09-15", v).empty   # 2008-09 not published until 10-03


def test_as_of_coverage_grows_with_time():
    v = _vintages()
    assert len(as_of_series("PAYEMS", "2008-11-01", v)) < len(as_of_series("PAYEMS", "2009-03-01", v))


def test_initial_release_returns_first_published_values():
    v = _vintages()
    ir = initial_release("PAYEMS", v)
    assert ir.loc[pd.Timestamp("2008-09-01")] == 137318.0
    assert len(ir) == 3


def test_unknown_series_is_empty():
    assert as_of_series("NOPE", "2020-01-01", _vintages()).empty
