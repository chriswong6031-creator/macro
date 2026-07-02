"""GBT meta-labeling LEAF for the Bitcoin Vector primary allocation signal.

WHAT THIS IS (López de Prado, *Advances in Financial ML* ch.3): the PRIMARY model
sets the SIDE — here the existing deterministic BTC allocation grid in
`engine.btc_signals.allocation()` (a function of momentum & risk_index). A
SECONDARY model (a gradient-boosted tree) takes the primary's "be long" calls plus
CONTEXT features and learns P(the primary call is correct) over a forward horizon.
It is used to FILTER false positives / SIZE the bet — it learns TRUST + SIZE, never
DIRECTION.

WHY HERE AND NOWHERE ELSE (institutional-grade review): GBT overfits catastrophically
on the ~10-episode macro/crisis layer (n≈crises). The BTC daily bar is the one place
in this repo with genuinely high-N labels — ~4000 daily bars since 2014, ~3000 of
which the primary flags "allocate". That is the only layer where a tree can earn its
keep without memorizing noise.

DEFAULT-OFF LEAF — ADDITIVE. Nothing in this module mutates the live deterministic
allocation. `compute_all()` does not import it. It is wired live ONLY if it proves
out (beats the primary baseline out-of-fold on a risk-adjusted basis AND the
probabilities are calibrated) and someone flips `vector.meta_label.enabled`.

HONEST VALIDATION — REUSES `engine.validation` (does not reinvent):
  * purged_folds()  — purged + embargoed CV geometry (embargo = the forward horizon,
    because overlapping forward labels leak across a plain k-fold boundary). We NEVER
    use a plain k-fold here. On top of the fold geometry we apply an explicit
    label-window PURGE + EMBARGO so no training label overlaps the test span.
  * deflated_sharpe() — the multiple-testing haircut; n_trials counts the configs tried.
  * brier_reliability + platt_fit — probability calibration (does P match reality?).
  * vif() — feature collinearity.
  * block_bootstrap_ci(), backtest_core() — CI + the shared net-of-cost backtest engine.

No look-ahead: every feature is known at bar t (rolling/backward only); barriers and
labels look FORWARD from t but are never used as features; the meta-probability acts
NEXT bar (backtest_core shifts the position by 1).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.validation import (
    backtest_core, block_bootstrap_ci, brier_reliability, deflated_sharpe,
    dsr_verdict, platt_fit, purged_folds, vif,
)

log = logging.getLogger(__name__)

TRADING_YEAR = 365  # BTC trades every calendar day

# Context features the primary grid does not already fully encode. Missing columns
# are skipped (the leaf degrades, never raises). All are known at bar t.
DEFAULT_FEATURES = [
    "momentum",         # primary momentum strength (its own confidence)
    "risk_index",       # primary risk gauge level
    "risk_oscillator",  # risk momentum
    "vol_pctile",       # downside-vol percentile regime
    "cycle_position",   # cycle/regime knob
    "cycle_pct",        # halving-cycle time tag
    "impulse",          # acceleration / trend strength
    "structure",        # market-structure score
    "funding_z",        # leverage / positioning extremity
    "leverage_stress",  # liquidation-cascade gauge
    "oi_mcap_ratio",    # leverage froth
    "corr_spx",         # cross-asset correlation regime
    "mvrv_z",           # valuation
    "reserve_risk",     # cycle-bottom / euphoria
    "vdd_multiple",     # spending-behaviour axis
    "bfi",              # fundamentals/liquidity blend
    "cot_z",            # CME positioning
    "macro_score",      # macro tailwind/headwind
    "global_m2_yoy",    # broad-money tide
]


# --------------------------------------------------------------------------- #
# events, labels, features
# --------------------------------------------------------------------------- #
def primary_events(alloc: pd.Series, min_alloc: float = 1e-9) -> pd.DatetimeIndex:
    """The bars where the PRIMARY signal says "allocate / be long" (alloc > 0). These
    are the only bars meta-labeling touches — meta-labels P(correct) on the primary's
    own positive calls; it can never invent a long the primary didn't make."""
    a = pd.to_numeric(alloc, errors="coerce")
    mask = a.notna() & (a > min_alloc)
    return a.index[mask]


def triple_barrier_labels(close: pd.Series, events, horizon: int, mult: float = 1.0,
                          vol_window: int = 30) -> pd.Series:
    """Triple-barrier meta-label for each event bar (López de Prado). Symmetric
    vol-scaled barriers at p0·(1 ± mult·σ_t·√horizon), where σ_t is the TRAILING
    daily-return std (no look-ahead in the barrier width). Walking forward up to
    `horizon` days: label 1 if the UPPER barrier is touched first (the long paid off),
    0 if the LOWER is touched first; if neither (the vertical/time barrier) the label
    is the sign of the close-to-close return at t+horizon. Returns a 0/1 Series indexed
    on the events that had enough forward data."""
    close = pd.to_numeric(close, errors="coerce")
    ret = close.pct_change()
    sigma = ret.rolling(vol_window, min_periods=max(5, vol_window // 3)).std()
    arr = close.to_numpy(dtype=float)
    sig = sigma.to_numpy(dtype=float)
    pos = {ts: i for i, ts in enumerate(close.index)}
    n = len(arr)
    out: dict = {}
    for ts in events:
        i = pos.get(ts)
        if i is None or i + 1 >= n or not np.isfinite(arr[i]) or not np.isfinite(sig[i]):
            continue
        p0 = arr[i]
        band = mult * sig[i] * np.sqrt(horizon)
        up, dn = p0 * (1.0 + band), p0 * (1.0 - band)
        j_end = min(i + horizon, n - 1)
        label = None
        for j in range(i + 1, j_end + 1):
            if not np.isfinite(arr[j]):
                continue
            if arr[j] >= up:
                label = 1.0
                break
            if arr[j] <= dn:
                label = 0.0
                break
        if label is None:                       # vertical (time) barrier
            label = 1.0 if arr[j_end] > p0 else 0.0
        out[ts] = label
    return pd.Series(out, dtype=float).sort_index()


def forward_sign_labels(close: pd.Series, events, horizon: int) -> pd.Series:
    """Simpler meta-label: 1 if the close-to-close forward return over `horizon` days
    is strictly positive (the primary's long made money), else 0. Indexed on the events
    that had `horizon` days of forward data."""
    close = pd.to_numeric(close, errors="coerce")
    fwd = close.shift(-horizon) / close - 1.0
    f = fwd.reindex(pd.Index(events))
    y = (f > 0).astype(float)
    return y[f.notna()].sort_index()


def build_features(df: pd.DataFrame, feature_cols=None, dd_window: int = 90) -> pd.DataFrame:
    """Assemble the leak-safe CONTEXT feature matrix from a compute_all() frame. Every
    column is known at bar t: the listed signals are rolling/backward, plus two
    engineered causal features — `drawdown` (price vs its trailing `dd_window` high,
    ≤0) and `risk_regime_hi` (the confirmed high-risk flag). Columns absent from `df`
    are skipped; an all-NaN column is dropped. NaNs are LEFT IN — the GBT
    (HistGradientBoostingClassifier) handles missing values natively, so no leaky
    imputation is needed."""
    cols = list(DEFAULT_FEATURES if feature_cols is None else feature_cols)
    X = pd.DataFrame(index=df.index)
    for c in cols:
        if c in df.columns:
            X[c] = pd.to_numeric(df[c], errors="coerce")
    if "close" in df.columns:
        close = pd.to_numeric(df["close"], errors="coerce")
        X["drawdown"] = close / close.rolling(dd_window, min_periods=10).max() - 1.0
    if "risk_regime" in df.columns:
        X["risk_regime_hi"] = (df["risk_regime"].astype("string") == "high_risk").astype(float)
    return X.dropna(axis=1, how="all")


# --------------------------------------------------------------------------- #
# purged + embargoed out-of-fold GBT probabilities
# --------------------------------------------------------------------------- #
def _bar_pos(full_index) -> dict:
    return {ts: i for i, ts in enumerate(full_index)}


def _train_events(ev_pos, test_lo: int, test_hi: int, horizon: int, embargo: int,
                  mode: str) -> list:
    """Candidate training events (as DatetimeIndex labels) for a test fold spanning bar
    positions [test_lo, test_hi], after the López de Prado PURGE + EMBARGO:

      * PURGE  — drop any training event whose forward-label window [t, t+horizon]
        overlaps the test span (t ≤ test_hi and t+horizon ≥ test_lo). This is the leak
        a plain k-fold has: a label computed near a fold edge peeks into the next fold.
      * EMBARGO — additionally drop training events within `embargo` bars AFTER the test
        span (serial correlation beyond the exact label window).

    mode="cpcv": candidates are all events OUTSIDE the test block (train on both earlier
    and later purged folds — López de Prado's combinatorial-purged CV; maximal data, used
    for probability-quality). mode="walkforward": candidates are strictly EARLIER events
    (a causal, tradeable backtest)."""
    out = []
    for ts, p in ev_pos.items():
        if test_lo <= p <= test_hi:
            continue                                          # the test fold itself
        if mode == "walkforward" and p >= test_lo:
            continue                                          # causal: earlier bars only
        if p <= test_hi and p + horizon >= test_lo:
            continue                                          # PURGE: label overlaps test
        if test_hi < p <= test_hi + embargo:
            continue                                          # EMBARGO: just after test
        out.append(ts)
    return out


def purged_oof_proba(X: pd.DataFrame, y: pd.Series, full_index, horizon: int,
                     k: int, embargo: int, hgb_params: dict, mode: str = "cpcv",
                     min_test: int = 20, min_train: int = 150) -> tuple:
    """Out-of-fold P(primary correct) from a HistGradientBoostingClassifier trained
    under purged + embargoed CV. Fold geometry comes from validation.purged_folds() on
    the FULL daily index; training events are then purged/embargoed against each test
    span by `_train_events` so no overlapping label leaks. Returns
    (oof_proba: Series on event bars, fold_info: list, folds: dict). A fold with too few
    test/train events, or only one class in train, is skipped (its events get no OOF
    prediction). DEGRADE: returns an empty Series if sklearn is unavailable."""
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
    except Exception as e:                                    # pragma: no cover
        log.warning("meta_label: scikit-learn unavailable (%s)", e)
        return pd.Series(dtype=float), [], {}

    y = y.dropna().sort_index()
    ev = y.index
    Xev = X.reindex(ev)
    folds = purged_folds(full_index, k, embargo)
    full_pos = _bar_pos(full_index)
    ev_pos = {ts: full_pos[ts] for ts in ev if ts in full_pos}
    proba = pd.Series(index=ev, dtype=float)
    fold_info: list = []

    for name, block in folds.items():
        if len(block) == 0:
            continue
        test_ev = ev.intersection(block)
        if len(test_ev) < min_test:
            continue
        test_lo = full_pos[block.min()]
        test_hi = full_pos[block.max()]
        train_ev = _train_events(ev_pos, test_lo, test_hi, horizon, embargo, mode)
        ytr = y.loc[train_ev]
        if len(train_ev) < min_train or ytr.nunique() < 2:
            continue
        # Per-fold feature usability: an entirely-NaN column (a feature that doesn't
        # exist yet in an early walk-forward fold — e.g. COT/funding/leverage) or a
        # constant column crashes the GBT binner. Keep only columns with enough signal
        # in THIS fold's training slice, and predict on the same set.
        Xtr = Xev.loc[train_ev]
        usable = [c for c in Xtr.columns
                  if Xtr[c].notna().sum() >= 20 and Xtr[c].nunique(dropna=True) >= 2]
        if len(usable) < 3:
            continue
        clf = HistGradientBoostingClassifier(**hgb_params)
        clf.fit(Xtr[usable].to_numpy(dtype=float), ytr.to_numpy(dtype=float))
        p = clf.predict_proba(Xev.loc[test_ev, usable].to_numpy(dtype=float))[:, 1]
        proba.loc[test_ev] = p
        fold_info.append({"fold": name, "span": f"{block.min().date()}..{block.max().date()}",
                          "n_train": len(train_ev), "n_test": int(len(test_ev)),
                          "n_features": len(usable), "train_pos_rate": round(float(ytr.mean()), 3)})
    return proba.dropna().sort_index(), fold_info, folds


# --------------------------------------------------------------------------- #
# meta-sizing transforms (the default-off APPLICATION — not wired live)
# --------------------------------------------------------------------------- #
def meta_size(alloc: pd.Series, proba: pd.Series, scheme: str = "prob_linear",
              threshold: float = 0.5, p_lo: float = 0.5, p_hi: float = 0.75) -> pd.Series:
    """Apply a meta-probability to the primary allocation and return a NEW alloc series
    (the live engine is never touched — this is what a future wiring WOULD do):

      * "filter"      — zero the position when P < threshold (drop low-trust longs).
      * "prob_raw"    — scale the grid by P directly (size ∝ trust).
      * "prob_linear" — scale by P mapped linearly from [p_lo, p_hi] → [0, 1] (a sharper
        trust ramp around the decision band).

    `proba` is the OOF probability on event bars. On bars with no meta-probability
    (non-events, where the primary alloc is ~0, or rare fold-edge gaps) the primary
    allocation is kept unchanged — missing trust defers to the primary."""
    a = pd.to_numeric(alloc, errors="coerce").copy()
    p = proba.reindex(a.index)
    if scheme == "filter":
        out = a.where((p >= threshold) | p.isna(), 0.0)
    elif scheme == "prob_raw":
        out = a * p.clip(0.0, 1.0).fillna(1.0)
    elif scheme == "prob_linear":
        mult = ((p - p_lo) / max(p_hi - p_lo, 1e-9)).clip(0.0, 1.0).fillna(1.0)
        out = a * mult
    else:
        raise ValueError(f"unknown meta-size scheme: {scheme}")
    return out.clip(0.0, 1.0)


# --------------------------------------------------------------------------- #
# backtest summary (net of cost) — thin wrapper on the shared engine
# --------------------------------------------------------------------------- #
def _bt_summary(close: pd.Series, alloc: pd.Series, cost_bps: float) -> dict:
    """NET-of-cost CAGR / Sharpe / MaxDD + the per-period moments the DSR consumes,
    via the shared validation.backtest_core (next-bar, turnover-scaled cost)."""
    bt = backtest_core(close, alloc, cost_bps=cost_bps)
    net, ret, pos, turn, years = bt["net"], bt["ret"], bt["pos"], bt["turnover"], bt["years"]
    eq = (1.0 + net).cumprod()

    def cagr(e):
        return float(e.iloc[-1] ** (1 / years) - 1) if years > 0 and e.iloc[-1] > 0 else float("nan")

    def sharpe(r):
        sd = float(r.std())
        return float(r.mean() / sd * np.sqrt(TRADING_YEAR)) if sd else float("nan")

    def maxdd(e):
        return float((e / e.cummax() - 1.0).min())

    r = net.dropna()
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    sr_daily = mu / sd if sd else None
    z = (r - mu) / sd if sd else None
    return {
        "cagr_pct": round(100 * cagr(eq), 1),
        "sharpe": round(sharpe(net), 3),
        "maxdd_pct": round(100 * maxdd(eq), 1),
        "time_in_market_pct": round(100 * float((pos > 0).mean()), 1),
        "turnover_annual": round(float(turn.sum() / years), 1) if years > 0 else None,
        "total_return_pct": round(100 * float(eq.iloc[-1] - 1.0), 0),
        "sharpe_daily": round(sr_daily, 6) if sr_daily is not None else None,
        "skew": round(float((z ** 3).mean()), 4) if z is not None else None,
        "kurt": round(float((z ** 4).mean()), 4) if z is not None else None,
        "n_obs": int(len(r)),
        "net_returns": net,                       # kept for the bootstrap/DSR; dropped before JSON
    }


# --------------------------------------------------------------------------- #
# orchestrator — DEGRADE-NEVER-RAISE
# --------------------------------------------------------------------------- #
def run_meta_label(df: pd.DataFrame | None = None, cfg: dict | None = None) -> dict:
    """Full meta-label pipeline → a structured result dict. Builds events/labels/
    features, fits the purged-OOF GBT for each label method and CV mode, sizes the
    primary allocation by the OOF probability across a small grid of schemes, backtests
    each NET of cost vs the primary baseline, deflates the best Sharpe (n_trials = the
    configs tried), checks probability calibration, and renders an honest verdict.

    DEGRADE-NEVER-RAISE: any failure (sklearn missing, too few events, single class,
    bad data) returns {"available": False, "reason": ...} rather than raising — a build
    embedding this can never crash. DEFAULT-OFF: nothing here mutates the live engine."""
    try:
        return _run_meta_label_impl(df, cfg)
    except Exception as e:                                    # pragma: no cover
        log.warning("meta_label unavailable: %s: %s", type(e).__name__, e)
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}


def default_cfg() -> dict:
    """Code-default tunables (the leaf ships runnable without a config.yml edit, the
    dislocation/leaf precedent). config.yml `vector.meta_label` overrides these."""
    return {
        "enabled": False,                 # DEFAULT-OFF — never feeds the live allocation
        "primary_variant": "optimal",
        "horizon": 30,
        "barrier_mult": 1.0,
        "vol_window": 30,
        "cv_folds": 6,
        "min_test_events": 20,
        "min_train_events": 150,
        "cost_bps": 10.0,
        "start_date": "2015-01-01",
        "label_methods": ["triple_barrier", "forward_sign"],
        "size_schemes": [
            {"name": "filter@0.50", "scheme": "filter", "threshold": 0.50},
            {"name": "filter@0.55", "scheme": "filter", "threshold": 0.55},
            {"name": "filter@0.60", "scheme": "filter", "threshold": 0.60},
            {"name": "prob_raw", "scheme": "prob_raw"},
            {"name": "prob_linear", "scheme": "prob_linear", "p_lo": 0.5, "p_hi": 0.75},
        ],
        # shallow + heavily regularized: the whole reason GBT is fenced to high-N is
        # that it overfits — constrain depth/leaf-size hard and let early bars stay NaN.
        "hgb": {"max_depth": 3, "max_iter": 200, "learning_rate": 0.05,
                "min_samples_leaf": 60, "l2_regularization": 1.0,
                "max_features": 0.8, "random_state": 7, "early_stopping": False},
        # verdict thresholds
        "min_sharpe_gain": 0.05,          # meta must add ≥ this to net Sharpe
        "maxdd_tolerance_pp": 2.0,        # and not worsen MaxDD by > this many points
        "dsr_floor": 0.90,
    }


def _run_meta_label_impl(df: pd.DataFrame | None, cfg: dict | None) -> dict:
    cfg = {**default_cfg(), **(cfg or {})}
    if df is None:
        from engine import btc_signals
        df = btc_signals.compute_all()
    df = df.loc[cfg["start_date"]:].copy()

    variant = cfg["primary_variant"]
    # Override-Registry (W0): use the pure engine series (alloc_<variant>_raw)
    # as the primary-event column so training events are not erased during gated
    # windows.  The gate-suppressed final alloc_* column would erase all 2026
    # events, silently removing a calendar year from the training set.  Fall back
    # to alloc_<variant> for backwards compatibility with pre-W0 parquet snapshots.
    acol_raw = f"alloc_{variant}_raw"
    acol = acol_raw if acol_raw in df.columns else f"alloc_{variant}"
    if acol not in df.columns or "close" not in df.columns:
        return {"available": False, "reason": f"missing {acol}/close in signal frame"}

    close = pd.to_numeric(df["close"], errors="coerce")
    alloc = pd.to_numeric(df[acol], errors="coerce")
    horizon = int(cfg["horizon"])
    embargo = horizon
    events = primary_events(alloc)
    X = build_features(df)
    if len(events) < 200 or X.shape[1] < 3:
        return {"available": False,
                "reason": f"insufficient events/features (events={len(events)}, feats={X.shape[1]})"}

    # ---- labels per method --------------------------------------------------- #
    labels = {}
    if "triple_barrier" in cfg["label_methods"]:
        labels["triple_barrier"] = triple_barrier_labels(
            close, events, horizon, cfg["barrier_mult"], cfg["vol_window"])
    if "forward_sign" in cfg["label_methods"]:
        labels["forward_sign"] = forward_sign_labels(close, events, horizon)
    labels = {k: v for k, v in labels.items() if v is not None and v.nunique() >= 2 and len(v) >= 200}
    if not labels:
        return {"available": False, "reason": "no usable label set (single class or too few)"}

    # ---- OOF probabilities per (label, mode) -------------------------------- #
    modes = ["walkforward", "cpcv"]   # walkforward drives the verdict; cpcv = info/calibration
    oof: dict = {}
    fold_info: dict = {}
    for lname, y in labels.items():
        for mode in modes:
            p, fi, folds = purged_oof_proba(
                X, y, df.index, horizon, cfg["cv_folds"], embargo, cfg["hgb"], mode=mode,
                min_test=cfg["min_test_events"], min_train=cfg["min_train_events"])
            oof[(lname, mode)] = p
            fold_info[(lname, mode)] = fi
    if all(len(p) == 0 for p in oof.values()):
        return {"available": False, "reason": "no out-of-fold predictions (folds too thin)"}

    cost_bps = float(cfg["cost_bps"])

    # ---- grid: backtest every (label, mode, size-scheme) vs its baseline ----- #
    def baseline_on(cover_index) -> dict:
        sub = alloc.reindex(close.index)
        cov = close.index.isin(cover_index)
        return _bt_summary(close[cov], sub[cov], cost_bps)

    grid: list = []
    for lname, y in labels.items():
        for mode in modes:
            p = oof[(lname, mode)]
            if len(p) == 0:
                continue
            cover = p.index
            base = baseline_on(cover)
            for spec in cfg["size_schemes"]:
                kwargs = {k: spec[k] for k in ("threshold", "p_lo", "p_hi") if k in spec}
                msized = meta_size(alloc, p, scheme=spec["scheme"], **kwargs)
                cov = close.index.isin(cover)
                meta_bt = _bt_summary(close[cov], msized.reindex(close.index)[cov], cost_bps)
                grid.append({
                    "label": lname, "mode": mode, "size": spec["name"],
                    "n_oof": int(len(p)), "cover": f"{cover.min().date()}..{cover.max().date()}",
                    "meta": meta_bt, "baseline": base,
                    "d_sharpe": round(meta_bt["sharpe"] - base["sharpe"], 3),
                    "d_cagr_pp": round(meta_bt["cagr_pct"] - base["cagr_pct"], 1),
                    "d_maxdd_pp": round(meta_bt["maxdd_pct"] - base["maxdd_pct"], 1),
                })

    if not grid:
        return {"available": False, "reason": "no backtestable meta configs"}

    n_trials = len(grid)  # honest: every (label × mode × scheme) strategy we evaluated

    # ---- selection: best CAUSAL (walk-forward) Sharpe gain ------------------- #
    wf = [g for g in grid if g["mode"] == "walkforward"]
    pool = wf if wf else grid
    best = max(pool, key=lambda g: g["d_sharpe"])

    # ---- deflated Sharpe on the selected meta strategy ----------------------- #
    m = best["meta"]
    daily_srs = [g["meta"]["sharpe_daily"] for g in grid if g["meta"]["sharpe_daily"] is not None]
    sr_var = float(np.var(daily_srs, ddof=1)) if len(daily_srs) >= 2 else None
    dsr_meta = deflated_sharpe(m["sharpe_daily"], m["skew"], m["kurt"], m["n_obs"],
                               n_trials, sr_variance=sr_var, trading_year=TRADING_YEAR)
    b = best["baseline"]
    dsr_base = deflated_sharpe(b["sharpe_daily"], b["skew"], b["kurt"], b["n_obs"],
                               1, trading_year=TRADING_YEAR)

    # ---- probability calibration (CPCV OOF — max data) ----------------------- #
    calibration = {}
    for lname, y in labels.items():
        p = oof[(lname, "cpcv")]
        if len(p) == 0:
            p = oof[(lname, "walkforward")]
        if len(p) == 0:
            continue
        yj = y.reindex(p.index)
        rel = brier_reliability(p.to_numpy(), yj.to_numpy()) or {}
        rel["platt"] = platt_fit(p.to_numpy(), yj.to_numpy()) or {}
        rel["horizon"] = horizon
        calibration[lname] = rel

    # ---- collinearity of the feature matrix (additive) ----------------------- #
    Xev = X.reindex(events).apply(pd.to_numeric, errors="coerce")
    vifs = vif(Xev)
    collinearity = {"vif": dict(sorted(vifs.items(), key=lambda kv: -kv[1])),
                    "redundant": [k for k, v in vifs.items() if v >= 5]} if vifs else {}

    # ---- block-bootstrap CI on the selected meta net returns ----------------- #
    boot = block_bootstrap_ci(best["meta"]["net_returns"], block=21, ann=TRADING_YEAR) or {}

    # ---- VERDICT ------------------------------------------------------------- #
    cal = calibration.get(best["label"], {})
    platt = cal.get("platt", {})
    skill = cal.get("skill_score")
    a_coef = platt.get("a")
    calibrated = (skill is not None and skill > 0
                  and a_coef is not None and 0.3 <= a_coef <= 2.0)
    # Risk-adjusted gate: meta must lift the net Sharpe by a meaningful margin AND not
    # buy that lift by deepening the worst drawdown. maxdd_pct is NEGATIVE, so
    # d_maxdd_pp = meta − base is POSITIVE when meta's drawdown is SHALLOWER (better);
    # the guard rejects a deepening worse than `maxdd_tolerance_pp` points. ΔCAGR is
    # reported for transparency but NOT gated — a Sharpe-improving filter legitimately
    # trims CAGR (it sits out some up-days), so a CAGR gate would be the wrong test.
    beats = (best["d_sharpe"] >= cfg["min_sharpe_gain"]
             and best["d_maxdd_pp"] >= -cfg["maxdd_tolerance_pp"])
    dsr_ok = dsr_meta is not None and dsr_meta["dsr"] >= cfg["dsr_floor"]
    recommend_live = bool(beats and calibrated and dsr_ok)

    reasons = []
    reasons.append(("✓" if beats else "✗") + f" risk-adjusted: ΔSharpe {best['d_sharpe']:+.3f} "
                   f"(need ≥{cfg['min_sharpe_gain']}), ΔMaxDD {best['d_maxdd_pp']:+.1f}pp "
                   f"(need ≥−{cfg['maxdd_tolerance_pp']}); ΔCAGR {best['d_cagr_pp']:+.1f}pp (informational)")
    reasons.append(("✓" if calibrated else "✗") + f" calibrated: skill={skill}, "
                   f"Platt a={a_coef}, b={platt.get('b')}")
    reasons.append(("✓" if dsr_ok else "✗") + f" multiple-testing: DSR="
                   f"{(dsr_meta or {}).get('dsr')} over n_trials={n_trials} "
                   f"(need ≥{cfg['dsr_floor']})")
    verdict = ("RECOMMEND WIRING LIVE — meta beats the primary baseline out-of-fold "
               "and is calibrated." if recommend_live else
               "DO NOT WIRE LIVE — meta does not beat the primary baseline out-of-fold "
               "on a calibrated, multiple-testing-honest basis. (The institutional review "
               "anticipated this: meta-labeling adds nothing here, which is a valid result.)")

    # strip the heavy net_returns series before returning (JSON-safe)
    for g in grid:
        g["meta"].pop("net_returns", None)
        g["baseline"].pop("net_returns", None)

    return {
        "available": True,
        "asof": str(df.index.max().date()),
        "span": f"{df.index.min().date()}..{df.index.max().date()}",
        "primary_variant": variant,
        "horizon_days": horizon,
        "embargo_days": embargo,
        "n_events": int(len(events)),
        "n_bars": int(len(df)),
        "features": list(X.columns),
        "n_features": int(X.shape[1]),
        "label_base_rates": {k: round(float(v.mean()), 3) for k, v in labels.items()},
        "cv_folds": cfg["cv_folds"],
        "fold_info": {f"{l}/{m}": fold_info[(l, m)] for (l, m) in fold_info},
        "n_trials": n_trials,
        "grid": grid,
        "selected": {"label": best["label"], "mode": best["mode"], "size": best["size"],
                     "cover": best["cover"], "meta": best["meta"], "baseline": best["baseline"],
                     "d_sharpe": best["d_sharpe"], "d_cagr_pp": best["d_cagr_pp"],
                     "d_maxdd_pp": best["d_maxdd_pp"]},
        "deflated_sharpe_meta": dsr_meta,
        "deflated_sharpe_baseline": dsr_base,
        "dsr_verdict": dsr_verdict(dsr_meta["dsr"]) if dsr_meta else "insufficient data",
        "calibration": calibration,
        "collinearity": collinearity,
        "bootstrap": boot,
        "verdict_checks": reasons,
        "recommend_live": recommend_live,
        "verdict": verdict,
        "note": ("DEFAULT-OFF LEAF. The verdict keys off the CAUSAL walk-forward OOF "
                 "backtest; CPCV OOF (train on all other purged folds) drives the "
                 "probability-calibration read. n_trials counts every (label × mode × "
                 "size-scheme) strategy compared. Wiring live requires recommend_live "
                 "AND a human flip of vector.meta_label.enabled."),
    }
