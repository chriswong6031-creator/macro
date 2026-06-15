"""Bonds & bond-health engine tests.

Synthetic where possible (the pillar primitives are deterministic); a real-data
integration cross-check skips if the store is empty. Locks in: the NY Fed probit
orientation, the near-term-forward-spread sign, the curve-move taxonomy, the
credit/MOVE bands, the cycle-clock mapping, health-score bounds, the no-look-ahead
property of the time series, and the alert debounce/idempotency.

Run: python -m tests.test_bonds
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import bonds as B  # noqa: E402
from engine import bonds_alerts as BA  # noqa: E402
from lib import config  # noqa: E402

CFG = config.load()["bonds"]


def _idx(n=600):
    return pd.date_range("2014-01-01", periods=n, freq="B")


# --- curve & growth ----------------------------------------------------------
def test_ny_fed_probit_orientation():
    """Inverted (negative) spread -> high recession prob; steep -> low."""
    idx = _idx(50)
    inv = pd.Series(-1.0, index=idx)
    steep = pd.Series(2.5, index=idx)
    p_inv = B.ny_fed_recession_prob(inv, CFG["curve"]).iloc[-1]
    p_steep = B.ny_fed_recession_prob(steep, CFG["curve"]).iloc[-1]
    assert 0 <= p_steep < 0.15 < p_inv <= 1, (p_steep, p_inv)
    assert p_inv > p_steep


def test_ntfs_sign():
    """A front end that prices CUTS (forward 3m below spot) -> negative NTFS; an
    upward-sloping front end -> positive NTFS."""
    idx = _idx(30)
    f_cut = pd.DataFrame({"us3m": 5.0, "us1y": 4.5, "us2y": 4.0}, index=idx)   # falling -> cuts priced
    f_hike = pd.DataFrame({"us3m": 2.0, "us1y": 2.5, "us2y": 3.0}, index=idx)  # rising -> normal/steep
    assert B.near_term_forward_spread(f_cut).iloc[-1] < 0
    assert B.near_term_forward_spread(f_hike).iloc[-1] > 0
    # missing node -> None (degrade gracefully)
    assert B.near_term_forward_spread(pd.DataFrame({"us3m": [1.0]}, index=idx[:1])) is None


def test_curve_move_taxonomy():
    """Rising long + steepening -> bear_steepener; falling yields + steepening -> bull_steepener."""
    idx = _idx(60)
    base = np.linspace(0, 1, 60)
    # bear steepener: 10y rises faster than 2y
    f_bs = pd.DataFrame({"us2y": 2.0 + 0.1 * base, "us10y": 2.0 + 0.6 * base}, index=idx)
    key, _ = B.curve_move_taxonomy(f_bs, 21)
    assert key == "bear_steepener", key
    # bull steepener: both fall, 2y faster (slope widens), 10y down
    f_bull = pd.DataFrame({"us2y": 3.0 - 0.6 * base, "us10y": 3.0 - 0.1 * base}, index=idx)
    key2, _ = B.curve_move_taxonomy(f_bull, 21)
    assert key2 == "bull_steepener", key2


def test_uninversion_flag():
    """The alarm is a ~21-day transient that fires just AFTER the curve dis-inverts
    following a recent inversion — not on a steady positive curve, and not months
    later (by then it is history, not an alarm)."""
    idx = _idx(215)
    # inverted for 200d then a FRESH dis-inversion (positive for 15d)
    spread = pd.Series(np.r_[np.full(200, -0.5), np.full(15, 0.4)], index=idx)
    last, flag = B.uninversion(spread, 252)
    assert last is True                  # end is within ~21d of the last inversion
    assert flag.iloc[205]                # shortly after the cross
    # ...but a dis-inversion 100 days ago is no longer an active alarm
    idx2 = _idx(300)
    old = pd.Series(np.r_[np.full(200, -0.5), np.full(100, 0.4)], index=idx2)
    last_old, _ = B.uninversion(old, 252)
    assert last_old is False
    # steady positive -> never fires
    last2, _ = B.uninversion(pd.Series(1.5, index=idx2), 252)
    assert last2 is False


# --- credit / rates-vol bands ------------------------------------------------
def test_hy_band_thresholds():
    c = CFG["credit"]
    assert B._hy_band(2.0, c) == "tight"
    assert B._hy_band(4.0, c) == "normal"
    assert B._hy_band(6.0, c) == "elevated"
    assert B._hy_band(9.0, c) == "distress"
    assert B._hy_band(11.0, c) == "crisis"
    assert B._hy_band(None, c) is None


def test_move_band_thresholds():
    r = CFG["rates_vol"]
    assert B._move_band(60, r) == "calm"
    assert B._move_band(100, r) == "normal"
    assert B._move_band(130, r) == "elevated"
    assert B._move_band(180, r) == "crisis"


def test_stress_maps_monotone():
    """Stress maps are monotone non-decreasing in the underlying risk and bounded 0..100."""
    for fn, xs in ((B._hy_stress, [1, 3, 6, 9, 12]), (B._move_stress, [40, 90, 130, 160, 220])):
        ys = [fn(x) for x in xs]
        assert all(0 <= y <= 100 for y in ys)
        assert ys == sorted(ys), (fn.__name__, ys)


# --- cycle clock -------------------------------------------------------------
def test_cycle_phase_mapping():
    cyc = CFG["cycle"]
    # wide + widening credit -> recession; wide + tightening -> early recovery
    assert B._cycle_phase(0.5, 0.9, "widening", cyc) == "recession"
    assert B._cycle_phase(1.5, 0.9, "tightening", cyc) == "early"
    # tight credit + steep curve -> mid; tight + flat/inverted -> late
    assert B._cycle_phase(2.0, 0.1, "tightening", cyc) == "mid"
    assert B._cycle_phase(0.3, 0.1, "tightening", cyc) == "late"
    assert B._cycle_phase(None, 0.1, "tightening", cyc) is None


# --- health composite + frame ------------------------------------------------
def _synthetic_frame(n=500, seed=0):
    """Minimal frame with the columns bonds_frame + conditions need, as random
    walks, so the engine runs end-to-end without the real store."""
    rng = np.random.default_rng(seed)
    idx = _idx(n)

    def rw(start, vol):
        return pd.Series(start + np.cumsum(rng.normal(0, vol, n)), index=idx)

    f = pd.DataFrame(index=idx)
    f["us3m"] = rw(2.0, 0.02).clip(0.05)
    f["us1y"] = f["us3m"] + 0.2
    f["us2y"] = f["us3m"] + 0.3
    f["us10y"] = f["us3m"] + 0.8
    f["spread_2s10s"] = f["us10y"] - f["us2y"]
    f["spread_10y3m"] = f["us10y"] - f["us3m"]
    f["term_premium_10y"] = rw(0.3, 0.01)
    f["curve_tp_adj"] = f["spread_2s10s"] + f["term_premium_10y"]
    f["us10y_real"] = rw(1.5, 0.02)
    f["us5y_real"] = rw(1.2, 0.02)
    f["breakeven_10y"] = rw(2.3, 0.01)
    f["breakeven_5y"] = rw(2.2, 0.01)
    f["breakeven_5y5y"] = rw(2.3, 0.01)
    f["hy_oas"] = rw(4.0, 0.05).clip(1.5)
    f["ig_oas"] = rw(1.2, 0.02).clip(0.4)
    f["ebp"] = rw(0.0, 0.02)
    f["ebp_recession_prob"] = rw(0.1, 0.005).clip(0, 1)
    f["move"] = rw(90, 1.5).clip(40)
    f["vix"] = rw(18, 0.5).clip(9)
    f["nfci"] = rw(-0.3, 0.02)
    f["sahm"] = pd.Series(0.1, index=idx)
    f["recession_prob"] = pd.Series(3.0, index=idx)
    f["SPY"] = np.exp(rw(np.log(300), 0.01))
    return f


def test_health_score_bounds_and_orientation():
    f = _synthetic_frame()
    fr = B.bonds_frame(f)
    hs = fr["health_score"].dropna()
    assert ((hs >= 0) & (hs <= 100)).all()
    # all-calm inputs -> healthy (>50); a credit blowout -> lower health
    f2 = _synthetic_frame()
    f2.loc[f2.index[-60:], "hy_oas"] = 12.0     # crisis-level credit at the end
    f2.loc[f2.index[-60:], "move"] = 180.0      # crisis rates vol
    fr2 = B.bonds_frame(f2)
    assert fr2["health_score"].iloc[-1] < fr["health_score"].iloc[-1]


def test_bonds_frame_no_lookahead():
    """Truncating the input must not change earlier outputs (causal-only ops)."""
    f = _synthetic_frame(n=520, seed=3)
    full = B.bonds_frame(f)
    cut = B.bonds_frame(f.iloc[:400])
    for col in ["nyfed_prob", "ntfs", "hy_pctile", "move_pctile", "health_score"]:
        if col not in full or col not in cut:
            continue
        a = full[col].iloc[:400].dropna()
        b = cut[col].reindex(a.index).dropna()
        common = a.index.intersection(b.index)[-50:]
        assert np.allclose(a.loc[common], b.loc[common], rtol=1e-6, atol=1e-6, equal_nan=True), col


def test_snapshot_structure_and_contract():
    f = _synthetic_frame()
    snap = B.bonds_snapshot(f)
    for k in ["health_score", "health_label", "cycle_phase", "verdict_en", "verdict_zh",
              "pillars", "alarms", "drivers_for"]:
        assert k in snap, k
    for p in ["curve", "credit", "real_inflation", "stress", "cross_asset", "sovereign"]:
        assert p in snap["pillars"], p
    for d in ["forex", "commodities", "bitcoin", "equities"]:
        assert d in snap["drivers_for"], d
    assert isinstance(snap["alarms"], list)
    assert snap["verdict_zh"] and snap["verdict_zh"] != snap["verdict_en"]


def test_china_hk_snapshot_contract_real_data():
    fr = B.china_hk_bond_frame()
    if fr.empty:
        print("SKIP no China/HK bond proxy data")
        return
    snap = B.china_hk_bond_snapshot(fr)
    assert snap["market"] == "china_hk"
    assert snap["health_label"] in {"healthy", "mixed", "stressed", None}
    if snap["health_score"] is not None:
        assert 0 <= snap["health_score"] <= 100
    for p in ["rates", "credit_liquidity", "market_health", "fx_funding"]:
        assert p in snap["pillars"], p
    assert set(snap["stress_legs"]).intersection({"curve", "credit_impulse", "breadth", "fx", "hk_funding", "hk_vol"})
    assert snap["verdict_en"] and snap["verdict_zh"]


# --- alerts ------------------------------------------------------------------
def test_alerts_debounce_and_idempotent():
    """Debounce kills the daily whipsaw; rebuilding is idempotent (same ids)."""
    f = _synthetic_frame(n=600, seed=5)
    fr = B.bonds_frame(f)
    ev1 = BA.compute_all_events(fr)
    ev2 = BA.compute_all_events(fr)
    assert {e["id"] for e in ev1} == {e["id"] for e in ev2}      # idempotent
    # a short (<5 bar) whipsaw run in the HY band must NOT spawn its own event
    raw = pd.Series(["tight"] * 100 + ["normal"] * 2 + ["tight"] * 100,
                    index=_idx(202))
    deb = BA._debounce(raw, 5)
    assert (deb == "tight").all(), "a 2-bar interior blip should be absorbed"
    # ...but the CURRENT (last) run is NEVER absorbed, even if short — a fresh genuine
    # flip (e.g. a curve un-inversion) must surface immediately, not be hidden for min_days.
    raw2 = pd.Series(["bear_flattener"] * 100 + ["bull_steepener"] * 2, index=_idx(102))
    deb2 = BA._debounce(raw2, 21)
    assert deb2.iloc[-1] == "bull_steepener", "the latest genuine transition must be preserved"


def test_real_data_smoke():
    """End-to-end on the real store; skips cleanly if data is absent."""
    try:
        from engine import inputs
        f = inputs.build_features()
    except Exception as e:  # noqa: BLE001 — no store in CI-less env
        print(f"  (skip real-data smoke: {e})")
        return
    fr = B.bonds_frame(f)
    snap = B.bonds_snapshot(f, fr)
    assert snap["as_of"]
    assert snap["health_score"] is None or 0 <= snap["health_score"] <= 100
    assert snap["cycle_phase"] in (None, "recession", "early", "mid", "late")
    ev = BA.compute_all_events(fr)
    assert isinstance(ev, list)
    print(f"  real data: health={snap['health_score']} phase={snap['cycle_phase']} "
          f"events={len(ev)}")


if __name__ == "__main__":
    for fn in [test_ny_fed_probit_orientation, test_ntfs_sign, test_curve_move_taxonomy,
               test_uninversion_flag, test_hy_band_thresholds, test_move_band_thresholds,
               test_stress_maps_monotone, test_cycle_phase_mapping,
               test_health_score_bounds_and_orientation, test_bonds_frame_no_lookahead,
               test_snapshot_structure_and_contract, test_china_hk_snapshot_contract_real_data,
               test_alerts_debounce_and_idempotent,
               test_real_data_smoke]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all bonds engine tests passed")
