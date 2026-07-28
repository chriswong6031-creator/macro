"""engine.marketing.reply_queue — the reply desk's store (XG-W4).

The outbox pattern, deliberately NOT the outbox. Replies share the outbox's
discipline (content-hash id, status machine with an in-flight state, attempts
cap, advisory flock, append-only ledger) but nothing else: a separate store,
a separate id namespace, a separate cap authority, and a separate sender.

Why a separate store (charter §5, load-bearing facts):
  * **Buffer cannot reply.** ``social_publisher._CREATE_POST_MUTATION`` has no
    reply target, so every reply necessarily leaves the sanctioned posting rail.
    Reply items must never be mistaken for postable outbox items by the
    publisher, the actuator, or the sentinel's plan gate.
  * **Zero repo writes.** The M1 Mac is the nightly render host; an intraday
    writer inside the render checkout collides with render-lane resets. The
    whole reply desk lives under a HOST state dir (``~/.mastermind/reply_desk``
    by default, ``MASTERMIND_REPLY_DESK_DIR`` to override) — see ``state_dir()``.
  * **Different lifecycle.** Outbox items wait for a slot; reply drafts DIE.
    A reply outside its window is worse than no reply, so ``expires_at`` is
    enforced by the store itself, not by a caller's good intentions.

Two laws this module enforces that live nowhere else:

  * **One conversation, one owner** (charter §2 amendment 6, §5). Two of our
    accounts must never reply to the same thread — the coordination signal no
    existing gate catches. ``enqueue()`` refuses a thread another account
    already holds. The lock is held by every LIVE status including ``sent``
    (we replied; the conversation is ours) and released only by ``rejected`` /
    ``expired`` (we never spoke).
  * **The standing 0-cap opens per the mode dial only** (D08; the operator's
    2026-07-28 directive is the opening ruling). ``may_send()`` refuses every
    send at M0 regardless of config, and clamps M1+ to a hard ceiling that no
    config edit can raise.

Public API:
    state_dir(root=None) -> Path                  # host state root, never repo
    MODES / resolve_mode(cfg, account) -> str      # M0/M1 dial, M2/M3 gated off
    make_item(...) -> dict                         # build + stamp, no I/O
    validate_item(item) -> list[str]               # [] means valid
    enqueue(item, *, root=None, cfg=None) -> dict  # one-owner + dup checks
    read_items(root=None) -> list[dict]
    fold_state(root=None) -> dict                  # items + status + attempts
    transition(item_id, to, *, actor, ...) -> bool
    expire_due(*, now=None, root=None) -> list[str]  # auto-kill past window
    claim(item_id, *, holder, lease_s=..., ...) -> dict | None
    release_expired_claims(*, now=None, root=None) -> list[str]
    may_send(account, *, cfg, root=None, as_of=None) -> dict
    mark_sent(item_id, *, receipt, ...) -> bool
    record_outcome(item_id, **fields) -> bool      # telemetry seam (XG-W6)
    sends_today(account, as_of, root=None) -> int
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from engine.marketing.ledgers import append_jsonl, read_jsonl

log = logging.getLogger(__name__)

SCHEMA_ID = "marketing.reply/v1"

# ---------------------------------------------------------------------------
# Mode dial (charter §5). M2/M3 exist as KEYS so the escalation path is legible,
# but they are config-gated OFF: the per-account health monitor + network
# tripwire (XG-W6) are a HARD PRECONDITION for any dial flip above M1, because
# a failure must be able to halt ONE account without halting seven. Until that
# lands, `modes_enabled` may not contain M2/M3 and `resolve_mode` clamps to M0.
# ---------------------------------------------------------------------------
MODES: tuple[str, ...] = ("M0", "M1", "M2", "M3")
DEFAULT_MODE = "M0"
#: Modes a config may actually select today. XG-W6 is the gate for widening it.
SHIPPABLE_MODES: frozenset[str] = frozenset({"M0", "M1"})

# ---------------------------------------------------------------------------
# Status machine. `claimed` is the in-flight state: the desktop session holds a
# lease on the item and is navigating to the thread. A crash leaves the item in
# `claimed` with a stale lease, which `release_expired_claims()` returns to
# `queued` — deliberately NOT to `approved`. We cannot know whether an expired
# lease posted or not, so a human re-approves. That friction is the point.
# ---------------------------------------------------------------------------
TRANSITIONS: dict[str, frozenset[str]] = {
    "queued":   frozenset({"approved", "rejected", "expired"}),
    "approved": frozenset({"claimed", "queued", "rejected", "expired"}),
    # `claimed` deliberately does NOT admit `expired`. An item whose lease is
    # live may already be posted; expiring it under the desktop session turns a
    # PUBLIC reply into an unrecorded one, and the receipt then bounces forever
    # against a terminal status. The lease governs an in-flight item — when it
    # runs out the item returns to `queued`, and expiry may take it there.
    "claimed":  frozenset({"sent", "failed", "queued", "rejected"}),
    "failed":   frozenset({"approved", "queued", "rejected", "expired"}),
    "sent":     frozenset(),   # terminal
    "rejected": frozenset(),   # terminal
    "expired":  frozenset(),   # terminal
}

#: Entering either of these states means the item is live toward a send, so the
#: attempts cap is checked on EVERY edge into them. Guarding only `failed →
#: approved` left `failed → queued → approved` as a free re-arm.
_ATTEMPT_GATED_STATUSES: frozenset[str] = frozenset({"approved", "claimed"})

#: Statuses that HOLD the one-conversation-one-owner lock on a thread. `sent`
#: holds it forever (we spoke; the thread is ours). `rejected`/`expired` release
#: it — we never spoke, so a sibling account may legitimately take the thread.
OWNING_STATUSES: frozenset[str] = frozenset({"queued", "approved", "claimed", "failed", "sent"})

#: Statuses that are done and never move again.
TERMINAL_STATUSES: frozenset[str] = frozenset({"sent", "rejected", "expired"})

TIERS: frozenset[str] = frozenset({"relationship", "conversion", "breakout", "inbound"})

MAX_SEND_ATTEMPTS: int = 2

#: Default lease on a claimed item. A desktop session that has not reported a
#: receipt inside this window has lost the item.
DEFAULT_LEASE_S: int = 600

#: Default life of a draft. Charter §3: replies live in a 5-15 minute window;
#: a draft that has aged past this is dead weight, not a backlog.
DEFAULT_TTL_MIN: int = 45


# ---------------------------------------------------------------------------
# Paths — HOST state only. Nothing here ever writes inside the repo checkout.
# ---------------------------------------------------------------------------
def state_dir(root: Path | str | None = None) -> Path:
    """Host-state root for the whole reply desk.

    Resolution order: explicit ``root`` (tests, and the admin surface passing a
    fixture dir) > ``MASTERMIND_REPLY_DESK_DIR`` > ``~/.mastermind/reply_desk``.

    This is NEVER inside the repo checkout by design (charter §5): the M1 Mac
    is the nightly render host, and an intraday writer in the render tree
    collides with render-lane resets. The house law is "pollers make zero repo
    writes"; the reply desk is a poller plus a queue, so it makes none either.
    """
    if root is not None:
        return Path(root).expanduser()
    env = os.environ.get("MASTERMIND_REPLY_DESK_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".mastermind" / "reply_desk"


def store_dir(root: Path | str | None = None) -> Path:
    """The queue's own append-only ledgers."""
    return state_dir(root) / "store"


def _items_path(root: Path | str | None) -> Path:
    return store_dir(root) / "items.jsonl"


def _ledger_path(root: Path | str | None) -> Path:
    return store_dir(root) / "ledger.jsonl"


@contextlib.contextmanager
def _store_lock(root: Path | str | None, timeout_s: float = 2.0) -> Iterator[bool]:
    """Best-effort advisory flock on <store>/.lock (outbox posture).

    Yields True when the lock was acquired, False when we proceed unlocked.
    Never raises: a lock we cannot take must not wedge the desk.
    """
    lock_fh = None
    acquired = False
    try:
        try:
            import fcntl  # noqa: PLC0415  (POSIX only; fail-soft elsewhere)

            d = store_dir(root)
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
                        log.warning("reply_queue: lock busy after %.1fs — proceeding unlocked", timeout_s)
                        break
                    time.sleep(0.05)
        except Exception as exc:  # noqa: BLE001
            log.warning("reply_queue: advisory lock unavailable (%s) — proceeding unlocked", exc)
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


# ---------------------------------------------------------------------------
# Mode dial
# ---------------------------------------------------------------------------
def resolve_mode(cfg: dict | None, account: str) -> str:
    """Resolve one account's dial setting, clamped to what actually ships.

    A config asking for a mode outside ``modes_enabled`` — or for M2/M3 at all,
    which XG-W6's health monitor + network tripwire gate — is clamped to M0 and
    announced. Silently honouring it would arm autonomous replying on an account
    with no way to halt it alone.
    """
    rd = ((cfg or {}).get("reply_desk") or {})
    # The whole-desk kill switch. Documented to the operator in the runbook, so
    # it has to actually do something: a switch that reads as off while the desk
    # keeps exporting is worse than no switch at all. Truthiness, not `is False`
    # — a hand-edited `enabled: 0` must disable too. Absent means enabled.
    if "enabled" in rd and not rd["enabled"]:
        return DEFAULT_MODE

    enabled_raw = rd.get("modes_enabled") or list(SHIPPABLE_MODES)
    enabled = {str(m).strip().upper() for m in enabled_raw} & set(MODES)
    # XG-W6 precondition: M2/M3 can never be enabled by a config edit alone.
    ungated = enabled - SHIPPABLE_MODES
    if ungated:
        print(
            f"::warning title=reply-desk-mode-gated::reply_desk.modes_enabled requests "
            f"{sorted(ungated)} but M2/M3 require the XG-W6 per-account health monitor "
            f"+ network tripwire — clamped to {sorted(SHIPPABLE_MODES)}",
            flush=True,
        )
        enabled &= SHIPPABLE_MODES
    if not enabled:
        enabled = {DEFAULT_MODE}

    mode_cfg = rd.get("mode") or {}
    per_account = mode_cfg.get("accounts") or {}
    want = str(per_account.get(account) or mode_cfg.get("default") or DEFAULT_MODE).strip().upper()
    if want not in MODES:
        log.warning("reply_queue: unknown mode %r for %r — using %s", want, account, DEFAULT_MODE)
        return DEFAULT_MODE
    if want not in enabled:
        print(
            f"::warning title=reply-desk-mode-clamped::account {account!r} asks for {want} "
            f"but only {sorted(enabled)} are enabled — clamped to {DEFAULT_MODE}",
            flush=True,
        )
        return DEFAULT_MODE
    return want


# ---------------------------------------------------------------------------
# Item construction
# ---------------------------------------------------------------------------
_STATUS_ID_RE = re.compile(r"/status/(\d+)")


def status_id_from_url(url: str) -> str:
    """Pull the numeric status id out of an x.com/twitter.com post URL."""
    m = _STATUS_ID_RE.search(str(url or ""))
    return m.group(1) if m else ""


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _item_id(account: str, thread_key: str, draft: str, as_of: str) -> str:
    """Content-hash id (outbox posture): same account + thread + draft = same id,
    so a re-run of discovery never doubles the queue."""
    payload = f"{account}|{thread_key}|{_normalize_text(draft)}|{as_of}"
    return f"rq-{as_of}-{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:10]}"  # noqa: S324


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: object) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def ttl_min_for(cfg: dict | None) -> int:
    """Configured draft lifetime. Config must actually reach the constructor —
    a documented knob nothing reads is a knob that lies."""
    try:
        return int(((cfg or {}).get("reply_desk") or {}).get("ttl_min", DEFAULT_TTL_MIN))
    except (TypeError, ValueError):
        return DEFAULT_TTL_MIN


def lease_s_for(cfg: dict | None) -> int:
    """Configured lease length (see ttl_min_for)."""
    try:
        return int(((cfg or {}).get("reply_desk") or {}).get("lease_s", DEFAULT_LEASE_S))
    except (TypeError, ValueError):
        return DEFAULT_LEASE_S


def make_item(
    *,
    account: str,
    target_url: str,
    parent_author: str,
    parent_excerpt: str,
    draft: str,
    tier: str,
    score: float,
    score_components: dict | None = None,
    alt_drafts: list[str] | None = None,
    chart: dict | None = None,
    family: str | None = None,
    thread_root_id: str | None = None,
    target_status_id: str | None = None,
    as_of: str | None = None,
    mode: str = DEFAULT_MODE,
    not_before: str | None = None,
    ttl_min: int | None = None,
    cfg: dict | None = None,
    now: datetime | None = None,
    provenance: str = "reply_desk",
) -> dict:
    """Build a reply-queue item. Raises ValueError on inputs that must not pass.

    ``chart`` carries BOTH ``local_path`` and ``public_url`` (charter §5) so a
    future official-API write rail needs no schema rewrite.

    ``ttl_min`` falls back to ``cfg.reply_desk.ttl_min`` and only then to the
    module default, so the documented config knob actually governs.
    """
    if ttl_min is None:
        ttl_min = ttl_min_for(cfg)
    if not account or not str(account).strip():
        raise ValueError("account must be a non-empty string")
    if not draft or not str(draft).strip():
        raise ValueError("draft must be a non-empty string")
    if tier not in TIERS:
        raise ValueError(f"tier {tier!r} not in {sorted(TIERS)}")
    sid = str(target_status_id or status_id_from_url(target_url) or "").strip()
    if not sid:
        raise ValueError(f"target_status_id missing and unparseable from {target_url!r}")

    ts_now = now if now is not None else datetime.now(timezone.utc)
    day = as_of or ts_now.strftime("%Y-%m-%d")
    thread_key = str(thread_root_id or sid).strip()

    media = None
    if chart:
        media = {
            "local_path": chart.get("local_path") or chart.get("media_png_path"),
            "public_url": chart.get("public_url") or chart.get("media_url"),
            "chart_id": chart.get("chart_id"),
        }

    return {
        "schema": SCHEMA_ID,
        "id": _item_id(account, thread_key, draft, day),
        "as_of": day,
        "account": str(account).strip(),
        "target_url": str(target_url or "").strip(),
        "target_status_id": sid,
        "thread_key": thread_key,
        "parent_author": str(parent_author or "").strip(),
        "parent_excerpt": str(parent_excerpt or "")[:500],
        "draft": str(draft).strip(),
        "alt_drafts": list(alt_drafts or []),
        "family": family,
        "chart": media,
        "tier": tier,
        "score": round(float(score), 6),
        "score_components": dict(score_components or {}),
        "not_before": not_before or _iso(ts_now),
        "expires_at": _iso(ts_now + timedelta(minutes=int(ttl_min))),
        "mode": str(mode or DEFAULT_MODE).upper(),
        "status": "queued",
        "provenance": provenance,
        "created_at": _iso(ts_now),
        # Telemetry seam — XG-W6 lands parent-adjusted labels on top of these.
        "sent_at": None,
        "author_replied": None,
        "likes": None,
        "follower_delta": None,
    }


def validate_item(item: dict) -> list[str]:
    """Return a list of validation errors; [] means valid."""
    errors: list[str] = []
    if item.get("schema") != SCHEMA_ID:
        errors.append(f"schema must be {SCHEMA_ID!r}; got {item.get('schema')!r}")
    for field in ("id", "as_of", "account", "target_status_id", "thread_key", "draft"):
        if not str(item.get(field) or "").strip():
            errors.append(f"field {field!r} must be non-empty")
    if item.get("tier") not in TIERS:
        errors.append(f"tier {item.get('tier')!r} not in {sorted(TIERS)}")
    if item.get("status") != "queued":
        errors.append(f"status must be 'queued' at creation; got {item.get('status')!r}")
    if not isinstance(item.get("score"), (int, float)):
        errors.append("score must be numeric")
    if not isinstance(item.get("score_components"), dict):
        errors.append("score_components must be a dict (assumptions law §8: inspectable)")
    if _parse_iso(item.get("expires_at")) is None:
        errors.append("expires_at must be an ISO-8601 UTC stamp")
    if str(item.get("mode") or "").upper() not in MODES:
        errors.append(f"mode {item.get('mode')!r} not in {list(MODES)}")
    chart = item.get("chart")
    if chart is not None:
        if not isinstance(chart, dict):
            errors.append("chart must be a dict or None")
        elif not chart.get("local_path") and not chart.get("public_url"):
            errors.append("chart must carry at least one of local_path/public_url")
    return errors


# ---------------------------------------------------------------------------
# Read / fold
# ---------------------------------------------------------------------------
def read_items(root: Path | str | None = None) -> list[dict]:
    """Every item ever enqueued, in insertion order."""
    return read_jsonl(_items_path(root))


def read_ledger(root: Path | str | None = None) -> list[dict]:
    return read_jsonl(_ledger_path(root))


def fold_state(root: Path | str | None = None) -> dict[str, Any]:
    """Fold items + ledger into current state.

    Returns {items: {id: item}, status: {id: str}, attempts: {id: int},
             last: {id: row}, claims: {id: {holder, lease_until}}}.
    """
    items: dict[str, dict] = {}
    for row in read_items(root):
        iid = str(row.get("id") or "")
        if iid:
            items[iid] = row

    status = {iid: str(it.get("status") or "queued") for iid, it in items.items()}
    attempts: dict[str, int] = {}
    last: dict[str, dict] = {}
    claims: dict[str, dict] = {}

    for row in read_ledger(root):
        iid = str(row.get("id") or "")
        if iid not in items:
            continue
        to = str(row.get("to") or "")
        if to:
            status[iid] = to
            last[iid] = row
        if to == "failed":
            attempts[iid] = attempts.get(iid, 0) + 1
        if to == "claimed":
            claims[iid] = {
                "holder": row.get("holder"),
                "lease_until": row.get("lease_until"),
                "at": row.get("at"),
            }
        elif to in TERMINAL_STATUSES or to in {"queued", "approved", "failed"}:
            claims.pop(iid, None)

    return {"items": items, "status": status, "attempts": attempts, "last": last, "claims": claims}


def sends_today(account: str, as_of: str, root: Path | str | None = None) -> int:
    """Count REAL sends for one account on one day.

    This is the number the sentinel's reply cap gates. It counts ledger rows
    (``to == "sent"``), not queue depth — the pre-XG-W4 counter was vacuous
    precisely because nothing ever produced a countable send.
    """
    state = fold_state(root)
    n = 0
    for iid, st in state["status"].items():
        if st != "sent":
            continue
        item = state["items"].get(iid) or {}
        if str(item.get("account") or "") != account:
            continue
        row = state["last"].get(iid) or {}
        sent_day = str(row.get("at") or item.get("sent_at") or "")[:10]
        if sent_day == as_of:
            n += 1
    return n


# ---------------------------------------------------------------------------
# Enqueue — one-owner-per-thread is enforced HERE, not by convention
# ---------------------------------------------------------------------------
def thread_owner(thread_key: str, root: Path | str | None = None, *, _state: dict | None = None) -> str | None:
    """Which account currently owns this thread, if any."""
    state = _state if _state is not None else fold_state(root)
    for iid, item in state["items"].items():
        if str(item.get("thread_key") or "") != str(thread_key):
            continue
        if state["status"].get(iid) in OWNING_STATUSES:
            return str(item.get("account") or "")
    return None


def enqueue(item: dict, root: Path | str | None = None, *, cfg: dict | None = None) -> dict:
    """Append one validated item. Returns {ok, id, reason}.

    Refuses, in order: schema errors, a duplicate id, and a thread another
    account (or this one) already owns. The one-owner check is a HARD gate —
    two of our accounts under the same post is the coordination signal that
    chains suspensions across a fleet, and no other gate in the codebase sees it.
    """
    errors = validate_item(item)
    if errors:
        return {"ok": False, "id": item.get("id"), "reason": "invalid", "errors": errors}

    iid = str(item["id"])
    thread_key = str(item["thread_key"])
    account = str(item["account"])

    with _store_lock(root):
        state = fold_state(root)
        if iid in state["items"]:
            return {"ok": False, "id": iid, "reason": "duplicate"}

        owner = thread_owner(thread_key, root, _state=state)
        if owner is not None:
            return {
                "ok": False,
                "id": iid,
                "reason": "thread_owned",
                "owner": owner,
                "note": (
                    f"thread {thread_key} is already owned by {owner!r} "
                    "(one conversation, one owner — charter §2 amendment 6)"
                ),
            }

        if cfg is not None:
            item = dict(item)
            item["mode"] = resolve_mode(cfg, account)

        if not append_jsonl(_items_path(root), item):
            return {"ok": False, "id": iid, "reason": "write_failed"}

    return {"ok": True, "id": iid, "reason": None}


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------
def transition(
    item_id: str,
    to: str,
    *,
    actor: str,
    root: Path | str | None = None,
    note: str | None = None,
    receipt: dict | None = None,
    holder: str | None = None,
    lease_until: str | None = None,
    now: datetime | None = None,
    _state: dict | None = None,
) -> bool:
    """Move one item. Illegal transitions are refused and logged, never raised."""
    try:
        def _do(state: dict) -> bool:
            if item_id not in state["items"]:
                log.warning("reply_queue.transition: unknown item_id %r", item_id)
                return False
            current = state["status"].get(item_id, "queued")
            if to not in TRANSITIONS.get(current, frozenset()):
                log.warning(
                    "reply_queue.transition: illegal %r→%r for %r (allowed: %s)",
                    current, to, item_id, sorted(TRANSITIONS.get(current, frozenset())),
                )
                return False
            if to in _ATTEMPT_GATED_STATUSES:
                if state["attempts"].get(item_id, 0) >= MAX_SEND_ATTEMPTS:
                    log.warning(
                        "reply_queue.transition: %r hit the attempts cap (%d) — refusing %r",
                        item_id, MAX_SEND_ATTEMPTS, to,
                    )
                    return False
            row = {
                "id": item_id,
                "from": current,
                "to": to,
                "at": _iso(now or datetime.now(timezone.utc)),
                "actor": actor,
                "note": note,
                "receipt": receipt,
                "holder": holder,
                "lease_until": lease_until,
            }
            if not append_jsonl(_ledger_path(root), row):
                log.warning("reply_queue.transition: ledger append failed for %r", item_id)
                return False
            state["status"][item_id] = to
            state["last"][item_id] = row
            if to == "failed":
                state["attempts"][item_id] = state["attempts"].get(item_id, 0) + 1
            return True

        if _state is not None:
            return _do(_state)
        with _store_lock(root):
            return _do(fold_state(root))
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_queue.transition: unexpected error: %s", exc)
        return False


def approve(item_id: str, *, actor: str = "admin", root=None, note: str | None = None) -> bool:
    return transition(item_id, "approved", actor=actor, root=root, note=note)


def reject(item_id: str, *, actor: str = "admin", root=None, reason: str | None = None) -> bool:
    """Terminal kill WITH a reason. Rejections are the taste corpus."""
    return transition(item_id, "rejected", actor=actor, root=root,
                      note=(str(reason or "").strip() or "rejected by operator"))


# ---------------------------------------------------------------------------
# Expiry — a stale reply is dead, not a backlog
# ---------------------------------------------------------------------------
def expire_due(*, now: datetime | None = None, root: Path | str | None = None,
               actor: str = "reply_queue") -> list[str]:
    """Auto-kill every live item past its window. Returns the killed ids.

    Charter §5: "Expiry enforced (a stale reply is dead — auto-kill past
    window)." Called by the exporter before every export and by the admin
    surface before every read, so an expired draft is never presented for
    approval and never leaves for the desktop lane.
    """
    ts = now or datetime.now(timezone.utc)
    killed: list[str] = []
    with _store_lock(root):
        state = fold_state(root)
        for iid, item in state["items"].items():
            st = state["status"].get(iid, "queued")
            if st in TERMINAL_STATUSES:
                continue
            if st == "claimed":
                # In flight: a desktop session holds a live lease and may have
                # already posted. Killing it here would orphan a public reply.
                # release_expired_claims() returns it to `queued` first.
                continue
            deadline = _parse_iso(item.get("expires_at"))
            if deadline is None or ts < deadline:
                continue
            if transition(iid, "expired", actor=actor, root=root,
                          note=f"window closed at {item.get('expires_at')}",
                          now=ts, _state=state):
                killed.append(iid)
    return killed


# ---------------------------------------------------------------------------
# Lease / claim protocol (the M1 desktop lane)
# ---------------------------------------------------------------------------
def claim(item_id: str, *, holder: str, lease_s: int = DEFAULT_LEASE_S,
          root: Path | str | None = None, now: datetime | None = None) -> dict | None:
    """Claim one APPROVED item before navigating to the thread.

    Returns the claim row, or None when the item is not claimable.
    """
    ts = now or datetime.now(timezone.utc)
    lease_until = _iso(ts + timedelta(seconds=int(lease_s)))
    ok = transition(item_id, "claimed", actor=holder, root=root,
                    holder=holder, lease_until=lease_until, now=ts,
                    note=f"lease {lease_s}s")
    if not ok:
        return None
    return {"id": item_id, "holder": holder, "lease_until": lease_until}


def release_expired_claims(*, now: datetime | None = None, root: Path | str | None = None,
                           actor: str = "reply_queue",
                           skip_ids: "frozenset[str] | set[str] | None" = None) -> list[str]:
    """Return items whose lease expired to `queued`. Returns the released ids.

    Deliberately `queued`, not `approved`: an expired lease means we do not know
    whether the desktop session posted before it died. A human re-approves, so a
    lease timeout can never silently double-post.

    ``skip_ids`` holds items with an unconsumed receipt waiting. Releasing one of
    those strands it forever — `queued` has no edge to `sent`, so a receipt that
    was merely deferred (a cap refusal, say) could never be recorded afterwards,
    and the send would vanish from the very count the cap is sized against. The
    exporter passes the pending-receipt set.
    """
    ts = now or datetime.now(timezone.utc)
    skip = set(skip_ids or ())
    released: list[str] = []
    with _store_lock(root):
        state = fold_state(root)
        for iid, cl in list(state["claims"].items()):
            if state["status"].get(iid) != "claimed":
                continue
            if iid in skip:
                continue
            lease_until = _parse_iso(cl.get("lease_until"))
            # A claim with no parseable lease has no natural exit and would hold
            # the thread-owner lock forever. Treat it as already expired.
            if lease_until is not None and ts < lease_until:
                continue
            note = (f"lease expired at {cl.get('lease_until')} "
                    f"(held by {cl.get('holder')!r})") if lease_until is not None else \
                   f"claim carried no lease (held by {cl.get('holder')!r}) — reclaimed"
            if transition(iid, "queued", actor=actor, root=root, now=ts,
                          note=note, _state=state):
                released.append(iid)
    return released


# ---------------------------------------------------------------------------
# Send gate — the cap the sentinel counter now actually enforces
# ---------------------------------------------------------------------------
def may_send(account: str, *, cfg: dict | None, root: Path | str | None = None,
             as_of: str | None = None, now: datetime | None = None) -> dict:
    """May this account send one more reply today?

    Returns {ok, mode, cap, sent, reason}. M0 always returns ok=False with
    cap=0 — the standing 0-cap (D08) opens per the mode dial only, never by a
    builder config edit.

    ``as_of`` defaults to the SEND day, never the draft's creation day. Gating a
    send against the day a draft was written lets a queue that straddles
    midnight spend two days' allowance in one afternoon.
    """
    from engine.marketing import sentinel as _sentinel  # local: avoid import cycles

    ts = now or datetime.now(timezone.utc)
    day = as_of or ts.strftime("%Y-%m-%d")
    mode = resolve_mode(cfg, account)
    cap = _sentinel.reply_send_cap(cfg or {}, account, mode=mode)
    sent = sends_today(account, day, root)
    if cap <= 0:
        return {"ok": False, "mode": mode, "cap": cap, "sent": sent,
                "reason": "reply_cap_daily" if mode != "M0" else "mode_m0_draft_only"}
    if sent >= cap:
        return {"ok": False, "mode": mode, "cap": cap, "sent": sent, "reason": "reply_cap_daily"}
    return {"ok": True, "mode": mode, "cap": cap, "sent": sent, "reason": None}


def mark_sent(item_id: str, *, receipt: dict, actor: str = "desktop",
              root: Path | str | None = None, cfg: dict | None = None,
              now: datetime | None = None) -> dict:
    """Record a real send, cap-checked. Returns {ok, reason}.

    The cap is re-checked HERE and not only at export time: the desktop lane is
    a separate process on a separate clock, and a cap enforced only upstream is
    a cap that a slow queue can walk straight through.
    """
    ts = now or datetime.now(timezone.utc)
    state = fold_state(root)
    item = state["items"].get(item_id)
    if item is None:
        return {"ok": False, "reason": "unknown_item"}
    account = str(item.get("account") or "")
    # Gate on the SEND day, not the item's as_of — see may_send().
    gate = may_send(account, cfg=cfg, root=root, now=ts)
    if not gate["ok"]:
        return {"ok": False, "reason": gate["reason"], "cap": gate["cap"], "sent": gate["sent"]}
    ok = transition(item_id, "sent", actor=actor, root=root, receipt=receipt, now=ts)
    if not ok:
        return {"ok": False, "reason": "illegal_transition"}
    record_outcome(item_id, root=root, sent_at=_iso(ts))
    return {"ok": True, "reason": None, "cap": gate["cap"], "sent": gate["sent"] + 1}


# ---------------------------------------------------------------------------
# Telemetry seam (XG-W6 lands parent-adjusted labels on top of this)
# ---------------------------------------------------------------------------
_OUTCOME_FIELDS = frozenset({"sent_at", "author_replied", "likes", "follower_delta"})


def record_outcome(item_id: str, *, root: Path | str | None = None, **fields: Any) -> bool:
    """Append an outcome row for one item.

    Outcomes live in the ledger (append-only), NOT as a mutation of the item —
    the item file stays an immutable record of what we drafted. XG-W6 reads
    these rows to build parent-adjusted labels; this wave only fills the fields
    the discovery provider's mentions endpoint can observe.
    """
    unknown = set(fields) - _OUTCOME_FIELDS
    if unknown:
        log.warning("reply_queue.record_outcome: ignoring unknown fields %s", sorted(unknown))
    payload = {k: v for k, v in fields.items() if k in _OUTCOME_FIELDS}
    if not payload:
        return False
    row = {
        "id": item_id,
        "row": "outcome",
        "at": _iso(datetime.now(timezone.utc)),
        **payload,
    }
    return append_jsonl(_ledger_path(root), row)


def outcomes(root: Path | str | None = None) -> dict[str, dict]:
    """Latest observed outcome per item id."""
    out: dict[str, dict] = {}
    for row in read_ledger(root):
        if row.get("row") != "outcome":
            continue
        iid = str(row.get("id") or "")
        if not iid:
            continue
        merged = out.setdefault(iid, {})
        for k in _OUTCOME_FIELDS:
            if k in row and row[k] is not None:
                merged[k] = row[k]
    return out


def summary(root: Path | str | None = None) -> dict[str, Any]:
    """Counts by status and by account — what the admin surface renders."""
    state = fold_state(root)
    by_status: dict[str, int] = {}
    by_account: dict[str, dict[str, int]] = {}
    for iid, item in state["items"].items():
        st = state["status"].get(iid, "queued")
        by_status[st] = by_status.get(st, 0) + 1
        acc = str(item.get("account") or "unknown")
        by_account.setdefault(acc, {})
        by_account[acc][st] = by_account[acc].get(st, 0) + 1
    return {"by_status": by_status, "by_account": by_account, "total": len(state["items"])}


__all__ = [
    "SCHEMA_ID", "MODES", "SHIPPABLE_MODES", "DEFAULT_MODE", "TRANSITIONS",
    "OWNING_STATUSES", "TERMINAL_STATUSES", "TIERS", "MAX_SEND_ATTEMPTS",
    "DEFAULT_LEASE_S", "DEFAULT_TTL_MIN", "ttl_min_for", "lease_s_for",
    "state_dir", "store_dir", "resolve_mode", "status_id_from_url",
    "make_item", "validate_item", "enqueue", "read_items", "read_ledger",
    "fold_state", "sends_today", "thread_owner", "transition", "approve",
    "reject", "expire_due", "claim", "release_expired_claims", "may_send",
    "mark_sent", "record_outcome", "outcomes", "summary",
]
