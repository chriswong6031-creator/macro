"""Breadth-honesty signal factory — roadmap Phase 4.

The Fundamental Law lever is breadth-manufacturing, not single-factor polish: a
handful of DECORRELATED, leak-free legs combined under a multiple-testing gate.
This builds a small set of NEW fundamental-TREND / earnings-quality legs from the
line items we ALREADY collect in the point-in-time EDGAR panel, plus two
filing-FLOW legs off the Form-4 and 8-K PIT panels — each distinct from the
value/quality/profitability/investment/payout/low-vol zoo:

  gross_margin_trend    Δ(gross_profit/revenue)      YoY   — improving pricing power
  asset_turnover_trend  Δ(revenue/assets)            YoY   — improving capital efficiency
  cash_conversion       cfo / |ni|                   level — earnings backed by cash
  net_issuance         −Δ(shares)                    YoY   — buyback breadth (dilution = bad)
  deleveraging         −Δ(debt_lt/assets)            YoY   — balance-sheet repair
  form4_cluster_breadth distinct Form-4 BUYERS / 90d  count — broad insider conviction
  eightk_velocity       material-8K count vs own rate z     — information-flow surge

The last two were deliberately deferred in the first cut because they need their
own point-in-time filing panels; this wires them in leak-free (count only filings
whose filing_date ≤ asof). form4_cluster_breadth is the distinct-buyer CLUSTER
count over a trailing window (the same construction as engine.equity_factors'
insider block), gently size-normalised by log book assets so a multi-insider buy
at a small/mid-cap isn't drowned by a big board. eightk_velocity standardises a
name's recent material-8K count against its OWN prior-year rate (a Poisson surprise
z) — an information-flow proxy, standalone and NOT directional.

Legs the roadmap names but we still DON'T build here, with the honest reason:
  * NOA / cash-conversion-accrual decomposition — needs cash & total-liabilities tags
    absent from the panel (only in the survivor-only statements cache);
  * R&D/sales — tag not collected; short-interest delta — no point-in-time history.

EVERYTHING here is leak-free: fundamental legs at `asof` use only fiscal years whose
`asof_date` (true filed date) is on or before `asof`, the trend's prior year is older
still, and the filing-flow legs count only filings whose filing_date ≤ asof.
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
        "net_issuance", "deleveraging",
        "form4_cluster_breadth", "eightk_velocity"]

# trailing-window defaults for the two filing-flow legs (calendar days)
FORM4_WINDOW_D = 90
EIGHTK_WINDOW_D = 90
EIGHTK_BASELINE_D = 365


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.where(b.abs() > 0)


def _form4_cluster_breadth(insider_panel, asof, index, size, window_days) -> pd.Series:
    """Distinct Form-4 OPEN-MARKET BUYERS (code ``P``) per ticker over the trailing
    ``window_days`` ending at ``asof``, counting ONLY filings with ``filing_date ≤ asof``
    (leak guard — a not-yet-filed buy can never enter), gently size-normalised by log
    book assets so a multi-insider cluster at a small/mid-cap isn't drowned by a big
    board (the live insider factor uses market cap; assets is the leak-free PIT size
    proxy available in this offline grid). NaN where no buyer activity is knowable."""
    nan = pd.Series(np.nan, index=index, name="form4_cluster_breadth")
    if insider_panel is None or len(insider_panel) == 0:
        return nan
    fd = pd.to_datetime(insider_panel["filing_date"], errors="coerce")
    lo = asof - pd.Timedelta(days=window_days)
    win = insider_panel[(fd <= asof) & (fd > lo) & (insider_panel["code"] == "P")]
    if win.empty:
        return nan
    raw = win.groupby("ticker")["rptownercik"].nunique().reindex(index)
    sz = pd.to_numeric(size, errors="coerce").reindex(index) if size is not None \
        else pd.Series(np.nan, index=index)
    denom = np.log1p(sz.where(sz > 0))
    norm = raw / denom
    return norm.where(denom.notna(), raw).rename("form4_cluster_breadth")   # raw if no size


def _eightk_velocity(eightk_panel, asof, index, window_days, baseline_days) -> pd.Series:
    """Material-8K filing velocity: the count in the trailing ``window_days`` ending at
    ``asof`` standardised against the name's OWN prior-``baseline_days`` rate as a
    Poisson surprise z, using ONLY filings with ``filing_date ≤ asof`` (leak guard).
    The baseline window sits ENTIRELY before the recent window, so a surge can't seed
    its own baseline. An information-FLOW proxy — standalone, NOT directional. NaN for
    names absent from the 8-K panel as of ``asof`` (uncovered); 0 for covered-quiet."""
    nan = pd.Series(np.nan, index=index, name="eightk_velocity")
    if eightk_panel is None or len(eightk_panel) == 0:
        return nan
    fd = pd.to_datetime(eightk_panel["filing_date"], errors="coerce")
    df = pd.DataFrame({"ticker": np.asarray(eightk_panel["ticker"]), "d": np.asarray(fd)})
    df = df[df["d"].notna() & (df["d"] <= asof)]
    if df.empty:
        return nan
    rec_lo = asof - pd.Timedelta(days=window_days)
    base_lo = rec_lo - pd.Timedelta(days=baseline_days)
    covered = pd.Index(sorted(set(df["ticker"])))
    rec = df[df["d"] > rec_lo].groupby("ticker").size().reindex(covered).fillna(0.0)
    bas = df[(df["d"] > base_lo) & (df["d"] <= rec_lo)].groupby("ticker").size() \
        .reindex(covered).fillna(0.0)
    lam = bas * (window_days / baseline_days)            # expected count in a recent window
    vel = (rec - lam) / np.sqrt(lam + 1.0)               # Poisson-standardised surprise
    return vel.reindex(index).rename("eightk_velocity")


def build_legs(panel: pd.DataFrame, asof, *, insider_panel=None, eightk_panel=None,
               form4_window_days=FORM4_WINDOW_D, eightk_window_days=EIGHTK_WINDOW_D,
               eightk_baseline_days=EIGHTK_BASELINE_D) -> pd.DataFrame:
    """Leak-free [ticker x leg] frame of the factory legs knowable at `asof`.

    Per ticker we take the two most recent fiscal years whose `asof_date` ≤ `asof`
    (the latest knowable report and its predecessor); TREND legs need both, LEVEL
    legs need only the latest. Tickers with a single knowable year get NaN trends
    (no look-ahead borrowing of a not-yet-filed prior). The two filing-flow legs
    (form4_cluster_breadth, eightk_velocity) are computed only when their PIT panels
    are supplied — each counting ONLY filings with filing_date ≤ asof — and are NaN
    otherwise. Returns RAW leg values on the fundamentals universe."""
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
    # FILING-FLOW legs (leak-free trailing windows off the Form-4 / 8-K PIT panels),
    # reindexed onto the fundamentals universe. size-normalise the buyer cluster by
    # the latest knowable book assets (already asof-filtered in `last`).
    size = pd.to_numeric(last["assets"], errors="coerce") if "assets" in last else None
    out["form4_cluster_breadth"] = _form4_cluster_breadth(
        insider_panel, asof, out.index, size, form4_window_days)
    out["eightk_velocity"] = _eightk_velocity(
        eightk_panel, asof, out.index, eightk_window_days, eightk_baseline_days)
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
