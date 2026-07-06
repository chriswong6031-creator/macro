"""Smoke + invariant tests for the display-only yield-curve analytics leaf."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from engine import yield_curve as yc
from engine.bonds import _TAXONOMY


def _curve_frame(n: int = 700, seed: int = 7) -> pd.DataFrame:
    """A synthetic frame carrying the full Treasury curve + real / breakeven / TP nodes."""
    idx = pd.bdate_range("2018-01-01", periods=n)
    rng = np.random.default_rng(seed)
    walk = lambda base, vol: base + np.cumsum(rng.normal(0, vol, n))  # noqa: E731
    f = pd.DataFrame(index=idx)
    # an upward-sloping curve by construction (each tenor a small spread over the last)
    f["us3m"] = walk(4.2, 0.01)
    f["us6m"] = f["us3m"] + 0.05
    f["us1y"] = f["us3m"] + 0.10
    f["us2y"] = f["us3m"] + 0.15
    f["us3y"] = f["us3m"] + 0.22
    f["us5y"] = f["us3m"] + 0.30
    f["us7y"] = f["us3m"] + 0.40
    f["us10y"] = f["us3m"] + 0.55
    f["us30y"] = f["us3m"] + 0.80
    f["spread_2s10s"] = f["us10y"] - f["us2y"]
    f["spread_10y3m"] = f["us10y"] - f["us3m"]
    f["us10y_real"] = f["us10y"] - 2.3
    f["us5y_real"] = f["us5y"] - 2.3
    f["breakeven_10y"] = f["us10y"] - f["us10y_real"]
    f["breakeven_5y"] = walk(2.3, 0.005)
    f["breakeven_5y5y"] = walk(2.35, 0.004)
    f["term_premium_10y"] = walk(0.2, 0.006)
    f["curve_tp_adj"] = f["spread_2s10s"] + f["term_premium_10y"]
    return f


def _ramp_last(f: pd.DataFrame, col: str, total: float, days: int = 30) -> None:
    """Add a linear ramp of `total` over the final `days` rows of a column (in place)."""
    ramp = np.linspace(0, total, days)
    f.iloc[-days:, f.columns.get_loc(col)] += ramp


# --------------------------------------------------------------------------- #
def test_metadata_and_maps_bilingual_and_complete():
    # the regime play map must cover every taxonomy key, bilingual, valid tickers
    assert set(yc.REGIME_PLAY) == set(_TAXONOMY)
    for k, p in yc.REGIME_PLAY.items():
        assert p["fed_phase_en"] and p["fed_phase_zh"] and p["note_en"] and p["note_zh"], k
        assert p["favored"] and p["pressured"], k
    for etf, m in yc.SECTOR_RATE.items():
        assert m["mech_en"] and m["mech_zh"], etf
        assert m["slope"] in (-1, 0, 1) and m["dur"] in ("long", "short", "neutral"), etf


def test_snapshot_well_formed_and_serializable():
    f = _curve_frame()
    s = yc.snapshot(f)
    assert s is not None
    for key in ("shape", "slopes", "momentum", "regime", "recession", "forwards",
                "signals", "scored_status", "caveats"):
        assert key in s, key
    for fam in ("core_macro", "sector", "stock_factor", "market_tendency"):
        assert fam in s["signals"], fam
    # bilingual everywhere it claims to be
    assert s["scored_status"]["en"] and s["scored_status"]["zh"]
    assert all(c["en"] and c["zh"] for c in s["caveats"])
    # JSON-serializable (no numpy scalars leaking) — the contract is written to disk
    json.dumps(s)


def test_pca_decomposition_variance_and_orientation():
    f = _curve_frame()
    pca = yc.pca_decomposition(f)
    assert pca is not None
    keys = [fct["key"] for fct in pca["factors"]]
    assert keys == ["level", "slope", "curvature"]
    vars_ = [fct["var_explained"] for fct in pca["factors"]]
    # each fraction in [0,1], descending, and the first three span a high share
    assert all(0.0 <= v <= 1.0 for v in vars_)
    assert vars_ == sorted(vars_, reverse=True)
    assert 0.5 < pca["first3_var"] <= 1.0
    # the level factor's loadings should be all the same sign (a parallel factor)
    lev = pca["factors"][0]["loadings"]
    signs = {np.sign(v) for v in lev.values() if v != 0}
    assert len(signs) == 1


def test_slopes_and_momentum_shapes():
    f = _curve_frame()
    slp = yc.slopes(f)
    for k in ("2s10s", "3m10y", "5s30s", "real_5s10s", "tp_adj"):
        assert k in slp, k
        assert slp[k]["label"]["en"] and slp[k]["label"]["zh"]
        assert isinstance(slp[k]["inverted"], bool)
    mom = yc.momentum(f)
    assert mom["window_d"] == yc.MOM_WINDOW
    assert "real10y_speed_bp" in mom
    # the low-frequency trend-spread (Faria-Verona) read is present
    assert "trend_spread" in mom and "trend_spread_dir" in mom


def test_regime_classification_known_moves():
    # bear steepener: long end rises, curve steepens
    f = _curve_frame(seed=1)
    _ramp_last(f, "us10y", +0.5)
    f["spread_2s10s"] = f["us10y"] - f["us2y"]
    f["spread_10y3m"] = f["us10y"] - f["us3m"]
    assert yc.regime(f)["key"] == "bear_steepener"

    # bull flattener: long end falls, curve flattens
    g = _curve_frame(seed=2)
    _ramp_last(g, "us10y", -0.5)
    g["spread_2s10s"] = g["us10y"] - g["us2y"]
    assert yc.regime(g)["key"] == "bull_flattener"

    # bear flattener: front end rises faster than long → curve flattens, long end up
    h = _curve_frame(seed=3)
    _ramp_last(h, "us10y", +0.1)
    _ramp_last(h, "us2y", +0.5)
    h["spread_2s10s"] = h["us10y"] - h["us2y"]
    assert yc.regime(h)["key"] == "bear_flattener"


def test_recession_dashboard_flags():
    # an inverted NTFS + 10y-3m inversion should raise flags & lift the risk band
    f = _curve_frame(seed=5)
    # invert the front: push 1y/2y/3m well above 10y at the tail
    for col, bump in [("us3m", 1.5), ("us1y", 1.4), ("us2y", 1.3)]:
        _ramp_last(f, col, bump, days=60)
    f["spread_10y3m"] = f["us10y"] - f["us3m"]
    f["spread_2s10s"] = f["us10y"] - f["us2y"]
    rec = yc.recession(f)
    assert rec["ntfs"] is not None and rec["ntfs"] < 0          # NTFS inverted
    assert "ntfs" in rec["flags"]
    assert rec["n_flags"] >= 1 and rec["risk"] in ("watch", "elevated", "high")
    assert rec["lead_time_note"]["en"] and rec["lead_time_note"]["zh"]
    # the Wright policy-stance context is present and bilingual when funds is available
    f["fed_funds"] = 5.0
    rec2 = yc.recession(f)
    assert rec2["policy_stance"]["stance"] == "restrictive"
    assert rec2["policy_stance"]["note"]["en"] and rec2["policy_stance"]["note"]["zh"]


def test_forwards_upward_curve():
    f = _curve_frame()
    fwd = yc.forwards(f)
    # on an upward-sloping curve the implied forwards exist and are above the front yield
    assert fwd["f_1y1y"] is not None and fwd["f_5y5y"] is not None
    assert fwd["carry_10y_pct"] is not None
    # roll-down on an upward curve is a positive return contribution
    assert fwd["rolldown_10y_pct"] is not None and fwd["rolldown_10y_pct"] >= 0


def test_sector_and_factor_signal_structure():
    f = _curve_frame()
    s = yc.snapshot(f)
    sec = s["signals"]["sector"]
    assert sec and all(t["etf"] and t["tilt"] in ("tailwind", "headwind", "neutral")
                       and t["basis"] in ("measured", "theory") for t in sec)
    fac = s["signals"]["stock_factor"]
    assert fac["value_vs_growth"] in ("value", "growth", "neutral")
    assert fac["size"] in ("small", "large", "neutral")
    assert fac["duration_factor"] in ("headwind", "tailwind", "neutral")
    mt = s["signals"]["market_tendency"]
    assert mt["drawdown_risk"] in ("calm", "watch", "elevated")


def test_graceful_degradation_missing_nodes():
    # drop the long end + a real leg — the snapshot must still return (degraded), not crash
    f = _curve_frame()
    f = f.drop(columns=["us30y", "us7y", "us5y_real"])
    s = yc.snapshot(f)
    assert s is not None and "slopes" in s
    # missing the whole curve front/back anchor → None, never an exception
    g = f.drop(columns=["us10y"])
    assert yc.snapshot(g) is None


# --------------------------------------------------------------------------- #
# pca_health tests (R-ORTH PR-2)
# --------------------------------------------------------------------------- #

def _rich_curve_frame(n: int = 700, seed: int = 42) -> pd.DataFrame:
    """Curve fixture with genuine cross-sectional factor structure (level + slope +
    curvature factors each have independent noise), so PC2/PC3 carry measurable variance
    and pca_health sub-fields are non-degenerate. Used exclusively by pca_health tests."""
    idx = pd.bdate_range("2018-01-01", periods=n)
    rng = np.random.default_rng(seed)
    # three orthogonal factors driving yield changes
    level_shocks = rng.normal(0, 0.012, n)       # parallel shift
    slope_shocks = rng.normal(0, 0.005, n)       # short minus long
    curv_shocks = rng.normal(0, 0.002, n)        # belly vs wings
    maturities = np.array([0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 30.0])
    # loadings: level=1, slope~linear in mat, curvature~butterfly
    slope_loads = (maturities - maturities.mean()) / maturities.std()
    curv_loads = -(abs(slope_loads) - abs(slope_loads).mean())
    # build yield changes per tenor
    dy_matrix = (
        level_shocks[:, None] * np.ones(9)
        + slope_shocks[:, None] * slope_loads
        + curv_shocks[:, None] * curv_loads
    )
    # integrate to levels (start at upward-sloping curve)
    base = np.array([4.2, 4.25, 4.30, 4.35, 4.42, 4.50, 4.60, 4.75, 5.00])
    yields = base + np.cumsum(dy_matrix, axis=0)
    cols = ["us3m", "us6m", "us1y", "us2y", "us3y", "us5y", "us7y", "us10y", "us30y"]
    f = pd.DataFrame(yields, index=idx, columns=cols)
    f["spread_2s10s"] = f["us10y"] - f["us2y"]
    f["spread_10y3m"] = f["us10y"] - f["us3m"]
    f["us10y_real"] = f["us10y"] - 2.3
    f["us5y_real"] = f["us5y"] - 2.3
    f["breakeven_10y"] = f["us10y"] - f["us10y_real"]
    f["breakeven_5y"] = pd.Series(2.3 + np.cumsum(rng.normal(0, 0.005, n)), index=idx)
    f["term_premium_10y"] = pd.Series(0.2 + np.cumsum(rng.normal(0, 0.006, n)), index=idx)
    f["curve_tp_adj"] = f["spread_2s10s"] + f["term_premium_10y"]
    return f

_PCA_HEALTH_KEYS = {
    "eigenvalue_gaps", "effective_dimension_pr", "pc1_loading_turnover_vs_2y",
    "oos_null", "vol_match_multipliers", "curvature_stability_tag", "window_set",
}
_OOS_NULL_KEYS = {"observed", "null_median", "null_p90", "pctile_vs_null", "n_null_draws"}


def test_pca_health_present_and_key_set():
    """pca_health is present on a rich (multi-factor) 700-row fixture and passes structural checks."""
    f = _rich_curve_frame(n=700)
    pca = yc.pca_decomposition(f)
    assert pca is not None, "pca_decomposition returned None"
    assert "pca_health" in pca, "pca_health key missing"
    h = pca["pca_health"]
    assert h is not None, "pca_health is None on 700-row frame"
    assert set(h.keys()) == _PCA_HEALTH_KEYS, f"unexpected keys: {set(h.keys()) ^ _PCA_HEALTH_KEYS}"

    # eigenvalue_gaps: present keys, gaps > 0 where not None
    gaps = h["eigenvalue_gaps"]
    for gk in ("pc1_to_pc2", "pc2_to_pc3", "pc3_to_pc4"):
        assert gk in gaps
    for gk, gv in gaps.items():
        if gv is not None:
            assert gv > 0, f"gap {gk} should be > 0, got {gv}"

    # effective_dimension_pr in [1, n_tenors]
    n_tenors = len(pca["tenors"])
    efd = h["effective_dimension_pr"]
    assert efd is not None
    assert 1.0 <= efd <= n_tenors, f"effective_dimension_pr={efd} outside [1, {n_tenors}]"

    # oos_null present and pctile_vs_null in [0, 1]
    oos = h["oos_null"]
    assert oos is not None, "oos_null should be populated on 700-row frame"
    assert set(oos.keys()) == _OOS_NULL_KEYS
    assert 0.0 <= oos["pctile_vs_null"] <= 1.0
    assert oos["n_null_draws"] >= 200  # RUL-ORTH-8: >=200-draw within-window null

    # curvature_stability_tag
    tag = h["curvature_stability_tag"]
    assert tag in {"stable", "caution", "unstable", None}

    # vol_match_multipliers >= 1 where not None
    mults = h["vol_match_multipliers"]
    for mk in ("pc2", "pc3"):
        assert mk in mults
        if mults[mk] is not None:
            assert mults[mk] >= 1.0, f"vol_match_multiplier {mk}={mults[mk]} < 1"

    # window_set
    ws = h["window_set"]
    assert ws["compare_window_d"] == 504
    assert ws["oos_horizon_d"] == 21
    assert ws["full_window_d"] > 0


def test_pca_health_backward_compat():
    """The existing keys factors/first3_var/window_d/tenors are untouched by pca_health."""
    f = _rich_curve_frame(n=700)
    pca = yc.pca_decomposition(f)
    assert pca is not None
    # all original keys still present
    for k in ("factors", "first3_var", "window_d", "tenors"):
        assert k in pca, f"original key {k!r} missing after pca_health addition"
    # check the variance-and-orientation invariants from the original test
    keys = [fct["key"] for fct in pca["factors"]]
    assert keys == ["level", "slope", "curvature"]
    vars_ = [fct["var_explained"] for fct in pca["factors"]]
    assert all(0.0 <= v <= 1.0 for v in vars_)
    assert vars_ == sorted(vars_, reverse=True)
    assert 0.5 < pca["first3_var"] <= 1.0
    lev = pca["factors"][0]["loadings"]
    signs = {np.sign(v) for v in lev.values() if v != 0}
    assert len(signs) == 1


def test_pca_health_degradation_300_rows():
    """300-row frame: main PCA passes; pca_health present; oos_null and turnover may be
    None (insufficient history) but the call must never raise."""
    f = _curve_frame(n=300)
    pca = yc.pca_decomposition(f)
    assert pca is not None, "pca_decomposition should succeed on 300-row frame"
    h = pca["pca_health"]
    assert h is not None, "pca_health should not be None on 300-row frame"
    # turnover needs >= 525 rows; must be None here
    assert h["pc1_loading_turnover_vs_2y"] is None
    # oos_null is None here twice over: train=278 rows yields <200 strided null draws
    # (RUL-ORTH-8 floor), and _curve_frame's tenors are near-perfectly correlated so
    # the degenerate-std guard trips (projected PC2/PC3 variance ~ 0)
    assert h["oos_null"] is None

    # a frame too small for the main PCA returns None overall (not an exception)
    g = _curve_frame(n=100)
    result = yc.pca_decomposition(g)
    assert result is None


def test_pca_health_degenerate_frame_oos_null_none():
    """A rank-deficient curve (all tenors driven by one factor — the original _curve_frame)
    must yield oos_null=None via the degenerate-std guard even with ample history, and the
    pc3_to_pc4 gap must be None (denominator floor), never a spuriously huge 'stable' read."""
    f = _curve_frame(n=700)
    pca = yc.pca_decomposition(f)
    assert pca is not None
    h = pca["pca_health"]
    assert h is not None
    assert h["oos_null"] is None
    gap34 = h["eigenvalue_gaps"]["pc3_to_pc4"]
    assert gap34 is None or gap34 < 1e6, f"degenerate PC4 produced runaway gap {gap34}"
    if gap34 is None:
        assert h["curvature_stability_tag"] is None


def test_pca_health_json_serializable():
    """No numpy scalar leaks from pca_health; json.dumps must round-trip."""
    f = _rich_curve_frame(n=700)
    pca = yc.pca_decomposition(f)
    assert pca is not None
    # snapshot round-trip (pca_health is nested inside shape.pca)
    s = yc.snapshot(f)
    assert s is not None
    dumped = json.dumps(s)  # raises TypeError on numpy types
    reloaded = json.loads(dumped)
    # pca_health preserved through round-trip
    assert "pca_health" in reloaded["shape"]["pca"]
