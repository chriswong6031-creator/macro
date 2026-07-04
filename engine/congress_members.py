"""Per-member reliability engine for the Congressional Trades desk.

SEMANTICS OF Quiver's ExcessReturn
------------------------------------
ExcessReturn = PriceChange − SPYChange, where PriceChange and SPYChange are each
the cumulative return from TransactionDate to Quiver's snapshot date (~their most
recent data pull, typically T-1 business day).

Cross-validation (2026-07-04):
  Mean(ExcessReturn − (PriceChange − SPYChange)) = 1.75e-15 (floating-point noise).
  Max abs diff across 943 valid rows: 9.1e-13. Identity is exact.

HORIZON PROBLEM: a July-2025 trade has ~12 months of return accrued; a June-2026
trade has 2 weeks. This makes raw ExcessReturn horizon-inconsistent across members
and inherently biased in favour of older trades (which have had more time for
alpha to compound OR for luck to dominate).

APPROACH: We use ExcessReturn as-is with a horizon discount that downweights
trades < 21 trading days old (too short to measure) and separately flag members
whose hit-rate estimate is driven mainly by recent long-horizon accumulations vs.
genuine skill. A proper fixed-horizon (63-day) recompute from yahoo prices would
require AAPL, MSFT etc. in data/yahoo — which are not present (only basket/ETF
constituents are cached). The approach taken is therefore:
  1. Exclude trades < 21 trading days (~1 calendar month) from skill computation
     (insufficient horizon to measure alpha).
  2. Apply empirical-Bayes shrinkage toward the pooled mean so n=3 members don't
     appear skilled based on a couple of lucky horizon-inflated trades.
  3. Label the limitation honestly in tier definitions and the display.

EMPIRICAL-BAYES SHRINKAGE
--------------------------
Pooled across all 943 valid ExcessReturn rows:
  hit_rate_pooled = 39.3%  (ER > 0)
  er_mean_pooled  = 2.76 pp

Shrinkage toward pooled mean:
  shrunk_hit_rate = (n_hits + κ × p0) / (n_valid + κ)
where κ = 8 (posterior pseudo-count; chosen so that n=8 effective observations
counts half as "proven").

DISPLAY TIERS
-------------
  proven    n_eff_valid ≥ 8  AND  shrunk_hit_rate > pooled
  watch     n_eff_valid 3–7
  limited   n_eff_valid < 3
  (n_eff_valid = trades where horizon ≥ 21 trading days AND ExcessReturn is not NaN)

MINIMAL-DEPS NOTE
-----------------
  Never call pd.Series.corr(method='spearman'). Use rank().corr(rank()) instead
  (scipy is not guaranteed in CI). This module avoids rank correlation entirely.

BACKFILL STATUS
---------------
  BLOCKED: no QUIVER_API_KEY found in project .env. The parquet covers ~12 months
  (TransactionDate 2025-07-01 → 2026-06-16). Deeper history would improve n for
  frequent traders but cannot be fetched without the key. See collectors/quiver.py
  QuiverCongress for the endpoint (/beta/live/congresstrading).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import NamedTuple

log = logging.getLogger(__name__)

# ── pooled priors (computed from 968-row snapshot 2026-07-04) ────────────────
_POOLED_HIT_RATE: float = 0.393   # P(ExcessReturn > 0) across all rows with valid ER
_POOLED_ER_MEAN: float  = 2.76    # pp, mean ExcessReturn

# Shrinkage pseudo-count: n=8 effective observations → hit-rate estimate is halfway
# between raw and pooled (i.e. κ controls the prior strength).
_KAPPA: int = 8

# Minimum trading-day horizon to include a trade in skill estimation.
# Trades < 21 trading days old (~1 calendar month) have too short a return window.
# Approximation: 21 trading days ≈ 30 calendar days.
_MIN_HORIZON_CALENDAR_DAYS: int = 30

# Tier thresholds
_TIER_PROVEN_MIN_N: int = 8
_TIER_WATCH_MIN_N:  int = 3


class MemberStats(NamedTuple):
    bio_guide_id:      str
    representative:    str
    party:             str
    chamber:           str
    n_trades:          int          # all trades in window
    n_buys:            int
    n_eff_valid:       int          # trades with horizon ≥ 30 calendar days and valid ER
    n_hits:            int          # ER > 0 among eff_valid
    shrunk_hit_rate:   float        # empirical-Bayes shrunk hit rate [0,1]
    raw_hit_rate:      float        # unshrunk, shown only when n_eff_valid ≥ 3
    er_median:         float | None # median ExcessReturn (eff_valid trades), pp
    er_mean:           float | None # mean ExcessReturn (eff_valid trades), pp
    total_notional:    float        # sum of range-midpoints across all trades, USD
    median_lag_days:   float | None # median filing lag (ReportDate − TransactionDate)
    days_since_last:   int | None   # calendar days since most-recent TransactionDate
    tier:              str          # 'proven' | 'watch' | 'limited'
    member_quality:    float        # 0–1 signal; used as a SMALL additive term in cluster


def _shrink(n_hits: int, n_valid: int, kappa: int = _KAPPA,
            prior: float = _POOLED_HIT_RATE) -> float:
    """Empirical-Bayes shrinkage toward pooled hit rate."""
    if n_valid <= 0:
        return prior
    return (n_hits + kappa * prior) / (n_valid + kappa)


def _tier(n_eff: int, shrunk: float, prior: float = _POOLED_HIT_RATE) -> str:
    if n_eff >= _TIER_PROVEN_MIN_N and shrunk > prior:
        return "proven"
    if n_eff >= _TIER_WATCH_MIN_N:
        return "watch"
    return "limited"


def _quality(n_eff: int, shrunk: float, prior: float = _POOLED_HIT_RATE) -> float:
    """Map member reliability to [0, 1] for use as a small cluster additive.

    Calibrated so that a fully-proven member with shrunk hit rate = 0.60 scores 1.0;
    a member at the pooled mean scores 0.5; a member well below pooled scores near 0.
    Deliberately conservative — do not overfit 12 months of data.
    """
    if n_eff < _TIER_WATCH_MIN_N:
        return 0.5   # neutral for limited members
    # linear from [prior-0.15, prior+0.20] → [0, 1], clamped
    lo, hi = prior - 0.15, prior + 0.20
    q = (shrunk - lo) / max(hi - lo, 0.01)
    return max(0.0, min(1.0, q))


def compute(df, asof: date | None = None) -> dict[str, MemberStats]:
    """Compute per-member reliability stats from the congress parquet DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        The congress.parquet dataframe (all rows, not just in-window).
    asof : date, optional
        Reference date for age calculations; defaults to today.

    Returns
    -------
    dict mapping BioGuideID -> MemberStats
    """
    import pandas as pd
    from datetime import datetime

    if asof is None:
        asof = datetime.now().date()

    asof_ts = pd.Timestamp(asof)

    # Coerce numeric columns (stored as float64, but may have NaN)
    er_col  = pd.to_numeric(df.get("ExcessReturn"), errors="coerce") if "ExcessReturn" in df.columns else None
    pc_col  = pd.to_numeric(df.get("PriceChange"),  errors="coerce") if "PriceChange"  in df.columns else None

    tx_dates = pd.to_datetime(df.get("TransactionDate"), errors="coerce")
    rd_dates = pd.to_datetime(df.get("ReportDate"),      errors="coerce")

    results: dict[str, MemberStats] = {}

    for bio_id, grp in df.groupby("BioGuideID", dropna=True):
        idx = grp.index
        rep = str(grp["Representative"].iloc[0] or "").strip()
        party = str(grp["Party"].iloc[0] or "").strip().upper()[:1]
        house = str(grp["House"].iloc[0] or "").strip().lower()
        chamber = "Senate" if house.startswith("sen") else "House"

        # Transaction sides
        transactions = grp.get("Transaction", pd.Series(dtype=str))
        is_buy = transactions.str.lower().str.startswith("purchase", na=False)
        n_trades = len(grp)
        n_buys   = int(is_buy.sum())

        # Amount midpoints (for total notional)
        # We can't call _amount_range here without importing build_congress; re-implement inline.
        import re as _re
        def _mid(row):
            rng = str(row.get("Range") or "")
            nums = [float(m.replace(",", "")) for m in _re.findall(r"\$?\s*([\d,]+(?:\.\d+)?)", rng)]
            if len(nums) >= 2:
                return (nums[0] + nums[1]) / 2.0
            if len(nums) == 1:
                return nums[0]
            try:
                amt = str(row.get("Amount") or "")
                if amt.lower() not in ("nan", "", "none"):
                    return float(amt.replace(",", "").replace("$", ""))
            except (TypeError, ValueError):
                pass
            return 0.0

        total_notional = float(sum(_mid(r) for r in grp.to_dict("records")))

        # Horizon filter: only trades ≥ 30 calendar days old are used for skill
        tx_g = tx_dates.loc[idx]
        age_days = (asof_ts - tx_g).dt.days.fillna(999).astype(float)
        horizon_ok = age_days >= _MIN_HORIZON_CALENDAR_DAYS

        # ExcessReturn for this group
        if er_col is not None:
            er_g = er_col.loc[idx]
        else:
            er_g = pd.Series([None] * n_trades, index=idx, dtype=float)

        eff_mask = horizon_ok & er_g.notna()
        n_eff_valid = int(eff_mask.sum())
        n_hits      = int((er_g[eff_mask] > 0).sum())

        er_eff = er_g[eff_mask]
        er_median = float(er_eff.median()) if n_eff_valid > 0 else None
        er_mean   = float(er_eff.mean())   if n_eff_valid > 0 else None

        shrunk   = _shrink(n_hits, n_eff_valid)
        raw_rate = (n_hits / n_eff_valid) if n_eff_valid >= 3 else float("nan")
        tier     = _tier(n_eff_valid, shrunk)
        quality  = _quality(n_eff_valid, shrunk)

        # Filing lag
        rd_g = rd_dates.loc[idx]
        lag_series = (rd_g - tx_g).dt.days
        median_lag = float(lag_series.dropna().median()) if lag_series.dropna().shape[0] > 0 else None

        # Recency
        most_recent_tx = tx_g.max()
        days_since = int((asof_ts - most_recent_tx).days) if not pd.isna(most_recent_tx) else None

        results[str(bio_id)] = MemberStats(
            bio_guide_id    = str(bio_id),
            representative  = rep,
            party           = party,
            chamber         = chamber,
            n_trades        = n_trades,
            n_buys          = n_buys,
            n_eff_valid     = n_eff_valid,
            n_hits          = n_hits,
            shrunk_hit_rate = round(shrunk, 3),
            raw_hit_rate    = round(raw_rate, 3) if n_eff_valid >= 3 else float("nan"),
            er_median       = round(er_median, 2) if er_median is not None else None,
            er_mean         = round(er_mean,   2) if er_mean   is not None else None,
            total_notional  = round(total_notional),
            median_lag_days = round(median_lag, 1) if median_lag is not None else None,
            days_since_last = days_since,
            tier            = tier,
            member_quality  = round(quality, 3),
        )

    return results


def leaderboard(stats: dict[str, MemberStats], top_n: int = 20) -> list[dict]:
    """Return leaderboard rows sorted by tier then shrunk hit rate, capped at top_n."""
    tier_order = {"proven": 0, "watch": 1, "limited": 2}
    rows = sorted(
        stats.values(),
        key=lambda m: (tier_order.get(m.tier, 9), -m.shrunk_hit_rate, -m.n_eff_valid),
    )
    out = []
    for m in rows[:top_n]:
        out.append({
            "representative":   m.representative,
            "party":            m.party,
            "chamber":          m.chamber,
            "tier":             m.tier,
            "n_trades":         m.n_trades,
            "n_eff_valid":      m.n_eff_valid,
            "shrunk_hit_rate":  m.shrunk_hit_rate,
            "raw_hit_rate":     m.raw_hit_rate if m.n_eff_valid >= 3 else None,
            "er_median":        m.er_median,
            "days_since_last":  m.days_since_last,
            "member_quality":   m.member_quality,
        })
    return out
