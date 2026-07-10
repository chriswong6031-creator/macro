"""Pure-function tests for the 13F smart-money feature — no network, no parquet.
Mirrors tests/test_pit_fundamentals.py: feed synthetic inputs into the pure
parser / resolver / diff and assert behaviour.
"""
import sys
import unittest.mock as mock
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

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


def _series(*holder_counts, vals=None):
    vals = vals or [c * 100.0 for c in holder_counts]
    return [{"period": f"2024-{3*(i+1):02d}-31", "n_funds": c, "value_usd": v}
            for i, (c, v) in enumerate(zip(holder_counts, vals))]


def test_accumulation_trend_holder_count_drives_direction():
    up = sm.accumulation_trend(_series(2, 3, 4, 5))
    assert up["direction"] == "accumulating"
    assert up["holders_first"] == 2 and up["holders_last"] == 5
    assert up["holders_delta"] == 3 and up["n_quarters"] == 4
    assert up["holders_series"] == [2, 3, 4, 5]

    down = sm.accumulation_trend(_series(6, 6, 4, 3))
    assert down["direction"] == "distributing" and down["holders_delta"] == -3

    # trailing exit-to-zero is the signal — must NOT read as "stable"
    exited = sm.accumulation_trend(_series(3, 3, 3, 0))
    assert exited["direction"] == "distributing"
    assert exited["holders_last"] == 0 and exited["holders_delta"] == -3


def test_accumulation_trend_value_breaks_holder_ties():
    flat_up = sm.accumulation_trend(_series(3, 3, 3, vals=[100.0, 150.0, 200.0]))
    assert flat_up["direction"] == "accumulating"          # +100% value, holders flat
    assert flat_up["value_change_pct"] == 100.0
    flat_down = sm.accumulation_trend(_series(3, 3, vals=[200.0, 100.0]))
    assert flat_down["direction"] == "distributing"        # -50% value
    flat_stable = sm.accumulation_trend(_series(3, 3, vals=[100.0, 105.0]))
    assert flat_stable["direction"] == "stable"            # +5% < threshold


def test_accumulation_trend_needs_two_real_quarters():
    assert sm.accumulation_trend(_series(4)) is None       # one point
    assert sm.accumulation_trend([]) is None
    # leading empty quarters (name not yet held) are dropped before the >=2 check
    assert sm.accumulation_trend(
        [{"period": "2024-03-31", "n_funds": 0, "value_usd": 0.0},
         {"period": "2024-06-31", "n_funds": 0, "value_usd": 0.0},
         {"period": "2024-09-31", "n_funds": 2, "value_usd": 200.0}]) is None


def test_accumulation_trend_emits_lookahead_free_as_of():
    # filing dates lag quarter-end ~45d — the trend must surface the FILING date
    # as `available_on`, never the quarter-end, so a scorer can't peek ahead.
    s = [{"period": "2024-03-31", "n_funds": 2, "value_usd": 100.0, "filing_date": "2024-05-15"},
         {"period": "2024-06-30", "n_funds": 4, "value_usd": 200.0, "filing_date": "2024-08-14"}]
    tr = sm.accumulation_trend(s)
    assert tr["to_period"] == "2024-06-30"                 # quarter-end (display)
    assert tr["available_on"] == "2024-08-14"              # PUBLIC filing date (scoring)
    assert tr["available_on_first"] == "2024-05-15"
    assert tr["available_on"] > tr["to_period"]            # filing strictly after quarter-end


def test_as_of_for_scoring_contract():
    s = [{"period": "2024-03-31", "n_funds": 2, "value_usd": 100.0, "filing_date": "2024-05-15"},
         {"period": "2024-06-30", "n_funds": 3, "value_usd": 150.0, "filing_date": "2024-08-14"}]
    assert sm.as_of_for_scoring(sm.accumulation_trend(s)) == "2024-08-14"
    assert sm.as_of_for_scoring(None) is None
    # legacy snapshots w/o filing_date -> no as-of -> trend must NOT be scored
    assert sm.as_of_for_scoring(sm.accumulation_trend(_series(2, 3))) is None


def test_smart_money_trend_never_keys_scoring_on_quarter_end():
    """Guard the look-ahead contract: as_of_for_scoring must return the filing date,
    which is strictly later than the quarter-end `to_period`. A regression that made
    scoring key on `to_period` would surface here."""
    s = [{"period": "2024-09-30", "n_funds": 1, "value_usd": 50.0, "filing_date": "2024-11-14"},
         {"period": "2024-12-31", "n_funds": 2, "value_usd": 120.0, "filing_date": "2025-02-14"}]
    tr = sm.accumulation_trend(s)
    asof = sm.as_of_for_scoring(tr)
    assert asof == "2025-02-14" and asof != tr["to_period"] and asof > tr["to_period"]


# ---- 13F-HR/A amendment support (SM2-R7) ------------------------------------

# Synthetic submissions JSON containing both 13F-HR and 13F-HR/A rows
_SUBMISSIONS_WITH_AMENDMENTS = {
    "name": "TEST FUND LLC",
    "filings": {
        "recent": {
            "form": [
                "13F-HR/A",    # amendment to Q1 2026
                "13F-HR",      # Q1 2026 original
                "13F-HR/A",    # amendment to Q4 2025
                "13F-HR",      # Q4 2025 original
                "13F-HR",      # Q3 2025 (no amendment)
                "13F-NT",      # notice only — must be excluded
            ],
            "accessionNumber": [
                "0001234567-26-000010",
                "0001234567-26-000005",
                "0001234567-25-000020",
                "0001234567-25-000015",
                "0001234567-25-000008",
                "0001234567-25-000003",
            ],
            "reportDate": [
                "2026-03-31",
                "2026-03-31",
                "2025-12-31",
                "2025-12-31",
                "2025-09-30",
                "2025-09-30",
            ],
            "filingDate": [
                "2026-05-20",
                "2026-05-15",
                "2026-02-18",
                "2026-02-14",
                "2025-11-14",
                "2025-11-13",
            ],
        }
    },
}


def test_list_13f_separates_originals_and_amendments():
    """_list_13f must return (originals_list, amendments_list) with 13F-NT excluded."""
    from collectors import edgar as _edgar  # noqa: PLC0415
    adapter = e13.Edgar13FAdapter.__new__(e13.Edgar13FAdapter)

    with mock.patch("collectors.edgar_13f._get_json", return_value=_SUBMISSIONS_WITH_AMENDMENTS), \
         mock.patch.object(_edgar, "_cfg", return_value={"retries": 3}), \
         mock.patch("collectors.edgar_13f.time.sleep"):
        originals, amendments = adapter._list_13f(1234567)

    # 3 originals: Q1 2026, Q4 2025, Q3 2025 (13F-NT excluded)
    assert len(originals) == 3
    orig_periods = [r["period_end"] for r in originals]
    assert orig_periods == ["2026-03-31", "2025-12-31", "2025-09-30"]  # newest-first

    # 2 amendments: Q1 2026 /A and Q4 2025 /A
    assert len(amendments) == 2
    amend_periods = [r["period_end"] for r in amendments]
    assert "2026-03-31" in amend_periods
    assert "2025-12-31" in amend_periods
    # 13F-NT must NOT appear in either list
    all_periods = orig_periods + amend_periods
    assert "2025-09-30" not in amend_periods  # Q3 has no amendment


def test_amendment_file_naming_and_pathing(tmp_path):
    """Amendments must be written to amendments/<period_end>__<filing_date>.parquet."""
    slug = "testfund"
    spec = {"cik": 1234567, "name": "Test Fund LLC"}

    adapter = e13.Edgar13FAdapter.__new__(e13.Edgar13FAdapter)
    adapter.cfg = {"enabled": True, "history_quarters": 4, "backfill_quarters": 5}
    adapter.dir = tmp_path

    # One original (Q1 2026) + one amendment (Q1 2026 /A)
    originals = [{"accession": "0001234567-26-000005",
                  "period_end": "2026-03-31", "filing_date": "2026-05-15"}]
    amendments = [{"accession": "0001234567-26-000010",
                   "period_end": "2026-03-31", "filing_date": "2026-05-20"}]

    # Minimal info table XML for the fetch
    fake_idx = {"directory": {"item": [{"name": "infotable.xml"}]}}
    fake_xml = INFO_XML

    with mock.patch.object(adapter, "_list_13f", return_value=(originals, amendments)), \
         mock.patch("collectors.edgar_13f._get_json", return_value=fake_idx), \
         mock.patch.object(adapter, "_get_text", return_value=fake_xml), \
         mock.patch("collectors.edgar_13f.time.sleep"):
        written = adapter._fetch_fund(slug, spec, keep=4)

    fund_dir = tmp_path / slug
    # Original: top-level parquet
    assert (fund_dir / "2026-03-31.parquet").exists(), "original must be at top-level"
    # Amendment: in amendments/ subdir with period_end__filing_date naming
    amend_file = fund_dir / "amendments" / "2026-03-31__2026-05-20.parquet"
    assert amend_file.exists(), f"amendment file not found at {amend_file}"
    assert written == 2  # original + amendment both written


def test_amendment_immutability_skip(tmp_path):
    """If an amendment file already exists, it must be skipped (immutability)."""
    slug = "testfund"
    spec = {"cik": 1234567, "name": "Test Fund LLC"}

    adapter = e13.Edgar13FAdapter.__new__(e13.Edgar13FAdapter)
    adapter.cfg = {"enabled": True, "history_quarters": 4, "backfill_quarters": 5}
    adapter.dir = tmp_path

    originals = [{"accession": "0001234567-26-000005",
                  "period_end": "2026-03-31", "filing_date": "2026-05-15"}]
    amendments = [{"accession": "0001234567-26-000010",
                   "period_end": "2026-03-31", "filing_date": "2026-05-20"}]

    # Pre-create both files to simulate "already fetched"
    fund_dir = tmp_path / slug
    fund_dir.mkdir()
    dummy = pd.DataFrame([{"cusip": "X", "val": 1}])

    orig_file = fund_dir / "2026-03-31.parquet"
    dummy.to_parquet(orig_file)

    amend_dir = fund_dir / "amendments"
    amend_dir.mkdir()
    amend_file = amend_dir / "2026-03-31__2026-05-20.parquet"
    dummy.to_parquet(amend_file)

    call_count = {"n": 0}

    def fake_fetch(cik, slug, name, f):
        call_count["n"] += 1
        return dummy.copy()

    with mock.patch.object(adapter, "_list_13f", return_value=(originals, amendments)), \
         mock.patch.object(adapter, "_fetch_filing", side_effect=fake_fetch), \
         mock.patch("collectors.edgar_13f.time.sleep"):
        written = adapter._fetch_fund(slug, spec, keep=4)

    assert written == 0, "nothing should be written when files already exist"
    assert call_count["n"] == 0, "_fetch_filing must not be called for existing files"


def test_amendments_outside_kept_window_are_skipped(tmp_path):
    """Amendments whose period_end is not in the kept-quarters window must be skipped."""
    slug = "testfund"
    spec = {"cik": 1234567, "name": "Test Fund LLC"}

    adapter = e13.Edgar13FAdapter.__new__(e13.Edgar13FAdapter)
    adapter.cfg = {"enabled": True, "history_quarters": 4, "backfill_quarters": 5}
    adapter.dir = tmp_path

    # keep=1 means only Q1 2026 is retained
    originals = [{"accession": "0001234567-26-000005",
                  "period_end": "2026-03-31", "filing_date": "2026-05-15"}]
    # Amendment for Q4 2025 — outside the window since keep=1
    amendments = [{"accession": "0001234567-25-000020",
                   "period_end": "2025-12-31", "filing_date": "2026-02-18"}]

    fake_idx = {"directory": {"item": [{"name": "infotable.xml"}]}}

    with mock.patch.object(adapter, "_list_13f", return_value=(originals, amendments)), \
         mock.patch("collectors.edgar_13f._get_json", return_value=fake_idx), \
         mock.patch.object(adapter, "_get_text", return_value=INFO_XML), \
         mock.patch("collectors.edgar_13f.time.sleep"):
        written = adapter._fetch_fund(slug, spec, keep=1)

    fund_dir = tmp_path / slug
    assert (fund_dir / "2026-03-31.parquet").exists()         # original present
    amend_dir = fund_dir / "amendments"
    if amend_dir.exists():
        outside_files = list(amend_dir.glob("2025-12-31*.parquet"))
        assert len(outside_files) == 0, "amendment outside kept window must not be written"
