#!/usr/bin/env python3
"""Advance the host-private same-basis prospective OPRA NBBO cohort.

The only network call is ThetaData Terminal's localhost v3 option-history quote
endpoint.  The CLI never publishes raw quotes or cohort rows.  An external
producer appends already-selected exact-contract enrollment/terminal events to
the private event ledger; this process only accrues entry/exit evidence.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import stat
import sys
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import options_nbbo_cohort as cohort

DEFAULT_PRIVATE_ROOT = Path.home() / ".mastermind_private" / "options_nbbo_cohort_v1"
DEFAULT_THETA_BASE_URL = "http://127.0.0.1:25503"


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        return None


def _private_file(path: Path, *, create: bool) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise cohort.NbboCohortError("private event ledger must be absolute")
    if expanded.is_symlink():
        raise cohort.NbboCohortError("private event ledger cannot be a symlink")
    resolved = expanded.resolve()
    repo = ROOT.resolve()
    if resolved == repo or repo in resolved.parents:
        raise cohort.NbboCohortError("private event ledger cannot be inside repository")
    parent = cohort._validate_private_dir(resolved.parent, create=create)
    if create and not resolved.exists():
        fd = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        parent_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    if resolved.exists():
        info = resolved.lstat()
        if (
            resolved.is_symlink()
            or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
        ):
            raise cohort.NbboCohortError("private event ledger must be owned 0600")
    return resolved


def initialize(private_root: Path) -> Path:
    root = private_root.expanduser().resolve()
    repo = ROOT.resolve()
    if root == repo or repo in root.parents:
        raise cohort.NbboCohortError("private root cannot be inside repository")
    cohort._validate_private_dir(root, create=True)
    events = _private_file(root / "events.jsonl", create=True)
    _private_file(root / "captures.jsonl", create=True)
    return events


def _private_producer_input(
    path: Path, *, private_root: Path, label: str, maximum: int
) -> bytes:
    """Read one producer input only from the owned 0700 private tree."""

    root = cohort._validate_private_dir(
        private_root.expanduser().resolve(), create=False
    )
    expanded = path.expanduser()
    if not expanded.is_absolute() or expanded.is_symlink():
        raise cohort.NbboCohortError(f"{label} must be an absolute non-symlink path")
    resolved = expanded.resolve()
    if root not in resolved.parents:
        raise cohort.NbboCohortError(f"{label} must be inside the private root")
    cursor = resolved.parent
    while True:
        cohort._validate_owned_private_directory(cursor, label=f"{label} parent")
        if cursor == root:
            break
        if root not in cursor.parents:
            raise cohort.NbboCohortError(f"{label} escapes the private root")
        cursor = cursor.parent
    return cohort._validate_private_file(resolved, label=label, maximum=maximum)


def _atomic_rewrite(path: Path, body: bytes) -> None:
    """Durably replace a private ledger without exposing a partial final row."""

    path = _private_file(path, create=True)
    temp = path.parent / f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temp, flags, 0o600)
    try:
        view = memoryview(body)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise cohort.NbboCohortError("short write to private ledger staging")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(temp, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if temp.exists():
            temp.unlink()


def _append_canonical_row(
    *,
    ledger: Path,
    lock_name: str,
    row: Mapping[str, Any],
    validate_row: Callable[[Any], dict[str, Any]],
    read_ledger: Callable[[Path], tuple[list[dict[str, Any]], dict[str, Any]]],
    id_field: str,
    max_rows: int,
    max_bytes: int,
    reconcile: Callable[[list[dict[str, Any]]], Any] | None = None,
) -> str:
    ledger = _private_file(ledger, create=True)
    lock_path = _private_file(ledger.parent / lock_name, create=True)
    line = cohort.canonical_json_bytes(validate_row(row))
    with lock_path.open("r+b", buffering=0) as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        rows, _receipt = read_ledger(ledger)
        existing = ledger.read_bytes()
        row_id = row[id_field]
        for prior in rows:
            if prior[id_field] == row_id:
                if prior != row:
                    raise cohort.NbboCohortError("conflicting duplicate private row")
                return row_id
        candidate = [*rows, dict(row)]
        if len(candidate) > max_rows:
            raise cohort.NbboCohortError("private ledger exceeds row cap")
        if len(existing) + len(line) > max_bytes:
            raise cohort.NbboCohortError("private ledger exceeds byte cap")
        if reconcile is not None:
            reconcile(candidate)
        _atomic_rewrite(ledger, existing + line)
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    read_ledger(ledger)
    return row_id


def append_event(
    event_ledger: Path,
    event_path: Path,
    evidence_path: Path,
    *,
    private_root: Path | None = None,
) -> str:
    root = (private_root or event_ledger.parent).expanduser().resolve()
    raw_event = _private_producer_input(
        event_path,
        private_root=root,
        label="append event",
        maximum=2 * 1024 * 1024,
    )
    event = cohort.validate_event(
        cohort.strict_json_object(raw_event, label="append event")
    )
    evidence_body = _private_producer_input(
        evidence_path,
        private_root=root,
        label="append event evidence",
        maximum=cohort.MAX_RESPONSE_BYTES,
    )
    evidence_payload = cohort.strict_json_object(
        evidence_body, label="append event evidence"
    )
    cohort.validate_event_evidence_binding(evidence_payload, event)
    cohort.write_private_evidence(
        root,
        namespace="event_evidence",
        raw_body=evidence_body,
        receipt=event["private_evidence"],
    )
    event_id = _append_canonical_row(
        ledger=event_ledger,
        lock_name=".events.lock",
        row=event,
        validate_row=cohort.validate_event,
        read_ledger=cohort.read_event_ledger,
        id_field="event_id",
        max_rows=cohort.MAX_EVENTS,
        max_bytes=cohort.MAX_EVENT_BYTES,
        reconcile=cohort.reconcile_events,
    )
    cohort.verify_event_evidence(root, cohort.read_event_ledger(event_ledger)[0])
    return event_id


def append_capture_receipt(
    capture_ledger: Path,
    receipt_path: Path,
    evidence_path: Path,
    *,
    private_root: Path | None = None,
) -> str:
    root = (private_root or capture_ledger.parent).expanduser().resolve()
    raw_receipt = _private_producer_input(
        receipt_path,
        private_root=root,
        label="append capture receipt",
        maximum=2 * 1024 * 1024,
    )
    receipt = cohort.validate_capture_receipt(
        cohort.strict_json_object(raw_receipt, label="append capture receipt")
    )
    evidence_body = _private_producer_input(
        evidence_path,
        private_root=root,
        label="append capture evidence",
        maximum=cohort.MAX_RESPONSE_BYTES,
    )
    evidence_payload = cohort.strict_json_object(
        evidence_body, label="append capture evidence"
    )
    cohort.validate_capture_evidence_binding(evidence_payload, receipt)
    cohort.write_private_evidence(
        root,
        namespace="capture_evidence",
        raw_body=evidence_body,
        receipt=receipt["private_evidence"],
    )
    cohort.verify_capture_evidence(root, [receipt])
    receipt_id = _append_canonical_row(
        ledger=capture_ledger,
        lock_name=".captures.lock",
        row=receipt,
        validate_row=cohort.validate_capture_receipt,
        read_ledger=cohort.read_capture_ledger,
        id_field="capture_receipt_id",
        max_rows=cohort.MAX_CAPTURE_RECEIPTS,
        max_bytes=cohort.MAX_CAPTURE_BYTES,
    )
    cohort.verify_capture_evidence(root, cohort.read_capture_ledger(capture_ledger)[0])
    return receipt_id


def _scheduled_slot(now: datetime) -> datetime | None:
    observed = cohort._aware_utc(now, label="capture runtime clock")
    now_et = observed.astimezone(cohort.ET)
    session = now_et.date()
    if not cohort.nyse_calendar.is_session(session):
        return None
    opened, closed = cohort._session_window(session)
    if not opened <= observed < closed:
        return None
    elapsed = int((observed - opened).total_seconds())
    return opened + timedelta(
        seconds=(elapsed // cohort.CAPTURE_CADENCE_SECONDS)
        * cohort.CAPTURE_CADENCE_SECONDS
    )


def record_unavailable_cycle(
    capture_ledger: Path,
    *,
    private_root: Path,
    clock: Callable[[], datetime],
) -> list[str]:
    attempted = cohort._aware_utc(clock(), label="capture attempt clock")
    slot = _scheduled_slot(attempted)
    if slot is None:
        return []
    completed = cohort._aware_utc(clock(), label="capture completion clock")
    if completed >= slot + timedelta(seconds=cohort.CAPTURE_CADENCE_SECONDS):
        raise cohort.NbboCohortError("unavailable cycle crossed its scheduled slot")
    ids: list[str] = []
    for system, reason in (
        ("mastermindx", "PRECISE_PRODUCER_NOT_CONFIGURED"),
        ("momoedge", "AUTHENTICATED_CAPTURE_NOT_CONFIGURED"),
    ):
        evidence_body = cohort.build_capture_evidence_bytes(
            comparison_system=system,
            scheduled_at=cohort.utc_text(slot),
            attempted_at=cohort.utc_text(attempted),
            completed_at=cohort.utc_text(completed),
            capture_event_at=None,
            disposition="unavailable",
            reason=reason,
            evidence_authenticated=False,
            observed_new_call_count=0,
            new_enrollment_event_ids=(),
            producer_rule_sha256=None,
            source_schema=None,
            source_payload=None,
        )
        receipt = cohort.make_capture_receipt(
            comparison_system=system,
            scheduled_at=cohort.utc_text(slot),
            attempted_at=cohort.utc_text(attempted),
            completed_at=cohort.utc_text(completed),
            disposition="unavailable",
            reason=reason,
            private_evidence_schema=cohort.UNAVAILABLE_CAPTURE_EVIDENCE_SCHEMA,
            private_evidence_sha256=sha256(evidence_body).hexdigest(),
            private_evidence_bytes=len(evidence_body),
        )
        cohort.write_private_evidence(
            private_root,
            namespace="capture_evidence",
            raw_body=evidence_body,
            receipt=receipt["private_evidence"],
        )
        ids.append(
            _append_canonical_row(
                ledger=capture_ledger,
                lock_name=".captures.lock",
                row=receipt,
                validate_row=cohort.validate_capture_receipt,
                read_ledger=cohort.read_capture_ledger,
                id_field="capture_receipt_id",
                max_rows=cohort.MAX_CAPTURE_RECEIPTS,
                max_bytes=cohort.MAX_CAPTURE_BYTES,
            )
        )
    return ids


def append_expiry_terminals(
    event_ledger: Path,
    *,
    private_root: Path,
    now: datetime,
) -> list[str]:
    events, _receipt = cohort.read_event_ledger(event_ledger)
    cohort.verify_event_evidence(private_root, events)
    appended: list[str] = []
    for terminal, evidence_body in cohort.expiry_terminal_candidates(
        events, available_at=now
    ):
        cohort.write_private_evidence(
            private_root,
            namespace="event_evidence",
            raw_body=evidence_body,
            receipt=terminal["private_evidence"],
        )
        appended.append(
            _append_canonical_row(
                ledger=event_ledger,
                lock_name=".events.lock",
                row=terminal,
                validate_row=cohort.validate_event,
                read_ledger=cohort.read_event_ledger,
                id_field="event_id",
                max_rows=cohort.MAX_EVENTS,
                max_bytes=cohort.MAX_EVENT_BYTES,
                reconcile=cohort.reconcile_events,
            )
        )
        events.append(terminal)
    return appended


def fetch_quote_factory(base_url: str, *, timeout_seconds: int):
    base = base_url.rstrip("/")
    if base not in {
        "http://127.0.0.1:25503",
        "http://localhost:25503",
    }:
        raise cohort.NbboCohortError("Theta source must be the local v3 terminal")
    opener = build_opener(_NoRedirectHandler())

    def fetch(query: Mapping[str, str]) -> cohort.FetchedQuoteResponse:
        url = f"{base}{cohort.SOURCE_ENDPOINT}?{urlencode(dict(query))}"
        with opener.open(url, timeout=timeout_seconds) as response:
            if response.geturl() != url:
                raise cohort.NbboSourceError("Theta source redirected unexpectedly")
            if response.status != 200:
                raise cohort.NbboSourceError(
                    f"Theta source returned HTTP {response.status}"
                )
            raw = response.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            raise cohort.NbboSourceError("Theta source response exceeds byte cap")
        payload = cohort.strict_json_value(raw, label="Theta source response")
        return cohort.FetchedQuoteResponse(payload=payload, raw_body=raw)

    return fetch


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-root",
        type=Path,
        default=DEFAULT_PRIVATE_ROOT,
        help="outside-repository 0700 cohort root",
    )
    parser.add_argument(
        "--events",
        type=Path,
        default=None,
        help="outside-repository 0600 event JSONL (default: ROOT/events.jsonl)",
    )
    parser.add_argument(
        "--captures",
        type=Path,
        default=None,
        help="outside-repository 0600 capture JSONL (default: ROOT/captures.jsonl)",
    )
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument(
        "--append-event",
        type=Path,
        help="append one canonical event JSON file to the private ledger",
    )
    parser.add_argument(
        "--event-evidence",
        type=Path,
        help="exact private evidence JSON bytes bound by --append-event",
    )
    parser.add_argument(
        "--append-capture-receipt",
        type=Path,
        help="append one canonical two-system capture receipt",
    )
    parser.add_argument(
        "--capture-evidence",
        type=Path,
        help="exact private evidence JSON bytes bound by --append-capture-receipt",
    )
    parser.add_argument("--record-unavailable-cycle", action="store_true")
    parser.add_argument("--expire-open", action="store_true")
    parser.add_argument("--advance", action="store_true")
    parser.add_argument("--theta-base-url", default=DEFAULT_THETA_BASE_URL)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if (
        sum(
            bool(value)
            for value in (
                args.initialize,
                args.append_event,
                args.append_capture_receipt,
                args.record_unavailable_cycle,
                args.expire_open,
                args.advance,
            )
        )
        != 1
    ):
        raise cohort.NbboCohortError("choose exactly one cohort operation")
    private_root = args.private_root.expanduser().resolve()
    event_ledger = (
        args.events.expanduser().resolve()
        if args.events is not None
        else private_root / "events.jsonl"
    )
    capture_ledger = (
        args.captures.expanduser().resolve()
        if args.captures is not None
        else private_root / "captures.jsonl"
    )
    if args.initialize:
        initialized = initialize(private_root)
        print(
            json.dumps(
                {
                    "status": "initialized",
                    "events": str(initialized),
                    "captures": str(private_root / "captures.jsonl"),
                }
            )
        )
        return 0
    if args.append_event is not None:
        if args.event_evidence is None:
            raise cohort.NbboCohortError(
                "--append-event requires exact --event-evidence"
            )
        event_id = append_event(
            event_ledger,
            args.append_event,
            args.event_evidence,
            private_root=private_root,
        )
        print(json.dumps({"status": "appended", "event_id": event_id}))
        return 0
    if args.append_capture_receipt is not None:
        if args.capture_evidence is None:
            raise cohort.NbboCohortError(
                "--append-capture-receipt requires exact --capture-evidence"
            )
        receipt_id = append_capture_receipt(
            capture_ledger,
            args.append_capture_receipt,
            args.capture_evidence,
            private_root=private_root,
        )
        print(json.dumps({"status": "appended", "capture_receipt_id": receipt_id}))
        return 0
    clock = lambda: datetime.now(timezone.utc)
    if args.record_unavailable_cycle:
        _private_file(capture_ledger, create=False)
        receipt_ids = record_unavailable_cycle(
            capture_ledger,
            private_root=private_root,
            clock=clock,
        )
        print(
            json.dumps(
                {
                    "status": "recorded" if receipt_ids else "outside_rth",
                    "capture_receipt_ids": receipt_ids,
                }
            )
        )
        return 0
    if args.expire_open:
        _private_file(event_ledger, create=False)
        event_ids = append_expiry_terminals(
            event_ledger,
            private_root=private_root,
            now=clock(),
        )
        print(json.dumps({"status": "expired", "event_ids": event_ids}))
        return 0
    _private_file(event_ledger, create=False)
    _private_file(capture_ledger, create=False)
    if args.timeout_seconds < 1 or args.timeout_seconds > 120:
        raise cohort.NbboCohortError("timeout must be between 1 and 120 seconds")
    result = cohort.advance(
        event_ledger=event_ledger,
        private_root=private_root,
        fetch_quote=fetch_quote_factory(
            args.theta_base_url, timeout_seconds=args.timeout_seconds
        ),
        now=clock(),
        clock=clock,
        capture_ledger=capture_ledger,
    )
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cohort.NbboCohortError as exc:
        print(f"options NBBO cohort refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
