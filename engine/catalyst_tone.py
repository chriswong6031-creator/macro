"""Catalyst tone — market/regime narrative DIGEST layer (LLM Tier A).

LEAF · GATED · DEFAULT-OFF · CONTEXT-ONLY. This mirrors the engine/commodity_news.py
contract exactly: it imports nothing from the mechanical core (conditions/cycles/
dislocation/calibrate), and nothing in the scoring path imports it. Every public
function returns plain data or None and NEVER raises into the pipeline — all
network / parse / LLM failures degrade to "no digest".

Role (Tier A of the two-tier LLM design — see memory llm-layer-decision):
  DIGEST one PUBLIC catalyst document (an FOMC statement/minutes, a regulatory
  release, or the catalyst text around a detected dislocation shock) into a small
  typed record:
      tone_score        float [-1,1]  net risk-off impulse: -1 strongly
                                       supportive/dovish/de-escalating ... +1
                                       strongly risk-off/hawkish/escalating
      guidance_direction enum         tightening | easing | on_hold | mixed | unknown
      risk_delta        float [-1,1]  implied change in forward market risk
                                       (-1 risk falling ... +1 risk rising)
      shock_reversible  enum          reversible | persistent | unknown
                                       (the missing dislocation Gate-1 leg: is a
                                       shock a transient washout or a regime break)
      confidence        enum          low | medium | high
      evidence          [{field, quote_span}]  VERBATIM quotes justifying each call

Runs on DeepSeek V4 Flash via its Anthropic-compatible endpoint — the very same
`anthropic` SDK and `client.messages.create(...)` shape commodity_news.py uses,
with `base_url` + `DEEPSEEK_API_KEY` swapped in. Cheap, public-docs-only.

The digest is honest CONTEXT. Promotion of any field to a deterministic feature
(e.g. shock_reversible -> dislocation Gate-1, tone/risk_delta -> a conditions.py
additive lens) happens DOWNSTREAM and is itself gated; THIS module never writes a
score. Safety lives in CODE, never in the prompt:
  (1) tolerant JSON parse (handles ```json fences / surrounding prose),
  (2) schema validation — enums, types, numeric range-clamp,
  (3) CITATION VERIFICATION — every evidence quote_span must be a verbatim
      substring of the source document, else that field is dropped to its neutral
      "unknown" value and flagged,
  (4) code-side confidence floor — below the threshold every interpretive field
      collapses to unknown,
  (5) degrade-never-raise — any failure returns a degraded record or None.
Only PUBLIC source documents are ever sent to the (third-party) model.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone

from lib import config

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# schema (also used by the validator below)
# --------------------------------------------------------------------------- #
_GUIDANCE = {"tightening", "easing", "on_hold", "mixed", "unknown"}
_REVERSIBLE = {"reversible", "persistent", "unknown"}
_CONF_RANK = {"low": 0, "medium": 1, "high": 2}
# interpretive fields that must be earned by a verbatim citation; the value each
# collapses to when unverified / low-confidence / absent.
_NEUTRAL = {
    "tone_score": 0.0,
    "guidance_direction": "unknown",
    "risk_delta": 0.0,
    "shock_reversible": "unknown",
}

DISCLAIMER_TEXT = (
    "Context only — not a signal. This is a machine DIGEST of a public document, "
    "produced by an AI model after the fact. The tone / guidance / risk / "
    "reversibility readings are background context; they are NOT inputs to any "
    "score, signal or allocation unless a downstream, separately-gated step "
    "promotes a single field, and even then only as one bounded factor. "
    "“unknown” means the evidence was insufficient — the honest answer. Every "
    "non-unknown field is backed by a quote verified to appear verbatim in the "
    "source; unverifiable claims are dropped."
)

CATALYST_SYSTEM = (
    "You DIGEST one public financial/macro document into a small JSON record. This "
    "is annotation metadata only — it never feeds any score, signal or trading "
    "decision directly. Guessing is harmful; abstaining (\"unknown\") is correct.\n\n"
    "Return ONLY a JSON object with these keys:\n"
    "  tone_score: number in [-1,1]. Net risk-off impulse of the document: -1 = "
    "strongly supportive / dovish / de-escalating, 0 = neutral, +1 = strongly "
    "risk-off / hawkish / escalating.\n"
    "  guidance_direction: one of \"tightening\",\"easing\",\"on_hold\",\"mixed\","
    "\"unknown\" — the policy/forward-guidance lean if the document states one.\n"
    "  risk_delta: number in [-1,1]. Implied change to FORWARD market risk: -1 = "
    "risk clearly falling, +1 = risk clearly rising.\n"
    "  shock_reversible: one of \"reversible\",\"persistent\",\"unknown\". ONLY when "
    "the document explains a market shock: \"reversible\" = transient / liquidity / "
    "technical washout likely to retrace; \"persistent\" = a structural or regime "
    "break. Use \"unknown\" if the document is not about a specific shock.\n"
    "  confidence: one of \"low\",\"medium\",\"high\".\n"
    "  evidence: array of {\"field\": <one of the above field names>, \"quote_span\": "
    "<a SHORT EXACT verbatim quote copied character-for-character from the "
    "document>}. Provide one entry for each non-\"unknown\" field.\n\n"
    "Rules:\n"
    "- Output JSON only. No prose, no markdown fences.\n"
    "- For any field you cannot support with a verbatim quote from the document, "
    "use its \"unknown\"/0 value and OMIT it from evidence.\n"
    "- quote_span must be copied EXACTLY from the document (it is checked by code; "
    "a paraphrase will be discarded).\n"
    "- Prefer \"unknown\"/0 over a low-confidence guess."
)


def _cfg() -> dict:
    return config.load().get("catalyst_tone", {}) or {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


def _extraction_model(cfg: dict) -> str:
    """Return the version-pinned extraction model id (W5 — P5 R5).

    Resolution order:
    1. config['llm_models']['extraction']  (version-pinned, authoritative)
    2. cfg['llm_model']                    (catalyst_tone section override)
    3. hardcoded "deepseek-v4-flash"       (emergency fallback)

    Does NOT raise — catalyst_tone may run outside the W5 llm_models requirement.
    """
    llm_models = config.load().get("llm_models") or {}
    if llm_models.get("extraction"):
        return str(llm_models["extraction"])
    if cfg.get("llm_model"):
        return str(cfg["llm_model"])
    return "deepseek-v4-flash"


# --------------------------------------------------------------------------- #
# pure helpers (no network) — independently unit-tested
# --------------------------------------------------------------------------- #
def _repair_json_text(t: str) -> str:
    """Best-effort STRUCTURAL repair of almost-valid model JSON, used only as a
    last resort after strict parsing fails. Fixes the JSON slips models actually
    make: a stray/mismatched closing bracket (e.g. a spurious ``]`` after a scalar
    value — the real failure that left a BTC brief 'unparseable'), brackets left
    open by a truncated reply, and trailing commas. String contents are never
    touched — quote/escape state is tracked so a ``]`` or ``,`` inside a value is
    preserved verbatim."""
    out: list[str] = []
    stack: list[str] = []
    in_str = esc = False
    for ch in t:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
        elif ch in "{[":
            stack.append(ch)
            out.append(ch)
        elif ch in "}]":
            if stack and ((ch == "}" and stack[-1] == "{") or (ch == "]" and stack[-1] == "[")):
                stack.pop()
                out.append(ch)
            # else: a closer with no matching opener -> drop the stray char
        else:
            out.append(ch)
    while stack:                                    # close whatever a truncation left open
        out.append("}" if stack.pop() == "{" else "]")
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))   # strip trailing commas


def _extract_json(text: str) -> dict | None:
    """Best-effort parse of a model reply into a dict. Tolerates ```json fences,
    leading/trailing prose, and — as a last resort — light structural repair of
    almost-valid JSON (stray brackets, truncation, trailing commas). Returns None
    on failure (never raises)."""
    if not text:
        return None
    t = text.strip()
    # strip a ```json ... ``` (or bare ```) fence if present
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if m:
        t = m.group(1).strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        pass
    # fall back to the first {...} block, then to a repaired version of it. The
    # block runs to the last "}" when there is one, else to end-of-text so a
    # TRUNCATED reply (opened but never closed) can still be repaired.
    start = t.find("{")
    if start < 0:
        return None
    end = t.rfind("}")
    block = t[start:end + 1] if end > start else t[start:]
    for candidate in (block, _repair_json_text(block)):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (ValueError, TypeError):
            continue
    return None


def _num_clamp(v, lo: float = -1.0, hi: float = 1.0):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return None


def _validate(parsed: dict) -> dict:
    """Coerce a parsed reply into the canonical record, enums/ranges enforced.
    Unparseable fields fall back to their neutral value (no exception)."""
    out = dict(_NEUTRAL)
    ts = _num_clamp(parsed.get("tone_score"))
    if ts is not None:
        out["tone_score"] = ts
    rd = _num_clamp(parsed.get("risk_delta"))
    if rd is not None:
        out["risk_delta"] = rd
    g = str(parsed.get("guidance_direction", "")).strip().lower()
    out["guidance_direction"] = g if g in _GUIDANCE else "unknown"
    sr = str(parsed.get("shock_reversible", "")).strip().lower()
    out["shock_reversible"] = sr if sr in _REVERSIBLE else "unknown"
    conf = str(parsed.get("confidence", "")).strip().lower()
    out["confidence"] = conf if conf in _CONF_RANK else "low"
    ev = parsed.get("evidence")
    clean_ev = []
    if isinstance(ev, list):
        for e in ev:
            if isinstance(e, dict):
                f = str(e.get("field", "")).strip()
                q = e.get("quote_span")
                if f in _NEUTRAL and isinstance(q, str) and q.strip():
                    clean_ev.append({"field": f, "quote_span": q.strip()})
    out["evidence"] = clean_ev
    return out


def _norm(s: str) -> str:
    """Typography-agnostic normalization for matching a quote against the source:
    lowercase, then collapse every run of non-ASCII-alphanumeric characters
    (whitespace, punctuation, Unicode dashes/quotes/NBSP, and mojibake fragments —
    e.g. the Fed's non-breaking hyphen U+2011 that reaches the reply as 'â€‘') to a
    single space. The actual word/number SEQUENCE must still appear verbatim in the
    source, so the anti-hallucination guarantee holds — only typographic noise is
    normalized away. (Caveat: accented/non-Latin letters in a quote are also dropped;
    fine for the English macro/FOMC docs this is used on, and it's context-only.)"""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _verify_citations(rec: dict, source_text: str) -> dict:
    """Every interpretive field must be backed by a verbatim quote present in the
    source. Fields without a verified quote collapse to their neutral value and
    are listed in `dropped_fields`. Mutates and returns `rec`."""
    src = _norm(source_text or "")
    verified: set[str] = set()
    kept_ev = []
    for e in rec.get("evidence", []):
        span = _norm(e.get("quote_span", ""))
        if span and len(span) >= 4 and span in src:
            verified.add(e["field"])
            kept_ev.append(e)
    dropped = []
    for field in _NEUTRAL:
        if rec.get(field) != _NEUTRAL[field] and field not in verified:
            rec[field] = _NEUTRAL[field]
            dropped.append(field)
    rec["evidence"] = kept_ev
    rec["dropped_fields"] = dropped
    return rec


def _apply_confidence_floor(rec: dict, threshold: str) -> dict:
    """Below the configured confidence floor, every interpretive field collapses
    to neutral (the call is logged via `confidence_gated`)."""
    if _CONF_RANK.get(rec.get("confidence"), 0) < _CONF_RANK.get(threshold, 2):
        for field in _NEUTRAL:
            rec[field] = _NEUTRAL[field]
        rec["evidence"] = []
        rec["confidence_gated"] = True
    else:
        rec["confidence_gated"] = False
    return rec


# --------------------------------------------------------------------------- #
# content-hash cache — determinism kit (W7 #33)
#
# Graded calls (shock_reversible → spvector veto, tone_score → ledger) MUST be
# reproducible: the SAME document on the SAME day must always yield the SAME
# record. We guarantee this by keying on a SHA-256 of (model, system_prompt,
# user_message) → the reply text is cached in data/catalyst/reply_cache/. A cache
# HIT returns the old bytes directly — no second model call, no sampling noise.
# The file is append-only-per-hash so two runs on the same day cannot diverge.
# --------------------------------------------------------------------------- #
def _prompt_hash(model: str, system: str, user: str) -> str:
    """SHA-256 hex of (model‖system‖user) — key for the reply cache."""
    h = hashlib.sha256()
    for part in (model, system, user):
        h.update(part.encode("utf-8"))
    return h.hexdigest()


def _reply_cache_path(prompt_hash: str, cfg: dict):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("reply_cache_dir", "data/catalyst/reply_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"{prompt_hash}.txt"


def _reply_cache_get(prompt_hash: str, cfg: dict) -> str | None:
    """Return cached reply text, or None on miss/error."""
    p = _reply_cache_path(prompt_hash, cfg)
    try:
        return p.read_text() if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _reply_cache_put(prompt_hash: str, text: str, cfg: dict) -> None:
    """Write reply text to cache. Idempotent (same hash → same file)."""
    try:
        _reply_cache_path(prompt_hash, cfg).write_text(text)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# GDELT headline snapshot — determinism kit (W7 #33)
#
# Live GDELT headlines shift intraday, so the same dislocation day can feed a
# DIFFERENT prompt on a second run → non-reproducible shock_reversible. Fix:
# snapshot the fetched headlines to a dated artifact BEFORE scoring; on a cache
# hit for the same date, reuse the snapshot instead of re-fetching.
# --------------------------------------------------------------------------- #
def _gdelt_snapshot_path(today: date, cfg: dict):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("gdelt_snapshot_dir", "data/catalyst/gdelt_snapshots")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"gdelt_{today.isoformat()}.json"


def _gdelt_snapshot_get(today: date, cfg: dict) -> list[str] | None:
    """Return cached headlines for `today`, or None on miss."""
    p = _gdelt_snapshot_path(today, cfg)
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _gdelt_snapshot_put(today: date, headlines: list[str], cfg: dict) -> None:
    """Write the headline list for `today`."""
    try:
        _gdelt_snapshot_path(today, cfg).write_text(json.dumps(headlines))
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# the model call (DeepSeek V4 Flash via the Anthropic-compatible endpoint)
# --------------------------------------------------------------------------- #
def _client(cfg: dict):
    """Build an Anthropic-SDK client pointed at the configured provider. Returns
    None if the SDK or the API key is unavailable (caller degrades)."""
    try:
        import anthropic
    except ImportError:
        return None
    key = config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY"))
    if not key:
        return None
    base = cfg.get("llm_base_url", "https://api.deepseek.com/anthropic")
    try:
        return anthropic.Anthropic(base_url=base, api_key=key)
    except Exception:  # noqa: BLE001
        return None


def _call_model(source_text: str, context: str, cfg: dict) -> tuple[str | None, str | None]:
    """Return (reply_text, degraded_reason). Never raises.

    Determinism kit (W7 #33): temperature=0 + seed=0 so the provider samples as
    deterministically as it can. Content-hash cache: the SHA-256 of (model, system,
    user) is checked FIRST — before any client/key check — so a cache hit never
    requires an API key and the same document always yields the SAME graded record.
    """
    model = _extraction_model(cfg)
    user = (f"Document context: {context}\n\n"
            f"Document text follows between <doc> tags.\n<doc>\n{source_text}\n</doc>")
    # content-hash cache check — BEFORE the client/key check (no key needed on hit)
    phash = _prompt_hash(model, CATALYST_SYSTEM, user)
    cached = _reply_cache_get(phash, cfg)
    if cached is not None:
        log.debug("catalyst_tone: reply cache HIT (%s)", phash[:12])
        return cached, None
    client = _client(cfg)
    if client is None:
        return None, "no_client_or_key"
    from engine import llm_auth

    env_var = cfg.get("api_key_env", "DEEPSEEK_API_KEY")
    providers = [{"name": "deepseek", "env_var": env_var, "cred": "present",
                  "client": client, "model": model}]

    def _do_call(_client, _model: str):
        kw: dict = {
            "model": _model,
            "max_tokens": int(cfg.get("max_tokens", 1500)),
            "system": CATALYST_SYSTEM,
            "messages": [{"role": "user", "content": user}],
            "temperature": 0,
        }
        try:
            kw["seed"] = 0
            resp = _client.messages.create(**kw)
        except TypeError:
            del kw["seed"]
            resp = _client.messages.create(**kw)
        if getattr(resp, "stop_reason", None) in ("refusal", "max_tokens"):
            return None, f"stop_{resp.stop_reason}"
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return (text or None), (None if text else "empty_reply")

    try:
        text, reason, _ = llm_auth.make_call(providers, _do_call, context="catalyst_tone")
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("catalyst_tone model call failed (%s)", e)
        return None, "llm_error"

    if text:
        _reply_cache_put(phash, text, cfg)
    return text, reason


# --------------------------------------------------------------------------- #
# public: digest one document
# --------------------------------------------------------------------------- #
def digest_document(source_text: str, kind: str = "macro", doc_id: str | None = None,
                    context: str = "", asof: date | str | None = None) -> dict | None:
    """Digest one PUBLIC catalyst document into the typed record. Returns None
    when the master switch is off; otherwise always returns a record (degraded
    fields flagged). NEVER raises into the pipeline.

    kind: free-form tag (e.g. "fomc_statement", "dislocation", "reg_release").
    context: a one-line hint passed to the model (e.g. "FOMC March 2026 statement"
             or "gold -4.1σ residual shock on 2026-06-12").
    """
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return None

    rec = {
        "schema": "catalyst_tone.v1",
        "is_context_only": True,
        "kind": kind,
        "doc_id": doc_id,
        "context": context,
        "asof": (asof.isoformat() if isinstance(asof, date) else asof),
        "digested_at": datetime.now(timezone.utc).isoformat(),
        "model": _extraction_model(cfg),
        "tone_score": 0.0, "guidance_direction": "unknown",
        "risk_delta": 0.0, "shock_reversible": "unknown",
        "confidence": "low", "evidence": [],
        "dropped_fields": [], "confidence_gated": False,
        "degraded_reason": None,
        "disclaimer": DISCLAIMER_TEXT,
    }
    if not source_text or not source_text.strip():
        rec["degraded_reason"] = "empty_source"
        return rec

    reply, reason = _call_model(source_text, context, cfg)
    if reply is None:
        rec["degraded_reason"] = reason
        return rec

    parsed = _extract_json(reply)
    if parsed is None:
        rec["degraded_reason"] = "unparseable_reply"
        return rec

    validated = _validate(parsed)
    rec.update(validated)
    _verify_citations(rec, source_text)                       # drops unverifiable fields
    _apply_confidence_floor(rec, cfg.get("llm_min_confidence", "high"))
    return rec


# --------------------------------------------------------------------------- #
# source fetch + daily snapshot — the most recent FOMC statement, digested once
# per meeting (cached) and surfaced as honest CONTEXT in latest.json.
# --------------------------------------------------------------------------- #
# FOMC decision dates (the statement is released that afternoon). Refresh yearly.
_FOMC_MEETINGS = [
    "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]
_FOMC_URL = "https://www.federalreserve.gov/newsevents/pressreleases/monetary{ymd}a.htm"


def _as_date(x: date | str | None) -> date | None:
    if x is None:
        return None
    if isinstance(x, datetime):          # datetime / pd.Timestamp -> pure date
        return x.date()                  # (Timestamp subclasses date, so this MUST precede the date check)
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def _recent_fomc(today: date, max_age_days: int) -> date | None:
    """Most recent FOMC decision on/before `today`, if within max_age_days."""
    past = [date.fromisoformat(d) for d in _FOMC_MEETINGS
            if date.fromisoformat(d) <= today]
    if not past:
        return None
    meeting = max(past)
    return meeting if (today - meeting).days <= max_age_days else None


def _html_to_statement(html: str, cap: int) -> str:
    """Crude tag-strip + best-effort trim to the FOMC statement body."""
    t = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.DOTALL | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    starts = ("Recent indicators", "Information received", "The Committee")
    ends = ("Voting for the monetary policy action", "Implementation Note",
            "Last Update", "Board of Governors")
    lo = min((i for i in (t.find(s) for s in starts) if i != -1), default=-1)
    if lo > 0:
        t = t[lo:]
    hi = min((i for i in (t.find(e) for e in ends) if i != -1), default=-1)
    if hi > 0:
        t = t[:hi]
    return t[:cap].strip()


def fetch_fomc_statement(meeting_date: date,
                         cfg: dict | None = None) -> tuple[str | None, str | None]:
    """Fetch + plain-text the FOMC statement for a decision date (public, keyless).
    Returns (text, degraded_reason); never raises."""
    cfg = cfg or _cfg()
    url = _FOMC_URL.format(ymd=meeting_date.strftime("%Y%m%d"))
    try:
        import requests
        r = requests.get(url, timeout=30,
                         headers={"User-Agent": "macro-dashboard/1.0 (research)"})
        if r.status_code != 200 or "html" not in r.headers.get("Content-Type", "").lower():
            return None, f"fetch_status_{getattr(r, 'status_code', '?')}"
        text = _html_to_statement(r.text, int(cfg.get("max_doc_chars", 20000)))
        return (text, None) if text else (None, "empty_after_strip")
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("fomc fetch failed (%s)", e)
        return None, "fetch_error"


def _cache_path(doc_id: str, cfg: dict):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("cache_dir", "data/catalyst/digest_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"{doc_id}.json"


def _cached_or_digest_fomc(meeting: date, cfg: dict) -> dict | None:
    """Return the digest for one FOMC meeting, from cache if present (the
    statement never changes) else fetch+digest. Only a SUCCESSFUL digest is
    cached, so a transient failure retries next run."""
    doc_id = f"fomc_{meeting.isoformat()}"
    cache = _cache_path(doc_id, cfg)
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except Exception:  # noqa: BLE001
            pass
    text, reason = fetch_fomc_statement(meeting, cfg)
    if not text:
        return {"schema": "catalyst_tone.v1", "is_context_only": True,
                "kind": "fomc_statement", "doc_id": doc_id, "asof": meeting.isoformat(),
                **_NEUTRAL, "confidence": "low", "confidence_gated": False,
                "evidence": [], "dropped_fields": [], "degraded_reason": reason,
                "disclaimer": DISCLAIMER_TEXT}
    rec = digest_document(text, kind="fomc_statement", doc_id=doc_id,
                          context=f"FOMC monetary-policy statement, {meeting.isoformat()}",
                          asof=meeting)
    if rec is None:                       # disabled mid-call; don't cache
        return None
    if rec.get("degraded_reason") is None:
        try:
            cache.write_text(json.dumps(rec))
        except Exception:  # noqa: BLE001
            pass
    return rec


_SNAP_KEYS = ("schema", "is_context_only", "kind", "doc_id", "asof",
              "tone_score", "guidance_direction", "risk_delta", "shock_reversible",
              "confidence", "confidence_gated", "dropped_fields", "evidence",
              "degraded_reason", "disclaimer")


def daily_snapshot(asof: date | str | None = None) -> dict | None:
    """Daily Action-step entry: digest the most recent FOMC statement (cached per
    meeting) as honest CONTEXT for latest.json. Returns None when disabled or
    when nothing is recent enough. NEVER raises into the pipeline."""
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return None
    try:
        today = _as_date(asof) or date.today()
        meeting = _recent_fomc(today, int(cfg.get("max_age_days", 120)))
        if meeting is None:
            return None
        rec = _cached_or_digest_fomc(meeting, cfg)
        if rec is None:
            return None
        return {k: rec.get(k) for k in _SNAP_KEYS}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("catalyst daily_snapshot failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# event trigger — on a dislocation day, digest that day's market news (Stage 3b)
# --------------------------------------------------------------------------- #
_GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_EVENT_QUERY = ('(stock market OR "S&P 500" OR selloff OR "Federal Reserve" OR Treasury '
                'OR "risk-off" OR volatility OR crash OR rally)')


def _fetch_event_headlines(today: date, cfg: dict) -> list[str]:
    """GDELT macro/market headlines around `today` (free, keyless). [] on any error.

    Delegates HTTP, throttling, and retry handling to engine.gdelt_client so
    all GDELT callers share a single cross-process pacing lock (GDELT 5s/IP rule;
    nine callers without shared throttle caused a penalty-box incident 2026-06-20)."""
    from datetime import timedelta
    from engine import gdelt_client as _gc
    win = int(cfg.get("event_window_days", 2))
    start = datetime(today.year, today.month, today.day) - timedelta(days=win)
    end = datetime(today.year, today.month, today.day, 23, 59, 59)
    n = int(cfg.get("event_max_records", 8))
    params = {"query": cfg.get("event_query", _EVENT_QUERY) + " sourcelang:eng",
              "mode": "artlist", "format": "json", "maxrecords": str(n), "sort": "datedesc",
              "startdatetime": start.strftime("%Y%m%d%H%M%S"),
              "enddatetime": end.strftime("%Y%m%d%H%M%S")}
    try:
        arts, _ = _gc.get_articles(params, timeout=30)
        if not arts:
            return []
        return [a.get("title", "").strip() for a in arts[:n] if a.get("title")]
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("event headline fetch failed (%s)", e)
        return []


def event_snapshot(asof: date | str | None = None, context: str = "") -> dict | None:
    """Digest the current dislocation day's market news into a shock_reversible read.
    None when disabled, event-digest off, or no headlines. NEVER raises.
    The digest text is PUBLIC headlines only (same firewall as the FOMC path).

    Determinism kit (W7 #33): GDELT headlines are snapshotted to a dated artifact
    BEFORE scoring. On a second run for the same date the snapshot is reused instead
    of re-fetching, so the input text feeding the graded shock_reversible call is
    identical and the content-hash cache can serve the same reply. This makes the
    veto reproducible even though GDELT headlines shift intraday.
    """
    cfg = _cfg()
    if not cfg.get("enabled", False) or not cfg.get("event_enabled", True):
        return None
    try:
        today = _as_date(asof) or date.today()
        # snapshot-before-score: reuse the dated snapshot if it exists, else fetch+persist
        headlines = _gdelt_snapshot_get(today, cfg)
        if headlines is None:
            headlines = _fetch_event_headlines(today, cfg)
            if headlines:
                _gdelt_snapshot_put(today, headlines, cfg)
        if not headlines:
            return None
        text = "Market headlines around the dislocation:\n" + "\n".join(f"- {h}" for h in headlines)
        rec = digest_document(text, kind="dislocation", doc_id=f"event_{today.isoformat()}",
                              context=context or "market dislocation day", asof=today)
        return {k: rec.get(k) for k in _SNAP_KEYS} if rec else None
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("catalyst event_snapshot failed (%s)", e)
        return None
