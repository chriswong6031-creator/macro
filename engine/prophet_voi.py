"""Read-only Prophet flagship Value-of-Information measurement primitives.

MAS-123 / Cell G owns formulas and report semantics here, not evidence storage,
promotion, rank influence, Availability, candidate identity, or outcome clocks.

Governing law:
    research/prophet_v4/CELL_G_FLAGSHIP_VOI_MEASUREMENT_LAW_2026-08-22.md

Hard boundaries:
- no file writes or ledger mutation;
- no protected-race outcome loader (W3 support is status-only);
- missing fields are explicit states, never backfilled;
- concentration-effective counts are diagnostics, not synthetic inferential n;
- current US-board outputs are DESCRIPTIVE_ONLY, never promotion evidence.
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

MEASUREMENT_STATES = frozenset(
    {
        MEASURED,
        NOT_MATURE,
        PROTECTED_OUTCOME,
        UNAVAILABLE_FIELD,
        UNESTIMABLE,
        NOT_APPLICABLE,
        DESCRIPTIVE_ONLY,
        HOLD_INTEGRITY,
    }
)

# Source-specific adapter only; this is not the final V4 Availability vocabulary.
ENTRY_SIGNAL_ACTIONABLE_NOW = frozenset({"buy_now", "partial"})
BROAD_COVERAGE_FLOOR = 0.70
BOARD_ENTRY_STATUS_NOT_APPLICABLE_REASONS = frozenset({"lane_not_stamped"})


def _finite_float(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _round(value: Any, places: int = 6) -> float | None:
    x = _finite_float(value)
    return round(x, places) if x is not None else None


def _missing_group(value: Any) -> bool:
    if value is None:
        return True
    try:
        marker = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(marker) if isinstance(marker, (bool, np.bool_)) else False


def concentration_effective_count(values: Iterable[Any]) -> dict[str, Any]:
    """Inverse-HHI concentration diagnostic: 1 / sum(group_share ** 2)."""
    seq = list(values)
    clean = [v for v in seq if not _missing_group(v)]
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
    shares = sorted((count / n for count in counts.values()), reverse=True)
    return {
        "state": MEASURED,
        "n_rows": len(seq),
        "n_nonnull": n,
        "n_missing": len(seq) - n,
        "n_groups": len(counts),
        "n_eff": round(1.0 / sum(p * p for p in shares), 6),
        "top1_share": round(shares[0], 6),
        "top5_share": round(sum(shares[:5]), 6),
        "dominated_gt_50pct": bool(shares[0] > 0.50),
    }


def ndcg_at_k(relevance: Sequence[int | float | None], k: int) -> dict[str, Any]:
    """NDCG@K for one fixed candidate population.

    ``relevance`` is the full candidate list in presented order. DCG uses the first K;
    IDCG sorts the full same candidate set and then takes K. A high-relevance item below
    K therefore remains in the denominator rather than disappearing.
    """
    if k <= 0:
        raise ValueError("k must be positive")
    raw = list(relevance)
    if any(value is None for value in raw):
        return {"state": UNAVAILABLE_FIELD, "value": None, "reason": "missing_relevance_grade"}

    gains: list[float] = []
    for value in raw:
        x = _finite_float(value)
        if x is None or x < 0 or not float(x).is_integer():
            return {
                "state": HOLD_INTEGRITY,
                "value": None,
                "reason": "relevance_grade_must_be_nonnegative_integer",
            }
        gains.append(x)

    def dcg(items: Sequence[float]) -> float:
        return sum(
            (2.0**rel - 1.0) / math.log2(rank + 2.0)
            for rank, rel in enumerate(items)
        )

    presented = gains[:k]
    ideal = sorted(gains, reverse=True)[:k]
    idcg = dcg(ideal)
    if idcg == 0.0:
        return {
            "state": NOT_APPLICABLE,
            "value": None,
            "reason": "idcg_zero_no_relevant_items",
            "k": k,
            "n_candidates": len(gains),
            "n_ranked": len(presented),
        }
    return {
        "state": MEASURED,
        "value": round(dcg(presented) / idcg, 10),
        "k": k,
        "n_candidates": len(gains),
        "n_ranked": len(presented),
    }


def precision_recall_at_k(
    positive: Sequence[bool | None],
    k: int,
    *,
    reference_positive_count: int | None = None,
) -> dict[str, Any]:
    """Top-K precision/fill plus recall against an explicit reference denominator."""
    if k <= 0:
        raise ValueError("k must be positive")
    top = list(positive[:k])
    if any(value is None for value in top):
        return {"state": UNAVAILABLE_FIELD, "reason": "missing_positive_label"}

    n_presented = len(top)
    n_positive = sum(bool(value) for value in top)
    out: dict[str, Any] = {
        "state": MEASURED,
        "k": k,
        "n_presented": n_presented,
        "n_positive_topk": n_positive,
        "precision_presented": _round(n_positive / n_presented) if n_presented else None,
        "fill_at_k": _round(n_presented / k),
    }
    if reference_positive_count is None:
        out.update(
            {
                "recall": None,
                "recall_state": UNAVAILABLE_FIELD,
                "recall_reason": "reference_population_positive_count_required",
            }
        )
    elif reference_positive_count < 0:
        raise ValueError("reference_positive_count must be non-negative")
    elif reference_positive_count == 0:
        out.update(
            {
                "recall": None,
                "recall_state": NOT_APPLICABLE,
                "recall_reason": "reference_population_has_no_positive_items",
            }
        )
    else:
        out.update(
            {
                "recall": _round(n_positive / reference_positive_count),
                "recall_state": MEASURED,
            }
        )
    return out


def expected_shortfall(
    values: Iterable[float | int | None],
    *,
    tail_fraction: float = 0.10,
    min_tail_n: int = 10,
) -> dict[str, Any]:
    """Lower-tail expected shortfall with an explicit minimum tail count."""
    if not (0.0 < tail_fraction <= 1.0):
        raise ValueError("tail_fraction must be in (0,1]")
    clean = sorted(x for x in (_finite_float(value) for value in values) if x is not None)
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
    """Apply the frozen zero-degradation flagship lead gate."""
    lead = _ci_pair(delta_lead_ci)
    actionable = _ci_pair(delta_actionable_ci)
    unusable = _ci_pair(delta_unusable_ci)
    if lead is None or actionable is None or unusable is None:
        return {
            "state": UNESTIMABLE,
            "classification": None,
            "reason": "all_three_cis_required",
        }

    passed = lead[0] >= 0.0 and actionable[0] >= 0.0 and unusable[1] <= 0.0
    failed = lead[1] < 0.0 or actionable[1] < 0.0 or unusable[0] > 0.0
    return {
        "state": MEASURED,
        "classification": "LEAD_PASS" if passed else ("LEAD_FAIL" if failed else "LEAD_MIXED"),
        "zero_degradation_margin": True,
        "delta_lead_ci": list(lead),
        "delta_actionable_ci": list(actionable),
        "delta_unusable_ci": list(unusable),
    }


def _w3_integrity_error(status: Mapping[str, Any]) -> str | None:
    if status.get("schema") != "us.prophet_w3_status/v1":
        return "unexpected_or_missing_w3_status_schema"
    try:
        floor = int(status["honest_n_floor"])
        matured = int(status["matured_h10_sessions"])
    except (KeyError, TypeError, ValueError):
        return "missing_or_invalid_w3_maturity_fields"
    if floor <= 0 or matured < 0:
        return "invalid_w3_maturity_floor_or_count"
    structural = status.get("structural")
    if not isinstance(structural, Mapping) or not isinstance(structural.get("outcome_blind"), bool):
        return "missing_w3_structural_outcome_blind_gate"
    if status.get("comparison_surface") is None:
        return "missing_w3_comparison_surface_gate"
    return None


def summarize_w3_status(status: Mapping[str, Any]) -> dict[str, Any]:
    """Fail-closed W3 status projection with no outcome adapter."""
    integrity_error = _w3_integrity_error(status)
    if integrity_error is not None:
        return {
            "schema": status.get("schema"),
            "state": HOLD_INTEGRITY,
            "gate_state": "CLOSED_INTEGRITY",
            "promotion_authority": False,
            "outcome_files_opened": False,
            "reason": integrity_error,
        }

    floor = int(status["honest_n_floor"])
    matured = int(status["matured_h10_sessions"])
    outcome_blind = bool(status["structural"]["outcome_blind"])
    comparison_surface = status.get("comparison_surface")
    gate_closed = outcome_blind or matured < floor or comparison_surface == "forbidden"
    return {
        "schema": status.get("schema"),
        "state": PROTECTED_OUTCOME if gate_closed else UNAVAILABLE_FIELD,
        "gate_state": "CLOSED_PROTECTED" if gate_closed else "OPEN_OWNER_GATE_ADAPTER_ABSENT",
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
            else "owner maturity gate is open, but v1 has no comparative outcome adapter"
        ),
    }


def _series_summary(series: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return {"state": UNAVAILABLE_FIELD, "n": 0, "mean": None, "median": None}
    return {
        "state": DESCRIPTIVE_ONLY,
        "n": int(values.shape[0]),
        "mean": _round(values.mean()),
        "median": _round(values.median()),
    }


def _column_or_unavailable(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    if column not in frame.columns:
        return {"state": UNAVAILABLE_FIELD, "column": column, "n_nonnull": 0}
    nonnull = int(frame[column].notna().sum())
    return {
        "state": DESCRIPTIVE_ONLY if nonnull else UNAVAILABLE_FIELD,
        "column": column,
        "n_nonnull": nonnull,
        "coverage": _round(nonnull / len(frame)) if len(frame) else None,
    }


def _published_precision(frame: pd.DataFrame, k: int) -> dict[str, Any]:
    """Board top-K telemetry that never backfills a missing higher-slot outcome."""
    needed = {"as_of", "position", "excess_spy"}
    if not needed.issubset(frame.columns):
        return {"state": UNAVAILABLE_FIELD, "missing_columns": sorted(needed - set(frame.columns))}
    if k <= 0:
        raise ValueError("k must be positive")

    complete_session_precision: list[float] = []
    gradable_hits = 0
    graded_top = 0
    presented_top = 0
    capacity = 0
    sessions_total = 0

    for _, group in frame.groupby("as_of", sort=True):
        sessions_total += 1
        positions = pd.to_numeric(group["position"], errors="coerce")
        top = group.loc[positions < k]
        outcomes = pd.to_numeric(top["excess_spy"], errors="coerce")
        graded = outcomes.dropna()
        capacity += k
        presented_top += int(top.shape[0])
        graded_top += int(graded.shape[0])
        gradable_hits += int((graded > 0).sum())
        if len(top) and len(graded) == len(top):
            complete_session_precision.append(float((graded > 0).mean()))

    if sessions_total == 0:
        return {"state": UNESTIMABLE, "k": k, "sessions_total": 0}

    all_presented_graded = presented_top > 0 and graded_top == presented_top
    return {
        "state": DESCRIPTIVE_ONLY,
        "label": "excess_spy_gt_0_existing_board_label",
        "basis": "published_rank_position_lt_k_no_survivor_backfill",
        "k": k,
        "sessions_total": sessions_total,
        "sessions_fully_graded_topk": len(complete_session_precision),
        "mean_session_precision_fully_graded": (
            _round(float(np.mean(complete_session_precision))) if complete_session_precision else None
        ),
        "precision_presented": _round(gradable_hits / presented_top) if all_presented_graded else None,
        "precision_presented_state": MEASURED if all_presented_graded else UNAVAILABLE_FIELD,
        "pooled_precision_gradable_only": _round(gradable_hits / graded_top) if graded_top else None,
        "presented_topk_rows": presented_top,
        "graded_topk_rows": graded_top,
        "published_capacity_rows": capacity,
        "fill_at_k": _round(presented_top / capacity) if capacity else None,
        "outcome_coverage_within_presented": _round(graded_top / presented_top) if presented_top else None,
        "confirmatory": False,
    }


def _mean_session_spearman(frame: pd.DataFrame) -> dict[str, Any]:
    needed = {"as_of", "position", "excess_spy"}
    if not needed.issubset(frame.columns):
        return {"state": UNAVAILABLE_FIELD, "missing_columns": sorted(needed - set(frame.columns))}

    values: list[float] = []
    for _, group in frame.groupby("as_of", sort=True):
        pair = group[["position", "excess_spy"]].apply(pd.to_numeric, errors="coerce").dropna()
        if pair.shape[0] < 3 or pair["position"].nunique() < 2 or pair["excess_spy"].nunique() < 2:
            continue
        correlation = pair["position"].corr(pair["excess_spy"], method="spearman")
        if pd.notna(correlation):
            values.append(float(correlation))

    if not values:
        return {"state": UNESTIMABLE, "n_sessions": 0, "value": None}
    return {
        "state": DESCRIPTIVE_ONLY,
        "n_sessions": len(values),
        "value": _round(float(np.mean(values))),
        "aggregation": "unweighted_mean_of_decision_session_spearman",
        "orientation_note": "position is 0-based; negative means higher published slots did better",
    }


def _entry_status_coverage(frame: pd.DataFrame) -> dict[str, Any]:
    if "entry_status" not in frame.columns:
        return {"state": UNAVAILABLE_FIELD, "reason": "entry_status_not_present"}

    if "entry_status_reason" in frame.columns:
        reasons = frame["entry_status_reason"].fillna("undisclosed").astype(str)
    else:
        reasons = pd.Series("undisclosed", index=frame.index, dtype="object")

    not_applicable = frame["entry_status"].isna() & reasons.isin(
        BOARD_ENTRY_STATUS_NOT_APPLICABLE_REASONS
    )
    applicable = frame.loc[~not_applicable]
    applicable_reasons = reasons.loc[applicable.index]
    missing_status = applicable["entry_status"].isna()
    null_reasons = applicable_reasons.loc[missing_status]

    denominator = int(len(applicable))
    covered = int(applicable["entry_status"].notna().sum())
    coverage = covered / denominator if denominator else None
    return {
        "state": DESCRIPTIVE_ONLY if denominator else NOT_APPLICABLE,
        "source_contract": "entry_signal",
        "all_rows": int(len(frame)),
        "not_applicable_rows": int(not_applicable.sum()),
        "applicable_rows": denominator,
        "covered_rows": covered,
        "coverage": _round(coverage),
        "broad_coverage_floor": BROAD_COVERAGE_FLOOR,
        "broad_claim_coverage_eligible": bool(
            coverage is not None and coverage >= BROAD_COVERAGE_FLOOR
        ),
        "null_reason_counts": {
            str(key): int(value)
            for key, value in null_reasons.value_counts().sort_index().items()
        },
    }


def summarize_us_board_frame(
    frame: pd.DataFrame,
    *,
    horizon: int = 10,
    lane: str = "buy",
    k_values: Sequence[int] = (1, 3, 5, 10),
) -> dict[str, Any]:
    """Project existing board truth without relabelling board observations as episodes."""
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

    matured = (
        sub.loc[sub["excess_spy"].notna()].copy()
        if "excess_spy" in sub.columns
        else sub.iloc[0:0].copy()
    )
    result: dict[str, Any] = {
        "state": DESCRIPTIVE_ONLY,
        "source": "data/us_board_ledger/retro_grades.parquet",
        "source_grain": "(as_of,lane,ticker,horizon)",
        "authority": "existing board telemetry; not a Cell-G family promotion read",
        "promotion_authority": False,
        "lane": lane,
        "horizon": horizon,
        "n_rows_at_lane_horizon": int(sub.shape[0]),
        "n_matured_excess_spy": int(matured.shape[0]),
        "n_board_subject_observations": (
            int(matured[["as_of", "ticker"]].drop_duplicates().shape[0])
            if not matured.empty
            else 0
        ),
        "decision_dates": concentration_effective_count(matured["as_of"].tolist()),
        "ticker_proxy_concentration": concentration_effective_count(matured["ticker"].tolist()),
        "entry_status_coverage": _entry_status_coverage(sub),
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

    # These refusals are load-bearing: board-date rows are not canonical first surfaces.
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
    result["ranking"] = {
        "state": DESCRIPTIVE_ONLY,
        "confirmatory": False,
        "ndcg_at_k": {
            "state": UNAVAILABLE_FIELD,
            "reason": "no_Cell-G_registered_graded_relevance_map_bound_to_this_read",
        },
        "precision_at_k": {str(k): _published_precision(sub, k) for k in k_values},
        "recall_at_k": {
            "state": UNAVAILABLE_FIELD,
            "reason": "independent_reference_population_positive_denominator_not_bound",
        },
        "session_spearman_position_vs_excess": _mean_session_spearman(sub),
    }

    mfe_column = f"fwd_mfe_{horizon}"
    result["path"] = {
        "state": DESCRIPTIVE_ONLY,
        "confirmatory": False,
        "path_basis": "current US board canonical grader; strictly-forward next-bar fill",
        "mfe": (
            _series_summary(matured[mfe_column])
            if mfe_column in matured.columns
            else {"state": UNAVAILABLE_FIELD, "column": mfe_column}
        ),
        "mae_close_excess_spy": (
            _series_summary(matured["mae_close_excess_spy"])
            if "mae_close_excess_spy" in matured.columns
            else {"state": UNAVAILABLE_FIELD, "column": "mae_close_excess_spy"}
        ),
        "r_multiple": {
            "state": UNAVAILABLE_FIELD,
            "reason": "initial_risk_unit_not_present",
        },
        "time_to_payoff": {
            "state": UNAVAILABLE_FIELD,
            "reason": "forward_path_series_not_present_in_grade_row",
        },
        "time_underwater": {
            "state": UNAVAILABLE_FIELD,
            "reason": "forward_path_series_not_present_in_grade_row",
        },
        "tail_loss_es10_excess_spy": expected_shortfall(matured["excess_spy"].tolist()),
    }

    result["field_support"] = {
        "entry_status": _column_or_unavailable(sub, "entry_status"),
        "fwd_mfe": _column_or_unavailable(sub, mfe_column),
        "mae_close_excess_spy": _column_or_unavailable(sub, "mae_close_excess_spy"),
        "price_basis": _column_or_unavailable(sub, "price_basis"),
        "economic_issuer_id": _column_or_unavailable(sub, "economic_issuer_id"),
    }
    if "price_basis" in sub.columns:
        basis_counts = {
            str(key): int(value)
            for key, value in sub["price_basis"].fillna("null").value_counts().sort_index().items()
        }
        result["price_basis_counts"] = basis_counts
        result["price_basis_mixed"] = len(basis_counts) > 1
    else:
        result["price_basis_mixed"] = None
    if "rank_by" in sub.columns:
        result["rank_by_values"] = sorted(str(value) for value in sub["rank_by"].dropna().unique())

    return result


def build_report(
    *,
    w3_status: Mapping[str, Any],
    board_frame: pd.DataFrame | None = None,
    horizon: int = 10,
    lane: str = "buy",
) -> dict[str, Any]:
    """Assemble the read-only report; this function performs no I/O."""
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
            else {
                "state": UNAVAILABLE_FIELD,
                "reason": "board_frame_not_supplied",
                "promotion_authority": False,
            }
        ),
        "promotion": {
            "authorized": False,
            "reason": "derived read-only Cell-G report; rank/predictive authority remains existing Eval/Fusion owned",
        },
    }
