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
_USAGE_LEDGER_REL = "data/metabolism/key_usage.jsonl"
_USAGE_SCHEMA = "metabolism.key_usage.v1"

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


def _usage_ledger_path(root: Path | None = None) -> Path:
    base = root if root is not None else _repo_root()
    return base / _USAGE_LEDGER_REL


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

    Only headers whose names start with "anthropic-ratelimit" are stored.
    Token values are never stored (REDLINE).  NEVER raises.

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
        ratelimit_headers = {
            k: v for k, v in headers.items()
            if k.lower().startswith("anthropic-ratelimit")
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
        ratelimit_headers, headers_ts.

    Covers POOL_CAPABILITY_IDS + "legacy".
    Returns [] on error (NEVER-RAISE).
    """
    try:
        now = datetime.now(timezone.utc)
        window_cutoff = now - timedelta(seconds=_WINDOW_SECONDS)
        week_cutoff = now - timedelta(seconds=_WEEK_SECONDS)

        all_rows = _read_ledger(root)
        usage_rows = _read_usage_ledger(root)

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
        except Exception:  # noqa: BLE001
            legacy_present = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", ""))

        all_ids = list(POOL_CAPABILITY_IDS) + ["legacy"]
        enabled_ids = enabled_key_ids()  # None = all enabled

        result: list[dict[str, Any]] = []
        for kid in all_ids:
            present = (legacy_present if kid == "legacy" else kid in present_set)
            enabled = (enabled_ids is None or kid in enabled_ids)
            cooling = is_cooling(kid, root) if kid != "legacy" else False
            ci = cooling_info.get(kid, {})
            agg = per_key.get(kid, {})
            lu = latest_usage.get(kid, {})
            result.append({
                "key_id": kid,
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
            })
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("key_pool.usage_snapshot: %s", exc)
        return []


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
