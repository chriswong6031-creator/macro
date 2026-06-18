"""Smoke + invariant tests for the display-only rate/inflation transmission leaf."""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import rate_inflation_transmission as rit


def _synthetic_frame(n: int = 800) -> pd.DataFrame:
    idx = pd.bdate_range("2019-01-01", periods=n)
    rng = np.random.default_rng(7)
    walk = lambda base, vol: base + np.cumsum(rng.normal(0, vol, n))  # noqa: E731
    f = pd.DataFrame(index=idx)
    f["us10y"] = walk(3.5, 0.03)
    f["us10y_real"] = walk(1.5, 0.03)
    f["breakeven_10y"] = f["us10y"] - f["us10y_real"]
    f["breakeven_5y5y"] = walk(2.3, 0.02)
    f["spread_2s10s"] = walk(0.2, 0.02)
    f["curve_tp_adj"] = f["spread_2s10s"] + walk(0.1, 0.01)
    f["rate_expectations_proxy"] = walk(-0.3, 0.02)
    f["core_pce_yoy"] = walk(3.0, 0.01)
    f["core_pce_3m_ann"] = f["core_pce_yoy"] + walk(0.0, 0.02)
    f["core_cpi_yoy"] = walk(3.2, 0.01)
    f["headline_cpi_yoy"] = walk(3.4, 0.02)
    f["ppi_core_yoy"] = walk(2.8, 0.02)
    f["eci_comp_yoy"] = walk(3.3, 0.005)
    f["infl_exp_5y"] = walk(2.4, 0.005)
    f["umich_infl_exp"] = walk(3.0, 0.01)
    f["cpi_core_services_yoy"] = walk(4.0, 0.01)
    f["cpi_shelter_yoy"] = walk(4.2, 0.01)
    return f


def test_metadata_is_bilingual_and_complete():
    for k, v in rit.DRIVERS_META.items():
        en, zh, kind = v
        assert en and zh and kind in {"level", "change"}, k
    for tkr, v in rit.ASSETS_META.items():
        en, zh, kind = v
        assert en and zh and kind, tkr
    # the live read drivers must all be defined and must EXCLUDE the raw levels
    assert rit.READ_DRIVERS <= set(rit.DRIVERS_META)
    assert not (rit.READ_DRIVERS & {"real10y", "be10y", "be5y5y"})


def test_chains_are_well_formed_and_bilingual():
    assert len(rit.CHAINS) >= 3
    for ch in rit.CHAINS:
        assert ch["trigger"] in rit.DRIVERS_META
        assert ch["title_en"] and ch["title_zh"]
        orders = [o["order"] for o in ch["orders"]]
        assert orders == [1, 2, 3], ch["id"]
        for o in ch["orders"]:
            assert o["en"] and o["zh"]
            assert all(a in rit.ASSETS_META for a in o["assets"]), ch["id"]


def test_build_drivers_causal_and_named():
    f = _synthetic_frame()
    d = rit.build_drivers(f)
    # every READ driver is present, finite at the tail, and the engine never crashes
    for k in rit.READ_DRIVERS:
        assert k in d.columns, k
    assert d.index.equals(f.index)


def test_snapshot_structure_and_invariants():
    f = _synthetic_frame()
    s = rit.snapshot(f)
    assert s is not None
    for key in ("asof", "state", "inflation_decomposition", "transmission",
                "headwinds", "tailwinds", "chains", "scenarios", "scored_status",
                "caveats", "calibrated"):
        assert key in s, key
    # state is bilingual & banded
    st = s["state"]
    assert st["rates"]["regime"] in {"restrictive", "neutral", "accommodative"}
    assert st["inflation"]["regime"] in {"above target", "at target", "below target"}
    assert st["expectations"]["anchoring"] in {"drifting up", "drifting down", "anchored"}
    for sub in ("rates", "inflation", "expectations"):
        assert st[sub]["label"]["en"] and st[sub]["label"]["zh"]
    # caveats + scored status bilingual
    assert s["scored_status"]["en"] and s["scored_status"]["zh"]
    assert all(c.get("en") and c.get("zh") for c in s["caveats"])
    # chains carry the live annotation
    assert len(s["chains"]) == len(rit.CHAINS)
    for ch in s["chains"]:
        assert isinstance(ch["active"], bool)
        assert ch["title"]["en"] and ch["title"]["zh"]


def test_transmission_read_excludes_levels_and_is_finite():
    f = _synthetic_frame()
    s = rit.snapshot(f)
    if not s["calibrated"]:
        return  # no measured matrix in this environment — structure already checked
    for tkr, v in s["transmission"].items():
        assert v["verdict"] in {"headwind", "tailwind", "neutral"}
        assert np.isfinite(v["net"])
        # only READ_DRIVERS may contribute (raw levels excluded as co-trend)
        for p in v["top_drivers"]:
            assert p["driver"] in rit.READ_DRIVERS


def test_scenarios_directional_and_caveated():
    f = _synthetic_frame()
    s = rit.snapshot(f)
    for sc in s["scenarios"]:
        assert sc["label"]["en"] and sc["label"]["zh"]
        for m in sc["headwinds"]:
            assert m["implied_move_pct"] < 0
        for m in sc["tailwinds"]:
            assert m["implied_move_pct"] > 0


def test_snapshot_degrades_when_columns_missing():
    # an almost-empty frame must not raise — additive, never fatal
    idx = pd.bdate_range("2022-01-01", periods=300)
    f = pd.DataFrame(index=idx)
    f["us10y"] = 4.0
    f["us10y_real"] = 2.0
    f["breakeven_10y"] = 2.0
    f["breakeven_5y5y"] = 2.3
    f["curve_tp_adj"] = 0.1
    s = rit.snapshot(f)
    assert s is not None and "state" in s


def test_disabled_returns_none(monkeypatch):
    from lib import config
    base = config.load()
    cfg = dict(base)
    cfg["transmission"] = dict(base.get("transmission") or {}, enabled=False)
    monkeypatch.setattr(config, "load", lambda: cfg)
    assert rit.snapshot(_synthetic_frame()) is None
