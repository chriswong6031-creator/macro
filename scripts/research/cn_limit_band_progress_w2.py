"""Wave-2 A-share band-progress construction and substrate gate.

This module intentionally does *not* backtest against ``data/china_stocks_raw``.
That Yahoo plane is split-adjusted even when downloaded with ``auto_adjust=False``;
its historical prices therefore cannot reconstruct exact legal CNY 0.01 limits.

The executable has two jobs until the canonical TuShare full-A spine lands:

1. freeze/test the non-combinatorial signal taxonomy and exchange half-up tick
   arithmetic; and
2. emit a deterministic ``BLOCKED_SUBSTRATE`` receipt.  An explicit legacy audit
   may count off-tick rows and rounding-driven event-key deltas, but it never emits
   transition, return, fill, or strategy metrics.

The later measurement path consumes the canonical v1 relative layout beneath an
operator-supplied private ``--spine-root``. Its ``event_daily/year=YYYY/month=MM``
plane joins TuShare unadjusted ``daily`` rows to vendor ``stk_limit`` upper/lower
prices, backed by a schema-valid completeness manifest and references. Vendor
integer-cent limit prices are authoritative; locally reconstructed prices are
audits. The v1 spine does not materialize every rule/lifecycle eligibility field
required by the frozen protocol, so those remain explicit blockers rather than
inferred values.

Run from repository root::

    TZ=UTC python3 scripts/research/cn_limit_band_progress_w2.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "cn_limit_band_progress_w2_substrate/v2"
RECEIPT_DATE = "2026-08-08"
AUTHORITY = "none_research_display_context_only"
TOLERANT_CUSHION = 0.002
# Float32-backed Parquet values such as 8.5299997 represent a legal 8.53 tick.
# Treat only a distance greater than CNY 0.00001 from the nearest cent as off tick.
TICK_ALIGNMENT_EPSILON_CNY = 1e-5

PROTOCOL_PATH = (
    ROOT
    / "research"
    / "cn_limit_alpha_sol"
    / "W2_BAND_PROGRESS_CONSTRUCTION_PROTOCOL_2026-08-08.md"
)
DEFAULT_JSON = (
    ROOT
    / "research"
    / "cn_limit_alpha_sol"
    / "W2_BAND_PROGRESS_SUBSTRATE_RECEIPT_2026-08-08.json"
)
DEFAULT_MARKDOWN = (
    ROOT
    / "research"
    / "cn_limit_alpha_sol"
    / "W2_BAND_PROGRESS_SUBSTRATE_RECEIPT_2026-08-08.md"
)

# Frozen full-A integration contract from ``claude/cn-limit-sol-w2-full-a-spine``
# commit b2548fdc095. This repo-local root is only a backward-compatible default;
# ``--spine-root`` can point at a licensed/private store outside the repository.
# Monthly planes retain the same ``year=YYYY/month=MM/part.parquet`` layout.
DEFAULT_SPINE_ROOT = ROOT / "data" / "china_tushare_spine"
DEFAULT_DAILY = DEFAULT_SPINE_ROOT / "daily"
DEFAULT_LIMITS = DEFAULT_SPINE_ROOT / "stk_limit"
DEFAULT_EVENT_DAILY = DEFAULT_SPINE_ROOT / "event_daily"
DEFAULT_CALENDAR = DEFAULT_SPINE_ROOT / "reference" / "market_sessions.parquet"
DEFAULT_SECURITY_MASTER = DEFAULT_SPINE_ROOT / "reference" / "security_master.parquet"
DEFAULT_STOCK_ST = DEFAULT_SPINE_ROOT / "stock_st"
DEFAULT_COVERAGE = DEFAULT_SPINE_ROOT / "coverage" / "daily_security_coverage.parquet"
DEFAULT_MANIFEST = DEFAULT_SPINE_ROOT / "completeness_manifest.json"
DEFAULT_MANIFEST_SCHEMA = (
    ROOT / "contracts" / "cn_tushare_a_share_spine_manifest.v1.schema.json"
)
DEFAULT_LEGACY_RAW = ROOT / "data" / "china_stocks_raw"
DEFAULT_ST_SNAPSHOT = ROOT / "data" / "china_st" / "st_snapshot.parquet"

DAILY_REQUIRED = frozenset(
    {
        "security_id",
        "ticker",
        "source_ts_code",
        "exchange",
        "board",
        "trade_date",
        "market_session_position",
        "open_cents",
        "high_cents",
        "low_cents",
        "close_cents",
        "pre_close_cents",
        "volume_lots",
        "positive_volume",
        "price_source_basis",
    }
)
LIMIT_REQUIRED = frozenset(
    {
        "security_id",
        "ticker",
        "source_ts_code",
        "exchange",
        "board",
        "trade_date",
        "market_session_position",
        "pre_close_cents",
        "up_limit_cents",
        "down_limit_cents",
        "source_limits_present",
        "limit_price_source",
    }
)
EVENT_DAILY_REQUIRED = frozenset(
    {
        "security_id",
        "ticker",
        "source_ts_code",
        "exchange",
        "board",
        "trade_date",
        "market_session_position",
        "open_cents",
        "high_cents",
        "low_cents",
        "close_cents",
        "pre_close_cents",
        "limit_pre_close_cents",
        "volume_lots",
        "positive_volume",
        "up_limit_cents",
        "down_limit_cents",
        "source_limits_present",
        "event_eligible",
        "touched_up",
        "sealed_up",
        "touched_down",
        "sealed_down",
        "event_price_authority",
        "calculated_limit_role",
    }
)
CALENDAR_REQUIRED = frozenset(
    {
        "trade_date",
        "market_session_position",
        "calendar_provenance",
        "bse_calendar_provenance",
    }
)
SECURITY_MASTER_REQUIRED = frozenset(
    {
        "security_id",
        "ticker",
        "source_ts_code",
        "exchange",
        "board",
        "list_status",
        "list_date",
        "delist_date",
        "effective_from",
        "effective_to",
    }
)
STOCK_ST_REQUIRED = frozenset(
    {"security_id", "ticker", "trade_date", "is_st", "st_provenance"}
)
COVERAGE_REQUIRED = frozenset(
    {
        "trade_date",
        "eligible_n",
        "daily_n",
        "positive_volume_n",
        "suspended_n",
        "unexplained_missing_n",
        "unexpected_daily_n",
    }
)

# V1 deliberately does not materialize these onto ``event_daily``. They are
# measurement prerequisites, not values this adapter may infer silently.
MEASUREMENT_OVERLAY_REQUIRED = frozenset(
    {
        "rule_cohort",
        "session_eligible",
        "corporate_action_reference_known",
        "no_limit",
        "ipo_no_limit_state_known",
        "st_membership_state",
        "st_provenance",
    }
)
MANIFEST_SCHEMA_VERSION = "cn_tushare_a_share_spine_manifest.v1"
CONTRACT_SNAPSHOT_COMMIT = "b2548fdc095"
CONTRACT_SNAPSHOT_STATUS = "SHAPE_ONLY_NO_READINESS_AUTHORITY_PENDING_REMEDIATION"
MANIFEST_SCHEMA_SHA256 = (
    "a43c4a133aee3aed571c9fb630c5154a826d24872f6ce107b1016cf6fc36ce02"
)
MEASUREMENT_START = "2011-01-01"
MEASUREMENT_END = "2026-08-07"
PREMEASUREMENT_CONTRACT_CORRECTIONS = (
    {
        "date": "2026-08-09",
        "id": "canonical_full_a_v1_binding",
        "change": (
            "replace placeholder input seams with the frozen china_tushare_spine v1 "
            "event_daily, reference, coverage, and manifest contract"
        ),
        "outcome_measurement_observed_before_change": False,
    },
    {
        "date": "2026-08-09",
        "id": "bounded_integer_cent_event_equality",
        "change": (
            "classify exact seals/touches only by close_cents/high_cents equality to the "
            "vendor up_limit_cents after quarantining OHLC outside vendor bounds"
        ),
        "outcome_measurement_observed_before_change": False,
    },
)

TOUCH_RETREAT_IDS = (
    "TF_TOL_ONLY",
    "TF_CP_095_100",
    "TF_CP_080_095",
    "TF_CP_060_080",
    "TF_CP_LT060",
)
NO_TOUCH_HIGH_IDS = (
    "NT_H_095_100",
    "NT_H_080_095",
    "NT_H_060_080",
    "NT_H_040_060",
)
NO_TOUCH_CLOSE_IDS = (
    "NT_C_095_100",
    "NT_C_080_095",
    "NT_C_060_080",
    "NT_C_040_060",
)
ALL_CONSTRUCTION_IDS = (
    "S_STRICT",
    "S_TOL_ONLY",
    *TOUCH_RETREAT_IDS,
    *NO_TOUCH_HIGH_IDS,
    *NO_TOUCH_CLOSE_IDS,
)

UNTESTED_VARIANTS = (
    "first-touch, first-seal, last-seal, break/reseal, sealed duration, and path order",
    "wall growth, depletion, replenishment, cancellation, queue rank, partial fills, and signed flow",
    "opening-auction imbalance and post-09:25 decisions with true 09:30 execution",
    "early failed-seal absorption versus late demand exhaustion",
    "closing-auction-only seals and post-close fixed-price execution",
    "upper-then-lower versus lower-then-upper intraday traversal",
    "multi-step cadence words and flexible 3/5/10-session first-passage paths",
    "T+1 inventory vintages, volume-at-price, free float, unlocks, and queue elasticity",
    "PIT theme topology, spectator substitution, and failed-leader redistribution",
    "ladder topology, hysteresis, and regime interactions",
    "availability-safe LHB, block sponsorship, and catalyst classes",
    "full-universe delisted-name, historical ST, IPO, suspension, and corporate-action truth",
    "board-local nonlinear models, threshold/cash portfolios, and nested confirmation",
    "live fees, slippage, rejection, capacity, sector caps, and mark-to-market drawdown",
    "at least ten prospective graded sessions and every authority-promotion gauntlet",
)


@dataclass(frozen=True)
class SignalState:
    """Daily close/high state under one exact vendor upper limit."""

    strict_seal: bool
    tolerant_close: bool
    tolerant_only: bool
    exact_touch: bool
    exact_touch_failed: bool
    partial_no_touch: bool
    high_progress: float
    close_progress: float


@dataclass(frozen=True)
class VendorBoundedBar:
    """One event-eligible bar expressed entirely in integer CNY cents."""

    pre_close_cents: int
    open_cents: int
    high_cents: int
    low_cents: int
    close_cents: int
    up_limit_cents: int
    down_limit_cents: int


def _finite_positive(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return bool(math.isfinite(number) and number > 0)


def _integer_cents(name: str, value: Any) -> int:
    """Return a positive integer-cent value or fail closed.

    Parquet readers can surface nullable integer-valued columns as ``float``.
    Accepting ``1100.0`` is therefore intentional; accepting ``1100.5`` is not.
    """

    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be positive integer CNY cents")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be positive integer CNY cents") from exc
    if (
        not decimal_value.is_finite()
        or decimal_value <= 0
        or decimal_value != decimal_value.to_integral_value()
    ):
        raise ValueError(f"{name} must be positive integer CNY cents")
    return int(decimal_value)


def validate_vendor_bounded_bar(
    *,
    pre_close_cents: Any,
    open_cents: Any,
    high_cents: Any,
    low_cents: Any,
    close_cents: Any,
    up_limit_cents: Any,
    down_limit_cents: Any,
) -> VendorBoundedBar:
    """Validate the exact vendor-limit event contract before classification.

    Event-eligible OHLC outside either vendor bound is quarantined.  This keeps
    defensive ``>=`` comparisons from turning an impossible overshoot into a
    legal seal/touch and likewise prevents below-floor prints from entering the
    ordinary-band taxonomy.
    """

    values = {
        name: _integer_cents(name, value)
        for name, value in {
            "pre_close_cents": pre_close_cents,
            "open_cents": open_cents,
            "high_cents": high_cents,
            "low_cents": low_cents,
            "close_cents": close_cents,
            "up_limit_cents": up_limit_cents,
            "down_limit_cents": down_limit_cents,
        }.items()
    }
    prior = values["pre_close_cents"]
    upper = values["up_limit_cents"]
    lower = values["down_limit_cents"]
    if not upper > prior >= lower:
        raise ValueError("vendor limits must satisfy up > pre_close >= down > 0")

    opening = values["open_cents"]
    high = values["high_cents"]
    low = values["low_cents"]
    close = values["close_cents"]
    if high < max(opening, close) or low > min(opening, close) or low > high:
        raise ValueError("OHLC ordering is internally inconsistent")
    outside = {
        name: value
        for name, value in {
            "open_cents": opening,
            "high_cents": high,
            "low_cents": low,
            "close_cents": close,
        }.items()
        if value < lower or value > upper
    }
    if outside:
        names = ", ".join(sorted(outside))
        raise ValueError(f"OHLC outside exact vendor bounds: {names}")
    return VendorBoundedBar(**values)


def half_up_yuan_tick(value: Any) -> float:
    """Round a positive price to CNY 0.01 with decimal ROUND_HALF_UP.

    The string conversion avoids importing the binary float's hidden tail into
    the decimal contract.  Vendor ``stk_limit`` remains authoritative; this is
    only an exchange-rule reconciliation helper.
    """

    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid tick value: {value!r}") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"tick value must be finite and positive: {value!r}")
    return float(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def half_up_limit_from_tick(pre_close: Any, width: Any, *, side: str = "up") -> float:
    """Reconstruct one legal bound from a tick-aligned close for audit only.

    Besides half-up rounding, this mirrors the frozen full-A spine's SZSE 2026
    one-tick separation and one-tick absolute floor. Vendor ``stk_limit`` still
    remains event authority.
    """

    try:
        prior = Decimal(str(pre_close))
        band = Decimal(str(width))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("pre_close and width must be decimal-compatible") from exc
    if not prior.is_finite() or prior <= 0:
        raise ValueError("pre_close must be finite and positive")
    if not band.is_finite() or band <= 0 or band >= 1:
        raise ValueError("width must be between zero and one")
    if prior.quantize(Decimal("0.01")) != prior:
        raise ValueError("pre_close is not aligned to the CNY 0.01 tick")
    if side not in {"up", "down"}:
        raise ValueError("side must be 'up' or 'down'")
    tick = Decimal("0.01")
    multiplier = Decimal(1) + band if side == "up" else Decimal(1) - band
    bound = (prior * multiplier).quantize(tick, rounding=ROUND_HALF_UP)
    if abs(bound - prior) < tick:
        bound = prior + tick if side == "up" else prior - tick
    return float(max(bound, tick))


def classify_band_state(
    *,
    pre_close_cents: Any,
    open_cents: Any,
    high_cents: Any,
    low_cents: Any,
    close_cents: Any,
    up_limit_cents: Any,
    down_limit_cents: Any,
) -> SignalState:
    """Classify one bounded daily bar without inventing intraday path order.

    Exact vendor-limit events use integer-cent equality, never ``>=``.  Values
    outside the vendor bounds fail validation instead of being relabelled as a
    seal or touch.
    """

    bar = validate_vendor_bounded_bar(
        pre_close_cents=pre_close_cents,
        open_cents=open_cents,
        high_cents=high_cents,
        low_cents=low_cents,
        close_cents=close_cents,
        up_limit_cents=up_limit_cents,
        down_limit_cents=down_limit_cents,
    )
    prior = bar.pre_close_cents
    hi = bar.high_cents
    finish = bar.close_cents
    upper = bar.up_limit_cents
    span = upper - prior
    high_progress = (hi - prior) / span
    close_progress = (finish - prior) / span
    strict = finish == upper
    # 0.2% tolerant sensitivity, written as exact integer arithmetic.
    tolerant = finish * 1000 >= upper * 998
    touch = hi == upper
    return SignalState(
        strict_seal=bool(strict),
        tolerant_close=bool(tolerant),
        tolerant_only=bool(tolerant and not strict),
        exact_touch=bool(touch),
        exact_touch_failed=bool(touch and not strict),
        partial_no_touch=bool(not touch),
        high_progress=float(high_progress),
        close_progress=float(close_progress),
    )


def _required_boolean(name: str, value: Any) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be an explicit boolean")
    return bool(value)


def classify_authoritative_event_row(row: Mapping[str, Any]) -> SignalState:
    """Re-attest one canonical ``event_daily`` row before classification.

    Stored event flags are useful transport fields, not independent authority.
    The consumer recomputes them from bounded integer cents and rejects any
    disagreement. Only exact-source, positive-volume, source-limit-present rows
    marked event eligible can reach the signal taxonomy.
    """

    required = EVENT_DAILY_REQUIRED - set(row)
    if required:
        raise ValueError(f"event_daily row missing columns: {sorted(required)}")
    if row["event_price_authority"] != (
        "tushare.daily_unadjusted_plus_stk_limit_exact_daily"
    ):
        raise ValueError("event_daily row lacks exact vendor-limit price authority")
    if row["calculated_limit_role"] != "validator_only_never_event_authority":
        raise ValueError("calculated limits cannot become event authority")
    if not _required_boolean("positive_volume", row["positive_volume"]):
        raise ValueError("event classification requires positive_volume")
    if not _required_boolean("source_limits_present", row["source_limits_present"]):
        raise ValueError("event classification requires source_limits_present")
    if not _required_boolean("event_eligible", row["event_eligible"]):
        raise ValueError("event classification requires event_eligible")

    pre_close = _integer_cents("pre_close_cents", row["pre_close_cents"])
    limit_pre_close = _integer_cents(
        "limit_pre_close_cents", row["limit_pre_close_cents"]
    )
    if pre_close != limit_pre_close:
        raise ValueError("daily and stk_limit previous-close cents disagree")
    state = classify_band_state(
        pre_close_cents=pre_close,
        open_cents=row["open_cents"],
        high_cents=row["high_cents"],
        low_cents=row["low_cents"],
        close_cents=row["close_cents"],
        up_limit_cents=row["up_limit_cents"],
        down_limit_cents=row["down_limit_cents"],
    )
    lower = _integer_cents("down_limit_cents", row["down_limit_cents"])
    low = _integer_cents("low_cents", row["low_cents"])
    close = _integer_cents("close_cents", row["close_cents"])
    expected_flags = {
        "touched_up": state.exact_touch,
        "sealed_up": state.strict_seal,
        "touched_down": low == lower,
        "sealed_down": close == lower,
    }
    mismatches = [
        name
        for name, expected in expected_flags.items()
        if _required_boolean(name, row[name]) != expected
    ]
    if mismatches:
        raise ValueError(
            "event_daily flags disagree with bounded integer-cent equality: "
            + ", ".join(mismatches)
        )
    return state


def _progress_bucket(value: float, prefix: str) -> str | None:
    """Return one frozen [0.4, 1.0) progress bucket."""

    if not math.isfinite(value) or value < 0.40 or value >= 1.00:
        return None
    if value >= 0.95:
        suffix = "095_100"
    elif value >= 0.80:
        suffix = "080_095"
    elif value >= 0.60:
        suffix = "060_080"
    else:
        suffix = "040_060"
    return f"{prefix}_{suffix}"


def signal_memberships(state: SignalState) -> tuple[str, ...]:
    """Return frozen construction memberships for one valid state.

    Seal/touch morphology and the two no-touch marginals are deliberately
    separate panels.  A no-touch row can appear once in each marginal; callers
    must never sum the panels as one portfolio.
    """

    memberships: list[str] = []
    if state.strict_seal:
        memberships.append("S_STRICT")
    elif state.tolerant_only:
        memberships.append("S_TOL_ONLY")

    if state.exact_touch_failed:
        if state.tolerant_only:
            memberships.append("TF_TOL_ONLY")
        elif state.close_progress >= 0.95:
            memberships.append("TF_CP_095_100")
        elif state.close_progress >= 0.80:
            memberships.append("TF_CP_080_095")
        elif state.close_progress >= 0.60:
            memberships.append("TF_CP_060_080")
        else:
            memberships.append("TF_CP_LT060")
    elif state.partial_no_touch:
        high_id = _progress_bucket(state.high_progress, "NT_H")
        close_id = _progress_bucket(state.close_progress, "NT_C")
        if high_id:
            memberships.append(high_id)
        if close_id:
            memberships.append(close_id)
    return tuple(memberships)


def entry_proxy_state(
    *, open_price: Any, up_limit: Any, volume: Any, row_present: bool = True
) -> str:
    """Classify the D+1 reported-open daily tradability proxy."""

    if not row_present:
        return "missing_bar_halt_or_data_missing_no_fill"
    if not _finite_positive(volume):
        return "zero_volume_halt_or_no_trade_no_fill"
    if not _finite_positive(open_price) or not _finite_positive(up_limit):
        return "price_or_limit_missing_no_fill"
    if float(open_price) >= float(up_limit) * (1.0 - TOLERANT_CUSHION):
        return "upper_queue_no_fill"
    return "daily_tradability_proxy"


def exact_exit_session(
    calendar: Sequence[Any], *, signal_date: Any, exit_id: str
) -> pd.Timestamp | None:
    """Return the frozen T+1-legal scheduled exit date.

    Signal information ends at D close, the candidate entry is D+1 open, and
    the earliest exit is therefore D+2.
    """

    sessions = pd.DatetimeIndex(
        pd.to_datetime(list(calendar), errors="coerce")
    ).normalize()
    sessions = sessions[~sessions.isna()].drop_duplicates().sort_values()
    positions = {date: i for i, date in enumerate(sessions)}
    date = pd.Timestamp(signal_date).normalize()
    start = positions.get(date)
    if start is None:
        return None
    offsets = {"E1_OPEN": 2, "E1_CLOSE": 2, "E3_CLOSE": 4}
    if exit_id not in offsets:
        raise ValueError(f"unknown exit_id: {exit_id}")
    target = start + offsets[exit_id]
    return sessions[target] if target < len(sessions) else None


def run_cluster_ids(
    frame: pd.DataFrame,
    *,
    calendar: Sequence[Any],
    ticker_col: str = "ticker",
    date_col: str = "signal_date",
    construction_col: str = "construction_id",
) -> pd.Series:
    """Assign immutable adjacent-session run IDs without hopping missing dates."""

    sessions = pd.DatetimeIndex(
        pd.to_datetime(list(calendar), errors="coerce")
    ).normalize()
    sessions = sessions[~sessions.isna()].drop_duplicates().sort_values()
    positions = {date: i for i, date in enumerate(sessions)}
    ordered = frame[[ticker_col, date_col, construction_col]].copy()
    ordered[date_col] = pd.to_datetime(
        ordered[date_col], errors="coerce"
    ).dt.normalize()
    ordered["_original"] = np.arange(len(ordered), dtype=np.int64)
    ordered["_position"] = ordered[date_col].map(positions)
    if ordered["_position"].isna().any():
        raise ValueError(
            "signal date is absent from the attested market-session calendar"
        )
    ordered = ordered.sort_values(
        [construction_col, ticker_col, date_col, "_original"], kind="mergesort"
    )
    group_cols = [construction_col, ticker_col]
    previous = ordered.groupby(group_cols, sort=False)["_position"].shift(1)
    new_run = previous.isna() | ordered["_position"].ne(previous + 1)
    ordered["_run_number"] = new_run.groupby(
        [ordered[construction_col], ordered[ticker_col]], sort=False
    ).cumsum()
    ordered["_run_id"] = (
        ordered[construction_col].astype(str)
        + ":"
        + ordered[ticker_col].astype(str)
        + ":"
        + ordered["_run_number"].astype(int).astype(str)
    )
    return ordered.set_index("_original")["_run_id"].reindex(range(len(frame)))


def apply_no_duplicate_state_machine(
    frame: pd.DataFrame,
    *,
    ticker_col: str = "ticker",
    signal_date_col: str = "signal_date",
    entry_date_col: str = "entry_date",
    exit_date_col: str = "exit_date",
    fill_state_col: str = "entry_state",
) -> pd.Series:
    """Accept first daily-proxy fill and reject overlap until its exit date.

    Nonfills never reserve capital.  Same-day exit proceeds cannot fund a same-day
    opening entry, so an entry date equal to the prior exit date remains rejected.
    """

    ordered = frame.copy()
    ordered["_original"] = np.arange(len(ordered), dtype=np.int64)
    for column in (signal_date_col, entry_date_col, exit_date_col):
        ordered[column] = pd.to_datetime(
            ordered[column], errors="coerce"
        ).dt.normalize()
    ordered = ordered.sort_values(
        [entry_date_col, signal_date_col, ticker_col, "_original"], kind="mergesort"
    )
    active_until: dict[str, pd.Timestamp] = {}
    states: dict[int, str] = {}
    for _, row in ordered.iterrows():
        original = int(row["_original"])
        if row[fill_state_col] != "daily_tradability_proxy":
            states[original] = "candidate_nonfill_cash"
            continue
        ticker = str(row[ticker_col])
        entry_date = row[entry_date_col]
        exit_date = row[exit_date_col]
        if pd.isna(entry_date):
            states[original] = "candidate_entry_date_missing_cash"
            continue
        prior_exit = active_until.get(ticker)
        if prior_exit is not None and pd.Timestamp(entry_date) <= prior_exit:
            states[original] = "overlap_rejected_cash"
            continue
        if pd.isna(exit_date):
            states[original] = "accepted_fill_exit_unresolved"
            active_until[ticker] = pd.Timestamp.max.normalize()
            continue
        states[original] = "accepted_fill"
        active_until[ticker] = pd.Timestamp(exit_date)
    return pd.Series(states).reindex(range(len(frame)))


def wilson_interval(
    successes: int, total: int, z: float = 1.959963984540054
) -> tuple[float | None, float | None]:
    """Wilson 95% interval for a binary rate."""

    if total <= 0:
        return None, None
    p = float(successes) / float(total)
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    half = (
        z
        * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return max(0.0, centre - half), min(1.0, centre + half)


def cluster_bootstrap_mean(
    values: Sequence[Any],
    clusters: Sequence[Any],
    *,
    reps: int = 1_000,
    seed: int = 20_260_808,
) -> tuple[float | None, float | None]:
    """Deterministic row-weighted one-way cluster-bootstrap interval."""

    frame = pd.DataFrame(
        {"value": pd.to_numeric(values, errors="coerce"), "cluster": clusters}
    )
    frame = frame.dropna(subset=["value", "cluster"])
    if frame.empty:
        return None, None
    grouped = frame.groupby("cluster", sort=True)["value"].agg(["sum", "count"])
    sums = grouped["sum"].to_numpy(dtype=float)
    counts = grouped["count"].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    draws = np.empty(reps, dtype=float)
    n_clusters = len(grouped)
    for i in range(reps):
        sampled = rng.integers(0, n_clusters, size=n_clusters)
        denominator = counts[sampled].sum()
        draws[i] = sums[sampled].sum() / denominator if denominator else np.nan
    finite = draws[np.isfinite(draws)]
    if not len(finite):
        return None, None
    low, high = np.quantile(finite, [0.025, 0.975])
    return float(low), float(high)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata_fingerprint(paths: Iterable[Path], *, root: Path) -> str:
    """Stable path/size fingerprint used only for blocked legacy diagnostics."""

    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(f"{relative}\0{path.stat().st_size}\n".encode())
    return digest.hexdigest()


def canonical_ticker(value: Any) -> str:
    ticker = str(value).strip().upper()
    return f"{ticker[:-3]}.SS" if ticker.endswith(".SH") else ticker


def _board_widths(ticker: str, dates: pd.DatetimeIndex) -> np.ndarray:
    code = canonical_ticker(ticker).split(".")[0]
    if code.startswith(("688", "689")):
        return np.full(len(dates), 0.20, dtype=float)
    if code.startswith(("300", "301", "302")):
        return np.where(dates >= pd.Timestamp("2020-08-24"), 0.20, 0.10)
    if code.startswith(("8", "4", "92")):
        return np.full(len(dates), 0.30, dtype=float)
    return np.full(len(dates), 0.10, dtype=float)


def _vector_half_up_positive(values: np.ndarray) -> np.ndarray:
    """Vector half-up for a legacy diagnostic, not an authority calculation."""

    scaled = values * 100.0
    return np.floor(np.nextafter(scaled, np.inf) + 0.5) / 100.0


def legacy_substrate_diagnostic(
    raw_dir: Path,
    *,
    st_snapshot_path: Path | None = DEFAULT_ST_SNAPSHOT,
    example_limit: int = 20,
) -> dict[str, Any]:
    """Audit the invalid Yahoo plane without producing any strategy metric."""

    files = sorted(raw_dir.glob("*.parquet")) if raw_dir.exists() else []
    if not files:
        return {
            "status": "legacy_raw_absent",
            "authority": "SUBSTRATE_INVALID_DIAGNOSTIC_ONLY",
            "files": 0,
        }

    st_names: set[str] = set()
    if st_snapshot_path is not None and st_snapshot_path.exists():
        st = pd.read_parquet(st_snapshot_path)
        column = (
            "ticker"
            if "ticker" in st.columns
            else "ts_code"
            if "ts_code" in st.columns
            else None
        )
        if column:
            st_names = {canonical_ticker(value) for value in st[column].dropna()}

    counts: dict[str, int] = {
        "rows": 0,
        "rows_with_prior_close": 0,
        "prior_close_not_exact_cent_at_1e_9_cny": 0,
        "prior_close_off_cny_0_01_tick": 0,
        "eligible_width_heuristic_rows": 0,
        "eligible_prior_close_not_exact_cent_at_1e_9_cny": 0,
        "eligible_prior_close_off_cny_0_01_tick": 0,
        "half_up_vs_legacy_upper_price_diff_rows": 0,
        "strict_seal_half_up": 0,
        "strict_seal_legacy": 0,
        "strict_seal_added_by_half_up": 0,
        "strict_seal_removed_by_half_up": 0,
        "exact_touch_half_up": 0,
        "exact_touch_legacy": 0,
        "exact_touch_added_by_half_up": 0,
        "exact_touch_removed_by_half_up": 0,
        "tolerant_close_half_up": 0,
        "tolerant_close_legacy": 0,
        "tolerant_close_symmetric_diff": 0,
        "files_read": 0,
        "files_failed": 0,
        "current_st_files_excluded": 0,
    }
    examples: list[dict[str, Any]] = []
    failed_files: list[str] = []

    for path in files:
        ticker = canonical_ticker(path.stem)
        if ticker in st_names:
            counts["current_st_files_excluded"] += 1
            continue
        try:
            frame = pd.read_parquet(path, columns=["open", "high", "close", "volume"])
        except Exception:  # noqa: BLE001 - diagnostic records the unreadable file
            counts["files_failed"] += 1
            failed_files.append(path.name)
            continue
        counts["files_read"] += 1
        counts["rows"] += len(frame)
        dates = pd.DatetimeIndex(
            pd.to_datetime(frame.index, errors="coerce")
        ).normalize()
        opens = pd.to_numeric(frame["open"], errors="coerce").to_numpy(dtype=float)
        highs = pd.to_numeric(frame["high"], errors="coerce").to_numpy(dtype=float)
        closes = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
        volumes = pd.to_numeric(frame["volume"], errors="coerce").to_numpy(dtype=float)
        previous = np.roll(closes, 1)
        if len(previous):
            previous[0] = np.nan
        widths = _board_widths(ticker, dates)
        finite_prior = np.isfinite(previous) & (previous > 0)
        counts["rows_with_prior_close"] += int(finite_prior.sum())
        tick_distance_cny = np.abs(previous - np.round(previous, 2))
        not_exact_cent = finite_prior & (tick_distance_cny > 1e-9)
        off_tick = finite_prior & (tick_distance_cny > TICK_ALIGNMENT_EPSILON_CNY)
        counts["prior_close_not_exact_cent_at_1e_9_cny"] += int(not_exact_cent.sum())
        counts["prior_close_off_cny_0_01_tick"] += int(off_tick.sum())

        valid = (
            finite_prior
            & np.isfinite(opens)
            & (opens > 0)
            & np.isfinite(highs)
            & (highs > 0)
            & np.isfinite(closes)
            & (closes > 0)
            & np.isfinite(volumes)
            & (volumes > 0)
        )
        corporate_action_proxy = valid & (
            np.abs(opens - previous) / previous > widths * 1.5
        )
        valid &= ~corporate_action_proxy
        counts["eligible_width_heuristic_rows"] += int(valid.sum())
        counts["eligible_prior_close_not_exact_cent_at_1e_9_cny"] += int(
            (valid & not_exact_cent).sum()
        )
        counts["eligible_prior_close_off_cny_0_01_tick"] += int(
            (valid & off_tick).sum()
        )
        raw_upper = previous * (1.0 + widths)
        half_up = _vector_half_up_positive(raw_upper)
        legacy = np.round(raw_upper, 2)
        price_diff = valid & ~np.isclose(half_up, legacy, rtol=0.0, atol=1e-12)
        counts["half_up_vs_legacy_upper_price_diff_rows"] += int(price_diff.sum())

        strict_half = valid & (closes >= half_up)
        strict_legacy = valid & (closes >= legacy)
        touch_half = valid & (highs >= half_up)
        touch_legacy = valid & (highs >= legacy)
        tolerant_half = valid & (closes >= half_up * (1.0 - TOLERANT_CUSHION))
        tolerant_legacy = valid & (closes >= legacy * (1.0 - TOLERANT_CUSHION))
        counts["strict_seal_half_up"] += int(strict_half.sum())
        counts["strict_seal_legacy"] += int(strict_legacy.sum())
        counts["strict_seal_added_by_half_up"] += int(
            (strict_half & ~strict_legacy).sum()
        )
        counts["strict_seal_removed_by_half_up"] += int(
            (strict_legacy & ~strict_half).sum()
        )
        counts["exact_touch_half_up"] += int(touch_half.sum())
        counts["exact_touch_legacy"] += int(touch_legacy.sum())
        counts["exact_touch_added_by_half_up"] += int(
            (touch_half & ~touch_legacy).sum()
        )
        counts["exact_touch_removed_by_half_up"] += int(
            (touch_legacy & ~touch_half).sum()
        )
        counts["tolerant_close_half_up"] += int(tolerant_half.sum())
        counts["tolerant_close_legacy"] += int(tolerant_legacy.sum())
        counts["tolerant_close_symmetric_diff"] += int(
            (tolerant_half ^ tolerant_legacy).sum()
        )

        changed = np.flatnonzero(
            price_diff & ((strict_half ^ strict_legacy) | (touch_half ^ touch_legacy))
        )
        for index in changed:
            if len(examples) >= example_limit:
                break
            examples.append(
                {
                    "ticker": ticker,
                    "date": str(dates[index].date()),
                    "previous_close": float(previous[index]),
                    "width": float(widths[index]),
                    "high": float(highs[index]),
                    "close": float(closes[index]),
                    "half_up_upper": float(half_up[index]),
                    "legacy_upper": float(legacy[index]),
                    "strict_half_up": bool(strict_half[index]),
                    "strict_legacy": bool(strict_legacy[index]),
                    "touch_half_up": bool(touch_half[index]),
                    "touch_legacy": bool(touch_legacy[index]),
                }
            )

    return {
        "status": "audited_invalid_plane",
        "authority": "SUBSTRATE_INVALID_DIAGNOSTIC_ONLY",
        "warning": (
            "Yahoo raw remains split-adjusted; these are detector-engineering counts only. "
            "No transition, return, fill, or strategy metric was computed."
        ),
        "scope_limitations": [
            "current ST-snapshot intersections excluded across all history",
            "board width inferred from ticker/date only",
            "historical ST, IPO no-limit, and exact corporate-action rules are not reconstructed",
            "vector half-up comparison is diagnostic; vendor stk_limit is the future authority",
        ],
        "tick_alignment_epsilon_cny": TICK_ALIGNMENT_EPSILON_CNY,
        "raw_metadata_fingerprint": _metadata_fingerprint(files, root=raw_dir),
        "files_discovered": len(files),
        "counts": counts,
        "changed_event_key_examples": examples,
        "failed_files": failed_files[:50],
    }


def _parquet_columns(path: Path) -> set[str]:
    """Return the union of Parquet columns for a file or partition directory."""

    try:
        import pyarrow.dataset as ds
    except ImportError as exc:  # pragma: no cover - repo runtime has pyarrow
        raise RuntimeError("pyarrow is required for the substrate gate") from exc
    dataset = ds.dataset(path, format="parquet")
    return set(dataset.schema.names)


def _schema_gate(path: Path, required: set[str] | frozenset[str]) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(
                path.relative_to(ROOT)
                if path.is_absolute() and ROOT in path.parents
                else path
            ),
            "exists": False,
            "columns": [],
            "missing_columns": sorted(required),
            "pass": False,
        }
    try:
        columns = _parquet_columns(path)
        error = None
    except Exception as exc:  # noqa: BLE001 - receipt must preserve gate failure
        columns = set()
        error = f"{type(exc).__name__}: {exc}"
    missing = sorted(set(required) - columns)
    payload: dict[str, Any] = {
        "path": str(
            path.relative_to(ROOT)
            if path.is_absolute() and ROOT in path.parents
            else path
        ),
        "exists": True,
        "sha256": _sha256_file(path) if path.is_file() else None,
        "columns": sorted(columns),
        "missing_columns": missing,
        "pass": not missing and error is None,
    }
    if error:
        payload["error"] = error
    return payload


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    return str(resolved.relative_to(ROOT)) if ROOT in resolved.parents else str(path)


def _monthly_partition_layout_matches(relative: Path, plane: str) -> bool:
    parts = relative.parts
    return bool(
        len(parts) == 4
        and parts[0] == plane
        and parts[1].startswith("year=")
        and len(parts[1]) == 9
        and parts[1][5:].isdigit()
        and parts[2].startswith("month=")
        and len(parts[2]) == 8
        and parts[2][6:].isdigit()
        and 1 <= int(parts[2][6:]) <= 12
        and parts[3] == "part.parquet"
    )


def _manifest_receipt_gate(
    store: Path,
    receipt: Mapping[str, Any],
    *,
    exact_relative: str | None = None,
    partition_plane: str | None = None,
) -> dict[str, Any]:
    """Verify one manifest-addressed file without trusting an escaping path."""

    relative = Path(str(receipt.get("path") or ""))
    candidate = (store / relative).resolve()
    try:
        candidate.relative_to(store.resolve())
        path_safe = bool(relative.as_posix() and not relative.is_absolute())
    except ValueError:
        path_safe = False
    exists = bool(path_safe and candidate.is_file())
    expected_hash = str(receipt.get("sha256") or "")
    actual_hash = _sha256_file(candidate) if exists else None
    expected_bytes = receipt.get("bytes")
    actual_bytes = candidate.stat().st_size if exists else None
    duplicate_rows = receipt.get("duplicate_key_rows")
    layout_matches = bool(
        (exact_relative is not None and relative.as_posix() == exact_relative)
        or (
            partition_plane is not None
            and _monthly_partition_layout_matches(relative, partition_plane)
        )
    )
    passed = bool(
        path_safe
        and layout_matches
        and exists
        and actual_hash == expected_hash
        and actual_bytes == expected_bytes
        and (duplicate_rows is None or duplicate_rows == 0)
    )
    return {
        "path": relative.as_posix(),
        "path_safe": path_safe,
        "layout_matches": layout_matches,
        "exists": exists,
        "sha256_matches": bool(exists and actual_hash == expected_hash),
        "bytes_match": bool(exists and actual_bytes == expected_bytes),
        "duplicate_key_rows": duplicate_rows,
        "pass": passed,
    }


def _manifest_identity_sha256(manifest: Mapping[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_identity_sha256", None)
    raw = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _manifest_gate(
    *, manifest_path: Path, schema_path: Path, store: Path
) -> dict[str, Any]:
    schema_path_matches = schema_path.resolve() == DEFAULT_MANIFEST_SCHEMA.resolve()
    schema_actual_sha256 = _sha256_file(schema_path) if schema_path.is_file() else None
    schema_sha256_matches = schema_actual_sha256 == MANIFEST_SCHEMA_SHA256
    payload: dict[str, Any] = {
        "path": _display_path(manifest_path),
        "schema_path": _display_path(schema_path),
        "exists": manifest_path.is_file(),
        "schema_exists": schema_path.is_file(),
        "manifest_sha256": (
            _sha256_file(manifest_path) if manifest_path.is_file() else None
        ),
        "schema_sha256": schema_actual_sha256,
        "schema_binding": {
            "expected_path": _display_path(DEFAULT_MANIFEST_SCHEMA),
            "expected_sha256": MANIFEST_SCHEMA_SHA256,
            "path_matches": schema_path_matches,
            "sha256_matches": schema_sha256_matches,
            "pass": bool(schema_path_matches and schema_sha256_matches),
        },
        "schema_valid": False,
        "identity_valid": False,
        "semantic_checks": {},
        "file_receipts": [],
        "pass": False,
    }
    if not manifest_path.is_file() or not schema_path.is_file():
        return payload
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        from jsonschema import Draft202012Validator, FormatChecker

        errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
                manifest
            ),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except Exception as exc:  # noqa: BLE001 - gate records exact class, never source payload
        payload["error"] = f"{type(exc).__name__}: {exc}"
        return payload
    payload["schema_valid"] = not errors
    if errors:
        payload["schema_error_sample"] = [
            {
                "path": "/".join(str(part) for part in error.absolute_path),
                "message": error.message,
            }
            for error in errors[:10]
        ]

    declared_identity = str(manifest.get("manifest_identity_sha256") or "")
    calculated_identity = _manifest_identity_sha256(manifest)
    payload["identity_valid"] = declared_identity == calculated_identity
    requested = manifest.get("requested_range") or {}
    reference = manifest.get("reference") or {}
    canonical = manifest.get("canonical_event_substrate") or {}
    coverage = manifest.get("daily_security_coverage") or {}
    endpoints = manifest.get("endpoints") or {}
    daily_endpoint = endpoints.get("daily") or {}
    limits_endpoint = endpoints.get("stk_limit") or {}
    st_endpoint = endpoints.get("stock_st") or {}
    checks = {
        "schema_version": manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION,
        "authority_context_only": manifest.get("authority") == "context_only",
        "source_tushare_pro": manifest.get("source") == "tushare_pro",
        "manifest_complete": manifest.get("complete") is True,
        "reference_ready": reference.get("ready") is True,
        "canonical_event_ready": canonical.get("ready") is True,
        "daily_security_coverage_complete": coverage.get("complete") is True,
        "measurement_start_covered": str(requested.get("start") or "")
        <= MEASUREMENT_START,
        "measurement_end_covered": str(requested.get("end") or "") >= MEASUREMENT_END,
        "daily_endpoint_complete": (
            daily_endpoint.get("required") is True
            and daily_endpoint.get("complete") is True
        ),
        "stk_limit_endpoint_complete": (
            limits_endpoint.get("required") is True
            and limits_endpoint.get("complete") is True
        ),
        "stock_st_endpoint_complete_from_2016": (
            st_endpoint.get("required") is True and st_endpoint.get("complete") is True
        ),
        "daily_source_exact": (
            canonical.get("daily_source") == "tushare.daily_unadjusted_nominal"
        ),
        "limit_source_exact": (
            canonical.get("limit_source") == "tushare.stk_limit_exact_daily"
        ),
        "integer_price_unit_cents": canonical.get("integer_price_unit") == "CNY_cents",
        "calculated_limits_not_event_authority": (
            canonical.get("calculated_limit_role")
            == "validator_only_never_event_authority"
        ),
    }
    payload["semantic_checks"] = checks

    receipt_specs: list[tuple[Mapping[str, Any], str | None, str | None]] = []
    for key, relative in (
        ("security_master", "reference/security_master.parquet"),
        ("market_sessions", "reference/market_sessions.parquet"),
    ):
        receipt = reference.get(key)
        if isinstance(receipt, Mapping):
            receipt_specs.append((receipt, relative, None))
    for endpoint, plane in (
        (daily_endpoint, "daily"),
        (limits_endpoint, "stk_limit"),
        (st_endpoint, "stock_st"),
        (canonical, "event_daily"),
    ):
        receipt_specs.extend(
            (receipt, None, plane)
            for receipt in endpoint.get("partitions") or []
            if isinstance(receipt, Mapping)
        )
    receipt_gates = [
        _manifest_receipt_gate(
            store,
            receipt,
            exact_relative=exact_relative,
            partition_plane=partition_plane,
        )
        for receipt, exact_relative, partition_plane in receipt_specs
    ]
    payload["file_receipts"] = receipt_gates
    payload["receipt_count"] = len(receipt_gates)
    payload["all_file_receipts_pass"] = bool(
        receipt_gates and all(gate["pass"] for gate in receipt_gates)
    )
    payload["pass"] = bool(
        payload["schema_binding"]["pass"]
        and payload["schema_valid"]
        and payload["identity_valid"]
        and all(checks.values())
        and payload["all_file_receipts_pass"]
    )
    return payload


def _spine_layout_gate(
    *,
    store: Path,
    daily: Path,
    limits: Path,
    event_daily: Path,
    calendar: Path,
    security_master: Path,
    stock_st: Path,
    coverage: Path,
    manifest: Path,
) -> dict[str, Any]:
    """Bind every consumed plane to one selected spine root and v1 layout."""

    expected = {
        "daily": store / "daily",
        "limits": store / "stk_limit",
        "event_daily": store / "event_daily",
        "calendar": store / "reference" / "market_sessions.parquet",
        "security_master": store / "reference" / "security_master.parquet",
        "stock_st": store / "stock_st",
        "coverage": store / "coverage" / "daily_security_coverage.parquet",
        "manifest": store / "completeness_manifest.json",
    }
    actual = {
        "daily": daily,
        "limits": limits,
        "event_daily": event_daily,
        "calendar": calendar,
        "security_master": security_master,
        "stock_st": stock_st,
        "coverage": coverage,
        "manifest": manifest,
    }
    bindings = {
        name: {
            "expected": _display_path(expected[name]),
            "actual": _display_path(path),
            "pass": path.resolve() == expected[name].resolve(),
        }
        for name, path in actual.items()
    }
    return {
        "bindings": bindings,
        "pass": all(binding["pass"] for binding in bindings.values()),
        "law": "all consumed planes must resolve to the frozen relative layout under one spine root",
    }


def authoritative_substrate_gate(
    *,
    store: Path,
    daily: Path,
    limits: Path,
    event_daily: Path,
    calendar: Path,
    security_master: Path,
    stock_st: Path,
    coverage: Path,
    manifest: Path,
    manifest_schema: Path,
) -> dict[str, Any]:
    daily_gate = _schema_gate(daily, DAILY_REQUIRED)
    limits_gate = _schema_gate(limits, LIMIT_REQUIRED)
    event_gate = _schema_gate(event_daily, EVENT_DAILY_REQUIRED)
    calendar_gate = _schema_gate(calendar, CALENDAR_REQUIRED)
    security_gate = _schema_gate(security_master, SECURITY_MASTER_REQUIRED)
    st_gate = _schema_gate(stock_st, STOCK_ST_REQUIRED)
    coverage_gate = _schema_gate(coverage, COVERAGE_REQUIRED)
    layout_gate = _spine_layout_gate(
        store=store,
        daily=daily,
        limits=limits,
        event_daily=event_daily,
        calendar=calendar,
        security_master=security_master,
        stock_st=stock_st,
        coverage=coverage,
        manifest=manifest,
    )
    manifest_gate = _manifest_gate(
        manifest_path=manifest, schema_path=manifest_schema, store=store
    )
    gates = {
        "tushare_unadjusted_daily": daily_gate,
        "tushare_vendor_stk_limit": limits_gate,
        "canonical_event_daily": event_gate,
        "attested_market_sessions": calendar_gate,
        "effective_dated_security_master": security_gate,
        "exact_daily_stock_st_from_2016": st_gate,
        "daily_security_coverage": coverage_gate,
    }
    event_columns = set(event_gate.get("columns") or [])
    overlay_missing = sorted(MEASUREMENT_OVERLAY_REQUIRED - event_columns)
    canonical_schema_pass = all(bool(gate.get("pass")) for gate in gates.values())
    shape_ready_for_row_attestation = bool(
        canonical_schema_pass
        and layout_gate["pass"]
        and manifest_gate["pass"]
        and not overlay_missing
    )
    generation_binding = {
        "required": True,
        "required_evidence": [
            "one promoted_generation_id in the manifest",
            "every input/reference/partition receipt bound to that generation",
            "consumer re-attestation that no mixed-vintage plane is present",
        ],
        "available_in_snapshot_v1": False,
        "pass": False,
        "law": "correct paths and hashes are insufficient unless they belong to one promoted generation",
    }
    return {
        "contract_snapshot_commit": CONTRACT_SNAPSHOT_COMMIT,
        "contract_snapshot_status": CONTRACT_SNAPSHOT_STATUS,
        "contract_snapshot_has_readiness_authority": False,
        "store": _display_path(store),
        "partition_contract": "{daily,stk_limit,event_daily}/year=YYYY/month=MM/part.parquet",
        "layout_binding": layout_gate,
        "gates": gates,
        "manifest": manifest_gate,
        "all_canonical_schema_gates_pass": canonical_schema_pass,
        "manifest_gate_pass": bool(manifest_gate["pass"]),
        "measurement_overlay": {
            "required_columns": sorted(MEASUREMENT_OVERLAY_REQUIRED),
            "missing_columns": overlay_missing,
            "pass": not overlay_missing,
            "law": "missing eligibility/rule fields remain blockers; this adapter does not infer them",
        },
        "shape_ready_for_row_attestation": shape_ready_for_row_attestation,
        "generation_binding": generation_binding,
        "contract_ready_for_row_attestation": False,
        # This packet implements the deterministic row contract but intentionally
        # does not run it against live partitions. Schema/manifest presence alone
        # can therefore never authorize measurement.
        "ready_for_measurement": False,
        "row_level_measurement_gates_run": False,
        "row_level_measurement_gates_pass": False,
        "row_level_measurement_gates_pending": [
            "event_daily unique ticker/date keys re-attested by the consumer",
            "all input hashes bound to one promoted generation identity",
            (
                "integer-cent OHLC ordering, inclusive vendor-bound containment, exact-equality "
                "event flags, and daily/limit previous-close equality re-attested"
            ),
            "positive_volume and source_limits_present restricted exactly",
            "event_daily market_session_position joined one-to-one to market_sessions",
            "effective security lifecycle expanded to a dense exact-session eligibility state",
            "rule cohort and IPO no-limit state materialized rather than ratio-inferred",
            "historical ST state joined with pre-2016 uncertainty quarantined",
            "corporate-action reference state materialized rather than inferred",
            "daily security coverage hash and counts re-attested against event/master rows",
            "exact successor and exit horizon support",
        ],
    }


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def build_receipt(
    *,
    store: Path = DEFAULT_SPINE_ROOT,
    daily: Path,
    limits: Path,
    event_daily: Path = DEFAULT_EVENT_DAILY,
    calendar: Path,
    security_master: Path = DEFAULT_SECURITY_MASTER,
    stock_st: Path = DEFAULT_STOCK_ST,
    coverage: Path = DEFAULT_COVERAGE,
    manifest: Path = DEFAULT_MANIFEST,
    manifest_schema: Path = DEFAULT_MANIFEST_SCHEMA,
    legacy_raw: Path | None,
    st_snapshot: Path | None,
) -> dict[str, Any]:
    gate = authoritative_substrate_gate(
        store=store,
        daily=daily,
        limits=limits,
        event_daily=event_daily,
        calendar=calendar,
        security_master=security_master,
        stock_st=stock_st,
        coverage=coverage,
        manifest=manifest,
        manifest_schema=manifest_schema,
    )
    status = "BLOCKED_SUBSTRATE"
    verdict = "BLOCKED_SUBSTRATE_NO_STRATEGY_MEASUREMENT"
    blockers: list[str] = []
    if not gate["contract_snapshot_has_readiness_authority"]:
        blockers.append(
            "the b2548fdc095 v1 contract is a schema-shape snapshot only and is pending a "
            "remediated promoted spine authority"
        )
    if not gate["layout_binding"]["pass"]:
        blockers.append(
            "one or more consumed planes do not resolve to the selected spine root's exact "
            "relative contract layout"
        )
    if not gate["all_canonical_schema_gates_pass"] or not gate["manifest_gate_pass"]:
        blockers.append(
            "the selected spine partitions, references, coverage, or pinned-schema complete "
            "manifest are absent/incomplete"
        )
    missing = gate["measurement_overlay"]["missing_columns"]
    if missing:
        blockers.append(
            "event_daily lacks frozen measurement eligibility/rule fields: "
            + ", ".join(missing)
        )
    if not gate["generation_binding"]["pass"]:
        blockers.append(
            "snapshot v1 cannot prove that every input hash belongs to one promoted generation"
        )
    if not gate["row_level_measurement_gates_pass"]:
        blockers.append("consumer-side row re-attestation has not run")
    blocker = "; ".join(blockers)
    legacy = (
        legacy_substrate_diagnostic(legacy_raw, st_snapshot_path=st_snapshot)
        if legacy_raw is not None
        else {
            "status": "not_requested",
            "authority": "SUBSTRATE_INVALID_DIAGNOSTIC_ONLY",
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "receipt_date": RECEIPT_DATE,
        "authority": AUTHORITY,
        "status": status,
        "verdict": verdict,
        "blocker": blocker,
        "blockers": blockers,
        "strategy_metrics_emitted": False,
        "transition_rates_emitted": False,
        "return_metrics_emitted": False,
        "fill_metrics_emitted": False,
        "instrument": {
            "path": str(Path(__file__).resolve().relative_to(ROOT)),
            "sha256": _sha256_file(Path(__file__).resolve()),
        },
        "construction_protocol": {
            "path": str(PROTOCOL_PATH.relative_to(ROOT)),
            "sha256": _sha256_file(PROTOCOL_PATH),
            "frozen_before_measurement": True,
            "premeasurement_contract_corrections": list(
                PREMEASUREMENT_CONTRACT_CORRECTIONS
            ),
            "outcome_measurement_observed_before_corrections": False,
            "construction_ids": list(ALL_CONSTRUCTION_IDS),
            "tolerant_close_is_legal_seal": False,
            "daily_bars_can_claim_path_order": False,
            "strict_seal_predicate": "close_cents == up_limit_cents after bound validation",
            "exact_touch_predicate": "high_cents == up_limit_cents after bound validation",
            "out_of_vendor_bounds_policy": "quarantine_no_classification",
            "entry_clock": "D close information to D+1 reported-open daily_tradability_proxy",
            "exits": ["E1_OPEN_D+2", "E1_CLOSE_D+2", "E3_CLOSE_D+4"],
            "cost_bps_round_trip": [0, 30, 60, 100],
            "bootstrap": {
                "date_clusters": True,
                "run_clusters": True,
                "repetitions": 1000,
                "seed": 20260808,
            },
        },
        "authoritative_substrate": gate,
        "legacy_substrate_diagnostic": legacy,
        "ore_ledger": {
            "law": (
                "A blocked or adverse exact construction cannot close the family; "
                "untested variants remain explicit and append-only."
            ),
            "untested_variants": list(UNTESTED_VARIANTS),
        },
        "next_action": (
            "land a remediated full-A TuShare spine contract with one promoted-generation identity, "
            "materialize the missing rule/lifecycle eligibility overlay without inference, pin the "
            "new schema/commit, re-attest every row-level gate, then execute the deterministic measurement"
        ),
    }


def render_markdown(receipt: Mapping[str, Any]) -> str:
    gate = receipt["authoritative_substrate"]
    lines = [
        "# CN limit-move alpha — Wave-2 band-progress substrate receipt",
        "",
        f"**Date:** {receipt['receipt_date']}",
        f"**Authority:** {receipt['authority']}",
        f"**Status:** `{receipt['status']}`",
        f"**Verdict:** `{receipt['verdict']}`",
        "",
        "## Outcome",
        "",
        (
            "The construction grammar is frozen, but no strategy measurement is admissible yet. "
            "The historical Yahoo plane remains split-adjusted and cannot reconstruct legal CNY "
            "0.01 limit prices. The adapter now binds to the canonical full-A v1 event plane and "
            "manifest, but it does not invent missing rule/lifecycle fields. No transition, return, "
            "fill, or strategy metric appears in this receipt."
        ),
        "",
        f"Exact blocker: {receipt['blocker']}.",
        "",
        "## Pre-measurement contract corrections",
        "",
        (
            "These corrections were recorded before any Wave-2 outcome, transition, return, fill, "
            "or strategy measurement. They bind the packet to the canonical v1 store and replace "
            "defensive comparisons with exact bounded integer-cent event predicates; no return-led "
            "threshold tuning occurred."
        ),
        "",
        "- Strict legal seal: `close_cents == up_limit_cents` after full OHLC bound validation.",
        "- Exact upper touch: `high_cents == up_limit_cents` after full OHLC bound validation.",
        (
            "- Any event-eligible OHLC outside `[down_limit_cents, up_limit_cents]` is quarantined "
            "without a signal classification."
        ),
        "",
        "## Authoritative input gates",
        "",
        "| Plane | Exists | Schema pass | Missing columns / contract |",
        "|---|---:|---:|---|",
    ]
    for name, payload in gate["gates"].items():
        missing = ", ".join(payload.get("missing_columns") or []) or "—"
        lines.append(
            f"| `{name}` | {str(bool(payload.get('exists'))).lower()} | "
            f"{str(bool(payload.get('pass'))).lower()} | {missing} |"
        )
    manifest = gate["manifest"]
    overlay = gate["measurement_overlay"]
    lines.extend(
        [
            "",
            "## Manifest and measurement overlay",
            "",
            f"- Spine shape-snapshot commit: `{gate['contract_snapshot_commit']}`",
            f"- Snapshot status: `{gate['contract_snapshot_status']}`",
            (
                "- Snapshot has readiness authority: "
                f"**{str(bool(gate['contract_snapshot_has_readiness_authority'])).lower()}**"
            ),
            f"- Partition contract: `{gate['partition_contract']}`",
            f"- One-root layout binding passes: **{str(bool(gate['layout_binding']['pass'])).lower()}**",
            (
                f"- Manifest exists / schema-valid / identity-valid / passes: "
                f"**{str(bool(manifest.get('exists'))).lower()} / "
                f"{str(bool(manifest.get('schema_valid'))).lower()} / "
                f"{str(bool(manifest.get('identity_valid'))).lower()} / "
                f"{str(bool(manifest.get('pass'))).lower()}**"
            ),
            f"- Canonical schemas pass: **{str(bool(gate['all_canonical_schema_gates_pass'])).lower()}**",
            f"- Measurement-overlay pass: **{str(bool(overlay['pass'])).lower()}**",
            f"- Missing overlay fields: **{', '.join(overlay['missing_columns']) or 'none'}**",
            (
                "- Single promoted-generation binding passes: "
                f"**{str(bool(gate['generation_binding']['pass'])).lower()}**"
            ),
            (
                "- Contract ready for row re-attestation / measurement ready: "
                f"**{str(bool(gate['contract_ready_for_row_attestation'])).lower()} / "
                f"{str(bool(gate['ready_for_measurement'])).lower()}**"
            ),
            "",
            (
                "Row-level uniqueness, join, exact-cent equality, OHLC bound, corporate-action, and "
                "exact-exit-clock gates remain pending even if the file schemas appear."
            ),
            "",
            "## Frozen definitions",
            "",
            "- Strict seal: integer-cent close equals vendor `stk_limit.up_limit_cents` exactly.",
            "- Tolerant-only close: inside the 0.2% cushion but below the legal ceiling; sensitivity only.",
            (
                "- Exact-touch failure: integer-cent daily high equals the vendor ceiling and close "
                "finishes below it."
            ),
            (
                "- Partial no-touch: high remains below the ceiling, with parallel fixed high-progress and "
                "close-progress buckets at 0.40/0.60/0.80/0.95."
            ),
            (
                "- Entry: D-close information to D+1 reported-open `daily_tradability_proxy`; upper queue "
                "and missing rows remain cash zero."
            ),
            "- Earliest exit: D+2 under A-share T+1; daily bars cannot claim intraday sequence or fill.",
            "",
            "## Legacy-plane diagnostic",
            "",
        ]
    )
    legacy = receipt["legacy_substrate_diagnostic"]
    lines.append(
        f"Status: `{legacy.get('status')}`; authority: `{legacy.get('authority')}`."
    )
    counts = legacy.get("counts") or {}
    if counts:
        lines.extend(
            [
                "",
                f"- Files read / discovered: **{counts.get('files_read', 0):,} / {legacy.get('files_discovered', 0):,}**",
                f"- Stored rows: **{counts.get('rows', 0):,}**",
                f"- Prior closes checked: **{counts.get('rows_with_prior_close', 0):,}**",
                f"- Eligible prior closes not exactly cent-valued at CNY 1e-9: **{counts.get('eligible_prior_close_not_exact_cent_at_1e_9_cny', 0):,} / {counts.get('eligible_width_heuristic_rows', 0):,}**",
                f"- Eligible prior closes materially off tick by more than CNY {TICK_ALIGNMENT_EPSILON_CNY:g}: **{counts.get('eligible_prior_close_off_cny_0_01_tick', 0):,}**",
                f"- Half-up versus legacy upper-price differences: **{counts.get('half_up_vs_legacy_upper_price_diff_rows', 0):,}**",
                f"- Strict-seal key additions/removals under half-up: **{counts.get('strict_seal_added_by_half_up', 0):,} / {counts.get('strict_seal_removed_by_half_up', 0):,}**",
                f"- Exact-touch key additions/removals under half-up: **{counts.get('exact_touch_added_by_half_up', 0):,} / {counts.get('exact_touch_removed_by_half_up', 0):,}**",
                "",
                "These are detector-engineering counts on an invalid substrate, not market findings.",
            ]
        )
    lines.extend(["", "## UNTESTED VARIANTS", ""])
    lines.extend(f"- {item}" for item in receipt["ore_ledger"]["untested_variants"])
    lines.extend(
        [
            "",
            "## Next action",
            "",
            receipt["next_action"] + ".",
            "",
        ]
    )
    return "\n".join(lines)


def write_receipts(
    receipt: Mapping[str, Any], *, json_path: Path, markdown_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(_canonical_json(receipt), encoding="utf-8")
    markdown_path.write_text(render_markdown(receipt), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spine-root",
        "--store",
        dest="spine_root",
        type=Path,
        default=DEFAULT_SPINE_ROOT,
        help=(
            "private full-A spine root; every child plane is bound to the frozen relative "
            "layout with no split-plane override"
        ),
    )
    parser.add_argument("--legacy-raw-dir", type=Path, default=DEFAULT_LEGACY_RAW)
    parser.add_argument("--st-snapshot", type=Path, default=DEFAULT_ST_SNAPSHOT)
    parser.add_argument("--skip-legacy-audit", action="store_true")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args(argv)
    root = args.spine_root
    args.store = root
    args.daily = root / "daily"
    args.limits = root / "stk_limit"
    args.event_daily = root / "event_daily"
    args.calendar = root / "reference" / "market_sessions.parquet"
    args.security_master = root / "reference" / "security_master.parquet"
    args.stock_st = root / "stock_st"
    args.coverage = root / "coverage" / "daily_security_coverage.parquet"
    args.manifest = root / "completeness_manifest.json"
    args.manifest_schema = DEFAULT_MANIFEST_SCHEMA
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    receipt = build_receipt(
        store=args.store,
        daily=args.daily,
        limits=args.limits,
        event_daily=args.event_daily,
        calendar=args.calendar,
        security_master=args.security_master,
        stock_st=args.stock_st,
        coverage=args.coverage,
        manifest=args.manifest,
        manifest_schema=args.manifest_schema,
        legacy_raw=None if args.skip_legacy_audit else args.legacy_raw_dir,
        st_snapshot=args.st_snapshot,
    )
    write_receipts(receipt, json_path=args.json, markdown_path=args.markdown)
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "verdict": receipt["verdict"],
                "strategy_metrics_emitted": receipt["strategy_metrics_emitted"],
                "json": str(args.json),
                "markdown": str(args.markdown),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
