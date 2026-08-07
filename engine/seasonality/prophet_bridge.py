"""Post-selection seasonality overlays for an ALREADY-FROZEN Prophet plan list.

This module is the first honest caller of ``contracts.build_prophet_overlay``.
It exists to attach human-facing seasonality context to Prophet trade plans
*without* touching the plans themselves.

ARCHITECTURE — a separate bounded artifact, never a plan migration
------------------------------------------------------------------
The overlay is its own object keyed to the immutable ``plan_id``.  The
``prophet.trade_plan/v1`` schema is NOT migrated and no unregistered field is
appended to a plan.  A consumer that wants the context joins the overlay set to
the plan list on ``plan_id``.  The plan stays byte-identical, which is the
invariant that matters: seasonality can never be blamed for a number a plan
carries, because it never had write access to one.

Consequences that are enforced here, not merely intended:

* :func:`build_overlays_for_plans` receives an already-frozen candidate list.
  It cannot add, remove, or reorder a plan — it never writes to the sequence it
  is given, and its return value contains no plan objects at all.  Exactly two
  plan-derived values leave this module: the ``plan_id`` string and the
  normalised ``plan_asof`` date the overlay's own arithmetic was measured at.
  No price, level, target, size, thesis, or geometry ever leaves.
* The returned overlays carry no rank, no score, no size, no confidence, and no
  geometry.  ``build_prophet_overlay`` stamps an authority block whose six
  write-capability keys are all ``False``, and
  :data:`FORBIDDEN_OVERLAY_FIELDS` is re-checked on the finished object so a
  later edit cannot smuggle a rank or a size past the schema validator (which
  accepts unknown keys).

WHAT ``ATTEND`` MEANS — a human-facing UI attention marker ONLY
--------------------------------------------------------------
``ATTEND`` is a marker for a person reading a page.  It MUST NOT change a
machine queue, a candidate prompt, plan ordering, plan management, an alert
route, a retraining set, a feature store, or any future plan decision.  It is
not a score, not a tie-break, and not an input to anything that selects,
ranks, or sizes.  A consumer that reads ``ATTEND`` and changes a machine
decision has violated the contract this module exists to keep.

WHY ``CAP_CONFIDENCE`` IS UNREACHABLE
-------------------------------------
``prophet.seasonality_overlay/v1`` admits four actions; this bridge emits only
three.  ``DNR:KILL-CALENDAR-GATED-RISK`` forbids a calendar or event-proximity
construction from capping confidence or moving a risk state — that is a
laundered pre-event conviction dampener, and event windows are display context
only.  So the decision function's codomain is
:data:`ALLOWED_ACTIONS` = {NONE, NARRATE, ATTEND}, and every action passes
:func:`assert_action_allowed` both on decision and immediately before
emission.  Anything that ever tries to emit ``CAP_CONFIDENCE`` raises
:class:`~engine.seasonality.contracts.ContractError` instead of shipping.

ABSENCE IS NOT A DEFAULT
------------------------
A missing, expired, contract-invalid, abstaining, or unjoinable state yields NO
overlay — never a default overlay and never a neutral score.  This extends to a
missing *field* on an otherwise-valid state: ``clock.occurrence_end_date`` is
not required by ``validate_neuralweb_state``, and reading its absence as "the
window does not close inside the plan horizon" would ship a display-tier claim
about a date nobody knows.  So an unreadable occurrence end skips the plan.  The
same holds plan-side for an unreadable horizon or an unreadable
``source_engines`` — a gate that cannot be measured is never scored as passed
or failed.  Every such case produces a structured ``skipped`` entry naming the
reason (drawn from the closed set :data:`SKIP_REASONS`), so silence is auditable
rather than merely quiet.

POINT-IN-TIME — ONE MOMENT PER PLAN, NOT ONE PER BATCH
------------------------------------------------------
Two moments are in play: the run ``asof`` (when the overlay set is built) and
each plan's own ``asof`` (when that plan was frozen).  A batch-level screen
alone is not PIT discipline: a state that first existed *after* a plan was
frozen must not colour that plan, even if it exists by the time the batch runs.
So availability is screened TWICE — once against the run ``asof`` (nothing from
the future of the run), then again per plan against that plan's own ``asof``
(nothing from the future of the plan).  Symmetrically, a plan stamped after the
run ``asof`` is skipped rather than joined, because resolving its identity would
ask the point-in-time plane a question about the future.

A plan ``asof`` is normalised to a UTC calendar date once, and that single value
anchors the horizon window, the availability comparison, and the plan's identity
key — so an offset-bearing timestamp and a bare date for the same instant can
never resolve to two different identities or two different windows.

The identity join itself is two-sided: the plan resolves at the plan's asof, the
state at the STATE's own asof, and the two identities must be equal.  A rename
still joins (a reviewed plane returns one permanent identity at both dates); a
ticker that was reused for a different company does not.

DETERMINISM
-----------
``asof`` is an explicit argument; this module reads no wall clock and draws no
sample.  Identical inputs produce an identical output object.
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence

from .contracts import (
    NEURALWEB_STATE_SCHEMA,
    PROPHET_OVERLAY_SCHEMA,
    ContractError,
    build_prophet_overlay,
    validate_neuralweb_state,
    validate_prophet_overlay,
)

OVERLAY_SET_SCHEMA = "seasonality.prophet_overlay_set.v1"
BRIDGE_VERSION = "seasonality.prophet_bridge/v1"

ACTION_NONE = "NONE"
ACTION_NARRATE = "NARRATE"
ACTION_ATTEND = "ATTEND"

#: The complete codomain of :func:`decide_action`.  ``CAP_CONFIDENCE`` is
#: deliberately absent — see the module docstring.
ALLOWED_ACTIONS = frozenset({ACTION_NONE, ACTION_NARRATE, ACTION_ATTEND})
#: Actions this bridge refuses to emit under any input (DNR:KILL-CALENDAR-GATED-RISK).
FORBIDDEN_ACTIONS = frozenset({"CAP_CONFIDENCE"})

# --- horizon comparison constants -------------------------------------------
# MEASURED, not assumed: despite its name, `forecast.horizon_td` is emitted in
# CALENDAR days by the only producer of `neuralweb.biopharma_seasonality_state.v1`
# in this repo — `engine/seasonality/state.py` computes it as
# `max(1, (end_date - asof_date).days)`, a difference of two `datetime.date`
# objects.  A plan's `horizon_days` is likewise calendar days.  So the two sides
# are already in the same unit and are compared raw.
#
# An earlier version of this module multiplied the plan side by 252/365 on the
# stated premise that the state side was in trading days.  That conversion did
# not remove a unit error, it INTRODUCED one: it shifted the band to
# `state/plan ∈ [0.345, 1.38]` in the producer's real units — asymmetric in log
# space, accepting a window half the plan's length while rejecting one 1.5x it.
# If a future producer ever emits a true trading-day horizon it must convert at
# the source, because the field is consumed here as calendar days.
#: A bounded-overlap band, not a calibrated statistic.  It answers "are these
#: two horizons the same order of magnitude", which is the only question a
#: display-tier context marker is entitled to ask.
HORIZON_MATCH_MIN_RATIO = 0.5
HORIZON_MATCH_MAX_RATIO = 2.0

#: Engines whose output already carries a calendar/seasonal term.  If a plan was
#: originated with one of these in `source_engines`, a seasonality overlay would
#: restate a factor the plan already contains, so the overlay says nothing.
SEASONALITY_BEARING_ENGINES = frozenset(
    {
        "biopharma_seasonality",
        "calendar_seasonality",
        "factor_seasonality",
        "seasonality",
        "seasonality_shadow",
        "stock_seasonality",
    }
)

# --- skip reason codes ------------------------------------------------------
SKIP_STATE_CONTRACT_INVALID = "state_contract_invalid"
SKIP_STATE_NOT_YET_AVAILABLE = "state_not_yet_available"
SKIP_STATE_EXPIRED = "state_expired"
SKIP_STATE_ABSTAINING = "state_abstaining"
SKIP_STATE_NOT_AVAILABLE_AT_PLAN_ASOF = "state_not_available_at_plan_asof"
SKIP_STATE_OCCURRENCE_END_UNREADABLE = "state_occurrence_end_unreadable"
SKIP_STATE_ASOF_UNREADABLE = "state_asof_unreadable"
SKIP_PLAN_MISSING_ID = "plan_missing_id"
SKIP_PLAN_DUPLICATE_ID = "plan_duplicate_id"
SKIP_PLAN_ASOF_UNREADABLE = "plan_asof_unreadable"
SKIP_PLAN_ASOF_AFTER_ASOF = "plan_asof_after_asof"
SKIP_PLAN_HORIZON_UNREADABLE = "plan_horizon_unreadable"
SKIP_PLAN_SOURCE_ENGINES_UNREADABLE = "plan_source_engines_unreadable"
SKIP_IDENTITY_UNRESOLVED = "identity_unresolved"
SKIP_NO_MATCHING_STATE = "no_matching_state"
SKIP_AMBIGUOUS_STATE_MATCH = "ambiguous_state_match"

#: The CLOSED set of skip reasons.  ``skipped[].reason`` is checked against it
#: before an entry is recorded, so a future literal-string skip fails loudly
#: instead of quietly widening the vocabulary a consumer has to understand.
#: (``detail`` stays free-form by design — it is prose for a human reader.)
SKIP_REASONS = frozenset(
    {
        SKIP_STATE_CONTRACT_INVALID,
        SKIP_STATE_NOT_YET_AVAILABLE,
        SKIP_STATE_EXPIRED,
        SKIP_STATE_ABSTAINING,
        SKIP_STATE_NOT_AVAILABLE_AT_PLAN_ASOF,
        SKIP_STATE_OCCURRENCE_END_UNREADABLE,
        SKIP_STATE_ASOF_UNREADABLE,
        SKIP_PLAN_MISSING_ID,
        SKIP_PLAN_DUPLICATE_ID,
        SKIP_PLAN_ASOF_UNREADABLE,
        SKIP_PLAN_ASOF_AFTER_ASOF,
        SKIP_PLAN_HORIZON_UNREADABLE,
        SKIP_PLAN_SOURCE_ENGINES_UNREADABLE,
        SKIP_IDENTITY_UNRESOLVED,
        SKIP_NO_MATCHING_STATE,
        SKIP_AMBIGUOUS_STATE_MATCH,
    }
)

# --- reason codes carried on an emitted overlay -----------------------------
REASON_HORIZON_MISMATCH = "horizon_mismatch"
REASON_ALREADY_IN_PLAN_FEATURES = "already_in_plan_features"
REASON_WINDOW_ENDS_INSIDE_PLAN_HORIZON = "window_ends_inside_plan_horizon"
REASON_CONTEXT_ONLY_OUTSIDE_HORIZON = "context_only_outside_horizon"

#: The CLOSED set of reason codes an emitted overlay may carry.
OVERLAY_REASON_CODES = frozenset(
    {
        REASON_HORIZON_MISMATCH,
        REASON_ALREADY_IN_PLAN_FEATURES,
        REASON_WINDOW_ENDS_INSIDE_PLAN_HORIZON,
        REASON_CONTEXT_ONLY_OUTSIDE_HORIZON,
    }
)

#: Keys that may NEVER appear on an emitted overlay.  ``validate_prophet_overlay``
#: builds its return value with ``dict(...)`` and does not reject unknown keys,
#: so passing it is not evidence that nothing authority-bearing rode along.  A
#: rank, a size, or a score stamped onto the overlay would hand a display-tier
#: object exactly the machine authority the authority block denies it.
FORBIDDEN_OVERLAY_FIELDS = frozenset(
    {
        "confidence",
        "conviction",
        "geometry",
        "gate",
        "priority",
        "rank",
        "score",
        "size",
        "size_multiplier",
        "weight",
    }
)

__all__ = [
    "ACTION_ATTEND",
    "ACTION_NARRATE",
    "ACTION_NONE",
    "ALLOWED_ACTIONS",
    "BRIDGE_VERSION",
    "FORBIDDEN_ACTIONS",
    "FORBIDDEN_OVERLAY_FIELDS",
    "OVERLAY_REASON_CODES",
    "OVERLAY_SET_SCHEMA",
    "REASON_ALREADY_IN_PLAN_FEATURES",
    "REASON_CONTEXT_ONLY_OUTSIDE_HORIZON",
    "REASON_HORIZON_MISMATCH",
    "REASON_WINDOW_ENDS_INSIDE_PLAN_HORIZON",
    "SKIP_AMBIGUOUS_STATE_MATCH",
    "SKIP_IDENTITY_UNRESOLVED",
    "SKIP_NO_MATCHING_STATE",
    "SKIP_PLAN_ASOF_AFTER_ASOF",
    "SKIP_PLAN_ASOF_UNREADABLE",
    "SKIP_PLAN_DUPLICATE_ID",
    "SKIP_PLAN_HORIZON_UNREADABLE",
    "SKIP_PLAN_MISSING_ID",
    "SKIP_PLAN_SOURCE_ENGINES_UNREADABLE",
    "SKIP_REASONS",
    "SKIP_STATE_ABSTAINING",
    "SKIP_STATE_ASOF_UNREADABLE",
    "SKIP_STATE_CONTRACT_INVALID",
    "SKIP_STATE_EXPIRED",
    "SKIP_STATE_NOT_AVAILABLE_AT_PLAN_ASOF",
    "SKIP_STATE_NOT_YET_AVAILABLE",
    "SKIP_STATE_OCCURRENCE_END_UNREADABLE",
    "assert_action_allowed",
    "build_overlays_for_plans",
    "decide_action",
    "event_inside_plan_horizon",
    "horizon_match",
    "no_identity",
    "overlap_with_existing_features",
]


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------


def no_identity(symbol: str, asof: str) -> None:
    """The DEFAULT identity resolver: resolves nothing.

    The reviewed point-in-time security-identity plane is blocked, and guessing
    an identity is how a ticker that was reused for a different company gets a
    context marker belonging to its predecessor.  So the default behaviour of
    this bridge is to produce NO overlays.  A caller that owns a reviewed PIT
    identity plane injects it via ``resolve_identity``.
    """
    return None


# ---------------------------------------------------------------------------
# small parsers (no wall clock anywhere in this module)
# ---------------------------------------------------------------------------


def _parse_moment(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    text = value.strip()
    if len(text) == 10:
        # A bare date is read as midnight UTC, explicitly — never as "local".
        # The try/except is not decoration: `2026-13-01` is ten characters and
        # `fromisoformat` raises a bare ValueError, which a caller catching this
        # module's documented failure mode (ContractError) would not catch.
        try:
            return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ContractError(f"{field} must be an ISO-8601 date") from exc
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _parse_date_or_none(value: Any) -> date | None:
    """Read a bare ``YYYY-MM-DD`` calendar date, or ``None``.

    Used only for ``clock.occurrence_end_date``, which ``state.py`` emits as a
    ``date.isoformat()`` with no time part and no offset.  Anything else — a
    missing key, a timestamp, or prose — returns ``None`` and the caller SKIPS
    the plan; ``None`` is never read as "the window does not close in time".
    A plan ``asof`` is deliberately NOT parsed here: it goes through
    :func:`_parse_moment` so it is normalised to UTC exactly once.
    """
    if not isinstance(value, str) or len(value.strip()) != 10:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _positive_int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


# ---------------------------------------------------------------------------
# plan view — read-only, shape-agnostic
# ---------------------------------------------------------------------------

_PLAN_FIELDS = ("id", "plan_id", "asof", "asset", "horizon_days", "source_engines")

#: Containers a ``source_engines`` value may legitimately arrive in.  A bare
#: string is handled separately (as a single engine name); anything else is
#: UNREADABLE, not empty — see :func:`_normalise_engines`.
_ENGINE_CONTAINERS = (list, tuple, set, frozenset)


def _normalise_engines(value: Any) -> list[str] | None:
    """Return the plan's declared engines, or ``None`` when they are unreadable.

    ``validate_trade_plan`` only asks that ``source_engines`` be non-empty, so a
    set or a bare string is a contract-valid plan.  Coercing an unrecognised
    container to ``[]`` would fail OPEN: the double-count suppression in
    :func:`overlap_with_existing_features` exists precisely to stop a
    seasonality-bearing plan getting a seasonality overlay, and an empty list
    silently answers "no overlap" for a plan whose provenance was never read.
    ``None`` means "not measured" and makes the caller skip the plan.
    """
    if isinstance(value, str):
        return [value] if value.strip() else None
    if isinstance(value, _ENGINE_CONTAINERS):
        return list(value)
    return None


def _plan_view(plan: Any) -> dict[str, Any]:
    """Return a detached read-only view of the plan fields we consult.

    Accepts a ``ProphetTradePlan`` dataclass instance or a mapping.  Nothing is
    written back: the plan object is never mutated and never re-emitted.
    """
    if isinstance(plan, Mapping):
        source: Mapping[str, Any] = plan
    elif dataclasses.is_dataclass(plan) and not isinstance(plan, type):
        source = dataclasses.asdict(plan)
    else:
        source = {name: getattr(plan, name, None) for name in _PLAN_FIELDS}
    view = {name: source.get(name) for name in _PLAN_FIELDS}
    if not view["id"]:
        view["id"] = view["plan_id"]
    view["source_engines"] = _normalise_engines(view["source_engines"])
    return view


def _state_ref(state: Any) -> str:
    """A stable, diagnosable reference for a state — valid or not."""
    if not isinstance(state, Mapping):
        return "state:<non-object>"
    entity = state.get("entity")
    entity_id = entity.get("id") if isinstance(entity, Mapping) else None
    provenance = state.get("provenance")
    snapshot = provenance.get("data_snapshot") if isinstance(provenance, Mapping) else None
    return "|".join(
        str(part) if part else "?"
        for part in (
            state.get("artifact_id"),
            entity_id,
            state.get("asof"),
            snapshot,
        )
    )


def _state_symbol(state: Mapping[str, Any]) -> str | None:
    entity = state.get("entity")
    if not isinstance(entity, Mapping):
        return None
    ticker = entity.get("ticker")
    if isinstance(ticker, str) and ticker.strip():
        return ticker.strip()
    identifier = entity.get("id")
    if isinstance(identifier, str) and identifier.strip():
        _, _, tail = identifier.partition(":")
        return (tail or identifier).strip() or None
    return None


# ---------------------------------------------------------------------------
# the three booleans
# ---------------------------------------------------------------------------


def horizon_match(plan_horizon_days: Any, state_horizon_td: Any) -> bool:
    """True when the plan horizon and the state's forecast horizon are comparable.

    RULE: require ``forecast.horizon_td / plan.horizon_days`` to land inside
    ``[0.5x, 2.0x]``.  Both sides are CALENDAR days — see the note on
    :data:`HORIZON_MATCH_MIN_RATIO` for the measurement behind that claim — so
    no unit conversion is applied and the band is symmetric in log space.
    Either horizon missing or non-positive is False: an unknown horizon is never
    a match.
    """
    plan_days = _positive_int_or_none(plan_horizon_days)
    state_td = _positive_int_or_none(state_horizon_td)
    if plan_days is None or state_td is None:
        return False
    ratio = state_td / plan_days
    return HORIZON_MATCH_MIN_RATIO <= ratio <= HORIZON_MATCH_MAX_RATIO


def event_inside_plan_horizon(
    plan_asof: date | None,
    plan_horizon_days: Any,
    occurrence_end: date | None,
) -> bool:
    """True when the seasonal window CLOSES inside the plan's own horizon.

    RULE: the state's ``clock.occurrence_end_date`` must fall in the closed
    interval ``[plan.asof, plan.asof + horizon_days]`` (calendar days on both
    sides — the plan horizon is a calendar horizon).  A missing plan asof,
    missing/non-positive horizon, or missing occurrence end is False: an unknown
    date never counts as inside.
    """
    plan_days = _positive_int_or_none(plan_horizon_days)
    if plan_asof is None or occurrence_end is None or plan_days is None:
        return False
    return plan_asof <= occurrence_end <= plan_asof + timedelta(days=plan_days)


def overlap_with_existing_features(source_engines: Sequence[Any]) -> bool:
    """True when the plan's own originating engines already carry a calendar term.

    RULE: normalise each ``source_engines`` entry (lowercase, trim, ``-``→``_``)
    and test membership in :data:`SEASONALITY_BEARING_ENGINES`.  Measured from
    the plan's declared provenance, never guessed from the thesis text.
    """
    for engine in source_engines or ():
        if not isinstance(engine, str):
            continue
        if engine.strip().lower().replace("-", "_") in SEASONALITY_BEARING_ENGINES:
            return True
    return False


# ---------------------------------------------------------------------------
# action decision + the CAP_CONFIDENCE guard
# ---------------------------------------------------------------------------


def assert_action_allowed(action: str) -> str:
    """Raise unless ``action`` is one this bridge is permitted to emit.

    ``CAP_CONFIDENCE`` is named explicitly so the refusal reads as a law, not as
    a typo check: ``DNR:KILL-CALENDAR-GATED-RISK`` forbids a calendar or
    event-proximity construction from capping confidence or moving a risk state.
    """
    if action in FORBIDDEN_ACTIONS:
        raise ContractError(
            f"seasonality overlay may never emit {action!r} — "
            "DNR:KILL-CALENDAR-GATED-RISK forbids calendar/event proximity "
            "capping confidence or changing a risk state"
        )
    if action not in ALLOWED_ACTIONS:
        raise ContractError(f"action {action!r} is not in {sorted(ALLOWED_ACTIONS)}")
    return action


def decide_action(
    *,
    matched_horizon: bool,
    event_inside: bool,
    overlaps: bool,
) -> tuple[str, list[str]]:
    """Map the three booleans to an action and its reason codes.

    The ladder, in order:

    1. horizons not comparable → ``NONE`` — a window on a different time scale
       has nothing to say about this plan;
    2. the plan already carries a calendar term → ``NONE`` — restating it would
       double-count a factor the plan owns;
    3. the window closes inside the plan horizon → ``ATTEND`` — a human-facing
       attention marker, and nothing else (see the module docstring);
    4. otherwise → ``NARRATE`` — background context a reader may want.

    ``CAP_CONFIDENCE`` is not reachable from any combination of the inputs.
    """
    if not matched_horizon:
        return ACTION_NONE, [REASON_HORIZON_MISMATCH]
    if overlaps:
        return ACTION_NONE, [REASON_ALREADY_IN_PLAN_FEATURES]
    if event_inside:
        return ACTION_ATTEND, [REASON_WINDOW_ENDS_INSIDE_PLAN_HORIZON]
    return ACTION_NARRATE, [REASON_CONTEXT_ONLY_OUTSIDE_HORIZON]


# ---------------------------------------------------------------------------
# state screening
# ---------------------------------------------------------------------------


def _screen_state(
    state: Any, asof_moment: datetime
) -> tuple[dict[str, Any] | None, datetime | None, str, str]:
    """Return ``(validated_state | None, available_at | None, reason, detail)``.

    Gates run in a fixed order and the FIRST failing gate names the reason, so
    the code is a claim about what was checked first, not about what else may
    also be wrong.  This is the RUN-level screen only; availability is screened
    a second time per plan, at that plan's own asof.
    """
    try:
        validated = validate_neuralweb_state(state)
    except ContractError as exc:
        return None, None, SKIP_STATE_CONTRACT_INVALID, str(exc)

    # `asof` is NOT validated by validate_neuralweb_state, and it is the date
    # this state's own identity is resolved at, so it is checked here.
    try:
        _parse_moment(validated.get("asof"), "state.asof")
    except ContractError as exc:
        return None, None, SKIP_STATE_ASOF_UNREADABLE, str(exc)

    available_at = _parse_moment(validated.get("available_at"), "available_at")
    if available_at > asof_moment:
        return (
            None,
            None,
            SKIP_STATE_NOT_YET_AVAILABLE,
            "state becomes available after asof; reading it would be look-ahead",
        )

    expires_at = _parse_moment(validated.get("expires_at"), "expires_at")
    if expires_at <= asof_moment:
        return None, None, SKIP_STATE_EXPIRED, "state expired at or before asof"

    uncertainty = validated.get("uncertainty") or {}
    if uncertainty.get("abstain") is not False:
        return None, None, SKIP_STATE_ABSTAINING, "state abstains; an abstention is not context"

    return validated, available_at, "", ""


def _skip_entry(
    *, kind: str, plan_id: str | None, state_ref: str | None, reason: str, detail: str
) -> dict[str, Any]:
    """Build one ``skipped`` entry, refusing any reason outside :data:`SKIP_REASONS`."""
    if reason not in SKIP_REASONS:
        raise ContractError(f"skip reason {reason!r} is not in {sorted(SKIP_REASONS)}")
    if not detail:
        raise ContractError(f"skip reason {reason!r} must carry a human-readable detail")
    return {
        "kind": kind,
        "plan_id": plan_id,
        "state_ref": state_ref,
        "reason": reason,
        "detail": detail,
    }


def _assert_overlay_carries_no_authority(overlay: Mapping[str, Any]) -> None:
    """Refuse an overlay that grew a rank/size/score field.

    ``validate_prophet_overlay`` accepts unknown keys, so schema validity is not
    evidence that nothing authority-bearing rode along on the object.
    """
    smuggled = sorted(FORBIDDEN_OVERLAY_FIELDS.intersection(overlay))
    if smuggled:
        raise ContractError(
            f"seasonality overlay may never carry {smuggled} — it is a display-tier "
            "attention marker with no rank, size, score, or gate authority"
        )
    reasons = overlay.get("reason_codes") or []
    unknown = sorted(set(reasons) - OVERLAY_REASON_CODES)
    if unknown:
        raise ContractError(f"overlay reason_codes {unknown} are not in OVERLAY_REASON_CODES")


# ---------------------------------------------------------------------------
# the public entry point
# ---------------------------------------------------------------------------


def build_overlays_for_plans(
    plans: Iterable[Any],
    states: Iterable[Any],
    *,
    asof: str,
    resolve_identity: Callable[[str, str], str | None] | None = None,
) -> dict[str, Any]:
    """Build seasonality overlays for an ALREADY-FROZEN Prophet plan list.

    :param plans: the frozen candidate list.  Read-only: never mutated, never
        reordered, and never re-emitted.  Each element may be a
        ``ProphetTradePlan`` dataclass instance or an equivalent mapping.
    :param states: candidate ``neuralweb.biopharma_seasonality_state.v1``
        payloads.  Only unexpired, contract-valid, non-abstaining, already-
        available states are read — available both at ``asof`` and at the asof
        of the plan they are joined to.
    :param asof: explicit point-in-time moment (``YYYY-MM-DD`` or a
        timezone-aware ISO-8601 timestamp).  No wall clock is read.
    :param resolve_identity: ``(symbol, asof) -> identity | None``.  ``asof`` is
        the plan's own asof, normalised to a ``YYYY-MM-DD`` UTC date.  Defaults
        to :func:`no_identity`, which resolves nothing, so the DEFAULT behaviour
        of this function is to emit no overlays at all.  It is called at most
        once per ``(symbol, plan asof)`` pair — a reviewed PIT plane is an IO
        lookup, not a dictionary.
    :returns: ``{"schema", "asof", "overlays", "skipped", "counts"}``.  Contains
        no plan objects — the only plan-derived values present are ``plan_id``
        and the normalised ``plan_asof``.
    """
    resolver = resolve_identity or no_identity
    asof_moment = _parse_moment(asof, "asof")

    plan_list = list(plans)
    state_list = list(states)

    overlays: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    identity_cache: dict[tuple[str, str], str | None] = {}

    def resolve_cached(symbol: str, plan_asof_key: str) -> str | None:
        key = (symbol, plan_asof_key)
        if key not in identity_cache:
            identity_cache[key] = resolver(symbol, plan_asof_key)
        return identity_cache[key]

    eligible: list[dict[str, Any]] = []
    for state in state_list:
        ref = _state_ref(state)
        validated, available_at, reason, detail = _screen_state(state, asof_moment)
        if validated is None:
            skipped.append(
                _skip_entry(
                    kind="state", plan_id=None, state_ref=ref, reason=reason, detail=detail
                )
            )
            continue
        eligible.append(
            {
                "state": validated,
                "ref": ref,
                "symbol": _state_symbol(validated),
                "available_at": available_at,
                # The date THIS state's identity is resolved at — its own asof,
                # not the plan's.  See the join comment below.
                "asof_key": _parse_moment(validated.get("asof"), "state.asof").date().isoformat(),
            }
        )

    seen_plan_ids: set[str] = set()

    for plan in plan_list:
        view = _plan_view(plan)
        plan_id = view["id"]
        if not isinstance(plan_id, str) or not plan_id.strip():
            skipped.append(
                _skip_entry(
                    kind="plan",
                    plan_id=None,
                    state_ref=None,
                    reason=SKIP_PLAN_MISSING_ID,
                    detail="an overlay is keyed to plan_id; a plan without one cannot be joined",
                )
            )
            continue

        # An overlay is keyed to plan_id, so a repeated plan_id would fan a
        # single overlay row out across N plans on any join a consumer writes.
        if plan_id in seen_plan_ids:
            skipped.append(
                _skip_entry(
                    kind="plan",
                    plan_id=plan_id,
                    state_ref=None,
                    reason=SKIP_PLAN_DUPLICATE_ID,
                    detail="plan_id already seen in this batch; an overlay key must be unique",
                )
            )
            continue
        seen_plan_ids.add(plan_id)

        plan_asof_raw = view["asof"] if isinstance(view["asof"], str) else ""
        asset = view["asset"]
        try:
            plan_moment = _parse_moment(plan_asof_raw, "plan.asof")
        except ContractError:
            plan_moment = None
        if plan_moment is None or not isinstance(asset, str) or not asset.strip():
            skipped.append(
                _skip_entry(
                    kind="plan",
                    plan_id=plan_id,
                    state_ref=None,
                    reason=SKIP_PLAN_ASOF_UNREADABLE,
                    detail="plan asof/asset could not be read; refusing to guess the join key",
                )
            )
            continue

        # One normalised value anchors the window, the availability comparison,
        # and the identity key, so a bare date and an offset-bearing timestamp
        # for the same instant can never disagree.
        plan_asof_date = plan_moment.date()
        plan_asof_key = plan_asof_date.isoformat()

        if plan_moment > asof_moment:
            skipped.append(
                _skip_entry(
                    kind="plan",
                    plan_id=plan_id,
                    state_ref=None,
                    reason=SKIP_PLAN_ASOF_AFTER_ASOF,
                    detail="plan asof is after the run asof; refusing to resolve an identity in the future",
                )
            )
            continue

        plan_horizon = _positive_int_or_none(view["horizon_days"])
        if plan_horizon is None:
            skipped.append(
                _skip_entry(
                    kind="plan",
                    plan_id=plan_id,
                    state_ref=None,
                    reason=SKIP_PLAN_HORIZON_UNREADABLE,
                    detail="plan horizon_days is absent or not a positive integer; "
                    "both overlay booleans are measured against it",
                )
            )
            continue

        plan_engines = view["source_engines"]
        if plan_engines is None:
            skipped.append(
                _skip_entry(
                    kind="plan",
                    plan_id=plan_id,
                    state_ref=None,
                    reason=SKIP_PLAN_SOURCE_ENGINES_UNREADABLE,
                    detail="plan source_engines could not be read; double-count suppression "
                    "cannot be measured, and an unmeasured gate is never scored as passed",
                )
            )
            continue

        # The join is on reviewed PIT identity, never on a ticker string.  Each
        # side is resolved AT ITS OWN ASOF — the plan at the date it was frozen,
        # the state at the date its data was measured — and the two identities
        # must then be equal.  Resolving both sides at the plan's asof would
        # look right and be wrong in the two cases that matter:
        #   * a RENAME (OLDCO -> NEWCO) still joins, because a reviewed plane
        #     returns the same permanent identity at both dates;
        #   * a REUSED ticker does NOT join, because the state was measured
        #     while that ticker meant the predecessor company, and a context
        #     marker belonging to the predecessor is exactly the zombie print
        #     this bridge refuses to make.
        plan_identity = resolve_cached(asset.strip(), plan_asof_key)
        if not plan_identity:
            skipped.append(
                _skip_entry(
                    kind="plan",
                    plan_id=plan_id,
                    state_ref=None,
                    reason=SKIP_IDENTITY_UNRESOLVED,
                    detail="no reviewed point-in-time identity for this plan; refusing to join on a ticker",
                )
            )
            continue

        identified = [
            candidate
            for candidate in eligible
            if candidate["symbol"]
            and resolve_cached(candidate["symbol"], candidate["asof_key"]) == plan_identity
        ]
        if not identified:
            skipped.append(
                _skip_entry(
                    kind="plan",
                    plan_id=plan_id,
                    state_ref=None,
                    reason=SKIP_NO_MATCHING_STATE,
                    detail="no eligible seasonality state resolves to this plan's reviewed identity",
                )
            )
            continue

        # SECOND availability screen, at the PLAN's asof: a state that first
        # existed after this plan was frozen is look-ahead relative to the plan
        # even though it is not look-ahead relative to the run.
        matches = [
            candidate for candidate in identified if candidate["available_at"] <= plan_moment
        ]
        if not matches:
            skipped.append(
                _skip_entry(
                    kind="plan",
                    plan_id=plan_id,
                    state_ref=identified[0]["ref"],
                    reason=SKIP_STATE_NOT_AVAILABLE_AT_PLAN_ASOF,
                    detail="the matching state became available after this plan's asof; "
                    "reading it would be look-ahead relative to the plan",
                )
            )
            continue
        if len(matches) > 1:
            skipped.append(
                _skip_entry(
                    kind="plan",
                    plan_id=plan_id,
                    state_ref=None,
                    reason=SKIP_AMBIGUOUS_STATE_MATCH,
                    detail=f"{len(matches)} eligible states share this identity; refusing to pick one",
                )
            )
            continue

        match = matches[0]
        state = match["state"]
        clock = state.get("clock") or {}
        forecast = state.get("forecast") or {}
        provenance = state.get("provenance") or {}

        # `clock.occurrence_end_date` is NOT required by validate_neuralweb_state,
        # so a producer key rename reaches here as `None`.  Reading that as
        # "the window does not close inside the plan horizon" would print a
        # display-tier claim about a date nobody has.
        occurrence_end = _parse_date_or_none(clock.get("occurrence_end_date"))
        if occurrence_end is None:
            skipped.append(
                _skip_entry(
                    kind="plan",
                    plan_id=plan_id,
                    state_ref=match["ref"],
                    reason=SKIP_STATE_OCCURRENCE_END_UNREADABLE,
                    detail="clock.occurrence_end_date is absent or unparseable; an unknown "
                    "window end is not the same claim as a window ending outside the horizon",
                )
            )
            continue

        matched_horizon = horizon_match(plan_horizon, forecast.get("horizon_td"))
        event_inside = event_inside_plan_horizon(plan_asof_date, plan_horizon, occurrence_end)
        overlaps = overlap_with_existing_features(plan_engines)

        action, reason_codes = decide_action(
            matched_horizon=matched_horizon,
            event_inside=event_inside,
            overlaps=overlaps,
        )
        assert_action_allowed(action)

        # Guarded once more at the emission point: whatever produced `action`,
        # nothing forbidden reaches build_prophet_overlay.
        overlay = build_prophet_overlay(
            plan_id=plan_id,
            seasonality_state_ref=match["ref"],
            horizon_match=matched_horizon,
            event_inside_plan_horizon=event_inside,
            overlap_with_existing_features=overlaps,
            action=assert_action_allowed(action),
            reason_codes=reason_codes,
            expires_at=str(state.get("expires_at")),
        )
        overlay = validate_prophet_overlay(
            {
                **overlay,
                "asof": asof,
                # The NORMALISED plan asof — the exact value the two booleans
                # above were measured at, not the raw string the caller passed.
                "plan_asof": plan_asof_key,
                "attention_only": True,
                "versions": {
                    "overlay_schema": PROPHET_OVERLAY_SCHEMA,
                    "overlay_set_schema": OVERLAY_SET_SCHEMA,
                    "bridge_version": BRIDGE_VERSION,
                    "state_schema": NEURALWEB_STATE_SCHEMA,
                    "state_artifact_id": state.get("artifact_id"),
                    "state_asof": state.get("asof"),
                    "state_model_version": provenance.get("model_version"),
                    "state_pattern_spec_hash": provenance.get("pattern_spec_hash"),
                    "state_data_snapshot": provenance.get("data_snapshot"),
                },
            }
        )
        _assert_overlay_carries_no_authority(overlay)
        overlays.append(overlay)

    by_action = {name: 0 for name in sorted(ALLOWED_ACTIONS)}
    for overlay in overlays:
        by_action[overlay["action"]] += 1
    by_skip_reason: dict[str, int] = {}
    for entry in skipped:
        by_skip_reason[entry["reason"]] = by_skip_reason.get(entry["reason"], 0) + 1

    return {
        "schema": OVERLAY_SET_SCHEMA,
        "asof": asof,
        "overlays": overlays,
        "skipped": skipped,
        "counts": {
            "plans_in": len(plan_list),
            "states_in": len(state_list),
            "states_eligible": len(eligible),
            "overlays": len(overlays),
            "skipped": len(skipped),
            "by_action": by_action,
            "by_skip_reason": dict(sorted(by_skip_reason.items())),
        },
    }
