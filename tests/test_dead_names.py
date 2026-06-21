"""Tests for dead-name fundamentals recovery (collectors/edgar_deadnames.py).

Load-bearing invariants:
  * LEAK GUARD — asof_date (the true SEC filed date) is STRICTLY after period_end;
    a row is never knowable at/before the period it reports.
  * COMPARATIVE TRAP — companyfacts tags prior-year comparatives with the filing's
    own `fy`; extraction must key by reporting PERIOD, not `e["fy"]`.
  * 52/53-WEEK TRAP — off-calendar filers must be labeled from the SEC CY{year}
    frame (not year(end)) so two fiscal years never collide on one calendar year.
  * SCHEMA — the dead panel is column-identical to fundamentals_panel so the merge
    is a concat; dedup keeps the survivor row.
  * CIK RESOLUTION — the audited seed wins over company_tickers.json (ticker reuse).
"""
import json

import pandas as pd
import pytest

from collectors import edgar_deadnames as dn


# --------------------------------------------------------------------------- #
# Pure extraction logic (no network)
# --------------------------------------------------------------------------- #
def test_frame_year():
    assert dn._frame_year("CY2019") == 2019
    assert dn._frame_year("CY2019Q4I") == 2019
    assert dn._frame_year(None) is None
    assert dn._frame_year("garbage") is None


def test_annual_dated_ignores_comparative_fy():
    """ATVI-shaped: a FY2009 10-K (filed 2010-03-01) carries 2007 & 2008 rows all
    tagged fy=2009. Keying on the PERIOD must recover the right value per year and
    must NOT mislabel the 2008 comparative as 2009."""
    entries = [
        # 2008 comparative inside the FY2009 10-K
        {"fp": "FY", "form": "10-K", "fy": 2009, "start": "2008-01-01",
         "end": "2008-12-31", "filed": "2010-03-01", "frame": None, "val": 3026},
        # 2009 primary in the FY2009 10-K
        {"fp": "FY", "form": "10-K", "fy": 2009, "start": "2009-01-01",
         "end": "2009-12-31", "filed": "2010-03-01", "frame": None, "val": 4279},
        # 2009 restated as comparative in a later filing (must NOT win — later filed)
        {"fp": "FY", "form": "10-K", "fy": 2011, "start": "2009-01-01",
         "end": "2009-12-31", "filed": "2012-02-28", "frame": "CY2009", "val": 9999},
    ]
    out = dn._annual_dated(entries, instant=False)
    assert out[2008][0] == 3026
    assert out[2009][0] == 4279                      # original, not the 9999 restatement
    assert out[2009][1] == "2010-03-01"              # earliest filed wins (leak-safe)
    assert 2007 not in out


def test_annual_dated_52_53_week_no_collision():
    """Cerner-shaped: fiscal years end on the Saturday near Dec 31, so ends land in
    adjacent calendar years and two FYs can share a calendar year. Frame labels keep
    them distinct; year(end) would collide."""
    entries = [
        {"fp": "FY", "form": "10-K", "fy": 2010, "start": "2010-01-03",
         "end": "2011-01-01", "filed": "2011-02-16", "frame": "CY2010", "val": 1850},
        {"fp": "FY", "form": "10-K", "fy": 2011, "start": "2011-01-02",
         "end": "2011-12-31", "filed": "2012-02-10", "frame": "CY2011", "val": 2203},
    ]
    out = dn._annual_dated(entries, instant=False)
    assert out[2010][0] == 1850 and out[2011][0] == 2203   # both retained, both years
    # year(end) alone would have put both 2011-ending periods on key 2011


def test_annual_dated_full_year_only():
    """A quarterly duration must be rejected from the annual (flow) extraction."""
    entries = [
        {"fp": "FY", "form": "10-K", "fy": 2020, "start": "2020-10-01",
         "end": "2020-12-31", "filed": "2021-02-01", "frame": None, "val": 50},   # 92d
        {"fp": "FY", "form": "10-K", "fy": 2020, "start": "2020-01-01",
         "end": "2020-12-31", "filed": "2021-02-01", "frame": "CY2020", "val": 200},
    ]
    out = dn._annual_dated(entries, instant=False)
    assert out[2020][0] == 200                       # full year kept, quarter dropped


def _fake_companyfacts():
    """Minimal companyfacts payload: Dec-FY filer, FY2019 & FY2020."""
    def flow(vals):  # vals: {fy: (end, filed, val)}
        return {"units": {"USD": [
            {"fp": "FY", "form": "10-K", "fy": fy, "start": f"{fy}-01-01",
             "end": end, "filed": filed, "frame": f"CY{fy}", "val": val}
            for fy, (end, filed, val) in vals.items()]}}

    def inst(vals):
        return {"units": {"USD": [
            {"fp": "FY", "form": "10-K", "fy": fy, "start": None,
             "end": end, "filed": filed, "frame": f"CY{fy}Q4I", "val": val}
            for fy, (end, filed, val) in vals.items()]}}

    return {"entityName": "TESTCO INC", "facts": {"us-gaap": {
        "Revenues": flow({2019: ("2019-12-31", "2020-02-20", 1000),
                          2020: ("2020-12-31", "2021-02-20", 1200)}),
        "NetIncomeLoss": flow({2019: ("2019-12-31", "2020-02-20", 100),
                               2020: ("2020-12-31", "2021-02-20", 150)}),
        "Assets": inst({2019: ("2019-12-31", "2020-02-20", 5000),
                        2020: ("2020-12-31", "2021-02-20", 5500)}),
        "StockholdersEquity": inst({2019: ("2019-12-31", "2020-02-20", 2000),
                                    2020: ("2020-12-31", "2021-02-20", 2200)}),
    }}}


def test_panel_rows_schema_and_priors(monkeypatch):
    monkeypatch.setattr(dn, "_get_json", lambda url, *a, **k: _fake_companyfacts())
    monkeypatch.setattr(dn.time, "sleep", lambda *a, **k: None)
    rows = dn._panel_rows_for("TST", 123)
    by_fy = {r["fy"]: r for r in rows}
    assert set(by_fy) == {2019, 2020}
    assert by_fy[2020]["revenue"] == 1200 and by_fy[2020]["assets"] == 5500
    assert by_fy[2020]["assets_prior"] == 5000          # prior-year linkage
    assert by_fy[2020]["ni_prior"] == 100
    # every panel column present
    for col in (["ticker", "cik", "fy"] + dn.PANEL_NUMERIC + ["period_end", "asof_date"]):
        assert col in by_fy[2020]


# --------------------------------------------------------------------------- #
# build_dead_panel — leak guard + resumability (data_dir redirected to tmp)
# --------------------------------------------------------------------------- #
def _redirect(monkeypatch, tmp_path):
    (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dn.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(dn.time, "sleep", lambda *a, **k: None)


def test_build_dead_panel_leak_guard(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "edgar" / "dead_name_cik.json").write_text(
        json.dumps({"TST": {"cik": 123, "method": "seed"}}))
    monkeypatch.setattr(dn, "_get_json", lambda url, *a, **k: _fake_companyfacts())
    panel = dn.build_dead_panel(force=True, max_new=10)
    assert not panel.empty
    assert (panel["asof_date"] > panel["period_end"]).all()      # LEAK GUARD
    assert list(panel.columns) == (["ticker", "cik", "fy"] + dn.PANEL_NUMERIC +
                                   ["period_end", "asof_date"])


def test_build_dead_panel_drops_filed_at_or_before_period_end(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "edgar" / "dead_name_cik.json").write_text(
        json.dumps({"BAD": {"cik": 9, "method": "seed"}}))
    bad = {"entityName": "BADCO", "facts": {"us-gaap": {
        "Assets": {"units": {"USD": [
            {"fp": "FY", "form": "10-K", "fy": 2020, "end": "2020-12-31",
             "filed": "2020-12-31", "frame": "CY2020Q4I", "val": 10}]}},  # filed==end
        "Revenues": {"units": {"USD": [
            {"fp": "FY", "form": "10-K", "fy": 2020, "start": "2020-01-01",
             "end": "2020-12-31", "filed": "2020-12-31", "frame": "CY2020", "val": 5}]}},
    }}}
    monkeypatch.setattr(dn, "_get_json", lambda url, *a, **k: bad)
    panel = dn.build_dead_panel(force=True, max_new=10)
    assert panel.empty                       # filed not strictly after period_end → dropped


def test_build_dead_panel_resumable(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "edgar" / "dead_name_cik.json").write_text(
        json.dumps({"TST": {"cik": 123, "method": "seed"}}))
    calls = {"n": 0}

    def counted(url, *a, **k):
        calls["n"] += 1
        return _fake_companyfacts()

    monkeypatch.setattr(dn, "_get_json", counted)
    dn.build_dead_panel(force=True, max_new=10)
    first = calls["n"]
    dn.build_dead_panel(force=False, max_new=10)     # fresh → must skip refetch
    assert calls["n"] == first


# --------------------------------------------------------------------------- #
# merge + coverage
# --------------------------------------------------------------------------- #
def test_merged_panel_dedup_keeps_survivor(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    cols = ["ticker", "cik", "fy"] + dn.PANEL_NUMERIC + ["period_end", "asof_date"]
    surv = pd.DataFrame([dict.fromkeys(cols, None) | {"ticker": "AAA", "fy": 2020, "assets": 1}])
    dead = pd.DataFrame([
        dict.fromkeys(cols, None) | {"ticker": "AAA", "fy": 2020, "assets": 999},  # collide
        dict.fromkeys(cols, None) | {"ticker": "DEAD", "fy": 2020, "assets": 7},
    ])
    dead.to_parquet(tmp_path / "edgar" / "dead_name_panel.parquet")
    merged = dn.merged_panel(surv)
    assert set(merged["ticker"]) == {"AAA", "DEAD"}
    assert merged.loc[merged.ticker == "AAA", "assets"].iloc[0] == 1   # survivor wins


def test_coverage_math(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "breadth").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": ["DEAD1", "DEAD2", "DEAD3", "LIVE"],
                  "start_date": pd.to_datetime(["2010-01-01"] * 4),
                  "end_date": pd.to_datetime(["2020-01-01", "2020-01-01", "2020-01-01", None]),
                  "src": ["sp500"] * 4}).to_parquet(
        tmp_path / "breadth" / "sp1500_pit_membership.parquet")
    (tmp_path / "edgar" / "dead_name_cik.json").write_text(json.dumps({
        "DEAD1": {"cik": 1, "method": "seed"},
        "DEAD2": {"cik": 2, "method": "company_tickers"},
        "DEAD3": {"cik": None, "method": "unresolved"}}))
    pd.DataFrame({"ticker": ["DEAD1"], "fy": [2019]}).to_parquet(
        tmp_path / "edgar" / "dead_name_panel.parquet")
    cov = dn.coverage()
    assert cov["n_dead_universe"] == 3
    assert cov["n_cik_resolved"] == 2
    assert cov["n_with_fundamentals"] == 1
    assert cov["coverage_frac"] == pytest.approx(1 / 3, abs=1e-4)
    assert cov["resolved_by_method"] == {"seed": 1, "company_tickers": 1}


# --------------------------------------------------------------------------- #
# CIK resolution — seed precedence guards ticker reuse
# --------------------------------------------------------------------------- #
def test_resolve_seed_beats_company_tickers(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    # company_tickers maps ATVI to a WRONG (reused) cik; the audited seed must win
    (tmp_path / "edgar" / "company_tickers.json").write_text(
        json.dumps({"0": {"ticker": "ATVI", "cik_str": 555}}))
    out = dn.resolve_dead_ciks(["ATVI"], use_polygon=False)
    assert out["ATVI"]["cik"] == dn._KNOWN_DEAD_CIK["ATVI"]
    assert out["ATVI"]["method"] == "seed"


def test_resolve_records_unresolved(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    out = dn.resolve_dead_ciks(["ZZZZ_NOPE"], use_polygon=False)
    assert out["ZZZZ_NOPE"]["cik"] is None
    assert out["ZZZZ_NOPE"]["method"] == "unresolved"
    # persisted
    cache = json.loads((tmp_path / "edgar" / "dead_name_cik.json").read_text())
    assert "ZZZZ_NOPE" in cache
