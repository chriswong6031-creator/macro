"""Country Cycle Intelligence engine tests — the international sibling of
test_sector_cycles. The turn/oscillator/phase/projection math is shared with
engine.sector_cycles (covered there); this verifies the country_cycles wrapper:
the universe wiring, region grouping, the intl meta contract, and JSON safety."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import country_cycles as cc  # noqa: E402


def test_universe_wiring():
    # every country maps to a known region; every aggregate to a bloc category
    assert set(cc.COUNTRIES) and set(cc.AGGREGATES)
    for tk, m in cc.COUNTRIES.items():
        assert m["region"] in cc.GROUP_ORDER, f"{tk} region {m['region']} not in GROUP_ORDER"
        assert m["dev"] in ("DM", "EM")
        assert m.get("flag") and m.get("name") and m.get("name_zh")
    for tk, m in cc.AGGREGATES.items():
        assert m["group"] in cc.GROUP_ZH
    # FXI carries the China line (longest large-cap tape), MCHI is intentionally unused
    assert "FXI" in cc.COUNTRIES and "MCHI" not in cc.COUNTRIES


def test_accents_distinct_per_region():
    for region in cc.GROUP_ORDER:
        n = sum(1 for m in cc.COUNTRIES.values() if m["region"] == region)
        accents = {cc._accent(region, k, n) for k in range(n)}
        assert len(accents) == n, f"{region}: accents collide ({n} members)"


def test_compute_smoke():
    try:
        data = cc.compute()
    except Exception as e:  # pragma: no cover - data env issue
        pytest.skip(f"yahoo_closes unavailable: {e}")
    if not data:
        pytest.skip("no country data in this environment")
    m = data["meta"]
    assert m["region"] == "intl"            # the JS branch key (US/China untouched)
    assert m["benchmark"] == "SPY"          # RS vs the US
    assert m["n_sectors"] >= 18             # most of the ~24 single-country ETFs present
    assert set(data["phases"]) == {"Trough", "Recovery", "Expansion", "Peak", "Downturn"}

    for s in data["sectors"]:
        assert s["kind"] == "sector"
        assert s["ticker"] in cc.COUNTRIES
        assert s["id"] == s["ticker"].lower()
        assert s["group"] in cc.GROUP_ORDER
        assert s["accent"] and s["name"]    # flag-prefixed display name
        assert s["price"] and s["osc"], f"{s['ticker']} missing series"
        assert s["now"]["phase"] in cc.sc.PHASES
        assert 0 <= s["now"]["pos"] <= 100
        kinds = [t["k"] for t in s["turns"]]
        for a, b in zip(kinds, kinds[1:]):
            assert a != b, f"{s['ticker']} turns not alternating"
        assert abs(s["price"][0]["v"] - 100.0) < 5.0   # rebased to ~100
        if s["proj"]:
            assert s["proj"]["nextTurn"] in ("peak", "trough")

    for b in data["baskets"]:
        assert b["kind"] == "basket"
        assert b["ticker"] in cc.AGGREGATES


def test_compute_json_serialisable():
    data = cc.compute()
    if not data:
        pytest.skip("no country data")
    js = json.dumps(data, ensure_ascii=False)   # no numpy / Timestamp leakage
    assert "NaN" not in js and "Infinity" not in js
