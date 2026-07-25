"""Portfolio factor-exposure engine — the "you own 8 names but ONE factor bet" lens.

The dashboard scores each stock in isolation. This module answers the *book-level*
question a discretionary trader actually has: across everything I hold, what am I
really long? It regresses each stock's daily return on a set of macro/style factor
returns and ships the per-ticker beta vector; the watchlist then aggregates those
betas against the user's actual position weights (client-side) into portfolio-level
exposures, per-factor risk contribution, a concentration ("one bet") read, and
factor shocks.

THE METHOD MATTERS. The naive version (the one ChatGPT's table implies) is a
*univariate* beta per factor — regress the stock on SPY, then separately on QQQ,
then on BTC, … But SPY/QQQ/BTC are 0.6–0.9 correlated, so each univariate beta
re-counts the same market move and the "exposures" sum to nonsense. Instead we
estimate a MULTIVARIATE model: the factors are orthogonalized in economic priority
order (market first, then style, then macro), so every reported beta is the
*marginal* exposure beyond the higher-priority factors. Because the factors are
then mutually orthogonal the slopes decouple into univariate cov/var (the same
trick engine.residual_alpha uses for sector ⟂ market) — fast and exact, no per-stock
matrix solve. `raw_betas()` keeps the un-orthogonalized univariate betas too: they
are the right number for a single-factor *shock* ("if oil +10%, the book moves …",
a total derivative) and they let the Phase-0 quantify the double-counting the
orthogonal set removes.

This is MEASUREMENT, not prediction — a thermometer, not a signal. So it does NOT go
through the IC/FDR/DSR alpha gauntlet; the honest gate (scripts/factor_exposure_phase0.py)
is whether the betas are STABLE out-of-sample, and the working assumption it
verifies is that only PORTFOLIO-LEVEL aggregates are trustworthy — a single stock's
oil/rate beta is noisy, but averaged across a book the idiosyncratic noise cancels.

ADDITIVE / leaf — nothing in the scoring path imports it. China is intentionally
absent as a *ticker* universe: the only onshore proxy we cache (510300.SS) trades on
a different clock than US names, so a same-day beta is timezone-contaminated; add it
when an FXI/MCHI (US-hours) proxy is collected. (An FXI-based `china` FACTOR is present
— it is US-hours.) HK/CN/CA cash equities are likewise unmodeled here and read
"unmodeled" in the watchlist; they need their own *clock-safe* factor models (own
proxies on their own session closes) — chartered in the WRI masterplan, not built here.

Crypto IS in the exposable universe: BTC-USD/ETH-USD (the coins) plus IBIT/ETHA/COIN
(spot-crypto ETFs + the Coinbase equity) get shipped betas like SPY/QQQ, so a user
holding them sees a real book contribution. They load btc-heavy with high idiosyncratic
vol and low R² on the equity factors — that is correct (crypto is its own bet), not a
bug the orthogonalization should hide. Timezone note: crypto trades ~24/7 while the
factor returns are US-session closes, so there is some async — but BTC-USD is ALREADY
the `btc` FACTOR, computed exactly this way (daily pct_change of the same close series),
so exposing BTC-USD/ETH-USD as tickers is CONSISTENT with existing treatment, not a new
source of contamination. This is why crypto is buildable now while HK/CN cash equities
(no US-hours proxy) are not.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from engine.equity_factors import _closes, _names_sectors
from lib import config, store

log = logging.getLogger(__name__)

TRADING_YEAR = 252

NOTE = ("Multivariate factor betas (market, growth, size, rates, dollar, oil, crypto), "
        "orthogonalized so each beta is the MARGINAL exposure — not the double-counted "
        "univariate kind. A risk/exposure lens, not a signal; trust the portfolio "
        "aggregate, not any single stock's secondary beta.")


@dataclass(frozen=True)
class Factor:
    key: str
    group: str
    sid: str
    col: str
    sign: int      # +1, or -1 to orient (none needed today; kept for symmetry)
    label: str
    note: str


# Economic priority order: market is THE factor, then the style tilts that are highly
# collinear with it (so they must be orthogonalized AFTER market), then the macro
# factors. Orthogonalization peels each factor against all the ones above it, so the
# reported beta is "exposure beyond market / style / …". US-hours, tradeable proxies
# only — see the module docstring on the deliberate China gap.
FACTORS: list[Factor] = [
    Factor("mkt", "yahoo", "SPY", "close", 1,
           "Market", "S&P 500 (SPY) — broad beta, the dominant risk."),
    Factor("growth", "yahoo", "QQQ", "close", 1,
           "Growth / Tech", "Nasdaq-100 (QQQ) beyond market — long-duration / tech tilt."),
    Factor("size", "yahoo", "IWM", "close", 1,
           "Small-cap", "Russell 2000 (IWM) beyond market — small-cap / domestic-cyclical tilt."),
    Factor("rates", "yahoo", "TLT", "close", 1,
           "Rates (duration)", "20y+ Treasuries (TLT) — rises when long yields fall; + beta = bond-like / long-duration."),
    Factor("usd", "yahoo", "DX-Y.NYB", "close", 1,
           "US Dollar", "Dollar index (DXY) — + beta = benefits from a stronger dollar (rare for equities)."),
    Factor("oil", "commodity", "signals_oil", "close", 1,
           "Oil / energy", "WTI crude (26y daily) — + beta = energy / inflation-shock exposure."),
    Factor("china", "yahoo", "FXI", "close", 1,
           "China", "FXI (China large-cap, US-hours) beyond global beta — China/HK growth exposure."),
    Factor("btc", "yahoo", "BTC-USD", "close", 1,
           "Bitcoin / crypto", "BTC-USD — + beta = crypto / high-risk-appetite exposure."),
    Factor("gold", "yahoo", "GC=F", "close", 1,
           "Gold", "Gold futures (GC=F) — + beta = gold / metals & miners exposure; closes the "
           "metals coverage gap so miners read as the gold bets they are, not low-R² idiosyncratics."),
    # NB: a high-yield-credit factor (HYG) was evaluated and DROPPED — in an equity universe its
    # loaders were an incoherent low-beta mix (redundant with market + rates), i.e. it fit noise
    # rather than a clean credit dimension. Keep the observable set small and clean (overfit guardrail).
]

FACTOR_ORDER = [f.key for f in FACTORS]
FACTOR_BY_KEY = {f.key: f for f in FACTORS}

# Confidence tiers MEASURED by the Phase-0 out-of-sample stability test
# (reports/factor-exposure-phase0.md, 22 monthly rebalances). The number is the
# in-sample→next-quarter rank-persistence; `scope` says where the read is trustworthy:
#   single — reliable per stock AND aggregated  | book — only meaningful for a basket
#   low    — weak even aggregated (show as context, expect ~0 for most equity books)
# The UI uses this to style each beta (full / muted / footnoted) — honesty baked in.
FACTOR_CONFIDENCE = {
    "mkt":    {"tier": "high",   "scope": "single", "persist": 0.69},
    "size":   {"tier": "high",   "scope": "single", "persist": 0.63},
    "growth": {"tier": "high",   "scope": "single", "persist": 0.50},
    "rates":  {"tier": "medium", "scope": "single", "persist": 0.36},
    "oil":    {"tier": "medium", "scope": "book",   "persist": 0.22},   # 0.22→0.49 with book size
    "china":  {"tier": "low",    "scope": "low",    "persist": 0.19},   # flat ~0.17 even aggregated
    "usd":    {"tier": "low",    "scope": "low",    "persist": 0.11},
    "btc":    {"tier": "low",    "scope": "low",    "persist": 0.02},
    # gold (GC=F) is a clean, well-identified factor in-sample (metals/miners R²≈0.60) but has
    # not yet been through the Phase-0 out-of-sample stability test on this factor set — so it
    # reads low/untested (persist unmeasured) until that runs, rather than carrying a fabricated number.
    "gold":   {"tier": "low",    "scope": "low",    "persist": None},
}


def _cfg() -> dict:
    base = {"window_d": 252, "min_obs": 126, "min_factor_obs": 252,
            "max_abs_beta": 5.0, "top_n_idio": 12,
            "stress_window_d": 756, "stress_quantile": 0.25}
    return {**base, **(config.load().get("engine", {}).get("factor_exposure", {}) or {})}


# Common ETFs to also expose betas for — many watchlists hold these, and the model
# reads them cleanly (a holding of SPY should show market beta ~1). Only the ones we
# already cache in data/yahoo are used; the rest are skipped gracefully. Labelled so
# the client shows a readable name + an "ETF" sector tag.
ETF_NAMES = {
    "SPY": "S&P 500", "QQQ": "Nasdaq 100", "IWM": "Russell 2000", "RSP": "S&P 500 equal-wt",
    "IJH": "S&P MidCap 400", "IWD": "Russell 1000 Value", "IWF": "Russell 1000 Growth",
    "MTUM": "US Momentum", "QUAL": "US Quality", "SPHB": "S&P High Beta",
    "SPLV": "S&P Low Vol", "USMV": "US Min Vol", "SMH": "Semiconductors",
    "XLB": "Materials", "XLC": "Communication Svcs", "XLE": "Energy", "XLF": "Financials",
    "XLI": "Industrials", "XLK": "Technology", "XLP": "Consumer Staples",
    "XLRE": "Real Estate", "XLU": "Utilities", "XLV": "Health Care", "XLY": "Consumer Disc",
    "TLT": "20y+ Treasuries", "IEF": "7-10y Treasuries", "TIP": "TIPS",
    "HYG": "High-yield credit", "LQD": "IG credit", "EMB": "EM bonds",
    "FXI": "China large-cap",
}

# Crypto book — the coins themselves (BTC-USD/ETH-USD, already the `btc` FACTOR series)
# plus the spot-crypto ETFs and Coinbase equity many watchlists actually hold. Exposed
# so a holder sees a real book contribution instead of an "unmodeled" chip; tagged with
# a "Crypto" sector (not "ETF") so the client groups the sleeve honestly. These load
# btc-heavy with high idio / low equity-factor R² — correct, crypto is its own bet.
# Only the cached ones are used (GBTC is NOT cached → skipped gracefully, like the rest);
# see the module docstring on why this is clock-consistent with the existing btc factor.
CRYPTO_NAMES = {
    "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum",
    "IBIT": "iShares Bitcoin (spot)", "ETHA": "iShares Ethereum (spot)",
    "COIN": "Coinbase",
}

# Union universe read by `_etf_closes`; `compute_exposure` tags CRYPTO_NAMES → "Crypto",
# the rest → "ETF". Keys are unique across the two maps.
ETF_UNIVERSE = list(ETF_NAMES) + list(CRYPTO_NAMES)


def _etf_closes() -> pd.DataFrame:
    """Close matrix for the curated ETF universe (only those cached in data/yahoo)."""
    cols: dict[str, pd.Series] = {}
    for sym in ETF_UNIVERSE:
        df = store.read("yahoo", sym)
        if df is not None and "close" in getattr(df, "columns", []):
            cols[sym] = df["close"].astype(float)
    return pd.DataFrame(cols).sort_index() if cols else pd.DataFrame()


# --------------------------------------------------------------------------- #
# factor returns + orthogonalization
# --------------------------------------------------------------------------- #
def factor_frame(asof=None) -> pd.DataFrame:
    """Aligned daily RAW factor returns, one column per available factor key.
    Rows kept only where every present factor has a return (so the orthogonalization
    transform and the shared-design regression are well defined)."""
    cols: dict[str, pd.Series] = {}
    for f in FACTORS:
        df = store.read(f.group, f.sid)
        if df is None or f.col not in getattr(df, "columns", []):
            log.warning("factor_exposure: missing factor %s (%s/%s)", f.key, f.group, f.sid)
            continue
        r = df[f.col].astype(float).pct_change(fill_method=None) * f.sign
        cols[f.key] = r.dropna()
    if not cols:
        return pd.DataFrame()
    F = pd.DataFrame(cols)
    if asof is not None:
        F = F.loc[:pd.Timestamp(asof)]
    return F.dropna(how="any")


def orthogonalize_fit(F_win: pd.DataFrame) -> dict:
    """FIT the sequential (Gram-Schmidt) orthogonalization transform on one window.

    Returns the projection coefficients — for each factor k (in FACTOR_ORDER), the
    slope of its residual-so-far on each *already-orthogonalized* prior column p:
    `coeffs[k][p] = cov(v_k, g_p) / var(g_p)` computed exactly as the sequential peel
    encounters it. This is the fixed transform; `orthogonalize_apply` reproduces the
    same residuals on the fit window and — crucially for the stress lens — projects a
    DIFFERENT (e.g. longer) frame into the SAME orthogonal basis. Returns
    `{"order": [...], "coeffs": {k: {p: float, ...}, ...}}`."""
    order = [k for k in FACTOR_ORDER if k in F_win.columns]
    G = pd.DataFrame(index=F_win.index)
    coeffs: dict[str, dict[str, float]] = {}
    for k in order:
        v = F_win[k].astype(float)
        ck: dict[str, float] = {}
        for prior in G.columns:                          # priors are already orthogonal cols
            p = G[prior]
            var = float(p.var())
            beta = (float(v.cov(p)) / var) if var > 0 else 0.0
            ck[prior] = beta
            if beta:
                v = v - beta * p
        coeffs[k] = ck
        G[k] = v
    return {"order": order, "coeffs": coeffs}


def orthogonalize_apply(F: pd.DataFrame, transform: dict) -> pd.DataFrame:
    """APPLY a fitted transform (from `orthogonalize_fit`) to any frame with the same
    factor columns, producing the orthogonalized set in the FIXED basis.

    Peels each factor with the stored coefficients (against the priors it re-derives on
    THIS frame as it goes — identical construction to the fit, but the slopes are frozen
    from the fit window). Applying the fit-window transform back to the fit window
    reproduces `orthogonalize_factors` exactly; applying it to an extended window keeps
    every column in the shipped betas' basis (so b′·F_stress·b is meaningful)."""
    order = [k for k in transform["order"] if k in F.columns]
    coeffs = transform["coeffs"]
    G = pd.DataFrame(index=F.index)
    for k in order:
        v = F[k].astype(float)
        for prior, beta in coeffs.get(k, {}).items():
            if prior in G.columns and beta:
                v = v - beta * G[prior]
        G[k] = v
    return G


def orthogonalize_factors(F: pd.DataFrame) -> pd.DataFrame:
    """Sequential (Gram-Schmidt) orthogonalization in FACTOR_ORDER priority.

    Each factor is replaced by its residual after regressing out every higher-priority
    factor already processed. Market stays raw; 'growth' becomes QQQ⟂market; 'size'
    becomes IWM⟂{market,growth}; and so on. The result is a mutually-orthogonal factor
    set whose betas read as marginal exposures and decouple into univariate cov/var.
    Estimated over the whole supplied window (static transform) — callers pass the
    estimation window so the transform and the betas share a sample. Convenience
    fit+apply on one frame; use `orthogonalize_fit`/`orthogonalize_apply` when the
    transform must be frozen on one window and applied to another (stress lens)."""
    return orthogonalize_apply(F, orthogonalize_fit(F))


# --------------------------------------------------------------------------- #
# per-stock betas
# --------------------------------------------------------------------------- #
def _betas_on_window(R_w: pd.DataFrame, G_w: pd.DataFrame, minp: int,
                     max_abs: float) -> dict:
    """Decoupled multivariate betas on one aligned window (factors already
    orthogonal ⇒ beta_k = cov(r,g_k)/var(g_k)). Returns per-ticker beta vector +
    R² + annualized idiosyncratic vol, keeping only tickers with ≥ minp observations."""
    var = {k: float(G_w[k].var()) for k in G_w.columns}
    cover = R_w.notna().sum()
    keep = cover[cover >= minp].index
    R_w = R_w[keep]
    if R_w.empty:
        return {"betas": {}, "n": {}}

    betas: dict[str, pd.Series] = {}
    fitted = np.zeros(R_w.shape, dtype=float)
    for k in G_w.columns:
        g = G_w[k]
        if not var[k] or not np.isfinite(var[k]):
            betas[k] = pd.Series(np.nan, index=R_w.columns)
            continue
        b = R_w.apply(lambda c: c.cov(g)) / var[k]   # Series.cov drops NaN pairwise
        b = b.clip(-max_abs, max_abs)
        betas[k] = b
        fitted += np.outer(g.to_numpy(), b.to_numpy())

    resid = R_w.to_numpy() - fitted
    with np.errstate(invalid="ignore"):
        var_y = np.nanvar(R_w.to_numpy(), axis=0)
        var_e = np.nanvar(resid, axis=0)
    r2 = np.where(var_y > 0, 1.0 - var_e / var_y, np.nan)
    idio = np.sqrt(np.clip(var_e, 0, None)) * np.sqrt(TRADING_YEAR)

    out: dict[str, dict] = {}
    for i, t in enumerate(R_w.columns):
        rec = {k: (round(float(betas[k][t]), 3) if np.isfinite(betas[k][t]) else None)
               for k in G_w.columns}
        rec["r2"] = round(float(r2[i]), 3) if np.isfinite(r2[i]) else None
        rec["idio_vol"] = round(float(idio[i]), 3) if np.isfinite(idio[i]) else None
        rec["n"] = int(cover[t])
        out[str(t)] = rec
    return {"betas": out, "n": {str(t): int(cover[t]) for t in R_w.columns}}


def stock_betas(closes: pd.DataFrame, F: pd.DataFrame, *, window: int, min_obs: int,
                max_abs: float) -> dict:
    """Orthogonal multivariate factor betas for every stock in `closes`, estimated on
    the trailing `window` rows shared with the factor frame."""
    if closes is None or closes.empty or F.empty:
        return {"betas": {}, "n": {}}
    idx = F.index.intersection(closes.index)
    if len(idx) < min_obs:
        return {"betas": {}, "n": {}}
    idx = idx[-window:]
    G_w = orthogonalize_factors(F.loc[idx])
    R_w = closes.reindex(idx).pct_change(fill_method=None)
    return _betas_on_window(R_w, G_w, min_obs, max_abs)


def raw_betas(closes: pd.DataFrame, F: pd.DataFrame, *, window: int, min_obs: int,
              max_abs: float) -> dict:
    """UNIVARIATE betas to each RAW (non-orthogonal) factor — one regressor at a time.
    These over-count shared variance (don't sum them), but each is the right total
    derivative for a single-factor SHOCK and the baseline the orthogonal set improves
    on. Same shape as stock_betas()['betas'] minus r2/idio."""
    if closes is None or closes.empty or F.empty:
        return {}
    idx = F.index.intersection(closes.index)
    if len(idx) < min_obs:
        return {}
    idx = idx[-window:]
    Fw = F.loc[idx]
    R_w = closes.reindex(idx).pct_change(fill_method=None)
    cover = R_w.notna().sum()
    R_w = R_w[cover[cover >= min_obs].index]
    out: dict[str, dict] = {t: {} for t in R_w.columns}
    for k in Fw.columns:
        g = Fw[k]
        var = float(g.var())
        if not var:
            continue
        b = (R_w.apply(lambda c: c.cov(g)) / var).clip(-max_abs, max_abs)
        for t in R_w.columns:
            out[str(t)][k] = round(float(b[t]), 3) if np.isfinite(b[t]) else None
    return out


# --------------------------------------------------------------------------- #
# portfolio aggregation (also runs client-side; kept here for tests + a server demo)
# --------------------------------------------------------------------------- #
def factor_cov(F: pd.DataFrame, *, window: int) -> pd.DataFrame:
    """Annualized covariance of the ORTHOGONAL factor returns over the trailing window
    (near-diagonal by construction) — the client uses it for risk decomposition and
    shocks."""
    if F.empty:
        return pd.DataFrame()
    G = orthogonalize_factors(F.tail(window))
    return G.cov() * TRADING_YEAR


def factor_cov_stress(F: pd.DataFrame, *, fit_window: int, stress_window: int,
                      quantile: float, min_stress_rows: int = 400,
                      min_stress_days: int = 60) -> dict:
    """Stress-conditioned orthogonal factor covariance — factor co-movement re-estimated
    on the worst-quartile market days, in the SAME orthogonal basis as the shipped betas.

    The core subtlety: the transform is FIT on the trailing `fit_window` rows (the window
    `stock_betas`/`factor_cov` use) and then APPLIED — never re-fit — to the trailing
    `stress_window` rows, so `b′·F_stress·b` client-side stays in one basis. Stress days
    are rows whose RAW `mkt` return (un-orthogonalized SPY daily) is ≤ its `quantile`
    percentile over the stress window. Returns a dict:
      {"available": bool, "cov": DataFrame|None, "vol_ann": {k: float}|None,
       "window_d": int, "n_stress": int, "mkt_cut_daily": float, "quantile": float,
       "reason": str (only when unavailable)}.
    Small-sample guard: <`min_stress_rows` usable rows → shrink window to what exists
    (stamped in window_d); <`min_stress_days` stress days → available=False, no cov."""
    if F.empty or "mkt" not in F.columns:
        return {"available": False, "reason": "no factor frame / missing mkt column",
                "window_d": 0, "n_stress": 0}

    # trailing stress window (shrink to what exists — never ship a scrap-sample cov)
    F_stress = F.tail(stress_window)
    win_actual = len(F_stress)

    # fit the transform on the SHIPPED-beta window, then APPLY it to the stress window
    F_fit = F.tail(fit_window)
    transform = orthogonalize_fit(F_fit)
    G_stress = orthogonalize_apply(F_stress, transform)

    # stress days: raw (un-orthogonalized) mkt ≤ its quantile over the same window
    mkt_raw = F_stress["mkt"].astype(float)
    cut = float(mkt_raw.quantile(quantile))
    mask = (mkt_raw <= cut).to_numpy()
    n_stress = int(mask.sum())

    meta = {"window_d": int(win_actual), "n_stress": n_stress,
            "mkt_cut_daily": round(cut, 5), "quantile": quantile}

    if win_actual < min_stress_rows or n_stress < min_stress_days:
        reason = (f"insufficient stress sample "
                  f"(window {win_actual} rows, {n_stress} stress days; "
                  f"need ≥{min_stress_rows} rows and ≥{min_stress_days} stress days)")
        return {"available": False, "reason": reason, **meta}

    G_days = G_stress.loc[mask]
    cov = G_days.cov() * TRADING_YEAR
    keys = list(cov.columns)
    vol_ann = {k: round(float(np.sqrt(max(cov.loc[k, k], 0.0))), 4) for k in keys}
    return {"available": True, "cov": cov, "vol_ann": vol_ann, **meta}


def portfolio_exposure(weights: dict[str, float], betas: dict[str, dict],
                       fcov: pd.DataFrame, idio: dict[str, float] | None = None) -> dict:
    """Aggregate a weighted book into portfolio factor betas, per-factor RISK
    contribution, and a concentration read.

    `weights` ticker→weight (need not sum to 1; normalized by gross). `betas` is
    stock_betas(...)['betas']; `fcov` the orthogonal factor covariance; `idio`
    optional ticker→annualized idiosyncratic vol for the residual risk sleeve.
    Risk contribution of factor k = b_k·(Σ_f b)_k / total variance (the factors are
    orthogonal so this is ≈ b_k²·var_k); the single biggest share is the "one bet"."""
    keys = [k for k in FACTOR_ORDER if k in fcov.columns]
    held = {t: w for t, w in weights.items() if t in betas and w}
    gross = sum(abs(w) for w in held.values())
    if not held or gross <= 0 or not keys:
        return {"verdict": "unknown", "headline": "no overlapping positions with factor betas"}

    b_p = {k: sum((held[t] / gross) * (betas[t].get(k) or 0.0) for t in held) for k in keys}
    bv = np.array([b_p[k] for k in keys])
    S = fcov.loc[keys, keys].to_numpy()
    factor_var = float(bv @ S @ bv)

    idio_var = 0.0
    if idio:
        idio_var = float(sum(((held[t] / gross) ** 2) * (idio.get(t, 0.0) ** 2) for t in held))
    total_var = factor_var + idio_var
    sd = np.sqrt(max(total_var, 0.0))

    mrc = bv * (S @ bv)                                   # marginal risk per factor
    rc = {k: (float(mrc[i]) / total_var if total_var > 0 else float("nan"))
          for i, k in enumerate(keys)}
    rc["idiosyncratic"] = (idio_var / total_var) if total_var > 0 else float("nan")

    ranked = sorted(((k, v) for k, v in rc.items() if k != "idiosyncratic"),
                    key=lambda kv: -abs(kv[1]))
    top_key, top_share = ranked[0]
    hhi = float(sum(v * v for _, v in ranked))            # factor-risk concentration
    verdict = ("concentrated" if top_share >= 0.50 else
               "tilted" if top_share >= 0.33 else "balanced")
    label = FACTOR_BY_KEY.get(top_key, Factor(top_key, "", "", "", 1, top_key, "")).label
    headline = (f"{round(top_share * 100)}% of this book's factor risk is {label.upper()} "
                f"(net beta {round(b_p[top_key], 2)}). "
                + ("Several names, largely one bet." if verdict == "concentrated"
                   else "A clear primary tilt." if verdict == "tilted"
                   else "Risk is spread across factors."))
    return {
        "verdict": verdict, "headline": headline,
        "n_positions": len(held), "gross": round(gross, 4),
        "port_vol_ann": round(float(sd), 4),
        "betas": {k: round(b_p[k], 3) for k in keys},
        "risk_contrib": {k: (round(v, 3) if np.isfinite(v) else None) for k, v in rc.items()},
        "top_factor": top_key, "top_share": round(float(top_share), 3),
        "concentration_hhi": round(hhi, 3),
    }


# --------------------------------------------------------------------------- #
# live snapshot / export
# --------------------------------------------------------------------------- #
def compute_exposure(asof=None, closes: pd.DataFrame | None = None) -> dict | None:
    """Live per-ticker factor-beta export for latest.json / site/exposure/betas.json.

    Ships the orthogonal betas (exposure/risk), the raw univariate betas (shocks),
    factor metadata, and the orthogonal factor covariance so the watchlist can do all
    the portfolio aggregation client-side from the user's own position weights."""
    cfg = _cfg()
    F = factor_frame(asof=asof)
    if F.empty or len(F) < int(cfg["min_factor_obs"]):
        log.warning("factor_exposure: too little factor history (%d rows)", len(F))
        return None
    if closes is None:
        closes = _closes()
    if closes is None or closes.empty:
        log.warning("factor_exposure: no close matrix")
        return None
    if asof is not None:
        closes = closes.loc[:pd.Timestamp(asof)]

    etf = _etf_closes()                                   # add common ETFs (SPY/QQQ/sectors/…)
    if not etf.empty:
        if asof is not None:
            etf = etf.loc[:pd.Timestamp(asof)]
        closes = pd.concat([closes, etf], axis=1, sort=False)
        closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()
    etf_set = set(ETF_UNIVERSE)

    win, minp, max_abs = int(cfg["window_d"]), int(cfg["min_obs"]), float(cfg["max_abs_beta"])
    res = stock_betas(closes, F, window=win, min_obs=minp, max_abs=max_abs)
    if not res["betas"]:
        log.warning("factor_exposure: no betas estimated")
        return None
    rb = raw_betas(closes, F, window=win, min_obs=minp, max_abs=max_abs)
    fcov = factor_cov(F, window=win)
    keys = list(fcov.columns)

    # Stress lens (W1): factor co-movement re-estimated on worst-quartile market days,
    # in the SAME orthogonal basis as the shipped betas (transform fit on `win`, applied
    # to the trailing stress window). Additive + guarded — a scrap sample emits nothing.
    stress = factor_cov_stress(F, fit_window=win, stress_window=int(cfg["stress_window_d"]),
                               quantile=float(cfg["stress_quantile"]))

    ns = _names_sectors()
    betas = res["betas"]
    for t, rec in betas.items():
        if t in CRYPTO_NAMES:
            # coins + spot-crypto ETFs + Coinbase: own "Crypto" sector so the sleeve
            # groups honestly. is_etf stays False (unused by the client; the coins/COIN
            # aren't ETFs and the sector tag already carries the grouping).
            rec["name"], rec["sector"], rec["is_etf"] = CRYPTO_NAMES[t], "Crypto", False
        elif t in etf_set:
            rec["name"], rec["sector"], rec["is_etf"] = ETF_NAMES.get(t, t), "ETF", True
        else:
            rec["name"], rec["sector"] = ns.get(t, (t, "—"))
            rec["is_etf"] = False
        rec["raw"] = rb.get(t, {})

    most_idio = sorted((t for t in betas if betas[t].get("idio_vol") is not None),
                       key=lambda t: -betas[t]["idio_vol"])[:int(cfg["top_n_idio"])]

    out = {
        "as_of": str(F.index.max().date()),
        "window_d": win, "n": len(betas), "note": NOTE,
        "factors": [{"key": f.key, "label": f.label, "note": f.note,
                     **FACTOR_CONFIDENCE.get(f.key, {})}
                    for f in FACTORS if f.key in keys],
        "factor_vol_ann": {k: round(float(np.sqrt(max(fcov.loc[k, k], 0.0))), 4) for k in keys},
        "factor_cov": {a: {b: round(float(fcov.loc[a, b]), 6) for b in keys} for a in keys},
        "betas": betas,
        "most_idiosyncratic": [{"ticker": t, "name": betas[t]["name"],
                                "idio_vol": betas[t]["idio_vol"], "r2": betas[t]["r2"]}
                               for t in most_idio],
    }

    # additive stress-lens emit — see factor_cov_stress(). Shares `keys` (== factor_cov
    # ordering) so the client reads both covariances in one basis. Guarded: on a scrap
    # sample only stress_meta (available:false) ships, no covariance.
    if stress.get("available"):
        scov = stress["cov"]
        skeys = [k for k in keys if k in scov.columns]
        out["factor_cov_stress"] = {a: {b: round(float(scov.loc[a, b]), 6) for b in skeys}
                                    for a in skeys}
        out["factor_vol_stress_ann"] = {k: stress["vol_ann"][k] for k in skeys}
        out["stress_meta"] = {
            "available": True, "window_d": stress["window_d"], "quantile": stress["quantile"],
            "n_stress": stress["n_stress"], "mkt_cut_daily": stress["mkt_cut_daily"],
            "note": ("factor co-movement re-estimated on worst-quartile market days; "
                     "idiosyncratic vol estimated on all days"),
        }
    else:
        out["stress_meta"] = {"available": False, "reason": stress.get("reason", "unavailable")}
    return out


def snapshot() -> dict:
    """latest.json["factor_exposure"] entry — degrades to verdict='unknown'."""
    out = compute_exposure()
    if out is None:
        return {"verdict": "unknown", "headline": "insufficient factor or price history"}
    return out
