from __future__ import annotations

import base64
import json

import pytest


class _Response:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


def test_plain_http_is_limited_to_loopback_or_tailscale():
    from engine.ollama_provider import validate_base_url

    assert validate_base_url("http://127.0.0.1:11434/") == "http://127.0.0.1:11434"
    assert validate_base_url("http://100.80.236.59:11434") == "http://100.80.236.59:11434"
    assert validate_base_url("http://winpc.example.ts.net:11434")
    assert validate_base_url("https://ollama.example.com")
    with pytest.raises(ValueError, match="loopback or a Tailscale"):
        validate_base_url("http://ollama.example.com:11434")
    with pytest.raises(ValueError, match="credentials"):
        validate_base_url("http://user:pass@100.80.236.59:11434")


def test_create_translates_anthropic_text_and_image(monkeypatch):
    from engine import ollama_provider as op

    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data)
        return _Response({
            "message": {"role": "assistant", "content": "visible person"},
            "done_reason": "stop",
            "prompt_eval_count": 23,
            "eval_count": 4,
        })

    monkeypatch.setattr(op.request, "urlopen", fake_urlopen)
    client = op.OllamaClient(
        base_url="http://100.80.236.59:11434",
        timeout_s=45,
        num_ctx=8192,
    )
    image = base64.b64encode(b"jpeg-bytes").decode()
    response = client.messages.create(
        model="qwen3.5:9b",
        max_tokens=100,
        system="Return concise text.",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "What is visible?"},
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg", "data": image,
                }},
            ],
        }],
    )

    assert captured["url"] == "http://100.80.236.59:11434/api/chat"
    assert captured["timeout"] == 45
    payload = captured["payload"]
    assert payload["think"] is False
    assert payload["stream"] is False
    assert payload["options"] == {
        "temperature": 0.0,
        "num_ctx": 8192,
        "num_predict": 100,
    }
    assert payload["messages"][1]["images"] == [image]
    assert response.content[0].text == "visible person"
    assert response.usage.input_tokens == 23
    assert response.usage.output_tokens == 4


def test_stream_compatibility_returns_final_message(monkeypatch):
    from engine import ollama_provider as op

    monkeypatch.setattr(
        op.request,
        "urlopen",
        lambda req, timeout: _Response({
            "message": {"content": "one buffered chunk"},
            "done_reason": "stop",
        }),
    )
    client = op.OllamaClient(base_url="http://127.0.0.1:11434")
    with client.messages.stream(model="qwen3.5:9b", messages=[]) as stream:
        assert list(stream.text_stream) == ["one buffered chunk"]
        assert stream.get_final_message().stop_reason == "end_turn"


def test_llm_auth_builds_ollama_only_when_explicit(monkeypatch):
    from engine import llm_auth

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://100.80.236.59:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:9b")
    providers = llm_auth.build_providers({
        "provider_order": ["ollama"],
        "codex_provider": False,
    })
    assert len(providers) == 1
    assert providers[0]["name"] == "ollama"
    assert providers[0]["model"] == "qwen3.5:9b"

    monkeypatch.delenv("OLLAMA_BASE_URL")
    assert llm_auth.build_providers({
        "provider_order": ["ollama"],
        "codex_provider": False,
    }) == []


# ── ai_costs attribution ──────────────────────────────────────────────────────
# Regression pins for 2026-08-07: llm_auth._capture_usage mapped provider names
# with an if/elif chain whose `else` charged every unmapped rung to
# ("claude_oauth", "subscription").  `ollama` was unmapped, so free calls to a
# private endpoint — the two Ollama-backed lanes are config/marketing.yml
# `cold_read` and `breaking.llm` — were recorded as Claude-subscription spend
# and inflated the very lane routing to a local model exists to relieve.
#
# No network: op.request.urlopen is monkeypatched, exactly as above.


def _ollama_reply(payload: dict | None = None):
    """A fake urlopen returning one well-formed Ollama /api/chat response."""
    def fake_urlopen(req, timeout):
        return _Response(payload or {
            "message": {"role": "assistant", "content": "no"},
            "done_reason": "stop",
            "prompt_eval_count": 428,
            "eval_count": 1,
        })
    return fake_urlopen


def _call_fn(client, model):
    """make_call's callable: returns the 3-tuple that carries .usage."""
    resp = client.messages.create(
        model=model, max_tokens=64, messages=[{"role": "user", "content": "hi"}],
    )
    return resp.content[0].text, None, resp


def _ledger_rows(root):
    from lib.ai_costs import read_usage

    return read_usage(root=root)


def test_ollama_call_is_not_recorded_as_claude_subscription(monkeypatch, tmp_path):
    """A call SERVED BY the ollama rung records provider 'ollama', never the
    Claude subscription lane."""
    from engine import llm_auth
    from engine import ollama_provider as op

    monkeypatch.setattr(op.request, "urlopen", _ollama_reply())
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    # Keep the ledger out of the repo tree (MM_DATA_GUARD).
    monkeypatch.setenv("AI_COSTS_STATE_ROOT", str(tmp_path))
    monkeypatch.delenv("AI_COSTS_SHARD", raising=False)

    providers = llm_auth.build_providers({
        "provider_order": ["ollama"],
        "codex_provider": False,
        "ollama_model": "qwen3.5:9b",
        "usage_lane": "marketing-cold-read",
        "usage_stage": "marketing_cold_read",
    })
    text, reason, served = llm_auth.make_call(
        providers, _call_fn, context="marketing_cold_read")
    assert (text, reason, served) == ("no", None, "ollama")

    rows = _ledger_rows(tmp_path)
    assert len(rows) == 1, rows
    row = rows[0]
    # The defect, pinned from both sides.
    assert row["provider"] == "ollama"
    assert row["cost_basis"] != "subscription"
    assert row["cost_basis"] == "local"
    # And the rest of the row still describes the call it came from.
    assert row["model"] == "qwen3.5:9b"
    assert row["lane"] == "marketing-cold-read"
    assert row["input_tokens"] == 428
    assert row["output_tokens"] == 1
    # A private endpoint on our own hardware costs $0 — stated, not left null.
    assert row["est_cost_usd"] == 0.0
    # No credential is involved, so no key may be claimed.
    assert row["key_id"] is None


def test_ledger_names_the_rung_that_served_not_the_first_configured(
    monkeypatch, tmp_path,
):
    """breaking.llm puts ollama LAST (`[codex, oauth, anthropic, deepseek,
    ollama]`).  When the earlier rungs fail, the row must name ollama."""
    from engine import llm_auth
    from engine import ollama_provider as op

    monkeypatch.setattr(op.request, "urlopen", _ollama_reply())
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("AI_COSTS_STATE_ROOT", str(tmp_path))
    monkeypatch.delenv("AI_COSTS_SHARD", raising=False)

    built = llm_auth.build_providers({
        "provider_order": ["ollama"],
        "codex_provider": False,
        "usage_lane": "marketing-breaking-summary",
    })
    assert len(built) == 1

    class _DeadClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise ConnectionError("endpoint down")

    dead = {"name": "anthropic", "env_var": "ANTHROPIC_API_KEY", "cred": "sk-x",
            "client": _DeadClient(), "model": "claude-opus-5",
            "usage_lane": "marketing-breaking-summary"}

    _text, _reason, served = llm_auth.make_call(
        [dead, *built], _call_fn, context="breaking_summary")
    assert served == "ollama"

    rows = _ledger_rows(tmp_path)
    # Exactly one row: the failed rung is not spend.
    assert [r["provider"] for r in rows] == ["ollama"]
    assert rows[0]["cost_basis"] == "local"
    assert rows[0]["lane"] == "marketing-breaking-summary"


def test_unmapped_rung_records_itself_rather_than_the_oauth_lane():
    """The root cause was a lying DEFAULT, not just a missing ollama row: an
    unknown provider name must never resolve to claude_oauth/subscription."""
    from engine.llm_auth import ledger_provider_for

    assert ledger_provider_for("ollama") == ("ollama", "local")
    assert ledger_provider_for("oauth") == ("claude_oauth", "subscription")
    assert ledger_provider_for("anthropic") == ("claude_api", "metered")
    assert ledger_provider_for("deepseek") == ("deepseek", "metered")
    assert ledger_provider_for("codex") == ("codex", "subscription")

    for unknown in ("vllm", "", None, "unknown"):
        provider, basis = ledger_provider_for(unknown)
        assert provider != "claude_oauth", unknown
        assert basis != "subscription", unknown


def test_local_rows_are_neither_subscription_nor_metered_spend(tmp_path):
    """summarize() must not fold free local calls into either money bucket."""
    from lib.ai_costs import record_usage, summarize

    record_usage(lane="marketing-cold-read", provider="ollama",
                 model="qwen3.5:9b", input_tokens=428, output_tokens=1,
                 cost_basis="local", est_cost_usd=0.0, root=tmp_path)
    record_usage(lane="brain-pro", provider="claude_oauth",
                 model="claude-opus-5", input_tokens=100, output_tokens=10,
                 cost_basis="subscription", root=tmp_path)

    buckets = summarize(root=tmp_path)["by_cost_basis"]
    assert buckets["local"]["calls"] == 1
    assert buckets["subscription"]["calls"] == 1
    assert "metered" not in buckets
    # The free rung contributes no USD to either money bucket.
    assert buckets["local"]["usd"] == 0.0


def test_ask_brain_shares_the_llm_auth_provider_table():
    """ask_brain used to hand-copy the map and drifted (no ollama row); it now
    resolves through llm_auth so the two writers cannot disagree."""
    from engine.neuralweb import ask_brain

    assert not hasattr(ask_brain, "_ASK_PROVIDER_MAP")
    assert "ledger_provider_for" in ask_brain._record_ask_usage.__code__.co_names
