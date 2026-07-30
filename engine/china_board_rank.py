"""China Prophet v2 board scoring and lane admission.

The module deliberately separates three decisions which the old board conflated:

* ``prophet_score`` orders names using a small, frozen set of features.
* execution checks decide whether a scored name may be *featured now*.
* lifecycle lanes preserve every raw gate-eligible name instead of silently dropping it.

The score is a transparent priority heuristic, not a calibrated return forecast.  Only
the five components in :data:`SCORE_WEIGHTS` have score authority.  Residual alpha,
the legacy setup score, sector/narrative context, fundamental quality, low volatility,
microstructure, liquidity, and risk sizing never add score.  Microstructure and
liquidity are used solely as execution/admission safeguards.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
import math
from typing import Any, Iterable, Mapping

from engine import signal_gate


BOARD_DEFINITION = "cn_prophet_v2"
FEATURED_CAP = 24
SECTOR_CAP = 4
ADV_FLOOR_YI = 0.5
NON_STOCK_SECTORS = frozenset(("Sector ETF", "Index"))

SCORE_WEIGHTS = {
    "signal": 35.0,
    "entry": 25.0,
    "runway": 20.0,
    "bottom_quality": 10.0,
    "reversal_member": 10.0,
}

# These values are frozen definition inputs, rather than fitted coefficients.
_SIGNAL_BASE = {"T2": 1.0, "T1": 0.9, "T3": 0.7}
_ENTRY_VALUE = {
    "buy_now": 1.0,
    "partial": 0.9,
    "buy_soon": 0.8,
    "hold": 0.65,
    "wait_pullback": 0.55,
    "later": 0.55,
    "await": 0.45,
    "await_confluence": 0.45,
    "watch": 0.4,
    "bounce_wait": 0.35,
    "extended": 0.0,
    "topping": 0.0,
    "blocked": 0.0,
    "exit": 0.0,
    "avoid": 0.0,
}
_FEATURED_ENTRY_STATUSES = frozenset(("buy_now", "partial"))
_ZERO_SCORE_AUTHORITY = (
    "residual_alpha",
    "setup",
    "sector_turn",
    "narrative",
    "quality",
    "low_vol",
    "risk_sizing",
)


def _clip01(value: Any) -> float:
    """Return a finite float clipped to ``[0, 1]``; malformed values become zero."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_date(value: Any) -> str | None:
    """Normalise common date values without making the ranking depend on pandas."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else (text or None)


def _mapped(
    mapping: Mapping[str, Any] | None,
    ticker: str,
    fallback: Any,
) -> Any:
    """Use an explicitly supplied mapping value (including ``None``), else fallback."""
    if mapping is not None and ticker in mapping:
        return mapping[ticker]
    return fallback


def stock_panel_asof(
    universe: Iterable[tuple[Any, Any, Any, Any, Any]],
    stock_tickers: set[str] | frozenset[str],
) -> Any:
    """Return the freshest stock session, ignoring context ETFs and indices."""
    return max(
        (
            close.last_valid_index()
            for ticker, close, *_rest in universe
            if ticker in stock_tickers
            and close is not None
            and close.last_valid_index() is not None
        ),
        default=None,
    )


def _signal_value(verdict: Mapping[str, Any] | None) -> float:
    verdict = verdict or {}
    tier = verdict.get("tier_cascade")
    value = _SIGNAL_BASE.get(str(tier), 0.0)
    if verdict.get("provisional"):
        value = max(0.0, value - 0.1)

    ticks = _finite_float(verdict.get("ticks"))
    if ticks == 2:
        value *= 0.85

    if tier == "T3":
        bars = _finite_float(verdict.get("bars_to_cross"))
        if bars is not None:
            if bars >= 2:
                value *= 0.70
            elif bars == 1:
                value *= 0.85
    return _clip01(value)


def _entry_value(entry: Mapping[str, Any] | None) -> float:
    status = str((entry or {}).get("status") or "").strip().lower()
    return _ENTRY_VALUE.get(status, 0.0)


def _potential(profile: Mapping[str, Any] | None) -> Mapping[str, Any]:
    profile = profile or {}
    potential = profile.get("potential")
    if isinstance(potential, Mapping):
        return potential
    conviction = profile.get("conviction")
    if isinstance(conviction, Mapping) and isinstance(conviction.get("potential"), Mapping):
        return conviction["potential"]
    return {}


def _runway_value(
    profile: Mapping[str, Any] | None,
    extension: Mapping[str, Any] | None,
) -> float:
    components = _potential(profile).get("components") or {}
    fuel = _clip01(components.get("fuel"))
    extension_score = _finite_float((extension or {}).get("score"))
    # Unknown extension evidence must not receive best-case "not extended"
    # points. It remains rankable on observed fuel but earns zero on this leg.
    not_extended = (
        1.0 - _clip01(extension_score)
        if extension_score is not None
        else 0.0
    )
    return _clip01(0.6 * fuel + 0.4 * not_extended)


def _bottom_quality_value(row: Mapping[str, Any]) -> float:
    coiled = row.get("coiled") or {}
    if coiled.get("star"):
        return 1.0
    if coiled.get("coiled"):
        return 0.8
    if coiled.get("washout_ctx") or row.get("washout_ctx"):
        return 0.4
    return 0.0


def _reversal_context(
    rows: list[dict],
    authoritative_by: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[int, dict[str, Any]]:
    """Return row-indexed within-sector reversal ranks over the full supplied pool.

    A higher ``rev_z`` is the deeper relative dip in ``engine.china_reversal``.
    Ties are resolved by ticker, making both the percentile and the top-quintile flag
    deterministic.  Missing reversal observations remain explicit ``None`` values.
    """
    if authoritative_by is not None:
        result: dict[int, dict[str, Any]] = {}
        for index, row in enumerate(rows):
            ctx = authoritative_by.get(str(row.get("ticker") or "")) or {}
            rev_z = _finite_float(ctx.get("rev_z"))
            rank = _finite_float(ctx.get("sector_rank"))
            count = _finite_float(ctx.get("sector_n"))
            rank_i = int(rank) if rank is not None and rank >= 1 else None
            count_i = int(count) if count is not None and count >= 1 else None
            member = bool(ctx.get("deepest_quintile")) if ctx else False
            if rank_i is not None and count_i is not None:
                member = rank_i <= max(1, count_i // 5)
            percentile = None
            if rank_i is not None and count_i is not None:
                percentile = (
                    1.0 if count_i == 1
                    else 1.0 - (rank_i - 1) / (count_i - 1)
                )
            result[index] = {
                "rev_z": rev_z,
                "ret_3m": _finite_float(ctx.get("ret_3m")),
                "rev_percentile": (
                    round(_clip01(percentile), 6) if percentile is not None else None
                ),
                "reversal_member": member,
                "reversal_sector_rank": rank_i,
                "reversal_sector_n": count_i,
            }
        return result

    grouped: dict[str, list[tuple[int, str, float]]] = defaultdict(list)
    for index, row in enumerate(rows):
        rev_z = _finite_float(row.get("rev_z"))
        if rev_z is None:
            continue
        sector = str(row.get("sector") or "—")
        grouped[sector].append((index, str(row.get("ticker") or ""), rev_z))

    result: dict[int, dict[str, Any]] = {
        index: {
            "rev_z": _finite_float(row.get("rev_z")),
            "ret_3m": _finite_float(row.get("ret_3m")),
            "rev_percentile": None,
            "reversal_member": False,
            "reversal_sector_rank": None,
            "reversal_sector_n": None,
        }
        for index, row in enumerate(rows)
    }
    for members in grouped.values():
        ordered = sorted(members, key=lambda item: (-item[2], item[1]))
        count = len(ordered)
        # Match the engine's pre-registered "sector_rank <= sector_n // 5" convention.
        deepest_n = max(1, count // 5)
        for rank, (index, _ticker, _rev_z) in enumerate(ordered, start=1):
            percentile = 1.0 if count == 1 else 1.0 - (rank - 1) / (count - 1)
            result[index].update(
                rev_percentile=round(percentile, 6),
                reversal_member=rank <= deepest_n,
                reversal_sector_rank=rank,
                reversal_sector_n=count,
            )
    return result


def enrich_and_score_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    verdict_by: Mapping[str, Mapping[str, Any]] | None = None,
    profile_by: Mapping[str, Mapping[str, Any]] | None = None,
    entry_by: Mapping[str, Mapping[str, Any]] | None = None,
    risk_by: Mapping[str, Mapping[str, Any]] | None = None,
    rev_z_by: Mapping[str, float] | None = None,
    reversal_by: Mapping[str, Mapping[str, Any]] | None = None,
    micro_by: Mapping[str, Mapping[str, Any]] | None = None,
    liquidity_by: Mapping[str, Mapping[str, Any]] | None = None,
    sector_turn_by: Mapping[str, Mapping[str, Any]] | None = None,
    micro_asof: Any = None,
    board_asof: Any = None,
) -> list[dict]:
    """Copy, enrich, and score every candidate row.

    The maps are optional to keep the function useful with already-enriched rows.
    If a map explicitly contains a ticker, that value is authoritative (even when it
    is ``None``); otherwise the corresponding value already attached to the row is used.
    The returned order is score-descending with ticker as the deterministic tiebreak.
    """
    enriched: list[dict] = []
    board_date = _as_date(board_asof)
    micro_date = _as_date(micro_asof)

    for source in rows:
        row = deepcopy(dict(source))
        # The library also analyzes sector ETFs and indices as market context.
        # Prophet is an A-share stock-selection surface, so those instruments
        # have no candidate or shadow-ledger authority.
        if str(row.get("sector") or "") in NON_STOCK_SECTORS:
            continue
        ticker = str(row.get("ticker") or "")

        verdict = _mapped(verdict_by, ticker, row.get("signal")) or {}
        profile = _mapped(profile_by, ticker, row.get("conviction")) or {}
        entry = _mapped(entry_by, ticker, row.get("entry_signal")) or {}
        risk = _mapped(risk_by, ticker, row.get("risk_sizing")) or {}
        micro = _mapped(micro_by, ticker, row.get("microstructure"))
        liquidity = _mapped(liquidity_by, ticker, row.get("liquidity"))
        sector_turn = _mapped(sector_turn_by, ticker, row.get("sector_turn"))
        rev_z = _mapped(rev_z_by, ticker, row.get("rev_z"))

        # The slim verdict prevents the raw analyzer payload from bloating the board
        # JSON. A bounded private receipt preserves research fields for the PIT
        # shadow ledger and is stripped by partition_board_rows.
        row["_signal_research"] = {
            key: deepcopy(verdict.get(key))
            for key in (
                "eligible", "tier_cascade", "tier_sub", "sub", "reason",
                "state", "ticks", "bars_to_cross", "weight", "provisional",
                # ``asof`` is the 3-business-day indicator bucket label. It is
                # not proof that the underlying daily input reached the board
                # session, so admission uses the separate input receipt.
                "asof", "input_asof",
            )
            if key in verdict
        }
        row["signal"] = signal_gate.buy_signal(dict(verdict))
        row["conviction"] = deepcopy(dict(profile))
        row["entry_signal"] = deepcopy(dict(entry))
        if risk:
            row["risk_sizing"] = deepcopy(dict(risk))
        if micro is not None:
            row["microstructure"] = deepcopy(dict(micro))
        if liquidity is not None:
            row["liquidity"] = deepcopy(dict(liquidity))
            adv_yi = _finite_float(liquidity.get("adv_yi"))
            if adv_yi is not None:
                row["adv_yi"] = adv_yi
        if sector_turn is not None:
            row["sector_turn"] = deepcopy(dict(sector_turn))
        row["rev_z"] = _finite_float(rev_z)
        row["_micro_asof"] = micro_date
        row["_board_asof"] = board_date
        enriched.append(row)

    reversal = _reversal_context(enriched, reversal_by)
    for index, row in enumerate(enriched):
        row.update(reversal[index])
        signal_value = _signal_value(row.get("signal"))
        entry_value = _entry_value(row.get("entry_signal"))
        runway_value = _runway_value(row.get("conviction"), row.get("extension"))
        bottom_value = _bottom_quality_value(row)
        reversal_value = 1.0 if row.get("reversal_member") else 0.0

        values = {
            "signal": signal_value,
            "entry": entry_value,
            "runway": runway_value,
            "bottom_quality": bottom_value,
            "reversal_member": reversal_value,
        }
        points = {
            name: round(SCORE_WEIGHTS[name] * value, 4)
            for name, value in values.items()
        }
        score = max(0.0, min(100.0, sum(points.values())))
        row["prophet_score"] = round(score, 2)
        row["prophet_rank"] = {
            "definition": BOARD_DEFINITION,
            "score": row["prophet_score"],
            "components": {
                name: {"value": round(value, 6), "points": points[name]}
                for name, value in values.items()
            },
            "zero_score_authority": list(_ZERO_SCORE_AUTHORITY),
        }
        # Compact display/ledger contract.  ``prophet_rank`` keeps the fully
        # self-describing research record; ``prophet`` avoids forcing every
        # consumer to unpack nested ``value``/``points`` objects.
        row["prophet"] = {
            "version": BOARD_DEFINITION,
            "score": row["prophet_score"],
            "components": {
                name: round(value, 6) for name, value in values.items()
            },
            "points": points,
            "zero_score_authority": list(_ZERO_SCORE_AUTHORITY),
        }
        row["board_definition"] = BOARD_DEFINITION

    enriched.sort(key=lambda row: (-float(row["prophet_score"]), str(row.get("ticker") or "")))
    for rank, row in enumerate(enriched, start=1):
        row["score_rank"] = rank
    return enriched


def _chase_flag(micro: Mapping[str, Any] | None) -> bool | None:
    if not micro:
        return None
    chase = micro.get("chase_veto")
    if isinstance(chase, Mapping):
        flag = chase.get("flag")
    else:
        flag = chase
    return flag if isinstance(flag, bool) else None


def _adv_yi(row: Mapping[str, Any]) -> float | None:
    liquidity = row.get("liquidity") or {}
    value = liquidity.get("adv_yi")
    if value is None:
        value = row.get("adv_yi")
    return _finite_float(value)


def _micro_is_fresh(row: Mapping[str, Any]) -> bool:
    micro = row.get("microstructure")
    if not isinstance(micro, Mapping):
        return False
    if not row.get("_board_asof"):
        return False
    packet_date = _as_date(micro.get("as_of"))
    # Missing packet dates fail closed.  The nightly artifact can be stale while
    # carrying apparently valid fillability flags from yesterday.
    return packet_date == row.get("_board_asof")


def _signal_is_fresh(row: Mapping[str, Any]) -> bool:
    """Require the confluence verdict to come from the board's stock session."""
    research = row.get("_signal_research")
    if not isinstance(research, Mapping):
        return False
    return (
        bool(row.get("_board_asof"))
        and _as_date(research.get("input_asof")) == row.get("_board_asof")
    )


def execution_coverage(scored_rows: Iterable[Mapping[str, Any]]) -> dict[str, int | float]:
    """Summarise current execution-data coverage for actionable T1-T3 rows.

    All rates use the actionable T1-T3 count as their denominator.  Fillability
    and clear-to-feature counts accept only packets that pass the same strict
    same-day check as admission.  Call this before removing the private
    ``_board_asof`` metadata from enriched rows.
    """
    rows = list(scored_rows)
    raw_eligible = sum(
        1 for row in rows if (row.get("signal") or {}).get("eligible") is True
    )
    actionable_rows = [
        row for row in rows if signal_gate.is_buyable(row.get("signal") or {})
    ]
    actionable = len(actionable_rows)

    fresh = 0
    known_fillability = 0
    clear = 0
    unknown_micro = 0
    stale_micro = 0
    fresh_but_incomplete = 0
    fresh_signal = 0
    unknown_signal = 0
    stale_signal = 0

    for row in actionable_rows:
        research = row.get("_signal_research")
        signal_date = (
            _as_date(research.get("input_asof"))
            if isinstance(research, Mapping)
            else None
        )
        if _signal_is_fresh(row):
            fresh_signal += 1
        elif signal_date is None:
            unknown_signal += 1
        else:
            stale_signal += 1

        micro = row.get("microstructure")
        if not isinstance(micro, Mapping):
            unknown_micro += 1
            continue
        if not _micro_is_fresh(row):
            stale_micro += 1
            continue

        fresh += 1
        fillable = micro.get("fillable")
        chase = _chase_flag(micro)
        if isinstance(fillable, bool):
            known_fillability += 1
        if fillable is True and chase is False:
            clear += 1
        if not isinstance(fillable, bool) or chase is None:
            fresh_but_incomplete += 1

    def rate(count: int) -> float:
        return round(100.0 * count / actionable, 1) if actionable else 0.0

    return {
        "raw_eligible": int(raw_eligible),
        "actionable_t1_t3": int(actionable),
        "fresh_same_day_signal_count": int(fresh_signal),
        "fresh_same_day_signal_rate_pct": rate(fresh_signal),
        "unknown_signal_date_count": int(unknown_signal),
        "stale_signal_count": int(stale_signal),
        "fresh_same_day_micro_count": int(fresh),
        "fresh_same_day_micro_rate_pct": rate(fresh),
        "known_fillability_count": int(known_fillability),
        "known_fillability_rate_pct": rate(known_fillability),
        "clear_count": int(clear),
        "clear_rate_pct": rate(clear),
        "unknown_micro_count": int(unknown_micro),
        "stale_micro_count": int(stale_micro),
        "fresh_but_incomplete_count": int(fresh_but_incomplete),
        "unknown_fillability_count": int(actionable - known_fillability),
    }


def reversal_coverage(
    scored_rows: Iterable[Mapping[str, Any]],
    reversal_by: Mapping[str, Mapping[str, Any]] | None,
    *,
    source_asof: Any,
    board_asof: Any,
    minimum_healthy_rate_pct: float = 80.0,
) -> dict[str, Any]:
    """Report whether the 10-point reversal input is truly available point-in-time."""
    rows = list(scored_rows)
    mapping = reversal_by or {}
    source_date = _as_date(source_asof)
    board_date = _as_date(board_asof)
    exact_date = bool(source_date and board_date and source_date == board_date)
    scored_tickers = {
        str(row.get("ticker") or "") for row in rows if row.get("ticker")
    }
    actionable_tickers = {
        str(row.get("ticker") or "")
        for row in rows
        if row.get("ticker")
        and signal_gate.is_buyable(row.get("signal") or {})
    }
    covered_tickers = set(mapping).intersection(scored_tickers) if exact_date else set()
    actionable_covered = covered_tickers.intersection(actionable_tickers)

    def rate(count: int, total: int) -> float:
        return round(100.0 * count / total, 1) if total else 0.0

    scored_rate = rate(len(covered_tickers), len(scored_tickers))
    actionable_rate = rate(len(actionable_covered), len(actionable_tickers))
    available = bool(exact_date and mapping)
    degraded = bool(
        len(actionable_tickers) >= 5
        and (
            not available
            or actionable_rate < float(minimum_healthy_rate_pct)
        )
    )
    return {
        "source_asof": source_date,
        "board_asof": board_date,
        "exact_date": exact_date,
        "available": available,
        "scored_count": len(scored_tickers),
        "scored_covered_count": len(covered_tickers),
        "scored_coverage_rate_pct": scored_rate,
        "actionable_count": len(actionable_tickers),
        "actionable_covered_count": len(actionable_covered),
        "actionable_coverage_rate_pct": actionable_rate,
        "minimum_healthy_rate_pct": float(minimum_healthy_rate_pct),
        "degraded": degraded,
    }


def _execution_reasons(row: Mapping[str, Any]) -> list[str]:
    """Known execution blockers.  Unknown/stale context is not treated as a veto."""
    reasons: list[str] = []
    micro = row.get("microstructure") or {}
    if _micro_is_fresh(row):
        if micro.get("fillable") is False:
            reasons.append("unfillable")
        if _chase_flag(micro) is True:
            reasons.append("chase_veto")
    adv = _adv_yi(row)
    if adv is not None and adv < ADV_FLOOR_YI:
        reasons.append("liquidity_below_floor")
    return reasons


def _featured_shortfalls(row: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not _signal_is_fresh(row):
        research = row.get("_signal_research")
        signal_date = (
            _as_date(research.get("input_asof"))
            if isinstance(research, Mapping)
            else None
        )
        reasons.append("signal_stale" if signal_date else "signal_date_unknown")

    status = str((row.get("entry_signal") or {}).get("status") or "")
    if status not in _FEATURED_ENTRY_STATUSES:
        reasons.append(f"entry_status_{status or 'unknown'}")

    adv = _adv_yi(row)
    if adv is None:
        reasons.append("liquidity_unknown")
    elif adv < ADV_FLOOR_YI:
        reasons.append("liquidity_below_floor")

    extension = row.get("extension")
    if not isinstance(extension, Mapping) or extension.get("extended") is None:
        reasons.append("extension_unknown")

    micro = row.get("microstructure")
    if not isinstance(micro, Mapping):
        reasons.append("micro_missing")
    elif not _micro_is_fresh(row):
        reasons.append("micro_stale")
    else:
        if micro.get("fillable") is not True:
            reasons.append("micro_fillability_unknown")
        if _chase_flag(micro) is not False:
            reasons.append("micro_chase_status_unknown")
    return reasons


def partition_board_rows(
    scored_rows: Iterable[Mapping[str, Any]],
    *,
    featured_cap: int = FEATURED_CAP,
    sector_cap: int = SECTOR_CAP,
) -> dict[str, Any]:
    """Partition scored, stage-assigned raw gate rows into four lossless lanes.

    ``forming`` contains legacy raw-eligible signals which are not actionable T1-T3.
    A buyable name with a known execution block, an extension flag, or a non-ENTRY
    lifecycle is routed to ``late_or_unfillable``.  Remaining ENTRY rows enter
    ``more_actionable`` unless they pass every featured-now safeguard and fit both
    display caps.
    """
    rows = [deepcopy(dict(row)) for row in scored_rows]
    rows.sort(
        key=lambda row: (
            int(row.get("score_rank") or 10**9),
            -float(row.get("prophet_score") or 0.0),
            str(row.get("ticker") or ""),
        )
    )

    featured: list[dict] = []
    more: list[dict] = []
    late: list[dict] = []
    forming: list[dict] = []
    sector_counts: dict[str, int] = defaultdict(int)

    def place(row: dict, lane: str, reasons: list[str], target: list[dict]) -> None:
        row["lane"] = lane
        row["lane_reasons"] = list(reasons)
        target.append(row)

    for row in rows:
        signal = row.get("signal") or {}
        tier = signal.get("tier_cascade")
        if not signal_gate.is_buyable(signal):
            if not signal.get("eligible"):
                reasons = ["raw_gate_ineligible"]
            elif tier == "T4":
                reasons = ["tier_t4_not_actionable"]
            else:
                reasons = ["no_buyable_tier"]
            place(row, "forming", reasons, forming)
            continue

        execution = _execution_reasons(row)
        extension = row.get("extension") or {}
        if extension.get("extended"):
            execution.append("extended")
        if row.get("stage") != "ENTRY":
            execution.append("non_entry_stage")
        if execution:
            place(row, "late_or_unfillable", execution, late)
            continue

        shortfalls = _featured_shortfalls(row)
        if shortfalls:
            place(row, "more_actionable", shortfalls, more)
            continue

        sector = str(row.get("sector") or "—")
        if len(featured) >= max(0, int(featured_cap)):
            place(row, "more_actionable", ["featured_cap"], more)
        elif sector_counts[sector] >= max(0, int(sector_cap)):
            place(row, "more_actionable", ["sector_cap"], more)
        else:
            sector_counts[sector] += 1
            place(
                row,
                "featured",
                [
                    "buyable_signal",
                    "entry_stage",
                    "entry_window_open",
                    "liquid",
                    "microstructure_clear",
                    "not_extended",
                ],
                featured,
            )

    lanes = {
        "featured": featured,
        "more_actionable": more,
        "late_or_unfillable": late,
        "forming": forming,
    }
    for lane_rows in lanes.values():
        lane_rows.sort(
            key=lambda row: (
                int(row.get("score_rank") or 10**9),
                str(row.get("ticker") or ""),
            )
        )
        for display_rank, row in enumerate(lane_rows, start=1):
            row["display_rank"] = display_rank
            # Builder-only join metadata and the verbose duplicate research
            # record never cross the public artifact boundary.
            row.pop("_micro_asof", None)
            row.pop("_board_asof", None)
            row.pop("_signal_research", None)
            row.pop("prophet_rank", None)
            row.pop("prophet_score", None)
            row.pop("liquidity", None)

    return {
        "board_definition": BOARD_DEFINITION,
        "featured_cap": max(0, int(featured_cap)),
        "sector_cap": max(0, int(sector_cap)),
        **lanes,
        "counts": {name: len(lane_rows) for name, lane_rows in lanes.items()},
        "eligible": len(rows),
    }


def build_board_lanes(
    rows: Iterable[Mapping[str, Any]],
    *,
    verdict_by: Mapping[str, Mapping[str, Any]] | None = None,
    profile_by: Mapping[str, Mapping[str, Any]] | None = None,
    entry_by: Mapping[str, Mapping[str, Any]] | None = None,
    risk_by: Mapping[str, Mapping[str, Any]] | None = None,
    rev_z_by: Mapping[str, float] | None = None,
    reversal_by: Mapping[str, Mapping[str, Any]] | None = None,
    micro_by: Mapping[str, Mapping[str, Any]] | None = None,
    liquidity_by: Mapping[str, Mapping[str, Any]] | None = None,
    sector_turn_by: Mapping[str, Mapping[str, Any]] | None = None,
    micro_asof: Any = None,
    board_asof: Any = None,
    featured_cap: int = FEATURED_CAP,
    sector_cap: int = SECTOR_CAP,
) -> dict[str, Any]:
    """Convenience wrapper: :func:`enrich_and_score_rows` then partition lanes."""
    scored = enrich_and_score_rows(
        rows,
        verdict_by=verdict_by,
        profile_by=profile_by,
        entry_by=entry_by,
        risk_by=risk_by,
        rev_z_by=rev_z_by,
        reversal_by=reversal_by,
        micro_by=micro_by,
        liquidity_by=liquidity_by,
        sector_turn_by=sector_turn_by,
        micro_asof=micro_asof,
        board_asof=board_asof,
    )
    return partition_board_rows(scored, featured_cap=featured_cap, sector_cap=sector_cap)
