"""Pure projection: BioCatalyst trial rows -> Trial Milestone Radar events.

This module is wave P1-1 of the BioCatalyst Trial Milestone Radar vertical
(``WS:BIOCATALYST-CORE-PRODUCT``). It takes ALREADY-PUBLIC-SHAPED trial rows
-- exactly the shape ``app/biocatalyst.py:_public_trial(snapshot,
detail=False)`` returns -- and turns them into deterministic, request-local
Trial Milestone event rows. A later packet layers an API endpoint and a UI on
top of this module, so its contract is frozen: names, shapes, and behavior
here are load-bearing for a downstream builder.

Hard character constraints:

* pure functions over data passed in -- no network, no filesystem reads, no
  database, no reading the runtime clock in any form, no module-level
  mutable state, no cache of any kind, no reaching into the serving app's
  own module tree;
* same inputs always produce identical outputs (unit-tested determinism);
* these rows are REGISTRY SCHEDULE FACTS, never signals -- no numeric
  importance, likelihood, priority, ordering, trust, weighting, or any
  combined-signal field is ever emitted anywhere in this module or its
  output; and
* the ``evidence`` block is a public-safety boundary: only the documented
  keys ever reach the output, regardless of what a caller's input carries
  alongside them (never a filesystem path, R2 object key, private hash,
  manifest digest, or worker receipt).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import re
from typing import Any, Mapping, Sequence

from engine.biocatalyst.sponsor_identity import resolve_sponsor

# --------------------------------------------------------------------------
# Public constants (frozen contract -- exact names and values, see §2)
# --------------------------------------------------------------------------

RADAR_EVENT_KINDS: tuple[str, ...] = ("primary_completion", "completion")
RADAR_HORIZONS: dict[str, int | None] = {
    "next_180d": 180,
    "next_365d": 365,
    "next_730d": 730,
    "all": None,
}
DEFAULT_RADAR_HORIZON = "next_365d"
TIMING_STATES = ("occurred", "current", "upcoming", "beyond_horizon")
HALTED_TRIAL_STATUSES = frozenset({"TERMINATED", "WITHDRAWN", "SUSPENDED"})

# --------------------------------------------------------------------------
# Internal constants
# --------------------------------------------------------------------------

_PARTIAL_ISO_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
_DATE_TYPES = frozenset({"ACTUAL", "ESTIMATED", "UNKNOWN"})

# Real ClinicalTrials.gov API v2 field names. Case-sensitive substring
# matching keeps these disjoint: "completionDateStruct" (lowercase c) is
# never a substring of "primaryCompletionDateStruct" (capital C).
_REVISION_KIND_MARKERS: dict[str, str] = {
    "primary_completion": "primaryCompletionDateStruct",
    "completion": "completionDateStruct",
}

# SUSPENDED is PAUSED, not terminal -- see §6a. Deliberately not named with
# the word this module and its tests must never use for a schedule fact.
_STATUS_ACTIVITY: dict[str, tuple[str, str]] = {
    "TERMINATED": ("inactive", "trial_terminated"),
    "WITHDRAWN": ("inactive", "trial_withdrawn"),
    "SUSPENDED": ("paused", "trial_suspended"),
}

# A caller's per-NCT evidence override never traverses this module as an
# opaque mapping -- only these two names are ever pulled out of it, so a
# caller smuggling object_key/receipt/path/sha256 (or anything else)
# alongside url/coverage cannot leak it into the served row.
_EVIDENCE_OVERRIDE_URL_KEY = "url"
_EVIDENCE_OVERRIDE_COVERAGE_KEY = "coverage"

# company_identity is ALWAYS this exact, fixed value (§6b): verified, no
# populated PIT Company/Stock Identity read seam exists in this repo (the
# only non-test IssuerRegistry construction is a hardcoded single-company
# fixture), so a ticker is never promoted to a company identity here.
_COMPANY_IDENTITY: dict[str, str] = {
    "state": "company_identity_not_joined",
    "reason": "no_pit_company_identity_seam",
}


@dataclass(frozen=True)
class CatalystEvent:
    """One Trial Milestone Radar row (§6 -- exact top-level keys, no others)."""

    event_id: str
    nct_id: str
    kind: str
    trial: Mapping[str, Any]
    milestone: Mapping[str, Any]
    timing: Mapping[str, Any]
    trial_status: Mapping[str, Any]
    issuer: Mapping[str, Any]
    revision: Mapping[str, Any]
    evidence: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "nct_id": self.nct_id,
            "kind": self.kind,
            "trial": dict(self.trial),
            "milestone": dict(self.milestone),
            "timing": dict(self.timing),
            "trial_status": dict(self.trial_status),
            "issuer": dict(self.issuer),
            "revision": dict(self.revision),
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class RadarProjection:
    """Projection result: ordered rows to render, plus a denominator-honest coverage map."""

    events: tuple[CatalystEvent, ...]
    coverage: Mapping[str, Any]


def _milestone_date_interval(value: object) -> tuple[date, date, str] | None:
    """Expand a partial-ISO source date into the full civil interval it denotes.

    Reimplements ``app/biocatalyst.py:_milestone_date_interval`` exactly
    (this module may not import ``app.*``): a partial value is the complete
    civil interval it denotes, never a point estimate.
    """

    if not isinstance(value, str) or not _PARTIAL_ISO_DATE.fullmatch(value):
        return None
    try:
        if len(value) == 4:
            year = int(value)
            return date(year, 1, 1), date(year, 12, 31), "year"
        if len(value) == 7:
            year_text, month_text = value.split("-")
            year, month = int(year_text), int(month_text)
            start = date(year, month, 1)
            if month == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, month + 1, 1) - timedelta(days=1)
            return start, end, "month"
        parsed = date.fromisoformat(value)
        return parsed, parsed, "day"
    except ValueError:
        return None


def _classify_timing(
    interval_start: date,
    interval_end: date,
    anchor_date: date,
    horizon_days: int | None,
    precision: str,
) -> tuple[str, dict[str, int | None] | None, int | None]:
    """Total classification into TIMING_STATES plus precision-honest day counts (§5)."""

    if interval_end < anchor_date:
        state = "occurred"
    elif interval_start <= anchor_date <= interval_end:
        state = "current"
    elif horizon_days is None:
        state = "upcoming"
    else:
        threshold = anchor_date + timedelta(days=horizon_days - 1)
        state = "upcoming" if interval_end <= threshold else "beyond_horizon"

    days_to_milestone: dict[str, int | None] | None = None
    days_since_milestone: int | None = None
    if state == "occurred":
        days_since_milestone = (anchor_date - interval_end).days
    elif state in ("upcoming", "beyond_horizon"):
        if precision == "day":
            exact = (interval_start - anchor_date).days
            days_to_milestone = {"exact": exact, "min": exact, "max": exact}
        else:
            # Month/year precision never gets a point estimate -- only the
            # honest [min, max] the source's own imprecision allows.
            days_to_milestone = {
                "exact": None,
                "min": (interval_start - anchor_date).days,
                "max": (interval_end - anchor_date).days,
            }
    return state, days_to_milestone, days_since_milestone


def _sponsor_name(value: object) -> str | None:
    """Read a trial's sponsor value defensively: a mapping with 'name', or a plain string."""

    if isinstance(value, Mapping):
        name = value.get("name")
        return name if isinstance(name, str) and name else None
    if isinstance(value, str) and value:
        return value
    return None


def _trial_status_block(value: object) -> dict[str, Any]:
    """§6a -- value preserved verbatim; activity/reason_code derived from value.upper()."""

    activity = "active"
    reason_code: str | None = None
    if isinstance(value, str):
        mapped = _STATUS_ACTIVITY.get(value.upper())
        if mapped is not None:
            activity, reason_code = mapped
    return {"value": value, "activity": activity, "reason_code": reason_code}


def _issuer_block(
    sponsor_name: str | None,
    sponsor_document: Mapping[str, Any] | None,
    sponsor_as_of: str | None,
) -> dict[str, Any]:
    """§6b -- typed absence, never a guess. company_identity is always fixed."""

    if sponsor_document is None or sponsor_as_of is None:
        state, ticker, issuer_relationship = "sponsor_map_unavailable", None, None
    elif not sponsor_name:
        state, ticker, issuer_relationship = "sponsor_name_absent", None, None
    else:
        try:
            resolution = resolve_sponsor(sponsor_name, as_of=sponsor_as_of, document=sponsor_document)
        except Exception:
            # resolve_sponsor must never be allowed to propagate out of a
            # pure projection -- an unavailable map is an unavailable map.
            state, ticker, issuer_relationship = "sponsor_map_unavailable", None, None
        else:
            if resolution.status == "resolved":
                state = "ticker_only"
                ticker = resolution.ticker
                issuer_relationship = resolution.issuer_relationship
            else:
                state, ticker, issuer_relationship = "unresolved_sponsor", None, None
    return {
        "state": state,
        "sponsor_name": sponsor_name,
        "ticker": ticker,
        "issuer_relationship": issuer_relationship,
        "company_identity": dict(_COMPANY_IDENTITY),
    }


def _revision_side_date(value: object) -> str | None:
    """Extract a raw before/after date string from a revision row side, defensively."""

    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        candidate = value.get("date")
        if isinstance(candidate, str):
            return candidate
    return None


def _version_int(versions: object, key: str) -> int | None:
    if not isinstance(versions, Mapping):
        return None
    value = versions.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _revision_block(
    nct_id: str,
    kind: str,
    revisions_by_nct: Mapping[str, Sequence[Mapping[str, Any]]] | None,
) -> dict[str, Any]:
    """§6c -- lineage from public change rows, matched by json_path marker."""

    if not isinstance(revisions_by_nct, Mapping) or nct_id not in revisions_by_nct:
        return {"state": "history_not_collected", "count": 0, "latest": None}
    entries = revisions_by_nct.get(nct_id)
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        return {"state": "history_not_collected", "count": 0, "latest": None}

    marker = _REVISION_KIND_MARKERS[kind]
    matching: list[Mapping[str, Any]] = []
    for row in entries:
        if not isinstance(row, Mapping):
            continue
        path = row.get("json_path")
        if not isinstance(path, str):
            path = row.get("source_json_path")
        if not isinstance(path, str) or marker not in path:
            continue
        matching.append(row)
    if not matching:
        return {"state": "no_revisions_recorded", "count": 0, "latest": None}

    best_index: int | None = None
    best_sort: tuple[int, int] | None = None
    for index, row in enumerate(matching):
        after = _version_int(row.get("source_versions"), "after")
        candidate_sort = (after if after is not None else -1, index)
        if best_sort is None or candidate_sort >= best_sort:
            best_sort = candidate_sort
            best_index = index
    best_row = matching[best_index]  # type: ignore[index]
    versions = best_row.get("source_versions")
    observed_at = best_row.get("observed_at")
    latest = {
        "from": _revision_side_date(best_row.get("before")),
        "to": _revision_side_date(best_row.get("after")),
        "from_version": _version_int(versions, "before"),
        "to_version": _version_int(versions, "after"),
        "observed_at": observed_at if isinstance(observed_at, str) else None,
    }
    return {"state": "has_revisions", "count": len(matching), "latest": latest}


def _evidence_block(
    nct_id: str,
    trial: Mapping[str, Any],
    evidence_by_nct: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """§6d -- public-safe evidence. Named-key extraction only, never a dict spread."""

    override: Mapping[str, Any] | None = None
    if isinstance(evidence_by_nct, Mapping):
        candidate = evidence_by_nct.get(nct_id)
        if isinstance(candidate, Mapping):
            override = candidate

    url: str | None = None
    coverage: Any = None
    if override is not None:
        raw_url = override.get(_EVIDENCE_OVERRIDE_URL_KEY)
        if isinstance(raw_url, str):
            url = raw_url
        raw_coverage = override.get(_EVIDENCE_OVERRIDE_COVERAGE_KEY)
        if raw_coverage is None or isinstance(raw_coverage, (str, int, float, bool)):
            coverage = raw_coverage

    updated_at = trial.get("updated_at")
    retrieved_at = trial.get("retrieved_at")
    return {
        "provider": "ClinicalTrials.gov",
        "record_id": nct_id,
        "url": url,
        "source_clocks": {
            "updated_at": updated_at if isinstance(updated_at, str) else None,
            "retrieved_at": retrieved_at if isinstance(retrieved_at, str) else None,
        },
        "coverage": coverage,
    }


def _trial_block(trial: Mapping[str, Any]) -> dict[str, Any]:
    def _text(key: str) -> str | None:
        value = trial.get(key)
        return value if isinstance(value, str) else None

    def _text_list(key: str) -> list[str]:
        value = trial.get(key)
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [item for item in value if isinstance(item, str)]

    return {
        "title": _text("title"),
        "brief_title": _text("brief_title"),
        "phases": _text_list("phases"),
        "conditions": _text_list("conditions"),
        "study_type": _text("study_type"),
    }


def project_trial_milestones(
    *,
    trials: Sequence[Mapping[str, Any]],
    anchor_date: date,
    horizon_days: int | None,
    kinds: Sequence[str] = RADAR_EVENT_KINDS,
    revisions_by_nct: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    sponsor_document: Mapping[str, Any] | None = None,
    sponsor_as_of: str | None = None,
    evidence_by_nct: Mapping[str, Mapping[str, Any]] | None = None,
) -> RadarProjection:
    """Project public trial rows into Trial Milestone Radar events (§3, §7).

    Pure and deterministic: no I/O, no wall clock, no mutable module state.
    ``trials`` are exactly the rows ``app/biocatalyst.py:_public_trial(...,
    detail=False)`` returns. See the module docstring for the full frozen
    contract.
    """

    kinds_tuple = tuple(kinds)

    dated: list[tuple[tuple[date, date, str, str], CatalystEvent]] = []
    unusable: list[tuple[tuple[str, str], CatalystEvent]] = []

    trials_with_events: set[str] = set()
    events_total = 0
    events_occurred = 0
    events_current = 0
    events_in_horizon = 0
    events_beyond_horizon = 0
    unusable_date_events = 0
    absent_date_events = 0

    for trial in trials:
        nct_id = trial.get("nct_id")
        nct_key = nct_id if isinstance(nct_id, str) else ""
        dates = trial.get("dates")
        dates = dates if isinstance(dates, Mapping) else {}
        trial_status = _trial_status_block(trial.get("status"))
        issuer = _issuer_block(_sponsor_name(trial.get("sponsor")), sponsor_document, sponsor_as_of)
        trial_block = _trial_block(trial)
        evidence = _evidence_block(nct_key, trial, evidence_by_nct)

        trial_has_event = False
        for kind in kinds_tuple:
            date_entry = dates.get(kind)
            if not isinstance(date_entry, Mapping):
                # A milestone kind entirely absent from `dates` is not an
                # event at all -- counted, never emitted (§4).
                absent_date_events += 1
                continue

            raw_date = date_entry.get("date")
            raw_type = date_entry.get("type")
            date_type = raw_type if isinstance(raw_type, str) and raw_type in _DATE_TYPES else "UNKNOWN"
            interval = _milestone_date_interval(raw_date)
            revision = _revision_block(nct_key, kind, revisions_by_nct)
            event_id = f"nct:{nct_key}:{kind}"
            events_total += 1
            trial_has_event = True

            if interval is None:
                # Present but unparsable is NOT dropped silently (§4) -- it
                # is emitted with a null timing state and an explicit reason.
                unusable_date_events += 1
                milestone = {
                    "kind": kind,
                    "date": raw_date,
                    "date_type": date_type,
                    "precision": None,
                    "interval_start": None,
                    "interval_end": None,
                    "unusable_reason": "unparsable_source_date",
                }
                timing = {
                    "state": None,
                    "anchor_date": anchor_date.isoformat(),
                    "days_to_milestone": None,
                    "days_since_milestone": None,
                }
                event = CatalystEvent(
                    event_id=event_id,
                    nct_id=nct_key,
                    kind=kind,
                    trial=trial_block,
                    milestone=milestone,
                    timing=timing,
                    trial_status=trial_status,
                    issuer=issuer,
                    revision=revision,
                    evidence=evidence,
                )
                unusable.append(((nct_key, kind), event))
                continue

            interval_start, interval_end, precision = interval
            state, days_to, days_since = _classify_timing(
                interval_start, interval_end, anchor_date, horizon_days, precision
            )
            if state == "occurred":
                events_occurred += 1
            elif state == "current":
                events_current += 1
            elif state == "upcoming":
                events_in_horizon += 1
            else:
                events_beyond_horizon += 1

            milestone = {
                "kind": kind,
                "date": raw_date,
                "date_type": date_type,
                "precision": precision,
                "interval_start": interval_start.isoformat(),
                "interval_end": interval_end.isoformat(),
                "unusable_reason": None,
            }
            timing = {
                "state": state,
                "anchor_date": anchor_date.isoformat(),
                "days_to_milestone": days_to,
                "days_since_milestone": days_since,
            }
            event = CatalystEvent(
                event_id=event_id,
                nct_id=nct_key,
                kind=kind,
                trial=trial_block,
                milestone=milestone,
                timing=timing,
                trial_status=trial_status,
                issuer=issuer,
                revision=revision,
                evidence=evidence,
            )
            if state == "beyond_horizon":
                # Counted, but excluded from the rendered rows (§7).
                continue
            dated.append(((interval_start, interval_end, nct_key, kind), event))

        if trial_has_event:
            trials_with_events.add(nct_key)

    dated.sort(key=lambda item: item[0])
    unusable.sort(key=lambda item: item[0])
    events = tuple(event for _, event in dated) + tuple(event for _, event in unusable)

    coverage = {
        "trials_in_cohort": len(trials),
        "trials_with_events": len(trials_with_events),
        "events_total": events_total,
        "events_in_horizon": events_in_horizon,
        "events_occurred": events_occurred,
        "events_current": events_current,
        "events_beyond_horizon": events_beyond_horizon,
        "unusable_date_events": unusable_date_events,
        "absent_date_events": absent_date_events,
        "kinds": list(kinds_tuple),
        "horizon_days": horizon_days,
        "anchor_date": anchor_date.isoformat(),
    }
    return RadarProjection(events=events, coverage=coverage)
