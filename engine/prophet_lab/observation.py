"""engine/prophet_lab/observation.py — observation-class classification (LAB-0 §4).

Pure functions over already-read data: no filesystem access happens here (see
``sources.py`` for that).  The rule, restated from the frozen doc:

* No baseline marker at all -> EVERY event is ``retrospective_seed``
  (fail-honest: the absence of proof of a continuous live baseline is treated
  as proof of absence, never as "probably fine").
* A baseline exists -> an event is ``live_forward`` only when its
  ``first_observed_at`` (earliest spool envelope ``pass_ts``) falls inside the
  claimed continuous-coverage window: at or after ``baseline_started_at`` and,
  when ``continuous_through`` is given, at or before it.
* Everything else (no known first observation, before the baseline, after the
  claimed coverage window) is ``retrospective_seed``.

Seeds always carry ``evidence_eligible=False`` and a ``None`` measured lead —
the LAB-0 §4 rule that only true live_forward observations may ever show a
measured Lab→Prophet lead.
"""
from __future__ import annotations

from typing import Any, Mapping

from engine.prophet_lab.contracts import (
    OBSERVATION_LIVE_FORWARD,
    OBSERVATION_RETROSPECTIVE_SEED,
)
from engine.prophet_lab.timeparse import parse_instant


def classify_observation(
    event_id: str,
    *,
    first_observed_at: Mapping[str, str],
    baseline: Mapping[str, Any] | None,
) -> str:
    """The ``observation_class`` for one event, per the rule above.

    Temporal correctness amendment (day-2 reconciliation): every comparison
    here is an INSTANT comparison via :func:`engine.prophet_lab.timeparse.parse_instant`,
    never a raw string compare — ``"2026-08-19T10:00:00Z"`` and
    ``"2026-08-19T06:00:00-04:00"`` name the SAME instant and must classify
    identically, which a lexicographic compare cannot guarantee (see
    ``timeparse.py``'s module docstring for the measured failure mode this
    replaces). An unparseable OR naive (no UTC offset) timestamp anywhere in
    this comparison — the observation itself, ``baseline_started_at``, or a
    present ``continuous_through`` — fails CLOSED to ``retrospective_seed``,
    the same fail-honest default this function already used for a missing
    baseline or a missing observation.
    """
    if not baseline:
        return OBSERVATION_RETROSPECTIVE_SEED
    observed = parse_instant(first_observed_at.get(event_id))
    if observed is None:
        return OBSERVATION_RETROSPECTIVE_SEED
    started = parse_instant(baseline.get("baseline_started_at"))
    if started is None or observed < started:
        return OBSERVATION_RETROSPECTIVE_SEED
    continuous_through_raw = baseline.get("continuous_through")
    if continuous_through_raw:
        through = parse_instant(continuous_through_raw)
        if through is None or observed > through:
            return OBSERVATION_RETROSPECTIVE_SEED
    return OBSERVATION_LIVE_FORWARD


def evidence_eligible(observation_class: str) -> bool:
    """Only a true live_forward observation is evidence-eligible (LAB-0 §4)."""
    return observation_class == OBSERVATION_LIVE_FORWARD


def measured_lead_days(
    observation_class: str,
    *,
    first_observed_at: str | None,
    prophet_anchor_at: str | None,
) -> int | None:
    """Days between the Lab's first observation and the Prophet plan anchor.

    ``None`` unless the row is ``live_forward`` AND both timestamps are
    present — a seed NEVER shows a measured lead, always, per LAB-0 §4.  Both
    timestamps are truncated to their date component before differencing so a
    fixture supplying bare ``YYYY-MM-DD`` values (as Prophet plan dates are)
    still produces a lead against a full ISO-8601 spool timestamp.

    Review B1: a lead is reported ONLY when the Prophet anchor POSTDATES the
    Lab's first observation — i.e. only when the Lab genuinely led Prophet.
    An anchor at or before the Lab's observation is not a "negative lead", it
    is a different fact entirely (Prophet recorded the name before the Lab's
    baseline saw it, or on the same day) and is never emitted as a signed
    lead — this function returns ``None`` for that case rather than a
    negative or zero integer a UI could mistake for "the Lab was N days
    behind".
    """
    if observation_class != OBSERVATION_LIVE_FORWARD:
        return None
    if not first_observed_at or not prophet_anchor_at:
        return None
    from datetime import date  # noqa: PLC0415

    try:
        lab_date = date.fromisoformat(str(first_observed_at)[:10])
        prophet_date = date.fromisoformat(str(prophet_anchor_at)[:10])
    except ValueError:
        return None
    lead = (prophet_date - lab_date).days
    return lead if lead > 0 else None


__all__ = ["classify_observation", "evidence_eligible", "measured_lead_days"]
