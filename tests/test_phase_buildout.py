"""Tests for the four-phase factor build-out (research/QUANT_FACTOR_EXPANSION.md):
commodity carry, EIA supply, FINRA short interest, SEC Form-4 insider.

Pure-logic tests run offline; integration checks run only when a real cache
exists in this environment."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.commodity_carry import _enumerate_symbols, _reconstruct  # noqa: E402
from collectors.finra import _candidate_dates, _last_business_day  # noqa: E402
from collectors.sec_insider import _candidate_quarters  # noqa: E402
from lib import config  # noqa: E402


# --- Phase 1: commodity carry -----------------------------------------------
def _contract(deliv_y: int, deliv_m: int, level: float, n: int = 120) -> tuple[int, int, pd.Series]:
    idx = pd.bdate_range("2026-01-02", periods=n)
    return (deliv_y, deliv_m, pd.Series(level, index=idx, dtype=float))


def test_carry_reconstruct_backwardation() -> None:
    # front (Jul) priced ABOVE second (Aug) => positive roll yield (backwardation)
    contracts = [_contract(2026, 7, 85.0), _contract(2026, 8, 83.0), _contract(2026, 9, 81.0)]
    df = _reconstruct(contracts, history_d=200)
    assert not df.empty and "roll_yield_ann" in df.columns
    assert df["roll_yield_ann"].iloc[-1] > 0           # backwardated
    assert df["front"].iloc[-1] == 85.0 and df["second"].iloc[-1] == 83.0


def test_carry_reconstruct_contango() -> None:
    contracts = [_contract(2026, 7, 80.0), _contract(2026, 8, 82.0)]  # front below second
    df = _reconstruct(contracts, history_d=200)
    assert df["roll_yield_ann"].iloc[-1] < 0           # contango


def test_carry_reconstruct_needs_two() -> None:
    assert _reconstruct([_contract(2026, 7, 80.0)], 200).empty


def test_enumerate_symbols_format() -> None:
    syms = _enumerate_symbols("CL", ".NYM", 2, 2)
    assert len(syms) == 5
    assert all(re.match(r"CL[FGHJKMNQUVXZ]\d\d\.NYM", s) for s, _, _ in syms)


# --- Phase 3: FINRA short interest ------------------------------------------
def test_last_business_day_skips_weekend() -> None:
    import datetime as dt
    assert _last_business_day(dt.date(2026, 5, 17)) == dt.date(2026, 5, 15)  # Sun -> Fri
    assert _last_business_day(dt.date(2026, 5, 15)).weekday() < 5


def test_finra_candidate_dates_descending() -> None:
    dates = _candidate_dates(6)
    assert len(dates) == 6
    assert dates == sorted(dates, reverse=True)
    assert all(re.match(r"\d{4}-\d{2}-\d{2}", d) for d in dates)


# --- Phase 4: SEC insider ----------------------------------------------------
def test_insider_parse_synthetic() -> None:
    """Parse a synthetic SEC insider zip (real SUBMISSION/NONDERIV_TRANS schema):
    open-market P/S only, min-trade and universe filters, net aggregation."""
    import io
    import zipfile

    from collectors.sec_insider import _parse
    sub = ("ACCESSION_NUMBER\tFILING_DATE\tISSUERTRADINGSYMBOL\tISSUERNAME\n"
           "0001-A\t01-APR-2026\tAAPL\tApple Inc\n"
           "0002-A\t02-APR-2026\tAAPL\tApple Inc\n"
           "0003-A\t03-APR-2026\tXYZ\tXyz Corp\n"
           "0004-A\t04-APR-2026\tTINY\tTiny Co\n")
    tr = ("ACCESSION_NUMBER\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD\n"
          "0001-A\tP\t10000\t150\tA\n"
          "0001-A\tP\t5000\t150\tA\n"
          "0002-A\tS\t8000\t150\tD\n"
          "0003-A\tS\t20000\t50\tD\n"
          "0003-A\tA\t999999\t50\tA\n"      # grant — must be excluded
          "0004-A\tP\t1000\t5\tA\n")        # $5k < min_trade_usd — must be dropped
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("2026q1_SUBMISSION.tsv", sub)
        z.writestr("2026q1_NONDERIV_TRANS.tsv", tr)
    buf.seek(0)
    out = _parse("2026q1", zipfile.ZipFile(buf), universe={"AAPL", "XYZ", "TINY"})
    assert out.loc["AAPL", "buy_usd"] == 15000 * 150
    assert out.loc["AAPL", "sell_usd"] == 8000 * 150
    assert out.loc["AAPL", "net_usd"] == (15000 - 8000) * 150
    assert out.loc["AAPL", "n_buys"] == 2 and out.loc["AAPL", "n_sells"] == 1
    assert out.loc["XYZ", "buy_usd"] == 0 and out.loc["XYZ", "sell_usd"] == 20000 * 50  # grant excluded
    assert "TINY" not in out.index                                                       # sub-threshold dropped


def test_insider_candidate_quarters() -> None:
    qs = _candidate_quarters(5)
    assert len(qs) == 5
    assert all(re.match(r"\d{4}q[1-4]", q) for q in qs)
    # strictly newest-first (each subsequent quarter is earlier)
    ords = [int(q[:4]) * 4 + int(q[-1]) for q in qs]
    assert ords == sorted(ords, reverse=True)


# --- integration checks (only if a real cache exists) -----------------------
def test_short_interest_factor_if_cache() -> None:
    if not (config.data_dir() / "finra" / "short_interest.parquet").exists():
        return
    from engine.equity_factors import compute_factors
    r = compute_factors()
    if r:
        assert "short_interest" in r["leaders"]
        # least-shorted leaders should have a positive factor z
        assert r["leaders"]["short_interest"][0]["z"] > 0


def test_eia_supply_read_if_cache() -> None:
    if not (config.data_dir() / "eia" / "crude_stocks.parquet").exists():
        return
    from scripts.build_commodities import _oil_supply_read
    s = _oil_supply_read()
    assert s is not None
    assert s["crude_stocks_mb"] > 0                                  # M bbl
    assert s["balance_word"] in ("tight", "ample", "balanced", "n/a")
    assert s["crude_z"] is None or isinstance(s["crude_z"], float)   # seasonal anomaly z
    assert s["caveat_en"] and "≠" in s["caveat_en"]                  # display-only honesty layer


def test_carry_read_if_cache() -> None:
    if not (config.data_dir() / "commodity_carry" / "oil.parquet").exists():
        return
    from scripts.build_commodities import _carry_read
    c = _carry_read("oil")
    assert c is not None and c["state"] in ("backwardation", "contango")
