"""Tests for collectors/hk_placements.py — H-PLC placement/rights event collector.

All tests run against synthetic servlet rows / tmp_path stores — no network, no real
data/ paths. Coverage:

  1. code_to_ticker normalisation (servlet zero-padded codes -> panel '.HK' keys).
  2. _rows_to_frame parsing: DD/MM/YYYY HH:MM datetimes, double-escaped HTML entities,
     rows with missing news_id/code/date dropped.
  3. merge_events: append-only dedupe on (news_id, stock_code), keep-FIRST.
  4. is_dilutive classifier: real titles from the 2026-07 live probe — genuine top-up
     placings/rights results qualify; AT1/perpetual capital, convertible bonds,
     meeting notices and cancellations do not.
  5. fetch fail-closed: the named tripwire raises on a zero-event fetch and the store
     is never touched.
  6. flag_map: window anchoring on asof, dilutive-title filtering, latest-event-wins.
"""
from __future__ import annotations

import pandas as pd
import pytest

import collectors.hk_placements as hp


# ---------------------------------------------------------------------------
# 1. code_to_ticker
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code,expected", [
    ("01323", "1323.HK"),
    ("00139", "0139.HK"),
    ("00005", "0005.HK"),
    ("08191", "8191.HK"),
    ("09678", "9678.HK"),
    ("0", None),          # out of range
    ("", None),
    ("ABC", None),        # non-numeric (structured products)
    (None, None),
])
def test_code_to_ticker(code, expected):
    assert hp.code_to_ticker(code) == expected


# ---------------------------------------------------------------------------
# 2. _rows_to_frame parsing
# ---------------------------------------------------------------------------
def _servlet_row(news_id="123", code="01323", dt="03/07/2026 22:48",
                 title="COMPLETION OF PLACING OF NEW SHARES\nUNDER GENERAL MANDATE",
                 short="Announcements and Notices - [Placing &#x2f; Issue of Shares "
                       "under a General Mandate]<br/>"):
    return {"NEWS_ID": news_id, "STOCK_CODE": code, "STOCK_NAME": "X",
            "DATE_TIME": dt, "TITLE": title, "SHORT_TEXT": short}


def test_rows_to_frame_parses_and_cleans():
    df = hp._rows_to_frame([_servlet_row()], "placing")
    assert len(df) == 1
    r = df.iloc[0]
    assert r["ticker"] == "1323.HK"
    assert r["category"] == "placing"
    assert r["announced_at"] == pd.Timestamp("2026-07-03 22:48")
    assert r["date"] == pd.Timestamp("2026-07-03")
    # newline folded, no raw entities/tags leak through
    assert r["title"] == "COMPLETION OF PLACING OF NEW SHARES UNDER GENERAL MANDATE"
    assert "&#x2f;" not in r["subcats"] and "<br" not in r["subcats"]
    assert "Placing / Issue of Shares" in r["subcats"]


def test_rows_to_frame_drops_malformed():
    rows = [
        _servlet_row(news_id=""),                      # no id
        _servlet_row(code=""),                         # no code
        _servlet_row(dt="not-a-date"),                 # bad datetime
        _servlet_row(news_id="ok1"),
    ]
    df = hp._rows_to_frame(rows, "placing")
    assert list(df["news_id"]) == ["ok1"]


# ---------------------------------------------------------------------------
# 3. merge_events dedupe
# ---------------------------------------------------------------------------
def test_merge_events_dedupes_on_news_id_and_code():
    a = hp._rows_to_frame([_servlet_row(news_id="1", code="00001"),
                           _servlet_row(news_id="1", code="00002")], "placing")
    # same news_id+code arriving again under ANOTHER category dedupes away (keep-FIRST);
    # same news_id for a DIFFERENT code is a distinct event row (joint announcements).
    b = hp._rows_to_frame([_servlet_row(news_id="1", code="00001"),
                           _servlet_row(news_id="2", code="00001")], "rights_issue")
    m = hp.merge_events(a, b)
    assert len(m) == 3
    first = m[(m["news_id"] == "1") & (m["stock_code"] == "00001")]
    assert list(first["category"]) == ["placing"]      # keep-FIRST won


# ---------------------------------------------------------------------------
# 4. is_dilutive classifier — titles from the 2026-07 live probe
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("title,expected", [
    # genuine dilution — qualify
    ("PLACING OF NEW SHARES UNDER GENERAL MANDATE", True),
    ("COMPLETION OF PLACING", True),
    ("COMPLETION OF TOP-UP PLACING OF EXISTING SHARES AND SUBSCRIPTION OF NEW "
     "SHARES UNDER GENERAL MANDATE", True),
    ("(1) RESULTS OF THE RIGHTS ISSUE ON THE BASIS OF FOUR (4) RIGHTS SHARES FOR "
     "EVERY ONE (1) EXISTING SHARE HELD ON THE RECORD DATE ON A NON-UNDERWRITTEN "
     "BASIS; AND (2) PLACING OF THE UNSUBSCRIBED RIGHTS SHARES", True),
    ("CONNECTED TRANSACTION IN RESPECT OF PROPOSED A SHARE ISSUANCE", True),
    ("PROPOSED RIGHTS ISSUE ON THE BASIS OF ONE RIGHTS SHARE FOR EVERY TWO SHARES", True),
    ("OPEN OFFER OF NEW SHARES", True),
    # over-capture — excluded
    ("ISSUANCE OF PERPETUAL SUBORDINATED CONTINGENT CONVERTIBLE SECURITIES", False),
    ("PROPOSED ISSUE OF HK$8,624,000,000 ZERO COUPON GUARANTEED CONVERTIBLE BONDS "
     "DUE 2027 UNDER THE GENERAL MANDATE", False),
    ("NOTICE OF THE FIRST EXTRAORDINARY SHAREHOLDERS' MEETING OF 2026", False),
    ("ANNOUNCEMENT POLL RESULTS OF THE ANNUAL SHAREHOLDERS' MEETING OF 2025 HELD ON "
     "17 JUNE 2026", False),
    ("FURTHER ANNOUNCEMENT CANCELLATION OF THE TRANCHE 2B SUBSCRIPTION", False),
    ("", False),
    # meeting notice CARRYING a strong phrase stays flagged (in-flight rights program)
    ("EXTENSION OF EFFECTIVE PERIOD OF SHAREHOLDERS' MEETING RESOLUTIONS REGARDING "
     "ISSUING RIGHTS SHARES TO EXISTING SHAREHOLDERS", True),
])
def test_is_dilutive(title, expected):
    assert hp.is_dilutive(title) is expected


# ---------------------------------------------------------------------------
# 5. fetch fail-closed tripwire
# ---------------------------------------------------------------------------
def _patch_store(monkeypatch, tmp_path):
    monkeypatch.setattr(hp, "_STORE", tmp_path / "events.parquet")
    monkeypatch.setattr(hp, "_COVERAGE", tmp_path / "coverage.json")


def test_zero_event_fetch_raises_and_never_writes(tmp_path, monkeypatch):
    _patch_store(monkeypatch, tmp_path)
    monkeypatch.setattr(hp, "_fetch_window", lambda *a, **k: [])
    monkeypatch.setattr(hp.time, "sleep", lambda *_: None)
    with pytest.raises(RuntimeError, match="TRIPWIRE"):
        hp.fetch_hk_placements(full_history=False)
    assert not (tmp_path / "events.parquet").exists()
    assert not (tmp_path / "coverage.json").exists()


def test_zero_event_fetch_raises_even_with_prior_store(tmp_path, monkeypatch):
    """A dead feed must trip even when a healthy store exists (no silent freeze)."""
    _patch_store(monkeypatch, tmp_path)
    prior = hp._rows_to_frame([_servlet_row()], "placing")
    hp._save_store(prior)
    monkeypatch.setattr(hp, "_fetch_window", lambda *a, **k: [])
    monkeypatch.setattr(hp.time, "sleep", lambda *_: None)
    with pytest.raises(RuntimeError, match="TRIPWIRE"):
        hp.fetch_hk_placements(full_history=False)
    assert len(hp._load_store()) == 1                  # store untouched


def test_fetch_merges_and_stamps_coverage(tmp_path, monkeypatch):
    _patch_store(monkeypatch, tmp_path)
    rows = [_servlet_row(news_id="9", code="06651",
                         title="PLACING OF NEW H SHARES UNDER GENERAL MANDATE")]
    monkeypatch.setattr(hp, "_fetch_window",
                        lambda cat, a, b: rows if cat == "placing" else [])
    monkeypatch.setattr(hp.time, "sleep", lambda *_: None)
    n = hp.fetch_hk_placements(full_history=False)
    assert n == 1
    st = hp.store_status()
    assert st["available"] and st["n_events"] == 1 and st["latest"] == "2026-07-03"
    # idempotent: same rows again -> 0 new, no dupes
    assert hp.fetch_hk_placements(full_history=False) == 0
    assert len(hp._load_store()) == 1


# ---------------------------------------------------------------------------
# 6. flag_map windowing + filtering
# ---------------------------------------------------------------------------
def test_flag_map_window_filter_and_latest(tmp_path, monkeypatch):
    _patch_store(monkeypatch, tmp_path)
    frame = hp._rows_to_frame([
        # in-window dilutive placing (2 events, latest should win)
        _servlet_row(news_id="a1", code="06651", dt="01/06/2026 09:00",
                     title="PLACING OF NEW H SHARES UNDER GENERAL MANDATE"),
        _servlet_row(news_id="a2", code="06651", dt="20/06/2026 09:00",
                     title="COMPLETION OF PLACING OF NEW H SHARES UNDER GENERAL MANDATE"),
        # in-window but NON-dilutive (AT1) -> never flags
        _servlet_row(news_id="b1", code="00005", dt="20/06/2026 09:00",
                     title="ISSUANCE OF PERPETUAL SUBORDINATED CONTINGENT CONVERTIBLE SECURITIES"),
        # dilutive but OUT of the 90d window
        _servlet_row(news_id="c1", code="01277", dt="01/01/2026 09:00",
                     title="PLACING OF NEW SHARES UNDER GENERAL MANDATE"),
        # dilutive but AFTER the asof anchor (future leak guard)
        _servlet_row(news_id="d1", code="02650", dt="30/07/2026 09:00",
                     title="PLACING OF NEW SHARES UNDER GENERAL MANDATE"),
    ], "placing")
    hp._save_store(frame)

    fm = hp.flag_map(["6651.HK", "0005.HK", "1277.HK", "2650.HK"],
                     asof="2026-07-03")
    assert set(fm) == {"6651.HK"}
    hit = fm["6651.HK"]
    assert hit["date"] == "2026-06-20" and hit["n_events"] == 2   # latest event wins
    assert hit["days_ago"] == 13
    assert hit["category"] == "placing"


def test_flag_map_empty_store_returns_empty(tmp_path, monkeypatch):
    _patch_store(monkeypatch, tmp_path)
    assert hp.flag_map(["0700.HK"]) == {}
    assert hp.store_status()["available"] is False
