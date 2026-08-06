"""Multi-window, multi-FACTOR residual momentum — the generalized BHM construction.

`engine.residual_alpha` already ships the validated two-leg form (market + sector,
sector-neutral residual info-ratio, ONE 12-1 window) and is wired into the US leaders
board. This module is the ADDITIVE research/diagnostic generalization it could not be
without re-measuring a live ranker:

    r_i = a_i + b_m*m + b_s*s~ + SUM_f b_f*F~_f + e_i

adding the size / value / quality / low-volatility legs (`F`) that the shipped engine
omits, and computing the residual over a TABLE of formation windows instead of one.

Why the orthogonal basis matters (and why there is no per-stock matrix solve): the
regressors are Gram-Schmidt orthogonalized IN ORDER inside each sector block —
market first, then that sector's peer return beyond the market, then each factor leg
beyond both. For a mutually orthogonal basis the multivariate OLS slopes EQUAL the
univariate slopes, so every beta stays a cheap rolling cov/var. This is the same trick
`residual_alpha` uses for sector-vs-market, extended to K legs.

Causality: every beta is a trailing rolling estimate SHIFTED ONE DAY, so the residual
at bar t uses only information through t-1 for the loadings and bar t for the returns.
Orthogonalization uses the same lagged rolling betas, so the basis is causal too —
which makes the legs orthogonal only APPROXIMATELY (an exact in-window Gram-Schmidt
would peek at the current window's covariance). That approximation is deliberate and
inherited from the validated harness; `tests/test_residual_momentum.py` pins that the
residual carries no look-ahead.

Windows (`WINDOWS`) are the five named in the build request. Note `w12_1` and
`w12_ex21` are the SAME construction — "12-1 months" and "12 months excluding the last
21 days" are two names for form=252/skip=21 — so the effective distinct set is FOUR.
Both keys are kept so the request's vocabulary round-trips; `distinct_windows()`
returns the de-duplicated set the scorecard actually tests, and the duplication is
printed rather than silently collapsed.

Honest status: DIAGNOSTIC / research tier. The shipped 12-1 residual leg was measured
at "a modest, regime-decayed edge — context, not a buy list"
(research/RESIDUAL_ALPHA_MOMENTUM.md); nothing here has cleared a promotion gate, and
no output of this module ranks, sizes, or gates a live board.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.equity_factors import _closes, _names_sectors, _winsor_z
from lib import config, store

log = logging.getLogger(__name__)

# name -> (formation days, skip-recent days). See the module docstring on w12_1/w12_ex21.
WINDOWS: dict[str, tuple[int, int]] = {
    "w3_1": (63, 21),        # 3-1 months
    "w6_1": (126, 21),       # 6-1 months
    "w12_1": (252, 21),      # 12-1 months
    "w6_ex5": (126, 5),      # 6 months excluding the last 5 days
    "w12_ex21": (252, 21),   # 12 months excluding the last 21 days == w12_1
}

WINDOW_LABELS = {
    "w3_1": "3-1 months", "w6_1": "6-1 months", "w12_1": "12-1 months",
    "w6_ex5": "6 months ex-last-5d", "w12_ex21": "12 months ex-last-21d",
}

# Factor legs added on top of market+sector. `size` is built here from market cap
# (small minus large); the rest reuse the shipped cross-sections in engine.equity_factors.
FACTOR_LEGS = ("size", "value", "quality", "low_vol")

_LEGS_REL = ("breadth", "_factor_legs.parquet")


def _defaults() -> dict:
    cfg = config.load().get("engine_residual_momentum", {})
    return {"win": int(cfg.get("beta_win", 252)),
            "shrink": float(cfg.get("shrink", 0.66)),
            "min_names": int(cfg.get("min_names", 20)),
            "cap": float(cfg.get("winsor_z", 3.0)),
            "top_n": int(cfg.get("top_n", 15))}


def distinct_windows(windows: dict | None = None) -> dict[str, tuple[int, int]]:
    """The de-duplicated window set, keeping the FIRST key for each (form, skip) pair.
    `w12_ex21` collapses onto `w12_1`; returning the reduced map is what stops the IC
    scorecard from counting one construction twice in its multiple-testing correction."""
    src = WINDOWS if windows is None else windows
    seen: dict[tuple[int, int], str] = {}
    for name, spec in src.items():
        seen.setdefault(tuple(spec), name)
    return {name: spec for spec, name in seen.items()}


def duplicate_windows(windows: dict | None = None) -> dict[str, str]:
    """{duplicate key: the key it duplicates} — printed by the harness, never hidden."""
    src = WINDOWS if windows is None else windows
    first: dict[tuple[int, int], str] = {}
    dupes: dict[str, str] = {}
    for name, spec in src.items():
        key = tuple(spec)
        if key in first:
            dupes[name] = first[key]
        else:
            first[key] = name
    return dupes


def _shrink(beta: pd.DataFrame, w: float) -> pd.DataFrame:
    """Vasicek-lite: w*raw + (1-w)*cross-sectional mean that day (w>=1 -> no-op)."""
    if w is None or w >= 1.0:
        return beta
    return beta.mul(w).add(beta.mean(axis=1).mul(1.0 - w), axis=0)


def _causal_beta(y, x, win: int, minp: int):
    """Rolling cov(y,x)/var(x) lagged one day — prior-window data only."""
    return (y.rolling(win, min_periods=minp).cov(x)
            .div(x.rolling(win, min_periods=minp).var(), axis=0)).shift(1)


def orthogonal_basis(legs: list[pd.Series], win: int, minp: int) -> list[pd.Series]:
    """Gram-Schmidt the leg list IN ORDER using causal rolling betas: leg k has every
    earlier leg's projection removed, so the returned basis is (approximately) mutually
    orthogonal and univariate betas against it equal multivariate OLS slopes.

    Order is load-bearing and intentional — market absorbs first, then sector beyond
    market, then each factor beyond both. A factor leg that is mostly market beta
    therefore contributes almost nothing rather than stealing the market's variance."""
    basis: list[pd.Series] = []
    for leg in legs:
        v = leg.astype(float)
        for b in basis:
            v = v - _causal_beta(v, b, win, minp) * b
        basis.append(v)
    return basis


def residuals(closes: pd.DataFrame, market: pd.Series, tkr_sector: dict,
              win: int, shrink: float,
              factor_legs: dict[str, pd.Series] | None = None) -> pd.DataFrame:
    """Per-stock causal residual e_i with market, sector and (optional) factor legs
    removed. With `factor_legs=None`/empty this reduces EXACTLY to the shipped
    `residual_alpha.residuals` two-leg construction, which is what makes the deep
    panel (no factor history) comparable to the live one."""
    minp = max(win // 2, 15)
    R = closes.pct_change(fill_method=None)
    m = market.reindex(R.index).astype(float)
    legs = {k: v.reindex(R.index).astype(float)
            for k, v in (factor_legs or {}).items() if v is not None}

    beta_m = _shrink(_causal_beta(R, m, win, minp), shrink)
    mkt_comp = beta_m.mul(m, axis=0)

    eps = pd.DataFrame(index=R.index, columns=R.columns, dtype=float)
    for sec in sorted({tkr_sector.get(t, "—") for t in R.columns}):
        cols = [t for t in R.columns if tkr_sector.get(t, "—") == sec]
        if not cols:
            continue
        s_raw = R[cols].mean(axis=1)                       # equal-weight peer basket
        # basis order: market, sector-beyond-market, then each factor beyond both
        ordered = [m, s_raw] + [legs[k] for k in FACTOR_LEGS if k in legs]
        basis = orthogonal_basis(ordered, win, minp)[1:]   # drop market (removed below)
        block = R[cols] - mkt_comp[cols]
        for b in basis:
            # Beta of the RAW return on each basis vector, NOT of the partially-stripped
            # block. For a mutually orthogonal basis these are the same quantity, and the
            # raw form is the one the shipped engine uses — regressing the running
            # remainder instead would compound the small non-orthogonality left by the
            # lagged rolling betas and silently drift away from the validated leg.
            beta_b = _shrink(_causal_beta(R[cols], b, win, minp), shrink)
            block = block - beta_b.mul(b, axis=0)
        eps[cols] = block
    return eps


def window_signals(R: pd.DataFrame, eps: pd.DataFrame, form: int, skip: int) -> dict:
    """The three per-window cross-sections as date x ticker matrices.

    `mom_res` is the build request's literal SUM of residuals over [t-form, t-skip];
    `ir_res` divides by the residual's own dispersion (the shipped headline — a
    consistency-scaled version of the same window); `mom_tot` is the plain
    total-return control the residual must beat to have earned its complexity."""
    mp = max(form // 2, 10)
    e = eps.shift(skip).rolling(form, min_periods=mp)
    return {
        "mom_res": e.sum(),
        "ir_res": e.mean() / e.std().replace(0, np.nan),
        "mom_tot": R.shift(skip).rolling(form, min_periods=mp).sum(),
    }


# --------------------------------------------------------------------------- #
# Factor legs (F). Built PIT from the shipped factor cross-sections: at each
# month-end the factor rank is rebuilt as it was knowable then, and the leg's daily
# return is the equal-weight top-quintile minus bottom-quintile spread held to the
# next month-end. `size` is small-minus-large on market cap.
#
# HONEST CEILING (inherited from engine/factor_series.py): free fundamentals are
# ANNUAL, so value/quality ranks refresh ~once a year per name and the usable history
# is only as long as the live price cache (~3y). On the deep panel these legs do not
# exist at all — `factor_legs()` returns {} and the residual degrades to market+sector
# rather than fabricating a factor history.
# --------------------------------------------------------------------------- #
def _ls_spread(rets: pd.DataFrame, z: pd.Series, hold: pd.DatetimeIndex,
               min_side: int = 10) -> pd.Series | None:
    """Equal-weight Q5-Q1 daily return over `hold`, or None if either side is thin."""
    z = pd.to_numeric(z, errors="coerce").dropna()
    if len(z) < 100:
        return None
    hi = [c for c in z[z >= z.quantile(0.8)].index if c in rets.columns]
    lo = [c for c in z[z <= z.quantile(0.2)].index if c in rets.columns]
    if len(hi) < min_side or len(lo) < min_side:
        return None
    return rets.loc[hold, hi].mean(axis=1) - rets.loc[hold, lo].mean(axis=1)


def factor_legs(closes: pd.DataFrame, *, universe: str = "broad",
                use_cache: bool = True) -> dict[str, pd.Series]:
    """Daily L/S return series for `FACTOR_LEGS`, PIT per month-end. Returns {} when
    the factor cross-section is unavailable (deep panel, missing fundamentals) — an
    ABSENT leg is reported as absent, never imputed to zero, because a zero leg would
    read as 'this factor had no return' rather than 'we could not measure it'."""
    from engine.equity_factors import compute_factors  # local: heavy import chain

    cache = config.data_dir().joinpath(*_LEGS_REL)
    if use_cache and cache.exists():
        try:
            cached = pd.read_parquet(cache)
            cached.index = pd.to_datetime(cached.index)
            keep = cached.reindex(closes.index)
            live = {c: keep[c] for c in keep.columns if keep[c].notna().sum() > 60}
            if live:
                log.info("residual_momentum: factor legs from cache (%s)", ", ".join(sorted(live)))
                return live
        except Exception as e:  # noqa: BLE001 — a bad cache must never be fatal
            log.warning("residual_momentum: unreadable factor-leg cache (%s)", e)

    rets = closes.pct_change(fill_method=None)
    idx = closes.index
    month_ends = [idx[idx <= d][-1] for d in pd.date_range(idx.min(), idx.max(), freq="ME")
                  if len(idx[idx <= d])]
    month_ends = sorted(set(month_ends))
    if len(month_ends) < 6:
        log.warning("residual_momentum: only %d month-ends — no factor legs", len(month_ends))
        return {}

    out = {f: pd.Series(np.nan, index=idx, dtype=float) for f in FACTOR_LEGS}
    for i, d in enumerate(month_ends):
        try:
            fac = compute_factors(asof=d, universe=universe)
        except Exception as e:  # noqa: BLE001
            log.warning("residual_momentum: compute_factors(%s) failed (%s)", d.date(), e)
            continue
        if not fac or not fac.get("table"):
            continue
        t = pd.DataFrame(fac["table"]).set_index("ticker")
        nxt = month_ends[i + 1] if i + 1 < len(month_ends) else idx[-1]
        hold = idx[(idx > d) & (idx <= nxt)]
        if not len(hold):
            continue
        for f in FACTOR_LEGS:
            # size = SMALL minus large, so a positive leg return means small-caps led
            if f == "size":
                mc = pd.to_numeric(t.get("mktcap_bn"), errors="coerce") if "mktcap_bn" in t else None
                if mc is None:
                    continue
                z = -mc.dropna()
            elif f in t.columns:
                z = t[f]
            else:
                continue
            sp = _ls_spread(rets, z, hold)
            if sp is not None:
                out[f].loc[hold] = sp

    live = {f: s for f, s in out.items() if s.notna().sum() > 60}
    absent = [f for f in FACTOR_LEGS if f not in live]
    if absent:
        log.warning("residual_momentum: factor legs ABSENT (not zeroed): %s", ", ".join(absent))
    if live:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(live).to_parquet(cache)
        except Exception as e:  # noqa: BLE001
            log.warning("residual_momentum: could not cache factor legs (%s)", e)
    return live


def _f(x, nd: int = 3):
    return round(float(x), nd) if x is not None and np.isfinite(x) else None


def compute_residual_momentum(closes: pd.DataFrame | None = None,
                              market: pd.Series | None = None,
                              tkr_sector: dict | None = None, *, asof=None,
                              win=None, shrink=None, min_names=None, top_n=None,
                              windows: dict | None = None,
                              legs: dict[str, pd.Series] | None = None,
                              with_factor_legs: bool = True) -> dict | None:
    """Live cross-section of residual momentum across every DISTINCT window.

    Returns a JSON-able dict: per-window sector-neutral z of both constructions plus
    the total-momentum control, the legs that were actually live, and the duplicate
    windows that collapsed. None when the panel is too thin to score."""
    d_ = _defaults()
    win = d_["win"] if win is None else win
    shrink = d_["shrink"] if shrink is None else shrink
    min_names = d_["min_names"] if min_names is None else min_names
    top_n = d_["top_n"] if top_n is None else top_n
    cap = d_["cap"]

    injected = closes is not None
    if closes is None:
        closes = _closes()
    if closes is None or closes.empty:
        log.warning("residual_momentum: no close matrix")
        return None
    if asof is not None:
        closes = closes.loc[:pd.Timestamp(asof)]
    if market is None:
        spy = store.read("yahoo", "SPY")
        if spy is None or "close" not in spy.columns:
            log.warning("residual_momentum: no SPY market series")
            return None
        market = spy["close"].pct_change(fill_method=None)
        if asof is not None:
            market = market.loc[:pd.Timestamp(asof)]
    if tkr_sector is None:
        ns = _names_sectors()
        tkr_sector = {t: ns.get(t, (t, "—"))[1] for t in closes.columns}
    else:
        ns = {t: (t, tkr_sector.get(t, "—")) for t in closes.columns}

    if legs is None:
        legs = factor_legs(closes) if (with_factor_legs and not injected) else {}

    R = closes.pct_change(fill_method=None)
    eps = residuals(closes, market, tkr_sector, win, shrink, legs)
    sec = pd.Series({t: tkr_sector.get(t, "—") for t in R.columns})

    wins = distinct_windows(windows)
    per_window: dict[str, dict] = {}
    frames: dict[str, pd.Series] = {}
    for name, (form, skip) in wins.items():
        sigs = window_signals(R, eps, form, skip)
        block: dict[str, dict] = {}
        for sig_name, mat in sigs.items():
            row = mat.iloc[-1]
            row = row[row.notna() & (sec.reindex(row.index) != "—")]
            if len(row) < min_names:
                continue
            s = sec.reindex(row.index)
            sn = row - row.groupby(s).transform("mean")     # sector-neutral
            z = _winsor_z(sn, cap).dropna()
            if z.empty:
                continue
            frames[f"{name}|{sig_name}"] = z
            order = z.sort_values(ascending=False)
            block[sig_name] = {
                "n": int(len(z)),
                "leaders": [{"ticker": t, "name": ns.get(t, (t, "—"))[0],
                             "sector": tkr_sector.get(t, "—"), "z": _f(z[t], 2)}
                            for t in order.head(top_n).index],
            }
        if block:
            per_window[name] = {"form": form, "skip": skip,
                                "label": WINDOW_LABELS.get(name, name), **block}

    if not per_window:
        log.warning("residual_momentum: no window produced a scorable cross-section")
        return None

    # cross-window agreement: how much of the "winner" verdict is window choice?
    keys = sorted(k for k in frames if k.endswith("|mom_res"))
    corr = None
    if len(keys) > 1:
        wide = pd.DataFrame({k.split("|")[0]: frames[k] for k in keys}).dropna()
        if len(wide) >= 20:
            corr = {a: {b: _f(wide[a].corr(wide[b], method="spearman"), 2)
                        for b in wide.columns} for a in wide.columns}

    return {"as_of": str(R.index.max().date()), "n": int(R.shape[1]),
            "windows": per_window,
            "window_rank_corr": corr,
            "factor_legs_live": sorted(legs),
            "factor_legs_absent": [f for f in FACTOR_LEGS if f not in legs],
            "duplicate_windows": duplicate_windows(windows),
            "beta_win": win, "shrink": shrink}
