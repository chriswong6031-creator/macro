"""engine/alert_delivery_drain.py -- pure decision logic + isolated PostgREST IO for the
fired-alert delivery drain (packet B-F08-1b).

Trigger: ``app/deploy/macro-alert-drain.timer`` on the VPS app host (``OnCalendar=*:0/5``).
Cadence: every 5 minutes. User-visible latency budget: 15 minutes p95 from fire to send
(three ticks: one to pick it up, two of slack). This module is OFF the render path -- it
is never imported by any render or nightly builder and writes nothing under ``site/`` or
``data/``.

Layering (STANDING, do not re-litigate): ``engine/`` may not import ``app/`` --
``engine/portfolio_digest.py`` states this as construction law for exactly this lane.
Therefore the mail-sending function is INJECTED at the ``scripts/`` seam
(``scripts/drain_alert_outbox.py`` wires ``app.mailer.send_alert`` in as ``send_fn``);
this module has no import of ``app`` anywhere, which is what makes it possible for
``tests/test_alert_delivery_drain.py::test_engine_module_does_not_import_app`` to prove
no test of it and no build step that imports it can ever send mail.

``_pg`` below mirrors ``app/mailer.py``'s helper (same headers, same env resolution, same
``urllib`` idiom) but is local to this module for the layering reason above.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

# --------------------------------------------------------------------------- #
# Typed reads (F08 freeze section 5 vocabulary)
# --------------------------------------------------------------------------- #
READ_OK = "READ_OK"
READ_OK_ZERO = "READ_OK_ZERO"
READ_NO_COVERAGE = "READ_NO_COVERAGE"
READ_UNAVAILABLE = "READ_UNAVAILABLE"

LANE = "macro_delivery_drain"
CADENCE_BUDGET_S = 300

# A 'failed' row is retried this many times (attempt 0 = the original send) before it
# leaves the drain's own selection predicate for good (review round 3 ruling). No new
# alert_outbox enum value is introduced -- the row stays 'failed', simply unselected.
ALERT_RETRY_ATTEMPTS_CAP = 3

# Mirrors app.mailer.ALERT_TEMPLATE / app.mailer.alert_idem_key -- duplicated locally
# for the same layering reason ``_pg`` is (module docstring): this module may not
# import ``app/``. Needed only to resolve what a mailer 'duplicate' result actually
# meant (review round 2 blocker, acceptance 1(d) -- see ``_resolve_duplicate`` below).
_ALERT_TEMPLATE = "alert_fire"


def _alert_idem_key(fire_event_id: str, attempt: int = 0) -> str:
    """Pinned identical to ``app.mailer.alert_idem_key`` (cross-module test in
    ``tests/test_alert_delivery_drain.py``) -- ``attempt=0`` is byte-identical to the
    original single-arg key; ``attempt>0`` mints a fresh key for a retry so a
    terminally-'failed' email_log row never blocks a later send under the same key
    (review round 3 BLOCKER)."""
    base = f"{_ALERT_TEMPLATE}:{fire_event_id}"
    return base if not attempt else f"{base}:{attempt}"


@dataclass(frozen=True)
class TypedRead:
    state: str
    rows: list | None
    error_class: str | None = None


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _pg(method: str, path: str, body=None, prefer: str | None = None, timeout: int = 6):
    url_base = _env("SUPABASE_URL").rstrip("/")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    if not key or not url_base:
        raise RuntimeError("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY unset")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(
        f"{url_base}/rest/v1/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def typed_get(path: str) -> TypedRead:
    """GET ``path`` and classify the result. ``READ_UNAVAILABLE`` never looks like
    ``READ_OK_ZERO`` -- a missing table is a typed failure, not an empty success."""
    try:
        rows = _pg("GET", path)
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        if exc.code == 404 or "42P01" in body or "PGRST205" in body:
            return TypedRead(READ_UNAVAILABLE, None, error_class="table_absent")
        return TypedRead(READ_UNAVAILABLE, None, error_class=f"HTTPError{exc.code}")
    except Exception as exc:  # noqa: BLE001
        return TypedRead(READ_UNAVAILABLE, None, error_class=type(exc).__name__)
    if rows is None:
        return TypedRead(READ_UNAVAILABLE, None, error_class="empty_response")
    if not rows:
        return TypedRead(READ_OK_ZERO, [])
    return TypedRead(READ_OK, rows)


# --------------------------------------------------------------------------- #
# Prefs (tolerant -- packet B-F08-1a may not have merged yet)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AlertPrefs:
    email_optin: bool
    categories: tuple | None
    tz: str
    tz_source: str
    quiet: tuple | None
    quiet_note: str | None
    lang: str


def _parse_quiet(value) -> tuple:
    """Returns (quiet_tuple_or_None, note_or_None)."""
    if value is None:
        return None, None
    try:
        if isinstance(value, dict):
            start_s, end_s = value.get("start"), value.get("end")
        elif isinstance(value, str) and "-" in value:
            start_s, end_s = value.split("-", 1)
        else:
            return None, "unparsed"

        def _to_min(s: str) -> int:
            h, m = str(s).strip().split(":")
            return int(h) * 60 + int(m)

        return (_to_min(start_s), _to_min(end_s)), None
    except Exception:  # noqa: BLE001
        return None, "unparsed"


def parse_alert_prefs(meta: dict | None) -> AlertPrefs | None:
    """None when ``meta`` is None -- 'we do not know', NOT 'nothing is set'."""
    if meta is None:
        return None
    optin_raw = meta.get("alert_email_optin")
    email_optin = optin_raw is True or optin_raw in ("true", "1", "on")
    cats = meta.get("alert_categories")
    categories = tuple(cats) if isinstance(cats, (list, tuple)) else None
    tz = meta.get("tz") or "UTC"
    tz_source = "user" if meta.get("tz") else "default_utc"
    quiet, quiet_note = _parse_quiet(meta.get("quiet_hours"))
    lang = meta.get("lang") if meta.get("lang") in ("en", "zh") else "en"
    return AlertPrefs(email_optin=email_optin, categories=categories, tz=tz,
                      tz_source=tz_source, quiet=quiet, quiet_note=quiet_note, lang=lang)


# --------------------------------------------------------------------------- #
# Recipient address (the gap the frozen contract leaves open)
# --------------------------------------------------------------------------- #
def fetch_user_record(user_id: str) -> tuple:
    """``(typed_state, {'email':..., 'user_metadata':...} | None)`` from GoTrue admin.
    ``READ_UNAVAILABLE`` on any failure -- an unknown recipient is never a send."""
    url_base = _env("SUPABASE_URL").rstrip("/")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    if not key or not url_base:
        return READ_UNAVAILABLE, None
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}
    req = urllib.request.Request(
        f"{url_base}/auth/v1/admin/users/{urllib.parse.quote(str(user_id), safe='')}",
        method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            raw = resp.read()
        rec = json.loads(raw) if raw else None
        if not rec:
            return READ_UNAVAILABLE, None
        return READ_OK, rec
    except Exception:  # noqa: BLE001
        return READ_UNAVAILABLE, None


# --------------------------------------------------------------------------- #
# Quiet hours -- user tz, never NY (F08 freeze section 3/8)
# --------------------------------------------------------------------------- #
def quiet_decision(now_utc: datetime, prefs: AlertPrefs) -> tuple:
    """('send', None) or ('defer', <window-open instant, UTC>)."""
    if not prefs.quiet:
        return "send", None
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        tz = ZoneInfo(prefs.tz)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        tz = ZoneInfo("UTC")
    local = now_utc.astimezone(tz)
    minute_of_day = local.hour * 60 + local.minute
    start_m, end_m = prefs.quiet
    if start_m <= end_m:
        in_quiet = start_m <= minute_of_day < end_m
    else:  # wraps midnight
        in_quiet = minute_of_day >= start_m or minute_of_day < end_m
    if not in_quiet:
        return "send", None
    # next local window-open instant (the day's `end_m`, rolled to tomorrow if already past)
    open_local = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=end_m)
    if open_local <= local:
        open_local += timedelta(days=1)
    return "defer", open_local.astimezone(timezone.utc)


# --------------------------------------------------------------------------- #
# Entitlement -- fail-closed (freeze section 5); NOT app.billing.read_entitlement,
# which fail-safes to free on any read error and would erase outage-vs-lapse.
# --------------------------------------------------------------------------- #
_LAPSED_STATUSES = {"canceled", "past_due", "unpaid", "incomplete_expired"}


_TIER_RANK = {"free": 0, "plus": 1, "pro": 2}


def entitlement_decision(read: TypedRead, now_utc: datetime, requires_tier: str | None = None) -> str:
    """'send' | 'suppress' | 'unavailable'. Fail-closed (freeze section 5): an
    unrecognised status, an unparsable period, or a tier below ``requires_tier``
    suppresses rather than sends -- this is the paid lane (MO-PAID-085/MO-PAID-027)."""
    if read.state == READ_UNAVAILABLE:
        return "unavailable"
    if read.state == READ_OK_ZERO:
        # No entitlement row at all: only a no-gate (free) alert may send.
        return "send" if not requires_tier else "suppress"
    row = (read.rows or [{}])[0]
    status = row.get("status")
    tier = row.get("tier")
    source = row.get("source")
    period_end = row.get("current_period_end")
    if not (source == "comp" and not period_end):
        if status in _LAPSED_STATUSES:
            return "suppress"
        if period_end:
            try:
                pe = datetime.fromisoformat(str(period_end).replace("Z", "+00:00"))
                if pe.tzinfo is None:
                    pe = pe.replace(tzinfo=timezone.utc)
                if pe < now_utc:
                    return "suppress"
            except Exception:  # noqa: BLE001
                return "suppress"  # unparsable period_end fails closed
    if requires_tier:
        have = _TIER_RANK.get(str(tier or "free"), -1)
        need = _TIER_RANK.get(str(requires_tier), 99)
        if have < need:
            return "suppress"
    if status in ("active", "trialing", "none") or source == "comp":
        return "send"
    return "suppress"  # fail-closed: an unrecognised status never sends


# --------------------------------------------------------------------------- #
# Decision (pure, the heart of the RED-first tests)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    deliver_after: datetime | None = None
    to_email: str | None = None
    lang: str = "en"


def decide_row(row: dict, *, user_state: str, record: dict | None,
              ent: TypedRead, suppression: TypedRead, now_utc: datetime) -> Decision:
    if user_state != READ_OK or record is None:
        return Decision(action="unevaluable", reason="prefs_unknown")
    meta = record.get("user_metadata") if isinstance(record, dict) else None
    prefs = parse_alert_prefs(meta)
    if prefs is None:
        return Decision(action="unevaluable", reason="prefs_unknown")
    to_email = str(record.get("email") or "")
    if not prefs.email_optin:
        return Decision(action="suppress", reason="not_opted_in", to_email=to_email, lang=prefs.lang)
    payload = row.get("payload") or {}
    category = payload.get("category")
    if prefs.categories is not None and category is not None and category not in prefs.categories:
        return Decision(action="suppress", reason="category_filtered", to_email=to_email, lang=prefs.lang)
    if suppression.state == READ_UNAVAILABLE:
        return Decision(action="unevaluable", reason="address_suppression_unavailable")
    if suppression.state == READ_OK and suppression.rows:
        return Decision(action="suppress", reason="address_suppressed", to_email=to_email, lang=prefs.lang)
    if ent.state == READ_UNAVAILABLE:
        return Decision(action="unevaluable", reason="entitlement_unavailable")
    requires_tier = payload.get("requires_tier")
    ent_decision = entitlement_decision(ent, now_utc, requires_tier=requires_tier)
    if ent_decision == "unavailable":
        return Decision(action="unevaluable", reason="entitlement_unavailable")
    if ent_decision == "suppress":
        return Decision(action="suppress", reason="entitlement_lapsed", to_email=to_email, lang=prefs.lang)
    if prefs.quiet_note == "unparsed":
        # An unrecognised quiet_hours shape must never fail OPEN to a silent send --
        # surface it as unevaluable (typed, counted, visible in the run receipt).
        return Decision(action="unevaluable", reason="quiet_hours_unparsed")
    action, deliver_after = quiet_decision(now_utc, prefs)
    if action == "defer":
        return Decision(action="defer", reason="quiet_hours", deliver_after=deliver_after,
                        to_email=to_email, lang=prefs.lang)
    return Decision(action="send", reason="ok", to_email=to_email, lang=prefs.lang)


# --------------------------------------------------------------------------- #
# Two-phase run receipts
# --------------------------------------------------------------------------- #
def open_receipt(now_utc: datetime) -> tuple:
    """(run_uuid, run_id, wrote) -- POST the started row; wrote=False if unwritable."""
    run_uuid = uuid.uuid4()
    started_at_iso = now_utc.isoformat()
    run_id = f"{LANE}:{started_at_iso}:{run_uuid.hex[:8]}"
    try:
        _pg("POST", "alert_runs", body=[{
            "id": str(run_uuid), "lane": LANE, "run_id": run_id,
            "started_at": started_at_iso, "lane_cadence_budget_s": CADENCE_BUDGET_S,
        }], prefer="return=minimal")
        return str(run_uuid), run_id, True
    except Exception:  # noqa: BLE001
        return str(run_uuid), run_id, False


def close_receipt(run_uuid: str, *, outcome: str, evaluated_n: int, fired_n: int,
                  unevaluable_n: int, source_asof: str | None, error_class: str | None,
                  duplicate_n: int = 0) -> bool:
    """``duplicate_n`` is accepted (kept in the caller's ``DrainResult``/stdout summary)
    but deliberately NOT written here (review round 3 MAJOR-3): no schema file in this
    tree evidences an ``alert_runs.duplicate_n`` column, nor a jsonb ``detail``-style
    column on that table to fold it into, and the frozen table is external to this
    repo -- adding an unproven column made every ``close_receipt`` PATCH 400 (schema
    mismatch), swallowed by the except below, forcing ``outcome='partial'`` on every
    run regardless of whether a duplicate ever occurred. Ruling: no schema change;
    state the disposition in the PR body's nulls section (done)."""
    try:
        _pg("PATCH", f"alert_runs?id=eq.{urllib.parse.quote(run_uuid, safe='')}", body={
            "concluded_at": datetime.now(timezone.utc).isoformat(),
            "outcome": outcome, "evaluated_n": evaluated_n, "fired_n": fired_n,
            "unevaluable_n": unevaluable_n, "source_asof": source_asof,
            "error_class": error_class,
        }, prefer="return=minimal")
        return True
    except Exception:  # noqa: BLE001
        return False


def _patch_outbox(row_id, body: dict) -> bool:
    """PATCH one ``alert_outbox`` row; returns whether the write actually persisted.
    Review round 3 MINOR-3: a run receipt's counters must reflect writes that
    happened, not writes attempted -- every counter increment in the loop below is
    gated on this return value so a swallowed PATCH (network blip, CHECK rejection)
    can never inflate a receipt with a change that never landed."""
    try:
        _pg("PATCH", f"alert_outbox?id=eq.{row_id}", body=body, prefer="return=minimal")
        return True
    except Exception:  # noqa: BLE001
        return False


def derive_outcome(*, read_state: str, evaluated_n: int, unevaluable_n: int,
                   failed_n: int, degraded_n: int) -> str:
    if read_state == READ_UNAVAILABLE:
        return "failure"
    if unevaluable_n > 0 or failed_n > 0 or degraded_n > 0:
        return "partial"
    return "success"


# --------------------------------------------------------------------------- #
# The one entry function
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DrainResult:
    outcome: str
    evaluated_n: int
    fired_n: int
    unevaluable_n: int
    deferred_n: int
    suppressed_n: int
    failed_n: int
    category_unfiltered_n: int
    duplicate_n: int
    read_state: str
    error_class: str | None
    run_id: str | None
    receipt_written: bool


def drain(*, send_fn: Callable[..., str] | None, now_utc: datetime | None = None,
         limit: int = 200, dry_run: bool = False) -> DrainResult:
    """Drain one batch. NEVER raises for a delivery reason.

    ``send_fn(fire_event_id=..., to_email=..., payload=..., lang=..., user_id=...,
    attempt=...) -> str`` returning a value in ``app.mailer.STATUSES`` +
    ``'duplicate'``. Injected so this module never imports ``app/`` (see the module
    docstring's Layering note). ``send_fn=None`` or ``dry_run=True`` => decisions
    computed, ZERO sends, ZERO writes.

    A 'failed' row is re-selected only while ``attempts < ALERT_RETRY_ATTEMPTS_CAP`` --
    once capped it stays 'failed' but drops out of the ``or=(...)`` predicate below, so
    it is never retried again and never silently reappears as unaccounted-for.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    outbox_read = typed_get(
        "alert_outbox?channel=eq.email"
        "&or=(status.eq.pending,"
        f"and(status.eq.failed,attempts.lt.{int(ALERT_RETRY_ATTEMPTS_CAP)}),"
        f"and(status.eq.deferred,deliver_after.lte.{urllib.parse.quote(now_iso)}))"
        "&select=id,user_id,alert_id,fire_event_id,status,payload,attempts,deliver_after"
        f"&order=created_at.asc&limit={int(limit)}")

    run_uuid, run_id, wrote = (None, None, False) if dry_run else open_receipt(now_utc)

    if outbox_read.state == READ_UNAVAILABLE:
        receipt_written = False
        if not dry_run and run_uuid is not None:
            receipt_written = close_receipt(
                run_uuid, outcome="failure", evaluated_n=0, fired_n=0, unevaluable_n=0,
                source_asof=None, error_class=outbox_read.error_class) and wrote
        return DrainResult(outcome="failure", evaluated_n=0, fired_n=0, unevaluable_n=0,
                           deferred_n=0, suppressed_n=0, failed_n=0, category_unfiltered_n=0,
                           duplicate_n=0,
                           read_state=READ_UNAVAILABLE, error_class=outbox_read.error_class,
                           run_id=run_id, receipt_written=receipt_written)

    rows = outbox_read.rows or []

    evaluated_n = fired_n = unevaluable_n = deferred_n = suppressed_n = failed_n = 0
    category_unfiltered_n = 0
    duplicate_n = 0
    degraded_n = 0
    fired_ats = []

    for row in rows:
        evaluated_n += 1
        payload = row.get("payload") or {}
        if payload.get("category") is None:
            category_unfiltered_n += 1
        user_id = row.get("user_id")

        user_state, record = fetch_user_record(str(user_id)) if user_id else (READ_UNAVAILABLE, None)
        suppression = TypedRead(READ_UNAVAILABLE, None)
        ent = TypedRead(READ_UNAVAILABLE, None)
        if user_state == READ_OK and record is not None:
            addr = str(record.get("email") or "").strip().lower()
            suppression = typed_get(f"email_suppression?email=eq.{urllib.parse.quote(addr, safe='')}&select=email,reason") if addr else TypedRead(READ_OK_ZERO, [])
            ent = typed_get(f"user_entitlements?user_id=eq.{urllib.parse.quote(str(user_id), safe='')}&select=tier,status,current_period_end,source")

        decision = decide_row(row, user_state=user_state, record=record, ent=ent,
                              suppression=suppression, now_utc=now_utc)

        if decision.action == "unevaluable":
            unevaluable_n += 1
            continue

        if dry_run or send_fn is None:
            if decision.action == "send":
                fired_n += 1
            elif decision.action == "defer":
                deferred_n += 1
            elif decision.action == "suppress":
                suppressed_n += 1
            continue

        if decision.action == "defer":
            ok = _patch_outbox(row["id"], {"status": "deferred",
                                            "deliver_after": decision.deliver_after.isoformat()})
            if ok:
                deferred_n += 1
            continue

        if decision.action == "suppress":
            ok = _patch_outbox(row["id"], {"status": "suppressed", "last_error": decision.reason})
            if ok:
                suppressed_n += 1
            continue

        # action == send
        fire_event_id = row.get("fire_event_id")
        attempt_n = int(row.get("attempts") or 0)
        try:
            status = send_fn(fire_event_id=fire_event_id, to_email=decision.to_email,
                             payload=payload, lang=decision.lang, user_id=user_id,
                             attempt=attempt_n)
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error_cls = type(exc).__name__
        else:
            error_cls = None

        if status == "duplicate":
            # A mailer 'duplicate' means email_log's UNIQUE idem_key was already claimed
            # -- it does NOT mean the earlier attempt actually sent (review round 2
            # blocker, acceptance 1(d)): the prior claim could equally be a failed,
            # suppressed, or still-queued send. Read that row rather than assume. The
            # key read back is the SAME one just attempted (same fire_event_id+attempt)
            # -- never the bare attempt=0 key -- so a retry's own claim is what gets
            # resolved, not the original attempt's.
            idem_key = _alert_idem_key(str(fire_event_id), attempt=attempt_n)
            log_read = typed_get(
                f"email_log?idem_key=eq.{urllib.parse.quote(idem_key, safe='')}"
                "&select=status,created_at,detail")
            log_row = (log_read.rows or [None])[0] if log_read.state == READ_OK else None
            log_status = log_row.get("status") if log_row else None
            if log_status == "sent":
                # The earlier attempt genuinely sent -- mirror THAT fact, counted as a
                # duplicate resolution, never as a fresh fire.
                delivered_at = log_row.get("created_at") or datetime.now(timezone.utc).isoformat()
                ok = _patch_outbox(row["id"], {"status": "sent", "delivered_at": delivered_at,
                                                "last_error": None})
                if ok:
                    duplicate_n += 1
            elif log_status == "failed":
                # Review round 3 BLOCKER: this idem_key is now TERMINAL -- the real
                # mailer never revisits a claimed key's terminal status, so retrying
                # under the SAME key would read 'failed' forever (livelock). Bump
                # attempts here (this WAS the bug: the old code left attempts
                # unchanged on this exact path) so the next tick's send_fn call mints
                # a fresh key via ``attempt_n`` above, and the selection predicate's
                # cap eventually retires the row instead of looping forever.
                new_attempts = int(row.get("attempts") or 0) + 1
                ok = _patch_outbox(row["id"], {"status": "failed", "attempts": new_attempts,
                                                "last_error": "prior send failed"})
                if ok:
                    duplicate_n += 1
                    failed_n += 1
            elif log_status == "suppressed":
                ok = _patch_outbox(row["id"], {"status": "suppressed",
                                                "last_error": "prior send suppressed"})
                if ok:
                    duplicate_n += 1
                    suppressed_n += 1
            elif log_status is not None:
                # 'queued' / 'skipped_no_smtp' (or any other readable, non-terminal
                # mailer status): NOT a failure and NOT a success, so it must not be
                # mirrored into alert_outbox's own CHECK-constrained status column --
                # neither value is a legal alert_outbox status (review round 3
                # MAJOR-2; the old code wrote it verbatim, which either violated the
                # CHECK constraint -- silently swallowed -- or, had it been accepted,
                # permanently orphaned the row outside this drain's own selection
                # predicate). The row stays 'pending' so the next tick re-selects it;
                # attempts is left unchanged since no send failure occurred.
                ok = _patch_outbox(row["id"], {"status": "pending",
                                                "last_error": f"prior send {log_status}"})
                if ok:
                    duplicate_n += 1
                    degraded_n += 1
            else:
                # Unreadable (READ_UNAVAILABLE) or a zero-row read that contradicts the
                # 'duplicate' claim -- either way we do not know what the prior send did,
                # so the row is left exactly as it was: pending, attempts unchanged, never
                # sent. Typed, printed, never silent.
                degraded_n += 1
                print("::warning title=alert-drain-duplicate-unreadable::"
                      "email_log row for idem_key %s state=READ_UNAVAILABLE (%s) -- outbox "
                      "row %s left pending, never marked sent"
                      % (idem_key, log_read.error_class or "no_matching_row", row["id"]),
                      flush=True)
        elif status == "sent":
            fired_at = payload.get("fired_at")
            ok = _patch_outbox(row["id"], {"status": "sent",
                                            "delivered_at": datetime.now(timezone.utc).isoformat(),
                                            "attempts": int(row.get("attempts") or 0) + 1,
                                            "last_error": None})
            if ok:
                fired_n += 1
                if fired_at:
                    fired_ats.append(str(fired_at))
        elif status in ("skipped_no_smtp", "queued"):
            # Not a failure -- a config/transient gap (mail-off, or a marketing-only
            # ledger race that should never reach this transactional class in
            # practice). Leave the row 'pending' so the next tick tries again, rather
            # than burning a retry attempt or mirroring a non-alert_outbox status
            # (review round 3 MINOR-2; mirrors the duplicate-branch treatment above).
            ok = _patch_outbox(row["id"], {"status": "pending", "last_error": status})
            if ok:
                degraded_n += 1
        elif status == "suppressed":
            ok = _patch_outbox(row["id"], {"status": "suppressed", "last_error": status})
            if ok:
                suppressed_n += 1
        else:
            # "failed", or any status outside app.mailer.STATUSES -- fail-closed as a
            # real send failure: attempts increments (bounded by the retry cap above).
            new_attempts = int(row.get("attempts") or 0) + 1
            ok = _patch_outbox(row["id"], {"status": "failed", "attempts": new_attempts,
                                            "last_error": error_cls or status})
            if ok:
                failed_n += 1

    outcome = derive_outcome(read_state=outbox_read.state, evaluated_n=evaluated_n,
                             unevaluable_n=unevaluable_n, failed_n=failed_n, degraded_n=degraded_n)

    receipt_written = False
    if not dry_run and run_uuid is not None:
        source_asof = max(fired_ats) if fired_ats else None
        receipt_written = close_receipt(run_uuid, outcome=outcome, evaluated_n=evaluated_n,
                                        fired_n=fired_n, unevaluable_n=unevaluable_n,
                                        source_asof=source_asof, error_class=None,
                                        duplicate_n=duplicate_n) and wrote
        if not receipt_written and outcome == "success":
            # The run's own provenance failed to persist -- freeze section 4's
            # fallback => partial applies to the receipt path itself, not only to
            # the rows evaluated (2(ii)): a run nobody can audit is never "success".
            outcome = "partial"

    return DrainResult(outcome=outcome, evaluated_n=evaluated_n, fired_n=fired_n,
                       unevaluable_n=unevaluable_n, deferred_n=deferred_n,
                       suppressed_n=suppressed_n, failed_n=failed_n,
                       category_unfiltered_n=category_unfiltered_n,
                       duplicate_n=duplicate_n,
                       read_state=outbox_read.state, error_class=None,
                       run_id=run_id, receipt_written=receipt_written)
