from __future__ import annotations

import base64
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from jsonschema import Draft202012Validator, FormatChecker
import pytest

import engine.options_momoedge_browser_adapter as adapter


SCHEDULED = "2026-08-11T23:30:00.000Z"
ATTEMPTED = "2026-08-11T23:30:01.000Z"
REQUESTED = "2026-08-11T23:30:01.125Z"
RESPONDED = "2026-08-11T23:30:01.875Z"
COMPLETED = "2026-08-11T23:30:02.000Z"
CUTOFF = "2026-08-11T00:00:00-04:00"


def _epoch_ms(timestamp: str) -> float:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp() * 1000


def _rows() -> list[dict[str, object]]:
    return [
        {
            "id": "source-active-1",
            "is_active": True,
            "created_at": "2026-08-11T14:31:00.000Z",
            "closed_at": None,
            "asset": "AAPL",
            "direction": "BULLISH",
            "option_symbol": "AAPL260918C00250000",
            "option_contracts": [
                {
                    "root": "AAPL",
                    "type": "CALL",
                    "strike": 250.0,
                    "expiry": "2026-09-18",
                    "premium": 3.45,
                }
            ],
        },
        {
            "id": "source-closed-2",
            "is_active": False,
            "created_at": "2026-08-11T15:00:00.000Z",
            "closed_at": "2026-08-11T20:00:00.000Z",
            "asset": "MSFT",
            "direction": "BEARISH",
            "option_contracts": "[{\"type\":\"PUT\",\"strike\":\"500.50\",\"expiry\":\"2026-09-18\",\"premium\":\"4.20\"}]",
        },
    ]


def _message(rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    source_rows = _rows() if rows is None else rows
    raw = json.dumps(source_rows, separators=(",", ":"), ensure_ascii=False).encode()
    return {
        "schema": adapter.OBSERVATION_SCHEMA,
        "mode": "observe_only",
        "extension_version": adapter.EXTENSION_VERSION,
        "scheduled_at": SCHEDULED,
        "attempted_at": ATTEMPTED,
        "completed_at": COMPLETED,
        "disposition": "fresh_response",
        "reason": None,
        "capture": {
            "request_contract": adapter.REQUEST_CONTRACT,
            "response_schema": adapter.RESPONSE_SCHEMA,
            "source_closed_cutoff_at": CUTOFF,
            "request_started_at": {"utc": REQUESTED, "epoch_ms": _epoch_ms(REQUESTED)},
            "response_completed_at": {"utc": RESPONDED, "epoch_ms": _epoch_ms(RESPONDED)},
            "http_status": 200,
            "response_body_base64": base64.b64encode(raw).decode(),
            "response_byte_count": len(raw),
            "response_sha256": adapter.sha256_bytes(raw),
            "row_count": len(source_rows),
            "active_count": sum(row["is_active"] is True for row in source_rows),
            "closed_count": sum(row["is_active"] is False for row in source_rows),
            "proof": {
                "fresh_request_observed": True,
                "active_and_source_today_closed_scope": True,
                "complete_new_york_day_proven": False,
                "runtime_response_reconciled": True,
                "sensitive_keys_absent": True,
                "fetch_wrapper_restored": True,
            },
        },
        "coverage_eligible": False,
        "authority": dict(adapter.FALSE_AUTHORITY),
    }


def _payload(message: dict[str, object]) -> bytes:
    return json.dumps(message, sort_keys=True, separators=(",", ":")).encode()


def _root(tmp_path: Path) -> Path:
    tmp_path.chmod(0o700)
    return tmp_path / "momoedge_browser_observe_v1"


def _journal(root: Path) -> dict[str, object]:
    path = next((root / "journal").glob("*.json"))
    return json.loads(path.read_text())


def test_fresh_response_persists_exact_private_raw_and_debranded_projection(tmp_path: Path) -> None:
    root = _root(tmp_path)
    message = _message()
    raw = base64.b64decode(message["capture"]["response_body_base64"])

    ack = adapter.persist_observation(_payload(message), root)

    assert ack["accepted"] is True
    assert ack["disposition"] == "fresh_response"
    assert ack["coverage_eligible"] is False
    raw_path = root / "raw" / "sha256" / ack["raw_sha256"][:2] / ack["raw_sha256"][2:4] / f"{ack['raw_sha256']}.json"
    assert raw_path.read_bytes() == raw
    journal = _journal(root)
    assert journal["coverage_eligible"] is False
    assert journal["authority"] == adapter.FALSE_AUTHORITY
    signals = journal["capture"]["projection"]["signals"]
    assert all("source-active-1" not in json.dumps(signal) for signal in signals)
    aapl = next(signal for signal in signals if signal["ticker"] == "AAPL")
    assert aapl["option_symbol"] == "AAPL260918C00250000"
    assert aapl["option_contracts"] == [
        {
            "expiry": "2026-09-18",
            "option_type": "CALL",
            "premium": "3.45",
            "right": "C",
            "root": "AAPL",
            "strike": "250.0",
        }
    ]
    for path in root.rglob("*"):
        expected = 0o700 if path.is_dir() else 0o600
        assert stat.S_IMODE(path.stat().st_mode) == expected


def test_exact_replay_is_idempotent(tmp_path: Path) -> None:
    root = _root(tmp_path)
    payload = _payload(_message())
    first = adapter.persist_observation(payload, root)
    second = adapter.persist_observation(payload, root)
    assert first["created"] is True
    assert second["created"] is False
    assert first["journal_sha256"] == second["journal_sha256"]
    assert len(list((root / "journal").glob("*.json"))) == 1
    assert len(list((root / "raw" / "sha256").rglob("*.json"))) == 1


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "access_token",
        "access_token_value",
        "session_id",
        "my_session_identifier",
        "csrf",
        "private-key",
    ],
)
def test_sensitive_key_fails_to_unavailable_without_raw_persistence(
    tmp_path: Path, sensitive_key: str
) -> None:
    rows = _rows()
    rows[0]["nested"] = {"safe": {sensitive_key: "must-not-persist"}}
    root = _root(tmp_path)
    ack = adapter.persist_observation(_payload(_message(rows)), root)
    assert ack["disposition"] == "unavailable"
    assert ack["reason"] == "sensitive_key_rejected"
    assert not list((root / "raw" / "sha256").rglob("*.json"))
    assert _journal(root)["capture"] is None


def test_duplicate_source_id_and_non_source_cutoff_spelling_fail_closed(tmp_path: Path) -> None:
    duplicate = _rows()
    duplicate[1]["id"] = duplicate[0]["id"]
    root = _root(tmp_path)
    ack = adapter.persist_observation(_payload(_message(duplicate)), root)
    assert (ack["disposition"], ack["reason"]) == ("unavailable", "invalid_fresh_response")

    other_root = tmp_path / "other"
    other_root.mkdir(mode=0o700)
    wrong_root = other_root / "momoedge_browser_observe_v1"
    wrong = _message()
    wrong["capture"]["source_closed_cutoff_at"] = "2026-08-11T04:00:00.000Z"
    ack = adapter.persist_observation(_payload(wrong), wrong_root)
    assert (ack["disposition"], ack["reason"]) == ("unavailable", "invalid_fresh_response")


def test_duplicate_json_key_is_never_written(tmp_path: Path) -> None:
    message = _message()
    raw = b'[{"id":"x","id":"y","is_active":true,"created_at":"2026-08-11T14:31:00Z"}]'
    message["capture"].update(
        {
            "response_body_base64": base64.b64encode(raw).decode(),
            "response_byte_count": len(raw),
            "response_sha256": adapter.sha256_bytes(raw),
            "row_count": 1,
            "active_count": 1,
            "closed_count": 0,
        }
    )
    root = _root(tmp_path)
    ack = adapter.persist_observation(_payload(message), root)
    assert (ack["disposition"], ack["reason"]) == ("unavailable", "invalid_fresh_response")
    assert not list((root / "raw" / "sha256").rglob("*.json"))


def test_numeric_id_bombs_and_nonfinite_js_magnitudes_fail_without_raw(tmp_path: Path) -> None:
    root = _root(tmp_path)
    message = _message()
    raw = (
        b'[{"id":'
        + (b"9" * 5000)
        + b',"is_active":true,"created_at":"2026-08-11T14:31:00Z"}]'
    )
    message["capture"].update(
        {
            "response_body_base64": base64.b64encode(raw).decode(),
            "response_byte_count": len(raw),
            "response_sha256": adapter.sha256_bytes(raw),
            "row_count": 1,
            "active_count": 1,
            "closed_count": 0,
        }
    )
    ack = adapter.persist_observation(_payload(message), root)
    assert (ack["disposition"], ack["reason"]) == ("unavailable", "invalid_fresh_response")
    assert not list((root / "raw" / "sha256").rglob("*.json"))

    with pytest.raises(adapter.MomoEdgeObserveError, match="magnitude"):
        adapter.strict_json_loads(b'{"safe":1e400}')


def test_projection_expansion_and_pathological_depth_fail_before_raw_write(tmp_path: Path) -> None:
    expanded = _rows()
    expanded[0]["option_contracts"] = [{} for _ in range(adapter.MAX_CONTRACTS_PER_SIGNAL + 1)]
    root = _root(tmp_path)
    ack = adapter.persist_observation(_payload(_message(expanded)), root)
    assert (ack["disposition"], ack["reason"]) == ("unavailable", "invalid_fresh_response")
    assert not list((root / "raw" / "sha256").rglob("*.json"))

    nested: dict[str, object] = {"leaf": "safe"}
    for _ in range(adapter.MAX_JSON_DEPTH + 2):
        nested = {"nested": nested}
    deep_rows = _rows()
    deep_rows[0]["metadata"] = nested
    other_parent = tmp_path / "deep"
    other_parent.mkdir(mode=0o700)
    other_root = other_parent / "momoedge_browser_observe_v1"
    ack = adapter.persist_observation(_payload(_message(deep_rows)), other_root)
    assert (ack["disposition"], ack["reason"]) == ("unavailable", "invalid_fresh_response")
    assert not list((other_root / "raw" / "sha256").rglob("*.json"))


def test_conflicting_slot_does_not_publish_incoming_raw(tmp_path: Path) -> None:
    root = _root(tmp_path)
    first = _message()
    adapter.persist_observation(_payload(first), root)
    before = set((root / "raw" / "sha256").rglob("*.json"))
    changed_rows = _rows()
    changed_rows[0]["direction"] = "BEARISH"
    with pytest.raises(adapter.ObservationConflict):
        adapter.persist_observation(_payload(_message(changed_rows)), root)
    assert set((root / "raw" / "sha256").rglob("*.json")) == before
    assert len(list((root / "quarantine").glob("*.json"))) == 1


def test_retry_recovers_crash_after_raw_before_journal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path)
    payload = _payload(_message())
    original = adapter._write_once
    faulted = False

    def fault_once(path: Path, body: bytes) -> bool:
        nonlocal faulted
        if path.parent.name == "journal" and not faulted:
            faulted = True
            raise OSError("seeded crash before journal publication")
        return original(path, body)

    monkeypatch.setattr(adapter, "_write_once", fault_once)
    with pytest.raises(OSError, match="seeded crash"):
        adapter.persist_observation(payload, root)
    monkeypatch.setattr(adapter, "_write_once", original)
    ack = adapter.persist_observation(payload, root)
    assert ack["disposition"] == "fresh_response"
    assert len(list((root / "raw" / "sha256").rglob("*.json"))) == 1
    assert len(list((root / "journal").glob("*.json"))) == 1


def test_retry_repairs_crash_after_journal_link_before_temp_unlink(tmp_path: Path) -> None:
    root = _root(tmp_path)
    payload = _payload(_message())
    adapter.persist_observation(payload, root)
    journal = next((root / "journal").glob("*.json"))
    interrupted = journal.parent / f".{journal.name}.999.{'a' * 16}.tmp"
    os.link(journal, interrupted)
    assert journal.stat().st_nlink == 2
    ack = adapter.persist_observation(payload, root)
    assert ack["created"] is False
    assert journal.stat().st_nlink == 1
    assert not interrupted.exists()


def test_retry_reconciles_raw_temp_before_capacity_scan(tmp_path: Path) -> None:
    root = _root(tmp_path)
    message = _message()
    raw = base64.b64decode(message["capture"]["response_body_base64"])
    digest = adapter.sha256_bytes(raw)
    adapter.prepare_private_root(root)
    raw_path = adapter._raw_path(root, digest)
    interrupted = raw_path.parent / f".{raw_path.name}.999.{'b' * 16}.tmp"
    interrupted.write_bytes(raw)
    interrupted.chmod(0o600)

    ack = adapter.persist_observation(_payload(message), root)

    assert ack["disposition"] == "fresh_response"
    assert raw_path.read_bytes() == raw
    assert not interrupted.exists()


def test_staging_from_old_slots_cannot_poison_future_capacity_scans(tmp_path: Path) -> None:
    root = _root(tmp_path)
    adapter.prepare_private_root(root)
    old_slot = "20260811T233000.000000Z"
    raw_target = adapter._raw_path(root, "f" * 64)
    journal_target = root / "journal" / f"{old_slot}.json"
    quarantine_target = root / "quarantine" / f"{old_slot}.{'e' * 64}.json"
    interrupted: list[Path] = []
    for index, target in enumerate((raw_target, journal_target, quarantine_target), start=1):
        candidate = target.parent / f".{target.name}.{index}.{'c' * 16}.tmp"
        candidate.write_bytes(b"{}")
        candidate.chmod(0o600)
        interrupted.append(candidate)

    message = _message()
    message.update(
        {
            "scheduled_at": "2026-08-11T23:35:00.000Z",
            "attempted_at": "2026-08-11T23:35:01.000Z",
            "completed_at": "2026-08-11T23:35:02.000Z",
            "disposition": "unavailable",
            "reason": "no_matching_tab",
            "capture": None,
        }
    )
    ack = adapter.persist_observation(_payload(message), root)
    assert ack["accepted"] is True
    assert not any(path.exists() for path in interrupted)


def test_directory_links_are_fsynced_before_ack_and_fsync_failure_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    payload = _payload(_message())
    original = adapter._fsync_directory
    calls: list[Path] = []

    def record(path: Path) -> None:
        calls.append(path)
        original(path)

    monkeypatch.setattr(adapter, "_fsync_directory", record)
    adapter.persist_observation(payload, root)
    raw_path = next((root / "raw" / "sha256").rglob("*.json"))
    assert root.parent in calls
    assert root in calls
    assert root / "raw" in calls
    assert root / "raw" / "sha256" in calls
    assert raw_path.parent.parent in calls
    assert raw_path.parent in calls

    other_parent = tmp_path / "fsync-fault"
    other_parent.mkdir(mode=0o700)
    other_root = other_parent / "momoedge_browser_observe_v1"
    faulted = False

    def fail_root_link_once(path: Path) -> None:
        nonlocal faulted
        if path == other_parent and not faulted:
            faulted = True
            raise OSError("seeded parent-link fsync failure")
        original(path)

    monkeypatch.setattr(adapter, "_fsync_directory", fail_root_link_once)
    with pytest.raises(OSError, match="seeded parent-link fsync failure"):
        adapter.persist_observation(payload, other_root)
    monkeypatch.setattr(adapter, "_fsync_directory", original)
    assert adapter.persist_observation(payload, other_root)["accepted"] is True


def test_retry_resyncs_target_link_after_object_directory_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    payload = _payload(_message())
    original = adapter._fsync_directory
    journal_dir = root / "journal"
    faulted = False

    def fail_journal_link_once(path: Path) -> None:
        nonlocal faulted
        if path == journal_dir and list(journal_dir.glob("*.json")) and not faulted:
            faulted = True
            raise OSError("seeded journal-link fsync failure")
        original(path)

    monkeypatch.setattr(adapter, "_fsync_directory", fail_journal_link_once)
    with pytest.raises(OSError, match="seeded journal-link fsync failure"):
        adapter.persist_observation(payload, root)
    assert len(list(journal_dir.glob("*.json"))) == 1

    synced: list[Path] = []

    def record(path: Path) -> None:
        synced.append(path)
        original(path)

    monkeypatch.setattr(adapter, "_fsync_directory", record)
    ack = adapter.persist_observation(payload, root)
    assert ack["created"] is False
    assert journal_dir in synced


def test_hardlink_mode_and_symlink_roots_fail_closed(tmp_path: Path) -> None:
    root = _root(tmp_path)
    payload = _payload(_message())
    ack = adapter.persist_observation(payload, root)
    raw_path = root / "raw" / "sha256" / ack["raw_sha256"][:2] / ack["raw_sha256"][2:4] / f"{ack['raw_sha256']}.json"
    os.link(raw_path, raw_path.with_suffix(".linked"))
    with pytest.raises(adapter.PrivateStoreError):
        adapter.persist_observation(payload, root)

    safe_parent = tmp_path / "safe-parent"
    safe_parent.mkdir(mode=0o700)
    real = safe_parent / "real"
    real.mkdir(mode=0o700)
    symlink_root = safe_parent / "momoedge_browser_observe_v1"
    symlink_root.symlink_to(real, target_is_directory=True)
    with pytest.raises(adapter.PrivateStoreError):
        adapter.persist_observation(payload, symlink_root)


def test_observer_root_must_be_disjoint_from_repo_and_cohort() -> None:
    repo_root = Path(adapter.__file__).resolve().parents[1]
    with pytest.raises(adapter.PrivateStoreError, match="disjoint"):
        adapter.prepare_private_root(repo_root / "tmp" / "momoedge_browser_observe_v1")
    cohort = Path.home() / ".mastermind_private" / "options_nbbo_cohort_v1" / "momoedge_browser_observe_v1"
    with pytest.raises(adapter.PrivateStoreError, match="disjoint"):
        adapter.prepare_private_root(cohort)


def test_unknown_private_namespace_fails_closed(tmp_path: Path) -> None:
    root = _root(tmp_path)
    adapter.persist_observation(_payload(_message()), root)
    forged = root / "journal" / "forged.json"
    forged.write_text("{}")
    forged.chmod(0o600)
    with pytest.raises(adapter.PrivateStoreError, match="unexpected journal filename"):
        adapter._private_tree_usage(root / "journal")


def test_whitespace_ticker_returns_one_structured_receiver_ack(tmp_path: Path) -> None:
    rows = _rows()
    rows[0]["ticker"] = "   "
    message = _payload(_message(rows))
    framed = len(message).to_bytes(4, "little") + message
    root = _root(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.momoedge_browser_receiver",
            "--private-root",
            str(root),
        ],
        cwd=Path(adapter.__file__).resolve().parents[1],
        input=framed,
        capture_output=True,
        timeout=10,
        check=True,
    )
    assert completed.stderr == b""
    length = int.from_bytes(completed.stdout[:4], "little")
    assert len(completed.stdout) == length + 4
    ack = json.loads(completed.stdout[4:])
    assert (ack["disposition"], ack["reason"], ack["accepted"]) == (
        "unavailable",
        "invalid_fresh_response",
        True,
    )
    assert ack["raw_sha256"] is None


@pytest.mark.parametrize("malformed_reason", [{}, []])
def test_unhashable_unavailable_reason_returns_one_rejected_ack(
    tmp_path: Path, malformed_reason: object
) -> None:
    message_value = _message()
    message_value.update(
        {"disposition": "unavailable", "reason": malformed_reason, "capture": None}
    )
    message = _payload(message_value)
    framed = len(message).to_bytes(4, "little") + message
    root = _root(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(Path(adapter.__file__).resolve().parents[1] / "scripts" / "momoedge_browser_receiver.py"),
            "--private-root",
            str(root),
        ],
        cwd=tmp_path,
        input=framed,
        capture_output=True,
        timeout=10,
        check=True,
    )
    assert completed.stderr == b""
    length = int.from_bytes(completed.stdout[:4], "little")
    assert len(completed.stdout) == length + 4
    ack = json.loads(completed.stdout[4:])
    assert ack["accepted"] is False
    assert ack["reason"] == "receiver_rejected"


class _OneByteReader(io.BytesIO):
    def read(self, size: int = -1) -> bytes:
        return super().read(1 if size < 0 else min(size, 1))


def test_native_frame_handles_partial_pipe_reads_and_rejects_truncation() -> None:
    payload = b'{"safe":true}'
    framed = len(payload).to_bytes(4, "little") + payload
    assert adapter.read_native_frame(_OneByteReader(framed)) == payload
    with pytest.raises(adapter.MomoEdgeObserveError, match="body is incomplete"):
        adapter.read_native_frame(io.BytesIO(len(payload).to_bytes(4, "little") + payload[:-1]))
    with pytest.raises(adapter.MomoEdgeObserveError, match="length"):
        adapter.read_native_frame(io.BytesIO((adapter.MAX_NATIVE_MESSAGE_BYTES + 1).to_bytes(4, "little")))


def test_unavailable_envelope_is_journaled_and_never_coverage(tmp_path: Path) -> None:
    message = _message()
    message.update({"disposition": "unavailable", "reason": "no_matching_tab", "capture": None})
    root = _root(tmp_path)
    ack = adapter.persist_observation(_payload(message), root)
    assert ack == {
        "schema": adapter.ACK_SCHEMA,
        "accepted": True,
        "created": True,
        "disposition": "unavailable",
        "reason": "no_matching_tab",
        "journal_sha256": ack["journal_sha256"],
        "raw_sha256": None,
        "coverage_eligible": False,
    }
    assert not list((root / "raw" / "sha256").rglob("*.json"))


def test_fresh_envelope_and_emitted_journal_validate_against_published_schemas(
    tmp_path: Path,
) -> None:
    repo = Path(adapter.__file__).resolve().parents[1]
    observation_schema = json.loads(
        (repo / "contracts" / "options" / "options.momoedge_browser_observation.v1.schema.json").read_text()
    )
    journal_schema = json.loads(
        (repo / "contracts" / "options" / "options.momoedge_browser_observe_journal.v1.schema.json").read_text()
    )
    message = _message()
    Draft202012Validator(observation_schema, format_checker=FormatChecker()).validate(message)

    root = _root(tmp_path)
    adapter.persist_observation(_payload(message), root)
    Draft202012Validator(journal_schema, format_checker=FormatChecker()).validate(_journal(root))
