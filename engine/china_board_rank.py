"""China Prophet v4 board scoring, INTELLIGENCE ORDERING, and lane admission.

The module deliberately separates three decisions which the old board conflated:

* ``prophet_score`` orders names using a small, frozen set of features.
* execution checks decide whether a scored name may be *featured now*.
* lifecycle lanes preserve every raw gate-eligible name instead of silently dropping it.

V4 (operator commission 2026-08-15, "Handoff B — intelligence-ranked, entry-gated")
adds a FOURTH separation on top of the v3 machinery, and changes nothing else:

    RANK BY INTERESTINGNESS · GATE BY ENTRY.

Every v3 admission rule is preserved byte for byte — the prime-entry-window shelf,
confirmed-late and relay-late demotions, freshness, fillability, liquidity floor,
extension, sector/board caps and the four lossless lanes.  What changes is the ORDER
in which names are considered and displayed inside each lane: primarily the measured
``intel_interest_score`` (:mod:`engine.china_intel_interest`), then the unchanged v3
``prophet_score``, then ticker.  Because the featured caps bind in that order, the
interest score decides who takes the last shelf slot — an uninteresting name can no
longer ride a pretty entry oscillator to the top, and an interesting name still cannot
be featured without clearing every execution safeguard.

The v4 score itself is v3's score: :data:`SCORE_WEIGHTS` is untouched, and no
intelligence term enters ``prophet_score``.  This module remains the SOLE live ranking
authority: China Intelligence produces evidence, ``china_board_rank`` decides what that
evidence does to the board.  The interest composite is board-independent by
construction (no board direction, no board label edge, no board-absent bonus, no board
term in the leading-vs-lagging gap, and no Prophet score or rank anywhere in its
inputs), so ranking by it closes no feedback loop.

A bake uses ONE ordering basis globally.  If every ranked name has a valid measured
interest score — including a measured ``0.0`` — the board orders by intelligence
interest.  If even one ranked name lacks valid Intelligence evidence (missing,
unavailable, or malformed), the entire board reverts to v3 ``score_rank`` order.
Individual Intelligence observations stay on the row; only their authority over this
bake's order is disabled.  Mixed-scale ranking (interest for covered names, v3 score
for uncovered names, compared in the same slot) is forbidden.

The displaced v3 ORDERING keeps grading as a labeled shadow via
:func:`v3_shadow_featured` under :data:`V3_SHADOW_DEFINITION`, exactly as the displaced
v2 admission rule does under :data:`V2_SHADOW_DEFINITION`.  Historical v3 rows are
untouched; v4 accrues prospectively.

The score is a transparent priority heuristic, not a calibrated return forecast.  Only
the six components in :data:`SCORE_WEIGHTS` have score authority.  Residual alpha,
the legacy setup score, sector-turn context, fundamental quality, low volatility,
microstructure, liquidity, and risk sizing never add score.  Microstructure and
liquidity are used solely as execution/admission safeguards.

V3 (operator-ratified 2026-08-04, masterplan
``research/CHINA_PROPHET_LOSER_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`` §5 R1-R3)
changes exactly three things and nothing else:

R1 — the featured shelf is re-founded on the PRIME ENTRY WINDOW.  §2.3/§2.11
     measured the entry gauge inverting in the CN mean-reversion tape: the patience
     statuses were the era's best cohort (bounce_wait 6.9% loser rate, wait_pullback
     7.7%) while the action statuses were the worst (buy_soon 46.7%, partial 41.4%,
     buy_now 30.0%).  :data:`_ENTRY_VALUE` is re-ordered to that measured order, and
     :data:`_FEATURED_ENTRY_STATUSES` admits the patience statuses while demoting
     CONFIRMED-LATE ``buy_now``/``partial`` (signal ticks > :data:`EARLY_TICKS_MAX`).
     Every other featured safeguard — fresh same-day signal, fresh microstructure,
     fillability, liquidity floor, not extended, sector/board caps — is unchanged.

R2 — theme/cycle context gains EXACTLY ONE bounded authority: the 15-point
     ``theme_timing`` component computed by :func:`_theme_timing_value`.  §2.10
     measured curated-basket membership at a 13.1% loser rate vs 36.2% for
     non-members, and the cycle engine's own early-turn state ("Trough+") at 3.6%.
     Nothing else about narrative or sector context may move the score: RAW HEAT
     LEVEL ALONE NEVER ADDS SCORE (a HOT member with no timing state scores the same
     0.6 as any other neutral member), and ``sector_turn`` keeps zero authority —
     see :data:`_ZERO_SCORE_AUTHORITY`.  ``narrative`` left that tuple because it
     now has this one bounded channel, not because it became free.

R3 — the chase guard is a RELAY-POSITION demotion, not a chase veto and not a
     theme-heat split.  The 12-month formalization (PR #4506, n=7,816 chase events)
     REFUTED both the blanket demote and the in-era §2.9 theme split: chase x HOT
     ran −2.04pp vs chase x no-theme −1.51pp — no separation, the n=5 in-era cell
     was noise.  What replicated (monotone, robust across halves, inside BOTH HOT
     and WARMING, steeper at H=21) is RELAY POSITION — how many OTHER members of
     the name's basket printed a limit-close in the trailing 3 sessions:
     early (<=1) −1.17pp / 46.0% win, mid (2-3) −2.61pp / 42.3%, late (>=4)
     −5.32pp / 36.0% (n=406).  So a chase-composite row sitting LATE in its
     theme's relay takes the ``relay_late`` featured shortfall and routes to
     ``more_actionable`` — an ordering-grade demotion, matching evidence the study
     itself calls "a ranking, not a de-escalation trigger".  Every other chase
     branch is display/ledger only so W0 can grade them all.  No name is ever
     deleted from the board, and nothing here is a buy trigger.

The displaced v2 admission rule keeps grading as a labeled shadow via
:func:`v2_shadow_featured` under :data:`V2_SHADOW_DEFINITION` (G0.8).  Tripwire
thresholds for that race live in :mod:`engine.cn_v3_tripwires`.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
import math
from typing import Any, Iterable, Mapping

from engine import signal_gate


BOARD_DEFINITION = "cn_prophet_v4"
# The displaced v2 admission rule keeps grading in parallel under this labeled
# definition (G0.8).  It is registered in ``china_standout_track.WATCH_DEFINITIONS``
# so it can never own the headline grade.
V2_SHADOW_DEFINITION = "cn_prophet_v2_shadow"
# V4: the displaced v3 ORDERING (v3 score rank, same admission rule) keeps grading the
# same way.  Reusing the existing standout-track shadow mechanism rather than inventing
# a second grader is deliberate — v2 is already preserved exactly like this.
V3_SHADOW_DEFINITION = "cn_prophet_v3_shadow"
FEATURED_CAP = 24
SECTOR_CAP = 4
ADV_FLOOR_YI = 0.5
NON_STOCK_SECTORS = frozenset(("Sector ETF", "Index"))

SCORE_WEIGHTS = {
    "signal": 30.0,
    "entry": 20.0,
    "runway": 15.0,
    "bottom_quality": 10.0,
    "reversal_member": 10.0,
    # R2: the ONLY score channel theme/cycle context has.  See _theme_timing_value.
    "theme_timing": 15.0,
}

# These values are frozen definition inputs, rather than fitted coefficients.
_SIGNAL_BASE = {"T2": 1.0, "T1": 0.9, "T3": 0.7}
# R1 — the MEASURED order (masterplan §2.3, V1 era, 407 matured episodes).  The
# patience statuses were the era's best cohort and the action statuses its worst;
# v2 had this ladder upside down.  Stats below are the era cohort's loser rate and
# median CSI300-relative excess; statuses with no printed §2.3 cohort keep an
# ordinal placement only and are marked as such.
_ENTRY_VALUE = {
    "bounce_wait": 1.0,       # §2.3: 6.9% loser rate, +6.3 median excess — era best
    "wait_pullback": 0.95,    # §2.3: 7.7% loser rate, +6.9 median excess
    "hold": 0.8,              # no §2.3 cohort printed — ordinal: patience, below the two measured leaders
    "buy_now": 0.7,           # §2.3: 30.0% loser rate — the confirmed-late window
    "partial": 0.6,           # §2.3: 41.4% loser rate
    "later": 0.5,             # no §2.3 cohort printed — ordinal
    "await": 0.45,            # no §2.3 cohort printed — ordinal
    "await_confluence": 0.45,  # no §2.3 cohort printed — ordinal
    "watch": 0.4,             # no §2.3 cohort printed — ordinal
    "buy_soon": 0.35,         # §2.3: 46.7% loser rate — era worst
    "extended": 0.3,          # already ran; kept rankable, never featured
    "topping": 0.0,
    "blocked": 0.0,
    "exit": 0.0,
    "avoid": 0.0,
}
# R1 — the prime-window featured set.  bounce_wait/wait_pullback/hold admit on the
# unchanged execution safeguards alone; buy_now/partial additionally need an EARLY
# signal (ticks <= EARLY_TICKS_MAX) or they take the ``confirmed_late`` shortfall.
_FEATURED_ENTRY_STATUSES = frozenset(
    ("bounce_wait", "wait_pullback", "hold", "buy_now", "partial")
)
_CONFIRMED_LATE_STATUSES = frozenset(("buy_now", "partial"))
EARLY_TICKS_MAX = 1
# The pre-R1 (v2) featured rule, kept only for the parallel shadow grading.
_V2_FEATURED_ENTRY_STATUSES = frozenset(("buy_now", "partial"))

# R2 — theme/cycle context has EXACTLY the bounded ``theme_timing`` authority in
# SCORE_WEIGHTS and nothing else.  ``narrative`` therefore leaves this tuple, but
# raw heat LEVEL alone still adds no score (see _theme_timing_value: a HOT member
# with no timing state scores the same neutral 0.6 as any other member), and
# ``sector_turn`` remains fully zero-authority.
_ZERO_SCORE_AUTHORITY = (
    "residual_alpha",
    "setup",
    "sector_turn",
    "quality",
    "low_vol",
    "risk_sizing",
)

# Public aliases for builders and contract emitters.  The underscored names stay
# the canonical in-module references.
ZERO_SCORE_AUTHORITY = _ZERO_SCORE_AUTHORITY
FEATURED_ENTRY_STATUSES = _FEATURED_ENTRY_STATUSES

# R2 — theme_timing states.  Phases are the ``china_sector_cycles`` forward-log
# vocabulary (Trough / Recovery / Expansion / Peak / Downturn).
_THEME_TIMING_NON_MEMBER = 0.25
_THEME_TIMING_MEMBER_NEUTRAL = 0.6
_EARLY_CYCLE_PHASES = frozenset(("Trough", "Recovery"))
_LATE_CYCLE_PHASES = frozenset(("Peak", "Downturn"))

# R3 — build-time-knowable chase composite (T+1 gap is grading-side and excluded).
# The composite itself is a COHORT LABEL, not a veto: PR #4506 measured a blanket
# chase demote as a mixed verdict (median worse, mean and win rate better — the
# cohort is right-tail heavy). Only relay POSITION earned an admission effect.
CHASE_TRAIL_21_MIN = 0.25
CHASE_RUN_5D_MIN = 0.15

# R3 — the replicated relay ladder (PR #4506, n=406 positioned chase events).
# ``count_3d`` counts DISTINCT OTHER members of the name's basket(s) that printed a
# limit-close in sessions [d-2, d]; the name itself is excluded from its own count.
RELAY_MID_MIN = 2
RELAY_LATE_MIN = 4
RELAY_POSITIONS = ("early", "mid", "late")


# V4 — the ordering contract.  A bake is coverage-atomic: either every ranked row
# has valid measured Intelligence interest and the board orders by
# :data:`INTEL_INTEREST_ORDER`, or the entire board reverts to v3 ``score_rank``.
# A measured interest of 0.0 is valid coverage and does not trigger fallback.
# Missing/unavailable/malformed evidence stamps ``intel_interest_basis="fallback_v3"``
# and, if any ranked row has that stamp, disables intelligence authority for the
# bake.  The observations themselves stay on the row for diagnostics.
INTEL_BASIS_MEASURED = "measured"
INTEL_BASIS_FALLBACK = "fallback_v3"
#: Requested v4 ordering.  Used as ``effective_order_basis`` only when coverage
#: is complete.  Never mixed with a per-row v3-score substitute.
INTEL_INTEREST_ORDER = "intel_interest_then_v3_score"
#: Effective ordering when Intelligence coverage is incomplete.  Same token as
#: the unchanged v3 score basis — the board definition stays ``cn_prophet_v4``.
V3_SCORE_ORDER = "cn_prophet_v3_score"
ORDER_MODE_INTELLIGENCE = "intelligence_complete"
ORDER_MODE_V3_FALLBACK = "v3_coverage_fallback"
FALLBACK_REASON_INCOMPLETE_COVERAGE = "incomplete_intel_interest_coverage"


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


def _theme_state(row: Mapping[str, Any]) -> tuple[str | None, str | None, bool, bool]:
    """Return ``(narrative_level, basket_phase, osc_up, has_cycle)`` for one row.

    Both inputs are optional and may be ``None``; a malformed payload reads as
    absent rather than raising.  Levels and phases are case-normalised so a
    producer's capitalisation can never silently change a score.
    """
    narrative = row.get("narrative")
    narrative = narrative if isinstance(narrative, Mapping) else None
    cycle = row.get("basket_cycle")
    # An EMPTY mapping is not a cycle record. Treating ``{}`` as "present" would
    # let a degraded producer manufacture theme membership out of nothing.
    cycle = cycle if isinstance(cycle, Mapping) and cycle else None

    level = str((narrative or {}).get("level") or "").strip().upper() or None
    phase = str((cycle or {}).get("phase") or "").strip().title() or None
    osc_up = bool((cycle or {}).get("osc_up")) if cycle is not None else False
    return level, phase, osc_up, cycle is not None


def _is_theme_member(row: Mapping[str, Any]) -> bool:
    """Theme membership: a qualifying narrative theme OR a joined basket cycle.

    Both halves require CONTENT, not just a present key: a narrative tag with no
    theme is a radar-only join (see china_narrative_tags.name_tags), and an empty
    ``basket_cycle`` mapping is a degraded producer, not a membership.
    """
    narrative = row.get("narrative")
    if isinstance(narrative, Mapping) and narrative.get("theme"):
        return True
    cycle = row.get("basket_cycle")
    return isinstance(cycle, Mapping) and bool(cycle)


def _theme_timing_value(row: Mapping[str, Any]) -> float:
    """R2 — the ONE bounded score channel theme/cycle context has (0 / .25 / .6 / 1).

    Measured basis (masterplan §2.10, PIT join onto the 407 matured V1 episodes):
    curated-basket membership ran a 13.1% loser rate vs 36.2% for non-members;
    "Trough+" (Trough phase with the oscillator turning up) ran 3.6% and Recovery+
    0%, while "Downturn−" ran 50%.  §2.2 measured narrative WARMING at a 16% loser
    rate vs HOT at 42% — theme *timing*, not theme *level*, is the predictive axis.

    Ladder, evaluated in this order (the 1.0 test precedes the 0.0 test, as
    specified in the ratified slate):

    * ``1.0``  member AND (narrative WARMING OR an early basket cycle turning up)
    * ``0.0``  member AND (Downturn with the oscillator down OR HOT into a
               late-cycle basket with the oscillator down)
    * ``0.6``  any other member — INCLUDING a HOT member with no timing state, so
               raw heat level alone never buys score
    * ``0.25`` non-member

    Deterministic and null-tolerant: a member whose states are all missing takes
    the neutral 0.6, and only a genuine non-member takes 0.25.
    """
    if not _is_theme_member(row):
        return _THEME_TIMING_NON_MEMBER

    level, phase, osc_up, has_cycle = _theme_state(row)

    early_cycle_turning_up = has_cycle and phase in _EARLY_CYCLE_PHASES and osc_up
    if level == "WARMING" or early_cycle_turning_up:
        return 1.0

    fading_basket = has_cycle and phase == "Downturn" and not osc_up
    hot_into_late_cycle = (
        level == "HOT" and has_cycle and phase in _LATE_CYCLE_PHASES and not osc_up
    )
    if fading_basket or hot_into_late_cycle:
        return 0.0

    return _THEME_TIMING_MEMBER_NEUTRAL


def _chase_composite(row: Mapping[str, Any]) -> bool:
    """R3 — the build-time-knowable chase composite (masterplan §2.6/§2.9).

    Fires on an admission-day limit-close, a trailing-21d run at or above
    :data:`CHASE_TRAIL_21_MIN`, or a 5-session run at or above
    :data:`CHASE_RUN_5D_MIN`.  Missing inputs never manufacture a fire.
    """
    chase = row.get("chase")
    if not isinstance(chase, Mapping):
        return False
    if chase.get("limit_close_day") is True:
        return True
    trail_21 = _finite_float(chase.get("trail_21"))
    if trail_21 is not None and trail_21 >= CHASE_TRAIL_21_MIN:
        return True
    run_5d = _finite_float(chase.get("run_5d"))
    return run_5d is not None and run_5d >= CHASE_RUN_5D_MIN


def relay_position(count_3d: Any) -> str | None:
    """Map a trailing-3-session relay count to its position bucket.

    ``None`` means "not positionable" — the name belongs to no basket, so there is
    no relay to be early or late in.  That is a DIFFERENT state from a count of
    zero (a basket member whose peers printed nothing), which is ``"early"``.

    Buckets are PR #4506's measured ladder: early <= 1, mid 2-3, late >= 4.
    """
    count = _finite_float(count_3d)
    if count is None:
        return None
    if count >= RELAY_LATE_MIN:
        return "late"
    if count >= RELAY_MID_MIN:
        return "mid"
    return "early"


def relay_state(count_3d: Any) -> dict[str, Any]:
    """Build the ``row["relay"]`` payload from a trailing-3-session relay count."""
    count = _finite_float(count_3d)
    return {
        "count_3d": int(count) if count is not None else None,
        "position": relay_position(count_3d),
    }


def _relay_position_of(row: Mapping[str, Any]) -> str | None:
    """Read a row's relay position, deriving it from ``count_3d`` when absent."""
    payload = row.get("relay")
    if not isinstance(payload, Mapping):
        return None
    position = payload.get("position")
    if position in RELAY_POSITIONS:
        return str(position)
    return relay_position(payload.get("count_3d"))


def _attach_intel(row: dict, record: Mapping[str, Any] | None) -> None:
    """Stamp one row's board-independent intelligence-interest evidence.

    A missing, malformed, or explicitly unavailable record all resolve the same way —
    ``fallback_v3`` with a ``None`` score — because none of them is a measurement.  The
    compact ``intel`` block is what the card and the ledger read; ``intel_interest_score``
    and ``intel_interest_basis`` are hoisted to the top level because they are the
    ordering key and must be greppable in a stored row without unpacking.
    """
    score: float | None = None
    basis = INTEL_BASIS_FALLBACK
    if isinstance(record, Mapping) and record.get("basis") == INTEL_BASIS_MEASURED:
        score = _finite_float(record.get("score"))
        if score is not None:
            score = max(0.0, min(100.0, score))
            basis = INTEL_BASIS_MEASURED
    row["intel_interest_score"] = round(score, 2) if score is not None else None
    row["intel_interest_basis"] = basis
    if isinstance(record, Mapping):
        row["intel"] = {
            "definition": record.get("definition"),
            "basis": basis,
            "score": row["intel_interest_score"],
            "drivers": list(record.get("drivers") or [])[:3],
            "signal_core": record.get("signal_core"),
            "signal_source": record.get("signal_source"),
            "edge_remaining": record.get("edge_remaining"),
            "gap": record.get("gap"),
            "unavailable_reason": record.get("unavailable_reason"),
        }
    else:
        row["intel"] = {
            "definition": None, "basis": basis, "score": None, "drivers": [],
            "unavailable_reason": "no_intel_record",
        }


def intel_order_key(row: Mapping[str, Any]) -> tuple[float, float, str]:
    """The v4 intelligence ordering key: interest first, v3 priority second, ticker third.

    Descending on both scores, so the tuple negates them.  Callers must only sort a
    bake with this key when :func:`intel_coverage_complete` is true.  The per-row
    v3-score substitute is retained as a defensive last resort so a single malformed
    row cannot crash the sort; it is not a licensed mixed-scale ranking mode.
    """
    prophet = _finite_float(row.get("prophet_score"))
    if prophet is None:
        prophet = _finite_float((row.get("prophet") or {}).get("score")) or 0.0
    interest = _finite_float(row.get("intel_interest_score"))
    primary = (
        interest
        if row.get("intel_interest_basis") == INTEL_BASIS_MEASURED and interest is not None
        else prophet
    )
    return (-float(primary), -float(prophet), str(row.get("ticker") or ""))


def intel_interest_is_measured(row: Mapping[str, Any]) -> bool:
    """True when the row carries valid measured Intelligence interest.

    A score of ``0.0`` is measured evidence.  Missing, unavailable, or malformed
    records are not — those stamp :data:`INTEL_BASIS_FALLBACK`.
    """
    if row.get("intel_interest_basis") != INTEL_BASIS_MEASURED:
        return False
    return _finite_float(row.get("intel_interest_score")) is not None


def intel_coverage_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Bake-level Intelligence coverage over already-enriched ranked rows.

    Denominator is the ranked stock set (non-stock sectors already dropped).
    ``complete`` is vacuously true on an empty board.
    """
    ranked = list(rows)
    n_rows = len(ranked)
    n_measured = sum(1 for row in ranked if intel_interest_is_measured(row))
    n_unavailable = n_rows - n_measured
    complete = n_unavailable == 0
    return {
        "n_rows": n_rows,
        "n_measured": n_measured,
        "n_unavailable": n_unavailable,
        "n_fallback_v3": n_unavailable,
        "measured_rate_pct": (
            round(100.0 * n_measured / n_rows, 1) if n_rows else 0.0
        ),
        "complete": complete,
        "intel_coverage_complete": complete,
    }


def intel_coverage_complete(rows: Iterable[Mapping[str, Any]]) -> bool:
    """True iff every ranked row has valid measured Intelligence interest."""
    return bool(intel_coverage_summary(rows)["complete"])


def order_provenance(
    rows: Iterable[Mapping[str, Any]] | None = None,
    *,
    coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Requested/effective ordering receipt for one v4 bake.

    Reads coverage from ``rows`` when ``coverage`` is omitted.  Empty input is
    complete coverage with intelligence ordering (nothing mixed).
    """
    summary = dict(coverage) if coverage is not None else intel_coverage_summary(
        rows or ()
    )
    complete = bool(summary.get("complete"))
    effective = INTEL_INTEREST_ORDER if complete else V3_SCORE_ORDER
    mode = ORDER_MODE_INTELLIGENCE if complete else ORDER_MODE_V3_FALLBACK
    reason = None if complete else FALLBACK_REASON_INCOMPLETE_COVERAGE
    return {
        "requested_order_basis": INTEL_INTEREST_ORDER,
        "effective_order_basis": effective,
        "order_mode": mode,
        "fallback_reason": reason,
        "intel_order_active": complete,
        "intel_coverage_complete": complete,
        "n_rows": int(summary.get("n_rows") or 0),
        "n_measured": int(summary.get("n_measured") or 0),
        "n_unavailable": int(summary.get("n_unavailable") or 0),
        "n_fallback_v3": int(summary.get("n_fallback_v3") or 0),
        "measured_rate_pct": float(summary.get("measured_rate_pct") or 0.0),
    }


def emit_intel_coverage_warning(provenance: Mapping[str, Any]) -> None:
    """Line-start warning when any ranked row lacks valid Intelligence interest.

    Does not warn on measured zeros.  Warns on unavailable rows, including the
    total-failure case of zero measured names.
    """
    n_rows = int(provenance.get("n_rows") or 0)
    n_measured = int(provenance.get("n_measured") or 0)
    n_unavailable = int(provenance.get("n_unavailable") or (n_rows - n_measured))
    if n_rows <= 0 or n_unavailable <= 0:
        return
    print(
        f"::warning title=cn-prophet-v4-intel-partial::Intelligence coverage "
        f"{n_measured}/{n_rows}; entire board reverted to v3 ordering for this bake",
        flush=True,
    )


def _stamp_order_provenance(rows: list[dict], provenance: Mapping[str, Any]) -> None:
    """Write bake-level requested/effective ordering onto every row."""
    requested = provenance["requested_order_basis"]
    effective = provenance["effective_order_basis"]
    mode = provenance["order_mode"]
    reason = provenance.get("fallback_reason")
    active = bool(provenance.get("intel_order_active"))
    complete = bool(provenance.get("intel_coverage_complete"))
    for row in rows:
        row["requested_order_basis"] = requested
        row["effective_order_basis"] = effective
        row["order_mode"] = mode
        row["intel_order_active"] = active
        row["intel_coverage_complete"] = complete
        if reason:
            row["fallback_reason"] = reason
        else:
            row.pop("fallback_reason", None)
        prophet = row.get("prophet")
        if isinstance(prophet, dict):
            prophet["requested_order_basis"] = requested
            prophet["effective_order_basis"] = effective
            prophet["order_mode"] = mode
            prophet["order_basis"] = effective
            if reason:
                prophet["fallback_reason"] = reason
            else:
                prophet.pop("fallback_reason", None)


def apply_v4_board_order(enriched: list[dict]) -> dict[str, Any]:
    """Assign ``board_rank`` atomically from Intelligence coverage.

    ``score_rank`` must already be set.  On complete coverage, sorts by
    :func:`intel_order_key`.  On incomplete coverage, copies ``score_rank``
    onto ``board_rank`` so the live board orders exactly as v3.  Intelligence
    observations on the rows are not discarded.
    """
    coverage = intel_coverage_summary(enriched)
    provenance = order_provenance(coverage=coverage)
    if coverage["complete"]:
        enriched.sort(key=intel_order_key)
        for rank, row in enumerate(enriched, start=1):
            row["board_rank"] = rank
    else:
        for row in enriched:
            row["board_rank"] = row["score_rank"]
        enriched.sort(
            key=lambda row: (
                int(row["board_rank"]),
                str(row.get("ticker") or ""),
            )
        )
    _stamp_order_provenance(enriched, provenance)
    emit_intel_coverage_warning(provenance)
    return provenance


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
    narrative_by: Mapping[str, Mapping[str, Any]] | None = None,
    basket_cycle_by: Mapping[str, Mapping[str, Any]] | None = None,
    chase_by: Mapping[str, Mapping[str, Any]] | None = None,
    relay_by: Mapping[str, Mapping[str, Any]] | None = None,
    intel_by: Mapping[str, Mapping[str, Any]] | None = None,
    micro_asof: Any = None,
    board_asof: Any = None,
) -> list[dict]:
    """Copy, enrich, and score every candidate row.

    The maps are optional to keep the function useful with already-enriched rows.
    If a map explicitly contains a ticker, that value is authoritative (even when it
    is ``None``); otherwise the corresponding value already attached to the row is used.
    The returned order is score-descending with ticker as the deterministic tiebreak.

    ``narrative_by`` and ``basket_cycle_by`` feed the R2 ``theme_timing`` component
    and must therefore be attached BEFORE scoring — unlike v2, where narrative was
    a post-hoc display column with an order-invariance assertion behind it.
    ``chase_by`` and ``relay_by`` feed the R3 relay-position demotion.  Both are
    admission/display inputs only and add no score; ``chase_by`` alone has no
    admission effect at all (PR #4506 refuted the blanket demote) — it is kept on
    the row so the W0 telemetry engine can grade every chase branch.

    ``intel_by`` carries the V4 board-independent interest records from
    :mod:`engine.china_intel_interest`.  It adds NO score — ``prophet_score`` is
    computed identically with or without it — and feeds only ``board_rank``, the v4
    display/admission ORDER, and only when every ranked row has valid measured
    interest.  Omitting it, or leaving even one ranked row without measured
    interest, makes ``board_rank`` equal to ``score_rank`` and the board order
    exactly v3's.
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
        narrative = _mapped(narrative_by, ticker, row.get("narrative"))
        basket_cycle = _mapped(basket_cycle_by, ticker, row.get("basket_cycle"))
        chase = _mapped(chase_by, ticker, row.get("chase"))
        relay = _mapped(relay_by, ticker, row.get("relay"))
        rev_z = _mapped(rev_z_by, ticker, row.get("rev_z"))

        # The slim verdict prevents the raw analyzer payload from bloating the board
        # JSON. A bounded private receipt preserves research fields for the PIT
        # shadow ledger and is stripped by partition_board_rows.
        row["_signal_research"] = {
            key: deepcopy(verdict.get(key))
            for key in (
                "eligible", "tier_cascade", "tier_sub", "sub", "reason",
                # `reasons` is the EXHAUSTIVE companion of `reason` (signal_gate._set_reason):
                # same label at [0], plus every other leg that refused the name. Research-only,
                # never a gate input — it exists so the PIT store records why a name was
                # blocked rather than which leg happened to fire first.
                "reasons",
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
        # R2/R3 inputs. Attached before scoring so ``theme_timing`` is computed on
        # the same point-in-time payload the card and the ledger later show.
        if narrative is not None:
            row["narrative"] = deepcopy(dict(narrative))
        if basket_cycle is not None:
            row["basket_cycle"] = deepcopy(dict(basket_cycle))
        if chase is not None:
            row["chase"] = deepcopy(dict(chase))
        if relay is not None:
            row["relay"] = deepcopy(dict(relay))
        row["rev_z"] = _finite_float(rev_z)
        # V4 — board-independent intelligence interest.  Attached before scoring so the
        # ordering key, the card and the ledger all read one point-in-time record.
        _attach_intel(row, (intel_by or {}).get(ticker))
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
        theme_timing_value = _theme_timing_value(row)

        values = {
            "signal": signal_value,
            "entry": entry_value,
            "runway": runway_value,
            "bottom_quality": bottom_value,
            "reversal_member": reversal_value,
            "theme_timing": theme_timing_value,
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
            # V4: the SCORE is v3's, unchanged.  ``order_basis`` is overwritten
            # below with the bake's effective ordering (intelligence or v3
            # coverage fallback).  The requested basis is always intelligence.
            "score_basis": V3_SCORE_ORDER,
            "requested_order_basis": INTEL_INTEREST_ORDER,
            "effective_order_basis": INTEL_INTEREST_ORDER,
            "order_basis": INTEL_INTEREST_ORDER,
            "order_mode": ORDER_MODE_INTELLIGENCE,
        }
        row["board_definition"] = BOARD_DEFINITION

    # ``score_rank`` stays the v3 SCORE order — the displaced-v3 shadow, the ledger and
    # every historical consumer read it, and it must not silently start meaning
    # something else.  ``board_rank`` is the v4 DISPLAY/ADMISSION order, assigned
    # atomically: intelligence when coverage is complete, otherwise equal to
    # ``score_rank``.
    enriched.sort(key=lambda row: (-float(row["prophet_score"]), str(row.get("ticker") or "")))
    for rank, row in enumerate(enriched, start=1):
        row["score_rank"] = rank
    apply_v4_board_order(enriched)
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
    """Known execution blockers.  Unknown/stale context is not treated as a veto.

    R3 deliberately adds NOTHING here: PR #4506 refuted the blanket chase demote,
    so no chase branch is an execution veto.  The one surviving chase effect is the
    ordering-grade ``relay_late`` featured shortfall below.
    """
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


def _featured_shortfalls(
    row: Mapping[str, Any],
    *,
    entry_statuses: frozenset[str] = _FEATURED_ENTRY_STATUSES,
    early_ticks_required: bool = True,
    relay_late_guard: bool = True,
) -> list[str]:
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
    if status not in entry_statuses:
        reasons.append(f"entry_status_{status or 'unknown'}")
    elif early_ticks_required and status in _CONFIRMED_LATE_STATUSES:
        # R1 — the confirmed-late demotion. §2.11: "window open" fires AFTER the
        # bounce has matured, which is the measured loser cohort. An unknown tick
        # count is not evidence of lateness and passes, matching the same field's
        # incumbent reading in signal_gate.gate() ("ticks is None" => fresh) and in
        # _signal_value above (only ticks == 2 is penalised).
        ticks = _finite_float((row.get("signal") or {}).get("ticks"))
        if ticks is not None and ticks > EARLY_TICKS_MAX:
            reasons.append("confirmed_late")

    # R3 — the ONE admission effect chase evidence earned. A chase-composite row
    # sitting LATE in its theme's limit-up relay (>= RELAY_LATE_MIN peers printing
    # inside 3 sessions) demotes to more_actionable: PR #4506 measured that cohort
    # at −5.32pp / 36.0% win vs −1.17pp / 46.0% for early. It is not an execution
    # veto and it never routes to late_or_unfillable — the evidence is
    # ordering-grade, so the demotion is too.
    if relay_late_guard and _chase_composite(row) and _relay_position_of(row) == "late":
        reasons.append("relay_late")

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


def _partition(
    scored_rows: Iterable[Mapping[str, Any]],
    *,
    featured_cap: int,
    sector_cap: int,
    definition: str,
    entry_statuses: frozenset[str],
    early_ticks_required: bool,
    relay_late_guard: bool,
    rank_field: str = "board_rank",
) -> dict[str, Any]:
    """Shared lane machinery for the live v4 rule and both shadow rules.

    ``rank_field`` selects the ORDER — ``board_rank`` (v4: intelligence when coverage
    is complete, otherwise equal to ``score_rank``) or ``score_rank`` (v3: score only).
    It governs both the iteration order, so the featured/sector caps bind on that
    priority, and the per-lane display order.  A row missing the field sorts last
    rather than raising, so a partially-enriched pool degrades to "unranked at the
    bottom" instead of darkening the board.
    """
    rows = [deepcopy(dict(row)) for row in scored_rows]

    def _rank_of(row: Mapping[str, Any]) -> int:
        rank = _finite_float(row.get(rank_field))
        return int(rank) if rank is not None else 10**9

    rows.sort(
        key=lambda row: (
            _rank_of(row),
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

        shortfalls = _featured_shortfalls(
            row,
            entry_statuses=entry_statuses,
            early_ticks_required=early_ticks_required,
            relay_late_guard=relay_late_guard,
        )
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
                    "prime_entry_window",
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
        lane_rows.sort(key=lambda row: (_rank_of(row), str(row.get("ticker") or "")))
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
            row["board_definition"] = definition

    return {
        "board_definition": definition,
        "featured_cap": max(0, int(featured_cap)),
        "sector_cap": max(0, int(sector_cap)),
        **lanes,
        "counts": {name: len(lane_rows) for name, lane_rows in lanes.items()},
        "eligible": len(rows),
    }


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
    ``more_actionable`` unless they pass every featured-now safeguard — including
    the R1 prime-window entry rule and the R3 ``relay_late`` demotion — and fit
    both display caps.

    V4: the admission RULES above are v3's, unchanged.  Only the ORDER is new — rows
    are considered in ``board_rank`` order, so the featured and sector caps admit the
    most interesting qualifying names when Intelligence coverage is complete, and
    the same names the v3 shadow would admit when it is not.
    """
    return _partition(
        scored_rows,
        featured_cap=featured_cap,
        sector_cap=sector_cap,
        definition=BOARD_DEFINITION,
        entry_statuses=_FEATURED_ENTRY_STATUSES,
        early_ticks_required=True,
        relay_late_guard=True,
        rank_field="board_rank",
    )


def v3_shadow_featured(
    scored_rows: Iterable[Mapping[str, Any]],
    *,
    featured_cap: int = FEATURED_CAP,
    sector_cap: int = SECTOR_CAP,
) -> list[dict]:
    """The DISPLACED v3 ORDERING, stamped :data:`V3_SHADOW_DEFINITION`.

    v3 ranked by ``prophet_score`` alone; v4 ranks by measured intelligence interest
    first.  Running the two on the SAME scored rows, with the SAME admission rule and
    the SAME caps, isolates the ordering change — the only thing v4 altered — so the
    v4-vs-v3 race accrues from merge day with v4 live, exactly as the v2 shadow does
    for the v3 admission change.

    Display-free measurement output: these rows log to the shared board store under
    their own definition, which ``china_standout_track.WATCH_DEFINITIONS`` excludes
    from headline-grade resolution.
    """
    lanes = _partition(
        scored_rows,
        featured_cap=featured_cap,
        sector_cap=sector_cap,
        definition=V3_SHADOW_DEFINITION,
        entry_statuses=_FEATURED_ENTRY_STATUSES,
        early_ticks_required=True,
        relay_late_guard=True,
        rank_field="score_rank",
    )
    return lanes["featured"]


def v2_shadow_featured(
    scored_rows: Iterable[Mapping[str, Any]],
    *,
    featured_cap: int = FEATURED_CAP,
    sector_cap: int = SECTOR_CAP,
) -> list[dict]:
    """The DISPLACED v2 featured shelf, stamped :data:`V2_SHADOW_DEFINITION` (G0.8).

    The v2 rule was ``entry_status in {buy_now, partial}`` with no confirmed-late
    demotion and no relay-late demotion; every other safeguard is shared with the
    live rule.  Running it on the SAME scored rows isolates the admission rule — the
    §2.3 defect under test — from the score weights, so the race the operator would
    otherwise have waited weeks for runs from merge day with v3 live.

    These rows are display-free measurement output: they log to the shared board
    store under their own definition, which ``china_standout_track.WATCH_DEFINITIONS``
    excludes from headline-grade resolution.

    Ordering stays ``score_rank`` under v4: this shadow exists to isolate the v2-vs-v3
    ADMISSION rule, and re-ordering it by intelligence interest would confound that
    race with the separate v4 ordering change.
    """
    lanes = _partition(
        scored_rows,
        featured_cap=featured_cap,
        sector_cap=sector_cap,
        definition=V2_SHADOW_DEFINITION,
        entry_statuses=_V2_FEATURED_ENTRY_STATUSES,
        early_ticks_required=False,
        relay_late_guard=False,
        rank_field="score_rank",
    )
    return lanes["featured"]


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
    narrative_by: Mapping[str, Mapping[str, Any]] | None = None,
    basket_cycle_by: Mapping[str, Mapping[str, Any]] | None = None,
    chase_by: Mapping[str, Mapping[str, Any]] | None = None,
    relay_by: Mapping[str, Mapping[str, Any]] | None = None,
    intel_by: Mapping[str, Mapping[str, Any]] | None = None,
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
        narrative_by=narrative_by,
        basket_cycle_by=basket_cycle_by,
        chase_by=chase_by,
        relay_by=relay_by,
        intel_by=intel_by,
        micro_asof=micro_asof,
        board_asof=board_asof,
    )
    return partition_board_rows(scored, featured_cap=featured_cap, sector_cap=sector_cap)
