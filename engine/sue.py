"""SUE — Standardized Unexpected Earnings (earnings-momentum) from the quarterly
EDGAR EPS panel (collectors/edgar_eps.py).

SUE expresses the post-earnings-announcement-drift (PEAD) effect: a company whose
latest quarterly EPS beat a naive seasonal-random-walk expectation (the same quarter
a year ago) tends to keep drifting in that direction. We compute, per company:

    surprise   = EPS_q − EPS_{q-4}                 (seasonal random walk)
    SUE        = surprise / σ(trailing surprises)  (standardized by its own history)

Quarters are matched by CALENDAR (the year-ago quarter within ±50 days), so a gap in
the filing history does not silently misalign the lag. Everything is point-in-time:
only quarters whose synthetic as-of date (period_end + reporting lag) is on or before
the rebalance date are visible, and a stale name (no fresh filing within ~7 months) is
dropped. Returns one raw SUE per ticker; the caller cross-sectionally winsorizes/z's.

DISPLAY/SIGNAL status is decided by scripts/validate_sue.py (Phase-0 IC/FDR) before
any wiring — see research/DATA_SIGNAL_EXPANSION_2026.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from collectors.edgar_eps import eps_panel_path


def load_panel() -> pd.DataFrame | None:
    p = eps_panel_path()
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["asof_date"] = pd.to_datetime(df["asof_date"])
    return df


def _seasonal_diffs(period_end: np.ndarray, eps: np.ndarray,
                    tol_days: int = 50) -> list[tuple[pd.Timestamp, float]]:
    """[(period_end, EPS_q − EPS_year-ago)] matched by calendar (year-ago within ±tol)."""
    out = []
    pe = period_end.astype("datetime64[D]")
    for i in range(len(pe)):
        target = pe[i] - np.timedelta64(365, "D")
        best_j, best_gap = -1, tol_days + 1
        for j in range(i):
            gap = abs(int((pe[j] - target) / np.timedelta64(1, "D")))
            if gap <= best_gap:
                best_gap, best_j = gap, j
        if best_j >= 0 and best_gap <= tol_days:
            out.append((pd.Timestamp(pe[i]), float(eps[i] - eps[best_j])))
    return out


def sue_cross_section(panel: pd.DataFrame, asof, *, min_diffs: int = 4,
                      vol_window: int = 12, recency_days: int = 215) -> pd.Series:
    """Point-in-time raw SUE per ticker knowable on `asof`. None of the inputs use a
    quarter not yet 'filed' (asof_date <= asof). Stale names (latest filed quarter older
    than recency_days) are dropped so we only ever read a recent surprise."""
    asof = pd.Timestamp(asof)
    sub = panel[panel["asof_date"] <= asof]
    out: dict[str, float] = {}
    for tic, g in sub.groupby("ticker"):
        g = g.sort_values("period_end")
        if len(g) < min_diffs + 2:
            continue
        diffs = _seasonal_diffs(g["period_end"].values, g["eps_q"].values)
        if len(diffs) < min_diffs:
            continue
        last_pe, last_d = diffs[-1]
        if (asof - last_pe).days > recency_days:        # no fresh quarter -> stale/delisted
            continue
        recent = pd.Series([d for _pe, d in diffs[-vol_window:]])
        sd = recent.std()
        if not sd or np.isnan(sd) or sd == 0:
            continue
        out[tic] = last_d / sd
    return pd.Series(out, dtype=float)


def winsor_z(s: pd.Series, cap: float = 3.0) -> pd.Series:
    """Cross-sectional standardize + clip (for the LIVE factor score; rank IC is
    invariant to this, so the Phase-0 harness ranks the raw SUE directly)."""
    s = s.replace([np.inf, -np.inf], np.nan)
    mu, sd = s.mean(), s.std()
    if not sd or np.isnan(sd):
        return pd.Series(np.nan, index=s.index)
    return ((s - mu) / sd).clip(-cap, cap)
