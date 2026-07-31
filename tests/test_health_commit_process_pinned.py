"""Regression — /api/health's ``commit`` must report the build the PROCESS is
serving, not whatever /opt/macro's checkout happens to be at request time.

WHY THIS EXISTS (observed live 2026-07-31): the VPS pull loop advances the
/opt/macro checkout every 3 minutes, but macro-api restarts only when the
deploy regex matches its own code (app/deploy/update.sh). The old handler
shelled ``git rev-parse`` per request, so the box pulled 42ab7b88bad at
01:24:10Z with (correctly) no restart and health immediately reported the NEW
sha while pid 1405846 was still serving code imported at 01:18:03Z. An
operator confirming an API deploy from that field was misled — in BOTH
directions (fresh sha over stale code, and, after a pull that DID restart, the
window where checkout advances again before the next deploy).

The fix pins ``commit`` at module import (app.main._PROCESS_COMMIT) — the
truthful "build this process is serving" — and adds ``checkout`` as the live
per-request read, so drift becomes visible instead of hidden. /api/status's
top-level ``commit`` follows the same contract; its checks["site"].commit
stays the LIVE read on purpose (that check reports the 3-min pull loop).

Offline: no network — TestClient against the mounted app; the live git read is
monkeypatched where a controlled value is needed.

Run:
    python -m pytest tests/test_health_commit_process_pinned.py -v
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


def test_health_commit_is_process_pinned_not_live(client, monkeypatch):
    """THE regression: a checkout advance must not move health's ``commit``.

    Simulate the 3-min pull loop moving /opt/macro under a running process by
    making the live read return a different sha: ``commit`` must stay the
    import-time value while ``checkout`` shows the new sha — drift visible.
    """
    import app.main as main

    monkeypatch.setattr(main, "_commit", lambda: "f0f0f0f")
    body = client.get("/api/health").json()
    assert body["commit"] == main._PROCESS_COMMIT, (
        "health's commit moved with the checkout — this is exactly the live "
        "2026-07-31 defect: the field claimed a build the process never imported"
    )
    assert body["checkout"] == "f0f0f0f", "the live checkout read must be surfaced"


def test_health_checkout_stays_fail_soft(client, monkeypatch):
    """A broken git read degrades to 'unknown'; the endpoint stays 200.

    The pinned ``commit`` must survive untouched — it was captured at import
    and owes nothing to request-time git.
    """
    import app.main as main

    def _boom(*a, **k):
        raise OSError("git unavailable")

    monkeypatch.setattr(main.subprocess, "check_output", _boom)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["checkout"] == "unknown"
    assert body["commit"] == main._PROCESS_COMMIT


def test_status_top_level_commit_is_process_pinned(client, monkeypatch):
    """/api/status follows the same contract; checks.site.commit stays LIVE.

    checks["site"] reports the 3-min pull loop, so the per-request read is the
    correct semantic THERE — pin both halves so a future cleanup doesn't
    'unify' them and reintroduce the lie in either direction.
    """
    import app.main as main

    monkeypatch.setattr(main, "_commit", lambda: "f0f0f0f")
    body = client.get("/api/status").json()
    assert body["commit"] == main._PROCESS_COMMIT
    assert body["checks"]["site"]["commit"] == "f0f0f0f", (
        "checks.site.commit is the pull-loop freshness read and must stay live"
    )


def test_process_commit_captured_at_import():
    """The pin exists and is a usable string even when git is absent."""
    import app.main as main

    assert isinstance(main._PROCESS_COMMIT, str) and main._PROCESS_COMMIT
