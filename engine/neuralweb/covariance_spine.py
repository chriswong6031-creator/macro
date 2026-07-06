"""engine.neuralweb.covariance_spine — R-ORTH covariance spine (RUL-ORTH-1..11).

Rail (not a lobe): measures structural concentration and independence across
rates PCA, factor-return correlations, dispersion regime, and NW engine firing
patterns.  Display-only, authority="context".  Never scores, sizes, gates, or
ranks.

Schema: neuralweb.covariance_spine.v1
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Repo-root resolution
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent.parent

SCHEMA = "neuralweb.covariance_spine.v1"

# ---------------------------------------------------------------------------
# Block-level constants
# ---------------------------------------------------------------------------

_FACTOR_MIN_OBS = 60       # require >= 60 shared observations for factor correlation
_FACTOR_MAX_OBS = 252      # trailing window cap

_LOBE_MIN_ACTIVE_WEEKS = 30      # engine must have >= 30 active weeks to be measurable
_LOBE_MIN_SHARED_WEEKS = 30      # pair needs >= 30 shared weeks for correlation
_LOBE_MIN_COFIRES = 10           # Jaccard needs >= 10 co-fire events
_CORR_CLUSTER_THRESHOLD = 0.6    # |corr| > 0.6 -> same cluster
_NULL_DRAWS = 200                 # RUL-ORTH-8 null draws

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(x: Any) -> float | None:
    """Convert to float, return None on any error."""
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _participation_ratio(eigenvalues: list[float]) -> float | None:
    """Participation ratio = (sum lambda)^2 / sum(lambda^2); eigenvalues clipped to >=0."""
    if not eigenvalues:
        return None
    ev = [max(0.0, e) for e in eigenvalues]
    total = sum(ev)
    if total <= 0:
        return None
    sum_sq = sum(e * e for e in ev)
    if sum_sq <= 0:
        return None
    return (total * total) / sum_sq


# ---------------------------------------------------------------------------
# Block 1 — rates PCA
# ---------------------------------------------------------------------------


def _build_rates_block(root: Path, missing_inputs: list[str]) -> dict | None:
    """Read yield_curve PCA from data/regime/latest.json."""
    src = root / "data" / "regime" / "latest.json"
    if not src.exists():
        missing_inputs.append("rates: data/regime/latest.json absent")
        return None

    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        missing_inputs.append(f"rates: data/regime/latest.json unreadable — {exc}")
        return None

    try:
        yc = raw.get("yield_curve", {})
        shape = yc.get("shape", {})
        pca = shape.get("pca", {})
        factors = pca.get("factors", [])
        if not factors:
            missing_inputs.append("rates: yield_curve.shape.pca.factors absent or empty")
            return None

        dominant_pc_share = _safe_float(factors[0].get("var_explained"))
        first3_var = _safe_float(pca.get("first3_var"))

        # pca_health fields (may not exist until next nightly render)
        pca_health_note = "pca_health pending next nightly render"
        pca_h = pca.get("pca_health", {}) or {}

        effective_dimension_pr = _safe_float(pca_h.get("effective_dimension_pr") or pca.get("effective_dimension_pr"))
        pc3_to_pc4_gap = _safe_float(pca_h.get("pc3_to_pc4_gap") or pca.get("pc3_to_pc4_gap"))
        oos_pctile_vs_null = _safe_float(pca_h.get("oos_pctile_vs_null") or pca.get("oos_pctile_vs_null"))
        curvature_stability_tag = pca_h.get("curvature_stability_tag") or pca.get("curvature_stability_tag")
        vol_match_multipliers = pca_h.get("vol_match_multipliers") or pca.get("vol_match_multipliers")

        block: dict[str, Any] = {
            "dominant_pc_share": dominant_pc_share,
            "first3_var": first3_var,
            "effective_dimension_pr": effective_dimension_pr,
            "pc3_to_pc4_gap": pc3_to_pc4_gap,
            "oos_pctile_vs_null": oos_pctile_vs_null,
            "curvature_stability_tag": curvature_stability_tag,
            "vol_match_multipliers": vol_match_multipliers,
            "source": "data/regime/latest.json#yield_curve",
        }
        if effective_dimension_pr is None and pc3_to_pc4_gap is None:
            block["pca_health_note"] = pca_health_note

        return block

    except Exception as exc:  # noqa: BLE001
        missing_inputs.append(f"rates: error parsing yield_curve PCA — {exc}")
        return None


# ---------------------------------------------------------------------------
# Block 2 — factor correlations
# ---------------------------------------------------------------------------


def _build_factors_block(root: Path, missing_inputs: list[str]) -> dict | None:
    """Compute correlation PCA over factor long-short return series."""
    src = root / "site" / "factordata" / "factor_series.json"
    if not src.exists():
        missing_inputs.append("factors: site/factordata/factor_series.json absent")
        return None

    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        missing_inputs.append(f"factors: factor_series.json unreadable — {exc}")
        return None

    try:
        import numpy as np  # noqa: PLC0415

        factors_list: list[str] = raw.get("factors", [])
        chart_data = raw.get("chart_data", {})
        dates_raw: list[str] = chart_data.get("dates", [])
        spread: dict[str, list] = chart_data.get("spread", {})

        # Exclude "composite" — it is a linear blend of the others (double-counts variance)
        composite_note = (
            "'composite' excluded from correlation PCA — it is a linear blend "
            "of the other factors; including it would double-count shared variance."
        )
        non_composite = [f for f in factors_list if f != "composite"]

        if not non_composite:
            missing_inputs.append("factors: no non-composite factors available")
            return None

        # Build date-indexed series for each factor using long-short (spread) series;
        # fall back to long-only if long-short is unavailable.
        # spread values are cumulative NAV levels; compute period returns as pct-change.
        n_dates = len(dates_raw)

        factor_returns: dict[str, list[float]] = {}
        for fac in non_composite:
            vals_raw = spread.get(fac)
            if not vals_raw:
                # Try long-only via chart_data.long
                vals_raw = chart_data.get("long", {}).get(fac)
            if not vals_raw or len(vals_raw) != n_dates:
                continue
            # Build a float array, skipping leading Nones
            arr = np.array([float(v) if v is not None else np.nan for v in vals_raw])
            # Compute period returns: pct change
            with np.errstate(invalid="ignore", divide="ignore"):
                rets = np.where(
                    np.isfinite(arr[:-1]) & np.isfinite(arr[1:]) & (arr[:-1] != 0),
                    arr[1:] / arr[:-1] - 1.0,
                    np.nan,
                )
            factor_returns[fac] = rets  # type: ignore[assignment]

        # Find shared trailing window (up to _FACTOR_MAX_OBS observations)
        if len(factor_returns) < 2:
            missing_inputs.append(
                f"factors: only {len(factor_returns)} factor series available; need >= 2"
            )
            return None

        # Stack and find rows where ALL factors are finite
        names = sorted(factor_returns.keys())
        mat = np.column_stack([factor_returns[n] for n in names])
        finite_mask = np.all(np.isfinite(mat), axis=1)
        finite_idx = np.where(finite_mask)[0]

        # Take trailing up to _FACTOR_MAX_OBS
        if len(finite_idx) > _FACTOR_MAX_OBS:
            finite_idx = finite_idx[-_FACTOR_MAX_OBS:]

        n_obs = len(finite_idx)
        if n_obs < _FACTOR_MIN_OBS:
            missing_inputs.append(
                f"factors: only {n_obs} shared observations; need >= {_FACTOR_MIN_OBS}"
            )
            return {
                "dominant_factor_pc_share": None,
                "effective_factor_bets_pr": None,
                "n_factors_used": len(names),
                "n_obs_used": n_obs,
                "degraded": True,
                "degraded_reason": f"insufficient shared observations: {n_obs} < {_FACTOR_MIN_OBS}",
                "caveat": "~3y history, annual fundamentals; descriptive only",
                "composite_note": composite_note,
            }

        window = mat[finite_idx, :]  # shape (n_obs, n_factors)

        # Correlation matrix
        corr_mat = np.corrcoef(window, rowvar=False)  # shape (n_fac, n_fac)

        # Eigenvalue decomposition of correlation matrix
        eigvals = np.linalg.eigvalsh(corr_mat)  # ascending order
        eigvals = eigvals[::-1]  # descending
        eigvals = np.clip(eigvals, 0, None)

        dominant_factor_pc_share: float | None = None
        if eigvals.sum() > 0:
            dominant_factor_pc_share = round(float(eigvals[0] / eigvals.sum()), 4)

        pr = _participation_ratio(eigvals.tolist())
        effective_factor_bets_pr = round(pr, 4) if pr is not None else None

        return {
            "dominant_factor_pc_share": dominant_factor_pc_share,
            "effective_factor_bets_pr": effective_factor_bets_pr,
            "n_factors_used": len(names),
            "n_obs_used": int(n_obs),
            "caveat": "~3y history, annual fundamentals; descriptive only",
            "composite_note": composite_note,
        }

    except Exception as exc:  # noqa: BLE001
        missing_inputs.append(f"factors: error computing factor correlations — {exc}")
        return None


# ---------------------------------------------------------------------------
# Block 3 — dispersion
# ---------------------------------------------------------------------------


def _build_dispersion_block(root: Path, missing_inputs: list[str]) -> dict | None:
    """Pass through dispersion regime state + eigen block (if present)."""
    src = root / "data" / "dispersion" / "regime.json"
    if not src.exists():
        missing_inputs.append("dispersion: data/dispersion/regime.json absent")
        return None

    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        missing_inputs.append(f"dispersion: regime.json unreadable — {exc}")
        return None

    try:
        block: dict[str, Any] = {
            "state": raw.get("state"),
            "dispersion_pctile": _safe_float(raw.get("dispersion_pctile")),
            "avg_corr": _safe_float(raw.get("avg_corr")),
        }
        # Eigen block — lands via sibling PR; emit null+note when absent
        eigen = raw.get("eigen", {}) or {}
        if eigen:
            block["dominant_equity_pc_share"] = _safe_float(eigen.get("dominant_equity_pc_share"))
            block["effective_universe_bets_pr"] = _safe_float(eigen.get("effective_universe_bets_pr"))
            block["idio_dispersion_share"] = _safe_float(eigen.get("idio_dispersion_share"))
        else:
            block["dominant_equity_pc_share"] = None
            block["effective_universe_bets_pr"] = None
            block["idio_dispersion_share"] = None
            block["eigen_note"] = "eigen block absent — lands via sibling PR"

        return block

    except Exception as exc:  # noqa: BLE001
        missing_inputs.append(f"dispersion: error parsing regime.json — {exc}")
        return None


# ---------------------------------------------------------------------------
# Block 4 — lobes (core new measurement)
# ---------------------------------------------------------------------------


def _build_lobes_block(root: Path, missing_inputs: list[str]) -> dict | None:
    """Measure structural independence across NW engine firing patterns."""
    src = root / "data" / "neuralweb" / "spine_index.parquet"
    if not src.exists():
        missing_inputs.append("lobes: data/neuralweb/spine_index.parquet absent")
        return None

    try:
        import numpy as np  # noqa: PLC0415
        import pandas as pd  # noqa: PLC0415

        df = pd.read_parquet(src)
    except Exception as exc:  # noqa: BLE001
        missing_inputs.append(f"lobes: spine_index.parquet unreadable — {exc}")
        return None

    try:
        import numpy as np  # noqa: PLC0415
        import pandas as pd  # noqa: PLC0415

        # Trailing 730 calendar days
        today_str = df["as_of"].max()  # derive from data, not datetime.now
        try:
            cutoff_dt = pd.Timestamp(today_str) - pd.Timedelta(days=730)
            cutoff_str = cutoff_dt.strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            cutoff_str = ""
        df_trail = df[df["as_of"] >= cutoff_str].copy() if cutoff_str else df.copy()

        # Exclude placebo (control lane)
        placebo_excluded_note = "'placebo' engine excluded — control lane, not a signal source"
        df_trail = df_trail[df_trail["engine"] != "placebo"]

        # ISO week from as_of
        df_trail["isoweek"] = pd.to_datetime(df_trail["as_of"]).dt.to_period("W").astype(str)

        # Per (engine, iso_week): net_direction, n_fires
        ew = (
            df_trail.groupby(["engine", "isoweek"])
            .agg(net_direction=("direction", "sum"), n_fires=("direction", "count"))
            .reset_index()
            .rename(columns={"isoweek": "iso_week"})
        )

        # Active weeks per engine (n_fires >= 1 — all grouped rows are active by construction)
        active_weeks_per_engine = ew.groupby("engine")["iso_week"].count().to_dict()

        # Measurable vs unmeasurable
        measurable_engines = sorted(
            [e for e, w in active_weeks_per_engine.items() if w >= _LOBE_MIN_ACTIVE_WEEKS]
        )
        unmeasurable = sorted(
            [e for e, w in active_weeks_per_engine.items() if w < _LOBE_MIN_ACTIVE_WEEKS]
        )
        unmeasurable_details = {e: int(active_weeks_per_engine[e]) for e in unmeasurable}

        n_lobes_total = len(active_weeks_per_engine)
        n_lobes_measurable = len(measurable_engines)

        # --- Build per-engine weekly z-scored net_direction series ---
        # pivot: index=iso_week, columns=engine, values=net_direction
        if n_lobes_measurable == 0:
            # No measurable engines — return degraded block with coverage
            return {
                "effective_independent_lobes": None,
                "n_lobes_measurable": 0,
                "n_lobes_total": n_lobes_total,
                "degraded": True,
                "degraded_reason": "no engine has >= 30 active weeks",
                "null_reference": None,
                "same_bet_warning": {"active": False},
                "highest_overlap_pairs": [],
                "clusters": [],
                "coverage": {
                    "measurable": [],
                    "unmeasurable": unmeasurable_details,
                    "pairs_below_floor": 0,
                    "placebo_excluded": placebo_excluded_note,
                },
            }

        # Pivot for measurable engines
        meas_ew = ew[ew["engine"].isin(measurable_engines)].copy()
        pivot = meas_ew.pivot(index="iso_week", columns="engine", values="net_direction")

        # Z-score per engine (over its own active weeks)
        def _zscore_col(s: "pd.Series") -> "pd.Series":
            s = s.dropna()
            mu = s.mean()
            std = s.std(ddof=1)
            if std == 0 or pd.isna(std):
                return s - mu  # all zeros
            return (s - mu) / std

        pivot_z = pivot.apply(_zscore_col)

        # Pairwise correlation + Jaccard (over measurable engines only)
        # Pre-initialize all per-engine dicts to avoid KeyError on symmetric assignment
        corr_matrix: dict[str, dict[str, float | None]] = {e: {} for e in measurable_engines}
        n_shared_matrix: dict[str, dict[str, int]] = {e: {} for e in measurable_engines}
        jaccard_matrix: dict[str, dict[str, float | None]] = {e: {} for e in measurable_engines}
        pairs_below_floor = 0

        # Pre-build co-fire tuple sets per measurable engine (avoid re-scanning df_trail)
        def _cofire_set(engine: str) -> set[tuple]:
            rows_e = df_trail[df_trail["engine"] == engine]
            result_set = set()
            for r in rows_e.itertuples():
                d = int(r.direction)
                sign = int(math.copysign(1, d)) if d != 0 else 0
                result_set.add((r.symbol, r.isoweek, sign))
            return result_set

        cofire_sets: dict[str, set[tuple]] = {
            e: _cofire_set(e) for e in measurable_engines
        }

        for i, ea in enumerate(measurable_engines):
            for j, eb in enumerate(measurable_engines):
                if i == j:
                    corr_matrix[ea][eb] = 1.0
                    n_shared_matrix[ea][eb] = int(pivot_z[ea].dropna().shape[0])
                    jaccard_matrix[ea][eb] = 1.0
                    continue

                if j < i:
                    # Already computed — copy symmetric values
                    corr_matrix[ea][eb] = corr_matrix[eb][ea]
                    n_shared_matrix[ea][eb] = n_shared_matrix[eb][ea]
                    jaccard_matrix[ea][eb] = jaccard_matrix[eb][ea]
                    continue

                # i < j: compute upper triangle
                # Shared active weeks for correlation
                shared = pivot_z[[ea, eb]].dropna()
                n_shared = len(shared)
                n_shared_matrix[ea][eb] = n_shared

                if n_shared < _LOBE_MIN_SHARED_WEEKS:
                    corr_matrix[ea][eb] = None
                    pairs_below_floor += 1
                else:
                    arr_a = shared[ea].values
                    arr_b = shared[eb].values
                    std_a = float(np.std(arr_a, ddof=1))
                    std_b = float(np.std(arr_b, ddof=1))
                    if std_a == 0 and std_b == 0:
                        # Both constant series: perfectly correlated by identity
                        c = 1.0
                    elif std_a == 0 or std_b == 0:
                        # One constant: correlation undefined
                        c = float("nan")
                    else:
                        c = float(np.corrcoef(arr_a, arr_b)[0, 1])
                    corr_matrix[ea][eb] = round(c, 4) if not math.isnan(c) else None

                # Jaccard co-fire: symbol × iso_week × sign(direction) tuple sets
                set_a = cofire_sets[ea]
                set_b = cofire_sets[eb]
                union_size = len(set_a | set_b)
                inter_size = len(set_a & set_b)
                if union_size == 0 or inter_size < _LOBE_MIN_COFIRES:
                    jaccard_val: float | None = None
                else:
                    jaccard_val = round(inter_size / union_size, 4)
                jaccard_matrix[ea][eb] = jaccard_val

        # --- Clusters: greedy, deterministic (alphabetical engine order, pairs by (-|corr|, a, b)) ---
        # Collect all measurable pairs sorted by (-|corr|, name_a, name_b)
        pair_corrs: list[tuple[float, str, str]] = []
        for i, ea in enumerate(measurable_engines):
            for j, eb in enumerate(measurable_engines):
                if j <= i:
                    continue
                c = corr_matrix[ea][eb]
                if c is not None:
                    pair_corrs.append((abs(c), ea, eb))

        pair_corrs.sort(key=lambda x: (-x[0], x[1], x[2]))

        # Union-find for clusters
        parent = {e: e for e in measurable_engines}

        def _find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def _union(x: str, y: str) -> None:
            px, py = _find(x), _find(y)
            if px != py:
                # Smaller alphabetically becomes child
                if px < py:
                    parent[py] = px
                else:
                    parent[px] = py

        for abs_c, ea, eb in pair_corrs:
            if abs_c > _CORR_CLUSTER_THRESHOLD:
                _union(ea, eb)

        # Build cluster groups
        cluster_groups: dict[str, list[str]] = {}
        for e in measurable_engines:
            root_e = _find(e)
            cluster_groups.setdefault(root_e, []).append(e)

        clusters: list[list[str]] = [
            sorted(members) for members in cluster_groups.values() if len(members) > 1
        ]
        clusters.sort(key=lambda c: c[0])

        # --- effective_independent_lobes (participation ratio) ---
        # Build correlation matrix for all measurable engines; if a pair is below floor,
        # treat as 0.0 (independent assumption)
        n_m = len(measurable_engines)
        corr_mat_arr = np.zeros((n_m, n_m))
        for i, ea in enumerate(measurable_engines):
            for j, eb in enumerate(measurable_engines):
                if i == j:
                    corr_mat_arr[i, j] = 1.0
                else:
                    c = corr_matrix[ea].get(eb)
                    corr_mat_arr[i, j] = c if c is not None else 0.0

        eigvals_m = np.linalg.eigvalsh(corr_mat_arr)[::-1]
        eigvals_m = np.clip(eigvals_m, 0, None)
        eil_pr = _participation_ratio(eigvals_m.tolist())
        effective_independent_lobes = round(eil_pr, 4) if eil_pr is not None else None

        # --- Null reference (RUL-ORTH-8): deterministic circular-shift null ---
        # For each engine, use its own active-week net_direction sequence
        engine_series: dict[str, list[float]] = {}
        for e in measurable_engines:
            weeks_sorted = sorted(pivot.index[pivot[e].notna()].tolist())
            engine_series[e] = [float(pivot.loc[w, e]) for w in weeks_sorted]

        null_pr_values: list[float] = []
        for d in range(_NULL_DRAWS):
            null_corr_mat = np.zeros((n_m, n_m))
            shifted: dict[str, list[float]] = {}
            for i, e in enumerate(measurable_engines):
                seq = engine_series[e]
                n_w = len(seq)
                shift = ((d + 1) * (i + 1) * 7) % n_w
                shifted[e] = seq[shift:] + seq[:shift]

            # Build pivot with shifted series — align by position (circular shift)
            # Use the ISO-week index ordering from the original series
            for i, ea in enumerate(measurable_engines):
                for j, eb in enumerate(measurable_engines):
                    if i == j:
                        null_corr_mat[i, j] = 1.0
                        continue
                    # Shared length = min of both (since circularly shifted, all are same n_w)
                    n_a = len(shifted[ea])
                    n_b = len(shifted[eb])
                    n_use = min(n_a, n_b)
                    if n_use < _LOBE_MIN_SHARED_WEEKS:
                        null_corr_mat[i, j] = 0.0
                    else:
                        arr_a = np.array(shifted[ea][:n_use])
                        arr_b = np.array(shifted[eb][:n_use])
                        c = float(np.corrcoef(arr_a, arr_b)[0, 1])
                        null_corr_mat[i, j] = c if not math.isnan(c) else 0.0

            null_eigvals = np.linalg.eigvalsh(null_corr_mat)[::-1]
            null_eigvals = np.clip(null_eigvals, 0, None)
            null_pr = _participation_ratio(null_eigvals.tolist())
            if null_pr is not None:
                null_pr_values.append(null_pr)

        null_reference: dict[str, Any] | None = None
        if null_pr_values and effective_independent_lobes is not None:
            null_arr = sorted(null_pr_values)
            null_median = float(np.median(null_arr))
            null_p90 = float(np.percentile(null_arr, 90))
            pctile_vs_null = sum(1 for v in null_arr if v <= effective_independent_lobes) / len(null_arr)
            null_reference = {
                "null_median": round(null_median, 4),
                "null_p90": round(null_p90, 4),
                "pctile_vs_null": round(pctile_vs_null, 4),
                "n_null_draws": _NULL_DRAWS,
            }

        # --- same_bet_warning (deterministic rule) ---
        same_bet_warning: dict[str, Any] = {"active": False}
        if clusters:
            # Find largest cluster
            largest_cluster = max(clusters, key=len)
            if len(largest_cluster) >= 3:
                # Compute mean intra-cluster |corr|
                intra_corrs = []
                for i, ea in enumerate(largest_cluster):
                    for j, eb in enumerate(largest_cluster):
                        if j <= i:
                            continue
                        c = corr_matrix[ea].get(eb)
                        if c is not None:
                            intra_corrs.append(abs(c))
                if intra_corrs:
                    mean_abs_corr = sum(intra_corrs) / len(intra_corrs)
                    if mean_abs_corr > _CORR_CLUSTER_THRESHOLD:
                        same_bet_warning = {
                            "active": True,
                            "cluster": sorted(largest_cluster),
                            "mean_abs_corr": round(mean_abs_corr, 4),
                            "text": (
                                "Structural overlap detected: a cluster of "
                                f"{len(largest_cluster)} engines fires with "
                                "mean intra-cluster |corr| > 0.60. "
                                "These lobes may be measuring the same bet. "
                                "Display-only; does not alter behavior."
                            ),
                        }

        # --- highest_overlap_pairs: top 5 by |corr| ---
        all_pairs: list[dict] = []
        for i, ea in enumerate(measurable_engines):
            for j, eb in enumerate(measurable_engines):
                if j <= i:
                    continue
                c = corr_matrix[ea].get(eb)
                if c is None:
                    continue
                all_pairs.append({
                    "a": ea,
                    "b": eb,
                    "corr": c,
                    "n_shared_weeks": n_shared_matrix[ea].get(eb, 0),
                    "jaccard": jaccard_matrix.get(ea, {}).get(eb),
                })

        all_pairs.sort(key=lambda p: -abs(p["corr"]))
        highest_overlap_pairs = all_pairs[:5]

        return {
            "effective_independent_lobes": effective_independent_lobes,
            "n_lobes_measurable": n_lobes_measurable,
            "n_lobes_total": n_lobes_total,
            "null_reference": null_reference,
            "same_bet_warning": same_bet_warning,
            "highest_overlap_pairs": highest_overlap_pairs,
            "clusters": clusters,
            "coverage": {
                "measurable": measurable_engines,
                "unmeasurable": unmeasurable_details,
                "pairs_below_floor": pairs_below_floor,
                "placebo_excluded": placebo_excluded_note,
            },
        }

    except Exception as exc:  # noqa: BLE001
        log.exception("lobes: unexpected error")
        missing_inputs.append(f"lobes: unexpected error — {exc}")
        return None


# ---------------------------------------------------------------------------
# Derive as_of from inputs (never datetime.now for as_of)
# ---------------------------------------------------------------------------


def _derive_as_of(root: Path) -> str:
    """Derive as_of from the most recent input data seen across inputs."""
    candidates: list[str] = []

    # From spine_index.parquet max as_of
    src_spine = root / "data" / "neuralweb" / "spine_index.parquet"
    if src_spine.exists():
        try:
            import pandas as pd  # noqa: PLC0415
            df = pd.read_parquet(src_spine, columns=["as_of"])
            candidates.append(df["as_of"].max())
        except Exception:  # noqa: BLE001
            pass

    # From regime/latest.json yield_curve.asof
    src_regime = root / "data" / "regime" / "latest.json"
    if src_regime.exists():
        try:
            raw = json.loads(src_regime.read_text(encoding="utf-8"))
            yc_asof = raw.get("yield_curve", {}).get("asof")
            if yc_asof:
                candidates.append(str(yc_asof))
        except Exception:  # noqa: BLE001
            pass

    # From dispersion/regime.json as_of
    src_disp = root / "data" / "dispersion" / "regime.json"
    if src_disp.exists():
        try:
            raw = json.loads(src_disp.read_text(encoding="utf-8"))
            if raw.get("as_of"):
                candidates.append(str(raw["as_of"]))
        except Exception:  # noqa: BLE001
            pass

    # From factor_series.json as_of
    src_fac = root / "site" / "factordata" / "factor_series.json"
    if src_fac.exists():
        try:
            raw = json.loads(src_fac.read_text(encoding="utf-8"))
            if raw.get("as_of"):
                candidates.append(str(raw["as_of"]))
        except Exception:  # noqa: BLE001
            pass

    if not candidates:
        return date.today().isoformat()

    # Return max valid date string
    valid = [c for c in candidates if c and len(c) >= 10]
    return max(valid) if valid else date.today().isoformat()


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------


def build_state(root: Path = _ROOT) -> dict:
    """Build the covariance spine artifact dict.

    Each block is independently guarded: on missing/failed input the block is
    omitted from the output, a string is appended to missing_inputs, and the
    function never raises.

    Returns
    -------
    dict
        Artifact dict conforming to neuralweb.covariance_spine.v1.
    """
    missing_inputs: list[str] = []

    rates_block = _build_rates_block(root, missing_inputs)
    factors_block = _build_factors_block(root, missing_inputs)
    dispersion_block = _build_dispersion_block(root, missing_inputs)
    lobes_block = _build_lobes_block(root, missing_inputs)

    as_of = _derive_as_of(root)

    # Committee annotations — deterministic strings
    committee_annotations: list[str] = [
        "Rail (not a lobe): provides concentration accounting context only.",
        "Display-only ceiling: no block may score, size, gate, rank, or originate a trade.",
        "Lobes block: effective_independent_lobes derived from participation-ratio of measurable-engine correlation matrix.",
        "Factors block: composite factor excluded — linear blend would double-count shared variance.",
        "Null reference: 200 deterministic circular-shift draws; pctile_vs_null in [0,1].",
    ]

    blocks: dict[str, Any] = {}
    if rates_block is not None:
        blocks["rates"] = rates_block
    if factors_block is not None:
        blocks["factors"] = factors_block
    if dispersion_block is not None:
        blocks["dispersion"] = dispersion_block
    if lobes_block is not None:
        blocks["lobes"] = lobes_block

    # Build top-level coverage (lobes coverage included in the lobes block)
    coverage: dict[str, Any] = {}
    if lobes_block is not None:
        coverage = lobes_block.get("coverage", {})

    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "display_only": True,
        "authority": "context",
        "descriptive_not_gauntleted": True,
        "blocks": blocks,
        "coverage": coverage,
        "missing_inputs": missing_inputs,
        "committee_annotations": committee_annotations,
        "allowed_actions": ["display", "explain", "de_escalation_research_only"],
        "forbidden_actions": ["score", "size", "originate_trade", "gate", "rank"],
    }
