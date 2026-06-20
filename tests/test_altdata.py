"""Tests for the Quiver alt-data collector + engine (no network)."""
from __future__ import annotations

import json
import math
from datetime import date

import pandas as pd
import pytest

from collectors import quiver
from engine import altdata, altdata_alerts, altdata_ledger, altdata_signals
from engine.trumpflow import graph as tfgraph
from lib import config


_SYNTH_INTEL = {
    "as_of": "2026-06-19",
    "people": [{"id": "p1", "name": "Eric Trump", "name_zh": "埃里克"}],
    "themes": {"crypto": {"en": "Crypto", "zh": "加密"}, "ai": {"en": "AI infra", "zh": "AI基建"}},
    "entities": [
        {"id": "abtc", "name": "American Bitcoin", "ticker": "ABTC", "brand_theme": "crypto"},
        {"id": "hut", "name": "Hut 8", "ticker": "HUT", "brand_theme": "crypto"},
    ],
    "edges": [
        {"src": "p1", "rel": "CONTROLS", "dst": "abtc", "confidence": 0.95, "provenance": "FACT"},
        {"src": "abtc", "rel": "OPERATED_BY", "dst": "hut", "confidence": 0.95, "provenance": "FACT"},
        {"src": "hut", "rel": "HOLDS_STAKE", "dst": "abtc", "confidence": 0.95, "provenance": "FACT"},
        {"src": "abtc", "rel": "MEMBER_OF", "dst": "theme:crypto", "confidence": 0.9, "provenance": "FACT"},
        {"src": "hut", "rel": "MEMBER_OF", "dst": "theme:ai", "confidence": 0.85, "provenance": "INFERRED"},
    ],
}


# --------------------------------------------------------------- coercion helpers
def test_usd_range_and_scalar():
    assert altdata._usd("$1,001 - $15,000") == pytest.approx(8000.5)
    assert altdata._usd("48395.4") == pytest.approx(48395.4)
    assert altdata._usd("$1,000,001 - $5,000,000") == pytest.approx(3000000.5)
    assert math.isnan(altdata._usd("nan"))
    assert math.isnan(altdata._usd(None))


def test_f_and_s_and_side():
    assert altdata._f("$1,234.5") == pytest.approx(1234.5)
    assert math.isnan(altdata._f("None"))
    assert altdata._s("nan") is None
    assert altdata._s("  AAPL ") == "AAPL"
    assert altdata._side("Purchase") == "buy"
    assert altdata._side("Sale (Full)") == "sell"
    assert altdata._side("Exchange") is None


# --------------------------------------------------------------- collector merge
class _DummyAdapter(quiver.QuiverAdapter):
    name = "quiver_test"
    dataset = "t_set"
    endpoint = "/beta/live/x"
    key_cols = ("Ticker", "Date", "Transaction")


def test_merge_is_append_only_and_dedups(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    a = _DummyAdapter()

    first = pd.DataFrame([
        {"Ticker": "ABC", "Date": "2026-06-01", "Transaction": "Purchase", "Note": "v1"},
        {"Ticker": "XYZ", "Date": "2026-06-01", "Transaction": "Sale", "Note": "v1"},
    ])
    added, total = a._merge(first)
    assert (added, total) == (2, 2)
    seen0 = pd.read_parquet(a._table_path())["_first_seen"].iloc[0]

    # re-fetch the SAME ABC row (a correction "v2") + one genuinely new row
    second = pd.DataFrame([
        {"Ticker": "ABC", "Date": "2026-06-01", "Transaction": "Purchase", "Note": "v2"},
        {"Ticker": "QQQ", "Date": "2026-06-02", "Transaction": "Purchase", "Note": "v1"},
    ])
    added2, total2 = a._merge(second)
    assert added2 == 1 and total2 == 3            # only QQQ is new
    out = pd.read_parquet(a._table_path())
    abc = out[out["Ticker"] == "ABC"].iloc[0]
    assert abc["Note"] == "v1"                    # keep='first' -> PIT record preserved
    assert abc["_first_seen"] == seen0            # first-seen latency stamp is stable


def test_snapshot_feed_keys_on_collected(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    class _Snap(quiver.QuiverAdapter):
        name = "quiver_snaptest"; dataset = "snap"; endpoint = "/x"
        snapshot = True; key_cols = ("Ticker", "_collected")

    s = _Snap()
    df = pd.DataFrame([{"Ticker": "BB", "Count": "10"}])
    added, total = s._merge(df)
    assert added == total == 1
    assert "_collected" in pd.read_parquet(s._table_path()).columns


# --------------------------------------------------------------- engine signals
def _patch_reads(monkeypatch, tables: dict):
    monkeypatch.setattr(altdata, "_read", lambda ds: tables.get(ds))


def test_political_netflow(monkeypatch):
    congress = pd.DataFrame([
        {"Ticker": "AAA", "TransactionDate": "2026-06-10", "Transaction": "Purchase",
         "Representative": "Rep A", "BioGuideID": "A1", "Party": "R", "Range": "$1,001 - $15,000"},
        {"Ticker": "AAA", "TransactionDate": "2026-06-11", "Transaction": "Purchase",
         "Representative": "Rep B", "BioGuideID": "B2", "Party": "D", "Range": "$15,001 - $50,000"},
        {"Ticker": "AAA", "TransactionDate": "2026-06-12", "Transaction": "Sale",
         "Representative": "Rep C", "BioGuideID": "C3", "Party": "R", "Range": "$1,001 - $15,000"},
    ])
    _patch_reads(monkeypatch, {"congress": congress})
    res = altdata.political_netflow(window_days=3650)
    top = res["buys"][0]
    assert top["ticker"] == "AAA"
    assert top["buys"] == 2 and top["sells"] == 1 and top["net"] == 1
    assert top["members"] == 3
    assert top["est_usd"] > 0


def test_convergence_scores_distinct_channels():
    signals = {
        "political": {"buys": [{"ticker": "EFX", "net": 3, "members": 2}]},
        "gov_contracts": [{"ticker": "EFX", "total_usd": 1_000_000}],
        "trump": [{"ticker": "EFX", "side": "buy", "company": "EQUIFAX"}],
        "lobbying": [], "insiders": {"buys": []}, "offexchange": [],
        "cnbc": [], "inst_13f": {"adds": []},
    }
    rows = altdata.convergence(signals)
    assert rows and rows[0]["ticker"] == "EFX"
    assert rows[0]["score"] == 3
    assert set(rows[0]["channel_list"]) == {"congress_buy", "gov_contract", "trump_buy"}


def test_convergence_ignores_single_channel():
    signals = {"political": {"buys": [{"ticker": "ONE", "net": 1, "members": 1}]},
               "gov_contracts": [], "trump": [], "lobbying": [], "insiders": {"buys": []},
               "offexchange": [], "cnbc": [], "inst_13f": {"adds": []}}
    assert altdata.convergence(signals) == []


# --------------------------------------------------------------- per-ticker substrate
def test_by_ticker_inversion(monkeypatch):
    monkeypatch.setattr(altdata_signals, "_write", lambda out: None)
    feed = {"as_of": "2026-06-19", "signals": {
        "political": {"buys": [{"ticker": "EFX", "net": 2, "members": 2}]},
        "gov_contracts": [{"ticker": "EFX", "total_usd": 1_000_000}],
        "trump": [{"ticker": "EFX", "side": "buy"},
                  {"ticker": "BKNG", "side": "buy"}, {"ticker": "BKNG", "side": "sell"}],
        "lobbying": [], "insiders": {"buys": []}, "offexchange": [],
        "inst_13f": {"adds": []}, "cnbc": [], "corporate_donors": [{"ticker": "EFX", "total_usd": 50000}],
    }}
    out = altdata_signals.build(feed)
    efx = out["tickers"]["EFX"]
    # congress + gov_contract + trump = 3 real channels; the donor row is recorded but
    # must NOT count toward the score (else it would be 4)
    assert efx["convergence_score"] == 3
    assert set(efx["channels"]) == {"congress_buy", "gov_contract", "trump"}
    assert efx["trump_linked"] is True
    assert efx["donor_usd"] == 50000
    # a Trump buy+sell round-trip on one name is ONE channel, not two
    bkng = out["tickers"]["BKNG"]
    assert bkng["convergence_score"] == 1 and bkng["channels"] == ["trump"]


# --------------------------------------------------------------- alert change-detection
def test_alerts_fire_on_enter_only(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    bt = {"as_of": "2026-06-19", "tickers": {
        "EFX": {"convergence_score": 2, "channels": ["gov_contract", "trump"], "trump_linked": True},
        "NVDA": {"convergence_score": 2, "channels": ["13f_add", "darkpool_accum"], "trump_linked": False},
        "AAA": {"convergence_score": 1, "channels": ["congress_buy"], "trump_linked": False},
    }}
    fired1 = altdata_alerts.rebuild(bt)
    assert len(fired1) == 2                                    # EFX + NVDA; AAA below MIN_SCORE
    assert any(e["severity"] == "high" and "EFX" in e["headline"] for e in fired1)  # trump-linked => high
    assert any(e["severity"] == "medium" and "NVDA" in e["headline"] for e in fired1)

    assert altdata_alerts.rebuild(bt) == []                   # unchanged -> nothing new

    bt2 = {"as_of": "2026-06-19", "tickers": dict(bt["tickers"])}
    bt2["tickers"]["NVDA"] = {"convergence_score": 3, "channels": ["13f_add", "darkpool_accum", "congress_buy"], "trump_linked": False}
    fired3 = altdata_alerts.rebuild(bt2)                       # score increase -> re-fires
    assert len(fired3) == 1 and "NVDA" in fired3[0]["headline"]


# --------------------------------------------------------------- falsifiable ledger
def test_ledger_logs_scorable_and_scores(tmp_path, monkeypatch):
    import json
    idx = pd.date_range("2026-01-01", "2026-05-01", freq="B")
    n = len(idx)

    def fake_closes(tk, root):  # WIN beats SPY; LOSE lags; PRIV has no price
        if tk == "SPY":
            return pd.Series([100 * (1 + 0.05 * i / n) for i in range(n)], index=idx)
        if tk == "WIN":
            return pd.Series([50 * (1 + 0.20 * i / n) for i in range(n)], index=idx)
        if tk == "LOSE":
            return pd.Series([50 * (1 - 0.15 * i / n) for i in range(n)], index=idx)
        return None
    # one patch covers build (via _level_asof) AND score (via the scorer's reads)
    monkeypatch.setattr(altdata_ledger._desk, "_close_series", fake_closes)

    bt = {"as_of": "2026-01-02", "tickers": {
        "WIN": {"convergence_score": 2, "channels": ["congress_buy", "trump"], "trump_linked": True},
        "LOSE": {"convergence_score": 2, "channels": ["insider_buy", "gov_contract"], "trump_linked": False},
        "PRIV": {"convergence_score": 3, "channels": ["a", "b", "c"], "trump_linked": False},
    }}
    new = altdata_ledger.build_theses(bt, root=tmp_path, today=date(2026, 1, 2))
    assert {r["ticker"] for r in new} == {"WIN", "LOSE"}       # PRIV unscorable -> skipped
    assert all(r["lean"] == "overweight" and r["conviction"] == "low" for r in new)

    # vintage dedupe — same day, windows still active -> nothing new
    assert altdata_ledger.build_theses(bt, root=tmp_path, today=date(2026, 1, 2)) == []

    # score once the window has elapsed (check_by ~2026-04-03; data runs to 2026-05-01)
    track = altdata_ledger.score(root=tmp_path, today=date(2026, 5, 2))
    assert track["scored_total"] == 2
    scored = [json.loads(l) for l in (tmp_path / "data" / "altdata" / "scored.jsonl").read_text().splitlines()]
    outcome = {r["id"].split("-")[-2]: r["outcome"] for r in scored}
    assert outcome["WIN"] == "hit" and outcome["LOSE"] == "miss"
    assert track["overall"]["hit_rate"] == 0.5


# --------------------------------------------------------------- per-stock chip
def test_chip_shaping():
    c = altdata_signals.chip({
        "ticker": "EFX", "channels": ["gov_contract", "trump"], "convergence_score": 2,
        "trump_linked": True, "gov_contract_usd_30d": 74_700_004.0, "trump_side": "buy"})
    assert c["tier"] == "high"                       # convergent + trump-linked
    assert len(c["channels"]) == 2
    assert "convergence" in c["headline"]["en"]
    assert c["trump_linked"] is True
    assert "gov contracts" in c["detail"]["en"].lower()
    assert all(k in c for k in ("headline", "detail", "caveat"))  # bilingual chip shape
    # single-channel name -> still a chip, medium/low tier
    c1 = altdata_signals.chip({"channels": ["congress_buy"], "convergence_score": 1, "congress_members": 4})
    assert c1["tier"] == "low" and c1["score"] == 1
    # nothing to show -> None
    assert altdata_signals.chip({"channels": []}) is None
    assert altdata_signals.chip(None) is None


# --------------------------------------------------------------- noise filter / picks
def test_is_passive_classifier():
    from engine import altdata_picks as ap
    assert ap.is_passive("VANGUARD S&P 500 ETF UNSOLICITED", None) is True
    assert ap.is_passive("Ishares Tr Russell 1000 Etf", None) is True
    assert ap.is_passive("Some Money Market Fund", None) is True
    assert ap.is_passive(None, "SPY") is True                  # broad ETF ticker
    # specific operating companies must NOT be flagged (incl. the 'Fidelity National' trap)
    assert ap.is_passive("Equifax Inc", "EFX") is False
    assert ap.is_passive("NVIDIA Corp", "NVDA") is False
    assert ap.is_passive("Fidelity National Information Services", "FIS") is False


def test_build_picks_filters_passive(monkeypatch):
    from engine import altdata_picks as ap
    monkeypatch.setattr(ap, "_rs_vs_spy", lambda tk, root, win=60: 3.5)
    feed = {"signals": {"trump": [
        {"ticker": "EFX", "company": "Equifax Inc", "side": "buy"},
        {"ticker": None, "company": "VANGUARD S&P 500 ETF", "side": "buy"},
        {"ticker": "VOO", "company": "Vanguard 500 Index", "side": "buy"},
    ]}}
    bt = {"tickers": {"EFX": {"convergence_score": 2, "channels": ["gov_contract", "trump"], "trump_linked": True}}}
    out = ap.build_picks(feed, bt, root=None, top=10)
    assert out["filtered_passive"] == 2                        # the two Vanguard/ETF rows
    tickers = [p["ticker"] for p in out["picks"]]
    assert "EFX" in tickers and "VOO" not in tickers           # specific kept, passive dropped
    efx = next(p for p in out["picks"] if p["ticker"] == "EFX")
    assert efx["convergence"] == 2 and efx["trump_linked"] is True
    assert "leading" in efx["verdict"]["en"]                   # +3.5pp vs SPY


# --------------------------------------------------------------- latent-stake graph
def test_graph_catches_label_mismatch():
    mm = tfgraph.label_mismatches(_SYNTH_INTEL)
    assert len(mm) == 1                                       # deduped (parent reached 2 ways)
    m = mm[0]
    assert m["entity_ticker"] == "ABTC"                       # branded crypto
    assert m["real_theme"]["id"] == "ai"                      # value accrues to AI infra
    assert m["repointed_ticker"] == "HUT"                     # flip the subject to the parent


def test_graph_short_path_to_real_theme():
    paths = tfgraph.short_paths(_SYNTH_INTEL)
    ai = [p for p in paths if p["theme"]["id"] == "ai"]
    assert ai, "expected an Eric Trump -> ... -> AI infra path"
    assert ai[0]["endpoint_ticker"] == "HUT"                  # the investable proxy is the parent


def test_graph_view_cross_references_altdata(monkeypatch):
    monkeypatch.setattr(tfgraph, "load_intel", lambda root=None: _SYNTH_INTEL)
    monkeypatch.setattr(tfgraph, "_write", lambda v: None)
    bt = {"tickers": {"HUT": {"convergence_score": 2, "channels": ["gov_contract", "trump"]}}}
    v = tfgraph.build_view(bt)
    hut = next(w for w in v["watch"] if w["ticker"] == "HUT")
    assert hut["alt_corroborated"] is True and hut["alt_score"] == 2
    abtc = next(w for w in v["watch"] if w["ticker"] == "ABTC")
    assert abtc["alt_corroborated"] is False                  # not in the live alt-data set


# --------------------------------------------------------------- LLM extractor (gate)
def test_extractor_citation_gate():
    from engine.trumpflow import extract
    source = ("Eric Trump's American Bitcoin is majority-owned by Hut 8, which retains "
              "an 80% stake and serves as its exclusive infrastructure partner.")
    reply = json.dumps({"edges": [
        # valid — citation is verbatim in the source
        {"src": "Hut 8", "rel": "HOLDS_STAKE", "dst": "American Bitcoin",
         "citation": "retains an 80% stake"},
        # hallucinated citation — not in the source -> must be DROPPED
        {"src": "Eric Trump", "rel": "CONTROLS", "dst": "World Liberty",
         "citation": "Eric Trump owns a controlling interest in World Liberty Financial"},
        # invalid rel -> dropped
        {"src": "Hut 8", "rel": "BANANA", "dst": "American Bitcoin", "citation": "Hut 8"},
    ]})
    edges = extract._extract_edges(source, reply)
    assert len(edges) == 1
    assert edges[0]["rel"] == "HOLDS_STAKE" and edges[0]["dst"] == "American Bitcoin"
    assert edges[0]["provenance"] == "INFERRED" and edges[0]["status"] == "candidate"
    # garbage reply / no key path -> empty, never raises
    assert extract._extract_edges(source, "not json at all") == []
    assert extract._extract_edges(source, None) == []


def test_extract_strip_html():
    from engine.trumpflow import extract
    html = "<html><body><p>Hut 8 retains an <b>80%</b> stake &amp; more.</p></body></html>"
    txt = extract._strip_html(html)
    assert "Hut 8 retains an 80% stake & more." in txt and "<" not in txt


def test_extract_run_watermark(tmp_path, monkeypatch):
    from engine.trumpflow import extract
    src = "Hut 8 retains an 80% stake in American Bitcoin."
    reply = json.dumps({"edges": [{"src": "Hut 8", "rel": "HOLDS_STAKE",
                                   "dst": "American Bitcoin", "citation": "retains an 80% stake"}]})
    monkeypatch.setattr(extract, "enabled", lambda: True)
    monkeypatch.setattr(extract._ct, "_client", lambda cfg: object())   # non-None => not gated on key
    monkeypatch.setattr(extract, "_call", lambda text, cfg: reply)
    monkeypatch.setattr(extract, "_news_items", lambda root=None, limit=40: [
        {"text": src, "url": "http://x", "time": "2026-06-01", "source_id": "filing:abc", "source_type": "filing"}])
    monkeypatch.setattr(extract, "_filing_items", lambda root=None, limit=15: [])

    r1 = extract.run(root=tmp_path)
    assert r1["extracted"] == 1 and r1["processed"] == 1
    cands = extract.load_candidates(tmp_path)
    assert len(cands) == 1 and cands[0]["rel"] == "HOLDS_STAKE" and cands[0]["source_type"] == "filing"
    # watermarked — the same source is not re-processed on the next run
    r2 = extract.run(root=tmp_path)
    assert r2["processed"] == 0 and r2["extracted"] == 0


# --------------------------------------------------------------- EDGAR early channel
def test_edgar_parse():
    from collectors.edgar_trumpflow import EdgarTrumpflowAdapter as A
    hit = {"_id": "0001558370-25-007236:hut-20250509xex99d1.htm", "_source": {
        "ciks": ["0001964789"], "adsh": "0001558370-25-007236", "form": "8-K",
        "file_type": "EX-99.1", "file_date": "2025-05-12",
        "display_names": ["Hut 8 Corp.  (HUT)  (CIK 0001964789)"], "items": ["7.01", "8.01"]}}
    row = A._parse(hit, "Hut 8")
    assert row["ticker"] == "HUT"
    assert row["form"] == "8-K" and row["company"] == "Hut 8 Corp."
    assert row["cik"] == "0001964789" and row["items"] == "7.01,8.01"
    assert row["url"] == ("https://www.sec.gov/Archives/edgar/data/1964789/"
                          "000155837025007236/hut-20250509xex99d1.htm")
    assert row["query"] == "Hut 8" and row["form"] in A.RELEVANT_FORMS
    # no id -> None; a company without a parenthesized ticker -> ticker None
    assert A._parse({"_source": {}}, "x") is None
    noticker = A._parse({"_id": "x:y.htm", "_source": {"display_names": ["Some LLC"], "form": "8-K"}}, "q")
    assert noticker["ticker"] is None and noticker["company"] == "Some LLC"
