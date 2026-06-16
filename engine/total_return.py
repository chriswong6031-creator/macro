"""Benchmark TOTAL-return series + income-yield helpers for the tactical-yield
strategies.

KEY FACT (verified against the on-disk data, not assumed): the yahoo `close` column
is the DIVIDEND/COUPON-ADJUSTED close — i.e. it already IS a total-return series.
Proof: HYG `close` runs 31.69 (2007-04) -> 80.04 (2026-06) = 2.53x ≈ 5.0%/yr, which is
HY's *total* return; the raw unadjusted price fell (~$109 -> ~$79) over the same span.
TLT (≈3.7%/yr) and SPY (≈11%/yr) check out the same way. So the honest benchmark for a
bond/credit "yield" strategy is simply the adjusted close — NO coupon-carry term is
added (that would double-count the coupon already baked into the adjusted price).

This module therefore mostly just *names* the right series and documents the choice,
plus exposes the current income yields used for the scorecard headline. Each TR builder
keeps an authoritative-upgrade hook: if a collector ever caches the real ICE BofA
total-return INDEX (FRED IDs below), it is used automatically with no code change.
Those parquets are absent today (FRED is unreachable from the sandbox), so locally the
adjusted close is used — which is the correct total return anyway.

The one genuine reconstruction is `treasury_tr`: a SYNTHETIC constant-maturity index
from a yield LEVEL with no underlying price series, where carry + (−dur·Δy) IS the only
way to get a total return — that is not double-counting. It is only a deep-history
fallback (pre-2002, before TLT exists).
"""
from __future__ import annotations

import pandas as pd

from lib import store

# Approx modified duration per constant-maturity leg (coarse; only used by the synthetic
# fallback). The authoritative-TR / ETF paths don't need it.
_DUR = {"us2y": 1.9, "us5y": 4.6, "us10y": 8.4, "us30y": 18.0, "long_tsy": 16.5}
_TY = 252  # trading days/yr


def _yield(series: str, col: str) -> pd.Series | None:
    df = store.read("fred", series)
    if df is None or df.empty:
        return None
    c = col if col in df.columns else df.columns[0]
    return df[c].astype(float).dropna()


def _adj_close(ticker: str) -> pd.Series | None:
    df = store.read("yahoo", ticker)
    if df is None or df.empty or "close" not in df.columns:
        return None
    return df["close"].astype(float).dropna()


def treasury_tr(yield_key: str = "DGS10", col: str = "us10y",
                dur: float | None = None) -> pd.Series:
    """SYNTHETIC constant-maturity Treasury total-return index from a yield LEVEL (%).
    Daily return = carry + price = (y_prev/252)/100 − dur·Δy/100, cumulated from 100.
    Reuses the −dur·Δy shape of cross_asset_trend._bond_price_index and ADDS the carry
    it omits — legitimate here because there is NO price series to double-count. Deep
    history; used only as the pre-ETF fallback."""
    y = _yield(yield_key, col)
    if y is None:
        raise FileNotFoundError(f"no Treasury yield series {yield_key} on disk")
    d = dur if dur is not None else _DUR.get(col, 8.0)
    r = ((y.shift(1) / _TY) / 100.0) + (-d * y.diff() / 100.0)
    return (1.0 + r.fillna(0.0)).cumprod() * 100.0


def long_treasury_tr() -> pd.Series:
    """Long-Treasury TOTAL return for the Duration strategy benchmark = TLT adjusted
    close (already total return, 2002→) → else a synthetic 30y CMT index (pre-2002).
    NB: there is no clean ICE BofA US *Treasury* total-return index on public FRED, so
    (unlike hy_tr) there is no authoritative-upgrade hook here — TLT's dividend-adjusted
    close already IS the total return. (Do NOT substitute a CORPORATE TR index here.)"""
    tlt = _adj_close("TLT")
    if tlt is not None:
        return tlt
    return treasury_tr("DGS30", "us30y", dur=_DUR["long_tsy"])


def hy_tr() -> pd.Series:
    """High-yield credit TOTAL return for the Credit Carry benchmark. Authoritative
    ICE BofA US HY TR (BAMLHYH0A0HYM2TRIV) if present (CI) → else HYG adjusted close
    (already total return; HYG starts 2007-04 — warm-up caveat, no silent backfill)."""
    auth = store.read("fred", "BAMLHYH0A0HYM2TRIV")  # authoritative HY TR (absent today)
    if auth is not None and not auth.empty:
        return auth[auth.columns[0]].astype(float).dropna()
    hyg = _adj_close("HYG")
    if hyg is None:
        raise FileNotFoundError("no HYG series on disk for the HY total-return benchmark")
    return hyg


# --------------------------------------------------------------------------- #
# current income yields (the per-strategy "income" headline on the scorecard)
# --------------------------------------------------------------------------- #
def hy_yield() -> pd.Series:
    """HY yield-to-worst proxy (%) = 5y Treasury + HY-OAS — the income a fully-invested
    Credit Carry book earns."""
    oas = _yield("BAMLH0A0HYM2", "hy_oas")
    ust = _yield("DGS5", "us5y")
    if oas is None or ust is None:
        return pd.Series(dtype=float)
    idx = ust.index.union(oas.index)
    return (ust.reindex(idx).ffill() + oas.reindex(idx).ffill()).dropna()


def treasury_cash_yield() -> pd.Series:
    """5y Treasury yield (%) — the rate the Credit Carry de-risked sleeve earns sitting
    in Treasuries (not under the mattress)."""
    s = _yield("DGS5", "us5y")
    return s if s is not None else pd.Series(dtype=float)


def long_yield() -> pd.Series:
    """30y Treasury yield (%) — income of a fully-invested Duration book."""
    s = _yield("DGS30", "us30y")
    return s if s is not None else pd.Series(dtype=float)
