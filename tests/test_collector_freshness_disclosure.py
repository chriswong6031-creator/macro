"""Collector never-silent disclosure (R4, research/ADJUDICATION_20260803_UNIVERSE_
SIDE_STORE_FRESHNESS.md): collectors/yahoo.py's requested-vs-returned reconciliation
+ store-tip audit, and collectors/breadth.py's current-constituent column disclosure.

CTRA/TPH/TCNNF froze because `_extract()` drops a requested-but-unreturned symbol
via a log-only `except KeyError`, invisible to every downstream guard; CWEN-A froze
because `_merge_refreshed`'s `fresh.combine_first(cached)` (a deliberate perpetual-
archive feature) carries a dead column forward with zero disclosure. No network —
every fixture here is a hand-built DataFrame/dict; store reads are monkeypatched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import breadth as bp  # noqa: E402
from collectors import yahoo as yh  # noqa: E402


# ---------------------------------------------------------------------------
# collectors/yahoo.py::_report_missing_symbols
# ---------------------------------------------------------------------------

def test_missing_symbols_prints_bare_warning_and_returns_list(capsys):
    requested = ["AAPL", "CTRA", "TPH", "TCNNF"]
    returned = {"AAPL"}   # CTRA/TPH/TCNNF silently absent, mirroring the incident
    missing = yh._report_missing_symbols(requested, returned)
    assert missing == ["CTRA", "TPH", "TCNNF"]
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("::")]
    assert len(lines) == 1
    assert lines[0].startswith("::warning title=yahoo collector missing symbols::")
    assert "CTRA" in lines[0] and "TPH" in lines[0] and "TCNNF" in lines[0]


def test_missing_symbols_silent_when_nothing_missing(capsys):
    missing = yh._report_missing_symbols(["AAPL", "MSFT"], {"AAPL", "MSFT"})
    assert missing == []
    out = capsys.readouterr().out
    assert not [ln for ln in out.splitlines() if ln.startswith("::")]


def test_missing_symbols_caps_display_at_15(capsys):
    requested = [f"T{i}" for i in range(20)]
    missing = yh._report_missing_symbols(requested, set())
    assert len(missing) == 20
    out = capsys.readouterr().out
    line = [ln for ln in out.splitlines() if ln.startswith("::")][0]
    assert "20 requested" in line
    assert "+5 more" in line
    # only the first 15 (request order) are named in the body
    for t in requested[:15]:
        assert t in line
    for t in requested[15:]:
        assert t not in line


# ---------------------------------------------------------------------------
# collectors/yahoo.py::audit_store_freshness
# ---------------------------------------------------------------------------

def _idx(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.date_range(start, periods=periods, freq="D")


def test_audit_store_freshness_classifies_stale_stub_missing(monkeypatch, capsys):
    fresh_df = pd.DataFrame({"close": range(80)}, index=_idx("2026-05-18", 80))   # tip 2026-08-05
    stale_df = pd.DataFrame({"close": range(70)}, index=_idx("2026-05-01", 70))   # tip 2026-07-09
    stub_df = pd.DataFrame({"close": [1.0, 2.0]}, index=_idx("2026-08-04", 2))    # tip 2026-08-05, 2 rows

    fixtures = {"FRESH": fresh_df, "STALE": stale_df, "STUB": stub_df}

    def fake_read(group, name):
        assert group == "yahoo"
        return fixtures.get(name)

    monkeypatch.setattr(yh.store, "read", fake_read)
    result = yh.audit_store_freshness(["FRESH", "STALE", "STUB", "GHOST"], group="yahoo")

    assert result["ref"] == "2026-08-05"           # FRESH sets the group's own tip
    assert "STALE" in result["stale"] and result["stale"]["STALE"] == "2026-07-09"
    assert "FRESH" not in result["stale"] and "STUB" not in result["stale"]
    assert "STUB" in result["stub"] and result["stub"] is not None
    assert "FRESH" not in result["stub"] and "STALE" not in result["stub"]
    assert result["missing"] == ["GHOST"]

    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("::")]
    joined = "\n".join(lines)
    assert "STALE" in joined and "STUB" in joined and "GHOST" in joined
    assert "FRESH" not in joined   # only the bad ones get named


def test_audit_store_freshness_all_fresh_prints_nothing(monkeypatch, capsys):
    fresh_df = pd.DataFrame({"close": range(80)}, index=_idx("2026-05-18", 80))

    def fake_read(group, name):
        return fresh_df

    monkeypatch.setattr(yh.store, "read", fake_read)
    result = yh.audit_store_freshness(["A", "B"], group="yahoo")
    assert result["stale"] == {} and result["stub"] == {} and result["missing"] == []
    out = capsys.readouterr().out
    assert not [ln for ln in out.splitlines() if ln.startswith("::")]


def test_audit_store_freshness_no_stores_returns_none_ref(monkeypatch):
    monkeypatch.setattr(yh.store, "read", lambda group, name: None)
    result = yh.audit_store_freshness(["A", "B"], group="yahoo")
    assert result["ref"] is None
    assert result["missing"] == ["A", "B"]


# ---------------------------------------------------------------------------
# collectors/breadth.py::disclose_stale_constituent_columns
# ---------------------------------------------------------------------------

def test_breadth_column_disclosure_names_only_the_bad_ones(capsys):
    idx = pd.date_range("2026-06-27", periods=40, freq="D")   # last date 2026-08-05
    fresh = pd.Series(1.0, index=idx)
    # CWEN-A class: real values only through day 5 (2026-07-01) -> 35 days behind
    frozen = pd.Series(1.0, index=idx[:5]).reindex(idx)
    never_pop = pd.Series([float("nan")] * len(idx), index=idx)
    closes = pd.DataFrame({"FRESH": fresh, "FROZEN": frozen, "NEVERPOP": never_pop})

    members = ["FRESH", "FROZEN", "NEVERPOP", "GONE"]   # GONE isn't even a column
    result = bp.disclose_stale_constituent_columns(members, closes, "smallcap_breadth")

    assert result["frozen"] == {"FROZEN": "2026-07-01"}
    assert result["never_populated"] == ["NEVERPOP"]
    assert result["no_column"] == ["GONE"]
    assert "FRESH" not in result["frozen"] and "FRESH" not in result["never_populated"] \
        and "FRESH" not in result["no_column"]

    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("::")]
    assert len(lines) == 1
    assert lines[0].startswith("::warning title=smallcap_breadth breadth constituents not refreshing::")
    assert "FROZEN" in lines[0] and "NEVERPOP" in lines[0] and "GONE" in lines[0]
    assert "FRESH" not in lines[0]


def test_breadth_column_disclosure_all_fresh_prints_nothing(capsys):
    idx = pd.date_range("2026-06-27", periods=10, freq="D")
    a = pd.Series(1.0, index=idx)
    b = pd.Series(2.0, index=idx)
    closes = pd.DataFrame({"A": a, "B": b})
    result = bp.disclose_stale_constituent_columns(["A", "B"], closes, "breadth")
    assert result == {"no_column": [], "never_populated": [], "frozen": {}}
    out = capsys.readouterr().out
    assert not [ln for ln in out.splitlines() if ln.startswith("::")]


def test_breadth_column_disclosure_empty_closes_marks_all_no_column():
    closes = pd.DataFrame()
    result = bp.disclose_stale_constituent_columns(["A", "B"], closes, "breadth")
    assert set(result["no_column"]) == {"A", "B"}
