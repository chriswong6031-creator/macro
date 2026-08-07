"""Freshness sentinel (masterplan W1) — the dead-man switch outside GitHub.

The load-bearing tests are the two failure modes of the 2026 outages:
  * §0.1 acceptance gate — a simulated dead nightly (every bake stamp >26h old)
    must produce a breach report, a composed operator alert, and a DELIVERED
    transport, proven against a real local webhook receiver (no mocks on the
    HTTP path).
  * the Jul-31→Aug-6 replay — the page re-baked every day of that outage while
    the board froze, and the page carries per-panel "as of" dates (options
    ceilings, rotation tooltips) that stay fresh throughout. The board check
    must anchor on the delayed-board marker the template renders only when the
    engine itself reports the lag, and must NOT be fooled by fresh peripheral
    as-of strings.
"""
from __future__ import annotations

import http.server
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts import freshness_sentinel as fs

NOW = datetime(2026, 8, 8, 5, 0, 0, tzinfo=timezone.utc)

#: Body shaped like the REAL outage page: fresh per-panel annotations, an old
#: board marker in both template renderings (dashboard.html.j2:15199-15200).
OUTAGE_BODY = (
    "<html>Options ceiling 2.2% above (as of 2026-08-07) "
    "rotation as of 2026-08-07 "
    "59 shown · 111 setups · dots reflect prices as of 2026-07-31 — verify before acting. "
    "Board is delayed — prices are as of 2026-07-31. Dots and entry signals…</html>"
)

#: Healthy body: per-panel as-of dates present (some old — weekly panels lag
#: legitimately), delayed-board marker ABSENT.
HEALTHY_BODY = (
    "<html>Options ceiling (as of 2026-08-07) seasonal panel as of 2026-07-01 "
    "green dot = entry open, yellow = wait for pullback.</html>"
)


def _page(bake_age_hours: float, body: str = HEALTHY_BODY) -> fs.FetchResult:
    return fs.FetchResult(
        status=200,
        last_modified=NOW - timedelta(hours=bake_age_hours),
        body=body,
    )


def _r2(bake_age_hours: float) -> fs.FetchResult:
    return fs.FetchResult(status=200, last_modified=NOW - timedelta(hours=bake_age_hours))


def _fresh_results() -> dict[str, fs.FetchResult]:
    return {
        "us_stocks": _page(14.0),
        "china": _page(7.0),
        "hub": _page(14.0),
        "r2_massive_stock_day": _r2(10.0),
    }


# --------------------------------------------------------------------------- #
# Evaluation core
# --------------------------------------------------------------------------- #
def test_fresh_estate_is_ok():
    report = fs.evaluate(_fresh_results(), NOW)
    assert report["ok"] is True
    assert report["stale_surfaces"] == []
    assert report["indeterminate_surfaces"] == []
    assert all(c["status"] == "ok" for c in report["surfaces"].values())


def test_dead_nightly_for_a_day_breaches_every_bake_surface():
    """§0.1 core condition: one missed nightly (stamps ~30h old) trips all four."""
    results = {
        "us_stocks": _page(30.0),
        "china": _page(30.0),
        "hub": _page(30.0),
        "r2_massive_stock_day": _r2(30.0),
    }
    report = fs.evaluate(results, NOW)
    assert report["ok"] is False
    assert report["stale_surfaces"] == ["china", "hub", "r2_massive_stock_day", "us_stocks"]
    for c in report["surfaces"].values():
        assert "bake stamp 30.0h old" in c["detail"]


def test_jul31_outage_replay_breaches_on_the_board_marker():
    """The outage the sentinel was built for: page re-bakes daily (bake fresh),
    peripheral as-of dates fresh, board marker frozen at 2026-07-31 (8d at NOW).
    A page-wide max-as-of scrape reads 2026-08-07 and calls this OK — the board
    anchor must breach it."""
    results = _fresh_results()
    results["us_stocks"] = _page(2.0, OUTAGE_BODY)
    report = fs.evaluate(results, NOW)
    assert report["stale_surfaces"] == ["us_stocks"]
    c = report["surfaces"]["us_stocks"]
    assert c["board_delayed"] is True
    assert c["board_price_through"] == "2026-07-31"
    assert "board reports itself delayed" in c["detail"]
    assert "page re-bakes are landing, board data is not" in c["detail"]


def test_short_board_delay_inside_budget_does_not_page():
    """A one-session lag (marker present, 2d old) stays inside the 4d budget —
    the B5 falsifier law: budgets absorb routine hiccups."""
    body = OUTAGE_BODY.replace("2026-07-31", "2026-08-06")
    results = _fresh_results()
    results["us_stocks"] = _page(2.0, body)
    report = fs.evaluate(results, NOW)
    assert report["ok"] is True
    assert report["surfaces"]["us_stocks"]["board_delayed"] is True


def test_fresh_peripheral_asof_dates_never_mask_or_fake_a_breach():
    # Healthy page carries an OLD weekly-panel as-of (2026-07-01) and no board
    # marker: must be ok — min() over generic as-of strings would false-alarm.
    report = fs.evaluate(_fresh_results(), NOW)
    assert report["surfaces"]["us_stocks"]["board_delayed"] is False
    assert report["ok"] is True


def test_board_delay_stamp_parses_both_template_renderings():
    assert fs.board_delay_stamp(OUTAGE_BODY) == "2026-07-31"
    assert fs.board_delay_stamp("dots reflect prices as of 2026-08-01 x") == "2026-08-01"
    assert fs.board_delay_stamp("Board is delayed — prices are as of 2026-08-02") == "2026-08-02"
    assert fs.board_delay_stamp(HEALTHY_BODY) is None
    assert fs.board_delay_stamp("plain as of 2026-08-05 annotation") is None


def test_network_error_is_indeterminate_not_stale():
    results = _fresh_results()
    results["us_stocks"] = fs.FetchResult(error="timed out")
    results["china"] = fs.FetchResult(status=503, error="HTTP 503 Service Unavailable")
    report = fs.evaluate(results, NOW)
    assert report["stale_surfaces"] == []
    assert report["indeterminate_surfaces"] == ["china", "us_stocks"]


def test_missing_last_modified_on_200_is_indeterminate():
    results = _fresh_results()
    results["hub"] = fs.FetchResult(status=200, last_modified=None, body=None)
    report = fs.evaluate(results, NOW)
    assert "hub" in report["indeterminate_surfaces"]


# --------------------------------------------------------------------------- #
# Alert decisions (counters, windows, stickiness, recovery)
# --------------------------------------------------------------------------- #
def _stale_report(now: datetime = NOW) -> dict:
    return fs.evaluate(
        {
            "us_stocks": fs.FetchResult(
                status=200, last_modified=now - timedelta(hours=30), body=HEALTHY_BODY
            ),
            "china": fs.FetchResult(
                status=200, last_modified=now - timedelta(hours=30), body=HEALTHY_BODY
            ),
            "hub": fs.FetchResult(
                status=200, last_modified=now - timedelta(hours=30), body=HEALTHY_BODY
            ),
            "r2_massive_stock_day": fs.FetchResult(
                status=200, last_modified=now - timedelta(hours=30)
            ),
        },
        now,
    )


def test_breach_alerts_immediately_and_holds_the_realert_window():
    report = _stale_report()
    alerts, state = fs.decide_alerts(report, {}, NOW)
    assert len(alerts) == 1
    assert "STALE LIVE ESTATE" in alerts[0]
    for sid in report["stale_surfaces"]:
        assert sid in alerts[0]

    # 30 minutes later, same breach: window closed, no repeat.
    later = NOW + timedelta(minutes=30)
    alerts2, state2 = fs.decide_alerts(_stale_report(later), state, later)
    assert alerts2 == []

    # Past the window: repeats.
    much_later = NOW + timedelta(hours=fs.REALERT_HOURS + 1)
    alerts3, _ = fs.decide_alerts(_stale_report(much_later), state2, much_later)
    assert len(alerts3) == 1 and "STALE LIVE ESTATE" in alerts3[0]


def test_new_surface_joining_the_breach_realerts_inside_the_window():
    partial = fs.evaluate(
        {
            **_fresh_results(),
            "us_stocks": fs.FetchResult(
                status=200, last_modified=NOW - timedelta(hours=30), body=HEALTHY_BODY
            ),
        },
        NOW,
    )
    _, state = fs.decide_alerts(partial, {}, NOW)
    soon = NOW + timedelta(minutes=30)
    alerts, _ = fs.decide_alerts(_stale_report(soon), state, soon)
    assert len(alerts) == 1  # breach set GREW → immediate re-alert


def test_flapping_surface_does_not_storm_inside_the_window():
    """A breached surface flipping stale↔indeterminate must ride the 6h window
    (sticky membership), not re-alert on every 30-minute pass."""
    _, state = fs.decide_alerts(_stale_report(), {}, NOW)
    total_alerts = 0
    for i in range(1, 8):  # 3.5h of passes, r2 alternating timeout/definitive
        t = NOW + timedelta(minutes=30 * i)
        report = _stale_report(t)
        if i % 2:
            report["surfaces"]["r2_massive_stock_day"]["status"] = "indeterminate"
            report["surfaces"]["r2_massive_stock_day"]["detail"] = "timed out"
            report["stale_surfaces"] = ["china", "hub", "us_stocks"]
            report["indeterminate_surfaces"] = ["r2_massive_stock_day"]
        alerts, state = fs.decide_alerts(report, state, t)
        total_alerts += len(alerts)
    assert total_alerts == 0
    # r2 stayed in the held breach set throughout the flapping.
    assert "r2_massive_stock_day" in state["breach_key"]


def test_blindness_never_reads_as_recovery():
    """Breach, then the site goes fully dark: NO 'RECOVERED' may be sent, and
    the breach state must survive the blindness."""
    _, state = fs.decide_alerts(_stale_report(), {}, NOW)
    dark = fs.evaluate(
        {s["id"]: fs.FetchResult(error="connection refused") for s in fs.SURFACES},
        NOW + timedelta(minutes=30),
    )
    alerts, state2 = fs.decide_alerts(dark, state, NOW + timedelta(minutes=30))
    assert all("RECOVERED" not in a for a in alerts)
    assert set(state2["breach_key"].split(",")) == {
        "china", "hub", "r2_massive_stock_day", "us_stocks"
    }


def test_recovery_notice_fires_once_and_only_on_definitive_ok():
    _, state = fs.decide_alerts(_stale_report(), {}, NOW)
    fresh = fs.evaluate(_fresh_results(), NOW + timedelta(hours=1))
    alerts, state2 = fs.decide_alerts(fresh, state, NOW + timedelta(hours=1))
    assert len(alerts) == 1 and "RECOVERED" in alerts[0]
    alerts2, _ = fs.decide_alerts(fresh, state2, NOW + timedelta(hours=2))
    assert alerts2 == []


def test_blindness_escalates_only_after_threshold():
    results = {**_fresh_results(), "us_stocks": fs.FetchResult(error="timed out")}
    state: dict = {}
    for i in range(fs.BLIND_AFTER):
        report = fs.evaluate(results, NOW + timedelta(minutes=30 * i))
        alerts, state = fs.decide_alerts(report, state, NOW + timedelta(minutes=30 * i))
        if i < fs.BLIND_AFTER - 1:
            assert alerts == [], f"blind alert fired early at pass {i + 1}"
    assert len(alerts) == 1 and "SENTINEL BLIND" in alerts[0]
    # A definitive read clears the counter and sends one recovery.
    ok_report = fs.evaluate(_fresh_results(), NOW + timedelta(hours=4))
    alerts2, state = fs.decide_alerts(ok_report, state, NOW + timedelta(hours=4))
    assert len(alerts2) == 1 and "RECOVERED" in alerts2[0]
    assert state["blind_counts"] == {}


# --------------------------------------------------------------------------- #
# §0.1 ACCEPTANCE GATE — dead nightly ⇒ alert DEMONSTRABLY fires (real webhook)
# --------------------------------------------------------------------------- #
class _Hook(http.server.BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self):  # noqa: N802 — stdlib handler name
        n = int(self.headers.get("Content-Length", 0))
        _Hook.received.append(json.loads(self.rfile.read(n)))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):  # keep pytest output clean
        pass


def test_simulated_dead_nightly_delivers_a_real_alert(tmp_path, monkeypatch, capsys):
    """Kill the nightly for one simulated day → the alert fires end-to-end:
    breach report → Discord-shaped webhook POST received by a real local HTTP
    server → staleness.json published. No mocks on the transport path."""
    _Hook.received = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "MAIL_SENTINEL_TO",
                    "MAIL_SUPPORT_TO", "DISCORD_WEBHOOK_WATCHLIST"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv(
            "DISCORD_WEBHOOK_URL", f"http://127.0.0.1:{srv.server_port}/hook"
        )

        def dead_nightly_fetcher(url, *, want_body):
            lm = NOW - timedelta(hours=30)  # last bake: one dead nightly ago
            body = HEALTHY_BODY if want_body else None
            return fs.FetchResult(status=200, last_modified=lm, body=body)

        rc = fs.run(
            now=NOW,
            base="https://example.invalid",
            r2_base="https://example.invalid",
            public_dir=tmp_path / "public",
            state_dir=tmp_path / "state",
            fetcher=dead_nightly_fetcher,
        )

        assert rc == 1
        assert len(_Hook.received) == 1
        content = _Hook.received[0]["content"]
        assert "STALE LIVE ESTATE" in content
        assert "us_stocks" in content and "china" in content

        served = json.loads((tmp_path / "public" / "live" / "staleness.json").read_text())
        assert served["ok"] is False
        assert served["active_breach"] == [
            "china", "hub", "r2_massive_stock_day", "us_stocks"
        ]
        assert served["alerting"]["breach_alerted_at"] == NOW.isoformat()
        out = capsys.readouterr().out
        assert "sentinel alert (discord)" in out
    finally:
        srv.shutdown()
        srv.server_close()


def test_fresh_run_writes_ok_state_and_exits_zero(tmp_path, monkeypatch):
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL",
                "DISCORD_WEBHOOK_WATCHLIST", "MAIL_SENTINEL_TO", "MAIL_SUPPORT_TO"):
        monkeypatch.delenv(var, raising=False)

    def fresh_fetcher(url, *, want_body):
        return fs.FetchResult(
            status=200,
            last_modified=NOW - timedelta(hours=10),
            body=HEALTHY_BODY if want_body else None,
        )

    rc = fs.run(
        now=NOW,
        base="https://example.invalid",
        r2_base="https://example.invalid",
        public_dir=tmp_path / "public",
        state_dir=tmp_path / "state",
        fetcher=fresh_fetcher,
    )
    assert rc == 0
    served = json.loads((tmp_path / "public" / "live" / "staleness.json").read_text())
    assert served["ok"] is True
    assert served["active_breach"] == [] and served["blind_surfaces"] == []
    assert (tmp_path / "state" / "state.json").exists()


def test_served_state_reads_not_ok_once_blind_past_threshold(tmp_path, monkeypatch):
    """'I can't tell' must never render as 'fresh': after BLIND_AFTER dark
    passes the SERVED verdict flips, and the unit exits non-zero."""
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL",
                "DISCORD_WEBHOOK_WATCHLIST", "MAIL_SENTINEL_TO", "MAIL_SUPPORT_TO"):
        monkeypatch.delenv(var, raising=False)

    def dark_fetcher(url, *, want_body):
        return fs.FetchResult(error="connection refused")

    rc = 0
    for i in range(fs.BLIND_AFTER):
        rc = fs.run(
            now=NOW + timedelta(minutes=30 * i),
            base="https://example.invalid",
            r2_base="https://example.invalid",
            public_dir=tmp_path / "public",
            state_dir=tmp_path / "state",
            fetcher=dark_fetcher,
        )
    assert rc == 1
    served = json.loads((tmp_path / "public" / "live" / "staleness.json").read_text())
    assert served["ok"] is False
    assert served["blind_surfaces"] == ["china", "hub", "r2_massive_stock_day", "us_stocks"]
    assert served["stale_surfaces"] == []  # blind, not provably stale — honest split


def test_alert_delivery_survives_an_unwritable_state_path(tmp_path, monkeypatch):
    """Disk trouble on /var/lib is CORRELATED with the outages this watches for —
    the alarm must fire even when neither state file can be written."""
    _Hook.received = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "MAIL_SENTINEL_TO",
                    "MAIL_SUPPORT_TO", "DISCORD_WEBHOOK_WATCHLIST"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv(
            "DISCORD_WEBHOOK_URL", f"http://127.0.0.1:{srv.server_port}/hook"
        )
        # Both target dirs are FILES → every mkdir/write raises OSError.
        blocked_public = tmp_path / "public"
        blocked_state = tmp_path / "state"
        blocked_public.write_text("not a directory")
        blocked_state.write_text("not a directory")

        def dead_nightly_fetcher(url, *, want_body):
            return fs.FetchResult(
                status=200,
                last_modified=NOW - timedelta(hours=30),
                body=HEALTHY_BODY if want_body else None,
            )

        rc = fs.run(
            now=NOW,
            base="https://example.invalid",
            r2_base="https://example.invalid",
            public_dir=blocked_public,
            state_dir=blocked_state,
            fetcher=dead_nightly_fetcher,
        )
        assert rc == 1
        assert len(_Hook.received) == 1
        assert "STALE LIVE ESTATE" in _Hook.received[0]["content"]
    finally:
        srv.shutdown()
        srv.server_close()


# --------------------------------------------------------------------------- #
# Deploy wiring — the sentinel must actually reach and arm on the VPS
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parents[1]


def test_sentinel_units_ship_and_are_oneshot_with_env_files():
    service = (ROOT / "app" / "deploy" / "macro-sentinel.service").read_text()
    assert "Type=oneshot" in service
    assert "ExecStart=/opt/macro/.venv/bin/python -m scripts.freshness_sentinel" in service
    assert "EnvironmentFile=-/etc/macro-api.env" in service
    assert "EnvironmentFile=-/etc/macro-sentinel.env" in service
    timer = (ROOT / "app" / "deploy" / "macro-sentinel.timer").read_text()
    assert "OnCalendar=*-*-* *:12/30:00 UTC" in timer
    # Dead-man switch: a reboot-missed pass must fire on boot.
    assert "Persistent=true" in timer
    assert "Unit=macro-sentinel.service" in timer


def test_update_sh_self_arms_the_sentinel_lane():
    script = (ROOT / "app" / "deploy" / "update.sh").read_text()
    block = script[script.index("macro-sentinel.timer"):]
    # Same contract as the prophet lane: verify-gated install, self-arming
    # (absent-file clause), timer restarted — the oneshot service never is.
    assert '[ ! -f /etc/systemd/system/macro-sentinel.timer ]' in script
    assert 'systemd-analyze verify "${SENTINEL_UNIT_SOURCES[@]}"' in script
    assert "systemctl restart macro-sentinel.timer" in block
    assert "systemctl restart macro-sentinel.service" not in script
    assert "systemctl enable --now macro-sentinel.timer" in script


def test_caddy_serves_staleness_state_publicly_with_no_store():
    caddy = (ROOT / "app" / "deploy" / "Caddyfile").read_text()
    matcher = caddy[caddy.index("@vps_public_live {"):]
    matcher = matcher[: matcher.index("}")]
    assert "/live/staleness.json" in matcher
    fallback = caddy[caddy.index("handle /live/staleness.json {"):]
    fallback = fallback[: fallback.index("file_server")]
    assert 'header Cache-Control "no-store"' in fallback


def test_naive_clock_override_is_utc_not_local(tmp_path, monkeypatch):
    """The runbook drill types a bare `--now 2026-08-08T05:00:00`. Treating that
    as LOCAL time shifts the whole comparison by the operator's UTC offset and
    reads as a budget bug rather than a clock one."""
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL",
                "DISCORD_WEBHOOK_WATCHLIST", "MAIL_SENTINEL_TO", "MAIL_SUPPORT_TO"):
        monkeypatch.delenv(var, raising=False)
    seen: list[datetime] = []

    def spy(now, **kw):
        seen.append(now)
        return 0

    monkeypatch.setattr(fs, "run", spy)
    fs.main(["--now", "2026-08-08T05:00:00",
             "--public-dir", str(tmp_path / "p"), "--state-dir", str(tmp_path / "s")])
    assert seen[0] == datetime(2026, 8, 8, 5, 0, tzinfo=timezone.utc)

    # An explicit offset is still honoured and normalised to UTC.
    seen.clear()
    fs.main(["--now", "2026-08-08T05:00:00+02:00",
             "--public-dir", str(tmp_path / "p"), "--state-dir", str(tmp_path / "s")])
    assert seen[0] == datetime(2026, 8, 8, 3, 0, tzinfo=timezone.utc)


def test_sentinel_is_stdlib_only():
    """The observer of last resort must not import the engine tree, lib.config,
    or any third-party package at module load — a broken venv or repo half-pull
    on the VPS cannot be allowed to take the watchdog down with it. Lazy
    (function-scoped) imports are exempt but must actually be lazy."""
    import ast

    src = (ROOT / "scripts" / "freshness_sentinel.py").read_text()
    tree = ast.parse(src)
    stdlib_ok = {
        "__future__", "argparse", "json", "os", "re", "sys", "tempfile", "urllib",
        "urllib.error", "urllib.request", "dataclasses", "datetime",
        "email.utils", "pathlib",
    }
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if node.col_offset > 0:
            continue  # function-scoped (lazy) — app.mailer + hashlib live here
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            assert node.module != "app", "app.mailer import must stay lazy"
            names = [node.module]
        else:
            names = [a.name for a in node.names]
        for name in names:
            assert name in stdlib_ok, f"non-stdlib module-level import: {name}"
