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


def entitlement_decision(read: TypedRead, now_utc: datetime, requires_tier: str | None = None) -> str:
    """'send' | 'suppress' | 'unavailable'."""
    if read.state == READ_UNAVAILABLE:
        return "unavailable"
    if read.state == READ_OK_ZERO:
        return "send"
    row = (read.rows or [{}])[0]
    status = row.get("status")
    tier = row.get("tier")
    source = row.get("source")
    period_end = row.get("current_period_end")
    if source == "comp" and not period_end:
        return "send"
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
            pass
    if status == "none" and tier == "free":
        return "send"
    return "send"


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
    if suppression.state == READ_UNAVAILABLE:
        return Decision(action="unevaluable", reason="address_suppression_unavailable")
    if suppression.state == READ_OK and suppression.rows:
        return Decision(action="suppress", reason="address_suppressed", to_email=to_email, lang=prefs.lang)
    if ent.state == READ_UNAVAILABLE:
        return Decision(action="unevaluable", reason="entitlement_unavailable")
    ent_decision = entitlement_decision(ent, now_utc)
    if ent_decision == "unavailable":
        return Decision(action="unevaluable", reason="entitlement_unavailable")
    if ent_decision == "suppress":
        return Decision(action="suppress", reason="entitlement_lapsed", to_email=to_email, lang=prefs.lang)
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
                  unevaluable_n: int, source_asof: str | None, error_class: str | None) -> bool:
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
    read_state: str
    error_class: str | None
    run_id: str | None
    receipt_written: bool


def drain(*, send_fn: Callable[..., str] | None, now_utc: datetime | None = None,
         limit: int = 200, dry_run: bool = False) -> DrainResult:
    """Drain one batch. NEVER raises for a delivery reason.

    ``send_fn(fire_event_id=..., to_email=..., payload=..., lang=..., user_id=...) -> str``
    returning a value in ``app.mailer.STATUSES`` + ``'duplicate'``. Injected so this
    module never imports ``app/`` (see the module docstring's Layering note).
    ``send_fn=None`` or ``dry_run=True`` => decisions computed, ZERO sends, ZERO writes.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    outbox_read = typed_get(
        "alert_outbox?channel=eq.email"
        f"&or=(status.eq.pending,and(status.eq.deferred,deliver_after.lte.{urllib.parse.quote(now_iso)}))"
        "&select=id,user_id,alert_id,fire_event_id,status,payload,attempts,deliver_after"
        f"&order=created_at.asc&limit={int(limit)}")

    if outbox_read.state == READ_UNAVAILABLE:
        return DrainResult(outcome="failure", evaluated_n=0, fired_n=0, unevaluable_n=0,
                           deferred_n=0, suppressed_n=0, failed_n=0, category_unfiltered_n=0,
                           read_state=READ_UNAVAILABLE, error_class=outbox_read.error_class,
                           run_id=None, receipt_written=False)

    rows = outbox_read.rows or []

    run_uuid, run_id, wrote = (None, None, False) if dry_run else open_receipt(now_utc)

    evaluated_n = fired_n = unevaluable_n = deferred_n = suppressed_n = failed_n = 0
    category_unfiltered_n = 0
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
            deferred_n += 1
            try:
                _pg("PATCH", f"alert_outbox?id=eq.{row['id']}",
                    body={"status": "deferred", "deliver_after": decision.deliver_after.isoformat()},
                    prefer="return=minimal")
            except Exception:  # noqa: BLE001
                pass
            continue

        if decision.action == "suppress":
            suppressed_n += 1
            try:
                _pg("PATCH", f"alert_outbox?id=eq.{row['id']}",
                    body={"status": "suppressed", "last_error": decision.reason},
                    prefer="return=minimal")
            except Exception:  # noqa: BLE001
                pass
            continue

        # action == send
        fire_event_id = row.get("fire_event_id")
        try:
            status = send_fn(fire_event_id=fire_event_id, to_email=decision.to_email,
                             payload=payload, lang=decision.lang, user_id=user_id)
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error_cls = type(exc).__name__
        else:
            error_cls = None

        if status == "duplicate":
            fired_n += 1
            try:
                _pg("PATCH", f"alert_outbox?id=eq.{row['id']}",
                    body={"status": "sent", "delivered_at": datetime.now(timezone.utc).isoformat(),
                          "last_error": "duplicate_idem_key"}, prefer="return=minimal")
            except Exception:  # noqa: BLE001
                pass
        elif status == "sent":
            fired_n += 1
            fired_at = payload.get("fired_at")
            if fired_at:
                fired_ats.append(str(fired_at))
            try:
                _pg("PATCH", f"alert_outbox?id=eq.{row['id']}",
                    body={"status": "sent", "delivered_at": datetime.now(timezone.utc).isoformat(),
                          "attempts": int(row.get("attempts") or 0) + 1, "last_error": None},
                    prefer="return=minimal")
            except Exception:  # noqa: BLE001
                pass
        else:
            failed_n += 1
            if status in ("skipped_no_smtp", "queued", "suppressed"):
                degraded_n += 1
            try:
                _pg("PATCH", f"alert_outbox?id=eq.{row['id']}",
                    body={"status": "failed", "attempts": int(row.get("attempts") or 0) + 1,
                          "last_error": error_cls or status}, prefer="return=minimal")
            except Exception:  # noqa: BLE001
                pass

    outcome = derive_outcome(read_state=outbox_read.state, evaluated_n=evaluated_n,
                             unevaluable_n=unevaluable_n, failed_n=failed_n, degraded_n=degraded_n)

    receipt_written = False
    if not dry_run and run_uuid is not None:
        source_asof = max(fired_ats) if fired_ats else None
        receipt_written = close_receipt(run_uuid, outcome=outcome, evaluated_n=evaluated_n,
                                        fired_n=fired_n, unevaluable_n=unevaluable_n,
                                        source_asof=source_asof, error_class=None) and wrote

    return DrainResult(outcome=outcome, evaluated_n=evaluated_n, fired_n=fired_n,
                       unevaluable_n=unevaluable_n, deferred_n=deferred_n,
                       suppressed_n=suppressed_n, failed_n=failed_n,
                       category_unfiltered_n=category_unfiltered_n,
                       read_state=outbox_read.state, error_class=None,
                       run_id=run_id, receipt_written=receipt_written)
