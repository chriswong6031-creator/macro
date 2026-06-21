"""Analyst revision-momentum: the CHANGE in consensus, not the level."""
from __future__ import annotations

import pandas as pd

from engine import analyst_revisions as ar
from engine.stock_fundamentals import _analyst


def _recs(rows):
    return pd.DataFrame(rows)


def test_revision_multi_period_upgrading():
    df = _recs([
        {"ticker": "AAA", "period": "2026-04-01", "strongBuy": 2, "buy": 3,
         "hold": 5, "sell": 1, "strongSell": 0, "prev_buy": 4},
        {"ticker": "AAA", "period": "2026-05-01", "strongBuy": 4, "buy": 4,
         "hold": 3, "sell": 0, "strongSell": 0, "prev_buy": 5},
    ])
    r = ar.revision_for(df)
    assert r["direction"] == "upgrading"              # net-buy 5 -> 8
    assert r["revision_delta"] == 3.0
    assert r["n_periods"] == 2
    assert r["consensus_pct"] == round(8 / 11 * 100, 1)   # LEVEL = context only


def test_revision_multi_period_downgrading():
    df = _recs([
        {"ticker": "BBB", "period": "2026-04-01", "strongBuy": 5, "buy": 3,
         "hold": 2, "sell": 0, "strongSell": 0, "prev_buy": 7},
        {"ticker": "BBB", "period": "2026-05-01", "strongBuy": 2, "buy": 2,
         "hold": 4, "sell": 2, "strongSell": 1, "prev_buy": 8},
    ])
    r = ar.revision_for(df)
    assert r["direction"] == "downgrading" and r["revision_delta"] == -4.0  # 8 -> 4
    assert r["weighted_delta"] is not None and r["weighted_delta"] < 0


def test_revision_single_period_uses_prev_buy():
    df = _recs([{"ticker": "CCC", "period": "2026-05-01", "strongBuy": 3, "buy": 2,
                 "hold": 1, "sell": 0, "strongSell": 0, "prev_buy": 3}])
    r = ar.revision_for(df)
    assert r["n_periods"] == 1
    assert r["revision_delta"] == 2.0 and r["direction"] == "upgrading"  # 5 vs prev_buy 3
    assert r["weighted_delta"] is None


def test_revision_single_period_no_prev_is_stable():
    df = _recs([{"ticker": "DDD", "period": "2026-05-01", "strongBuy": 1, "buy": 1,
                 "hold": 1, "sell": 0, "strongSell": 0, "prev_buy": None}])
    r = ar.revision_for(df)
    assert r["revision_delta"] is None and r["direction"] == "stable"


def test_weighted_tilt_sign():
    assert ar._weighted({"strongBuy": 4, "buy": 2, "hold": 1, "sell": 0, "strongSell": 0}, 7) > 0
    assert ar._weighted({"strongBuy": 0, "buy": 0, "hold": 1, "sell": 2, "strongSell": 4}, 7) < 0
    assert ar._weighted({"strongBuy": 0, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}, 0) is None


def test_revision_map_and_empty():
    assert ar.revision_map(pd.DataFrame()) == {}
    assert ar.revision_map(None) == {} or isinstance(ar.revision_map(None), dict)
    df = _recs([{"ticker": "AAA", "period": "2026-05-01", "strongBuy": 1, "buy": 1,
                 "hold": 1, "sell": 0, "strongSell": 0, "prev_buy": 2}])
    assert "AAA" in ar.revision_map(df)


def test_analyst_panel_attaches_revision_block():
    rev = {"direction": "upgrading", "revision_delta": 3.0, "consensus_pct": 72.7,
           "n_analysts": 11, "n_periods": 2, "latest_period": "2026-05-01"}
    out = _analyst("AAA", None, rev)                  # lite tier (no deep snapshot)
    assert out["revision"]["direction"] == "upgrading"
    assert out["revision"]["delta"] == 3.0 and out["revision"]["consensus_pct"] == 72.7
    assert _analyst("AAA", None, None).get("revision") is None
