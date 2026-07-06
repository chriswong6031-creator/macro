"""Long-Hold Thesis Layer — W1 PR-F: Missed-Hold Kill-Test Study.

Pre-registration: research/long_hold/OBJECTIVE.md (LOCKED, including Amendment A1).
Masterplan: research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md.
Fable rulings: LH-W1-1, LH-W1-2, LH-W1-3.

This script implements EXACTLY the W1 kill-test as specified in OBJECTIVE.md:
  1. Nine-feature at-entry family (OBJECTIVE.md §5), computed PIT at each fire date
     via fundamentals_panel.parquet as_of_cross_section (period_end+120d lag).
     Features with < 20% non-null coverage in the honest cohort are dropped with
     documentation (per §5 drop rule).
  2. Contrast: missed_hold (compounder among tactical wins) vs tactical_only.
  3. Inference: BH-FDR q=0.10 across the family; cluster-robust/block-bootstrap
     per §6.2; episode-cluster floors per §6.3; within-regime reshuffle null per §6.4.
  4. Temporal protocol: fit 2014-2019 (UPPER-BOUND survivor-caveated);
     OOS 2020-2023 honest cohort (G1 decision cell).
  5. Mandatory sensitivity runs:
       - fund_unchecked: primary analysis excluding fund_unchecked=True fires
       - Amendment A1: market-benchmark reassignment of no-benchmark G fires
  6. Outputs:
       data/research/missed_hold_study_results.parquet
       research/long_hold/W1_KILLTEST_RESULTS.md

Does NOT declare G1 fate. Ends with "G1 ratification: PENDING FABLE RULING".

Feature computation from fundamentals_panel.parquet (all PIT via period_end+120d):
  piotroski_f       — already in long_hold_labels.parquet; used directly
  quality_z         — cross-sectional z-score of quality composite: ROA + CFO/assets
                      (op_income unavailable; cfo used as income proxy per coverage note)
  profitability_z   — cross-sectional z-score of: NI/assets + CFO/assets
  sue               — standardized unexpected earnings: (ni - ni_prior) / assets_prior
                      (no consensus EPS; accounting SUE proxy only)
  insider_cmp       — NOT COMPUTABLE from fundamentals_panel (no insider filing data);
                      coverage = 0%; dropped per §5 drop rule
  interest_coverage — NOT COMPUTABLE from fundamentals_panel (interest_exp absent);
                      coverage < 20%; dropped per §5 drop rule
  dilution_flag     — shares YoY > +3%: (shares / shares_prior - 1) > 0.03
  gross_margin_trend — 3-year slope of gross_profit/revenue across last 3 annual PIT rows
  archetype         — NOT PRE-COMPUTED in any parquet; coverage = 0%; dropped per §5

All features are computed at fire_date using PIT cross-section
(as_of_cross_section with period_end+120d lag from fundamentals_panel).

Usage:
    python scripts/research/missed_hold_study.py
    python scripts/research/missed_hold_study.py --dry-run
    python scripts/research/missed_hold_study.py --fit-only   # exploration only
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Bootstrap repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA = _REPO_ROOT / "data"
_LABELS_PATH = _DATA / "research" / "long_hold_labels.parquet"
_FUNDAMENTALS_PANEL = _DATA / "edgar" / "fundamentals_panel.parquet"
_REGIME_HISTORY = _DATA / "regime" / "regime_history.parquet"
_OUT_PARQUET = _DATA / "research" / "missed_hold_study_results.parquet"
_OUT_MD = _REPO_ROOT / "research" / "long_hold" / "W1_KILLTEST_RESULTS.md"

# ---------------------------------------------------------------------------
# Constants (OBJECTIVE.md §6-§7)
# ---------------------------------------------------------------------------
BH_Q_THRESHOLD = 0.10          # §6.1
RESHUFFLE_SEED = 42             # §6.4 — LOCKED in pre-registration; do not change
BOOTSTRAP_SEED_BLOCK = 43       # §6.2 block-bootstrap CI — distinct from RESHUFFLE_SEED
                                # (should-fix: shared seeds cause correlated draws across
                                #  independent inference gates §6.2 and §6.4)
BOOTSTRAP_SEED_CLUSTER = 44     # §6.2 cluster-bootstrap CI — distinct from RESHUFFLE_SEED
N_RESHUFFLE = 1000              # §6.4
N_BOOTSTRAP = 1000              # §6.2
BLOCK_RADIUS_DAYS = 14          # §6.3: spec says ±10 TRADING days; 14 CALENDAR days is an
                                # approximation (undercounts across holidays; ~10 trading days
                                # in most weeks). See deviation note in deduplicate_episode_clusters.
EPISODE_FLOOR = 25              # §6.3 minimum episode-cluster count
BLOCK_WIDTH = 63                # trading days for block-bootstrap fallback (§6.2)
                                # Note: BLOCK_WIDTH is labeled in trading days but the block
                                # assignment arithmetic in _block_bootstrap_rbc uses calendar-day
                                # arithmetic (dt.days // (BLOCK_WIDTH * 1.4)). Deviation documented.

FIT_START = "2014-01-01"        # §7
FIT_END   = "2019-12-31"        # §7
OOS_START = "2020-01-01"        # §7
OOS_END   = "2023-12-31"        # §7
# 2024+ reserved: do NOT use

# Feature coverage threshold for dropping (§5)
COVERAGE_FLOOR = 0.20

# Nine frozen features per OBJECTIVE.md §5
FROZEN_FEATURES = [
    "piotroski_f",
    "quality_z",
    "profitability_z",
    "sue",
    "insider_cmp",        # expected 0% coverage → dropped
    "interest_coverage",  # expected <20% coverage → dropped
    "dilution_flag",
    "gross_margin_trend",
    "archetype",          # expected 0% coverage → dropped
]


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------

def _compute_pit_features(
    ticker: str,
    fire_date: pd.Timestamp,
    panel_by_ticker: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """Compute the nine frozen W1 features PIT at fire_date for one ticker.

    PIT mechanism: for each feature, take the latest FY row where
    asof_date <= fire_date (asof_date = period_end + 120d lag in the panel).

    Returns dict with one key per FROZEN_FEATURES entry (None if unavailable).
    """
    rows_all = panel_by_ticker.get(ticker)
    if rows_all is None or len(rows_all) == 0:
        return {f: None for f in FROZEN_FEATURES}

    # PIT filter: only rows with asof_date <= fire_date
    pit_rows = rows_all[rows_all["asof_date"] <= fire_date].sort_values("fy")
    if len(pit_rows) == 0:
        return {f: None for f in FROZEN_FEATURES}

    latest = pit_rows.iloc[-1]

    def n(col: str) -> float | None:
        v = latest.get(col) if isinstance(latest, dict) else (
            latest[col] if col in latest.index else None
        )
        if v is None:
            return None
        try:
            fv = float(v)
            return None if np.isnan(fv) else fv
        except (TypeError, ValueError):
            return None

    assets = n("assets")
    assets_prior = n("assets_prior")
    ni = n("ni")
    ni_prior = n("ni_prior")
    cfo = n("cfo")
    gross_profit = n("gross_profit")
    revenue = n("revenue")
    shares = n("shares")

    # --- piotroski_f: not recomputed here; read from labels ---
    piotroski_f = None  # will be merged from labels later

    # --- quality_z: ROA + CFO/assets composite (cross-sectional z computed later) ---
    roa = (ni / assets) if (ni is not None and assets not in (None, 0.0)) else None
    cfo_a = (cfo / assets) if (cfo is not None and assets not in (None, 0.0)) else None
    quality_raw = None
    if roa is not None and cfo_a is not None:
        quality_raw = roa + cfo_a
    elif roa is not None:
        quality_raw = roa
    elif cfo_a is not None:
        quality_raw = cfo_a

    # --- profitability_z: NI/assets + CFO/assets (separate from quality_z) ---
    # quality_z uses the composite; profitability_z is the same here since
    # we lack op_income. Store as separate raw value; will z-score later.
    profitability_raw = quality_raw  # same inputs; z-scored independently

    # --- sue: standardized unexpected earnings (ni - ni_prior) / assets_prior ---
    sue_raw = None
    if (ni is not None and ni_prior is not None
            and assets_prior not in (None, 0.0)):
        sue_raw = (ni - ni_prior) / assets_prior

    # --- insider_cmp: NOT COMPUTABLE from fundamentals_panel ---
    insider_cmp = None

    # --- interest_coverage: NOT COMPUTABLE from fundamentals_panel ---
    # (interest_exp absent from panel; op_income absent from panel)
    interest_coverage = None

    # --- dilution_flag: shares YoY > +3% ---
    # Need prior year shares. Use the second-to-last PIT row if available.
    dilution_flag = None
    if len(pit_rows) >= 2:
        prior_row = pit_rows.iloc[-2]
        def n_row(row: Any, col: str) -> float | None:
            v = row[col] if col in row.index else None
            if v is None:
                return None
            try:
                fv = float(v)
                return None if np.isnan(fv) else fv
            except (TypeError, ValueError):
                return None
        shares_prior = n_row(prior_row, "shares")
        if shares is not None and shares_prior not in (None, 0.0):
            dilution_flag = float((shares / shares_prior - 1.0) > 0.03)

    # --- gross_margin_trend: 3-year slope of gross_profit/revenue ---
    gross_margin_trend = None
    if len(pit_rows) >= 3:
        recent_3 = pit_rows.iloc[-3:]
        gm_vals = []
        for _, row in recent_3.iterrows():
            gp = row.get("gross_profit") if hasattr(row, "get") else row["gross_profit"] if "gross_profit" in row.index else None
            rv = row.get("revenue") if hasattr(row, "get") else row["revenue"] if "revenue" in row.index else None
            try:
                gp_f = float(gp) if gp is not None else None
                rv_f = float(rv) if rv is not None else None
                if gp_f is not None and rv_f not in (None, 0.0):
                    gm_vals.append(gp_f / rv_f)
                else:
                    gm_vals.append(None)
            except (TypeError, ValueError):
                gm_vals.append(None)
        valid = [(i, v) for i, v in enumerate(gm_vals) if v is not None]
        if len(valid) >= 2:
            xs = np.array([i for i, _ in valid], dtype=float)
            ys = np.array([v for _, v in valid], dtype=float)
            xs_dm = xs - xs.mean()
            denom = float(np.dot(xs_dm, xs_dm))
            if denom > 1e-12:
                gross_margin_trend = float(np.dot(xs_dm, ys - ys.mean()) / denom)

    # --- archetype: NOT PRE-COMPUTED ---
    archetype = None

    return {
        "piotroski_f":       piotroski_f,  # filled from labels
        "quality_raw":       quality_raw,   # z-scored cross-sectionally
        "profitability_raw": profitability_raw,
        "sue":               sue_raw,
        "insider_cmp":       insider_cmp,
        "interest_coverage": interest_coverage,
        "dilution_flag":     dilution_flag,
        "gross_margin_trend":gross_margin_trend,
        "archetype":         archetype,
    }


def _zscore_raw_features(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Cross-sectional z-score for raw features across the entire dataset.

    Z-scores are computed on the full dataset at once (not per date) since
    the features are already PIT; this gives a global ranking scale.
    Winsorized at ±5 sigma before z-scoring to reduce outlier influence.
    """
    df = df.copy()
    for feat in features:
        if feat not in df.columns:
            continue
        col = df[feat].copy()
        notna = col.notna()
        if notna.sum() < 10:
            continue
        vals = col[notna].copy()
        mu = vals.mean()
        sigma = vals.std(ddof=1)
        if sigma < 1e-10:
            df.loc[notna, feat] = 0.0
            continue
        # winsorize
        lo, hi = mu - 5 * sigma, mu + 5 * sigma
        vals_clip = vals.clip(lo, hi)
        mu2 = vals_clip.mean()
        sigma2 = vals_clip.std(ddof=1)
        if sigma2 < 1e-10:
            df.loc[notna, feat] = 0.0
        else:
            df.loc[notna, feat] = ((vals_clip - mu2) / sigma2).values
    return df


# ---------------------------------------------------------------------------
# Regime labeling
# ---------------------------------------------------------------------------

def _attach_macro_regime(df: pd.DataFrame, regime_path: Path) -> pd.DataFrame:
    """Attach macro_regime (Q1..Q4) to each fire via backward-fill from regime_history."""
    df = df.copy()
    if not regime_path.exists():
        log.warning("regime_history.parquet not found; macro_regime will be null")
        df["macro_regime"] = None
        return df
    regime = pd.read_parquet(regime_path)
    if "quad" not in regime.columns:
        log.warning("regime_history.parquet missing 'quad' column")
        df["macro_regime"] = None
        return df
    regime_quad = regime["quad"]
    fire_dates = pd.to_datetime(df["fire_date"])
    # Map each fire date to its most-recent regime label via merge_asof
    fires_df = pd.DataFrame({"fire_date": fire_dates.values}).drop_duplicates().sort_values("fire_date")
    rq_df = regime_quad.reset_index().rename(columns={"index": "date", 0: "macro_regime", "quad": "macro_regime"})
    rq_df = rq_df.sort_values("date").dropna(subset=["macro_regime"])
    merged = pd.merge_asof(fires_df, rq_df, left_on="fire_date", right_on="date", direction="backward")
    regime_map = merged.set_index("fire_date")["macro_regime"]
    df["macro_regime"] = fire_dates.map(regime_map).values
    log.info(
        "macro_regime: %d/%d non-null (dist: %s)",
        df["macro_regime"].notna().sum(), len(df),
        df["macro_regime"].value_counts().to_dict(),
    )
    return df


# ---------------------------------------------------------------------------
# Episode-cluster deduplication (OBJECTIVE.md §6.3)
# ---------------------------------------------------------------------------

def deduplicate_episode_clusters(
    df: pd.DataFrame,
    key_cols: tuple[str, ...] = ("ticker", "macro_regime"),
    date_col: str = "fire_date",
    window_days: int = BLOCK_RADIUS_DAYS,
) -> pd.DataFrame:
    """Greedy left-to-right deduplication per §6.3.

    For each (ticker × macro_regime) group, retain only the earliest fire_date
    in any ±window_days window. Returns deduplicated DataFrame.

    DEVIATION FROM OBJECTIVE.md §6.3 (documented per should-fix):
    §6.3 specifies "±10 TRADING days (measured on fire_date)."
    This implementation uses BLOCK_RADIUS_DAYS=14 CALENDAR days, which is an
    approximation of 10 trading days (typical ~2-week span). Calendar-day measurement
    undercounts across holiday-heavy weeks and may retain ~1-2% extra clusters at
    holiday boundaries. Impact on the DEFERRED verdict is nil (4 compounders regardless
    of dedup window), but the fit and OOS-all cluster counts quoted as inferential n are
    computed on a calendar-day proxy for a trading-day spec.
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col).reset_index(drop=True)
    keep_mask = np.zeros(len(df), dtype=bool)
    last_retained: dict[tuple, pd.Timestamp] = {}

    for idx, row in df.iterrows():
        key = tuple(
            str(row[k]) if pd.notna(row[k]) else "__none__"
            for k in key_cols
        )
        fd = row[date_col]
        prev = last_retained.get(key)
        if prev is None or abs((fd - prev).days) > window_days:
            keep_mask[idx] = True
            last_retained[key] = fd

    dedup = df[keep_mask].reset_index(drop=True)
    log.info(
        "Episode-cluster dedup: %d -> %d rows (%.1f%% retained)",
        len(df), len(dedup), 100.0 * len(dedup) / max(len(df), 1),
    )
    return dedup


# ---------------------------------------------------------------------------
# Feature coverage check (OBJECTIVE.md §5)
# ---------------------------------------------------------------------------

def check_feature_coverage(df: pd.DataFrame, features: list[str]) -> dict[str, float]:
    """Compute non-null coverage for each feature in the dataset."""
    n = max(len(df), 1)
    return {f: float(df[f].notna().sum() / n) if f in df.columns else 0.0
            for f in features}


def drop_low_coverage_features(
    df: pd.DataFrame,
    features: list[str],
    coverage: dict[str, float],
    floor: float = COVERAGE_FLOOR,
) -> tuple[list[str], list[str]]:
    """Return (retained_features, dropped_features) based on coverage floor."""
    retained, dropped = [], []
    for f in features:
        if f not in df.columns:
            dropped.append(f)
        elif coverage.get(f, 0.0) >= floor:
            retained.append(f)
        else:
            dropped.append(f)
    return retained, dropped


# ---------------------------------------------------------------------------
# Mann-Whitney U (rank-biserial correlation) — the per-feature test statistic
# ---------------------------------------------------------------------------

def _mann_whitney_rbc(
    x1: np.ndarray,
    x2: np.ndarray,
) -> tuple[float, float]:
    """Mann-Whitney U rank-biserial correlation and two-sided p-value.

    x1 = feature values for group 1 (missed_hold=True)
    x2 = feature values for group 2 (tactical_only)
    Returns (rbc, p_value) where rbc ∈ [-1, 1].
    """
    x1 = x1[~np.isnan(x1)]
    x2 = x2[~np.isnan(x2)]
    n1, n2 = len(x1), len(x2)
    if n1 == 0 or n2 == 0:
        return np.nan, np.nan

    # Mann-Whitney U
    combined = np.concatenate([x1, x2])
    ranks = pd.Series(combined).rank(method="average").values
    u1 = ranks[:n1].sum() - n1 * (n1 + 1) / 2
    u2 = n1 * n2 - u1

    # Rank-biserial correlation (RBC)
    rbc = float(2 * u1 / (n1 * n2) - 1)

    # Normal approximation p-value (two-sided)
    u = min(u1, u2)
    mean_u = n1 * n2 / 2
    std_u = np.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    if std_u < 1e-10:
        p_val = 1.0
    else:
        z = (u - mean_u) / std_u
        from scipy import stats as _stats  # noqa: PLC0415
        p_val = float(2 * _stats.norm.sf(abs(z)))

    return rbc, min(1.0, p_val)


# ---------------------------------------------------------------------------
# BH-FDR correction (OBJECTIVE.md §6.1)
# ---------------------------------------------------------------------------

def bh_fdr(
    p_values: list[float | None],
    labels: list[str],
    q: float = BH_Q_THRESHOLD,
) -> list[dict[str, Any]]:
    """Benjamini-Hochberg step-up FDR correction.

    None p-values (dropped features or insufficient data) are excluded from
    the correction but retained in output with rejected=None.
    """
    valid = [(i, p) for i, p in enumerate(p_values) if p is not None and not np.isnan(p)]
    m = len(valid)
    out = []
    q_map: dict[int, float] = {}

    if valid:
        sorted_valid = sorted(valid, key=lambda x: x[1])
        for rank1, (orig_i, p) in enumerate(sorted_valid, start=1):
            q_map[orig_i] = float(p * m / rank1)
        # enforce monotonicity
        running_min = 1.0
        for _, (orig_i, _) in reversed(list(enumerate(sorted_valid))):
            q_map[orig_i] = min(q_map[orig_i], running_min)
            running_min = q_map[orig_i]

    for i, (lbl, p) in enumerate(zip(labels, p_values)):
        if p is None or np.isnan(p):
            out.append({"feature": lbl, "p_value": p, "q_value": None, "rejected": None})
        else:
            qv = q_map[i]
            out.append({
                "feature": lbl,
                "p_value": round(float(p), 6),
                "q_value": round(qv, 6),
                "rejected": bool(qv <= q),
            })
    return out


# ---------------------------------------------------------------------------
# Block-bootstrap CI for RBC (OBJECTIVE.md §6.2)
# ---------------------------------------------------------------------------

def _block_bootstrap_rbc(
    df: pd.DataFrame,
    feature: str,
    outcome_col: str,
    date_col: str = "fire_date",
    block_width: int = BLOCK_WIDTH,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED_BLOCK,
) -> dict[str, Any]:
    """Block-bootstrap 95% CI for the RBC of feature vs missed_hold.

    Block structure: consecutive time blocks of block_width trading days.
    Returns dict with ci_lo, ci_hi, n_blocks.
    """
    df = df[[feature, outcome_col, date_col]].dropna().copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col).reset_index(drop=True)

    if len(df) < 10:
        return {"ci_lo": np.nan, "ci_hi": np.nan, "n_blocks": 0}

    # Build time blocks: assign each row to a block by calendar position
    min_date = df[date_col].min()
    df["_block_id"] = ((df[date_col] - min_date).dt.days // (block_width * 1.4)).astype(int)
    block_ids = df["_block_id"].unique()
    n_blocks = len(block_ids)

    rng = np.random.default_rng(BOOTSTRAP_SEED_BLOCK)
    boot_rbcs = []
    for _ in range(n_bootstrap):
        chosen_blocks = rng.choice(block_ids, size=n_blocks, replace=True)
        boot_rows = pd.concat(
            [df[df["_block_id"] == b] for b in chosen_blocks], ignore_index=True
        )
        mh = boot_rows[boot_rows[outcome_col] == 1][feature].dropna().values
        to = boot_rows[boot_rows[outcome_col] == 0][feature].dropna().values
        if len(mh) == 0 or len(to) == 0:
            continue
        rbc, _ = _mann_whitney_rbc(mh, to)
        if not np.isnan(rbc):
            boot_rbcs.append(rbc)

    if len(boot_rbcs) < 10:
        return {"ci_lo": np.nan, "ci_hi": np.nan, "n_blocks": n_blocks}

    arr = np.array(boot_rbcs)
    return {
        "ci_lo": round(float(np.percentile(arr, 2.5)), 4),
        "ci_hi": round(float(np.percentile(arr, 97.5)), 4),
        "n_blocks": n_blocks,
    }


def _cluster_robust_ci(
    df: pd.DataFrame,
    feature: str,
    outcome_col: str,
    sector_col: str = "ticker",   # fallback: ticker as cluster ID
    regime_col: str = "macro_regime",
) -> dict[str, Any]:
    """CI via sector×macro_regime clustering.

    DEVIATION FROM OBJECTIVE.md §6.2 (documented per should-fix):
    §6.2 specifies clustering by (ticker_SECTOR × macro_regime).
    The labels parquet has no sector-category column (only sector_rel_252d as a
    continuous return); the ticker→sector mapping covers only the 503/2,495 tickers
    that map to the 11 EW basket names. This function therefore clusters by
    (ticker × macro_regime) as a finer-grained proxy. Ticker-level clustering is
    finer than sector-level and may understate within-sector error correlation,
    biasing CIs slightly narrow. The §6.2 "wider CI governs" rule (block-bootstrap
    fallback) partially mitigates this. Results tables in the markdown carry a
    "(ticker × macro_regime)" note in the inference design section.

    Computes the RBC cluster-by-cluster and bootstraps the cluster-level RBCs.
    Where regime is unavailable, falls back to block-bootstrap.
    Returns dict with ci_lo, ci_hi, method.
    """
    sub = df[[feature, outcome_col, sector_col, regime_col, "fire_date"]].dropna(
        subset=[feature, outcome_col]
    ).copy()
    if len(sub) < 10:
        return {"ci_lo": np.nan, "ci_hi": np.nan, "method": "insufficient_data"}

    # cluster column = ticker × regime (deviation from §6.2 sector×regime: see docstring)
    sub["_cluster"] = (
        sub[sector_col].astype(str) + "|" + sub[regime_col].astype(str).fillna("none")
    )
    cluster_rbcs = []
    for _, grp in sub.groupby("_cluster"):
        mh = grp[grp[outcome_col] == 1][feature].dropna().values
        to = grp[grp[outcome_col] == 0][feature].dropna().values
        if len(mh) == 0 or len(to) == 0:
            continue
        rbc, _ = _mann_whitney_rbc(mh, to)
        if not np.isnan(rbc):
            cluster_rbcs.append(rbc)

    if len(cluster_rbcs) < 5:
        # Fall back to block-bootstrap
        bb = _block_bootstrap_rbc(df, feature, outcome_col)
        bb["method"] = "block_bootstrap_fallback"
        return bb

    arr = np.array(cluster_rbcs)
    # Bootstrap over cluster-level RBCs (distinct seed from reshuffle null per should-fix)
    rng = np.random.default_rng(BOOTSTRAP_SEED_CLUSTER)
    boot = rng.choice(arr, size=(N_BOOTSTRAP, len(arr)), replace=True).mean(axis=1)

    bb = _block_bootstrap_rbc(df, feature, outcome_col)
    cluster_ci_lo = float(np.percentile(boot, 2.5))
    cluster_ci_hi = float(np.percentile(boot, 97.5))

    # Take the wider CI (more conservative per §6.2)
    ci_lo = min(cluster_ci_lo, bb.get("ci_lo", cluster_ci_lo))
    ci_hi = max(cluster_ci_hi, bb.get("ci_hi", cluster_ci_hi))

    return {
        "ci_lo": round(ci_lo, 4),
        "ci_hi": round(ci_hi, 4),
        "method": "cluster_wider",
        "cluster_ci_lo": round(cluster_ci_lo, 4),
        "cluster_ci_hi": round(cluster_ci_hi, 4),
        "block_bootstrap_ci_lo": round(bb.get("ci_lo", np.nan), 4),
        "block_bootstrap_ci_hi": round(bb.get("ci_hi", np.nan), 4),
    }


# ---------------------------------------------------------------------------
# Within-regime reshuffle null (OBJECTIVE.md §6.4)
# ---------------------------------------------------------------------------

def reshuffle_null(
    df: pd.DataFrame,
    feature: str,
    outcome_col: str,
    cohort_year_col: str = "cohort_year",
    regime_col: str = "macro_regime",
    n_shuffle: int = N_RESHUFFLE,
    seed: int = RESHUFFLE_SEED,
) -> dict[str, Any]:
    """Within-(cohort_year × macro_regime) reshuffle null per §6.4.

    Permutes missed_hold within each (cohort_year × macro_regime) cell n_shuffle times.
    Returns the 90th-percentile of the null distribution and whether the observed
    statistic exceeds it (one-sided, consistent with q=0.10).
    """
    sub = df[[feature, outcome_col, cohort_year_col, regime_col]].dropna(
        subset=[feature, outcome_col]
    ).copy()

    if len(sub) < 10:
        return {
            "null_p90": np.nan,
            "observed_rbc": np.nan,
            "passes_reshuffle": None,
            "n_shuffle": n_shuffle,
            "note": "insufficient data",
        }

    # Observed RBC
    mh_obs = sub[sub[outcome_col] == 1][feature].dropna().values
    to_obs = sub[sub[outcome_col] == 0][feature].dropna().values
    obs_rbc, _ = _mann_whitney_rbc(mh_obs, to_obs)

    # Cell labels for permutation
    sub["_cell"] = sub[cohort_year_col].astype(str) + "|" + sub[regime_col].astype(str).fillna("none")
    cells = sub["_cell"].unique()

    rng = np.random.default_rng(seed)
    null_rbcs = []
    for _ in range(n_shuffle):
        shuffled = sub.copy()
        for cell in cells:
            mask = shuffled["_cell"] == cell
            cell_outcomes = shuffled.loc[mask, outcome_col].values.copy()
            rng.shuffle(cell_outcomes)
            shuffled.loc[mask, outcome_col] = cell_outcomes
        mh_s = shuffled[shuffled[outcome_col] == 1][feature].dropna().values
        to_s = shuffled[shuffled[outcome_col] == 0][feature].dropna().values
        if len(mh_s) == 0 or len(to_s) == 0:
            null_rbcs.append(0.0)
            continue
        rbc_s, _ = _mann_whitney_rbc(mh_s, to_s)
        if not np.isnan(rbc_s):
            null_rbcs.append(rbc_s)

    if len(null_rbcs) < 10:
        return {
            "null_p90": np.nan,
            "observed_rbc": float(obs_rbc),
            "passes_reshuffle": None,
            "n_shuffle": n_shuffle,
            "note": "null distribution degenerate",
        }

    null_arr = np.array(null_rbcs)
    p90 = float(np.percentile(null_arr, 90))
    passes = bool(not np.isnan(obs_rbc) and obs_rbc > p90)

    return {
        "null_p90": round(p90, 4),
        "observed_rbc": round(float(obs_rbc), 4),
        "passes_reshuffle": passes,
        "n_shuffle": n_shuffle,
    }


# ---------------------------------------------------------------------------
# Core analysis for one split/sensitivity variant
# ---------------------------------------------------------------------------

def run_analysis(
    df_split: pd.DataFrame,
    features: list[str],
    split_label: str,
    survivorship_note: str,
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    n_shuffle: int = N_RESHUFFLE,
) -> dict[str, Any]:
    """Run the full W1 analysis on a given data split.

    Parameters
    ----------
    df_split:
        DataFrame with columns: missed_hold (binary 0/1), label,
        features from FROZEN_FEATURES, cohort_year, macro_regime, fire_date,
        survivorship_biased.
    features:
        List of feature names to test (post-coverage-filter).
    split_label:
        Identifier for this split (e.g. 'OOS_2020-2023').
    survivorship_note:
        Human-readable stamp for this split.

    Returns dict with per-feature results, BH panel, episode-cluster counts.
    """
    # Subset to missed_hold contrast: missed_hold=True vs label=tactical_only
    df_contrast = df_split[
        df_split["label"].isin(["compounder", "tactical_only"])
    ].copy()
    df_contrast["missed_hold_bin"] = (df_contrast["label"] == "compounder").astype(int)

    # Episode-cluster deduplication (§6.3)
    df_dedup = deduplicate_episode_clusters(
        df_contrast,
        key_cols=("ticker", "macro_regime"),
        date_col="fire_date",
        window_days=BLOCK_RADIUS_DAYS,
    )

    n_clusters_total = len(df_dedup)
    n_missed_hold = int((df_dedup["missed_hold_bin"] == 1).sum())
    n_tactical_only = int((df_dedup["missed_hold_bin"] == 0).sum())

    log.info(
        "%s: dedup clusters=%d, missed_hold=%d, tactical_only=%d",
        split_label, n_clusters_total, n_missed_hold, n_tactical_only,
    )

    # Check episode-cluster floor (§6.3)
    floor_met = (n_missed_hold >= EPISODE_FLOOR and n_tactical_only >= EPISODE_FLOOR)
    floor_note = ""
    if not floor_met:
        floor_note = (
            f"n-floor NOT MET: missed_hold clusters={n_missed_hold}, "
            f"tactical_only clusters={n_tactical_only}. "
            f"Floor requires ≥{EPISODE_FLOOR} per group. "
            "Results for this split are REFUSED per OBJECTIVE.md §6.3 "
            "and routed to survivorship-deferral path per §8."
        )
        log.warning(floor_note)

    # Per-feature results
    feature_results = []
    p_values_for_bh = []
    bh_labels = []

    for feat in features:
        if feat not in df_dedup.columns or df_dedup[feat].notna().sum() < 5:
            feature_results.append({
                "feature": feat,
                "status": "insufficient_data",
                "n_covered": 0,
            })
            p_values_for_bh.append(None)
            bh_labels.append(feat)
            continue

        if not floor_met:
            # Floor not met: record but mark refused
            n_cov = df_dedup[feat].notna().sum()
            feature_results.append({
                "feature": feat,
                "status": "refused_floor_not_met",
                "n_covered": int(n_cov),
            })
            p_values_for_bh.append(None)
            bh_labels.append(feat)
            continue

        sub = df_dedup[[feat, "missed_hold_bin", "cohort_year", "macro_regime", "fire_date",
                         "ticker"]].dropna(subset=[feat, "missed_hold_bin"]).copy()
        mh_vals = sub[sub["missed_hold_bin"] == 1][feat].dropna().values
        to_vals = sub[sub["missed_hold_bin"] == 0][feat].dropna().values

        if len(mh_vals) < 2 or len(to_vals) < 2:
            feature_results.append({
                "feature": feat, "status": "insufficient_coverage",
                "n_missed_hold_covered": len(mh_vals),
                "n_tactical_only_covered": len(to_vals),
            })
            p_values_for_bh.append(None)
            bh_labels.append(feat)
            continue

        rbc, p_val = _mann_whitney_rbc(mh_vals, to_vals)
        n_cov_mh = len(mh_vals)
        n_cov_to = len(to_vals)

        # Effect size (Cohen's d approximation via RBC)
        # RBC = 2*AUC - 1; convert to Cohen's d: d ≈ 2*rbc / sqrt(1 - rbc^2)
        if not np.isnan(rbc) and abs(rbc) < 1.0:
            cohens_d_approx = 2 * rbc / np.sqrt(1 - rbc ** 2)
        else:
            cohens_d_approx = np.nan

        # Cluster-robust CI
        ci_result = _cluster_robust_ci(sub, feat, "missed_hold_bin")

        # Reshuffle null
        reshuffle_result = reshuffle_null(sub, feat, "missed_hold_bin")

        feature_results.append({
            "feature": feat,
            "status": "computed",
            "rbc": round(float(rbc), 4) if not np.isnan(rbc) else None,
            "p_value_raw": round(float(p_val), 6) if not np.isnan(p_val) else None,
            "cohens_d_approx": round(float(cohens_d_approx), 4) if not np.isnan(cohens_d_approx) else None,
            "ci_lo": ci_result.get("ci_lo"),
            "ci_hi": ci_result.get("ci_hi"),
            "ci_method": ci_result.get("method"),
            "n_missed_hold_covered": n_cov_mh,
            "n_tactical_only_covered": n_cov_to,
            "missed_hold_mean": round(float(np.nanmean(mh_vals)), 4),
            "tactical_only_mean": round(float(np.nanmean(to_vals)), 4),
            "reshuffle_null_p90": reshuffle_result.get("null_p90"),
            "reshuffle_observed_rbc": reshuffle_result.get("observed_rbc"),
            "passes_reshuffle_null": reshuffle_result.get("passes_reshuffle"),
            "reshuffle_n_draws": reshuffle_result.get("n_shuffle"),
        })
        p_values_for_bh.append(float(p_val) if not np.isnan(p_val) else None)
        bh_labels.append(feat)

    # BH-FDR correction (§6.1)
    bh_panel = bh_fdr(p_values_for_bh, bh_labels)

    # Attach BH results to per-feature records
    bh_by_feat = {r["feature"]: r for r in bh_panel}
    for fr in feature_results:
        feat = fr["feature"]
        if feat in bh_by_feat:
            bh_r = bh_by_feat[feat]
            fr["q_value_bh"] = bh_r.get("q_value")
            fr["rejected_bh_fdr"] = bh_r.get("rejected")

    # G1 condition check per §8 (three gates: BH-FDR, reshuffle, n-floor)
    g1_survivors = []
    for fr in feature_results:
        if fr.get("status") != "computed":
            continue
        passes_bh = fr.get("rejected_bh_fdr") is True
        passes_reshuffle = fr.get("passes_reshuffle_null") is True
        if passes_bh and passes_reshuffle:
            g1_survivors.append(fr["feature"])

    g1_condition_met = len(g1_survivors) > 0 and floor_met
    g1_status = (
        "DEFERRED_N_FLOOR"    if not floor_met else
        "SURVIVE"             if g1_condition_met else
        "KILL"
    )

    return {
        "split_label": split_label,
        "survivorship_note": survivorship_note,
        "n_clusters_total": n_clusters_total,
        "n_missed_hold_clusters": n_missed_hold,
        "n_tactical_only_clusters": n_tactical_only,
        "floor_met": floor_met,
        "floor_note": floor_note,
        "feature_results": feature_results,
        "bh_panel": bh_panel,
        "g1_survivors": g1_survivors,
        "g1_status": g1_status,
    }


# ---------------------------------------------------------------------------
# Amendment A1 label reassignment (OBJECTIVE.md Amendment A1)
# ---------------------------------------------------------------------------

def apply_amendment_a1(
    df_all: pd.DataFrame,
    labels_full: pd.DataFrame,
) -> pd.DataFrame:
    """Reassign no-benchmark sector_laggard_winner fires using market benchmark.

    Per Amendment A1:
    - For every fire where sector_rel_252d is null at labeling time, replace
      sector_rel_252d with market_rel_252d = name's 252d return minus equal-weight
      average 252d return across all resolvable tickers for that fire.
    - Reapply label assignment logic to affected fires.

    SPEC-INFEASIBILITY NOTE (must-fix, LH-W1-2):
    ---
    OBJECTIVE.md Amendment A1 defines the benchmark constituent set S(f) as:
      "every ticker in the fire tape whose 252-trading-day fill-anchored forward
       price path is FULLY RESOLVABLE (no NaN, length == 252) as of that fire's
       own fire_date."

    This per-fire S(f) is NOT computable from long_hold_labels.parquet alone because:
    - The labels parquet only records rows that achieved ≥252 matured bars AND were
      tactical wins. Specifically:
        - 34,604 tactical_only_fail fires have total_return_252d=null (never lifted off;
          their 252d paths may be resolvable but were never computed by the label harness).
        - 65,723 unlabeled fires have total_return_252d=null (unmatured, no_price, or
          unmatured_126).
    - The filter `full[full['total_return_252d'].notna()]` therefore covers ONLY the
      ~13,215 rows with non-null total_return_252d — all of which are tactical wins
      with usable 252d legs: cheap_trap (4,409), tactical_only (4,406),
      sector_laggard_winner (3,404), multiple_expansion_only (801), compounder (195).
    - tactical_only_fail fires (which form the bulk of dead-name candidates) are
      entirely EXCLUDED from the benchmark pool.

    Consequence: the cohort-year mean used here is a WINNER-SELECTED, UPWARD-BIASED
    benchmark — it excludes all fires that never achieved tactical liftoff, which
    are disproportionately the worst-performing names. This depresses (makes less
    negative) market_rel_252d for surviving names, shifting Label G (sector_laggard_winner)
    back toward compounder — exactly the direction that inflated the A1 SURVIVE result.

    The 2021 benchmark of 0.0178 computed below is drawn entirely from this winner-
    selected pool. The 128 no-benchmark SLW fires in the honest OOS window with
    total_return_252d ranging 0.116–2.548 (all positive, all strong performers) flip
    to compounder when compared against a ~1.78% winner-pool mean. That flip produces
    the A1 honest compounder count of 132 and drives the A1 SURVIVE result.

    Per must-fix ruling: A1 results are reported with this spec-infeasibility flag.
    The A1 SURVIVE verdict is NOT presented as evidence on the pre-registered S(f)
    specification — it is an approximate sensitivity only. See §7 of the results doc.
    ---

    The exact S(f) requires iterating the full price tape per fire_date — a computation
    that requires access to the raw price store, not the labels parquet.
    """
    df_a1 = df_all.copy()

    # Get the full label set (not just kill-test subset) for market benchmark computation
    full = labels_full.copy()
    full["fire_date"] = pd.to_datetime(full["fire_date"])
    full["cohort_year"] = full["fire_date"].dt.year

    # Compute cohort-year market benchmark: mean of total_return_252d for
    # all fires with a non-null 252d return.
    #
    # WINNER-SELECTION NOTE: only tactical-win rows have non-null total_return_252d
    # in the labels parquet. tactical_only_fail (34,604) and unlabeled (65,723) rows
    # are excluded. This benchmark is upward-biased relative to the spec's S(f).
    # See SPEC-INFEASIBILITY NOTE in this docstring for full consequences.
    ew_benchmark = (
        full[full["total_return_252d"].notna()]
        .groupby("cohort_year")["total_return_252d"]
        .mean()
    )
    log.info(
        "A1 market benchmark (cohort-year EW mean, WINNER-SELECTED pool only): %s",
        ew_benchmark.to_dict(),
    )
    log.warning(
        "A1 SPEC-INFEASIBILITY: benchmark computed from winner-selected tactical-win pool "
        "only (excludes %d tactical_only_fail + %d unlabeled rows with null 252d returns). "
        "A1 results are approximate sensitivity only — NOT the pre-registered S(f). "
        "See apply_amendment_a1 docstring and §7 of W1_KILLTEST_RESULTS.md.",
        int((labels_full["label"] == "tactical_only_fail").sum()),
        int((labels_full["label"] == "unlabeled").sum()),
    )

    # For fires where sector_rel_252d is null AND label == sector_laggard_winner:
    # recompute label using market_rel_252d
    df_a1["fire_date"] = pd.to_datetime(df_a1["fire_date"])
    needs_a1 = (
        df_a1["sector_rel_252d"].isna() &
        df_a1["total_return_252d"].notna()
    )
    log.info("A1: fires needing reassignment = %d", needs_a1.sum())

    if needs_a1.sum() == 0:
        log.info("A1: no fires need reassignment (no null sector_rel_252d in kill-test)")
        df_a1["a1_applied"] = False
        df_a1["market_rel_252d"] = np.nan
        return df_a1

    # Compute market_rel_252d for affected fires
    df_a1["market_benchmark"] = df_a1["cohort_year"].map(ew_benchmark)
    df_a1["market_rel_252d"] = np.where(
        needs_a1,
        df_a1["total_return_252d"] - df_a1["market_benchmark"],
        np.nan,
    )

    # Reapply label assignment for affected fires
    # Tercile cutoffs are pre-computed in labels (tercile_rank column)
    # Re-use existing tercile_rank; just update the benchmark comparison
    def reassign_label(row: pd.Series) -> str:
        if not (
            pd.notna(row.get("total_return_252d"))
            and pd.notna(row.get("tercile_rank"))
            and pd.notna(row.get("market_rel_252d"))
        ):
            return row["label"]
        tercile = row["tercile_rank"]
        mrel = row["market_rel_252d"]
        pf = row.get("piotroski_f")
        fund_unchecked = row.get("fund_unchecked", False)
        if tercile >= 0.67:
            if mrel >= 0:
                # top tercile + beats market
                if (pf is not None and pf >= 6) or fund_unchecked:
                    return "compounder"
                elif pf is not None and pf < 6:
                    return "multiple_expansion_only"
                else:
                    # coverage waived
                    return "compounder"
            else:
                return "sector_laggard_winner"
        elif tercile < 0.33:
            return "cheap_trap"
        else:
            return "tactical_only"

    reassigned_labels = df_a1[needs_a1].apply(reassign_label, axis=1)
    df_a1.loc[needs_a1, "label"] = reassigned_labels
    df_a1.loc[needs_a1, "a1_applied"] = True
    df_a1.loc[~needs_a1, "a1_applied"] = False

    # Update missed_hold flag
    df_a1["missed_hold"] = (df_a1["label"] == "compounder").astype(bool)

    n_reassigned = needs_a1.sum()
    n_now_compounder = (df_a1.loc[needs_a1, "label"] == "compounder").sum()
    n_now_tactical = (df_a1.loc[needs_a1, "label"] == "tactical_only").sum()
    log.info(
        "A1 reassignment: %d fires → %d compounder, %d tactical_only, "
        "%d sector_laggard_winner (remaining)",
        n_reassigned, n_now_compounder, n_now_tactical,
        (df_a1.loc[needs_a1, "label"] == "sector_laggard_winner").sum(),
    )
    return df_a1


# ---------------------------------------------------------------------------
# Main: build feature panel and run all analyses
# ---------------------------------------------------------------------------

def build_feature_panel(
    labels: pd.DataFrame,
    fundamentals_panel: pd.DataFrame,
) -> pd.DataFrame:
    """Join nine frozen features to the kill-test label set.

    For each (ticker, fire_date) in the kill-test subset (compounder + tactical_only),
    compute PIT features from fundamentals_panel.
    """
    # Index fundamentals panel by ticker for fast lookup
    fp_by_ticker: dict[str, pd.DataFrame] = {}
    for ticker, grp in fundamentals_panel.groupby("ticker"):
        grp = grp.copy()
        grp["asof_date"] = pd.to_datetime(grp["asof_date"])
        grp = grp.sort_values("asof_date")
        fp_by_ticker[str(ticker)] = grp

    kt = labels[labels["label"].isin(["compounder", "tactical_only"])].copy()
    kt["fire_date"] = pd.to_datetime(kt["fire_date"])
    kt["cohort_year"] = kt["fire_date"].dt.year
    log.info("Building feature panel for %d kill-test fires", len(kt))

    # Compute raw features
    raw_features = {
        "quality_raw": [],
        "profitability_raw": [],
        "sue": [],
        "insider_cmp": [],
        "interest_coverage": [],
        "dilution_flag": [],
        "gross_margin_trend": [],
        "archetype": [],
    }

    for _, row in kt.iterrows():
        ticker = str(row["ticker"])
        fire_date = row["fire_date"]
        feats = _compute_pit_features(ticker, fire_date, fp_by_ticker)
        for k in raw_features:
            raw_features[k].append(feats.get(k))

    for col, vals in raw_features.items():
        kt[col] = vals

    # piotroski_f is already in the labels parquet; use it directly
    # (it was computed PIT by long_hold_label_panel.py)

    log.info(
        "Raw feature coverage: %s",
        {k: sum(v is not None and not (isinstance(v, float) and np.isnan(v)) for v in vals)
         for k, vals in raw_features.items()},
    )

    # Cross-sectional z-scoring for quality_raw and profitability_raw
    # (done globally on the kill-test set; within-split z-scoring would be data leakage)
    kt = _zscore_raw_features(kt, ["quality_raw", "profitability_raw", "sue"])

    # Rename z-scored columns to final feature names
    kt = kt.rename(columns={
        "quality_raw": "quality_z",
        "profitability_raw": "profitability_z",
    })

    return kt


def main(dry_run: bool = False, fit_only: bool = False) -> None:
    """Run the full W1 kill-test study."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # -------------------------------------------------------------------
    # Load inputs
    # -------------------------------------------------------------------
    log.info("Loading labels: %s", _LABELS_PATH)
    if not _LABELS_PATH.exists():
        raise FileNotFoundError(f"labels parquet not found: {_LABELS_PATH}")
    labels = pd.read_parquet(_LABELS_PATH)
    labels["fire_date"] = pd.to_datetime(labels["fire_date"])

    log.info("Loading fundamentals panel: %s", _FUNDAMENTALS_PANEL)
    if not _FUNDAMENTALS_PANEL.exists():
        raise FileNotFoundError(f"fundamentals_panel not found: {_FUNDAMENTALS_PANEL}")
    fundamentals_panel = pd.read_parquet(_FUNDAMENTALS_PANEL)

    # -------------------------------------------------------------------
    # Build feature panel
    # -------------------------------------------------------------------
    log.info("Building feature panel...")
    kt = build_feature_panel(labels, fundamentals_panel)
    kt = _attach_macro_regime(kt, _REGIME_HISTORY)

    # -------------------------------------------------------------------
    # Coverage check (OBJECTIVE.md §5 drop rule)
    # -------------------------------------------------------------------
    all_9 = [
        "piotroski_f", "quality_z", "profitability_z", "sue",
        "insider_cmp", "interest_coverage", "dilution_flag",
        "gross_margin_trend", "archetype",
    ]
    coverage = check_feature_coverage(kt, all_9)
    log.info("Feature coverage (kill-test set): %s", {f: f"{v:.2%}" for f, v in coverage.items()})

    retained_features, dropped_features = drop_low_coverage_features(
        kt, all_9, coverage, COVERAGE_FLOOR
    )
    log.info("Retained features: %s", retained_features)
    log.info("Dropped features (< 20%% coverage): %s", dropped_features)

    if dry_run:
        log.info("DRY RUN: stopping before analysis. Feature panel shape: %s", kt.shape)
        return

    # -------------------------------------------------------------------
    # Temporal splits
    # -------------------------------------------------------------------
    fit_mask = (kt["fire_date"] >= FIT_START) & (kt["fire_date"] <= FIT_END)
    oos_mask  = (kt["fire_date"] >= OOS_START)  & (kt["fire_date"] <= OOS_END)

    kt_fit = kt[fit_mask].copy()
    kt_oos = kt[oos_mask].copy()

    # Honest OOS = survivorship_biased=False only.
    # NOTE: explicit == False comparison (not ~astype(bool)) to avoid coercing None → False.
    # astype(bool) maps None→False (treats unknown-survivorship fires as honest), which is
    # a latent correctness trap if the label harness ever emits null survivorship in-window.
    kt_oos_honest = kt_oos[kt_oos["survivorship_biased"] == False].copy()  # noqa: E712

    log.info("Fit period fires (kill-test): %d", len(kt_fit))
    log.info("OOS period fires (kill-test, all): %d", len(kt_oos))
    log.info("OOS period fires (kill-test, honest): %d", len(kt_oos_honest))

    all_results: dict[str, Any] = {
        "study_metadata": {
            "prereg_doc": "research/long_hold/OBJECTIVE.md",
            "masterplan": "research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md",
            "fdr_family": "long_hold",
            "bh_q_threshold": BH_Q_THRESHOLD,
            "n_reshuffle": N_RESHUFFLE,
            "n_bootstrap": N_BOOTSTRAP,
            "reshuffle_seed": RESHUFFLE_SEED,
            "episode_floor": EPISODE_FLOOR,
            "fit_period": f"{FIT_START} to {FIT_END}",
            "oos_period": f"{OOS_START} to {OOS_END}",
            "all_9_features": all_9,
            "retained_features": retained_features,
            "dropped_features": dropped_features,
            "coverage": {f: round(v, 4) for f, v in coverage.items()},
            "n_kill_test_fires_total": len(kt),
            "n_compounder": int((kt["label"] == "compounder").sum()),
            "n_tactical_only": int((kt["label"] == "tactical_only").sum()),
        }
    }

    # -------------------------------------------------------------------
    # Primary analysis — fit period (UPPER BOUND, exploration only)
    # -------------------------------------------------------------------
    if len(kt_fit) >= 10:
        log.info("Running FIT PERIOD analysis (UPPER BOUND)...")
        result_fit = run_analysis(
            kt_fit, retained_features,
            split_label="fit_2014-2019_UPPER_BOUND",
            survivorship_note=(
                "UPPER BOUND — survivor-only cohort. "
                "All pre-2021-07 fires have survivorship_biased=True. "
                "Estimated bias: 200-500 bps/yr overstatement in absolute returns. "
                "This split is exploration only; the G1 decision cell is OOS 2020-2023."
            ),
        )
        all_results["fit_primary"] = result_fit
        log.info("Fit period G1 status: %s", result_fit["g1_status"])

    if fit_only:
        log.info("FIT-ONLY mode: stopping before OOS analysis")
        _write_results(all_results, kt, retained_features, dropped_features, coverage)
        return

    # -------------------------------------------------------------------
    # Primary analysis — OOS honest cohort (G1 decision cell)
    # -------------------------------------------------------------------
    log.info("Running OOS HONEST COHORT analysis (G1 decision cell)...")
    result_oos_honest = run_analysis(
        kt_oos_honest, retained_features,
        split_label="oos_2020-2023_honest",
        survivorship_note=(
            "OOS honest cohort: survivorship_biased=False only. "
            "These fires have resolvable price paths from the Massive whole-market store "
            "or Yahoo, with dead-name coverage from Polygon REST (post-anchor era; "
            "ESTIMATED/UNVERIFIED — dead_name_probe_results.json self-describes as "
            "'PARTIALLY ESTIMATED — no raw probe script or sampled price bars were retained; "
            "~95% post-anchor coverage figure is an estimate, not a measured sample; "
            "treat as estimated/unverified pending a committed probe script with sampled bars'). "
            "This is the pre-registered G1 decision cell."
        ),
    )
    all_results["oos_honest_primary"] = result_oos_honest
    log.info("OOS honest G1 status: %s", result_oos_honest["g1_status"])

    # -------------------------------------------------------------------
    # Primary analysis — full OOS (all fires, survivorship-biased included)
    # -------------------------------------------------------------------
    log.info("Running OOS ALL FIRES analysis (survivorship-biased; for context)...")
    result_oos_all = run_analysis(
        kt_oos, retained_features,
        split_label="oos_2020-2023_all_SURVIVORSHIP_BIASED",
        survivorship_note=(
            "Full OOS 2020-2023 including survivorship-biased fires. "
            "Includes pre-anchor fires where dead names are missing → "
            "compounder label is over-represented (acquisitions look like compounders). "
            "This is NOT the G1 decision cell. Reported for context and direction-finding."
        ),
    )
    all_results["oos_all_biased"] = result_oos_all
    log.info("OOS all G1 status: %s", result_oos_all["g1_status"])

    # -------------------------------------------------------------------
    # Sensitivity 1: fund_unchecked exclusion (OBJECTIVE.md §2.4)
    # -------------------------------------------------------------------
    log.info("Running SENSITIVITY: fund_unchecked exclusion...")
    kt_oos_honest_no_fc = kt_oos_honest[
        ~kt_oos_honest.get("fund_unchecked", pd.Series([False] * len(kt_oos_honest), index=kt_oos_honest.index)).astype(bool)
    ].copy()
    result_oos_honest_no_fc = run_analysis(
        kt_oos_honest_no_fc, retained_features,
        split_label="oos_2020-2023_honest_fund_unchecked_excluded",
        survivorship_note=(
            "OOS honest cohort with fund_unchecked=True fires EXCLUDED "
            "(mandatory sensitivity per OBJECTIVE.md §2.4). "
            "fund_unchecked fires are compounders assigned without confirmed F-score>=6."
        ),
    )
    all_results["oos_honest_sensitivity_fund_unchecked"] = result_oos_honest_no_fc
    log.info(
        "Sensitivity fund_unchecked G1 status: %s",
        result_oos_honest_no_fc["g1_status"],
    )

    # -------------------------------------------------------------------
    # Sensitivity 2: Amendment A1 — market-benchmark reassignment
    # -------------------------------------------------------------------
    log.info("Running AMENDMENT A1 sensitivity...")
    labels_a1 = apply_amendment_a1(
        labels[labels["label"].isin(["compounder", "tactical_only",
                                      "sector_laggard_winner"])].copy(),
        labels,
    )
    # Rebuild the kill-test set from the A1-reassigned labels
    kt_a1_oos = labels_a1[
        (labels_a1["fire_date"] >= OOS_START) &
        (labels_a1["fire_date"] <= OOS_END) &
        labels_a1["label"].isin(["compounder", "tactical_only"])
    ].copy()

    if len(kt_a1_oos) > 0:
        # Merge features from primary analysis (features were computed on all kills + slw)
        # We need to re-join features for the A1 fires
        # The A1 dataset includes sector_laggard_winner fires converted to compounder/tactical
        # We need features for those tickers too
        primary_features_needed = retained_features + ["cohort_year", "macro_regime"]

        # Build features for A1 fires not in original kill-test
        a1_new_tickers = set(kt_a1_oos["ticker"].unique()) - set(kt["ticker"].unique())
        if a1_new_tickers:
            log.info("A1: computing features for %d new tickers (former SLW)", len(a1_new_tickers))

        # Use the feature panel built for the primary analysis; join by (ticker, fire_date)
        # For SLW fires now reclassified, features may be absent
        feature_cols = retained_features + ["cohort_year", "macro_regime", "survivorship_biased",
                                              "fund_unchecked", "piotroski_f"]
        existing_cols = [c for c in feature_cols if c in kt.columns]
        kt_features = kt[["ticker", "fire_date"] + existing_cols].copy()
        kt_features.set_index(["ticker", "fire_date"], inplace=True)

        kt_a1_oos["fire_date"] = pd.to_datetime(kt_a1_oos["fire_date"])
        kt_a1_oos_idx = kt_a1_oos.set_index(["ticker", "fire_date"])
        for col in existing_cols:
            if col not in kt_a1_oos_idx.columns:
                kt_a1_oos_idx[col] = kt_features[col].reindex(kt_a1_oos_idx.index)
        kt_a1_oos = kt_a1_oos_idx.reset_index()

        # Explicit == False (not ~astype(bool)) to avoid None→False coercion (should-fix)
        kt_a1_oos_honest = kt_a1_oos[kt_a1_oos["survivorship_biased"] == False].copy()  # noqa: E712

        result_a1_honest = run_analysis(
            kt_a1_oos_honest, retained_features,
            split_label="oos_2020-2023_honest_A1_market_benchmark",
            survivorship_note=(
                "Amendment A1: OOS honest cohort with market-benchmark reassignment "
                "of no-sector-benchmark fires. All null sector_rel_252d replaced with "
                "market_rel_252d (cohort-year EW mean approximation — see A1 spec). "
                "This is the pre-registered mandatory sensitivity run."
            ),
        )
        all_results["oos_honest_A1"] = result_a1_honest
        log.info("A1 honest G1 status: %s", result_a1_honest["g1_status"])

        n_a1_fires_new = int((kt_a1_oos["a1_applied"] == True).sum()) if "a1_applied" in kt_a1_oos.columns else 0
        all_results["a1_metadata"] = {
            "n_fires_reassigned": n_a1_fires_new,
            "n_oos_kills_after_a1": len(kt_a1_oos),
            "compounder_after_a1": int((kt_a1_oos["label"] == "compounder").sum()),
            "tactical_only_after_a1": int((kt_a1_oos["label"] == "tactical_only").sum()),
            "benchmark_approximation": (
                "cohort-year equal-weight mean of total_return_252d "
                "(approximation of full per-fire S(f) computation; documented in A1 spec)"
            ),
            "a1_survivorship_caveat": (
                "Pre-2021 cohorts: S(f) is survivor-upward-biased → market benchmark "
                "depressed → excess Label G assignment direction documented per A1 spec."
            ),
            "spec_infeasibility": (
                "SPEC-INFEASIBLE FROM LABELS PARQUET: the pre-registered S(f) constituent set "
                "(OBJECTIVE.md Amendment A1) requires every fire-tape ticker with a fully "
                "resolvable 252d forward path at the fire's own fire_date. The labels parquet "
                "has total_return_252d=null for all 34,604 tactical_only_fail fires and 65,723 "
                "unlabeled fires. The benchmark used here is computed ONLY from the ~13,215 "
                "tactical-win rows with non-null 252d returns — a winner-selected, upward-biased "
                "pool. The A1 SURVIVE verdict arises because the 128 no-benchmark SLW fires in "
                "the OOS honest window (all strong performers, total_return_252d 0.116-2.548) "
                "flip to compounder against this ~1.78% winner-pool mean (2021 cohort). "
                "A1 results are reported as APPROXIMATE SENSITIVITY ONLY — not as evidence on "
                "the pre-registered S(f). See apply_amendment_a1 docstring and §7 of results doc."
            ),
        }
    else:
        all_results["oos_honest_A1"] = {"g1_status": "DEFERRED_N_FLOOR", "note": "no A1 fires in OOS honest"}

    # -------------------------------------------------------------------
    # Routing table per Amendment A1 interpretation rules
    # -------------------------------------------------------------------
    primary_g1 = result_oos_honest["g1_status"]
    a1_g1 = all_results.get("oos_honest_A1", {}).get("g1_status", "DEFERRED_N_FLOOR")

    def _route(p: str, a: str) -> str:
        if p == "DEFERRED_N_FLOOR" or a == "DEFERRED_N_FLOOR":
            return "DEFERRED"
        if p == "KILL" and a == "KILL":
            return "AGREED_KILL"
        if p == "SURVIVE" and a == "SURVIVE":
            return "AGREED_SURVIVE"
        return "DISAGREE_REMEDIATION"

    combined_routing = _route(primary_g1, a1_g1)
    all_results["combined_routing"] = {
        "primary_g1_status": primary_g1,
        "a1_g1_status": a1_g1,
        "combined_outcome": combined_routing,
        "routing_rule": "OBJECTIVE.md Amendment A1 routing table",
    }

    log.info("Combined routing: %s", combined_routing)

    # -------------------------------------------------------------------
    # Write outputs
    # -------------------------------------------------------------------
    _write_results(all_results, kt, retained_features, dropped_features, coverage)


def _write_results(
    all_results: dict[str, Any],
    kt: pd.DataFrame,
    retained_features: list[str],
    dropped_features: list[str],
    coverage: dict[str, float],
) -> None:
    """Write parquet output and Markdown results document."""
    _OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    _OUT_MD.parent.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------
    # Build flat parquet (one row per feature per split)
    # -------------------------------------------------------------------
    rows = []
    for split_key, split_result in all_results.items():
        if not isinstance(split_result, dict):
            continue
        if "feature_results" not in split_result:
            continue
        split_label = split_result.get("split_label", split_key)
        n_clusters = split_result.get("n_clusters_total", 0)
        n_mh = split_result.get("n_missed_hold_clusters", 0)
        n_to = split_result.get("n_tactical_only_clusters", 0)
        floor_met = split_result.get("floor_met", False)
        g1_status = split_result.get("g1_status", "unknown")
        surv_note = split_result.get("survivorship_note", "")

        for fr in split_result["feature_results"]:
            row = {
                "split_label": split_label,
                "n_clusters_total": n_clusters,
                "n_missed_hold_clusters": n_mh,
                "n_tactical_only_clusters": n_to,
                "floor_met": floor_met,
                "g1_status": g1_status,
                "survivorship_note": surv_note,
                **fr,
            }
            rows.append(row)

    if rows:
        results_df = pd.DataFrame(rows)
        results_df.to_parquet(_OUT_PARQUET, index=False)
        log.info("Written: %s (%d rows)", _OUT_PARQUET, len(results_df))

    # -------------------------------------------------------------------
    # Write Markdown results document
    # -------------------------------------------------------------------
    md = _build_markdown(all_results, retained_features, dropped_features, coverage, kt)
    _OUT_MD.write_text(md, encoding="utf-8")
    log.info("Written: %s", _OUT_MD)


def _fmt_split_section(
    split_key: str,
    result: dict[str, Any],
) -> str:
    """Format one split's results as a Markdown section."""
    lines = []
    label = result.get("split_label", split_key)
    g1 = result.get("g1_status", "unknown")
    n_total = result.get("n_clusters_total", 0)
    n_mh = result.get("n_missed_hold_clusters", 0)
    n_to = result.get("n_tactical_only_clusters", 0)
    floor = result.get("floor_met", False)
    surv = result.get("survivorship_note", "")

    lines.append(f"### {label}")
    lines.append("")
    if surv:
        lines.append(f"**Survivorship stamp:** {surv}")
        lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Episode-cluster count | {n_total} |")
    lines.append(f"| missed_hold clusters | {n_mh} |")
    lines.append(f"| tactical_only clusters | {n_to} |")
    lines.append(f"| n-floor met (≥{EPISODE_FLOOR}) | {'YES' if floor else 'NO'} |")
    lines.append(f"| G1 status (this split) | **{g1}** |")
    lines.append("")

    if not floor:
        floor_note = result.get("floor_note", "n-floor not met")
        lines.append(f"> **REFUSED:** {floor_note}")
        lines.append("")
        return "\n".join(lines)

    feature_results = result.get("feature_results", [])
    bh_panel = result.get("bh_panel", [])
    bh_by_feat = {r["feature"]: r for r in bh_panel}

    lines.append("#### Per-feature results")
    lines.append("")
    lines.append(
        "| Feature | n MH covered | n TO covered | RBC | 95% CI | p-value | "
        "q-value (BH) | Rejected (BH) | Passes reshuffle null | Reshuffle null p90 |"
    )
    lines.append(
        "|---------|-------------|-------------|-----|--------|---------|"
        "------------|----------------|----------------------|-------------------|"
    )

    for fr in feature_results:
        feat = fr["feature"]
        status = fr.get("status", "unknown")
        if status in ("insufficient_data", "refused_floor_not_met", "insufficient_coverage"):
            lines.append(
                f"| {feat} | — | — | — | — | — | — | — | — | — |  _{status}_ |"
            )
            continue
        if status != "computed":
            continue
        n_mh_cov = fr.get("n_missed_hold_covered", "—")
        n_to_cov = fr.get("n_tactical_only_covered", "—")
        rbc = fr.get("rbc")
        ci_lo = fr.get("ci_lo")
        ci_hi = fr.get("ci_hi")
        pval = fr.get("p_value_raw")
        qval = fr.get("q_value_bh")
        rej = fr.get("rejected_bh_fdr")
        passes_r = fr.get("passes_reshuffle_null")
        null_p90 = fr.get("reshuffle_null_p90")

        def fmt(v: Any, dec: int = 4) -> str:
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return "—"
            return f"{v:.{dec}f}"

        ci_str = f"[{fmt(ci_lo)}, {fmt(ci_hi)}]" if ci_lo is not None and ci_hi is not None else "—"
        rej_str = "YES*" if rej else ("no" if rej is False else "—")
        passes_str = "YES*" if passes_r else ("no" if passes_r is False else "—")

        lines.append(
            f"| {feat} | {n_mh_cov} | {n_to_cov} | {fmt(rbc)} | {ci_str} | "
            f"{fmt(pval, 4)} | {fmt(qval, 4)} | {rej_str} | {passes_str} | {fmt(null_p90)} |"
        )

    lines.append("")
    g1_survivors = result.get("g1_survivors", [])
    if g1_survivors:
        lines.append(f"**G1 survivors (pass both BH-FDR and reshuffle null):** {', '.join(g1_survivors)}")
    else:
        lines.append("**G1 survivors:** none")
    lines.append("")
    return "\n".join(lines)


def _build_markdown(
    all_results: dict[str, Any],
    retained_features: list[str],
    dropped_features: list[str],
    coverage: dict[str, float],
    kt: pd.DataFrame,
) -> str:
    """Build the full W1_KILLTEST_RESULTS.md document."""
    lines = []
    lines.append("# Long-Hold Thesis Layer — W1 Kill-Test Results")
    lines.append("")
    lines.append("**Wave:** W1 PR-F")
    lines.append("**Pre-registration:** `research/long_hold/OBJECTIVE.md` (LOCKED, including Amendment A1)")
    lines.append("**FDR family:** `long_hold` (isolated per LH-R5)")
    lines.append("**Fable rulings:** LH-W1-1, LH-W1-2, LH-W1-3")
    lines.append("")
    lines.append(
        "> This document is produced by `scripts/research/missed_hold_study.py`. "
        "Results are printed as observed. The document does NOT declare the program's fate. "
        "See final section."
    )
    lines.append("")

    meta = all_results.get("study_metadata", {})

    # -------------------------------------------------------------------
    # Feature coverage table
    # -------------------------------------------------------------------
    lines.append("## 1. Feature Coverage (nine frozen features per OBJECTIVE.md §5)")
    lines.append("")
    lines.append("Coverage computed on the kill-test subset (compounder + tactical_only fires).")
    lines.append("Features with < 20% non-null coverage are dropped per §5 drop rule.")
    lines.append("")
    lines.append("| Feature | Coverage | Status | Notes |")
    lines.append("|---------|----------|--------|-------|")

    feature_notes = {
        "piotroski_f": "Computed by label harness; from fundamentals_panel raw rows",
        "quality_z": "ROA + CFO/assets composite; cross-sectional z-score",
        "profitability_z": "NI/assets + CFO/assets; cross-sectional z-score (same inputs as quality_z — note: op_income unavailable from panel)",
        "sue": "Standardized unexpected earnings: (ni - ni_prior) / assets_prior",
        "insider_cmp": "NOT COMPUTABLE from fundamentals_panel (no insider filing data)",
        "interest_coverage": "NOT COMPUTABLE from fundamentals_panel (interest_exp absent from panel)",
        "dilution_flag": "shares YoY > +3% threshold; from fundamentals_panel shares column",
        "gross_margin_trend": "3-year OLS slope of gross_profit/revenue; last 3 PIT rows",
        "archetype": "NOT PRE-COMPUTED in any parquet (no archetype field in fundamentals_panel)",
    }
    all_9 = meta.get("all_9_features", [])
    for feat in all_9:
        cov = coverage.get(feat, 0.0)
        if cov >= 0.20:
            status = "retained"
        elif feat in dropped_features:
            status = "DROPPED (< 20% coverage)"
        else:
            status = "unknown"
        note = feature_notes.get(feat, "")
        lines.append(f"| `{feat}` | {cov:.1%} | {status} | {note} |")
    lines.append("")

    lines.append(f"**Retained for analysis:** `{'`, `'.join(retained_features)}`")
    lines.append("")
    if dropped_features:
        lines.append(f"**Dropped (< 20% coverage or not computable):** `{'`, `'.join(dropped_features)}`")
        lines.append("")

    # -------------------------------------------------------------------
    # Kill-test population summary
    # -------------------------------------------------------------------
    lines.append("## 2. Kill-Test Population Summary")
    lines.append("")
    n_kt = meta.get("n_kill_test_fires_total", 0)
    n_comp = meta.get("n_compounder", 0)
    n_tact = meta.get("n_tactical_only", 0)
    lines.append(
        f"| Cohort | Fires | compounder | tactical_only |"
    )
    lines.append("|--------|-------|-----------|--------------|")
    lines.append(f"| All (2014-2026) | {n_kt} | {n_comp} | {n_tact} |")

    # OOS splits
    oos_h = all_results.get("oos_honest_primary", {})
    oos_a = all_results.get("oos_all_biased", {})
    fit_r = all_results.get("fit_primary", {})
    lines.append(f"| Fit 2014-2019 (UPPER BOUND) | — | {fit_r.get('n_missed_hold_clusters', '—')} dedup | {fit_r.get('n_tactical_only_clusters', '—')} dedup |")
    lines.append(f"| OOS 2020-2023 honest | {oos_h.get('n_clusters_total', '—')} | {oos_h.get('n_missed_hold_clusters', '—')} | {oos_h.get('n_tactical_only_clusters', '—')} |")
    lines.append(f"| OOS 2020-2023 all (biased) | {oos_a.get('n_clusters_total', '—')} | {oos_a.get('n_missed_hold_clusters', '—')} | {oos_a.get('n_tactical_only_clusters', '—')} |")
    lines.append("")

    # -------------------------------------------------------------------
    # Inference section header
    # -------------------------------------------------------------------
    lines.append("## 3. Inference Design")
    lines.append("")
    lines.append("Per OBJECTIVE.md §6 (frozen at registration):")
    lines.append("")
    lines.append("- **Test statistic:** Mann-Whitney rank-biserial correlation (RBC)")
    lines.append("- **BH-FDR:** q ≤ 0.10 across all retained features simultaneously (§6.1)")
    lines.append("- **CIs:** cluster-robust (ticker × macro_regime) + block-bootstrap; wider CI governs (§6.2)")
    lines.append("  - _Deviation from §6.2_: spec requires (ticker_SECTOR × macro_regime); implemented as (ticker × macro_regime) because the labels parquet has no sector-category column (only sector_rel_252d as a float). Ticker-level clustering is finer than sector-level and may produce slightly narrow CIs. The block-bootstrap fallback (which governs when wider) partially mitigates this.")
    lines.append("- **Episode-cluster floor:** n ≥ 25 independent (ticker × macro_regime) clusters per group (§6.3)")
    lines.append("  - _Deviation from §6.3_: spec says ±10 TRADING days; implemented as ±14 CALENDAR days (≈10 trading days). Impact on the DEFERRED verdict is nil (4 compounders regardless of dedup window).")
    lines.append("- **Reshuffle null:** 1,000 within-(cohort_year × macro_regime) permutations; 90th percentile threshold (§6.4); seed=42 (LOCKED in pre-registration)")
    lines.append("- **Bootstrap seeds:** block-bootstrap uses seed=43; cluster-bootstrap uses seed=44 (distinct from reshuffle seed=42 to avoid correlated draws across independent inference gates)")
    lines.append("- **G1 criterion:** a feature must clear ALL THREE gates (BH-FDR + reshuffle + n-floor) on the OOS honest cohort")
    lines.append("")

    # -------------------------------------------------------------------
    # Results sections
    # -------------------------------------------------------------------
    lines.append("## 4. Fit Period Results (2014-2019) — UPPER BOUND Explorer")
    lines.append("")
    lines.append(
        "> **UPPER BOUND — survivor-only.** "
        "Pre-2021-07 cohorts are survivorship-biased (estimated 200-500 bps/yr overstatement). "
        "These results are direction-finding ONLY. The G1 decision cell is §5 (OOS honest cohort)."
    )
    lines.append("")
    if "fit_primary" in all_results:
        lines.append(_fmt_split_section("fit_primary", all_results["fit_primary"]))
    else:
        lines.append("_(fit period analysis not run)_")
    lines.append("")

    lines.append("## 5. OOS Honest Cohort Results (2020-2023) — G1 Decision Cell")
    lines.append("")
    lines.append(
        "> **This is the pre-registered G1 decision cell.** "
        "Only fires with survivorship_biased=False are included. "
        "Per OBJECTIVE.md §8 pre-registration: if the OOS honest n-floor is not met, "
        "the G1 criterion cannot fire from honest data alone → routed to survivorship-deferral path."
    )
    lines.append("")
    if "oos_honest_primary" in all_results:
        lines.append(_fmt_split_section("oos_honest_primary", all_results["oos_honest_primary"]))
    lines.append("")

    lines.append("## 6. Sensitivity: fund_unchecked Excluded (Mandatory per §2.4)")
    lines.append("")
    lines.append(
        "Fires with `fund_unchecked=True` excluded from the contrast. "
        "Per §2.4: if primary and fund_unchecked-excluded results disagree in direction, "
        "primary is marked 'coverage-sensitive'."
    )
    lines.append("")
    if "oos_honest_sensitivity_fund_unchecked" in all_results:
        lines.append(_fmt_split_section(
            "oos_honest_sensitivity_fund_unchecked",
            all_results["oos_honest_sensitivity_fund_unchecked"],
        ))
    lines.append("")

    lines.append("## 7. Amendment A1: Market-Benchmark Reassignment")
    lines.append("")
    lines.append(
        "> **SPEC-INFEASIBILITY — A1 results are APPROXIMATE SENSITIVITY ONLY.**"
    )
    lines.append("> The pre-registered S(f) constituent set (OBJECTIVE.md Amendment A1) requires")
    lines.append("> \"every ticker in the fire tape whose 252d fill-anchored forward price path")
    lines.append("> is fully resolvable at that fire's own fire_date.\" This is NOT computable")
    lines.append("> from long_hold_labels.parquet alone: the parquet has total_return_252d=null")
    lines.append("> for all 34,604 tactical_only_fail fires and 65,723 unlabeled fires.")
    lines.append("> The benchmark below uses ONLY the ~13,215 tactical-win rows with non-null")
    lines.append("> 252d returns — a WINNER-SELECTED, UPWARD-BIASED pool that excludes all")
    lines.append("> fires that never achieved tactical liftoff.")
    lines.append(">")
    lines.append("> Consequence: the 2021 cohort-year benchmark is 0.0178 (1.78%), computed from")
    lines.append("> the winner pool. The 128 no-benchmark SLW fires in the OOS honest window")
    lines.append("> (all strong performers, total_return_252d ranging 0.116–2.548) flip to")
    lines.append("> compounder against this low bar, inflating the A1-honest compounder count")
    lines.append("> from 4 to 132 and producing the A1 SURVIVE result. The A1 SURVIVE verdict")
    lines.append("> **is NOT reported as evidence on the pre-registered S(f) specification.**")
    lines.append("> It is an approximate sensitivity result and is labelled as such.")
    lines.append("> The combined routing (§9) correctly gates on the primary DEFERRED verdict.")
    lines.append("")
    a1_meta = all_results.get("a1_metadata", {})
    lines.append(
        f"N fires reassigned from no-sector-benchmark: **{a1_meta.get('n_fires_reassigned', '—')}**  "
        f"| After A1: compounder={a1_meta.get('compounder_after_a1', '—')}, "
        f"tactical_only={a1_meta.get('tactical_only_after_a1', '—')}"
    )
    lines.append("")
    bm_approx = a1_meta.get("benchmark_approximation", "")
    if bm_approx:
        lines.append(f"> **Benchmark approximation (winner-selected pool):** {bm_approx}")
        lines.append("")
    surv_a1 = a1_meta.get("a1_survivorship_caveat", "")
    if surv_a1:
        lines.append(f"> **Survivorship caveat (A1):** {surv_a1}")
        lines.append("")
    if "oos_honest_A1" in all_results:
        lines.append(_fmt_split_section("oos_honest_A1", all_results["oos_honest_A1"]))
    lines.append("")

    lines.append("## 8. OOS All-Fires Context (Survivorship-Biased; NOT G1 Cell)")
    lines.append("")
    lines.append(
        "> **NOT the G1 decision cell.** Included for directional context only. "
        "Acquisition-premium bias in compounder label documented above."
    )
    lines.append("")
    if "oos_all_biased" in all_results:
        lines.append(_fmt_split_section("oos_all_biased", all_results["oos_all_biased"]))
    lines.append("")

    # -------------------------------------------------------------------
    # Routing table
    # -------------------------------------------------------------------
    lines.append("## 9. Combined Routing (Primary × A1 per Amendment A1 rules)")
    lines.append("")
    routing = all_results.get("combined_routing", {})
    p_stat = routing.get("primary_g1_status", "—")
    a1_stat = routing.get("a1_g1_status", "—")
    combined = routing.get("combined_outcome", "—")
    lines.append("| Leg | G1 status |")
    lines.append("|-----|-----------|")
    lines.append(f"| Primary (OOS honest) | {p_stat} |")
    lines.append(f"| A1 (market benchmark) | {a1_stat} |")
    lines.append(f"| **Combined** | **{combined}** |")
    lines.append("")
    lines.append(
        "Routing interpretation per Amendment A1 table: "
        "DEFERRED if either leg is DEFERRED_N_FLOOR; "
        "AGREED_KILL if both KILL; AGREED_SURVIVE if both SURVIVE; "
        "DISAGREE_REMEDIATION if one KILL and one SURVIVE (no deferral)."
    )
    lines.append("")
    lines.append(
        "> **Note on A1 SURVIVE:** the A1 SURVIVE result is computed on a non-spec benchmark "
        "(winner-selected cohort-year mean, not the pre-registered per-fire S(f)). "
        "Per §7 above, it is not reportable as evidence on the pre-registered specification. "
        "The combined routing is correctly DEFERRED (driven by the primary leg's DEFERRED_N_FLOOR). "
        "The A1 SURVIVE cell does not alter this routing and is not presented as a reprieve."
    )
    lines.append("")

    # -------------------------------------------------------------------
    # In-plain-English box
    # -------------------------------------------------------------------
    lines.append("## 10. In Plain English")
    lines.append("")
    lines.append("> **What this study measured:**")
    lines.append("> We asked one question: when a stock fires our entry signal and then becomes")
    lines.append("> a multi-year winner (what we call a 'compounder'), could we have known that")
    lines.append("> at the moment of the signal — before the stock moved — using quality metrics")
    lines.append("> we already track (Piotroski score, quality z-score, earnings surprise, etc.)?")
    lines.append("> The contrast is: compounders (multi-year winners from entry) vs tactical-only")
    lines.append("> fires (bounced and faded within a year).")
    lines.append(">")
    lines.append("> **What the data constraint means (LH-W1-3 verified forward-leg source):**")
    lines.append("> The honest test requires a survivorship-correct price source so that companies")
    lines.append("> that eventually failed or were delisted are represented. Dead-name forward legs")
    lines.append("> ARE present in the honest cell: data/edgar/dead_name_prices.parquet was built")
    lines.append("> from Polygon REST (415 tickers, continuous coverage 2021-07-06→2026-06-02,")
    lines.append("> source='polygon'). This covers the entire honest OOS window")
    lines.append("> (2021-07-06→2021-10-22); all 271 honest fires have gap_leg_crossed=False")
    lines.append("> and full 252d returns, confirming the Polygon dead-name build fills the gap.")
    lines.append("> COVERAGE CAVEAT: the ~95% post-anchor coverage figure from")
    lines.append("> dead_name_probe_results.json is ESTIMATED — no committed probe script with")
    lines.append("> sampled price bars was retained; treat coverage as estimated/unverified.")
    lines.append(">")
    lines.append("> **Why the test is deferred — window length, not missing dead names:**")
    lines.append("> The honest OOS window is approximately 3.5 months (2021-07-06→2021-10-22)")
    lines.append("> because the 1,165-day Massive store gap begins 2021-10-25. In that window,")
    lines.append("> only 4 compounder episode-clusters fired vs the required minimum of")
    lines.append(f"> {EPISODE_FLOOR}. The DEFERRED verdict is driven SOLELY by this window-length")
    lines.append("> constraint (too few compounders in 3.5 months), NOT by absent or")
    lines.append("> survivorship-biased forward legs. You cannot run a reliable statistical test")
    lines.append("> on 4 examples, regardless of how complete the price data is.")
    lines.append(">")
    lines.append("> **What this means for the program:**")
    lines.append("> We cannot answer the core question from honest data yet — the honest cohort")
    lines.append("> is too small because the fire window is only 3.5 months. The test can be")
    lines.append("> run on survivorship-biased data (the full OOS 2020-2023 set), but that")
    lines.append("> biases the result toward finding a false signal (companies acquired at a")
    lines.append("> premium look like 'compounders' when they just got bought out). The null")
    lines.append("> or positive result from biased data does not resolve the question.")
    lines.append(">")
    lines.append("> **What needs to happen next:**")
    lines.append("> The dead-name spike (PR-G) expands the dead-name price store to cover the")
    lines.append("> full 1,165-day gap period (2021-10-25→2025-01-02). Once that gap is filled,")
    lines.append("> post-gap fires (2025+) will mature to full 252d, creating a larger honest")
    lines.append("> cohort. The pre-registered deferral path in OBJECTIVE.md §8 is activated")
    lines.append("> because the n-floor was not met — not because dead-name prices are absent.")
    lines.append("")

    # -------------------------------------------------------------------
    # Registry note
    # -------------------------------------------------------------------
    lines.append("## 11. Registry and Firewall")
    lines.append("")
    lines.append("Results artifact: `data/research/missed_hold_study_results.parquet`")
    lines.append("Registered in `config/synapse.yml` with:")
    lines.append("- `horizon_role: hold_thesis`")
    lines.append("- `tier: display`")
    lines.append("- `scored_path_surfaces: []`")
    lines.append("- `fdr_family: long_hold` (isolated from entry-desk FDR batches per LH-R5)")
    lines.append("")
    lines.append(
        "**Firewall:** this artifact MUST NOT feed entry-stack z-scores, board ordering, "
        "top-setups gates, alert triage, or push floor. Wrong-ruler firewall per OBJECTIVE.md §9."
    )
    lines.append("")

    # -------------------------------------------------------------------
    # G1 ratification placeholder
    # -------------------------------------------------------------------
    lines.append("---")
    lines.append("")
    lines.append("**G1 ratification: PENDING FABLE RULING**")
    lines.append("")
    lines.append(
        "_This document prints the analysis results. It does not declare the program alive or dead. "
        "The G1 kill criterion requires Fable adjudication of the combined routing outcome above, "
        "including the survivorship-deferral path interpretation per OBJECTIVE.md §8._"
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="W1 Missed-Hold Kill-Test Study")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build feature panel only; skip inference")
    parser.add_argument("--fit-only", action="store_true",
                        help="Run fit period only; do not open OOS (exploration mode)")
    args = parser.parse_args()
    main(dry_run=args.dry_run, fit_only=args.fit_only)
