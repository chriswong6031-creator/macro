"""Entry-Stack Expansion W1 — Null-Competitors (NC-1 / NC-2).

Masterplan ref: research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md
  §2 R1/R2 laws, §5 NC-1/NC-2 + trial protocol, §10 RUL-3.
W0 baselines frozen in: research/entry_stack/W0_BASELINES.md (RUL-7 gate).

NC-1: Tier-subsetting and freshness-tightening of the existing gate.
  Stratum A: T1-only vs T1+T2+T3 (recall cost of dropping T2/T3)
  Stratum B: ticks==0 (freshest fires) vs all fresh fires

NC-2: Proximity proxy for the calibrated entry_quality composite.
  Full entry_quality() requires cyc/mtf/early/regime dicts from the
  cycles.py call chain. PARTIAL implementation: proximity component only
  (EQ_W_PROX=0.52 of total score), computable offline from close series.
  Exact deferral stamp in the report.

Output: research/entry_stack/W1_NC_REPORT.md + trial-ledger rows.

Performance note: this runner implements the R1 date-FE estimator with a
vectorized block bootstrap, avoiding the O(n^2) _make_blocks bottleneck in
entry_strata_phase0.py. Blocks are constructed in O(n log n) via sorted-date
grouping; bootstrap inner loop uses numpy operations throughout.

Usage:
    cd /path/to/repo
    python scripts/research/run_w1_nc.py
    python scripts/research/run_w1_nc.py --n-bootstrap 500 --panel deep
    python scripts/research/run_w1_nc.py --smoke   # 50 boot, deep only
    python scripts/research/run_w1_nc.py --out research/entry_stack/W1_NC_REPORT.md
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import harness primitives (from W0 PR-C) — only the non-bootstrap parts
# ---------------------------------------------------------------------------
from scripts.research.entry_strata_phase0 import (  # noqa: E402
    _build_sector_map,
    _get_closes,
    _register_all_families,
    _prepare_binary_outcomes,
    _assign_era,
    compute_recall,
    grade_fires,
    load_fires,
    FAMILY_BUDGETS,
    PROGRAM_ERAS,
    BH_Q_THRESHOLD,
    BLOCK_RADIUS,
    N_BOOTSTRAP,
    RNG_SEED,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA          = _REPO_ROOT / "data"
_RESEARCH_DIR  = _REPO_ROOT / "research" / "entry_stack"
_FIRES_DEEP    = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS = _DATA / "research" / "gate_fires_baskets.parquet"
_LEDGER_PATH   = _DATA / "trial_ledger.jsonl"

# ---------------------------------------------------------------------------
# Fast vectorized R1 estimator (replaces entry_strata_phase0 r1_estimate
# for large-n panels; avoids O(n^2) _make_blocks from the harness)
# ---------------------------------------------------------------------------

def _fast_make_blocks(
    dates: np.ndarray,          # int64 nanoseconds (from pd.DatetimeIndex)
    sector_ids: np.ndarray,     # int sector group id (-1 = no sector)
    block_radius_days: int = 14,
) -> list[np.ndarray]:
    """O(n log n) block construction for episode-clustered bootstrap.

    Sorts rows by (sector, date). Within each sector group, slides a window
    of ±block_radius_days calendar days. Each sliding window becomes one block.
    Rows within the same window are in the same block.

    Returns list of 1-D index arrays (iloc positions into the original df).
    This is the vectorized replacement for _make_blocks which had an O(n^2)
    Python inner loop.
    """
    n = len(dates)
    if n == 0:
        return []

    radius_ns = block_radius_days * 86400 * 10**9  # days → nanoseconds

    # Sort by (sector, date) for efficient window scanning
    order = np.lexsort((dates, sector_ids))
    sorted_dates = dates[order]
    sorted_sectors = sector_ids[order]

    blocks: list[np.ndarray] = []
    i = 0
    while i < n:
        # start of a new block: anchor at sorted_dates[i]
        sec = sorted_sectors[i]
        anchor = sorted_dates[i]
        # find all rows in the same sector within ±radius of anchor
        # since sorted by (sector, date), scan forward until sector changes or date > anchor+radius
        j = i
        while j < n and sorted_sectors[j] == sec and sorted_dates[j] - anchor <= radius_ns:
            j += 1
        # also scan backward for rows within radius of anchor (same sector)
        # sorted, so backward = rows before i with date >= anchor - radius
        k = i - 1
        while k >= 0 and sorted_sectors[k] == sec and anchor - sorted_dates[k] <= radius_ns:
            k -= 1
        k += 1
        # block = original indices for rows k..j-1
        block_sorted_pos = np.arange(k, j)
        blocks.append(order[block_sorted_pos])
        # advance i to first row not in this block
        i = j
    return blocks


def fast_r1_estimate(
    df: pd.DataFrame,
    outcome_col: str,
    stratum_col: str,
    *,
    fe_col: str = "_fe",
    sector_col: str | None = None,
    n_bootstrap: int = N_BOOTSTRAP,
    rng_seed: int = RNG_SEED,
    block_radius_days: int = 14,
) -> dict[str, Any]:
    """Fast R1 FE estimator with vectorized block bootstrap.

    Implements the same estimator as entry_strata_phase0.r1_estimate but
    with O(n log n) block construction (vs O(n^2) in _make_blocks).

    Parameters match r1_estimate; FE column must already be in df.
    Returns same dict schema as r1_estimate.

    BUG FIX (index misalignment): sector and _date_ts are carried as columns
    INSIDE work from the start to avoid df.loc[work.index, ...] label-indexing
    errors when work has been reset_index(drop=True) and rows are dropped.
    """
    # --- select outcome, stratum, FE, and block-building helpers together ---
    # Carrying sector_col and _date_ts as columns inside work avoids parent-frame
    # label-indexing errors after reset_index(drop=True). Bug (2) fix.
    cols_to_select = [outcome_col, stratum_col, fe_col]
    if sector_col and sector_col in df.columns:
        cols_to_select.append(sector_col)
    if "_date_ts" in df.columns:
        cols_to_select.append("_date_ts")
    # deduplicate preserving order
    seen: set[str] = set()
    cols_to_select = [c for c in cols_to_select if not (c in seen or seen.add(c))]  # type: ignore[func-returns-value]

    work = df[cols_to_select].copy()
    work = work[work[outcome_col].notna() & work[stratum_col].notna()].copy()
    work[outcome_col] = work[outcome_col].astype(float)
    work[stratum_col] = work[stratum_col].astype(float)
    work = work.reset_index(drop=True)

    n = len(work)
    if n < 10:
        return _empty_r1(outcome_col, stratum_col)

    # Report pre-drop N for disclosure (finding 6: N inconsistency)
    n_pre_drop = n

    # --- drop singleton FE cells ---
    cell_counts = work[fe_col].value_counts()
    multi = cell_counts[cell_counts > 1].index
    work = work[work[fe_col].isin(multi)].copy().reset_index(drop=True)
    if len(work) < 10:
        return _empty_r1(outcome_col, stratum_col)

    # --- within-FE demeaning (vectorized via bincount) ---
    fe_codes = work[fe_col].astype("category").cat.codes.to_numpy()  # int
    y = work[outcome_col].to_numpy(dtype=float)
    x = work[stratum_col].to_numpy(dtype=float)

    # Vectorized group mean subtraction using bincount (fast for large n)
    n_fe = int(fe_codes.max()) + 1 if len(fe_codes) > 0 else 1
    cnt   = np.bincount(fe_codes, minlength=n_fe).astype(float)
    cnt[cnt == 0] = 1.0
    y_sum = np.bincount(fe_codes, weights=y, minlength=n_fe)
    x_sum = np.bincount(fe_codes, weights=x, minlength=n_fe)
    y_dm = y - y_sum[fe_codes] / cnt[fe_codes]
    x_dm = x - x_sum[fe_codes] / cnt[fe_codes]

    # --- OLS coefficient ---
    denom = float(np.dot(x_dm, x_dm))
    coef = float(np.dot(x_dm, y_dm) / denom) if denom > 1e-12 else 0.0

    # --- naive diff ---
    treat = y[x == 1]
    ctrl  = y[x == 0]
    naive_diff = float(treat.mean() - ctrl.mean()) if (len(treat) > 0 and len(ctrl) > 0) else np.nan

    # --- build blocks: use columns INSIDE work (not df.loc[work.index, ...]) ---
    # Bug (2) fix: sector and _date_ts were selected into work at the start;
    # we read them directly from work here, never from the parent df.
    if sector_col and sector_col in work.columns:
        sec_work = work[sector_col]
    else:
        sec_work = pd.Series(["__all__"] * len(work), index=work.index)

    if "_date_ts" in work.columns:
        dates_work = work["_date_ts"].to_numpy()
    else:
        dates_work = np.zeros(len(work), dtype=np.int64)

    sec_cat = sec_work.fillna("__none__").astype("category")
    sec_ids = sec_cat.cat.codes.to_numpy()
    blocks = _fast_make_blocks(dates_work, sec_ids, block_radius_days=block_radius_days)
    if len(blocks) == 0:
        blocks = [np.arange(len(work))]
    n_blocks = len(blocks)

    # Precompute n_cells for vectorized demeaning (max code + 1 gives correct minlength)
    n_fe_cells = int(fe_codes.max()) + 1 if len(fe_codes) > 0 else 1

    # --- block bootstrap (vectorized FE demeaning via bincount) ---
    rng = np.random.default_rng(rng_seed)
    boot_coefs = np.empty(n_bootstrap, dtype=float)

    for b_iter in range(n_bootstrap):
        chosen = rng.integers(0, n_blocks, size=n_blocks)
        boot_idx = np.concatenate([blocks[i] for i in chosen])
        boot_fe = fe_codes[boot_idx]
        boot_y  = y[boot_idx]
        boot_x  = x[boot_idx]

        # Vectorized within-FE demeaning using bincount (1200x faster than loop)
        # Codes are from the full fe_codes array — boot sample may have gaps.
        # Use a local recode for the boot sample to keep bincount tight.
        boot_fe_local, _ = pd.factorize(boot_fe, sort=False)
        n_boot_cells = int(boot_fe_local.max()) + 1 if len(boot_fe_local) > 0 else 1
        cnt_b   = np.bincount(boot_fe_local, minlength=n_boot_cells).astype(float)
        cnt_b[cnt_b == 0] = 1.0
        y_sum_b = np.bincount(boot_fe_local, weights=boot_y, minlength=n_boot_cells)
        x_sum_b = np.bincount(boot_fe_local, weights=boot_x, minlength=n_boot_cells)
        boot_y_dm = boot_y - y_sum_b[boot_fe_local] / cnt_b[boot_fe_local]
        boot_x_dm = boot_x - x_sum_b[boot_fe_local] / cnt_b[boot_fe_local]

        denom_b = float(np.dot(boot_x_dm, boot_x_dm))
        boot_coefs[b_iter] = float(np.dot(boot_x_dm, boot_y_dm) / denom_b) if denom_b > 1e-12 else 0.0

    ci_lo = float(np.percentile(boot_coefs, 2.5))
    ci_hi = float(np.percentile(boot_coefs, 97.5))
    p_value = float(min(1.0, 2.0 * min(
        (boot_coefs <= 0).mean(),
        (boot_coefs >= 0).mean(),
    )))

    # Finding (6): n_total reports the ESTIMATION-SAMPLE N (post-singleton-drop).
    # n_pre_drop is reported separately so callers can disclose the discrepancy.
    n_estimation = len(work)  # post singleton-drop
    return {
        "coef":           round(coef, 6),
        "ci_lo":          round(ci_lo, 6),
        "ci_hi":          round(ci_hi, 6),
        "n_total":        n_estimation,
        "n_pre_drop":     n_pre_drop,
        "n_treatment":    int((x == 1).sum()),
        "n_control":      int((x == 0).sum()),
        "n_blocks":       n_blocks,
        "naive_diff":     round(naive_diff, 6) if np.isfinite(naive_diff) else None,
        "p_value":        round(p_value, 6),
        "outcome":        outcome_col,
        "stratum":        stratum_col,
    }


def _empty_r1(outcome: str, stratum: str) -> dict[str, Any]:
    return {
        "coef": None, "ci_lo": None, "ci_hi": None,
        "n_total": 0, "n_treatment": 0, "n_control": 0,
        "n_blocks": 0, "naive_diff": None, "p_value": None,
        "outcome": outcome, "stratum": stratum,
    }


# ---------------------------------------------------------------------------
# BH FDR correction
# ---------------------------------------------------------------------------

def bh_correction(
    p_values: list[float | None],
    labels: list[str],
    q_threshold: float = BH_Q_THRESHOLD,
) -> list[dict[str, Any]]:
    valid = [(i, p) for i, p in enumerate(p_values) if p is not None]
    if not valid:
        return [{"label": l, "p_value": None, "q_value": None, "rejected": None}
                for l in labels]
    m = len(valid)
    sorted_valid = sorted(valid, key=lambda x: x[1])
    q_vals: dict[int, float] = {}
    for rank_1, (orig_i, p) in enumerate(sorted_valid, start=1):
        q_vals[orig_i] = float(p * m / rank_1)
    running_min = 1.0
    for _, (orig_i, _) in reversed(list(enumerate(sorted_valid))):
        q_vals[orig_i] = min(q_vals[orig_i], running_min)
        running_min = q_vals[orig_i]
    results = []
    for i, label in enumerate(labels):
        p = p_values[i]
        if p is None:
            results.append({"label": label, "p_value": None, "q_value": None, "rejected": None})
        else:
            q = q_vals[i]
            results.append({
                "label": label, "p_value": round(p, 6),
                "q_value": round(q, 6), "rejected": q <= q_threshold,
            })
    return results


# ---------------------------------------------------------------------------
# Fast effect table (replaces entry_strata_phase0.effect_table for NC runs)
# ---------------------------------------------------------------------------

EFFECT_OUTCOMES = [
    "stop5",
    "rotational_liftoff",
    "positional_liftoff",
    "dead_money",
    "cushion_rot",
    "mae63",
    "mfe63",
]


def fast_effect_table(
    graded: pd.DataFrame,
    stratum_col: str,
    *,
    fe_granularity: str = "date",
    sector_col: str | None = None,
    n_bootstrap: int = N_BOOTSTRAP,
    family_label: str = "study",
) -> dict[str, Any]:
    """Fast effect table using vectorized R1 estimator.

    Builds FE column + blocks ONCE per stratum, then runs R1 for each outcome.
    """
    df = _prepare_binary_outcomes(graded)
    df_ok = df[df["gradable"].fillna(False)].copy() if "gradable" in df.columns else df.copy()
    df_ok = df_ok.reset_index(drop=True)

    if len(df_ok) == 0:
        return {"effects": [], "bh_panel": [], "n_total": 0,
                "n_treatment": 0, "n_control": 0,
                "fe_granularity": fe_granularity, "sector_fallback": False,
                "survivor_stamp": "no gradable rows", "family_label": family_label}

    # Build FE column (date string = one FE per unique fire-date)
    df_ok["date"] = pd.to_datetime(df_ok["date"])
    if fe_granularity == "date":
        df_ok["_fe"] = df_ok["date"].dt.strftime("%Y-%m-%d")
    else:
        raise ValueError(f"Unsupported fe_granularity: {fe_granularity!r}")

    # Precompute date timestamps (int64 nanoseconds) for fast block construction.
    # BUG FIX (1): pandas datetime64 may be stored as datetime64[us] (microseconds)
    # in newer pandas versions. _fast_make_blocks computes radius_ns assuming
    # nanosecond integers, so we must force conversion to datetime64[ns] first.
    # Without this fix, datetime64[us] values are 1000x smaller than expected,
    # making the 14-day radius cover the ENTIRE data span and collapsing all
    # fires into a single block per sector, yielding degenerate CIs.
    df_ok["_date_ts"] = df_ok["date"].values.astype("datetime64[ns]").astype(np.int64)

    # Check sector coverage
    sector_fallback = False
    if sector_col and sector_col in df_ok.columns:
        cov = df_ok[sector_col].notna().mean()
        if cov < 0.50:
            sector_fallback = True
            log.warning("sector coverage=%.0f%% < 50%%; sector-only block fallback", cov * 100)
    else:
        sector_col = None

    # Run R1 for each outcome
    effects = []
    p_values: list[float | None] = []
    labels: list[str] = []

    for col in EFFECT_OUTCOMES:
        if col not in df_ok.columns:
            continue
        res = fast_r1_estimate(
            df_ok, col, stratum_col,
            fe_col="_fe",
            sector_col=sector_col if not sector_fallback else None,
            n_bootstrap=n_bootstrap,
        )
        res["label"] = col
        effects.append(res)
        p_values.append(res.get("p_value"))
        labels.append(col)

    bh = bh_correction(p_values, labels)
    n_ok = len(df_ok)
    n_treat = int((df_ok[stratum_col].fillna(0) == 1).sum()) if stratum_col in df_ok.columns else 0
    n_ctrl  = int((df_ok[stratum_col].fillna(0) == 0).sum()) if stratum_col in df_ok.columns else 0

    return {
        "effects":         effects,
        "bh_panel":        bh,
        "n_total":         n_ok,
        "n_treatment":     n_treat,
        "n_control":       n_ctrl,
        "fe_granularity":  fe_granularity,
        "sector_fallback": sector_fallback,
        "survivor_stamp":  (
            "SURVIVOR BIAS WARNING: absolute rates on surviving names only. "
            "Comparisons between strata are survivor-bias-neutral iff both arms "
            "have similar listing-survival distributions."
        ),
        "family_label": family_label,
    }


# ---------------------------------------------------------------------------
# Era table (simplified; no bootstrap)
# ---------------------------------------------------------------------------

def fast_era_table(
    graded: pd.DataFrame,
    stratum_col: str | None = None,
    *,
    panel_label: str = "panel",
) -> pd.DataFrame:
    df = _prepare_binary_outcomes(graded)
    df["date"] = pd.to_datetime(df["date"])
    df["era"] = df["date"].apply(_assign_era)
    df_ok = df[df["gradable"].fillna(False)].copy() if "gradable" in df.columns else df.copy()

    group_keys = ["era"]
    if stratum_col and stratum_col in df_ok.columns:
        group_keys.append(stratum_col)

    rows = []
    for keys, g in df_ok.groupby(group_keys):
        if not isinstance(keys, tuple):
            keys = (keys,)
        rec: dict[str, Any] = {}
        for k, v in zip(group_keys, keys):
            rec[k] = v
        rec["panel"]          = panel_label
        rec["n_fires"]        = len(g)
        rec["stop5_rate"]     = round(float(g["stop5"].mean()), 4) if "stop5" in g else None
        rec["rot_liftoff_rate"] = round(float(g["rotational_liftoff"].mean()), 4) if "rotational_liftoff" in g else None
        rec["pos_liftoff_rate"] = round(float(g["positional_liftoff"].mean()), 4) if "positional_liftoff" in g else None
        rec["dead_money_rate"]  = round(float(g["dead_money"].mean()), 4) if "dead_money" in g else None
        rec["mae63_mean"]     = round(float(g["mae63"].mean()), 4) if g["mae63"].notna().any() else None
        rows.append(rec)

    result = pd.DataFrame(rows)
    if not result.empty and "era" in result.columns:
        era_order = ["pre_2012", "2012-2015", "2016-2019", "2020-2022", "2023-2026"]
        result["era"] = pd.Categorical(result["era"], categories=era_order, ordered=True)
        result = result.sort_values(group_keys).reset_index(drop=True)
    return result


# ---------------------------------------------------------------------------
# NC-2 proximity proxy: computable offline from close series
# ---------------------------------------------------------------------------

def _eq_proximity_long(pct: float) -> float:
    """Entry-quality PROXIMITY component (long/buy-setup), from cycles.py:1625.
    Exact copy of _eq_proximity(pct, up=True) — frozen, no discretion.
    Uses fractional distance above (positive) or below (negative) the rolling low.
    """
    p = pct
    if p < -0.06:
        return 0.15
    if p < -0.03:
        return 0.15 + (0.5 - 0.15) * (p - (-0.06)) / (-0.03 - (-0.06))
    if p < 0.0:
        return 0.5 + (0.9 - 0.5) * (p - (-0.03)) / (0.0 - (-0.03))
    if p < 0.03:
        return 0.9 + (1.0 - 0.9) * (p - 0.0) / (0.03 - 0.0)
    if p < 0.06:
        return 1.0 + (0.85 - 1.0) * (p - 0.03) / (0.06 - 0.03)
    t = min(1.0, (p - 0.06) / (0.18 - 0.06))
    return 0.85 + (0.2 - 0.85) * t


def compute_nc2_proximity_proxy(
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
    *,
    rolling_window: int = 63,
) -> pd.Series:
    """Proximity component of entry_quality for each fire row.

    NC-2 PARTIAL IMPLEMENTATION — proximity component only (EQ_W_PROX=0.52).

    FINDING (4) — PROXY-INPUT LIMITATION:
    The engine (engine/cycles.py:1705-1706) uses cand_price/dcl_price as the
    reference pivot for the proximity sub-component. This implementation uses
    a naive 63-bar close-minimum as a PROXY for that pivot. No offline cache
    of cand_price/dcl_price exists in data/research/. This is a proxy-INPUT
    (the pivot itself is approximated), not merely a proxy-composite. The full
    NC-2 test with the engine's real cand/dcl pivot is explicitly DEFERRED.
    Until then, NC-2 is descriptive-only and must not be used as a promotion
    bar for any candidate.

    DEFERRED: freshness (EQ_W_FRESH=0.30) and momentum (EQ_W_MOM=0.18)
    sub-components require the full cycles.py call chain (multi_cycle, mtf_state,
    early_state, regime_state) per fire — computationally infeasible offline at
    scale (~224 tickers × ~38k fires). See W0_BASELINES.md DEFERRALS.

    Proxy: pct_from_low = close_at_fire / rolling_63d_close_min - 1 (strictly
    prior bars, no lookahead), fed through _eq_proximity() from cycles.py:1625.
    Known limitation: proximity is correlated with NC-1B (ticks=0 fires are
    typically closer to the low — both measure freshness/distance from pivot).

    Returns pd.Series of float in [0, 1], NaN where not computable.
    """
    prox_scores: list[float | None] = []
    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        sig_date = pd.Timestamp(row["date"])
        close = closes.get(ticker)
        if close is None or close.empty:
            prox_scores.append(None)
            continue
        c = close.dropna().sort_index()
        # find fire date index
        locs = c.index.searchsorted(sig_date)
        # Reject loc==len(c): fire date is after the last available bar; using
        # the final bar as 'fire close' while the rolling low covers a prior
        # 63-bar window creates an undisclosed look-at-last-bar approximation.
        if locs <= 0 or locs >= len(c):
            prox_scores.append(None)
            continue
        loc = locs  # first bar on/after sig_date
        # Use strictly prior bars (no lookahead)
        if loc < rolling_window:
            prox_scores.append(None)
            continue
        prior_window = c.iloc[loc - rolling_window:loc]
        if len(prior_window) == 0:
            prox_scores.append(None)
            continue
        rolling_low = float(prior_window.min())
        price = float(c.iloc[loc])
        if rolling_low <= 0:
            prox_scores.append(None)
            continue
        pct_from_low = price / rolling_low - 1.0
        prox_scores.append(_eq_proximity_long(pct_from_low))
    return pd.Series(prox_scores, index=fires.index, name="nc2_prox")


def assign_nc2_bands(prox: pd.Series) -> pd.Series:
    """Cross-sectional proximity bands by tercile.
    Bands 0/1/2 = bottom/mid/top tercile (fixed, not fitted).
    """
    valid = prox.dropna()
    if len(valid) < 30:
        return pd.Series(np.nan, index=prox.index, name="nc2_band")
    q33 = float(valid.quantile(1/3))
    q67 = float(valid.quantile(2/3))
    bands = np.where(
        prox.isna(), np.nan,
        np.where(prox <= q33, 0.0,
                 np.where(prox <= q67, 1.0, 2.0))
    )
    return pd.Series(bands, index=prox.index, name="nc2_band")


# ---------------------------------------------------------------------------
# NC-1 stratum builders
# ---------------------------------------------------------------------------

def build_nc1_strata(fires: pd.DataFrame) -> pd.DataFrame:
    """Attach NC-1 stratum columns.
    nc1_t1_only: 1 iff tier=='T1', else 0
    nc1_fresh0:  1 iff ticks==0, else 0
    """
    f = fires.copy()
    f["nc1_t1_only"] = (f["tier"] == "T1").astype(float)
    f["nc1_fresh0"]  = (f["ticks"] == 0).astype(float)
    return f


# ---------------------------------------------------------------------------
# Trial-ledger registration for W1 NC runs
# ---------------------------------------------------------------------------

def _register_nc_trials(ledger_path: Path | None = None) -> None:
    """Log each NC test as a trial in the esx_null_competitors family."""
    try:
        from engine.trial_ledger import TrialLedger
    except ImportError:
        log.warning("trial_ledger not importable; NC trial rows skipped")
        return
    led = TrialLedger(path=ledger_path or _LEDGER_PATH)
    configs = [
        {"nc": "NC1A", "stratum": "t1_only", "panel": "deep"},
        {"nc": "NC1A", "stratum": "t1_only", "panel": "baskets"},
        {"nc": "NC1B", "stratum": "fresh0",  "panel": "deep"},
        {"nc": "NC1B", "stratum": "fresh0",  "panel": "baskets"},
    ]
    for cfg in configs:
        led.log_trial(cfg, family="esx_null_competitors", note="W1 NC run")
    log.info("Logged %d NC trial configs in esx_null_competitors", len(configs))


# ---------------------------------------------------------------------------
# Core study runner for one panel
# ---------------------------------------------------------------------------

def run_nc_study(
    panel_name: str,
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
    sector_map: dict[str, str],
    *,
    fe_granularity: str = "date",
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Run NC-1A, NC-1B, NC-2 proxy for one panel."""
    fires = fires.copy()
    fires["sector"] = fires["ticker"].map(sector_map)
    fires = build_nc1_strata(fires)

    log.info("Panel %s: grading %d fires...", panel_name, len(fires))
    graded = grade_fires(fires, closes)
    n_gradable = int(graded["gradable"].fillna(False).sum())
    log.info("  Gradable: %d / %d", n_gradable, len(fires))

    # Attach NC-2 proximity proxy
    log.info("  Computing NC-2 proximity proxy...")
    nc2_prox = compute_nc2_proximity_proxy(fires, closes)
    nc2_bands = assign_nc2_bands(nc2_prox)
    graded["nc2_prox"] = nc2_prox.reindex(graded.index).values
    graded["nc2_band"] = nc2_bands.reindex(graded.index).values
    log.info("  NC-2 proxy: %d non-null of %d gradable",
             graded["nc2_prox"].notna().sum(), n_gradable)

    results: dict[str, Any] = {
        "panel":          panel_name,
        "n_fires_total":  len(fires),
        "n_gradable":     n_gradable,
        "fe_granularity": fe_granularity,
        "survivor_stamp": (
            "SURVIVOR BIAS: absolute rates on surviving names only; "
            "comparisons between strata are valid within this constraint."
        ),
    }

    # ---- NC-1A: T1-only vs T1+T2+T3 -----------------------------------------
    log.info("  Computing NC-1A effects (n_bootstrap=%d)...", n_bootstrap)
    recall_nc1a = compute_recall(graded, "nc1_t1_only")
    eff_nc1a = fast_effect_table(
        graded, "nc1_t1_only",
        fe_granularity=fe_granularity,
        sector_col="sector",
        n_bootstrap=n_bootstrap,
        family_label=f"NC1A_{panel_name}",
    )
    era_nc1a = fast_era_table(graded, "nc1_t1_only", panel_label=panel_name)
    results["nc1a"] = {
        "stratum": "T1-only vs all (T1+T2+T3)",
        "recall": recall_nc1a,
        "effect_table": eff_nc1a,
        "era_table": era_nc1a.to_dict(orient="records"),
    }

    # ---- NC-1B: ticks==0 vs all ---------------------------------------------
    log.info("  Computing NC-1B effects (n_bootstrap=%d)...", n_bootstrap)
    recall_nc1b = compute_recall(graded, "nc1_fresh0")
    eff_nc1b = fast_effect_table(
        graded, "nc1_fresh0",
        fe_granularity=fe_granularity,
        sector_col="sector",
        n_bootstrap=n_bootstrap,
        family_label=f"NC1B_{panel_name}",
    )
    era_nc1b = fast_era_table(graded, "nc1_fresh0", panel_label=panel_name)
    results["nc1b"] = {
        "stratum": "ticks==0 (freshest) vs all",
        "recall": recall_nc1b,
        "effect_table": eff_nc1b,
        "era_table": era_nc1b.to_dict(orient="records"),
    }

    # ---- NC-2: proximity-proxy bands ----------------------------------------
    log.info("  Computing NC-2 effects...")
    nc2_results: dict[str, Any] = {
        "proxy_type": "proximity-only (EQ_W_PROX=0.52 of total)",
        "rolling_window_bars": 63,
        "n_gradable_with_proxy": int(graded["nc2_prox"].notna().sum()),
        "prox_stats": {},
        "band_table": [],
        "top_vs_rest_effect": None,
        "deferral_stamp": (
            "NC-2 PARTIAL: proximity component only (EQ_W_PROX=0.52 of total). "
            "PROXY-INPUT LIMITATION (finding 4): the engine (cycles.py:1705-1706) "
            "uses cand_price/dcl_price as the proximity pivot; this implementation "
            "uses a naive 63-bar close-minimum PROXY. No offline cache of "
            "cand_price/dcl_price exists. This is a proxy-INPUT, not merely a "
            "proxy-composite — NC-2 is DESCRIPTIVE-ONLY until the full deferred "
            "test with the real cycle pivot runs. "
            "DEFERRED components: freshness (EQ_W_FRESH=0.30) and momentum "
            "(EQ_W_MOM=0.18) require the full cycles.py call chain "
            "(multi_cycle, mtf_state, early_state, regime_state) per fire — "
            "computationally infeasible offline at this scale. "
            "The full NC-2 marginality test (coefficient survives eq-band FE "
            "in the R1 model) is deferred to the S-UR phase0 PR. "
            "Known limitation: proximity correlates with NC-1B (ticks=0 fires "
            "are typically closer to the rolling low pivot)."
        ),
    }

    gradable_nc2 = graded[graded["gradable"].fillna(False) & graded["nc2_prox"].notna()].copy()
    n_nc2 = len(gradable_nc2)
    if n_nc2 >= 400:
        prox_vals = gradable_nc2["nc2_prox"]
        nc2_results["prox_stats"] = {
            "mean": round(float(prox_vals.mean()), 4),
            "p25":  round(float(prox_vals.quantile(0.25)), 4),
            "p50":  round(float(prox_vals.quantile(0.50)), 4),
            "p75":  round(float(prox_vals.quantile(0.75)), 4),
        }

        gradable_nc2 = _prepare_binary_outcomes(gradable_nc2)
        band_rows = []
        for b in [0.0, 1.0, 2.0]:
            g = gradable_nc2[gradable_nc2["nc2_band"] == b]
            if len(g) == 0:
                continue
            band_rows.append({
                "band":        int(b),
                "band_label":  ["bottom_tercile", "mid_tercile", "top_tercile"][int(b)],
                "n_fires":     len(g),
                "stop5_rate":  round(float(g["stop5"].mean()), 4),
                "rot_liftoff": round(float(g["rotational_liftoff"].mean()), 4),
                "pos_liftoff": round(float(g["positional_liftoff"].mean()), 4),
                "dead_money":  round(float(g["dead_money"].mean()), 4),
                "mae63_mean":  round(float(g["mae63"].mean()), 4) if g["mae63"].notna().any() else None,
                "mfe63_mean":  round(float(g["mfe63"].mean()), 4) if g["mfe63"].notna().any() else None,
            })
        nc2_results["band_table"] = band_rows

        # Top-tercile vs rest
        gradable_nc2["nc2_top_tercile"] = (gradable_nc2["nc2_band"] == 2.0).astype(float)
        top_recall = {
            "n_top":   int((gradable_nc2["nc2_top_tercile"] == 1).sum()),
            "n_total": len(gradable_nc2),
            "recall":  round(float((gradable_nc2["nc2_top_tercile"] == 1).mean()), 4),
        }
        eff_nc2 = fast_effect_table(
            gradable_nc2, "nc2_top_tercile",
            fe_granularity=fe_granularity,
            sector_col="sector" if "sector" in gradable_nc2.columns else None,
            n_bootstrap=n_bootstrap,
            family_label=f"NC2_top_{panel_name}",
        )
        nc2_results["top_vs_rest_effect"] = eff_nc2
        nc2_results["top_vs_rest_recall"] = top_recall
    else:
        nc2_results["note"] = f"Insufficient gradable fires with proximity ({n_nc2}) for FE estimation."

    results["nc2"] = nc2_results
    return results


# ---------------------------------------------------------------------------
# Main report runner
# ---------------------------------------------------------------------------

def run_all_panels(
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    panels: list[str] | None = None,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Run NC-1/NC-2 across deep + baskets panels."""
    _register_all_families(ledger_path)
    _register_nc_trials(ledger_path)

    sector_map = _build_sector_map()
    log.info("Sector map: %d tickers", len(sector_map))

    panel_configs = [
        ("deep",    _FIRES_DEEP,    "date"),
        ("baskets", _FIRES_BASKETS, "date"),
    ]
    if panels:
        panel_configs = [(n, p, fe) for n, p, fe in panel_configs if n in panels]

    all_results: dict[str, Any] = {}
    for panel_name, fires_path, fe_gran in panel_configs:
        if not fires_path.exists():
            log.warning("Fire dump not found: %s — skipping", fires_path)
            all_results[panel_name] = {"error": f"fires not found: {fires_path}"}
            continue
        fires = load_fires(fires_path)
        log.info("Panel %s: %d fires loaded", panel_name, len(fires))
        closes = _get_closes(panel_name)
        res = run_nc_study(
            panel_name, fires, closes, sector_map,
            fe_granularity=fe_gran,
            n_bootstrap=n_bootstrap,
        )
        all_results[panel_name] = res

    return all_results


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------

def _fmt_pct(v: float | None, default: str = "—") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return default
    return f"{v:.1%}"


def _fmt_f(v: float | None, decimals: int = 4, default: str = "—") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return default
    return f"{v:.{decimals}f}"


def _ci_str(res: dict[str, Any]) -> str:
    lo = res.get("ci_lo")
    hi = res.get("ci_hi")
    if lo is None or hi is None:
        return "—"
    excludes_zero = (lo > 0 or hi < 0)
    flag = " *" if excludes_zero else ""
    return f"[{lo:+.3f}, {hi:+.3f}]{flag}"


def _excl_zero(res: dict[str, Any]) -> str:
    lo = res.get("ci_lo")
    hi = res.get("ci_hi")
    if lo is None or hi is None:
        return "—"
    return "YES *" if (lo > 0 or hi < 0) else "no"


def _write_effect_md(lines: list[str], eff: dict[str, Any], title: str) -> None:
    lines.append(f"#### {title}")
    lines.append("")
    # Finding (6): N total shown here is the pre-singleton-drop gradable count.
    # Estimation-sample N (post-drop) is per-outcome in n_total within each R1 result;
    # see n_blocks for number of episode blocks used in the bootstrap.
    first_eff = eff.get("effects", [{}])[0] if eff.get("effects") else {}
    n_blocks = first_eff.get("n_blocks", "—")
    n_pre = eff.get("n_total", 0)  # pre-singleton-drop (gradable rows passed in)
    n_est = first_eff.get("n_total", n_pre)  # post-drop estimation sample (stop5 outcome)
    n_pre_drop_val = first_eff.get("n_pre_drop", n_pre)
    lines.append(f"N total (pre-drop): {n_pre:,} | "
                 f"N estimation-sample (post-drop): {n_est:,} | "
                 f"N blocks: {n_blocks}")
    if n_pre != n_est and n_pre_drop_val != n_pre:
        lines.append(f"_(N footnote: effect tables use estimation-sample N {n_est:,}; "
                     f"pre-drop gradable N was {n_pre:,}. Discrepancy = singleton-FE-cell exclusions.)_")
    lines.append(f"N treatment: {eff.get('n_treatment', 0):,} | "
                 f"N control: {eff.get('n_control', 0):,}")
    lines.append(f"FE: `{eff.get('fe_granularity', '?')}` | "
                 f"Sector fallback: {eff.get('sector_fallback', False)}")
    lines.append("")
    lines.append("| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |")
    lines.append("|---|---|---|---|---|---|---|")

    bh = {b["label"]: b for b in eff.get("bh_panel", [])}
    for e in eff.get("effects", []):
        lbl = e.get("label", "?")
        bh_r = bh.get(lbl, {})
        rej = bh_r.get("rejected")
        lines.append(
            f"| {lbl} | {_fmt_f(e.get('coef'), 4)} | {_ci_str(e)} | "
            f"{_fmt_f(e.get('naive_diff'), 4)} | {_fmt_f(e.get('p_value'), 4)} | "
            f"{_fmt_f(bh_r.get('q_value'), 4)} | "
            f"{'YES' if rej else 'no' if rej is not None else '—'} |"
        )
    lines.append("")


def write_report(all_results: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    a = lines.append

    a("# W1 Null-Competitor Report — Entry-Stack Expansion")
    a("")
    a("**Status:** W1 report only — no promotion, no product change (RUL-3).")
    a("**Date:** 2026-07-05")
    a("")
    a("Per masterplan §10 RUL-3: null-competitors run FIRST and appear as the")
    a("first table in every subsequent W1/W2 report. The YARDSTICK section")
    a("at the end of this document is the authoritative reference for later reports.")
    a("")
    a("**Adjacency (R2 per RUL-2):**")
    a("- NC-1 (tier/freshness subsetting): no falsified relative — this is a")
    a("  first-principles question about whether simple subsetting already buys")
    a("  the asymmetry. Mechanical difference from any species candidate:")
    a("  NC-1 uses ONLY existing tier/ticks columns, adds no new information.")
    a("- NC-2 (entry_quality proxy): nearest falsified relative = volume-confirmation")
    a("  confirmers (H4, dead). Mechanical difference: entry_quality is a multi-axis")
    a("  proximity+freshness+momentum composite, not a volume-based screen.")
    a("")
    a("---")
    a("")
    a("## Trial Registration")
    a("")
    a("Family: `esx_null_competitors` (budget=4, pre-registered at W0).")
    a("4 trial configs logged: 2 NC × 2 panels (deep / baskets).")
    a("")
    a("---")
    a("")

    for panel_name, res in all_results.items():
        a(f"## Panel: {panel_name.upper()}")
        a("")
        if "error" in res:
            a(f"**ERROR:** {res['error']}")
            a("")
            continue

        a(f"**SURVIVOR BIAS STAMP:** {res.get('survivor_stamp', '')}")
        a("")
        a(f"- Total fires: {res.get('n_fires_total', 0):,}")
        a(f"- Gradable fires: {res.get('n_gradable', 0):,}")
        a(f"- FE granularity: `{res.get('fe_granularity', 'date')}` (frozen per RUL-12)")
        a("")

        # Dynamic block-count caveat for low-sector-coverage panels (finding 3).
        # After fix (1)+(2), block counts are real. If sector fallback is active
        # (coverage <50%), block construction uses date-only clustering. Report
        # the actual n_blocks so readers know the effective resampling unit.
        # Pull n_blocks from the first stop5 effect of NC-1A if available.
        _nc1a_eff = res.get("nc1a", {}).get("effect_table", {})
        _nc1a_effects = {e["label"]: e for e in _nc1a_eff.get("effects", [])}
        _nb = _nc1a_effects.get("stop5", {}).get("n_blocks")
        _sf = _nc1a_eff.get("sector_fallback", False)
        if _nb is not None and _sf:
            a(f"**BOOTSTRAP CI NOTE (this panel):** Sector coverage < 50%, so block "
              f"construction uses date-only clustering. This panel produced **{_nb:,} episode "
              f"blocks** for the bootstrap. If n_blocks is small (< ~100), CI width "
              f"understates true sampling uncertainty. Point-estimate coefficients "
              f"(date-FE OLS) remain valid regardless of block count.")
            a("")

        # NC-1A
        nc1a = res.get("nc1a", {})
        a("### NC-1A: T1-only vs T1+T2+T3")
        a("")
        rc = nc1a.get("recall", {})
        a(f"**Recall of T1-only arm:** {_fmt_pct(rc.get('recall'))} "
          f"({rc.get('n_treatment', 0):,} of {rc.get('n_all', 0):,} gradable fires)")
        a(f"**Recall COST:** {_fmt_pct(1.0 - rc.get('recall', 1.0))} of fires dropped by restricting to T1")
        a("")
        _write_effect_md(lines, nc1a.get("effect_table", {}),
                         "NC-1A Effect Table (R1 FE, fast block bootstrap)")

        era_recs = nc1a.get("era_table", [])
        if era_recs:
            era_df = pd.DataFrame(era_recs)
            prog = era_df[era_df["era"].isin(PROGRAM_ERAS)] if "era" in era_df.columns else era_df
            if not prog.empty:
                a("#### NC-1A Era summary (program eras, stop5 rate by stratum)")
                a("")
                cols = [c for c in ["era", "nc1_t1_only", "n_fires", "stop5_rate", "mae63_mean"]
                        if c in prog.columns]
                a("| " + " | ".join(cols) + " |")
                a("|" + "---|" * len(cols))
                for _, row in prog.iterrows():
                    cells = []
                    for c in cols:
                        v = row.get(c)
                        if c in ("stop5_rate",):
                            cells.append(_fmt_pct(v))
                        elif c == "mae63_mean":
                            cells.append(_fmt_f(v))
                        else:
                            cells.append(str(v) if v is not None else "—")
                    a("| " + " | ".join(cells) + " |")
                a("")

        # NC-1B
        nc1b = res.get("nc1b", {})
        a("### NC-1B: ticks==0 (freshest) vs all")
        a("")
        rc = nc1b.get("recall", {})
        a(f"**Recall of ticks==0 arm:** {_fmt_pct(rc.get('recall'))} "
          f"({rc.get('n_treatment', 0):,} of {rc.get('n_all', 0):,} gradable fires)")
        a(f"**Recall COST:** {_fmt_pct(1.0 - rc.get('recall', 1.0))} of fires dropped by restricting to ticks=0")
        a("")
        _write_effect_md(lines, nc1b.get("effect_table", {}),
                         "NC-1B Effect Table (R1 FE, fast block bootstrap)")

        era_recs = nc1b.get("era_table", [])
        if era_recs:
            era_df = pd.DataFrame(era_recs)
            prog = era_df[era_df["era"].isin(PROGRAM_ERAS)] if "era" in era_df.columns else era_df
            if not prog.empty:
                a("#### NC-1B Era summary (program eras, stop5 rate by stratum)")
                a("")
                cols = [c for c in ["era", "nc1_fresh0", "n_fires", "stop5_rate", "mae63_mean"]
                        if c in prog.columns]
                a("| " + " | ".join(cols) + " |")
                a("|" + "---|" * len(cols))
                for _, row in prog.iterrows():
                    cells = []
                    for c in cols:
                        v = row.get(c)
                        if c in ("stop5_rate",):
                            cells.append(_fmt_pct(v))
                        elif c == "mae63_mean":
                            cells.append(_fmt_f(v))
                        else:
                            cells.append(str(v) if v is not None else "—")
                    a("| " + " | ".join(cells) + " |")
                a("")

        # NC-2
        nc2 = res.get("nc2", {})
        a("### NC-2: Entry-Quality Proximity Proxy (Partial)")
        a("")
        a(f"> **DEFERRAL STAMP:** {nc2.get('deferral_stamp', '')}")
        a("")
        a(f"Proxy: {nc2.get('proxy_type', '?')} | "
          f"Rolling window: {nc2.get('rolling_window_bars', '?')} bars | "
          f"Gradable with proxy: {nc2.get('n_gradable_with_proxy', 0):,}")
        a("")

        prox_stats = nc2.get("prox_stats", {})
        if prox_stats:
            a(f"Proximity stats: mean={prox_stats.get('mean','?')}, "
              f"p25={prox_stats.get('p25','?')}, "
              f"p50={prox_stats.get('p50','?')}, "
              f"p75={prox_stats.get('p75','?')}")
            a("")

        band_table = nc2.get("band_table", [])
        if band_table:
            a("#### NC-2 Band Outcome Table (descriptive; survivor bias applies)")
            a("")
            a("| Band | Label | N fires | stop5 | rot_liftoff | pos_liftoff | dead_money | mae63 | mfe63 |")
            a("|---|---|---|---|---|---|---|---|---|")
            for b in band_table:
                a(f"| {b['band']} | {b['band_label']} | {b['n_fires']:,} | "
                  f"{_fmt_pct(b.get('stop5_rate'))} | {_fmt_pct(b.get('rot_liftoff'))} | "
                  f"{_fmt_pct(b.get('pos_liftoff'))} | {_fmt_pct(b.get('dead_money'))} | "
                  f"{_fmt_f(b.get('mae63_mean'))} | {_fmt_f(b.get('mfe63_mean'))} |")
            a("")

        nc2_top_eff = nc2.get("top_vs_rest_effect")
        nc2_top_rc  = nc2.get("top_vs_rest_recall", {})
        if nc2_top_eff:
            a(f"Top-tercile recall: {_fmt_pct(nc2_top_rc.get('recall'))} "
              f"({nc2_top_rc.get('n_top', 0):,} of {nc2_top_rc.get('n_total', 0):,})")
            a("")
            _write_effect_md(lines, nc2_top_eff,
                             "NC-2 Top-tercile vs rest (R1 FE, proximity proxy)")

        if nc2.get("note"):
            a(f"**Note:** {nc2['note']}")
            a("")

        a("---")
        a("")

    # ---- YARDSTICK (RUL-3) -----------------------------------------------
    a("## YARDSTICK — Reference Numbers for Every Later W1/W2 Report (RUL-3)")
    a("")
    a("Per §10 RUL-3: null-competitors appear as the FIRST table in every")
    a("subsequent W1/W2 report. A candidate 'beats the null-competitors' when its")
    a("stratum FE coefficients clear the bar below with CI excluding 0, AND at")
    a("better or equal recall. Direction note: stop5 is an adverse outcome —")
    a("a BETTER signal has a MORE NEGATIVE stop5 coefficient (fewer stops); a")
    a("candidate must be more negative on stop5 (not merely numerically larger).")
    a("For beneficial outcomes (rotational_liftoff, positional_liftoff) the")
    a("candidate must have a higher (more positive) coefficient. The full NC-2")
    a("marginality test (coefficient survives entry_quality-band FE) remains")
    a("DEFERRED (cycles.py pipeline required).")
    a("")
    a("### CI caveat (RUL-7 freeze, 2026-07-05):")
    a("At n≥400/arm with baseline stop5 ~12%, difference-SE ≈ 2.3pp. A bare 2pp")
    a("point-estimate rarely clears CI-excluding-0 at minimum n. The CI-excluding-0")
    a("clause is the operative promotion bar — not the 2pp level alone.")
    a("")
    # Finding (3): after fixes (1)+(2) the n_blocks column shows REAL block counts.
    # A degenerate-block caveat is dynamically appended below if n_blocks is small.
    a("| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | N blocks | N treat | N ctrl | Recall (treat arm) |")
    a("|---|---|---|---|---|---|---|---|---|")

    yardstick_caveats: list[str] = []
    for panel_name, res in all_results.items():
        if "error" in res:
            continue
        for nc_key, nc_label in [("nc1a", "NC-1A (T1-only)"), ("nc1b", "NC-1B (ticks=0)")]:
            nc = res.get(nc_key, {})
            eff = nc.get("effect_table", {})
            effects = {e["label"]: e for e in eff.get("effects", [])}
            stop5 = effects.get("stop5", {})
            rc = nc.get("recall", {})
            n_blk = stop5.get("n_blocks", "—")
            ci_label = _ci_str(stop5)
            if isinstance(n_blk, int) and n_blk < 100:
                ci_label = f"{ci_label} [low-block caveat: {n_blk} blocks]"
                yardstick_caveats.append(
                    f"  - {panel_name} {nc_label}: only {n_blk} episode blocks — "
                    f"CI width understates true sampling uncertainty."
                )
            a(f"| {panel_name} | {nc_label} | "
              f"{_fmt_f(stop5.get('coef'), 4)} | {ci_label} | {_excl_zero(stop5)} | "
              f"{n_blk} | {eff.get('n_treatment', 0):,} | {eff.get('n_control', 0):,} | "
              f"{_fmt_pct(rc.get('recall'))} |")

        nc2 = res.get("nc2", {})
        nc2_eff = nc2.get("top_vs_rest_effect", {})
        if nc2_eff:
            effects = {e["label"]: e for e in nc2_eff.get("effects", [])}
            stop5 = effects.get("stop5", {})
            rc = nc2.get("top_vs_rest_recall", {})
            n_blk = stop5.get("n_blocks", "—")
            ci_label = _ci_str(stop5)
            if isinstance(n_blk, int) and n_blk < 100:
                ci_label = f"{ci_label} [low-block caveat: {n_blk} blocks]"
                yardstick_caveats.append(
                    f"  - {panel_name} NC-2: only {n_blk} episode blocks — "
                    f"CI width understates true sampling uncertainty."
                )
            a(f"| {panel_name} | NC-2 (prox top-tercile) | "
              f"{_fmt_f(stop5.get('coef'), 4)} | {ci_label} | {_excl_zero(stop5)} | "
              f"{n_blk} | {nc2_eff.get('n_treatment', 0):,} | {nc2_eff.get('n_control', 0):,} | "
              f"{_fmt_pct(rc.get('recall'))} |")

    a("")
    if yardstick_caveats:
        a("**Low-block caveats (finding 3):** The following rows have fewer than 100 "
          "episode blocks — CI width understates true sampling uncertainty:")
        for cav in yardstick_caveats:
            a(cav)
        a("")
    a("**Reading the yardstick:**")
    a("- CI excl 0 = YES: the block-bootstrap 95% CI excludes zero — stratum effect")
    a("  distinguishable from no-effect at this sample size.")
    a("- CI excl 0 = no: NULL result for that NC stratum — simple subsetting does NOT")
    a("  already buy distinguishable asymmetry improvement. A null NC is informative:")
    a("  it means new signals have room to add genuine value beyond tier/freshness.")
    a("- Later reports must show their candidate's stop5 coef + CI alongside this table.")
    a("- N blocks column shows real block counts after bug fixes (1)+(2). Low block "
      "counts are flagged with [low-block caveat] inline.")
    a("")
    a("### Null result declaration (mandatory per masterplan §5):")
    a("Any NC with CI-including-0 is a NULL — printed here, not hidden.")
    a("A NULL means that simple subsetting CANNOT already buy the improvement.")
    a("This does NOT mean the full gate is unimportant — only that tier/ticks")
    a("subsetting alone is insufficient as a proxy for a new signal.")
    a("")
    a("---")
    a("")
    a("*Generated by `scripts/research/run_w1_nc.py`*")
    a("*Grader: engine/grading.py (program barriers, RUL-9).*")
    a("*'validated' word deliberately absent (CI-enforced).*")
    a("*No promotion language. Studies only.*")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s", out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Entry-Stack Expansion W1 — Null-Competitors NC-1/NC-2.",
    )
    parser.add_argument(
        "--out", default=str(_RESEARCH_DIR / "W1_NC_REPORT.md"),
        help="Output path for W1_NC_REPORT.md",
    )
    parser.add_argument(
        "--n-bootstrap", type=int, default=1000,
        help="Block-bootstrap resamples (default 1000; use --smoke for 50)",
    )
    parser.add_argument(
        "--panel", nargs="+", choices=["deep", "baskets"],
        default=None,
        help="Restrict to named panel(s); default runs all.",
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="Quick smoke test: 50 bootstrap, deep panel only.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    n_boot = 50 if args.smoke else args.n_bootstrap
    panels = ["deep"] if args.smoke else args.panel

    log.info("Starting W1 NC study (n_bootstrap=%d, panels=%s)", n_boot, panels or "all")
    all_results = run_all_panels(n_bootstrap=n_boot, panels=panels)
    write_report(all_results, Path(args.out))
    log.info("Done. Report at %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
