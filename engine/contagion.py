"""Contagion Engine — Diebold-Yilmaz Spillover + Correlation Tightening + Two-Tier Read.

ADDITIVE / pure-leaf: imports nothing from the scoring core. Reads stores via lib.store
only. All public functions are fail-open and deterministic.

IRD-R4 PRE-REGISTERED PARAMETERS (frozen — any change requires a masterplan edit):
  Window:       150 business days
  VAR lag:      2
  Horizon H:    10 (generalized FEVD)
  Vol measure:  Garman-Klass range-based vol
  Basket:       6 DM + 6 EM country ETFs + EEM + SPY (adjudicated 2026-07-12)

FROZEN ADJUDICATED BASKET (2026-07-12 — coverage-greedy all-DM draft rejected):
  DM (6): EWJ (Japan), EWG (Germany), EWU (UK), EWC (Canada), EWA (Australia), EWL (Switzerland)
  EM (6): EWZ (Brazil), EWW (Mexico), INDA (India), EIDO (Indonesia), EZA (South Africa), EWY (South Korea)
  + EEM (broad EM benchmark) + SPY (US benchmark)
  Total: 14 tickers. All verified present in data/intl_etf (2026-07-12).

Public API
----------
spillover()         — DY total + directional connectedness + 1y weekly history
corr_tightening()   — rolling EEM-vs-EM-FX-basket corr + avg pairwise ETF corr velocity
two_tier_read()     — IRD-R3 state machine: contained / watching / transmitting / quiet
"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import store
from engine.ird_velocity import velocity_fields as _ird_velocity_fields

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IRD-R4 frozen parameters
# ---------------------------------------------------------------------------
_DY_WINDOW = 150        # business days
_DY_VAR_LAG = 2
_DY_HORIZON = 10
_DY_WEEKLY_STRIDE = 5   # every 5th business day for the ~1y history

# Frozen adjudicated basket (IRD-R4, adjudicated 2026-07-12):
#   coverage-greedy all-DM 12-ticker draft rejected; replaced with 6-DM / 6-EM split.
# DM (6): EWJ, EWG, EWU, EWC, EWA, EWL
# EM (6): EWZ, EWW, INDA, EIDO, EZA, EWY
# + EEM (broad EM) + SPY (US) — total 14 tickers, all in data/intl_etf (except EEM/SPY from yahoo)
_ETF_BASKET_DM = ["EWJ", "EWG", "EWU", "EWC", "EWA", "EWL"]
_ETF_BASKET_EM = ["EWZ", "EWW", "INDA", "EIDO", "EZA", "EWY"]
_ETF_BASKET = _ETF_BASKET_DM + _ETF_BASKET_EM + ["EEM", "SPY"]

_CORR_WINDOW = 60       # days for correlation tightening
_TWO_YEARS = 504        # ~2y in trading days


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r(v, nd: int = 3):
    if v is None:
        return None
    try:
        f = float(v)
        return None if not math.isfinite(f) else round(f, nd)
    except (TypeError, ValueError):
        return None


def _load_etf_close(ticker: str) -> pd.Series | None:
    """Load close from intl_etf (country ETFs) or yahoo (EEM, SPY) store."""
    if ticker in ("EEM", "SPY", "KRE"):
        df = store.read("yahoo", ticker)
    else:
        df = store.read("intl_etf", ticker)
    if df is None or df.empty:
        return None
    col = "close" if "close" in df.columns else df.columns[0]
    s = df[col].astype(float).dropna()
    return s if not s.empty else None


def _load_etf_ohlc(ticker: str) -> pd.DataFrame | None:
    """Load OHLCV from intl_etf or yahoo."""
    if ticker in ("EEM", "SPY", "KRE"):
        df = store.read("yahoo", ticker)
    else:
        df = store.read("intl_etf", ticker)
    if df is None or df.empty:
        return None
    needed = {"open", "high", "low", "close"}
    has = set(df.columns)
    if not needed.issubset(has):
        return None
    return df[list(needed)].astype(float)


def _garman_klass_vol(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Garman-Klass annualized range-based volatility (causal rolling).

    GK = sqrt( 252 * (0.5*(ln(H/L))^2 - (2*ln2-1)*(ln(C/O))^2) )
    Strictly causal: rolling over past window rows.
    """
    lo = np.log(df["high"] / df["low"])
    co = np.log(df["close"] / df["open"])
    gk = (0.5 * lo ** 2 - (2 * math.log(2) - 1) * co ** 2).clip(lower=0)
    vol = np.sqrt(gk.rolling(window, min_periods=max(5, window // 3)).mean() * 252)
    return vol


def _fred_series(series_id: str) -> pd.Series | None:
    df = store.read("fred", series_id)
    if df is None or df.empty:
        return None
    s = df.iloc[:, 0].astype(float).dropna()
    return s if not s.empty else None


def _pctile_trailing(s: pd.Series, window: int) -> float | None:
    """Trailing percentile of the current observation within its own window.

    Inclusive convention: the current value IS included in its own ranking window
    (w <= last includes the last element of w, which equals last).  This means a
    fresh all-time-high within the window reads 100.0, not (n-1)/n × 100.
    Callers that need exclusive-window percentiles must slice before calling.
    """
    if s is None or s.empty:
        return None
    w = s.iloc[-min(window, len(s)):]
    last = float(s.iloc[-1])
    return round(float((w <= last).mean() * 100.0), 1)


def _vel_z_20d(s: pd.Series) -> float | None:
    """20d velocity z-score via shared IRD-R13 grammar (engine.ird_velocity).

    Calls velocity_fields(s, scale=1) and returns vel_20d_z — a TRUE z (mean-subtracted,
    current-obs excluded from the norm window, trailing 2y or max-available).
    This is the single authoritative velocity grammar for all IRD lobes.
    """
    return _ird_velocity_fields(s, scale=1.0)["vel_20d_z"]


# ---------------------------------------------------------------------------
# VAR + GFEVD implementation (pure numpy, ~40 lines of math)
# ---------------------------------------------------------------------------

def _fit_var(Y: np.ndarray, p: int) -> tuple[np.ndarray, np.ndarray]:
    """Fit VAR(p) via OLS. Y shape: (T, K). Returns (A_stacked, Sigma).

    A_stacked shape: (K, K*p) — coefficient matrices [A1 | A2 | ... | Ap]
    Sigma: (K, K) innovation covariance matrix.
    """
    T, K = Y.shape
    # Build regressor matrix X with lags
    rows = T - p
    X = np.ones((rows, K * p), dtype=float)
    for lag in range(1, p + 1):
        X[:, (lag - 1) * K: lag * K] = Y[p - lag: T - lag, :]
    y = Y[p:, :]

    # OLS: A = (X'X)^-1 X'Y  (coefficient matrix, shape (K*p, K))
    try:
        XtX = X.T @ X
        XtY = X.T @ y
        A = np.linalg.lstsq(XtX, XtY, rcond=None)[0]  # (K*p, K)
    except np.linalg.LinAlgError:
        return np.zeros((K, K * p)), np.eye(K)

    Amat = A.T  # (K, K*p)
    resid = y - X @ A
    Sigma = (resid.T @ resid) / max(rows - K * p - 1, 1)
    return Amat, Sigma


def _var_to_ma(Amat: np.ndarray, p: int, H: int) -> list[np.ndarray]:
    """Compute MA coefficient matrices Phi_0 ... Phi_H from VAR coefficient matrix.

    Amat: (K, K*p). Returns list of H+1 matrices each (K, K).
    Recursive: Phi_h = sum_{j=1}^{p} A_j * Phi_{h-j}, Phi_0 = I.
    """
    K = Amat.shape[0]
    # Extract individual A_j matrices
    A_list = [Amat[:, j * K: (j + 1) * K] for j in range(p)]

    Phi = [np.eye(K)]
    for h in range(1, H + 1):
        ph = np.zeros((K, K))
        for j, Aj in enumerate(A_list):
            if h - 1 - j >= 0:
                ph += Aj @ Phi[h - 1 - j]
        Phi.append(ph)
    return Phi


def _gfevd(Phi: list[np.ndarray], Sigma: np.ndarray, H: int) -> np.ndarray:
    """Generalized Forecast Error Variance Decomposition (Koop-Pesaran-Shin).

    Returns theta matrix (K, K) where theta[i, j] = share of H-step-ahead
    forecast error variance of variable i due to innovations in variable j.
    Each row sums to 1 (after row-normalization).

    Ref: Diebold & Yilmaz (2012), equation (4).
    """
    K = Sigma.shape[0]
    sigma_diag = np.diag(Sigma)  # (K,) variance vector

    # Numerator: sum_{h=0}^{H-1} (e_i' Phi_h Sigma e_j)^2 / sigma_jj
    # e_j is the j-th unit vector
    numer = np.zeros((K, K))
    denom = np.zeros(K)
    for h in range(H):
        Ph = Phi[h]
        PhS = Ph @ Sigma  # (K, K)
        # theta_h numerator contribution: (PhS)_{i,j}^2 / sigma_jj
        for j in range(K):
            numer[:, j] += (PhS[:, j] ** 2) / max(sigma_diag[j], 1e-12)
        # Denominator for variable i = sum_h e_i' Phi_h Sigma Phi_h' e_i
        for i in range(K):
            e_i = Ph[i, :]  # i-th row of Phi_h
            denom[i] += float(e_i @ Sigma @ e_i)

    # Row-normalize so rows sum to 1
    theta = np.zeros((K, K))
    for i in range(K):
        d = denom[i]
        if d > 1e-12:
            theta[i, :] = numer[i, :] / d
    # Row-normalize to ensure exact sum-to-1 (generalized FEVD normalization)
    row_sums = theta.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums < 1e-12, 1.0, row_sums)
    theta = theta / row_sums
    return theta


def _dy_connectedness(theta: np.ndarray) -> dict:
    """Compute Diebold-Yilmaz connectedness measures from normalized GFEVD.

    Returns total_connectedness (0-100), to_others[:], from_others[:].
    """
    K = theta.shape[0]
    # Own-share = diagonal; off-diagonal = spillovers
    own_share = np.diag(theta)
    # from_others[i] = 1 - own_share[i] = share from other variables
    from_others = 1.0 - own_share
    # to_others[j] = sum_i theta[i,j] for i != j (column sum excluding diagonal)
    to_others = (theta.sum(axis=0) - np.diag(theta))

    # Total connectedness = mean of from_others (or equivalently off-diagonal / K)
    total = float(np.mean(from_others)) * 100.0
    return {
        "total": max(0.0, min(100.0, total)),
        "to_others": to_others.tolist(),
        "from_others": from_others.tolist(),
        "own_share": own_share.tolist(),
    }


# ---------------------------------------------------------------------------
# spillover() — public function
# ---------------------------------------------------------------------------

def spillover() -> dict:
    """Diebold-Yilmaz Connectedness Index (IRD-R4 frozen params).

    Returns:
      total_connectedness: 0-100 scalar
      to_others: {ticker: value} directional transmitting shares
      from_others: {ticker: value} directional receiving shares
      top_transmitters: list of top-3 ticker names (highest to_others)
      us_from_others: SPY's from_others share (0-1) — contagion-to-US read
      history_weekly: list of {date, total} for ~52 weeks (every 5th business day)
      n_series: int
      gaps: list[str]
      as_of: ISO date
      built: ISO timestamp
      timing_sec: wall-clock seconds for the snapshot computation
    """
    t0 = time.time()
    gaps: list[str] = []

    # --- Load and align all series ---
    gk_vols: dict[str, pd.Series] = {}
    loaded_tickers: list[str] = []
    missing_tickers: list[str] = []

    for ticker in _ETF_BASKET:
        ohlc = _load_etf_ohlc(ticker)
        if ohlc is None or ohlc.empty or len(ohlc) < _DY_WINDOW + 20:
            # Fallback: use daily close log-return vol
            c = _load_etf_close(ticker)
            if c is not None and len(c) >= _DY_WINDOW + 20:
                # Parkinson-style proxy: use rolling std of log returns
                lr = np.log(c / c.shift(1)).dropna()
                vol_s = lr.rolling(20, min_periods=5).std() * math.sqrt(252)
                gk_vols[ticker] = vol_s.dropna()
                loaded_tickers.append(ticker)
                gaps.append(f"{ticker}: OHLC absent — using close-return vol proxy")
            else:
                missing_tickers.append(ticker)
                gaps.append(f"{ticker}: insufficient data, omitted from basket")
            continue

        vol_s = _garman_klass_vol(ohlc, window=20).dropna()
        if len(vol_s) < _DY_WINDOW + 20:
            missing_tickers.append(ticker)
            gaps.append(f"{ticker}: GK vol too short, omitted")
            continue
        gk_vols[ticker] = vol_s
        loaded_tickers.append(ticker)

    if missing_tickers:
        gaps.append(f"DY basket: {len(missing_tickers)} tickers omitted {missing_tickers}")

    if len(loaded_tickers) < 3:
        elapsed = time.time() - t0
        log.warning("[timing] DY spillover: insufficient data in %.2fs", elapsed)
        print(f"[timing] DY spillover: insufficient_data in {elapsed:.2f}s")
        return {
            "total_connectedness": None,
            "to_others": {}, "from_others": {},
            "top_transmitters": [],
            "us_from_others": None,
            "history_weekly": [],
            "n_series": 0,
            "gaps": gaps,
            "as_of": "n/a",
            "built": datetime.now(timezone.utc).isoformat(),
            "timing_sec": _r(elapsed, 2),
            "state": "insufficient_data",
        }

    # --- Align to common daily index ---
    idx = gk_vols[loaded_tickers[0]].index
    for t in loaded_tickers[1:]:
        idx = idx.union(gk_vols[t].index)
    idx = idx.sort_values()

    aligned = {}
    for t in loaded_tickers:
        s = gk_vols[t].reindex(idx).ffill(limit=3).dropna()
        aligned[t] = s

    # Intersect to rows where ALL tickers have data
    all_idx = aligned[loaded_tickers[0]].index
    for t in loaded_tickers[1:]:
        all_idx = all_idx.intersection(aligned[t].index)
    all_idx = all_idx.sort_values()

    if len(all_idx) < _DY_WINDOW + 10:
        elapsed = time.time() - t0
        gaps.append(f"DY: common index only {len(all_idx)} rows (need {_DY_WINDOW + 10})")
        print(f"[timing] DY spillover: short common idx in {elapsed:.2f}s")
        return {
            "total_connectedness": None,
            "to_others": {}, "from_others": {},
            "top_transmitters": [], "us_from_others": None,
            "history_weekly": [],
            "n_series": len(loaded_tickers),
            "gaps": gaps,
            "as_of": "n/a",
            "built": datetime.now(timezone.utc).isoformat(),
            "timing_sec": _r(elapsed, 2),
            "state": "insufficient_data",
        }

    K = len(loaded_tickers)
    mat = np.column_stack([aligned[t].reindex(all_idx).values for t in loaded_tickers])
    as_of = str(all_idx[-1].date())

    # --- Current snapshot DY (on last 150d window) ---
    Y = mat[-_DY_WINDOW:, :]
    Amat, Sigma = _fit_var(Y, _DY_VAR_LAG)
    Phi = _var_to_ma(Amat, _DY_VAR_LAG, _DY_HORIZON)
    theta = _gfevd(Phi, Sigma, _DY_HORIZON)
    conn = _dy_connectedness(theta)

    to_dict = {loaded_tickers[j]: _r(conn["to_others"][j] * 100.0, 1)
               for j in range(K)}
    from_dict = {loaded_tickers[j]: _r(conn["from_others"][j] * 100.0, 1)
                 for j in range(K)}

    # Top 3 transmitters
    top3 = sorted(to_dict.items(), key=lambda x: x[1] or 0, reverse=True)[:3]
    top_transmitters = [{"ticker": t, "to_others_pct": v} for t, v in top3]

    # SPY from_others
    spy_from = from_dict.get("SPY")

    # --- Weekly history (~52 weeks of 5th-business-day strides) ---
    history: list[dict] = []
    n_hist_steps = 260  # ~52 weeks * 5 trading days
    # Compute on weekly strides ending at most recent window
    stride_ends = list(range(len(all_idx) - 1, max(_DY_WINDOW - 1, len(all_idx) - n_hist_steps - 1), -_DY_WEEKLY_STRIDE))
    stride_ends.reverse()

    for end_idx in stride_ends:
        if end_idx < _DY_WINDOW:
            continue
        Y_w = mat[end_idx - _DY_WINDOW + 1: end_idx + 1, :]
        if Y_w.shape[0] < _DY_WINDOW:
            continue
        try:
            A_w, S_w = _fit_var(Y_w, _DY_VAR_LAG)
            Ph_w = _var_to_ma(A_w, _DY_VAR_LAG, _DY_HORIZON)
            th_w = _gfevd(Ph_w, S_w, _DY_HORIZON)
            c_w = _dy_connectedness(th_w)
            d_str = str(all_idx[end_idx].date())
            history.append({"date": d_str, "total": _r(c_w["total"], 1)})
        except Exception:
            continue

    elapsed = time.time() - t0
    print(f"[timing] DY spillover snapshot: {elapsed:.2f}s ({len(loaded_tickers)} series, {len(history)} history points)")

    return {
        "total_connectedness": _r(conn["total"], 1),
        "to_others": to_dict,
        "from_others": from_dict,
        "top_transmitters": top_transmitters,
        "us_from_others": spy_from,
        "history_weekly": history,
        "n_series": K,
        "tickers": loaded_tickers,
        "gaps": gaps,
        "as_of": as_of,
        "built": datetime.now(timezone.utc).isoformat(),
        "timing_sec": _r(elapsed, 2),
        "params": {
            "window": _DY_WINDOW,
            "var_lag": _DY_VAR_LAG,
            "horizon": _DY_HORIZON,
            "vol_measure": "Garman-Klass (20d rolling)",
            "basket": _ETF_BASKET,
        },
    }


# ---------------------------------------------------------------------------
# corr_tightening() — public function
# ---------------------------------------------------------------------------

def corr_tightening() -> dict:
    """Rolling 60d correlation — EEM vs EM FX basket + avg pairwise ETF basket.

    Returns:
      eem_emfx_corr_60d: rolling corr of EEM weekly returns vs EM FX basket (latest)
      pairwise_avg_corr: avg pairwise 60d corr across the ETF basket (latest)
      pairwise_vel_20d_z: velocity z of avg pairwise corr (tightening detector)
      tightening: bool — corr rising while returns negative
      gaps: list[str]
    """
    gaps: list[str] = []

    # EEM weekly returns
    eem = _load_etf_close("EEM")
    if eem is None or eem.empty:
        gaps.append("corr_tightening: EEM absent")
        return {"eem_emfx_corr_60d": None, "pairwise_avg_corr": None,
                "pairwise_vel_20d_z": None, "tightening": None, "gaps": gaps}

    # EM FX basket: equal-weight inverted returns (rising basket = EM FX strengthening)
    _EM_FX_YAHOO_CORR = ["USDTRY_X", "USDZAR_X", "USDBRL_X", "USDMXN_X", "USDIDR_X"]
    _EM_FX_INTL_CORR = ["USDKRW_X", "USDINR_X", "USDTWD_X"]

    fx_rets: list[pd.Series] = []
    for ticker in _EM_FX_YAHOO_CORR:
        df = store.read("yahoo", ticker)
        if df is not None and not df.empty:
            col = "close" if "close" in df.columns else df.columns[0]
            s = df[col].astype(float).dropna()
            if not s.empty:
                fx_rets.append((-np.log(s / s.shift(1))).dropna().rename(ticker))
    for ticker in _EM_FX_INTL_CORR:
        df = store.read("intl", ticker)
        if df is not None and not df.empty:
            col = "close" if "close" in df.columns else df.columns[0]
            s = df[col].astype(float).dropna()
            if not s.empty:
                fx_rets.append((-np.log(s / s.shift(1))).dropna().rename(ticker))

    eem_emfx = None
    if fx_rets:
        idx = fx_rets[0].index
        for r in fx_rets[1:]:
            idx = idx.union(r.index)
        stk = pd.DataFrame({r.name: r.reindex(idx) for r in fx_rets})
        basket_ret = stk.mean(axis=1, skipna=True).dropna()

        # Align EEM daily returns with basket
        eem_ret = np.log(eem / eem.shift(1)).dropna()
        common = eem_ret.index.intersection(basket_ret.index)
        if len(common) >= _CORR_WINDOW:
            eem_a = eem_ret.reindex(common)
            fx_a = basket_ret.reindex(common)
            corr_ser = eem_a.rolling(_CORR_WINDOW, min_periods=30).corr(fx_a).dropna()
            if not corr_ser.empty:
                eem_emfx = _r(float(corr_ser.iloc[-1]), 3)
    else:
        gaps.append("corr_tightening: no EM FX series loaded")

    # Avg pairwise 60d corr across ETF basket
    closes: dict[str, pd.Series] = {}
    for ticker in _ETF_BASKET:
        s = _load_etf_close(ticker)
        if s is not None and len(s) >= _CORR_WINDOW + 20:
            closes[ticker] = s

    pairwise = None
    pairwise_vel = None
    if len(closes) >= 3:
        tickers = sorted(closes.keys())
        # Align all
        idx0 = closes[tickers[0]].index
        for t in tickers[1:]:
            idx0 = idx0.union(closes[t].index)
        df_all = pd.DataFrame({t: closes[t].reindex(idx0).ffill(limit=3) for t in tickers})
        rets_df = np.log(df_all / df_all.shift(1)).dropna()

        if len(rets_df) >= _CORR_WINDOW + 20:
            # Build rolling avg pairwise corr time series
            n = len(tickers)
            pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
            avg_corr_ts = []
            # Only compute on the last min(_TWO_YEARS, len) rows for speed
            tail = rets_df.iloc[-min(_TWO_YEARS + _CORR_WINDOW, len(rets_df)):]
            for end in range(_CORR_WINDOW, len(tail)):
                window_df = tail.iloc[end - _CORR_WINDOW: end]
                corr_mat = window_df.corr()
                pair_corrs = [corr_mat.iloc[i, j] for i, j in pairs
                              if math.isfinite(corr_mat.iloc[i, j])]
                avg_corr_ts.append(float(np.mean(pair_corrs)) if pair_corrs else float("nan"))

            avg_corr_ser = pd.Series(avg_corr_ts, index=tail.index[_CORR_WINDOW:]).dropna()
            if not avg_corr_ser.empty:
                pairwise = _r(float(avg_corr_ser.iloc[-1]), 3)
                pairwise_vel = _vel_z_20d(avg_corr_ser)

    # Tightening signal: corr rising (vel > 0) while returns negative
    tightening = None
    if pairwise_vel is not None and eem is not None and len(eem) >= 20:
        eem_ret_20d = float(eem.iloc[-1] / eem.iloc[-21] - 1.0)
        tightening = bool(pairwise_vel > 0.5 and eem_ret_20d < 0)

    return {
        "eem_emfx_corr_60d": eem_emfx,
        "pairwise_avg_corr": pairwise,
        "pairwise_vel_20d_z": pairwise_vel,
        "tightening": tightening,
        "gaps": gaps,
        "as_of": str(eem.index[-1].date()) if eem is not None else "n/a",
        "built": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# two_tier_read() — public function
# ---------------------------------------------------------------------------

def two_tier_read(em_stress_state: str | None = None) -> dict:
    """IRD-R3 Two-Tier Contagion State Machine.

    Tier-1 (origin): EM stress state from em_stress() + regional OAS velocity read.
    Tier-2 (US transmission): US HY OAS Δ20d z, bank RS, MOVE pctile,
                               SOFR-IORB corridor, safety-bid flag.

    State transitions (deterministic):
      'quiet'        — tier1 is 'calm'
      'contained'    — tier1 >= 'strained', tier2 hot count == 0
      'watching'     — tier1 >= 'strained', tier2 hot count == 1
      'transmitting' — tier1 >= 'strained', tier2 hot count >= 2

    Parameters
    ----------
    em_stress_state : str or None
        Caller may pass the state from em_stress() to avoid re-reading stores.
        If None, this function calls em_stress() internally.

    Returns
    -------
    dict with state, tier1, tier2, detail per leg, gaps, built timestamp.
    """
    from engine.intl_risk import em_stress as _em_stress

    gaps: list[str] = []

    # ---- Tier-1: origin stress ----
    if em_stress_state is None:
        try:
            es = _em_stress()
            tier1_state = es.get("state", "unknown")
        except Exception as exc:
            gaps.append(f"tier1: em_stress() error: {exc}")
            tier1_state = "unknown"
    else:
        tier1_state = em_stress_state

    # Regional OAS velocity: which region is hottest?
    regional_oas: dict[str, dict | None] = {}
    for name, series_id in [("asia", "BAMLEMRACRPIASIAOAS"),
                              ("latam", "BAMLEMRLCRPILAOAS"),
                              ("emea", "BAMLEMRECRPIEMEAOAS")]:
        s = _fred_series(series_id)
        if s is None or s.empty:
            gaps.append(f"tier1: regional OAS {series_id} absent")
            regional_oas[name] = None
            continue
        v20z = _vel_z_20d(s)
        regional_oas[name] = {
            "value": _r(float(s.iloc[-1])),
            "vel_20d_z": v20z,
            "asof": str(s.index[-1].date()),
        }

    # Hottest region by vel_20d_z
    hottest_region = None
    max_vel = None
    for region, data in regional_oas.items():
        if data and data.get("vel_20d_z") is not None:
            v = data["vel_20d_z"]
            if max_vel is None or v > max_vel:
                max_vel = v
                hottest_region = region

    # ---- Tier-2: US transmission legs ----
    tier2_legs: dict[str, dict] = {}
    tier2_hot_count = 0

    # (a) US HY OAS Δ20d z >= 2
    us_hy = _fred_series("BAMLH0A0HYM2")
    if us_hy is not None:
        v20z = _vel_z_20d(us_hy)
        hot = v20z is not None and v20z >= 2.0
        tier2_legs["us_hy_oas_vel"] = {
            "value": _r(float(us_hy.iloc[-1])),
            "vel_20d_z": v20z,
            "hot": hot,
            "threshold": "vel_20d_z >= 2",
        }
        if hot:
            tier2_hot_count += 1
    else:
        gaps.append("tier2: BAMLH0A0HYM2 (US HY OAS) absent")

    # (b) KRE/SPY 20d RS < -5%  (EUFN absent from store)
    spy = _load_etf_close("SPY")
    kre = _load_etf_close("KRE")
    if spy is not None and kre is not None and len(spy) >= 21 and len(kre) >= 21:
        # Align
        idx_rs = spy.index.union(kre.index).sort_values()
        spy_a = spy.reindex(idx_rs).ffill(limit=3)
        kre_a = kre.reindex(idx_rs).ffill(limit=3)
        kre_ret = (kre_a.iloc[-1] / kre_a.iloc[-21] - 1.0) * 100.0
        spy_ret = (spy_a.iloc[-1] / spy_a.iloc[-21] - 1.0) * 100.0
        rs = float(kre_ret) - float(spy_ret)
        hot = rs < -5.0
        tier2_legs["kre_spy_rs"] = {
            "value": _r(rs, 1),
            "kre_ret_20d": _r(float(kre_ret), 2),
            "spy_ret_20d": _r(float(spy_ret), 2),
            "hot": hot,
            "threshold": "KRE-SPY 20d RS < -5%",
            "note": "EUFN/KBWB absent from yahoo store — only KRE included",
        }
        if hot:
            tier2_hot_count += 1
    else:
        gaps.append("tier2: KRE or SPY insufficient data for RS")

    # (c) MOVE pctile >= 85
    move_df = store.read("yahoo", "_MOVE")
    if move_df is not None and not move_df.empty:
        col = "close" if "close" in move_df.columns else move_df.columns[0]
        move_s = move_df[col].astype(float).dropna()
        pct = _pctile_trailing(move_s, len(move_s))  # full history pctile
        hot = pct is not None and pct >= 85.0
        tier2_legs["move_pctile"] = {
            "value": _r(float(move_s.iloc[-1])),
            "pctile": pct,
            "hot": hot,
            "threshold": "pctile >= 85 (full history)",
            "asof": str(move_s.index[-1].date()),
        }
        if hot:
            tier2_hot_count += 1
    else:
        gaps.append("tier2: _MOVE absent from yahoo store")

    # (d) SOFR − IORB > 0 persistent 5d
    # Quarter-end spikes are technical — labeled in caveat
    sofr = _fred_series("SOFR")
    iorb = _fred_series("IORB")
    if sofr is not None and iorb is not None:
        idx_ci = sofr.index.union(iorb.index).sort_values()
        sofr_a = sofr.reindex(idx_ci).ffill(limit=5)
        iorb_a = iorb.reindex(idx_ci).ffill(limit=5)
        spread = (sofr_a - iorb_a).dropna()
        if len(spread) >= 5:
            last5 = spread.iloc[-5:]
            persistent = bool((last5 > 0).all())
            last_val = _r(float(spread.iloc[-1]), 4)
            hot = persistent
            tier2_legs["sofr_iorb_corridor"] = {
                "value": last_val,
                "last5_all_positive": persistent,
                "hot": hot,
                "threshold": "SOFR-IORB > 0 for 5 consecutive days",
                "caveat": "Quarter-end spikes (late Dec/Mar/Jun/Sep) are technical — "
                          "not structural funding stress; verify calendar proximity.",
            }
            if hot:
                tier2_hot_count += 1
        else:
            gaps.append("tier2: SOFR-IORB spread < 5 rows after alignment")
    else:
        gaps.append("tier2: SOFR or IORB absent")

    # (e) Safety-bid flag: DXY 5d up AND DGS2 5d down
    dxy_df = store.read("yahoo", "DX-Y.NYB")
    dgs2 = _fred_series("DGS2")
    safety_bid = None
    if dxy_df is not None and not dxy_df.empty and dgs2 is not None:
        col = "close" if "close" in dxy_df.columns else dxy_df.columns[0]
        dxy = dxy_df[col].astype(float).dropna()
        if len(dxy) >= 6 and len(dgs2) >= 6:
            dxy_5d = float(dxy.iloc[-1]) - float(dxy.iloc[-6])
            dgs2_5d = float(dgs2.iloc[-1]) - float(dgs2.iloc[-6])
            safety_bid = bool(dxy_5d > 0 and dgs2_5d < 0)
            tier2_legs["safety_bid_flag"] = {
                "dxy_5d_chg": _r(dxy_5d, 3),
                "dgs2_5d_chg": _r(dgs2_5d * 100.0, 1),  # convert to bp
                "safety_bid": safety_bid,
                "hot": False,   # informational, not in K-of-N count
                "note": "DXY up & 2y yield down = safe-haven demand, not hot for K-of-N",
            }
    else:
        gaps.append("tier2: DXY or DGS2 absent for safety-bid flag")

    # ---- State machine ----
    tier1_hot = tier1_state in ("strained", "stressed")

    if not tier1_hot:
        state = "quiet"
    elif tier2_hot_count == 0:
        state = "contained"
    elif tier2_hot_count == 1:
        state = "watching"
    else:  # >= 2 tier2 hot while tier1 >= strained
        state = "transmitting"

    return {
        "state": state,
        "tier1": {
            "em_stress_state": tier1_state,
            "hottest_region": hottest_region,
            "regional_oas": regional_oas,
        },
        "tier2": {
            "hot_count": tier2_hot_count,
            "legs": tier2_legs,
        },
        "safety_bid": safety_bid,
        "gaps": gaps,
        "state_logic": (
            "quiet: tier1 calm | contained: tier1>=strained, 0 tier2 hot | "
            "watching: 1 tier2 hot | transmitting: >=2 tier2 hot with tier1>=strained"
        ),
        "built": datetime.now(timezone.utc).isoformat(),
    }
