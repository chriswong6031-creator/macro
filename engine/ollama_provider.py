"""Anthropic-compatible adapter for a private Ollama endpoint.

Macro Dashboard callers standardize on ``client.messages.create`` and
``client.messages.stream``. This module preserves that surface while sending
requests to Ollama's native ``/api/chat`` endpoint. It is deliberately opt-in:
``engine.llm_auth`` constructs it only when a lane explicitly lists ``ollama``
in ``provider_order`` and ``OLLAMA_BASE_URL`` (or ``ollama_base_url``) is set.

Plain HTTP is accepted only for loopback or Tailscale addresses. This keeps a
configuration typo from sending prompts or image bytes to an arbitrary public
HTTP host. HTTPS endpoints remain available for operator-managed proxies.
"""
from __future__ import annotations

import ipaddress
import json
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib import error, parse, request


class OllamaProviderError(RuntimeError):
    """Failure returned by or while reaching the configured Ollama service."""


@dataclass
class _TextBlock:
    text: str
    type: str = "text"


@dataclass
class _ToolUseBlock:
    name: str
    input: dict[str, Any]
    id: str = field(default_factory=lambda: f"toolu_ollama_{uuid.uuid4().hex[:16]}")
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


def validate_base_url(value: str) -> str:
    """Validate and normalize an operator-provided Ollama base URL."""
    raw = str(value or "").strip().rstrip("/")
    parts = parse.urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("OLLAMA_BASE_URL must be an HTTP or HTTPS URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("OLLAMA_BASE_URL cannot contain credentials, query, or fragment")
    if parts.scheme == "http":
        host = parts.hostname.lower().rstrip(".")
        allowed = host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".ts.net")
        if not allowed:
            try:
                allowed = ipaddress.ip_address(host) in ipaddress.ip_network("100.64.0.0/10")
            except ValueError:
                allowed = False
        if not allowed:
            raise ValueError(
                "plain HTTP Ollama endpoints must use loopback or a Tailscale address"
            )
    return raw


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    fields = {}
    for name in ("type", "text", "id", "name", "input", "tool_use_id", "content"):
        if hasattr(value, name):
            fields[name] = _jsonable(getattr(value, name))
    return fields or str(value)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    plain = _jsonable(value)
    if isinstance(plain, list):
        parts = [
            str(block.get("text", ""))
            for block in plain
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if parts:
            return "\n\n".join(part for part in parts if part)
    return json.dumps(plain, ensure_ascii=False, default=str)


def _message_payload(message: Any) -> dict[str, Any]:
    role = str(_field(message, "role", "user") or "user")
    content = _field(message, "content", "")
    if isinstance(content, str):
        return {"role": role, "content": content}

    text_parts: list[str] = []
    images: list[str] = []
    for block in content or []:
        kind = str(_field(block, "type", "") or "")
        if kind == "text":
            text_parts.append(str(_field(block, "text", "") or ""))
        elif kind == "image":
            source = _field(block, "source", {}) or {}
            if str(_field(source, "type", "") or "") != "base64":
                raise OllamaProviderError(
                    "400 unsupported request feature: Ollama requires inline base64 images"
                )
            data = str(_field(source, "data", "") or "")
            if not data:
                raise OllamaProviderError("400 unsupported request feature: empty image")
            images.append(data)
        elif kind == "tool_result":
            text_parts.append(
                "TOOL RESULT "
                f"{_field(block, 'tool_use_id', '')}: "
                f"{json.dumps(_jsonable(_field(block, 'content', '')), ensure_ascii=False)}"
            )
        elif kind == "tool_use":
            text_parts.append(
                "TOOL CALL: "
                f"{json.dumps(_jsonable(block), ensure_ascii=False, separators=(',', ':'))}"
            )
        else:
            text_parts.append(json.dumps(_jsonable(block), ensure_ascii=False, default=str))
    payload: dict[str, Any] = {"role": role, "content": "\n\n".join(text_parts)}
    if images:
        payload["images"] = images
    return payload


def _tool_contract(tools: Any) -> str:
    if not tools:
        return ""
    return (
        "\n\nAVAILABLE APPLICATION TOOLS\n"
        f"{json.dumps(_jsonable(tools), ensure_ascii=False, separators=(',', ':'))}\n\n"
        "When a tool is needed, return only this JSON shape: "
        '{"text":"","tool_calls":[{"name":"exact_tool_name","input":{}}]}. '
        "Use only listed tool names and valid inputs. Otherwise answer normally."
    )


def _tool_envelope(text: str) -> dict[str, Any] | None:
    stripped = str(text or "").strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        stripped = stripped[7:-3].strip()
    try:
        parsed = json.loads(stripped)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) and isinstance(parsed.get("tool_calls"), list) else None


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
        base_url: str,
        timeout_s: float,
        num_ctx: int,
        keep_alive: str,
    ) -> None:
        self.base_url = validate_base_url(base_url)
        self.timeout_s = max(1.0, float(timeout_s))
        # A FLOOR, NOT A CAP — and inert at every window this repo configures.
        #
        # It only RAISES a nonsense request (0, a typo, a lane that resolved its
        # window from an absent config key); it never lowers a real one, so a
        # caller asking for 32768 sends 32768. Read as a ceiling it looks like a
        # 4,096-token pin, which is how it was misread once the host's
        # OLLAMA_CONTEXT_LENGTH moved off its 4,096 default on 2026-08-06.
        #
        # That host setting never reaches this line: it is the default for
        # requests that OMIT num_ctx, and every request built here carries one.
        # Measured against qwen3.5:9b on the RTX 5070 Ti — a request for 65536
        # against a server configured at 32768 loaded a 65536-token runner — so
        # the per-request option is the lever in both directions, above the
        # server's default as well as below it. `tests/test_ollama_provider.py`
        # pins both halves.
        self.num_ctx = max(4096, int(num_ctx))
        self.keep_alive = str(keep_alive or "5m")

    def create(self, **kwargs: Any) -> _Message:
        messages = []
        system = _text(kwargs.get("system", "")).strip()
        tools = kwargs.get("tools")
        if system or tools:
            messages.append({"role": "system", "content": system + _tool_contract(tools)})
        messages.extend(_message_payload(message) for message in kwargs.get("messages") or [])

        options: dict[str, Any] = {
            "temperature": float(kwargs.get("temperature", 0) or 0),
            "num_ctx": self.num_ctx,
        }
        max_tokens = kwargs.get("max_tokens")
        if max_tokens is not None:
            options["num_predict"] = max(1, int(max_tokens))
        payload = {
            "model": str(kwargs.get("model") or ""),
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": options,
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as response:  # noqa: S310
                data = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise OllamaProviderError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except (error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise OllamaProviderError(f"Ollama endpoint unavailable: {exc}") from exc

        text = str(((data.get("message") or {}).get("content")) or "").strip()
        if not text:
            raise OllamaProviderError("Ollama returned an empty response")
        usage = _Usage(
            input_tokens=int(data.get("prompt_eval_count") or 0),
            output_tokens=int(data.get("eval_count") or 0),
        )
        envelope = _tool_envelope(text) if tools else None
        if envelope is None:
            stop = "max_tokens" if data.get("done_reason") == "length" else "end_turn"
            return _Message(content=[_TextBlock(text)], usage=usage, stop_reason=stop)

        content: list[Any] = []
        if envelope.get("text"):
            content.append(_TextBlock(str(envelope["text"])))
        for call in envelope.get("tool_calls", []):
            if isinstance(call, dict) and call.get("name"):
                tool_input = call.get("input")
                content.append(_ToolUseBlock(
                    name=str(call["name"]),
                    input=tool_input if isinstance(tool_input, dict) else {},
                ))
        return _Message(content=content or [_TextBlock(text)], usage=usage, stop_reason="tool_use")

    def stream(self, **kwargs: Any) -> _Stream:
        return _Stream(self, kwargs)


class OllamaClient:
    """Small Anthropic SDK compatibility surface used by existing callers."""

    thinking_disabled_by_default = True

    def __init__(
        self,
        *,
        base_url: str,
        timeout_s: float = 120,
        num_ctx: int = 16384,
        keep_alive: str = "5m",
    ) -> None:
        self.messages = _Messages(
            base_url=base_url,
            timeout_s=timeout_s,
            num_ctx=num_ctx,
            keep_alive=keep_alive,
        )
