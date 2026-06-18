"""Offline tests for the JODI collector's unit reconciliation + filtering.

The one non-obvious bit: CONVBBL is a bbl/tonne CONVERSION FACTOR, not a level.
The level is KBBL where reported, else KTONS x CONVBBL. Missing markers ('-','x','..')
must drop, off-roster / wrong-flow / wrong-product rows must filter out, and a country
that reports nothing (China) must be absent.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.jodi import JodiAdapter  # noqa: E402

COLS = ["REF_AREA", "TIME_PERIOD", "ENERGY_PRODUCT", "FLOW_BREAKDOWN",
        "UNIT_MEASURE", "OBS_VALUE", "ASSESSMENT_CODE"]


def _row(area, period, unit, val, code=1, prod="CRUDEOIL", flow="CLOSTLV"):
    return [area, period, prod, flow, unit, val, code]


def _fixture() -> pd.DataFrame:
    rows = [
        # US reports in barrels (KBBL), officially (code 1) -> use KBBL
        _row("US", "2024-12", "KBBL", "671557.0000", 1),
        _row("US", "2024-12", "KTONS", "90751.0000", 1),
        _row("US", "2024-12", "CONVBBL", "7.4000", 1),
        # Germany reports tonnes only (KBBL missing) -> derive KTONS x CONVBBL
        _row("DE", "2024-12", "KBBL", "-", 1),
        _row("DE", "2024-12", "KTONS", "10000.0000", 1),
        _row("DE", "2024-12", "CONVBBL", "7.3000", 1),
        # India KBBL present but ESTIMATED (code 3) -> assess carries 3
        _row("IN", "2024-12", "KBBL", "46522.3200", 3),
        # China reports nothing -> must be absent
        _row("CN", "2024-12", "KBBL", "-", 3),
        _row("CN", "2024-12", "KTONS", "..", 3),
        _row("CN", "2024-12", "CONVBBL", "x", 3),
        # noise that must be filtered: wrong flow, wrong product, off-roster country
        _row("US", "2024-12", "KBBL", "999.0", 1, flow="PRODUCTION"),
        _row("US", "2024-12", "KBBL", "888.0", 1, prod="TOTPRODS"),
        _row("ZZ", "2024-12", "KBBL", "777.0", 1),
    ]
    return pd.DataFrame(rows, columns=COLS)


def test_reconciliation(monkeypatch):
    a = JodiAdapter()
    monkeypatch.setattr(a, "_years", lambda full_history: [2024])
    monkeypatch.setattr(a, "_fetch_year", lambda year: _fixture())
    frames = a.fetch(full_history=False)

    assert "crude_us" in frames and "crude_de" in frames and "crude_in" in frames
    assert "crude_cn" not in frames               # China reports nothing
    assert "crude_zz" not in frames               # off-roster filtered

    us = frames["crude_us"]
    assert us["level"].iloc[-1] == 671557.0       # KBBL used directly
    assert int(us["assess"].iloc[-1]) == 1

    de = frames["crude_de"]
    assert abs(de["level"].iloc[-1] - 10000.0 * 7.3) < 1e-6   # KTONS x CONVBBL

    assert int(frames["crude_in"]["assess"].iloc[-1]) == 3    # estimate flag preserved

    # the wrong-flow / wrong-product / off-roster noise never leaked into crude_us
    assert (us["level"] == 999.0).sum() == 0
    assert (us["level"] == 888.0).sum() == 0


def test_index_is_monthly_datetime(monkeypatch):
    a = JodiAdapter()
    monkeypatch.setattr(a, "_years", lambda full_history: [2024])
    monkeypatch.setattr(a, "_fetch_year", lambda year: _fixture())
    frames = a.fetch(full_history=False)
    idx = frames["crude_us"].index
    assert isinstance(idx, pd.DatetimeIndex)
    assert str(idx[-1].date()) == "2024-12-01"
