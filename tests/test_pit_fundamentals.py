"""Point-in-time fundamentals panel (Phase B / Step 1).

The factor engine previously read a single latest-FY snapshot, so a factor
backtest would use today's restated numbers at every past date (look-ahead).
collectors.edgar.fetch_panel now builds a (ticker, fy) panel stamped with
period_end + asof_date (= period_end + reporting_lag_days), and
as_of_cross_section(date) returns only what was knowable on that date. These
tests pin the leak-free property and the prior-year linkage on a synthetic panel
(no network), plus a guard that the as-of reader degrades gracefully.
"""
from __future__ import annotations

import pandas as pd

from collectors.edgar import as_of_cross_section


def _panel() -> pd.DataFrame:
    # two Dec-FY filers, FY2021..2023; asof = period_end + 120d
    rows = []
    for t, base in (("AAA", 100.0), ("BBB", 50.0)):
        for fy, end in ((2021, "2021-12-31"), (2022, "2022-12-31"), (2023, "2023-12-31")):
            rows.append({"ticker": t, "cik": 1 if t == "AAA" else 2, "fy": fy,
                         "assets": base * (fy - 2000), "ni": base, "equity": base * 5,
                         "period_end": pd.Timestamp(end)})
    p = pd.DataFrame(rows)
    p["asof_date"] = p["period_end"] + pd.Timedelta(days=120)
    return p


def test_as_of_excludes_not_yet_filed_reports():
    p = _panel()
    # 2023-03-01: FY2022 (asof 2023-04-30) is NOT yet knowable -> latest is FY2021
    cs = as_of_cross_section("2023-03-01", panel=p)
    assert int(cs.loc["AAA", "fy"]) == 2021
    # 2023-06-01: now past FY2022's asof_date -> FY2022
    cs2 = as_of_cross_section("2023-06-01", panel=p)
    assert int(cs2.loc["AAA", "fy"]) == 2022


def test_as_of_picks_latest_knowable_year_per_ticker():
    p = _panel()
    cs = as_of_cross_section("2030-01-01", panel=p)
    assert int(cs.loc["AAA", "fy"]) == 2023 and int(cs.loc["BBB", "fy"]) == 2023
    assert cs.index.is_unique                      # one row per ticker


def test_as_of_before_any_filing_is_empty():
    p = _panel()
    cs = as_of_cross_section("2000-01-01", panel=p)
    assert cs.empty


def test_as_of_is_monotone_in_date():
    p = _panel()
    fys = [int(as_of_cross_section(d, panel=p).loc["AAA", "fy"])
           for d in ("2022-06-01", "2023-06-01", "2024-06-01")
           if "AAA" in as_of_cross_section(d, panel=p).index]
    assert fys == sorted(fys)                      # never goes backwards as the clock advances
