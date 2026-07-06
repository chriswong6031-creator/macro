"""OTA W1 — Onset-Quality Discriminator
===========================================
Pre-registered protocol (research/oracle_asymmetry/W1_SPEC.md).
Seed: 20260705 everywhere.

Outputs:
  research/oracle_asymmetry/W1_features.csv
  research/oracle_asymmetry/W1_REPORT.md

Run:
  python scripts/oracle_onset_quality_w1.py [--data-dir <path>]

Spec §7 prohibitions are enforced in this file: no engine/scripts edits,
no trial-ledger writes, no hyperparameter search beyond §3 inner CV,
no post-hoc feature additions.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("w1")

# ---------------------------------------------------------------------------
# Constants (frozen — spec §1 / §4)
# ---------------------------------------------------------------------------
SEED = 20260705
W0_CSV_EP_ONSET_IN_ROWS_POS63 = 357  # assert exactly — per spec §1
LOEO_PURGE_SESSIONS = 63            # purge window §4
NULL_PERMS = 200                     # shuffled-label count §4
GOOD_STATES = {"CUSHIONED", "CLEAN_LIFTOFF"}
KEEP_TOP_40 = 0.40
KEEP_TOP_60 = 0.60

# Era cuts (imported from scripts.oracle_screen)
try:
    from scripts.oracle_screen import _ERA_CUTS  # type: ignore
except Exception:  # pragma: no cover – fallback matches oracle_screen source
    _ERA_CUTS = [
        ("1999-2014", "1999-01-01", "2014-12-31"),
        ("2015-2019", "2015-01-01", "2019-12-31"),
        ("2020-2022", "2020-01-01", "2022-12-31"),
        ("2023-2026", "2023-01-01", "2099-12-31"),
    ]

# ETF → complex mapping (mirrors oracle_gauntlet_p8._MEMBER_TO_ETF +
# _ETF_DIRECT_OVERRIDE and engine.oracle.graph.COMPLEX_ETF_MAP).
# Kept local to avoid importing engine (which we must not modify).
_MEMBER_TO_ETF: dict[str, str] = {
    "us_sector_health": "XLV",
    "us_sector_staples": "XLP",
    "us_sector_energy": "XLE",
    "us_sector_materials": "XLB",
    "us_sector_financials": "XLF",
    "us_sector_realestate": "XLRE",
    "us_sector_utilities": "XLU",
    "us_sector_industrials": "XLI",
}
_ETF_DIRECT_OVERRIDE: dict[str, str] = {
    "XLK": "ai_compute",
    "XLY": "short_duration_value",
    "XLC": "software",
}


# ---------------------------------------------------------------------------
# Helpers: complex mapping
# ---------------------------------------------------------------------------

def build_etf_complex_map(rotation_groups: dict) -> dict[str, dict]:
    """Return etf -> {complex_id, risk_sign}."""
    etf_map: dict[str, dict] = {}
    complexes = rotation_groups.get("complexes", [])
    for cdef in complexes:
        cid = cdef["id"]
        risk_sign = cdef["risk_sign"]
        for member in cdef.get("members", []):
            etf = _MEMBER_TO_ETF.get(member)
            if etf and etf not in etf_map:
                etf_map[etf] = {"complex_id": cid, "risk_sign": risk_sign}
    for etf, cid in _ETF_DIRECT_OVERRIDE.items():
        if etf not in etf_map:
            for cdef in complexes:
                if cdef["id"] == cid:
                    etf_map[etf] = {"complex_id": cid, "risk_sign": cdef["risk_sign"]}
                    break
    return etf_map


def build_opposite_risk_map(rotation_groups: dict) -> dict[str, list[str]]:
    """Return complex_id -> list of complex_ids with opposite risk_sign."""
    complexes = rotation_groups.get("complexes", [])
    risk_by_cid: dict[str, str] = {c["id"]: c["risk_sign"] for c in complexes}
    opp: dict[str, list[str]] = {}
    for cid, rsign in risk_by_cid.items():
        opp[cid] = [c for c, r in risk_by_cid.items() if r != rsign]
    return opp


# ---------------------------------------------------------------------------
# Feature computation helpers
# ---------------------------------------------------------------------------

def _rolling_252d_pctile(series: pd.Series) -> pd.Series:
    """Causal 252-session percentile rank of rs.  Returns NaN if < 252 obs."""
    def pctile(arr: np.ndarray) -> float:
        if len(arr) < 252:
            return np.nan
        return float(np.sum(arr[:-1] < arr[-1]) / (len(arr) - 1))
    return series.rolling(252, min_periods=252).apply(pctile, raw=True)


def _causal_accel_z_5d(accel_z: pd.Series) -> pd.Series:
    """Rolling 5-session mean of accel_z (causal, trailing)."""
    return accel_z.rolling(5, min_periods=1).mean()


def compute_features(
    pop: pd.DataFrame,
    panel: pd.DataFrame,
    episodes_s: pd.DataFrame,
    etf_complex_map: dict,
    opposite_risk_map: dict,
    w0_state_lookup: Optional[dict] = None,
) -> pd.DataFrame:
    """Build all 16 PIT features for each row in pop.

    pop: the matured pos63 onset events (one row per episode onset).
    w0_state_lookup: dict mapping (node, onset_date_str) -> 1.0/0.0 for F15.
        If None, F15 will always emit 0.0 (no prior quality info).
    Returns pop with feature columns appended.
    """
    log.info("Computing features for %d events …", len(pop))

    # Pre-compute per-node panel features (causal, no lookahead)
    # We need: accel_z, accel_z_5d, accel, rs_pctile_252d,
    #           persistence, washout_w, stochrsi_w_k, stochrsi_w_d,
    #           vix_pctile, spy_above_200d, tlt_ret_10d

    # Unstack panel to per-node series for fast lookup
    # panel index: (node, date)
    panel_by_col: dict[str, pd.DataFrame] = {}
    for col in [
        "accel_z", "accel", "rs", "persistence", "washout_w",
        "stochrsi_w_k", "stochrsi_w_d", "vix_pctile", "spy_above_200d",
        "tlt_ret_10d",
    ]:
        if col in panel.columns:
            panel_by_col[col] = panel[col].unstack(level="node")

    # Compute accel_z_5d per node (causal rolling mean)
    accel_z_wide = panel_by_col["accel_z"]
    accel_z_5d_wide = accel_z_wide.apply(_causal_accel_z_5d, axis=0)

    # Compute 252d rs percentile per node (causal)
    rs_wide = panel_by_col["rs"]
    rs_pctile_wide = rs_wide.apply(_rolling_252d_pctile, axis=0)

    # Build per-date lookup tables for flow counts (F12, F13, F14)
    # episodes_s has onset_date, exhausted_date, direction, node
    eps_in = episodes_s[episodes_s["direction"] == "in"].copy()
    eps_out = episodes_s[episodes_s["direction"] == "out"].copy()

    # Convert dates to pandas Timestamps for comparison
    eps_in = eps_in.copy()
    eps_out = eps_out.copy()
    eps_in["onset_date"] = pd.to_datetime(eps_in["onset_date"])
    eps_out["onset_date"] = pd.to_datetime(eps_out["onset_date"])

    # For each trigger date t and node, get the trading-session calendar
    # We need session-lag counts: episodes with onset within 20 sessions <= t
    # "20 sessions" means 20 business days before t (inclusive of t).
    # We approximate with a 28-calendar-day window (conservative for 20 sessions).
    # For an exact 20-session count we compare against the panel date index.
    all_dates = panel.index.get_level_values("date").unique().sort_values()
    all_dates_arr = np.array(all_dates, dtype="datetime64[D]")

    def sessions_before(t: pd.Timestamp, n: int = 20) -> np.ndarray:
        """Return array of n session dates strictly before t (inclusive of t)."""
        t_val = np.datetime64(t.date(), "D")
        idx = np.searchsorted(all_dates_arr, t_val, side="right")
        start = max(0, idx - n)
        return all_dates_arr[start:idx]

    # Build rows
    rows = []
    for _, ev in pop.iterrows():
        node = ev["node"]
        t = pd.Timestamp(ev["trigger_date"])
        t_key = t.normalize()

        row: dict = {}

        # ---- F1: accel_z at t ----
        try:
            row["accel_z"] = float(accel_z_wide.loc[t_key, node]) if node in accel_z_wide.columns else np.nan
        except KeyError:
            row["accel_z"] = np.nan

        # ---- F2: accel_z_5d (causal rolling-5 mean) ----
        try:
            row["accel_z_5d"] = float(accel_z_5d_wide.loc[t_key, node]) if node in accel_z_5d_wide.columns else np.nan
        except KeyError:
            row["accel_z_5d"] = np.nan

        # ---- F3: accel (vel_1w − vel_3m) at t ----
        try:
            row["accel"] = float(panel_by_col["accel"].loc[t_key, node]) if node in panel_by_col["accel"].columns else np.nan
        except KeyError:
            row["accel"] = np.nan

        # ---- F4: causal 252d percentile of rs at t ----
        try:
            row["rs_pctile_252d"] = float(rs_pctile_wide.loc[t_key, node]) if node in rs_pctile_wide.columns else np.nan
        except KeyError:
            row["rs_pctile_252d"] = np.nan

        # ---- F5: persistence at t ----
        try:
            row["persistence"] = float(panel_by_col["persistence"].loc[t_key, node]) if node in panel_by_col["persistence"].columns else np.nan
        except KeyError:
            row["persistence"] = np.nan

        # ---- F6: washout_w at t ----
        try:
            row["washout_w"] = float(panel_by_col["washout_w"].loc[t_key, node]) if node in panel_by_col["washout_w"].columns else np.nan
        except KeyError:
            row["washout_w"] = np.nan

        # ---- F7: stochrsi_w_k at t (scale 0–100) ----
        try:
            row["stochrsi_w_k"] = float(panel_by_col["stochrsi_w_k"].loc[t_key, node]) if node in panel_by_col["stochrsi_w_k"].columns else np.nan
        except KeyError:
            row["stochrsi_w_k"] = np.nan

        # ---- F8: stochrsi_w_k − stochrsi_w_d at t ----
        try:
            k = panel_by_col["stochrsi_w_k"].loc[t_key, node] if node in panel_by_col["stochrsi_w_k"].columns else np.nan
            d = panel_by_col["stochrsi_w_d"].loc[t_key, node] if node in panel_by_col["stochrsi_w_d"].columns else np.nan
            row["stochrsi_kd_diff"] = float(k - d) if not (np.isnan(k) or np.isnan(d)) else np.nan
        except KeyError:
            row["stochrsi_kd_diff"] = np.nan

        # ---- F9: vix_pctile at t ----
        try:
            # vix_pctile is node-invariant; use any node
            vix_col = panel_by_col["vix_pctile"]
            first_col = vix_col.columns[0]
            row["vix_pctile"] = float(vix_col.loc[t_key, first_col]) if t_key in vix_col.index else np.nan
        except (KeyError, IndexError):
            row["vix_pctile"] = np.nan

        # ---- F10: spy_above_200d at t ----
        try:
            spy_col = panel_by_col["spy_above_200d"]
            first_col = spy_col.columns[0]
            row["spy_above_200d"] = float(spy_col.loc[t_key, first_col]) if t_key in spy_col.index else np.nan
        except (KeyError, IndexError):
            row["spy_above_200d"] = np.nan

        # ---- F11: tlt_ret_10d at t ----
        try:
            tlt_col = panel_by_col["tlt_ret_10d"]
            first_col = tlt_col.columns[0]
            row["tlt_ret_10d"] = float(tlt_col.loc[t_key, first_col]) if t_key in tlt_col.index else np.nan
        except (KeyError, IndexError):
            row["tlt_ret_10d"] = np.nan

        # ---- F12/F13: flow displacement (opposite-complex and same-complex OUT-onset counts) ----
        # Map this node to its complex
        node_complex_info = etf_complex_map.get(node, {})
        node_cid = node_complex_info.get("complex_id", "")
        opp_cids = opposite_risk_map.get(node_cid, [])

        # Get set of ETFs in opposite complexes
        opp_etfs: set[str] = set()
        same_etfs: set[str] = set()
        for etf, cinfo in etf_complex_map.items():
            cid = cinfo.get("complex_id", "")
            if cid in opp_cids:
                opp_etfs.add(etf)
            elif cid == node_cid and etf != node:
                same_etfs.add(etf)

        # 20-session window <= t
        window_dates = sessions_before(t, n=20)
        if len(window_dates) > 0:
            wmin = pd.Timestamp(window_dates[0])
            wmax = pd.Timestamp(window_dates[-1])
        else:
            wmin = t
            wmax = t

        # F12: opposite-complex OUT onsets within 20 sessions <= t
        mask_opp = (
            eps_out["node"].isin(opp_etfs)
            & (eps_out["onset_date"] >= wmin)
            & (eps_out["onset_date"] <= wmax)
        )
        row["flow_opp_out_20s"] = int(mask_opp.sum())

        # F13: same-complex OUT onsets within 20 sessions <= t (same complex, different node)
        mask_same = (
            eps_out["node"].isin(same_etfs)
            & (eps_out["onset_date"] >= wmin)
            & (eps_out["onset_date"] <= wmax)
        )
        row["flow_same_out_20s"] = int(mask_same.sum())

        # ---- F14: concurrently active IN episodes across all nodes at t ----
        # An IN episode is "active at t" if onset_date <= t and exhausted_date is NaN or >= t.
        # Use episodes_s (MAIN, read-only)
        eps_in_active = eps_in[
            (eps_in["onset_date"] <= t)
            & (eps_in["node"] != node)  # exclude self
        ]
        # Check exhausted_date — include episodes not yet exhausted
        if "exhausted_date" in eps_in.columns:
            exhaust_dates = pd.to_datetime(eps_in_active["exhausted_date"], errors="coerce")
            active_mask = exhaust_dates.isna() | (exhaust_dates >= t)
            row["active_in_episodes"] = int(active_mask.sum())
        else:
            row["active_in_episodes"] = int(len(eps_in_active))

        # ---- F15: previous same-node episode's good/bad outcome ----
        # Most recent same-node IN episode whose onset is fully matured
        # >= 63 sessions before t (leakage-lawful cutoff).
        # "good" = CUSHIONED | CLEAN_LIFTOFF (the W0 good-set label from the
        # committed W0_2_events_graded.csv, pos63 rows).
        # outcome_mature_63d in episodes_s is a MATURITY FLAG (True for 98%
        # of IN episodes), NOT a quality signal — spec §2 F15 requires the
        # prior episode's good/bad quality outcome, so we use the W0 state lookup.
        cutoff_idx = np.searchsorted(all_dates_arr, np.datetime64(t.date(), "D"), side="right")
        cutoff_idx = max(0, cutoff_idx - 63)
        if cutoff_idx > 0:
            cutoff_date = pd.Timestamp(all_dates_arr[cutoff_idx])
        else:
            cutoff_date = pd.Timestamp("1970-01-01")

        prev_episodes = eps_in[
            (eps_in["node"] == node)
            & (eps_in["onset_date"] < cutoff_date)
        ].sort_values("onset_date", ascending=False)

        if len(prev_episodes) == 0 or w0_state_lookup is None:
            row["prev_same_node_outcome"] = 0.0
        else:
            latest = prev_episodes.iloc[0]
            onset_key = str(pd.Timestamp(latest["onset_date"]).date())
            lookup_key = (str(node), onset_key)
            label = w0_state_lookup.get(lookup_key, None)
            if label is None:
                # Prior episode not in W0 pos63 sample (different direction/param);
                # emit 0.0 (no information) rather than crashing.
                row["prev_same_node_outcome"] = 0.0
            else:
                row["prev_same_node_outcome"] = label

        # ---- F16: sigma20 from the W0 CSV row ----
        row["sigma20"] = float(ev["sigma20"]) if pd.notna(ev.get("sigma20", np.nan)) else np.nan

        rows.append(row)

    feat_df = pd.DataFrame(rows, index=pop.index)
    # Drop any columns from pop that are already in feat_df to avoid duplicate columns
    pop_clean = pop.drop(columns=[c for c in pop.columns if c in feat_df.columns], errors="ignore")
    result = pd.concat([pop_clean.reset_index(drop=True), feat_df.reset_index(drop=True)], axis=1)
    return result


FEATURE_COLS = [
    "accel_z", "accel_z_5d", "accel", "rs_pctile_252d",
    "persistence", "washout_w", "stochrsi_w_k", "stochrsi_kd_diff",
    "vix_pctile", "spy_above_200d", "tlt_ret_10d",
    "flow_opp_out_20s", "flow_same_out_20s", "active_in_episodes",
    "prev_same_node_outcome", "sigma20",
]

M0_FEATURES = ["accel_z_5d", "vix_pctile"]


# ---------------------------------------------------------------------------
# LOEO protocol
# ---------------------------------------------------------------------------

def assign_era(trigger_date: pd.Timestamp) -> Optional[str]:
    """Assign era label to a trigger date."""
    for era_name, start, end in _ERA_CUTS:
        if pd.Timestamp(start) <= trigger_date <= pd.Timestamp(end):
            return era_name
    return None


def get_era_date_bounds(era_name: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (start, end) Timestamps for an era."""
    for name, start, end in _ERA_CUTS:
        if name == era_name:
            return pd.Timestamp(start), pd.Timestamp(end)
    raise KeyError(f"Unknown era: {era_name!r}")


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------

def _fill_nans_train_median(
    X_train: np.ndarray,
    X_test: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fill NaNs using train-fold medians (spec §2).

    Returns (X_train_filled, X_test_filled, medians).
    """
    medians = np.nanmedian(X_train, axis=0)
    X_train_f = np.where(np.isnan(X_train), medians, X_train)
    X_test_f = np.where(np.isnan(X_test), medians, X_test)
    return X_train_f, X_test_f, medians


def fit_m0(X_train: np.ndarray, y_train: np.ndarray) -> object:
    """M0: logistic regression on {accel_z_5d, vix_pctile}."""
    from sklearn.linear_model import LogisticRegression
    clf = LogisticRegression(
        C=1.0, solver="lbfgs", max_iter=1000, random_state=SEED
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        clf.fit(X_train, y_train)
    return clf


def fit_m1(X_train: np.ndarray, y_train: np.ndarray) -> object:
    """M1: L2 logistic on all 16 features with inner time-ordered CV."""
    from sklearn.linear_model import LogisticRegressionCV
    from sklearn.model_selection import TimeSeriesSplit
    inner_cv = TimeSeriesSplit(n_splits=3)
    clf = LogisticRegressionCV(
        Cs=10,
        cv=inner_cv,
        penalty="l2",
        solver="lbfgs",
        max_iter=2000,
        random_state=SEED,
        refit=True,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        clf.fit(X_train, y_train)
    return clf


def fit_m2(X_train: np.ndarray, y_train: np.ndarray, feature_cols: list[str]) -> Optional[object]:
    """M2: shallow gradient boosting (depth<=2, <=150 trees, lr<=0.1).

    Spec §3: depth ≤ 2, ≤ 150 trees, learning rate ≤ 0.1.
    We use max_iter=50 (within ≤150 bound) for computational feasibility;
    this is a first-time parameter selection, not hyperparameter search.
    Monotone constraints where sign is mechanism-implied:
      +flow_opp_out_20s: more opposite-complex displacement → better onset
      +washout_w: washout condition → better onset
      -stochrsi_w_k: lower StochRSI level (more room to run) → better onset
      +accel_z: stronger acceleration → better onset

    Returns None if no library supports it.
    """
    # Monotone constraints (+1 = monotone increasing, -1 = monotone decreasing, 0 = unconstrained)
    monotone_map = {
        "flow_opp_out_20s": 1,    # more opposite-complex outflows → better
        "washout_w": 1,           # washout → better
        "stochrsi_w_k": -1,       # lower stoch level → more room → better
        "accel_z": 1,             # stronger acceleration → better
    }
    # HistGradientBoostingClassifier supports monotonic_cst (unlike GradientBoostingClassifier)
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        monotone_cst = [monotone_map.get(c, 0) for c in feature_cols]
        clf = HistGradientBoostingClassifier(
            max_depth=2,
            max_iter=50,         # ≤ 150 per spec; 50 chosen for computational feasibility
            learning_rate=0.1,
            random_state=SEED,
            monotonic_cst=monotone_cst,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            clf.fit(X_train, y_train)
        log.info("M2: HistGradientBoostingClassifier with monotone constraints fitted")
        return clf
    except Exception as exc:
        log.warning("M2: HistGradientBoostingClassifier failed (%s) — skipping M2", exc)
        return None


def predict_proba_pos(clf, X: np.ndarray) -> np.ndarray:
    """Return probability of positive class."""
    if clf is None:
        return np.full(len(X), 0.5)
    return clf.predict_proba(X)[:, 1]


# ---------------------------------------------------------------------------
# Calibration table
# ---------------------------------------------------------------------------

def calibration_table(y_true: np.ndarray, proba: np.ndarray, n_bins: int = 5) -> pd.DataFrame:
    """5-bin reliability table for calibration reporting."""
    bins = np.linspace(0, 1, n_bins + 1)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (proba >= lo) & (proba < hi)
        if hi == 1.0:
            mask = (proba >= lo) & (proba <= hi)
        n = int(mask.sum())
        if n > 0:
            mean_pred = float(proba[mask].mean())
            actual_rate = float(y_true[mask].mean())
        else:
            mean_pred = float((lo + hi) / 2)
            actual_rate = float("nan")
        rows.append({
            "bin_lo": round(lo, 2),
            "bin_hi": round(hi, 2),
            "n": n,
            "mean_pred": round(mean_pred, 4) if n > 0 else float("nan"),
            "actual_rate": round(actual_rate, 4) if n > 0 else float("nan"),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Wilson lower bound
# ---------------------------------------------------------------------------

def wilson_lb(k: int, n: int, z: float = 1.96) -> float:
    """Wilson 95% lower bound for a proportion k/n."""
    if n == 0:
        return float("nan")
    p_hat = k / n
    denom = 1 + z ** 2 / n
    centre = (p_hat + z ** 2 / (2 * n)) / denom
    half_width = (z * math.sqrt(p_hat * (1 - p_hat) / n + z ** 2 / (4 * n ** 2))) / denom
    return max(0.0, centre - half_width)


# ---------------------------------------------------------------------------
# G-C reporting helper
# ---------------------------------------------------------------------------

def gc_report(
    y_true: np.ndarray,
    proba: np.ndarray,
    era_labels: np.ndarray,
    threshold_40: float,
    threshold_60: float,
    base_rate: float,
) -> dict:
    """Compute G-C lift table at 40% and 60% keep-top thresholds (train-fitted)."""
    results: dict = {"pooled_40": {}, "pooled_60": {}, "per_era_40": {}, "per_era_60": {}}

    for pct, key_suffix, thresh in [
        (KEEP_TOP_40, "40", threshold_40),
        (KEEP_TOP_60, "60", threshold_60),
    ]:
        mask = proba >= thresh
        k = int(y_true[mask].sum())
        n = int(mask.sum())
        rate = float(y_true[mask].mean()) if n > 0 else float("nan")
        lb = wilson_lb(k, n)
        results[f"pooled_{key_suffix}"] = {
            "threshold": round(thresh, 4),
            "n_kept": n,
            "n_total": len(y_true),
            "good_rate": round(rate, 4) if n > 0 else float("nan"),
            "base_rate": round(base_rate, 4),
            "lift": round(rate - base_rate, 4) if n > 0 else float("nan"),
            "wilson_lb_95": round(lb, 4),
        }
        # Per era
        era_rows = {}
        for era in np.unique(era_labels):
            em = era_labels == era
            em_keep = em & mask
            k_e = int(y_true[em_keep].sum())
            n_e = int(em_keep.sum())
            n_era = int(em.sum())
            br_e = float(y_true[em].mean()) if n_era > 0 else float("nan")
            rate_e = float(y_true[em_keep].mean()) if n_e > 0 else float("nan")
            lb_e = wilson_lb(k_e, n_e)
            era_rows[str(era)] = {
                "n_era": n_era,
                "n_kept": n_e,
                "good_rate": round(rate_e, 4) if n_e > 0 else float("nan"),
                "base_rate": round(br_e, 4),
                "lift": round(rate_e - br_e, 4) if n_e > 0 else float("nan"),
                "wilson_lb_95": round(lb_e, 4),
            }
        results[f"per_era_{key_suffix}"] = era_rows
    return results


def gc_report_fold_thresholds(
    y_true: np.ndarray,
    proba: np.ndarray,
    era_labels: np.ndarray,
    threshold_40_per_event: np.ndarray,
    threshold_60_per_event: np.ndarray,
    base_rate: float,
    avg_thresh_40: float,
    avg_thresh_60: float,
) -> dict:
    """G-C lift table using per-event thresholds derived from train folds only.

    Each OOF event is kept/filtered by the threshold computed from the train
    fold that held it out — no test-distribution contamination (spec §5/§7).
    avg_thresh_40/avg_thresh_60 are the pooled-average thresholds, reported
    for display only.
    """
    results: dict = {"pooled_40": {}, "pooled_60": {}, "per_era_40": {}, "per_era_60": {}}

    for key_suffix, threshold_per_event, avg_thresh in [
        ("40", threshold_40_per_event, avg_thresh_40),
        ("60", threshold_60_per_event, avg_thresh_60),
    ]:
        # Keep events whose OOF proba >= their fold's train-derived threshold
        covered = ~np.isnan(threshold_per_event)
        mask = covered & (proba >= threshold_per_event)
        k = int(y_true[mask].sum())
        n = int(mask.sum())
        n_total_covered = int(covered.sum())
        rate = float(y_true[mask].mean()) if n > 0 else float("nan")
        lb = wilson_lb(k, n)
        results[f"pooled_{key_suffix}"] = {
            "threshold": round(avg_thresh, 4),
            "n_kept": n,
            "n_total": n_total_covered,
            "good_rate": round(rate, 4) if n > 0 else float("nan"),
            "base_rate": round(base_rate, 4),
            "lift": round(rate - base_rate, 4) if n > 0 else float("nan"),
            "wilson_lb_95": round(lb, 4),
        }
        # Per era
        era_rows = {}
        for era in np.unique(era_labels):
            em = era_labels == era
            em_covered = em & covered
            em_keep = em & mask
            k_e = int(y_true[em_keep].sum())
            n_e = int(em_keep.sum())
            n_era = int(em_covered.sum())
            br_e = float(y_true[em_covered].mean()) if n_era > 0 else float("nan")
            rate_e = float(y_true[em_keep].mean()) if n_e > 0 else float("nan")
            lb_e = wilson_lb(k_e, n_e)
            era_rows[str(era)] = {
                "n_era": n_era,
                "n_kept": n_e,
                "good_rate": round(rate_e, 4) if n_e > 0 else float("nan"),
                "base_rate": round(br_e, 4),
                "lift": round(rate_e - br_e, 4) if n_e > 0 else float("nan"),
                "wilson_lb_95": round(lb_e, 4),
            }
        results[f"per_era_{key_suffix}"] = era_rows
    return results


# ---------------------------------------------------------------------------
# Main LOEO protocol
# ---------------------------------------------------------------------------

def run_loeo(
    df: pd.DataFrame,
    label_col: str,
    feature_cols: list[str],
    m0_features: list[str],
    smoke: bool = False,
) -> dict:
    """Run full LOEO protocol per spec §4.

    smoke=True skips the 200-permutation null loop (0 perms) so the end-to-end
    path can be exercised cheaply.  Produces valid AUCs but no null p-value.

    Returns a dict with per-era and pooled metrics for M0, M1, M2.
    """
    from sklearn.metrics import roc_auc_score

    n_perms = 0 if smoke else NULL_PERMS
    if smoke:
        log.info("SMOKE MODE: skipping permutation null (0 perms)")

    rng = np.random.default_rng(SEED)

    eras = [era for era, _, _ in _ERA_CUTS]
    n_eras = len(eras)

    # Per-model results storage
    results: dict = {
        "M0": {"per_era_auc": {}, "oof_proba": np.zeros(len(df)), "oof_y": np.zeros(len(df))},
        "M1": {"per_era_auc": {}, "oof_proba": np.zeros(len(df)), "oof_y": np.zeros(len(df))},
        "M2": {"per_era_auc": {}, "oof_proba": np.zeros(len(df)), "oof_y": np.zeros(len(df))},
        "null": {"per_era_mean_aucs": []},
    }

    all_X = df[feature_cols].values.astype(float)
    all_X_m0 = df[m0_features].values.astype(float)
    all_y = df[label_col].values.astype(int)
    all_era = df["era"].values

    oof_idx_map: dict[str, list[int]] = {era: [] for era in eras}

    for test_era in eras:
        log.info("LOEO fold: test_era=%s", test_era)
        test_era_start, test_era_end = get_era_date_bounds(test_era)

        test_mask = all_era == test_era
        n_test = int(test_mask.sum())
        if n_test == 0:
            log.warning("  No test events in era %s — skipping fold", test_era)
            continue

        # Build train mask with 63-session purge at both boundaries
        # Purge: any training event whose 63-session outcome window overlaps the test era.
        # A 63-session outcome window starting at trigger date t ends at approximately
        # t + 63 business days ≈ t + 89 calendar days.
        # Purge condition (conservative): trigger_date > test_era_start - 63_sessions OR
        # trigger_date < test_era_end + 63_sessions.
        # Simpler equivalent: exclude train events within [test_era_start - 63bd, test_era_end + 63bd].
        train_dates = pd.to_datetime(df["trigger_date"])
        purge_lo = test_era_start - pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)
        purge_hi = test_era_end + pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)
        purge_mask = (train_dates >= purge_lo) & (train_dates <= purge_hi)
        train_mask = (~test_mask) & (~purge_mask)

        n_train = int(train_mask.sum())
        log.info(
            "  train n=%d (after purge), test n=%d, purged=%d",
            n_train, n_test, int(purge_mask.sum()) - n_test,
        )

        if n_train < 10:
            log.warning("  Too few train events (%d) — skipping fold", n_train)
            continue

        X_tr = all_X[train_mask]
        X_te = all_X[test_mask]
        X_tr_m0 = all_X_m0[train_mask]
        X_te_m0 = all_X_m0[test_mask]
        y_tr = all_y[train_mask]
        y_te = all_y[test_mask]

        # Fill NaNs with train medians (spec §2)
        X_tr_f, X_te_f, _ = _fill_nans_train_median(X_tr, X_te)
        X_tr_m0_f, X_te_m0_f, _ = _fill_nans_train_median(X_tr_m0, X_te_m0)

        # Track OOF indices
        te_indices = np.where(test_mask)[0]
        for i in te_indices:
            oof_idx_map[test_era].append(i)

        # ---- M0 ----
        clf_m0 = fit_m0(X_tr_m0_f, y_tr)
        p_m0 = predict_proba_pos(clf_m0, X_te_m0_f)
        auc_m0 = roc_auc_score(y_te, p_m0) if len(np.unique(y_te)) > 1 else float("nan")
        results["M0"]["per_era_auc"][test_era] = round(auc_m0, 4)
        results["M0"]["oof_proba"][te_indices] = p_m0
        results["M0"]["oof_y"][te_indices] = y_te

        # ---- M1 ----
        clf_m1 = fit_m1(X_tr_f, y_tr)
        p_m1 = predict_proba_pos(clf_m1, X_te_f)
        auc_m1 = roc_auc_score(y_te, p_m1) if len(np.unique(y_te)) > 1 else float("nan")
        results["M1"]["per_era_auc"][test_era] = round(auc_m1, 4)
        results["M1"]["oof_proba"][te_indices] = p_m1
        results["M1"]["oof_y"][te_indices] = y_te

        # ---- M2 ----
        clf_m2 = fit_m2(X_tr_f, y_tr, feature_cols)
        if clf_m2 is not None:
            p_m2 = predict_proba_pos(clf_m2, X_te_f)
        else:
            p_m2 = np.full(n_test, 0.5)
        auc_m2 = roc_auc_score(y_te, p_m2) if len(np.unique(y_te)) > 1 else float("nan")
        results["M2"]["per_era_auc"][test_era] = round(auc_m2, 4) if clf_m2 is not None else None
        results["M2"]["oof_proba"][te_indices] = p_m2
        results["M2"]["oof_y"][te_indices] = y_te

    # Compute mean AUCs
    for model_key in ["M0", "M1", "M2"]:
        era_aucs = results[model_key]["per_era_auc"]
        valid = [v for v in era_aucs.values() if v is not None and not math.isnan(float(v))]
        results[model_key]["mean_auc"] = round(float(np.mean(valid)), 4) if valid else float("nan")

    # Pooled OOF AUC (for reference)
    for model_key in ["M0", "M1", "M2"]:
        y_oof = results[model_key]["oof_y"]
        p_oof = results[model_key]["oof_proba"]
        covered = np.any(np.array([test_mask.sum() for test_mask in
                                    [all_era == e for e in eras]]) > 0)
        if covered and len(np.unique(y_oof)) > 1:
            results[model_key]["pooled_auc"] = round(float(roc_auc_score(y_oof, p_oof)), 4)
        else:
            results[model_key]["pooled_auc"] = float("nan")

    # ---- Shuffled-label null for chosen model (M1 or M2) ----
    # Choose model: higher mean OOS AUC between M1/M2 (§3 — choose BEFORE reading G-C tables)
    m1_auc = results["M1"]["mean_auc"]
    m2_auc = results["M2"]["mean_auc"]
    m2_valid = (
        results["M2"]["per_era_auc"].get(eras[0]) is not None
        and not any(v is None for v in results["M2"]["per_era_auc"].values())
    )
    if m2_valid and not math.isnan(m2_auc) and m2_auc > m1_auc:
        chosen_model = "M2"
        chosen_feature_cols = feature_cols
    else:
        chosen_model = "M1"
        chosen_feature_cols = feature_cols
    results["chosen_model"] = chosen_model
    log.info("Chosen model: %s (M1 mean_auc=%.4f, M2 mean_auc=%s)",
             chosen_model, m1_auc, m2_auc if m2_valid else "N/A")

    # ---- Shuffled-label null: within-era permutations through IDENTICAL pipeline ----
    log.info("Running %d shuffled-label nulls …", n_perms)
    chosen_auc = results[chosen_model]["mean_auc"]
    null_mean_aucs: list[float] = []
    for perm_i in range(n_perms):
        # Permute labels WITHIN each era separately (within-era permutation)
        y_perm = all_y.copy()
        for era in eras:
            era_idx = np.where(all_era == era)[0]
            if len(era_idx) > 1:
                shuffled = rng.permutation(y_perm[era_idx])
                y_perm[era_idx] = shuffled

        perm_era_aucs: list[float] = []
        for test_era in eras:
            test_mask = all_era == test_era
            n_test = int(test_mask.sum())
            if n_test == 0:
                continue
            test_era_start, test_era_end = get_era_date_bounds(test_era)
            train_dates_arr = pd.to_datetime(df["trigger_date"])
            purge_lo = test_era_start - pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)
            purge_hi = test_era_end + pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)
            purge_mask = (train_dates_arr >= purge_lo) & (train_dates_arr <= purge_hi)
            train_mask = (~test_mask) & (~purge_mask)

            if int(train_mask.sum()) < 10:
                continue

            X_tr = all_X[train_mask] if chosen_feature_cols == feature_cols else all_X_m0[train_mask]
            X_te = all_X[test_mask] if chosen_feature_cols == feature_cols else all_X_m0[test_mask]
            y_tr_perm = y_perm[train_mask]
            y_te = all_y[test_mask]

            X_tr_f, X_te_f, _ = _fill_nans_train_median(X_tr, X_te)

            if chosen_model == "M1":
                clf = fit_m1(X_tr_f, y_tr_perm)
            else:
                clf = fit_m2(X_tr_f, y_tr_perm, feature_cols)
                if clf is None:
                    clf_m1_fallback = fit_m1(X_tr_f, y_tr_perm)
                    clf = clf_m1_fallback

            p = predict_proba_pos(clf, X_te_f)
            if len(np.unique(y_te)) > 1:
                auc = float(roc_auc_score(y_te, p))
                perm_era_aucs.append(auc)

        if perm_era_aucs:
            null_mean_aucs.append(float(np.mean(perm_era_aucs)))

    null_p = float(np.mean([a >= chosen_auc for a in null_mean_aucs])) if null_mean_aucs else float("nan")
    results["null"]["mean_aucs"] = null_mean_aucs
    results["null"]["p_value"] = round(null_p, 4)
    results["null"]["null_mean_auc"] = round(float(np.mean(null_mean_aucs)), 4) if null_mean_aucs else float("nan")
    results["null"]["n_perms"] = len(null_mean_aucs)
    log.info("Null p=%.4f (chosen %s mean AUC=%.4f, null mean=%.4f, n_perms=%d)",
             null_p, chosen_model, chosen_auc,
             results["null"]["null_mean_auc"], len(null_mean_aucs))

    # ---- G-C thresholds (fit on train folds only — spec §5 / §7) ----
    # Per spec: "threshold fit on train folds only".  The previous implementation
    # computed percentiles of the pooled OOF (test) probas and applied them back
    # to those same OOF events — train/test contamination.
    #
    # Correct approach: for each fold, fit the chosen model on the train set,
    # compute train-fold predicted probas, derive the keep-top-X% threshold from
    # those train probas, then apply that threshold to the held-out (test) OOF
    # probas already accumulated in results[chosen_model]["oof_proba"].
    # Each OOF event is scored against the threshold from its own fold's train set.
    log.info("Computing G-C thresholds from per-fold train probabilities …")
    base_rate = float(all_y.mean())

    # We need per-event thresholds.  Accumulate: for each test event index,
    # store (threshold_40, threshold_60) derived from its fold's train probas.
    gc_threshold_40_per_event = np.full(len(df), float("nan"))
    gc_threshold_60_per_event = np.full(len(df), float("nan"))

    for test_era in eras:
        test_era_start, test_era_end = get_era_date_bounds(test_era)
        test_mask = all_era == test_era
        n_test = int(test_mask.sum())
        if n_test == 0:
            continue

        train_dates_gc = pd.to_datetime(df["trigger_date"])
        purge_lo = test_era_start - pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)
        purge_hi = test_era_end + pd.tseries.offsets.BusinessDay(n=LOEO_PURGE_SESSIONS)
        purge_mask = (train_dates_gc >= purge_lo) & (train_dates_gc <= purge_hi)
        train_mask = (~test_mask) & (~purge_mask)

        n_train = int(train_mask.sum())
        if n_train < 10:
            continue

        X_tr = all_X[train_mask]
        y_tr = all_y[train_mask]
        X_tr_f, _, _ = _fill_nans_train_median(X_tr, X_tr)  # medians from train only

        # Fit chosen model on this fold's train set
        if chosen_model == "M1":
            clf_gc = fit_m1(X_tr_f, y_tr)
        else:
            clf_gc = fit_m2(X_tr_f, y_tr, feature_cols)
            if clf_gc is None:
                clf_gc = fit_m1(X_tr_f, y_tr)

        # Train-fold predicted probas → derive thresholds
        p_train = predict_proba_pos(clf_gc, X_tr_f)
        thresh_40 = float(np.percentile(p_train, (1 - KEEP_TOP_40) * 100))
        thresh_60 = float(np.percentile(p_train, (1 - KEEP_TOP_60) * 100))

        # Assign per-event threshold for every event in this test fold
        te_indices_gc = np.where(test_mask)[0]
        gc_threshold_40_per_event[te_indices_gc] = thresh_40
        gc_threshold_60_per_event[te_indices_gc] = thresh_60

    p_chosen_oof = results[chosen_model]["oof_proba"]
    y_chosen_oof = results[chosen_model]["oof_y"]
    era_chosen_oof = all_era

    # Build G-C report using per-fold thresholds.
    # gc_report_per_fold_thresholds is a local variant that uses per-event thresholds.
    covered_mask = ~np.isnan(gc_threshold_40_per_event)
    if covered_mask.sum() == 0:
        log.error("G-C: no covered OOF events — all fold thresholds missing; G-C skipped")
        results["gc"] = {"chosen_model": chosen_model, "_gc_skipped": True}
    else:
        # Report average thresholds for display
        avg_thresh_40 = float(np.nanmean(gc_threshold_40_per_event))
        avg_thresh_60 = float(np.nanmean(gc_threshold_60_per_event))
        results["gc"] = gc_report_fold_thresholds(
            y_chosen_oof, p_chosen_oof, era_chosen_oof,
            gc_threshold_40_per_event, gc_threshold_60_per_event,
            base_rate, avg_thresh_40, avg_thresh_60,
        )
    results["gc"]["chosen_model"] = chosen_model

    # ---- Calibration tables ----
    results["M0"]["calibration"] = calibration_table(
        results["M0"]["oof_y"], results["M0"]["oof_proba"]
    ).to_dict(orient="records")
    results[chosen_model]["calibration_chosen"] = calibration_table(
        results[chosen_model]["oof_y"], results[chosen_model]["oof_proba"]
    ).to_dict(orient="records")

    # ---- Coefficient/importance table (single full-data fit) ----
    X_full_m0, _, _ = _fill_nans_train_median(all_X_m0, all_X_m0)
    clf_m0_full = fit_m0(X_full_m0, all_y)
    results["M0"]["coef"] = dict(zip(m0_features, clf_m0_full.coef_[0].tolist()))

    X_full, _, _ = _fill_nans_train_median(all_X, all_X)
    if chosen_model == "M1":
        clf_chosen_full = fit_m1(X_full, all_y)
        results[chosen_model]["coef"] = dict(zip(feature_cols, clf_chosen_full.coef_[0].tolist()))
    else:
        clf_chosen_full = fit_m2(X_full, all_y, feature_cols)
        if clf_chosen_full is not None:
            if hasattr(clf_chosen_full, "feature_importances_"):
                results[chosen_model]["importances"] = dict(
                    zip(feature_cols, clf_chosen_full.feature_importances_.tolist())
                )
            else:
                # HistGradientBoostingClassifier has no feature_importances_.
                # Use permutation_importance on full data (seed-fixed, for reproducibility).
                # This is NOT a CV-based estimate — it is a full-data diagnostic for the
                # report's mechanism-sign commentary, consistent with M1's full-data coef.
                try:
                    from sklearn.inspection import permutation_importance
                    perm_result = permutation_importance(
                        clf_chosen_full, X_full, all_y,
                        n_repeats=20, random_state=SEED, scoring="roc_auc",
                    )
                    results[chosen_model]["importances"] = dict(
                        zip(feature_cols, perm_result.importances_mean.tolist())
                    )
                    log.info(
                        "M2: permutation_importance computed (n_repeats=20, scoring=roc_auc)"
                    )
                except Exception as exc:
                    # Loud error — spec house law: loud errors, not silent omissions.
                    log.error(
                        "DELIVERABLE GAP: chosen model %s importance table could not be "
                        "computed (permutation_importance failed: %s). "
                        "Spec §6.1 requires coefficient/importance table — aborting.",
                        chosen_model, exc,
                    )
                    raise RuntimeError(
                        f"Chosen model {chosen_model} importance table unavailable: {exc}"
                    ) from exc

    return results


# ---------------------------------------------------------------------------
# Gate evaluations (spec §5)
# ---------------------------------------------------------------------------

def evaluate_gates(results: dict, base_rate: float) -> dict:
    """Evaluate pre-registered gates G-A, G-B, G-C per spec §5."""
    chosen = results["chosen_model"]
    chosen_mean_auc = results[chosen]["mean_auc"]
    m0_mean_auc = results["M0"]["mean_auc"]
    null_p = results["null"]["p_value"]

    # G-A: mean LOEO AUC > 0.5 AND null p < 0.05
    ga_auc_ok = (not math.isnan(chosen_mean_auc)) and (chosen_mean_auc > 0.5)
    ga_p_ok = (not math.isnan(null_p)) and (null_p < 0.05)
    ga_pass = ga_auc_ok and ga_p_ok

    # G-B: chosen model mean AUC >= M0 mean AUC + 0.03
    gb_pass = (not math.isnan(chosen_mean_auc)) and (not math.isnan(m0_mean_auc)) and \
               (chosen_mean_auc >= m0_mean_auc + 0.03)

    # G-C: reported (not gating) — lifted from results["gc"]
    gc_info = results.get("gc", {})

    gates = {
        "G-A": {
            "pass": ga_pass,
            "chosen_mean_auc": round(chosen_mean_auc, 4),
            "null_p": round(null_p, 4),
            "criterion": f"mean_auc > 0.5 ({ga_auc_ok}) AND null_p < 0.05 ({ga_p_ok})",
            "verdict": (
                f"PASS — mean AUC={chosen_mean_auc:.4f} > 0.5, null p={null_p:.4f} < 0.05"
                if ga_pass else
                f"FAIL — mean AUC={chosen_mean_auc:.4f}, null p={null_p:.4f} — "
                "NO ONSET-QUALITY SIGNAL AT n=350 — printed null"
            ),
        },
        "G-B": {
            "pass": gb_pass,
            "chosen_mean_auc": round(chosen_mean_auc, 4),
            "m0_mean_auc": round(m0_mean_auc, 4),
            "delta": round(chosen_mean_auc - m0_mean_auc, 4),
            "criterion": f"chosen mean AUC >= M0 mean AUC + 0.03",
            "verdict": (
                f"PASS — {chosen}={chosen_mean_auc:.4f} >= M0={m0_mean_auc:.4f}+0.03"
                if gb_pass else
                f"FAIL — {chosen}={chosen_mean_auc:.4f} < M0={m0_mean_auc:.4f}+0.03 "
                "(delta={:.4f}) — deliverable IS M0".format(chosen_mean_auc - m0_mean_auc)
            ),
        },
        "G-C": {
            "pass": None,  # reported, not gating
            "verdict": "REPORTED (not gating) — see G-C table below",
            "detail": gc_info,
        },
    }
    return gates


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(
    df: pd.DataFrame,
    results: dict,
    gates: dict,
    base_rate: float,
    out_dir: Path,
    label_mode: str = "pos63_goodset",
    report_filename: str = "W1_REPORT.md",
    smoke: bool = False,
) -> Path:
    """Write W1_REPORT.md (or W1B_REPORT.md) per spec §6.1.

    label_mode: 'pos63_goodset' (default) or 'reversion21'
    report_filename: output filename within out_dir
    smoke: if True, adds a SMOKE RUN note to the header
    """
    chosen = results["chosen_model"]
    lines: list[str] = []

    def h(text: str, level: int = 2) -> None:
        lines.append("#" * level + " " + text)
        lines.append("")

    def p(*args: str) -> None:
        lines.extend(args)
        lines.append("")

    is_w1b = label_mode == "reversion21"
    title = "OTA W1b — Onset-Quality Discriminator (reversion21 label) — Protocol Report" \
        if is_w1b else "OTA W1 — Onset-Quality Discriminator — Protocol Report"
    h(title, 1)

    header_lines = [
        "**Pre-registered spec:** research/oracle_asymmetry/W1_SPEC.md §Amendment log (W1b REGISTRATION)",
        f"**Seed:** {SEED}",
        f"**Date:** 2026-07-05",
        "",
        "> 'validated' is banned from this file. Every table carries n + base rate.",
        "> Gate verdicts are pre-bound: results are printed as-is.",
    ]
    if is_w1b:
        header_lines = [
            "**Pre-registered spec:** research/oracle_asymmetry/W1_SPEC.md §Amendment log (W1b REGISTRATION)",
            "**Label definition (reversion21):** absolute forward return at 21 sessions > 0 "
            "(next-bar fill per grading.fill_index; div-adjusted close; TIME-exit only; "
            "ABSOLUTE, not SPY-excess).",
            f"**Base rate (label=1 / n_labeled):** {base_rate:.4f} ({base_rate*100:.1f}%)",
            f"**Seed:** {SEED}",
            f"**Date:** 2026-07-05",
            "",
            "> 'validated' is banned from this file. Every table carries n + base rate.",
            "> Gate verdicts are pre-bound: results are printed as-is.",
            "> Pre-stated expectation: LOW — W1's AUCs were sub-coin-flip on primary and "
            "secondary labels; W1b exists because the label postdated the wave, not because "
            "a different result is expected.",
        ]
    if smoke:
        header_lines.append("> **SMOKE RUN**: permutation null skipped (0 perms). "
                            "AUCs are valid; null p-value is not computed.")
    p(*header_lines)

    # Determine the active label column for population reporting
    label_col = "label_reversion21" if is_w1b else "label_good"

    # ---- Population ----
    h("1. Population & Labels")
    n_total = len(df)
    n_good = int(df[label_col].sum())
    if is_w1b:
        pop_desc = (
            f"- Population: ep_onset_in × pos63 (matured, filtered to rows with ≥21 fwd bars) "
            f"— **n = {n_total}**"
        )
        label_desc = f"- label_reversion21=1 (abs fwd_ret_21 > 0): **n = {n_good}**"
    else:
        pop_desc = f"- Population: ep_onset_in × pos63 × matured — **n = {n_total}**"
        label_desc = f"- Good-set (CUSHIONED | CLEAN_LIFTOFF): **n = {n_good}**"
    p(
        pop_desc,
        label_desc,
        f"- Base rate: **{base_rate:.4f}** ({base_rate*100:.1f}%)",
        "",
        "| Era | n | n_good | base_rate |",
        "|-----|---|--------|-----------|",
    )
    for era_name, _, _ in _ERA_CUTS:
        era_df = df[df["era"] == era_name]
        n_e = len(era_df)
        ng_e = int(era_df[label_col].sum()) if label_col in era_df.columns else 0
        br_e = ng_e / n_e if n_e > 0 else float("nan")
        lines.append(f"| {era_name} | {n_e} | {ng_e} | {br_e:.4f} |")
    lines.append("")

    # ---- Feature table ----
    h("2. Feature Coverage (n = matured events with non-NaN)")
    lines.append("| Feature | Non-NaN | Mean | Std |")
    lines.append("|---------|---------|------|-----|")
    for fc in FEATURE_COLS:
        if fc in df.columns:
            col = df[fc].dropna()
            lines.append(
                f"| {fc} | {len(col)} | {float(col.mean()):.4f} | {float(col.std()):.4f} |"
            )
    lines.append("")

    # ---- LOEO per-era AUC table ----
    h("3. LOEO Per-Era AUC Table")
    era_names = [e for e, _, _ in _ERA_CUTS]
    header = "| Era | n_test | M0 AUC | M1 AUC | M2 AUC | Chosen |"
    sep    = "|-----|--------|--------|--------|--------|--------|"
    lines += [header, sep]
    for era in era_names:
        era_df = df[df["era"] == era]
        n_e = len(era_df)
        m0_a = results["M0"]["per_era_auc"].get(era, float("nan"))
        m1_a = results["M1"]["per_era_auc"].get(era, float("nan"))
        m2_a = results["M2"]["per_era_auc"].get(era, None)
        ch_a = results[chosen]["per_era_auc"].get(era, float("nan"))
        m2_str = f"{m2_a:.4f}" if m2_a is not None and not math.isnan(float(m2_a)) else "N/A"
        lines.append(
            f"| {era} | {n_e} | {m0_a:.4f} | {m1_a:.4f} | {m2_str} | {ch_a:.4f} |"
        )
    lines.append("")
    p(
        f"**M0 mean AUC: {results['M0']['mean_auc']:.4f}**",
        f"**M1 mean AUC: {results['M1']['mean_auc']:.4f}**",
        f"**M2 mean AUC: {results['M2']['mean_auc'] if results['M2']['per_era_auc'] else 'N/A'}**",
        f"**Chosen model: {chosen} (mean AUC = {results[chosen]['mean_auc']:.4f})**",
    )

    # ---- Shuffled-null ----
    h("4. Shuffled-Label Null Distribution")
    null_info = results["null"]
    p(
        f"- n_permutations: {null_info['n_perms']}",
        f"- null distribution mean AUC: {null_info['null_mean_auc']:.4f}",
        f"- observed {chosen} mean AUC: {results[chosen]['mean_auc']:.4f}",
        f"- p-value (fraction null >= observed): **{null_info['p_value']:.4f}**",
    )

    # ---- Gate verdicts ----
    h("5. Pre-Registered Gate Verdicts")
    for gate_name in ["G-A", "G-B", "G-C"]:
        g = gates[gate_name]
        verdict_str = g["verdict"]
        pass_str = "PASS" if g["pass"] else ("FAIL" if g["pass"] is not None else "REPORTED")
        lines.append(f"### {gate_name}: {pass_str}")
        lines.append(f"- {verdict_str}")
        lines.append("")

    # G-C tables
    h("5.1 G-C Lift Tables (reported, not gating)", 3)
    gc = results.get("gc", {})
    for pct_label in ["40", "60"]:
        pooled = gc.get(f"pooled_{pct_label}", {})
        p(
            f"**Keep-top-{pct_label}% threshold = {pooled.get('threshold', 'N/A')}**",
            f"Pooled: n_kept={pooled.get('n_kept','?')}/{pooled.get('n_total','?')}, "
            f"good_rate={pooled.get('good_rate','?')}, base_rate={pooled.get('base_rate','?')}, "
            f"lift={pooled.get('lift','?')}, Wilson 95% LB={pooled.get('wilson_lb_95','?')}",
        )
        per_era = gc.get(f"per_era_{pct_label}", {})
        lines.append(f"| Era | n_era | n_kept | good_rate | base_rate | lift | Wilson LB |")
        lines.append(f"|-----|-------|--------|-----------|-----------|------|-----------|")
        for era in era_names:
            er = per_era.get(era, {})
            lines.append(
                f"| {era} | {er.get('n_era','?')} | {er.get('n_kept','?')} | "
                f"{er.get('good_rate','?')} | {er.get('base_rate','?')} | "
                f"{er.get('lift','?')} | {er.get('wilson_lb_95','?')} |"
            )
        lines.append("")

    # ---- Calibration ----
    h("6. Calibration (Reliability Table, 5 bins)")
    for model_key, cal_key in [("M0", "calibration"), (chosen, "calibration_chosen")]:
        cal = results.get(model_key, {}).get(cal_key)
        if cal:
            lines.append(f"**{model_key}**")
            lines.append("| Bin | n | mean_pred | actual_rate |")
            lines.append("|-----|---|-----------|-------------|")
            for row in cal:
                lines.append(
                    f"| [{row['bin_lo']:.2f}, {row['bin_hi']:.2f}) | {row['n']} | "
                    f"{row['mean_pred']} | {row['actual_rate']} |"
                )
            lines.append("")

    # ---- Coefficients / Importances ----
    h("7. Coefficients / Feature Importances (full-data fit)")
    p(
        "> Sign commentary: positive coefficient → higher feature value → "
        "higher predicted probability of good outcome (CUSHIONED/CLEAN_LIFTOFF).",
        "> Mechanism-implied signs are noted in brackets.",
    )

    m0_coef = results["M0"].get("coef", {})
    if m0_coef:
        lines.append("**M0 coefficients (accel_z_5d, vix_pctile):**")
        lines.append("| Feature | Coef | Mechanism sign | Comment |")
        lines.append("|---------|------|----------------|---------|")
        sign_comments = {
            "accel_z_5d": ("+", "sustained acceleration favors conversion"),
            "vix_pctile": ("-", "high VIX → macro headwind → fewer clean lifts (expected neg)"),
        }
        for feat, coef in m0_coef.items():
            exp_sign, comment = sign_comments.get(feat, ("?", ""))
            actual_sign = "+" if coef >= 0 else "-"
            match = "ok" if actual_sign == exp_sign else "REVERSED"
            lines.append(f"| {feat} | {coef:.4f} | {exp_sign} | {comment} ({match}) |")
        lines.append("")

    chosen_coef = results.get(chosen, {}).get("coef", {})
    chosen_imp = results.get(chosen, {}).get("importances", {})
    if chosen_coef:
        lines.append(f"**{chosen} L2 logistic coefficients (all 16 features):**")
        lines.append("| Feature | Coef | Mechanism sign | Comment |")
        lines.append("|---------|------|----------------|---------|")
        sign_comments_full = {
            "accel_z": ("+", "onset acceleration signal"),
            "accel_z_5d": ("+", "sustained 5-day acceleration"),
            "accel": ("+", "vel_1w - vel_3m momentum"),
            "rs_pctile_252d": ("+", "relative strength vs peers"),
            "persistence": ("+", "trend persistence"),
            "washout_w": ("+", "washout = fuel for recovery"),
            "stochrsi_w_k": ("-", "lower stoch = more room to run"),
            "stochrsi_kd_diff": ("+", "K crossing D = early signal"),
            "vix_pctile": ("-", "high VIX = macro headwind"),
            "spy_above_200d": ("+", "bull tape supports rotation"),
            "tlt_ret_10d": ("+", "TLT rising = bonds supporting risk, or flight-to-quality easing"),
            "flow_opp_out_20s": ("+", "opposite-complex outflows = capital must rotate IN"),
            "flow_same_out_20s": ("-", "same-complex outflows = sector-wide pressure"),
            "active_in_episodes": ("-", "crowded = diminishing marginal returns"),
            "prev_same_node_outcome": ("+", "node momentum in rotation quality"),
            "sigma20": ("-", "higher vol at onset = noisier signal"),
        }
        for feat, coef in chosen_coef.items():
            exp_sign, comment = sign_comments_full.get(feat, ("?", ""))
            actual_sign = "+" if coef >= 0 else "-"
            match = "ok" if actual_sign == exp_sign else "REVERSED"
            lines.append(f"| {feat} | {coef:.4f} | {exp_sign} | {comment} ({match}) |")
        lines.append("")
    elif chosen_imp:
        lines.append(f"**{chosen} feature importances (HGBC):**")
        lines.append("| Feature | Importance | Mechanism sign | Comment |")
        lines.append("|---------|-----------|----------------|---------|")
        sorted_imp = sorted(chosen_imp.items(), key=lambda x: -x[1])
        sign_comments_full = {
            "accel_z": ("+", "onset acceleration signal"),
            "accel_z_5d": ("+", "sustained 5-day acceleration"),
            "accel": ("+", "vel_1w - vel_3m momentum"),
            "rs_pctile_252d": ("+", "relative strength vs peers"),
            "persistence": ("+", "trend persistence"),
            "washout_w": ("+", "washout = fuel for recovery"),
            "stochrsi_w_k": ("-", "lower stoch = more room to run"),
            "stochrsi_kd_diff": ("+", "K crossing D = early signal"),
            "vix_pctile": ("-", "high VIX = macro headwind"),
            "spy_above_200d": ("+", "bull tape supports rotation"),
            "tlt_ret_10d": ("+", "TLT rising bonds supporting risk"),
            "flow_opp_out_20s": ("+", "opposite-complex outflows = forced rotation IN"),
            "flow_same_out_20s": ("-", "same-complex outflows = sector-wide pressure"),
            "active_in_episodes": ("-", "crowded = diminishing marginal returns"),
            "prev_same_node_outcome": ("+", "node momentum in rotation quality"),
            "sigma20": ("-", "higher vol at onset = noisier signal"),
        }
        for feat, imp in sorted_imp:
            exp_sign, comment = sign_comments_full.get(feat, ("?", ""))
            lines.append(f"| {feat} | {imp:.4f} | {exp_sign} | {comment} |")
        lines.append("")

    # ---- Secondary labels appendix ----
    h("Appendix A: Secondary Labels (reported, never gate-bearing)")
    # rot21 good-set
    if "label_rot21" in df.columns:
        rot21_df = df.dropna(subset=["label_rot21"])
        n_r21 = len(rot21_df)
        n_r21_good = int(rot21_df["label_rot21"].sum())
        p(
            f"**rot21 good-set:** n={n_r21}, good_rate={n_r21_good/n_r21:.4f}" if n_r21 > 0 else "rot21 label: n=0",
        )
    # false-start-5d
    if "label_false_start_5d" in df.columns:
        fs_df = df.dropna(subset=["label_false_start_5d"])
        n_fs = len(fs_df)
        n_fs_pos = int(fs_df["label_false_start_5d"].sum())
        p(
            f"**False-start 5d:** n={n_fs}, false_start_rate={n_fs_pos/n_fs:.4f}" if n_fs > 0 else "false_start_5d: n=0",
        )

    out_path = out_dir / report_filename
    out_path.write_text("\n".join(lines) + "\n")
    log.info("Report written to %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Reversion-21 label computation (W1b registration)
# ---------------------------------------------------------------------------

def compute_reversion21_labels(
    pop: pd.DataFrame,
    data_dir: Path,
) -> pd.DataFrame:
    """Compute the reversion21 primary label for W1b.

    Label definition (W1_SPEC.md §Amendment log, W1b REGISTRATION):
      label_reversion21 = 1.0 if absolute forward return at 21 sessions > 0, else 0.0.
      - Fill convention: next bar strictly after trigger_date via grading.fill_index
        (i.e. iloc position = first bar strictly after trigger_date).
      - fwd_ret_21 = close[fill + 21] / close[fill] − 1  (div-adjusted close).
      - TIME-exit only — no barriers, no SPY excess, ABSOLUTE (not SPY-excess).
      - Rows without 21 forward bars after fill are DROPPED from the labeled set
        (counted and printed).

    Returns a copy of pop filtered to rows with valid labels, with 'label_reversion21'
    column added (float 0.0 or 1.0).

    Raises FileNotFoundError if any node's yahoo parquet is missing.
    """
    from engine.grading import fill_index as _fill_index  # type: ignore

    yahoo_dir = data_dir / "yahoo"
    nodes = pop["node"].unique()

    # Pre-load close series for all nodes
    close_by_node: dict[str, pd.Series] = {}
    for node in nodes:
        ypath = yahoo_dir / f"{node}.parquet"
        if not ypath.exists():
            raise FileNotFoundError(
                f"reversion21: yahoo parquet missing for node {node!r}: {ypath}"
            )
        df_y = pd.read_parquet(ypath)
        # close column is div-adjusted per memory note [yahoo close is total return]
        close_s = df_y["close"].copy()
        close_s.index = pd.to_datetime(close_s.index)
        close_s = close_s.sort_index()
        close_by_node[node] = close_s

    results = []
    n_dropped_no_fill = 0
    n_dropped_no_fwd = 0
    for _, ev in pop.iterrows():
        node = str(ev["node"])
        trigger = pd.Timestamp(ev["trigger_date"])
        close_s = close_by_node.get(node)
        if close_s is None:
            n_dropped_no_fill += 1
            continue

        fill = _fill_index(close_s, trigger)
        if fill is None:
            # No next bar after trigger
            n_dropped_no_fill += 1
            continue

        # Need fill + 21 to be a valid index (0-based iloc)
        if fill + 21 >= len(close_s):
            n_dropped_no_fwd += 1
            continue

        entry_price = float(close_s.iloc[fill])
        exit_price = float(close_s.iloc[fill + 21])
        if not (np.isfinite(entry_price) and np.isfinite(exit_price)
                and entry_price > 0 and exit_price > 0):
            n_dropped_no_fwd += 1
            continue

        fwd_ret_21 = exit_price / entry_price - 1.0
        label = 1.0 if fwd_ret_21 > 0 else 0.0
        results.append({**ev.to_dict(), "label_reversion21": label})

    n_total = len(pop)
    n_labeled = len(results)
    n_dropped = n_total - n_labeled
    log.info(
        "reversion21 labels: n_total=%d, n_labeled=%d, n_dropped=%d "
        "(no_fill=%d, no_21_fwd_bars=%d)",
        n_total, n_labeled, n_dropped, n_dropped_no_fill, n_dropped_no_fwd,
    )
    print(
        f"\nreversion21 label summary: n_labeled={n_labeled} / n_total={n_total}  "
        f"dropped={n_dropped} (no_fill={n_dropped_no_fill}, "
        f"no_21_fwd_bars={n_dropped_no_fwd})"
    )
    if n_labeled == 0:
        raise RuntimeError("reversion21: zero rows labeled — check yahoo data and trigger dates")

    labeled_df = pd.DataFrame(results)
    labeled_df["trigger_date"] = pd.to_datetime(labeled_df["trigger_date"])
    return labeled_df


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(
    data_dir: Optional[Path] = None,
    label: str = "pos63_goodset",
    smoke: bool = False,
) -> None:
    if data_dir is None:
        data_dir = ROOT / "data"

    data_dir = Path(data_dir)
    log.info("Data dir: %s  label=%s  smoke=%s", data_dir, label, smoke)

    valid_labels = ("pos63_goodset", "reversion21")
    if label not in valid_labels:
        raise ValueError(f"--label must be one of {valid_labels}, got {label!r}")

    # ---- 1. Load population from committed W0_2 CSV ----
    w0_csv = ROOT / "research" / "oracle_asymmetry" / "W0_2_events_graded.csv"
    if not w0_csv.exists():
        raise FileNotFoundError(f"W0_2 CSV not found: {w0_csv}")

    w0_all = pd.read_csv(w0_csv)
    # Filter to ep_onset_in rows
    ep_onset_rows = w0_all[w0_all["family"] == "ep_onset_in"].copy()
    n_ep_onset_total = len(ep_onset_rows)
    log.info("W0_2 ep_onset_in rows total: %d", n_ep_onset_total)

    # pos63 only — spec §1 asserts 357 pos63 rows
    pos63 = ep_onset_rows[ep_onset_rows["parameterization"] == "pos63"].copy()
    n_pos63 = len(pos63)
    log.info("pos63 rows: %d (expected %d)", n_pos63, W0_CSV_EP_ONSET_IN_ROWS_POS63)
    if n_pos63 != W0_CSV_EP_ONSET_IN_ROWS_POS63:
        raise AssertionError(
            f"ABORT: ep_onset_in pos63 count mismatch — got {n_pos63}, "
            f"expected {W0_CSV_EP_ONSET_IN_ROWS_POS63}. "
            "Labels must not drift from committed CSV."
        )

    # Matured only (spec §1: matured rows only)
    pop = pos63[pos63["state_immature"] == False].copy()  # noqa: E712
    n_pop = len(pop)
    log.info("Matured pos63 rows: %d", n_pop)

    # Labels (from committed CSV — cannot drift)
    pop["label_good"] = pop["state"].isin(GOOD_STATES).astype(int)

    # Secondary labels (always computed for pos63_goodset mode; W1b omits these)
    if label == "pos63_goodset":
        # rot21: CUSHIONED | CLEAN_LIFTOFF under rot21 parameterization
        rot21 = ep_onset_rows[ep_onset_rows["parameterization"] == "rot21"].copy()
        rot21_matured = rot21[rot21["state_immature"] == False].copy()
        rot21_good = rot21_matured.set_index(["node", "trigger_date"])["state"].isin(GOOD_STATES)
        pop_idx = pop.set_index(["node", "trigger_date"]).index
        pop["label_rot21"] = pop_idx.map(
            lambda x: 1 if rot21_good.get(x, False) else 0
        )
        # false_start_5d: direction-adjusted 5d outcome < 0
        pop["label_false_start_5d"] = (pop["fwd_ret_5"] < 0).astype(int)

    # Era assignment (done pre-feature-computation so reversion21 filtering preserves era col)
    pop["trigger_date"] = pd.to_datetime(pop["trigger_date"])
    pop["era"] = pop["trigger_date"].apply(assign_era)
    n_unassigned = pop["era"].isna().sum()
    if n_unassigned > 0:
        log.warning("%d events have no era assignment — dropping", n_unassigned)
        pop = pop.dropna(subset=["era"])

    # ---- 2. Load panel and episodes ----
    panel_path = data_dir / "oracle" / "panel_s.parquet"
    eps_path = data_dir / "oracle" / "episodes_s.parquet"
    if not panel_path.exists():
        raise FileNotFoundError(f"panel_s.parquet not found: {panel_path}")
    if not eps_path.exists():
        raise FileNotFoundError(f"episodes_s.parquet not found: {eps_path}")

    log.info("Loading panel_s …")
    panel = pd.read_parquet(panel_path)
    log.info("Loading episodes_s …")
    episodes_s = pd.read_parquet(eps_path)

    # ---- 3. Load rotation_groups from WORKTREE (not MAIN) ----
    rg_path = ROOT / "data" / "oracle" / "rotation_groups.json"
    if not rg_path.exists():
        raise FileNotFoundError(f"rotation_groups.json not found: {rg_path}")
    rotation_groups = json.loads(rg_path.read_text())
    etf_complex_map = build_etf_complex_map(rotation_groups)
    opposite_risk_map = build_opposite_risk_map(rotation_groups)
    log.info("ETF complex map: %s", etf_complex_map)

    # ---- 3b. Build W0 state lookup for F15 ----
    w0_state_lookup: dict = {}
    for _, r in pos63.iterrows():
        onset_key = str(pd.Timestamp(r["trigger_date"]).date())
        label_val = 1.0 if r["state"] in GOOD_STATES else 0.0
        w0_state_lookup[(str(r["node"]), onset_key)] = label_val
    log.info("W0 state lookup built: %d entries", len(w0_state_lookup))

    # ---- 4. For reversion21 mode: compute labels BEFORE features so we only
    #         compute features for the labeled subset ----
    if label == "reversion21":
        log.info("Computing reversion21 labels from yahoo div-adjusted close …")
        pop = compute_reversion21_labels(pop, data_dir)
        # Era must be re-derived after filtering (drop events that lost era in filter)
        pop["era"] = pop["trigger_date"].apply(assign_era)
        pop = pop.dropna(subset=["era"])
        base_rate = float(pop["label_reversion21"].mean())
        log.info(
            "reversion21 base rate: %.4f (n_good=%d / n=%d)",
            base_rate, int(pop["label_reversion21"].sum()), len(pop),
        )
        active_label_col = "label_reversion21"
        feat_csv_name = "W1B_features.csv"
        report_filename = "W1B_REPORT.md"
        run_label = "W1b"
    else:
        base_rate = float(pop["label_good"].mean())
        log.info("Base rate (CUSHIONED|CLEAN_LIFTOFF): %.4f (n_good=%d / n=%d)",
                 base_rate, int(pop["label_good"].sum()), n_pop)
        active_label_col = "label_good"
        feat_csv_name = "W1_features.csv"
        report_filename = "W1_REPORT.md"
        run_label = "W1"

    # ---- 5. Compute features ----
    df_feat = compute_features(pop, panel, episodes_s, etf_complex_map, opposite_risk_map,
                               w0_state_lookup=w0_state_lookup)

    # ---- 6. Emit features CSV ----
    out_dir = ROOT / "research" / "oracle_asymmetry"
    if label == "reversion21":
        _meta_cols = ["family", "node", "trigger_date", "era", "state", "label_reversion21"]
    else:
        _meta_cols = ["family", "node", "trigger_date", "era", "state",
                      "label_good", "label_rot21", "label_false_start_5d"]
    _all_out = _meta_cols + FEATURE_COLS
    _seen: set = set()
    feat_out_cols = []
    for c in _all_out:
        if c not in _seen:
            _seen.add(c)
            feat_out_cols.append(c)
    feat_out_cols = [c for c in feat_out_cols if c in df_feat.columns]
    feat_csv = out_dir / feat_csv_name
    df_feat[feat_out_cols].to_csv(feat_csv, index=False)
    log.info("%s written: %d rows × %d cols", feat_csv_name, len(df_feat), len(feat_out_cols))

    # ---- 7. Run LOEO protocol ----
    log.info("Starting LOEO protocol (label=%s, smoke=%s) …", label, smoke)
    results = run_loeo(df_feat, active_label_col, FEATURE_COLS, M0_FEATURES, smoke=smoke)

    # ---- 8. Evaluate gates ----
    gates = evaluate_gates(results, base_rate)

    # ---- 9. Print gate verdicts to stdout (loud) ----
    run_hdr = f"{run_label} GATE VERDICTS (label={label})"
    if smoke:
        run_hdr += " [SMOKE RUN — 0 perms]"
    print("\n" + "=" * 70)
    print(run_hdr)
    print("=" * 70)
    chosen = results["chosen_model"]
    for era in [e for e, _, _ in _ERA_CUTS]:
        auc = results[chosen]["per_era_auc"].get(era, float("nan"))
        print(f"  {era}: {chosen} AUC = {auc:.4f}" if auc == auc else f"  {era}: {chosen} AUC = N/A")
    print(f"\n  {chosen} MEAN AUC: {results[chosen]['mean_auc']:.4f}")
    print(f"  M0 MEAN AUC:     {results['M0']['mean_auc']:.4f}")
    print(f"  Label base rate: {base_rate:.4f}")
    null_p = results["null"]["p_value"]
    if smoke:
        print("  Null p-value:    N/A (smoke mode — 0 perms)")
    else:
        print(f"  Null p-value:    {null_p:.4f}")
    print("")
    for gate_name in ["G-A", "G-B", "G-C"]:
        g = gates[gate_name]
        print(f"{gate_name}: {g['verdict']}")
    print("=" * 70 + "\n")

    # ---- 10. Write report ----
    write_report(
        df_feat, results, gates, base_rate, out_dir,
        label_mode=label,
        report_filename=report_filename,
        smoke=smoke,
    )

    log.info("%s complete.", run_label)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OTA W1/W1b onset-quality discriminator")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Path to data/ directory (default: <repo-root>/data/)",
    )
    parser.add_argument(
        "--label",
        choices=["pos63_goodset", "reversion21"],
        default="pos63_goodset",
        help=(
            "Primary label to use. "
            "'pos63_goodset' (default) = CUSHIONED|CLEAN_LIFTOFF from W0.2 CSV (byte-identical "
            "to original W1 behavior). "
            "'reversion21' = absolute forward return at 21 sessions > 0 (W1b registration); "
            "outputs W1B_features.csv + W1B_REPORT.md."
        ),
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        default=False,
        help=(
            "Smoke-test mode: skip the 200-permutation null loop (0 perms). "
            "LOEO AUCs are computed normally; null p-value is not reported. "
            "Use to verify the end-to-end path without the long permutation run."
        ),
    )
    args = parser.parse_args()
    main(data_dir=args.data_dir, label=args.label, smoke=args.smoke)
