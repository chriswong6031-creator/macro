"""Long-Hold Thesis Layer — LT-2b: Ruler-P study for expect_drift family.

Pre-registration: research/long_hold/EXPECT_DRIFT_FAMILY_PREREG.md §3 (LOCKED).
Masterplan ref: research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md LH-R14.

Contrast: cheap_trap vs tactical_only at 252d, fires with fire_date <= 2023-12-31 only.
Hard assertion in code: 2024+ fires MUST NEVER enter any feature-outcome join
(AMENDMENT_A2_G1_RETEST.md §4).

Features from data/research/expect_drift_panel.parquet (7 hypotheses ED-1..ED-7):
  Outcome coding: ruler_p_positive=1 means cheap_trap (bad outcome), 0 means tactical_only.
  Mechanism: higher feature → likelier to *avoid* cheap_trap → feature is LOWER in cheap_trap
  arm → expected RBC is NEGATIVE (sign '-').  Prereg §2 specifies '+' relative to the
  compounder-favorable outcome; because this ruler codes the opposite (cheap_trap=1), the
  sign flips to '-' here.

  ED-1  sue_latest          cont  -  MWU/RBC
  ED-2  sue_streak          int   -  MWU/RBC
  ED-3  pead_drift          cont  -  MWU/RBC
  ED-4  bad_news_absorption bin   -  Fisher
  ED-5  good_news_hold      bin   -  Fisher
  ED-6  sue_accel           cont  -  MWU/RBC
  ED-7  confirmed_absorption bin  -  Fisher

Methodology (reuses machinery from scripts/research/missed_hold_study.py):
  - episode-clustering: name × macro_regime ±14 calendar-day dedup
  - Mann-Whitney U + rank-biserial for cont features (ED-1/2/3/6)
  - Fisher exact for bin features (ED-4/5/7)
  - within-regime label-reshuffle null 1,000 permutations seed=42 (LOCKED)
  - BH q=0.10 within-family DESCRIPTIVE (per LH-R11.2 — not ratifying)
  - temporal cells: fit 2014-2019 / OOS-biased 2020-2023
  - era breakout: 2014-2019 / 2020-2021 / 2022-2023
  - n-floor >= 25 episode-clusters per arm per cell (print SKIPPED cells)
  - survivorship stamps "UPPER BOUND" on every cell

TrialLedger: log_declared_budget(7, family='long_hold.expect_drift') BEFORE p-values.
Cast numpy scalars to native Python before any json write.

Outputs:
  data/research/expect_drift_ruler_p_results.parquet
  research/long_hold/EXPECT_DRIFT_RULER_P_RESULTS.md

Experiments entries:
  expect-drift-ruler-p         (study complete on run)
  expect-drift-ruler-h-accrual (come_back_on 2027-07-01)

Usage:
    python scripts/research/expect_drift_ruler_p_study.py
    python scripts/research/expect_drift_ruler_p_study.py --dry-run
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
_PANEL_PATH       = _DATA / "research" / "expect_drift_panel.parquet"
_REGIME_PATH      = _DATA / "regime" / "regime_history.parquet"
_EXPERIMENTS_PATH = _DATA / "experiments" / "registry_seed.json"
_OUT_PARQUET      = _DATA / "research" / "expect_drift_ruler_p_results.parquet"
_OUT_MD           = _REPO_ROOT / "research" / "long_hold" / "EXPECT_DRIFT_RULER_P_RESULTS.md"

# ---------------------------------------------------------------------------
# Constants — LOCKED by prereg §3 (EXPECT_DRIFT_FAMILY_PREREG.md)
# ---------------------------------------------------------------------------
FAMILY            = "long_hold.expect_drift"
M_HYPOTHESES      = 7          # LOCKED in prereg §2; declared budget before p-values
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

# Ruler-P gates (LOCKED by prereg §3)
RULER_P_CUTOFF    = "2023-12-31"   # hard-asserted: no fires after this date
RULER_P_FIT_START = "2014-01-01"
RULER_P_FIT_END   = "2019-12-31"
RULER_P_OOS_START = "2020-01-01"
RULER_P_OOS_END   = "2023-12-31"

# Pre-registered era breakout labels (EXPECT_DRIFT_FAMILY_PREREG.md §3)
ERA_LABELS = [
    ("fit_2014-2019",    "2014-01-01", "2019-12-31"),
    ("oos_2020-2021",    "2020-01-01", "2021-12-31"),
    ("oos_2022-2023",    "2022-01-01", "2023-12-31"),
]

# Features (prereg §2; ED-1..ED-7)
FEATURES = [
    "sue_latest",           # ED-1 cont
    "sue_streak",           # ED-2 cont (integer counts)
    "pead_drift",           # ED-3 cont
    "bad_news_absorption",  # ED-4 bin
    "good_news_hold",       # ED-5 bin
    "sue_accel",            # ED-6 cont
    "confirmed_absorption", # ED-7 bin
]
FEATURE_TYPES = {
    "sue_latest":           "cont",
    "sue_streak":           "cont",
    "pead_drift":           "cont",
    "bad_news_absorption":  "bin",
    "good_news_hold":       "bin",
    "sue_accel":            "cont",
    "confirmed_absorption": "bin",
}
EXPECTED_SIGNS = {
    # NB: outcome is coded cheap_trap=1, tactical_only=0 (see RULER_P_OUTCOME_COL below).
    # The mechanism predicts higher feature values AVOID cheap_trap, so mechanism-consistent
    # features are LOWER in the cheap_trap arm → expected RBC is NEGATIVE.
    # A '+' sign here would require the feature to be *higher* among cheap_traps, which is
    # the wrong direction.  All seven are '-'.
    "sue_latest":           "-",
    "sue_streak":           "-",
    "pead_drift":           "-",
    "bad_news_absorption":  "-",
    "good_news_hold":       "-",
    "sue_accel":            "-",
    "confirmed_absorption": "-",
}

# Ruler-P outcome label: cheap_trap = positive group, tactical_only = baseline
RULER_P_OUTCOME_COL = "ruler_p_positive"   # 1 = cheap_trap, 0 = tactical_only


# ---------------------------------------------------------------------------
# TrialLedger — declare budget BEFORE computing p-values (CI gate)
# ---------------------------------------------------------------------------

def _declare_trial_budget() -> None:
    """Log declared budget to trial_ledger.jsonl BEFORE any p-value computation."""
    try:
        from engine.trial_ledger import TrialLedger  # noqa: PLC0415
        led = TrialLedger(path=_DATA / "trial_ledger.jsonl", family=FAMILY)
        led.log_declared_budget(
            M_HYPOTHESES,
            family=FAMILY,
            reason=f"F3 expect_drift prereg m={M_HYPOTHESES}: ED-1/2/3/4/5/6/7",
        )
        log.info("TrialLedger: declared budget m=%d for family=%s", M_HYPOTHESES, FAMILY)
    except Exception as exc:  # noqa: BLE001
        log.warning("TrialLedger declare failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Macro regime attachment
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
    fires_df = (
        pd.DataFrame({"fire_date": fire_dates.values})
        .drop_duplicates()
        .sort_values("fire_date")
    )
    rq_df = (
        regime_quad.reset_index()
        .rename(columns={"index": "date", 0: "macro_regime", "quad": "macro_regime"})
        .sort_values("date")
        .dropna(subset=["macro_regime"])
    )
    merged = pd.merge_asof(
        fires_df, rq_df, left_on="fire_date", right_on="date", direction="backward"
    )
    regime_map = merged.set_index("fire_date")["macro_regime"]
    df["macro_regime"] = fire_dates.map(regime_map).values
    log.info(
        "macro_regime attached: %d/%d non-null (dist: %s)",
        df["macro_regime"].notna().sum(),
        len(df),
        df["macro_regime"].value_counts().to_dict(),
    )
    return df


# ---------------------------------------------------------------------------
# Episode-cluster deduplication (LH-R4 / OBJECTIVE.md §6.3)
# ---------------------------------------------------------------------------

def deduplicate_episode_clusters(
    df: pd.DataFrame,
    key_cols: tuple[str, ...] = ("ticker", "macro_regime"),
    date_col: str = "fire_date",
    window_days: int = BLOCK_RADIUS_DAYS,
) -> pd.DataFrame:
    """Greedy left-to-right dedup per LH-R4.

    DEVIATION: ±10 trading days specified; implemented as ±14 calendar days
    (≈10 trading days). Identical contract to missed_hold_study.py and
    insider_lh_ruler_p_study.py.
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
# Mann-Whitney U rank-biserial correlation (ED-1/2/3/6)
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


# ---------------------------------------------------------------------------
# Fisher's exact test (ED-4/5/7 binary features)
# ---------------------------------------------------------------------------

def _fisher_exact(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Fisher's exact test for binary feature x vs binary outcome y.

    Returns (odds_ratio, two-sided p_value).
    x = feature values (0/1/None), y = outcome values (0/1).
    """
    from scipy import stats as _stats  # noqa: PLC0415
    # Drop NaN from both arrays (aligned)
    mask = ~(np.isnan(x.astype(float)) | np.isnan(y.astype(float)))
    xi = x[mask].astype(int)
    yi = y[mask].astype(int)
    if len(xi) == 0:
        return np.nan, np.nan
    a = int(((xi == 1) & (yi == 1)).sum())
    b = int(((xi == 1) & (yi == 0)).sum())
    c = int(((xi == 0) & (yi == 1)).sum())
    d = int(((xi == 0) & (yi == 0)).sum())
    table = [[a, b], [c, d]]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        or_val, p_val = _stats.fisher_exact(table, alternative="two-sided")
    return float(or_val), float(p_val)


# ---------------------------------------------------------------------------
# BH-FDR correction (descriptive, per LH-R11.2)
# ---------------------------------------------------------------------------

def bh_fdr(
    p_values: list[float | None],
    labels: list[str],
    q: float = BH_Q_THRESHOLD,
) -> list[dict[str, Any]]:
    """Benjamini-Hochberg step-up FDR correction.

    Per LH-R11.2: within-family q is DESCRIPTIVE, not ratifying.
    None p-values retained in output with rejected=None.
    """
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
        if p is None or (isinstance(p, float) and np.isnan(p)):
            out.append({"feature": lbl, "p_value": None, "q_value": None, "rejected": None})
        else:
            qv = q_map[i]
            out.append({
                "feature": lbl,
                "p_value": round(float(p), 6),
                "q_value": round(float(qv), 6),
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
    """Block-bootstrap 95% CI for RBC of continuous feature."""
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
        return {"ci_lo": np.nan, "ci_hi": np.nan, "n_blocks": int(n_blocks)}
    arr = np.array(boot_rbcs)
    return {
        "ci_lo": round(float(np.percentile(arr, 2.5)), 4),
        "ci_hi": round(float(np.percentile(arr, 97.5)), 4),
        "n_blocks": int(n_blocks),
    }


# ---------------------------------------------------------------------------
# Cluster-robust CI (wider of cluster and block-bootstrap, per §6.2)
# ---------------------------------------------------------------------------

def _cluster_robust_ci(
    df: pd.DataFrame,
    feature: str,
    outcome_col: str,
    regime_col: str = "macro_regime",
) -> dict[str, Any]:
    """CI via ticker × macro_regime clustering; wider CI governs per §6.2."""
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
        rbc, _ = _mann_whitney_rbc(x1.astype(float), x2.astype(float))
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
    ci_lo = min(cluster_ci_lo, float(bb.get("ci_lo", cluster_ci_lo) or cluster_ci_lo))
    ci_hi = max(cluster_ci_hi, float(bb.get("ci_hi", cluster_ci_hi) or cluster_ci_hi))
    return {
        "ci_lo": round(ci_lo, 4),
        "ci_hi": round(ci_hi, 4),
        "method": "cluster_wider",
        "cluster_ci_lo": round(cluster_ci_lo, 4),
        "cluster_ci_hi": round(cluster_ci_hi, 4),
        "block_bootstrap_ci_lo": round(float(bb.get("ci_lo", np.nan)), 4),
        "block_bootstrap_ci_hi": round(float(bb.get("ci_hi", np.nan)), 4),
    }


# ---------------------------------------------------------------------------
# Within-regime reshuffle null (1,000 permutations, seed=42 LOCKED)
# ---------------------------------------------------------------------------

def reshuffle_null(
    df: pd.DataFrame,
    feature: str,
    outcome_col: str,
    n_shuffle: int = N_RESHUFFLE,
    seed: int = RESHUFFLE_SEED,
    expected_sign: str = "+",
) -> dict[str, Any]:
    """Within-(cohort_year × macro_regime) reshuffle null per §6.4 of OBJECTIVE.md.

    expected_sign controls the tail used for the one-sided pass gate:
      '+' → obs_rbc must exceed null p90 (feature higher in group-1)
      '-' → obs_rbc must be below null p10 (feature lower in group-1)
    When outcome is coded cheap_trap=1 and mechanism predicts avoidance, all
    features use '-'.
    """
    sub = df[[feature, outcome_col, "cohort_year", "macro_regime"]].dropna(
        subset=[feature, outcome_col]
    ).copy()
    if len(sub) < 10:
        return {
            "null_p90": np.nan, "null_p10": np.nan, "observed_rbc": np.nan,
            "passes_reshuffle": None, "n_shuffle": n_shuffle,
            "note": "insufficient data",
        }
    x1 = sub[sub[outcome_col] == 1][feature].dropna().values.astype(float)
    x2 = sub[sub[outcome_col] == 0][feature].dropna().values.astype(float)
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
        mh_s = shuffled[shuffled[outcome_col] == 1][feature].dropna().values.astype(float)
        to_s = shuffled[shuffled[outcome_col] == 0][feature].dropna().values.astype(float)
        if len(mh_s) == 0 or len(to_s) == 0:
            null_rbcs.append(0.0)
            continue
        rbc_s, _ = _mann_whitney_rbc(mh_s, to_s)
        if not np.isnan(rbc_s):
            null_rbcs.append(rbc_s)

    if len(null_rbcs) < 10:
        return {
            "null_p90": np.nan, "null_p10": np.nan, "observed_rbc": float(obs_rbc),
            "passes_reshuffle": None, "n_shuffle": n_shuffle,
            "note": "null distribution degenerate",
        }
    null_arr = np.array(null_rbcs)
    p90 = float(np.percentile(null_arr, 90))
    p10 = float(np.percentile(null_arr, 10))
    if expected_sign == "-":
        passes = bool(not np.isnan(obs_rbc) and obs_rbc < p10)
    else:
        passes = bool(not np.isnan(obs_rbc) and obs_rbc > p90)
    return {
        "null_p90": round(p90, 4),
        "null_p10": round(p10, 4),
        "observed_rbc": round(float(obs_rbc), 4),
        "passes_reshuffle": passes,
        "n_shuffle": int(n_shuffle),
    }


# ---------------------------------------------------------------------------
# Per-cell analysis (one temporal cell or era)
# ---------------------------------------------------------------------------

def _coerce_binary_col(series: pd.Series) -> pd.Series:
    """Coerce object-typed binary column (True/False/None) to float (1.0/0.0/NaN)."""
    def _conv(v: Any) -> float:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return np.nan
        try:
            return float(bool(v))
        except (TypeError, ValueError):
            return np.nan
    return series.apply(_conv)


def _analyze_cell(
    df: pd.DataFrame,
    features: list[str],
    cell_label: str,
    survivorship_note: str,
) -> dict[str, Any]:
    """Run Ruler-P analysis on a single temporal cell.

    Contrast: ruler_p_positive=1 (cheap_trap) vs ruler_p_positive=0 (tactical_only).
    n-floor >= 25 per arm. Skipped cells are printed with reason.
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

        if feat not in df_dedup.columns:
            log.info("  %s: SKIPPED (feature not in panel)", feat)
            per_feature.append(_skipped_record(feat, feat_type, expected_sign, cell_label,
                                                survivorship_note, n_pos, n_neg,
                                                0, 0, 0.0, "FEATURE_ABSENT"))
            p_values.append(None)
            continue

        # Coerce binary columns to float for numpy ops
        col = df_dedup[feat]
        if feat_type == "bin":
            col_float = _coerce_binary_col(col)
        else:
            col_float = pd.to_numeric(col, errors="coerce")

        coverage_frac = float(col_float.notna().mean())

        # Count coverage per arm (before dedup already done)
        n_feat_pos = int((df_dedup[RULER_P_OUTCOME_COL] == 1)[col_float.notna()].sum())
        n_feat_neg = int((df_dedup[RULER_P_OUTCOME_COL] == 0)[col_float.notna()].sum())

        # n-floor: >= 25 episode-clusters per arm WITH non-null feature
        n_floor_ok = (n_feat_pos >= EPISODE_FLOOR) and (n_feat_neg >= EPISODE_FLOOR)

        if not n_floor_ok:
            log.info(
                "  %s: SKIPPED (n_feat_pos=%d, n_feat_neg=%d, floor=%d)",
                feat, n_feat_pos, n_feat_neg, EPISODE_FLOOR,
            )
            per_feature.append(_skipped_record(feat, feat_type, expected_sign, cell_label,
                                                survivorship_note, n_pos, n_neg,
                                                n_feat_pos, n_feat_neg, coverage_frac,
                                                "BELOW_FLOOR"))
            p_values.append(None)
            continue

        if coverage_frac < COVERAGE_FLOOR:
            log.info(
                "  %s: SKIPPED (coverage=%.1f%% < %.0f%%)",
                feat, coverage_frac * 100, COVERAGE_FLOOR * 100,
            )
            per_feature.append(_skipped_record(feat, feat_type, expected_sign, cell_label,
                                                survivorship_note, n_pos, n_neg,
                                                n_feat_pos, n_feat_neg, coverage_frac,
                                                "BELOW_COVERAGE"))
            p_values.append(None)
            continue

        # Assign aligned float column back to a temp copy for test
        df_tmp = df_dedup.copy()
        df_tmp[feat] = col_float.values

        pos_vals = df_tmp[df_tmp[RULER_P_OUTCOME_COL] == 1][feat].dropna().values.astype(float)
        neg_vals = df_tmp[df_tmp[RULER_P_OUTCOME_COL] == 0][feat].dropna().values.astype(float)

        or_val: float | None = None
        if feat_type == "bin":
            # Fisher's exact for binary features (ED-4/5/7)
            outcome_arr = df_tmp.loc[df_tmp[feat].notna(), RULER_P_OUTCOME_COL].values.astype(float)
            feat_arr = df_tmp.loc[df_tmp[feat].notna(), feat].values.astype(float)
            or_val, p_val = _fisher_exact(feat_arr, outcome_arr)
            # Also compute RBC for consistency reporting
            rbc, _ = _mann_whitney_rbc(pos_vals, neg_vals)
        else:
            # Mann-Whitney U for continuous features (ED-1/2/3/6)
            rbc, p_val = _mann_whitney_rbc(pos_vals, neg_vals)

        p_values.append(p_val)

        # CI (cluster-robust, wider governs per §6.2)
        ci_result = _cluster_robust_ci(df_tmp, feat, RULER_P_OUTCOME_COL)

        # Reshuffle null (within cohort_year × macro_regime, seed=42 LOCKED)
        # Pass expected_sign so the one-sided tail matches the mechanism direction.
        reshuffle_result = reshuffle_null(
            df_tmp, feat, RULER_P_OUTCOME_COL, expected_sign=expected_sign
        )

        rec: dict[str, Any] = {
            "feature": feat,
            "feature_id": f"ED-{FEATURES.index(feat) + 1}",
            "type": feat_type,
            "expected_sign": expected_sign,
            "cell": cell_label,
            "survivorship_note": survivorship_note,
            "n_pos": int(n_pos),
            "n_neg": int(n_neg),
            "n_feat_pos": int(n_feat_pos),
            "n_feat_neg": int(n_feat_neg),
            "coverage_frac": round(coverage_frac, 4),
            "n_floor_ok": True,
            "rbc": round(float(rbc), 4) if not np.isnan(rbc) else None,
            "p_value": round(float(p_val), 6) if p_val is not None and not np.isnan(p_val) else None,
            "q_value": None,      # filled after BH
            "rejected_bh": None,  # filled after BH
            "ci_lo": ci_result.get("ci_lo"),
            "ci_hi": ci_result.get("ci_hi"),
            "ci_method": ci_result.get("method"),
            "reshuffle_null_p90": reshuffle_result.get("null_p90"),
            "reshuffle_null_p10": reshuffle_result.get("null_p10"),
            "reshuffle_observed_rbc": reshuffle_result.get("observed_rbc"),
            "passes_reshuffle": reshuffle_result.get("passes_reshuffle"),
            "display_claim": None,  # filled after BH
            "fdr_family": FAMILY,
            "horizon_role": "hold_thesis",
            "_display_only": True,
            "survivorship_biased": True,
        }
        if feat_type == "bin" and or_val is not None:
            rec["odds_ratio"] = round(float(or_val), 4) if not np.isnan(or_val) else None
        per_feature.append(rec)

    # BH-FDR correction across the full family (all m=7 registered hypotheses)
    all_p = [rec.get("p_value") for rec in per_feature]
    all_labels = [rec["feature"] for rec in per_feature]
    bh_results = bh_fdr(all_p, all_labels, q=BH_Q_THRESHOLD)
    for i, bhr in enumerate(bh_results):
        per_feature[i]["q_value"] = bhr.get("q_value")
        per_feature[i]["rejected_bh"] = bhr.get("rejected")

    # Assign display_claim per feature
    for rec in per_feature:
        if rec.get("display_claim") in ("BELOW_FLOOR", "BELOW_COVERAGE", "FEATURE_ABSENT"):
            continue
        passes_bh = rec.get("rejected_bh") is True
        passes_r = rec.get("passes_reshuffle") is True
        n_ok = rec.get("n_floor_ok", False)
        rbc_val = rec.get("rbc")
        right_sign = (rbc_val is not None and rbc_val < 0) if rec["expected_sign"] == "-" else (
            rbc_val is not None and rbc_val > 0
        ) if rec["expected_sign"] == "+" else True
        if passes_bh and passes_r and n_ok and right_sign:
            rec["display_claim"] = "DESCRIPTIVE_PASS"
        else:
            rec["display_claim"] = "NULL"

    return {
        "cell": cell_label,
        "n_pos_dedup": int(n_pos),
        "n_neg_dedup": int(n_neg),
        "survivorship_note": survivorship_note,
        "per_feature": per_feature,
    }


def _skipped_record(
    feat: str,
    feat_type: str,
    expected_sign: str,
    cell_label: str,
    survivorship_note: str,
    n_pos: int,
    n_neg: int,
    n_feat_pos: int,
    n_feat_neg: int,
    coverage_frac: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "feature": feat,
        "feature_id": f"ED-{FEATURES.index(feat) + 1}",
        "type": feat_type,
        "expected_sign": expected_sign,
        "cell": cell_label,
        "survivorship_note": survivorship_note,
        "n_pos": int(n_pos),
        "n_neg": int(n_neg),
        "n_feat_pos": int(n_feat_pos),
        "n_feat_neg": int(n_feat_neg),
        "coverage_frac": round(float(coverage_frac), 4),
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
        "display_claim": reason,
        "fdr_family": FAMILY,
        "horizon_role": "hold_thesis",
        "_display_only": True,
        "survivorship_biased": True,
    }


# ---------------------------------------------------------------------------
# Main study
# ---------------------------------------------------------------------------

def run_study() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run the full Ruler-P study and return (results_df, summary_dict)."""
    # STEP 1: Declare trial budget BEFORE computing any p-values (CI gate)
    _declare_trial_budget()

    # STEP 2: Load data
    log.info("Loading labels from %s", _LABELS_PATH)
    if not _LABELS_PATH.exists():
        raise FileNotFoundError(f"long_hold_labels.parquet not found: {_LABELS_PATH}")
    labels = pd.read_parquet(_LABELS_PATH)
    labels["fire_date"] = pd.to_datetime(labels["fire_date"])

    log.info("Loading expect_drift panel from %s", _PANEL_PATH)
    if not _PANEL_PATH.exists():
        raise FileNotFoundError(
            f"expect_drift_panel.parquet not found: {_PANEL_PATH}. "
            "Run build_expect_drift_panel.py first."
        )
    panel = pd.read_parquet(_PANEL_PATH)
    panel["fire_date"] = pd.to_datetime(panel["fire_date"])

    log.info(
        "Labels date range: %s → %s",
        str(labels["fire_date"].min().date()),
        str(labels["fire_date"].max().date()),
    )

    # STEP 3: Build Ruler-P cohort (cheap_trap + tactical_only, fires <= 2023-12-31)
    # HARD ASSERTION: 2024+ fires MUST NEVER enter any feature-outcome join (A2 §4)
    labeled = labels[labels["label"].isin(["cheap_trap", "tactical_only"])].copy()
    ruler_p = labeled[labeled["fire_date"] <= pd.Timestamp(RULER_P_CUTOFF)].copy()

    # NOTE: this assertion checks the output of the filter one line above, so it cannot fail
    # on its own.  The actual OOS-2 leak-prevention comes from the left-join key at the
    # feature merge step below (ruler_p already filtered; panel rows for 2024+ are never
    # selected).  The assertion is retained as a belt-and-suspenders documentation aid.
    assert (ruler_p["fire_date"] <= pd.Timestamp(RULER_P_CUTOFF)).all(), (
        f"OOS-2 CONTAMINATION: fires after {RULER_P_CUTOFF} detected — "
        "AMENDMENT_A2_G1_RETEST.md §4 violation"
    )

    log.info(
        "Ruler-P eligible: %d (cheap_trap=%d, tactical_only=%d), range %s → %s",
        len(ruler_p),
        int((ruler_p["label"] == "cheap_trap").sum()),
        int((ruler_p["label"] == "tactical_only").sum()),
        str(ruler_p["fire_date"].min().date()),
        str(ruler_p["fire_date"].max().date()),
    )

    # STEP 4: Merge expect_drift features onto Ruler-P fires
    panel_cols = ["ticker", "fire_date"] + [f for f in FEATURES if f in panel.columns]
    df = ruler_p.merge(panel[panel_cols], on=["ticker", "fire_date"], how="left")
    df["cohort_year"] = df["fire_date"].dt.year
    df[RULER_P_OUTCOME_COL] = (df["label"] == "cheap_trap").astype(int)

    # Attach macro regime
    df = _attach_macro_regime(df)

    # STEP 5: Coverage check
    coverage: dict[str, float] = {}
    for feat in FEATURES:
        if feat in df.columns:
            col = df[feat]
            if FEATURE_TYPES[feat] == "bin":
                col = _coerce_binary_col(col)
            else:
                col = pd.to_numeric(col, errors="coerce")
            coverage[feat] = float(col.notna().mean())
        else:
            coverage[feat] = 0.0

    log.info(
        "Feature coverage in Ruler-P cohort: %s",
        {k: f"{v:.1%}" for k, v in coverage.items()},
    )
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

    # STEP 6: Full Ruler-P cell (2014-2023, UPPER BOUND)
    log.info("--- Full Ruler-P cell (2014-2023) ---")
    full_cell = _analyze_cell(
        df, retained,
        "full_ruler_p_2014-2023",
        "UPPER_BOUND",
    )
    for rec in full_cell["per_feature"]:
        all_rows.append(rec)

    # STEP 7: Temporal cells (pre-registered split: fit 2014-2019 / OOS-biased 2020-2023)
    # NB: cell labels here are distinct from ERA_LABELS (STEP 8) to avoid duplicate rows in
    # the output parquet.  The pre-registered era breakout (STEP 8) also covers 2014-2019
    # as "fit_2014-2019"; the temporal-split cell is labelled "temporal_fit_2014-2019" to
    # prevent the two from colliding.
    for cell_label, cell_start, cell_end in [
        ("temporal_fit_2014-2019",       RULER_P_FIT_START, RULER_P_FIT_END),
        ("oos_biased_2020-2023", RULER_P_OOS_START, RULER_P_OOS_END),
    ]:
        mask = (
            (df["fire_date"] >= pd.Timestamp(cell_start)) &
            (df["fire_date"] <= pd.Timestamp(cell_end))
        )
        cell_df = df[mask].copy()
        surv_note = "UPPER_BOUND"
        log.info("--- Temporal cell: %s (n=%d) ---", cell_label, len(cell_df))
        cell_result = _analyze_cell(cell_df, retained, cell_label, surv_note)
        for rec in cell_result["per_feature"]:
            all_rows.append(rec)

    # STEP 8: Pre-registered era breakout (2014-2019 / 2020-2021 / 2022-2023)
    for era_label, era_start, era_end in ERA_LABELS:
        mask = (
            (df["fire_date"] >= pd.Timestamp(era_start)) &
            (df["fire_date"] <= pd.Timestamp(era_end))
        )
        era_df = df[mask].copy()
        surv_note = "UPPER_BOUND"
        log.info("--- Era cell: %s (n=%d) ---", era_label, len(era_df))
        cell_result = _analyze_cell(era_df, retained, era_label, surv_note)
        for rec in cell_result["per_feature"]:
            all_rows.append(rec)

    # Assemble results DataFrame (cast numpy scalars to native Python)
    results_df = pd.DataFrame(all_rows)

    summary = {
        "family": str(FAMILY),
        "m_hypotheses": int(M_HYPOTHESES),
        "bh_q_threshold": float(BH_Q_THRESHOLD),
        "n_reshuffle": int(N_RESHUFFLE),
        "reshuffle_seed": int(RESHUFFLE_SEED),
        "ruler_p_cutoff": str(RULER_P_CUTOFF),
        "n_ruler_p_fires": int(len(ruler_p)),
        "n_cheap_trap": int((ruler_p["label"] == "cheap_trap").sum()),
        "n_tactical_only": int((ruler_p["label"] == "tactical_only").sum()),
        "retained_features": [str(f) for f in retained],
        "dropped_features": [str(f) for f in dropped],
        "feature_coverage": {str(f): round(float(v), 4) for f, v in coverage.items()},
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    return results_df, summary


# ---------------------------------------------------------------------------
# Markdown report (house style: plain-English box, UPPER BOUND stamps,
# no "validated", no SURVIVE/KILL)
# ---------------------------------------------------------------------------

def write_markdown_report(results_df: pd.DataFrame, summary: dict[str, Any]) -> str:
    """Generate EXPECT_DRIFT_RULER_P_RESULTS.md."""
    lines: list[str] = []
    lines.append("# Expect-Drift Family — Ruler-P Study Results")
    lines.append("")
    lines.append(
        f"**Family:** `{summary['family']}` | "
        f"**m = {summary['m_hypotheses']}** | "
        f"**Ruler-P cutoff:** fires ≤ {summary['ruler_p_cutoff']} | "
        f"**Generated:** {summary['generated_at'][:10]}"
    )
    lines.append("")
    lines.append(
        "> **Authority ceiling:** DISPLAY ONLY. "
        "No SURVIVE/KILL vocabulary. "
        "All cells are UPPER BOUND (survivorship-biased). "
        "The word 'validated' does not appear in this document (CI-enforced)."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # In plain English box (house style)
    lines.append("## In plain English")
    lines.append("")
    lines.append("> **What this study asked:**")
    lines.append("> At the moment of a tactical entry fire, do post-earnings signals — how")
    lines.append("> strong the recent earnings surprise was, how long it has been positive,")
    lines.append("> whether the stock absorbed bad news or held good news — predict which")
    lines.append("> fires end up as cheap traps (durable hold candidates at 252 days)")
    lines.append("> versus tactical-only fires (bounced but faded)?")
    lines.append(">")
    lines.append("> **The contrast:**")
    lines.append("> cheap_trap vs tactical_only, measured at 252 days, fires 2014-2023 only.")
    lines.append("> cheap_trap = entry fires where the stock traded below its fire-date price")
    lines.append("> again within 252 days (the 'left behind' outcome). The hypothesis is that")
    lines.append("> earnings-momentum signals at entry predict this bad outcome — that a fire")
    lines.append("> without earnings support is more likely to become a cheap trap.")
    lines.append(">")
    lines.append("> **What the results mean:**")
    lines.append("> All results here carry a survivorship-bias stamp (UPPER BOUND) because the")
    lines.append("> 2014-2021 cohorts include only stocks that survived. This inflates apparent")
    lines.append("> edges. A feature passing both BH-FDR and the reshuffle-null descriptive")
    lines.append("> gates may be used in display copy, but no result is a final verdict.")
    lines.append("> Final ratification requires Ruler-H on OOS-2 (2025+ honest fires)")
    lines.append("> at the G1-Retest trigger (~2027-H2).")
    lines.append("")

    # Population summary
    lines.append("## Population summary")
    lines.append("")
    lines.append(
        f"| Metric | Value |"
    )
    lines.append("|---|---|")
    lines.append(f"| Ruler-P fires (≤ 2023-12-31) | {summary['n_ruler_p_fires']} |")
    lines.append(f"| cheap_trap | {summary['n_cheap_trap']} |")
    lines.append(f"| tactical_only | {summary['n_tactical_only']} |")
    lines.append(f"| BH q threshold | {summary['bh_q_threshold']} (DESCRIPTIVE per LH-R11.2) |")
    lines.append(f"| Reshuffle permutations | {summary['n_reshuffle']} (seed={summary['reshuffle_seed']} LOCKED) |")
    lines.append(f"| n-floor per arm | {EPISODE_FLOOR} episode-clusters |")
    lines.append("")

    # Feature coverage
    lines.append("## Feature coverage")
    lines.append("")
    lines.append("| Feature | ID | Type | Expected sign | Coverage | Status |")
    lines.append("|---|---|---|---|---|---|")
    for feat in FEATURES:
        cov = summary["feature_coverage"].get(feat, 0.0)
        ftype = FEATURE_TYPES.get(feat, "cont")
        esign = EXPECTED_SIGNS.get(feat, "?")
        feat_id = f"ED-{FEATURES.index(feat) + 1}"
        status = "RETAINED" if feat in summary["retained_features"] else "DROPPED"
        lines.append(f"| `{feat}` | {feat_id} | {ftype} | {esign} | {cov:.1%} | {status} |")
    lines.append("")

    if summary["dropped_features"]:
        lines.append(
            f"> **Dropped features (coverage < {int(COVERAGE_FLOOR * 100)}%):** "
            + ", ".join(f"`{f}`" for f in summary["dropped_features"])
        )
        lines.append("")

    # Results per cell — ALL cells printed including nulls (house style)
    cells = results_df["cell"].unique().tolist() if len(results_df) > 0 else []
    for cell in cells:
        cell_df = results_df[results_df["cell"] == cell]
        surv_note = str(cell_df["survivorship_note"].iloc[0]) if len(cell_df) > 0 else "UPPER_BOUND"
        n_pos = int(cell_df["n_pos"].iloc[0]) if len(cell_df) > 0 else 0
        n_neg = int(cell_df["n_neg"].iloc[0]) if len(cell_df) > 0 else 0
        lines.append(f"## Cell: `{cell}`")
        lines.append("")
        lines.append(
            f"**Survivorship stamp:** {surv_note} | "
            f"cheap_trap n = {n_pos} | tactical_only n = {n_neg} "
            f"(after episode-cluster dedup)"
        )
        lines.append("")

        # Check if any features had enough data
        has_computed = any(
            row.get("n_floor_ok", False)
            for _, row in cell_df.iterrows()
        )
        if not has_computed:
            lines.append(
                f"> **SKIPPED** — n-floor (≥ {EPISODE_FLOOR} per arm) not met "
                "for any feature in this cell."
            )
            lines.append("")
            # Still print the skipped features table
            lines.append(
                "| Feature | ID | n_pos | n_neg | Coverage | Skip reason |"
            )
            lines.append("|---|---|---|---|---|---|")
            for _, row in cell_df.iterrows():
                feat = row["feature"]
                feat_id = row.get("feature_id", "—")
                nfp = row.get("n_feat_pos", "—")
                nfn = row.get("n_feat_neg", "—")
                cov = f"{row['coverage_frac']:.1%}" if row.get("coverage_frac") is not None else "—"
                reason = row.get("display_claim", "SKIPPED")
                lines.append(f"| `{feat}` | {feat_id} | {nfp} | {nfn} | {cov} | {reason} |")
            lines.append("")
            continue

        lines.append(
            "| Feature | ID | Type | RBC | p-value | q-value (BH) | Rej (BH) | "
            "Passes reshuffle | Reshuffle p90 | CI lo | CI hi | n_pos | n_neg | Verdict |"
        )
        lines.append(
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
        )
        for _, row in cell_df.iterrows():
            feat = row["feature"]
            feat_id = row.get("feature_id", "—")
            ftype = row.get("type", "—")
            skipped = not row.get("n_floor_ok", False)
            if skipped:
                reason = row.get("display_claim", "SKIPPED")
                lines.append(
                    f"| `{feat}` | {feat_id} | {ftype} | — | — | — | — | — | — | — | — | "
                    f"{row.get('n_feat_pos', '—')} | {row.get('n_feat_neg', '—')} | _{reason}_ |"
                )
                continue
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
            lines.append(
                f"| `{feat}` | {feat_id} | {ftype} | {rbc} | {p_val} | {q_val} | "
                f"{rej} | {pass_r} | {r_p90} | {ci_lo} | {ci_hi} | "
                f"{n_fp} | {n_fn} | **{verdict}** |"
            )
        lines.append("")

    # Protocol notes
    lines.append("---")
    lines.append("")
    lines.append("## Protocol notes")
    lines.append("")
    lines.append(
        f"- **BH-FDR:** q ≤ {BH_Q_THRESHOLD} across all m = {M_HYPOTHESES} registered features "
        "(DESCRIPTIVE per LH-R11.2 — not ratifying)"
    )
    lines.append(
        f"- **Reshuffle null:** {N_RESHUFFLE} permutations, seed = {RESHUFFLE_SEED} (LOCKED in pre-registration)"
    )
    lines.append(f"- **Episode-cluster floor:** ≥ {EPISODE_FLOOR} per arm")
    lines.append(
        f"- **Episode-cluster dedup:** ± {BLOCK_RADIUS_DAYS} calendar days (≈ ± 10 trading days, "
        "documented deviation from LH-R4)"
    )
    lines.append(
        f"- **CI method:** wider of cluster-bootstrap (ticker × macro_regime; "
        f"seed = {BOOTSTRAP_SEED_CLUSTER}) and block-bootstrap (seed = {BOOTSTRAP_SEED_BLOCK})"
    )
    lines.append(
        "- **Ruler-P cutoff:** fires ≤ 2023-12-31 only. "
        "OOS-2 2025+ cohort is reserved for Ruler-H at G1-Retest (~2027-H2). No contact."
    )
    lines.append(
        "- **Authority ceiling:** DISPLAY ONLY. "
        "A feature passing both BH-FDR and reshuffle null may be shown in display copy. "
        "SURVIVE/KILL vocabulary is banned until Ruler-H."
    )
    lines.append(
        "- **TrialLedger:** `log_declared_budget(7, family='long_hold.expect_drift')` "
        "called BEFORE p-value computation (CI gate passed)."
    )
    lines.append(
        "- **Survivorship bias:** all Ruler-P cells are UPPER BOUND "
        "(pre-2021-07 tickers survivorship-biased per LH-R3)."
    )
    lines.append(
        "- **OOS-2 contamination guard:** hard assertion `fire_date <= 2023-12-31` — "
        "no 2024+ fires enter any feature-outcome join (AMENDMENT_A2_G1_RETEST.md §4)."
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

def _register_experiments(
    results_df: pd.DataFrame,
    dry_run: bool = False,
) -> None:
    """Add expect-drift-ruler-p and expect-drift-ruler-h-accrual to registry."""
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

    # Derive study status from results (DESCRIPTIVE_PASS vs all NULL)
    if len(results_df) > 0:
        full_cell = results_df[results_df["cell"] == "full_ruler_p_2014-2023"]
        n_pass = int((full_cell["display_claim"] == "DESCRIPTIVE_PASS").sum())
        study_status = "complete"
        study_state = (
            f"Ruler-P complete; {n_pass}/{M_HYPOTHESES} features pass both "
            "BH-FDR and reshuffle-null descriptive gates in full cell. "
            "Ruler-H accruing."
        )
    else:
        n_pass = 0
        study_status = "complete"
        study_state = "Ruler-P complete (no results); Ruler-H accruing."

    new_entries = []

    if "expect-drift-ruler-p" not in existing_ids:
        new_entries.append({
            "id": "expect-drift-ruler-p",
            "name": "Expect-Drift LH — Ruler-P study (cheap_trap vs tactical_only, 252d)",
            "kind": "offline_study",
            "priority": "medium",
            "cadence": "on-demand",
            "what": (
                "Ruler-P study for F3 expect_drift family: ED-1..ED-7 features, "
                "cheap_trap vs tactical_only contrast at 252d, fires <= 2023-12-31, "
                "episode-clustered (name × macro_regime ±14 calendar days), "
                "MWU/RBC for cont (ED-1/2/3/6), Fisher exact for bin (ED-4/5/7), "
                "BH q=0.10 descriptive, reshuffle null 1000/seed=42. "
                "UPPER BOUND (survivorship-biased). Display-ceiling authority."
            ),
            "source": "scripts/research/expect_drift_ruler_p_study.py",
            "storage": "data/research/expect_drift_ruler_p_results.parquet",
            "hook": "offline_study",
            "started": "2026-07-06",
            "come_back_on": "2026-07-06",
            "come_back_note": "Study complete on run; Ruler-H at G1-Retest ~2027-H2",
            "maturation": "Ruler-H on OOS-2 at G1-Retest trigger (~2027-H2); program-wide BH q=0.10",
            "status": study_status,
            "state": study_state,
            "next_step": "Review Ruler-H at G1-Retest (~2027-H2).",
            "phase_hint": "Ruler-H",
        })

    if "expect-drift-ruler-h-accrual" not in existing_ids:
        new_entries.append({
            "id": "expect-drift-ruler-h-accrual",
            "name": "Expect-Drift LH — Ruler-H accrual (OOS-2 honest compounder contrast)",
            "kind": "track_record",
            "priority": "low",
            "cadence": "none",
            "what": (
                "Ruler-H for F3 expect_drift family: missed_hold vs tactical_only "
                "on OOS-2 (2025+) at G1-Retest. Program-wide HLZ q=0.10. "
                "Evaluated at >= 25 honest compounder episode-cluster trigger (~2027-H2)."
            ),
            "source": "scripts/research/expect_drift_ruler_p_study.py",
            "storage": "data/research/expect_drift_panel.parquet",
            "hook": "offline_study",
            "started": "2026-07-06",
            "come_back_on": "2027-07-01",
            "come_back_note": (
                "G1-Retest A2 trigger: >= 25 honest compounder clusters "
                "(Amendment A2 §4, AMENDMENT_A2_G1_RETEST.md)"
            ),
            "maturation": (
                ">= 25 episode-cluster honest compounder fires in OOS-2 "
                "AND program-wide BH q=0.10"
            ),
            "status": "accruing",
            "state": "Accruing OOS-2 honest compounder fires. G1-Retest not triggered yet.",
            "next_step": "Check 2027-07-01: if >= 25 honest compounder clusters, run Ruler-H study.",
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
                json.dumps(out_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
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
    ap = argparse.ArgumentParser(
        description="LT-2b Ruler-P study: cheap_trap vs tactical_only for expect_drift family"
    )
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

        _register_experiments(results_df, dry_run=False)
    else:
        log.info("DRY RUN: skipping file writes")
        print(md_text[:4000])

    # Print headline table to stdout
    if len(results_df) > 0:
        full_cell_df = results_df[results_df["cell"] == "full_ruler_p_2014-2023"]
        print("\n=== Ruler-P headline results (full cell 2014-2023) ===")
        print(
            f"{'Feature':<26} {'ID':>5} {'Type':>5} {'RBC':>7} {'p-val':>8} "
            f"{'q-val':>8} {'Reject':>7} {'PassR':>6} {'Verdict'}"
        )
        print("-" * 105)
        for _, row in full_cell_df.iterrows():
            rbc = f"{row['rbc']:.3f}" if row.get("rbc") is not None else "    —"
            p = f"{row['p_value']:.4f}" if row.get("p_value") is not None else "       —"
            q = f"{row['q_value']:.4f}" if row.get("q_value") is not None else "       —"
            rej = str(row.get("rejected_bh", "—"))
            pr = str(row.get("passes_reshuffle", "—"))
            v = str(row.get("display_claim", "—"))
            fid = str(row.get("feature_id", "—"))
            ftype = str(row.get("type", "—"))
            print(
                f"{row['feature']:<26} {fid:>5} {ftype:>5} {rbc:>7} {p:>8} "
                f"{q:>8} {rej:>7} {pr:>6} {v}"
            )
        print()


if __name__ == "__main__":
    main()
