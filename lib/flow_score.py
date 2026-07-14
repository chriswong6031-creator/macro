"""lib/flow_score.py — FS-4 flow-score utility library.

LAZY SKLEARN IMPORT LAW (FS-R7):
  sklearn is NEVER imported at module level. Every sklearn-dependent function
  imports it locally (inside the function body). Importing this module must
  succeed even when sklearn is not installed — engine modules that import from
  lib/ run on the nightly render path where sklearn is absent.

PRE-GATE LAW (amendment §9 / FS-R3):
  The score returned by score_events() is display-only. It may not feed any
  ranker, sizer, sorter, or gate. score_calibrated is null unless the artifact
  manifest marks deployable=True, and even then the gate.json scored field
  controls whether it surfaces at all.

STATUS ENUM (scores.parquet / frozen contract):
  scored | no_model | not_deployable | prefiltered_index_root |
  bucket_unmapped | error
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── frozen status enum (scores.parquet contract) ──────────────────────────────
STATUS_SCORED                = "scored"
STATUS_NO_MODEL              = "no_model"
STATUS_NOT_DEPLOYABLE        = "not_deployable"
STATUS_PREFILTERED_INDEX_ROOT = "prefiltered_index_root"
STATUS_BUCKET_UNMAPPED       = "bucket_unmapped"
STATUS_ERROR                 = "error"

# ── model bucket map (mirrors config/flow_score.yml — kept in sync) ──────────
# Authoritative source: collectors/flow_signals.py dte_bucket derivation.
# gate.json shows live dte_bucket values: 0d, 1_7d, 8_30d, 31_90d, 90p.
_BUCKET_MAP: dict[str, str] = {
    "0d":    "0_7",
    "1_7d":  "0_7",
    "8_30d": "8_90",
    "31_90d": "8_90",
    "90p":   "90p",
}


def build_interaction_features(
    df: pd.DataFrame,
    feature_columns: list[str],
    dte_interaction_enabled: bool = False,
) -> pd.DataFrame:
    """Build a feature DataFrame including any configured interaction terms.

    Called by BOTH the trainer (_build_features) and the scorer (score_events)
    so that dte_X_premium_z is computed identically at train and serve time.

    Amendment §2.1 / FS4-01: the 8_90 model is trained with dte_X_premium_z =
    dte × premium_z.  If score_events falls back to raw column lookup, this
    feature is NaN at serve time, producing corrupted feature vectors.

    Parameters
    ----------
    df : DataFrame
        Input data.  For serving, this is the ledger slice for the bucket.
    feature_columns : list[str]
        Ordered list of feature column names (from manifest cv_params).
    dte_interaction_enabled : bool
        Whether dte_X_premium_z should be computed.  Keyed from
        manifest cv_params.dte_interaction_enabled.

    Returns
    -------
    DataFrame with exactly the columns in feature_columns, in that order.
    Missing raw columns → NaN; dte_X_premium_z computed when enabled.
    """
    X = pd.DataFrame(index=df.index)
    for col in feature_columns:
        if col == "dte_X_premium_z" and dte_interaction_enabled:
            if "dte" in df.columns and "premium_z" in df.columns:
                X[col] = pd.to_numeric(df["dte"], errors="coerce") * pd.to_numeric(
                    df["premium_z"], errors="coerce"
                )
            else:
                X[col] = float("nan")
        elif col in df.columns:
            X[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            X[col] = float("nan")
    return X


def map_model_bucket(dte_bucket: str | None) -> str | None:
    """Map a ledger dte_bucket value to a model bucket string.

    Returns None when the dte_bucket is not recognised (bucket_unmapped).
    Covers all live values (0d, 1_7d, 8_30d, 31_90d, 90p) seen in gate.json.

    >>> map_model_bucket("8_30d")
    '8_90'
    >>> map_model_bucket("unknown") is None
    True
    """
    if dte_bucket is None:
        return None
    return _BUCKET_MAP.get(str(dte_bucket))


# ── sha256 helper ──────────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    """Return lowercase hex SHA-256 of a file's contents."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── ECE ───────────────────────────────────────────────────────────────────────

def ece(
    pred: np.ndarray | list,
    y: np.ndarray | list,
    n_bins: int = 10,
    equal_mass: bool = True,
) -> float:
    """Expected Calibration Error (ECE) over n_bins equal-mass bins.

    Amendment §5: 10 equal-mass bins; ECE < 0.05 → deployable per bucket.

    Parameters
    ----------
    pred : array-like of float
        Predicted probabilities in [0, 1].
    y : array-like of float
        Binary outcomes (0.0 or 1.0).
    n_bins : int
        Number of bins (default 10).
    equal_mass : bool
        If True (default), bins are equal-mass (quantile-based). If False,
        uses equal-width bins in [0, 1].

    Returns
    -------
    float: ECE value (0.0 = perfect calibration).

    Notes
    -----
    Empty bins are skipped in the weighted average (not added as 0 contribution).
    This is the standard formula: ECE = Σ_b (|B_b| / n) * |acc(B_b) - conf(B_b)|
    """
    pred = np.asarray(pred, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(pred) & np.isfinite(y)
    pred, y = pred[mask], y[mask]
    n = len(pred)
    if n == 0:
        return float("nan")

    if equal_mass:
        # quantile bin edges so each bin has ~n/n_bins observations
        quantiles = np.linspace(0.0, 1.0, n_bins + 1)
        bin_edges = np.quantile(pred, quantiles)
        # deduplicate edges (can happen on constant predictions)
        bin_edges = np.unique(bin_edges)
        if len(bin_edges) < 2:
            # all predictions are identical
            return float(abs(float(y.mean()) - float(pred.mean())))
        bin_indices = np.digitize(pred, bin_edges[1:-1])
    else:
        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
        bin_indices = np.digitize(pred, bin_edges[1:-1])

    total_err = 0.0
    for b in np.unique(bin_indices):
        mask_b = bin_indices == b
        n_b = int(mask_b.sum())
        if n_b == 0:
            continue
        conf_b = float(pred[mask_b].mean())
        acc_b = float(y[mask_b].mean())
        total_err += (n_b / n) * abs(acc_b - conf_b)
    return float(total_err)


# ── Brier score ───────────────────────────────────────────────────────────────

def brier(pred: np.ndarray | list, y: np.ndarray | list) -> float:
    """Brier score: mean squared error of predicted probabilities vs outcomes.

    Lower is better. The no-skill (base-rate) Brier = p_bar * (1 - p_bar)
    where p_bar = mean(y). A model must beat base_rate Brier to be deployable
    (amendment §5).

    Returns float (NaN on empty/all-NaN input).
    """
    pred = np.asarray(pred, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(pred) & np.isfinite(y)
    pred, y = pred[mask], y[mask]
    if len(pred) == 0:
        return float("nan")
    return float(np.mean((pred - y) ** 2))


# ── reliability table ─────────────────────────────────────────────────────────

def reliability_table(
    pred: np.ndarray | list,
    y: np.ndarray | list,
    weights: np.ndarray | list | None = None,
    n_bins: int = 10,
    equal_mass: bool = True,
) -> list[dict[str, Any]]:
    """Compute a reliability (calibration) table for the given predictions.

    Amendment §5: bins must be equal-mass (equal_mass=True default).
    Each bin row carries n_eff (effective n from weights) so ERA-SPARSE
    bins are identifiable (n_eff < n_floor → ERA-SPARSE, not smoothed).

    Parameters
    ----------
    pred : array-like of float
        Predicted probabilities.
    y : array-like of float
        Binary outcomes.
    weights : array-like of float or None
        Uniqueness weights (from uniqueness_weights()). If None, uniform.
    n_bins : int
        Number of bins.
    equal_mass : bool
        Quantile-based bins (default True, as amendment requires).

    Returns
    -------
    list of dict with keys:
        bin_lo, bin_hi: prediction range for the bin
        pred_mean: mean predicted probability in the bin
        emp_rate: weighted empirical outcome rate
        n_eff: sum of weights (effective n)
    Bins with zero weight are omitted.
    """
    pred = np.asarray(pred, dtype=float)
    y = np.asarray(y, dtype=float)
    if weights is None:
        w = np.ones(len(pred), dtype=float)
    else:
        w = np.asarray(weights, dtype=float)

    mask = np.isfinite(pred) & np.isfinite(y) & np.isfinite(w)
    pred, y, w = pred[mask], y[mask], w[mask]
    n = len(pred)
    if n == 0:
        return []

    if equal_mass:
        quantiles = np.linspace(0.0, 1.0, n_bins + 1)
        bin_edges = np.quantile(pred, quantiles)
        bin_edges = np.unique(bin_edges)
        if len(bin_edges) < 2:
            # Constant predictions — one bin
            return [{
                "bin_lo": float(pred.min()),
                "bin_hi": float(pred.max()),
                "pred_mean": float(pred.mean()),
                "emp_rate": float(np.average(y, weights=w)) if w.sum() > 0 else float("nan"),
                "n_eff": float(w.sum()),
            }]
        bin_indices = np.digitize(pred, bin_edges[1:-1])
    else:
        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
        bin_indices = np.digitize(pred, bin_edges[1:-1])

    rows: list[dict[str, Any]] = []
    unique_bins = np.unique(bin_indices)
    for b in unique_bins:
        mask_b = bin_indices == b
        w_b = w[mask_b]
        w_sum = float(w_b.sum())
        if w_sum == 0:
            continue
        p_b = pred[mask_b]
        y_b = y[mask_b]
        # Bin edges
        b_lo = float(p_b.min())
        b_hi = float(p_b.max())
        rows.append({
            "bin_lo": b_lo,
            "bin_hi": b_hi,
            "pred_mean": float(np.average(p_b, weights=w_b)),
            "emp_rate": float(np.average(y_b, weights=w_b)),
            "n_eff": w_sum,
        })
    return rows


def is_reliability_monotone(table: list[dict[str, Any]], tol: float = 1e-3) -> bool:
    """Check that the reliability table is monotone non-decreasing within tolerance.

    Amendment §5: non-monotone reliability curve = kill trigger.
    Returns True if monotone (pred_mean non-decreasing with emp_rate, approximately).

    Strategy: check that emp_rate is non-decreasing as pred_mean increases,
    allowing tolerance `tol` for near-flat bins.
    """
    if len(table) < 2:
        return True
    # Sort by pred_mean (should already be, but sort to be safe)
    rows = sorted(table, key=lambda r: r["pred_mean"])
    rates = [r["emp_rate"] for r in rows]
    for i in range(1, len(rates)):
        if rates[i] < rates[i - 1] - tol:
            return False
    return True


# ── uniqueness weights (amendment §4.4) ───────────────────────────────────────

def uniqueness_weights(
    events_df: pd.DataFrame,
    horizon_days: int,
    date_col: str = "session_date",
    underlying_col: str = "root",
    event_id_col: str = "event_id",
) -> pd.Series:
    """Compute uniqueness sample weights for overlapping-label events.

    Amendment §4.4 — full spec including (session, underlying) concurrency collapse:

    For each event i in bucket b with horizon H:
      1. Label window W_i = [t_i, t_i + H_b].
      2. For each day t in W_i, c_t = count of events whose label window covers t.
         BUT: within a (session_date, underlying) group, all events share a common
         outcome shock (amendment §4.4 "same-session down-weight"). The c_t count
         uses the (session, underlying)-collapsed concurrency — a thousand SPY prints
         on one session count as ONE event for concurrency purposes.
      3. Average uniqueness u_i = mean over t in W_i of (1 / c_t).
      4. Weight w_i = u_i. Returned weights are NOT renormalized here so the
         caller can compute effective N = Σ w_i and apply their own normalization.

    Parameters
    ----------
    events_df : DataFrame
        Must contain date_col (str YYYY-MM-DD), underlying_col, event_id_col.
        date_col must be parseable as dates.
    horizon_days : int
        Label horizon in trading days (used as calendar days here for simplicity;
        the purge/embargo in CV also uses calendar days per amendment).
    date_col : str
        Column name for the session/event date.
    underlying_col : str
        Column name for the underlying (root ticker).
    event_id_col : str
        Column name for the event identifier.

    Returns
    -------
    pd.Series indexed by event_id_col containing uniqueness weights in (0, 1].
    Events absent from the DataFrame get weight NaN.

    Notes
    -----
    (session, underlying) concurrency collapse: for the purposes of counting c_t,
    we treat a (session_date, underlying) pair as ONE unit. This means if 1000 SPY
    events land on the same session, they contribute c_t = 1 for that session's
    label windows (not 1000). Each of those 1000 events still gets its own weight,
    but their average uniqueness is computed against the collapsed concurrency.
    """
    if events_df.empty:
        return pd.Series(dtype=float)

    df = events_df[[event_id_col, date_col, underlying_col]].copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.date

    # Step 1: Collapse to unique (session_date, underlying) units for concurrency.
    # Each such unit represents ONE independent outcome-contributing entity per day.
    # Amendment §4.4: a thousand SPY prints on one session count as ONE unit for
    # concurrency purposes.
    units_df = df[[date_col, underlying_col]].drop_duplicates()
    units_df = units_df.reset_index(drop=True)

    # Count how many raw events map to each (session_date, underlying) unit.
    # This multiplicity factor distributes the unit's weight equally across events.
    unit_key_col = "__unit_key__"
    df[unit_key_col] = list(zip(df[date_col], df[underlying_col]))
    unit_multiplicity: dict = df[unit_key_col].value_counts().to_dict()

    # Build: for each unit u, its label window = [u.date, u.date + horizon_days].
    # Build a dict: day -> count of units whose label window covers that day.
    from collections import defaultdict
    day_concurrency: dict = defaultdict(int)

    unit_rows = list(units_df.itertuples(index=False))
    for unit in unit_rows:
        import datetime as _dt
        t0 = unit[0]  # date
        for d in range(horizon_days + 1):
            day = t0 + _dt.timedelta(days=d)
            day_concurrency[day] += 1

    # Step 2: For each (session_date, underlying) unit, compute average uniqueness
    # u_unit = mean(1 / c_t) over its label window.  Then divide by the multiplicity
    # so that the sum of weights across all events in the unit equals u_unit (one unit
    # worth of effective observation).  This ensures:
    #   Σ w_i  ≈  number of independent (session, underlying) shocks
    # not the raw row count.  Amendment §4.4 / §7 effective-n requirement.
    import datetime as _dt
    unit_avg_u: dict = {}
    for unit in unit_rows:
        t0 = unit[0]  # date
        root = unit[1]
        inv_counts = []
        for d in range(horizon_days + 1):
            day = t0 + _dt.timedelta(days=d)
            c_t = day_concurrency.get(day, 1)
            inv_counts.append(1.0 / max(1, c_t))
        unit_avg_u[(t0, root)] = float(np.mean(inv_counts))

    weights: dict = {}
    for row in df.itertuples(index=False):
        eid = getattr(row, event_id_col)
        t0 = getattr(row, date_col)
        root = getattr(row, underlying_col)
        if t0 is None or not isinstance(t0, _dt.date):
            weights[eid] = float("nan")
            continue
        u_unit = unit_avg_u.get((t0, root), 1.0)
        n_in_unit = unit_multiplicity.get((t0, root), 1)
        # Distribute the unit's average uniqueness equally across all events in it
        weights[eid] = u_unit / max(1, n_in_unit)

    return pd.Series(weights, name="uniqueness_weight")


# ── artifact loader ───────────────────────────────────────────────────────────

def load_artifact(
    models_dir: str | Path,
    bucket: str,
) -> tuple[Any, Any, dict] | None:
    """Load the latest versioned model artifact for a bucket.

    Scans models_dir for directories matching flow_score_{bucket}_v{N}/,
    picks the highest N, loads model.joblib + calibrator.joblib + manifest.json,
    and verifies SHA-256 hashes from the manifest.

    Parameters
    ----------
    models_dir : str or Path
        Directory containing versioned artifact subdirectories.
    bucket : str
        Model bucket ('0_7', '8_90', '90p').

    Returns
    -------
    (model, calibrator, manifest) if found and hash-verified; None otherwise.
    Logs a warning and returns None on any error (INERT — never crashes callers).
    """
    # LAZY sklearn import
    try:
        import joblib
    except ImportError:
        log.warning("flow_score.load_artifact: joblib not available — cannot load artifacts")
        return None

    models_dir = Path(models_dir)
    if not models_dir.exists():
        log.debug("flow_score.load_artifact: models_dir %s does not exist", models_dir)
        return None

    # Find all artifact directories for this bucket
    prefix = f"flow_score_{bucket}_v"
    candidates: list[tuple[int, Path]] = []
    for d in models_dir.iterdir():
        if d.is_dir() and d.name.startswith(prefix):
            try:
                version = int(d.name[len(prefix):])
                candidates.append((version, d))
            except ValueError:
                continue

    if not candidates:
        log.debug("flow_score.load_artifact: no artifact for bucket=%s in %s", bucket, models_dir)
        return None

    # Pick highest version
    candidates.sort(key=lambda x: x[0], reverse=True)
    _, artifact_dir = candidates[0]

    manifest_path = artifact_dir / "manifest.json"
    model_path = artifact_dir / "model.joblib"
    calibrator_path = artifact_dir / "calibrator.joblib"

    for p in (manifest_path, model_path, calibrator_path):
        if not p.exists():
            log.warning("flow_score.load_artifact: missing file %s", p)
            return None

    try:
        with manifest_path.open() as f:
            manifest = json.load(f)
    except Exception as e:
        log.warning("flow_score.load_artifact: cannot read manifest %s: %s", manifest_path, e)
        return None

    # Verify SHA-256 hashes from manifest
    hashes = manifest.get("hashes", {})
    expected_model_sha = hashes.get("model_sha256")
    expected_cal_sha = hashes.get("calibrator_sha256")

    if expected_model_sha:
        actual = _sha256_file(model_path)
        if actual != expected_model_sha:
            log.error(
                "flow_score.load_artifact: SHA-256 MISMATCH for model %s "
                "(expected=%s, got=%s) — artifact rejected",
                model_path, expected_model_sha, actual,
            )
            return None

    if expected_cal_sha:
        actual = _sha256_file(calibrator_path)
        if actual != expected_cal_sha:
            log.error(
                "flow_score.load_artifact: SHA-256 MISMATCH for calibrator %s "
                "(expected=%s, got=%s) — artifact rejected",
                calibrator_path, expected_cal_sha, actual,
            )
            return None

    try:
        model = joblib.load(model_path)
        calibrator = joblib.load(calibrator_path)
    except Exception as e:
        log.warning("flow_score.load_artifact: cannot load joblib files: %s", e)
        return None

    return (model, calibrator, manifest)


# ── scorer ────────────────────────────────────────────────────────────────────

def score_events(
    artifact: tuple[Any, Any, dict],
    features_df: pd.DataFrame,
    event_id_col: str = "event_id",
) -> pd.DataFrame:
    """Score events using a loaded artifact.

    Produces score_raw (model's raw predicted probability) and score_calibrated
    (isotonic-calibrated probability, null unless manifest.deployable is True).

    PRE-GATE LAW (amendment §9 / FS-R3):
      score_calibrated is null when deployable=False — the score must not silently
      surface a number that has not passed calibration criteria.

    Parameters
    ----------
    artifact : (model, calibrator, manifest) from load_artifact().
    features_df : DataFrame
        Must contain event_id_col and the feature columns the model was trained on.
        Columns not in the training feature set are ignored; missing columns are
        filled with NaN (HistGradientBoostingClassifier handles NaN natively).
    event_id_col : str
        Column name for event identifiers.

    Returns
    -------
    DataFrame with columns: event_id, score_raw, score_calibrated.
    score_raw is always populated when scoring succeeds; score_calibrated is null
    when deployable=False.
    """
    model, calibrator, manifest = artifact
    deployable = bool(manifest.get("deployable", False))

    if features_df.empty:
        return pd.DataFrame(columns=[event_id_col, "score_raw", "score_calibrated"])

    event_ids = features_df[event_id_col].values if event_id_col in features_df.columns else (
        features_df.index.values
    )

    # Canonical grade/outcome columns that must NEVER enter the feature frame
    # (mirrors _GRADE_COLS in build_flow_signals.py — kept in sync).
    # This guard ensures the fallback path cannot silently include label columns
    # even when manifest.cv_params.feature_columns is empty.
    _GRADE_COLS: frozenset[str] = frozenset([
        "fwd_ret", "spy_ret", "spy_excess", "outcome", "grade",
        "spy_excess_5", "spy_excess_21", "spy_excess_63", "spy_excess_126",
        "prem_touch_50", "prem_touch_100",
        "graded_at", "grade_source", "split_seam",
    ])

    # Select/align feature columns in training order
    train_features = manifest.get("cv_params", {}).get("feature_columns", [])
    if not train_features:
        # Fallback: use all numeric columns except event_id_col AND grade/outcome cols.
        # NEVER auto-select without excluding grade columns — that would silently
        # create a PIT leak when outcome columns are present in the ledger
        # (FS4-04 defense-in-depth guard).
        train_features = [
            c for c in features_df.columns
            if c != event_id_col
            and c not in _GRADE_COLS
            and pd.api.types.is_numeric_dtype(features_df[c])
        ]
        if not train_features:
            log.warning(
                "flow_score.score_events: manifest.cv_params.feature_columns is empty "
                "and no valid numeric non-grade columns found — returning empty scores"
            )
            return pd.DataFrame(columns=[event_id_col, "score_raw", "score_calibrated"])

    # Build feature matrix via the shared helper so interaction features
    # (e.g. dte_X_premium_z for 8_90) are computed identically at serve time
    # as they were at train time.  A raw column lookup would leave dte_X_premium_z
    # as NaN at serve time (FS4-01 train/serve skew fix).
    dte_interaction_enabled = bool(
        manifest.get("cv_params", {}).get("dte_interaction_enabled", False)
    )
    X = build_interaction_features(
        features_df, train_features, dte_interaction_enabled=dte_interaction_enabled
    )

    try:
        score_raw = model.predict_proba(X)[:, 1]
    except Exception as e:
        log.error("flow_score.score_events: predict_proba failed: %s", e)
        return pd.DataFrame({
            event_id_col: event_ids,
            "score_raw": [float("nan")] * len(event_ids),
            "score_calibrated": [None] * len(event_ids),
        })

    score_calibrated: list[float | None]
    if deployable and calibrator is not None:
        try:
            score_calibrated = list(calibrator.predict(score_raw))
        except Exception as e:
            log.warning("flow_score.score_events: calibrator.predict failed: %s", e)
            score_calibrated = [None] * len(score_raw)
    else:
        score_calibrated = [None] * len(score_raw)

    return pd.DataFrame({
        event_id_col: event_ids,
        "score_raw": score_raw.astype(float),
        "score_calibrated": score_calibrated,
    })
