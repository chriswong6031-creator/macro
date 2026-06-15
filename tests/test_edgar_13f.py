"""Pure-function tests for the 13F smart-money feature — no network, no parquet.
Mirrors tests/test_pit_fundamentals.py: feed synthetic inputs into the pure
parser / resolver / diff and assert behaviour.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import edgar_13f as e13  # noqa: E402
from engine import smart_money as sm  # noqa: E402


# a real-shaped (namespaced) 13F INFORMATION TABLE with two issuers + a second
# Apple lot that must collapse into one row.
INFO_XML = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
 <infoTable>
  <nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass>
  <cusip>037833100</cusip><value>1000</value>
  <shrsOrPrnAmt><sshPrnamt>100</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
 </infoTable>
 <infoTable>
  <nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass>
  <cusip>037833100</cusip><value>500</value>
  <shrsOrPrnAmt><sshPrnamt>50</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
 </infoTable>
 <infoTable>
  <nameOfIssuer>MICROSOFT CORP</nameOfIssuer><titleOfClass>COM</titleOfClass>
  <cusip>594918104</cusip><value>2000</value>
  <shrsOrPrnAmt><sshPrnamt>20</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
 </infoTable>
</informationTable>"""


def test_parse_information_table():
    df = e13.parse_information_table(INFO_XML)
    assert len(df) == 2                       # two Apple lots collapsed into one
    aapl = df[df["cusip"] == "037833100"].iloc[0]
    assert aapl["issuer"] == "APPLE INC"
    assert aapl["shares"] == 150.0            # 100 + 50
    assert aapl["value_raw"] == 1500.0        # 1000 + 500
    assert aapl["sh_type"] == "SH"
    assert set(df["cusip"]) == {"037833100", "594918104"}


def test_parse_empty_or_coverpage():
    assert e13.parse_information_table("<html><body>not xml</body></html>").empty
    assert e13.parse_information_table("<edgarSubmission><x>1</x></edgarSubmission>").empty


def test_value_units_thousands_vs_dollars():
    # pre-amendment period: value reported in thousands -> *1000
    assert e13.value_to_dollars(1500.0, date(2021, 12, 31)) == 1_500_000.0
    # on/after 2022-12-31: already dollars -> *1
    assert e13.value_to_dollars(1500.0, date(2022, 12, 31)) == 1500.0
    assert e13.value_to_dollars(1500.0, date(2026, 3, 31)) == 1500.0


def test_norm_handles_possessive_connective_abbrev():
    assert sm._norm("Moody's Corp") == "MOODYS"
    assert sm._norm("Bank of America Corp") == "BANK AMERICA"
    assert sm._norm("Capital One Finl Corp") == "CAPITAL ONE FINANCIAL"
    assert sm._norm("Occidental Pete Corp") == "OCCIDENTAL PETROLEUM"
    # domicile tag dropped
    assert sm._norm("Chubb Ltd Switz") == "CHUBB"


def test_name_ticker_map_first_wins():
    mem = pd.DataFrame([
        {"ticker": "GOOGL", "name": "Alphabet Inc. (Class A)", "active": True},
        {"ticker": "GOOG", "name": "Alphabet Inc. (Class C)", "active": True},
        {"ticker": "DROP", "name": "Inactive Co", "active": False},
    ])
    m = sm.name_ticker_map(mem)
    assert m["ALPHABET"] == "GOOGL"           # first active row wins the collision
    assert "INACTIVE" not in m                 # inactive excluded


def test_resolve_tickers_cusip_then_name():
    df = pd.DataFrame([
        {"cusip": "037833100", "issuer": "APPLE INC"},          # via cusip seed
        {"cusip": "ZZZZZZZZZ", "issuer": "Bank of America Corp"},  # via name
        {"cusip": "999999999", "issuer": "Totally Unknown Co"},   # unresolved
    ])
    name_map = {"BANK AMERICA": "BAC"}
    cusip_map = {"037833100": "AAPL"}
    out = sm.resolve_tickers(df, name_map, cusip_map)
    got = out["ticker"].tolist()
    assert got[0] == "AAPL" and got[1] == "BAC"
    assert pd.isna(got[2])                     # unresolved -> missing (None/nan)
    assert out["ticker"].notna().sum() == 2


def _snap(rows, sh_type="SH"):
    return pd.DataFrame([
        {"cusip": c, "issuer": i, "shares": s, "value_usd": v, "sh_type": sh_type}
        for c, i, s, v in rows])


def test_diff_snapshots_classifies_actions():
    prev = _snap([
        ("A", "Alpha Co", 100, 100), ("B", "Beta Co", 100, 100),
        ("C", "Gamma Co", 100, 100), ("E", "Exit Co", 100, 100)])
    latest = _snap([
        ("A", "Alpha Co", 100, 100),    # unchanged -> hold
        ("B", "Beta Co", 130, 130),     # +30% -> add
        ("C", "Gamma Co", 70, 70),      # -30% -> trim
        ("D", "Delta Co", 100, 100)])   # brand new -> new ; E missing -> exit
    out = sm.diff_snapshots(prev, latest).set_index("cusip")
    assert out.loc["A", "action"] == "hold"
    assert out.loc["B", "action"] == "add"
    assert out.loc["C", "action"] == "trim"
    assert out.loc["D", "action"] == "new"
    assert out.loc["E", "action"] == "exit"
    assert out.loc["E", "shares_change_pct"] == -100.0
    # pct_portfolio sums to ~100 over the latest (non-exit) book
    live = out[out["action"] != "exit"]
    assert abs(live["pct_portfolio"].sum() - 100.0) < 1e-6


def test_diff_drops_non_equity_prn():
    latest = _snap([("A", "Alpha Co", 100, 100)], sh_type="PRN")  # a bond line
    out = sm.diff_snapshots(None, latest)
    assert out.empty


# ---- cross-fund VIP / overlap (display-only context) ------------------------

def _holder(fund, action, pct, value):
    return {"fund": fund, "action": action, "pct_portfolio": pct, "value_usd": value}


def test_overlap_stats_vip_and_concentration():
    # 3 funds currently hold (one exited -> excluded from the VIP count).
    holders = [
        _holder("A", "hold", 10.0, 600.0),
        _holder("B", "add", 4.0, 300.0),
        _holder("C", "new", 2.0, 100.0),
        _holder("D", "exit", 0.0, 999.0),     # exited -> not a current holder
    ]
    o = sm.overlap_stats(holders)
    assert o["vip"] == 3                        # exits excluded
    assert o["max_book_pct"] == 10.0           # top-conviction holder's weight
    assert o["avg_book_pct"] == round((10 + 4 + 2) / 3, 2)   # rounded to 2dp
    # HHI of value shares 0.6/0.3/0.1 = .36+.09+.01 = .46
    assert abs(o["ownership_hhi"] - 0.46) < 1e-3


def test_overlap_stats_vip_threshold_and_empty():
    many = [_holder(f"F{i}", "hold", 1.0, 100.0) for i in range(5)]
    assert sm.overlap_stats(many)["is_vip"] is True          # >= _VIP_MIN
    assert sm.overlap_stats(many[:2])["is_vip"] is False
    assert sm.overlap_stats([_holder("X", "exit", 0.0, 1.0)]) == {"vip": 0}
