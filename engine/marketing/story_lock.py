"""engine.marketing.story_lock — one conversation, one owner (XG-W2).

THE LAW (charter §2 amendment 6): *one conversation, one owner is a hard lock,
not an editorial preference.* Two of our accounts posting the same story is the
coordination signal no existing gate catches — the near-dup radar only sees it
when the WORDING also collides, and two desks writing the same event in two
genuine voices is precisely the case where the wording does not collide. That is
a network-linkage tell, and the fleet-linkage research is why it is a lock.

MECHANISM. At emission time an item records the STORY KEY it drew from. A second
account drawing the same key inside the lock window is refused. The key is taken
in this order:

  1. an explicit cluster/dedupe key the producer already computed
     (``press_lane._corroboration_key`` — the mirror-collapsed Truth status id,
     or ``claim:{event_class}:{entity}``). Reusing it means the lock inherits the
     press lane's own understanding of "the same claim", including the M3 fix
     that made two differently-worded relays of one claim collapse;
  2. an explicit event/source id;
  3. a normalized-headline hash — the honest fallback, and deliberately last:
     it only catches near-verbatim headlines.

STATE. The lock reads the outbox items the publisher ALREADY maintains
(``items.jsonl``), matching on ``source.story_key``. There is no new store, no
new file, and no intraday repo write beyond the outbox append the emission was
always going to make. That matters: the fastlane daemon runs on the VPS and the
house law is that pollers make zero repo writes of their own.

SCOPE. The lock is CROSS-ACCOUNT only. The same account re-drawing its own story
is a repeat, and repeats are the near-dup guard's job — refusing them here would
double-punish an account for updating its own coverage.

Public API:
    story_key(...)                     -> str
    owner_of(key, items, ...)          -> str | None
    check(account, key, items, ...)    -> LockVerdict
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, Iterable

log = logging.getLogger(__name__)

#: Default lock window. A story is one account's for this long; after it, a
#: second desk may legitimately pick up a developing story with a new angle.
#: Charter §8 law — a cadence/threshold constant is a HYPOTHESIS, so this is
#: overridable from ``config/marketing.yml`` (``story_lock.window_minutes``).
DEFAULT_WINDOW_MINUTES = 720  # 12h


def lock_config(cfg: dict | None) -> dict[str, Any]:
    """Resolve the ``story_lock:`` config block. Fail-soft to the defaults."""
    block = {}
    if isinstance(cfg, dict):
        raw = cfg.get("story_lock")
        if isinstance(raw, dict):
            block = raw
    enabled = block.get("enabled", True)
    if not isinstance(enabled, bool):
        enabled = str(enabled).strip().lower() in {"1", "true", "yes"}
    try:
        window = int(block.get("window_minutes", DEFAULT_WINDOW_MINUTES))
    except (TypeError, ValueError):
        window = DEFAULT_WINDOW_MINUTES
    return {"enabled": enabled, "window_minutes": max(0, window)}


def _normalize_headline(headline: Any) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", str(headline or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def story_key(
    *,
    cluster_key: Any = None,
    event_id: Any = None,
    headline: Any = None,
) -> str:
    """The lock identity for one story. Empty string when nothing identifies it.

    An empty key NEVER locks — a story we cannot identify must not be able to
    silence an unrelated one. Callers treat "" as "no lock available".
    """
    ck = str(cluster_key or "").strip()
    if ck:
        return f"c:{ck}"
    eid = str(event_id or "").strip()
    if eid:
        return f"e:{eid}"
    norm = _normalize_headline(headline)
    if not norm:
        return ""
    return "h:" + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def item_story_key(item: dict) -> str:
    """The story key recorded on an outbox item, or ""."""
    source = item.get("source")
    if isinstance(source, dict):
        return str(source.get("story_key") or "")
    return ""


def owner_of(
    key: str,
    items: Iterable[dict],
    *,
    now: datetime,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
) -> str | None:
    """The account that already owns ``key`` inside the window, or None.

    Reads ``created_at`` (emission time) and falls back to ``as_of`` — an item
    whose timestamps are both unreadable is treated as IN WINDOW, so a malformed
    row tightens the lock rather than disarming it.
    """
    if not key:
        return None
    horizon = now - timedelta(minutes=max(0, window_minutes))
    for item in items or ():
        if not isinstance(item, dict):
            continue
        if item_story_key(item) != key:
            continue
        ts = _parse_ts(item.get("created_at")) or _parse_ts(item.get("as_of"))
        if ts is not None and ts < horizon:
            continue
        account = str(item.get("account") or "")
        if account:
            return account
    return None


@dataclass(frozen=True)
class LockVerdict:
    """``allowed`` plus the account that holds the lock when refused."""

    allowed: bool
    key: str
    owner: str | None = None
    reason: str = "ok"

    def __bool__(self) -> bool:
        return self.allowed


def check(
    account: str,
    key: str,
    items: Iterable[dict],
    *,
    now: datetime,
    cfg: dict | None = None,
) -> LockVerdict:
    """May ``account`` emit the story identified by ``key``?

    Refuses only when a DIFFERENT account already emitted it inside the window.
    Never raises.
    """
    knobs = lock_config(cfg)
    if not key:
        return LockVerdict(True, key, None, "no_key")
    if not knobs["enabled"]:
        return LockVerdict(True, key, None, "disabled")
    try:
        holder = owner_of(key, items, now=now, window_minutes=knobs["window_minutes"])
    except Exception as exc:  # noqa: BLE001
        log.warning("story_lock: owner lookup failed (%s) — allowing", exc)
        return LockVerdict(True, key, None, "lookup_failed")
    if holder and holder != str(account):
        return LockVerdict(False, key, holder, "owned_by_other_account")
    return LockVerdict(True, key, holder, "ok")
