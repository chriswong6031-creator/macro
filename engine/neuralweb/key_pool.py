"""engine/neuralweb/key_pool.py — Multi-key OAuth pool for the Metabolism loop (V2-B).

SIBLING OF capability_broker.py — same NEVER-RAISE contract.

PURPOSE
-------
Tracks ESTIMATED usage state (belief-state) for N OAuth keys discovered from
the capability manifest.  Anthropic exposes no exact quota counter, so this
module maintains a local ledger of session counts + estimated tokens per 5h
window and per week.  Quota is unobservable; the ledger is calibrated on
every 429/usage-limit error.

REDLINE (the single unforgivable defect — shared with capability_broker):
    A secret VALUE must NEVER appear in a git artifact or in any return value
    of this module.  This module:
      - Discovers keys from capability_manifest.yml (secret_ref NAMES only).
      - Returns capability_id strings; the CALLER reads os.environ[secret_ref].
      - Never reads, logs, or stores token values.
      - is subject to check_capability_redline.py scanning.

POOL SIZING
-----------
Works with 1..N keys.  discover_present_keys() returns the subset whose
os.environ[secret_ref] is non-empty.  With 1 key present, the pool serializes
(no spread benefit); with N keys it distributes load.  Operator adds keys by
setting CLAUDE_CODE_OAUTH_TOKEN_1 / _2 / _3 as GH secrets and adding rows to
config/capability_manifest.yml.

COOLING DUAL-HORIZON
--------------------
A key may enter cooling for two reasons:
  - window:  a 5h-window 429.  Reset = next 5h boundary (or retry-after header).
  - weekly:  a weekly-quota 429.  Reset = next weekly boundary.

Cooling keys are SKIPPED by the dispatcher.  When ALL keys are cooling, the
caller emits a freeze no-op and computes earliest_reset.

STATELESS-CATTLE
----------------
State defaults to data/metabolism/key_ledger.jsonl. Long-lived appliances may
set METABOLISM_STATE_ROOT so their append-only key/session telemetry lives
outside an immutable Git checkout. The pool reads the ledger on every call; it
holds no in-process mutable state between calls.

NEVER-RAISE CONTRACT
--------------------
All public functions catch ALL exceptions, log a warning, and return a safe
fallback.  A pool failure must never abort the lane that invoked it.

Usage:
    from engine.neuralweb.key_pool import (
        discover_present_keys,
        window_load, weekly_load,
        record_session, mark_cooling, is_cooling,
        all_cooling_freeze_info,
    )

    keys = discover_present_keys()        # e.g. ["claude_code_oauth_1"]
    if not keys:
        sys.exit(0)  # nothing to work with
    best = min(keys, key=lambda k: window_load(k))
    record_session(best, est_tokens=50_000)
"""
from __future__ import annotations

import json
import logging
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_MANIFEST_REL = "config/capability_manifest.yml"
_LEDGER_REL = "data/metabolism/key_ledger.jsonl"
_SCHEMA = "metabolism.key_ledger.v1"
_USAGE_LEDGER_REL = "data/metabolism/key_usage.jsonl"
_USAGE_SCHEMA = "metabolism.key_usage.v1"
# Mastermind bot publishes its own key-pool ledger rows here (same schema).
# This is a display-only join: rotation-relevant reads (is_cooling, window_load,
# weekly_load, discover_present_keys) remain macro-only by design.
# Cross-repo rotation coordination is an explicitly deferred follow-up.
_MM_EVENTS_REL = "data/mastermind/key_events.jsonl"
# Mastermind bot also publishes a point-in-time pool-status snapshot here (a
# NEW artifact from the parallel bot-side PR; may be ABSENT for a while). When
# present, fresh, and schema-valid it is the preferred source for per-key bot
# cooling state; otherwise state is reconstructed from the _MM_EVENTS tail.
# Display-only join — rotation reads (is_cooling, window_load, weekly_load,
# discover_present_keys) remain macro-only by design.
_MM_STATUS_REL = "data/mastermind/key_pool_status.json"
_MM_STATUS_SCHEMA = "mastermind.key_pool_status.v1"
# The status snapshot is trusted only while fresh; a stale file (bot stopped
# publishing) falls back to events-tail reconstruction.
_MM_STATUS_MAX_AGE_SECONDS = 48 * 3600
# How many trailing lines of the events ledger to scan when reconstructing
# bot cooling state (bounded read — the ledger is append-only and unbounded).
_MM_EVENTS_TAIL_LINES = 300

# The capability_ids this pool manages (in order).
# Operator adds keys by setting CLAUDE_CODE_OAUTH_TOKEN_1.._7 as GH secrets
# and adding rows to capability_manifest.yml.  The pool discovers which subset
# is present by checking if the env ref exists.  Keys can be added one at a
# time — absent secrets resolve to empty env = "not present", so presence-based
# discovery handles partial sets with no code change required.
POOL_CAPABILITY_IDS = [
    "claude_code_oauth_1",
    "claude_code_oauth_2",
    "claude_code_oauth_3",
    "claude_code_oauth_4",
    "claude_code_oauth_5",
    "claude_code_oauth_6",
    "claude_code_oauth_7",
]

# Non-Claude credentials that participate in the shared LLM waterfall.  These
# are displayed and cooled by the same ledger, but deliberately remain outside
# POOL_CAPABILITY_IDS so the seven-slot Claude rotation contract stays exact.
PROVIDER_CAPABILITY_IDS = [
    "codex_account",
    "codex_account_2",
    "codex_account_3",
    "deepseek_api_key",
]

# 5-hour window in seconds
_WINDOW_SECONDS = 5 * 3600
# 1 week in seconds
_WEEK_SECONDS = 7 * 24 * 3600


# ── Path helpers ─────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Auto-detect repo root from this file's location (engine/neuralweb/)."""
    return Path(__file__).resolve().parent.parent.parent


def _state_root() -> Path:
    """Resolve mutable key-ledger storage independently of repo config."""
    # Literal allowlisted name: this module must never dynamically dereference
    # an environment key because capability ref names can point at secrets.
    override = os.environ.get("METABOLISM_STATE_ROOT", "").strip()
    if not override:
        return _repo_root()

    candidate = Path(override).expanduser()
    if not candidate.is_absolute():
        raise ValueError("METABOLISM_STATE_ROOT must be an absolute path")
    resolved = candidate.resolve(strict=False)
    repo = _repo_root().resolve(strict=False)
    home = Path.home().resolve(strict=False)
    filesystem_root = Path(resolved.anchor)
    if resolved in {filesystem_root, home}:
        raise ValueError("METABOLISM_STATE_ROOT is too broad for mutable telemetry")
    if resolved == repo or repo in resolved.parents:
        raise ValueError("METABOLISM_STATE_ROOT must live outside the repository")
    return resolved


def _manifest_path(root: Path | None = None) -> Path:
    base = root if root is not None else _repo_root()
    return base / _MANIFEST_REL


def _ledger_path(root: Path | None = None) -> Path:
    base = root if root is not None else _state_root()
    return base / _LEDGER_REL


def _usage_ledger_path(root: Path | None = None) -> Path:
    base = root if root is not None else _state_root()
    return base / _USAGE_LEDGER_REL


def _mm_events_path(root: Path | None = None) -> Path:
    base = root if root is not None else _repo_root()
    return base / _MM_EVENTS_REL


def _mm_status_path(root: Path | None = None) -> Path:
    base = root if root is not None else _repo_root()
    return base / _MM_STATUS_REL


# ── Mastermind event reader ───────────────────────────────────────────────────

def _read_mm_events(root: Path | None = None) -> list[dict[str, Any]]:
    """Read Mastermind bot key-pool ledger rows (display-only join).

    Mirrors _read_ledger: absent file -> [], corrupt lines skipped, NEVER raises.

    SCOPE GUARD: this reader is ONLY for display aggregation in usage_snapshot().
    Rotation-relevant reads (is_cooling, window_load, weekly_load,
    discover_present_keys) remain macro-only by design.  Cross-repo rotation
    coordination is an explicitly deferred follow-up.
    """
    try:
        p = _mm_events_path(root)
        if not p.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # corrupt row — skip gracefully
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool._read_mm_events: %s", exc)
        return []


def _read_mm_status(root: Path | None = None) -> dict[str, Any] | None:
    """Read the Mastermind bot pool-status snapshot (display-only join).

    Returns the parsed dict when the file exists, parses, carries the expected
    schema, and its `ts` is younger than _MM_STATUS_MAX_AGE_SECONDS. Otherwise
    returns None (absent / corrupt / wrong-schema / stale) so the caller falls
    back to events-tail reconstruction. NEVER raises.
    """
    try:
        p = _mm_status_path(root)
        if not p.exists():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        if raw.get("schema") != _MM_STATUS_SCHEMA:
            return None
        ts = _parse_ts(raw.get("ts", "") or "")
        if ts is None:
            return None  # no usable timestamp — cannot judge freshness
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        if age > _MM_STATUS_MAX_AGE_SECONDS:
            return None  # stale — fall back to events reconstruction
        return raw
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool._read_mm_status: %s", exc)
        return None


def _mm_state_from_status(status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build the per-key bot-state map from a fresh status snapshot.

    Returns {key_id: {mm_cooling, mm_cool_kind, mm_reset_hint,
    mm_last_outcome, mm_last_ts}} for each valid key row. NEVER raises.
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        keys = status.get("keys")
        if not isinstance(keys, list):
            return out
        for entry in keys:
            if not isinstance(entry, dict):
                continue
            kid = entry.get("key_id")
            if not kid:
                continue
            out[kid] = {
                "mm_cooling": bool(entry.get("cooling", False)),
                "mm_cool_kind": entry.get("cool_kind"),
                "mm_reset_hint": entry.get("reset_hint"),
                "mm_last_outcome": entry.get("last_outcome"),
                "mm_last_ts": entry.get("last_ts"),
            }
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool._mm_state_from_status: %s", exc)
    return out


def _mm_state_from_events(
    mm_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Reconstruct per-key bot cooling state from the events-ledger tail.

    A key is `mm_cooling` when its most-recent cooling row (outcome
    rate_limited|auth_failed, carrying a reset_hint) is NEWER than its
    most-recent `ok` row AND that reset_hint is still in the future.

    mm_cool_kind / mm_reset_hint come from that latest cooling row.
    mm_last_outcome / mm_last_ts come from the latest row of ANY outcome (so
    the tooltip reflects the true tail even when the key is not cooling).

    `mm_rows` must already be schema/key filtered by the caller. NEVER raises.
    Returns {key_id: {mm_cooling, mm_cool_kind, mm_reset_hint,
    mm_last_outcome, mm_last_ts}}.
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        now = datetime.now(timezone.utc)
        # latest row overall + latest cooling row + latest ok row, per key
        latest_any: dict[str, tuple[datetime, dict[str, Any]]] = {}
        latest_cool: dict[str, tuple[datetime, dict[str, Any]]] = {}
        latest_ok_dt: dict[str, datetime] = {}
        for r in mm_rows:
            kid = r.get("key_id")
            if not kid:
                continue
            ts = _parse_ts(r.get("ts", "") or "")
            if ts is None:
                continue
            if kid not in latest_any or ts > latest_any[kid][0]:
                latest_any[kid] = (ts, r)
            outcome = r.get("outcome")
            if outcome == "ok":
                if kid not in latest_ok_dt or ts > latest_ok_dt[kid]:
                    latest_ok_dt[kid] = ts
            elif outcome in ("rate_limited", "auth_failed") and r.get("reset_hint"):
                if kid not in latest_cool or ts > latest_cool[kid][0]:
                    latest_cool[kid] = (ts, r)

        for kid, (_last_dt, last_row) in latest_any.items():
            mm_cooling = False
            mm_cool_kind: str | None = None
            mm_reset_hint: str | None = None
            cool = latest_cool.get(kid)
            if cool is not None:
                cool_dt, cool_row = cool
                ok_dt = latest_ok_dt.get(kid)
                newer_than_ok = ok_dt is None or cool_dt > ok_dt
                reset_dt = _parse_ts(cool_row.get("reset_hint", "") or "")
                reset_in_future = reset_dt is not None and now < reset_dt
                if newer_than_ok and reset_in_future:
                    mm_cooling = True
                    mm_cool_kind = cool_row.get("cool_kind")
                    mm_reset_hint = cool_row.get("reset_hint")
            out[kid] = {
                "mm_cooling": mm_cooling,
                "mm_cool_kind": mm_cool_kind,
                "mm_reset_hint": mm_reset_hint,
                "mm_last_outcome": last_row.get("outcome"),
                "mm_last_ts": last_row.get("ts"),
            }
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool._mm_state_from_events: %s", exc)
    return out


def _mm_pool_state(
    mm_rows: list[dict[str, Any]],
    root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Derive per-key Mastermind bot state (display-only).

    Preference order (spec):
      (a) a fresh (< 48h), schema-valid data/mastermind/key_pool_status.json
          snapshot is used directly;
      (b) otherwise state is reconstructed from the events-ledger tail
          (`mm_rows`, already schema/key filtered by the caller).

    Returns {key_id: {mm_cooling, mm_cool_kind, mm_reset_hint,
    mm_last_outcome, mm_last_ts}}. Missing keys default (in the caller) to
    False/None. NEVER raises.
    """
    try:
        status = _read_mm_status(root)
        if status is not None:
            return _mm_state_from_status(status)
        return _mm_state_from_events(mm_rows)
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool._mm_pool_state: %s", exc)
        return {}


# ── Manifest helpers ─────────────────────────────────────────────────────────

def _load_manifest(root: Path | None = None) -> dict[str, Any]:
    """Load capability manifest.  Returns {} on error (NEVER-RAISE)."""
    try:
        import yaml
        p = _manifest_path(root)
        with open(p) as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool._load_manifest: %s", exc)
        return {}


def _get_capability_row(capability_id: str, root: Path | None = None) -> dict[str, Any] | None:
    """Return the manifest row for capability_id, or None."""
    try:
        manifest = _load_manifest(root)
        for cap in manifest.get("capabilities", []):
            if isinstance(cap, dict) and cap.get("capability_id") == capability_id:
                return cap
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool._get_capability_row: %s", exc)
    return None


# ── Ledger helpers ────────────────────────────────────────────────────────────

def _read_ledger(root: Path | None = None) -> list[dict[str, Any]]:
    """Read all ledger rows.  Returns [] on error or absent file (NEVER-RAISE)."""
    try:
        p = _ledger_path(root)
        if not p.exists():
            return []
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # corrupt row — skip gracefully
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool._read_ledger: %s", exc)
        return []


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_ts(ts: str) -> datetime | None:
    """Parse an ISO-8601 UTC timestamp string.  Returns None on error."""
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


# ── V10 key-economy helpers ───────────────────────────────────────────────────

def enabled_key_ids() -> set[str] | None:
    """Return the enabled capability-id set from METAB_KEYS_ENABLED, or None.

    None means "all keys enabled" (fail-open default for absent/empty env var).

    METAB_KEYS_ENABLED is a csv of numeric ids and/or "legacy":
        "1,3"      -> {"claude_code_oauth_1", "claude_code_oauth_3"}
        "legacy,2" -> {"legacy", "claude_code_oauth_2"}
        garbage tokens are silently ignored.

    Returns None on error (NEVER-RAISE).
    """
    try:
        raw = os.environ.get("METAB_KEYS_ENABLED", "").strip()
        if not raw:
            return None
        enabled: set[str] = set()
        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue
            if token == "legacy":
                enabled.add("legacy")
            elif token.isdigit():
                enabled.add(f"claude_code_oauth_{token}")
            else:
                log.debug("key_pool.enabled_key_ids: ignoring unknown token %r", token)
        # If we got tokens but none were valid, treat as absent (fail-open)
        return enabled if enabled else None
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.enabled_key_ids: %s", exc)
        return None


def is_enabled(key_id: str) -> bool:
    """Return True when key_id is in the enabled set (or all are enabled).

    key_id is a capability id like "claude_code_oauth_2" or "legacy".
    Returns True on error (fail-open — NEVER-RAISE).
    """
    try:
        ids = enabled_key_ids()
        if ids is None:
            return True  # all enabled
        return key_id in ids
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.is_enabled(%s): %s", key_id, exc)
        return True  # fail-open


def record_usage_headers(
    key_id: str,
    headers: dict,
    status_code: int,
    root: Path | None = None,
) -> None:
    """Append one header-capture row to data/metabolism/key_usage.jsonl.

    Only recognized provider rate-limit metadata is stored. Token/credential
    headers are never stored (REDLINE).  NEVER raises.

    Parameters
    ----------
    key_id : str
        Capability id ("claude_code_oauth_1", "claude_code_oauth_2", etc.) or
        "legacy" for the single CLAUDE_CODE_OAUTH_TOKEN provider.
    headers : dict
        Response headers dict.  Keys/values are strings.
    status_code : int
        HTTP response status code.
    root : Path | None
        Repo root override (for tests).
    """
    try:
        safe_prefixes = (
            "anthropic-ratelimit",
            "codex-ratelimit",
            "x-ratelimit-",
            "ratelimit-",
            "retry-after",
        )
        ratelimit_headers = {
            k: v for k, v in headers.items()
            if k.lower().startswith(safe_prefixes)
        }
        row: dict[str, Any] = {
            "schema": _USAGE_SCHEMA,
            "ts": _now_ts(),
            "key_id": key_id,
            "status": status_code,
            "headers": ratelimit_headers,
        }
        p = _usage_ledger_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.record_usage_headers(%s): %s", key_id, exc)


def _read_usage_ledger(root: Path | None = None) -> list[dict[str, Any]]:
    """Read all usage-header ledger rows.  Returns [] on error (NEVER-RAISE)."""
    try:
        p = _usage_ledger_path(root)
        if not p.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool._read_usage_ledger: %s", exc)
        return []


def usage_snapshot(root: Path | None = None) -> list[dict[str, Any]]:
    """Return per-key usage rows for the admin panel.

    Each row covers one key_id and has fields:
        key_id, present, enabled, cooling, cool_kind, reset_hint,
        window_5h_est_tokens, weekly_est_tokens,
        window_5h_sessions, weekly_sessions,
        last_outcome, last_ts,
        ratelimit_headers, headers_ts,
        mm_sessions (count of Mastermind bot rows for this key in the last 7d),
        mm_cooling (bool), mm_cool_kind (str|None), mm_reset_hint (ISO|None),
        mm_last_outcome (str|None), mm_last_ts (ISO|None)
            — Mastermind bot key-pool health (display-only join): sourced from a
            fresh data/mastermind/key_pool_status.json snapshot when present,
            else reconstructed from the key_events.jsonl tail.  Default
            False/None when the bot has published nothing.

    Covers POOL_CAPABILITY_IDS + PROVIDER_CAPABILITY_IDS + "legacy".
    Returns [] on error (NEVER-RAISE).
    """
    try:
        now = datetime.now(timezone.utc)
        window_cutoff = now - timedelta(seconds=_WINDOW_SECONDS)
        week_cutoff = now - timedelta(seconds=_WEEK_SECONDS)

        all_rows = _read_ledger(root)
        usage_rows = _read_usage_ledger(root)

        # Read Mastermind bot events and filter to known key_ids + correct schema
        # (display-only join; rotation reads stay macro-only — see _read_mm_events)
        _valid_key_ids: set[str] = (
            set(POOL_CAPABILITY_IDS) | set(PROVIDER_CAPABILITY_IDS) | {"legacy"}
        )
        mm_rows = [
            r for r in _read_mm_events(root)
            if r.get("schema") == _SCHEMA
            and r.get("key_id") in _valid_key_ids
        ]

        # Count mm_sessions per key_id in the last 7d
        mm_sessions_per_key: dict[str, int] = {}
        for row in mm_rows:
            kid = row.get("key_id")
            if not kid:
                continue
            ts = _parse_ts(row.get("ts", ""))
            if ts is not None and ts >= week_cutoff:
                mm_sessions_per_key[kid] = mm_sessions_per_key.get(kid, 0) + 1

        # Derive per-key bot cooling state (status snapshot preferred, else
        # events-tail reconstruction). Additive display fields; fail-soft to
        # {} → per-key defaults of False/None below. Bounded to the last
        # _MM_EVENTS_TAIL_LINES events rows.
        mm_state = _mm_pool_state(mm_rows[-_MM_EVENTS_TAIL_LINES:], root)

        # Build per-key aggregates from the main ledger
        per_key: dict[str, dict[str, Any]] = {}

        def _ensure(kid: str) -> dict[str, Any]:
            if kid not in per_key:
                per_key[kid] = {
                    "window_5h_est_tokens": 0,
                    "weekly_est_tokens": 0,
                    "window_5h_sessions": 0,
                    "weekly_sessions": 0,
                    "last_outcome": None,
                    "last_ts": None,
                    "_last_dt": None,
                    "cool_kind": None,
                    "reset_hint": None,
                }
            return per_key[kid]

        for row in all_rows:
            kid = row.get("key_id")
            if not kid:
                continue
            d = _ensure(kid)
            ts = _parse_ts(row.get("ts", ""))
            if ts is None:
                continue
            tokens = int(row.get("est_tokens", 0) or 0)
            if ts >= window_cutoff:
                d["window_5h_est_tokens"] += tokens
                d["window_5h_sessions"] += 1
            if ts >= week_cutoff:
                d["weekly_est_tokens"] += tokens
                d["weekly_sessions"] += 1
            if d["_last_dt"] is None or ts > d["_last_dt"]:
                d["_last_dt"] = ts
                d["last_outcome"] = row.get("outcome")
                d["last_ts"] = row.get("ts")

        # Extract cooling state from per-key agg (re-derive from ledger for accuracy)
        # We use is_cooling() for correctness; pull reset_hint + cool_kind from latest
        # cooling row (rate_limited/auth_failed) for display.
        cooling_info: dict[str, dict[str, Any]] = {}
        for row in all_rows:
            kid = row.get("key_id")
            if not kid:
                continue
            outcome = row.get("outcome", "")
            if outcome in ("rate_limited", "auth_failed") and row.get("reset_hint"):
                ts = _parse_ts(row.get("ts", ""))
                if kid not in cooling_info or (
                    ts is not None
                    and (cooling_info[kid].get("_dt") is None or ts > cooling_info[kid]["_dt"])
                ):
                    cooling_info[kid] = {
                        "_dt": ts,
                        "cool_kind": row.get("cool_kind"),
                        "reset_hint": row.get("reset_hint"),
                    }

        # Build latest header capture per key
        latest_usage: dict[str, dict[str, Any]] = {}
        for row in usage_rows:
            kid = row.get("key_id")
            if not kid:
                continue
            ts = _parse_ts(row.get("ts", ""))
            if kid not in latest_usage or (
                ts is not None
                and (latest_usage[kid].get("_dt") is None or ts > latest_usage[kid]["_dt"])
            ):
                latest_usage[kid] = {
                    "_dt": ts,
                    "ratelimit_headers": row.get("headers", {}),
                    "headers_ts": row.get("ts"),
                }

        # Determine which keys are present
        present_set: set[str] = set(discover_present_keys(root))
        # Legacy token presence (REDLINE: check only, never read value)
        try:
            from lib import config as _config  # noqa: PLC0415
            legacy_present = bool(_config.secret("CLAUDE_CODE_OAUTH_TOKEN"))
            deepseek_present = bool(_config.secret("DEEPSEEK_API_KEY"))
        except Exception:  # noqa: BLE001
            legacy_present = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", ""))
            deepseek_present = bool(os.environ.get("DEEPSEEK_API_KEY", ""))
        try:
            from engine import codex_provider as _codex  # noqa: PLC0415
            codex_accounts = {
                cap_id for cap_id, _home in _codex.available_accounts()
            }
            codex_enabled = _codex.provider_enabled()
        except Exception:  # noqa: BLE001
            codex_accounts = set()
            codex_enabled = False

        all_ids = list(POOL_CAPABILITY_IDS) + list(PROVIDER_CAPABILITY_IDS) + ["legacy"]
        enabled_ids = enabled_key_ids()  # None = all enabled

        result: list[dict[str, Any]] = []
        for kid in all_ids:
            if kid == "legacy":
                present = legacy_present
                enabled = enabled_ids is None or kid in enabled_ids
                provider = "Claude OAuth"
                model_translation = None
            elif kid.startswith("codex_account"):
                present = kid in codex_accounts
                enabled = codex_enabled
                provider = "Codex subscription"
                model_translation = (
                    "Opus/Fable→Sol · Sonnet→Terra · Haiku→Luna"
                )
            elif kid == "deepseek_api_key":
                present = deepseek_present
                enabled = True
                provider = "DeepSeek API"
                model_translation = "V4 Pro→Sol · V4 Flash→Terra"
            else:
                present = kid in present_set
                enabled = enabled_ids is None or kid in enabled_ids
                provider = "Claude OAuth"
                model_translation = None
            cooling = is_cooling(kid, root) if kid != "legacy" else False
            ci = cooling_info.get(kid, {})
            agg = per_key.get(kid, {})
            lu = latest_usage.get(kid, {})
            ms = mm_state.get(kid, {})
            result.append({
                "key_id": kid,
                "provider": provider,
                "model_translation": model_translation,
                "present": present,
                "enabled": enabled,
                "cooling": cooling,
                "cool_kind": ci.get("cool_kind"),
                "reset_hint": ci.get("reset_hint"),
                "window_5h_est_tokens": agg.get("window_5h_est_tokens", 0),
                "weekly_est_tokens": agg.get("weekly_est_tokens", 0),
                "window_5h_sessions": agg.get("window_5h_sessions", 0),
                "weekly_sessions": agg.get("weekly_sessions", 0),
                "last_outcome": agg.get("last_outcome"),
                "last_ts": agg.get("last_ts"),
                "ratelimit_headers": lu.get("ratelimit_headers", {}),
                "headers_ts": lu.get("headers_ts"),
                "mm_sessions": mm_sessions_per_key.get(kid, 0),
                # Additive Mastermind bot key-pool health (display-only join).
                "mm_cooling": ms.get("mm_cooling", False),
                "mm_cool_kind": ms.get("mm_cool_kind"),
                "mm_reset_hint": ms.get("mm_reset_hint"),
                "mm_last_outcome": ms.get("mm_last_outcome"),
                "mm_last_ts": ms.get("mm_last_ts"),
            })
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.usage_snapshot: %s", exc)
        return []


# ── Capacity Fabric read-only observation seam ───────────────────────────────

_CAPACITY_KEY_IDS = (
    "claude_code_oauth",
    *POOL_CAPABILITY_IDS,
    "codex_account",
    "codex_account_2",
    "codex_account_3",
    "deepseek_api_key",
)
_CAPACITY_LEDGER_ID = {
    "claude_code_oauth": "legacy",
    **{capability_id: capability_id for capability_id in POOL_CAPABILITY_IDS},
    "codex_account": "codex_account",
    "codex_account_2": "codex_account_2",
    "codex_account_3": "codex_account_3",
    "deepseek_api_key": "deepseek_api_key",
}


def _capacity_read_jsonl(path: Path, schema: str) -> dict[str, Any]:
    """Strictly read one Provider Control JSONL source for capacity use."""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return {"quality": "missing", "rows": []}
    except OSError:
        return {"quality": "unreadable", "rows": []}
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        return {"quality": "unreadable", "rows": []}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return {"quality": "unreadable", "rows": []}

    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"quality": "corrupt", "rows": []}
        if not isinstance(row, dict) or row.get("schema") != schema:
            return {"quality": "corrupt", "rows": []}
        rows.append(row)
    return {"quality": "ok", "rows": rows}


def _capacity_enabled_set() -> dict[str, Any]:
    """Observe METAB_KEYS_ENABLED without inheriting its fail-open errors."""
    try:
        raw = os.environ.get("METAB_KEYS_ENABLED", "").strip()
    except Exception:  # noqa: BLE001
        return {"quality": "unreadable", "all": False, "ids": set()}
    if not raw:
        return {"quality": "ok", "all": True, "ids": set()}

    enabled: set[str] = set()
    saw_invalid = False
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if token == "legacy":
            enabled.add("legacy")
        elif token.isdigit() and 1 <= int(token) <= len(POOL_CAPABILITY_IDS):
            enabled.add(f"claude_code_oauth_{int(token)}")
        else:
            saw_invalid = True
    if not enabled and saw_invalid:
        return {"quality": "corrupt", "all": False, "ids": set()}
    return {"quality": "ok", "all": False, "ids": enabled}


def _capacity_cooling_state(
    key_id: str,
    rows: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    """Evaluate cooling from a complete strict ledger without fail-soft false."""
    relevant = [row for row in rows if row.get("key_id") == key_id]
    for row in relevant:
        if not isinstance(row.get("ts"), str) or _parse_ts(row["ts"]) is None:
            return {"quality": "corrupt", "active": None}

    ok_times = [
        _parse_ts(row["ts"])
        for row in relevant
        if row.get("outcome") == "ok"
    ]
    ok_times = [value for value in ok_times if value is not None]
    latest_by_kind: dict[str, dict[str, Any]] = {}
    for row in sorted(relevant, key=lambda item: _parse_ts(item["ts"]) or datetime.min.replace(tzinfo=timezone.utc)):
        if row.get("outcome") not in ("rate_limited", "auth_failed"):
            continue
        if not row.get("reset_hint"):
            return {"quality": "corrupt", "active": None}
        kind = str(row.get("cool_kind") or "window")
        if kind not in {"window", "weekly", "auth"}:
            return {"quality": "corrupt", "active": None}
        if _parse_ts(str(row.get("reset_hint"))) is None:
            return {"quality": "corrupt", "active": None}
        latest_by_kind[kind] = row

    active_rows: list[dict[str, Any]] = []
    for kind, row in latest_by_kind.items():
        reset_at = _parse_ts(str(row["reset_hint"]))
        if reset_at is None or now >= reset_at:
            continue
        if kind == "auth":
            row_at = _parse_ts(str(row["ts"]))
            if row_at is not None and any(value >= row_at for value in ok_times):
                continue
        active_rows.append(row)

    if not active_rows:
        return {
            "quality": "ok",
            "active": False,
            "kind": None,
            "reset_at": None,
            "evidence": "exact",
            "observed_at": None,
        }
    chosen = min(
        active_rows,
        key=lambda item: _parse_ts(str(item["reset_hint"])) or datetime.max.replace(tzinfo=timezone.utc),
    )
    return {
        "quality": "ok",
        "active": True,
        "kind": str(chosen.get("cool_kind") or "window"),
        "reset_at": str(chosen["reset_hint"]),
        # Local application of the cooling timer is exact, but the active
        # reset itself came from provider evidence.
        "evidence": "provider_reported",
        "observed_at": str(chosen["ts"]),
    }


def capacity_key_observations(
    root: Path | None = None,
    *,
    state_root: Path | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Return secret-free Claude/DeepSeek observations with source quality.

    This is deliberately separate from :func:`usage_snapshot`, whose admin
    contract combines enablement/fallback and renders display zeros.  The
    capacity seam preserves a reviewed inventory, observes credential presence
    before enablement filtering, and distinguishes missing/corrupt/unreadable
    ledgers from a complete source proving a negative.
    """
    now = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    repo_root = root if root is not None else _repo_root()
    telemetry_root = state_root if state_root is not None else _state_root()
    result: dict[str, Any] = {"quality": "ok", "slots": [], "codes": []}

    try:
        import yaml  # noqa: PLC0415

        manifest_path = _manifest_path(repo_root)
        try:
            manifest_mode = manifest_path.lstat().st_mode
        except FileNotFoundError:
            manifest_quality = "missing"
            manifest_rows: dict[str, dict[str, Any]] = {}
        except OSError:
            manifest_quality = "unreadable"
            manifest_rows = {}
        else:
            if stat.S_ISLNK(manifest_mode) or not stat.S_ISREG(manifest_mode):
                manifest_quality = "unreadable"
                manifest_rows = {}
            else:
                raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
                capabilities = raw.get("capabilities") if isinstance(raw, dict) else None
                if not isinstance(capabilities, list):
                    raise ValueError("capabilities must be a list")
                manifest_rows = {}
                for row in capabilities:
                    if not isinstance(row, dict):
                        raise ValueError("capability row must be an object")
                    capability_id = row.get("capability_id")
                    if capability_id in _CAPACITY_KEY_IDS:
                        if capability_id in manifest_rows:
                            raise ValueError("duplicate capacity capability")
                        manifest_rows[str(capability_id)] = row
                manifest_quality = "ok"
    except (OSError, UnicodeError):
        manifest_quality = "unreadable"
        manifest_rows = {}
    except Exception:  # noqa: BLE001
        manifest_quality = "corrupt"
        manifest_rows = {}

    ledger = _capacity_read_jsonl(Path(telemetry_root) / _LEDGER_REL, _SCHEMA)
    usage = _capacity_read_jsonl(Path(telemetry_root) / _USAGE_LEDGER_REL, _USAGE_SCHEMA)
    enabled_source = _capacity_enabled_set()

    known_ledger_ids = set(_CAPACITY_LEDGER_ID.values())
    if ledger["quality"] == "ok":
        for row in ledger["rows"]:
            key_id = row.get("key_id")
            outcome = row.get("outcome")
            est_tokens = row.get("est_tokens")
            if (
                not isinstance(key_id, str)
                or not key_id
                or _parse_ts(str(row.get("ts") or "")) is None
                or outcome not in {"ok", "rate_limited", "auth_failed", "error"}
                or isinstance(est_tokens, bool)
                or not isinstance(est_tokens, int)
                or est_tokens < 0
            ):
                ledger = {"quality": "corrupt", "rows": []}
                break
            if outcome in {"rate_limited", "auth_failed"} and (
                row.get("cool_kind") not in {"window", "weekly", "auth"}
                or _parse_ts(str(row.get("reset_hint") or "")) is None
            ):
                ledger = {"quality": "corrupt", "rows": []}
                break
            if key_id not in known_ledger_ids:
                result["codes"].append("PROVIDER_INVENTORY_UNKNOWN")

    if usage["quality"] == "ok":
        for row in usage["rows"]:
            key_id = row.get("key_id")
            status = row.get("status")
            if (
                not isinstance(key_id, str)
                or not key_id
                or _parse_ts(str(row.get("ts") or "")) is None
                or isinstance(status, bool)
                or not isinstance(status, int)
                or not isinstance(row.get("headers"), dict)
            ):
                usage = {"quality": "corrupt", "rows": []}
                break
            if key_id not in known_ledger_ids:
                result["codes"].append("PROVIDER_INVENTORY_UNKNOWN")

    if manifest_quality != "ok":
        result["quality"] = manifest_quality
        quality_code = {
            "unreadable": "SOURCE_UNREADABLE",
            "corrupt": "SOURCE_CORRUPT",
        }.get(manifest_quality, "PROVIDER_INVENTORY_UNKNOWN")
        result["codes"].extend(["PROVIDER_INVENTORY_UNKNOWN", quality_code])

    for capability_id in _CAPACITY_KEY_IDS:
        ledger_id = _CAPACITY_LEDGER_ID[capability_id]
        codes: list[str] = []
        manifest_row = manifest_rows.get(capability_id)

        present: bool | None = None
        enabled: bool | None = None
        if manifest_quality == "ok" and manifest_row is not None:
            secret_ref = manifest_row.get("secret_ref")
            if isinstance(secret_ref, str) and secret_ref:
                try:
                    present = bool(os.environ.get(secret_ref, ""))
                except Exception:  # noqa: BLE001
                    codes.extend(["SOURCE_UNREADABLE", "PROVIDER_PRESENCE_UNKNOWN"])
            else:
                codes.extend(["SOURCE_CORRUPT", "PROVIDER_PRESENCE_UNKNOWN"])

            kill_state = str(manifest_row.get("kill_state") or "active")
            if kill_state != "active":
                enabled = False
            elif capability_id == "deepseek_api_key":
                enabled = True
            elif enabled_source["quality"] == "ok":
                enabled = bool(
                    enabled_source["all"] or ledger_id in enabled_source["ids"]
                )
            else:
                quality_code = (
                    "SOURCE_CORRUPT"
                    if enabled_source["quality"] == "corrupt"
                    else "SOURCE_UNREADABLE"
                )
                codes.extend(["PROVIDER_ENABLEMENT_UNKNOWN", quality_code])
        else:
            codes.extend(["PROVIDER_INVENTORY_UNKNOWN", "PROVIDER_PRESENCE_UNKNOWN", "PROVIDER_ENABLEMENT_UNKNOWN"])

        if present is None:
            codes.append("PROVIDER_PRESENCE_UNKNOWN")
        if enabled is None:
            codes.append("PROVIDER_ENABLEMENT_UNKNOWN")

        if ledger["quality"] == "ok":
            cooling = _capacity_cooling_state(ledger_id, ledger["rows"], now)
            if cooling["quality"] != "ok":
                cooling = {"quality": "corrupt", "active": None}
                codes.extend(["SOURCE_CORRUPT", "PROVIDER_COOLING_UNKNOWN"])
        else:
            cooling = {"quality": ledger["quality"], "active": None}
            quality_code = {
                "corrupt": "SOURCE_CORRUPT",
                "unreadable": "SOURCE_UNREADABLE",
            }.get(ledger["quality"], "PROVIDER_COOLING_UNKNOWN")
            codes.extend(["PROVIDER_COOLING_UNKNOWN", quality_code])

        key_rows = [
            row for row in ledger.get("rows", [])
            if row.get("key_id") == ledger_id
        ] if ledger["quality"] == "ok" else []
        valid_times = [
            (row, _parse_ts(str(row.get("ts") or "")))
            for row in key_rows
        ]
        if any(ts is None for _row, ts in valid_times):
            valid_times = []
            codes.extend(["SOURCE_CORRUPT", "PROVIDER_BUDGET_UNKNOWN"])
        timed_rows = [(row, ts) for row, ts in valid_times if ts is not None]
        latest = max(timed_rows, key=lambda item: item[1], default=None)
        five_cutoff = now - timedelta(seconds=_WINDOW_SECONDS)
        week_cutoff = now - timedelta(seconds=_WEEK_SECONDS)
        est_5h = None
        est_weekly = None
        if timed_rows:
            try:
                est_5h = sum(
                    int(row.get("est_tokens", 0) or 0)
                    for row, ts in timed_rows if ts >= five_cutoff
                )
                est_weekly = sum(
                    int(row.get("est_tokens", 0) or 0)
                    for row, ts in timed_rows if ts >= week_cutoff
                )
            except (TypeError, ValueError, OverflowError):
                est_5h = None
                est_weekly = None
                codes.extend(["SOURCE_CORRUPT", "PROVIDER_BUDGET_UNKNOWN"])

        header_row = None
        if usage["quality"] == "ok":
            candidates = []
            for row in usage["rows"]:
                if row.get("key_id") != ledger_id:
                    continue
                ts = _parse_ts(str(row.get("ts") or ""))
                headers = row.get("headers")
                if ts is None or not isinstance(headers, dict):
                    codes.extend(["SOURCE_CORRUPT", "PROVIDER_BUDGET_UNKNOWN"])
                    candidates = []
                    header_row = None
                    break
                safe_prefixes = (
                    "anthropic-ratelimit",
                    "codex-ratelimit",
                    "x-ratelimit-",
                    "ratelimit-",
                    "retry-after",
                )
                if any(not str(key).lower().startswith(safe_prefixes) for key in headers):
                    codes.extend(["SOURCE_CORRUPT", "PROVIDER_BUDGET_UNKNOWN"])
                    candidates = []
                    header_row = None
                    break
                candidates.append((row, ts))
            if candidates:
                header_row = max(candidates, key=lambda item: item[1])[0]
        else:
            quality_code = {
                "corrupt": "SOURCE_CORRUPT",
                "unreadable": "SOURCE_UNREADABLE",
            }.get(usage["quality"], "PROVIDER_BUDGET_UNKNOWN")
            codes.extend(["PROVIDER_BUDGET_UNKNOWN", quality_code])

        result["slots"].append({
            "capability_id": capability_id,
            "source_key_id": ledger_id,
            "present": present,
            "enabled": enabled,
            "cooling": cooling,
            "budget": {
                "headers": dict(header_row.get("headers") or {}) if header_row else {},
                "headers_ts": header_row.get("ts") if header_row else None,
                "est_5h_tokens": est_5h,
                "est_weekly_tokens": est_weekly,
            },
            "last_outcome": {
                "class": str(latest[0].get("outcome") or "unknown") if latest else "unknown",
                "observed_at": str(latest[0].get("ts")) if latest else None,
            },
            "codes": sorted(set(codes)),
        })

    result["codes"] = sorted(set(result["codes"]))
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def discover_present_keys(root: Path | None = None) -> list[str]:
    """Return the capability_ids whose env secret ref is present in os.environ.

    Only looks at POOL_CAPABILITY_IDS.  Returns a list (possibly empty).
    With 1 key present, the pool serializes — that is by design.

    REDLINE: this function checks for the PRESENCE of the env var name; it
    reads len(os.environ.get(ref_name, "")) > 0.  It does NOT read or return
    the token value.

    Returns
    -------
    list[str]
        Capability IDs whose env ref is non-empty.  May be empty.
    """
    try:
        present = []
        for cap_id in POOL_CAPABILITY_IDS:
            row = _get_capability_row(cap_id, root)
            if row is None:
                continue  # not in manifest yet
            if row.get("kill_state", "active") != "active":
                continue  # killed capability
            ref_name: str = row.get("secret_ref", "")
            if not ref_name:
                continue
            # REDLINE: check presence only — never read or store the value
            if os.environ.get(ref_name, ""):
                present.append(cap_id)

        # R-V10-3: filter present keys to the enabled set.
        # If the filter yields zero keys while unfiltered keys exist, log and
        # fall back to the unfiltered list — never strand the loop silently.
        ids = enabled_key_ids()
        if ids is not None and present:
            filtered = [k for k in present if k in ids]
            if not filtered:
                log.warning(
                    "key_pool.discover_present_keys: enabled-set %r filtered all "
                    "present keys %r — falling back to unfiltered list (R-V10-3)",
                    ids,
                    present,
                )
                return present
            return filtered

        return present
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.discover_present_keys: %s", exc)
        return []


def window_load(key_id: str, root: Path | None = None) -> int:
    """Return the estimated number of sessions for key_id in the last 5h window.

    Reads the ledger and counts rows whose ts is within the last 5h and whose
    key_id matches.  Returns 0 on error (NEVER-RAISE).
    """
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=_WINDOW_SECONDS)
        rows = _read_ledger(root)
        count = 0
        for row in rows:
            if row.get("key_id") != key_id:
                continue
            ts = _parse_ts(row.get("ts", ""))
            if ts is None:
                continue
            if ts >= cutoff:
                count += 1
        return count
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.window_load(%s): %s", key_id, exc)
        return 0


def weekly_load(key_id: str, root: Path | None = None) -> int:
    """Return the estimated number of sessions for key_id in the last 7 days.

    Returns 0 on error (NEVER-RAISE).
    """
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=_WEEK_SECONDS)
        rows = _read_ledger(root)
        count = 0
        for row in rows:
            if row.get("key_id") != key_id:
                continue
            ts = _parse_ts(row.get("ts", ""))
            if ts is None:
                continue
            if ts >= cutoff:
                count += 1
        return count
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.weekly_load(%s): %s", key_id, exc)
        return 0


def record_session(
    key_id: str,
    est_tokens: int = 0,
    cycle_id: str = "",
    stage: str = "",
    outcome: str = "ok",
    root: Path | None = None,
) -> bool:
    """Append one session row to the key ledger.

    Parameters
    ----------
    key_id : str
        The capability_id of the key used (e.g. "claude_code_oauth_1").
    est_tokens : int
        Estimated tokens consumed in this session.
    cycle_id : str
        The metabolism cycle_id (for traceability).
    stage : str
        The metabolism stage name.
    outcome : str
        "ok" | "rate_limited" | "error"

    Returns
    -------
    bool
        True if the row was written; False on any error.  NEVER raises.

    REDLINE: this function appends key_id (a capability_id string, not a token
    value) and metadata.  It NEVER writes a token value.
    """
    try:
        row: dict[str, Any] = {
            "schema": _SCHEMA,
            "ts": _now_ts(),
            "key_id": key_id,
            "cycle_id": cycle_id,
            "stage": stage,
            "est_tokens": int(est_tokens),
            "outcome": outcome,
        }
        p = _ledger_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.record_session(%s): %s", key_id, exc)
        return False


def mark_cooling(
    key_id: str,
    reset_hint: str | None = None,
    cool_kind: str = "window",
    root: Path | None = None,
) -> bool:
    """Mark a key as cooling by appending a cooling row to the ledger.

    Parameters
    ----------
    key_id : str
        The capability_id of the key to cool.
    reset_hint : str | None
        ISO-8601 UTC timestamp when the key is expected to recover.
        If None, defaults to next 5h window boundary (window), next week
        (weekly), or +24h (auth).
    cool_kind : str
        "window" (5h-quota 429), "weekly" (weekly-quota 429), or "auth"
        (401/403 — revoked/expired token; 24h cooling gives an automatic
        re-probe after the operator rotates the secret, while a successful
        session on the key clears the cooling immediately).

    Returns
    -------
    bool
        True if the row was written; False on any error.  NEVER raises.
    """
    try:
        now = datetime.now(timezone.utc)
        if reset_hint is None:
            if cool_kind == "weekly":
                reset_dt = now + timedelta(seconds=_WEEK_SECONDS)
            elif cool_kind == "auth":
                reset_dt = now + timedelta(hours=24)
            else:
                reset_dt = now + timedelta(seconds=_WINDOW_SECONDS)
            reset_hint = reset_dt.isoformat(timespec="seconds")

        row: dict[str, Any] = {
            "schema": _SCHEMA,
            "ts": _now_ts(),
            "key_id": key_id,
            "cycle_id": "",
            "stage": "cooling",
            "est_tokens": 0,
            "outcome": "auth_failed" if cool_kind == "auth" else "rate_limited",
            "cool_kind": cool_kind,
            "reset_hint": reset_hint,
        }
        p = _ledger_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.mark_cooling(%s): %s", key_id, exc)
        return False


def is_cooling(key_id: str, root: Path | None = None) -> bool:
    """Return True if key_id is currently in a cooling period.

    A key is cooling when its most recent cooling row's reset_hint is still in
    the future.  Resolved (reset_hint in the past) → not cooling.
    No cooling row → not cooling.

    Returns False on error (NEVER-RAISE — a pool error never blocks a lane).
    """
    try:
        rows = _read_ledger(root)
        # Find the most recent cooling row for this key ("rate_limited" =
        # window/weekly 429; "auth_failed" = 401/403 revoked-token cooling)
        cooling_rows = [
            r for r in rows
            if r.get("key_id") == key_id
            and r.get("outcome") in ("rate_limited", "auth_failed")
            and r.get("reset_hint")
        ]
        if not cooling_rows:
            return False

        def _ts_key(r: dict) -> datetime:
            t = _parse_ts(r.get("ts", ""))
            return t if t is not None else datetime.min.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)

        # Evaluate EVERY horizon independently (not just the most recent row):
        # a short window cooling stacked after a weekly cooling must not mask
        # the weekly horizon once the window expires (#2295 review F4).
        # Per horizon, take the LATEST cooling row of that kind and apply the
        # kind's clear rule:
        #   auth — cleared by a later "ok" row (a confirmed successful use
        #     proves the operator rotated the secret), else by reset_hint
        #     passage. Note "launched" rows never clear (R-V5-3 — recorded at
        #     launch, before success is known).
        #   window — cleared ONLY by reset_hint passage (#2469 F4); an ok
        #     within the same quota window does NOT restore exhausted quota.
        #   weekly — cleared ONLY by reset_hint passage; an intra-week ok does
        #     NOT restore a weekly-exhausted quota.
        ok_ts = [
            _ts_key(r) for r in rows
            if r.get("key_id") == key_id and r.get("outcome") == "ok"
        ]
        latest_by_kind: dict[str, dict] = {}
        for r in sorted(cooling_rows, key=_ts_key):
            latest_by_kind[r.get("cool_kind", "window")] = r

        for kind, cool_row in latest_by_kind.items():
            reset_dt = _parse_ts(cool_row.get("reset_hint", ""))
            if reset_dt is None:
                continue  # unparseable hint → treat this horizon as resolved
            if now >= reset_dt:
                continue  # horizon expired by time
            # F4 FIX: only 'auth' cooling (revoked/expired token) can be cleared
            # early by a later 'ok' row — a confirmed success proves the operator
            # rotated the secret.  A 'window' (429) cooling MUST wait for
            # reset_hint to elapse: a successful call within the same quota window
            # does NOT restore exhausted quota, so clearing the cooling would
            # cause the key to be re-selected before the window expires.
            if kind == "auth":
                cooling_ts = _ts_key(cool_row)
                if any(t >= cooling_ts for t in ok_ts):
                    continue  # auth horizon cleared by a later ok row (secret rotated)
            return True  # at least one horizon still active

        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.is_cooling(%s): %s", key_id, exc)
        return False


def all_cooling_freeze_info(
    present_keys: list[str],
    root: Path | None = None,
) -> dict[str, Any]:
    """Return freeze info when all present keys are cooling.

    If NOT all cooling, returns {"all_cooling": False}.
    If all cooling, returns:
      {"all_cooling": True, "earliest_reset": "<ISO-8601 UTC>", "key_reset_hints": {...}}

    NEVER raises.
    """
    try:
        if not present_keys:
            return {"all_cooling": False}  # no keys → not a cooling freeze

        cooling_status = {k: is_cooling(k, root) for k in present_keys}
        if not all(cooling_status.values()):
            return {"all_cooling": False}

        # All cooling — collect reset hints
        rows = _read_ledger(root)
        key_resets: dict[str, str] = {}
        for k in present_keys:
            cooling_rows = [
                r for r in rows
                if r.get("key_id") == k
                and r.get("outcome") in ("rate_limited", "auth_failed")
                and r.get("reset_hint")
            ]
            if cooling_rows:
                def _ts_key(r: dict) -> datetime:
                    t = _parse_ts(r.get("ts", ""))
                    return t if t is not None else datetime.min.replace(tzinfo=timezone.utc)
                last = sorted(cooling_rows, key=_ts_key)[-1]
                key_resets[k] = last.get("reset_hint", "")

        # earliest_reset = min of all reset hints
        parsed_resets = [_parse_ts(v) for v in key_resets.values() if v]
        parsed_resets = [r for r in parsed_resets if r is not None]
        earliest = min(parsed_resets).isoformat(timespec="seconds") if parsed_resets else ""

        return {
            "all_cooling": True,
            "earliest_reset": earliest,
            "key_reset_hints": key_resets,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.all_cooling_freeze_info: %s", exc)
        return {"all_cooling": False}


def get_secret_ref(key_id: str, root: Path | None = None) -> str | None:
    """Return the secret_ref NAME (env-var name) for a capability_id.

    REDLINE: returns the NAME only, never the value.
    Returns None if the capability is not found or has no secret_ref.
    NEVER raises.
    """
    try:
        row = _get_capability_row(key_id, root)
        if row is None:
            return None
        return row.get("secret_ref") or None
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.get_secret_ref(%s): %s", key_id, exc)
        return None
