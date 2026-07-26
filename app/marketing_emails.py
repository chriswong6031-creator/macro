"""app/marketing_emails.py — welcome mail + campaign drain (SEE W4, masterplan §4 W4).

Three legs on one in-process sweeper, all marketing-class, all default OFF:

  ``sweep_welcome``     behaviour-triggered welcome on signup (PIN §7.6)
  ``drain_campaigns``   send a queued ``email_campaigns`` row to its segment (PIN §7.9)
  ``drain_parked``      finish the rows W3's fail-closed suppression check parked

Shape is W3's (``app/billing_emails.py``): env-gated, registered from ``app/main.py``, an
asyncio loop that sleeps FIRST, each wake wrapped, work done in ``asyncio.to_thread``, and
cursor-free — the eligible set is re-derived every wake and ``email_log``'s unique
``idem_key`` decides what has already gone out, so a restart mid-sweep costs nothing.

THE BLAST RADIUS, AND THE THREE BOUNDS ON IT
--------------------------------------------
"Every account with no ``welcome:{user_id}`` ledger row" is, on the first run, EVERY
ACCOUNT THAT HAS EVER EXISTED. The idempotency key protects against sending twice; it does
nothing whatsoever about sending once to ten thousand people who signed up last year. That
is the single largest risk in this lane, so the eligible set is bounded three ways and the
first two are hard gates, not tuning:

1. **An activation floor that must be set by hand.** ``MAIL_WELCOME_AFTER`` is an ISO
   date/time; only accounts created strictly after it are ever candidates. **Unset means
   ZERO candidates** — not "everyone", not "since boot". Arming ``MAIL_WELCOME_ENABLED``
   without also naming the day the feature went live therefore sends nothing at all, which
   is the correct behaviour for a half-finished rollout and the one that cannot be
   regretted.
2. **A lookback ceiling.** The floor is combined with ``now - MAIL_WELCOME_LOOKBACK_HOURS``
   (default 72h) and the LATER of the two wins. So even a correctly-set floor cannot mail
   a year of backlog if the sweeper was off for a year: a welcome email three months after
   signup is worse than no welcome email, and this makes that unsendable rather than
   merely unlikely.
3. **A per-wake cap.** :data:`_WELCOME_MAX_PER_WAKE` bounds one wake's sends regardless.

:func:`welcome_window` returns the pair actually in force and is what the test asserts;
nothing computes the bound a second time.

TWO PLANES, ONE SEGMENT DEFINITION
----------------------------------
This module runs in macro-api, which holds a **service-role** key and no Management PAT,
so it cannot run the admin console's SQL. It assembles the roster from the GoTrue admin
list + PostgREST instead. Membership is NOT re-derived here: ``app/email_segments.py``
declares each segment once, and this module evaluates the Python half of that same pair.

SUPPRESSION IS CHECKED AT SEND TIME, NOT AT QUEUE TIME
------------------------------------------------------
Nothing here pre-filters unsubscribers out of a segment and calls that compliance.
``mailer.send(cls='marketing')`` re-reads ``email_suppression`` and
``email_prefs.marketing_opt_out`` for every single recipient, immediately before the relay
is touched, and is fail-closed if that read errors. A campaign queued at 09:00 and drained
at 09:40 cannot reach someone who unsubscribed at 09:20. The counters report what actually
happened — ``skipped_n`` counts the people we did not mail, and a campaign that skips half
its segment says so.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Collection
from datetime import datetime, timedelta, timezone
from typing import Any

from app import email_segments, mailer

log = logging.getLogger("macro.marketing_emails")


class SegmentUnavailable(RuntimeError):
    """A read the segment depends on failed, so membership is UNKNOWN, not empty.

    The distinction is the whole point. Both reads used to fail open — a roster page error
    ``break``ed out of the loop and a failed entitlements read returned ``{}`` — and both
    failures are silent and plausible: 199 of 600 people mailed and the campaign marked
    ``done``, or every user normalising to ``tier='free'`` so a free-only campaign reaches
    the Pro subscribers it was written to exclude. An idem_key claimed for the wrong
    audience cannot be taken back, so a partial read must abort, never complete.
    """


class RosterUnavailable(SegmentUnavailable):
    """A page of the GoTrue admin roster could not be read."""


class EntitlementsUnavailable(SegmentUnavailable):
    """``user_entitlements`` could not be read, so nobody's tier is known."""

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://fsldfzlxyavsuwqbceod.supabase.co").rstrip("/")

_TRUTHY = ("1", "true", "yes", "on")
_DEFAULT_SITE_BASE = "https://www.mastermind-x.com"

# Bounds. Deliberately module constants rather than env knobs: an operator who needs a
# bigger blast radius should have to change code and get it reviewed.
_WELCOME_MAX_PER_WAKE = 200
_CAMPAIGN_MAX_PER_WAKE = 500
_PARKED_LIMIT = 500
_ROSTER_PAGE = 200
_ROSTER_MAX_PAGES = 25          # 5,000 accounts — the default scan depth
#: The campaign drain scans deeper, because for IT the page cap is not a work bound but an
#: AUDIENCE cap: a segment whose members sit past the ceiling can never be reached, and
#: the drain would mark itself `done` having never seen them. 50,000 accounts is the whole
#: user base with room to spare, the scan stops early the moment it has a full wake's
#: worth of unmailed members, and hitting the ceiling is reported (:func:`roster_scan`
#: returns ``truncated``) instead of being swallowed by a ``break``.
_CAMPAIGN_MAX_PAGES = 250
_ABORT_CHECK_EVERY = 25         # re-read campaign status this often mid-send

DEFAULT_LOOKBACK_HOURS = 72
DEFAULT_THROTTLE_PER_MIN = 30
MARKETING_INTERVAL_SEC = 900    # four wakes an hour; the welcome window is 72h wide

#: Splits the EN half of a campaign body from the 中文 half. On its own line. Chosen to be
#: unmistakable in a plain textarea and impossible to type by accident, unlike ``---``.
ZH_DELIM = "===zh==="


def _site_base() -> str:
    """Same env var as billing_emails._site_base, read independently.

    Importing app.billing_emails for two lines would drag app.billing (and Stripe) into
    every process that only wants to send a welcome email.
    """
    return (os.environ.get("MAIL_SITE_BASE") or _DEFAULT_SITE_BASE).strip().rstrip("/")


# --------------------------------------------------------------------------- #
# Env gates — all read at CALL time (mailer._env idiom), all default OFF
# --------------------------------------------------------------------------- #
def _on(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _TRUTHY


def marketing_enabled() -> bool:
    """Master switch for this module. OFF unless explicitly armed.

    Unlike W3's ``MAIL_BILLING_ENABLED`` (default ON, because a receipt is owed the moment
    a relay exists), marketing defaults OFF: nobody is owed a broadcast, and the failure
    mode of an accidental ON is mail nobody asked for.
    """
    return _on("MAIL_MARKETING_ENABLED")


def welcome_enabled() -> bool:
    return _on("MAIL_WELCOME_ENABLED")


def campaigns_enabled() -> bool:
    return _on("MAIL_CAMPAIGNS_ENABLED")


def throttle_per_min() -> int:
    try:
        return max(1, min(600, int(os.environ.get("MAIL_THROTTLE_PER_MIN") or DEFAULT_THROTTLE_PER_MIN)))
    except ValueError:
        return DEFAULT_THROTTLE_PER_MIN


def _lookback_hours() -> int:
    try:
        return max(1, min(24 * 30, int(os.environ.get("MAIL_WELCOME_LOOKBACK_HOURS")
                                       or DEFAULT_LOOKBACK_HOURS)))
    except ValueError:
        return DEFAULT_LOOKBACK_HOURS


def _parse_dt(value: Any) -> datetime | None:
    """ISO8601 (date or datetime, Z or offset) -> aware UTC datetime, else None."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def welcome_window(now: datetime | None = None) -> tuple[datetime | None, datetime]:
    """``(floor, now)`` — the exact bound in force, or ``(None, now)`` meaning NO sends.

    The floor is the LATER of the operator's activation timestamp and the lookback
    ceiling, so both bounds bind at once and neither can be defeated by the other. A
    missing or unparseable ``MAIL_WELCOME_AFTER`` yields ``None``: unparseable is treated
    exactly like unset, because a typo'd date must not silently become "the epoch".
    """
    now = now or datetime.now(timezone.utc)
    after = _parse_dt(os.environ.get("MAIL_WELCOME_AFTER"))
    if after is None:
        return None, now
    ceiling = now - timedelta(hours=_lookback_hours())
    return max(after, ceiling), now


# --------------------------------------------------------------------------- #
# Data access — service-role PostgREST + the GoTrue admin list
# --------------------------------------------------------------------------- #
def _key() -> str:
    return mailer.SUPABASE_SERVICE_ROLE_KEY


def _pg(method: str, path: str, body: Any = None, prefer: str | None = None,
        timeout: int = 8) -> Any:
    key = _key()
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY unset")
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def _auth_page(page: int, per_page: int = _ROSTER_PAGE) -> list[dict]:
    """One page of ``auth.users`` through the GoTrue admin API.

    PostgREST exposes ``public`` only, so the auth schema is unreachable from the REST
    lane; this is the supported way to read the roster with a service-role key. Answers
    ``{"users": [...]}``, but a bare list is accepted too — the shape has moved between
    GoTrue versions and a roster reader should not break on a wrapper.
    """
    key = _key()
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY unset")
    url = f"{SUPABASE_URL}/auth/v1/admin/users?page={int(page)}&per_page={int(per_page)}"
    req = urllib.request.Request(
        url, headers={"apikey": key, "Authorization": f"Bearer {key}",
                      "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read() or b"{}")
    if isinstance(payload, list):
        return payload
    return list((payload or {}).get("users") or [])


def _mailable(row: dict) -> dict | None:
    """A GoTrue row reduced to the roster shape, or None when it is not a recipient."""
    norm = {
        "email": (row.get("email") or "").strip(),
        "deleted_at": row.get("deleted_at"),
        "is_anonymous": row.get("is_anonymous"),
        "banned_until": row.get("banned_until"),
    }
    if not email_segments.base_match(norm):
        return None
    return {"user_id": str(row.get("id") or ""), "email": norm["email"],
            "created_at": _parse_dt(row.get("created_at"))}


def roster_scan(*, max_pages: int = _ROSTER_MAX_PAGES,
                newer_than: datetime | None = None,
                start_page: int = 1,
                stop_after: int | None = None,
                skip_ids: Collection[str] = (),
                keep: Any = None) -> tuple[list[dict], bool]:
    """``(rows, complete)`` — mailable accounts, newest first.

    ``complete`` is True only when the scan reached the **end of the roster** (an empty or
    short page), i.e. there is provably nobody after these. It is False when the scan
    stopped early for any reason: the caller's quota filled, or the page ceiling was hit.

    ``newer_than`` is an EARLY EXIT, never the correctness gate: GoTrue lists newest-first,
    so once a whole page holds nothing inside the window there is nothing further to find.
    Every returned row is filtered against the bound regardless, so a future GoTrue that
    ordered differently would cost pages, not correctness.

    Two things this does NOT do any more, both of them ways a caller was previously lied
    to about how much of the roster it had seen:

    * **A failed page raises.** It used to ``break``, so page 2 of 3 failing produced a
      short list indistinguishable from a short roster — the campaign drain then mailed
      199 of 600 people and marked itself ``done``. "Could not read" is not "there is
      nobody else".
    * **Hitting the page ceiling is REPORTED and LOGGED.** That is the 5,000-account cap
      made visible; the caller decides whether it is a work bound (the welcome window is
      72h wide and re-derived every wake) or an audience cap it must not mistake for
      exhaustion (a campaign).

    ``skip_ids``, ``start_page``, ``keep`` and ``stop_after`` are the paging seam: a
    caller that already knows whom it has processed hands them in, the scan walks PAST
    them into the part of the roster no wake has reached yet, and it stops as soon as it
    has a wake's worth rather than materialising the whole user base.
    """
    out: list[dict] = []
    skip = set(skip_ids or ())
    first = max(1, int(start_page))
    last = first + max(1, max_pages) - 1
    for page in range(first, last + 1):
        try:
            rows = _auth_page(page)
        except Exception as exc:  # noqa: BLE001
            log.warning("marketing: roster page %d failed (%s)", page, type(exc).__name__)
            raise RosterUnavailable(f"page {page}: {type(exc).__name__}") from None
        if not rows:
            return out, True
        hit = 0
        for raw in rows:
            row = _mailable(raw)
            if not row:
                continue
            if newer_than is not None:
                if row["created_at"] is None or row["created_at"] <= newer_than:
                    continue
                hit += 1
            if row["user_id"] in skip:
                continue
            if keep is not None and not keep(row):
                continue
            out.append(row)
            if stop_after is not None and len(out) >= stop_after:
                return out, False       # a full quota — there may well be more behind it
        if newer_than is not None and hit == 0:
            return out, True
        if len(rows) < _ROSTER_PAGE:
            return out, True
    log.warning("marketing: roster scan stopped at its %d-page ceiling (%d accounts, from "
                "page %d) with the roster not yet exhausted — anyone past that point was "
                "NOT seen this wake", max_pages, max_pages * _ROSTER_PAGE, first)
    return out, False


def roster(*, max_pages: int = _ROSTER_MAX_PAGES,
           newer_than: datetime | None = None) -> list[dict]:
    """Mailable accounts, newest first. :func:`roster_scan` without the completeness flag,
    for the callers that genuinely only want a bounded sample of the top of the roster."""
    return roster_scan(max_pages=max_pages, newer_than=newer_than)[0]


def _entitlements() -> dict[str, dict]:
    """``{user_id: {tier, status}}`` for everyone who has ever touched billing.

    RAISES on a failed read. It used to answer ``{}``, which is not "nobody has an
    entitlement" — it is "we do not know" wearing the costume of an answer, and
    :func:`email_segments.normalize` turns an unknown tier into ``free``. One transient
    PostgREST blip therefore rewrote a 20-free/20-paid roster as 40-free/0-paid, and a
    campaign addressed to free users went to the paying subscribers it was written to
    leave alone, with every idem_key claimed and the campaign marked ``done``.
    """
    try:
        rows = _pg("GET", "user_entitlements?select=user_id,tier,status&limit=10000") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing: entitlements read failed (%s)", type(exc).__name__)
        raise EntitlementsUnavailable(type(exc).__name__) from None
    return {str(r.get("user_id")): r for r in rows if r.get("user_id")}


def segment_page(segment: str, *, limit: int = _CAMPAIGN_MAX_PER_WAKE,
                 skip_ids: Collection[str] = (), start_page: int = 1,
                 max_pages: int = _ROSTER_MAX_PAGES) -> tuple[list[dict], bool]:
    """``(members, exhausted)`` for one wake's slice of ``segment``.

    ``exhausted`` is the only honest basis for calling a campaign finished: True means the
    scan reached the END of the roster, so there is provably nobody left after these.
    False means the wake filled its quota, or stopped at the page ceiling, or both — in
    every one of those cases there may be more people, and marking ``done`` would strand
    them permanently (the segment is re-derived each wake, so a campaign that says ``done``
    is never looked at again).

    Note what is NOT done here: suppression and opt-out are not read, so
    ``marketing_eligible`` resolves to the whole mailable roster on this plane. That is
    deliberate and it is the safe direction — ``mailer.send`` re-reads both for every
    recipient at send time and is fail-closed, so the people this list over-includes are
    exactly the people the send will refuse and count as skipped. Pre-filtering here would
    add a second, staler copy of a compliance decision that already has an authority.

    The entitlements read is skipped entirely for a segment whose rule does not reference
    the billing join (``all``, ``marketing_eligible``), so an unavailable
    ``user_entitlements`` cannot stop a send whose audience it could not have changed.
    """
    ents = _entitlements() if email_segments.needs_entitlements(segment) else {}
    tiers: dict[str, dict] = {}

    def _keep(row: dict) -> bool:
        ent = ents.get(row["user_id"]) or {}
        norm = email_segments.normalize({"tier": ent.get("tier"), "status": ent.get("status")})
        if not email_segments.matches(segment, norm):
            return False
        tiers[row["user_id"]] = norm
        return True

    rows, complete = roster_scan(max_pages=max_pages, start_page=start_page,
                                 skip_ids=skip_ids, stop_after=limit, keep=_keep)
    members = [{**r, "tier": tiers[r["user_id"]]["tier"], "status": tiers[r["user_id"]]["status"]}
               for r in rows]
    return members, complete


def segment_members(segment: str, *, limit: int = _CAMPAIGN_MAX_PER_WAKE) -> list[dict]:
    """Everyone in ``segment``, up to ``limit``. :func:`segment_page` for callers that
    only want the members and can live with the default scan depth."""
    return segment_page(segment, limit=limit)[0]


# --------------------------------------------------------------------------- #
# Unsubscribe URLs — TWO of them, and they are not interchangeable
# --------------------------------------------------------------------------- #
def unsub_page_url(identity: str) -> str:
    """The link a HUMAN clicks in the footer (PIN §6.7). A page, so it can explain itself
    and so nothing mutates until the reader presses the button."""
    tok = mailer.unsub_token(identity)
    return f"{_site_base()}/unsubscribe.html?t={urllib.parse.quote(tok)}" if tok else ""


def unsub_api_url(identity: str) -> str:
    """The URI that goes in ``List-Unsubscribe`` (RFC 8058).

    A mail client doing one-click POSTs to this URI directly — it cannot run the page's
    JavaScript — so it must be the API route, not the HTML page. Pointing the header at
    ``/unsubscribe.html`` would make Gmail's one-click button POST at a static file and
    fail silently, which is worse than not offering one-click at all.
    """
    tok = mailer.unsub_token(identity)
    return f"{_site_base()}/api/email/unsubscribe?t={urllib.parse.quote(tok)}" if tok else ""


def _marketing_headers(identity: str) -> dict:
    url = unsub_api_url(identity)
    return {"unsubscribe_url": url} if url else {}


# --------------------------------------------------------------------------- #
# Welcome (PIN §7.6)
# --------------------------------------------------------------------------- #
WELCOME_TEMPLATE = "welcome"


def welcome_message(identity: str) -> tuple[str, str, str]:
    """(subject, html, text) for the welcome email. PIN §7.6, verbatim slots.

    Three one-line links rather than a slip, one CTA, no fine print. The lede says what
    the product does for the reader in one sentence — not what tier they are on, which
    they already know and cannot act on.
    """
    base = _site_base()
    blocks = [
        {"en": "Your account is ready. Mastermind reads the macro tape — rates, growth, "
               "liquidity, and what the market is actually paying for — and tells you "
               "where that leaves you.",
         "zh": "账户已经开通。Mastermind 追踪宏观走势——利率、增长、流动性，以及市场当下真正在买什么"
               "——并告诉你这对你意味着什么。"},
        {"kind": "links",
         "en": [("The Terminal — live charts and your watchlist", f"{base}/terminal.html"),
                ("The dashboards — where the macro picture stands today", f"{base}/macro.html"),
                ("The research desk — the longer write-ups", f"{base}/research.html")],
         "zh": [("终端——实时图表与你的自选股", f"{base}/terminal.html"),
                ("仪表盘——今天的宏观全景", f"{base}/macro.html"),
                ("研究台——更长的深度报告", f"{base}/research.html")]},
        {"kind": "button", "en": "Open the Terminal", "zh": "打开终端",
         "url": f"{base}/terminal.html"},
    ]
    html, text = mailer.render_email(
        "You're in", "欢迎加入", blocks,
        eyebrow="WELCOME",
        preheader="Three places worth opening first.",
        why_en="You received this because you created a Mastermind account.",
        why_zh="你收到这封邮件，是因为你注册了 Mastermind 账户。",
        unsubscribe_url=unsub_page_url(identity),
    )
    return "You're in · 欢迎加入", html, text


def _welcomed() -> set[str]:
    """The user ids that already hold a ``welcome:`` ledger row.

    One query, so the per-wake cap can be spent on people who have NOT been welcomed. It
    used to take the oldest 200 of the window and dedupe afterwards inside
    ``mailer.send``, which is starvation dressed as a cap: with more than 200 signups in
    the window, every wake spent its whole budget re-offering the same already-welcomed
    200 and collecting 200 ``duplicate``s, while accounts 201+ waited until the 72h
    lookback expired them out of the window entirely — a welcome email that never arrives.

    An unreadable ledger falls back to no dedup rather than to no sends: ``mailer.send``
    is still idempotent, so the cost is a wasted wake, not a double send.
    """
    try:
        rows = _pg("GET", "email_log?select=idem_key&idem_key=like."
                          f"{urllib.parse.quote('welcome:*', safe='')}&limit=20000") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing: welcome dedup preload failed (%s) — this wake may spend its "
                    "budget on duplicates", type(exc).__name__)
        return set()
    return {str(r.get("idem_key") or "").split(":", 1)[1]
            for r in rows if str(r.get("idem_key") or "").startswith("welcome:")}


def welcome_candidates(now: datetime | None = None) -> list[dict]:
    """Accounts created inside the window that have NOT been welcomed yet.

    Dedup happens BEFORE the cap, deliberately — see :func:`_welcomed`.
    """
    floor, now = welcome_window(now)
    if floor is None:
        return []
    rows = roster(newer_than=floor)
    already = _welcomed()
    rows = [r for r in rows if r["user_id"] not in already]
    rows.sort(key=lambda r: r["created_at"] or now)      # oldest first: closest to expiring
    return rows[:_WELCOME_MAX_PER_WAKE]


def sweep_welcome(*, now: datetime | None = None) -> dict:
    """Send the welcome email to every account inside the window. Never raises."""
    out = {"scanned": 0, "sent": 0, "duplicate": 0, "skipped": 0,
           "skipped_no_smtp": 0, "failed": 0}
    if not (marketing_enabled() and welcome_enabled()):
        return out
    if not _relay_ready("welcome", out):
        return out
    floor, now = welcome_window(now)
    if floor is None:
        log.warning("marketing: welcome sweep did nothing — MAIL_WELCOME_AFTER is unset. "
                    "Set it to the day the feature went live (an ISO date); with no floor "
                    "the eligible set would be every account ever created.")
        return out
    log.info("marketing: welcome window is created_at > %s (lookback %dh)",
             floor.isoformat(), _lookback_hours())

    try:
        rows = welcome_candidates(now)
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing: welcome candidate query failed (%s)", type(exc).__name__)
        out["failed"] += 1
        return out

    for row in rows:
        out["scanned"] += 1
        try:
            user_id, to_email = row["user_id"], row["email"]
            if not (user_id and to_email):
                out["skipped"] += 1
                continue
            subject, html, text = welcome_message(user_id)
            status = mailer.send(
                template=WELCOME_TEMPLATE, cls="marketing", to_email=to_email,
                subject=subject, html=html, text=text,
                idem_key=f"welcome:{user_id}",
                user_id=user_id, headers=_marketing_headers(user_id))
            _tally(out, status)
            _pace(status)
        except Exception as exc:  # noqa: BLE001 — one bad row must not end the sweep
            log.warning("marketing: welcome row failed (%s)", type(exc).__name__)
            out["failed"] += 1
    if out["scanned"]:
        log.info("marketing: welcome sweep %s", out)
    return out


def _bucket(status: str) -> str:
    """Which census column one mailer status belongs in.

    'skipped_no_smtp' HAS ITS OWN COLUMN and is emphatically not a send. It used to be
    folded into ``sent``, and that single line was the most expensive thing in this
    module: ``mailer.send`` writes a TERMINAL ledger row for it, so the idem_key is burnt
    and a later retry answers ``duplicate`` without sending — meaning arming the welcome
    leg while the relay is off would have destroyed the welcome email for every account in
    the window while reporting ``sent: N``. The refusal in :func:`_relay_ready` is the
    real fix; this column is how the census stops lying about what happened either way.

    'queued' counts as SKIPPED — it is W3's fail-closed park, and the parked drain owns it
    from there.
    """
    if status == "duplicate":
        return "duplicate"
    if status == "sent":
        return "sent"
    if status == "skipped_no_smtp":
        return "skipped_no_smtp"
    if status in ("suppressed", "queued"):
        return "skipped"
    return "failed"


def _tally(out: dict, status: str) -> str:
    """Record one mailer status in ``out``; returns the bucket it landed in."""
    b = _bucket(status)
    out[b] = out.get(b, 0) + 1
    return b


#: Statuses that mean the relay was actually reached, so the pacer owes them a gap.
_TRANSMITTED = ("sent", "failed")

#: Legs already told, once, that the relay is unconfigured. A sweeper wakes four times an
#: hour forever; the first line is the operator's signal and the rest are noise.
_UNCONFIGURED_LOGGED: set[str] = set()


def _relay_ready(leg: str, out: dict) -> bool:
    """False (and ``out`` marked) when there is no relay, so the leg must not run.

    THE ACUTE ONE. Production has SMTP off today. Without this, arming the welcome leg
    would walk the window, claim ``welcome:{user_id}`` for every account in it, PATCH each
    row to the terminal ``skipped_no_smtp``, and report success — after which those people
    can never be welcomed, because the key is spent and ``drain_parked`` only ever looked
    for ``status='queued'``. Refusing to start is the only version of this that is
    recoverable: nothing is claimed, so the day the relay lands the window is still intact.
    """
    if mailer.is_configured():
        return True
    out["not_configured"] = True
    if leg not in _UNCONFIGURED_LOGGED:
        _UNCONFIGURED_LOGGED.add(leg)
        log.warning("marketing: the %s leg is armed but there is no relay (MAIL_SMTP_* / "
                    "MAIL_FROM unset) — refusing to run. Nothing was claimed, so no "
                    "message was burnt; it will run for the same people once mail is "
                    "configured.", leg)
    return False


def _pace(status: str = "sent") -> None:
    """Wait the shared inter-message gap after a message that reached the relay.

    ONE pacer for ALL THREE legs. It used to exist only inside the campaign drain, so a
    single wake could fire 200 welcomes and 500 parked rows back to back, ungated — up to
    700 SMTP connections in a few seconds, which every relay reads as a spam burst from a
    compromised account. Sharing it also changes the arithmetic the runbook quotes: the
    ceiling is now ``MAIL_THROTTLE_PER_MIN`` × 60 messages an hour whatever the wake
    interval is, instead of the interval multiplying the two unthrottled legs.

    Only a status that actually touched the transport is paced. Pacing a ``duplicate`` or
    a ``suppressed`` would throttle bookkeeping, which costs wall-clock and protects
    nothing.
    """
    if status not in _TRANSMITTED:
        return
    gap = 60.0 / throttle_per_min()
    if gap:
        time.sleep(gap)


# --------------------------------------------------------------------------- #
# Campaigns (PIN §7.9)
# --------------------------------------------------------------------------- #
CAMPAIGN_TEMPLATE = "campaign"


#: :data:`ZH_DELIM` ON ITS OWN LINE, which is what the docstring always promised and what
#: ``admin/email_center.py::_compose`` always writes. A bare substring ``partition`` took
#: the delimiter anywhere, so an English paragraph that merely MENTIONED ``===zh===``
#: truncated the English body at that word and shipped the remainder as the 中文 half.
_ZH_SPLIT = re.compile(rf"^[ \t]*{re.escape(ZH_DELIM)}[ \t]*$", re.M)


def split_langs(text: str) -> tuple[str, str]:
    """``body_md`` -> (english, chinese) on a :data:`ZH_DELIM` LINE.

    No delimiter means the operator wrote one language; it is used for both halves rather
    than shipping an empty 中文 section, because a blank half reads as a broken email.
    """
    raw = str(text or "")
    parts = _ZH_SPLIT.split(raw, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return raw.strip(), raw.strip()


def _blocks(body: str) -> list[dict]:
    """The deliberately small markdown subset the campaign shell accepts.

    Paragraphs separated by blank lines, and a line that is exactly ``[Label](url)``
    becomes THE call to action. At most one button survives (PIN §7.9: at most one CTA) —
    a later one is dropped rather than rendered, because two primary buttons in one email
    is a design failure the composer should not be able to ship.
    """
    out: list[dict] = []
    seen_button = False
    for para in [p.strip() for p in str(body or "").split("\n\n")]:
        if not para:
            continue
        one = " ".join(para.split())
        if one.startswith("[") and one.endswith(")") and "](" in one:
            label, _, url = one[1:-1].partition("](")
            if not seen_button and label.strip() and url.strip().startswith(("http://", "https://")):
                seen_button = True
                out.append({"kind": "button", "label": label.strip(), "url": url.strip()})
            continue
        out.append({"kind": "p", "text": para})
    return out


#: How ``admin/email_center.py::_compose`` joins the two subject halves into the single
#: ``subject`` column, and therefore how they are taken apart again.
SUBJECT_SEP = " · "


def campaign_message(campaign: dict, identity: str) -> tuple[str, str, str]:
    """(subject, html, text) for one recipient of a campaign."""
    subject = " ".join(str(campaign.get("subject") or "").split()) or "Mastermind"
    # rpartition, not partition: the 中文 half is the LAST field, so an English subject
    # that itself contains " · " splits at its own separator and ships half a headline in
    # English and the other half labelled as Chinese. The composer also refuses to store a
    # half containing the separator (email_center._subject_error) — this is the second
    # belt, for a row written before that check existed or edited in the table editor.
    subj_en, _, subj_zh = subject.rpartition(SUBJECT_SEP)
    if not subj_en:                       # no separator at all: one language, used for both
        subj_en, subj_zh = subj_zh, ""
    en_body, zh_body = split_langs(campaign.get("body_md"))
    en, zh = _blocks(en_body), _blocks(zh_body)

    blocks: list[dict] = []
    for i in range(max(len(en), len(zh))):
        a = en[i] if i < len(en) else {"kind": "p", "text": ""}
        b = zh[i] if i < len(zh) else {"kind": "p", "text": ""}
        if a["kind"] == "button" or b["kind"] == "button":
            blocks.append({"kind": "button",
                           "en": a.get("label") or b.get("label") or "",
                           "zh": b.get("label") or a.get("label") or "",
                           "url": a.get("url") or b.get("url") or ""})
        else:
            blocks.append({"en": a.get("text", ""), "zh": b.get("text", "")})

    html, text = mailer.render_email(
        subj_en or subject, subj_zh or subj_en or subject, blocks,
        eyebrow="NEWS",
        why_en="You received this because you hold a Mastermind account.",
        why_zh="你收到这封邮件，是因为你拥有 Mastermind 账户。",
        unsubscribe_url=unsub_page_url(identity),
    )
    return subject, html, text


def _campaign(campaign_id: str) -> dict | None:
    rows = _pg("GET", f"email_campaigns?id=eq.{urllib.parse.quote(campaign_id, safe='')}"
                      "&select=id,subject,body_md,segment,status,queued_n,sent_n,skipped_n,failed_n")
    return (rows or [None])[0]


def _patch_campaign(campaign_id: str, patch: dict) -> None:
    _pg("PATCH", f"email_campaigns?id=eq.{urllib.parse.quote(campaign_id, safe='')}",
        body=patch, prefer="return=minimal")


def _already_sent(campaign_id: str) -> set[str]:
    """The idem_keys this campaign has already claimed.

    One query instead of re-offering every recipient to ``mailer.send`` and taking a
    'duplicate' per head: resuming a half-drained campaign should cost one round trip, not
    one per person already mailed.
    """
    try:
        rows = _pg("GET", "email_log?select=idem_key&idem_key=like."
                          f"{urllib.parse.quote(f'campaign:{campaign_id}:*', safe='')}&limit=20000") or []
    except Exception as exc:  # noqa: BLE001
        log.debug("marketing: sent-key preload failed (%s)", type(exc).__name__)
        return set()
    return {str(r.get("idem_key")) for r in rows}


def drain_campaigns() -> dict:
    """Send every queued campaign to its segment, throttled. Never raises."""
    out = {"campaigns": 0, "sent": 0, "duplicate": 0, "skipped": 0,
           "skipped_no_smtp": 0, "failed": 0}
    if not (marketing_enabled() and campaigns_enabled()):
        return out
    if not _relay_ready("campaign", out):
        return out
    try:
        rows = _pg("GET", "email_campaigns?status=in.(queued,sending)"
                          "&select=id,subject,body_md,segment,status"
                          "&order=created_at.asc&limit=5") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing: campaign query failed (%s)", type(exc).__name__)
        out["failed"] += 1
        return out

    for camp in rows:
        out["campaigns"] += 1
        try:
            _drain_one(camp, out)
        except Exception as exc:  # noqa: BLE001
            log.warning("marketing: campaign %s failed (%s)", camp.get("id"), type(exc).__name__)
            out["failed"] += 1
    return out


def _resume_page(processed: int) -> int:
    """Which GoTrue page a wake should START on, given how many members are already done.

    The cursor this lane does not have a column for, derived from the one it does: every
    recipient the drain has offered holds an ``email_log`` row, so ``len(done)`` IS the
    progress marker. Members are drawn in roster order and an account can only ever be
    filtered OUT of that order, so the Nth member always sits at account index ≥ N — which
    makes ``1 + (N-1)//page`` a page that provably cannot be past the first unprocessed
    person. Deliberately conservative: overlapping a page costs one wasted read (the
    skip-set drops it), skipping one costs somebody their email.
    """
    return 1 + max(0, int(processed) - 1) // _ROSTER_PAGE


def _drain_one(camp: dict, out: dict) -> None:
    cid = str(camp.get("id") or "")
    if not cid:
        return
    segment = camp.get("segment") or email_segments.DEFAULT_KEY
    try:
        email_segments.get(segment)
    except KeyError:
        log.warning("marketing: campaign %s names unknown segment %r — aborted", cid, segment)
        _patch_campaign(cid, {"status": "aborted"})
        return

    done = _already_sent(cid)
    seen = {k.rsplit(":", 1)[-1] for k in done}
    try:
        # Walk PAST everyone this campaign has already offered, so wake 2 reaches people
        # wake 1 never saw. Before this the drain re-read the same first 500 members every
        # wake, skipped them all as already-claimed, ran off the end of an empty loop and
        # marked itself `done` — a 2,000-person segment received exactly 500 emails and
        # the row said "done" with nothing anywhere recording the other 1,500.
        members, exhausted = segment_page(
            segment, limit=_CAMPAIGN_MAX_PER_WAKE, skip_ids=seen,
            start_page=_resume_page(len(seen)), max_pages=_CAMPAIGN_MAX_PAGES)
    except SegmentUnavailable as exc:
        # Membership is UNKNOWN, not empty. Leave the campaign exactly as it was: it is
        # still selected next wake, and nothing has been claimed for the wrong audience.
        log.warning("marketing: campaign %s left queued — %s (%s)",
                    cid, type(exc).__name__, exc)
        out["failed"] += 1
        return

    # queued_n is the OPERATOR'S plan, written from the console's full SQL count, and the
    # drain no longer touches it. Overwriting it with one wake's slice is what made the
    # 500-of-2,000 truncation invisible: the row read "queued 500 · sent 500 · done" and
    # the number the operator had actually approved was gone.
    _patch_campaign(cid, {"status": "sending"})

    tally = {"sent": 0, "skipped": 0, "skipped_no_smtp": 0, "failed": 0}
    n = 0
    for member in members:
        key = f"campaign:{cid}:{member['user_id']}"
        if key in done:
            continue
        # Abort must land promptly, not at the end of a 500-recipient run: the operator
        # who pressed it is watching mail they no longer want go out.
        if n and n % _ABORT_CHECK_EVERY == 0:
            live = _campaign(cid) or {}
            if (live.get("status") or "") == "aborted":
                log.info("marketing: campaign %s aborted mid-send after %d", cid, n)
                _bump(cid, tally)
                return
        if n >= _CAMPAIGN_MAX_PER_WAKE:
            log.info("marketing: campaign %s hit the per-wake cap — resuming next wake", cid)
            _bump(cid, tally)
            return
        subject, html, text = campaign_message(camp, member["user_id"])
        status = mailer.send(
            template=CAMPAIGN_TEMPLATE, cls="marketing", to_email=member["email"],
            subject=subject, html=html, text=text, idem_key=key,
            user_id=member["user_id"], headers=_marketing_headers(member["user_id"]))
        # One classification, two ledgers: the sweep census this wake returns, and the
        # campaign's own running counters. A 'duplicate' belongs in neither of the
        # campaign's — it was already counted the wake that actually sent it.
        bucket = _tally(out, status)
        if bucket in tally:
            tally[bucket] += 1
        n += 1
        _pace(status)

    # `done` ONLY when the roster was walked to its end. A wake that filled its quota, or
    # stopped at the scan ceiling, has not proved there is nobody left — and a campaign
    # marked done is never selected again, so the proof has to come first.
    _bump(cid, tally, done=exhausted)
    log.info("marketing: campaign %s wake %s (audience %s)", cid, tally,
             "exhausted" if exhausted else "MORE TO COME — still sending")


def _bump(cid: str, tally: dict, *, done: bool = False) -> None:
    """Add this wake's outcome onto the campaign's running counters."""
    live = _campaign(cid) or {}
    patch = {
        "sent_n": int(live.get("sent_n") or 0) + tally["sent"],
        # No column exists for "the relay was off", and it is emphatically not a send, so
        # it lands with the other people we did not reach rather than inflating sent_n.
        "skipped_n": (int(live.get("skipped_n") or 0) + tally["skipped"]
                      + tally.get("skipped_no_smtp", 0)),
        "failed_n": int(live.get("failed_n") or 0) + tally["failed"],
    }
    # An aborted campaign keeps its status: the operator's decision outranks the drain's
    # opinion that it finished.
    if done and (live.get("status") or "") != "aborted":
        patch["status"] = "done"
    _patch_campaign(cid, patch)


# --------------------------------------------------------------------------- #
# The parked-row drain (W3's documented contract, app/mailer.py module docstring)
# --------------------------------------------------------------------------- #
def drain_parked() -> dict:
    """Finish the rows W3 parked when its suppression lookup was unavailable.

    Those rows sit at ``status='queued', detail='suppression_lookup_failed'``: the ledger
    claimed the idem_key, so the message can never go out through :func:`mailer.send`
    again — a second call would hit the unique constraint and return ``'duplicate'``
    without sending anything. The claimed row IS the work item and it is completed IN
    PLACE: re-check suppression, then either PATCH it to ``suppressed`` or rebuild the
    message and hand it straight to the transport, PATCHing the same row to its terminal
    status.

    Rebuilding is possible because ``email_log`` stores no body: the content of both
    templates this module owns is a pure function of an identity (``welcome:{user_id}``)
    or of a campaign row (``campaign:{id}:{user_id}``). A parked row from any OTHER
    template is left alone and logged — guessing at content nobody stored would be a
    worse outcome than a row an operator has to look at.

    TWO KINDS OF STRANDED ROW, and the second one is the recovery lane
    ------------------------------------------------------------------
    ``status='queued', detail='suppression_lookup_failed'`` is W3's park, above.
    ``status='skipped_no_smtp'`` is the OTHER one: a terminal row whose idem_key is spent
    and whose message was never written, produced by any send attempted while the relay
    was off. :func:`_relay_ready` stops the welcome and campaign legs from creating more
    of them, but rows created before that landed still exist, and nothing would ever have
    looked at them again — the message was simply gone. So once a relay exists they are
    re-offered exactly like a parked row: suppression re-checked, message rebuilt,
    transport handed the result, THIS row PATCHed. While there is still no relay they are
    not selected at all, because re-skipping them is work with no outcome.

    The gates are the LEG's gates, per row. A parked welcome is only completed when the
    welcome leg is armed and a parked campaign only when campaigns are — the same switches
    that decide whether those messages may go out at all, applied to messages that are
    merely late.
    """
    out = {"scanned": 0, "sent": 0, "suppressed": 0, "skipped": 0,
           "skipped_no_smtp": 0, "failed": 0}
    if not (marketing_enabled() and (welcome_enabled() or campaigns_enabled())):
        return out
    rows: list[dict] = []
    try:
        rows += _pg("GET", "email_log?status=eq.queued&detail=eq.suppression_lookup_failed"
                           "&select=idem_key,template,class,to_email,user_id"
                           f"&order=created_at.asc&limit={_PARKED_LIMIT}") or []
        if mailer.is_configured():
            rows += _pg("GET", "email_log?status=eq.skipped_no_smtp"
                               "&select=idem_key,template,class,to_email,user_id"
                               f"&order=created_at.asc&limit={_PARKED_LIMIT}") or []
    except Exception as exc:  # noqa: BLE001
        log.warning("marketing: parked query failed (%s)", type(exc).__name__)
        out["failed"] += 1
        return out

    for row in rows:
        out["scanned"] += 1
        try:
            _complete_parked(row, out)
        except Exception as exc:  # noqa: BLE001
            log.warning("marketing: parked row %s failed (%s)",
                        row.get("idem_key"), type(exc).__name__)
            out["failed"] += 1
    if out["scanned"]:
        log.info("marketing: parked drain %s", out)
    return out


def _rebuild(idem_key: str, template: str, user_id: str | None) -> tuple[str, str, str] | None:
    """The message a parked row was going to carry, or None when we cannot know."""
    if template == WELCOME_TEMPLATE and user_id:
        return welcome_message(user_id)
    if template == CAMPAIGN_TEMPLATE and idem_key.startswith("campaign:"):
        parts = idem_key.split(":")
        if len(parts) >= 3:
            camp = _campaign(parts[1])
            if camp:
                return campaign_message(camp, user_id or parts[2])
    return None


def _leg_armed(template: str) -> bool:
    """Is the leg that owns this template switched on? Unknown templates are not ours."""
    if template == WELCOME_TEMPLATE:
        return welcome_enabled()
    if template == CAMPAIGN_TEMPLATE:
        return campaigns_enabled()
    return False


def _complete_parked(row: dict, out: dict) -> None:
    idem_key = str(row.get("idem_key") or "")
    to_email = str(row.get("to_email") or "")
    user_id = row.get("user_id") or None
    template = str(row.get("template") or "")
    if not (idem_key and to_email):
        out["skipped"] += 1
        return
    if not _leg_armed(template):
        out["skipped"] += 1
        return

    try:
        reason = mailer._suppression_reason(to_email, user_id)
    except mailer.SuppressionUnavailable:
        out["skipped"] += 1          # still unavailable — the row waits for the next wake
        return
    if reason:
        mailer._ledger_finish(idem_key, "suppressed", reason)
        out["suppressed"] += 1
        return

    built = _rebuild(idem_key, template, str(user_id) if user_id else None)
    if built is None:
        log.info("marketing: parked %s (template=%r) has no rebuild rule — left queued",
                 idem_key, template)
        out["skipped"] += 1
        return
    if not mailer.is_configured():
        # Terminal, but no longer final: the row is picked up again by the second select
        # in drain_parked the moment a relay exists.
        mailer._ledger_finish(idem_key, "skipped_no_smtp", "MAIL_SMTP_* unset")
        out["skipped_no_smtp"] += 1
        return

    subject, html, text = built
    identity = str(user_id) if user_id else to_email
    try:
        msg = mailer._build_message(
            to_email=to_email, subject=subject, html=html, text=text,
            cls="marketing", headers=_marketing_headers(identity))
        mailer._smtp_send(msg)
    except Exception as exc:  # noqa: BLE001
        mailer._ledger_finish(idem_key, "failed", type(exc).__name__)
        out["failed"] += 1
        _pace("failed")
        return
    mailer._ledger_finish(idem_key, "sent", "drained")
    out["sent"] += 1
    _pace("sent")


# --------------------------------------------------------------------------- #
# The sweep + the loop
# --------------------------------------------------------------------------- #
def sweep() -> dict:
    """One wake: parked rows first, then welcomes, then campaigns.

    Parked first because those rows are already claimed and already late; welcomes before
    campaigns because a welcome is time-sensitive and a broadcast is not, and a long
    campaign drain must not push a signup's welcome into the next wake.
    """
    return {"parked": drain_parked(), "welcome": sweep_welcome(), "campaigns": drain_campaigns()}


def _interval() -> int:
    try:
        return max(60, int(os.environ.get("MAIL_MARKETING_INTERVAL_SEC") or MARKETING_INTERVAL_SEC))
    except ValueError:
        return MARKETING_INTERVAL_SEC


def register_marketing(app: Any) -> bool:
    """Attach the marketing sweeper to a FastAPI app. No-op unless armed.

    Returns whether the loop started, so the caller can log it. Decided at mount time like
    W3's ``register_lifecycle``: a background task that can appear mid-process is a
    debugging trap, and flipping the env is already a service restart in the runbook.
    """
    if not marketing_enabled():
        log.info("marketing: sweeper not enabled (MAIL_MARKETING_ENABLED=%r; enable with one of %s)",
                 (os.environ.get("MAIL_MARKETING_ENABLED") or "").strip(), _TRUTHY)
        return False
    import asyncio  # noqa: PLC0415 — only needed on the armed path

    interval = _interval()

    async def _loop() -> None:
        # Sleep FIRST: a crash-restart loop must never become a send loop.
        while True:
            try:
                await asyncio.sleep(interval)
                await asyncio.to_thread(sweep)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — a bad wake must not kill the loop
                log.warning("marketing: wake failed (%s)", type(exc).__name__)

    async def _start() -> None:
        app.state.mail_marketing_task = asyncio.create_task(_loop())
        log.info("marketing: sweeper armed (every %ds; welcome=%s campaigns=%s)",
                 interval, welcome_enabled(), campaigns_enabled())

    async def _stop() -> None:
        task = getattr(app.state, "mail_marketing_task", None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            log.debug("marketing: task ended with %s", type(exc).__name__)

    app.add_event_handler("startup", _start)
    app.add_event_handler("shutdown", _stop)
    return True


# --------------------------------------------------------------------------- #
# CLI — `python -m app.marketing_emails --sweep`
# --------------------------------------------------------------------------- #
def _main(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(description="Marketing + welcome email sweeper")
    ap.add_argument("--sweep", action="store_true", help="run one sweep and exit")
    ap.add_argument("--window", action="store_true",
                    help="print the welcome window in force and exit (sends nothing)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.window:
        floor, now = welcome_window()
        print(json.dumps({"floor": floor.isoformat() if floor else None,
                          "now": now.isoformat(),
                          "lookback_hours": _lookback_hours(),
                          "armed": bool(floor and marketing_enabled() and welcome_enabled())}))
        return 0
    if args.sweep:
        print(json.dumps(sweep()))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
