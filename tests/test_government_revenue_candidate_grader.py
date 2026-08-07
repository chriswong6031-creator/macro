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


# ---------------------------------------------------------------------------
# GATE 5 — the preregistration exists, is versioned, and declares the kill
# condition before any observation
# ---------------------------------------------------------------------------


def test_preregistration_document_is_committed_and_binds_the_code():
    family, digest = grader.load_family_declaration(PREREG_PATH)
    assert family is GRV_FA1
    assert len(digest) == 64
    assert family.version == "1.0.0"


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
        reason="official source corrected the obligated amount",
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
            reason="attempted identity swap",
            appended_at=_APPENDED_AT,
            changes={"candidate_id": "grc1-000000000000000000000009"},
        )


def test_retraction_keeps_its_slot_in_the_denominator(calendar):
    """You cannot retract your way out of a loss — only into a wider bound."""
    loser = _row(calendar, candidate_id="grc1-000000000000000000000002", ticker="LOSR", event_id="evt-2")
    retraction = grader.build_correction_row(
        loser,
        reason="source receipt binding was withdrawn upstream",
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


def test_every_rate_in_a_live_report_carries_its_coverage(calendar):
    log, panel = _mixed_cohort(calendar)
    report = _report(calendar, log, panel)
    grader.assert_rates_carry_coverage(report)  # must not raise

    found = []

    def walk(node, path="$"):
        if isinstance(node, dict):
            for key, value in node.items():
                if key.endswith("_rate"):
                    found.append(f"{path}.{key}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(report)
    assert found, "the report must actually contain rates for this guard to mean anything"


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
    gate = grader.maturity_gate(rows, family=GRV_FA1, outcome_coverage=coverage)

    assert gate["observed"]["issued"] == 30
    assert gate["observed"]["distinct_source_events"] == 1
    assert gate["observed"]["distinct_issuers"] == 1
    assert gate["observed"]["distinct_event_months"] == 1
    assert gate["satisfied"] is False, (
        "a gate satisfiable by issuance cadence alone gates nothing"
    )
    # The threshold must NAME what it counts. "min_issued" against a distinct-event
    # counter is a column-shifted row waiting to be misread.
    assert gate["required"]["min_distinct_source_events"] == 40
    assert "min_issued" not in gate["required"]


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
