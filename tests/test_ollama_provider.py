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
