"""GATE-4 commercial-path alerting — synthetic injection + transport proof.

Not done unless each of the five launch-gate conditions:
  1. Stripe webhook silence / excessive webhook errors
  2. checkout creation failures
  3. require_user 502 spike
  4. LLM daily spend above threshold
  5. brain_gateway quota fail-open
produces a DETECT + a constructed human message, and the Discord-shaped
transport is proven against a real local HTTP receiver (no mocks on the POST
path). A missing Telegram/Discord/email credential is reported as SKIP, never
PASS.

The evaluator is pure: every trip is a fixture, every healthy case is the
same fixture with the triggering rows removed.
"""
from __future__ import annotations

import http.server
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lib import commercial_path as cp
from scripts import commercial_path_sentinel as cps
from scripts import freshness_sentinel as fs

NOW = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
TH = cp.Thresholds()


def _eval(rows, now=NOW, thresholds=TH):
    return {a.kind: a for a in cp.evaluate(rows, now=now, thresholds=thresholds)}


def test_quiet_new_box_does_not_page():
    """No events → no money path → no page. Silence is not 'no customers yet'."""
    assert cp.evaluate([], now=NOW, thresholds=TH) == []


def test_healthy_armed_path_is_silent():
    rows = [
        {"kind": "checkout.ok", "ts": (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"kind": "webhook.ok", "ts": (NOW - timedelta(hours=1, minutes=50)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"kind": "llm.spend", "ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "usd": 1.25},
    ]
    assert _eval(rows) == {}


def test_webhook_silence_after_checkout_without_followup():
    rows = [{
        "kind": "checkout.ok",
        "ts": (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session_id": "cs_1",
    }]
    hit = _eval(rows)["webhook_silence"]
    assert "no webhook.ok after it" in hit.body
    assert "COMMERCIAL PATH —" in hit.message()


def test_webhook_silence_does_not_fire_when_followup_lands():
    rows = [
        {"kind": "checkout.ok", "ts": (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"kind": "webhook.ok", "ts": (NOW - timedelta(hours=1, minutes=50)).strftime("%Y-%m-%dT%H:%M:%SZ")},
    ]
    assert "webhook_silence" not in _eval(rows)


def test_webhook_n_hour_silence_only_when_armed():
    old = (NOW - timedelta(hours=TH.webhook_silence_hours + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert "webhook_silence" not in _eval([])
    assert "webhook_silence" in _eval([{"kind": "webhook.ok", "ts": old}])


def test_webhook_errors_trip_on_count_and_clear_on_healthy_ratio():
    errs = [
        {"kind": "webhook.error", "ts": (NOW - timedelta(minutes=i + 1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "reason": "invalid_signature"}
        for i in range(TH.webhook_error_min_count)
    ]
    assert "webhook_errors" in _eval(errs)
    oks = [
        {"kind": "webhook.ok", "ts": (NOW - timedelta(minutes=i + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        for i in range(20)
    ]
    # 1 error among 21 attempts is below both floors.
    mixed = oks + [errs[0]]
    assert "webhook_errors" not in _eval(mixed)


def test_checkout_fail_and_auth_and_spend_and_fail_open():
    fails = [
        {"kind": "checkout.fail", "ts": (NOW - timedelta(minutes=i + 1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "reason": "StripeError"}
        for i in range(TH.checkout_fail_min_count)
    ]
    assert "checkout_fail" in _eval(fails)
    assert "checkout_fail" not in _eval(fails[:1])

    spikes = [
        {"kind": "auth.502", "ts": (NOW - timedelta(minutes=i + 1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "reason": "URLError"}
        for i in range(TH.auth_502_min_count)
    ]
    assert "auth_502" in _eval(spikes)
    assert "auth_502" not in _eval(spikes[:3])

    spend = [{"kind": "llm.spend", "ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "usd": TH.llm_daily_usd}]
    assert "llm_spend" in _eval(spend)
    assert "llm_spend" not in _eval([{"kind": "llm.spend", "ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     "usd": 1.0}])

    assert "quota_fail_open" in _eval([
        {"kind": "quota.fail_open", "ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
         "reason": "dir_unavailable"}
    ])


def test_inject_every_kind_trips_exactly_that_kind(tmp_path):
    for kind in cp.ALERT_KINDS:
        root = tmp_path / kind
        cp.inject(kind, now=NOW, root=root, thresholds=TH)
        events = cp.load_events(now=NOW, root=root)
        active = _eval(events)
        assert kind in active, f"{kind} inject did not trip evaluate"
        assert active[kind].message().startswith("COMMERCIAL PATH —")


def test_emit_never_raises_on_unwritable_dir(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    assert cp.emit("checkout.fail", root=blocked, reason="x") is False


def test_realert_window_and_recovery():
    alert = cp.Alert(kind="checkout_fail", title="t", body="b")
    first, rec, state = cp.decide_alerts([alert], {}, now=NOW, thresholds=TH)
    assert [a.kind for a in first] == ["checkout_fail"] and rec == []
    again, rec2, state2 = cp.decide_alerts([alert], state, now=NOW + timedelta(hours=1),
                                           thresholds=TH)
    assert again == [] and rec2 == []
    later, rec3, _ = cp.decide_alerts([alert], state2,
                                      now=NOW + timedelta(hours=TH.realert_hours),
                                      thresholds=TH)
    assert [a.kind for a in later] == ["checkout_fail"]
    recovered, notes, _ = cp.decide_alerts([], state2, now=NOW + timedelta(hours=1),
                                           thresholds=TH)
    assert recovered == []
    assert any("checkout_fail" in n for n in notes)


# --------------------------------------------------------------------------- #
# Transport construction — real local webhook, no mocks on the POST path
# --------------------------------------------------------------------------- #
class _Hook(http.server.BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        _Hook.received.append(json.loads(self.rfile.read(n)))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.mark.parametrize("kind", list(cp.ALERT_KINDS))
def test_each_injected_alert_delivers_to_a_real_local_webhook(kind, tmp_path, monkeypatch):
    _Hook.received = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "MAIL_SENTINEL_TO",
                    "MAIL_SUPPORT_TO", "DISCORD_WEBHOOK_WATCHLIST"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", f"http://127.0.0.1:{srv.server_port}/hook")

        cp.inject(kind, now=NOW, root=tmp_path, thresholds=TH)
        rc = cps.run(now=NOW, root=tmp_path, dry_run=False)
        assert rc == 1
        assert len(_Hook.received) == 1
        content = _Hook.received[0]["content"]
        assert content.startswith("COMMERCIAL PATH —")
        assert kind.replace("_", " ") in content.lower() or {
            "webhook_silence": "webhook silence",
            "webhook_errors": "webhook error",
            "checkout_fail": "checkout",
            "auth_502": "502",
            "llm_spend": "spend",
            "quota_fail_open": "fail-open",
        }[kind] in content.lower()
    finally:
        srv.shutdown()
        srv.server_close()


def test_prove_all_reports_skip_not_pass_without_credentials(tmp_path, monkeypatch, capsys):
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL",
                "DISCORD_WEBHOOK_WATCHLIST", "MAIL_SENTINEL_TO", "MAIL_SUPPORT_TO"):
        monkeypatch.delenv(var, raising=False)
    rc = cps.prove_all(now=NOW, root=tmp_path, send=True)
    out = capsys.readouterr().out
    assert rc == 0
    for kind in cp.ALERT_KINDS:
        assert f"{kind:<18} DETECT=PASS" in out
        assert "MESSAGE=PASS" in out
    assert "DELIVER=SKIP (no human-channel credentials)" in out
    assert "DELIVER=PASS" not in out
    assert "REMAINING: live delivery" in out


def test_prove_all_delivers_when_a_channel_is_up(tmp_path, monkeypatch, capsys):
    _Hook.received = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "MAIL_SENTINEL_TO",
                    "MAIL_SUPPORT_TO", "DISCORD_WEBHOOK_WATCHLIST"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", f"http://127.0.0.1:{srv.server_port}/hook")
        rc = cps.prove_all(now=NOW, root=tmp_path, send=True)
        out = capsys.readouterr().out
        assert rc == 0
        assert out.count("DELIVER=PASS (discord)") == len(cp.ALERT_KINDS)
        assert len(_Hook.received) == len(cp.ALERT_KINDS)
    finally:
        srv.shutdown()
        srv.server_close()


def test_emit_sites_are_wired_in_the_money_path():
    """Source pin — the launch gate named these files as the emit points."""
    billing = (ROOT / "app" / "billing.py").read_text()
    assert 'checkout.fail' in billing and 'checkout.ok' in billing
    assert 'webhook.error' in billing and 'webhook.ok' in billing
    assert "invalid_signature" in billing and "handler_failed" in billing

    main = (ROOT / "app" / "main.py").read_text()
    assert 'auth.502' in main
    assert "auth check failed, please try again" in main

    gw = (ROOT / "engine" / "neuralweb" / "brain_gateway.py").read_text()
    assert 'quota.fail_open' in gw
    assert "dir_unavailable" in gw and "write_failed" in gw
    assert "guest_dir_unavailable" in gw
    assert 'llm.spend' in gw
    assert "::error::brain_gateway:" in gw


def test_sentinel_reuses_freshness_transport_and_the_same_unit():
    service = (ROOT / "app" / "deploy" / "macro-sentinel.service").read_text()
    assert "scripts.commercial_path_sentinel" in service
    assert "scripts.freshness_sentinel" in service
    assert "EnvironmentFile=-/etc/macro-sentinel.env" in service
    # Reuse, do not fork: the commercial runner imports the freshness transports.
    src = (ROOT / "scripts" / "commercial_path_sentinel.py").read_text()
    assert "from scripts.freshness_sentinel import" in src
    assert "send_telegram" in src and "send_discord" in src and "send_email" in src
    assert "sentry" not in src.lower()
    assert "datadog" not in src.lower()
    assert "pagerduty" not in src.lower()


def test_send_email_accepts_commercial_subject(monkeypatch):
    """The shared mail helper keeps the freshness default and accepts GATE-4 names."""
    monkeypatch.setenv("MAIL_SENTINEL_TO", "ops@example.test")
    captured = {}

    def fake_send(**kwargs):
        captured.update(kwargs)
        return "sent"

    import app.mailer as mailer
    monkeypatch.setattr(mailer, "send", fake_send)
    ok = fs.send_email(
        "COMMERCIAL PATH — test", NOW,
        subject="Mastermind commercial-path alert",
        template="commercial_path_sentinel",
    )
    assert ok is True
    assert captured["subject"] == "Mastermind commercial-path alert"
    assert captured["template"] == "commercial_path_sentinel"
    assert captured["idem_key"].startswith("commercial_path_sentinel:")
