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
from datetime import date


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
    and must not pull the scoring path into the import graph."""
    import sys
    assert sse.SCORED is False
    # importing the engine must not have imported regime/conditions/run
    assert not any(m in sys.modules for m in
                   ("engine.regime", "engine.conditions", "engine.run", "conditions"))


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
    assert sse.classify("8-K", "5.02") == ("Management Changes", "change", "mgmt_maybe")
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


def test_build_mgmt_502_only_when_filer_active(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sse, "_universe_caps", lambda: ({}, {}))
    (tmp_path / "special_situations").mkdir()
    _events([
        {"id": "a", "form_type": "8-K", "company": "ROUTINE CO", "cik": "111", "items": "5.02", "date_filed": "2026-06-12"},
        {"id": "b", "form_type": "8-K", "company": "ACTIVIST TGT", "cik": "222", "items": "5.02", "date_filed": "2026-06-12"},
        {"id": "c", "form_type": "SC 13D", "company": "ACTIVIST TGT", "cik": "222", "items": None, "date_filed": "2026-06-11"},
    ]).to_parquet(tmp_path / "special_situations" / "events.parquet")
    df = sse.build_situations().set_index("id")
    assert df.loc["a", "status"] == "skip"                 # routine officer change dropped
    assert df.loc["b", "status"] == "ok"                   # filer is an activist target -> kept
    assert df.loc["b", "category"] == "Management Changes"


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


def test_summary_lane_llm_ready_gate(monkeypatch):
    monkeypatch.setattr(config, "secret", lambda n: "key")
    assert ss._llm_ready({"enabled": True, "llm_brief": True}) is True
    assert ss._llm_ready({"enabled": True, "llm_brief": False}) is False
    assert ss._llm_ready({"enabled": False, "llm_brief": True}) is False
    monkeypatch.setattr(config, "secret", lambda n: None)
    assert ss._llm_ready({"enabled": True, "llm_brief": True}) is False   # no key


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
