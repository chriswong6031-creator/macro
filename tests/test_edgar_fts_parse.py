"""collectors.edgar_fts._parse_hit — must handle BOTH EDGAR display_name shapes (legacy
single-paren '(TICK, CIK ..)' and current two-paren '(TICK) (CIK ..)'), or the whole
EDGAR-language leg (T1 bottleneck + T3 guidance) silently drops every hit.
"""
from __future__ import annotations

from collectors.edgar_fts import _parse_hit, _tickers_from_display


def _hit(display):
    return {"_id": "abc", "_source": {"display_names": [display], "ciks": ["1563411"],
                                      "root_forms": ["8-K"], "file_date": "2026-05-01"}}


def test_current_two_paren_format():
    assert _tickers_from_display("CONSTELLIUM SE  (CSTM)  (CIK 0001563411)") == ["CSTM"]
    assert _parse_hit(_hit("MIDDLEBY Corp  (MIDD)  (CIK 0000769520)"))["ticker"] == "MIDD"


def test_legacy_single_paren_format():
    # the old format must still parse (backward compatible)
    assert _tickers_from_display("ACME CORP  (ACME, CIK 0001234567)") == ["ACME"]
    assert _parse_hit(_hit("ACME CORP  (ACME, CIK 0001234567)"))["ticker"] == "ACME"


def test_name_paren_before_ticker_is_not_mistaken():
    # EDGAR renders "The Boeing Company" as "Boeing Co (The)  (BA)  (CIK ..)" — the "(The)"
    # name-paren must NOT be taken as the ticker (BA is in defense_aerospace).
    assert _tickers_from_display("Boeing Co (The)  (BA)  (CIK 0000012927)") == ["BA"]
    assert _parse_hit(_hit("Coca-Cola Co (The)  (KO)  (CIK 0000021344)"))["ticker"] == "KO"
    assert _parse_hit(_hit("Carlyle Group Inc. (The)  (CG)  (CIK 0001527166)"))["ticker"] == "CG"


def test_multi_class_takes_common_share_first():
    # warrants / second classes follow the common share; we take the first
    assert _tickers_from_display("BlackSky Technology Inc.  (BKSY, BKSY-WT)  (CIK 0001753539)")[0] == "BKSY"
    assert _parse_hit(_hit("BlackSky Technology Inc.  (BKSY, BKSY-WT)  (CIK 0001753539)"))["ticker"] == "BKSY"


def test_no_ticker_returns_none():
    assert _tickers_from_display("SOME FUND TRUST  (CIK 0001234567)") == []
    assert _parse_hit(_hit("SOME FUND TRUST  (CIK 0001234567)")) is None
    assert _parse_hit({"_source": {"display_names": []}}) is None
