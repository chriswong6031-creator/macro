"""engine/options_payoff.py — deterministic multi-leg payoff / scenario / Greeks-drift substrate.

RESEARCH EXPRESSION ONLY (MO-DELTA-034, MO-PAID-077: source_rights=research_expression_only).
This module computes what a stated structure IS WORTH under stated assumptions. It has ZERO
entry authority: it never ranks, scores, sizes, admits a contract, selects an expiry, or
recommends. No LLM originates anything here — every number is a closed-form function of inputs
the caller supplied (F03 handoff Method/failure law; Neural Web A7).

NO SECOND BLACK-SCHOLES (F03 do_not_redo: "No second option chain/surface/Greeks/flow/
strategy-pricing engine"). Every greek comes from engine/greeks.py::bs_greeks (:32) and every
option price from engine/intraday_greeks.py::bs_price (:111) / bs_vega (:125). This file
defines NO d1, NO normal CDF, NO closed form. tests/test_options_payoff.py enforces that by AST
scan of this file.

SIGMA IS A DECIMAL (0.15, not 15) — engine/greeks.py:7-8. T is in YEARS, ACT/365 fixed.
Charm from engine/greeks.py is per YEAR (:33) and is divided by 365.0 for a per-day figure.

Inputs come from engine/thetadata_store.py::chain() (:544, columns :548-553), which supplies
NO mid, NO multiplier and NO intraday timestamp. Mid is derived from bid_eod/ask_eod; the
contract multiplier is a REQUIRED caller input whose absence is the typed null
MULTIPLIER_UNKNOWN; the as-of clock grain is the EOD session date, never an instant.

Nulls are PRINTED, never zeroed and never omitted (CLAUDE.md §Epistemics). A missing input
degrades the OUTPUT CLASS that needs it and nothing else: an absent IV kills the scenario grid
and the greeks for that leg while the expiry payoff — which needs no vol, no rate and no time —
still computes. Every returned object carries an AssumptionBlock (model, version, r, q, IV
source, as-of, multiplier) and a tuple of typed states.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from datetime import date as _date
from hashlib import sha256
from typing import Mapping, Sequence

from engine.greeks import bs_greeks
from engine.intraday_greeks import bs_price, bs_vega
from lib.evidence_foundation import canonical_json_bytes, compute_recipe_id

# ── constants ────────────────────────────────────────────────────────────────────────
MODEL_NAME = "black_scholes_dividend_adjusted"
MODEL_VERSION = "options_payoff.v1"
GREEKS_SOURCE = "engine/greeks.py::bs_greeks"
PRICE_SOURCE = "engine/intraday_greeks.py::bs_price"

# Declared constants, mirrored from engine/intraday_greeks.py:50-51 (which mirror
# scripts/build_gex_board.py:151 + engine/gex_model.py:39). NOT a live curve pull.
DEFAULT_R = 0.043
DEFAULT_Q = 0.0
RATE_SOURCE_LABEL = "declared_constant_r_0.043_no_live_curve"
DIVIDEND_SOURCE_LABEL = "declared_constant_q_0.0_no_dividend_feed"

DAYS_PER_YEAR = 365.0  # ACT/365 fixed. Declared, not inferred.
UNBOUNDED = "UNBOUNDED"  # sentinel STRING. Never a large float. Never None.
WIDE_SPREAD_RATIO = 0.25  # (ask-bid)/mid above which a leg is flagged WIDE_SPREAD
MAX_LEGS = 8
DEFAULT_MAX_STALE_SESSIONS = 1

THETA_METHOD = "finite_difference_over_shared_pricer"
_TOL = 1e-9

NULL_STATES: frozenset[str] = frozenset(
    {
        "QUOTE_MISSING",
        "QUOTE_CROSSED",
        "ZERO_BID_LIQUIDITY",
        "WIDE_SPREAD",
        "LEG_IV_MISSING",
        "MULTIPLIER_UNKNOWN",
        "CORPORATE_ACTION_UNVERIFIED",
        "CHAIN_EMPTY",
        "CHAIN_STALE",
        "LEG_NOT_IN_CHAIN",
        "IDENTITY_MISMATCH",
        "OPEN_INTEREST_MISSING",
        "EXPIRY_PASSED",
        "EXPIRY_PASSED_AT_HORIZON",
        "MODEL_INPUT_ABSENT",
        "UNSUPPORTED_STRATEGY",
        "INCOMPLETE_LEGS",
        "NO_BREAKEVEN",
    }
)

SHAPES = (
    "single",
    "vertical",
    "calendar",
    "diagonal",
    "straddle",
    "strangle",
    "collar",
    "butterfly",
    "risk_reversal",
    "custom",
)


# ── dataclasses ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class NullState:
    code: str
    scope: str
    reason: str
    receipt: dict[str, object]


@dataclass(frozen=True)
class LegQuote:
    bid: float | None
    ask: float | None
    mid: float | None
    open_interest: float | None
    volume: float | None
    asof_date: str
    source: str


@dataclass(frozen=True)
class Leg:
    right: str
    strike: float
    expiration: str
    qty: int
    entry_price: float | None
    multiplier: float | None
    iv: float | None
    quote: LegQuote | None = None
    states: tuple[NullState, ...] = ()


@dataclass(frozen=True)
class Structure:
    root: str
    legs: tuple[Leg, ...]
    asof_date: str
    shape: str
    states: tuple[NullState, ...] = ()


@dataclass(frozen=True)
class AssumptionBlock:
    model_name: str
    model_version: str
    greeks_source: str
    price_source: str
    r: float
    q: float
    rate_source: str
    dividend_source: str
    iv_source: str
    asof_date: str
    asof_grain: str
    day_count: str
    multipliers: tuple[float | None, ...]
    sigma_convention: str
    oi_timing_note: str


@dataclass(frozen=True)
class PayoffCurve:
    spots: tuple[float, ...]
    pnl: tuple[float | None, ...]
    pnl_per_unit: tuple[float, ...]
    cost: float | None
    cost_per_unit: float
    max_gain: float | str | None
    max_loss: float | str | None
    breakevens: tuple[float, ...]
    assumptions: AssumptionBlock
    states: tuple[NullState, ...]


@dataclass(frozen=True)
class ScenarioGrid:
    spot_shocks: tuple[float, ...]
    vol_shocks: tuple[float, ...]
    days_forward: int
    base_spot: float
    pnl: tuple[tuple[float | None, ...], ...]
    value: tuple[tuple[float | None, ...], ...]
    cell_states: tuple[tuple[tuple[str, ...], ...], ...]
    assumptions: AssumptionBlock
    states: tuple[NullState, ...]


@dataclass(frozen=True)
class LegGreeks:
    delta: float | None
    gamma: float | None
    vanna: float | None
    charm_per_day: float | None
    vega: float | None
    theta_per_day: float | None
    states: tuple[str, ...]


@dataclass(frozen=True)
class GreeksDriftPoint:
    days_forward: int
    t_years: tuple[float, ...]
    per_leg: tuple[LegGreeks, ...]
    net: LegGreeks
    states: tuple[str, ...]


@dataclass(frozen=True)
class GreeksDrift:
    base_spot: float
    points: tuple[GreeksDriftPoint, ...]
    assumptions: AssumptionBlock
    states: tuple[NullState, ...]


@dataclass(frozen=True)
class StructureSummary:
    structure: Structure
    cost: float | None
    max_gain: float | str | None
    max_loss: float | str | None
    breakevens: tuple[float, ...]
    horizon_days: int | None
    horizon_expiry: str | None
    liquidity: str
    prerequisites_met: bool
    states: tuple[NullState, ...]
    assumptions: AssumptionBlock


# ── small internal helpers (NO Black-Scholes math here) ─────────────────────────────
def _is_nan(x: object) -> bool:
    try:
        return isinstance(x, float) and math.isnan(x)
    except TypeError:
        return False


def _finite_or_none(x: object) -> float | None:
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(xf):
        return None
    return xf


def _parse_date(s: str) -> _date:
    y, m, d = s.split("-")
    return _date(int(y), int(m), int(d))


def _dedup_sorted_states(states: Sequence[NullState]) -> tuple[NullState, ...]:
    seen: dict[tuple[str, str], NullState] = {}
    for st in states:
        seen[(st.scope, st.code)] = st
    return tuple(sorted(seen.values(), key=lambda s: (s.scope, s.code)))


def _net_greek_field(per_leg: Sequence["LegGreeks"], legs: Sequence[Leg], field_name: str) -> float | None:
    total = 0.0
    for leg, lg in zip(legs, per_leg):
        val = getattr(lg, field_name)
        if val is None or leg.multiplier is None:
            return None
        total += leg.qty * leg.multiplier * val
    return total


# ── 5.1 shape classification ─────────────────────────────────────────────────────────
def classify_shape(legs: Sequence[Leg]) -> str:
    """Pure geometry over (right, strike, expiration, sign(qty)). DESCRIPTIVE ONLY —
    never an admission or a recommendation."""
    n = len(legs)
    if n == 0:
        return "custom"
    if n == 1:
        return "single"

    if n == 2:
        a, b = legs[0], legs[1]
        same_right = a.right == b.right
        same_strike = a.strike == b.strike
        same_expiry = a.expiration == b.expiration
        sign_a = 1 if a.qty > 0 else (-1 if a.qty < 0 else 0)
        sign_b = 1 if b.qty > 0 else (-1 if b.qty < 0 else 0)

        if same_right and same_expiry and not same_strike:
            return "vertical"
        if same_right and same_strike and not same_expiry:
            return "calendar"
        if same_right and not same_strike and not same_expiry:
            return "diagonal"
        if not same_right and same_expiry:
            # Opposite signs (one long, one short) is a risk-reversal-shaped
            # combo regardless of strike (long P + short C, or the mirror).
            # Matching signs (both long or both short) is straddle/strangle,
            # split on whether the strikes coincide.
            if sign_a != 0 and sign_b != 0 and sign_a != sign_b:
                return "risk_reversal"
            if sign_a == sign_b and sign_a != 0:
                return "straddle" if same_strike else "strangle"
        return "custom"

    if n == 3:
        rights = {leg.right for leg in legs}
        expiries = {leg.expiration for leg in legs}
        if len(rights) == 1 and len(expiries) == 1:
            strikes = [leg.strike for leg in legs]
            order = sorted(range(3), key=lambda i: strikes[i])
            qtys_sorted = [legs[order[i]].qty for i in range(3)]
            lo, mid, hi = qtys_sorted
            if lo != 0 and mid != 0 and hi != 0:
                if lo == hi and mid == -2 * lo:
                    return "butterfly"
        return "custom"

    return "custom"


# ── 5.2 construction ─────────────────────────────────────────────────────────────────
def _mid_from_quote(bid: float | None, ask: float | None, scope: str) -> tuple[float | None, list[NullState]]:
    states: list[NullState] = []
    if bid is None or ask is None:
        states.append(
            NullState(
                code="QUOTE_MISSING",
                scope=scope,
                reason="bid or ask absent/NaN",
                receipt={"bid_eod": bid, "ask_eod": ask, "source": "thetadata_eod_chain"},
            )
        )
        return None, states
    if ask < bid:
        states.append(
            NullState(
                code="QUOTE_CROSSED",
                scope=scope,
                reason="ask < bid",
                receipt={"bid_eod": bid, "ask_eod": ask, "source": "thetadata_eod_chain"},
            )
        )
        return None, states
    if bid == 0.0 and ask == 0.0:
        states.append(
            NullState(
                code="QUOTE_MISSING",
                scope=scope,
                reason="bid and ask both zero",
                receipt={"bid_eod": bid, "ask_eod": ask, "source": "thetadata_eod_chain"},
            )
        )
        return None, states
    if bid == 0.0 and ask > 0.0:
        states.append(
            NullState(
                code="ZERO_BID_LIQUIDITY",
                scope=scope,
                reason="zero bid is not a two-sided market; mid=ask/2 is forbidden",
                receipt={"bid_eod": bid, "ask_eod": ask, "source": "thetadata_eod_chain"},
            )
        )
        return None, states
    mid = (bid + ask) / 2.0
    if mid > 0 and (ask - bid) / mid > WIDE_SPREAD_RATIO:
        states.append(
            NullState(
                code="WIDE_SPREAD",
                scope=scope,
                reason="(ask-bid)/mid exceeds WIDE_SPREAD_RATIO",
                receipt={"bid_eod": bid, "ask_eod": ask, "mid": mid, "ratio": (ask - bid) / mid},
            )
        )
    return mid, states


def leg_from_chain_row(row: Mapping[str, object], *, qty: int, multiplier: float | None) -> Leg:
    scope_placeholder = "leg:?"
    states: list[NullState] = []

    right_raw = row.get("right")
    right = str(right_raw).upper() if right_raw is not None else ""
    if right not in ("C", "P"):
        states.append(
            NullState(
                code="IDENTITY_MISMATCH",
                scope=scope_placeholder,
                reason="right is not C/P",
                receipt={"right": right_raw},
            )
        )

    strike = float(row.get("strike"))
    expiration = str(row.get("expiration"))

    bid = _finite_or_none(row.get("bid_eod"))
    ask = _finite_or_none(row.get("ask_eod"))
    mid, quote_states = _mid_from_quote(bid, ask, scope_placeholder)
    states.extend(quote_states)

    iv_raw = _finite_or_none(row.get("implied_vol"))
    iv: float | None
    if iv_raw is None or iv_raw <= 0:
        iv = None
        states.append(
            NullState(
                code="LEG_IV_MISSING",
                scope=scope_placeholder,
                reason="implied_vol NaN/absent/<=0",
                receipt={"implied_vol": row.get("implied_vol")},
            )
        )
    else:
        iv = iv_raw

    if multiplier is None:
        states.append(
            NullState(
                code="MULTIPLIER_UNKNOWN",
                scope=scope_placeholder,
                reason="caller supplied no multiplier; chain() carries none",
                receipt={"multiplier": None},
            )
        )
    elif multiplier != 100.0:
        states.append(
            NullState(
                code="CORPORATE_ACTION_UNVERIFIED",
                scope=scope_placeholder,
                reason="multiplier != 100.0 cannot be verified against a corporate-action feed",
                receipt={"multiplier": multiplier},
            )
        )

    if qty == 0:
        states.append(
            NullState(
                code="UNSUPPORTED_STRATEGY",
                scope=scope_placeholder,
                reason="leg qty == 0",
                receipt={"qty": qty},
            )
        )

    open_interest = _finite_or_none(row.get("open_interest"))
    volume = _finite_or_none(row.get("volume"))
    asof_date = str(row.get("date")) if row.get("date") is not None else ""

    quote = LegQuote(
        bid=bid,
        ask=ask,
        mid=mid,
        open_interest=open_interest,
        volume=volume,
        asof_date=asof_date,
        source="thetadata_eod_chain",
    )

    return Leg(
        right=right,
        strike=strike,
        expiration=expiration,
        qty=qty,
        entry_price=mid,
        multiplier=multiplier,
        iv=iv,
        quote=quote,
        states=tuple(states),
    )


def _rescope_leg(leg: Leg, idx: int) -> Leg:
    scope = f"leg:{idx}"
    new_states = tuple(
        NullState(code=s.code, scope=scope, reason=s.reason, receipt=s.receipt) for s in leg.states
    )
    return Leg(
        right=leg.right,
        strike=leg.strike,
        expiration=leg.expiration,
        qty=leg.qty,
        entry_price=leg.entry_price,
        multiplier=leg.multiplier,
        iv=leg.iv,
        quote=leg.quote,
        states=new_states,
    )


def structure_from_chain(
    chain_df,
    *,
    root: str,
    asof_date: str,
    leg_specs: Sequence[Mapping[str, object]],
    multipliers: Sequence[float | None] | None = None,
    has_underlying: bool = False,
) -> Structure:
    struct_states: list[NullState] = []

    if chain_df is None or len(chain_df) == 0:
        struct_states.append(
            NullState(
                code="CHAIN_EMPTY",
                scope="structure",
                reason="chain() returned an empty frame",
                receipt={"root": root, "asof_date": asof_date},
            )
        )
        legs: list[Leg] = []
        for i, spec in enumerate(leg_specs):
            right = str(spec["right"]).upper()
            strike = float(spec["strike"])
            expiration = str(spec["expiration"])
            qty = int(spec["qty"])
            multiplier = multipliers[i] if multipliers is not None and i < len(multipliers) else None
            leg_states: list[NullState] = []
            if multiplier is None:
                leg_states.append(
                    NullState(
                        code="MULTIPLIER_UNKNOWN",
                        scope=f"leg:{i}",
                        reason="caller supplied no multiplier",
                        receipt={"multiplier": None},
                    )
                )
            elif multiplier != 100.0:
                leg_states.append(
                    NullState(
                        code="CORPORATE_ACTION_UNVERIFIED",
                        scope=f"leg:{i}",
                        reason="multiplier != 100.0 cannot be verified",
                        receipt={"multiplier": multiplier},
                    )
                )
            if qty == 0:
                leg_states.append(
                    NullState(
                        code="UNSUPPORTED_STRATEGY",
                        scope=f"leg:{i}",
                        reason="leg qty == 0",
                        receipt={"qty": qty},
                    )
                )
            legs.append(
                Leg(
                    right=right,
                    strike=strike,
                    expiration=expiration,
                    qty=qty,
                    entry_price=None,
                    multiplier=multiplier,
                    iv=None,
                    quote=None,
                    states=tuple(leg_states),
                )
            )
        if len(legs) == 0 or len(legs) > MAX_LEGS:
            struct_states.append(
                NullState(
                    code="UNSUPPORTED_STRATEGY",
                    scope="structure",
                    reason="zero legs or too many legs",
                    receipt={"n_legs": len(legs), "max_legs": MAX_LEGS},
                )
            )
        shape = classify_shape(legs) if not has_underlying else "collar"
        return Structure(
            root=root,
            legs=tuple(legs),
            asof_date=asof_date,
            shape=shape,
            states=_dedup_sorted_states(struct_states),
        )

    legs = []
    for i, spec in enumerate(leg_specs):
        right = str(spec["right"]).upper()
        strike = float(spec["strike"])
        expiration = str(spec["expiration"])
        qty = int(spec["qty"])
        multiplier = multipliers[i] if multipliers is not None and i < len(multipliers) else None

        mask = (
            (chain_df["expiration"].astype(str) == expiration)
            & (chain_df["strike"].astype(float) == strike)
            & (chain_df["right"].astype(str).str.upper() == right)
        )
        matched = chain_df[mask]
        if len(matched) == 0:
            leg_states = [
                NullState(
                    code="LEG_NOT_IN_CHAIN",
                    scope=f"leg:{i}",
                    reason="spec not found in chain frame",
                    receipt={"right": right, "strike": strike, "expiration": expiration},
                )
            ]
            if qty == 0:
                leg_states.append(
                    NullState(
                        code="UNSUPPORTED_STRATEGY",
                        scope=f"leg:{i}",
                        reason="leg qty == 0",
                        receipt={"qty": qty},
                    )
                )
            legs.append(
                Leg(
                    right=right,
                    strike=strike,
                    expiration=expiration,
                    qty=qty,
                    entry_price=None,
                    multiplier=multiplier,
                    iv=None,
                    quote=None,
                    states=tuple(leg_states),
                )
            )
            continue

        row = matched.iloc[0].to_dict()
        leg = leg_from_chain_row(row, qty=qty, multiplier=multiplier)
        leg = _rescope_leg(leg, i)

        row_root = row.get("root")
        if row_root is not None and str(row_root) != root:
            extra = NullState(
                code="IDENTITY_MISMATCH",
                scope=f"leg:{i}",
                reason="chain row root does not match requested root",
                receipt={"row_root": row_root, "requested_root": root},
            )
            leg = Leg(
                right=leg.right,
                strike=leg.strike,
                expiration=leg.expiration,
                qty=leg.qty,
                entry_price=leg.entry_price,
                multiplier=leg.multiplier,
                iv=leg.iv,
                quote=leg.quote,
                states=leg.states + (extra,),
            )
        legs.append(leg)

    if len(legs) == 0 or len(legs) > MAX_LEGS:
        struct_states.append(
            NullState(
                code="UNSUPPORTED_STRATEGY",
                scope="structure",
                reason="zero legs or too many legs",
                receipt={"n_legs": len(legs), "max_legs": MAX_LEGS},
            )
        )

    shape = classify_shape(legs) if not has_underlying else "collar"
    return Structure(
        root=root,
        legs=tuple(legs),
        asof_date=asof_date,
        shape=shape,
        states=_dedup_sorted_states(struct_states),
    )


def structure_from_legs(
    legs: Sequence[Leg], *, root: str, asof_date: str, has_underlying: bool = False
) -> Structure:
    """The synthetic/test path — same validation, no DataFrame. Never requires data/."""
    legs = list(legs)
    struct_states: list[NullState] = []
    rescoped: list[Leg] = []
    for i, leg in enumerate(legs):
        extra: list[NullState] = []
        if leg.right not in ("C", "P"):
            extra.append(
                NullState(
                    code="IDENTITY_MISMATCH",
                    scope=f"leg:{i}",
                    reason="right is not C/P",
                    receipt={"right": leg.right},
                )
            )
        if leg.qty == 0:
            extra.append(
                NullState(
                    code="UNSUPPORTED_STRATEGY",
                    scope=f"leg:{i}",
                    reason="leg qty == 0",
                    receipt={"qty": leg.qty},
                )
            )
        if leg.multiplier is None:
            extra.append(
                NullState(
                    code="MULTIPLIER_UNKNOWN",
                    scope=f"leg:{i}",
                    reason="caller supplied no multiplier",
                    receipt={"multiplier": None},
                )
            )
        elif leg.multiplier != 100.0:
            extra.append(
                NullState(
                    code="CORPORATE_ACTION_UNVERIFIED",
                    scope=f"leg:{i}",
                    reason="multiplier != 100.0 cannot be verified",
                    receipt={"multiplier": leg.multiplier},
                )
            )
        if leg.entry_price is None:
            extra.append(
                NullState(
                    code="QUOTE_MISSING",
                    scope=f"leg:{i}",
                    reason="entry_price absent",
                    receipt={"entry_price": None},
                )
            )
        if leg.iv is None or (isinstance(leg.iv, float) and math.isnan(leg.iv)):
            extra.append(
                NullState(
                    code="LEG_IV_MISSING",
                    scope=f"leg:{i}",
                    reason="iv absent/NaN",
                    receipt={"iv": leg.iv},
                )
            )
        existing = _rescope_leg(leg, i)
        combined_states = existing.states + tuple(extra)
        rescoped.append(
            Leg(
                right=existing.right,
                strike=existing.strike,
                expiration=existing.expiration,
                qty=existing.qty,
                entry_price=existing.entry_price,
                multiplier=existing.multiplier,
                iv=None if (leg.iv is not None and isinstance(leg.iv, float) and math.isnan(leg.iv)) else existing.iv,
                quote=existing.quote,
                states=_dedup_sorted_states(combined_states),
            )
        )

    if len(rescoped) == 0 or len(rescoped) > MAX_LEGS:
        struct_states.append(
            NullState(
                code="UNSUPPORTED_STRATEGY",
                scope="structure",
                reason="zero legs or too many legs",
                receipt={"n_legs": len(rescoped), "max_legs": MAX_LEGS},
            )
        )

    shape = classify_shape(rescoped) if not has_underlying else "collar"
    return Structure(
        root=root,
        legs=tuple(rescoped),
        asof_date=asof_date,
        shape=shape,
        states=_dedup_sorted_states(struct_states),
    )


# ── 5.3 expiry payoff ────────────────────────────────────────────────────────────────
def _intrinsic(right: str, K: float, S: float) -> float:
    if right == "C":
        return max(S - K, 0.0)
    return max(K - S, 0.0)


def expiry_payoff(structure: Structure, spots: Sequence[float]) -> PayoffCurve:
    spots = tuple(float(s) for s in spots)
    legs = structure.legs
    states: list[NullState] = list(structure.states)

    abstained_idx = {i for i, leg in enumerate(legs) if leg.entry_price is None}
    if abstained_idx:
        states.append(
            NullState(
                code="QUOTE_MISSING",
                scope="structure",
                reason="one or more legs have no entry price",
                receipt={"abstained_legs": sorted(abstained_idx)},
            )
        )

    missing_mult_idx = {i for i, leg in enumerate(legs) if leg.multiplier is None}

    pnl_per_unit: list[float] = []
    for S in spots:
        total_unit = 0.0
        for i, leg in enumerate(legs):
            if i in abstained_idx:
                continue
            intrinsic = _intrinsic(leg.right, leg.strike, S)
            total_unit += leg.qty * (intrinsic - leg.entry_price)
        pnl_per_unit.append(total_unit)

    if missing_mult_idx:
        pnl: tuple[float | None, ...] = tuple([None] * len(spots))
        cost: float | None = None
        states.append(
            NullState(
                code="MULTIPLIER_UNKNOWN",
                scope="structure",
                reason="one or more legs have no multiplier",
                receipt={"legs_missing_multiplier": sorted(missing_mult_idx)},
            )
        )
        max_gain: float | str | None = None
        max_loss: float | str | None = None
        breakevens: tuple[float, ...] = ()
        cost_per_unit = sum(
            leg.qty * leg.entry_price for i, leg in enumerate(legs) if i not in abstained_idx
        )
        return PayoffCurve(
            spots=spots,
            pnl=pnl,
            pnl_per_unit=tuple(pnl_per_unit),
            cost=cost,
            cost_per_unit=cost_per_unit,
            max_gain=max_gain,
            max_loss=max_loss,
            breakevens=breakevens,
            assumptions=assumption_block(structure, r=DEFAULT_R, q=DEFAULT_Q),
            states=_dedup_sorted_states(states),
        )

    pnl_list: list[float] = []
    for j, S in enumerate(spots):
        total = 0.0
        for i, leg in enumerate(legs):
            if i in abstained_idx:
                continue
            intrinsic = _intrinsic(leg.right, leg.strike, S)
            total += leg.qty * leg.multiplier * (intrinsic - leg.entry_price)
        pnl_list.append(total)

    cost_terms = [
        leg.qty * leg.multiplier * leg.entry_price for i, leg in enumerate(legs) if i not in abstained_idx
    ]
    cost = sum(cost_terms) if cost_terms or not abstained_idx else sum(cost_terms)
    cost_per_unit = sum(
        leg.qty * leg.entry_price for i, leg in enumerate(legs) if i not in abstained_idx
    )

    active_legs = [(i, leg) for i, leg in enumerate(legs) if i not in abstained_idx]

    if abstained_idx:
        max_gain = None
        max_loss = None
        breakevens = ()
        states.append(
            NullState(
                code="INCOMPLETE_LEGS",
                scope="structure",
                reason="bounds/breakevens withheld because one or more legs abstained",
                receipt={"abstained_legs": sorted(abstained_idx)},
            )
        )
    else:
        strikes = sorted({leg.strike for _, leg in active_legs})

        def pnl_at(S: float) -> float:
            total = 0.0
            for _, leg in active_legs:
                intrinsic = _intrinsic(leg.right, leg.strike, S)
                total += leg.qty * leg.multiplier * (intrinsic - leg.entry_price)
            return total

        eval_points = [0.0] + strikes
        values_at_points = [pnl_at(S) for S in eval_points]

        # Tail slope as S -> inf: puts are flat above the top strike (intrinsic -> 0),
        # so only CALL legs contribute. Domain is [0, inf), so the downside is always
        # finite at S=0 (a put's intrinsic there is the finite value K) — the only tail
        # that can be unbounded is S -> inf, governed entirely by slope_high.
        slope_high = sum(leg.qty * leg.multiplier for _, leg in active_legs if leg.right == "C")

        if slope_high > _TOL:
            max_gain = UNBOUNDED
        else:
            max_gain = max(values_at_points)

        if slope_high < -_TOL:
            max_loss = UNBOUNDED
        else:
            max_loss = min(values_at_points)

        breakeven_list: list[float] = []
        for idx in range(len(eval_points)):
            lo = eval_points[idx]
            lo_val = values_at_points[idx]
            if idx + 1 < len(eval_points):
                hi = eval_points[idx + 1]
                hi_val = values_at_points[idx + 1]
                if hi == lo:
                    continue
                slope = (hi_val - lo_val) / (hi - lo)
                if abs(slope) > _TOL and (lo_val <= 0 <= hi_val or hi_val <= 0 <= lo_val):
                    root = lo - lo_val / slope
                    if lo - 1e-9 <= root <= hi + 1e-9:
                        breakeven_list.append(root)
            else:
                if abs(slope_high) > _TOL:
                    root = lo - lo_val / slope_high
                    if root >= lo - 1e-9:
                        breakeven_list.append(root)

        dedup: list[float] = []
        for b in sorted(breakeven_list):
            if not dedup or abs(b - dedup[-1]) > 1e-6:
                dedup.append(b)
        breakevens = tuple(dedup)
        if not breakevens:
            states.append(
                NullState(
                    code="NO_BREAKEVEN",
                    scope="structure",
                    reason="pnl(S) never crosses zero",
                    receipt={"eval_points": eval_points, "values": values_at_points},
                )
            )

    return PayoffCurve(
        spots=spots,
        pnl=tuple(pnl_list),
        pnl_per_unit=tuple(pnl_per_unit),
        cost=cost,
        cost_per_unit=cost_per_unit,
        max_gain=max_gain,
        max_loss=max_loss,
        breakevens=breakevens,
        assumptions=assumption_block(structure, r=DEFAULT_R, q=DEFAULT_Q),
        states=_dedup_sorted_states(states),
    )


# ── 5.4 scenario grid ────────────────────────────────────────────────────────────────
def scenario_grid(
    structure: Structure,
    *,
    base_spot: float,
    spot_shocks: Sequence[float],
    vol_shocks: Sequence[float],
    days_forward: int,
    evaluation_date: str,
    r: float = DEFAULT_R,
    q: float = DEFAULT_Q,
) -> ScenarioGrid:
    """spot_shocks are MULTIPLICATIVE: S = base_spot*(1+shock). vol_shocks are ADDITIVE
    in decimal vol: sigma = iv + shock, floored at 1e-4. Mixing these two conventions
    silently is the classic bug — do not."""
    if not isinstance(days_forward, int) or isinstance(days_forward, bool) or days_forward < 0:
        raise ValueError("days_forward must be a non-negative int")
    spot_shocks = tuple(float(s) for s in spot_shocks)
    vol_shocks = tuple(float(v) for v in vol_shocks)
    if len(spot_shocks) == 0 or len(vol_shocks) == 0:
        raise ValueError("spot_shocks and vol_shocks must be non-empty")

    legs = structure.legs
    states: list[NullState] = list(structure.states)

    missing_mult_idx = {i for i, leg in enumerate(legs) if leg.multiplier is None}
    if missing_mult_idx:
        states.append(
            NullState(
                code="MULTIPLIER_UNKNOWN",
                scope="structure",
                reason="one or more legs have no multiplier",
                receipt={"legs_missing_multiplier": sorted(missing_mult_idx)},
            )
        )

    eval_d = _parse_date(evaluation_date)

    leg_T: list[float] = []
    leg_expiry_passed_at_horizon: list[bool] = []
    for leg in legs:
        exp_d = _parse_date(leg.expiration)
        days_remaining = (exp_d - eval_d).days - days_forward
        T = max(days_remaining, 0) / DAYS_PER_YEAR
        leg_T.append(T)
        leg_expiry_passed_at_horizon.append(days_remaining <= 0)

    cost = None
    if not any(leg.entry_price is None for leg in legs) and not missing_mult_idx:
        cost = sum(leg.qty * leg.multiplier * leg.entry_price for leg in legs)
    elif not missing_mult_idx and any(leg.entry_price is None for leg in legs):
        cost = None

    n_vol = len(vol_shocks)
    n_spot = len(spot_shocks)
    pnl_grid: list[list[float | None]] = []
    value_grid: list[list[float | None]] = []
    cell_states_grid: list[list[tuple[str, ...]]] = []

    for vi, vshock in enumerate(vol_shocks):
        pnl_row: list[float | None] = []
        value_row: list[float | None] = []
        state_row: list[tuple[str, ...]] = []
        for si, sshock in enumerate(spot_shocks):
            S = base_spot * (1.0 + sshock)
            cell_codes: list[str] = []

            leg_missing_iv = [i for i, leg in enumerate(legs) if leg.iv is None]
            if leg_missing_iv:
                cell_codes.append("LEG_IV_MISSING")
                value_row.append(None)
                pnl_row.append(None)
                state_row.append(tuple(sorted(set(cell_codes))))
                continue

            if any(leg_expiry_passed_at_horizon):
                cell_codes.append("EXPIRY_PASSED_AT_HORIZON")

            value = 0.0
            for i, leg in enumerate(legs):
                if leg.multiplier is None:
                    continue
                T = leg_T[i]
                sigma = max(leg.iv + vshock, 1e-4)
                is_call = leg.right == "C"
                if T <= 0:
                    price = _intrinsic(leg.right, leg.strike, S)
                else:
                    price = float(bs_price(S, leg.strike, T, sigma, is_call, r, q))
                value += leg.qty * leg.multiplier * price

            if missing_mult_idx:
                value_row.append(None)
                pnl_row.append(None)
            else:
                value_row.append(value)
                pnl_row.append(value - cost if cost is not None else None)
            state_row.append(tuple(sorted(set(cell_codes))))
        pnl_grid.append(pnl_row)
        value_grid.append(value_row)
        cell_states_grid.append(state_row)

    return ScenarioGrid(
        spot_shocks=spot_shocks,
        vol_shocks=vol_shocks,
        days_forward=days_forward,
        base_spot=float(base_spot),
        pnl=tuple(tuple(row) for row in pnl_grid),
        value=tuple(tuple(row) for row in value_grid),
        cell_states=tuple(tuple(row) for row in cell_states_grid),
        assumptions=assumption_block(structure, r=r, q=q),
        states=_dedup_sorted_states(states),
    )


# ── 5.5 greeks drift ─────────────────────────────────────────────────────────────────
def _leg_greeks_at(
    leg: Leg, S: float, T: float, r: float, q: float
) -> LegGreeks:
    if leg.iv is None:
        return LegGreeks(
            delta=None,
            gamma=None,
            vanna=None,
            charm_per_day=None,
            vega=None,
            theta_per_day=None,
            states=("LEG_IV_MISSING",),
        )

    is_call = leg.right == "C"
    delta, gamma, vanna, charm = bs_greeks(S, leg.strike, T, leg.iv, is_call, r, q)

    states: list[str] = []

    def _clean(v: float) -> float | None:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            if "MODEL_INPUT_ABSENT" not in states:
                states.append("MODEL_INPUT_ABSENT")
            return None
        return v

    delta_c = _clean(delta)
    gamma_c = _clean(gamma)
    vanna_c = _clean(vanna)
    charm_c = _clean(charm)
    charm_per_day = None if charm_c is None else charm_c / DAYS_PER_YEAR

    vega_raw = bs_vega(S, leg.strike, T, leg.iv, r, q)
    vega_c = _clean(float(vega_raw))

    if T > 0:
        dt = 0.5 / DAYS_PER_YEAR
        T_back = T + dt
        T_fwd = max(T - dt, 1e-9)
        price_back = float(bs_price(S, leg.strike, T_back, leg.iv, is_call, r, q))
        price_fwd = float(bs_price(S, leg.strike, T_fwd, leg.iv, is_call, r, q))
        theta_per_day = price_fwd - price_back
        if math.isnan(theta_per_day):
            theta_per_day = None
            if "MODEL_INPUT_ABSENT" not in states:
                states.append("MODEL_INPUT_ABSENT")
    else:
        theta_per_day = None
        if "MODEL_INPUT_ABSENT" not in states:
            states.append("MODEL_INPUT_ABSENT")

    return LegGreeks(
        delta=delta_c,
        gamma=gamma_c,
        vanna=vanna_c,
        charm_per_day=charm_per_day,
        vega=vega_c,
        theta_per_day=theta_per_day,
        states=tuple(states),
    )


def greeks_drift(
    structure: Structure,
    *,
    base_spot: float,
    days_forward: Sequence[int],
    evaluation_date: str,
    r: float = DEFAULT_R,
    q: float = DEFAULT_Q,
) -> GreeksDrift:
    legs = structure.legs
    eval_d = _parse_date(evaluation_date)
    struct_states: list[NullState] = list(structure.states)

    points: list[GreeksDriftPoint] = []
    for d in days_forward:
        t_years: list[float] = []
        per_leg: list[LegGreeks] = []
        for leg in legs:
            exp_d = _parse_date(leg.expiration)
            days_remaining = (exp_d - eval_d).days - d
            T = max(days_remaining, 0) / DAYS_PER_YEAR
            t_years.append(T)
            lg = _leg_greeks_at(leg, base_spot, T, r, q)
            per_leg.append(lg)

        point_states: list[str] = []
        for lg in per_leg:
            point_states.extend(lg.states)

        missing_mult = any(leg.multiplier is None for leg in legs)
        missing_iv = any(leg.iv is None for leg in legs)

        if missing_mult or missing_iv:
            net = LegGreeks(
                delta=None, gamma=None, vanna=None, charm_per_day=None,
                vega=None, theta_per_day=None,
                states=tuple(sorted(set(point_states + (["MULTIPLIER_UNKNOWN"] if missing_mult else [])))),
            )
        else:
            net_delta = _net_greek_field(per_leg, legs, "delta")
            net_gamma = _net_greek_field(per_leg, legs, "gamma")
            net_vanna = _net_greek_field(per_leg, legs, "vanna")
            net_charm = _net_greek_field(per_leg, legs, "charm_per_day")
            net_vega = _net_greek_field(per_leg, legs, "vega")
            net_theta = _net_greek_field(per_leg, legs, "theta_per_day")
            net = LegGreeks(
                delta=net_delta,
                gamma=net_gamma,
                vanna=net_vanna,
                charm_per_day=net_charm,
                vega=net_vega,
                theta_per_day=net_theta,
                states=tuple(sorted(set(point_states))),
            )

        points.append(
            GreeksDriftPoint(
                days_forward=d,
                t_years=tuple(t_years),
                per_leg=tuple(per_leg),
                net=net,
                states=tuple(sorted(set(point_states))),
            )
        )

    return GreeksDrift(
        base_spot=float(base_spot),
        points=tuple(points),
        assumptions=assumption_block(structure, r=r, q=q),
        states=_dedup_sorted_states(struct_states),
    )


# ── 5.6 summary, assumptions, evidence ───────────────────────────────────────────────
def assumption_block(structure: Structure, *, r: float, q: float) -> AssumptionBlock:
    any_iv = any(leg.iv is not None for leg in structure.legs)
    iv_source = "thetadata_chain.implied_vol" if any_iv else "MISSING"
    return AssumptionBlock(
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        greeks_source=GREEKS_SOURCE,
        price_source=PRICE_SOURCE,
        r=r,
        q=q,
        rate_source=RATE_SOURCE_LABEL,
        dividend_source=DIVIDEND_SOURCE_LABEL,
        iv_source=iv_source,
        asof_date=structure.asof_date,
        asof_grain="eod_session",
        day_count="ACT/365",
        multipliers=tuple(leg.multiplier for leg in structure.legs),
        sigma_convention="decimal (0.15 not 15) per engine/greeks.py:7-8",
        oi_timing_note="chain() returns raw point-in-time OI, unshifted (thetadata_store.py:555-556)",
    )


def structure_summary(
    structure: Structure,
    *,
    base_spot: float,
    evaluation_date: str,
    r: float = DEFAULT_R,
    q: float = DEFAULT_Q,
) -> StructureSummary:
    states: list[NullState] = list(structure.states)
    legs = structure.legs
    eval_d = _parse_date(evaluation_date)

    # horizon
    horizon_days: int | None = None
    horizon_expiry: str | None = None
    future_expiries: list[tuple[int, str]] = []
    any_past = False
    for leg in legs:
        exp_d = _parse_date(leg.expiration)
        delta_days = (exp_d - eval_d).days
        if delta_days <= 0:
            any_past = True
        else:
            future_expiries.append((delta_days, leg.expiration))
    if any_past:
        states.append(
            NullState(
                code="EXPIRY_PASSED",
                scope="structure",
                reason="one or more legs have an expiration on/before evaluation_date",
                receipt={"evaluation_date": evaluation_date},
            )
        )
    if future_expiries:
        future_expiries.sort(key=lambda t: t[0])
        horizon_days, horizon_expiry = future_expiries[0]

    # staleness
    asof_d = _parse_date(structure.asof_date) if structure.asof_date else eval_d
    stale_days = (eval_d - asof_d).days
    if stale_days > DEFAULT_MAX_STALE_SESSIONS:
        states.append(
            NullState(
                code="CHAIN_STALE",
                scope="structure",
                reason="asof_date is more than DEFAULT_MAX_STALE_SESSIONS behind evaluation_date",
                receipt={
                    "asof_date": structure.asof_date,
                    "evaluation_date": evaluation_date,
                    "grain": "eod_session",
                    "stale_days": stale_days,
                },
            )
        )

    # liquidity
    any_crossed = any(any(s.code == "QUOTE_CROSSED" for s in leg.states) for leg in legs)
    any_zero_bid = any(any(s.code == "ZERO_BID_LIQUIDITY" for s in leg.states) for leg in legs)
    any_oi_unknown = any(
        (leg.quote is None or leg.quote.open_interest is None) for leg in legs
    )
    any_thin = any(
        (leg.quote is not None and leg.quote.open_interest is not None and leg.quote.open_interest < 10)
        or any(s.code == "WIDE_SPREAD" for s in leg.states)
        for leg in legs
    )
    if any_crossed:
        liquidity = "LIQUIDITY_CROSSED"
    elif any_zero_bid:
        liquidity = "LIQUIDITY_ZERO_BID"
    elif any_oi_unknown:
        liquidity = "LIQUIDITY_UNKNOWN"
        states.append(
            NullState(
                code="OPEN_INTEREST_MISSING",
                scope="structure",
                reason="one or more legs have no open_interest reading",
                receipt={
                    "legs_missing_oi": [
                        i for i, leg in enumerate(legs)
                        if leg.quote is None or leg.quote.open_interest is None
                    ]
                },
            )
        )
    elif any_thin:
        liquidity = "LIQUIDITY_THIN"
    else:
        liquidity = "LIQUIDITY_OK"

    # prerequisites
    failing_codes: set[str] = set()
    for leg in legs:
        for s in leg.states:
            if s.code in (
                "QUOTE_MISSING", "QUOTE_CROSSED", "ZERO_BID_LIQUIDITY",
                "LEG_IV_MISSING", "MULTIPLIER_UNKNOWN", "IDENTITY_MISMATCH",
                "LEG_NOT_IN_CHAIN",
            ):
                failing_codes.add(s.code)
    for s in states:
        if s.code in ("CHAIN_EMPTY", "CHAIN_STALE", "EXPIRY_PASSED", "UNSUPPORTED_STRATEGY"):
            failing_codes.add(s.code)
    root_mismatch = any(any(s.code == "IDENTITY_MISMATCH" for s in leg.states) for leg in legs)
    if root_mismatch:
        failing_codes.add("IDENTITY_MISMATCH")

    prerequisites_met = len(failing_codes) == 0

    all_states = _dedup_sorted_states(states)
    if not prerequisites_met and not all_states:
        # Guard against the forbidden false-completeness shape: a False with
        # empty states. Should be unreachable given failing_codes non-empty,
        # but keep it explicit and defensive.
        all_states = _dedup_sorted_states(
            [
                NullState(
                    code=code,
                    scope="structure",
                    reason="prerequisite failure",
                    receipt={"code": code},
                )
                for code in sorted(failing_codes)
            ]
        )

    curve = None
    max_gain: float | str | None = None
    max_loss: float | str | None = None
    breakevens: tuple[float, ...] = ()
    cost: float | None = None
    if legs:
        curve = expiry_payoff(structure, [base_spot])
        cost = curve.cost
        max_gain = curve.max_gain
        max_loss = curve.max_loss
        breakevens = curve.breakevens

    return StructureSummary(
        structure=structure,
        cost=cost,
        max_gain=max_gain,
        max_loss=max_loss,
        breakevens=breakevens,
        horizon_days=horizon_days,
        horizon_expiry=horizon_expiry,
        liquidity=liquidity,
        prerequisites_met=prerequisites_met,
        states=all_states,
        assumptions=assumption_block(structure, r=r, q=q),
    )


def evidence_recipe(
    structure: Structure,
    *,
    r: float,
    q: float,
    spot_shocks: Sequence[float] = (),
    vol_shocks: Sequence[float] = (),
    days_forward: Sequence[int] = (),
) -> dict[str, object]:
    ab = assumption_block(structure, r=r, q=q)

    leg_tuples = sorted(
        (
            leg.right,
            leg.strike,
            leg.expiration,
            leg.qty,
            leg.entry_price,
            leg.multiplier,
            leg.iv,
        )
        for leg in structure.legs
    )
    inputs_payload = {
        "root": structure.root,
        "legs": leg_tuples,
        "asof_date": structure.asof_date,
        "r": r,
        "q": q,
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "spot_shocks": list(spot_shocks),
        "vol_shocks": list(vol_shocks),
        "days_forward": list(days_forward),
    }
    inputs_hash = sha256(canonical_json_bytes(inputs_payload)).hexdigest()

    recipe: dict[str, object] = {
        "recipe_name": "options_payoff.structure_scenario.v1",
        "model": {
            "name": MODEL_NAME,
            "version": MODEL_VERSION,
            "greeks_source": GREEKS_SOURCE,
            "price_source": PRICE_SOURCE,
        },
        "required_blocks": [
            "thetadata_eod_chain.quote",
            "structure.legs",
            "structure.multipliers",
        ],
        "optional_blocks": [
            "thetadata_eod_chain.implied_vol",
            "thetadata_eod_chain.open_interest",
            "thetadata_eod_chain.underlying_price",
        ],
        "owner_readers": [
            "engine/thetadata_store.py::chain",
            "engine/greeks.py::bs_greeks",
            "engine/intraday_greeks.py::bs_price",
        ],
        "identity_joins": ["root", "expiration", "strike", "right"],
        "clocks": {
            "asof_date": structure.asof_date,
            "asof_grain": "eod_session",
            "day_count": "ACT/365",
            "oi_timing": "chain() returns raw point-in-time OI, unshifted (thetadata_store.py:555-556)",
        },
        "refusal_rules": sorted(NULL_STATES),
        "dedup_rules": [
            "legs deduplicated on (right, strike, expiration); duplicate specs are summed into one qty"
        ],
        "output_field_map": {
            "cost": "PayoffCurve.cost / StructureSummary.cost",
            "max_gain": "PayoffCurve.max_gain / StructureSummary.max_gain",
            "max_loss": "PayoffCurve.max_loss / StructureSummary.max_loss",
            "breakevens": "PayoffCurve.breakevens / StructureSummary.breakevens",
            "horizon_days": "StructureSummary.horizon_days",
            "liquidity": "StructureSummary.liquidity",
            "prerequisites_met": "StructureSummary.prerequisites_met",
        },
        "assumptions": asdict(ab),
        "inputs_hash": inputs_hash,
        "authority": {
            "source_rights": "research_expression_only",
            "entry_authority": "none",
            "ranking_authority": "none",
            "sizing_authority": "none",
            "llm_origination": "none",
        },
    }
    recipe["recipe_id"] = compute_recipe_id(recipe)
    return recipe
