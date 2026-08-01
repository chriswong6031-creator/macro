from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine import codex_provider as cp


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        ("claude-opus-5", cp.SOL_MODEL),
        ("Fable", cp.SOL_MODEL),
        ("deepseek-v4-pro", cp.SOL_MODEL),
        ("DeepSeek V4 Pro", cp.SOL_MODEL),
        ("claude-sonnet-4-6", cp.TERRA_MODEL),
        ("deepseek-v4-flash", cp.TERRA_MODEL),
        ("DeepSeek V4 Flash", cp.TERRA_MODEL),
        ("claude-haiku-4-5", cp.LUNA_MODEL),
        (cp.SOL_MODEL, cp.SOL_MODEL),
        (cp.TERRA_MODEL, cp.TERRA_MODEL),
        (cp.LUNA_MODEL, cp.LUNA_MODEL),
        ("unknown-model", cp.TERRA_MODEL),
    ],
)
def test_translate_model(requested, expected):
    assert cp.translate_model(requested) == expected


def test_availability_requires_enable_binary_and_auth(monkeypatch):
    monkeypatch.setenv("CODEX_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "test-present")
    monkeypatch.setattr(cp, "resolve_codex_bin", lambda: "/usr/bin/true")
    assert cp.is_available() is True

    monkeypatch.setenv("CODEX_PROVIDER_ENABLED", "0")
    assert cp.is_available() is False


def test_availability_uses_vps_codex_home(monkeypatch, tmp_path):
    codex_home = tmp_path / "macro-codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text('{"auth_mode":"chatgpt"}', encoding="utf-8")

    monkeypatch.setenv("CODEX_PROVIDER_ENABLED", "1")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.setattr(cp, "resolve_codex_bin", lambda: "/usr/bin/true")

    assert cp.auth_file_path() == codex_home / "auth.json"
    assert cp.is_available() is True


def test_create_runs_locked_text_only_codex_turn(monkeypatch):
    captured = {}

    def fake_run(prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        return {
            "ok": True,
            "final_message": "provider answer",
            "token_usage": {
                "input_tokens": 120,
                "cached_input_tokens": 20,
                "output_tokens": 30,
            },
            "rate_limits": None,
            "error_kind": None,
        }

    monkeypatch.setattr(cp, "run_codex", fake_run)
    client = cp.CodexClient(timeout_s=45, cwd="/tmp")
    response = client.messages.create(
        model="claude-opus-5",
        system="Be precise.",
        messages=[{"role": "user", "content": "Question"}],
    )

    assert response.content[0].text == "provider answer"
    assert response.stop_reason == "end_turn"
    assert response.usage.input_tokens == 120
    assert response.usage.cache_read_input_tokens == 20
    assert response.usage.output_tokens == 30
    assert captured["model"] == cp.SOL_MODEL
    assert captured["sandbox"] == "read-only"
    assert captured["network"] is False
    assert captured["timeout_s"] == 45
    assert "Be precise." in captured["prompt"]
    assert "Question" in captured["prompt"]
    joined_args = " ".join(captured["extra_args"])
    assert "features.shell_tool=false" in joined_args
    assert 'web_search="disabled"' in joined_args
    assert "agents.enabled=false" in joined_args


def test_create_applies_configured_reasoning_effort(monkeypatch):
    captured = {}

    def fake_run(prompt, **kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "final_message": "high-effort answer",
            "token_usage": {},
            "rate_limits": None,
            "error_kind": None,
        }

    monkeypatch.setattr(cp, "run_codex", fake_run)
    cp.CodexClient(reasoning_effort="high").messages.create(
        model=cp.SOL_MODEL,
        messages=[{"role": "user", "content": "Question"}],
    )
    joined_args = " ".join(captured["extra_args"])
    assert 'model_reasoning_effort="high"' in joined_args


def test_tool_envelope_becomes_anthropic_tool_use(monkeypatch):
    monkeypatch.setattr(
        cp,
        "run_codex",
        lambda prompt, **kwargs: {
            "ok": True,
            "final_message": (
                '{"text":"","tool_calls":[{"name":"lookup_signal",'
                '"input":{"symbol":"SPY"}}]}'
            ),
            "token_usage": {},
            "rate_limits": None,
            "error_kind": None,
        },
    )
    response = cp.CodexClient().messages.create(
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": "Look it up"}],
        tools=[{
            "name": "lookup_signal",
            "description": "read-only lookup",
            "input_schema": {"type": "object"},
        }],
    )
    assert response.stop_reason == "tool_use"
    assert response.content[0].type == "tool_use"
    assert response.content[0].name == "lookup_signal"
    assert response.content[0].input == {"symbol": "SPY"}
    assert response.content[0].id.startswith("toolu_codex_")


def test_usage_limit_is_classified_for_shared_failover(monkeypatch):
    monkeypatch.setattr(
        cp,
        "run_codex",
        lambda prompt, **kwargs: {
            "ok": False,
            "final_message": "",
            "token_usage": None,
            "rate_limits": None,
            "error_kind": "usage_limit",
            "raw_tail": "limit reached",
        },
    )
    with pytest.raises(cp.CodexProviderError, match="429.*usage limit"):
        cp.CodexClient().messages.create(
            model="claude-haiku-4-5",
            messages=[{"role": "user", "content": "Hello"}],
        )


def test_stream_compatibility(monkeypatch):
    fake = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="streamed")],
        usage=SimpleNamespace(input_tokens=3, output_tokens=2),
        stop_reason="end_turn",
    )
    client = cp.CodexClient()
    monkeypatch.setattr(client.messages, "create", lambda **kwargs: fake)

    with client.messages.stream(
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": "Hello"}],
    ) as stream:
        assert "".join(stream.text_stream) == "streamed"
        assert stream.get_final_message() is fake


def test_inline_image_fails_as_provider_specific_unsupported_feature(monkeypatch):
    with pytest.raises(cp.CodexUnsupportedInput, match="unsupported request feature"):
        cp.CodexClient().messages.create(
            model="claude-opus-5",
            messages=[{
                "role": "user",
                "content": [{
                    "type": "image",
                    "source": {"type": "base64", "data": "not-a-real-image"},
                }],
            }],
        )


class TestACodexFailureSaysWhatWentWrong:
    """`Codex provider error (error)` is not a diagnosis, it is a shrug.

    "error" is the FALLBACK classification — engine/codex_lane/runner._classify_error
    returns it when the CLI output matched neither the usage-limit nor the auth
    phrase list. So that line means "Codex failed for a reason we did not
    recognise", and printing only the kind discarded `raw_tail`, the one field
    that says what it actually was.

    It mattered: the 2026-07-31 nightly logged that line four times per post for
    every post, fell through to DeepSeek, and ended with zero posts planned.
    Codex is the FIRST provider in the marketing order and the one the operator
    wants used, and its failures were unreadable.
    """

    def test_a_generic_failure_carries_the_cli_tail(self):
        from engine.codex_provider import CodexProviderError, _message_from_result

        try:
            _message_from_result(
                {"ok": False, "error_kind": "error",
                 "raw_tail": "stream disconnected before completion"}, None)
        except CodexProviderError as exc:
            assert "stream disconnected before completion" in str(exc)
        else:
            raise AssertionError("no error raised")

    def test_an_empty_tail_says_so_rather_than_pretending(self):
        from engine.codex_provider import CodexProviderError, _message_from_result

        try:
            _message_from_result(
                {"ok": False, "error_kind": "error", "raw_tail": ""}, None)
        except CodexProviderError as exc:
            assert "no output captured" in str(exc)
        else:
            raise AssertionError("no error raised")

    def test_the_classified_kinds_keep_their_exact_prefixes(self):
        """llm_auth classifies retry/failover on the 429 and 401 prefixes.

        Enriching the GENERIC branch must not disturb the ones a caller matches
        on, or a usage limit stops being recognised as a usage limit.
        """
        from engine.codex_provider import CodexProviderError, _message_from_result

        for kind, expected in (("usage_limit", "429 Codex usage limit reached"),
                               ("auth", "401 Codex authentication failed"),
                               ("timeout", "Codex provider timeout"),
                               ("not_installed", "Codex provider not installed")):
            try:
                _message_from_result(
                    {"ok": False, "error_kind": kind, "raw_tail": "noise"}, None)
            except CodexProviderError as exc:
                assert str(exc) == expected, (kind, str(exc))
            else:
                raise AssertionError(f"no error raised for {kind}")
