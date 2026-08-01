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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from engine.marketing.ledgers import append_jsonl, read_jsonl

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_ID = "marketing.outbox/v1"

# The nine nightly content-plan kinds, plus the three FAST-LANE kinds admitted
# by XG-W2. The fast lanes (press_lane, fastlane) were writing raw per-item JSON
# files straight to data/marketing/outbox/<id>.json — a shape nothing read, that
# bypassed make_item/validate_item, and that therefore inherited NONE of the
# id-dedup, text-dedup or near-dup guarantees this module exists to provide.
# Admitting their kinds is what lets those writers use the canonical path:
#   wire      — a wire-lane emission routed by wire_routing (press_lane)
#   breaking  — a corroborated press/breaking post (press_lane)
#   earnings  — an earnings fast-lane post (fastlane)
#   congress  — a congressional-disclosure post (content_studio, XG-E2)
#   insider   — a Form-4 open-market-purchase post (content_studio, XG-E2)
# Both are PLANNED kinds (see `planned_kinds`): they are written by the W1 v2
# writer from a fact-locked packet, so the no-fallback law covers them and
# template prose can never reach a timeline under a politician's name.
KINDS: frozenset[str] = frozenset({
    "signal", "chart", "education", "macro", "receipt",
    "watchlist", "event", "mover", "theme_list",
    "wire", "breaking", "earnings",
    "congress", "insider",
})

# Status machine — only these transitions are legal.
#
# "posting" is the in-flight state the W1 live publisher
# (scripts/marketing_publisher.py) sets AFTER an item is approved but BEFORE
# the network call, so a crash mid-post leaves a durable "posting" marker that
# is REPORTED and never auto-reposted (no-double-post guarantee). approved may
# still go straight to posted/failed so the W0 dry-run actuator and its tests
# keep working — the extra target is purely additive.
#
# "posted" IS OVERLOADED, and naming that is the whole reason `recalled` exists.
# It means "the backend accepted this post", NOT "this post is live on X". Since
# publish.max_forward_book_min (#3913) a single sweep books items as Buffer
# customScheduled sends up to an hour out, so a `posted` item may be nothing more
# than a reservation in Buffer's queue. On 2026-07-28 five such reservations
# survived the operator's kill switch by 41 minutes.
#
# "recalled" is where such a booking goes once it has been CANCELLED at the
# backend before it ever sent (scripts/marketing_recall.py). Design constraints,
# each load-bearing:
#   * posted → recalled is the ONLY new edge. `posted` stays otherwise terminal:
#     a sent post can never walk back to approved/queued and re-send.
#   * recalled is TERMINAL. Recall is not a re-queue — the operator recalls
#     because the copy was wrong, and the fix is new copy under a new id, not a
#     second attempt at the same text. Nothing may re-arm a recalled item.
#   * NOTHING may transition to recalled without a CONFIRMED backend delete. The
#     runner's rule is: booked send time still in the future AND
#     DeleteResult.ok. A post that already went out stays `posted` forever, so
#     posted_today_by_account keeps counting it and the no-double-post
#     guarantee is untouched.
TRANSITIONS: dict[str, frozenset[str]] = {
    "queued":      frozenset({"approved", "quarantined"}),
    "approved":    frozenset({"posting", "posted", "failed", "quarantined"}),
    "posting":     frozenset({"posted", "failed", "quarantined"}),
    "failed":      frozenset({"approved", "quarantined"}),
    "posted":      frozenset({"recalled"}),   # cancelled-before-send ONLY
    "recalled":    frozenset(),   # terminal
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


def _host_items_path(root: Path | str | None) -> Path:
    """The GITIGNORED daemon-local spool: <outbox>/items-host.jsonl.

    WHY IT EXISTS. items.jsonl is git-TRACKED (the nightly emit and the
    marketing-publish lane both commit it back). The XG-W2 fast lanes now append
    through the canonical path, and those lanes run inside the VPS daemon — so
    without this split the daemon would dirty a tracked file in the VPS
    checkout and collide with its 3-minute `git pull`. The spool keeps every
    daemon-side write out of git while local readers (the near-dup corpus, the
    story lock) see the union, so the guards still work.

    WHAT THIS DOES *NOT* SOLVE — say it plainly. Items in the spool are invisible
    to the Actions-side publisher, which folds items.jsonl in a different
    checkout. Press and earnings items therefore still do not reach the
    publisher; they will reach it via the future VPS-direct posting lane
    (B3/P1), not via this file. The split-brain is unchanged: this only removes
    the tracked-file dirt hazard the canonical-path move would otherwise have
    introduced.
    """
    return outbox_dir(root) / "items-host.jsonl"


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

    UNLIMITED: a value of -1 (or any negative) means "no daily cap" — the
    autonomous-cadence policy (operator 2026-07-24). This function returns -1 to
    signal unlimited; every consumer treats a negative cap as "do not bound"
    (emission gate below, the admin slot-meter/limits display). The outbox may
    still LOWER an unlimited Sentinel cap to a real number.
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
    # Negative = unlimited (+∞ for the min); outbox may lower a bounded ceiling.
    s = float("inf") if sentinel_cap < 0 else sentinel_cap
    o = float("inf") if outbox_cap < 0 else outbox_cap
    eff = min(s, o)
    return -1 if eff == float("inf") else max(0, int(eff))


def stricter_daily_cap(base_cap: int, tier_cap: "int | None") -> int:
    """Combine a base daily cap with a ramp tier's, keeping the STRICTER.

    Both sides speak the same unlimited dialect from opposite ends: ``base_cap``
    negative means unlimited (the -1 sentinel every consumer already handles),
    ``tier_cap`` None means unlimited (what sentinel's resolved caps carry). The
    result is a plain cap in the base dialect: -1 for "still unlimited", else a
    non-negative bound.
    """
    if tier_cap is None:
        return base_cap
    t = max(0, int(tier_cap))
    return t if base_cap < 0 else max(0, min(int(base_cap), t))


def effective_cap_for(
    cfg: dict,
    account_id: str,
    as_of: str,
    *,
    root: "Path | str | None" = None,
    ramp: "dict | None" = None,
) -> int:
    """``effective_cap`` narrowed by ONE account's D08 age-ramp tier.

    WHY THIS EXISTS. effective_cap() reads only the base
    ``sentinel.max_posts_per_account_per_day``, which is -1 (unlimited) live — so
    every post-time cap check was vacuously False and an approved backlog
    (retries, operator approvals, items queued before the ramp shipped) could
    drain at roughly one per publisher sweep, far past a week-1 account's 2/day.
    The plan-tier gate cannot catch that: those items already cleared it, on an
    earlier day or by a different route.

    ``as_of`` is the caller's OWN reference date — the plan date at plan tier, the
    posting date at post tier. An account can cross a tier boundary between the
    two, and that is fine: each seam applies the stricter answer for its own
    moment, and the ramp only ever loosens with age, so the later seam can only
    agree or be more permissive than the earlier one.

    Pass ``ramp`` (a resolve_ramp result) when calling this in a loop — otherwise
    each call re-resolves the tier table and re-reads the override file.
    Fail-soft: any resolution error falls back to the base cap.
    """
    base = effective_cap(cfg)
    try:
        if ramp is None:
            from engine.marketing.sentinel import resolve_ramp  # noqa: PLC0415
            ramp = resolve_ramp(cfg or {}, as_of, root=root)
        entry = (ramp.get("accounts") or {}).get(str(account_id))
        caps = entry["caps"] if entry else (ramp.get("fallback") or {})
        tier_cap = caps.get("max_posts_per_account_per_day")
    except Exception as exc:  # noqa: BLE001 — a cap lookup must never break a post
        log.warning("outbox.effective_cap_for(%r): %s — using the base cap",
                    account_id, exc)
        return base
    return stricter_daily_cap(base, tier_cap)


def sentinel_contract(cfg: dict) -> dict[str, Any]:
    """The Sentinel knobs the D02 actuator must honour, resolved from config
    with Sentinel in-code defaults. One read path for actuator + admin display.

    BASE VALUES ONLY — this is deliberately NOT ramp-aware. Every knob here is
    the un-tiered contract; the per-account narrowing lives in
    effective_cap_for() (daily volume) and sentinel.resolve_ramp() (everything
    else). ``effective_cap`` in the returned dict is likewise the base number, so
    a caller showing it next to a week-1 desk is showing the ceiling, not that
    desk's actual allowance.
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


# ── Cross-night near-duplicate guard ──────────────────────────────────────────
# _item_id folds as_of into the hash, so identical copy re-emitted on a LATER
# day gets a fresh id and id-dedupe never catches it. That is how two byte-
# identical "My read on today's move" event posts landed in the queue on
# 2026-07-26 and 2026-07-27 (each auto-approved, each bound for X ~24h apart —
# the exact robotic-repeat an anti-spam voice must not ship). The guard rejects
# a re-emit whose account-scoped normalized text matches any item from the last
# _TEXT_DEDUP_WINDOW_DAYS days. It fires ONLY on truly identical copy, so a
# signal/watchlist that legitimately updates its numbers day to day is untouched.
_TEXT_DEDUP_WINDOW_DAYS = 7


def _text_key(account: object, text: object) -> tuple[str, str]:
    """Account-scoped normalized-text key for near-dup detection (mirrors the
    normalization _item_id already applies, so whitespace-only diffs collide)."""
    return (str(account or ""), _normalize_text(str(text or "")))


def _parse_as_of(s: object) -> date | None:
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001
        return None


def _within_text_window(old_as_of: object, ref_as_of: object) -> bool:
    """True if old_as_of is within the dedup window of ref_as_of.

    Fail-OPEN on an unparseable date: an in-window verdict keeps the guard
    active rather than silently disarming it on one malformed row.
    """
    old = _parse_as_of(old_as_of)
    ref = _parse_as_of(ref_as_of)
    if old is None or ref is None:
        return True
    return abs((ref - old).days) <= _TEXT_DEDUP_WINDOW_DAYS


# Public alias for the publisher's post-time repeat gate.
text_key = _text_key


# ── Near-duplicate ("deeply reworded") guard ──────────────────────────────────
# Operator law 2026-07-27: accounts must not post repetitive same content unless
# DEEPLY REWORDED. Exact-text dedup (_text_key) only catches whitespace-diff
# copies; a lightly-edited repeat ("SPY holding 640" → "SPY is holding 640 today")
# still reads as robotic spam. near_duplicate() upgrades the guard to token
# Jaccard: two posts count as the same content when ≥ _NEAR_DUP_JACCARD of their
# combined token set is shared. Numbers are kept in the token set on purpose — a
# genuinely changed level/price legitimately lowers similarity, which is exactly
# the "deep rewording" signal we want to reward. 0.7 matches the plan-time
# distinctness() precedent (content_studio.distinctness).
_NEAR_DUP_JACCARD = 0.7


def token_jaccard(a: str, b: str) -> float:
    """Token-Jaccard similarity between two strings in [0.0, 1.0].

    Lowercase, tokenize on ``\\w+`` (numbers KEPT — a changed level/price should
    lower similarity). Two empty texts → 0.0. Shared with near_duplicate() so the
    publisher's quarantine receipt can print the same score the gate decided on."""
    ta = set(re.findall(r"\w+", (a or "").lower()))
    tb = set(re.findall(r"\w+", (b or "").lower()))
    union = len(ta | tb)
    if not union:
        return 0.0
    return len(ta & tb) / union


def near_duplicate(a: str, b: str, *, threshold: float = _NEAR_DUP_JACCARD) -> bool:
    """True when a and b share ≥ ``threshold`` of their combined token set
    (token_jaccard). Two empty texts are NOT near-duplicates (0.0 < threshold)."""
    return token_jaccard(a, b) >= threshold


def cross_account_threshold(cfg: dict | None) -> float:
    """The CROSS-ACCOUNT near-dup Jaccard bar, from Sentinel config.

    ``sentinel.near_dup_jaccard`` is by its own config comment the cross-account
    threshold ("lowered from 0.60 to 0.50 per D08_APPENDIX_X_POLICY_REDTEAM §4 …
    the policy bar is 'substantially similar'"), and it is DELIBERATELY stricter
    than the same-account bar (_NEAR_DUP_JACCARD = 0.7): one account rewording
    its own coverage is a style problem, two accounts converging on one wording
    is a network-linkage tell — the text-similarity clustering X has run since
    2026-03. Sentinel already applies this bar ACROSS accounts inside a single
    nightly content plan (sentinel.py STEP 4); this is the same bar applied to
    the outbox queue, which spans nights and carries the fast lanes that never
    enter a plan at all.
    """
    try:
        return float(sentinel_contract(cfg or {})["near_dup_jaccard"])
    except Exception:  # noqa: BLE001
        return float(_sentinel_defaults()["near_dup_jaccard"])


#: Folded statuses that mean an item is DEAD — it will never be posted.
#: `recalled` belongs here for a concrete reason: the operator recalls in order
#: to REPLACE the copy, and a recalled item left in the near-dup corpus would
#: veto its own replacement as a near-duplicate of a post nobody ever saw.
_DEAD_STATUSES: frozenset[str] = frozenset({"quarantined", "failed", "recalled"})


def dead_item_ids(root: Path | str | None = None) -> set[str]:
    """Ids whose LAST ledger transition left them quarantined or failed.

    A dead item must not sit in the near-dup corpus. It is not competing for the
    slot — nothing will ever post it — so letting its text block a live desk's
    item is a guard punishing the wrong post. This matters most for the
    CROSS-ACCOUNT radar, where one desk's quarantined copy would otherwise
    silently veto another desk's coverage of the same event indefinitely.

    Last-row semantics on purpose: ``failed`` is re-armable (failed → approved),
    so an item that failed and was retried is alive again and the last row says
    so. The CAP counter deliberately still counts dead items — refilling a bad
    slot the same day is how retry-spam starts — which is a different question
    from "may this text go out".
    """
    last_to: dict[str, str] = {}
    for row in read_jsonl(_ledger_path(root)):
        iid, to = row.get("id"), row.get("to")
        if iid and to:
            last_to[str(iid)] = str(to)
    return {i for i, s in last_to.items() if s in _DEAD_STATUSES}


def _recent_texts_by_account(existing: list[dict], ref_as_of: object,
                             dead: set[str] | frozenset[str] = frozenset(),
                             ) -> dict[str, list[str]]:
    """account → [normalized text, ...] for every in-window, LIVE existing item.

    Feeds the enqueue-time near-dup guard (near_duplicate): a new item's text is
    compared against every same-account prior text in the 7-day window.
    ``dead`` (see :func:`dead_item_ids`) is excluded — a quarantined or failed
    item is not going out, so it must not block anything."""
    out: dict[str, list[str]] = {}
    for i in existing:
        if not _within_text_window(i.get("as_of"), ref_as_of):
            continue
        if str(i.get("id") or "") in dead:
            continue
        acct = str(i.get("account") or "")
        out.setdefault(acct, []).append(_normalize_text(str(i.get("text") or "")))
    return out


def recent_posted_text_keys(state: dict, ref_as_of: str) -> set:
    """Account-scoped normalized-text keys of items that already WENT OUT
    (folded status posted/posting) within the last _TEXT_DEDUP_WINDOW_DAYS.

    The enqueue() text guard stops identical copy ENTERING the queue, but an
    item that slipped in before that guard shipped (the 2026-07-26/27 "My read
    on today's move" pair) sits queued under a fresh id and fires a night
    later. This is the post-time half: the publisher checks a due item's text
    against this set and quarantines a repeat instead of sending it.

    A `recalled` item is excluded on purpose (see TRANSITIONS): its text never
    reached anyone, so it is not a prior post and must not veto the rewrite the
    operator recalled it to make room for.
    """
    keys: set = set()
    items = state.get("items") or {}
    statuses = state.get("status") or {}
    for iid, st in statuses.items():
        if st not in ("posted", "posting"):
            continue
        it = items.get(iid)
        if not isinstance(it, dict):
            continue
        if _within_text_window(it.get("as_of"), ref_as_of):
            keys.add(_text_key(it.get("account"), it.get("text")))
    return keys


def recent_posted_texts(state: dict, ref_as_of: str) -> dict[str, list[tuple[str, str, str]]]:
    """account → [(item_id, normalized text, as_of), ...] of items that already
    WENT OUT (folded status posted/posting) within the window.

    The richer sibling of recent_posted_text_keys: it carries the item id and
    date so the publisher's post-time NEAR-DUP gate can name the offending prior
    post in its quarantine receipt (\"near-identical (jaccard=0.83) to <id> posted
    <date>\"). Same window/status scoping as recent_posted_text_keys."""
    out: dict[str, list[tuple[str, str, str]]] = {}
    items = state.get("items") or {}
    statuses = state.get("status") or {}
    for iid, st in statuses.items():
        if st not in ("posted", "posting"):
            continue
        it = items.get(iid)
        if not isinstance(it, dict):
            continue
        if not _within_text_window(it.get("as_of"), ref_as_of):
            continue
        acct = str(it.get("account") or "")
        out.setdefault(acct, []).append(
            (iid, _normalize_text(str(it.get("text") or "")), str(it.get("as_of") or "")))
    return out


def compose_text(headline: object, body: object) -> str:
    """Flatten a {headline, body} pair into the canonical item ``text`` (XG-W2).

    WHY THE SCHEMA HAS ONE STRING. ``text`` is the post, and every guard in this
    module is built on that: :func:`_item_id` hashes ``_normalize_text(text)``,
    the exact-text dedup keys on it, and :func:`near_duplicate` tokenizes it. The
    fast lanes (press_lane, fastlane) used to carry ``{"headline":…, "body":…}``
    in that slot, which is not merely unsupported — it silently DEFEATS the
    guards (``_normalize_text`` raises on a dict, and a stringified dict
    tokenizes the schema key names alongside the copy). Routing those lanes
    through the canonical path is only worth anything if the text they carry is
    the text the guards can see.

    ``"\\n\\n".join`` is the house convention, not a new one: ``admin/marketing.py``
    already reconstructs a plan post's outbox text as headline + blank line +
    body when it joins usage back onto the plan. Producers that want the two
    halves separately readable keep them as top-level ``headline``/``body``.
    """
    parts = [str(headline or "").strip(), str(body or "").strip()]
    return "\n\n".join(p for p in parts if p)


def _value_gate_enforced(cfg: dict | None, kind: str | None = None) -> bool:
    """Is the Gift-Grip-Proof gate armed to BLOCK this kind, or only to record?

    THE SINGLE READER of `config/marketing.yml` `value_gate.enforce`. Ships
    false (the XG-W2 "LAND DARK" precedent): every emission carries its verdict
    from day one, but an abstention does not stop a live desk until an operator
    flips this after reading a cycle of `value_gate_would_block` counts.

    A config key nothing reads is a lie in a config file, which is precisely
    what the XG-W3 review caught — so this function exists to be the reader, and
    `tests/test_marketing_desk_feeds.py` asserts both branches are live.

    ARMING IS PER-KIND, BECAUSE THE EVIDENCE IS PER-KIND (2026-07-30).
    `value_gate.py`'s own PRE-ARMING REQUIREMENT is that the regression corpus
    cover the kinds enforcement will police, and it names the reason: a gate
    armed on the kinds that happened to be in one nightly plan is "validated on
    the generator it polices". The measured corpus
    (`data/marketing/outbox/items.jsonl`, 154 stamped emissions) covers eight
    kinds. It does not cover `wire`, `earnings`, `receipt`, `reply` or `news` —
    for those the honest count of observations is ZERO, and a global boolean
    would silence them on no evidence at all.

    So `enforce` arms only the kinds listed in `value_gate.enforce_kinds`. An
    emission of any other kind keeps its verdict RECORDED and ships, and the
    caller announces the unmeasured kind so it stops being unmeasured. This is
    the same posture the repo takes everywhere else: display-tier freely,
    authority only where it was earned.

    `enforce_kinds` absent (or empty) with `enforce: true` means EVERY kind —
    the old global behaviour — so an operator can still arm the whole board in
    one line once the corpus justifies it.
    """
    block = (cfg or {}).get("value_gate") or {}
    if not bool(block.get("enforce", False)):
        return False
    armed = block.get("enforce_kinds")
    if not armed:
        return True
    if kind is None:
        # No kind supplied: the caller cannot say what it is emitting, so it
        # gets the conservative answer rather than a silent block.
        return False
    return str(kind) in {str(k) for k in armed}


def value_gate_kind_is_measured(cfg: dict | None, kind: str | None) -> bool:
    """Does `kind` sit inside the armed set? False means "recorded, not policed".

    Exists so a caller can tell an abstention it ACTED on from one it merely
    noticed, and log them differently — the distinction that was invisible while
    both printed "would abstain".
    """
    block = (cfg or {}).get("value_gate") or {}
    armed = block.get("enforce_kinds")
    if not armed:
        return True
    return kind is not None and str(kind) in {str(k) for k in armed}


def stamp_value_gate(
    source: dict,
    *,
    headline: str,
    body: str,
    kind: str,
    has_media: bool = False,
    numbers_whitelist: Any = (),
    source_headline: str = "",
    citation: str = "",
    cfg: dict | None = None,
) -> bool:
    """Evaluate the Gift-Grip-Proof gate and STAMP the verdict onto `source`.

    Charter §0 XG-W3: "every emission carries its Gift-Grip-Proof gate verdict
    in the item metadata (abstention logged with reason)". This is the function
    that makes that true of real emissions — the gate module itself only
    computes; without a call here the verdict existed in tests and nowhere else.

    Returns True when the verdict is an ABSTENTION (i.e. the gate WOULD block if
    armed). The caller decides what to do with that: record-only today,
    skip-the-emission once `value_gate.enforce` is flipped.

    Fail-soft: if the gate raises, the item is stamped `error` and treated as
    PASSING. A publish gate that goes down must not silence the desks — the
    whole calibration exercise was about not doing that.
    """
    try:
        from engine.marketing import value_gate as _vg  # noqa: PLC0415

        verdict = _vg.evaluate(
            headline, body, kind=kind, has_media=has_media,
            numbers_whitelist=numbers_whitelist,
            source_headline=source_headline, citation=citation,
        )
        meta = _vg.verdict_metadata(verdict)
        meta["enforced"] = _value_gate_enforced(cfg)
        source["value_gate"] = meta
        return verdict.verdict != "pass"
    except Exception as exc:  # noqa: BLE001
        log.warning("value_gate: verdict unavailable (%s) — emitting unstamped", exc)
        source["value_gate"] = {"verdict": "error", "error": str(exc)[:200]}
        return False


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
    """Read all item records from the TRACKED items.jsonl. [] on any error.

    Deliberately NOT the union: this is what fold_state, the publisher and the
    admin read, and those must keep seeing exactly the queue that is committed
    and shared. Local guards that need the daemon spool too call
    :func:`read_items_all`.
    """
    return read_jsonl(_items_path(root))


def read_items_all(root: Path | str | None = None) -> list[dict]:
    """Tracked items PLUS the gitignored daemon spool (see _host_items_path).

    The corpus for anything that asks "does this content already exist?" — the
    enqueue dedup/near-dup guards and the one-owner story lock. Those questions
    must be answered against everything this host has emitted, or a daemon-side
    emission would be invisible to the very guards that exist to catch it.
    """
    return read_jsonl(_items_path(root)) + read_jsonl(_host_items_path(root))


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


def posted_today_by_account(state: dict, today: str) -> dict[str, int]:
    """Ledger-based posts-today per account — the Sentinel daily-cap counter.

    Nightly content-plan items carry the GENERATION day's as_of (content_studio
    stamps the nightly run date) and post the NEXT trading day, so counting
    as_of == today undercounts. Count instead by the last ledger row's `at`
    date: an item whose folded status is posted/posting AND whose last
    transition happened today consumed a posting slot today ("posting" is
    in-flight — it likely reached the network, so it holds its slot).

    `recalled` is DELIBERATELY not in that set, and it must stay out: a recalled
    item was cancelled at the backend before it ever sent, so it consumed no
    posting slot. Counting it would silently shrink the day's real volume by
    exactly the number of posts the operator pulled — the opposite of what a
    recall is for, which is to make room for the corrected copy. The safety this
    set DOES carry is unchanged: a genuinely-sent post stays `posted` forever
    (the runner only recalls a booking whose send time is still in the future),
    so it keeps counting here.

    `state` is a fold_state() dict; `today` is "YYYY-MM-DD".
    """
    return {acct: len(rows)
            for acct, rows in posted_today_rows_by_account(state, today).items()}


def posted_today_rows_by_account(
    state: dict, today: str,
) -> dict[str, list[tuple[str, str, str]]]:
    """account → [(item_id, text, kind), ...] for items that POSTED today.

    The richer sibling of :func:`posted_today_by_account`, which is now a count
    over this — ONE predicate decides "did this consume a posting slot today", so
    the cap counter and the post-time gates below can never disagree about which
    posts make up an account's day. Read the docstring above for why the day comes
    from the last ledger row's `at` and not from `as_of`.

    Feeds the publisher's ported #3928 gates: the per-account template-FRAME
    similarity check needs the day's texts, and the filler cap needs their kinds.
    Deliberately SAME-DAY where recent_posted_texts is 7-day — one desk reusing a
    frame next week is cadence, not spam, and a filler cap is a daily budget.
    """
    items = state.get("items") or {}
    last = state.get("last") or {}
    status = state.get("status") or {}
    out: dict[str, list[tuple[str, str, str]]] = {}
    for iid, it in items.items():
        if status.get(iid, "queued") not in {"posted", "posting"}:
            continue
        at = str((last.get(iid) or {}).get("at") or "")
        if at[:10] == today:
            out.setdefault(it.get("account", ""), []).append(
                (str(iid), str(it.get("text") or ""), str(it.get("kind") or "")))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Enqueue
# ─────────────────────────────────────────────────────────────────────────────

def _rejection_reason(
    *,
    item_id: str,
    account: str,
    as_of: str,
    text: str,
    ctx: dict,
    cap: int,
) -> str | None:
    """Why `enqueue` would refuse this item, or None if it would accept it.

    EXTRACTED SO A PREFLIGHT CANNOT DRIFT FROM THE REAL CHECK (2026-07-30).
    Every rejection here is a function of (id, account, as_of, text) — NOT of
    media. That is what makes `preflight_enqueue` below possible and honest: a
    caller can learn the verdict before paying for a picture, and it learns it
    from THIS function rather than from a second copy of these rules that would
    quietly diverge on the next edit. A preflight that disagrees with the gate
    is worse than no preflight — it either wastes the render it promised to
    save, or silently drops a post the gate would have taken.
    """
    if item_id in ctx["ids"]:
        return "duplicate"
    # Cross-night near-dup: identical copy re-emitted on a later day gets
    # a fresh id (as_of is in the hash), so the id check above misses it.
    # recent_texts holds account-scoped normalized text from the window;
    # absent for legacy _ctx callers → the guard no-ops (back-compat).
    new_text = _normalize_text(str(text or ""))
    if (account, new_text) in ctx.get("recent_texts", ()):
        return "duplicate"
    # Near-duplicate ("deeply reworded" law, 2026-07-27): also reject a
    # lightly-edited repeat — token Jaccard ≥ 0.7 vs any same-account text
    # in the window. recent_texts_by_account maps account → its normalized
    # texts; absent for legacy _ctx callers → the guard no-ops.
    prior_texts = ctx.get("recent_texts_by_account", {}).get(account, ())
    if any(near_duplicate(new_text, prior) for prior in prior_texts):
        return "duplicate"
    # CROSS-ACCOUNT near-dup radar (XG-W2). The guard above is strictly
    # same-account; with seven live accounts the failure that matters is
    # TWO of ours posting near-identical text, which reads as one
    # operator running a fleet — the coordination signal the near-dup
    # bar exists to deny. Same Jaccard machinery, wider corpus, stricter
    # threshold (sentinel.near_dup_jaccard — see cross_account_threshold).
    xa_thresh = ctx.get("cross_account_threshold")
    if xa_thresh is not None:
        by_account = ctx.get("recent_texts_by_account", {})
        for other_acct, other_texts in by_account.items():
            if other_acct == account:
                continue
            if any(near_duplicate(new_text, prior, threshold=xa_thresh)
                   for prior in other_texts):
                log.warning(
                    "outbox.enqueue: %s rejected — near-identical to a "
                    "recent %s item (cross-account jaccard >= %.2f)",
                    account, other_acct, xa_thresh)
                return "cross_account_duplicate"
    # Cap: every existing same-day item consumed a slot regardless of
    # status (quarantined/failed included — refilling a bad slot the
    # same day is how retry-spam starts). A negative cap = unlimited
    # (autonomous cadence) → never blocks on volume.
    if cap >= 0 and ctx["day_counts"].get((account, as_of), 0) >= cap:
        return "cap_exceeded"
    return None


def _enqueue_ctx(root: Path | str | None, as_of: object, cfg: dict | None) -> dict:
    """The corpus `_rejection_reason` reads. Built identically for both callers."""
    existing = read_items_all(root)
    dead = dead_item_ids(root)
    ctx = {
        "ids": {i.get("id") for i in existing},
        "day_counts": {},
        "recent_texts": {
            _text_key(i.get("account"), i.get("text"))
            for i in existing
            if _within_text_window(i.get("as_of"), as_of)
            and str(i.get("id") or "") not in dead
        },
        "recent_texts_by_account": _recent_texts_by_account(existing, as_of, dead),
        "cross_account_threshold": cross_account_threshold(cfg),
    }
    for i in existing:
        key = (i.get("account"), i.get("as_of"))
        ctx["day_counts"][key] = ctx["day_counts"].get(key, 0) + 1
    return ctx


def preflight_enqueue(
    *,
    account: str,
    kind: str,
    text: str,
    as_of: str,
    root: Path | str | None = None,
    cfg: dict | None = None,
    max_per_account_day: int | None = None,
) -> str:
    """Would `enqueue` refuse this copy? Answered WITHOUT building the media.

    Returns the same code `enqueue` would ("duplicate", "cross_account_duplicate",
    "cap_exceeded") or "ok".

    WHY THIS EXISTS. A lane that draws a chart card before enqueueing pays a
    Chrome raster AND an R2 upload for every duplicate, near-duplicate and cap
    rejection — a picture nobody will ever see, charged against a nightly render
    budget that is law (~67 min, 4-core-bound). The deciding text always exists
    before the render; only the ordering was wrong. Callers keep their own
    account of that; this function stays generic, and deliberately knows nothing
    about which program calls it.

    FAIL-OPEN BY CONSTRUCTION. Any error returns "ok", so a preflight that
    cannot read the corpus costs a wasted render at worst and can never become a
    publish outage. It is an optimisation, not a gate: `enqueue` still runs every
    one of these checks under the outbox lock, which is where the answer is
    authoritative. This function races by design — it reads without the lock —
    and that is safe precisely because it can only skip work, never admit any.
    """
    try:
        item_id = _item_id(account, kind, text, as_of)
        cap = (max_per_account_day if max_per_account_day is not None
               else effective_cap(cfg or {}))
        ctx = _enqueue_ctx(root, as_of, cfg)
        return _rejection_reason(
            item_id=item_id, account=account, as_of=as_of,
            text=text, ctx=ctx, cap=cap,
        ) or "ok"
    except Exception as exc:  # noqa: BLE001
        log.warning("outbox.preflight_enqueue: %s — assuming ok", exc)
        return "ok"


def _parse_ts(value: object) -> datetime | None:
    """Parse an outbox timestamp ("...Z" or ISO) to an aware UTC datetime.

    None for "immediate", "", or anything unparseable — those carry no schedule
    to compare, and a floor that guessed at them would invent one.
    """
    raw = str(value or "").strip()
    if not raw or raw.lower() == "immediate":
        return None
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def apply_schedule_floor(item: dict, *, now: datetime | None = None) -> str | None:
    """Clamp `scheduled_at` forward so a post is never scheduled before it existed.

    Returns the ORIGINAL scheduled_at when the item was clamped, else None.
    Mutates `item` in place — deliberately: the caller keeps the dict it queued
    (the governor lanes log and index off it), and a copy corrected only on the
    persisted row would leave the caller's state disagreeing with the ledger
    about when its own post goes out. Because the mutation is visible to the
    caller, :func:`enqueue` calls this only AFTER the duplicate/cap checks have
    passed — see the call site for why a rejected item must come back untouched.

    THE DEFECT (X Growth audit, 2026-07-31): 41 items in one week carried a
    `scheduled_at` EARLIER than their own `created_at` — a slot ladder resolved
    against the content date while the run itself happened hours later, so an
    item created 15:46Z was booked for 13:00Z the same day. It poisons every
    "was this late?" measurement downstream: an item can be nine hours overdue
    the instant it is written, so lateness stops measuring the pipeline and
    starts measuring the ladder's arithmetic.

    WHAT THIS DOES **NOT** FIX (stated plainly because an earlier draft of this
    docstring claimed it, adversarial review 2026-07-31). Clamping to
    `created_at` moves the due time from "hours before the item existed" to "the
    moment the item existed" — which is still in the PAST by the time any
    publish sweep sees it. The item is therefore still due-now, still lands in
    the same undifferentiated backlog, and a batch of them still drains
    back-to-back. Only the LATENESS MEASUREMENT is repaired here. What actually
    spaces the burst is the publisher's own `min_minutes_between_posts` floor;
    what would prevent it is a lane that books an honest future slot.

    THE CLAMP IS TO `created_at`, NOT TO A LATER LADDER SLOT. Choosing the next
    free slot needs the whole day's ladder occupancy, which this function has no
    business knowing and no lock over; creation time is the earliest moment the
    post could honestly have gone out. The original value is preserved in
    `source.scheduled_at_original` so a lane emitting bad slots stays diagnosable
    rather than being silently tidied up.
    """
    created = _parse_ts(item.get("created_at")) or (now or datetime.now(timezone.utc))
    sched = _parse_ts(item.get("scheduled_at"))
    if sched is None or sched >= created:
        return None
    original = str(item.get("scheduled_at") or "")
    item["scheduled_at"] = created.strftime("%Y-%m-%dT%H:%M:%SZ")
    src = item.get("source")
    if not isinstance(src, dict):
        src = {}
        item["source"] = src
    src["scheduled_at_original"] = original
    log.warning(
        "outbox.enqueue: %s scheduled %s BEFORE it was created %s — clamped "
        "forward to creation time (lane %r)",
        item.get("id"), original, item.get("created_at"), item.get("provenance"),
    )
    return original


def enqueue(
    item: dict,
    root: Path | str | None = None,
    *,
    max_per_account_day: int | None = None,
    cfg: dict | None = None,
    spool: bool = False,
    _ctx: dict | None = None,
) -> str:
    """Append an item to the outbox queue if valid and not duplicate/over-cap.

    Returns one of: "queued" | "duplicate" | "cross_account_duplicate" |
    "cap_exceeded" | "invalid:<msg>". Never raises.

    cfg: the marketing config, read for the daily cap and the cross-account
    near-dup threshold (sentinel.near_dup_jaccard). None → Sentinel's in-code
    defaults, so the guard is on either way; the config can tune it, never
    disarm it.

    spool: True writes to the GITIGNORED daemon-local items-host.jsonl instead
    of the tracked items.jsonl (see _host_items_path). The VPS daemon sets it;
    everything else leaves it False. The read side is unaffected — every guard
    below reads the UNION, so a spooled item still blocks a later duplicate.

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
        # effective_cap({}) here IGNORED the threaded cfg and landed on the
        # Sentinel in-code default of 2/account/day — so every caller that
        # passed cfg but no explicit max_per_account_day (the XG-W2 fast lanes)
        # was silently capped at 2, contradicting the operator's 2026-07-27
        # "breaking has no limits" ruling. Read the cfg that was actually given.
        cap = (max_per_account_day if max_per_account_day is not None
               else effective_cap(cfg or {}))

        def _check_and_append(ctx: dict) -> str:
            rejection = _rejection_reason(
                item_id=item_id, account=account, as_of=as_of,
                text=str(item.get("text") or ""), ctx=ctx, cap=cap,
            )
            if rejection is not None:
                return rejection
            # SCHEDULE FLOOR — here rather than in each lane because every lane
            # that builds a slot ladder can get this wrong and only this seam
            # sees them all; `scheduled_at` is not part of the item id (which
            # hashes account/kind/text/as_of), so clamping it cannot change
            # dedupe behaviour and running it after the checks is free.
            #
            # AFTER THE CHECKS, NOT BEFORE (adversarial review, 2026-07-31). The
            # clamp mutates the CALLER's dict — deliberately, so the lane and the
            # ledger agree about a queued post — but it used to run at the top of
            # enqueue, before `_rejection_reason`. A duplicate or over-cap item
            # therefore came back to its lane rewritten ("queued" it never was),
            # with a `source.scheduled_at_original` breadcrumb about a row that
            # does not exist and a WARNING in the log about a post nobody queued.
            # Nothing is written here until the item is actually accepted, so
            # nothing should be rewritten either.
            apply_schedule_floor(item)
            new_text = _normalize_text(str(item.get("text") or ""))
            text_key = (account, new_text)
            target = _host_items_path(root) if spool else _items_path(root)
            if not append_jsonl(target, item):
                log.warning("outbox.enqueue: append_jsonl failed for item %r", item_id)
                return "invalid:append failed"
            ctx["ids"].add(item_id)
            ctx["day_counts"][(account, as_of)] = ctx["day_counts"].get((account, as_of), 0) + 1
            # Keep the near-dup structures current so two identical/near-identical
            # posts in ONE batch (same night) also collapse to one, not just across
            # nights.
            ctx.setdefault("recent_texts", set()).add(text_key)
            ctx.setdefault("recent_texts_by_account", {}).setdefault(account, []).append(new_text)
            return "queued"

        if _ctx is not None:
            _ctx.setdefault("cross_account_threshold", cross_account_threshold(cfg))
            return _check_and_append(_ctx)

        with _outbox_lock(root):
            # UNION corpus (tracked + daemon spool): a question of the form "does
            # this content already exist on this host?" must see every emission,
            # or a daemon-side item would be invisible to the guards.
            # Quarantined/failed items are excluded from the TEXT corpus only —
            # a dead item is not competing for the slot, so it must not veto a
            # live desk. It still counts toward the cap (see _rejection_reason).
            # Built by the SAME helper `preflight_enqueue` uses, so the two can
            # never answer differently because their corpora were assembled
            # differently.
            return _check_and_append(_enqueue_ctx(root, as_of, cfg))

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
    now: datetime | None = None,
    _state: dict | None = None,
) -> bool:
    """Append a status transition row to status_ledger.jsonl.

    Returns False (with log.warning) if the item is unknown or the transition
    is illegal from the current folded status. Never raises.

    now: stamps the row's `at` (default wall-clock UTC). Tests inject a fixed
    now so posted_today_by_account() — which counts by `at` date — stays
    deterministic; production callers leave it unset.

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
                "at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
# Regeneration
# ─────────────────────────────────────────────────────────────────────────────

def decided_source_keys(
    *,
    account: str,
    as_of: str,
    provenance: str,
    key: str = "ticker",
    root: Path | str | None = None,
) -> set[str]:
    """`source[key]` values this lane has already SETTLED for a day.

    Settled = the operator approved it, or it has moved past `queued` (posting /
    posted / failed). supersede_lane refuses to retire those, and rightly — but
    that alone leaves the door open to the same duplicate by another route: the
    lane regenerates, the old approved post survives, the new one queues beside
    it, and the ticker goes out twice. A regenerating lane must therefore also
    skip GENERATING for a slot that is already settled.

    A `hold` decision does not settle anything — held means "not yet", so better
    copy for a held ticker is exactly what a re-run should replace it with.
    """
    out: set[str] = set()
    try:
        state = fold_state(root)
        statuses, decisions = state["status"], (state.get("decisions") or {})
        for iid, it in state["items"].items():
            if (it.get("account") != account or it.get("as_of") != as_of
                    or it.get("provenance") != provenance):
                continue
            settled = (
                str(statuses.get(iid) or "queued") not in ("queued", "quarantined")
                or str((decisions.get(iid) or {}).get("decision") or "") == "approve"
            )
            if not settled:
                continue
            val = str(((it.get("source") or {}).get(key)) or "").strip()
            if val:
                out.add(val)
    except Exception as exc:  # noqa: BLE001
        log.warning("outbox.decided_source_keys failed: %s", exc)
    return out


def supersede_lane(
    *,
    account: str,
    as_of: str,
    provenance: str,
    keep_ids: set[str] | list[str],
    root: Path | str | None = None,
    actor: str = "governor",
    note: str | None = None,
) -> dict[str, Any]:
    """Retire a lane's PREVIOUS items for a day after it regenerates them.

    WHY: enqueue() dedupes on item id, and make_item() hashes the item's content
    into that id. So the moment a lane's copy changes, a re-run mints new ids and
    the new posts land ALONGSIDE the old ones instead of replacing them. On
    2026-07-26 two governor runs each wrote a full set for the same day and the
    operator had to delete eight duplicates by hand — the second set was strictly
    better (it was the first run with the LLM voice lane), but nothing retired
    the first.

    Only UNDECIDED items are retired. Two separate things can mean "the operator
    has spoken", and both are honoured:
      * a folded status past `queued` (approved / posting / posted / failed), and
      * an `approve` DECISION on an item still folded `queued` — record_decision
        writes the decision ledger, NOT a status transition, so an item the
        operator cleared minutes ago still folds as `queued`. Checking status
        alone silently threw that approval away (caught in test).
    A `hold` decision is not protection: held means "not yet", so replacing a
    held post with better copy for the same ticker is the point of a re-run.

    Returns {"superseded": n, "ids": [...], "skipped_decided": m}. Never raises —
    a failure here leaves duplicates, which is bad, but it must not break a
    nightly that has already written good content.
    """
    out: dict[str, Any] = {"superseded": 0, "ids": [], "skipped_decided": 0}
    try:
        keep = {str(i) for i in (keep_ids or set())}
        state = fold_state(root)
        items, statuses = state["items"], state["status"]
        decisions = state.get("decisions") or {}

        stale = [
            iid for iid, it in items.items()
            if iid not in keep
            and it.get("account") == account
            and it.get("as_of") == as_of
            and it.get("provenance") == provenance
        ]
        if not stale:
            return out

        msg = note or f"superseded by a later {provenance} run for {as_of}"
        for iid in stale:
            if str(statuses.get(iid) or "queued") != "queued":
                out["skipped_decided"] += 1
                continue
            if str((decisions.get(iid) or {}).get("decision") or "") == "approve":
                out["skipped_decided"] += 1
                continue
            if transition(iid, "quarantined", actor=actor, root=root,
                          note=msg, _state=state):
                out["superseded"] += 1
                out["ids"].append(iid)
        if out["superseded"]:
            log.info("outbox.supersede_lane: retired %d stale %s item(s) for %s/%s",
                     out["superseded"], provenance, account, as_of)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("outbox.supersede_lane failed: %s", exc)
        return out


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

# Legacy fixed-UTC suffixes — pre-ladder items (and their tests) still resolve.
_SLOT_SUFFIX_TIMES = {
    "AM":  "T14:00:00Z",
    "PM":  "T17:30:00Z",
    "EOD": "T20:15:00Z",
}

# The 30-minute Pacific signal ladder (operator re-spec 2026-07-28): 28 slots at
# 30-min steps from 4:00 AM to 5:30 PM LOCAL, resolved per-date through zoneinfo
# so the Pacific→UTC offset tracks DST — never hardcode -7/-8, it would drift the
# whole ladder an hour twice a year.
#
# Was 19 slots at 45-min steps (2026-07-27). The operator asked for a 30-minute
# flagship cadence and up to 20 posts/day there, which 19 slots cannot hold. The
# window is unchanged (4:00 AM–5:30 PM) so no post moves into low-engagement
# hours; only the step tightens, which is what makes room for 28.
#
# Slot NUMBERS therefore point at different clock times than they did (old S9 was
# 10:00, new S9 is 8:00). Nothing in flight moves: outbox items carry an absolute
# `scheduled_at` stamped at enqueue time, and this table is only consulted when a
# plan slot is first resolved. Generated from a step so the table cannot drift
# out of arithmetic — the previous hand-written dict is exactly the kind of thing
# that rots when someone inserts a slot.
_LADDER_START_PT = (4, 0)      # 4:00 AM Pacific
_LADDER_STEP_MIN = 30
_LADDER_N_SLOTS = 28           # 4:00 AM + 27*30min = 5:30 PM

_LADDER_PT_TIMES = {
    f"S{i + 1}": (
        (_LADDER_START_PT[0] * 60 + _LADDER_START_PT[1] + i * _LADDER_STEP_MIN) // 60,
        (_LADDER_START_PT[0] * 60 + _LADDER_START_PT[1] + i * _LADDER_STEP_MIN) % 60,
    )
    for i in range(_LADDER_N_SLOTS)
}
_LADDER_TZ = "America/Los_Angeles"


def slot_datetime(as_of: str, slot: str) -> str | None:
    """Resolve a plan slot to its advisory absolute ISO datetime (UTC), or None.

    A day slot is ``D<n>-<suffix>``: day n runs on ``as_of + (n-1) days`` (D1 is
    as_of itself). Two suffix families resolve:
      * ladder ``S1``..``S28`` — the Pacific clock ladder (4:00 AM–5:30 PM
        local, 30-min steps: see _LADDER_START_PT / _LADDER_STEP_MIN /
        _LADDER_N_SLOTS, which are the only source of truth), converted to UTC
        per-date via zoneinfo so DST is handled correctly. This line read
        "S1..S19 … 45-min steps" through two widenings of the ladder; the movers
        seating now depends on the upper slots existing, so a reader who trusted
        the doc would conclude S20+ resolves to None and the seating is broken;
      * legacy ``AM``/``PM``/``EOD`` — fixed UTC times, kept so pre-ladder items
        (and their tests) still resolve.
    Returns None for immediate/publish-time slots (MOVER-/THEME-/CONF-, or any
    non-``D<n>`` prefix), an unknown suffix, an unparseable as_of, or a missing
    tz database — the admin renders "immediate"/blank for None.

    Advisory only; the publisher applies the 10-min floor + jitter before posting.
    """
    if "-" not in slot:
        return None
    prefix, suffix = slot.split("-", 1)
    # suffix may itself contain a "-" for exotic labels; the key is the LAST
    # segment (matches the historical rsplit behaviour).
    suffix_key = suffix.rsplit("-", 1)[-1]
    if not (len(prefix) >= 2 and prefix[0] == "D" and prefix[1:].isdigit()):
        return None  # non-day slot (MOVER-/THEME-/CONF-/…) — treat as immediate
    day_n = int(prefix[1:])
    try:
        base = datetime.strptime(as_of[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    day = (base + timedelta(days=max(day_n - 1, 0))).date()

    # Ladder slot (Pacific clock) → UTC via zoneinfo (DST-safe).
    pt_time = _LADDER_PT_TIMES.get(suffix_key)
    if pt_time is not None:
        pt_hour, pt_minute = pt_time
        try:
            from zoneinfo import ZoneInfo  # noqa: PLC0415
            local = datetime(day.year, day.month, day.day, pt_hour, pt_minute,
                             tzinfo=ZoneInfo(_LADDER_TZ))
        except Exception:  # noqa: BLE001 — missing tz database → fail-soft to None
            return None
        return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Legacy fixed-UTC suffix (AM/PM/EOD) — pre-ladder items.
    time_suffix = _SLOT_SUFFIX_TIMES.get(suffix_key)
    if time_suffix is None:
        return None
    return f"{day.strftime('%Y-%m-%d')}{time_suffix}"


def _scheduled_at_for_slot(slot: str, as_of: str) -> str:
    """Map a slot to an advisory scheduled_at time, or "immediate".

    Thin wrapper over slot_datetime() that preserves the enqueue contract: a
    resolvable day slot returns its absolute ISO datetime; everything else
    (publish-time slots, unparseable inputs) returns the "immediate" sentinel.
    """
    return slot_datetime(as_of, slot) or "immediate"


#: Slot families that are unemittable ON PURPOSE and permanently, so their skip
#: count is a fact rather than an alarm (see the annotation block at the end of
#: emit_from_content_plan). `CONF` is the confluence lane: content_studio slots
#: it CONF-NN knowing this function takes D1- only, and its census note states
#: the choice outright — relabelling the slot would start publishing copy whose
#: win rate is a selection-on-test-half statistic, and a lane earns publication
#: on evidence, not on a prefix change. Anything NOT in this set that reaches
#: the unemittable bucket is a producer that went dark by accident and IS worth
#: waking the operator for.
_EXPECTED_UNEMITTABLE_FAMILIES: frozenset[str] = frozenset({"CONF"})


# ─────────────────────────────────────────────────────────────────────────────
# W1 no-fallback lane + stale-queued expiry
# (research/MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md §0 gate 1,
#  research/marketing_dockets/CONTENT_STUDIO_W1_BUILD_CONTRACT.md §Emit)
# ─────────────────────────────────────────────────────────────────────────────

#: The kinds the nightly Content Studio plans and writes. Mirrors
#: content_studio.PLANNED_KINDS and is resolved through it at call time so the
#: two lists cannot drift; this literal is only the import-failure floor.
_PLANNED_KINDS_FALLBACK: frozenset[str] = frozenset({
    "signal", "chart", "education", "macro", "receipt", "watchlist", "event",
    "congress", "insider",
})

#: Modes that mean "a language model wrote this sentence" (contract §Writer API).
_LLM_MODES: frozenset[str] = frozenset({"llm", "llm_repair"})

#: How far past its slot a planned item may sit before tonight's plan retires it.
_STALE_QUEUED_HOURS = 36

#: Provenances whose items :func:`expire_stale_wire` retires. These are the fast
#: lanes: they enqueue with ``scheduled_at="immediate"``, they carry no ladder
#: slot, and NOTHING ever swept them.
#:
#: `fastlane` and `neural_web` are deliberately absent — this reaper takes only
#: the three lanes whose stall was measured (see the docstring), and adopting a
#: lane whose retirement policy nobody has stated would be this function
#: guessing on that lane's behalf. Add one when its perishability is known.
#:
#: ONE LINE ON PURPOSE. The tape radar's safety-stack guard (in its own test
#: module) forbids this file from naming that program except through a reviewed,
#: token-pinned allowance — "a reviewed exception, recorded by name, rather than
#: a loosened rule". So the reference is confined to the single line below, and
#: every comment around it says "the fast lanes" instead.
_WIRE_PROVENANCES: frozenset[str] = frozenset({"press_lane", "hot_tape", "publisher_live_movers"})  # noqa: E501

#: Per-kind TTL, in hours, for a wire item that never got dispatched.
#:
#: DERIVED FROM THE LANES' OWN FRESHNESS CONSTANTS, deliberately loosened:
#:   * the tape radar's ``two_step.max_age_min`` = 60 — "past this the moment
#:     has passed and a 'context brief' is a history lesson";
#:   * its ``CARRYOVER_MAX_AGE_MIN`` = 20 — how long a booked-but-unposted alert
#:     may still ride a fresh dispatch;
#:   * publish_time_content _DEFAULTS["max_quote_age_min"] = 45 — past this the
#:     lane will not even WRITE a price claim, let alone stand behind one.
#:
#: Those say the copy is dead within the hour. The TTL is 3h, i.e. ~3x the
#: longest of them, because this reaper is TERMINAL and the failure it must not
#: have is shredding a live queue during a two-hour publish-sweep outage. The
#: publisher's tape gate already refuses a stale price claim non-terminally; this
#: is the backstop for items that gate never even reaches.
#:
#: MEASURED: the AMZN/COIN movers created 2026-07-31T15:32:53Z sat `queued` with
#: zero ledger rows for 8h — their "right now" long dead — because
#: expire_stale_planned takes `content_studio` provenance only and skips
#: `scheduled_at == "immediate"` outright, which is every row this lane writes.
_WIRE_TTL_HOURS_BY_KIND: dict[str, float] = {
    "breaking": 3.0,
    "mover": 3.0,
    "theme_list": 3.0,
}

#: TTL for a wire-provenance item of any other kind (`event` — the publish-time
#: daily read — and anything a lane adds later). Longer because it is not a
#: five-minute tape claim, still bounded because an unswept queue is how this
#: defect happened.
_WIRE_TTL_HOURS_DEFAULT: float = 12.0


def planned_kinds() -> frozenset[str]:
    """The planned-kind set, from content_studio when importable."""
    try:
        from engine.marketing.content_studio import PLANNED_KINDS  # noqa: PLC0415
        return frozenset(PLANNED_KINDS)
    except Exception:  # noqa: BLE001
        return _PLANNED_KINDS_FALLBACK


def llm_required(cfg: dict | None) -> bool:
    """Is the no-fallback law armed? (`copywriter.llm.required`)

    Resolved through content_studio.llm_required so ONE function decides it for
    the plan side and the emit side — a gate honoured at one seam and not the
    other is how template prose reached readers in the first place. The inline
    fallback repeats its rule exactly: default TRUE when a `copywriter.llm` block
    exists (deleting the key cannot disarm the gate), FALSE when a caller ships
    no copywriter config at all (it is not running the writer lane).
    """
    try:
        from engine.marketing.content_studio import llm_required as _req  # noqa: PLC0415
        return _req(cfg)
    except Exception:  # noqa: BLE001
        cw = (cfg or {}).get("copywriter") if isinstance(cfg, dict) else None
        llm = (cw or {}).get("llm") if isinstance(cw, dict) else None
        if not isinstance(llm, dict):
            return False
        v = llm.get("required", True)
        return v if isinstance(v, bool) else str(v).strip().lower() in {"1", "true", "yes"}


def _item_copy_mode(qi: dict) -> str:
    """The writer mode stamped on a plan queue item ("" when unstamped)."""
    return str(qi.get("_copy_mode") or qi.get("copy_mode") or "").strip().lower()


def expire_stale_planned(
    root: Path | str | None = None,
    *,
    now: datetime | None = None,
    max_age_hours: int = _STALE_QUEUED_HOURS,
    actor: str = "nightly_expiry",
) -> dict[str, Any]:
    """Retire planned-kind items that sat unposted long past their slot.

    Contract §Emit. A `queued`/`approved` item whose `scheduled_at` is more than
    ``max_age_hours`` in the past is a post about a tape that no longer exists —
    it was written against a close two nights ago and the plan that replaces it
    is being emitted RIGHT NOW. Left alone it either ships stale (the publisher
    happily posts anything approved and due) or clogs the admin queue with
    yesterday's rejects, and its text keeps vetoing tonight's copy through the
    7-day near-dup corpus.

    `expired` is deliberately NOT a new ledger status: TRANSITIONS is a safety
    contract and widening it for a housekeeping case would cost more than it
    buys. The item goes to `quarantined` (terminal, already reachable from both
    live statuses) with the note "expired: superseded by tonight's plan", so the
    admin's quarantine view carries the reason verbatim.

    SCOPED TO `content_studio` PROVENANCE. The wire lanes (press/fastlane) and
    weekend_levels manage their own retirement, and quarantining another lane's
    items from the nightly emit path would be this lane reaching into theirs.

    Uses the canonical writer (`transition`) on a single pre-folded snapshot, the
    same batch pattern supersede_lane uses — never a hand-appended ledger row.
    Never raises: expiry failing must not stop tonight's emission.
    """
    out: dict[str, Any] = {"expired": 0, "ids": []}
    try:
        ts_now = now if now is not None else datetime.now(timezone.utc)
        cutoff = ts_now - timedelta(hours=max(int(max_age_hours), 0))
        kinds = planned_kinds()
        state = fold_state(root)
        for iid, it in (state.get("items") or {}).items():
            if str(state["status"].get(iid) or "") not in ("queued", "approved"):
                continue
            if str(it.get("kind") or "") not in kinds:
                continue
            if str(it.get("provenance") or "") != "content_studio":
                continue
            raw = str(it.get("scheduled_at") or "").strip()
            if not raw or raw == "immediate":
                continue  # no slot to be late for
            try:
                sched = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if sched.tzinfo is None:
                sched = sched.replace(tzinfo=timezone.utc)
            if sched >= cutoff:
                continue
            if transition(iid, "quarantined", actor=actor, root=root,
                          note="expired: superseded by tonight's plan",
                          now=ts_now, _state=state):
                out["expired"] += 1
                out["ids"].append(iid)
        if out["expired"]:
            log.info("outbox.expire_stale_planned: retired %d stale planned item(s)",
                     out["expired"])
    except Exception as exc:  # noqa: BLE001
        log.warning("outbox.expire_stale_planned failed: %s", exc)
    return out


def _wire_item_born_at(it: dict, last_row: dict | None,
                       decision_row: dict | None = None) -> datetime | None:
    """The moment the wire reaper's idle clock starts. None when nothing parses.

    "Born" is IDLE-birth, not creation: the clock restarts every time somebody
    touches the item, so what the TTL measures is "how long has this sat with
    nobody doing anything about it", never "how long since it was written".

    NOT ``scheduled_at``: every lane in :data:`_WIRE_PROVENANCES` enqueues with
    the literal string ``"immediate"``, which is exactly why
    :func:`expire_stale_planned` — whose age comes from ``scheduled_at`` and
    whose first act on an immediate row is ``continue`` ("no slot to be late
    for") — could never have retired one of these even had the provenance
    matched.

    THE PRECEDENCE DEFECT (adversarial review, 2026-07-31). This function used
    to read ``created_at`` FIRST and fall through to the ledger only when it was
    missing — and :func:`make_item` ALWAYS stamps ``created_at``. So the ledger
    rung was dead code for every real item, and the docstring's own promise
    ("an item an operator touched five minutes ago is treated as five minutes
    old, not eight hours") was unreachable in production. Reproduced: item
    created 14:00Z, operator approved it 17:59Z, the 18:00Z sweep quarantined it
    — TERMINALLY, one minute after a human said ship it. The documented
    mitigation existed only in the fixture shapes the tests invented.

    Ladder, newest-touch first:
      1. the LATEST of (last APPLIED ledger row ``at``, latest decision row
         ``at``) — ANY activity restarts the clock. Both logs matter and neither
         subsumes the other: an operator's approve/hold lands in
         ``decisions.jsonl`` IMMEDIATELY, while the matching ledger row is only
         written when :func:`apply_decisions` next runs, so an item approved
         between the decision and the actuator has a fresh decision row and a
         stale (or absent) ledger row. Taking the max is what makes a
         human/desk touch — ``admin``/``operator`` decisions, the
         ``approval-desk`` and ``actuator`` transitions — reset the clock by
         itself, which is the whole point of this fix;
      2. ``created_at`` — stamped by make_item; the honest birth time, and the
         right answer for an item NOBODY has touched (the AMZN/COIN movers had
         zero ledger rows at 8h, which is exactly the stall this reaper exists
         for);
      3. ``as_of`` at 00:00Z — a date-only floor for pre-stamp rows.

    Returning None (nothing parsed) means the item is NEVER expired. A malformed
    stamp must not be the reason a post is destroyed — the same rule
    _item_age_days states in the publisher.
    """
    # Rung 1: newest touch across BOTH activity logs. max() over what parsed,
    # not "ledger else decision" — either log can be the newer one.
    touches = [
        ts for ts in (_parse_ts((last_row or {}).get("at")),
                      _parse_ts((decision_row or {}).get("at")))
        if ts is not None
    ]
    if touches:
        return max(touches)
    # Rungs 2 and 3: never touched — fall back to when it was written.
    for raw in (it.get("created_at"), it.get("as_of")):
        parsed = _parse_ts(raw)
        if parsed is not None:
            return parsed
    return None


def expire_stale_wire(
    root: Path | str | None = None,
    *,
    now: datetime | None = None,
    ttl_hours_by_kind: dict[str, float] | None = None,
    default_ttl_hours: float = _WIRE_TTL_HOURS_DEFAULT,
    provenances: frozenset[str] | set[str] | None = None,
    exempt_ids: frozenset[str] | set[str] | None = None,
    actor: str = "wire_expiry",
) -> dict[str, Any]:
    """Retire wire-lane items that outlived the moment they were written about.

    THE DEFECT. :func:`expire_stale_planned` is scoped to ``content_studio``
    provenance, and the note above it says why: "the wire lanes (press/fastlane)
    and weekend_levels manage their own retirement". They do not. Nothing in
    this repo sweeps an item from any of the lanes in :data:`_WIRE_PROVENANCES`,
    so a breaking/mover row that no ``--post-now`` batch happened to select sits
    `queued` FOREVER. Measured on 2026-07-31: the AMZN and COIN movers created
    at 15:32:53Z carried ZERO status-ledger rows eight hours later — their copy
    says "right now" about a tape that closed — and the operator's audit had to
    quarantine them by hand alongside 14 older siblings.

    Two separate reasons the planned reaper could never have covered them, both
    load-bearing: the provenance filter, AND the ``scheduled_at == "immediate"``
    skip, which every one of these rows trips (see :func:`_wire_item_born_at`).

    TTL IS PER KIND (:data:`_WIRE_TTL_HOURS_BY_KIND`) because perishability is:
    a `breaking` alert and a `mover` claim are five-minute facts, the
    publish-time daily read is not. Ages from IDLE TIME, not from a slot
    (a wire item has no slot) and not from creation — any touch in the ledger or
    the decisions log restarts the clock; see :func:`_wire_item_born_at`.

    ``exempt_ids``: ids this sweep must leave alone whatever their age. The
    publisher passes its ``--post-now`` set, because the reaper runs BEFORE
    post-now id resolution and would otherwise let the very run summoned to
    dispatch a breaking item quarantine it on the way in.

    `expired` is not a new ledger status, for the same reason expire_stale_planned
    gives: TRANSITIONS is a safety contract. The item goes to `quarantined`
    (terminal, reachable from both live statuses) with the note
    ``expired_stale_wire: …`` so the admin quarantine view carries the reason
    verbatim and is greppable.

    Returns {"expired": n, "ids": [...], "by_kind": {kind: n}}. Never raises:
    housekeeping failing must not stop a dispatch.
    """
    out: dict[str, Any] = {"expired": 0, "ids": [], "by_kind": {}}
    try:
        ts_now = now if now is not None else datetime.now(timezone.utc)
        ttls = dict(_WIRE_TTL_HOURS_BY_KIND)
        if ttl_hours_by_kind:
            ttls.update({str(k): float(v) for k, v in ttl_hours_by_kind.items()})
        lanes = frozenset(provenances) if provenances is not None else _WIRE_PROVENANCES
        spared = frozenset(exempt_ids or ())
        state = fold_state(root)
        for iid, it in (state.get("items") or {}).items():
            if iid in spared:
                # An id this run was explicitly told to dispatch. Checked FIRST,
                # ahead of every other filter, so no future scope change can
                # sneak past it.
                continue
            if str(state["status"].get(iid) or "") not in ("queued", "approved"):
                continue
            if str(it.get("provenance") or "") not in lanes:
                continue
            kind = str(it.get("kind") or "")
            ttl_h = float(ttls.get(kind, default_ttl_hours))
            if ttl_h <= 0:
                continue          # a lane may opt out by configuring 0
            # Both activity logs, because either can hold the newest touch —
            # see _wire_item_born_at for why an operator approval is visible in
            # decisions.jsonl before the ledger ever hears about it.
            born = _wire_item_born_at(
                it,
                (state.get("last") or {}).get(iid),
                (state.get("decisions") or {}).get(iid),
            )
            if born is None:
                continue          # unparseable birth → never expire (fail-open)
            age_h = (ts_now - born).total_seconds() / 3600.0
            if age_h < ttl_h:
                continue
            note = (f"expired_stale_wire: {kind or 'item'} sat untouched "
                    f"{age_h:.1f}h (ttl {ttl_h:.0f}h) — the moment it was "
                    f"written about is gone")
            if transition(iid, "quarantined", actor=actor, root=root,
                          note=note, now=ts_now, _state=state):
                out["expired"] += 1
                out["ids"].append(iid)
                out["by_kind"][kind] = out["by_kind"].get(kind, 0) + 1
        if out["expired"]:
            log.info("outbox.expire_stale_wire: retired %d stale wire item(s) %s",
                     out["expired"], out["by_kind"])
    except Exception as exc:  # noqa: BLE001
        log.warning("outbox.expire_stale_wire failed: %s", exc)
    return out


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
    An item that still claims an entry (type == "signal") and carries a truthy
    "_live_gate_fail" is skipped — a stale or invalidated signal never queues AS
    A SIGNAL. The same item after content_plan demotes it to "watchlist" DOES
    queue: it claims no entry, carries the no-marker tape card, and its copy is
    chosen by watch_reason. Items the D08 Sentinel gate quarantined
    (status == "quarantined") or left unverified (sentinel_ok is False — the
    gate's crash path stamps this) are skipped too: quarantined items surface
    on the admin Sentinel/Outbox views with reasons, never as queueable posts.

    THE NO-FALLBACK LAW (masterplan §0 gate 1, operator directive 2026-07-29).
    While `copywriter.llm.required` is on, a PLANNED-kind item (signal chart
    education macro receipt watchlist event) may only queue when a language model
    wrote it — item `_copy_mode` ∈ {llm, llm_repair}. The 2026-07-29 batch was
    65/65 deterministic-template output and the operator aborted review at post
    15; every patch before this one added another banned word to a list the
    generator cannot see its own output against. Refusals are counted
    (`skipped_not_llm`) and announced ONCE per emit as a start-of-line ::error,
    with different wording for "the lane is mute" and "the lane ran and these
    items still are not model copy" — the operator needs to know which.

    Reads items.jsonl ONCE for the whole batch (enqueue _ctx snapshot) and
    appends a summary row to activity.jsonl so the admin Outbox page can show
    what the last emit did and why items were skipped.

    Returns a summary dict: {emitted, skipped_dupe, skipped_cap, skipped_gate,
    skipped_sentinel, skipped_invalid, skipped_not_llm, skipped_slot_mismatch,
    skipped_slot_by_family, expired, media_written, by_account}.
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
        "skipped_not_llm": 0,
        # SLOT-PREFIX REFUSALS, COUNTED (defect closed 2026-07-31). The skip
        # below is the oldest and quietest gate in this function and it
        # incremented NOTHING: the 2026-07-31 emit activity row read
        # {emitted: 0, skipped_dupe: 0, skipped_cap: 0, skipped_gate: 0,
        # skipped_sentinel: 0, skipped_invalid: 0, skipped_not_llm: 0} while six
        # live movers/theme_list items were dropped on the floor. Every counter
        # zero and nothing emitted reads as "the plan was empty"; it was not.
        # `by_slot_family` names WHICH labels were refused, because the two
        # populations behave completely differently — see the annotation below.
        "skipped_slot_mismatch": 0,
        "skipped_slot_by_family": {},
        "expired": 0,
        "media_written": 0,
        "by_account": {},
    }

    cap = effective_cap(cfg or {})

    # ── Stale-queued expiry (contract §Emit) ─────────────────────────────────
    # BEFORE the emit lock, and before anything new is queued: tonight's plan is
    # what supersedes them, and an item retired here frees its text from the
    # near-dup corpus so tonight's copy for the same name is not vetoed by a post
    # that never went out. expire_stale_planned takes its own fold and writes
    # through transition(); running it inside the lock below would re-enter the
    # same advisory flock.
    _expiry = expire_stale_planned(root, now=ts_now)
    counts["expired"] = _expiry.get("expired", 0)

    # The no-fallback law and whether the writer lane spoke at all tonight. The
    # plan's own copy report is the honest witness for the second question: it
    # records the mode the copywriter pass resolved to.
    _require_llm = llm_required(cfg)
    _planned = planned_kinds()
    _plan_copy_mode = str(
        (((plan.get("content") or {}).get("copy") or {}).get("mode") or "")
    ).strip().lower()
    _lane_mute = not _plan_copy_mode.startswith("llm")
    _not_llm_modes: dict[str, int] = {}

    with _outbox_lock(root):
        # Same union + dead-item exclusion as enqueue()'s own corpus builder.
        existing = read_items_all(root)
        dead = dead_item_ids(root)
        ctx: dict[str, Any] = {
            "ids": {i.get("id") for i in existing},
            "day_counts": {},
            "recent_texts": {
                _text_key(i.get("account"), i.get("text"))
                for i in existing
                if _within_text_window(i.get("as_of"), as_of)
                and str(i.get("id") or "") not in dead
            },
            "recent_texts_by_account": _recent_texts_by_account(
                existing, as_of, dead),
            "cross_account_threshold": cross_account_threshold(cfg),
        }
        for i in existing:
            key = (i.get("account"), i.get("as_of"))
            ctx["day_counts"][key] = ctx["day_counts"].get(key, 0) + 1

        for acct_block in plan.get("accounts") or []:
            account_id = acct_block.get("id") or acct_block.get("name") or ""
            for qi in acct_block.get("queue") or []:
                try:
                    slot = qi.get("slot") or ""

                    if not slot.startswith(f"{day_prefix}-"):
                        # COUNTED, and bucketed by label family. A bare
                        # `continue` here is what let the movers desk exist for
                        # two weeks without publishing anything: the emit summary
                        # and the activity row both said every counter was zero.
                        #
                        # The family split is the whole point. `D2`..`D7` are the
                        # FORWARD ladder and are supposed to be skipped — nothing
                        # reads a previous plan, tomorrow regenerates the whole
                        # week, so those are noise, not a fault. Anything else
                        # (MOVER-, THEME-, CONF-, a bare label) is a producer that
                        # minted a slot this function can NEVER take: that lane
                        # cannot publish as built, whatever its census says, and
                        # that is worth an annotation.
                        counts["skipped_slot_mismatch"] += 1
                        _fam = slot.split("-", 1)[0] if "-" in slot else (slot or "(none)")
                        counts["skipped_slot_by_family"][_fam] = (
                            counts["skipped_slot_by_family"].get(_fam, 0) + 1)
                        continue

                    # The live gate protects the ENTRY CLAIM, so it only bars an
                    # item that is still making one. An item that failed it was
                    # demoted signal→watchlist by content_plan: it claims no
                    # entry, its card is the no-marker tape variant, and its copy
                    # comes from a template family chosen by watch_reason (a name
                    # that ran away gets "went without me", never "near entry").
                    # Dropping those was silently costing almost the whole day's
                    # volume — 39 of 47 Prophet signals are older than the 10-day
                    # window, so the network was living on the 8 fresh ones and
                    # publishing ~5 posts across 6 desks (measured 2026-07-28).
                    # A stale signal must never post AS A SIGNAL; "we're watching
                    # this name, here's the tape" is honest content and is the
                    # entry-timing material the desks exist to publish.
                    if qi.get("_live_gate_fail") and qi.get("type") == "signal":
                        counts["skipped_gate"] += 1
                        continue

                    # D08 Sentinel verdicts on the plan item. A missing
                    # sentinel_ok field (pre-D08 plan) passes through.
                    if qi.get("status") == "quarantined" or qi.get("sentinel_ok") is False:
                        counts["skipped_sentinel"] += 1
                        continue

                    # NO TEMPLATE PROSE ON A PLANNED KIND (§0 gate 1). The wire
                    # lanes are untouched — a wire one-liner survives templating,
                    # a persona's diary voice does not, which is the whole reason
                    # the fallback dies here and not everywhere.
                    _kind = str(qi.get("type") or "signal")
                    if _require_llm and _kind in _planned:
                        _mode = _item_copy_mode(qi)
                        if _mode not in _LLM_MODES:
                            counts["skipped_not_llm"] += 1
                            _label = _mode or "unwritten"
                            _not_llm_modes[_label] = _not_llm_modes.get(_label, 0) + 1
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

                            media_entry: dict[str, Any] = {
                                "kind": "chart_svg",
                                "path": svg_rel_path,
                                "chart_id": chart_id,
                                "ticker": qi.get("ticker") or fc.get("ticker") or "",
                            }
                            # Copy through the PNG variant rendered at plan-build
                            # time (content_studio._attach_chart_media): media_url
                            # is the public https URL the publisher attaches to the
                            # post; media_png_path is the repo-relative local PNG.
                            # Absent when publish.media_enabled is off or no chart
                            # closes existed — the post then stays text/SVG-only.
                            if fc.get("media_url"):
                                media_entry["media_url"] = fc.get("media_url")
                            if fc.get("media_png_path"):
                                media_entry["media_png_path"] = fc.get("media_png_path")
                            media.append(media_entry)

                    scheduled_at = _scheduled_at_for_slot(slot, as_of)

                    source: dict[str, Any] = {
                        "plan_item_id": qi.get("id"),
                        # Exact back-join key for the admin Content Studio usage
                        # fold (admin/marketing.content): plan post id → outbox
                        # item, so a posted post shows "posted" instead of a
                        # forever-"drafted" badge. Does NOT enter the item id hash
                        # (sha1 of account|kind|text|as_of only).
                        "plan_post_id": qi.get("id"),
                        "chart_id": chart_id,
                    }
                    # Surface the chart PNG on source too (the publisher reads
                    # source.media_url to attach without unpacking the media list).
                    if chart_id and chart_id in featured_charts:
                        _fc = featured_charts[chart_id]
                        if _fc.get("media_url"):
                            source["media_url"] = _fc.get("media_url")
                        if _fc.get("media_png_path"):
                            source["media_png_path"] = _fc.get("media_png_path")
                    # W1 telemetry provenance (contract §Emit): the mixer's
                    # shape, the allocator's angle and the writer's mode travel
                    # with the item so the learning lane (W1.5 per-shape
                    # engagement table) and the metrics poll can join engagement
                    # back onto the decisions that produced the post. Absent keys
                    # are omitted, never stubbed — an item with no shape is a
                    # pre-W1 item and must read as one.
                    for _pk, _sk in (("shape", "shape"), ("angle", "angle")):
                        _pv = qi.get(_pk)
                        if _pv:
                            source[_sk] = _pv
                    _cm = _item_copy_mode(qi)
                    if _cm:
                        source["copy_mode"] = _cm
                    _cc = qi.get("_copy_critic")
                    if _cc:
                        source["critic_verdict"] = _cc

                    # Structured tape-claim stamp for the publisher's post-time
                    # live gate (engine/marketing/live_verify.py): the ticker the
                    # copy is about, the thesis direction and levels, and any
                    # same-day move pct the copy asserts. Without this the gate
                    # can only regex cashtags out of the text.
                    if qi.get("ticker"):
                        source["ticker"] = qi.get("ticker")
                    plan_block = qi.get("_plan")
                    if isinstance(plan_block, dict):
                        if plan_block.get("id") is not None:
                            source["signal_id"] = plan_block.get("id")
                        for _sk, _pk in (("direction", "direction"),
                                         ("entry", "entry"),
                                         ("invalidation", "invalidation")):
                            if plan_block.get(_pk) is not None:
                                source[_sk] = plan_block.get(_pk)
                        # THE TARGETS TRAVEL TOO (approval-desk concern #1,
                        # measured 11/185 items on the 2026-07-31 corpus). The
                        # loop above copied direction/entry/invalidation and
                        # stopped, so a signal/watchlist post that printed its
                        # own plan's T1 — the copywriter whitelists t1/t2 from
                        # `plan["targets"]` and the templates literally say
                        # "T1 {target1}" — reached approval_desk with no source
                        # level to match it against and read as `invented_level`.
                        # The desk has read `source.t1`/`.t2`/`.target`
                        # defensively since it was built (approval_desk
                        # `_LEVEL_SOURCE_KEYS`) precisely so the day an emitter
                        # stamped them the desk would widen by itself; this is
                        # that day.
                        #
                        # `targets` is the plan's own shape (an ordered list),
                        # so t1/t2 are positions in it; the flat `t1`/`t2`/
                        # `target` keys are read first for the lanes that build
                        # a plan block by hand. Absent values are OMITTED, never
                        # stubbed — the same rule the W1 telemetry block above
                        # follows, and a stubbed None would look to the desk like
                        # a level the plan asserted.
                        _tgts = plan_block.get("targets")
                        _tgts = list(_tgts) if isinstance(_tgts, (list, tuple)) else []
                        for _sk, _pv in (
                            ("t1", plan_block.get("t1") if plan_block.get("t1") is not None
                                   else (_tgts[0] if len(_tgts) > 0 else None)),
                            ("t2", plan_block.get("t2") if plan_block.get("t2") is not None
                                   else (_tgts[1] if len(_tgts) > 1 else None)),
                            ("target", plan_block.get("target")),
                        ):
                            if _pv is not None:
                                source[_sk] = _pv
                    _mv_blk = qi.get("_mover_data")
                    if isinstance(_mv_blk, dict) and _mv_blk.get("pct") is not None:
                        source["baseline_pct"] = _mv_blk.get("pct")
                    _th_blk = qi.get("_theme_data")
                    if isinstance(_th_blk, dict) and _th_blk.get("agg_pct") is not None:
                        source["baseline_pct"] = _th_blk.get("agg_pct")

                    # GIFT-GRIP-PROOF VERDICT (XG-W3, charter §0). Every
                    # emission carries its verdict in metadata. RECORD-ONLY
                    # unless config value_gate.enforce is true — see
                    # `stamp_value_gate`.
                    _would_block = stamp_value_gate(
                        source,
                        headline=qi.get("headline") or "",
                        body=qi.get("body") or "",
                        kind=qi.get("type") or "signal",
                        has_media=bool(media),
                        numbers_whitelist=qi.get("numbers_whitelist") or (),
                        cfg=cfg,
                    )
                    if _would_block:
                        counts["value_gate_would_block"] = (
                            counts.get("value_gate_would_block", 0) + 1
                        )
                        _k = qi.get("type") or "signal"
                        if _value_gate_enforced(cfg, _k):
                            counts["value_gate_blocked"] = (
                                counts.get("value_gate_blocked", 0) + 1
                            )
                            continue
                        # Recorded, not policed. Counted separately so the two
                        # never read as one number: an unmeasured kind that
                        # abstains is a REQUEST FOR EVIDENCE, not a rejection.
                        if not value_gate_kind_is_measured(cfg, _k):
                            counts["value_gate_unmeasured_kind"] = (
                                counts.get("value_gate_unmeasured_kind", 0) + 1
                            )

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
                    elif result_code in ("duplicate", "cross_account_duplicate"):
                        counts["skipped_dupe"] += 1
                    elif result_code == "cap_exceeded":
                        counts["skipped_cap"] += 1
                    elif result_code.startswith("invalid:"):
                        log.warning("outbox.emit_from_content_plan: invalid item: %s", result_code)
                        counts["skipped_invalid"] += 1

                except Exception as exc:  # noqa: BLE001
                    log.warning("outbox.emit_from_content_plan: per-item error: %s", exc)
                    counts["skipped_invalid"] += 1

    # ONE annotation per emit, whatever the refusal count (contract §Emit).
    #
    # BARE PRINT, "::" FIRST ON THE LINE, flush=True. This module's logger
    # prefixes every record ("WARNING ::error …"), and GitHub silently drops a
    # workflow command that does not start the line — the failure mode that
    # shipped dead five times before #3587 swept 69 sites. stdout is block-
    # buffered when piped in CI, so an unflushed annotation can be lost with the
    # step's tail. tests/test_gh_annotation_line_start.py pins both.
    if counts["skipped_not_llm"] > 0:
        _breakdown = ", ".join(
            f"{k}={v}" for k, v in sorted(_not_llm_modes.items()))
        if _lane_mute:
            print(
                f"::error title=marketing_copy_lane_mute::"
                f"{counts['skipped_not_llm']} planned-kind post(s) NOT emitted for "
                f"{as_of}: the model copy lane never ran (plan copy mode="
                f"{_plan_copy_mode or 'none'}) and copywriter.llm.required is on, so "
                f"template prose was refused instead of posted. Check "
                f"MARKETING_LLM_ENABLED + the LLM credentials on the governor step. "
                f"[{_breakdown}]",
                flush=True,
            )
        else:
            print(
                f"::error title=marketing_copy_not_llm::"
                f"{counts['skipped_not_llm']} planned-kind post(s) NOT emitted for "
                f"{as_of}: the writer lane ran but these items carry no model copy "
                f"(copywriter.llm.required). [{_breakdown}]",
                flush=True,
            )

    # UNEMITTABLE SLOT LABELS — one annotation per emit, and only for the
    # families that can never resolve. A `D2`..`D7` skip is the designed forward
    # ladder (regenerated nightly, never emitted) and must NOT raise an alarm, or
    # this fires every night on ~800 items and stops being read. A non-day label
    # means a producer built posts on a slot this function refuses by
    # construction — the movers desk shipped MOVER-NN/THEME-NN for two weeks and
    # published nothing, and the silence was the reason nobody saw it.
    #
    # `CONF` IS EXCLUDED FROM THE ALARM, NOT FROM THE COUNT (adversarial review,
    # 2026-07-31). Confluence is deliberately, permanently unemittable: it slots
    # CONF-NN and content_studio's own reserve comment says so in as many words
    # ("this lane CANNOT publish as built … deliberately NOT fixed by relabelling
    # the slot", `_confluence_census`), because publication has to be earned on
    # evidence rather than on a prefix change. So this warning fired EVERY
    # nightly on a state nobody intends to change — which is the definition of
    # alarm fatigue, and it trains the operator to scroll past the annotation on
    # the night a REAL lane (a new MOVER-/THEME-/bare label) goes dark. It stays
    # in `skipped_slot_by_family` and therefore in the activity row, where the
    # count is a fact rather than an alarm.
    _unemittable = {
        fam: n for fam, n in counts["skipped_slot_by_family"].items()
        if not (len(fam) >= 2 and fam[0] == "D" and fam[1:].isdigit())
        and fam not in _EXPECTED_UNEMITTABLE_FAMILIES
    }
    if _unemittable:
        _fam_breakdown = ", ".join(
            f"{k}={v}" for k, v in sorted(_unemittable.items()))
        print(
            f"::warning title=marketing_unemittable_slots::"
            f"{sum(_unemittable.values())} plan item(s) for {as_of} carry a slot "
            f"label the outbox can never emit — emit takes {day_prefix}- only, so "
            f"these lanes publish NOTHING as built. [{_fam_breakdown}]",
            flush=True,
        )

    _append_activity(root, {
        "at": ts_now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lane": "emit",
        "as_of": as_of,
        "cap": cap,
        "llm_required": _require_llm,
        "not_llm_modes": _not_llm_modes,
        **{k: v for k, v in counts.items() if k != "by_account"},
        "by_account": counts["by_account"],
    })

    return counts
