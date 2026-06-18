"""Offline test for the World Bank reserves collector — JSON -> wide (year x ISO3)."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.worldbank import WorldBankAdapter  # noqa: E402


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _payload(indicator):
    meta = {"page": 1, "pages": 1, "per_page": 2000, "total": 4}
    data = [
        {"countryiso3code": "USA", "date": "2024", "value": 910.0},
        {"countryiso3code": "USA", "date": "2023", "value": 770.0},
        {"countryiso3code": "CHN", "date": "2024", "value": 3456.0},
        {"countryiso3code": "XKX", "date": "2024", "value": None},   # null dropped
        {"countryiso3code": "", "date": "2024", "value": 5.0},        # blank iso dropped
    ]
    return [meta, data]


def test_fetch_builds_wide_frames(monkeypatch):
    a = WorldBankAdapter()
    monkeypatch.setattr(a, "http_get", lambda url, **kw: _Resp(_payload(url)))
    frames = a.fetch(full_history=True)
    assert set(frames) == {"reserves_total", "reserves_exgold"}
    tot = frames["reserves_total"]
    assert isinstance(tot.index, pd.DatetimeIndex)
    assert "USA" in tot.columns and "CHN" in tot.columns
    assert "XKX" not in tot.columns          # null-only country dropped
    assert "" not in tot.columns             # blank iso dropped
    assert tot.loc[pd.Timestamp("2024-12-31"), "USA"] == 910.0
    assert tot.loc[pd.Timestamp("2023-12-31"), "USA"] == 770.0
