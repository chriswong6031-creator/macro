"""Regression — the public /api/status endpoint must not leak raw exception
strings (absolute server paths) to anonymous callers.

WHY THIS EXISTS (pre-launch hardening, 2026-07-26): /api/status is public +
unauthenticated. Two except branches in app.main.status() returned
``{"error": str(e), ...}``; for a FileNotFoundError / IsADirectoryError /
PermissionError, ``str(e)`` embeds the artifact's ABSOLUTE path (e.g.
``/opt/macro/site/live/overlay.json``) — a path-disclosure leak (CWE-209, the
same class PR #3615 closed for the billing/auth routes). The fix coarsens the
client-facing error to a generic ``"unavailable"`` token and logs the real
detail server-side via the ``macro.api`` logger.

These tests pin the properties that matter so the leak cannot silently return:

  1. a broken live-lane artifact -> check present, error=="unavailable", no path leak
  2. a broken terminal_data manifest -> same
  3. age_min survives on the coarsened live-lane check — the dead-man monitor
     (scripts/check_vps_live_health.py) keys off age_min and NEVER reads `error`
  4. the happy-path envelope is unchanged: 200 + status=="ok"
  5. /api/health stays 200 (co-resident diagnostic — must not regress)

Offline: no network, no Supabase, no Stripe — TestClient against the mounted
app with the artifacts pointed at throwaway temp paths.

Run:
    python -m pytest tests/test_status_error_leak.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def test_status_coarsens_broken_artifact_errors_without_leaking_paths(
    client, tmp_path, monkeypatch
):
    """A live artifact and the terminal manifest that both fail to read must
    surface a generic token — never the absolute path in the exception string."""
    import app.main as main

    # A path that .exists() is True for but whose .read_text() raises with the
    # absolute path in the message (IsADirectoryError, [Errno 21]). This is the
    # deterministic stand-in for the FileNotFoundError/PermissionError class the
    # task flags. The sentinel component lets us assert the path never reaches
    # the client — pre-fix str(e) contained it; post-fix it is coarsened away.
    live_leak = tmp_path / "SENTINEL_LIVE_LEAK"
    live_leak.mkdir()
    monkeypatch.setattr(main, "_live_artifact", lambda name: live_leak)

    term_leak = tmp_path / "SENTINEL_TERMINAL_LEAK"
    term_leak.mkdir()
    monkeypatch.setattr(main, "TERMINAL_MANIFEST", term_leak)

    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok", "the 200/ok envelope must be preserved"

    checks = body["checks"]

    # Every live lane hit the coarsened branch; the per-check key is still present
    # (so monitoring can see WHICH check failed) and carries the generic token.
    live = checks["overlay"]
    assert live["error"] == "unavailable"
    assert "age_min" in live, (
        "age_min must survive coarsening — scripts/check_vps_live_health.py keys "
        "off it and would otherwise flag a false 'missing or invalid age'"
    )

    assert checks["terminal_data"]["error"] == "unavailable"

    # THE leak assertion: no absolute artifact path anywhere in the payload.
    raw = r.text
    assert "SENTINEL_LIVE_LEAK" not in raw
    assert "SENTINEL_TERMINAL_LEAK" not in raw
    assert str(tmp_path) not in raw


def test_status_happy_envelope_and_health_both_return_200(client):
    """No monkeypatching: the endpoints return their healthy 200 shape.

    In a fresh checkout the live artifacts are simply absent, so each check is
    {"status": "missing"} — the envelope stays status=="ok" and both /api/status
    and /api/health answer 200 on the happy path (task acceptance requirement)."""
    r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    h = client.get("/api/health")
    assert h.status_code == 200


def test_status_reports_release_semantics_not_only_file_age(
    client, tmp_path, monkeypatch
):
    import app.main as main

    scheduled = datetime.now(ZoneInfo("America/New_York")) - timedelta(minutes=3)
    release = tmp_path / "release_publications.json"
    release.write_text(
        json.dumps(
            {
                "schema": "release_publications.v2",
                "built": datetime.now().astimezone().isoformat(),
                "due": [{"type": "FOMC"}],
                "publications": [],
                "events": [
                    {
                        "type": "FOMC",
                        "date": scheduled.date().isoformat(),
                        "time_et": scheduled.strftime("%H:%M"),
                        "status": "awaiting_publication",
                    }
                ],
                "source_health": [{"source_id": "fed_fomc", "status": "error"}],
            }
        ),
        encoding="utf-8",
    )

    def artifact(name: str):
        return release if name == "release_publications.json" else tmp_path / name

    monkeypatch.setattr(main, "_live_artifact", artifact)
    response = client.get("/api/status")
    assert response.status_code == 200
    check = response.json()["checks"]["release_publications"]
    assert check["event_status"] == {"awaiting_publication": 1}
    assert check["source_errors"] == 1
    assert 2 <= check["max_publication_lag_min"] <= 4


def test_status_exposes_unparsed_high_impact_publication(
    client, tmp_path, monkeypatch
):
    import app.main as main

    scheduled = datetime.now(ZoneInfo("America/New_York")) - timedelta(minutes=4)
    event = {
        "event_id": f"fomc:{scheduled.date().isoformat()}",
        "type": "FOMC",
        "date": scheduled.date().isoformat(),
        "time_et": scheduled.strftime("%H:%M"),
        "status": "published_unparsed",
        "data_ready": False,
    }
    release = tmp_path / "release_publications.json"
    release.write_text(
        json.dumps(
            {
                "schema": "release_publications.v2",
                "built": datetime.now().astimezone().isoformat(),
                "due": [event],
                "publications": [event],
                "events": [event],
                "source_health": [{"source_id": "fed_fomc", "status": "ok"}],
            }
        ),
        encoding="utf-8",
    )

    def artifact(name: str):
        return release if name == "release_publications.json" else tmp_path / name

    monkeypatch.setattr(main, "_live_artifact", artifact)
    check = client.get("/api/status").json()["checks"]["release_publications"]
    assert check["event_status"] == {"published_unparsed": 1}
    assert check["published"] == 1
    assert check["verified_publications"] == 0
    assert check["unparsed_publications"] == 1
    assert 3 <= check["max_publication_lag_min"] <= 5
