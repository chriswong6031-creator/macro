"""Market-response forecasts for biopharma seasonality — the ONLY family this
package is allowed to train.

THE OWNERSHIP LAW
=================
Three probabilities live in this product and they have three different owners.
Confusing them is not a modelling preference, it is a boundary violation, and it
is the failure this module is shaped to make impossible:

1. **Does a catalyst happen, and when?**  Event occurrence and timing.
   **BioCatalyst owns it.**  Nothing here estimates a hazard, a slip probability,
   or a readout date.
2. **What is the clinical or regulatory RESULT?**  Approval, hit/miss on the
   endpoint, CRL.  **BioCatalyst owns it.**  Nothing here estimates an approval
   probability or a trial-success prior.
3. **How does the MARKET respond, conditional on the known calendar / event /
   regime state?**  Return, barrier touch, drawdown, volatility, or the whole
   outcome distribution.  **This is the only family Seasonality may train**, and
   everything in this file is inside it.

The law is enforced twice over.  ``screen_features`` classifies every offered
feature by name and ``require_lawful_features`` REFUSES an owner probability BY
NAME rather than quietly regressing on it.  A caller who genuinely holds a
versioned, calibrated, read-only owner artifact may present it — and it is still
display/context by default: promoting it to a model FEATURE needs
``allow_owner_probability_feature=True`` *and* a preregistration that NAMES the
feature (a membership test, not a non-blank id), and this PR never flips that
default anywhere.  The reason for the double lock is that an approval probability
used as a regressor turns a market-response model into a clinical model wearing
market clothes, and the resulting number reads exactly like a legitimate edge.

The screen reads RATE-SHAPED names too.  ``phase3_success_rate``,
``historical_approval_rate``, ``crl_rate``, ``trial_win_pct`` and
``readout_success_share`` are owner probabilities written in spreadsheet
vocabulary; a screen that only knows the word "probability" waves every one of
them through and stamps it ``lawful``.  What survives the rate screen is the
calendar — ``expected_readout_date`` is a date, not a rate, and dates are exactly
what a market-response model conditions on.

POSITIONING AND FINANCING are the third refusal.  ``short_interest_pct``,
``dealer_gamma_state``, ``atm_shelf_state`` and their siblings are readable as
CONTEXT and may never be model features.  The ceiling
:mod:`engine.seasonality.regime` enforces on its own axis path is enforced here
too, on the same list, read from that module rather than copied.

WHAT ELSE THIS MODULE REFUSES TO DO
-----------------------------------
* **It never hides the baseline.**  Transparent empirical and shrinkage baselines
  are returned ALONGSIDE any challenger, never replaced by it.  A challenger with
  no visible benchmark is an unfalsifiable claim; ``forecast`` has no code path
  that drops ``baselines``.
* **It never forces a probability onto a continuous target.**  A binary target
  returns ``kind="probability"`` and carries a ``probability`` key; a continuous
  or distributional target returns ``expectation`` / ``quantiles`` /
  ``distribution`` and carries NO probability key anywhere in the payload.  A
  forced probability on a continuous target is how "62% chance" gets printed for
  a quantity that has no such interpretation.
* **It never labels an uncertainty generically.**  Every uncertainty payload
  names its semantics — ``parameter_ci`` (how well we know the parameter),
  ``predictive_interval`` (where the NEXT outcome lands), or
  ``outcome_quantiles`` (the shape of the outcome distribution).  A bare
  ``interval`` raises :class:`UncertaintySemanticsError`, because those three
  differ by a factor of several and a reader cannot tell which one they are
  looking at from a number alone.
* **It abstains rather than guessing.**  Thin, stale, extrapolative, structurally
  broken, and unestimable cases return a NAMED abstention, never a number.

SHADOW STATUS IS BINDING
------------------------
The forward ledger carries 28 registrations and ZERO matured grades.  Nothing in
this module is promoted, no availability flag moves, and every payload it
produces — including every abstention — carries ``tier="shadow"``.  Promotion to
rank/size/gate runs the separate gauntlet, and nothing here runs it.

Build floors (``BUILD_FLOORS``) are DESCRIPTIVE: they say when a picture is too
thin to draw, not when a signal has earned authority.

Determinism: this module reads no wall clock and no filesystem.  ``asof`` and
``data_cutoff`` are arguments.  Two calls with the same inputs return the same
bytes.  Pure stdlib on purpose — the thin ingestion runners that import
``engine.seasonality`` have no scientific stack, and a market-response point
estimate needs arithmetic, not linear algebra.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

# --- identity ---------------------------------------------------------------

MODEL_SCHEMA = "biopharma.seasonality.model.v1"
ABSTENTION_SCHEMA = "biopharma.seasonality.model.abstention.v1"
MODEL_VERSION = "seasonality-market-response-v1"

#: The default calibration stamp.  ``uncalibrated-v0`` is a deliberate, VISIBLE
#: null: a payload carrying it has not been through
#: :mod:`engine.seasonality.calibration` at all.  It is not a placeholder that
#: reads like a version.
UNCALIBRATED_VERSION = "uncalibrated-v0"

#: Binding for every payload this module emits.  See the module docstring.
TIER = "shadow"


# --- the ownership law ------------------------------------------------------

#: Forecast families and who owns them.  The keys are the vocabulary the refusal
#: messages speak in, so a caller reads WHICH boundary they crossed.
FORECAST_FAMILY_OWNERS: dict[str, str] = {
    "event_occurrence_timing": "biocatalyst",
    "event_outcome": "biocatalyst",
    "market_response": "seasonality",
}

#: The one family this module may train.
OWNED_FAMILY = "market_response"

#: Name fragments that mark a field as a PROBABILITY/likelihood quantity.
_PROBABILITY_TOKENS = (
    "prob", "probability", "likelihood", "odds", "hazard", "chance", "prior",
    "expected_success", "pos_", "ptrs", "ptrs_", "risk_of",
)

#: RATE-SHAPED probability words.  ``phase3_success_rate``,
#: ``historical_approval_rate``, ``crl_rate``, ``trial_win_pct``,
#: ``endpoint_hit_ratio`` and ``readout_success_share`` are approval
#: probabilities written in the vocabulary a spreadsheet uses, and the fragment
#: list above misses every one of them: a rate IS a probability once it is
#: conditioned on a clinical event.
#:
#: Matched as WHOLE TOKENS, never as substrings — ``corporate`` ends in the
#: letters "rate", and a substring scan would refuse it.
_RATE_TOKENS = frozenset({
    "rate", "rates", "pct", "percent", "percentage", "share", "ratio", "ratios",
    "frequency", "freq", "incidence", "propensity", "proportion", "expected",
    "baserate", "hitrate",
})

#: Words that, as the FINAL token, say the field is a date, a count, or a label
#: rather than a rate.  ``expected_readout_date`` and ``expected_pdufa_date`` are
#: known calendar facts and the calendar is lawful; without this exemption the
#: rate screen above would refuse exactly the conditioning state this module is
#: supposed to use.
_NON_RATE_UNIT_TOKENS = frozenset({
    "date", "dates", "day", "days", "dt", "time", "timestamp", "ts", "month",
    "months", "week", "weeks", "year", "years", "quarter", "count", "n", "num",
    "flag", "id", "label", "state", "bucket", "venue", "tier", "name", "type",
    "category", "class", "status", "code",
})

#: Bare tokens that mean "probability of" when they LEAD or TRAIL a name.
#: ``p_phase3_success`` and ``approval_p`` are the two shapes this catches, and
#: they are the single most common way an owner probability is named.  A fragment
#: scan cannot catch them: a bare ``p`` appears inside half the words in English.
_PROBABILITY_EDGE_TOKENS = frozenset({"p", "pr", "prob", "probability", "prb"})

#: Name fragments that mark a field as EVENT OCCURRENCE / TIMING (owner 1).
_OCCURRENCE_TOKENS = (
    "readout", "pdufa", "catalyst", "occurrence", "announce", "slip", "delay",
    "hazard", "timing", "filing", "submission", "adcom",
)

#: Name fragments that mark a field as EVENT OUTCOME (owner 2).
_OUTCOME_TOKENS = (
    "approval", "approve", "success", "efficacy", "endpoint", "crl", "clinical",
    "regulatory", "phase1", "phase2", "phase3", "phase_1", "phase_2", "phase_3",
    "ph1", "ph2", "ph3", "topline", "win", "hit_endpoint", "trial",
)

#: Fields whose bare NAME is an owner probability with no qualifier — the
#: industry shorthands.  ``pos`` = probability of success, ``ptrs`` = probability
#: of technical and regulatory success.  These carry no probability token that a
#: fragment scan would catch, so they are listed.
_OWNER_PROBABILITY_EXACT = frozenset({
    "pos", "ptrs", "pts", "ptrs_score", "pos_score", "loa", "likelihood_of_approval",
    "success_prior", "readout_prior", "approval_prior",
})

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


class SeasonalityModelError(Exception):
    """Base for every refusal in this module."""


class OwnerProbabilityFeatureError(SeasonalityModelError):
    """A caller tried to use a BioCatalyst-owned probability as a model feature.

    Raised BY NAME, listing every offending field, because the failure mode is a
    feature dict that grew one convenient column and a model that then silently
    forecasts the wrong thing.
    """


class UncertaintySemanticsError(SeasonalityModelError):
    """An uncertainty payload did not name which uncertainty it is."""


class TargetKindError(SeasonalityModelError):
    """A target asked for an output kind that does not fit it."""


# --- typed targets ----------------------------------------------------------

#: What a caller may ask for.
TARGET_KINDS = ("binary", "continuous", "distributional")

#: What this module may return.  ``probability`` is reachable ONLY from a binary
#: target; the mapping below is the whole permission table.
OUTPUT_KINDS = ("probability", "expectation", "quantiles", "distribution")

TARGET_KIND_OUTPUTS: dict[str, tuple[str, ...]] = {
    "binary": ("probability",),
    "continuous": ("expectation",),
    "distributional": ("quantiles", "distribution"),
}


# --- uncertainty semantics --------------------------------------------------

#: The three uncertainties a reader can actually distinguish.  Each answers a
#: different question and they differ in width by a large factor, so a payload
#: that does not say which one it is cannot be read at all.
UNCERTAINTY_SEMANTICS = ("parameter_ci", "predictive_interval", "outcome_quantiles")

#: Labels that name NOTHING.  Rejected explicitly so the error message can say
#: which generic word was used rather than "unknown semantics".
FORBIDDEN_UNCERTAINTY_LABELS = frozenset({
    "interval", "ci", "band", "bands", "range", "bounds", "error", "error_bar",
    "uncertainty", "conf", "confidence", "spread",
})

#: z for the two-sided levels this module supports.  An unsupported level raises
#: rather than silently interpolating a normal quantile nobody asked for.
_Z_BY_LEVEL: dict[float, float] = {0.80: 1.281552, 0.90: 1.644854,
                                   0.95: 1.959964, 0.99: 2.575829}


# --- pooling ----------------------------------------------------------------

#: Pooling ladder, BROADEST first.  Each level shrinks toward the level above it
#: and the top level shrinks toward the grand mean, so a thin issuer cell borrows
#: from its event type, which borrows from its therapeutic class.
POOLING_LEVELS = ("therapeutic_class", "event_type", "issuer")

#: Shrinkage strength in pseudo-observations.  Deliberately STRONG (a cell needs
#: 24 effective observations before it outweighs its parent) because biotech
#: cells are thin and an unshrunk issuer mean on six events is noise wearing a
#: name.  A constant, not a parameter default a caller can quietly tune down to
#: zero: ``forecast`` records the value it used in every payload.
DEFAULT_SHRINKAGE_K = 24.0

#: The declared benchmark.  ONE, named, and always reported — there is
#: deliberately no "pick the best baseline" function in this module.
DEFAULT_BENCHMARK = "grand_mean_empirical"

BENCHMARKS = ("grand_mean_empirical", "shrunk_parent", "zero")


# --- build floors and staleness --------------------------------------------

#: DESCRIPTIVE floors — when the picture is too thin to draw.  NOT promotion
#: gates.  Effective N, not row count: same-week biotech catalysts are one macro
#: draw, and the default ``icc=1.0`` makes that explicit by collapsing each date
#: cluster to a single independent observation.
BUILD_FLOORS: dict[str, int] = {
    "min_effective_n": 12,
    "min_issuers": 8,
    "min_date_clusters": 12,
}

#: A market-response estimate built on a panel that stops more than a quarter
#: before the decision date is describing a different market.
MAX_DATA_AGE_DAYS = 120

#: Below this many rows a CELL cannot describe a spread or a shape, so the
#: predictive interval and the outcome quantiles are borrowed from the pooled
#: sample and the payload says ``borrowed_from_pool=True``.  The point estimate is
#: still the shrunk cell value — only the WIDTH is borrowed, and a borrowed width
#: that is disclosed beats a degenerate one that is not.
MIN_SPREAD_OBS = 8

# --- named abstention reasons ----------------------------------------------

ABSTAIN_NO_OBSERVATIONS = "no_observations"
ABSTAIN_THIN_EFFECTIVE_N = "thin_effective_n"
ABSTAIN_THIN_ISSUERS = "thin_issuers"
ABSTAIN_THIN_DATE_CLUSTERS = "thin_date_clusters"
ABSTAIN_STALE_DATA = "stale_data_cutoff"
ABSTAIN_FUTURE_DATA_CUTOFF = "data_cutoff_after_asof"
ABSTAIN_EXTRAPOLATIVE = "extrapolation_outside_declared_support"
ABSTAIN_STRUCTURALLY_BROKEN = "structurally_broken"
ABSTAIN_UNESTIMABLE_TARGET = "unestimable_target"

ABSTENTION_REASONS = (
    ABSTAIN_NO_OBSERVATIONS,
    ABSTAIN_THIN_EFFECTIVE_N,
    ABSTAIN_THIN_ISSUERS,
    ABSTAIN_THIN_DATE_CLUSTERS,
    ABSTAIN_STALE_DATA,
    ABSTAIN_FUTURE_DATA_CUTOFF,
    ABSTAIN_EXTRAPOLATIVE,
    ABSTAIN_STRUCTURALLY_BROKEN,
    ABSTAIN_UNESTIMABLE_TARGET,
)


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _to_date(value: Any, field: str) -> date:
    """Parse a date-like into ``date``.  Naive and declared, never guessed."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:  # pragma: no cover - message is the point
            raise SeasonalityModelError(f"{field} is not an ISO date: {value!r}") from exc
    raise SeasonalityModelError(f"{field} must be a date, datetime, or ISO string")


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _sd(values: Sequence[float]) -> float:
    """Sample standard deviation.  0.0 on a single observation — and the caller
    treats a zero-variance sample as structurally broken rather than as certain."""
    n = len(values)
    if n < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))


def _quantile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile on a sorted copy."""
    if not values:
        raise SeasonalityModelError("quantile of an empty sample")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * float(q)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[int(pos)]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def _z_for(level: float) -> float:
    z = _Z_BY_LEVEL.get(round(float(level), 4))
    if z is None:
        raise SeasonalityModelError(
            f"confidence level {level} is not one of {sorted(_Z_BY_LEVEL)} — this "
            "module does not interpolate normal quantiles a caller did not declare"
        )
    return z


# --------------------------------------------------------------------------- #
# THE OWNERSHIP LAW — feature screening
# --------------------------------------------------------------------------- #
_DISPLAY_ONLY_AXIS_CACHE: frozenset[str] | None = None


def display_context_axes() -> frozenset[str]:
    """The positioning/financing axes :mod:`engine.seasonality.regime` holds at
    display/context.

    READ from the regime module rather than copied, because a second copy of the
    list is a list that drifts, and imported LAZILY so this module stays
    importable on its own.  ``regime`` is pure stdlib too, so nothing scientific
    comes in behind it.
    """
    global _DISPLAY_ONLY_AXIS_CACHE
    if _DISPLAY_ONLY_AXIS_CACHE is None:
        from engine.seasonality import regime as _regime

        _DISPLAY_ONLY_AXIS_CACHE = frozenset(
            str(axis) for axes in _regime.DISPLAY_ONLY_AXES.values() for axis in axes)
    return _DISPLAY_ONLY_AXIS_CACHE


def classify_feature(name: str) -> dict[str, Any]:
    """Classify ONE offered feature name into a forecast family.

    A name is an OWNER PROBABILITY when it carries a probability/likelihood token
    OR a rate-shaped token (``rate``, ``pct``, ``share``, ``ratio``,
    ``frequency``, ``expected``) AND a clinical-occurrence or clinical-outcome
    token, or when its bare name is one of the industry shorthands (``pos``,
    ``ptrs``, ``loa``).  A rate conditioned on a clinical event IS a clinical
    probability: ``phase3_success_rate`` and ``p_phase3_success`` are the same
    number in different clothes, and only the second one looks like one.

    A name carrying only an occurrence/outcome token and no probability token is
    a KNOWN FACT — ``pdufa_date``, ``days_to_readout``, ``clinical_hold_flag``,
    ``expected_readout_date`` — and known calendar/event state is exactly what a
    market-response model is supposed to condition on.  That distinction is the
    whole point: the calendar is lawful, the clinical odds are not.

    A POSITIONING or FINANCING axis (``short_interest_pct``,
    ``dealer_gamma_state``, ``atm_shelf_state``, ...) is neither: it is lawful to
    SHOW and never lawful to model, and it comes back with
    ``is_display_context_only=True`` so the model boundary enforces the same
    ceiling :mod:`engine.seasonality.regime` enforces on its own axis path.
    """
    raw = str(name)
    lowered = raw.lower()
    tokens = [t for t in _TOKEN_SPLIT.split(lowered) if t]
    joined = "_".join(tokens)

    if joined in _OWNER_PROBABILITY_EXACT or lowered in _OWNER_PROBABILITY_EXACT:
        return {"name": raw, "family": "event_outcome", "owner": "biocatalyst",
                "is_owner_probability": True, "is_display_context_only": False,
                "matched": ["exact:" + joined], "detail": "industry shorthand for an owner probability"}

    if joined in display_context_axes() or lowered in display_context_axes():
        return {"name": raw, "family": OWNED_FAMILY,
                "owner": FORECAST_FAMILY_OWNERS[OWNED_FAMILY],
                "is_owner_probability": False, "is_display_context_only": True,
                "matched": ["display_only_axis:" + joined],
                "detail": ("positioning/financing axis: readable as CONTEXT and never a "
                           "model feature — fusing positioning into a model is "
                           "Signal-Commons illegal")}

    prob_hits = [t for t in _PROBABILITY_TOKENS if t in lowered]
    if tokens and tokens[0] in _PROBABILITY_EDGE_TOKENS and len(tokens) > 1:
        prob_hits.append(f"prefix:{tokens[0]}_")
    if len(tokens) > 1 and tokens[-1] in _PROBABILITY_EDGE_TOKENS:
        prob_hits.append(f"suffix:_{tokens[-1]}")
    # A rate-shaped token counts UNLESS the final token says the field is a date,
    # a count, or a label: ``expected_readout_date`` is a calendar fact.
    if tokens and tokens[-1] not in _NON_RATE_UNIT_TOKENS:
        prob_hits += [f"rate:{t}" for t in tokens if t in _RATE_TOKENS]
    occ_hits = [t for t in _OCCURRENCE_TOKENS if t in lowered]
    out_hits = [t for t in _OUTCOME_TOKENS if t in lowered]

    if prob_hits and (occ_hits or out_hits):
        family = "event_outcome" if out_hits else "event_occurrence_timing"
        return {
            "name": raw, "family": family, "owner": FORECAST_FAMILY_OWNERS[family],
            "is_owner_probability": True, "is_display_context_only": False,
            "matched": sorted(set(prob_hits + occ_hits + out_hits)),
            "detail": ("probability or rate token + clinical token: this estimates "
                       "whether/when a catalyst happens or how it resolves, which "
                       "Seasonality does not own"),
        }

    return {"name": raw, "family": OWNED_FAMILY, "owner": FORECAST_FAMILY_OWNERS[OWNED_FAMILY],
            "is_owner_probability": False, "is_display_context_only": False,
            "matched": sorted(set(occ_hits + out_hits)),
            "detail": ("known calendar/event/regime state" if (occ_hits or out_hits)
                       else "market-response state")}


def _owner_artifact_defects(envelope: Any, name: str) -> list[str]:
    """What is missing from a claimed owner artifact.  Empty list == well-formed.

    A well-formed artifact is VERSIONED, CALIBRATED, READ-ONLY, owned by
    BioCatalyst, and named by a preregistration.  Anything less is a number in a
    dict claiming to be governance.

    "Named by a preregistration" is a MEMBERSHIP test, not a non-blank string:
    ``preregistration_id="-"`` used to satisfy the check while naming nothing,
    which is the same hole :func:`engine.seasonality.regime.interaction_eligibility`
    closes by testing ``primary_interactions``.  The envelope must list this exact
    feature under ``preregistration_features``.
    """
    if not isinstance(envelope, Mapping):
        return ["not_a_mapping"]
    defects: list[str] = []
    if str(envelope.get("owner", "")).lower() != "biocatalyst":
        defects.append("owner!=biocatalyst")
    for field in ("artifact_version", "calibration_version", "preregistration_id"):
        if not str(envelope.get(field) or "").strip():
            defects.append(f"missing:{field}")
    if envelope.get("read_only") is not True:
        defects.append("read_only!=True")
    declared = envelope.get("preregistration_features")
    if not isinstance(declared, (list, tuple, set)) or not declared:
        defects.append("missing:preregistration_features")
    elif str(name) not in {str(x) for x in declared}:
        defects.append(f"preregistration_does_not_name:{name}")
    return defects


def screen_features(
    features: Mapping[str, Any] | Iterable[str] | None,
    *,
    allow_owner_probability_feature: bool = False,
    owner_artifacts: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Split offered features into lawful, refused, and context-only.

    ``allow_owner_probability_feature`` defaults to ``False`` and this PR never
    flips it.  Even when a caller sets it True the owner probability is admitted
    only behind a well-formed owner artifact (see :func:`_owner_artifact_defects`)
    — the flag lowers a lock, it does not remove the wall.

    A POSITIONING or FINANCING axis is refused outright and has no flag: it is
    ``context_only`` and nothing lowers that ceiling.

    NOTE on the two lists: an owner probability whose artifact is well-formed is
    reported in ``refused`` (as a FEATURE) *and* in ``context_only`` (as a lawful
    display), so this non-raising screen tells a caller both things at once.
    :func:`require_lawful_features` and :func:`forecast` see the ``refused``
    entry and REFUSE — the context/display path is reachable through
    ``screen_features`` only, deliberately, because a display permission must
    never become a modelling permission by being read from the wrong key.
    """
    if features is None:
        names: list[str] = []
    elif isinstance(features, Mapping):
        names = [str(k) for k in features]
    else:
        names = [str(k) for k in features]

    artifacts = dict(owner_artifacts or {})
    lawful: list[str] = []
    refused: list[dict[str, Any]] = []
    admitted: list[dict[str, Any]] = []
    context_only: list[dict[str, Any]] = []

    for name in names:
        verdict = classify_feature(name)
        if verdict.get("is_display_context_only"):
            refused.append({
                **verdict,
                "reason": "positioning_or_financing_axis_is_display_context_only",
                "artifact_defects": [],
            })
            context_only.append({**verdict, "authority": "display_context"})
            continue
        if not verdict["is_owner_probability"]:
            lawful.append(name)
            continue
        envelope = artifacts.get(name)
        defects = (_owner_artifact_defects(envelope, name) if envelope is not None
                   else ["no_owner_artifact"])
        if not allow_owner_probability_feature:
            refused.append({
                **verdict,
                "reason": "owner_probability_as_feature_requires_preregistration",
                "artifact_defects": defects,
            })
            if not defects:
                context_only.append({**verdict, "authority": "display_context"})
            continue
        if defects:
            refused.append({**verdict,
                            "reason": "owner_artifact_malformed",
                            "artifact_defects": defects})
            continue
        admitted.append({**verdict, "authority": "model_feature",
                         "artifact_version": envelope.get("artifact_version"),
                         "preregistration_id": envelope.get("preregistration_id")})

    return {
        "schema": MODEL_SCHEMA,
        "tier": TIER,
        "n_offered": len(names),
        "lawful": sorted(lawful),
        "refused": sorted(refused, key=lambda r: r["name"]),
        "admitted_owner_probability": sorted(admitted, key=lambda r: r["name"]),
        "context_only": sorted(context_only, key=lambda r: r["name"]),
        "allow_owner_probability_feature": bool(allow_owner_probability_feature),
        "owner_law": ("BioCatalyst owns event occurrence/timing and event outcome; "
                      "Seasonality owns market response conditional on known state"),
    }


def require_lawful_features(
    features: Mapping[str, Any] | Iterable[str] | None,
    *,
    allow_owner_probability_feature: bool = False,
    owner_artifacts: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Screen, and RAISE naming every refused field.  Returns the screen on pass."""
    screen = screen_features(
        features,
        allow_owner_probability_feature=allow_owner_probability_feature,
        owner_artifacts=owner_artifacts,
    )
    if screen["refused"]:
        named = ", ".join(
            f"{r['name']} ({r['family']} → owner={r['owner']}; {r['reason']})"
            for r in screen["refused"]
        )
        raise OwnerProbabilityFeatureError(
            "refused as model features (BioCatalyst owns them, or they are "
            "positioning/financing context): " + named +
            ". Seasonality may train ONLY the market response conditional on known "
            "calendar/event/regime state. A versioned, calibrated, read-only owner "
            "artifact may be shown as context; using one as a FEATURE additionally "
            "requires allow_owner_probability_feature=True and its own preregistration."
        )
    return screen


# --------------------------------------------------------------------------- #
# uncertainty with named semantics
# --------------------------------------------------------------------------- #
def make_uncertainty(semantics: str, **fields: Any) -> dict[str, Any]:
    """Build ONE uncertainty payload that says which uncertainty it is.

    ``semantics`` must be one of :data:`UNCERTAINTY_SEMANTICS`.  A generic label
    (``interval``, ``ci``, ``band``, ...) raises: those three uncertainties
    differ by a large factor and a reader cannot tell them apart from the numbers.
    """
    label = str(semantics).strip().lower()
    if label in FORBIDDEN_UNCERTAINTY_LABELS:
        raise UncertaintySemanticsError(
            f"'{semantics}' names no uncertainty. Say which one it is: "
            f"{list(UNCERTAINTY_SEMANTICS)} — parameter_ci is how well the parameter "
            "is known, predictive_interval is where the NEXT outcome lands, and "
            "outcome_quantiles is the shape of the outcome distribution. They are not "
            "the same width and a generic label makes them unreadable."
        )
    if label not in UNCERTAINTY_SEMANTICS:
        raise UncertaintySemanticsError(
            f"unknown uncertainty semantics {semantics!r}; expected one of "
            f"{list(UNCERTAINTY_SEMANTICS)}"
        )
    payload = {"semantics": label}
    payload.update(fields)
    return payload


def validate_uncertainty(block: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a whole ``uncertainty`` block (keyed by semantics)."""
    if not isinstance(block, Mapping):
        raise UncertaintySemanticsError("uncertainty block must be a mapping keyed by semantics")
    for key, payload in block.items():
        label = str(key).strip().lower()
        if label in FORBIDDEN_UNCERTAINTY_LABELS or label not in UNCERTAINTY_SEMANTICS:
            raise UncertaintySemanticsError(
                f"uncertainty key {key!r} names no uncertainty; expected one of "
                f"{list(UNCERTAINTY_SEMANTICS)}"
            )
        stated = str((payload or {}).get("semantics", "")).strip().lower()
        if stated != label:
            raise UncertaintySemanticsError(
                f"uncertainty['{key}'] states semantics={stated!r} — the key and the "
                "payload must agree, or a downstream reader picks whichever it sees first"
            )
    return dict(block)


def _wilson(p: float, n_eff: float, level: float) -> tuple[float, float]:
    """Wilson score interval on the EFFECTIVE sample size.  Wald is wrong at the
    edges and biotech rates live near the edges.

    ``p`` must be an OBSERVED proportion out of ``n_eff`` — that is the sampling
    model the interval is derived from.  Handing it a shrunk estimate produces an
    interval centred on one estimator and widthed for another; see
    :func:`shrunk_rate_interval` for the estimate this module actually publishes.
    """
    if n_eff <= 0:
        return (0.0, 1.0)
    z = _z_for(level)
    denom = 1.0 + z * z / n_eff
    centre = (p + z * z / (2 * n_eff)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n_eff + z * z / (4 * n_eff * n_eff))
    return (max(0.0, centre - half), min(1.0, centre + half))


def _log_beta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _betainc_regularized(x: float, a: float, b: float) -> float:
    """Regularized incomplete beta ``I_x(a, b)`` by the Lentz continued fraction.

    Stdlib only, because this module is imported by runners with no scientific
    stack.  Accurate to ~1e-12 over the range this file uses, and the test suite
    pins it against the three closed forms (``I_x(1,1)=x``, ``I_x(2,1)=x^2``,
    ``I_x(1,2)=1-(1-x)^2``).
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    # The continued fraction converges fast only on one side of the mode.
    if x > (a + 1.0) / (a + b + 2.0):
        return 1.0 - _betainc_regularized(1.0 - x, b, a)
    lbeta = _log_beta(a, b)
    front = math.exp(a * math.log(x) + b * math.log1p(-x) - lbeta) / a
    tiny = 1e-300
    f, c, d = 1.0, 1.0, 0.0
    for i in range(0, 400):
        m = i // 2
        if i == 0:
            numerator = 1.0
        elif i % 2 == 0:
            numerator = (m * (b - m) * x) / ((a + 2.0 * m - 1.0) * (a + 2.0 * m))
        else:
            numerator = (-((a + m) * (a + b + m) * x)
                         / ((a + 2.0 * m) * (a + 2.0 * m + 1.0)))
        d = 1.0 + numerator * d
        if abs(d) < tiny:
            d = tiny
        d = 1.0 / d
        c = 1.0 + numerator / c
        if abs(c) < tiny:
            c = tiny
        f *= c * d
        if abs(1.0 - c * d) < 1e-14:
            break
    return min(1.0, max(0.0, front * (f - 1.0)))


def _beta_quantile(q: float, a: float, b: float) -> float:
    """Inverse of :func:`_betainc_regularized` by bisection.

    Bisection rather than Newton on purpose: it cannot diverge, it needs no
    derivative, and 200 halvings on [0,1] is far below the precision anyone reads
    off a biotech rate.
    """
    if a <= 0.0 or b <= 0.0:
        return float("nan")
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _betainc_regularized(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return 0.5 * (lo + hi)


def shrunk_rate_interval(raw_rate: float, n_eff: float, parent: float,
                         shrinkage_k: float, level: float) -> dict[str, Any]:
    """The interval for the rate this module actually PUBLISHES.

    ``shrunk_baseline`` is exactly the posterior mean of a Beta prior centred on
    ``parent`` carrying ``shrinkage_k`` pseudo-observations, updated with
    ``n_eff`` effective trials at ``raw_rate``::

        posterior = Beta(k*parent + n_eff*raw,  k*(1-parent) + n_eff*(1-raw))
        posterior mean = (n_eff*raw + k*parent) / (n_eff + k)   <- the point estimate

    So the coherent uncertainty for that point is the posterior's own credible
    interval, and that is what this returns.  The previous construction — a
    Wilson interval fed the SHRUNK point but the RAW cell's ``n_eff`` — was
    centred on one estimator and widthed for another: it covered neither the true
    cell rate nor the shrunk estimand (measured 58.5% coverage at a nominal 90%
    on a 12-cluster cell whose parent disagreed with it).

    The UNSHRUNK cell rate and its Wilson interval are returned alongside, named,
    because a reader who wants the cell's own rate must not have to read a shrunk
    one and guess.
    """
    n_eff = max(float(n_eff), 0.0)
    k = max(float(shrinkage_k), 0.0)
    parent = min(max(float(parent), 0.0), 1.0)
    raw_rate = min(max(float(raw_rate), 0.0), 1.0)
    alpha = k * parent + n_eff * raw_rate
    beta = k * (1.0 - parent) + n_eff * (1.0 - raw_rate)
    tail = (1.0 - float(level)) / 2.0
    if alpha <= 0.0 or beta <= 0.0:
        # A degenerate prior+likelihood (k=0 on an all-0 or all-1 cell) has no
        # posterior to quote; say so rather than quoting a point as an interval.
        lo, hi = (0.0, 1.0)
        basis = "degenerate_posterior_widened_to_the_unit_interval"
    else:
        lo = _beta_quantile(tail, alpha, beta)
        hi = _beta_quantile(1.0 - tail, alpha, beta)
        basis = "beta_posterior_of_the_shrinkage_prior"
    w_lo, w_hi = _wilson(raw_rate, n_eff, level)
    weight = n_eff / (n_eff + k) if (n_eff + k) > 0 else 0.0
    return {
        "lo": lo, "hi": hi, "basis": basis,
        "posterior_alpha": alpha, "posterior_beta": beta,
        "prior_parent": parent, "prior_pseudo_observations": k,
        "n_eff": n_eff, "shrinkage_weight": weight,
        "raw_cell_rate": raw_rate,
        "raw_cell_wilson_lo": w_lo, "raw_cell_wilson_hi": w_hi,
    }


# --------------------------------------------------------------------------- #
# effective sample size
# --------------------------------------------------------------------------- #
def effective_sample_size(n_obs: int, n_clusters: int, icc: float = 1.0) -> float:
    """Design-effect effective N: ``n / (1 + (mbar - 1) * icc)``.

    The default ``icc=1.0`` is the CONSERVATIVE reading and it is the house line:
    biotech catalysts arrive in waves, so rows sharing a date cluster are one
    macro draw and effective N collapses to the number of clusters.  A caller who
    has measured a lower intra-cluster correlation may pass it, and the value used
    is stamped on every payload.
    """
    n_obs = int(n_obs)
    n_clusters = max(int(n_clusters), 0)
    if n_obs <= 0:
        return 0.0
    if n_clusters <= 0:
        return float(n_obs)
    mbar = n_obs / n_clusters
    deff = 1.0 + (mbar - 1.0) * float(icc)
    return float(n_obs) / max(deff, 1e-9)


# --------------------------------------------------------------------------- #
# baselines and hierarchical pooling — both always visible
# --------------------------------------------------------------------------- #
def empirical_baseline(values: Sequence[float]) -> dict[str, Any]:
    """The transparent baseline: the pooled sample mean and nothing else.

    It is here so a reader can always check the challenger against arithmetic
    they can do themselves.
    """
    vals = [float(v) for v in values]
    if not vals:
        return {"kind": "empirical", "value": None, "n": 0,
                "abstained": True, "reason": ABSTAIN_NO_OBSERVATIONS}
    return {"kind": "empirical", "value": _mean(vals), "n": len(vals),
            "sd": _sd(vals), "abstained": False, "reason": None}


def shrunk_baseline(values: Sequence[float], parent: float,
                    shrinkage_k: float = DEFAULT_SHRINKAGE_K,
                    n_eff: float | None = None) -> dict[str, Any]:
    """James-Stein-flavoured shrinkage of a cell mean toward its ``parent``.

    ``est = (n_eff * raw + k * parent) / (n_eff + k)``.  ``n_eff`` defaults to the
    row count only when the caller has no cluster structure; ``forecast`` always
    passes the clustered effective N, because shrinking on row count would let a
    single busy week outvote the parent.
    """
    vals = [float(v) for v in values]
    if not vals:
        return {"kind": "shrunk", "value": float(parent), "n": 0, "weight": 0.0,
                "parent": float(parent), "shrinkage_k": float(shrinkage_k),
                "abstained": False, "reason": "empty_cell_fell_back_to_parent"}
    raw = _mean(vals)
    w_n = float(n_eff if n_eff is not None else len(vals))
    weight = w_n / (w_n + float(shrinkage_k)) if (w_n + shrinkage_k) > 0 else 0.0
    return {"kind": "shrunk", "value": weight * raw + (1.0 - weight) * float(parent),
            "raw": raw, "n": len(vals), "n_eff": w_n, "weight": weight,
            "parent": float(parent), "shrinkage_k": float(shrinkage_k),
            "abstained": False, "reason": None}


def hierarchical_pooling(
    observations: Sequence[Mapping[str, Any]],
    *,
    levels: Sequence[str] = POOLING_LEVELS,
    value_key: str = "value",
    shrinkage_k: float = DEFAULT_SHRINKAGE_K,
    cluster_key: str = "date_cluster",
    icc: float = 1.0,
) -> dict[str, Any]:
    """Partial pooling down the ``levels`` ladder, broadest level first.

    Every level's cell is shrunk toward its PARENT cell (and the broadest level
    toward the grand mean), so a six-event issuer borrows from its event type,
    which borrows from its therapeutic class.  Shrinkage runs on the clustered
    effective N, not the row count.

    Returns the WHOLE ladder — grand mean, every level, every cell's raw value,
    n, effective n, and shrinkage weight — because a pooled number whose ladder
    is hidden cannot be audited.
    """
    rows = [r for r in observations if r.get(value_key) is not None]
    if not rows:
        return {"grand": None, "n": 0, "levels": {}, "abstained": True,
                "reason": ABSTAIN_NO_OBSERVATIONS, "shrinkage_k": float(shrinkage_k)}

    all_values = [float(r[value_key]) for r in rows]
    grand = _mean(all_values)

    ladder: dict[str, dict[str, Any]] = {}
    # A cell is addressed by the TUPLE of level values down to it, so two issuers
    # in different therapeutic classes never collide on a bare issuer name.
    parent_by_path: dict[tuple, float] = {(): grand}
    for depth, level in enumerate(levels):
        cells: dict[tuple, list[Mapping[str, Any]]] = {}
        for row in rows:
            path = tuple(str(row.get(lv)) for lv in levels[: depth + 1])
            if any(p in ("None", "") for p in path):
                continue
            cells.setdefault(path, []).append(row)
        level_out: dict[str, Any] = {}
        for path, cell_rows in sorted(cells.items()):
            vals = [float(r[value_key]) for r in cell_rows]
            n_clusters = len({str(r.get(cluster_key)) for r in cell_rows})
            n_eff = effective_sample_size(len(vals), n_clusters, icc=icc)
            parent = parent_by_path.get(path[:-1], grand)
            est = shrunk_baseline(vals, parent, shrinkage_k=shrinkage_k, n_eff=n_eff)
            parent_by_path[path] = est["value"]
            level_out["|".join(path)] = {
                "path": list(path), "raw": est["raw"], "n": est["n"],
                "n_eff": round(n_eff, 4), "n_date_clusters": n_clusters,
                "weight": round(est["weight"], 6), "parent": parent,
                "shrunk": est["value"],
            }
        ladder[level] = level_out

    return {"grand": grand, "n": len(rows), "levels": ladder,
            "level_order": list(levels), "shrinkage_k": float(shrinkage_k),
            "icc": float(icc), "abstained": False, "reason": None}


def _cell_path(pool: Mapping[str, Any], cell: Mapping[str, Any] | None,
               levels: Sequence[str]) -> tuple[list[str], dict[str, Any] | None, bool]:
    """Walk the ladder to the NARROWEST cell present for ``cell``.

    Returns ``(path, node, backed_off)``.  ``backed_off`` is True when the
    requested cell was not observed at some level and the estimate is therefore
    the broader parent's — an extrapolation the payload must flag rather than
    quietly absorb.
    """
    if not cell:
        return ([], None, False)
    requested = [str(cell.get(lv)) for lv in levels]
    node: dict[str, Any] | None = None
    path: list[str] = []
    backed_off = False
    for depth, level in enumerate(levels):
        if cell.get(levels[depth]) is None:
            backed_off = True
            break
        key = "|".join(requested[: depth + 1])
        found = (pool.get("levels", {}).get(level) or {}).get(key)
        if found is None:
            backed_off = True
            break
        node = found
        path = requested[: depth + 1]
    if node is None or len(path) < len([lv for lv in levels if cell.get(lv) is not None]):
        backed_off = True
    return (path, node, backed_off)


# --------------------------------------------------------------------------- #
# the forecast entry point
# --------------------------------------------------------------------------- #
def _provenance(
    *, target: Mapping[str, Any], n_obs: int, n_issuers: int, n_date_clusters: int,
    n_eff: float, icc: float, data_cutoff: date, asof: date,
    calibration_version: str, declared_benchmark: str, shrinkage_k: float,
    extrapolation: Mapping[str, Any], floors: Mapping[str, int],
) -> dict[str, Any]:
    """The block EVERY payload carries — abstentions included.  A refusal that
    does not say how thin the sample was is not auditable."""
    return {
        "schema": MODEL_SCHEMA,
        "tier": TIER,
        "family": OWNED_FAMILY,
        "owner": FORECAST_FAMILY_OWNERS[OWNED_FAMILY],
        "target": {"name": target.get("name"), "kind": target.get("kind"),
                   "horizon_days": target.get("horizon_days")},
        "effective_n": round(float(n_eff), 4),
        "n_obs": int(n_obs),
        "n_issuers": int(n_issuers),
        "n_date_clusters": int(n_date_clusters),
        "icc": float(icc),
        "extrapolation": dict(extrapolation),
        "calibration_version": str(calibration_version),
        "model_version": MODEL_VERSION,
        "data_cutoff": data_cutoff.isoformat(),
        "asof": asof.isoformat(),
        "data_age_days": (asof - data_cutoff).days,
        "declared_benchmark": str(declared_benchmark),
        "shrinkage_k": float(shrinkage_k),
        "build_floors": dict(floors),
    }


def _abstain(reason: str, detail: str, provenance: Mapping[str, Any]) -> dict[str, Any]:
    """The structured non-answer.  A refusal is a result with a name."""
    payload = dict(provenance)
    payload.update({
        "schema": ABSTENTION_SCHEMA,
        "abstained": True,
        "reason": reason,
        "detail": detail,
        "kind": None,
        "value": None,
        "baseline": None,
        "edge": None,
        "uncertainty": {},
        "baselines": payload.get("baselines", {}),
    })
    return payload


def _extrapolation_report(features: Mapping[str, Any] | None,
                          support: Mapping[str, Sequence[float]] | None,
                          cell_backoff: bool, backoff_detail: str) -> dict[str, Any]:
    """Two distinct extrapolations, kept apart on purpose.

    ``cell_backoff`` — the requested cell was not observed and the estimate came
    from a broader parent.  Shrinkage handles it honestly, so it is FLAGGED and
    the forecast proceeds.

    ``outside_declared_support`` — a feature value sits outside the range the
    caller declared the model was fit on.  There is no honest handling of that;
    it abstains.
    """
    outside: list[dict[str, Any]] = []
    if features and support:
        for name, bounds in support.items():
            if name not in features or features[name] is None:
                continue
            try:
                value = float(features[name])
                lo, hi = float(bounds[0]), float(bounds[1])
            except (TypeError, ValueError, IndexError):
                continue
            if value < lo or value > hi:
                outside.append({"feature": name, "value": value, "support": [lo, hi]})
    return {
        "cell_backoff": bool(cell_backoff),
        "cell_backoff_detail": backoff_detail if cell_backoff else None,
        "outside_declared_support": bool(outside),
        "outside_features": outside,
        "flagged": bool(cell_backoff or outside),
    }


def forecast(
    *,
    target: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    data_cutoff: Any,
    asof: Any,
    cell: Mapping[str, Any] | None = None,
    features: Mapping[str, Any] | None = None,
    challenger: Mapping[str, Any] | None = None,
    calibration_version: str = UNCALIBRATED_VERSION,
    declared_benchmark: str = DEFAULT_BENCHMARK,
    shrinkage_k: float = DEFAULT_SHRINKAGE_K,
    icc: float = 1.0,
    levels: Sequence[str] = POOLING_LEVELS,
    value_key: str = "value",
    cluster_key: str = "date_cluster",
    issuer_key: str = "issuer",
    floors: Mapping[str, int] = BUILD_FLOORS,
    max_data_age_days: int = MAX_DATA_AGE_DAYS,
    support: Mapping[str, Sequence[float]] | None = None,
    quantile_levels: Sequence[float] = (0.05, 0.25, 0.50, 0.75, 0.95),
    ci_level: float = 0.90,
    allow_owner_probability_feature: bool = False,
    owner_artifacts: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """A calibrated-shape MARKET RESPONSE forecast, or a named abstention.

    ``target`` is ``{"name": str, "kind": "binary"|"continuous"|"distributional",
    "horizon_days": int, "form": "quantiles"|"distribution" (distributional only)}``.

    The output kind is decided by the target kind and nothing else
    (:data:`TARGET_KIND_OUTPUTS`).  A continuous or distributional target carries
    NO probability key anywhere in the payload; a binary target carries
    ``kind="probability"`` and an explicit ``probability`` field.

    Baselines are always present under ``baselines``.  A ``challenger`` is
    reported next to them and never replaces them.
    """
    kind = str(target.get("kind", "")).strip().lower()
    if kind not in TARGET_KINDS:
        raise TargetKindError(
            f"target kind {target.get('kind')!r} is not one of {list(TARGET_KINDS)}"
        )
    form = str(target.get("form") or "").strip().lower()
    if kind == "distributional":
        # Quantiles by default: a quantile set is readable, a raw sample dump is a
        # payload a caller has to reduce themselves before it means anything.
        form = form or "quantiles"
        if form not in TARGET_KIND_OUTPUTS["distributional"]:
            raise TargetKindError(
                f"distributional target form {form!r} must be one of "
                f"{list(TARGET_KIND_OUTPUTS['distributional'])}"
            )
    if str(declared_benchmark) not in BENCHMARKS:
        raise SeasonalityModelError(
            f"declared_benchmark must be one of {list(BENCHMARKS)}; there is no "
            "'pick the best baseline' path in this module"
        )

    # The ownership law runs BEFORE anything is estimated: a refused feature must
    # never reach a fit, not even a fit that is later thrown away.
    feature_screen = require_lawful_features(
        features,
        allow_owner_probability_feature=allow_owner_probability_feature,
        owner_artifacts=owner_artifacts,
    )

    cutoff = _to_date(data_cutoff, "data_cutoff")
    when = _to_date(asof, "asof")

    rows = [r for r in observations if r.get(value_key) is not None]
    n_obs = len(rows)
    issuers = {str(r.get(issuer_key)) for r in rows if r.get(issuer_key) is not None}
    clusters = {str(r.get(cluster_key)) for r in rows if r.get(cluster_key) is not None}
    n_eff = effective_sample_size(n_obs, len(clusters), icc=icc)

    pool = hierarchical_pooling(rows, levels=levels, value_key=value_key,
                                shrinkage_k=shrinkage_k, cluster_key=cluster_key, icc=icc)
    path, node, backed_off = _cell_path(pool, cell, levels)
    backoff_detail = (
        f"requested cell {dict(cell or {})} resolved to path {path or ['<grand>']}"
    )
    extrapolation = _extrapolation_report(features, support, backed_off, backoff_detail)

    provenance = _provenance(
        target=target, n_obs=n_obs, n_issuers=len(issuers), n_date_clusters=len(clusters),
        n_eff=n_eff, icc=icc, data_cutoff=cutoff, asof=when,
        calibration_version=calibration_version, declared_benchmark=declared_benchmark,
        shrinkage_k=shrinkage_k, extrapolation=extrapolation, floors=floors,
    )
    provenance["feature_screen"] = feature_screen
    provenance["pooling"] = {"level_order": list(levels), "grand": pool.get("grand"),
                             "cell_path": path, "cell": dict(cell or {})}

    # --- the abstention ladder, cheapest and most fundamental first ---------
    if n_obs == 0:
        return _abstain(ABSTAIN_NO_OBSERVATIONS,
                        "no observation carried a value for this target", provenance)

    values = [float(r[value_key]) for r in rows]

    # Staleness is ONE-SIDED by construction, so the other side needs its own
    # branch: a data_cutoff AFTER asof is a panel that extends past the decision
    # moment.  It produced a negative data_age_days that nothing read, and the
    # forecast went out happily on data nobody could have had.
    if (when - cutoff).days < 0:
        return _abstain(
            ABSTAIN_FUTURE_DATA_CUTOFF,
            f"data_cutoff={cutoff.isoformat()} is {(cutoff - when).days}d AFTER "
            f"asof={when.isoformat()}: the panel extends past the decision moment, so "
            "every estimate built on it is a lookahead, not a forecast",
            provenance)
    if (when - cutoff).days > int(max_data_age_days):
        return _abstain(
            ABSTAIN_STALE_DATA,
            f"panel stops {(when - cutoff).days}d before asof (floor {max_data_age_days}d): "
            "a market-response estimate this old is describing a different market",
            provenance)
    if extrapolation["outside_declared_support"]:
        named = ", ".join(f"{o['feature']}={o['value']} outside {o['support']}"
                          for o in extrapolation["outside_features"])
        return _abstain(ABSTAIN_EXTRAPOLATIVE, named, provenance)
    if n_eff < float(floors.get("min_effective_n", 0)):
        return _abstain(
            ABSTAIN_THIN_EFFECTIVE_N,
            f"effective_n={n_eff:.2f} < floor {floors.get('min_effective_n')} "
            f"({n_obs} rows in {len(clusters)} date clusters at icc={icc})",
            provenance)
    if len(issuers) < int(floors.get("min_issuers", 0)):
        return _abstain(ABSTAIN_THIN_ISSUERS,
                        f"n_issuers={len(issuers)} < floor {floors.get('min_issuers')}",
                        provenance)
    if len(clusters) < int(floors.get("min_date_clusters", 0)):
        return _abstain(
            ABSTAIN_THIN_DATE_CLUSTERS,
            f"n_date_clusters={len(clusters)} < floor {floors.get('min_date_clusters')}",
            provenance)

    sd = _sd(values)
    if kind == "binary":
        distinct = {round(float(v), 9) for v in values}
        if not distinct <= {0.0, 1.0}:
            return _abstain(ABSTAIN_UNESTIMABLE_TARGET,
                            "binary target received values outside {0,1}", provenance)
        if len(distinct) < 2:
            return _abstain(
                ABSTAIN_STRUCTURALLY_BROKEN,
                f"outcome is constant at {distinct.pop()} across {n_obs} observations — "
                "a rate with no variation is a fact about the sample, not a forecast",
                provenance)
    elif sd == 0.0:
        return _abstain(
            ABSTAIN_STRUCTURALLY_BROKEN,
            f"zero outcome variance across {n_obs} observations", provenance)

    # --- baselines: always computed, always returned ------------------------
    emp = empirical_baseline(values)
    parent = node["parent"] if node else pool["grand"]
    cell_values = values
    if node:
        cell_values = [
            float(r[value_key]) for r in rows
            if [str(r.get(lv)) for lv in levels[: len(path)]] == list(path)
        ] or values
    cell_clusters = len({str(r.get(cluster_key)) for r in rows
                         if [str(r.get(lv)) for lv in levels[: len(path)]] == list(path)}) or len(clusters)
    cell_eff = effective_sample_size(len(cell_values), cell_clusters, icc=icc)
    shr = shrunk_baseline(cell_values, parent, shrinkage_k=shrinkage_k, n_eff=cell_eff)

    benchmark_value = {"grand_mean_empirical": pool["grand"],
                       "shrunk_parent": parent,
                       "zero": 0.0}[str(declared_benchmark)]

    baselines = {
        "empirical_pooled": emp,
        "empirical_cell": {"kind": "empirical", "value": _mean(cell_values),
                           "n": len(cell_values), "n_eff": round(cell_eff, 4)},
        "shrunk_cell": shr,
        "grand": pool["grand"],
        "declared_benchmark": str(declared_benchmark),
        "benchmark_value": benchmark_value,
        "ladder": pool["levels"],
    }
    provenance["baselines"] = baselines

    value = float(shr["value"])
    challenger_block = None
    if challenger is not None:
        if not isinstance(challenger, Mapping) or "value" not in challenger:
            raise SeasonalityModelError("challenger must be a mapping carrying a 'value'")
        challenger_block = {
            "name": str(challenger.get("name") or "unnamed_challenger"),
            "value": float(challenger["value"]),
            "vs_declared_benchmark": float(challenger["value"]) - float(benchmark_value),
            "vs_shrunk_baseline": float(challenger["value"]) - value,
            "note": ("reported ALONGSIDE the baselines above, never in place of them — "
                     "a challenger with no visible benchmark is unfalsifiable"),
        }

    # BUILD_FLOORS gate the POOLED panel, but the published number describes the
    # CELL.  Those are different samples and the cell is usually far thinner, so
    # the payload states the cell's own size and whether it would clear the same
    # floor.  It is a DISCLOSURE, not a second abstention: shrinkage toward a
    # well-estimated parent is exactly how a thin cell is supposed to be handled
    # (a 12-cluster cell at k=24 is ~two-thirds parent), and refusing every thin
    # cell would delete the pooling ladder this module is built on.  What is not
    # allowed is publishing it while `build_floors` in the same dict advertises
    # floors that were never applied to it.
    cell_floor = float(floors.get("min_effective_n", 0))
    cell_meets = cell_eff >= cell_floor
    cell_floors_block = {
        "n_cell_obs": len(cell_values),
        "effective_n_cell": round(cell_eff, 4),
        "n_cell_date_clusters": cell_clusters,
        "min_effective_n": cell_floor,
        "meets_build_floors": bool(cell_meets),
        "floors_applied_to": "pooled_panel",
        "note": ("build_floors gate the POOLED panel; this block reports the CELL the "
                 "published value describes. A cell below the floor is not refused — it "
                 "is shrunk toward its parent and disclosed here."),
    }

    out = dict(provenance)
    out.update({
        "abstained": False,
        "reason": None,
        "baselines": baselines,
        "challenger": challenger_block,
        "n_cell_obs": len(cell_values),
        "effective_n_cell": round(cell_eff, 4),
        "n_cell_date_clusters": cell_clusters,
        "thin_cell": bool(not cell_meets),
        "cell_floors": cell_floors_block,
    })

    if kind == "binary":
        # The point estimate is the SHRUNK cell rate, so the interval is that
        # estimator's own posterior — not a Wilson interval for a raw proportion
        # wrapped around a shrunk centre.  See shrunk_rate_interval.
        raw_cell_rate = _mean(cell_values)
        band = shrunk_rate_interval(raw_cell_rate, cell_eff, parent, shrinkage_k, ci_level)
        unc = validate_uncertainty({
            "parameter_ci": make_uncertainty(
                "parameter_ci", level=ci_level, lo=band["lo"], hi=band["hi"],
                basis=band["basis"],
                posterior_alpha=round(band["posterior_alpha"], 6),
                posterior_beta=round(band["posterior_beta"], 6),
                prior_parent=round(band["prior_parent"], 6),
                prior_pseudo_observations=band["prior_pseudo_observations"],
                n_eff=round(band["n_eff"], 4),
                shrinkage_weight=round(band["shrinkage_weight"], 6),
                raw_cell_rate=round(band["raw_cell_rate"], 6),
                raw_cell_wilson_lo=band["raw_cell_wilson_lo"],
                raw_cell_wilson_hi=band["raw_cell_wilson_hi"],
                note=("how well the SHRUNK CELL RATE reported as `value` is known, under "
                      "this module's own pooling prior. It is NOT an interval for the "
                      "cell's unshrunk rate — that one is reported beside it as "
                      "raw_cell_rate / raw_cell_wilson_* — and it is not where the next "
                      "outcome lands")),
        })
        out.update({
            "kind": "probability",
            # A binary target is the ONLY payload in this module that carries a
            # probability key.  The continuous/distributional branches below do
            # not, and the test suite pins both directions.
            "probability": value,
            "value": value,
            "baseline": float(benchmark_value),
            "edge": value - float(benchmark_value),
            "uncertainty": unc,
        })
        return out

    if kind == "continuous":
        # A cell with one row has sd 0, and a zero-width predictive interval is a
        # lie about certainty.  Fall back to the POOLED spread and say so, rather
        # than publishing a degenerate band.
        cell_sd = _sd(cell_values)
        borrowed = len(cell_values) < MIN_SPREAD_OBS or cell_sd <= 0.0
        pred_sd = sd if borrowed else cell_sd
        # Same coherence rule as the binary branch: `value` is the SHRUNK cell
        # mean, which is the posterior mean of a normal prior at `parent`
        # carrying `shrinkage_k` pseudo-observations, so its standard error runs
        # on n_eff + k rather than on n_eff alone.  Dividing the raw cell's SE
        # around a shrunk centre describes neither estimator.
        se_denom = cell_eff + float(shrinkage_k)
        se = (pred_sd / math.sqrt(se_denom)) if se_denom > 0 else float("nan")
        se_raw_cell = (pred_sd / math.sqrt(cell_eff)) if cell_eff > 0 else float("nan")
        z = _z_for(ci_level)
        unc = validate_uncertainty({
            "parameter_ci": make_uncertainty(
                "parameter_ci", level=ci_level, lo=value - z * se, hi=value + z * se,
                se=se, basis="normal_posterior_on_effective_n_plus_shrinkage_pseudo_obs",
                prior_parent=float(parent),
                prior_pseudo_observations=float(shrinkage_k),
                n_eff=round(cell_eff, 4),
                raw_cell_mean=_mean(cell_values),
                raw_cell_se=se_raw_cell,
                note=("how well the SHRUNK MEAN response reported as `value` is known, "
                      "under this module's own pooling prior; the unshrunk cell mean and "
                      "its standard error are reported beside it")),
            "predictive_interval": make_uncertainty(
                "predictive_interval", level=ci_level,
                lo=value - z * pred_sd, hi=value + z * pred_sd,
                sd=pred_sd,
                basis="pooled_outcome_sd" if borrowed else "cell_outcome_sd",
                borrowed_from_pool=bool(borrowed),
                note="where a SINGLE next outcome lands — wider than the parameter CI"),
        })
        out.update({
            "kind": "expectation",
            "value": value,
            "baseline": float(benchmark_value),
            "edge": value - float(benchmark_value),
            "uncertainty": unc,
        })
        return out

    # distributional — a shape drawn from three points is not a shape.  Below
    # MIN_SPREAD_OBS the quantiles are the POOLED ones and the payload says so.
    borrowed = len(cell_values) < MIN_SPREAD_OBS
    shape_sample = values if borrowed else cell_values
    qs = {str(q): _quantile(shape_sample, q) for q in quantile_levels}
    base_qs = {str(q): _quantile(values, q) for q in quantile_levels}
    unc = validate_uncertainty({
        "outcome_quantiles": make_uncertainty(
            "outcome_quantiles", levels=[float(q) for q in quantile_levels],
            quantiles=qs,
            basis="pooled_empirical_quantiles" if borrowed else "cell_empirical_quantiles",
            borrowed_from_pool=bool(borrowed),
            note="the SHAPE of the outcome distribution, not an estimate's precision"),
    })
    # When the shape is BORROWED, `qs` and `base_qs` are computed from the same
    # pooled sample, so a per-quantile edge would be identically 0.0 at every
    # level — a structurally forced zero that reads as a measured "no edge".  Say
    # it was not computed instead.
    if borrowed:
        edge: Any = None
        edge_note = ("NOT COMPUTED: this cell borrowed the pooled shape, so a "
                     "cell-minus-pool edge is exactly zero by construction at every "
                     "quantile and would read as a measured null")
    else:
        edge = {k: qs[k] - base_qs[k] for k in qs}
        edge_note = "cell empirical quantiles minus the pooled empirical quantiles"
    out.update({
        "kind": "quantiles" if form == "quantiles" else "distribution",
        "value": value,
        "quantiles": qs,
        "baseline": base_qs,
        "baseline_expectation": float(benchmark_value),
        "edge": edge,
        "edge_note": edge_note,
        "uncertainty": unc,
    })
    if form == "distribution":
        # The SAME sample the quantiles were drawn from.  Reporting the cell's
        # rows underneath pooled quantiles put two different samples in one
        # payload with nothing saying which was which.
        out["distribution"] = {"form": "empirical_sample",
                               "samples": sorted(float(v) for v in shape_sample),
                               "n": len(shape_sample),
                               "borrowed_from_pool": bool(borrowed),
                               "basis": ("pooled_sample" if borrowed else "cell_sample"),
                               "n_cell_obs": len(cell_values)}
    return out


__all__ = [
    "ABSTAIN_EXTRAPOLATIVE",
    "ABSTAIN_FUTURE_DATA_CUTOFF",
    "ABSTAIN_NO_OBSERVATIONS",
    "ABSTAIN_STALE_DATA",
    "ABSTAIN_STRUCTURALLY_BROKEN",
    "ABSTAIN_THIN_DATE_CLUSTERS",
    "ABSTAIN_THIN_EFFECTIVE_N",
    "ABSTAIN_THIN_ISSUERS",
    "ABSTAIN_UNESTIMABLE_TARGET",
    "ABSTENTION_REASONS",
    "ABSTENTION_SCHEMA",
    "BENCHMARKS",
    "BUILD_FLOORS",
    "DEFAULT_BENCHMARK",
    "DEFAULT_SHRINKAGE_K",
    "FORBIDDEN_UNCERTAINTY_LABELS",
    "FORECAST_FAMILY_OWNERS",
    "MAX_DATA_AGE_DAYS",
    "MIN_SPREAD_OBS",
    "MODEL_SCHEMA",
    "MODEL_VERSION",
    "OUTPUT_KINDS",
    "OWNED_FAMILY",
    "POOLING_LEVELS",
    "TARGET_KINDS",
    "TARGET_KIND_OUTPUTS",
    "TIER",
    "UNCALIBRATED_VERSION",
    "UNCERTAINTY_SEMANTICS",
    "OwnerProbabilityFeatureError",
    "SeasonalityModelError",
    "TargetKindError",
    "UncertaintySemanticsError",
    "classify_feature",
    "display_context_axes",
    "effective_sample_size",
    "empirical_baseline",
    "forecast",
    "hierarchical_pooling",
    "make_uncertainty",
    "require_lawful_features",
    "screen_features",
    "shrunk_baseline",
    "shrunk_rate_interval",
    "validate_uncertainty",
]
