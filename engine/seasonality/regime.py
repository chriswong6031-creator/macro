"""Lawful regime FEATURES for biopharma seasonality — axes kept apart, on purpose.

This module reads regime state.  It does not score it, rank it, or fuse it, and
the absence of a fusion function here is the deliberate product of three standing
kills rather than an oversight:

* ``DNR:KILL-REGIME-SCORECARD`` — a composite market-regime scorecard fusing
  gamma/vol/flow/breadth into a regime verdict is a FORBIDDEN fusion path.
* ``DNR:KILL-COMPOSITE-REGIME-RELIABILITY-MONITOR`` — the same claim on a wider
  input list is the same kill; widening the input list does not make it new.
* ``DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY`` — the family x regime INTERACTION
  measured 3.8x smaller than the family main effect, with era-split sign stability
  at 62% (a coin flip).  Reopening requires
  ``engine.regime_conditioning_coverage.assess()`` returning ``estimable`` for the
  target axis AND a fresh preregistration naming the interaction as primary.

**Renaming a composite does not make it lawful.**  There is no function in this
file that takes several regime axes and returns one number, and
``test_seasonality_model.py`` pins that at runtime rather than trusting this
paragraph: every public callable is invoked with a multi-axis input and asserted
to return a per-axis mapping, never a scalar.

POSITIONING AND FINANCING STAY DISPLAY/CONTEXT
----------------------------------------------
Short interest, dealer gamma, crowding, ATM shelves, and dilution pressure are
readable as CONTEXT and may never be model features.  Fusing positioning keys
into a regime score is Signal-Commons ILLEGAL, and the display/context ceiling is
carried on every axis payload as ``authority`` rather than left to a convention
a later caller can forget.

POINT-IN-TIME OR NOTHING
------------------------
Every field enters through a REVIEWED adapter (:data:`REVIEWED_PIT_ADAPTERS`)
that names where the value came from and when it was knowable.  A field with no
reviewed adapter, or one whose ``known_at`` is after the decision moment, is
REFUSED BY NAME.  A regime read that quietly uses a value stamped after the
decision produces a perfectly plausible conditional table that could never have
been acted on.

THE INTERACTION GATE
--------------------
An interaction between a market-response estimate and a regime axis is eligible
ONLY when all of these hold:

0. the axis is ON THE ALLOWLIST at all.  An axis nobody authorized has no
   authority to fall back on, so it is refused by name rather than treated as a
   conditionable default;
1. the coverage report is one :func:`engine.regime_conditioning_coverage.assess`
   actually produced — its gates block and its per-axis verdict fields must be
   present, because a hand-written ``{"status": "ok", "axes": {...}}`` is a
   caller's assertion wearing the meter's clothes;
2. that report returns ``estimable`` for THAT EXACT AXIS — not for a sibling
   axis, not for the report as a whole; and
3. a preregistration names that interaction as PRIMARY, and (when ``asof`` is
   supplied) was registered inside
   :data:`MAX_PREREGISTRATION_AGE_DAYS` of it.  Freshness is checkable only
   against a decision moment, so an eligibility call with no ``asof`` says
   ``preregistration_freshness="not_checked:no_asof_supplied"`` rather than
   claiming a check it did not run.

Otherwise the regime is shown as CONTEXT and the interaction estimate ABSTAINS
with a named reason.  Every path is tested.

The gate binds ELIGIBILITY, not the estimator's arithmetic, so the estimate an
eligible path returns is screened too: a payload carrying a composite-looking
scalar, or declaring more than one axis as its input, is REFUSED
(:class:`RegimeFeatureError`).  Otherwise the one lawful door in this module
would be a way to hand back exactly the fused regime score the kills forbid.

Shadow status is binding: every payload here carries ``tier="shadow"``.
Pure stdlib — the coverage meter (which needs pandas) is imported lazily, and the
primary entry point takes an already-computed coverage report so a thin runner
can call it.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Callable, Mapping

REGIME_SCHEMA = "biopharma.seasonality.regime_context.v1"
REGIME_ABSTENTION_SCHEMA = "biopharma.seasonality.regime_abstention.v1"
REGIME_VERSION = "seasonality-regime-context-v1"
TIER = "shadow"

#: The authority ceiling every regime payload carries.  A regime axis explains;
#: it never ranks, sizes, or gates.
DISPLAY_CONTEXT = "display_context"
MODEL_FEATURE = "model_feature"

#: The standing kills this module is shaped by.  Cited by KEY, never by row
#: number — registry rows shift on every append.
GOVERNING_KILLS = (
    "DNR:KILL-REGIME-SCORECARD",
    "DNR:KILL-COMPOSITE-REGIME-RELIABILITY-MONITOR",
    "DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY",
)


class RegimeFeatureError(Exception):
    """A regime field was offered that this module may not consume."""


# --------------------------------------------------------------------------- #
# the authorization tables
# --------------------------------------------------------------------------- #
#: Axes a market-response model may CONDITION on, by family.  An explicit
#: allowlist, not a pattern: a pattern admits tomorrow's field without review.
AUTHORIZED_AXES: dict[str, tuple[str, ...]] = {
    "market": ("regime_at_entry", "quad_hard_label", "risk_radar_state"),
    "biotech": ("xbi_trend_state", "biotech_breadth_state", "biotech_ipo_window_state"),
    "liquidity_rates": ("rate_pressure", "real_yield_state", "credit_spread_state"),
    "issuer": ("issuer_size_bucket", "issuer_listing_venue", "issuer_index_membership"),
    "volatility": ("vol_regime", "implied_vol_bucket", "realized_vol_bucket"),
}

#: Axes that may be SHOWN and never modelled.  Positioning and financing fusion
#: into a regime score is Signal-Commons ILLEGAL; these are here so a caller who
#: passes one gets a named display-only verdict instead of a silent drop.
DISPLAY_ONLY_AXES: dict[str, tuple[str, ...]] = {
    "positioning": ("short_interest_pct", "dealer_gamma_state", "crowding_state"),
    "financing": ("atm_shelf_state", "cash_runway_months", "dilution_pressure_state"),
}

#: Reviewed point-in-time adapters, axis -> adapter identity.  An axis absent
#: from this table has no reviewed provenance and is refused by name.
REVIEWED_PIT_ADAPTERS: dict[str, str] = {
    **{axis: f"pit.{family}.v1" for family, axes in AUTHORIZED_AXES.items() for axis in axes},
    **{axis: f"pit.{family}.v1" for family, axes in DISPLAY_ONLY_AXES.items() for axis in axes},
}

_FAMILY_BY_AXIS: dict[str, str] = {
    **{axis: family for family, axes in AUTHORIZED_AXES.items() for axis in axes},
    **{axis: family for family, axes in DISPLAY_ONLY_AXES.items() for axis in axes},
}

#: Named refusal reasons.
REFUSE_UNAUTHORIZED = "unauthorized_axis"
REFUSE_NO_ADAPTER = "no_reviewed_pit_adapter"
REFUSE_NOT_PIT = "value_not_knowable_at_asof"
REFUSE_MALFORMED = "malformed_axis_payload"

#: Named interaction abstentions.
ABSTAIN_AXIS_NOT_ESTIMABLE = "axis_not_estimable"
ABSTAIN_NO_PREREGISTRATION = "interaction_not_preregistered_as_primary"
ABSTAIN_AXIS_NOT_IN_REPORT = "axis_absent_from_coverage_report"
ABSTAIN_AXIS_DISPLAY_ONLY = "axis_is_display_context_only"
ABSTAIN_COVERAGE_UNAVAILABLE = "coverage_report_unavailable"
ABSTAIN_AXIS_UNAUTHORIZED = "axis_not_on_the_authorization_allowlist"
ABSTAIN_COVERAGE_NOT_FROM_METER = "coverage_report_not_from_the_house_meter"
ABSTAIN_PREREGISTRATION_STALE = "preregistration_stale_at_asof"
ABSTAIN_PREREGISTRATION_UNDATED = "preregistration_carries_no_registered_at"

#: How old a preregistration may be at the decision moment before it stops being
#: a hypothesis and becomes a habit.  Checked only when ``asof`` is supplied —
#: freshness has no meaning without a decision date to be fresh AT.
MAX_PREREGISTRATION_AGE_DAYS = 365

#: The fields :func:`engine.regime_conditioning_coverage.assess` stamps on every
#: report and on every per-axis verdict.  Required as PROVENANCE: a hand-written
#: ``{"status": "ok", "axes": {"x": {"estimable": True}}}`` is a caller asserting
#: the answer, and this gate exists precisely so the caller cannot.
COVERAGE_REPORT_MARKERS = ("axes", "status", "gates", "n_rows")
COVERAGE_GATE_MARKERS = ("min_coverage", "min_states", "min_months_per_state")
COVERAGE_AXIS_MARKERS = ("estimable", "verdict", "reason", "coverage", "n_states",
                         "min_state_months")

#: Words that make a NUMERIC estimate key a composite regime verdict.  Matched
#: per TOKEN, not on the whole key: the kill this enforces is defeated by exactly
#: one rename, and ``fused_score``/``regime_grade``/``composite_v2`` are the
#: renames.  A key is composite when any of its tokens is one of these AND its
#: value is a number.
_COMPOSITE_ESTIMATE_TOKENS = frozenset({
    "score", "scores", "composite", "fused", "fusion", "rating", "grade",
    "verdict", "reliability", "blend", "ensemble", "aggregate", "overall",
})
_ESTIMATE_KEY_SPLIT = re.compile(r"[^a-z0-9]+")

#: Where an estimator declares what it consumed.  More than one axis named here
#: is a fusion, whatever the payload calls itself.
_ESTIMATE_INPUT_KEYS = ("axes", "inputs", "components", "features", "factors")


def _to_date(value: Any, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise RegimeFeatureError(f"{field} is not an ISO date: {value!r}") from exc
    raise RegimeFeatureError(f"{field} must be a date, datetime, or ISO string")


def axis_family(axis: str) -> str | None:
    """Which family an axis belongs to, or None when it is not authorized at all."""
    return _FAMILY_BY_AXIS.get(str(axis))


def axis_authority(axis: str) -> str | None:
    """``model_feature`` for a conditionable axis, ``display_context`` for a
    positioning/financing axis, None for an unauthorized one."""
    family = axis_family(axis)
    if family is None:
        return None
    return DISPLAY_CONTEXT if family in DISPLAY_ONLY_AXES else MODEL_FEATURE


def read_regime_context(
    raw: Mapping[str, Any],
    *,
    asof: Any,
    adapters: Mapping[str, str] = REVIEWED_PIT_ADAPTERS,
) -> dict[str, Any]:
    """Read authorized regime axes through reviewed PIT adapters.

    ``raw`` maps axis name -> ``{"value": ..., "known_at": date-like,
    "source": str}``.  Each axis comes back as its OWN entry carrying its own
    family, authority, value, and provenance.  Nothing is combined, summed,
    averaged, or ranked, and the return has no cross-axis aggregate key.

    Refusals are named and returned rather than raised, so a caller offering one
    unusable field still gets the rest of the context.  Use
    :func:`require_lawful_axes` when a refusal should be fatal.
    """
    when = _to_date(asof, "asof")
    axes: dict[str, dict[str, Any]] = {}
    refused: list[dict[str, Any]] = []

    for name in sorted(raw or {}):
        payload = raw[name]
        family = axis_family(name)
        if family is None:
            refused.append({"axis": name, "reason": REFUSE_UNAUTHORIZED,
                            "detail": "not on the explicit authorization allowlist"})
            continue
        adapter = adapters.get(name)
        if not adapter:
            refused.append({"axis": name, "reason": REFUSE_NO_ADAPTER,
                            "detail": "no reviewed point-in-time adapter for this axis"})
            continue
        if not isinstance(payload, Mapping) or "value" not in payload:
            refused.append({"axis": name, "reason": REFUSE_MALFORMED,
                            "detail": "expected {'value':..., 'known_at':...}"})
            continue
        try:
            known_at = _to_date(payload.get("known_at"), f"{name}.known_at")
        except RegimeFeatureError as exc:
            refused.append({"axis": name, "reason": REFUSE_MALFORMED, "detail": str(exc)})
            continue
        if known_at > when:
            refused.append({
                "axis": name, "reason": REFUSE_NOT_PIT,
                "detail": f"known_at={known_at.isoformat()} is after asof={when.isoformat()}",
            })
            continue
        axes[name] = {
            "axis": name,
            "family": family,
            "authority": axis_authority(name),
            "value": payload.get("value"),
            "known_at": known_at.isoformat(),
            "pit_adapter": adapter,
            "source": payload.get("source"),
            "note": ("display/context only — positioning and financing may never be "
                     "model features" if family in DISPLAY_ONLY_AXES else
                     "conditionable, subject to the interaction gate"),
        }

    return {
        "schema": REGIME_SCHEMA,
        "tier": TIER,
        "regime_version": REGIME_VERSION,
        "asof": when.isoformat(),
        "axes": axes,
        "refused": refused,
        "n_axes": len(axes),
        "conditionable_axes": sorted(a for a, v in axes.items()
                                     if v["authority"] == MODEL_FEATURE),
        "display_only_axes": sorted(a for a, v in axes.items()
                                    if v["authority"] == DISPLAY_CONTEXT),
        "governing_kills": list(GOVERNING_KILLS),
        "fusion": ("NOT COMPUTED — no composite regime score exists here; "
                   "renaming a composite does not make it lawful"),
    }


def require_lawful_axes(raw: Mapping[str, Any], *, asof: Any,
                        adapters: Mapping[str, str] = REVIEWED_PIT_ADAPTERS) -> dict[str, Any]:
    """Read the context and RAISE naming every refused axis."""
    context = read_regime_context(raw, asof=asof, adapters=adapters)
    if context["refused"]:
        named = ", ".join(f"{r['axis']} ({r['reason']}: {r['detail']})"
                          for r in context["refused"])
        raise RegimeFeatureError("refused regime axes: " + named)
    return context


# --------------------------------------------------------------------------- #
# the interaction gate
# --------------------------------------------------------------------------- #
def coverage_report_defects(report: Any) -> list[str]:
    """What is missing before a coverage report can be read as the house meter's.

    Empty list == the report carries the provenance
    :func:`engine.regime_conditioning_coverage.assess` stamps on everything it
    produces.  This is deliberately a SHAPE check on the meter's own fields
    rather than a version string: the gate's whole purpose is that a caller
    cannot assert its way past it, and a caller who can fabricate every gate
    value and every per-axis verdict field has reimplemented the meter.
    """
    if not isinstance(report, Mapping):
        return ["not_a_mapping"]
    defects = [f"missing:{k}" for k in COVERAGE_REPORT_MARKERS if k not in report]
    gates = report.get("gates")
    if not isinstance(gates, Mapping):
        defects.append("missing:gates_block")
    else:
        defects += [f"missing:gates.{k}" for k in COVERAGE_GATE_MARKERS if k not in gates]
    if not isinstance(report.get("axes"), Mapping):
        defects.append("axes_is_not_a_mapping")
    return defects


def _axis_report_defects(axis_report: Any) -> list[str]:
    if not isinstance(axis_report, Mapping):
        return ["not_a_mapping"]
    return [f"missing:{k}" for k in COVERAGE_AXIS_MARKERS if k not in axis_report]


def _estimate_defects(payload: Any) -> list[str]:
    """Why an interaction estimate may not be returned.  Empty list == lawful.

    Two shapes are refused, both of them the forbidden fusion wearing a
    per-axis coat: a composite-looking key carrying a NUMBER, and a payload that
    declares more than one axis as its input.
    """
    if not isinstance(payload, Mapping):
        return ["estimate_is_not_a_mapping"]
    defects: list[str] = []
    for key, value in payload.items():
        tokens = {t for t in _ESTIMATE_KEY_SPLIT.split(str(key).lower()) if t}
        if (tokens & _COMPOSITE_ESTIMATE_TOKENS) and isinstance(value, (int, float)) \
                and not isinstance(value, bool):
            defects.append(f"composite_scalar:{key}")
    for key in _ESTIMATE_INPUT_KEYS:
        declared = payload.get(key)
        if isinstance(declared, (list, tuple, set)) and len(
                {str(x) for x in declared}) > 1:
            defects.append(f"multi_axis_input:{key}={sorted(str(x) for x in declared)}")
    return defects


def interaction_eligibility(
    axis: str,
    coverage_report: Mapping[str, Any] | None,
    preregistration: Mapping[str, Any] | None = None,
    *,
    interaction_name: str | None = None,
    asof: Any = None,
    max_preregistration_age_days: int = MAX_PREREGISTRATION_AGE_DAYS,
) -> dict[str, Any]:
    """Is a regime INTERACTION on ``axis`` eligible to be estimated at all?

    Every condition is checked against the artifacts, not against a caller's
    assertion:

    0. ``axis`` is on the explicit allowlist.  An axis nobody authorized is
       refused by name — falling through to "conditionable" would make the
       allowlist a pattern, which is exactly what it is not.
    1. the coverage report carries the provenance
       :func:`engine.regime_conditioning_coverage.assess` stamps (see
       :func:`coverage_report_defects`), and so does the per-axis verdict.
    2. ``coverage_report["axes"][axis]["estimable"]`` is True — that meter binds
       on DISTINCT MONTHS rather than rows, because same-day rows share one
       market.
    3. ``preregistration["primary_interactions"]`` names this interaction, and
       when ``asof`` is supplied it was registered within
       ``max_preregistration_age_days`` of it.

    A display/context-only axis (positioning, financing) is never eligible, no
    matter what the coverage says.
    """
    axis = str(axis)
    name = interaction_name or f"market_response_x_{axis}"
    base = {
        "schema": REGIME_ABSTENTION_SCHEMA,
        "tier": TIER,
        "axis": axis,
        "interaction": name,
        "family": axis_family(axis),
        "eligible": False,
        "reason": None,
        "coverage_verdict": None,
        "preregistration_id": None,
        "preregistration_freshness": None,
        "governing_kills": list(GOVERNING_KILLS),
    }

    authority = axis_authority(axis)
    if authority is None:
        base["reason"] = ABSTAIN_AXIS_UNAUTHORIZED
        base["detail"] = (
            f"'{axis}' is not on the explicit authorization allowlist "
            f"{sorted(_FAMILY_BY_AXIS)} — an unreviewed axis has no authority to fall "
            "back on, and admitting it here would turn the allowlist into a pattern")
        return base

    if authority == DISPLAY_CONTEXT:
        base["reason"] = ABSTAIN_AXIS_DISPLAY_ONLY
        base["detail"] = (f"'{axis}' is a {axis_family(axis)} key: readable as context, "
                          "never a model feature and never fused into a score")
        return base

    if not isinstance(coverage_report, Mapping) or coverage_report.get("status") != "ok":
        base["reason"] = ABSTAIN_COVERAGE_UNAVAILABLE
        base["detail"] = ("no usable engine.regime_conditioning_coverage.assess() report — "
                          "treat every axis as NOT estimable")
        return base

    defects = coverage_report_defects(coverage_report)
    if defects:
        base["reason"] = ABSTAIN_COVERAGE_NOT_FROM_METER
        base["coverage_report_defects"] = defects
        base["detail"] = (
            "the coverage report does not carry what "
            f"engine.regime_conditioning_coverage.assess() stamps ({defects}); a "
            "hand-written report is the caller asserting the answer this gate exists "
            "to check")
        return base

    axis_report = (coverage_report.get("axes") or {}).get(axis)
    if axis_report is None:
        base["reason"] = ABSTAIN_AXIS_NOT_IN_REPORT
        base["detail"] = (f"'{axis}' was not assessed; a sibling axis being estimable "
                          "says nothing about this one")
        return base

    axis_defects = _axis_report_defects(axis_report)
    if axis_defects:
        base["reason"] = ABSTAIN_COVERAGE_NOT_FROM_METER
        base["coverage_report_defects"] = [f"axes.{axis}.{d}" for d in axis_defects]
        base["detail"] = (f"the verdict for '{axis}' is missing {axis_defects} — a bare "
                          "{'estimable': True} is an assertion, not a measurement")
        return base

    base["coverage_verdict"] = axis_report.get("verdict")
    base["coverage_detail"] = axis_report.get("reason")
    if not axis_report.get("estimable"):
        base["reason"] = ABSTAIN_AXIS_NOT_ESTIMABLE
        base["detail"] = (f"coverage verdict '{axis_report.get('verdict')}': "
                          f"{axis_report.get('reason')}")
        return base

    prereg = preregistration if isinstance(preregistration, Mapping) else {}
    primary = [str(x) for x in (prereg.get("primary_interactions") or [])]
    if name not in primary:
        base["reason"] = ABSTAIN_NO_PREREGISTRATION
        base["detail"] = (f"'{name}' is not named in the preregistration's "
                          f"primary_interactions {primary or '[]'} — an interaction found "
                          "after the fact is a search result, not a hypothesis")
        return base

    freshness, stale_reason, stale_detail = _preregistration_freshness(
        prereg, asof, int(max_preregistration_age_days))
    base["preregistration_freshness"] = freshness
    if stale_reason is not None:
        base["reason"] = stale_reason
        base["detail"] = stale_detail
        return base

    base.update({
        "schema": REGIME_SCHEMA,
        "eligible": True,
        "reason": None,
        "preregistration_id": prereg.get("id"),
        "preregistration_version": prereg.get("version"),
        "detail": (f"coverage 'estimable' for '{axis}' and the interaction is "
                   f"preregistered as primary ({freshness})"),
    })
    return base


def _preregistration_freshness(prereg: Mapping[str, Any], asof: Any,
                               max_age_days: int) -> tuple[str, str | None, str | None]:
    """``(freshness_label, abstention_reason | None, detail | None)``.

    Freshness is only meaningful against a decision moment.  With no ``asof``
    the label says the check did NOT run, rather than implying it passed — a
    preregistration written years earlier would otherwise read as fresh.
    """
    if asof is None:
        return ("not_checked:no_asof_supplied", None, None)
    when = _to_date(asof, "asof")
    raw = prereg.get("registered_at")
    if raw is None:
        return ("undated", ABSTAIN_PREREGISTRATION_UNDATED,
                "the preregistration carries no registered_at, so its freshness at "
                f"asof={when.isoformat()} cannot be checked and is not assumed")
    registered = _to_date(raw, "preregistration.registered_at")
    age = (when - registered).days
    if registered > when:
        return (f"registered_at={registered.isoformat()}_after_asof",
                ABSTAIN_PREREGISTRATION_STALE,
                f"registered_at={registered.isoformat()} is AFTER asof={when.isoformat()} "
                "— a hypothesis written after the decision is not a preregistration")
    if age > int(max_age_days):
        return (f"stale:{age}d", ABSTAIN_PREREGISTRATION_STALE,
                f"registered {age}d before asof={when.isoformat()} (floor "
                f"{max_age_days}d) — a preregistration that old is a habit, not a "
                "hypothesis; re-register it")
    return (f"fresh:{age}d_at_{when.isoformat()}", None, None)


def conditional_estimate_or_context(
    axis: str,
    coverage_report: Mapping[str, Any] | None,
    preregistration: Mapping[str, Any] | None = None,
    *,
    estimator: Callable[[], Mapping[str, Any]] | None = None,
    context: Mapping[str, Any] | None = None,
    interaction_name: str | None = None,
    asof: Any = None,
    max_preregistration_age_days: int = MAX_PREREGISTRATION_AGE_DAYS,
) -> dict[str, Any]:
    """The gate, applied.  Eligible -> run ``estimator``.  Otherwise -> show the
    regime as CONTEXT and abstain from the interaction estimate BY NAME.

    ``estimator`` is a zero-argument callable so the ineligible path cannot even
    build the estimate: there is no computed number waiting to be dropped.

    The estimator's RESULT is screened before it is returned
    (:func:`_estimate_defects`).  The gate authorizes an interaction on ONE
    axis; an estimator that hands back a composite scalar, or that declares
    several axes as its inputs, is doing the fusion the governing kills forbid
    and is refused with :class:`RegimeFeatureError` rather than passed through
    because the axis-level gate happened to open.
    """
    gate = interaction_eligibility(axis, coverage_report, preregistration,
                                   interaction_name=interaction_name, asof=asof,
                                   max_preregistration_age_days=max_preregistration_age_days)
    out = {
        "schema": REGIME_SCHEMA,
        "tier": TIER,
        "axis": axis,
        "gate": gate,
        "context": dict(context) if context else None,
        "estimate": None,
        "abstained": True,
        "reason": gate.get("reason"),
    }
    if not gate["eligible"]:
        out["display"] = ("regime shown as context; the interaction estimate is "
                          "withheld, not zeroed")
        return out
    if estimator is None:
        out["reason"] = "no_estimator_supplied"
        return out
    estimate = estimator()
    defects = _estimate_defects(estimate)
    if defects:
        raise RegimeFeatureError(
            f"the interaction estimate for '{axis}' is a forbidden fusion ({defects}). "
            f"{', '.join(GOVERNING_KILLS)}: an eligible axis authorizes an interaction on "
            "THAT AXIS, not a composite regime verdict returned through it. Renaming a "
            "composite does not make it lawful.")
    out.update({"estimate": dict(estimate), "abstained": False, "reason": None,
                "estimate_screen": {"defects": [], "screened_for":
                                    "composite scalars and multi-axis inputs"}})
    return out


def assess_axis_coverage(frame: Any, axis: str, *, date_col: str = "date") -> dict[str, Any]:
    """Thin wrapper over :func:`engine.regime_conditioning_coverage.assess`.

    Imported LAZILY: the coverage meter needs pandas, and the rest of this module
    is stdlib so a thin ingestion runner can read regime context without the
    scientific stack.
    """
    from engine import regime_conditioning_coverage as rcc

    return rcc.assess(frame, axes=(str(axis),), date_col=date_col)


__all__ = [
    "ABSTAIN_AXIS_DISPLAY_ONLY",
    "ABSTAIN_AXIS_NOT_ESTIMABLE",
    "ABSTAIN_AXIS_NOT_IN_REPORT",
    "ABSTAIN_AXIS_UNAUTHORIZED",
    "ABSTAIN_COVERAGE_NOT_FROM_METER",
    "ABSTAIN_COVERAGE_UNAVAILABLE",
    "ABSTAIN_NO_PREREGISTRATION",
    "ABSTAIN_PREREGISTRATION_STALE",
    "ABSTAIN_PREREGISTRATION_UNDATED",
    "AUTHORIZED_AXES",
    "COVERAGE_AXIS_MARKERS",
    "COVERAGE_GATE_MARKERS",
    "COVERAGE_REPORT_MARKERS",
    "DISPLAY_CONTEXT",
    "DISPLAY_ONLY_AXES",
    "GOVERNING_KILLS",
    "MAX_PREREGISTRATION_AGE_DAYS",
    "MODEL_FEATURE",
    "REFUSE_MALFORMED",
    "REFUSE_NOT_PIT",
    "REFUSE_NO_ADAPTER",
    "REFUSE_UNAUTHORIZED",
    "REGIME_ABSTENTION_SCHEMA",
    "REGIME_SCHEMA",
    "REGIME_VERSION",
    "REVIEWED_PIT_ADAPTERS",
    "RegimeFeatureError",
    "TIER",
    "assess_axis_coverage",
    "axis_authority",
    "axis_family",
    "conditional_estimate_or_context",
    "coverage_report_defects",
    "interaction_eligibility",
    "read_regime_context",
    "require_lawful_axes",
]
