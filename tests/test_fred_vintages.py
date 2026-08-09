"""ALFRED point-in-time FRED vintages (Phase B / Step 1, macro half).

The live FRED store keeps the latest-revised value per date, so a macro backtest
reading it sees numbers nobody had in real time (payrolls revised for years; NFCI
re-revised weekly). collectors.fred stores the INITIAL RELEASE per period stamped
with its first-publish date; as_of_series(date) returns what was knowable then.
These tests pin the leak-free property on a synthetic vintage matrix (no network).
"""
from __future__ import annotations

import pandas as pd

from collectors.fred import as_of_series, fetch_all_vintages, initial_release


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


def test_output_type_2_json_wide_shape_is_normalized_to_full_vintages(monkeypatch):
    """Pin the documented JSON shape: one date row with series_vintage keys."""
    calls = []

    class _Response:
        def json(self):
            return {
                "output_type": 2,
                "observations": [
                    {
                        "date": "2025-01-01",
                        "CPIAUCSL_20250212": "100.0",
                        "CPIAUCSL_20250312": "100.1",
                    },
                    {
                        "date": "2025-02-01",
                        "CPIAUCSL_20250212": ".",
                        "CPIAUCSL_20250312": "100.5",
                    },
                ],
            }

    def _fake_http_get(self, url, **kwargs):
        calls.append((url, kwargs))
        return _Response()

    monkeypatch.setattr(
        "collectors.fred._VintageAdapter.http_get",
        _fake_http_get,
    )

    frame = fetch_all_vintages(
        "CPIAUCSL",
        output_type=2,
        realtime_start="2025-01-01",
        api_key="test-key",
    )

    assert list(frame.columns) == ["period", "realtime_start", "realtime_end", "value"]
    assert [tuple(row) for row in frame[["period", "realtime_start", "value"]].itertuples(index=False, name=None)] == [
        (pd.Timestamp("2025-01-01"), pd.Timestamp("2025-02-12"), 100.0),
        (pd.Timestamp("2025-01-01"), pd.Timestamp("2025-03-12"), 100.1),
        (pd.Timestamp("2025-02-01"), pd.Timestamp("2025-03-12"), 100.5),
    ]
    assert frame.iloc[0]["realtime_end"] == pd.Timestamp("2025-03-11")
    assert str(frame.iloc[-1]["realtime_end"].date()) == "9999-12-31"
    assert calls[0][1]["params"]["output_type"] == 2
    assert calls[0][1]["params"]["file_type"] == "json"
