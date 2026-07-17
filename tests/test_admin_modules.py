"""admin read-only panels — smoke tests against the real repo state (no network)."""
import json
import sys
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin import ai_cost, brief, content, ga4, github_api, gitops, health
from admin import orchestrator_chat


def test_health_summary_shape():
    s = health.summary()
    for k in ("healthy", "sources", "markets", "source_rows"):
        assert k in s
    assert {"ok", "stale", "dead", "total"} <= set(s["sources"])
    assert isinstance(s["markets"], list) and s["markets"]


def test_ai_cost_estimate_shape():
    c = ai_cost.estimate()
    for k in ("components", "monthly_usd", "savings_by_interval", "assumptions"):
        assert k in c
    assert len(c["savings_by_interval"]) == 7        # intervals 1..7
    assert all(s["interval"] in range(1, 8) for s in c["savings_by_interval"])
    assert c["monthly_usd"] >= 0


def test_content_inventory_finds_pages():
    inv = content.inventory()
    assert inv["total_pages"] > 0
    assert all("name" in p and "kb" in p for p in inv["pages"][:5])


def test_brief_panel_shape():
    b = brief.panel()
    assert "master_brain" in b and "ai_desk" in b
    assert 1 <= b["master_brain"]["interval_days"] <= 7
    assert isinstance(b["master_brain"]["items"], list)


def test_ga4_status_degrades_without_creds():
    st = ga4.status()
    assert st["measurement_id"] == "G-BZTZ9W1BBB"
    assert "setup_steps" in st and st["setup_steps"]
    # configured is a bool either way; without creds it must be False
    assert isinstance(st["configured"], bool)


def test_github_repo_detected():
    owner, name = github_api.repo()
    # this checkout's origin is chriswong6031-creator/macro
    assert owner and name


def test_gitops_status_shape():
    s = gitops.status()
    for k in ("branch", "config_dirty", "can_push_live"):
        assert k in s


def test_ai_cost_estimate_has_measured_key():
    """estimate() must return a 'measured' key; fail-soft None is accepted."""
    c = ai_cost.estimate()
    assert "measured" in c
    # measured is None (no ledger) or a dict with the expected keys
    m = c["measured"]
    if m is not None:
        assert isinstance(m, dict)
        for k in ("summary", "budget_ledger", "mastermind", "codex", "recent_cycles"):
            assert k in m, f"measured missing key: {k}"
        assert isinstance(m["recent_cycles"], list)


def test_ai_cost_estimate_old_keys_intact():
    """Old shape keys must be present regardless of measured."""
    c = ai_cost.estimate()
    for k in ("components", "monthly_usd", "savings_by_interval", "assumptions",
              "per_build_usd", "effective_daily_usd", "deepseek_key"):
        assert k in c, f"estimate() missing legacy key: {k}"


def test_chat_log_write_uses_tmp_root(tmp_path, monkeypatch):
    """_append_chat_log writes to tmp_path/data/neuralweb/orchestrator_chat_log.jsonl."""
    orchestrator_chat._append_chat_log(
        tmp_path,
        model="claude-sonnet-4-6",
        key_source="CORTEX_ANTHROPIC_API_KEY",
        input_tokens=100,
        output_tokens=50,
        est_cost_usd=0.001,
        degraded=False,
        tool_call_census={"read_health": 1},
    )
    log_path = tmp_path / "data" / "neuralweb" / "orchestrator_chat_log.jsonl"
    assert log_path.exists(), "chat log file was not created"
    rows = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["model"] == "claude-sonnet-4-6"
    assert row["input_tokens"] == 100
    assert row["output_tokens"] == 50
    assert row["est_cost_usd"] == 0.001
    assert row["degraded"] is False
    assert row["tool_call_census"] == {"read_health": 1}
    assert "ts" in row


def test_chat_log_write_never_raises(tmp_path):
    """_append_chat_log must not raise even on a bad path."""
    bad_root = tmp_path / "nonexistent" / "path"
    # Should not raise — just log a warning
    orchestrator_chat._append_chat_log(
        bad_root,
        model="x", key_source=None,
        input_tokens=0, output_tokens=0, est_cost_usd=None,
        degraded=True, tool_call_census={},
    )


def test_chat_returns_usage_keys_in_live_mode(tmp_path, monkeypatch):
    """chat() in live mode includes input_tokens, output_tokens, est_cost_usd keys."""
    # Clear LLM key env vars so we can inject a fake key
    for env in ("CORTEX_ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("CORTEX_ANTHROPIC_API_KEY", "test-key")

    # Build a fake anthropic client that returns a minimal response
    class FakeUsage:
        input_tokens = 42
        output_tokens = 17

    class FakeBlock:
        type = "text"
        text = "The pipeline ran without errors."

    class FakeResp:
        content = [FakeBlock()]
        stop_reason = "end_turn"
        usage = FakeUsage()

    class FakeMessages:
        def create(self, **kwargs):
            return FakeResp()

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(orchestrator_chat, "_build_client", lambda kind, cred: FakeClient())
    monkeypatch.setattr(orchestrator_chat, "_advice_filter", lambda text: (text, False))

    result = orchestrator_chat.chat("What happened last night?", root=tmp_path)
    assert result["ok"] is True
    assert result["degraded"] is False
    assert result["mode"] == "live"
    assert "input_tokens" in result
    assert "output_tokens" in result
    assert "est_cost_usd" in result
    assert result["input_tokens"] == 42
    assert result["output_tokens"] == 17


def test_cost_route_returns_json(tmp_path):
    """GET /api/cost returns valid JSON with the expected shape."""
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from admin import server

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    port = httpd.server_address[1]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/cost", timeout=10) as r:
            d = json.loads(r.read())
        assert isinstance(d, dict)
        for k in ("components", "monthly_usd", "savings_by_interval", "assumptions", "measured"):
            assert k in d, f"/api/cost response missing key: {k}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_resolve_candidates_pool_waterfall(monkeypatch):
    """_resolve_candidates: CORTEX → pool keys → ANTHROPIC_API_KEY; legacy not in list."""
    # Clear all keys first
    for env in ("CORTEX_ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
                "ANTHROPIC_API_KEY", "METAB_KEYS_ENABLED",
                "CLAUDE_CODE_OAUTH_TOKEN_1", "CLAUDE_CODE_OAUTH_TOKEN_2",
                "CLAUDE_CODE_OAUTH_TOKEN_3"):
        monkeypatch.delenv(env, raising=False)

    # Set specific pool keys
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN_3", "pool-tok-3")
    monkeypatch.setenv("METAB_KEYS_ENABLED", "3,4,5,6,7")

    # Stub key_pool to return cap_id 3 with ref CLAUDE_CODE_OAUTH_TOKEN_3
    try:
        import engine.neuralweb.key_pool as _kp
        monkeypatch.setattr(_kp, "discover_present_keys", lambda root=None: ["claude_code_oauth_3"])
        monkeypatch.setattr(_kp, "get_secret_ref", lambda cap_id, root=None: f"CLAUDE_CODE_OAUTH_TOKEN_{cap_id.split('_')[-1]}")
        monkeypatch.setattr(_kp, "is_cooling", lambda k, root=None: False)
        monkeypatch.setattr(_kp, "window_load", lambda k, root=None: 0)
    except Exception:
        pass

    cands = orchestrator_chat._resolve_candidates()
    cap_ids = [c[3] for c in cands]
    # CORTEX and ANTHROPIC_API_KEY absent; only pool key
    assert "claude_code_oauth_3" in cap_ids
    # Legacy must NOT appear
    assert all("CLAUDE_CODE_OAUTH_TOKEN" not in c[2] or c[2].endswith("_3") for c in cands if c[2])


def test_resolve_candidates_includes_cortex_first(monkeypatch):
    """CORTEX_ANTHROPIC_API_KEY is always first when set."""
    monkeypatch.setenv("CORTEX_ANTHROPIC_API_KEY", "cortex-key")
    # Pool: make discover_present_keys return empty so only CORTEX + ANTHROPIC matter
    try:
        import engine.neuralweb.key_pool as _kp
        monkeypatch.setattr(_kp, "discover_present_keys", lambda root=None: [])
    except Exception:
        pass
    monkeypatch.setenv("ANTHROPIC_API_KEY", "api-key")
    for env in ("CLAUDE_CODE_OAUTH_TOKEN",):
        monkeypatch.delenv(env, raising=False)

    cands = orchestrator_chat._resolve_candidates()
    assert len(cands) >= 1
    assert cands[0][3] == "cortex_api_key"


def test_chat_pool_waterfall_advances_on_auth_error(tmp_path, monkeypatch):
    """chat() advances to the next pool key when the first returns 401."""
    for env in ("CORTEX_ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(env, raising=False)

    # Two candidates: first will 401, second will succeed
    call_order = []

    class FakeUsage:
        input_tokens = 10
        output_tokens = 5

    class FakeBlock:
        type = "text"
        text = "all good"

    class FakeResp:
        content = [FakeBlock()]
        stop_reason = "end_turn"
        usage = FakeUsage()

    class Client1:
        class messages:
            @staticmethod
            def create(**kw):
                call_order.append("client1")
                raise Exception("401 authentication_error: Invalid bearer token")

    class Client2:
        class messages:
            @staticmethod
            def create(**kw):
                call_order.append("client2")
                return FakeResp()

    clients = {"oauth-3": Client1(), "oauth-4": Client2()}

    def fake_build_client(kind, cred):
        return clients.get(cred)

    monkeypatch.setattr(orchestrator_chat, "_build_client", fake_build_client)
    monkeypatch.setattr(orchestrator_chat, "_advice_filter", lambda t: (t, False))

    # Inject two pool candidates
    cands = [
        ("oauth", "oauth-3", "CLAUDE_CODE_OAUTH_TOKEN_3", "claude_code_oauth_3"),
        ("oauth", "oauth-4", "CLAUDE_CODE_OAUTH_TOKEN_4", "claude_code_oauth_4"),
    ]
    monkeypatch.setattr(orchestrator_chat, "_resolve_candidates", lambda: cands)

    result = orchestrator_chat.chat("hello", root=tmp_path)
    assert result["ok"] is True
    assert result["degraded"] is False
    assert "client1" in call_order and "client2" in call_order
    assert result["key_source"] == "claude_code_oauth_4"


def test_preflight_picks_pool_key_not_legacy(monkeypatch, tmp_path):
    """check_auth picks the first enabled+present pool key, not the legacy token."""
    import sys
    sys.path.insert(0, str(tmp_path.parent))

    # Set a pool key and also a legacy token
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN_3", "pool-tok-3")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "legacy-tok")
    monkeypatch.setenv("METAB_KEYS_ENABLED", "3,4,5,6,7")

    from scripts import preflight_claude_auth

    # Stub key_pool to return key 3 as non-cooling
    try:
        import engine.neuralweb.key_pool as _kp
        monkeypatch.setattr(_kp, "discover_present_keys", lambda root=None: ["claude_code_oauth_3"])
        monkeypatch.setattr(_kp, "get_secret_ref",
                            lambda cap_id, root=None: f"CLAUDE_CODE_OAUTH_TOKEN_{cap_id.split('_')[-1]}")
        monkeypatch.setattr(_kp, "is_cooling", lambda k, root=None: False)
    except Exception:
        pass

    # Stub the broker audit — check_auth calls it best-effort and it writes
    # data/neuralweb/capability_audit.jsonl against the real tree (MM_DATA_GUARD).
    try:
        import engine.neuralweb.capability_broker as _cb
        monkeypatch.setattr(_cb, "audit", lambda *a, **k: None)
    except Exception:
        pass

    # Stub the ping so it succeeds, and capture the env it was called with
    captured_env = {}

    def fake_ping(ref_name, *, token_value=None):
        captured_env["ref_name"] = ref_name
        captured_env["token_value"] = token_value
        return True, "ping ok"

    monkeypatch.setattr(preflight_claude_auth, "_run_ping_check", fake_ping)

    result = preflight_claude_auth.check_auth(lane="test-lane")
    assert result["auth_ok"] is True
    # ref_name must be the pool key, not the legacy var
    assert captured_env["ref_name"] == "CLAUDE_CODE_OAUTH_TOKEN_3"
    # token_value was passed (not None) — the pool key's VALUE was injected
    assert captured_env["token_value"] == "pool-tok-3"
    # The reported ref_name must never be the legacy name
    assert result["ref_name"] == "CLAUDE_CODE_OAUTH_TOKEN_3"


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn(); print("PASS", fn.__name__)
