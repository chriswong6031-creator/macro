from __future__ import annotations

import fcntl
import json
import os
import stat
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine import options_nbbo_cohort as cohort
from scripts import capture_options_nbbo_cohort as cli

UTC = timezone.utc
RULE_A = "1" * 64
RULE_B = "2" * 64
TEST_EVENT_SOURCE_SCHEMAS = {
    "mastermindx_prophet": "private.mastermindx-prophet.test/v1",
    "mastermindx_selector": "private.mastermindx-selector.test/v1",
    "momoedge": "private.momoedge-events.test/v1",
}
TEST_CAPTURE_SOURCE_SCHEMAS = {
    "mastermindx": "private.mastermindx-capture.test/v1",
    "momoedge": "private.momoedge-capture.test/v1",
}


@pytest.fixture(autouse=True)
def armed_test_producers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cohort,
        "EVENT_PRODUCER_REGISTRY",
        {
            system: {
                "armed": True,
                "source_schema": source_schema,
                "decision_rule_sha256": RULE_A,
                "lifecycle_rule_sha256": RULE_B,
                "authentication_basis": "test_authenticated_producer_receipt",
            }
            for system, source_schema in TEST_EVENT_SOURCE_SCHEMAS.items()
        },
    )
    monkeypatch.setattr(
        cohort,
        "CAPTURE_PRODUCER_REGISTRY",
        {
            system: {
                "armed": True,
                "source_schema": source_schema,
                "producer_rule_sha256": ("4" if system == "mastermindx" else "5") * 64,
                "authentication_basis": "test_authenticated_producer_receipt",
            }
            for system, source_schema in TEST_CAPTURE_SOURCE_SCHEMAS.items()
        },
    )


def contract() -> dict:
    return {
        "root": "SOFI",
        "expiration": "2026-10-16",
        "right": "call",
        "strike": "16",
        "strike_millis": 16000,
        "occ_symbol": "SOFI  261016C00016000",
    }


def event(
    *,
    kind: str = "enroll",
    event_at: str = "2026-08-12T14:00:00.000000Z",
    available_at: str = "2026-08-12T14:00:01.000000Z",
    enrollment_event_id: str | None = None,
    stable_signal_id: str = "signal:ours:1",
    system: str = "mastermindx_selector",
) -> dict:
    claim = cohort.make_event(
        kind=kind,
        system=system,
        stable_signal_id=stable_signal_id,
        contract=contract(),
        event_at=event_at,
        available_at=available_at,
        decision_rule_sha256=RULE_A,
        lifecycle_rule_sha256=RULE_B,
        private_evidence_schema=cohort.AUTHENTICATED_EVENT_EVIDENCE_SCHEMA,
        private_evidence_sha256="0" * 64,
        private_evidence_bytes=1,
        enrollment_event_id=enrollment_event_id,
    )
    evidence_body = event_evidence_for_event(claim)
    return cohort.make_event(
        kind=claim["kind"],
        system=claim["system"],
        stable_signal_id=claim["stable_signal_id"],
        contract=claim["contract"],
        event_at=claim["event_at"],
        available_at=claim["available_at"],
        decision_rule_sha256=claim["rule_digests"]["decision_rule_sha256"],
        lifecycle_rule_sha256=claim["rule_digests"]["lifecycle_rule_sha256"],
        private_evidence_schema=cohort.AUTHENTICATED_EVENT_EVIDENCE_SCHEMA,
        private_evidence_sha256=sha256(evidence_body).hexdigest(),
        private_evidence_bytes=len(evidence_body),
        enrollment_event_id=claim["enrollment_event_id"],
        terminal_reason=claim["terminal_reason"],
    )


def event_evidence_for_event(row: dict) -> bytes:
    if row["terminal_reason"] == "expiry_liquidation_1555_et":
        expiry = date.fromisoformat(row["contract"]["expiration"])
        last_session = cohort.nyse_calendar.last_session_on_or_before(expiry)
        source_schema = cohort.EXPIRY_EVENT_SOURCE_SCHEMA
        source_payload = {
            "enrollment_event_id": row["enrollment_event_id"],
            "contract": row["contract"],
            "last_tradable_session": last_session.isoformat(),
            "terminal_event_at": row["event_at"],
            "available_at": row["available_at"],
            "rule": "last_nyse_session_on_or_before_occ_expiration_at_1555_et/v1",
        }
    else:
        source_schema = TEST_EVENT_SOURCE_SCHEMAS[row["system"]]
        source_payload = {
            "kind": row["kind"],
            "system": row["system"],
            "stable_signal_id": row["stable_signal_id"],
            "event_at": row["event_at"],
            "available_at": row["available_at"],
            "contract": row["contract"],
        }
    return cohort.build_event_evidence_bytes(
        event=row,
        source_schema=source_schema,
        source_payload=source_payload,
    )


def quote_row(
    *,
    timestamp: str = "2026-08-12T10:00:00.010",
    bid: float = 2.1,
    ask: float = 2.2,
    bid_size: int = 11,
    ask_size: int = 12,
    bid_exchange: int = 4,
    ask_exchange: int = 11,
    bid_condition: int = 50,
    ask_condition: int = 50,
) -> dict:
    return {
        "timestamp": timestamp,
        "bid_size": bid_size,
        "ask_size": ask_size,
        "bid_exchange": bid_exchange,
        "ask_exchange": ask_exchange,
        "bid_condition": bid_condition,
        "ask_condition": ask_condition,
        "bid": bid,
        "ask": ask,
    }


def response(*rows: dict) -> list[dict]:
    return [
        {
            "symbol": "SOFI",
            "expiration": "2026-10-16",
            "right": "call",
            "strike": 16.0,
            **row,
        }
        for row in rows
    ]


def fetched_response(*rows: dict) -> cohort.FetchedQuoteResponse:
    payload = response(*rows)
    return cohort.FetchedQuoteResponse(
        payload=payload,
        raw_body=cohort.canonical_json_bytes(payload),
    )


def build_observation(**kwargs: Any) -> dict:
    payload = kwargs.get("source_payload")
    if payload is not None and "source_response_body" not in kwargs:
        kwargs["source_response_body"] = cohort.canonical_json_bytes(payload)
    if (
        payload is not None or kwargs.get("source_error") is not None
    ) and "request_started_at" not in kwargs:
        kwargs["request_started_at"] = kwargs["available_at"]
    return cohort.build_observation(**kwargs)


def private_root(tmp_path: Path) -> Path:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def producer_input(root: Path, name: str, body: bytes) -> Path:
    inbox = root / "inbox"
    inbox.mkdir(mode=0o700, exist_ok=True)
    inbox.chmod(0o700)
    path = inbox / name
    path.write_bytes(body)
    path.chmod(0o600)
    return path


def event_ledger(tmp_path: Path, *events: dict) -> Path:
    root = private_root(tmp_path)
    path = root / "events.jsonl"
    path.write_bytes(b"".join(cohort.canonical_event_line(row) for row in events))
    path.chmod(0o600)
    captures = root / "captures.jsonl"
    captures.write_bytes(b"")
    captures.chmod(0o600)
    for row in events:
        evidence_body = event_evidence_for_event(row)
        cohort.write_private_evidence(
            root,
            namespace="event_evidence",
            raw_body=evidence_body,
            receipt=row["private_evidence"],
        )
    return path


def full_capture_receipts(enrolled: dict) -> list[dict]:
    opened, closed = cohort._session_window(date(2026, 8, 12))
    rows: list[dict] = []
    slot = opened
    while slot < closed:
        for system in ("mastermindx", "momoedge"):
            observes_event = system == "mastermindx" and slot == datetime(
                2026, 8, 12, 14, 0, tzinfo=UTC
            )
            disposition = (
                "new_calls_observed" if observes_event else "no_new_calls_observed"
            )
            event_ids = [enrolled["event_id"]] if observes_event else []
            producer_digest = ("4" if system == "mastermindx" else "5") * 64
            completed = (
                slot + timedelta(seconds=2)
                if observes_event
                else slot.replace(microsecond=1)
            )
            source_payload = {
                "comparison_system": system,
                "scheduled_at": cohort.utc_text(slot),
                "attempted_at": cohort.utc_text(slot),
                "completed_at": cohort.utc_text(completed),
                "capture_event_at": cohort.utc_text(completed),
                "disposition": disposition,
                "observed_new_call_count": 1 if observes_event else 0,
                "new_enrollment_event_ids": event_ids,
                "producer_rule_sha256": producer_digest,
            }
            evidence_body = cohort.build_capture_evidence_bytes(
                comparison_system=system,
                scheduled_at=cohort.utc_text(slot),
                attempted_at=cohort.utc_text(slot),
                completed_at=cohort.utc_text(completed),
                capture_event_at=cohort.utc_text(completed),
                disposition=disposition,
                reason=None,
                evidence_authenticated=True,
                observed_new_call_count=1 if observes_event else 0,
                new_enrollment_event_ids=event_ids,
                producer_rule_sha256=producer_digest,
                source_schema=TEST_CAPTURE_SOURCE_SCHEMAS[system],
                source_payload=source_payload,
            )
            rows.append(
                cohort.make_capture_receipt(
                    comparison_system=system,
                    scheduled_at=cohort.utc_text(slot),
                    attempted_at=cohort.utc_text(slot),
                    completed_at=cohort.utc_text(completed),
                    capture_event_at=cohort.utc_text(completed),
                    disposition=disposition,
                    observed_new_call_count=1 if observes_event else 0,
                    new_enrollment_event_ids=(event_ids),
                    producer_rule_sha256=producer_digest,
                    evidence_authenticated=True,
                    private_evidence_schema=cohort.AUTHENTICATED_CAPTURE_EVIDENCE_SCHEMA,
                    private_evidence_sha256=sha256(evidence_body).hexdigest(),
                    private_evidence_bytes=len(evidence_body),
                )
            )
        slot += timedelta(seconds=cohort.CAPTURE_CADENCE_SECONDS)
    return rows


def install_capture_receipts(root: Path, receipts: list[dict]) -> None:
    (root / "captures.jsonl").write_bytes(
        b"".join(cohort.canonical_json_bytes(row) for row in receipts)
    )
    (root / "captures.jsonl").chmod(0o600)
    for receipt in receipts:
        evidence_body = capture_evidence_for_receipt(receipt)
        assert (
            sha256(evidence_body).hexdigest()
            == receipt["private_evidence"]["object_sha256"]
        )
        cohort.write_private_evidence(
            root,
            namespace="capture_evidence",
            raw_body=evidence_body,
            receipt=receipt["private_evidence"],
        )


def capture_evidence_for_receipt(receipt: dict) -> bytes:
    source_payload = {
        "comparison_system": receipt["comparison_system"],
        "scheduled_at": receipt["scheduled_at"],
        "attempted_at": receipt["attempted_at"],
        "completed_at": receipt["completed_at"],
        "capture_event_at": receipt["capture_event_at"],
        "disposition": receipt["disposition"],
        "observed_new_call_count": receipt["observed_new_call_count"],
        "new_enrollment_event_ids": receipt["new_enrollment_event_ids"],
        "producer_rule_sha256": receipt["producer_rule_sha256"],
    }
    return cohort.build_capture_evidence_bytes(
        comparison_system=receipt["comparison_system"],
        scheduled_at=receipt["scheduled_at"],
        attempted_at=receipt["attempted_at"],
        completed_at=receipt["completed_at"],
        capture_event_at=receipt["capture_event_at"],
        disposition=receipt["disposition"],
        reason=receipt["reason"],
        evidence_authenticated=receipt["evidence_authenticated"],
        observed_new_call_count=receipt["observed_new_call_count"],
        new_enrollment_event_ids=receipt["new_enrollment_event_ids"],
        producer_rule_sha256=receipt["producer_rule_sha256"],
        source_schema=TEST_CAPTURE_SOURCE_SCHEMAS[receipt["comparison_system"]],
        source_payload=source_payload,
    )


def test_schema_is_draft_2020_12_and_real_instances_validate() -> None:
    schema = json.loads(cohort.SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert list(validator.iter_errors(event())) == []
    observation = build_observation(
        role="entry",
        event=event(),
        available_at=datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
        source_payload=response(quote_row()),
    )
    assert list(validator.iter_errors(observation)) == []


def test_exact_occ_contract_and_content_identity_fail_closed() -> None:
    row = event()
    assert cohort.validate_event(row) == row
    bad = json.loads(json.dumps(row))
    bad["contract"]["occ_symbol"] = "SOFI  261016P00016000"
    with pytest.raises(cohort.NbboCohortError, match="OCC symbol"):
        cohort.validate_event(bad)
    bad = json.loads(json.dumps(row))
    bad["stable_signal_id"] = "signal:ours:changed"
    with pytest.raises(cohort.NbboCohortError, match="content identity"):
        cohort.validate_event(bad)


def test_event_requires_false_authority_and_exact_benchmark() -> None:
    row = event()
    row["authority"]["may_select"] = True
    with pytest.raises(cohort.NbboCohortError, match="all-false"):
        cohort.validate_event(row)
    row = event()
    row["benchmark_digest_sha256"] = "0" * 64
    with pytest.raises(cohort.NbboCohortError, match="benchmark"):
        cohort.validate_event(row)


def test_terminal_must_reference_prior_exact_enrollment() -> None:
    enrolled = event()
    terminal = event(
        kind="terminal",
        event_at="2026-08-12T19:55:00.000000Z",
        available_at="2026-08-12T19:55:01.000000Z",
        enrollment_event_id=enrolled["event_id"],
    )
    enrollments, terminals = cohort.reconcile_events([enrolled, terminal])
    assert enrollments == [enrolled]
    assert terminals[enrolled["event_id"]] == terminal
    with pytest.raises(cohort.NbboCohortError, match="missing or later"):
        cohort.reconcile_events([terminal, enrolled])


def test_event_ledger_is_canonical_bounded_and_duplicate_idempotent(
    tmp_path: Path,
) -> None:
    enrolled = event()
    path = event_ledger(tmp_path, enrolled, enrolled)
    rows, receipt = cohort.read_event_ledger(path)
    assert rows == [enrolled]
    assert receipt["row_count"] == 1
    assert receipt["sha256"] == sha256(path.read_bytes()).hexdigest()
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    with pytest.raises(cohort.NbboCohortError, match="final line"):
        cohort.read_event_ledger(path)


def test_quote_parser_selects_first_valid_at_or_after_boundary() -> None:
    payload = response(
        quote_row(timestamp="2026-08-12T09:59:59.990", bid=1.9, ask=2.0),
        quote_row(timestamp="2026-08-12T10:00:00.020", bid=2.1, ask=2.2),
        quote_row(timestamp="2026-08-12T10:00:00.010", bid=2.0, ask=2.1),
    )
    selected = cohort.parse_quote_response(
        payload,
        role="entry",
        contract=contract(),
        boundary_at=datetime(2026, 8, 12, 14, 0, tzinfo=UTC),
    )
    assert selected is not None
    assert cohort.utc_text(selected.event_at) == "2026-08-12T14:00:00.010000Z"
    assert selected.ask == cohort.Decimal("2.1")


def test_quote_parser_rejects_conflicting_same_clock_and_crossed_quotes() -> None:
    conflicting = response(
        quote_row(bid=2.0, ask=2.1),
        quote_row(bid=2.0, ask=2.2),
    )
    with pytest.raises(cohort.NbboSourceError, match="conflicting"):
        cohort.parse_quote_response(
            conflicting,
            role="entry",
            contract=contract(),
            boundary_at=datetime(2026, 8, 12, 14, 0, tzinfo=UTC),
        )
    crossed = response(quote_row(bid=2.2, ask=2.1))
    assert (
        cohort.parse_quote_response(
            crossed,
            role="entry",
            contract=contract(),
            boundary_at=datetime(2026, 8, 12, 14, 0, tzinfo=UTC),
        )
        is None
    )


def test_quote_parser_requires_official_flat_tick_rows() -> None:
    assert cohort.SOURCE_INTERVAL == "tick"
    with pytest.raises(cohort.NbboSourceError, match="flat JSON array"):
        cohort.parse_quote_response(
            {"response": []},
            role="entry",
            contract=contract(),
            boundary_at=datetime(2026, 8, 12, 14, 0, tzinfo=UTC),
        )
    wrong_contract = response(quote_row())
    wrong_contract[0]["strike"] = 17.0
    with pytest.raises(cohort.NbboSourceError, match="different exact contract"):
        cohort.parse_quote_response(
            wrong_contract,
            role="entry",
            contract=contract(),
            boundary_at=datetime(2026, 8, 12, 14, 0, tzinfo=UTC),
        )


def test_quote_selection_is_role_side_firm_and_known_exchange() -> None:
    invalid_then_valid = response(
        quote_row(timestamp="2026-08-12T10:00:00.010", ask_condition=17),
        quote_row(timestamp="2026-08-12T10:00:00.020", ask_condition=21),
        quote_row(timestamp="2026-08-12T10:00:00.030", ask_condition=61),
        quote_row(timestamp="2026-08-12T10:00:00.040", ask_exchange=74),
        quote_row(timestamp="2026-08-12T10:00:00.050", ask_condition=50),
    )
    selected = cohort.parse_quote_response(
        invalid_then_valid,
        role="entry",
        contract=contract(),
        boundary_at=datetime(2026, 8, 12, 14, 0, tzinfo=UTC),
    )
    assert selected is not None
    assert cohort.utc_text(selected.event_at) == "2026-08-12T14:00:00.050000Z"

    ask_only = response(
        quote_row(
            bid=0,
            bid_size=0,
            bid_exchange=0,
            bid_condition=21,
            ask=2.2,
            ask_size=12,
            ask_exchange=11,
            ask_condition=50,
        )
    )
    entry = build_observation(
        role="entry",
        event=event(),
        available_at=datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
        source_payload=ask_only,
    )
    assert entry["status"] == "admitted"
    assert entry["quote"]["selected_price"] == "2.2"
    for field, value in (("ask_condition", 21), ("ask_exchange", 74)):
        forged = json.loads(json.dumps(entry))
        forged["quote"][field] = value
        forged["observation_id"] = cohort._content_id(
            "nbboobs_", forged, "observation_id"
        )
        with pytest.raises(cohort.NbboCohortError, match="not valid firm NBBO"):
            cohort.validate_observation(forged)

    enrolled = event()
    terminal = event(
        kind="terminal",
        event_at="2026-08-12T14:05:00.000000Z",
        available_at="2026-08-12T14:05:01.000000Z",
        enrollment_event_id=enrolled["event_id"],
    )
    bid_only = response(
        quote_row(
            timestamp="2026-08-12T10:05:00.010",
            bid=2.5,
            bid_size=11,
            bid_exchange=4,
            bid_condition=50,
            ask=0,
            ask_size=0,
            ask_exchange=0,
            ask_condition=21,
        )
    )
    exit_row = build_observation(
        role="exit",
        event=terminal,
        available_at=datetime(2026, 8, 12, 14, 5, 5, tzinfo=UTC),
        source_payload=bid_only,
    )
    assert exit_row["status"] == "admitted"
    assert exit_row["quote"]["selected_price"] == "2.5"


def test_query_is_exact_contract_rth_and_unaggregated_tick_source() -> None:
    query = cohort.source_query(
        contract=contract(),
        boundary_at=datetime(2026, 8, 12, 14, 0, 0, 123000, tzinfo=UTC),
        available_at=datetime(2026, 8, 12, 14, 5, tzinfo=UTC),
    )
    assert query == {
        "symbol": "SOFI",
        "expiration": "20261016",
        "strike": "16.000",
        "right": "call",
        "date": "20260812",
        "start_time": "10:00:00.123",
        "end_time": "10:05:00.000",
        "interval": "tick",
        "format": "json",
    }
    with pytest.raises(cohort.NbboCohortError, match="outside NYSE RTH"):
        cohort.source_query(
            contract=contract(),
            boundary_at=datetime(2026, 8, 12, 13, 29, 59, tzinfo=UTC),
            available_at=datetime(2026, 8, 12, 13, 30, tzinfo=UTC),
        )


def test_observation_uses_ask_for_entry_bid_for_exit_and_600s_fence() -> None:
    enrolled = event()
    now = datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC)
    entry = build_observation(
        role="entry",
        event=enrolled,
        available_at=now,
        source_payload=response(quote_row()),
    )
    assert entry["status"] == "admitted"
    assert entry["quote"]["selected_side"] == "ask"
    assert entry["quote"]["selected_price"] == "2.2"
    terminal = event(
        kind="terminal",
        event_at="2026-08-12T14:05:00.000000Z",
        available_at="2026-08-12T14:05:01.000000Z",
        enrollment_event_id=enrolled["event_id"],
    )
    exit_row = build_observation(
        role="exit",
        event=terminal,
        available_at=datetime(2026, 8, 12, 14, 5, 5, tzinfo=UTC),
        source_payload=response(
            quote_row(timestamp="2026-08-12T10:05:00.010", bid=2.5, ask=2.6)
        ),
    )
    assert exit_row["quote"]["selected_side"] == "bid"
    assert exit_row["quote"]["selected_price"] == "2.5"
    missed = build_observation(
        role="entry",
        event=enrolled,
        available_at=datetime(2026, 8, 12, 14, 10, 1, tzinfo=UTC),
        source_payload=response(quote_row()),
    )
    assert missed["status"] == "unavailable"
    assert missed["reason"] == "FIRST_QUOTE_AVAILABLE_TOO_LATE"


def test_return_is_exact_frozen_one_contract_fee_formula() -> None:
    result = cohort.net_return_pct("2.2", "2.5")
    expected = (
        (
            (cohort.Decimal(100) * cohort.Decimal("2.5") - cohort.Decimal("0.65"))
            - (cohort.Decimal(100) * cohort.Decimal("2.2") + cohort.Decimal("0.65"))
        )
        / (cohort.Decimal(100) * cohort.Decimal("2.2") + cohort.Decimal("0.65"))
        * cohort.Decimal(100)
    ).quantize(cohort.Decimal("0.000001"))
    assert result == expected


def test_private_store_is_0700_0600_content_addressed(tmp_path: Path) -> None:
    root = private_root(tmp_path)
    observation = build_observation(
        role="entry",
        event=event(),
        available_at=datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
        source_payload=response(quote_row()),
    )
    cohort.write_source_response(
        root, cohort.canonical_json_bytes(response(quote_row()))
    )
    path = cohort.write_immutable(root, observation)
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert cohort.write_immutable(root, observation) == path
    assert cohort.read_observations(root) == [observation]
    path.chmod(0o644)
    with pytest.raises(cohort.NbboCohortError, match="0600"):
        cohort.read_observations(root)


def test_snapshot_head_survives_short_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = private_root(tmp_path)
    snapshot = cohort.build_snapshot(
        events=[],
        event_receipt={
            "sha256": sha256(b"").hexdigest(),
            "bytes": 0,
            "row_count": 0,
        },
        observations=[],
        built_at=datetime(2026, 8, 12, 20, 0, tzinfo=UTC),
    )
    real_write = cohort.os.write

    def short_write(fd: int, body) -> int:
        return real_write(fd, body[:7])

    monkeypatch.setattr(cohort.os, "write", short_write)
    _snapshot_path, head_path = cohort.write_snapshot(root, snapshot)
    head = json.loads(head_path.read_text())
    assert head["snapshot_id"] == snapshot["snapshot_id"]


def test_end_to_end_advance_entry_then_terminal_exit(tmp_path: Path) -> None:
    enrolled = event()
    ledger = event_ledger(tmp_path, enrolled)
    root = ledger.parent
    queries: list[dict[str, str]] = []

    def entry_fetch(query: dict[str, str]) -> cohort.FetchedQuoteResponse:
        queries.append(query)
        return fetched_response(quote_row())

    first = cohort.advance(
        event_ledger=ledger,
        private_root=root,
        fetch_quote=entry_fetch,
        now=datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
        clock=lambda: datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
    )
    assert first["coverage"]["enrollment_count"] == 1
    assert first["coverage"]["complete_outcome_count"] == 0
    assert first["coverage"]["session_coverage"]["covered_session_count"] == 0
    assert len(queries) == 1
    terminal = event(
        kind="terminal",
        event_at="2026-08-12T14:05:00.000000Z",
        available_at="2026-08-12T14:05:01.000000Z",
        enrollment_event_id=enrolled["event_id"],
    )
    ledger.write_bytes(
        cohort.canonical_event_line(enrolled) + cohort.canonical_event_line(terminal)
    )
    ledger.chmod(0o600)
    terminal_evidence = event_evidence_for_event(terminal)
    cohort.write_private_evidence(
        root,
        namespace="event_evidence",
        raw_body=terminal_evidence,
        receipt=terminal["private_evidence"],
    )

    def exit_fetch(_: dict[str, str]) -> cohort.FetchedQuoteResponse:
        return fetched_response(
            quote_row(timestamp="2026-08-12T10:05:00.010", bid=2.5, ask=2.6)
        )

    second = cohort.advance(
        event_ledger=ledger,
        private_root=root,
        fetch_quote=exit_fetch,
        now=datetime(2026, 8, 12, 14, 5, 5, tzinfo=UTC),
        clock=lambda: datetime(2026, 8, 12, 14, 5, 5, tzinfo=UTC),
    )
    assert second["coverage"]["complete_outcome_count"] == 0
    assert second["coverage"]["quote_complete_outcome_count"] == 1
    install_capture_receipts(root, full_capture_receipts(enrolled))
    third = cohort.advance(
        event_ledger=ledger,
        private_root=root,
        fetch_quote=lambda _: pytest.fail("completed outcome must not refetch"),
        now=datetime(2026, 8, 12, 20, 0, tzinfo=UTC),
    )
    assert third["coverage"]["complete_outcome_count"] == 1
    assert third["coverage"]["session_coverage"]["covered_session_count"] == 1
    head = json.loads((root / "HEAD.json").read_text())
    assert head["coverage"] == third["coverage"]
    snapshot_path = root / "snapshots" / f"{head['snapshot_id']}.json"
    snapshot = json.loads(snapshot_path.read_text())
    assert snapshot["rows"][0]["complete"] is True
    assert snapshot["rows"][0]["net_return_pct"] is not None
    assert snapshot["authority"] == cohort.FALSE_AUTHORITY


def test_cli_initializes_and_appends_idempotently(tmp_path: Path) -> None:
    root = tmp_path / "private"
    ledger = cli.initialize(root)
    assert ledger.read_bytes() == b""
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(ledger.stat().st_mode) == 0o600
    row = event()
    event_path = producer_input(root, "event.json", cohort.canonical_json_bytes(row))
    evidence_path = producer_input(root, "evidence.json", event_evidence_for_event(row))
    first = cli.append_event(ledger, event_path, evidence_path)
    second = cli.append_event(ledger, event_path, evidence_path)
    assert first == second
    rows, receipt = cohort.read_event_ledger(ledger)
    assert len(rows) == 1
    assert receipt["row_count"] == 1


def test_producer_inputs_must_be_private_owned_unlinked_and_inside_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    ledger = cli.initialize(root)
    row = event()
    evidence = producer_input(
        root, "valid-evidence.json", event_evidence_for_event(row)
    )

    outside = tmp_path / "outside-event.json"
    outside.write_bytes(cohort.canonical_json_bytes(row))
    outside.chmod(0o600)
    with pytest.raises(cohort.NbboCohortError, match="inside the private root"):
        cli.append_event(ledger, outside, evidence)

    world_readable = producer_input(
        root, "world-event.json", cohort.canonical_json_bytes(row)
    )
    world_readable.chmod(0o644)
    with pytest.raises(cohort.NbboCohortError, match="private 0600"):
        cli.append_event(ledger, world_readable, evidence)

    valid_event = producer_input(
        root, "valid-event.json", cohort.canonical_json_bytes(row)
    )
    hardlinked_evidence = root / "inbox" / "hardlinked-evidence.json"
    os.link(evidence, hardlinked_evidence)
    with pytest.raises(cohort.NbboCohortError, match="private 0600"):
        cli.append_event(ledger, valid_event, hardlinked_evidence)

    evidence.unlink()
    symlink_evidence = root / "inbox" / "symlink-evidence.json"
    symlink_evidence.symlink_to(valid_event)
    with pytest.raises(cohort.NbboCohortError, match="non-symlink"):
        cli.append_event(ledger, valid_event, symlink_evidence)
    assert ledger.read_bytes() == b""


def test_runtime_cutoff_exposes_a_wholly_silent_missed_session(tmp_path: Path) -> None:
    enrolled = event()
    ledger = event_ledger(tmp_path, enrolled)
    root = ledger.parent
    install_capture_receipts(root, full_capture_receipts(enrolled))

    result = cohort.advance(
        event_ledger=ledger,
        private_root=root,
        fetch_quote=lambda _: pytest.fail("closed entry window must not refetch"),
        now=datetime(2026, 8, 13, 20, 0, tzinfo=UTC),
    )
    session_coverage = result["coverage"]["session_coverage"]
    assert session_coverage["eligible_finalized_session_count"] == 2
    assert session_coverage["covered_session_count"] == 1
    assert session_coverage["excluded_finalized_session_count"] == 1
    assert [row["session_date"] for row in session_coverage["sessions"]] == [
        "2026-08-12",
        "2026-08-13",
    ]
    missed = session_coverage["sessions"][1]
    assert missed["common_successful_slot_count"] == 0
    assert "NO_COMMON_AUTHENTICATED_CAPTURE" in missed["exclusion_reasons"]


def test_source_url_is_local_only() -> None:
    cli.fetch_quote_factory("http://127.0.0.1:25503", timeout_seconds=5)
    with pytest.raises(cohort.NbboCohortError, match="local v3 terminal"):
        cli.fetch_quote_factory("https://example.com", timeout_seconds=5)


def test_theta_fetcher_disables_and_refuses_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = response(quote_row())

    class RedirectedResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self) -> str:
            return "https://unexpected.example/quote"

        def read(self, _maximum: int) -> bytes:
            return cohort.canonical_json_bytes(payload)

    class FakeOpener:
        def open(self, _url: str, *, timeout: int):
            assert timeout == 5
            return RedirectedResponse()

    def fake_build_opener(handler):
        assert isinstance(handler, cli._NoRedirectHandler)
        assert handler.redirect_request(None, None, 302, "", {}, "https://x") is None
        return FakeOpener()

    monkeypatch.setattr(cli, "build_opener", fake_build_opener)
    fetch = cli.fetch_quote_factory("http://127.0.0.1:25503", timeout_seconds=5)
    query = cohort.source_query(
        contract=contract(),
        boundary_at=datetime(2026, 8, 12, 14, 0, tzinfo=UTC),
        available_at=datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
    )
    with pytest.raises(cohort.NbboSourceError, match="redirected"):
        fetch(query)


def test_prospective_freeze_and_rule_receipts_are_immutable() -> None:
    with pytest.raises(cohort.NbboCohortError, match="pre-freeze"):
        event(
            event_at="2026-08-11T15:47:05.999999Z",
            available_at="2026-08-11T15:47:05.999999Z",
        )
    first = event()
    with pytest.raises(cohort.NbboCohortError, match="decision rule digest"):
        cohort.make_event(
            kind="enroll",
            system="mastermindx_selector",
            stable_signal_id="signal:ours:2",
            contract=contract(),
            event_at="2026-08-12T14:01:00.000000Z",
            available_at="2026-08-12T14:01:01.000000Z",
            decision_rule_sha256="4" * 64,
            lifecycle_rule_sha256=RULE_B,
            private_evidence_schema=cohort.AUTHENTICATED_EVENT_EVIDENCE_SCHEMA,
            private_evidence_sha256="0" * 64,
            private_evidence_bytes=1,
        )
    changed_quote_rule = json.loads(json.dumps(first))
    changed_quote_rule["rule_digests"]["quote_rule_sha256"] = "0" * 64
    changed_quote_rule["event_id"] = cohort._event_content_id(changed_quote_rule)
    with pytest.raises(cohort.NbboCohortError, match="quote rule digest"):
        cohort.validate_event(changed_quote_rule)


def test_terminal_clocks_and_rules_must_follow_enrollment() -> None:
    enrolled = event(available_at="2026-08-12T14:00:10.000000Z")
    early_available = event(
        kind="terminal",
        event_at="2026-08-12T14:00:05.000000Z",
        available_at="2026-08-12T14:00:05.000000Z",
        enrollment_event_id=enrolled["event_id"],
    )
    with pytest.raises(cohort.NbboCohortError, match="availability predates"):
        cohort.reconcile_events([enrolled, early_available])
    with pytest.raises(cohort.NbboCohortError, match="decision rule digest"):
        cohort.make_event(
            kind="terminal",
            system=enrolled["system"],
            stable_signal_id=enrolled["stable_signal_id"],
            contract=enrolled["contract"],
            event_at="2026-08-12T14:05:00.000000Z",
            available_at="2026-08-12T14:05:01.000000Z",
            decision_rule_sha256="4" * 64,
            lifecycle_rule_sha256=RULE_B,
            private_evidence_schema=cohort.AUTHENTICATED_EVENT_EVIDENCE_SCHEMA,
            private_evidence_sha256="0" * 64,
            private_evidence_bytes=1,
            enrollment_event_id=enrolled["event_id"],
        )


def test_exact_raw_response_and_post_fetch_clock_are_durable(tmp_path: Path) -> None:
    enrolled = event()
    ledger = event_ledger(tmp_path, enrolled)
    root = ledger.parent
    payload = response(quote_row(timestamp="2026-08-12T10:00:04.000", bid=2.1, ask=2.2))
    raw = json.dumps(payload, indent=2, sort_keys=False).encode("utf-8")
    times = iter(
        [
            datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
            datetime(2026, 8, 12, 14, 0, 7, tzinfo=UTC),
        ]
    )

    def fetch(query: dict[str, str]) -> cohort.FetchedQuoteResponse:
        assert query["end_time"] == "10:00:05.000"
        return cohort.FetchedQuoteResponse(payload=payload, raw_body=raw)

    result = cohort.advance(
        event_ledger=ledger,
        private_root=root,
        fetch_quote=fetch,
        now=datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
        clock=lambda: next(times),
    )
    assert result["new_observation_count"] == 1
    observation = cohort.read_observations(root)[0]
    assert observation["source"]["requested_at"] == "2026-08-12T14:00:05.000000Z"
    assert observation["observed_at"] == "2026-08-12T14:00:07.000000Z"
    receipt = observation["source"]["response"]
    stored = root / "source_responses" / f"{receipt['sha256']}.json"
    assert stored.read_bytes() == raw
    assert receipt == {"sha256": sha256(raw).hexdigest(), "bytes": len(raw)}


def test_attempted_quote_requires_exact_raw_bytes_and_request_clock(
    tmp_path: Path,
) -> None:
    enrolled = event()
    payload = response(quote_row())
    observed_at = datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC)
    with pytest.raises(cohort.NbboSourceError, match="exact source response bytes"):
        cohort.build_observation(
            role="entry",
            event=enrolled,
            available_at=observed_at,
            request_started_at=observed_at,
            source_payload=payload,
        )
    with pytest.raises(cohort.NbboCohortError, match="request_started_at"):
        cohort.build_observation(
            role="entry",
            event=enrolled,
            available_at=observed_at,
            source_payload=payload,
            source_response_body=cohort.canonical_json_bytes(payload),
        )

    ledger = event_ledger(tmp_path, enrolled)
    root = ledger.parent
    with pytest.raises(cohort.NbboCohortError, match="runtime clock callback"):
        cohort.advance(
            event_ledger=ledger,
            private_root=root,
            fetch_quote=lambda _: pytest.fail("clock fence must precede fetch"),
            now=observed_at,
        )
    with pytest.raises(cohort.NbboCohortError, match="exact FetchedQuoteResponse"):
        cohort.advance(
            event_ledger=ledger,
            private_root=root,
            fetch_quote=lambda _: payload,
            now=observed_at,
            clock=lambda: observed_at,
        )
    source_dir = root / "source_responses"
    assert not source_dir.exists()


def test_quote_after_exact_query_end_is_refused() -> None:
    with pytest.raises(cohort.NbboSourceError, match="after the exact query end"):
        cohort.parse_quote_response(
            response(quote_row(timestamp="2026-08-12T10:00:00.020")),
            role="entry",
            contract=contract(),
            boundary_at=datetime(2026, 8, 12, 14, 0, tzinfo=UTC),
            query_end_at=datetime(2026, 8, 12, 14, 0, 0, 15_000, tzinfo=UTC),
        )


def test_first_quote_may_arrive_late_but_its_availability_must_be_prompt() -> None:
    admitted = build_observation(
        role="entry",
        event=event(),
        request_started_at=datetime(2026, 8, 12, 15, 0, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 12, 15, 0, 2, tzinfo=UTC),
        source_payload=response(
            quote_row(timestamp="2026-08-12T10:59:59.000", bid=2.1, ask=2.2)
        ),
    )
    assert admitted["status"] == "admitted"
    assert admitted["quote"]["event_to_available_lag_seconds"] == 3.0
    too_late = build_observation(
        role="entry",
        event=event(),
        request_started_at=datetime(2026, 8, 12, 15, 0, 1, tzinfo=UTC),
        available_at=datetime(2026, 8, 12, 15, 0, 2, tzinfo=UTC),
        source_payload=response(quote_row()),
    )
    assert too_late["status"] == "unavailable"
    assert too_late["reason"] == "FIRST_QUOTE_AVAILABLE_TOO_LATE"


def test_event_availability_gates_request_without_moving_quote_boundary(
    tmp_path: Path,
) -> None:
    enrolled = event(available_at="2026-08-12T14:00:05.000000Z")
    ledger = event_ledger(tmp_path, enrolled)
    root = ledger.parent
    called = False

    def fetch(_: dict[str, str]) -> cohort.FetchedQuoteResponse:
        nonlocal called
        called = True
        return fetched_response(quote_row())

    with pytest.raises(cohort.NbboCohortError, match="future clock"):
        cohort.advance(
            event_ledger=ledger,
            private_root=root,
            fetch_quote=fetch,
            now=datetime(2026, 8, 12, 14, 0, 4, tzinfo=UTC),
        )
    assert called is False
    after = cohort.advance(
        event_ledger=ledger,
        private_root=root,
        fetch_quote=fetch,
        now=datetime(2026, 8, 12, 14, 0, 6, tzinfo=UTC),
        clock=lambda: datetime(2026, 8, 12, 14, 0, 6, tzinfo=UTC),
    )
    assert called is True
    assert after["new_observation_count"] == 1
    observation = cohort.read_observations(root)[0]
    assert observation["boundary_at"] == enrolled["event_at"]


def test_advance_rejects_retained_observation_from_the_future(tmp_path: Path) -> None:
    enrolled = event()
    ledger = event_ledger(tmp_path, enrolled)
    root = ledger.parent
    payload = response(quote_row())
    body = cohort.canonical_json_bytes(payload)
    cohort.write_source_response(root, body)
    observation = build_observation(
        role="entry",
        event=enrolled,
        request_started_at=datetime(2026, 8, 12, 14, 0, 9, tzinfo=UTC),
        available_at=datetime(2026, 8, 12, 14, 0, 10, tzinfo=UTC),
        source_payload=payload,
        source_response_body=body,
    )
    cohort.write_immutable(root, observation)
    with pytest.raises(cohort.NbboCohortError, match="future observation"):
        cohort.advance(
            event_ledger=ledger,
            private_root=root,
            fetch_quote=lambda _: pytest.fail("future state must fail before fetch"),
            now=datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
        )


def test_transient_source_failures_retry_without_object_bloat(tmp_path: Path) -> None:
    enrolled = event()
    ledger = event_ledger(tmp_path, enrolled)
    root = ledger.parent

    def unavailable(_: dict[str, str]) -> dict:
        raise TimeoutError("private source timed out")

    failed = cohort.advance(
        event_ledger=ledger,
        private_root=root,
        fetch_quote=unavailable,
        now=datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
        clock=lambda: datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
    )
    assert failed["new_observation_count"] == 0
    assert failed["transient_failure_count"] == 1
    assert cohort.read_observations(root) == []
    recovered = cohort.advance(
        event_ledger=ledger,
        private_root=root,
        fetch_quote=lambda _: fetched_response(quote_row()),
        now=datetime(2026, 8, 12, 14, 0, 10, tzinfo=UTC),
        clock=lambda: datetime(2026, 8, 12, 14, 0, 10, tzinfo=UTC),
    )
    assert recovered["new_observation_count"] == 1
    assert len(cohort.read_observations(root)) == 1


def test_closed_quote_window_is_terminal_and_idempotent(tmp_path: Path) -> None:
    enrolled = event()
    ledger = event_ledger(tmp_path, enrolled)
    root = ledger.parent

    def must_not_fetch(_: dict[str, str]) -> dict:
        raise AssertionError("closed window must not hit provider")

    first = cohort.advance(
        event_ledger=ledger,
        private_root=root,
        fetch_quote=must_not_fetch,
        now=datetime(2026, 8, 12, 20, 10, 1, tzinfo=UTC),
    )
    assert first["new_observation_count"] == 1
    assert cohort.read_observations(root)[0]["reason"] == "QUOTE_WINDOW_CLOSED"
    second = cohort.advance(
        event_ledger=ledger,
        private_root=root,
        fetch_quote=must_not_fetch,
        now=datetime(2026, 8, 12, 21, 0, tzinfo=UTC),
    )
    assert second["new_observation_count"] == 0
    assert second["snapshot_id"] == first["snapshot_id"]
    assert len(cohort.read_observations(root)) == 1


def test_concurrent_advance_is_refused(tmp_path: Path) -> None:
    enrolled = event()
    ledger = event_ledger(tmp_path, enrolled)
    root = ledger.parent
    lock_fd = cohort._acquire_advance_lock(root)
    try:
        with pytest.raises(cohort.NbboCohortError, match="already running"):
            cohort.advance(
                event_ledger=ledger,
                private_root=root,
                fetch_quote=lambda _: fetched_response(quote_row()),
                now=datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
            )
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def test_observation_is_bound_to_exact_event_and_selected_side() -> None:
    enrolled = event()
    observation = build_observation(
        role="entry",
        event=enrolled,
        available_at=datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
        source_payload=response(quote_row()),
    )
    bad_price = json.loads(json.dumps(observation))
    bad_price["quote"]["selected_price"] = "2.1"
    bad_price["observation_id"] = cohort._content_id(
        "nbboobs_", bad_price, "observation_id"
    )
    with pytest.raises(cohort.NbboCohortError, match="selected price"):
        cohort.validate_observation(bad_price)
    bad_pointer = json.loads(json.dumps(observation))
    bad_pointer["event"]["sha256"] = "0" * 64
    bad_pointer["observation_id"] = cohort._content_id(
        "nbboobs_", bad_pointer, "observation_id"
    )
    cohort.validate_observation(bad_pointer)
    with pytest.raises(cohort.NbboCohortError, match="does not bind"):
        cohort.build_snapshot(
            events=[enrolled],
            event_receipt={
                "sha256": "0" * 64,
                "bytes": len(cohort.canonical_event_line(enrolled)),
                "row_count": 1,
            },
            observations=[bad_pointer],
            built_at=datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
        )


def test_entry_after_terminal_never_becomes_a_return() -> None:
    enrolled = event()
    terminal = event(
        kind="terminal",
        event_at="2026-08-12T14:03:00.000000Z",
        available_at="2026-08-12T14:03:01.000000Z",
        enrollment_event_id=enrolled["event_id"],
    )
    entry = build_observation(
        role="entry",
        event=enrolled,
        available_at=datetime(2026, 8, 12, 14, 5, 5, tzinfo=UTC),
        source_payload=response(
            quote_row(timestamp="2026-08-12T10:05:00.000", bid=2.1, ask=2.2)
        ),
    )
    exit_row = build_observation(
        role="exit",
        event=terminal,
        available_at=datetime(2026, 8, 12, 14, 4, 5, tzinfo=UTC),
        source_payload=response(
            quote_row(timestamp="2026-08-12T10:04:00.000", bid=2.5, ask=2.6)
        ),
    )
    snapshot = cohort.build_snapshot(
        events=[enrolled, terminal],
        event_receipt={"sha256": "0" * 64, "bytes": 1, "row_count": 2},
        observations=[entry, exit_row],
        built_at=datetime(2026, 8, 12, 14, 5, 5, tzinfo=UTC),
    )
    assert snapshot["rows"][0]["completion_reason"] == "ENTRY_AFTER_TERMINAL"
    assert snapshot["rows"][0]["net_return_pct"] is None
    assert snapshot["coverage"]["complete_outcome_count"] == 0


def test_private_source_tamper_is_detected(tmp_path: Path) -> None:
    enrolled = event()
    ledger = event_ledger(tmp_path, enrolled)
    root = ledger.parent
    cohort.advance(
        event_ledger=ledger,
        private_root=root,
        fetch_quote=lambda _: fetched_response(quote_row()),
        now=datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
        clock=lambda: datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
    )
    observation = cohort.read_observations(root)[0]
    receipt = observation["source"]["response"]
    path = root / "source_responses" / f"{receipt['sha256']}.json"
    path.write_bytes(path.read_bytes() + b" ")
    path.chmod(0o600)
    with pytest.raises(cohort.NbboCohortError, match="does not match private bytes"):
        cohort.read_observations(root)


def test_invalid_terminal_append_never_mutates_private_ledger(tmp_path: Path) -> None:
    root = tmp_path / "private"
    ledger = cli.initialize(root)
    terminal = event(
        kind="terminal",
        event_at="2026-08-12T14:05:00.000000Z",
        available_at="2026-08-12T14:05:01.000000Z",
        enrollment_event_id="nbboevt_" + "0" * 64,
    )
    event_path = producer_input(
        root, "terminal.json", cohort.canonical_json_bytes(terminal)
    )
    evidence_path = producer_input(
        root, "evidence.json", event_evidence_for_event(terminal)
    )
    with pytest.raises(cohort.NbboCohortError, match="missing or later"):
        cli.append_event(ledger, event_path, evidence_path)
    assert ledger.read_bytes() == b""


def test_production_cli_has_no_backdated_clock_flag() -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(["--advance", "--now", "2026-08-12T14:00:00.000000Z"])


def test_production_producer_registries_are_unarmed_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cohort, "EVENT_PRODUCER_REGISTRY", cohort.DEFAULT_EVENT_PRODUCER_REGISTRY
    )
    monkeypatch.setattr(
        cohort, "CAPTURE_PRODUCER_REGISTRY", cohort.DEFAULT_CAPTURE_PRODUCER_REGISTRY
    )
    assert all(
        registration["armed"] is False
        for registration in cohort.EVENT_PRODUCER_REGISTRY.values()
    )
    assert all(
        registration["armed"] is False
        for registration in cohort.CAPTURE_PRODUCER_REGISTRY.values()
    )
    with pytest.raises(cohort.NbboCohortError, match="event producer is not armed"):
        cohort.make_event(
            kind="enroll",
            system="mastermindx_selector",
            stable_signal_id="signal:blocked:1",
            contract=contract(),
            event_at="2026-08-12T14:00:00.000000Z",
            available_at="2026-08-12T14:00:01.000000Z",
            decision_rule_sha256=RULE_A,
            lifecycle_rule_sha256=RULE_B,
            private_evidence_schema=cohort.AUTHENTICATED_EVENT_EVIDENCE_SCHEMA,
            private_evidence_sha256="0" * 64,
            private_evidence_bytes=1,
        )
    with pytest.raises(cohort.NbboCohortError, match="capture producer is not armed"):
        cohort.make_capture_receipt(
            comparison_system="mastermindx",
            scheduled_at="2026-08-12T14:00:00.000000Z",
            attempted_at="2026-08-12T14:00:01.000000Z",
            completed_at="2026-08-12T14:00:02.000000Z",
            capture_event_at="2026-08-12T14:00:01.000000Z",
            disposition="no_new_calls_observed",
            producer_rule_sha256="4" * 64,
            evidence_authenticated=True,
            private_evidence_schema=cohort.AUTHENTICATED_CAPTURE_EVIDENCE_SCHEMA,
            private_evidence_sha256="0" * 64,
            private_evidence_bytes=1,
        )


def test_event_evidence_replay_binds_id_clocks_rules_and_source() -> None:
    first = event()
    evidence_body = event_evidence_for_event(first)
    evidence_payload = cohort.strict_json_object(evidence_body, label="event evidence")
    cohort.validate_event_evidence_binding(evidence_payload, first)

    second = event(
        event_at="2026-08-12T14:01:00.000000Z",
        available_at="2026-08-12T14:01:01.000000Z",
        stable_signal_id="signal:ours:2",
    )
    with pytest.raises(cohort.NbboCohortError, match="does not bind"):
        cohort.validate_event_evidence_binding(evidence_payload, second)

    forged = json.loads(json.dumps(evidence_payload))
    forged["source"]["schema"] = "private.attacker/v1"
    forged_source = cohort.canonical_json_bytes(forged["source"]["payload"])
    forged["source"]["payload_sha256"] = sha256(forged_source).hexdigest()
    forged["source"]["payload_bytes"] = len(forged_source)
    with pytest.raises(cohort.NbboCohortError, match="not preregistered"):
        cohort.validate_event_evidence_binding(forged, first)


def test_capture_receipt_schema_and_zero_call_semantics_are_exact() -> None:
    evidence_body = cohort.build_capture_evidence_bytes(
        comparison_system="momoedge",
        scheduled_at="2026-08-12T14:00:00.000000Z",
        attempted_at="2026-08-12T14:00:01.000000Z",
        completed_at="2026-08-12T14:00:02.000000Z",
        capture_event_at="2026-08-12T14:00:01.000000Z",
        disposition="no_new_calls_observed",
        reason=None,
        evidence_authenticated=True,
        observed_new_call_count=0,
        new_enrollment_event_ids=(),
        producer_rule_sha256="5" * 64,
        source_schema=TEST_CAPTURE_SOURCE_SCHEMAS["momoedge"],
        source_payload={
            "comparison_system": "momoedge",
            "scheduled_at": "2026-08-12T14:00:00.000000Z",
            "attempted_at": "2026-08-12T14:00:01.000000Z",
            "completed_at": "2026-08-12T14:00:02.000000Z",
            "capture_event_at": "2026-08-12T14:00:01.000000Z",
            "disposition": "no_new_calls_observed",
            "observed_new_call_count": 0,
            "new_enrollment_event_ids": [],
            "producer_rule_sha256": "5" * 64,
        },
    )
    receipt = cohort.make_capture_receipt(
        comparison_system="momoedge",
        scheduled_at="2026-08-12T14:00:00.000000Z",
        attempted_at="2026-08-12T14:00:01.000000Z",
        completed_at="2026-08-12T14:00:02.000000Z",
        capture_event_at="2026-08-12T14:00:01.000000Z",
        disposition="no_new_calls_observed",
        producer_rule_sha256="5" * 64,
        evidence_authenticated=True,
        private_evidence_schema=cohort.AUTHENTICATED_CAPTURE_EVIDENCE_SCHEMA,
        private_evidence_sha256=sha256(evidence_body).hexdigest(),
        private_evidence_bytes=len(evidence_body),
    )
    schema = json.loads(cohort.SCHEMA_PATH.read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(receipt)
    assert receipt["authority"] == cohort.FALSE_AUTHORITY
    bad = json.loads(json.dumps(receipt))
    bad["disposition"] = "selector_abstained"
    bad["capture_receipt_id"] = cohort._capture_content_id(bad)
    with pytest.raises(cohort.NbboCohortError, match="cannot infer"):
        cohort.validate_capture_receipt(bad)

    reused = cohort.make_capture_receipt(
        comparison_system="momoedge",
        scheduled_at="2026-08-12T14:05:00.000000Z",
        attempted_at="2026-08-12T14:05:01.000000Z",
        completed_at="2026-08-12T14:05:02.000000Z",
        capture_event_at="2026-08-12T14:05:01.000000Z",
        disposition="no_new_calls_observed",
        producer_rule_sha256="5" * 64,
        evidence_authenticated=True,
        private_evidence_schema=cohort.AUTHENTICATED_CAPTURE_EVIDENCE_SCHEMA,
        private_evidence_sha256=sha256(evidence_body).hexdigest(),
        private_evidence_bytes=len(evidence_body),
    )
    with pytest.raises(cohort.NbboCohortError, match="does not bind"):
        cohort.validate_capture_evidence_binding(
            cohort.strict_json_object(evidence_body, label="capture evidence"),
            reused,
        )


def test_capture_gap_uses_actual_response_completion_not_scheduled_slot() -> None:
    def captured(system: str, scheduled: datetime, completed: datetime) -> dict:
        scheduled_text = cohort.utc_text(scheduled)
        completed_text = cohort.utc_text(completed)
        source = {
            "comparison_system": system,
            "scheduled_at": scheduled_text,
            "attempted_at": scheduled_text,
            "completed_at": completed_text,
            "capture_event_at": completed_text,
            "disposition": "no_new_calls_observed",
            "observed_new_call_count": 0,
            "new_enrollment_event_ids": [],
            "producer_rule_sha256": ("4" if system == "mastermindx" else "5") * 64,
        }
        evidence = cohort.build_capture_evidence_bytes(
            comparison_system=system,
            scheduled_at=scheduled_text,
            attempted_at=scheduled_text,
            completed_at=completed_text,
            capture_event_at=completed_text,
            disposition="no_new_calls_observed",
            reason=None,
            evidence_authenticated=True,
            observed_new_call_count=0,
            new_enrollment_event_ids=(),
            producer_rule_sha256=("4" if system == "mastermindx" else "5") * 64,
            source_schema=TEST_CAPTURE_SOURCE_SCHEMAS[system],
            source_payload=source,
        )
        return cohort.make_capture_receipt(
            comparison_system=system,
            scheduled_at=scheduled_text,
            attempted_at=scheduled_text,
            completed_at=completed_text,
            capture_event_at=completed_text,
            disposition="no_new_calls_observed",
            producer_rule_sha256=("4" if system == "mastermindx" else "5") * 64,
            evidence_authenticated=True,
            private_evidence_schema=cohort.AUTHENTICATED_CAPTURE_EVIDENCE_SCHEMA,
            private_evidence_sha256=sha256(evidence).hexdigest(),
            private_evidence_bytes=len(evidence),
        )

    receipts = []
    opened, closed = cohort._session_window(date(2026, 8, 12))
    for system in ("mastermindx", "momoedge"):
        slot = opened
        while slot < closed:
            if slot not in {
                datetime(2026, 8, 12, 13, 35, tzinfo=UTC),
                datetime(2026, 8, 12, 13, 40, tzinfo=UTC),
            }:
                completed = (
                    datetime(2026, 8, 12, 13, 49, 59, tzinfo=UTC)
                    if slot == datetime(2026, 8, 12, 13, 45, tzinfo=UTC)
                    else slot
                )
                receipts.append(captured(system, slot, completed))
            slot += timedelta(seconds=cohort.CAPTURE_CADENCE_SECONDS)
    coverage, _covered, _silent = cohort.build_session_coverage(
        capture_receipts=receipts,
        events=[],
        built_at=datetime(2026, 8, 12, 20, 0, tzinfo=UTC),
    )
    session = coverage["sessions"][0]
    assert session["by_system"]["mastermindx"]["maximum_capture_gap_seconds"] == 1199
    assert session["common_maximum_capture_gap_seconds"] == 1199
    assert "COMMON_CAPTURE_GAP_OVER_900_SECONDS" in session["exclusion_reasons"]


def test_common_capture_coverage_requires_ratio_gap_and_event_reconciliation() -> None:
    enrolled = event()
    receipts = full_capture_receipts(enrolled)
    coverage, covered, silent = cohort.build_session_coverage(
        capture_receipts=receipts,
        events=[enrolled],
        built_at=datetime(2026, 8, 12, 20, 0, tzinfo=UTC),
    )
    assert covered == {"2026-08-12"}
    assert silent == 0
    session = coverage["sessions"][0]
    assert session["common_capture_coverage_ratio"] == "1.000000"
    assert session["common_maximum_capture_gap_seconds"] == 302

    # Remove three consecutive MomoEdge slots. Coverage remains above 95%, but
    # the 1,200-second authenticated gap excludes the session from both systems.
    removed = {
        "2026-08-12T18:05:00.000000Z",
        "2026-08-12T18:10:00.000000Z",
        "2026-08-12T18:15:00.000000Z",
    }
    gapped = [
        row
        for row in receipts
        if not (
            row["comparison_system"] == "momoedge" and row["scheduled_at"] in removed
        )
    ]
    coverage, covered, _silent = cohort.build_session_coverage(
        capture_receipts=gapped,
        events=[enrolled],
        built_at=datetime(2026, 8, 12, 20, 0, tzinfo=UTC),
    )
    assert covered == set()
    session = coverage["sessions"][0]
    assert cohort.Decimal(session["common_capture_coverage_ratio"]) >= cohort.Decimal(
        "0.95"
    )
    assert session["common_maximum_capture_gap_seconds"] == 1200
    assert "COMMON_CAPTURE_GAP_OVER_900_SECONDS" in session["exclusion_reasons"]

    unreconciled = [
        row
        for row in receipts
        if enrolled["event_id"] not in row["new_enrollment_event_ids"]
    ]
    coverage, covered, silent = cohort.build_session_coverage(
        capture_receipts=unreconciled,
        events=[enrolled],
        built_at=datetime(2026, 8, 12, 20, 0, tzinfo=UTC),
    )
    assert covered == set()
    assert silent == 1
    assert (
        "EVENT_RECONCILIATION_INCOMPLETE"
        in coverage["sessions"][0]["exclusion_reasons"]
    )


def test_capture_reconciliation_rejects_backfilled_future_event_claim() -> None:
    enrolled = event(available_at="2026-08-12T19:00:00.000000Z")
    receipts = full_capture_receipts(enrolled)
    coverage, covered, silent = cohort.build_session_coverage(
        capture_receipts=receipts,
        events=[enrolled],
        built_at=datetime(2026, 8, 12, 20, 0, tzinfo=UTC),
    )
    assert covered == set()
    assert silent == 1
    session = coverage["sessions"][0]
    assert session["event_reconciliation"]["invalid_enrollment_reference_count"] == 1
    assert "EVENT_RECONCILIATION_INCOMPLETE" in session["exclusion_reasons"]


def test_capture_gap_boundary_uses_exact_microseconds() -> None:
    opened = datetime(2026, 8, 12, 13, 30, tzinfo=UTC)
    closed = opened + timedelta(seconds=1800)
    assert (
        cohort._maximum_capture_gap(
            [opened + timedelta(seconds=900)], opened=opened, closed=closed
        )
        == 900
    )
    assert (
        cohort._maximum_capture_gap(
            [opened + timedelta(seconds=900, microseconds=1)],
            opened=opened,
            closed=closed,
        )
        == 901
    )


def test_empty_safe_cycle_is_private_and_never_counts_as_abstention(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    cli.initialize(root)
    times = iter(
        [
            datetime(2026, 8, 12, 14, 0, 5, tzinfo=UTC),
            datetime(2026, 8, 12, 14, 0, 6, tzinfo=UTC),
        ]
    )
    ids = cli.record_unavailable_cycle(
        root / "captures.jsonl", private_root=root, clock=lambda: next(times)
    )
    assert len(ids) == 2
    rows, _receipt = cohort.read_capture_ledger(root / "captures.jsonl")
    assert {row["comparison_system"] for row in rows} == {
        "mastermindx",
        "momoedge",
    }
    assert {row["disposition"] for row in rows} == {"unavailable"}
    assert all(row["evidence_authenticated"] is False for row in rows)
    for row in rows:
        evidence_path = (
            root
            / "capture_evidence"
            / f"{row['private_evidence']['object_sha256']}.json"
        )
        assert stat.S_IMODE(evidence_path.stat().st_mode) == 0o600
    coverage, covered, _silent = cohort.build_session_coverage(
        capture_receipts=rows,
        events=[],
        built_at=datetime(2026, 8, 12, 20, 0, tzinfo=UTC),
    )
    assert covered == set()
    assert (
        coverage["sessions"][0]["by_system"]["mastermindx"]["zero_new_call_slot_count"]
        == 0
    )


def test_capture_evidence_tamper_and_future_receipt_fail_closed(
    tmp_path: Path,
) -> None:
    enrolled = event()
    ledger = event_ledger(tmp_path, enrolled)
    root = ledger.parent
    receipt = full_capture_receipts(enrolled)[0]
    install_capture_receipts(root, [receipt])
    evidence_path = (
        root
        / "capture_evidence"
        / f"{receipt['private_evidence']['object_sha256']}.json"
    )
    evidence_path.write_bytes(evidence_path.read_bytes() + b" ")
    evidence_path.chmod(0o600)
    with pytest.raises(cohort.NbboCohortError, match="does not match bytes"):
        cohort.verify_capture_evidence(root, [receipt])

    # Restore exact evidence, then prove the runtime cannot ingest future rows.
    evidence_path.write_bytes(capture_evidence_for_receipt(receipt))
    evidence_path.chmod(0o600)
    with pytest.raises(cohort.NbboCohortError, match="future receipt"):
        cohort.advance(
            event_ledger=ledger,
            private_root=root,
            fetch_quote=lambda _: fetched_response(quote_row()),
            now=datetime(2026, 8, 12, 13, 29, tzinfo=UTC),
        )


def test_expiry_terminal_is_exact_1555_and_never_backdates_availability() -> None:
    enrolled = event()
    assert (
        cohort.expiry_terminal_candidates(
            [enrolled],
            available_at=datetime(2026, 10, 16, 19, 54, 59, tzinfo=UTC),
        )
        == []
    )
    candidates = cohort.expiry_terminal_candidates(
        [enrolled],
        available_at=datetime(2026, 10, 19, 14, 0, tzinfo=UTC),
    )
    terminal, evidence_body = candidates[0]
    assert terminal["event_at"] == "2026-10-16T19:55:00.000000Z"
    assert terminal["available_at"] == "2026-10-19T14:00:00.000000Z"
    assert terminal["terminal_reason"] == "expiry_liquidation_1555_et"
    assert (
        sha256(evidence_body).hexdigest()
        == terminal["private_evidence"]["object_sha256"]
    )
    wrong = json.loads(json.dumps(terminal))
    wrong["event_at"] = "2026-10-16T19:54:59.000000Z"
    wrong["event_id"] = cohort._event_content_id(wrong)
    with pytest.raises(cohort.NbboCohortError, match="exactly 15:55"):
        cohort.validate_event(wrong)


def test_enrollment_after_expiry_liquidation_boundary_is_rejected() -> None:
    exact_boundary = event(
        event_at="2026-10-16T19:55:00.000000Z",
        available_at="2026-10-16T19:55:00.000000Z",
        stable_signal_id="signal:expiry-edge",
    )
    assert exact_boundary["event_at"] == "2026-10-16T19:55:00.000000Z"
    with pytest.raises(cohort.NbboCohortError, match="frozen expiry liquidation"):
        event(
            event_at="2026-10-16T19:56:00.000000Z",
            available_at="2026-10-16T19:56:00.000000Z",
            stable_signal_id="signal:expiry-poison",
        )


def test_early_close_quotes_after_actual_rth_are_rejected() -> None:
    # 2026-11-27 is the recurring Friday-after-Thanksgiving 13:00 ET close.
    with pytest.raises(cohort.NbboCohortError, match="outside NYSE RTH"):
        cohort.source_query(
            contract=contract(),
            boundary_at=datetime(2026, 11, 27, 18, 1, tzinfo=UTC),
            available_at=datetime(2026, 11, 27, 18, 2, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("event_at", "available_at", "now"),
    (
        (
            "2026-08-15T14:00:00.000000Z",
            "2026-08-15T14:00:01.000000Z",
            datetime(2026, 8, 15, 14, 0, 5, tzinfo=UTC),
        ),
        (
            "2026-08-12T13:00:00.000000Z",
            "2026-08-12T13:00:01.000000Z",
            datetime(2026, 8, 12, 13, 0, 5, tzinfo=UTC),
        ),
        (
            "2026-08-12T20:01:00.000000Z",
            "2026-08-12T20:01:01.000000Z",
            datetime(2026, 8, 12, 20, 1, 5, tzinfo=UTC),
        ),
    ),
)
def test_outside_rth_events_close_without_poisoning_advance(
    tmp_path: Path,
    event_at: str,
    available_at: str,
    now: datetime,
) -> None:
    enrolled = event(
        event_at=event_at,
        available_at=available_at,
        stable_signal_id=f"signal:outside-rth:{event_at}",
    )
    ledger = event_ledger(tmp_path, enrolled)
    result = cohort.advance(
        event_ledger=ledger,
        private_root=ledger.parent,
        fetch_quote=lambda _: pytest.fail("outside-RTH event must not fetch"),
        now=now,
    )
    assert result["new_observation_count"] == 1
    observation = cohort.read_observations(ledger.parent)[0]
    assert observation["status"] == "unavailable"
    assert observation["reason"] == "BOUNDARY_OUTSIDE_RTH"


@pytest.mark.parametrize(
    ("event_at", "available_at"),
    (
        (
            "2026-08-12T13:00:00.000000Z",
            "2026-08-12T13:00:01.000000Z",
        ),
        (
            "2026-08-12T20:01:00.000000Z",
            "2026-08-12T20:01:01.000000Z",
        ),
    ),
)
def test_outside_rth_enrollments_do_not_poison_rth_capture_coverage(
    event_at: str,
    available_at: str,
) -> None:
    in_scope = event()
    outside = event(
        event_at=event_at,
        available_at=available_at,
        stable_signal_id=f"signal:coverage-outside-rth:{event_at}",
    )
    coverage, covered, _silent_drops = cohort.build_session_coverage(
        capture_receipts=full_capture_receipts(in_scope),
        events=[in_scope, outside],
        built_at=datetime(2026, 8, 12, 21, 0, tzinfo=UTC),
    )
    assert covered == {"2026-08-12"}
    session = coverage["sessions"][0]
    assert session["event_reconciliation"] == {
        "missing_enrollment_reference_count": 0,
        "duplicate_enrollment_reference_count": 0,
        "invalid_enrollment_reference_count": 0,
    }


def test_atomic_event_append_survives_replace_failure_and_concurrency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "private"
    ledger = cli.initialize(root)
    first = event()
    first_evidence_path = producer_input(
        root, "first-evidence.json", event_evidence_for_event(first)
    )
    first_path = producer_input(root, "first.json", cohort.canonical_json_bytes(first))
    cli.append_event(ledger, first_path, first_evidence_path)
    original = ledger.read_bytes()

    second = event(
        event_at="2026-08-12T14:01:00.000000Z",
        available_at="2026-08-12T14:01:01.000000Z",
        stable_signal_id="signal:ours:2",
    )
    second_evidence_path = producer_input(
        root, "second-evidence.json", event_evidence_for_event(second)
    )
    second_path = producer_input(
        root, "second.json", cohort.canonical_json_bytes(second)
    )
    real_replace = cli.os.replace
    monkeypatch.setattr(
        cli.os,
        "replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("fault")),
    )
    with pytest.raises(OSError, match="fault"):
        cli.append_event(ledger, second_path, second_evidence_path)
    assert ledger.read_bytes() == original
    monkeypatch.setattr(cli.os, "replace", real_replace)

    third = event(
        event_at="2026-08-12T14:02:00.000000Z",
        available_at="2026-08-12T14:02:01.000000Z",
        stable_signal_id="signal:ours:3",
    )
    third_evidence_path = producer_input(
        root, "third-evidence.json", event_evidence_for_event(third)
    )
    third_path = producer_input(root, "third.json", cohort.canonical_json_bytes(third))
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(cli.append_event, ledger, event_path, evidence_path)
            for event_path, evidence_path in (
                (second_path, second_evidence_path),
                (third_path, third_evidence_path),
            )
        ]
        assert {future.result() for future in futures} == {
            second["event_id"],
            third["event_id"],
        }
    rows, receipt = cohort.read_event_ledger(ledger)
    assert receipt["row_count"] == 3
    assert {row["event_id"] for row in rows} == {
        first["event_id"],
        second["event_id"],
        third["event_id"],
    }


def test_private_store_lock_prevents_cross_writer_staging_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    root = private_root(tmp_path)
    first_at_link = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_reconciled = threading.Event()
    role = threading.local()
    call_lock = threading.Lock()
    first_link = True
    real_link = cohort.os.link
    real_reconcile = cohort._reconcile_staging

    def blocking_link(*args, **kwargs):
        nonlocal first_link
        with call_lock:
            should_block = first_link
            first_link = False
        if should_block:
            first_at_link.set()
            assert release_first.wait(2)
        return real_link(*args, **kwargs)

    def observed_reconcile(store_root: Path) -> Path:
        if getattr(role, "name", None) == "second":
            second_reconciled.set()
        return real_reconcile(store_root)

    def write(name: str, body: bytes) -> dict:
        role.name = name
        if name == "second":
            second_started.set()
        return cohort.write_source_response(root, body)

    monkeypatch.setattr(cohort.os, "link", blocking_link)
    monkeypatch.setattr(cohort, "_reconcile_staging", observed_reconcile)
    first_body = cohort.canonical_json_bytes(response(quote_row()))
    second_body = cohort.canonical_json_bytes(
        response(quote_row(timestamp="2026-08-12T10:00:00.020"))
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(write, "first", first_body)
        assert first_at_link.wait(2)
        second_future = pool.submit(write, "second", second_body)
        assert second_started.wait(2)
        assert second_reconciled.wait(0.2) is False
        release_first.set()
        first_receipt = first_future.result(timeout=2)
        second_receipt = second_future.result(timeout=2)
    for receipt in (first_receipt, second_receipt):
        path = root / "source_responses" / f"{receipt['sha256']}.json"
        assert path.is_file()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
