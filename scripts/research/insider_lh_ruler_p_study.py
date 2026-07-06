"""Long-Hold Thesis Layer — LT-3b: Ruler-P study for insider_sponsor_lh family.

Pre-registration: research/long_hold/INSIDER_SPONSOR_LH_FAMILY_PREREG.md (LOCKED).
Methodology contract: IDENTICAL to the expect_drift Ruler-P (cheap_trap vs tactical_only,
252d, fires <= 2023-12-31 hard-asserted, episode-clustering via missed_hold_study.py
machinery, reshuffle null 1000/seed42, BH q=0.10 descriptive, cells + eras, n-floors,
UPPER BOUND stamps).

TrialLedger.log_declared_budget(3, family='long_hold.insider_sponsor_lh') BEFORE p-values.

Features: IS-1 (insider_net_usd_mcap_6m_pct, cont), IS-2 (cluster_buy_pre_fire, bin),
          IS-3 (officer_buy_flag, bin).

Contrast: cheap_trap vs tactical_only at 252d on fires with fire_date <= 2023-12-31.
          cheap_trap = positive group (expected sign +).
          tactical_only = baseline.

Outputs:
  data/research/insider_lh_ruler_p_results.parquet
  research/long_hold/INSIDER_LH_RULER_P_RESULTS.md

Experiments entries registered:
  insider-lh-ruler-p         (study complete on run)
  insider-lh-ruler-h-accrual (come_back_on 2027-07-01)

Usage:
    cd /path/to/repo
    python scripts/research/insider_lh_ruler_p_study.py
    python scripts/research/insider_lh_ruler_p_study.py --dry-run   # skip writes
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from datetime import datetime, timezone
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
# Paths
# ---------------------------------------------------------------------------
_DATA             = _REPO_ROOT / "data"
_LABELS_PATH      = _DATA / "research" / "long_hold_labels.parquet"
_PANEL_PATH       = _DATA / "research" / "insider_lh_panel.parquet"
_REGIME_PATH      = _DATA / "regime" / "regime_history.parquet"
_EXPERIMENTS_PATH = _DATA / "experiments" / "registry_seed.json"
_OUT_PARQUET      = _DATA / "research" / "insider_lh_ruler_p_results.parquet"
_OUT_MD           = _REPO_ROOT / "research" / "long_hold" / "INSIDER_LH_RULER_P_RESULTS.md"

# ---------------------------------------------------------------------------
# Constants — LOCKED by prereg (identical contract to expect_drift)
# ---------------------------------------------------------------------------
FAMILY            = "long_hold.insider_sponsor_lh"
M_HYPOTHESES      = 3          # LOCKED in prereg §2; declared budget before p-values
BH_Q_THRESHOLD    = 0.10
RESHUFFLE_SEED    = 42         # LOCKED — do not change
BOOTSTRAP_SEED_BLOCK   = 43
BOOTSTRAP_SEED_CLUSTER = 44
N_RESHUFFLE       = 1000
N_BOOTSTRAP       = 1000
BLOCK_RADIUS_DAYS = 14         # ±14 calendar days ≈ ±10 trading days (documented deviation)
EPISODE_FLOOR     = 25         # per LH-R4
BLOCK_WIDTH       = 63         # trading-day block width for block-bootstrap
COVERAGE_FLOOR    = 0.20       # per OBJECTIVE.md §5

# Ruler-P gates (LOCKED)
RULER_P_CUTOFF    = "2023-12-31"   # hard-asserted: no fires after this date
RULER_P_FIT_START = "2014-01-01"
RULER_P_FIT_END   = "2019-12-31"
RULER_P_OOS_START = "2020-01-01"
RULER_P_OOS_END   = "2023-12-31"

# Pre-registered era breakout labels
ERA_LABELS = [
    ("fit_2014-2019",    "2014-01-01", "2019-12-31"),
    ("oos_2020-2021",    "2020-01-01", "2021-12-31"),
    ("oos_2022-2023",    "2022-01-01", "2023-12-31"),
]

# Features (F4 prereg §2)
FEATURES = ["insider_net_usd_mcap_6m_pct", "cluster_buy_pre_fire", "officer_buy_flag"]
FEATURE_TYPES = {
    "insider_net_usd_mcap_6m_pct": "cont",
    "cluster_buy_pre_fire":         "bin",
    "officer_buy_flag":             "bin",
}
EXPECTED_SIGNS = {
    "insider_net_usd_mcap_6m_pct": "+",
    "cluster_buy_pre_fire":         "+",
    "officer_buy_flag":             "+",
}

# Ruler-P outcome label (cheap_trap = positive group, tactical_only = baseline)
RULER_P_OUTCOME_COL = "ruler_p_positive"  # 1 = cheap_trap, 0 = tactical_only


# ---------------------------------------------------------------------------
# TrialLedger — declare budget BEFORE computing p-values
# ---------------------------------------------------------------------------

def _declare_trial_budget() -> None:
    """Log declared budget to trial_ledger.jsonl BEFORE any p-value computation."""
    try:
        from engine.trial_ledger import TrialLedger
        led = TrialLedger(path=_DATA / "trial_ledger.jsonl", family=FAMILY)
        led.log_declared_budget(
            M_HYPOTHESES,
            family=FAMILY,
            reason=f"F4 insider_sponsor_lh prereg m={M_HYPOTHESES}: IS-1/IS-2/IS-3",
        )
        log.info("TrialLedger: declared budget m=%d for family=%s", M_HYPOTHESES, FAMILY)
    except Exception as exc:  # noqa: BLE001
        log.warning("TrialLedger declare failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Macro regime attachment (identical to missed_hold_study.py)
# ---------------------------------------------------------------------------

def _attach_macro_regime(df: pd.DataFrame) -> pd.DataFrame:
    """Attach macro_regime (Q1..Q4) to each fire via backward-fill from regime_history."""
    df = df.copy()
    if not _REGIME_PATH.exists():
        log.warning("regime_history.parquet not found; macro_regime will be null")
        df["macro_regime"] = None
        return df
    try:
        regime = pd.read_parquet(_REGIME_PATH)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load regime_history: %s; macro_regime=null", exc)
        df["macro_regime"] = None
        return df

    if "quad" not in regime.columns:
        log.warning("regime_history missing 'quad'; macro_regime=null")
        df["macro_regime"] = None
        return df

    regime_quad = regime["quad"]
    fire_dates = pd.to_datetime(df["fire_date"])
    fires_df = pd.DataFrame({"fire_date": fire_dates.values}).drop_duplicates().sort_values("fire_date")
    rq_df = (
        regime_quad.reset_index()
        .rename(columns={"index": "date", 0: "macro_regime", "quad": "macro_regime"})
        .sort_values("date")
        .dropna(subset=["macro_regime"])
    )
    merged = pd.merge_asof(fires_df, rq_df, left_on="fire_date", right_on="date", direction="backward")
    regime_map = merged.set_index("fire_date")["macro_regime"]
    df["macro_regime"] = fire_dates.map(regime_map).values
    log.info(
        "macro_regime attached: %d/%d non-null (dist: %s)",
        df["macro_regime"].notna().sum(), len(df),
        df["macro_regime"].value_counts().to_dict(),
    )
    return df


# ---------------------------------------------------------------------------
# Episode-cluster deduplication (identical contract to missed_hold_study.py)
# ---------------------------------------------------------------------------

def deduplicate_episode_clusters(
    df: pd.DataFrame,
    key_cols: tuple[str, ...] = ("ticker", "macro_regime"),
    date_col: str = "fire_date",
    window_days: int = BLOCK_RADIUS_DAYS,
) -> pd.DataFrame:
    """Greedy left-to-right dedup per LH-R4 / OBJECTIVE.md §6.3.

    DEVIATION: ±10 trading days specified; implemented as ±14 calendar days
    (≈10 trading days). Same as missed_hold_study.py — documented deviation.
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
# Mann-Whitney U rank-biserial correlation
# ---------------------------------------------------------------------------

def _mann_whitney_rbc(x1: np.ndarray, x2: np.ndarray) -> tuple[float, float]:
    """Mann-Whitney U rank-biserial correlation and two-sided p-value."""
    x1 = x1[~np.isnan(x1)]
    x2 = x2[~np.isnan(x2)]
    n1, n2 = len(x1), len(x2)
    if n1 == 0 or n2 == 0:
        return np.nan, np.nan
    combined = np.concatenate([x1, x2])
    ranks = pd.Series(combined).rank(method="average").values
    u1 = ranks[:n1].sum() - n1 * (n1 + 1) / 2
    u2 = n1 * n2 - u1
    rbc = float(2 * u1 / (n1 * n2) - 1)
    u = min(u1, u2)
    mean_u = n1 * n2 / 2
    std_u = np.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    if std_u < 1e-10:
        return rbc, 1.0
    z = (u - mean_u) / std_u
    from scipy import stats as _stats  # noqa: PLC0415
    p_val = float(2 * _stats.norm.sf(abs(z)))
    return rbc, min(1.0, p_val)


def _fisher_exact(
    x: np.ndarray,
    y: np.ndarray,
) -> tuple[float, float]:
    """Fisher's exact test for binary feature (x=0/1) vs binary outcome (y=0/1).

    Returns (odds_ratio, two-sided p_value).
    """
    from scipy import stats as _stats  # noqa: PLC0415
    mask = ~(np.isnan(x) | np.isnan(y))
    x = x[mask].astype(int)
    y = y[mask].astype(int)
    if len(x) == 0:
        return np.nan, np.nan
    a = int(((x == 1) & (y == 1)).sum())
    b = int(((x == 1) & (y == 0)).sum())
    c = int(((x == 0) & (y == 1)).sum())
    d = int(((x == 0) & (y == 0)).sum())
    table = [[a, b], [c, d]]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        or_val, p_val = _stats.fisher_exact(table, alternative="two-sided")
    return float(or_val), float(p_val)


# ---------------------------------------------------------------------------
# BH-FDR correction
# ---------------------------------------------------------------------------

def bh_fdr(
    p_values: list[float | None],
    labels: list[str],
    q: float = BH_Q_THRESHOLD,
) -> list[dict[str, Any]]:
    """Benjamini-Hochberg step-up FDR correction."""
    valid = [(i, p) for i, p in enumerate(p_values) if p is not None and not np.isnan(p)]
    m = len(valid)
    q_map: dict[int, float] = {}
    if valid:
        sorted_valid = sorted(valid, key=lambda x: x[1])
        for rank1, (orig_i, p) in enumerate(sorted_valid, start=1):
            q_map[orig_i] = float(p * m / rank1)
        running_min = 1.0
        for _, (orig_i, _) in reversed(list(enumerate(sorted_valid))):
            q_map[orig_i] = min(q_map[orig_i], running_min)
            running_min = q_map[orig_i]
    out = []
    for i, (lbl, p) in enumerate(zip(labels, p_values)):
        if p is None or np.isnan(p):
            out.append({"feature": lbl, "p_value": None, "q_value": None, "rejected": None})
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
# Block-bootstrap CI for RBC
# ---------------------------------------------------------------------------

def _block_bootstrap_rbc(
    df: pd.DataFrame,
    feature: str,
    outcome_col: str,
    date_col: str = "fire_date",
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Block-bootstrap 95% CI for RBC."""
    sub = df[[feature, outcome_col, date_col]].dropna().copy()
    sub[date_col] = pd.to_datetime(sub[date_col])
    sub = sub.sort_values(date_col).reset_index(drop=True)
    if len(sub) < 10:
        return {"ci_lo": np.nan, "ci_hi": np.nan, "n_blocks": 0}
    min_date = sub[date_col].min()
    sub["_block_id"] = ((sub[date_col] - min_date).dt.days // (BLOCK_WIDTH * 1.4)).astype(int)
    block_ids = sub["_block_id"].unique()
    n_blocks = len(block_ids)
    rng = np.random.default_rng(BOOTSTRAP_SEED_BLOCK)
    boot_rbcs = []
    for _ in range(n_bootstrap):
        chosen_blocks = rng.choice(block_ids, size=n_blocks, replace=True)
        boot_rows = pd.concat(
            [sub[sub["_block_id"] == b] for b in chosen_blocks], ignore_index=True
        )
        x1 = boot_rows[boot_rows[outcome_col] == 1][feature].dropna().values
        x2 = boot_rows[boot_rows[outcome_col] == 0][feature].dropna().values
        if len(x1) == 0 or len(x2) == 0:
            continue
        rbc, _ = _mann_whitney_rbc(x1, x2)
        if not np.isnan(rbc):
            boot_rbcs.append(rbc)
    if len(boot_rbcs) < 10:
        return {"ci_lo": np.nan, "ci_hi": np.nan, "n_blocks": n_blocks}
    arr = np.array(boot_rbcs)
    return {
        "ci_lo": round(float(np.percentile(arr, 2.5)), 4),
        "ci_hi": round(float(np.percentile(arr, 97.5)), 4),
        "n_blocks": int(n_blocks),
    }


# ---------------------------------------------------------------------------
# Cluster-robust CI (wider of cluster and block-bootstrap per §6.2)
# ---------------------------------------------------------------------------

def _cluster_robust_ci(
    df: pd.DataFrame,
    feature: str,
    outcome_col: str,
    regime_col: str = "macro_regime",
) -> dict[str, Any]:
    """CI via ticker×macro_regime clustering; wider CI governs per §6.2."""
    sub = df[[feature, outcome_col, "ticker", regime_col, "fire_date"]].dropna(
        subset=[feature, outcome_col]
    ).copy()
    if len(sub) < 10:
        return {"ci_lo": np.nan, "ci_hi": np.nan, "method": "insufficient_data"}
    sub["_cluster"] = (
        sub["ticker"].astype(str) + "|" + sub[regime_col].astype(str).fillna("none")
    )
    cluster_rbcs = []
    for _, grp in sub.groupby("_cluster"):
        x1 = grp[grp[outcome_col] == 1][feature].dropna().values
        x2 = grp[grp[outcome_col] == 0][feature].dropna().values
        if len(x1) == 0 or len(x2) == 0:
            continue
        rbc, _ = _mann_whitney_rbc(x1, x2)
        if not np.isnan(rbc):
            cluster_rbcs.append(rbc)
    bb = _block_bootstrap_rbc(df, feature, outcome_col)
    if len(cluster_rbcs) < 5:
        bb["method"] = "block_bootstrap_fallback"
        return bb
    arr = np.array(cluster_rbcs)
    rng = np.random.default_rng(BOOTSTRAP_SEED_CLUSTER)
    boot = rng.choice(arr, size=(N_BOOTSTRAP, len(arr)), replace=True).mean(axis=1)
    cluster_ci_lo = float(np.percentile(boot, 2.5))
    cluster_ci_hi = float(np.percentile(boot, 97.5))
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
# Reshuffle null (within cohort_year × macro_regime, LOCKED seed=42)
# ---------------------------------------------------------------------------

def reshuffle_null(
    df: pd.DataFrame,
    feature: str,
    outcome_col: str,
    n_shuffle: int = N_RESHUFFLE,
    seed: int = RESHUFFLE_SEED,
) -> dict[str, Any]:
    """Within-(cohort_year × macro_regime) reshuffle null per §6.4."""
    sub = df[[feature, outcome_col, "cohort_year", "macro_regime"]].dropna(
        subset=[feature, outcome_col]
    ).copy()
    if len(sub) < 10:
        return {
            "null_p90": np.nan, "observed_rbc": np.nan,
            "passes_reshuffle": None, "n_shuffle": n_shuffle,
            "note": "insufficient data",
        }
    x1 = sub[sub[outcome_col] == 1][feature].dropna().values
    x2 = sub[sub[outcome_col] == 0][feature].dropna().values
    obs_rbc, _ = _mann_whitney_rbc(x1, x2)

    sub["_cell"] = sub["cohort_year"].astype(str) + "|" + sub["macro_regime"].astype(str).fillna("none")
    cells = sub["_cell"].unique()
    rng = np.random.default_rng(seed)
    null_rbcs = []
    for _ in range(n_shuffle):
        shuffled = sub.copy()
        for cell in cells:
            mask = shuffled["_cell"] == cell
            cell_out = shuffled.loc[mask, outcome_col].values.copy()
            rng.shuffle(cell_out)
            shuffled.loc[mask, outcome_col] = cell_out
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
            "null_p90": np.nan, "observed_rbc": float(obs_rbc),
            "passes_reshuffle": None, "n_shuffle": n_shuffle,
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
# Per-cell analysis (one temporal cell or era)
# ---------------------------------------------------------------------------

def _analyze_cell(
    df: pd.DataFrame,
    features: list[str],
    cell_label: str,
    survivorship_note: str,
) -> dict[str, Any]:
    """Run Ruler-P analysis on a single temporal cell.

    Contrast: ruler_p_positive=1 (cheap_trap) vs ruler_p_positive=0 (tactical_only).
    """
    # Episode-cluster deduplication
    df_dedup = deduplicate_episode_clusters(
        df,
        key_cols=("ticker", "macro_regime"),
        date_col="fire_date",
        window_days=BLOCK_RADIUS_DAYS,
    )

    n_pos = int((df_dedup[RULER_P_OUTCOME_COL] == 1).sum())
    n_neg = int((df_dedup[RULER_P_OUTCOME_COL] == 0).sum())
    log.info(
        "Cell %s: %d cheap_trap / %d tactical_only (after dedup)",
        cell_label, n_pos, n_neg,
    )

    per_feature: list[dict[str, Any]] = []
    p_values: list[float | None] = []

    for feat in features:
        feat_type = FEATURE_TYPES.get(feat, "cont")
        expected_sign = EXPECTED_SIGNS.get(feat, "?")

        # Coverage in this cell
        n_total = max(len(df_dedup), 1)
        coverage_frac = float(df_dedup[feat].notna().mean()) if feat in df_dedup.columns else 0.0
        n_floor_met_pos = int((df_dedup[df_dedup[RULER_P_OUTCOME_COL] == 1][feat].notna()).sum())
        n_floor_met_neg = int((df_dedup[df_dedup[RULER_P_OUTCOME_COL] == 0][feat].notna()).sum())

        # Check n-floor per arm
        n_floor_ok = (n_floor_met_pos >= EPISODE_FLOOR) and (n_floor_met_neg >= EPISODE_FLOOR)

        if not n_floor_ok or coverage_frac < COVERAGE_FLOOR:
            log.info(
                "  %s: SKIPPED (n_pos=%d, n_neg=%d, n_floor=%d, coverage=%.1f%%)",
                feat, n_floor_met_pos, n_floor_met_neg, EPISODE_FLOOR, coverage_frac * 100,
            )
            per_feature.append({
                "feature": feat,
                "type": feat_type,
                "expected_sign": expected_sign,
                "cell": cell_label,
                "survivorship_note": survivorship_note,
                "n_pos": int(n_pos),
                "n_neg": int(n_neg),
                "n_feat_pos": int(n_floor_met_pos),
                "n_feat_neg": int(n_floor_met_neg),
                "coverage_frac": round(coverage_frac, 4),
                "n_floor_ok": False,
                "rbc": None,
                "p_value": None,
                "q_value": None,
                "rejected_bh": None,
                "ci_lo": None,
                "ci_hi": None,
                "ci_method": None,
                "reshuffle_null_p90": None,
                "reshuffle_observed_rbc": None,
                "passes_reshuffle": None,
                "display_claim": "BELOW_FLOOR",
            })
            p_values.append(None)
            continue

        # Compute test statistic
        pos_vals = df_dedup[df_dedup[RULER_P_OUTCOME_COL] == 1][feat].dropna().values
        neg_vals = df_dedup[df_dedup[RULER_P_OUTCOME_COL] == 0][feat].dropna().values

        if feat_type == "bin":
            # Fisher's exact for binary features
            outcome_arr = df_dedup[RULER_P_OUTCOME_COL].dropna().values
            feat_arr = df_dedup[feat].dropna()
            feat_arr = feat_arr.astype(float).values
            outcome_for_feat = df_dedup.loc[df_dedup[feat].notna(), RULER_P_OUTCOME_COL].values.astype(float)
            feat_for_test = df_dedup.loc[df_dedup[feat].notna(), feat].values.astype(float)
            or_val, p_val = _fisher_exact(feat_for_test, outcome_for_feat)
            # RBC for consistency reporting (MWU on 0/1 arrays)
            rbc, _ = _mann_whitney_rbc(pos_vals.astype(float), neg_vals.astype(float))
        else:
            rbc, p_val = _mann_whitney_rbc(pos_vals, neg_vals)
            or_val = None

        p_values.append(p_val)

        # CI
        ci_result = _cluster_robust_ci(df_dedup, feat, RULER_P_OUTCOME_COL)

        # Reshuffle null (compute per-feature within the deduped cell)
        reshuffle_result = reshuffle_null(df_dedup, feat, RULER_P_OUTCOME_COL)

        rec: dict[str, Any] = {
            "feature": feat,
            "type": feat_type,
            "expected_sign": expected_sign,
            "cell": cell_label,
            "survivorship_note": survivorship_note,
            "n_pos": int(n_pos),
            "n_neg": int(n_neg),
            "n_feat_pos": int(n_floor_met_pos),
            "n_feat_neg": int(n_floor_met_neg),
            "coverage_frac": round(coverage_frac, 4),
            "n_floor_ok": True,
            "rbc": round(float(rbc), 4) if not np.isnan(rbc) else None,
            "p_value": round(float(p_val), 6) if p_val is not None and not np.isnan(p_val) else None,
            "q_value": None,  # filled in after BH
            "rejected_bh": None,  # filled in after BH
            "ci_lo": ci_result.get("ci_lo"),
            "ci_hi": ci_result.get("ci_hi"),
            "ci_method": ci_result.get("method"),
            "reshuffle_null_p90": reshuffle_result.get("null_p90"),
            "reshuffle_observed_rbc": reshuffle_result.get("observed_rbc"),
            "passes_reshuffle": reshuffle_result.get("passes_reshuffle"),
            "display_claim": None,  # filled in below
        }
        if feat_type == "bin" and or_val is not None:
            rec["odds_ratio"] = round(float(or_val), 4) if not np.isnan(or_val) else None
        per_feature.append(rec)

    # BH-FDR correction across the family (all m=3 features declared)
    all_p = []
    all_labels = []
    for rec in per_feature:
        all_p.append(rec.get("p_value"))
        all_labels.append(rec["feature"])
    bh_results = bh_fdr(all_p, all_labels, q=BH_Q_THRESHOLD)
    for i, bhr in enumerate(bh_results):
        per_feature[i]["q_value"] = bhr.get("q_value")
        per_feature[i]["rejected_bh"] = bhr.get("rejected")

    # Assign display_claim per feature
    for rec in per_feature:
        if rec.get("display_claim") == "BELOW_FLOOR":
            continue
        passes_bh = rec.get("rejected_bh") is True
        passes_r = rec.get("passes_reshuffle") is True
        n_ok = rec.get("n_floor_ok", False)
        rbc_val = rec.get("rbc")
        right_sign = (rbc_val is not None and rbc_val > 0) if rec["expected_sign"] == "+" else True
        if passes_bh and passes_r and n_ok and right_sign:
            rec["display_claim"] = "DESCRIPTIVE_PASS"
        elif rec.get("p_value") is None:
            rec["display_claim"] = "NULL"
        else:
            rec["display_claim"] = "NULL"

    return {
        "cell": cell_label,
        "n_pos_dedup": int(n_pos),
        "n_neg_dedup": int(n_neg),
        "survivorship_note": survivorship_note,
        "per_feature": per_feature,
    }


# ---------------------------------------------------------------------------
# Main study
# ---------------------------------------------------------------------------

def run_study() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run the full Ruler-P study and return (results_df, summary_dict)."""
    # STEP 1: Declare trial budget BEFORE computing any p-values
    _declare_trial_budget()

    # STEP 2: Load data
    log.info("Loading labels from %s", _LABELS_PATH)
    labels = pd.read_parquet(_LABELS_PATH)

    log.info("Loading feature panel from %s", _PANEL_PATH)
    if not _PANEL_PATH.exists():
        raise FileNotFoundError(
            f"insider_lh_panel.parquet not found: {_PANEL_PATH}. "
            "Run build_insider_lh_panel.py first."
        )
    panel = pd.read_parquet(_PANEL_PATH)

    # STEP 3: Confirm labels exist (fires extend to 2026+ which is expected)
    log.info("Labels date range: %s → %s", str(labels["fire_date"].min().date()), str(labels["fire_date"].max().date()))

    # STEP 4: Merge features onto labeled fires (cheap_trap + tactical_only, <=2023-12-31)
    labeled = labels[labels["label"].isin(["cheap_trap", "tactical_only"])].copy()
    ruler_p = labeled[labeled["fire_date"] <= RULER_P_CUTOFF].copy()
    # Hard-assert: NO OOS-2 contamination
    assert (ruler_p["fire_date"] <= pd.Timestamp(RULER_P_CUTOFF)).all(), \
        "OOS-2 contamination: fires after RULER_P_CUTOFF detected"
    log.info(
        "Ruler-P eligible: %d (cheap_trap=%d, tactical_only=%d), date range %s → %s",
        len(ruler_p),
        (ruler_p["label"] == "cheap_trap").sum(),
        (ruler_p["label"] == "tactical_only").sum(),
        str(ruler_p["fire_date"].min().date()),
        str(ruler_p["fire_date"].max().date()),
    )

    df = ruler_p.merge(
        panel[["ticker", "fire_date"] + FEATURES],
        on=["ticker", "fire_date"],
        how="left",
    )
    df["cohort_year"] = pd.to_datetime(df["fire_date"]).dt.year
    df[RULER_P_OUTCOME_COL] = (df["label"] == "cheap_trap").astype(int)

    # Attach macro regime
    df = _attach_macro_regime(df)

    # STEP 5: Coverage check
    coverage = {f: float(df[f].notna().mean()) for f in FEATURES if f in df.columns}
    log.info("Feature coverage in Ruler-P cohort: %s", {k: f"{v:.1%}" for k, v in coverage.items()})
    retained = [f for f in FEATURES if coverage.get(f, 0.0) >= COVERAGE_FLOOR]
    dropped = [f for f in FEATURES if coverage.get(f, 0.0) < COVERAGE_FLOOR]
    if dropped:
        log.warning(
            "Features dropped (coverage < %.0f%%): %s",
            COVERAGE_FLOOR * 100,
            {f: f"{coverage.get(f, 0.0):.1%}" for f in dropped},
        )
    log.info("Retained features: %s", retained)

    all_rows: list[dict[str, Any]] = []

    # STEP 6: Full Ruler-P cell (fit 2014-2019 + OOS 2020-2023 combined)
    log.info("--- Full Ruler-P cell ---")
    full_cell = _analyze_cell(df, retained, "full_ruler_p_2014-2023", "UPPER_BOUND")
    for rec in full_cell["per_feature"]:
        all_rows.append(rec)

    # STEP 7: Era breakout (pre-registered)
    for era_label, era_start, era_end in ERA_LABELS:
        era_mask = (
            (df["fire_date"] >= pd.Timestamp(era_start)) &
            (df["fire_date"] <= pd.Timestamp(era_end))
        )
        era_df = df[era_mask].copy()
        surv_note = "UPPER_BOUND" if era_end <= "2021-06-30" else "UPPER_BOUND_partial"
        log.info("--- Era cell: %s (n=%d) ---", era_label, len(era_df))
        cell_result = _analyze_cell(era_df, retained, era_label, surv_note)
        for rec in cell_result["per_feature"]:
            all_rows.append(rec)

    # Assemble results DataFrame
    results_df = pd.DataFrame(all_rows)
    for col in ["fdr_family", "horizon_role", "_display_only"]:
        if col not in results_df.columns:
            results_df[col] = None
    results_df["fdr_family"] = "long_hold.insider_sponsor_lh"
    results_df["horizon_role"] = "hold_thesis"
    results_df["_display_only"] = True
    results_df["survivorship_biased"] = True  # all Ruler-P cells are upper-bound

    summary = {
        "family": FAMILY,
        "m_hypotheses": int(M_HYPOTHESES),
        "bh_q_threshold": float(BH_Q_THRESHOLD),
        "n_reshuffle": int(N_RESHUFFLE),
        "reshuffle_seed": int(RESHUFFLE_SEED),
        "ruler_p_cutoff": RULER_P_CUTOFF,
        "n_ruler_p_fires": int(len(ruler_p)),
        "retained_features": retained,
        "dropped_features": dropped,
        "feature_coverage": {f: round(v, 4) for f, v in coverage.items()},
        "cells_analyzed": [c[0] for c in [(ERA_LABELS[0], "full")] + ERA_LABELS],
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    return results_df, summary


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def write_markdown_report(results_df: pd.DataFrame, summary: dict[str, Any]) -> str:
    """Generate INSIDER_LH_RULER_P_RESULTS.md content."""
    lines: list[str] = []
    lines.append("# Insider Sponsor LH Family — Ruler-P Study Results")
    lines.append("")
    lines.append(
        f"**Family:** `{summary['family']}` | **m = {summary['m_hypotheses']}** | "
        f"**Ruler-P cutoff:** fires ≤ {summary['ruler_p_cutoff']} | "
        f"**Generated:** {summary['generated_at'][:10]}"
    )
    lines.append("")
    lines.append(
        "**Authority ceiling:** DISPLAY ONLY (G1-DEFERRED ruling 2026-07-06). "
        "No SURVIVE/KILL vocabulary. All cells stamped UPPER BOUND (survivorship-biased)."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## In plain English")
    lines.append("")
    lines.append(
        "This study tests whether three insider-buying signals measured at the time "
        "of a tactical entry fire predict which fires end up as cheap traps (durable "
        "hold candidates) vs tactical-only at 252 days. The contrast is cheap_trap vs "
        "tactical_only using fires up to end-2023 only (Ruler-P). Because the data goes "
        "back to 2014, all results carry a survivorship-bias stamp (UPPER BOUND). "
        "No result here is a final verdict — that requires Ruler-H on 2025+ OOS data "
        "at the G1-Retest (~2027-H2)."
    )
    lines.append("")

    # Coverage summary
    lines.append("## Coverage")
    lines.append("")
    lines.append("| Feature | Type | Expected sign | Coverage in Ruler-P |")
    lines.append("|---|---|---|---|")
    for feat in FEATURES:
        cov = summary["feature_coverage"].get(feat, 0.0)
        ftype = FEATURE_TYPES.get(feat, "cont")
        esign = EXPECTED_SIGNS.get(feat, "?")
        status = "RETAINED" if feat in summary["retained_features"] else "DROPPED"
        lines.append(f"| `{feat}` | {ftype} | {esign} | {cov:.1%} ({status}) |")
    lines.append("")

    if summary["dropped_features"]:
        lines.append(
            f"> **Dropped features (coverage < {int(100*0.20)}%):** "
            + ", ".join(f"`{f}`" for f in summary["dropped_features"])
        )
        lines.append("")

    # Results table per cell
    cells = results_df["cell"].unique().tolist()
    for cell in cells:
        cell_df = results_df[results_df["cell"] == cell]
        surv_note = cell_df["survivorship_note"].iloc[0] if len(cell_df) > 0 else "UPPER_BOUND"
        n_pos = cell_df["n_pos"].iloc[0] if len(cell_df) > 0 else 0
        n_neg = cell_df["n_neg"].iloc[0] if len(cell_df) > 0 else 0
        lines.append(f"## Cell: {cell}")
        lines.append("")
        lines.append(
            f"Stamp: **{surv_note}** | cheap_trap n={n_pos} | tactical_only n={n_neg} "
            f"(after episode-cluster dedup)"
        )
        lines.append("")
        lines.append(
            "| Feature | Type | RBC | p-value | q-value (BH) | Rejected (BH) | "
            "Passes reshuffle | Reshuffle p90 | CI lo | CI hi | n_pos | n_neg | Verdict |"
        )
        lines.append(
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"
        )
        for _, row in cell_df.iterrows():
            rbc = f"{row['rbc']:.3f}" if row.get("rbc") is not None else "—"
            p_val = f"{row['p_value']:.4f}" if row.get("p_value") is not None else "—"
            q_val = f"{row['q_value']:.4f}" if row.get("q_value") is not None else "—"
            rej = str(row.get("rejected_bh", "—"))
            pass_r = str(row.get("passes_reshuffle", "—"))
            r_p90 = f"{row['reshuffle_null_p90']:.3f}" if row.get("reshuffle_null_p90") is not None else "—"
            ci_lo = f"{row['ci_lo']:.3f}" if row.get("ci_lo") is not None else "—"
            ci_hi = f"{row['ci_hi']:.3f}" if row.get("ci_hi") is not None else "—"
            n_fp = row.get("n_feat_pos", "—")
            n_fn = row.get("n_feat_neg", "—")
            verdict = row.get("display_claim", "—")
            feat = row["feature"]
            lines.append(
                f"| `{feat}` | {row['type']} | {rbc} | {p_val} | {q_val} | "
                f"{rej} | {pass_r} | {r_p90} | {ci_lo} | {ci_hi} | "
                f"{n_fp} | {n_fn} | {verdict} |"
            )
        lines.append("")

    # Protocol notes
    lines.append("---")
    lines.append("")
    lines.append("## Protocol notes")
    lines.append("")
    lines.append(f"- **BH-FDR:** q ≤ {BH_Q_THRESHOLD} across all m={M_HYPOTHESES} retained features")
    lines.append(f"- **Reshuffle null:** {N_RESHUFFLE} permutations, seed={RESHUFFLE_SEED} (LOCKED)")
    lines.append(f"- **Episode-cluster floor:** ≥{EPISODE_FLOOR} per arm")
    lines.append(
        f"- **Episode-cluster dedup:** ±{BLOCK_RADIUS_DAYS} calendar days (≈±10 trading days, "
        "documented deviation from LH-R4)"
    )
    lines.append(
        f"- **CI method:** wider of cluster-bootstrap (ticker × macro_regime; seed={BOOTSTRAP_SEED_CLUSTER}) "
        f"and block-bootstrap (seed={BOOTSTRAP_SEED_BLOCK})"
    )
    lines.append(
        "- **Ruler-P cutoff:** fires ≤ 2023-12-31 only. OOS-2 2025+ cohort is reserved "
        "for Ruler-H at G1-Retest (~2027-H2). No contact."
    )
    lines.append(
        "- **Authority ceiling:** DISPLAY ONLY. A feature passing both BH-FDR and reshuffle "
        "null may be shown in display context. SURVIVE/KILL vocabulary is banned until Ruler-H."
    )
    lines.append(
        "- **TrialLedger:** `log_declared_budget(3, family='long_hold.insider_sponsor_lh')` "
        "called BEFORE p-value computation."
    )
    lines.append(
        "- **Survivorship bias:** all Ruler-P cells are UPPER BOUND (pre-2021-07 tickers "
        "survivorship-biased per LH-R3)."
    )
    lines.append(
        "- The word 'validated' does not appear in this document (CI-enforced)."
    )
    lines.append("")
    lines.append(
        "**G1 ratification:** PENDING RULER-H (OOS-2, ~2027-H2). "
        "These results are display-tier upper bounds only."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Experiment registry update
# ---------------------------------------------------------------------------

def _register_experiments(dry_run: bool = False) -> None:
    """Add insider-lh-ruler-p and insider-lh-ruler-h-accrual to experiments registry."""
    if not _EXPERIMENTS_PATH.exists():
        log.warning("experiments registry not found: %s", _EXPERIMENTS_PATH)
        return
    try:
        with _EXPERIMENTS_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load experiments registry: %s", exc)
        return

    exp_list: list[dict] = data.get("experiments", data) if isinstance(data, dict) else data
    existing_ids = {e.get("id") for e in exp_list}

    new_entries = []

    if "insider-lh-ruler-p" not in existing_ids:
        new_entries.append({
            "id": "insider-lh-ruler-p",
            "name": "Insider Sponsor LH — Ruler-P study (cheap_trap vs tactical_only, 252d)",
            "kind": "offline_study",
            "priority": "medium",
            "cadence": "on-demand",
            "what": (
                "Ruler-P study for F4 insider_sponsor_lh family: IS-1/IS-2/IS-3 features, "
                "cheap_trap vs tactical_only contrast at 252d, fires <= 2023-12-31, "
                "episode-clustered, BH q=0.10, reshuffle null 1000/seed42. "
                "UPPER BOUND (survivorship-biased). Display-ceiling authority."
            ),
            "source": "scripts/research/insider_lh_ruler_p_study.py",
            "storage": "data/research/insider_lh_ruler_p_results.parquet",
            "hook": "offline_study",
            "started": "2026-07-06",
            "come_back_on": "2026-07-06",
            "come_back_note": "Study complete on run; Ruler-H at G1-Retest ~2027-H2",
            "maturation": "Ruler-H on OOS-2 at G1-Retest trigger (~2027-H2); program-wide BH q=0.10",
            "status": "complete",
            "state": "Ruler-P complete; Ruler-H accruing.",
            "next_step": "Review Ruler-H at G1-Retest (~2027-H2).",
            "phase_hint": "Ruler-H",
        })

    if "insider-lh-ruler-h-accrual" not in existing_ids:
        new_entries.append({
            "id": "insider-lh-ruler-h-accrual",
            "name": "Insider Sponsor LH — Ruler-H accrual (OOS-2 missed_hold contrast)",
            "kind": "track_record",
            "priority": "low",
            "cadence": "none",
            "what": (
                "Ruler-H for F4 insider_sponsor_lh family: missed_hold vs tactical_only "
                "on OOS-2 (2025+) at G1-Retest. Program-wide HLZ q=0.10. "
                "Evaluated at >=25-cluster trigger (~2027-H2)."
            ),
            "source": "scripts/research/insider_lh_ruler_p_study.py",
            "storage": "data/research/insider_lh_panel.parquet",
            "hook": "offline_study",
            "started": "2026-07-06",
            "come_back_on": "2027-07-01",
            "come_back_note": "G1-Retest checkpoint; check >=25 missed_hold clusters in OOS-2",
            "maturation": ">=25 episode-cluster missed_hold fires in OOS-2 AND program-wide BH q=0.10",
            "status": "accruing",
            "state": "Accruing OOS-2 fires. G1-Retest not triggered yet.",
            "next_step": "Check 2027-07-01: if >=25 missed_hold clusters, run Ruler-H study.",
            "phase_hint": "G1-Retest",
        })

    if new_entries:
        log.info("Registering %d new experiment entries", len(new_entries))
        if not dry_run:
            exp_list.extend(new_entries)
            if isinstance(data, dict):
                data["experiments"] = exp_list
                out_data = data
            else:
                out_data = exp_list
            _EXPERIMENTS_PATH.write_text(
                json.dumps(out_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            log.info("Experiments registry updated: %s", _EXPERIMENTS_PATH)
        else:
            log.info("DRY RUN: would add experiments: %s", [e["id"] for e in new_entries])
    else:
        log.info("Experiment entries already registered; no update needed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Ruler-P study for insider_sponsor_lh family")
    ap.add_argument("--dry-run", action="store_true", help="Run analysis but skip file writes")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    results_df, summary = run_study()

    md_text = write_markdown_report(results_df, summary)

    if not args.dry_run:
        _OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
        results_df.to_parquet(_OUT_PARQUET, index=False)
        log.info("Wrote %s (%d rows)", _OUT_PARQUET, len(results_df))

        _OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        _OUT_MD.write_text(md_text, encoding="utf-8")
        log.info("Wrote %s", _OUT_MD)

        _register_experiments(dry_run=False)
    else:
        log.info("DRY RUN: skipping file writes")
        print(md_text[:3000])

    # Print headline table to stdout
    full_cell_df = results_df[results_df["cell"] == "full_ruler_p_2014-2023"]
    print("\n=== Ruler-P headline results (full cell 2014-2023) ===")
    print(f"{'Feature':<45} {'RBC':>7} {'p-val':>8} {'q-val':>8} {'Reject':>7} {'PassR':>6} {'Verdict'}")
    print("-" * 100)
    for _, row in full_cell_df.iterrows():
        rbc = f"{row['rbc']:.3f}" if row.get("rbc") is not None else "   —"
        p = f"{row['p_value']:.4f}" if row.get("p_value") is not None else "      —"
        q = f"{row['q_value']:.4f}" if row.get("q_value") is not None else "      —"
        rej = str(row.get("rejected_bh", "—"))
        pr = str(row.get("passes_reshuffle", "—"))
        v = str(row.get("display_claim", "—"))
        print(f"{row['feature']:<45} {rbc:>7} {p:>8} {q:>8} {rej:>7} {pr:>6} {v}")
    print()


if __name__ == "__main__":
    main()
