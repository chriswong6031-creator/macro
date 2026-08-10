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


def _provisional(as_of: str | None = PROPHET_CURRENT_ASOF, *,
                 mtime_age_hours: float = 12.0) -> fs.FetchResult:
    """One live-plane read of us_board_provisional.json (W-L1a close pass)."""
    doc: dict = {"schema": "us_board_provisional/v1", "lane": "closepass",
                 "provisional": True}
    if as_of is not None:
        doc["as_of"] = as_of
    return fs.FetchResult(
        status=200, last_modified=NOW - timedelta(hours=mtime_age_hours),
        body=json.dumps(doc),
    )


#: The path the READER's browser polls. The dashboard never fetches
#: us_board_provisional.json — it paints from the ``board_state`` key on this
#: artifact (templates/dashboard.html.j2 ``_plvData.board_state``), which a
#: separate, later step merges in and which fails dark on its own.
CLIENT_PATH = "/live/prophet_live.json"


def _live_strip(as_of: str | None = PROPHET_CURRENT_ASOF, *,
                key: str = "board_state") -> fs.FetchResult:
    """One live-plane read of prophet_live.json — the artifact the client polls.

    ``as_of=None`` is the shape that matters most: the evaluator's artifact
    present and healthy with NO ``board_state`` on it at all. That is what the
    plane looks like for most of every day (the evaluator rewrites the file
    whole every five minutes and carries no board_state of its own) and it is
    what the plane looks like all evening when annotate_live_strip fails dark.
    """
    doc: dict = {"schema": "prophet_live/v1", "status": "live", "states": []}
    if as_of is not None:
        doc[key] = {"rel": "ahead", "note": "ahead",
                    "board": {"as_of": as_of, "lane": "closepass",
                              "tickers": ["AAPL", "MSFT"]}}
    return fs.FetchResult(
        status=200, last_modified=NOW - timedelta(hours=12), body=json.dumps(doc),
    )


#: What read_served returns for a file that is simply not there — the ordinary
#: pre-publication state of the close-pass artifact for most of every day.
ABSENT = fs.FetchResult(error="served read failed: FileNotFoundError: [Errno 2] …")


def _served(result: fs.FetchResult, live: fs.FetchResult | None = None,
            strip: fs.FetchResult | None = None):
    """A served_reader stand-in.

    PATH-AWARE, because one reader now answers three different artifacts: the
    git-rsynced site.served tree (``/prophet/index.json``), the daemon-written
    close-pass board (``/live/us_board_provisional.json``) and the client
    artifact the SLA is measured against (``/live/prophet_live.json``). A stub
    that answered them with the same body would hand one surface's payload to a
    surface judged on a different field and manufacture a breach that has
    nothing to do with the case under test — and, for the strip specifically,
    would let a board payload with no ``board_state`` masquerade as a reader who
    can see something.
    """
    fallback = _provisional() if live is None else live
    strip = _live_strip() if strip is None else strip

    def _read(root, path):
        if path == CLIENT_PATH:
            return strip
        return fallback if path.startswith("/live/") else result
    return _read


def _fresh_results() -> dict[str, fs.FetchResult]:
    return {
        "us_stocks": _page(14.0),
        "china": _page(7.0),
        "hub": _page(14.0),
        "r2_massive_stock_day": _r2(10.0),
        "prophet_us": _prophet(),
        "us_board_provisional": _provisional(),
    }


def _client_reads(as_of: str | None = PROPHET_CURRENT_ASOF, **kw
                  ) -> dict[str, fs.FetchResult]:
    """The reader-side reads evaluate() folds into the SLA surfaces."""
    return {CLIENT_PATH: _live_strip(as_of, **kw)}


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
        # prophet_us and us_board_provisional are judged on content, not on a
        # stamp — they stay ok here, which is the point: the four bake surfaces
        # answer independently.
        "prophet_us": _prophet(),
        "us_board_provisional": _provisional(),
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
            "us_board_provisional": _provisional(),
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
        if path == CLIENT_PATH:
            return _live_strip()
        return _provisional() if path.startswith("/live/") else _prophet()

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
    # The close-pass board is walled for the same reason (#3391 — the real board
    # is not free content) and is read off the LIVE PLANE root, not the
    # site.served tree and not over HTTP. The client artifact the SLA is
    # measured against is walled harder still — /live/prophet_live.json names
    # which tickers are armed (research/PAYWALL_GIT_MIRROR_EXPOSURE_ADJUDICATION
    # .md) and is deliberately NOT in the public /live/ allowlist — so the
    # reader-side read goes to the same live-plane root as the board and never
    # over HTTP either. Two roots, one reader, zero HTTP.
    assert reads == [
        ("/opt/macro/site.served", "/prophet/index.json"),
        (str(tmp_path / "public"), "/live/us_board_provisional.json"),
        (str(tmp_path / "public"), CLIENT_PATH),
    ]
    assert not [u for u in urls if "us_board_provisional" in u], urls
    assert not [u for u in urls if "prophet_live" in u], urls


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


# --------------------------------------------------------------------------- #
# W-L1a — the SLA record ("was the evening board live by 18:30 ET?")
#
# staleness.json and state.json are both overwritten every pass, so before this
# the estate could answer "is it fresh NOW" and could not answer the only
# question the W-L1 gate asks. These pin the two ways such a record silently
# lies: keying it on the wrong clock, and counting a streak over its own gaps.
# --------------------------------------------------------------------------- #
#: 16:47 EDT on Friday 2026-08-07 — inside the 18:30 deadline, on the session's
#: own ET day. The UTC hour (20:47) is deliberately one that reads as MISSED if
#: anything on the path forgets to convert to Eastern.
ON_TIME = datetime(2026, 8, 7, 20, 47, tzinfo=timezone.utc)
#: 21:30 EDT the same session day — published, but after the deadline.
LATE = datetime(2026, 8, 8, 1, 30, tzinfo=timezone.utc)
#: 01:00 EDT on 08-08 — the next ET morning, still describing the 08-07 session.
NEXT_MORNING = NOW


#: "not passed" — distinct from an explicit None, which MEANS "the reader sees
#: nothing" and is the whole point of the divergence tests below.
_UNSET = object()


def _ok_report(session: str = "2026-08-07", now: datetime = ON_TIME,
               client=_UNSET) -> dict:
    """A pass on which the board is fresh AND the reader can see that session.

    ``client`` defaults to agreeing with the board, which is the healthy case
    every pre-existing test here was written against. Pass it explicitly to
    build the divergence: ``client=None`` is a fresh board with a dark surface,
    a date is a reader looking at some OTHER session.
    """
    results = _fresh_results()
    results["us_board_provisional"] = _provisional(session)
    reads = _client_reads(session if client is _UNSET else client)
    return fs.evaluate(results, now, client_reads=reads)


def test_the_sla_record_stamps_the_first_fresh_read_and_never_rewrites_it():
    """First is first, forever. A later pass re-stamping would erase the only
    measurement the gate has — and every pass after the board lands reads fresh,
    so an overwrite-on-write record would converge on "landed at 23:55"."""
    rec = fs.record_first_fresh({}, _ok_report(), ON_TIME)
    entry = rec["sessions"]["2026-08-07"]["us_board_provisional"]
    assert entry["first_fresh_at"] == ON_TIME.isoformat()
    assert entry["first_fresh_et"] == "16:47"
    assert entry["met"] is True
    assert rec["schema"] == fs.FIRST_FRESH_SCHEMA

    # Three more passes over the same session leave the stamp untouched.
    for minutes in (30, 60, 400):
        later = ON_TIME + timedelta(minutes=minutes)
        rec = fs.record_first_fresh(rec, _ok_report(now=later), later)
    assert rec["sessions"]["2026-08-07"]["us_board_provisional"] == entry


def test_the_sla_record_is_keyed_on_the_session_not_the_wall_clock():
    """The two disagree for five hours every evening. A UTC-date key would file
    the 20:47Z measurement under 08-07 by luck and the 01:30Z one under 08-08 —
    splitting one session's record across two keys on the very lane it measures.
    """
    rec = fs.record_first_fresh({}, _ok_report(now=LATE), LATE)
    assert list(rec["sessions"]) == ["2026-08-07"]          # NOT 2026-08-08

    # And a genuinely different session gets its own key rather than merging.
    rec = fs.record_first_fresh(rec, _ok_report("2026-08-06"), ON_TIME)
    assert sorted(rec["sessions"]) == ["2026-08-06", "2026-08-07"]


def test_a_late_publish_is_recorded_and_scored_missed_not_dropped():
    """Honesty in both directions: the record keeps the measurement AND the
    verdict. Dropping a late board would make a missed SLA indistinguishable
    from a board that never published."""
    rec = fs.record_first_fresh({}, _ok_report(now=LATE), LATE)
    entry = rec["sessions"]["2026-08-07"]["us_board_provisional"]
    assert entry["first_fresh_et"] == "21:30"
    assert entry["met"] is False


def test_a_board_that_lands_after_midnight_et_never_scores_as_met():
    """01:00 ET reads "01:00 <= 18:30" on the clock alone and would score as a
    comfortable pass on a session it missed by seven hours. The date half of the
    comparison is what stops that."""
    rec = fs.record_first_fresh({}, _ok_report(now=NEXT_MORNING), NEXT_MORNING)
    entry = rec["sessions"]["2026-08-07"]["us_board_provisional"]
    assert entry["first_fresh_et"] == "01:00"
    assert entry["met"] is False


def test_an_indeterminate_pass_stamps_nothing():
    """A pass that could not read the artifact says nothing about when it
    landed. Stamping it would record a time the board may not have existed at."""
    results = _fresh_results()
    results["us_board_provisional"] = ABSENT
    rec = fs.record_first_fresh({}, fs.evaluate(results, ON_TIME), ON_TIME)
    assert rec.get("sessions") in (None, {})


def test_a_stale_board_stamps_nothing():
    """`ok` only. A board four sessions behind is present and readable and is
    not the evening board this SLA is about."""
    results = _fresh_results()
    results["us_board_provisional"] = _provisional("2026-07-28")
    report = fs.evaluate(results, ON_TIME)
    assert report["surfaces"]["us_board_provisional"]["status"] == "stale"
    assert fs.record_first_fresh({}, report, ON_TIME).get("sessions") in (None, {})


def test_the_streak_walks_the_exchange_calendar_so_a_gap_breaks_it():
    """The failure this exists to prevent: a session on which the board never
    published leaves NO key, so a streak counted over recorded rows steps
    straight over the miss and reports five green sessions that never happened.

    2026-08-03..07 is a clean Mon-Fri week. Recording four of them and skipping
    Wednesday must yield a streak of 2 (Fri, Thu), not 4.
    """
    rec: dict = {}
    for session, stamp in (
        ("2026-08-03", datetime(2026, 8, 3, 20, 40, tzinfo=timezone.utc)),
        ("2026-08-04", datetime(2026, 8, 4, 20, 40, tzinfo=timezone.utc)),
        # 08-05 deliberately missing — the lane did not publish that evening
        ("2026-08-06", datetime(2026, 8, 6, 20, 40, tzinfo=timezone.utc)),
        ("2026-08-07", datetime(2026, 8, 7, 20, 40, tzinfo=timezone.utc)),
    ):
        rec = fs.record_first_fresh(rec, _ok_report(session, stamp), stamp)

    streak, rows = fs.sla_streak(rec, "us_board_provisional", NOW, cap=5)
    assert [r["session"] for r in rows] == [
        "2026-08-07", "2026-08-06", "2026-08-05", "2026-08-04", "2026-08-03"
    ]
    assert [r["met"] for r in rows] == [True, True, False, True, True]
    assert streak == 2

    # Fill the gap and the same record now clears the five-session gate.
    gap = datetime(2026, 8, 5, 20, 40, tzinfo=timezone.utc)
    rec = fs.record_first_fresh(rec, _ok_report("2026-08-05", gap), gap)
    assert fs.sla_streak(rec, "us_board_provisional", NOW, cap=5)[0] == 5


def test_the_streak_is_anchored_on_completed_sessions_not_on_today():
    """expected_last_session, not date.today(): at 16:47 ET the session is not
    over (the 17:00 settle buffer), and judging a board on a day still in
    progress would score every in-flight session as a miss."""
    _, rows = fs.sla_streak({}, "us_board_provisional", ON_TIME, cap=1)
    assert rows[0]["session"] == "2026-08-06"      # not 08-07, still in flight


def test_the_public_summary_carries_the_streak_and_the_gate_threshold():
    rec: dict = {}
    for session in ("2026-08-05", "2026-08-06", "2026-08-07"):
        stamp = datetime.fromisoformat(f"{session}T20:40:00+00:00")
        rec = fs.record_first_fresh(rec, _ok_report(session, stamp), stamp)

    block = fs.sla_summary(rec, NOW)["us_board_provisional"]
    assert block["by_et"] == "18:30" and block["sessions_required"] == 5
    assert block["consecutive_met"] == 3
    assert block["recent"][0] == {"session": "2026-08-07",
                                  "first_fresh_et": "16:40", "met": True}
    # Timestamps and verdicts only — this rides the PUBLIC staleness file.
    assert set(block["recent"][0]) == {"session", "first_fresh_et", "met"}


def test_the_history_is_bounded():
    """Append-only must not mean unbounded — this file is written on a box whose
    disk filling up is one of the outages the sentinel exists to catch."""
    rec: dict = {}
    for i in range(fs.SLA_HISTORY_SESSIONS + 15):
        stamp = datetime(2026, 1, 1, 20, 40, tzinfo=timezone.utc) + timedelta(days=i)
        rec = fs.record_first_fresh(rec, _ok_report(stamp.date().isoformat(), stamp), stamp)
    assert len(rec["sessions"]) == fs.SLA_HISTORY_SESSIONS
    # The NEWEST are the ones kept — a gate reads the recent sessions.
    assert max(rec["sessions"]) == "2026-02-24"


def test_an_absent_close_pass_board_is_not_blindness():
    """This artifact publishes once a day, so it is legitimately missing for
    most of every day. Counting those hours toward the blindness escalation
    would page "the sentinel is blind" every morning by construction — the
    false-positive machine the module's own falsifier law forbids."""
    results = _fresh_results()
    results["us_board_provisional"] = ABSENT
    report = fs.evaluate(results, NOW)
    c = report["surfaces"]["us_board_provisional"]
    assert c["status"] == "indeterminate" and c["absent"] is True

    state: dict = {}
    for i in range(fs.BLIND_AFTER + 4):
        alerts, state = fs.decide_alerts(report, state, NOW + timedelta(minutes=30 * i))
        assert alerts == [], alerts
    assert "us_board_provisional" not in (state.get("blind_counts") or {})


def test_only_a_missing_file_is_absent_a_broken_read_is_still_blindness():
    """Narrow on purpose. A permission error or a truncated read is the sentinel
    failing to see, and exempting those would disarm the surface entirely."""
    for err in ("served read failed: PermissionError: [Errno 13] denied",
                "served body exceeded 2000000 byte cap"):
        results = _fresh_results()
        results["us_board_provisional"] = fs.FetchResult(status=200, error=err)
        c = fs.evaluate(results, NOW)["surfaces"]["us_board_provisional"]
        assert c["status"] == "indeterminate" and c["absent"] is False, err


def test_a_dead_close_pass_lane_still_breaches_on_its_own_asof():
    """The absence exemption must not become a way for the lane to die quietly:
    once a board IS present and two sessions stale, it breaches like any other
    surface (the same 'breach by day 2' shape prophet_us uses)."""
    results = _fresh_results()
    results["us_board_provisional"] = _provisional("2026-08-05")   # 2 behind at NOW
    report = fs.evaluate(results, NOW)
    c = report["surfaces"]["us_board_provisional"]
    assert c["status"] == "stale" and c["asof_sessions_behind"] == 2
    assert "budget 1" in c["detail"]

    # One missed evening is absorbed — the second is what pages.
    results["us_board_provisional"] = _provisional("2026-08-06")
    assert fs.evaluate(results, NOW)["surfaces"]["us_board_provisional"]["status"] == "ok"


def test_the_record_is_written_beside_the_state_and_rides_the_public_report(
        tmp_path, monkeypatch):
    """End to end through run(): a private append-only record on the state dir,
    a public summary inside staleness.json, and no third file anywhere."""
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL",
                "DISCORD_WEBHOOK_WATCHLIST", "MAIL_SENTINEL_TO", "MAIL_SUPPORT_TO"):
        monkeypatch.delenv(var, raising=False)

    def fresh_fetcher(url, *, want_body):
        return fs.FetchResult(status=200, last_modified=ON_TIME - timedelta(hours=10),
                              body=HEALTHY_BODY if want_body else None)

    assert fs.run(now=ON_TIME, base="https://example.invalid",
                  r2_base="https://example.invalid",
                  public_dir=tmp_path / "public", state_dir=tmp_path / "state",
                  fetcher=fresh_fetcher,
                  served_reader=_served(_prophet())) == 0

    record = json.loads((tmp_path / "state" / "first_fresh.json").read_text())
    assert record["sessions"]["2026-08-07"]["us_board_provisional"]["met"] is True
    assert sorted(p.name for p in (tmp_path / "state").iterdir()) == [
        "first_fresh.json", "state.json"
    ]
    served = json.loads((tmp_path / "public" / "live" / "staleness.json").read_text())
    assert served["sla"]["us_board_provisional"]["consecutive_met"] == 0  # 08-07 in flight
    assert served["sla"]["us_board_provisional"]["by_et"] == "18:30"


def test_a_dry_run_reads_the_record_without_stamping_it(tmp_path, monkeypatch, capsys):
    """The operator's lever for evaluating the gate must not perturb the very
    measurement it reads."""
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL",
                "DISCORD_WEBHOOK_WATCHLIST", "MAIL_SENTINEL_TO", "MAIL_SUPPORT_TO"):
        monkeypatch.delenv(var, raising=False)

    fs.run(now=ON_TIME, base="https://example.invalid", r2_base="https://example.invalid",
           public_dir=tmp_path / "public", state_dir=tmp_path / "state", dry_run=True,
           fetcher=lambda url, *, want_body: fs.FetchResult(
               status=200, last_modified=ON_TIME, body=HEALTHY_BODY if want_body else None),
           served_reader=_served(_prophet()))
    assert not (tmp_path / "state").exists()
    out = capsys.readouterr().out
    assert "SLA by 18:30 ET" in out and "0 consecutive of 5 required" in out


def test_no_tzdata_reports_unknown_rather_than_a_utc_verdict(monkeypatch):
    """A box without a timezone database must not answer in UTC: 20:47Z would
    read as "missed the 18:30 deadline" on a session the board made with 100
    minutes to spare. Unknown, never a wrong verdict.

    This also proves the reader condition did not fork the clock: _ok_report now
    carries a matching client read, so the stamp reaches the ET comparison, and
    stubbing the ONE ``_et`` still governs the whole verdict."""
    monkeypatch.setattr(fs, "_et", lambda stamp: None)
    entry = fs.record_first_fresh({}, _ok_report(), ON_TIME)[
        "sessions"]["2026-08-07"]["us_board_provisional"]
    assert entry["met"] is None and entry["first_fresh_et"] is None
    assert entry["first_fresh_at"] == ON_TIME.isoformat()   # the raw fact survives


# --------------------------------------------------------------------------- #
# W-L1 — the SLA measures the READER, not the artifact
#
# The gate is "fresh US picks live on the site by 18:30 ET". The sentinel budgets
# live/us_board_provisional.json, and NO reader's browser fetches that file: the
# dashboard polls live/prophet_live.json and paints from its top-level
# `board_state` key (templates/dashboard.html.j2, `_plvData.board_state`).
#
# The two are written by the same 5-minute timer seconds apart, which is exactly
# why the divergence hides: scripts/close_pass_mirror.run() publishes the full
# board FIRST and unconditionally, then calls annotate_live_strip(), which
# returns False WITHOUT WRITING whenever the evaluator's artifact is absent or
# unparseable — and run() discards that return and exits 0. Board perfect, page
# dark, sentinel green. These pin that the SLA can no longer score such a
# session as a pass.
# --------------------------------------------------------------------------- #
def test_a_fresh_on_time_board_the_reader_cannot_see_is_not_a_met_sla():
    """THE DEFECT. The board is fresh, on time, on its own ET day — every
    condition the old SLA checked — and the client-visible key is simply not
    there, which is what annotate_live_strip failing dark leaves behind. The old
    record stamped met=True here and the gate counted it toward five green
    sessions while no reader saw anything."""
    report = _ok_report(client=None)
    c = report["surfaces"]["us_board_provisional"]
    # Everything the artifact-side check can see still reads perfect...
    assert c["status"] == "ok" and c["asof"] == "2026-08-07"
    assert report["stale_surfaces"] == [] and report["indeterminate_surfaces"] == []
    # ...and the SLA refuses to stamp, because the reader saw nothing.
    assert c["client_session"] is None
    rec = fs.record_first_fresh({}, report, ON_TIME)
    assert rec.get("sessions") in (None, {})

    # A withheld stamp is not a silent hole: the calendar walk reads it MISSED,
    # which is what breaks the five-session streak the gate is measured on.
    _, rows = fs.sla_streak(rec, "us_board_provisional", NOW, cap=1)
    assert rows == [{"session": "2026-08-07", "first_fresh_et": None, "met": False}]


def test_a_reader_looking_at_another_session_is_not_a_met_sla():
    """The stale-key twin of the absent-key case. prophet_live.json is rewritten
    whole by the Prophet evaluator and re-annotated by the mirror, so a surviving
    key from a previous evening is a real state — and a page showing YESTERDAY's
    board is not tonight's picks being live."""
    report = _ok_report("2026-08-07", client="2026-08-06")
    assert report["surfaces"]["us_board_provisional"]["client_session"] == "2026-08-06"
    assert fs.record_first_fresh({}, report, ON_TIME).get("sessions") in (None, {})

    # And the agreeing case still stamps — the condition is "same session", not
    # "no client key ever qualifies".
    rec = fs.record_first_fresh({}, _ok_report("2026-08-07"), ON_TIME)
    assert rec["sessions"]["2026-08-07"]["us_board_provisional"]["met"] is True


def test_a_key_that_lands_after_the_deadline_is_stamped_late_not_dropped():
    """The honest middle case: the board was on time, the surface was dark until
    21:30 ET. The SLA measures when the READER could see it, so the stamp records
    the late time and scores MISSED — not a pass (the board was on time) and not
    a hole (something did eventually publish)."""
    rec = fs.record_first_fresh({}, _ok_report(client=None), ON_TIME)
    assert rec.get("sessions") in (None, {})           # 16:47 ET: nothing to see

    rec = fs.record_first_fresh(rec, _ok_report(now=LATE), LATE)
    entry = rec["sessions"]["2026-08-07"]["us_board_provisional"]
    assert entry["first_fresh_et"] == "21:30" and entry["met"] is False


def test_the_streak_breaks_on_a_session_the_reader_never_saw():
    """End to end on the gate's own unit. Five clean Mon-Fri sessions, all with a
    fresh on-time board, one of them dark to the reader: the gate must read 2,
    not 5. This is the whole point — the old code returned 5 here."""
    rec: dict = {}
    for session, dark in (("2026-08-03", False), ("2026-08-04", False),
                          ("2026-08-05", True), ("2026-08-06", False),
                          ("2026-08-07", False)):
        stamp = datetime.fromisoformat(f"{session}T20:40:00+00:00")
        rec = fs.record_first_fresh(
            rec, _ok_report(session, stamp, client=None if dark else _UNSET), stamp)

    streak, rows = fs.sla_streak(rec, "us_board_provisional", NOW, cap=5)
    assert [r["met"] for r in rows] == [True, True, False, True, True]
    assert streak == 2
    assert fs.sla_summary(rec, NOW)["us_board_provisional"]["consecutive_met"] == 2


@pytest.mark.parametrize("read,label", [
    (ABSENT, "no file at all"),
    (fs.FetchResult(status=200, body="<html>login</html>"), "unparseable body"),
    (fs.FetchResult(status=200, body='{"status":"dark","reason":"no_pack"}'),
     "healthy artifact, no board_state key"),
    (fs.FetchResult(status=200, body='{"board_state":{"rel":"ahead"}}'),
     "board_state present but naming no session"),
    (fs.FetchResult(error="served read failed: PermissionError"), "unreadable"),
])
def test_a_dark_reader_never_breaches_never_blinds_and_never_pages(read, label):
    """THE FALSE-POSITIVE GATE. ``board_state`` is legitimately absent for most of
    every day — the evaluator rewrites prophet_live.json whole every five minutes
    and carries no board_state of its own, so the key exists only between the
    evening annotate and the next morning's first evaluator pass. A reader-side
    read that could breach would page daily by construction, which is the
    factory this module's falsifier law forbids.

    Structural, not conditional: the client artifact is NOT a surface. It cannot
    reach stale_surfaces, indeterminate_surfaces or the blindness counters at
    all — the only thing it can do is withhold a stamp."""
    results = _fresh_results()
    report = fs.evaluate(results, NOW, client_reads={CLIENT_PATH: read})

    assert report["ok"] is True, label
    assert report["stale_surfaces"] == [] and report["indeterminate_surfaces"] == []
    assert CLIENT_PATH not in report["surfaces"], label
    assert not [k for k in report["surfaces"] if "prophet_live" in k], label
    assert report["surfaces"]["us_board_provisional"]["client_session"] is None, label

    state: dict = {}
    for i in range(fs.BLIND_AFTER + 4):
        alerts, state = fs.decide_alerts(report, state, NOW + timedelta(minutes=30 * i))
        assert alerts == [], (label, alerts)
    assert state.get("blind_counts") == {}, label


def test_the_reader_condition_cannot_manufacture_a_breach_on_the_board_itself():
    """The board surface's own verdict is untouched by the reader read: a dark
    surface must not turn a healthy board stale, and a visible one must not
    launder a stale board fresh."""
    results = _fresh_results()
    for read in (ABSENT, _live_strip(), _live_strip(None)):
        c = fs.evaluate(results, NOW, client_reads={CLIENT_PATH: read}
                        )["surfaces"]["us_board_provisional"]
        assert c["status"] == "ok"

    results["us_board_provisional"] = _provisional("2026-08-05")   # 2 behind
    c = fs.evaluate(results, NOW, client_reads=_client_reads("2026-08-05")
                    )["surfaces"]["us_board_provisional"]
    assert c["status"] == "stale"
    assert fs.record_first_fresh({}, fs.evaluate(
        results, NOW, client_reads=_client_reads("2026-08-05")),
        NOW).get("sessions") in (None, {})


def test_the_et_boundary_protections_survive_the_reader_condition():
    """Both clock traps this module already defeats, re-run with the reader
    condition in the path — a second comparison bolted on beside the first is
    how one of them silently comes back.

      * 20:47Z is 16:47 EDT: MET. Read as UTC it is 20:47 > 18:30 and would
        score MISSED on a session made with 100 minutes to spare.
      * 01:00 EDT the next morning reads "01:00 <= 18:30" on the clock alone and
        would score a comfortable pass on a session missed by seven hours; the
        DATE half of the comparison is what stops it.
    """
    on_time = fs.record_first_fresh({}, _ok_report(), ON_TIME)[
        "sessions"]["2026-08-07"]["us_board_provisional"]
    assert on_time["first_fresh_et"] == "16:47" and on_time["met"] is True

    morning = fs.record_first_fresh({}, _ok_report(now=NEXT_MORNING), NEXT_MORNING)[
        "sessions"]["2026-08-07"]["us_board_provisional"]
    assert morning["first_fresh_et"] == "01:00" and morning["met"] is False


def test_the_deadline_comparison_is_reused_never_duplicated():
    """One clock comparison in the module, executed by every path. A second one
    would drift — and the two traps above are exactly what drift restores."""
    src = Path(fs.__file__).read_text(encoding="utf-8")
    assert src.count('<= sla["by_et"]') == 1, (
        "the 18:30 deadline must be compared in exactly one place"
    )


def test_a_dark_reader_is_diagnosable_from_the_operator_line_and_the_report(
        tmp_path, monkeypatch, capsys):
    """A condition that silently never stamps is indistinguishable from a broken
    sentinel, and this one is meant to be read by a human deciding whether the
    W-L1 gate has passed. The pass must SAY which half is dark."""
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DISCORD_WEBHOOK_URL",
                "DISCORD_WEBHOOK_WATCHLIST", "MAIL_SENTINEL_TO", "MAIL_SUPPORT_TO"):
        monkeypatch.delenv(var, raising=False)

    def fresh_fetcher(url, *, want_body):
        return fs.FetchResult(status=200, last_modified=ON_TIME - timedelta(hours=10),
                              body=HEALTHY_BODY if want_body else None)

    assert fs.run(now=ON_TIME, base="https://example.invalid",
                  r2_base="https://example.invalid",
                  public_dir=tmp_path / "public", state_dir=tmp_path / "state",
                  fetcher=fresh_fetcher,
                  served_reader=_served(_prophet(), strip=_live_strip(None))) == 0

    out = capsys.readouterr().out
    assert "us_board_provisional: ok" in out and "reader DARK" in out
    served = json.loads((tmp_path / "public" / "live" / "staleness.json").read_text())
    assert served["surfaces"]["us_board_provisional"]["client_session"] is None
    assert served["ok"] is True                       # dark reader never pages
    # The SLA is the only thing that noticed, which is the design.
    assert json.loads(
        (tmp_path / "state" / "first_fresh.json").read_text()).get("sessions") in (
            None, {})
