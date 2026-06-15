"""Pure-function tests for the Treasury supply-absorption leaf — no network."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import treasury_auctions as ta  # noqa: E402
from engine import treasury_supply as ts  # noqa: E402

_CFG = {"trailing": 8, "min_trailing": 5, "strong_z": 0.6, "recent": 10, "mix_window_days": 90}


# --------------------------------------------------------------------------- #
# collector — pure parsing
# --------------------------------------------------------------------------- #
def test_term_years():
    assert ta.term_years("9-Year 11-Month") == round(9 + 11 / 12, 4)
    assert ta.term_years("2-Year") == 2.0
    assert ta.term_years("26-Week") == 0.5
    assert ta.term_years("4-Week") == round(4 / 52, 4)
    assert ta.term_years("") is None
    assert ta.term_years("junk") is None


def test_bench_tenor():
    assert ta.bench_tenor(9.917) == 10        # 9y11m note -> 10y benchmark
    assert ta.bench_tenor(19.917) == 20
    assert ta.bench_tenor(6.5) == 7
    assert ta.bench_tenor(0.5) is None        # bills have no coupon-tenor bucket
    assert ta.bench_tenor(None) is None


def test_parse_record_nominal():
    rec = {"cusip": "91282CQQ7", "auctionDate": "2026-06-10T00:00:00", "type": "Note",
           "securityType": "Note", "securityTerm": "9-Year 11-Month", "reopening": "No",
           "highYield": "4.5380", "bidToCoverRatio": "2.57", "totalAccepted": "39000001000",
           "primaryDealerAccepted": "3683175000", "indirectBidderAccepted": "30435505400"}
    row = ta.parse_record(rec)
    assert row["klass"] == "Note" and row["tenor"] == 10
    assert row["bid_to_cover"] == 2.57
    assert row["high_yield"] == 4.538
    assert row["auction_date"] == pd.Timestamp("2026-06-10")


def test_parse_record_classifies_tips_and_frn_by_type_not_securitytype():
    # the API labels TIPS / FRN with securityType "Note"/"Bond" — `type` is canonical
    tips = ta.parse_record({"cusip": "X1", "auctionDate": "2026-05-22", "type": "TIPS",
                            "securityType": "Note", "securityTerm": "9-Year 8-Month",
                            "highYield": "", "highInvestmentRate": "2.10", "bidToCoverRatio": "2.5"})
    frn = ta.parse_record({"cusip": "X2", "auctionDate": "2026-04-30", "type": "FRN",
                           "securityType": "Note", "securityTerm": "1-Year 11-Month"})
    assert tips["klass"] == "TIPS" and frn["klass"] == "FRN"
    # bills/TIPS carry yield in highInvestmentRate, not highYield -> fallback
    assert tips["high_yield"] == 2.10


def test_parse_record_rejects_missing_key_fields():
    assert ta.parse_record({"auctionDate": "2026-06-10"}) is None        # no cusip
    assert ta.parse_record({"cusip": "A", "auctionDate": ""}) is None    # no date
    assert ta.parse_record({"cusip": "A", "auctionDate": "not-a-date"}) is None


# --------------------------------------------------------------------------- #
# engine — z-scores, tags, supply trend
# --------------------------------------------------------------------------- #
def _auction(d, tenor, klass="Note", btc=2.5, ind=0.70, dlr=0.10, total=100e9):
    return {"auction_date": pd.Timestamp(d), "cusip": f"C{d}{tenor}{klass}", "klass": klass,
            "security_type": "Note" if klass in ("Note", "FRN", "TIPS") else klass,
            "security_term": f"{tenor}-Year", "tenor_years": None if tenor is None else float(tenor),
            "tenor": tenor, "reopening": False, "bid_to_cover": btc, "total_accepted": total,
            "indirect_accepted": ind * total, "primary_dealer_accepted": dlr * total,
            "high_yield": 4.0, "interest_rate": 4.0}


def _baseline(tenor, n=8, start="2026-01-05"):
    """n same-tenor auctions with mild variance so the z-score denominator is finite."""
    rng = np.linspace(-1, 1, n)
    dates = pd.bdate_range(start, periods=n, freq="7D")
    return [_auction(d.date(), tenor, btc=2.5 + 0.05 * x, ind=0.70 + 0.02 * x,
                     dlr=0.10 + 0.01 * x) for d, x in zip(dates, rng)]


def test_compute_flags_soft_auction():
    rows = _baseline(10)
    rows.append(_auction("2026-04-01", 10, btc=2.15, ind=0.52, dlr=0.18))  # weak: low cover/indirect, high dealer
    out = ts.compute(pd.DataFrame(rows), _CFG)
    newest = out["rows"][0]
    assert newest["date"] == "2026-04-01"
    assert newest["tag"] == "soft" and newest["absorption_z"] < 0
    assert out["n_soft"] >= 1


def test_compute_flags_strong_auction():
    rows = _baseline(10)
    rows.append(_auction("2026-04-01", 10, btc=2.85, ind=0.82, dlr=0.05))  # strong demand
    out = ts.compute(pd.DataFrame(rows), _CFG)
    newest = out["rows"][0]
    assert newest["tag"] == "strong" and newest["absorption_z"] > 0


def test_tips_excluded_from_nominal_buckets():
    # a wild TIPS row at tenor 10 must NOT pollute the nominal 10y z-score / appear in rows
    rows = _baseline(10)
    rows.append(_auction("2026-03-20", 10, klass="TIPS", btc=9.9, ind=0.01, dlr=0.9))
    rows.append(_auction("2026-04-01", 10, btc=2.5, ind=0.70, dlr=0.10))   # in-line nominal
    out = ts.compute(pd.DataFrame(rows), _CFG)
    assert all(r["type"] in ("Note", "Bond") for r in out["rows"])         # no TIPS shown
    newest = out["rows"][0]
    assert newest["date"] == "2026-04-01" and newest["tag"] == "in-line"   # TIPS didn't skew it


def test_supply_trend_detects_rising_coupon_issuance():
    # end = 2026-06-01; recent 90d window (Mar 3..Jun 1] heavy, prior (Dec 3..Mar 3] light
    prior = ["2025-12-20", "2026-01-02", "2026-01-12", "2026-01-21", "2026-01-31", "2026-02-10"]
    recent = ["2026-04-13", "2026-04-22", "2026-05-01", "2026-05-12", "2026-05-22", "2026-06-01"]
    rows = [_auction(d, 10, total=50e9) for d in prior] + [_auction(d, 10, total=90e9) for d in recent]
    out = ts.compute(pd.DataFrame(rows), _CFG)
    assert out["supply"]["pressure"] == "coupon supply rising"
    assert out["supply"]["coupon_chg_pct"] > 10


def test_compute_graceful_on_empty_and_bills_only():
    assert ts.compute(pd.DataFrame(), _CFG) is None
    assert ts.compute(None, _CFG) is None
    bills = pd.DataFrame([_auction("2026-06-01", None, klass="Bill", total=70e9)])
    assert ts.compute(bills, _CFG) is None          # no nominal coupons -> nothing to score


def test_note_present_and_marks_display_only():
    rows = _baseline(10) + [_auction("2026-04-01", 10)]
    out = ts.compute(pd.DataFrame(rows), _CFG)
    assert "never scored" in out["note_en"].lower()
    assert "when-issued" in out["note_en"].lower()   # the tail-omission honesty
