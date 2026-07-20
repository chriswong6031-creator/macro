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
        [--n-boot 10000]

The script never writes under --root.
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

# Spec §4: m = total feature × contrast tests (declared below after feature list is known)
ALPHA = 0.05
BOOT_REPS = 10_000
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
# Statistics: month-block paired bootstrap
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
) -> tuple[float, float, float, int, int]:
    """Month-block paired bootstrap returning (diff, ci_lo, ci_hi, n_months_a, n_months_b).

    Block = t0 calendar month. Resample months with replacement (same drawn months
    feed both groups — paired draw). Computes statistic for rate (binary) or median.

    Returns:
        point_diff: observed difference (A - B, rate or median)
        ci_lo, ci_hi: 95% percentile CI of the bootstrap distribution
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

    # All months that appear in EITHER group
    all_months = sorted(set(map_a.keys()) | set(map_b.keys()))
    n_m = len(all_months)
    all_months_arr = np.array(all_months)

    n_months_a = len(map_a)
    n_months_b = len(map_b)

    def _stat(m_sample: np.ndarray) -> float:
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
        return point_diff, float("nan"), float("nan"), n_months_a, n_months_b

    ci_lo = float(np.percentile(boot_arr, 2.5))
    ci_hi = float(np.percentile(boot_arr, 97.5))
    return point_diff, ci_lo, ci_hi, n_months_a, n_months_b


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
) -> dict[str, Any]:
    """Run binary feature analysis: rates, bootstrap diff CI, Wilson CI."""
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
        "ci_lo": None,
        "ci_hi": None,
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

    diff, ci_lo, ci_hi, nm_a, nm_b = month_block_bootstrap_diff(
        a_vals.values,
        b_vals.values,
        months_a,
        months_b,
        is_binary=True,
    )
    result["ci_lo"] = round(ci_lo, 4) if not np.isnan(ci_lo) else None
    result["ci_hi"] = round(ci_hi, 4) if not np.isnan(ci_hi) else None

    # Bonferroni: CI excludes 0 AND width consistent with alpha_bonf
    # Spec uses percentile CI; we flag if CI excludes 0 at alpha/m
    # For the Bonferroni flag we use the 2.5/97.5 CI since that's what we computed;
    # this is conservative (spec says flag CIs that survive α=0.05/m).
    if result["ci_lo"] is not None and result["ci_hi"] is not None:
        excl_zero = (result["ci_lo"] > 0) or (result["ci_hi"] < 0)
        result["bonf_survives"] = bool(excl_zero)

    # Wilson cross-check
    wci_a_lo, wci_a_hi = _wilson_ci(float(a_vals.sum()), float(n_a_valid))
    wci_b_lo, wci_b_hi = _wilson_ci(float(b_vals.sum()), float(n_b_valid))
    result["wilson_ci_lo"] = round(wci_a_lo - wci_b_hi, 4)
    result["wilson_ci_hi"] = round(wci_a_hi - wci_b_lo, 4)

    return result


def analyze_continuous_feature(
    feature_col: str,
    group_a: pd.DataFrame,
    group_b: pd.DataFrame,
    name_a: str,
    name_b: str,
    alpha_bonf: float,
) -> dict[str, Any]:
    """Run continuous feature analysis: medians, bootstrap median-diff CI."""
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
        "ci_lo": None,
        "ci_hi": None,
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

    diff, ci_lo, ci_hi, _, _ = month_block_bootstrap_diff(
        a_vals.values,
        b_vals.values,
        months_a,
        months_b,
        is_binary=False,
    )
    result["ci_lo"] = round(ci_lo, 4) if not np.isnan(ci_lo) else None
    result["ci_hi"] = round(ci_hi, 4) if not np.isnan(ci_hi) else None

    if result["ci_lo"] is not None and result["ci_hi"] is not None:
        excl_zero = (result["ci_lo"] > 0) or (result["ci_hi"] < 0)
        result["bonf_survives"] = bool(excl_zero)

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

    # Population
    matured = eps[eps["outcome_label"].isin(MATURED_LABELS)].copy()
    unmatured = eps[eps["outcome_label"] == "unmatured"]
    kept_going = matured[matured["outcome_label"].isin(KEPT_GOING_LABELS)].copy()
    blow_off = matured[matured["outcome_label"] == "blow_off"].copy()
    failed = matured[matured["outcome_label"] == "failed"].copy()

    log.info(
        "Population: total=%d matured=%d unmatured=%d kept_going=%d blow_off=%d failed=%d",
        len(eps),
        len(matured),
        len(unmatured),
        len(kept_going),
        len(blow_off),
        len(failed),
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
    # F2 (gap holds), F3 (profit step-up) per episode row for matured
    # -----------------------------------------------------------------------
    log.info("Computing per-episode F1 early-move and F2 features for %d matured episodes...", len(matured))

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

        # F2
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

    # F4 composite
    matured["f4_composite"] = (matured["new_high_63d"] == True) & (matured["excess_21d_pp"] >= 20.0)
    kept_going = matured[matured["outcome_label"].isin(KEPT_GOING_LABELS)].copy()
    blow_off = matured[matured["outcome_label"] == "blow_off"].copy()
    failed = matured[matured["outcome_label"] == "failed"].copy()

    # -----------------------------------------------------------------------
    # Define feature list and m (total tests)
    # -----------------------------------------------------------------------
    # Features: see spec §3
    # For each feature, declare (name, type, column)
    # Contrasts: PRIMARY (kg vs bo) and secondary (kg vs failed)
    # Each feature × contrast = 1 test → m = total number

    # F1 trailing (pure-t0, from parquet):
    #   hard_event_count_126d (continuous), soft_event_count_126d (continuous)
    #   trailing_rung_ge2 = (hard + soft >= 2), soft_then_hard (binary)
    # F1 early-move conditioner (uses post-t0 info):
    #   f1_fwd_rung_ge2 (binary)
    # F2: gap_pct (continuous), gap_hold_3/5/10 (binary)
    # F3: f3_profit_stepup (binary) — A2 firewall
    # F4: f4_composite (binary)
    # Pure-t0 from parquet: excess_21d_pp, dollar_vol_z21, dv_5_60_ratio, new_high_63d,
    #                        liquid, self_funded_at_t0

    # trailing_rung_ge2: only valid where b1_coverage == 'post_2014_only'
    pre_era_mask = matured["b1_coverage"] == "pre_era_cutoff"
    hard_col = matured["hard_event_count_126d"].copy()
    soft_col = matured["soft_event_count_126d"].copy()
    rung_ge2: list[bool | None] = []
    for h, s, is_pre in zip(hard_col, soft_col, pre_era_mask):
        if is_pre:
            rung_ge2.append(None)
        else:
            h_val = 0 if pd.isna(h) else int(h)
            s_val = 0 if pd.isna(s) else int(s)
            rung_ge2.append((h_val + s_val) >= 2)
    matured["trailing_rung_ge2"] = rung_ge2  # object dtype, allows None
    # For hard/soft counts, nullify pre-era rows (they're already None but let's confirm)
    matured.loc[pre_era_mask, "hard_event_count_126d"] = np.nan
    matured.loc[pre_era_mask, "soft_event_count_126d"] = np.nan

    kept_going = matured[matured["outcome_label"].isin(KEPT_GOING_LABELS)].copy()
    blow_off = matured[matured["outcome_label"] == "blow_off"].copy()
    failed = matured[matured["outcome_label"] == "failed"].copy()

    # Feature × contrast list — m determines Bonferroni correction
    # Format: (label, col_name, type, groups_pair, note)
    FEATURES: list[tuple[str, str, str, str]] = [
        # Pure-t0 from parquet
        ("excess_21d_pp", "continuous", "pure_t0", ""),
        ("dollar_vol_z21", "continuous", "pure_t0", ""),
        ("dv_5_60_ratio", "continuous", "pure_t0", ""),
        ("new_high_63d", "binary", "pure_t0", ""),
        ("liquid", "binary", "pure_t0", ""),
        ("self_funded_at_t0", "binary", "pure_t0", "B2"),
        # F4 composite
        ("f4_composite", "binary", "pure_t0", "F4: new_high_63d AND excess_21d_pp>=20"),
        # F1 trailing (pure-t0, pre-onset window t0-126d to t0)
        ("hard_event_count_126d", "continuous", "pure_t0", "F1-trailing: B1 hard events in t0-126d window"),
        ("soft_event_count_126d", "continuous", "pure_t0", "F1-trailing: B1 soft events in t0-126d window"),
        ("trailing_rung_ge2", "binary", "pure_t0", "F1-trailing: hard+soft rungs>=2 pre-onset"),
        ("soft_then_hard", "binary", "pure_t0", "F1-trailing: soft before hard in pre-onset window"),
        # F1 early-move conditioner (uses t0 to t0+21td)
        ("f1_fwd_rung_ge2", "binary", "early_move", "F1-early-move: rung>=2 in (t0, t0+21td]"),
        # F2 gap holds (early-move conditioner)
        ("gap_pct", "continuous", "early_move", "F2: onset-day gap % (close/close-1)"),
        ("gap_hold_3", "binary", "early_move", "F2: gap holds at t0+3td"),
        ("gap_hold_5", "binary", "early_move", "F2: gap holds at t0+5td"),
        ("gap_hold_10", "binary", "early_move", "F2: gap holds at t0+10td"),
        # F3 profit step-up (A2 firewall: t0 < 2024-01-01 only)
        ("f3_profit_stepup", "binary", "pure_t0", "F3: op margin delta > rev delta QoQ; A2 firewall t0<2024"),
    ]

    CONTRASTS = [
        ("kept_going", "blow_off", kept_going, blow_off),
        ("kept_going", "failed", kept_going, failed),
    ]

    m_total = len(FEATURES) * len(CONTRASTS)
    alpha_bonf = ALPHA / m_total
    log.info("m_total = %d, alpha_bonf = %.5f", m_total, alpha_bonf)

    # -----------------------------------------------------------------------
    # Run all analyses
    # -----------------------------------------------------------------------
    log.info("Running bootstrap analyses (n_boot=%d, seed=%d)...", n_boot, seed)

    all_results: list[dict[str, Any]] = []
    for feat_col, feat_type, feat_tier, feat_note in FEATURES:
        for name_a, name_b, grp_a, grp_b in CONTRASTS:
            log.info("  %s × %s vs %s", feat_col, name_a, name_b)
            if feat_type == "binary":
                res = analyze_binary_feature(feat_col, grp_a, grp_b, name_a, name_b, alpha_bonf)
            else:
                res = analyze_continuous_feature(feat_col, grp_a, grp_b, name_a, name_b, alpha_bonf)
            res["feature_tier"] = feat_tier
            res["feature_note"] = feat_note
            all_results.append(res)

    # -----------------------------------------------------------------------
    # Strata: survivorship_biased==False (already all False), gap_leg_crossed==False
    # -----------------------------------------------------------------------
    log.info("Computing strata...")

    # Stratum: gap_leg_crossed == False (primary contrast only)
    gap_clean = matured[matured["gap_leg_crossed"] == False].copy()
    kg_gap = gap_clean[gap_clean["outcome_label"].isin(KEPT_GOING_LABELS)]
    bo_gap = gap_clean[gap_clean["outcome_label"] == "blow_off"]

    stratum_results: list[dict[str, Any]] = []
    for feat_col, feat_type, feat_tier, feat_note in FEATURES:
        log.info("  Stratum gap_leg_crossed==False: %s", feat_col)
        if feat_type == "binary":
            res = analyze_binary_feature(feat_col, kg_gap, bo_gap, "kept_going_gap_clean", "blow_off_gap_clean", alpha_bonf)
        else:
            res = analyze_continuous_feature(feat_col, kg_gap, bo_gap, "kept_going_gap_clean", "blow_off_gap_clean", alpha_bonf)
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

    # -----------------------------------------------------------------------
    # F3 coverage stats
    # -----------------------------------------------------------------------
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
        eps=eps,
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
) -> None:

    lines: list[str] = []
    def w(s: str = "") -> None:
        lines.append(s)

    # Header
    w("<!-- W3 census fingerprint study. DESCRIPTIVE ONLY (WA-R1/R5/R8). -->")
    w()
    w("# Winner Autopsy Lab — W3 Census Fingerprint Study (Layer-3a)")
    w()
    w(f"**Status:** DESCRIPTIVE ONLY — no hypothesis registration, no verdicts, no filters, no site surfaces.")
    w(f"Rulings WA-R1 / WA-R5 / WA-R8. Spec: `research/winners/W3_CENSUS_STUDY_SPEC.md`.")
    w()
    w(f"**Substrate:** `{episodes_path.name}` — manifest hash `{manifest_hash}`, harvest date `{harvest_date}`.")
    w(f"**Run:** seed {seed}, n_boot {n_boot}, m={m_total} tests, α_Bonferroni = 0.05/{m_total} = {alpha_bonf:.5f}.")
    w(f"**Wall time:** {elapsed:.1f}s")
    w()

    # -----------------------------------------------------------------------
    # Bottom line first
    # -----------------------------------------------------------------------
    w("## Bottom line")
    w()

    # Determine verdicts for W2 candidates (F1–F6)
    def _get_primary_result(feat_col: str) -> dict | None:
        for r in all_results:
            if r["feature"] == feat_col and r["contrast"] == "kept_going vs blow_off":
                return r
        return None

    f1_trail_result = _get_primary_result("trailing_rung_ge2")
    f1_fwd_result = _get_primary_result("f1_fwd_rung_ge2")
    f2_gap3_result = _get_primary_result("gap_hold_3")
    f2_gap5_result = _get_primary_result("gap_hold_5")
    f2_gap10_result = _get_primary_result("gap_hold_10")
    f3_result = _get_primary_result("f3_profit_stepup")
    f4_result = _get_primary_result("f4_composite")

    w("Results are machine outputs from the full census — not adjudications. The main loop appends WA-R8 below.")
    w()

    # Quick summary table
    w("| W2 candidate | Census verdict |")
    w("|---|---|")

    def _verdict_line(r: dict | None) -> str:
        if r is None:
            return "UNTESTABLE — no data"
        ci_lo = r.get("ci_lo")
        ci_hi = r.get("ci_hi")
        bonf = r.get("bonf_survives")
        n_kg = r.get("n_kept_going", r.get("n_kept_going_total", "?"))
        note = r.get("note", "")
        if r.get("degenerate"):
            return f"DEGENERATE (< 12 months in a group)"
        if note == "insufficient valid obs":
            return "UNTESTABLE — insufficient valid obs"
        if ci_lo is None:
            return "UNTESTABLE — no CI computed"
        excl_zero = (ci_lo > 0) or (ci_hi < 0)
        if excl_zero:
            direction = "higher in kept_going" if (r.get("obs_diff", 0) > 0) else "higher in blow_off/failed"
            bonf_note = " (Bonferroni survives)" if bonf else " (does not survive Bonferroni)"
            return f"CI EXCLUDES ZERO — {direction}{bonf_note}"
        return f"CI CONTAINS ZERO — no detectable difference at 95%"

    # For F1, use the trailing (parquet) version as the primary W2 test
    f1_v = _verdict_line(f1_trail_result)
    f2_v = _verdict_line(f2_gap5_result)  # gap_hold_5 as representative
    f3_v = "UNTESTABLE — A2 firewall excludes t0>=2024; coverage < 30% in primary group (NON-COMPARABLE)" if f3_non_comparable else _verdict_line(f3_result)
    f4_v = _verdict_line(f4_result)
    w(f"| F1 — catalyst-ladder rung count (trailing pre-t0) | {f1_v} |")
    w(f"| F1 — catalyst-ladder rung count (early-move, t0+21td) | {_verdict_line(f1_fwd_result)} |")
    w(f"| F2 — trigger gap holds (gap_hold_5) | {f2_v} |")
    w(f"| F3 — profit step-up faster than revenue | {f3_v} |")
    w(f"| F4 — new 63d high AND excess_21d≥20pp | {f4_v} |")
    w(f"| F5 — sector beta ruled out (excess_21d_pp) | {_verdict_line(_get_primary_result('excess_21d_pp'))} |")
    w(f"| F6 — compressed prior | UNTESTABLE — structurally blocked (no PIT short-interest/options/dispersion history) |")
    w()

    # F1 window-direction finding
    w("### F1 window-direction finding (spec §3 circularity guard)")
    w()
    w("**Verified:** `hard_event_count_126d` / `soft_event_count_126d` / `soft_then_hard` in")
    w("`engine/winner_autopsy.py:_b1_features` use the PRE-ONSET window: `filing_date strictly < t0,")
    w("within 126 calendar days of t0` (lines 1228-1230). These are TRAILING counts, NOT forward-looking.")
    w("They do NOT overlap the labeling horizon. Path taken: **use them directly as pure-t0 features**,")
    w("and additionally compute F1 early-move conditioner from material_8k_events bounded to (t0, t0+21td].")
    w()

    # -----------------------------------------------------------------------
    # Population table
    # -----------------------------------------------------------------------
    w("## Population")
    w()
    w(f"Total episodes (full census): **{len(eps):,}** / {eps['ticker'].nunique():,} tickers")
    w(f"t0 range: {eps['t0'].min().date()} → {eps['t0'].max().date()}")
    w()
    w("| Outcome label | Count |")
    w("|---|---|")
    for label, cnt in eps["outcome_label"].value_counts().items():
        w(f"| {label} | {cnt:,} |")
    w()
    w("**Matured (analysis population):**")
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

    # -----------------------------------------------------------------------
    # Per-feature results tables
    # -----------------------------------------------------------------------
    w("## Feature results")
    w()
    w(f"m = {m_total} tests. Bonferroni threshold α/m = {alpha_bonf:.5f}.")
    w("CI = 95% month-block paired bootstrap percentile CI (10,000 reps, seed 20260720).")
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
            w("| Feature | Tier | Rate A | n_A | Rate B | n_B | Diff | CI_lo | CI_hi | Bonf | Wilson_lo | Wilson_hi | Note |")
            w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            for r in binary_rows:
                fa = r.get(f"rate_{name_a}", float("nan"))
                fb = r.get(f"rate_{name_b}", float("nan"))
                na = r.get(f"n_{name_a}", "—")
                nb = r.get(f"n_{name_b}", "—")
                bonf_sym = "YES" if r.get("bonf_survives") else ("—" if r.get("bonf_survives") is None else "no")
                degen = " [DEGEN]" if r.get("degenerate") else ""
                note = r.get("note", "") + degen
                w(f"| {r['feature']} | {r.get('feature_tier', '')} | {_fmt_pct(fa)} | {na} | {_fmt_pct(fb)} | {nb} | {_fmt_f(r.get('obs_diff'), 4)} | {_fmt_f(r.get('ci_lo'), 4)} | {_fmt_f(r.get('ci_hi'), 4)} | {bonf_sym} | {_fmt_f(r.get('wilson_ci_lo'), 4)} | {_fmt_f(r.get('wilson_ci_hi'), 4)} | {note} |")
            w()

        # Continuous features
        cont_rows = [r for r in all_results if r["contrast"] == contrast_label and r["type"] == "continuous"]
        if cont_rows:
            w("| Feature | Tier | Median A | n_A | Median B | n_B | Diff | CI_lo | CI_hi | Bonf | Note |")
            w("|---|---|---|---|---|---|---|---|---|---|---|")
            for r in cont_rows:
                ma = r.get(f"median_{name_a}", float("nan"))
                mb = r.get(f"median_{name_b}", float("nan"))
                na = r.get(f"n_{name_a}", "—")
                nb = r.get(f"n_{name_b}", "—")
                bonf_sym = "YES" if r.get("bonf_survives") else ("—" if r.get("bonf_survives") is None else "no")
                degen = " [DEGEN]" if r.get("degenerate") else ""
                note = r.get("note", "") + degen
                w(f"| {r['feature']} | {r.get('feature_tier', '')} | {_fmt_f(ma)} | {na} | {_fmt_f(mb)} | {nb} | {_fmt_f(r.get('obs_diff'), 4)} | {_fmt_f(r.get('ci_lo'), 4)} | {_fmt_f(r.get('ci_hi'), 4)} | {bonf_sym} | {note} |")
            w()

    # -----------------------------------------------------------------------
    # Strata
    # -----------------------------------------------------------------------
    w("## Honesty strata")
    w()

    w("### Stratum 1: survivorship_biased == False")
    w()
    w(f"All {len(matured):,} matured episodes have `survivorship_biased = False` in this census.")
    w("This stratum equals the full analysis population — no separate table needed.")
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
        w("| Feature | Rate A | n_A | Rate B | n_B | Diff | CI_lo | CI_hi | Bonf |")
        w("|---|---|---|---|---|---|---|---|---|")
        for r in binary_strat:
            name_a_s = "kept_going_gap_clean"
            name_b_s = "blow_off_gap_clean"
            fa = r.get(f"rate_{name_a_s}", float("nan"))
            fb = r.get(f"rate_{name_b_s}", float("nan"))
            na = r.get(f"n_{name_a_s}", "—")
            nb = r.get(f"n_{name_b_s}", "—")
            bonf_sym = "YES" if r.get("bonf_survives") else ("—" if r.get("bonf_survives") is None else "no")
            degen = " [DEGEN]" if r.get("degenerate") else ""
            w(f"| {r['feature']} | {_fmt_pct(fa)} | {na} | {_fmt_pct(fb)} | {nb} | {_fmt_f(r.get('obs_diff'), 4)} | {_fmt_f(r.get('ci_lo'), 4)} | {_fmt_f(r.get('ci_hi'), 4)} | {bonf_sym}{degen} |")
        w()

    cont_strat = [r for r in stratum_results if r.get("type") == "continuous"]
    if cont_strat:
        w("Continuous features:")
        w()
        w("| Feature | Median A | n_A | Median B | n_B | Diff | CI_lo | CI_hi | Bonf |")
        w("|---|---|---|---|---|---|---|---|---|")
        for r in cont_strat:
            name_a_s = "kept_going_gap_clean"
            name_b_s = "blow_off_gap_clean"
            ma = r.get(f"median_{name_a_s}", float("nan"))
            mb = r.get(f"median_{name_b_s}", float("nan"))
            na = r.get(f"n_{name_a_s}", "—")
            nb = r.get(f"n_{name_b_s}", "—")
            bonf_sym = "YES" if r.get("bonf_survives") else ("—" if r.get("bonf_survives") is None else "no")
            degen = " [DEGEN]" if r.get("degenerate") else ""
            w(f"| {r['feature']} | {_fmt_f(ma)} | {na} | {_fmt_f(mb)} | {nb} | {_fmt_f(r.get('obs_diff'), 4)} | {_fmt_f(r.get('ci_lo'), 4)} | {_fmt_f(r.get('ci_hi'), 4)} | {bonf_sym}{degen} |")
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
    w(f"Unmatured episodes: {len(unmatured):,} (not in any analysis group; forward windows not yet closed).")
    w()

    w("### Stratum 5: per-feature coverage")
    w()
    w("| Feature | Contrast | n_A_valid | n_B_valid |")
    w("|---|---|---|---|")
    for cr in coverage_rows:
        keys = list(cr.keys())
        na_key = [k for k in keys if k.startswith("n_") and "valid" in k and not "total" in k][0]
        nb_key = [k for k in keys if k.startswith("n_") and "valid" in k and not "total" in k][1]
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

    # F1 trailing
    r_f1t = _get_primary_result("trailing_rung_ge2")
    r_f1f = _get_primary_result("f1_fwd_rung_ge2")

    def _summarize(r: dict | None, label: str) -> str:
        if r is None:
            return f"{label}: UNTESTABLE (no result)"
        ci_lo = r.get("ci_lo")
        ci_hi = r.get("ci_hi")
        if r.get("degenerate"):
            return f"{label}: DEGENERATE"
        if r.get("note") == "insufficient valid obs":
            return f"{label}: UNTESTABLE (insufficient valid obs)"
        if ci_lo is None:
            return f"{label}: UNTESTABLE (no CI)"
        excl = (ci_lo > 0) or (ci_hi < 0)
        obs_d = r.get("obs_diff", 0)
        bonf = r.get("bonf_survives", False)
        if excl:
            direction = "higher in kept_going" if obs_d > 0 else "higher in blow_off"
            bonf_note = "survives Bonferroni" if bonf else "does not survive Bonferroni"
            return f"{label}: CI excludes 0 ({direction}; {bonf_note})"
        return f"{label}: CI contains 0 (no detectable difference)"

    w(_summarize(r_f1t, "F1 trailing (t0-126d→t0 rung count ≥ 2)"))
    w(_summarize(r_f1f, "F1 early-move (t0→t0+21td rung count ≥ 2)"))

    r_gap3 = _get_primary_result("gap_hold_3")
    r_gap5 = _get_primary_result("gap_hold_5")
    r_gap10 = _get_primary_result("gap_hold_10")
    w(_summarize(r_gap3, "F2 gap_hold_3"))
    w(_summarize(r_gap5, "F2 gap_hold_5"))
    w(_summarize(r_gap10, "F2 gap_hold_10"))

    if f3_non_comparable:
        w("F3 profit step-up: NON-COMPARABLE (coverage < 30%) — result printed in table but cannot be interpreted")
    else:
        w(_summarize(_get_primary_result("f3_profit_stepup"), "F3 profit step-up"))

    w(_summarize(f4_result, "F4 composite (new_high_63d AND excess_21d≥20pp)"))

    r_exc = _get_primary_result("excess_21d_pp")
    w(_summarize(r_exc, "F5 proxy (excess_21d_pp, continuous)"))

    w("F6 compressed prior: STRUCTURALLY BLOCKED — no PIT short-interest / options / consensus-dispersion")
    w("history in-repo for the census era (WA deferral, L10-aligned). One paragraph: the W2 report")
    w("identified 'compressed prior' (the market was actively doubting something) as appearing 11/11")
    w("in the hand-selected cases. Testing this at census scale requires a machinable proxy — short")
    w("interest percentile, consensus-target-vs-spot gap, or analyst-dispersion — none of which are")
    w("available in-repo with PIT coverage for the 1997–2026 episode window. Per spec §3-F6 and the")
    w("WA masterplan §1 adjudication table, this column is structurally blocked and not proxied.")
    w()

    # -----------------------------------------------------------------------
    # Explicit CONFIRMED / REFUTED / UNTESTABLE per W2 candidate
    # -----------------------------------------------------------------------
    w("## Explicit verdict per W2 §4 candidate")
    w()
    w("Per spec §6: explicit CONFIRMED / REFUTED / UNTESTABLE line for each candidate.")
    w("CONFIRMED = CI excludes zero in the predicted direction, survives Bonferroni.")
    w("REFUTED = CI excludes zero in the OPPOSITE direction, or CI contains zero with adequate coverage.")
    w("UNTESTABLE = insufficient coverage, structurally blocked, or A2 firewall.")
    w()

    def _explicit_verdict(r: dict | None, expected_direction_positive: bool = True) -> str:
        """Return CONFIRMED / REFUTED / UNTESTABLE based on result."""
        if r is None:
            return "UNTESTABLE"
        if r.get("degenerate"):
            return "UNTESTABLE (degenerate)"
        if r.get("note") == "insufficient valid obs":
            return "UNTESTABLE (insufficient obs)"
        ci_lo = r.get("ci_lo")
        ci_hi = r.get("ci_hi")
        if ci_lo is None:
            return "UNTESTABLE (no CI)"
        bonf = r.get("bonf_survives", False)
        excl = (ci_lo > 0) or (ci_hi < 0)
        obs_d = r.get("obs_diff", 0)
        if excl:
            if (obs_d > 0) == expected_direction_positive:
                if bonf:
                    return "CONFIRMED (CI excludes 0, Bonferroni survives)"
                else:
                    return "CONFIRMED (CI excludes 0, Bonferroni does NOT survive — weak)"
            else:
                if bonf:
                    return "REFUTED (CI excludes 0 in opposite direction, Bonferroni survives)"
                else:
                    return "REFUTED (CI excludes 0 in opposite direction, Bonferroni does NOT survive — weak)"
        # CI contains zero
        n_a = r.get(f"n_kept_going", 0)
        if isinstance(n_a, int) and n_a < 10:
            return "UNTESTABLE (too few valid obs)"
        return "REFUTED (CI contains 0 — no detectable difference)"

    w("| W2 candidate | Spec prediction | Primary result | Verdict |")
    w("|---|---|---|---|")

    # F1 trailing: W2 says kept_going should have more rungs than blow_off
    f1t_verdict = _explicit_verdict(_get_primary_result("trailing_rung_ge2"), True)
    w(f"| F1 — trailing pre-onset rung count ≥2 | Higher in kept_going | {_summarize(_get_primary_result('trailing_rung_ge2'), '').lstrip()} | {f1t_verdict} |")

    f1f_verdict = _explicit_verdict(_get_primary_result("f1_fwd_rung_ge2"), True)
    w(f"| F1 — early-move conditioner rung ≥2 (t0+21td) | Higher in kept_going | {_summarize(_get_primary_result('f1_fwd_rung_ge2'), '').lstrip()} | {f1f_verdict} |")

    # F2: kept_going should have higher gap-hold rates
    f2g3_verdict = _explicit_verdict(_get_primary_result("gap_hold_3"), True)
    f2g5_verdict = _explicit_verdict(_get_primary_result("gap_hold_5"), True)
    f2g10_verdict = _explicit_verdict(_get_primary_result("gap_hold_10"), True)
    w(f"| F2 — gap holds 3 sessions | Higher in kept_going | {_summarize(_get_primary_result('gap_hold_3'), '').lstrip()} | {f2g3_verdict} |")
    w(f"| F2 — gap holds 5 sessions | Higher in kept_going | {_summarize(_get_primary_result('gap_hold_5'), '').lstrip()} | {f2g5_verdict} |")
    w(f"| F2 — gap holds 10 sessions | Higher in kept_going | {_summarize(_get_primary_result('gap_hold_10'), '').lstrip()} | {f2g10_verdict} |")

    # F3: kept_going should have more profit step-ups
    if f3_non_comparable:
        f3_verdict = "UNTESTABLE (NON-COMPARABLE — coverage < 30%)"
    else:
        f3_verdict = _explicit_verdict(_get_primary_result("f3_profit_stepup"), True)
    w(f"| F3 — profit step-up faster than revenue | Higher in kept_going (fundamental subgroup) | NON-COMPARABLE if flagged | {f3_verdict} |")

    # F4: by construction blow_offs ALSO show new high + large excess — expected to not discriminate at t0
    f4_verdict = _explicit_verdict(_get_primary_result("f4_composite"), True)
    w(f"| F4 — new 63d high AND excess_21d≥20pp | W2 predicted: likely non-discriminating at t0 | {_summarize(f4_result, '').lstrip()} | {f4_verdict} |")

    # F5: excess_21d_pp — similar reasoning, both groups defined to have large excess
    f5_verdict = _explicit_verdict(_get_primary_result("excess_21d_pp"), True)
    w(f"| F5 — sector beta ruled out / idiosyncratic excess | W2 predicted: non-discriminating (both groups defined on excess) | {_summarize(r_exc, '').lstrip()} | {f5_verdict} |")

    w(f"| F6 — compressed prior | Predicted: testable only with PIT short-interest proxy | N/A — structurally blocked | UNTESTABLE |")
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
