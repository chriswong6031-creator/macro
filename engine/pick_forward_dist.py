"""Pick-class conditional forward distributions — the CROSS-SECTIONAL sibling of
engine/forward_dist.py.

engine/forward_dist.py conditions ONE asset's own history on ONE state series and
emits an empirical forward cone; engine/anticipation.py drives it live for 48
curated cross-asset names. Neither reaches the equity cross-section: the ~2,900
Prophet board names carry no distributional read at all. This module is that layer.

The construction is deliberately EMPIRICAL (an analog cohort), not a fitted quantile
regression. For an as-of date t we take every (name, date) observation that sits in
the same pre-registered STATE CELL, inside a trailing window, whose forward outcome
was already fully realized before t — and read the empirical quantiles of that pooled
cohort. There are zero fitted weights, empirical quantiles cannot cross, and the read
degrades to the pooled marginal (loudly flagged) when a cell is thin. Whether the
cells carry any information at all is a MEASUREMENT question, answered by
scripts/pick_forward_dist_phase0.py — this module only computes, it never asserts.

LAG CONVENTION (the load-bearing contract)
------------------------------------------
Every feature emitted for date t is computable from bars with date <= t, and nothing
else. Concretely:

  * A plain rolling statistic ending at t (sma200, rolling 252d high, 20d realized
    vol) INCLUDES bar t. That is causal: bar t is known at the close of t.
  * A REFERENCE distribution that bar t is scored against (the trailing 252d mean/std
    of 20d vol, the trailing 252d median of the 20d range) is `.shift(1)` — lagged one
    bar — so an observation is never inside its own reference distribution.
  * The VOL SCALE used to standardize outcomes is `rvol20.shift(1)` (lag 1), so the
    scale is fixed before the outcome window opens.
  * Forward outcomes (ret / mae / mfe over the next h bars) are LABELS, not features;
    they are all-NaN in the last h rows and must never be fed back as state.

`state_features` is truncate-and-recompute stable: features computed on the full panel,
restricted to dates <= T, equal features computed on the panel truncated at T (tests
(a)/(b) in tests/test_pick_forward_dist.py pin this).

EMBARGO
-------
A training observation at date d has its outcome realized at d + h. For it to be fully
realized STRICTLY BEFORE an as-of date t we need d + h < t, i.e. d <= t - h - 1 in
session units. `cohort_mask` is that rule; `window` bounds how far back the cohort
reaches. Nothing else in this module reads a date.

UNITS
-----
`forward_paths` (engine/forward_dist) returns PERCENT. The primary frame here is
VOL-STANDARDIZED: pct/100 divided by (trailing 20d daily vol, lag 1, floored) * sqrt(h),
so a cone is expressed in "h-day sigmas" and is comparable across a 4,000-name
cross-section. `rescale_cone` converts a standardized cone back to percent for a
specific name-date. The raw-percent frame is the secondary read.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.forward_dist import forward_paths

# ---------------------------------------------------------------- pre-registered constants
TAUS: tuple[float, ...] = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
MAE_TAUS: tuple[float, ...] = (0.05, 0.25, 0.50)
HORIZONS: tuple[int, ...] = (10, 21, 63)
PRIMARY_HORIZON = 21

MIN_CELL_N = 400          # pooled observations below which a cell degrades to the marginal
DEFAULT_WINDOW = 504      # trailing cohort window, sessions
VOL_FLOOR = 0.005         # daily-vol floor (0.5%/day) — a name quieter than this is not trading
MIN_OWN_N = 252           # own-name marginal (baseline B1) needs at least this many observations

# Feature windows
SMA_LONG, SMA_SHORT, SLOPE_LAG = 200, 50, 10
HIGH_WIN, HIGH_MINP = 252, 126
VOL_WIN, VOL_MINP = 20, 15
REF_WIN, REF_MINP = 252, 126
RANGE_WIN = 20

FEATURE_COLS = ("above_200dma", "slope50_up", "ext_pct", "rvol_z", "coil")


# ================================================================= split repair
def carry_split_factor(ohlcv: pd.DataFrame, adj_close: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Propagate a split-adjusted CLOSE onto the rest of an OHLCV frame.

    ``scripts.replay_standout_pipeline.split_adjust`` (the only sanctioned splitter in
    this repo — yahoo-verified) adjusts the close series alone. The back-multiplication
    factor is recoverable as ``raw_close / adj_close``; prices divide by it and share
    counts multiply by it. Returns (adjusted frame, touched mask), where `touched` marks
    the bars straddling each applied factor change — the split print itself, which is
    never a clean observation and is stamped ineligible for event selection.
    """
    out = ohlcv.copy()
    raw = ohlcv["close"].astype(float)
    adj = adj_close.reindex(ohlcv.index).astype(float)
    factor = (raw / adj).where(adj.abs() > 0)
    factor = factor.ffill().bfill().fillna(1.0)
    for col in ("open", "high", "low", "close"):
        if col in out.columns:
            out[col] = out[col].astype(float) / factor
    if "volume" in out.columns:
        out["volume"] = out["volume"].astype(float) * factor
    # A factor step between bar i and bar i+1 is the split print: stamp both bars.
    # Stamping bar i-1 uses one-bar-AHEAD factor information (roll(step, -1)) — this is
    # deliberate and disclosed (REVIEW-9): the stamp is feature-side removal only, is
    # never read by outcome construction, and identifying a split print inherently
    # requires seeing the bar after it.
    # Compared with a tolerance, not ==: the factor is recovered by division, so exact
    # equality would flag float noise on every bar and stamp the whole series ineligible.
    f = factor.to_numpy()
    step = ~np.isclose(f, np.roll(f, 1), rtol=1e-6, atol=0.0)
    step[0] = False
    touched = pd.Series(step | np.roll(step, -1), index=ohlcv.index)
    touched.iloc[-1] = bool(step[-1])
    return out, touched


# ================================================================= state features
def state_features(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Causal state features for one name (see LAG CONVENTION in the module docstring).

    Columns
      above_200dma : close > 200d SMA                                    (bool, trend side)
      slope50_up   : 50d SMA above its own value 10 bars ago             (bool, trend slope)
      ext_pct      : 100 * (close / trailing-252d high - 1), <= 0        (extension)
      rvol_z       : 20d realized daily vol, z vs its own trailing 252d
                     mean/std LAGGED ONE BAR                             (vol state)
      coil         : 20d (high-low)/close range / its own trailing 252d
                     median LAGGED ONE BAR; < 1 = compression            (coil)
      rvol20       : 20d realized daily vol (the raw scale, unlagged)
      vol_scale    : rvol20 lagged one bar, floored — the standardizer
      dvol20_med   : 20d median dollar volume (universe filter input)
      bar_index    : 0-based bar count (history-depth filter input)
    """
    close = ohlcv["close"].astype(float)
    high = ohlcv["high"].astype(float) if "high" in ohlcv else close
    low = ohlcv["low"].astype(float) if "low" in ohlcv else close
    volume = ohlcv["volume"].astype(float) if "volume" in ohlcv else pd.Series(np.nan, index=close.index)

    sma_long = close.rolling(SMA_LONG, min_periods=SMA_LONG).mean()
    sma_short = close.rolling(SMA_SHORT, min_periods=SMA_SHORT).mean()
    high252 = close.rolling(HIGH_WIN, min_periods=HIGH_MINP).max()

    logret = np.log(close / close.shift(1))
    rvol20 = logret.rolling(VOL_WIN, min_periods=VOL_MINP).std()
    ref_mean = rvol20.rolling(REF_WIN, min_periods=REF_MINP).mean().shift(1)
    ref_std = rvol20.rolling(REF_WIN, min_periods=REF_MINP).std().shift(1)

    range20 = (high.rolling(RANGE_WIN, min_periods=VOL_MINP).max()
               - low.rolling(RANGE_WIN, min_periods=VOL_MINP).min()) / close
    range_ref = range20.rolling(REF_WIN, min_periods=REF_MINP).median().shift(1)

    out = pd.DataFrame(index=close.index)
    # Booleans are carried as float 1.0/0.0/NaN — an unknown trend side must stay
    # unknown (a bool column silently fills False, which is a state claim).
    out["above_200dma"] = np.where(sma_long.notna(), (close > sma_long).to_numpy(float), np.nan)
    _slope_ok = sma_short.notna() & sma_short.shift(SLOPE_LAG).notna()
    out["slope50_up"] = np.where(
        _slope_ok, (sma_short > sma_short.shift(SLOPE_LAG)).to_numpy(float), np.nan)
    out["ext_pct"] = 100.0 * (close / high252 - 1.0)
    out["rvol_z"] = (rvol20 - ref_mean) / ref_std.where(ref_std > 0)
    out["coil"] = range20 / range_ref.where(range_ref > 0)
    out["rvol20"] = rvol20
    out["vol_scale"] = rvol20.shift(1).clip(lower=VOL_FLOOR)
    out["dvol20_med"] = (close * volume).rolling(VOL_WIN, min_periods=VOL_MINP).median()
    out["bar_index"] = np.arange(len(close), dtype=np.int32)
    return out


# ================================================================= standardization
def standardize_paths(paths: pd.DataFrame, vol_scale: pd.Series, horizon: int) -> pd.DataFrame:
    """Percent forward outcomes -> h-day sigmas: (pct/100) / (vol_scale * sqrt(h)).

    `vol_scale` is the lag-1 floored trailing 20d daily vol from `state_features`."""
    denom = vol_scale.reindex(paths.index).astype(float) * np.sqrt(float(horizon))
    denom = denom.where(denom > 0)
    return paths.divide(100.0 * denom, axis=0)


def rescale_cone(cone: dict, vol_scale: float, horizon: int) -> dict:
    """Standardized cone -> percent, for one name-date. Inverse of `standardize_paths`."""
    mult = 100.0 * float(vol_scale) * np.sqrt(float(horizon))
    out = dict(cone)
    for key in ("ret_q", "mae_q"):
        if isinstance(cone.get(key), dict):
            out[key] = {k: (None if v is None else float(v) * mult) for k, v in cone[key].items()}
    if cone.get("mfe_q50") is not None:
        out["mfe_q50"] = float(cone["mfe_q50"]) * mult
    out["units"] = "pct"
    return out


# ================================================================= cells
def bands_of(x, edges: np.ndarray) -> np.ndarray:
    """Vectorized band index, elementwise-identical to engine.forward_dist.band_of:
    right-closed bands, first band closed-left, clipped at both ends. NaN -> -1."""
    a = np.asarray(x, dtype=float)
    edges = np.asarray(edges, dtype=float)
    if edges.size < 2:
        return np.full(a.shape, -1, dtype=np.int16)
    idx = np.clip(np.searchsorted(edges, a, side="left") - 1, 0, edges.size - 2)
    return np.where(np.isfinite(a), idx, -1).astype(np.int16)


def cohort_edges(values, k: int) -> np.ndarray:
    """k equal-frequency edges from a COHORT of values (deduped). Same construction as
    engine.forward_dist.quantile_edges, but fed the embargoed training cohort rather
    than the full sample — the cross-sectional path's causal band estimate."""
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return np.array([], dtype=float)
    return np.unique(np.nanquantile(a, np.linspace(0.0, 1.0, k + 1)))


# Pre-registered schemes. `axes` = (feature column, kind, k). kind "bool" -> {0,1};
# kind "q" -> k equal-frequency bands whose edges are fit on the training cohort.
SCHEMES: dict[str, tuple[tuple[str, str, int], ...]] = {
    "S1_trend":     (("above_200dma", "bool", 2), ("slope50_up", "bool", 2)),
    "S2_extension": (("ext_pct", "q", 4),),
    "S3_vol":       (("rvol_z", "q", 4),),
    "S4_coil":      (("coil", "q", 4),),
    "S5_trend_vol": (("above_200dma", "bool", 2), ("rvol_z", "q", 3)),
}
SCHEME_CELLS = {name: int(np.prod([a[2] for a in axes])) for name, axes in SCHEMES.items()}


def fit_scheme_edges(train: pd.DataFrame, scheme: str) -> dict[str, np.ndarray]:
    """Cohort quantile edges for each quantile axis of `scheme` (bool axes need none)."""
    edges = {}
    for col, kind, k in SCHEMES[scheme]:
        if kind == "q":
            edges[col] = cohort_edges(train[col].to_numpy(), k)
    return edges


def assign_cells(feat, scheme: str, edges: dict[str, np.ndarray]) -> np.ndarray:
    """Mixed-radix cell code per row; -1 when ANY axis is missing (never silently pooled).

    `feat` is a DataFrame or any column-mapping of arrays — the evaluation path passes
    zero-copy numpy views of one session's rows rather than slicing a DataFrame per date."""
    axes = SCHEMES[scheme]
    n = len(feat[axes[0][0]])
    codes, radices = [], []
    for col, kind, k in axes:
        v = feat[col]
        v = v.to_numpy() if hasattr(v, "to_numpy") else np.asarray(v)
        if kind == "bool":
            f = pd.to_numeric(pd.Series(v), errors="coerce").to_numpy(dtype=float)
            good = np.isfinite(f)
            c = np.where(good, np.clip(np.nan_to_num(f, nan=0.0), 0, 1), -1).astype(np.int16)
        else:
            e = edges.get(col, np.array([]))
            c = bands_of(v, e)
            if e.size >= 2:
                c = np.where(c >= 0, np.minimum(c, k - 1), -1).astype(np.int16)
        codes.append(c)
        radices.append(k)
    out = np.zeros(n, dtype=np.int32)
    bad = np.zeros(n, dtype=bool)
    for c, k in zip(codes, radices):
        out = out * k + np.maximum(c, 0)
        bad |= (c < 0)
    return np.where(bad, -1, out).astype(np.int32)


# ================================================================= embargoed cohort
def cohort_mask(obs_sess, asof_sess: int, horizon: int, window: int = DEFAULT_WINDOW) -> np.ndarray:
    """Training observations usable at as-of session `asof_sess`.

    An observation at session d resolves at d + horizon. It is admissible only if it
    resolved STRICTLY BEFORE the as-of bar: d + horizon < asof  <=>  d <= asof - horizon - 1.
    `window` bounds the trailing reach. Sessions are integer indices into a shared
    trading calendar, so the embargo is exact regardless of holidays."""
    s = np.asarray(obs_sess)
    hi = int(asof_sess) - int(horizon) - 1
    return (s <= hi) & (s > hi - int(window))


# ================================================================= empirical cones
def _qkey(tau: float) -> str:
    return f"q{int(round(tau * 100)):02d}"


def empirical_cone(z_ret, z_mae=None, z_mfe=None, *, taus=TAUS, mae_taus=MAE_TAUS) -> dict:
    """Empirical forward distribution of one pooled cohort (standardized units).

    Quantiles come straight from the sample, so they are monotone by construction —
    a cone from this function can never cross."""
    r = np.asarray(z_ret, dtype=float)
    r = r[np.isfinite(r)]
    if r.size == 0:
        return {"n": 0, "ret_q": {}, "mae_q": {}, "mfe_q50": None, "p_up": None}
    out = {
        "n": int(r.size),
        "ret_q": {_qkey(t): float(v) for t, v in zip(taus, np.quantile(r, taus))},
        "mae_q": {},
        "mfe_q50": None,
        "p_up": float((r > 0).mean()),
    }
    if z_mae is not None:
        m = np.asarray(z_mae, dtype=float)
        m = m[np.isfinite(m)]
        if m.size:
            out["mae_q"] = {_qkey(t): float(v) for t, v in zip(mae_taus, np.quantile(m, mae_taus))}
    if z_mfe is not None:
        f = np.asarray(z_mfe, dtype=float)
        f = f[np.isfinite(f)]
        if f.size:
            out["mfe_q50"] = float(np.median(f))
    return out


def fit_cones(cell_codes, z_ret, z_mae=None, z_mfe=None, *, min_n: int = MIN_CELL_N,
              taus=TAUS, mae_taus=MAE_TAUS) -> dict:
    """Per-cell empirical cones from an embargoed cohort, with the marginal fallback.

    A cell holding fewer than `min_n` pooled observations does NOT get its own thin
    quantiles — it inherits the pooled marginal and is stamped ``degraded=True`` with
    its own ``n`` preserved beside ``n_used``. Consumers must surface that stamp; a
    silently-marginal cell reads as a conditional claim it cannot support."""
    codes = np.asarray(cell_codes, dtype=np.int64)
    r = np.asarray(z_ret, dtype=float)
    ok = np.isfinite(r) & (codes >= 0)
    marginal = empirical_cone(r[ok],
                              None if z_mae is None else np.asarray(z_mae, float)[ok],
                              None if z_mfe is None else np.asarray(z_mfe, float)[ok],
                              taus=taus, mae_taus=mae_taus)
    marginal["degraded"] = False
    marginal["cell"] = None

    cells: dict[int, dict] = {}
    if ok.any():
        c_ok = codes[ok]
        order = np.argsort(c_ok, kind="stable")
        c_sorted = c_ok[order]
        uniq, starts = np.unique(c_sorted, return_index=True)
        bounds = np.append(starts, c_sorted.size)
        r_ok = r[ok][order]
        m_ok = None if z_mae is None else np.asarray(z_mae, float)[ok][order]
        f_ok = None if z_mfe is None else np.asarray(z_mfe, float)[ok][order]
        for i, code in enumerate(uniq):
            sl = slice(int(bounds[i]), int(bounds[i + 1]))
            n = int(bounds[i + 1] - bounds[i])
            if n < min_n:
                cells[int(code)] = {**marginal, "n": n, "n_used": marginal["n"],
                                    "degraded": True, "cell": int(code)}
                continue
            cone = empirical_cone(r_ok[sl],
                                  None if m_ok is None else m_ok[sl],
                                  None if f_ok is None else f_ok[sl],
                                  taus=taus, mae_taus=mae_taus)
            cone.update({"degraded": False, "n_used": n, "cell": int(code)})
            cells[int(code)] = cone
    return {"marginal": marginal, "cells": cells, "min_n": int(min_n),
            "taus": list(taus), "mae_taus": list(mae_taus)}


def cone_for(fit: dict, cell_code) -> dict:
    """Cone for one cell. An unseen cell (or a missing feature, code -1) degrades to the
    marginal — flagged, never silent."""
    code = int(cell_code)
    if code < 0 or code not in fit["cells"]:
        m = dict(fit["marginal"])
        m.update({"degraded": True, "n": 0, "n_used": fit["marginal"]["n"], "cell": code})
        return m
    return fit["cells"][code]


def _lut(fit: dict, sig, need_top: int, build):
    """Dense lookup table for a fit, memoized ON the fit.

    Slot 0 is the marginal/unknown row; cell c lives at c+1. A table rather than a loop
    over unique cells because B1's cells are NAMES: a per-cell mask loop is O(names^2)
    per evaluation date, and the table is rebuilt only when the fit changes (quarterly),
    not once per date."""
    cache = fit.setdefault("_luts", {})
    hit = cache.get(sig)
    if hit is not None and hit[0] >= need_top:
        return hit
    top = int(max(need_top, max(fit["cells"], default=-1)))
    built = (top, *build(top))
    cache[sig] = built
    return built


def cone_matrix(fit: dict, cell_codes, *, taus=TAUS) -> tuple[np.ndarray, np.ndarray]:
    """(n_obs x n_tau) predicted-quantile matrix + a per-obs `degraded` mask.
    Vectorized `cone_for`: an unknown or uncodable cell resolves to the marginal and
    is stamped degraded, exactly as `cone_for` does one at a time."""
    codes = np.asarray(cell_codes, dtype=np.int64)
    keys = [_qkey(t) for t in taus]
    if codes.size == 0:
        return np.empty((0, len(keys)), dtype=float), np.empty(0, dtype=bool)

    def build(top: int):
        marg = np.array([fit["marginal"]["ret_q"].get(k, np.nan) for k in keys], dtype=float)
        lut = np.tile(marg, (top + 2, 1))
        degl = np.ones(top + 2, dtype=bool)
        for c, v in fit["cells"].items():
            lut[c + 1] = [v["ret_q"].get(k, np.nan) for k in keys]
            degl[c + 1] = bool(v["degraded"])
        return lut, degl

    top, lut, degl = _lut(fit, ("ret_q", tuple(keys)), int(codes.max()), build)
    idx = np.where((codes >= 0) & (codes <= top), codes + 1, 0)
    return lut[idx], degl[idx]


def cone_scalar(fit: dict, cell_codes, field: str = "mae_q", key: str = "q05") -> np.ndarray:
    """One cone field per observation (e.g. the predicted MAE p05), vectorized the same
    way as `cone_matrix`. NaN where the cone does not carry the field."""
    codes = np.asarray(cell_codes, dtype=np.int64)
    if codes.size == 0:
        return np.empty(0, dtype=float)

    def build(top: int):
        marg = float((fit["marginal"].get(field) or {}).get(key, np.nan))
        lut = np.full(top + 2, marg, dtype=float)
        for c, v in fit["cells"].items():
            lut[c + 1] = float((v.get(field) or {}).get(key, np.nan))
        return (lut,)

    top, lut = _lut(fit, (field, key), int(codes.max()), build)
    idx = np.where((codes >= 0) & (codes <= top), codes + 1, 0)
    return lut[idx]


def own_name_cones(name_codes, z_ret, *, min_own_n: int = MIN_OWN_N, taus=TAUS,
                   fallback: dict | None = None) -> dict:
    """Baseline B1: each name's OWN trailing marginal. A name with fewer than
    `min_own_n` observations in the embargoed window falls back to `fallback`
    (normally the pooled marginal) and is stamped degraded."""
    codes = np.asarray(name_codes, dtype=np.int64)
    r = np.asarray(z_ret, dtype=float)
    ok = np.isfinite(r) & (codes >= 0)
    fb = fallback if fallback is not None else empirical_cone(r[ok], taus=taus)
    fb = {**fb, "degraded": True}
    cells: dict[int, dict] = {}
    if ok.any():
        c_ok, r_ok = codes[ok], r[ok]
        order = np.argsort(c_ok, kind="stable")
        c_sorted, r_sorted = c_ok[order], r_ok[order]
        uniq, starts = np.unique(c_sorted, return_index=True)
        bounds = np.append(starts, c_sorted.size)
        for i, code in enumerate(uniq):
            n = int(bounds[i + 1] - bounds[i])
            if n < min_own_n:
                cells[int(code)] = {**fb, "n": n, "n_used": fb.get("n", 0),
                                    "degraded": True, "cell": int(code)}
                continue
            cone = empirical_cone(r_sorted[int(bounds[i]):int(bounds[i + 1])], taus=taus)
            cone.update({"degraded": False, "n_used": n, "cell": int(code)})
            cells[int(code)] = cone
    return {"marginal": fb, "cells": cells, "min_n": int(min_own_n), "taus": list(taus),
            "mae_taus": []}


# ================================================================= panel assembly
# Pre-registered daily universe filter (causal — every input ends at bar t).
PRICE_MIN = 5.0
DVOL_MIN = 2.0e6
MIN_BARS = 300


def build_panel(frames: dict, *, horizons=HORIZONS, price_min: float = PRICE_MIN,
                dvol_min: float = DVOL_MIN, min_bars: int = MIN_BARS,
                calendar: pd.DatetimeIndex | None = None) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """Assemble a skinny long-format observation panel from per-name OHLCV frames.

    PURE: `frames` is {name: OHLCV DataFrame} already in memory (already split-repaired
    by the caller). A frame carrying a boolean ``split_touched`` column has those bars
    stamped ineligible — a split print is not a clean observation.

    A row survives only if it clears the daily universe filter (close > `price_min`,
    20d median dollar volume >= `dvol_min`, at least `min_bars` of own history) AND every
    state feature plus the vol scale is finite. Outcome columns per horizon h:
    ``z_ret_h`` / ``z_mae_h`` / ``z_mfe_h`` (vol-standardized, the primary frame) and
    ``ret_h`` (raw percent, the secondary frame). They are NaN in the last h bars of each
    name — that is the label horizon, not a defect.

    ``sess`` is an integer index into the shared trading calendar, so the embargo in
    `cohort_mask` is exact across holidays and per-name gaps. Returns (panel, calendar).
    """
    if calendar is None:
        allidx = pd.DatetimeIndex(sorted({d for f in frames.values() for d in f.index}))
    else:
        allidx = pd.DatetimeIndex(calendar)
    sess_of = pd.Series(np.arange(len(allidx), dtype=np.int32), index=allidx)

    chunks = []
    for name, ohlcv in frames.items():
        if ohlcv is None or len(ohlcv) < min_bars:
            continue
        feat = state_features(ohlcv)
        close = ohlcv["close"].astype(float)
        elig = ((close > price_min)
                & (feat["dvol20_med"] >= dvol_min)
                & (feat["bar_index"] >= min_bars)
                & feat[list(FEATURE_COLS)].notna().all(axis=1)
                & feat["vol_scale"].notna())
        if "split_touched" in ohlcv.columns:
            elig &= ~ohlcv["split_touched"].fillna(False).astype(bool)
        elig = elig.fillna(False).to_numpy(dtype=bool)
        if not elig.any():
            continue
        cols = {c: feat[c].to_numpy(dtype=np.float32)[elig] for c in FEATURE_COLS}
        cols["vol_scale"] = feat["vol_scale"].to_numpy(dtype=np.float32)[elig]
        for h in horizons:
            paths = forward_paths(close, int(h))
            z = standardize_paths(paths, feat["vol_scale"], int(h))
            cols[f"ret_{h}"] = paths["ret"].to_numpy(dtype=np.float32)[elig]
            cols[f"z_ret_{h}"] = z["ret"].to_numpy(dtype=np.float32)[elig]
            cols[f"z_mae_{h}"] = z["mae"].to_numpy(dtype=np.float32)[elig]
            cols[f"z_mfe_{h}"] = z["mfe"].to_numpy(dtype=np.float32)[elig]
        idx = ohlcv.index[elig]
        chunk = pd.DataFrame(cols, index=range(len(idx)))
        chunk.insert(0, "sess", sess_of.reindex(idx).to_numpy(dtype=np.int32))
        chunk.insert(0, "name", name)
        chunks.append(chunk)

    if not chunks:
        return pd.DataFrame(columns=["name", "sess"]), allidx
    panel = pd.concat(chunks, ignore_index=True)
    panel["name"] = panel["name"].astype("category")
    panel.sort_values(["sess", "name"], kind="stable", inplace=True)
    panel.reset_index(drop=True, inplace=True)
    return panel, allidx


def fit_at(panel: pd.DataFrame, asof_sess: int, scheme: str, horizon: int, *,
           window: int = DEFAULT_WINDOW, min_n: int = MIN_CELL_N, taus=TAUS,
           ret_col: str | None = None, mae_col: str | None = None,
           mfe_col: str | None = None) -> dict:
    """The whole PIT recipe at one as-of session: embargoed cohort -> cohort band edges
    -> cell codes -> per-cell empirical cones. The study and the truncate-and-recompute
    test both call THIS, so a leak cannot hide in a path only one of them exercises."""
    ret_col = ret_col or f"z_ret_{horizon}"
    mae_col = mae_col or f"z_mae_{horizon}"
    mfe_col = mfe_col or f"z_mfe_{horizon}"
    m = cohort_mask(panel["sess"].to_numpy(), asof_sess, horizon, window)
    tr = panel.loc[m]
    edges = fit_scheme_edges(tr, scheme)
    codes = assign_cells(tr, scheme, edges)
    fit = fit_cones(codes, tr[ret_col].to_numpy(),
                    tr[mae_col].to_numpy() if mae_col in tr else None,
                    tr[mfe_col].to_numpy() if mfe_col in tr else None,
                    min_n=min_n, taus=taus)
    fit["edges"] = {k: [float(x) for x in v] for k, v in edges.items()}   # JSON-safe copy
    fit["edges_arr"] = edges                                             # reuse at emit time
    fit["scheme"], fit["horizon"] = scheme, int(horizon)
    fit["asof_sess"], fit["cohort_rows"] = int(asof_sess), int(len(tr))
    fit["window"] = int(window)
    return fit


def fit_baselines_at(panel: pd.DataFrame, asof_sess: int, horizon: int, *,
                     window: int = DEFAULT_WINDOW, min_own_n: int = MIN_OWN_N,
                     taus=TAUS, ret_col: str | None = None) -> tuple[dict, dict]:
    """The two pre-registered nulls at one as-of session, on the SAME embargoed cohort:
      B0 — the pooled unconditional trailing distribution (no cells at all).
      B1 — each name's OWN trailing marginal (>= `min_own_n` observations, else B0).
    A conditioning scheme that cannot beat both of these has bought nothing."""
    ret_col = ret_col or f"z_ret_{horizon}"
    m = cohort_mask(panel["sess"].to_numpy(), asof_sess, horizon, window)
    tr = panel.loc[m]
    z = tr[ret_col].to_numpy()
    b0_marg = empirical_cone(z, taus=taus)
    b0_marg.update({"degraded": False, "cell": None, "n_used": b0_marg["n"]})
    b0 = {"marginal": b0_marg, "cells": {}, "min_n": 0, "taus": list(taus), "mae_taus": [],
          "cohort_rows": int(len(tr))}
    name_codes = tr["name"].cat.codes.to_numpy() if hasattr(tr["name"], "cat") \
        else pd.Categorical(tr["name"]).codes
    b1 = own_name_cones(name_codes, z, min_own_n=min_own_n, taus=taus, fallback=b0_marg)
    b1["cohort_rows"] = int(len(tr))
    return b0, b1


# ================================================================= evaluation metrics
def pinball(y, q, tau: float) -> np.ndarray:
    """Pinball (quantile) loss at level tau. Lower is better; 0 only at a perfect call."""
    y = np.asarray(y, dtype=float)
    q = np.asarray(q, dtype=float)
    d = y - q
    return np.where(d >= 0, tau * d, (tau - 1.0) * d)


def mean_pinball(y, qmat, taus=TAUS) -> np.ndarray:
    """Per-observation mean pinball across the tau grid — the CRPS proxy this study
    scores schemes on. `qmat` is (n_obs x n_tau) aligned to `taus`."""
    y = np.asarray(y, dtype=float)
    qmat = np.asarray(qmat, dtype=float)
    loss = np.empty_like(qmat)
    for j, t in enumerate(taus):
        loss[:, j] = pinball(y, qmat[:, j], float(t))
    return loss.mean(axis=1)


def interval_coverage(y, lo, hi) -> float:
    """Fraction of realized outcomes inside [lo, hi]. Nominal 80% for [q10, q90]."""
    y, lo, hi = np.broadcast_arrays(np.asarray(y, dtype=float), np.asarray(lo, dtype=float),
                                    np.asarray(hi, dtype=float))
    ok = np.isfinite(y) & np.isfinite(lo) & np.isfinite(hi)
    if not ok.any():
        return float("nan")
    return float(((y[ok] >= lo[ok]) & (y[ok] <= hi[ok])).mean())


def tail_hit_rate(realized_mae, pred_mae_q05) -> float:
    """Fraction of name-days whose worst dip was AT OR BEYOND the predicted p05 dip
    (both are negative). Nominal 5% — well above means the tail is understated."""
    y = np.asarray(realized_mae, dtype=float)
    q = np.asarray(pred_mae_q05, dtype=float)
    ok = np.isfinite(y) & np.isfinite(q)
    if not ok.any():
        return float("nan")
    return float((y[ok] <= q[ok]).mean())


def breach_run_stat(breach_rate_by_date, nominal: float = 0.20) -> dict:
    """REPORT-ONLY clustering read on interval breaches. Independent breaches give a
    lag-1 autocorrelation near 0 and short runs; a cone that is only wrong in clusters
    (the honest failure mode of a state-conditioned read) shows up here even when the
    unconditional coverage looks fine. Never a gate — it has no pre-registered null."""
    s = pd.Series(breach_rate_by_date).dropna().astype(float)
    if len(s) < 10:
        return {"n_dates": int(len(s)), "lag1_autocorr": None, "max_run_above_nominal": None,
                "frac_dates_above_nominal": None}
    a = s.to_numpy()
    x, y = a[:-1], a[1:]
    sx, sy = x.std(), y.std()
    ac = float(np.mean((x - x.mean()) * (y - y.mean())) / (sx * sy)) if sx > 0 and sy > 0 else None
    above = a > nominal
    run = best = 0
    for v in above:
        run = run + 1 if v else 0
        best = max(best, run)
    return {"n_dates": int(len(s)), "lag1_autocorr": None if ac is None else round(ac, 4),
            "max_run_above_nominal": int(best),
            "frac_dates_above_nominal": round(float(above.mean()), 4),
            "nominal": nominal}


def block_bootstrap_mean_ci(x, block: int = 21, B: int = 5000, seed: int = 7) -> dict:
    """Circular block bootstrap of the MEAN of a date-indexed series.

    engine.validation.block_bootstrap_ci bootstraps the SHARPE of a return series (its
    CI excluding 0 is the same sign test, since a draw's Sharpe is positive exactly when
    its mean is). This returns the interval in the series' OWN units, which is what a
    pinball delta has to be reported in. Blocks preserve the autocorrelation that
    overlapping forward windows induce across adjacent dates."""
    a = np.asarray(x.dropna() if hasattr(x, "dropna") else x, dtype=float)
    a = a[np.isfinite(a)]
    n = a.size
    if n < max(block * 3, 60):
        return {}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    grid = np.arange(block)
    means = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        means[k] = a[idx].mean()
    lo, mid, hi = (float(np.percentile(means, p)) for p in (2.5, 50, 97.5))
    return {"mean": float(a.mean()), "ci": [lo, mid, hi],
            "excludes_zero": bool(lo > 0 or hi < 0),
            "gt0_prob": float(np.mean(means > 0)), "block": int(block), "B": int(B), "n": int(n)}


__all__ = [
    "TAUS", "MAE_TAUS", "HORIZONS", "PRIMARY_HORIZON", "MIN_CELL_N", "DEFAULT_WINDOW",
    "VOL_FLOOR", "MIN_OWN_N", "FEATURE_COLS", "SCHEMES", "SCHEME_CELLS",
    "PRICE_MIN", "DVOL_MIN", "MIN_BARS",
    "carry_split_factor", "state_features", "standardize_paths", "rescale_cone",
    "bands_of", "cohort_edges", "fit_scheme_edges", "assign_cells", "cohort_mask",
    "empirical_cone", "fit_cones", "cone_for", "cone_matrix", "cone_scalar", "own_name_cones",
    "build_panel", "fit_at", "fit_baselines_at",
    "pinball", "mean_pinball", "interval_coverage", "tail_hit_rate", "breach_run_stat",
    "block_bootstrap_mean_ci", "forward_paths",
]
