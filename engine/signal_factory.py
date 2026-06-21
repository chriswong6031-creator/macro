"""Breadth-honesty signal factory — roadmap Phase 4.

The Fundamental Law lever is breadth-manufacturing, not single-factor polish: a
handful of DECORRELATED, leak-free legs combined under a multiple-testing gate.
This builds a small set of NEW fundamental-TREND / earnings-quality legs from the
line items we ALREADY collect in the point-in-time EDGAR panel (no new data), each
distinct from the value/quality/profitability/investment/payout/low-vol zoo:

  gross_margin_trend   Δ(gross_profit/revenue)      YoY  — improving pricing power
  asset_turnover_trend Δ(revenue/assets)            YoY  — improving capital efficiency
  cash_conversion      cfo / |ni|                   level — earnings backed by cash
  net_issuance        −Δ(shares)                    YoY  — buyback breadth (dilution = bad)
  deleveraging        −Δ(debt_lt/assets)            YoY  — balance-sheet repair

Legs the roadmap names but we DON'T build here, with the honest reason:
  * NOA / cash-conversion-accrual decomposition — needs cash & total-liabilities tags
    absent from the panel (only in the survivor-only statements cache);
  * Form-4 cluster breadth + 8-K velocity — real, but they need their own PIT panels
    wired in before they can be IC-tested leak-free (a later add);
  * R&D/sales — tag not collected; short-interest delta — no point-in-time history.

EVERYTHING here is leak-free: legs at `asof` use only fiscal years whose `asof_date`
(true filed date) is on or before `asof`, and the trend's prior year is older still.
The accompanying harness (scripts/signal_factory.py) FDR-gates the legs, drops VIF≥5,
logs the trial count, and combines survivors by inverse-correlation shrinkage —
framed as a falsifiable, decorrelated CONTEXT score, never as alpha (the free-data
realized-IR ceiling is ~0.3–0.4).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# the leg menu (raw, higher = more attractive). The harness z/ranks them.
LEGS = ["gross_margin_trend", "asset_turnover_trend", "cash_conversion",
        "net_issuance", "deleveraging"]


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.where(b.abs() > 0)


def build_legs(panel: pd.DataFrame, asof) -> pd.DataFrame:
    """Leak-free [ticker x leg] frame of the factory legs knowable at `asof`.

    Per ticker we take the two most recent fiscal years whose `asof_date` ≤ `asof`
    (the latest knowable report and its predecessor); TREND legs need both, LEVEL
    legs need only the latest. Tickers with a single knowable year get NaN trends
    (no look-ahead borrowing of a not-yet-filed prior). Returns RAW leg values."""
    asof = pd.Timestamp(asof)
    sub = panel[panel["asof_date"] <= asof].sort_values(["ticker", "fy"])
    if sub.empty:
        return pd.DataFrame(columns=LEGS)
    last = sub.groupby("ticker").tail(1).set_index("ticker")
    pair = sub.groupby("ticker").tail(2)
    prev = pair.groupby("ticker").head(1).set_index("ticker")   # earlier of the last two
    prev = prev.reindex(last.index)
    has_prior = (prev["fy"] < last["fy"]).fillna(False)         # a genuine prior year exists

    def lvl(df, num, den):
        return _safe_div(pd.to_numeric(df[num], errors="coerce"),
                         pd.to_numeric(df[den], errors="coerce"))

    out = pd.DataFrame(index=last.index)
    # TREND legs (current ratio − prior ratio), masked where no prior year
    gm = lvl(last, "gross_profit", "revenue") - lvl(prev, "gross_profit", "revenue")
    at = lvl(last, "revenue", "assets") - lvl(prev, "revenue", "assets")
    lev = lvl(last, "debt_lt", "assets") - lvl(prev, "debt_lt", "assets")
    sh_last = pd.to_numeric(last["shares"], errors="coerce")
    sh_prev = pd.to_numeric(prev["shares"], errors="coerce")
    issuance = _safe_div(sh_last, sh_prev) - 1.0
    out["gross_margin_trend"] = gm.where(has_prior)
    out["asset_turnover_trend"] = at.where(has_prior)
    out["deleveraging"] = (-lev).where(has_prior)
    out["net_issuance"] = (-issuance).where(has_prior)
    # LEVEL leg: cash conversion (CFO backing reported earnings)
    out["cash_conversion"] = _safe_div(pd.to_numeric(last["cfo"], errors="coerce"),
                                       pd.to_numeric(last["ni"], errors="coerce").abs())
    return out[LEGS]


def inverse_correlation_weights(z: pd.DataFrame, shrink: float = 0.5) -> dict:
    """Long-only inverse-correlation shrinkage weights over the survivor legs: each
    leg is down-weighted by how correlated it is with the others, then blended toward
    equal-weight by `shrink` (∈[0,1], 1 = pure equal-weight). Redundant (high-VIF)
    legs that slip through get less weight; near-independent legs get more. Negative
    raw weights are clipped to 0 before renormalizing (no shorting a context leg)."""
    cols = list(z.columns)
    if not cols:
        return {}
    eq = {c: 1.0 / len(cols) for c in cols}
    d = z.dropna()
    if len(d) < 30 or len(cols) < 2:
        return eq
    C = np.corrcoef(d.to_numpy(float), rowvar=False)
    inv_abs = 1.0 / np.clip(np.abs(C).sum(axis=1), 1e-9, None)   # 1 / total |corr|
    w = np.clip(inv_abs, 0, None)
    w = w / w.sum() if w.sum() > 0 else np.full(len(cols), 1.0 / len(cols))
    blended = (1.0 - shrink) * w + shrink * (1.0 / len(cols))
    blended = blended / blended.sum()
    return {c: float(blended[i]) for i, c in enumerate(cols)}
