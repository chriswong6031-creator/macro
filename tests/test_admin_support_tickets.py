"""tests/test_admin_support_tickets.py — admin/support_tickets.py (SEE W1 operator console).

Fully offline. One seam: ``admin.users._query`` — the Supabase Management-API SQL call
that carries BOTH the reads and the writes for this module — is replaced by a scripted
fake that records every statement, so the real SQL construction (filters, paging, quoting,
the RETURNING insert, the status update) is what gets asserted. ``users.status()`` is
forced configured so nothing depends on an operator-local SUPABASE_ACCESS_TOKEN (#3553).

Coverage maps to the mission's asks: list filter + pagination + search escaping; detail
with its thread; the legal/illegal transition matrix; reply appending a message, calling
the mailer, and setting ``emailed`` from the real result; and the HTTP layer via the live
admin.server Handler (401 unauthenticated, 403 write without the CSRF header).
"""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin import auth, support_tickets, users  # noqa: E402

TID = "7f000000-0000-4000-8000-000000000001"
MID = "7f000000-0000-4000-8000-0000000000aa"


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _Q:
    """Records every SQL statement and answers from a scripted table set."""

    def __init__(self, ticket=None, messages=None, total=3, counts=None):
        self.sqls: list[str] = []
        self.ticket = ticket
        self.messages = messages if messages is not None else []
        self.total = total
        self.counts = counts if counts is not None else [
            {"status": "open", "n": 2}, {"status": "closed", "n": 1}]

    def __call__(self, sql):
        self.sqls.append(sql)
        low = sql.lower()
        if low.startswith("insert into public.support_ticket_messages"):
            return [{"id": MID}]
        if low.startswith("update "):
            return []
        # NOTE order: the status summary ALSO contains "count(*)::int as n from
        # public.support_tickets", so the group-by branch must be tested first.
        if "group by 1" in low:
            return list(self.counts)
        if "count(*)::int as n from public.support_tickets" in low:
            return [{"n": self.total}]
        if "from public.support_ticket_messages m" in low:
            return list(self.messages)
        if "from public.support_tickets t" in low:
            return [dict(self.ticket)] if self.ticket else []
        raise AssertionError(f"unscripted SQL: {sql[:120]}")

    def find(self, needle):
        return next(s for s in self.sqls if needle in s)


def _ticket(**kw):
    row = {"id": TID, "status": "open", "email": "ada@example.com",
           "subject": "Card declined", "topic": "billing", "tier": "pro",
           "lang": "en", "user_id": None,
           "created_at": "2026-07-25 09:00", "updated_at": "2026-07-25 09:00"}
    row.update(kw)
    return row


@pytest.fixture
def wired(monkeypatch):
    q = _Q(ticket=_ticket())
    monkeypatch.setattr(users, "status", lambda: {"configured": True, "project_ref": "x",
                                                  "reason": None, "setup_steps": []})
    monkeypatch.setattr(users, "_query", q)
    return q


@pytest.fixture
def no_mail(monkeypatch):
    """Replace mailer.send with a recorder; returns the captured call list."""
    from app import mailer
    calls: list[dict] = []
    monkeypatch.setattr(mailer, "send", lambda **kw: (calls.append(kw), "sent")[1])
    return calls


# ===========================================================================
# Transition matrix (pure)
# ===========================================================================
def test_legal_actions_by_status():
    assert support_tickets.legal_actions("open") == ["reply", "resolve", "close"]
    assert support_tickets.legal_actions("pending") == ["reply", "resolve", "close"]
    assert support_tickets.legal_actions("resolved") == ["close", "reopen"]
    assert support_tickets.legal_actions("closed") == ["reopen"]
    assert support_tickets.legal_actions("nonsense") == []


def test_is_legal_rejects_unknown_action_and_status():
    assert support_tickets.is_legal("nuke", "open") is False
    assert support_tickets.is_legal("reply", "closed") is False
    assert support_tickets.is_legal("reopen", "open") is False
    assert support_tickets.is_legal("reply", "") is False


def test_next_status_map():
    assert support_tickets.next_status("reply") == "pending"
    assert support_tickets.next_status("resolve") == "resolved"
    assert support_tickets.next_status("close") == "closed"
    assert support_tickets.next_status("reopen") == "open"
    assert support_tickets.next_status("bogus") is None


# ===========================================================================
# READ — list
# ===========================================================================
def test_panel_lists_newest_first_with_counts(wired):
    q = wired
    q.ticket = _ticket()
    out = support_tickets.panel()
    assert out["ok"] is True
    assert out["tickets"][0]["email"] == "ada@example.com"
    assert out["counts"] == {"open": 2, "closed": 1}
    assert out["open_count"] == 2
    assert out["total"] == 3 and out["pages"] == 1
    rows = q.find("t.subject")
    assert "order by t.created_at desc" in rows
    # no join: the tier/lang snapshot lives on the ticket row
    assert "join" not in rows.lower()


def test_panel_status_filter_is_allow_listed(wired):
    q = wired
    support_tickets.panel(status="closed")
    assert "t.status = 'closed'" in q.find("t.subject")
    q.sqls.clear()
    support_tickets.panel(status="'; drop table support_tickets; --")
    rows = q.find("t.subject")
    assert "drop table" not in rows and "t.status =" not in rows


def test_panel_search_escapes_quotes(wired):
    q = wired
    support_tickets.panel(q="o'brien")
    rows = q.find("t.subject")
    assert "%o''brien%" in rows and "ilike" in rows


def test_panel_pagination_offsets(wired):
    q = wired
    out = support_tickets.panel(page=3, page_size=25)
    rows = q.find("t.subject")
    assert "limit 25" in rows and "offset 50" in rows
    assert out["page"] == 3 and out["page_size"] == 25


def test_panel_clamps_absurd_paging(wired):
    q = wired
    out = support_tickets.panel(page=-4, page_size=9999)
    assert out["page"] == 1 and out["page_size"] == 200


def test_panel_not_configured_returns_setup_steps(monkeypatch):
    monkeypatch.setattr(users, "status",
                        lambda: {"configured": False, "reason": "no PAT", "setup_steps": ["s"]})
    out = support_tickets.panel()
    assert out["ok"] is False and out["reason"] == "no PAT"


def test_panel_query_error_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(users, "status", lambda: {"configured": True})
    monkeypatch.setattr(users, "_query",
                        lambda sql: (_ for _ in ()).throw(RuntimeError("HTTP 500")))
    out = support_tickets.panel()
    assert out["ok"] is False and "HTTP 500" in out["error"]


# ===========================================================================
# READ — detail
# ===========================================================================
def test_detail_returns_ticket_thread_and_legal_actions(wired):
    q = wired
    q.messages = [
        {"id": "m1", "created_at": "2026-07-25 09:00", "author": "user",
         "body": "help", "emailed": False},
        {"id": "m2", "created_at": "2026-07-25 10:00", "author": "operator",
         "body": "on it", "emailed": True},
    ]
    out = support_tickets.detail(TID)
    assert out["ok"] is True
    assert out["ticket"]["subject"] == "Card declined"
    assert [m["author"] for m in out["messages"]] == ["user", "operator"]
    assert out["legal_actions"] == ["reply", "resolve", "close"]
    assert "order by m.created_at asc" in q.find("from public.support_ticket_messages m")


def test_detail_rejects_a_non_uuid_id(wired):
    q = wired
    out = support_tickets.detail("'; drop table support_tickets; --")
    assert out["ok"] is False and out["error"] == "invalid ticket id"
    assert q.sqls == []          # nothing reached SQL


def test_detail_missing_ticket(wired):
    q = wired
    q.ticket = None
    out = support_tickets.detail(TID)
    assert out["ok"] is False and out["error"] == "ticket not found"


# ===========================================================================
# WRITE — state transitions
# ===========================================================================
@pytest.mark.parametrize("current,action,target", [
    ("open", "resolve", "resolved"),
    ("pending", "resolve", "resolved"),
    ("open", "close", "closed"),
    ("resolved", "close", "closed"),
    ("resolved", "reopen", "open"),
    ("closed", "reopen", "open"),
])
def test_legal_transitions_update_the_row(wired, current, action, target):
    q = wired
    q.ticket = _ticket(status=current)
    payload, code = support_tickets.act(TID, action)
    assert code == 200 and payload["ok"] is True
    assert payload["from_status"] == current and payload["status"] == target
    upd = q.find("update public.support_tickets")
    assert f"status = '{target}'" in upd and f"where id = '{TID}'" in upd
    assert "updated_at = now()" in upd


@pytest.mark.parametrize("current,action", [
    ("closed", "reply"), ("resolved", "reply"),
    ("open", "reopen"), ("closed", "close"), ("closed", "resolve"),
])
def test_illegal_transitions_are_refused_with_the_legal_set(wired, current, action):
    q = wired
    q.ticket = _ticket(status=current)
    payload, code = support_tickets.act(TID, action)
    assert code == 400 and payload["ok"] is False
    assert payload["current_status"] == current
    assert payload["legal_actions"] == support_tickets.legal_actions(current)
    assert not any(s.lower().startswith("update ") for s in q.sqls)


def test_unknown_action_and_bad_id_rejected(wired):
    q = wired
    _p, code = support_tickets.act(TID, "delete_everything")
    assert code == 400
    _p, code = support_tickets.act("not-a-uuid", "close")
    assert code == 400
    assert q.sqls == []


def test_missing_ticket_is_404(wired):
    q = wired
    q.ticket = None
    _p, code = support_tickets.act(TID, "close")
    assert code == 404


def test_transition_legality_is_read_from_the_db_not_the_client(wired):
    """Two operator tabs cannot race a ticket into an illegal state."""
    q = wired
    q.ticket = _ticket(status="closed")     # someone else already closed it
    payload, code = support_tickets.act(TID, "resolve")
    assert code == 400 and payload["current_status"] == "closed"


def test_not_configured_is_503(monkeypatch):
    monkeypatch.setattr(users, "status",
                        lambda: {"configured": False, "reason": "no PAT", "setup_steps": []})
    _p, code = support_tickets.act(TID, "close")
    assert code == 503


# ===========================================================================
# WRITE — reply (append, then mail, then flag)
# ===========================================================================
def test_reply_appends_message_emails_and_sets_emailed(wired, no_mail):
    q = wired
    payload, code = support_tickets.act(TID, "reply", "We refunded the failed charge.")
    assert code == 200 and payload["ok"] is True
    assert payload["status"] == "pending" and payload["message_id"] == MID
    assert payload["emailed"] is True and payload["email_status"] == "sent"

    ins = q.find("insert into public.support_ticket_messages")
    assert "'operator'" in ins and "We refunded the failed charge." in ins
    assert "returning id" in ins

    assert len(no_mail) == 1
    call = no_mail[0]
    assert call["template"] == "ticket_reply" and call["cls"] == "transactional"
    assert call["idem_key"] == f"ticket-reply:{MID}"
    assert call["to_email"] == "ada@example.com"
    assert "Card declined" in call["subject"]

    flag = q.find("update public.support_ticket_messages")
    assert "emailed = true" in flag and MID in flag


def test_reply_with_mail_off_still_records_the_message(wired, monkeypatch):
    """Mail-off must be VISIBLE in the thread, not silently lost."""
    q = wired
    from app import mailer
    monkeypatch.setattr(mailer, "send", lambda **kw: "skipped_no_smtp")
    payload, code = support_tickets.act(TID, "reply", "answered")
    assert code == 200
    assert payload["emailed"] is False and payload["email_status"] == "skipped_no_smtp"
    q.find("insert into public.support_ticket_messages")           # recorded anyway
    assert not any("emailed = true" in s for s in q.sqls)          # …but not flagged sent
    assert "status = 'pending'" in q.find("update public.support_tickets")


def test_reply_survives_an_exploding_mailer(wired, monkeypatch):
    q = wired
    from app import mailer
    monkeypatch.setattr(mailer, "send",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("relay exploded")))
    payload, code = support_tickets.act(TID, "reply", "answered")
    assert code == 200 and payload["email_status"] == "failed" and payload["emailed"] is False


@pytest.mark.parametrize("body", ["", "   ", None, "x" * (support_tickets.REPLY_MAX + 1)])
def test_reply_body_is_validated(wired, body):
    q = wired
    _p, code = support_tickets.act(TID, "reply", body)
    assert code == 400
    assert not any(s.lower().startswith("insert") for s in q.sqls)


def test_reply_body_quotes_are_escaped(wired, no_mail):
    q = wired
    support_tickets.act(TID, "reply", "it's fixed'; drop table support_tickets; --")
    ins = q.find("insert into public.support_ticket_messages")
    assert "it''s fixed''; drop table support_tickets; --" in ins
    # the literal is closed correctly: an odd number of quotes would break the statement
    assert ins.count("'") % 2 == 0


def test_reply_passes_the_user_id_for_the_ledger(wired, no_mail):
    q = wired
    q.ticket = _ticket(user_id="22222222-2222-2222-2222-222222222222")
    support_tickets.act(TID, "reply", "hello")
    assert no_mail[0]["user_id"] == "22222222-2222-2222-2222-222222222222"


# ===========================================================================
# _lit / _uuid guards
# ===========================================================================
def test_lit_caps_strips_nul_and_doubles_quotes():
    assert support_tickets._lit("a'b", maxlen=99) == "'a''b'"
    assert support_tickets._lit("a\x00b", maxlen=99) == "'ab'"
    assert support_tickets._lit("x" * 50, maxlen=5) == "'xxxxx'"
    assert support_tickets._lit(None, maxlen=9) == "''"


def test_uuid_guard():
    assert support_tickets._uuid(TID) == TID
    for bad in ("", None, "abc", TID + "x", "'; drop --", "7f000000_0000_4000_8000_000000000001"):
        assert support_tickets._uuid(bad) is None


# ===========================================================================
# Live server auth — 401 (no session) / 403 (write missing CSRF)
# ===========================================================================
def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                __import__("admin.server", fromlist=["Handler"]).Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _req(port, path, method="GET", body=None, cookies=None, headers=None):
    h = dict(headers or {})
    if body is not None:
        h["Content-Type"] = "application/json"
    if cookies:
        h["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                 headers=h, method=method)
    return urllib.request.urlopen(req, timeout=10)


def test_support_routes_require_auth_and_csrf():
    import os
    old = {k: os.environ.get(k) for k in ("ADMIN_DEPLOYED", "ADMIN_PASSWORD", "ADMIN_SESSION_SECRET")}
    os.environ.update({"ADMIN_DEPLOYED": "1", "ADMIN_PASSWORD": "s3cret",
                       "ADMIN_SESSION_SECRET": "it-secret"})
    auth._attempts.clear()
    httpd, port = _server()
    try:
        for path in ("/api/support_tickets", f"/api/support_tickets/detail?id={TID}"):
            try:
                _req(port, path)
                raise AssertionError(f"expected 401 for unauthenticated GET {path}")
            except urllib.error.HTTPError as e:
                assert e.code == 401

        try:
            _req(port, "/api/support_tickets/action", "POST",
                 {"ticket_id": TID, "action": "close"})
            raise AssertionError("expected 401 for unauthenticated POST")
        except urllib.error.HTTPError as e:
            assert e.code == 401

        r = _req(port, "/api/login", "POST", {"password": "s3cret"})
        jar = {}
        for c in (r.headers.get_all("Set-Cookie") or []):
            k, _, rest = c.partition("=")
            jar[k] = rest.split(";")[0]

        try:
            _req(port, "/api/support_tickets/action", "POST",
                 {"ticket_id": TID, "action": "close"},
                 cookies={auth.SESSION_COOKIE: jar[auth.SESSION_COOKIE],
                          auth.CSRF_COOKIE: jar[auth.CSRF_COOKIE]})
            raise AssertionError("expected 403 (missing CSRF header)")
        except urllib.error.HTTPError as e:
            assert e.code == 403 and "CSRF" in json.loads(e.read())["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()
        auth._attempts.clear()
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
