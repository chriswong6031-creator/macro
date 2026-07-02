"""White House alert brain — the Claude-Opus policy analyst.

LEAF · GATED · CONTEXT-ONLY · DEGRADE-NEVER-RAISE. For each NEW White House
announcement (engine.whitehouse_feed) this asks Claude Opus to do the judgement a
keyword rule can't:

  1. SIGNIFICANCE — is this market-moving enough to earn a site-wide alert banner?
     The vast majority of WH posts (proclamations, ceremonial days, nomination
     lists, personnel notes) are NOT. Only a genuinely market-relevant policy
     action — tariffs, sanctions, a sector-shaping executive order, fiscal /
     regulatory / energy / defense / health / tech moves — clears the bar.
  2. If it clears it: a concise BANNER TITLE that states the market importance
     (not just the headline), a banner LIFESPAN (1-7 days, scaled to durability),
     an overall TONE, and a full REPORT — implications, why it matters, analysis,
     the SECTORS facing head/tailwinds, and the specific liquid US-listed TICKERS
     that benefit, each with a one-line thesis.
  3. If it does NOT clear it: `activate=false` and nothing else is written — no
     banner, no report (per the desk's contract).

AUTH (the "Opus brain via the CLI"): Claude via the user's Claude-Code OAuth token
(CLAUDE_CODE_OAUTH_TOKEN → the SDK `auth_token=` Bearer path + the required
`anthropic-beta: oauth-2025-04-20` header), model claude-opus-4-8. Falls back to an
ANTHROPIC_API_KEY, then a DeepSeek reasoning model (Anthropic-compatible endpoint)
so the desk still runs in CI without the subscription token. No provider → a clean
no-op (the item is marked seen / inactive).

This is analysis, never advice or a trade signal. Nothing in the scoring path
imports it; the tickers it names feed no score, size, or allocation.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from lib import config
from engine.catalyst_tone import _extract_json   # shared tolerant JSON parser (leaf util)

log = logging.getLogger(__name__)

OAUTH_BETA = "oauth-2025-04-20"   # REQUIRED on /v1/messages when authing with an OAuth token

_DEFAULTS = {
    "enabled": True,                               # MASTER SWITCH (no-op anyway without a provider)
    "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",  # Claude-Code subscription (Bearer + oauth beta)
    "api_key_env": "ANTHROPIC_API_KEY",            # direct-API fallback
    "deepseek_key_env": "DEEPSEEK_API_KEY",        # last-resort reasoning fallback (CI)
    "deepseek_base_url": "https://api.deepseek.com/anthropic",
    "opus_model": "claude-opus-4-8",
    "deepseek_model": "deepseek-v4-pro",
    "provider_order": ["oauth", "anthropic", "deepseek"],
    "max_tokens": 4000,
    "min_importance": 60,        # importance floor below which the banner is suppressed
    "max_banner_days": 7,        # hard ceiling on banner lifespan
    "max_tickers": 8,            # cap named beneficiaries (honesty over breadth)
    "max_sectors": 6,
    "max_new_per_run": 6,        # cap brain calls per sentinel run (cost guard)
    "max_banner_alerts": 6,      # cap LIVE banners on the ticker tape (readability)
}

DISCLAIMER = (
    "AI-generated analysis of a primary-source White House announcement — context "
    "only, NOT investment advice and NOT a trade signal. It feeds no score, size or "
    "allocation. Policy-to-market reasoning is uncertain; the named tickers are "
    "illustrative of plausible exposure, can be wrong, and are not recommendations. "
    "Verify against the linked primary source."
)

_TONES = {"tailwind", "headwind", "mixed", "neutral"}
_DIRS = {"benefit", "hurt"}
_CONF = {"low", "medium", "high"}

SYSTEM = (
    "You are a senior policy-and-markets strategist for a solo macro trader's dashboard. "
    "You are handed the FULL TEXT of a single, just-published White House announcement "
    "(executive order, proclamation, fact sheet, statement or release). Your job has two "
    "stages.\n\n"
    "STAGE 1 — SIGNIFICANCE GATE. Decide whether this announcement is market-relevant "
    "enough to justify a SITE-WIDE ALERT BANNER on a markets dashboard. Be STRICT and "
    "selective: most White House posts are NOT (ceremonial proclamations, 'National X "
    "Month', flag days, routine nominations/personnel, condolences, generic statements). "
    "ACTIVATE only for genuinely market-moving policy: tariffs / trade actions, sanctions / "
    "export controls, sector-shaping executive orders, fiscal or tax measures, financial / "
    "antitrust / energy / defense / healthcare / tech / immigration-labor regulation, "
    "major federal procurement or strategic-reserve actions, or anything that clearly "
    "redirects capital toward or away from identifiable industries.\n\n"
    "STAGE 2 — only if it clears the gate. Write the alert:\n"
    "- banner_title: ONE punchy line (<=90 chars) stating the MARKET significance, not a "
    "restatement of the headline (e.g. 'Trump 25% auto tariff — supplier margins squeezed, "
    "domestic OEMs shielded'). This is what scrolls on the ticker.\n"
    "- importance: 0-100, how broadly market-moving (100 = a sweeping tariff regime or a "
    "Fed-level shock; 60 = a real but contained sector action). Below ~60 you should "
    "usually NOT activate.\n"
    "- banner_days: integer 1-7 — how long the banner should stay live, scaled to how "
    "DURABLE the market impact is (a one-day headline = 1-2; a structural policy shift = "
    "5-7).\n"
    "- tone: overall market read — 'tailwind' (net risk-positive / pro-growth), 'headwind' "
    "(net risk-negative), 'mixed' (clear winners AND losers), or 'neutral'.\n"
    "- summary: 1-2 sentences a reader sees first.\n"
    "- analysis: 2-4 short paragraphs — what the action actually does, WHY it matters for "
    "markets, the transmission mechanism, and the key uncertainty. Plain prose, no advice.\n"
    "- sectors: the industries facing a tailwind or headwind, each with a one-line "
    "rationale.\n"
    "- tickers: specific, LIQUID, US-LISTED names (or ADRs) plausibly affected — for each, "
    "direction ('benefit' or 'hurt') and a one-line thesis tying it to the action. Name "
    "real tickers you are confident exist; prefer the most direct exposure; omit rather "
    "than pad. These are illustrative exposure, never recommendations.\n"
    "- summary_zh / banner_title_zh: a faithful Simplified-Chinese rendering of summary and "
    "banner_title (the dashboard is bilingual).\n"
    "- confidence: 'low' | 'medium' | 'high' in the market read.\n\n"
    "Reason from the announcement's actual content; do not invent provisions it doesn't "
    "contain. If the policy is real but the market impact is genuinely ambiguous, say so "
    "and lower confidence rather than overstating.\n\n"
    "Return ONLY a JSON object (no markdown fences) with keys: activate (bool), importance "
    "(int), banner_days (int), tone (string), banner_title (string), banner_title_zh "
    "(string), summary (string), summary_zh (string), analysis (string), sectors (array of "
    "{name, impact:'tailwind'|'headwind', rationale}), tickers (array of {symbol, "
    "direction:'benefit'|'hurt', rationale}), confidence (string). If activate is false, "
    "return just {activate:false, importance:<int>} and omit the rest."
)


# --------------------------------------------------------------------------- #
# config + provider
# --------------------------------------------------------------------------- #
def _cfg() -> dict:
    try:
        return {**_DEFAULTS, **(config.load().get("whitehouse") or {})}
    except Exception:  # noqa: BLE001
        return dict(_DEFAULTS)


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def _provider(cfg: dict) -> tuple[str, str, str] | None:
    """(provider, credential, model) for the first available provider, or None."""
    order = cfg.get("provider_order") or ["oauth", "anthropic", "deepseek"]
    opus = cfg.get("opus_model", "claude-opus-4-8")
    for p in order:
        if p == "oauth":
            tok = config.secret(cfg.get("oauth_token_env", "CLAUDE_CODE_OAUTH_TOKEN"))
            if tok:
                return ("oauth", tok, opus)
        elif p == "anthropic":
            key = config.secret(cfg.get("api_key_env", "ANTHROPIC_API_KEY"))
            if key:
                return ("anthropic", key, opus)
        elif p == "deepseek":
            key = config.secret(cfg.get("deepseek_key_env", "DEEPSEEK_API_KEY"))
            if key:
                return ("deepseek", key, cfg.get("deepseek_model", "deepseek-v4-pro"))
    return None


def provider_label(cfg: dict | None = None) -> str:
    prov = _provider(cfg or _cfg())
    if prov is None:
        return ""
    provider, _, model = prov
    return {"oauth": f"Claude {model} (subscription)",
            "anthropic": f"Claude {model}",
            "deepseek": f"DeepSeek {model}"}.get(provider, model)


def _client(provider: str, cred: str, cfg: dict):
    import anthropic
    if provider == "oauth":
        return anthropic.Anthropic(api_key=None, auth_token=cred,
                                   default_headers={"anthropic-beta": OAUTH_BETA})
    if provider == "deepseek":
        return anthropic.Anthropic(api_key=cred,
                                   base_url=cfg.get("deepseek_base_url",
                                                    "https://api.deepseek.com/anthropic"))
    return anthropic.Anthropic(api_key=cred)


def _wh_prompt_hash(model: str, system: str, user: str) -> str:
    h = hashlib.sha256()
    for part in (model, system, user):
        h.update(part.encode("utf-8"))
    return h.hexdigest()


def _wh_reply_cache_path(prompt_hash: str, cfg: dict):
    from pathlib import Path as _P
    cdir = config.ROOT / cfg.get("reply_cache_dir", "data/whitehouse/reply_cache")
    _P(cdir).mkdir(parents=True, exist_ok=True)
    return _P(cdir) / f"{prompt_hash}.txt"


def _wh_reply_cache_get(prompt_hash: str, cfg: dict) -> str | None:
    p = _wh_reply_cache_path(prompt_hash, cfg)
    try:
        return p.read_text() if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _wh_reply_cache_put(prompt_hash: str, text: str, cfg: dict) -> None:
    try:
        _wh_reply_cache_path(prompt_hash, cfg).write_text(text)
    except Exception:  # noqa: BLE001
        pass


def _call_model(system: str, user: str, cfg: dict) -> tuple[str | None, str | None]:
    """(reply_text, degraded_reason). Never raises.

    Determinism kit: temperature=0 to make significance/activation judgments
    reproducible. The Anthropic SDK does NOT support a `seed` parameter on
    messages.create() — the parameter was never added to the API (verified W5);
    passing it raises TypeError. Content-hash cache provides the idempotency
    guarantee instead: the same announcement body always yields the same graded
    record so the banner can't toggle between runs.
    """
    prov = _provider(cfg)
    if prov is None:
        return None, "no_provider"
    provider, cred, model = prov
    # content-hash cache check
    phash = _wh_prompt_hash(model, system, user)
    cached = _wh_reply_cache_get(phash, cfg)
    if cached is not None:
        log.debug("whitehouse_brain: reply cache HIT (%s)", phash[:12])
        return cached, None
    try:
        client = _client(provider, cred, cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("whitehouse_brain client init failed (%s)", e)
        return None, "client_init_failed"
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=int(cfg.get("max_tokens", 4000)),
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=0,          # greedy decode — determinism where supported
        )
        sr = getattr(resp, "stop_reason", None)
        if sr == "refusal":
            return None, "stop_refusal"
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        if not text:
            return None, "empty_reply"
        _wh_reply_cache_put(phash, text, cfg)  # cache successful reply
        return text, ("truncated" if sr == "max_tokens" else None)
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("whitehouse_brain model call failed (%s)", e)
        return None, "llm_error"


# --------------------------------------------------------------------------- #
# best-effort price enrichment for the ticker tape (committed data/yahoo)
# --------------------------------------------------------------------------- #
def _recent_change(symbol: str, root: Path) -> float | None:
    """Last daily % change for a symbol from the committed data/yahoo cache, or None.

    Display garnish for the ticker chips — purely best-effort, never fatal.

    NOTE: data/yahoo/*.parquet `close` is the dividend-adjusted TOTAL-RETURN price
    (repo memory: yahoo-close-is-total-return). Day-over-day on TR-adjusted close
    is a valid % change — the adjustment applies equally to both bars so the ratio
    is correct and there is no dividend-reinvestment distortion within one day.
    The field is labelled `chg_pct` (price-change percent on TR-adjusted close) to
    be precise; it is display-only garnish on the ticker chip, never a signal.
    """
    sym = (symbol or "").strip().upper()
    if not sym or not sym.replace(".", "").replace("-", "").isalnum():
        return None
    p = Path(root) / "data" / "yahoo" / f"{sym}.parquet"
    if not p.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(p, columns=["close"])
        if len(df) < 2:
            return None
        prev, last = float(df["close"].iloc[-2]), float(df["close"].iloc[-1])
        if prev <= 0:
            return None
        # chg_pct = day-over-day % on TR-adjusted close (both bars adjusted → ratio ok)
        return round((last / prev - 1.0) * 100.0, 2)
    except Exception:  # noqa: BLE001
        return None


def _macro_backdrop(root: Path) -> str:
    """One compact line of current market backdrop so the brain grounds sector calls.
    Best-effort; empty string when unavailable."""
    try:
        d = json.loads((Path(root) / "data" / "regime" / "latest.json").read_text())
        bits = [f"date={d.get('date')}", f"regime={d.get('quad_name') or d.get('label')}"]
        mr = d.get("macro_risk") or {}
        if mr.get("label"):
            bits.append(f"macro_risk={mr.get('label')}")
        return "; ".join(b for b in bits if b and "None" not in b)
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- #
# validation / normalisation of the model's JSON
# --------------------------------------------------------------------------- #
def _coerce_int(v, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return default


def _truthy(v) -> bool:
    """Honest truthiness for a model-emitted flag. A real bool is used as-is; a STRING
    is matched against true-words — because bool("false") is True in Python, so passing
    a stringy "false" through bool() would WRONGLY activate a site-wide banner."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "y")
    return bool(v)


def _norm_sectors(raw, cfg: dict) -> list[dict]:
    out = []
    for s in (raw or [])[: int(cfg.get("max_sectors", 6))]:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name", "")).strip()[:60]
        impact = str(s.get("impact", "")).strip().lower()
        impact = impact if impact in ("tailwind", "headwind") else "mixed"
        if not name:
            continue
        out.append({"name": name, "impact": impact,
                    "rationale": str(s.get("rationale", "")).strip()[:240]})
    return out


def _known_universe(root: Path) -> set[str]:
    """Load the known US-listed ticker universe from the signal_gate.json verdicts file.
    This is the broadest reliable universe the repo has (built daily from the US stock
    library, ~1600+ tickers). Falls back to an empty set if the file is absent so the
    caller degrades gracefully — but callers must treat an empty set as 'gate open'
    (no false drops when the universe file is missing)."""
    p = root / "site" / "factordata" / "signal_gate.json"
    if not p.exists():
        return set()
    try:
        d = json.loads(p.read_text())
        verdicts = d.get("verdicts") or {}
        return set(verdicts.keys())
    except Exception:  # noqa: BLE001
        return set()


def _norm_tickers(raw, cfg: dict, root: Path) -> list[dict]:
    """Normalise and existence-gate LLM-proposed tickers.

    Fix #43b: add an existence gate — each proposed ticker is validated against the
    known US-listed universe (site/factordata/signal_gate.json). A hallucinated,
    delisted, or misidentified ticker that passes the symbol-shape check but is not
    in the universe is DROPPED with a log warning rather than reaching the every-page
    banner. The universe is loaded lazily; when the file is absent the gate opens
    (no false drops) so the desk degrades to the old shape-only check.
    """
    universe = _known_universe(root)          # empty set when file missing → gate open
    out, seen = [], set()
    for t in (raw or [])[: int(cfg.get("max_tickers", 8))]:
        if not isinstance(t, dict):
            continue
        sym = str(t.get("symbol", "")).strip().upper()
        # plausible US ticker/ADR shape only — block prose leaking into the symbol slot
        if not sym or len(sym) > 6 or not all(c.isalnum() or c in ".-" for c in sym):
            continue
        if sym in seen:
            continue
        # existence gate: if the universe is loaded and the ticker isn't in it, drop it
        if universe and sym not in universe:
            log.info("whitehouse_brain: dropped unknown/delisted ticker %s (not in universe)", sym)
            continue
        seen.add(sym)
        direction = str(t.get("direction", "")).strip().lower()
        direction = direction if direction in _DIRS else "benefit"
        out.append({
            "symbol": sym,
            "direction": direction,
            "rationale": str(t.get("rationale", "")).strip()[:240],
            "chg_pct": _recent_change(sym, root),
        })
    return out


def evaluate(item: dict, cfg: dict | None = None, root: Path | None = None) -> dict:
    """Run the significance gate + report for ONE White House item. Always returns a
    record (activated True/False, degraded fields flagged); never raises."""
    cfg = cfg or _cfg()
    root = Path(root) if root else config.ROOT
    now = datetime.now(timezone.utc)
    rec: dict = {
        "schema": "wh_alert.v1",
        "id": item.get("id"),
        "source_title": item.get("title"),
        "source_url": item.get("url"),
        "section": item.get("section"),
        "published": item.get("published"),
        "generated_at": now.isoformat(),
        "model": provider_label(cfg) or "(none)",
        "activated": False,
        "importance": None,
        "banner_days": None,
        "tone": "neutral",
        "banner_title": None, "banner_title_zh": None,
        "summary": None, "summary_zh": None,
        "analysis": None,
        "sectors": [], "tickers": [],
        "confidence": "low",
        "is_context_only": True,
        "disclaimer": DISCLAIMER,
        "degraded_reason": None,
        "raw_text": None,
    }

    backdrop = _macro_backdrop(root)
    user = (
        "WHITE HOUSE ANNOUNCEMENT\n"
        f"Section: {item.get('section')}\n"
        f"Published: {item.get('published')}\n"
        f"Title: {item.get('title')}\n"
        f"URL: {item.get('url')}\n"
        + (f"Market backdrop: {backdrop}\n" if backdrop else "")
        + "\nFull text:\n<<<\n" + (item.get("body") or item.get("excerpt") or "") + "\n>>>\n\n"
        "Apply the significance gate, then (only if it clears) write the alert. JSON only."
    )

    reply, reason = _call_model(SYSTEM, user, cfg)
    rec["raw_text"] = reply
    if reply is None:
        rec["degraded_reason"] = reason
        return rec
    parsed = _extract_json(reply)
    if not isinstance(parsed, dict):
        rec["degraded_reason"] = reason or "unparseable_reply"
        return rec

    importance = _coerce_int(parsed.get("importance", 0), 0, 100, 0)
    rec["importance"] = importance
    activate = _truthy(parsed.get("activate", False))
    # server-side gate: respect the model's call BUT enforce the importance floor so a
    # low-importance "activate:true" can't squat a site-wide banner.
    floor = int(cfg.get("min_importance", 60))
    if not activate or importance < floor:
        rec["activated"] = False
        if reason:
            rec["degraded_reason"] = reason
        return rec

    rec["activated"] = True
    rec["banner_days"] = _coerce_int(parsed.get("banner_days", 3), 1,
                                     int(cfg.get("max_banner_days", 7)), 3)
    tone = str(parsed.get("tone", "neutral")).strip().lower()
    rec["tone"] = tone if tone in _TONES else "neutral"
    rec["banner_title"] = str(parsed.get("banner_title", "")).strip()[:140] or item.get("title")
    rec["banner_title_zh"] = str(parsed.get("banner_title_zh", "")).strip()[:140] or None
    rec["summary"] = str(parsed.get("summary", "")).strip()[:600] or None
    rec["summary_zh"] = str(parsed.get("summary_zh", "")).strip()[:600] or None
    rec["analysis"] = str(parsed.get("analysis", "")).strip()[:6000] or None
    rec["sectors"] = _norm_sectors(parsed.get("sectors"), cfg)
    rec["tickers"] = _norm_tickers(parsed.get("tickers"), cfg, root)
    conf = str(parsed.get("confidence", "low")).strip().lower()
    rec["confidence"] = conf if conf in _CONF else "low"
    if reason:
        rec["degraded_reason"] = reason
    return rec
