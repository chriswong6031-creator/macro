"""admin/email_center.py — the operator's email surface (SEE W4, masterplan R7).

Four things on one tab: who we can reach (roster + segments + CSV export), who has told
us to stop (the suppression manager), whether mail is even switched on (the SMTP card and
the last sends), and the campaign composer/queue.

**One data plane, no new secret.** Everything here runs through ``admin/users.py::_query``
— the Supabase **Management-API SQL** endpoint authenticated by the ``SUPABASE_ACCESS_TOKEN``
PAT the admin service already holds. That endpoint runs INSERT/UPDATE/DELETE as well as
SELECT, so the console needs no service-role JWT added to /etc/macro-admin.env. Same
choice, for the same reason, as ``admin/support_tickets.py``.

**Injection posture.** The Management endpoint takes a SQL string, not bound parameters.
Every interpolated value is either (a) an int through :func:`_clamp`, (b) a strict-regex
uuid through :func:`_uuid`, (c) a token resolved through a fixed allow-list, or (d) a
literal through :func:`_lit`, which caps length, strips NULs and doubles single quotes
(Postgres runs ``standard_conforming_strings=on``, so a doubled-quote literal closes
correctly and a backslash is just a backslash). The segment name is case (c): the
operator's string is used to LOOK UP a fragment authored in ``app/email_segments.py``,
never to build one — see :func:`app.email_segments.get`.

**Segments are not defined here.** ``app/email_segments.py`` declares each one once, as a
SQL fragment paired with a Python predicate, because ``app/marketing_emails.py`` has to
answer the same question on the other side of a different secret. In particular
``marketing_eligible`` excludes suppressed addresses and opted-out users BY CONSTRUCTION
(G3/G4) — this module cannot forget to apply that, because it never applies it: it asks
for a WHERE clause and the exclusion is inside it.

**The counts foot, and the page shows its work.** :func:`panel` returns a ``foot`` block
reconciling the roster against ``auth.users`` in full — total, minus inactive accounts,
minus accounts with no address, equals the roster — because "412 people" is a number an
operator has to be able to trust against the Users page before mailing them. The Users
page counts ``_ACTIVE`` accounts; the Entitlements roster counts every row including
soft-deleted ones; those two already disagree with each other, so a third number with no
derivation would have been useless.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timezone

from app import email_segments

from . import actions, users

log = logging.getLogger("macro.admin.email_center")

SEARCH_MAX = 120
SUBJECT_MAX = 200
BODY_MAX = 20_000
EMAIL_MAX = 320

VALID_REASONS = tuple(email_segments.REASONS)
#: Reasons an operator may lift from the console. A bounce or a complaint is evidence
#: about the ADDRESS, not a preference someone set, and clearing it re-arms the exact
#: send that damaged our sending reputation in the first place. Re-adding is always
#: available; un-recording a complaint is not.
#:
#: Read from ``app/email_segments.py`` rather than spelled again here, because the public
#: unsubscribe page holds the same list and the two came apart once already: this module
#: documented "not removable" three times while its INSERT quietly allowed a re-suppression
#: as `manual` to overwrite a `complaint`, after which the removal it forbids was legal.
LIFTABLE = tuple(email_segments.SOFT_REASONS)

CAMPAIGN_ACTIONS = frozenset({"preview", "save", "queue", "abort", "delete"})
SUPPRESSION_ACTIONS = frozenset({"add", "remove"})

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# Deliberately loose, matching app/support.py: a SHAPE check, not an RFC 5322 parser.
_EMAIL_RE = re.compile(r"^[^@\s,;]{1,128}@[^@\s,;.]+(\.[^@\s,;.]+)+$")

# Spreadsheet formula prefixes. A cell beginning with any of these is executed as a
# formula by Excel, Google Sheets and LibreOffice on open — so an address like
# `=HYPERLINK(...)` in an exported list becomes code running on the operator's machine.
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")

EXPORT_COLUMNS = ("email", "user_id", "tier", "status", "lang",
                  "marketing_opt_out", "suppressed", "suppression_reason", "joined")


# --------------------------------------------------------------------------- #
# SQL literal helpers (mirrors admin/support_tickets.py — same certified shapes)
# --------------------------------------------------------------------------- #
def _lit(value, *, maxlen: int) -> str:
    """A safe single-quoted SQL literal: length-capped, NUL-stripped, quotes doubled."""
    s = str(value if value is not None else "")[:maxlen].replace("\x00", "")
    return "'" + s.replace("'", "''") + "'"


def _uuid(value) -> str | None:
    """Return the value iff it is a well-formed uuid — else None (never interpolated)."""
    s = str(value or "").strip()
    return s if _UUID_RE.match(s) else None


def _clamp(v, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _not_configured() -> dict | None:
    st = users.status()
    return None if st.get("configured") else {"ok": False, **st}


def _search_clause(q: str | None) -> str | None:
    """An ILIKE fragment over the address, or None. Capped BEFORE quoting."""
    needle = str(q or "").strip()[:SEARCH_MAX]
    if not needle:
        return None
    return f"u.email ilike {_lit(f'%{needle}%', maxlen=SEARCH_MAX + 2)}"


# --------------------------------------------------------------------------- #
# READ — roster + segment counts + the reconciliation
# --------------------------------------------------------------------------- #
def _counts(search: str | None) -> dict:
    """Every segment's size in ONE scan.

    One query with a `filter (where …)` per segment rather than N queries: the numbers
    are then a single consistent snapshot, so `paid` + `free` cannot fail to add up
    because someone upgraded between two round trips.
    """
    cols = ", ".join(
        f"count(*) filter (where {seg.sql})::int as seg_{seg.key}"
        for seg in email_segments.SEGMENTS
    )
    where = email_segments.BASE_SQL + (f" and ({search})" if search else "")
    rows = users._query(f"select {cols} {email_segments.JOIN_SQL} where {where}")
    row = (rows or [{}])[0]
    return {seg.key: int(row.get(f"seg_{seg.key}") or 0) for seg in email_segments.SEGMENTS}


def _foot() -> dict:
    """Reconcile the roster against auth.users, in one scan.

    ``auth_total == excluded_inactive + excluded_no_email + roster`` is arithmetic the
    operator can check on screen, and ``roster`` is what segment ``all`` reports. The
    Users page's own total is ``auth_total - excluded_inactive``, so the two surfaces are
    relatable without either one having to be wrong.
    """
    active, mailable = email_segments.ACTIVE_SQL, email_segments.MAILABLE_SQL
    rows = users._query(
        "select count(*)::int as auth_total, "
        f"count(*) filter (where not ({active}))::int as excluded_inactive, "
        f"count(*) filter (where ({active}) and not ({mailable}))::int as excluded_no_email, "
        f"count(*) filter (where {email_segments.BASE_SQL})::int as roster "
        "from auth.users u")
    row = (rows or [{}])[0]
    out = {k: int(row.get(k) or 0) for k in
           ("auth_total", "excluded_inactive", "excluded_no_email", "roster")}
    out["users_page_total"] = out["auth_total"] - out["excluded_inactive"]
    out["balances"] = (out["excluded_inactive"] + out["excluded_no_email"]
                       + out["roster"]) == out["auth_total"]
    return out


def _people(segment: str, search: str | None, page: int, page_size: int) -> list[dict]:
    offset = (page - 1) * page_size
    where = email_segments.where_sql(segment, extra=search)
    return users._query(
        "select u.id::text as user_id, u.email as email, "
        f"{email_segments.TIER_SQL} as tier, {email_segments.STATUS_SQL} as status, "
        "coalesce(p.lang,'') as lang, "
        "coalesce(p.marketing_opt_out, false) as marketing_opt_out, "
        "(s.email is not null) as suppressed, "
        "coalesce(s.reason,'') as suppression_reason, "
        "to_char(u.created_at,'YYYY-MM-DD') as joined "
        f"{email_segments.JOIN_SQL} where {where} "
        f"order by u.created_at desc limit {page_size} offset {offset}") or []


def panel(segment: str | None = None, q: str | None = None,
          page: int = 1, page_size: int = 50) -> dict:
    """The roster page: one segment's people, every segment's count, and the footing."""
    nc = _not_configured()
    if nc:
        return nc

    try:
        seg = email_segments.get(segment or email_segments.DEFAULT_KEY)
    except KeyError:
        seg = email_segments.get(email_segments.DEFAULT_KEY)

    page = _clamp(page, 1, 1, 100_000)
    page_size = _clamp(page_size, 50, 1, 200)
    search = _search_clause(q)

    try:
        counts = _counts(search)
        total = counts.get(seg.key, 0)
        rows = _people(seg.key, search, page, page_size)
        return {
            "ok": True,
            "segment": seg.key,
            "segments": email_segments.options(),
            "people": rows,
            "counts": counts,
            "foot": _foot(),
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------- #
# CSV export
# --------------------------------------------------------------------------- #
def _cell(value) -> str:
    """One CSV cell, guarded against spreadsheet formula injection.

    ``csv.writer`` already handles commas, embedded quotes and newlines — that is
    QUOTING, and quoting does nothing about the other half of the problem: Excel, Sheets
    and LibreOffice all EXECUTE a cell whose first character is ``= + - @`` (or a leading
    tab/CR) when the file is opened. An address is attacker-supplied — anyone can sign up
    as ``=cmd|'/c calc'!A1@example.com`` — so the value is prefixed with an apostrophe,
    which every spreadsheet reads as "the rest of this cell is text" and which a plain
    CSV parser sees as one harmless leading character.
    """
    s = "" if value is None else str(value)
    if s.startswith(_FORMULA_LEAD):
        return "'" + s
    return s


def export_csv(segment: str | None = None, q: str | None = None,
               limit: int = 50_000) -> tuple[str, bytes] | dict:
    """``(filename, utf-8 bytes)`` for a segment, or an error dict.

    The byte stream opens with a UTF-8 BOM: without it Excel on Windows decodes the file
    as the system codepage and every Chinese display name in the export becomes mojibake.
    Every other reader (Sheets, pandas, ``csv`` itself with ``utf-8-sig``) ignores it.

    The row count equals the segment count from :func:`panel` by construction — both come
    from ``email_segments.where_sql(segment)`` over the same join, and neither applies a
    filter the other does not — **up to** ``limit``. Past that the file is a prefix of the
    segment, and :func:`panel`'s count is uncapped, so the two numbers differ. That is now
    SAID rather than implied: the query asks for one row more than it will write, and a
    truncated file is named ``…-first-50000.csv``. An operator who mails a list has to be
    able to tell a complete one from the top of one, and a filename is the only part of a
    CSV that survives being opened in Excel.
    """
    nc = _not_configured()
    if nc:
        return nc
    try:
        seg = email_segments.get(segment or email_segments.DEFAULT_KEY)
    except KeyError:
        return {"ok": False, "error": f"unknown segment; expected one of {list(email_segments.KEYS)}"}

    limit = _clamp(limit, 50_000, 1, 200_000)
    search = _search_clause(q)
    try:
        rows = users._query(
            "select u.email as email, u.id::text as user_id, "
            f"{email_segments.TIER_SQL} as tier, {email_segments.STATUS_SQL} as status, "
            "coalesce(p.lang,'') as lang, "
            "coalesce(p.marketing_opt_out, false) as marketing_opt_out, "
            "(s.email is not null) as suppressed, "
            "coalesce(s.reason,'') as suppression_reason, "
            "to_char(u.created_at,'YYYY-MM-DD') as joined "
            f"{email_segments.JOIN_SQL} "
            f"where {email_segments.where_sql(seg.key, extra=search)} "
            f"order by u.created_at desc limit {limit + 1}") or []
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}

    truncated = len(rows) > limit
    rows = rows[:limit]
    if truncated:
        log.warning("email_center: %s export truncated at %d rows — the segment is larger",
                    seg.key, limit)

    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")     # CRLF per RFC 4180
    w.writerow(EXPORT_COLUMNS)
    for row in rows:
        w.writerow([_cell(row.get(c)) for c in EXPORT_COLUMNS])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    tail = f"-first-{limit}" if truncated else ""
    name = f"mastermind_{seg.key}_{stamp}{tail}.csv"
    return name, ("﻿" + buf.getvalue()).encode("utf-8")


# --------------------------------------------------------------------------- #
# Suppression manager
# --------------------------------------------------------------------------- #
def suppression(q: str | None = None, page: int = 1, page_size: int = 50) -> dict:
    """The kill list, newest first, searchable."""
    nc = _not_configured()
    if nc:
        return nc
    page = _clamp(page, 1, 1, 100_000)
    page_size = _clamp(page_size, 50, 1, 200)
    offset = (page - 1) * page_size

    where = "true"
    needle = str(q or "").strip()[:SEARCH_MAX]
    if needle:
        where = f"s.email ilike {_lit(f'%{needle}%', maxlen=SEARCH_MAX + 2)}"
    try:
        total = ((users._query(
            f"select count(*)::int as n from public.email_suppression s where {where}")
            or [{}])[0].get("n", 0))
        rows = users._query(
            "select s.email, s.reason, "
            "to_char(s.created_at,'YYYY-MM-DD HH24:MI') as created_at "
            f"from public.email_suppression s where {where} "
            f"order by s.created_at desc limit {page_size} offset {offset}") or []
        counts = users._query(
            "select reason, count(*)::int as n from public.email_suppression "
            "group by 1 order by 1") or []
        return {"ok": True, "rows": rows, "total": total, "page": page,
                "page_size": page_size, "pages": max(1, (total + page_size - 1) // page_size),
                "counts": {r["reason"]: r["n"] for r in counts if r.get("reason")},
                "liftable": list(LIFTABLE)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def suppress(email: str, reason: str = "manual", *, operator: str = "operator") -> tuple[dict, int]:
    """Add (or re-add) an address to the kill list. A hard reason is never downgraded.

    The ``where`` on the conflict clause is the whole point, and it closes a hole that
    made :func:`unsuppress`'s 409 decorative. Without it the sequence was: suppress an
    address as ``complaint``; try to remove it and get the documented "a 'complaint'
    suppression is not removable here" refusal; re-suppress the SAME address as
    ``manual``, which overwrote the reason; remove it — legally, this time — and watch the
    operator ledger record the removal of a *manual* suppression, with no trace anywhere
    that a spam complaint had ever been filed. Marketing then resumed to that address.

    The row is kept either way. Refusing the downgrade must never mean deleting the
    suppression, so the address stays on the kill list and the answer reports the reason
    actually in force rather than the one that was asked for.
    """
    nc = _not_configured()
    if nc:
        return nc, 503
    addr = str(email or "").strip().lower()[:EMAIL_MAX]
    if not _EMAIL_RE.match(addr):
        return {"ok": False, "error": "a valid email address is required"}, 400
    if reason not in VALID_REASONS:
        return {"ok": False, "error": f"reason must be one of {list(VALID_REASONS)}"}, 400
    lit = _lit(addr, maxlen=EMAIL_MAX)
    try:
        rows = users._query(
            "insert into public.email_suppression (email, reason) "
            f"values ({lit}, '{reason}') "
            "on conflict (email) do update set reason = excluded.reason "
            f"where email_suppression.reason not in {email_segments.HARD_REASONS_SQL} "
            "returning reason")
        if rows:
            kept = str(rows[0].get("reason") or reason)
        else:
            # No row came back: the conflict fired and the guard refused the write. Read
            # what is actually on file, so the console shows the truth and not the input.
            cur = users._query(
                f"select reason from public.email_suppression where email = {lit}") or []
            kept = str((cur[0] if cur else {}).get("reason") or reason)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}, 500
    if kept != reason:
        log.info("email_center: %s stays suppressed as '%s' — a '%s' does not overwrite it "
                 "(requested by %s)", addr, kept, reason, operator)
        return {"ok": True, "email": addr, "reason": kept, "requested": reason,
                "kept": True,
                "note": f"this address is already suppressed as '{kept}', which records what "
                        f"the address did rather than what its owner chose — a '{reason}' "
                        f"does not replace it"}, 200
    log.info("email_center: suppressed %s (%s) by %s", addr, kept, operator)
    return {"ok": True, "email": addr, "reason": kept}, 200


def unsuppress(email: str, *, confirm: bool = False,
               operator: str = "operator") -> tuple[dict, int]:
    """Remove an address from the kill list. Compliance-sensitive; guarded three ways.

    1. ``confirm`` must be true IN THE REQUEST, not merely in a browser dialog — a
       client-side ``confirm()`` is a UI courtesy, not an authorisation, and it is absent
       from a replayed or hand-rolled request.
    2. Only :data:`LIFTABLE` reasons may be lifted. A ``bounce`` or a ``complaint`` is
       evidence about the address, not a preference, and re-arming it is how a sending
       domain gets blocklisted.
    3. It is recorded in the operator action ledger (``admin/actions.py``) as well as the
       log, so "who turned this person's mail back on, and when" has a durable answer.
       ``overrode`` is the ledger verb that fits: the operator is overriding a recorded
       decision, which is exactly what this is.
    """
    nc = _not_configured()
    if nc:
        return nc, 503
    addr = str(email or "").strip().lower()[:EMAIL_MAX]
    if not addr:
        return {"ok": False, "error": "an email address is required"}, 400
    if not confirm:
        return {"ok": False,
                "error": "removing a suppression re-enables marketing email to this "
                         "address — resend with confirm=true"}, 400
    lit = _lit(addr, maxlen=EMAIL_MAX)
    try:
        rows = users._query(
            f"select email, reason from public.email_suppression where email = {lit}")
        if not rows:
            return {"ok": False, "error": "that address is not suppressed"}, 404
        reason = str(rows[0].get("reason") or "")
        if reason not in LIFTABLE:
            return {"ok": False,
                    "error": f"a '{reason}' suppression is not removable here — it records "
                             f"what the address did, not what its owner chose",
                    "reason": reason}, 409
        users._query(f"delete from public.email_suppression where email = {lit}")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}, 500

    actions.append_action(
        surface=f"email_suppression:{addr}",
        action="overrode",
        direction_note=f"removed a '{reason}' suppression — marketing email to this "
                       f"address is re-enabled (operator {operator})")
    log.info("email_center: suppression removed for %s (was %s) by %s", addr, reason, operator)
    return {"ok": True, "email": addr, "was": reason}, 200


# --------------------------------------------------------------------------- #
# SMTP status card
# --------------------------------------------------------------------------- #
def mail_status(limit: int = 20) -> dict:
    """Is mail on, and what were the last sends?

    The recent rows are the honest answer to "did my campaign go out": in mail-off mode
    every one of them says ``skipped_no_smtp``, which looks exactly like a working system
    until you read the status column. Showing both together is what stops an operator
    concluding a send succeeded because nothing went red.
    """
    from app import mailer  # noqa: PLC0415 — keeps admin importable without app deps

    out = {
        "ok": True,
        "configured": mailer.is_configured(),
        "host": mailer.smtp_host(),
        "from": mailer.mail_from(),
        "reply_to": mailer.reply_to(),
        "unsub_secret_set": bool(mailer.unsub_token("probe@example.com")),
        "recent": [],
    }
    nc = _not_configured()
    if nc:
        out["recent_error"] = nc.get("reason") or "not configured"
        return out
    limit = _clamp(limit, 20, 1, 100)
    try:
        out["recent"] = users._query(
            "select to_char(l.created_at,'YYYY-MM-DD HH24:MI') as created_at, "
            "l.template, l.class, l.status, coalesce(l.detail,'') as detail, l.to_email "
            f"from public.email_log l order by l.created_at desc limit {limit}") or []
        summary = users._query(
            "select status, count(*)::int as n from public.email_log "
            "where created_at > now() - interval '30 days' group by 1 order by 1") or []
        out["last_30d"] = {r["status"]: r["n"] for r in summary if r.get("status")}
        parked = users._query(
            "select count(*)::int as n from public.email_log "
            "where status = 'queued' and detail = 'suppression_lookup_failed'")
        out["parked"] = int((parked or [{}])[0].get("n") or 0)
    except Exception as e:  # noqa: BLE001
        out["recent_error"] = str(e)
    return out


# --------------------------------------------------------------------------- #
# Campaigns
# --------------------------------------------------------------------------- #
def campaigns(limit: int = 25) -> dict:
    nc = _not_configured()
    if nc:
        return nc
    limit = _clamp(limit, 25, 1, 100)
    try:
        rows = users._query(
            "select c.id::text as id, "
            "to_char(c.created_at,'YYYY-MM-DD HH24:MI') as created_at, "
            "c.subject, c.body_md, c.segment, c.status, "
            "c.queued_n, c.sent_n, c.skipped_n, c.failed_n "
            f"from public.email_campaigns c order by c.created_at desc limit {limit}") or []
        return {"ok": True, "campaigns": rows, "segments": email_segments.options(),
                "zh_delim": _zh_delim()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _zh_delim() -> str:
    from app import marketing_emails  # noqa: PLC0415
    return marketing_emails.ZH_DELIM


def _subject_sep() -> str:
    from app import marketing_emails  # noqa: PLC0415
    return marketing_emails.SUBJECT_SEP


def _compose_error(subject_en: str, subject_zh: str) -> str | None:
    """Why these two subject halves cannot be packed into one column, in plain words.

    ``EN · ZH`` is a delimited format stored in a single ``subject`` column, so a half that
    CONTAINS the delimiter is ambiguous: the renderer split at the first occurrence and
    shipped part of the English headline as the Chinese one. Refusing at compose time is
    the honest fix — silently rewriting somebody's headline is worse than telling them.
    """
    sep = _subject_sep()
    for value in (subject_en, subject_zh):
        if sep in " ".join(str(value or "").split()):
            return (f"a subject cannot contain '{sep.strip()}' with spaces around it — that "
                    f"is the mark that joins the English and 中文 halves. Use a comma, a "
                    f"dash, or a middot with no spaces")
    return None


def _compose(subject_en: str, subject_zh: str, body_en: str, body_zh: str) -> tuple[str, str]:
    """Pack the composer's four fields into the two columns the table has.

    ``email_campaigns`` carries one ``subject`` and one ``body_md``, and every send in
    this estate is dual-language (masterplan R4), so the two halves travel inside them
    under the same conventions the renderer reads back: ``EN · ZH`` for the subject (the
    format ``billing_emails._render`` already produces) and a delimiter line for the
    body. Storing JSON would have been tidier for the code and unreadable for the
    operator who opens the row in the Supabase table editor.

    Callers validate with :func:`_compose_error` first — an ambiguous subject is refused,
    not packed.
    """
    en = " ".join(str(subject_en or "").split())[:SUBJECT_MAX]
    zh = " ".join(str(subject_zh or "").split())[:SUBJECT_MAX]
    subject = f"{en}{_subject_sep()}{zh}" if (en and zh) else (en or zh)
    b_en = str(body_en or "").strip()[:BODY_MAX]
    b_zh = str(body_zh or "").strip()[:BODY_MAX]
    body = f"{b_en}\n\n{_zh_delim()}\n\n{b_zh}" if b_zh else b_en
    return subject, body


def _preview(subject_en: str, subject_zh: str,
             body_en: str, body_zh: str) -> tuple[dict, int]:
    """Render the draft through the REAL campaign renderer, without storing anything.

    The preview is the TEXT half of the message plus the parsed block structure, not an
    iframe of the HTML shell. Two reasons, in order:

    * The console's CSP is ``default-src 'none'`` with no ``frame-src``, so a srcdoc
      iframe is blocked — and widening a security policy to render a preview is the wrong
      trade for a nicety.
    * The text half IS the content the operator is authoring, in both languages, and the
      block census answers the question the markdown subset actually raises: "why is my
      button not showing?" A picture of the pinned shell would not — the shell never
      changes, and it is already proven by tests/test_email_templates.py.

    Rendered through ``marketing_emails.campaign_message`` itself, so a preview can never
    drift from what the drain would send.
    """
    from app import marketing_emails  # noqa: PLC0415

    bad = _compose_error(subject_en, subject_zh)
    if bad:
        return {"ok": False, "error": bad}, 400
    subject, body = _compose(subject_en, subject_zh, body_en, body_zh)
    if not subject:
        return {"ok": False, "error": "a subject is required"}, 400
    if not body.strip():
        return {"ok": False, "error": "a body is required"}, 400

    draft = {"subject": subject, "body_md": body}
    # A placeholder identity: the token is per-recipient, and no recipient is chosen yet.
    subj, _html, text = marketing_emails.campaign_message(draft, "preview")
    en_body, zh_body = marketing_emails.split_langs(body)
    en_blocks = marketing_emails._blocks(en_body)
    cta = next((b for b in en_blocks if b["kind"] == "button"), None)
    return {
        "ok": True,
        "subject": subj,
        "text": text,
        "paragraphs": sum(1 for b in en_blocks if b["kind"] == "p"),
        "zh_paragraphs": sum(1 for b in marketing_emails._blocks(zh_body) if b["kind"] == "p"),
        "cta": {"label": cta["label"], "url": cta["url"]} if cta else None,
        "mirrored": en_body == zh_body,
    }, 200


def campaign_action(action: str, *, campaign_id: str | None = None,
                    subject_en: str = "", subject_zh: str = "",
                    body_en: str = "", body_zh: str = "",
                    segment: str = "", operator: str = "operator") -> tuple[dict, int]:
    """One composer action. Returns (payload, http_status).

    ``save`` writes a draft (creating or updating). ``queue`` hands it to the sweeper.
    ``abort`` stops one that is sending. ``delete`` removes a draft only — a campaign that
    has sent to anyone keeps its row, because those counters are the only record that the
    send happened.
    """
    nc = _not_configured()
    if nc:
        return nc, 503
    action = (action or "").strip()
    if action not in CAMPAIGN_ACTIONS:
        return {"ok": False, "error": f"action must be one of {sorted(CAMPAIGN_ACTIONS)}"}, 400

    if action == "preview":
        return _preview(subject_en, subject_zh, body_en, body_zh)

    cid = _uuid(campaign_id) if campaign_id else None
    if action != "save" and not cid:
        return {"ok": False, "error": "a valid campaign id is required"}, 400

    try:
        if action == "save":
            bad = _compose_error(subject_en, subject_zh)
            if bad:
                return {"ok": False, "error": bad}, 400
            subject, body = _compose(subject_en, subject_zh, body_en, body_zh)
            if not subject:
                return {"ok": False, "error": "a subject is required"}, 400
            if not body.strip():
                return {"ok": False, "error": "a body is required"}, 400
            try:
                seg = email_segments.get(segment or email_segments.MARKETING_KEY).key
            except KeyError:
                return {"ok": False,
                        "error": f"unknown segment; expected one of {list(email_segments.KEYS)}"}, 400
            s_lit = _lit(subject, maxlen=SUBJECT_MAX * 2 + 3)
            b_lit = _lit(body, maxlen=BODY_MAX * 2 + 32)
            if cid:
                # Only a draft may be edited: rewriting the copy of a campaign that is
                # already sending would mean two different emails going out under one
                # record, and the counters would describe neither.
                rows = users._query(
                    f"update public.email_campaigns set subject = {s_lit}, body_md = {b_lit}, "
                    f"segment = '{seg}' where id = '{cid}' and status = 'draft' "
                    "returning id::text as id")
                if not rows:
                    return {"ok": False,
                            "error": "only a draft can be edited"}, 409
            else:
                rows = users._query(
                    "insert into public.email_campaigns (subject, body_md, segment, status) "
                    f"values ({s_lit}, {b_lit}, '{seg}', 'draft') returning id::text as id")
            new_id = (rows or [{}])[0].get("id")
            log.info("email_center: campaign %s saved by %s (segment=%s)", new_id, operator, seg)
            return {"ok": True, "id": new_id, "status": "draft", "segment": seg}, 200

        if action == "queue":
            rows = users._query(
                "select id::text as id, segment, status from public.email_campaigns "
                f"where id = '{cid}'")
            if not rows:
                return {"ok": False, "error": "campaign not found"}, 404
            if (rows[0].get("status") or "") != "draft":
                return {"ok": False,
                        "error": f"only a draft can be queued (this one is "
                                 f"{rows[0].get('status')})"}, 409
            seg = rows[0].get("segment") or email_segments.DEFAULT_KEY
            # queued_n is the segment size AT QUEUE TIME — a plan, not a promise. The
            # drain re-resolves membership and re-checks suppression per recipient, so
            # sent_n + skipped_n + failed_n is what actually happened and may differ.
            try:
                planned = _counts(None).get(email_segments.get(seg).key, 0)
            except Exception:  # noqa: BLE001
                planned = 0
            users._query(
                f"update public.email_campaigns set status = 'queued', queued_n = {int(planned)} "
                f"where id = '{cid}'")
            log.info("email_center: campaign %s queued by %s (%d planned)", cid, operator, planned)
            return {"ok": True, "id": cid, "status": "queued", "queued_n": planned}, 200

        if action == "abort":
            rows = users._query(
                f"update public.email_campaigns set status = 'aborted' where id = '{cid}' "
                "and status in ('queued','sending') returning id::text as id")
            if not rows:
                return {"ok": False, "error": "only a queued or sending campaign can be aborted"}, 409
            log.info("email_center: campaign %s aborted by %s", cid, operator)
            return {"ok": True, "id": cid, "status": "aborted"}, 200

        rows = users._query(
            f"delete from public.email_campaigns where id = '{cid}' and status = 'draft' "
            "returning id::text as id")
        if not rows:
            return {"ok": False, "error": "only a draft can be deleted"}, 409
        log.info("email_center: campaign %s deleted by %s", cid, operator)
        return {"ok": True, "id": cid, "status": "deleted"}, 200
    except Exception as e:  # noqa: BLE001
        log.warning("email_center: campaign %s failed (%s)", action, e)
        return {"ok": False, "error": str(e)}, 500
