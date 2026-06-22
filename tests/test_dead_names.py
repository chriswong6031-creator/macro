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


# --------------------------------------------------------------------------- #
# Half 1b — EDGAR full-text crawl (windowed · dominance-gated · submissions-confirmed)
#
# The SEC submissions doc carries NO former-ticker field (verified: acquired names
# return tickers=[]), so a bare dead ticker can only be bridged through EDGAR
# full-text search of the cover-page symbol. These tests pin the load-bearing
# guards — all NETWORK-FREE (the efts + submissions fetchers are monkeypatched):
#   * DOMINANCE — an ambiguous result resolves NOTHING (a wrong CIK is worse than none).
#   * REUSE / NAME-COINCIDENCE — a live entity under a DIFFERENT current symbol is
#     rejected by the submissions confirmation, even at high dominance.
#   * PRECEDENCE — seed / company_tickers / polygon are never clobbered.
#   * RESUMABILITY — drip cap honored; fresh attempts not re-queried.
# --------------------------------------------------------------------------- #
def _efts_payload(buckets):
    """Build an efts-shaped response from [(cik, name, doc_count)]: the entity_filter
    aggregation embeds the CIK in each bucket key exactly as EDGAR FTS does."""
    return {"hits": {"total": {"value": sum(b[2] for b in buckets)}},
            "aggregations": {"entity_filter": {"buckets": [
                {"key": f"{nm}  (CIK {cik:010d})", "doc_count": docs}
                for cik, nm, docs in buckets]}}}


def _write_membership(tmp_path, dead_windows, live=("LIVE",)):
    """sp1500_pit_membership.parquet with the given dead stints + a live (never-exited)
    name so dead_universe()/_dead_windows() exclude currently-listed symbols."""
    (tmp_path / "breadth").mkdir(parents=True, exist_ok=True)
    rows = [{"ticker": t, "start_date": pd.Timestamp(s), "end_date": pd.Timestamp(e),
             "src": "sp500"} for t, (s, e) in dead_windows.items()]
    rows += [{"ticker": t, "start_date": pd.Timestamp("2010-01-01"),
              "end_date": pd.NaT, "src": "sp500"} for t in live]
    pd.DataFrame(rows).to_parquet(tmp_path / "breadth" / "sp1500_pit_membership.parquet")


def _boom(*a, **k):
    raise AssertionError("fetcher called when it should not have been")


def test_entity_buckets_parses_cik_and_sorts():
    data = _efts_payload([(111, "SMALL CO", 2), (743988, "XILINX INC", 41)])
    bk = dn._entity_buckets(data)
    assert bk[0] == (743988, "XILINX INC  (CIK 0000743988)", 41)   # doc_count-desc
    assert bk[1][0] == 111
    # a bucket whose key has no CIK token is skipped, not crashed
    assert dn._entity_buckets(
        {"aggregations": {"entity_filter": {"buckets": [{"key": "NO CIK", "doc_count": 9}]}}}) == []
    assert dn._entity_buckets(None) == []


def test_dominant_cik_threshold():
    assert dn._dominant_cik([(7, "A", 41), (8, "B", 2)])[0] == 7      # clear dominator
    assert dn._dominant_cik([(7, "A", 3), (8, "B", 0)])[0] is None    # below MIN_DOCS
    assert dn._dominant_cik([(7, "A", 20), (8, "B", 12)])[0] is None  # runner too close (<2.5x)
    assert dn._dominant_cik([(7, "A", 6)])[0] == 7                    # sole entity, enough docs
    assert dn._dominant_cik([])[0] is None


def test_dead_windows_clamps_to_fts_floor(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    _write_membership(tmp_path, {"OLD": ("1996-01-02", "2010-06-01")})
    w = dn._dead_windows()
    assert w["OLD"][0] == dn.EFTS_MIN_DATE              # start clamped to 2001
    assert w["OLD"][1] == "2011-06-01"                  # end padded +1y past index exit
    assert "LIVE" not in w                              # currently-listed names excluded


def test_fts_accepts_acquired_empty_ticker(monkeypatch, tmp_path):
    """Atwood-shaped: acquired filer (current tickers EMPTY), dominant in-window, last
    10-K within the grace window, symbol corroborated by the name (ATW⊂ATWOOD) →
    accepted, written as method=edgar_fts."""
    _redirect(monkeypatch, tmp_path)
    _write_membership(tmp_path, {"ATW": ("2012-01-01", "2017-06-01")})
    monkeypatch.setattr(dn, "_efts_search",
                        lambda t, s, e, *a, **k: _efts_payload([(8411, "ATWOOD OCEANICS INC", 18),
                                                                (999, "OTHER CO", 5)]))
    monkeypatch.setattr(dn, "_get_json", lambda url, *a, **k: {
        "name": "ATWOOD OCEANICS INC", "tickers": [], "formerNames": [],
        "filings": {"recent": {"form": ["10-K"], "filingDate": ["2017-11-20"]}}})
    fts = dn.resolve_via_fulltext(max_new=10)
    assert fts["ATW"]["status"] == "resolved" and fts["ATW"]["cik"] == 8411
    cik = json.loads((tmp_path / "edgar" / "dead_name_cik.json").read_text())
    assert cik["ATW"] == {"cik": 8411, "method": "edgar_fts"}


def test_ticker_in_name_subsequence():
    assert dn._ticker_in_name("ATW", ["ATWOOD OCEANICS INC"])      # A·T·Wood
    assert dn._ticker_in_name("SPLS", ["STAPLES INC"])             # S·ta·P·L·e·S
    assert dn._ticker_in_name("XLNX", ["XILINX INC"])
    assert dn._ticker_in_name("BCR", ["BARD C R INC /NJ/"])
    assert not dn._ticker_in_name("ANDV", ["AMERICAN NATIONAL INSURANCE CO"])  # no D → reject
    assert dn._ticker_in_name("WTW", ["WERNER CO", "WILLIS TOWERS WATSON"])    # matches a FORMER name
    assert not dn._ticker_in_name("ZZ9", ["NOTHING HERE"])


def test_fts_rejects_coincidence_without_name_corroboration(monkeypatch, tmp_path):
    """ANDV→'American National Insurance': acquired filer (empty current tickers, so
    the live-mismatch guard can't fire) coincidentally dense in the string 'ANDV',
    but the symbol is NOT a subsequence of its name → rejected. NEVER mis-resolve."""
    _redirect(monkeypatch, tmp_path)
    _write_membership(tmp_path, {"ANDV": ("2007-01-01", "2018-10-01")})
    monkeypatch.setattr(dn, "_efts_search",
                        lambda *a, **k: _efts_payload([(904163, "AMERICAN NATIONAL INSURANCE CO", 10),
                                                       (5, "X", 1)]))
    monkeypatch.setattr(dn, "_get_json", lambda url, *a, **k: {
        "name": "AMERICAN NATIONAL INSURANCE CO", "tickers": [], "formerNames": [],
        "filings": {"recent": {"form": ["10-K"], "filingDate": ["2019-03-01"]}}})
    fts = dn.resolve_via_fulltext(max_new=10)
    assert fts["ANDV"]["status"] == "reject_no_name_corroboration"
    cik = json.loads((tmp_path / "edgar" / "dead_name_cik.json").read_text())
    assert cik.get("ANDV", {}).get("cik") is None


def test_fts_rejects_live_name_coincidence(monkeypatch, tmp_path):
    """APPS→'Cyber Apps World': a phrase hit on the word in the name, but the entity
    is LIVE under a different current symbol → rejected by submissions confirm even
    though it clears dominance. NEVER mis-resolve."""
    _redirect(monkeypatch, tmp_path)
    _write_membership(tmp_path, {"APPS": ("2019-01-01", "2021-01-01")})
    monkeypatch.setattr(dn, "_efts_search",
                        lambda *a, **k: _efts_payload([(1230524, "Cyber Apps World", 20),
                                                       (5, "OTHER", 8)]))
    monkeypatch.setattr(dn, "_get_json", lambda url, *a, **k: {
        "name": "Cyber Apps World", "tickers": ["CYAP"], "formerNames": [],
        "filings": {"recent": {"form": ["10-K"], "filingDate": ["2021-05-01"]}}})
    fts = dn.resolve_via_fulltext(max_new=10)
    assert fts["APPS"]["status"] == "reject_live_mismatch"
    cik = json.loads((tmp_path / "edgar" / "dead_name_cik.json").read_text())
    assert cik.get("APPS", {}).get("cik") is None      # not written


def test_fts_rejects_still_active(monkeypatch, tmp_path):
    """A dominant CIK whose latest annual report is years past the index exit is not
    the delisted company → rejected (recency guard)."""
    _redirect(monkeypatch, tmp_path)
    _write_membership(tmp_path, {"GONE": ("2010-01-01", "2014-01-01")})
    monkeypatch.setattr(dn, "_efts_search",
                        lambda *a, **k: _efts_payload([(321, "STILL FILING INC", 30), (9, "X", 4)]))
    monkeypatch.setattr(dn, "_get_json", lambda url, *a, **k: {
        "name": "STILL FILING INC", "tickers": [], "formerNames": [],
        "filings": {"recent": {"form": ["10-K"], "filingDate": ["2024-02-01"]}}})
    fts = dn.resolve_via_fulltext(max_new=10)
    assert fts["GONE"]["status"] == "reject_still_active"


def test_fts_no_dominant_leaves_unresolved_without_confirming(monkeypatch, tmp_path):
    """Ambiguous result → no submissions fetch, nothing written."""
    _redirect(monkeypatch, tmp_path)
    _write_membership(tmp_path, {"AMB": ("2007-01-01", "2015-01-01")})
    monkeypatch.setattr(dn, "_efts_search",
                        lambda *a, **k: _efts_payload([(1, "A", 17), (2, "B", 14)]))  # 17 < 2.5*14
    monkeypatch.setattr(dn, "_get_json", _boom)        # confirmation must NOT run
    fts = dn.resolve_via_fulltext(max_new=10)
    assert fts["AMB"]["status"] == "no_dominant"
    assert not (tmp_path / "edgar" / "dead_name_cik.json").exists() or \
        json.loads((tmp_path / "edgar" / "dead_name_cik.json").read_text()).get("AMB", {}).get("cik") is None


def test_fts_out_of_range_never_queries(monkeypatch, tmp_path):
    """Pre-2001 delistings are out of EDGAR FTS range → marked, never queried."""
    _redirect(monkeypatch, tmp_path)
    _write_membership(tmp_path, {"PRE": ("1996-01-01", "1999-06-01")})
    monkeypatch.setattr(dn, "_efts_search", _boom)
    fts = dn.resolve_via_fulltext(max_new=10)
    assert fts["PRE"]["status"] == "out_of_range"


def test_fts_transient_error_retries_next_run(monkeypatch, tmp_path):
    """A None from efts (5xx/timeout) caches status=error and is re-attempted on the
    next run — never frozen as a false miss."""
    _redirect(monkeypatch, tmp_path)
    _write_membership(tmp_path, {"FLAKY": ("2012-01-01", "2018-01-01")})
    monkeypatch.setattr(dn, "_efts_search", lambda *a, **k: None)
    monkeypatch.setattr(dn, "_get_json", _boom)
    fts = dn.resolve_via_fulltext(max_new=10)
    assert fts["FLAKY"]["status"] == "error"
    assert dn._fts_stale(fts["FLAKY"]) is False        # fresh error not retried THIS run...
    fts["FLAKY"]["attempted_utc"] = "2000-01-01T00:00:00+00:00"
    assert dn._fts_stale(fts["FLAKY"]) is True          # ...but a stale one is


def test_fts_drip_cap_and_resume(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    _write_membership(tmp_path, {f"D{i}": ("2015-01-01", "2019-01-01") for i in range(5)})
    calls = {"n": 0}

    def counted(*a, **k):
        calls["n"] += 1
        return _efts_payload([(1, "A", 1)])            # below MIN → no_dominant

    monkeypatch.setattr(dn, "_efts_search", counted)
    dn.resolve_via_fulltext(max_new=2)
    assert calls["n"] == 2                              # cap honored
    dn.resolve_via_fulltext(max_new=2)                 # fresh no_dominant skipped → next batch
    assert calls["n"] == 4


def test_fts_never_clobbers_resolved(monkeypatch, tmp_path):
    """A ticker already resolved (seed) is not even queried, let alone overwritten."""
    _redirect(monkeypatch, tmp_path)
    _write_membership(tmp_path, {"SEEDED": ("2015-01-01", "2019-01-01")})
    (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
    (tmp_path / "edgar" / "dead_name_cik.json").write_text(
        json.dumps({"SEEDED": {"cik": 42, "method": "seed"}}))
    monkeypatch.setattr(dn, "_efts_search", _boom)
    dn.resolve_via_fulltext(max_new=10)
    cik = json.loads((tmp_path / "edgar" / "dead_name_cik.json").read_text())
    assert cik["SEEDED"] == {"cik": 42, "method": "seed"}


def test_coverage_reports_fts_funnel(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    (tmp_path / "breadth").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": ["DEAD1", "DEAD2"],
                  "start_date": pd.to_datetime(["2010-01-01"] * 2),
                  "end_date": pd.to_datetime(["2020-01-01", "2020-01-01"]),
                  "src": ["sp500"] * 2}).to_parquet(
        tmp_path / "breadth" / "sp1500_pit_membership.parquet")
    (tmp_path / "edgar" / "dead_name_cik.json").write_text(json.dumps({
        "DEAD1": {"cik": 1, "method": "edgar_fts"}}))
    (tmp_path / "edgar" / "_dead_name_fts.json").write_text(json.dumps({
        "DEAD1": {"status": "resolved", "cik": 1},
        "DEAD2": {"status": "no_dominant"}}))
    cov = dn.coverage()
    assert cov["resolved_by_method"] == {"edgar_fts": 1}
    assert cov["fts_funnel"] == {"resolved": 1, "no_dominant": 1}
