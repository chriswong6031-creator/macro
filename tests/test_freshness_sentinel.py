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
  * the 2026-08-08 Prophet replay — the same re-stamp trap one layer down.
    data/us_prophet_rank/candidates/2026-08.parquet froze at stamp_date
    2026-08-05 while us_stocks.html re-baked fresh every day, so BOTH checks
    above stayed green through it. The prophet_us surface anchors on the store's
    own ``asof`` measured against the NYSE session calendar, so the weekend the
    freeze was found on cannot excuse it and cannot fake it either.
"""
from __future__ import annotations

import http.server
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import freshness_sentinel as fs

NOW = datetime(2026, 8, 8, 5, 0, 0, tzinfo=timezone.utc)
#: NOW is a SATURDAY, so the last COMPLETED NYSE session is Friday 2026-08-07.
#: Every prophet expectation below is derived from that, not from the wall clock.
PROPHET_CURRENT_ASOF = "2026-08-07"

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


def _prophet(asof: str | None = PROPHET_CURRENT_ASOF, *,
             mtime_age_hours: float = 2.0,
             body: str | None = None) -> fs.FetchResult:
    """One served read of prophet/index.json, shaped like the real artifact.

    ``mtime_age_hours`` stays FRESH by default on purpose: the whole point of
    this surface is that the file keeps landing on schedule while its contents
    freeze, so every staleness verdict below has to come from ``asof`` alone.
    """
    if body is None:
        doc = {"schema": "prophet.index/v1", "cadence": "nightly-EOD",
               "authority_tier": "display", "plan_count": 120,
               "source_delayed": False, "source_unknown": False,
               "source_mixed_vintage": False,
               "source_basis": "panel_majority"}
        if asof is not None:
            doc["source_asof"] = asof
        body = json.dumps(doc)
    return fs.FetchResult(
        status=200, last_modified=NOW - timedelta(hours=mtime_age_hours), body=body
    )


def _served(result: fs.FetchResult):
    """A served_reader stand-in that answers every path with ``result``."""
    return lambda served_dir, path: result


def _fresh_results() -> dict[str, fs.FetchResult]:
    return {
        "us_stocks": _page(14.0),
        "china": _page(7.0),
        "hub": _page(14.0),
        "r2_massive_stock_day": _r2(10.0),
        "prophet_us": _prophet(),
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
        # prophet_us is judged on content, not on a stamp — it stays ok here,
        # which is the point: the four bake surfaces answer independently.
        "prophet_us": _prophet(),
    }
    report = fs.evaluate(results, NOW)
    assert report["ok"] is False
    assert report["stale_surfaces"] == ["china", "hub", "r2_massive_stock_day", "us_stocks"]
    for sid in report["stale_surfaces"]:
        assert "bake stamp 30.0h old" in report["surfaces"][sid]["detail"]


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
            # held fresh: these cases exercise the alert window, and the four
            # bake surfaces above are the breach set they assert on.
            "prophet_us": _prophet(),
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
            served_reader=_served(_prophet()),
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
        served_reader=_served(_prophet()),
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
            served_reader=_served(fs.FetchResult(error="served read failed: no such file")),
        )
    assert rc == 1
    served = json.loads((tmp_path / "public" / "live" / "staleness.json").read_text())
    assert served["ok"] is False
    assert served["blind_surfaces"] == [
        "china", "hub", "prophet_us", "r2_massive_stock_day", "us_stocks"
    ]
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
            served_reader=_served(_prophet()),
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


# --------------------------------------------------------------------------- #
# prophet_us — the store's own asof, judged against the NYSE session calendar
# --------------------------------------------------------------------------- #
def _prophet_surface() -> dict:
    return next(s for s in fs.SURFACES if s["id"] == "prophet_us")


def test_prophet_surface_is_armed_on_its_own_asof():
    s = _prophet_surface()
    assert s["kind"] == "served_file"
    assert s["path"] == "/prophet/index.json"
    assert s["asof_field"] == "source_asof"
    # Judged on CONTENT: a mtime budget here would be the re-stamp trap again,
    # since the served file's mtime comes from an rsync of a git checkout.
    assert s["bake_budget_hours"] is None
    assert s["delay_budget_days"] is None


def test_frozen_prophet_store_replay_breaches_on_its_own_asof():
    """The 2026-08-08 audit replay. candidates/2026-08.parquet stopped at
    stamp_date 2026-08-05 while every other surface read fresh: the page kept
    re-baking, the R2 manifest kept publishing, and the delayed-board marker
    never rendered because PRICES were not the thing that froze. Only the
    store's own asof can see this, and it is 2 completed sessions (08-06,
    08-07) behind at NOW."""
    results = _fresh_results()
    results["prophet_us"] = _prophet("2026-08-05")
    report = fs.evaluate(results, NOW)
    assert report["stale_surfaces"] == ["prophet_us"]
    c = report["surfaces"]["prophet_us"]
    assert c["asof"] == "2026-08-05"
    assert c["asof_sessions_behind"] == 2
    assert "store as of 2026-08-05 is 2 completed NYSE session(s) behind" in c["detail"]
    # the one-layer-down re-stamp disclosure: the file IS landing, the data is not
    assert "the file is being re-published, the store is not" in c["detail"]


def test_fresh_publication_stamp_cannot_hide_a_frozen_source_watermark():
    results = _fresh_results()
    results["prophet_us"] = _prophet(body=json.dumps({
        "schema": "prophet.index/v1",
        "asof": "2026-08-08",          # successful Saturday rerun/publication
        "recorded_at": "2026-08-08",
        "source_asof": "2026-08-05",   # frozen rank/board input
        "source_delayed": False,
        "source_unknown": False,
        "source_mixed_vintage": False,
        "source_basis": "panel_majority",
    }))
    report = fs.evaluate(results, NOW)
    assert report["stale_surfaces"] == ["prophet_us"]
    assert report["surfaces"]["prophet_us"]["asof"] == "2026-08-05"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_delayed", True),
        ("source_unknown", True),
        ("source_mixed_vintage", True),
        ("source_delayed", None),
    ],
)
def test_prophet_source_freshness_flags_fail_closed(field, value):
    doc = {
        "source_asof": PROPHET_CURRENT_ASOF,
        "source_delayed": False,
        "source_unknown": False,
        "source_mixed_vintage": False,
        "source_basis": "panel_majority",
    }
    if value is None:
        doc.pop(field)
    else:
        doc[field] = value
    results = _fresh_results()
    results["prophet_us"] = _prophet(body=json.dumps(doc))

    report = fs.evaluate(results, NOW)

    assert report["stale_surfaces"] == ["prophet_us"]
    assert field in report["surfaces"]["prophet_us"]["detail"]


@pytest.mark.parametrize("basis", [None, "board_asof", "unknown"])
def test_prophet_source_basis_must_be_panel_majority(basis):
    doc = {
        "source_asof": PROPHET_CURRENT_ASOF,
        "source_delayed": False,
        "source_unknown": False,
        "source_mixed_vintage": False,
    }
    if basis is not None:
        doc["source_basis"] = basis
    results = _fresh_results()
    results["prophet_us"] = _prophet(body=json.dumps(doc))

    report = fs.evaluate(results, NOW)

    assert report["stale_surfaces"] == ["prophet_us"]
    assert "source_basis" in report["surfaces"]["prophet_us"]["detail"]


def test_prophet_three_sessions_behind_breaches():
    """The gate the masterplan pins: an index 3 sessions behind the calendar
    must breach, so the freeze can never sit unannounced for a week again."""
    results = _fresh_results()
    results["prophet_us"] = _prophet("2026-08-04")
    report = fs.evaluate(results, NOW)
    assert report["ok"] is False
    assert report["surfaces"]["prophet_us"]["asof_sessions_behind"] == 3


def test_current_prophet_store_does_not_page():
    """The other half of the gate: a current index must NOT breach. NOW is a
    Saturday — an asof of Friday's session is exactly current, and a
    calendar-blind "days since asof" rule would already be calling it stale."""
    report = fs.evaluate(_fresh_results(), NOW)
    assert report["ok"] is True
    c = report["surfaces"]["prophet_us"]
    assert c["status"] == "ok"
    assert c["asof"] == PROPHET_CURRENT_ASOF
    assert c["asof_sessions_behind"] == 0


def test_prophet_one_missed_nightly_is_inside_budget():
    """B5 falsifier law: budgets absorb routine hiccups. One missed nightly (and
    the next-day retry that fixes it) is one session of lag and must not page;
    the SECOND missed session is the breach above."""
    results = _fresh_results()
    results["prophet_us"] = _prophet("2026-08-06")
    report = fs.evaluate(results, NOW)
    assert report["ok"] is True
    assert report["surfaces"]["prophet_us"]["asof_sessions_behind"] == 1


def test_prophet_weekend_and_holiday_never_manufacture_a_breach():
    """The whole reason the anchor is the exchange calendar. On Monday morning
    the newest session that CAN exist is still Friday's — a wall-clock budget of
    2 days would page every Monday on a perfectly healthy store."""
    monday = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    results = _fresh_results()
    results["prophet_us"] = _prophet("2026-08-07", mtime_age_hours=50.0)
    report = fs.evaluate(results, monday)
    assert report["surfaces"]["prophet_us"]["asof_sessions_behind"] == 0
    assert report["surfaces"]["prophet_us"]["status"] == "ok"


def test_prophet_is_read_from_the_served_tree_never_over_http(tmp_path, monkeypatch):
    """/prophet/index.json is BEHIND the registration wall: an anonymous GET
    answers HTTP 401 + x-regwall: deny (probed 2026-08-08), and app/regwall.py
    grants only /prophet/showcase.json — a deliberately delayed artifact. A
    sentinel that fetched this over HTTP would read indeterminate on every pass
    forever and page "sentinel is blind" every REALERT_HOURS: a false-alarm
    machine bolted to the alarm that has to stay trusted."""
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL",
                "DISCORD_WEBHOOK_WATCHLIST", "MAIL_SENTINEL_TO", "MAIL_SUPPORT_TO"):
        monkeypatch.delenv(var, raising=False)
    urls: list[str] = []
    reads: list[tuple[str, str]] = []

    def spy_fetch(url, *, want_body):
        urls.append(url)
        return fs.FetchResult(status=200, last_modified=NOW - timedelta(hours=4),
                              body=HEALTHY_BODY if want_body else None)

    def spy_served(served_dir, path):
        reads.append((str(served_dir), path))
        return _prophet()

    rc = fs.run(
        now=NOW,
        base="https://example.invalid",
        r2_base="https://example.invalid",
        public_dir=tmp_path / "public",
        state_dir=tmp_path / "state",
        served_dir=Path(fs.DEFAULT_SERVED_DIR),
        fetcher=spy_fetch,
        served_reader=spy_served,
    )
    assert rc == 0
    assert not [u for u in urls if "/prophet/" in u], (
        f"prophet must not be fetched over HTTP — the wall 401s it: {urls}"
    )
    assert reads == [("/opt/macro/site.served", "/prophet/index.json")]


def test_read_served_round_trips_and_maps_a_missing_file_to_indeterminate(tmp_path):
    (tmp_path / "prophet").mkdir()
    (tmp_path / "prophet" / "index.json").write_text(
        '{"source_asof": "2026-08-07"}'
    )
    got = fs.read_served(tmp_path, "/prophet/index.json")
    assert got.status == 200 and got.last_modified is not None
    assert json.loads(got.body)["source_asof"] == "2026-08-07"

    missing = fs.read_served(tmp_path, "/prophet/nope.json")
    assert missing.error and missing.status is None
    # A sentinel pointed at the wrong root reports blindness, never an outage.
    assert fs.check_surface(_prophet_surface(), missing, NOW)["status"] == "indeterminate"


def test_prophet_non_json_body_is_indeterminate_not_stale():
    """A login page, an error shell or a half-written file mid-rsync is a
    transport failure wearing a 200. It escalates through the blindness counter
    — it must not be read as an outage verdict in either direction."""
    results = _fresh_results()
    results["prophet_us"] = _prophet(body="<html>Sign in to continue</html>")
    report = fs.evaluate(results, NOW)
    assert report["stale_surfaces"] == []
    assert report["indeterminate_surfaces"] == ["prophet_us"]
    assert "not JSON" in report["surfaces"]["prophet_us"]["detail"]


def test_prophet_payload_without_an_asof_is_a_breach_not_a_silent_pass():
    """Well-formed JSON that cannot say when it is from is a definitive
    regression in the artifact. "I can't tell" must never render as "fresh"."""
    results = _fresh_results()
    results["prophet_us"] = _prophet(asof=None)
    report = fs.evaluate(results, NOW)
    assert report["stale_surfaces"] == ["prophet_us"]
    assert "cannot vouch for its own date" in report["surfaces"]["prophet_us"]["detail"]


def test_prophet_budget_is_tighter_than_the_board_budgets():
    """Stated so a later widening is a deliberate edit, not a drift: Prophet is
    the surface a reader acts on, and a calendar anchor lets its budget be tight
    without flapping on the closures that force the others wide."""
    assert fs.PROPHET_MAX_SESSIONS_BEHIND == 1
    assert _prophet_surface()["asof_max_sessions_behind"] == 1
    board_budgets = [s["delay_budget_days"] for s in fs.SURFACES
                     if s["delay_budget_days"] is not None]
    assert board_budgets and min(board_budgets) > fs.PROPHET_MAX_SESSIONS_BEHIND


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
            continue  # function-scoped (lazy) — app.mailer, lib.nyse_calendar, hashlib
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            assert node.module != "app", "app.mailer import must stay lazy"
            # lib.nyse_calendar is stdlib-only itself, but a module-level import
            # would still let a half-pulled repo take the watchdog down instead
            # of degrading the one surface that needs it to indeterminate.
            assert node.module != "lib", "lib.nyse_calendar import must stay lazy"
            names = [node.module]
        else:
            names = [a.name for a in node.names]
        for name in names:
            assert name in stdlib_ok, f"non-stdlib module-level import: {name}"


# --------------------------------------------------------------------------- #
# china board-lag arming (templates/china.html.j2 delayed-board disclosure)
# --------------------------------------------------------------------------- #
#: china's rendering of the marker. Same English phrase the regex anchors on,
#: different surrounding copy from us_stocks — this body proves the sentinel
#: reads the CHINA wording, not just the dashboard one.
CN_OUTAGE_BODY = (
    "<html>FX data as of 2026-08-07 "
    "<strong>⚠ BOARD DELAYED</strong> — prices as of 2026-07-20 (19d behind). "
    "Data is stale; readings on this page may not reflect latest prices.</html>"
)

#: Same marker, lag still inside the holiday budget.
CN_HOLIDAY_BODY = CN_OUTAGE_BODY.replace("2026-07-20", "2026-08-01")


def _china_surface() -> dict:
    return next(s for s in fs.SURFACES if s["id"] == "china")


def test_china_is_armed_on_the_board_marker():
    """china carries a board-lag budget — it is no longer bake-only.

    Reverting delay_budget_days to None fails here, and would also silence
    test_china_breaches_when_its_board_lag_exceeds_the_budget below.
    """
    assert _china_surface()["delay_budget_days"] == 12


def test_china_budget_clears_the_longest_mainland_closure():
    """The budget is a calendar fact, not a slack allowance.

    Spring Festival and National Day Golden Week each run ~9-10 CALENDAR days
    with no A-share session, and lib/cn_calendar.py's holiday table is minimal
    on purpose, so china may legitimately print its disclosure part-way through
    one. The budget has to clear that or the sentinel pages every October.
    """
    assert _china_surface()["delay_budget_days"] > 10


def test_china_page_is_fetched_with_a_body_now():
    """run() decides GET-vs-HEAD from the budget: a None budget fetches no body,
    and a body-less china page can never be parsed for the marker."""
    assert _china_surface()["delay_budget_days"] is not None


def test_china_breaches_when_its_board_lag_exceeds_the_budget():
    """The china twin of the Jul-31 replay: bake stamp fresh (the page re-bakes
    nightly throughout), FX widget stamp fresh, board marker frozen 19 days."""
    results = _fresh_results()
    results["china"] = _page(2.0, CN_OUTAGE_BODY)
    report = fs.evaluate(results, NOW)

    assert report["ok"] is False
    assert report["stale_surfaces"] == ["china"]
    c = report["surfaces"]["china"]
    assert c["board_delayed"] is True
    assert c["board_price_through"] == "2026-07-20"
    assert "prices as of 2026-07-20" in c["detail"]
    # the failure mode Last-Modified alone cannot see
    assert "page re-bakes are landing, board data is not" in c["detail"]


def test_china_holiday_length_lag_is_not_a_breach():
    """A Golden-Week-length lag with the marker showing is honest, not an
    outage. Tightening the budget under the longest legitimate closure fails
    here — that is the false-positive this budget exists to prevent."""
    results = _fresh_results()
    results["china"] = _page(2.0, CN_HOLIDAY_BODY)
    report = fs.evaluate(results, NOW)

    assert report["ok"] is True
    assert report["stale_surfaces"] == []
    c = report["surfaces"]["china"]
    # the marker WAS parsed — this is budget tolerance, not a failure to read
    assert c["board_delayed"] is True
    assert c["board_price_through"] == "2026-08-01"
    assert c["status"] == "ok"


def test_china_fx_widget_stamp_is_not_mistaken_for_a_board_marker():
    """china.html's only pre-existing 'as of' was an FX widget stamp. It must
    never register as a board delay — that would arm the surface on a string
    that stays fresh while the board freezes."""
    fx_only = "<html><div>FX data as of 2026-08-07</div>rotation as of 2026-08-07</html>"
    assert fs.board_delay_stamp(fx_only) is None

    results = _fresh_results()
    results["china"] = _page(2.0, fx_only)
    report = fs.evaluate(results, NOW)
    assert report["stale_surfaces"] == []
    assert report["surfaces"]["china"]["board_delayed"] is False
