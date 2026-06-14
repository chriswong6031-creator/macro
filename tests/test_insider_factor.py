"""Insider-buying factor — collector panel parse + signal-construction unit tests.

Covers the point-in-time per-transaction panel (collectors/sec_insider) and the
causal cross-sectional signals (engine/insider_factor): exclusion rules, role/
identity extraction, opportunistic-vs-routine classification, size-normalisation
and — the load-bearing property — NO LOOK-AHEAD (a filing enters a rebalance only
once its filing_date has passed).
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.sec_insider import _parse_panel, _quarters_from  # noqa: E402
from engine.insider_factor import (build_signals, classify_routine,  # noqa: E402
                                   market_cap, role_weights)


def _synthetic_zip() -> zipfile.ZipFile:
    """A form345 quarter exercising every filter: amendment, non-P/S code,
    sub-threshold trade, direct/indirect, multi-owner cluster, officer titles."""
    sub = ("ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\tISSUERTRADINGSYMBOL\n"
           "A1\t15-JAN-2025\t4\t320193\tAAPL\n"
           "A2\t20-JAN-2025\t4\t320193\tAAPL\n"
           "A3\t25-JAN-2025\t4\t320193\tAAPL\n"
           "A4\t10-JAN-2025\t4/A\t111\tXYZ\n"      # amendment — excluded
           "A5\t12-JAN-2025\t4\t111\tXYZ\n"        # sub-threshold trade
           "A6\t14-JAN-2025\t4\t111\tXYZ\n"        # M code — excluded
           "A7\t16-JAN-2025\t4\t222\tTINY\n")
    own = ("ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNER_RELATIONSHIP\tRPTOWNER_TITLE\n"
           "A1\t1001\tDirector,Officer\tChief Executive Officer\n"
           "A2\t1002\tDirector\t\n"
           "A3\t1003\tOfficer\tEVP\n"
           "A4\t1004\tTenPercentOwner\t\n"
           "A5\t1004\tTenPercentOwner\t\n"
           "A6\t1005\tOfficer\t\n"
           "A7\t1006\tOfficer\tChief Financial Officer\n")
    tr = ("ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tDIRECT_INDIRECT_OWNERSHIP\n"
          "A1\t15-JAN-2025\tP\t1000\t150\tD\n"     # 150k buy, direct, CEO
          "A2\t18-JAN-2025\tP\t500\t150\tD\n"      # 75k buy
          "A3\t24-JAN-2025\tS\t2000\t150\tI\n"     # 300k sell, indirect
          "A4\t09-JAN-2025\tP\t1000\t50\tD\n"      # amendment — excluded
          "A5\t12-JAN-2025\tP\t100\t5\tD\n"        # $500 < min_trade — dropped
          "A6\t14-JAN-2025\tM\t1000\t50\tD\n"      # option exercise — excluded
          "A7\t16-JAN-2025\tP\t1000\t20\tI\n")     # 20k buy, indirect, CFO
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("2025q1_SUBMISSION.tsv", sub)
        z.writestr("2025q1_REPORTINGOWNER.tsv", own)
        z.writestr("2025q1_NONDERIV_TRANS.tsv", tr)
    buf.seek(0)
    return zipfile.ZipFile(buf)


def test_parse_panel_filters_and_fields() -> None:
    out = _parse_panel("2025q1", _synthetic_zip())
    # XYZ fully removed: amendment + sub-threshold + non-P/S code
    assert set(out["ticker"]) == {"AAPL", "TINY"}
    aapl = out[out["ticker"] == "AAPL"]
    assert len(aapl) == 3                                  # 2 buys + 1 sell
    assert aapl[aapl["code"] == "P"]["usd"].sum() == (1000 + 500) * 150
    assert aapl[aapl["code"] == "S"]["usd"].iloc[0] == 2000 * 150
    ceo = aapl[aapl["rptownercik"] == "1001"].iloc[0]
    assert ceo["is_officer"] and ceo["is_director"] and not ceo["is_tenpct"]
    assert ceo["direct"] and ceo["title"] == "Chief Executive Officer"
    assert aapl[aapl["code"] == "S"].iloc[0]["direct"] == np.False_  # indirect sell
    assert pd.api.types.is_datetime64_any_dtype(out["filing_date"])
    tiny = out[out["ticker"] == "TINY"].iloc[0]
    assert tiny["usd"] == 20000 and not tiny["direct"]    # indirect


def test_quarters_from_oldest_first() -> None:
    qs = _quarters_from("2006q1")
    assert qs[0] == "2006q1"
    assert qs == sorted(qs, key=lambda q: (int(q[:4]), int(q[5])))
    assert len(qs) >= 80                                   # ~20y of quarters


def test_classify_routine_is_causal() -> None:
    # R1 trades every March 2020-2024; O1 trades once.
    rows = [("R1", f"{y}-03-10") for y in range(2020, 2025)] + [("O1", "2024-06-01")]
    panel = pd.DataFrame({
        "rptownercik": [r[0] for r in rows],
        "filing_date": pd.to_datetime([r[1] for r in rows]),
    })
    out = classify_routine(panel).set_index(panel["filing_date"])
    r1 = out[out["rptownercik"] == "R1"]
    # routine only once ≥3 prior same-month years exist: 2023 & 2024 March
    assert bool(r1.loc["2024-03-10", "is_routine"])
    assert bool(r1.loc["2023-03-10", "is_routine"])
    assert not bool(r1.loc["2022-03-10", "is_routine"])   # 2019 March absent
    assert not bool(r1.loc["2020-03-10", "is_routine"])   # no prior history
    assert not bool(out[out["rptownercik"] == "O1"]["is_routine"].iloc[0])


def test_role_weights_ordering() -> None:
    panel = pd.DataFrame({
        "is_officer": [True, True, False, False, False],
        "is_director": [True, False, True, False, False],
        "is_tenpct": [False, False, False, True, False],
        "title": ["Chief Executive Officer", "EVP", "", "", ""],
    })
    w = role_weights(panel).tolist()
    assert w[0] == 1.5    # top officer (CEO)
    assert w[1] == 1.0    # line officer
    assert w[2] == 0.6    # director
    assert w[3] == 0.3    # 10% holder
    assert w[4] == 0.2    # other/unknown


def _signal_panel() -> pd.DataFrame:
    rows = [
        # ticker, code, filing_date, owner, usd, routine
        ("FOO", "P", "2025-01-20", "1", 100_000, False),
        ("FOO", "P", "2025-02-15", "2", 200_000, False),
        ("FOO", "S", "2025-02-20", "3", 50_000, False),
        ("BAR", "P", "2025-02-10", "4", 300_000, True),    # routine — out of opp variants
        ("BAZ", "P", "2025-03-05", "5", 10_000, False),    # extends the month index to March
    ]
    return pd.DataFrame({
        "ticker": [r[0] for r in rows],
        "code": [r[1] for r in rows],
        "filing_date": pd.to_datetime([r[2] for r in rows]),
        "rptownercik": [r[3] for r in rows],
        "usd": [r[4] for r in rows],
        "is_routine": [r[5] for r in rows],
        "is_officer": True, "is_director": False, "is_tenpct": False, "title": "",
    })


def test_build_signals_no_lookahead_and_aggregation() -> None:
    panel = _signal_panel()
    grid = [pd.Timestamp("2025-01-31"), pd.Timestamp("2025-02-28"), pd.Timestamp("2025-03-31")]
    mcap = pd.DataFrame(1e9, index=grid, columns=["FOO", "BAR", "BAZ"])
    sigs = build_signals(panel, grid, mcap=mcap, k_months=6)

    buy = sigs["buy_usd"]
    # PIT: the 15-Feb filing must NOT be visible at the 31-Jan rebalance
    assert buy.loc[grid[0], "FOO"] == 100_000
    assert buy.loc[grid[1], "FOO"] == 300_000              # Jan+Feb within window
    assert buy.loc[grid[2], "FOO"] == 300_000              # window persists into March
    assert buy.loc[grid[0], "BAR"] == 0.0                  # BAR's first buy is in Feb

    assert sigs["n_buyers"].loc[grid[0], "FOO"] == 1
    assert sigs["n_buyers"].loc[grid[1], "FOO"] == 2       # two distinct insiders
    assert sigs["net_usd"].loc[grid[1], "FOO"] == 250_000  # 300k buys − 50k sell

    # opportunistic variant excludes the routine BAR buy — BAR has no opportunistic
    # trade at all, so it drops out of the matrix entirely (= zero contribution; the
    # harness reindexes missing names to 0 before scoring).
    assert sigs["opp_buy_usd"].loc[grid[1], "FOO"] == 300_000
    assert "BAR" not in sigs["opp_buy_usd"].columns

    # size-normalised = net buy $ ÷ market cap
    assert np.isclose(sigs["net_usd_mcap"].loc[grid[1], "FOO"], 250_000 / 1e9)


def test_market_cap_is_causal() -> None:
    grid = [pd.Timestamp("2025-01-31"), pd.Timestamp("2025-02-28")]
    closes_me = pd.DataFrame({"FOO": [10.0, 12.0]}, index=grid)
    shares = pd.DataFrame({
        "ticker": ["FOO", "FOO"],
        "shares": [1_000_000.0, 2_000_000.0],
        "asof_date": pd.to_datetime(["2024-06-01", "2025-02-15"]),
    })
    mc = market_cap(closes_me, shares, grid)
    # Jan uses the only shares figure available then (1M); Feb sees the 15-Feb update (2M)
    assert mc.loc[grid[0], "FOO"] == 10.0 * 1_000_000
    assert mc.loc[grid[1], "FOO"] == 12.0 * 2_000_000
