"""Read-only Prophet flagship Value-of-Information measurement primitives.

MAS-123 / Cell G.  This module deliberately owns *measurement formulas*, not evidence
storage, promotion, rank influence, Availability, candidate identity, or outcome clocks.

The governing research law is:
    research/prophet_v4/CELL_G_FLAGSHIP_VOI_MEASUREMENT_LAW_2026-08-22.md

Hard boundaries
---------------
* No function writes a file or mutates a ledger.
* No function opens a protected race outcome.  W3 support is STATUS-ONLY.
* Missing fields produce explicit measurement states; they are never backfilled.
* Concentration-effective counts are diagnostics, never substituted into a t/binomial
  distribution as a synthetic sample size.
* All current US-board results produced here are DESCRIPTIVE_ONLY.  They are not a
  prospective family-promotion read.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

REPORT_SCHEMA = "prophet.flagship_voi_report/v1"

MEASURED = "MEASURED"
NOT_MATURE = "NOT_MATURE"
PROTECTED_OUTCOME = "PROTECTED_OUTCOME"
UNAVAILABLE_FIELD = "UNAVAILABLE_FIELD"
UNESTIMABLE = "UNESTIMABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"
DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
HOLD_INTEGRITY = "HOLD_INTEGRITY"

MEASUREMENT_STATES = frozenset({
    MEASURED,
    NOT_MATURE,
    PROTECTED_OUTCOME,
    UNAVAILABLE_FIELD,
    UNESTIMABLE,
    NOT_APPLICABLE,
    DESCRIPTIVE_ONLY,
    HOLD_INTEGRITY,
})

# Source-specific adapter only.  This is explicitly *not* the final V4 Availability
# vocabulary; it mirrors entry_signal's current "buyable now" semantics.
ENTRY_SIGNAL_ACTIONABLE_NOW = frozenset({"buy_now", "partial"})
BROAD_COVERAGE_FLOOR = 0.70


def _finite_float(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _round(value: Any, places: int = 6) -> float | None:
    x = _finite_float(value)
    return round(x, places) if x is not None else None


def concentration_effective_count(values: Iterable[Any]) -> dict[str, Any]:
    """Return Cell-G's concentration-effective-count diagnostic.

    N_eff(G) = 1 / sum_g p_g^2, where p_g is the share of non-null observations
    carried by group g.  This is the effective number of equally represented groups
    with the same concentration.  It is NOT an inferential degrees-of-freedom fix.
    """
    seq = list(values)
    clean = [v for v in seq if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not clean:
        return {
            "state": UNESTIMABLE,
            "n_rows": len(seq),
            "n_missing": len(seq),
            "n_groups": 0,
            "n_eff": None,
            "top1_share": None,
            "top5_share": None,
            "dominated_gt_50pct": None,
        }
    counts = Counter(clean)
    n = len(clean)
    shares = sorted((c / n for c in counts.values()), reverse=True)
    n_eff = 1.0 / sum(p * p for p in shares)
    return {
        "state": MEASURED,
        "n_rows": len(seq),
        "n_nonnull": n,
        "n_missing": len(seq) - n,
        "n_groups": len(counts),
        "n_eff": round(n_eff, 6),
        "top1_share": round(shares[0], 6),
        "top5_share": round(sum(shares[:5]), 6),
        "dominated_gt_50pct": bool(shares[0] > 0.50),
    }


def ndcg_at_k(relevance: Sequence[int | float | None], k: int) -> dict[str, Any]:
    """Exact Cell-G NDCG formula with loud no-relevant/null handling."""
    if k <= 0:
        raise ValueError("k must be positive")
    vals = list(relevance[:k])
    if any(v is None for v in vals):
        return {"state": UNAVAILABLE_FIELD, "value": None, "reason": "missing_relevance_grade"}
    gains: list[float] = []
    for v in vals:
        x = _finite_float(v)
        if x is None or x < 0:
            return {"state": HOLD_INTEGRITY, "value": None, "reason": "invalid_relevance_grade"}
        gains.append(x)

    def dcg(xs: Sequence[float]) -> float:
        return sum((2.0**rel - 1.0) / math.log2(rank + 2.0) for rank, rel in enumerate(xs))

    ideal = sorted(gains, reverse=True)
    idcg = dcg(ideal)
    if idcg == 0.0:
        return {
            "state": NOT_APPLICABLE,
            "value": None,
            "reason": "idcg_zero_no_relevant_items",
            "k": k,
            "n_ranked": len(gains),
        }
    return {
        "state": MEASURED,
        "value": round(dcg(gains) / idcg, 10),
        "k": k,
        "n_ranked": len(gains),
    }


def precision_recall_at_k(
    positive: Sequence[bool | None],
    k: int,
    *,
    reference_positive_count: int | None = None,
) -> dict[str, Any]:
    """Precision/fill and recall for an already-frozen binary relevance label.

    Missing labels in the presented top-K are not silently treated as negatives; the
    metric is unavailable because the winner label itself is missing.  Recall requires
    an explicit reference-population positive count so retrieval-changing experiments
    cannot accidentally use their own surfaced set as the denominator.
    """
    if k <= 0:
        raise ValueError("k must be positive")
    top = list(positive[:k])
    if any(v is None for v in top):
        return {"state": UNAVAILABLE_FIELD, "reason": "missing_positive_label"}
    n_presented = len(top)
    n_positive = sum(bool(v) for v in top)
    precision = (n_positive / n_presented) if n_presented else None
    fill = n_presented / k
    out: dict[str, Any] = {
        "state": MEASURED,
        "k": k,
        "n_presented": n_presented,
        "n_positive_topk": n_positive,
        "precision_presented": _round(precision),
        "fill_at_k": _round(fill),
    }
    if reference_positive_count is None:
        out["recall"] = None
        out["recall_state"] = UNAVAILABLE_FIELD
        out["recall_reason"] = "reference_population_positive_count_required"
    elif reference_positive_count < 0:
        raise ValueError("reference_positive_count must be non-negative")
    elif reference_positive_count == 0:
        out["recall"] = None
        out["recall_state"] = NOT_APPLICABLE
        out["recall_reason"] = "reference_population_has_no_positive_items"
    else:
        out["recall"] = _round(n_positive / reference_positive_count)
        out["recall_state"] = MEASURED
    return out


def expected_shortfall(
    values: Iterable[float | int | None],
    *,
    tail_fraction: float = 0.10,
    min_tail_n: int = 10,
) -> dict[str, Any]:
    """Lower-tail expected shortfall with the Cell-G minimum tail-count floor."""
    if not (0.0 < tail_fraction <= 1.0):
        raise ValueError("tail_fraction must be in (0,1]")
    clean = sorted(x for x in (_finite_float(v) for v in values) if x is not None)
    if not clean:
        return {"state": UNESTIMABLE, "value": None, "n": 0, "tail_n": 0}
    tail_n = int(math.ceil(tail_fraction * len(clean)))
    if tail_n < min_tail_n:
        return {
            "state": UNESTIMABLE,
            "value": None,
            "n": len(clean),
            "tail_n": tail_n,
            "min_tail_n": min_tail_n,
        }
    return {
        "state": MEASURED,
        "value": _round(float(np.mean(clean[:tail_n]))),
        "n": len(clean),
        "tail_n": tail_n,
        "tail_fraction": tail_fraction,
    }


def _ci_pair(ci: Sequence[float] | None) -> tuple[float, float] | None:
    if ci is None or len(ci) != 2:
        return None
    lo, hi = _finite_float(ci[0]), _finite_float(ci[1])
    if lo is None or hi is None or lo > hi:
        return None
    return lo, hi


def classify_flagship_lead_gate(
    *,
    delta_lead_ci: Sequence[float] | None,
    delta_actionable_ci: Sequence[float] | None,
    delta_unusable_ci: Sequence[float] | None,
) -> dict[str, Any]:
    """Frozen zero-margin PASS/MIXED/FAIL classifier from Cell-G §14.

    Positive lead/actionable is better.  Positive unusable is worse.  The caller owns
    the dependence-aware CI construction; this function only applies the frozen law.
    """
    lead = _ci_pair(delta_lead_ci)
    action = _ci_pair(delta_actionable_ci)
    unusable = _ci_pair(delta_unusable_ci)
    if lead is None or action is None or unusable is None:
        return {"state": UNESTIMABLE, "classification": None, "reason": "all_three_cis_required"}

    pass_gate = lead[0] >= 0.0 and action[0] >= 0.0 and unusable[1] <= 0.0
    fail_gate = lead[1] < 0.0 or action[1] < 0.0 or unusable[0] > 0.0
    classification = "LEAD_PASS" if pass_gate else ("LEAD_FAIL" if fail_gate else "LEAD_MIXED")
    return {
        "state": MEASURED,
        "classification": classification,
        "zero_degradation_margin": True,
        "delta_lead_ci": list(lead),
        "delta_actionable_ci": list(action),
        "delta_unusable_ci": list(unusable),
    }


def summarize_w3_status(status: Mapping[str, Any]) -> dict[str, Any]:
    """STATUS-ONLY W3 projection.

    Important: there is intentionally no outcome-loader parameter and no outcome path in
    this module.  Maturity is decided from the owner-written status surface before any
    comparative race adapter can exist.
    """
    floor = int(status.get("honest_n_floor") or 0)
    matured = int(status.get("matured_h10_sessions") or 0)
    structural = status.get("structural") if isinstance(status.get("structural"), Mapping) else {}
    outcome_blind = bool(structural.get("outcome_blind", False))
    comparison_surface = status.get("comparison_surface")
    gate_closed = outcome_blind or matured < floor or comparison_surface == "forbidden"
    return {
        "schema": status.get("schema"),
        "state": PROTECTED_OUTCOME if gate_closed else MEASURED,
        "authority": status.get("authority"),
        "promotion_authority": False,
        "comparison_surface": comparison_surface,
        "first_lawful_comparison_read": status.get("first_lawful_comparison_read"),
        "honest_n_floor": floor,
        "matured_h10_sessions": matured,
        "paired_sessions_accrued": int(status.get("paired_sessions_accrued") or 0),
        "unmatured_sessions": int(status.get("unmatured_sessions") or 0),
        "n_degraded_or_unpaired": int(status.get("n_degraded_or_unpaired") or 0),
        "n_missing": int(status.get("n_missing") or 0),
        "outcome_blind": outcome_blind,
        "outcome_files_opened": False,
        "reason": (
            "protected until owner status opens the comparison gate"
            if gate_closed
            else "owner maturity gate open; comparative outcome adapter is intentionally absent from v1"
        ),
    }


def _series_summary(series: pd.Series) -> dict[str, Any]:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if vals.empty:
        return {"state": UNAVAILABLE_FIELD, "n": 0, "mean": None, "median": None}
    return {
        "state": DESCRIPTIVE_ONLY,
        "n": int(vals.shape[0]),
        "mean": _round(vals.mean()),
        "median": _round(vals.median()),
    }


def _column_or_unavailable(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    if column not in frame.columns:
        return {"state": UNAVAILABLE_FIELD, "column": column, "n_nonnull": 0}
    n_nonnull = int(frame[column].notna().sum())
    return {
        "state": DESCRIPTIVE_ONLY if n_nonnull else UNAVAILABLE_FIELD,
        "column": column,
        "n_nonnull": n_nonnull,
        "coverage": _round(n_nonnull / len(frame)) if len(frame) else None,
    }


def _published_precision(frame: pd.DataFrame, k: int) -> dict[str, Any]:
    """US-board descriptive precision using published 0-based position, no backfill."""
    needed = {"as_of", "position", "excess_spy"}
    if not needed.issubset(frame.columns):
        return {"state": UNAVAILABLE_FIELD, "missing_columns": sorted(needed - set(frame.columns))}
    per_session: list[float] = []
    graded_top = 0
    capacity = 0
    for _, group in frame.groupby("as_of", sort=True):
        pos = pd.to_numeric(group["position"], errors="coerce")
        top = group[pos < k]
        vals = pd.to_numeric(top["excess_spy"], errors="coerce").dropna()
        capacity += k
        graded_top += int(vals.shape[0])
        if not vals.empty:
            per_session.append(float((vals > 0).mean()))
    if not per_session:
        return {"state": UNESTIMABLE, "k": k, "sessions": 0}
    return {
        "state": DESCRIPTIVE_ONLY,
        "label": "excess_spy_gt_0_existing_board_label",
        "basis": "published_rank_position_lt_k_no_survivor_backfill",
        "k": k,
        "sessions": len(per_session),
        "mean_session_precision": _round(float(np.mean(per_session))),
        "graded_topk_rows": graded_top,
        "published_capacity_rows": capacity,
        "fill_at_k": _round(graded_top / capacity) if capacity else None,
        "confirmatory": False,
    }


def summarize_us_board_frame(
    frame: pd.DataFrame,
    *,
    horizon: int = 10,
    lane: str = "buy",
    k_values: Sequence[int] = (1, 3, 5, 10),
) -> dict[str, Any]:
    """Summarize lawful matured US-board rows as DESCRIPTIVE_ONLY Cell-G telemetry.

    The board ledger does not supply canonical V4 episode first-surface timestamps or
    economic-issuer identity at this grain today.  Those metrics are returned as loud
    unavailable states rather than reverse engineered from ticker/as_of.
    """
    required = {"as_of", "ticker", "horizon", "lane"}
    missing_required = sorted(required - set(frame.columns))
    if missing_required:
        return {
            "state": HOLD_INTEGRITY,
            "reason": "board_ledger_missing_required_columns",
            "missing_columns": missing_required,
            "promotion_authority": False,
        }

    sub = frame[(frame["horizon"] == horizon) & (frame["lane"] == lane)].copy()
    if sub.empty:
        return {
            "state": NOT_MATURE,
            "horizon": horizon,
            "lane": lane,
            "n_rows": 0,
            "promotion_authority": False,
        }

    # A row is outcome-mature for the benchmark-relative descriptive read only when the
    # canonical board grader has already attached excess_spy.  Unmatured rows never get
    # converted to zero and never shrink another metric's declared eligibility silently.
    if "excess_spy" in sub.columns:
        matured = sub[sub["excess_spy"].notna()].copy()
    else:
        matured = sub.iloc[0:0].copy()

    result: dict[str, Any] = {
        "state": DESCRIPTIVE_ONLY,
        "source": "data/us_board_ledger/retro_grades.parquet",
        "source_grain": "(as_of,lane,ticker,horizon)",
        "authority": "historical/forward board telemetry; not a Cell-G family promotion read",
        "promotion_authority": False,
        "lane": lane,
        "horizon": horizon,
        "n_rows_at_lane_horizon": int(sub.shape[0]),
        "n_matured_excess_spy": int(matured.shape[0]),
        "n_subject_episodes": int(matured[["as_of", "ticker"]].drop_duplicates().shape[0])
        if not matured.empty else 0,
        "decision_dates": concentration_effective_count(matured["as_of"].tolist()),
        # Ticker is disclosed as a proxy only.  Cross-list/economic-issuer identity is a
        # separate Cell-F/A1 concern and must not be fabricated here.
        "ticker_proxy_concentration": concentration_effective_count(matured["ticker"].tolist()),
    }

    if "economic_issuer_id" in matured.columns:
        result["economic_issuer_concentration"] = concentration_effective_count(
            matured["economic_issuer_id"].tolist()
        )
    else:
        result["economic_issuer_concentration"] = {
            "state": UNAVAILABLE_FIELD,
            "reason": "economic_issuer_id_not_present; ticker proxy is not issuer identity",
        }
    for axis in ("theme_id", "species_id"):
        result[axis.replace("_id", "_concentration")] = (
            concentration_effective_count(matured[axis].tolist())
            if axis in matured.columns
            else {"state": UNAVAILABLE_FIELD, "reason": f"{axis}_not_present"}
        )

    # Coverage is measured on the full lane/horizon population, not only the rows with
    # an entry_status.  Missing actionability cannot improve the coverage percentage.
    if "entry_status" in sub.columns:
        covered = int(sub["entry_status"].notna().sum())
        coverage = covered / len(sub)
        null_reasons: dict[str, int] = {}
        if "entry_status_reason" in sub.columns:
            nulls = sub[sub["entry_status"].isna()]["entry_status_reason"].fillna("undisclosed")
            null_reasons = {str(k): int(v) for k, v in nulls.value_counts().sort_index().items()}
        result["entry_status_coverage"] = {
            "state": DESCRIPTIVE_ONLY,
            "source_contract": "entry_signal",
            "applicable_rows": int(len(sub)),
            "covered_rows": covered,
            "coverage": _round(coverage),
            "broad_coverage_floor": BROAD_COVERAGE_FLOOR,
            "broad_claim_coverage_eligible": bool(coverage >= BROAD_COVERAGE_FLOOR),
            "null_reason_counts": null_reasons,
        }
    else:
        result["entry_status_coverage"] = {
            "state": UNAVAILABLE_FIELD,
            "reason": "entry_status_not_present",
        }

    # Critical refusal: these rows are board-date observations, not canonical episode
    # first surfaces.  Computing first-surface actionability or lead from them would be
    # exactly the temporal collapse Cell G exists to prevent.
    result["first_eligible_surface"] = {
        "state": UNAVAILABLE_FIELD,
        "reason": "canonical_episode_T_eligible_not_present",
    }
    result["first_presented_surface"] = {
        "state": UNAVAILABLE_FIELD,
        "reason": "canonical_episode_T_surface_not_present",
    }
    result["actionable_at_first_surface"] = {
        "state": UNAVAILABLE_FIELD,
        "reason": "first_surface_not_reconstructable_from_board_grade_rows",
    }
    result["lead_vs_champion"] = {
        "state": UNAVAILABLE_FIELD,
        "reason": "paired_champion_challenger_first_surface_timestamps_required",
    }

    if matured.empty:
        result["benchmark_relative_return"] = {"state": NOT_MATURE, "n": 0}
        result["ranking"] = {"state": NOT_MATURE}
        result["path"] = {"state": NOT_MATURE}
        return result

    result["benchmark_relative_return"] = _series_summary(matured["excess_spy"])

    ranking: dict[str, Any] = {
        "state": DESCRIPTIVE_ONLY,
        "confirmatory": False,
        "ndcg_at_k": {
            "state": UNAVAILABLE_FIELD,
            "reason": "no_Cell-G_registered_graded_relevance_map_bound_to_this_read",
        },
        "precision_at_k": {str(k): _published_precision(matured, k) for k in k_values},
        "recall_at_k": {
            "state": UNAVAILABLE_FIELD,
            "reason": "independent_reference_population_positive_denominator_not_bound",
        },
    }
    if {"position", "excess_spy"}.issubset(matured.columns):
        pair = matured[["position", "excess_spy"]].apply(pd.to_numeric, errors="coerce").dropna()
        if pair.shape[0] >= 3:
            ranking["spearman_position_vs_excess"] = _round(
                pair["position"].corr(pair["excess_spy"], method="spearman")
            )
            ranking["orientation_note"] = "position is 0-based; negative correlation means higher slots did better"
        else:
            ranking["spearman_position_vs_excess"] = None
    result["ranking"] = ranking

    mfe_col = f"fwd_mfe_{horizon}"
    path: dict[str, Any] = {
        "state": DESCRIPTIVE_ONLY,
        "confirmatory": False,
        "path_basis": "current US board canonical grader; strictly-forward next-bar fill",
        "mfe": _series_summary(matured[mfe_col]) if mfe_col in matured.columns else {
            "state": UNAVAILABLE_FIELD,
            "column": mfe_col,
        },
        "mae_close_excess_spy": _series_summary(matured["mae_close_excess_spy"])
        if "mae_close_excess_spy" in matured.columns else {
            "state": UNAVAILABLE_FIELD,
            "column": "mae_close_excess_spy",
        },
        "r_multiple": {"state": UNAVAILABLE_FIELD, "reason": "initial_risk_unit_not_present"},
        "time_to_payoff": {"state": UNAVAILABLE_FIELD, "reason": "forward_path_series_not_present_in_grade_row"},
        "time_underwater": {"state": UNAVAILABLE_FIELD, "reason": "forward_path_series_not_present_in_grade_row"},
        "tail_loss_es10_excess_spy": expected_shortfall(matured["excess_spy"].tolist()),
    }
    result["path"] = path

    result["field_support"] = {
        "entry_status": _column_or_unavailable(sub, "entry_status"),
        "fwd_mfe": _column_or_unavailable(sub, mfe_col),
        "mae_close_excess_spy": _column_or_unavailable(sub, "mae_close_excess_spy"),
        "price_basis": _column_or_unavailable(sub, "price_basis"),
        "economic_issuer_id": _column_or_unavailable(sub, "economic_issuer_id"),
    }
    if "price_basis" in sub.columns:
        result["price_basis_counts"] = {
            str(k): int(v) for k, v in sub["price_basis"].fillna("null").value_counts().sort_index().items()
        }
    if "rank_by" in sub.columns:
        result["rank_by_values"] = sorted(str(v) for v in sub["rank_by"].dropna().unique())

    return result


def build_report(*, w3_status: Mapping[str, Any], board_frame: pd.DataFrame | None = None,
                 horizon: int = 10, lane: str = "buy") -> dict[str, Any]:
    """Assemble the read-only report.  This function performs no I/O."""
    return {
        "schema": REPORT_SCHEMA,
        "cell": "MAS-123 / Cell G",
        "promotion_authority": False,
        "writes_evaluation_store": False,
        "metric_law": "research/prophet_v4/CELL_G_FLAGSHIP_VOI_MEASUREMENT_LAW_2026-08-22.md",
        "w3": summarize_w3_status(w3_status),
        "us_board": (
            summarize_us_board_frame(board_frame, horizon=horizon, lane=lane)
            if board_frame is not None
            else {"state": UNAVAILABLE_FIELD, "reason": "board_frame_not_supplied", "promotion_authority": False}
        ),
        "promotion": {
            "authorized": False,
            "reason": "derived read-only Cell-G report; rank/predictive authority remains existing Eval/Fusion owned",
        },
    }
