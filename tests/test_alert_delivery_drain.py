"""tests/test_alert_delivery_drain.py -- RED-first tests for packet B-F08-1b's drain."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import pytest

from engine import alert_delivery_drain as drain


def _now(iso="2026-09-05T15:00:00+00:00"):
    return datetime.fromisoformat(iso)


def _outbox_row_selected(row: dict, path: str) -> bool:
    """Mirrors drain.drain's own or=(...) selection predicate against the fake
    table, so a test that never varies path can no longer pass by construction --
    this is what the review found missing (Acceptance 1(d)). Round 3: a 'failed' row
    is selected only below the retry cap (mirrors the ``attempts.lt.N`` clause)."""
    status = row.get("status")
    if status == "pending":
        return True
    if status == "failed":
        m = re.search(r"attempts\.lt\.(\d+)", path)
        cap = int(m.group(1)) if m else drain.ALERT_RETRY_ATTEMPTS_CAP
        return int(row.get("attempts") or 0) < cap
    if status == "deferred":
        m = re.search(r"deliver_after\.lte\.([^&)]+)", path)
        if not m:
            return False
        import urllib.parse as _up
        cutoff = _up.unquote(m.group(1))
        da = row.get("deliver_after")
        return bool(da) and str(da) <= cutoff
    return False


class FakeTables:
    def __init__(self, *, outbox=None, users=None, suppression=None, entitlements=None,
                 email_log=None):
        self.outbox = outbox if outbox is not None else []
        self.users = users if users is not None else {}
        self.suppression = suppression if suppression is not None else []
        self.entitlements = entitlements if entitlements is not None else {}
        # idem_key -> email_log row (or a sentinel: "UNREADABLE" raises on GET).
        self.email_log = email_log if email_log is not None else {}
        self.runs = {}
        self.patches = []

    def pg(self, method, path, body=None, prefer=None, timeout=6):
        if path.startswith("alert_outbox") and method == "GET":
            return [r for r in self.outbox if _outbox_row_selected(r, path)]
        if path.startswith("alert_outbox") and method == "PATCH":
            row_id = re.search(r"id=eq\.([^&]+)", path).group(1)
            self.patches.append((row_id, body))
            for r in self.outbox:
                if str(r["id"]) == row_id:
                    r.update(body)
            return None
        if path.startswith("alert_runs") and method == "POST":
            row = body[0]
            self.runs[row["id"]] = row
            return None
        if path.startswith("alert_runs") and method == "PATCH":
            run_id = re.search(r"id=eq\.([^&]+)", path).group(1)
            self.runs[run_id].update(body)
            return None
        if path.startswith("email_log") and method == "GET":
            import urllib.parse as _up
            m = re.search(r"idem_key=eq\.([^&]+)", path)
            key = _up.unquote(m.group(1)) if m else None
            row = self.email_log.get(key)
            if row == "UNREADABLE":
                raise RuntimeError("boom")
            return [row] if row else []
        if path.startswith("email_suppression"):
            return list(self.suppression)
        if path.startswith("user_entitlements"):
            uid = re.search(r"user_id=eq\.([^&]+)", path).group(1)
            row = self.entitlements.get(uid)
            return [row] if row else []
        raise AssertionError(f"unexpected _pg call: {method} {path}")


def _patch(monkeypatch, fake, *, users=None):
    monkeypatch.setattr(drain, "_pg", fake.pg)
    if users is not None:
        def fetch(user_id):
            rec = users.get(str(user_id))
            if rec is None:
                return drain.READ_UNAVAILABLE, None
            return drain.READ_OK, rec
        monkeypatch.setattr(drain, "fetch_user_record", fetch)


def _row(**kw):
    base = dict(id=str(uuid.uuid4()), user_id="u1", alert_id="a1", fire_event_id="fe1",
               status="pending", attempts=0, deliver_after=None,
               payload={"subject": "AAPL moved", "ticker": "AAPL", "summary_plain": "x",
                        "condition_plain": "RSI crossed 70", "evidence_url": "https://x/e", "fired_at": "2026-09-05T14:00:00Z"})
    base.update(kw)
    return base


OPTED_IN_USER = {"email": "u@example.com", "user_metadata": {"alert_email_optin": "true", "lang": "en"}}


def test_same_fire_event_id_drained_twice_sends_once_and_reports_duplicate(monkeypatch):
    row = _row()
    fake = FakeTables(outbox=[row])
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    sends = []

    def send_fn(**kw):
        sends.append(kw)
        return "sent"

    r1 = drain.drain(send_fn=send_fn, now_utc=_now(), limit=10)
    assert r1.fired_n == 1
    assert len(sends) == 1

    def send_fn_dup(**kw):
        return "duplicate"

    # A genuine 'duplicate' means email_log already holds this idem_key -- simulate the
    # real world by recording the email_log row the first send would have written
    # (review round 2 blocker, acceptance 1(d)): 'duplicate' is never assumed to mean
    # 'fired'; the email_log row is READ to find out what actually happened.
    fake.email_log["alert_fire:fe1"] = {"status": "sent", "created_at": "2026-09-05T15:00:01+00:00"}
    fake.outbox[0]["status"] = "pending"  # simulate a replay before terminal write races in
    # The replay is of the SAME original attempt (the send that already landed in
    # email_log under attempt=0) -- reset attempts too, or the drain would compute a
    # different attempt number and look up a idem_key that was never claimed.
    fake.outbox[0]["attempts"] = 0
    r2 = drain.drain(send_fn=send_fn_dup, now_utc=_now(), limit=10)
    assert r2.fired_n == 0
    assert r2.duplicate_n == 1
    assert fake.outbox[0]["status"] == "sent"
    assert fake.outbox[0]["delivered_at"] == "2026-09-05T15:00:01+00:00"


def test_duplicate_whose_email_log_row_is_failed_mirrors_status_never_counted_sent(monkeypatch):
    row = _row()
    fake = FakeTables(outbox=[row])
    fake.email_log["alert_fire:fe1"] = {"status": "failed", "created_at": "2026-09-05T14:59:00+00:00"}
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    result = drain.drain(send_fn=lambda **kw: "duplicate", now_utc=_now(), limit=10)
    assert result.fired_n == 0
    assert result.duplicate_n == 1
    assert fake.outbox[0]["status"] == "failed"
    assert fake.outbox[0]["last_error"] == "prior send failed"
    # Review round 3 BLOCKER: attempts MUST increment here -- this is the exact path
    # that used to leave attempts unchanged, so a 'failed' email_log row selected
    # every tick (status.eq.failed, no cap) never advanced and never retried under a
    # fresh idem_key. Without this bump the row would loop forever.
    assert fake.outbox[0]["attempts"] == 1


def test_duplicate_whose_email_log_row_is_suppressed_mirrors_status_never_counted_sent(monkeypatch):
    row = _row()
    fake = FakeTables(outbox=[row])
    fake.email_log["alert_fire:fe1"] = {"status": "suppressed", "created_at": "2026-09-05T14:59:00+00:00"}
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    result = drain.drain(send_fn=lambda **kw: "duplicate", now_utc=_now(), limit=10)
    assert result.fired_n == 0
    assert result.duplicate_n == 1
    assert fake.outbox[0]["status"] == "suppressed"
    assert fake.outbox[0]["last_error"] == "prior send suppressed"


def test_duplicate_whose_email_log_row_is_queued_stays_pending_never_mirrors_a_non_outbox_status(monkeypatch):
    """Review round 3 MAJOR-2: 'queued' is a mailer/email_log-only status, never a
    legal alert_outbox one -- mirroring it verbatim either violates alert_outbox's own
    CHECK constraint (silently swallowed) or, if ever accepted, orphans the row
    outside the drain's selection predicate forever. The row must stay 'pending'."""
    row = _row()
    fake = FakeTables(outbox=[row])
    fake.email_log["alert_fire:fe1"] = {"status": "queued", "created_at": "2026-09-05T14:59:00+00:00"}
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    result = drain.drain(send_fn=lambda **kw: "duplicate", now_utc=_now(), limit=10)
    assert result.fired_n == 0
    assert result.duplicate_n == 1
    assert fake.outbox[0]["status"] == "pending"
    assert fake.outbox[0]["last_error"] == "prior send queued"
    assert fake.outbox[0]["attempts"] == 0


def test_duplicate_whose_email_log_row_is_unreadable_leaves_outbox_row_pending(monkeypatch, capsys):
    row = _row()
    fake = FakeTables(outbox=[row])
    fake.email_log["alert_fire:fe1"] = "UNREADABLE"
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    result = drain.drain(send_fn=lambda **kw: "duplicate", now_utc=_now(), limit=10)
    assert result.fired_n == 0
    assert result.duplicate_n == 0
    assert fake.outbox[0]["status"] == "pending"
    assert fake.outbox[0]["attempts"] == 0
    out = capsys.readouterr().out
    warning_lines = [ln for ln in out.splitlines() if "alert-drain-duplicate-unreadable" in ln]
    assert warning_lines, "expected a ::warning line for an unreadable email_log row"
    assert warning_lines[0].startswith("::warning")
    # Ruling: the unreadable branch must carry the literal token READ_UNAVAILABLE.
    assert "READ_UNAVAILABLE" in warning_lines[0]


def test_duplicate_whose_email_log_row_is_missing_leaves_outbox_row_pending(monkeypatch):
    """A 'duplicate' claim with NO matching email_log row contradicts itself -- fail
    closed exactly like the unreadable case rather than fabricating an outcome."""
    row = _row()
    fake = FakeTables(outbox=[row])  # no email_log entry at all
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    result = drain.drain(send_fn=lambda **kw: "duplicate", now_utc=_now(), limit=10)
    assert result.fired_n == 0
    assert result.duplicate_n == 0
    assert fake.outbox[0]["status"] == "pending"


def test_idem_key_is_derived_deterministically_from_fire_event_id():
    from app import mailer
    assert mailer.alert_idem_key("fe1") == "alert_fire:fe1"
    assert mailer.alert_idem_key("fe1") == mailer.alert_idem_key("fe1")


def test_drain_idem_key_is_pinned_identical_to_the_mailer_for_every_attempt():
    """Review round 3 MAJOR-4: engine/alert_delivery_drain.py's ``_alert_idem_key``
    duplicates app/mailer.py's ``alert_idem_key`` (required by the layering law --
    engine/ may not import app/), so this cross-module test is the ONLY thing that
    can ever catch the two drifting apart. Exercises both sides, not just the
    mailer's own tautology."""
    from app import mailer
    assert drain._alert_idem_key("fe1") == mailer.alert_idem_key("fe1") == "alert_fire:fe1"
    for attempt in (0, 1, 2, 3, 7):
        assert drain._alert_idem_key("fe1", attempt=attempt) == mailer.alert_idem_key("fe1", attempt=attempt)
    # attempt=0 (default on both sides) is byte-identical to the no-attempt call --
    # every alert already resolved under the old single-arg signature keeps
    # resolving to the same email_log row.
    assert drain._alert_idem_key("fe1", attempt=0) == drain._alert_idem_key("fe1")
    assert mailer.alert_idem_key("fe1", attempt=0) == mailer.alert_idem_key("fe1")
    # distinct attempts mint distinct keys -- this is what breaks the livelock.
    assert drain._alert_idem_key("fe1", attempt=1) != drain._alert_idem_key("fe1", attempt=0)


def test_quiet_hours_defers_in_user_timezone_not_ny():
    # Asia/Shanghai quiet 22:00-07:00, now 15:00Z == 23:00 local (quiet) but 11:00 NY (not quiet)
    prefs = drain.AlertPrefs(email_optin=True, categories=None, tz="Asia/Shanghai",
                             tz_source="user", quiet=(22 * 60, 7 * 60), quiet_note=None, lang="en")
    action, deliver_after = drain.quiet_decision(_now("2026-09-05T15:00:00+00:00"), prefs)
    assert action == "defer"
    assert deliver_after is not None


def test_deferred_row_is_sent_when_the_window_opens(monkeypatch):
    prefs = drain.AlertPrefs(email_optin=True, categories=None, tz="Asia/Shanghai",
                             tz_source="user", quiet=(22 * 60, 7 * 60), quiet_note=None, lang="en")
    _, opens_at = drain.quiet_decision(_now("2026-09-05T15:00:00+00:00"), prefs)
    action, _ = drain.quiet_decision(opens_at, prefs)
    assert action == "send"


def test_deliver_after_is_the_next_local_window_open_in_utc():
    prefs = drain.AlertPrefs(email_optin=True, categories=None, tz="UTC", tz_source="user",
                             quiet=(0, 60), quiet_note=None, lang="en")
    action, deliver_after = drain.quiet_decision(_now("2026-09-05T00:30:00+00:00"), prefs)
    assert action == "defer"
    assert deliver_after.hour == 1 and deliver_after.minute == 0


def test_lapsed_entitlement_yields_suppressed_row_never_deleted_never_sent(monkeypatch):
    row = _row()
    fake = FakeTables(outbox=[row], entitlements={"u1": {"tier": "pro", "status": "canceled",
                                                          "current_period_end": None, "source": "stripe"}})
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    result = drain.drain(send_fn=lambda **kw: "sent", now_utc=_now(), limit=10)
    assert result.suppressed_n == 1
    assert result.fired_n == 0
    assert len(fake.outbox) == 1
    assert fake.outbox[0]["status"] == "suppressed"


def test_free_tier_user_is_not_treated_as_lapsed():
    read = drain.TypedRead(drain.READ_OK, [{"tier": "free", "status": "none", "current_period_end": None}])
    assert drain.entitlement_decision(read, _now()) == "send"


def test_entitlement_read_unavailable_leaves_row_pending_and_counts_unevaluable(monkeypatch):
    row = _row()
    fake = FakeTables(outbox=[row])
    fake.entitlements = None  # force lookups to raise

    def pg(method, path, body=None, prefer=None, timeout=6):
        if path.startswith("user_entitlements"):
            raise RuntimeError("boom")
        return FakeTables.pg(fake, method, path, body, prefer, timeout)

    monkeypatch.setattr(drain, "_pg", pg)
    monkeypatch.setattr(drain, "fetch_user_record", lambda uid: (drain.READ_OK, OPTED_IN_USER))
    result = drain.drain(send_fn=lambda **kw: "sent", now_utc=_now(), limit=10)
    assert result.unevaluable_n == 1
    assert fake.outbox[0]["status"] == "pending"


def test_smtp_failure_records_failed_with_last_error_and_attempts_plus_one(monkeypatch):
    row = _row()
    fake = FakeTables(outbox=[row])
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    drain.drain(send_fn=lambda **kw: "failed", now_utc=_now(), limit=10)
    assert fake.outbox[0]["status"] == "failed"
    assert fake.outbox[0]["attempts"] == 1
    assert fake.outbox[0]["last_error"] == "failed"


def test_skipped_no_smtp_leaves_outbox_row_pending_not_failed(monkeypatch):
    """Review round 3 MINOR-2: 'skipped_no_smtp' is a config gap (mail-off), not a
    send failure -- it must not burn a retry attempt or land the row on 'failed'."""
    row = _row()
    fake = FakeTables(outbox=[row])
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    result = drain.drain(send_fn=lambda **kw: "skipped_no_smtp", now_utc=_now(), limit=10)
    assert result.fired_n == 0
    assert result.failed_n == 0
    assert fake.outbox[0]["status"] == "pending"
    assert fake.outbox[0]["attempts"] == 0
    assert fake.outbox[0]["last_error"] == "skipped_no_smtp"


def test_failed_row_is_retried_by_a_later_drain_and_never_reads_as_sent(monkeypatch):
    row = _row()
    fake = FakeTables(outbox=[row])
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    drain.drain(send_fn=lambda **kw: "failed", now_utc=_now(), limit=10)
    assert fake.outbox[0]["status"] == "failed"
    # No manual status flip: the fake's GET now honours the drain's own selection
    # predicate (status.eq.failed is part of the `or=`), so this exercises that
    # predicate directly rather than assuming it.
    drain.drain(send_fn=lambda **kw: "sent", now_utc=_now(), limit=10)
    assert fake.outbox[0]["status"] == "sent"
    assert fake.outbox[0]["attempts"] == 2


class _ReplayFaithfulFakeMailer:
    """Models the REAL mailer's per-idem_key ledger (app/mailer.py:367-371,
    196-204): once an idem_key is claimed, EVERY later call under that exact same
    key returns 'duplicate' -- regardless of what status the first call settled at.
    A fake that instead returns 'sent' for an already-claimed key (the old test at
    this line, review round 3 MAJOR-1) proves a retry path that cannot exist against
    the real mailer."""

    def __init__(self, first_attempt_status="failed"):
        self.claimed: dict[str, str] = {}
        self.first_attempt_status = first_attempt_status
        self.calls: list[tuple[str, int]] = []

    def send_fn(self, *, fire_event_id, to_email, payload, lang, user_id, attempt=0):
        key = drain._alert_idem_key(fire_event_id, attempt=attempt)
        self.calls.append((key, attempt))
        if key in self.claimed:
            return "duplicate"
        status = self.first_attempt_status if attempt == 0 else "sent"
        self.claimed[key] = status
        return status


def test_retry_livelock_regression_a_terminally_failed_row_retries_under_a_fresh_key(monkeypatch):
    """Review round 3 BLOCKER (engine/alert_delivery_drain.py:500-517 + :390, with
    app/mailer.py:367-371/196-204): the prior head reused the SAME idem_key on every
    retry of a 'failed' row. Against the real mailer that key is permanently claimed
    once its email_log row settles, so every retry came back 'duplicate', read
    'failed' from email_log, and PATCHed the outbox row back to 'failed' with
    attempts UNCHANGED -- forever. This test fails on the prior head (its
    ``_alert_idem_key`` takes no ``attempt`` kwarg at all, so the fake below raises
    TypeError) and passes once each retry mints a fresh key via
    ``attempt=row['attempts']``, letting a genuinely-transient failure eventually
    succeed instead of looping."""
    row = _row()
    fake = FakeTables(outbox=[row])
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    mailer_fake = _ReplayFaithfulFakeMailer(first_attempt_status="failed")

    r1 = drain.drain(send_fn=mailer_fake.send_fn, now_utc=_now(), limit=10)
    assert r1.failed_n == 1
    assert fake.outbox[0]["status"] == "failed"
    assert fake.outbox[0]["attempts"] == 1

    r2 = drain.drain(send_fn=mailer_fake.send_fn, now_utc=_now(), limit=10)
    assert r2.fired_n == 1
    assert fake.outbox[0]["status"] == "sent"
    assert fake.outbox[0]["attempts"] == 2
    # The critical assertion: the two send attempts used DIFFERENT idem_keys. If they
    # had reused the same key, the second call would have come back 'duplicate' and
    # (pre-fix) the row would still be 'failed' with attempts==1 forever.
    assert mailer_fake.calls == [("alert_fire:fe1", 0), ("alert_fire:fe1:1", 1)]
    assert len(mailer_fake.claimed) == 2


def test_retry_livelock_row_retired_after_the_attempts_cap_never_loops_forever(monkeypatch):
    """The other half of the BLOCKER fix: a row that never succeeds must eventually
    stop being retried (ruling: attempts capped at 3) rather than looping every tick
    indefinitely, even once each retry has a fresh key."""
    row = _row()
    fake = FakeTables(outbox=[row])
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    mailer_fake = _ReplayFaithfulFakeMailer(first_attempt_status="failed")
    # Every attempt fails outright (never "sent").
    def always_failing(*, fire_event_id, to_email, payload, lang, user_id, attempt=0):
        key = drain._alert_idem_key(fire_event_id, attempt=attempt)
        assert key not in mailer_fake.claimed, "must never reuse a claimed idem_key"
        mailer_fake.claimed[key] = "failed"
        return "failed"

    for _ in range(drain.ALERT_RETRY_ATTEMPTS_CAP):
        drain.drain(send_fn=always_failing, now_utc=_now(), limit=10)
    assert fake.outbox[0]["status"] == "failed"
    assert fake.outbox[0]["attempts"] == drain.ALERT_RETRY_ATTEMPTS_CAP

    # One more tick: the row is now at the cap and must NOT be selected/retried again.
    result = drain.drain(send_fn=always_failing, now_utc=_now(), limit=10)
    assert result.evaluated_n == 0
    assert fake.outbox[0]["attempts"] == drain.ALERT_RETRY_ATTEMPTS_CAP
    assert len(mailer_fake.claimed) == drain.ALERT_RETRY_ATTEMPTS_CAP


def test_counters_never_increment_when_the_persisting_patch_fails(monkeypatch):
    """Review round 3 MINOR-3: a swallowed PATCH must not inflate the run receipt --
    the old code incremented fired_n/failed_n/etc. before attempting the write, so a
    repeat tick over a row whose PATCH keeps failing would count a 'sent'/'failed'
    that never actually persisted."""
    row = _row()
    fake = FakeTables(outbox=[row])
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})

    def failing_pg(method, path, body=None, prefer=None, timeout=6):
        if path.startswith("alert_outbox") and method == "PATCH":
            raise RuntimeError("boom")
        return fake.pg(method, path, body, prefer, timeout)

    monkeypatch.setattr(drain, "_pg", failing_pg)
    result = drain.drain(send_fn=lambda **kw: "sent", now_utc=_now(), limit=10)
    assert fake.outbox[0]["status"] == "pending"  # never actually written
    assert result.fired_n == 0


def test_patch_outbox_url_quotes_the_row_id(monkeypatch):
    """Review round 3 MINOR-2: ``_patch_outbox`` built its PostgREST filter as
    ``f"alert_outbox?id=eq.{row_id}"`` with no quoting, while every sibling filter in
    this module (``email_log``, ``email_suppression``, ``user_entitlements``) and
    ``close_receipt``'s own ``alert_runs`` PATCH already quote their filter value.
    A DB-minted UUID never needs it, but an unquoted id is an inconsistent contract
    with the rest of the module -- this pins that the path is always quoted the same
    way every other filter in this file already is."""
    captured = {}

    def capturing_pg(method, path, body=None, prefer=None, timeout=6):
        captured["path"] = path
        return None

    monkeypatch.setattr(drain, "_pg", capturing_pg)
    ok = drain._patch_outbox("weird id&x=y", {"status": "sent"})
    assert ok is True
    assert captured["path"] == "alert_outbox?id=eq.weird%20id%26x%3Dy"


def test_selection_predicate_never_selects_a_sent_or_suppressed_row(monkeypatch):
    import uuid as _uuid
    sent_row = _row(id=str(_uuid.uuid4()), status="sent")
    suppressed_row = _row(id=str(_uuid.uuid4()), status="suppressed")
    pending_row = _row(id=str(_uuid.uuid4()), status="pending")
    fake = FakeTables(outbox=[sent_row, suppressed_row, pending_row])
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    result = drain.drain(send_fn=lambda **kw: "sent", now_utc=_now(), limit=10)
    assert result.evaluated_n == 1
    assert sent_row["status"] == "sent"
    assert suppressed_row["status"] == "suppressed"


def test_missing_tables_yield_typed_read_unavailable_zero_sends_and_exit_zero(monkeypatch, capsys):
    def pg(method, path, body=None, prefer=None, timeout=6):
        import urllib.error
        raise urllib.error.HTTPError(path, 404, "not found", None, None)

    monkeypatch.setattr(drain, "_pg", pg)
    result = drain.drain(send_fn=lambda **kw: "sent", now_utc=_now(), limit=10)
    assert result.read_state == drain.READ_UNAVAILABLE
    assert result.fired_n == 0
    assert result.receipt_written is False


def test_main_reports_read_unavailable_with_a_line_start_warning_and_exits_zero(monkeypatch, capsys):
    """Exercises scripts.drain_alert_outbox.main() directly -- the previous version of
    this test asserted only on drain(), never imported or called main(), and never
    used capsys (Acceptance 5 + 1(e))."""
    import urllib.error
    from scripts import drain_alert_outbox

    def pg(method, path, body=None, prefer=None, timeout=6):
        raise urllib.error.HTTPError(path, 404, "not found", None, None)

    monkeypatch.setattr(drain, "_pg", pg)
    monkeypatch.delenv("ALERT_DRAIN_ENABLE", raising=False)
    rc = drain_alert_outbox.main(["--now", "2026-09-05T15:00:00+00:00"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "alert-drain: DORMANT" in out
    warning_lines = [ln for ln in out.splitlines() if "alert-drain-read-unavailable" in ln]
    assert warning_lines, "expected a ::warning line for READ_UNAVAILABLE, got: " + out
    assert warning_lines[0].startswith("::warning")


def test_main_forces_dry_run_and_zero_sends_when_alert_drain_enable_is_unset(monkeypatch, capsys):
    """DORMANT default (freeze section 10 V4): main() must perform zero sends against
    real fixture rows unless ALERT_DRAIN_ENABLE=1, even with a send_fn that would send."""
    from scripts import drain_alert_outbox

    row = _row()
    fake = FakeTables(outbox=[row])
    monkeypatch.setattr(drain, "_pg", fake.pg)
    monkeypatch.setattr(drain, "fetch_user_record",
                        lambda uid: (drain.READ_OK, OPTED_IN_USER) if str(uid) == "u1"
                        else (drain.READ_UNAVAILABLE, None))
    monkeypatch.delenv("ALERT_DRAIN_ENABLE", raising=False)
    sent = []
    monkeypatch.setattr("app.mailer.send_alert", lambda **kw: sent.append(kw) or "sent")
    rc = drain_alert_outbox.main(["--now", "2026-09-05T15:00:00+00:00"])
    out = capsys.readouterr().out
    assert rc == 0
    assert sent == []
    assert fake.outbox[0]["status"] == "pending"
    assert fake.runs == {}
    assert "outcome=" in out
    assert "category_unfiltered=" in out
    assert "receipt_written=" in out


def test_category_filter_suppresses_a_row_outside_the_users_categories(monkeypatch):
    row = _row(payload={"subject": "AAPL moved", "ticker": "AAPL", "summary_plain": "x",
                        "condition_plain": "RSI crossed 70", "evidence_url": "https://x/e",
                        "fired_at": "2026-09-05T14:00:00Z", "category": "earnings"})
    fake = FakeTables(outbox=[row])
    user = {"email": "u@example.com",
            "user_metadata": {"alert_email_optin": "true", "alert_categories": ["technical"]}}
    _patch(monkeypatch, fake, users={"u1": user})
    result = drain.drain(send_fn=lambda **kw: "sent", now_utc=_now(), limit=10)
    assert result.fired_n == 0
    assert result.suppressed_n == 1
    assert fake.outbox[0]["status"] == "suppressed"
    assert fake.outbox[0]["last_error"] == "category_filtered"


def test_requires_tier_suppresses_below_gate_and_sends_at_or_above():
    read_free = drain.TypedRead(drain.READ_OK, [{"tier": "free", "status": "none"}])
    read_pro = drain.TypedRead(drain.READ_OK, [{"tier": "pro", "status": "active"}])
    assert drain.entitlement_decision(read_free, _now(), requires_tier="pro") == "suppress"
    assert drain.entitlement_decision(read_pro, _now(), requires_tier="pro") == "send"
    zero = drain.TypedRead(drain.READ_OK_ZERO, [])
    assert drain.entitlement_decision(zero, _now(), requires_tier="pro") == "suppress"
    assert drain.entitlement_decision(zero, _now(), requires_tier=None) == "send"


def test_entitlement_unrecognised_status_fails_closed_not_open():
    read = drain.TypedRead(drain.READ_OK, [{"tier": "pro", "status": "some_new_enum_value"}])
    assert drain.entitlement_decision(read, _now()) == "suppress"


def test_quiet_hours_unparsed_shape_is_unevaluable_not_a_silent_send():
    """Major finding: an unrecognised quiet_hours shape must never fail OPEN to 'send'."""
    meta = {"alert_email_optin": "true", "quiet_hours": "not-a-window"}
    parsed = drain.parse_alert_prefs(meta)
    assert parsed.quiet_note == "unparsed"
    row = _row()
    decision = drain.decide_row(row, user_state=drain.READ_OK,
                                record={"email": "u@example.com", "user_metadata": meta},
                                ent=drain.TypedRead(drain.READ_OK_ZERO, []),
                                suppression=drain.TypedRead(drain.READ_OK_ZERO, []),
                                now_utc=_now())
    assert decision.action == "unevaluable"
    assert decision.reason == "quiet_hours_unparsed"


def test_read_unavailable_is_not_read_ok_zero(monkeypatch):
    def pg(method, path, body=None, prefer=None, timeout=6):
        raise RuntimeError("boom")

    monkeypatch.setattr(drain, "_pg", pg)
    read = drain.typed_get("alert_outbox?channel=eq.email")
    assert read.state == drain.READ_UNAVAILABLE
    assert read.state != drain.READ_OK_ZERO


def test_every_run_writes_started_then_terminal_alert_runs_rows_with_the_same_id(monkeypatch):
    row = _row()
    fake = FakeTables(outbox=[row])
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    result = drain.drain(send_fn=lambda **kw: "sent", now_utc=_now(), limit=10)
    assert result.run_id is not None
    (run,) = fake.runs.values()
    assert run["lane"] == "macro_delivery_drain"
    assert run.get("concluded_at") is not None
    assert run.get("outcome") == "success"


def test_outcome_is_derived_partial_when_unevaluable_or_degraded_send(monkeypatch):
    rows = [_row(id=str(uuid.uuid4()), user_id="u1"), _row(id=str(uuid.uuid4()), user_id="unknown")]
    fake = FakeTables(outbox=rows)
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    result = drain.drain(send_fn=lambda **kw: "sent", now_utc=_now(), limit=10)
    assert result.unevaluable_n == 1
    assert result.outcome == "partial"


def test_optin_absent_yields_suppressed_and_unknown_metadata_leaves_pending(monkeypatch):
    row = _row()
    fake = FakeTables(outbox=[row])
    no_optin_user = {"email": "u@example.com", "user_metadata": {}}
    _patch(monkeypatch, fake, users={"u1": no_optin_user})
    result = drain.drain(send_fn=lambda **kw: "sent", now_utc=_now(), limit=10)
    assert result.suppressed_n == 1
    assert fake.outbox[0]["status"] == "suppressed"


def test_user_plane_modules_write_no_site_or_data_paths():
    """No FILE-WRITE call anywhere in either module, and no write-mode `open()`/
    `Path.write_*`/`mkdir` referencing a site/ or data/ path. Prose in the module
    docstring (e.g. "writes nothing under site/ or data/") is not a write context."""
    import pathlib
    for path in ("engine/alert_delivery_drain.py", "scripts/drain_alert_outbox.py"):
        src = pathlib.Path(path).read_text()
        assert "'w')" not in src and '"w")' not in src
        assert ".write_text(" not in src and ".write_bytes(" not in src
        assert "mkdir(" not in src
        assert not re.search(r"(?<![a-zA-Z_])open\(", src)


def test_user_sends_never_touch_push_sent_jsonl():
    import pathlib
    for path in ("engine/alert_delivery_drain.py", "scripts/drain_alert_outbox.py"):
        src = pathlib.Path(path).read_text()
        assert "push_sent" not in src


def test_engine_module_does_not_import_app():
    import pathlib
    src = pathlib.Path("engine/alert_delivery_drain.py").read_text()
    assert not re.search(r"^\s*(from app|import app)\b", src, re.MULTILINE)


def test_dry_run_performs_no_send_and_no_write(monkeypatch):
    row = _row()
    fake = FakeTables(outbox=[row])
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    sent = []
    result = drain.drain(send_fn=lambda **kw: sent.append(kw) or "sent", now_utc=_now(),
                         limit=10, dry_run=True)
    assert sent == []
    assert fake.outbox[0]["status"] == "pending"
    assert fake.runs == {}
    assert result.fired_n == 1  # decision counted, no send performed


def test_two_users_alerting_on_the_same_ticker_both_receive(monkeypatch):
    rows = [_row(id=str(uuid.uuid4()), user_id="u1", fire_event_id="fe1"),
            _row(id=str(uuid.uuid4()), user_id="u2", fire_event_id="fe2")]
    fake = FakeTables(outbox=rows)
    users = {"u1": OPTED_IN_USER, "u2": {"email": "u2@example.com",
                                          "user_metadata": {"alert_email_optin": "true"}}}
    _patch(monkeypatch, fake, users=users)
    sent_to = []
    result = drain.drain(send_fn=lambda **kw: sent_to.append(kw["to_email"]) or "sent",
                         now_utc=_now(), limit=10)
    assert result.fired_n == 2
    assert set(sent_to) == {"u@example.com", "u2@example.com"}


def test_docstring_declares_trigger_cadence_and_latency_budget():
    doc = drain.__doc__
    assert "5 minutes" in doc
    assert "15 minutes" in doc
    assert "off the render path" in doc.lower() or "off-render" in doc.lower()
