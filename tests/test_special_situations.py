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

def _f09_env(tmp_path, monkeypatch, *, text, sessions, ticker="ABC", last_close=15.19,
             filed="2026-06-17", category="Acquisitions"):
    """A tmp data dir carrying one arb-category event, its observation ledger and a closes panel."""
    import json
    from engine import special_arb as arb
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({1: ticker}, {}))
    root = tmp_path / "special_situations"
    root.mkdir(exist_ok=True)
    pd.DataFrame([{"id": 9, "ticker": ticker, "company": f"{ticker} Inc", "country": "US",
                   "category": category, "issue": 19, "issue_date": "2026-06-14",
                   "market_cap_musd": 500.0, "summary": "deal", "source_url": "u",
                   "headline": "h"}]).to_parquet(root / "digest_db.parquet")
    pd.DataFrame([{"id": "e1", "form_type": "DEFM14A", "company": f"{ticker} Inc", "cik": "1",
                   "items": None, "date_filed": filed, "source_url": "edgarurl"}]
                 ).to_parquet(root / "events.parquet")
    src = arb.source_descriptor(cik="1", form_type="8-K", accession="0000000001-26-000001",
                                filing_date=filed, source_url="https://sec.gov/x", body=text,
                                acquired_at="2026-06-17T00:00:00Z",
                                raw_sha256="c" * 64, raw_bytes=len(text) * 3,
                                acceptance_datetime=f"{filed}T17:31:00-04:00")
    obs = arb.extract_term_observations(text, source=src, listing_currency="USD",
                                        recorded_at="2026-06-17T00:00:00Z")
    (root / "observations").mkdir(exist_ok=True)
    (root / "observations" / "observations.jsonl").write_text(
        "\n".join(json.dumps(o, sort_keys=True) for o in obs) + "\n")
    closes = pd.DataFrame({ticker: [last_close] * len(sessions), "ZZZZ": [1.0] * len(sessions)},
                          index=pd.to_datetime(sessions))
    (tmp_path / "breadth").mkdir(exist_ok=True)
    closes.to_parquet(tmp_path / "breadth" / "_closes_cache.parquet")
    return obs


NOW_UTC = datetime(2026, 6, 18, 22, 0, tzinfo=timezone.utc)   # explicit market clock

_CASH_EXACT = ("Each share of common stock will be converted into the right to receive $25.00 "
               "in cash per share. The transaction is expected to close on December 15, 2026.")
_CASH_MONTH = ("Each share of common stock will be converted into the right to receive $25.00 "
               "in cash per share. The transaction is expected to close in November 2026.")


def test_enrich_arb_publishes_receipts_not_bare_numbers(tmp_path, monkeypatch):
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"])
    sits = [{"ticker": "ABC", "company": "ABC Inc", "category": "Acquisitions", "cik": "1",
             "stage": "pending", "date_filed": "2026-06-17"}]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    assert e["quality_state"] == arb.QUALITY_VERIFIED
    assert e["offer_price"] == 25.0 and e["currency"] == "USD"
    # a real exchange session, a real artifact and a real basis — not "the last non-null row"
    assert e["live_session"] == "2026-06-18" and e["sessions_behind"] == 0
    assert e["live_source"].endswith("_closes_cache.parquet") and e["price_basis"] == "close_raw"
    # the reference session is strictly BEFORE SEC availability, not a 30-row lookback
    assert e["reference_session"] == "2026-06-16"
    assert e["accession"] == "0000000001-26-000001"
    assert e["evidence"]["price_per_share"]["locator"]["end"] > 0


def test_enrich_arb_marks_a_stale_close_instead_of_pricing_off_it(tmp_path, monkeypatch):
    """The panel's newest session exists, but this listing did not trade on it."""
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-15", "2026-06-16"])
    sits = [{"ticker": "ABC", "company": "ABC Inc", "category": "Acquisitions", "cik": "1",
             "stage": "pending", "date_filed": "2026-06-17"}]
    # ZZZZ trades on a later session; ABC does not, so ABC is one session behind
    panel = pd.read_parquet(tmp_path / "breadth" / "_closes_cache.parquet")
    panel.loc[pd.Timestamp("2026-06-18")] = [float("nan"), 1.0]
    panel.sort_index().to_parquet(tmp_path / "breadth" / "_closes_cache.parquet")
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    # 2, not 1: nyse_calendar counts real completed sessions (06-17 and 06-18) after the last
    # close this listing actually has. The old panel-derived count could only ever see rows the
    # panel happened to contain, which is what let a frozen store look current.
    assert e["quality_state"] == arb.QUALITY_STALE_PRICE and e["sessions_behind"] == 2
    assert e["calendar_owner"] == "lib/nyse_calendar.py"
    assert e["orderable"] is False


def test_enrich_arb_never_invents_a_close_day(tmp_path, monkeypatch):
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_MONTH, sessions=["2026-06-16", "2026-06-18"])
    sits = [{"ticker": "ABC", "company": "ABC Inc", "category": "Acquisitions", "cik": "1",
             "stage": "pending", "date_filed": "2026-06-17"}]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    assert e["expected_close"] == "2026-11" and e["expected_close_precision"] == "month"
    assert e["days_to_close"] is None and e["annualized_pct"] is None
    assert e["quality_state"] == arb.QUALITY_VERIFIED and e["orderable"] is False


def test_enrich_arb_without_observations_is_degraded_not_absent(tmp_path, monkeypatch):
    """The LLM lane may still hold `llm_terms`; with no observation ledger there is no number."""
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-16", "2026-06-18"])
    (tmp_path / "special_situations" / "observations" / "observations.jsonl").write_text("")
    sits = [{"ticker": "ABC", "company": "ABC Inc", "category": "Acquisitions", "cik": "1",
             "stage": "pending", "date_filed": "2026-06-17",
             "deal_terms": {"price_per_share": 25.0, "consideration": "cash"}}]
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
    sits = [{"ticker": "ABC", "company": "ABC Inc", "category": "Acquisitions", "cik": "1",
             "stage": "pending", "date_filed": "2026-06-17"},
            {"ticker": "MIX", "company": "MIX Inc", "category": "Acquisitions", "cik": "1",
             "stage": "pending", "date_filed": "2026-06-17"}]
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


def test_desk_page_renderer_consumes_the_economics_contract():
    """The desk page reads the F09-1 contract, not the retired keys.

    This was found by tracing the wire rather than by any check: `_arb_str` subscripted
    `a['gross_spread_pct']` directly, so the page build raised KeyError on the new block — and
    nothing in CI covers `_arb_str`, so the PR would have gone fully green carrying a page-build
    crash. Authorized as a one-path boundary expansion; this guard replaces the temporary xfail.
    """
    from datetime import date as _d
    from engine import special_arb as arb
    from scripts.build_special_situations import _arb_str

    # a degraded row renders as nothing — it must never format a null or raise
    degraded = arb.reduce_cash_deal(arb.compile_current_terms([]), category="Acquisitions",
                                    now_utc=NOW_UTC)
    assert degraded["quality_state"] == arb.QUALITY_SOURCE_UNAVAILABLE
    assert _arb_str(degraded) == ""

    # a verified row renders the LIVE spread, named unambiguously
    obs = arb.extract_term_observations(
        _CASH_EXACT,
        source=arb.source_descriptor(cik="1", form_type="8-K",
                                     accession="0000000001-26-000001",
                                     filing_date="2026-06-17", source_url="u",
                                     body=_CASH_EXACT, acquired_at="z",
                                     raw_sha256="e" * 64, raw_bytes=999,
                                     acceptance_datetime="2026-06-17T17:31:00-04:00"),
        listing_currency="USD")
    live = arb.price_input(ticker="ABC", session="2026-06-18", value=20.0, currency="USD",
                           basis="close_raw", source_artifact="breadth/_closes_cache.parquet",
                           artifact_sha256="d" * 64, sessions_behind=0,
                           expected_session="2026-06-18", calendar_owner="lib/nyse_calendar.py",
                           calendar_revision="nyse_calendar.v1")
    econ = arb.reduce_cash_deal(arb.compile_current_terms(obs), category="Acquisitions",
                                stage="pending", live_price=live, now_utc=NOW_UTC)
    assert econ["quality_state"] == arb.QUALITY_VERIFIED
    rendered = _arb_str(econ)
    assert rendered.startswith("spread +25.0%")
    assert "%/yr" in rendered and "d" in rendered
    # the retired ambiguous key must not come back as an alias
    assert "gross_spread_pct" not in econ


def test_desk_payload_carries_the_ledger_join_key_end_to_end(tmp_path, monkeypatch):
    """Regression: hand-built `sits` masked a real defect.

    The observation ledger is keyed by subject CIK, but neither situation constructor put a
    `cik` on the row and a digest-confirmed row keeps the digest dict, which has none. Every
    production cash deal would have reported SOURCE_UNAVAILABLE while every unit test passed,
    because the tests supplied the cik the real path never set. Go through desk_payload().
    """
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-15", "2026-06-16", "2026-06-18"])
    d = sse.desk_payload()
    sits = {s["ticker"]: s for s in d["situations"]}
    assert "ABC" in sits
    assert sits["ABC"].get("cik"), "situation row lost the observation-ledger join key"
    e = sse.mastermind_emit()
    assert e["by_ticker"]["ABC"].get("cik"), "emit row lost the observation-ledger join key"
    assert arb  # the join key exists for the reducer's ledger lookup


# ---- F09-1: the collector lane that writes the ledger --------------------------------------

def test_deal_term_lane_writes_a_byte_bound_ledger_and_is_idempotent(tmp_path, monkeypatch):
    import json
    from engine import special_arb as arb
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    root = tmp_path / "special_situations"
    (root / "doc_cache").mkdir(parents=True)
    (root / "doc_cache" / "0000000001-26-000001.txt").write_text(_CASH_EXACT)
    ss._retain_source("0000000001-26-000001",
                      "<ACCEPTANCE-DATETIME>20260617173100\n" + _CASH_EXACT)
    pd.DataFrame([{"id": "e1", "form_type": "DEFM14A", "company": "ABC Inc", "cik": "0000000001",
                   "accession": "0000000001-26-000001", "ticker": "ABC", "items": None,
                   "date_filed": "2026-06-17", "source_url": "u"}]
                 ).to_parquet(root / "events.parquet")

    n = ss.enrich_deal_terms()
    assert n > 0
    path = root / "observations" / "observations.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    assert rows and all(r["schema"] == arb.OBSERVATION_SCHEMA for r in rows)
    price = next(r for r in rows if r["field"] == "price_per_share")
    assert price["normalized"] == 25.0
    # bound to bytes, not to a URL: the digest and the exact span both travel with the number
    assert len(price["source"]["body_sha256"]) == 64
    assert _CASH_EXACT[price["locator"]["start"]:price["locator"]["end"]] == price["locator"]["excerpt"]

    # a rebuild over unchanged bytes appends NOTHING — observation_id is a digest of the inputs
    assert ss.enrich_deal_terms() == 0
    assert len(path.read_text().splitlines()) == len(rows)


def test_deal_term_lane_reads_only_already_cached_bodies(tmp_path, monkeypatch):
    """The rights boundary: the lane must never open a parallel corpus of its own."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    root = tmp_path / "special_situations"
    root.mkdir(parents=True)
    pd.DataFrame([{"id": "e1", "form_type": "DEFM14A", "company": "ABC Inc", "cik": "1",
                   "accession": "0000000001-26-000001", "ticker": "ABC", "items": None,
                   "date_filed": "2026-06-17", "source_url": "u"}]
                 ).to_parquet(root / "events.parquet")

    def _boom(*a, **k):                      # any network fetch is a contract violation here
        raise AssertionError("the deal-term lane must not fetch; doc_cache only")
    monkeypatch.setattr(ss, "_get", _boom)
    assert ss.enrich_deal_terms() == 0       # no cached body -> nothing, and no fetch
    assert not (root / "observations").exists()


def test_deal_term_lane_ignores_events_outside_the_fixed_cash_categories(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    root = tmp_path / "special_situations"
    (root / "doc_cache").mkdir(parents=True)
    (root / "doc_cache" / "0000000002-26-000002.txt").write_text(
        "The Board declared a special cash dividend of $2.50 per share.")
    ss._retain_source("0000000002-26-000002",
                      "The Board declared a special cash dividend of $2.50 per share.")
    pd.DataFrame([{"id": "e2", "form_type": "SC 13D", "company": "XYZ Inc", "cik": "2",
                   "accession": "0000000002-26-000002", "ticker": "XYZ", "items": None,
                   "date_filed": "2026-06-17", "source_url": "u"}]
                 ).to_parquet(root / "events.parquet")
    assert ss.enrich_deal_terms() == 0


# ---- F09-1 repair: required REDs that only exist at the engine/build boundary ---------------

def test_a_malformed_last_ledger_line_is_partial_generation_not_a_healthy_subset(
        tmp_path, monkeypatch):
    """A truncated final write is a REAL failure. The old loader skipped it silently and
    published the surviving rows as a complete, healthy projection."""
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-06-16", "2026-06-18"])
    led = tmp_path / "special_situations" / "observations" / "observations.jsonl"
    led.write_text(led.read_text() + '{"schema":"special_situations.deal_term_obs')  # cut mid-write
    sits = [{"ticker": "ABC", "company": "ABC Inc", "category": "Acquisitions", "cik": "1",
             "stage": "pending", "date_filed": "2026-06-17"}]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    assert e["quality_state"] != arb.QUALITY_VERIFIED
    assert "PARTIAL_GENERATION" in e["reasons"] and "INTEGRITY_FAILED" in e["reasons"]
    assert e["ledger_census"]["malformed"] == 1


def test_a_forged_ledger_row_does_not_reach_the_projection(tmp_path, monkeypatch):
    import json
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=["2026-06-16", "2026-06-18"])
    led = tmp_path / "special_situations" / "observations" / "observations.jsonl"
    rows = [json.loads(x) for x in led.read_text().splitlines() if x.strip()]
    for r in rows:
        if r["field"] == "price_per_share":
            r["normalized"] = 999.0            # value swapped, observation_id left intact
    led.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n")
    sits = [{"ticker": "ABC", "company": "ABC Inc", "category": "Acquisitions", "cik": "1",
             "stage": "pending", "date_filed": "2026-06-17"}]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    assert e["quality_state"] != arb.QUALITY_VERIFIED
    assert e["offer_price"] != 999.0 and e["offer_price"] is None


def test_a_globally_stale_panel_cannot_certify_itself_as_current(tmp_path, monkeypatch):
    """The whole point of the independent calendar: when EVERY listing is equally behind, a
    panel-derived session count still reports 0 behind, because it can only see its own rows."""
    from engine import special_arb as arb
    _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT,
             sessions=["2026-05-04", "2026-05-05"])          # panel frozen six weeks back
    sits = [{"ticker": "ABC", "company": "ABC Inc", "category": "Acquisitions", "cik": "1",
             "stage": "pending", "date_filed": "2026-06-17"}]
    sse._enrich_arb(sits, now_utc=NOW_UTC)
    e = sits[0]["arb"]
    assert e["sessions_behind"] > 20, "a frozen panel certified itself as current"
    assert e["quality_state"] == arb.QUALITY_STALE_PRICE and e["orderable"] is False


def test_after_close_and_premarket_acceptance_pick_different_reference_sessions(
        tmp_path, monkeypatch):
    """Date-only `date_filed` cannot tell these apart, which is why it may not fix a reference
    session at all. With an exact acceptance time the reference is deterministic."""
    from engine import special_arb as arb
    sessions = ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18"]

    def _ref_for(acceptance):
        _f09_env(tmp_path, monkeypatch, text=_CASH_EXACT, sessions=sessions)
        led = tmp_path / "special_situations" / "observations" / "observations.jsonl"
        import json
        rows = [json.loads(x) for x in led.read_text().splitlines() if x.strip()]
        rebuilt = []
        for r in rows:
            r["source"] = dict(r["source"], acceptance_datetime=acceptance)
            r["observation_id"] = arb.observation_id(
                source=r["source"], field=r["field"], locator=r["locator"],
                normalized=r["normalized"])
            rebuilt.append(r)
        led.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rebuilt) + "\n")
        sits = [{"ticker": "ABC", "company": "ABC Inc", "category": "Acquisitions", "cik": "1",
                 "stage": "pending", "date_filed": "2026-06-17"}]
        sse._enrich_arb(sits, now_utc=NOW_UTC)
        return sits[0]["arb"]

    premarket = _ref_for("2026-06-17T07:45:00-04:00")   # before the 06-17 close
    after_close = _ref_for("2026-06-17T17:31:00-04:00")  # after it
    assert premarket["reference_session"] == "2026-06-16"
    assert after_close["reference_session"] == "2026-06-17"
    assert premarket["reference_session"] != after_close["reference_session"]


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
