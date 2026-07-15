"""Hermetic unit tests for engine/momentum_king.py (MK-1).

No I/O, no parquet fixtures. The deterministic core — the K-of-N eligibility
gates and the per-sector state machine — is exercised exhaustively; the onset
overlay (which calls the real canon/postcross engines) gets a smoke test on a
synthetic price series.
"""
import numpy as np
import pandas as pd

from engine.momentum_king import (
    SCHEMA,
    build_board,
    classify_name,
    confluence_onset,
    sector_state,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _rec(ticker, alpha, entry="intact", **kw):
    return {"ticker": ticker, "name": ticker, "sector": kw.get("sector", "S"),
            "alpha": alpha, "entry": entry, "sector_rank": kw.get("sector_rank", 1),
            "sector_n": kw.get("sector_n", 6), "rev_pctile": kw.get("rev_pctile", 40)}


def _onset(trend_legs=3, cs_active=False, extended=False, species="FRESH_INITIATION"):
    return {"trend_legs": trend_legs, "cs_active": cs_active, "extended": extended,
            "species": species, "fresh_cross": True, "ticks_since_cross": 4,
            "based": True}


def _price_series(n=400, start=100.0, drift=0.03, seed=0):
    idx = pd.bdate_range("2024-01-01", periods=n)
    t = np.arange(n)
    # deterministic gentle uptrend + a slow oscillation — enough structure for a cross
    vals = start * (1 + drift) ** (t / 252.0) * (1 + 0.05 * np.sin(t / 23.0))
    return pd.Series(vals, index=idx)


# ── classify_name: the K-of-N gates ────────────────────────────────────────────

def test_classify_all_gates_pass():
    m = classify_name(_rec("AAA", 1.2), _onset())
    assert m["eligible"] is True
    assert m["gates"] == {"alpha_leader": True, "confluence_bull": True, "not_extended": True}
    assert m["reasons"] == []


def test_classify_alpha_below_leader_blocks():
    m = classify_name(_rec("AAA", 0.1), _onset())
    assert m["eligible"] is False
    assert "alpha_below_leader" in m["reasons"]


def test_classify_extended_blocks_and_residual_entry_extended_blocks():
    m1 = classify_name(_rec("AAA", 1.0), _onset(extended=True))
    assert m1["eligible"] is False and "extended" in m1["reasons"]
    # residual_alpha's own overlay says extended → also blocks (end-of-run guard)
    m2 = classify_name(_rec("AAA", 1.0, entry="extended"), _onset(extended=False))
    assert m2["eligible"] is False and "extended" in m2["reasons"]


def test_classify_active_sell_blocks():
    m = classify_name(_rec("AAA", 1.0), _onset(cs_active=True))
    assert m["eligible"] is False and "active_sell" in m["reasons"]


def test_classify_weak_confluence_blocks():
    m = classify_name(_rec("AAA", 1.0), _onset(trend_legs=1))
    assert m["eligible"] is False and "weak_confluence" in m["reasons"]


# ── sector_state: the honest abstain ────────────────────────────────────────────

def test_state_no_eligible_is_no_clear_leader():
    members = [{"ticker": "A", "alpha": 0.2, "eligible": False},
               {"ticker": "B", "alpha": 0.1, "eligible": False}]
    st = sector_state(members, dominance_tau=0.5)
    assert st["state"] == "NO_CLEAR_LEADER" and st["leader"] is None


def test_state_unique_dominant_leader():
    members = [{"ticker": "A", "alpha": 2.0, "eligible": True},
               {"ticker": "B", "alpha": 0.3, "eligible": False}]
    st = sector_state(members, dominance_tau=0.5)
    assert st["state"] == "LEADER_CANDIDATE" and st["leader"] == "A"
    assert st["dominance_margin"] == round(2.0 - 0.3, 3)


def test_state_two_eligible_no_separation_is_contested():
    members = [{"ticker": "A", "alpha": 1.0, "eligible": True},
               {"ticker": "B", "alpha": 0.8, "eligible": True}]
    st = sector_state(members, dominance_tau=0.5)  # margin 0.2 < 0.5
    assert st["state"] == "CONTESTED" and st["leader"] is None


def test_state_lone_eligible_not_separated_from_field_is_contested():
    # A is the only eligible name but an ineligible B sits right behind it → no
    # cross-sectional dominance, so we must NOT crown A.
    members = [{"ticker": "A", "alpha": 1.0, "eligible": True},
               {"ticker": "B", "alpha": 0.9, "eligible": False}]
    st = sector_state(members, dominance_tau=0.5)
    assert st["state"] == "CONTESTED" and st["leader"] is None


# ── build_board: envelope + plumbing ────────────────────────────────────────────

def _residual_fixture():
    return {
        "as_of": "2026-07-10",
        "by_sector": {
            "Semiconductors": {"n": 5, "leaders": [
                _rec("AAA", 2.0, sector="Semiconductors"),
                _rec("BBB", 0.2, entry="neutral", sector="Semiconductors"),
            ]},
            "Software": {"n": 4, "leaders": [
                _rec("CCC", 0.1, entry="laggard", sector="Software"),
            ]},
        },
    }


def test_build_board_envelope_and_null_coverage():
    # empty close panel → no onset coverage → confluence gate fails everywhere →
    # every sector abstains. Deterministic, no dependence on canon internals.
    board = build_board(_residual_fixture(), pd.DataFrame())
    assert board["schema"] == SCHEMA
    assert board["as_of"] == "2026-07-10"
    assert {s["sector"] for s in board["sectors"]} == {"Semiconductors", "Software"}
    assert all(s["state"] == "NO_CLEAR_LEADER" for s in board["sectors"])
    assert board["coverage"]["n_leader_candidates"] == 0
    assert board["top_candidates"] == []
    # params echo the frozen prospective seeds
    assert board["params"]["dominance_tau"] == 0.5


def test_build_board_none_on_missing_residual():
    assert build_board({}, pd.DataFrame()) is None
    assert build_board({"by_sector": None}, pd.DataFrame()) is None


# ── confluence_onset: smoke on a real series + short-series guard ────────────────

def test_confluence_onset_smoke_long_series():
    from engine.canon import confluence_signals
    s = _price_series(420)
    o = confluence_onset(s)
    conf = confluence_signals(s)
    assert set(o) >= {"fresh_cross", "trend_legs", "species", "extended", "cs_active"}
    # on a sufficiently long series the trend-leg count is a real int in [0, 4]
    assert o["trend_legs"] is None or 0 <= o["trend_legs"] <= 4
    # BUG-1 regression: ticks_since_cross rides the SAME canon CB grid as cb_recent,
    # so if canon saw any confluence buy, onset MUST report a tick count.
    if not conf.empty and bool(conf["CB"].any()):
        assert o["ticks_since_cross"] is not None
    # a "recent" cross is within FRESH_WITHIN buckets by construction (no divergence).
    if o.get("cb_recent"):
        assert o["ticks_since_cross"] is not None and o["ticks_since_cross"] <= 3


def test_confluence_onset_short_series_is_all_null():
    o = confluence_onset(_price_series(40))
    assert o["trend_legs"] is None and o["fresh_cross"] is None and o["species"] is None


def test_state_null_alpha_second_member_still_crowns_leader():
    # BUG-2: a null-alpha #2 must be SKIPPED, not poison the margin into a false CONTESTED
    members = [{"ticker": "A", "alpha": 2.0, "eligible": True},
               {"ticker": "B", "alpha": None, "eligible": False},
               {"ticker": "C", "alpha": 0.3, "eligible": False}]
    st = sector_state(members, dominance_tau=0.5)
    assert st["state"] == "LEADER_CANDIDATE" and st["leader"] == "A"
    assert st["dominance_margin"] == round(2.0 - 0.3, 3)


def test_state_single_member_cannot_demonstrate_dominance():
    # BUG-4: a lone member (no competitor in the field) abstains regardless of alpha
    st = sector_state([{"ticker": "A", "alpha": 3.0, "eligible": True}], dominance_tau=0.5)
    assert st["state"] == "NO_CLEAR_LEADER" and st["leader"] is None


def test_classify_dual_reason_weak_and_active_sell():
    # BUG-5: BOTH failure causes must surface in reasons, not just the first
    m = classify_name(_rec("AAA", 1.0), _onset(trend_legs=1, cs_active=True))
    assert m["eligible"] is False
    assert "weak_confluence" in m["reasons"] and "active_sell" in m["reasons"]


def test_classify_unknown_extension_fails_closed():
    # BUG-3: extended=None (short history / no postcross) must BLOCK, not pass silently
    onset = {"trend_legs": 3, "cs_active": False, "extended": None, "species": None,
             "fresh_cross": False, "ticks_since_cross": None, "based": None}
    m = classify_name(_rec("AAA", 1.0), onset)
    assert m["eligible"] is False
    assert m["gates"]["not_extended"] is False
    assert "not_enough_history" in m["reasons"]
