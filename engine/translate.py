"""Machine translation of sourced English free-text → 简体中文 (gated, degrade-never-raise).

The dashboards are bilingual by DUAL-EMITTING both languages in the DOM (see
engine/i18n.py) — but that only works for strings WE compose. A few fields are
sourced English prose (the single-stock analyzer's company blurb, from
Wikipedia/SEC) that cannot be hand-translated at the source. This module is the
escape hatch: an OPTIONAL, provider-agnostic LLM translator used by a CACHED batch
job (scripts/translate_profiles.py), never on the hot path.

Design contract (mirrors engine/commodity_news.py's gated LLM helper):
  * GATED — returns "no translations" unless `enabled` AND the configured key is set.
  * DEGRADE-NEVER-RAISE — any error/parse-failure yields None for the affected items;
    the caller then keeps the English text. Translation never breaks a build.
  * PROVIDER-AGNOSTIC — uses the `anthropic` SDK's wire format; `base_url` points it at
    DeepSeek's Anthropic-compatible endpoint (the documented cheap/中文-native choice)
    or, when null, at native Anthropic. `api_key_env` names the key.
  * BATCHED + VALIDATED — N short blurbs per call via a strict JSON-array contract; a
    count mismatch fails the whole batch closed (all None), never silently misaligns.
"""
from __future__ import annotations

import json
import logging

from lib import config

log = logging.getLogger("translate")

_SYSTEM = (
    "You are a professional financial translator. Translate each English company "
    "description into concise, natural Simplified Chinese (简体中文). Preserve company "
    "names, ticker symbols, and place names; translate the rest faithfully. Do not add, "
    "omit, or comment. Return ONLY a JSON array of strings — exactly one translation per "
    "input item, in the same order, and nothing else."
)


def is_enabled(cfg: dict | None = None) -> bool:
    """True only when the feature is on AND a key is actually present — so callers can
    short-circuit (and tests can assert the no-op path) without constructing a client."""
    cfg = cfg if cfg is not None else config.load().get("profile_translation", {})
    if not cfg.get("enabled"):
        return False
    return bool(config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY")))


def _extract_json_array(text: str) -> list | None:
    """Tolerant parse: strip code fences / prose and pull the first JSON array. Returns a
    list, or None if nothing array-shaped is found / it isn't a list of scalars."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    i, j = s.find("["), s.rfind("]")
    if i == -1 or j == -1 or j < i:
        return None
    try:
        out = json.loads(s[i:j + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return out if isinstance(out, list) else None


def _client(cfg: dict):
    """Build an Anthropic-SDK client pointed at the configured endpoint, or None when the
    SDK is missing or no key is set. Never raises."""
    key = config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY"))
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK not installed — translation skipped")
        return None
    base_url = cfg.get("base_url")
    try:
        return anthropic.Anthropic(api_key=key, base_url=base_url) if base_url \
            else anthropic.Anthropic(api_key=key)
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("translation client init failed (%s)", e)
        return None


def _translate_one_batch(client, texts: list[str], cfg: dict) -> list[str | None]:
    """One API call for a batch; returns a same-length list (None per item on any failure).
    The JSON-array contract is validated by COUNT — a mismatch fails the batch closed."""
    none = [None] * len(texts)
    max_chars = int(cfg.get("max_chars", 600))
    payload = [t[:max_chars] for t in texts]
    user = ("Translate each item of this JSON array to Simplified Chinese and return a "
            "JSON array of the same length and order:\n" + json.dumps(payload, ensure_ascii=False))
    try:
        resp = client.messages.create(
            model=cfg.get("model", "deepseek-chat"),
            max_tokens=int(cfg.get("max_tokens", 4000)),
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        if getattr(resp, "stop_reason", None) in ("refusal", "max_tokens"):
            log.warning("translation batch stopped (%s) — keeping English", resp.stop_reason)
            return none
        text = "".join(getattr(b, "text", "") for b in resp.content
                       if getattr(b, "type", "") == "text")
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("translation batch failed (%s) — keeping English", e)
        return none
    arr = _extract_json_array(text)
    if arr is None or len(arr) != len(texts):
        log.warning("translation batch malformed (got %s for %d items) — keeping English",
                    None if arr is None else len(arr), len(texts))
        return none
    # only accept non-empty strings that actually contain CJK; else keep English
    out: list[str | None] = []
    for v in arr:
        s = str(v).strip() if v is not None else ""
        out.append(s if (s and any("一" <= ch <= "鿿" for ch in s)) else None)
    return out


def translate_to_zh(texts: list[str], cfg: dict | None = None) -> list[str | None]:
    """Translate a list of English strings to 简体中文, batched. Returns a list aligned to
    `texts`; each element is the translation or None (caller keeps the English original).
    A no-op (all None) when disabled / unkeyed / SDK-missing. Never raises."""
    cfg = cfg if cfg is not None else config.load().get("profile_translation", {})
    if not texts:
        return []
    if not cfg.get("enabled"):
        return [None] * len(texts)
    client = _client(cfg)
    if client is None:
        return [None] * len(texts)
    batch = max(1, int(cfg.get("batch_size", 20)))
    out: list[str | None] = []
    for i in range(0, len(texts), batch):
        out.extend(_translate_one_batch(client, texts[i:i + batch], cfg))
    return out
