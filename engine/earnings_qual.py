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
    "provider_order": ["openai_compat", "deepseek", "anthropic"],
    "openai_compat": {
        "base_url": "http://localhost:8000/v1",
        "model": "qwen3-14b",
        "api_key_env": "LOCAL_LLM_API_KEY",
        "timeout_s": 120,
        "max_tokens": 1200,
    },
    "opus_model": "claude-haiku-4-5",
    "deepseek_model": "deepseek-v4-pro",
    "daily_cap": 8,
    "max_chars": 24000,
    "retry_on_bad_json": 1,
    "prompt_version": "equal-v1",
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


def _call_llm_auth(
    system: str, user: str, cfg: dict, provider_name: str, *, max_tokens: int
) -> tuple[str | None, str | None]:
    """Cloud fallback via engine.llm_auth for a single named provider.

    provider_name ∈ {"anthropic", "deepseek"}.  Builds a one-provider waterfall
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
        elif name in ("anthropic", "deepseek"):
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

    Returns a dict conforming to the §2 scores contract:
      { ticker, quarter, year, call_date, source, model, sentiment,
        performance, confidence, tone_word, positive_highlights,
        negative_highlights, tags, source_sha256, scored_at,
        is_context_only, degraded_reason }
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
        "is_context_only": True,   # SGA-R5 — ALWAYS context-only
        "degraded_reason": None,
    }

    if not text or not str(text).strip():
        base_row["degraded_reason"] = "empty_text"
        return base_row

    max_chars = int(cfg.get("max_chars", 24000))
    body = str(text)[:max_chars]
    max_tokens = int(
        (provider_cfg.get("openai_compat") or {}).get("max_tokens")
        or (cfg.get("openai_compat") or {}).get("max_tokens")
        or 1200
    )

    user = _build_user_prompt(base_row["ticker"], q_norm, y_norm, source, body)

    # First attempt.
    reply, reason, provider_used = _dispatch(
        _SYSTEM_PROMPT, user, cfg, provider_cfg, max_tokens=max_tokens
    )
    obj = _extract_json(reply) if reply else None

    # One retry on invalid JSON (SGA harness contract).
    retries = int(cfg.get("retry_on_bad_json", 1))
    if obj is None and reply is not None and retries > 0:
        reply2, reason2, provider_used2 = _dispatch(
            _SYSTEM_PROMPT, user + _RETRY_SUFFIX, cfg, provider_cfg,
            max_tokens=max_tokens,
        )
        obj2 = _extract_json(reply2) if reply2 else None
        if obj2 is not None:
            obj, provider_used = obj2, provider_used2
        else:
            reason = reason2 or reason

    if obj is None:
        # Degraded — no usable JSON.  Distinguish no-provider from bad-json.
        if reply is None:
            base_row["degraded_reason"] = reason or "no_provider"
        else:
            base_row["degraded_reason"] = "invalid_json"
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
    return base_row


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
        return pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001
        log.warning("earnings_qual: scores parquet unreadable (%s) — empty", exc)
        return pd.DataFrame(columns=_STORE_COLUMNS)


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


def upsert_scores(rows: list[dict], root: Path | None = None):
    """Upsert score rows into scores.parquet keyed (ticker, quarter, year, source).

    Idempotent: a later score for the same key REPLACES the prior row.  Returns
    the number of rows written (inserted or replaced).  Atomic write.
    """
    import pandas as pd  # noqa: PLC0415
    if not rows:
        return 0
    existing = load_scores(root)
    new_df = pd.DataFrame([_row_to_store(r) for r in rows], columns=_STORE_COLUMNS)
    if existing.empty:
        combined = new_df
    else:
        # Align existing columns to the store schema (fill missing).
        for c in _STORE_COLUMNS:
            if c not in existing.columns:
                existing[c] = None
        existing = existing[_STORE_COLUMNS]
        combined = pd.concat([existing, new_df], ignore_index=True)
    # New rows are appended last → keep='last' retains the fresh score.
    key = ["ticker", "quarter", "year", "source"]
    combined = combined.drop_duplicates(subset=key, keep="last").reset_index(drop=True)
    _atomic_write_parquet(combined, store_path(root))
    return len(new_df)


def _seen_shas(root: Path | None = None) -> set[str]:
    df = load_scores(root)
    if df.empty or "source_sha256" not in df.columns:
        return set()
    return set(df["source_sha256"].dropna().astype(str).tolist())


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


# --------------------------------------------------------------------------- #
# CLI (cold-start / ops convenience — NOT wired into the render path)
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="Score un-scored earnings text.")
    ap.add_argument("--root", default=None, help="repo root override")
    ap.add_argument("--source", default="auto", choices=["auto", "transcript", "8k"])
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args(argv)
    n = score_new(root=args.root, source=args.source, limit=args.limit)
    print(f"scored {n} new earnings row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
