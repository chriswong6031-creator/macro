"""Tests for the multi-day ΔOI positioning read (engine.options_flow.oi_positioning) — the
RELIABLE, trade-signing-free 'smart-money positioning' signal: day-over-day open-interest
change (Garleanu-Pedersen-Poteshman net demand)."""
import glob

import pandas as pd
import pytest

from engine import options_flow as of


def _today(rows):
    return pd.DataFrame(rows, columns=["ticker", "is_call", "strike", "expiry", "oi", "delta"]) \
        .assign(expiry=lambda d: pd.to_datetime(d["expiry"]))


def _prior(rows):
    return pd.DataFrame(rows, columns=["ticker", "oi"])


def test_doi_net_and_call_put_split():
    today = _today([
        ("AC", True, 100.0, "2026-07-17", 300.0, 0.5),    # call +200
        ("BP", False, 90.0, "2026-07-17", 120.0, -0.4),   # put  +20
        ("NC", True, 110.0, "2026-07-17", 50.0, 0.3),     # brand-new contract (today only)
    ])
    prior = _prior([("AC", 100.0), ("BP", 100.0)])
    r = of.oi_positioning(today, prior, 100.0, "2026-06-19", "2026-06-18")
    assert r["available"] and r["reliable"] is True
    assert r["call_doi"] == 200 and r["put_doi"] == 20 and r["net_doi"] == 220
    assert r["n_matched"] == 2 and r["n_new_contracts"] == 1 and r["new_contract_oi"] == 50
    assert r["doi_pc"] == 0.1                              # put/call = 20/200
    assert r["tone"] == "pos" and "CALL" in r["lean_en"]   # calls dominate -> bullish lean
    assert r["top_build"][0]["cp"] == "C" and r["top_build"][0]["doi"] == 200
    assert r["days_back"] == 1


def test_doi_put_dominant_is_defensive():
    today = _today([
        ("AC", True, 100.0, "2026-07-17", 110.0, 0.5),    # call +10
        ("BP", False, 90.0, "2026-07-17", 400.0, -0.4),   # put  +300
    ])
    prior = _prior([("AC", 100.0), ("BP", 100.0)])
    r = of.oi_positioning(today, prior, 100.0, "2026-06-19", "2026-06-18")
    assert r["tone"] == "neg" and "PUT" in r["lean_en"]    # puts dominate -> defensive/hedging


def test_doi_matched_only_excludes_new_from_net():
    # a giant brand-new contract must NOT swing the matched-contract headline net
    today = _today([
        ("AC", True, 100.0, "2026-07-17", 105.0, 0.5),    # call +5 (matched)
        ("HUGE", False, 50.0, "2026-07-17", 99999.0, -0.4),
    ])
    prior = _prior([("AC", 100.0)])
    r = of.oi_positioning(today, prior, 100.0, "2026-06-19", "2026-06-18")
    assert r["net_doi"] == 5 and r["n_new_contracts"] == 1   # HUGE counted separately, not in net


def test_doi_unwind_detected():
    today = _today([("AC", True, 100.0, "2026-07-17", 40.0, 0.5)])   # call -60
    prior = _prior([("AC", 100.0)])
    r = of.oi_positioning(today, prior, 100.0, "2026-06-19", "2026-06-18")
    assert r["net_doi"] == -60 and not r["opening"]
    assert r["top_unwind"] and r["top_unwind"][0]["doi"] == -60


def test_doi_needs_two_snapshot_days():
    today = _today([("AC", True, 100.0, "2026-07-17", 100.0, 0.5)])
    assert of.oi_positioning(today, None, 100.0, "2026-06-19", None)["available"] is False
    assert of.oi_positioning(today, _prior([]), 100.0, "2026-06-19", "2026-06-18")["available"] is False
    assert of.oi_positioning(None, _prior([("AC", 1.0)]), 100.0, "x", "y")["available"] is False


def test_build_flow_surfaces_positioning_and_drives_tone():
    # minimal massive minute schema for one bought call so sign_volume produces an agg
    minute = pd.DataFrame({
        "ticker": ["O:X1", "O:X1"], "underlying": ["X", "X"],
        "window_start": [1_700_000_000_000_000_000, 1_700_000_060_000_000_000],
        "close": [1.0, 1.2], "volume": [10.0, 10.0],
        "expiry": pd.to_datetime(["2026-07-17", "2026-07-17"]),
        "is_call": [True, True], "strike": [100.0, 100.0]})
    greeks = pd.DataFrame({"ticker": ["O:X1"], "gamma": [0.01], "delta": [0.5], "oi": [100.0]})
    oi_today = _today([("O:X1", True, 100.0, "2026-07-17", 400.0, 0.5)])   # +300 calls
    prior = _prior([("O:X1", 100.0)])
    payload = of.build_flow("X", minute, greeks, 100.0, "2026-06-19",
                            oi_today=oi_today, prior_oi=prior, prior_asof="2026-06-18")
    assert payload["available"]
    pos = payload["positioning"]
    assert pos["available"] and pos["net_doi"] == 300 and pos["tone"] == "pos"
    # reliable positioning lean drives the verdict tone + appears in the headline
    assert payload["verdict"]["tone"] == "pos"
    assert payload["verdict"]["positioning_reliable"] is True
    assert "CALL positioning" in payload["verdict"]["en"]


def test_build_flow_without_prior_oi_has_no_positioning():
    minute = pd.DataFrame({
        "ticker": ["O:X1"], "underlying": ["X"], "window_start": [1_700_000_000_000_000_000],
        "close": [1.0], "volume": [10.0], "expiry": pd.to_datetime(["2026-07-17"]),
        "is_call": [True], "strike": [100.0]})
    payload = of.build_flow("X", minute, None, 100.0, "2026-06-19")
    assert payload["positioning"]["available"] is False


@pytest.mark.skipif(not glob.glob("data/polygon_gex/chains/*.parquet"),
                    reason="no snapshot chains stored")
def test_doi_on_real_chains_smoke():
    """On the real accrued chains, a day-pair with genuine OI change yields a coherent read;
    a static (weekend / T+1-stale) pair yields net 0 — both correct."""
    fs = sorted(glob.glob("data/polygon_gex/chains/*.parquet"))
    if len(fs) < 2:
        pytest.skip("need >=2 chain files")
    found_change = False
    for i in range(1, len(fs)):
        t = pd.read_parquet(fs[i]).rename(columns={"strike_ticker": "ticker"})
        p = pd.read_parquet(fs[i - 1]).rename(columns={"strike_ticker": "ticker"})
        sub = t[t["underlying"] == "SPY"]
        if sub.empty:
            continue
        tsub = sub[["ticker", "is_call", "K", "expiry", "oi", "delta"]].rename(columns={"K": "strike"})
        psub = p[p["underlying"] == "SPY"][["ticker", "oi"]]
        r = of.oi_positioning(tsub, psub, float(sub["spot"].iloc[0]),
                              fs[i].split("/")[-1][:10], fs[i - 1].split("/")[-1][:10])
        assert r["available"] and r["reliable"]
        assert r["net_doi"] == r["call_doi"] + r["put_doi"]
        if r["net_doi"] != 0:
            found_change = True
    assert found_change, "expected at least one day-pair with real OI change"
