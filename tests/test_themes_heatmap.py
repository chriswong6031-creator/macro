"""Pure-function tests for the Finviz themes treemap engine.

Covers the theme → subsector → member assembly: the contract shape the shared
``heatmap.js`` renderer consumes (``map_type='themes'``, sectors=themes, tiles=
subsectors carrying a member list), subsector/member perf wiring, count-based
sizing, bilingual theme labels, and graceful handling of missing perf. No
network; everything is driven by small in-memory fixtures.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import themes_heatmap as th  # noqa: E402


def _tree():
    return [
        {"theme": "Artificial Intelligence", "key": "Artificial Intelligence", "subsectors": [
            {"key": "aicompute", "name": "Compute", "description": "Compute & Acceleration",
             "members": ["NVDA", "AMD", "MSFT"]},
            {"key": "aimodels", "name": "Models", "description": "Foundation Models",
             "members": ["GOOGL", "META"]},
        ]},
        {"theme": "FinTech", "key": "FinTech", "subsectors": [
            {"key": "fintechpayments", "name": "Payments", "description": "Payments",
             "members": ["V", "MA"]},
        ]},
    ]


def _sub_perf():
    return {
        "aicompute": {"1D": -3.1, "1W": -6.32},
        "aimodels": {"1D": 2.05},
        "fintechpayments": {"1D": 3.75, "1W": 1.1},
    }


def _mem_perf():
    return {
        "NVDA": {"1D": -1.64}, "AMD": {"1D": -2.06}, "MSFT": {"1D": 5.71},
        "GOOGL": {"1D": -1.84}, "META": {"1D": 0.4},
        "V": {"1D": 0.9}, "MA": {"1D": 1.2},
    }


def test_contract_shape():
    p = th.build_themes_heatmap(_tree(), _sub_perf(), _mem_perf(), asof="2026-06-28")
    assert p["map_type"] == "themes"
    assert p["size_basis"] == "count"
    assert p["default_tf"] == "1D"
    # eight daily-group timeframes, all available
    assert [tf["key"] for tf in p["timeframes"]] == ["1D", "1W", "MTD", "1M", "3M", "6M", "YTD", "1Y"]
    assert all(tf["available"] for tf in p["timeframes"])
    # sectors = themes, in tree order, bilingual
    assert [s["key"] for s in p["sectors"]] == ["Artificial Intelligence", "FinTech"]
    assert p["sectors"][0]["zh"] == "人工智能"
    assert p["n_tiles"] == 3
    assert p["n_members"] == 7


def test_tile_is_subsector_with_members():
    p = th.build_themes_heatmap(_tree(), _sub_perf(), _mem_perf())
    compute = next(t for t in p["tiles"] if t["t"] == "aicompute")
    assert compute["name"] == "Compute"
    assert compute["sector"] == "Artificial Intelligence"       # theme is the group
    assert compute["desc"] == "Compute & Acceleration"
    assert compute["size"] == 3                                  # member count
    assert compute["perf"]["1D"] == -3.1                         # subsector colour
    assert compute["perf"]["1W"] == -6.32
    mem = {m["t"]: m["perf"] for m in compute["members"]}
    assert mem["NVDA"]["1D"] == -1.64 and mem["MSFT"]["1D"] == 5.71  # member rows


def test_missing_perf_is_dropped_not_nulled():
    # subsector with no perf entry, member with no perf entry
    tree = [{"theme": "X", "key": "X", "subsectors": [
        {"key": "xsub", "name": "Sub", "description": "", "members": ["AAA", "BBB"]},
    ]}]
    p = th.build_themes_heatmap(tree, {"xsub": {}}, {"AAA": {"1D": 1.0}})
    tile = p["tiles"][0]
    assert tile["perf"] == {}                                    # no perf → empty, not None
    rows = {m["t"]: m["perf"] for m in tile["members"]}
    assert rows["AAA"] == {"1D": 1.0}
    assert rows["BBB"] == {}                                     # uncovered member still listed
    assert tile["size"] == 2                                     # floors at member count
    # unknown theme falls back to its own name for the zh label
    assert p["sectors"][0]["zh"] == "X"


def test_empty_inputs():
    p = th.build_themes_heatmap([], {}, {})
    assert p["n_tiles"] == 0 and p["sectors"] == [] and p["tiles"] == []
    assert p["map_type"] == "themes"
