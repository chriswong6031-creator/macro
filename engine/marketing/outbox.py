"""engine.marketing.outbox — Posting-queue contract for the D02 desk network.

Contract:
  * Producers call enqueue() to append item records to items.jsonl.
  * Only the actuator (scripts/marketing_actuator.py or W1 publisher) may call
    transition()/apply_decisions() to advance statuses in status_ledger.jsonl.
  * Admin/operator decisions are recorded via record_decision(); the actuator
    then applies them as transitions.
  * Caps are OWNED by D08 Sentinel (config/marketing.yml sentinel: block).
    This module never hardcodes its own cap — see effective_cap().

Storage layout (all paths relative to repo root; written ONLY through this module):
  data/marketing/outbox/items.jsonl          — append-only item records
  data/marketing/outbox/status_ledger.jsonl  — append-only status transitions
  data/marketing/outbox/decisions.jsonl      — operator approve/hold decisions
  data/marketing/outbox/activity.jsonl       — append-only pipeline activity
                                               (emit summaries, actuator runs)
  data/marketing/outbox/media/<as_of>/<chart_id>.svg  — chart snapshots

Concurrency: the nightly emitter and the operator-run actuator can touch these
files from separate processes on the same host. All read-check-append sections
take a best-effort advisory flock on <outbox>/.lock — fail-soft: if the lock
cannot be acquired within ~2s we proceed unlocked with a warning rather than
deadlocking a fail-soft pipeline.

This is display-tier ops state — not a forward signal ledger.  Items describe
what the actuator should post; the ledger records what actually happened.  The
gauntlet does not apply here; nulls are the honest initial state.
"""
from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from engine.marketing.ledgers import append_jsonl, read_jsonl

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_ID = "marketing.outbox/v1"

KINDS: frozenset[str] = frozenset({
    "signal", "chart", "education", "macro", "receipt",
    "watchlist", "event", "mover", "theme_list",
})

# Status machine — only these transitions are legal.
TRANSITIONS: dict[str, frozenset[str]] = {
    "queued":      frozenset({"approved", "quarantined"}),
    "approved":    frozenset({"posted", "failed", "quarantined"}),
    "failed":      frozenset({"approved", "quarantined"}),
    "posted":      frozenset(),   # terminal
    "quarantined": frozenset(),   # terminal
}

# Docket W1 §7: a failed item may be re-armed at most this many times before it
# is quarantined ("quarantine after 2 attempts, never retry-spam").
MAX_POST_ATTEMPTS: int = 2

# Ultra-fallback ONLY for when engine.marketing.sentinel cannot be imported at
# all. Matches Sentinel's weeks_1_2 floor (2/day). The real authority is the
# sentinel: block in config/marketing.yml — see effective_cap().
_SENTINEL_IMPORT_FALLBACK_CAP: int = 2


def _sentinel_defaults() -> dict[str, Any]:
    """Sentinel in-code defaults, imported so there is ONE source of truth.

    config/marketing.yml sentinel: LAW — "D02 actuator: read ALL caps from
    this block — NEVER hardcode constants in the actuator." This module keeps
    no cap constants of its own beyond the import-failure fallback above.
    """
    try:
        from engine.marketing import sentinel as _s  # noqa: PLC0415
        return {
            "max_posts_per_account_per_day": _s._DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY,
            "min_minutes_between_posts": _s._DEFAULT_MIN_MINUTES_BETWEEN_POSTS,
            "links_allowed": _s._DEFAULT_LINKS_ALLOWED,
            "max_media_posts_per_account_per_day": _s._DEFAULT_MAX_MEDIA_POSTS_PER_ACCOUNT_PER_DAY,
            "max_cashtags_per_post": _s._DEFAULT_MAX_CASHTAGS_PER_POST,
            "near_dup_jaccard": _s._DEFAULT_NEAR_DUP_JACCARD,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("outbox: sentinel defaults unavailable (%s); using floor fallback", exc)
        return {
            "max_posts_per_account_per_day": _SENTINEL_IMPORT_FALLBACK_CAP,
            "min_minutes_between_posts": 120,
            "links_allowed": False,
            "max_media_posts_per_account_per_day": 1,
            "max_cashtags_per_post": 3,
            "near_dup_jaccard": 0.50,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Directory helpers
# ─────────────────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Derive repo root the same way other marketing modules do."""
    return Path(__file__).resolve().parent.parent.parent


def outbox_dir(root: Path | str | None = None) -> Path:
    """Return the outbox directory: <root>/data/marketing/outbox."""
    r = Path(root) if root is not None else _repo_root()
    return r / "data" / "marketing" / "outbox"


def _items_path(root: Path | str | None) -> Path:
    return outbox_dir(root) / "items.jsonl"


def _ledger_path(root: Path | str | None) -> Path:
    return outbox_dir(root) / "status_ledger.jsonl"


def _decisions_path(root: Path | str | None) -> Path:
    return outbox_dir(root) / "decisions.jsonl"


def _activity_path(root: Path | str | None) -> Path:
    return outbox_dir(root) / "activity.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# Advisory lock (best-effort, fail-soft)
# ─────────────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _outbox_lock(root: Path | str | None, timeout_s: float = 2.0) -> Iterator[bool]:
    """Best-effort advisory flock on <outbox>/.lock.

    Yields True when the lock was acquired, False when we proceed unlocked
    (lock unavailable within timeout, or flock unsupported). Never raises.
    """
    lock_fh = None
    acquired = False
    try:
        try:
            import fcntl  # noqa: PLC0415  (POSIX only; fail-soft elsewhere)
            d = outbox_dir(root)
            d.mkdir(parents=True, exist_ok=True)
            lock_fh = open(d / ".lock", "a", encoding="utf-8")  # noqa: SIM115
            deadline = time.monotonic() + timeout_s
            while True:
                try:
                    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        log.warning("outbox: lock busy after %.1fs — proceeding unlocked", timeout_s)
                        break
                    time.sleep(0.05)
        except Exception as exc:  # noqa: BLE001
            log.warning("outbox: advisory lock unavailable (%s) — proceeding unlocked", exc)
        yield acquired
    finally:
        if lock_fh is not None:
            try:
                if acquired:
                    import fcntl  # noqa: PLC0415
                    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            except Exception:  # noqa: BLE001
                pass
            try:
                lock_fh.close()
            except Exception:  # noqa: BLE001
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Effective cap + sentinel contract
# ─────────────────────────────────────────────────────────────────────────────

def effective_cap(cfg: dict) -> int:
    """Return the effective per-account-per-day cap.

    AUTHORITY: D08 Sentinel (config/marketing.yml sentinel:
    max_posts_per_account_per_day; in-code Sentinel default when the block is
    absent — weeks_1_2 tier). outbox.max_posts_per_account_per_day may LOWER
    the Sentinel cap, never raise it. There is deliberately no independent
    outbox ceiling: when Sentinel's ramp raises the cap (week 5+), the outbox
    follows.
    """
    defaults = _sentinel_defaults()
    try:
        sentinel_cap = int((cfg.get("sentinel") or {}).get(
            "max_posts_per_account_per_day",
            defaults["max_posts_per_account_per_day"]))
    except Exception:  # noqa: BLE001
        sentinel_cap = int(defaults["max_posts_per_account_per_day"])
    try:
        outbox_cap = int((cfg.get("outbox") or {}).get(
            "max_posts_per_account_per_day", sentinel_cap))
    except Exception:  # noqa: BLE001
        outbox_cap = sentinel_cap
    return max(0, min(outbox_cap, sentinel_cap))


def sentinel_contract(cfg: dict) -> dict[str, Any]:
    """The Sentinel knobs the D02 actuator must honour, resolved from config
    with Sentinel in-code defaults. One read path for actuator + admin display.
    """
    defaults = _sentinel_defaults()
    sc = cfg.get("sentinel") or {}
    out: dict[str, Any] = {}
    for key, dv in defaults.items():
        try:
            v = sc.get(key, dv)
            if isinstance(dv, bool):
                # Strings parse strictly: a quoted "false" in YAML must not
                # silently enable a policy (links_allowed guards D08 R2).
                out[key] = v if isinstance(v, bool) else (
                    str(v).strip().lower() in {"1", "true", "yes"})
            else:
                out[key] = type(dv)(v)
        except Exception:  # noqa: BLE001
            out[key] = dv
    out["effective_cap"] = effective_cap(cfg)
    out["source"] = "config" if sc else "sentinel_defaults"
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Item construction
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    """Collapse whitespace runs to single spaces, strip edges."""
    return re.sub(r"\s+", " ", text.strip())


def _item_id(account: str, kind: str, text: str, as_of: str) -> str:
    """Deterministic item id: sha1(account|kind|normalized_text|as_of)[:10]."""
    normalized = _normalize_text(text)
    raw = f"{account}|{kind}|{normalized}|{as_of}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"ob-{as_of}-{digest}"


def make_item(
    *,
    account: str,
    kind: str,
    text: str,
    as_of: str,
    media: list[dict] | None = None,
    scheduled_at: str = "immediate",
    slot: str | None = None,
    priority: int = 5,
    provenance: str,
    source: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Build and validate an outbox item dict.

    Raises ValueError on invalid inputs (bad kind, empty text, empty account,
    empty provenance).  All other public API functions are fail-soft.
    """
    if not account or not account.strip():
        raise ValueError("account must be a non-empty string")
    if kind not in KINDS:
        raise ValueError(f"kind {kind!r} not in KINDS; valid: {sorted(KINDS)}")
    if not text or not text.strip():
        raise ValueError("text must be a non-empty string")
    if not provenance or not provenance.strip():
        raise ValueError("provenance must be a non-empty string")
    if not isinstance(priority, int):
        raise ValueError("priority must be an int")

    ts_now = now if now is not None else datetime.now(timezone.utc)
    created_at = ts_now.strftime("%Y-%m-%dT%H:%M:%SZ")

    item: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "id": _item_id(account, kind, text, as_of),
        "as_of": as_of,
        "account": account,
        "kind": kind,
        "text": text,
        "media": media if media is not None else [],
        "scheduled_at": scheduled_at,
        "slot": slot,
        "priority": priority,
        "provenance": provenance,
        "source": source,
        "status": "queued",
        "created_at": created_at,
    }
    return item


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_item(item: dict) -> list[str]:
    """Return a list of validation error strings; [] means valid."""
    errors: list[str] = []

    if item.get("schema") != SCHEMA_ID:
        errors.append(f"schema must be {SCHEMA_ID!r}; got {item.get('schema')!r}")

    for field in ("id", "as_of", "account", "kind", "text", "provenance"):
        v = item.get(field)
        if not v or not str(v).strip():
            errors.append(f"field {field!r} must be non-empty")

    if item.get("kind") not in KINDS:
        errors.append(f"kind {item.get('kind')!r} not in KINDS")

    if item.get("status") != "queued":
        errors.append(f"status must be 'queued' at creation; got {item.get('status')!r}")

    if not isinstance(item.get("priority"), int):
        errors.append("priority must be an int")

    for i, m in enumerate(item.get("media") or []):
        if not isinstance(m, dict):
            errors.append(f"media[{i}] must be a dict")
            continue
        if m.get("kind") != "chart_svg":
            errors.append(f"media[{i}].kind must be 'chart_svg'")
        if not m.get("path"):
            errors.append(f"media[{i}].path must be non-empty")
        if not m.get("chart_id"):
            errors.append(f"media[{i}].chart_id must be non-empty")

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Read helpers
# ─────────────────────────────────────────────────────────────────────────────

def read_items(root: Path | str | None = None) -> list[dict]:
    """Read all item records from items.jsonl.  Returns [] on any error."""
    return read_jsonl(_items_path(root))


def read_ledger(root: Path | str | None = None) -> list[dict]:
    """Read all status transition rows from status_ledger.jsonl."""
    return read_jsonl(_ledger_path(root))


def read_decisions(root: Path | str | None = None) -> list[dict]:
    """Read all operator decision rows from decisions.jsonl."""
    return read_jsonl(_decisions_path(root))


def read_activity(root: Path | str | None = None, n: int = 20) -> list[dict]:
    """Read the last n pipeline-activity rows (emit summaries, actuator runs)."""
    rows = read_jsonl(_activity_path(root))
    return rows[-n:] if n > 0 else rows


def _append_activity(root: Path | str | None, row: dict) -> None:
    """Append a pipeline-activity row. Fail-soft."""
    try:
        append_jsonl(_activity_path(root), row)
    except Exception as exc:  # noqa: BLE001
        log.warning("outbox: activity append failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Status fold
# ─────────────────────────────────────────────────────────────────────────────

def fold_state(root: Path | str | None = None) -> dict[str, Any]:
    """Single-pass fold of items + ledger + decisions.

    Returns {
      "items":     {id: item dict},
      "order":     [ids in items.jsonl order],
      "status":    {id: folded status},
      "last":      {id: last APPLIED ledger row (at/actor/note/receipt)},
      "attempts":  {id: count of transitions INTO 'failed'},
      "decisions": {id: latest decision row},
      "held":      set of ids (status queued AND latest decision 'hold'),
    }

    Only legal transitions are applied; illegal or unknown rows are skipped
    with a log.warning (defensive — the ledger should never carry illegal rows
    because transition() validates before appending, but a concurrent or
    hand-edited row must not corrupt the fold).
    """
    items: dict[str, dict] = {}
    order: list[str] = []
    for item in read_jsonl(_items_path(root)):
        item_id = item.get("id")
        if item_id and item_id not in items:
            items[item_id] = item
            order.append(item_id)

    status: dict[str, str] = {i: items[i].get("status", "queued") for i in order}
    last: dict[str, dict] = {}
    attempts: dict[str, int] = {}

    for row in read_jsonl(_ledger_path(root)):
        item_id = row.get("id")
        to_status = row.get("to")
        if not item_id or not to_status:
            log.warning("outbox.fold_state: skipping row with missing id or to: %r", row)
            continue
        current = status.get(item_id)
        if current is None:
            log.warning("outbox.fold_state: ledger row for unknown item %r; skipping", item_id)
            continue
        if to_status not in TRANSITIONS.get(current, frozenset()):
            log.warning(
                "outbox.fold_state: illegal transition %r→%r for item %r; skipping",
                current, to_status, item_id,
            )
            continue
        status[item_id] = to_status
        last[item_id] = row
        if to_status == "failed":
            attempts[item_id] = attempts.get(item_id, 0) + 1

    decisions: dict[str, dict] = {}
    for row in read_jsonl(_decisions_path(root)):
        item_id = row.get("id")
        if item_id:
            decisions[item_id] = row

    held = {
        i for i in order
        if status.get(i) == "queued" and (decisions.get(i) or {}).get("decision") == "hold"
    }

    return {
        "items": items,
        "order": order,
        "status": status,
        "last": last,
        "attempts": attempts,
        "decisions": decisions,
        "held": held,
    }


def current_statuses(root: Path | str | None = None) -> dict[str, str]:
    """Folded current status per item id (thin wrapper over fold_state)."""
    return fold_state(root)["status"]


# ─────────────────────────────────────────────────────────────────────────────
# Enqueue
# ─────────────────────────────────────────────────────────────────────────────

def enqueue(
    item: dict,
    root: Path | str | None = None,
    *,
    max_per_account_day: int | None = None,
    _ctx: dict | None = None,
) -> str:
    """Append an item to items.jsonl if valid and not duplicate/over-cap.

    Returns one of: "queued" | "duplicate" | "cap_exceeded" | "invalid:<msg>".
    Never raises.

    _ctx (internal, used by emit_from_content_plan): a preloaded
    {"ids": set, "day_counts": {(account, as_of): int}} snapshot so a batch of
    enqueues reads items.jsonl once instead of once per item. The snapshot is
    kept current as items are appended.
    """
    try:
        errors = validate_item(item)
        if errors:
            return f"invalid:{errors[0]}"

        item_id = item["id"]
        account = item["account"]
        as_of = item["as_of"]
        cap = max_per_account_day if max_per_account_day is not None else effective_cap({})

        def _check_and_append(ctx: dict) -> str:
            if item_id in ctx["ids"]:
                return "duplicate"
            # Cap: every existing same-day item consumed a slot regardless of
            # status (quarantined/failed included — refilling a bad slot the
            # same day is how retry-spam starts).
            if ctx["day_counts"].get((account, as_of), 0) >= cap:
                return "cap_exceeded"
            if not append_jsonl(_items_path(root), item):
                log.warning("outbox.enqueue: append_jsonl failed for item %r", item_id)
                return "invalid:append failed"
            ctx["ids"].add(item_id)
            ctx["day_counts"][(account, as_of)] = ctx["day_counts"].get((account, as_of), 0) + 1
            return "queued"

        if _ctx is not None:
            return _check_and_append(_ctx)

        with _outbox_lock(root):
            existing = read_items(root)
            ctx = {
                "ids": {i.get("id") for i in existing},
                "day_counts": {},
            }
            for i in existing:
                key = (i.get("account"), i.get("as_of"))
                ctx["day_counts"][key] = ctx["day_counts"].get(key, 0) + 1
            return _check_and_append(ctx)

    except Exception as exc:  # noqa: BLE001
        log.warning("outbox.enqueue: unexpected error: %s", exc)
        return f"invalid:{exc}"


# ─────────────────────────────────────────────────────────────────────────────
# Transitions
# ─────────────────────────────────────────────────────────────────────────────

def transition(
    item_id: str,
    to: str,
    *,
    actor: str,
    root: Path | str | None = None,
    note: str | None = None,
    receipt: dict | str | None = None,
    _state: dict | None = None,
) -> bool:
    """Append a status transition row to status_ledger.jsonl.

    Returns False (with log.warning) if the item is unknown or the transition
    is illegal from the current folded status. Never raises.

    _state (internal): a preloaded fold_state() snapshot for batch callers;
    kept current on success so N sequential transitions fold once, not N times.
    """
    try:
        def _do(state: dict) -> bool:
            if item_id not in state["status"]:
                log.warning("outbox.transition: unknown item_id %r", item_id)
                return False
            current = state["status"][item_id]
            if to not in TRANSITIONS.get(current, frozenset()):
                log.warning(
                    "outbox.transition: illegal transition %r→%r for %r (allowed: %s)",
                    current, to, item_id, sorted(TRANSITIONS.get(current, frozenset())),
                )
                return False
            row: dict[str, Any] = {
                "id": item_id,
                "from": current,
                "to": to,
                "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "actor": actor,
                "note": note,
                "receipt": receipt,
            }
            if not append_jsonl(_ledger_path(root), row):
                log.warning("outbox.transition: append_jsonl failed for %r→%r on %r",
                            current, to, item_id)
                return False
            state["status"][item_id] = to
            state["last"][item_id] = row
            if to == "failed":
                state["attempts"][item_id] = state["attempts"].get(item_id, 0) + 1
            return True

        if _state is not None:
            return _do(_state)
        with _outbox_lock(root):
            return _do(fold_state(root))

    except Exception as exc:  # noqa: BLE001
        log.warning("outbox.transition: unexpected error: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Operator decisions
# ─────────────────────────────────────────────────────────────────────────────

_VALID_DECISIONS = frozenset({"approve", "hold"})


def record_decision(
    item_id: str,
    decision: str,
    *,
    actor: str,
    root: Path | str | None = None,
    note: str | None = None,
) -> bool:
    """Record an operator approve/hold decision to decisions.jsonl.

    Returns False (with log.warning) on unknown item_id or invalid decision.
    Never raises.
    """
    try:
        if decision not in _VALID_DECISIONS:
            log.warning("outbox.record_decision: invalid decision %r; must be approve|hold", decision)
            return False

        with _outbox_lock(root):
            existing_ids = {i.get("id") for i in read_items(root)}
            if item_id not in existing_ids:
                log.warning("outbox.record_decision: unknown item_id %r", item_id)
                return False

            row: dict[str, Any] = {
                "id": item_id,
                "decision": decision,
                "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "actor": actor,
                "note": note,
            }
            if not append_jsonl(_decisions_path(root), row):
                log.warning("outbox.record_decision: append_jsonl failed for %r on %r",
                            decision, item_id)
                return False
            return True

    except Exception as exc:  # noqa: BLE001
        log.warning("outbox.record_decision: unexpected error: %s", exc)
        return False


def latest_decisions(root: Path | str | None = None) -> dict[str, dict]:
    """Return the last decision row per item_id."""
    result: dict[str, dict] = {}
    for row in read_decisions(root):
        item_id = row.get("id")
        if item_id:
            result[item_id] = row
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Decision application (the actuator's write path)
# ─────────────────────────────────────────────────────────────────────────────

def apply_decisions(
    root: Path | str | None = None,
    *,
    actor: str = "actuator",
    note: str | None = None,
    max_attempts: int = MAX_POST_ATTEMPTS,
) -> dict[str, Any]:
    """Apply pending operator approvals as status transitions (batch, one fold).

    Rules:
      * approve + status queued              → approved
      * approve + status failed, decision recorded AFTER the failure
                                             → approved (re-arm) …unless the
        item already failed max_attempts times, in which case → quarantined
        ("never retry-spam", docket W1 §7). A stale approve (recorded before
        the failure) does nothing — a failure always needs a fresh human look.
      * hold                                 → no transition (held overlay)

    Returns {"approved": [ids], "rearmed": [ids], "quarantined": [ids]}.
    Never raises.
    """
    out: dict[str, Any] = {"approved": [], "rearmed": [], "quarantined": []}
    try:
        with _outbox_lock(root):
            state = fold_state(root)
            for item_id, dec in state["decisions"].items():
                if dec.get("decision") != "approve":
                    continue
                status = state["status"].get(item_id)
                if status == "queued":
                    if transition(item_id, "approved", actor=actor, root=root,
                                  note=note or "operator approval applied",
                                  _state=state):
                        out["approved"].append(item_id)
                elif status == "failed":
                    last_at = (state["last"].get(item_id) or {}).get("at") or ""
                    dec_at = dec.get("at") or ""
                    if dec_at <= last_at:
                        continue  # stale approve from before the failure
                    if state["attempts"].get(item_id, 0) >= max_attempts:
                        if transition(item_id, "quarantined", actor=actor, root=root,
                                      note=f"max attempts reached ({max_attempts})",
                                      _state=state):
                            out["quarantined"].append(item_id)
                    else:
                        if transition(item_id, "approved", actor=actor, root=root,
                                      note=note or "re-armed after failure (fresh approval)",
                                      _state=state):
                            out["rearmed"].append(item_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("outbox.apply_decisions: unexpected error: %s", exc)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# emit_from_content_plan
# ─────────────────────────────────────────────────────────────────────────────

_SLOT_SUFFIX_TIMES = {
    "AM":  "T14:00:00Z",
    "PM":  "T17:30:00Z",
    "EOD": "T20:15:00Z",
}


def _scheduled_at_for_slot(slot: str, as_of: str) -> str:
    """Map slot suffix to an advisory scheduled_at time.

    Advisory times; W1 actuator applies jitter/spacing before actual posting.
    """
    suffix = slot.rsplit("-", 1)[-1] if "-" in slot else ""
    time_suffix = _SLOT_SUFFIX_TIMES.get(suffix)
    if time_suffix:
        return f"{as_of}{time_suffix}"
    return "immediate"


def emit_from_content_plan(
    plan: dict,
    root: Path | str | None = None,
    *,
    cfg: dict | None = None,
    day_prefix: str = "D1",
    now: datetime | None = None,
) -> dict:
    """Map a content_plan dict to outbox items and enqueue them.

    Only processes items whose slot startswith f"{day_prefix}-".
    Items with a truthy "_live_gate_fail" field are skipped (never queue stale
    or invalidated signals). Items the D08 Sentinel gate quarantined
    (status == "quarantined") or left unverified (sentinel_ok is False — the
    gate's crash path stamps this) are skipped too: quarantined items surface
    on the admin Sentinel/Outbox views with reasons, never as queueable posts.

    Reads items.jsonl ONCE for the whole batch (enqueue _ctx snapshot) and
    appends a summary row to activity.jsonl so the admin Outbox page can show
    what the last emit did and why items were skipped.

    Returns a summary dict: {emitted, skipped_dupe, skipped_cap, skipped_gate,
    skipped_sentinel, skipped_invalid, media_written, by_account}.
    """
    ts_now = now if now is not None else datetime.now(timezone.utc)
    as_of: str = plan.get("as_of") or ts_now.strftime("%Y-%m-%d")

    featured_charts: dict[str, dict] = {}
    for fc in plan.get("featured_charts") or []:
        fc_id = fc.get("id")
        if fc_id:
            featured_charts[fc_id] = fc

    counts: dict[str, Any] = {
        "emitted": 0,
        "skipped_dupe": 0,
        "skipped_cap": 0,
        "skipped_gate": 0,
        "skipped_sentinel": 0,
        "skipped_invalid": 0,
        "media_written": 0,
        "by_account": {},
    }

    cap = effective_cap(cfg or {})

    with _outbox_lock(root):
        existing = read_items(root)
        ctx: dict[str, Any] = {"ids": {i.get("id") for i in existing}, "day_counts": {}}
        for i in existing:
            key = (i.get("account"), i.get("as_of"))
            ctx["day_counts"][key] = ctx["day_counts"].get(key, 0) + 1

        for acct_block in plan.get("accounts") or []:
            account_id = acct_block.get("id") or acct_block.get("name") or ""
            for qi in acct_block.get("queue") or []:
                try:
                    slot = qi.get("slot") or ""

                    if not slot.startswith(f"{day_prefix}-"):
                        continue

                    if qi.get("_live_gate_fail"):
                        counts["skipped_gate"] += 1
                        continue

                    # D08 Sentinel verdicts on the plan item. A missing
                    # sentinel_ok field (pre-D08 plan) passes through.
                    if qi.get("status") == "quarantined" or qi.get("sentinel_ok") is False:
                        counts["skipped_sentinel"] += 1
                        continue

                    parts = [
                        (qi.get("headline") or "").strip(),
                        (qi.get("body") or "").strip(),
                    ]
                    text = "\n\n".join(p for p in parts if p)
                    if not text:
                        counts["skipped_invalid"] += 1
                        continue

                    media: list[dict] = []
                    chart_id = qi.get("chart_id")
                    if chart_id and chart_id in featured_charts:
                        fc = featured_charts[chart_id]
                        svg_str = fc.get("svg") or ""
                        if svg_str:
                            media_dir = outbox_dir(root) / "media" / as_of
                            svg_rel_path = f"data/marketing/outbox/media/{as_of}/{chart_id}.svg"
                            try:
                                media_dir.mkdir(parents=True, exist_ok=True)
                                svg_path = media_dir / f"{chart_id}.svg"
                                if not svg_path.exists():
                                    tmp_fd, tmp_p = tempfile.mkstemp(
                                        dir=media_dir, prefix=".tmp_", suffix=".svg"
                                    )
                                    try:
                                        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                                            f.write(svg_str)
                                        os.replace(tmp_p, svg_path)
                                        counts["media_written"] += 1
                                    except Exception:
                                        try:
                                            os.unlink(tmp_p)
                                        except Exception:  # noqa: BLE001
                                            pass
                                        raise
                            except Exception as exc:  # noqa: BLE001
                                log.warning(
                                    "outbox.emit_from_content_plan: media write failed for %r: %s",
                                    chart_id, exc)

                            media.append({
                                "kind": "chart_svg",
                                "path": svg_rel_path,
                                "chart_id": chart_id,
                                "ticker": qi.get("ticker") or fc.get("ticker") or "",
                            })

                    scheduled_at = _scheduled_at_for_slot(slot, as_of)

                    source: dict[str, Any] = {
                        "plan_item_id": qi.get("id"),
                        "chart_id": chart_id,
                    }
                    plan_block = qi.get("_plan")
                    if isinstance(plan_block, dict):
                        source["signal_id"] = plan_block.get("id")

                    try:
                        item = make_item(
                            account=account_id,
                            kind=qi.get("type") or "signal",
                            text=text,
                            as_of=as_of,
                            media=media,
                            scheduled_at=scheduled_at,
                            slot=slot,
                            priority=5,
                            provenance="content_studio",
                            source=source,
                            now=ts_now,
                        )
                    except ValueError as exc:
                        log.warning("outbox.emit_from_content_plan: make_item failed: %s", exc)
                        counts["skipped_invalid"] += 1
                        continue

                    result_code = enqueue(item, root, max_per_account_day=cap, _ctx=ctx)
                    if result_code == "queued":
                        counts["emitted"] += 1
                        counts["by_account"][account_id] = counts["by_account"].get(account_id, 0) + 1
                    elif result_code == "duplicate":
                        counts["skipped_dupe"] += 1
                    elif result_code == "cap_exceeded":
                        counts["skipped_cap"] += 1
                    elif result_code.startswith("invalid:"):
                        log.warning("outbox.emit_from_content_plan: invalid item: %s", result_code)
                        counts["skipped_invalid"] += 1

                except Exception as exc:  # noqa: BLE001
                    log.warning("outbox.emit_from_content_plan: per-item error: %s", exc)
                    counts["skipped_invalid"] += 1

    _append_activity(root, {
        "at": ts_now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lane": "emit",
        "as_of": as_of,
        "cap": cap,
        **{k: v for k, v in counts.items() if k != "by_account"},
        "by_account": counts["by_account"],
    })

    return counts
