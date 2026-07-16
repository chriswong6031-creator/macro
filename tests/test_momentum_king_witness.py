"""Hermetic tests for the T4 (MK-P2) subordinate witnesses — net-inflow + options tide.

The load-bearing property: a witness ANNOTATES a leader but can NEVER create, kill, or
reorder a candidate. Plus loader absent-safety and the signing-free / magnitude-only
guarantees (no direction-bearing options field ever escapes). No Bash, no parquet, no net.
"""
import copy
import json

import pandas as pd

from engine.momentum_king import build_board


def _rec(ticker, alpha, sector="S", **kw):
    return {"ticker": ticker, "name": ticker, "sector": sector, "alpha": alpha,
            "entry": "intact", "sector_rank": kw.get("sector_rank", 1),
            "sector_n": kw.get("sector_n", 6), "rev_pctile": kw.get("rev_pctile", 40)}


def _residual():
    return {"as_of": "2026-07-10",
            "by_sector": {"IT": {"n": 6, "leaders": [_rec("AAA", 3.0, sector="IT"),
                                                     _rec("BBB", 0.2, sector="IT")]}}}


def _strip_witnesses(board):
    b = copy.deepcopy(board)
    for s in b.get("sectors", []):
        for m in s.get("members", []):
            m.pop("net_inflow_witness", None)
            m.pop("options_context", None)
    return b


# ── The invariant: witnesses never change state / eligibility / ordering ─────────

def test_witness_never_changes_state():
    residual = _residual()
    closes = pd.DataFrame()                       # empty → deterministic (all abstain)
    fw = {"AAA": {"flow_z": 9.9, "recurrence_count": 10, "source": "flow_leaders.v1"}}
    oc = {"AAA": {"net_doi": 99999, "positioning_lean": "net new CALL positioning",
                  "source": "options_flow.context.v1", "direction_reliable": False}}
    b_without = build_board(residual, closes)
    b_with = build_board(residual, closes, flow_witness=fw, options_ctx=oc)

    # stripping the witness keys makes the two boards STRUCTURALLY IDENTICAL:
    # witnesses cannot change any state / eligibility / coverage / ordering.
    assert _strip_witnesses(b_with) == b_without
    assert b_with["coverage"] == b_without["coverage"]
    assert b_with["top_candidates"] == b_without["top_candidates"]

    # the witness attached, and the engine (not the loader) owns authority_tier
    m = b_with["sectors"][0]["members"][0]
    assert m["ticker"] == "AAA"
    assert m["net_inflow_witness"]["authority_tier"] == "display"
    assert m["options_context"]["authority_tier"] == "display"


def test_witness_on_ineligible_member_does_not_promote():
    # AAA is ineligible here (empty closes → no confluence) — a monster witness must
    # NOT flip it eligible or crown the sector.
    residual = _residual()
    b = build_board(residual, pd.DataFrame(),
                    flow_witness={"AAA": {"flow_z": 99.0}},
                    options_ctx={"AAA": {"net_doi": 10 ** 9}})
    assert b["sectors"][0]["state"] == "NO_CLEAR_LEADER"
    assert b["sectors"][0]["leader"] is None
    assert b["coverage"]["n_leader_candidates"] == 0


# ── Loader absent-safety + signing-free guarantees (monkeypatched) ───────────────

def test_flow_witness_absent_safe(monkeypatch, tmp_path):
    import scripts.build_momentum_king as bmk
    monkeypatch.setattr(bmk, "_FLOW_LEADERS_JSON", tmp_path / "nope.json")
    assert bmk._build_flow_witness({"AAA"}) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    monkeypatch.setattr(bmk, "_FLOW_LEADERS_JSON", bad)
    assert bmk._build_flow_witness({"AAA"}) == {}


def test_flow_witness_signing_free_only(monkeypatch, tmp_path):
    import scripts.build_momentum_king as bmk
    p = tmp_path / "leaders.json"
    p.write_text(json.dumps({
        "stale": False, "cold_start": False,
        "board_a": [{"ticker": "AAA", "flow_z": 3.2, "recurrence_count": 7,
                     "A2_flow_z_hot": True, "net_premium_mn": -500.0,
                     "B5_flow_inflect": True, "signing_source": "tape"}],
        "board_b": [], "etf_strip": [],
    }))
    monkeypatch.setattr(bmk, "_FLOW_LEADERS_JSON", p)
    w = bmk._build_flow_witness({"AAA", "ZZZ"})
    assert "AAA" in w and "ZZZ" not in w                 # absent ticker omitted
    aaa = w["AAA"]
    assert aaa["flow_z"] == 3.2 and aaa["recurrence_count"] == 7
    assert aaa["A2_flow_z_hot"] is True
    assert aaa["stale"] is False                         # meaningful False survives the prune
    # BANNED (~-soft / direction-bearing) fields never emitted
    assert "net_premium_mn" not in aaa and "B5_flow_inflect" not in aaa


def test_options_context_magnitude_only(monkeypatch, tmp_path):
    import scripts.build_momentum_king as bmk
    p = tmp_path / "mm.json"
    p.write_text(json.dumps({
        "asof": "2026-07-08",
        "names": {"AAA": {"net_doi": 1200, "positioning_lean": "net new CALL positioning",
                          "zerodte_share": 0.35, "net_premium_mn": -389.0,
                          "signed_pc": 0.9, "tone": "bullish", "verdict": "buy"}},
    }))
    monkeypatch.setattr(bmk, "_OPTIONS_CTX_JSON", p)
    aaa = bmk._build_options_context({"AAA"})["AAA"]
    assert aaa["net_doi"] == 1200 and aaa["asof"] == "2026-07-08"
    assert aaa["net_premium_mn_mag"] == 389.0            # abs magnitude, no sign
    assert aaa["direction_reliable"] is False
    # BANNED direction-bearing fields never escape
    for banned in ("signed_pc", "tone", "verdict", "net_premium_mn", "gamma_flow_bn"):
        assert banned not in aaa


def test_options_context_omits_when_no_useful_fields(monkeypatch, tmp_path):
    import scripts.build_momentum_king as bmk
    p = tmp_path / "mm.json"
    p.write_text(json.dumps({"asof": "2026-07-08", "names": {"AAA": {"spot": 100.0}}}))
    monkeypatch.setattr(bmk, "_OPTIONS_CTX_JSON", p)
    assert bmk._build_options_context({"AAA"}) == {}     # no bare chip on empty data


def test_leader_tickers_union_across_granularities():
    import scripts.build_momentum_king as bmk
    residual = {"by_sector": {"IT": {"leaders": [{"ticker": "AAA"}]}}}
    by_theme = {"mag7": {"leaders": [{"ticker": "NVDA"}]}}
    by_sub = {"Semis": {"leaders": [{"ticker": "AAA"}, {"ticker": "MU"}]}}
    assert bmk._leader_tickers(residual, by_theme, by_sub) == {"AAA", "NVDA", "MU"}
