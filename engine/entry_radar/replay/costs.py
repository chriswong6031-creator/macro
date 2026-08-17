"""Frozen §11 cost mechanics — the liquidity floor and the max(measured, floor) law.

Pure arithmetic over the prereg's frozen tier table.  Kept in its own module (not
inside the replay runner) so the battery-I tests can import the law WITHOUT
importing an orchestration script, and so exactly one implementation of "what
does a side cost" exists for the runner, the reconciler and the tests.

THE ONE LAW THIS FILE ENCODES (§11, verbatim):

    per-side cost = max(measured median half-spread at the signal timestamp
                        when lawful NBBO exists, liquidity floor)

and its two teeth:

  * **Missing NBBO is never zero cost.**  ``measured=None`` (unentitled feed, no
    quotes in the window, an invalid book) binds the FLOOR.  The tempting
    alternative — treat an unmeasurable spread as 0 and let the tape speak — is
    the single most flattering defect available to a cost model, because it
    fires exactly on the illiquid names whose real spreads are widest.
  * **A measured spread BELOW the floor still binds the floor.**  The floor is
    not a fallback for missing data; it is a liquidity-conditioned minimum that a
    lucky midpoint quote may not undercut.

Unknown ADV binds the WIDEST floor, never the cheapest: a name we cannot size is
treated as the least liquid tier, so a coverage gap costs the episode money
rather than buying it a discount (fail-closed, the same direction every other
refusal in this package points).

``outcomes.attach`` applies the ROUND TRIP (``fwd_ret - 2 * cost_bps / 1e4``);
this module only prices ONE side, and :func:`round_trip_fraction` exists so the
round-trip arithmetic has a single named form the tests can pin.
"""
from __future__ import annotations

import math

from engine.entry_radar.replay import prereg

#: Cost provenance words that ride every episode row (§11 "cost provenance").
COST_BASIS_MEASURED = "measured"
COST_BASIS_FLOOR = "floor"


def tier_floor_bps(adv_usd: float | None) -> float:
    """Liquidity floor in bps PER SIDE for a trailing-60-session median $-volume.

    Reads ``prereg.COST_TIER_FLOORS_BPS`` — ``((50e6, 5.0), (5e6, 15.0), (0.0,
    40.0))``, i.e. (ADV floor, bps/side) in DESCENDING ADV order — rather than
    restating the tiers, so a prereg amendment moves this function with it.

    ``None``, NaN, negative, or an ADV below every declared tier returns the
    widest declared floor.  There is no "no floor" answer.
    """
    tiers = tuple(prereg.COST_TIER_FLOORS_BPS)
    widest = max(float(bps) for _adv, bps in tiers)
    if adv_usd is None:
        return widest
    try:
        adv = float(adv_usd)
    except (TypeError, ValueError):
        return widest
    if not math.isfinite(adv) or adv < 0.0:
        return widest
    for adv_floor, bps in tiers:
        if adv >= float(adv_floor):
            return float(bps)
    return widest


def per_side_cost_bps(measured_bps: float | None,
                      adv_usd: float | None) -> tuple[float, str]:
    """``(cost_bps, basis)`` under the frozen ``max(measured, floor)`` law.

    ``basis`` is ``"measured"`` ONLY when a finite, non-negative measured
    half-spread strictly exceeds the tier floor — every other path (missing,
    NaN, negative, or below/equal to the floor) returns the floor and says so.
    Equality reports ``floor``: when the two coincide the binding constraint is
    the floor, and a row that claims ``measured`` at exactly the floor value
    would overstate how much NBBO evidence the episode actually carries.
    """
    floor = tier_floor_bps(adv_usd)
    if measured_bps is None:
        return floor, COST_BASIS_FLOOR
    try:
        measured = float(measured_bps)
    except (TypeError, ValueError):
        return floor, COST_BASIS_FLOOR
    if not math.isfinite(measured) or measured < 0.0:
        return floor, COST_BASIS_FLOOR
    if measured > floor:
        return measured, COST_BASIS_MEASURED
    return floor, COST_BASIS_FLOOR


def round_trip_fraction(cost_per_side_bps: float) -> float:
    """The round-trip cost as a RETURN fraction: ``2 * bps / 1e4``.

    The single named form of the arithmetic ``outcomes.attach`` performs inline
    (``fwd_ret_net = fwd_ret - 2.0 * cost / 1e4``); battery I pins the two
    against each other so they can never drift into two different cost models.
    """
    return 2.0 * float(cost_per_side_bps) / 1e4


__all__ = ["COST_BASIS_MEASURED", "COST_BASIS_FLOOR", "tier_floor_bps",
           "per_side_cost_bps", "round_trip_fraction"]
