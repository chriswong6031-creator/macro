"""Treasury PCA diagnostics for Neural Web covariance research.

This script reads the repo's local FRED constant-maturity Treasury yield
history and writes reproducible PCA diagnostics for the research memo. It is
research/display only: no signal, score, or sizing authority is produced here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
FRED_DIR = ROOT / "data" / "fred"
OUT_DIR = ROOT / "research" / "pca_factor_orthogonality"

NODES = [
    ("DGS3MO.parquet", "us3m", 0.25),
    ("DGS6MO.parquet", "us6m", 0.50),
    ("DGS1.parquet", "us1y", 1.00),
    ("DGS2.parquet", "us2y", 2.00),
    ("DGS3.parquet", "us3y", 3.00),
    ("DGS5.parquet", "us5y", 5.00),
    ("DGS7.parquet", "us7y", 7.00),
    ("DGS10.parquet", "us10y", 10.00),
    ("DGS30.parquet", "us30y", 30.00),
]

ROLLING_WINDOW = 504
LONG_WINDOW = 1260
OOS_HORIZON = 21
ROLL_STEP = 21


def _round_float(value: Any, digits: int = 6) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _load_yields() -> pd.DataFrame:
    frames = []
    for file_name, column, _maturity in NODES:
        path = FRED_DIR / file_name
        frame = pd.read_parquet(path)
        if column not in frame.columns:
            if len(frame.columns) != 1:
                raise ValueError(f"{path} did not contain expected column {column}")
            frame = frame.rename(columns={frame.columns[0]: column})
        series = frame[[column]].copy()
        series.index = pd.to_datetime(series.index)
        frames.append(series.astype(float))

    yields = pd.concat(frames, axis=1, sort=False).sort_index()
    # NOTE: inner-join dropna starts the joint sample at DGS3MO inception (~1981-09-01),
    # discarding earlier DGS10/DGS30 history.  All diagnostics reflect this truncated sample.
    return yields.dropna(how="any")


def _orient_vectors(vectors: np.ndarray) -> np.ndarray:
    """Give the first three PCs stable finance-friendly signs."""

    oriented = vectors.copy()
    maturities = np.array([node[2] for node in NODES], dtype=float)

    # Level: positive parallel shift.
    if oriented[:, 0].sum() < 0:
        oriented[:, 0] *= -1

    # Slope: positive loading rises with maturity.
    if np.corrcoef(oriented[:, 1], maturities)[0, 1] < 0:
        oriented[:, 1] *= -1

    # Curvature: belly positive relative to wings.
    belly = np.array([2.0 <= maturity <= 7.0 for maturity in maturities])
    wing = ~belly
    if oriented[belly, 2].mean() - oriented[wing, 2].mean() < 0:
        oriented[:, 2] *= -1

    return oriented


def _pca(change_window: pd.DataFrame) -> dict[str, Any]:
    array = change_window.to_numpy(dtype=float)
    cov = np.cov(array.T)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = _orient_vectors(eigenvectors[:, order])

    total = float(eigenvalues.sum())
    shares = eigenvalues / total if total else np.zeros_like(eigenvalues)
    gaps = [
        float(eigenvalues[i] / eigenvalues[i + 1])
        if i + 1 < len(eigenvalues) and eigenvalues[i + 1] > 0
        else None
        for i in range(len(eigenvalues) - 1)
    ]
    participation = total * total / float(np.square(eigenvalues).sum()) if total else None

    loadings = {}
    for idx, name in enumerate(["pc1_level", "pc2_slope", "pc3_curvature"]):
        loadings[name] = {
            node[1]: _round_float(eigenvectors[node_idx, idx], 4)
            for node_idx, node in enumerate(NODES)
        }

    return {
        "n_obs": int(len(change_window)),
        "start": change_window.index.min().date().isoformat(),
        "end": change_window.index.max().date().isoformat(),
        "variance_explained": {
            f"pc{i + 1}": _round_float(share, 6)
            for i, share in enumerate(shares[:9])
        },
        "first3_var": _round_float(shares[:3].sum(), 6),
        "effective_dimension_pr": _round_float(participation, 4),
        "eigenvalue_gaps": {
            f"pc{i + 1}_to_pc{i + 2}": _round_float(gap, 4)
            for i, gap in enumerate(gaps[:5])
        },
        "loadings": loadings,
        "_vectors": eigenvectors,
    }


def _project_oos(future_changes: pd.DataFrame, vectors: np.ndarray) -> float | None:
    if len(future_changes) < 5:
        return None
    projected = future_changes.to_numpy(dtype=float) @ vectors[:, :3]
    # Degenerate guard: if any PC projection is constant, correlation is undefined.
    col_stds = projected.std(axis=0)
    if np.any(col_stds < 1e-12):
        return None
    corr = np.corrcoef(projected.T)
    if corr.shape != (3, 3) or np.isnan(corr).all():
        return None
    off_diag = corr - np.eye(3)
    return _round_float(np.nanmax(np.abs(off_diag)), 4)


def _strip_vectors(result: dict[str, Any]) -> dict[str, Any]:
    clean = dict(result)
    clean.pop("_vectors", None)
    return clean


def _latest_window(changes: pd.DataFrame, window: int) -> dict[str, Any]:
    if len(changes) < window:
        raise ValueError(f"Need {window} observations, found {len(changes)}")
    return _pca(changes.iloc[-window:])


def _within_window_null(window: pd.DataFrame, vectors: np.ndarray, stride: int = 2, cap: int = 200) -> list[float]:
    """Compute the OOS statistic on contiguous 21-row slices INSIDE the training window.

    Slices are deterministically enumerated at the given stride (no randomness).
    Capped at `cap` draws, evenly spaced via strided index.
    Returns a list of observed statistic values (floats), dropping None entries.
    """
    n = len(window)
    # All valid start positions for a 21-row contiguous slice inside the window.
    starts = list(range(0, n - OOS_HORIZON + 1, stride))
    # Evenly-space down to cap if over limit.
    if len(starts) > cap:
        indices = np.linspace(0, len(starts) - 1, cap, dtype=int)
        starts = [starts[i] for i in indices]
    null_vals: list[float] = []
    for s in starts:
        sl = window.iloc[s:s + OOS_HORIZON]
        val = _project_oos(sl, vectors)
        if val is not None:
            null_vals.append(val)
    return null_vals


def _rolling_summary(changes: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    prior_vectors = None
    n_degenerate = 0

    for end_pos in range(ROLLING_WINDOW, len(changes) - OOS_HORIZON + 1, ROLL_STEP):
        window = changes.iloc[end_pos - ROLLING_WINDOW:end_pos]
        result = _pca(window)
        vectors = result["_vectors"]
        future = changes.iloc[end_pos:end_pos + OOS_HORIZON]
        stability = None
        if prior_vectors is not None:
            stability = 1.0 - abs(float(np.dot(prior_vectors[:, 0], vectors[:, 0])))
        prior_vectors = vectors

        observed = _project_oos(future, vectors)
        if observed is None and len(future) >= 5:
            n_degenerate += 1

        # Within-window null: enumerate contiguous 21-row slices inside training window.
        null_vals = _within_window_null(window, vectors)
        if null_vals:
            null_arr = np.array(null_vals)
            null_median = _round_float(float(np.median(null_arr)), 6)
            null_p90 = _round_float(float(np.percentile(null_arr, 90)), 6)
            if observed is not None:
                null_pctile = _round_float(float(np.mean(null_arr <= observed)), 6)
            else:
                null_pctile = None
        else:
            null_median = None
            null_p90 = None
            null_pctile = None

        rows.append(
            {
                "end": result["end"],
                "pc1_var": result["variance_explained"]["pc1"],
                "pc2_var": result["variance_explained"]["pc2"],
                "pc3_var": result["variance_explained"]["pc3"],
                "first3_var": result["first3_var"],
                "effective_dimension_pr": result["effective_dimension_pr"],
                "pc1_to_pc2_gap": result["eigenvalue_gaps"]["pc1_to_pc2"],
                "pc2_to_pc3_gap": result["eigenvalue_gaps"]["pc2_to_pc3"],
                "pc3_to_pc4_gap": result["eigenvalue_gaps"]["pc3_to_pc4"],
                "pc1_loading_turnover_vs_prev": _round_float(stability, 6),
                "next_21d_oos_max_abs_pc_corr": observed,
                "oos_null_median": null_median,
                "oos_null_p90": null_p90,
                "oos_pctile_vs_null": null_pctile,
            }
        )

    frame = pd.DataFrame(rows)
    summary = {
        "window_days": ROLLING_WINDOW,
        "step_days": ROLL_STEP,
        "oos_horizon_days": OOS_HORIZON,
        "count": int(len(frame)),
        "n_degenerate_windows": n_degenerate,
    }
    for column in [
        "pc1_var",
        "first3_var",
        "effective_dimension_pr",
        "pc1_to_pc2_gap",
        "pc3_to_pc4_gap",
        "pc1_loading_turnover_vs_prev",
        "next_21d_oos_max_abs_pc_corr",
        "oos_null_median",
        "oos_null_p90",
        "oos_pctile_vs_null",
    ]:
        series = frame[column].dropna()
        if not series.empty:
            summary[column] = {
                "min": _round_float(series.min(), 6),
                "median": _round_float(series.median(), 6),
                "max": _round_float(series.max(), 6),
                "latest": _round_float(series.iloc[-1], 6),
            }

    return rows, summary


def _snapshot(changes: pd.DataFrame, end_date: str, window: int = ROLLING_WINDOW) -> dict[str, Any] | None:
    end_ts = pd.Timestamp(end_date)
    eligible = changes.loc[:end_ts]
    if len(eligible) < window:
        return None
    return _strip_vectors(_pca(eligible.iloc[-window:]))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    yields = _load_yields()
    changes = yields.diff().dropna()

    full = _pca(changes)
    latest_5y = _latest_window(changes, LONG_WINDOW)
    latest_2y = _latest_window(changes, ROLLING_WINDOW)
    rolling_rows, rolling_stats = _rolling_summary(changes)

    snapshots = {
        date: snapshot
        for date in [
            "2019-12-31",
            "2020-03-16",
            "2020-04-30",
            "2021-12-31",
            "2022-06-30",
            "2023-10-31",
            # "2026-07-06" removed: byte-identical to latest_2y (current window).
        ]
        if (snapshot := _snapshot(changes, date)) is not None
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "Local FRED Treasury constant-maturity parquet files under data/fred",
        "source_files": [node[0] for node in NODES],
        "method": {
            "input": "Daily yield changes in percentage points, complete rows only",
            "demeaning": "numpy covariance demeaning inside np.cov",
            "orientation": "PC1 sum positive; PC2 rising with maturity; PC3 belly positive",
            "rolling_window_days": ROLLING_WINDOW,
            "long_window_days": LONG_WINDOW,
            "oos_horizon_days": OOS_HORIZON,
            "notes": "OOS health is max absolute off-diagonal correlation of next-21d projected first-three PC returns.",
            "sample_truncation": (
                "Joint sample starts at DGS3MO inception (~1981-09-01) due to inner-join dropna; "
                "earlier DGS10/DGS30 history is discarded."
            ),
            "latest_2y_note": "latest_2y covers the current rolling window; no separate snapshot is created for today.",
            "null_calibration": (
                "oos_null_median/p90 are computed from contiguous 21-row slices inside each training window "
                "(stride=2, cap=200, deterministic enumeration, ≥200 draws per window per RUL-ORTH-8). "
                "oos_pctile_vs_null is the fraction of null draws <= the observed value. "
                "Per RUL-ORTH-8, raw OOS thresholds are illegal; metrics must be read against these null columns."
            ),
        },
        "sample": {
            "yield_start": yields.index.min().date().isoformat(),
            "yield_end": yields.index.max().date().isoformat(),
            "yield_rows": int(len(yields)),
            "change_rows": int(len(changes)),
        },
        "full_sample": _strip_vectors(full),
        "latest_5y": _strip_vectors(latest_5y),
        "latest_2y": _strip_vectors(latest_2y),
        "rolling_2y_summary": rolling_stats,
        "snapshots_2y": snapshots,
        "interpretation_notes": [
            "Use high PC1 share as a market-mode/concentration warning, not a directional forecast.",
            "Use low PC3-to-PC4 separation or high OOS PC correlation as a PCA-trust warning.",
            "Use effective dimension as an independent-bets estimate for governance and confluence de-duplication.",
            (
                "CRITICAL (RUL-ORTH-8): the observed OOS statistic MUST be read against oos_null_median and "
                "oos_null_p90 — at n=21 the null floor is ~0.4-0.5; raw thresholds are illegal per RUL-ORTH-8 "
                "(research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md). "
                "oos_pctile_vs_null is the calibrated metric to report."
            ),
        ],
    }

    json_path = OUT_DIR / "treasury_pca_diagnostics.json"
    csv_path = OUT_DIR / "treasury_pca_rolling_summary.csv"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(rolling_rows).to_csv(csv_path, index=False)

    print(json.dumps({"json": str(json_path), "csv": str(csv_path)}, indent=2))


if __name__ == "__main__":
    main()
