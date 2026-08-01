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
import os
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

# The Codex tier that carries this lane (operator directive 2026-07-31). Kept as a
# literal rather than an import of engine.codex_provider.TERRA_MODEL: that module
# pulls in the codex_lane runner, and a deepseek host must not pay that import just
# to name a default. tests/test_news_translate_render_gate.py pins the two equal.
CODEX_TERRA_MODEL = "gpt-5.6-terra"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"

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
            "provider": "deepseek",
            "api_key_env": "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com/anthropic",
            "model": DEFAULT_DEEPSEEK_MODEL,
            "cache_dir": "data/news_translation/cache",
        }
    return cfg


def _provider(cfg: dict) -> str:
    """Which transport this config selects: "codex" or "deepseek" (the default).

    One provider at a time, chosen by config — deliberately NOT a failover chain.
    An unreachable provider degrades this lane to cache-only, which is the same
    honest fallback an unkeyed host has always had.
    """
    return str(cfg.get("provider") or "deepseek").strip().lower()


def _model(cfg: dict) -> str:
    """The model id sent on the wire, defaulted per provider.

    Without the per-provider default a codex config that omits `model` would send
    "deepseek-chat"; ``codex_provider.translate_model`` maps that to Terra anyway,
    so the call would work while the usage ledger recorded a model that never ran.
    """
    return str(cfg.get("model") or (
        CODEX_TERRA_MODEL if _provider(cfg) == "codex" else DEFAULT_DEEPSEEK_MODEL))


def translator_ready(cfg: dict | None = None) -> tuple[bool, str]:
    """Whether the CONFIGURED translator can actually run here -> (ready, reason).

    Callers used to preflight with a bare ``config.secret("DEEPSEEK_API_KEY")``.
    That reads as a correct check and is wrong under any other provider: on a
    codex host it warns about a key nothing needs while the lane works fine, and
    it would stay silent in the one case that matters — codex selected and not
    attached. Asking the translator keeps the check from drifting away from the
    client it is checking.

    ``reason`` is an operator sentence in both directions; the ready form names
    the provider and model actually in force, so a log line proves WHICH
    translator ran rather than which one the config hoped for.
    """
    cfg = cfg if cfg is not None else _cfg()
    provider = _provider(cfg)
    if provider == "codex":
        try:
            from engine import codex_provider as _codex  # noqa: PLC0415
        except Exception as e:  # noqa: BLE001
            return (False, f"codex provider import failed ({type(e).__name__}: {e})")
        if not _codex.is_available():
            return (False, "no attached Codex account on this host (codex CLI "
                           "missing, no login under CODEX_HOME, or "
                           "CODEX_PROVIDER_ENABLED is off)")
        return (True, f"codex/{_model(cfg)}")
    env = str(cfg.get("api_key_env") or "DEEPSEEK_API_KEY")
    if not config.secret(env):
        return (False, f"{env} is not set on this host")
    return (True, f"{provider}/{_model(cfg)}")


def _api_fill_allowed(cfg: dict) -> bool:
    """Cache reads always happen; this gates only the network fill.

    Render-family lanes (render / engine-render / closing-bell, identified by the
    RENDER_NO_DRIP=1 sentinel they already set) are secret-free by design, so the
    API fill there is opt-in via news_translation.render_lanes (default off) —
    per-build LLM spend stays an operator decision. Nightly daily.yml and
    asia-close leave the sentinel unset and are unaffected.
    """
    if not cfg.get("enabled"):
        return False
    if os.environ.get("RENDER_NO_DRIP") == "1" and not cfg.get("render_lanes"):
        return False
    return True


def _cache_dir(cfg: dict) -> Path:
    """The translation cache directory.

    A relative ``cache_dir`` resolves under the repo root (the nightly/render
    lanes, whose cache IS committed). An ABSOLUTE one is taken verbatim, which is
    how a long-running poller keeps its cache off the deployed checkout — that
    tree is hard-reset every few minutes and its ``data/news_translation/cache``
    is git-tracked, so a poller writing there both loses its cache and dirties
    the work-tree (D05 W0 zero-repo-writes law).
    """
    raw = str(cfg.get("cache_dir") or "data/news_translation/cache")
    cdir = Path(raw) if Path(raw).is_absolute() else config.ROOT / raw
    cdir.mkdir(parents=True, exist_ok=True)
    return cdir


def _payload_text(text: str, cfg: dict) -> str:
    """The EXACT string sent to the model for ``text``.

    The batch call truncates to ``max_chars``; the cache must be keyed on THIS,
    not on the caller's original. Keying on the original stored a translation of
    the first N characters under the full text, so every later consumer of the
    SHARED cache — macro_news, china_news — read back a silently truncated
    Chinese string as if it were the whole item. One definition, used by the
    reader, the writer and the sender so they cannot drift apart.
    """
    try:
        max_chars = int(cfg.get("max_chars", 360))
    except (TypeError, ValueError):
        max_chars = 360
    return text[:max_chars] if max_chars > 0 else text


def _create_kwargs(cfg: dict, system: str, user: str) -> dict:
    """Arguments for one messages.create call.

    ``timeout``/``max_retries`` are opt-in per lane: the SDK default is minutes
    plus retries, which is fine inside a nightly build and fatal inside a
    75-second poller tick whose heartbeat only touches after the tick returns —
    one hung endpoint reads to the monitor as a dead daemon.
    """
    kwargs: dict = {
        "model": _model(cfg),
        "max_tokens": int(cfg.get("max_tokens", 3000)),
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if cfg.get("timeout_s"):
        kwargs["timeout"] = float(cfg["timeout_s"])
    return kwargs


def _record_usage(cfg: dict, resp) -> None:
    """Record spend, unless the caller owns a sink outside the repo.

    ``usage_sink`` set to "none" suppresses the lib.ai_costs write entirely. That
    ledger lives at data/ai_costs/usage.jsonl, which the nightly is the sole
    advancer of; an intraday poller appending to it both violates that law and
    writes inside a checkout that gets hard-reset. Such a caller reports its own
    spend through its own gitignored host state.
    """
    if str(cfg.get("usage_sink", "")).lower() == "none":
        return
    try:
        from lib import ai_costs as _ac  # noqa: PLC0415
        if _provider(cfg) == "codex":
            # infer_provider only knows base_url shapes, and the codex path has no
            # base_url — it would file an attached-subscription turn as metered
            # claude_api. Same vocabulary llm_auth._capture_usage uses for codex.
            _prov, _basis = "codex", "subscription"
        else:
            _prov, _basis = _ac.infer_provider(cfg.get("base_url"))
        _ac.record_response_usage(lane=str(cfg.get("usage_lane", "news-translate")),
                                  response=resp,
                                  model=_model(cfg),
                                  provider=_prov, cost_basis=_basis)
    except Exception:  # noqa: BLE001
        pass


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
        path = cdir / f"{_key(_payload_text(text, cfg))}.json"
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
            sent = _payload_text(src, cfg)
            (cdir / f"{_key(sent)}.json").write_text(json.dumps(
                {"text": sent, "text_zh": zh}, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass


def _codex_client(cfg: dict):
    """The attached Codex subscription, wearing the Anthropic client shape.

    Operator directive 2026-07-31: the zh wire-headline pass runs on the embedded
    codex subscription instead of DEEPSEEK_API_KEY, which was never provisioned on
    the press host — the lane looked armed in config and shipped English forever.
    ``CodexClient`` exposes the same ``messages.create(model=, max_tokens=, system=,
    messages=)`` surface, so the batch JSON-array protocol above is untouched: only
    the transport moves. Tier is Terra, which already carries the hot-tape wire.

    The import is lazy because ``engine.codex_provider`` drags in the codex_lane
    runner; a deepseek host must neither pay that import nor fail on it.

    Unavailable is a NORMAL outcome, not an error: a runner with no codex login
    returns None here and the lane degrades to cache-only, exactly as an unkeyed
    host always has.
    """
    try:
        from engine import codex_provider as _codex  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        log.warning("news translation codex provider unavailable: %s", e)
        return None
    if not _codex.is_available():
        log.warning("news translation: provider is codex but no attached account "
                    "on this host — translation degrades to cache-only")
        return None
    try:
        kw: dict = {"timeout_s": max(1, int(float(cfg.get("timeout_s") or 60)))}
        # Optional: headline translation is mechanical, so a lane on a short tick
        # budget can spend less thinking time per turn.
        effort = str(cfg.get("codex_reasoning_effort") or "").strip()
        if effort:
            kw["reasoning_effort"] = effort
        return _codex.CodexClient(**kw)
    except Exception as e:  # noqa: BLE001
        log.warning("news translation codex client init failed: %s", e)
        return None


def _client(cfg: dict):
    if _provider(cfg) == "codex":
        return _codex_client(cfg)
    key = config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY"))
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK not installed; news translation skipped")
        return None
    try:
        kw: dict = {"api_key": key}
        if cfg.get("base_url"):
            kw["base_url"] = cfg["base_url"]
        # A poller lane sets max_retries=0: the SDK's default retry ladder turns
        # one slow endpoint into several multiples of the timeout, inside a tick
        # that has a heartbeat waiting on it.
        if cfg.get("max_retries") is not None:
            kw["max_retries"] = int(cfg["max_retries"])
        return anthropic.Anthropic(**kw)
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
    payload = [_payload_text(t, cfg) for t in texts]
    user = "Translate this JSON array to Simplified Chinese:\n" + json.dumps(payload, ensure_ascii=False)
    try:
        resp = client.messages.create(**_create_kwargs(cfg, SYSTEM_ZH, user))
        _record_usage(cfg, resp)
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
    if not missing or not _api_fill_allowed(cfg):
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
        path = cdir / f"{_key(_payload_text(text, cfg), 'en')}.json"
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
            sent = _payload_text(src, cfg)
            (cdir / f"{_key(sent, 'en')}.json").write_text(json.dumps(
                {"text": sent, "text_en": en}, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass


def _translate_batch_en(client, texts: list[str], cfg: dict) -> list[str | None]:
    none = [None] * len(texts)
    payload = [_payload_text(t, cfg) for t in texts]
    user = "Translate this JSON array to English:\n" + json.dumps(payload, ensure_ascii=False)
    try:
        resp = client.messages.create(**_create_kwargs(cfg, SYSTEM_EN, user))
        _record_usage(cfg, resp)
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
    if not missing or not _api_fill_allowed(cfg):
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
