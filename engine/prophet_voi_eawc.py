"""Executable Early Actionable Winner Capture primitives for MAS-123 / Cell G.

These are pure claim-level formulas. They deliberately accept owner-resolved session
ordinals / first-surface states rather than discovering episodes, reading ledgers, or
reconstructing Availability. That keeps the frozen measurement law executable without
creating a second temporal or identity system.

The current flagship VOI report may still return ``UNAVAILABLE_FIELD`` for these metrics
when canonical V4 first-surface fields do not exist. Synthetic tests prove the formulas
without peeking at protected prospective outcomes.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from engine.prophet_voi import (
    DESCRIPTIVE_ONLY,
    HOLD_INTEGRITY,
    MEASURED,
    NOT_APPLICABLE,
    UNAVAILABLE_FIELD,
    UNESTIMABLE,
)


def _aligned(*values: Sequence[Any]) -> int:
    lengths = {len(value) for value in values}
    if len(lengths) != 1:
        raise ValueError("all subject-level vectors must have equal length")
    return next(iter(lengths), 0)


def _ordinal(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        x = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    try:
        if float(value) != float(x):
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    return x


def _is_bool(value: Any) -> bool:
    return isinstance(value, (bool, np.bool_))


def _invalid_bool_count(values: Sequence[Any], *, allow_none: bool) -> int:
    return sum(
        not (_is_bool(value) or (allow_none and value is None))
        for value in values
    )


def _is_true(value: Any) -> bool:
    return _is_bool(value) and bool(value)


def paired_surface_lead_sessions(
    *,
    challenger_first_session: Sequence[int | None],
    champion_first_session: Sequence[int | None],
) -> dict[str, Any]:
    """Pairwise earliness without imputing one-sided captures.

    Inputs are owner-resolved trading-session ordinals for the same fixed reference
    episodes. The function is valid for either ``T_eligible`` or ``T_surface``; the
    caller names which clock it supplied in the experiment registration.

    Paired lead is ``champion - challenger`` so positive means the challenger surfaced
    earlier. Challenger-only/champion-only/neither observations are reported as capture
    cells and never converted into arbitrary large lead values.
    """
    n = _aligned(challenger_first_session, champion_first_session)
    paired: list[int] = []
    challenger_only = 0
    champion_only = 0
    neither = 0
    invalid = 0

    for raw_challenger, raw_champion in zip(challenger_first_session, champion_first_session):
        challenger = _ordinal(raw_challenger)
        champion = _ordinal(raw_champion)
        if raw_challenger is not None and challenger is None:
            invalid += 1
            continue
        if raw_champion is not None and champion is None:
            invalid += 1
            continue
        if challenger is not None and champion is not None:
            paired.append(champion - challenger)
        elif challenger is not None:
            challenger_only += 1
        elif champion is not None:
            champion_only += 1
        else:
            neither += 1

    if invalid:
        return {
            "state": HOLD_INTEGRITY,
            "reference_subjects": n,
            "invalid_session_ordinals": invalid,
            "reason": "first-surface sessions must be integral owner-resolved ordinals",
        }

    out: dict[str, Any] = {
        "state": MEASURED if paired else UNESTIMABLE,
        "reference_subjects": n,
        "paired_subjects": len(paired),
        "challenger_only": challenger_only,
        "champion_only": champion_only,
        "neither": neither,
        "one_sided_lead_imputed": False,
        "lead_orientation": "positive_means_challenger_earlier",
    }
    if paired:
        out.update(
            {
                "mean_lead_sessions": round(float(np.mean(paired)), 6),
                "median_lead_sessions": round(float(np.median(paired)), 6),
                "min_lead_sessions": int(min(paired)),
                "max_lead_sessions": int(max(paired)),
            }
        )
    else:
        out.update(
            {
                "mean_lead_sessions": None,
                "median_lead_sessions": None,
                "min_lead_sessions": None,
                "max_lead_sessions": None,
            }
        )
    return out


def early_actionable_capture_recall(
    *,
    positive_label: Sequence[bool | None],
    surfaced: Sequence[bool | None],
    actionable_at_first_surface: Sequence[bool | None],
) -> dict[str, Any]:
    """Full-denominator Early Actionable Winner Capture recall.

    The denominator is every registered positive episode in the independent reference
    population. A missed surface, blocked/missing actionability, or explicit refusal is
    not dropped: it contributes zero to the numerator and remains in the denominator.
    Unknown *outcome labels* are different — the metric is not legally settled and is
    therefore unavailable rather than treating unknown outcomes as losses.
    """
    n = _aligned(positive_label, surfaced, actionable_at_first_surface)
    invalid_labels = _invalid_bool_count(positive_label, allow_none=True)
    invalid_surface = _invalid_bool_count(surfaced, allow_none=True)
    invalid_actionability = _invalid_bool_count(actionable_at_first_surface, allow_none=True)
    if invalid_labels or invalid_surface or invalid_actionability:
        return {
            "state": HOLD_INTEGRITY,
            "reference_subjects": n,
            "reason": "eawc_owner_states_must_be_boolean_or_null",
            "invalid_positive_labels": invalid_labels,
            "invalid_surface_states": invalid_surface,
            "invalid_actionability_states": invalid_actionability,
        }
    if any(label is None for label in positive_label):
        return {
            "state": UNAVAILABLE_FIELD,
            "reference_subjects": n,
            "reason": "positive_label_missing_in_reference_population",
        }

    positives = [index for index, label in enumerate(positive_label) if _is_true(label)]
    denominator = len(positives)
    if denominator == 0:
        return {
            "state": NOT_APPLICABLE,
            "reference_subjects": n,
            "positive_reference_subjects": 0,
            "value": None,
            "reason": "reference_population_has_no_registered_positives",
        }

    captured_actionable = 0
    missed_surface = 0
    missing_or_blocked_actionability = 0
    surfaced_not_actionable = 0
    for index in positives:
        if not _is_true(surfaced[index]):
            missed_surface += 1
            continue
        if _is_true(actionable_at_first_surface[index]):
            captured_actionable += 1
        elif actionable_at_first_surface[index] is None:
            missing_or_blocked_actionability += 1
        else:
            surfaced_not_actionable += 1

    return {
        "state": MEASURED,
        "reference_subjects": n,
        "positive_reference_subjects": denominator,
        "captured_actionable": captured_actionable,
        "missed_surface": missed_surface,
        "missing_or_blocked_actionability": missing_or_blocked_actionability,
        "surfaced_not_actionable": surfaced_not_actionable,
        "value": round(captured_actionable / denominator, 6),
        "denominator_includes_missed_and_blocked": True,
    }


def first_surface_actionability_rate(
    *,
    applicable_first_surface: Sequence[bool],
    actionable: Sequence[bool | None],
) -> dict[str, Any]:
    """Actionability rate over all applicable first surfaces.

    Missing/blocked owner actionability remains in the denominator and does not count as
    actionable. By-design non-applicable subjects are excluded explicitly by the caller.
    """
    n = _aligned(applicable_first_surface, actionable)
    invalid_applicability = _invalid_bool_count(applicable_first_surface, allow_none=False)
    invalid_actionability = _invalid_bool_count(actionable, allow_none=True)
    if invalid_applicability or invalid_actionability:
        return {
            "state": HOLD_INTEGRITY,
            "reference_subjects": n,
            "reason": "first_surface_owner_states_have_invalid_type",
            "invalid_applicability_states": invalid_applicability,
            "invalid_actionability_states": invalid_actionability,
        }

    denominator = sum(_is_true(value) for value in applicable_first_surface)
    if denominator == 0:
        return {
            "state": NOT_APPLICABLE,
            "reference_subjects": n,
            "applicable_first_surfaces": 0,
            "value": None,
        }

    numerator = 0
    missing_or_blocked = 0
    explicit_not_actionable = 0
    for applicable, status in zip(applicable_first_surface, actionable):
        if not _is_true(applicable):
            continue
        if _is_true(status):
            numerator += 1
        elif status is None:
            missing_or_blocked += 1
        else:
            explicit_not_actionable += 1

    return {
        "state": MEASURED,
        "reference_subjects": n,
        "applicable_first_surfaces": denominator,
        "actionable": numerator,
        "missing_or_blocked": missing_or_blocked,
        "explicit_not_actionable": explicit_not_actionable,
        "value": round(numerator / denominator, 6),
        "missing_in_denominator": True,
    }


def unusable_or_unknown_at_first_surface_rate(
    *,
    applicable_first_surface: Sequence[bool],
    chased_or_closed: Sequence[bool | None],
) -> dict[str, Any]:
    """Owner-stamped opportunity-consumption guardrail.

    ``True`` means the canonical owner says chased/closed/late. ``False`` means known not
    consumed. ``None`` means blocked/missing/unknown and is conservatively counted as
    unusable-or-unknown in the numerator. This is the promotion guardrail counterpart to
    the more permissive descriptive ex-post "move consumed" diagnostic.
    """
    n = _aligned(applicable_first_surface, chased_or_closed)
    invalid_applicability = _invalid_bool_count(applicable_first_surface, allow_none=False)
    invalid_chase = _invalid_bool_count(chased_or_closed, allow_none=True)
    if invalid_applicability or invalid_chase:
        return {
            "state": HOLD_INTEGRITY,
            "reference_subjects": n,
            "reason": "first_surface_chase_states_have_invalid_type",
            "invalid_applicability_states": invalid_applicability,
            "invalid_chase_states": invalid_chase,
        }

    denominator = sum(_is_true(value) for value in applicable_first_surface)
    if denominator == 0:
        return {
            "state": NOT_APPLICABLE,
            "reference_subjects": n,
            "applicable_first_surfaces": 0,
            "value": None,
        }

    chased = 0
    unknown = 0
    for applicable, state in zip(applicable_first_surface, chased_or_closed):
        if not _is_true(applicable):
            continue
        if _is_true(state):
            chased += 1
        elif state is None:
            unknown += 1

    return {
        "state": MEASURED,
        "reference_subjects": n,
        "applicable_first_surfaces": denominator,
        "chased_or_closed": chased,
        "unknown_or_blocked": unknown,
        "known_unusable_or_unknown": chased + unknown,
        "value": round((chased + unknown) / denominator, 6),
        "unknown_counts_as_unusable_guardrail": True,
    }


def realized_r_multiple(
    *,
    direction_signed_pnl: float | int | None,
    entry_price: float | int | None,
    initial_invalidation_price: float | int | None,
) -> dict[str, Any]:
    """Realized R using only decision-time initial risk.

    The caller supplies direction-signed realized PnL in price/return units compatible
    with the entry/invalidation distance. A missing or zero initial risk is unavailable;
    this function never derives a retrospective stop.
    """
    try:
        pnl = float(direction_signed_pnl)
        entry = float(entry_price)
        invalidation = float(initial_invalidation_price)
    except (TypeError, ValueError, OverflowError):
        return {"state": UNAVAILABLE_FIELD, "value": None, "reason": "initial_risk_fields_missing"}
    if not all(math.isfinite(value) for value in (pnl, entry, invalidation)):
        return {"state": UNAVAILABLE_FIELD, "value": None, "reason": "initial_risk_fields_nonfinite"}
    risk = abs(entry - invalidation)
    if risk == 0.0:
        return {"state": UNAVAILABLE_FIELD, "value": None, "reason": "initial_risk_zero"}
    return {
        "state": MEASURED,
        "value": round(pnl / risk, 10),
        "initial_risk_unit": risk,
        "retrospective_stop_derived": False,
    }


def time_to_payoff_r(
    *,
    strictly_forward_r_path: Sequence[float | int | None],
    threshold_r: float,
) -> dict[str, Any]:
    """First strictly-forward session reaching a preregistered +xR payoff threshold.

    Non-hits are right-censored at the supplied path horizon; they are never dropped from
    the sample. Missing path points make the subject unavailable because silently
    compressing the clock would invent an earlier hit.
    """
    if not math.isfinite(float(threshold_r)) or threshold_r <= 0:
        raise ValueError("threshold_r must be finite and positive")
    horizon = len(strictly_forward_r_path)
    if horizon == 0:
        return {"state": UNESTIMABLE, "hit": False, "censored": True, "horizon_sessions": 0}

    path: list[float] = []
    for value in strictly_forward_r_path:
        if value is None:
            return {"state": UNAVAILABLE_FIELD, "reason": "forward_path_has_missing_session"}
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            return {"state": HOLD_INTEGRITY, "reason": "forward_path_non_numeric"}
        if not math.isfinite(numeric):
            return {"state": HOLD_INTEGRITY, "reason": "forward_path_nonfinite"}
        path.append(numeric)

    for session_index, value in enumerate(path, start=1):
        if value >= threshold_r:
            return {
                "state": MEASURED,
                "hit": True,
                "censored": False,
                "threshold_r": float(threshold_r),
                "time_to_payoff_sessions": session_index,
                "horizon_sessions": horizon,
            }
    return {
        "state": MEASURED,
        "hit": False,
        "censored": True,
        "threshold_r": float(threshold_r),
        "time_to_payoff_sessions": None,
        "horizon_sessions": horizon,
        "censor_at_session": horizon,
    }


def eventual_move_consumed_fraction(
    *,
    favorable_move_at_first_surface: float | int | None,
    future_mfe: float | int | None,
) -> dict[str, Any]:
    """Ex-post chase diagnostic only; never a live actionability or promotion gate."""
    try:
        consumed = float(favorable_move_at_first_surface)
        mfe = float(future_mfe)
    except (TypeError, ValueError, OverflowError):
        return {"state": UNAVAILABLE_FIELD, "value": None}
    if not math.isfinite(consumed) or not math.isfinite(mfe) or mfe <= 0.0:
        return {
            "state": UNESTIMABLE,
            "value": None,
            "reason": "future_mfe_must_be_positive_and_finite",
            "confirmatory": False,
        }
    return {
        "state": DESCRIPTIVE_ONLY,
        "value": round(consumed / mfe, 10),
        "confirmatory": False,
        "authority": "diagnostic_only_ex_post_denominator",
    }
