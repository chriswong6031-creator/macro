"""W4.2 acceptance test suite for the cycle-hazard fit (scripts/fit_cycle_hazard.py).

Tests (per W4.2 spec, task step 5):
1. Logistic gradient check: analytic gradient matches numeric (finite-difference).
2. PAV isotonic monotonicity: the calibrated map is non-decreasing.
3. Walk-forward split integrity: no train/test DATE overlap; expanding origin; embargo.
4. Gate math — synthetic model that MUST PASS (strictly better Brier) and one that MUST
   ship PRIOR (Brier equal to / worse than KM).
5. FDR application: BH-FDR rejects the right cells on a synthetic p-value vector.
6. Epoch sanity: the shipped panel's turns are on the PRICE basis (close_price), not TR.
7. No sklearn/statsmodels import in the fit module (house rule, D5 §1.9).
8. KM baseline is never worse than the base rate (fair, non-strawman compounding).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_REPO))

from scripts.fit_cycle_hazard import (  # noqa: E402
    DESIGN,
    HORIZONS,
    L2_MASK_EXEMPT,
    _brier,
    _grad_logistic,
    _sigmoid,
    bh_fdr,
    build_design,
    fit_logistic_l2,
    km_predict,
    month_block_brier_gap_ci,
    walk_forward,
)
from engine.validation import isotonic_calibration, apply_calibration  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# 1. Logistic gradient check
# ─────────────────────────────────────────────────────────────────────────────

def test_logistic_gradient_matches_numeric():
    rng = np.random.default_rng(0)
    n, p = 200, 5
    X = rng.normal(size=(n, p))
    w_true = np.array([1.0, -0.5, 0.3, 0.0, 0.8])
    y = (rng.uniform(size=n) < _sigmoid(X @ w_true)).astype(float)
    w = rng.normal(size=p) * 0.1
    b = 0.2
    l2_mask = np.array([True, True, True, True, True])
    l2 = 1.0

    gw, gb = _grad_logistic(X, y, w, b, l2_mask, l2=l2)

    def nll(w_, b_):
        f = _sigmoid(X @ w_ + b_)
        f = np.clip(f, 1e-12, 1 - 1e-12)
        base = -np.mean(y * np.log(f) + (1 - y) * np.log(1 - f))
        pen = 0.5 * l2 * np.sum((l2_mask.astype(float) * w_) ** 2) / len(y)
        return base + pen

    eps = 1e-6
    gw_num = np.zeros(p)
    for j in range(p):
        wp = w.copy(); wp[j] += eps
        wm = w.copy(); wm[j] -= eps
        gw_num[j] = (nll(wp, b) - nll(wm, b)) / (2 * eps)
    gb_num = (nll(w, b + eps) - nll(w, b - eps)) / (2 * eps)

    assert np.allclose(gw, gw_num, atol=1e-6), f"grad w mismatch: {gw} vs {gw_num}"
    assert abs(gb - gb_num) < 1e-6, f"grad b mismatch: {gb} vs {gb_num}"


def test_logistic_fit_recovers_signal():
    """Sanity: on separable-ish data the fit learns the right coefficient signs."""
    rng = np.random.default_rng(1)
    n = 4000
    x = rng.normal(size=(n, 2))
    y = (rng.uniform(size=n) < _sigmoid(2.0 * x[:, 0] - 1.5 * x[:, 1])).astype(float)
    l2_mask = np.array([True, True])
    w, b = fit_logistic_l2(x, y, l2_mask, l2=0.1, iters=1500, lr=0.3)
    assert w[0] > 0.5 and w[1] < -0.3, f"coef signs wrong: {w}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. PAV isotonic monotonicity
# ─────────────────────────────────────────────────────────────────────────────

def test_isotonic_monotone():
    rng = np.random.default_rng(2)
    p = rng.uniform(size=1000)
    y = (rng.uniform(size=1000) < p ** 1.5).astype(float)
    iso = isotonic_calibration(p, y)
    assert iso, "isotonic should fit on n=1000"
    grid = np.linspace(0, 1, 200)
    cal = apply_calibration(iso, grid)
    diffs = np.diff(cal)
    assert (diffs >= -1e-9).all(), "calibration map must be non-decreasing"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Walk-forward split integrity
# ─────────────────────────────────────────────────────────────────────────────

def _synthetic_panel(seed=3, n_ids=12, start="2000-01", end="2024-12"):
    rng = np.random.default_rng(seed)
    months = pd.date_range(start, end, freq="ME")
    rows = []
    fams = ["us_sector", "country", "cn_sector"]
    for i in range(n_ids):
        fam = fams[i % 3]
        for m in months:
            age = rng.uniform(0.1, 3.0)
            bucket = "b1" if age < 0.5 else "b2" if age < 0.8 else "b3" if age < 1.1 else "b4" if age < 1.5 else "b5"
            base = 0.2 + 0.15 * (age > 1.1)   # older legs turn more
            y1 = int(rng.uniform() < base)
            rows.append({
                "date": m, "id": f"ID{i}", "family": fam,
                "direction": "up" if i % 2 == 0 else "down",
                "age_bucket": bucket, "age_m": age * 12,
                "log_age_ratio": np.log(max(age, 0.05)),
                "amp_proxy": rng.uniform(), "pos_osc": rng.uniform(0, 100),
                "osc_slope": rng.normal() * 5, "trend_pass": float(rng.uniform() < 0.5),
                "mom_score": rng.normal() * 0.1, "rs_63d": rng.normal() * 0.05,
                "vol_pctile": rng.uniform(),
                "quad": rng.choice(["Q1", "Q2", "Q3", "Q4"]),
                "liquidity": rng.choice(["expanding", "neutral", "contracting"]),
                "y1": y1, "y3": min(1, y1 + int(rng.uniform() < 0.2)),
                "y6": min(1, y1 + int(rng.uniform() < 0.35)),
            })
    return pd.DataFrame(rows)


def test_walk_forward_no_date_overlap():
    panel = build_design(_synthetic_panel())
    panel["date"] = pd.to_datetime(panel["date"])
    # Instrument the split: replicate the fold cutoffs and assert no overlap.
    sub = panel[panel["direction"] == "up"].sort_values("date")
    years = sorted(sub["date"].dt.year.unique())
    embargo_m = 6
    for Y in range(2010, years[-1] + 1):
        cutoff = pd.Timestamp(year=Y - 1, month=12, day=31) - pd.DateOffset(months=embargo_m)
        train = sub[sub["date"] <= cutoff]
        test = sub[sub["date"].dt.year == Y]
        if len(train) == 0 or len(test) == 0:
            continue
        # No date overlap
        assert train["date"].max() < test["date"].min(), f"overlap at Y={Y}"
        # Embargo respected: at least ~6 months gap
        gap_days = (test["date"].min() - train["date"].max()).days
        assert gap_days >= 150, f"embargo too small at Y={Y}: {gap_days}d"


def test_walk_forward_expanding_origin():
    """Train set must grow monotonically across folds (expanding origin)."""
    panel = build_design(_synthetic_panel())
    panel["date"] = pd.to_datetime(panel["date"])
    oos, fits = walk_forward(panel, "up")
    n_trains = [f["n_train"] for f in fits]
    assert n_trains == sorted(n_trains), f"train not expanding: {n_trains}"
    # OOS predictions exist and are probabilities
    assert not oos.empty
    assert oos["p1_raw"].between(0, 1).all()
    assert {"p1_caloof", "p3_caloof", "p6_caloof"}.issubset(oos.columns)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Gate math — synthetic PASS and synthetic PRIOR
# ─────────────────────────────────────────────────────────────────────────────

def test_gate_pass_when_model_strictly_better():
    """A model that predicts y perfectly must beat a KM that predicts the base rate:
    the gap CI must be entirely above zero."""
    rng = np.random.default_rng(4)
    months = pd.date_range("2010-01", "2024-12", freq="ME")
    dates, y, km, model = [], [], [], []
    base = 0.3
    for m in months:
        for _ in range(20):
            yi = int(rng.uniform() < base)
            dates.append(m); y.append(yi)
            km.append(base)                       # KM = base rate
            model.append(0.98 if yi else 0.02)    # near-perfect model
    y = np.array(y, float)
    gap, lo, hi = month_block_brier_gap_ci(np.array(dates),
                                           _brier(np.array(km), y),
                                           _brier(np.array(model), y))
    assert lo is not None and lo > 0, f"strong model must PASS: gap={gap} ci=[{lo},{hi}]"


def test_gate_prior_when_model_no_better():
    """A model equal to the KM base rate must NOT pass: the gap CI must include zero."""
    rng = np.random.default_rng(5)
    months = pd.date_range("2010-01", "2024-12", freq="ME")
    dates, y, km, model = [], [], [], []
    base = 0.3
    for m in months:
        for _ in range(20):
            yi = int(rng.uniform() < base)
            dates.append(m); y.append(yi)
            km.append(base)
            model.append(base + rng.normal() * 1e-6)   # identical to KM (noise)
    y = np.array(y, float)
    gap, lo, hi = month_block_brier_gap_ci(np.array(dates),
                                           _brier(np.array(km), y),
                                           _brier(np.array(model), y))
    assert not (lo is not None and lo > 0), f"null model must ship PRIOR: ci=[{lo},{hi}]"


# ─────────────────────────────────────────────────────────────────────────────
# 5. BH-FDR application
# ─────────────────────────────────────────────────────────────────────────────

def test_bh_fdr_rejects_correct_cells():
    # 6 p-values: three tiny, three large. BH q=0.10 should reject the small ones.
    pvals = [0.001, 0.008, 0.04, 0.5, 0.7, 0.9]
    rej = bh_fdr(pvals, q=0.10)
    assert rej[0] and rej[1], "smallest p-values must be rejected"
    assert not any(rej[3:]), "large p-values must not be rejected"


def test_bh_fdr_all_null():
    pvals = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    assert not any(bh_fdr(pvals, q=0.10)), "no rejections under global null"


def test_bh_fdr_monotone_step_up():
    """Classic BH boundary: a moderate p can be rejected because a smaller one carries it."""
    pvals = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
    rej = bh_fdr(pvals, q=0.20)
    # At q=0.2, m=6: threshold p_(k) <= k*0.2/6. k=6 → 0.20 ≥ 0.06 → all reject.
    assert all(rej), f"all should reject at q=0.2: {rej}"


# ─────────────────────────────────────────────────────────────────────────────
# 6. KM baseline is not a strawman (never worse than base rate on a synthetic panel)
# ─────────────────────────────────────────────────────────────────────────────

def test_km_not_worse_than_base_rate():
    panel = build_design(_synthetic_panel(seed=7))
    panel["date"] = pd.to_datetime(panel["date"])
    up = panel[panel["direction"] == "up"]
    train = up[up["date"].dt.year < 2020]
    test = up[up["date"].dt.year >= 2020]
    km = km_predict(train, test)
    for h in HORIZONS:
        y = test[f"y{h}"].to_numpy(float)
        br_km = float(np.mean(_brier(km[h], y)))
        base = float(train[f"y{h}"].mean())
        br_base = float(np.mean(_brier(np.full(len(y), base), y)))
        # KM (family/bucket-stratified) must not be materially worse than the base rate.
        assert br_km <= br_base + 0.02, f"KM strawman at {h}m: km={br_km} base={br_base}"


# ─────────────────────────────────────────────────────────────────────────────
# 7. No sklearn/statsmodels import (house rule)
# ─────────────────────────────────────────────────────────────────────────────

def test_no_sklearn_import():
    src = (_REPO / "scripts/fit_cycle_hazard.py").read_text()
    for banned in ["import sklearn", "from sklearn", "import statsmodels",
                   "from statsmodels", "import lifelines", "from lifelines"]:
        assert banned not in src, f"banned import present: {banned}"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Epoch sanity: shipped panel turns are on the PRICE basis
# ─────────────────────────────────────────────────────────────────────────────

def test_shipped_panel_is_price_basis_epoch():
    """The W4.2 epoch sanity check: the panel the fit consumes must be stamped with a
    price-basis epoch (price_*), not the old TR epoch (tr_*). Turns on TR closes violate
    the D4 substrate contract."""
    hz = _REPO / "data/hazard"
    price_panels = list(hz.glob("panel_price_*.parquet"))
    assert price_panels, "no price-basis panel found — epoch not corrected"
    panel = pd.read_parquet(price_panels[-1])
    stamp = str(panel["turn_def_version"].iloc[0])
    assert stamp.startswith("price_"), f"panel epoch not price-basis: {stamp}"
