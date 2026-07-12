"""Pure-logic tests for the unified engine.event_calendar — no network.

Network paths (TreasuryDirect auctions, FRED release/dates) are stubbed so the suite
is hermetic and deterministic. We assert: the date arithmetic, the two latent bugs
the unification fixes (FOMC SEP meetings; published-vs-naive jobs dates), the FRED
synthetic-scaffold parser, scope routing (macro vs commodity), the DISPLAY-only
impact tier, and the no-event-risk-dampener contract.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import event_calendar as ec  # noqa: E402

T = date(2026, 6, 14)


def _no_auctions(monkeypatch):
    """Stub the keyless TreasuryDirect fetch so tests never touch the network."""
    monkeypatch.setattr(ec, "_fetch_upcoming_auctions", lambda today: [])


# --------------------------------------------------------------------------- #
# date arithmetic
# --------------------------------------------------------------------------- #
def test_first_and_third_friday():
    assert ec.first_friday(2026, 5) == date(2026, 5, 1)
    assert ec.first_friday(2026, 7) == date(2026, 7, 3)
    assert ec.third_friday(2026, 6) == date(2026, 6, 19)
    assert ec.third_friday(2026, 1) == date(2026, 1, 16)


def test_quad_witching():
    assert ec.is_quad_witching(date(2026, 6, 19)) is True       # 3rd Fri of June
    assert ec.is_quad_witching(date(2026, 7, 17)) is False      # July not a quarter-end
    assert ec.is_quad_witching(date(2026, 6, 12)) is False      # 2nd Friday


def test_nth_business_day():
    # June 2026: the 1st is a Monday -> 1st bday = Jun 1, 3rd bday = Jun 3
    assert ec.nth_business_day(2026, 6, 1) == date(2026, 6, 1)
    assert ec.nth_business_day(2026, 6, 3) == date(2026, 6, 3)
    # Aug 2026: the 1st is a Saturday -> 1st bday = Mon Aug 3
    assert ec.nth_business_day(2026, 8, 1) == date(2026, 8, 3)


# --------------------------------------------------------------------------- #
# the two bugs the unification fixes
# --------------------------------------------------------------------------- #
def test_fomc_sep_meetings_are_mar_jun_sep_dec(monkeypatch):
    """The old macro copy flagged Jan/Apr/Jul/Oct as SEP; the correct dot-plot
    meetings are Mar/Jun/Sep/Dec. The unified source must agree with reality."""
    _no_auctions(monkeypatch)
    ev = next(e for e in ec.us_macro_events(date(2026, 6, 1), 30, use_fred=False)
              if e["type"] == "FOMC")
    assert ev["date"] == "2026-06-17"
    assert "SEP" in ev["label"] and "dot-plot" in ev["label"]
    # a non-SEP meeting carries no dot-plot tag
    ev2 = next(e for e in ec.us_macro_events(date(2026, 4, 1), 40, use_fred=False)
               if e["type"] == "FOMC")
    assert ev2["date"] == "2026-04-29" and "SEP" not in ev2["label"]


def test_jobs_report_uses_published_not_naive_first_friday(monkeypatch):
    """April's jobs report prints 2026-05-08, NOT the naive first Friday 2026-05-01.
    The old first-Friday arithmetic would have shown the wrong date."""
    _no_auctions(monkeypatch)
    nfp = [e for e in ec.us_macro_events(date(2026, 5, 1), 14, use_fred=False)
           if e["type"] == "NFP"]
    assert nfp and nfp[0]["date"] == "2026-05-08"
    assert date(2026, 5, 1).strftime("%A") == "Friday"          # the naive trap


# --------------------------------------------------------------------------- #
# us_macro_events: shape, window, impact, context-only
# --------------------------------------------------------------------------- #
def test_us_macro_events_shape_and_window(monkeypatch):
    _no_auctions(monkeypatch)
    evs = ec.us_macro_events(T, 14, use_fred=False)
    assert evs, "expected FOMC/GDP/PCE/claims in mid-June 2026"
    end = date(2026, 6, 28)
    for e in evs:
        assert {"type", "date", "time_et", "label", "impact", "is_context_only"} <= set(e)
        assert e["is_context_only"] is True
        assert T <= date.fromisoformat(e["date"]) <= end
        assert e["impact"] in ("high", "med")
    assert evs == sorted(evs, key=lambda c: (c["date"], c["time_et"] or "99:99"))
    types = {e["type"] for e in evs}
    assert {"FOMC", "GDP", "PCE", "CLAIMS", "OPEX"} <= types


def test_no_event_risk_score_field(monkeypatch):
    """Contract guard: events are scheduling context only — they must NOT carry any
    score / weight / dampener field that could leak into the conviction path."""
    _no_auctions(monkeypatch)
    banned = {"score", "weight", "dampener", "risk_mult", "penalty", "exposure"}
    for e in ec.us_macro_events(T, 30, use_fred=False):
        assert banned.isdisjoint(e.keys())


# --------------------------------------------------------------------------- #
# high-impact strip + LLM line
# --------------------------------------------------------------------------- #
def test_high_impact_strip(monkeypatch):
    _no_auctions(monkeypatch)
    strip = ec.high_impact_strip(T, 14)
    assert strip and all(s["impact"] == "high" for s in strip)
    # auctions/claims/opex (med) are excluded from the strip
    assert all(s["type"] not in ("AUCTION", "CLAIMS", "OPEX", "ISM_MFG") for s in strip)
    for s in strip:
        assert s["dow"] in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        assert s["md"] and s["is_context_only"] is True
    assert any(s["type"] == "FOMC" and s["md"] == "Jun 17" for s in strip)


def test_imminent_line_for_llm(monkeypatch):
    _no_auctions(monkeypatch)
    line = ec.imminent_line(T, 14)
    assert line.startswith("Imminent US catalysts")
    assert "FOMC" in line and "Jun 17" in line
    # empty window -> empty string (degrade quietly, no fabricated context)
    assert ec.imminent_line(date(2026, 7, 6), 3) == ""


# --------------------------------------------------------------------------- #
# commodity scope
# --------------------------------------------------------------------------- #
def test_commodity_events_scope():
    evs = ec.commodity_events(date(2026, 6, 13), 14)
    types = {e["type"] for e in evs}
    assert "FOMC" in types and "EIA_WPSR" in types
    assert "CPI" not in types and "AUCTION" not in types        # macro-only types excluded
    for e in evs:
        assert e["is_context_only"] is True and e.get("assets")


# --------------------------------------------------------------------------- #
# FRED synthetic scaffold (FRED needs a key + is sandbox-unreachable)
# --------------------------------------------------------------------------- #
def test_parse_fred_release_dates_synthetic():
    payload = {"release_dates": [
        {"release_id": 10, "date": "2026-06-10"},    # in window
        {"release_id": 10, "date": "2026-07-14"},    # out of window
        {"release_id": 10, "date": "2026-06-01"},    # before today
        {"release_id": 10, "date": "not-a-date"},    # malformed -> skipped
    ]}
    got = ec.parse_fred_release_dates(payload, date(2026, 6, 5), date(2026, 6, 30))
    assert got == [date(2026, 6, 10)]
    assert ec.parse_fred_release_dates({}, T, T) == []          # degrade on empty


def test_fred_override_used_when_reachable(monkeypatch):
    """When FRED returns dates, they REPLACE the static schedule for that release."""
    _no_auctions(monkeypatch)
    monkeypatch.setattr(ec, "_fred_release_dates",
                        lambda rid, today, end: [date(2026, 6, 20)] if rid == 10 else None)
    cpi = [e for e in ec.us_macro_events(T, 14, use_fred=True) if e["type"] == "CPI"]
    assert len(cpi) == 1 and cpi[0]["date"] == "2026-06-20" and cpi[0]["source"] == "fred"


# --------------------------------------------------------------------------- #
# Treasury term normalisation
# --------------------------------------------------------------------------- #
def test_normalize_term():
    assert ec._normalize_term("Bond", "19-Year 11-Month") == "20-Year Bond"
    assert ec._normalize_term("Note", "4-Year 10-Month") == "5-Year Note"
    assert ec._normalize_term("Note", "2-Year") == "2-Year Note"
    assert ec._normalize_term("Note", "9-Year 11-Month") == "10-Year Note"


def test_auction_events_parse(monkeypatch):
    """Coupon auctions are kept (with clean benchmark labels); bills are dropped."""
    monkeypatch.setattr(ec, "_fetch_upcoming_auctions", lambda today: [
        {"securityType": "Note", "securityTerm": "7-Year", "auctionDate": "2026-06-25T00:00:00",
         "reopening": "No"},
        {"securityType": "Bond", "securityTerm": "19-Year 11-Month",
         "auctionDate": "2026-06-16T00:00:00", "reopening": "Yes"},
        {"securityType": "Bill", "securityTerm": "13-Week", "auctionDate": "2026-06-15T00:00:00",
         "reopening": "No"},                                    # bill -> excluded
        {"securityType": "Note", "securityTerm": "5-Year", "auctionDate": "2026-07-30T00:00:00",
         "reopening": "No"},                                    # out of window -> excluded
    ])
    evs = ec._auction_events(T, date(2026, 6, 28))
    labels = sorted(e["label"] for e in evs)
    assert labels == ["20-Year Bond auction (reopening)", "7-Year Note auction"]
    labels_zh = sorted(e["label_zh"] for e in evs)
    assert labels_zh == ["20年期国债拍卖（续发行）", "7年期国债拍卖"]
    for e in evs:
        assert e["type"] == "AUCTION" and e["impact"] == "med" and e["is_context_only"] is True


# --------------------------------------------------------------------------- #
# bilingual parity (docs/DESIGN_DOCTRINE.md) — every event carries label_zh
# --------------------------------------------------------------------------- #
def _has_cjk(s: str) -> bool:
    return any("一" <= c <= "鿿" for c in s)


def test_every_event_carries_label_zh(monkeypatch):
    _no_auctions(monkeypatch)
    for e in ec.us_macro_events(T, 30, use_fred=False) + ec.commodity_events(T, 30):
        assert e.get("label_zh"), f"missing label_zh on {e['type']}"
        assert _has_cjk(e["label_zh"]), e


def test_fomc_sep_tag_translated(monkeypatch):
    """The SEP/dot-plot tag must not leak the EN tag into the ZH label."""
    _no_auctions(monkeypatch)
    ev = next(e for e in ec.us_macro_events(date(2026, 6, 1), 30, use_fred=False)
              if e["type"] == "FOMC")
    assert "点阵图" in ev["label_zh"] and "dot-plot" not in ev["label_zh"]


def test_opex_quad_witching_label_zh(monkeypatch):
    _no_auctions(monkeypatch)
    opex = next(e for e in ec.us_macro_events(date(2026, 6, 15), 7, use_fred=False)
                if e["type"] == "OPEX")
    assert opex["label"] == "Quad-witching expiration"
    assert opex["label_zh"] == "四巫日期权到期"


def test_high_impact_strip_md_zh(monkeypatch):
    _no_auctions(monkeypatch)
    strip = ec.high_impact_strip(T, 14)
    assert any(s["type"] == "FOMC" and s["md_zh"] == "6月17日" for s in strip)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
