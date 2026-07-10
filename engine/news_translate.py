"""Cached build-time translation for sourced news headlines.

Static pages cannot call a translation API in the browser without exposing a key.
This helper is therefore build-time only: translate the small filtered headline
set, cache by text hash, and degrade to the original English when disabled,
unkeyed, rate-limited, or malformed.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

SYSTEM_ZH = (
    "You are a professional financial-news translator. Translate each English "
    "headline or short summary into concise, natural Simplified Chinese. Preserve "
    "ticker symbols, company names when commonly used in English, numbers, and "
    "market terms such as ETF names. Do not add analysis. Return ONLY a JSON array "
    "of strings, exactly one output per input, in the same order."
)

SYSTEM_EN = (
    "You are a professional financial-news translator. Translate each Simplified "
    "Chinese headline or short summary into concise, natural English. Use the "
    "common English names for Chinese companies, institutions and policy terms "
    "(PBOC, CSRC, RRR, A-shares); preserve ticker symbols and numbers. Do not add "
    "analysis. Return ONLY a JSON array of strings, exactly one output per input, "
    "in the same order."
)


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff") / len(text)


def _looks_english(text: str) -> bool:
    """A plausible English translation: nonempty, mostly non-CJK (proper nouns may
    keep a few CJK glyphs), and carries at least some latin letters."""
    s = (text or "").strip()
    return bool(s) and _cjk_ratio(s) <= 0.3 and any(c.isascii() and c.isalpha() for c in s)


def _cfg() -> dict:
    cfg = config.load().get("news_translation", {}) or {}
    if not cfg:
        cfg = {
            "enabled": False,
            "api_key_env": "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com/anthropic",
            "model": "deepseek-chat",
            "cache_dir": "data/news_translation/cache",
        }
    return cfg


def _cache_dir(cfg: dict) -> Path:
    cdir = config.ROOT / cfg.get("cache_dir", "data/news_translation/cache")
    cdir.mkdir(parents=True, exist_ok=True)
    return cdir


def _key(text: str, target: str = "zh") -> str:
    return hashlib.sha1(f"{target}\0{text}".encode("utf-8")).hexdigest()


def _read_cache(texts: list[str], cfg: dict) -> tuple[list[str | None], list[int]]:
    cdir = _cache_dir(cfg)
    out: list[str | None] = []
    missing: list[int] = []
    for i, text in enumerate(texts):
        if not text or _has_cjk(text):
            out.append(text if text else None)
            continue
        path = cdir / f"{_key(text)}.json"
        try:
            if path.exists():
                val = json.loads(path.read_text()).get("text_zh")
                out.append(val if val and _has_cjk(val) else None)
                if out[-1]:
                    continue
        except Exception:  # noqa: BLE001
            pass
        out.append(None)
        missing.append(i)
    return out, missing


def _write_cache(pairs: list[tuple[str, str | None]], cfg: dict) -> None:
    cdir = _cache_dir(cfg)
    for src, zh in pairs:
        if not src or not zh or not _has_cjk(zh):
            continue
        try:
            (cdir / f"{_key(src)}.json").write_text(json.dumps(
                {"text": src, "text_zh": zh}, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass


def _client(cfg: dict):
    key = config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY"))
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK not installed; news translation skipped")
        return None
    try:
        base = cfg.get("base_url")
        return anthropic.Anthropic(api_key=key, base_url=base) if base else anthropic.Anthropic(api_key=key)
    except Exception as e:  # noqa: BLE001
        log.warning("news translation client init failed: %s", e)
        return None


def _extract_array(text: str) -> list | None:
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        parts = s.split("```")
        s = parts[1] if len(parts) > 1 else s.strip("`")
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    i, j = s.find("["), s.rfind("]")
    if i < 0 or j < i:
        return None
    try:
        arr = json.loads(s[i:j + 1])
    except Exception:  # noqa: BLE001
        return None
    return arr if isinstance(arr, list) else None


def _translate_batch(client, texts: list[str], cfg: dict) -> list[str | None]:
    none = [None] * len(texts)
    max_chars = int(cfg.get("max_chars", 360))
    payload = [t[:max_chars] for t in texts]
    user = "Translate this JSON array to Simplified Chinese:\n" + json.dumps(payload, ensure_ascii=False)
    try:
        resp = client.messages.create(
            model=cfg.get("model", "deepseek-chat"),
            max_tokens=int(cfg.get("max_tokens", 3000)),
            system=SYSTEM_ZH,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
    except Exception as e:  # noqa: BLE001
        log.warning("news translation batch failed: %s", e)
        return none
    arr = _extract_array(text)
    if arr is None or len(arr) != len(texts):
        log.warning("news translation malformed: got %s for %d inputs",
                    None if arr is None else len(arr), len(texts))
        return none
    out: list[str | None] = []
    for val in arr:
        s = str(val).strip() if val is not None else ""
        out.append(s if _has_cjk(s) else None)
    return out


def translate_to_zh(texts: list[str], cfg: dict | None = None) -> list[str | None]:
    """Translate English news strings to Simplified Chinese, cache-aligned.

    Native Chinese strings pass through. English strings return a cached/API
    translation or None, so callers can fall back to the original text.
    """
    cfg = cfg if cfg is not None else _cfg()
    if not texts:
        return []
    cached, missing = _read_cache(texts, cfg)
    if not missing or not cfg.get("enabled"):
        return cached
    client = _client(cfg)
    if client is None:
        return cached
    batch_size = max(1, int(cfg.get("batch_size", 16)))
    for start in range(0, len(missing), batch_size):
        idxs = missing[start:start + batch_size]
        src = [texts[i] for i in idxs]
        zh = _translate_batch(client, src, cfg)
        _write_cache(list(zip(src, zh)), cfg)
        for i, val in zip(idxs, zh, strict=False):
            if val:
                cached[i] = val
    return cached


# --------------------------------------------------------------------------- #
# ZH -> EN direction (the china_news page's EN language toggle). Mirrors the
# EN -> ZH path: same cache dir (keys carry target="en"), same client, same
# batch protocol — only the system prompt, cache field and output validator
# differ (a plausible English string instead of a CJK one).
# --------------------------------------------------------------------------- #
def _read_cache_en(texts: list[str], cfg: dict) -> tuple[list[str | None], list[int]]:
    cdir = _cache_dir(cfg)
    out: list[str | None] = []
    missing: list[int] = []
    for i, text in enumerate(texts):
        if not text or not _has_cjk(text):
            out.append(text if text else None)     # already English -> passthrough
            continue
        path = cdir / f"{_key(text, 'en')}.json"
        try:
            if path.exists():
                val = json.loads(path.read_text()).get("text_en")
                out.append(val if val and _looks_english(val) else None)
                if out[-1]:
                    continue
        except Exception:  # noqa: BLE001
            pass
        out.append(None)
        missing.append(i)
    return out, missing


def _write_cache_en(pairs: list[tuple[str, str | None]], cfg: dict) -> None:
    cdir = _cache_dir(cfg)
    for src, en in pairs:
        if not src or not en or not _looks_english(en):
            continue
        try:
            (cdir / f"{_key(src, 'en')}.json").write_text(json.dumps(
                {"text": src, "text_en": en}, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass


def _translate_batch_en(client, texts: list[str], cfg: dict) -> list[str | None]:
    none = [None] * len(texts)
    max_chars = int(cfg.get("max_chars", 360))
    payload = [t[:max_chars] for t in texts]
    user = "Translate this JSON array to English:\n" + json.dumps(payload, ensure_ascii=False)
    try:
        resp = client.messages.create(
            model=cfg.get("model", "deepseek-chat"),
            max_tokens=int(cfg.get("max_tokens", 3000)),
            system=SYSTEM_EN,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
    except Exception as e:  # noqa: BLE001
        log.warning("news EN-translation batch failed: %s", e)
        return none
    arr = _extract_array(text)
    if arr is None or len(arr) != len(texts):
        log.warning("news EN-translation malformed: got %s for %d inputs",
                    None if arr is None else len(arr), len(texts))
        return none
    out: list[str | None] = []
    for val in arr:
        s = str(val).strip() if val is not None else ""
        out.append(s if _looks_english(s) else None)
    return out


def translate_to_en(texts: list[str], cfg: dict | None = None) -> list[str | None]:
    """Translate Simplified-Chinese news strings to English, cache-aligned.

    English strings pass through unchanged. Chinese strings return a cached/API
    translation or None, so callers can fall back to the original text.
    """
    cfg = cfg if cfg is not None else _cfg()
    if not texts:
        return []
    cached, missing = _read_cache_en(texts, cfg)
    if not missing or not cfg.get("enabled"):
        return cached
    client = _client(cfg)
    if client is None:
        return cached
    batch_size = max(1, int(cfg.get("batch_size", 16)))
    for start in range(0, len(missing), batch_size):
        idxs = missing[start:start + batch_size]
        src = [texts[i] for i in idxs]
        en = _translate_batch_en(client, src, cfg)
        _write_cache_en(list(zip(src, en)), cfg)
        for i, val in zip(idxs, en, strict=False):
            if val:
                cached[i] = val
    return cached
