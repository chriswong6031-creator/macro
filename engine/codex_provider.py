"""Anthropic-compatible adapter for the attached Codex subscription.

The site already standardizes model calls on ``client.messages.create`` and
``client.messages.stream``.  This module gives the existing provider waterfall
that same interface while executing an ephemeral, non-interactive Codex CLI
turn on hosts where a Codex login is already attached.

Security boundary
-----------------
Codex is deliberately reduced here: shell, web search and sub-agents are
disabled; the sandbox is read-only; user configuration and repository rules are
ignored; and the working directory is the system temp directory.  The credential
is never read by Python and never logged.

The ONE tool that can be enabled is ``view_image``, and only on a call that
carries image blocks (operator directive 2026-07-31 — chat vision runs on the
attached Codex subscription rather than metered Anthropic).  Such a call gets a
throwaway temp directory as its cwd, holding just the decoded attachments, and
that directory is deleted when the call returns.  Image URLs are never fetched
server-side; the model is told it cannot see them.

The provider auto-discovers either a trusted-automation environment credential
(``CODEX_ACCESS_TOKEN`` / ``CODEX_API_KEY``) or the attached login under
``CODEX_HOME`` (default ``~/.codex``).  Hosts without Codex and an attached
login simply omit this provider from the waterfall.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.codex_lane.runner import resolve_codex_bin, run_codex

CODEX_CAPABILITY_ID = "codex_account"
CODEX_ENV_ID = "CODEX_ACCOUNT_ATTACHED"

SOL_MODEL = "gpt-5.6-sol"
TERRA_MODEL = "gpt-5.6-terra"
LUNA_MODEL = "gpt-5.6-luna"

_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}

# Vision (operator directive 2026-07-31): chat vision is served by the attached
# Codex SUBSCRIPTION, not by metered Anthropic. The CLI has no inline-image
# request field — its `view_image` tool reads a LOCAL FILE under the turn's
# working directory — so an image block is staged to disk inside a throwaway
# sandbox that IS the cwd for that one call, and deleted in a finally.
# media type → the extension the staged file gets.
VISION_MEDIA_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}
# Decoded-byte ceiling per image. The gateway already caps attachments at ~3.5MB;
# this is the provider's own floor-level guard so a caller that skips that check
# cannot push an arbitrary blob onto this host's disk.
VISION_MAX_IMAGE_BYTES = 3_500_000


def provider_enabled() -> bool:
    """Return the operator enable switch (default: auto/on)."""
    return os.environ.get("CODEX_PROVIDER_ENABLED", "auto").strip().lower() not in _FALSE_VALUES


def auth_file_path() -> Path:
    """Return the active Codex credential-cache path without opening it."""
    configured_home = os.environ.get("CODEX_HOME", "").strip()
    codex_home = Path(configured_home).expanduser() if configured_home else Path("~/.codex").expanduser()
    return codex_home / "auth.json"


def is_available() -> bool:
    """Return whether this host can safely execute the attached Codex account.

    This is a presence check only.  It never opens the credential file or reads
    an environment credential value.
    """
    if not provider_enabled():
        return False

    binary = resolve_codex_bin()
    binary_present = bool(
        (binary != "codex" and Path(binary).is_file())
        or shutil.which(binary)
    )
    if not binary_present:
        return False

    env_auth_present = any(
        bool(os.environ.get(name))
        for name in ("CODEX_ACCESS_TOKEN", "CODEX_API_KEY")
    )
    file_auth_present = auth_file_path().is_file()

    # An explicit enable still requires a real credential source; it must not
    # turn a missing login into a provider that fails every request.
    return env_auth_present or file_auth_present


def translate_model(requested_model: str | None) -> str:
    """Translate Claude/DeepSeek tier names to the requested Codex agent tier.

    Operator mapping:
      Opus / Fable / DeepSeek V4 Pro   -> Sol
      Sonnet / DeepSeek V4 Flash       -> Terra
      Haiku                            -> Luna

    Unknown model names use Terra, the all-rounder tier.
    """
    raw = str(requested_model or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")

    if raw in {SOL_MODEL, TERRA_MODEL, LUNA_MODEL}:
        return raw
    if "opus" in normalized or "fable" in normalized:
        return SOL_MODEL
    if "deepseek" in normalized and (
        "v4-pro" in normalized or normalized.endswith("-pro")
    ):
        return SOL_MODEL
    if "sonnet" in normalized:
        return TERRA_MODEL
    if "deepseek" in normalized and (
        "v4-flash" in normalized or normalized.endswith("-flash")
    ):
        return TERRA_MODEL
    if "haiku" in normalized:
        return LUNA_MODEL
    return TERRA_MODEL


class CodexProviderError(RuntimeError):
    """Base provider failure whose message is classified by llm_auth."""


class CodexUnsupportedInput(CodexProviderError):
    """A provider-specific unsupported request feature (safe to fail over)."""

    status_code = 400


@dataclass
class _TextBlock:
    text: str
    type: str = "text"


@dataclass
class _ToolUseBlock:
    name: str
    input: dict[str, Any]
    id: str = field(default_factory=lambda: f"toolu_codex_{uuid.uuid4().hex[:16]}")
    type: str = "tool_use"


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class _Message:
    content: list[Any]
    usage: _Usage
    stop_reason: str = "end_turn"


def _plain(value: Any) -> Any:
    """Convert Anthropic block objects and nested request data to JSON values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key == "source" and isinstance(item, dict) and item.get("type") == "base64":
                # Backstop only. Top-level image blocks are staged to disk by
                # _stage_image_inputs BEFORE the prompt is built, so anything
                # still carrying a base64 source here sits in a position the
                # vision path does not handle (e.g. nested inside a tool_result).
                # Serialising the payload into the prompt would be worse than
                # failing over, so this stays a hard unsupported-input error.
                raise CodexUnsupportedInput(
                    "400 unsupported request feature: inline image input in this "
                    "position is not supported by the Codex CLI provider"
                )
            out[str(key)] = _plain(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]

    attrs: dict[str, Any] = {}
    for name in ("type", "text", "id", "name", "input", "tool_use_id", "content"):
        if hasattr(value, name):
            attrs[name] = _plain(getattr(value, name))
    return attrs or str(value)


def _text(value: Any) -> str:
    """Flatten an Anthropic system parameter to readable text."""
    plain = _plain(value)
    if isinstance(plain, str):
        return plain
    if isinstance(plain, list):
        text_parts = [
            str(item.get("text", ""))
            for item in plain
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if text_parts:
            return "\n\n".join(part for part in text_parts if part)
    return json.dumps(plain, ensure_ascii=False, default=str)


def _tool_contract(tools: Any) -> str:
    if not tools:
        return ""
    schemas = _plain(tools)
    return (
        "\n\nAVAILABLE APPLICATION TOOLS\n"
        f"{json.dumps(schemas, ensure_ascii=False, separators=(',', ':'), default=str)}\n\n"
        "If an application tool is needed, reply with ONLY this JSON shape:\n"
        '{"text":"","tool_calls":[{"name":"exact_tool_name","input":{}}]}\n'
        "Use only listed tool names and valid inputs. The application will execute "
        "the calls and return tool_result messages. If no tool is needed, answer "
        "normally and do not emit that JSON shape."
    )


# ---------------------------------------------------------------------------
# Vision: stage image blocks as files the CLI's view_image tool can open
# ---------------------------------------------------------------------------

def _attr(obj: Any, name: str) -> Any:
    """Read a field from either a plain dict block or an SDK block object."""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _source_fields(source: Any) -> dict[str, Any]:
    """Normalise an image ``source`` (dict or SDK object) to a plain dict."""
    if isinstance(source, dict):
        return source
    if source is None:
        return {}
    return {
        name: getattr(source, name)
        for name in ("type", "media_type", "data", "url")
        if hasattr(source, name)
    }


def _is_image_block(block: Any) -> bool:
    return str(_attr(block, "type") or "") == "image"


def _has_image_input(messages: Any) -> bool:
    """True when any top-level message content list carries an image block."""
    for message in messages or []:
        content = _attr(message, "content")
        if isinstance(content, (list, tuple)) and any(_is_image_block(b) for b in content):
            return True
    return False


def _stage_image_block(block: Any, index: int, tmpdir: str) -> tuple[dict[str, str], bool]:
    """One Anthropic image block → (text block for the prompt, wrote_a_file).

    base64 sources are decoded and written to ``<tmpdir>/img_<index>.<ext>``; the
    replacement text points the model at that path and tells it to call
    ``view_image``.  https sources are NOT fetched — doing so server-side would
    hand a caller an SSRF primitive — so the model is told the image exists but
    could not be attached, and must say it cannot see it.

    Raises CodexUnsupportedInput for shapes this path cannot serve, so the
    waterfall fails over to a natively multimodal provider instead of answering
    a picture it never received.
    """
    source = _source_fields(_attr(block, "source"))
    source_type = str(source.get("type") or "")

    if source_type == "base64":
        media_type = str(source.get("media_type") or "").strip().lower()
        extension = VISION_MEDIA_TYPES.get(media_type)
        if not extension:
            raise CodexUnsupportedInput(
                "400 unsupported request feature: image media type "
                f"{media_type or '(missing)'} is not supported by the Codex vision path"
            )
        try:
            raw = base64.b64decode(str(source.get("data") or ""), validate=True)
        except Exception as exc:  # noqa: BLE001
            raise CodexUnsupportedInput(
                "400 unsupported request feature: image payload is not valid base64"
            ) from exc
        if not raw:
            raise CodexUnsupportedInput(
                "400 unsupported request feature: image payload is empty"
            )
        if len(raw) > VISION_MAX_IMAGE_BYTES:
            raise CodexUnsupportedInput(
                "400 unsupported request feature: image is larger than the "
                f"{VISION_MAX_IMAGE_BYTES}-byte Codex vision limit"
            )
        name = f"img_{index}.{extension}"
        Path(tmpdir, name).write_bytes(raw)
        return (
            {"type": "text", "text": (
                f"Image {index} is saved at ./{name} — use the view_image tool to "
                "look at it before answering."
            )},
            True,
        )

    if source_type == "url":
        url = str(source.get("url") or "").strip()
        return (
            {"type": "text", "text": (
                f"Image {index} was supplied as the URL {url or '(missing)'} and could "
                "NOT be attached to this turn — it was not downloaded and there is no "
                "local copy. You cannot see it: say so plainly instead of guessing at "
                "its contents."
            )},
            False,
        )

    raise CodexUnsupportedInput(
        "400 unsupported request feature: unrecognised image source "
        f"{source_type or '(missing)'} for the Codex vision path"
    )


def _stage_image_inputs(messages: Any) -> tuple[Any, str | None]:
    """Rewrite image blocks into text and return ``(messages, sandbox_dir|None)``.

    ``sandbox_dir`` is a fresh temp directory holding the decoded image files; it
    is the working directory for that one CLI call so ``view_image`` can reach
    them, and the CALLER must delete it in a ``finally``.  None means no file was
    written (text-only turn, or url-only attachments) and view_image stays off.

    Cleans up its own directory if staging raises part-way, so a rejected second
    image never leaves the first one's bytes on disk.
    """
    if not _has_image_input(messages):
        return messages, None

    tmpdir = tempfile.mkdtemp(prefix="codex_vision_")
    try:
        rewritten: list[Any] = []
        index = 0
        wrote_any = False
        for message in messages or []:
            content = _attr(message, "content")
            if not isinstance(content, (list, tuple)) or not any(
                _is_image_block(b) for b in content
            ):
                rewritten.append(message)
                continue
            blocks: list[Any] = []
            for block in content:
                if not _is_image_block(block):
                    blocks.append(block)
                    continue
                index += 1
                text_block, wrote = _stage_image_block(block, index, tmpdir)
                wrote_any = wrote_any or wrote
                blocks.append(text_block)
            rewritten.append({"role": _attr(message, "role"), "content": blocks})
    except BaseException:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise

    if not wrote_any:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return rewritten, None
    return rewritten, tmpdir


def _build_prompt(system: Any, messages: Any, tools: Any, *, vision: bool = False) -> str:
    """Build one isolated chat turn for ``codex exec``.

    ``vision`` swaps the "no built-in tools" preamble for one that permits the
    single tool the turn needs (view_image) — telling the model every tool is
    disabled and then asking it to open a file is a contradiction it resolves by
    not looking.
    """
    plain_messages = _plain(messages or [])
    if vision:
        preamble = (
            "You are serving as a text-generation provider inside an application. "
            "Follow the application system instruction and conversation. This turn "
            "carries image attachments, saved as files in your working directory: "
            "call the view_image tool on each one and read it before you answer. "
            "Do not run commands, browse, or use any other built-in tool; every "
            "other capability is disabled for this turn."
        )
    else:
        preamble = (
            "You are serving as a text-generation provider inside an application. "
            "Follow the application system instruction and conversation. Do not try "
            "to inspect files, run commands, browse, or use any built-in tools; those "
            "capabilities are disabled for this turn."
        )
    return (
        f"{preamble}\n\n"
        f"APPLICATION SYSTEM INSTRUCTION\n{_text(system)}\n\n"
        "CONVERSATION (JSON)\n"
        f"{json.dumps(plain_messages, ensure_ascii=False, separators=(',', ':'), default=str)}"
        f"{_tool_contract(tools)}"
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Parse a tool envelope from a bare or fenced JSON final answer."""
    stripped = str(text or "").strip()
    candidates = [stripped]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("tool_calls"), list):
            return parsed
    return None


def _record_rate_limits(rate_limits: Any, status_code: int) -> None:
    """Project Codex quota telemetry into the shared admin header ledger."""
    if not isinstance(rate_limits, dict):
        return
    headers: dict[str, str] = {}
    for horizon in ("primary", "secondary"):
        value = rate_limits.get(horizon)
        if not isinstance(value, dict):
            continue
        if value.get("used_percent") is not None:
            headers[f"codex-ratelimit-{horizon}-used-percent"] = str(value["used_percent"])
        if value.get("resets_at"):
            headers[f"codex-ratelimit-{horizon}-resets-at"] = str(value["resets_at"])
    if not headers:
        return
    try:
        from engine.neuralweb.key_pool import record_usage_headers

        record_usage_headers(CODEX_CAPABILITY_ID, headers, status_code)
    except Exception:
        pass


def _message_from_result(result: dict[str, Any], tools: Any) -> _Message:
    rate_limits = result.get("rate_limits")
    if not result.get("ok"):
        _record_rate_limits(rate_limits, 429 if result.get("error_kind") == "usage_limit" else 500)
        kind = str(result.get("error_kind") or "error")
        if kind == "usage_limit":
            raise CodexProviderError("429 Codex usage limit reached")
        if kind == "auth":
            raise CodexProviderError("401 Codex authentication failed")
        if kind == "timeout":
            raise CodexProviderError("Codex provider timeout")
        if kind == "not_installed":
            raise CodexProviderError("Codex provider not installed")
        # CARRY THE TAIL (2026-07-31). "error" is the FALLBACK classification —
        # _classify_error returns it when the CLI's output matched neither the
        # usage-limit nor the auth phrase lists. So `Codex provider error (error)`
        # means "Codex failed for a reason we did not recognise", and printing
        # only the kind discards the one field that says what it was.
        #
        # The nightly logged that line four times per post, for every post, on
        # 2026-07-31; the lane then fell through to DeepSeek and the night ended
        # with zero posts. Codex is the FIRST provider in the marketing order and
        # the one the operator wants used, and its failures were unreadable.
        # `raw_tail` is already on the result and already truncated by the runner.
        tail = str(result.get("raw_tail") or "").strip().replace("\n", " ")
        if tail:
            raise CodexProviderError(f"Codex provider error ({kind}): {tail[:400]}")
        raise CodexProviderError(
            f"Codex provider error ({kind}) — no output captured; the CLI wrote "
            f"nothing this run")

    _record_rate_limits(rate_limits, 200)
    final = str(result.get("final_message") or "").strip()
    if not final:
        raise CodexProviderError("Codex provider returned an empty response")

    token_usage = result.get("token_usage") or {}
    usage = _Usage(
        input_tokens=int(token_usage.get("input_tokens", 0) or 0),
        output_tokens=int(token_usage.get("output_tokens", 0) or 0),
        cache_read_input_tokens=int(token_usage.get("cached_input_tokens", 0) or 0),
    )

    envelope = _extract_json_object(final) if tools else None
    if envelope is None:
        return _Message(content=[_TextBlock(final)], usage=usage)

    content: list[Any] = []
    if envelope.get("text"):
        content.append(_TextBlock(str(envelope["text"])))
    for call in envelope.get("tool_calls", []):
        if not isinstance(call, dict) or not call.get("name"):
            continue
        tool_input = call.get("input")
        content.append(_ToolUseBlock(
            name=str(call["name"]),
            input=tool_input if isinstance(tool_input, dict) else {},
        ))
    if not content:
        content.append(_TextBlock(final))
    stop_reason = "tool_use" if any(
        getattr(block, "type", "") == "tool_use" for block in content
    ) else "end_turn"
    return _Message(content=content, usage=usage, stop_reason=stop_reason)


class _Stream:
    def __init__(self, messages_api: "_Messages", kwargs: dict[str, Any]) -> None:
        self._messages_api = messages_api
        self._kwargs = kwargs
        self._message: _Message | None = None

    def __enter__(self) -> "_Stream":
        self._message = self._messages_api.create(**self._kwargs)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    @property
    def text_stream(self):
        if self._message is None:
            self._message = self._messages_api.create(**self._kwargs)
        for block in self._message.content:
            if getattr(block, "type", "") == "text":
                yield block.text

    def get_final_message(self) -> _Message:
        if self._message is None:
            self._message = self._messages_api.create(**self._kwargs)
        return self._message


class _Messages:
    def __init__(
        self,
        *,
        timeout_s: int,
        cwd: str | None,
        reasoning_effort: str | None,
    ) -> None:
        self.timeout_s = timeout_s
        self.cwd = cwd
        effort = str(reasoning_effort or "").strip().lower()
        self.reasoning_effort = effort if effort in {
            "none", "minimal", "low", "medium", "high", "xhigh", "max",
        } else ""

    def create(self, **kwargs: Any) -> _Message:
        requested_model = str(kwargs.get("model") or "")
        model = translate_model(requested_model)
        # Vision turns stage their images to disk first; the sandbox directory
        # becomes this call's cwd so view_image can open ./img_<n>.<ext>, and it
        # is deleted in the finally below whatever the outcome — user image bytes
        # must not outlive the request. Staging raises before the dir exists (or
        # cleans up itself) for shapes the vision path cannot serve.
        messages, vision_dir = _stage_image_inputs(kwargs.get("messages") or [])
        try:
            prompt = _build_prompt(
                kwargs.get("system", ""),
                messages,
                kwargs.get("tools"),
                vision=vision_dir is not None,
            )
            extra_args = [
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "-c", 'approval_policy="never"',
                "-c", 'web_search="disabled"',
                "-c", "agents.enabled=false",
                "-c", "features.shell_tool=false",
                "-c", f"tools.view_image={'true' if vision_dir else 'false'}",
            ]
            if self.reasoning_effort:
                extra_args.extend([
                    "-c",
                    f'model_reasoning_effort="{self.reasoning_effort}"',
                ])
            result = run_codex(
                prompt,
                cwd=vision_dir or self.cwd or tempfile.gettempdir(),
                timeout_s=self.timeout_s,
                model=model,
                sandbox="read-only",
                network=False,
                extra_args=extra_args,
            )
            return _message_from_result(result, kwargs.get("tools"))
        finally:
            if vision_dir:
                shutil.rmtree(vision_dir, ignore_errors=True)

    def stream(self, **kwargs: Any) -> _Stream:
        return _Stream(self, kwargs)


class CodexClient:
    """Small Anthropic SDK compatibility surface used by existing callers."""

    def __init__(
        self,
        *,
        timeout_s: int = 180,
        cwd: str | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self.messages = _Messages(
            timeout_s=max(1, int(timeout_s)),
            cwd=cwd,
            reasoning_effort=reasoning_effort,
        )
