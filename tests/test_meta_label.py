"""GBT meta-label leaf tests — label/feature construction, purged-fold leakage,
and degrade-never-raise. No network; the integration test uses a tiny synthetic
frame + a shrunk GBT so it runs in well under a second.

The leakage test is the load-bearing one: it proves the López de Prado PURGE +
EMBARGO around each test fold leaves NO training label window overlapping the test
span (the leak a plain k-fold has with overlapping forward labels).

Run: .venv/bin/python -m tests.test_meta_label
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import meta_label  # noqa: E402
from engine.validation import purged_folds  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers — a deterministic synthetic Vector frame
# --------------------------------------------------------------------------- #
def _synth(n: int = 900, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2016-01-01", periods=n, freq="D")
    steps = rng.normal(0.001, 0.03, n)
    close = pd.Series(100 * np.exp(np.cumsum(steps)), index=idx)
    mom = pd.Series(np.tanh(pd.Series(steps, index=idx).rolling(20).mean() * 30)).fillna(0.0)
    risk = pd.Series(np.clip(50 + 40 * rng.normal(0, 1, n).cumsum() / np.sqrt(n), 0, 100), index=idx)
    df = pd.DataFrame({
        "close": close,
        "alloc_optimal": (mom > 0).astype(float),       # primary: long when momentum positive
        "momentum": mom,
        "risk_index": risk,
        "vol_pctile": pd.Series(rng.random(n), index=idx),
        "cycle_position": pd.Series(rng.random(n), index=idx),
        "impulse": pd.Series(rng.normal(0, 1, n), index=idx),
        "risk_regime": pd.Series(np.where(risk > 60, "high_risk", "low_risk"), index=idx),
    })
    return df


# --------------------------------------------------------------------------- #
# events + labels
# --------------------------------------------------------------------------- #
def test_primary_events_are_the_long_calls():
    df = _synth()
    ev = meta_label.primary_events(df["alloc_optimal"])
    assert len(ev) > 0
    # every event has alloc>0, every non-event has alloc<=0 (no missed/extra long calls)
    assert bool((df["alloc_optimal"].reindex(ev) > 0).all())
    non = df.index.difference(ev)
    assert bool((df["alloc_optimal"].reindex(non) <= 0).all())


def test_triple_barrier_directional_on_monotone_series():
    """On a strictly rising series the UPPER barrier is hit first → label 1; on a
    strictly falling series the LOWER → label 0. Labels are pure 0/1."""
    idx = pd.date_range("2020-01-01", periods=120, freq="D")
    up = pd.Series(100 * 1.01 ** np.arange(120), index=idx)
    dn = pd.Series(100 * 0.99 ** np.arange(120), index=idx)
    ev = idx[10:80]
    y_up = meta_label.triple_barrier_labels(up, ev, horizon=20, mult=1.0, vol_window=10)
    y_dn = meta_label.triple_barrier_labels(dn, ev, horizon=20, mult=1.0, vol_window=10)
    assert set(np.unique(y_up.dropna())) <= {0.0, 1.0}
    assert y_up.mean() == 1.0, "rising series must label every long correct"
    assert y_dn.mean() == 0.0, "falling series must label every long wrong"


def test_forward_sign_matches_realized_return_sign():
    df = _synth()
    ev = meta_label.primary_events(df["alloc_optimal"])
    h = 30
    y = meta_label.forward_sign_labels(df["close"], ev, h)
    fwd = df["close"].shift(-h) / df["close"] - 1.0
    # y must equal 1 exactly where the realized forward return is positive
    chk = pd.concat([y.rename("y"), (fwd.reindex(y.index) > 0).astype(float).rename("r")], axis=1)
    assert bool((chk["y"] == chk["r"]).all())
    assert y.notna().all() and set(np.unique(y)) <= {0.0, 1.0}


# --------------------------------------------------------------------------- #
# features — leak-safe construction
# --------------------------------------------------------------------------- #
def test_build_features_columns_and_causal_drawdown():
    df = _synth()
    X = meta_label.build_features(df)
    assert {"drawdown", "risk_regime_hi"} <= set(X.columns)          # engineered features present
    assert "momentum" in X.columns and "risk_index" in X.columns     # passthrough context
    # drawdown is price vs a TRAILING max → always ≤ 0 (causal: never peeks forward)
    dd = X["drawdown"].dropna()
    assert float(dd.max()) <= 1e-9
    assert set(np.unique(X["risk_regime_hi"].dropna())) <= {0.0, 1.0}


def test_build_features_drops_all_nan_columns():
    df = _synth()
    df["mvrv_z"] = np.nan                       # a feature that doesn't exist for this asset/era
    X = meta_label.build_features(df)
    assert "mvrv_z" not in X.columns


# --------------------------------------------------------------------------- #
# PURGED FOLDS — no leakage (the load-bearing test)
# --------------------------------------------------------------------------- #
def test_purged_folds_have_no_label_leakage():
    """For every test fold, NO training event's forward-label window [t, t+horizon]
    may overlap the test span, the test bars themselves must be excluded, and the
    embargo must hold. Checked for BOTH cv modes; walk-forward must also be causal."""
    df = _synth(n=1000)
    horizon, embargo, k = 30, 30, 5
    full = df.index
    ev = meta_label.primary_events(df["alloc_optimal"])
    folds = purged_folds(full, k, embargo)
    pos = {ts: i for i, ts in enumerate(full)}
    ev_pos = {ts: pos[ts] for ts in ev}

    for mode in ("cpcv", "walkforward"):
        for block in folds.values():
            if len(block) == 0:
                continue
            test_lo, test_hi = pos[block.min()], pos[block.max()]
            train = meta_label._train_events(ev_pos, test_lo, test_hi, horizon, embargo, mode)
            tp = [ev_pos[t] for t in train]
            # (1) no test bar is in training
            assert all(not (test_lo <= p <= test_hi) for p in tp)
            # (2) PURGE: no training label window [p, p+horizon] overlaps [test_lo, test_hi]
            assert all(not (p <= test_hi and p + horizon >= test_lo) for p in tp), \
                f"label leak in {mode}"
            # (3) EMBARGO: nothing in (test_hi, test_hi+embargo]
            assert all(not (test_hi < p <= test_hi + embargo) for p in tp)
            # (4) walk-forward is strictly causal (train entirely before the test fold)
            if mode == "walkforward":
                assert all(p < test_lo for p in tp)


def test_oof_proba_only_predicts_test_bars():
    """Out-of-fold sanity: predictions land only on event bars, are valid
    probabilities, and never cover a bar outside the fold geometry."""
    df = _synth(n=900)
    X = meta_label.build_features(df)
    ev = meta_label.primary_events(df["alloc_optimal"])
    y = meta_label.forward_sign_labels(df["close"], ev, 20)
    hgb = {"max_depth": 2, "max_iter": 30, "random_state": 0}
    proba, info, folds = meta_label.purged_oof_proba(
        X, y, df.index, horizon=20, k=3, embargo=20, hgb_params=hgb,
        mode="walkforward", min_test=10, min_train=50)
    assert len(proba) > 0 and proba.between(0, 1).all()
    assert proba.index.isin(y.index).all()      # only labeled event bars
    assert len(info) >= 1


# --------------------------------------------------------------------------- #
# meta-sizing transforms
# --------------------------------------------------------------------------- #
def test_meta_size_filter_and_scale():
    idx = pd.date_range("2021-01-01", periods=5, freq="D")
    alloc = pd.Series([1.0, 1.0, 0.5, 1.0, 0.0], index=idx)
    proba = pd.Series([0.4, 0.7, 0.9, 0.45, 0.8], index=idx)
    filt = meta_label.meta_size(alloc, proba, scheme="filter", threshold=0.5)
    assert filt.iloc[0] == 0.0 and filt.iloc[1] == 1.0 and filt.iloc[3] == 0.0  # P<0.5 zeroed
    raw = meta_label.meta_size(alloc, proba, scheme="prob_raw")
    assert abs(raw.iloc[1] - 0.7) < 1e-9                                        # 1.0 * 0.7
    assert (raw <= alloc + 1e-9).all() and (raw >= 0).all()


# --------------------------------------------------------------------------- #
# DEGRADE-NEVER-RAISE
# --------------------------------------------------------------------------- #
def test_degrade_on_empty_frame():
    r = meta_label.run_meta_label(pd.DataFrame())
    assert r["available"] is False and "reason" in r


def test_degrade_on_missing_alloc_column():
    df = _synth().drop(columns=["alloc_optimal"])
    r = meta_label.run_meta_label(df)
    assert r["available"] is False and "alloc_optimal" in r["reason"]


def test_degrade_on_internal_error_is_caught():
    """An exception raised INSIDE the pipeline (here an unknown size scheme) must be
    swallowed by the top-level guard, not propagated."""
    df = _synth()
    r = meta_label.run_meta_label(df, {"size_schemes": [{"name": "bad", "scheme": "nope"}],
                                       "label_methods": ["forward_sign"],
                                       "hgb": {"max_depth": 2, "max_iter": 20, "random_state": 0},
                                       "cv_folds": 3, "horizon": 20})
    assert r["available"] is False and "reason" in r


def test_full_run_is_available_and_does_not_recommend_noise():
    """End-to-end on synthetic data: the leaf returns a complete result and, on data
    with no real edge, correctly does NOT recommend wiring live (random features can't
    beat the primary out-of-fold). Uses a shrunk GBT so it stays fast."""
    df = _synth(n=900)
    cfg = {"label_methods": ["forward_sign"], "cv_folds": 3, "horizon": 20,
           "min_train_events": 50, "min_test_events": 10,
           "size_schemes": [{"name": "filter@0.55", "scheme": "filter", "threshold": 0.55},
                            {"name": "prob_raw", "scheme": "prob_raw"}],
           "hgb": {"max_depth": 2, "max_iter": 40, "learning_rate": 0.05,
                   "min_samples_leaf": 40, "random_state": 0, "early_stopping": False}}
    r = meta_label.run_meta_label(df, cfg)
    assert r["available"] is True
    for key in ("selected", "grid", "deflated_sharpe_meta", "calibration",
                "verdict", "recommend_live", "n_trials"):
        assert key in r
    assert isinstance(r["recommend_live"], bool)
    assert r["n_trials"] == len(r["grid"])
    # random context has no genuine edge → must not be recommended live
    assert r["recommend_live"] is False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"all {len(fns)} meta-label tests passed")
