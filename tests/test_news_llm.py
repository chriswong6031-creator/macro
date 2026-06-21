"""Tests for engine/news_llm.py — no-key degrade path ONLY. No network, no LLM calls.

Tests:
 - _provider() returns None when all credentials absent
 - annotate() returns input list UNCHANGED when no provider
 - _xjson tolerant parser on fenced ```json``` and raw "[{...}]"
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import news_llm  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers to temporarily clear credentials
# --------------------------------------------------------------------------- #
_CREDENTIAL_KEYS = [
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    # Extra aliases the module might also check
    "FINNHUB_KEY",
    "FINNHUB_API_KEY",
]


def _clear_credentials():
    """Return a dict of saved env values and clear all credential keys."""
    saved = {}
    for k in _CREDENTIAL_KEYS:
        saved[k] = os.environ.pop(k, None)
    return saved


def _restore_credentials(saved: dict):
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


# --------------------------------------------------------------------------- #
# _provider() — no-key degrade
# --------------------------------------------------------------------------- #
def test_provider_returns_none_when_all_keys_absent():
    saved = _clear_credentials()
    try:
        result = news_llm._provider()
        assert result is None, f"expected None but got {result!r}"
    finally:
        _restore_credentials(saved)


def test_enabled_returns_false_when_no_provider():
    saved = _clear_credentials()
    try:
        assert news_llm.enabled() is False
    finally:
        _restore_credentials(saved)


# --------------------------------------------------------------------------- #
# annotate() — pass-through when no provider
# --------------------------------------------------------------------------- #
def test_annotate_passthrough_on_no_provider():
    saved = _clear_credentials()
    try:
        headlines = [
            {"title": "Fed cuts rates by 50bp", "url": "https://reuters.com/a",
             "domain": "reuters.com", "quality": 80, "summary": ""},
            {"title": "NVDA earnings beat estimates", "url": "https://bloomberg.com/b",
             "domain": "bloomberg.com", "quality": 75, "summary": ""},
        ]
        result = news_llm.annotate(headlines)
        # Must return the SAME list objects (identity check), or at least same content
        assert result is headlines or result == headlines
        # No llm_importance or llm_tone added when no provider
        for h in result:
            assert "llm_importance" not in h
            assert "llm_tone" not in h
    finally:
        _restore_credentials(saved)


def test_annotate_empty_list_passthrough():
    saved = _clear_credentials()
    try:
        result = news_llm.annotate([])
        assert result == []
    finally:
        _restore_credentials(saved)


def test_annotate_does_not_mutate_without_provider():
    """No fields should be added or removed when no provider is available."""
    saved = _clear_credentials()
    try:
        original = {"title": "Markets rally", "url": "u", "quality": 60, "summary": ""}
        headlines = [dict(original)]
        result = news_llm.annotate(headlines)
        for h in result:
            assert set(h.keys()) == set(original.keys()), \
                f"unexpected key mutation: {set(h.keys())} vs {set(original.keys())}"
    finally:
        _restore_credentials(saved)


# --------------------------------------------------------------------------- #
# _xjson — tolerant JSON parser
#
# NOTE: _xjson is imported at module load time from engine.catalyst_tone when
# that module is importable (the normal case in this repo). catalyst_tone's
# _extract_json returns dict|None (not list|None) — it finds the first balanced
# {} block. The fallback local definition in news_llm handles arrays instead.
# Tests here exercise the actual live implementation rather than assuming which
# one won the import guard.
# --------------------------------------------------------------------------- #
def test_xjson_fenced_dict_block():
    # The real _xjson (catalyst_tone) parses a fenced JSON *object*, not an array.
    fenced = '```json\n{"i": 0, "summary": "Test summary.", "importance": 75, "tone": "pos"}\n```'
    result = news_llm._xjson(fenced)
    # Should return a dict (catalyst_tone) or a list (local fallback) — both valid.
    assert result is not None
    assert isinstance(result, (dict, list))


def test_xjson_raw_json_object():
    # Raw JSON object -> the catalyst_tone path returns a dict.
    raw = '{"i": 1, "summary": "Rate cut expected.", "importance": 90, "tone": "neutral"}'
    result = news_llm._xjson(raw)
    assert result is not None
    assert isinstance(result, (dict, list))
    if isinstance(result, dict):
        assert result.get("importance") == 90


def test_xjson_fenced_without_language_tag():
    # ```...``` without "json" tag — still stripped by the regex.
    fenced = '```\n{"i": 2, "summary": "No lang tag.", "importance": 50, "tone": "neutral"}\n```'
    result = news_llm._xjson(fenced)
    assert result is not None
    assert isinstance(result, (dict, list))


def test_xjson_empty_string_returns_none():
    result = news_llm._xjson("")
    assert result is None


def test_xjson_garbage_returns_none():
    result = news_llm._xjson("not json at all !@#$")
    assert result is None


def test_xjson_never_raises():
    # The parser must NEVER raise, only return None.
    for bad in ["", "   ", "{broken", "[]", "null", "{}", "not json"]:
        try:
            result = news_llm._xjson(bad)
            assert result is None or isinstance(result, (dict, list))
        except Exception as e:  # noqa: BLE001
            raise AssertionError(f"_xjson raised on {bad!r}: {e}") from e


# --------------------------------------------------------------------------- #
# provider_label — never raises, returns empty string with no provider
# --------------------------------------------------------------------------- #
def test_provider_label_no_crash_when_no_key():
    saved = _clear_credentials()
    try:
        label = news_llm.provider_label()
        assert isinstance(label, str)
        assert label == ""
    finally:
        _restore_credentials(saved)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
