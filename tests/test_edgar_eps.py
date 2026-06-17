"""Tests for the EDGAR EPS real-filing-date overlay (collectors/edgar_eps.py).

The SUE panel's PIT as-of is the date a quarter's earnings actually became public. These
tests pin the two load-bearing behaviours: (1) fetch_eps_filing_dates takes the EARLIEST
original 10-Q/10-K `filed` per period-end (never a later comparative re-tag or amendment),
and (2) _apply_filing_dates overlays it only where valid and otherwise keeps the conservative
synthetic fallback (never NaT, which would silently hide the row in sue_cross_section)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.edgar_eps as ee  # noqa: E402


def _cc(facts):
    """A fake companyconcept response. facts = list of (end, filed, form, val)."""
    return {"units": {"USD/shares": [
        {"end": e, "filed": f, "form": fm, "val": v} for (e, f, fm, v) in facts]}}


def _patch_fetch(monkeypatch, tmp_path, resp_by_cik):
    monkeypatch.setattr(ee, "_get_json", lambda url, *a, **k: next(
        (resp_by_cik[c] for c in resp_by_cik if f"CIK{c:010d}" in url), None))
    monkeypatch.setattr(ee, "_cfg", lambda: {
        "base_url": "https://data.sec.gov/api/xbrl/frames/us-gaap", "retries": 1})
    monkeypatch.setattr(ee, "_filing_dates_path", lambda: tmp_path / "fd.parquet")
    monkeypatch.setattr(ee.time, "sleep", lambda *a, **k: None)


def test_takes_earliest_original_filed_ignoring_retags(monkeypatch, tmp_path):
    # the Q1 value is emitted by the ORIGINAL 10-Q (filed 2024-05-02) and again as a
    # comparative in next year's 10-Q (filed 2025-05-02) — we must keep the original.
    resp = {320193: _cc([
        ("2024-03-30", "2024-05-02", "10-Q", 1.53),
        ("2024-03-30", "2025-05-02", "10-Q", 1.53),   # later comparative re-tag
        ("2024-06-29", "2024-08-02", "10-Q", 1.40),
    ])}
    _patch_fetch(monkeypatch, tmp_path, resp)
    fd = ee.fetch_eps_filing_dates({320193: "AAPL"}, force=True)
    q1 = fd[(fd.ticker == "AAPL") & (fd.period_end == pd.Timestamp("2024-03-30"))]
    assert len(q1) == 1 and q1.iloc[0]["filed_date"] == pd.Timestamp("2024-05-02")


def test_excludes_amendments_and_8k(monkeypatch, tmp_path):
    # an 8-K (preliminary) and a 10-K/A amendment for the same end must NOT be sourced;
    # only the original 10-Q/10-K filing date counts.
    resp = {1: _cc([
        ("2024-03-31", "2024-04-20", "8-K", 2.0),      # earnings release — excluded
        ("2024-03-31", "2024-05-05", "10-Q", 2.0),     # the original periodic report
        ("2024-03-31", "2024-09-01", "10-Q/A", 2.1),   # amendment — excluded
    ])}
    _patch_fetch(monkeypatch, tmp_path, resp)
    fd = ee.fetch_eps_filing_dates({1: "TST"}, force=True)
    assert fd.iloc[0]["filed_date"] == pd.Timestamp("2024-05-05")   # the 10-Q, not the 8-K


def test_skipped_cik_is_graceful(monkeypatch, tmp_path):
    # a CIK that 404s (None) contributes no rows; a covered one still does.
    resp = {1: _cc([("2024-03-31", "2024-05-05", "10-Q", 2.0)])}   # cik 2 absent -> None
    _patch_fetch(monkeypatch, tmp_path, resp)
    fd = ee.fetch_eps_filing_dates({1: "AAA", 2: "BBB"}, force=True)
    assert set(fd.ticker) == {"AAA"}


def _panel(rows):
    df = pd.DataFrame(rows, columns=["ticker", "period_end", "eps_q"])
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["asof_date"] = df["period_end"] + pd.Timedelta(days=60)   # synthetic fallback
    return df


def test_apply_overlays_real_keeps_synthetic_fallback():
    df = _panel([("AAA", "2024-03-31", 1.0), ("AAA", "2024-06-30", 1.1),
                 ("BBB", "2024-03-31", 2.0)])
    fd = pd.DataFrame({"ticker": ["AAA"], "period_end": [pd.Timestamp("2024-03-31")],
                       "filed_date": [pd.Timestamp("2024-05-02")]})
    out = ee._apply_filing_dates(df, fd, lag=60)
    a = out[(out.ticker == "AAA") & (out.period_end == pd.Timestamp("2024-03-31"))].iloc[0]
    assert a["asof_date"] == pd.Timestamp("2024-05-02")          # real filing date used
    # the unmatched AAA Q2 and BBB rows keep the synthetic +60d fallback, never NaT
    a2 = out[(out.ticker == "AAA") & (out.period_end == pd.Timestamp("2024-06-30"))].iloc[0]
    assert a2["asof_date"] == pd.Timestamp("2024-08-29")
    assert out["asof_date"].notna().all()
    assert "filed_date" not in out.columns


def test_apply_guards_against_predated_filing():
    # a junk filing date BEFORE the period close must be ignored (keep synthetic)
    df = _panel([("AAA", "2024-03-31", 1.0)])
    fd = pd.DataFrame({"ticker": ["AAA"], "period_end": [pd.Timestamp("2024-03-31")],
                       "filed_date": [pd.Timestamp("2024-02-01")]})   # before period_end
    out = ee._apply_filing_dates(df, fd, lag=60)
    assert out.iloc[0]["asof_date"] == pd.Timestamp("2024-05-30")     # synthetic retained


def test_apply_empty_fd_is_noop():
    df = _panel([("AAA", "2024-03-31", 1.0)])
    out = ee._apply_filing_dates(df, pd.DataFrame(), lag=60)
    assert out.iloc[0]["asof_date"] == pd.Timestamp("2024-05-30")
