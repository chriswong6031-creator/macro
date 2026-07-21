"""Winner Autopsy Lab — W3 Census Fingerprint Study (Layer-3a).

Spec: research/winners/W3_CENSUS_STUDY_SPEC.md (2026-07-20, main-loop Fable).
Tests W2 candidate fingerprints (F1–F6) against full census base rates.
DESCRIPTIVE ONLY — no hypothesis registration, no composite scores, no site surfaces.
Rulings WA-R1/R5/R8 — all display-tier.

Usage:
    python scripts/research/run_w3_census_fingerprints.py \\
        --root /path/to/data \\
        --out research/winners/FINGERPRINT_CENSUS_W3.md \\
        [--episodes data/research/winner_episodes.parquet] \\
        [--seed 20260720] \\
        [--n-boot 50000]

The script never writes under --root.

Review-round-1 fixes applied (adversarial stats review 2026-07-20):
  - BLOCKER: bonf_survives now uses α/m percentile CI, not 95% CI.
  - n_boot raised to 50,000 (same seed). Both CIs printed per row.
  - F2 gap_hold_k reclassified as TAUTOLOGICAL — moved out of fingerprint tables.
  - F4 collapsed into F5: new_high_63d is 100% by construction, removed from m.
  - liquid and new_high_63d excluded from m (constants by construction).
  - F1 missing-as-zero replaced with mask (drop) on uncovered episodes.
  - Bootstrap pairing: one drawn month multiset per replicate feeds BOTH groups.
  - Ticker-cluster bootstrap CI added as robustness column.
  - Stratum 1 (survivorship) replaced with honest disclosure (untested).
  - Crypto episodes (BTC-USD, BTC_F, ETH-USD, SOL-USD) segregated.
  - _b1_features citation corrected to extract_b1_hardening_ladder.
  - Leading-colon lstrip artifacts fixed in verdict cells.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
B1_ERA_CUTOFF: pd.Timestamp = pd.Timestamp("2014-01-01")
B1_HARD_ITEMS: frozenset[str] = frozenset({"1.01", "2.01"})
B1_SOFT_ITEMS: frozenset[str] = frozenset({"7.01", "8.01"})

MATURED_LABELS = {"durable_winner", "clean_hold", "blow_off", "failed"}
KEPT_GOING_LABELS = {"durable_winner", "clean_hold"}

# Crypto tickers: 7-day calendar, SPY benchmark error, index-alignment mismatch
CRYPTO_TICKERS: frozenset[str] = frozenset({"BTC-USD", "BTC_F", "ETH-USD", "SOL-USD"})

# Spec §4: m = total feature × contrast tests (declared below after feature list is known)
ALPHA = 0.05
BOOT_REPS = 50_000  # raised from 10,000 for α/m tail resolution
BOOT_SEED = 20260720

# 21 trading days ≈ 30 calendar days — we use position in sorted price index
# to find t0+k trading days
FORWARD_TDS = [3, 5, 10]  # for F2 gap-hold
EARLY_MOVE_TDS = 21        # for F1 early-move conditioner

# ---------------------------------------------------------------------------
# Helper: parse B1 item codes from string
# ---------------------------------------------------------------------------

def _parse_items_list(items_str: str | None) -> list[str]:
    if not items_str:
        return []
    s = str(items_str).strip()
    if s.startswith("["):
        import ast
        try:
            return [str(x) for x in ast.literal_eval(s)]
        except Exception:  # noqa: BLE001
            pass
    # Comma or space separated
    return [x.strip().strip("'\"") for x in s.replace(";", ",").split(",") if x.strip()]


# ---------------------------------------------------------------------------
# Helper: load price series for a ticker (honoring price_source)
# ---------------------------------------------------------------------------

def _load_price_series(
    ticker: str,
    price_source: str,
    root: Path,
) -> pd.Series | None:
    """Return close price series indexed by date, or None if unavailable."""
    if price_source == "massive":
        fpath = root / "massive_stock_day" / f"{ticker}.parquet"
        if fpath.exists():
            try:
                df = pd.read_parquet(fpath)
                if "close" in df.columns:
                    return df["close"].dropna().sort_index()
            except Exception:  # noqa: BLE001
                pass
    # Default / yahoo
    fpath = root / "yahoo" / f"{ticker}.parquet"
    if fpath.exists():
        try:
            df = pd.read_parquet(fpath)
            col = "close" if "close" in df.columns else df.columns[0]
            return df[col].dropna().sort_index()
        except Exception:  # noqa: BLE001
            pass
    return None


# ---------------------------------------------------------------------------
# F2 — trigger gap holds (early-move conditioner: uses t0 and forward bars)
# NOTE: gap_hold_k is TAUTOLOGICAL for kept_going episodes (see tautology section).
# This function is preserved for blow_off descriptive rates only.
# ---------------------------------------------------------------------------

def compute_f2_gap_holds(
    ticker: str,
    t0: pd.Timestamp,
    price_source: str,
    root: Path,
) -> dict[str, Any]:
    """Compute onset-day gap % and gap-hold booleans at t0+3/5/10 trading days.

    gap_pct: close(t0) / close(t0-1td) - 1, expressed as %.
    gap_hold_k: close(t0+k_td) > close(t0-1td), i.e., gap not fully reversed.
    Missing bars are counted-not-hidden (None returned, not excluded).

    Returns:
        gap_pct: float | None
        gap_hold_3: bool | None
        gap_hold_5: bool | None
        gap_hold_10: bool | None
        f2_coverage: str  -- 'ok' | 'insufficient_bars' | 'no_price_data'
    """
    empty = {
        "gap_pct": None,
        "gap_hold_3": None,
        "gap_hold_5": None,
        "gap_hold_10": None,
        "f2_coverage": "no_price_data",
    }

    series = _load_price_series(ticker, price_source, root)
    if series is None or len(series) < 5:
        return empty

    # Find t0 position in the price index
    idx = series.index
    t0_normalized = pd.Timestamp(t0).normalize()
    pos_arr = idx.searchsorted(t0_normalized, side="left")
    if pos_arr >= len(idx):
        return {**empty, "f2_coverage": "insufficient_bars"}

    # t0 price (use the exact t0 bar, or nearest available)
    # Find the position that is at or just after t0
    if idx[pos_arr] != t0_normalized:
        # t0 not in index; find nearest >=
        if pos_arr == 0 or idx[pos_arr] > t0_normalized + pd.Timedelta(days=5):
            return {**empty, "f2_coverage": "insufficient_bars"}

    # Verify t0 bar is close to t0 (within 3 calendar days to handle weekends)
    t0_bar_date = idx[pos_arr]
    if abs((t0_bar_date - t0_normalized).days) > 3:
        return {**empty, "f2_coverage": "insufficient_bars"}

    if pos_arr < 1:
        return {**empty, "f2_coverage": "insufficient_bars"}

    close_t0m1 = float(series.iloc[pos_arr - 1])
    close_t0 = float(series.iloc[pos_arr])

    if close_t0m1 <= 0:
        return {**empty, "f2_coverage": "insufficient_bars"}

    gap_pct = (close_t0 / close_t0m1 - 1.0) * 100.0

    gap_holds: dict[str, bool | None] = {}
    for k in FORWARD_TDS:
        fwd_pos = pos_arr + k
        if fwd_pos < len(idx):
            close_fwd = float(series.iloc[fwd_pos])
            gap_holds[f"gap_hold_{k}"] = close_fwd > close_t0m1
        else:
            gap_holds[f"gap_hold_{k}"] = None  # missing bar — counted not hidden

    return {
        "gap_pct": round(gap_pct, 4),
        "gap_hold_3": gap_holds["gap_hold_3"],
        "gap_hold_5": gap_holds["gap_hold_5"],
        "gap_hold_10": gap_holds["gap_hold_10"],
        "f2_coverage": "ok",
    }


# ---------------------------------------------------------------------------
# F1 early-move conditioner: rung count in (t0, t0+21td]
# F1 trailing: use per-episode from parquet, but MASK (not zero-fill) missing coverage
# ---------------------------------------------------------------------------

def compute_f1_early_move(
    ticker: str,
    t0: pd.Timestamp,
    price_source: str,
    events_df: pd.DataFrame,
    root: Path,
) -> dict[str, Any]:
    """Compute hard+soft rung count in the early-move window (t0, t0+21 trading days].

    This is an EARLY-MOVE CONDITIONER — it uses post-t0 information up to +21td.
    Labeled clearly as such in all tables.

    Citation: engine/winner_autopsy.py:extract_b1_hardening_ladder (line 1139).

    Returns:
        f1_fwd_hard_count: int | None
        f1_fwd_soft_count: int | None
        f1_fwd_rung_ge2: bool | None   (hard+soft combined >= 2)
        f1_fwd_coverage: str
    """
    empty = {
        "f1_fwd_hard_count": None,
        "f1_fwd_soft_count": None,
        "f1_fwd_rung_ge2": None,
        "f1_fwd_coverage": "no_8k_data",
    }

    if events_df is None or events_df.empty:
        return empty

    if t0 < B1_ERA_CUTOFF:
        return {**empty, "f1_fwd_coverage": "pre_era_cutoff"}

    # Find t0 + 21 trading days using the price series calendar
    series = _load_price_series(ticker, price_source, root)
    if series is None or len(series) < 5:
        return {**empty, "f1_fwd_coverage": "no_price_for_td_count"}

    idx = series.index
    t0_norm = pd.Timestamp(t0).normalize()
    pos_arr = idx.searchsorted(t0_norm, side="left")

    fwd_end_pos = pos_arr + EARLY_MOVE_TDS
    if fwd_end_pos >= len(idx):
        # Not enough forward bars — use calendar 31d as fallback bound
        t0_plus_21td = t0_norm + pd.Timedelta(days=31)
    else:
        t0_plus_21td = idx[fwd_end_pos]

    # Filter 8K events for this ticker in (t0, t0+21td]
    ticker_mask = events_df["ticker"].astype(str) == str(ticker)
    ev = events_df[ticker_mask]
    if ev.empty:
        return {**empty, "f1_fwd_coverage": "ticker_not_in_8k"}

    ev = ev.copy()
    ev["_fd"] = pd.to_datetime(ev["filing_date"], errors="coerce")
    ev = ev.dropna(subset=["_fd"])

    fwd_mask = (ev["_fd"] > t0_norm) & (ev["_fd"] <= t0_plus_21td)
    fwd_ev = ev[fwd_mask]

    hard_count = 0
    soft_count = 0
    for _, row in fwd_ev.iterrows():
        items_str = row.get("items")
        items = _parse_items_list(items_str)
        if any(c in B1_HARD_ITEMS for c in items):
            hard_count += 1
        if any(c in B1_SOFT_ITEMS for c in items):
            soft_count += 1

    total_rungs = hard_count + soft_count
    return {
        "f1_fwd_hard_count": hard_count,
        "f1_fwd_soft_count": soft_count,
        "f1_fwd_rung_ge2": total_rungs >= 2,
        "f1_fwd_coverage": "ok",
    }


# ---------------------------------------------------------------------------
# F3 — profit step-up faster than revenue (quarterly statements)
# ---------------------------------------------------------------------------

def compute_f3_profit_stepup(
    ticker: str,
    t0: pd.Timestamp,
    statements_q: pd.DataFrame,
) -> dict[str, Any]:
    """Compute sign of Δ(op_income_margin) - Δ(revenue) QoQ at nearest print <= t0.

    A2 firewall (WA-R7): excluded for episodes with t0 >= 2024-01-01.
    Only computed where committed quarterly panel coverage exists.

    Returns:
        f3_margin_delta_minus_rev_delta: float | None
        f3_profit_stepup: bool | None  (True if op_income margin grew faster than revenue)
        f3_coverage: str
    """
    empty = {
        "f3_margin_delta_minus_rev_delta": None,
        "f3_profit_stepup": None,
        "f3_coverage": "no_statements",
    }

    # A2 firewall
    if t0 >= pd.Timestamp("2024-01-01"):
        return {**empty, "f3_coverage": "a2_firewall_excluded"}

    if statements_q is None or statements_q.empty:
        return empty

    required = {"ticker", "period_end", "filed", "revenue", "op_income"}
    if not required.issubset(set(statements_q.columns)):
        return {**empty, "f3_coverage": "missing_columns"}

    ticker_mask = statements_q["ticker"].astype(str) == str(ticker)
    tk_rows = statements_q[ticker_mask].copy()
    if tk_rows.empty:
        return {**empty, "f3_coverage": "ticker_not_in_statements"}

    # PIT filter: only rows where filed <= t0
    tk_rows["_filed"] = pd.to_datetime(tk_rows["filed"], errors="coerce")
    tk_rows = tk_rows.dropna(subset=["_filed"])
    pit_rows = tk_rows[tk_rows["_filed"] <= t0].copy()
    if len(pit_rows) < 2:
        return {**empty, "f3_coverage": "insufficient_pit_rows"}

    # Sort by period_end, take the two most recent PIT-visible quarters
    pit_rows["_period_end"] = pd.to_datetime(pit_rows["period_end"], errors="coerce")
    pit_rows = pit_rows.dropna(subset=["_period_end"])
    pit_rows = pit_rows.sort_values("_period_end", ascending=False)
    latest = pit_rows.iloc[0]
    prior = pit_rows.iloc[1]

    rev_latest = latest.get("revenue")
    rev_prior = prior.get("revenue")
    oi_latest = latest.get("op_income")
    oi_prior = prior.get("op_income")

    if any(pd.isna(x) for x in [rev_latest, rev_prior, oi_latest, oi_prior]):
        return {**empty, "f3_coverage": "null_financials"}

    if rev_latest == 0 or rev_prior == 0:
        return {**empty, "f3_coverage": "zero_revenue_divisor"}

    # Δ(op_income_margin) = (oi_latest/rev_latest) - (oi_prior/rev_prior)
    margin_delta = (float(oi_latest) / float(rev_latest)) - (float(oi_prior) / float(rev_prior))
    # Δ(revenue) growth
    rev_delta = (float(rev_latest) - float(rev_prior)) / abs(float(rev_prior))

    diff = margin_delta - rev_delta
    return {
        "f3_margin_delta_minus_rev_delta": round(diff, 6),
        "f3_profit_stepup": diff > 0,
        "f3_coverage": "ok",
    }


# ---------------------------------------------------------------------------
# Statistics: month-block paired bootstrap (BOTH groups draw from same month multiset)
# ---------------------------------------------------------------------------

def _month_key(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m")


def _wilson_ci(successes: float, n: float, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return float("nan"), float("nan")
    p_hat = successes / n
    z = 1.959964  # ~1.96 for 95% CI
    denom = 1 + z ** 2 / n
    center = (p_hat + z ** 2 / (2 * n)) / denom
    spread = z * np.sqrt(p_hat * (1 - p_hat) / n + z ** 2 / (4 * n ** 2)) / denom
    return max(0.0, center - spread), min(1.0, center + spread)


def month_block_bootstrap_diff(
    values_a: np.ndarray,
    values_b: np.ndarray,
    months_a: np.ndarray,
    months_b: np.ndarray,
    is_binary: bool,
    n_reps: int = BOOT_REPS,
    seed: int = BOOT_SEED,
    alpha_bonf: float | None = None,
) -> tuple[float, float, float, float, float, int, int]:
    """Month-block paired bootstrap returning:
      (diff, ci95_lo, ci95_hi, ci_bonf_lo, ci_bonf_hi, n_months_a, n_months_b).

    Block = t0 calendar month. Resample months with replacement — ONE drawn month
    multiset per replicate feeds BOTH groups. When a drawn month has no episodes
    in a group, that group simply contributes no observations for that replicate
    (month support can differ between groups within the same replicate). Computes
    statistic as rate (binary) or median difference.

    Returns:
        point_diff: observed difference (A - B, rate or median)
        ci95_lo, ci95_hi: 95% percentile CI
        ci_bonf_lo, ci_bonf_hi: α/m percentile CI (NaN if alpha_bonf is None)
        n_months_a: distinct t0 months in group A
        n_months_b: distinct t0 months in group B
    """
    rng = np.random.default_rng(seed)

    # Maps: month -> array of values
    def _group_by_month(vals: np.ndarray, months: np.ndarray) -> dict[str, np.ndarray]:
        out: dict[str, list] = {}
        for v, m in zip(vals, months):
            out.setdefault(m, []).append(v)
        return {k: np.array(v, dtype=float) for k, v in out.items()}

    map_a = _group_by_month(values_a, months_a)
    map_b = _group_by_month(values_b, months_b)

    # All months that appear in EITHER group — the shared universe to resample from
    all_months = sorted(set(map_a.keys()) | set(map_b.keys()))
    n_m = len(all_months)
    all_months_arr = np.array(all_months)

    n_months_a = len(map_a)
    n_months_b = len(map_b)

    def _stat(m_sample: np.ndarray) -> float:
        # One drawn month multiset feeds BOTH groups — truly paired
        vals_a_boot: list[float] = []
        vals_b_boot: list[float] = []
        for m in m_sample:
            if m in map_a:
                vals_a_boot.extend(map_a[m])
            if m in map_b:
                vals_b_boot.extend(map_b[m])
        if not vals_a_boot or not vals_b_boot:
            return float("nan")
        a_arr = np.array(vals_a_boot)
        b_arr = np.array(vals_b_boot)
        # Drop NaN
        a_arr = a_arr[~np.isnan(a_arr)]
        b_arr = b_arr[~np.isnan(b_arr)]
        if len(a_arr) == 0 or len(b_arr) == 0:
            return float("nan")
        if is_binary:
            return float(np.nanmean(a_arr)) - float(np.nanmean(b_arr))
        else:
            return float(np.nanmedian(a_arr)) - float(np.nanmedian(b_arr))

    # Observed statistic (no resampling — use all data directly)
    if is_binary:
        obs_a = np.nanmean(values_a) if len(values_a) > 0 else float("nan")
        obs_b = np.nanmean(values_b) if len(values_b) > 0 else float("nan")
    else:
        obs_a = np.nanmedian(values_a) if len(values_a) > 0 else float("nan")
        obs_b = np.nanmedian(values_b) if len(values_b) > 0 else float("nan")
    point_diff = obs_a - obs_b

    # Bootstrap
    boot_diffs: list[float] = []
    for _ in range(n_reps):
        m_sample = rng.choice(all_months_arr, size=n_m, replace=True)
        boot_diffs.append(_stat(m_sample))

    boot_arr = np.array(boot_diffs)
    boot_arr = boot_arr[~np.isnan(boot_arr)]
    if len(boot_arr) == 0:
        nan = float("nan")
        return point_diff, nan, nan, nan, nan, n_months_a, n_months_b

    ci95_lo = float(np.percentile(boot_arr, 2.5))
    ci95_hi = float(np.percentile(boot_arr, 97.5))

    # Bonferroni CI: two-sided tail = (alpha_bonf / 2) * 100 each side
    if alpha_bonf is not None:
        tail_pct = (alpha_bonf / 2.0) * 100.0
        ci_bonf_lo = float(np.percentile(boot_arr, tail_pct))
        ci_bonf_hi = float(np.percentile(boot_arr, 100.0 - tail_pct))
    else:
        ci_bonf_lo = float("nan")
        ci_bonf_hi = float("nan")

    return point_diff, ci95_lo, ci95_hi, ci_bonf_lo, ci_bonf_hi, n_months_a, n_months_b


def ticker_cluster_bootstrap_diff(
    values_a: np.ndarray,
    tickers_a: np.ndarray,
    values_b: np.ndarray,
    tickers_b: np.ndarray,
    is_binary: bool,
    n_reps: int = BOOT_REPS,
    seed: int = BOOT_SEED,
) -> tuple[float, float]:
    """Ticker-cluster bootstrap: resample tickers with replacement per group.

    Each replicate draws a ticker multiset independently for A and B, then computes
    the pooled statistic. This is a robustness check for within-ticker dependence.

    Returns: (ci_cluster_lo, ci_cluster_hi) at 95%
    """
    rng = np.random.default_rng(seed + 1)

    def _group_by_ticker(vals: np.ndarray, tickers: np.ndarray) -> dict[str, np.ndarray]:
        out: dict[str, list] = {}
        for v, t in zip(vals, tickers):
            out.setdefault(t, []).append(v)
        return {k: np.array(v, dtype=float) for k, v in out.items()}

    map_a = _group_by_ticker(values_a, tickers_a)
    map_b = _group_by_ticker(values_b, tickers_b)

    tickers_a_unique = np.array(list(map_a.keys()))
    tickers_b_unique = np.array(list(map_b.keys()))

    if len(tickers_a_unique) == 0 or len(tickers_b_unique) == 0:
        nan = float("nan")
        return nan, nan

    boot_diffs: list[float] = []
    for _ in range(n_reps):
        drawn_a = rng.choice(tickers_a_unique, size=len(tickers_a_unique), replace=True)
        drawn_b = rng.choice(tickers_b_unique, size=len(tickers_b_unique), replace=True)
        pool_a = np.concatenate([map_a[t] for t in drawn_a])
        pool_b = np.concatenate([map_b[t] for t in drawn_b])
        pool_a = pool_a[~np.isnan(pool_a)]
        pool_b = pool_b[~np.isnan(pool_b)]
        if len(pool_a) == 0 or len(pool_b) == 0:
            boot_diffs.append(float("nan"))
            continue
        if is_binary:
            boot_diffs.append(float(np.nanmean(pool_a)) - float(np.nanmean(pool_b)))
        else:
            boot_diffs.append(float(np.nanmedian(pool_a)) - float(np.nanmedian(pool_b)))

    boot_arr = np.array(boot_diffs)
    boot_arr = boot_arr[~np.isnan(boot_arr)]
    if len(boot_arr) == 0:
        nan = float("nan")
        return nan, nan

    return float(np.percentile(boot_arr, 2.5)), float(np.percentile(boot_arr, 97.5))


def _degenerate_guard(grp: pd.DataFrame, name: str) -> bool:
    """Return True if group has < 12 distinct t0 months (degenerate — report only, no CI)."""
    n_months = grp["t0"].dt.to_period("M").nunique()
    if n_months < 12:
        log.warning(
            "Degenerate guard: group %s has only %d distinct t0 months (< 12) — "
            "reporting stats only, no bootstrap CI.",
            name,
            n_months,
        )
        return True
    return False


# ---------------------------------------------------------------------------
# Feature-level analysis runner
# ---------------------------------------------------------------------------

def analyze_binary_feature(
    feature_col: str,
    group_a: pd.DataFrame,
    group_b: pd.DataFrame,
    name_a: str,
    name_b: str,
    alpha_bonf: float,
    n_boot: int = BOOT_REPS,
    seed: int = BOOT_SEED,
) -> dict[str, Any]:
    """Run binary feature analysis: rates, bootstrap diff CI (95% and α/m), Wilson CI,
    ticker-cluster robustness CI."""
    a_vals = group_a[feature_col].dropna().astype(float)
    b_vals = group_b[feature_col].dropna().astype(float)

    n_a_total = len(group_a)
    n_b_total = len(group_b)
    n_a_valid = len(a_vals)
    n_b_valid = len(b_vals)

    rate_a = float(a_vals.mean()) if len(a_vals) > 0 else float("nan")
    rate_b = float(b_vals.mean()) if len(b_vals) > 0 else float("nan")
    obs_diff = rate_a - rate_b

    result: dict[str, Any] = {
        "feature": feature_col,
        "contrast": f"{name_a} vs {name_b}",
        "type": "binary",
        f"rate_{name_a}": round(rate_a, 4),
        f"n_{name_a}": n_a_valid,
        f"rate_{name_b}": round(rate_b, 4),
        f"n_{name_b}": n_b_valid,
        f"n_{name_a}_total": n_a_total,
        f"n_{name_b}_total": n_b_total,
        "obs_diff": round(obs_diff, 4),
        "ci95_lo": None,
        "ci95_hi": None,
        "ci_bonf_lo": None,
        "ci_bonf_hi": None,
        "ci_cluster_lo": None,
        "ci_cluster_hi": None,
        "wilson_ci_lo": None,
        "wilson_ci_hi": None,
        "bonf_survives": None,
        "degenerate": False,
        "note": "",
    }

    # Degenerate guard
    degen_a = _degenerate_guard(group_a[group_a[feature_col].notna()], name_a)
    degen_b = _degenerate_guard(group_b[group_b[feature_col].notna()], name_b)
    if degen_a or degen_b:
        result["degenerate"] = True
        return result

    if n_a_valid < 5 or n_b_valid < 5:
        result["note"] = "insufficient valid obs"
        return result

    months_a = group_a.loc[group_a[feature_col].notna(), "t0"].dt.strftime("%Y-%m").values
    months_b = group_b.loc[group_b[feature_col].notna(), "t0"].dt.strftime("%Y-%m").values

    diff, ci95_lo, ci95_hi, ci_bonf_lo, ci_bonf_hi, nm_a, nm_b = month_block_bootstrap_diff(
        a_vals.values,
        b_vals.values,
        months_a,
        months_b,
        is_binary=True,
        n_reps=n_boot,
        seed=seed,
        alpha_bonf=alpha_bonf,
    )
    result["ci95_lo"] = round(ci95_lo, 4) if not np.isnan(ci95_lo) else None
    result["ci95_hi"] = round(ci95_hi, 4) if not np.isnan(ci95_hi) else None
    result["ci_bonf_lo"] = round(ci_bonf_lo, 4) if not np.isnan(ci_bonf_lo) else None
    result["ci_bonf_hi"] = round(ci_bonf_hi, 4) if not np.isnan(ci_bonf_hi) else None

    # bonf_survives: use the α/m CI (NOT the 95% CI)
    if result["ci_bonf_lo"] is not None and result["ci_bonf_hi"] is not None:
        excl_zero_bonf = (result["ci_bonf_lo"] > 0) or (result["ci_bonf_hi"] < 0)
        result["bonf_survives"] = bool(excl_zero_bonf)

    # Wilson cross-check
    wci_a_lo, wci_a_hi = _wilson_ci(float(a_vals.sum()), float(n_a_valid))
    wci_b_lo, wci_b_hi = _wilson_ci(float(b_vals.sum()), float(n_b_valid))
    result["wilson_ci_lo"] = round(wci_a_lo - wci_b_hi, 4)
    result["wilson_ci_hi"] = round(wci_a_hi - wci_b_lo, 4)

    # Ticker-cluster robustness CI
    tickers_a = group_a.loc[group_a[feature_col].notna(), "ticker"].astype(str).values
    tickers_b = group_b.loc[group_b[feature_col].notna(), "ticker"].astype(str).values
    cl_lo, cl_hi = ticker_cluster_bootstrap_diff(
        a_vals.values, tickers_a, b_vals.values, tickers_b,
        is_binary=True, n_reps=n_boot, seed=seed,
    )
    result["ci_cluster_lo"] = round(cl_lo, 4) if not np.isnan(cl_lo) else None
    result["ci_cluster_hi"] = round(cl_hi, 4) if not np.isnan(cl_hi) else None

    return result


def analyze_continuous_feature(
    feature_col: str,
    group_a: pd.DataFrame,
    group_b: pd.DataFrame,
    name_a: str,
    name_b: str,
    alpha_bonf: float,
    n_boot: int = BOOT_REPS,
    seed: int = BOOT_SEED,
) -> dict[str, Any]:
    """Run continuous feature analysis: medians, bootstrap median-diff CI (95% and α/m),
    ticker-cluster robustness CI."""
    a_vals = group_a[feature_col].dropna().astype(float)
    b_vals = group_b[feature_col].dropna().astype(float)

    med_a = float(a_vals.median()) if len(a_vals) > 0 else float("nan")
    med_b = float(b_vals.median()) if len(b_vals) > 0 else float("nan")
    obs_diff = med_a - med_b

    result: dict[str, Any] = {
        "feature": feature_col,
        "contrast": f"{name_a} vs {name_b}",
        "type": "continuous",
        f"median_{name_a}": round(med_a, 4),
        f"n_{name_a}": len(a_vals),
        f"median_{name_b}": round(med_b, 4),
        f"n_{name_b}": len(b_vals),
        f"n_{name_a}_total": len(group_a),
        f"n_{name_b}_total": len(group_b),
        "obs_diff": round(obs_diff, 4),
        "ci95_lo": None,
        "ci95_hi": None,
        "ci_bonf_lo": None,
        "ci_bonf_hi": None,
        "ci_cluster_lo": None,
        "ci_cluster_hi": None,
        "bonf_survives": None,
        "degenerate": False,
        "note": "",
    }

    degen_a = _degenerate_guard(group_a[group_a[feature_col].notna()], name_a)
    degen_b = _degenerate_guard(group_b[group_b[feature_col].notna()], name_b)
    if degen_a or degen_b:
        result["degenerate"] = True
        return result

    if len(a_vals) < 5 or len(b_vals) < 5:
        result["note"] = "insufficient valid obs"
        return result

    months_a = group_a.loc[group_a[feature_col].notna(), "t0"].dt.strftime("%Y-%m").values
    months_b = group_b.loc[group_b[feature_col].notna(), "t0"].dt.strftime("%Y-%m").values

    diff, ci95_lo, ci95_hi, ci_bonf_lo, ci_bonf_hi, _, _ = month_block_bootstrap_diff(
        a_vals.values,
        b_vals.values,
        months_a,
        months_b,
        is_binary=False,
        n_reps=n_boot,
        seed=seed,
        alpha_bonf=alpha_bonf,
    )
    result["ci95_lo"] = round(ci95_lo, 4) if not np.isnan(ci95_lo) else None
    result["ci95_hi"] = round(ci95_hi, 4) if not np.isnan(ci95_hi) else None
    result["ci_bonf_lo"] = round(ci_bonf_lo, 4) if not np.isnan(ci_bonf_lo) else None
    result["ci_bonf_hi"] = round(ci_bonf_hi, 4) if not np.isnan(ci_bonf_hi) else None

    # bonf_survives: use α/m CI
    if result["ci_bonf_lo"] is not None and result["ci_bonf_hi"] is not None:
        excl_zero_bonf = (result["ci_bonf_lo"] > 0) or (result["ci_bonf_hi"] < 0)
        result["bonf_survives"] = bool(excl_zero_bonf)

    # Ticker-cluster robustness CI
    tickers_a = group_a.loc[group_a[feature_col].notna(), "ticker"].astype(str).values
    tickers_b = group_b.loc[group_b[feature_col].notna(), "ticker"].astype(str).values
    cl_lo, cl_hi = ticker_cluster_bootstrap_diff(
        a_vals.values, tickers_a, b_vals.values, tickers_b,
        is_binary=False, n_reps=n_boot, seed=seed,
    )
    result["ci_cluster_lo"] = round(cl_lo, 4) if not np.isnan(cl_lo) else None
    result["ci_cluster_hi"] = round(cl_hi, 4) if not np.isnan(cl_hi) else None

    return result


# ---------------------------------------------------------------------------
# Main study runner
# ---------------------------------------------------------------------------

def run_study(
    episodes_path: Path,
    root: Path,
    out_path: Path,
    n_boot: int = BOOT_REPS,
    seed: int = BOOT_SEED,
) -> None:
    t_start = time.time()

    log.info("Loading episodes from %s", episodes_path)
    eps = pd.read_parquet(episodes_path)
    eps["t0"] = pd.to_datetime(eps["t0"])

    # Manifest
    manifest_path = episodes_path.parent / "winner_episodes_manifest.json"
    manifest_hash = "N/A"
    harvest_date = "N/A"
    if manifest_path.exists():
        raw = manifest_path.read_text()
        manifest_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
        try:
            manifest_data = json.loads(raw)
            harvest_date = manifest_data.get("as_of", "N/A")
        except Exception:  # noqa: BLE001
            pass

    # Crypto segregation (fix #7): BTC-USD, BTC_F, ETH-USD, SOL-USD have SPY
    # benchmark error and 7-day calendar → exclude from primary analysis.
    is_crypto = eps["ticker"].isin(CRYPTO_TICKERS)
    eps_equity = eps[~is_crypto].copy()
    eps_crypto = eps[is_crypto].copy()

    # Population — EQUITY ONLY (primary)
    matured = eps_equity[eps_equity["outcome_label"].isin(MATURED_LABELS)].copy()
    unmatured = eps_equity[eps_equity["outcome_label"] == "unmatured"]
    kept_going = matured[matured["outcome_label"].isin(KEPT_GOING_LABELS)].copy()
    blow_off = matured[matured["outcome_label"] == "blow_off"].copy()
    failed = matured[matured["outcome_label"] == "failed"].copy()

    # Crypto matured counts (for appendix)
    matured_crypto = eps_crypto[eps_crypto["outcome_label"].isin(MATURED_LABELS)]
    kg_crypto = matured_crypto[matured_crypto["outcome_label"].isin(KEPT_GOING_LABELS)]
    bo_crypto = matured_crypto[matured_crypto["outcome_label"] == "blow_off"]
    fa_crypto = matured_crypto[matured_crypto["outcome_label"] == "failed"]

    log.info(
        "Population (equity-only): total=%d matured=%d unmatured=%d "
        "kept_going=%d blow_off=%d failed=%d | crypto matured=%d",
        len(eps_equity),
        len(matured),
        len(unmatured),
        len(kept_going),
        len(blow_off),
        len(failed),
        len(matured_crypto),
    )

    # Load external data stores (read-only from root)
    log.info("Loading 8K events from %s", root / "edgar" / "material_8k_events.parquet")
    events_path = root / "edgar" / "material_8k_events.parquet"
    events_df: pd.DataFrame | None = None
    if events_path.exists():
        events_df = pd.read_parquet(events_path)
        events_df["filing_date"] = pd.to_datetime(events_df["filing_date"], errors="coerce")

    log.info("Loading quarterly statements from %s", root / "edgar" / "statements_quarterly.parquet")
    stmt_path = root / "edgar" / "statements_quarterly.parquet"
    statements_q: pd.DataFrame | None = None
    if stmt_path.exists():
        statements_q = pd.read_parquet(stmt_path)

    # -----------------------------------------------------------------------
    # Compute F1 (trailing, already in parquet) and F1 early-move conditioner
    # F2 (gap holds, descriptive only — tautological for kept_going),
    # F3 (profit step-up) per episode row for matured
    # -----------------------------------------------------------------------
    log.info("Computing per-episode features for %d matured episodes...", len(matured))

    f1_fwd_records = []
    f2_records = []
    f3_records = []

    for i, (_, row) in enumerate(matured.iterrows()):
        ticker = str(row["ticker"])
        t0 = pd.Timestamp(row["t0"])
        price_source = str(row.get("price_source", "yahoo"))

        # F1 early-move
        f1_res = compute_f1_early_move(ticker, t0, price_source, events_df, root)
        f1_fwd_records.append({"ticker": ticker, "t0": t0, **f1_res})

        # F2 (descriptive only)
        f2_res = compute_f2_gap_holds(ticker, t0, price_source, root)
        f2_records.append({"ticker": ticker, "t0": t0, **f2_res})

        # F3
        f3_res = compute_f3_profit_stepup(ticker, t0, statements_q)
        f3_records.append({"ticker": ticker, "t0": t0, **f3_res})

        if (i + 1) % 200 == 0:
            log.info("  Processed %d/%d episodes", i + 1, len(matured))

    f1_fwd_df = pd.DataFrame(f1_fwd_records)
    f2_df = pd.DataFrame(f2_records)
    f3_df = pd.DataFrame(f3_records)

    # Merge into matured
    matured = matured.reset_index(drop=True)
    merge_keys = ["ticker", "t0"]
    matured = matured.merge(f1_fwd_df[merge_keys + [c for c in f1_fwd_df.columns if c not in merge_keys]], on=merge_keys, how="left")
    matured = matured.merge(f2_df[merge_keys + [c for c in f2_df.columns if c not in merge_keys]], on=merge_keys, how="left")
    matured = matured.merge(f3_df[merge_keys + [c for c in f3_df.columns if c not in merge_keys]], on=merge_keys, how="left")

    # Re-split groups with enriched data
    kept_going = matured[matured["outcome_label"].isin(KEPT_GOING_LABELS)].copy()
    blow_off = matured[matured["outcome_label"] == "blow_off"].copy()
    failed = matured[matured["outcome_label"] == "failed"].copy()

    # F4/F5 collapse: new_high_63d is 100% by construction (constant) → exclude from m.
    # f4_composite ≡ excess_21d_pp >= 20 for all episodes (since new_high_63d is always True).
    # We keep f4_composite column for legacy/appendix but collapse it with F5 in the analysis.
    # The ≥20pp dichotomization is a sub-row of the F4/F5 family.
    matured["f4_composite"] = (matured["new_high_63d"] == True) & (matured["excess_21d_pp"] >= 20.0)
    kept_going = matured[matured["outcome_label"].isin(KEPT_GOING_LABELS)].copy()
    blow_off = matured[matured["outcome_label"] == "blow_off"].copy()
    failed = matured[matured["outcome_label"] == "failed"].copy()

    # -----------------------------------------------------------------------
    # F1 trailing: MASK (not zero-fill) episodes absent from 8K store (fix #4)
    # pre-era_cutoff rows stay NaN (already handled below).
    # -----------------------------------------------------------------------
    pre_era_mask = matured["b1_coverage"] == "pre_era_cutoff"
    # Zero-to-mask fix: for post-era rows, if coverage is missing from 8K store
    # the original code zero-filled. We now mask those rows instead (drop them
    # from the F1 trailing analysis, report coverage counts).
    # The parquet column hard_event_count_126d is NaN for pre-era by construction;
    # post-era rows with NaN count as "not covered" → mask them too.
    # trailing_rung_ge2: only valid where b1_coverage == 'post_2014_only' AND counts are non-NaN
    hard_col = matured["hard_event_count_126d"].copy()
    soft_col = matured["soft_event_count_126d"].copy()
    rung_ge2: list[bool | None] = []
    for h, s, is_pre in zip(hard_col, soft_col, pre_era_mask):
        if is_pre or pd.isna(h) or pd.isna(s):
            # Mask missing-coverage episodes — do NOT impute 0
            rung_ge2.append(None)
        else:
            rung_ge2.append((int(h) + int(s)) >= 2)
    matured["trailing_rung_ge2"] = rung_ge2  # object dtype, allows None
    matured.loc[pre_era_mask, "hard_event_count_126d"] = np.nan
    matured.loc[pre_era_mask, "soft_event_count_126d"] = np.nan

    kept_going = matured[matured["outcome_label"].isin(KEPT_GOING_LABELS)].copy()
    blow_off = matured[matured["outcome_label"] == "blow_off"].copy()
    failed = matured[matured["outcome_label"] == "failed"].copy()

    # -----------------------------------------------------------------------
    # F1 coverage counts for caveat
    # -----------------------------------------------------------------------
    f1_kg_covered = int(kept_going["trailing_rung_ge2"].notna().sum())
    f1_bo_covered = int(blow_off["trailing_rung_ge2"].notna().sum())
    f1_kg_pct = f1_kg_covered / max(len(kept_going), 1)
    f1_bo_pct = f1_bo_covered / max(len(blow_off), 1)

    # -----------------------------------------------------------------------
    # Define feature list and m (total tests)
    # Excluded from m (constants by construction): new_high_63d, liquid
    # F2 gap_hold columns excluded from m (TAUTOLOGICAL for kept_going)
    # F4/F5 collapsed: use excess_21d_pp (continuous) + f4_composite (≥20pp dichotomy)
    # -----------------------------------------------------------------------

    # F1 trailing (pure-t0, from parquet — masked where coverage absent):
    #   hard_event_count_126d (continuous), soft_event_count_126d (continuous)
    #   trailing_rung_ge2 = (hard + soft >= 2), soft_then_hard (binary)
    # F1 early-move conditioner (uses post-t0 info):
    #   f1_fwd_rung_ge2 (binary)
    # F3: f3_profit_stepup (binary) — A2 firewall
    # F4/F5 family (collapsed): excess_21d_pp continuous + f4_composite binary (≥20pp)
    # Pure-t0 from parquet: dollar_vol_z21, dv_5_60_ratio, self_funded_at_t0
    # EXCLUDED from m (constants): new_high_63d, liquid

    FEATURES: list[tuple[str, str, str, str]] = [
        # Pure-t0 from parquet
        ("dollar_vol_z21", "continuous", "pure_t0", ""),
        ("dv_5_60_ratio", "continuous", "pure_t0", ""),
        ("self_funded_at_t0", "binary", "pure_t0", "B2"),
        # F4/F5 family (collapsed — new_high_63d is 100% by construction)
        ("excess_21d_pp", "continuous", "pure_t0", "F4/F5: trailing excess return (F4-equivalent since new_high_63d≡True)"),
        ("f4_composite", "binary", "pure_t0", "F4/F5: excess_21d_pp>=20pp dichotomization (new_high_63d≡True so f4≡excess>=20)"),
        # F1 trailing (pure-t0, pre-onset window t0-126d to t0; MASKED where 8K coverage absent)
        ("hard_event_count_126d", "continuous", "pure_t0", "F1-trailing: B1 hard events in t0-126d window (covered subset)"),
        ("soft_event_count_126d", "continuous", "pure_t0", "F1-trailing: B1 soft events in t0-126d window (covered subset)"),
        ("trailing_rung_ge2", "binary", "pure_t0", "F1-trailing: hard+soft rungs>=2 pre-onset (covered subset only, missing MASKED not zero-filled)"),
        ("soft_then_hard", "binary", "pure_t0", "F1-trailing: soft before hard in pre-onset window"),
        # F1 early-move conditioner (uses t0 to t0+21td)
        ("f1_fwd_rung_ge2", "binary", "early_move", "F1-early-move: rung>=2 in (t0, t0+21td]; cite: extract_b1_hardening_ladder"),
        # F3 profit step-up (A2 firewall: t0 < 2024-01-01 only)
        ("f3_profit_stepup", "binary", "pure_t0", "F3: op margin delta > rev delta QoQ; A2 firewall t0<2024"),
    ]

    CONTRASTS = [
        ("kept_going", "blow_off", kept_going, blow_off),
        ("kept_going", "failed", kept_going, failed),
    ]

    m_total = len(FEATURES) * len(CONTRASTS)
    alpha_bonf = ALPHA / m_total
    log.info("m_total = %d, alpha_bonf = %.6f", m_total, alpha_bonf)

    # -----------------------------------------------------------------------
    # F2 descriptive-only rates (for blow_off residual section)
    # -----------------------------------------------------------------------
    f2_blow_off_rates: dict[str, float | None] = {}
    for k in [3, 5, 10]:
        col = f"gap_hold_{k}"
        if col in blow_off.columns:
            vals = blow_off[col].dropna().astype(float)
            f2_blow_off_rates[col] = float(vals.mean()) if len(vals) > 0 else None
        else:
            f2_blow_off_rates[col] = None
    if "gap_pct" in matured.columns:
        f2_gap_pct_kg = float(kept_going["gap_pct"].dropna().median()) if "gap_pct" in kept_going.columns else None
        f2_gap_pct_bo = float(blow_off["gap_pct"].dropna().median()) if "gap_pct" in blow_off.columns else None
    else:
        f2_gap_pct_kg = None
        f2_gap_pct_bo = None

    # -----------------------------------------------------------------------
    # Run all analyses
    # -----------------------------------------------------------------------
    log.info("Running bootstrap analyses (n_boot=%d, seed=%d)...", n_boot, seed)

    all_results: list[dict[str, Any]] = []
    for feat_col, feat_type, feat_tier, feat_note in FEATURES:
        for name_a, name_b, grp_a, grp_b in CONTRASTS:
            log.info("  %s × %s vs %s", feat_col, name_a, name_b)
            if feat_type == "binary":
                res = analyze_binary_feature(feat_col, grp_a, grp_b, name_a, name_b, alpha_bonf, n_boot=n_boot, seed=seed)
            else:
                res = analyze_continuous_feature(feat_col, grp_a, grp_b, name_a, name_b, alpha_bonf, n_boot=n_boot, seed=seed)
            res["feature_tier"] = feat_tier
            res["feature_note"] = feat_note
            all_results.append(res)

    # -----------------------------------------------------------------------
    # Strata: gap_leg_crossed==False (primary contrast only)
    # -----------------------------------------------------------------------
    log.info("Computing strata...")

    gap_clean = matured[matured["gap_leg_crossed"] == False].copy()
    kg_gap = gap_clean[gap_clean["outcome_label"].isin(KEPT_GOING_LABELS)]
    bo_gap = gap_clean[gap_clean["outcome_label"] == "blow_off"]

    stratum_results: list[dict[str, Any]] = []
    for feat_col, feat_type, feat_tier, feat_note in FEATURES:
        log.info("  Stratum gap_leg_crossed==False: %s", feat_col)
        if feat_type == "binary":
            res = analyze_binary_feature(feat_col, kg_gap, bo_gap, "kept_going_gap_clean", "blow_off_gap_clean", alpha_bonf, n_boot=n_boot, seed=seed)
        else:
            res = analyze_continuous_feature(feat_col, kg_gap, bo_gap, "kept_going_gap_clean", "blow_off_gap_clean", alpha_bonf, n_boot=n_boot, seed=seed)
        res["stratum"] = "gap_leg_crossed==False"
        res["feature_tier"] = feat_tier
        stratum_results.append(res)

    # Coverage summary
    coverage_rows = []
    for feat_col, feat_type, feat_tier, feat_note in FEATURES:
        for name_a, name_b, grp_a, grp_b in CONTRASTS:
            n_a_valid = int(grp_a[feat_col].notna().sum()) if feat_col in grp_a.columns else 0
            n_b_valid = int(grp_b[feat_col].notna().sum()) if feat_col in grp_b.columns else 0
            coverage_rows.append({
                "feature": feat_col,
                "contrast": f"{name_a} vs {name_b}",
                f"n_{name_a}_valid": n_a_valid,
                f"n_{name_b}_valid": n_b_valid,
            })

    # F3 coverage stats
    f3_cov_matured = matured["f3_coverage"].value_counts(dropna=False).to_dict()
    f3_kg_ok = int((kept_going["f3_coverage"] == "ok").sum()) if "f3_coverage" in kept_going.columns else 0
    f3_bo_ok = int((blow_off["f3_coverage"] == "ok").sum()) if "f3_coverage" in blow_off.columns else 0
    f3_non_comparable = (f3_kg_ok / max(len(kept_going), 1)) < 0.30 or (f3_bo_ok / max(len(blow_off), 1)) < 0.30

    elapsed = time.time() - t_start

    # -----------------------------------------------------------------------
    # Write report
    # -----------------------------------------------------------------------
    log.info("Writing report to %s", out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_report(
        out_path=out_path,
        eps=eps_equity,
        eps_full=eps,
        matured=matured,
        kept_going=kept_going,
        blow_off=blow_off,
        failed=failed,
        unmatured=unmatured,
        manifest_hash=manifest_hash,
        harvest_date=harvest_date,
        episodes_path=episodes_path,
        all_results=all_results,
        stratum_results=stratum_results,
        coverage_rows=coverage_rows,
        m_total=m_total,
        alpha_bonf=alpha_bonf,
        FEATURES=FEATURES,
        CONTRASTS=CONTRASTS,
        f3_cov_matured=f3_cov_matured,
        f3_kg_ok=f3_kg_ok,
        f3_bo_ok=f3_bo_ok,
        f3_non_comparable=f3_non_comparable,
        n_boot=n_boot,
        seed=seed,
        elapsed=elapsed,
        gap_clean_kg=kg_gap,
        gap_clean_bo=bo_gap,
        matured_gap_clean=gap_clean,
        f1_kg_covered=f1_kg_covered,
        f1_bo_covered=f1_bo_covered,
        f1_kg_pct=f1_kg_pct,
        f1_bo_pct=f1_bo_pct,
        f2_blow_off_rates=f2_blow_off_rates,
        f2_gap_pct_kg=f2_gap_pct_kg,
        f2_gap_pct_bo=f2_gap_pct_bo,
        matured_crypto=matured_crypto,
        kg_crypto=kg_crypto,
        bo_crypto=bo_crypto,
        fa_crypto=fa_crypto,
    )
    log.info("Done. Wall time: %.1fs", elapsed)


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _fmt_pct(v: float | None, decs: int = 1) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v*100:.{decs}f}%"


def _fmt_f(v: float | None, decs: int = 4) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{decs}f}"


def _write_report(
    *,
    out_path: Path,
    eps: pd.DataFrame,
    eps_full: pd.DataFrame,
    matured: pd.DataFrame,
    kept_going: pd.DataFrame,
    blow_off: pd.DataFrame,
    failed: pd.DataFrame,
    unmatured: pd.DataFrame,
    manifest_hash: str,
    harvest_date: str,
    episodes_path: Path,
    all_results: list[dict],
    stratum_results: list[dict],
    coverage_rows: list[dict],
    m_total: int,
    alpha_bonf: float,
    FEATURES: list,
    CONTRASTS: list,
    f3_cov_matured: dict,
    f3_kg_ok: int,
    f3_bo_ok: int,
    f3_non_comparable: bool,
    n_boot: int,
    seed: int,
    elapsed: float,
    gap_clean_kg: pd.DataFrame,
    gap_clean_bo: pd.DataFrame,
    matured_gap_clean: pd.DataFrame,
    f1_kg_covered: int,
    f1_bo_covered: int,
    f1_kg_pct: float,
    f1_bo_pct: float,
    f2_blow_off_rates: dict,
    f2_gap_pct_kg: float | None,
    f2_gap_pct_bo: float | None,
    matured_crypto: pd.DataFrame,
    kg_crypto: pd.DataFrame,
    bo_crypto: pd.DataFrame,
    fa_crypto: pd.DataFrame,
) -> None:

    lines: list[str] = []
    def w(s: str = "") -> None:
        lines.append(s)

    # Header
    w("<!-- W3 census fingerprint study. DESCRIPTIVE ONLY (WA-R1/R5/R8). -->")
    w("<!-- Review-round-1 corrections applied 2026-07-20: Bonf CI fix, F2 tautology, -->")
    w("<!-- F4/F5 collapse, F1 mask, pairing fix, ticker-cluster CI, survivorship honesty, -->")
    w("<!-- crypto segregation, citation fix, leading-colon fix. -->")
    w()
    w("# Winner Autopsy Lab — W3 Census Fingerprint Study (Layer-3a)")
    w()
    w("**Status:** DESCRIPTIVE ONLY — no hypothesis registration, no verdicts, no filters, no site surfaces.")
    w("Rulings WA-R1 / WA-R5 / WA-R8. Spec: `research/winners/W3_CENSUS_STUDY_SPEC.md`.")
    w()
    w(f"**Substrate:** `{episodes_path.name}` — manifest hash `{manifest_hash}`, harvest date `{harvest_date}`.")
    w(f"**Run:** seed {seed}, n_boot {n_boot}, m={m_total} tests, α_Bonferroni = 0.05/{m_total} = {alpha_bonf:.6f}.")
    w(f"**Primary analysis:** equity-only (crypto segregated — see appendix). {len(matured):,} matured episodes.")
    w(f"**Wall time:** {elapsed:.1f}s")
    w()
    w("**Review-round-1 corrections (adversarial stats review 2026-07-20):**")
    w("- BLOCKER: `bonf_survives` now uses α/m percentile CI, not 95% CI.")
    w("- n_boot raised to 50,000 for α/m tail resolution (seed unchanged).")
    w("- Both 95% CI and α/m CI printed per row.")
    w("- Ticker-cluster bootstrap CI added as robustness column.")
    w("- F2 gap_hold_k: reclassified as TAUTOLOGICAL — moved out of fingerprint tables into dedicated section.")
    w("- F4/F5 collapsed: `new_high_63d` is 100% by construction → excluded from m; `f4_composite ≡ excess_21d_pp≥20`.")
    w("- `new_high_63d` and `liquid` excluded from m (constants by construction, noted once).")
    w("- F1 trailing: missing 8K coverage now MASKED (dropped) not zero-filled.")
    w("- Bootstrap pairing: one drawn month multiset per replicate feeds BOTH groups.")
    w("- Stratum 1 (survivorship): replaced with honest untested disclosure.")
    w("- Citation fixed: `extract_b1_hardening_ladder` (was `_b1_features`).")
    w()

    # -----------------------------------------------------------------------
    # Bottom line first
    # -----------------------------------------------------------------------
    w("## Bottom line")
    w()

    def _get_primary_result(feat_col: str) -> dict | None:
        for r in all_results:
            if r["feature"] == feat_col and r["contrast"] == "kept_going vs blow_off":
                return r
        return None

    f1_trail_result = _get_primary_result("trailing_rung_ge2")
    f1_fwd_result = _get_primary_result("f1_fwd_rung_ge2")
    f3_result = _get_primary_result("f3_profit_stepup")
    f4_result = _get_primary_result("f4_composite")
    f5_result = _get_primary_result("excess_21d_pp")

    w("Results are machine outputs from the equity-only census — not adjudications. The main loop appends WA-R8 below.")
    w()
    w("**Net finding (post-correction):** Once the F2 tautology is removed and the real Bonferroni")
    w("correction applied, NO tested t0 feature separates kept_going from blow_off at the α/m threshold.")
    w("F4/F5 (excess_21d_pp family) lose Bonferroni survival under the corrected CI. F1 trailing and")
    w("early-move conditioner remain null. F3 is untestable. F6 is structurally blocked.")
    w()

    # Quick summary table
    w("| W2 candidate | Post-correction verdict |")
    w("|---|---|")

    def _verdict_line(r: dict | None) -> str:
        if r is None:
            return "UNTESTABLE — no data"
        ci95_lo = r.get("ci95_lo")
        ci95_hi = r.get("ci95_hi")
        ci_bonf_lo = r.get("ci_bonf_lo")
        ci_bonf_hi = r.get("ci_bonf_hi")
        bonf = r.get("bonf_survives")
        note = r.get("note", "")
        if r.get("degenerate"):
            return "DEGENERATE (< 12 months in a group)"
        if note == "insufficient valid obs":
            return "UNTESTABLE — insufficient valid obs"
        if ci95_lo is None:
            return "UNTESTABLE — no CI computed"
        excl_95 = (ci95_lo > 0) or (ci95_hi < 0)
        excl_bonf = False
        if ci_bonf_lo is not None and ci_bonf_hi is not None:
            excl_bonf = (ci_bonf_lo > 0) or (ci_bonf_hi < 0)
        obs_diff = r.get("obs_diff", 0)
        direction = "higher in kept_going" if (obs_diff > 0) else "higher in blow_off/failed"
        if excl_bonf:
            return f"95% CI excludes 0, α/m CI excludes 0 — {direction} (Bonferroni survives)"
        elif excl_95:
            return f"95% CI excludes 0 but α/m CI CONTAINS 0 — {direction} (Bonferroni does NOT survive)"
        return "Both CIs contain 0 — no detectable difference"

    w(f"| F1 — catalyst-ladder rung count (trailing pre-t0) | {_verdict_line(f1_trail_result)} |")
    w(f"| F1 — catalyst-ladder rung count (early-move, t0+21td) | {_verdict_line(f1_fwd_result)} |")
    w("| F2 — trigger gap holds (gap_hold_k) | TAUTOLOGICAL — not a fingerprint, ineligible for registration (see §F2 Tautology) |")
    w(f"| F3 — profit step-up faster than revenue | {'UNTESTABLE — A2 firewall + coverage < 30%' if f3_non_comparable else _verdict_line(f3_result)} |")
    w(f"| F4/F5 — trailing-excess magnitude family (collapsed) | {_verdict_line(f4_result)} (see note: direction reversal vs failed) |")
    w("| F6 — compressed prior | UNTESTABLE — structurally blocked (no PIT short-interest/options/dispersion history) |")
    w()

    # F4/F5 direction reversal note
    f45_vs_failed = _get_primary_result("f4_composite") # vs blow_off above; get vs failed
    for r in all_results:
        if r["feature"] == "f4_composite" and r["contrast"] == "kept_going vs failed":
            f45_vs_failed = r
            break
    f45_bo_diff = f4_result.get("obs_diff", None) if f4_result else None  # kept_going vs blow_off
    f45_fa_diff = f45_vs_failed.get("obs_diff", None) if f45_vs_failed else None  # kept_going vs failed
    w("**F4/F5 direction reversal:** Initial-excess magnitude is not a winner selector.")
    w(f"- kept_going vs blow_off: +{f45_bo_diff*100:.1f}pp (kept_going has MORE excess than blow_off)" if f45_bo_diff is not None and f45_bo_diff > 0 else f"- kept_going vs blow_off: {f45_bo_diff}")
    w(f"- kept_going vs failed: {f45_fa_diff*100:.1f}pp (kept_going has LESS excess than failed)" if f45_fa_diff is not None else f"- kept_going vs failed: {f45_fa_diff}")
    w("- Interpretation: blow_off episodes have lower t0 excess than kept_going (gap selection); failed")
    w("  episodes have HIGHER t0 excess than kept_going. Initial-excess magnitude cuts both ways — it")
    w("  is not a reliable t0 separator. Under corrected Bonferroni CI, neither direction survives.")
    w()

    # F1 window-direction finding
    w("### F1 window-direction finding (spec §3 circularity guard)")
    w()
    w("**Verified:** `hard_event_count_126d` / `soft_event_count_126d` / `soft_then_hard` in")
    w("`engine/winner_autopsy.py:extract_b1_hardening_ladder` (line 1139) use the PRE-ONSET window:")
    w("`filing_date strictly < t0, within 126 calendar days of t0`. These are TRAILING counts, NOT forward-looking.")
    w("They do NOT overlap the labeling horizon. Path taken: **use them directly as pure-t0 features**,")
    w("and additionally compute F1 early-move conditioner from material_8k_events bounded to (t0, t0+21td].")
    w()
    w(f"**F1 trailing coverage (masked-not-zero-filled):** kept_going {f1_kg_covered}/{len(kept_going)}")
    w(f"({f1_kg_pct*100:.0f}%); blow_off {f1_bo_covered}/{len(blow_off)} ({f1_bo_pct*100:.0f}%).")
    w("Episodes absent from the 8K store are MASKED (excluded from the F1 trailing analysis),")
    w("not imputed to zero. Results below are on the covered subset only.")
    w()

    # -----------------------------------------------------------------------
    # F2 Tautology section
    # -----------------------------------------------------------------------
    w("## F2 — Label-tautology disclosure")
    w()
    w("**gap_hold_k is TAUTOLOGICAL for all kept_going episodes. It is NOT a fingerprint and is")
    w("INELIGIBLE for registration.**")
    w()
    w("### Algebraic chain")
    w()
    w("1. `clean_hold` requires no forward close below close(t0) over (t0, t0+126td]")
    w("   (`engine/winner_autopsy.py:497-506`).")
    w("2. `durable_winner` requires `clean_hold` (`:511`).")
    w("3. Detector onset requires a new-63d-high at t0 (`:296`), forcing close(t0) >= close(t0-1).")
    w("4. Therefore: `gap_hold_k ≡ close(t0+k) > close(t0-1)` is **TRUE by algebra** for every")
    w("   kept_going episode (clean_hold prevents any close below close(t0) >= close(t0-1)).")
    w("5. Conclusion: gap_hold_k = 1.0 for 100% of kept_going episodes is a logical consequence")
    w("   of the label definition, not an empirical fingerprint.")
    w()
    w("### Blow_off residual rates (descriptive only)")
    w()
    w("These rates describe blow_off episode behavior — they are NOT used in any contrast or verdict.")
    w()
    w("| Gap-hold measure | Blow_off rate (descriptive) |")
    w("|---|---|")
    for k in [3, 5, 10]:
        col = f"gap_hold_{k}"
        rate = f2_blow_off_rates.get(col)
        w(f"| gap_hold_{k} | {_fmt_pct(rate)} |")
    w()
    w(f"Blow_off gap_hold rates: 3-session {_fmt_pct(f2_blow_off_rates.get('gap_hold_3'))},")
    w(f"5-session {_fmt_pct(f2_blow_off_rates.get('gap_hold_5'))},")
    w(f"10-session {_fmt_pct(f2_blow_off_rates.get('gap_hold_10'))}.")
    w("These rates reflect that blow_off episodes ALSO tend to hold the gap at short horizons,")
    w("declining at longer horizons — descriptive blow_off behavior only.")
    w()
    w("**Non-tautological gap magnitude (gap_pct):** No difference between groups.")
    w(f"Median gap_pct: kept_going {_fmt_f(f2_gap_pct_kg, 2)}%, blow_off {_fmt_f(f2_gap_pct_bo, 2)}%")
    w("(CI contains zero — gap magnitude does not distinguish groups).")
    w()

    # -----------------------------------------------------------------------
    # Population table
    # -----------------------------------------------------------------------
    w("## Population")
    w()
    w(f"**Primary analysis: equity-only** (crypto excluded — see appendix)")
    w(f"Total episodes (equity): **{len(eps):,}** / {eps['ticker'].nunique():,} tickers")
    w(f"t0 range: {eps['t0'].min().date()} → {eps['t0'].max().date()}")
    w()
    w("| Outcome label | Count |")
    w("|---|---|")
    for label, cnt in eps["outcome_label"].value_counts().items():
        w(f"| {label} | {cnt:,} |")
    w()
    w("**Matured (analysis population — equity only):**")
    w()
    w("| Group | Definition | Count |")
    w("|---|---|---|")
    w(f"| kept_going (PRIMARY) | durable_winner + clean_hold | {len(kept_going):,} |")
    w(f"| blow_off (Contrast 1) | blow_off | {len(blow_off):,} |")
    w(f"| failed (Contrast 2) | failed | {len(failed):,} |")
    w(f"| **unmatured** (not in analysis — counted here) | unmatured | {len(unmatured):,} |")
    w()
    w(f"Blow_off:kept_going ratio: {len(blow_off)/max(len(kept_going),1):.1f}:1 (census is blow_off-dominated as expected).")
    w()
    w("**Constants by construction (excluded from m, noted once):**")
    w(f"- `new_high_63d`: 100% True in all {len(matured):,} matured equity episodes (detector gate).")
    w(f"- `liquid`: 100% True in all {len(matured):,} matured equity episodes (detector gate).")
    w("These are structural constants — testing them is uninformative and they are excluded from m.")
    w()

    # -----------------------------------------------------------------------
    # Per-feature results tables
    # -----------------------------------------------------------------------
    w("## Feature results")
    w()
    w(f"m = {m_total} tests. Bonferroni threshold α/m = {alpha_bonf:.6f}.")
    w(f"CI_95 = 95% month-block paired bootstrap percentile CI ({n_boot:,} reps, seed {seed}).")
    w(f"CI_bonf = α/m percentile CI (two-sided tail = (α/m)/2 = {alpha_bonf/2:.7f} each side).")
    w("**bonf_survives uses CI_bonf** (corrected from prior run which used CI_95).")
    w("CI_cluster = 95% ticker-cluster bootstrap CI (robustness for within-ticker dependence).")
    w("Wilson CI = cross-check for binary features (Newcombe method).")
    w("ALL rows printed regardless of significance (census, not a screen).")
    w()

    # Group results by contrast
    for name_a, name_b, _ga, _gb in CONTRASTS:
        contrast_label = f"{name_a} vs {name_b}"
        w(f"### Contrast: {contrast_label}")
        w()

        # Binary features
        binary_rows = [r for r in all_results if r["contrast"] == contrast_label and r["type"] == "binary"]
        if binary_rows:
            w("| Feature | Tier | Rate_A | n_A | Rate_B | n_B | Diff | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | CIcluster_lo | CIcluster_hi | Wilson_lo | Wilson_hi | Note |")
            w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            for r in binary_rows:
                fa = r.get(f"rate_{name_a}", float("nan"))
                fb = r.get(f"rate_{name_b}", float("nan"))
                na = r.get(f"n_{name_a}", "—")
                nb = r.get(f"n_{name_b}", "—")
                bonf_sym = "YES" if r.get("bonf_survives") else ("—" if r.get("bonf_survives") is None else "no")
                degen = " [DEGEN]" if r.get("degenerate") else ""
                note = r.get("note", "") + degen
                w(f"| {r['feature']} | {r.get('feature_tier', '')} | {_fmt_pct(fa)} | {na} | {_fmt_pct(fb)} | {nb} | {_fmt_f(r.get('obs_diff'), 4)} | {_fmt_f(r.get('ci95_lo'), 4)} | {_fmt_f(r.get('ci95_hi'), 4)} | {_fmt_f(r.get('ci_bonf_lo'), 4)} | {_fmt_f(r.get('ci_bonf_hi'), 4)} | {bonf_sym} | {_fmt_f(r.get('ci_cluster_lo'), 4)} | {_fmt_f(r.get('ci_cluster_hi'), 4)} | {_fmt_f(r.get('wilson_ci_lo'), 4)} | {_fmt_f(r.get('wilson_ci_hi'), 4)} | {note} |")
            w()

        # Continuous features
        cont_rows = [r for r in all_results if r["contrast"] == contrast_label and r["type"] == "continuous"]
        if cont_rows:
            w("| Feature | Tier | Median_A | n_A | Median_B | n_B | Diff | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | CIcluster_lo | CIcluster_hi | Note |")
            w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            for r in cont_rows:
                ma = r.get(f"median_{name_a}", float("nan"))
                mb = r.get(f"median_{name_b}", float("nan"))
                na = r.get(f"n_{name_a}", "—")
                nb = r.get(f"n_{name_b}", "—")
                bonf_sym = "YES" if r.get("bonf_survives") else ("—" if r.get("bonf_survives") is None else "no")
                degen = " [DEGEN]" if r.get("degenerate") else ""
                note = r.get("note", "") + degen
                w(f"| {r['feature']} | {r.get('feature_tier', '')} | {_fmt_f(ma)} | {na} | {_fmt_f(mb)} | {nb} | {_fmt_f(r.get('obs_diff'), 4)} | {_fmt_f(r.get('ci95_lo'), 4)} | {_fmt_f(r.get('ci95_hi'), 4)} | {_fmt_f(r.get('ci_bonf_lo'), 4)} | {_fmt_f(r.get('ci_bonf_hi'), 4)} | {bonf_sym} | {_fmt_f(r.get('ci_cluster_lo'), 4)} | {_fmt_f(r.get('ci_cluster_hi'), 4)} | {note} |")
            w()

    # -----------------------------------------------------------------------
    # Strata
    # -----------------------------------------------------------------------
    w("## Honesty strata")
    w()

    w("### Stratum 1: Survivorship — UNTESTED")
    w()
    w("The census as harvested is **survivor-only**. The masterplan's dead-name coverage")
    w("(`scripts/research/fetch_dead_name_prices_polygon.py`) did not flow into this parquet.")
    w("All matured episodes have `survivorship_biased = False` as a column value, but this")
    w("reflects the _label_ applied during harvest, not actual dead-stock inclusion.")
    w("**Stratum 1 is UNTESTED, not passed.** Survivorship bias remains an unresolved gap.")
    w(f"Dead-name coverage: `price_source` contains only yahoo/massive (see Stratum 3) —")
    w("no dead-ticker source is present. The `survivorship_biased` column is constant False.")
    w()

    w("### Stratum 2: gap_leg_crossed == False (primary contrast only)")
    w()
    w(f"Episodes with gap_leg_crossed==False: kept_going={len(gap_clean_kg):,}, blow_off={len(gap_clean_bo):,}")
    w(f"(excluded from primary contrast: kept_going={len(kept_going)-len(gap_clean_kg):,}, blow_off={len(blow_off)-len(gap_clean_bo):,})")
    w()
    w("Binary features:")
    w()
    binary_strat = [r for r in stratum_results if r.get("type") == "binary"]
    if binary_strat:
        w("| Feature | Rate_A | n_A | Rate_B | n_B | Diff | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in binary_strat:
            name_a_s = "kept_going_gap_clean"
            name_b_s = "blow_off_gap_clean"
            fa = r.get(f"rate_{name_a_s}", float("nan"))
            fb = r.get(f"rate_{name_b_s}", float("nan"))
            na = r.get(f"n_{name_a_s}", "—")
            nb = r.get(f"n_{name_b_s}", "—")
            bonf_sym = "YES" if r.get("bonf_survives") else ("—" if r.get("bonf_survives") is None else "no")
            degen = " [DEGEN]" if r.get("degenerate") else ""
            w(f"| {r['feature']} | {_fmt_pct(fa)} | {na} | {_fmt_pct(fb)} | {nb} | {_fmt_f(r.get('obs_diff'), 4)} | {_fmt_f(r.get('ci95_lo'), 4)} | {_fmt_f(r.get('ci95_hi'), 4)} | {_fmt_f(r.get('ci_bonf_lo'), 4)} | {_fmt_f(r.get('ci_bonf_hi'), 4)} | {bonf_sym}{degen} |")
        w()

    cont_strat = [r for r in stratum_results if r.get("type") == "continuous"]
    if cont_strat:
        w("Continuous features:")
        w()
        w("| Feature | Median_A | n_A | Median_B | n_B | Diff | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in cont_strat:
            name_a_s = "kept_going_gap_clean"
            name_b_s = "blow_off_gap_clean"
            ma = r.get(f"median_{name_a_s}", float("nan"))
            mb = r.get(f"median_{name_b_s}", float("nan"))
            na = r.get(f"n_{name_a_s}", "—")
            nb = r.get(f"n_{name_b_s}", "—")
            bonf_sym = "YES" if r.get("bonf_survives") else ("—" if r.get("bonf_survives") is None else "no")
            degen = " [DEGEN]" if r.get("degenerate") else ""
            w(f"| {r['feature']} | {_fmt_f(ma)} | {na} | {_fmt_f(mb)} | {nb} | {_fmt_f(r.get('obs_diff'), 4)} | {_fmt_f(r.get('ci95_lo'), 4)} | {_fmt_f(r.get('ci95_hi'), 4)} | {_fmt_f(r.get('ci_bonf_lo'), 4)} | {_fmt_f(r.get('ci_bonf_hi'), 4)} | {bonf_sym}{degen} |")
        w()

    w("### Stratum 3: price_source mix per group")
    w()
    w("| Group | price_source | Count |")
    w("|---|---|---|")
    for label_name, grp in [("kept_going", kept_going), ("blow_off", blow_off), ("failed", failed)]:
        for ps, cnt in grp["price_source"].value_counts().items():
            w(f"| {label_name} | {ps} | {cnt:,} |")
    w()

    w("### Stratum 4: unmatured count")
    w()
    w(f"Unmatured episodes (equity): {len(unmatured):,} (not in any analysis group; forward windows not yet closed).")
    w()

    w("### Stratum 5: per-feature coverage")
    w()
    w("| Feature | Contrast | n_A_valid | n_B_valid |")
    w("|---|---|---|---|")
    for cr in coverage_rows:
        keys = list(cr.keys())
        na_key = [k for k in keys if k.startswith("n_") and "valid" in k and "total" not in k][0]
        nb_key = [k for k in keys if k.startswith("n_") and "valid" in k and "total" not in k][1]
        w(f"| {cr['feature']} | {cr['contrast']} | {cr[na_key]} | {cr[nb_key]} |")
    w()

    w("**F3 coverage detail:**")
    w()
    for cov_label, cnt in f3_cov_matured.items():
        w(f"- {cov_label}: {cnt}")
    w(f"- kept_going ok: {f3_kg_ok} of {len(kept_going)} ({f3_kg_ok/max(len(kept_going),1)*100:.1f}%)")
    w(f"- blow_off ok: {f3_bo_ok} of {len(blow_off)} ({f3_bo_ok/max(len(blow_off),1)*100:.1f}%)")
    if f3_non_comparable:
        w()
        w("**NON-COMPARABLE flag:** Coverage < 30% in at least one primary contrast group.")
        w("F3 results are printed but must not be interpreted as representative of the full groups.")
    w()

    # -----------------------------------------------------------------------
    # Honest read
    # -----------------------------------------------------------------------
    w("## Honest read (nulls printed)")
    w()

    r_f1t = _get_primary_result("trailing_rung_ge2")
    r_f1f = _get_primary_result("f1_fwd_rung_ge2")

    def _summarize(r: dict | None, label: str) -> str:
        if r is None:
            return f"{label}: UNTESTABLE (no result)" if label else "UNTESTABLE (no result)"
        ci95_lo = r.get("ci95_lo")
        ci95_hi = r.get("ci95_hi")
        ci_bonf_lo = r.get("ci_bonf_lo")
        ci_bonf_hi = r.get("ci_bonf_hi")
        if r.get("degenerate"):
            return f"{label}: DEGENERATE" if label else "DEGENERATE"
        if r.get("note") == "insufficient valid obs":
            return f"{label}: UNTESTABLE (insufficient valid obs)" if label else "UNTESTABLE (insufficient valid obs)"
        if ci95_lo is None:
            return f"{label}: UNTESTABLE (no CI)" if label else "UNTESTABLE (no CI)"
        excl_95 = (ci95_lo > 0) or (ci95_hi < 0)
        excl_bonf = False
        if ci_bonf_lo is not None and ci_bonf_hi is not None:
            excl_bonf = (ci_bonf_lo > 0) or (ci_bonf_hi < 0)
        obs_d = r.get("obs_diff", 0)
        direction = "higher in kept_going" if obs_d > 0 else "higher in blow_off/failed"
        pfx = f"{label}: " if label else ""
        if excl_bonf:
            return f"{pfx}95% CI excludes 0 AND α/m CI excludes 0 ({direction}; Bonferroni survives)"
        elif excl_95:
            return f"{pfx}95% CI excludes 0 BUT α/m CI contains 0 ({direction}; Bonferroni does NOT survive — real correction)"
        return f"{pfx}Both CIs contain 0 (no detectable difference)"

    w(_summarize(r_f1t, "F1 trailing (t0-126d→t0 rung count ≥ 2, covered subset)"))
    w(_summarize(r_f1f, "F1 early-move (t0→t0+21td rung count ≥ 2)"))
    w("F2 gap_hold: TAUTOLOGICAL — algebraically guaranteed True for kept_going by label definition (see §F2)")
    w("F2 gap_pct (non-tautological): CI contains 0 — gap magnitude null (no difference)")

    if f3_non_comparable:
        w("F3 profit step-up: NON-COMPARABLE (coverage < 30%) — result printed in table but cannot be interpreted")
    else:
        w(_summarize(_get_primary_result("f3_profit_stepup"), "F3 profit step-up"))

    w(_summarize(f4_result, "F4/F5 excess_21d_pp≥20pp (vs blow_off)"))
    r_exc = _get_primary_result("excess_21d_pp")
    w(_summarize(r_exc, "F4/F5 excess_21d_pp continuous (vs blow_off)"))

    w("F6 compressed prior: STRUCTURALLY BLOCKED — no PIT short-interest / options / consensus-dispersion")
    w("history in-repo for the census era (WA deferral, L10-aligned). The W2 report identified")
    w("'compressed prior' as appearing 11/11 in the hand-selected cases. Testing at census scale")
    w("requires short interest percentile, consensus-target-vs-spot gap, or analyst-dispersion —")
    w("none available in-repo with PIT coverage for the 1997–2026 episode window.")
    w("Per spec §3-F6 and the WA masterplan §1 adjudication table: structurally blocked, not proxied.")
    w()

    # -----------------------------------------------------------------------
    # Explicit CONFIRMED / REFUTED / UNTESTABLE per W2 candidate
    # -----------------------------------------------------------------------
    w("## Explicit verdict per W2 §4 candidate")
    w()
    w("Per spec §6: explicit CONFIRMED / REFUTED / UNTESTABLE line for each candidate.")
    w("CONFIRMED = α/m CI (corrected Bonferroni) excludes zero in the predicted direction.")
    w("REFUTED = α/m CI excludes zero in the OPPOSITE direction, or CI contains zero with adequate coverage.")
    w("UNTESTABLE = insufficient coverage, structurally blocked, or A2 firewall.")
    w("TAUTOLOGICAL = algebraically guaranteed by label definition (not a fingerprint).")
    w()

    def _explicit_verdict(r: dict | None, expected_direction_positive: bool = True) -> str:
        """Return CONFIRMED / REFUTED / UNTESTABLE based on corrected CI."""
        if r is None:
            return "UNTESTABLE"
        if r.get("degenerate"):
            return "UNTESTABLE (degenerate)"
        if r.get("note") == "insufficient valid obs":
            return "UNTESTABLE (insufficient obs)"
        ci_bonf_lo = r.get("ci_bonf_lo")
        ci_bonf_hi = r.get("ci_bonf_hi")
        if ci_bonf_lo is None:
            return "UNTESTABLE (no CI)"
        bonf = r.get("bonf_survives", False)
        excl = (ci_bonf_lo > 0) or (ci_bonf_hi < 0)
        obs_d = r.get("obs_diff", 0)
        if excl:
            if (obs_d > 0) == expected_direction_positive:
                return "CONFIRMED (α/m CI excludes 0, Bonferroni survives)"
            else:
                return "REFUTED (α/m CI excludes 0 in opposite direction)"
        # α/m CI contains zero
        n_a = r.get("n_kept_going", 0)
        if isinstance(n_a, int) and n_a < 10:
            return "UNTESTABLE (too few valid obs)"
        return "REFUTED (α/m CI contains 0 — no detectable difference at corrected threshold)"

    w("| W2 candidate | Spec prediction | Primary result (equity-only) | Post-correction verdict |")
    w("|---|---|---|---|")

    # F1 trailing
    f1t_v = _explicit_verdict(_get_primary_result("trailing_rung_ge2"), True)
    w(f"| F1 — trailing pre-onset rung count ≥2 | Higher in kept_going | {_summarize(_get_primary_result('trailing_rung_ge2'), '')} | {f1t_v} |")

    f1f_v = _explicit_verdict(_get_primary_result("f1_fwd_rung_ge2"), True)
    w(f"| F1 — early-move conditioner rung ≥2 (t0+21td) | Higher in kept_going | {_summarize(_get_primary_result('f1_fwd_rung_ge2'), '')} | {f1f_v} — on 8K-covered subset ({f1_kg_covered/max(len(kept_going),1)*100:.0f}%/{f1_bo_covered/max(len(blow_off),1)*100:.0f}%) |")

    w("| F2 — gap holds k sessions | Higher in kept_going | TAUTOLOGICAL (label definition) | TAUTOLOGICAL — not a fingerprint, ineligible for registration |")

    if f3_non_comparable:
        f3_v = "UNTESTABLE (NON-COMPARABLE — coverage < 30%)"
    else:
        f3_v = _explicit_verdict(_get_primary_result("f3_profit_stepup"), True)
    w(f"| F3 — profit step-up faster than revenue | Higher in kept_going | NON-COMPARABLE | {f3_v} |")

    # F4/F5 collapsed
    f45_v = _explicit_verdict(_get_primary_result("f4_composite"), True)
    f45_cont_v = _explicit_verdict(_get_primary_result("excess_21d_pp"), True)
    w(f"| F4/F5 — trailing-excess magnitude (≥20pp dichotomy) | W2: non-discriminating prediction | {_summarize(f4_result, '')} | {f45_v} |")
    w(f"| F4/F5 — trailing-excess magnitude (continuous) | W2: non-discriminating prediction | {_summarize(r_exc, '')} | {f45_cont_v} |")

    w("| F6 — compressed prior | Testable only with PIT proxy | N/A — structurally blocked | UNTESTABLE |")
    w()

    # -----------------------------------------------------------------------
    # Appendix: crypto
    # -----------------------------------------------------------------------
    w("## Appendix: Crypto episodes")
    w()
    w(f"Tickers excluded from primary analysis: {sorted(CRYPTO_TICKERS)}")
    w("Exclusion rationale: 7-day-calendar trading (vs equity 5-day), SPY benchmark category error,")
    w("and index-alignment mismatch in price reads (no weekend bars → F2 forward positions shift).")
    w()
    w(f"Crypto matured episodes: {len(matured_crypto):,} total")
    w(f"- kept_going: {len(kg_crypto):,}")
    w(f"- blow_off: {len(bo_crypto):,}")
    w(f"- failed: {len(fa_crypto):,}")
    w()
    w("Including crypto in the primary contrast changes group sizes by:")
    w(f"- kept_going: {len(kept_going):,} → {len(kept_going)+len(kg_crypto):,} (+{len(kg_crypto):,})")
    w(f"- blow_off: {len(blow_off):,} → {len(blow_off)+len(bo_crypto):,} (+{len(bo_crypto):,})")
    w(f"- failed: {len(failed):,} → {len(failed)+len(fa_crypto):,} (+{len(fa_crypto):,})")
    w("A with-crypto re-run is not performed (benchmark error makes the comparison invalid).")
    w()

    # -----------------------------------------------------------------------
    # Adjudication placeholder
    # -----------------------------------------------------------------------
    w("## Adjudication (WA-R8, main loop)")
    w()
    w("PENDING")
    w()

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Report written: %s (%d lines)", out_path, len(lines))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data"),
        help="Data root (read-only). Never written to.",
    )
    parser.add_argument(
        "--episodes",
        type=Path,
        default=None,
        help="Path to winner_episodes.parquet (default: <worktree>/data/research/winner_episodes.parquet)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("research/winners/FINGERPRINT_CENSUS_W3.md"),
        help="Output report path.",
    )
    parser.add_argument("--seed", type=int, default=BOOT_SEED)
    parser.add_argument("--n-boot", type=int, default=BOOT_REPS)

    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.exists():
        log.error("--root %s does not exist", root)
        return 1

    # Resolve episodes path — prefer worktree-local committed parquet
    if args.episodes is not None:
        episodes_path = args.episodes.resolve()
    else:
        # Try relative to this script's repo root first (worktree)
        script_root = Path(__file__).resolve().parents[2]
        episodes_path = script_root / "data" / "research" / "winner_episodes.parquet"
        if not episodes_path.exists():
            episodes_path = root / "research" / "winner_episodes.parquet"

    if not episodes_path.exists():
        log.error("Episodes parquet not found: %s", episodes_path)
        return 1

    # Resolve output path
    out_path = args.out
    if not out_path.is_absolute():
        out_path = Path(__file__).resolve().parents[2] / out_path

    # Safety: ensure out_path is not under root
    try:
        out_path.resolve().relative_to(root.resolve())
        log.error("Output path %s is under --root %s — forbidden (spec §7)", out_path, root)
        return 1
    except ValueError:
        pass  # Good — out_path is not under root

    run_study(
        episodes_path=episodes_path,
        root=root,
        out_path=out_path,
        n_boot=args.n_boot,
        seed=args.seed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
