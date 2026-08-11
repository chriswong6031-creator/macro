"""scripts/live_flow_poller.py — intraday options-flow polling driver.

Mac-side loop: fetches bulk_trade_quote per root per cycle, runs the live_flow
event engine, writes JSON artifacts locally and uploads to R2.

Config block 'live_flow:' in config.yml:
  cadence_sec:    120     # minimum interval between cycle starts (poll floor)
  max_concurrent: 2       # HARD LAW — T1 backfill shares the 8-request cap
  etf_anchors:    [...]   # defaults to build_tape_flow's 21 + DIA
  top_names:      100     # resolved from gex_symbols() after anchors
  etf_floor:      1000000 # $ gross premium floor for ETF anchors
  name_floor:     250000  # $ gross premium floor for single names
  retention_hours: 24     # trailing window for feed events
  state_retention_days: 5 # local day_state files kept (newest N sessions; current day never pruned)

Usage:
  # Import/entrypoint smoke only; does not fetch, stage, or publish
  python -m scripts.live_flow_poller --help

  # Production launchd command (RTH only — exits outside 09:25–16:05 ET)
  python -m scripts.live_flow_poller --rth-only

  Historical ``--once --date`` is not a smoke test. It conflicts with exact
  PIT clock admission and can overwrite live/current or replay objects. Use the
  isolated unit fixtures documented in ops/LIVE_FLOW_RUNBOOK.md instead.

INERT semantics: root failures → skip + log, never abort the cycle.
NEVER raise max_concurrent above 2 without explicit Fable adjudication.

New R2 objects emitted each cycle (live_flow/ prefix):
  tide_current.json       — market tide (NCP/NPP/gross/vol cumulative minutes + sectors)
  dte_tide_current.json   — DTE-bucket tide (5 buckets)
  tickers/{ROOT}.json     — per-root drill (top ~40 by day gross premium)
  tide/{DATE}.json        — dated archive of tide_current (same bytes; OIP W0 T-lane)
  dte_tide/{DATE}.json    — dated archive of dte_tide_current (same bytes)
  {tide,dte_tide}/dates.json — sessions index per family (see scripts/build_flow_archive.py)
"""
from __future__ import annotations

import argparse
import fcntl
import gc
import hashlib
import json
import logging
import math
import os
import re
import resource
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.session_digest import session_window_et  # noqa: E402
from lib import config, nyse_calendar  # noqa: E402

log = logging.getLogger(__name__)


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

# ── constants ─────────────────────────────────────────────────────────────────
# Stdlib zoneinfo (repo convention, e.g. engine/options_flow.py) — no pytz dependency.
ET = ZoneInfo("America/New_York")
PROBE_ROOT   = "SPY"        # root used for delta_mode probe
PROBE_WINDOW = 90           # seconds to subtract from "now" for time-windowed probe
ARCHIVE_HOUR_CADENCE = 3600  # write hourly archive every ~3600s

# R2 live_flow prefix
R2_PREFIX = "live_flow/"

# Out/state dirs (gitignored)
OUT_DIR   = "live_flow_out"
STATE_DIR = "live_flow_state"
EVENT_STAGE_SCHEMA = "live_flow.event_stage/v1"
EVENT_STAGE_RETAIN_SESSIONS = 64

# Prospective Market Memory capture is opt-in and private. The poller queues a
# request only after both owner receipts are fsynced. Historical/manual runs
# never initialize this boundary.
OPTIONS_CONTEXT_CAPTURE_ENV = "MARKET_MEMORY_OPTIONS_CONTEXT_CAPTURE"
OPTIONS_CONTEXT_CAPTURE_ROOT_ENV = "MARKET_MEMORY_OPTIONS_CONTEXT_OUTBOX"
OPTIONS_CONTEXT_CAPTURE_TARGET_ENV = "MARKET_MEMORY_OPTIONS_CONTEXT_SSH_TARGET"
OPTIONS_CONTEXT_CAPTURE_KEY_ENV = "MARKET_MEMORY_OPTIONS_CONTEXT_SSH_KEY"
_OPTIONS_CONTEXT_DISPATCHER = None

# Top tickers to publish per cycle (by day gross premium)
TOP_TICKERS_N = 40

# Day-state size guard: warn if exceeds this byte threshold
DAY_STATE_SIZE_WARN_BYTES = 50 * 1024 * 1024  # 50 MB

# RTH window (America/New_York) — poller active within this range
RTH_START_H, RTH_START_M = 9, 25     # 09:25 ET
RTH_END_H,   RTH_END_M   = 16, 5     # 16:05 ET

# Item 1b: per-root retry on None return — widen connect timeout and pause before skip.
# "terminal offline" may only be claimed after a direct probe with PROBE_CONNECT_TIMEOUT.
RETRY_CONNECT_TIMEOUT = 15   # seconds — wider connect for per-root retry
RETRY_PAUSE_SEC       = 5    # seconds — pause before retry

# Item 8: RSS logging threshold
RSS_WARN_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB

# ── FC-R6: two-tier cadence config (DEFAULT OFF) ──────────────────────────────
# Tier-1 roots are always polled every cycle; tier-2 (long tail) are round-robined.
# Enable via env: LIVE_FLOW_TWO_TIER=1
# NEVER raise max_concurrent above 2 without explicit Fable adjudication.
# max_concurrent override: LIVE_FLOW_MAX_CONCURRENT=N (default: config or 2).
TWO_TIER_ENV         = "LIVE_FLOW_TWO_TIER"
MAX_CONCURRENT_ENV   = "LIVE_FLOW_MAX_CONCURRENT"

# FC-R6: Tier-1 roots — ETF anchors + Mag7 + memory-storage names.
# These are always polled every cycle when two-tier mode is ON.
TIER1_ROOTS = [
    # ETF anchors (22)
    "SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "XLF", "XLE",
    "XLU", "XLK", "XLV", "XLI", "XLB", "XLY", "XLP", "XLRE",
    "KRE", "SMH", "XBI", "ARKK", "DIA",
    # Mag7
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    # Memory storage (flow continuity names)
    "MU", "WDC", "STX", "SNDK",
]

# Task 3: pinned always-publish roots (Mag7 + memory + ETF majors).
# When LIVE_FLOW_PINNED_PUBLISH=1 (DEFAULT ON), these roots are included in the
# published ticker JSON even if they fall outside the top-40 by gross premium.
PINNED_PUBLISH_ENV = "LIVE_FLOW_PINNED_PUBLISH"
PINNED_PUBLISH_ROOTS = [
    "SPY", "QQQ", "SMH",
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    "MU", "WDC", "STX", "SNDK",
]

# FC-R8: daily summary (DEFAULT OFF — new production write, operator must opt-in).
# Enable via env: LIVE_FLOW_DAILY_SUMMARY=1
# When enabled: writes data/live_flow_daily/YYYY-MM-DD.json each cycle (idempotent)
# and uploads to R2 as live_flow_daily/<date>.json (permanent, outside 48h prune scope).
DAILY_SUMMARY_ENV = "LIVE_FLOW_DAILY_SUMMARY"
DAILY_SUMMARY_DIR = "live_flow_daily"


def _daily_summary_enabled() -> bool:
    """True iff LIVE_FLOW_DAILY_SUMMARY=1.  Default OFF (production safe)."""
    return os.environ.get(DAILY_SUMMARY_ENV, "0").strip() == "1"


# ── config access ─────────────────────────────────────────────────────────────

def _cfg() -> dict:
    """Return the live_flow config block (with defaults filled)."""
    try:
        return dict(config.load().get("live_flow", {}) or {})
    except Exception:  # noqa: BLE001
        return {}


def _poll_floor_sec(cfg: dict) -> int:
    """Configured minimum start-to-start interval; never an observed cadence.

    A cycle whose fetch/compute work takes longer than this floor starts the next
    cycle immediately.  Consumers therefore use this value as the expected-frame
    denominator and use the separately measured start-to-start interval only as
    descriptive evidence.
    """
    value = cfg.get("cadence_sec", 120)
    if type(value) is not int or value <= 0:
        raise ValueError("live_flow.cadence_sec must be an exact positive integer poll floor")
    return value


def _r2_public_base() -> str:
    try:
        return config.load().get("r2_data_plane", {}).get("public_base", "")
    except Exception:  # noqa: BLE001
        return ""


# ── FC-R6: two-tier cadence helpers ──────────────────────────────────────────

def _max_concurrent(cfg: dict) -> int:
    """Resolve max_concurrent: LIVE_FLOW_MAX_CONCURRENT env > config > default 2.

    HARD LAW: ThetaData T1 backfill shares the 8-request cap.  Default is 2
    and must not be raised without explicit Fable adjudication.
    """
    env_val = os.environ.get(MAX_CONCURRENT_ENV)
    if env_val is not None:
        try:
            return max(1, int(env_val))
        except ValueError:
            log.warning("poller: invalid %s=%r — using config/default", MAX_CONCURRENT_ENV, env_val)
    return int(cfg.get("max_concurrent", 2))


def _two_tier_enabled() -> bool:
    """True iff LIVE_FLOW_TWO_TIER=1.  Default OFF (production safe)."""
    return os.environ.get(TWO_TIER_ENV, "0").strip() == "1"


def _select_cycle_roots(
    all_roots: list[str],
    cycle_n: int,
    cfg: dict,
) -> tuple[list[str], int]:
    """Return (roots_for_this_cycle, tail_slot_polled).

    Two-tier cadence (LIVE_FLOW_TWO_TIER=1, DEFAULT OFF):
      - Tier-1 (TIER1_ROOTS ∩ universe) polled every cycle.
      - Tier-2 (remaining) split into N_TIER2_BUCKETS buckets; one bucket per cycle
        (round-robin by cycle_n).  Each long-tail root is polled every
        N_TIER2_BUCKETS cycles.  Projection example (122 roots):
          tier1 = 34 (TIER1_ROOTS ∩ universe), tier2 = 88
          With max_concurrent=2: tier1_time ≈ 34 * ~17s = 578s (~9.6 min)
          Per-cycle time budget targeted at 10 min → tail slot ≈ 22 roots/cycle
          N_TIER2_BUCKETS ≈ 88/22 = 4 → each tail root polled every 4 cycles (~40 min).

    When two-tier is OFF: returns all_roots unchanged.
    Returns tail_slot = -1 when two-tier is OFF or tier-2 is empty.
    """
    n_tier2_buckets = int(cfg.get("tier2_buckets", 4))

    if not _two_tier_enabled():
        return all_roots, -1

    tier1_set = set(TIER1_ROOTS)
    tier1 = [r for r in all_roots if r.upper() in tier1_set]
    tier2 = [r for r in all_roots if r.upper() not in tier1_set]

    if not tier2:
        return tier1 if tier1 else all_roots, -1

    # Round-robin tier-2 bucket
    bucket_idx = (cycle_n - 1) % n_tier2_buckets
    bucket_size = max(1, (len(tier2) + n_tier2_buckets - 1) // n_tier2_buckets)
    start = bucket_idx * bucket_size
    tier2_slice = tier2[start: start + bucket_size]

    cycle_roots = tier1 + tier2_slice
    log.info(
        "poller: two-tier cycle=%d tier1=%d tier2_slot=%d/%d (%d roots)",
        cycle_n, len(tier1), bucket_idx, n_tier2_buckets, len(tier2_slice),
    )
    return cycle_roots, bucket_idx


# ── Task 3: pinned-publish helper ─────────────────────────────────────────────

def _pinned_publish_enabled() -> bool:
    """True by default; set LIVE_FLOW_PINNED_PUBLISH=0 to disable."""
    return os.environ.get(PINNED_PUBLISH_ENV, "1").strip() != "0"


# ── output paths ─────────────────────────────────────────────────────────────

def _fsync_directory(path: Path) -> None:
    """Persist directory contents and metadata before claiming durability."""
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _ensure_directory_durable(path: Path) -> Path:
    """Create each missing component and durably link it from its parent."""
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            raise RuntimeError(f"cannot find existing parent for directory: {path}")
        cursor = parent
    if not cursor.is_dir():
        raise RuntimeError(f"directory parent is not a directory: {cursor}")
    for directory in reversed(missing):
        try:
            directory.mkdir()
        except FileExistsError:
            if not directory.is_dir():
                raise
        _fsync_directory(directory)
        _fsync_directory(directory.parent)
    return path


def _out_dir() -> Path:
    p = config.data_dir() / OUT_DIR
    return _ensure_directory_durable(p)


def _state_dir() -> Path:
    p = config.data_dir() / STATE_DIR
    return _ensure_directory_durable(p)


def _initialize_options_context_dispatcher(
    session_date: str, *, historical: bool,
):
    """Arm the private owner-time outbox, never a backdated run."""

    if os.environ.get(OPTIONS_CONTEXT_CAPTURE_ENV, "0").strip() != "1":
        return None
    if historical:
        log.warning(
            "poller: option-context capture disabled for a historical --date run"
        )
        return None
    try:
        from engine.neuralweb import market_memory_options_episode_capture as capture

        root_text = os.environ.get(OPTIONS_CONTEXT_CAPTURE_ROOT_ENV, "").strip()
        root = (
            Path(root_text)
            if root_text
            else _state_dir() / "market_memory_options_context"
        )
        target = os.environ.get(OPTIONS_CONTEXT_CAPTURE_TARGET_ENV, "").strip()
        key = os.environ.get(OPTIONS_CONTEXT_CAPTURE_KEY_ENV, "").strip()
        if not target or not key:
            raise capture.OptionsEpisodeContextCaptureError(
                "capture transport target/key path is not configured"
            )
        return capture.initialize_dispatcher(
            root,
            session_date=session_date,
            config_path=_ROOT / "config" / "market_memory_canary.v1.json",
            ssh_target=target,
            ssh_key=key,
        )
    except Exception as exc:  # noqa: BLE001 - evidence must not stop live flow
        log.warning(
            "poller: prospective option-context capture is abstaining (%s)", exc,
        )
        return None


def _flush_options_context_outbox() -> None:
    """Bounded fail-soft transport; failed evidence remains durable."""

    if _OPTIONS_CONTEXT_DISPATCHER is None:
        return
    try:
        result = _OPTIONS_CONTEXT_DISPATCHER.drain_pending()
        if result.get("captured") or result.get("expired") or result.get("unknown"):
            log.info(
                "poller: option-context outbox captured=%d expired=%d "
                "unknown=%d pending=%d",
                result.get("captured", 0),
                result.get("expired", 0),
                result.get("unknown", 0),
                result.get("pending", 0),
            )
    except Exception as exc:  # noqa: BLE001 - evidence must not stop live flow
        log.warning("poller: option-context outbox transport deferred (%s)", exc)


def _utc_now_iso(now_fn=None) -> str:
    """Return an aware UTC clock without discarding sub-second ordering."""
    value = (now_fn or (lambda: datetime.now(timezone.utc)))()
    if getattr(value, "tzinfo", None) is None:
        raise RuntimeError("poller clock must be a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_utc_timestamp(value: object, *, field: str) -> str:
    """Validate an aware UTC clock without inventing or discarding precision."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty UTC timestamp")
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(
            raw[:-1] + "+00:00" if raw.endswith("Z") else raw,
        )
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{field} must carry an explicit UTC offset")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _observed_interval_sec(value: object) -> float | None:
    """Validate a descriptive monotonic start-to-start interval."""
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(
            "observed_start_to_start_sec must be a finite non-negative number or null"
        )
    return round(float(value), 3)


def _event_stage_path(session_date: str) -> Path:
    override = os.environ.get("LIVE_FLOW_EVENT_STAGE_DIR")
    root = Path(override) if override else _state_dir() / "events"
    _ensure_directory_durable(root)
    return root / f"{session_date}.jsonl"


def _event_dates_index_path() -> Path:
    return _event_stage_path("1970-01-01").parent / "dates.json"


def _event_publish_receipts_path() -> Path:
    return _event_stage_path("1970-01-01").parent / "published.json"


def _load_event_publish_receipts() -> dict[str, dict[str, object]]:
    path = _event_publish_receipts_path()
    if not path.exists():
        return {}
    try:
        payload = _strict_json_loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"corrupt event-stage publication receipts: {path}") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema", "objects"}:
        raise RuntimeError(f"invalid event-stage publication receipt envelope: {path}")
    if payload.get("schema") != "live_flow.event_publications/v1":
        raise RuntimeError(f"wrong event-stage publication receipt schema: {path}")
    objects = payload.get("objects")
    if not isinstance(objects, dict):
        raise RuntimeError(f"invalid event-stage publication receipt objects: {path}")
    for session, receipt in objects.items():
        try:
            parsed_session = date.fromisoformat(session) if type(session) is str else None
        except ValueError as exc:
            raise RuntimeError(
                f"invalid published event session in {path}: {session}"
            ) from exc
        if (
            parsed_session is None
            or parsed_session.isoformat() != session
            or not nyse_calendar.is_session(parsed_session)
        ):
            raise RuntimeError(f"invalid published event session in {path}: {session}")
        if not isinstance(receipt, dict) or set(receipt) != {"bytes", "sha256"}:
            raise RuntimeError(f"invalid published event receipt for {session}")
        if type(receipt["bytes"]) is not int or receipt["bytes"] <= 0:
            raise RuntimeError(f"invalid published event byte count for {session}")
        if type(receipt["sha256"]) is not str or not re.fullmatch(
            r"[a-f0-9]{64}", receipt["sha256"],
        ):
            raise RuntimeError(f"invalid published event digest for {session}")
    return objects


def _atomic_write_json(path: Path, payload: dict) -> Path:
    _ensure_directory_durable(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    _fsync_directory(path.parent)
    return path


def _write_event_publish_receipts(objects: dict[str, dict[str, object]]) -> Path:
    return _atomic_write_json(
        _event_publish_receipts_path(),
        {
            "schema": "live_flow.event_publications/v1",
            "objects": {key: objects[key] for key in sorted(objects)},
        },
    )


def _write_event_dates_index(sessions: set[str] | None = None) -> Path:
    path = _event_dates_index_path()
    proven = sessions if sessions is not None else set(_load_event_publish_receipts())
    payload = {
        "schema": "live_flow.event_dates/v1",
        "sessions": sorted(proven)[-EVENT_STAGE_RETAIN_SESSIONS:],
    }
    return _atomic_write_json(path, payload)


def _event_inside_regular_session(session_date: str, event: dict) -> bool:
    try:
        event_dt = datetime.fromisoformat(str(event.get("ts") or "").replace("Z", "+00:00"))
        session = date.fromisoformat(session_date)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("event staging requires a valid session and event timestamp") from exc
    if event_dt.tzinfo is None:
        raise RuntimeError("event staging requires a timezone-aware event timestamp")
    if not nyse_calendar.is_session(session):
        raise RuntimeError(f"event staging date is not an NYSE session: {session_date}")
    open_et, close_et = session_window_et(session)
    event_utc = event_dt.astimezone(timezone.utc)
    return open_et.astimezone(timezone.utc) <= event_utc < close_et.astimezone(timezone.utc)


def _partition_learning_stage_events(
    session_date: str, events: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Split display events from the strict [open, close) learning source."""
    eligible: list[dict] = []
    display_only: list[dict] = []
    for event in events:
        (eligible if _event_inside_regular_session(session_date, event) else display_only).append(event)
    return eligible, display_only


def _prepare_event_stage_batch(session_date: str, events: list[dict]) -> list[dict]:
    """Validate a whole batch before opening/creating its durable stage file."""
    prepared: list[dict] = []
    seen_ids: set[str] = set()
    for source in events:
        event = dict(source)
        try:
            json.dumps(event, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("event staging requires strict finite JSON facts") from exc
        raw_event_id = event.get("id")
        if (
            type(raw_event_id) is not str
            or not raw_event_id
            or raw_event_id != raw_event_id.strip()
        ):
            raise RuntimeError("event staging requires a normalized string id")
        event_id = raw_event_id
        if not event.get("observed_at") or not event.get("decision_at"):
            raise RuntimeError("event staging requires id, observed_at, and decision_at")
        if event_id in seen_ids:
            raise RuntimeError(f"duplicate event id in one staging batch: {event_id}")
        seen_ids.add(event_id)
        try:
            event_dt = datetime.fromisoformat(
                str(event.get("ts") or "").replace("Z", "+00:00")
            )
            observed_dt = datetime.fromisoformat(
                str(event.get("observed_at") or "").replace("Z", "+00:00")
            )
            decision_dt = datetime.fromisoformat(
                str(event.get("decision_at") or "").replace("Z", "+00:00")
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeError("event staging requires timezone-aware causal clocks") from exc
        if any(value.tzinfo is None for value in (event_dt, observed_dt, decision_dt)):
            raise RuntimeError("event staging requires timezone-aware causal clocks")
        if not (event_dt <= observed_dt <= decision_dt):
            raise RuntimeError("event staging clock order must be event <= observed <= decision")
        event_session = event_dt.astimezone(ET).date().isoformat()
        if event_session != session_date:
            raise RuntimeError(
                f"event {event_id} belongs to {event_session}, not stage {session_date}"
            )
        if not _event_inside_regular_session(session_date, event):
            raise RuntimeError(
                f"event {event_id} is outside the regular-session learning window"
            )
        if any(
            value.astimezone(ET).date().isoformat() != session_date
            for value in (observed_dt, decision_dt)
        ):
            raise RuntimeError(
                f"event {event_id} decision clocks leave stage date {session_date}"
            )
        prepared.append({
            key: value for key, value in event.items()
            if key not in (
                "available_at", "published_at", "source_snapshot_asof", "anchor_strategy",
            )
        })
    return prepared


def _parse_event_stage_bytes(
    session_date: str,
    raw: bytes,
    *,
    path: Path,
    require_complete: bool,
) -> tuple[dict[str, dict], dict[str, str], dict[str, dict]]:
    """Parse a stage as an ordered per-event state machine, failing closed."""
    if raw and not raw.endswith(b"\n"):
        raise RuntimeError(f"torn live-flow event stage: {path}")
    if require_complete and not raw:
        raise RuntimeError(f"empty live-flow event stage: {path}")
    decisions: dict[str, dict] = {}
    available: dict[str, str] = {}
    context_capture: dict[str, dict] = {}
    for lineno, line in enumerate(raw.splitlines(), start=1):
        try:
            receipt = _strict_json_loads(line)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"malformed event stage {path}:{lineno}") from exc
        if not isinstance(receipt, dict) or receipt.get("schema") != EVENT_STAGE_SCHEMA:
            raise RuntimeError(f"wrong event-stage schema {path}:{lineno}")
        raw_event_id = receipt.get("event_id")
        if (
            type(raw_event_id) is not str
            or not raw_event_id
            or raw_event_id != raw_event_id.strip()
        ):
            raise RuntimeError(f"invalid event id {path}:{lineno}")
        event_id = raw_event_id
        kind = receipt.get("kind")
        if kind == "decision":
            if set(receipt) != {"schema", "kind", "event_id", "event"}:
                raise RuntimeError(f"invalid decision receipt shape {path}:{lineno}")
            event = receipt.get("event")
            if not isinstance(event, dict) or event.get("id") != event_id:
                raise RuntimeError(f"invalid decision receipt {path}:{lineno}")
            if event_id in decisions:
                raise RuntimeError(f"duplicate staged decision {event_id}")
            normalized = _prepare_event_stage_batch(session_date, [event])[0]
            if normalized != event:
                raise RuntimeError(f"decision receipt contains non-durable fields {event_id}")
            decisions[event_id] = event
        elif kind == "availability":
            if set(receipt) not in (
                {"schema", "kind", "event_id", "available_at"},
                {"schema", "kind", "event_id", "available_at", "context_capture"},
            ):
                raise RuntimeError(f"invalid availability receipt shape {path}:{lineno}")
            if event_id not in decisions:
                raise RuntimeError(
                    f"availability receipt precedes decision {event_id} at {path}:{lineno}"
                )
            if event_id in available:
                raise RuntimeError(f"duplicate staged availability {event_id}")
            stamp = str(receipt.get("available_at") or "")
            try:
                available_dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                decision_dt = datetime.fromisoformat(
                    str(decisions[event_id].get("decision_at") or "").replace("Z", "+00:00")
                )
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"invalid staged clock for {event_id}") from exc
            if available_dt.tzinfo is None or decision_dt.tzinfo is None:
                raise RuntimeError(f"staged clocks must be timezone-aware for {event_id}")
            if available_dt < decision_dt:
                raise RuntimeError(f"staged availability predates decision for {event_id}")
            if available_dt.astimezone(ET).date().isoformat() != session_date:
                raise RuntimeError(
                    f"staged availability leaves session date for {event_id}"
                )
            binding = receipt.get("context_capture")
            if binding is None:
                binding = {"status": "abstained", "reason": "legacy_unbound"}
            if not isinstance(binding, dict):
                raise RuntimeError(f"invalid context capture binding for {event_id}")
            if binding.get("status") == "prepared":
                if (
                    set(binding) != {"status", "request_id", "request_sha256"}
                    or not re.fullmatch(r"mmoptrequest_[a-f0-9]{64}", str(binding.get("request_id") or ""))
                    or not re.fullmatch(r"[a-f0-9]{64}", str(binding.get("request_sha256") or ""))
                ):
                    raise RuntimeError(
                        f"invalid prepared context capture binding for {event_id}"
                    )
            elif binding.get("status") == "abstained":
                if (
                    set(binding) != {"status", "reason"}
                    or binding.get("reason") not in {
                        "capture_not_armed",
                        "outside_predeclared_canary",
                        "precommit_not_proven",
                        "legacy_unbound",
                    }
                ):
                    raise RuntimeError(
                        f"invalid context capture abstention for {event_id}"
                    )
            else:
                raise RuntimeError(f"unknown context capture state for {event_id}")
            available[event_id] = stamp
            context_capture[event_id] = dict(binding)
        else:
            raise RuntimeError(f"unknown event-stage receipt {path}:{lineno}")
    missing = set(decisions) - set(available)
    if require_complete and missing:
        raise RuntimeError(f"event stage has decisions without availability: {sorted(missing)}")
    return decisions, available, context_capture


def _stage_raw_events(
    session_date: str,
    events: list[dict],
    *,
    now_fn=None,
) -> list[dict]:
    """Durably stage decision events before retention and assign availability.

    A decision record is fsynced first. Only then is ``available_at`` observed and
    an availability receipt appended+fsynced. Thus available_at never means fetch
    completion or sequential-processing completion. The date-keyed append ledger
    is the durable source consumed by nightly; ``feed_current`` is only a display.
    """
    if not events:
        return []
    clock = now_fn or (lambda: datetime.now(timezone.utc))
    prepared = _prepare_event_stage_batch(session_date, events)
    path = _event_stage_path(session_date)
    admission_checked = False
    if not path.exists():
        admission_stamp = _utc_now_iso(clock)
        admission_dt = datetime.fromisoformat(admission_stamp.replace("Z", "+00:00"))
        if admission_dt.astimezone(ET).date().isoformat() != session_date:
            raise RuntimeError(f"event staging clock is outside session date {session_date}")
        admission_checked = True
    with path.open("a+b") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.seek(0)
            raw = fh.read()
            decisions, available, context_capture = _parse_event_stage_bytes(
                session_date, raw, path=path, require_complete=False,
            )
            # An empty file means this call is creating the first durable source
            # receipt (including recovery from a crash that left only an empty
            # pathname). The directory entry must be fsynced after the decision
            # file fsync and before available_at is observed; otherwise a power
            # loss can retain day_state/emitted_ids while losing the source name.
            needs_directory_fsync = not raw

            # Resolve every replay/conflict before appending the first byte, so a
            # bad event later in the batch cannot leave earlier events half-staged.
            resolved: list[tuple[str, dict, bool]] = []
            for candidate in prepared:
                event_id = str(candidate["id"])
                durable_event = candidate
                prior = decisions.get(event_id)
                if prior is not None:
                    # A crash can occur after the first decision receipt is fsynced but
                    # before day_state is committed. The next cycle then re-fetches the
                    # same source event with later observation/processing clocks. Preserve
                    # the first durable clocks and compare every causal payload field; a
                    # clock-only replay is idempotent, while feature drift still fails shut.
                    replay_payload = dict(durable_event)
                    for clock_field in ("observed_at", "decision_at"):
                        replay_payload[clock_field] = prior.get(clock_field)
                    if json.dumps(prior, sort_keys=True) != json.dumps(replay_payload, sort_keys=True):
                        raise RuntimeError(f"staged event drift for {event_id}")
                    durable_event = prior
                resolved.append((event_id, durable_event, prior is None))

            if (
                not admission_checked
                and any(event_id not in available for event_id, _event, _new in resolved)
            ):
                # Reject a stale-session invocation before appending the first
                # new decision. This clock is only an admission guard; durable
                # availability is observed again after the decision fsync.
                admission_stamp = _utc_now_iso(clock)
                admission_dt = datetime.fromisoformat(
                    admission_stamp.replace("Z", "+00:00")
                )
                if admission_dt.astimezone(ET).date().isoformat() != session_date:
                    raise RuntimeError(
                        f"event staging clock is outside session date {session_date}"
                    )

            enriched: list[dict] = []
            context_promotions: list[tuple[str, object, str, dict]] = []
            for event_id, durable_event, needs_decision in resolved:
                if needs_decision:
                    receipt = {
                        "schema": EVENT_STAGE_SCHEMA,
                        "kind": "decision",
                        "event_id": event_id,
                        "event": durable_event,
                    }
                    fh.seek(0, os.SEEK_END)
                    fh.write(json.dumps(
                        receipt, sort_keys=True, separators=(",", ":"), allow_nan=False,
                    ).encode() + b"\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                    if needs_directory_fsync:
                        _fsync_directory(path.parent)
                        needs_directory_fsync = False
                    decisions[event_id] = durable_event
                stamp = available.get(event_id)
                new_availability = stamp is None
                prepared_context_request = None
                capture_binding = {"status": "abstained", "reason": "capture_not_armed"}
                if new_availability:
                    stamp = _utc_now_iso(clock)
                    stamp_dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    decision_dt = datetime.fromisoformat(
                        str(durable_event.get("decision_at") or "").replace("Z", "+00:00")
                    )
                    if stamp_dt < decision_dt:
                        raise RuntimeError(
                            f"durable availability predates decision for {event_id}"
                        )
                    if stamp_dt.astimezone(ET).date().isoformat() != session_date:
                        raise RuntimeError(
                            f"durable availability leaves session date for {event_id}"
                        )
                    enriched_event = dict(durable_event)
                    enriched_event["available_at"] = stamp
                    enriched_event["published_at"] = None
                    enriched_event["source_snapshot_asof"] = stamp
                    enriched_event["anchor_strategy"] = "durable_available_at"
                    # Observe missingness at the newly sampled cutoff, after the
                    # decision fsync but before any later clock can be confused
                    # with owner-time evidence. The private precommit is not
                    # transport-eligible; it only closes the crash seam until
                    # the availability receipt below becomes durable.
                    if _OPTIONS_CONTEXT_DISPATCHER is not None:
                        try:
                            prepared_context_request = (
                                _OPTIONS_CONTEXT_DISPATCHER.prepare(
                                    owner_event=enriched_event,
                                    session_date=session_date,
                                )
                            )
                            _OPTIONS_CONTEXT_DISPATCHER.stage(
                                prepared_context_request
                            )
                            if prepared_context_request is None:
                                capture_binding = {
                                    "status": "abstained",
                                    "reason": "outside_predeclared_canary",
                                }
                            else:
                                capture_binding = {
                                    "status": "prepared",
                                    **_OPTIONS_CONTEXT_DISPATCHER.availability_binding(
                                        prepared_context_request
                                    ),
                                }
                        except Exception as exc:  # noqa: BLE001 - context abstains
                            prepared_context_request = None
                            capture_binding = {
                                "status": "abstained",
                                "reason": "precommit_not_proven",
                            }
                            log.warning(
                                "poller: option-context observation abstained for %s (%s)",
                                event_id,
                                exc,
                            )
                    receipt = {
                        "schema": EVENT_STAGE_SCHEMA,
                        "kind": "availability",
                        "event_id": event_id,
                        "available_at": stamp,
                        "context_capture": capture_binding,
                    }
                    fh.write(json.dumps(
                        receipt, sort_keys=True, separators=(",", ":"), allow_nan=False,
                    ).encode() + b"\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                    available[event_id] = stamp
                    if prepared_context_request is not None:
                        context_promotions.append(
                            ("commit", prepared_context_request, event_id, capture_binding)
                        )
                else:
                    enriched_event = dict(durable_event)
                    enriched_event["available_at"] = stamp
                    enriched_event["published_at"] = None
                    enriched_event["source_snapshot_asof"] = stamp
                    enriched_event["anchor_strategy"] = "durable_available_at"
                    if _OPTIONS_CONTEXT_DISPATCHER is not None:
                        capture_binding = context_capture.get(
                            event_id,
                            {"status": "abstained", "reason": "legacy_unbound"},
                        )
                        if capture_binding.get("status") == "prepared":
                            context_promotions.append(
                                ("recover", enriched_event, event_id, capture_binding)
                            )
                # An already-available replay cannot manufacture a request. Only
                # exact bytes precommitted at the first cutoff may retry transport.
                enriched.append(enriched_event)
            # Reconfirm the complete visible prefix at the transaction boundary,
            # even when every receipt came from a prior attempt.  A failed fsync
            # can leave bytes visible in page cache; replay must not clear the
            # pending-learning WAL merely because those unconfirmed bytes parse.
            # The parent sync also closes the analogous first-create case where
            # the decision file fsync succeeded but linking its pathname did not.
            fh.flush()
            os.fsync(fh.fileno())
            _fsync_directory(path.parent)
            # Only this point proves both the complete availability-file bytes
            # and their parent entry durable. A replay may promote an exact
            # precommit after this proof, never merely because page-cache bytes
            # parsed before the final fsync boundary.
            for action, payload, event_id, capture_binding in context_promotions:
                owner_binding = {
                    "request_id": capture_binding["request_id"],
                    "request_sha256": capture_binding["request_sha256"],
                }
                if action == "commit":
                    _OPTIONS_CONTEXT_DISPATCHER.commit(
                        payload, owner_binding=owner_binding
                    )
                else:
                    _OPTIONS_CONTEXT_DISPATCHER.recover(
                        owner_event=payload,
                        session_date=session_date,
                        owner_binding=owner_binding,
                    )
            return enriched
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


# ── universe resolver ─────────────────────────────────────────────────────────

def _resolve_universe(cfg: dict) -> list[str]:
    """ETF anchors + top_names from gex_symbols(), deduped."""
    from engine.options_universe import gex_symbols

    default_anchors = [
        "SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "XLF", "XLE",
        "XLU", "XLK", "XLV", "XLI", "XLB", "XLY", "XLP", "XLRE",
        "KRE", "SMH", "XBI", "ARKK", "DIA",
    ]
    anchors = [a.upper() for a in (cfg.get("etf_anchors") or default_anchors)]
    top_n   = int(cfg.get("top_names", 100))

    seen: dict[str, None] = {}
    for t in anchors:
        seen.setdefault(t, None)

    try:
        gex = gex_symbols()
        for t in gex:
            seen.setdefault(t.upper(), None)
    except Exception as e:  # noqa: BLE001
        log.warning("poller: gex_symbols failed: %s", e)

    all_syms = list(seen)
    # Cap at anchors + top_n names after anchors
    return all_syms[: max(len(anchors), len(anchors) + top_n)]


# ── delta_mode probe ─────────────────────────────────────────────────────────

def _probe_delta_mode(session_date: str) -> str:
    """Determine whether time-filtered incremental pulls work on this terminal.

    Probes the PREVIOUS trading session, not the current one. The poller starts
    at 09:25 ET; the original same-session probe compared the full day against a
    14:30–14:45 window that lay in the FUTURE at probe time, so the window pull
    always returned 0 rows and the probe concluded full_day — every day, at any
    terminal capability. (That alone kept delta_mode=full_day after the 2026-07
    terminal builds added working time filters.) A completed prior session gives
    an unambiguous full-vs-window comparison at any hour of day.

    Uses an EXPLICIT expiration (nearest listed at/after the probe day):
    wildcard expiration + time filter returns silently-empty (HTTP 200, zero
    rows) on terminal build 202607231 — see the guard in
    collectors.thetadata.bulk_trade_quote — and a single-expiration past-day
    pull is ~60× cheaper than the old full-chain probe.

    Window is 10:00–10:15 ET so the comparison also works on half-day sessions
    (13:00 ET close). If the prior weekday has no data (holiday), steps back up
    to 4 more weekdays before giving up to full_day.
    """
    from collectors import thetadata as td

    def _pull(**kw):
        """One probe pull, retried once after a pause. The probe runs exactly once
        per poller session and decides the WHOLE day's cadence, so a single
        transient reachable()/contention flake (measured 2026-07-31 while the
        evening backfill saturated the terminal's 8 slots) must not condemn the
        day to full_day."""
        df = td.bulk_trade_quote(PROBE_ROOT, "call", **kw)
        if df is None:
            time.sleep(RETRY_PAUSE_SEC)
            df = td.bulk_trade_quote(PROBE_ROOT, "call", **kw)
        return df

    log.info("poller: probing delta_mode via %s prior session …", PROBE_ROOT)
    try:
        target = datetime.strptime(session_date, "%Y-%m-%d").date()

        exps = td.list_expirations(PROBE_ROOT)
        exp_iso = None
        if exps:
            exp_iso = next((e for e in exps if e >= session_date), None)
        if exp_iso is None:
            log.info("poller: probe — no expiration at/after %s, defaulting to full_day",
                     session_date)
            return "full_day"

        probe_day = target
        for _ in range(5):
            probe_day -= timedelta(days=1)
            while probe_day.weekday() >= 5:
                probe_day -= timedelta(days=1)
            full = _pull(start_date=probe_day, end_date=probe_day, expiration=exp_iso)
            if full is None:
                log.info("poller: probe — full pull failed for %s, using full_day",
                         probe_day)
                return "full_day"
            if not full.empty:
                break
            log.info("poller: probe — no %s trades on %s (holiday?), stepping back",
                     exp_iso, probe_day)
        else:
            log.info("poller: probe — no prior-session data found, defaulting to full_day")
            return "full_day"

        n_full = len(full)
        win = _pull(start_date=probe_day, end_date=probe_day,
                    start_time="10:00:00", end_time="10:15:00",
                    expiration=exp_iso)
        if win is None:
            log.info("poller: probe — windowed pull failed, using full_day")
            return "full_day"

        n_win = len(win)
        log.info("poller: probe — %s exp=%s full=%d window(10:00-10:15)=%d",
                 probe_day, exp_iso, n_full, n_win)
        if 0 < n_win < n_full:
            log.info("poller: delta_mode=time_window (time filter confirmed)")
            return "time_window"
        log.info("poller: delta_mode=full_day (window filter inconclusive)")
        return "full_day"
    except Exception as e:  # noqa: BLE001
        log.warning("poller: delta_mode probe failed: %s — defaulting full_day", e)
        return "full_day"


# ── per-root fetch ────────────────────────────────────────────────────────────

def _fetch_root(root: str, session_date: str,
                start_time: str | None, end_time: str | None
                ) -> tuple[str, object | None, object | None]:
    """Fetch call + put for one root.  Returns (root, calls_df, puts_df).

    Either may be None (terminal failure) or empty DataFrame (no trades).

    Item 1b — retry logic:
      If the first fetch returns None (terminal contention under ~360-root backfill
      saturates the 8-request ceiling), pause RETRY_PAUSE_SEC seconds then retry ONCE
      with RETRY_CONNECT_TIMEOUT (15s).  "terminal offline/unreachable" log may only be
      emitted after a direct probe with the wider timeout confirms the terminal is down.
      Otherwise log "terminal contended — root skipped after retry".

    INERT: never raises.
    """
    from collectors import thetadata as td

    try:
        cfg = _cfg()
        kw: dict = {}
        if start_time:
            kw["start_time"] = start_time
        if end_time:
            kw["end_time"] = end_time
        near_dte_cap = cfg.get("near_dte_cap_days", 90)
        if near_dte_cap is not None:
            kw["near_dte_cap_days"] = int(near_dte_cap)

        calls = td.bulk_trade_quote(root, "call", session_date, session_date, **kw)
        puts  = td.bulk_trade_quote(root, "put",  session_date, session_date, **kw)

        # Item 1b: if BOTH legs are None (not just empty) retry once with wider timeout
        if calls is None and puts is None:
            log.debug("poller: fetch returned None for %s — pausing %ds before retry",
                      root, RETRY_PAUSE_SEC)
            time.sleep(RETRY_PAUSE_SEC)
            calls = td.bulk_trade_quote(root, "call", session_date, session_date, **kw)
            puts  = td.bulk_trade_quote(root, "put",  session_date, session_date, **kw)

            if calls is None and puts is None:
                # Determine whether the terminal is genuinely offline
                terminal_up = td.reachable(connect_timeout=RETRY_CONNECT_TIMEOUT)
                if terminal_up:
                    log.warning("poller: terminal contended — root %s skipped after retry", root)
                else:
                    log.warning("poller: terminal offline/unreachable (probe with %ds timeout failed)"
                                " — root %s skipped after retry",
                                RETRY_CONNECT_TIMEOUT, root)
                return root, None, None

        return root, calls, puts
    except Exception as e:  # noqa: BLE001
        log.warning("poller: fetch failed for %s: %s", root, e)
        return root, None, None


# ── OI loader ────────────────────────────────────────────────────────────────

# WP-RESOLVER: resolve the ThetaData store ONCE per poller session via the
# canonical resolver. A missing store must NEVER crash the live lane — it is
# logged at ERROR exactly once and surfaced as a meta note; every subsequent
# _load_oi_prev call degrades to None silently.
_OI_STORE_RESOLVED = False
_OI_STORE: Path | None = None


def _oi_store() -> Path | None:
    """Session-cached canonical store resolution for the t-1 OI reads."""
    global _OI_STORE_RESOLVED, _OI_STORE
    if not _OI_STORE_RESOLVED:
        try:
            from engine.thetadata_store import resolve_thetadata_store
            _OI_STORE = resolve_thetadata_store(
                required=False, purpose="live_flow_poller oi_prev")
        except Exception as e:  # noqa: BLE001 — resolver failure must not kill the lane
            log.error("poller: store resolution failed: %s", e)
            _OI_STORE = None
        _OI_STORE_RESOLVED = True
        if _OI_STORE is None:
            log.error(
                "poller: ThetaData store missing — t-1 OI unavailable for this "
                "whole session (OI-dependent context degrades; poller continues)")
    return _OI_STORE


def _load_oi_prev(root: str, session_date: str) -> object | None:
    """Load the latest pre-session OI from thetadata_eod; returns None gracefully.

    The exact source date is attached as ``DataFrame.attrs['oi_vintage']`` so the
    live event can retain point-in-time provenance.  The frame remains the return
    value for backward compatibility with existing callers and tests.
    """
    try:
        from engine import thetadata_store as ts
        from lib import nyse_calendar
        store = _oi_store()
        if store is None:
            return None
        session = datetime.strptime(session_date, "%Y-%m-%d").date()
        d_prev = nyse_calendar.last_session_on_or_before(
            session - timedelta(days=1)
        )
        for _ in range(5):
            oi = ts.oi_for_date(str(d_prev), root.upper(), store=store)
            if not oi.empty and "open_interest" in oi.columns:
                cols = [c for c in ("expiration", "strike", "right", "open_interest")
                        if c in oi.columns]
                out = oi[cols].dropna(subset=["open_interest"])
                out.attrs["oi_vintage"] = d_prev.isoformat()
                return out
            d_prev = nyse_calendar.last_session_on_or_before(
                d_prev - timedelta(days=1)
            )
        return None
    except Exception as e:  # noqa: BLE001
        log.debug("poller: oi_prev failed for %s: %s", root, e)
        return None


def _peak_rss_bytes() -> int:
    """Return the process lifetime high-water RSS in bytes."""
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # macOS reports bytes; Linux reports KiB.
    if sys.platform.startswith("linux"):
        value *= 1024
    return value


def _current_rss_bytes() -> int | None:
    """Return current resident bytes without adding a runtime dependency.

    Linux exposes the value through ``/proc``.  On macOS, ``proc_pidinfo`` gives
    the same resident-size counter without spawning ``ps`` on every phase probe.
    Unsupported hosts return ``None``; telemetry must never disturb the lane.
    """
    try:
        if sys.platform.startswith("linux"):
            statm = Path("/proc/self/statm").read_text(encoding="ascii").split()
            if len(statm) >= 2:
                return int(statm[1]) * int(os.sysconf("SC_PAGE_SIZE"))
            return None
        if sys.platform == "darwin":
            import ctypes  # noqa: PLC0415

            class _ProcTaskInfo(ctypes.Structure):
                _fields_ = [
                    ("virtual_size", ctypes.c_uint64),
                    ("resident_size", ctypes.c_uint64),
                    ("total_user", ctypes.c_uint64),
                    ("total_system", ctypes.c_uint64),
                    ("threads_user", ctypes.c_uint64),
                    ("threads_system", ctypes.c_uint64),
                    ("policy", ctypes.c_int32),
                    ("faults", ctypes.c_int32),
                    ("pageins", ctypes.c_int32),
                    ("cow_faults", ctypes.c_int32),
                    ("messages_sent", ctypes.c_int32),
                    ("messages_received", ctypes.c_int32),
                    ("syscalls_mach", ctypes.c_int32),
                    ("syscalls_unix", ctypes.c_int32),
                    ("csw", ctypes.c_int32),
                    ("threadnum", ctypes.c_int32),
                    ("numrunning", ctypes.c_int32),
                    ("priority", ctypes.c_int32),
                ]

            libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
            proc_pidinfo = libproc.proc_pidinfo
            proc_pidinfo.argtypes = [
                ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                ctypes.c_void_p, ctypes.c_int,
            ]
            proc_pidinfo.restype = ctypes.c_int
            info = _ProcTaskInfo()
            # PROC_PIDTASKINFO = 4 (libproc.h).
            read_n = proc_pidinfo(
                os.getpid(), 4, 0, ctypes.byref(info), ctypes.sizeof(info),
            )
            if read_n == ctypes.sizeof(info):
                return int(info.resident_size)
    except Exception:  # noqa: BLE001 — observability is strictly fail-soft
        return None
    return None


def _log_rss_phase(phase: str, *, cycle_n: int | None = None) -> tuple[int | None, int | None]:
    """Emit one bounded, machine-readable current/peak RSS phase sample."""
    try:
        current = _current_rss_bytes()
        peak = _peak_rss_bytes()
    except Exception as exc:  # noqa: BLE001 — telemetry cannot break the poller
        log.debug("poller: RSS phase telemetry failed phase=%s: %s", phase, exc)
        return None, None
    log.info(
        "poller: rss phase=%s cycle=%s current_rss_bytes=%s peak_rss_bytes=%s",
        phase,
        cycle_n if cycle_n is not None else "-",
        current if current is not None else "unavailable",
        peak if peak is not None else "unavailable",
    )
    return current, peak


# ── surface greek OI cache (Lane G) ────────────────────────────────────────────────
# The intraday greek grids weight per-contract exposure by prior-day OI (the OI-timing
# law: OPRA OI is EOD t-1, unchanged intraday). OI is therefore constant for the whole
# session — cache the {(exp,strike,right)→oi} map per surface root ONCE per session so the
# greek path costs no extra parquet read after the first cycle. Reuses _load_oi_prev (the
# same EOD-t-1 source the feed uses) — no new API fetch, no 8-request-ceiling contention.
_SURFACE_OI_CACHE: dict[str, dict] = {}


def _surface_oi_map(root: str, session_date: str) -> dict:
    """Session-cached {(exp_str,strike,right)→oi} for a surface root (Lane G). {} if absent."""
    key = f"{session_date}:{root.upper()}"
    if key in _SURFACE_OI_CACHE:
        return _SURFACE_OI_CACHE[key]
    oi_map: dict = {}
    try:
        oi_df = _load_oi_prev(root, session_date)  # cols: expiration, strike, right, open_interest
        if oi_df is not None:
            from scripts.build_flow_surface import oi_by_contract
            oi_map = oi_by_contract(oi_df)
    except Exception as e:  # noqa: BLE001 — never break a cycle for greek OI
        log.debug("poller: surface OI map failed for %s: %s", root, e)
        oi_map = {}
    _SURFACE_OI_CACHE[key] = oi_map
    if oi_map:
        log.info("poller: surface OI cached %s — %d contracts (EOD t-1)", root.upper(), len(oi_map))
    else:
        log.info("poller: surface OI empty for %s (greek grids will show 0 coverage)", root.upper())
    return oi_map


# ── prior-session close loader (FIX 3 — moneyness) ───────────────────────────

def _load_prev_close(root: str, session_date: str) -> float | None:
    """Return the prior-session close for `root` from the yahoo store.

    Looks up data/yahoo/{ROOT}.parquet, takes the LAST row with date STRICTLY
    before session_date (never session_date itself — lookahead law).
    Returns None if the store is absent or no qualifying row exists.
    INERT: never raises — missing store must not crash a cycle.
    """
    try:
        from lib import store
        import pandas as pd

        safe_root = root.upper().replace("^", "_").replace("=", "_").replace("/", "_")
        df = store.read("yahoo", safe_root)
        if df is None or df.empty or "close" not in df.columns:
            return None
        sess_dt = pd.Timestamp(session_date)
        # Strictly before session_date — no lookahead
        prior = df[df.index < sess_dt]
        if prior.empty:
            return None
        last_close = prior["close"].iloc[-1]
        if pd.isna(last_close) or float(last_close) <= 0:
            return None
        return float(last_close)
    except Exception as e:  # noqa: BLE001
        log.debug("poller: prev_close failed for %s: %s", root, e)
        return None


# ── state I/O ─────────────────────────────────────────────────────────────────

def _load_day_state(session_date: str) -> dict:
    p = _state_dir() / f"day_state_{session_date}.json"
    stage_path = _event_stage_path(session_date)
    stage_has_rows = stage_path.exists() and stage_path.stat().st_size > 0
    if not p.exists():
        if stage_has_rows:
            raise RuntimeError(
                f"day_state is missing for {session_date} while a learning stage exists"
            )
        return {}
    try:
        raw = _strict_json_loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise RuntimeError("day_state root must be an object")
        # Item 2: version check — discard day_state written by an older schema version.
        # full_day mode re-accumulates from zero so nothing is lost.
        # time_window mode also resets here; one full-day cycle follows before windowed
        # increments resume (watermarks start empty and full-day pull is safe).
        from engine.live_flow import DAY_STATE_VERSION  # noqa: PLC0415
        stored_ver = raw.get("schema_version", 1)
        if type(stored_ver) is not int:
            raise RuntimeError("day_state schema_version must be an exact integer")
        if stored_ver < DAY_STATE_VERSION:
            if stage_has_rows:
                raise RuntimeError(
                    "stale day_state cannot be discarded while this session has a learning stage"
                )
            log.info(
                "poller: day_state schema_version=%d < current=%d — discarding stale state "
                "(full_day mode will re-accumulate from zero this cycle)",
                stored_ver, DAY_STATE_VERSION,
            )
            return {}
        if stored_ver != DAY_STATE_VERSION:
            raise RuntimeError(
                f"day_state schema_version={stored_ver} is newer than supported "
                f"{DAY_STATE_VERSION}"
            )
        # emitted_ids is serialised as a list
        raw["emitted_ids"] = set(raw.get("emitted_ids", []))
        # Per-contract state is root-scoped in v5. A legacy three-part key is
        # never coerced because that would reintroduce cross-ticker contamination.
        def _restore_key(k: str):
            try:
                parts = json.loads(k)
                if isinstance(parts, list) and len(parts) == 4:
                    return (str(parts[0]), str(parts[1]), float(parts[2]), str(parts[3]))
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"invalid root-scoped contract state key: {k!r}")

        def _restore_seq_key(k: str):
            # seen_sequences keys are now 4-tuples: (root:str, exp:str, strike:float, right:str)
            # (schema_version>=2).  A 3-tuple key would be pre-v2 residue and is discarded
            # by the version gate above, so only the 4-tuple form is expected here.
            try:
                parts = json.loads(k)
                if isinstance(parts, list) and len(parts) == 4:
                    return (str(parts[0]), str(parts[1]), float(parts[2]), str(parts[3]))
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"invalid root-scoped sequence state key: {k!r}")
        raw["contract_vol"] = {
            _restore_key(k): v for k, v in raw.get("contract_vol", {}).items()
        }
        raw["notability_history"] = {
            _restore_key(k): v for k, v in raw.get("notability_history", {}).items()
        }
        raw["seen_sequences"] = {
            _restore_seq_key(k): v for k, v in raw.get("seen_sequences", {}).items()
        }
        # Tide accumulators — all string-keyed, load as-is
        for tide_key in ("market_tide_minutes", "sector_tide", "dte_tide",
                         "root_minutes", "root_strikes", "root_expiries",
                         "root_top_contracts", "sweep_clusters"):
            if tide_key not in raw:
                raw[tide_key] = {}
        if not isinstance(raw.get("all_events", []), list):
            raise RuntimeError("day_state all_events must be a list")
        if not isinstance(raw.get("pending_learning_events", []), list):
            raise RuntimeError("day_state pending_learning_events must be a list")
        if not isinstance(raw.get("cycle_watermarks", {}), dict):
            raise RuntimeError("day_state cycle_watermarks must be an object")
        if raw.get("source_asof") is not None:
            raw["source_asof"] = _canonical_utc_timestamp(
                raw["source_asof"], field="day_state.source_asof",
            )
        raw.setdefault("pending_learning_events", [])
        raw.setdefault("cycle_watermarks", {})
        return raw
    except Exception as e:  # noqa: BLE001
        # Once a state pathname exists, corruption is never equivalent to an
        # empty session. In particular, the vulnerable transaction interval has
        # a durable pending WAL but intentionally no stage yet; fail-open here
        # would refetch and recluster the same prints under new event IDs.
        raise RuntimeError(f"cannot recover day_state for {session_date}") from e


def _state_key(k) -> str:
    """Convert a tuple or other key to a JSON-safe string key."""
    if isinstance(k, (list, tuple)):
        return json.dumps([str(x) for x in k])
    return str(k)


def _state_json_default(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise TypeError("naive datetime is not valid durable state")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    item = getattr(value, "item", None)
    if callable(item):
        scalar = item()
        if type(scalar) in (str, int, float, bool) or scalar is None:
            return scalar
    raise TypeError(f"unsupported day_state value: {type(value).__name__}")


def _save_day_state(session_date: str, state: dict) -> Path:
    p = _state_dir() / f"day_state_{session_date}.json"
    lock_path = p.with_suffix(p.suffix + ".lock")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        from engine.live_flow import DAY_STATE_VERSION as _DSV  # noqa: PLC0415
        raw: dict = {}
        raw["schema_version"] = _DSV   # Item 2: stamp version for forward-compat checks
        raw["emitted_ids"] = list(state.get("emitted_ids", set()))
        raw["all_events"]  = state.get("all_events", [])
        raw["root_gross_today"] = state.get("root_gross_today", {})
        raw["pending_learning_events"] = state.get("pending_learning_events", [])
        raw["cycle_watermarks"] = state.get("cycle_watermarks", {})
        # Source age survives a process restart.  A fully failed recovery cycle
        # must keep the last represented response clock instead of looking new.
        source_asof = state.get("source_asof")
        raw["source_asof"] = (
            _canonical_utc_timestamp(source_asof, field="day_state.source_asof")
            if source_asof is not None else None
        )
        # Tuple-keyed dicts → string-keyed for JSON serialisation
        raw["contract_vol"]      = {_state_key(k): v
                                    for k, v in state.get("contract_vol", {}).items()}
        raw["notability_history"] = {_state_key(k): v
                                     for k, v in state.get("notability_history", {}).items()}
        raw["seen_sequences"]     = {_state_key(k): v
                                     for k, v in state.get("seen_sequences", {}).items()}
        # Tide accumulators — all string-keyed, serialise directly
        for tide_key in ("market_tide_minutes", "sector_tide", "dte_tide",
                         "root_minutes", "root_strikes", "root_expiries",
                         "root_top_contracts", "sweep_clusters"):
            raw[tide_key] = state.get(tide_key, {})

        serialised = json.dumps(
            raw,
            default=_state_json_default,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"

        # Size guard: warn if day-state exceeds threshold
        byte_count = len(serialised.encode())
        if byte_count > DAY_STATE_SIZE_WARN_BYTES:
            log.warning(
                "poller: day_state size %d MB exceeds %d MB threshold — "
                "consider reducing top_names or retention_hours",
                byte_count // (1024 * 1024),
                DAY_STATE_SIZE_WARN_BYTES // (1024 * 1024),
            )

        encoded = serialised.encode("utf-8")
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{p.name}.", suffix=".tmp", dir=p.parent,
        )
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, p)
            _fsync_directory(p.parent)
        finally:
            if tmp.exists():
                tmp.unlink()
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return p


def _drain_pending_learning_events(
    session_date: str,
    state: dict,
    *,
    event_stager,
    cutoff_ts: str | None = None,
) -> tuple[dict, list[dict]]:
    """Idempotently stage the durable cycle WAL, then durably clear it.

    The first state save owns the engine accumulators and fixed decision clocks.
    A crash at any later boundary can only replay the same semantic event IDs and
    clocks into the append-only stage; it can never re-run an earlier print
    through the clustering engine under a new event identity.
    """
    pending = state.get("pending_learning_events", [])
    if not isinstance(pending, list):
        raise RuntimeError("pending learning WAL must be a list")
    if not pending:
        return state, []
    if event_stager is None:
        raise RuntimeError("pending learning WAL requires a durable event stager")

    durable_fields = {
        "available_at", "published_at", "source_snapshot_asof", "anchor_strategy",
    }
    pending_ids: list[str] = []
    for event in pending:
        event_id = event.get("id") if isinstance(event, dict) else None
        if (
            type(event_id) is not str
            or not event_id
            or event_id != event_id.strip()
        ):
            raise RuntimeError("pending learning WAL contains an invalid event id")
        if durable_fields.intersection(event):
            raise RuntimeError("pending learning WAL contains post-durability fields")
        pending_ids.append(event_id)
    if len(set(pending_ids)) != len(pending_ids):
        raise RuntimeError("pending learning WAL contains duplicate event ids")

    staged = list(event_stager(session_date, [dict(event) for event in pending]))
    if len(staged) != len(pending):
        raise RuntimeError("event stager did not reconcile every pending learning event")
    staged_ids: list[str] = []
    for pending_event, staged_event in zip(pending, staged, strict=True):
        staged_id = staged_event.get("id") if isinstance(staged_event, dict) else None
        if (
            type(staged_id) is not str
            or not staged_id
            or staged_id != staged_id.strip()
        ):
            raise RuntimeError("staged learning event has an invalid id")
        staged_ids.append(staged_id)
        staged_decision = {
            key: value for key, value in staged_event.items() if key not in durable_fields
        }
        if staged_decision != pending_event:
            raise RuntimeError(
                f"event stager changed pending decision payload: {pending_event['id']}"
            )
    if staged_ids != pending_ids or len(set(staged_ids)) != len(staged_ids):
        raise RuntimeError("event stager did not preserve pending event identities")

    existing_events = list(state.get("all_events", []))
    by_id: dict[str, dict] = {}
    for event in existing_events:
        event_id = event.get("id") if isinstance(event, dict) else None
        if type(event_id) is not str or not event_id:
            raise RuntimeError("day_state all_events contains an invalid event id")
        prior = by_id.get(event_id)
        if prior is not None and prior != event:
            raise RuntimeError(f"day_state contains conflicting event payloads: {event_id}")
        by_id[event_id] = event
    for event in staged:
        event_id = event.get("id") if isinstance(event, dict) else None
        if type(event_id) is not str or not event_id:
            raise RuntimeError("staged learning event has an invalid id")
        prior = by_id.get(event_id)
        if prior is not None and prior != event:
            raise RuntimeError(f"staged event conflicts with day_state payload: {event_id}")
        if prior is None:
            existing_events.append(event)
            by_id[event_id] = event
    if cutoff_ts is not None:
        from engine.live_flow import trim_events  # noqa: PLC0415
        existing_events = trim_events(existing_events, cutoff_ts)

    cleared = dict(state)
    cleared["all_events"] = existing_events
    cleared["pending_learning_events"] = []
    _save_day_state(session_date, cleared)
    return cleared, staged


# ── day-state retention sweep ────────────────────────────────────────────────
# day_state files run 50-70 MB per session and R2 archive pruning does not cover
# them — without a local sweep they accumulate unbounded (~500 MB/2wk measured).

DAY_STATE_RETENTION_DAYS_DEFAULT = 5
_DAY_STATE_RE = re.compile(r"^day_state_(\d{4}-\d{2}-\d{2})(?:\.tmp)?\.json$")


def _stale_pending_learning_sessions(current_session: str) -> list[str]:
    """Return retained prior sessions with an undrained durable learning WAL.

    This scan intentionally precedes retention pruning. A process death near the
    close can leave exact decision clocks in yesterday's state but no availability
    receipt; deleting or silently skipping that state would erase the only proof
    that the batch existed. Prior-date WALs require reviewed quarantine/recovery
    and are never backdated with a clock from a later exchange date.
    """
    stale: list[str] = []
    for path in sorted(_state_dir().glob("day_state_*.json")):
        match = _DAY_STATE_RE.fullmatch(path.name)
        if match is None:
            continue
        session = match.group(1)
        if session == current_session:
            continue
        try:
            payload = _strict_json_loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"cannot inspect retained prior day_state for stranded WAL: {path}"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"retained prior day_state is not an object: {path}")
        pending = payload.get("pending_learning_events", [])
        if not isinstance(pending, list):
            raise RuntimeError(f"retained prior day_state has invalid pending WAL: {path}")
        if pending:
            stale.append(session)
    return stale


def _select_prunable_day_states(
    filenames: list[str],
    session_date: str,
    keep_days: int,
) -> list[str]:
    """Return the day_state filenames that fall outside the retention window.

    Pure selection (no I/O).  Keeps the `keep_days` most recent embedded dates
    present in `filenames` — files only exist for trading sessions, so the count
    is in sessions, not calendar days.  The current session's files are NEVER
    selected regardless of the window.  Filenames that don't match the
    day_state pattern or carry an invalid date are never selected (and don't
    consume keep slots).  Crash-residue .tmp.json files follow the same date
    rule as their clean counterparts.
    """
    keep_days = max(1, int(keep_days))
    dated: list[tuple[str, str]] = []
    for fn in filenames:
        m = _DAY_STATE_RE.match(Path(fn).name)
        if not m:
            continue
        try:
            date.fromisoformat(m.group(1))
        except ValueError:
            continue
        dated.append((m.group(1), fn))
    keep_dates = set(sorted({d for d, _ in dated}, reverse=True)[:keep_days])
    keep_dates.add(session_date)
    return sorted(fn for d, fn in dated if d not in keep_dates)


def _prune_day_states(session_date: str, cfg: dict) -> None:
    """Delete local day_state files older than the newest state_retention_days
    sessions (default 5).  The current session's file is never touched; every
    deletion is logged.  INERT: never raises.
    """
    try:
        keep_days = int(cfg.get("state_retention_days", DAY_STATE_RETENTION_DAYS_DEFAULT))
        sdir = _state_dir()
        names = sorted(p.name for p in sdir.glob("day_state_*") if p.is_file())
        doomed = _select_prunable_day_states(names, session_date, keep_days)
        if not doomed:
            log.debug("poller: day_state retention sweep — nothing to prune (keep=%d sessions)",
                      keep_days)
            return
        n_pruned, freed = 0, 0
        for name in doomed:
            p = sdir / name
            try:
                size = p.stat().st_size
                p.unlink()
                n_pruned += 1
                freed += size
                log.info("poller: pruned day_state %s (%.1f MB)", name, size / (1024 * 1024))
            except FileNotFoundError:
                pass
            except Exception as e:  # noqa: BLE001
                log.warning("poller: could not prune day_state %s: %s", name, e)
        log.info(
            "poller: day_state retention sweep — pruned %d file(s), freed %.1f MB "
            "(keep=%d sessions)",
            n_pruned, freed / (1024 * 1024), keep_days,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("poller: day_state retention sweep failed: %s", e)


# ── JSON file writers ─────────────────────────────────────────────────────────

def _write_json(filename: str, obj: dict) -> Path:
    """Atomic write to data/live_flow_out/<filename>."""
    out = _out_dir() / filename
    tmp = out.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(obj, default=str))
    tmp.rename(out)
    return out


# ── R2 upload ─────────────────────────────────────────────────────────────────

def _r2_client():
    """Build a boto3 S3 client for R2, or None if creds absent."""
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3
        from botocore.config import Config
        kw = dict(region_name="auto", signature_version="s3v4",
                  max_pool_connections=16,
                  retries={"max_attempts": 3, "mode": "standard"})
        try:
            cfg = Config(**kw, request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client("s3", endpoint_url=ep,
                            aws_access_key_id=ak,
                            aws_secret_access_key=sk,
                            config=cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("poller: R2 client build failed: %s", e)
        return None


def _upload_r2(s3, bucket: str, local_path: Path, r2_key: str) -> bool:
    """Upload a local file to R2.  Returns True on success."""
    try:
        s3.upload_file(
            str(local_path),
            bucket,
            r2_key,
            ExtraArgs={"ContentType": "application/json"},
        )
        log.info("poller: R2 upload ok → %s", r2_key)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("poller: R2 upload failed for %s: %s", r2_key, e)
        return False


def _publish_event_stage(s3, bucket: str, session_date: str) -> bool:
    """Serialize publication-receipt/index mutation across process overlap."""
    stage_root = _event_stage_path(session_date).parent
    lock_path = stage_root / "publish.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            return _publish_event_stage_locked(s3, bucket, session_date)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _publish_event_stage_locked(s3, bucket: str, session_date: str) -> bool:
    """Publish/retry local stages, then advertise only proven remote sessions.

    Proven closed sessions are immutable.  Their stored byte count is therefore
    a cheap unchanged-prefix fast path; only the current, never-proven, or
    size-changed stages are read, parsed, and hashed each poll.  After the R2
    dates index succeeds, proven local stages and receipts are retained to the
    same bounded catch-up window while R2 remains the longer-lived archive.
    """
    stage_root = _event_stage_path(session_date).parent
    current_path = stage_root / f"{session_date}.jsonl"
    current_required = current_path.exists()
    try:
        published = _load_event_publish_receipts()
    except RuntimeError as exc:
        log.warning("poller: refusing event index publish: %s", exc)
        return False

    local_sessions = sorted(
        candidate.stem for candidate in stage_root.glob("????-??-??.jsonl")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate.stem)
    )
    local_receipts: dict[str, dict[str, object]] = {}
    local_payloads: dict[str, bytes] = {}
    rejected_sessions: set[str] = set()
    for candidate in local_sessions:
        local_path = stage_root / f"{candidate}.jsonl"
        prior_receipt = published.get(candidate)
        try:
            local_size = local_path.stat().st_size
        except OSError as exc:
            log.warning("poller: event stage unreadable for %s: %s", candidate, exc)
            rejected_sessions.add(candidate)
            continue
        if (
            candidate != session_date
            and prior_receipt is not None
            and prior_receipt.get("bytes") == local_size
        ):
            local_receipts[candidate] = dict(prior_receipt)
            continue
        try:
            raw = local_path.read_bytes()
        except OSError as exc:
            log.warning("poller: event stage unreadable for %s: %s", candidate, exc)
            rejected_sessions.add(candidate)
            continue
        if not raw or not raw.endswith(b"\n"):
            log.warning("poller: refusing empty/torn event stage publish for %s", candidate)
            rejected_sessions.add(candidate)
            continue
        try:
            _parse_event_stage_bytes(
                candidate, raw, path=local_path, require_complete=True,
            )
        except RuntimeError as exc:
            log.warning("poller: refusing invalid event stage publish for %s: %s", candidate, exc)
            rejected_sessions.add(candidate)
            continue
        receipt = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        prior_receipt = published.get(candidate)
        if prior_receipt is not None:
            prior_bytes = int(prior_receipt["bytes"])
            if len(raw) < prior_bytes:
                log.warning("poller: refusing event-stage shrink for %s", candidate)
                rejected_sessions.add(candidate)
                continue
            if len(raw) == prior_bytes:
                if receipt["sha256"] != prior_receipt["sha256"]:
                    log.warning("poller: refusing same-size event-stage rewrite for %s", candidate)
                    rejected_sessions.add(candidate)
                    continue
            else:
                prior_prefix = raw[:prior_bytes]
                if (
                    not prior_prefix.endswith(b"\n")
                    or hashlib.sha256(prior_prefix).hexdigest() != prior_receipt["sha256"]
                ):
                    log.warning("poller: refusing changed event-stage prefix for %s", candidate)
                    rejected_sessions.add(candidate)
                    continue
        local_receipts[candidate] = receipt
        local_payloads[candidate] = raw

    # Retry every never-proven or valid append extension. Equal proven bytes do
    # not need another PUT; upload candidates use immutable snapshots below.
    candidates = [
        value for value in local_sessions
        if value in local_receipts and published.get(value) != local_receipts[value]
    ]
    current_ok = (
        session_date not in rejected_sessions
        and published.get(session_date) is not None
        and published.get(session_date) == local_receipts.get(session_date)
    )
    any_success = False
    for candidate in candidates:
        receipt = local_receipts.get(candidate)
        raw = local_payloads.get(candidate)
        if receipt is None or raw is None:
            continue
        snapshot_path: Path | None = None
        try:
            fd, snapshot_name = tempfile.mkstemp(
                dir=stage_root,
                prefix=f".publish-{candidate}-",
                suffix=".jsonl",
            )
            snapshot_path = Path(snapshot_name)
            with os.fdopen(fd, "wb") as snapshot:
                snapshot.write(raw)
                snapshot.flush()
                os.fsync(snapshot.fileno())
            ok = _upload_r2(
                s3, bucket, snapshot_path,
                R2_PREFIX + f"events/{candidate}.jsonl",
            )
        except OSError as exc:
            log.warning("poller: event-stage snapshot failed for %s: %s", candidate, exc)
            ok = False
        finally:
            if snapshot_path is not None:
                try:
                    snapshot_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    log.warning(
                        "poller: event-stage snapshot cleanup failed for %s: %s",
                        candidate, exc,
                    )
        if ok:
            published[candidate] = receipt
            any_success = True
        if candidate == session_date:
            current_ok = ok

    if not published:
        return False

    historical_candidates_ok = all(
        candidate not in rejected_sessions
        and published.get(candidate) == local_receipts.get(candidate)
        for candidate in local_sessions
    )

    try:
        _write_event_publish_receipts(published)
        dates_index = _write_event_dates_index(set(published))
    except (OSError, RuntimeError) as exc:
        log.warning("poller: event publication receipt/index write failed: %s", exc)
        return False
    index_ok = _upload_r2(
        s3, bucket, dates_index, R2_PREFIX + "events/dates.json",
    )
    if index_ok:
        retained_sessions = set(sorted(published)[-EVENT_STAGE_RETAIN_SESSIONS:])
        for candidate in local_sessions:
            if (
                candidate in published
                and candidate not in retained_sessions
                and candidate not in rejected_sessions
                and local_receipts.get(candidate) == published.get(candidate)
            ):
                try:
                    (stage_root / f"{candidate}.jsonl").unlink()
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    log.warning(
                        "poller: could not prune proven event stage %s: %s",
                        candidate, exc,
                    )
        remaining_local_sessions = {
            path.stem for path in stage_root.glob("????-??-??.jsonl")
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem)
        }
        receipt_keep_sessions = retained_sessions | (
            set(published) & remaining_local_sessions
        )
        retained_receipts = {
            key: published[key] for key in sorted(receipt_keep_sessions)
        }
        try:
            _write_event_publish_receipts(retained_receipts)
        except (OSError, RuntimeError) as exc:
            log.warning("poller: event receipt retention write failed: %s", exc)
            return False
    requested_stage_ok = current_ok if current_required else historical_candidates_ok
    return requested_stage_ok and index_ok


def _list_archive_keys(s3, bucket: str) -> list[str]:
    """List all keys under live_flow/archive/."""
    try:
        out, tok = [], None
        while True:
            kw: dict = {"Bucket": bucket, "Prefix": R2_PREFIX + "archive/"}
            if tok:
                kw["ContinuationToken"] = tok
            r = s3.list_objects_v2(**kw)
            for o in r.get("Contents", []):
                out.append(o["Key"])
            if not r.get("IsTruncated"):
                return out
            tok = r.get("NextContinuationToken")
    except Exception as e:  # noqa: BLE001
        log.warning("poller: list archive keys failed: %s", e)
        return []


def _prune_archive(s3, bucket: str, older_than_hours: int = 48) -> None:
    """Delete archive objects older than older_than_hours."""
    keys = _list_archive_keys(s3, bucket)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    to_delete = []
    for k in keys:
        # key format: live_flow/archive/YYYYMMDDTHH.json
        stem = Path(k).stem  # e.g. "2026070214"
        try:
            ts = datetime.strptime(stem, "%Y%m%dT%H").replace(tzinfo=timezone.utc)
            if ts < cutoff:
                to_delete.append(k)
        except Exception:  # noqa: BLE001
            pass
    if to_delete:
        try:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in to_delete]})
            log.info("poller: pruned %d archive objects older than %dh", len(to_delete), older_than_hours)
        except Exception as e:  # noqa: BLE001
            log.warning("poller: archive prune failed: %s", e)


# ── baseline loader ───────────────────────────────────────────────────────────

def _load_baselines() -> dict:
    p = config.data_dir() / "live_flow_baselines" / "baselines.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("poller: could not load baselines: %s", e)
        return {}


def _load_unusual_baseline() -> dict:
    """Load the 30-session volume baseline artifact (flow.unusual_baseline/v1).

    Only loaded when UNUSUAL_BASELINE=1 is set in env AND the artifact is present
    and fresh (asof within 5 NYSE sessions of today).  Returns {} otherwise (fail-open).

    DEFAULT OFF: UNUSUAL_BASELINE env is NOT set in any plist — the poller lane
    owner flips it.  When absent or stale the poller falls back to the current
    heuristic exactly as before.
    """
    if os.environ.get("UNUSUAL_BASELINE") != "1":
        return {}

    p = config.data_dir() / "live_flow_out" / "unusual_baseline.json"
    if not p.exists():
        log.debug("poller: unusual_baseline artifact absent — falling back to heuristic")
        return {}

    try:
        blob = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("poller: could not load unusual_baseline: %s", e)
        return {}

    # Freshness check: asof within 5 NYSE sessions of today.
    try:
        from lib.nyse_calendar import last_session_on_or_before, is_session
        from datetime import date as _date
        asof_str = blob.get("asof", "")
        asof_dt = _date.fromisoformat(asof_str)
        today = _date.today()
        # Count sessions between asof and today
        sessions_since = 0
        d = asof_dt + __import__("datetime").timedelta(days=1)
        while d <= today:
            if is_session(d):
                sessions_since += 1
            d += __import__("datetime").timedelta(days=1)
        if sessions_since > 5:
            log.info(
                "poller: unusual_baseline stale (asof=%s, %d sessions ago > 5) — "
                "falling back to heuristic",
                asof_str, sessions_since,
            )
            return {}
        log.info("poller: unusual_baseline loaded (asof=%s, sessions_since=%d)",
                 asof_str, sessions_since)
        return blob
    except Exception as e:  # noqa: BLE001
        log.warning("poller: unusual_baseline freshness check failed: %s — using artifact", e)
        return blob


# ── session date ─────────────────────────────────────────────────────────────

def _session_date(override: str | None = None) -> str:
    """Return session date as YYYY-MM-DD.

    Uses America/New_York to determine the current date during market hours.
    ``--date`` is retained only for legacy diagnostics; it is unsafe as a live
    smoke because this combined poller mutates current/replay output surfaces.
    """
    if override:
        return override
    return datetime.now(ET).strftime("%Y-%m-%d")


# ── single-cycle logic ────────────────────────────────────────────────────────

def run_cycle(
    roots: list[str],
    session_date: str,
    delta_mode: str,
    day_state: dict,
    baselines: dict,
    cfg: dict,
    cycle_watermarks: dict,   # FIX 2: {root: {"ts": str, "seq": float}} — mutated in place
    forced_full_day: bool = False,  # True when --date override forces full_day regardless of probe
    unusual_baseline: dict | None = None,  # flow.unusual_baseline/v1 artifact; None = fall back to heuristic
    event_stager=None,
    cycle_n: int | None = None,  # observability only; never enters signal/state clocks
    cycle_started_at: str | None = None,
    observed_start_to_start_sec: float | None = None,
) -> tuple[dict, dict, dict, dict, dict]:
    """Run one poll cycle.  Returns (feed_data, heat_data, meta_data, updated_day_state, tide_day_state).

    Fetches all roots in parallel (max_concurrent=2), runs the engine, aggregates.

    FIX 2 — per-root watermarks + overlap dedup:
      cycle_watermarks[root] = {"ts": last_trade_ts_str, "seq": max_sequence_seen}
      time_window mode: start_time = watermark_ts - 30s overlap (RTH open on first cycle).
      Row-level dedup inside the engine (seen_sequences state) makes overlap safe.
      full_day mode: always pulls full day; engine dedup ensures idempotency.

    FIX 3 — prev_close loaded per-root from yahoo store for honest moneyness.
    """
    from engine import live_flow as lf
    import pandas as pd

    max_w = _max_concurrent(cfg)
    etf_floor = cfg.get("etf_floor", 1_000_000)
    name_floor = cfg.get("name_floor", 250_000)
    for label, value in (("etf_floor", etf_floor), ("name_floor", name_floor)):
        if type(value) is not int or value < 0:
            raise ValueError(f"{label} must be an exact non-negative integer")

    etf_anchors = [a.upper() for a in (cfg.get("etf_anchors") or [])]
    if not etf_anchors:
        from scripts.live_flow_poller import _resolve_universe
        etf_anchors_set = set(_resolve_universe(cfg)[:23])  # rough default
    else:
        etf_anchors_set = set(etf_anchors)

    cycle_t0 = time.perf_counter()
    cycle_started_at = _canonical_utc_timestamp(
        _utc_now_iso() if cycle_started_at is None else cycle_started_at,
        field="cycle_started_at",
    )
    observed_start_to_start_sec = _observed_interval_sec(
        observed_start_to_start_sec,
    )
    poll_floor_sec = _poll_floor_sec(cfg)
    _log_rss_phase("pre_fetch", cycle_n=cycle_n)

    # FIX 2 — compute per-root start_time for time_window mode
    # For full_day mode start_time is always None (pull full day; dedup handles idempotency)
    RTH_OPEN = "09:30:00"
    _OVERLAP_SEC = 30   # 30s overlap safety window

    def _root_start_time(root: str) -> str | None:
        """Return start_time for this root's fetch, or None (full day)."""
        if delta_mode != "time_window":
            return None
        wm = cycle_watermarks.get(root)
        if not wm or not wm.get("ts"):
            # First cycle for this root → start from RTH open
            return RTH_OPEN
        # Advance watermark by subtracting overlap
        try:
            wm_dt = datetime.fromisoformat(wm["ts"].replace("Z", "+00:00"))
            wm_et = wm_dt.astimezone(ET)
            overlap_dt = wm_et - timedelta(seconds=_OVERLAP_SEC)
            return overlap_dt.strftime("%H:%M:%S")
        except Exception:  # noqa: BLE001
            return RTH_OPEN

    if day_state.get("pending_learning_events"):
        raise RuntimeError("pending learning WAL must be drained before a new fetch cycle")
    all_events: list[dict]  = list(day_state.get("all_events", []))
    pending_learning_events: list[dict] = []
    root_gross: dict        = dict(day_state.get("root_gross_today", {}))
    emitted_ids: set[str]   = set(day_state.get("emitted_ids", set()))
    contract_vol: dict      = dict(day_state.get("contract_vol", {}))
    notab_hist: dict        = dict(day_state.get("notability_history", {}))
    seen_sequences: dict    = dict(day_state.get("seen_sequences", {}))

    # Tide accumulator state — carry forward across cycles
    market_tide_minutes: dict = dict(day_state.get("market_tide_minutes", {}))
    sector_tide: dict         = {k: dict(v) for k, v in day_state.get("sector_tide", {}).items()}
    dte_tide: dict            = {k: dict(v) for k, v in day_state.get("dte_tide", {}).items()}
    root_minutes_acc: dict    = {k: dict(v) for k, v in day_state.get("root_minutes", {}).items()}
    root_strikes_acc: dict    = {k: dict(v) for k, v in day_state.get("root_strikes", {}).items()}
    root_expiries_acc: dict   = {k: dict(v) for k, v in day_state.get("root_expiries", {}).items()}
    root_top_contr: dict      = {k: list(v) for k, v in day_state.get("root_top_contracts", {}).items()}
    sweep_clusters_acc: dict  = dict(day_state.get("sweep_clusters", {}))

    heat_rows: list[dict]   = []
    unusual_by_root: dict   = {}
    meta_notes: list[str]   = []
    requests_count          = 0

    # ── Lane G: surface greek inputs (per-contract quotes tapped from the raw tape) ──
    # For SURFACE roots only, extract the freshest per-contract NBBO mid this cycle from
    # calls_df/puts_df BEFORE they're freed (line ~"del calls_df"), so the greek grids get
    # per-contract quotes without any extra API fetch. Bounded: surface roots only, one
    # quote per contract. Fenced so a failure never disturbs the feed. Timed → meta.
    try:
        from scripts.build_flow_surface import resolve_surface_roots as _rsr
        _surface_root_set = set(_rsr(cfg, root_gross))
    except Exception:  # noqa: BLE001
        _surface_root_set = set()
    surface_quotes: dict[str, list] = {}
    surface_spot_fallback: dict[str, float] = {}
    surface_quote_sec: float = 0.0

    # Fetch in parallel (max_concurrent=2); per-root start_time in time_window mode
    fetch_results: dict[str, tuple] = {}
    source_response_times: list[str] = []
    with ThreadPoolExecutor(max_workers=max_w) as pool:
        futs = {
            pool.submit(
                _fetch_root, root, session_date,
                _root_start_time(root),   # per-root watermark start
                None,                     # end_time always None ("now")
            ): root
            for root in roots
        }
        for fut in as_completed(futs):
            r, calls_df, puts_df = fut.result()
            # This is the first honest clock at which the fetched root payload is
            # available to the poller.  A cycle-start timestamp would predate the
            # network response and create false point-in-time provenance.
            observed_at = _utc_now_iso()
            fetch_results[r] = (calls_df, puts_df, observed_at)
            if calls_df is not None or puts_df is not None:
                source_response_times.append(observed_at)
            requests_count += 2  # two calls per root (call + put)
    _log_rss_phase("post_fetch", cycle_n=cycle_n)

    # Process each root
    for root in roots:
        calls_df, puts_df, observed_at = fetch_results.get(root, (None, None, None))
        if calls_df is None and puts_df is None:
            log.debug("poller: skip %s (both legs failed)", root)
            continue

        # Derive, but do not yet commit, the fetched-root watermark. It advances
        # only after process_batch succeeds and its state has been merged.
        candidate_watermark = dict(cycle_watermarks.get(root, {}))
        for df_part in (calls_df, puts_df):
            if df_part is not None and not df_part.empty and "trade_timestamp" in df_part.columns:
                try:
                    import pandas as pd
                    max_ts = df_part["trade_timestamp"].dropna().max()
                    max_seq_val = None
                    if "sequence" in df_part.columns:
                        max_seq_val = float(pd.to_numeric(
                            df_part["sequence"], errors="coerce").dropna().max())
                    if max_ts and str(max_ts) not in ("NaT", "nan", ""):
                        cur_ts  = candidate_watermark.get("ts")
                        if cur_ts is None or str(max_ts) > cur_ts:
                            wm_new = {"ts": str(max_ts)}
                            if max_seq_val is not None and not (max_seq_val != max_seq_val):
                                wm_new["seq"] = max_seq_val
                            candidate_watermark = wm_new
                except Exception as e:  # noqa: BLE001
                    log.debug("poller: watermark advance failed for %s: %s", root, e)

        # FIX 3 — load prev_close for honest moneyness
        prev_close = _load_prev_close(root, session_date)

        # Per-root prior state — pass ALL accumulators so the engine starts from the
        # running cross-root total rather than empty dicts.  The engine deep-copies each
        # dict on entry (lines 399-416 of live_flow.py), so passing the live references
        # here is safe — no aliasing hazard between concurrent workers because fetch is
        # already done (parallel phase is over) and processing is sequential.
        prior = {
            "emitted_ids":      emitted_ids,
            "contract_vol":     contract_vol,
            "notability_history": notab_hist,
            "root_gross_today": root_gross,
            "seen_sequences":   seen_sequences,
            # FIX: tide accumulators were missing — each root was starting fresh and the
            # last root's result was overwriting all prior roots' data (drop-all bug).
            "market_tide_minutes": market_tide_minutes,
            "sector_tide":         sector_tide,
            "dte_tide":            dte_tide,
            "root_minutes":        root_minutes_acc,
            "root_strikes":        root_strikes_acc,
            "root_expiries":       root_expiries_acc,
            "root_top_contracts":  root_top_contr,
            "sweep_clusters":      sweep_clusters_acc,
        }

        try:
            oi_prev = _load_oi_prev(root, session_date)
            oi_vintage = None
            if oi_prev is not None:
                try:
                    oi_vintage = oi_prev.attrs.get("oi_vintage")
                except Exception:  # noqa: BLE001 - provenance absence is an honest null
                    oi_vintage = None
            result  = lf.process_batch(
                calls_df=calls_df,
                puts_df=puts_df,
                session_date=session_date,
                batch_ts=observed_at,
                prior_state=prior,
                oi_prev=oi_prev,
                baselines=baselines,
                etf_floor=etf_floor,
                name_floor=name_floor,
                etf_anchors=list(etf_anchors_set),
                prev_close=prev_close,
                oi_vintage=oi_vintage,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("poller: engine failed for %s: %s", root, e)
            continue

        # Merge state
        state_out = result.get("state", {})
        emitted_ids     = state_out.get("emitted_ids", emitted_ids)
        contract_vol    = state_out.get("contract_vol", contract_vol)
        notab_hist      = state_out.get("notability_history", notab_hist)
        root_gross      = state_out.get("root_gross_today", root_gross)
        seen_sequences  = state_out.get("seen_sequences", seen_sequences)

        # Merge tide accumulators (engine returns updated dicts mutated in-place)
        market_tide_minutes = state_out.get("market_tide_minutes", market_tide_minutes)
        sector_tide         = state_out.get("sector_tide", sector_tide)
        dte_tide            = state_out.get("dte_tide", dte_tide)
        root_minutes_acc    = state_out.get("root_minutes", root_minutes_acc)
        root_strikes_acc    = state_out.get("root_strikes", root_strikes_acc)
        root_expiries_acc   = state_out.get("root_expiries", root_expiries_acc)
        root_top_contr      = state_out.get("root_top_contracts", root_top_contr)
        sweep_clusters_acc  = state_out.get("sweep_clusters", sweep_clusters_acc)
        if candidate_watermark:
            cycle_watermarks[root] = candidate_watermark

        # Decision completion is later than fetch observation. Durably stage the
        # events before they can enter the capped/retained display feed.
        new_events = list(result.get("events", []))
        if new_events:
            decision_at = _utc_now_iso()
            for ev in new_events:
                ev["decision_at"] = decision_at
            learning_events, display_only_events = _partition_learning_stage_events(
                session_date, new_events,
            )
            if display_only_events:
                all_events.extend(display_only_events)
                meta_notes.append(
                    "pit_learning_stage_excluded_outside_rth="
                    f"{len(display_only_events)}"
                )
            if learning_events:
                if event_stager is None:
                    # Production persists this exact post-cycle state + fixed-clock
                    # batch as a WAL before any event-stage write. Tests may still
                    # inject a stager to exercise the pure cycle synchronously.
                    pending_learning_events.extend(learning_events)
                else:
                    all_events.extend(event_stager(session_date, learning_events))

        # Heat rows
        heat_rows.extend(result.get("heat", []))

        # Unusual names (latest per root)
        for un in result.get("unusual_names", []):
            r2 = un.get("root", root)
            if r2:
                unusual_by_root[r2] = un

        meta_notes.extend(result.get("meta_notes", []))

        # ── Lane G: tap this cycle's per-contract quotes for the surface greek grids ──
        # Surface roots only; freshest NBBO mid per contract; fenced + timed. Done BEFORE
        # the frames are freed below so no extra fetch is needed. prev_close is the parity
        # spot fallback the greek engine uses when parity can't resolve.
        if root.upper() in _surface_root_set:
            _sq_t0 = time.perf_counter()
            try:
                from scripts.build_flow_surface import extract_cycle_quotes
                near_cap = cfg.get("near_dte_cap_days", 90)
                quotes = extract_cycle_quotes(
                    calls_df, puts_df, session_date=session_date,
                    near_dte_cap_days=int(near_cap) if near_cap is not None else None)
                if quotes:
                    surface_quotes[root.upper()] = quotes
                    if prev_close is not None and prev_close > 0:
                        surface_spot_fallback[root.upper()] = float(prev_close)
            except Exception as sq_err:  # noqa: BLE001 — greek tap must not disturb the feed
                log.debug("poller: surface quote tap failed for %s: %s", root, sq_err)
            surface_quote_sec += time.perf_counter() - _sq_t0

        # Item 8 — free per-root frames after processing to cap intraday memory growth.
        del calls_df, puts_df, result
        fetch_results[root] = (None, None, None)  # release DataFrame references

    _log_rss_phase("post_oi_process", cycle_n=cycle_n)

    # Periodic GC after processing all roots (Item 8)
    gc.collect()
    _log_rss_phase("post_gc", cycle_n=cycle_n)

    # 24h retention trim
    retention_h = int(cfg.get("retention_hours", 24))
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(hours=retention_h)).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_events = lf.trim_events(all_events, cutoff_ts)

    # Aggregate heat across roots
    agg_heat = lf.aggregate_heat(heat_rows)

    # Enrich unusual_names with group labels
    unusual_list: list[dict] = []
    for root, un in unusual_by_root.items():
        from engine.live_flow import _root_to_group, _load_names_sectors
        ns = _load_names_sectors()
        grp_en, grp_zh = _root_to_group(root, ns)
        un["group"]    = grp_en
        un["group_zh"] = grp_zh
        # Fill call_prem_share from heat rows
        for hr in heat_rows:
            if hr.get("_root") == root:
                un["call_prem_share"] = round(float(hr.get("call_prem_share", 0.0)), 4)
                break
        unusual_list.append(un)

    # Sort unusual by |prem_z| desc, then by gross_premium_today desc
    def _un_sort_key(u: dict):
        pz = u.get("prem_z")
        return (abs(pz) if pz is not None else 0.0, u.get("gross_premium_today", 0.0))
    unusual_list.sort(key=_un_sort_key, reverse=True)

    # ── UNUSUAL_BASELINE annotation (BEHIND FLAG — fail-open) ─────────────────
    # When unusual_baseline artifact is loaded (UNUSUAL_BASELINE=1 + fresh artifact),
    # annotate each unusual entry with vol_baseline fields comparing gross_premium_today
    # against max(p95_vol_30d, 2 * mean_vol_30d).  No change to sort or existing fields.
    # Falls back silently when artifact absent, stale, or flag unset.
    if unusual_baseline:
        _ub_roots = unusual_baseline.get("roots", {})
        for un in unusual_list:
            r = un.get("root", "")
            rb = _ub_roots.get(r.upper())
            if rb and rb.get("mean_vol_30d") is not None and rb.get("p95_vol_30d") is not None:
                try:
                    mean_v = float(rb["mean_vol_30d"])
                    p95_v  = float(rb["p95_vol_30d"])
                    threshold = max(p95_v, 2.0 * mean_v)
                    gross_today = float(un.get("gross_premium_today") or 0.0)
                    un["vol_baseline"] = {
                        "mean_vol_30d":  mean_v,
                        "p95_vol_30d":   p95_v,
                        "threshold":     round(threshold, 0),
                        "above_threshold": gross_today > threshold,
                        "sessions_used": int(rb.get("sessions_used", 0)),
                    }
                except Exception:  # noqa: BLE001
                    pass  # fail-open: skip annotation for this root

    fetch_compute_sec = time.perf_counter() - cycle_t0
    prior_source_asof = day_state.get("source_asof")
    source_asof = source_response_times[-1] if source_response_times else prior_source_asof
    if source_asof is not None:
        source_asof = _canonical_utc_timestamp(source_asof, field="source_asof")

    # Build feed payload
    n_events = len(all_events)
    truncated = n_events >= lf.MAX_EVENTS

    baseline_note_ready = sum(1 for b in baselines.values()
                               if b.get("std") and float(b["std"]) > 0)
    notes: list[str] = []
    if baseline_note_ready == 0:
        notes.append("No EOD-252 baselines ready; floor gate only. "
                     "Run build_live_flow_baselines to enable z-scores.")
    else:
        notes.append(f"{baseline_note_ready} roots have EOD-252 baselines.")
    if delta_mode == "full_day":
        if forced_full_day:
            notes.append("Historical session — full-day mode forced (--date override).")
        else:
            notes.append("Incremental time-window pulls not supported on this terminal; "
                         "using full-day re-pull each cycle.")
    if truncated:
        notes.append(f"Events capped at {lf.MAX_EVENTS}; oldest dropped.")
    # WP-RESOLVER: surface a missing ThetaData store in meta (store_missing shape)
    if _OI_STORE_RESOLVED and _OI_STORE is None:
        notes.append("ThetaData store missing — t-1 OI context unavailable this session.")
    # Deduplicate meta_notes: same note from N roots appears only once
    seen_notes: set[str] = set()
    for note in meta_notes:
        if note not in seen_notes:
            seen_notes.add(note)
            notes.append(note)

    # The cumulative snapshot clock is taken only after all event processing, so
    # it can never predate an event's first-availability receipt.
    payload_asof = _utc_now_iso()
    feed_payload = {
        "schema":       "live_flow.feed/v1",
        "asof":         payload_asof,
        # Source age and build/availability age are different clocks.  ``asof``
        # remains the display envelope clock for event-availability ordering;
        # downstream derivative builders bind their legacy ``asof`` to this
        # explicit source clock instead.
        "source_asof":  source_asof,
        "session_date": session_date,
        "session_pct":  _session_pct(),
        "baseline_note": {
            "en": notes[0] if notes else "",
            "zh": notes[0] if notes else "",  # same text; no translation
        },
        "events":         all_events,
        "unusual_names":  unusual_list,
    }

    heat_payload = {
        "schema":       "live_flow.heat/v1",
        "asof":         payload_asof,
        "source_asof":  source_asof,
        "session_date": session_date,
        "groups":       agg_heat,
    }

    meta_payload = {
        "schema":                "live_flow.meta/v2",
        # Snapshot age is anchored to the newest successful source response
        # represented by the cumulative state, never to cycle completion.
        "asof":                  source_asof,
        "built_at":              payload_asof,
        "poll_floor_sec":        poll_floor_sec,
        "cycle_started_at":      cycle_started_at,
        "observed_start_to_start_sec": observed_start_to_start_sec,
        "fetch_compute_sec":     round(fetch_compute_sec, 3),
        "source_response_at_first": (
            source_response_times[0] if source_response_times else None
        ),
        "source_response_at_last": (
            source_response_times[-1] if source_response_times else None
        ),
        "roots_requested":       len(roots),
        "roots_with_source_payload": len(source_response_times),
        # Compatibility count aliases.  They do not define cadence truth.
        "universe_n":            len(roots),
        "roots_polled":          len(source_response_times),
        "requests_last_cycle":   requests_count,
        "delta_mode":            delta_mode,
        "max_concurrent":        max_w,
        "two_tier":              _two_tier_enabled(),
        "daily_summary":         _daily_summary_enabled(),
        # Lane G: added wall time to tap per-contract quotes for the surface greek grids
        # (surface roots only). Measured so the render budget stays honest.
        "surface_greek_quote_sec": round(surface_quote_sec, 3),
        "surface_greek_roots":     len(surface_quotes),
        "notes":                 notes,
    }

    # Build compound day_state for tide JSON builders
    tide_day_state = {
        "market_tide_minutes": market_tide_minutes,
        "sector_tide":         sector_tide,
        "dte_tide":            dte_tide,
        "root_minutes":        root_minutes_acc,
        "root_strikes":        root_strikes_acc,
        "root_expiries":       root_expiries_acc,
        "root_top_contracts":  root_top_contr,
        "root_gross_today":    root_gross,
        # Lane G: per-contract quote extract for the surface greek grids (this cycle only —
        # ephemeral, never serialized to day_state). Consumed by build_and_stage_surfaces.
        "surface_quotes":         surface_quotes,
        "surface_spot_fallback":  surface_spot_fallback,
    }

    updated_state = {
        "all_events":         all_events,
        "emitted_ids":        emitted_ids,
        "contract_vol":       contract_vol,
        "notability_history": notab_hist,
        "root_gross_today":   root_gross,
        "seen_sequences":     seen_sequences,
        # Tide accumulators
        "market_tide_minutes": market_tide_minutes,
        "sector_tide":         sector_tide,
        "dte_tide":            dte_tide,
        "root_minutes":        root_minutes_acc,
        "root_strikes":        root_strikes_acc,
        "root_expiries":       root_expiries_acc,
        "root_top_contracts":  root_top_contr,
        "sweep_clusters":      sweep_clusters_acc,
        "pending_learning_events": pending_learning_events,
        # Retain the newest successful source response across a fully failed
        # cycle so an unchanged cumulative snapshot cannot acquire a fresh age.
        "source_asof":         source_asof,
    }

    return feed_payload, heat_payload, meta_payload, updated_state, tide_day_state


# ── FC-R8: end-of-session daily summary writer ───────────────────────────────

def _daily_summary_path(session_date: str) -> Path:
    p = config.data_dir() / DAILY_SUMMARY_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{session_date}.json"


def write_daily_summary(
    session_date: str,
    day_state: dict,
    baselines: dict,
    cycle_n: int,
    asof: str,
) -> Path | None:
    """Write end-of-session per-day summary to data/live_flow_daily/YYYY-MM-DD.json.

    Per FC-R8: per-name + per-cohort {gross, soft_net, pc, minutes_covered,
    quality flags}.  Written locally AND uploaded to R2 WITHOUT the 48h TTL
    prefix (permanent storage path: live_flow_daily/<date>.json).

    Nightly-idempotent: safe to call multiple times; always overwrites with
    latest accumulated state.

    Returns the written Path on success, None on failure (INERT).
    """
    try:
        rg = day_state.get("root_gross_today", {})
        root_minutes = day_state.get("root_minutes", {})
        market_tide = day_state.get("market_tide_minutes", {})

        # Per-name summary rows
        names: list[dict] = []
        for root, gross in sorted(rg.items()):
            rm = root_minutes.get(root, {})
            minutes_covered = len(rm)
            # Cumulative NCP/NPP from root_minutes
            ncp_total = sum(float(v.get("ncp", 0.0)) for v in rm.values())
            npp_total = sum(float(v.get("npp", 0.0)) for v in rm.values())
            soft_net = round(ncp_total + npp_total, 0)
            # P/C ratio from root_strikes accumulator
            root_strikes = day_state.get("root_strikes", {}).get(root, {})
            call_prem = sum(float(v.get("call_prem", 0.0)) for v in root_strikes.values())
            put_prem = sum(float(v.get("put_prem", 0.0)) for v in root_strikes.values())
            total_prem = call_prem + put_prem
            pc_ratio = round(put_prem / call_prem, 3) if call_prem > 0 else None
            call_share = round(call_prem / total_prem, 4) if total_prem > 0 else None
            # Baseline info
            bl = baselines.get(root.upper())
            has_baseline = bl is not None and bl.get("std") and float(bl["std"]) > 0
            prem_z = None
            if has_baseline:
                m, s = float(bl["mean"]), float(bl["std"])
                prem_z = round((float(gross) - m) / s, 2)
            names.append({
                "root": root,
                "gross": round(float(gross), 0),
                "soft_net": soft_net,
                "pc_ratio": pc_ratio,
                "call_share": call_share,
                "minutes_covered": minutes_covered,
                "has_baseline": has_baseline,
                "prem_z": prem_z,
            })

        # Sort by gross desc
        names.sort(key=lambda r: r["gross"], reverse=True)

        # Market-level tide summary (cumulative NCP/NPP across all minutes)
        mkt_ncp = sum(float(v.get("ncp", 0.0)) for v in market_tide.values())
        mkt_npp = sum(float(v.get("npp", 0.0)) for v in market_tide.values())
        mkt_minutes = len(market_tide)

        summary = {
            "schema": "live_flow_daily.v1",
            "session_date": session_date,
            "asof": asof,
            "cycle_n": cycle_n,
            "n_names": len(names),
            "market": {
                "gross_total": round(sum(r["gross"] for r in names), 0),
                "soft_net_total": round(mkt_ncp + mkt_npp, 0),
                "minutes_covered": mkt_minutes,
            },
            "names": names,
        }

        out_path = _daily_summary_path(session_date)
        tmp = out_path.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(summary, default=str))
        tmp.rename(out_path)
        log.info("poller: FC-R8 daily summary written — %s (%d names, cycle=%d)",
                 out_path, len(names), cycle_n)
        return out_path
    except Exception as e:  # noqa: BLE001
        log.warning("poller: FC-R8 daily summary write failed: %s", e)
        return None


def _session_pct() -> float:
    """Fraction of the 6.5h trading session elapsed (0–1).  Clamped [0,1]."""
    try:
        now = datetime.now(ET)
        open_et  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
        close_et = now.replace(hour=16, minute=0,  second=0, microsecond=0)
        total    = (close_et - open_et).total_seconds()
        elapsed  = (now - open_et).total_seconds()
        return round(max(0.0, min(1.0, elapsed / total)), 4)
    except Exception:  # noqa: BLE001
        return 0.0


# ── main loop ─────────────────────────────────────────────────────────────────

def _within_rth() -> bool:
    """True if the current America/New_York time is within RTH window (09:25–16:05)
    on a weekday.  Never raises — returns False on any error.
    """
    try:
        now = datetime.now(ET)
        if now.weekday() >= 5:          # Saturday=5, Sunday=6
            return False
        t = now.hour * 60 + now.minute  # minutes since midnight ET
        start = RTH_START_H * 60 + RTH_START_M   # 565
        end   = RTH_END_H   * 60 + RTH_END_M     # 965
        return start <= t <= end
    except Exception:  # noqa: BLE001
        return False


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912, PLR0915
    global _OPTIONS_CONTEXT_DISPATCHER

    parser = argparse.ArgumentParser(description="Live options-flow poller")
    parser.add_argument(
        "--once", action="store_true",
        help="Run one mutating live-output cycle; not a smoke test",
    )
    parser.add_argument("--date",  metavar="YYYY-MM-DD",
                        help="Legacy diagnostic override; unsafe for smoke/PIT staging")
    parser.add_argument("--roots", nargs="+", metavar="ROOT",
                        help="Subset of roots (default: full universe)")
    parser.add_argument("--retention-hours", type=int, default=None,
                        metavar="N",
                        help="Override retention_hours for controlled diagnostics")
    parser.add_argument("--rth-only", action="store_true",
                        help="Exit cleanly outside 09:25-16:05 ET on weekdays "
                             "(use with launchd StartCalendarInterval)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = _cfg()

    # --retention-hours CLI override
    if args.retention_hours is not None:
        cfg["retention_hours"] = args.retention_hours
        log.info("poller: retention_hours overridden to %d (CLI)", args.retention_hours)

    session_date = _session_date(args.date)
    log.info("poller: session_date=%s once=%s", session_date, args.once)
    _OPTIONS_CONTEXT_DISPATCHER = _initialize_options_context_dispatcher(
        session_date, historical=bool(args.date),
    )

    # Recover the transaction seam before any network dependency or RTH exit.
    # A same-session restart can durably stage the exact pending decisions without
    # Theta. A prior-session WAL cannot acquire an honest later-date availability
    # clock, so surface it and stop before retention can erase the evidence.
    try:
        stale_pending = _stale_pending_learning_sessions(session_date)
        if stale_pending:
            log.error(
                "poller: stranded prior-session learning WAL requires reviewed "
                "recovery: %s",
                ",".join(stale_pending),
            )
            return 1
        day_state = _load_day_state(session_date)
        if day_state.get("pending_learning_events"):
            cutoff = (
                datetime.now(timezone.utc)
                - timedelta(hours=int(cfg.get("retention_hours", 24)))
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            day_state, _ = _drain_pending_learning_events(
                session_date,
                day_state,
                event_stager=_stage_raw_events,
                cutoff_ts=cutoff,
            )
        _flush_options_context_outbox()
    except Exception as exc:  # noqa: BLE001
        log.error("poller: startup learning-WAL recovery failed: %s", exc, exc_info=True)
        return 1

    # The clean outside-RTH exit remains zero, so launchd's SuccessfulExit=false
    # policy will not respawn it. Crash/Theta failures are nonzero and retry after
    # ThrottleInterval, allowing a same-session WAL to drain on the next launch.
    if args.rth_only and not _within_rth():
        log.info("poller: --rth-only outside RTH window — exiting cleanly")
        return 0

    # Check terminal reachable only after local WAL recovery. Startup uses a
    # tolerant 15s default so a slow-starting ThetaTerminal does not abort the
    # poller unnecessarily.
    from collectors import thetadata as td
    startup_timeout = int(os.environ.get("THETA_CONNECT_TIMEOUT", "15"))
    if not td.reachable(connect_timeout=startup_timeout):
        log.error("poller: Theta Terminal not reachable — abort")
        return 1

    # Resolve universe
    if args.roots:
        roots = [r.upper() for r in args.roots]
    else:
        roots = _resolve_universe(cfg)
    log.info("poller: universe=%d roots", len(roots))

    # A historical --date override is not a supported smoke, but retain the
    # legacy diagnostic's full-day semantics: a live-clock window on a past
    # session would be nonsensical and less safe.
    if args.date:
        delta_mode = "full_day"
        log.info("poller: delta_mode=full_day (forced — historical --date override)")
    else:
        delta_mode = _probe_delta_mode(session_date)
        log.info("poller: delta_mode=%s", delta_mode)

    # Load baselines (static for the session)
    baselines = _load_baselines()
    n_baselines = len(baselines)
    log.info("poller: loaded %d baseline entries", n_baselines)

    # Load unusual baseline (BEHIND FLAG — fail-open; default OFF)
    unusual_baseline = _load_unusual_baseline()
    if unusual_baseline:
        log.info("poller: unusual_baseline loaded (%d roots)", len(unusual_baseline.get("roots", {})))
    else:
        log.debug("poller: unusual_baseline not active (UNUSUAL_BASELINE env not set or artifact absent/stale)")

    # R2 setup
    bucket = os.environ.get("R2_BUCKET", "")
    s3 = _r2_client()
    if not s3:
        log.warning("poller: R2 creds absent — uploads will be skipped")
    elif not bucket:
        log.warning("poller: R2_BUCKET not set — uploads will be skipped")
        s3 = None

    # Retention runs only after the stale-WAL scan above proves no prior session
    # owns an undrained transaction.
    _prune_day_states(session_date, cfg)

    watermarks: dict = dict(day_state.get("cycle_watermarks", {}))
    last_archive_write = 0.0
    # M-XP(a): session date whose Flow-Surface retention sweep has already succeeded.
    # The sweep is a once-per-session R2 listing + delete, not a per-cycle cost; it stays
    # None until it completes cleanly so a failed sweep retries on the next cycle.
    last_surface_prune_date: str | None = None
    # OIP W0 T-lane: same once-per-session contract for the dated tide/dte_tide archives.
    # Tracked separately from the surface sweep so a surface-staging failure (which empties
    # surf_roots) can never starve the tide families of their retention sweep. Unlike the
    # surface sentinel this is set even when the sweep FAILS — a failed sweep retries NEXT
    # SESSION, not next cycle, so a persistent R2 fault cannot re-issue the listing ~200×.
    last_archive_prune_date: str | None = None

    # T-lane write gate: a MANUAL/BACKDATED run must never rewrite settled history.
    # The runbook explicitly forbids using `--date` as a smoke. Keep this older
    # defense in depth because such a run can still poll only a handful of roots;
    # its tide payload is a valid-looking partial of that past session, and the archive key is
    # derived from session_date — so an ungated invocation would overwrite the settled
    # live_flow/tide/<that date>.json with a 5-root fragment, undetectably (schema valid,
    # date correct; roots_polled lives only in meta.json, which the archive does not carry).
    # Live sessions never pass --date: session_date comes from the ET clock.
    archive_writes_enabled = not args.date
    if not archive_writes_enabled:
        log.warning("poller: --date=%s given — dated tide/dte archive writes AND retention "
                    "sweep are DISABLED for this run (a manual/backdated run must never "
                    "rewrite settled archive history)", args.date)
    else:
        # Second gate, resolved ONCE per run (session_date is fixed): launchd fires on market
        # holidays too, and the lane goes fully dark on a non-session — no dated payload, no
        # ledger entry, and no retention mutation on a day the market never opened.
        # stage_dated_archives re-checks this itself, so a future caller cannot bypass it.
        try:
            from scripts.build_flow_archive import is_market_session as _is_mkt_session
            if not _is_mkt_session(session_date):
                archive_writes_enabled = False
                log.info("poller: %s is not an NYSE trading session — dated tide/dte archive "
                         "lane is dark for this run", session_date)
        except Exception as _cal_err:  # noqa: BLE001 — fail closed, loudly
            archive_writes_enabled = False
            log.warning("poller: trading-calendar gate unavailable (%s) — dated tide/dte "
                        "archive lane DISABLED for this run", _cal_err)
    poll_floor_sec = _poll_floor_sec(cfg)

    # FC-R6: log two-tier + max_concurrent configuration at startup
    if _two_tier_enabled():
        log.info(
            "poller: FC-R6 two-tier cadence ON — tier1=%d roots every cycle, "
            "long tail round-robined (set %s=0 to disable)",
            len([r for r in roots if r.upper() in set(TIER1_ROOTS)]),
            TWO_TIER_ENV,
        )
    else:
        log.info(
            "poller: FC-R6 two-tier cadence OFF (%s) — all %d roots every cycle",
            TWO_TIER_ENV, len(roots),
        )
    mc = _max_concurrent(cfg)
    log.info("poller: max_concurrent=%d (env %s)", mc, MAX_CONCURRENT_ENV)
    # FC-R8: daily summary flag
    log.info(
        "poller: FC-R8 daily summary %s (set %s=1 to enable)",
        "ON" if _daily_summary_enabled() else "OFF",
        DAILY_SUMMARY_ENV,
    )

    cycle_n = 0
    previous_cycle_started_perf: float | None = None
    while True:
        loop_t0 = time.perf_counter()
        cycle_started_at = _utc_now_iso()
        observed_start_to_start_sec = (
            loop_t0 - previous_cycle_started_perf
            if previous_cycle_started_perf is not None else None
        )
        previous_cycle_started_perf = loop_t0
        cycle_n += 1

        # FC-R6: two-tier root selection (DEFAULT OFF)
        cycle_roots, _tail_slot = _select_cycle_roots(roots, cycle_n, cfg)

        log.info("poller: cycle #%d starting (date=%s delta_mode=%s roots=%d)",
                 cycle_n, session_date, delta_mode, len(cycle_roots))

        try:
            # Drain a crash-recovered post-cycle WAL before fetching any print.
            # Idempotent stage replay preserves its first decision clocks.
            if day_state.get("pending_learning_events"):
                cutoff = (
                    datetime.now(timezone.utc)
                    - timedelta(hours=int(cfg.get("retention_hours", 24)))
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
                day_state, _ = _drain_pending_learning_events(
                    session_date,
                    day_state,
                    event_stager=_stage_raw_events,
                    cutoff_ts=cutoff,
                )
                watermarks = dict(day_state.get("cycle_watermarks", {}))
            feed, heat, meta, updated_state, tide_day_state = run_cycle(
                roots=cycle_roots,
                session_date=session_date,
                delta_mode=delta_mode,
                day_state=day_state,
                baselines=baselines,
                cfg=cfg,
                cycle_watermarks=watermarks,
                forced_full_day=bool(args.date),
                unusual_baseline=unusual_baseline,
                event_stager=None,
                cycle_n=cycle_n,
                cycle_started_at=cycle_started_at,
                observed_start_to_start_sec=observed_start_to_start_sec,
            )
            # Transaction boundary: the post-cycle engine state and exact fixed-clock
            # events become durable together before the append-only learning stage.
            updated_state["cycle_watermarks"] = dict(watermarks)
            _save_day_state(session_date, updated_state)
            cutoff = (
                datetime.now(timezone.utc)
                - timedelta(hours=int(cfg.get("retention_hours", 24)))
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            day_state, _ = _drain_pending_learning_events(
                session_date,
                updated_state,
                event_stager=_stage_raw_events,
                cutoff_ts=cutoff,
            )
            _flush_options_context_outbox()
            # The cumulative display envelope is published only after durable
            # availability receipts exist for every newly admitted learning event.
            committed_asof = _utc_now_iso()
            feed["events"] = list(day_state.get("all_events", []))
            feed["asof"] = committed_asof
            heat["asof"] = committed_asof
            # Meta ``asof`` remains the newest represented source response.
            # Publication durability gets its own build clock instead of making
            # an unchanged source snapshot appear fresh.
            meta["built_at"] = committed_asof
        except Exception as e:  # noqa: BLE001
            log.error("poller: cycle #%d unhandled error: %s", cycle_n, e, exc_info=True)
            # Restore the last durable transaction. If it owns a pending event WAL,
            # the next loop drains that exact batch before any new fetch.
            try:
                day_state = _load_day_state(session_date)
                watermarks = dict(day_state.get("cycle_watermarks", {}))
            except Exception:
                log.error("poller: durable day_state recovery failed", exc_info=True)
            if args.once:
                return 1
            time.sleep(poll_floor_sec)
            continue

        # Write legacy JSON
        feed_path = _write_json("feed_current.json", feed)
        heat_path = _write_json("heat_current.json", heat)
        meta_path = _write_json("meta.json", meta)

        # ── Build and write tide JSON objects ─────────────────────────────────
        from engine import live_flow as lf_mod
        from engine.live_flow import _load_names_sectors

        tide_payload = lf_mod.build_tide_current(
            session_date=session_date,
            asof=meta.get("asof", feed.get("asof", "")),
            day_state=tide_day_state,
            spy_minute_prices=[],   # spy series: omit (no clean intraday spot source)
        )
        dte_tide_payload = lf_mod.build_dte_tide_current(
            session_date=session_date,
            asof=meta.get("asof", feed.get("asof", "")),
            day_state=tide_day_state,
        )
        tide_path     = _write_json("tide_current.json", tide_payload)
        dte_tide_path = _write_json("dte_tide_current.json", dte_tide_payload)

        # ── T-lane: dated tide/dte archives (OIP W0; masterplan §6 E1 / §7) ───
        # The current keys above are OVERWRITTEN every cycle, so the session's story dies at
        # the close. Queue a SECOND, date-keyed R2 key for the SAME two local files
        # (live_flow/{tide,dte_tide}/{DATE}.json) plus each family's dates.json, so the day's
        # final write is the settled record the nightly Session Digest reads. Both payloads
        # already carry the FULL-SESSION cumulative series (build_tide_current /
        # build_dte_tide_current cumulate every minute from the open), so no payload change is
        # needed and the current keys' bytes are untouched. Fully fenced: the current-key
        # uploads are queued below regardless, so a staging failure here degrades to
        # current-keys-only (today's behavior) and can never cost the live Terminal a cycle.
        # Gated OFF for a --date run (see archive_writes_enabled above) and, inside
        # stage_dated_archives, for any date that is not a real NYSE trading session.
        archive_paths: list[tuple[Path, str]] = []
        if archive_writes_enabled:
            try:
                from scripts.build_flow_archive import (
                    ARCHIVE_RETAIN_SESSIONS, DTE_TIDE_FAMILY, TIDE_FAMILY,
                    stage_dated_archives,
                )
                archive_paths = stage_dated_archives(
                    paths_by_family={TIDE_FAMILY: tide_path, DTE_TIDE_FAMILY: dte_tide_path},
                    session_date=session_date,
                    asof=meta.get("asof", feed.get("asof", "")),
                    cadence_sec=poll_floor_sec,
                    retain_sessions=int(cfg.get("archive_retain_sessions",
                                                ARCHIVE_RETAIN_SESSIONS) or
                                        ARCHIVE_RETAIN_SESSIONS),
                )
            except Exception as arch_err:  # noqa: BLE001
                log.warning("poller: dated tide archive staging failed: %s", arch_err)

        # Build ticker JSONs for top ~40 roots by gross premium + pinned roots (Task 3).
        ns_map  = _load_names_sectors()
        rg_dict = tide_day_state.get("root_gross_today", {})
        top_roots_by_gross = sorted(rg_dict.items(), key=lambda kv: kv[1], reverse=True)
        ticker_count = 0
        ticker_paths: list[tuple[Path, str]] = []  # (local_path, r2_key)
        _tickers_out_dir = _out_dir() / "tickers"
        _tickers_out_dir.mkdir(parents=True, exist_ok=True)

        # Task 3: pinned-publish roots guarantee — Mag7 + memory + SPY/QQQ/SMH are
        # always included in the published set even if they fall outside the top-40.
        # Default ON (LIVE_FLOW_PINNED_PUBLISH=1); set =0 to disable.
        top40_set = {r for r, _ in top_roots_by_gross[:TOP_TICKERS_N]}
        if _pinned_publish_enabled():
            pinned_extra = [r for r in PINNED_PUBLISH_ROOTS
                            if r.upper() not in top40_set and r.upper() in rg_dict]
            publish_roots = [r for r, _ in top_roots_by_gross[:TOP_TICKERS_N]] + pinned_extra
        else:
            publish_roots = [r for r, _ in top_roots_by_gross[:TOP_TICKERS_N]]

        for tick_root in publish_roots:
            try:
                tk_payload = lf_mod.build_ticker_json(
                    root=tick_root,
                    session_date=session_date,
                    asof=meta.get("asof", feed.get("asof", "")),
                    day_state=tide_day_state,
                    root_gross_today=rg_dict,
                    baselines=baselines,
                    names_sectors=ns_map,
                )
                # Skip empty payloads — minutes=0 AND strikes=0 means no data landed for
                # this root (e.g. fetch failed under contention); publishing an empty file
                # would overwrite a valid prior-cycle file with stale zeros.
                n_min = len(tk_payload.get("minutes", []))
                n_str = len(tk_payload.get("strikes", []))
                if n_min == 0 and n_str == 0:
                    log.info("poller: skip empty ticker JSON for %s (minutes=0, strikes=0)",
                             tick_root)
                    continue
                tk_file = tick_root.upper().replace(".", "_") + ".json"
                tk_local = _tickers_out_dir / tk_file
                tmp_tk = tk_local.with_suffix(".tmp.json")
                tmp_tk.write_text(json.dumps(tk_payload, default=str))
                tmp_tk.rename(tk_local)
                ticker_paths.append((tk_local, R2_PREFIX + f"tickers/{tick_root.upper()}.json"))
                ticker_count += 1
            except Exception as tk_err:  # noqa: BLE001
                log.warning("poller: ticker JSON failed for %s: %s", tick_root, tk_err)

        # ── Flow-Surface snapshot store (netprem + Lane-G greek grids) ────────
        # Materialize the Terminal surface pane's replay store. netprem comes from the
        # tide_day_state["root_strikes"] cumulative rollup; the GEX/DEX/VANNA/CHARM grids +
        # walls + coverage come from tide_day_state["surface_quotes"] (this cycle's freshest
        # per-contract NBBO, tapped in run_cycle) joined to EOD-t-1 OI (session-cached).
        # Staged to the gitignored data/live_flow_out/surface/ dir + uploaded to R2 below.
        # The configured poll floor is the completeness denominator. Each public
        # frame separately derives its observed spacing from truncated stamps; a
        # slow/sparse session therefore cannot relabel itself complete. A greek
        # failure never blocks a root's netprem column. See
        # scripts/build_flow_surface.py + engine/intraday_greeks.py + RECON §2 / MASTERPLAN §4.
        # M-XP(a): each cycle also stages date-keyed copies under
        # live_flow/surface/{ROOT}/{YYYY-MM-DD}/ plus the root's dates.json, so the Terminal
        # can replay completed sessions. Legacy today-paths are written unchanged alongside
        # them. Retention (newest N sessions per root) is swept once per session below.
        surface_paths: list[tuple[Path, str]] = []
        surf_roots: list[str] = []
        try:
            from scripts.build_flow_surface import (
                SURFACE_RETAIN_SESSIONS, build_and_stage_surfaces, resolve_surface_roots,
            )
            surf_roots = resolve_surface_roots(cfg, rg_dict)
            surf_quotes = tide_day_state.get("surface_quotes", {}) or {}
            surf_spot_fb = tide_day_state.get("surface_spot_fallback", {}) or {}
            # EOD-t-1 OI map per surface root that has quotes (session-cached; no new fetch).
            surf_oi = {}
            for _sr in surf_roots:
                if surf_quotes.get(_sr.upper()):
                    surf_oi[_sr.upper()] = _surface_oi_map(_sr, session_date)
            surface_paths = build_and_stage_surfaces(
                root_strikes_by_root=tide_day_state.get("root_strikes", {}),
                roots=surf_roots,
                session_date=session_date,
                asof=meta.get("asof", feed.get("asof", "")),
                cadence_sec=poll_floor_sec,
                quotes_by_root=surf_quotes,
                oi_by_root=surf_oi,
                spot_fallback_by_root=surf_spot_fb,
                retain_sessions=int(cfg.get("surface_retain_sessions",
                                            SURFACE_RETAIN_SESSIONS) or
                                    SURFACE_RETAIN_SESSIONS),
            )
        except Exception as surf_err:  # noqa: BLE001
            log.warning("poller: flow-surface store failed: %s", surf_err)

        roots_ok_n = meta.get(
            "roots_with_source_payload", meta.get("roots_polled", 0),
        )
        roots_total_n = meta.get("roots_requested", meta.get("universe_n", len(roots)))
        roots_skip_n  = roots_total_n - roots_ok_n

        log.info("poller: cycle #%d events=%d unusual=%d heat_groups=%d "
                 "minutes=%d sectors=%d tickers=%d cycle_sec=%.1fs",
                 cycle_n,
                 len(feed.get("events", [])),
                 len(feed.get("unusual_names", [])),
                 len(heat.get("groups", [])),
                 len(tide_payload.get("minutes", [])),
                 len(tide_payload.get("sectors", [])),
                 ticker_count,
                 meta.get("fetch_compute_sec", 0))

        # Item 6 — register live_flow_poller in the run_status/circuit-breaker pattern.
        # Mirrors the established pattern in scripts/collect.py + lib/store.write_status.
        # Writes a 'live_flow_poller' entry under sources with ok/roots_ok/roots_skipped/asof.
        try:
            from lib import store as _store   # noqa: PLC0415
            _rs = _store.read_status()
            _rs.setdefault("sources", {})["live_flow_poller"] = {
                "status":        "ok",
                "roots_ok":      roots_ok_n,
                "roots_skipped": roots_skip_n,
                "asof":          meta.get("asof", ""),
                "cycle_n":       cycle_n,
                "checked_at":    datetime.now(timezone.utc).isoformat(),
            }
            _store.write_status(_rs)
        except Exception as _rs_err:  # noqa: BLE001
            log.debug("poller: run_status write failed (non-fatal): %s", _rs_err)

        # Item 8 — bounded pre-publication RSS telemetry and existing >2 GB alarm.
        try:
            _current_rss, rss_bytes = _log_rss_phase(
                "pre_publication", cycle_n=cycle_n,
            )
            if rss_bytes is not None and rss_bytes > RSS_WARN_BYTES:
                log.warning(
                    "poller: cycle #%d peak RSS %.1f GB exceeds 2 GB threshold",
                    cycle_n, rss_bytes / (1024 ** 3),
                )
                meta.setdefault("notes", []).append(
                    f"peak RSS {rss_bytes / (1024**3):.1f} GB > 2 GB threshold — "
                    "consider reducing universe or retention_hours"
                )
        except Exception as _rss_err:  # noqa: BLE001
            log.debug("poller: RSS check failed (non-fatal): %s", _rss_err)

        # FC-R8: write end-of-session daily summary (every cycle; nightly-idempotent).
        # Gated behind LIVE_FLOW_DAILY_SUMMARY=1 (default OFF — new production write path).
        # Operator action: set LIVE_FLOW_DAILY_SUMMARY=1 in /etc/macro-api.env to enable.
        daily_summary_path = None
        if _daily_summary_enabled():
            daily_summary_path = write_daily_summary(
                session_date=session_date,
                day_state=day_state,
                baselines=baselines,
                cycle_n=cycle_n,
                asof=meta.get("asof", ""),
            )

        # Upload to R2
        if s3:
            # Durable, date-keyed source comes first. feed_current is capped display
            # state and is never the learning source. A failed stage upload leaves
            # published_at null and the nightly consumer checkpoint unchanged.
            _publish_event_stage(s3, bucket, session_date)
            _upload_r2(s3, bucket, feed_path, R2_PREFIX + "feed_current.json")
            _upload_r2(s3, bucket, heat_path, R2_PREFIX + "heat_current.json")
            _upload_r2(s3, bucket, meta_path, R2_PREFIX + "meta.json")
            _upload_r2(s3, bucket, tide_path,     R2_PREFIX + "tide_current.json")
            _upload_r2(s3, bucket, dte_tide_path, R2_PREFIX + "dte_tide_current.json")
            for tk_local, tk_r2_key in ticker_paths:
                _upload_r2(s3, bucket, tk_local, tk_r2_key)

            # T-lane dated archives: the same two local tide files under their
            # {DATE}.json keys, plus each family's dates.json (re-PUT every cycle so a
            # missing/corrupt index heals in THIS cycle — a --once run must never defer its
            # heal to a cycle that will not run). _upload_r2 is already fail-soft: a PUT
            # failure logs "R2 upload failed for <key>" and the loop continues.
            # The r2_key is the full key built by build_flow_archive — no R2_PREFIX join.
            for arch_local, arch_r2_key in archive_paths:
                _upload_r2(s3, bucket, arch_local, arch_r2_key)

            # Flow-Surface store: idx.json + {HHMM}.json per root, each queued under BOTH
            # the legacy today-key and its date-keyed {YYYY-MM-DD}/ copy, plus dates.json.
            # The r2_key is the full key (live_flow/surface/{ROOT}/…) built by
            # build_flow_surface — no R2_PREFIX join here.
            for surf_local, surf_r2_key in surface_paths:
                _upload_r2(s3, bucket, surf_local, surf_r2_key)

            # M-XP(a): Flow-Surface retention sweep — keep the newest N session prefixes
            # per root, delete the rest. Runs ONCE per session (first successful cycle),
            # never per-cycle. Fully fenced, and prune_surface_dates is itself fail-soft +
            # only ever deletes under a {ROOT}/{YYYY-MM-DD}/ prefix, so a retention failure
            # can neither break the flow cycle nor touch the legacy today-paths the live
            # Terminal reads. Merging R2 truth back into the local ledger self-heals
            # dates.json after a staging-dir wipe (droplet redeploy) — and the healed file
            # is PUT right here, in this same cycle (#F3-04): deferring it to "the next
            # cycle's surface upload" left a `--once` / `--rth-only` run (the plist's own
            # documented cold-start recipe) exiting at the bottom of THIS cycle with the
            # pre-heal, truncated dates.json still the live R2 object — until the second
            # cycle of a LATER session ever runs.
            if surf_roots and last_surface_prune_date != session_date:
                try:
                    from scripts.build_flow_surface import (
                        R2_SURFACE_PREFIX as _R2_SURFACE_PREFIX,
                        SURFACE_DATES_NAME as _SURFACE_DATES_NAME,
                        SURFACE_RETAIN_SESSIONS as _RETAIN,
                        _surface_out_dir,
                        merge_surface_dates as _merge_dates,
                        prune_surface_dates as _prune_dates,
                    )
                    keep_n = int(cfg.get("surface_retain_sessions", _RETAIN) or _RETAIN)
                    all_ok = True
                    for _sr in surf_roots:
                        res = _prune_dates(s3, bucket, _sr, keep=keep_n)
                        all_ok = all_ok and res["ok"]
                        if res["retained"]:
                            dates_local = _merge_dates(
                                _sr, res["retained"], cadence_sec=poll_floor_sec,
                                asof=meta.get("asof", ""), retain=keep_n)
                            log.info("poller: surface retention %s → %d session(s) kept",
                                     _sr.upper(), len(dates_local))
                            try:
                                healed_path = _surface_out_dir(_sr) / _SURFACE_DATES_NAME
                                if healed_path.exists():
                                    _upload_r2(s3, bucket, healed_path,
                                               f"{_R2_SURFACE_PREFIX}{_sr.upper()}/{_SURFACE_DATES_NAME}")
                            except Exception as heal_err:  # noqa: BLE001
                                log.warning("poller: healed dates.json upload failed for %s: %s",
                                            _sr.upper(), heal_err)
                    if all_ok:
                        last_surface_prune_date = session_date
                except Exception as prune_err:  # noqa: BLE001
                    log.warning("poller: surface retention sweep failed: %s", prune_err)

            # OIP W0 T-lane: dated tide/dte_tide retention sweep — keep the newest N
            # sessions per family, delete the rest. Runs ONCE per session (first successful
            # cycle), never per-cycle: two cheap R2 listings (~30 small objects each).
            # prune_archive_dates is fail-soft and rebuilds every delete target from
            # dated_archive_key, so it can only ever delete a key this lane itself wrote —
            # never dates.json, never live_flow/tide_current.json. Merging R2 truth back into
            # the local ledger self-heals dates.json after a staging wipe, and the healed
            # file is PUT right here in THIS cycle (#F3-04): deferring it to "the next
            # cycle's upload" left a --once / --rth-only run exiting with the pre-heal index
            # still live in R2.
            if archive_writes_enabled and last_archive_prune_date != session_date:
                try:
                    from scripts.build_flow_archive import (
                        ARCHIVE_DATES_NAME as _ARCH_DATES_NAME,
                        ARCHIVE_FAMILIES as _ARCH_FAMILIES,
                        ARCHIVE_RETAIN_SESSIONS as _ARCH_RETAIN,
                        archive_out_dir as _archive_out_dir,
                        dates_index_key as _dates_index_key,
                        merge_archive_dates as _merge_archive_dates,
                        prune_archive_dates as _prune_archive_dates,
                    )
                    keep_n = int(cfg.get("archive_retain_sessions", _ARCH_RETAIN)
                                 or _ARCH_RETAIN)
                    all_ok = True
                    for _fam in _ARCH_FAMILIES:
                        res = _prune_archive_dates(s3, bucket, _fam, keep=keep_n)
                        all_ok = all_ok and res["ok"]
                        if res["retained"]:
                            kept = _merge_archive_dates(
                                _fam, res["retained"], cadence_sec=poll_floor_sec,
                                asof=meta.get("asof", ""), retain=keep_n)
                            log.info("poller: archive retention %s → %d session(s) kept",
                                     _fam, len(kept))
                            try:
                                healed = _archive_out_dir(_fam) / _ARCH_DATES_NAME
                                if healed.exists():
                                    _upload_r2(s3, bucket, healed, _dates_index_key(_fam))
                            except Exception as heal_err:  # noqa: BLE001
                                log.warning("poller: healed dates.json upload failed for "
                                            "%s: %s", _fam, heal_err)
                    # ONE attempt per session, pass or fail: prune_archive_dates already
                    # returns ok=True for an empty store, so a False here is a genuine R2
                    # fault. Retrying it every 120s would re-issue the listing ~200×/session
                    # for a fault that will not clear; retention is 30 sessions deep, so
                    # skipping one sweep costs nothing — the next session's sweep prunes
                    # everything that went stale meanwhile.
                    last_archive_prune_date = session_date
                    if not all_ok:
                        log.warning("poller: archive retention sweep incomplete — retention "
                                    "NOT verified this session; retrying next session")
                except Exception as prune_err:  # noqa: BLE001
                    last_archive_prune_date = session_date
                    log.warning("poller: archive retention sweep failed: %s", prune_err)

            # FC-R8: upload daily summary to R2 WITHOUT the live_flow/ TTL prefix.
            # Key: live_flow_daily/<date>.json — permanent (no 48h prune).
            # Only runs when LIVE_FLOW_DAILY_SUMMARY=1 (daily_summary_path is not None).
            if daily_summary_path is not None:
                r2_daily_key = f"live_flow_daily/{session_date}.json"
                _upload_r2(s3, bucket, daily_summary_path, r2_daily_key)

            # Hourly archive
            now_ts  = time.time()
            if now_ts - last_archive_write >= ARCHIVE_HOUR_CADENCE:
                hour_key = datetime.now(timezone.utc).strftime("%Y%m%dT%H")
                archive_local = _write_json(f"archive_{hour_key}.json", feed)
                _upload_r2(s3, bucket, archive_local,
                           R2_PREFIX + f"archive/{hour_key}.json")
                last_archive_write = now_ts
                _prune_archive(s3, bucket, older_than_hours=48)

        _log_rss_phase("post_publication", cycle_n=cycle_n)

        if args.once:
            log.info("poller: --once flag set — exiting after one cycle")
            return 0

        # --rth-only: exit at end of each cycle once outside RTH
        if args.rth_only and not _within_rth():
            _prune_day_states(session_date, cfg)   # end-of-session sweep
            log.info("poller: --rth-only outside RTH window — exiting cleanly")
            return 0

        # Sleep for remainder of cadence
        elapsed = time.perf_counter() - loop_t0
        sleep_for = max(0.0, poll_floor_sec - elapsed)
        if sleep_for > 0:
            log.debug("poller: sleeping %.1fs", sleep_for)
            time.sleep(sleep_for)


if __name__ == "__main__":
    sys.exit(main())
