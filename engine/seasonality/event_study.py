"""Biopharma event-study core — two estimands that are never allowed to blur.

An event study answers two completely different questions, and almost every
published biotech "catalyst edge" is the first question wearing the second one's
clothes:

1. **What happened around a realized event?**  ``estimate_reaction`` — ex-post,
   descriptive.  It may use anything revealed at or after the event, including the
   fact that the event happened at all and how it resolved.  It is a measurement,
   not a forecast, and nothing here may be read as tradable.

2. **What could have been forecast before the event?**  ``forecast_ex_ante`` —
   tradable, and therefore bound to what a decision-maker actually had.  Only
   schedules and facts whose ``known_at`` precedes the decision cutoff enter the
   feature cut; realized outcomes and later revisions never do.

The two are SEPARATE OBJECTS WITH SEPARATE CODE PATHS on purpose.  The failure
mode is not a bug someone writes deliberately — it is a shared helper that grows
one convenient argument, and six months later the "ex-ante" number is quietly
reading a resolution field.  ``forecast_ex_ante`` does not call
``abnormal_returns`` and does not call ``estimate_reaction``; the test suite pins
that structurally rather than trusting the comment you are reading.

What the module refuses to do
-----------------------------
* **No midpoint imputation, ever.**  A source that said "Q3 2025" knows a quarter,
  not a Tuesday.  Interval-precision events run the study across the WHOLE interval
  (``interval_sensitivity_anchors``) or abstain with a named reason
  (``event_interval_policy``).  Collapsing a span to its centre invents precision
  the source never had and is the single most common way a biotech event panel
  becomes fiction.
* **No ticker-cluster-only confidence intervals** (``DNR:LAW-TIME-CLUSTERED-CI``).
  Biotech catalysts arrive in waves — an FDA calendar quarter, a conference week —
  so events that look independent across issuers are the same macro draw.
  ``clustered_bootstrap_ci`` REFUSES a call that supplies only issuer clusters.
* **No era-pooled inference across the 2010 break** (``DNR:LAW-ERA-SPLIT``).
  ``era_split`` returns both eras or DISCLOSES the missing one; it never
  manufactures a second era out of a single-era panel.
* **No benchmark shopping.**  SPY / XBI / IBB are declared sensitivity legs.
  ``abnormal_returns_all_benchmarks`` returns ALL of them and there is deliberately
  no "pick the best benchmark" function anywhere in this module.
* **No winner without a registered family.**  ``register_search_family`` writes the
  whole config family to ``engine.trial_ledger`` AT GENERATION; ``inspect_winner``
  raises :class:`UnregisteredSearchFamily` if you try to read a maximum out of an
  unregistered search.

Build floors (``BUILD_FLOORS``) are DESCRIPTIVE — they say when a picture is too
thin to draw, not when a signal has earned authority.  Promotion to rank/size/gate
runs the separate gauntlet; nothing in this file promotes anything.

Determinism: every resampling entry point takes an explicit ``seed`` and no estimator
in this module reads a wall clock.  Two calls to an estimator with the same inputs
return the same bytes.  ONE function is deliberately outside that claim:
``register_search_family`` WRITES to the trial ledger, so the ledger is an input it
mutates — its ``n_newly_distinct`` is the count added by THIS call (zero on a re-run)
and the row it appends is timestamped by ``engine.trial_ledger``, not here.  That is
the point of a ledger and it is named rather than glossed.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .contracts import (
    ContractError,
    source_temporal_day,
    source_temporal_is_study_eligible,
    source_temporal_span_seconds,
    validate_source_temporal,
)

EVENT_STUDY_SCHEMA = "biopharma.event_study.v1"
ABSTENTION_SCHEMA = "biopharma.event_study.abstention.v1"
EX_ANTE_ROW_SCHEMA = "biopharma.event_study.ex_ante_row.v1"
AVAILABILITY_RECEIPT_SCHEMA = "biopharma.event_study.availability_receipt.v1"

#: The declared sensitivity legs.  A list, always reported in full — never a menu.
SENSITIVITY_BENCHMARKS = ("SPY", "XBI", "IBB")

#: Return models for :func:`abnormal_returns`.  ``market_adjusted`` fixes beta at 1
#: (no estimation risk, no estimation bias either); ``market`` estimates alpha/beta
#: by OLS on the estimation window only.
AR_MODELS = ("raw", "market_adjusted", "market")

#: Descriptive build floors.  NOT promotion gates — see the module docstring.
BUILD_FLOORS: dict[str, int] = {
    "min_events": 50,
    "min_issuers": 20,
    "min_date_clusters": 20,
}

#: The structural break the era-split law names.  Deliberately a constant and not a
#: parameter: a caller who can move the break can move it until the panel splits
#: somewhere flattering.
ERA_BREAK_YEAR = 2010

#: Declared width threshold for an event's temporal span.  A span wider than this
#: cannot be anchored on one bar; it runs across the whole interval or abstains.
#: Seven calendar days — one exchange week — is the widest span whose whole interval
#: still fits inside a normal +/-10 day event window without swallowing it.
MAX_EVENT_SPAN_SECONDS = 7 * 24 * 3600

#: Cluster keys that count as a TIME control for ``clustered_bootstrap_ci``.
TIME_CLUSTER_KEYS = frozenset(
    {"date", "day", "week", "month", "quarter", "year", "period", "era", "time",
     "date_cluster", "time_cluster", "event_month", "event_quarter", "event_week"}
)

#: Cluster keys that are issuer identity, not time.  Present so the refusal message
#: can say WHICH key it saw rather than "no time key found".
ISSUER_CLUSTER_KEYS = frozenset(
    {"issuer", "issuer_id", "ticker", "symbol", "cik", "company", "name"}
)

#: Feature names that can only be known after the fact.  Their presence in an
#: ex-ante feature cut is a leak, whatever timestamp is attached to them.
REALIZED_OUTCOME_KEYS = frozenset(
    {"actual", "actual_outcome", "outcome", "realized", "realised", "realized_return",
     "realised_return", "result", "resolution", "resolved", "car", "abnormal_return",
     "post_event", "post_event_return", "revision", "revised", "restated",
     "final_label"}
)

#: Timestamp keys that mark a fact as a LATER REVISION of an earlier value.  A fact
#: carrying one of these after the decision cutoff is a restatement the decision-maker
#: did not have, whatever its ``known_at`` says.
REVISION_TIME_KEYS = ("revised_at", "restated_at", "vintage", "vintage_at",
                      "as_of", "asof")

_DATE_CLUSTER_GRAINS = ("day", "week", "month", "quarter", "year")


class EventStudyError(ValueError):
    """A malformed call — the input could not describe any study."""


class UnregisteredSearchFamily(RuntimeError):
    """A maximum was read out of a search whose family was never registered.

    Selecting the best of K configurations spends K units of multiple-testing
    budget.  If the family was not written to the trial ledger AT GENERATION, that
    budget is unrecorded and every downstream haircut is too lenient — so reading
    the winner is refused rather than served with a warning nobody sees.
    """


# --------------------------------------------------------------------------- #
# small pure helpers (no scipy, matching engine/validation.py's thin-env rule)
# --------------------------------------------------------------------------- #
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _betacf(a: float, b: float, x: float, itmax: int = 300, eps: float = 3e-14) -> float:
    """Continued fraction for the incomplete beta function (Lentz's algorithm)."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lb = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
          + a * math.log(x) + b * math.log1p(-x))
    bt = math.exp(lb)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _student_t_two_sided_p(t: float, df: float) -> float | None:
    """Exact two-sided Student-t p-value.

    The normal approximation is used everywhere else in the repo, and at the event
    counts this module actually sees (N = 50 events is the FLOOR, not a typical
    sample) it over-rejects: the 5% normal critical value fires ~5.9% of the time
    against a true t(49).  A cross-sectional test whose stated size is wrong by a
    fifth is a bug, so the incomplete beta is spelled out here instead."""
    if t is None or not math.isfinite(t) or df <= 0:
        return None
    x = df / (df + t * t)
    return float(min(1.0, max(0.0, _betainc(df / 2.0, 0.5, x))))


def _abstain(reason: str, **extra: Any) -> dict:
    """The structured non-answer.  A refusal is a result with a name, never a
    silent NaN and never a number that reads like a weak finding."""
    payload = {"schema": ABSTENTION_SCHEMA, "abstained": True, "reason": reason}
    payload.update(extra)
    return payload


def _to_utc(value: Any, field: str = "timestamp") -> datetime:
    """Parse anything date-like into a UTC-aware datetime.  Naive input is read as
    UTC (declared, not guessed) — the contracts layer is where timezone-bearing
    source values are validated."""
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        moment = datetime(value.year, value.month, value.day)
    elif isinstance(value, pd.Timestamp):  # pragma: no cover - Timestamp is a datetime
        moment = value.to_pydatetime()
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            moment = datetime.fromisoformat(text)
        except ValueError as exc:
            raise EventStudyError(f"{field} is not an ISO-8601 timestamp: {value!r}") from exc
    else:
        raise EventStudyError(f"{field} must be a date, datetime, or ISO-8601 string")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _iso(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_hash(payload: Any) -> str:
    """sha256 of a stable JSON encoding — the freeze receipt for a feature cut."""
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# event temporal resolution — spans in, spans out, never a midpoint
# --------------------------------------------------------------------------- #
_TEMPORAL_FIELD_ORDER = ("actual", "scheduled_window", "source_effective")
_PLAIN_DATE_KEYS = ("event_date", "date", "effective_date")


def event_temporal(event: Mapping[str, Any]) -> dict[str, Any]:
    """The ``source_temporal`` span an event should be studied on.

    A ``biopharma.event.v2`` payload already carries spans; the realized ``actual``
    is preferred, then the ``scheduled_window``, then ``source_effective``.  A plain
    row carrying only ``event_date`` is lifted through
    :func:`engine.seasonality.contracts.source_temporal_day`, so even the convenience
    path produces a whole-day SPAN rather than a midnight instant that would read as
    a precise time nobody stated."""
    if not isinstance(event, Mapping):
        raise EventStudyError("event must be a mapping")
    for field in _TEMPORAL_FIELD_ORDER:
        value = event.get(field)
        if isinstance(value, Mapping):
            return validate_source_temporal(value, field)
    for key in _PLAIN_DATE_KEYS:
        value = event.get(key)
        if value is None:
            continue
        if isinstance(value, Mapping):
            return validate_source_temporal(value, key)
        moment = _to_utc(value, key)
        return source_temporal_day(moment.date().isoformat())
    raise EventStudyError(
        "event carries no temporal span: expected one of "
        f"{list(_TEMPORAL_FIELD_ORDER)} or {list(_PLAIN_DATE_KEYS)}"
    )


def event_bounds(event: Mapping[str, Any]) -> tuple[datetime | None, datetime | None]:
    """(lower, upper) UTC bounds of the event's span, or (None, None) if unbounded."""
    temporal = event_temporal(event)
    if not source_temporal_is_study_eligible(temporal):
        return None, None
    return (_to_utc(temporal["lower_bound"], "lower_bound"),
            _to_utc(temporal["upper_bound"], "upper_bound"))


def event_interval_policy(temporal: Mapping[str, Any], *,
                          max_span_seconds: float = MAX_EVENT_SPAN_SECONDS,
                          run_interval_sensitivity: bool = False) -> dict:
    """How wide is this event's span, and what is the study allowed to do with it?

    Three outcomes, and MIDPOINT IMPUTATION IS NOT ONE OF THEM:

    * ``mode="point"`` — the span is inside the declared width threshold, so the
      whole interval fits in one anchor's neighbourhood and the study runs once.
      A calendar day is a span too; "point" means "narrow enough that the whole span
      is the anchor", never "we picked an instant inside it".
    * ``mode="interval_sensitivity"`` — the span exceeds the threshold and the caller
      declared it will run the study across the WHOLE interval
      (``run_interval_sensitivity=True``); see :func:`interval_sensitivity_anchors`.
    * ``mode="abstain"`` — the span is unbounded, or it is wider than the threshold
      and no interval sensitivity was declared.  The reason is named.

    A month-precision FDA row is a real fact about a month.  Reading it as the 15th
    manufactures 29 days of precision the source never had, and an event study built
    on manufactured dates produces abnormal returns around dates that never happened.
    """
    try:
        payload = validate_source_temporal(temporal)
    except ContractError as exc:
        return _abstain(f"invalid_source_temporal:{exc}", mode="abstain", eligible=False,
                        span_seconds=None, lower=None, upper=None)
    if not source_temporal_is_study_eligible(payload):
        return _abstain("source_temporal_not_study_eligible", mode="abstain",
                        eligible=False, span_seconds=None, lower=None, upper=None,
                        precision=payload.get("precision"))
    span = source_temporal_span_seconds(payload)
    base = {
        "schema": EVENT_STUDY_SCHEMA,
        "eligible": True,
        "precision": payload["precision"],
        "span_seconds": float(span) if span is not None else None,
        "max_span_seconds": float(max_span_seconds),
        "lower": payload["lower_bound"],
        "upper": payload["upper_bound"],
        "abstained": False,
        "reason": None,
    }
    if span is None:  # pragma: no cover - eligibility already implies bounds
        return _abstain("span_unmeasurable", mode="abstain", **{k: base[k] for k in
                        ("eligible", "precision", "span_seconds", "lower", "upper")})
    if span <= max_span_seconds:
        base["mode"] = "point"
        return base
    if run_interval_sensitivity:
        base["mode"] = "interval_sensitivity"
        return base
    out = _abstain("interval_span_exceeds_threshold_without_sensitivity",
                   mode="abstain", eligible=True, precision=payload["precision"],
                   span_seconds=float(span), max_span_seconds=float(max_span_seconds),
                   lower=payload["lower_bound"], upper=payload["upper_bound"])
    return out


def interval_sensitivity_anchors(temporal: Mapping[str, Any], calendar: Sequence[Any]) -> list:
    """Every tradable bar inside the event's span — the WHOLE interval, in order.

    This is the honest alternative to a midpoint: a quarter-precision event is
    studied at each of its ~63 sessions and the dispersion across those anchors IS
    the sensitivity result.  Returns an empty list when the calendar holds no
    session inside the span, which is itself a finding (the event's own interval
    contains no tradable bar)."""
    payload = validate_source_temporal(temporal)
    if not source_temporal_is_study_eligible(payload):
        return []
    lower = _to_utc(payload["lower_bound"], "lower_bound")
    upper = _to_utc(payload["upper_bound"], "upper_bound")
    bars = _normalize_calendar(calendar)
    return [b for b in bars if lower <= b <= upper]


def _normalize_calendar(calendar: Sequence[Any]) -> list[datetime]:
    """Sorted, de-duplicated UTC bars.  A calendar that arrives out of order is a
    caller bug that would otherwise silently mis-place every placebo date."""
    if calendar is None:
        raise EventStudyError("a trading calendar is required")
    bars = sorted({_to_utc(b, "calendar bar") for b in calendar})
    if not bars:
        raise EventStudyError("the trading calendar is empty")
    return bars


# --------------------------------------------------------------------------- #
# availability — the bar an ex-ante decision could actually have been executed on
# --------------------------------------------------------------------------- #
_FACT_TIME_KEYS = ("known_at", "published", "published_at", "available", "available_at")


def _fact_timestamps(fact: Any, index: int) -> list[tuple[str, datetime]]:
    """Every availability timestamp a fact carries, as (key, moment) pairs."""
    if isinstance(fact, (str, datetime, date)):
        return [("known_at", _to_utc(fact, f"facts[{index}]"))]
    if not isinstance(fact, Mapping):
        raise EventStudyError(f"facts[{index}] must be a mapping or a timestamp")
    stamps: list[tuple[str, datetime]] = []
    for key in _FACT_TIME_KEYS:
        value = fact.get(key)
        if value is None:
            continue
        stamps.append((key, _to_utc(value, f"facts[{index}].{key}")))
    temporal = fact.get("source_temporal")
    if isinstance(temporal, Mapping):
        payload = validate_source_temporal(temporal, f"facts[{index}].source_temporal")
        if payload.get("upper_bound") is not None:
            stamps.append(("source_temporal.upper_bound",
                           _to_utc(payload["upper_bound"], "upper_bound")))
    if not stamps:
        raise EventStudyError(
            f"facts[{index}] carries no availability timestamp; expected one of "
            f"{list(_FACT_TIME_KEYS)} or a source_temporal span"
        )
    return stamps


def earliest_executable_bar(decision_cutoff: Any, facts: Iterable[Any], *,
                            trading_bars: Sequence[Any]) -> dict:
    """The first tradable bar an ex-ante decision could actually have reached.

    Execution is the next eligible bar STRICTLY AFTER

        max(decision cutoff, every source fact's known_at / published / available)

    and that maximum is computed here, explicitly, rather than assumed to be the
    cutoff.  The assumption is the bug: a feature can be *published* before the
    cutoff and still not be *available* to the decision-maker until after it — a
    vendor that stamps a filing 09:30 and delivers it 16:10, a fact that lands in the
    store the following session.  Anchoring execution on the cutoff in that case buys
    at a price nobody could have paid, and the resulting backtest is a forecast of the
    past.

    Returns the receipt — binding timestamp, WHICH fact and which key bound it, and
    the resolved bar — so a published number can be audited back to the one fact
    that set its execution clock."""
    cutoff = _to_utc(decision_cutoff, "decision_cutoff")
    bars = _normalize_calendar(trading_bars)
    binding = cutoff
    binding_source: dict[str, Any] = {"kind": "decision_cutoff", "fact_index": None,
                                      "key": None, "fact_id": None}
    stamps_report: list[dict[str, Any]] = []
    fact_list = list(facts or [])
    for i, fact in enumerate(fact_list):
        fact_id = fact.get("id") or fact.get("name") if isinstance(fact, Mapping) else None
        for key, moment in _fact_timestamps(fact, i):
            stamps_report.append({"fact_index": i, "fact_id": fact_id,
                                  "key": key, "timestamp": _iso(moment)})
            if moment > binding:
                binding = moment
                binding_source = {"kind": "fact", "fact_index": i, "key": key,
                                  "fact_id": fact_id}
    later = [b for b in bars if b > binding]
    receipt = {
        "schema": AVAILABILITY_RECEIPT_SCHEMA,
        "decision_cutoff": _iso(cutoff),
        "binding_timestamp": _iso(binding),
        "binding_source": binding_source,
        "n_facts": len(fact_list),
        "fact_timestamps": stamps_report,
        "abstained": False,
        "reason": None,
        "execution_bar": None,
    }
    if not later:
        receipt.update({"abstained": True,
                        "reason": "no_tradable_bar_after_availability"})
        return receipt
    receipt["execution_bar"] = _iso(later[0])
    return receipt


# --------------------------------------------------------------------------- #
# abnormal returns (ESTIMAND 1 — ex-post, descriptive)
# --------------------------------------------------------------------------- #
def _resolve_event_position(index: pd.Index, event_index: Any) -> int | None:
    """Position of the event bar: an int is positional; anything else is resolved to
    the LAST bar at or before the event moment (never after — that would be the first
    look-ahead)."""
    if isinstance(event_index, (int, np.integer)) and not isinstance(event_index, bool):
        pos = int(event_index)
        return pos if 0 <= pos < len(index) else None
    moment = _to_utc(event_index, "event_index")
    try:
        stamps = pd.to_datetime(pd.Index(index), utc=True)
    except (TypeError, ValueError) as exc:
        raise EventStudyError("prices index is not date-like; pass a positional "
                              "event_index instead") from exc
    pos = int(stamps.searchsorted(pd.Timestamp(moment), side="right")) - 1
    return pos if pos >= 0 else None


def abnormal_returns(prices, event_index, *, benchmark=None, model: str = "market",
                     estimation: tuple[int, int] = (-250, -31),
                     window: tuple[int, int] = (-10, 10),
                     min_estimation: int = 60,
                     with_estimation_ar: bool = False) -> dict:
    """Abnormal returns around ONE realized event.  Ex-post and descriptive.

    ``prices`` is a price series (simple returns are taken internally), ``benchmark``
    the matching benchmark price series, ``event_index`` either a positional index or
    a timestamp resolved to the last bar at or before it.

    ``model``:

    * ``"raw"`` — AR is the raw return.  No benchmark, no estimation risk, and no
      control for the tape the event happened on.
    * ``"market_adjusted"`` — beta fixed at 1: ``AR = r - r_benchmark``.
    * ``"market"`` — OLS ``r = alpha + beta * r_benchmark`` on the estimation window;
      ``AR = r - (alpha + beta * r_benchmark)``.

    **The estimation window ends strictly before BOTH the event window and the event
    day.**  That is enforced twice, not documented.  On the ARGUMENTS:
    ``estimation[1] < min(window[0], 0)`` or the call raises — the ``0`` limb matters,
    because a window that opens after the event (``window=(1, 10)``, a post-drift
    study) would otherwise let the event day itself, and every bar between it and the
    window, into the OLS fit while satisfying ``estimation[1] < window[0]``.  And on
    the SAMPLE: the fitted slice's length and end position are re-checked against the
    declared window before any coefficient is computed, so a slice that reaches past
    the declared end raises instead of returning a plausible alpha and beta.  Beta,
    alpha and the benchmark returns are therefore all fitted on bars before the event,
    which is what stops the event's own variance burst from being absorbed into the
    "normal" return model and quietly shrinking the abnormal return it exists to
    measure.  Move the event later and the estimation sample moves with it; the
    estimate changes, and it should.

    Returns AR per relative day, CAR over the window, and the per-event diagnostics a
    reader needs to distrust it: ``n_estimation_obs``, ``alpha``, ``beta``, ``r2``,
    ``sigma_estimation`` (the estimation-period residual sd that BMP standardizes by),
    and, when it abstained, why."""
    if model not in AR_MODELS:
        raise EventStudyError(f"model must be one of {list(AR_MODELS)}")
    est_lo, est_hi = int(estimation[0]), int(estimation[1])
    win_lo, win_hi = int(window[0]), int(window[1])
    if est_lo > est_hi:
        raise EventStudyError("estimation window must be ordered (lo <= hi)")
    if win_lo > win_hi:
        raise EventStudyError("event window must be ordered (lo <= hi)")
    latest_allowed = min(win_lo, 0)
    if est_hi >= latest_allowed:
        raise EventStudyError(
            f"estimation window ends at {est_hi} but the last bar it may use is "
            f"{latest_allowed - 1} (event window opens at {win_lo}, event day is 0): "
            "the estimation sample must end STRICTLY before BOTH the event window and "
            "the event day itself, with a gap, or the event's own bars set the "
            "normal-return model"
        )

    px = prices if isinstance(prices, pd.Series) else pd.Series(prices)
    px = px.astype(float)
    ret = px.pct_change()
    base = {
        "schema": EVENT_STUDY_SCHEMA,
        "estimand": "ex_post_reaction",
        "model": model,
        "estimation": [est_lo, est_hi],
        "window": [win_lo, win_hi],
        "gap_days": win_lo - est_hi - 1,
        "benchmark_name": getattr(benchmark, "name", None),
        "n_estimation_obs": 0,
        "alpha": None, "beta": None, "r2": None, "sigma_estimation": None,
        "ar": {}, "car": None, "event_position": None,
        "event_bar": None, "estimation_end_bar": None,
        "abstained": True, "reason": None,
    }
    if model != "raw" and benchmark is None:
        base["reason"] = "benchmark_required_for_model"
        return base

    pos = _resolve_event_position(px.index, event_index)
    if pos is None:
        base["reason"] = "event_not_on_price_index"
        return base
    base["event_position"] = pos

    n = len(px)
    est_start, est_end = pos + est_lo, pos + est_hi
    win_start, win_end = pos + win_lo, pos + win_hi
    if est_start < 1:
        base["reason"] = "estimation_window_truncated_at_series_start"
        return base
    if win_start < 0 or win_end >= n:
        base["reason"] = "event_window_truncated_at_series_edge"
        return base

    bm = None
    if benchmark is not None:
        bm = benchmark if isinstance(benchmark, pd.Series) else pd.Series(benchmark)
        bm = bm.astype(float).reindex(px.index)
        if len(bm.dropna()) == 0:
            base["reason"] = "benchmark_does_not_align_with_prices"
            return base
        bm = bm.pct_change()

    r_est = ret.iloc[est_start:est_end + 1].to_numpy(float)
    if bm is not None:
        b_est = bm.iloc[est_start:est_end + 1].to_numpy(float)
    else:
        b_est = np.zeros_like(r_est)
    # The SAMPLE, not just the arguments.  The guard above rejects a bad `estimation`
    # pair; this rejects a slice that reaches past the declared end however it got
    # there, because a widened slice produces perfectly plausible alphas and betas and
    # is exactly the leak this function's docstring promises cannot happen.
    _expected_est = est_hi - est_lo + 1
    if len(r_est) != _expected_est or len(b_est) != _expected_est or est_end >= pos:
        raise EventStudyError(
            f"internal: the estimation slice holds {len(r_est)} bars ending at "
            f"relative day {est_end - pos} but the declared estimation window is "
            f"[{est_lo}, {est_hi}] ({_expected_est} bars, all strictly before the "
            "event day) — a post-event bar cannot enter the normal-return model"
        )
    ok = np.isfinite(r_est) & np.isfinite(b_est)
    n_est = int(ok.sum())
    base["n_estimation_obs"] = n_est
    base["estimation_end_bar"] = _index_label(px.index, est_end)
    base["event_bar"] = _index_label(px.index, pos)
    if n_est < int(min_estimation):
        base["reason"] = f"insufficient_estimation_obs:{n_est}<{int(min_estimation)}"
        return base

    y, x = r_est[ok], b_est[ok]
    if model == "raw":
        alpha, beta = 0.0, 0.0
        fitted = np.zeros_like(y)
        ddof = 1
    elif model == "market_adjusted":
        alpha, beta = 0.0, 1.0
        fitted = x
        ddof = 1
    else:
        sx = float(np.std(x, ddof=1))
        if not math.isfinite(sx) or sx <= 0.0:
            base["reason"] = "zero_variance_benchmark_in_estimation_window"
            return base
        A = np.column_stack([np.ones(len(x)), x])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        alpha, beta = float(coef[0]), float(coef[1])
        fitted = A @ coef
        ddof = 2
    resid = y - fitted
    sse = float(np.dot(resid, resid))
    sst = float(np.dot(y - y.mean(), y - y.mean()))
    r2 = float(1.0 - sse / sst) if sst > 0 else None
    denom = max(len(resid) - ddof, 1)
    sigma = float(math.sqrt(sse / denom))
    base.update({"alpha": alpha, "beta": beta,
                 "r2": None if r2 is None else round(r2, 6),
                 "sigma_estimation": sigma})
    if not math.isfinite(sigma) or sigma <= 0.0:
        base["reason"] = "zero_residual_variance_in_estimation_window"
        return base

    def _ar_slice(lo: int, hi: int) -> dict[int, float]:
        out: dict[int, float] = {}
        for rel in range(lo, hi + 1):
            i = pos + rel
            r_i = float(ret.iloc[i])
            b_i = float(bm.iloc[i]) if bm is not None else 0.0
            if not math.isfinite(r_i) or (bm is not None and not math.isfinite(b_i)):
                out[rel] = float("nan")
                continue
            out[rel] = r_i - (alpha + beta * b_i)
        return out

    ar = _ar_slice(win_lo, win_hi)
    values = np.array(list(ar.values()), dtype=float)
    if not np.isfinite(values).all():
        base["reason"] = "missing_returns_inside_event_window"
        base["ar"] = ar
        return base
    base["ar"] = {int(k): float(v) for k, v in ar.items()}
    base["car"] = float(values.sum())
    base["abstained"] = False
    if with_estimation_ar:
        base["ar_estimation"] = {int(k): float(v) for k, v in _ar_slice(est_lo, est_hi).items()}
    return base


def _index_label(index: pd.Index, pos: int) -> Any:
    if 0 <= pos < len(index):
        label = index[pos]
        return label.isoformat() if hasattr(label, "isoformat") else str(label)
    return None


def abnormal_returns_all_benchmarks(prices, event_index, benchmarks: Mapping[str, Any],
                                    **kwargs) -> dict:
    """Run :func:`abnormal_returns` against EVERY declared benchmark and return all
    of them, keyed by name.

    SPY / XBI / IBB are sensitivity legs, not a menu.  A biotech catalyst's abnormal
    return against the S&P and against a biotech index are different questions; the
    honest report is both answers side by side, and the dispersion between them is
    itself the result.  There is deliberately NO function in this module that reads
    the legs and returns the most favourable one — such a function is benchmark
    shopping with a helper's name on it, and the omission is the control."""
    if not isinstance(benchmarks, Mapping) or not benchmarks:
        raise EventStudyError("benchmarks must be a non-empty mapping of name -> series")
    legs = {}
    for name in benchmarks:
        series = benchmarks[name]
        if isinstance(series, pd.Series):
            series = series.rename(name)
        legs[name] = abnormal_returns(prices, event_index, benchmark=series, **kwargs)
        legs[name]["benchmark_name"] = name
    return {"schema": EVENT_STUDY_SCHEMA, "estimand": "ex_post_reaction",
            "benchmarks": list(benchmarks), "legs": legs,
            "n_benchmarks": len(legs), "selection_policy": "all_legs_reported"}


# --------------------------------------------------------------------------- #
# cross-sectional tests over an event cohort
# --------------------------------------------------------------------------- #
def _as_matrix(ar_matrix) -> tuple["np.ndarray", list]:
    if isinstance(ar_matrix, pd.DataFrame):
        return ar_matrix.to_numpy(dtype=float), list(ar_matrix.columns)
    arr = np.asarray(ar_matrix, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2:
        raise EventStudyError("ar_matrix must be 2-D (events x window days)")
    return arr, list(range(arr.shape[1]))


def bmp_test(ar_matrix, sigma_estimation) -> dict:
    """Boehmer-Musumeci-Poulsen (1991) standardized cross-sectional test.

    ``ar_matrix`` is the EVENT-WINDOW abnormal returns, one row per event.
    ``sigma_estimation`` is each event's own estimation-period residual sd (the
    ``sigma_estimation`` field ``abnormal_returns`` returns).

    Each event's CAR is standardized by ITS OWN estimation-period sigma,

        SCAR_i = CAR_i / (sigma_i * sqrt(L))

    and the test is the cross-sectional t of the SCARs.  Be precise about WHICH
    failure each half fixes, because the folklore version of this docstring is wrong
    and was shipped here once already:

    * **Standardizing by sigma_i buys POWER, not size.**  The estimation-period sigma
      of a $200m clinical-stage name and of a large-cap pharma differ by an order of
      magnitude; unstandardized, the loudest events dominate both the cross-sectional
      mean CAR and the cross-sectional SD it is divided by.  MEASURED (per-event
      sigma ~ U[0.005, 0.06], a constant additive event-day abnormal return of +2.0%
      on every event, N=60, L=5, 1,200 replications, nominal 5%): BMP rejects 82.7%
      of the time, a plain cross-sectional t on raw CARs 45.7%.  Identical size under
      the null (4.9% vs 5.4%), nearly double the power — that is the case for the
      first step, and it is a power argument, not a size argument.
    * **Taking the CROSS-SECTIONAL SD is what survives EVENT-INDUCED VARIANCE.**  An
      FDA decision multiplies the return variance for the days around it whichever
      way it resolves, so the event-window variance is not the estimation-window
      variance.  The test that breaks on this is PATELL's — it divides by the
      estimation-period sd as if it were the truth.  MEASURED under a per-event
      variance burst of U[1, 3] Patell rejects 32.6% of the time against a nominal
      5%, and 71.1% under a burst of U[1, 9].  BMP's cross-sectional denominator lets
      the event-window variance be whatever it is; a plain cross-sectional t on raw
      CARs is likewise correctly sized here (4.6% / 4.9% — the burst cancels in a
      cross-sectional SD), so the honest claim is "BMP is calibrated where PATELL is
      not", never "where a raw-CAR t is not".  The earlier version of this docstring
      said the latter and it is false as written.

    The p-value is an exact Student-t with N-1 degrees of freedom.  Abstains rather
    than returning a number when N < 2, when a sigma is non-positive or non-finite,
    or when the SCARs have zero cross-sectional dispersion.

    MEASURED SIZE (zero-mean ARs, per-event sigma drawn from U[0.01, 0.05] and an
    independent event-window variance burst of U[1, 3] — i.e. event-induced variance
    present and unmodelled, 1,500 replications, nominal 5%): 5.1% at N=60, 3.9% at
    N=200; 4.9% at N=60 with the burst raised to U[1, 9]."""
    arr, _cols = _as_matrix(ar_matrix)
    sigmas = np.asarray(list(sigma_estimation), dtype=float).ravel()
    n_events, window_len = arr.shape
    stub = {"schema": EVENT_STUDY_SCHEMA, "test": "bmp",
            "n_events": int(n_events), "window_len": int(window_len)}
    if sigmas.shape[0] != n_events:
        raise EventStudyError(
            f"sigma_estimation has {sigmas.shape[0]} entries for {n_events} events")
    if n_events < 2:
        return _abstain("insufficient_events_lt_2", **stub)
    if window_len < 1:
        return _abstain("empty_event_window", **stub)
    car = arr.sum(axis=1)
    good = np.isfinite(car) & np.isfinite(sigmas) & (sigmas > 0)
    if not good.all():
        dropped = int((~good).sum())
        car, sigmas = car[good], sigmas[good]
        stub["n_dropped"] = dropped
    n = int(car.shape[0])
    stub["n_events"] = n
    if n < 2:
        return _abstain("insufficient_usable_events_lt_2", **stub)
    scar = car / (sigmas * math.sqrt(window_len))
    mean_scar = float(scar.mean())
    sd_scar = float(scar.std(ddof=1))
    if not math.isfinite(sd_scar) or sd_scar <= 0.0:
        return _abstain("zero_cross_sectional_dispersion", **stub)
    t = mean_scar * math.sqrt(n) / sd_scar
    p = _student_t_two_sided_p(t, n - 1)
    return {**stub, "t_stat": round(float(t), 6),
            "p_value": None if p is None else round(float(p), 6),
            "df": n - 1, "mean_scar": round(mean_scar, 6),
            "sd_scar": round(sd_scar, 6), "mean_car": round(float(car.mean()), 8),
            "abstained": False, "reason": None}


def corrado_rank_test(ar_matrix, *, event_cols: Sequence | None = None) -> dict:
    """Corrado (1989) / Corrado-Zivney (1992) non-parametric rank test.

    ``ar_matrix`` is the COMBINED estimation + event abnormal returns, one row per
    event, columns ordered in time and — in the normal case — labelled by relative
    day (which is exactly what ``abnormal_returns(..., with_estimation_ar=True)``
    produces).  ``event_cols`` names the columns being tested; it defaults to the
    single event day ``0`` when the columns are relative-day labels.

    Ranking is done WITHIN each event across the whole supplied period, so each
    event contributes a uniform rank distribution regardless of how fat its own
    return tail is.  That is the point: biotech abnormal returns are violently
    non-normal (a binary readout is bimodal, not Gaussian), and a t-test on them
    inherits the tail.  The rank transform does not care.

    Note the structural constraint the test carries: ranks within a row sum to a
    constant, so testing EVERY supplied column is identically zero.  The ranking
    period must be strictly wider than the tested window, and a call that cannot
    identify the event columns abstains instead of returning that structural zero
    dressed as a null result.

    MEASURED SIZE (zero-mean ARs with a per-event sigma drawn from U[0.01, 0.05],
    single event day, 3,000 replications, nominal 5%): 5.5% at N=60 over a 120-day
    ranking period, 4.8% at N=60 over 250 days, 4.7% at N=200 over 120 days.  Mildly
    CONSERVATIVE once the ranking period is long — the null dispersion S(K) is itself
    estimated from only that many daily means — so a longer ranking period is the
    cheap fix, and a Corrado p just above 0.05 on a 120-day period is weaker evidence
    of nothing than it looks.

    WHAT THOSE NUMBERS WERE MEASURED ON, and where they do not transfer.  The grid
    above draws an iid Gaussian matrix, so every column is exchangeable — which is the
    assumption the rank transform rests on.  ``estimate_reaction`` feeds this function
    something else: the estimation columns are IN-SAMPLE OLS residuals (mean exactly
    zero by construction, variance shrunk by the fit, orthogonal to the benchmark) and
    the event columns are out-of-sample abnormal returns carrying extra estimation
    error.  The two blocks are not exchangeable, so the quoted grid is a measurement
    of the statistic, not of the pipeline.  MEASURED on the residual-shaped panel the
    pipeline actually builds (220 in-sample residual columns + a 21-day out-of-sample
    event window, N=60, 2,000 replications, nominal 5%): 4.4% — the distortion is
    CONSERVATIVE, not liberal, and small.  ``tests/test_seasonality_event_study.py``
    re-measures it as
    ``test_corrado_size_on_the_residual_shaped_panel_the_pipeline_actually_feeds_it``
    so the claim is a check rather than a note."""
    frame_cols: list
    arr, frame_cols = _as_matrix(ar_matrix)
    n_events, n_days = arr.shape
    stub = {"schema": EVENT_STUDY_SCHEMA, "test": "corrado_rank",
            "n_events": int(n_events), "n_days": int(n_days)}
    if event_cols is None:
        if 0 in frame_cols:
            event_cols = [0]
        else:
            return _abstain("event_columns_unidentified", **stub)
    positions = []
    for col in event_cols:
        if col in frame_cols:
            positions.append(frame_cols.index(col))
        elif isinstance(col, (int, np.integer)) and 0 <= int(col) < n_days:
            positions.append(int(col))
        else:
            return _abstain(f"event_column_absent:{col!r}", **stub)
    positions = sorted(set(positions))
    stub["event_cols"] = [frame_cols[p] for p in positions]
    stub["window_len"] = len(positions)
    if len(positions) >= n_days:
        return _abstain("ranking_period_not_wider_than_event_window", **stub)
    keep = np.isfinite(arr).all(axis=1)
    if int(keep.sum()) != n_events:
        stub["n_dropped"] = int(n_events - keep.sum())
    arr = arr[keep]
    n_events = int(arr.shape[0])
    stub["n_events"] = n_events
    if n_events < 2:
        return _abstain("insufficient_usable_events_lt_2", **stub)
    if n_days < 10:
        return _abstain("ranking_period_lt_10_days", **stub)

    ranks = pd.DataFrame(arr).rank(axis=1, method="average").to_numpy(float)
    K = ranks / (n_days + 1.0) - 0.5          # mean-zero rank deviations
    kbar = K.mean(axis=0)                      # per-day cross-sectional mean
    s = float(math.sqrt(float(np.mean(kbar ** 2))))
    if not math.isfinite(s) or s <= 0.0:
        return _abstain("zero_rank_dispersion", **stub)
    L = len(positions)
    z = float(kbar[positions].sum() / (math.sqrt(L) * s))
    p = float(2.0 * (1.0 - _norm_cdf(abs(z))))
    return {**stub, "z_stat": round(z, 6), "p_value": round(p, 6),
            "mean_rank_deviation": round(float(kbar[positions].mean()), 6),
            "rank_sd": round(s, 6), "abstained": False, "reason": None}


def _cluster_frame(clusters) -> pd.DataFrame:
    if isinstance(clusters, pd.DataFrame):
        return clusters.reset_index(drop=True)
    if isinstance(clusters, Mapping):
        return pd.DataFrame({str(k): list(v) for k, v in clusters.items()})
    raise EventStudyError(
        "clusters must be a mapping (or DataFrame) of cluster-kind -> labels; "
        "a bare label array cannot say whether it is time or issuer identity"
    )


def _cluster_robust_se(sums: "np.ndarray", counts: "np.ndarray",
                       mean: float, n_clusters: int) -> float:
    """Cluster-robust standard error of a mean, from per-cluster sums and counts.

    ``sqrt(G/(G-1) * sum_g (S_g - mean * N_g)^2) / N`` — the sandwich variance of the
    sample mean when every event inside a cluster may be arbitrarily correlated."""
    total = float(counts.sum())
    if total <= 0:
        return float("nan")
    corr = n_clusters / max(n_clusters - 1.0, 1.0)
    resid = sums - mean * counts
    return float(math.sqrt(corr * float(np.dot(resid, resid))) / total)


def _effective_clusters(counts: "np.ndarray") -> float:
    """Kish's effective cluster count: ``(sum N_g)^2 / sum N_g^2``.

    Equal to ``G`` when every cluster is the same size and collapses toward 1 as one
    cluster comes to dominate the pool.  Twenty months of which one carried forty
    readouts and nineteen carried one each is not twenty independent draws — it is
    about two — and the degrees of freedom of the interval have to say so."""
    total = float(counts.sum())
    ssq = float(np.dot(counts, counts))
    if ssq <= 0:
        return 1.0
    return total * total / ssq


def _student_t_critical(df: float, q: float = 0.975) -> float:
    """Two-sided Student-t critical value at ``q``, by bisection on ``_betainc``."""
    if not math.isfinite(df) or df <= 0:
        return float("inf")
    target = 2.0 * (1.0 - q)
    lo, hi = 0.0, 400.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _student_t_two_sided_p(mid, df) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def clustered_bootstrap_ci(car, clusters, *, B: int = 5000, seed: int = 11) -> dict:
    """Studentized cluster bootstrap CI for the mean CAR — WHOLE clusters resampled.

    ``clusters`` is a mapping of cluster-kind -> per-event labels, e.g.
    ``{"date_cluster": [...], "issuer_id": [...]}``.  A TIME/DATE cluster key is
    REQUIRED (``DNR:LAW-TIME-CLUSTERED-CI``): a call supplying only issuer clusters
    is refused, not warned about.

    Why the refusal.  Biotech catalysts arrive in waves — an FDA quarter, a data
    conference week, a financing window — so a hundred events across ninety distinct
    tickers can be a dozen independent macro draws.  Bootstrapping on issuer identity
    alone treats each of those hundred as its own draw, shrinks the interval by
    roughly sqrt(events / months), and manufactures significance out of calendar
    clustering.  The effective N of this evidence is MONTHS, not tickers.

    Resampling draws whole time clusters with replacement, keeping every event inside
    a drawn cluster together, so within-cluster correlation survives the bootstrap
    exactly as it exists in the data.  Deterministic given ``seed``.

    THE INTERVAL IS STUDENTIZED, AND THAT IS NOT A REFINEMENT.  A raw percentile
    interval on the resampled means is anti-conservative at exactly the cluster counts
    this module's own build floor admits (``min_date_clusters = 20``) — MEASURED at
    nominal 5%, a true mean of zero, equicorrelated clusters, 1,500 replications:
    6.9% at 20 equal clusters, 8.3% at 20 clusters of U[1,12] events, 8.7% with one
    wave of 40 among singletons, and it does NOT converge away with more clusters
    (6.1-8.1% at 60).  A statistic that is the field readers key on
    (``excludes_zero``) and that rejects at up to 1.7x its stated rate is a bug, so
    the percentile interval is not what ships.  What ships is
    ``mean +/- q * cluster_robust_se``, where the cluster-robust SE is the sandwich
    error of the mean over WHOLE clusters and ``q`` is

        max(bootstrap 95th percentile of |t*|, Student-t at the EFFECTIVE cluster df)

    — the bootstrap's own studentized quantile, FLOORED at the analytic critical value
    for Kish's effective cluster count.  The floor is the part that earns its keep: a
    bootstrap over G labels cannot see that one of those clusters carries two thirds
    of the events, so a panel whose evidence is really two draws would otherwise get a
    twenty-draw interval.  MEASURED size of the shipped interval on the same three
    panels: 4.2% / 3.9% / 0.3%, and 4.9% / 4.6% / 5.4% at 60 clusters.  It is mildly
    CONSERVATIVE, which is the direction an interval that gates a headline should err
    in; the 0.3% is the one-wave panel, where the honest answer is that there is
    almost no independent evidence and the interval now says so.

    Both critical values are reported (``q_bootstrap``, ``q_floor``, ``q_used``,
    ``critical_source``) so a published interval can be audited back to which one set
    its width."""
    frame = _cluster_frame(clusters)
    values = np.asarray(list(car), dtype=float).ravel()
    if len(frame) != len(values):
        raise EventStudyError(
            f"clusters describe {len(frame)} events but {len(values)} CARs were given")
    lowered = {str(c).lower(): c for c in frame.columns}
    time_key = next((lowered[k] for k in lowered if k in TIME_CLUSTER_KEYS), None)
    if time_key is None:
        issuer_seen = sorted(lowered[k] for k in lowered if k in ISSUER_CLUSTER_KEYS)
        raise EventStudyError(
            "DNR:LAW-TIME-CLUSTERED-CI — a time/date cluster key is required; "
            f"got cluster kinds {sorted(map(str, frame.columns))}"
            + (f" (issuer-only keys {issuer_seen})" if issuer_seen else "")
            + ". Issuer-clustered intervals are anti-conservative here because the "
              "effective sample size of catalyst evidence is months, not tickers."
        )
    issuer_key = next((lowered[k] for k in lowered if k in ISSUER_CLUSTER_KEYS), None)

    good = np.isfinite(values)
    labels = frame[time_key].astype(str).to_numpy()[good]
    vals = values[good]
    if vals.size == 0:
        return _abstain("no_finite_cars", schema=EVENT_STUDY_SCHEMA,
                        test="clustered_bootstrap_ci", n_events=0)
    uniq = sorted(set(labels.tolist()))
    groups = [vals[labels == u] for u in uniq]
    n_clusters = len(groups)
    n_issuer_clusters = (int(pd.Series(frame[issuer_key]).astype(str).nunique())
                         if issuer_key is not None else None)
    stub = {"schema": EVENT_STUDY_SCHEMA, "test": "clustered_bootstrap_ci",
            "n_events": int(vals.size), "n_time_clusters": n_clusters,
            "time_cluster_key": str(time_key),
            "issuer_cluster_key": None if issuer_key is None else str(issuer_key),
            "n_issuer_clusters": n_issuer_clusters,
            "B": int(B), "seed": int(seed), "law": "DNR:LAW-TIME-CLUSTERED-CI"}
    if int(B) < 2:
        return _abstain(f"insufficient_bootstrap_draws_lt_2:{int(B)}", **stub)
    if n_clusters < 2:
        return _abstain("insufficient_time_clusters_lt_2", **stub)

    sums = np.array([g.sum() for g in groups], dtype=float)
    counts = np.array([g.size for g in groups], dtype=float)
    point = float(vals.mean())
    se = _cluster_robust_se(sums, counts, point, n_clusters)
    if not math.isfinite(se) or se <= 0.0:
        return _abstain("zero_cluster_robust_standard_error", **stub)

    rng = np.random.default_rng(int(seed))
    picks = rng.integers(0, n_clusters, size=(int(B), n_clusters))
    boot_sums, boot_counts = sums[picks].sum(axis=1), counts[picks].sum(axis=1)
    boot_mean = boot_sums / boot_counts
    corr = n_clusters / max(n_clusters - 1.0, 1.0)
    resid = sums[picks] - boot_mean[:, None] * counts[picks]
    boot_se = np.sqrt(corr * (resid ** 2).sum(axis=1)) / boot_counts
    usable = np.isfinite(boot_se) & (boot_se > 0.0)
    if int(usable.sum()) < 2:
        return _abstain("bootstrap_produced_no_usable_standard_errors", **stub)
    t_star = np.abs((boot_mean[usable] - point) / boot_se[usable])
    q_boot = float(np.percentile(t_star, 95.0))
    g_eff = _effective_clusters(counts)
    q_floor = _student_t_critical(max(g_eff - 1.0, 1.0))
    q_used = max(q_boot, q_floor)
    lo, hi = point - q_used * se, point + q_used * se
    return {**stub,
            "mean_car": round(point, 8),
            "ci": [round(float(lo), 8), round(point, 8), round(float(hi), 8)],
            "excludes_zero": bool(lo > 0.0 or hi < 0.0),
            "cluster_robust_se": round(se, 10),
            "q_bootstrap": round(q_boot, 6),
            "q_floor": round(float(q_floor), 6),
            "q_used": round(float(q_used), 6),
            "critical_source": "bootstrap" if q_boot >= q_floor else "effective_cluster_t",
            "effective_clusters_kish": round(float(g_eff), 4),
            "n_bootstrap_usable": int(usable.sum()),
            "effective_n": (n_clusters if n_issuer_clusters is None
                            else min(n_clusters, n_issuer_clusters)),
            "abstained": False, "reason": None}


# --------------------------------------------------------------------------- #
# contamination, placebos, perturbation, matched controls
# --------------------------------------------------------------------------- #
def _event_id(event: Mapping[str, Any], i: int) -> str:
    return str(event.get("event_id") or event.get("id") or f"event_{i}")


def _issuer_id(event: Mapping[str, Any]) -> str:
    return str(event.get("issuer_id") or event.get("issuer")
               or event.get("ticker") or event.get("symbol") or "__unknown__")


def flag_contamination(events: Sequence[Mapping[str, Any]], *,
                       window: tuple[int, int]) -> list:
    """Events whose study window overlaps ANOTHER event on the same issuer.

    The window is applied to the event's whole SPAN (``[lower + window[0]*day,
    upper + window[1]*day]``), so a month-precision row contaminates for the whole
    month rather than for one invented day.  A contaminated event's abnormal return
    is not the reaction to this catalyst; it is the reaction to whatever else that
    issuer did that fortnight, and pooling it in is how a strong-looking cohort mean
    turns out to be twelve issuers announcing financings.

    Returns one record per contaminated event (unflagged events are absent)."""
    lo_days, hi_days = int(window[0]), int(window[1])
    spans: list[tuple[str, str, datetime, datetime, int]] = []
    for i, ev in enumerate(events):
        lower, upper = event_bounds(ev)
        if lower is None or upper is None:
            continue
        spans.append((_event_id(ev, i), _issuer_id(ev),
                      lower + timedelta(days=lo_days),
                      upper + timedelta(days=hi_days), i))
    out: list[dict[str, Any]] = []
    for eid, issuer, lo, hi, i in spans:
        overlaps = [
            other_id for other_id, other_issuer, o_lo, o_hi, j in spans
            if j != i and other_issuer == issuer and o_lo <= hi and lo <= o_hi
        ]
        if overlaps:
            out.append({"schema": EVENT_STUDY_SCHEMA, "event_id": eid,
                        "issuer_id": issuer, "window": [lo_days, hi_days],
                        "window_start": _iso(lo), "window_end": _iso(hi),
                        "contaminating_event_ids": sorted(overlaps),
                        "n_overlaps": len(overlaps), "contaminated": True})
    return sorted(out, key=lambda r: (r["issuer_id"], r["event_id"]))


def placebo_dates(events: Sequence[Mapping[str, Any]], *, offsets: Sequence[int],
                  calendar: Sequence[Any]) -> list:
    """Shift each event by ``offsets`` TRADING days on ``calendar``.

    A placebo cohort is the cheapest refutation available: run the identical
    estimator on dates where nothing happened.  If the method finds the same
    "abnormal" return 40 sessions before every catalyst, the estimator is measuring
    its own construction — a benchmark misfit, a survivorship artefact, a calendar
    effect — and not the event.  Offsets are trading days, not calendar days, so a
    placebo never lands on a session that does not exist."""
    if 0 in [int(o) for o in offsets]:
        raise EventStudyError("offset 0 is the event itself, not a placebo")
    bars = _normalize_calendar(calendar)
    out: list[dict[str, Any]] = []
    for i, ev in enumerate(events):
        lower, upper = event_bounds(ev)
        eid, issuer = _event_id(ev, i), _issuer_id(ev)
        if lower is None:
            out.append({"schema": EVENT_STUDY_SCHEMA, "event_id": eid, "issuer_id": issuer,
                        "abstained": True, "reason": "event_span_not_study_eligible"})
            continue
        anchor = _bar_position(bars, lower)
        for offset in offsets:
            k = anchor + int(offset)
            row = {"schema": EVENT_STUDY_SCHEMA, "event_id": eid, "issuer_id": issuer,
                   "placebo_offset_trading_days": int(offset),
                   "source_event_lower": _iso(lower), "source_event_upper": _iso(upper),
                   "abstained": False, "reason": None, "placebo_date": None}
            if anchor < 0 or not (0 <= k < len(bars)):
                row.update({"abstained": True, "reason": "placebo_offset_off_calendar"})
            else:
                row["placebo_date"] = _iso(bars[k])
            out.append(row)
    return out


def _bar_position(bars: Sequence[datetime], moment: datetime) -> int:
    """Index of the last bar at or before ``moment``; -1 if the calendar starts later."""
    lo, hi = 0, len(bars)
    while lo < hi:
        mid = (lo + hi) // 2
        if bars[mid] <= moment:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1


def perturb_event_dates(events: Sequence[Mapping[str, Any]], *,
                        deltas: Sequence[int] = (-5, -2, 2, 5)) -> list:
    """Slide each event's whole SPAN by ``deltas`` calendar days.

    Perturbation is the date-precision stress test that placebos do not cover: if a
    result survives being moved two days but the announced dates were only ever
    accurate to a week, the effect being measured is not the announcement.  The span
    moves as a unit — both bounds — so a perturbed month stays a month.  Zero is
    refused: it is the study, not a perturbation."""
    deltas = [int(d) for d in deltas]
    if any(d == 0 for d in deltas):
        raise EventStudyError("delta 0 is the unperturbed study, not a perturbation")
    out: list[dict[str, Any]] = []
    for i, ev in enumerate(events):
        lower, upper = event_bounds(ev)
        eid, issuer = _event_id(ev, i), _issuer_id(ev)
        if lower is None or upper is None:
            out.append({"schema": EVENT_STUDY_SCHEMA, "event_id": eid, "issuer_id": issuer,
                        "abstained": True, "reason": "event_span_not_study_eligible"})
            continue
        for delta in deltas:
            shift = timedelta(days=delta)
            out.append({"schema": EVENT_STUDY_SCHEMA, "event_id": eid, "issuer_id": issuer,
                        "delta_days": delta,
                        "source_event_lower": _iso(lower), "source_event_upper": _iso(upper),
                        "perturbed_lower": _iso(lower + shift),
                        "perturbed_upper": _iso(upper + shift),
                        "abstained": False, "reason": None})
    return out


def matched_controls(events: Sequence[Mapping[str, Any]],
                     candidates: Sequence[Mapping[str, Any]], *,
                     on: Sequence[str], tolerance) -> list:
    """Greedy nearest-neighbour matching of each event to an unused control.

    ``on`` names the covariates (market cap, ADV, sector code, whatever the panel
    carries); ``tolerance`` is a per-key caliper (a mapping) or one scalar applied to
    every key.  Distance is the sum of |difference| / caliper across ``on``, and a
    candidate outside ANY caliper is not eligible at all — a caliper that is only a
    tie-break is not a caliper.

    Matching is WITHOUT replacement and fully deterministic: events are processed in
    sorted event-id order and ties break on candidate id, so the same panel yields
    the same pairing on every run.  Unmatched events are returned with
    ``matched=False`` and a named reason rather than being dropped, because a cohort
    that could only match a third of its events is a finding about the cohort."""
    keys = list(on)
    if not keys:
        raise EventStudyError("matched_controls needs at least one covariate in `on`")
    if isinstance(tolerance, Mapping):
        tol = {k: float(tolerance[k]) for k in keys}
    else:
        tol = {k: float(tolerance) for k in keys}
    if any(v <= 0 for v in tol.values()):
        raise EventStudyError("every caliper in `tolerance` must be positive")

    pool: list[tuple[str, Mapping[str, Any]]] = [
        (str(c.get("candidate_id") or c.get("id") or f"candidate_{j}"), c)
        for j, c in enumerate(candidates)
    ]
    pool.sort(key=lambda t: t[0])
    used: set[str] = set()
    rows: list[dict[str, Any]] = []
    ordered = sorted(((_event_id(ev, i), ev) for i, ev in enumerate(events)),
                     key=lambda t: t[0])
    for eid, ev in ordered:
        row = {"schema": EVENT_STUDY_SCHEMA, "event_id": eid, "issuer_id": _issuer_id(ev),
               "on": keys, "control_id": None, "distance": None,
               "matched": False, "reason": None}
        if any(ev.get(k) is None for k in keys):
            row["reason"] = "event_missing_covariate"
            rows.append(row)
            continue
        best_id, best_d = None, math.inf
        for cid, cand in pool:
            if cid in used or any(cand.get(k) is None for k in keys):
                continue
            dist = 0.0
            ok = True
            for k in keys:
                try:
                    diff = abs(float(ev[k]) - float(cand[k]))
                except (TypeError, ValueError):
                    ok = False
                    break
                if diff > tol[k]:
                    ok = False
                    break
                dist += diff / tol[k]
            if ok and dist < best_d:
                best_id, best_d = cid, dist
        if best_id is None:
            row["reason"] = "no_candidate_inside_caliper"
        else:
            used.add(best_id)
            row.update({"control_id": best_id, "distance": round(float(best_d), 8),
                        "matched": True})
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# cohort accounting, build floors, era split
# --------------------------------------------------------------------------- #
def date_cluster_key(moment: datetime, grain: str = "month") -> str:
    """Calendar cluster label for a bar.  ``month`` is the default because the
    dependence in a catalyst panel is a calendar quarter's worth of regulatory and
    conference scheduling, not a day's."""
    if grain not in _DATE_CLUSTER_GRAINS:
        raise EventStudyError(f"grain must be one of {list(_DATE_CLUSTER_GRAINS)}")
    if grain == "day":
        return moment.date().isoformat()
    if grain == "week":
        iso = moment.isocalendar()
        return f"{iso[0]:04d}-W{iso[1]:02d}"
    if grain == "month":
        return f"{moment.year:04d}-{moment.month:02d}"
    if grain == "quarter":
        return f"{moment.year:04d}-Q{(moment.month - 1) // 3 + 1}"
    return f"{moment.year:04d}"


def cohort_counts(events: Sequence[Mapping[str, Any]], *,
                  date_cluster: str = "month") -> dict:
    """``n_events`` / ``n_issuers`` / ``n_date_clusters`` / ``effective_n``.

    ``effective_n = min(n_issuers, n_date_clusters)``.  Events inside a cluster are
    NEVER counted as independent: forty readouts from one issuer in one quarter are
    one draw about that issuer and one draw about that quarter, and the binding
    constraint is whichever is scarcer.  Every result this module returns carries all
    four numbers, so a headline can never quote the event count alone.

    An event whose span is not study-eligible (unbounded, "date unavailable") is
    counted in ``n_events`` — it is a real row in the panel — but ALSO reported
    separately as ``n_events_bounded`` / ``n_issuers_bounded``, and those are the
    counts :func:`check_build_floors` reads.  An event with no date cannot be studied,
    so letting it clear ``min_events`` while contributing nothing to
    ``min_date_clusters`` would be a floor passed on rows the estimator will drop."""
    n_events = 0
    issuers: set[str] = set()
    issuers_bounded: set[str] = set()
    clusters: set[str] = set()
    unbounded = 0
    for i, ev in enumerate(events):
        lower, _upper = event_bounds(ev)
        n_events += 1
        issuers.add(_issuer_id(ev))
        if lower is None:
            unbounded += 1
            continue
        issuers_bounded.add(_issuer_id(ev))
        clusters.add(date_cluster_key(lower, date_cluster))
    return {"schema": EVENT_STUDY_SCHEMA,
            "n_events": n_events, "n_issuers": len(issuers),
            "n_date_clusters": len(clusters),
            "effective_n": min(len(issuers), len(clusters)),
            "n_events_bounded": n_events - unbounded,
            "n_issuers_bounded": len(issuers_bounded),
            "n_unbounded_events": unbounded,
            "date_cluster_grain": date_cluster}


def check_build_floors(events: Sequence[Mapping[str, Any]], *,
                       floors: Mapping[str, int] = None,
                       date_cluster: str = "month") -> dict:
    """Are there enough independent events to draw the picture at all?

    These are DESCRIPTIVE BUILD FLOORS, not promotion gates.  Clearing them earns a
    chart, not authority; a signal that wants to rank or size runs the separate
    gauntlet.  Below any floor the caller gets a structured abstention naming WHICH
    floor failed and the observed count — "insufficient events" with no number is the
    disclosure that discloses nothing.

    ``floors`` OVERLAYS the module defaults, it does not replace them.  A caller
    passing ``{}`` used to switch every floor off and still get ``floors_passed:
    True``, which is the one field a downstream reader is told to key on — three
    events, one issuer, one month and a p = 0.0007 headline were indistinguishable
    from a fifty-event cohort.  Now: unspecified floors keep their default, and any
    floor set BELOW its default is reported by name in ``floors_relaxed`` alongside
    ``floors_passed_at_default``, so a relaxed build is visible in the payload rather
    than in the caller's memory of what it passed."""
    supplied = {} if floors is None else {str(k): int(v) for k, v in floors.items()}
    floors = {**BUILD_FLOORS, **supplied}
    counts = cohort_counts(events, date_cluster=date_cluster)
    # The floors are read on the STUDYABLE rows: an event with no usable date clears
    # min_events while contributing nothing to min_date_clusters, and the estimator
    # will drop it anyway.
    observed = {"min_events": counts["n_events_bounded"],
                "min_issuers": counts["n_issuers_bounded"],
                "min_date_clusters": counts["n_date_clusters"]}
    failed = [{"floor": name, "required": int(floors[name]),
               "observed": int(observed.get(name, 0))}
              for name in sorted(floors)
              if observed.get(name, 0) < int(floors[name])]
    relaxed = [{"floor": name, "default": int(BUILD_FLOORS[name]),
                "used": int(floors[name])}
               for name in sorted(BUILD_FLOORS)
               if int(floors[name]) < int(BUILD_FLOORS[name])]
    failed_at_default = [name for name in sorted(BUILD_FLOORS)
                         if observed.get(name, 0) < int(BUILD_FLOORS[name])]
    return {**counts, "floors": {k: int(v) for k, v in floors.items()},
            "failed_floors": failed, "floors_passed": not failed,
            "floors_relaxed": relaxed,
            "floors_are_default": {k: int(v) for k, v in floors.items()} == dict(BUILD_FLOORS),
            "floors_passed_at_default": not failed_at_default,
            "failed_floors_at_default": failed_at_default,
            "floors_are": "descriptive_build_floors_not_promotion_gates"}


def era_split(events: Sequence[Mapping[str, Any]]) -> dict:
    """Split the cohort at the 2010 structural break — ``DNR:LAW-ERA-SPLIT``.

    Evidence spanning 2010 must be split: the pre-2010 biotech tape (pre-QE, pre-XBI,
    pre-breakthrough-therapy, a different FDA review clock) is a different regime, and
    a pooled estimate across it is an average of two populations reported as one.

    A single-era panel does NOT get a fabricated second era.  It gets an empty list
    for the missing era and a DISCLOSURE naming the regime evidence that is absent,
    because "we have no pre-2010 evidence" is the honest statement and inventing a
    split from post-2010 data is the dishonest one.

    An event whose own span STRADDLES the break is assignable to neither era and is
    returned under ``unassignable`` — assigning it by its midpoint would be the same
    fabrication this module refuses everywhere else."""
    break_at = datetime(ERA_BREAK_YEAR, 1, 1, tzinfo=timezone.utc)
    pre: list[str] = []
    post: list[str] = []
    unassignable: list[str] = []
    for i, ev in enumerate(events):
        eid = _event_id(ev, i)
        lower, upper = event_bounds(ev)
        if lower is None or upper is None:
            unassignable.append(eid)
        elif upper < break_at:
            pre.append(eid)
        elif lower >= break_at:
            post.append(eid)
        else:
            unassignable.append(eid)
    if pre and post:
        disclosure = (
            f"Era split applied at {ERA_BREAK_YEAR}-01-01: {len(pre)} pre-{ERA_BREAK_YEAR} "
            f"and {len(post)} post-{ERA_BREAK_YEAR} events. Read each era on its own; the "
            "pooled figure across the break is not reported."
        )
    elif post and not pre:
        disclosure = (
            f"No pre-{ERA_BREAK_YEAR} evidence exists in this panel ({len(post)} events, "
            f"all post-{ERA_BREAK_YEAR}). The pre-break regime is UNMEASURED here, not "
            "measured and found similar; nothing in this result speaks to it."
        )
    elif pre and not post:
        disclosure = (
            f"No post-{ERA_BREAK_YEAR} evidence exists in this panel ({len(pre)} events, "
            f"all pre-{ERA_BREAK_YEAR}). The panel describes a regime that ended; it does "
            "not describe the current one."
        )
    else:
        disclosure = (
            "No event in this panel could be assigned to an era: every span is "
            f"unbounded or straddles {ERA_BREAK_YEAR}-01-01. No era-conditioned claim "
            "is available."
        )
    return {"schema": EVENT_STUDY_SCHEMA,
            "law": "DNR:LAW-ERA-SPLIT",
            "break_year": ERA_BREAK_YEAR,
            "pre_2010": pre, "post_2010": post,
            "n_pre_2010": len(pre), "n_post_2010": len(post),
            "unassignable": unassignable, "n_unassignable": len(unassignable),
            "era_split_available": bool(pre and post),
            "disclosure": disclosure}


# --------------------------------------------------------------------------- #
# search-family registration — no winner out of an unregistered search
# --------------------------------------------------------------------------- #
def register_search_family(ledger, family: str, configs: Iterable[Any], *,
                           info_cutoff: Any | None = None,
                           note: str | None = None) -> dict:
    """Log the WHOLE config family to the trial ledger AT GENERATION.

    Wraps :mod:`engine.trial_ledger` — there is deliberately no second ledger in this
    module.  Registration happens before anything is estimated, because multiple
    testing is incurred when a candidate is GENERATED, not when one survives to a
    headline.  A family registered after the fact is a count chosen with knowledge of
    the answer.

    ``info_cutoff`` is passed STRAIGHT THROUGH to
    :meth:`engine.trial_ledger.TrialLedger.log_trial`, and it is the whole reason a
    ledger row is auditable later: that field is what lets a leakage audit check the
    config could not have peeked ahead.  This wrapper used to drop it, so every row
    the module wrote carried ``info_cutoff: null`` and the audit was permanently
    unavailable for exactly the search families this module registers."""
    if not family:
        raise EventStudyError("register_search_family needs a non-empty family")
    grid = list(configs)
    if not grid:
        raise EventStudyError("register_search_family needs at least one config")
    stamp = None if info_cutoff is None else _iso(_to_utc(info_cutoff, "info_cutoff"))
    n_new = ledger.log_grid(grid, family=family, source="seasonality_event_study",
                            info_cutoff=stamp, note=note)
    return {"schema": EVENT_STUDY_SCHEMA, "family": family,
            "n_configs": len(grid), "n_newly_distinct": int(n_new),
            "info_cutoff": stamp,
            "effective_n": int(ledger.effective_n(family)), "registered": True}


def family_is_registered(ledger, family: str) -> bool:
    """True iff ``family`` has a trial record in ``ledger``."""
    if ledger is None or not family:
        return False
    try:
        return family in set(ledger.families())
    except Exception:  # noqa: BLE001 - a duck-typed ledger must not crash the check
        return False


def _require_registered_family(ledger, family: str) -> int:
    if not family_is_registered(ledger, family):
        raise UnregisteredSearchFamily(
            f"search family {family!r} was never registered: call "
            "register_search_family(ledger, family, configs) at GENERATION, before "
            "any estimate is inspected. Reading the best of K configs spends K units "
            "of multiple-testing budget and an unregistered search cannot be deflated."
        )
    return int(ledger.effective_n(family))


def inspect_winner(scores: Mapping[str, float], *, ledger, family: str,
                   metric: str = "score", higher_is_better: bool = True) -> dict:
    """The best config in a search — available ONLY for a registered family.

    Raises :class:`UnregisteredSearchFamily` otherwise.  The returned row carries the
    family's ``effective_n`` beside the winner so the multiple-testing budget travels
    with the number instead of being looked up later by whoever remembers to.

    It also REFUSES to rank the declared sensitivity benchmarks.  This is a generic
    argmax, and a generic argmax fed ``{"SPY": ..., "XBI": ..., "IBB": ...}`` is the
    "pick the best benchmark" function the module docstring says does not exist here —
    registering a three-config family would otherwise buy benchmark shopping with a
    receipt attached.  SPY / XBI / IBB are sensitivity legs and
    :func:`abnormal_returns_all_benchmarks` reports all of them; there is no maximum
    to read."""
    n_eff = _require_registered_family(ledger, family)
    bench_keys = sorted(str(k) for k in scores
                        if str(k).upper() in SENSITIVITY_BENCHMARKS)
    if bench_keys:
        raise EventStudyError(
            f"refusing to rank declared sensitivity benchmarks {bench_keys}: SPY / "
            "XBI / IBB are sensitivity legs reported side by side, not a menu to take "
            "a maximum over. Read abnormal_returns_all_benchmarks' legs and report "
            "the dispersion between them; a registered family does not turn benchmark "
            "shopping into a legal search."
        )
    if not scores:
        return _abstain("no_scores_to_inspect", schema=EVENT_STUDY_SCHEMA,
                        family=family, effective_n=n_eff)
    usable = {k: float(v) for k, v in scores.items()
              if v is not None and math.isfinite(float(v))}
    if not usable:
        return _abstain("no_finite_scores", schema=EVENT_STUDY_SCHEMA,
                        family=family, effective_n=n_eff)
    pick = (max if higher_is_better else min)(sorted(usable), key=lambda k: usable[k])
    return {"schema": EVENT_STUDY_SCHEMA, "family": family, "metric": metric,
            "winner": pick, "winner_score": usable[pick],
            "n_configs_scored": len(usable), "effective_n": n_eff,
            "higher_is_better": bool(higher_is_better),
            "multiple_testing": "effective_n is the ledger's honest distinct-config "
                                "count for this family; deflate before promoting"}


# --------------------------------------------------------------------------- #
# ESTIMAND 1 — ex-post reaction (descriptive; may see the event's own resolution)
# --------------------------------------------------------------------------- #
def estimate_reaction(prices_by_issuer: Mapping[str, Any],
                      events: Sequence[Mapping[str, Any]], *,
                      benchmarks: Mapping[str, Any] | None = None,
                      model: str = "market",
                      estimation: tuple[int, int] = (-250, -31),
                      window: tuple[int, int] = (-10, 10),
                      min_estimation: int = 60,
                      date_cluster: str = "month",
                      floors: Mapping[str, int] | None = None,
                      max_span_seconds: float = MAX_EVENT_SPAN_SECONDS,
                      B: int = 5000, seed: int = 11,
                      exclude_contaminated: bool = True,
                      select_winner: bool = False,
                      ledger=None, family: str | None = None) -> dict:
    """ESTIMAND 1: what the tape DID around a cohort of realized events.

    Ex-post and descriptive.  This function may use information revealed at or after
    the event — it knows the event happened and how it resolved — and nothing it
    returns is tradable.  ``forecast_ex_ante`` is the other estimand and shares no
    code path with this one.

    Pipeline, in order, with a named abstention at every step that can fail:

    1. Each event's temporal span is screened by :func:`event_interval_policy`; a span
       wider than the declared threshold is dropped with a reason, never centred.
    2. CONTAMINATED events — an event whose study window overlaps another event on the
       same issuer — are dropped by name (``exclude_contaminated=True``, the default).
       :func:`flag_contamination`'s own docstring says pooling them in is how a
       strong-looking cohort mean turns out to be twelve issuers announcing
       financings; computing the flag and then pooling anyway would make the flag
       decoration.  Pass ``exclude_contaminated=False`` to pool them deliberately —
       the choice is then recorded in ``contamination_policy`` rather than implicit.
    3. Build floors (:func:`check_build_floors`) are checked BEFORE any statistic is
       computed, and on the cohort that will ACTUALLY be estimated (post-drop), so a
       thin cohort abstains instead of producing a confident number from twelve
       events.
    4. Per benchmark leg (all of them, no chooser): per-event abnormal returns, then
       :func:`bmp_test` on the EVENT-WINDOW columns only, :func:`corrado_rank_test`
       over the whole ranking period, and :func:`clustered_bootstrap_ci` on the TIME
       clusters.
    5. Contamination flags, the era split, and the cohort counts ride along with the
       result, because a CAR without its ``effective_n`` and its era disclosure is
       exactly the number that gets quoted out of context.

    ``select_winner=True`` DECLARES that this estimate will be read as the winner of a
    search: it requires ``ledger`` and ``family``, refuses on an unregistered family,
    and stamps the family's multiple-testing budget onto the result as
    ``search_family``.  It selects nothing itself — this function has one
    configuration and reports every benchmark leg — so the flag is a budget
    declaration, not a chooser."""
    events = list(events)
    search_family = None
    if select_winner:
        n_eff = _require_registered_family(ledger, family or "")
        search_family = {"family": family, "effective_n": int(n_eff),
                         "registered": True,
                         "multiple_testing": "deflate any headline read out of this "
                                             "family by effective_n before promoting"}
    bench_map = dict(benchmarks or {})
    if model != "raw" and not bench_map:
        raise EventStudyError("a non-raw model needs at least one benchmark leg")

    eligible: list[tuple[Mapping[str, Any], str, str, datetime]] = []
    dropped: list[dict[str, Any]] = []
    for i, ev in enumerate(events):
        eid, issuer = _event_id(ev, i), _issuer_id(ev)
        try:
            temporal = event_temporal(ev)
        except (EventStudyError, ContractError) as exc:
            dropped.append({"event_id": eid, "issuer_id": issuer,
                            "reason": f"unreadable_temporal:{exc}"})
            continue
        policy = event_interval_policy(temporal, max_span_seconds=max_span_seconds)
        if policy.get("mode") != "point":
            dropped.append({"event_id": eid, "issuer_id": issuer,
                            "reason": policy.get("reason") or "interval_policy_not_point",
                            "span_seconds": policy.get("span_seconds")})
            continue
        eligible.append((ev, eid, issuer, _to_utc(policy["lower"], "lower")))

    contamination = flag_contamination([ev for ev, _e, _i, _d in eligible],
                                       window=window)
    contaminated_ids = {row["event_id"] for row in contamination}
    if exclude_contaminated and contaminated_ids:
        kept: list[tuple[Mapping[str, Any], str, str, datetime]] = []
        for ev, eid, issuer, anchor in eligible:
            if eid in contaminated_ids:
                dropped.append({"event_id": eid, "issuer_id": issuer,
                                "reason": "contaminated_by_overlapping_event"})
            else:
                kept.append((ev, eid, issuer, anchor))
        eligible = kept

    eligible_events = [ev for ev, _e, _i, _d in eligible]
    floor_report = check_build_floors(eligible_events, floors=floors,
                                      date_cluster=date_cluster)
    counts = {k: floor_report[k] for k in
              ("n_events", "n_issuers", "n_date_clusters", "effective_n")}
    head = {"schema": EVENT_STUDY_SCHEMA, "estimand": "ex_post_reaction",
            "is_tradable": False,
            "model": model, "estimation": [int(estimation[0]), int(estimation[1])],
            "window": [int(window[0]), int(window[1])],
            "benchmarks": sorted(bench_map), "selection_policy": "all_legs_reported",
            "n_events_supplied": len(events),
            "n_events_dropped": len(dropped), "dropped_events": dropped,
            "build_floors": floor_report,
            "era": era_split(eligible_events),
            "contamination": contamination,
            "n_contaminated": len(contaminated_ids),
            "contamination_policy": ("excluded_from_pooled_statistics"
                                     if exclude_contaminated else
                                     "pooled_in_deliberately_by_caller"),
            "search_family": search_family,
            **counts}
    if not floor_report["floors_passed"]:
        failed = floor_report["failed_floors"]
        names = ",".join(f"{f['floor']}({f['observed']}<{f['required']})" for f in failed)
        return {**head, **_abstain(f"build_floor_not_met:{names}"),
                "legs": {}, "seed": int(seed), "B": int(B)}

    legs: dict[str, dict] = {}
    leg_names = sorted(bench_map) if bench_map else ["__raw__"]
    for name in leg_names:
        bench_series = bench_map.get(name)
        per_event: list[dict[str, Any]] = []
        car_rows, sigma_rows, ar_rows, time_clusters, issuer_clusters = [], [], [], [], []
        for ev, eid, issuer, anchor in eligible:
            px = prices_by_issuer.get(issuer)
            if px is None:
                per_event.append({"event_id": eid, "issuer_id": issuer,
                                  "abstained": True, "reason": "no_price_series_for_issuer"})
                continue
            res = abnormal_returns(px, anchor, benchmark=bench_series, model=model,
                                   estimation=estimation, window=window,
                                   min_estimation=min_estimation,
                                   with_estimation_ar=True)
            res["event_id"], res["issuer_id"] = eid, issuer
            per_event.append(res)
            if res.get("abstained"):
                continue
            car_rows.append(res["car"])
            sigma_rows.append(res["sigma_estimation"])
            merged = dict(res.get("ar_estimation") or {})
            merged.update(res["ar"])
            ar_rows.append(merged)
            time_clusters.append(date_cluster_key(anchor, date_cluster))
            issuer_clusters.append(issuer)
        leg = {"benchmark": None if bench_series is None else name,
               "n_estimated": len(car_rows), "per_event": per_event}
        if len(car_rows) < 2:
            leg.update(_abstain("insufficient_estimated_events_lt_2"))
            legs[name] = leg
            continue
        cols = sorted(set().union(*(set(r) for r in ar_rows)))
        full = pd.DataFrame([[r.get(c, float("nan")) for c in cols] for r in ar_rows],
                            columns=cols)
        event_cols = [c for c in cols if int(window[0]) <= c <= int(window[1])]
        # BMP is a test of the EVENT WINDOW.  Handing it the ranking period as well
        # is silent under model="market" (OLS residuals sum to zero, so the CAR and a
        # scale-invariant t survive) and flips the answer under market_adjusted, so
        # the column count is checked rather than assumed.
        expected_window = int(window[1]) - int(window[0]) + 1
        if len(event_cols) != expected_window:
            raise EventStudyError(
                f"internal: {len(event_cols)} event-window columns for a declared "
                f"window of {expected_window} days {list(window)}")
        leg["bmp"] = bmp_test(full[event_cols], sigma_rows)
        if leg["bmp"].get("window_len") != expected_window:
            raise EventStudyError(
                f"internal: bmp_test saw {leg['bmp'].get('window_len')} columns for a "
                f"declared event window of {expected_window} days")
        leg["corrado_rank"] = corrado_rank_test(full, event_cols=event_cols)
        leg["clustered_ci"] = clustered_bootstrap_ci(
            car_rows, {"date_cluster": time_clusters, "issuer_id": issuer_clusters},
            B=B, seed=seed)
        # DNR:LAW-TIME-CLUSTERED-CI is enforced on the SIGNATURE; this is the call
        # site's half — the labels handed under the time key must be the calendar
        # clusters, not the issuer labels wearing a date key's name.
        if (not leg["clustered_ci"].get("abstained")
                and leg["clustered_ci"].get("n_time_clusters") != len(set(time_clusters))):
            raise EventStudyError(
                "internal: the clustered CI was given "
                f"{leg['clustered_ci'].get('n_time_clusters')} time clusters but the "
                f"estimated cohort spans {len(set(time_clusters))} calendar clusters")
        leg["mean_car"] = float(np.mean(car_rows))
        leg["abstained"] = False
        leg["reason"] = None
        legs[name] = leg
    return {**head, "legs": legs, "abstained": False, "reason": None,
            "seed": int(seed), "B": int(B)}


# --------------------------------------------------------------------------- #
# ESTIMAND 2 — ex-ante tradable forecast (separate object, separate code path)
# --------------------------------------------------------------------------- #
def _name_tokens(name: Any) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", str(name).lower()) if t]


def _realized_outcome_match(name: Any, forbidden_keys: Iterable[str]) -> str | None:
    """The forbidden key a feature name matches, or ``None``.

    Matching is on TOKEN SUBSEQUENCES, not string equality.  Exact equality was the
    original rule and it refused ``outcome`` while waving through
    ``actual_outcome_pdufa``, ``realized_car_5d``, ``trial_result`` and
    ``post_event_car`` — every realistic spelling of the thing it exists to stop.  A
    leak guard that only catches the name nobody would actually use is decoration."""
    tokens = _name_tokens(name)
    if not tokens:
        return None
    for key in sorted({str(k) for k in forbidden_keys}):
        want = _name_tokens(key)
        if not want:
            continue
        span = len(want)
        for i in range(len(tokens) - span + 1):
            if tokens[i:i + span] == want:
                return key
    return None


def forecast_ex_ante(*, event: Mapping[str, Any], features: Mapping[str, Mapping[str, Any]],
                     decision_cutoff: Any, trading_bars: Sequence[Any],
                     risk_set: Sequence[str], event_policy: Mapping[str, Any],
                     outcome_policy: Mapping[str, Any],
                     prediction_issued_at: Any | None = None,
                     forbidden_keys: Iterable[str] = ()) -> dict:
    """ESTIMAND 2: a frozen, tradable ex-ante row.  Shares NO code path with
    :func:`estimate_reaction` — it does not compute abnormal returns and cannot see a
    realized outcome, by construction rather than by discipline.

    THE DECISION CUTOFF MUST PRECEDE THE EVENT.  ``decision_cutoff`` is checked
    against the event's own span, and a cutoff at or after the event opens abstains by
    name.  Without that check the ``known_at <= cutoff`` rule is vacuous: nothing
    stopped a caller from passing a cutoff three weeks AFTER the readout, at which
    point ``{"price_move_since_readout": {"known_at": <the day after the event>}}`` is
    a legal, non-abstaining, ``is_tradable: True`` row whose only feature is the
    realized reaction.  The leak needs no shared helper and no forbidden name — it
    walks in through the front door — so the temporal relation between the cutoff and
    the event is enforced here rather than assumed of the caller.

    ``features`` maps a feature name to ``{"value": ..., "known_at": ..., optional
    "published"/"available_at"/"source_temporal"}``.  Every feature MUST carry a
    ``known_at``; a feature whose ``known_at`` is after ``decision_cutoff`` is a leak
    and the row abstains, naming the offending features (a feature known EXACTLY at
    the cutoff is legal — the cutoff is inclusive, and that boundary is pinned by
    test).  A feature named like a realized outcome (``REALIZED_OUTCOME_KEYS``) is
    refused regardless of its timestamp, because a convincing timestamp on a
    resolution field is the exact shape of the bug; matching is on name TOKENS, so
    ``realized_car_5d`` and ``post_event_car`` are refused too, and
    ``forbidden_keys`` ADDS to that set rather than replacing it — passing ``()`` can
    no longer switch the guard off.

    A fact carrying a REVISION stamp (``revised_at`` / ``restated_at`` / ``vintage``,
    ``REVISION_TIME_KEYS``) later than the cutoff is refused by name.  A restated
    value keeping its original ``known_at`` is the canonical point-in-time failure and
    the only thing that made it "detectable" before was a hash nobody stored.

    What each row freezes, permanently:

    * ``prediction_issued_at`` — defaults to the decision cutoff.  There is NO wall
      clock read here: a row stamped with "now" is not reproducible, and a rebuild
      six months later would silently claim a different issue time.
    * ``feature_snapshot`` + ``feature_snapshot_hash`` — the exact cut, hashed, so a
      later revision of any input is detectable rather than absorbed.
    * ``risk_set`` — the names that were eligible at the cutoff, not the ones that
      survived to today.
    * ``event_policy`` / ``outcome_policy`` — what counted as an event and how it
      would be graded, fixed before the answer is known.
    * ``availability_receipt`` — :func:`earliest_executable_bar`'s full receipt, and
      the ``execution_bar`` it resolved.  A feature published before the cutoff but
      only AVAILABLE after it pushes execution later; that is correct and is the
      difference between a backtest and a forecast of the past.
    """
    cutoff = _to_utc(decision_cutoff, "decision_cutoff")
    issued = cutoff if prediction_issued_at is None else _to_utc(
        prediction_issued_at, "prediction_issued_at")
    if not isinstance(features, Mapping) or not features:
        raise EventStudyError("features must be a non-empty mapping of name -> fact")
    forbidden = set(REALIZED_OUTCOME_KEYS) | {str(k) for k in forbidden_keys}

    event_lower, event_upper = event_bounds(event)

    snapshot: dict[str, Any] = {}
    facts: list[dict[str, Any]] = []
    leaks: list[str] = []
    banned: list[dict[str, str]] = []
    revised: list[dict[str, str]] = []
    for name in sorted(features):
        fact = features[name]
        if not isinstance(fact, Mapping):
            raise EventStudyError(f"features[{name!r}] must be a mapping with a known_at")
        hit = _realized_outcome_match(name, forbidden)
        if hit is not None:
            banned.append({"feature": str(name), "matched": str(hit)})
            continue
        if fact.get("known_at") is None:
            raise EventStudyError(
                f"features[{name!r}] has no known_at; an ex-ante feature with no "
                "availability timestamp cannot be proven to precede the cutoff")
        known_at = _to_utc(fact["known_at"], f"features[{name!r}].known_at")
        if known_at > cutoff:
            leaks.append(str(name))
            continue
        late_revision = None
        for key in REVISION_TIME_KEYS:
            if fact.get(key) is None:
                continue
            stamp = _to_utc(fact[key], f"features[{name!r}].{key}")
            if stamp > cutoff:
                late_revision = {"feature": str(name), "key": key,
                                 "revised_at": _iso(stamp)}
                break
        if late_revision is not None:
            revised.append(late_revision)
            continue
        snapshot[str(name)] = fact.get("value")
        entry = {"id": str(name), "known_at": _iso(known_at)}
        for key in ("published", "published_at", "available", "available_at"):
            if fact.get(key) is not None:
                entry[key] = _iso(_to_utc(fact[key], f"features[{name!r}].{key}"))
        # The availability SPAN travels too.  earliest_executable_bar reads
        # source_temporal.upper_bound as an availability stamp; rebuilding the fact
        # from four flat keys silently dropped it, so a feature whose availability was
        # declared as a span contributed nothing to the execution clock and the row
        # executed at the cutoff bar — the exact "price nobody could have paid" case
        # that function exists to prevent.
        if isinstance(fact.get("source_temporal"), Mapping):
            entry["source_temporal"] = validate_source_temporal(
                fact["source_temporal"], f"features[{name!r}].source_temporal")
        facts.append(entry)

    row = {
        "schema": EX_ANTE_ROW_SCHEMA,
        "estimand": "ex_ante_tradable",
        "is_tradable": True,
        "event_id": _event_id(event, 0),
        "issuer_id": _issuer_id(event),
        "prediction_issued_at": _iso(issued),
        "decision_cutoff": _iso(cutoff),
        "feature_snapshot": snapshot,
        "feature_snapshot_hash": _canonical_hash(snapshot),
        "n_features": len(snapshot),
        "risk_set": sorted(str(r) for r in risk_set),
        "n_risk_set": len(set(map(str, risk_set))),
        "event_policy": dict(event_policy),
        "outcome_policy": dict(outcome_policy),
        "event_lower": _iso(event_lower),
        "event_upper": _iso(event_upper),
        "leaking_features": sorted(leaks),
        "realized_outcome_features_refused": sorted(b["feature"] for b in banned),
        "realized_outcome_matches": sorted(banned, key=lambda b: b["feature"]),
        "revised_features_refused": sorted(revised, key=lambda r: r["feature"]),
        "availability_receipt": None,
        "execution_bar": None,
        "abstained": False,
        "reason": None,
    }
    # The cutoff-vs-event relation is checked FIRST: if the decision cutoff is not
    # before the event, no feature timestamp can rescue the row, and every other
    # refusal below would be reporting a symptom of this one.
    if event_lower is None:
        row.update({"abstained": True,
                    "reason": "event_span_not_study_eligible_for_cutoff_check"})
        return row
    if cutoff >= event_lower:
        row.update({"abstained": True,
                    "reason": f"decision_cutoff_not_before_event:"
                              f"cutoff={_iso(cutoff)}>=event_opens={_iso(event_lower)}"})
        return row
    if banned:
        names = sorted(b["feature"] for b in banned)
        row.update({"abstained": True,
                    "reason": f"realized_outcome_in_feature_cut:{names}"})
        return row
    if revised:
        names = sorted(r["feature"] for r in revised)
        row.update({"abstained": True,
                    "reason": f"revision_after_decision_cutoff:{names}"})
        return row
    if leaks:
        row.update({"abstained": True,
                    "reason": f"feature_known_after_decision_cutoff:{sorted(leaks)}"})
        return row
    if not snapshot:
        row.update({"abstained": True, "reason": "empty_feature_cut"})
        return row
    receipt = earliest_executable_bar(cutoff, facts, trading_bars=trading_bars)
    row["availability_receipt"] = receipt
    row["execution_bar"] = receipt.get("execution_bar")
    if receipt.get("abstained"):
        row.update({"abstained": True, "reason": receipt.get("reason")})
    return row


__all__ = [
    "ABSTENTION_SCHEMA",
    "AR_MODELS",
    "AVAILABILITY_RECEIPT_SCHEMA",
    "BUILD_FLOORS",
    "ERA_BREAK_YEAR",
    "EVENT_STUDY_SCHEMA",
    "EX_ANTE_ROW_SCHEMA",
    "EventStudyError",
    "ISSUER_CLUSTER_KEYS",
    "MAX_EVENT_SPAN_SECONDS",
    "REALIZED_OUTCOME_KEYS",
    "REVISION_TIME_KEYS",
    "SENSITIVITY_BENCHMARKS",
    "TIME_CLUSTER_KEYS",
    "UnregisteredSearchFamily",
    "abnormal_returns",
    "abnormal_returns_all_benchmarks",
    "bmp_test",
    "check_build_floors",
    "clustered_bootstrap_ci",
    "cohort_counts",
    "corrado_rank_test",
    "date_cluster_key",
    "earliest_executable_bar",
    "era_split",
    "estimate_reaction",
    "event_bounds",
    "event_interval_policy",
    "event_temporal",
    "family_is_registered",
    "flag_contamination",
    "forecast_ex_ante",
    "inspect_winner",
    "interval_sensitivity_anchors",
    "matched_controls",
    "perturb_event_dates",
    "placebo_dates",
    "register_search_family",
]
