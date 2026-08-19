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


def classify_observation(
    event_id: str,
    *,
    first_observed_at: Mapping[str, str],
    baseline: Mapping[str, Any] | None,
) -> str:
    """The ``observation_class`` for one event, per the rule above."""
    if not baseline:
        return OBSERVATION_RETROSPECTIVE_SEED
    observed_at = first_observed_at.get(event_id)
    if not observed_at:
        return OBSERVATION_RETROSPECTIVE_SEED
    started_at = str(baseline.get("baseline_started_at") or "")
    if not started_at or observed_at < started_at:
        return OBSERVATION_RETROSPECTIVE_SEED
    continuous_through = baseline.get("continuous_through")
    if continuous_through and observed_at > str(continuous_through):
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
    return (prophet_date - lab_date).days


__all__ = ["classify_observation", "evidence_eligible", "measured_lead_days"]
