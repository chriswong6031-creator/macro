"""Tests for the Signal Intelligence layer — newly-activated Quiver feeds, the weighted
convergence kernel, the multi-actor influence graph, the Opus brain, and the Mastermind
emit. No network, no LLM (the brain call is injected)."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from engine import altdata_models as M
from engine import altdata_brain as B
from engine import altdata_emit as EM
from engine import altdata_signals
from engine.influence import graph as IG
from lib import config


# =========================================================================== new feeds
def test_app_ratings_momentum(monkeypatch):
    df = pd.DataFrame([
        {"Ticker": "AAA", "App": "Big App", "Rating": 4.6, "Count": 5000, "Time": "2026-06-13"},
        {"Ticker": "AAA", "App": "Tiny", "Rating": 3.0, "Count": 10, "Time": "2026-06-13"},
        {"Ticker": "BBB", "App": "Meh", "Rating": 3.2, "Count": 2000, "Time": "2026-06-13"},
    ])
    monkeypatch.setattr(M, "_read", lambda ds: df if ds == "appratings" else None)
    rows = M.app_ratings_momentum()
    aaa = next(r for r in rows if r["ticker"] == "AAA")
    assert aaa["reviews"] == 5010
    assert aaa["rating"] == pytest.approx((4.6 * 5000 + 3.0 * 10) / 5010, abs=0.01)
    assert aaa["lean"] == "strong"                       # >=4.3 rating AND >=1000 reviews
    assert next(r for r in rows if r["ticker"] == "BBB")["lean"] == "soft"   # rating < 3.5


def test_patent_velocity(monkeypatch):
    df = pd.DataFrame(
        [{"Ticker": "QCOM", "Date": "2026-06-09", "IPC": f"H04L9/4{i}", "Title": "x"} for i in range(4)]
        + [{"Ticker": "AAA", "Date": "2026-06-09", "IPC": "G06F", "Title": "y"}])
    monkeypatch.setattr(M, "_read", lambda ds: df if ds == "patents" else None)
    rows = M.patent_velocity(window_days=3650)
    q = next(r for r in rows if r["ticker"] == "QCOM")
    assert q["patents"] == 4 and q["ipc_classes"] >= 1


def test_bill_catalysts_sector_map(monkeypatch):
    df = pd.DataFrame([
        {"title": "Defense Appropriations", "summary": "funds the armed forces and missile defense",
         "billType": "HR", "number": "1", "currentChamber": "House", "lastActionDate": "2026-06-10",
         "url": "u", "lastAction": "Reported"},
        {"title": "Generic Naming Act", "summary": "renames a post office, nothing market-relevant",
         "billType": "HR", "number": "2", "currentChamber": "House", "lastActionDate": "2026-06-09",
         "url": "u", "lastAction": "x"},
    ])
    monkeypatch.setattr(M, "_read", lambda ds: df if ds == "bills" else None)
    rows = M.bill_catalysts()
    assert len(rows) == 1 and rows[0]["sector"] == "Defense"     # only the sector-mapped bill


def test_congress_holdings_parse(monkeypatch):
    df = pd.DataFrame([
        {"Politician": "A", "Holdings": '{"AAA": 24000, "BBB": 8000}', "Type": "Rep"},
        {"Politician": "B", "Holdings": '{"AAA": -40000}', "Type": "Sen"},   # |abs| size
        {"Politician": "C", "Holdings": "not json", "Type": "Rep"},          # skipped, no crash
    ])
    monkeypatch.setattr(M, "_read", lambda ds: df if ds == "congressholdings" else None)
    agg = M.congress_holdings()
    assert agg["AAA"]["position_usd"] == 64000 and agg["AAA"]["holders"] == 2


# =========================================================================== convergence kernel
def test_channel_records_upgrades_and_weights(monkeypatch):
    monkeypatch.setattr(M, "_dpi_z_lookup", lambda: {})
    signals = {
        "political": {"buys": [{"ticker": "AAA", "net": 5, "members": 4},
                               {"ticker": "BBB", "net": 1, "members": 1}]},
        "gov_contracts": [{"ticker": "AAA", "total_usd": 1e8, "accel_x": 3.0}],
        "insiders": {"buys": [{"ticker": "AAA", "net_usd": 1e6, "buyers": 4}]},
        "inst_13f": {"adds": [{"ticker": "AAA", "fund": "Berkshire Hathaway", "chg_usd": 5e6}]},
    }
    recs = M.channel_records(signals)
    aaa = recs["AAA"]
    # every strong read is UPGRADED and replaces its weaker base channel
    assert "congress_cluster" in aaa["channels"] and "congress_buy" not in aaa["channels"]
    assert "gov_contract_accel" in aaa["channels"] and "gov_contract" not in aaa["channels"]
    assert "insider_cluster" in aaa["channels"] and "insider_buy" not in aaa["channels"]
    assert "smart_money_13f" in aaa["channels"] and "13f_add" not in aaa["channels"]
    assert aaa["weighted_score"] == pytest.approx(1.0 + 0.9 + 0.85 + 0.8, abs=0.01)
    assert recs["BBB"]["channels"] == ["congress_buy"]          # single member, not a cluster


def test_channel_records_gov_accel_floor(monkeypatch):
    monkeypatch.setattr(M, "_dpi_z_lookup", lambda: {})
    # huge accel ratio but tiny absolute $ -> NOT an accel channel (floor kills the noise)
    recs = M.channel_records({"gov_contracts": [{"ticker": "AAA", "total_usd": 1000, "accel_x": 10.0}]})
    assert recs["AAA"]["channels"] == ["gov_contract"]


def test_channel_records_affiliation_channel(monkeypatch):
    monkeypatch.setattr(M, "_dpi_z_lookup", lambda: {})
    recs = M.channel_records({"political": {"buys": [{"ticker": "AAA", "net": 1, "members": 1}]}},
                             affiliations={"AAA": "Elon Musk controls"})
    assert "affiliation" in recs["AAA"]["channels"] and recs["AAA"]["count"] == 2


def test_by_ticker_uses_weighted_kernel(monkeypatch):
    monkeypatch.setattr(M, "_dpi_z_lookup", lambda: {})
    monkeypatch.setattr(altdata_signals, "_write", lambda out: None)
    feed = {"as_of": "2026-06-19", "signals": {
        "political": {"buys": [{"ticker": "AAA", "net": 5, "members": 4}]},
        "insiders": {"buys": [{"ticker": "AAA", "net_usd": 1e6, "buyers": 4}]},
    }}
    out = altdata_signals.build(feed, affiliations={"AAA": "Cathie Wood holds"})
    aaa = out["tickers"]["AAA"]
    assert aaa["convergence_score"] == 3                        # cluster + insider_cluster + affiliation
    assert aaa["weighted_score"] > 2.0 and aaa["affiliated"] is True
    assert out["schema"] == "altdata.by_ticker.v2"


# =========================================================================== influence graph
_INTEL = {"as_of": "2026-06-19",
          "people": [{"id": "eric_trump", "name": "Eric Trump"}],
          "themes": {"crypto": {"en": "Crypto", "zh": "加密"}},
          "entities": [{"id": "abtc", "name": "American Bitcoin", "ticker": "ABTC", "brand_theme": "crypto"}],
          "edges": [{"src": "eric_trump", "rel": "CONTROLS", "dst": "abtc", "confidence": 0.9, "provenance": "FACT"}]}
_SEED = {"schema": "influence.seed.v1", "as_of": "2026-06-19",
         "actors": [
             {"id": "musk", "name": "Elon Musk", "kind": "exec", "tickers": ["TSLA"]},
             {"id": "pelosi", "name": "Nancy Pelosi", "kind": "politician", "tickers": ["NVDA"]},
         ],
         "themes": {"ev": {"en": "EV", "zh": "电动车"}},
         "entities": [{"id": "tesla", "name": "Tesla", "ticker": "TSLA", "brand_theme": "ev"}],
         "edges": [
             {"src": "pelosi", "rel": "HOLDS_STAKE", "dst": "ticker:NVDA", "confidence": 0.9, "provenance": "DISCLOSED"},
             {"src": "musk", "rel": "TALKS_ABOUT", "dst": "theme:ev", "confidence": 0.7, "provenance": "INFERRED"},
         ]}


def _seed_dirs(tmp_path):
    (tmp_path / "data" / "trumpflow").mkdir(parents=True)
    (tmp_path / "data" / "altdata").mkdir(parents=True)
    (tmp_path / "data" / "trumpflow" / "intel.json").write_text(json.dumps(_INTEL))
    (tmp_path / "data" / "altdata" / "influence_seed.json").write_text(json.dumps(_SEED))


def test_influence_merge_and_kind_aware_synthesis(tmp_path):
    _seed_dirs(tmp_path)
    g = IG.load_seed(root=tmp_path)
    ids = {a["id"] for a in g["actors"]}
    assert {"eric_trump", "musk", "pelosi"} <= ids                # Trump cohort merged in
    affil = IG.affiliations(g)
    # exec -> CONTROLS from .tickers; politician -> NOT control (explicit HOLDS_STAKE wins)
    tsla = {a["rel"] for a in affil["TSLA"]}
    nvda = {a["rel"] for a in affil["NVDA"]}
    assert "CONTROLS" in tsla and "CONTROLS" not in nvda
    assert "HOLDS_STAKE" in nvda


def test_influence_label_mismatch(tmp_path, monkeypatch):
    # ABTC branded crypto but its OPERATED_BY/MEMBER_OF parent is in AI infra -> repoint
    intel = {"as_of": "x", "people": [{"id": "p", "name": "P"}],
             "themes": {"crypto": {"en": "Crypto"}, "ai": {"en": "AI"}},
             "entities": [{"id": "abtc", "name": "ABTC", "ticker": "ABTC", "brand_theme": "crypto"},
                          {"id": "hut", "name": "Hut 8", "ticker": "HUT", "brand_theme": "crypto"}],
             "edges": [{"src": "abtc", "rel": "OPERATED_BY", "dst": "hut", "confidence": 0.9, "provenance": "FACT"},
                       {"src": "hut", "rel": "MEMBER_OF", "dst": "theme:ai", "confidence": 0.85, "provenance": "INFERRED"}]}
    (tmp_path / "data" / "trumpflow").mkdir(parents=True)
    (tmp_path / "data" / "altdata").mkdir(parents=True)
    (tmp_path / "data" / "trumpflow" / "intel.json").write_text(json.dumps(intel))
    g = IG.load_seed(root=tmp_path)
    mm = IG.label_mismatches(g)
    assert any(m["entity_ticker"] == "ABTC" and m["repointed_ticker"] == "HUT" for m in mm)


# =========================================================================== brain
def test_brain_derive_check():
    assert B._derive_check("AAA", "overweight", 63, 0.05)["op"] == "<"
    assert B._derive_check("AAA", "avoid", 63, 0.05)["op"] == ">"
    assert B._derive_check("AAA", "overweight", 63, 0.05)["subject_ticker"] == "AAA"


def test_brain_reconcile_clamps():
    t1 = B._reconcile({"action": "ACCUMULATE", "extended": True, "lean": "overweight"})
    assert t1["action"] == "WATCH" and "extended" in t1["clamped"]
    t2 = B._reconcile({"action": "ACCUMULATE", "extended": False, "lean": "avoid"})
    assert t2["action"] == "AVOID"
    t3 = B._reconcile({"action": "ACCUMULATE", "extended": False, "lean": "overweight"})
    assert t3["action"] == "ACCUMULATE" and "clamped" not in t3       # legitimate buy untouched


def test_brain_synthesize_mocked(tmp_path, monkeypatch):
    # synthesize emits article3 governance events via append_event(root=None)
    # → config.data_dir(); redirect so they land in tmp, not the real
    # data/neuralweb/governance.jsonl.
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")

    state = {"as_of": "2026-06-19", "n_clusters": 1, "clusters": [
        {"ticker": "AAA", "weighted_score": 1.5, "channels": ["x"], "rs_vs_spy_60d": 5,
         "extended": False, "scorable": True}]}
    reply = json.dumps({"regime_read": "aligned", "theses": [
        {"ticker": "AAA", "lean": "overweight", "conviction": "high", "action": "ACCUMULATE",
         "horizon_d": 63, "thesis": "t", "second_order": ["S1"], "evidence": ["e"],
         "dissent": "d", "falsifier_text": "f"}]})
    brief = B.synthesize(state, call=lambda sysp, usr: (reply, None))
    assert brief["regime_read"] == "aligned" and len(brief["theses"]) == 1
    th = brief["theses"][0]
    assert th["action"] == "ACCUMULATE" and th["falsifier"]["check"]["subject_ticker"] == "AAA"
    assert th["second_order"] == ["S1"]


def test_brain_no_call_degrades(tmp_path, monkeypatch):
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")

    brief = B.synthesize({"as_of": "x", "n_clusters": 0, "clusters": []}, call=None)
    assert brief["degraded_reason"] == "no_client_or_token" and brief["theses"] == []


def test_brain_ledger_logs_only_scorable(tmp_path, monkeypatch):
    idx = pd.date_range("2026-01-01", "2026-05-01", freq="B")
    n = len(idx)

    def closes(tk, root):
        if tk == "SPY":
            return pd.Series([100 * (1 + 0.05 * i / n) for i in range(n)], index=idx)
        if tk == "WIN":
            return pd.Series([50 * (1 + 0.2 * i / n) for i in range(n)], index=idx)
        return None                                          # PRIV has no price -> unscorable
    monkeypatch.setattr(B._desk, "_close_series", closes)
    brief = {"generated_at": "2026-01-02T00:00:00Z", "state_asof": "2026-01-02", "theses": [
        {"ticker": "WIN", "lean": "overweight", "conviction": "high", "action": "ACCUMULATE",
         "horizon_d": 63, "scorable": True,
         "falsifier": {"text": "x", "check": B._derive_check("WIN", "overweight", 63, 0.05)},
         "check_by": "2026-04-03"},
        {"ticker": "PRIV", "lean": "overweight", "conviction": "low", "action": "WATCH",
         "horizon_d": 63, "scorable": True,
         "falsifier": {"text": "x", "check": B._derive_check("PRIV", "overweight", 63, 0.05)},
         "check_by": "2026-04-03"}]}
    logged = B._append_ledger(brief, tmp_path)
    assert {r["ticker"] for r in logged} == {"WIN"}          # PRIV has no price -> not logged


# =========================================================================== emit
def test_emit_ranking_score_and_filter(tmp_path):
    by_ticker = {"as_of": "2026-06-19", "tickers": {
        "AAA": {"ticker": "AAA", "convergence_score": 4, "weighted_score": 2.0,
                "channels": ["gov_contract_accel", "trump"], "trump_linked": True},
        "BBB": {"ticker": "BBB", "convergence_score": 1, "weighted_score": 0.4,
                "channels": ["retail_buzz"], "trump_linked": False},
    }}
    brain = {"theses": [{"ticker": "AAA", "conviction": "high", "action": "ACCUMULATE",
                         "lean": "overweight", "extended": False, "thesis": "t",
                         "second_order": ["S1"], "rs_vs_spy_60d": 5,
                         "falsifier": {"check": {}}}]}
    influence = {"watch": [{"ticker": "AAA", "n_actors": 3,
                            "actors": [{"actor": "Musk", "rel": "CONTROLS", "kind": "exec"}]}]}
    out = EM.build_mastermind(by_ticker, brain, influence, {}, {}, root=tmp_path, top=10)
    tickers = [s["ticker"] for s in out["signals"]]
    assert "AAA" in tickers and "BBB" not in tickers          # BBB: 1 channel, no brain, no affil -> filtered
    aaa = next(s for s in out["signals"] if s["ticker"] == "AAA")
    assert aaa["source"] == "brain" and aaa["action"] == "ACCUMULATE" and aaa["direction"] == "long"
    assert aaa["signal_score"] >= 90 and aaa["n_affiliated_actors"] == 3
    assert out["schema"] == "altdata.mastermind.v1"


def test_emit_deterministic_when_no_brain(tmp_path):
    by_ticker = {"as_of": "x", "tickers": {
        "AAA": {"ticker": "AAA", "convergence_score": 4, "weighted_score": 1.7,
                "channels": ["a", "b", "c", "d"], "trump_linked": False}}}
    out = EM.build_mastermind(by_ticker, {}, {}, {}, {}, root=tmp_path, top=10)
    aaa = out["signals"][0]
    assert aaa["source"] == "deterministic" and aaa["action"] == "WATCH"
    assert aaa["conviction"] == "high"                       # weighted 1.7 >= high band
    assert out["brain_present"] is False


# =========================================================================== emit honesty (W0 audit fixes)

def test_emit_det_conviction_no_double_count(tmp_path):
    """(a) Deterministic path: conviction bonus must NOT be added back to the score.
    A name with count=4, weighted=1.8 must score identically regardless of whether
    _det_conviction returns 'high' or 'medium' — both are derived from the same weighted
    base that already drives the score spine."""
    by_ticker = {"as_of": "x", "tickers": {
        # count=4 → _det_conviction="high"; weighted=1.8 → base = min(60, 1.8*32) = 57.6
        "HI": {"ticker": "HI", "convergence_score": 4, "weighted_score": 1.8,
               "channels": ["a", "b", "c", "d"], "trump_linked": False},
        # count=4 → _det_conviction="high" BUT force a scenario where we need to check
        # the medium path: weighted=0.5 (below _W_MED=0.9) but count>=4 → still "high"
        # We directly test _signal_score for the medium case to isolate the guard
    }}
    out = EM.build_mastermind(by_ticker, {}, {}, {}, {}, root=tmp_path, top=10)
    hi = out["signals"][0]
    assert hi["source"] == "deterministic"
    # Directly verify that changing conviction label does not affect deterministic score
    from engine.altdata_emit import _signal_score
    score_high = _signal_score(1.8, "high", "WATCH", None, False, 0, source="deterministic")
    score_med  = _signal_score(1.8, "medium", "WATCH", None, False, 0, source="deterministic")
    assert score_high == score_med, (
        f"deterministic score must be conviction-label-invariant: high={score_high}, med={score_med}")


def test_emit_det_extended_clamp_from_rs(tmp_path):
    """(b) Deterministic extended flag: rs > _EXTENDED_PP triggers the −15 dock even with
    no brain, and rs <= _EXTENDED_PP does not.

    RS is now computed DIRECTLY from yahoo parquets (not from the picks list).
    We build yahoo parquets where EXT outperforms SPY by ~40pp and NON by ~10pp.
    """
    import pandas as pd
    yahoo = tmp_path / "data" / "yahoo"
    yahoo.mkdir(parents=True)
    idx = pd.date_range("2025-01-01", periods=200, freq="B")
    # SPY: flat
    spy_p = [100.0] * 200
    pd.DataFrame({"close": spy_p}, index=idx).to_parquet(yahoo / "SPY.parquet")
    # EXT: up +40% over 60 days (from bar 140 onward) → RS ≈ +40pp
    ext_p = [50.0] * 140 + [50.0 * (1 + i * 0.40 / 60) for i in range(60)]
    pd.DataFrame({"close": ext_p}, index=idx).to_parquet(yahoo / "EXT.parquet")
    # NON: up +10% over 60 days → RS ≈ +10pp
    non_p = [50.0] * 140 + [50.0 * (1 + i * 0.10 / 60) for i in range(60)]
    pd.DataFrame({"close": non_p}, index=idx).to_parquet(yahoo / "NON.parquet")

    by_ticker = {"as_of": "x", "tickers": {
        "EXT": {"ticker": "EXT", "convergence_score": 3, "weighted_score": 1.5,
                "channels": ["a", "b", "c"], "trump_linked": False},
        "NON": {"ticker": "NON", "convergence_score": 3, "weighted_score": 1.5,
                "channels": ["a", "b", "c"], "trump_linked": False},
    }}
    out = EM.build_mastermind(by_ticker, {}, {}, {"picks": []}, {}, root=tmp_path, top=10)
    # EXT may be rolling_over (recently strong) or in signals — check both lists
    all_sigs = out["signals"] + out.get("broken_signals", [])
    by_tk = {s["ticker"]: s for s in all_sigs}
    assert by_tk["EXT"]["extended"] is True,  f"rs={by_tk['EXT']['rs_vs_spy_60d']} > 35 → extended must be True"
    assert by_tk["NON"]["extended"] is False, f"rs={by_tk['NON']['rs_vs_spy_60d']} ≤ 35 → extended must be False"
    # EXT gets the −15 dock; NON does not — so EXT must score lower (same weighted base).
    assert by_tk["EXT"]["signal_score"] < by_tk["NON"]["signal_score"], (
        f"extended name must score lower; got EXT={by_tk['EXT']['signal_score']}, NON={by_tk['NON']['signal_score']}")
    # Verify the -15 dock fires in isolation via _signal_score (same rs → isolates the extended flag)
    from engine.altdata_emit import _signal_score
    score_ext = _signal_score(1.5, "medium", "WATCH", 20.0, True,  0, source="deterministic")
    score_non = _signal_score(1.5, "medium", "WATCH", 20.0, False, 0, source="deterministic")
    assert score_non - score_ext == 15, (
        f"isolated −15 dock check failed: non={score_non}, ext={score_ext}")


def test_emit_brain_usable_flag(tmp_path):
    """(c) brain_usable is emitted and correctly False when brain is degraded."""
    by_ticker = {"as_of": "x", "tickers": {
        "AAA": {"ticker": "AAA", "convergence_score": 2, "weighted_score": 1.0,
                "channels": ["a", "b"], "trump_linked": False},
    }}
    # Healthy brain: theses present, no degraded_reason
    brain_ok = {"theses": [{"ticker": "AAA", "conviction": "high", "action": "ACCUMULATE",
                             "lean": "overweight", "extended": False, "thesis": "t",
                             "second_order": [], "rs_vs_spy_60d": 5, "falsifier": {}}]}
    out_ok = EM.build_mastermind(by_ticker, brain_ok, {}, {}, {}, root=tmp_path, top=10)
    assert out_ok["brain_usable"] is True, "healthy brain → brain_usable should be True"

    # Degraded brain: degraded_reason is set
    brain_deg = {"theses": [], "degraded_reason": "no_client_or_token"}
    out_deg = EM.build_mastermind(by_ticker, brain_deg, {}, {}, {}, root=tmp_path, top=10)
    assert out_deg["brain_usable"] is False, "degraded brain → brain_usable should be False"

    # No brain at all
    out_none = EM.build_mastermind(by_ticker, {}, {}, {}, {}, root=tmp_path, top=10)
    assert out_none["brain_usable"] is False, "absent brain → brain_usable should be False"
