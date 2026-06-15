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
from scripts.midsmall_pit import reconstruct_intervals  # noqa: E402


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


def test_pit_membership_reconstruction() -> None:
    """Walk-backward reconstruction of index membership from a changes log: closed
    spell for a name that left, floor-start for pre-log members, orphan adds skipped,
    and open intervals reconcile exactly to the current constituents."""
    current = {"AAA", "BBB", "CCC"}
    changes = pd.DataFrame({
        "date": pd.to_datetime(["2023-01-01", "2021-01-01", "2020-01-01"]),
        "add": ["CCC", "YYY", "XXX"],   # YYY = orphan (never current, no later removal)
        "rem": ["XXX", "", ""],
    })
    m, orphan = reconstruct_intervals(current, changes)
    m = m.set_index("ticker")
    assert orphan == 1 and "YYY" not in m.index
    # XXX entered 2020, left 2023 → closed spell
    xxx = m.loc["XXX"]
    assert xxx["start_date"] == pd.Timestamp("2020-01-01")
    assert xxx["end_date"] == pd.Timestamp("2023-01-01")
    # CCC entered 2023 and is still a member
    assert m.loc["CCC", "start_date"] == pd.Timestamp("2023-01-01")
    assert pd.isna(m.loc["CCC", "end_date"])
    # AAA/BBB never appear as "added" → pre-log members, floored to the log start
    assert m.loc["AAA", "start_date"] == pd.Timestamp("2020-01-01")
    assert pd.isna(m.loc["AAA", "end_date"])
    # reconciliation: open spells == current constituents
    assert set(m.index[m["end_date"].isna()]) == current


def test_insider_leaderboard_size_normalised() -> None:
    """The upgraded leaderboard ranks by net buying as a fraction of market cap, so a
    high-conviction small/mid-cap buy outranks a bigger raw-dollar megacap buy."""
    import tempfile

    from engine.equity_factors import _insider_block_panel
    fd = pd.Timestamp("2026-03-15")
    rows = [
        # ticker, code, usd, owner  (all within the trailing window)
        ("BIG", "P", 10_000_000, "1"),   # megacap: big $, tiny % of cap
        ("SML", "P", 5_000_000, "2"),    # small cap: smaller $, large % of cap
        ("SML", "P", 1_000_000, "3"),    # second distinct buyer at SML (cluster)
        ("SEL", "S", 4_000_000, "4"),    # net seller
    ]
    panel = pd.DataFrame({
        "ticker": [r[0] for r in rows], "code": [r[1] for r in rows],
        "usd": [r[2] for r in rows], "rptownercik": [r[3] for r in rows],
        "filing_date": [fd] * len(rows),
    })
    ns = {"BIG": ("Big Co", "Tech"), "SML": ("Small Co", "Industrials"), "SEL": ("Sell Co", "Energy")}
    mktcap = pd.Series({"BIG": 1e12, "SML": 1e9, "SEL": 2e9})
    with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
        panel.to_parquet(f.name)
        blk = _insider_block_panel(ns, mktcap, f.name)
    assert blk["basis"] == "net_mcap_bps"
    buying = blk["top_buying"]
    # SML (50 bps of cap) must rank above BIG (0.1 bps of cap) despite half the dollars
    assert buying[0]["ticker"] == "SML" and buying[1]["ticker"] == "BIG"
    assert buying[0]["n_buyers"] == 2                       # distinct-insider cluster
    assert blk["top_selling"][0]["ticker"] == "SEL"


def test_insider_aggregate_size_normalised_and_legacy() -> None:
    """The single-quarter aggregate path (live in CI, no panel): size-normalises when
    caps are given (basis flag set, cluster False), and falls back to raw net-$ ranking
    without caps."""
    import tempfile

    from engine.equity_factors import _insider_block_aggregate
    agg = pd.DataFrame({
        "buy_usd": [10_000_000.0, 5_000_000.0, 0.0],
        "sell_usd": [0.0, 0.0, 4_000_000.0],
        "n_buys": [1, 2, 0], "n_sells": [0, 0, 3],
        "net_usd": [10_000_000.0, 5_000_000.0, -4_000_000.0],
        "quarter": ["2026q1"] * 3,
    }, index=pd.Index(["BIG", "SML", "SEL"], name="ticker"))
    ns = {"BIG": ("Big Co", "Tech"), "SML": ("Small Co", "Industrials"), "SEL": ("Sell Co", "Energy")}
    mktcap = pd.Series({"BIG": 1e12, "SML": 1e9, "SEL": 2e9})
    with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
        agg.to_parquet(f.name)
        norm = _insider_block_aggregate(ns, mktcap, path=f.name)
        legacy = _insider_block_aggregate(ns, None, path=f.name)
    # size-normalised: SML (50 bps) outranks BIG (0.1 bps); flagged, not a cluster
    assert norm["basis"] == "net_mcap_bps" and norm["cluster"] is False
    assert norm["top_buying"][0]["ticker"] == "SML"
    # legacy: raw dollars rank BIG first, no basis flag
    assert legacy["basis"] is None
    assert legacy["top_buying"][0]["ticker"] == "BIG"


def test_per_stock_chip_panel_and_aggregate() -> None:
    """Per-stock insider chip: panel path gives distinct-insider clusters + net buying
    as % of cap; aggregate fallback size-normalises the single-quarter net-$ too."""
    import tempfile

    from engine.stock_fundamentals import _insider_from_aggregate, _insider_from_panel
    mcap = {"SML": 1e9}   # $1bn cap
    fd = pd.Timestamp("2026-03-15")
    panel = pd.DataFrame({
        "ticker": ["SML", "SML", "SML"],
        "code": ["P", "P", "S"],
        "usd": [3_000_000.0, 2_000_000.0, 1_000_000.0],   # net +$4m = 40 bps of $1bn
        "rptownercik": ["1", "2", "3"],                    # 2 distinct buyers, 1 seller
        "filing_date": [fd, fd, fd],
    })
    with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
        panel.to_parquet(f.name)
        rec = _insider_from_panel(mcap, 6, path=f.name)["SML"]
    assert rec["cluster"] is True
    assert rec["n_buyers"] == 2 and rec["n_sellers"] == 1
    assert rec["net_usd_mn"] == 4.0
    assert rec["net_mcap_bps"] == 40.0           # +$4m / $1bn = 40 bps

    agg = pd.DataFrame({"net_usd": [4_000_000.0], "n_buys": [2], "n_sells": [1],
                        "quarter": ["2026q1"]}, index=pd.Index(["SML"], name="ticker"))
    with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
        agg.to_parquet(f.name)
        arec = _insider_from_aggregate(mcap, path=f.name)["SML"]
    assert arec["cluster"] is False and arec["net_mcap_bps"] == 40.0
    assert arec["n_buys"] == 2 and arec["n_sells"] == 1


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
