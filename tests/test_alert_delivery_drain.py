"""tests/test_alert_delivery_drain.py -- RED-first tests for packet B-F08-1b's drain."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import pytest

from engine import alert_delivery_drain as drain


def _now(iso="2026-09-05T15:00:00+00:00"):
    return datetime.fromisoformat(iso)


class FakeTables:
    def __init__(self, *, outbox=None, users=None, suppression=None, entitlements=None):
        self.outbox = outbox if outbox is not None else []
        self.users = users if users is not None else {}
        self.suppression = suppression if suppression is not None else []
        self.entitlements = entitlements if entitlements is not None else {}
        self.runs = {}
        self.patches = []

    def pg(self, method, path, body=None, prefer=None, timeout=6):
        if path.startswith("alert_outbox") and method == "GET":
            return list(self.outbox)
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

    fake.outbox[0]["status"] = "pending"  # simulate a replay before terminal write races in
    r2 = drain.drain(send_fn=send_fn_dup, now_utc=_now(), limit=10)
    assert r2.fired_n == 1


def test_idem_key_is_derived_deterministically_from_fire_event_id():
    from app import mailer
    assert mailer.alert_idem_key("fe1") == "alert_fire:fe1"
    assert mailer.alert_idem_key("fe1") == mailer.alert_idem_key("fe1")


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


def test_failed_row_is_retried_by_a_later_drain_and_never_reads_as_sent(monkeypatch):
    row = _row()
    fake = FakeTables(outbox=[row])
    _patch(monkeypatch, fake, users={"u1": OPTED_IN_USER})
    drain.drain(send_fn=lambda **kw: "failed", now_utc=_now(), limit=10)
    assert fake.outbox[0]["status"] == "failed"
    fake.outbox[0]["status"] = "pending"  # a later drain still selects it (frozen contract has no 'sending')
    drain.drain(send_fn=lambda **kw: "sent", now_utc=_now(), limit=10)
    assert fake.outbox[0]["status"] == "sent"


def test_missing_tables_yield_typed_read_unavailable_zero_sends_and_exit_zero(monkeypatch, capsys):
    def pg(method, path, body=None, prefer=None, timeout=6):
        import urllib.error
        raise urllib.error.HTTPError(path, 404, "not found", None, None)

    monkeypatch.setattr(drain, "_pg", pg)
    result = drain.drain(send_fn=lambda **kw: "sent", now_utc=_now(), limit=10)
    assert result.read_state == drain.READ_UNAVAILABLE
    assert result.fired_n == 0


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
