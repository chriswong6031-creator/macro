"""Calendar-only cross-symbol RESEARCH BROWSER — deliberately not a screener.

W7's real screener is blocked on two things that do not exist yet: point-in-time
membership (the identity plane answers "unavailable" for anything before its
first snapshot) and a calibrated / out-of-sample record (the forward ledger
carries zero matured grades).  Shipping a browser anyway is fine.  Shipping one
that *looks* like the calibrated screener is not, so the distinction is the
deliverable here rather than a caveat bolted onto the payload:

* every module constant, every row, and every result set declares
  ``tier="research"`` and ``is_calibrated_screener=False`` with a plain-word
  reason a reader can act on;
* a historical up-share with a Wilson interval is a DESCRIPTION of what already
  happened, not a forecast.  The descriptive and calibrated legs live in
  separately named and separately typed fields so no caller can read one as the
  other, and :func:`order_rows` refuses to put them on a single sort axis;
* "ranking" here means the reader chose a column to sort by.  It never means
  engine conviction.  There is no default "best" ordering, no composite score,
  and no ``top_n``-by-fused-metric function anywhere in this module — see
  :data:`FORBIDDEN_RANKING_SYMBOLS`, which ``tests/test_seasonality_screener.py``
  asserts against the module namespace.  That roll-call only ever looked for a
  fused ranker spelled as a FUNCTION, so the ``*_edge`` columns (``share -
  baseline``: derived, fused, and carrying no interval of their own) are off
  :data:`SORTABLE_COLUMNS` too — sorting by one and taking the first page IS
  top-N-by-fused-metric, composed out of two permitted primitives;
* cross-symbol browsing spends a search budget the per-symbol window family knows
  nothing about, so every result set carries the PROGRAM-level multiplicity
  disclosure — validated on its CONTENT, not merely on its ``scope`` string — and
  any cohort or filter a reader composes is labelled exploratory and spends a NEW
  budget that ACCUMULATES across successive cuts.  It may never inherit an
  existing evidence label, p-value, calibration claim, or the program budget
  block itself;
* the injected boundaries are checked, not believed: a membership resolver's
  ``available: True`` must name a snapshot at or before the asof and actually
  contain members, an evidence label must be on an allowlist (the word
  "validated" cannot reach a reader through this surface), a calibrated row's
  reference must name the epoch it declares, and no calibrated row may live in
  this artifact at all while it stamps ``is_calibrated_screener=False``.

The module is pure stdlib on purpose (see the package docstring): it takes
resolvers and already-computed numbers rather than reading a store itself.
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime

# --- what this is, said in the payload -------------------------------------

RESEARCH_BROWSER_SCHEMA = "seasonality.research_browser.v1"
RESEARCH_ROW_SCHEMA = "seasonality.research_browser.row.v1"

TIER = "research"
IS_CALIBRATED_SCREENER = False
NOT_CALIBRATED_REASON = (
    "This is a research browser over the calendar clock, not a calibrated screener. "
    "It describes what a window did in past complete years. It does not forecast, "
    "rank, or size anything, and nothing here has an out-of-sample record yet."
)
NOT_CALIBRATED_BLOCKERS = (
    "point_in_time_membership_unavailable_before_first_identity_snapshot",
    "forward_ledger_has_zero_matured_grades",
)

#: The declared tier, frozen against the module globals above.  ``TIER`` and
#: ``IS_CALIBRATED_SCREENER`` are read at CALL time by the result-set builder and
#: by the API envelope, so a caller that reassigns them (a test fixture, a
#: monkeypatch, an importing module) could flip the artifact-level flag a consumer
#: branches on while every ROW kept ``False`` — a payload that contradicts itself.
#: :func:`assert_research_tier_intact` compares the live globals against these and
#: refuses, so the flip fails loudly instead of shipping.
_DECLARED_TIER = "research"
_DECLARED_IS_CALIBRATED_SCREENER = False

# --- estimate types: descriptive and calibrated never share an axis ---------

ESTIMATE_DESCRIPTIVE = "descriptive"
ESTIMATE_CALIBRATED = "calibrated"
ESTIMATE_TYPES = frozenset({ESTIMATE_DESCRIPTIVE, ESTIMATE_CALIBRATED})

#: The descriptive leg. A historical up-share and its Wilson interval.
DESCRIPTIVE_FIELDS = (
    "historical_up_share",
    "historical_up_share_baseline",
    "historical_up_share_edge",
)
#: The calibrated leg. Separately named AND separately typed so a descriptive
#: number can never arrive in a field a caller reads as a forecast. Nothing on
#: this tier fills it — a calibrated row additionally requires a
#: ``calibration_reference``, which only a graded out-of-sample epoch can mint.
CALIBRATED_FIELDS = (
    "calibrated_probability",
    "calibrated_probability_baseline",
    "calibrated_probability_edge",
)
_LEG_FIELDS = {
    ESTIMATE_DESCRIPTIVE: DESCRIPTIVE_FIELDS,
    ESTIMATE_CALIBRATED: CALIBRATED_FIELDS,
}

# --- typed uncertainty ------------------------------------------------------

#: The only three uncertainty semantics a row may declare. They answer different
#: questions and are NOT interchangeable: a parameter CI covers the unknown rate,
#: a predictive interval covers the next observation, and outcome quantiles
#: describe the realised spread. A generic label ("interval", "band", "range")
#: hides which one is meant and is refused.
UNCERTAINTY_SEMANTICS = ("parameter_ci", "predictive_interval", "outcome_quantiles")
FORBIDDEN_UNCERTAINTY_LABELS = frozenset(
    {
        "interval",
        "intervals",
        "ci",
        "confidence",
        "confidence_interval",
        "credible_interval",
        "band",
        "bands",
        "range",
        "bounds",
        "error_bar",
        "error_bars",
        "uncertainty",
        "spread",
    }
)

# --- user sorting, never engine conviction ----------------------------------

#: The complete allowlist of sortable columns. Anything else raises. Note what is
#: absent: there is no composite, no blended score, and no "rank" column, because
#: the browser has no conviction to express.
#: The ``*_edge`` fields are deliberately ABSENT.  An edge is ``share - baseline``:
#: a DERIVED, fused quantity rather than a raw disclosure.  Sorting by it and
#: taking the first page is top-N-by-fused-metric composed out of two permitted
#: primitives — the exact function this module claims not to have.  The edges
#: still ship on every row as disclosure; they are simply not a ranking axis.
#: (They also carry no interval of their own: ``uncertainty_low/high`` are the
#: Wilson bounds on the SHARE, on a different scale, so a UI that paired "the
#: sortable number" with "the interval" would mis-plot it by the baseline.)
SORTABLE_COLUMNS = (
    "symbol",
    "window_start_doy",
    "window_end_doy",
    "sample_size",
    "issuer_count",
    "date_cluster_count",
    "freshness_age_days",
    "round_trip_cost_bps",
    "family_adjusted_p_value",
    "historical_up_share",
    "historical_up_share_baseline",
    "calibrated_probability",
    "calibrated_probability_baseline",
)
#: Derived/fused columns that may be DISCLOSED but never sorted on. Named so the
#: test suite can assert the allowlist and this set stay disjoint.
FUSED_DISCLOSURE_ONLY_COLUMNS = frozenset(
    {"historical_up_share_edge", "calibrated_probability_edge"}
)
_TEXT_COLUMNS = frozenset({"symbol"})

#: Columns that carry an ESTIMATE. Sorting a mixed set of descriptive and
#: calibrated rows by one of these would place two different kinds of number on
#: one axis, which is the exact confusion this module exists to prevent.
ESTIMATE_AXIS_COLUMNS = frozenset(DESCRIPTIVE_FIELDS) | frozenset(CALIBRATED_FIELDS)

#: There is NO default ordering that means "best". Absent an explicit
#: ``sort_by`` the browser returns rows in stable identity order, which is an
#: index, not a ranking.
DEFAULT_SORT_BY = None
IDENTITY_ORDER_LABEL = "stable_identity_order_not_a_ranking"

#: Names that must never exist in this module. The test suite asserts every one
#: of them is absent from the namespace: a function that fuses disclosure columns
#: into one number and returns "the top N patterns" is the screener this PR
#: explicitly is not.
FORBIDDEN_RANKING_SYMBOLS = (
    "top_n",
    "top_patterns",
    "best_patterns",
    "best_windows",
    "rank_rows",
    "rank_symbols",
    "ranked_rows",
    "composite_score",
    "conviction",
    "conviction_score",
    "overall_score",
    "score_rows",
    "screen",
    "screener_score",
)

# --- machine authority ------------------------------------------------------

#: Consumers this artifact is FOR. Fail closed: an identity that is not here is
#: refused, because Synapse declares no consumer for this artifact at all and a
#: silent default would be the first step to one appearing.
PERMITTED_CONSUMERS = frozenset(
    {
        "human_research_browser",
        "api_research_browser",
    }
)

#: Substrings that mark a caller as a machine-authority consumer — a Neural Web
#: or Prophet score/rank/size path. Matching one is refused BY NAME so the log
#: says which system asked, not merely that something did.
#: Identities are folded (lowercased, ``-`` and whitespace mapped to ``_``) before
#: matching, so a token only ever needs its underscore spelling here — a
#: hyphenated duplicate would be dead weight that reads as extra coverage.
MACHINE_AUTHORITY_TOKENS = (
    "neuralweb",
    "neural_web",
    "synapse",
    "prophet",
    "signal_bus",
    "signalbus",
    "signal_engine",
    "qbus",
    "overlay",
    "scorer",
    "score_consumer",
    "ranker",
    "ranking_engine",
    "conviction",
    "sizer",
    "sizing",
    "position_manager",
    "gatekeeper",
    "risk_engine",
    "optimizer",
    "allocator",
    "alpha_model",
    "backtester",
    "trade_execution",
    "execution_engine",
    "trader",
    "llm_agent",
    "agent_runtime",
)
MACHINE_AUTHORITY_REFUSAL = "machine_authority_consumer_refused_by_name"
UNKNOWN_CONSUMER_REFUSAL = "consumer_not_on_research_allowlist"

# --- universe ---------------------------------------------------------------

UNIVERSE_POINT_IN_TIME = "point_in_time"
UNIVERSE_CURRENT_VINTAGE = "current_vintage"
CURRENT_VINTAGE_NOTE = (
    "Universe is current-vintage, survivorship-biased: this is today's roster read "
    "backwards, so names that delisted, were acquired, or were renamed are simply "
    "absent from every past year shown."
)
NO_RESOLVER_REASON = "point_in_time_membership_resolver_not_injected"

OOS_EPOCH_NONE = "none_no_matured_forward_grades"

#: ``\Z`` rather than ``$``: ``$`` also matches immediately BEFORE a trailing
#: newline, so ``"AAA\n"`` would pass and a newline-bearing symbol would then
#: travel into the total-order key, the payload, and every log line.
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,15}\Z")

# --- evidence labels --------------------------------------------------------

#: ``evidence_label`` is free text nowhere.  An unvalidated label is how the
#: word "validated" (CI-enforced on the site by ``scripts/check_validated_claims``,
#: which scans templates and never sees an API body) reaches a reader through
#: this surface, and how "STRONG BUY" would.  The allowlist is per leg.
DESCRIPTIVE_EVIDENCE_LABELS = (
    "descriptive_only_no_forward_record",
    "descriptive_only_small_sample",
    "descriptive_only_wide_interval",
    "descriptive_only_costs_exceed_edge",
)
CALIBRATED_EVIDENCE_LABELS = ("graded_out_of_sample",)
EVIDENCE_LABELS = DESCRIPTIVE_EVIDENCE_LABELS + CALIBRATED_EVIDENCE_LABELS
_LEG_EVIDENCE_LABELS = {
    ESTIMATE_DESCRIPTIVE: DESCRIPTIVE_EVIDENCE_LABELS,
    ESTIMATE_CALIBRATED: CALIBRATED_EVIDENCE_LABELS,
}


# --- errors -----------------------------------------------------------------


class ScreenerError(ValueError):
    """Base for every refusal in this module."""


class UncertaintySemanticsError(ScreenerError):
    """An untyped or generic uncertainty label."""


class SortKeyError(ScreenerError):
    """A sort column outside the allowlist."""


class MixedEstimateAxisError(ScreenerError):
    """Descriptive and calibrated estimates asked to share one sort axis."""


class MachineAuthorityRefused(ScreenerError):
    """A consumer identity that would read this research tier as authority."""


class DeterminismError(ScreenerError):
    """The row set has no total order, so pagination could not be stable."""


class TierDeclarationError(ScreenerError):
    """The module's tier declaration was mutated away from ``research``."""


class LookaheadError(ScreenerError):
    """An input is dated AFTER the asof it is being disclosed against."""


# --- invariants -------------------------------------------------------------


def assert_research_tier_intact() -> None:
    """Refuse if the module tier declaration no longer says what it declares.

    Every surface that stamps ``tier`` / ``is_calibrated_screener`` on a payload
    calls this first, so the artifact-level flag and the row-level flag can never
    disagree: a reassignment fails the request rather than upgrading the claim.
    """
    if TIER != _DECLARED_TIER or IS_CALIBRATED_SCREENER is not _DECLARED_IS_CALIBRATED_SCREENER:
        raise TierDeclarationError(
            f"tier declaration was mutated: TIER={TIER!r} "
            f"IS_CALIBRATED_SCREENER={IS_CALIBRATED_SCREENER!r}; this artifact is "
            f"{_DECLARED_TIER!r} and is not a calibrated screener. Refusing to serve a "
            "payload whose artifact-level flag contradicts its own rows."
        )


def _is_missing(value: object) -> bool:
    """A disclosure is missing when it is absent OR empty.

    ``is None`` alone is not enough: ``evidence_label=""`` and ``multiplicity={}``
    are absences dressed as values, and testing only for ``None`` counts them as
    complete disclosure.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (Mapping, list, tuple, set, frozenset)):
        return len(value) == 0
    return False


def _is_nan(value: float) -> bool:
    return value != value  # noqa: PLR0124 - the NaN identity


def _is_calendar_date(value: object) -> bool:
    """A calendar date and NOT a ``datetime``.

    ``datetime`` subclasses ``date``, so an ``isinstance`` check alone lets a
    timestamp through anywhere a trading day is meant — and two requests for the
    same day then carry different keys and different serialised asof strings.
    """
    return isinstance(value, date) and not isinstance(value, datetime)


# --- small statistics -------------------------------------------------------


def wilson_interval(successes: int, n: int, *, level: float = 0.90) -> tuple[float, float]:
    """Wilson score interval for a binomial rate — a PARAMETER CI, nothing more.

    It covers the unknown historical up-rate.  It says nothing about the next
    occurrence, which is why every row that carries it must declare
    ``uncertainty_semantics="parameter_ci"`` rather than a generic label.
    """
    if isinstance(successes, bool) or not isinstance(successes, int):
        raise ScreenerError("successes must be an int")
    if isinstance(n, bool) or not isinstance(n, int):
        raise ScreenerError("n must be an int")
    if n <= 0:
        raise ScreenerError("n must be positive — an interval over zero years is not an interval")
    if not 0 <= successes <= n:
        raise ScreenerError(f"successes {successes} outside [0, {n}]")
    if not 0.0 < level < 1.0:
        raise ScreenerError("level must be in (0, 1)")

    # Two-sided normal quantile via the inverse error function.
    z = math.sqrt(2.0) * _erfinv(level)
    p = successes / n
    denominator = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = (z / denominator) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def _erfinv(x: float) -> float:
    """Inverse error function by Newton refinement on a Winitzki seed."""
    if not -1.0 < x < 1.0:
        raise ScreenerError("erfinv domain is (-1, 1)")
    a = 0.147
    # Defensive, and UNREACHABLE on IEEE-754 doubles: for every representable
    # x in (-1, 1), x*x rounds strictly below 1.0, so `tail` stays positive
    # (checked down to the 60 doubles below 1.0 — smallest tail ~1.3e-14). It
    # stays because `math.log(0.0)` would otherwise raise a bare ValueError from
    # inside a statistics helper rather than this module's own refusal, and the
    # rounding that saves it is a property of the platform's float type, not of
    # anything this module controls. No test can drive this branch.
    tail = 1.0 - x * x
    if tail <= 0.0:
        raise ScreenerError(
            f"erfinv({x!r}) saturates in double precision — pick a level further from 0 or 1"
        )
    ln = math.log(tail)
    term = 2 / (math.pi * a) + ln / 2
    guess = math.copysign(math.sqrt(math.sqrt(term * term - ln / a) - term), x)
    for _ in range(4):
        error = math.erf(guess) - x
        guess -= error / (2 / math.sqrt(math.pi) * math.exp(-guess * guess))
    return guess


# --- disclosure blocks ------------------------------------------------------


def program_multiplicity(
    *,
    symbols_searched: int,
    windows_per_symbol: int,
    family_id: str,
    correction: str,
    note: str | None = None,
) -> dict:
    """The PROGRAM-level selection disclosure carried by every result set.

    The per-symbol window family prices its own 2,645-window scan.  It does not
    know that a reader is now looking across N symbols, so the cross-symbol
    budget is disclosed here as a rate rather than corrected away.
    """
    if symbols_searched <= 0 or windows_per_symbol <= 0:
        raise ScreenerError("a program budget with no hypotheses in it is not a budget")
    return {
        "scope": "program_level",
        "family_id": str(family_id),
        "symbols_searched": int(symbols_searched),
        "windows_per_symbol": int(windows_per_symbol),
        "hypotheses_total": int(symbols_searched) * int(windows_per_symbol),
        "within_symbol_correction": str(correction),
        "across_symbol_correction": "disclosed_as_program_level_rate_not_corrected_away",
        "note": note
        or (
            "Browsing across symbols spends a budget the per-symbol family does not "
            "count. The rate above is the honest size of the search behind this page."
        ),
    }


def exploratory_budget(
    *,
    filter_name: str,
    rows_considered: int,
    rows_kept: int,
    note: str | None = None,
) -> dict:
    """A NEW budget for a cohort or filter the reader composed.

    A user-composed cut is a fresh search.  It cannot inherit the evidence label,
    p-value, or calibration claim of the rows it selected from, so
    :func:`mark_exploratory` strips those and attaches this instead.
    """
    if rows_considered <= 0:
        raise ScreenerError("an exploratory cut over nothing is not a cut")
    return {
        "scope": "user_composed_exploratory",
        "filter_name": str(filter_name),
        "rows_considered": int(rows_considered),
        "rows_kept": int(rows_kept),
        "inherits_program_budget": False,
        "inherited_claim_stripped": True,
        "note": note
        or (
            "You composed this cut after seeing the rows, which spends testing budget "
            "nothing here has counted. The evidence label and p-value from the "
            "unfiltered rows do not carry over and have been removed."
        ),
    }


def costs_disclosure(
    *,
    round_trip_cost_bps: float,
    borrow_cost_included: bool,
    slippage_model: str,
    applied_to_estimate: bool,
) -> dict:
    """What a reader would pay to act on the row, and whether it is netted out."""
    if round_trip_cost_bps < 0:
        raise ScreenerError("round_trip_cost_bps cannot be negative")
    return {
        "round_trip_cost_bps": float(round_trip_cost_bps),
        "borrow_cost_included": bool(borrow_cost_included),
        "slippage_model": str(slippage_model),
        "applied_to_estimate": bool(applied_to_estimate),
    }


def freshness_disclosure(*, artifact_asof: date, asof: date, stale_after_days: int = 7) -> dict:
    """How old the numbers behind the row are, in days, and whether that is stale.

    An artifact dated AFTER ``asof`` is lookahead by construction.  Without the
    sign guard it produced a negative age that read as maximally fresh — and
    ``freshness_age_days`` is a sortable column, so future-dated rows would sort
    to the top of "freshest first".
    """
    if not _is_calendar_date(artifact_asof) or not _is_calendar_date(asof):
        raise ScreenerError(
            "freshness needs two calendar dates (a datetime is not one — it makes two "
            "reads of the same trading day disagree)"
        )
    age = (asof - artifact_asof).days
    if age < 0:
        raise LookaheadError(
            f"artifact_asof {artifact_asof.isoformat()} is AFTER asof {asof.isoformat()}: "
            f"an artifact from the future is lookahead, not fresh ({age} days)"
        )
    return {
        "artifact_asof": artifact_asof.isoformat(),
        "asof": asof.isoformat(),
        "age_days": age,
        "stale": age > stale_after_days,
        "stale_after_days": int(stale_after_days),
    }


def assert_uncertainty_semantics(label: object) -> str:
    """Return ``label`` if it names one of the three typed semantics, else raise."""
    if not isinstance(label, str) or not label:
        raise UncertaintySemanticsError(
            "uncertainty_semantics must be one of "
            f"{list(UNCERTAINTY_SEMANTICS)}; got {label!r}"
        )
    if label in UNCERTAINTY_SEMANTICS:
        return label
    if label.strip().lower().replace(" ", "_") in FORBIDDEN_UNCERTAINTY_LABELS:
        raise UncertaintySemanticsError(
            f"{label!r} is a generic uncertainty label and is forbidden: it hides whether "
            "the number covers the unknown rate (parameter_ci), the next observation "
            "(predictive_interval), or the realised spread (outcome_quantiles). "
            f"Declare one of {list(UNCERTAINTY_SEMANTICS)}."
        )
    raise UncertaintySemanticsError(
        f"unknown uncertainty_semantics {label!r}; expected one of {list(UNCERTAINTY_SEMANTICS)}"
    )


def assert_evidence_label(label: object, estimate_type: str) -> str:
    """Return ``label`` if it is on this leg's allowlist, else raise.

    An evidence label is a CLAIM in one word.  Free text here is how "validated",
    "STRONG BUY", or "tradeable_edge" reach a reader from a research-tier browser:
    the site-side CI guard on the word "validated" reads templates, never an API
    body, so this surface is the only place that can refuse it.
    """
    if estimate_type not in ESTIMATE_TYPES:
        raise ScreenerError(f"unknown estimate_type {estimate_type!r}")
    permitted = _LEG_EVIDENCE_LABELS[estimate_type]
    if not isinstance(label, str) or not label.strip():
        raise ScreenerError(
            f"evidence_label must be one of {list(permitted)}; got {label!r}"
        )
    if label in permitted:
        return label
    if label in EVIDENCE_LABELS:
        raise ScreenerError(
            f"evidence_label {label!r} belongs to the other estimate leg; a "
            f"{estimate_type} row may only carry one of {list(permitted)}"
        )
    raise ScreenerError(
        f"evidence_label {label!r} is not on the allowlist {list(permitted)}. "
        "This artifact has no out-of-sample record, so it cannot label anything "
        "validated, strong, or tradeable — the label says what the evidence IS."
    )


def assert_consumer_permitted(consumer: object) -> str:
    """Refuse machine-authority consumers BY NAME; fail closed on unknown ones."""
    if not isinstance(consumer, str) or not consumer.strip():
        raise MachineAuthorityRefused(
            f"{UNKNOWN_CONSUMER_REFUSAL}: consumer identity is required, got {consumer!r}"
        )
    identity = consumer
    # Folded for MATCHING only — the refusal still names the identity verbatim.
    # Whitespace folds to `_` so "neural web ingest" is refused BY NAME rather
    # than landing in the anonymous "unknown consumer" bucket, which is the whole
    # point of the by-name rule: the log must say which system asked.
    folded = identity.lower().replace("-", "_").replace(" ", "_")
    for token in MACHINE_AUTHORITY_TOKENS:
        if token.replace("-", "_") in folded:
            raise MachineAuthorityRefused(
                f"{MACHINE_AUTHORITY_REFUSAL}: consumer {identity!r} matched {token!r}. "
                "This artifact is research tier — it may not rank, gate, size, or score. "
                "Synapse declares no machine consumer for it, so there is nothing to wire."
            )
    if any(character.isspace() for character in identity):
        # Refused rather than trimmed: a padded or newline-bearing identity would
        # otherwise be normalised into a permitted one and then travel verbatim
        # into the `consumer` payload field and every log line, where an embedded
        # newline forges a log record.
        raise MachineAuthorityRefused(
            f"{UNKNOWN_CONSUMER_REFUSAL}: consumer identity {consumer!r} carries whitespace; "
            "identities are matched exactly, never trimmed"
        )
    if identity not in PERMITTED_CONSUMERS:
        raise MachineAuthorityRefused(
            f"{UNKNOWN_CONSUMER_REFUSAL}: consumer {identity!r} is not one of "
            f"{sorted(PERMITTED_CONSUMERS)}"
        )
    return identity


# --- universe ---------------------------------------------------------------


@dataclass(frozen=True)
class UniverseDisclosure:
    """What the row set's membership actually is — never a silent assumption."""

    asof: date
    basis: str
    point_in_time_available: bool
    survivorship_biased: bool
    note: str
    unavailable_reason: str | None = None
    snapshot_date: date | None = None
    resolver: str = "default_unavailable"

    def __post_init__(self) -> None:
        if self.basis not in (UNIVERSE_POINT_IN_TIME, UNIVERSE_CURRENT_VINTAGE):
            raise ScreenerError(f"unknown universe basis {self.basis!r}")
        if self.point_in_time_available and self.basis != UNIVERSE_POINT_IN_TIME:
            raise ScreenerError("a point-in-time read must declare the point_in_time basis")
        if not self.point_in_time_available and not self.unavailable_reason:
            raise ScreenerError("a non-point-in-time universe must state why")
        if not self.point_in_time_available and not self.survivorship_biased:
            raise ScreenerError(
                "today's roster read backwards IS survivorship biased — refusing to say otherwise"
            )
        if not _is_calendar_date(self.asof):
            raise ScreenerError("universe asof must be a calendar date")
        if self.snapshot_date is not None:
            # Enforced on the INSTANCE, not only in the resolver, so a caller that
            # constructs the disclosure directly cannot hand `as_dict()` a string
            # (which used to die with a bare AttributeError at serialisation time)
            # or a snapshot dated after the asof it claims to describe.
            if not _is_calendar_date(self.snapshot_date):
                raise ScreenerError(
                    f"snapshot_date must be a calendar date; got {self.snapshot_date!r}"
                )
            if self.snapshot_date > self.asof:
                raise LookaheadError(
                    f"snapshot_date {self.snapshot_date.isoformat()} is after asof "
                    f"{self.asof.isoformat()} — membership cannot be read from the future"
                )
        if self.point_in_time_available and self.snapshot_date is None:
            raise ScreenerError(
                "a point-in-time membership claim must name the snapshot it read; "
                "an unnamed one cannot be checked and is not point-in-time"
            )

    def as_dict(self) -> dict:
        return {
            "asof": self.asof.isoformat(),
            "basis": self.basis,
            "point_in_time_available": self.point_in_time_available,
            "survivorship_biased": self.survivorship_biased,
            "note": self.note,
            "unavailable_reason": self.unavailable_reason,
            "snapshot_date": self.snapshot_date.isoformat() if self.snapshot_date else None,
            "resolver": self.resolver,
        }


def unavailable_membership_resolver(asof: date) -> dict:
    """The DEFAULT resolver: point-in-time membership is not available."""
    return {"available": False, "unavailable_reason": NO_RESOLVER_REASON}


def universe_membership_resolver(asof: date, *, root) -> dict:
    """Adapt :mod:`engine.seasonality.universe` into a resolver payload.

    Imported lazily so this module stays importable on a thin runner, and so a
    branch where ``universe`` has not landed yet degrades to the default
    resolver instead of failing at import.
    """
    try:
        from . import universe as universe_module
    except ImportError:  # pragma: no cover - defensive; the module is on this branch
        return {"available": False, "unavailable_reason": "universe_module_absent"}
    read = universe_module.membership_asof(asof, root=root)
    if not read.available:
        return {
            "available": False,
            "unavailable_reason": read.unavailable_reason or "membership_unavailable",
        }
    return {
        "available": True,
        "snapshot_date": read.snapshot_date,
        "members": tuple((read.security or {}).get("members") or ()),
    }


def _resolver_name(resolver: Callable) -> str:
    """A resolver's name for provenance, seeing THROUGH a ``functools.partial``.

    ``partial`` objects have no ``__name__``, so the class-name fallback recorded
    every one of them as ``"partial"`` — which destroys the provenance the field
    exists to carry.
    """
    seen = 0
    current = resolver
    while hasattr(current, "func") and not hasattr(current, "__name__") and seen < 8:
        current = current.func
        seen += 1
    name = getattr(current, "__name__", None)
    if name:
        return f"partial({name})" if seen else name
    return type(resolver).__name__


def resolve_universe(
    asof: date,
    *,
    membership_resolver: Callable[[date], Mapping] | None = None,
) -> UniverseDisclosure:
    """Resolve membership, disclosing survivorship bias when it is not point-in-time.

    Never silently substitutes today's roster for history: an unavailable read
    downgrades the BASIS and says so in plain words.

    The resolver is an INJECTED trust boundary, so ``available: True`` is checked,
    not believed.  A point-in-time claim must name the snapshot it read, that
    snapshot must be at or before ``asof`` (a later one is tomorrow's roster read
    into the past — the exact survivorship lie the disclosure exists to prevent),
    and it must actually contain members.  Anything else is DOWNGRADED to the
    current-vintage basis with the failure named, rather than stamped
    ``survivorship_biased=False``.
    """
    resolver = membership_resolver or unavailable_membership_resolver
    name = _resolver_name(resolver)
    answer = resolver(asof)
    if not isinstance(answer, Mapping):
        raise ScreenerError("a membership resolver must return a mapping")
    unavailable_reason = answer.get("unavailable_reason")
    if answer.get("available"):
        snapshot_date = answer.get("snapshot_date")
        members = answer.get("members")
        if not _is_calendar_date(snapshot_date):
            unavailable_reason = (
                "point_in_time_claim_without_a_usable_snapshot_date:"
                f"{type(snapshot_date).__name__}"
            )
        elif snapshot_date > asof:
            raise LookaheadError(
                f"membership snapshot {snapshot_date.isoformat()} is AFTER asof "
                f"{asof.isoformat()}: that is a future roster read backwards, which is "
                "the survivorship bias this disclosure exists to refuse"
            )
        elif _is_missing(members):
            unavailable_reason = "point_in_time_snapshot_resolved_no_members"
        else:
            return UniverseDisclosure(
                asof=asof,
                basis=UNIVERSE_POINT_IN_TIME,
                point_in_time_available=True,
                survivorship_biased=False,
                note="Membership resolved point-in-time from the identity snapshot store.",
                snapshot_date=snapshot_date,
                resolver=name,
            )
        answer = {"available": False, "unavailable_reason": unavailable_reason}
    return UniverseDisclosure(
        asof=asof,
        basis=UNIVERSE_CURRENT_VINTAGE,
        point_in_time_available=False,
        survivorship_biased=True,
        note=CURRENT_VINTAGE_NOTE,
        unavailable_reason=str(answer.get("unavailable_reason") or NO_RESOLVER_REASON),
        resolver=name,
    )


# --- the row ----------------------------------------------------------------

#: Disclosure every non-abstaining row must supply. A row that cannot fill one of
#: these ABSTAINS (naming what was missing) rather than dropping the field.
COMMON_REQUIRED_FIELDS = (
    "estimate_type",
    "uncertainty_semantics",
    "uncertainty_low",
    "uncertainty_high",
    "uncertainty_level",
    "sample_size",
    "issuer_count",
    "date_cluster_count",
    "search_family",
    "family_size",
    "multiplicity",
    "costs",
    "oos_epoch",
    "freshness",
    "extrapolation",
)
#: Claim fields an evidence-bearing row must carry — and that an exploratory row
#: must NOT, because a user-composed cut inherits neither.
CLAIM_FIELDS = ("family_adjusted_p_value", "evidence_label")


def required_fields(estimate_type: str, *, exploratory: bool) -> tuple[str, ...]:
    """The complete disclosure contract for one row shape."""
    if estimate_type not in ESTIMATE_TYPES:
        raise ScreenerError(f"unknown estimate_type {estimate_type!r}")
    fields = COMMON_REQUIRED_FIELDS + _LEG_FIELDS[estimate_type]
    if not exploratory:
        fields += CLAIM_FIELDS
    return fields


@dataclass(frozen=True)
class ResearchRow:
    """One symbol-window row of the research browser.

    Constructed through :func:`build_row`, which turns a missing disclosure into
    an abstention rather than a hole.  The invariants here are enforced on every
    instance, so an incomplete row cannot exist even if a caller bypasses the
    builder.
    """

    row_id: str
    symbol: str
    window_start_doy: int
    window_end_doy: int
    estimate_type: str

    historical_up_share: float | None = None
    historical_up_share_baseline: float | None = None
    historical_up_share_edge: float | None = None

    calibrated_probability: float | None = None
    calibrated_probability_baseline: float | None = None
    calibrated_probability_edge: float | None = None
    calibration_reference: str | None = None

    uncertainty_semantics: str | None = None
    uncertainty_low: float | None = None
    uncertainty_high: float | None = None
    uncertainty_level: float | None = None

    sample_size: int | None = None
    issuer_count: int | None = None
    date_cluster_count: int | None = None

    search_family: str | None = None
    family_size: int | None = None
    multiplicity: dict | None = None
    family_adjusted_p_value: float | None = None
    evidence_label: str | None = None

    costs: dict | None = None
    oos_epoch: str | None = None
    freshness: dict | None = None
    extrapolation: bool | None = None
    extrapolation_reason: str | None = None

    exploratory: bool = False
    exploratory_budget: dict | None = None
    abstained: bool = False
    abstention_reason: str | None = None

    schema: str = RESEARCH_ROW_SCHEMA
    tier: str = TIER
    is_calibrated_screener: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not _SYMBOL.match(self.symbol):
            raise ScreenerError(f"symbol {self.symbol!r} is not a usable identity")
        if not isinstance(self.row_id, str) or not self.row_id:
            raise ScreenerError("row_id is required — it is part of the total order")
        if self.estimate_type not in ESTIMATE_TYPES:
            raise ScreenerError(
                f"estimate_type must be one of {sorted(ESTIMATE_TYPES)}; got {self.estimate_type!r}"
            )
        if self.tier != TIER or self.is_calibrated_screener is not False:
            raise ScreenerError("a row on this artifact is research tier and is not calibrated")
        if not (1 <= int(self.window_start_doy) < int(self.window_end_doy) <= 365):
            raise ScreenerError(
                f"window ({self.window_start_doy}, {self.window_end_doy}) is not a 1-based no-wrap window"
            )

        # Typed uncertainty is checked even on an abstaining row: a generic label
        # is a schema defect, not a data gap, and must surface either way.
        if self.uncertainty_semantics is not None:
            assert_uncertainty_semantics(self.uncertainty_semantics)

        # The two legs never coexist. This is what keeps a description from being
        # read as a forecast — not the docstring.
        other_leg = (
            CALIBRATED_FIELDS if self.estimate_type == ESTIMATE_DESCRIPTIVE else DESCRIPTIVE_FIELDS
        )
        populated = [name for name in other_leg if getattr(self, name) is not None]
        if populated:
            raise ScreenerError(
                f"a {self.estimate_type} row must leave {populated} empty — descriptive and "
                "calibrated estimates are separately named fields and never share one"
            )
        if self.estimate_type == ESTIMATE_DESCRIPTIVE and self.calibration_reference is not None:
            raise ScreenerError("a descriptive row has no calibration to reference")
        if self.estimate_type == ESTIMATE_CALIBRATED:
            if _is_missing(self.calibration_reference):
                raise ScreenerError(
                    "a calibrated row must name the graded out-of-sample epoch it rests on"
                )
            # The reference used to be truthiness-checked only, and `oos_epoch` was
            # a free string — so a historical up-share could be served under
            # `calibrated_probability` with `calibration_reference="trust_me_bro"`.
            # The reference must POINT AT the epoch the row declares.
            if self.oos_epoch is not None:
                if self.oos_epoch == OOS_EPOCH_NONE:
                    raise ScreenerError(
                        f"a calibrated row cannot declare oos_epoch={OOS_EPOCH_NONE!r}: "
                        "a calibration with no matured grades behind it is not a calibration"
                    )
                if str(self.oos_epoch) not in str(self.calibration_reference):
                    raise ScreenerError(
                        f"calibration_reference {self.calibration_reference!r} does not name "
                        f"the declared oos_epoch {self.oos_epoch!r}; an unreferenced calibration "
                        "claim is indistinguishable from a relabelled historical rate"
                    )
        if not _is_missing(self.evidence_label):
            assert_evidence_label(self.evidence_label, self.estimate_type)

        if self.exploratory:
            if self.exploratory_budget is None:
                raise ScreenerError("an exploratory row must carry the new budget it spent")
            inherited = [name for name in CLAIM_FIELDS if getattr(self, name) is not None]
            if inherited:
                raise ScreenerError(
                    f"an exploratory row may not inherit {inherited} from the rows it was cut from"
                )
            if self.estimate_type == ESTIMATE_CALIBRATED:
                raise ScreenerError("a user-composed cut cannot inherit a calibration claim")

        if self.abstained:
            if not self.abstention_reason:
                raise ScreenerError("an abstaining row must state why it abstained")
            return

        missing = [
            name
            for name in required_fields(self.estimate_type, exploratory=self.exploratory)
            # `_is_missing`, not `is None`: `evidence_label=""` and `multiplicity={}`
            # are absences dressed as values and used to count as complete disclosure.
            if _is_missing(getattr(self, name))
        ]
        if missing:
            raise ScreenerError(
                f"row {self.row_id!r} is missing {missing} and did not abstain — "
                "use build_row(), which converts a missing disclosure into an abstention"
            )
        if self.extrapolation and not self.extrapolation_reason:
            raise ScreenerError("an extrapolating row must say what it extrapolated past")

    # -- views --

    @property
    def freshness_age_days(self) -> int | None:
        """Sortable projection of ``freshness``. A sortable column that resolved to
        ``None`` for every row would sort nothing while looking like it sorted."""
        if not self.freshness:
            return None
        value = self.freshness.get("age_days")
        return None if value is None else int(value)

    @property
    def round_trip_cost_bps(self) -> float | None:
        """Sortable projection of ``costs``."""
        if not self.costs:
            return None
        value = self.costs.get("round_trip_cost_bps")
        return None if value is None else float(value)

    @property
    def identity(self) -> tuple:
        """The unique total-order key. Pagination determinism rests on this."""
        return (self.symbol, int(self.window_start_doy), int(self.window_end_doy), self.row_id)

    def as_dict(self) -> dict:
        return {
            "schema": self.schema,
            "tier": self.tier,
            "is_calibrated_screener": self.is_calibrated_screener,
            "row_id": self.row_id,
            "symbol": self.symbol,
            "window_start_doy": self.window_start_doy,
            "window_end_doy": self.window_end_doy,
            "estimate_type": self.estimate_type,
            "historical_up_share": self.historical_up_share,
            "historical_up_share_baseline": self.historical_up_share_baseline,
            "historical_up_share_edge": self.historical_up_share_edge,
            "calibrated_probability": self.calibrated_probability,
            "calibrated_probability_baseline": self.calibrated_probability_baseline,
            "calibrated_probability_edge": self.calibrated_probability_edge,
            "calibration_reference": self.calibration_reference,
            "uncertainty_semantics": self.uncertainty_semantics,
            "uncertainty_low": self.uncertainty_low,
            "uncertainty_high": self.uncertainty_high,
            "uncertainty_level": self.uncertainty_level,
            "sample_size": self.sample_size,
            "issuer_count": self.issuer_count,
            "date_cluster_count": self.date_cluster_count,
            "search_family": self.search_family,
            "family_size": self.family_size,
            "multiplicity": dict(self.multiplicity) if self.multiplicity else None,
            "family_adjusted_p_value": self.family_adjusted_p_value,
            "evidence_label": self.evidence_label,
            "costs": dict(self.costs) if self.costs else None,
            "oos_epoch": self.oos_epoch,
            "freshness": dict(self.freshness) if self.freshness else None,
            "extrapolation": self.extrapolation,
            "extrapolation_reason": self.extrapolation_reason,
            "exploratory": self.exploratory,
            "exploratory_budget": dict(self.exploratory_budget) if self.exploratory_budget else None,
            "abstained": self.abstained,
            "abstention_reason": self.abstention_reason,
        }


def build_row(**fields) -> ResearchRow:
    """Build a row, ABSTAINING (with the field names) when disclosure is missing.

    Schema defects — a generic uncertainty label, a mixed estimate leg, a
    calibrated claim with no graded epoch — still raise.  Only a genuine data gap
    becomes an abstention, and the abstention names the gap.
    """
    fields.setdefault("estimate_type", ESTIMATE_DESCRIPTIVE)
    exploratory = bool(fields.get("exploratory"))
    estimate_type = fields["estimate_type"]
    if estimate_type not in ESTIMATE_TYPES:
        raise ScreenerError(f"unknown estimate_type {estimate_type!r}")

    if not fields.get("abstained"):
        missing = [
            name
            for name in required_fields(estimate_type, exploratory=exploratory)
            if _is_missing(fields.get(name))
        ]
        if missing:
            fields["abstained"] = True
            fields["abstention_reason"] = "missing_disclosure:" + ",".join(sorted(missing))
    return ResearchRow(**fields)


def descriptive_row(
    *,
    row_id: str,
    symbol: str,
    window_start_doy: int,
    window_end_doy: int,
    up_years: int,
    n_years: int,
    baseline_up_share: float,
    issuer_count: int,
    date_cluster_count: int,
    search_family: str,
    family_size: int,
    multiplicity: Mapping,
    family_adjusted_p_value: float,
    evidence_label: str,
    costs: Mapping,
    freshness: Mapping,
    oos_epoch: str = OOS_EPOCH_NONE,
    extrapolation: bool = False,
    extrapolation_reason: str | None = None,
    ci_level: float = 0.90,
) -> ResearchRow:
    """A descriptive row: historical up-share + Wilson PARAMETER CI.

    This is a description of complete past years.  It is not a forecast, and the
    field names say so.
    """
    share = up_years / n_years if n_years else None
    low, high = wilson_interval(up_years, n_years, level=ci_level) if n_years else (None, None)
    return build_row(
        row_id=row_id,
        symbol=symbol,
        window_start_doy=window_start_doy,
        window_end_doy=window_end_doy,
        estimate_type=ESTIMATE_DESCRIPTIVE,
        historical_up_share=None if share is None else round(share, 6),
        historical_up_share_baseline=round(float(baseline_up_share), 6),
        historical_up_share_edge=(
            None if share is None else round(share - float(baseline_up_share), 6)
        ),
        uncertainty_semantics="parameter_ci",
        uncertainty_low=None if low is None else round(low, 6),
        uncertainty_high=None if high is None else round(high, 6),
        uncertainty_level=ci_level,
        sample_size=n_years,
        issuer_count=issuer_count,
        date_cluster_count=date_cluster_count,
        search_family=search_family,
        family_size=family_size,
        multiplicity=dict(multiplicity),
        family_adjusted_p_value=family_adjusted_p_value,
        evidence_label=evidence_label,
        costs=dict(costs),
        oos_epoch=oos_epoch,
        freshness=dict(freshness),
        extrapolation=extrapolation,
        extrapolation_reason=extrapolation_reason,
    )


#: The multiplicity block a user-composed row carries INSTEAD of the program one.
#: A cut whose own budget declares ``inherits_program_budget: False`` may not also
#: carry a block whose ``scope`` reads ``program_level`` — the row would then
#: assert and disclaim the same inheritance in two adjacent fields.
EXPLORATORY_MULTIPLICITY_SCOPE = "user_composed_exploratory"


def _exploratory_multiplicity(inherited: Mapping | None) -> dict:
    return {
        "scope": EXPLORATORY_MULTIPLICITY_SCOPE,
        "corrected_for_this_cut": False,
        "inherited_program_multiplicity": dict(inherited) if inherited else None,
        "note": (
            "The block below prices the search that produced the rows you cut FROM. "
            "It does not price this cut, which you composed after seeing them, and "
            "nothing here has counted that."
        ),
    }


def _chain_budget(budget: Mapping, prior: Mapping | None) -> dict:
    """Accumulate successive cuts instead of overwriting the previous budget.

    A second filter over already-exploratory rows used to REPLACE the first cut's
    budget, so a reader who spent two cuts over 3 rows saw one 2-row cut
    disclosed — the understatement this whole block exists to prevent.
    """
    chained = dict(budget)
    history = []
    if prior:
        history = [dict(entry) for entry in (prior.get("prior_cuts") or ())]
        history.append({key: value for key, value in prior.items() if key != "prior_cuts"})
    chained["prior_cuts"] = history
    chained["cuts_applied"] = len(history) + 1
    chained["rows_considered_cumulative"] = int(chained.get("rows_considered") or 0) + sum(
        int(entry.get("rows_considered") or 0) for entry in history
    )
    return chained


def mark_exploratory(row: ResearchRow, *, budget: Mapping) -> ResearchRow:
    """Re-label a row as user-composed, STRIPPING every inherited claim.

    The p-value and evidence label belonged to the unfiltered family.  A cut the
    reader composed after seeing the rows spends a budget nothing counted, so
    those claims do not travel with it — and neither does the PROGRAM-level
    multiplicity block, which is demoted to provenance so the row cannot disclaim
    inheritance in one field while carrying it in the next.
    """
    return replace(
        row,
        exploratory=True,
        exploratory_budget=_chain_budget(budget, row.exploratory_budget),
        multiplicity=_exploratory_multiplicity(row.multiplicity),
        family_adjusted_p_value=None,
        evidence_label=None,
    )


def apply_user_filter(
    rows: Sequence[ResearchRow],
    *,
    filter_name: str,
    predicate: Callable[[ResearchRow], bool],
    note: str | None = None,
) -> list[ResearchRow]:
    """Apply a reader-composed cohort/filter and label the result exploratory.

    Filtering an EMPTY set is not a cut — there was no budget to spend — so it
    returns an empty cohort rather than raising into the caller's request path.
    """
    rows = list(rows)
    if not rows:
        return []
    kept = [row for row in rows if predicate(row)]
    budget = exploratory_budget(
        filter_name=filter_name,
        rows_considered=len(rows),
        rows_kept=len(kept),
        note=note,
    )
    return [mark_exploratory(row, budget=budget) for row in kept]


# --- ordering: the reader sorts; the engine has no opinion -------------------


def _column_value(row: ResearchRow, column: str):
    return getattr(row, column, None)


def order_rows(
    rows: Iterable[ResearchRow],
    *,
    sort_by: str | None = DEFAULT_SORT_BY,
    descending: bool = False,
) -> list[ResearchRow]:
    """Return rows in a DETERMINISTIC TOTAL ORDER.

    ``sort_by=None`` is identity order — an index, not a ranking.  Any other
    column must be on :data:`SORTABLE_COLUMNS`; the identity key is always
    appended as the tiebreaker, so two calls over an unchanged set produce the
    same sequence and page 2 can never repeat or skip a row.
    """
    ordered = sorted(rows, key=lambda row: row.identity)
    identities = [row.identity for row in ordered]
    if len(set(identities)) != len(identities):
        # Counted in one pass: `identities.count(key)` inside a comprehension over
        # `identities` is O(n^2), and this is a cross-symbol browser.
        seen: dict[tuple, int] = {}
        for key_ in identities:
            seen[key_] = seen.get(key_, 0) + 1
        duplicates = sorted(key_ for key_, count in seen.items() if count > 1)
        raise DeterminismError(
            f"rows share identity keys {duplicates}; without a unique total order "
            "pagination cannot be stable"
        )

    if sort_by is None:
        return ordered
    if sort_by not in SORTABLE_COLUMNS:
        raise SortKeyError(
            f"sort_by {sort_by!r} is not sortable; the allowlist is {list(SORTABLE_COLUMNS)}. "
            "There is no composite, 'best', or edge column — sorting here is the reader's "
            "choice, not an engine ranking, and a derived edge is a fused metric."
        )
    if sort_by in ESTIMATE_AXIS_COLUMNS:
        kinds = {row.estimate_type for row in ordered}
        if len(kinds) > 1:
            raise MixedEstimateAxisError(
                f"cannot sort {sorted(kinds)} rows by {sort_by!r}: descriptive and calibrated "
                "estimates answer different questions and are never placed on one axis. "
                "Group by estimate_type first."
            )
        # A column belonging to the OTHER leg resolves to None on every row: the
        # sort then silently no-ops while the payload reports a successful
        # user_selected_column_sort, and the reader reads an unchanged order as
        # "the data is flat". Refuse it on the same axis rule.
        column_leg = ESTIMATE_CALIBRATED if sort_by in CALIBRATED_FIELDS else ESTIMATE_DESCRIPTIVE
        foreign = sorted(kinds - {column_leg})
        if foreign:
            raise MixedEstimateAxisError(
                f"cannot sort {foreign} rows by {sort_by!r}: that column belongs to the "
                f"{column_leg} leg and is empty on every row here, so the sort would do "
                "nothing while reporting that it sorted. Group by estimate_type first."
            )

    if sort_by in _TEXT_COLUMNS:
        # `sorted` is stable, so the identity order above survives as the tiebreaker.
        ordered.sort(key=lambda row: str(_column_value(row, sort_by)), reverse=descending)
        return ordered

    sign = -1.0 if descending else 1.0

    def key(row: ResearchRow) -> tuple[int, float]:
        value = _column_value(row, sort_by)
        if value is None:
            # Missing values sort LAST in both directions — an abstention is not a
            # winner, and flipping the direction must not float it to the top.
            return (1, 0.0)
        numeric = float(value)
        if _is_nan(numeric):
            # NaN compares false against everything, so it neither sorts nor
            # raises: the page comes back deterministic (the identity pre-sort
            # fixes it) but NOT monotonic — wrong while looking right. It is the
            # same hazard as a missing value, so it gets the same answer.
            return (1, 0.0)
        return (0, sign * numeric)

    ordered.sort(key=key)
    return ordered


def group_by_estimate_type(rows: Iterable[ResearchRow]) -> dict[str, list[ResearchRow]]:
    """Split rows by estimate type — the supported way to show both at once."""
    grouped: dict[str, list[ResearchRow]] = {kind: [] for kind in sorted(ESTIMATE_TYPES)}
    for row in rows:
        grouped[row.estimate_type].append(row)
    return grouped


# --- the result set ---------------------------------------------------------


#: Keys the program-level multiplicity block must actually CARRY. Checking only
#: ``scope == "program_level"`` reduced the module's central epistemic promise to
#: one string: ``{"scope": "program_level"}`` disclosed a zero-hypothesis search
#: and was served verbatim.
PROGRAM_MULTIPLICITY_REQUIRED_KEYS = (
    "family_id",
    "symbols_searched",
    "windows_per_symbol",
    "hypotheses_total",
    "across_symbol_correction",
)


def assert_program_multiplicity(block: object, *, distinct_symbols: int = 0) -> dict:
    """Validate the program-level budget's CONTENT, not just its scope string.

    ``distinct_symbols`` is the number of distinct symbols actually in the result
    set: a budget claiming a search narrower than what it is disclosing is an
    understatement, which is the only direction that flatters the result.
    """
    if not isinstance(block, Mapping) or block.get("scope") != "program_level":
        raise ScreenerError(
            "a cross-symbol result set must carry the program-level multiplicity disclosure"
        )
    missing = [key for key in PROGRAM_MULTIPLICITY_REQUIRED_KEYS if _is_missing(block.get(key))]
    if missing:
        raise ScreenerError(
            f"the program-level multiplicity disclosure is missing {missing}: a scope "
            "string with no budget inside it discloses nothing"
        )
    try:
        symbols = int(block["symbols_searched"])
        windows = int(block["windows_per_symbol"])
        total = int(block["hypotheses_total"])
    except (TypeError, ValueError) as exc:
        raise ScreenerError("program multiplicity counts must be whole numbers") from exc
    if symbols <= 0 or windows <= 0:
        raise ScreenerError("a program budget with no hypotheses in it is not a budget")
    if total != symbols * windows:
        raise ScreenerError(
            f"program multiplicity does not add up: hypotheses_total {total} != "
            f"symbols_searched {symbols} x windows_per_symbol {windows}"
        )
    if symbols < distinct_symbols:
        raise ScreenerError(
            f"program multiplicity understates the search: symbols_searched {symbols} is "
            f"smaller than the {distinct_symbols} distinct symbols this result set is "
            "already showing"
        )
    return dict(block)


def _applicable_sortable_columns(kinds: set) -> list[str]:
    """The allowlist minus the columns that are empty on EVERY row present.

    ``sortable_columns`` is the full contract and stays whole; a UI that builds a
    sort control per column needs the shorter list, or it grows three "calibrated
    probability" controls on a set where no row can ever be calibrated.
    """
    inapplicable: set[str] = set()
    if ESTIMATE_CALIBRATED not in kinds:
        inapplicable |= set(CALIBRATED_FIELDS)
    if ESTIMATE_DESCRIPTIVE not in kinds:
        inapplicable |= set(DESCRIPTIVE_FIELDS)
    return [column for column in SORTABLE_COLUMNS if column not in inapplicable]


def _sample_disclosure(rows: Sequence[ResearchRow], sort_by: str | None) -> dict | None:
    """Say out loud that a rate sort is not weighted by how many years made it."""
    if sort_by not in ESTIMATE_AXIS_COLUMNS:
        return None
    samples = [row.sample_size for row in rows if row.sample_size is not None]
    return {
        "sample_weighted": False,
        "min_sample_size": min(samples) if samples else None,
        "max_sample_size": max(samples) if samples else None,
        "note": (
            "Sorting by a rate does not weight it by how many years produced it: a "
            "window with one complete year can sit above one with twenty-five. Read "
            "sample_size and the interval on every row before comparing them."
        ),
    }


def build_result_set(
    *,
    asof: date,
    rows: Sequence[ResearchRow],
    consumer: str,
    multiplicity: Mapping,
    universe: UniverseDisclosure,
    sort_by: str | None = DEFAULT_SORT_BY,
    descending: bool = False,
) -> dict:
    """The one result-set payload — used identically by the API and the UI."""
    assert_research_tier_intact()
    identity = assert_consumer_permitted(consumer)
    if not isinstance(universe, UniverseDisclosure):
        raise ScreenerError("universe must be a UniverseDisclosure — membership is never assumed")
    if not _is_calendar_date(asof):
        raise ScreenerError("asof must be a calendar date")
    if universe.asof != asof:
        raise ScreenerError(
            f"universe disclosure is asof {universe.asof.isoformat()} but this result set "
            f"claims {asof.isoformat()}: the membership a page rests on must be the "
            "membership the page says it rests on"
        )

    ordered = order_rows(rows, sort_by=sort_by, descending=descending)
    kinds = {row.estimate_type for row in ordered}
    if ESTIMATE_CALIBRATED in kinds:
        # The artifact stamps `is_calibrated_screener: False` and names
        # `forward_ledger_has_zero_matured_grades` as the blocker. A calibrated row
        # inside it makes `counts.estimate_types` say "calibrated" while the
        # envelope says the artifact is not calibrated — the payload contradicting
        # itself is exactly the confusion the separate legs exist to prevent.
        raise ScreenerError(
            "this result set declares is_calibrated_screener=False and "
            f"{OOS_EPOCH_NONE!r}; it may not carry calibrated rows. Serve them from an "
            "artifact that has a graded out-of-sample epoch behind it."
        )
    block = assert_program_multiplicity(
        multiplicity, distinct_symbols=len({row.symbol for row in ordered})
    )
    exploratory_rows = [row for row in ordered if row.exploratory]
    return {
        "schema": RESEARCH_BROWSER_SCHEMA,
        "tier": TIER,
        "is_calibrated_screener": IS_CALIBRATED_SCREENER,
        "not_calibrated_reason": NOT_CALIBRATED_REASON,
        "not_calibrated_blockers": list(NOT_CALIBRATED_BLOCKERS),
        "asof": asof.isoformat(),
        "consumer": identity,
        "universe": universe.as_dict(),
        "multiplicity": block,
        "ordering": {
            "sort_by": sort_by,
            "descending": bool(descending),
            "is_engine_ranking": False,
            "meaning": IDENTITY_ORDER_LABEL if sort_by is None else "user_selected_column_sort",
            "sortable_columns": list(SORTABLE_COLUMNS),
            "sortable_columns_applicable": _applicable_sortable_columns(kinds),
            "disclosure_only_columns": sorted(FUSED_DISCLOSURE_ONLY_COLUMNS),
            "sample_disclosure": _sample_disclosure(ordered, sort_by),
            "tiebreaker": ["symbol", "window_start_doy", "window_end_doy", "row_id"],
        },
        "counts": {
            # Set-scoped, NOT page-scoped: the API replaces `rows` with one page
            # and leaves these alone, so a UI that renders "N of len(rows)" from
            # the page it holds would be wrong without this label.
            "scope": "result_set_not_page",
            "rows": len(ordered),
            "abstained": sum(1 for row in ordered if row.abstained),
            "exploratory": len(exploratory_rows),
            "estimate_types": sorted(kinds),
        },
        "rows": [row.as_dict() for row in ordered],
    }
