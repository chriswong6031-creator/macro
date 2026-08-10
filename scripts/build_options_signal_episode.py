"""Nightly options signal-episode and separately matured outcome accrual.

Discovers every retained date-keyed ``live_flow/events/{DATE}.jsonl`` stage from
R2, verifies its append-only prefix checkpoint, freezes exact decision episodes,
and accrues explicitly labeled aligned-bar proxies from the existing Polygon
hourly cache. The capped cumulative ``feed_current`` is never a learning source.
Desired event H+60, EOD, and 1/3/5/10-session targets remain separate clocks;
coarse session measurements are not training labels. The live poller writes raw
R2 facts; this nightly builder is the sole advancer of the committed split ledgers.

The durable stage's notable events are recorded as ``watch`` episodes. They are
not promoted into picks, and the option outcome stays null until a future source
provides a complete executable bid/ask quote path.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import logging
import os
import re
import sys
import tempfile
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.ledger_lane import nightly_advance_enabled
from engine.options_signal_episode import (
    EPISODE_REL,
    OUTCOME_REL,
    PRICE_BASIS,
    PRICE_RECEIPT_SCHEMA,
    SESSION_HORIZONS,
    SESSION_OUTCOME_REL,
    TIMESTAMP_BASIS,
    ContractError,
    append_episodes,
    append_outcomes,
    append_session_outcomes,
    derive_h60_outcome,
    derive_session_outcome,
    episode_from_live_event,
    load_jsonl,
    normalize_price_bars,
    validate_episode,
    validate_outcome,
    validate_outcome_against_episode,
    validate_session_outcome,
    validate_session_outcome_against_episode,
)
from engine.session_digest import ET
from lib import config, nyse_calendar

log = logging.getLogger("build_options_signal_episode")

PUBLIC_BASE = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"
EVENT_STAGE_SCHEMA = "live_flow.event_stage/v1"
CHECKPOINT_REL = Path("options_signal_episode") / "checkpoint.json"
MAX_DISCOVERED_SESSIONS = 64
_EVENT_KEY_RE = re.compile(r"^live_flow/events/(\d{4}-\d{2}-\d{2})\.jsonl$")


def _reject_duplicate_object_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON object key {key!r}")
        obj[key] = value
    return obj


def _strict_json_loads(value):
    return json.loads(
        value,
        object_pairs_hook=_reject_duplicate_object_pairs,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant {token}")
        ),
    )


def _r2_client():
    endpoint = os.environ.get("R2_ENDPOINT")
    key_id = os.environ.get("R2_ACCESS_KEY_ID")
    secret = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (endpoint and key_id and secret):
        return None
    try:
        import boto3
        return boto3.client(
            "s3", endpoint_url=endpoint,
            aws_access_key_id=key_id, aws_secret_access_key=secret,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("options signal episode: R2 client unavailable (%s)", exc)
        return None


def fetch_event_stage(session_date: str) -> list[dict[str, Any]] | None:
    """Fetch the append-only date-keyed learning source; never use feed_current rows."""
    key = f"live_flow/events/{session_date}.jsonl"
    client = _r2_client()
    bucket = os.environ.get("R2_BUCKET", "")
    try:
        if client is not None and bucket:
            raw = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        else:
            req = urllib.request.Request(
                f"{PUBLIC_BASE}/{key}",
                headers={"User-Agent": "mastermind-options-episode/1.0"},
            )
            with urllib.request.urlopen(req, timeout=20) as response:  # noqa: S310
                raw = response.read()
    except Exception as exc:  # noqa: BLE001
        log.warning("options signal episode: dated event stage unavailable (%s)", exc)
        return None
    if raw and not raw.endswith(b"\n"):
        raise ContractError("dated event stage has a torn final line")
    records: list[dict[str, Any]] = []
    for lineno, line in enumerate(raw.splitlines(), start=1):
        try:
            row = _strict_json_loads(line)
        except Exception as exc:  # noqa: BLE001
            raise ContractError(f"dated event stage malformed at line {lineno}") from exc
        if not isinstance(row, dict):
            raise ContractError(f"dated event stage line {lineno} is not an object")
        records.append(row)
    return records


def _validate_event_dates_index(payload: object) -> list[str]:
    if not isinstance(payload, dict) or set(payload) != {"schema", "sessions"}:
        raise ContractError("event-stage dates index envelope is invalid")
    if payload.get("schema") != "live_flow.event_dates/v1":
        raise ContractError("event-stage dates index schema is invalid")
    values = payload.get("sessions")
    if not isinstance(values, list) or len(values) > MAX_DISCOVERED_SESSIONS:
        raise ContractError("event-stage dates index sessions are invalid")
    sessions: list[str] = []
    for value in values:
        if type(value) is not str:
            raise ContractError("event-stage dates index contains a non-string session")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ContractError("event-stage dates index contains an invalid session") from exc
        if parsed.isoformat() != value or not nyse_calendar.is_session(parsed):
            raise ContractError("event-stage dates index contains an invalid NYSE session")
        sessions.append(value)
    if sessions != sorted(sessions) or len(sessions) != len(set(sessions)):
        raise ContractError("event-stage dates index must be sorted and unique")
    return sessions


def discover_event_sessions() -> list[str]:
    """Bounded retained-session discovery, credentialed listing then public index."""
    client = _r2_client()
    bucket = os.environ.get("R2_BUCKET", "")
    sessions: set[str] = set()
    if client is not None and bucket:
        token = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": bucket,
                "Prefix": "live_flow/events/",
                "MaxKeys": 1000,
            }
            if token:
                kwargs["ContinuationToken"] = token
            page = client.list_objects_v2(**kwargs)
            for item in page.get("Contents") or []:
                match = _EVENT_KEY_RE.match(str(item.get("Key") or ""))
                if match:
                    session_text = match.group(1)
                    try:
                        parsed_session = date.fromisoformat(session_text)
                    except ValueError as exc:
                        raise ContractError(
                            f"R2 event-stage key has an invalid session: {session_text}"
                        ) from exc
                    if (
                        parsed_session.isoformat() != session_text
                        or not nyse_calendar.is_session(parsed_session)
                    ):
                        raise ContractError(
                            f"R2 event-stage key has an invalid NYSE session: {session_text}"
                        )
                    sessions.add(session_text)
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")
            if not token:
                raise ContractError("R2 event-stage listing truncated without continuation token")
    else:
        try:
            req = urllib.request.Request(
                f"{PUBLIC_BASE}/live_flow/events/dates.json",
                headers={"User-Agent": "mastermind-options-episode/1.0"},
            )
            with urllib.request.urlopen(req, timeout=20) as response:  # noqa: S310
                raw_index = response.read()
        except Exception as exc:  # noqa: BLE001
            log.warning("options signal episode: event-stage dates index unavailable (%s)", exc)
            return []
        try:
            index = _strict_json_loads(raw_index)
        except Exception as exc:  # noqa: BLE001
            raise ContractError("event-stage dates index is malformed") from exc
        sessions.update(_validate_event_dates_index(index))
    ordered = sorted(sessions)
    if len(ordered) > MAX_DISCOVERED_SESSIONS:
        ordered = ordered[-MAX_DISCOVERED_SESSIONS:]
    return ordered


def _events_from_stage(
    records: list[dict[str, Any]], *, expected_session_date: str,
) -> list[dict[str, Any]]:
    if not records:
        raise ContractError("empty dated event stage")
    decisions: dict[str, dict[str, Any]] = {}
    availability: dict[str, str] = {}
    for lineno, record in enumerate(records, start=1):
        if record.get("schema") != EVENT_STAGE_SCHEMA:
            raise ContractError(f"wrong dated event-stage schema at line {lineno}")
        raw_event_id = record.get("event_id")
        if (
            type(raw_event_id) is not str
            or not raw_event_id
            or raw_event_id != raw_event_id.strip()
        ):
            raise ContractError(f"invalid event id at line {lineno}")
        event_id = raw_event_id
        kind = record.get("kind")
        if kind == "decision":
            if set(record) != {"schema", "kind", "event_id", "event"}:
                raise ContractError(f"invalid decision receipt shape at line {lineno}")
            if event_id in decisions or event_id in availability:
                raise ContractError(f"duplicate staged decision {event_id}")
            event = record.get("event")
            if (
                not isinstance(event, dict)
                or type(event.get("id")) is not str
                or event.get("id") != event_id
            ):
                raise ContractError(f"invalid decision receipt at line {lineno}")
            if {
                "available_at", "published_at", "source_snapshot_asof", "anchor_strategy",
            }.intersection(event):
                raise ContractError(
                    f"decision receipt contains non-durable fields at line {lineno}"
                )
            try:
                event_dt = datetime.fromisoformat(
                    str(event.get("ts") or "").replace("Z", "+00:00")
                )
            except (TypeError, ValueError) as exc:
                raise ContractError(f"invalid event timestamp at line {lineno}") from exc
            if event_dt.tzinfo is None:
                raise ContractError(f"event timestamp lacks timezone at line {lineno}")
            event_session = event_dt.astimezone(ET).date().isoformat()
            if event_session != expected_session_date:
                raise ContractError(
                    f"event-stage key/session mismatch at line {lineno}: "
                    f"key={expected_session_date} event={event_session}"
                )
            decisions[event_id] = event
        elif kind == "availability":
            if set(record) != {"schema", "kind", "event_id", "available_at"}:
                raise ContractError(f"invalid availability receipt shape at line {lineno}")
            if event_id not in decisions:
                raise ContractError(
                    f"availability receipt precedes its decision at line {lineno}"
                )
            if event_id in availability:
                raise ContractError(f"duplicate staged availability {event_id}")
            stamp = str(record.get("available_at") or "")
            if not stamp:
                raise ContractError(f"invalid availability receipt at line {lineno}")
            availability[event_id] = stamp
        else:
            raise ContractError(f"unknown event-stage receipt at line {lineno}")
    missing_availability = set(decisions) - set(availability)
    if missing_availability:
        raise ContractError(
            f"decision receipts lack durable availability: {sorted(missing_availability)}"
        )
    out: list[dict[str, Any]] = []
    for event_id, event in decisions.items():
        stamp = availability.get(event_id)
        if stamp is None:
            continue
        row = dict(event)
        row.update({
            "available_at": stamp,
            "published_at": None,
            "source_snapshot_asof": stamp,
            "anchor_strategy": "durable_available_at",
        })
        out.append(row)
    return out


def _stage_digest(records: list[dict[str, Any]], count: int | None = None) -> str:
    subset = records if count is None else records[:count]
    try:
        raw = b"".join(
            json.dumps(
                row, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode() + b"\n"
            for row in subset
        )
    except (TypeError, ValueError) as exc:
        raise ContractError("dated event stage contains non-finite JSON") from exc
    return hashlib.sha256(raw).hexdigest()


def _validate_checkpoint_document(checkpoint: object) -> dict[str, Any]:
    if not isinstance(checkpoint, dict) or set(checkpoint) != {"schema", "sessions"}:
        raise ContractError("signal-episode checkpoint shape mismatch")
    if checkpoint.get("schema") != "options.signal_episode_checkpoint/v1":
        raise ContractError("signal-episode checkpoint schema mismatch")
    sessions = checkpoint.get("sessions")
    if not isinstance(sessions, dict):
        raise ContractError("signal-episode checkpoint sessions must be an object")
    empty_digest = _stage_digest([])
    for session_date, receipt in sessions.items():
        try:
            parsed_session = date.fromisoformat(session_date)
        except (TypeError, ValueError) as exc:
            raise ContractError("signal-episode checkpoint has an invalid session date") from exc
        if parsed_session.isoformat() != session_date:
            raise ContractError("signal-episode checkpoint session date is not canonical")
        if not nyse_calendar.is_session(parsed_session):
            raise ContractError(
                f"signal-episode checkpoint date is not an NYSE session: {session_date}"
            )
        if not isinstance(receipt, dict) or set(receipt) != {"records", "prefix_sha256"}:
            raise ContractError(
                f"signal-episode checkpoint receipt shape is invalid for {session_date}"
            )
        record_count = receipt.get("records")
        digest = receipt.get("prefix_sha256")
        if type(record_count) is not int or record_count < 0:
            raise ContractError(
                f"signal-episode checkpoint record count is invalid for {session_date}"
            )
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ContractError(
                f"signal-episode checkpoint digest is invalid for {session_date}"
            )
        if record_count == 0 and digest != empty_digest:
            raise ContractError(
                f"signal-episode checkpoint empty-prefix digest is invalid for {session_date}"
            )
    return checkpoint


def _advance_checkpoint(path: Path, session_date: str, records: list[dict[str, Any]], *, dry_run: bool) -> None:
    """Validate and atomically merge one source prefix into the checkpoint.

    The JSONL ledgers have their own locks.  The checkpoint needs a stable
    sidecar lock because replacing the checkpoint changes its inode; locking
    the checkpoint itself would allow a later opener to bypass an older lock.
    """
    if dry_run or not nightly_advance_enabled():
        _merge_checkpoint(path, session_date, records, write=False)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f"{path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            _merge_checkpoint(path, session_date, records, write=True)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _merge_checkpoint(
    path: Path,
    session_date: str,
    records: list[dict[str, Any]],
    *,
    write: bool,
) -> None:
    checkpoint: dict[str, Any] = {"schema": "options.signal_episode_checkpoint/v1", "sessions": {}}
    if path.exists():
        try:
            checkpoint = _strict_json_loads(path.read_text())
        except Exception as exc:  # noqa: BLE001
            raise ContractError("signal-episode checkpoint is corrupt") from exc
    checkpoint = _validate_checkpoint_document(checkpoint)
    sessions = checkpoint.setdefault("sessions", {})
    prior = sessions.get(session_date) or {}
    prior_count = int(prior.get("records") or 0)
    if prior_count > len(records):
        raise ContractError("dated event stage shrank behind its checkpoint")
    if prior_count and prior.get("prefix_sha256") != _stage_digest(records, prior_count):
        raise ContractError("dated event stage prefix changed behind its checkpoint")
    sessions[session_date] = {
        "records": len(records),
        "prefix_sha256": _stage_digest(records),
    }
    _validate_checkpoint_document(checkpoint)
    if not write:
        return
    encoded = (json.dumps(checkpoint, indent=2, sort_keys=True) + "\n").encode()
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if tmp.exists():
            tmp.unlink()


def _intraday_root(repo: Path, data_root: Path) -> Path:
    configured = os.environ.get("MACRO_INTRADAY_DIR")
    root = Path(configured).expanduser() if configured else data_root / "intraday"
    if not root.is_absolute():
        root = repo / root
    return root.resolve()


def _price_source_label(repo: Path, intraday_root: Path, ticker: str) -> str:
    path = (intraday_root / f"{ticker}.parquet").resolve()
    try:
        return path.relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _canonical_utc(value: object) -> str:
    if type(value) is not str:
        raise ValueError("timestamp must be a string")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must carry a timezone")
    canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise ValueError("timestamp must be canonical UTC")
    return canonical


def _price_snapshot(
    intraday_root: Path, ticker: str,
) -> tuple[pd.DataFrame | None, dict[str, Any] | None]:
    """Read one receipt-bound immutable parquet byte snapshot without TOCTOU."""
    source = intraday_root / f"{ticker}.parquet"
    receipt_path = intraday_root / f"{ticker}.parquet.receipt.json"
    source_exists = source.exists()
    receipt_exists = receipt_path.exists()
    if not source_exists and not receipt_exists:
        return None, None
    # Existing deployments already carry mutable Polygon parquets that predate
    # this causal sidecar.  Until the collector successfully refreshes that
    # ticker, those bytes are not admissible evidence but they are not ledger
    # corruption either: leave its outcome pending and let other tickers accrue.
    if source_exists and not receipt_exists:
        return None, None
    if receipt_exists and not source_exists:
        raise ContractError(
            f"price snapshot pair is incomplete for {ticker}: "
            f"source={source_exists} receipt={receipt_exists}"
        )
    try:
        receipt_before = receipt_path.read_bytes()
        if not receipt_before or not receipt_before.endswith(b"\n"):
            raise ValueError("receipt is empty or torn")
        receipt = _strict_json_loads(receipt_before.decode("utf-8"))
        required = {
            "schema", "ticker", "source_file", "source_file_sha256",
            "source_available_at", "bar_seconds", "vendor_delay_minutes",
            "adjusted", "price_basis", "timestamp_basis", "row_count",
            "first_time", "last_time",
        }
        if not isinstance(receipt, dict) or set(receipt) != required:
            raise ValueError("receipt shape is invalid")
        if receipt.get("schema") != PRICE_RECEIPT_SCHEMA or receipt.get("ticker") != ticker:
            raise ValueError("receipt identity is invalid")
        if receipt.get("source_file") != source.name:
            raise ValueError("receipt source file is invalid")
        raw = source.read_bytes()
        receipt_after = receipt_path.read_bytes()
        if receipt_before != receipt_after:
            raise ValueError("receipt changed while taking the source snapshot")
        digest = hashlib.sha256(raw).hexdigest()
        if receipt.get("source_file_sha256") != digest:
            raise ValueError("source bytes disagree with the receipt digest")
        if (
            type(receipt.get("bar_seconds")) is not int
            or receipt["bar_seconds"] not in (60, 300, 900, 1800, 3600)
            or type(receipt.get("vendor_delay_minutes")) is not int
            or receipt["vendor_delay_minutes"] < 0
            or receipt.get("adjusted") is not True
            or receipt.get("price_basis") != PRICE_BASIS
            or receipt.get("timestamp_basis") != TIMESTAMP_BASIS
        ):
            raise ValueError("receipt price semantics are invalid")
        for field in ("source_available_at", "first_time", "last_time"):
            _canonical_utc(receipt.get(field))
        frame = pd.read_parquet(io.BytesIO(raw))
        normalized = normalize_price_bars(frame)
        if normalized.empty or type(receipt.get("row_count")) is not int:
            raise ValueError("receipt source frame is empty")
        if receipt["row_count"] != len(normalized):
            raise ValueError("receipt row count disagrees with source bytes")
        first = normalized.index.min().to_pydatetime().astimezone(timezone.utc)
        last = normalized.index.max().to_pydatetime().astimezone(timezone.utc)
        if receipt["first_time"] != first.isoformat().replace("+00:00", "Z"):
            raise ValueError("receipt first timestamp disagrees with source bytes")
        if receipt["last_time"] != last.isoformat().replace("+00:00", "Z"):
            raise ValueError("receipt last timestamp disagrees with source bytes")
        return frame, receipt
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, ContractError):
            raise
        raise ContractError(f"invalid price snapshot for {ticker}: {exc}") from exc


def run(
    *,
    root_dir: Path | None = None,
    feed: dict[str, Any] | None = None,
    stage_records: list[dict[str, Any]] | None = None,
    stages_by_session: dict[str, list[dict[str, Any]]] | None = None,
    computed_at: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    repo = Path(root_dir) if root_dir is not None else Path(config.ROOT)
    storage = config.load().get("storage") or {}
    data_root = repo / str(storage.get("data_dir") or "data")
    episode_path = data_root / EPISODE_REL
    outcome_path = data_root / OUTCOME_REL
    session_outcome_path = data_root / SESSION_OUTCOME_REL
    now = computed_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ContractError("computed_at must be timezone-aware")
    now = now.astimezone(timezone.utc)

    summary: dict[str, Any] = {
        "ok": True,
        "lane_armed": nightly_advance_enabled(),
        "dry_run": bool(dry_run),
        "feed_events": 0,
        "episodes_valid": 0,
        "episodes_rejected": 0,
        "episodes_appended": 0,
        "outcomes_complete": 0,
        "outcomes_terminal_incomplete": 0,
        "outcomes_pending": 0,
        "outcomes_appended": 0,
        "session_outcomes_complete": 0,
        "session_outcomes_terminal_incomplete": 0,
        "session_outcomes_pending": 0,
        "session_outcomes_appended": 0,
        "session_pending_reasons": {},
        "pending_reasons": {},
        "rejection_reasons": {},
        "sessions_discovered": [],
        "sessions_processed": [],
    }

    if stages_by_session is not None:
        stages = {str(key): value for key, value in stages_by_session.items()}
    elif stage_records is not None:
        if not isinstance(feed, dict) or not feed.get("session_date"):
            raise ContractError("injected stage_records require feed.session_date")
        stages = {str(feed["session_date"]): stage_records}
    else:
        sessions = discover_event_sessions()
        stages = {}
        for session_date in sessions:
            records = fetch_event_stage(session_date)
            if records is None:
                raise ContractError(f"discovered event stage disappeared: {session_date}")
            stages[session_date] = records
    summary["sessions_discovered"] = sorted(stages)
    if not stages:
        summary.update(ok=False, reason="no_dated_event_stages_discovered")
        return summary

    candidates: list[dict[str, Any]] = []
    for session_date in sorted(stages):
        records = stages[session_date]
        # Validate every retained prefix before deriving or writing anything.
        # Checkpoints advance only after all three ledgers finish successfully below.
        _advance_checkpoint(
            data_root / CHECKPOINT_REL, session_date, records, dry_run=True,
        )
        events = _events_from_stage(records, expected_session_date=session_date)
        summary["feed_events"] += len(events)
        for event in events:
            try:
                candidates.append(
                    episode_from_live_event(
                        event,
                        source_snapshot_asof=str(event.get("source_snapshot_asof")),
                        source_artifact=f"live_flow/events/{session_date}.jsonl",
                    )
                )
            except ContractError as exc:
                summary["episodes_rejected"] += 1
                reason = str(exc)
                summary["rejection_reasons"][reason] = summary["rejection_reasons"].get(reason, 0) + 1
                raise ContractError(
                    f"dated event stage contains an inadmissible decision {event.get('id')}: {exc}"
                ) from exc
        summary["sessions_processed"].append(session_date)
    summary["episodes_valid"] = len(candidates)

    existing_episodes = load_jsonl(episode_path)
    by_episode: dict[str, dict[str, Any]] = {}
    for row in existing_episodes:
        validate_episode(row)
        episode_id = row["episode_id"]
        if episode_id in by_episode:
            raise ContractError(f"duplicate existing episode row: {episode_id}")
        by_episode[episode_id] = row
    for row in candidates:
        prior = by_episode.get(row["episode_id"])
        if prior is not None and prior != row:
            raise ContractError(f"existing episode payload drift: {row['episode_id']}")
        by_episode.setdefault(row["episode_id"], row)

    existing_outcomes = load_jsonl(outcome_path)
    resolved_episodes: set[str] = set()
    outcome_ids: set[str] = set()
    outcome_keys: set[tuple[str, int]] = set()
    for row in existing_outcomes:
        validate_outcome(row)
        outcome_id = row["outcome_id"]
        semantic_key = (row["episode_id"], row["horizon_minutes"])
        if outcome_id in outcome_ids or semantic_key in outcome_keys:
            raise ContractError(f"duplicate existing outcome row: {outcome_id}")
        episode = by_episode.get(row["episode_id"])
        if episode is None:
            raise ContractError(f"outcome references missing episode: {row['episode_id']}")
        validate_outcome_against_episode(row, episode)
        outcome_ids.add(outcome_id)
        outcome_keys.add(semantic_key)
        resolved_episodes.add(row["episode_id"])

    existing_session_outcomes = load_jsonl(session_outcome_path)
    resolved_session_keys: set[tuple[str, str]] = set()
    session_outcome_ids: set[str] = set()
    for row in existing_session_outcomes:
        validate_session_outcome(row)
        outcome_id = row["outcome_id"]
        semantic_key = (row["episode_id"], row["horizon"])
        if outcome_id in session_outcome_ids or semantic_key in resolved_session_keys:
            raise ContractError(f"duplicate existing session outcome row: {outcome_id}")
        episode = by_episode.get(row["episode_id"])
        if episode is None:
            raise ContractError(
                f"session outcome references missing episode: {row['episode_id']}"
            )
        validate_session_outcome_against_episode(row, episode)
        session_outcome_ids.add(outcome_id)
        resolved_session_keys.add(semantic_key)

    if not dry_run:
        appended = append_episodes(episode_path, candidates)
        summary["episodes_appended"] = max(0, appended)
        if appended < 0:
            summary["write_skipped"] = "COLLECT_LANE is not nightly"

    intraday_root = _intraday_root(repo, data_root)
    price_cache: dict[str, tuple[pd.DataFrame | None, dict[str, Any] | None]] = {}
    price_cache_errors: set[str] = set()
    outcomes: list[dict[str, Any]] = []
    for episode_id, episode in by_episode.items():
        if episode_id in resolved_episodes:
            continue
        ticker = str(episode.get("ticker") or "")
        price_source = _price_source_label(repo, intraday_root, ticker)
        # Resolve clocks before touching the mutable price cache. Session-close
        # terminal facts and unmatured horizons are source-independent; a torn
        # or legacy sidecar must not change them. Only a matured, potentially
        # measurable episode is allowed to acquire and validate price evidence.
        attempt = derive_h60_outcome(
            episode,
            None,
            computed_at=now,
            price_source=price_source,
            bar_seconds=None,
            price_delay_minutes=None,
            price_receipt=None,
        )
        if attempt.get("reason") == "missing_price_receipt":
            if ticker not in price_cache:
                price_cache[ticker] = _price_snapshot(intraday_root, ticker)
            frame, receipt = price_cache[ticker]
            bar_seconds = receipt.get("bar_seconds") if receipt is not None else None
            price_delay_minutes = (
                receipt.get("vendor_delay_minutes") if receipt is not None else None
            )
            attempt = derive_h60_outcome(
                episode,
                frame,
                computed_at=now,
                price_source=price_source,
                bar_seconds=bar_seconds,
                price_delay_minutes=price_delay_minutes,
                price_receipt=receipt,
            )
        status = attempt.get("status")
        if status == "complete":
            summary["outcomes_complete"] += 1
            outcomes.append(attempt)
        elif status == "incomplete":
            summary["outcomes_terminal_incomplete"] += 1
            outcomes.append(attempt)
        else:
            summary["outcomes_pending"] += 1
            reason = str(attempt.get("reason") or "unknown")
            summary["pending_reasons"][reason] = summary["pending_reasons"].get(reason, 0) + 1

    if not dry_run:
        appended = append_outcomes(outcome_path, outcomes)
        summary["outcomes_appended"] = max(0, appended)
        if appended < 0:
            summary["write_skipped"] = "COLLECT_LANE is not nightly"

    session_outcomes: list[dict[str, Any]] = []
    for episode_id, episode in by_episode.items():
        ticker = str(episode.get("ticker") or "")
        price_source = _price_source_label(repo, intraday_root, ticker)
        for horizon in SESSION_HORIZONS:
            if (episode_id, horizon) in resolved_session_keys:
                continue
            attempt = derive_session_outcome(
                episode,
                horizon,
                None,
                computed_at=now,
                price_source=price_source,
                bar_seconds=None,
                price_delay_minutes=None,
                price_receipt=None,
            )
            if attempt.get("reason") == "missing_price_receipt":
                if ticker not in price_cache and ticker not in price_cache_errors:
                    try:
                        price_cache[ticker] = _price_snapshot(intraday_root, ticker)
                    except ContractError:
                        # One corrupt receipt-bound snapshot applies to every
                        # unresolved session horizon for this ticker in this run.
                        # Cache the failure so the mutable pair is read exactly
                        # once and every horizon reports the same retryable gap.
                        price_cache_errors.add(ticker)
                if ticker in price_cache_errors:
                    # H+60 clock-terminal rows historically do not acquire the
                    # cache. A newly-mature session horizon must not retroactively
                    # make that source-independent append fail; leave the new
                    # horizon retryable and consume no unreceipted bytes.
                    attempt = {
                        "status": "pending", "reason": "invalid_price_receipt",
                        "episode_id": episode_id, "horizon": horizon,
                    }
                else:
                    frame, receipt = price_cache[ticker]
                    bar_seconds = receipt.get("bar_seconds") if receipt is not None else None
                    price_delay_minutes = (
                        receipt.get("vendor_delay_minutes") if receipt is not None else None
                    )
                    attempt = derive_session_outcome(
                        episode,
                        horizon,
                        frame,
                        computed_at=now,
                        price_source=price_source,
                        bar_seconds=bar_seconds,
                        price_delay_minutes=price_delay_minutes,
                        price_receipt=receipt,
                    )
            status = attempt.get("status")
            if status == "complete":
                summary["session_outcomes_complete"] += 1
                session_outcomes.append(attempt)
            elif status == "incomplete":
                summary["session_outcomes_terminal_incomplete"] += 1
                session_outcomes.append(attempt)
            else:
                summary["session_outcomes_pending"] += 1
                reason = str(attempt.get("reason") or "unknown")
                summary["session_pending_reasons"][reason] = (
                    summary["session_pending_reasons"].get(reason, 0) + 1
                )

    if not dry_run:
        appended = append_session_outcomes(session_outcome_path, session_outcomes)
        summary["session_outcomes_appended"] = max(0, appended)
        if appended < 0:
            summary["write_skipped"] = "COLLECT_LANE is not nightly"
        # Ledger appends are idempotent. Advancing the source-prefix checkpoint
        # last means a later checkpoint failure can safely replay every exact row,
        # while a conversion/ledger failure can never bless an unconsumed prefix.
        for session_date in sorted(stages):
            _advance_checkpoint(
                data_root / CHECKPOINT_REL,
                session_date,
                stages[session_date],
                dry_run=False,
            )
    return summary


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(
        description=(
            "Accrue PIT options episodes, H+60 labels, and declared-session-close proxies"
        )
    )
    parser.add_argument("--dry-run", action="store_true", help="derive and report; write nothing")
    parser.add_argument("--root-dir", default=None, help="repo root override for replay/tests")
    args = parser.parse_args(argv)
    try:
        summary = run(
            root_dir=Path(args.root_dir) if args.root_dir else None,
            dry_run=bool(args.dry_run),
        )
        print(json.dumps(summary, sort_keys=True))
    except Exception as exc:  # noqa: BLE001
        log.exception("options signal episode builder failed")
        print(json.dumps({"ok": False, "reason": str(exc)}, sort_keys=True))
        return 1
    # An ordinary source gap is reported in the summary but remains nonfatal. Any
    # integrity/contract exception above is nonzero so workflow continue-on-error
    # remains visible instead of silently blessing a broken learning ledger.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
