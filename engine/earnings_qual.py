"""engine/earnings_qual.py — provider-agnostic earnings-call qualitative scorer.

SGA W4 (rulings SGA-R5/R6, masterplan §4).  Turns earnings-call text (a
transcript, or an 8-K Item-2.02 press release as the free cold-start fallback)
into a small structured qualitative read: a sentiment score, a numbers-first
performance score, a plain tone word, up to three positive/negative evidence
highlights, and a pinned set of tags.

WHY THIS EXISTS
---------------
A competitor ($25/mo) gates early-Stage-2 entries on LLM-scored earnings calls.
We reproduce the *substrate* — but under our epistemics: every score carries
``is_context_only: true`` (SGA-R5).  LLM output NEVER originates ranking
authority; it displays as chips and an earnings-desk section and is EXCLUDED
from ``sga_score`` until a pre-registered promotion gauntlet passes.

PROVIDERS
---------
Provider-agnostic dispatch, ordered by ``config/earnings_qual.yml``:
  • ``openai_compat`` — the LOCAL Qwen path.  POST ``{base_url}/chat/completions``
    (OpenAI Chat Completions shape) against a llama.cpp / LM Studio / vLLM server
    on the operator's Windows PC.  base_url + model come from provider_cfg.
  • ``anthropic`` / ``deepseek`` — cloud fallback via ``engine.llm_auth.make_call``
    (off the render-critical path, cheapest lane — Haiku/DeepSeek).

STRICT JSON, ONE RETRY, THEN DEGRADE
------------------------------------
The prompt demands a single JSON object.  If parsing fails we retry once with a
terse "return ONLY valid JSON" reminder; a second failure returns a degraded row
(``degraded_reason`` set, scores None) rather than crashing — fail-open is law.

TRADING-VERB POST-FILTER (SGA-R5 / masterplan §7)
-------------------------------------------------
Highlight strings are deterministically scrubbed of trading verbs
(buy/sell/short/accumulate/add/trim/…).  A model that leaks "accumulate the dip"
never reaches the page: the verb is rewritten to neutral phrasing, or the
highlight is dropped when it cannot be salvaged.  This runs regardless of
provider — it is a hard post-filter, not a prompt hope.

FAIL-OPEN CONTRACT
------------------
Nothing here crashes a build.  Missing config → sane defaults.  No sources →
score_new returns 0.  Provider errors → degraded row.  Parquet writes are atomic
(temp file + os.replace).  No new heavy deps: pandas + requests only (both are
already pipeline dependencies).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repo-root bootstrap so `lib.*` / `engine.*` imports work when run as a script
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Shared advice scrubber (SAME rules as engine/stage_research.py) — every piece
# of user-facing free text on the Earnings-Calls surfaces routes through it so no
# "buy / sell / accumulate / price target / go long" language reaches the page.
from engine._text_scrub import scrub_advice as _scrub_advice_text  # noqa: E402

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Pinned tag taxonomy (masterplan §2 — the ONLY tags that survive the filter).
# Any tag the model emits outside this set is dropped.
# --------------------------------------------------------------------------- #
TAG_TAXONOMY: tuple[str, ...] = (
    "guidance_raised",
    "guidance_lowered",
    "beat_and_raise",
    "miss_and_cut",
    "margin_expansion",
    "margin_contraction",
    "demand_acceleration",
    "demand_slowdown",
    "supply_constraint",
    "new_product",
    "buyback_or_dividend",
    "regulatory_headwind",
    "competitor_threat",
    "macro_sensitivity",
)
_TAG_SET = frozenset(TAG_TAXONOMY)

# Allowed tone words (kept small + plain so the page reads with zero jargon).
_TONE_WORDS: frozenset[str] = frozenset({
    "confident", "upbeat", "steady", "cautious", "defensive",
    "mixed", "guarded", "downbeat", "reassuring", "uncertain",
})

# --------------------------------------------------------------------------- #
# Trading-verb post-filter (SGA-R5).  These verbs must never reach a highlight.
# We match on word boundaries, case-insensitively.  When a verb is found we try
# a neutral rewrite; if the highlight is dominated by the trade call, we drop it.
# --------------------------------------------------------------------------- #
# verb (regex, case-insensitive, word-boundary) -> neutral replacement phrase
_TRADING_VERB_REWRITES: tuple[tuple[str, str], ...] = (
    (r"\bbuy the dip\b", "note the pullback"),
    (r"\bbuy(?:ing|s)?\b", "note"),
    (r"\bsell(?:ing|s)?\b", "note"),
    (r"\bshort(?:ing|s)?\b", "note weakness in"),
    (r"\baccumulat(?:e|ing|es|ion)\b", "note"),
    (r"\badd(?:ing|s)?\b(?=.*\bposition|\bshares?\b|\bexposure\b)", "hold"),
    (r"\btrim(?:ming|s)?\b", "reduce exposure note"),
    (r"\bgo long\b", "note strength in"),
    (r"\btake profit(?:s)?\b", "note the gain"),
    (r"\bstop[- ]loss\b", "downside level"),
    (r"\benter(?:ing)? (?:a )?(?:position|trade)\b", "note the setup"),
    (r"\bexit(?:ing)? (?:the )?(?:position|trade)\b", "note the move"),
)
# A highlight that STILL contains any of these hard-trade tokens after rewriting
# is dropped entirely (belt-and-suspenders — if the rewrite left a residue).
_HARD_TRADE_TOKENS = re.compile(
    r"\b(buy|sell|short|accumulate|long|overweight|underweight|price target|"
    r"upgrade|downgrade)\b",
    re.IGNORECASE,
)

_MAX_HIGHLIGHTS = 3

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
_DEFAULT_CFG: dict[str, Any] = {
    "provider_order": ["openai_compat", "deepseek", "kimi", "anthropic"],
    "openai_compat": {
        "base_url": "http://localhost:8000/v1",
        "model": "qwen3-14b",
        "api_key_env": "LOCAL_LLM_API_KEY",
        "timeout_s": 120,
        "max_tokens": 1200,
    },
    "opus_model": "claude-haiku-4-5",
    "deepseek_model": "deepseek-v4-flash",
    "kimi": {
        "base_url": "https://api.moonshot.ai/v1",
        "model": "kimi-k2.6",
        "api_key_env": "MOONSHOT_API_KEY",
        "timeout_s": 120,
        "max_tokens": 1200,
    },
    "daily_cap": 64,
    "max_chars": 24000,
    "tail_chars": 8000,
    "retry_on_bad_json": 1,
    "prompt_version": "equal-v2",
    "analysis_schema_version": "earnings-qual/v2",
    "usage_lane": "earnings_qual",
}


def load_config(root: Path | None = None) -> dict[str, Any]:
    """Load config/earnings_qual.yml, merged over defaults.  Never raises."""
    cfg = dict(_DEFAULT_CFG)
    try:
        r = Path(root) if root is not None else _REPO_ROOT
        p = r / "config" / "earnings_qual.yml"
        if p.exists():
            import yaml  # noqa: PLC0415
            loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                cfg.update(loaded)
                # deep-merge the openai_compat block so partial overrides work
                oc = dict(_DEFAULT_CFG["openai_compat"])
                oc.update(loaded.get("openai_compat") or {})
                cfg["openai_compat"] = oc
                kimi = dict(_DEFAULT_CFG["kimi"])
                kimi.update(loaded.get("kimi") or {})
                cfg["kimi"] = kimi
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings_qual: config load failed (%s) — using defaults", exc)
    return cfg


# --------------------------------------------------------------------------- #
# The scoring system prompt.  The definitive copy lives in
# tools/earnings_worker/prompts.py (the product surface); this is a compact,
# self-contained mirror so the engine works even when the worker package is not
# importable (e.g. cloud-fallback lane on the Mac runner).
# --------------------------------------------------------------------------- #
_SYSTEM_PROMPT = """You are an equity-research analyst reading an earnings call \
(or an earnings press release). Read the NUMBERS FIRST — revenue, EPS, margins, \
segment growth, guidance versus prior guidance and versus consensus. THEN read \
tone and forward guidance. Ground every judgement in the text. Do not invent \
figures. You describe what management reported and how it reads. You do NOT give \
investment advice, price targets, or trade calls of any kind.

Return ONE JSON object and nothing else — no prose, no markdown fences. Schema:
{
  "sentiment": <float -1..1>,          // net tone+guidance read; +1 very positive
  "performance": <float 0..10>,        // numbers-first quarter quality; 10 = blowout
  "confidence": <float 0..1>,          // your confidence given the text provided
  "tone_word": "<one of: confident, upbeat, steady, cautious, defensive, mixed, \
guarded, downbeat, reassuring, uncertain>",
  "summary": "<2-4 factual sentences: numbers, guidance, key change; no advice>",
  "positive_highlights": ["<=3 short evidence phrases, each grounded in the text"],
  "negative_highlights": ["<=3 short evidence phrases, each grounded in the text"],
  "tags": ["subset of: guidance_raised, guidance_lowered, beat_and_raise, \
miss_and_cut, margin_expansion, margin_contraction, demand_acceleration, \
demand_slowdown, supply_constraint, new_product, buyback_or_dividend, \
regulatory_headwind, competitor_threat, macro_sensitivity"]
}
Highlights are factual observations ("revenue up 22% YoY, above the high end of \
guidance"), never trade instructions. Use ONLY tags from the list; omit tags you \
cannot support. If the text is too thin to score, still return the JSON with your \
best low-confidence read."""

_RETRY_SUFFIX = (
    "\n\nYour previous reply was not valid JSON. Return ONLY the JSON object, "
    "with no surrounding text and no markdown code fences."
)


# --------------------------------------------------------------------------- #
# Provider dispatch
# --------------------------------------------------------------------------- #
def _call_openai_compat(
    system: str, user: str, oc_cfg: dict, *, max_tokens: int
) -> tuple[str | None, str | None]:
    """POST to a local OpenAI-compatible /chat/completions endpoint.

    Returns (text, degraded_reason). Never raises — connection / HTTP / shape
    errors degrade to (None, reason). base_url + model come from oc_cfg.
    """
    base_url = str(oc_cfg.get("base_url") or "").rstrip("/")
    model = str(oc_cfg.get("model") or "")
    if not base_url or not model:
        return None, "openai_compat_unconfigured"
    url = f"{base_url}/chat/completions"
    api_key = ""
    key_env = oc_cfg.get("api_key_env")
    if key_env:
        api_key = os.environ.get(str(key_env), "") or ""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": int(max_tokens),
        "temperature": 0,
        "stream": False,
    }
    timeout = float(oc_cfg.get("timeout_s", 120))
    try:
        import requests  # noqa: PLC0415
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if r.status_code != 200:
            return None, f"openai_compat_http_{r.status_code}"
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings_qual: openai_compat call failed (%s)", exc)
        return None, "openai_compat_error"
    try:
        choices = data.get("choices") or []
        if not choices:
            return None, "openai_compat_empty"
        msg = choices[0].get("message") or {}
        text = msg.get("content")
        if not text:
            return None, "openai_compat_empty"
        return str(text), None
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings_qual: openai_compat parse failed (%s)", exc)
        return None, "openai_compat_bad_shape"


def _call_kimi(
    system: str, user: str, kimi_cfg: dict, *, max_tokens: int
) -> tuple[str | None, str | None]:
    """Call Moonshot/Kimi through its OpenAI-compatible Chat Completions API."""

    cfg = dict(kimi_cfg or {})
    key_env = str(cfg.get("api_key_env") or "MOONSHOT_API_KEY")
    api_key = os.environ.get(key_env, "") or ""
    if not api_key:
        return None, "kimi_unconfigured"
    cfg["api_key_env"] = key_env
    # Reuse the same hardened OpenAI-compatible request path.  The API key is
    # read from cfg.api_key_env and never enters a persisted artifact.
    return _call_openai_compat(system, user, cfg, max_tokens=max_tokens)


def _call_llm_auth(
    system: str, user: str, cfg: dict, provider_name: str, *, max_tokens: int
) -> tuple[str | None, str | None]:
    """Cloud fallback via engine.llm_auth for a single named provider.

    provider_name ∈ {"anthropic", "deepseek", "codex"}. Builds a one-provider waterfall
    so the harness controls ordering (config's provider_order), not llm_auth's
    default oauth-first ladder.  Never raises.
    """
    try:
        from engine import llm_auth  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings_qual: llm_auth import failed (%s)", exc)
        return None, "no_provider"

    sub_cfg = dict(cfg)
    sub_cfg["provider_order"] = [provider_name]
    # The earnings worker owns its explicit provider order and cost ledger.
    # llm_auth normally appends the attached Codex subscription as a fallback
    # to non-OAuth lanes; disable that implicit rung here so a failed DeepSeek
    # request cannot silently execute Terra while the score says "deepseek".
    # Codex remains available to callers that choose it explicitly elsewhere.
    sub_cfg["codex_provider"] = False
    try:
        providers = llm_auth.build_providers(
            sub_cfg,
            opus_model=cfg.get("opus_model", "claude-haiku-4-5"),
            deepseek_model=cfg.get("deepseek_model", "deepseek-v4-pro"),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings_qual: build_providers failed (%s)", exc)
        return None, "no_provider"
    if not providers:
        return None, "no_provider"

    def _do_call(client, model: str):
        resp = client.messages.create(
            model=model,
            max_tokens=int(max_tokens),
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        sr = getattr(resp, "stop_reason", None)
        if sr == "refusal":
            return None, "stop_refusal", resp
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        )
        if not text:
            return None, "empty_reply", resp
        return text, ("truncated" if sr == "max_tokens" else None), resp

    try:
        text, reason, _used = llm_auth.make_call(
            providers, _do_call, context="earnings_qual"
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings_qual: llm_auth call failed (%s)", exc)
        return None, "llm_error"
    return text, reason


def _dispatch(
    system: str, user: str, cfg: dict, provider_cfg: dict, *, max_tokens: int
) -> tuple[str | None, str | None, str | None]:
    """Try providers in provider_order until one answers.

    Returns (text, degraded_reason, provider_used).  provider_cfg may override
    the openai_compat block (e.g. the PC worker passing its live endpoint).
    """
    order = provider_cfg.get("provider_order") or cfg.get("provider_order") \
        or ["openai_compat", "deepseek", "anthropic"]
    oc_cfg = dict(cfg.get("openai_compat") or {})
    oc_cfg.update(provider_cfg.get("openai_compat") or {})

    last_reason: str | None = None
    for name in order:
        if name == "openai_compat":
            text, reason = _call_openai_compat(system, user, oc_cfg, max_tokens=max_tokens)
        elif name == "kimi":
            text, reason = _call_kimi(
                system, user, cfg.get("kimi") or {}, max_tokens=max_tokens
            )
        elif name in ("anthropic", "deepseek", "codex"):
            text, reason = _call_llm_auth(system, user, cfg, name, max_tokens=max_tokens)
        else:
            log.warning("earnings_qual: unknown provider '%s' — skipping", name)
            continue
        if text:
            return text, reason, name
        last_reason = reason or last_reason
    return None, last_reason or "no_provider", None


# --------------------------------------------------------------------------- #
# JSON parsing + coercion
# --------------------------------------------------------------------------- #
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict | None:
    """Parse a JSON object out of a model reply.  Tolerates code fences and
    surrounding prose by grabbing the outermost {...} span.  Returns None when
    no valid object can be recovered."""
    if not text:
        return None
    t = text.strip()
    # Strip common markdown fences.
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except Exception:  # noqa: BLE001
        pass
    m = _JSON_OBJ_RE.search(t)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:  # noqa: BLE001
            return None
    return None


def _clip(v: Any, lo: float, hi: float, default: float | None) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f:  # NaN
        return default
    return max(lo, min(hi, f))


# --------------------------------------------------------------------------- #
# Trading-verb post-filter
# --------------------------------------------------------------------------- #
def _scrub_trading_verbs(phrase: str) -> str | None:
    """Rewrite trading verbs to neutral phrasing; return None if the highlight
    is dominated by a trade call and cannot be salvaged.

    Deterministic, provider-independent (SGA-R5).  Applied to every highlight.
    """
    if not phrase or not isinstance(phrase, str):
        return None
    out = phrase.strip()
    if not out:
        return None
    for pat, repl in _TRADING_VERB_REWRITES:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    # Collapse doubled spaces produced by rewrites.
    out = re.sub(r"\s{2,}", " ", out).strip()
    # Belt-and-suspenders: if a hard trade token survived, drop the highlight.
    if _HARD_TRADE_TOKENS.search(out):
        return None
    if not out:
        return None
    return out


def _clean_highlights(raw: Any) -> list[str]:
    """Coerce a highlights value into <=3 scrubbed, de-duplicated strings."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        cleaned = _scrub_trading_verbs(item)
        if cleaned is None:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if len(out) >= _MAX_HIGHLIGHTS:
            break
    return out


def _clean_tags(raw: Any) -> list[str]:
    """Keep only pinned taxonomy tags; drop unknowns; preserve first-seen order
    and de-duplicate."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for t in raw:
        if not isinstance(t, str):
            continue
        key = t.strip().lower()
        if key in _TAG_SET and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _clean_tone(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    w = raw.strip().lower()
    return w if w in _TONE_WORDS else None


def _analysis_obj_complete(obj: dict | None) -> bool:
    """Whether a parsed provider reply satisfies the required score fields."""

    if not isinstance(obj, dict):
        return False
    return all((
        _clip(obj.get("sentiment"), -1.0, 1.0, None) is not None,
        _clip(obj.get("performance"), 0.0, 10.0, None) is not None,
        _clip(obj.get("confidence"), 0.0, 1.0, None) is not None,
    ))


# --------------------------------------------------------------------------- #
# source_sha256
# --------------------------------------------------------------------------- #
def source_sha256(text: str) -> str:
    """Deterministic content hash of the scored text (dedup key component)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# score_text — the harness core
# --------------------------------------------------------------------------- #
def score_text(
    text: str,
    ticker: str,
    quarter: str | int | None,
    year: int | None,
    provider_cfg: dict | None = None,
    *,
    cfg: dict | None = None,
    call_date: str | None = None,
    source: str = "transcript",
    source_record_id: str | None = None,
    source_updated_at: str | None = None,
    source_url: str | None = None,
    source_revision_sha256: str | None = None,
) -> dict:
    """Score one earnings-call text.  Provider-agnostic; never raises.

    Parameters
    ----------
    text        : the transcript or 8-K press-release text.
    ticker      : symbol (upper-cased in the row).
    quarter     : "Q1".."Q4" or 1..4 (stored as given, normalized to str).
    year        : fiscal/report year (int).
    provider_cfg: optional overrides for the local endpoint / provider order
                  (the PC worker passes {"openai_compat": {...}} here).
    cfg         : full loaded config (load_config()); loaded lazily if omitted.
    call_date   : ISO date of the call/filing (for the row + ledger join).
    source      : "transcript" | "8k".
    source_record_id: stable upstream identity (preferred upsert key).
    source_updated_at: upstream commit-marker/index generation timestamp.
    source_url: public-safe citation back to the scored source body.
    source_revision_sha256: canonical upstream body hash, including metadata.

    Returns a dict conforming to the §2 scores contract:
      { ticker, quarter, year, call_date, source, model, sentiment,
        performance, confidence, tone_word, positive_highlights,
        negative_highlights, tags, summary, source_sha256, scored_at,
        source_record_id, source_updated_at, source_url,
        source_revision_sha256, prompt_version,
        analysis_schema_version, is_context_only, degraded_reason }
    """
    cfg = cfg if cfg is not None else load_config()
    provider_cfg = provider_cfg or {}
    sha = source_sha256(text or "")
    q_norm = _norm_quarter(quarter)
    y_norm = _norm_year(year)

    base_row: dict[str, Any] = {
        "ticker": (ticker or "").upper(),
        "quarter": q_norm,
        "year": y_norm,
        "call_date": call_date or "",
        "source": source,
        "model": None,
        "sentiment": None,
        "performance": None,
        "confidence": None,
        "tone_word": None,
        "positive_highlights": [],
        "negative_highlights": [],
        "tags": [],
        "source_sha256": sha,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "source_record_id": source_record_id or None,
        "source_updated_at": source_updated_at or None,
        "source_url": source_url or None,
        "source_revision_sha256": source_revision_sha256 or None,
        "prompt_version": str(cfg.get("prompt_version") or ""),
        "analysis_schema_version": str(cfg.get("analysis_schema_version") or ""),
        "summary": None,           # SGA W5: call_summary from the model (optional)
        "is_context_only": True,   # SGA-R5 — ALWAYS context-only
        "degraded_reason": None,
    }

    if not text or not str(text).strip():
        base_row["degraded_reason"] = "empty_text"
        return base_row

    max_chars = int(cfg.get("max_chars", 24000))
    tail_chars = int(cfg.get("tail_chars", 8000))
    body = _bounded_transcript_text(str(text), max_chars=max_chars, tail_chars=tail_chars)
    max_tokens = int(
        (provider_cfg.get("openai_compat") or {}).get("max_tokens")
        or (cfg.get("openai_compat") or {}).get("max_tokens")
        or 1200
    )

    user = _build_user_prompt(base_row["ticker"], q_norm, y_norm, source, body)

    # Validate and retry one provider rung at a time. A local endpoint that
    # answers with malformed or incomplete JSON must not pin the durable queue;
    # after its bounded retry the next configured provider gets a chance.
    retries = int(cfg.get("retry_on_bad_json", 1))
    order = (
        provider_cfg.get("provider_order")
        or cfg.get("provider_order")
        or ["openai_compat", "deepseek", "anthropic"]
    )
    obj: dict | None = None
    provider_used: str | None = None
    last_reason: str | None = None
    last_shape_reason: str | None = None
    for provider_name in [str(name) for name in order if str(name).strip()]:
        rung_cfg = dict(provider_cfg)
        rung_cfg["provider_order"] = [provider_name]
        reply, reason, used = _dispatch(
            _SYSTEM_PROMPT, user, cfg, rung_cfg, max_tokens=max_tokens
        )
        last_reason = reason or last_reason
        if reply is None:
            continue
        provider_used = used or provider_name
        candidate = _extract_json(reply)
        shape_reason = (
            None
            if _analysis_obj_complete(candidate)
            else ("incomplete_schema" if candidate is not None else "invalid_json")
        )
        if shape_reason is not None and retries > 0:
            reply2, reason2, used2 = _dispatch(
                _SYSTEM_PROMPT,
                user + _RETRY_SUFFIX,
                cfg,
                rung_cfg,
                max_tokens=max_tokens,
            )
            last_reason = reason2 or last_reason
            if reply2 is not None:
                provider_used = used2 or provider_name
                candidate = _extract_json(reply2)
                shape_reason = (
                    None
                    if _analysis_obj_complete(candidate)
                    else (
                        "incomplete_schema"
                        if candidate is not None
                        else "invalid_json"
                    )
                )
        if shape_reason is None:
            obj = candidate
            break
        last_shape_reason = shape_reason

    if obj is None:
        base_row["degraded_reason"] = (
            last_shape_reason or last_reason or "no_provider"
        )
        base_row["model"] = provider_used
        return base_row

    # Coerce + post-filter.
    base_row["model"] = provider_used
    base_row["sentiment"] = _clip(obj.get("sentiment"), -1.0, 1.0, None)
    base_row["performance"] = _clip(obj.get("performance"), 0.0, 10.0, None)
    base_row["confidence"] = _clip(obj.get("confidence"), 0.0, 1.0, None)
    base_row["tone_word"] = _clean_tone(obj.get("tone_word"))
    base_row["positive_highlights"] = _clean_highlights(obj.get("positive_highlights"))
    base_row["negative_highlights"] = _clean_highlights(obj.get("negative_highlights"))
    base_row["tags"] = _clean_tags(obj.get("tags"))
    raw_summary = obj.get("summary")
    if isinstance(raw_summary, str):
        base_row["summary"] = _scrub_advice_text(raw_summary.strip()[:1600])
    # A parseable JSON object is not necessarily a usable score.  Treat a
    # partial schema as retryable degradation so it never becomes the live
    # overlay merely because the provider happened to return ``{}``.
    if any(base_row.get(key) is None for key in (
        "sentiment", "performance", "confidence",
    )):
        base_row["degraded_reason"] = "incomplete_schema"
    return base_row


def _bounded_transcript_text(text: str, *, max_chars: int, tail_chars: int) -> str:
    """Keep prepared remarks plus Q&A tail instead of truncating the tail away.

    The scorer remains a compact one-pass extractor, but a long call's analyst
    questions often contain the most useful guidance challenges.  The old
    ``text[:max_chars]`` contract discarded that section on nearly every call.
    """

    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    tail = min(max(0, int(tail_chars)), max_chars // 2)
    if tail <= 0:
        return text[:max_chars]
    marker = "\n\n[... middle of transcript omitted for bounded extraction ...]\n\n"
    head = max_chars - tail - len(marker)
    if head <= 0:
        return text[: max_chars - tail] + text[-tail:]
    return text[:head] + marker + text[-tail:]


def _build_user_prompt(
    ticker: str, quarter: str | None, year: int | None, source: str, body: str
) -> str:
    src_label = "earnings-call transcript" if source == "transcript" \
        else "earnings press release (8-K Item 2.02)"
    q = quarter or "?"
    y = year if year is not None else "?"
    return (
        f"Company: {ticker}\nPeriod: {q} FY{y}\nSource: {src_label}\n\n"
        f"--- BEGIN {src_label.upper()} ---\n{body}\n--- END ---\n\n"
        "Return the JSON object per the schema. JSON only."
    )


def _norm_quarter(q: str | int | None) -> str | None:
    if q is None:
        return None
    if isinstance(q, int):
        return f"Q{q}" if 1 <= q <= 4 else str(q)
    s = str(q).strip().upper()
    if not s:
        return None
    if s.isdigit():
        n = int(s)
        return f"Q{n}" if 1 <= n <= 4 else s
    return s


def _norm_year(y: int | None) -> int | None:
    if y is None:
        return None
    try:
        return int(y)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Parquet store — data/earnings_calls/scores.parquet (gitignored, R2-transport)
# Keyed (ticker, quarter, year, source); never rescore same source_sha256.
# --------------------------------------------------------------------------- #
_STORE_COLUMNS = [
    "ticker", "quarter", "year", "call_date", "source", "model",
    "sentiment", "performance", "confidence", "tone_word",
    "positive_highlights", "negative_highlights", "tags",
    "source_sha256", "scored_at",
    "source_record_id", "source_updated_at", "source_url",
    "source_revision_sha256", "prompt_version",
    "analysis_schema_version",
    "summary",   # SGA W5: model call_summary (str, nullable); live scorer fills if present
    "is_context_only", "degraded_reason",
]
# JSON-encoded columns (stored as strings in parquet for portability).
_JSON_COLUMNS = ("positive_highlights", "negative_highlights", "tags")


def store_path(root: Path | None = None) -> Path:
    r = Path(root) if root is not None else _REPO_ROOT
    return r / "data" / "earnings_calls" / "scores.parquet"


def _row_to_store(row: dict) -> dict:
    """Serialize a score_text row into the parquet column shape (json → str)."""
    out = {c: row.get(c) for c in _STORE_COLUMNS}
    for c in _JSON_COLUMNS:
        val = out.get(c)
        out[c] = json.dumps(val if isinstance(val, list) else [])
    return out


def load_scores(root: Path | None = None):
    """Load the scores parquet as a DataFrame (empty with schema if absent)."""
    import pandas as pd  # noqa: PLC0415
    p = store_path(root)
    if not p.exists():
        return pd.DataFrame(columns=_STORE_COLUMNS)
    try:
        frame = pd.read_parquet(p)
        valid, reason = _validate_transport_frame(frame, p, "scores", root=root)
        if valid is False:
            log.warning("earnings_qual: scores generation rejected (%s)", reason)
            return pd.DataFrame(columns=_STORE_COLUMNS)
        return frame
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings_qual: scores parquet unreadable (%s) — empty", exc)
        return pd.DataFrame(columns=_STORE_COLUMNS)


def _load_scores_unvalidated(root: Path | None = None):
    """Read the producer's mutable local store without transport validation.

    ``manifest.json`` is a published-generation commit marker. It necessarily
    becomes stale between the first local upsert and the later R2 publish, so a
    producer read-modify-write cycle must not reject its own pending local rows.
    Consumer surfaces continue to use strict manifest validation.
    """

    import pandas as pd  # noqa: PLC0415

    p = store_path(root)
    if not p.exists():
        return pd.DataFrame(columns=_STORE_COLUMNS)
    try:
        frame = pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings_qual: mutable scores store unreadable (%s) — empty", exc)
        return pd.DataFrame(columns=_STORE_COLUMNS)
    for column in _STORE_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    return frame[_STORE_COLUMNS]


def _atomic_write_parquet(df, path: Path) -> None:
    """Write a parquet atomically (temp + os.replace) so a crashed write never
    leaves a truncated store."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _merge_score_frames(existing, new_df):
    """Return one identity-deduplicated producer frame."""

    import pandas as pd  # noqa: PLC0415

    if existing.empty:
        combined = new_df.copy()
    else:
        combined = pd.concat([existing, new_df], ignore_index=True)

    def _identity(row) -> str:
        record_id = row.get("source_record_id")
        if record_id is not None and str(record_id).strip() and str(record_id) != "nan":
            return f"record:{str(record_id).strip()}"
        return "legacy:" + "|".join(
            str(row.get(c) if row.get(c) is not None else "")
            for c in ("ticker", "quarter", "year", "source")
        )

    combined["_identity"] = combined.apply(_identity, axis=1)

    # A transient provider outage is useful as an observability receipt, but it
    # must never replace a previously healthy score for the same source record.
    # Among equally healthy rows, prefer the newest source/scoring timestamp and
    # use arrival order only as a deterministic final tie-break.
    degraded = combined["degraded_reason"].fillna("").astype(str).str.strip()
    combined["_healthy"] = degraded.eq("")
    source_time = combined["source_updated_at"].fillna("").astype(str).str.strip()
    scored_time = combined["scored_at"].fillna("").astype(str).str.strip()
    combined["_freshness"] = source_time.where(source_time.ne(""), scored_time)
    combined["_arrival"] = range(len(combined))
    combined = combined.sort_values(
        ["_identity", "_healthy", "_freshness", "_arrival"],
        kind="stable",
    )
    combined = combined.drop_duplicates(subset=["_identity"], keep="last")
    combined = combined.sort_values("_arrival", kind="stable")
    combined = combined.drop(
        columns=["_identity", "_healthy", "_freshness", "_arrival"]
    )
    return combined.reset_index(drop=True)


def _invalidate_local_manifest(root: Path | None = None) -> None:
    """Remove the old commit marker after mutating the producer store."""

    r = Path(root) if root is not None else _REPO_ROOT
    (r / "data" / "earnings_calls" / "manifest.json").unlink(missing_ok=True)


def merge_score_store_frame(frame, root: Path | None = None) -> int:
    """Merge a previously local producer frame after hydrating R2 history."""

    import pandas as pd  # noqa: PLC0415

    if frame is None or frame.empty:
        return 0
    incoming = frame.copy()
    for column in _STORE_COLUMNS:
        if column not in incoming.columns:
            incoming[column] = None
    incoming = incoming[_STORE_COLUMNS]
    existing = _load_scores_unvalidated(root)
    combined = _merge_score_frames(existing, incoming)
    _atomic_write_parquet(combined, store_path(root))
    _invalidate_local_manifest(root)
    return int(len(incoming))


def upsert_scores(rows: list[dict], root: Path | None = None):
    """Upsert rows by stable source record, falling back to the legacy key.

    A later revision for the same ``source_record_id`` replaces its prior score.
    Historical rows that predate that field retain the old
    ``(ticker, quarter, year, source)`` identity.  This avoids collapsing two
    same-quarter source events while preserving backwards compatibility.
    """
    import pandas as pd  # noqa: PLC0415
    if not rows:
        return 0
    existing = _load_scores_unvalidated(root)
    new_df = pd.DataFrame([_row_to_store(r) for r in rows], columns=_STORE_COLUMNS)
    combined = _merge_score_frames(existing, new_df)
    _atomic_write_parquet(combined, store_path(root))
    _invalidate_local_manifest(root)
    return len(new_df)


def _seen_shas(root: Path | None = None) -> set[str]:
    # Producer completion ledger: local rows remain authoritative between a
    # model upsert and the later manifest-last R2 publication.
    df = _load_scores_unvalidated(root)
    if df.empty or "source_sha256" not in df.columns:
        return set()
    # Provider-down/invalid-JSON rows are observability receipts, not completed
    # work.  Excluding them keeps the same source retryable on the next run.
    if "degraded_reason" in df.columns:
        degraded = df["degraded_reason"].fillna("").astype(str).str.strip()
        df = df[degraded == ""]
    return set(df["source_sha256"].dropna().astype(str).tolist())


def _completed_record_shas(root: Path | None = None) -> dict[str, str]:
    """Return healthy stable-source completions for crash-safe intake replay."""

    df = _load_scores_unvalidated(root)
    if df.empty or "source_record_id" not in df.columns:
        return {}
    degraded = df["degraded_reason"].fillna("").astype(str).str.strip()
    healthy = df[degraded.eq("")]
    out: dict[str, str] = {}
    for _, row in healthy.iterrows():
        record_id = str(row.get("source_record_id") or "").strip()
        sha = str(
            row.get("source_revision_sha256")
            or row.get("source_sha256")
            or ""
        ).strip()
        if record_id and record_id != "nan" and sha and sha != "nan":
            out[record_id] = sha
    return out


# --------------------------------------------------------------------------- #
# Cold-start input lane — score_new
# --------------------------------------------------------------------------- #
def _transcripts_dir(root: Path) -> Path:
    return root / "data" / "earnings_calls" / "transcripts"


def _iter_transcript_inputs(root: Path):
    """Yield (payload_dict, text) for each transcript JSON.

    Files: data/earnings_calls/transcripts/*.json shaped
    {ticker, quarter, year, call_date, text}.  Malformed files are skipped.
    """
    d = _transcripts_dir(root)
    if not d.is_dir():
        return
    for p in sorted(d.glob("*.json")):
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("earnings_qual: bad transcript json %s (%s)", p.name, exc)
            continue
        if not isinstance(payload, dict):
            continue
        text = payload.get("text") or ""
        if not str(text).strip():
            continue
        yield payload, str(text)


def _iter_8k_inputs(root: Path, limit: int):
    """Cold-start fallback: yield (payload, text) from EDGAR 8-K Item-2.02
    earnings press releases.

    The committed EDGAR store (data/edgar/earnings_8k_dates.parquet, built by
    collectors/edgar_earnings_8k.py) carries the FILING DATES + item codes, not
    the press-release body.  The body lives in the filing's primary document on
    SEC EDGAR.  For the cold-start lane we fetch the press-release text on demand
    for the most recent filings, capped by `limit`, using the accession available
    in data/edgar/material_8k_events.parquet when present, else the submissions
    index.  Fully fail-open: any fetch error skips that name.

    source='8k' on every row produced here.
    """
    dates_p = root / "data" / "edgar" / "earnings_8k_dates.parquet"
    if not dates_p.exists():
        return
    try:
        import pandas as pd  # noqa: PLC0415
        dates = pd.read_parquet(dates_p)
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings_qual: 8k dates parquet unreadable (%s)", exc)
        return
    if dates.empty:
        return
    # Most-recent Item-2.02 filing per ticker.
    dates = dates.copy()
    dates["_fd"] = pd.to_datetime(dates.get("filing_date"), errors="coerce")
    dates = dates.dropna(subset=["_fd"]).sort_values("_fd", ascending=False)
    seen_tickers: set[str] = set()
    yielded = 0
    for _, r in dates.iterrows():
        if yielded >= limit:
            break
        tk = str(r.get("ticker") or "").upper()
        if not tk or tk in seen_tickers:
            continue
        seen_tickers.add(tk)
        cik = int(r.get("cik") or 0)
        filing_date = r["_fd"].date().isoformat()
        text = _fetch_8k_press_release(cik, filing_date, tk, root)
        if not text or not text.strip():
            continue
        payload = {
            "ticker": tk,
            "quarter": _quarter_from_date(filing_date),
            "year": r["_fd"].year,
            "call_date": filing_date,
        }
        yield payload, text
        yielded += 1


def _quarter_from_date(iso_date: str) -> str | None:
    """Best-effort calendar quarter from a filing date (reporting quarter is the
    prior one — an 8-K filed in Feb reports Q4)."""
    try:
        d = datetime.fromisoformat(iso_date)
    except Exception:  # noqa: BLE001
        return None
    # Reporting quarter ≈ the quarter ending shortly before the filing.
    m = d.month
    if m in (1, 2, 3):
        return "Q4"
    if m in (4, 5, 6):
        return "Q1"
    if m in (7, 8, 9):
        return "Q2"
    return "Q3"


_SEC_UA = "macro-dashboard admin@macro-dashboard.example.com"


def _fetch_8k_press_release(cik: int, filing_date: str, ticker: str, root: Path) -> str | None:
    """Fetch the earnings press-release text of the Item-2.02 8-K filed on
    `filing_date` for `cik`.  Fail-open: returns None on any error.

    Strategy: hit the SEC submissions JSON for the CIK, find the 8-K accession on
    that filing_date carrying item 2.02, then fetch the filing's primary document
    and strip HTML to plain text.  This lane is a COLD-START bootstrap only — the
    production text path is the local transcript vendor on the PC worker.
    """
    if not cik:
        return None
    try:
        import requests  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    sub_url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    try:
        resp = requests.get(
            sub_url,
            headers={"User-Agent": _SEC_UA, "Accept-Encoding": "gzip, deflate"},
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.debug("earnings_qual: 8k submissions fetch failed %s (%s)", ticker, exc)
        return None
    recent = ((data.get("filings") or {}).get("recent")) or {}
    forms = recent.get("form") or []
    fdates = recent.get("filingDate") or []
    accns = recent.get("accessionNumber") or []
    items = recent.get("items") or []
    prim = recent.get("primaryDocument") or []
    accession = doc = None
    for i, form in enumerate(forms):
        if form not in ("8-K", "8-K/A"):
            continue
        if (fdates[i] if i < len(fdates) else "") != filing_date:
            continue
        raw_items = (items[i] if i < len(items) else "") or ""
        if "2.02" not in [t.strip() for t in raw_items.split(",")]:
            continue
        accession = (accns[i] if i < len(accns) else "") or ""
        doc = (prim[i] if i < len(prim) else "") or ""
        break
    if not accession or not doc:
        return None
    acc_nodash = accession.replace("-", "")
    doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/{doc}"
    try:
        r2 = requests.get(doc_url, headers={"User-Agent": _SEC_UA}, timeout=30)
        if r2.status_code != 200:
            return None
        return _html_to_text(r2.text)
    except Exception as exc:  # noqa: BLE001
        log.debug("earnings_qual: 8k doc fetch failed %s (%s)", ticker, exc)
        return None


def _html_to_text(html: str) -> str:
    """Strip tags/scripts to plain text (dependency-free, best-effort)."""
    if not html:
        return ""
    t = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"<style[^>]*>.*?</style>", " ", t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"<[^>]+>", " ", t)
    # Unescape a few common entities.
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                    ("&gt;", ">"), ("&#8217;", "'"), ("&#8220;", '"'),
                    ("&#8221;", '"'), ("&quot;", '"')):
        t = t.replace(ent, ch)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def score_new(
    root: str | Path | None = None,
    source: str = "auto",
    limit: int = 8,
    *,
    cfg: dict | None = None,
    provider_cfg: dict | None = None,
) -> int:
    """Cold-start scoring lane: score un-scored earnings text, upsert to parquet.

    Parameters
    ----------
    root   : repo root (defaults to the package parent).
    source : "auto"       — prefer transcripts, fall back to 8-K when none;
             "transcript" — transcripts only;
             "8k"         — 8-K press-release fallback only.
    limit  : max NEW scores this call (also bounded by cfg daily_cap).

    Returns the number of rows scored+upserted.  Never rescores a source_sha256
    already in the store.  Fail-open: returns 0 when there is nothing to score.
    """
    r = Path(root) if root is not None else _REPO_ROOT
    cfg = cfg if cfg is not None else load_config(r)
    cap = min(int(limit), int(cfg.get("daily_cap", 8)))
    if cap <= 0:
        return 0

    seen = _seen_shas(r)

    # Choose input iterators per source mode.
    inputs: list[tuple[dict, str]] = []
    have_transcripts = _transcripts_dir(r).is_dir() and any(
        _transcripts_dir(r).glob("*.json")
    )
    use_transcripts = source in ("auto", "transcript")
    use_8k = source == "8k" or (source == "auto" and not have_transcripts)

    if use_transcripts:
        for payload, text in _iter_transcript_inputs(r):
            inputs.append((payload, text))
            if len(inputs) >= cap * 4:  # over-collect; dedup filters below
                break

    # Fall back to 8-K only when transcripts didn't fill the batch.
    scored_rows: list[dict] = []
    n = 0
    for payload, text in inputs:
        if n >= cap:
            break
        sha = source_sha256(text)
        if sha in seen:
            continue
        row = score_text(
            text,
            payload.get("ticker", ""),
            payload.get("quarter"),
            payload.get("year"),
            provider_cfg=provider_cfg,
            cfg=cfg,
            call_date=payload.get("call_date"),
            source=payload.get("source", "transcript"),
            source_record_id=payload.get("source_record_id"),
            source_updated_at=payload.get("source_updated_at"),
        )
        seen.add(sha)
        scored_rows.append(row)
        n += 1

    if n < cap and use_8k:
        for payload, text in _iter_8k_inputs(r, limit=(cap - n) * 3):
            if n >= cap:
                break
            sha = source_sha256(text)
            if sha in seen:
                continue
            row = score_text(
                text,
                payload.get("ticker", ""),
                payload.get("quarter"),
                payload.get("year"),
                provider_cfg=provider_cfg,
                cfg=cfg,
                call_date=payload.get("call_date"),
                source="8k",
                source_record_id=payload.get("source_record_id"),
                source_updated_at=payload.get("source_updated_at"),
            )
            seen.add(sha)
            scored_rows.append(row)
            n += 1

    if not scored_rows:
        log.info("earnings_qual: score_new found nothing new to score (source=%s)", source)
        return 0

    written = upsert_scores(scored_rows, root=r)
    log.info("earnings_qual: score_new scored %d new row(s) → %s",
             written, store_path(r))
    return written


# =========================================================================== #
# SGA-2 W2 — Earnings-season / industry-heatmap / comparison / table surfaces
# =========================================================================== #
# These read the committed EquityDesk backfill seed
# (data/stage_analysis/backfill/earnings_calls.parquet — one row per
# company-quarter, full history 2019→now — and ec_industry.parquet) and, going
# forward, our own scores.parquet.  They emit the four Earnings-Calls surfaces
# the Stage-Analysis hub renders (masterplan §1 surface D + §2 engines #4/#5):
#
#   ec_industry_heatmap() -> data/stage_analysis/ec_industry.json
#       weekly per-GICS-industry {companies_with_fresh_ec, avg sent/perf/combined}
#       matched to their earnings_call_gics_industry_weekly.
#   earnings_season(q)    -> data/stage_analysis/earnings_season.json
#       per fiscal quarter Raisers (Δcombined > +5 QoQ) vs Decliners (< -5),
#       with per-industry allocation counts + level1/level2 tag-frequency cloud.
#   earnings_comparison() -> data/stage_analysis/earnings_compare.json
#       per ticker current-quarter combined+tags vs prior-quarter → delta_combined.
#   earnings_table()      -> data/stage_analysis/earnings_table.json
#       the per-call display rows (cap latest ~500; full set via R2/detail later).
#
# EPISTEMICS (SGA-R5): every artifact carries is_context_only + display_only.
# These are CONTEXT signals — the LLM earnings scores never gate, rank, or size.
# FAIL-OPEN: a missing / unreadable seed yields an empty-but-valid artifact; no
# path here can crash a build.  Atomic JSON writes (tmp + os.replace).
# --------------------------------------------------------------------------- #

# Calibration constant: reproducing their weekly "fresh EC" window.  Their
# earnings_call_gics_industry_weekly counts, per Friday week, the companies whose
# most-recent call falls inside a trailing window.  120 days is the window.
#
# MEASURED (region-aggregated (week, industry) join vs their table, ~1,900 rows;
# see tests/test_earnings_seasons.py::test_ec_industry_calibration):
#   - avg_earnings_call_combined tracks THEIRS at r ≈ 0.97 — the genuine fidelity
#     metric (the per-industry combined read is faithful).
#   - companies_with_fresh_ec count MAE ≈ 3.9 — NOT the ~1.0 previously claimed.
#     Our seed does not carry their per-region split, so we sum a name's fresh EC
#     across regions where their table splits it; that inflates our counts vs a
#     single-region cell. The count is a coarse volume proxy, not a matched read.
_EC_FRESH_WINDOW_DAYS = 120

# Season split thresholds (their Raisers Δ>5 / Decliners Δ<-5 on combined).
_SEASON_RAISER_DELTA = 5.0
_SEASON_DECLINER_DELTA = -5.0

_EARNINGS_TABLE_CAP = 500
# earnings_compare.json artifact budget: the full universe (~3.2k names) is ~2.5MB,
# over the ~1.2MB page budget. Cap to the top-N largest |delta_combined| movers
# (the most informative rows; the full set stays in the backfill / R2 detail lane).
_EARNINGS_COMPARE_CAP = 1500


def _sa_data_root(root: Path | None = None) -> Path:
    r = Path(root) if root is not None else _REPO_ROOT
    return r / "data" / "stage_analysis"


def _backfill_earnings_path(root: Path | None = None) -> Path:
    return _sa_data_root(root) / "backfill" / "earnings_calls.parquet"


def _backfill_earnings_candidates(root: Path | None = None) -> list[tuple[str, Path]]:
    """Ordered historical-call stores, strongest first.

    ``history.parquet`` is the canonical R2-transported migration of the full
    EquityDesk numeric/tag/highlight archive.  The two committed stores are
    deliberate cold-start fallbacks so a fresh checkout can never silently
    render a zero-row Earnings Calls tab merely because the R2 producer missed
    a run.  The overview fallback has one recent call per covered name; the
    compact score seed is the last-resort context lane.
    """
    r = Path(root) if root is not None else _REPO_ROOT
    return [
        ("r2_history", r / "data" / "earnings_calls" / "history.parquet"),
        ("legacy_full_history", _backfill_earnings_path(root)),
        (
            "committed_overview_fallback",
            _sa_data_root(root) / "backfill" / "equitydesk_overview.parquet",
        ),
        (
            "committed_score_seed_fallback",
            _sa_data_root(root) / "backfill" / "earnings_seed.parquet",
        ),
    ]


_STORE_HASH_CACHE: dict[tuple[str, int, int], str] = {}


def _store_md5(path: Path) -> str:
    """Content hash with a tiny stat-keyed cache (surfaces load the store often)."""
    stat = path.stat()
    key = (str(path), int(stat.st_mtime_ns), int(stat.st_size))
    cached = _STORE_HASH_CACHE.get(key)
    if cached:
        return cached
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    _STORE_HASH_CACHE.clear()
    _STORE_HASH_CACHE[key] = value
    return value


def _transport_manifest(root: Path | None = None) -> dict | None:
    r = Path(root) if root is not None else _REPO_ROOT
    path = r / "data" / "earnings_calls" / "manifest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _validate_transport_frame(
    frame,
    path: Path,
    block_name: str,
    root: Path | None = None,
) -> tuple[bool | None, str | None]:
    """Validate a fetched parquet against its generation manifest.

    ``None`` means a legacy/local fixture has no manifest.  ``False`` is an
    explicit contract failure and the caller must reject this R2 candidate.
    """
    # The commit marker lives beside the transported payload.  Prefer that
    # sibling path so validation remains correct whether callers pass a repo
    # root or a data-root fixture; fall back to the conventional repo layout.
    manifest = None
    sibling_manifest = path.parent / "manifest.json"
    if sibling_manifest.exists():
        try:
            payload = json.loads(sibling_manifest.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return False, "manifest_contract_invalid"
            manifest = payload
        except Exception as exc:  # noqa: BLE001
            return False, f"manifest_unreadable:{exc}"
    else:
        manifest = _transport_manifest(root)
    if manifest is None:
        return None, "manifest_absent"
    if manifest.get("schema") not in {
        "earnings_intelligence_manifest.v2",
        "earnings_intelligence_manifest.v3",
    }:
        return False, "manifest_schema_unsupported"
    scores_block = manifest.get("scores")
    history_block = manifest.get("history")
    if manifest.get("generation_id"):
        scores_md5 = (
            scores_block.get("md5") if isinstance(scores_block, dict) else ""
        )
        history_md5 = (
            history_block.get("md5") if isinstance(history_block, dict) else ""
        )
        material = f"{scores_md5 or ''}:{history_md5 or ''}"
        expected_generation = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
        if str(manifest.get("generation_id")) != expected_generation:
            return False, "manifest_generation_id_mismatch"
    if manifest.get("schema") == "earnings_intelligence_manifest.v3":
        for name, filename in (("scores", "scores.parquet"), ("history", "history.parquet")):
            candidate = manifest.get(name)
            if candidate is None:
                continue
            if not isinstance(candidate, dict):
                return False, f"manifest_{name}_block_invalid"
            key = str(candidate.get("key") or "")
            if (
                not key.startswith("earnings_calls/generations/")
                or not key.endswith(f"/{filename}")
            ):
                return False, f"manifest_{name}_immutable_key_invalid"
    reconciliation = manifest.get("reconciliation")
    if isinstance(reconciliation, dict):
        try:
            if int(reconciliation["input_rows"]) != (
                int(reconciliation["output_rows"])
                + int(reconciliation["rejected_rows"])
            ):
                return False, "manifest_reconciliation_arithmetic_mismatch"
        except (KeyError, TypeError, ValueError):
            return False, "manifest_reconciliation_counts_invalid"
    block = manifest.get(block_name)
    if not isinstance(block, dict):
        return False, f"manifest_{block_name}_block_absent"
    try:
        expected_md5 = str(block.get("md5") or "")
        if not expected_md5 or _store_md5(path) != expected_md5:
            return False, f"{block_name}_md5_mismatch"
        expected_bytes = block.get("bytes")
        if expected_bytes is not None and int(expected_bytes) != int(path.stat().st_size):
            return False, f"{block_name}_bytes_mismatch"
        expected_rows = block.get("rows")
        if expected_rows is not None and int(expected_rows) != int(len(frame)):
            return False, f"{block_name}_rows_mismatch"
        ticker_col = "ticker" if block_name == "scores" else "document_ticker"
        expected_tickers = block.get("tickers")
        if expected_tickers is not None and ticker_col in frame.columns:
            actual = int(frame[ticker_col].dropna().astype(str).nunique())
            if int(expected_tickers) != actual:
                return False, f"{block_name}_tickers_mismatch"
    except Exception as exc:  # noqa: BLE001
        return False, f"{block_name}_validation_error:{exc}"
    return True, None


def _clean_identity(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"", "NAN", "NONE", "<NA>"}:
        return ""
    return re.sub(r"\s+", " ", text)


def _display_ticker(value: Any) -> str:
    """Preserve the source listing ticker, removing only a redundant US token."""
    text = _clean_identity(value)
    parts = text.split()
    if len(parts) == 2 and parts[1] in {"US", "UN", "UW"}:
        return parts[0]
    return text


def _issuer_region(document_ticker: Any, company_ticker: Any) -> str:
    """Map an exchange-qualified listing to the page's five region buckets."""
    listing = _display_ticker(document_ticker)
    if re.search(r"\.(SS|SH|SZ|BJ)$", listing):
        return "CHINA"
    if listing.endswith(".HK"):
        return "HK"
    if re.search(r"\.(TO|V|CN|NE)$", listing):
        return "CANADA"
    if re.search(r"\.[A-Z]{1,4}$", listing):
        return "OTHER"
    company = _clean_identity(company_ticker)
    market = company.split()[-1] if " " in company else ""
    if market in {"US", "UN", "UW"}:
        return "US"
    if market == "CN":
        return "CANADA"
    if market == "HK":
        return "HK"
    return "OTHER" if market else "US"


def _add_earnings_identity_and_period(df):
    """Attach listing identity, issuer identity, region and validated fiscal period."""
    import pandas as pd  # noqa: PLC0415

    out = df.copy()
    documents = out.get("document_ticker", pd.Series("", index=out.index))
    companies = out.get("company_ticker", pd.Series("", index=out.index))
    out["ticker"] = documents.map(_display_ticker)
    company_keys = companies.map(_clean_identity)
    fallback_keys = out["ticker"].map(lambda value: f"DOC:{value}" if value else "")
    out["issuer_key"] = company_keys.where(company_keys.ne(""), fallback_keys)
    out["region"] = [
        _issuer_region(document, company)
        for document, company in zip(documents, companies)
    ]

    raw_year = out.get("fiscal_year", pd.Series(None, index=out.index))
    raw_quarter = out.get("fiscal_quarter", pd.Series(None, index=out.index))
    fiscal_year = pd.to_numeric(raw_year, errors="coerce")
    fiscal_quarter = pd.to_numeric(raw_quarter, errors="coerce")
    # Producer rows conventionally use ``Q1``..``Q4`` (and some upstream
    # feeds spell years as ``FY2026``), while the historical archive stores
    # integers.  Normalize both representations before validating the period.
    quarter_text = raw_quarter.astype("string").str.extract(
        r"(?i)^\s*Q?([1-4])\s*$", expand=False,
    )
    year_text = raw_year.astype("string").str.extract(
        r"(?i)^\s*(?:FY)?(\d{4})\s*$", expand=False,
    )
    fiscal_quarter = fiscal_quarter.fillna(pd.to_numeric(quarter_text, errors="coerce"))
    fiscal_year = fiscal_year.fillna(pd.to_numeric(year_text, errors="coerce"))
    call_year = out["call_dt"].dt.year
    present = fiscal_year.notna() | fiscal_quarter.notna()
    valid = (
        fiscal_year.notna()
        & fiscal_quarter.between(1, 4)
        & call_year.notna()
        # Earnings-call fiscal labels in the observed archive live in a clean
        # call-year +/-1 band. Wider offsets are stale/copied source revisions
        # (for example a 2026 call mislabeled 2023Q1) and can manufacture
        # adjacent-but-temporally-impossible QoQ pairs.
        & fiscal_year.between(call_year - 1, call_year + 1)
    )
    out["fiscal_period"] = None
    out.loc[valid, "fiscal_period"] = (
        fiscal_year[valid].astype("Int64").astype(str)
        + "Q"
        + fiscal_quarter[valid].astype("Int64").astype(str)
    )
    out["fiscal_period_order"] = None
    out.loc[valid, "fiscal_period_order"] = (
        fiscal_year[valid] * 4 + fiscal_quarter[valid]
    ).astype("Int64")
    out["invalid_fiscal_period"] = present & ~valid
    out["missing_fiscal_period"] = ~present
    return out


def _quarterly_earnings_frame(df):
    """One deterministic call per exact issuer and valid fiscal period."""
    import pandas as pd  # noqa: PLC0415

    if df.empty:
        return df.copy()
    d = df[
        df["issuer_key"].astype(str).str.strip().ne("")
        & df["fiscal_period"].notna()
        & df["call_dt"].notna()
    ].copy()
    if d.empty:
        return d
    for col in ("updated_at", "created_at"):
        raw = d[col] if col in d.columns else pd.Series(None, index=d.index)
        d[f"_{col}_dt"] = pd.to_datetime(raw, utc=True, errors="coerce")
    d["_row_id"] = d.get("id", pd.Series("", index=d.index)).fillna("").astype(str)
    d = d.sort_values(
        [
            "issuer_key", "fiscal_period_order", "call_dt", "_updated_at_dt",
            "_created_at_dt", "_row_id", "ticker",
        ],
        kind="mergesort",
        na_position="first",
    ).drop_duplicates(["issuer_key", "fiscal_period"], keep="last")
    return d.drop(columns=["_updated_at_dt", "_created_at_dt", "_row_id"])


def _atomic_write_json(path: Path, obj: Any) -> None:
    """Write JSON via tmp-then-rename (atomic on POSIX).  Never partial."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _json_safe(obj: Any) -> Any:
    """Coerce numpy / NaN scalars to plain JSON-safe Python (recursive)."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (bool, str, int)) or obj is None:
        return obj
    if isinstance(obj, float):
        return None if (obj != obj or obj in (float("inf"), float("-inf"))) else obj
    try:
        import numpy as np  # noqa: PLC0415
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            f = float(obj)
            return None if (f != f) else f
    except Exception:  # noqa: BLE001
        pass
    try:
        f = float(obj)
        return None if (f != f) else f
    except Exception:  # noqa: BLE001
        return str(obj)


def _context_envelope(surface: str, extra: dict | None = None) -> dict:
    """Shared display-tier envelope — every artifact stamps these (SGA-R5)."""
    env = {
        "surface": surface,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_context_only": True,   # SGA-R5 — never gates / ranks / sizes
        "display_only": True,
        "source": "equitydesk_backfill_seed + our earnings scores",
    }
    if extra:
        env.update(extra)
    return env


def _scrub_tag_list(tags: list[str]) -> list[str]:
    """Advice-scrub each tag string (shared scrubber), dropping any that scrub to
    empty. Tags reach a user surface, so they get the same treatment as free
    text — even though the pinned taxonomy is advice-free, seed level1/level2
    tags are free-form and untrusted."""
    out: list[str] = []
    for t in tags:
        s = _scrub_advice_text(t)
        if s:
            out.append(s)
    return out


def _parse_tag_list(raw: Any) -> list[str]:
    """Coerce a tags cell (JSON-string, list, or None) into a list[str]."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw if isinstance(t, (str, int, float)) and str(t).strip()]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return [str(t) for t in v if str(t).strip()]
        except Exception:  # noqa: BLE001
            # comma-separated fallback
            return [t.strip() for t in s.split(",") if t.strip()]
    return []


def _normalise_earnings_source(df, source_tier: str, root: Path | None = None):
    """Project any supported cold-start store into the full-history schema."""
    import pandas as pd  # noqa: PLC0415

    out = df.copy()

    if source_tier == "committed_score_seed_fallback":
        # Reverse the documented EquityDesk->our-score calibration used by
        # scripts/import_equitydesk_backfill.py.  This keeps the legacy Stage
        # Analysis display scale (sent 0..30, perf -12..12) consistent.
        sent = pd.to_numeric(out.get("sentiment"), errors="coerce")
        perf = pd.to_numeric(out.get("performance"), errors="coerce")
        ticker = out.get("ticker", pd.Series("", index=out.index)).astype(str).str.upper()
        projected = pd.DataFrame(index=out.index)
        projected["document_ticker"] = ticker
        projected["company_ticker"] = ticker
        projected["company_name"] = ticker
        projected["id"] = None
        projected["created_at"] = out.get("scored_at")
        projected["updated_at"] = out.get("scored_at")
        projected["fiscal_quarter"] = out.get("quarter")
        projected["fiscal_year"] = out.get("year")
        projected["call_date"] = out.get("call_date")
        projected["earnings_call_sent"] = (sent * 18.0 + 12.0).clip(0.0, 30.0)
        projected["earnings_call_perf"] = (perf * 2.4 - 12.0).clip(-12.0, 12.0)
        projected["earnings_call_combined"] = (
            projected["earnings_call_sent"] + projected["earnings_call_perf"]
        )
        projected["level1_tags"] = out.get("tags")
        projected["level2_tags"] = None
        projected["key_quote"] = out.get("summary")
        projected["positive_highlights"] = None
        projected["negative_highlights"] = None
        projected["file_path"] = None
        out = projected

        # Enrich the compact seed with the committed issuer/GICS dictionary.
        ov = _sa_data_root(root) / "backfill" / "equitydesk_overview.parquet"
        if ov.exists():
            try:
                meta = pd.read_parquet(
                    ov,
                    columns=[
                        "ticker", "name_ui", "gics_sector", "gics_industry_group",
                        "gics_industry", "gics_sub_industry",
                    ],
                ).drop_duplicates("ticker", keep="last")
                meta["document_ticker"] = meta["ticker"].astype(str).str.upper()
                meta = meta.drop(columns=["ticker"]).rename(
                    columns={
                        "name_ui": "_company_name",
                        "gics_sub_industry": "gics_subindustry",
                    }
                )
                out = out.merge(meta, on="document_ticker", how="left")
                out["company_name"] = out["_company_name"].fillna(out["company_name"])
                out = out.drop(columns=["_company_name"])
            except Exception as exc:  # noqa: BLE001
                log.warning("earnings_qual: score-seed metadata join failed (%s)", exc)

    elif source_tier == "committed_overview_fallback":
        # The overview parquet now also accrues nightly ENGINE stage snapshots
        # (source="stage_engine", no earnings fields) — only the vendor seed
        # rows are earnings evidence here.
        if "source" in out.columns:
            out = out[
                out["source"].fillna("equitydesk_backfill") != "stage_engine"
            ].copy()
        ticker = out.get("ticker", pd.Series("", index=out.index)).astype(str).str.upper()
        out["document_ticker"] = ticker
        out["company_ticker"] = ticker
        if "company_name" not in out.columns:
            out["company_name"] = out.get("name_ui", ticker)
        else:
            out["company_name"] = out["company_name"].fillna(out.get("name_ui"))
        if "gics_subindustry" not in out.columns:
            out["gics_subindustry"] = out.get("gics_sub_industry")
        out["fiscal_quarter"] = None
        out["fiscal_year"] = None
        out["key_quote"] = None
        out["file_path"] = None

    return out


def _frame_metadata(df) -> dict:
    """Small provenance/readiness block carried by every earnings artifact."""
    import pandas as pd  # noqa: PLC0415

    source_tier = str(df.attrs.get("source_tier") or "none")
    latest = None
    if not df.empty and "call_dt" in df.columns:
        mx = df["call_dt"].max()
        if pd.notna(mx):
            latest = pd.Timestamp(mx).date().isoformat()
    n_listings = (
        int(df["ticker"].replace("", None).dropna().nunique())
        if not df.empty and "ticker" in df.columns else 0
    )
    n_issuers = (
        int(df["issuer_key"].replace("", None).dropna().nunique())
        if not df.empty and "issuer_key" in df.columns else 0
    )
    invalid_fiscal = (
        int(df["invalid_fiscal_period"].fillna(False).sum())
        if not df.empty and "invalid_fiscal_period" in df.columns else 0
    )
    missing_fiscal = (
        int(df["missing_fiscal_period"].fillna(False).sum())
        if not df.empty and "missing_fiscal_period" in df.columns else 0
    )
    reconciliation = df.attrs.get("import_reconciliation")
    if not isinstance(reconciliation, dict):
        reconciliation = {}
    if df.empty:
        status = "empty"
    elif source_tier in {
        "r2_history",
        "r2_history_plus_score_overlay",
        "legacy_full_history",
        "legacy_full_history_plus_score_overlay",
    }:
        status = "ready"
    else:
        status = "degraded"
    if status == "ready" and latest:
        try:
            age_days = (
                pd.Timestamp.now(tz="UTC").date() - pd.Timestamp(latest).date()
            ).days
            if age_days > 14:
                status = "stale"
        except Exception:  # noqa: BLE001
            pass
    return {
        "data_status": status,
        "data_source_tier": source_tier,
        "source_rows": int(len(df)),
        # Backward-compatible name: this is listing coverage (document_ticker),
        # not canonical issuer coverage.  Both are exposed to prevent the old
        # 3,529-vs-3,496 distinction from being mislabeled as data loss.
        "source_tickers": n_listings,
        "source_listings": n_listings,
        "source_issuers": n_issuers,
        "invalid_fiscal_period_rows": invalid_fiscal,
        "missing_fiscal_period_rows": missing_fiscal,
        "import_input_rows": reconciliation.get("input_rows"),
        "import_output_rows": reconciliation.get("output_rows"),
        "import_rejected_rows": reconciliation.get("rejected_rows"),
        "import_duplicate_groups": reconciliation.get("duplicate_group_count"),
        "transport_manifest_valid": df.attrs.get("transport_manifest_valid"),
        "transport_generation_id": df.attrs.get("transport_generation_id"),
        "latest_call_date": latest,
    }


def _overlay_forward_scores(df, source_tier: str, root: Path | None = None):
    """Append post-migration score rows that are absent from call history.

    The imported history is a calibration/backfill snapshot.  The existing
    producer lane continues to advance ``scores.parquet`` from newly collected
    transcripts or 8-K text.  Without this overlay, a healthy score producer
    could publish a newer call while the Stage surfaces stayed frozen at the
    migration cutoff forever.

    History wins for matching ticker/date pairs; the score projection is used
    only for genuinely new events and remains display/context-only.
    """
    import pandas as pd  # noqa: PLC0415

    if source_tier not in {"r2_history", "legacy_full_history"}:
        return df, source_tier
    r = Path(root) if root is not None else _REPO_ROOT
    scores_path = r / "data" / "earnings_calls" / "scores.parquet"
    if not scores_path.exists():
        return df, source_tier
    try:
        scores = pd.read_parquet(scores_path)
        if scores.empty:
            return df, source_tier
        score_valid, score_reason = _validate_transport_frame(
            scores, scores_path, "scores", root=root,
        )
        if score_valid is False:
            log.warning(
                "earnings_qual: rejecting score overlay (%s)", score_reason,
            )
            return df, source_tier
        # Provider failures and partial JSON are retry receipts, not calls that
        # earned a product surface. Apply the same health/context/completeness
        # gate as stage_analysis before normalization or the latest-500 cap.
        if "degraded_reason" in scores.columns:
            degraded = scores["degraded_reason"].fillna("").astype(str).str.strip()
            scores = scores[degraded.eq("")]
        if "is_context_only" in scores.columns:
            context = scores["is_context_only"]
            context_ok = context.map(
                lambda value: (
                    str(value).strip().lower() in {"1", "true", "yes", "y"}
                    if isinstance(value, str)
                    else bool(value) if value is not None and not pd.isna(value) else False
                )
            )
            scores = scores[context_ok]
        if "call_date" in scores.columns:
            # Defense in depth: even if a producer bug or manually published
            # parquet bypasses the worker quarantine, a future-labelled call
            # cannot enter the Stage/product projection.
            score_days = pd.to_datetime(
                scores["call_date"], errors="coerce", utc=True,
            )
            today = datetime.now(timezone.utc).date()
            scores = scores[score_days.notna() & score_days.dt.date.le(today)]
        for required in ("sentiment", "performance"):
            if required not in scores.columns:
                return df, source_tier
            scores = scores[pd.to_numeric(scores[required], errors="coerce").notna()]
        if scores.empty:
            return df, source_tier
        projected = _normalise_earnings_source(
            scores,
            "committed_score_seed_fallback",
            root=root,
        )
        # Preserve the canonical issuer key for known listings.  The score
        # contract carries a listing ticker, while history carries the exact
        # Bloomberg-style company ticker (e.g. CLS CN vs CLS SJ).
        issuer_map = (
            df[["document_ticker", "company_ticker"]]
            .dropna(subset=["document_ticker"])
            .drop_duplicates("document_ticker", keep="last")
            .set_index("document_ticker")["company_ticker"]
        )
        projected["company_ticker"] = (
            projected["document_ticker"].map(issuer_map)
            .fillna(projected["company_ticker"])
        )
        base_ticker = (
            df.get("document_ticker", pd.Series("", index=df.index))
            .map(_display_ticker)
        )
        score_ticker = (
            projected.get("document_ticker", pd.Series("", index=projected.index))
            .map(_display_ticker)
        )
        base_date = pd.to_datetime(df.get("call_date"), errors="coerce").dt.date.astype(str)
        score_date = pd.to_datetime(
            projected.get("call_date"), errors="coerce"
        ).dt.date.astype(str)
        base_keys = set((base_ticker + "|" + base_date).tolist())
        keep = ~((score_ticker + "|" + score_date).isin(base_keys))
        keep &= score_ticker.ne("") & score_date.ne("NaT")
        additions = projected.loc[keep]
        if additions.empty:
            return df, source_tier
        out = pd.concat([df, additions], ignore_index=True, sort=False)
        return out, f"{source_tier}_plus_score_overlay"
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings_qual: forward score overlay failed (%s)", exc)
        return df, source_tier


def load_backfill_earnings(root: Path | None = None):
    """Load the committed EquityDesk earnings backfill as a normalized frame.

    Returns a DataFrame with a coerced ``call_dt`` (datetime) and a canonical
    ``calendar_quarter`` (e.g. ``2026Q2``) plus parsed tag lists.  Empty (with
    the expected columns) when the seed is absent / unreadable — fail-open.
    """
    import pandas as pd  # noqa: PLC0415

    cols = [
        "id", "created_at", "updated_at", "document_ticker", "company_ticker",
        "company_name", "fiscal_quarter",
        "fiscal_year", "call_date", "gics_sector", "gics_industry_group",
        "gics_industry", "gics_subindustry", "earnings_call_sent",
        "earnings_call_perf", "earnings_call_combined", "earnings_call_pop",
        "positive_highlights", "negative_highlights", "key_quote",
        "level1_tags", "level2_tags", "file_path",
    ]
    df = None
    source_tier = "none"
    source_path = None
    for tier, p in _backfill_earnings_candidates(root):
        if not p.exists():
            continue
        try:
            candidate = pd.read_parquet(p)
        except Exception as exc:  # noqa: BLE001
            log.warning("earnings_qual: %s unreadable (%s) — trying fallback", p, exc)
            continue
        if candidate.empty:
            log.warning("earnings_qual: %s is empty — trying fallback", p)
            continue
        transport_valid = None
        transport_reason = None
        if tier == "r2_history":
            transport_valid, transport_reason = _validate_transport_frame(
                candidate, p, "history", root=root,
            )
            if transport_valid is not True:
                log.warning(
                    "earnings_qual: rejecting unmanifested/mixed R2 history (%s) — "
                    "trying committed fallback",
                    transport_reason,
                )
                continue
        df = _normalise_earnings_source(candidate, tier, root=root)
        source_tier = tier
        source_path = p
        manifest = _transport_manifest(root) if tier == "r2_history" else None
        df.attrs.update(
            transport_manifest_valid=transport_valid,
            transport_manifest_reason=transport_reason,
            transport_generation_id=(manifest or {}).get("generation_id"),
            import_reconciliation=(manifest or {}).get("reconciliation"),
        )
        break

    if df is None or df.empty:
        empty = pd.DataFrame(columns=cols + [
            "call_dt", "calendar_quarter", "ticker", "issuer_key", "region",
            "fiscal_period", "fiscal_period_order", "invalid_fiscal_period",
            "missing_fiscal_period",
        ])
        empty.attrs.update(source_tier="none", source_path=None)
        return empty

    transport_attrs = dict(df.attrs)
    df, source_tier = _overlay_forward_scores(df, source_tier, root=root)
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df["call_dt"] = pd.to_datetime(df.get("call_date"), errors="coerce")
    # Canonical, dirty-value-proof quarter key: the CALENDAR quarter of the call
    # (their fiscal_year has occasional dirty entries like 2925; call_date is the
    # trustworthy anchor and aligns for the vast majority of names).
    q = df["call_dt"].dt.quarter
    y = df["call_dt"].dt.year
    df["calendar_quarter"] = (
        y.astype("Int64").astype(str) + "Q" + q.astype("Int64").astype(str)
    )
    df.loc[df["call_dt"].isna(), "calendar_quarter"] = None
    df = _add_earnings_identity_and_period(df)
    df.attrs.update(transport_attrs)
    df.attrs.update(source_tier=source_tier, source_path=str(source_path))
    return df


def _latest_quarters(df, n: int = 4) -> list[str]:
    """The latest `n` calendar-quarter keys present, ordered newest→oldest,
    restricted to quarters with a non-trivial call count (avoids a barely-begun
    quarter dominating)."""
    import pandas as pd  # noqa: PLC0415
    if df.empty or "calendar_quarter" not in df.columns:
        return []
    counts = df["calendar_quarter"].dropna().value_counts()
    # sortable key: (year, q)
    def _key(qk: str):
        try:
            yy, qq = qk.split("Q")
            return (int(yy), int(qq))
        except Exception:  # noqa: BLE001
            return (0, 0)
    ordered = sorted(counts.index, key=_key, reverse=True)
    return ordered[:n]


# --------------------------------------------------------------------------- #
# Surface #1 — EC industry heatmap (weekly per-GICS-industry)
# --------------------------------------------------------------------------- #
def ec_industry_heatmap(
    root: Path | None = None,
    *,
    weeks: int = 26,
    window_days: int = _EC_FRESH_WINDOW_DAYS,
    region: str | None = None,
    frame=None,
    write: bool = True,
) -> dict:
    """Weekly per-GICS-industry earnings-call heatmap.

    For each Friday week over the trailing `weeks`, and each GICS industry, count
    the companies whose MOST-RECENT call falls inside a `window_days` trailing
    window and average their EC sent / perf / combined.  Mirrors their
    ``earnings_call_gics_industry_weekly`` (MEASURED vs their table: combined
    r≈0.97 — faithful; count MAE≈3.9 — a coarse volume proxy, not a matched read,
    because our seed lacks their per-region split.  See ::test_ec_industry_calibration).

    Emits data/stage_analysis/ec_industry.json.  Fail-open + display-tier.
    """
    import pandas as pd  # noqa: PLC0415

    df = frame if frame is not None else load_backfill_earnings(root)
    weeks_out: list[dict] = []
    industries: set[str] = set()

    if not df.empty:
        d = df.dropna(subset=["call_dt", "gics_industry"]).copy()
        if region is not None:
            d = d[d["region"] == str(region).upper()]
        d = d[d["gics_industry"].astype(str).str.strip() != ""]
        if not d.empty:
            last = d["call_dt"].max()
            # Anchor weeks on Fridays (their as_of convention: weekday == 4).
            # Round the latest call UP to its week-ending Friday so a call landing
            # Mon–Fri is captured by that week (rounding down would orphan it).
            last_fri = last + pd.Timedelta(days=(4 - last.weekday()) % 7)
            fridays = [last_fri - pd.Timedelta(weeks=w) for w in range(weeks)]
            fridays = [f for f in fridays if pd.notna(f)]
            for fri in sorted(fridays):
                lo = fri - pd.Timedelta(days=window_days)
                win = d[(d["call_dt"] <= fri) & (d["call_dt"] > lo)]
                if win.empty:
                    continue
                # Latest call per company inside the window.
                latest = (
                    win.sort_values("call_dt")
                    .groupby("issuer_key", as_index=False)
                    .tail(1)
                )
                g = latest.groupby("gics_industry").agg(
                    companies_with_fresh_ec=("issuer_key", "nunique"),
                    avg_earnings_call_sent=("earnings_call_sent", "mean"),
                    avg_earnings_call_perf=("earnings_call_perf", "mean"),
                    avg_earnings_call_combined=("earnings_call_combined", "mean"),
                )
                for ind, r in g.iterrows():
                    industries.add(str(ind))
                    weeks_out.append({
                        "week": fri.date().isoformat(),
                        "as_of_date": fri.date().isoformat(),
                        "gics_industry": str(ind),
                        "companies_with_fresh_ec": int(r["companies_with_fresh_ec"]),
                        "avg_earnings_call_sent": round(float(r["avg_earnings_call_sent"]), 3),
                        "avg_earnings_call_perf": round(float(r["avg_earnings_call_perf"]), 3),
                        "avg_earnings_call_combined": round(float(r["avg_earnings_call_combined"]), 3),
                    })

    out = _context_envelope("ec_industry_heatmap", {
        **_frame_metadata(df),
        "window_days": int(window_days),
        "n_weeks": len({r["week"] for r in weeks_out}),
        "n_industries": len(industries),
        "rows": _json_safe(weeks_out),
    })
    if write:
        _atomic_write_json(_sa_data_root(root) / "ec_industry.json", out)
    return out


# --------------------------------------------------------------------------- #
# Surface #1b — EC industry heatmap GRID (per-region, matrix form)
# --------------------------------------------------------------------------- #
# The `ec_industry_heatmap` above emits a long-format list (one row per
# week×industry cell) from earnings_calls.parquet with an exchange-derived
# five-bucket region split.
# This grid form reads the EquityDesk seed ec_industry.parquet directly — it
# carries their per-region GICS-industry weekly aggregates
# (avg_earnings_call_combined + companies_with_fresh_ec) — and reshapes them
# into the matrix the Industries surface renders as a heatmap: rows = GICS
# industries, columns = trailing Friday weeks (most-recent first), cells =
# {combined, count}. DISPLAY-TIER / CONTEXT-ONLY.

_EC_GRID_REGIONS = ("USA", "EUROPE", "ASIA")


def _ec_industry_seed_path(root: Path | None = None) -> Path:
    return _sa_data_root(root) / "backfill" / "ec_industry.parquet"


def ec_industry_heatmap_grid(
    root: Path | None = None,
    *,
    weeks: int = 26,
    max_rows: int = 90,
    write: bool = True,
) -> dict:
    """Per-region EC combined-sentiment grid from the EquityDesk seed.

    Returns a display-tier envelope with ``regions`` = {region: {
        weeks:[Friday dates, most-recent first],
        rows:[{industry, cells:[{combined, count}|null per week]}],
        n_industries, n_weeks}}. Rows are ordered by the most-recent week's
    combined score (highest first). ``cells[]`` is aligned to ``weeks[]`` with
    ``null`` where an industry has no fresh-EC read that week. Fail-open: a
    missing/unreadable seed yields empty ``regions`` (page shows a warm state).

    Emits data/stage_analysis/ec_industry_heatmap.json.
    """
    import pandas as pd  # noqa: PLC0415

    regions_out: dict[str, dict] = {}
    grid_source_tier = "none"
    source_frame = None
    p = _ec_industry_seed_path(root)
    if p.exists():
        try:
            df = pd.read_parquet(
                p, columns=["as_of_date", "region", "gics_industry_name",
                            "companies_with_fresh_ec",
                            "avg_earnings_call_combined"])
        except Exception as exc:  # noqa: BLE001
            # Bare print, NOT a logger call: GitHub only parses a workflow command when
            # "::" STARTS the line, and this module's logging format prefixes every
            # record (e.g. "WARNING ::warning ..."), which silently drops the annotation.
            print(f"::warning:: earnings_qual: ec grid seed unreadable ({exc})", flush=True)
            df = pd.DataFrame()
        if not df.empty:
            try:
                df = df.assign(dt_=pd.to_datetime(df["as_of_date"], errors="coerce"))
                df = df.dropna(subset=["dt_", "gics_industry_name"])
                for reg in _EC_GRID_REGIONS:
                    sub = df[df["region"] == reg]
                    if sub.empty:
                        continue
                    grid = _ec_grid_region(sub, weeks=weeks, max_rows=max_rows)
                    if grid is not None:
                        regions_out[reg] = grid
                if regions_out:
                    grid_source_tier = "committed_ec_industry_seed"
            except Exception as exc:  # noqa: BLE001
                print(f"::warning:: earnings_qual: ec grid build failed ({exc})", flush=True)

    # When the old per-region seed is absent, derive exact five-bucket grids
    # from the exchange-qualified historical archive.  This both prevents a
    # permanent warm state and avoids the old error of labeling every foreign
    # call as USA.
    if not regions_out:
        source_frame = load_backfill_earnings(root)
        if not source_frame.empty:
            for region_code, output_key in (
                ("US", "USA"),
                ("CHINA", "CHINA"),
                ("HK", "HK"),
                ("CANADA", "CANADA"),
                ("OTHER", "OTHER"),
            ):
                long_view = ec_industry_heatmap(
                    root=root,
                    weeks=weeks,
                    region=region_code,
                    frame=source_frame,
                    write=False,
                )
                rows = long_view.get("rows") or []
                if not rows:
                    continue
                fallback = pd.DataFrame(rows).rename(
                    columns={"gics_industry": "gics_industry_name"}
                )
                # The long view intentionally carries both aliases; select one
                # rather than renaming ``week`` into a duplicate column.
                fallback["as_of_date"] = fallback["week"]
                fallback["dt_"] = pd.to_datetime(
                    fallback["as_of_date"], errors="coerce"
                )
                grid = _ec_grid_region(fallback, weeks=weeks, max_rows=max_rows)
                if grid is not None:
                    regions_out[output_key] = grid
            if regions_out:
                grid_source_tier = str(
                    source_frame.attrs.get("source_tier") or "history_fallback"
                )

    if source_frame is not None:
        grid_meta = _frame_metadata(source_frame)
    elif regions_out:
        grid_meta = {
            "data_status": "ready",
            "data_source_tier": grid_source_tier,
            "source_rows": None,
            "source_tickers": None,
            "latest_call_date": None,
        }
    else:
        grid_meta = {
            "data_status": "empty",
            "data_source_tier": "none",
            "source_rows": 0,
            "source_tickers": 0,
            "latest_call_date": None,
        }

    out = _context_envelope("ec_industry_heatmap_grid", {
        **grid_meta,
        "n_regions": len(regions_out),
        "regions": _json_safe(regions_out),
    })
    if write:
        _atomic_write_json(_sa_data_root(root) / "ec_industry_heatmap.json", out)
    return out


def _ec_grid_region(sub, *, weeks: int, max_rows: int) -> dict | None:
    """Build one region's EC grid. `sub` = rows for a single region."""
    import pandas as pd  # noqa: PLC0415

    all_weeks = sorted(sub["dt_"].dropna().unique())
    if not all_weeks:
        return None
    keep = all_weeks[-weeks:]
    week_labels = [pd.Timestamp(w).date().isoformat() for w in reversed(keep)]
    keep_set = set(keep)
    win = sub[sub["dt_"].isin(keep_set)].sort_values("dt_")

    # {industry: {week: {combined, count}}} — last write wins on dup cells.
    cells_by_ind: dict[str, dict] = {}
    for row in win.itertuples():
        ind = str(row.gics_industry_name).strip()
        if not ind or ind.lower() == "nan":
            continue
        wk = pd.Timestamp(row.dt_).date().isoformat()
        combined = row.avg_earnings_call_combined
        try:
            combined = None if combined != combined else round(float(combined), 2)
        except (TypeError, ValueError):
            combined = None
        try:
            count = int(row.companies_with_fresh_ec)
        except (TypeError, ValueError):
            count = 0
        cells_by_ind.setdefault(ind, {})[wk] = {"combined": combined, "count": count}

    if not cells_by_ind:
        return None

    latest = week_labels[0]

    def _sort_key(ind: str):
        cell = cells_by_ind[ind].get(latest)
        if cell is not None and cell.get("combined") is not None:
            return (0, -cell["combined"])
        # Industries missing the latest week fall to the bottom, ordered by the
        # most recent combined they DO have.
        best = None
        for wk in week_labels:
            c = cells_by_ind[ind].get(wk)
            if c and c.get("combined") is not None:
                best = c["combined"]
                break
        return (1, -(best if best is not None else -1e9))

    ordered = sorted(cells_by_ind.keys(), key=_sort_key)[:max_rows]
    rows = [{
        "industry": ind,
        "cells": [cells_by_ind[ind].get(wk) for wk in week_labels],
    } for ind in ordered]

    return {
        "weeks": week_labels,
        "rows": rows,
        "n_industries": len(rows),
        "n_weeks": len(week_labels),
    }


# --------------------------------------------------------------------------- #
# Surface #2 — Earnings season (per fiscal quarter Raisers / Decliners)
# --------------------------------------------------------------------------- #
def _tag_frequency(rows, col: str, top: int = 25) -> list[dict]:
    """Tag-frequency cloud for a set of call rows on a tag column."""
    from collections import Counter
    c: Counter = Counter()
    for _, r in rows.iterrows():
        for t in _parse_tag_list(r.get(col)):
            c[t] += 1
    return [{"tag": t, "count": int(n)} for t, n in c.most_common(top)]


def _industry_allocation(rows, top: int = 20) -> list[dict]:
    """Per-industry count allocation for a set of call rows."""
    if rows.empty:
        return []
    g = rows.groupby("gics_industry").size().sort_values(ascending=False)
    return [{"gics_industry": str(k), "count": int(v)} for k, v in g.head(top).items()]


def earnings_season(
    quarter: str | None = None,
    root: Path | None = None,
    *,
    n_quarters: int = 4,
    write: bool = True,
) -> dict:
    """Per fiscal (calendar-anchored) quarter, split names into Raisers vs
    Decliners by QoQ change in combined score.

    A name is a Raiser when its combined rose > +5 vs its immediately-prior call,
    a Decliner when it fell < -5 (their thresholds).  Each side carries an
    industry-allocation count list and a level1/level2 tag-frequency cloud.

    `quarter` restricts output to a single quarter key (e.g. ``2026Q2``); when
    None, the latest `n_quarters` are emitted.  Writes earnings_season.json.
    """
    import pandas as pd  # noqa: PLC0415

    df = load_backfill_earnings(root)
    quarters_out: list[dict] = []

    if not df.empty:
        d = _quarterly_earnings_frame(df)
        d = d.dropna(subset=["call_dt", "calendar_quarter", "fiscal_period"]).copy()
        d = d[pd.to_numeric(d["earnings_call_combined"], errors="coerce").notna()]
        if not d.empty:
            # Prior combined = the same exact issuer's prior VALID fiscal period.
            # Multiple vendor rows/listings inside one fiscal period have already
            # been deterministically reduced by _quarterly_earnings_frame.
            d = d.sort_values(["issuer_key", "fiscal_period_order", "call_dt"])
            grouped = d.groupby("issuer_key", sort=False)
            d["prev_combined"] = grouped["earnings_call_combined"].shift(1)
            d["prev_period_order"] = grouped["fiscal_period_order"].shift(1)
            adjacent = (
                pd.to_numeric(d["fiscal_period_order"], errors="coerce")
                - pd.to_numeric(d["prev_period_order"], errors="coerce")
            ).eq(1)
            # QoQ is literal here: a 2026Q2 row may compare only with 2026Q1,
            # never with the merely previous stored call (for example 2025Q4).
            d.loc[~adjacent, "prev_combined"] = None
            current_combined = pd.to_numeric(
                d["earnings_call_combined"], errors="coerce",
            )
            prior_combined = pd.to_numeric(d["prev_combined"], errors="coerce")
            d["delta_combined"] = current_combined - prior_combined
            # The imported archive uses exact combined==0 as an UNSCORED /
            # missing-call placeholder, not a real tone reading. Apply the same
            # both-quarters-scored gate as earnings_comparison so false 0-vs-35
            # deltas never inflate Season counts or tag clouds.
            both_scored = (
                current_combined.notna()
                & prior_combined.notna()
                & current_combined.ne(0)
                & prior_combined.ne(0)
            )
            d.loc[~both_scored, "delta_combined"] = None
            want = [quarter] if quarter else _latest_quarters(d, n_quarters)
            for qk in want:
                qd = d[d["calendar_quarter"] == qk]
                if qd.empty:
                    continue
                scored = qd.dropna(subset=["delta_combined"])
                raisers = scored[scored["delta_combined"] > _SEASON_RAISER_DELTA]
                decliners = scored[scored["delta_combined"] < _SEASON_DECLINER_DELTA]
                quarters_out.append({
                    "quarter": qk,
                    "n_calls": int(len(qd)),
                    "n_scored_qoq": int(len(scored)),
                    "raisers": {
                        "count": int(len(raisers)),
                        "median_delta": round(float(raisers["delta_combined"].median()), 3)
                        if len(raisers) else None,
                        "industry_allocation": _industry_allocation(raisers),
                        "level1_tags": _tag_frequency(raisers, "level1_tags"),
                        "level2_tags": _tag_frequency(raisers, "level2_tags"),
                    },
                    "decliners": {
                        "count": int(len(decliners)),
                        "median_delta": round(float(decliners["delta_combined"].median()), 3)
                        if len(decliners) else None,
                        "industry_allocation": _industry_allocation(decliners),
                        "level1_tags": _tag_frequency(decliners, "level1_tags"),
                        "level2_tags": _tag_frequency(decliners, "level2_tags"),
                    },
                })

    out = _context_envelope("earnings_season", {
        **_frame_metadata(df),
        "n_quarters": len(quarters_out),
        "quarters": _json_safe(quarters_out),
    })
    if write:
        _atomic_write_json(_sa_data_root(root) / "earnings_season.json", out)
    return out


# --------------------------------------------------------------------------- #
# Surface #3 — Earnings comparison (per ticker current vs prior quarter)
# --------------------------------------------------------------------------- #
def earnings_comparison(
    root: Path | None = None,
    *,
    cap: int = _EARNINGS_COMPARE_CAP,
    write: bool = True,
) -> dict:
    """Per ticker: current-quarter combined + tags vs prior-quarter combined +
    tags → ``delta_combined``.  One row per name (its two most-recent calls).

    Capped to the top `cap` rows by |delta_combined| (largest movers — the most
    informative; the full set stays in the backfill / R2 detail lane) so the
    artifact fits the ~1.2MB page budget.

    Emits earnings_compare.json.  Fail-open + display-tier.
    """
    import pandas as pd  # noqa: PLC0415

    df = load_backfill_earnings(root)
    rows_out: list[dict] = []
    n_full = 0
    n_scored = 0

    if not df.empty:
        d = _quarterly_earnings_frame(df)
        d = d.sort_values(["issuer_key", "fiscal_period_order", "call_dt"])
        for issuer_key, grp in d.groupby("issuer_key"):
            if len(grp) < 2:
                continue
            cur = grp.iloc[-1]
            prev = grp.iloc[-2]
            cur_order = pd.to_numeric(
                pd.Series([cur.get("fiscal_period_order")]), errors="coerce",
            ).iloc[0]
            prev_order = pd.to_numeric(
                pd.Series([prev.get("fiscal_period_order")]), errors="coerce",
            ).iloc[0]
            if pd.isna(cur_order) or pd.isna(prev_order) or int(cur_order - prev_order) != 1:
                continue
            cur_comb = pd.to_numeric(pd.Series([cur.get("earnings_call_combined")]),
                                     errors="coerce").iloc[0]
            prev_comb = pd.to_numeric(pd.Series([prev.get("earnings_call_combined")]),
                                      errors="coerce").iloc[0]
            if pd.isna(cur_comb) or pd.isna(prev_comb):
                continue
            # FIX 2 — a stored combined of exactly 0 is an UNSCORED / missing-call
            # placeholder, NOT a true tone reading. MEASURED on the seed: 2,330
            # rows carry combined==0 yet 2,297 of them have a NON-ZERO sent and
            # 2,328 a non-zero perf (internally inconsistent with a real blend,
            # and 0 is the clamp floor — scored calls populate 1..41). Pairing an
            # unscored 0 against a scored ~35-40 manufactured the false ±35 "tone
            # swings" that dominated the top of the Raisers/Decliners ranking
            # (BTU, CMPO, RBLX, ARE, BSX, … all 0-vs-35). We keep such rows
            # VIEWABLE (the delta is still emitted) but mark them unscored so the
            # page can EXCLUDE them from the top swing ranking. `both_scored` is
            # the ranking gate; the sort below floors unscored pairs to the bottom.
            cur_scored = float(cur_comb) != 0.0
            prev_scored = float(prev_comb) != 0.0
            both_scored = cur_scored and prev_scored
            # Tags reach a user surface — advice-scrub via the shared scrubber.
            cur_tags = _scrub_tag_list(_parse_tag_list(cur.get("level1_tags")))
            prev_tags = _scrub_tag_list(_parse_tag_list(prev.get("level1_tags")))
            new_tags = [t for t in cur_tags if t not in set(prev_tags)]
            dropped_tags = [t for t in prev_tags if t not in set(cur_tags)]
            rows_out.append({
                "ticker": str(cur.get("ticker") or ""),
                "issuer_key": str(issuer_key),
                "region": str(cur.get("region") or "US"),
                "company_name": str(cur.get("company_name") or ""),
                "gics_industry": str(cur.get("gics_industry") or ""),
                "current_quarter": cur.get("fiscal_period"),
                "current_date": cur["call_dt"].date().isoformat(),
                "current_combined": round(float(cur_comb), 3),
                "current_scored": cur_scored,
                "current_tags": cur_tags,
                "prior_quarter": prev.get("fiscal_period"),
                "prior_date": prev["call_dt"].date().isoformat(),
                "prior_combined": round(float(prev_comb), 3),
                "prior_scored": prev_scored,
                "prior_tags": prev_tags,
                "fiscal_period_gap": 1,
                "delta_combined": round(float(cur_comb) - float(prev_comb), 3),
                # True iff BOTH quarters are genuinely scored — the swing-ranking
                # gate. A False here means the delta straddles an unscored quarter
                # and must NOT lead the biggest-tone-swings list.
                "both_scored": both_scored,
                "new_tags": new_tags,
                "dropped_tags": dropped_tags,
            })
        n_full = len(rows_out)
        n_scored = sum(1 for r in rows_out if r["both_scored"])
        # Cap to the top-N largest ABSOLUTE movers, but ONLY the both-scored pairs
        # compete for the top of the swing ranking (unscored-straddling pairs are
        # floored so they can never masquerade as the biggest tone swing). Within
        # each group we still sort by |delta|; the scored block leads. After the
        # cap, present signed-descending for the page's Raisers-first default.
        rows_out.sort(key=lambda r: (not r["both_scored"], -abs(r["delta_combined"])))
        rows_out = rows_out[:cap]
        rows_out.sort(key=lambda r: (not r["both_scored"], -r["delta_combined"]))

    out = _context_envelope("earnings_comparison", {
        **_frame_metadata(df),
        "n_rows": len(rows_out),
        "n_total": n_full,
        "n_scored": n_scored,       # both-quarters-scored pairs (rank-eligible)
        "cap": int(cap),
        "unscored_note": (
            "A stored combined of 0 marks an UNSCORED / missing earnings call, "
            "not a true zero. Pairs where either quarter is unscored carry "
            "both_scored=false and are excluded from the biggest-tone-swings "
            "ranking (still viewable, floored below the scored pairs)."
        ),
        "rows": _json_safe(rows_out),
    })
    if write:
        _atomic_write_json(_sa_data_root(root) / "earnings_compare.json", out)
    return out


# --------------------------------------------------------------------------- #
# Surface #4 — Earnings table (per-call display rows, latest ~500)
# --------------------------------------------------------------------------- #
def earnings_table(
    root: Path | None = None,
    *,
    cap: int = _EARNINGS_TABLE_CAP,
    write: bool = True,
) -> dict:
    """Per-call display rows: ticker, industry, date, ec_sent, ec_perf, tags,
    positive/negative highlights, slide file_path.  Latest `cap` calls by date
    (the full history stays in the backfill / R2 for the detail lane).

    Emits earnings_table.json.  Fail-open + display-tier.
    """
    import pandas as pd  # noqa: PLC0415

    df = load_backfill_earnings(root)
    rows_out: list[dict] = []

    if not df.empty:
        d = df.dropna(subset=["call_dt"]).sort_values("call_dt", ascending=False)
        d = d.head(int(cap))
        for _, r in d.iterrows():
            fp = r.get("file_path")
            fp = None if (fp is None or (isinstance(fp, float) and fp != fp)) else str(fp)
            rows_out.append({
                "ticker": str(r.get("ticker") or ""),
                "issuer_key": str(r.get("issuer_key") or ""),
                "region": str(r.get("region") or "US"),
                "company_name": str(r.get("company_name") or ""),
                "gics_industry": str(r.get("gics_industry") or ""),
                "gics_sector": str(r.get("gics_sector") or ""),
                "call_date": r["call_dt"].date().isoformat(),
                "quarter": r.get("fiscal_period") or r.get("calendar_quarter"),
                "fiscal_period_valid": not bool(r.get("invalid_fiscal_period")),
                "ec_sent": _json_safe(r.get("earnings_call_sent")),
                "ec_perf": _json_safe(r.get("earnings_call_perf")),
                "ec_combined": _json_safe(r.get("earnings_call_combined")),
                "level1_tags": _scrub_tag_list(_parse_tag_list(r.get("level1_tags"))),
                "level2_tags": _scrub_tag_list(_parse_tag_list(r.get("level2_tags"))),
                # Free-text highlights + quote reach a user surface — advice-scrub
                # them through the SAME scrubber as stage_research (item 9).
                "positive_highlights": _scrub_advice_text(
                    str(r.get("positive_highlights") or "") or None),
                "negative_highlights": _scrub_advice_text(
                    str(r.get("negative_highlights") or "") or None),
                "key_quote": _scrub_advice_text(
                    str(r.get("key_quote") or "") or None),
                "file_path": fp,
            })

    out = _context_envelope("earnings_table", {
        **_frame_metadata(df),
        "n_rows": len(rows_out),
        "cap": int(cap),
        "rows": _json_safe(rows_out),
    })
    if write:
        _atomic_write_json(_sa_data_root(root) / "earnings_table.json", out)
    return out


def earnings_intelligence_health(
    root: Path | None = None,
    *,
    frame=None,
    write: bool = True,
) -> dict:
    """Emit the operational heartbeat for the earnings data plane.

    Unlike the legacy warm-up copy, this distinguishes a healthy full-history
    lane from a committed cold-start fallback and from a genuinely empty store.
    It is intentionally diagnostic: callers may alert on ``status=empty`` but
    Stage Analysis remains display/context-only.
    """
    import pandas as pd  # noqa: PLC0415

    df = frame if frame is not None else load_backfill_earnings(root)
    meta = _frame_metadata(df)
    qoq_tickers = 0
    quarterly = _quarterly_earnings_frame(df)
    valid_period_rows = 0
    same_period_superseded_rows = 0
    if not df.empty:
        period_mask = (
            df["issuer_key"].astype(str).str.strip().ne("")
            & df["fiscal_period"].notna()
            & df["call_dt"].notna()
        )
        valid_period_rows = int(period_mask.sum())
        same_period_superseded_rows = max(0, valid_period_rows - int(len(quarterly)))
    if not quarterly.empty and "issuer_key" in quarterly.columns:
        ordered = quarterly.sort_values(
            ["issuer_key", "fiscal_period_order", "call_dt"],
        ).copy()
        grouped = ordered.groupby("issuer_key", sort=False)
        ordered["_prior_order"] = grouped["fiscal_period_order"].shift(1)
        ordered["_prior_combined"] = grouped["earnings_call_combined"].shift(1)
        latest = ordered.groupby("issuer_key", sort=False).tail(1)
        gap = (
            pd.to_numeric(latest["fiscal_period_order"], errors="coerce")
            - pd.to_numeric(latest["_prior_order"], errors="coerce")
        )
        current_combined = pd.to_numeric(
            latest["earnings_call_combined"], errors="coerce",
        )
        prior_combined = pd.to_numeric(latest["_prior_combined"], errors="coerce")
        qoq_tickers = int(
            (gap.eq(1) & current_combined.notna() & prior_combined.notna()).sum()
        )
    age_days = None
    latest = meta.get("latest_call_date")
    if latest:
        try:
            age_days = int((pd.Timestamp.now(tz="UTC").date() - pd.Timestamp(latest).date()).days)
        except Exception:  # noqa: BLE001
            age_days = None
    status = meta["data_status"]
    if status == "ready" and age_days is not None and age_days > 14:
        status = "stale"
    health = {
        "schema": "earnings_intelligence_health.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        **meta,
        "age_days": age_days,
        "valid_fiscal_source_rows": valid_period_rows,
        "canonical_issuer_period_rows": int(len(quarterly)),
        "same_period_superseded_rows": same_period_superseded_rows,
        "quarantined_fiscal_rows": int(meta.get("invalid_fiscal_period_rows") or 0),
        "qoq_eligible_tickers": qoq_tickers,
        "qoq_eligible_issuers": qoq_tickers,
        "checks": {
            "has_rows": bool(len(df)),
            "has_full_history": meta["data_source_tier"] in {
                "r2_history",
                "r2_history_plus_score_overlay",
                "legacy_full_history",
                "legacy_full_history_plus_score_overlay",
            },
            "has_qoq_pairs": qoq_tickers > 0,
            "latest_within_14d": age_days is not None and age_days <= 14,
            "transport_manifest_valid": meta.get("transport_manifest_valid") is not False,
            "fiscal_anomalies_quarantined": bool(
                quarterly.empty
                or not quarterly.get("invalid_fiscal_period", pd.Series(False)).fillna(False).any()
            ),
            "issuer_periods_reconciled": (
                int(len(quarterly)) + same_period_superseded_rows
                == valid_period_rows
            ),
        },
        "operator_note": (
            "ready = full history available; degraded = committed one-call fallback; "
            "stale = full history older than 14 days; empty = ingestion contract failure"
        ),
        "is_context_only": True,
        "display_only": True,
    }
    if write:
        r = Path(root) if root is not None else _REPO_ROOT
        _atomic_write_json(r / "data" / "quality" / "earnings_intelligence_health.json", health)
    return health


_EARNINGS_SURFACE_ARTIFACTS = {
    "ec_industry": ("ec_industry.json", "ec_industry_heatmap"),
    "ec_industry_grid": ("ec_industry_heatmap.json", "ec_industry_heatmap_grid"),
    "earnings_season": ("earnings_season.json", "earnings_season"),
    "earnings_compare": ("earnings_compare.json", "earnings_comparison"),
    "earnings_table": ("earnings_table.json", "earnings_table"),
}

_FULL_HISTORY_SOURCE_TIERS = frozenset({
    "r2_history",
    "r2_history_plus_score_overlay",
    "legacy_full_history",
    "legacy_full_history_plus_score_overlay",
})


def _read_json_artifact(path: Path) -> dict | None:
    """Return a prior JSON artifact only when it is a complete object."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return raw if isinstance(raw, dict) else None


def _is_recent_verified_full_history_surface(
    artifact: dict | None,
    *,
    expected_surface: str,
) -> bool:
    """Whether an existing artifact is safe to retain during a transient outage.

    A committed overview is deliberately a usable degraded fallback on a cold
    start.  It must not, however, replace an already-published, recent R2/full
    history generation merely because the transport is temporarily unavailable.
    The freshness gate prevents this guard from concealing genuinely stale data.
    """
    if not isinstance(artifact, dict):
        return False
    if artifact.get("surface") != expected_surface:
        return False
    # ``stale`` here means the latest *call date* is older than 14 days.  That
    # is normal between earnings seasons and is independent of whether this
    # full-history artifact was rebuilt recently enough to be a safe fallback.
    if artifact.get("data_status") not in {"ready", "stale"}:
        return False
    if artifact.get("data_source_tier") not in _FULL_HISTORY_SOURCE_TIERS:
        return False
    if not artifact.get("is_context_only") or not artifact.get("display_only"):
        return False
    try:
        if int(artifact.get("source_rows") or 0) <= 0:
            return False
        generated_at = datetime.fromisoformat(
            str(artifact["generated_at"]).replace("Z", "+00:00"),
        )
        if generated_at.tzinfo is None:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    age = datetime.now(timezone.utc) - generated_at.astimezone(timezone.utc)
    return 0 <= age.total_seconds() <= 14 * 24 * 60 * 60


def _candidate_requires_last_good_guard(candidate: dict | None) -> bool:
    """A missing, empty, or degraded candidate may not erase verified history."""
    if not isinstance(candidate, dict):
        return True
    return candidate.get("data_status") in {"empty", "degraded"}


def build_all_earnings_surfaces(root: Path | None = None) -> dict:
    """Build Earnings-Calls surface artifacts without downgrading last good data.

    Individual surfaces remain fail-open.  During a temporary history transport
    outage, a recent verified full-history artifact is retained instead of being
    overwritten by the committed overview fallback.  Cold starts still publish
    that fallback, so the UI never regresses to an empty/warming state.
    """
    r = Path(root) if root is not None else _REPO_ROOT
    out_root = _sa_data_root(r)
    results: dict[str, Any] = {}
    guarded_surfaces: list[str] = []
    for name, fn in (
        ("ec_industry", ec_industry_heatmap),
        ("ec_industry_grid", ec_industry_heatmap_grid),
        ("earnings_season", earnings_season),
        ("earnings_compare", earnings_comparison),
        ("earnings_table", earnings_table),
    ):
        filename, expected_surface = _EARNINGS_SURFACE_ARTIFACTS[name]
        path = out_root / filename
        previous = _read_json_artifact(path)
        candidate: dict | None = None
        try:
            candidate = fn(root=r, write=False)  # type: ignore[operator]
        except Exception as exc:  # noqa: BLE001
            print(f"::warning:: earnings_qual: surface {name} failed ({exc})", flush=True)

        if (
            _candidate_requires_last_good_guard(candidate)
            and _is_recent_verified_full_history_surface(
                previous, expected_surface=expected_surface,
            )
        ):
            results[name] = previous
            guarded_surfaces.append(name)
            print(
                "::warning:: earnings_qual: retaining recent verified "
                f"{name} surface because this generation is unavailable or degraded",
                flush=True,
            )
        elif candidate is not None:
            _atomic_write_json(path, candidate)
            results[name] = candidate
        else:
            results[name] = {"error": "surface generation failed"}

    try:
        health = earnings_intelligence_health(root=r, write=True)
        if guarded_surfaces:
            health["surface_publish_guard"] = {
                "status": "retained_recent_verified_full_history",
                "surfaces": guarded_surfaces,
                "reason": "current_generation_unavailable_or_degraded",
            }
            _atomic_write_json(
                r / "data" / "quality" / "earnings_intelligence_health.json", health,
            )
        results["health"] = health
    except Exception as exc:  # noqa: BLE001
        print(f"::warning:: earnings_qual: health build failed ({exc})", flush=True)
        results["health"] = {"error": str(exc)}
    return results


# --------------------------------------------------------------------------- #
# CLI (cold-start / ops convenience — NOT wired into the render path)
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="Score earnings text / build surfaces.")
    ap.add_argument("--root", default=None, help="repo root override")
    ap.add_argument("--source", default="auto", choices=["auto", "transcript", "8k"])
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--surfaces", action="store_true",
                    help="Build the four Earnings-Calls surface artifacts and exit.")
    args = ap.parse_args(argv)
    if args.surfaces:
        res = build_all_earnings_surfaces(root=args.root)
        for name, r in res.items():
            n = r.get("n_rows") or r.get("n_quarters") or r.get("n_weeks") or "?"
            print(f"{name}: {n} rows")
        return 0
    n = score_new(root=args.root, source=args.source, limit=args.limit)
    print(f"scored {n} new earnings row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
