"""engine.altdata_confirmers — roll the leading rerating confirmers (insider clusters /
award accel) from data/altdata/by_ticker.json up to the foresight themes. Pure / fixture.
"""
from __future__ import annotations

from engine import altdata_confirmers as ac


def test_theme_confirmers_rolls_up_leading_and_context():
    tickers = {
        "MU": {"channels": ["insider_cluster"], "insider_buyers": 4, "insider_net_usd": 1e6},
        "WDC": {"channels": ["gov_contract_accel"], "gov_contract_accel": 5.0, "gov_contract_usd_30d": 2e7},
        "STX": {"channels": ["patent_cluster"]},
    }
    r = ac._theme_confirmers("Memory", ["MU", "WDC", "STX", "NTAP"], tickers)
    assert r["n_leading"] == 2                       # insider + gov are 2 distinct leading channels
    assert r["insider_cluster"][0]["ticker"] == "MU" and r["insider_cluster"][0]["buyers"] == 4
    assert r["gov_accel"][0]["ticker"] == "WDC"
    assert "patent_cluster" in r["context"]          # context kept separate, not scored
    assert set(r["leading_members"]) == {"MU", "WDC"}


def test_context_only_or_none():
    # only a context channel -> n_leading 0 but still returned (context present)
    r = ac._theme_confirmers("X", ["AAA"], {"AAA": {"channels": ["13f_add"]}})
    assert r is not None and r["n_leading"] == 0 and "13f_add" in r["context"]
    # no leading and no context -> None
    assert ac._theme_confirmers("Y", ["BBB"], {"BBB": {"channels": ["special_situation"]}}) is None


def test_compute_over_config_theme():
    byt = {"as_of": "2026-06-28", "tickers": {
        "MU": {"channels": ["insider_cluster"], "insider_buyers": 3, "insider_net_usd": 5e5},
        "WDC": {"channels": ["gov_contract_accel"], "gov_contract_accel": 4.0, "gov_contract_usd_30d": 1e7},
    }}
    out = ac.compute_altdata_confirmers(by_ticker=byt)
    assert out is not None
    ms = out["themes"].get("memory_storage")          # MU/WDC are memory_storage members
    assert ms and ms["n_leading"] == 2


def test_compute_none_on_empty():
    assert ac.compute_altdata_confirmers(by_ticker={"tickers": {}}) is None
    assert ac.compute_altdata_confirmers(by_ticker={}) is None
