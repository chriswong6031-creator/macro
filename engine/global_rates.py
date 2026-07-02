"""Global cost-of-capital leaf — the C5 producer (masterplan §5 C5, W3).

A pure, causal LEAF (imports nothing from the scoring core): it reconstructs the
GDP-weighted GLOBAL 10y level + the US-vs-rest-of-world 10y premium as *daily
time series* — the same two aggregates ``engine/intl_bonds.snapshot`` computes for
the display card, but as HISTORY rather than a single as-of snapshot. The bond
scorecard dead-ends those numbers into ``data/bonds/bond_health.json`` with no
history on disk (INTL-15), so this leaf reconstructs them causally from the same
underlying sovereign 10y series the scorecard consumes.

Reconstruction fidelity: the aggregation MIRRORS ``intl_bonds`` exactly — the same
ROSTER of sovereign 10y legs, the same rough nominal-GDP weights, the same monthly-
onto-business-day carry (ffill, bounded), the same GDP-weight-over-AVAILABLE-legs
normalisation. Cross-checked against the live ``bond_health.json`` snapshot
(avg_10y within ~0.05pp; us_premium_bp differs by the roster availability on the
snapshot date). All same-day-available: a monthly OECD long-rate print is carried
forward, never back-filled, so the value at t uses only data published by t.

The C5 mechanism under test (de-risk): a RISING global 10y / WIDENING US premium is
a global duration + growth-beta headwind that should lead US equity drawdowns. The
DECIDING gate is orthogonality vs the existing US curve/credit MRS legs — the global
10y is plausibly ~US 10y + noise, so a truthful CONTEXT is the expected outcome and
is welcome (measured, not assumed). DISPLAY/CONTEXT tier until it clears the harness.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import store

log = logging.getLogger(__name__)

_TY = 252  # business days / yr

# The sovereign 10y roster + GDP weights — MIRRORS engine.intl_bonds.ROSTER so the
# reconstructed aggregate matches the display card. (code, gdp_w, (group, series)).
# US 10y = FRED DGS10 (the scorecard reads it off the build_features frame as us10y,
# which is DGS10); the rest are the ECB Bund / JGB / OECD long-rate legs on disk.
ROSTER: list[tuple[str, float, tuple[str, str]]] = [
    ("US", 0.42, ("fred", "DGS10")),
    ("DE", 0.22, ("sovereign", "ez_aaa_10y")),
    ("JP", 0.10, ("sovereign", "jgb_10y")),
    ("GB", 0.07, ("fred", "IRLTLT01GBM156N")),
    ("CA", 0.06, ("fred", "IRLTLT01CAM156N")),
    ("AU", 0.05, ("fred", "IRLTLT01AUM156N")),
    ("CH", 0.03, ("fred", "IRLTLT01CHM156N")),
]

# minimum number of AVAILABLE legs required to emit an aggregate on a date — the same
# fail-closed spirit as the breadth panel: no aggregate on a sparse roster.
_MIN_LEGS = 4
# monthly-onto-bday carry limit (matches intl_bonds._align default of 40 bdays).
_FFILL_LIMIT = 40


def _load(group: str, name: str) -> pd.Series | None:
    """One 10y leg as a clean float Series (deduped, sorted), or None."""
    try:
        df = store.read(group, name)
    except Exception:  # noqa: BLE001 — a read error is a data gap, not a crash
        return None
    if df is None or df.empty:
        return None
    s = df.iloc[:, 0].astype(float).dropna()
    if s.empty:
        return None
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def _carry(s: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    """Carry a (possibly monthly) leg onto the business-day index — ffill only
    (never back-fill), bounded, so a 63-bday change is uniform across daily and
    monthly legs and the value at t uses only data published by t (causal)."""
    return s.reindex(idx.union(s.index)).ffill(limit=_FFILL_LIMIT).reindex(idx)


def _bday_index() -> pd.DatetimeIndex | None:
    """Business-day index spanning the US 10y history (the deepest daily leg)."""
    us = _load("fred", "DGS10")
    if us is None:
        return None
    return pd.bdate_range(us.index.min(), us.index.max())


def _panel(idx: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.Series]:
    """Return (levels DataFrame [code], gdp-weight Series [code]) carried onto idx."""
    cols: dict[str, pd.Series] = {}
    wt: dict[str, float] = {}
    for code, w, (g, n) in ROSTER:
        s = _load(g, n)
        if s is None:
            continue
        cols[code] = _carry(s, idx)
        wt[code] = w
    return pd.DataFrame(cols), pd.Series(wt)


def avg_10y(idx: pd.DatetimeIndex | None = None) -> pd.Series:
    """GDP-weighted GLOBAL 10y level (%), daily, over the AVAILABLE legs — the global
    cost of capital as a time series. NaN on dates with < _MIN_LEGS legs."""
    idx = idx if idx is not None else _bday_index()
    if idx is None:
        return pd.Series(dtype=float)
    lv, wt = _panel(idx)
    if lv.empty:
        return pd.Series(index=idx, dtype=float)
    avail = lv.notna()
    tot_w = (avail * wt).sum(axis=1)
    agg = lv.mul(wt, axis=1).sum(axis=1) / tot_w.replace(0, np.nan)
    return agg.where(avail.sum(axis=1) >= _MIN_LEGS)


def us_premium_bp(idx: pd.DatetimeIndex | None = None) -> pd.Series:
    """US 10y minus the GDP-weighted rest-of-world 10y, in bp — the dollar's rate-
    differential anchor, daily. NaN where the US leg or the ex-US aggregate is absent."""
    idx = idx if idx is not None else _bday_index()
    if idx is None:
        return pd.Series(dtype=float)
    lv, wt = _panel(idx)
    if lv.empty or "US" not in lv.columns:
        return pd.Series(index=idx, dtype=float)
    exus = [c for c in lv.columns if c != "US"]
    if not exus:
        return pd.Series(index=idx, dtype=float)
    lex, wex = lv[exus], wt[exus]
    availex = lex.notna()
    totex = (availex * wex).sum(axis=1)
    exus_10y = lex.mul(wex, axis=1).sum(axis=1) / totex.replace(0, np.nan)
    return (lv["US"] - exus_10y) * 100.0


def series(idx: pd.DatetimeIndex | None = None) -> dict[str, pd.Series]:
    """Both reconstructed aggregates, business-day-aligned, for the C5 builder + display.
    Returns {'avg_10y', 'us_premium_bp'} — pure, causal, no look-ahead."""
    idx = idx if idx is not None else _bday_index()
    if idx is None:
        return {}
    return {"avg_10y": avg_10y(idx), "us_premium_bp": us_premium_bp(idx)}


def snapshot() -> dict:
    """The latest reconstructed aggregates (for a display card / cross-check vs
    bond_health.json). Never raises; returns {} if the roster is unavailable."""
    s = series()
    if not s:
        return {}
    a = s["avg_10y"].dropna()
    p = s["us_premium_bp"].dropna()
    if a.empty:
        return {}
    a63 = float((a.iloc[-1] - a.iloc[-1 - 63]) * 100.0) if len(a) > 63 else None
    return {
        "avg_10y": round(float(a.iloc[-1]), 2),
        "avg_10y_chg_63d_bp": round(a63, 0) if a63 is not None else None,
        "us_premium_bp": round(float(p.iloc[-1]), 0) if not p.empty else None,
        "as_of": str(a.index[-1].date()),
    }
