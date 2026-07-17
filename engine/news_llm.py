"""News LLM processor — cheap batch summaries + relevance re-rank.

GATED · DEGRADE-TO-NONE · CONTEXT-ONLY · DEFAULT OFF (W5 P5 R3).

WHY DEFAULT OFF
---------------
The annotator computes ``llm_importance`` and ``llm_tone`` fields but NO
downstream consumer reads them for scoring or allocation (confirmed by audit:
only ``build_news._blend_key`` uses ``llm_importance`` as a 40% secondary sort
weight; the deterministic quality score is always the primary key).  The
``max_batches=16`` cap silently dropped ~87% of the tape even when enabled [P5].

Re-enabling this module requires:
  1. A registered scored-consumer entry in ``config/qual_ladder.yml`` (field
     ``news_llm.llm_importance``) with ``ladder_state: DISPLAY`` minimum.
  2. A qledger ``claim_family`` tag so the claim accrues a grade.
  3. Flip ``news_llm.enabled: true`` in ``config.yml``.

Until those are in place, the code path is preserved but the module is off.

WHAT IT DOES (when enabled)
---------------------------
The deterministic engine.news_common quality score already decides what's shown
and in what order. This layer only *adds* two display niceties on top of the
already-filtered headlines:

  • a one-line plain-English summary (when the source gave none), and
  • an LLM "importance" hint (0-100) used as a SECONDARY sort key — it can
    re-order within a section but never adds or removes a headline.

Nothing it produces is ever a scoring/trade input.

Provider order (first that has a credential wins; override via config):
  1. Claude Haiku via the Claude subscription OAuth token  (CLAUDE_CODE_OAUTH_TOKEN)
        — Authorization: Bearer + the oauth-2025-04-20 beta header.
  2. Claude Haiku via a normal API key                     (ANTHROPIC_API_KEY)
  3. DeepSeek V4-Flash via its Anthropic-compatible wire   (DEEPSEEK_API_KEY)

Cost control: headlines are processed in BATCHES (one model call summarises N at
once), with a hard cap on total calls per build. Haiku 4.5 is ~$1/$5 per 1M tok;
a full daily run is a few cents. The Claude subscription path bills against the
5-hour / weekly subscription limits, not the API. Any failure → headlines pass
through unchanged.
"""
from __future__ import annotations

import json
import logging
import os

from lib import config

log = logging.getLogger(__name__)

# Fallback literals — used when config['llm_models'] block is absent (W5 migration).
# Prefer config['llm_models']['classify'] at runtime via _classify_model().
DEFAULT_HAIKU = "claude-haiku-4-5"
DEFAULT_DEEPSEEK = "deepseek-chat"
DEEPSEEK_BASE = "https://api.deepseek.com/anthropic"
OAUTH_BETA = "oauth-2025-04-20"


def _classify_model() -> str:
    """Return the version-pinned classify model id (W5 — P5 R5).

    Resolution order:
    1. config['llm_models']['classify']  (version-pinned, authoritative)
    2. config['news_llm']['anthropic_model']  (per-section override)
    3. DEFAULT_HAIKU                     (emergency fallback)

    Does NOT raise on absence — news_llm predates the W5 requirement.
    """
    llm_models = config.load().get("llm_models") or {}
    if llm_models.get("classify"):
        return str(llm_models["classify"])
    cfg_model = (_cfg() or {}).get("anthropic_model")
    if cfg_model:
        return str(cfg_model)
    return DEFAULT_HAIKU

SYSTEM = (
    "You compress financial/market headlines for a dashboard. For each numbered item you are "
    "given a HEADLINE and (sometimes) a short SOURCE BLURB. Return STRICT JSON only — an array "
    "of objects {\"i\": <int>, \"summary\": <string>, \"importance\": <int 0-100>, "
    "\"tone\": \"pos\"|\"neg\"|\"neutral\"}.\n"
    "summary: ONE factual sentence (<=160 chars) drawn ONLY from the given headline/blurb — no "
    "advice, no price targets, no predictions, no invented facts. If the headline already says "
    "everything, lightly rephrase for clarity.\n"
    "importance: how market-moving / broadly relevant the item is (100 = a Fed decision, major "
    "M&A, megacap guidance; 0 = trivia or an opinion listicle).\n"
    "tone: directional sentiment of the news for the named company/sector, or \"neutral\".\n"
    "Output the JSON array and nothing else."
)


def _cfg() -> dict:
    return config.load().get("news_llm", {}) or {}


def enabled() -> bool:
    """On by default WHEN a credential is present — but degrades to a no-op (returns
    the input unchanged) the moment any provider is unavailable, so the suite never
    depends on it."""
    return bool(_cfg().get("enabled", True)) and _provider() is not None


# --------------------------------------------------------------------------- #
# provider selection
# --------------------------------------------------------------------------- #
def _provider() -> tuple[str, str, str] | None:
    """Return (provider, credential, model) for the first available provider, or None.
    provider ∈ {"oauth", "anthropic", "deepseek"}."""
    cfg = _cfg()
    order = cfg.get("provider_order") or ["oauth", "anthropic", "deepseek"]
    haiku = _classify_model()
    for p in order:
        if p == "oauth":
            tok = config.secret(cfg.get("oauth_token_env", "CLAUDE_CODE_OAUTH_TOKEN"))
            if tok:
                return ("oauth", tok, haiku)
        elif p == "anthropic":
            key = config.secret("ANTHROPIC_API_KEY")
            if key:
                return ("anthropic", key, haiku)
        elif p == "deepseek":
            key = config.secret(cfg.get("deepseek_key_env", "DEEPSEEK_API_KEY"))
            if key:
                return ("deepseek", key, cfg.get("deepseek_model", DEFAULT_DEEPSEEK))
    return None


def _client(provider: str, cred: str):
    """Build an anthropic SDK client for the chosen provider. The OAuth path uses a
    Bearer token + the oauth beta header; we pass api_key=None so the SDK does not
    also attach an x-api-key from the environment (which the API would reject)."""
    import anthropic
    if provider == "oauth":
        # Subscription OAuth token → Authorization: Bearer + oauth beta header.
        return anthropic.Anthropic(api_key=None, auth_token=cred,
                                   default_headers={"anthropic-beta": OAUTH_BETA})
    if provider == "deepseek":
        return anthropic.Anthropic(api_key=cred, base_url=DEEPSEEK_BASE)
    return anthropic.Anthropic(api_key=cred)


# Tolerant JSON extraction. NOTE: engine.catalyst_tone._extract_json only recovers a
# JSON *object* (it scans for {...}); our batch contract is a JSON *array*, so we use
# our own array-aware parser here rather than reuse it.
def _xjson(text: str):
    """Recover a JSON array (or object) from model text — handles ```json fences and
    leading prose; falls back to the outermost [...] / {...} span. Returns None on
    failure."""
    import re
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    body = (m.group(1) if m else text).strip()
    try:
        return json.loads(body)
    except Exception:  # noqa: BLE001
        pass
    # outermost array first (our contract), then object
    for open_c, close_c in (("[", "]"), ("{", "}")):
        a, b = body.find(open_c), body.rfind(close_c)
        if 0 <= a < b:
            try:
                return json.loads(body[a:b + 1])
            except Exception:  # noqa: BLE001
                continue
    return None


# --------------------------------------------------------------------------- #
# batch summarise + score
# --------------------------------------------------------------------------- #
def _summarise_batch_raw(items: list[dict], client, model: str):
    """One model call for up to len(items) headlines. items: [{i,title,blurb}].
    Returns (results_dict, resp) where results_dict = {i: {summary, importance, tone}}.
    Raises on auth errors (so llm_auth.make_call can detect 401 and trigger provider
    fallback); degrades to ({}, None) on other non-auth failures.
    The resp object is returned so the caller can pass it back via the 3-tuple
    make_call contract for usage capture.
    """
    lines = []
    for it in items:
        blurb = (it.get("blurb") or "").strip()
        lines.append(f'{it["i"]}. HEADLINE: {it.get("title","")}'
                     + (f' | BLURB: {blurb[:240]}' if blurb else ""))
    user = "Items:\n" + "\n".join(lines)
    max_tok = min(4000, 90 * len(items) + 200)
    # NOTE: we do NOT catch all exceptions here — auth errors must propagate to
    # llm_auth.make_call() so it can detect 401 and try the next provider.
    resp = client.messages.create(
        model=model, max_tokens=max_tok, system=SYSTEM,
        messages=[{"role": "user", "content": user}])
    if getattr(resp, "stop_reason", "") == "refusal":
        return {}, resp
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    parsed = _xjson(text)
    if not isinstance(parsed, list):
        return {}, resp
    out: dict[int, dict] = {}
    for row in parsed:
        if not isinstance(row, dict) or "i" not in row:
            continue
        try:
            idx = int(row["i"])
        except (ValueError, TypeError):
            continue
        summ = str(row.get("summary", "")).strip()[:200]
        try:
            imp = max(0, min(100, int(row.get("importance", 50))))
        except (ValueError, TypeError):
            imp = 50
        tone = str(row.get("tone", "neutral")).lower()
        tone = tone if tone in ("pos", "neg", "neutral") else "neutral"
        out[idx] = {"summary": summ, "importance": imp, "tone": tone}
    return out, resp


# backward-compat alias (tests may import _summarise_batch directly)
_summarise_batch = _summarise_batch_raw


def annotate(headlines: list[dict], batch_size: int | None = None,
             max_batches: int | None = None) -> list[dict]:
    """Attach `summary`, `llm_importance`, `llm_tone` to each headline in place-ish
    (returns the same list objects, mutated). No-op pass-through when no provider /
    disabled / on any error. Caps total model calls at `max_batches`.

    Headlines lacking a usable title are skipped. Existing `summary` fields are
    preserved (only filled when blank), so provider-supplied blurbs win.

    W5 ITEM 1 — 401-fallback: uses engine.llm_auth.build_providers() so that an
    expired OAuth token triggers a per-batch fallback to the next provider. Each
    batch independently tries the full waterfall (dead providers are skipped at
    process level via llm_auth).
    """
    if not headlines:
        return headlines
    cfg = _cfg()
    if not bool(cfg.get("enabled", True)):
        return headlines

    from engine import llm_auth
    haiku = _classify_model()
    ds_model = cfg.get("deepseek_model", DEFAULT_DEEPSEEK)
    cfg_aug = {**cfg,
               "oauth_pool_lane": cfg.get("oauth_pool_lane", "news-llm"),
               "usage_lane": cfg.get("usage_lane", "news-llm")}
    providers = llm_auth.build_providers(cfg_aug, opus_model=haiku, deepseek_model=ds_model)
    if not providers:
        return headlines

    bs = int(batch_size or cfg.get("batch_size", 12))
    mb = int(max_batches or cfg.get("max_batches", 12))

    # Build the worklist: index every headline that wants enrichment.
    work = [(n, h) for n, h in enumerate(headlines) if (h.get("title") or "").strip()]
    batches = [work[i:i + bs] for i in range(0, len(work), bs)][:mb]
    calls = 0
    provider_used_log: list[str] = []
    for batch in batches:
        items = [{"i": gi, "title": h.get("title", ""),
                  "blurb": h.get("summary") or h.get("description") or ""}
                 for gi, h in batch]

        def _do_call(client, model: str):
            result_dict, resp = _summarise_batch_raw(items, client, model)
            return result_dict, None, resp

        try:
            raw_res, _, pused = llm_auth.make_call(providers, _do_call, context="news_llm")
        except Exception as e:  # noqa: BLE001
            log.warning("news_llm batch call error (%s)", e)
            raw_res, pused = None, None

        res = raw_res or {}
        if pused:
            provider_used_log.append(pused)
        calls += 1
        for gi, h in batch:
            r = res.get(gi)
            if not r:
                continue
            if not (h.get("summary") or "").strip() and r.get("summary"):
                h["summary"] = r["summary"]
            h["llm_importance"] = r.get("importance")
            h["llm_tone"] = r.get("tone")

    if calls:
        providers_str = ",".join(sorted(set(provider_used_log))) or "none"
        log.info("news_llm: %d batch call(s) via %s", calls, providers_str)
    return headlines


def provider_label() -> str:
    """Human label of the active provider, for the page footer. Never raises."""
    prov = _provider()
    if prov is None:
        return ""
    provider, _, model = prov
    return {"oauth": f"Claude {model} (subscription)",
            "anthropic": f"Claude {model}",
            "deepseek": f"DeepSeek {model}"}.get(provider, model)
