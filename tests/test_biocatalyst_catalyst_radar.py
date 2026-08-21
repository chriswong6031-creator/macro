"""Unit tests for engine/biocatalyst/catalyst_events.py (BioCatalyst P1-1).

Frozen contract under test: project_trial_milestones() is pure and
deterministic, timing classification is total, precision is honestly
reported, the evidence boundary never leaks private-shaped keys, and no
score/probability/materiality/rank/composite/confidence/weight field is ever
emitted -- these rows are registry schedule facts, never signals.
"""

from __future__ import annotations

from datetime import date
import json
import re

from engine.biocatalyst.catalyst_events import (
    DEFAULT_RADAR_HORIZON,
    HALTED_TRIAL_STATUSES,
    RADAR_EVENT_KINDS,
    RADAR_HORIZONS,
    TIMING_STATES,
    project_trial_milestones,
)


def _date_value(value, date_type="ESTIMATED"):
    if value is None:
        return None
    return {"date": value, "type": date_type}


def _trial(
    nct_id,
    *,
    status="RECRUITING",
    primary_completion=None,
    completion=None,
    start=None,
    sponsor=None,
    title="A Study",
    brief_title="Study",
    phases=("PHASE3",),
    conditions=("Obesity",),
    study_type="INTERVENTIONAL",
    updated_at="2026-08-01T00:00:00Z",
    retrieved_at="2026-08-15T00:00:00Z",
):
    return {
        "nct_id": nct_id,
        "title": title,
        "brief_title": brief_title,
        "status": status,
        "study_type": study_type,
        "phases": list(phases),
        "sponsor": sponsor,
        "conditions": list(conditions),
        "enrollment": {"count": 100, "type": "ACTUAL"},
        "dates": {
            "start": _date_value(start),
            "primary_completion": _date_value(primary_completion[0], primary_completion[1])
            if primary_completion
            else None,
            "completion": _date_value(completion[0], completion[1]) if completion else None,
        },
        "updated_at": updated_at,
        "retrieved_at": retrieved_at,
    }


# ---------------------------------------------------------------------------
# 1. Determinism
# ---------------------------------------------------------------------------


def test_projection_is_byte_identical_across_two_runs():
    trials = [
        _trial(
            "NCT00000001",
            status="TERMINATED",
            primary_completion=("2027-03", "ESTIMATED"),
            completion=("2028", "ESTIMATED"),
            sponsor={"name": "Acme Pharma", "class": "industry"},
        ),
        _trial(
            "NCT00000002",
            status="recruiting",
            primary_completion=("2026-01-01", "ACTUAL"),
            completion=("not-a-date", "UNKNOWN"),
        ),
    ]
    revisions_by_nct = {
        "NCT00000001": [
            {
                "json_path": "$.protocolSection.statusModule.primaryCompletionDateStruct.date",
                "before": {"date": "2027-01", "type": "ESTIMATED"},
                "after": {"date": "2027-03", "type": "ESTIMATED"},
                "source_versions": {"before": 3, "after": 4},
                "observed_at": "2026-07-01T00:00:00Z",
            }
        ]
    }
    sponsor_document = {
        "rows": [
            {
                "sponsor_name": "Acme Pharma",
                "valid_from": "2020-01-01",
                "valid_to": None,
                "review_state": "reviewed_admitted",
                "ticker": "ACME",
                "issuer_relationship": "direct_issuer",
            }
        ]
    }
    evidence_by_nct = {
        "NCT00000001": {"url": "https://clinicaltrials.gov/study/NCT00000001", "coverage": "full"},
    }
    kwargs = dict(
        trials=trials,
        anchor_date=date(2026, 8, 20),
        horizon_days=365,
        revisions_by_nct=revisions_by_nct,
        sponsor_document=sponsor_document,
        sponsor_as_of="2026-08-20",
        evidence_by_nct=evidence_by_nct,
    )
    first = project_trial_milestones(**kwargs)
    second = project_trial_milestones(**kwargs)

    first_json = json.dumps([e.as_dict() for e in first.events], sort_keys=True)
    second_json = json.dumps([e.as_dict() for e in second.events], sort_keys=True)
    assert first_json == second_json
    assert json.dumps(first.coverage, sort_keys=True) == json.dumps(second.coverage, sort_keys=True)


# ---------------------------------------------------------------------------
# 2. Precision handling
# ---------------------------------------------------------------------------


def test_day_precision_yields_exact_days_to_milestone():
    trials = [_trial("NCT10000001", primary_completion=("2026-08-30", "ESTIMATED"))]
    proj = project_trial_milestones(trials=trials, anchor_date=date(2026, 8, 20), horizon_days=365)
    events = [e for e in proj.events if e.kind == "primary_completion"]
    assert len(events) == 1
    timing = events[0].as_dict()["timing"]
    assert timing["state"] == "upcoming"
    assert timing["days_to_milestone"] == {"exact": 10, "min": 10, "max": 10}
    assert events[0].as_dict()["milestone"]["precision"] == "day"


def test_month_precision_yields_min_max_with_no_exact():
    trials = [_trial("NCT10000002", primary_completion=("2027-03", "ESTIMATED"))]
    proj = project_trial_milestones(trials=trials, anchor_date=date(2026, 8, 20), horizon_days=3650)
    events = [e for e in proj.events if e.kind == "primary_completion"]
    assert len(events) == 1
    d = events[0].as_dict()
    assert d["milestone"]["precision"] == "month"
    assert d["milestone"]["interval_start"] == "2027-03-01"
    assert d["milestone"]["interval_end"] == "2027-03-31"
    dtm = d["timing"]["days_to_milestone"]
    assert dtm["exact"] is None
    assert dtm["min"] == (date(2027, 3, 1) - date(2026, 8, 20)).days
    assert dtm["max"] == (date(2027, 3, 31) - date(2026, 8, 20)).days


def test_year_precision_yields_min_max_with_no_exact():
    trials = [_trial("NCT10000003", primary_completion=("2029", "ESTIMATED"))]
    proj = project_trial_milestones(trials=trials, anchor_date=date(2026, 8, 20), horizon_days=3650)
    events = [e for e in proj.events if e.kind == "primary_completion"]
    assert len(events) == 1
    d = events[0].as_dict()
    assert d["milestone"]["precision"] == "year"
    assert d["milestone"]["interval_start"] == "2029-01-01"
    assert d["milestone"]["interval_end"] == "2029-12-31"
    dtm = d["timing"]["days_to_milestone"]
    assert dtm["exact"] is None
    assert dtm["min"] == (date(2029, 1, 1) - date(2026, 8, 20)).days
    assert dtm["max"] == (date(2029, 12, 31) - date(2026, 8, 20)).days


# ---------------------------------------------------------------------------
# 3. Timing totality
# ---------------------------------------------------------------------------


def test_timing_totality_and_coverage_sums():
    anchor = date(2026, 8, 20)
    trials = [
        _trial("NCT20000001", primary_completion=("2026-01-01", "ACTUAL")),  # occurred
        _trial("NCT20000002", primary_completion=("2026-08-20", "ACTUAL")),  # current (== anchor)
        _trial("NCT20000003", primary_completion=("2026-09-01", "ESTIMATED")),  # upcoming
        _trial("NCT20000004", primary_completion=("2030-01-01", "ESTIMATED")),  # beyond_horizon
    ]
    proj = project_trial_milestones(
        trials=trials, anchor_date=anchor, horizon_days=365, kinds=("primary_completion",)
    )
    states = {e.nct_id: e.as_dict()["timing"]["state"] for e in proj.events}
    # beyond_horizon events are excluded from `events`, so only 3 are present.
    assert states == {
        "NCT20000001": "occurred",
        "NCT20000002": "current",
        "NCT20000003": "upcoming",
    }
    for state in states.values():
        assert state in TIMING_STATES

    cov = proj.coverage
    assert cov["events_total"] == 4
    assert (
        cov["events_occurred"] + cov["events_current"] + cov["events_in_horizon"] + cov["events_beyond_horizon"]
        == cov["events_total"]
    )
    assert cov["events_occurred"] == 1
    assert cov["events_current"] == 1
    assert cov["events_in_horizon"] == 1
    assert cov["events_beyond_horizon"] == 1
    assert cov["unusable_date_events"] == 0
    # kinds=("primary_completion",) only, so a missing "completion" date is
    # never even considered -- absent_date_events counts only requested kinds.
    assert cov["absent_date_events"] == 0


# ---------------------------------------------------------------------------
# 4. Horizon boundary
# ---------------------------------------------------------------------------


def test_horizon_boundary_inclusive_then_exclusive():
    anchor = date(2026, 1, 1)
    horizon_days = 10
    # anchor + (horizon_days - 1) days = 2026-01-10 -> exactly on the boundary.
    on_boundary = _trial("NCT30000001", primary_completion=("2026-01-10", "ESTIMATED"))
    one_day_later = _trial("NCT30000002", primary_completion=("2026-01-11", "ESTIMATED"))

    proj = project_trial_milestones(
        trials=[on_boundary, one_day_later],
        anchor_date=anchor,
        horizon_days=horizon_days,
        kinds=("primary_completion",),
    )
    by_nct = {e.nct_id: e.as_dict()["timing"]["state"] for e in proj.events}
    assert by_nct.get("NCT30000001") == "upcoming"
    assert "NCT30000002" not in by_nct  # beyond_horizon rows are excluded from events
    assert proj.coverage["events_beyond_horizon"] == 1
    assert proj.coverage["events_in_horizon"] == 1


# ---------------------------------------------------------------------------
# 5. Revision lineage
# ---------------------------------------------------------------------------


def test_revision_lineage_matching_non_matching_and_missing():
    trials = [_trial("NCT40000001", primary_completion=("2027-01-01", "ESTIMATED"))]
    revisions_by_nct = {
        "NCT40000001": [
            {
                # Non-matching path: an enrollment change must not count as a
                # milestone revision.
                "json_path": "$.protocolSection.designModule.enrollmentInfo.count",
                "before": {"date": "2026-01-01"},
                "after": {"date": "2026-06-01"},
                "source_versions": {"before": 1, "after": 2},
                "observed_at": "2026-01-15T00:00:00Z",
            },
            {
                "json_path": "$.protocolSection.statusModule.primaryCompletionDateStruct.date",
                "before": {"date": "2026-12-01", "type": "ESTIMATED"},
                "after": {"date": "2026-11-01", "type": "ESTIMATED"},
                "source_versions": {"before": 2, "after": 3},
                "observed_at": "2026-02-01T00:00:00Z",
            },
            {
                "source_json_path": "$.protocolSection.statusModule.primaryCompletionDateStruct.date",
                "before": {"date": "2026-11-01", "type": "ESTIMATED"},
                "after": {"date": "2027-01-01", "type": "ESTIMATED"},
                "source_versions": {"before": 3, "after": 4},
                "observed_at": "2026-03-01T00:00:00Z",
            },
        ]
    }
    proj = project_trial_milestones(
        trials=trials,
        anchor_date=date(2026, 8, 20),
        horizon_days=365,
        kinds=("primary_completion",),
        revisions_by_nct=revisions_by_nct,
    )
    event = next(e for e in proj.events if e.nct_id == "NCT40000001")
    revision = event.as_dict()["revision"]
    assert revision["state"] == "has_revisions"
    assert revision["count"] == 2  # the enrollment row must not be counted
    assert revision["latest"] == {
        "from": "2026-11-01",
        "to": "2027-01-01",
        "from_version": 3,
        "to_version": 4,
        "observed_at": "2026-03-01T00:00:00Z",
    }

    # A missing nct entirely -> history_not_collected.
    missing = project_trial_milestones(
        trials=[_trial("NCT40000002", primary_completion=("2027-01-01", "ESTIMATED"))],
        anchor_date=date(2026, 8, 20),
        horizon_days=365,
        kinds=("primary_completion",),
        revisions_by_nct=revisions_by_nct,  # does not contain NCT40000002
    )
    missing_event = next(e for e in missing.events if e.nct_id == "NCT40000002")
    assert missing_event.as_dict()["revision"] == {"state": "history_not_collected", "count": 0, "latest": None}

    # Entry present, but no matching rows -> no_revisions_recorded.
    no_match = project_trial_milestones(
        trials=[_trial("NCT40000003", primary_completion=("2027-01-01", "ESTIMATED"))],
        anchor_date=date(2026, 8, 20),
        horizon_days=365,
        kinds=("primary_completion",),
        revisions_by_nct={"NCT40000003": []},
    )
    no_match_event = next(e for e in no_match.events if e.nct_id == "NCT40000003")
    assert no_match_event.as_dict()["revision"] == {"state": "no_revisions_recorded", "count": 0, "latest": None}


# ---------------------------------------------------------------------------
# 6. Unresolved issuer
# ---------------------------------------------------------------------------

_SPONSOR_DOCUMENT = {
    "rows": [
        {
            "sponsor_name": "Reviewed Pharma Inc",
            "valid_from": "2020-01-01",
            "valid_to": None,
            "review_state": "reviewed_admitted",
            "ticker": "RVWD",
            "issuer_relationship": "direct_issuer",
        }
    ]
}


def test_unmapped_sponsor_is_unresolved_with_null_ticker():
    trials = [
        _trial(
            "NCT50000001",
            primary_completion=("2027-01-01", "ESTIMATED"),
            sponsor={"name": "Totally Unmapped Biotech"},
        )
    ]
    proj = project_trial_milestones(
        trials=trials,
        anchor_date=date(2026, 8, 20),
        horizon_days=365,
        kinds=("primary_completion",),
        sponsor_document=_SPONSOR_DOCUMENT,
        sponsor_as_of="2026-08-20",
    )
    issuer = proj.events[0].as_dict()["issuer"]
    assert issuer["state"] == "unresolved_sponsor"
    assert issuer["ticker"] is None
    assert issuer["company_identity"] == {
        "state": "company_identity_not_joined",
        "reason": "no_pit_company_identity_seam",
    }


def test_reviewed_admitted_sponsor_resolves_to_ticker_only():
    trials = [
        _trial(
            "NCT50000002",
            primary_completion=("2027-01-01", "ESTIMATED"),
            sponsor={"name": "Reviewed Pharma Inc"},
        )
    ]
    proj = project_trial_milestones(
        trials=trials,
        anchor_date=date(2026, 8, 20),
        horizon_days=365,
        kinds=("primary_completion",),
        sponsor_document=_SPONSOR_DOCUMENT,
        sponsor_as_of="2026-08-20",
    )
    issuer = proj.events[0].as_dict()["issuer"]
    assert issuer["state"] == "ticker_only"
    assert issuer["ticker"] == "RVWD"
    assert issuer["issuer_relationship"] == "direct_issuer"
    assert issuer["company_identity"]["state"] == "company_identity_not_joined"


def test_company_identity_is_always_not_joined_regardless_of_resolution():
    unavailable_trials = [_trial("NCT50000003", primary_completion=("2027-01-01", "ESTIMATED"))]
    unavailable = project_trial_milestones(
        trials=unavailable_trials, anchor_date=date(2026, 8, 20), horizon_days=365, kinds=("primary_completion",)
    )
    absent_trials = [
        _trial("NCT50000004", primary_completion=("2027-01-01", "ESTIMATED"), sponsor=None)
    ]
    absent = project_trial_milestones(
        trials=absent_trials,
        anchor_date=date(2026, 8, 20),
        horizon_days=365,
        kinds=("primary_completion",),
        sponsor_document=_SPONSOR_DOCUMENT,
        sponsor_as_of="2026-08-20",
    )
    for proj in (unavailable, absent):
        assert proj.events[0].as_dict()["issuer"]["company_identity"] == {
            "state": "company_identity_not_joined",
            "reason": "no_pit_company_identity_seam",
        }
    assert unavailable.events[0].as_dict()["issuer"]["state"] == "sponsor_map_unavailable"
    assert absent.events[0].as_dict()["issuer"]["state"] == "sponsor_name_absent"


def test_raising_resolver_yields_sponsor_map_unavailable_without_propagating():
    trials = [
        _trial(
            "NCT50000005",
            primary_completion=("2027-01-01", "ESTIMATED"),
            sponsor={"name": "Reviewed Pharma Inc"},
        )
    ]
    # A malformed as_of string makes resolve_sponsor raise SponsorIdentityError
    # internally -- the projection must swallow it, never propagate.
    proj = project_trial_milestones(
        trials=trials,
        anchor_date=date(2026, 8, 20),
        horizon_days=365,
        kinds=("primary_completion",),
        sponsor_document=_SPONSOR_DOCUMENT,
        sponsor_as_of="not-a-valid-date",
    )
    issuer = proj.events[0].as_dict()["issuer"]
    assert issuer["state"] == "sponsor_map_unavailable"
    assert issuer["ticker"] is None


# ---------------------------------------------------------------------------
# 7. Trial status
# ---------------------------------------------------------------------------


def test_terminated_and_withdrawn_are_inactive_suspended_is_paused_not_terminal():
    trials = [
        _trial("NCT60000001", status="TERMINATED", primary_completion=("2027-01-01", "ESTIMATED")),
        _trial("NCT60000002", status="WITHDRAWN", primary_completion=("2027-01-01", "ESTIMATED")),
        _trial("NCT60000003", status="SUSPENDED", primary_completion=("2027-01-01", "ESTIMATED")),
        _trial("NCT60000004", status="RECRUITING", primary_completion=("2027-01-01", "ESTIMATED")),
    ]
    proj = project_trial_milestones(
        trials=trials, anchor_date=date(2026, 8, 20), horizon_days=365, kinds=("primary_completion",)
    )
    by_nct = {e.nct_id: e.as_dict()["trial_status"] for e in proj.events}

    assert by_nct["NCT60000001"] == {"value": "TERMINATED", "activity": "inactive", "reason_code": "trial_terminated"}
    assert by_nct["NCT60000002"] == {"value": "WITHDRAWN", "activity": "inactive", "reason_code": "trial_withdrawn"}
    # The most load-bearing assertion in this test: SUSPENDED is explicitly
    # NOT terminal. It is "paused", never lumped in with inactive/terminated.
    assert by_nct["NCT60000003"]["activity"] == "paused"
    assert by_nct["NCT60000003"]["activity"] != "inactive"
    assert by_nct["NCT60000003"] == {"value": "SUSPENDED", "activity": "paused", "reason_code": "trial_suspended"}
    assert by_nct["NCT60000004"] == {"value": "RECRUITING", "activity": "active", "reason_code": None}
    assert HALTED_TRIAL_STATUSES == frozenset({"TERMINATED", "WITHDRAWN", "SUSPENDED"})


def test_trial_status_value_preserved_verbatim_including_case():
    # Lower-case source string must be preserved exactly, even though
    # classification is derived from .upper().
    trials = [_trial("NCT60000005", status="terminated", primary_completion=("2027-01-01", "ESTIMATED"))]
    proj = project_trial_milestones(
        trials=trials, anchor_date=date(2026, 8, 20), horizon_days=365, kinds=("primary_completion",)
    )
    status = proj.events[0].as_dict()["trial_status"]
    assert status["value"] == "terminated"
    assert status["activity"] == "inactive"


# ---------------------------------------------------------------------------
# 8. Valid empty
# ---------------------------------------------------------------------------


def test_empty_cohort_yields_no_events_and_honest_coverage():
    proj = project_trial_milestones(trials=[], anchor_date=date(2026, 8, 20), horizon_days=365)
    assert proj.events == ()
    assert proj.coverage["trials_in_cohort"] == 0
    assert proj.coverage["trials_with_events"] == 0
    assert proj.coverage["events_total"] == 0


# ---------------------------------------------------------------------------
# 9. Evidence safety
# ---------------------------------------------------------------------------

_POISON_MARKERS = ("object_key", "receipt", "sha256", "leaked-receipt-value", "/var/lib/macro-biocatalyst/private")


def test_poisoned_evidence_input_never_reaches_serialized_output():
    poisoned_trial = _trial("NCT70000001", primary_completion=("2027-01-01", "ESTIMATED"))
    # A caller must not be able to smuggle private-shaped keys onto the trial
    # row itself either -- this module only ever reads named fields.
    poisoned_trial["object_key"] = "r2://macro-biocatalyst-private/NCT70000001/receipt.json"
    poisoned_trial["worker_receipt_path"] = "/var/lib/macro-biocatalyst/private/receipts/leaked-receipt-value.json"

    evidence_by_nct = {
        "NCT70000001": {
            "url": "https://clinicaltrials.gov/study/NCT70000001",
            "coverage": "full",
            "object_key": "r2://macro-biocatalyst-private/NCT70000001.parquet",
            "receipt": "leaked-receipt-value",
            "path": "/var/lib/macro-biocatalyst/private/receipts/NCT70000001.json",
            "sha256": "deadbeef" * 8,
        }
    }
    proj = project_trial_milestones(
        trials=[poisoned_trial],
        anchor_date=date(2026, 8, 20),
        horizon_days=365,
        kinds=("primary_completion",),
        evidence_by_nct=evidence_by_nct,
    )
    serialized = json.dumps([e.as_dict() for e in proj.events])

    for marker in _POISON_MARKERS:
        assert marker not in serialized

    evidence = proj.events[0].as_dict()["evidence"]
    assert set(evidence) == {"provider", "record_id", "url", "source_clocks", "coverage"}
    assert evidence["url"] == "https://clinicaltrials.gov/study/NCT70000001"
    assert evidence["coverage"] == "full"


# ---------------------------------------------------------------------------
# 10. No-score invariant
# ---------------------------------------------------------------------------

_FORBIDDEN_KEY_PATTERN = re.compile(r"score|probability|materiality|rank|composite|confidence|weight", re.IGNORECASE)


def _walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk_keys(item)


def test_no_score_or_confidence_shaped_field_anywhere_in_output():
    trials = [
        _trial(
            "NCT80000001",
            status="TERMINATED",
            primary_completion=("2027-03", "ESTIMATED"),
            completion=("2028-01-01", "ACTUAL"),
            sponsor={"name": "Reviewed Pharma Inc"},
        )
    ]
    revisions_by_nct = {
        "NCT80000001": [
            {
                "json_path": "$.protocolSection.statusModule.completionDateStruct.date",
                "before": {"date": "2027-06-01"},
                "after": {"date": "2028-01-01"},
                "source_versions": {"before": 1, "after": 2},
                "observed_at": "2026-05-01T00:00:00Z",
            }
        ]
    }
    proj = project_trial_milestones(
        trials=trials,
        anchor_date=date(2026, 8, 20),
        horizon_days=365,
        revisions_by_nct=revisions_by_nct,
        sponsor_document=_SPONSOR_DOCUMENT,
        sponsor_as_of="2026-08-20",
    )
    payload = {
        "events": [e.as_dict() for e in proj.events],
        "coverage": proj.coverage,
    }
    for key in _walk_keys(payload):
        assert not _FORBIDDEN_KEY_PATTERN.search(str(key)), f"forbidden key found: {key!r}"
    assert "cancelled" not in json.dumps(payload).lower()


# ---------------------------------------------------------------------------
# 11. The real four-NCT acceptance cohort (frozen gate -- do not adjust)
# ---------------------------------------------------------------------------


def _acceptance_cohort():
    return [
        _trial(
            "NCT04528082",
            status="RECRUITING",
            primary_completion=("2030-02-07", "ESTIMATED"),
            completion=("2030-12-17", "ESTIMATED"),
        ),
        _trial(
            "NCT05020236",
            status="RECRUITING",
            primary_completion=("2026-02-26", "ACTUAL"),
            completion=("2027-05-31", "ESTIMATED"),
        ),
        _trial(
            "NCT06602479",
            status="RECRUITING",
            primary_completion=("2026-12-18", "ESTIMATED"),
            completion=("2027-05-07", "ESTIMATED"),
        ),
        _trial(
            "NCT07218380",
            status="RECRUITING",
            primary_completion=("2029-10", "ESTIMATED"),
            completion=("2033-05", "ESTIMATED"),
        ),
    ]


def test_acceptance_cohort_horizon_365():
    proj = project_trial_milestones(
        trials=_acceptance_cohort(), anchor_date=date(2026, 8, 20), horizon_days=365
    )
    assert proj.coverage["events_in_horizon"] == 3
    assert proj.coverage["events_occurred"] == 1
    upcoming = [e for e in proj.events if e.as_dict()["timing"]["state"] == "upcoming"]
    occurred = [e for e in proj.events if e.as_dict()["timing"]["state"] == "occurred"]
    assert len(upcoming) == 3
    assert len(occurred) == 1


def test_acceptance_cohort_horizon_180():
    proj = project_trial_milestones(
        trials=_acceptance_cohort(), anchor_date=date(2026, 8, 20), horizon_days=180
    )
    assert proj.coverage["events_in_horizon"] == 1
    assert proj.coverage["events_occurred"] == 1
    upcoming = [e for e in proj.events if e.as_dict()["timing"]["state"] == "upcoming"]
    occurred = [e for e in proj.events if e.as_dict()["timing"]["state"] == "occurred"]
    assert len(upcoming) == 1
    assert len(occurred) == 1


# ---------------------------------------------------------------------------
# Public constants sanity (contract the API/UI builder codes against)
# ---------------------------------------------------------------------------


def test_public_constants_match_frozen_contract():
    assert RADAR_EVENT_KINDS == ("primary_completion", "completion")
    assert RADAR_HORIZONS == {"next_180d": 180, "next_365d": 365, "next_730d": 730, "all": None}
    assert DEFAULT_RADAR_HORIZON == "next_365d"
    assert TIMING_STATES == ("occurred", "current", "upcoming", "beyond_horizon")
    assert HALTED_TRIAL_STATUSES == frozenset({"TERMINATED", "WITHDRAWN", "SUSPENDED"})
