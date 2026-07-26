"""tests/test_admin_email_center.py — admin/email_center.py (SEE W4, gates G3 + CSV).

Fully offline. One seam: ``admin.users._query`` — the Supabase Management-API SQL call
that carries every read AND write in this module — is replaced by a fake that records each
statement, so the real SQL construction (the segment fragments, the escaping, the paging,
the reconciliation) is what gets asserted. ``users.status()`` is forced configured so
nothing depends on an operator-local SUPABASE_ACCESS_TOKEN (#3553).

What is proven:
  * **G3** — the roster and the export both go through ``email_segments.where_sql``, so
    ``marketing_eligible`` carries its two exclusions into the actual SQL, and the export's
    row count equals the segment's count by construction rather than by coincidence;
  * **CSV correctness** — formula injection is neutralised, quoting survives commas,
    quotes and newlines, and the file opens with a UTF-8 BOM so Excel renders 中文;
  * **the suppression guards** — a removal needs confirm IN THE REQUEST, refuses to lift a
    bounce or a complaint, and is written to the operator action ledger;
  * every interpolated value goes through _lit/_uuid/_clamp — the search box included;
  * the HTTP layer: 401 unauthenticated, 403 on a write with no CSRF header.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from admin import actions, email_center as ec, users  # noqa: E402
from app import email_segments as seg  # noqa: E402

CID = "c0000000-0000-4000-8000-000000000001"


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _Q:
    """Records every SQL statement and answers from a scripted table set."""

    def __init__(self, people=None, suppression=None, campaigns=None, counts=None):
        self.sqls: list[str] = []
        self.people = people if people is not None else [_person()]
        self.suppression = suppression if suppression is not None else []
        self.campaigns = campaigns if campaigns is not None else []
        self.counts = counts or {k: 7 for k in seg.KEYS}
        self.campaign_status = "draft"

    def __call__(self, sql):
        self.sqls.append(sql)
        low = sql.lower()
        if "as auth_total" in low:
            return [{"auth_total": 30, "excluded_inactive": 3,
                     "excluded_no_email": 2, "roster": 25}]
        if "seg_all" in low:
            return [{f"seg_{k}": v for k, v in self.counts.items()}]
        if low.startswith("select count(*)::int as n from public.email_suppression"):
            return [{"n": len(self.suppression)}]
        if "from public.email_suppression s" in low:
            return list(self.suppression)
        if low.startswith("select reason, count(*)"):
            return [{"reason": "unsubscribe", "n": 2}]
        if "from public.email_suppression where email" in low:
            return list(self.suppression)
        if low.startswith("insert into public.email_suppression"):
            return self._upsert_suppression(sql)
        if low.startswith("delete from public.email_suppression"):
            return []
        if "from public.email_log l" in low:
            return [{"created_at": "2026-07-26 09:00", "template": "welcome",
                     "class": "marketing", "status": "skipped_no_smtp",
                     "detail": "MAIL_SMTP_* unset", "to_email": "a@example.com"}]
        if "from public.email_log" in low and "group by" in low:
            return [{"status": "skipped_no_smtp", "n": 4}]
        if "from public.email_log" in low:
            return [{"n": 0}]
        if low.startswith("insert into public.email_campaigns"):
            return [{"id": CID}]
        if low.startswith("update public.email_campaigns"):
            return [{"id": CID}] if self.campaign_status in sql else []
        if low.startswith("delete from public.email_campaigns"):
            return [{"id": CID}] if self.campaign_status == "draft" else []
        if "from public.email_campaigns c" in low:
            return list(self.campaigns)
        if "from public.email_campaigns" in low:
            return [{"id": CID, "segment": "marketing_eligible",
                     "status": self.campaign_status}]
        if "from auth.users u" in low:
            return list(self.people)
        raise AssertionError(f"unscripted SQL: {sql[:160]}")

    def _upsert_suppression(self, sql: str) -> list[dict]:
        """Model `on conflict (email) do update … where reason not in (…) returning reason`.

        Postgres runs the DO UPDATE only when the guard holds, and `returning` yields NO
        ROW when it does not — which is exactly the signal the console reads to report the
        reason actually in force. A fake that always overwrote could not tell a guarded
        upsert from an unguarded one, and that difference is the whole fix.
        """
        m = re.search(r"values \('([^']*)', '([^']*)'\)", sql)
        assert m, sql
        addr, reason = m.group(1), m.group(2)
        guard = re.search(r"where email_suppression\.reason not in \(([^)]*)\)", sql)
        hard = set(re.findall(r"'([^']*)'", guard.group(1))) if guard else set()
        row = next((r for r in self.suppression if r.get("email") == addr), None)
        if row is None:
            self.suppression.append({"email": addr, "reason": reason})
            return [{"reason": reason}]
        if row.get("reason") in hard:
            return []                       # the guard refused the write; the row stands
        row["reason"] = reason
        return [{"reason": reason}]

    def find(self, needle):
        return next(s for s in self.sqls if needle in s)

    def all(self, needle):
        return [s for s in self.sqls if needle in s]


def _person(**kw):
    row = {"user_id": "11111111-1111-4111-8111-111111111111", "email": "ada@example.com",
           "tier": "pro", "status": "active", "lang": "en", "marketing_opt_out": False,
           "suppressed": False, "suppression_reason": "", "joined": "2026-01-05"}
    row.update(kw)
    return row


@pytest.fixture
def wired(monkeypatch):
    q = _Q()
    monkeypatch.setattr(users, "status", lambda: {"configured": True, "project_ref": "x",
                                                  "reason": None, "setup_steps": []})
    monkeypatch.setattr(users, "_query", q)
    return q


@pytest.fixture
def ledger(monkeypatch):
    """Capture admin/actions.py writes without touching the real JSONL file."""
    rows: list[dict] = []
    monkeypatch.setattr(actions, "append_action",
                        lambda **kw: (rows.append(kw), kw)[1])
    monkeypatch.setattr(ec.actions, "append_action",
                        lambda **kw: (rows.append(kw), kw)[1])
    return rows


# ===========================================================================
# G3 — the roster asks email_segments for its WHERE, it does not write one
# ===========================================================================
def test_the_roster_query_carries_the_segment_fragment(wired):
    ec.panel(segment="marketing_eligible")
    roster = wired.find("order by u.created_at desc")
    assert seg.BY_KEY["marketing_eligible"].sql in roster
    assert "s.email is null" in roster
    assert "coalesce(p.marketing_opt_out, false) = false" in roster


def test_the_roster_joins_all_four_relations(wired):
    ec.panel()
    roster = wired.find("order by u.created_at desc")
    for alias in ("auth.users u", "public.user_entitlements e",
                  "public.email_prefs p", "public.email_suppression s"):
        assert alias in roster


def test_every_segment_is_counted_in_one_scan(wired):
    """One query with a filter per segment, so `paid` + `free` cannot fail to add up
    because somebody upgraded between two round trips."""
    ec.panel()
    counts = wired.find("seg_all")
    for key in seg.KEYS:
        assert f"as seg_{key}" in counts
    assert len(wired.all("seg_all")) == 1


def test_an_unknown_segment_falls_back_to_all_and_never_reaches_sql(wired):
    out = ec.panel(segment="'; drop table auth.users --")
    assert out["segment"] == "all"
    assert "drop table" not in " ".join(wired.sqls)


def test_the_counts_and_the_total_come_from_the_same_place(wired):
    wired.counts = {**{k: 3 for k in seg.KEYS}, "marketing_eligible": 11}
    out = ec.panel(segment="marketing_eligible")
    assert out["total"] == 11 == out["counts"]["marketing_eligible"]


# ===========================================================================
# The footing — the page shows its work
# ===========================================================================
def test_the_reconciliation_balances_and_relates_to_the_users_page(wired):
    """The Users page counts active accounts; the Entitlements roster counts every
    auth.users row including soft-deleted ones. Those two already disagree, so a third
    number with no derivation would be useless — this one carries its arithmetic."""
    out = ec.panel()
    f = out["foot"]
    assert f["auth_total"] == 30
    assert f["excluded_inactive"] + f["excluded_no_email"] + f["roster"] == f["auth_total"]
    assert f["balances"] is True
    assert f["users_page_total"] == 27          # auth_total - inactive
    assert f["roster"] == 25


def test_the_foot_query_uses_the_shared_active_and_mailable_clauses(wired):
    ec.panel()
    foot = wired.find("as auth_total")
    assert seg.ACTIVE_SQL in foot and seg.MAILABLE_SQL in foot


def test_a_roster_that_does_not_balance_is_reported_not_hidden(wired, monkeypatch):
    monkeypatch.setattr(users, "_query",
                        lambda sql: [{"auth_total": 30, "excluded_inactive": 1,
                                      "excluded_no_email": 1, "roster": 1}]
                        if "as auth_total" in sql else wired(sql))
    assert ec._foot()["balances"] is False


# ===========================================================================
# CSV
# ===========================================================================
def _rows(blob: bytes) -> list[list[str]]:
    text = blob.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def test_the_export_opens_with_a_utf8_bom(wired):
    """Without it, Excel on Windows decodes the file as the system codepage and every
    Chinese name in the export becomes mojibake."""
    name, blob = ec.export_csv("all")
    assert blob.startswith(b"\xef\xbb\xbf")
    assert name.endswith(".csv") and "all" in name


def test_chinese_survives_the_round_trip(wired):
    wired.people = [_person(email="爱达@example.com", lang="zh")]
    _name, blob = ec.export_csv("all")
    assert "爱达@example.com" in _rows(blob)[1][0]


@pytest.mark.parametrize("hostile", [
    "=cmd|'/c calc'!A1@example.com",
    "+1234@example.com",
    "-2+3@example.com",
    "@SUM(1,2)@example.com",
    "\t=1+1@example.com",
])
def test_formula_injection_is_neutralised(wired, hostile):
    """Quoting is not the whole problem: Excel, Sheets and LibreOffice all EXECUTE a cell
    whose first character is = + - @ (or a leading tab). Anyone can sign up with an
    address shaped like a formula, so the cell is prefixed with an apostrophe, which every
    spreadsheet reads as 'this is text' and a CSV parser sees as one leading character."""
    wired.people = [_person(email=hostile)]
    _name, blob = ec.export_csv("all")
    cell = _rows(blob)[1][0]
    assert cell.startswith("'"), cell
    assert not cell.lstrip("'").startswith(("=", "+", "-", "@", "\t", "\r")) or cell[0] == "'"


def test_a_benign_value_is_not_mangled(wired):
    wired.people = [_person(email="ada@example.com")]
    _name, blob = ec.export_csv("all")
    assert _rows(blob)[1][0] == "ada@example.com"


def test_commas_quotes_and_newlines_survive_quoting(wired):
    wired.people = [_person(suppression_reason='a,b "c" \n d')]
    _name, blob = ec.export_csv("all")
    rows = _rows(blob)
    assert rows[1][EC_COL("suppression_reason")] == 'a,b "c" \n d'


def EC_COL(name: str) -> int:
    return list(ec.EXPORT_COLUMNS).index(name)


def test_the_export_and_the_count_apply_THE_SAME_predicate(wired):
    """The gate, asserted on the two STATEMENTS rather than on the fixture.

    This test used to set both numbers to 3 itself and then assert 3 == 3, which is a
    tautology: the fake decided the answer, so the export could have carried any WHERE
    clause at all and it would still have passed. What actually has to hold is that the
    count's per-segment filter and the export's WHERE are the same predicate — base ∧
    segment — over the same join, and that is a property of the SQL.
    """
    key = "marketing_eligible"
    frag = seg.BY_KEY[key].sql
    ec.panel(segment=key)
    ec.export_csv(key)

    count_sql = wired.find(f"seg_{key}")
    export_sql = wired.find("limit 50001")

    # the count: `count(*) filter (where <frag>)` narrowed by a `where <BASE_SQL>`
    assert f"count(*) filter (where {frag})::int as seg_{key}" in count_sql
    assert f"where {seg.BASE_SQL}" in count_sql
    # the export: the composed clause, which IS base ∧ segment
    assert f"where {seg.where_sql(key)}" in export_sql
    assert seg.where_sql(key) == f"{seg.BASE_SQL} and ({frag})"
    # ...and neither statement carries a filter the other does not
    assert seg.JOIN_SQL in count_sql and seg.JOIN_SQL in export_sql


def test_the_export_says_so_when_it_is_only_the_top_of_a_segment(wired):
    """The cap was contradicted by the docstring above it: the export stopped at 50,000
    rows while `_counts` was uncapped, so a bigger segment produced a file that silently
    was not the segment. An operator about to mail a list has to be able to tell a
    complete one from a prefix, and the filename is the only part of a CSV that survives
    being opened in Excel."""
    wired.people = [_person(email=f"u{i}@example.com") for i in range(4)]
    name, blob = ec.export_csv("all", limit=3)

    assert "limit 4" in wired.find("limit 4"), "it asks for one more than it will write"
    assert len(_rows(blob)[1:]) == 3, "and writes exactly the cap"
    assert name.endswith("-first-3.csv"), name


def test_a_complete_export_is_not_labelled_as_a_prefix(wired):
    """The control: exactly at the cap is complete, so the plain name must survive."""
    wired.people = [_person(email=f"u{i}@example.com") for i in range(3)]
    name, _blob = ec.export_csv("all", limit=3)
    assert "-first-" not in name and name.endswith(".csv")


def test_the_export_header_is_the_declared_column_set(wired):
    _name, blob = ec.export_csv("all")
    assert _rows(blob)[0] == list(ec.EXPORT_COLUMNS)


def test_an_unknown_export_segment_is_an_error_not_a_full_dump(wired):
    """Failing open here would hand the operator every address on file under the label of
    a segment that does not exist."""
    out = ec.export_csv("everyone-ish")
    assert isinstance(out, dict) and out["ok"] is False
    assert not any("everyone-ish" in s for s in wired.sqls)


def test_the_export_search_is_escaped_like_the_roster(wired):
    ec.export_csv("all", q="o'brien")
    assert "ilike '%o''brien%'" in wired.find("limit 50001")


# ===========================================================================
# Suppression
# ===========================================================================
def test_adding_a_suppression_upserts_the_reason(wired):
    payload, code = ec.suppress("Ada@Example.com", "manual")
    assert code == 200 and payload["email"] == "ada@example.com"
    sql = wired.find("insert into public.email_suppression")
    assert "'ada@example.com'" in sql and "on conflict (email) do update" in sql


def test_an_invalid_address_is_refused_before_sql(wired):
    payload, code = ec.suppress("not-an-address", "manual")
    assert code == 400 and payload["ok"] is False
    assert not wired.all("insert into public.email_suppression")


def test_an_unknown_reason_is_refused(wired):
    payload, code = ec.suppress("a@example.com", "vibes")
    assert code == 400
    assert not wired.all("insert into public.email_suppression")


def test_removing_a_suppression_requires_confirm_in_the_request(wired, ledger):
    """A browser confirm() is a courtesy, not an authorisation — it is absent from a
    replayed or hand-rolled request. The server checks the flag itself."""
    payload, code = ec.unsuppress("a@example.com", confirm=False)
    assert code == 400 and "confirm=true" in payload["error"]
    assert not wired.all("delete from public.email_suppression")
    assert ledger == []


@pytest.mark.parametrize("reason", ["bounce", "complaint"])
def test_a_bounce_or_a_complaint_is_not_removable(wired, ledger, reason):
    """Those record what the address DID. Clearing one re-arms the exact send that cost us
    sending reputation."""
    wired.suppression = [{"email": "a@example.com", "reason": reason}]
    payload, code = ec.unsuppress("a@example.com", confirm=True)
    assert code == 409 and payload["reason"] == reason
    assert not wired.all("delete from public.email_suppression")
    assert ledger == []


@pytest.mark.parametrize("reason", ["unsubscribe", "manual"])
def test_a_liftable_suppression_is_removed_and_recorded(wired, ledger, reason):
    wired.suppression = [{"email": "a@example.com", "reason": reason}]
    payload, code = ec.unsuppress("a@example.com", confirm=True, operator="chris")
    assert code == 200 and payload["was"] == reason
    assert wired.all("delete from public.email_suppression")

    assert len(ledger) == 1, "a compliance-sensitive removal must leave a durable record"
    entry = ledger[0]
    assert entry["surface"] == "email_suppression:a@example.com"
    assert entry["action"] in actions.VALID_ACTIONS
    assert reason in entry["direction_note"] and "chris" in entry["direction_note"]


def test_removing_an_address_that_is_not_suppressed_is_a_404(wired, ledger):
    wired.suppression = []
    payload, code = ec.unsuppress("a@example.com", confirm=True)
    assert code == 404
    assert ledger == []


def test_the_suppression_search_is_escaped(wired):
    ec.suppression(q="o'brien")
    assert "ilike '%o''brien%'" in wired.find("from public.email_suppression s")


# ===========================================================================
# Campaigns
# ===========================================================================
def test_saving_packs_both_languages_into_the_two_columns(wired):
    payload, code = ec.campaign_action(
        "save", subject_en="What changed", subject_zh="本周更新",
        body_en="Hello.", body_zh="你好。", segment="marketing_eligible")
    assert code == 200 and payload["id"] == CID
    sql = wired.find("insert into public.email_campaigns")
    assert "What changed · 本周更新" in sql
    assert "Hello." in sql and "你好。" in sql and ec._zh_delim() in sql
    assert "'marketing_eligible'" in sql


def test_a_campaign_body_and_subject_are_required(wired):
    assert ec.campaign_action("save", subject_en="", body_en="x")[1] == 400
    assert ec.campaign_action("save", subject_en="x", body_en="")[1] == 400


def test_an_unknown_segment_is_refused_at_save(wired):
    payload, code = ec.campaign_action("save", subject_en="s", body_en="b",
                                       segment="everyone-ish")
    assert code == 400
    assert not wired.all("insert into public.email_campaigns")


def test_a_quote_in_the_subject_is_escaped_not_executed(wired):
    ec.campaign_action("save", subject_en="Ada's week", subject_zh="本周",
                       body_en="hi", body_zh="嗨", segment="all")
    assert "'Ada''s week · 本周'" in wired.find("insert into public.email_campaigns")


def test_only_a_draft_can_be_queued(wired):
    wired.campaign_status = "sending"
    payload, code = ec.campaign_action("queue", campaign_id=CID)
    assert code == 409


def test_queueing_records_the_planned_size_without_sending(wired):
    """queued_n is a PLAN, not a promise: the drain re-resolves membership and re-checks
    suppression per recipient, so the outcome counters may differ — and nothing on this
    console touches a relay."""
    wired.campaign_status = "draft"
    wired.counts = {**{k: 0 for k in seg.KEYS}, "marketing_eligible": 12}
    payload, code = ec.campaign_action("queue", campaign_id=CID)
    assert code == 200 and payload["queued_n"] == 12
    assert "status = 'queued', queued_n = 12" in wired.find("update public.email_campaigns")


def test_a_bad_campaign_id_never_reaches_sql(wired):
    payload, code = ec.campaign_action("abort", campaign_id="'; drop table x --")
    assert code == 400
    assert not any("drop table" in s for s in wired.sqls)


def test_abort_only_applies_to_a_live_campaign(wired):
    wired.campaign_status = "queued"
    payload, code = ec.campaign_action("abort", campaign_id=CID)
    assert code == 200 and payload["status"] == "aborted"
    assert "status in ('queued','sending')" in wired.find("set status = 'aborted'")


def test_an_unknown_campaign_action_is_refused(wired):
    payload, code = ec.campaign_action("launch_the_missiles", campaign_id=CID)
    assert code == 400


# ---- preview --------------------------------------------------------------- #
def test_preview_renders_through_the_real_sender_and_stores_nothing(wired):
    """A preview that used its own renderer could drift from what the drain sends, so it
    goes through marketing_emails.campaign_message itself."""
    payload, code = ec.campaign_action(
        "preview", subject_en="What changed", subject_zh="本周更新",
        body_en="Sector breadth is live.\n\n[Open the Terminal](https://www.mastermind-x.com/terminal.html)",
        body_zh="板块广度已上线。\n\n[打开终端](https://www.mastermind-x.com/terminal.html)")
    assert code == 200 and payload["ok"] is True
    assert payload["subject"] == "What changed · 本周更新"
    assert "Sector breadth is live." in payload["text"]
    assert "板块广度已上线。" in payload["text"]
    assert payload["cta"]["url"] == "https://www.mastermind-x.com/terminal.html"
    assert payload["paragraphs"] == 1 and payload["zh_paragraphs"] == 1
    assert payload["mirrored"] is False
    # nothing was written
    assert not wired.all("insert into public.email_campaigns")
    assert not wired.all("update public.email_campaigns")


def test_preview_flags_a_missing_chinese_half(wired):
    """A one-language body is mirrored into both halves rather than shipping a blank 中文
    section — the operator should be told, not surprised in someone's inbox."""
    payload, code = ec.campaign_action("preview", subject_en="Hi", body_en="English only.")
    assert code == 200 and payload["mirrored"] is True


def test_preview_reports_no_cta_when_the_link_line_is_malformed(wired):
    payload, code = ec.campaign_action(
        "preview", subject_en="Hi", body_en="text\n\n[Bad](javascript:alert(1))")
    assert code == 200 and payload["cta"] is None


def test_preview_needs_a_subject_and_a_body(wired):
    assert ec.campaign_action("preview", subject_en="", body_en="x")[1] == 400
    assert ec.campaign_action("preview", subject_en="x", body_en="")[1] == 400


# ===========================================================================
# The SMTP card
# ===========================================================================
def test_the_mail_card_reports_mail_off_honestly(wired, monkeypatch):
    """In mail-off mode every send lands a clean `skipped_no_smtp` row, which looks
    exactly like a working system until you read the status column."""
    for k in ("MAIL_SMTP_HOST", "MAIL_SMTP_USER", "MAIL_SMTP_PASS", "MAIL_FROM"):
        monkeypatch.delenv(k, raising=False)
    out = ec.mail_status()
    assert out["configured"] is False
    assert out["recent"] and out["recent"][0]["status"] == "skipped_no_smtp"
    assert out["last_30d"] == {"skipped_no_smtp": 4}
    assert "parked" in out


# ===========================================================================
# Escaping helpers
# ===========================================================================
def test_lit_caps_strips_nul_and_doubles_quotes():
    assert ec._lit("a'b", maxlen=99) == "'a''b'"
    assert ec._lit("a\x00b", maxlen=99) == "'ab'"
    assert ec._lit("x" * 50, maxlen=5) == "'xxxxx'"
    assert ec._lit(None, maxlen=9) == "''"


def test_uuid_guard():
    good = CID
    assert ec._uuid(good) == good
    for bad in ("", None, "abc", good + "x", "'; drop --"):
        assert ec._uuid(bad) is None


def test_the_search_needle_is_capped_before_quoting(wired):
    ec.panel(q="z" * 5000)
    roster = wired.find("order by u.created_at desc")
    assert "z" * ec.SEARCH_MAX in roster
    assert "z" * (ec.SEARCH_MAX + 1) not in roster


def test_paging_is_clamped(wired):
    out = ec.panel(page=-5, page_size=99999)
    assert out["page"] == 1 and out["page_size"] == 200


# ===========================================================================
# Live server — 401 unauthenticated, 403 write without CSRF
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


def test_email_center_routes_require_auth_and_csrf():
    import os

    from admin import auth

    old = {k: os.environ.get(k) for k in ("ADMIN_DEPLOYED", "ADMIN_PASSWORD",
                                          "ADMIN_SESSION_SECRET")}
    os.environ.update({"ADMIN_DEPLOYED": "1", "ADMIN_PASSWORD": "s3cret",
                       "ADMIN_SESSION_SECRET": "it-secret"})
    auth._attempts.clear()
    httpd, port = _server()
    try:
        for path in ("/api/email_center", "/api/email_center/suppression",
                     "/api/email_center/mail", "/api/email_center/campaigns",
                     "/api/email_center/export.csv?segment=all"):
            try:
                _req(port, path)
                raise AssertionError(f"expected 401 for unauthenticated GET {path}")
            except urllib.error.HTTPError as e:
                assert e.code == 401, path

        for path in ("/api/email_center/suppression", "/api/email_center/campaign"):
            try:
                _req(port, path, "POST", {"action": "add", "email": "a@example.com"})
                raise AssertionError(f"expected 401 for unauthenticated POST {path}")
            except urllib.error.HTTPError as e:
                assert e.code == 401, path

        r = _req(port, "/api/login", "POST", {"password": "s3cret"})
        jar = {}
        for c in (r.headers.get_all("Set-Cookie") or []):
            k, _, rest = c.partition("=")
            jar[k] = rest.split(";")[0]

        for path in ("/api/email_center/suppression", "/api/email_center/campaign"):
            try:
                _req(port, path, "POST", {"action": "add", "email": "a@example.com"},
                     cookies={auth.SESSION_COOKIE: jar[auth.SESSION_COOKIE],
                              auth.CSRF_COOKIE: jar[auth.CSRF_COOKIE]})
                raise AssertionError(f"expected 403 (missing CSRF header) for {path}")
            except urllib.error.HTTPError as e:
                assert e.code == 403 and "CSRF" in json.loads(e.read())["error"], path
    finally:
        httpd.shutdown()
        httpd.server_close()
        auth._attempts.clear()
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ===========================================================================
# The downgrade hole — the console documented the opposite guarantee three times
# ===========================================================================
@pytest.mark.parametrize("hard", ["bounce", "complaint"])
def test_a_hard_reason_cannot_be_overwritten_by_a_weaker_one(wired, ledger, hard):
    """THE FULL SEQUENCE the reviewer executed, as one test.

    1. suppress as `complaint` — recorded;
    2. try to remove it — the documented 409, "not removable here";
    3. RE-SUPPRESS THE SAME ADDRESS AS `manual` — this is the hole: `on conflict do
       update set reason = excluded.reason` fired unconditionally and rewrote the reason;
    4. remove it — now legal, and the operator ledger records the removal of a *manual*
       suppression, erasing every trace that a spam complaint had ever been filed.

    The `where` on the conflict clause is what makes step 3 a no-op, and steps 2 and 4 the
    same answer. The row must survive step 3 either way — refusing the downgrade may never
    mean dropping the suppression.
    """
    payload, code = ec.suppress("a@example.com", hard)
    assert code == 200 and payload["reason"] == hard

    _p, code = ec.unsuppress("a@example.com", confirm=True)
    assert code == 409, "the documented refusal"

    payload, code = ec.suppress("a@example.com", "manual")
    assert code == 200
    assert payload["reason"] == hard, "the reason on file, not the one asked for"
    assert payload.get("kept") is True and "requested" in payload
    assert wired.suppression == [{"email": "a@example.com", "reason": hard}], \
        "the row stands, and it stands at its hard reason"

    _p, code = ec.unsuppress("a@example.com", confirm=True)
    assert code == 409, "and the refusal cannot be unlocked by re-suppressing"
    assert ledger == [], "nothing was lifted, so nothing may be recorded as lifted"


def test_the_guard_is_in_the_statement_not_only_in_the_python(wired):
    """Read-then-write would race two operators; the guard has to be inside the one
    statement Postgres executes."""
    ec.suppress("a@example.com", "manual")
    sql = wired.find("insert into public.email_suppression")
    assert "on conflict (email) do update set reason = excluded.reason" in sql
    assert f"where email_suppression.reason not in {seg.HARD_REASONS_SQL}" in sql
    assert "returning reason" in sql


def test_a_soft_reason_still_upgrades_to_a_hard_one(wired):
    """The guard is one-directional on purpose: a bounce webhook must be able to promote
    an existing `unsubscribe` row, because that records something new about the ADDRESS."""
    ec.suppress("a@example.com", "unsubscribe")
    payload, code = ec.suppress("a@example.com", "complaint")
    assert code == 200 and payload["reason"] == "complaint"
    assert wired.suppression == [{"email": "a@example.com", "reason": "complaint"}]


def test_the_two_reason_lists_come_from_one_place(wired):
    """The console and the public unsubscribe page both decide what "not removable" means.
    Two hand-written copies is how they came apart the first time."""
    from app import unsubscribe as unsub

    assert set(ec.LIFTABLE) == set(seg.SOFT_REASONS) == set(unsub.RESUBSCRIBABLE)
    assert set(ec.VALID_REASONS) == set(seg.REASONS)
    assert set(ec.LIFTABLE) & set(seg.HARD_REASONS) == set()


# ===========================================================================
# The bilingual subject is a DELIMITED format, so the delimiter is reserved
# ===========================================================================
def test_a_subject_half_carrying_the_separator_is_refused(wired):
    """`EN · ZH` lives in one column, so a half that contains ' · ' is ambiguous and the
    renderer split it in the wrong place — shipping part of an English headline as the
    Chinese one. Refused at compose time, in plain words, rather than silently rewritten."""
    payload, code = ec.campaign_action(
        "save", subject_en="Q3 · Q4 outlook", subject_zh="三四季度展望",
        body_en="hi", body_zh="嗨", segment="all")
    assert code == 400
    assert "·" in payload["error"]
    assert not wired.all("insert into public.email_campaigns")

    payload, code = ec.campaign_action(
        "preview", subject_en="fine", subject_zh="也 · 不行", body_en="hi", body_zh="嗨")
    assert code == 400


def test_an_ordinary_middot_is_not_refused(wired):
    """The reserved mark is the separator WITH its spaces. A middot inside a word, or an
    ordinary bullet, is somebody's headline and must survive."""
    _p, code = ec.campaign_action(
        "save", subject_en="A·B channel check", subject_zh="A·B 渠道核查",
        body_en="hi", body_zh="嗨", segment="all")
    assert code == 200
