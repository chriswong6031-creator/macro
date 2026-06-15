"""Per-stock commodity / FX factor betas for the TSX analyzer — the Canada signature.

The S&P/TSX Composite is ~70% Energy + Materials + Financials, so the dimension that
actually separates TSX names is their sensitivity to oil, gold and the loonie. For each
stock we regress its daily returns on the commodity/FX factor returns WHILE controlling
for the broad market (orthogonal betas, the engine/factor_orthogonal.py approach): an
energy name's residual oil-beta is high and positive, a bank's is ~0, a gold miner loads
on gold. The "primary driver" is the largest-magnitude commodity/FX leg.

Inputs are already on hand: the per-stock close panel (canada_search/breadth) and the
macro factor levels canada_overlay.factor_series() already builds (oil=CL=F, gold=GC=F,
usdcad=USDCAD=X, spy=market control). DISPLAY-ONLY exposure context — a beta is a
descriptive sensitivity, not a forecast or an alpha.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger("canada_factor_beta")

# the Canada-relevant trio (commodity + FX), regressed orthogonally to the market
LEGS = ["oil", "gold", "usdcad"]
LEG_LABELS = {"oil": ("Oil", "原油"), "gold": ("Gold", "黄金"), "usdcad": ("CAD", "加元")}
# a leg is the "primary driver" only when its |beta| clears this (avoid labelling noise)
_PRIMARY_MIN = 0.10


def _returns(s: pd.Series) -> pd.Series:
    return s.dropna().pct_change(fill_method=None)


def _factor_frame(factor_series: dict[str, pd.Series], market: pd.Series | None) -> pd.DataFrame | None:
    """Aligned daily-return frame [market, oil, gold, usdcad]. usdcad is flipped to CAD
    strength (a rising loonie) so a positive CAD-beta reads intuitively. None if thin."""
    cols: dict[str, pd.Series] = {}
    mkt = market if market is not None else factor_series.get("spy")
    if mkt is None:
        return None
    cols["mkt"] = _returns(mkt)
    for leg in LEGS:
        s = factor_series.get(leg)
        if s is None:
            continue
        r = _returns(s)
        cols[leg] = (-r if leg == "usdcad" else r)   # USDCAD down = CAD up
    F = pd.concat(cols, axis=1).dropna()
    return F if not F.empty and "mkt" in F.columns else None


def compute_betas(closes: pd.DataFrame, factor_series: dict[str, pd.Series],
                  market: pd.Series | None = None, window: int = 504,
                  min_obs: int = 180) -> dict[str, dict]:
    """{ticker: {oil, gold, cad, r2, n, primary, primary_label/_zh}} — market-controlled
    factor betas over the trailing `window` sessions. Best-effort: a name with too little
    overlap is skipped; never raises."""
    F = _factor_frame(factor_series, market)
    if F is None or len(F) < min_obs:
        log.warning("canada factor beta: factor frame too thin")
        return {}
    legs = [c for c in LEGS if c in F.columns]
    if not legs:
        return {}
    out: dict[str, dict] = {}
    for t in closes.columns:
        y_full = _returns(closes[t])
        df = pd.concat([y_full.rename("y"), F], axis=1, join="inner").dropna()
        if len(df) > window:
            df = df.iloc[-window:]
        if len(df) < min_obs:
            continue
        y = df["y"].to_numpy()
        # design matrix: intercept + market + the commodity/FX legs (orthogonalised by
        # including the market so the legs carry the RESIDUAL sensitivity)
        X = np.column_stack([np.ones(len(df)), df["mkt"].to_numpy(),
                             *[df[l].to_numpy() for l in legs]])
        try:
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
            resid = y - X @ coef
            ss_tot = float(((y - y.mean()) ** 2).sum())
            r2 = 1.0 - float((resid ** 2).sum()) / ss_tot if ss_tot > 0 else None
        except Exception:  # noqa: BLE001
            continue
        betas = {l: round(float(coef[2 + i]), 3) for i, l in enumerate(legs)}
        # primary driver = largest |beta| that clears the noise floor
        prim = max(betas, key=lambda k: abs(betas[k]))
        primary = prim if abs(betas[prim]) >= _PRIMARY_MIN else None
        rec = {"oil": betas.get("oil"), "gold": betas.get("gold"), "cad": betas.get("usdcad"),
               "r2": round(r2, 2) if r2 is not None else None, "n": int(len(df))}
        if primary:
            en, zh = LEG_LABELS[primary]
            rec["primary"], rec["primary_label"], rec["primary_label_zh"] = primary, en, zh
        out[t] = rec
    log.info("canada factor beta: %d names", len(out))
    return out
