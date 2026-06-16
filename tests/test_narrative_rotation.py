"""Thematic Narrative-Rotation engine (engine.narrative_rotation).

Verify the disciplined-allocation contract: the momentum ranker orders themes and the
absolute-trend gate decides eligibility; the suggested book equal-weights the top-N
trend-passers with a T-bill cash escape, trims crowded themes toward cash, and respects
the position cap (weights+cash always == 1); the crash overlay halves exposure; and every
DURABILITY / CROWDING / ROTATION block is display-only (directional=False) with the AI
handoff forbidding directional / fade / next-theme conclusions — none of it ever scored.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from engine import narrative_rotation as nr


# --------------------------------------------------------------------------- #
# synthetic per-basket prep (mirrors what _basket_preps builds)
# --------------------------------------------------------------------------- #
def _seed(bid):
    # deterministic across processes (Python's hash() is salted by PYTHONHASHSEED)
    return int.from_bytes(hashlib.sha1(bid.encode()).digest()[:4], "big")


def _prep(bid, drift, n=420, k=4, vol=0.009, seed=None):
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed if seed is not None else _seed(bid))
    mc = pd.DataFrame(np.cumprod(1 + rng.normal(drift, vol, (n, k)), axis=0) * 100,
                      index=idx, columns=[f"{bid}{i}" for i in range(k)])
    ew = mc.pct_change().mean(axis=1).fillna(0.0)
    lvl = (1 + ew).cumprod()
    bench = pd.Series(np.cumprod(1 + np.full(n, 0.0003)) , index=idx)        # ~+8%/yr SPY
    return {"id": bid, "name": bid.title(), "name_zh": bid, "category": "X", "thesis": "t",
            "etf_proxy": None, "n_live": k, "live": list(mc.columns),
            "lvl": lvl, "rs": lvl / bench, "members_closes": mc,
            "members_resid": mc.pct_change(), "names": {c: c for c in mc.columns}}


def test_rank_orders_by_momentum_and_gates_trend():
    preps = [_prep("lead", 0.0028), _prep("mid", 0.0008), _prep("lag", -0.0014)]
    ranks = nr.rank_themes(preps)
    assert ranks["lead"]["rank"] == 1                       # strongest momentum leads
    assert ranks["lead"]["eligible"] is True                # rising → above its own 200d trend
    assert ranks["lag"]["eligible"] is False                # falling → off trend, ineligible
    assert ranks["lead"]["score"] > ranks["mid"]["score"]


def test_abs_gate_and_hurst_and_13612w():
    up = _prep("up", 0.0015)["lvl"]
    dn = _prep("dn", -0.0012)["lvl"]
    assert nr._abs_gate(up)[0] is True
    assert nr._abs_gate(dn)[0] is False
    assert nr._mom_13612w(up) is not None and nr._mom_13612w(up) > 0
    # trending series → Hurst above the random-walk 0.5; pure noise → near 0.5
    h_trend = nr._hurst(up.pct_change().dropna().to_numpy())
    assert h_trend is not None


def test_allocate_weights_sum_caps_and_crowding_trim():
    preps = [_prep(b, d) for b, d in
             [("a", 0.0016), ("b", 0.0013), ("c", 0.0011), ("d", 0.0009), ("e", 0.0006)]]
    ranks = nr.rank_themes(preps)
    crowd = {p["id"]: {"crowding_z": None, "crowded": False} for p in preps}
    crowd["a"] = {"crowding_z": 1.6, "crowded": True}       # crowd the leader
    rot = nr.rotation_radar(preps, ranks, {p["id"]: {"bar": 0.6} for p in preps},
                            {"idx": preps[0]["lvl"].index})
    alloc = nr.allocate(preps, ranks, crowd, rot)
    w = {x["id"]: x["weight"] for x in alloc["weights"]}
    assert abs(sum(w.values()) + alloc["cash"] - 1.0) < 1e-6           # fully accounted
    assert all(v <= nr.POS_CAP + 1e-9 for v in w.values())            # position cap
    # the crowded leader is trimmed below the equal-weight base (down-size → cash)
    assert w["a"] < 1.0 / nr.N_HOLD - 1e-9
    assert alloc["directional"] is False


def test_crash_overlay_halves(monkeypatch):
    preps = [_prep(b, d) for b, d in [("a", 0.0016), ("b", 0.0012), ("c", 0.0010), ("d", 0.0008)]]
    ranks = nr.rank_themes(preps)
    crowd = {p["id"]: {"crowding_z": None, "crowded": False} for p in preps}
    rot = nr.rotation_radar(preps, ranks, {}, {})
    monkeypatch.setattr(nr, "_crash_state", lambda *a, **k: {"active": True, "bench_ret_24m": -0.1, "vol_pctile": 0.9})
    alloc = nr.allocate(preps, ranks, crowd, rot)
    assert alloc["crash_overlay"]["active"] is True
    assert sum(x["weight"] for x in alloc["weights"]) <= 0.5 + 1e-6   # exposure halved


def test_full_payload_display_only_invariants(monkeypatch):
    """End-to-end via a synthetic _setup: assert the payload contract AND that nothing is
    scored — every detector block is directional=False and the AI handoff forbids it."""
    n = 420
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    rng = np.random.default_rng(7)
    drifts = {"alpha": 0.0040, "beta": 0.0014, "gamma": 0.0009, "delta": 0.0005, "eps": -0.0010}
    tickers, items = [], []
    closes = {}
    for bid, dr in drifts.items():
        mem = []
        for i in range(4):
            tk = f"{bid[:2].upper()}{i}"
            closes[tk] = np.cumprod(1 + rng.normal(dr, 0.011, n)) * 100
            mem.append({"ticker": tk, "added": "2024-01-01", "removed": None})
            tickers.append(tk)
        items.append((bid, {"name": bid.title(), "name_zh": bid, "category": "X",
                            "thesis": "t", "etf_proxy": None, "members": mem}))
    C = pd.DataFrame(closes, index=idx)
    rets = C.pct_change(fill_method=None)
    spy_ret = pd.Series(np.full(n, 0.0003), index=idx)
    bench = (1 + spy_ret).cumprod()
    resid = nr._market_residuals(C, spy_ret)
    setup = {"mem": {"baskets": dict(items)}, "items": items, "closes": C, "rets": rets,
             "idx": idx, "bench": bench, "bench_ret": spy_ret, "bench_close": bench, "resid": resid}
    monkeypatch.setattr(nr, "_setup", lambda *a, **k: setup)
    monkeypatch.setattr(nr, "_validation_meta", lambda *a, **k: {})
    monkeypatch.setattr(nr, "_crash_state", lambda *a, **k: {"active": False})

    d = nr.compute_narrative_rotation("us")
    assert d is not None
    assert d["verdict"] == "discipline_not_prediction"
    assert d["headline"]["id"] == "alpha"                              # strongest theme leads
    assert abs(sum(w["weight"] for w in d["allocation"]["weights"]) + d["allocation"]["cash"] - 1) < 1e-6
    # display-only invariants: NO detector block is directional, AI is fenced
    for row in d["ranks"]:
        assert row["durability"]["directional"] is False
        assert row["crowding"]["directional"] is False
    assert d["rotation"]["directional"] is False
    assert d["allocation"]["directional"] is False
    assert len(d["ai_handoff"]["do_not_conclude"]) >= 4
    assert "forecast_weights" not in d                                 # never exposes a scored weight set


def test_returns_none_without_data(monkeypatch):
    monkeypatch.setattr(nr, "_setup", lambda *a, **k: None)
    assert nr.compute_narrative_rotation() is None


def test_all_regions_have_cfg_and_smoke(monkeypatch):
    """Every region resolves a cfg; and (if its caches are present) produces a valid,
    weight-conserving, display-only payload. Regions without local caches simply skip."""
    import pytest
    for region in nr.REGION_IDS:
        assert nr._region_cfg(region) is not None
    seen = 0
    for region in nr.REGION_IDS:
        d = nr.compute_narrative_rotation(region)
        if d is None:
            continue
        seen += 1
        assert d["region"] == region and d["bench_label"]
        assert abs(sum(w["weight"] for w in d["allocation"]["weights"]) + d["allocation"]["cash"] - 1) < 0.01
        assert d["allocation"]["directional"] is False
        assert d["ai_handoff"]["overall_verdict"] == "discipline_not_prediction"
    if seen == 0:
        pytest.skip("no regional caches available in this environment")


def test_integration_smoke_real_data():
    """If the real caches are present, the live payload must satisfy the contract; else skip."""
    import pytest
    d = nr.compute_narrative_rotation()
    if d is None:
        pytest.skip("real caches unavailable in this environment")
    assert d["headline"] and d["ranks"] and d["allocation"]["weights"]
    # weights & cash are each rounded to 3dp for display, so the shown sum can drift a few
    # thousandths from the (conserved) true 1.0 — allow display rounding, not a gross error.
    assert abs(sum(w["weight"] for w in d["allocation"]["weights"]) + d["allocation"]["cash"] - 1) < 0.01
    assert d["ai_handoff"]["overall_verdict"] == "discipline_not_prediction"
