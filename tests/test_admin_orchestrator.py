"""Tests for the W-AI admin surface — Master Brain (orchestrator) page.

Covers:
  - orchestrator_panel() shape on an EMPTY root (no artifacts → degrades, never raises)
  - orchestrator_panel() against fixture artifacts (run log / reviews / dialogue / cortex)
  - lobes_panel() gains orchestrator_hero WITHOUT breaking the groups contract
  - POST /api/orchestrator/settings server-side validation bounds (no config writes)
  - orchestrator chat keyless degraded mode (deterministic run-log composition)
  - wake() gh-CLI plumbing (mocked — the workflow is NEVER dispatched from tests)
  - mastermind proxy whitelist + unreachable-bot 502 contract
  - mastermind proxy bearer: MASTERMIND_BOT_TOKEN attached on GET+POST, omitted when unset
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

from admin import mastermind_proxy, neural_web, orchestrator_chat, server


# ---------------------------------------------------------------------------
# Fixture repo
# ---------------------------------------------------------------------------

@pytest.fixture()
def orch_repo(tmp_path):
    """A fake repo root with orchestrator run log, reviews, dialogue + cortex artifacts."""
    nw = tmp_path / "data" / "neuralweb"
    (nw / "cortex").mkdir(parents=True)
    gov = tmp_path / "data" / "governance"
    gov.mkdir(parents=True)

    entries = [
        {"run_date": "2026-07-11", "produced_at": "2026-07-11T02:30:00Z", "workflow": "daily",
         "overall_status": "ok", "lobes_total": 40, "lobes_stale": 2, "what_changed_n": 3,
         "what_changed_kinds": {"refresh": 3}, "contradictions_n": 0, "gaps_n": 0,
         "operator_attention_n": 1, "cortex_status": "ok", "cortex_tool_calls": 4,
         "feedback_state": "present", "nudges_n": 1, "nudge_codes": ["stale_feed"],
         "directives_n": 1, "summary": "daily run for 2026-07-11: 40 lobes (2 stale)"},
        {"run_date": "2026-07-12", "produced_at": "2026-07-12T02:30:00Z", "workflow": "daily",
         "overall_status": "warn", "lobes_total": 41, "lobes_stale": 3, "what_changed_n": 2,
         "what_changed_kinds": {"refresh": 1, "flip": 1}, "contradictions_n": 1, "gaps_n": 0,
         "operator_attention_n": 2, "cortex_status": "degraded", "cortex_tool_calls": 0,
         "feedback_state": "present", "nudges_n": 1, "nudge_codes": ["stale_feed"],
         "directives_n": 1, "summary": "daily run for 2026-07-12: 41 lobes (3 stale)"},
    ]
    (nw / "orchestrator_runlog.jsonl").write_text(
        "\n".join(json.dumps(e) for e in entries), encoding="utf-8")

    review = {"produced_at": "2026-07-12T02:31:00Z", "window_runs": 2,
              "from_run": "2026-07-11", "to_run": "2026-07-12",
              "completed": {"runs": 2, "what_changed_total": 5,
                            "what_changed_kinds": {"refresh": 4, "flip": 1},
                            "directives_seen": 2},
              "assessment": ["stale lobes up (2 -> 3) over 2 runs"]}
    (nw / "orchestrator_reviews.jsonl").write_text(json.dumps(review), encoding="utf-8")

    feedback = {"schema": "neuralweb.mastermind_feedback_summary.v1",
                "state": "present", "generated_utc": "2026-07-12T02:00:00Z",
                "nudges": [{"code": "stale_feed", "kind": "data", "severity": "warn",
                            "detail": "ETF lobe stale 3 builds", "first_seen": "2026-07-10",
                            "builds_seen": 3}],
                "operator_directives": [{"id": "dir-1", "created": "2026-07-11",
                                         "text": "check the ETF feed"}],
                "ack": {"nudge_codes_seen": ["stale_feed"], "directive_ids_seen": ["dir-1"]}}
    (gov / "mastermind_feedback_summary.json").write_text(json.dumps(feedback), encoding="utf-8")

    (nw / "cortex" / "probation.json").write_text(json.dumps(
        {"granted": False, "tier": "A0/A1 shadow", "reason": "insufficient-n"}), encoding="utf-8")
    (nw / "health.json").write_text(json.dumps(
        {"schema": "neuralweb.health.v1", "overall_status": "warn",
         "summary_counts": {"stale": 3},
         "cortex": {"run_status": {"status": "degraded",
                                   "degradation_reason": "model_unavailable"}},
         "lobes": []}), encoding="utf-8")
    (nw / "daily_brief.json").write_text(json.dumps(
        {"schema": "neuralweb.daily_brief.v1", "as_of": "2026-07-12", "status": "warn",
         "operator_attention": [{"priority": 1, "summary": "ETF feed stale 3 days"}]}),
        encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# orchestrator_panel — empty root degrades, never raises
# ---------------------------------------------------------------------------

def test_orchestrator_panel_empty_root(tmp_path):
    d = neural_web.orchestrator_panel(tmp_path)
    assert d["ok"] is True
    for key in ("status_hero", "entries", "reviews", "settings", "dialogue", "cortex"):
        assert key in d, f"missing key: {key}"
    assert d["entries"] == []
    assert d["reviews"] == []
    hero = d["status_hero"]
    assert hero["id"] == "orchestrator"
    assert hero["overall_status"] == "unknown"
    assert hero["nudges_n"] == 0 and hero["directives_n"] == 0
    assert "daily.yml" in hero["next_run_note"]
    # settings degrade to defaults (all four keys present)
    s = d["settings"]
    assert s["review_every_n_runs"] == 5
    assert s["site_rows"] == 60
    assert s["ingest_bot_feedback"] is True
    assert s["brief_attention_nudges"] is True
    # dialogue + cortex fail open
    assert d["dialogue"]["feedback_state"] == "absent"
    assert d["dialogue"]["nudges"] == []
    assert d["cortex"]["status"] == "unknown"
    assert d["cortex"]["probation"].get("missing") is True


def test_orchestrator_panel_fixture(orch_repo):
    d = neural_web.orchestrator_panel(orch_repo)
    assert d["ok"] is True
    # entries newest-first for display
    assert [e["run_date"] for e in d["entries"]] == ["2026-07-12", "2026-07-11"]
    hero = d["status_hero"]
    assert hero["run_date"] == "2026-07-12"
    assert hero["overall_status"] == "warn"
    assert hero["lobes_total"] == 41 and hero["lobes_stale"] == 3
    assert hero["nudges_n"] == 1 and hero["directives_n"] == 1
    assert hero["feedback_state"] == "present"
    assert hero["last_review_at"] == "2026-07-12T02:31:00Z"
    # dialogue block passthrough
    dia = d["dialogue"]
    assert dia["nudges"][0]["code"] == "stale_feed"
    assert dia["operator_directives"][0]["id"] == "dir-1"
    assert dia["ack"]["nudge_codes_seen"] == ["stale_feed"]
    # cortex from probation.json + health.json
    assert d["cortex"]["status"] == "degraded"
    assert d["cortex"]["probation"]["tier"] == "A0/A1 shadow"
    # reviews newest-first
    assert d["reviews"][0]["from_run"] == "2026-07-11"


def test_orchestrator_panel_reads_config_settings(orch_repo):
    (orch_repo / "config.yml").write_text(
        "orchestrator:\n"
        "  review_every_n_runs: 7   # comment survives\n"
        "  site_rows: 90\n"
        "  ingest_bot_feedback: false\n"
        "  brief_attention_nudges: false\n", encoding="utf-8")
    s = neural_web.orchestrator_panel(orch_repo)["settings"]
    assert s["review_every_n_runs"] == 7
    assert s["site_rows"] == 90
    assert s["ingest_bot_feedback"] is False
    assert s["brief_attention_nudges"] is False


def test_orchestrator_panel_out_of_range_config_falls_back(orch_repo):
    (orch_repo / "config.yml").write_text(
        "orchestrator:\n  review_every_n_runs: 999\n  site_rows: 1\n", encoding="utf-8")
    s = neural_web.orchestrator_panel(orch_repo)["settings"]
    assert s["review_every_n_runs"] == 5    # 999 out of [2, 50] → default
    assert s["site_rows"] == 60             # 1 out of [10, 365] → default


# ---------------------------------------------------------------------------
# lobes_panel — orchestrator_hero is additive
# ---------------------------------------------------------------------------

def test_lobes_panel_has_orchestrator_hero_and_groups_intact():
    d = neural_web.lobes_panel()
    if not d.get("ok"):
        pytest.skip("synapse.yml unreadable in this environment")
    hero = d.get("orchestrator_hero")
    assert isinstance(hero, dict)
    assert hero["id"] == "orchestrator"
    for key in ("summary", "overall_status", "nudges_n", "directives_n", "last_review_at"):
        assert key in hero, f"orchestrator_hero missing {key}"
    # existing groups contract unchanged
    lobes_in_groups = {ls["id"] for g in d["groups"] for ls in g["lobes"]}
    assert lobes_in_groups == {ls["id"] for ls in d["lobes"]}


# ---------------------------------------------------------------------------
# settings validation — unit + live-server bounds (never writes config.yml)
# ---------------------------------------------------------------------------

def test_validate_orchestrator_setting_unit():
    ok, err, val = server.validate_orchestrator_setting("review_every_n_runs", 5)
    assert ok and val == 5
    ok, _, val = server.validate_orchestrator_setting("review_every_n_runs", 50.0)
    assert ok and val == 50 and isinstance(val, int)   # float-int coerced
    for bad in (1, 51, "5", None, True, 5.5):
        ok, err, _ = server.validate_orchestrator_setting("review_every_n_runs", bad)
        assert not ok, f"review_every_n_runs={bad!r} must be rejected"
        assert err
    for bad in (9, 366):
        ok, _, _ = server.validate_orchestrator_setting("site_rows", bad)
        assert not ok
    ok, _, _ = server.validate_orchestrator_setting("site_rows", 10)
    assert ok
    ok, _, val = server.validate_orchestrator_setting("ingest_bot_feedback", False)
    assert ok and val is False
    for bad in (1, "true", None):
        ok, _, _ = server.validate_orchestrator_setting("brief_attention_nudges", bad)
        assert not ok, f"bool setting must reject {bad!r}"
    ok, err, _ = server.validate_orchestrator_setting("nope", 5)
    assert not ok and "unknown" in err


def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


def _post(port, path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return urllib.request.urlopen(req, timeout=10)


def test_settings_post_rejects_out_of_bounds_and_unknown_keys():
    """Out-of-range / wrong-typed values → 400 before any config.yml write."""
    httpd, port = _server()
    try:
        for body in ({"key": "review_every_n_runs", "value": 1},
                     {"key": "review_every_n_runs", "value": 51},
                     {"key": "site_rows", "value": 9},
                     {"key": "site_rows", "value": 400},
                     {"key": "ingest_bot_feedback", "value": "yes"},
                     {"key": "not_a_setting", "value": 5},
                     {"value": 5}):
            try:
                _post(port, "/api/orchestrator/settings", body)
                raise AssertionError(f"expected 400 for {body}")
            except urllib.error.HTTPError as e:
                assert e.code == 400, f"{body} → {e.code}"
                assert json.loads(e.read())["ok"] is False
    finally:
        httpd.shutdown(); httpd.server_close()


def test_get_orchestrator_route_live():
    httpd, port = _server()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/orchestrator", timeout=10) as r:
            d = json.loads(r.read())
        assert d["ok"] is True
        for key in ("status_hero", "entries", "reviews", "settings", "dialogue", "cortex"):
            assert key in d
    finally:
        httpd.shutdown(); httpd.server_close()


# ---------------------------------------------------------------------------
# chat — keyless degraded mode (deterministic; no network, no SDK needed)
# ---------------------------------------------------------------------------

def _clear_llm_keys(monkeypatch):
    for env in ("CORTEX_ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(env, raising=False)


def test_chat_degraded_no_key(orch_repo, monkeypatch):
    _clear_llm_keys(monkeypatch)
    r = orchestrator_chat.chat("What did you do last night?", root=orch_repo)
    assert r["ok"] is True
    assert r["degraded"] is True
    assert r["mode"] == "degraded"
    assert r["reply"].startswith("(degraded — no LLM key; composed from the run log)")
    # composed from the latest run-log entry + review + attention + dialogue
    assert "2026-07-12" in r["reply"]
    assert "stale lobes up" in r["reply"]
    assert "ETF feed stale 3 days" in r["reply"]
    assert "1 nudge(s), 1 directive(s)" in r["reply"]


def test_chat_degraded_empty_repo_no_key(tmp_path, monkeypatch):
    _clear_llm_keys(monkeypatch)
    r = orchestrator_chat.chat("hello", root=tmp_path)
    assert r["ok"] is True and r["degraded"] is True
    assert "No run-log entries yet" in r["reply"]


def test_chat_rejects_empty_and_oversized(monkeypatch, tmp_path):
    _clear_llm_keys(monkeypatch)
    assert orchestrator_chat.chat("", root=tmp_path)["ok"] is False
    assert orchestrator_chat.chat("x" * 2001, root=tmp_path)["ok"] is False


def test_chat_history_sanitation():
    turns = orchestrator_chat._sanitize_history([
        {"role": "assistant", "content": "dropped — leading assistant"},
        {"role": "user", "content": "a"},
        {"role": "user", "content": "b"},          # merged into previous user turn
        {"role": "assistant", "content": "c"},
        {"role": "bogus", "content": "dropped"},
        "not-a-dict",
    ])
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[0]["content"] == "a\n\nb"


# ---------------------------------------------------------------------------
# wake — NEVER dispatches from tests (gh mocked in both directions)
# ---------------------------------------------------------------------------

def test_wake_without_gh(monkeypatch):
    monkeypatch.setattr(orchestrator_chat.shutil, "which", lambda _cmd: None)
    r = orchestrator_chat.wake()
    assert r["ok"] is False
    assert "gh workflow run daily.yml" in r["hint"]


def test_wake_with_mocked_gh(monkeypatch):
    calls = {}

    class _P:
        returncode = 0
        stdout = "✓ Created workflow_dispatch event"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        assert kwargs.get("timeout") == 30
        return _P()

    monkeypatch.setattr(orchestrator_chat.shutil, "which", lambda _cmd: "/usr/local/bin/gh")
    monkeypatch.setattr(orchestrator_chat.subprocess, "run", fake_run)
    r = orchestrator_chat.wake()
    assert r["ok"] is True
    assert calls["cmd"][:3] == ["gh", "workflow", "run"]
    assert "daily.yml" in calls["cmd"]


# ---------------------------------------------------------------------------
# mastermind proxy — whitelist + unreachable contract
# ---------------------------------------------------------------------------

def test_proxy_rejects_unknown_paths():
    payload, code = mastermind_proxy.forward_get("/api/mastermind_ai/../secrets")
    assert code == 404
    payload, code = mastermind_proxy.forward_post("/api/mastermind_ai/nuke", {})
    assert code == 404


def test_proxy_unreachable_bot_returns_502(monkeypatch):
    monkeypatch.setenv("MASTERMIND_BOT_BASE", "http://127.0.0.1:9")   # discard port — nothing listens
    payload, code = mastermind_proxy.forward_get("/api/mastermind_ai")
    assert code == 502
    assert payload["error"] == "bot unreachable"
    assert "detail" in payload


# ---------------------------------------------------------------------------
# mastermind proxy — bearer auth (transport mocked; NEVER hits a real server)
# ---------------------------------------------------------------------------

class _FakeBotResp:
    """Minimal stand-in for urllib's HTTPResponse context manager."""
    status = 200

    def read(self):
        return b'{"ok": true}'

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _mock_transport(monkeypatch, seen):
    def fake_urlopen(req, timeout=None):
        seen["auth"] = req.get_header("Authorization")
        seen["method"] = req.get_method()
        seen["url"] = req.full_url
        return _FakeBotResp()

    monkeypatch.setattr(mastermind_proxy.urllib.request, "urlopen", fake_urlopen)


def test_proxy_attaches_bearer_when_token_set(monkeypatch):
    seen = {}
    _mock_transport(monkeypatch, seen)
    monkeypatch.setenv("MASTERMIND_BOT_BASE", "http://127.0.0.1:9")
    monkeypatch.setenv("MASTERMIND_BOT_TOKEN", "test-bearer-token")

    payload, code = mastermind_proxy.forward_get("/api/mastermind_ai/loop_log", "n=30")
    assert code == 200 and payload == {"ok": True}
    assert seen["method"] == "GET"
    assert seen["auth"] == "Bearer test-bearer-token"

    payload, code = mastermind_proxy.forward_post("/api/mastermind_ai/directive", {"text": "x"})
    assert code == 200 and payload == {"ok": True}
    assert seen["method"] == "POST"
    assert seen["auth"] == "Bearer test-bearer-token"


def test_proxy_omits_bearer_when_token_unset(monkeypatch):
    seen = {}
    _mock_transport(monkeypatch, seen)
    monkeypatch.setenv("MASTERMIND_BOT_BASE", "http://127.0.0.1:9")
    monkeypatch.delenv("MASTERMIND_BOT_TOKEN", raising=False)

    _payload, code = mastermind_proxy.forward_get("/api/mastermind_ai")
    assert code == 200 and seen["auth"] is None

    _payload, code = mastermind_proxy.forward_post("/api/mastermind_ai/run", {})
    assert code == 200 and seen["auth"] is None
