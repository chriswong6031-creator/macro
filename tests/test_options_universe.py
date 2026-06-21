"""Tests for engine.options_universe — the shared options-snapshot universe resolver that
build_polygon_gex + build_options_flow use, so the GEX accrual and the flow desk read the
SAME set (anchors + baskets, deduped, capped, anchors kept under the cap)."""
import json

from engine import options_universe as ou
from lib import config


def test_anchors_only_when_baskets_excluded():
    syms = ou.gex_symbols({"symbols": ou.DEFAULT_ANCHORS, "include_baskets": False})
    assert syms == [s.upper() for s in ou.DEFAULT_ANCHORS]


def test_includes_baskets_when_enabled():
    anchors_only = ou.gex_symbols({"symbols": ou.DEFAULT_ANCHORS, "include_baskets": False})
    expanded = ou.gex_symbols({"symbols": ou.DEFAULT_ANCHORS, "include_baskets": True,
                               "max_underlyings": 1000})
    assert len(expanded) > len(anchors_only)
    # anchors stay first and present
    assert expanded[:len(anchors_only)] == anchors_only
    assert all(a in expanded for a in [s.upper() for s in ou.DEFAULT_ANCHORS])


def test_dedup_and_uppercase():
    syms = ou.gex_symbols({"symbols": ["spy", "SPY", "qqq"], "include_baskets": False})
    assert syms == ["SPY", "QQQ"]               # case-normalised + deduped, order preserved


def test_cap_never_drops_an_anchor():
    # cap below the anchor count must still keep every anchor (anchors take the first slots)
    capped = ou.gex_symbols({"symbols": ou.DEFAULT_ANCHORS, "include_baskets": True,
                             "max_underlyings": 3})
    assert len(capped) == len(ou.DEFAULT_ANCHORS)
    assert all(a in capped for a in [s.upper() for s in ou.DEFAULT_ANCHORS])


def test_baskets_universe_real_membership():
    bu = ou.baskets_universe()
    # the live membership file should yield a sizeable, clean, upper-cased ticker set
    assert len(bu) > 50
    assert all(isinstance(t, str) and t == t.upper() for t in bu)
    assert len(bu) == len(set(bu))              # deduped


def test_baskets_universe_excludes_removed(monkeypatch, tmp_path):
    doc = {"baskets": {"x": {"members": [
        {"ticker": "AAA", "removed": None},
        {"ticker": "BBB", "removed": "2024-01-01"},   # dropped -> excluded
        {"ticker": "ccc", "removed": None},
    ]}}}
    bdir = tmp_path / "baskets"
    bdir.mkdir()
    (bdir / "membership.json").write_text(json.dumps(doc))
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    bu = ou.baskets_universe()
    assert bu == ["AAA", "CCC"]                 # BBB removed; upper-cased


def test_graceful_when_membership_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)   # empty dir, no membership.json
    assert ou.baskets_universe() == []
    # with no baskets file, include_baskets just yields the anchors
    assert ou.gex_symbols({"symbols": ou.DEFAULT_ANCHORS, "include_baskets": True}) == \
        [s.upper() for s in ou.DEFAULT_ANCHORS]
