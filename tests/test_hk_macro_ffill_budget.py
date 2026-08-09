"""HK monthly-macro step-fill must bridge China's publication lag.

Pins MACRO_FFILL_LIMIT_BDAYS against the real incident calendar (2026-08-08,
commit 901282ec209): China CPI/PPI prints are stamped on their reference month
(June -> 2026-06-01) and the NEXT print publishes ~5 weeks after the reference
month ends (July's on ~08-09), so the June stamp is the freshest available for
~49 business days. The old limit of 40 ran dry on exactly 2026-07-28 —
cpi_yoy/ppi_yoy dropped out together and, with the cache-fed inflation basket
dark on the weekly runner, the whole inflation axis went NaN for 9 sessions.
engine/china_inputs.py took the same fix first (limit=90); this pins the HK
mirror so the two sides cannot drift apart again.

Run: .venv/bin/python -m pytest tests/test_hk_macro_ffill_budget.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.hk_inputs import MACRO_FFILL_LIMIT_BDAYS


def _carry(limit: int) -> pd.Series:
    """Replicate build_features' put() idiom: union-reindex + ffill(limit)."""
    idx = pd.bdate_range("2026-01-01", "2026-08-07")   # daily grid to the incident end
    stamps = pd.Series(
        [0.8, 0.9, 1.0],
        index=pd.to_datetime(["2026-04-01", "2026-05-01", "2026-06-01"]))
    union = idx.union(stamps.index)
    return stamps.reindex(union).ffill(limit=limit).reindex(idx)


def test_budget_bridges_the_publication_gap():
    s = _carry(MACRO_FFILL_LIMIT_BDAYS)
    # every session of the incident window carries the June print
    assert not s.loc["2026-07-28":"2026-08-07"].isna().any()


def test_incident_budget_of_40_ran_dry_on_2026_07_28():
    s = _carry(40)
    assert not np.isnan(s.loc["2026-07-27"])   # last covered session
    assert np.isnan(s.loc["2026-07-28"])       # first dark session of the incident


def test_budget_still_expires_on_a_real_outage():
    # honesty bound: a genuinely dead macro feed must still NaN out eventually
    idx = pd.bdate_range("2026-01-01", "2026-12-31")
    stamps = pd.Series([1.0], index=pd.to_datetime(["2026-06-01"]))
    s = stamps.reindex(idx.union(stamps.index)).ffill(limit=MACRO_FFILL_LIMIT_BDAYS).reindex(idx)
    assert np.isnan(s.iloc[-1])
    assert int(s.notna().sum()) == MACRO_FFILL_LIMIT_BDAYS + 1   # stamp + budget, no further
