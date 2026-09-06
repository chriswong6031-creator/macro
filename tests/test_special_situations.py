"""Special Situations collector (collectors/special_situations.py, Phase-1 Lane A).

Pins the pure, network-free pieces of the EDGAR event collector:
- the daily-index .idx parser (form filter + fixed-width field extraction + the
  accession/source-url derivation),
- the EFTS 8-K item gate (keep special-situations items, drop the rest, pass
  structured forms through, and the fail-open fallback when EFTS is down),
- the append-only event store's keep-FIRST guarantee (first_seen / earliest source
  is never overwritten when a filing is re-discovered or amended),
- quarter math + the weekday-only daily-index sweep window.

These are the load-bearing invariants: the collector must capture Schedule 13D/A
(which EFTS cannot see) and must never lose the first market-observable timestamp.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

from lib import config
from collectors import special_situations as ss
from engine import special_situations as sse
from scripts import ingest_digest_db as idb
from scripts import backtest_special_situations as bt
from datetime import date, datetime, timezone


# ---- fixtures ---------------------------------------------------------------
SAMPLE_IDX = """Description:           Daily Index of EDGAR Dissemination Feed by Form Type
Last Data Received:    Jun 12, 2026
Comments:              webmaster@sec.gov

Form Type   Company Name                                                  CIK      Date Filed  File Name
---------------------------------------------------------------------------------------------------------------------------------------------
SC 13D/A         GENCO SHIPPING & TRADING LTD                            1326200     20260612    edgar/data/1326200/0001104659-26-074497.txt
DEFM14A          KORE Group Holdings, Inc.                               1855457     20260612    edgar/data/1855457/0001140361-26-025086.txt
8-K              ACADIA REALTY TRUST                                     899629      20260612    edgar/data/899629/0001193125-26-269000.txt
8-K              BORING REG-FD CO                                        222         20260612    edgar/data/222/0001193125-26-111111.txt
6-K              AKANDA CORP.                                            1888014     20260612    edgar/data/1888014/0001493152-26-002222.txt
10-K             SHOULD BE IGNORED INC                                   333         20260612    edgar/data/333/0001-26-3.txt
"""


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


# ---- .idx parser ------------------------------------------------------------
def test_parse_idx_filters_to_target_forms():
    rows = ss._parse_idx(SAMPLE_IDX)
    forms = {r["form_type"] for r in rows}
    assert forms == {"SC 13D/A", "DEFM14A", "8-K", "6-K"}      # 10-K excluded
    assert len(rows) == 5                                       # two 8-Ks both kept here


def test_parse_idx_extracts_fields_and_accession():
    rows = {r["form_type"]: r for r in ss._parse_idx(SAMPLE_IDX) if r["form_type"] != "8-K"}
    g = rows["SC 13D/A"]
    assert g["company"] == "GENCO SHIPPING & TRADING LTD"      # name with internal spaces preserved
    assert g["cik"] == "1326200"
    assert g["date_filed"] == "2026-06-12"
    assert g["accession"] == "0001104659-26-074497"
    assert g["id"] == g["accession"]
    assert g["source_lane"] == "edgar"
    # source_url points at the human-readable filing index page (dash-stripped accession dir)
    assert g["source_url"] == (
        "https://www.sec.gov/Archives/edgar/data/1326200/"
        "000110465926074497/0001104659-26-074497-index.htm"
    )


def test_parse_idx_captures_schedule_13d():
    """13D/A is the EFTS blind spot — the daily index is the only place we see it."""
    assert any(r["form_type"] == "SC 13D/A" for r in ss._parse_idx(SAMPLE_IDX))


# ---- EFTS 8-K item gate -----------------------------------------------------
def _rows_for_enrich():
    return [r for r in ss._parse_idx(SAMPLE_IDX)]


def test_enrich_keeps_special_item_8k_and_drops_others():
    efts = {
        "0001193125-26-269000": {"items": ["8.01", "9.01"], "biz_locations": ["Rye, NY"],
                                 "inc_states": ["MD"], "sics": ["6798"]},
        "0001193125-26-111111": {"items": ["7.01"], "biz_locations": ["X"],   # Reg FD only
                                 "inc_states": ["DE"], "sics": ["1000"]},
    }
    out = ss._enrich_eight_ks(_rows_for_enrich(), efts)
    by_acc = {r["accession"]: r for r in out}
    # the 8.01 8-K survives and is enriched
    assert "0001193125-26-269000" in by_acc
    kept = by_acc["0001193125-26-269000"]
    assert kept["items"] == "8.01|9.01"
    assert kept["biz_locations"] == "Rye, NY"
    # the Reg-FD-only 8-K is dropped
    assert "0001193125-26-111111" not in by_acc
    # structured forms always pass through untouched
    assert any(r["form_type"] == "DEFM14A" for r in out)
    assert any(r["form_type"] == "6-K" for r in out)


def test_enrich_failopen_when_efts_empty():
    """If EFTS is down (empty map), 8-Ks are kept flagged rather than silently lost."""
    out = ss._enrich_eight_ks(_rows_for_enrich(), {})
    eights = [r for r in out if r["form_type"] == "8-K"]
    assert len(eights) == 2
    assert all(r.get("items_unknown") for r in eights)


# ---- append-only store: keep-FIRST -----------------------------------------
def test_save_events_dedups_keep_first(tmp_store):
    first = [{"id": "A", "form_type": "DEFM14A", "company": "ORIGINAL"}]
    ss._save_events(first)
    again = [{"id": "A", "form_type": "DEFM14A", "company": "AMENDED-LATER"},
             {"id": "B", "form_type": "SC 13D/A", "company": "NEW"}]
    merged = ss._save_events(again)
    by_id = {r.id: r for r in merged.itertuples()}
    assert len(merged) == 2
    assert by_id["A"].company == "ORIGINAL"          # keep-first: re-discovery does not overwrite
    assert by_id["B"].company == "NEW"


def test_save_events_preserves_first_seen(tmp_store):
    ss._save_events([{"id": "A", "form_type": "DEFM14A", "company": "X"}])
    fs1 = ss._read_events().set_index("id").loc["A", "first_seen"]
    ss._save_events([{"id": "A", "form_type": "DEFM14A", "company": "X"}])
    fs2 = ss._read_events().set_index("id").loc["A", "first_seen"]
    assert fs1 == fs2                                  # first_seen is immutable


# ---- date math --------------------------------------------------------------
def test_qtr():
    assert ss._qtr(date(2026, 1, 1)) == 1
    assert ss._qtr(date(2026, 4, 30)) == 2
    assert ss._qtr(date(2026, 6, 18)) == 2
    assert ss._qtr(date(2026, 12, 31)) == 4


def test_dates_to_sweep_skips_weekends_and_honors_watermark(tmp_store, monkeypatch):
    # no watermark -> backfill window; weekends excluded
    monkeypatch.setattr(ss, "_load_meta", lambda: {})
    monkeypatch.setattr(ss, "_cfg", lambda: {"backfill_days": 7})
    days = ss._dates_to_sweep(date(2026, 6, 18))       # Thu
    assert date(2026, 6, 13) not in days              # Sat
    assert date(2026, 6, 14) not in days              # Sun
    assert date(2026, 6, 18) in days
    assert all(d.weekday() < 5 for d in days)
    # with a watermark, sweep starts the day after it
    monkeypatch.setattr(ss, "_load_meta", lambda: {"last_index_date": "2026-06-16"})
    days2 = ss._dates_to_sweep(date(2026, 6, 18))
    assert days2 == [date(2026, 6, 17), date(2026, 6, 18)]


# =========================================================================
# Engine (engine/special_situations.py) — classifier / floor / cross-border
# =========================================================================

def test_engine_is_display_only_leaf():
    """Load-bearing honesty invariant: the desk is context-only, never scored,
    and must not pull the scoring path into the import graph. Checked in a FRESH
    subprocess so the result is independent of whatever other tests imported into
    this process's sys.modules (the invariant is about THIS module's import graph)."""
    import subprocess
    import sys
    assert sse.SCORED is False
    code = (
        "import sys, engine.special_situations\n"
        "bad=[m for m in ('engine.regime','engine.conditions','engine.run','conditions') "
        "if m in sys.modules]\n"
        "raise SystemExit('pulled scoring path: '+repr(bad) if bad else 0)"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=str(config.ROOT))
    assert r.returncode == 0, (r.stdout + r.stderr)


def test_classify_structured_forms():
    assert sse.classify("SC 13D") == ("Activist Campaigns", "initiated", "ok")
    assert sse.classify("SC 13D/A") == ("Activist Campaigns", "escalation", "ok")
    assert sse.classify("DEFM14A") == ("Acquisitions", "vote-scheduled", "ok")
    assert sse.classify("SC 13E3") == ("Going-Private", "live", "ok")
    assert sse.classify("SC TO-I") == ("Issuer Tenders", "live", "ok")
    assert sse.classify("SC TO-T") == ("Tender Offers", "live", "ok")
    assert sse.classify("DEFC14A") == ("Activist Campaigns", "proxy-fight", "ok")
    assert sse.classify("25-NSE") == ("Delistings", "live", "ok")
    assert sse.classify("10-12B") == ("Spin-Offs", "registered", "ok")


def test_classify_8k_items():
    assert sse.classify("8-K", "1.03|9.01") == ("Restructuring", "filed", "ok")
    assert sse.classify("8-K", "3.01") == ("Delistings", "notice", "ok")
    # 1.02 fires for ANY contract termination -> text lane confirms deal-context
    assert sse.classify("8-K", "1.02")[2] == "defer"
    # ambiguous M&A / strategic-review / capital-return items -> text lane
    assert sse.classify("8-K", "1.01|9.01")[2] == "defer"
    assert sse.classify("8-K", "8.01")[2] == "defer"
    assert sse.classify("8-K", "2.01")[2] == "defer"
    # routine officer change -> provisional, resolved in build_situations
    # routine officer change (5.02) is not a situation (0% precision vs digest)
    assert sse.classify("8-K", "5.02") == (None, None, "skip")
    # plain Reg-FD only -> not a situation
    assert sse.classify("8-K", "7.01") == (None, None, "skip")


def test_classify_skip_and_defer_forms():
    assert sse.classify("SC 13G")[2] == "skip"        # passive
    assert sse.classify("SC 13G/A")[2] == "skip"
    assert sse.classify("6-K")[2] == "defer"          # foreign — needs text
    assert sse.classify("424B5")[2] == "defer"        # rights vs shelf — needs text


def test_apply_floor():
    assert sse.apply_floor(150.0, 100) is True
    assert sse.apply_floor(50.0, 100) is False
    assert sse.apply_floor(None, 100) is None         # unknown mc kept & flagged


def test_passes_floor_confidence_gate():
    # >= $100M always passes; unknown mc kept
    assert sse.passes_floor(150.0, "low") is True
    assert sse.passes_floor(None, "low") is True
    # $25M-$100M: only HIGH confidence passes (structured/LLM-verified/digest)
    assert sse.passes_floor(40.0, "high") is True
    assert sse.passes_floor(40.0, "low") is False
    assert sse.passes_floor(40.0, "medium") is False
    # below the relaxed floor: dropped even at high confidence
    assert sse.passes_floor(10.0, "high") is False


def test_cross_border():
    import pandas as pd
    assert sse._is_cross_border(pd.Series({"form_type": "6-K"})) is True
    assert sse._is_cross_border(pd.Series({"form_type": "8-K", "inc_states": "E9"})) is True   # foreign code
    assert sse._is_cross_border(pd.Series({"form_type": "8-K", "inc_states": "DE"})) is False
    assert sse._is_cross_border(pd.Series({"form_type": "8-K", "biz_locations": "Rye, NY"})) is False


def _events(rows):
    import pandas as pd
    return pd.DataFrame(rows)


def test_build_going_private_upgrade(tmp_path, monkeypatch):
    """A merger proxy whose filer also filed an SC 13E-3 is an affiliate take-private."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    _events([
        {"id": "1", "form_type": "DEFM14A", "company": "KORE", "cik": "1855457", "items": None, "date_filed": "2026-06-12"},
        {"id": "2", "form_type": "SC 13E3/A", "company": "KORE", "cik": "1855457", "items": None, "date_filed": "2026-06-15"},
        {"id": "3", "form_type": "DEFM14A", "company": "PLAIN MERGER", "cik": "999", "items": None, "date_filed": "2026-06-12"},
    ]).to_parquet(tmp_path / "special_situations" / "events.parquet")
    df = sse.build_situations().set_index("id")
    assert df.loc["1", "category"] == "Going-Private"      # upgraded (filer has 13E-3)
    assert df.loc["3", "category"] == "Acquisitions"       # plain merger, no 13E-3


def test_build_spac_reclassification(tmp_path, monkeypatch):
    """A de-SPAC S-4 / merger proxy from a blank-check shell is a SPAC, not an Acquisition."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    _events([
        {"id": "1", "form_type": "S-4", "company": "Pono Capital Acquisition Corp", "cik": "1", "items": None, "date_filed": "2026-06-12"},
        {"id": "2", "form_type": "DEFM14A", "company": "Acme Industrials, Inc.", "cik": "2", "items": None, "date_filed": "2026-06-12"},
    ]).to_parquet(tmp_path / "special_situations" / "events.parquet")
    df = sse.build_situations().set_index("id")
    assert df.loc["1", "category"] == "SPACs"          # name has "Acquisition Corp"
    assert df.loc["2", "category"] == "Acquisitions"   # ordinary merger


def test_build_delisting_dedup_per_filer_day(tmp_path, monkeypatch):
    """Multi-security-class Form 25s (common + warrants + units) collapse to one event."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    _events([
        {"id": "a", "form_type": "25-NSE", "company": "Pono Corp", "cik": "5", "items": None, "date_filed": "2026-06-12"},
        {"id": "b", "form_type": "25-NSE", "company": "Pono Corp", "cik": "5", "items": None, "date_filed": "2026-06-12"},
        {"id": "c", "form_type": "25-NSE", "company": "Pono Corp", "cik": "5", "items": None, "date_filed": "2026-06-12"},
    ]).to_parquet(tmp_path / "special_situations" / "events.parquet")
    df = sse.build_situations()
    ok = df[(df.category == "Delistings") & (df.status == "ok")]
    assert len(ok) == 1                                  # collapsed to a single delisting event


def test_build_502_dropped(tmp_path, monkeypatch):
    """Routine officer-change 8-Ks (Item 5.02) are never situations (0% precision vs digest)."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    _events([
        {"id": "a", "form_type": "8-K", "company": "ROUTINE CO", "cik": "111", "items": "5.02", "date_filed": "2026-06-12"},
        {"id": "b", "form_type": "8-K", "company": "ACTIVIST TGT", "cik": "222", "items": "5.02", "date_filed": "2026-06-12"},
        {"id": "c", "form_type": "SC 13D", "company": "ACTIVIST TGT", "cik": "222", "items": None, "date_filed": "2026-06-11"},
    ]).to_parquet(tmp_path / "special_situations" / "events.parquet")
    df = sse.build_situations().set_index("id")
    assert df.loc["a", "status"] == "skip"
    assert df.loc["b", "status"] == "skip"                 # 5.02 dropped even for an activist target
    assert df.loc["c", "category"] == "Activist Campaigns"  # the 13D is the situation


def test_classify_text_keyword_lane():
    assert sse.classify_text("the Company entered into an Agreement and Plan of Merger to be acquired")[0] == "Acquisitions"
    assert sse.classify_text("definitive agreement to sell its packaging business")[0] == "Divestitures"
    assert sse.classify_text("the board is exploring strategic alternatives")[0] == "Strategic Reviews"
    assert sse.classify_text("announced a new $500 million share repurchase program")[0] == "Capital Returns"
    assert sse.classify_text("the parties mutually agreed to terminate the merger agreement")[0] == "Deal Terminations"
    assert sse.classify_text("intends to separate into two independent public companies via spin-off")[0] == "Spin-Offs"
    assert sse.classify_text("entered into a routine office lease and a credit facility")[0] is None


def test_noise_filer_dropped(tmp_path, monkeypatch):
    import pandas as pd
    assert sse._is_noise_filer("HYUNDAI ABS FUNDING LLC") is True
    assert sse._is_noise_filer("GraniteShares ETF Trust") is True
    assert sse._is_noise_filer("NYSE ARCA, INC.") is True
    assert sse._is_noise_filer("Amneal Pharmaceuticals, Inc.") is False
    # end-to-end: a securitization shell is skipped even with a classifiable form
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    _events([
        {"id": "1", "form_type": "25-NSE", "company": "HYUNDAI ABS FUNDING LLC", "cik": "1", "items": None, "date_filed": "2026-06-12"},
        {"id": "2", "form_type": "SC 13D", "company": "REAL CO", "cik": "2", "items": None, "date_filed": "2026-06-12"},
    ]).to_parquet(tmp_path / "special_situations" / "events.parquet")
    df = sse.build_situations().set_index("id")
    assert df.loc["1", "status"] == "skip"
    assert df.loc["2", "status"] == "ok"


# =========================================================================
# Digest DB ingest (scripts/ingest_digest_db.py) + backtest helpers
# =========================================================================

def test_ingest_parse_usd_m():
    assert idb._parse_usd_m("$153M") == 153.0
    assert idb._parse_usd_m("$12.9B") == 12900.0
    assert idb._parse_usd_m("$2M") == 2.0
    assert idb._parse_usd_m("$4.5T") == 4500000.0
    assert idb._parse_usd_m("¥2.6T") is None        # non-USD kept out of the USD column
    assert idb._parse_usd_m(None) is None


def test_ingest_parse_price():
    assert idb._parse_price("CAD 31.76") == (31.76, "CAD")
    assert idb._parse_price("$5.20") == (5.20, "USD")
    assert idb._parse_price(None) == (None, None)


def test_ingest_parse_metrics():
    m = idb._parse_metrics("Fwd P/E: 10.4x · EV/EBITDA: 5.8x · EV/Sales: 3.0x · EV/GP: 9.5x (FY2026)")
    assert m == {"fwd_pe": 10.4, "ev_ebitda": 5.8, "ev_sales": 3.0, "ev_gp": 9.5}
    assert idb._parse_metrics("EV/GP: 6.2x") == {"ev_gp": 6.2}
    assert idb._parse_metrics(None) == {}


def test_ingest_source_bucket():
    assert idb._bucket("https://www.sec.gov/x")[0] == "SEC EDGAR"
    assert idb._bucket("https://www.sedarplus.ca/x")[0] == "Canada SEDAR+"
    assert idb._bucket("https://disclosure2.edinet-fsa.go.jp/x")[0] == "Japan EDINET/TDnet"
    assert idb._bucket("https://www.tradingview.com/x")[0] == "Data platform"
    assert idb._bucket(None) == (None, "(none)")


def test_backtest_forward_return():
    import pandas as pd
    s = pd.Series([100.0, 101, 102, 103, 104, 110])   # +5 from pos0 -> 110/100-1 = .10
    assert round(bt._fwd(s, 0, 5), 4) == 0.10
    assert bt._fwd(s, 0, 99) is None                   # not enough forward data
    assert bt._fwd(s, 3, 2) == round(110 / 103 - 1, 10) or abs(bt._fwd(s, 3, 2) - (110/103 - 1)) < 1e-9


def test_backtest_agg_stage_groups():
    import pandas as pd
    btdf = pd.DataFrame([
        {"category": "Going-Private", "stage": "live", "ticker": "A", "r5": 0.01, "r20": 0.02, "r60": 0.03, "x5": 0.0, "x20": 0.01, "x60": 0.0},
        {"category": "Going-Private", "stage": "live", "ticker": "B", "r5": 0.03, "r20": 0.04, "r60": 0.05, "x5": 0.0, "x20": 0.02, "x60": 0.0},
        {"category": "Going-Private", "stage": "closed", "ticker": "C", "r5": -0.01, "r20": -0.02, "r60": None, "x5": 0.0, "x20": -0.01, "x60": None},
    ])
    res = bt._agg_stage(btdf)
    rows = {(r.category, r.stage): r for _, r in res.iterrows()}
    assert (("Going-Private", "live") in rows) and (("Going-Private", "closed") in rows)
    assert rows[("Going-Private", "live")].n == 2
    assert rows[("Going-Private", "live")].med_r20 == 3.0          # median of 2%, 4%


def test_backtest_run_edgar_filing_date_entry(tmp_path, monkeypatch):
    """run_edgar enters at the first close STRICTLY AFTER the filing date (+1bd, PIT fix).

    The price on the filing day itself (idx[7]=2026-06-10) is set to 50; the next business
    day (idx[8]=2026-06-11) is set to 100. If entry were on the filing date, r5 would be
    computed off 50 and would be 1.20 (a 120% gain).  With the correct +1bd entry it is
    0.10 (a 10% gain from 100 to 110), confirming the look-ahead leak is closed.
    """
    import pandas as pd
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({1: "ABC"}, {"ABC": 500.0}))
    (tmp_path / "special_situations").mkdir()
    # filed 2026-06-10 == idx[7]
    _events([{"id": "1", "form_type": "SC 13D", "company": "ABC Inc", "cik": "1",
              "items": None, "date_filed": "2026-06-10"}]
            ).to_parquet(tmp_path / "special_situations" / "events.parquet")
    idx = pd.bdate_range("2026-06-01", periods=20)   # idx[7]=2026-06-10, idx[8]=2026-06-11
    prices = [100.0] * 7 + [50.0] + [100.0] * 4 + [110.0] * 8  # filing-day spike at idx[7]
    (tmp_path / "breadth").mkdir()
    pd.DataFrame({"ABC": prices}, index=idx).to_parquet(
        tmp_path / "breadth" / "_closes_cache.parquet")
    btdf = bt.run_edgar()
    row = btdf.set_index("ticker").loc["ABC"]
    assert row["category"] == "Activist Campaigns" and row["stage"] in ("initiated", "—")
    # entry at idx[8]=100, +5d=idx[13]=110: r5 = 0.10 (NOT 1.20 from the filing-day 50)
    assert round(row["r5"], 4) == 0.10


def test_summary_lane_llm_ready_gate(monkeypatch):
    monkeypatch.setattr(config, "secret", lambda n: "key")
    assert ss._llm_ready({"enabled": True, "llm_brief": True}) is True
    assert ss._llm_ready({"enabled": True, "llm_brief": False}) is False
    assert ss._llm_ready({"enabled": False, "llm_brief": True}) is False
    monkeypatch.setattr(config, "secret", lambda n: None)
    assert ss._llm_ready({"enabled": True, "llm_brief": True}) is False   # no key


# ---- historical priors context (P5.1 consumption) ---------------------------
def test_prior_for_stage_then_category_fallback():
    stage_p = {("Going-Private", "live"): {"category": "Going-Private", "stage": "live",
                                           "n": 10, "win_20d_pct": 90.0, "med_ret_20d_pct": 0.5,
                                           "med_ret_60d_pct": 2.4}}
    cat_p = {"Going-Private": {"n": 50, "win_20d_pct": 65.0, "med_ret_20d_pct": 1.0,
                              "med_ret_60d_pct": 3.0}}
    # exact (category, stage) wins when it clears the sample floor
    p = sse._prior_for("Going-Private", "live", stage_p, cat_p)
    assert p["scope"] == "Going-Private · live" and p["win_20d_pct"] == 90.0
    # unknown stage -> category fallback
    p2 = sse._prior_for("Going-Private", "announced", stage_p, cat_p)
    assert p2["scope"] == "Going-Private" and p2["n"] == 50
    # thin (category, stage) below floor -> category fallback
    thin = {("Going-Private", "live"): {"category": "Going-Private", "stage": "live",
                                        "n": 2, "win_20d_pct": 100.0}}
    assert sse._prior_for("Going-Private", "live", thin, cat_p)["scope"] == "Going-Private"
    # nothing -> None
    assert sse._prior_for("Mystery", "x", stage_p, cat_p) is None


def test_attach_priors_and_desk_surfaces_it(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({1: "ABC"}, {}))
    (tmp_path / "special_situations").mkdir()
    (tmp_path / "special_situations" / "edgar_backtest_priors.json").write_text(json.dumps(
        {"by_category_stage": {"Acquisitions · vote-scheduled": {
            "category": "Acquisitions", "stage": "vote-scheduled", "n": 11,
            "win_20d_pct": 64.0, "med_ret_20d_pct": 1.2, "med_ret_60d_pct": 3.0}}}))
    pd.DataFrame([{"id": "e1", "form_type": "DEFM14A", "company": "ABC Inc", "cik": "1",
                   "items": None, "date_filed": "2026-06-17", "source_url": "u"}]
                 ).to_parquet(tmp_path / "special_situations" / "events.parquet")
    d = sse.desk_payload()
    abc = {s["ticker"]: s for s in d["situations"]}["ABC"]
    assert abc["prior"]["scope"] == "Acquisitions · vote-scheduled"
    assert abc["prior"]["win_20d_pct"] == 64.0
    assert d["coverage"]["with_prior"] >= 1


# ---- lifecycle / stage tracking (P3.1) --------------------------------------
def test_lifecycle_links_amendments(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    _events([
        {"id": "1", "form_type": "SC 13D", "company": "X", "cik": "7", "items": None, "date_filed": "2026-06-01"},
        {"id": "2", "form_type": "SC 13D/A", "company": "X", "cik": "7", "items": None, "date_filed": "2026-06-10"},
    ]).to_parquet(tmp_path / "special_situations" / "events.parquet")
    df = sse.build_situations().set_index("id")
    assert df.loc["2", "n_amendments"] == 1                 # one /A amendment in the timeline
    assert df.loc["2", "current_stage"] == "escalation"     # latest filing's stage
    lc = sse.lifecycle(sse.build_situations())
    assert lc[("7", "Activist Campaigns")]["n_filings"] == 2


def test_lifecycle_terminal_terminated(tmp_path, monkeypatch):
    """A filer with both a merger proxy AND a deal-termination event -> the deal reads 'terminated'."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    ev = _events([
        {"id": "1", "form_type": "DEFM14A", "company": "DealCo", "cik": "8", "items": None, "date_filed": "2026-05-01"},
        {"id": "2", "form_type": "8-K", "company": "DealCo", "cik": "8", "items": "1.02", "date_filed": "2026-06-01"},
    ])
    ev["text_category"] = [None, "Deal Terminations"]       # 1.02 + termination keyword -> promoted
    ev["text_stage"] = [None, "terminated"]
    ev.to_parquet(tmp_path / "special_situations" / "events.parquet")
    df = sse.build_situations().set_index("id")
    assert df.loc["1", "deal_terminal"] == "terminated"
    assert df.loc["1", "current_stage"] == "terminated"


def test_lifecycle_terminal_closed(tmp_path, monkeypatch):
    """An 8-K Item 2.01 (completion) by the deal filer flips the deal to 'closed' — even
    though the 2.01 8-K itself is only a deferred row."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    _events([
        {"id": "1", "form_type": "DEFM14A", "company": "DealCo", "cik": "9", "items": None, "date_filed": "2026-05-01"},
        {"id": "2", "form_type": "8-K", "company": "DealCo", "cik": "9", "items": "2.01", "date_filed": "2026-06-01"},
    ]).to_parquet(tmp_path / "special_situations" / "events.parquet")
    df = sse.build_situations().set_index("id")
    assert df.loc["1", "current_stage"] == "closed"
    assert df.loc["1", "deal_terminal"] == "closed"


# ---- LLM verify lane (P1.1) -------------------------------------------------
def test_parse_llm_json_robust():
    assert ss._parse_llm_json('{"category": "Acquisitions"}')["category"] == "Acquisitions"
    # tolerates a ```json fence
    assert ss._parse_llm_json('```json\n{"category": "Spin-Offs"}\n```')["category"] == "Spin-Offs"
    # tolerates leading prose
    assert ss._parse_llm_json('Here you go: {"category": "Other", "role": "filer"}')["role"] == "filer"
    assert ss._parse_llm_json("not json at all") == {}
    assert ss._parse_llm_json(None) == {}


class _FakeResp:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]


class _FakeClient:
    """Returns a fixed JSON reply for every messages.create call."""
    def __init__(self, text):
        self._text = text
        self.messages = self

    def create(self, **_kw):
        return _FakeResp(self._text)


def _mock_llm(monkeypatch, reply_json: str):
    monkeypatch.setattr(config, "secret", lambda n: "key")
    monkeypatch.setattr(ss, "_cfg", lambda: {"enabled": True, "llm_brief": True})
    monkeypatch.setattr(ss, "_llm_client", lambda cfg: (_FakeClient(reply_json), "deepseek-chat"))
    monkeypatch.setattr(ss, "_fetch_filing_text", lambda cik, acc, **kw: "filing body text")


def _seed_defer_event(tmp_path):
    (tmp_path / "special_situations").mkdir()
    pd.DataFrame([{"id": "e1", "form_type": "8-K", "company": "Acme Inc", "cik": "10",
                   "accession": "acc1", "items": "8.01", "date_filed": "2026-06-12",
                   "source_url": "u"}]
                 ).to_parquet(tmp_path / "special_situations" / "events.parquet")


def test_enrich_classify_writes_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _mock_llm(monkeypatch, '{"category": "Acquisitions", "role": "target", "confidence": "high",'
                           ' "summary": "Acme to be acquired for $25/sh cash.",'
                           ' "deal_terms": {"price_per_share": 25.0, "consideration": "cash"}}')
    _seed_defer_event(tmp_path)
    df = ss.enrich_classify().set_index("id")
    assert df.loc["e1", "llm_category"] == "Acquisitions"
    assert df.loc["e1", "llm_role"] == "target"
    assert df.loc["e1", "llm_confidence"] == "high"
    assert "price_per_share" in df.loc["e1", "llm_terms"]


def test_llm_verdict_promotes_in_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    _mock_llm(monkeypatch, '{"category": "Strategic Reviews", "role": "filer", "confidence": "high",'
                           ' "summary": "Board to explore alternatives.", "deal_terms": {}}')
    _seed_defer_event(tmp_path)
    ss.enrich_classify()
    df = sse.build_situations().set_index("id")
    assert df.loc["e1", "status"] == "ok"
    assert df.loc["e1", "category"] == "Strategic Reviews"
    assert df.loc["e1", "confidence"] == "high"          # LLM-verified, not the keyword 'low'
    assert df.loc["e1", "stage"] == "initiated"          # default stage for Strategic Reviews


def test_llm_management_changes_not_promoted(tmp_path, monkeypatch):
    """Verification found the LLM over-fires 'Management Changes' on routine foreign-6-K
    meeting/circular notices -> it must NOT auto-promote to the desk (stays unshown)."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    _mock_llm(monkeypatch, '{"category": "Management Changes", "role": "issuer",'
                           ' "confidence": "high", "summary": "AGM notice", "deal_terms": {}}')
    _seed_defer_event(tmp_path)
    ss.enrich_classify()
    df = sse.build_situations().set_index("id")
    assert df.loc["e1", "status"] != "ok"                 # not promoted to the desk
    assert df.loc["e1", "category"] != "Management Changes"
    assert "Management Changes" in sse.MATURE_CATEGORIES and "Management Changes" not in sse.LLM_PROMOTABLE


def test_llm_none_kills_false_positive(tmp_path, monkeypatch):
    """The precision fix: a deferred filing the LLM judges NOT a situation is dropped,
    even if the keyword text-lane had promoted it."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    _mock_llm(monkeypatch, '{"category": "None", "role": "none", "confidence": "high",'
                           ' "summary": "", "deal_terms": {}}')
    _seed_defer_event(tmp_path)
    # pretend the noisy keyword lane already (wrongly) promoted it
    df0 = ss._read_events()
    df0["text_category"] = "Acquisitions"
    df0["text_stage"] = "announced"
    df0.to_parquet(tmp_path / "special_situations" / "events.parquet")
    ss.enrich_classify()
    df = sse.build_situations().set_index("id")
    assert df.loc["e1", "status"] == "skip"              # LLM "None" overrides the keyword FP


def test_enrich_classify_noop_when_gated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ss, "_cfg", lambda: {"enabled": True, "llm_brief": False})  # gate off
    _seed_defer_event(tmp_path)
    df = ss.enrich_classify()
    assert df["llm_category"].isna().all()               # nothing classified, no network


def test_summary_lane_noop_when_gated(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ss, "_cfg", lambda: {"enabled": True, "llm_brief": False})  # gate off
    (tmp_path / "special_situations").mkdir()
    pd.DataFrame([{"id": "1", "form_type": "SC 13D", "company": "X", "cik": "1",
                   "accession": "a", "items": None, "date_filed": "2026-06-12"}]
                 ).to_parquet(tmp_path / "special_situations" / "events.parquet")
    df = ss.enrich_summaries()
    assert df["summary"].isna().all()                # nothing generated, no network


def test_desk_payload_merges_digest_and_edgar(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({1: "ABC"}, {}))   # cik 1 -> ABC
    (tmp_path / "special_situations").mkdir()
    # one digest situation (with summary) + EDGAR confirms the same ticker/category
    pd.DataFrame([{"id": 9, "ticker": "ABC", "company": "ABC Inc", "country": "US",
                   "category": "Acquisitions", "issue": 19, "issue_date": "2026-06-14",
                   "market_cap_musd": 500.0, "summary": "ABC to be acquired...", "source_url": "u1",
                   "business_desc": "b", "headline": "h"}]
                 ).to_parquet(tmp_path / "special_situations" / "digest_db.parquet")
    pd.DataFrame([{"id": "e1", "form_type": "DEFM14A", "company": "ABC Inc", "cik": "1",
                   "items": None, "date_filed": "2026-06-17", "source_url": "edgarurl"}]
                 ).to_parquet(tmp_path / "special_situations" / "events.parquet")
    d = sse.desk_payload()
    sits = {s["ticker"]: s for s in d["situations"]}
    assert "ABC" in sits
    assert sits["ABC"]["live"] is True                       # digest situation confirmed by EDGAR
    assert sits["ABC"]["summary"] == "ABC to be acquired..."  # digest summary used
    assert d["coverage"]["with_summary"] >= 1


def test_mastermind_emit_context_only(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    pd.DataFrame([{"id": 9, "ticker": "ABC", "company": "ABC Inc", "country": "US",
                   "category": "Acquisitions", "issue": 19, "issue_date": "2026-06-14",
                   "market_cap_musd": 500.0, "summary": "ABC deal", "source_url": "u", "headline": "h"}]
                 ).to_parquet(tmp_path / "special_situations" / "digest_db.parquet")
    e = sse.mastermind_emit()
    assert e["schema"] == "special_situations.v1" and e["is_context_only"] is True
    assert "ABC" in e["by_ticker"]
    assert e["by_ticker"]["ABC"]["category"] == "Acquisitions"


def test_snapshot_is_context_only(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    _events([
        {"id": "1", "form_type": "SC 13D", "company": "X", "cik": "1", "items": None, "date_filed": "2026-06-12"},
    ]).to_parquet(tmp_path / "special_situations" / "events.parquet")
    snap = sse.snapshot()
    assert snap["scored"] is False and snap["is_context_only"] is True
    assert "disclaimer" in snap
    assert snap["counts"].get("Activist Campaigns") == 1
    assert snap["coverage"]["floor_musd"] == 100.0


# ---- F09-1: evidence-bound cash-deal economics, end to end -------------------
#
# The published 42,790.2% annualized spread had essentially no test coverage: one
# `"risk_arb_top" in result` assertion stood between an ungrounded number and the machine
# context every Neural Web consumer reads. These pin the wiring, not just the pure math.

NOW_UTC = datetime(2026, 6, 18, 22, 0, tzinfo=timezone.utc)   # 18:00 ET, after the 06-18 close

_CASH_EXACT = ("Each share of common stock will be converted into the right to receive $25.00 "
               "in cash per share. The transaction is expected to close on December 15, 2026.")
_CASH_MONTH = ("Each share of common stock will be converted into the right to receive $25.00 "
               "in cash per share. The transaction is expected to close in November 2026.")
_ACC = "0000000001-26-000001"


def _submission(text: str, *, accepted: str = "20260617173100") -> bytes:
    """A minimal SEC full-submission body: SGML acceptance header + document text, as BYTES.

    The acceptance stamp is SEC EASTERN wall-clock, exactly as EDGAR writes it, because the
    reference session is derived from that instant and nothing else may stand in for it.
    """
    return (f"<SEC-DOCUMENT>x.txt<ACCEPTANCE-DATETIME>{accepted}\n<DOCUMENT>"
            f"{text}</DOCUMENT>").encode("utf-8")


def _yahoo_store(tmp_path, ticker, sessions, closes, *, column="close_price"):
    """The ONE price provenance V1 admits: `data/yahoo/<T>.parquet::close_price`."""
    d = tmp_path / "yahoo"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({column: list(closes)}, index=pd.to_datetime(sessions)).to_parquet(
        d / f"{ticker}.parquet")
    return d / f"{ticker}.parquet"


def _f09_env(tmp_path, monkeypatch, *, text, sessions, ticker="ABC", last_close=15.19,
             filed="2026-06-17", category="Acquisitions", accepted="20260617173100",
             accession=_ACC, price_column="close_price", run_producer=True):
    """A tmp data dir carrying one arb-category event, its RETAINED source object, the
    per-ticker Yahoo store, and a ledger written by the REAL producer.

    The ledger is no longer hand-built. It used to be assembled in the test from a source
    descriptor the test invented, so the test could not have caught either of the two defects
    that mattered: that the extractor read a legacy `doc_cache/*.txt` while the observation cited
    the retained object's digest, and that nothing ever re-opened those bytes at load time.
    Retaining a real submission and running `enrich_deal_terms()` exercises the actual seam.
    """
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({1: ticker}, {}))
    root = tmp_path / "special_situations"
    root.mkdir(exist_ok=True)
    pd.DataFrame([{"id": 9, "ticker": ticker, "company": f"{ticker} Inc", "country": "US",
                   "category": category, "issue": 19, "issue_date": "2026-06-14",
                   "market_cap_musd": 500.0, "summary": "deal", "source_url": "u",
                   "headline": "h"}]).to_parquet(root / "digest_db.parquet")
    pd.DataFrame([{"id": accession, "form_type": "DEFM14A", "company": f"{ticker} Inc",
                   "cik": "1", "accession": accession, "ticker": ticker, "items": None,
                   "date_filed": filed, "source_url": "edgarurl"}]
                 ).to_parquet(root / "events.parquet")
    _yahoo_store(tmp_path, ticker, sessions, [last_close] * len(sessions), column=price_column)
    ss._retain_source(accession, _submission(text, accepted=accepted),
                      source_url=f"https://sec.gov/{accession}.txt")
    if run_producer:
        ss.enrich_deal_terms()
    return accession


def _sit(ticker="ABC", *, accession=_ACC, **kw):
    row = {"ticker": ticker, "company": f"{ticker} Inc", "category": "Acquisitions",
           "accession": accession, "cik": "1", "stage": "pending", "date_filed": "2026-06-17"}
    row.update(kw)
    return row


def test_enrich_arb_publishes_receipts_not_bare_numbers(tmp_path, monkeypatch):
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"])
    sits = [_sit()]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    assert e["quality_state"] == arb.QUALITY_VERIFIED
    assert e["offer_price"] == 25.0 and e["currency"] == "USD"
    # a real exchange session, the ONE admitted artifact and its reviewed basis — not "the last
    # non-null row of whichever concatenated panel happened to carry this column"
    assert e["live_session"] == "2026-06-18" and e["sessions_behind"] == 0
    assert e["live_source"] == "yahoo/ABC.parquet"
    assert e["price_basis"] == arb.PRICE_BASIS_SPLIT_ADJ
    assert len(e["live_artifact_sha256"]) == 64
    # the reference session is strictly BEFORE SEC availability, not a 30-row lookback
    assert e["reference_session"] == "2026-06-16"
    assert e["accession"] == _ACC
    assert e["evidence"]["price_per_share"]["locator"]["end"] > 0
    # a VERIFIED row carries no failure reasons; informational gaps are warnings
    assert e["reasons"] == []


def test_enrich_arb_marks_a_stale_close_instead_of_pricing_off_it(tmp_path, monkeypatch):
    """The market has moved on two sessions; this listing's store has not."""
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-15", "2026-06-16"])
    sits = [_sit()]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    # 2, recomputed from the calendar: 06-17 and 06-18 both completed after this store's tip.
    # A count derived from the price store itself can only ever see rows the store contains,
    # which is exactly what let a frozen store report every listing as current.
    assert e["quality_state"] == arb.QUALITY_STALE_PRICE and e["sessions_behind"] == 2
    assert e["calendar_owner"] == "lib/nyse_calendar.py"
    assert e["orderable"] is False
    assert e["live_gross_spread_pct"] is not None      # visible …
    assert e["quality_state"] != arb.QUALITY_VERIFIED  # … never verified


def test_enrich_arb_never_invents_a_close_day(tmp_path, monkeypatch):
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_MONTH, sessions=["2026-06-16", "2026-06-18"])
    sits = [_sit()]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    assert e["expected_close"] == "2026-11" and e["expected_close_precision"] == "month"
    assert e["days_to_close"] is None and e["annualized_pct"] is None
    assert e["quality_state"] == arb.QUALITY_VERIFIED and e["orderable"] is False
    assert "DATE_PRECISION_INSUFFICIENT" in e["warnings"] and e["reasons"] == []


def test_enrich_arb_without_observations_is_degraded_not_absent(tmp_path, monkeypatch):
    """The LLM lane may still hold `llm_terms`; with no observation ledger there is no number."""
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-16", "2026-06-18"])
    (tmp_path / "special_situations" / "observations" / "observations.jsonl").write_text("")
    sits = [_sit(deal_terms={"price_per_share": 25.0, "consideration": "cash"})]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    assert e["quality_state"] == arb.QUALITY_SOURCE_UNAVAILABLE
    assert e["offer_price"] is None and e["live_gross_spread_pct"] is None


def test_mastermind_emit_and_context_feed_cannot_diverge(tmp_path, monkeypatch):
    """The mutant that shipped: one consumer excluded a row the other ranked first."""
    from engine import special_arb as arb
    from engine import special_sits_intel as si
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"])
    sits = [_sit(), _sit("MIX")]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    emit_rows, emit_counts = arb.select_ordered_context(sits, limit=25)
    feed_rows, feed_counts = arb.select_ordered_context(sits, limit=5)
    assert {r["ticker"] for r in feed_rows} <= {r["ticker"] for r in emit_rows}
    assert emit_counts["by_state"] == feed_counts["by_state"]
    # and the emitted payload carries the census, so an excluded row is countable
    e = sse.mastermind_emit()
    assert "risk_arb_census" in e
    for row in e["risk_arb"]:
        assert row["is_signal"] is False and row["quality_state"] == arb.QUALITY_VERIFIED
    assert si  # the feed consumer imports the same owner


def test_desk_page_renderer_consumes_the_economics_contract(tmp_path, monkeypatch):
    """The desk page reads the F09-1 contract, not the retired keys.

    This was found by tracing the wire rather than by any check: `_arb_str` subscripted
    `a['gross_spread_pct']` directly, so the page build raised KeyError on the new block — and
    nothing in CI covers `_arb_str`, so the PR would have gone fully green carrying a page-build
    crash. Authorized as a one-path boundary expansion; this guard replaces the temporary xfail.
    """
    from engine import special_arb as arb
    from scripts.build_special_situations import _arb_str

    # a degraded row renders as nothing — it must never format a null or raise
    degraded = arb.reduce_cash_deal(arb.compile_current_terms([]), category="Acquisitions",
                                    now_utc=NOW_UTC)
    assert degraded["quality_state"] == arb.QUALITY_SOURCE_UNAVAILABLE
    assert _arb_str(degraded) == ""

    # a verified row renders the LIVE spread, named unambiguously
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, last_close=20.0,
             sessions=["2026-06-16", "2026-06-18"])
    sits = [_sit()]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    econ = sits[0]["arb"]
    assert econ["quality_state"] == arb.QUALITY_VERIFIED
    rendered = _arb_str(econ)
    assert rendered.startswith("spread +25.0%")
    assert "%/yr" in rendered and "d" in rendered
    # the retired ambiguous key must not come back as an alias
    assert "gross_spread_pct" not in econ


def test_desk_payload_carries_the_ledger_join_key_end_to_end(tmp_path, monkeypatch):
    """Regression: hand-built `sits` masked a real defect.

    The join key is the EVENT ACCESSION. Neither situation constructor carried one — the branch
    plumbed a `cik` instead, which is an ISSUER and compiled one bucket for every situation — so
    this goes through `desk_payload()` rather than a hand-built row, and asserts the accession
    reaches both consumers.
    """
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"])
    d = sse.desk_payload()
    sits = {s["ticker"]: s for s in d["situations"]}
    assert "ABC" in sits
    assert sits["ABC"].get("accession") == _ACC, "situation row lost the ledger join key"
    e = sse.mastermind_emit()
    assert e["by_ticker"]["ABC"].get("accession") == _ACC, "emit row lost the ledger join key"


# ---- F09-1 CRITICAL: the accession is the transaction, the CIK is not ----------------------

def test_two_accessions_under_one_cik_cannot_share_terms_end_to_end(tmp_path, monkeypatch):
    """The real `_enrich_arb` join. `_load_observations()` grouped by `source.cik` and
    `_enrich_arb` read `obs_by_cik[cik]`, so one issuer's unrelated second deal supplied terms
    to the first. Two accessions, same filer, no link: neither may borrow the other's price."""
    from engine import special_arb as arb
    other = "0000000001-26-000777"
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-16", "2026-06-18"])
    # a second, unrelated deal by the same filer
    root = tmp_path / "special_situations"
    ss._retain_source(other, _submission(
        "Each share will be converted into the right to receive $250.00 in cash per share. "
        "The transaction is expected to close on December 20, 2026."),
        source_url="https://sec.gov/other.txt")
    pd.DataFrame([{"id": _ACC, "form_type": "DEFM14A", "company": "ABC Inc", "cik": "1",
                   "accession": _ACC, "ticker": "ABC", "items": None,
                   "date_filed": "2026-06-17", "source_url": "u"},
                  {"id": other, "form_type": "DEFM14A", "company": "ABC Inc", "cik": "1",
                   "accession": other, "ticker": "ABC", "items": None,
                   "date_filed": "2026-06-18", "source_url": "u"}]
                 ).to_parquet(root / "events.parquet")
    ss.enrich_deal_terms()
    first, second = _sit(accession=_ACC), _sit(accession=other)
    sse._enrich_arb([first, second], now_utc=NOW_UTC)
    assert first["arb"]["offer_price"] == 25.0
    assert second["arb"]["offer_price"] == 250.0
    for row in (first, second):
        assert row["arb"]["quality_state"] == arb.QUALITY_VERIFIED
        cited = {ev.get("accession") for ev in row["arb"]["evidence"].values()}
        assert cited == {row["accession"]}, "a situation cited another accession's evidence"


def test_a_forged_supersession_cannot_reach_the_projection(tmp_path, monkeypatch):
    """One unauthenticated field used to merge two unrelated deals into a VERIFIED price."""
    import json
    from engine import special_arb as arb
    other = "0000000001-26-000777"
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-16", "2026-06-18"])
    root = tmp_path / "special_situations"
    ss._retain_source(other, _submission(
        "Each share will be converted into the right to receive $250.00 in cash per share. "
        "The transaction is expected to close on December 20, 2026."), source_url="u")
    pd.DataFrame([{"id": _ACC, "form_type": "DEFM14A", "company": "ABC Inc", "cik": "1",
                   "accession": _ACC, "ticker": "ABC", "items": None,
                   "date_filed": "2026-06-17", "source_url": "u"},
                  {"id": other, "form_type": "DEFM14A", "company": "ABC Inc", "cik": "1",
                   "accession": other, "ticker": "ABC", "items": None,
                   "date_filed": "2026-06-18", "source_url": "u"}]
                 ).to_parquet(root / "events.parquet")
    ss.enrich_deal_terms()
    led = root / "observations" / "observations.jsonl"
    rows = [json.loads(x) for x in led.read_text().splitlines() if x.strip()]
    target = next(r for r in rows if r["field"] == "price_per_share"
                  and r["source"]["accession"] == _ACC)
    out = []
    for r in rows:
        if r["field"] == "price_per_share" and r["source"]["accession"] == other:
            r = dict(r, prior_observation_id=target["observation_id"],
                     supersedes_observation_id=target["observation_id"],
                     correction_reason="forged")           # id deliberately NOT recomputed
        out.append(r)
    led.write_text("\n".join(json.dumps(r, sort_keys=True) for r in out) + "\n")
    sits = [_sit(accession=_ACC)]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    assert e["quality_state"] != arb.QUALITY_VERIFIED
    assert e["offer_price"] != 250.0
    assert "INTEGRITY_FAILED" in e["reasons"]


# ---- F09-1 CRITICAL: the narrow U.S.-listing boundary in the PRODUCER ----------------------

@pytest.mark.parametrize("ticker", ["ARX.TO", "0700.HK", "BRK.B"])
def test_a_foreign_or_class_listing_is_never_priced_by_the_producer(tmp_path, monkeypatch,
                                                                    ticker):
    """XNYS cannot grade a foreign listing, and the suffix-root fallback priced one off a
    same-root U.S. column. On 2026-07-03 NYSE was closed while HKEX traded, so an HK row one
    local session stale reported `sessions_behind=0` and reached VERIFIED."""
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, ticker=ticker,
             sessions=["2026-06-16", "2026-06-18"])
    # a same-root U.S. store exists too — the old selector fell back to it
    _yahoo_store(tmp_path, ticker.split(".")[0], ["2026-06-18"], [15.19])
    sits = [_sit(ticker)]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    assert e["quality_state"] != arb.QUALITY_VERIFIED
    assert e["live_price"] is None and e["live_gross_spread_pct"] is None


def test_a_store_without_close_price_is_declined_not_substituted(tmp_path, monkeypatch):
    """`close` is total-return (split+dividend) adjusted; `close_price` is split-only. A writer
    that serves one for the other leaves every number on the wrong basis with no error."""
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-16", "2026-06-18"],
             price_column="close")
    sits = [_sit()]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    assert sits[0]["arb"]["quality_state"] != arb.QUALITY_VERIFIED
    assert sits[0]["arb"]["live_price"] is None


def test_the_broad_adjusted_panels_are_never_read_by_the_arb_lane(tmp_path, monkeypatch):
    """breadth / bt_prices / arb_prices / Canada-intl-HK search are all `auto_adjust=True`.

    A number existing in one of them may not make a row VERIFIED, and the lane must not read
    them at all: the producer's own source no longer mentions the close panels.
    """
    import inspect
    from engine import special_arb as arb
    src = inspect.getsource(sse._enrich_arb) + inspect.getsource(sse._price_inputs)
    for forbidden in ("_closes_panel", "_closes_frames", "_panel_sources", "close_raw"):
        assert forbidden not in src, f"the arb lane still reaches for {forbidden}"
    # and with ONLY a breadth panel present there is no price at all
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-16", "2026-06-18"])
    (tmp_path / "yahoo" / "ABC.parquet").unlink()
    (tmp_path / "breadth").mkdir(exist_ok=True)
    pd.DataFrame({"ABC": [15.19]}, index=pd.to_datetime(["2026-06-18"])).to_parquet(
        tmp_path / "breadth" / "_closes_cache.parquet")
    sits = [_sit()]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    econ = sits[0]["arb"]
    assert econ["quality_state"] != arb.QUALITY_VERIFIED
    # The subject is that the breadth number never becomes a price — assert THAT, not the
    # particular reason. Since the clock/listing rebind, deleting the per-ticker Yahoo store
    # also removes the canonical listing proof, so the lane now fails closed one step earlier
    # (INTEGRITY_FAILED: the retained rows claim a USD listing no owner can still vouch for)
    # rather than reaching PRICE_MISSING. Pinning the old reason would pin the shallower gate.
    assert econ["live_price"] is None
    assert econ["live_gross_spread_pct"] is None and econ["annualized_pct"] is None
    assert 15.19 not in [econ.get("live_price"), econ.get("reference_price")]
    assert econ["orderable"] is False


def test_the_price_receipt_digest_is_the_artifact_bytes(tmp_path, monkeypatch):
    """A path is a location; a digest over the exact bytes is an identity."""
    import hashlib
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-16", "2026-06-18"])
    sits = [_sit()]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    path = tmp_path / "yahoo" / "ABC.parquet"
    assert sits[0]["arb"]["live_artifact_sha256"] == \
        hashlib.sha256(path.read_bytes()).hexdigest()


# ---- F09-1: the collector lane that writes the ledger --------------------------------------

def test_deal_term_lane_writes_a_byte_bound_ledger_and_is_idempotent(tmp_path, monkeypatch):
    import json
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-18"],
             run_producer=False)
    n = ss.enrich_deal_terms()
    assert n > 0
    root = tmp_path / "special_situations"
    path = root / "observations" / "observations.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    assert rows and all(r["schema"] == arb.OBSERVATION_SCHEMA for r in rows)
    price = next(r for r in rows if r["field"] == "price_per_share")
    assert price["normalized"] == 25.0
    # bound to the RETAINED bytes: the excerpt is re-read out of the projection derived from the
    # verified object, not out of a legacy stripped cache the observation never cited
    projection, receipt = ss.verified_projection(_ACC)
    assert projection[price["locator"]["start"]:price["locator"]["end"]] == \
        price["locator"]["excerpt"]
    assert price["source"]["raw_sha256"] == receipt["raw_sha256"]
    assert price["source"]["raw_bytes"] == receipt["raw_bytes"]
    assert price["source"]["completeness"] == arb.COMPLETENESS_COMPLETE
    assert len(price["source"]["body_sha256"]) == 64

    # a rebuild over unchanged bytes appends NOTHING — observation_id is a digest of the inputs
    assert ss.enrich_deal_terms() == 0
    assert len(path.read_text().splitlines()) == len(rows)


def test_deal_term_lane_reads_only_already_retained_bodies(tmp_path, monkeypatch):
    """The rights boundary: with no verified receipt and no refresh, the lane opens nothing."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    root = tmp_path / "special_situations"
    root.mkdir(parents=True)
    pd.DataFrame([{"id": _ACC, "form_type": "DEFM14A", "company": "ABC Inc", "cik": "1",
                   "accession": _ACC, "ticker": "ABC", "items": None,
                   "date_filed": "2026-06-17", "source_url": "u"}]
                 ).to_parquet(root / "events.parquet")

    def _boom(*a, **k):                      # any network fetch is a contract violation here
        raise AssertionError("the deal-term lane must not fetch without refresh")
    monkeypatch.setattr(ss, "_get", _boom)
    assert ss.enrich_deal_terms() == 0       # no retained object -> nothing, and no fetch
    assert not (root / "observations").exists()


def test_deal_term_lane_ignores_events_outside_the_fixed_cash_categories(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    root = tmp_path / "special_situations"
    root.mkdir(parents=True)
    ss._retain_source("0000000002-26-000002", _submission(
        "The Board declared a special cash dividend of $2.50 per share."), source_url="u")
    pd.DataFrame([{"id": "0000000002-26-000002", "form_type": "SC 13D", "company": "XYZ Inc",
                   "cik": "2", "accession": "0000000002-26-000002", "ticker": "XYZ",
                   "items": None, "date_filed": "2026-06-17", "source_url": "u"}]
                 ).to_parquet(root / "events.parquet")
    assert ss.enrich_deal_terms() == 0


# ---- F09-1 CRITICAL: exact acquired bytes, atomically retained and read back ---------------

def test_retention_keeps_the_exact_acquired_bytes_content_addressed(tmp_path, monkeypatch):
    """`Response.text` re-encoded with `errors="replace"` is a lossy round trip, so a digest
    over it describes our decoding, not SEC's document. The object is also content-addressed:
    it used to be named by accession and written only if absent while its receipt was rewritten
    every call, so object and receipt could disagree silently and forever."""
    import gzip
    import hashlib
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    raw = b"<ACCEPTANCE-DATETIME>20260617173100\n<DOCUMENT>caf\xc3\xa9 \xe2\x82\xac25.00</DOCUMENT>"
    receipt = ss._retain_source(_ACC, raw, source_url="u")
    obj = ss.source_object_path(receipt["raw_sha256"])
    assert obj.name == f"sha256-{hashlib.sha256(raw).hexdigest()}.raw.gz"
    with gzip.open(obj, "rb") as fh:
        assert fh.read() == raw, "the retained object is not the exact acquired bytes"
    assert receipt["raw_bytes"] == len(raw) and receipt["readback_verified"] is True
    assert receipt["truncated"] is False
    assert ss.retained_source_bytes(receipt) == raw


def test_retention_is_atomic_and_leaves_no_partial_object(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    ss._retain_source(_ACC, _submission(_CASH_EXACT), source_url="u")
    root = tmp_path / "special_situations" / "source_objects"
    assert not list(root.glob("*.tmp")), "a temp file survived publication"
    assert not list(root.glob(".*tmp*")), "a temp file survived publication"


@pytest.mark.parametrize("mutate", ["changed_object", "receipt_length", "projection_digest"])
def test_a_retained_object_that_disagrees_with_its_receipt_is_refused(tmp_path, monkeypatch,
                                                                      mutate):
    import gzip
    import json
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    receipt = ss._retain_source(_ACC, _submission(_CASH_EXACT), source_url="u")
    assert ss.verified_projection(_ACC) is not None          # control
    obj = ss.source_object_path(receipt["raw_sha256"])
    rpath = tmp_path / "special_situations" / "source_objects" / f"{_ACC}.receipt.json"
    if mutate == "changed_object":
        obj.write_bytes(gzip.compress(b"different bytes entirely"))
    elif mutate == "receipt_length":
        rpath.write_text(json.dumps(dict(receipt, raw_bytes=receipt["raw_bytes"] + 7)))
    else:
        rpath.write_text(json.dumps(dict(receipt, projection_sha256="f" * 64)))
    assert ss.verified_projection(_ACC) is None, f"{mutate} was accepted"


@pytest.mark.parametrize("mutate", ["locator_out_of_range", "excerpt_mismatch",
                                    "forged_value_resealed"])
def test_a_row_that_does_not_descend_from_the_retained_bytes_is_unbound(tmp_path, monkeypatch,
                                                                        mutate):
    """`validate_observation()` re-derives a row's id from the row's OWN fields, so a forger who
    edits a value, moves a span and RECOMPUTES the id passes it. Only re-opening the retained
    object and re-reading the span can refuse these."""
    import json
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-16", "2026-06-18"])
    led = tmp_path / "special_situations" / "observations" / "observations.jsonl"
    rows = [json.loads(x) for x in led.read_text().splitlines() if x.strip()]
    out = []
    for r in rows:
        if r["field"] == "price_per_share":
            if mutate == "locator_out_of_range":
                r = dict(r, locator=dict(r["locator"], start=10 ** 6, end=10 ** 6 + 5))
                r = arb.reseal(r)
            elif mutate == "excerpt_mismatch":
                r = dict(r, locator=dict(r["locator"], excerpt="$999.00 in cash per share"))
            else:
                r = arb.reseal(dict(r, normalized=999.0))
            assert arb.validate_observation(r), "the mutant must be internally self-consistent"
        out.append(r)
    led.write_text("\n".join(json.dumps(r, sort_keys=True) for r in out) + "\n")
    sits = [_sit()]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    assert e["quality_state"] != arb.QUALITY_VERIFIED
    assert e["offer_price"] not in (999.0,)
    assert e["ledger_census"]["unbound"] >= 1


# ---- F09-1 CRITICAL: the SEC acceptance clock is DST-correct -------------------------------

@pytest.mark.parametrize("stamp,expected", [
    ("20260115120000", "2026-01-15T17:00:00+00:00"),   # winter: EST, -05:00
    ("20260715120000", "2026-07-15T16:00:00+00:00"),   # summer: EDT, -04:00
    ("20260308013000", "2026-03-08T06:30:00+00:00"),   # the DST spring-forward morning
    ("20261101013000", "2026-11-01T05:30:00+00:00"),   # the fall-back morning (first pass)
])
def test_sec_acceptance_is_converted_with_the_correct_offset(stamp, expected):
    """`-04:00` was hard-coded for EVERY acceptance timestamp. SEC Eastern is not permanently
    EDT: every winter filing was stamped an hour early, which can select the wrong reference
    session around the close."""
    assert ss.parse_acceptance_datetime(_submission("x", accepted=stamp)) == expected


_STAMPS = ("20260115120000", "20260715120000", "20260308013000", "20261101013000")


def test_the_acceptance_parser_is_byte_equivalent_to_the_proven_owner():
    """Reuse, not re-invention: the same bytes must yield the same instant as the already-proven
    `sec_capital_structure.parse_submission()` raw-submission semantics.

    Run against the real owner where it imports. On this host it does not: importing
    `collectors.sec_capital_structure` pulls `engine/capital_structure/document_terms.py`, whose
    sealed-closure self-check raises "document-term parser code contains unsupported constant
    slice" under Python 3.14 — a PRE-EXISTING failure on blobs identical to `origin/main`
    (both verified unchanged by this branch), unrelated to F09 and not ours to repair here.

    Equivalence is therefore asserted twice, so neither path is a bare skip: the owner's exact
    conversion expression is re-executed here over the same bytes, AND that expression is pinned
    against the owner's source, so a change to its clock semantics fails this test.
    """
    from zoneinfo import ZoneInfo
    owner = Path(__file__).resolve().parents[1] / "collectors/sec_capital_structure.py"
    src = owner.read_text()
    for fragment in (r'br"<ACCEPTANCE-DATETIME>\s*(\d{14})"',
                     'datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(',
                     'tzinfo=ZoneInfo("America/New_York")',
                     ".astimezone(timezone.utc).isoformat()"):
        assert fragment in src, f"the proven owner no longer contains {fragment!r}"

    for stamp in _STAMPS:
        # the owner's expression, re-executed verbatim over the same bytes
        reference = (datetime.strptime(stamp, "%Y%m%d%H%M%S")
                     .replace(tzinfo=ZoneInfo("America/New_York"))
                     .astimezone(timezone.utc).isoformat())
        assert ss.parse_acceptance_datetime(_submission("x", accepted=stamp)) == reference

    try:
        from collectors.sec_capital_structure import parse_submission
    except Exception as exc:  # noqa: BLE001 — pre-existing, unrelated import-time failure
        assert "document-term" in str(exc) or "closure" in str(exc), \
            f"unexpected import failure — investigate rather than tolerate: {exc!r}"
        return
    for stamp in _STAMPS:
        raw = _submission("x", accepted=stamp)
        assert ss.parse_acceptance_datetime(raw) == parse_submission(raw).accepted_at


@pytest.mark.parametrize("raw", [b"no header at all",
                                 b"<ACCEPTANCE-DATETIME>20261301120000",   # month 13
                                 b"<ACCEPTANCE-DATETIME>notanumber"])
def test_an_invalid_acceptance_timestamp_yields_no_clock(raw):
    assert ss.parse_acceptance_datetime(raw) is None


def test_after_close_and_premarket_acceptance_pick_different_reference_sessions(
        tmp_path, monkeypatch):
    """Date-only `date_filed` cannot tell these apart, which is why it may not fix a reference
    session at all. With an exact acceptance moment the reference is deterministic — and the
    acceptance comes from the SOURCE BYTES, so each case retains its own submission."""
    sessions = ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18"]

    def _ref_for(stamp):
        env = tmp_path / stamp
        env.mkdir(exist_ok=True)
        _f09_env(env, monkeypatch, text=_CASH_EXACT, sessions=sessions, accepted=stamp)
        sits = [_sit()]
        sse._enrich_arb(sits, now_utc=NOW_UTC)
        return sits[0]["arb"]

    premarket = _ref_for("20260617074500")    # 07:45 ET, before the 06-17 close
    after_close = _ref_for("20260617173100")  # 17:31 ET, after it
    assert premarket["reference_session"] == "2026-06-16"
    assert after_close["reference_session"] == "2026-06-17"
    assert premarket["reference_session"] != after_close["reference_session"]


# ---- F09-1 CRITICAL: ledger integrity fails closed BEFORE the write -----------------------

def test_a_malformed_last_ledger_line_is_partial_generation_not_a_healthy_subset(
        tmp_path, monkeypatch):
    """A truncated final write is a REAL failure. The old loader skipped it silently and
    published the surviving rows as a complete, healthy projection."""
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-16", "2026-06-18"])
    led = tmp_path / "special_situations" / "observations" / "observations.jsonl"
    led.write_text(led.read_text() + '{"schema":"special_situations.deal_term_obs')  # cut mid-write
    sits = [_sit()]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    assert e["quality_state"] != arb.QUALITY_VERIFIED
    assert "PARTIAL_GENERATION" in e["reasons"] and "INTEGRITY_FAILED" in e["reasons"]
    assert e["ledger_census"]["malformed"] == 1


def test_the_producer_refuses_to_append_to_a_ledger_that_does_not_validate(tmp_path,
                                                                           monkeypatch, capsys):
    """The producer scanned the ledger with a bare `except ValueError: continue` while building
    `known` and then appended with `open(..., "a")` — so an already-corrupt ledger quietly
    received more rows, and a crash mid-append created exactly the malformed tail the reader
    later reported. A ledger that does not fully validate may not be extended."""
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-18"])
    led = tmp_path / "special_situations" / "observations" / "observations.jsonl"
    before = led.read_text() + '{"schema":"truncated'
    led.write_text(before)
    # a fresh accession that WOULD otherwise produce new rows
    other = "0000000001-26-000777"
    ss._retain_source(other, _submission(
        "Each share will be converted into the right to receive $30.00 in cash per share. "
        "The transaction is expected to close on December 20, 2026."), source_url="u")
    root = tmp_path / "special_situations"
    pd.DataFrame([{"id": other, "form_type": "DEFM14A", "company": "ABC Inc", "cik": "1",
                   "accession": other, "ticker": "ABC", "items": None,
                   "date_filed": "2026-06-18", "source_url": "u"}]
                 ).to_parquet(root / "events.parquet")
    assert ss.enrich_deal_terms() == 0
    assert led.read_text() == before, "the producer appended to a corrupt ledger"
    out = capsys.readouterr().out
    assert any(line.startswith("::warning") and "ledger integrity" in line
               for line in out.splitlines()), out


def test_the_ledger_is_published_atomically_and_read_back(tmp_path, monkeypatch):
    """One atomic replacement of old+new, then a readback through the SAME validator."""
    import inspect
    import json
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-18"],
             run_producer=False)
    src = inspect.getsource(ss.enrich_deal_terms)
    assert 'open(' not in src or '"a"' not in src, "the producer still appends in place"
    assert "_atomic_write" in src and "read_ledger_strict" in src
    assert ss.enrich_deal_terms() > 0
    led = tmp_path / "special_situations" / "observations" / "observations.jsonl"
    rows = [json.loads(x) for x in led.read_text().splitlines() if x.strip()]
    _, census = ss.read_ledger_strict()
    assert census["ok"] and census["kept"] == len(rows)
    assert not list((tmp_path / "special_situations" / "observations").glob("*.tmp"))


# ---- F09-1 HIGH: existing cached filings can acquire a receipt on a real refresh -----------

def test_a_legacy_cache_without_a_receipt_is_reacquired_on_refresh(tmp_path, monkeypatch):
    """`_fetch_filing_text()` returned the legacy `.txt` BEFORE `_retain_source()` ran, so any
    accession with a `doc_cache` entry could never obtain a receipt, `enrich_deal_terms()`
    skipped it, and the natural build passes `fetch_missing=False`. Coverage over the whole
    pre-existing corpus was therefore structurally ZERO, permanently, with no backfill path."""
    from engine import special_arb as arb
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    root = tmp_path / "special_situations"
    (root / "doc_cache").mkdir(parents=True)
    (root / "doc_cache" / f"{_ACC}.txt").write_text("legacy stripped 40k candidate text")
    pd.DataFrame([{"id": _ACC, "form_type": "DEFM14A", "company": "ABC Inc", "cik": "1",
                   "accession": _ACC, "ticker": "ABC", "items": None,
                   "date_filed": "2026-06-17", "source_url": "u"}]
                 ).to_parquet(root / "events.parquet")
    _yahoo_store(tmp_path, "ABC", ["2026-06-18"], [15.19])

    # no-refresh: source-inert, zero fetch, and the legacy text is NEVER promoted
    calls = []
    monkeypatch.setattr(ss, "_get", lambda *a, **k: calls.append(a) or None)
    assert ss.enrich_deal_terms() == 0
    assert calls == [], "the no-refresh path fetched"
    assert ss._source_receipt(_ACC) is None

    # a real refresh reacquires the exact complete bytes through the existing fetch owner
    served = _submission(_CASH_EXACT)
    monkeypatch.setattr(ss, "_get", lambda *a, **k: served if k.get("as_bytes") else "x")
    assert ss.enrich_deal_terms(fetch_missing=True) > 0
    receipt = ss._source_receipt(_ACC)
    assert receipt and receipt["raw_bytes"] == len(served)
    projection, _ = ss.verified_projection(_ACC)
    assert "legacy stripped" not in projection, "the 40k candidate text was promoted"
    sits = [_sit()]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    assert sits[0]["arb"]["quality_state"] == arb.QUALITY_VERIFIED


# ---- F09-1: the natural build path ---------------------------------------------------------

def test_the_real_build_path_calls_the_producer_and_no_refresh_stays_source_inert():
    """`enrich_deal_terms()` was never called by build(refresh=True), so a natural run would
    leave the ledger empty and every cash deal would report SOURCE_UNAVAILABLE."""
    import inspect
    from scripts import build_special_situations as bss
    src = inspect.getsource(bss.build)
    assert "enrich_deal_terms" in src, "the producer is not wired into the refresh sequence"
    refresh_block = src.split("if refresh:", 1)[1]
    assert "enrich_deal_terms" in refresh_block, "producer must run only under refresh"
    # it must run BEFORE the desk is compiled, or the first build reads an empty ledger
    assert refresh_block.index("enrich_deal_terms") < refresh_block.index("desk_payload")
    # it may be allowed to REACQUIRE a legacy cache, but never unconditionally on the render
    # path (macro#6793 review): a live SEC full-submission GET + unbounded, unpruned disk
    # retention belongs behind a config gate that defaults OFF, not a hardcoded fetch_missing=True.
    assert "fetch_missing=True" not in refresh_block, \
        "reacquire-on-every-render-build must not be hardcoded True — gate it via config"
    assert "deal_terms_fetch_missing" in refresh_block, \
        "the reacquire path must be config-gated so it can stay off until #6783 lands"
    from lib import config as _config
    default_ss = _config.load().get("special_situations", {}) or {}
    assert not default_ss.get("deal_terms_fetch_missing", False), \
        "deal_terms_fetch_missing must default to False in the shipped config"


# ===========================================================================
# Sol CRITICAL SOURCE-AUTHORITY ADDENDUM (carrier 1788495129.504909) —
# the ledger clock and listing must be RE-BOUND to owners outside the row.
# Sealing a field into observation_id stops a silent edit; it does not stop a
# forger who edits and reseals. Every mutant below reseals.
# ===========================================================================

def _ledger_rows(tmp_path):
    import json
    p = ss._observations_path()
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()], p


def _reseal(o):
    """Recompute the row's own id from its own (mutated) fields — a forger's move."""
    from engine import special_arb as arb
    o["observation_id"] = arb.observation_id(
        source=o.get("source") or {}, field=o.get("field"),
        locator=o.get("locator") or {}, normalized=o.get("normalized"),
        extraction_revision=o.get("extraction_revision") or arb.EXTRACTION_REVISION,
        prior_observation_id=o.get("prior_observation_id"),
        supersedes_observation_id=o.get("supersedes_observation_id"),
        correction_reason=o.get("correction_reason"))
    return o


def _rewrite(p, rows):
    import json
    p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


def _both_readers_reject(tmp_path):
    """The collector readback AND the engine runtime must BOTH refuse. Neither may be lenient."""
    from engine import special_arb as arb  # noqa: F401
    _, col_census = ss.read_ledger_strict()
    _, eng_census = sse._load_observations()
    return col_census, eng_census


def test_a_resealed_acceptance_clock_is_rejected_by_both_readers(tmp_path, monkeypatch):
    """Premarket -> after-close moves the filing-reference SESSION, so a row that can rewrite
    its own acceptance clock can move a published premium."""
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"], accepted="20260617073000")
    rows, p = _ledger_rows(tmp_path)
    assert rows, "producer wrote no observations"
    for r in rows:
        r["source"]["acceptance_datetime"] = "2026-06-17T21:31:00+00:00"   # after-close
        _reseal(r)
    _rewrite(p, rows)
    col_census, eng_census = _both_readers_reject(tmp_path)
    assert col_census["kept"] == 0 and col_census["unbound"] >= 1 and col_census["ok"] is False
    assert eng_census["kept"] == 0 and eng_census["integrity_failed"] is True


def test_a_resealed_filing_date_cannot_reorder_current_terms(tmp_path, monkeypatch):
    """`compile_current_terms()` orders candidates by source.filing_date."""
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"])
    rows, p = _ledger_rows(tmp_path)
    for r in rows:
        r["source"]["filing_date"] = "2099-01-01"        # sort it to the front of any lineage
        _reseal(r)
    _rewrite(p, rows)
    col_census, eng_census = _both_readers_reject(tmp_path)
    assert col_census["kept"] == 0
    assert eng_census["kept"] == 0 and eng_census["integrity_failed"] is True
    sits = [_sit()]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    assert "INTEGRITY_FAILED" in sits[0]["arb"]["reasons"]
    assert sits[0]["arb"]["offer_price"] is None


def test_a_row_cannot_self_authorize_its_listing_currency(tmp_path, monkeypatch):
    """Strip the listing receipt, assert USD anyway, reseal: a bare `$` must not self-authorize."""
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"])
    rows, p = _ledger_rows(tmp_path)
    for r in rows:
        r["source"]["resolved_listing"] = None
        r["currency"] = "USD"
        _reseal(r)
    _rewrite(p, rows)
    col_census, eng_census = _both_readers_reject(tmp_path)
    assert col_census["kept"] == 0
    assert eng_census["kept"] == 0 and eng_census["integrity_failed"] is True


def test_a_row_cannot_promote_a_foreign_target_to_a_us_listing(tmp_path, monkeypatch):
    """The canonical event owner is unchanged; only the row claims the U.S. listing."""
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"])
    rows, p = _ledger_rows(tmp_path)
    for r in rows:
        r["source"]["resolved_listing"] = "XYZ"          # a listing this event never had
        _reseal(r)
    _rewrite(p, rows)
    col_census, eng_census = _both_readers_reject(tmp_path)
    assert col_census["kept"] == 0
    assert eng_census["kept"] == 0 and eng_census["integrity_failed"] is True


def test_the_untampered_ledger_rebinds_idempotently_and_still_reaches_the_reducer(
        tmp_path, monkeypatch):
    """Positive control — the law must not be satisfied by refusing everything."""
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"])
    col_rows, col_census = ss.read_ledger_strict()
    eng_rows, eng_census = sse._load_observations()
    assert col_census["kept"] >= 1 and col_census["ok"] is True
    assert eng_census["kept"] >= 1 and eng_census["integrity_failed"] is False
    # idempotent: a second read of untouched bytes binds identically
    again_rows, again_census = ss.read_ledger_strict()
    assert again_census["kept"] == col_census["kept"]
    sits = [_sit()]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    econ = sits[0]["arb"]
    assert "INTEGRITY_FAILED" not in econ["reasons"]
    assert econ["offer_price"] == 25.0


def test_a_malformed_ledger_line_is_counted_as_malformed_not_merely_unhealthy(
        tmp_path, monkeypatch):
    """Found by mutation: deleting `census["malformed"] += 1` changed nothing.

    Once the clock/listing rebind existed, a corrupt ledger reached `ok is False` through the
    *unbound* path as well, so every assertion phrased as "the census is unhealthy" was
    satisfied either way and the malformed counter itself was pinned by nothing. A truncated
    final write is a distinct, nameable failure and the census has to say so.
    """
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"])
    p = ss._observations_path()
    p.write_text(p.read_text() + '{"schema": "truncated last write, no closing brace"\n')
    _, census = ss.read_ledger_strict()
    assert census["malformed"] >= 1, "a truncated JSONL line was not counted as malformed"
    assert census["ok"] is False


def test_a_meaning_bearing_field_edited_without_resealing_fails_on_identity_alone(
        tmp_path, monkeypatch):
    """The three meaning-bearing source fields are INSIDE the closed digest.

    The independent rebind catches a resealed forgery, which is why this needs its own test:
    with the rebind in place, dropping these fields from `observation_id()` changed no test at
    all. Identity is the cheap first gate and must hold on its own — an edit with no reseal is
    `invalid` (the id no longer matches its row), not merely `unbound`.
    """
    import json
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"])
    p = ss._observations_path()
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    for r in rows:
        r["source"]["filing_date"] = "2099-01-01"        # NO reseal: id must stop this
    p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    _, census = ss.read_ledger_strict()
    assert census["invalid"] >= 1, "an unresealed edit survived the closed observation identity"
    assert census["kept"] == 0


def test_authored_terms_receives_the_canonical_listing_currency_not_the_rows(
        tmp_path, monkeypatch):
    """The untrusted row must not nominate the authority that then blesses its own bare `$`.

    Also found by mutation: reverting to `o.get("currency")` broke nothing, because a row whose
    currency contradicts the canonical listing is now rejected by the rebind first. The case
    that still discriminates is a row that simply OMITS currency — the old code would then
    re-extract with `listing_currency=None` and authorize a different term set.
    """
    import json
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"])
    p = ss._observations_path()
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    for r in rows:
        r.pop("currency", None)
    p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))

    seen = []
    real = arb.authored_terms
    monkeypatch.setattr(arb, "authored_terms",
                        lambda proj, **kw: (seen.append(kw.get("listing_currency")),
                                            real(proj, **kw))[1])
    sse._load_observations()
    assert seen, "the runtime never re-derived the authored term set"
    assert set(seen) == {"USD"}, (
        f"authored_terms was keyed on {seen} — the canonical event listing proves USD, and the "
        "row (which omits currency) must not be the authority")
