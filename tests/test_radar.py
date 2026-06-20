"""Divergence Radar kernel tests (hermetic — synthetic obligations + baskets payload)."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from engine import radar


def _monthly(complete_baseline: float, recent: float, n_complete: int = 15):
    """A monthly series: (n_complete-3) baseline months then 3 `recent` months,
    plus radar.LAG_MONTHS trailing 'incomplete' months the engine should drop."""
    vals = [complete_baseline] * (n_complete - 3) + [recent] * 3
    vals += [complete_baseline] * radar.LAG_MONTHS
    idx = pd.date_range(end="2026-05-01", periods=len(vals), freq="MS")
    return pd.Series(vals, index=idx)


def _obligations():
    M = 1e6
    series = {
        # defense: spend ACCELERATING (10 -> 50)
        "LMT": _monthly(5 * M, 25 * M), "NOC": _monthly(5 * M, 25 * M),
        # nuclear: spend COOLING (50 -> 10)
        "BWXT": _monthly(25 * M, 5 * M), "OKLO": _monthly(25 * M, 5 * M),
        # space: spend ACCELERATING (10 -> 50)
        "RKLB": _monthly(5 * M, 25 * M), "IRDM": _monthly(5 * M, 25 * M),
        # uranium: FLAT (20 -> 20)
        "LEU": _monthly(10 * M, 10 * M), "UUUU": _monthly(10 * M, 10 * M),
    }
    return pd.DataFrame(series).sort_index()


def _payload():
    def basket(bid, name, members, rel60):
        return {
            "id": bid, "name": name, "name_zh": name, "category": "x",
            "members": [{"symbol": s} for s in members],
            "perf": {"60d": {"ret": rel60, "rel": rel60}},
        }
    return {
        "as_of": "2026-06-19",
        "baskets": [
            basket("defense", "Defense", ["LMT", "NOC"], -0.10),        # money up, price weak
            basket("nuclear_power", "Nuclear", ["BWXT", "OKLO"], 0.20),  # money down, price strong
            basket("space_economy", "Space", ["RKLB", "IRDM"], 0.18),    # money up, price strong
            basket("uranium_miners", "Uranium", ["LEU", "UUUU"], 0.02),  # flat money
        ],
    }


def _states(res):
    return {f["basket"]: f["state"] for f in res["flags"]}


def test_2x2_states():
    res = radar.compute_radar(_payload(), obligations=_obligations())
    assert res is not None
    st = _states(res)
    assert st["defense"] == "POSITIVE_DIVERGENCE"
    assert st["nuclear_power"] == "NEGATIVE_DIVERGENCE"
    assert st["space_economy"] == "CONFIRMED_UP"
    assert st["uranium_miners"] == "QUIET"


def test_off_diagonal_sorted_first():
    res = radar.compute_radar(_payload(), obligations=_obligations())
    states = [f["state"] for f in res["flags"]]
    # both DIVERGENCE flags must precede the CONFIRMED/QUIET ones
    last_div = max(i for i, s in enumerate(states) if s.endswith("DIVERGENCE"))
    first_non = min(i for i, s in enumerate(states) if not s.endswith("DIVERGENCE"))
    assert last_div < first_non
    assert res["coverage"]["divergences"] == 2


def test_accel_and_dollars_reported():
    res = radar.compute_radar(_payload(), obligations=_obligations())
    d = next(f for f in res["flags"] if f["basket"] == "defense")
    assert d["observable"]["accel"] > radar.ACCEL_UP
    assert d["observable"]["recent_3m_usd"] > d["observable"]["base_3m_usd"]
    assert d["observable"]["n_covered"] == 2
    n = next(f for f in res["flags"] if f["basket"] == "nuclear_power")
    assert n["observable"]["accel"] < radar.ACCEL_DOWN


def test_positive_divergence_emits_falsifiable_hypothesis():
    res = radar.compute_radar(_payload(), obligations=_obligations())
    hyps = {h["subject"]: h for h in res["hypotheses"]}
    assert set(hyps) == {"defense"}  # only the POSITIVE_DIVERGENCE theme
    h = hyps["defense"]
    assert h["horizon_d"] == radar.HORIZON_D
    assert h["falsifier"]["check"]["kind"] in ("rel_return", "soft")
    assert h["falsifier"]["check"].get("vs", "SPY") == "SPY"


def test_coverage_floor_excludes_thin_themes():
    payload = _payload()
    payload["baskets"].append({
        "id": "lonely", "name": "Lonely", "category": "x",
        "members": [{"symbol": "LMT"}],  # only 1 covered member < MIN_COVERED
        "perf": {"60d": {"rel": 0.5}},
    })
    res = radar.compute_radar(payload, obligations=_obligations())
    assert "lonely" not in _states(res)


def test_min_base_dollars_floor():
    M = 1e6
    obl = pd.DataFrame({
        "LMT": _monthly(0.1 * M, 0.5 * M), "NOC": _monthly(0.1 * M, 0.5 * M),
    }).sort_index()
    payload = {"as_of": "2026-06-19", "baskets": [
        {"id": "defense", "name": "Defense", "members": [{"symbol": "LMT"}, {"symbol": "NOC"}],
         "perf": {"60d": {"rel": -0.1}}}]}
    # 12m baseline well under MIN_BASE_USD -> excluded
    assert radar.compute_radar(payload, obligations=obl) is None


def test_degraded_returns_none():
    assert radar.compute_radar(None, obligations=_obligations()) is None
    assert radar.compute_radar(_payload(), obligations=pd.DataFrame()) is None
    assert radar.compute_radar({"baskets": []}, obligations=_obligations()) is None


def test_robust_z_orders_and_is_finite():
    z = radar._robust_z([1.0, 2.0, 3.0, 4.0, 100.0])
    assert all(abs(v) < 1e6 for v in z)
    assert z[-1] == max(z)  # the outlier is the most positive
    assert radar._robust_z([5.0]) == [0.0]  # no spread
    assert radar._robust_z([2.0, 2.0, 2.0]) == [0.0, 0.0, 0.0]


def test_append_ledger_idempotent(tmp_path):
    res = radar.compute_radar(_payload(), obligations=_obligations())
    (tmp_path / "data").mkdir()
    n1 = radar.append_ledger(res, root=tmp_path)
    n2 = radar.append_ledger(res, root=tmp_path)  # same ids -> no dupes
    assert n1 == len(res["hypotheses"]) >= 1
    assert n2 == 0
    lines = (tmp_path / "data" / "radar" / "theses.jsonl").read_text().splitlines()
    assert len(lines) == n1
    assert all(json.loads(ln)["id"] for ln in lines)


def test_bilingual_notes_present():
    res = radar.compute_radar(_payload(), obligations=_obligations())
    for f in res["flags"]:
        assert f["note"] and f["note_zh"]
        assert f["note"] != f["note_zh"]  # actually translated, not echoed
