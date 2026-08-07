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
    # T1/T10/T11.../T19 share a prefix — a naive "T1 in line" substring check would
    # pass even if T1 itself were silently dropped from the shown set (it would
    # still match inside "T10"). Assert on the exact comma-delimited token list.
    requested = [f"T{i}" for i in range(20)]
    missing = yh._report_missing_symbols(requested, set())
    assert len(missing) == 20
    out = capsys.readouterr().out
    line = [ln for ln in out.splitlines() if ln.startswith("::")][0]
    assert "20 requested" in line
    assert "+5 more" in line
    body = line.split("returned no data: ", 1)[1]
    names_part = body.split(", +", 1)[0]
    shown_tokens = [t.strip() for t in names_part.split(",")]
    assert shown_tokens == requested[:15]


# ---------------------------------------------------------------------------
# collectors/yahoo.py::audit_store_freshness
# ---------------------------------------------------------------------------

def _idx(start: str, periods: int) -> pd.DatetimeIndex:
    return pd.date_range(start, periods=periods, freq="D")


# Wall-clock anchor for every "fresh" fixture: the M1 backstops compare a fixture's own
# tip against utcnow, so a hardcoded fresh-tip date is a scheduled failure fuse — it
# passes until (date + 7d) and then reds the suite with no code change. Same idiom as
# the production backstops (Timestamp.utcnow kept for consistency with breadth.py:436).
_TODAY = pd.Timestamp.utcnow().tz_localize(None).normalize()


def _idx_ending(periods: int, end: pd.Timestamp = _TODAY, lag_days: int = 0) -> pd.DatetimeIndex:
    return pd.date_range(end=end - pd.Timedelta(days=lag_days), periods=periods, freq="D")


def test_audit_store_freshness_classifies_stale_stub_missing(monkeypatch, capsys):
    fresh_df = pd.DataFrame({"close": range(80)}, index=_idx_ending(80))              # tip today
    stale_df = pd.DataFrame({"close": range(70)}, index=_idx_ending(70, lag_days=27))  # tip today-27d
    stub_df = pd.DataFrame({"close": [1.0, 2.0]}, index=_idx_ending(2))               # tip today, 2 rows
    _stale_tip = str((_TODAY - pd.Timedelta(days=27)).date())

    fixtures = {"FRESH": fresh_df, "STALE": stale_df, "STUB": stub_df}

    def fake_read(group, name):
        assert group == "yahoo"
        return fixtures.get(name)

    monkeypatch.setattr(yh.store, "read", fake_read)
    result = yh.audit_store_freshness(["FRESH", "STALE", "STUB", "GHOST"], group="yahoo")

    assert result["ref"] == str(_TODAY.date())     # FRESH sets the group's own tip
    assert "STALE" in result["stale"] and result["stale"]["STALE"] == _stale_tip
    assert "FRESH" not in result["stale"] and "STUB" not in result["stale"]
    assert "STUB" in result["stub"]
    assert "FRESH" not in result["stub"] and "STALE" not in result["stub"]
    assert result["missing"] == ["GHOST"]

    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("::")]
    joined = "\n".join(lines)
    assert "STALE" in joined and "STUB" in joined and "GHOST" in joined
    assert "FRESH" not in joined   # only the bad ones get named


def test_audit_store_freshness_all_fresh_prints_nothing(monkeypatch, capsys):
    fresh_df = pd.DataFrame({"close": range(80)}, index=_idx_ending(80))

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


def test_audit_store_freshness_m1_wall_clock_backstop_on_old_ref(monkeypatch, capsys):
    """M1: a store-tip audit is self-relative to its OWN ref tip — a store whose
    every ticker is stuck at the same ancient date reads as internally consistent
    (nothing is `stale` relative to `ref`) unless something also checks `ref` against
    wall-clock now. Old, fixed dates (not utcnow-anchored) are the point of this test —
    utcnow is naturally far ahead of them."""
    old_df = pd.DataFrame({"close": range(60)}, index=_idx("2020-01-01", 60))

    def fake_read(group, name):
        return old_df

    monkeypatch.setattr(yh.store, "read", fake_read)
    result = yh.audit_store_freshness(["A", "B"], group="yahoo")
    assert result["stale"] == {}   # internally consistent — nothing is behind `ref`
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("::")]
    assert any(ln.startswith("::warning title=yahoo store audit tip stale::") for ln in lines)


# ---------------------------------------------------------------------------
# collectors/breadth.py::disclose_stale_constituent_columns
# ---------------------------------------------------------------------------

def test_breadth_column_disclosure_names_only_the_bad_ones(capsys):
    idx = _idx_ending(40)   # ends today — a hardcoded end date would arm the M1 backstop
    fresh = pd.Series(1.0, index=idx)
    # CWEN-A class: real values only through day 5 (idx[4]) -> 35 days behind the tip
    frozen = pd.Series(1.0, index=idx[:5]).reindex(idx)
    never_pop = pd.Series([float("nan")] * len(idx), index=idx)
    closes = pd.DataFrame({"FRESH": fresh, "FROZEN": frozen, "NEVERPOP": never_pop})

    members = ["FRESH", "FROZEN", "NEVERPOP", "GONE"]   # GONE isn't even a column
    result = bp.disclose_stale_constituent_columns(members, closes, "smallcap_breadth")

    assert result["frozen"] == {"FROZEN": str(idx[4].date())}
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
    # anchored to wall-clock "today" (not a hardcoded date) so the new M1 wall-clock
    # backstop doesn't fire here — this test's whole point is that a genuinely fresh
    # frame prints NOTHING, from either check.
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    idx = pd.date_range(today - pd.Timedelta(days=9), periods=10, freq="D")
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


def test_breadth_column_disclosure_m1_wall_clock_backstop_on_total_freeze(capsys):
    """M1: every member frozen TOGETHER at the same old date is invisible to the
    `frozen` check (nothing is behind `overall_tip` — it IS overall_tip). Old, fixed
    dates are the point here — utcnow is naturally far ahead of them."""
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    a = pd.Series(1.0, index=idx)
    b = pd.Series(2.0, index=idx)
    closes = pd.DataFrame({"A": a, "B": b})
    result = bp.disclose_stale_constituent_columns(["A", "B"], closes, "breadth")
    assert result == {"no_column": [], "never_populated": [], "frozen": {}}
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("::")]
    assert any(ln.startswith("::warning title=breadth breadth tip stale::") for ln in lines)


# ---------------------------------------------------------------------------
# M3: collectors/yahoo.py::YahooAdapter.fetch — a basis-DEFERRED name (returned by
# yfinance this run, pulled out of `frames` only by `_rebase_shifted`'s failed re-
# pull) must not be relabeled "returned no data".
# ---------------------------------------------------------------------------

def test_fetch_missing_warning_excludes_basis_deferred_names(monkeypatch, capsys):
    served = {"OK0", "OK1", "OK2", "OK3", "OK4", "OK5", "OK6", "DEFERRED1"}
    idx = pd.date_range("2026-08-01", periods=3, freq="D")

    def fake_download(self, batch, period):
        cols = [t for t in batch if t in served]
        if not cols:
            raise RuntimeError("empty yfinance response")
        col_idx = pd.MultiIndex.from_product([cols, ["Close", "Adj Close", "Volume"]])
        return pd.DataFrame(1.0, index=idx, columns=col_idx)

    def fake_rebase(self, frames, ohlc):
        # DEFERRED1 WAS returned by yfinance (it's in `served`/`frames`) but the
        # basis-guard's re-pull failed, so it's popped from `frames` for this run —
        # never "requested symbol returned no data".
        frames.pop("DEFERRED1", None)
        return ["DEFERRED1"]

    monkeypatch.setattr(yh.YahooAdapter, "_download", fake_download)
    monkeypatch.setattr(yh.YahooAdapter, "_rebase_shifted", fake_rebase)
    monkeypatch.setattr(yh.config, "load", lambda: {"stock_search": {"extra_tickers": []}})

    adapter = yh.YahooAdapter.__new__(yh.YahooAdapter)
    adapter.cfg = {"batch_size": 20, "retries": 1, "backoff_base_s": 0, "tickers": {"vol": []}}
    tickers = ["OK0", "OK1", "OK2", "OK3", "OK4", "OK5", "OK6",
               "DEFERRED1", "REALLYMISSING1", "REALLYMISSING2"]
    monkeypatch.setattr(adapter, "all_tickers", lambda: tickers)

    frames = adapter.fetch(full_history=False)
    assert "DEFERRED1" not in frames
    assert set(frames) == {"OK0", "OK1", "OK2", "OK3", "OK4", "OK5", "OK6"}

    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines()
             if ln.startswith("::warning title=yahoo collector missing symbols::")]
    assert len(lines) == 1
    body = lines[0].split("returned no data: ", 1)[1]
    shown = [t.strip() for t in body.split(",")]
    assert "REALLYMISSING1" in shown and "REALLYMISSING2" in shown
    assert "DEFERRED1" not in shown
