from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path
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


class TestChatVisionRunsOnTheCodexSubscription:
    """Operator directive 2026-07-31: chat vision must be CODEX-routed.

    This class REPLACES test_inline_image_fails_as_provider_specific_unsupported_feature,
    which pinned the old contract (any inline image → CodexUnsupportedInput → fail over
    to metered Anthropic). Codex is the attached FLAT-RATE subscription; Anthropic is
    metered per image, which is exactly why the operator wants image turns here.

    The Codex CLI has no inline-image request field. What it has is `view_image`, a
    native tool that reads a LOCAL FILE under the turn's working directory — disabled
    on every text call by `-c tools.view_image=false`. So the vision path is: decode
    each image into a throwaway sandbox dir, make that dir the cwd for THAT call,
    enable view_image for THAT call, point the prompt at ./img_<n>.<ext>, and delete
    the dir in a finally. The real CLI cannot run in tests, so every assertion here
    reads the kwargs a monkeypatched run_codex received.
    """

    # a 1x1 transparent PNG / a 1x1 JPEG-ish payload — content is irrelevant, only
    # that the exact bytes handed in are the exact bytes written to disk.
    PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
    )
    JPEG_B64 = "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAg="

    @staticmethod
    def _image(b64, media_type="image/png"):
        return {"type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64}}

    @staticmethod
    def _capturing_run(captured, *, ok=True):
        """A fake run_codex that snapshots the sandbox WHILE the call is in flight."""
        def fake_run(prompt, **kwargs):
            captured["prompt"] = prompt
            captured.update(kwargs)
            cwd = Path(kwargs.get("cwd") or ".")
            sandbox = cwd.name.startswith("codex_vision_") and cwd.is_dir()
            captured["files_at_call_time"] = sorted(p.name for p in cwd.iterdir()) if sandbox else None
            captured["bytes_at_call_time"] = {
                name: (cwd / name).read_bytes()
                for name in (captured["files_at_call_time"] or [])
            }
            if not ok:
                return {"ok": False, "final_message": "", "token_usage": None,
                        "rate_limits": None, "error_kind": "error", "raw_tail": "boom"}
            return {"ok": True, "final_message": "a candlestick chart", "token_usage": {},
                    "rate_limits": None, "error_kind": None}
        return fake_run

    def test_images_are_written_into_the_call_sandbox_with_view_image_enabled(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(cp, "run_codex", self._capturing_run(captured))

        response = cp.CodexClient().messages.create(
            model="claude-opus-5",
            system="Be precise.",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "what pattern is this?"},
                    self._image(self.PNG_B64),
                    self._image(self.JPEG_B64, "image/jpeg"),
                ],
            }],
        )

        assert response.content[0].text == "a candlestick chart"
        # the sandbox IS the cwd, so ./img_N is reachable by view_image
        assert Path(captured["cwd"]).name.startswith("codex_vision_")
        assert captured["files_at_call_time"] == ["img_1.png", "img_2.jpg"]
        assert captured["bytes_at_call_time"]["img_1.png"] == base64.b64decode(self.PNG_B64)
        assert captured["bytes_at_call_time"]["img_2.jpg"] == base64.b64decode(self.JPEG_B64)

        joined = " ".join(captured["extra_args"])
        assert "tools.view_image=true" in joined
        assert "tools.view_image=false" not in joined
        # the prompt must point at the files and permit the one tool it needs
        assert "./img_1.png" in captured["prompt"] and "./img_2.jpg" in captured["prompt"]
        assert "use the view_image tool" in captured["prompt"]
        assert "call the view_image tool on each one" in captured["prompt"]
        # and must NOT carry the payload it just wrote to disk
        assert self.PNG_B64 not in captured["prompt"]
        assert "what pattern is this?" in captured["prompt"]

    def test_the_sandbox_is_gone_after_a_successful_call(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(cp, "run_codex", self._capturing_run(captured))
        cp.CodexClient().messages.create(
            model="claude-opus-5",
            messages=[{"role": "user", "content": [self._image(self.PNG_B64)]}],
        )
        assert captured["files_at_call_time"] == ["img_1.png"]  # it existed during the call
        assert not os.path.exists(captured["cwd"]), "user image bytes must not persist on disk"

    def test_the_sandbox_is_gone_after_a_failed_call(self, monkeypatch):
        """Cleanup lives in a finally: a provider error must not leak the image either."""
        captured = {}
        monkeypatch.setattr(cp, "run_codex", self._capturing_run(captured, ok=False))
        with pytest.raises(cp.CodexProviderError):
            cp.CodexClient().messages.create(
                model="claude-opus-5",
                messages=[{"role": "user", "content": [self._image(self.PNG_B64)]}],
            )
        assert captured["files_at_call_time"] == ["img_1.png"]
        assert not os.path.exists(captured["cwd"])

    def test_a_rejected_image_leaves_nothing_behind(self, monkeypatch, tmp_path):
        """The first image is written before the second is rejected — staging cleans up."""
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        monkeypatch.setattr(cp, "run_codex", lambda *a, **k: pytest.fail("must not reach the CLI"))
        with pytest.raises(cp.CodexUnsupportedInput, match="media type"):
            cp.CodexClient().messages.create(
                model="claude-opus-5",
                messages=[{"role": "user", "content": [
                    self._image(self.PNG_B64),
                    self._image(self.PNG_B64, "image/svg+xml"),
                ]}],
            )
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.parametrize(
        ("block", "match"),
        [
            ({"type": "image", "source": {"type": "base64", "media_type": "image/svg+xml",
                                          "data": PNG_B64}}, "media type"),
            ({"type": "image", "source": {"type": "base64", "data": PNG_B64}}, "media type"),
            ({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                          "data": "not-a-real-image"}}, "not valid base64"),
            ({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                          "data": ""}}, "empty"),
            ({"type": "image", "source": {"type": "file", "file_id": "f_1"}}, "unrecognised"),
        ],
    )
    def test_junk_image_shapes_still_fail_over(self, monkeypatch, block, match):
        """CodexUnsupportedInput is retained for what the vision path cannot serve —
        it is the 400 that lets llm_auth move to the next provider."""
        monkeypatch.setattr(cp, "run_codex", lambda *a, **k: pytest.fail("must not reach the CLI"))
        with pytest.raises(cp.CodexUnsupportedInput, match=match):
            cp.CodexClient().messages.create(
                model="claude-opus-5",
                messages=[{"role": "user", "content": [block]}],
            )

    def test_an_oversized_image_fails_over_rather_than_hitting_the_disk(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        monkeypatch.setattr(cp, "run_codex", lambda *a, **k: pytest.fail("must not reach the CLI"))
        huge = base64.b64encode(b"\x00" * (cp.VISION_MAX_IMAGE_BYTES + 1)).decode()
        with pytest.raises(cp.CodexUnsupportedInput, match="larger than"):
            cp.CodexClient().messages.create(
                model="claude-opus-5",
                messages=[{"role": "user", "content": [self._image(huge)]}],
            )
        assert list(tmp_path.iterdir()) == []

    def test_an_https_image_is_never_fetched_and_the_model_is_told(self, monkeypatch):
        """No server-side fetch (that would be an SSRF primitive). The model gets the
        URL and an explicit statement that it cannot see it — so it says so."""
        captured = {}
        monkeypatch.setattr(cp, "run_codex", self._capturing_run(captured))
        cp.CodexClient().messages.create(
            model="claude-opus-5",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "read this"},
                {"type": "image", "source": {"type": "url", "url": "https://example.com/c.png"}},
            ]}],
        )
        assert "https://example.com/c.png" in captured["prompt"]
        assert "could NOT be attached" in captured["prompt"]
        assert "You cannot see it" in captured["prompt"]
        # nothing was written, so the tool stays off and the cwd is the ordinary one
        assert "tools.view_image=false" in " ".join(captured["extra_args"])
        assert not Path(captured["cwd"]).name.startswith("codex_vision_")

    def test_view_image_stays_disabled_on_a_text_only_call(self, monkeypatch):
        """Pin the flag BOTH ways: the vision path must not leak into ordinary turns."""
        captured = {}
        monkeypatch.setattr(cp, "run_codex", self._capturing_run(captured))
        cp.CodexClient(cwd="/tmp").messages.create(
            model="claude-opus-5",
            messages=[{"role": "user", "content": "just words"}],
        )
        joined = " ".join(captured["extra_args"])
        assert "tools.view_image=false" in joined
        assert "tools.view_image=true" not in joined
        assert captured["cwd"] == "/tmp"
        assert "Do not try to inspect files" in captured["prompt"]

    def test_an_image_in_an_unsupported_position_still_raises(self, monkeypatch):
        """Only top-level content blocks are staged. An image nested inside a
        tool_result is a shape this path does not handle, and serialising its base64
        into the prompt would be worse than failing over."""
        monkeypatch.setattr(cp, "run_codex", lambda *a, **k: pytest.fail("must not reach the CLI"))
        with pytest.raises(cp.CodexUnsupportedInput, match="unsupported request feature"):
            cp.CodexClient().messages.create(
                model="claude-opus-5",
                messages=[{"role": "user", "content": [{
                    "type": "tool_result", "tool_use_id": "t1",
                    "content": [self._image(self.PNG_B64)],
                }]}],
            )

    def test_a_streamed_vision_turn_takes_the_same_path(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(cp, "run_codex", self._capturing_run(captured))
        with cp.CodexClient().messages.stream(
            model="claude-opus-5",
            messages=[{"role": "user", "content": [self._image(self.PNG_B64)]}],
        ) as stream:
            assert "".join(stream.text_stream) == "a candlestick chart"
        assert "tools.view_image=true" in " ".join(captured["extra_args"])
        assert not os.path.exists(captured["cwd"])


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
