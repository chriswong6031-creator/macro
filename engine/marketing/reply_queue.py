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

**Producer status.** XG-W4 shipped every piece and no connective tissue; XG-W6
built it. ``engine/marketing/reply_producer.py`` walks discovery -> score ->
draft -> critics -> ``enqueue`` on the wire daemon's host
(``marketing_fastlane_daemon.py --lane reply``), dark until
``reply_desk.producer.enabled``. It still sends nothing: output lands in the M0
queue and only ``reply_export`` at M1+ reaches the desktop lane.

The critic guarantee stays enforced HERE rather than in that producer, and that
is the whole point of where it lives: ``validate_item`` refuses any item without
a full passing critic stamp, so "everything that reaches the desktop cleared the
critics" is a property of the STORE — true of the producer, of an operator's
one-off script, and of whatever fills this store next.

Three laws this module enforces that live nowhere else:

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
  * **No item enters without a passing critic stamp** (``validate_critic_stamp``).
    The full roster must have run — a forged ``{"verdict": "pass"}`` and a
    partial pass are both refused.

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

    # Pacing (burst discipline; see the section comment above `CAP_NAMES`)
    CAP_NAMES / PACING_DEFAULTS / pacing_for(cfg, account) -> dict
    burst_plan(account, day, *, cfg=None) -> dict        # deterministic per seed
    active_burst(plan, now) / next_burst(plan, now) -> dict | None
    sent_times(account, root=None, *, since=None, until=None) -> list[datetime]
    pacing_gate(account, *, cfg, ...) -> dict            # weekly + burst
    target_gate(item, *, cfg, ...) -> dict               # author floor + convo cap
    record_pacing_hold(decision, *, account, item_id=None, ...) -> bool
    pacing_holds(root=None, *, day=None) -> list[dict]
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
    critics: dict | None = None,
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
        # The critic stamp. Not optional in practice — validate_item refuses an
        # item without a passing one, so an unstamped item cannot be enqueued.
        "critics": dict(critics) if critics else None,
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


def validate_critic_stamp(item: dict) -> list[str]:
    """Errors in an item's critic stamp; [] means it cleared the full pass.

    THE STRUCTURAL GUARANTEE. The runbook tells the operator that every draft
    they see has already cleared nine critics. That was a claim about the
    producer, and the producer is not built yet (XG-W6 wires
    discovery -> score -> draft -> critics -> enqueue), so it was a claim about
    nothing. Enforcing it at the STORE makes it true for anything that ever
    reaches the desktop lane, whoever built it and whenever that lands.

    Requires the full critic roster, not just a verdict: a hand-written
    ``{"verdict": "pass"}`` and a partial pass both fail here.
    """
    from engine.marketing import reply_critics as _rc  # noqa: PLC0415

    stamp = item.get("critics")
    if not isinstance(stamp, dict):
        return ["field 'critics' must be a critic stamp (reply_critics.stamp) — "
                "an item that never faced the critics may not enter the queue"]

    errors: list[str] = []
    if stamp.get("schema") != _rc.STAMP_SCHEMA:
        errors.append(f"critics.schema must be {_rc.STAMP_SCHEMA!r}; got {stamp.get('schema')!r}")
    if stamp.get("verdict") != "pass":
        errors.append(
            f"critics.verdict must be 'pass'; got {stamp.get('verdict')!r} "
            f"(rejected_by={stamp.get('rejected_by')})")
    ran = {str(c) for c in (stamp.get("critics_run") or [])}
    missing = set(_rc.CRITICS) - ran
    if missing:
        errors.append(f"critics did not all run; missing {sorted(missing)}")
    return errors


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
    errors.extend(validate_critic_stamp(item))
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


def sends_today(account: str, as_of: str, root: Path | str | None = None,
                *, _state: dict | None = None) -> int:
    """Count REAL sends for one account on one day.

    This is the number the sentinel's reply cap gates. It counts ledger rows
    (``to == "sent"``), not queue depth — the pre-XG-W4 counter was vacuous
    precisely because nothing ever produced a countable send.
    """
    state = _state if _state is not None else fold_state(root)
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


def enqueue(item: dict, root: Path | str | None = None, *, cfg: dict | None = None,
            now: datetime | None = None) -> dict:
    """Append one validated item. Returns {ok, id, reason}.

    Refuses, in order: schema errors, a duplicate id, a thread another account
    (or this one) already owns, and then the two per-target pacing floors. The
    one-owner check is a HARD gate — two of our accounts under the same post is
    the coordination signal that chains suspensions across a fleet, and no other
    gate in the codebase sees it.

    The per-target floors run LAST because they are the only refusals that are
    about us rather than about the item: a same-author floor hit means the draft
    was fine and the timing was not, and the operator reading `held_by` needs
    that distinguished from "this thread belongs to Cici".
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

        target = target_gate(item, cfg=cfg, root=root, now=now, _state=state)
        if not target["ok"]:
            record_pacing_hold(target, account=account, item_id=iid, root=root, now=now)
            return {
                "ok": False,
                "id": iid,
                "reason": target["held_by"],
                "held_by": target["held_by"],
                "note": target["note"],
                "checks": target["checks"],
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


def hold(item_id: str, *, actor: str = "admin", root: Path | str | None = None,
         note: str | None = None, now: datetime | None = None) -> bool:
    """Record that an operator looked at an item and chose not to send it yet.

    Not a status change — the item stays `queued` and remains approvable. It is
    a LEDGER row so the decision leaves a trace: "the operator held this" and
    "the operator never opened it" are different facts, and only one of them
    says anything about the draft.
    """
    row = {
        "id": item_id,
        "row": "decision",
        "decision": "hold",
        "at": _iso(now or datetime.now(timezone.utc)),
        "actor": actor,
        "note": note,
    }
    return append_jsonl(_ledger_path(root), row)


def decisions(root: Path | str | None = None) -> dict[str, list[dict]]:
    """Operator decision rows per item id, oldest first."""
    out: dict[str, list[dict]] = {}
    for row in read_ledger(root):
        if row.get("row") != "decision":
            continue
        iid = str(row.get("id") or "")
        if iid:
            out.setdefault(iid, []).append(row)
    return out


def rejections_path(root: Path | str | None = None) -> Path:
    """The reply desk's OWN taste corpus, in host state.

    Not ``data/marketing/rejections.jsonl``: the operator approving replies runs
    the admin on the M1, which is the nightly render host, so writing the corpus
    into the checkout dirties the render tree from an intraday human action —
    the exact collision the whole desk is kept out of the repo to avoid. The
    corpus survives; the checkout stays clean.
    """
    return store_dir(root) / "rejections.jsonl"


def record_rejection(item: dict, *, reason: str | None, actor: str = "admin",
                     root: Path | str | None = None,
                     now: datetime | None = None) -> bool:
    """Append one rejection row. Snapshots the draft, never a pointer."""
    row = {
        "schema": "marketing.reply_rejection/v1",
        "id": f"rej-{item.get('id')}",
        "item_id": item.get("id"),
        "as_of": item.get("as_of"),
        "account": item.get("account"),
        "kind": "reply",
        "tier": item.get("tier"),
        "family": item.get("family"),
        "target_url": item.get("target_url"),
        "parent_author": item.get("parent_author"),
        "parent_excerpt": item.get("parent_excerpt"),
        "text": item.get("draft"),
        "score": item.get("score"),
        "reason": (str(reason or "").strip() or None),
        "actor": actor,
        "rejected_at": _iso(now or datetime.now(timezone.utc)),
    }
    return append_jsonl(rejections_path(root), row)


def read_rejections(root: Path | str | None = None) -> list[dict]:
    """The taste corpus, oldest first."""
    return read_jsonl(rejections_path(root))


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

    An item past ``expires_at`` is refused even if the sweep has not reached it
    yet. Claiming one would be doubly wrong: it sends a stale reply, and because
    `claimed` is (correctly) not expirable, it would also make the item
    permanently unexpirable — a dead draft pinned live by the race between the
    sweep and the claim.
    """
    ts = now or datetime.now(timezone.utc)
    state = fold_state(root)
    item = state["items"].get(item_id)
    if item is None:
        log.warning("reply_queue.claim: unknown item_id %r", item_id)
        return None
    deadline = _parse_iso(item.get("expires_at"))
    if deadline is not None and ts >= deadline:
        log.warning("reply_queue.claim: %r expired at %s — refusing the claim",
                    item_id, item.get("expires_at"))
        return None

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
# Pacing — burst discipline, the weekly cap, and the two per-target floors
# ---------------------------------------------------------------------------
# THE OPERATOR'S RULE (2026-08-01): a real desk does not drip replies evenly
# across 24 hours. It works in 2-4 BURSTS a day of 15-25 minutes each, clustered
# on the session hours it actually cares about (pre-open, open, midday,
# post-close), with per-burst counts that vary, some bursts skipped outright,
# and irregular gaps. The daily cap alone cannot express any of that: a cap of
# 18 is satisfied just as well by one reply an hour around the clock, which is
# the single most legible bot signature there is and is precisely what the
# runbook's staggering section asks a human not to do. This section is that
# rule, made executable.
#
# WHY A SEEDED PLAN AND NOT LIVE RANDOMNESS. A desk needs to be able to answer
# "why did nothing export at 14:05?" hours after the fact, from a different
# process, on a different host. Live `random` makes that unanswerable — the
# schedule that held the item no longer exists anywhere. `burst_plan()` is a
# pure function of (seed, account, day): identical inputs give a byte-identical
# plan forever, every day is different from every other day, and every account
# is different from every other account on the same day.
#
# WHY LOCAL-CLOCK SESSIONS AND NOT UTC MINUTES. A window pinned to UTC drifts an
# hour twice a year against the market it is supposed to track — the pre-open
# burst quietly becomes an at-the-open burst every spring. Sessions are declared
# in a named zone's local clock and converted per day, so the plan follows the
# exchange, not the offset.
#
# WHY THE IN-CODE `enabled` DEFAULT IS FALSE AND THE SHIPPED CONFIG IS TRUE.
# An ad-hoc `{"reply_desk": {...}}` dict in a script or a test must never be
# silently burst-gated by a rule it does not know exists — that is how a caller
# ends up debugging a cap it cannot see. The protection against this shipping
# dark is NOT the in-code default: it is `config/marketing.yml` carrying
# `reply_desk.pacing.enabled: true` plus a test that fails if that key is
# removed or flipped (tests/test_marketing_reply_pacing.py).
#
# EXPLAINABILITY IS A REQUIREMENT, NOT A NICETY. Every gate here returns the
# NAME of the cap that held the item alongside the numbers it held it on, and
# writes a deduplicated row to `store/pacing_holds.jsonl` so the desk can say
# "kelly is outside her burst window; the next one opens at 16:22Z" instead of
# "nothing exported".

#: Every cap name this module can report, in evaluation order. The desk and the
#: admin surface quote these strings, so they are API: renaming one is a
#: breaking change, not a refactor.
CAP_NAMES: tuple[str, ...] = (
    "mode",                # the dial (M0 / silenced) — pre-existing authority
    "daily_cap",           # sentinel.reply_send_cap — pre-existing authority
    "weekly_cap",          # rolling 7 days, this module
    "burst_window",        # we are between bursts
    "burst_capacity",      # this burst's own item count is spent
    "same_author_floor",   # too soon after the last reply to this author
    "conversation_cap",    # too many entries into one conversation
)

#: In-code pacing defaults. Every one of these is overridable under
#: `reply_desk.pacing` (fleet-wide) and `reply_desk.pacing.accounts.<id>`
#: (per desk). The numbers are editorial pacing judgments, not measurements —
#: they encode "what a person with a day job would plausibly do", and nothing
#: here is claimed to be optimal.
PACING_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "seed": "reply-desk-v1",
    # 2-4 bursts a day (the operator's number).
    "bursts_per_day": {"min": 2, "max": 4},
    # 15-25 minutes each (the operator's number).
    "burst_minutes": {"min": 15, "max": 25},
    # Per-burst counts VARY. A fixed 4-per-burst is a metronome with extra steps.
    "items_per_burst": {"min": 2, "max": 5},
    # SOME BURSTS ARE SKIPPED. A desk that never misses a session is a cron job.
    # A day where the dice skip every planned burst is legitimate and means the
    # account is quiet that day — do not "fix" that into a floor.
    "skip_probability": 0.18,
    # Rolling 7-day per-account ceiling. Binds well below 7 x daily on purpose:
    # the daily cap is a spike limiter, this is the sustained-rate limiter, and
    # an account that runs its daily cap every day for a week is not pacing.
    "per_account_weekly": 70,
    # Hard floor between two of OUR replies aimed at the SAME author.
    "min_minutes_between_same_author": 360,
    # How many times one account may enter one conversation, ever. See
    # `_conversation_entries` for why this is not already covered by the
    # one-owner lock.
    "max_per_conversation": 2,
    "tz": "America/New_York",
    # FOUR windows for a 2-4 burst range. One burst per session, so three
    # windows would make `bursts_per_day.max: 4` unreachable and the operator's
    # stated range quietly a 2-3.
    "sessions": {
        "pre_open": {"start": "08:05", "end": "09:25"},
        "open": {"start": "09:40", "end": "10:45"},
        "midday": {"start": "11:40", "end": "13:20"},
        "post_close": {"start": "16:10", "end": "17:40"},
    },
    "accounts": {},
}

#: Sub-dicts that are FILLED from the default rather than replaced wholesale, so
#: a config supplying `{"bursts_per_day": {"max": 3}}` keeps the default min.
#: `sessions` is deliberately NOT in this set: a desk that declares its own
#: sessions (Cici on Asia hours) means "these, instead of yours", and merging
#: would leave her awake during the New York close.
_PACING_FILL_KEYS: frozenset[str] = frozenset({
    "bursts_per_day", "burst_minutes", "items_per_burst",
})


def _pacing_holds_path(root: Path | str | None) -> Path:
    return store_dir(root) / "pacing_holds.jsonl"


def pacing_for(cfg: dict | None, account: str) -> dict:
    """Effective pacing settings for one desk: defaults <- fleet <- account."""
    merged: dict[str, Any] = {k: (dict(v) if isinstance(v, dict) else v)
                              for k, v in PACING_DEFAULTS.items()}
    rd = ((cfg or {}).get("reply_desk") or {})
    fleet = rd.get("pacing") or {}
    per_account = (fleet.get("accounts") or {}).get(account) or {}
    for layer in (fleet, per_account):
        if not isinstance(layer, dict):
            continue
        for key, value in layer.items():
            if key == "accounts":
                continue
            if key in _PACING_FILL_KEYS and isinstance(value, dict):
                base = dict(PACING_DEFAULTS[key])
                base.update({k: v for k, v in value.items() if v is not None})
                merged[key] = base
            elif value is not None:
                merged[key] = dict(value) if isinstance(value, dict) else value
    return merged


def _minutes_of_day(value: object, fallback: int) -> int:
    """Parse "HH:MM" into minutes since local midnight."""
    try:
        hh, _, mm = str(value).strip().partition(":")
        total = int(hh) * 60 + int(mm or 0)
    except (TypeError, ValueError):
        return fallback
    return total if 0 <= total < 24 * 60 else fallback


def _zone(name: object):
    """Resolve a tz name, falling back to UTC loudly rather than silently."""
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415

        return ZoneInfo(str(name))
    except Exception:  # noqa: BLE001
        print(
            f"::warning title=reply-pacing-tz::unknown reply_desk.pacing timezone "
            f"{name!r} — falling back to UTC, so session windows will not track "
            "the exchange clock",
            flush=True,
        )
        return timezone.utc


def _plan_rng(seed: object, account: str, day: str):
    """Deterministic RNG for one (seed, account, day).

    sha256 rather than `hash()`: PYTHONHASHSEED randomises str hashing per
    process, which would make the "same inputs, same plan" guarantee true only
    within a single run — the exact opposite of what an auditable plan needs.
    """
    import random  # noqa: PLC0415

    digest = hashlib.sha256(f"{seed}|{account}|{day}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def burst_plan(account: str, day: str, *, cfg: dict | None = None) -> dict:
    """The burst schedule for one account on one calendar day.

    Pure and deterministic: same (seed, account, day) -> same plan, forever.

    A burst carries its own ``items`` allowance because per-burst counts vary,
    and its own ``skipped`` flag because some bursts do not happen. The plan is
    a SHAPE, not a promise: the daily and weekly caps are enforced separately
    and independently, and the effective allowance is always the smaller of the
    two. That separation is why a plan can be printed and reasoned about without
    knowing anything about how many sends already happened.
    """
    p = pacing_for(cfg, account)
    tz = _zone(p.get("tz"))
    rng = _plan_rng(p.get("seed"), account, day)

    raw_sessions = p.get("sessions") or {}
    sessions: list[tuple[str, int, int]] = []
    for name, window in raw_sessions.items():
        if not isinstance(window, dict):
            continue
        start = _minutes_of_day(window.get("start"), 0)
        end = _minutes_of_day(window.get("end"), start + 60)
        if end > start:
            sessions.append((str(name), start, end))
    sessions.sort(key=lambda s: (s[1], s[0]))

    try:
        base_day = datetime.strptime(str(day)[:10], "%Y-%m-%d")
    except ValueError:
        base_day = datetime.now(timezone.utc)
    midnight = base_day.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz)

    bursts: list[dict] = []
    requested = 0
    if sessions:
        span = p.get("bursts_per_day") or {}
        lo = max(1, int(span.get("min", 2)))
        hi = max(lo, int(span.get("max", 4)))
        requested = rng.randint(lo, hi)
        # One burst per session, so a `max` above the number of declared sessions
        # is silently unreachable. That is a real configuration trap — asking for
        # "2-4 bursts" against a three-window map yields at most three, forever,
        # with nothing to see. The clamp is reported in the plan (see
        # `bursts_requested` / `session_count` below) rather than warned about,
        # because this is a pure function called on every tick and a print here
        # would be a log flood, not a signal.
        n = min(requested, len(sessions))
        chosen = sorted(rng.sample(sessions, n), key=lambda s: s[1])

        dur_cfg = p.get("burst_minutes") or {}
        dur_lo = max(1, int(dur_cfg.get("min", 15)))
        dur_hi = max(dur_lo, int(dur_cfg.get("max", 25)))
        items_cfg = p.get("items_per_burst") or {}
        it_lo = max(0, int(items_cfg.get("min", 2)))
        it_hi = max(it_lo, int(items_cfg.get("max", 5)))
        try:
            skip_p = float(p.get("skip_probability", 0.0))
        except (TypeError, ValueError):
            skip_p = 0.0

        for name, w_start, w_end in chosen:
            minutes = rng.randint(dur_lo, dur_hi)
            room = (w_end - w_start) - minutes
            # A burst longer than its own session window is clamped to the
            # window rather than allowed to spill past the close.
            offset = rng.randint(0, room) if room > 0 else 0
            if room < 0:
                minutes = w_end - w_start
            items = rng.randint(it_lo, it_hi)
            skipped = rng.random() < skip_p
            start_dt = (midnight + timedelta(minutes=w_start + offset)).astimezone(timezone.utc)
            end_dt = start_dt + timedelta(minutes=minutes)
            bursts.append({
                "session": name,
                "start": _iso(start_dt),
                "end": _iso(end_dt),
                "minutes": minutes,
                "items": 0 if skipped else items,
                "skipped": skipped,
            })

    active = [b for b in bursts if not b["skipped"]]
    return {
        "account": account,
        "day": str(day)[:10],
        "tz": str(p.get("tz")),
        "seed": str(p.get("seed")),
        "bursts": bursts,
        "planned_bursts": len(bursts),
        "active_bursts": len(active),
        "planned_items": sum(int(b["items"]) for b in active),
        # Explainability for the clamp above: `bursts_requested > session_count`
        # means the configured `bursts_per_day.max` cannot be reached with this
        # session map, no matter what the dice say.
        "bursts_requested": requested,
        "session_count": len(sessions),
    }


def active_burst(plan: dict, now: datetime) -> dict | None:
    """The burst containing ``now``, or None when we are between bursts."""
    ts = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    for burst in (plan or {}).get("bursts") or []:
        if burst.get("skipped"):
            continue
        start = _parse_iso(burst.get("start"))
        end = _parse_iso(burst.get("end"))
        if start is None or end is None:
            continue
        if start <= ts < end:
            return burst
    return None


def next_burst(plan: dict, now: datetime) -> dict | None:
    """The next burst that opens after ``now`` today, or None."""
    ts = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    upcoming = []
    for burst in (plan or {}).get("bursts") or []:
        if burst.get("skipped"):
            continue
        start = _parse_iso(burst.get("start"))
        if start is not None and start > ts:
            upcoming.append((start, burst))
    if not upcoming:
        return None
    return min(upcoming, key=lambda pair: pair[0])[1]


def sent_times(account: str, root: Path | str | None = None, *,
               _state: dict | None = None,
               since: datetime | None = None,
               until: datetime | None = None) -> list[datetime]:
    """When this account's replies actually went out, oldest first.

    Reads the LEDGER, not the items file: `sends_today` counts, this one needs
    the individual timestamps because a burst is a window, not a day.
    """
    state = _state if _state is not None else fold_state(root)
    out: list[datetime] = []
    for row in read_ledger(root):
        if str(row.get("to") or "") != "sent":
            continue
        item = state["items"].get(str(row.get("id") or "")) or {}
        if str(item.get("account") or "") != account:
            continue
        ts = _parse_iso(row.get("at"))
        if ts is None:
            continue
        if since is not None and ts < since:
            continue
        if until is not None and ts >= until:
            continue
        out.append(ts)
    out.sort()
    return out


def _live_items_for(account: str, state: dict) -> list[dict]:
    """This account's items that still HOLD ground — queued through sent.

    Rejected and expired items are excluded on purpose: nobody ever saw them,
    so they must not lock an author out for six hours.
    """
    out = []
    for iid, item in state["items"].items():
        if str(item.get("account") or "") != account:
            continue
        if state["status"].get(iid) in OWNING_STATUSES:
            out.append(item)
    return out


def _conversation_entries(account: str, thread_key: str, state: dict) -> int:
    """How many times this account has ENTERED one conversation, ever.

    Deliberately counts every status, including `rejected` and `expired`, and
    that is the whole reason this cap is not redundant with the one-owner lock.
    `thread_owner` only sees LIVE items, so a thread whose draft expired
    unnoticed is unlocked again — and again, and again. Nothing else in the
    store bounds "we tried to get into this conversation nine times today".
    """
    n = 0
    for iid, item in state["items"].items():
        if str(item.get("account") or "") != account:
            continue
        if str(item.get("thread_key") or "") == str(thread_key):
            n += 1
    return n


def _check(name: str, ok: bool, **detail: Any) -> dict:
    return {"cap": name, "ok": bool(ok), "detail": detail}


def pacing_gate(account: str, *, cfg: dict | None, root: Path | str | None = None,
                now: datetime | None = None, _state: dict | None = None) -> dict:
    """Account-scoped pacing: the weekly cap and the burst schedule.

    Returns {ok, held_by, reason, note, allowance, checks, plan}. EVERY check is
    evaluated even after one fails, because the desk asking "why is nothing
    moving" wants the whole picture, not the first excuse. ``held_by`` names the
    first cap that bound, in ``CAP_NAMES`` order.

    ``allowance`` is how many more sends pacing permits right now. `may_send`
    folds it into the effective cap it returns, which is what makes burst
    discipline bind in the export path without that path knowing this exists.
    """
    ts = now or datetime.now(timezone.utc)
    p = pacing_for(cfg, account)
    if not p.get("enabled"):
        return {
            "ok": True, "held_by": None, "reason": None,
            "note": "pacing disabled (reply_desk.pacing.enabled)",
            "allowance": None, "checks": [], "plan": None,
        }

    state = _state if _state is not None else fold_state(root)
    day = ts.strftime("%Y-%m-%d")
    plan = burst_plan(account, day, cfg=cfg)
    checks: list[dict] = []

    # ── weekly cap: rolling 7 days, not a calendar week. A calendar week resets
    # on a boundary the account cannot feel, so a Sunday-Monday double-spend
    # passes a calendar-week cap while looking exactly like a burnout.
    week_start = ts - timedelta(days=7)
    week_sent = len(sent_times(account, root, _state=state, since=week_start, until=ts))
    try:
        weekly = int(p.get("per_account_weekly") or 0)
    except (TypeError, ValueError):
        weekly = 0
    weekly_room = max(0, weekly - week_sent) if weekly > 0 else None
    checks.append(_check("weekly_cap", weekly <= 0 or week_sent < weekly,
                         sent_7d=week_sent, cap=weekly,
                         since=_iso(week_start)))

    # ── burst window
    burst = active_burst(plan, ts)
    nxt = next_burst(plan, ts)
    checks.append(_check("burst_window", burst is not None,
                         session=(burst or {}).get("session"),
                         opens_at=(nxt or {}).get("start"),
                         planned_bursts=plan["planned_bursts"],
                         active_bursts=plan["active_bursts"]))

    # ── burst capacity
    burst_room: int | None = None
    if burst is not None:
        b_start = _parse_iso(burst["start"]) or ts
        in_burst = len(sent_times(account, root, _state=state, since=b_start, until=ts))
        burst_room = max(0, int(burst["items"]) - in_burst)
        checks.append(_check("burst_capacity", burst_room > 0,
                             session=burst.get("session"), sent_in_burst=in_burst,
                             burst_items=int(burst["items"])))
    else:
        checks.append(_check("burst_capacity", False, session=None,
                             note="no active burst"))

    held = next((c for c in checks if not c["ok"]), None)
    held_by = held["cap"] if held else None
    reason = {
        "weekly_cap": "reply_cap_weekly",
        "burst_window": "outside_burst",
        "burst_capacity": "burst_full",
    }.get(held_by or "", None)

    if held_by == "weekly_cap":
        note = (f"{account} has sent {week_sent} replies in the last 7 days "
                f"against a weekly cap of {weekly}")
    elif held_by == "burst_window":
        when = (nxt or {}).get("start")
        note = (f"{account} is between bursts; "
                + (f"the next one opens at {when}" if when
                   else f"no burst remains today ({plan['active_bursts']} planned)"))
    elif held_by == "burst_capacity":
        note = (f"{account}'s {burst.get('session')} burst is spent "  # type: ignore[union-attr]
                f"({burst['items']} items)")  # type: ignore[index]
    else:
        note = (f"{account} is inside the {burst.get('session')} burst"  # type: ignore[union-attr]
                if burst else f"{account} is clear")

    rooms = [r for r in (weekly_room, burst_room) if r is not None]
    allowance = min(rooms) if rooms else 0
    return {
        "ok": held_by is None, "held_by": held_by, "reason": reason, "note": note,
        "allowance": 0 if held_by else allowance,
        "checks": checks, "plan": plan,
    }


def target_gate(item: dict, *, cfg: dict | None, root: Path | str | None = None,
                now: datetime | None = None, _state: dict | None = None) -> dict:
    """Per-TARGET pacing: the same-author floor and the conversation cap.

    Enforced at ENQUEUE, which is the last moment before a draft exists at all.
    Deliberately NOT enforced at `mark_sent`: a reply whose receipt has arrived
    is already public, and refusing to record it would trade a pacing violation
    we cannot undo for a bookkeeping hole we also cannot undo — the receipt gets
    retired as `.unresolved` and the send is lost from the ledger forever. Rules
    about what we START belong upstream of starting.
    """
    ts = now or datetime.now(timezone.utc)
    account = str(item.get("account") or "")
    p = pacing_for(cfg, account)
    if not p.get("enabled"):
        return {"ok": True, "held_by": None, "reason": None,
                "note": "pacing disabled (reply_desk.pacing.enabled)", "checks": []}

    state = _state if _state is not None else fold_state(root)
    checks: list[dict] = []

    # ── same-author floor
    try:
        floor_min = int(p.get("min_minutes_between_same_author") or 0)
    except (TypeError, ValueError):
        floor_min = 0
    author = str(item.get("parent_author") or "").strip().lstrip("@").lower()
    last_at: datetime | None = None
    if floor_min > 0 and author:
        for prior in _live_items_for(account, state):
            if str(prior.get("parent_author") or "").strip().lstrip("@").lower() != author:
                continue
            when = _parse_iso(prior.get("created_at"))
            if when is not None and (last_at is None or when > last_at):
                last_at = when
    gap_min = None if last_at is None else (ts - last_at).total_seconds() / 60.0
    checks.append(_check(
        "same_author_floor",
        floor_min <= 0 or gap_min is None or gap_min >= floor_min,
        author=author or None, floor_minutes=floor_min,
        minutes_since_last=None if gap_min is None else round(gap_min, 1),
        last_at=None if last_at is None else _iso(last_at),
    ))

    # ── conversation cap
    try:
        conv_cap = int(p.get("max_per_conversation") or 0)
    except (TypeError, ValueError):
        conv_cap = 0
    thread_key = str(item.get("thread_key") or "")
    entries = _conversation_entries(account, thread_key, state) if thread_key else 0
    checks.append(_check("conversation_cap", conv_cap <= 0 or entries < conv_cap,
                         thread_key=thread_key or None, entries=entries, cap=conv_cap))

    held = next((c for c in checks if not c["ok"]), None)
    held_by = held["cap"] if held else None
    if held_by == "same_author_floor":
        note = (f"{account} last aimed at @{author} {gap_min:.0f} min ago; the "
                f"floor is {floor_min} min")
    elif held_by == "conversation_cap":
        note = (f"{account} has already entered conversation {thread_key} "
                f"{entries} time(s); the cap is {conv_cap}")
    else:
        note = f"{account} is clear on this target"
    return {"ok": held_by is None, "held_by": held_by, "reason": held_by,
            "note": note, "checks": checks}


def record_pacing_hold(decision: dict, *, account: str, item_id: str | None = None,
                       root: Path | str | None = None,
                       now: datetime | None = None) -> bool:
    """Write down WHICH cap held something, so the desk can say why.

    Deduplicated on (item_id or account, day, held_by): the fastlane daemon ticks
    every ~75 seconds, and an undeduplicated hold row would write a thousand
    identical lines a day and bury the one transition an operator cares about.
    """
    held_by = (decision or {}).get("held_by")
    if not held_by:
        return False
    ts = now or datetime.now(timezone.utc)
    key = str(item_id or account)
    day = ts.strftime("%Y-%m-%d")
    try:
        latest = None
        for prior in read_jsonl(_pacing_holds_path(root)):
            if str(prior.get("key") or "") == key and str(prior.get("day") or "") == day:
                latest = prior
        if latest is not None and str(latest.get("held_by") or "") == str(held_by):
            return False
    except Exception as exc:  # noqa: BLE001
        # Fail OPEN on a read error: a hold we cannot dedupe is still a hold the
        # desk needs to see. A duplicate row is noise; a missing row is a desk
        # that cannot answer "why".
        log.warning("reply_queue.record_pacing_hold: cannot read prior holds: %s", exc)
    return _append_hold(root, key, day, account, item_id, decision, ts)


def _append_hold(root, key: str, day: str, account: str, item_id: str | None,
                 decision: dict, ts: datetime) -> bool:
    return append_jsonl(_pacing_holds_path(root), {
        "row": "pacing_hold",
        "key": key,
        "day": day,
        "at": _iso(ts),
        "account": account,
        "id": item_id,
        "held_by": decision.get("held_by"),
        "reason": decision.get("reason"),
        "note": decision.get("note"),
        "checks": decision.get("checks"),
    })


def pacing_holds(root: Path | str | None = None, *, day: str | None = None) -> list[dict]:
    """Recorded pacing holds, oldest first — the desk's "why" feed."""
    rows = read_jsonl(_pacing_holds_path(root))
    if day is None:
        return rows
    return [r for r in rows if str(r.get("day") or "") == str(day)[:10]]


# ---------------------------------------------------------------------------
# Send gate — the cap the sentinel counter now actually enforces
# ---------------------------------------------------------------------------
def may_send(account: str, *, cfg: dict | None, root: Path | str | None = None,
             as_of: str | None = None, now: datetime | None = None,
             _state: dict | None = None, enforce_pacing: bool = True) -> dict:
    """May this account send one more reply today?

    Returns {ok, mode, cap, cap_daily, sent, reason, held_by, pacing}. M0 always
    returns ok=False with cap=0 — the standing 0-cap (D08) opens per the mode
    dial only, never by a builder config edit.

    ``as_of`` defaults to the SEND day, never the draft's creation day. Gating a
    send against the day a draft was written lets a queue that straddles
    midnight spend two days' allowance in one afternoon.

    ``cap`` is the EFFECTIVE cap right now — the daily cap narrowed by whatever
    pacing currently permits (weekly room, this burst's remaining items). That
    is deliberate and load-bearing: the export lane sizes its headroom as
    ``cap - sent - in_flight``, so burst discipline binds there without the
    export lane needing to know pacing exists. ``cap_daily`` keeps the raw
    number for anything that wants to report the dial rather than the moment.

    ``enforce_pacing=False`` drops back to the pre-pacing behaviour and exists
    for exactly one caller: `mark_sent`. See the comment there.
    """
    from engine.marketing import sentinel as _sentinel  # local: avoid import cycles

    ts = now or datetime.now(timezone.utc)
    day = as_of or ts.strftime("%Y-%m-%d")
    mode = resolve_mode(cfg, account)
    cap = _sentinel.reply_send_cap(cfg or {}, account, mode=mode)
    sent = sends_today(account, day, root, _state=_state)
    if cap <= 0:
        # A silenced account is NOT a spent cap. They read the same to a caller
        # that only checks ok=False, but they need opposite handling: a spent cap
        # clears at midnight so a receipt is worth retaining, while a silenced
        # account never clears on its own, so retaining the receipt means warning
        # about it on every sweep forever with nothing an operator can do.
        reason = "mode_m0_draft_only" if mode == "M0" else "account_silenced"
        return {"ok": False, "mode": mode, "cap": cap, "cap_daily": cap, "sent": sent,
                "reason": reason, "held_by": "mode", "pacing": None}
    if sent >= cap:
        return {"ok": False, "mode": mode, "cap": cap, "cap_daily": cap, "sent": sent,
                "reason": "reply_cap_daily", "held_by": "daily_cap", "pacing": None}

    if not enforce_pacing:
        return {"ok": True, "mode": mode, "cap": cap, "cap_daily": cap, "sent": sent,
                "reason": None, "held_by": None, "pacing": None}

    pace = pacing_gate(account, cfg=cfg, root=root, now=ts, _state=_state)
    if pace["plan"] is None:  # pacing disabled — unchanged behaviour
        return {"ok": True, "mode": mode, "cap": cap, "cap_daily": cap, "sent": sent,
                "reason": None, "held_by": None, "pacing": pace}
    effective = min(cap, sent + int(pace["allowance"] or 0))
    if not pace["ok"]:
        record_pacing_hold(pace, account=account, root=root, now=ts)
        return {"ok": False, "mode": mode, "cap": effective, "cap_daily": cap,
                "sent": sent, "reason": pace["reason"], "held_by": pace["held_by"],
                "pacing": pace}
    return {"ok": True, "mode": mode, "cap": effective, "cap_daily": cap, "sent": sent,
            "reason": None, "held_by": None, "pacing": pace}


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
    #
    # PACING IS DELIBERATELY NOT ENFORCED HERE. By the time a receipt reaches
    # this function the reply is already PUBLIC; the only question left is
    # whether we write it down. Refusing on a burst window would turn a pacing
    # miss into a permanent bookkeeping hole — `reply_export.ingest_receipts`
    # retires an unrecognised refusal reason to `.unresolved` and the send is
    # gone from the ledger, which also means the daily and weekly counters
    # under-read forever after. Pacing governs what we START (export, enqueue);
    # it never governs what we RECORD.
    gate = may_send(account, cfg=cfg, root=root, now=ts, enforce_pacing=False)
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
    "make_item", "validate_item", "validate_critic_stamp", "enqueue",
    "read_items", "read_ledger", "fold_state", "sends_today", "thread_owner",
    "transition", "approve", "hold", "decisions", "reject", "expire_due",
    "claim", "release_expired_claims", "may_send", "mark_sent",
    "record_outcome", "outcomes", "summary",
    "rejections_path", "record_rejection", "read_rejections",
    # Pacing
    "CAP_NAMES", "PACING_DEFAULTS", "pacing_for", "burst_plan", "active_burst",
    "next_burst", "sent_times", "pacing_gate", "target_gate",
    "record_pacing_hold", "pacing_holds",
]
