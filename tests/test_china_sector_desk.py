"""China Sector Desk + Pathway engine tests.

Pure-function invariants (zigzag turn detection, Wilson CI, leak-free standardization,
composite construction) always run. The data-dependent snapshot / evidence-gate tests
skip cleanly when the china_sectors plane is absent (a bare checkout) and assert the
contract when it is present (CI commits the data).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from collectors.china_sectors import SW_L1
from engine import china_sector_index as csi
from engine import china_sector_pathway as pw
from engine import china_sector_pathway_backtest as bt

HAVE_DATA = csi.sw_close("801780") is not None


# --------------------------------------------------------------- pure functions ----

def test_zigzag_detects_major_top_then_bottom():
    idx = pd.date_range("2020-01-01", periods=240, freq="B")
    vals = np.concatenate([
        np.linspace(100, 200, 80),   # +100% up-leg  -> a top at 200
        np.linspace(200, 90, 80),    # -55% down-leg -> a bottom at 90
        np.linspace(90, 260, 80),    # up-leg (unconfirmed, no trailing reversal)
    ])
    turns = csi.zigzag_turns(pd.Series(vals, index=idx), pct=0.25)
    kinds = [t["kind"] for t in turns]
    assert kinds[:2] == ["top", "bottom"]
    assert abs(turns[0]["price"] - 200) < 1.0
    assert abs(turns[1]["price"] - 90) < 1.0
    # alternation invariant
    assert all(kinds[i] != kinds[i + 1] for i in range(len(kinds) - 1))


def test_zigzag_flat_series_no_turns():
    idx = pd.date_range("2020-01-01", periods=120, freq="B")
    s = pd.Series(100 + np.sin(np.arange(120) / 5) * 2, index=idx)  # <25% wiggle
    assert csi.zigzag_turns(s, pct=0.25) == []


def test_wilson_interval_bounds():
    lo, hi = pw._wilson(8, 10)
    assert 0.0 <= lo <= 0.8 <= hi <= 1.0
    lo0, hi0 = pw._wilson(0, 0)
    assert (lo0, hi0) == (0.0, 0.0)


def test_expanding_z_is_leak_free():
    s = pd.Series(np.arange(1, 101, dtype=float))
    full = pw._expanding_z(s, min_periods=12)
    # truncating the future must not change a past value (no look-ahead)
    trunc = pw._expanding_z(s.iloc[:60], min_periods=12)
    assert np.isclose(full.iloc[59], trunc.iloc[59], equal_nan=True)
    assert full.iloc[:11].isna().all()  # min_periods respected


def test_composite_index_lies_between_legs(monkeypatch):
    idx = pd.date_range("2020-01-01", periods=120, freq="B")
    a = pd.Series(100 * (1.002 ** np.arange(120)), index=idx)   # strong
    b = pd.Series(100 * (1.000 ** np.arange(120)), index=idx)   # flat
    monkeypatch.setattr(csi, "sw_close", lambda code: {"X": a, "Y": b}.get(code))
    comp = csi.composite_index(["X", "Y"])
    assert comp is not None and len(comp) > 0 and (comp > 0).all()
    # equal-weight composite return sits strictly between the two legs
    assert b.iloc[-1] / b.iloc[0] < comp.iloc[-1] / comp.iloc[0] < a.iloc[-1] / a.iloc[0]


def test_sw_universe_covers_every_gs_basket():
    for key, b in csi.GS_BASKETS.items():
        codes = b.get("sw_composite") or [b["sw"]]
        for c in codes:
            assert c in SW_L1, f"{key} references unknown Shenwan code {c}"


# ------------------------------------------------------------ data-dependent ----

@pytest.mark.skipif(not HAVE_DATA, reason="china_sectors data plane absent")
def test_desk_snapshot_contract():
    from engine.china_sector_desk import snapshot
    snap = snapshot()
    assert snap and snap["sectors"]
    assert len(snap["sectors"]) >= 12
    s = snap["sectors"][0]
    for k in ("name", "sw_code", "level", "position", "live_sym", "spark"):
        assert k in s
    assert 0 <= s["position"]["score"] <= 100
    assert {"leaders", "laggards", "washed_out", "euphoric"} <= set(snap["summary"])


@pytest.mark.skipif(not HAVE_DATA, reason="china_sectors data plane absent")
def test_pathway_snapshot_contract():
    snap = pw.snapshot()
    assert snap and len(snap["sectors"]) == 4
    for s in snap["sectors"]:
        assert s["bbg"].startswith("GSXAC")
        assert s["setup"]["tercile"] in ("low", "mid", "high")
        assert s["caveat_en"] and s["narrative_en"]
        for h, c in s["conditional"].items():
            assert 0.0 <= c["cond_rate"] <= 1.0
            assert c["ci_lo"] <= c["cond_rate"] <= c["ci_hi"]
            assert c["n"] >= 8


@pytest.mark.skipif(not HAVE_DATA, reason="china_sectors data plane absent")
def test_evidence_gate_signature_holds():
    rep = bt.run_gate()
    assert rep["passed"], f"signature gate failed: {rep}"
    # every HARD signature check must show bottoms below tops on the washout axis
    for c in rep["checks"]:
        if c["type"] == "signature":
            assert c["bottom_pctile"] < c["top_pctile"]
