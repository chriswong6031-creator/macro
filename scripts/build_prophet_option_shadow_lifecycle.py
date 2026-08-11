#!/usr/bin/env python3
"""Advance the host-private Prophet exact-option shadow lifecycle.

This processor consumes two already-governed sources and writes no public object:

* the host-private ``prophet.option_mark_observation/v1`` chain; and
* append-only canonical ``prophet.ledger/v1`` close rows.

The first invocation freezes a prospective boundary.  Later invocations enroll a
plan only on its first fresh, post-trigger trade-paired mid after that boundary.
When the canonical Prophet ledger closes an enrolled plan, the processor writes one
immutable terminal event using the latest admitted mark from that same session, or
an explicit unavailable reason.  The resulting percentage is a shadow mid-to-mid
research return.  It is never a fill, executable quote, NBBO, trade P&L, or input to
``prophet.ledger/v1.option_result_pct``.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import secrets
import stat
import subprocess
from copy import deepcopy
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from pathlib import Path
from typing import Any

from scripts import build_prophet_marks as mark_chain


log = logging.getLogger(__name__)

EVENT_SCHEMA = "prophet.option_shadow_lifecycle_event/v1"
EVENT_POINTER_SCHEMA = "prophet.option_shadow_lifecycle_pointer/v1"
STATE_SCHEMA = "prophet.option_shadow_lifecycle_state/v1"
ACTIVATION_BOUNDARY_SCHEMA = "prophet.option_shadow_lifecycle_activation_boundary/v1"
LEDGER_SNAPSHOT_RECEIPT_SCHEMA = "prophet.canonical_ledger_snapshot_receipt/v1"
EVENT_PREFIX = "events"

_REPO = Path(__file__).resolve().parents[1]
DEFAULT_STATE_ROOT = (
    Path.home() / ".mastermind_private" / "prophet_option_shadow_lifecycle_v1"
)
DEFAULT_EVENT_SCHEMA_PATH = (
    _REPO
    / "contracts"
    / "options"
    / "prophet.option_shadow_lifecycle_event.v1.schema.json"
)
DEFAULT_LEDGER_DIRECTORY = DEFAULT_STATE_ROOT / "canonical_ledger"
DEFAULT_LEDGER_PATH = DEFAULT_LEDGER_DIRECTORY / "ledger.jsonl"
DEFAULT_LEDGER_RECEIPT_PATH = DEFAULT_LEDGER_DIRECTORY / "receipt.json"

CANONICAL_LEDGER_REPOSITORY = (
    "https://github.com/mastermindx-market-intelligence/macro"
)
CANONICAL_LEDGER_GIT_REMOTE = CANONICAL_LEDGER_REPOSITORY + ".git"
CANONICAL_LEDGER_REF = "refs/heads/main"
CANONICAL_LEDGER_SOURCE_PATH = "data/prophet/ledger.jsonl"
CANONICAL_LEDGER_RAW_TEMPLATE = (
    "https://raw.githubusercontent.com/mastermindx-market-intelligence/macro/"
    "{commit}/data/prophet/ledger.jsonl"
)

MAX_LEDGER_BYTES = 32 * 1024 * 1024
MAX_RECEIPT_BYTES = 64 * 1024
MAX_CHAIN_DEPTH = 20_000

POST_TRIGGER_PHASES = frozenset(
    {
        "triggered_pre_t1",
        "at_t1",
        "between_t1_t2",
        "post_t1_failed_hold",
        "at_t2",
        "post_t2",
        "overtime",
    }
)
CANONICAL_OUTCOMES = frozenset(
    {
        "T1_HIT",
        "T2_HIT",
        "INVALIDATED",
        "EXPIRED",
        "CLOSED_EARLY",
        "NO_ENTRY",
    }
)
UNAVAILABLE_REASONS = frozenset(
    {
        "NO_SAME_SESSION_ADMITTED_MARK",
        "CONTRACT_DRIFT",
        "CANONICAL_NO_ENTRY",
        "CANONICAL_CLOSE_PREDATES_ENROLLMENT",
    }
)

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[a-f0-9]{40,64}$")
_EVENT_ID_RE = re.compile(r"^posle_[a-f0-9]{64}$")
_STATE_ID_RE = re.compile(r"^posls_[a-f0-9]{64}$")


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _authority_block() -> dict[str, bool]:
    return {
        "rank_authority": False,
        "gate_authority": False,
        "sizing_authority": False,
        "issue_authority": False,
        "trade_authority": False,
        "prophet_authority": False,
        "neural_web_authority": False,
        "training_authority": False,
        "execution_authority": False,
    }


def _limitations_block() -> dict[str, bool]:
    return {
        "shadow_research_only": True,
        "not_trade_pnl": True,
        "no_provider_observed_entry_or_exit": True,
        "not_fill": True,
        "not_nbbo": True,
        "not_executable": True,
        "public_redistribution": False,
        "never_populates_option_result_pct": True,
        "prospective_after_activation_only": True,
    }


def _parse_date(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} is missing")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} is malformed") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{label} is malformed")
    return value


def _event_validator():
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except Exception as exc:  # noqa: BLE001
        raise ValueError("jsonschema is required for lifecycle event publication") from exc

    raw = os.environ.get(
        "PROPHET_OPTION_SHADOW_LIFECYCLE_SCHEMA_PATH",
        str(DEFAULT_EVENT_SCHEMA_PATH),
    )
    schema_path = Path(raw).expanduser()
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            f"option shadow lifecycle schema unavailable: {schema_path}: {exc}"
        ) from exc
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_event_schema(event: dict[str, object]) -> None:
    errors = sorted(
        _event_validator().iter_errors(event),
        key=lambda item: (list(item.absolute_path), item.message),
    )
    if errors:
        summary = "; ".join(
            f"{'.'.join(str(part) for part in err.absolute_path) or '<root>'}: "
            f"{err.message}"
            for err in errors[:5]
        )
        raise ValueError(f"option shadow lifecycle schema check failed: {summary}")


def _event_pointer(event: dict[str, object]) -> dict[str, object]:
    event_id = event.get("event_id")
    session_date = event.get("event_session_date")
    if not isinstance(event_id, str) or not _EVENT_ID_RE.fullmatch(event_id):
        raise ValueError("option shadow lifecycle event id is malformed")
    _parse_date(session_date, label="option shadow lifecycle event session")
    identity = dict(event)
    identity.pop("event_id", None)
    expected = "posle_" + sha256(_canonical_json_bytes(identity)).hexdigest()
    if event_id != expected:
        raise ValueError("option shadow lifecycle event content identity mismatch")
    body = _canonical_json_bytes(event)
    return {
        "schema": EVENT_POINTER_SCHEMA,
        "event_id": event_id,
        "key": f"{EVENT_PREFIX}/{session_date}/{event_id}.json",
        "sha256": sha256(body).hexdigest(),
        "bytes": len(body),
    }


def _validate_event_pointer(pointer: object) -> dict[str, object]:
    required = {"schema", "event_id", "key", "sha256", "bytes"}
    if not isinstance(pointer, dict) or set(pointer) != required:
        raise ValueError("option shadow lifecycle pointer shape is malformed")
    event_id = pointer.get("event_id")
    key = pointer.get("key")
    digest = pointer.get("sha256")
    size = pointer.get("bytes")
    if pointer.get("schema") != EVENT_POINTER_SCHEMA:
        raise ValueError("option shadow lifecycle pointer schema mismatch")
    if not isinstance(event_id, str) or not _EVENT_ID_RE.fullmatch(event_id):
        raise ValueError("option shadow lifecycle pointer id is malformed")
    if (
        not isinstance(key, str)
        or not re.fullmatch(
            rf"{EVENT_PREFIX}/\d{{4}}-\d{{2}}-\d{{2}}/"
            rf"{re.escape(event_id)}\.json",
            key,
        )
    ):
        raise ValueError("option shadow lifecycle pointer key is malformed")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise ValueError("option shadow lifecycle pointer digest is malformed")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("option shadow lifecycle pointer size is malformed")
    return dict(pointer)


def _state_root() -> Path:
    raw = os.environ.get(
        "PROPHET_OPTION_SHADOW_LIFECYCLE_STATE_ROOT",
        str(DEFAULT_STATE_ROOT),
    )
    root = _validate_private_root_location(
        Path(raw).expanduser(), label="private lifecycle state"
    )
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    mark_chain._require_private_directory(root)
    return root


def _validate_private_root_location(root: Path, *, label: str) -> Path:
    if not root.is_absolute() or root in {Path("/"), Path.home()}:
        raise ValueError(f"{label} root must be a narrow absolute path")
    resolved = root.resolve(strict=False)
    repo = _REPO.resolve()
    if resolved == repo or repo in resolved.parents:
        raise ValueError(f"{label} root cannot be inside the repo")
    return root


def _mark_root() -> Path:
    raw = os.environ.get(
        "PROPHET_OPTION_EVIDENCE_STATE_ROOT",
        str(mark_chain.DEFAULT_EVIDENCE_STATE_ROOT),
    )
    root = _validate_private_root_location(
        Path(raw).expanduser(), label="private option mark evidence"
    )
    mark_chain._require_private_directory(root)
    return root


def _event_path(
    root: Path,
    pointer: dict[str, object],
    *,
    create_parents: bool,
) -> Path:
    pointer = _validate_event_pointer(pointer)
    parts = str(pointer["key"]).split("/")
    events = root / parts[0]
    session = events / parts[1]
    check = mark_chain._ensure_private_directory if create_parents else mark_chain._require_private_directory
    check(events)
    check(session)
    return session / parts[2]


def _load_event(root: Path, pointer: object) -> dict[str, object]:
    checked = _validate_event_pointer(pointer)
    body = mark_chain._read_private_file(
        _event_path(root, checked, create_parents=False)
    )
    if body is None or len(body) != checked["bytes"]:
        raise ValueError("option shadow lifecycle event byte count mismatch")
    if sha256(body).hexdigest() != checked["sha256"]:
        raise ValueError("option shadow lifecycle event digest mismatch")
    try:
        event = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("option shadow lifecycle event is invalid JSON") from exc
    if not isinstance(event, dict) or _canonical_json_bytes(event) != body:
        raise ValueError("option shadow lifecycle event is not canonical JSON")
    _validate_event_schema(event)
    if _event_pointer(event) != checked:
        raise ValueError("option shadow lifecycle event pointer mismatch")
    return event


def _mark_head(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    body = mark_chain._read_private_file(root / "current.json")
    if body is None:
        raise ValueError("private option mark evidence head is missing")
    try:
        head = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("private option mark evidence head is invalid JSON") from exc
    if (
        not isinstance(head, dict)
        or set(head) != {"schema", "evidence"}
        or head.get("schema") != mark_chain.EVIDENCE_HEAD_SCHEMA
        or mark_chain._canonical_json_bytes(head) != body
    ):
        raise ValueError("private option mark evidence head shape is malformed")
    pointer = mark_chain._validate_pointer(head.get("evidence"))
    return pointer, _load_mark_observation(root, pointer)


def _load_mark_observation(
    root: Path,
    pointer: object,
) -> dict[str, object]:
    checked = mark_chain._validate_pointer(pointer)
    path = mark_chain._private_observation_path(
        root, checked, create_parents=False
    )
    body = mark_chain._read_private_file(path)
    if body is None or len(body) != checked["bytes"]:
        raise ValueError("private option mark observation byte count mismatch")
    if sha256(body).hexdigest() != checked["sha256"]:
        raise ValueError("private option mark observation digest mismatch")
    try:
        observation = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("private option mark observation is invalid JSON") from exc
    if not isinstance(observation, dict) or mark_chain._canonical_json_bytes(observation) != body:
        raise ValueError("private option mark observation is not canonical JSON")
    mark_chain._validate_evidence_schema(observation)
    if mark_chain._observation_pointer(observation) != checked:
        raise ValueError("private option mark observation pointer mismatch")
    return observation


def _new_mark_observations(
    root: Path,
    current: dict[str, object],
    cursor: dict[str, object],
) -> list[tuple[dict[str, object], dict[str, object]]]:
    current = mark_chain._validate_pointer(current)
    cursor = mark_chain._validate_pointer(cursor)
    if current == cursor:
        _load_mark_observation(root, cursor)
        return []

    backwards: list[tuple[dict[str, object], dict[str, object]]] = []
    pointer: dict[str, object] | None = current
    seen: set[str] = set()
    for _ in range(MAX_CHAIN_DEPTH):
        if pointer is None:
            break
        if pointer == cursor:
            _load_mark_observation(root, cursor)
            backwards.reverse()
            return backwards
        observation_id = str(pointer["observation_id"])
        if observation_id in seen:
            raise ValueError("private option mark observation chain contains a cycle")
        seen.add(observation_id)
        observation = _load_mark_observation(root, pointer)
        backwards.append((pointer, observation))
        previous = observation.get("previous")
        pointer = None if previous is None else mark_chain._validate_pointer(previous)
    raise ValueError("private option mark cursor is not an ancestor of the current head")


def _read_private_blob(path: Path, *, max_bytes: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{label} is unavailable: {path}: {exc}") from exc
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or info.st_size <= 0
            or info.st_size > max_bytes
        ):
            raise ValueError(f"{label} is not a caller-owned 0600 regular file")
        body = b""
        while len(body) < info.st_size:
            chunk = os.read(fd, info.st_size - len(body))
            if not chunk:
                break
            body += chunk
        if len(body) != info.st_size or os.read(fd, 1):
            raise ValueError(f"{label} changed length during read")
        return body
    finally:
        os.close(fd)


def _atomic_private_write(path: Path, body: bytes, *, max_bytes: int) -> None:
    if not body or len(body) > max_bytes:
        raise ValueError("private canonical ledger write has an unsafe size")
    mark_chain._require_private_directory(path.parent)
    temporary = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
    )
    fd = os.open(temporary, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        mark_chain._write_all(fd, body)
        os.fsync(fd)
    except Exception:
        os.close(fd)
        temporary.unlink(missing_ok=True)
        raise
    else:
        os.close(fd)
    try:
        os.replace(temporary, path)
        mark_chain._fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)
    if _read_private_blob(path, max_bytes=max_bytes, label="private canonical ledger file") != body:
        raise ValueError("private canonical ledger atomic write readback mismatch")


def _read_ledger(path: Path) -> bytes:
    body = _read_private_blob(
        path,
        max_bytes=MAX_LEDGER_BYTES,
        label="canonical Prophet ledger snapshot",
    )
    if not body.endswith(b"\n"):
        raise ValueError("canonical Prophet ledger does not end on a line boundary")
    return body


def _validate_ledger_row(row: object, *, ordinal: int) -> dict[str, object]:
    if not isinstance(row, dict):
        raise ValueError(f"canonical Prophet ledger row {ordinal} is not an object")
    if row.get("schema") != "prophet.ledger/v1":
        raise ValueError(f"canonical Prophet ledger row {ordinal} has wrong schema")
    plan_id = row.get("id")
    outcome = row.get("outcome")
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise ValueError(f"canonical Prophet ledger row {ordinal} has no plan id")
    if outcome not in CANONICAL_OUTCOMES:
        raise ValueError(f"canonical Prophet ledger row {ordinal} has unknown outcome")
    close_date = _parse_date(
        row.get("close_date"), label=f"canonical Prophet ledger row {ordinal} close_date"
    )
    asof = _parse_date(
        row.get("asof"), label=f"canonical Prophet ledger row {ordinal} asof"
    )
    if date.fromisoformat(asof) < date.fromisoformat(close_date):
        raise ValueError(f"canonical Prophet ledger row {ordinal} predates its close")
    if "option_result_pct" not in row or row.get("option_result_pct") is not None:
        raise ValueError(
            f"canonical Prophet ledger row {ordinal} already claims or lacks an "
            "explicit null option_result_pct"
        )
    return dict(row)


def _ledger_rows(body: bytes) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("canonical Prophet ledger is not UTF-8") from exc
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            raw_row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"canonical Prophet ledger line {line_number} is invalid JSON"
            ) from exc
        row = _validate_ledger_row(raw_row, ordinal=len(rows) + 1)
        plan_id = str(row["id"])
        if plan_id in seen:
            raise ValueError(f"canonical Prophet ledger repeats plan id {plan_id}")
        seen.add(plan_id)
        rows.append(row)
    return rows


def _ledger_receipt(
    body: bytes,
    rows: list[dict[str, object]],
    *,
    source_commit: str,
) -> dict[str, object]:
    return {
        "schema": LEDGER_SNAPSHOT_RECEIPT_SCHEMA,
        "source_repository": CANONICAL_LEDGER_REPOSITORY,
        "source_ref": CANONICAL_LEDGER_REF,
        "source_commit": source_commit,
        "source_path": CANONICAL_LEDGER_SOURCE_PATH,
        "bytes": len(body),
        "sha256": sha256(body).hexdigest(),
        "row_count": len(rows),
    }


def _validate_ledger_receipt(receipt: object) -> dict[str, object]:
    required = {
        "schema",
        "source_repository",
        "source_ref",
        "source_commit",
        "source_path",
        "bytes",
        "sha256",
        "row_count",
    }
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise ValueError("canonical Prophet ledger cursor shape is malformed")
    if (
        receipt.get("schema") != LEDGER_SNAPSHOT_RECEIPT_SCHEMA
        or receipt.get("source_repository") != CANONICAL_LEDGER_REPOSITORY
        or receipt.get("source_ref") != CANONICAL_LEDGER_REF
        or receipt.get("source_path") != CANONICAL_LEDGER_SOURCE_PATH
    ):
        raise ValueError("canonical Prophet ledger cursor source is malformed")
    source_commit = receipt.get("source_commit")
    if not isinstance(source_commit, str) or not _GIT_COMMIT_RE.fullmatch(source_commit):
        raise ValueError("canonical Prophet ledger cursor commit is malformed")
    size = receipt.get("bytes")
    digest = receipt.get("sha256")
    count = receipt.get("row_count")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("canonical Prophet ledger cursor size is malformed")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise ValueError("canonical Prophet ledger cursor digest is malformed")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("canonical Prophet ledger cursor row count is malformed")
    return dict(receipt)


def _read_ledger_snapshot(
    ledger_path: Path,
    receipt_path: Path,
) -> tuple[bytes, list[dict[str, object]], dict[str, object]]:
    body = _read_ledger(ledger_path)
    rows = _ledger_rows(body)
    raw_receipt = _read_private_blob(
        receipt_path,
        max_bytes=MAX_RECEIPT_BYTES,
        label="canonical Prophet ledger receipt",
    )
    try:
        receipt_object = json.loads(raw_receipt.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("canonical Prophet ledger receipt is invalid JSON") from exc
    if (
        not isinstance(receipt_object, dict)
        or _canonical_json_bytes(receipt_object) != raw_receipt
    ):
        raise ValueError("canonical Prophet ledger receipt is not canonical JSON")
    receipt = _validate_ledger_receipt(receipt_object)
    expected = _ledger_receipt(
        body,
        rows,
        source_commit=str(receipt["source_commit"]),
    )
    if receipt != expected:
        raise ValueError("canonical Prophet ledger snapshot does not match its receipt")
    return body, rows, receipt


def _verify_ledger_prefix(body: bytes, cursor: object) -> dict[str, object]:
    checked = _validate_ledger_receipt(cursor)
    size = int(checked["bytes"])
    if len(body) < size or sha256(body[:size]).hexdigest() != checked["sha256"]:
        raise ValueError("canonical Prophet ledger no longer extends the prior prefix")
    if body[:size] and not body[:size].endswith(b"\n"):
        raise ValueError("canonical Prophet ledger cursor is not on a line boundary")
    return checked


def _ledger_paths(
    lifecycle_root: Path,
    *,
    ledger_path: Path | None,
    ledger_receipt_path: Path | None,
    create: bool,
) -> tuple[Path, Path]:
    if ledger_path is None:
        raw = os.environ.get(
            "PROPHET_LEDGER_PATH",
            str(lifecycle_root / "canonical_ledger" / "ledger.jsonl"),
        )
        ledger_path = Path(raw).expanduser()
    if ledger_receipt_path is None:
        raw_receipt = os.environ.get(
            "PROPHET_LEDGER_RECEIPT_PATH",
            str(ledger_path.parent / "receipt.json"),
        )
        ledger_receipt_path = Path(raw_receipt).expanduser()
    if ledger_path == ledger_receipt_path or ledger_path.parent != ledger_receipt_path.parent:
        raise ValueError("canonical Prophet ledger and receipt must be distinct siblings")
    parent = _validate_private_root_location(
        ledger_path.parent,
        label="private canonical Prophet ledger",
    )
    if ledger_receipt_path.parent.resolve(strict=False) != parent.resolve(strict=False):
        raise ValueError("canonical Prophet ledger receipt parent is ambiguous")
    if create:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    mark_chain._require_private_directory(parent)
    return ledger_path, ledger_receipt_path


def _resolve_current_main_commit() -> str:
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            [
                "/usr/bin/git",
                "ls-remote",
                CANONICAL_LEDGER_GIT_REMOTE,
                CANONICAL_LEDGER_REF,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"could not resolve canonical current main: {exc}") from exc
    matches: list[str] = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1] == CANONICAL_LEDGER_REF:
            matches.append(fields[0])
    if result.returncode != 0 or len(matches) != 1 or not _GIT_COMMIT_RE.fullmatch(matches[0]):
        detail = result.stderr.strip()[:240] or f"exit {result.returncode}"
        raise ValueError(f"canonical current-main ref resolution failed: {detail}")
    return matches[0]


def _download_current_main_ledger(source_commit: str) -> bytes:
    if not _GIT_COMMIT_RE.fullmatch(source_commit):
        raise ValueError("canonical current-main commit is malformed")
    url = CANONICAL_LEDGER_RAW_TEMPLATE.format(commit=source_commit)
    try:
        result = subprocess.run(
            [
                "/usr/bin/curl",
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--max-time",
                "30",
                "--max-filesize",
                str(MAX_LEDGER_BYTES),
                "--proto",
                "=https",
                "--user-agent",
                "macro-prophet-shadow-lifecycle/1",
                url,
            ],
            check=False,
            capture_output=True,
            timeout=35,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"canonical current-main ledger download failed: {exc}") from exc
    body = result.stdout
    if result.returncode != 0 or not body or len(body) > MAX_LEDGER_BYTES:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[:240]
        raise ValueError(
            "canonical current-main ledger response is unsafe"
            + (f": {detail}" if detail else "")
        )
    return body


def sync_canonical_ledger(
    *,
    lifecycle_root: Path | None = None,
    ledger_path: Path | None = None,
    ledger_receipt_path: Path | None = None,
) -> dict[str, object]:
    """Install an exact, receipt-bound current-main ledger in the private plane."""
    if lifecycle_root is None:
        lifecycle_root = _state_root()
    else:
        _validate_private_root_location(
            lifecycle_root,
            label="private lifecycle state",
        )
        mark_chain._require_private_directory(lifecycle_root)
    ledger_path, ledger_receipt_path = _ledger_paths(
        lifecycle_root,
        ledger_path=ledger_path,
        ledger_receipt_path=ledger_receipt_path,
        create=True,
    )

    with mark_chain._private_ledger_lock(lifecycle_root):
        source_commit = _resolve_current_main_commit()
        body = _download_current_main_ledger(source_commit)
        rows = _ledger_rows(body)
        receipt = _ledger_receipt(body, rows, source_commit=source_commit)

        # A source refresh may only extend evidence already made durable.  This also
        # recovers safely from a crash between the two atomic file swaps: the durable
        # lifecycle cursor or activation marker remains the governing old prefix.
        state = _load_state(lifecycle_root)
        boundary = _load_activation_boundary(lifecycle_root)
        if state is not None:
            _verify_ledger_prefix(body, state["ledger_cursor"])
        elif boundary is not None:
            _verify_ledger_prefix(body, boundary["ledger_boundary"])

        existing: tuple[bytes, list[dict[str, object]], dict[str, object]] | None = None
        try:
            existing = _read_ledger_snapshot(ledger_path, ledger_receipt_path)
        except ValueError:
            # Missing/mismatched pair is a recoverable interrupted install.  Unsafe
            # paths/modes are still rejected by the atomic readback after replacement.
            existing = None
        if existing is not None:
            _verify_ledger_prefix(body, existing[2])
            if existing[0] == body and existing[2] == receipt:
                return {
                    "status": "unchanged",
                    "source_commit": source_commit,
                    "sha256": receipt["sha256"],
                    "row_count": receipt["row_count"],
                }

        _atomic_private_write(ledger_path, body, max_bytes=MAX_LEDGER_BYTES)
        _atomic_private_write(
            ledger_receipt_path,
            _canonical_json_bytes(receipt),
            max_bytes=MAX_RECEIPT_BYTES,
        )
        installed_body, installed_rows, installed_receipt = _read_ledger_snapshot(
            ledger_path,
            ledger_receipt_path,
        )
        if installed_body != body or installed_rows != rows or installed_receipt != receipt:
            raise ValueError("canonical current-main ledger install readback mismatch")
        return {
            "status": "installed",
            "source_commit": source_commit,
            "sha256": receipt["sha256"],
            "row_count": receipt["row_count"],
        }


def _activation_boundary_identity(boundary: dict[str, object]) -> str:
    identity = dict(boundary)
    identity.pop("boundary_id", None)
    return "poslab_" + sha256(_canonical_json_bytes(identity)).hexdigest()


def _validate_activation_boundary(boundary: object) -> dict[str, object]:
    required = {
        "schema",
        "boundary_id",
        "mark_boundary",
        "mark_boundary_observed_at_utc",
        "ledger_boundary",
    }
    if not isinstance(boundary, dict) or set(boundary) != required:
        raise ValueError("option shadow lifecycle activation boundary is malformed")
    boundary_id = boundary.get("boundary_id")
    if (
        boundary.get("schema") != ACTIVATION_BOUNDARY_SCHEMA
        or not isinstance(boundary_id, str)
        or not re.fullmatch(r"poslab_[a-f0-9]{64}", boundary_id)
        or boundary_id != _activation_boundary_identity(boundary)
    ):
        raise ValueError("option shadow lifecycle activation boundary identity is malformed")
    mark_chain._validate_pointer(boundary.get("mark_boundary"))
    observed = boundary.get("mark_boundary_observed_at_utc")
    if not isinstance(observed, str) or not observed:
        raise ValueError("option shadow lifecycle activation mark clock is malformed")
    _validate_ledger_receipt(boundary.get("ledger_boundary"))
    return deepcopy(boundary)


def _make_activation_boundary(
    *,
    mark_pointer: dict[str, object],
    mark_observation: dict[str, object],
    ledger_receipt: dict[str, object],
) -> dict[str, object]:
    boundary: dict[str, object] = {
        "schema": ACTIVATION_BOUNDARY_SCHEMA,
        "boundary_id": None,
        "mark_boundary": mark_pointer,
        "mark_boundary_observed_at_utc": mark_observation["observed_at_utc"],
        "ledger_boundary": ledger_receipt,
    }
    boundary["boundary_id"] = _activation_boundary_identity(boundary)
    return _validate_activation_boundary(boundary)


def _load_activation_boundary(root: Path) -> dict[str, object] | None:
    body = mark_chain._read_private_file(
        root / "activation_boundary.json", required=False
    )
    if body is None:
        return None
    try:
        boundary = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("option shadow lifecycle activation boundary is invalid JSON") from exc
    if not isinstance(boundary, dict) or _canonical_json_bytes(boundary) != body:
        raise ValueError("option shadow lifecycle activation boundary is not canonical JSON")
    return _validate_activation_boundary(boundary)


def _load_or_create_activation_boundary(
    *,
    lifecycle_root: Path,
    mark_root: Path,
    current_mark_pointer: dict[str, object],
    current_mark_observation: dict[str, object],
    ledger_body: bytes,
    ledger_receipt: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    boundary = _load_activation_boundary(lifecycle_root)
    if boundary is None:
        boundary = _make_activation_boundary(
            mark_pointer=current_mark_pointer,
            mark_observation=current_mark_observation,
            ledger_receipt=ledger_receipt,
        )
        # Validate the event that this marker will produce before the marker itself is
        # durable. The marker is the crash-stable transaction boundary, not a second
        # event format.
        _activation_event(
            mark_pointer=boundary["mark_boundary"],
            mark_observation=current_mark_observation,
            ledger_receipt=boundary["ledger_boundary"],
        )
        mark_chain._write_private_immutable(
            lifecycle_root / "activation_boundary.json",
            _canonical_json_bytes(boundary),
        )
        return boundary, current_mark_observation

    boundary_pointer = mark_chain._validate_pointer(boundary["mark_boundary"])
    boundary_observation = _load_mark_observation(mark_root, boundary_pointer)
    if boundary_observation.get("observed_at_utc") != boundary["mark_boundary_observed_at_utc"]:
        raise ValueError("option shadow lifecycle activation mark clock mismatch")
    _new_mark_observations(mark_root, current_mark_pointer, boundary_pointer)
    _verify_ledger_prefix(ledger_body, boundary["ledger_boundary"])
    return boundary, boundary_observation


def _state_identity(state: dict[str, object]) -> str:
    identity = dict(state)
    identity.pop("state_id", None)
    return "posls_" + sha256(_canonical_json_bytes(identity)).hexdigest()


def _validate_state_shape(state: object) -> dict[str, object]:
    required = {
        "schema",
        "state_id",
        "activation",
        "lifecycle_head",
        "mark_cursor",
        "ledger_cursor",
        "enrollments",
        "terminals",
        "latest_marks",
    }
    if not isinstance(state, dict) or set(state) != required:
        raise ValueError("option shadow lifecycle state shape is malformed")
    state_id = state.get("state_id")
    if (
        state.get("schema") != STATE_SCHEMA
        or not isinstance(state_id, str)
        or not _STATE_ID_RE.fullmatch(state_id)
        or state_id != _state_identity(state)
    ):
        raise ValueError("option shadow lifecycle state identity is malformed")
    _validate_event_pointer(state.get("activation"))
    _validate_event_pointer(state.get("lifecycle_head"))
    mark_chain._validate_pointer(state.get("mark_cursor"))
    _validate_ledger_receipt(state.get("ledger_cursor"))
    for key in ("enrollments", "terminals", "latest_marks"):
        if not isinstance(state.get(key), dict):
            raise ValueError(f"option shadow lifecycle state {key} is malformed")
    for mapping_name in ("enrollments", "terminals"):
        mapping = state[mapping_name]
        for plan_id, pointer in mapping.items():
            if not isinstance(plan_id, str) or not plan_id:
                raise ValueError(f"option shadow lifecycle {mapping_name} plan id is malformed")
            _validate_event_pointer(pointer)
    enrollments = set(state["enrollments"])
    terminals = set(state["terminals"])
    if not terminals <= enrollments:
        raise ValueError("terminal lifecycle state exists without enrollment")
    latest_marks = state["latest_marks"]
    if not set(latest_marks) <= enrollments - terminals:
        raise ValueError("latest mark state is outside the open enrolled cohort")
    for plan_id, details in latest_marks.items():
        if not isinstance(details, dict) or set(details) != {
            "contract_occ_symbol",
            "contract_drift",
            "sessions",
        }:
            raise ValueError(f"latest mark state for {plan_id} is malformed")
        occ = details.get("contract_occ_symbol")
        drift = details.get("contract_drift")
        sessions = details.get("sessions")
        if not isinstance(occ, str) or len(occ) != 21 or not isinstance(drift, bool):
            raise ValueError(f"latest mark contract state for {plan_id} is malformed")
        if not isinstance(sessions, dict):
            raise ValueError(f"latest mark session state for {plan_id} is malformed")
        for session_date, pointer in sessions.items():
            _parse_date(session_date, label=f"latest mark session for {plan_id}")
            mark_chain._validate_pointer(pointer)
    return deepcopy(state)


def _load_state(root: Path) -> dict[str, object] | None:
    body = mark_chain._read_private_file(root / "current.json", required=False)
    if body is None:
        return None
    try:
        state = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("option shadow lifecycle state is invalid JSON") from exc
    if not isinstance(state, dict) or _canonical_json_bytes(state) != body:
        raise ValueError("option shadow lifecycle state is not canonical JSON")
    return _validate_state_shape(state)


def _validate_event_chain(root: Path, state: dict[str, object]) -> None:
    pointer: dict[str, object] | None = _validate_event_pointer(state["lifecycle_head"])
    seen: set[str] = set()
    activation_pointer: dict[str, object] | None = None
    enrollments: dict[str, dict[str, object]] = {}
    terminals: dict[str, dict[str, object]] = {}
    for _ in range(MAX_CHAIN_DEPTH):
        if pointer is None:
            break
        event_id = str(pointer["event_id"])
        if event_id in seen:
            raise ValueError("option shadow lifecycle event chain contains a cycle")
        seen.add(event_id)
        event = _load_event(root, pointer)
        kind = event["event_kind"]
        payload = event["payload"]
        if kind == "activation_boundary":
            if activation_pointer is not None or event["previous"] is not None:
                raise ValueError("option shadow lifecycle activation is not the chain root")
            activation_pointer = pointer
        elif kind == "enrollment":
            plan_id = str(payload["plan"]["id"])
            if plan_id in enrollments:
                raise ValueError(f"duplicate lifecycle enrollment for {plan_id}")
            enrollments[plan_id] = pointer
        elif kind == "terminal":
            plan_id = str(payload["plan_id"])
            if plan_id in terminals:
                raise ValueError(f"duplicate lifecycle terminal for {plan_id}")
            terminals[plan_id] = pointer
        previous = event.get("previous")
        pointer = None if previous is None else _validate_event_pointer(previous)
    else:
        raise ValueError("option shadow lifecycle event chain exceeds safe depth")
    if activation_pointer is None or activation_pointer != state["activation"]:
        raise ValueError("option shadow lifecycle activation pointer mismatch")
    if enrollments != state["enrollments"] or terminals != state["terminals"]:
        raise ValueError("option shadow lifecycle state does not match its event chain")
    for plan_id, terminal_pointer in terminals.items():
        terminal = _load_event(root, terminal_pointer)
        if terminal["payload"]["enrollment_event"] != enrollments[plan_id]:
            raise ValueError(f"terminal lifecycle enrollment pointer mismatch for {plan_id}")


def _validate_activation_boundary_against_state(
    root: Path,
    state: dict[str, object],
) -> None:
    boundary = _load_activation_boundary(root)
    if boundary is None:
        raise ValueError("option shadow lifecycle activation boundary is missing")
    activation = _load_event(root, state["activation"])
    payload = activation["payload"]
    if (
        activation.get("event_kind") != "activation_boundary"
        or payload.get("mark_boundary") != boundary["mark_boundary"]
        or payload.get("mark_boundary_observed_at_utc")
        != boundary["mark_boundary_observed_at_utc"]
        or payload.get("ledger_boundary") != boundary["ledger_boundary"]
        or payload.get("prospective_after_boundary") is not True
    ):
        raise ValueError("option shadow lifecycle activation event disagrees with boundary")


def _mark_history_from_enrollment(
    *,
    mark_root: Path,
    enrollment: dict[str, object],
    head_pointer: dict[str, object],
) -> list[tuple[dict[str, object], dict[str, object]]]:
    entry_pointer = mark_chain._validate_pointer(
        enrollment["payload"]["mark_observation"]
    )
    entry_observation = _load_mark_observation(mark_root, entry_pointer)
    later = _new_mark_observations(mark_root, head_pointer, entry_pointer)
    return [(entry_pointer, entry_observation), *later]


def _reconstruct_admitted_marks(
    *,
    mark_root: Path,
    enrollment: dict[str, object],
    head_pointer: dict[str, object],
) -> tuple[dict[str, dict[str, object]], bool]:
    payload = enrollment["payload"]
    plan_id = str(payload["plan"]["id"])
    contract = payload["contract"]
    sessions: dict[str, dict[str, object]] = {}
    contract_drift = False
    for pointer, observation in _mark_history_from_enrollment(
        mark_root=mark_root,
        enrollment=enrollment,
        head_pointer=head_pointer,
    ):
        row = _optional_row_for_plan(observation, plan_id)
        if row is None:
            continue
        row_contract = row.get("contract")
        if isinstance(row_contract, dict) and row_contract != contract:
            contract_drift = True
        plan = row.get("plan")
        eligible = (
            isinstance(plan, dict)
            and plan.get("phase") in POST_TRIGGER_PHASES
            and row.get("quote_status") == "available"
            and isinstance(row.get("quote"), dict)
            and row_contract == contract
        )
        if eligible:
            sessions[str(observation["session_date"])] = pointer
    return sessions, contract_drift


def _validate_source_references(
    *,
    lifecycle_root: Path,
    mark_root: Path,
    state: dict[str, object],
    ledger_body: bytes,
    ledger_rows: list[dict[str, object]],
) -> None:
    activation = _load_event(lifecycle_root, state["activation"])
    activation_mark = activation["payload"]["mark_boundary"]
    _new_mark_observations(mark_root, state["mark_cursor"], activation_mark)

    enrollment_events: dict[str, dict[str, object]] = {}
    for plan_id, pointer in state["enrollments"].items():
        enrollment = _load_enrollment(lifecycle_root, pointer, plan_id)
        enrollment_events[plan_id] = enrollment
        payload = enrollment["payload"]
        mark_pointer = mark_chain._validate_pointer(payload["mark_observation"])
        _new_mark_observations(mark_root, mark_pointer, activation_mark)
        observation = _load_mark_observation(mark_root, mark_pointer)
        row = _row_for_plan(observation, plan_id)
        if (
            observation.get("session_date") != enrollment["event_session_date"]
            or _plan_from_mark_row(row) != payload["plan"]
            or row.get("contract") != payload["contract"]
            or row.get("quote_status") != "available"
            or row["plan"].get("phase") not in POST_TRIGGER_PHASES
            or payload["shadow_entry_mark"]
            != _shadow_mark(
                row,
                mark_pointer,
                basis="first_fresh_post_trigger_trade_paired_mid",
            )
        ):
            raise ValueError(f"lifecycle enrollment source mismatch for {plan_id}")

    for plan_id, details in state["latest_marks"].items():
        enrollment = enrollment_events[plan_id]
        sessions, drift = _reconstruct_admitted_marks(
            mark_root=mark_root,
            enrollment=enrollment,
            head_pointer=state["mark_cursor"],
        )
        if (
            details["contract_occ_symbol"]
            != enrollment["payload"]["contract"]["occ_symbol"]
            or details["contract_drift"] is not drift
            or details["sessions"] != sessions
        ):
            raise ValueError(f"latest admitted mark state mismatch for {plan_id}")

    for plan_id, pointer in state["terminals"].items():
        terminal = _load_event(lifecycle_root, pointer)
        payload = terminal["payload"]
        enrollment = enrollment_events[plan_id]
        if (
            payload["enrollment_event"] != state["enrollments"][plan_id]
            or payload["shadow_entry_mark"]
            != enrollment["payload"]["shadow_entry_mark"]
            or payload["contract"] != enrollment["payload"]["contract"]
        ):
            raise ValueError(f"terminal enrollment evidence mismatch for {plan_id}")

        close = payload["canonical_close"]
        receipt = _verify_ledger_prefix(ledger_body, close["ledger_receipt"])
        ordinal = close["row_ordinal"]
        if (
            not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or ordinal < 1
            or ordinal > int(receipt["row_count"])
            or ordinal > len(ledger_rows)
        ):
            raise ValueError(f"terminal canonical row ordinal mismatch for {plan_id}")
        source_row = ledger_rows[ordinal - 1]
        if (
            sha256(_canonical_json_bytes(source_row)).hexdigest()
            != close["row_semantic_sha256"]
            or close["schema"] != source_row["schema"]
            or not (close["plan_id"] == source_row["id"] == plan_id)
            or close["close_date"] != source_row["close_date"]
            or close["outcome"] != source_row["outcome"]
            or close["asof"] != source_row["asof"]
            or source_row.get("option_result_pct") is not None
        ):
            raise ValueError(f"terminal canonical close mismatch for {plan_id}")

        terminal_head = mark_chain._validate_pointer(payload["mark_chain_head"])
        _new_mark_observations(mark_root, state["mark_cursor"], terminal_head)
        sessions, drift = _reconstruct_admitted_marks(
            mark_root=mark_root,
            enrollment=enrollment,
            head_pointer=terminal_head,
        )
        close_date = str(close["close_date"])
        enrollment_date = str(enrollment["event_session_date"])
        if source_row["outcome"] == "NO_ENTRY":
            expected_reason = "CANONICAL_NO_ENTRY"
            expected_pointer = None
        elif close_date < enrollment_date:
            expected_reason = "CANONICAL_CLOSE_PREDATES_ENROLLMENT"
            expected_pointer = None
        elif drift:
            expected_reason = "CONTRACT_DRIFT"
            expected_pointer = None
        else:
            expected_pointer = sessions.get(close_date)
            expected_reason = (
                None if expected_pointer is not None else "NO_SAME_SESSION_ADMITTED_MARK"
            )

        terminal_mark = payload["terminal_mark"]
        shadow_return = payload["shadow_return"]
        if expected_pointer is None:
            if (
                terminal_mark
                != {"status": "unavailable", "reason": expected_reason, "mark": None}
                or shadow_return
                != {
                    "status": "unavailable",
                    "basis": "shadow_mid_to_mid_research_only",
                    "shadow_mark_to_mark_return_pct": None,
                    "unavailable_reason": expected_reason,
                    "trade_pnl": False,
                }
            ):
                raise ValueError(f"terminal unavailable receipt mismatch for {plan_id}")
            continue

        expected_observation = _load_mark_observation(mark_root, expected_pointer)
        expected_row = _row_for_plan(expected_observation, plan_id)
        expected_mark = _shadow_mark(
            expected_row,
            expected_pointer,
            basis="latest_admitted_same_session_trade_paired_mid",
        )
        entry = Decimal(str(enrollment["payload"]["shadow_entry_mark"]["mid"]))
        terminal_mid = Decimal(str(expected_mark["mid"]))
        expected_return = float(
            (((terminal_mid / entry) - Decimal("1")) * Decimal("100")).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        )
        if (
            terminal_mark
            != {"status": "available", "reason": None, "mark": expected_mark}
            or shadow_return
            != {
                "status": "available",
                "basis": "shadow_mid_to_mid_research_only",
                "shadow_mark_to_mark_return_pct": expected_return,
                "unavailable_reason": None,
                "trade_pnl": False,
            }
        ):
            raise ValueError(f"terminal shadow return mismatch for {plan_id}")


def _make_state(
    *,
    activation: dict[str, object],
    lifecycle_head: dict[str, object],
    mark_cursor: dict[str, object],
    ledger_cursor: dict[str, object],
    enrollments: dict[str, dict[str, object]],
    terminals: dict[str, dict[str, object]],
    latest_marks: dict[str, dict[str, object]],
) -> dict[str, object]:
    state: dict[str, object] = {
        "schema": STATE_SCHEMA,
        "state_id": None,
        "activation": activation,
        "lifecycle_head": lifecycle_head,
        "mark_cursor": mark_cursor,
        "ledger_cursor": ledger_cursor,
        "enrollments": enrollments,
        "terminals": terminals,
        "latest_marks": latest_marks,
    }
    state["state_id"] = _state_identity(state)
    return _validate_state_shape(state)


def _make_event(
    *,
    kind: str,
    session_date: str,
    payload: dict[str, object],
    previous: dict[str, object] | None,
) -> dict[str, object]:
    _parse_date(session_date, label="option shadow lifecycle event session")
    event: dict[str, object] = {
        "schema": EVENT_SCHEMA,
        "event_id": None,
        "event_kind": kind,
        "event_session_date": session_date,
        "storage": {
            "visibility": "host_private",
            "public_discovery": False,
            "public_redistribution": False,
        },
        "previous": previous,
        "payload": payload,
        "limitations": _limitations_block(),
        "authority": _authority_block(),
    }
    identity = dict(event)
    identity.pop("event_id")
    event["event_id"] = "posle_" + sha256(_canonical_json_bytes(identity)).hexdigest()
    _validate_event_schema(event)
    _event_pointer(event)
    return event


def _write_events(
    root: Path,
    events: list[dict[str, object]],
) -> None:
    # Every event is schema-validated before the first durable write.  A retry after a
    # crash regenerates byte-identical events from source pointers, so O_EXCL readback
    # safely adopts the already-written prefix rather than minting a parallel history.
    for event in events:
        _validate_event_schema(event)
    for event in events:
        pointer = _event_pointer(event)
        mark_chain._write_private_immutable(
            _event_path(root, pointer, create_parents=True),
            _canonical_json_bytes(event),
        )


def _write_state(root: Path, state: dict[str, object]) -> None:
    checked = _validate_state_shape(state)
    mark_chain._write_private_head(root, _canonical_json_bytes(checked))


def _activation_event(
    *,
    mark_pointer: dict[str, object],
    mark_observation: dict[str, object],
    ledger_receipt: dict[str, object],
) -> dict[str, object]:
    return _make_event(
        kind="activation_boundary",
        session_date=str(mark_observation["session_date"]),
        previous=None,
        payload={
            "kind": "activation_boundary",
            "mark_boundary": mark_pointer,
            "mark_boundary_observed_at_utc": mark_observation["observed_at_utc"],
            "ledger_boundary": ledger_receipt,
            "prospective_after_boundary": True,
        },
    )


def _plan_from_mark_row(row: dict[str, object]) -> dict[str, object]:
    plan = row.get("plan")
    if not isinstance(plan, dict):
        raise ValueError("option mark row plan is malformed")
    return {
        "id": plan["id"],
        "asset": plan["asset"],
        "phase": plan["phase"],
        "plan_asof": plan["plan_asof"],
        "recorded_at": plan["recorded_at"],
        "entry_date": plan["entry_date"],
    }


def _shadow_mark(
    row: dict[str, object],
    observation_pointer: dict[str, object],
    *,
    basis: str,
) -> dict[str, object]:
    quote = row.get("quote")
    if row.get("quote_status") != "available" or not isinstance(quote, dict):
        raise ValueError("fresh option mark is unavailable")
    values = [quote.get("bid"), quote.get("ask"), quote.get("mid")]
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in values
    ):
        raise ValueError("fresh option mark contains a non-finite value")
    return {
        "bid": quote["bid"],
        "ask": quote["ask"],
        "mid": quote["mid"],
        "basis": basis,
        "quote_label": quote["label"],
        "quote_ts_utc": quote["quote_ts_utc"],
        "trade_ts_utc": quote["trade_ts_utc"],
        "source_sequence": quote["source_sequence"],
        "mark_observation": observation_pointer,
        "nbbo": False,
        "executable": False,
        "fill": False,
    }


def _enrollment_event(
    *,
    row: dict[str, object],
    mark_pointer: dict[str, object],
    mark_observation: dict[str, object],
    previous: dict[str, object],
) -> dict[str, object]:
    plan = _plan_from_mark_row(row)
    if plan["phase"] not in POST_TRIGGER_PHASES:
        raise ValueError("option lifecycle enrollment is not post-trigger")
    contract = row.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("option lifecycle enrollment contract is unavailable")
    return _make_event(
        kind="enrollment",
        session_date=str(mark_observation["session_date"]),
        previous=previous,
        payload={
            "kind": "enrollment",
            "plan": plan,
            "contract": dict(contract),
            "mark_observation": mark_pointer,
            "shadow_entry_mark": _shadow_mark(
                row,
                mark_pointer,
                basis="first_fresh_post_trigger_trade_paired_mid",
            ),
            "position_assumed": False,
            "provider_observed_entry": False,
        },
    )


def _row_for_plan(
    observation: dict[str, object],
    plan_id: str,
) -> dict[str, object]:
    match = _optional_row_for_plan(observation, plan_id)
    if match is None:
        raise ValueError(f"option mark observation does not identify {plan_id}")
    return match


def _optional_row_for_plan(
    observation: dict[str, object],
    plan_id: str,
) -> dict[str, object] | None:
    rows = observation.get("rows")
    if not isinstance(rows, list):
        raise ValueError("option mark observation rows are malformed")
    matches = [
        row
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("plan"), dict)
        and row["plan"].get("id") == plan_id
    ]
    if len(matches) > 1:
        raise ValueError(f"option mark observation repeats {plan_id}")
    return matches[0] if matches else None


def _load_enrollment(
    root: Path,
    pointer: dict[str, object],
    plan_id: str,
) -> dict[str, object]:
    event = _load_event(root, pointer)
    if (
        event.get("event_kind") != "enrollment"
        or event["payload"]["plan"]["id"] != plan_id
    ):
        raise ValueError(f"lifecycle enrollment pointer is wrong for {plan_id}")
    return event


def _terminal_event(
    *,
    lifecycle_root: Path,
    mark_root: Path,
    plan_id: str,
    ledger_row: dict[str, object],
    ledger_row_ordinal: int,
    ledger_receipt: dict[str, object],
    enrollment_pointer: dict[str, object],
    enrollment_event: dict[str, object] | None,
    mark_chain_head: dict[str, object],
    latest_state: dict[str, object],
    previous: dict[str, object],
) -> dict[str, object]:
    enrollment = enrollment_event or _load_enrollment(
        lifecycle_root, enrollment_pointer, plan_id
    )
    if (
        enrollment.get("event_kind") != "enrollment"
        or enrollment["payload"]["plan"]["id"] != plan_id
        or _event_pointer(enrollment) != enrollment_pointer
    ):
        raise ValueError(f"lifecycle enrollment object is wrong for {plan_id}")
    enrollment_payload = enrollment["payload"]
    close_date = str(ledger_row["close_date"])
    enrollment_session = str(enrollment["event_session_date"])
    reason: str | None = None
    terminal_mark: dict[str, object] | None = None

    if ledger_row["outcome"] == "NO_ENTRY":
        reason = "CANONICAL_NO_ENTRY"
    elif date.fromisoformat(close_date) < date.fromisoformat(enrollment_session):
        reason = "CANONICAL_CLOSE_PREDATES_ENROLLMENT"
    elif latest_state.get("contract_drift") is True:
        reason = "CONTRACT_DRIFT"
    else:
        sessions = latest_state.get("sessions")
        mark_pointer = sessions.get(close_date) if isinstance(sessions, dict) else None
        if mark_pointer is None:
            reason = "NO_SAME_SESSION_ADMITTED_MARK"
        else:
            mark_pointer = mark_chain._validate_pointer(mark_pointer)
            observation = _load_mark_observation(mark_root, mark_pointer)
            row = _row_for_plan(observation, plan_id)
            if row.get("contract") != enrollment_payload["contract"]:
                reason = "CONTRACT_DRIFT"
            elif observation.get("session_date") != close_date:
                raise ValueError("terminal mark reference is not from the close session")
            else:
                terminal_mark = _shadow_mark(
                    row,
                    mark_pointer,
                    basis="latest_admitted_same_session_trade_paired_mid",
                )

    if reason is not None and reason not in UNAVAILABLE_REASONS:
        raise ValueError("unknown lifecycle terminal unavailable reason")

    entry_mark = enrollment_payload["shadow_entry_mark"]
    if terminal_mark is None:
        terminal_wrapper: dict[str, object] = {
            "status": "unavailable",
            "reason": reason,
            "mark": None,
        }
        shadow_return: dict[str, object] = {
            "status": "unavailable",
            "basis": "shadow_mid_to_mid_research_only",
            "shadow_mark_to_mark_return_pct": None,
            "unavailable_reason": reason,
            "trade_pnl": False,
        }
    else:
        entry = Decimal(str(entry_mark["mid"]))
        terminal = Decimal(str(terminal_mark["mid"]))
        if entry <= 0 or terminal <= 0:
            raise ValueError("shadow lifecycle mark is non-positive")
        value = ((terminal / entry) - Decimal("1")) * Decimal("100")
        rounded = float(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        terminal_wrapper = {
            "status": "available",
            "reason": None,
            "mark": terminal_mark,
        }
        shadow_return = {
            "status": "available",
            "basis": "shadow_mid_to_mid_research_only",
            "shadow_mark_to_mark_return_pct": rounded,
            "unavailable_reason": None,
            "trade_pnl": False,
        }

    canonical_close = {
        "schema": "prophet.ledger/v1",
        "plan_id": plan_id,
        "close_date": close_date,
        "outcome": ledger_row["outcome"],
        "asof": ledger_row["asof"],
        "row_ordinal": ledger_row_ordinal,
        "row_semantic_sha256": sha256(_canonical_json_bytes(ledger_row)).hexdigest(),
        "ledger_receipt": ledger_receipt,
        "source_option_result_pct_was_null": True,
    }
    return _make_event(
        kind="terminal",
        session_date=close_date,
        previous=previous,
        payload={
            "kind": "terminal",
            "plan_id": plan_id,
            "contract": enrollment_payload["contract"],
            "enrollment_event": enrollment_pointer,
            "mark_chain_head": mark_chain_head,
            "shadow_entry_mark": entry_mark,
            "canonical_close": canonical_close,
            "terminal_mark": terminal_wrapper,
            "shadow_return": shadow_return,
            "position_assumed": False,
            "provider_observed_exit": False,
        },
    )


def _activation_state(
    *,
    lifecycle_root: Path,
    mark_root: Path,
    mark_pointer: dict[str, object],
    mark_observation: dict[str, object],
    ledger_body: bytes,
    ledger_rows: list[dict[str, object]],
    ledger_receipt: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    event = _activation_event(
        mark_pointer=mark_pointer,
        mark_observation=mark_observation,
        ledger_receipt=ledger_receipt,
    )
    pointer = _event_pointer(event)
    state = _make_state(
        activation=pointer,
        lifecycle_head=pointer,
        mark_cursor=mark_pointer,
        ledger_cursor=ledger_receipt,
        enrollments={},
        terminals={},
        latest_marks={},
    )
    _write_events(lifecycle_root, [event])
    _validate_event_chain(lifecycle_root, state)
    _validate_activation_boundary_against_state(lifecycle_root, state)
    _validate_source_references(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        state=state,
        ledger_body=ledger_body,
        ledger_rows=ledger_rows,
    )
    _write_state(lifecycle_root, state)
    if _load_state(lifecycle_root) != state:
        raise ValueError("option shadow lifecycle activation state readback mismatch")
    return state, [event]


def advance_lifecycle(
    *,
    lifecycle_root: Path | None = None,
    mark_root: Path | None = None,
    ledger_path: Path | None = None,
    ledger_receipt_path: Path | None = None,
) -> dict[str, object]:
    """Advance lifecycle state once; fail closed before advancing any cursor."""
    if lifecycle_root is None:
        lifecycle_root = _state_root()
    else:
        _validate_private_root_location(
            lifecycle_root, label="private lifecycle state"
        )
        mark_chain._require_private_directory(lifecycle_root)
    if mark_root is None:
        mark_root = _mark_root()
    else:
        _validate_private_root_location(
            mark_root, label="private option mark evidence"
        )
        mark_chain._require_private_directory(mark_root)
    ledger_path, ledger_receipt_path = _ledger_paths(
        lifecycle_root,
        ledger_path=ledger_path,
        ledger_receipt_path=ledger_receipt_path,
        create=False,
    )

    with mark_chain._private_ledger_lock(lifecycle_root):
        current_mark_pointer, current_mark = _mark_head(mark_root)
        ledger_body, rows, ledger_receipt = _read_ledger_snapshot(
            ledger_path,
            ledger_receipt_path,
        )
        state = _load_state(lifecycle_root)

        if state is None:
            boundary, boundary_observation = _load_or_create_activation_boundary(
                lifecycle_root=lifecycle_root,
                mark_root=mark_root,
                current_mark_pointer=current_mark_pointer,
                current_mark_observation=current_mark,
                ledger_body=ledger_body,
                ledger_receipt=ledger_receipt,
            )
            state, events = _activation_state(
                lifecycle_root=lifecycle_root,
                mark_root=mark_root,
                mark_pointer=boundary["mark_boundary"],
                mark_observation=boundary_observation,
                ledger_body=ledger_body,
                ledger_rows=rows,
                ledger_receipt=boundary["ledger_boundary"],
            )
            return {
                "status": "activated",
                "event_count": len(events),
                "enrollment_count": 0,
                "terminal_count": 0,
                "state_id": state["state_id"],
                "lifecycle_head": state["lifecycle_head"]["event_id"],
                "mark_cursor": state["mark_cursor"]["observation_id"],
                "ledger_row_count": state["ledger_cursor"]["row_count"],
            }

        _validate_event_chain(lifecycle_root, state)
        _validate_activation_boundary_against_state(lifecycle_root, state)
        _validate_source_references(
            lifecycle_root=lifecycle_root,
            mark_root=mark_root,
            state=state,
            ledger_body=ledger_body,
            ledger_rows=rows,
        )
        old_ledger_cursor = _verify_ledger_prefix(ledger_body, state["ledger_cursor"])
        if len(rows) < int(old_ledger_cursor["row_count"]):
            raise ValueError("canonical Prophet ledger row count moved backwards")
        new_marks = _new_mark_observations(
            mark_root,
            current_mark_pointer,
            state["mark_cursor"],
        )
        new_ledger_rows = list(
            enumerate(rows[int(old_ledger_cursor["row_count"]):], start=int(old_ledger_cursor["row_count"]) + 1)
        )
        previously_closed_ids = {
            str(row["id"])
            for row in rows[: int(old_ledger_cursor["row_count"])]
        }
        current_closes = {
            str(row["id"]): str(row["close_date"])
            for row in rows[int(old_ledger_cursor["row_count"]):]
        }
        all_closed_ids = previously_closed_ids | set(current_closes)

        enrollments = deepcopy(state["enrollments"])
        durable_enrollment_ids = set(enrollments)
        terminals = deepcopy(state["terminals"])
        latest_marks = deepcopy(state["latest_marks"])
        lifecycle_head = _validate_event_pointer(state["lifecycle_head"])
        events: list[dict[str, object]] = []
        pending_enrollments: dict[str, dict[str, object]] = {}

        for mark_pointer, observation in new_marks:
            observation_rows = observation.get("rows")
            if not isinstance(observation_rows, list):
                raise ValueError("option mark observation rows are malformed")
            ordered_rows = sorted(
                (row for row in observation_rows if isinstance(row, dict)),
                key=lambda row: str((row.get("plan") or {}).get("id") or ""),
            )
            for row in ordered_rows:
                plan = row.get("plan")
                contract = row.get("contract")
                if not isinstance(plan, dict):
                    raise ValueError("option mark observation plan row is malformed")
                plan_id = str(plan.get("id") or "")
                if not plan_id:
                    raise ValueError("option mark observation plan id is missing")
                if plan_id in terminals:
                    continue
                if plan_id in enrollments and isinstance(contract, dict):
                    enrolled = pending_enrollments.get(plan_id) or _load_enrollment(
                        lifecycle_root,
                        enrollments[plan_id],
                        plan_id,
                    )
                    if contract != enrolled["payload"]["contract"]:
                        latest_marks[plan_id]["contract_drift"] = True
                close_date = current_closes.get(plan_id)
                eligible = (
                    (plan_id in enrollments or plan_id not in all_closed_ids)
                    and (
                        close_date is None
                        or str(observation["session_date"]) <= close_date
                    )
                    and plan.get("phase") in POST_TRIGGER_PHASES
                    and row.get("quote_status") == "available"
                    and isinstance(row.get("quote"), dict)
                    and isinstance(contract, dict)
                )
                if not eligible:
                    continue
                if plan_id not in enrollments:
                    event = _enrollment_event(
                        row=row,
                        mark_pointer=mark_pointer,
                        mark_observation=observation,
                        previous=lifecycle_head,
                    )
                    event_pointer = _event_pointer(event)
                    events.append(event)
                    lifecycle_head = event_pointer
                    enrollments[plan_id] = event_pointer
                    pending_enrollments[plan_id] = event
                    latest_marks[plan_id] = {
                        "contract_occ_symbol": contract["occ_symbol"],
                        "contract_drift": False,
                        "sessions": {},
                    }
                enrolled = pending_enrollments.get(plan_id) or _load_enrollment(
                    lifecycle_root,
                    enrollments[plan_id],
                    plan_id,
                )
                if contract != enrolled["payload"]["contract"]:
                    latest_marks[plan_id]["contract_drift"] = True
                    continue
                latest_marks[plan_id]["sessions"][
                    str(observation["session_date"])
                ] = mark_pointer

        for ordinal, ledger_row in new_ledger_rows:
            plan_id = str(ledger_row["id"])
            if plan_id not in durable_enrollment_ids or plan_id in terminals:
                continue
            event = _terminal_event(
                lifecycle_root=lifecycle_root,
                mark_root=mark_root,
                plan_id=plan_id,
                ledger_row=ledger_row,
                ledger_row_ordinal=ordinal,
                ledger_receipt=ledger_receipt,
                enrollment_pointer=enrollments[plan_id],
                enrollment_event=pending_enrollments.get(plan_id),
                mark_chain_head=current_mark_pointer,
                latest_state=latest_marks[plan_id],
                previous=lifecycle_head,
            )
            event_pointer = _event_pointer(event)
            events.append(event)
            lifecycle_head = event_pointer
            terminals[plan_id] = event_pointer
            latest_marks.pop(plan_id, None)

        candidate = _make_state(
            activation=state["activation"],
            lifecycle_head=lifecycle_head,
            mark_cursor=current_mark_pointer,
            ledger_cursor=ledger_receipt,
            enrollments=enrollments,
            terminals=terminals,
            latest_marks=latest_marks,
        )

        if candidate == state:
            return {
                "status": "unchanged",
                "event_count": 0,
                "enrollment_count": 0,
                "terminal_count": 0,
                "state_id": state["state_id"],
                "lifecycle_head": state["lifecycle_head"]["event_id"],
                "mark_cursor": state["mark_cursor"]["observation_id"],
                "ledger_row_count": ledger_receipt["row_count"],
            }

        # Validate every candidate event and the complete state before the first write.
        for event in events:
            _validate_event_schema(event)
        _validate_state_shape(candidate)
        _write_events(lifecycle_root, events)
        _validate_event_chain(lifecycle_root, candidate)
        _validate_source_references(
            lifecycle_root=lifecycle_root,
            mark_root=mark_root,
            state=candidate,
            ledger_body=ledger_body,
            ledger_rows=rows,
        )
        _write_state(lifecycle_root, candidate)
        if _load_state(lifecycle_root) != candidate:
            raise ValueError("option shadow lifecycle state readback mismatch")

        return {
            "status": "advanced",
            "event_count": len(events),
            "enrollment_count": sum(
                event["event_kind"] == "enrollment" for event in events
            ),
            "terminal_count": sum(
                event["event_kind"] == "terminal" for event in events
            ),
            "state_id": candidate["state_id"],
            "lifecycle_head": candidate["lifecycle_head"]["event_id"],
            "mark_cursor": candidate["mark_cursor"]["observation_id"],
            "ledger_row_count": ledger_receipt["row_count"],
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Advance host-private Prophet exact-option shadow lifecycles"
    )
    parser.add_argument(
        "--advance",
        action="store_true",
        help="advance the private prospective lifecycle once",
    )
    parser.add_argument(
        "--sync-current-main-ledger",
        action="store_true",
        help=(
            "resolve origin main, install its exact canonical Prophet ledger and "
            "write a private source receipt before any requested advancement"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.advance and not args.sync_current_main_ledger:
        _parser().print_help()
        return 2
    try:
        sync_summary = None
        if args.sync_current_main_ledger:
            sync_summary = sync_canonical_ledger()
        if args.advance:
            # Production CLI advancement is never permitted to skip the exact-main
            # refresh.  Python callers can still inject a receipt-bound fixture.
            if not args.sync_current_main_ledger:
                raise ValueError(
                    "CLI advancement requires --sync-current-main-ledger"
                )
            summary = advance_lifecycle()
        else:
            summary = None
    except Exception as exc:  # noqa: BLE001
        log.error("prophet option shadow lifecycle refused advancement: %s", exc)
        return 1
    if sync_summary is not None:
        log.info(
            "canonical Prophet ledger: status=%s commit=%s rows=%s sha256=%s",
            sync_summary["status"],
            sync_summary["source_commit"],
            sync_summary["row_count"],
            sync_summary["sha256"],
        )
    if summary is not None:
        log.info(
            "prophet option shadow lifecycle: status=%s events=%s enrollments=%s "
            "terminals=%s head=%s",
            summary["status"],
            summary["event_count"],
            summary["enrollment_count"],
            summary["terminal_count"],
            summary["lifecycle_head"],
        )
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    raise SystemExit(main())
