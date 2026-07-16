"""Hermetic tests for the T2 multi-granularity seam (sub-industry + theme boards).

The state machine itself is covered by test_momentum_king.py. These tests validate
the NEW grouping/assembly layer: _assemble_groups + _rank_groups + build_board's
additive sections, and the build-script group-builder floors. Onset is pre-seeded
in the cache so tests are deterministic and never touch the canon/postcross engines.
"""
import numpy as np
import pandas as pd

from engine.momentum_king import (
    _assemble_groups,
    _rank_groups,
    build_board,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _rec(ticker, alpha, entry="intact", sector="S", **kw):
    return {"ticker": ticker, "name": ticker, "sector": sector,
            "alpha": alpha, "entry": entry, "sector_rank": kw.get("sector_rank", 1),
            "sector_n": kw.get("sector_n", 6), "rev_pctile": kw.get("rev_pctile", 40)}


def _onset(trend_legs=3, cs_active=False, extended=False, species="FRESH_INITIATION"):
    return {"trend_legs": trend_legs, "cs_active": cs_active, "extended": extended,
            "species": species, "fresh_cross": True, "ticks_since_cross": 2, "based": True}


def _long_closes(cols, n=200):
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({c: np.linspace(100.0, 120.0, n) for c in cols}, index=idx)


_COMMON = dict(flow_witness={}, options_ctx={}, alpha_min=0.5, min_legs=2, dominance_tau=0.5)


# ── _assemble_groups: the same state machine over an arbitrary grouping ──────────

def test_assemble_groups_reuses_state_machine():
    cache = {"AAA": _onset(), "BBB": _onset(trend_legs=1)}
    by_group = {"THEME_A": {"n": 5, "leaders": [_rec("AAA", 3.0), _rec("BBB", 0.4)]}}
    rows = _assemble_groups(by_group, pd.DataFrame(), label_key="theme",
                            onset_cache=cache, **_COMMON)
    assert len(rows) == 1
    r = rows[0]
    assert r["theme"] == "THEME_A"                      # label field carries through
    assert r["state"] == "LEADER_CANDIDATE" and r["leader"] == "AAA"
    assert r["dominance_margin"] == round(3.0 - 0.4, 3)


def test_contested_group_abstains():
    cache = {"A": _onset(), "B": _onset()}
    by_group = {"THEME_B": {"n": 4, "leaders": [_rec("A", 2.0), _rec("B", 1.9)]}}
    rows = _assemble_groups(by_group, pd.DataFrame(), label_key="theme",
                            onset_cache=cache, **_COMMON)
    assert rows[0]["state"] == "CONTESTED" and rows[0]["leader"] is None


def test_meta_merges_without_clobbering_state_fields():
    cache = {"A": _onset()}
    by_group = {"mag7": {"n": 5, "leaders": [_rec("A", 3.0)]}}
    meta = {"mag7": {"name": "Magnificent Seven", "category": "AI", "state": "SHOULD_NOT_WIN"}}
    rows = _assemble_groups(by_group, pd.DataFrame(), label_key="theme",
                            meta=meta, onset_cache=cache, **_COMMON)
    r = rows[0]
    assert r["name"] == "Magnificent Seven" and r["category"] == "AI"
    # meta must NOT overwrite the state-machine's own fields
    assert r["state"] == "NO_CLEAR_LEADER" or r["state"] == "LEADER_CANDIDATE"
    assert r["state"] != "SHOULD_NOT_WIN"


def test_overlap_produces_independent_records():
    # a ticker in two themes yields two INDEPENDENT member records (overlap is real)
    cache = {"NVDA": _onset(), "AMD": _onset(trend_legs=1)}
    by_group = {
        "mag7": {"n": 5, "leaders": [_rec("NVDA", 3.0), _rec("AMD", 0.3)]},
        "ai_semis": {"n": 5, "leaders": [_rec("NVDA", 2.5), _rec("AMD", 0.4)]},
    }
    rows = _assemble_groups(by_group, pd.DataFrame(), label_key="theme",
                            onset_cache=cache, **_COMMON)
    m0 = next(m for m in rows[0]["members"] if m["ticker"] == "NVDA")
    m1 = next(m for m in rows[1]["members"] if m["ticker"] == "NVDA")
    assert m0 is not m1                                 # not a shared/deduped object
    assert rows[0]["leader"] == "NVDA" and rows[1]["leader"] == "NVDA"


def test_rank_groups_orders_and_builds_top():
    rows = [
        {"theme": "x", "state": "NO_CLEAR_LEADER", "leader": None, "members": []},
        {"theme": "y", "state": "LEADER_CANDIDATE", "leader": "AAA",
         "members": [{"ticker": "AAA", "name": "AAA", "sector": "y", "alpha": 2.0,
                      "species": "FRESH_INITIATION", "trend_legs": 3,
                      "fresh_cross": True, "ticks_since_cross": 2}]},
    ]
    ranked, top = _rank_groups(rows)
    assert ranked[0]["state"] == "LEADER_CANDIDATE"      # candidates float to the top
    assert len(top) == 1 and top[0]["ticker"] == "AAA"


# ── build_board: additive back-compatibility ────────────────────────────────────

def _residual_fixture():
    return {"as_of": "2026-07-10",
            "by_sector": {"IT": {"n": 5, "leaders": [_rec("AAA", 2.0, sector="IT")]}}}


def test_build_board_backcompat_omits_new_sections():
    board = build_board(_residual_fixture(), pd.DataFrame())
    assert board["schema"] == "momentum_king.v1"
    assert "sectors" in board
    assert "themes" not in board and "sub_industries" not in board
    assert "n_themes" not in board["coverage"]


def test_build_board_additive_sections_and_meta():
    by_theme = {"mag7": {"n": 5, "leaders": [_rec("NVDA", 3.0)]}}
    theme_meta = {"mag7": {"name": "Magnificent Seven", "category": "AI"}}
    by_sub = {"Semiconductors": {"n": 6, "leaders": [_rec("NVDA", 3.0)]}}
    sub_meta = {"Semiconductors": {"sub_industry": "Semiconductors", "sector": "Technology"}}
    board = build_board(_residual_fixture(), pd.DataFrame(),
                        by_theme=by_theme, theme_meta=theme_meta,
                        by_sub_industry=by_sub, sub_meta=sub_meta)
    assert isinstance(board["themes"], list) and isinstance(board["sub_industries"], list)
    assert board["coverage"]["n_themes"] == 1 and board["coverage"]["n_sub_industries"] == 1
    assert board["themes"][0]["name"] == "Magnificent Seven"
    assert board["themes"][0]["theme"] == "mag7"          # basket id as label
    assert board["sub_industries"][0]["sector"] == "Technology"
    # sector spine is unchanged by the additive sections
    assert board["sectors"] == build_board(_residual_fixture(), pd.DataFrame())["sectors"]


# ── build-script group builders: floors + absent-safety (monkeypatched) ─────────

def test_below_min_theme_excluded_before_residual_call(monkeypatch):
    import scripts.build_momentum_king as bmk
    calls = []
    monkeypatch.setattr(bmk, "compute_residual_alpha", lambda **k: calls.append(k) or None)
    monkeypatch.setattr(bmk, "_membership", lambda: {"baskets": {
        "tiny": {"name": "Tiny", "members": [{"ticker": "A"}, {"ticker": "B"}, {"ticker": "C"}]},
    }})
    closes = _long_closes(["A", "B", "C"], n=200)         # 3 members < min 5
    by_theme, meta = bmk._build_theme_groups(closes, {}, min_members=5)
    assert by_theme == {} and meta == {}
    assert calls == []                                    # excluded BEFORE any residual pass


def test_name_remap_restores_company_name():
    import scripts.build_momentum_king as bmk
    blk = {"leaders": [{"ticker": "NVDA", "name": "NVDA", "sector": "THEME_X", "alpha": 2.0}],
           "laggards": []}
    bmk._remap_names(blk, {"NVDA": ("NVIDIA", "Technology")})
    assert blk["leaders"][0]["name"] == "NVIDIA"
    assert blk["leaders"][0]["sector"] == "THEME_X"       # group label left untouched


def test_absent_loaders_are_safe(monkeypatch):
    import scripts.build_momentum_king as bmk
    monkeypatch.setattr(bmk, "_membership", lambda: None)
    monkeypatch.setattr(bmk, "_industry_map", lambda: None)
    closes = _long_closes(["A", "B"], n=200)
    assert bmk._build_theme_groups(closes, {}) == ({}, {})
    assert bmk._build_subindustry_groups(closes, {}) == ({}, {})
