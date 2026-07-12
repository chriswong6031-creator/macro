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
All state is in data/metabolism/key_ledger.jsonl (append-only, git-tracked).
The pool reads the ledger on every call; it holds no in-process mutable state
between calls.  A fresh process on a fresh key resumes from the ledger.

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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_MANIFEST_REL = "config/capability_manifest.yml"
_LEDGER_REL = "data/metabolism/key_ledger.jsonl"
_SCHEMA = "metabolism.key_ledger.v1"

# The capability_ids this pool manages (in order).
# Operator adds keys by setting CLAUDE_CODE_OAUTH_TOKEN_1/_2/_3 as GH secrets
# and adding rows to capability_manifest.yml.  The pool discovers which subset
# is present by checking if the env ref exists.
POOL_CAPABILITY_IDS = [
    "claude_code_oauth_1",
    "claude_code_oauth_2",
    "claude_code_oauth_3",
]

# 5-hour window in seconds
_WINDOW_SECONDS = 5 * 3600
# 1 week in seconds
_WEEK_SECONDS = 7 * 24 * 3600


# ── Path helpers ─────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Auto-detect repo root from this file's location (engine/neuralweb/)."""
    return Path(__file__).resolve().parent.parent.parent


def _manifest_path(root: Path | None = None) -> Path:
    base = root if root is not None else _repo_root()
    return base / _MANIFEST_REL


def _ledger_path(root: Path | None = None) -> Path:
    base = root if root is not None else _repo_root()
    return base / _LEDGER_REL


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

        # Sort by ts ascending, take the last
        def _ts_key(r: dict) -> datetime:
            t = _parse_ts(r.get("ts", ""))
            return t if t is not None else datetime.min.replace(tzinfo=timezone.utc)

        last_cooling = sorted(cooling_rows, key=_ts_key)[-1]
        reset_hint = last_cooling.get("reset_hint", "")
        reset_dt = _parse_ts(reset_hint)
        if reset_dt is None:
            return False  # unparseable hint → treat as resolved

        now = datetime.now(timezone.utc)

        # A subsequent "ok" row clears cooling ONLY for window/auth kinds.
        # A "weekly" cooling clears ONLY when reset_hint passes (i.e. now >= reset_dt).
        # An "ok" row recorded before the session completes (former pick-time recording)
        # must NOT clear weekly cooling — that would let a weekly-exhausted key be
        # re-picked on the very next cycle (R-V5-3).
        cool_kind = last_cooling.get("cool_kind", "window")
        if cool_kind in ("window", "auth"):
            # window and auth coolings are cleared by a later "ok" row
            cooling_ts = _ts_key(last_cooling)
            for r in rows:
                if r.get("key_id") != key_id:
                    continue
                if r.get("outcome") == "ok":
                    row_ts = _ts_key(r)
                    if row_ts >= cooling_ts:
                        return False  # key was used successfully at or after the cooling row
        # weekly cooling: cleared ONLY by time (reset_hint passage), not by ok rows

        return now < reset_dt
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
