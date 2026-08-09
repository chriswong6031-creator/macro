"""Guards for the Wave 9G prospective candidate grader.

This suite exists to keep the instrument capable of returning "no". Every test
below pins a failure mode that has ACTUALLY shipped in this repository, and each
one is paired with a mutation that proves the assertion can see the defect it
claims to guard — a green assertion against an implementation that cannot fail is
the exact class of dead guard this file is meant not to join.

The lobe has zero live candidates by design (the ledger is 0 bytes and the event
spine is unavailable), so everything here runs against fixtures. That is the
point: the harness has to exist before the first candidate is issued, or the
first cohort is ungradeable after the fact.
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone
import inspect
import json
from pathlib import Path

import pytest

from engine.government_revenue import candidate_grader as grader
from engine.government_revenue.candidate_grader import (
    Coverage,
    GRV_FA1,
    GraderError,
    PriceBasis,
    PricePanel,
    Rate,
    SessionCalendar,
)

ROOT = Path(__file__).resolve().parents[1]
PREREG_PATH = ROOT / "research" / "GOVERNMENT_REVENUE_CANDIDATE_GRADER_PREREG.md"

_DIGEST = "a" * 64
_APPENDED_AT = "2026-08-06T00:00:00+00:00"
_ENTRY_INDEX = 300


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _sessions(count: int = 600, start: date = date(2024, 1, 1)) -> list[date]:
    """An explicit weekday session list. No resample, no business-day offset."""
    days: list[date] = []
    cursor = start
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


@pytest.fixture()
def calendar() -> SessionCalendar:
    return SessionCalendar.from_dates(_sessions(), calendar_id=GRV_FA1.calendar_id)


def _basis(vintage_id: str = "prices-2026-08-06", adjustment: str | None = None) -> PriceBasis:
    return PriceBasis(
        field=GRV_FA1.price_field,
        adjustment=adjustment or GRV_FA1.price_adjustment,
        vintage_id=vintage_id,
        vintage_observed_at="2026-08-06T05:00:00+00:00",
    )


def _flat(calendar: SessionCalendar, value: float) -> dict[date, float]:
    return {session: value for session in calendar.sessions}


def _step(calendar: SessionCalendar, *, before: float, after: float, index: int) -> dict[date, float]:
    """``before`` up to and including ``index``, ``after`` from ``index + 1``."""
    return {
        session: (before if position <= index else after)
        for position, session in enumerate(calendar.sessions)
    }


def _panel(calendar: SessionCalendar, series: dict[str, dict[date, float]], **basis_kwargs) -> PricePanel:
    rows = {"SPY": _flat(calendar, 100.0), "ITA": _flat(calendar, 100.0)}
    rows.update(series)
    return PricePanel(basis=_basis(**basis_kwargs), series=rows)


def _known_at(calendar: SessionCalendar, entry_index: int) -> str:
    """A clock whose UTC date is the session BEFORE ``entry_index``."""
    return datetime.combine(
        calendar.sessions[entry_index - 1], datetime.min.time(), tzinfo=timezone.utc
    ).replace(hour=18).isoformat()


def _candidate(
    calendar: SessionCalendar,
    *,
    ticker: str = "PLTR",
    candidate_id: str = "grc1-000000000000000000000001",
    observation_id: str = "gro1-000000000000000000000001",
    event_id: str = "evt-1",
    entry_index: int = _ENTRY_INDEX,
    **overrides,
) -> dict:
    payload = {
        "contract": "government_revenue_candidate.v1",
        "schema_version": "1.0.0",
        "candidate_id": candidate_id,
        "observation_id": observation_id,
        "candidate_family": "award_obligation_change",
        "candidate_state": "awaiting_crosscheck",
        "ticker": ticker,
        "issuer_company_id": f"company:{ticker.lower()}",
        "issuer": {"company_name": f"{ticker} Inc", "ticker": ticker},
        "issuer_resolution_ref": {
            "resolution_state": "reviewed",
            "graph_id": "recipient-graph:reviewed:2026-08-03:pltr-v1",
            "graph_digest": "b" * 64,
            "evidence_refs": ["ev-1"],
        },
        "artifact_content_ids": ["c" * 64],
        "event_refs": [event_id, "rec-1"],
        "source_event": {
            "event_id": event_id,
            "record_id": "rec-1",
            "event_type": "obligation",
            "source_rail": "usaspending_award_action",
            "source_content_id": "d" * 64,
            "is_late_discovery": False,
        },
        "source_receipt_refs": [{"ref_id": "receipt-1", "content_sha256": "e" * 64}],
        "effective_at": "2025-02-01T00:00:00+00:00",
        "known_at": _known_at(calendar, entry_index),
        "coverage": {"scope": "bounded", "exact_link_status": "exact_linked", "is_complete": False},
        "transmission_direction": "possible_positive",
        "authority": {
            "tier": "display",
            "context_only": True,
            "can_rank": False,
            "can_size": False,
            "can_gate": False,
            "can_originate_signal": False,
            "can_add_candidates": False,
            "can_escalate": False,
        },
    }
    payload.update(overrides)
    return payload


def _row(calendar: SessionCalendar, **kwargs) -> dict:
    return grader.build_issuance_row(
        _candidate(calendar, **kwargs),
        family=GRV_FA1,
        prereg_document_sha256=_DIGEST,
        price_basis=_basis(),
        appended_at=_APPENDED_AT,
    )


def _log(rows) -> grader.IssuanceLog:
    raw = b"".join(grader.canonical_bytes(row) + b"\n" for row in rows)
    return grader.parse_issuance_log(raw)


def _identity_coverage() -> Coverage:
    # The real 2026-08-06 numbers: one reviewed issuer against a 21-company backlog.
    return Coverage(
        kind="identity",
        scope="issuers with a reviewed exact recipient path",
        observed=1,
        universe=21,
        status="partial",
    )


def _event_coverage() -> Coverage:
    return Coverage(
        kind="event",
        scope="post-baseline eligible award events observed by the forward spine",
        observed=0,
        universe=0,
        status="unavailable",
    )


def _report(calendar: SessionCalendar, log: grader.IssuanceLog, panel: PricePanel, **kwargs) -> dict:
    defaults = dict(
        family=GRV_FA1,
        panel=panel,
        calendar=calendar,
        as_of=datetime.combine(calendar.sessions[-1], datetime.min.time(), tzinfo=timezone.utc),
        identity_coverage=_identity_coverage(),
        event_coverage=_event_coverage(),
        generated_at="2026-08-06T12:00:00+00:00",
    )
    defaults.update(kwargs)
    return grader.build_cohort_report(log, **defaults)


def _family_with(**overrides) -> grader.PreregisteredFamily:
    """GRV-FA1 with fields overridden, tolerant of fields the family lacks.

    Deliberately signature-tolerant: the red-before/green-after demonstrations
    below have to be able to RUN against the pre-fix implementation, so that
    their red is a real assertion about behavior rather than a ``TypeError``
    from a keyword that did not exist yet. A test that goes red because the API
    moved proves nothing about the defect it names.
    """
    fields = {field: getattr(GRV_FA1, field) for field in GRV_FA1.__dataclass_fields__}
    fields.update({key: value for key, value in overrides.items() if key in fields})
    return grader.PreregisteredFamily(**fields)


def _gate(rows, *, family, coverage, calendar):
    """Call ``maturity_gate`` with the calendar only if it takes one."""
    kwargs = {"family": family, "outcome_coverage": coverage}
    if "calendar" in inspect.signature(grader.maturity_gate).parameters:
        kwargs["calendar"] = calendar
    return grader.maturity_gate(rows, **kwargs)


# ---------------------------------------------------------------------------
# GATE 5 — the preregistration exists, is versioned, and declares the kill
# condition before any observation
# ---------------------------------------------------------------------------


def test_preregistration_document_is_committed_and_binds_the_code():
    family, digest = grader.load_family_declaration(PREREG_PATH)
    assert family is GRV_FA1
    assert len(digest) == 64
    assert family.version == "3.1.0"


def test_preregistration_declares_kill_expiry_and_thresholds():
    text = PREREG_PATH.read_text(encoding="utf-8")
    assert GRV_FA1.kill_condition_id in text, "the kill condition must be named, not implied"
    assert "KILL" in text and "TESTED-NULL" in text and "EXPIRY" in text
    assert GRV_FA1.accrual_expiry_date in text, (
        "an accrual expiry is what stops 'still accruing' from being a permanent alibi"
    )
    # Registration precedes observation: the live issuance log must not exist yet.
    live = ROOT / "data" / "government_revenue" / grader.ISSUANCE_LOG_FILENAME
    assert not live.exists() or live.stat().st_size == 0


def test_document_and_code_cannot_drift(tmp_path):
    """Mutation proof for the two tests above."""
    text = PREREG_PATH.read_text(encoding="utf-8")
    drifted = text.replace('"sessions": 63, "role": "primary"', '"sessions": 30, "role": "primary"')
    assert drifted != text
    target = tmp_path / "prereg.md"
    target.write_text(drifted, encoding="utf-8")
    with pytest.raises(GraderError, match="disagree"):
        grader.load_family_declaration(target)


def test_document_without_its_kill_condition_is_refused(tmp_path):
    """An id inside the declaration block is not a decision rule anyone is held to."""
    text = PREREG_PATH.read_text(encoding="utf-8")
    fence = text.index("```json")
    end = text.index("```", fence + 7) + 3
    stripped = text[:end] + text[end:].replace(GRV_FA1.kill_condition_id, "GRV-FA1-UNSTATED")
    assert stripped != text
    assert GRV_FA1.kill_condition_id in stripped, "the declaration block still declares the id"

    target = tmp_path / "prereg.md"
    target.write_text(stripped, encoding="utf-8")
    with pytest.raises(GraderError, match="kill condition"):
        grader.load_family_declaration(target)


# ---------------------------------------------------------------------------
# admission and abstention
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"candidate_family": "award_ceiling_change"}, "ceiling_change_out_of_family"),
        ({"candidate_family": "new_award"}, "family_mismatch"),
        ({"transmission_direction": "possible_negative"}, "direction_not_positive"),
        ({"coverage": {"exact_link_status": "discovery_name"}}, "not_exact_linked"),
        ({"known_at": "not-a-clock"}, "missing_known_at"),
        ({"authority": {"tier": "signal"}}, "authority_not_display"),
    ],
)
def test_out_of_family_candidates_abstain_with_a_named_reason(calendar, overrides, reason):
    decision = grader.admit(_candidate(calendar, **overrides), family=GRV_FA1)
    assert not decision.admitted
    assert decision.reason == reason
    assert decision.reason in grader.ABSTENTION_REASONS


def test_deobligation_and_late_discovery_abstain(calendar):
    payload = _candidate(calendar)
    payload["source_event"] = {**payload["source_event"], "event_type": "deobligation"}
    assert grader.admit(payload, family=GRV_FA1).reason == "deobligation"

    payload = _candidate(calendar)
    payload["source_event"] = {**payload["source_event"], "is_late_discovery": True}
    assert grader.admit(payload, family=GRV_FA1).reason == "late_discovery"


def test_abstentions_are_recorded_in_the_log_and_reported(calendar):
    admitted = _row(calendar)
    refused = grader.build_issuance_row(
        _candidate(calendar, candidate_id="grc1-000000000000000000000002", candidate_family="award_ceiling_change"),
        family=GRV_FA1,
        prereg_document_sha256=_DIGEST,
        price_basis=_basis(),
        appended_at=_APPENDED_AT,
    )
    assert refused["row_kind"] == "abstention"
    log = _log([admitted, refused])
    panel = _panel(calendar, {"PLTR": _step(calendar, before=100.0, after=110.0, index=_ENTRY_INDEX)})
    report = _report(calendar, log, panel)

    assert report["admission"]["considered"] == 2
    assert report["admission"]["issued"] == 1
    assert report["admission"]["abstention_rate"]["value"] == 0.5
    assert report["admission"]["abstention_reasons"] == {"ceiling_change_out_of_family": 1}
    # An abstained candidate never enters the outcome cohort.
    assert report["outcome_by_horizon"]["h5"]["cohort"]["issued_n"] == 1


# ---------------------------------------------------------------------------
# GATE 3 — a correction appends and never mutates
# ---------------------------------------------------------------------------


def test_correction_appends_and_the_prior_row_stays_byte_identical(tmp_path, calendar):
    path = tmp_path / grader.ISSUANCE_LOG_FILENAME
    original = _row(calendar)
    grader.append_issuance_rows(path, [original])
    before = path.read_bytes()

    correction = grader.build_correction_row(
        original,
        reason="source_record_corrected",
        appended_at="2026-08-07T00:00:00+00:00",
        changes={"candidate_payload_sha256": "f" * 64},
    )
    receipt = grader.append_issuance_rows(path, [correction])
    after = path.read_bytes()

    # The bytes of the superseded row are untouched, forever.
    assert after[: len(before)] == before
    assert grader.verify_append_only(before, after)
    assert receipt["prior_byte_count"] == len(before)
    assert receipt["append_count"] == 1

    log = grader.load_issuance_log(path)
    assert log.rows[0] == original, "the superseded row must parse back identically"
    assert log.rows[1]["supersedes_row_id"] == original["row_id"]
    assert log.rows[1]["row_id"] != original["row_id"]

    # The cohort follows the correction; the log keeps both.
    cohort = grader.cohort_rows(log, family_id=GRV_FA1.family_id)
    assert len(cohort) == 1
    assert cohort[0]["row_id"] == correction["row_id"]


def test_a_rewritten_row_is_detectable(tmp_path, calendar):
    """Mutation proof: an in-place edit fails both the prefix check and the parse."""
    path = tmp_path / grader.ISSUANCE_LOG_FILENAME
    grader.append_issuance_rows(path, [_row(calendar)])
    before = path.read_bytes()

    tampered = before.replace(b'"ticker":"PLTR"', b'"ticker":"LMTX"')
    assert tampered != before
    path.write_bytes(tampered)

    assert not grader.verify_append_only(before, path.read_bytes())
    with pytest.raises(GraderError, match="row_id does not address its own content"):
        grader.load_issuance_log(path)


def test_append_refuses_a_duplicate_row(tmp_path, calendar):
    path = tmp_path / grader.ISSUANCE_LOG_FILENAME
    row = _row(calendar)
    grader.append_issuance_rows(path, [row])
    with pytest.raises(GraderError, match="duplicates an existing row_id"):
        grader.append_issuance_rows(path, [row])


def test_correction_cannot_rewrite_identity(calendar):
    with pytest.raises(GraderError, match="cannot rewrite"):
        grader.build_correction_row(
            _row(calendar),
            reason="source_record_corrected",
            appended_at=_APPENDED_AT,
            changes={"candidate_id": "grc1-000000000000000000000009"},
        )


@pytest.mark.parametrize(
    "field",
    [
        "known_at",
        "ticker",
        "horizons",
        "entry_rule",
        "effective_at",
        "source_event",
        "issuer_company_id",
        "prereg_document_sha256",
    ],
)
def test_correction_cannot_rewrite_the_fields_that_define_the_measurement(calendar, field):
    """B2. A correction may not move the ruler it is being measured with.

    Version 1.0.0 blocked six identity fields and accepted everything else, so a
    plain ``correction`` — under no restriction at all, unlike a retraction —
    could rewrite:

    * ``known_at``, which RE-CUTS the entry session. Issued after the outcome is
      observable, that is post-issuance information reaching the grade: the one
      leak this module exists to prevent.
    * ``ticker``, which moves the row onto a symbol the panel does not carry and
      quietly ungrades it — the vector that walked a losing cohort out of a
      ``kill`` (see the B1 test below).
    * ``horizons`` and ``entry_rule``, which re-cut the window §3 froze at
      issuance.

    ``test_correction_cannot_rewrite_identity`` above probed only
    ``candidate_id`` and could not see any of this.
    """
    original = _row(calendar)
    replacement = {
        "known_at": _known_at(calendar, _ENTRY_INDEX + 40),
        "ticker": "NOPX",
        "horizons": [{"name": "h5", "sessions": 40, "role": "primary"}],
        "entry_rule": {**original["entry_rule"], "market_benchmark": "QQQ"},
        "effective_at": "2026-01-01T00:00:00+00:00",
        "source_event": {**original["source_event"], "event_id": "evt-swapped"},
        "issuer_company_id": "company:someone-else",
        "prereg_document_sha256": "9" * 64,
    }[field]
    with pytest.raises(GraderError, match="cannot rewrite"):
        grader.build_correction_row(
            original,
            reason="source_record_corrected",
            appended_at=_APPENDED_AT,
            changes={field: replacement},
        )


def test_a_correction_reason_comes_from_a_closed_vocabulary(calendar):
    """§8 restricted retractions and left plain corrections unrestricted."""
    original = _row(calendar)
    with pytest.raises(GraderError, match="not a registered correction reason"):
        grader.build_correction_row(
            original,
            reason="the number looked wrong to me",
            appended_at=_APPENDED_AT,
            changes={"candidate_payload_sha256": "f" * 64},
        )
    # A retraction takes the narrower list: the record changed, or the receipt
    # binding failed. "We regenerated an artifact" is not grounds to retract.
    with pytest.raises(GraderError, match="not a registered retraction reason"):
        grader.build_correction_row(
            original,
            reason="evidence_artifact_regenerated",
            appended_at=_APPENDED_AT,
            retract=True,
        )
    # ...and the allowed shape still works.
    corrected = grader.build_correction_row(
        original,
        reason="evidence_artifact_regenerated",
        appended_at=_APPENDED_AT,
        changes={"candidate_payload_sha256": "f" * 64},
    )
    assert corrected["correction_reason"] in grader.CORRECTION_REASONS
    assert corrected["known_at"] == original["known_at"]
    assert corrected["ticker"] == original["ticker"]


def test_retraction_keeps_its_slot_in_the_denominator(calendar):
    """You cannot retract your way out of a loss — only into a wider bound."""
    loser = _row(calendar, candidate_id="grc1-000000000000000000000002", ticker="LOSR", event_id="evt-2")
    retraction = grader.build_correction_row(
        loser,
        reason="source_receipt_binding_failed",
        appended_at="2026-08-07T00:00:00+00:00",
        retract=True,
    )
    winner = _row(calendar)
    log = _log([winner, loser, retraction])
    panel = _panel(
        calendar,
        {
            "PLTR": _step(calendar, before=100.0, after=110.0, index=_ENTRY_INDEX),
            "LOSR": _step(calendar, before=100.0, after=50.0, index=_ENTRY_INDEX),
        },
    )
    report = _report(calendar, log, panel)
    h5 = report["outcome_by_horizon"]["h5"]

    assert h5["cohort"]["issued_n"] == 2, "a retraction must not shrink the denominator"
    assert h5["cohort"]["ungraded_reasons"] == {"retracted": 1}
    assert h5["hit_rate"]["value"] == 1.0
    assert h5["coverage"]["observed"] == 1 and h5["coverage"]["universe"] == 2
    # The retracted loser is paid for in the bounds, not deleted.
    assert h5["hit_rate_bounds"]["lower_bound_hit_rate"]["value"] == 0.5
    assert h5["hit_rate_bounds"]["upper_bound_hit_rate"]["value"] == 1.0


# ---------------------------------------------------------------------------
# GATE 1 — no leakage
# ---------------------------------------------------------------------------


def test_grade_reads_only_the_issuance_time_window(calendar):
    """The future is present in the fixture and must not reach the grade."""
    closes = _flat(calendar, 100.0)
    closes[calendar.sessions[_ENTRY_INDEX + 6]] = 1000.0  # the session after h5's exit
    closes[calendar.sessions[_ENTRY_INDEX - 1]] = 7.0  # the known_at session itself
    panel = _panel(calendar, {"PLTR": closes})
    row = _row(calendar)

    grade = grader.grade_row(row, "h5", panel=panel, calendar=calendar, as_of=_as_of(calendar))
    assert grade.state == "graded"
    assert grade.entry_session == calendar.sessions[_ENTRY_INDEX]
    assert grade.exit_session == calendar.sessions[_ENTRY_INDEX + 5]
    assert grade.read_window_sessions == 6
    assert grade.absolute_return == pytest.approx(0.0)

    moved = dict(closes)
    moved[calendar.sessions[_ENTRY_INDEX + 6]] = 5000.0
    moved[calendar.sessions[_ENTRY_INDEX - 1]] = 3.0
    regraded = grader.grade_row(
        row, "h5", panel=_panel(calendar, {"PLTR": moved}), calendar=calendar, as_of=_as_of(calendar)
    )
    assert regraded.read_window_sha256 == grade.read_window_sha256
    assert regraded.absolute_return == grade.absolute_return
    assert regraded.max_drawdown == grade.max_drawdown


def test_widening_the_read_window_by_one_session_changes_the_grade(calendar, monkeypatch):
    """Mutation proof that the leakage assertion above is not vacuous.

    Two independent widenings, one per seam. If either left the grade unchanged,
    the leakage guard would be measuring nothing.
    """
    closes = _flat(calendar, 100.0)
    closes[calendar.sessions[_ENTRY_INDEX + 6]] = 1000.0
    panel = _panel(calendar, {"PLTR": closes})
    row = _row(calendar)
    honest = grader.grade_row(row, "h5", panel=panel, calendar=calendar, as_of=_as_of(calendar))
    assert honest.absolute_return == pytest.approx(0.0)

    # (a) widen the horizon itself: the window stops being the frozen length, so
    # the row loses its number rather than quietly getting a longer one.
    with monkeypatch.context() as patched:
        patched.setattr(grader, "_horizon_exit_index", lambda entry, sessions: entry + sessions + 1)
        stretched = grader.grade_row(row, "h5", panel=panel, calendar=calendar, as_of=_as_of(calendar))
    assert stretched.state == "ungraded"
    assert stretched.ungraded_reason == "calendar_gap"
    assert stretched.absolute_return != honest.absolute_return

    # (b) widen only the PRICE READ by one session, keeping the horizon intact:
    # the post-exit spike reaches the number and the window hash changes.
    real_read = grader._read_window

    def leaky(panel_arg, symbol, sessions):
        last = calendar.index_of(sessions[-1])
        return real_read(panel_arg, symbol, tuple(sessions) + (calendar.sessions[last + 1],))

    with monkeypatch.context() as patched:
        patched.setattr(grader, "_read_window", leaky)
        leaked = grader.grade_row(row, "h5", panel=panel, calendar=calendar, as_of=_as_of(calendar))
    assert leaked.absolute_return == pytest.approx(9.0)
    assert leaked.read_window_sha256 != honest.read_window_sha256


def test_entry_is_strictly_after_known_at(calendar):
    """A row is never filled on the session during which it became knowable."""
    row = _row(calendar)
    known = grader._instant(row["known_at"])
    assert known.date() == calendar.sessions[_ENTRY_INDEX - 1]
    grade = grader.grade_row(row, "h5", panel=_panel(calendar, {"PLTR": _flat(calendar, 100.0)}),
                             calendar=calendar, as_of=_as_of(calendar))
    assert grade.entry_session > known.date()
    assert grade.entry_session == calendar.sessions[_ENTRY_INDEX]


def test_placebo_window_lies_entirely_before_issuance(calendar):
    row = _row(calendar)
    placebo = grader.grade_placebo_row(
        row, "h5", panel=_panel(calendar, {"PLTR": _flat(calendar, 100.0)}),
        calendar=calendar, family=GRV_FA1,
    )
    assert placebo.state == "graded"
    assert placebo.exit_session < calendar.sessions[_ENTRY_INDEX]
    assert placebo.entry_session == calendar.sessions[_ENTRY_INDEX + GRV_FA1.placebo_offset_sessions]


def test_grading_uses_the_horizons_frozen_on_the_row(calendar):
    """A later edit to the registration cannot re-cut a live cohort's window."""
    row = _row(calendar)
    retuned = grader.PreregisteredFamily(
        **{
            **{field: getattr(GRV_FA1, field) for field in GRV_FA1.__dataclass_fields__},
            "horizons": (grader.Horizon(name="h5", sessions=40, role="primary"),),
            "primary_horizon": "h5",
        }
    )
    panel = _panel(calendar, {"PLTR": _flat(calendar, 100.0)})
    report = _report(calendar, _log([row]), panel, family=retuned)
    graded = report["outcome_by_horizon"]["h5"]["rows"][0]
    assert graded["exit_session"] == calendar.sessions[_ENTRY_INDEX + 5].isoformat(), (
        "the row froze h5 at 5 sessions; the retuned family must not move it"
    )


# ---------------------------------------------------------------------------
# GATE 2 — ungraded rows, and a denominator fixed at issuance
# ---------------------------------------------------------------------------


def _mixed_cohort(calendar):
    winner = _row(calendar)
    loser = _row(calendar, candidate_id="grc1-000000000000000000000002", ticker="LOSR", event_id="evt-2")
    unpriced = _row(calendar, candidate_id="grc1-000000000000000000000003", ticker="NOPX", event_id="evt-3")
    unmatured = _row(
        calendar,
        candidate_id="grc1-000000000000000000000004",
        ticker="PLTR",
        event_id="evt-4",
        observation_id="gro1-000000000000000000000004",
        entry_index=len(calendar.sessions) - 3,
    )
    panel = _panel(
        calendar,
        {
            "PLTR": _step(calendar, before=100.0, after=110.0, index=_ENTRY_INDEX),
            "LOSR": _step(calendar, before=100.0, after=50.0, index=_ENTRY_INDEX),
        },
    )
    return _log([winner, loser, unpriced, unmatured]), panel


def test_unresolvable_rows_are_ungraded_and_leave_the_rate_alone(calendar):
    log, panel = _mixed_cohort(calendar)
    h5 = _report(calendar, log, panel)["outcome_by_horizon"]["h5"]

    assert h5["cohort"] == {
        "issued_n": 4,
        "graded_n": 2,
        "ungraded_n": 2,
        "ungraded_reasons": {"price_missing": 1, "horizon_not_matured": 1},
        "denominator_source": "issuance_log_cohort",
    }
    # Excluded from BOTH sides of the conditional rate.
    assert h5["hit_rate"]["numerator"] == 1
    assert h5["hit_rate"]["denominator"] == 2
    assert h5["hit_rate"]["value"] == 0.5
    # Never imputed to a neutral outcome.
    for row in h5["rows"]:
        if row["state"] == "ungraded":
            assert row["hit"] is None
            assert row["market_relative_return"] is None
            assert row["ungraded_reason"] in grader.UNGRADED_REASONS


def test_the_denominator_is_the_issuance_cohort_not_the_resolved_subset(calendar, monkeypatch):
    log, panel = _mixed_cohort(calendar)
    honest = _report(calendar, log, panel)["outcome_by_horizon"]["h5"]

    assert honest["coverage"]["universe"] == 4, "the cohort is fixed at issuance"
    assert honest["coverage"]["observed"] == 2
    assert honest["coverage"]["fraction"] == 0.5
    assert honest["coverage"]["universe"] != honest["coverage"]["observed"]
    assert honest["hit_rate_bounds"]["lower_bound_hit_rate"]["value"] == 0.25
    assert honest["hit_rate_bounds"]["upper_bound_hit_rate"]["value"] == 0.75

    # Mutation: a resolution-conditioned implementation enumerates the cohort
    # from the rows that happened to resolve. Coverage then reads "complete" and
    # the bounds collapse onto the rate — the exact way a track record inflates.
    real_cohort = grader.cohort_rows

    def resolution_conditioned(log_arg, *, family_id):
        return tuple(
            row
            for row in real_cohort(log_arg, family_id=family_id)
            if row["ticker"] in {"PLTR", "LOSR"} and "000004" not in row["candidate_id"]
        )

    monkeypatch.setattr(grader, "cohort_rows", resolution_conditioned)
    inflated = _report(calendar, log, panel)["outcome_by_horizon"]["h5"]

    assert inflated["coverage"]["universe"] == 2
    assert inflated["coverage"]["fraction"] == 1.0
    assert inflated["hit_rate_bounds"]["lower_bound_hit_rate"]["value"] == 0.5
    assert inflated["hit_rate_bounds"]["lower_bound_hit_rate"]["value"] != (
        honest["hit_rate_bounds"]["lower_bound_hit_rate"]["value"]
    ), "the assertions above must be able to see a resolution-conditioned denominator"


def test_horizon_running_off_the_calendar_is_ungraded_not_clamped(calendar):
    row = _row(calendar, entry_index=len(calendar.sessions) - 2)
    grade = grader.grade_row(
        row, "h126", panel=_panel(calendar, {"PLTR": _flat(calendar, 100.0)}),
        calendar=calendar, as_of=_as_of(calendar),
    )
    assert grade.state == "ungraded"
    assert grade.ungraded_reason == "horizon_not_matured"
    assert grade.exit_session is None


# ---------------------------------------------------------------------------
# GATE 4 — no rate without its coverage
# ---------------------------------------------------------------------------


def test_a_rate_cannot_be_built_without_coverage():
    with pytest.raises(GraderError, match="without its coverage"):
        Rate(name="x", numerator=1, denominator=2, coverage=None)  # type: ignore[arg-type]
    with pytest.raises(GraderError, match="without its coverage"):
        Rate(name="x", numerator=1, denominator=2, coverage=0.5)  # type: ignore[arg-type]


def test_the_report_walker_rejects_a_bare_rate():
    outcome = Coverage(kind="outcome", scope="s", observed=1, universe=2, status="partial").to_payload()
    with pytest.raises(GraderError, match="no coverage beside it"):
        grader.assert_rates_carry_coverage({"hit_rate": 0.5})
    with pytest.raises(GraderError, match="no coverage beside it"):
        grader.assert_rates_carry_coverage({"block": {"win_rate": {"value": 0.5}}})
    grader.assert_rates_carry_coverage({"hit_rate": 0.5, "coverage": outcome})


def test_a_rate_may_not_cite_identity_or_event_coverage():
    """The three coverages are not interchangeable, and this is where that bites."""
    identity = _identity_coverage().to_payload()
    with pytest.raises(GraderError, match="never identity or event coverage"):
        grader.assert_rates_carry_coverage({"hit_rate": 0.5, "coverage": identity})


@pytest.mark.parametrize(
    "strip",
    [
        ("outcome_by_horizon", "h5", "market_relative_return_summary"),
        ("outcome_by_horizon", "h5", "market_relative_return_bounds"),
        ("outcome_by_horizon", "h5", "absolute_return_summary"),
        ("outcome_by_horizon", "h5", "max_drawdown_summary"),
        ("outcome_by_horizon", "h5", "placebo"),
        ("outcome_by_horizon", "h5", "verdict_basis", "market_relative_return_summary"),
        ("outcome_by_horizon", "h5", "verdict_basis", "paired_placebo_delta_summary"),
        ("outcome_by_horizon", "h5", "verdict_basis", "conditional_hit_rate"),
        ("outcome_by_horizon", "h5", "hit_rate"),
    ],
)
def test_the_coverage_walker_sees_the_statistics_the_verdict_reads(calendar, strip):
    """M9. The walker was blind to every number the verdict actually reads.

    The prior version of this test asserted only that a list of ``*_rate`` paths
    was non-empty: stub the walker to ``return`` and it still passed. And the
    walker itself matched only keys ending ``_rate``/``_ratio``, so
    ``market_relative_return``, ``absolute_return``, ``max_drawdown`` and the
    placebo delta — the kill-bearing statistic among them — were structurally
    invisible to it.

    This version is non-vacuous by construction: it strips the coverage off one
    real block per parameter and requires the walker to raise. Stubbing
    ``assert_rates_carry_coverage`` to ``return`` turns every case red.
    """
    log, panel = _mixed_cohort(calendar)
    report = _report(calendar, log, panel)
    grader.assert_rates_carry_coverage(report)  # the honest report must pass

    broken = copy.deepcopy(report)
    node = broken
    for key in strip:
        node = node[key]
    assert "coverage" in node, f"{strip} must carry a coverage for this guard to bite"
    del node["coverage"]
    with pytest.raises(GraderError, match="no coverage beside it"):
        grader.assert_rates_carry_coverage(broken)


def test_the_walker_covers_every_statistic_suffix_the_report_emits(calendar):
    """A key shaped like a cohort statistic must be one the walker inspects."""
    log, panel = _mixed_cohort(calendar)
    report = _report(calendar, log, panel)

    emitted: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                emitted.add(key)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(report)
    # Every number the verdict reads must be emitted under a key the walker
    # inspects. A cohort statistic under a bare name is one the walker cannot
    # see, and "the walker passed" would then mean nothing about it.
    verdict_inputs = {
        "market_relative_return_summary",
        "paired_placebo_delta_summary",
        "paired_delta_market_relative_mean",
        "lower_bound_mean",
        "upper_bound_mean",
        "conditional_hit_rate",
    }
    assert verdict_inputs <= emitted, verdict_inputs - emitted
    for key in verdict_inputs:
        assert key.endswith(grader.COVERAGE_BEARING_SUFFIXES), (
            f"{key} is a cohort statistic under a name the coverage walker never inspects"
        )
    # The pre-fix pair alone would have missed most of them.
    assert not {"market_relative_return_summary", "lower_bound_mean"} <= {
        key for key in verdict_inputs if key.endswith(("_rate", "_ratio"))
    }


# ---------------------------------------------------------------------------
# three coverages, never one
# ---------------------------------------------------------------------------


def test_identity_event_and_outcome_coverage_stay_separate(calendar):
    log, panel = _mixed_cohort(calendar)
    report = _report(calendar, log, panel)

    assert "coverage" not in report, "there is no single fused coverage number"
    assert report["identity_coverage"]["kind"] == "identity"
    assert report["event_coverage"]["kind"] == "event"
    assert report["outcome_by_horizon"]["h5"]["coverage"]["kind"] == "outcome"
    # Three genuinely different numbers: excellent identity coverage would not
    # rescue a thin outcome cohort, and the report must keep that legible.
    assert report["identity_coverage"]["fraction"] == pytest.approx(1 / 21)
    assert report["event_coverage"]["fraction"] is None
    assert report["outcome_by_horizon"]["h5"]["coverage"]["fraction"] == 0.5


def test_a_fused_coverage_is_refused(calendar):
    log, panel = _mixed_cohort(calendar)
    fused = Coverage(kind="outcome", scope="everything at once", observed=1, universe=2, status="partial")
    with pytest.raises(GraderError, match="identity_coverage must be an identity coverage"):
        _report(calendar, log, panel, identity_coverage=fused)
    with pytest.raises(GraderError, match="event_coverage must be an event coverage"):
        _report(calendar, log, panel, event_coverage=_identity_coverage())


# ---------------------------------------------------------------------------
# the N-gate a cadence change cannot satisfy
# ---------------------------------------------------------------------------


def test_reobserving_one_event_cannot_inflate_the_cohort(calendar):
    """Nightly re-issuance of one candidate must not manufacture cohort members."""
    rows = [
        _row(calendar, observation_id=f"gro1-{index:024d}")
        for index in range(1, 31)
    ]
    assert len({row["row_id"] for row in rows}) == 30
    cohort = grader.cohort_rows(_log(rows), family_id=GRV_FA1.family_id)
    assert len(cohort) == 1
    assert cohort[0]["row_id"] == rows[0]["row_id"], "the FIRST issuance is the honest known_at"


def test_the_maturity_gate_counts_events_not_rows(calendar):
    """30 rows, one source event, one issuer, one month: not a gate."""
    rows = [
        _row(calendar, candidate_id=f"grc1-{index:024d}", observation_id=f"gro1-{index:024d}")
        for index in range(1, 31)
    ]
    coverage = Coverage(kind="outcome", scope="s", observed=30, universe=30, status="complete")
    gate = _gate(rows, family=GRV_FA1, coverage=coverage, calendar=calendar)

    assert gate["observed"]["issued"] == 30
    assert gate["observed"]["distinct_source_events"] == 1
    assert gate["observed"]["distinct_issuers"] == 1
    assert gate["observed"]["distinct_event_months"] == 1
    assert gate["satisfied"] is False, (
        "a gate satisfiable by issuance cadence alone gates nothing"
    )
    # The threshold must NAME what it counts. "min_issued" against a distinct-event
    # counter is a column-shifted row waiting to be misread.
    assert gate["required"]["min_distinct_source_events"] == GRV_FA1.min_distinct_source_events
    assert "min_issued" not in gate["required"]


def test_the_maturity_gate_is_not_satisfied_by_one_backfill_night(calendar):
    """B3. 40 events, 12 issuers, 12 event months — and ONE ``known_at``.

    Reproduces the reviewer's scenario exactly. Version 1.0.0 counted months off
    ``effective_at`` (falling back to ``known_at``), so a single backfill night
    could hand the gate forty distinct events spread over twelve historical
    months while every row shared one ``known_at`` — and therefore one entry
    session, one market window, one independent draw. The gate reported
    ``satisfied: True`` at coverage 1.0. That is the trap §6 exists to close,
    reintroduced through the wrong clock.

    ``test_the_maturity_gate_counts_events_not_rows`` above cannot see this: it
    repeats ONE candidate, so it varies neither clock independently.
    """
    shared_known_at = _known_at(calendar, _ENTRY_INDEX)
    rows = []
    for index in range(1, 41):
        # Twelve distinct issuers, forty distinct source events, and an
        # `effective_at` marching across twelve historical months.
        issuer = f"TK{index % 12:02d}"
        month = (index % 12) + 1
        rows.append(
            _row(
                calendar,
                ticker=issuer,
                candidate_id=f"grc1-{index:024d}",
                observation_id=f"gro1-{index:024d}",
                event_id=f"evt-{index}",
                effective_at=f"2025-{month:02d}-01T00:00:00+00:00",
                known_at=shared_known_at,
            )
        )
    coverage = Coverage(kind="outcome", scope="s", observed=40, universe=40, status="complete")
    family = _family_with(
        min_distinct_source_events=40,
        min_distinct_issuers=12,
        min_distinct_event_months=12,
        min_distinct_known_at_months=12,
        min_distinct_entry_sessions=12,
        min_outcome_coverage=0.70,
    )
    gate = _gate(rows, family=family, coverage=coverage, calendar=calendar)

    # The counters version 1.0.0 looked at are all satisfied.
    assert gate["observed"]["distinct_source_events"] == 40
    assert gate["observed"]["distinct_issuers"] == 12
    assert gate["observed"]["distinct_event_months"] == 12
    assert gate["observed"]["outcome_coverage_fraction"] == 1.0
    assert gate["satisfied"] is False, (
        "40 rows sharing one known_at are 40 rows and ONE independent draw; a gate "
        "that reads the event clock and ignores the entry clock does not gate"
    )
    # ...because the counters that matter are not.
    assert gate["observed"]["distinct_known_at_months"] == 1
    assert gate["observed"]["distinct_entry_sessions"] == 1, (
        "one known_at is one entry session is one market window"
    )


# ---------------------------------------------------------------------------
# median vs pooled
# ---------------------------------------------------------------------------


def test_monthly_median_and_pooled_rate_are_emitted_together_and_can_disagree():
    coverage = Coverage(kind="outcome", scope="s", observed=8, universe=8, status="complete")
    per_row = [
        ("2026-01", False),
        ("2026-02", False),
        *[("2026-03", True) for _ in range(6)],
    ]
    block = grader.monthly_and_pooled(per_row, coverage=coverage, name="demo_rate")

    assert block["median_of_monthly_hit_rate"] == 0.0
    assert block["pooled_hit_rate"]["value"] == 0.75
    assert block["median_of_monthly_hit_rate"] < 0.5 < block["pooled_hit_rate"]["value"], (
        "this fixture is the sign flip; both numbers must be published side by side"
    )
    assert block["months"] == 3


def test_a_live_report_publishes_both(calendar):
    log, panel = _mixed_cohort(calendar)
    block = _report(calendar, log, panel)["outcome_by_horizon"]["h5"]["hit_rate_by_month"]
    assert "median_of_monthly_hit_rate" in block
    assert "pooled_hit_rate" in block
    assert block["pooled_hit_rate"]["coverage"]["kind"] == "outcome"


# ---------------------------------------------------------------------------
# price vintages
# ---------------------------------------------------------------------------


def test_a_panel_on_the_wrong_basis_is_refused(calendar):
    log, _panel_unused = _mixed_cohort(calendar)
    raw = _panel(calendar, {"PLTR": _flat(calendar, 100.0)}, adjustment="raw")
    with pytest.raises(GraderError, match="registered price basis"):
        _report(calendar, log, raw)


def test_grades_record_their_vintage_and_drift_is_surfaced(calendar):
    row = _row(calendar)
    first = grader.grade_row(
        row, "h5", panel=_panel(calendar, {"PLTR": _flat(calendar, 100.0)}, vintage_id="v1"),
        calendar=calendar, as_of=_as_of(calendar),
    )
    assert first.price_basis["vintage_id"] == "v1"

    readjusted = _flat(calendar, 100.0)
    readjusted[calendar.sessions[_ENTRY_INDEX + 5]] = 104.0  # upstream re-adjustment, in place
    second = grader.grade_row(
        row, "h5", panel=_panel(calendar, {"PLTR": readjusted}, vintage_id="v2"),
        calendar=calendar, as_of=_as_of(calendar),
    )
    assert second.absolute_return != first.absolute_return

    drift = grader.regrade_diff([first.to_payload()], [second.to_payload()])
    assert len(drift) == 1
    assert drift[0]["prior_price_basis"]["vintage_id"] == "v1"
    assert drift[0]["current_price_basis"]["vintage_id"] == "v2"
    assert drift[0]["prior_market_relative_return"] != drift[0]["current_market_relative_return"]


# ---------------------------------------------------------------------------
# the verdict — proof that this instrument can return "no"
# ---------------------------------------------------------------------------


def _reachable_family(**overrides) -> grader.PreregisteredFamily:
    """GRV-FA1's RULES with a gate a fixture can reach.

    The thresholds are the registered family's business; what this exercises is
    whether the decision rule can emit each state at all. A kill condition no
    code path can produce is a detector with an unsatisfiable precondition.
    """
    reachable = dict(
        horizons=(grader.Horizon(name="h5", sessions=5, role="primary"),),
        primary_horizon="h5",
        min_distinct_source_events=1,
        min_distinct_issuers=1,
        min_distinct_event_months=1,
        min_distinct_known_at_months=1,
        min_distinct_entry_sessions=1,
        min_outcome_coverage=0.5,
        min_verdict_outcome_coverage=0.5,
    )
    reachable.update(overrides)
    return _family_with(**reachable)


def _placebo_aware_series(calendar, *, event_move: float, placebo_move: float) -> dict[date, float]:
    closes = _flat(calendar, 100.0)
    placebo_entry = _ENTRY_INDEX + GRV_FA1.placebo_offset_sessions
    for offset in range(1, 6):
        closes[calendar.sessions[placebo_entry + offset]] = 100.0 * (1 + placebo_move)
        closes[calendar.sessions[_ENTRY_INDEX + offset]] = 100.0 * (1 + event_move)
    return closes


def test_the_kill_condition_is_reachable(calendar):
    """A losing cohort must actually produce KILL, not a permanent 'accruing'."""
    panel = _panel(calendar, {"PLTR": _placebo_aware_series(calendar, event_move=-0.10, placebo_move=0.0)})
    report = _report(calendar, _log([_row(calendar)]), panel, family=_reachable_family())

    assert report["verdict_state"] == "kill"
    assert report["verdict"]["kill_condition_id"] == GRV_FA1.kill_condition_id
    assert report["verdict"]["gate_satisfied"] is True
    assert report["verdict"]["inputs"]["pooled_market_relative_mean"] < 0
    assert report["verdict"]["inputs"]["placebo_delta_market_relative_mean"] <= 0
    assert "never deletes the layer" in report["verdict"]["meaning"]


def test_a_cohort_that_cannot_beat_its_own_placebo_is_a_null(calendar):
    panel = _panel(calendar, {"PLTR": _placebo_aware_series(calendar, event_move=0.10, placebo_move=0.10)})
    report = _report(calendar, _log([_row(calendar)]), panel, family=_reachable_family())

    assert report["verdict_state"] == "tested_null"
    assert report["verdict"]["inputs"]["pooled_market_relative_mean"] > 0
    assert report["verdict"]["inputs"]["placebo_delta_market_relative_mean"] == pytest.approx(0.0)


def test_a_supported_verdict_buys_nothing(calendar):
    panel = _panel(calendar, {"PLTR": _placebo_aware_series(calendar, event_move=0.10, placebo_move=0.0)})
    report = _report(calendar, _log([_row(calendar)]), panel, family=_reachable_family())

    assert report["verdict_state"] == "supported"
    assert "not a promotion" in report["verdict"]["meaning"]
    assert report["verdict"]["authority_effect"] == "none in every branch; a ruling is an operator act"
    assert report["authority"]["can_rank"] is False
    assert report["authority"]["can_size"] is False
    assert report["authority"]["can_gate"] is False


def test_an_unmet_gate_expires_instead_of_accruing_forever(calendar):
    """'Still accruing' must stop being an available answer on the registered date."""
    panel = _panel(calendar, {"PLTR": _flat(calendar, 100.0)})
    strict = _reachable_family(min_distinct_source_events=99)

    before = _report(calendar, _log([_row(calendar)]), panel, family=strict)
    assert before["verdict_state"] == "accruing"

    expiry = date.fromisoformat(GRV_FA1.accrual_expiry_date)
    after = _report(
        calendar,
        _log([_row(calendar)]),
        panel,
        family=strict,
        as_of=datetime.combine(expiry + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
    )
    assert after["verdict_state"] == "expired_unmeasurable"
    assert after["verdict"]["gate_satisfied"] is False


def _two_row_cohort(calendar):
    """The reviewer's B1 fixture: a +1% winner and a −40% loser."""
    winner = _row(calendar, candidate_id="grc1-000000000000000000000001", ticker="PLTR", event_id="evt-1")
    loser = _row(
        calendar,
        candidate_id="grc1-000000000000000000000002",
        observation_id="gro1-000000000000000000000002",
        ticker="LOSR",
        event_id="evt-2",
    )
    panel = _panel(
        calendar,
        {
            "PLTR": _placebo_aware_series(calendar, event_move=0.01, placebo_move=0.0),
            "LOSR": _placebo_aware_series(calendar, event_move=-0.40, placebo_move=0.0),
        },
    )
    return winner, loser, panel


def test_a_supersession_cannot_ungrade_its_way_out_of_a_kill(calendar):
    """B1. The kill-bearing statistic must not be gameable by post-hoc ungrading.

    §8 promises "you cannot retract your way out of a loss; you can only pay for
    it in coverage". That was true for the hit rate — which has carried Manski
    bounds since day one — and FALSE for the verdict, which read the pooled mean
    over ``graded`` rows only, unbounded and with no sensitivity beside it.

    On this two-row cohort (+1% winner, −40% loser) the reviewer moved the loser
    to ``ungraded`` and watched the verdict walk from ``kill`` to
    ``tested_null`` with ``issued_n`` unchanged at 2:

        honest:      mean=-0.1950  delta=-0.1950  verdict=kill
        after corr:  mean=+0.0100  delta=+0.0100  verdict=tested_null

    The supersession ratchet closes it: the append-only log keeps the superseded
    row byte-identical forever, so the grade it already earned is still
    computable, and the verdict basis retains it. Coverage is deliberately NOT
    repaired — the retraction still lowers coverage and still widens the bounds,
    exactly as §8 says. What it cannot do is delete a number.
    """
    winner, loser, panel = _two_row_cohort(calendar)
    family = _reachable_family()

    honest = _report(calendar, _log([winner, loser]), panel, family=family)
    assert honest["verdict_state"] == "kill"
    honest_inputs = honest["verdict"]["inputs"]
    assert honest_inputs["pooled_market_relative_mean"] == pytest.approx(-0.195)

    # The discretionary act §8 explicitly permits: retract the loser.
    retraction = grader.build_correction_row(
        loser,
        reason="source_receipt_binding_failed",
        appended_at="2026-08-07T00:00:00+00:00",
        retract=True,
    )
    after = _report(calendar, _log([winner, loser, retraction]), panel, family=family)
    h5 = after["outcome_by_horizon"]["h5"]

    # §8 is honoured on both sides: coverage falls and the bounds widen...
    assert h5["cohort"]["issued_n"] == 2
    assert h5["coverage"]["observed"] == 1 and h5["coverage"]["universe"] == 2
    assert h5["hit_rate_bounds"]["lower_bound_hit_rate"]["value"] == 0.5
    # ...and the verdict does not move.
    assert after["verdict_state"] == "kill", (
        "an ungraded loser must not be an exit from the kill-bearing statistic"
    )
    assert after["verdict"]["inputs"]["pooled_market_relative_mean"] == pytest.approx(-0.195)
    retained = h5["verdict_basis"]["retained_from_superseded"]
    assert [entry["retained_ticker"] for entry in retained] == ["LOSR"]
    assert retained[0]["effective_ungraded_reason"] == "retracted"


def test_the_verdict_refuses_to_fire_below_the_registered_coverage_floor(calendar):
    """B1, second protection: a resolution failure the ratchet cannot repair.

    A price outage is not a discretionary act, so the ratchet has no superseded
    grade to retain — and the pooled mean over "the rows that resolved" is then
    a resolution-conditioned statistic, the same defect §5 names for rates
    applied to the number the verdict reads. Below the registered
    ``min_verdict_outcome_coverage`` no verdict fires at all. Not a softer one:
    ``accruing``, with the reason named. Escaping into a softer decided state is
    the same escape.
    """
    winner, loser, _panel_unused = _two_row_cohort(calendar)
    family = _reachable_family(min_verdict_outcome_coverage=0.70)

    complete = _panel(
        calendar,
        {
            "PLTR": _placebo_aware_series(calendar, event_move=0.01, placebo_move=0.0),
            "LOSR": _placebo_aware_series(calendar, event_move=-0.40, placebo_move=0.0),
        },
    )
    assert _report(calendar, _log([winner, loser]), complete, family=family)["verdict_state"] == "kill"

    # The loser's prices go missing. Nothing superseded it, so there is no grade
    # to retain: 1 of 2 rows resolves, and 0.5 is below the registered floor.
    outage = _panel(
        calendar, {"PLTR": _placebo_aware_series(calendar, event_move=0.01, placebo_move=0.0)}
    )
    blocked = _report(calendar, _log([winner, loser]), outage, family=family)

    assert blocked["outcome_by_horizon"]["h5"]["cohort"]["ungraded_reasons"] == {"price_missing": 1}
    assert blocked["verdict_state"] == "accruing"
    assert (
        blocked["verdict"]["verdict_blocked_reason"]
        == "verdict_basis_coverage_below_registered_floor"
    )
    assert blocked["verdict"]["verdict_blocked_reason"] in grader.VERDICT_BLOCKED_REASONS


def test_a_point_estimate_is_not_a_verdict(calendar):
    """M2. Every verdict region tests an INTERVAL against its threshold.

    Version 1.0.0 compared bare point estimates to 0, +1.0pp and 0.50. At its
    gate floor (~40 graded h63 rows) with single-name 63-session market-relative
    SD of 15–25pp, SE of the delta is ~3.4–5.6pp, so a preregistered KILL fired
    on noise ~25–40% of the time under a true null and ~15–25% of the time
    against a genuine +3pp edge.

    This cohort is the small version of that: two hits, a large pooled delta,
    and dispersion wide enough that the interval cannot separate it from the
    registered minimum interesting effect. A point rule calls it ``supported``.
    """
    winner = _row(calendar, candidate_id="grc1-000000000000000000000001", ticker="PLTR", event_id="evt-1")
    barely = _row(
        calendar,
        candidate_id="grc1-000000000000000000000002",
        observation_id="gro1-000000000000000000000002",
        ticker="TINY",
        event_id="evt-2",
    )
    panel = _panel(
        calendar,
        {
            "PLTR": _placebo_aware_series(calendar, event_move=0.60, placebo_move=0.0),
            "TINY": _placebo_aware_series(calendar, event_move=0.005, placebo_move=0.0),
        },
    )
    report = _report(calendar, _log([winner, barely]), panel, family=_reachable_family())
    h5 = report["outcome_by_horizon"]["h5"]

    # Both rows are hits and the pooled delta is enormous by any point rule.
    assert h5["hit_rate"]["value"] == 1.0
    assert report["verdict_state"] == "tested_null", (
        "a mean this noisy is not separable from the registered minimum interesting "
        "effect; a point comparison at the gate floor is a coin flip"
    )

    basis = h5["verdict_basis"]
    assert basis["paired_placebo_delta_summary"]["mean"] == pytest.approx(0.3025)

    # The spread is emitted, and the interval does not clear the threshold.
    summary = basis["market_relative_return_summary"]
    assert summary["sd"] > 0.4
    assert summary["standard_error"] > 0.2
    assert summary["ci_lower"] is not None and summary["ci_upper"] is not None
    assert summary["ci_level"] == GRV_FA1.confidence_level
    delta_ci_lower = basis["paired_placebo_delta_summary"]["ci_lower"]
    assert delta_ci_lower <= GRV_FA1.minimum_interesting_effect


def _synthetic_primary_block(
    *,
    family,
    mean,
    mean_ci,
    delta,
    delta_ci,
    conditional_hit_rate,
    hit_rate_ci_lower,
    coverage_fraction,
    issued_n=1000,
):
    """A primary-horizon block carrying BOTH the pre-fix and post-fix key shapes.

    Both shapes on purpose: this test has to be readable by the implementation it
    is indicting, or its red is a ``KeyError`` about renamed keys rather than a
    statement about the decision rule.
    """
    graded_n = round(issued_n * coverage_fraction)
    hits = round(graded_n * conditional_hit_rate)
    coverage = Coverage(
        kind="outcome", scope="synthetic", observed=graded_n, universe=issued_n, status="partial"
    ).to_payload()
    summary = lambda value, ci: {  # noqa: E731 - a fixture shape, not a code path
        "n": graded_n,
        "mean": value,
        "median": value,
        "min": value,
        "max": value,
        "sd": 0.25,
        "standard_error": 0.25 / (graded_n ** 0.5),
        "ci_lower": ci[0],
        "ci_upper": ci[1],
        # getattr defaults keep this fixture buildable against an implementation
        # that has not registered these thresholds yet, so the red below is about
        # the decision rule and not about a missing attribute.
        "ci_level": getattr(family, "confidence_level", 0.95),
        "ci_method": "percentile_bootstrap",
        "ci_resamples": getattr(family, "bootstrap_resamples", 2000),
        "coverage": coverage,
    }
    return {
        "coverage": coverage,
        "gate": {"satisfied": True, "required": {}, "observed": {}, "note": "synthetic"},
        "hit_rate": {"value": conditional_hit_rate, "coverage": coverage},
        "hit_rate_bounds": {
            "lower_bound_hit_rate": {"value": hits / issued_n, "coverage": coverage},
            "upper_bound_hit_rate": {
                "value": (hits + issued_n - graded_n) / issued_n,
                "coverage": coverage,
            },
        },
        # pre-fix shape
        "market_relative_return": {"mean": mean},
        "placebo": {"delta_market_relative_mean": delta},
        # post-fix shape
        "verdict_basis": {
            "n": graded_n,
            "coverage": {**coverage, "fraction": coverage_fraction},
            "market_relative_return_summary": summary(mean, mean_ci),
            "paired_placebo_delta_summary": summary(delta, delta_ci),
            "conditional_hit_rate": {
                "value": conditional_hit_rate,
                "ci_lower": hit_rate_ci_lower,
                "coverage": coverage,
            },
            "retained_from_superseded": [],
        },
    }


def test_the_registered_family_still_carries_its_real_thresholds():
    """The reachable-family fixture must not be mistaken for the registration.

    M3: and the registered constants must be JOINTLY SATISFIABLE. Asserting that
    each constant has the value it has proves nothing about whether any data
    configuration can satisfy them together — version 1.0.0 passed that check
    while shipping a ``SUPPORTED`` branch no plausible signal could reach,
    because it tested ``hits/issued > 0.50`` over the FIXED cohort and
    ``hits/issued = p·coverage``: at the registered 0.70 coverage floor that
    demanded a conditional h63 hit rate above 71.4%.
    """
    assert GRV_FA1.min_distinct_issuers == 12
    assert GRV_FA1.min_distinct_event_months == 12
    assert GRV_FA1.min_outcome_coverage == 0.70
    assert GRV_FA1.primary_horizon == "h63"

    as_of = datetime(2027, 1, 1, tzinfo=timezone.utc)

    # JOINT SATISFIABILITY, at the REGISTERED constants and at exactly the
    # registered coverage floor. A conditional hit rate of 0.60 is a strong but
    # plausible equity signal at a one-quarter horizon; 0.714 is not.
    supported = _synthetic_primary_block(
        family=GRV_FA1,
        mean=0.05,
        mean_ci=(0.02, 0.08),
        delta=0.06,
        delta_ci=(0.04, 0.08),
        conditional_hit_rate=0.60,
        hit_rate_ci_lower=0.55,
        coverage_fraction=GRV_FA1.min_outcome_coverage,
    )
    verdict = grader.evaluate_verdict({"h63": supported}, family=GRV_FA1, as_of=as_of)
    assert verdict["state"] == "supported", (
        "SUPPORTED must be reachable at the registered thresholds by a plausible "
        "signal; a branch no data can reach is an unsatisfiable precondition"
    )

    # ...and KILL is reachable at the same constants, so the instrument has two
    # answers rather than one.
    killed = _synthetic_primary_block(
        family=GRV_FA1,
        mean=-0.01,
        mean_ci=(-0.04, 0.005),
        delta=-0.005,
        delta_ci=(-0.03, 0.02),
        conditional_hit_rate=0.48,
        hit_rate_ci_lower=0.43,
        coverage_fraction=GRV_FA1.min_outcome_coverage,
    )
    assert grader.evaluate_verdict({"h63": killed}, family=GRV_FA1, as_of=as_of)["state"] == "kill"

    # The registered N is the N the registered effect needs, not a round number:
    # δ* = 3.0pp at σ_paired = 25pp, alpha 0.05, power 0.80 → N ≥ (0.25/0.0107)².
    assert GRV_FA1.min_distinct_source_events == GRV_FA1.planning_n_required
    assert GRV_FA1.planning_n_required >= (
        GRV_FA1.planning_sd_paired / (GRV_FA1.minimum_interesting_effect / 2.80)
    ) ** 2


def test_the_verdict_is_evaluated_once_and_latched(calendar):
    """§7 promises ONE look. Recomputing nightly is optional stopping."""
    winner, loser, panel = _two_row_cohort(calendar)
    family = _reachable_family()
    first = _report(calendar, _log([winner, loser]), panel, family=family)
    assert first["verdict_state"] == "kill"
    assert first["verdict"]["latched"] is False

    kinder = _panel(
        calendar,
        {
            "PLTR": _placebo_aware_series(calendar, event_move=0.30, placebo_move=0.0),
            "LOSR": _placebo_aware_series(calendar, event_move=0.30, placebo_move=0.0),
        },
    )
    later = _report(
        calendar,
        _log([winner, loser]),
        kinder,
        family=family,
        latched_verdict={**first["verdict"], "latched_at": "2026-08-06T12:00:00+00:00"},
    )
    assert later["verdict_state"] == "kill", "the latched verdict is the verdict"
    assert later["verdict"]["latched"] is True
    assert later["verdict"]["recomputed_state"] == "supported"
    assert later["verdict"]["latched_at"] == "2026-08-06T12:00:00+00:00"


# ---------------------------------------------------------------------------
# authority
# ---------------------------------------------------------------------------


def test_authority_is_display_only_everywhere(calendar):
    log, panel = _mixed_cohort(calendar)
    report = _report(calendar, log, panel)
    expected = _candidate(calendar)["authority"]

    assert report["authority"] == expected
    assert log.rows[0]["authority"] == expected
    assert report["verdict_state"] == "accruing"
    for flag in ("can_rank", "can_size", "can_gate", "can_originate_signal", "can_add_candidates", "can_escalate"):
        assert report["authority"][flag] is False


def test_prices_are_only_reachable_through_the_audited_accessor():
    """The window hash proves what was consumed only if nothing bypasses it.

    ``read_window_sha256`` covers the triples that pass through ``_read_window``.
    A direct ``panel.close(...)`` anywhere else would read a bar that the hash
    cannot see, which is how a leakage guard goes quietly blind.
    """
    source = (ROOT / "engine" / "government_revenue" / "candidate_grader.py").read_text(encoding="utf-8")
    calls = [
        (number, line)
        for number, line in enumerate(source.splitlines(), start=1)
        if ".close(" in line and "def close" not in line
    ]
    assert len(calls) == 1, f"price reads outside _read_window: {calls}"
    inside = source.split("def _read_window(", 1)[1].split("\ndef ", 1)[0]
    assert calls[0][1].strip() in inside


def test_no_promotion_language_in_the_instrument():
    source = (ROOT / "engine" / "government_revenue" / "candidate_grader.py").read_text(encoding="utf-8")
    lowered = source.lower()
    assert "validated" not in lowered
    assert "已验证" not in source


def test_report_is_canonically_serializable(calendar):
    log, panel = _mixed_cohort(calendar)
    report = _report(calendar, log, panel)
    assert json.loads(grader.canonical_bytes(report)) == json.loads(json.dumps(report))
    assert report["contract"] == grader.REPORT_CONTRACT
    assert report["issuance_log"]["line_count"] == 4


def test_the_zero_candidate_state_reports_cleanly(calendar):
    """Today's actual state: an empty ledger is a result, not a crash.

    The lobe has zero candidates by design. A grader that raises, divides by
    zero, or quietly prints 0.0 on an empty cohort would push a future session
    toward manufacturing activity to make the screen look alive.
    """
    report = _report(calendar, _log([]), _panel(calendar, {"PLTR": _flat(calendar, 100.0)}))

    assert report["admission"] == {
        "considered": 0,
        "issued": 0,
        "abstained": 0,
        "abstention_rate": {
            "name": "grv-fa1.abstention_rate",
            "numerator": 0,
            "denominator": 0,
            "value": None,
            "coverage": {
                "kind": "outcome",
                "scope": "candidates the family considered, from the append-only issuance log",
                "observed": 0,
                "universe": 0,
                "fraction": None,
                "status": "empty",
            },
        },
        "abstention_reasons": {},
    }
    h63 = report["outcome_by_horizon"]["h63"]
    assert h63["hit_rate"]["value"] is None, "an empty cohort has no rate, not a zero"
    assert h63["coverage"]["fraction"] is None
    assert h63["gate"]["satisfied"] is False
    assert report["prereg_document_sha256"] == []
    assert report["verdict_state"] == "accruing"


def test_calibration_asserts_a_direction_and_never_invents_a_probability(calendar):
    log, panel = _mixed_cohort(calendar)
    block = _report(calendar, log, panel)["outcome_by_horizon"]["h5"]["calibration"]

    assert block["asserted_direction"] == "possible_positive"
    assert block["asserted_probability"] is None, (
        "the candidate contract carries no probability; a reliability curve here would be invented"
    )
    assert block["realized_direction_rate"]["value"] == 0.5
    assert block["placebo_base_rate"]["coverage"]["kind"] == "outcome"
    assert "reliability curve" in block["limitation"]


def test_a_document_edit_mid_cohort_is_visible_in_the_report(calendar):
    """§9 forbids editing a live cohort's terms; the report must not hide it."""
    first = _row(calendar)
    second = grader.build_issuance_row(
        _candidate(calendar, candidate_id="grc1-000000000000000000000002", event_id="evt-2"),
        family=GRV_FA1,
        prereg_document_sha256="b" * 64,  # the document changed underneath
        price_basis=_basis(),
        appended_at=_APPENDED_AT,
    )
    report = _report(
        calendar,
        _log([first, second]),
        _panel(calendar, {"PLTR": _flat(calendar, 100.0)}),
    )
    assert report["prereg_document_sha256"] == sorted({_DIGEST, "b" * 64})
    assert len(report["prereg_document_sha256"]) == 2


# ---------------------------------------------------------------------------
# session calendar
# ---------------------------------------------------------------------------


def test_calendar_refuses_ambiguous_input():
    with pytest.raises(GraderError, match="empty"):
        SessionCalendar.from_dates([], calendar_id="x")
    with pytest.raises(GraderError, match="duplicate"):
        SessionCalendar.from_dates([date(2026, 1, 5), date(2026, 1, 5)], calendar_id="x")
    with pytest.raises(GraderError, match="dates, not datetimes"):
        SessionCalendar.from_dates([datetime(2026, 1, 5)], calendar_id="x")


def test_grading_refuses_a_foreign_calendar(calendar):
    other = SessionCalendar.from_dates(calendar.sessions, calendar_id="hk_equity_sessions")
    with pytest.raises(GraderError, match="calendar frozen at issuance"):
        grader.grade_row(
            _row(calendar), "h5", panel=_panel(calendar, {"PLTR": _flat(calendar, 100.0)}),
            calendar=other, as_of=_as_of(calendar),
        )


def _as_of(calendar: SessionCalendar) -> datetime:
    return datetime.combine(calendar.sessions[-1], datetime.min.time(), tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# the remaining reviewer findings
# ---------------------------------------------------------------------------


def test_a_missing_late_discovery_flag_abstains(calendar):
    """M6. The only fail-OPEN admission test in the family.

    ``bool(source_event.get("is_late_discovery"))`` admitted any payload that
    simply omitted the key. Every sibling check is fail-closed, and §1 makes this
    the guard against measuring stale news.
    """
    payload = _candidate(calendar)
    payload["source_event"] = {
        key: value for key, value in payload["source_event"].items() if key != "is_late_discovery"
    }
    assert grader.admit(payload, family=GRV_FA1).reason == "late_discovery"

    for value in (None, "false", 0, ""):
        payload = _candidate(calendar)
        payload["source_event"] = {**payload["source_event"], "is_late_discovery": value}
        assert grader.admit(payload, family=GRV_FA1).reason == "late_discovery", (
            f"{value!r} is not evidence of a fresh discovery"
        )


def test_the_placebo_delta_is_paired_over_identical_rows(calendar):
    """M1. An unpaired difference of means is a difference of different cohorts.

    On the suite's own ``_mixed_cohort`` the real side has n=2 and the placebo
    side n=3: rows that are ``horizon_not_matured`` on the event window are
    graded on the placebo window, 252 sessions earlier. The prior delta
    subtracted one mean from the other and fed the result to the kill condition.
    """
    winner = _row(calendar, candidate_id="grc1-000000000000000000000001", ticker="AAA", event_id="evt-1")
    loser = _row(
        calendar,
        candidate_id="grc1-000000000000000000000002",
        observation_id="gro1-000000000000000000000002",
        ticker="BBB",
        event_id="evt-2",
    )
    # Matured on the placebo window, NOT matured on the event window: graded on
    # one side of the subtraction and absent from the other.
    unmatured = _row(
        calendar,
        candidate_id="grc1-000000000000000000000003",
        observation_id="gro1-000000000000000000000003",
        ticker="CCC",
        event_id="evt-3",
        entry_index=len(calendar.sessions) - 3,
    )
    ccc = _flat(calendar, 100.0)
    placebo_entry = len(calendar.sessions) - 3 + GRV_FA1.placebo_offset_sessions
    for offset in range(1, 6):
        ccc[calendar.sessions[placebo_entry + offset]] = 140.0
    panel = _panel(
        calendar,
        {
            "AAA": _step(calendar, before=100.0, after=110.0, index=_ENTRY_INDEX),
            "BBB": _step(calendar, before=100.0, after=50.0, index=_ENTRY_INDEX),
            "CCC": ccc,
        },
    )
    h5 = _report(calendar, _log([winner, loser, unmatured]), panel)["outcome_by_horizon"]["h5"]
    placebo = h5["placebo"]

    assert h5["coverage"]["observed"] == 2
    assert placebo["placebo_coverage"]["observed"] == 3, (
        "the two sides genuinely resolve different rows; that is the defect"
    )
    assert placebo["paired_n"] == 2
    assert placebo["coverage"]["observed"] == placebo["paired_n"]
    assert placebo["paired_delta_market_relative_mean"] != placebo[
        "unpaired_delta_market_relative_mean"
    ], "this fixture must be able to see the difference between paired and unpaired"

    basis = h5["verdict_basis"]["paired_placebo_delta_summary"]
    assert basis["n"] == placebo["paired_n"]


def test_the_placebo_carries_the_same_refusals_as_the_grade(calendar):
    """m7. A baseline on a foreign calendar or basis is not a baseline."""
    row = _row(calendar)
    other = SessionCalendar.from_dates(calendar.sessions, calendar_id="hk_equity_sessions")
    with pytest.raises(GraderError, match="calendar frozen at issuance"):
        grader.grade_placebo_row(
            row, "h5", panel=_panel(calendar, {"PLTR": _flat(calendar, 100.0)}),
            calendar=other, family=GRV_FA1,
        )
    with pytest.raises(GraderError, match="basis pinned at issuance"):
        grader.grade_placebo_row(
            row, "h5", panel=_panel(calendar, {"PLTR": _flat(calendar, 100.0)}, adjustment="raw"),
            calendar=calendar, family=GRV_FA1,
        )


def test_the_read_window_hash_is_order_sensitive(calendar):
    """m1. A sorted hash is permutation-invariant, so an inversion is invisible."""
    closes = _flat(calendar, 100.0)
    for offset in range(1, 6):
        closes[calendar.sessions[_ENTRY_INDEX + offset]] = 100.0 + offset
    panel = _panel(calendar, {"PLTR": closes})
    honest = grader.grade_row(_row(calendar), "h5", panel=panel, calendar=calendar, as_of=_as_of(calendar))

    real_read = grader._read_window

    def inverted(panel_arg, symbol, sessions):
        return real_read(panel_arg, symbol, tuple(reversed(tuple(sessions))))

    original = grader._read_window
    grader._read_window = inverted
    try:
        flipped = grader.grade_row(
            _row(calendar), "h5", panel=panel, calendar=calendar, as_of=_as_of(calendar)
        )
    finally:
        grader._read_window = original

    assert flipped.absolute_return != honest.absolute_return, "the fixture must invert the sign"
    assert flipped.read_window_sha256 != honest.read_window_sha256, (
        "an entry/exit inversion flips every return; the window hash must be able to see it"
    )


def test_overlapping_windows_are_disclosed_beside_issued_n(calendar):
    """M8. Two rows on one ticker five sessions apart are not two draws."""
    first = _row(calendar, candidate_id="grc1-000000000000000000000001", event_id="evt-1")
    second = _row(
        calendar,
        candidate_id="grc1-000000000000000000000002",
        observation_id="gro1-000000000000000000000002",
        event_id="evt-2",
        entry_index=_ENTRY_INDEX + 5,
    )
    panel = _panel(calendar, {"PLTR": _flat(calendar, 100.0)})
    h21 = _report(calendar, _log([first, second]), panel)["outcome_by_horizon"]["h21"]
    independence = h21["window_independence"]

    assert h21["cohort"]["issued_n"] == 2
    assert independence["distinct_tickers"] == 1
    assert independence["distinct_entry_sessions"] == 2
    assert independence["overlapping_window_pairs"] == 1
    assert independence["max_window_overlap_sessions"] == 17
    assert independence["non_overlapping_window_estimate"] == 1, (
        "two h21 windows five sessions apart are two rows and about one draw"
    )


def test_no_verdict_region_ships_a_label_that_contradicts_its_numbers():
    """M4. ``mean <= 0 and delta > 0`` fell through to a 'positive but...' label."""
    as_of = datetime(2027, 1, 1, tzinfo=timezone.utc)
    block = _synthetic_primary_block(
        family=GRV_FA1,
        mean=-0.02,
        mean_ci=(-0.06, 0.05),
        delta=0.01,
        delta_ci=(-0.02, 0.06),
        conditional_hit_rate=0.49,
        hit_rate_ci_lower=0.44,
        coverage_fraction=GRV_FA1.min_outcome_coverage,
    )
    verdict = grader.evaluate_verdict({"h63": block}, family=GRV_FA1, as_of=as_of)
    assert verdict["state"] == "tested_null"
    assert "positive but" not in verdict["meaning"], (
        "the cohort mean here is negative; the label must not assert a sign"
    )
    assert verdict["inputs"]["pooled_market_relative_mean"] < 0
    assert "makes no claim about the sign" in verdict["meaning"]


def test_every_decision_threshold_lives_in_the_binding_declaration():
    """M5. Two of three verdict thresholds sat where the drift guard was blind."""
    declaration = GRV_FA1.to_payload()
    assert declaration["decision_rule"] == {
        "minimum_interesting_effect": GRV_FA1.minimum_interesting_effect,
        "hit_rate_floor": GRV_FA1.hit_rate_floor,
        "confidence_level": GRV_FA1.confidence_level,
        "bootstrap_resamples": GRV_FA1.bootstrap_resamples,
        "bootstrap_seed": GRV_FA1.bootstrap_seed,
        "min_verdict_outcome_coverage": GRV_FA1.min_verdict_outcome_coverage,
    }
    source = (ROOT / "engine" / "government_revenue" / "candidate_grader.py").read_text(encoding="utf-8")
    assert "_PLACEBO_FLOOR" not in source, "a threshold in a module constant is not registered"
    assert "lower > 0.5" not in source

    # Mutation: moving a threshold moves the verdict, so the declaration is
    # load-bearing rather than decorative.
    as_of = datetime(2027, 1, 1, tzinfo=timezone.utc)
    block = _synthetic_primary_block(
        family=GRV_FA1,
        mean=0.05,
        mean_ci=(0.02, 0.08),
        delta=0.06,
        delta_ci=(0.04, 0.08),
        conditional_hit_rate=0.60,
        hit_rate_ci_lower=0.55,
        coverage_fraction=GRV_FA1.min_outcome_coverage,
    )
    assert grader.evaluate_verdict({"h63": block}, family=GRV_FA1, as_of=as_of)["state"] == "supported"
    stricter = _family_with(minimum_interesting_effect=0.05)
    assert grader.evaluate_verdict({"h63": block}, family=stricter, as_of=as_of)["state"] == "tested_null"

    # ...and the document/code drift guard actually reads the block.
    family, _digest = grader.load_family_declaration(PREREG_PATH)
    assert family.minimum_interesting_effect == GRV_FA1.minimum_interesting_effect
    assert family.min_verdict_outcome_coverage == GRV_FA1.min_verdict_outcome_coverage


def test_the_preregistration_states_its_power_calculation():
    text = PREREG_PATH.read_text(encoding="utf-8")
    assert "power calculation" in text.lower()
    assert str(GRV_FA1.planning_n_required) in text
    assert "minimum interesting effect" in text.lower()
    assert GRV_FA1.accrual_expiry_date in text


# ---------------------------------------------------------------------------
# GATE — earnings-window and subsequent-filings disclosure labels (§11)
#
# Wave 9G's build list asks for "earnings-window and subsequent-filings outcome
# labels where available". The trap this section is built around is the third
# word of the answer: "where available" is where a label layer lies, because the
# natural implementation returns an empty list for an issuer nobody has data
# for, and an empty list reads as a clean, uncontaminated window. Every issuer
# with the WORST data would score as the CLEANEST. So the split between
# "looked and found nothing" and "could not look" is what these tests defend,
# alongside the two point-in-time clamps.
# ---------------------------------------------------------------------------


def _event(
    calendar: SessionCalendar,
    index: int,
    *,
    kind: str = "earnings",
    ticker: str = "PLTR",
    known_offset_days: int = -1,
    reference: str = "acc-0001",
) -> "grader.DisclosureEvent":
    """A disclosure on session ``index``, knowable ``known_offset_days`` from it."""
    day = calendar.sessions[index]
    known = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(
        days=known_offset_days
    )
    return grader.DisclosureEvent(
        kind=kind, ticker=ticker, event_date=day, known_at=known.isoformat(), reference=reference
    )


def _disclosure(events, *, covered=("PLTR",), outage=()) -> "grader.DisclosureCalendar":
    return grader.DisclosureCalendar.build(
        events,
        calendar_id="disclosure-2026-08-07",
        covered_tickers=covered,
        outage_tickers=outage,
    )


def _label(calendar, *, events, as_of=None, covered=("PLTR",), outage=(), horizon="h5"):
    row = _row(calendar)
    grade = grader.grade_row(
        row,
        horizon,
        panel=_panel(calendar, {"PLTR": _flat(calendar, 100.0)}),
        calendar=calendar,
        as_of=_as_of(calendar),
    )
    return grader.label_disclosures(
        grade,
        disclosure=_disclosure(events, covered=covered, outage=outage),
        as_of=as_of or _as_of(calendar),
    )


def test_a_disclosure_inside_the_graded_window_is_labelled(calendar):
    """The h5 window is [ENTRY, ENTRY+5]; an earnings print at ENTRY+3 is in it."""
    label = _label(calendar, events=[_event(calendar, _ENTRY_INDEX + 3)])
    assert label.state == "observed"
    assert label.earnings_in_window == 1
    assert label.filings_in_window == 0
    assert [event["reference"] for event in label.events] == ["acc-0001"]


def test_earnings_and_filings_are_counted_separately(calendar):
    label = _label(
        calendar,
        events=[
            _event(calendar, _ENTRY_INDEX + 1, kind="earnings", reference="acc-earn"),
            _event(calendar, _ENTRY_INDEX + 2, kind="filing", reference="acc-10q"),
            _event(calendar, _ENTRY_INDEX + 4, kind="filing", reference="acc-8k"),
        ],
    )
    assert label.state == "observed"
    assert (label.earnings_in_window, label.filings_in_window) == (1, 2)


def test_a_disclosure_after_the_exit_session_is_not_labelled(calendar):
    """Clamp 1 — the window clamp. ENTRY+6 is one session past h5's exit."""
    label = _label(calendar, events=[_event(calendar, _ENTRY_INDEX + 6)])
    assert label.state == "none_in_window"
    assert label.earnings_in_window == 0
    assert label.events == ()


def test_a_disclosure_before_the_entry_session_is_not_labelled(calendar):
    """The window is closed on both ends: a print before entry did not touch it."""
    label = _label(calendar, events=[_event(calendar, _ENTRY_INDEX - 2)])
    assert label.state == "none_in_window"
    assert label.earnings_in_window == 0


def test_widening_the_disclosure_window_by_one_session_changes_the_label(calendar, monkeypatch):
    """MUTATION PROOF that the window clamp above is not vacuous.

    The honest label for a print at ENTRY+6 is ``none_in_window``. Extend the
    one seam that computes the window by a single session and the same fixture
    must flip to ``observed`` — if it did not, the clamp test would be asserting
    nothing about the code.
    """
    events = [_event(calendar, _ENTRY_INDEX + 6)]
    assert _label(calendar, events=events).state == "none_in_window"

    real_window = grader._disclosure_window

    def widened(grade):
        window = real_window(grade)
        if window is None:
            return None
        start, end = window
        return start, calendar.sessions[calendar.index_of(end) + 1]

    with monkeypatch.context() as patched:
        patched.setattr(grader, "_disclosure_window", widened)
        leaked = _label(calendar, events=events)
    assert leaked.state == "observed", "the widened window must reach the post-exit print"
    assert leaked.earnings_in_window == 1


def test_a_disclosure_not_yet_published_is_not_labelled(calendar):
    """Clamp 2 — the availability clamp.

    The print is dated inside the window, but the index that carries it does not
    publish until after ``as_of``. Reading it would be tomorrow's data
    describing a window already graded.
    """
    day = calendar.sessions[_ENTRY_INDEX + 3]
    late = grader.DisclosureEvent(
        kind="earnings",
        ticker="PLTR",
        event_date=day,
        known_at=datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
        reference="acc-late",
    )
    assert _label(calendar, events=[late]).state == "none_in_window"


def test_moving_as_of_past_the_publication_reveals_the_disclosure(calendar):
    """MUTATION PROOF for the availability clamp, by behavior rather than patch.

    Same event, same window, two evaluation points. The label is ``none_in_window``
    before the index publishes and ``observed`` after, so the clamp is doing work.
    """
    day = calendar.sessions[_ENTRY_INDEX + 3]
    published = datetime(2026, 6, 1, tzinfo=timezone.utc)
    event = grader.DisclosureEvent(
        kind="earnings",
        ticker="PLTR",
        event_date=day,
        known_at=published.isoformat(),
        reference="acc-lagged",
    )
    before = _label(calendar, events=[event], as_of=published - timedelta(seconds=1))
    after = _label(calendar, events=[event], as_of=published)
    assert before.state == "none_in_window"
    assert after.state == "observed"


def test_an_uncovered_issuer_is_unavailable_and_never_reads_as_clean(calendar):
    """The whole reason ``covered_tickers`` exists.

    A calendar that carries no PLTR coverage must not answer "no disclosures" —
    that converts missing data into a clean window and flatters the cohort
    exactly where coverage is worst.
    """
    label = _label(calendar, events=[], covered=("XYZ",))
    assert label.state == "unavailable"
    assert label.unavailable_reason == "issuer_not_in_calendar"
    assert label.state != "none_in_window"
    assert label.earnings_in_window is None, "an uncovered issuer has no count, not a zero"


def test_a_source_outage_is_named_separately_from_missing_coverage(calendar):
    label = _label(calendar, events=[], covered=(), outage=("PLTR",))
    assert label.state == "unavailable"
    assert label.unavailable_reason == "source_outage"


def test_with_no_calendar_every_label_is_unavailable(calendar):
    """Today's actual state: no disclosure calendar is wired anywhere."""
    row = _row(calendar)
    grade = grader.grade_row(
        row, "h5", panel=_panel(calendar, {"PLTR": _flat(calendar, 100.0)}),
        calendar=calendar, as_of=_as_of(calendar),
    )
    label = grader.label_disclosures(grade, disclosure=None, as_of=_as_of(calendar))
    assert label.state == "unavailable"
    assert label.unavailable_reason == "no_disclosure_calendar"
    assert (label.earnings_in_window, label.filings_in_window) == (None, None)


def test_an_ungraded_row_is_labelled_not_dropped(calendar):
    """A row with no window keeps its slot in the label census."""
    row = _row(calendar, ticker="NOPX", candidate_id="grc1-000000000000000000000009")
    grade = grader.grade_row(
        row, "h5", panel=_panel(calendar, {"PLTR": _flat(calendar, 100.0)}),
        calendar=calendar, as_of=_as_of(calendar),
    )
    assert grade.state == "ungraded"
    label = grader.label_disclosures(
        grade, disclosure=_disclosure([], covered=("NOPX",)), as_of=_as_of(calendar)
    )
    assert label.state == "unavailable"
    assert label.unavailable_reason == "row_ungraded"


def test_every_unavailable_reason_is_named(calendar, monkeypatch):
    """The vocabulary is closed, and the guard that closes it is live.

    Mutation: drop ``issuer_not_in_calendar`` from the registered vocabulary and
    the path that emits it must RAISE rather than ship an unnamed state. A
    label layer whose reasons are free text is one edit away from
    ``assume_clean``.
    """
    assert set(grader.DISCLOSURE_UNAVAILABLE_REASONS) == {
        "no_disclosure_calendar",
        "issuer_not_in_calendar",
        "row_ungraded",
        "source_outage",
    }
    assert _label(calendar, events=[], covered=("XYZ",)).unavailable_reason == (
        "issuer_not_in_calendar"
    )

    trimmed = tuple(
        reason
        for reason in grader.DISCLOSURE_UNAVAILABLE_REASONS
        if reason != "issuer_not_in_calendar"
    )
    with monkeypatch.context() as patched:
        patched.setattr(grader, "DISCLOSURE_UNAVAILABLE_REASONS", trimmed)
        with pytest.raises(GraderError, match="unnamed disclosure-unavailable reason"):
            _label(calendar, events=[], covered=("XYZ",))


def test_a_calendar_cannot_carry_an_event_for_an_issuer_it_does_not_cover(calendar):
    """Coverage and contents cannot disagree — that disagreement is the bug."""
    with pytest.raises(GraderError, match="does not declare it covered"):
        _disclosure([_event(calendar, _ENTRY_INDEX + 1)], covered=("XYZ",))


def test_a_ticker_cannot_be_both_covered_and_in_outage(calendar):
    with pytest.raises(GraderError, match="both covered and in outage"):
        _disclosure([], covered=("PLTR",), outage=("PLTR",))


def test_a_disclosure_event_refuses_a_datetime_and_an_unknown_kind(calendar):
    with pytest.raises(GraderError, match="must be a date"):
        grader.DisclosureEvent(
            kind="earnings", ticker="PLTR",
            event_date=datetime(2025, 6, 2, tzinfo=timezone.utc),
            known_at="2025-06-01T00:00:00+00:00", reference="acc-1",
        )
    with pytest.raises(GraderError, match="disclosure kind"):
        grader.DisclosureEvent(
            kind="whisper", ticker="PLTR", event_date=date(2025, 6, 2),
            known_at="2025-06-01T00:00:00+00:00", reference="acc-1",
        )


def test_the_label_block_counts_every_row_and_carries_outcome_coverage(calendar):
    """Three states, and they sum to the cohort — no row is silently dropped."""
    log, panel = _mixed_cohort(calendar)
    report = _report(
        calendar, log, panel,
        disclosure=_disclosure(
            [_event(calendar, _ENTRY_INDEX + 3)], covered=("PLTR",),
        ),
    )
    block = report["outcome_by_horizon"]["h5"]["disclosure_labels"]
    issued = report["admission"]["issued"]
    assert sum(block["counts"].values()) == issued
    assert set(block["counts"]) == set(grader.DISCLOSURE_LABEL_STATES)
    # LOSR and NOPX are not covered; the unmatured PLTR row cannot be graded.
    assert block["counts"]["observed"] == 1
    assert block["unavailable_reasons"]["issuer_not_in_calendar"] == 1

    coverage = block["earnings_window_rate"]["coverage"]
    assert coverage["kind"] == "outcome", "a cohort statistic may not cite identity coverage"
    assert coverage["universe"] == issued, "the universe is the FIXED issuance cohort"
    assert coverage["observed"] == block["counts"]["observed"] + block["counts"]["none_in_window"]


def test_disclosure_rates_are_conditioned_on_computable_rows_only(calendar):
    log, panel = _mixed_cohort(calendar)
    report = _report(
        calendar, log, panel,
        disclosure=_disclosure([_event(calendar, _ENTRY_INDEX + 3)], covered=("PLTR",)),
    )
    rate = report["outcome_by_horizon"]["h5"]["disclosure_labels"]["earnings_window_rate"]
    assert rate["denominator"] == report["outcome_by_horizon"]["h5"]["disclosure_labels"]["counts"][
        "observed"
    ] + report["outcome_by_horizon"]["h5"]["disclosure_labels"]["counts"]["none_in_window"]
    assert rate["numerator"] <= rate["denominator"]
    # The walker still passes over the enlarged report.
    grader.assert_rates_carry_coverage(report)


def test_disclosure_labels_cannot_reach_the_verdict(calendar):
    """The structural guarantee, pinned by comparison rather than by comment.

    §7.2 derives N = 545 for the paired market-relative mean. If a label could
    enter the decision rule, the registered N would describe a statistic the
    instrument no longer computes. ``build_cohort_report`` therefore calls
    ``evaluate_verdict`` BEFORE attaching the labels — so a disclosure calendar
    that changes every label must leave the verdict byte-identical.
    """
    log, panel = _mixed_cohort(calendar)
    without = _report(calendar, log, panel)
    with_labels = _report(
        calendar, log, panel,
        disclosure=_disclosure(
            [
                _event(calendar, _ENTRY_INDEX + 1, kind="earnings", reference="acc-a"),
                _event(calendar, _ENTRY_INDEX + 2, kind="filing", reference="acc-b"),
            ],
            covered=("PLTR",),
        ),
    )
    # The labels genuinely differ...
    assert (
        without["outcome_by_horizon"]["h5"]["disclosure_labels"]["counts"]
        != with_labels["outcome_by_horizon"]["h5"]["disclosure_labels"]["counts"]
    )
    # ...and the verdict does not move by one byte.
    assert grader.canonical_bytes(with_labels["verdict"]) == grader.canonical_bytes(
        without["verdict"]
    )
    assert with_labels["verdict_state"] == without["verdict_state"]


def test_the_zero_candidate_state_labels_cleanly(calendar):
    """Zero candidates plus a calendar is an empty label census, not a crash."""
    report = _report(
        calendar,
        _log([]),
        _panel(calendar, {"PLTR": _flat(calendar, 100.0)}),
        disclosure=_disclosure([_event(calendar, _ENTRY_INDEX + 3)]),
    )
    block = report["outcome_by_horizon"]["h63"]["disclosure_labels"]
    assert block["counts"] == {"observed": 0, "none_in_window": 0, "unavailable": 0}
    assert block["labels"] == []
    assert block["earnings_window_rate"]["value"] is None, "an empty census has no rate"
    assert block["filing_window_rate"]["value"] is None
    assert block["earnings_window_rate"]["coverage"]["fraction"] is None


def test_the_registration_registers_the_disclosure_layer_before_observation():
    """§11 exists, is versioned, and the code/document drift guard reads it."""
    text = PREREG_PATH.read_text(encoding="utf-8")
    assert "## 11. Disclosure labels" in text
    for state in grader.DISCLOSURE_LABEL_STATES:
        assert f"`{state}`" in text, f"{state} must be registered, not merely implemented"
    for reason in grader.DISCLOSURE_UNAVAILABLE_REASONS:
        assert f"`{reason}`" in text
    family, _digest = grader.load_family_declaration(PREREG_PATH)
    assert family.version == "3.1.0"
    # Still pre-observation, which is what makes this amendment legal at all.
    live = ROOT / "data" / "government_revenue" / grader.ISSUANCE_LOG_FILENAME
    assert not live.exists() or live.stat().st_size == 0
