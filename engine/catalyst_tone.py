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


# --------------------------------------------------------------------------- #
# pure helpers (no network) — independently unit-tested
# --------------------------------------------------------------------------- #
def _extract_json(text: str) -> dict | None:
    """Best-effort parse of a model reply into a dict. Tolerates ```json fences
    and leading/trailing prose. Returns None on failure (never raises)."""
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
    # fall back to the first balanced {...} block
    start = t.find("{")
    end = t.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(t[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except (ValueError, TypeError):
            return None
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
    """Whitespace-insensitive, case-insensitive normalization for substring
    matching a quote against the source (models often reflow whitespace)."""
    return re.sub(r"\s+", " ", s).strip().lower()


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
    """Return (reply_text, degraded_reason). Never raises."""
    client = _client(cfg)
    if client is None:
        return None, "no_client_or_key"
    user = (f"Document context: {context}\n\n"
            f"Document text follows between <doc> tags.\n<doc>\n{source_text}\n</doc>")
    try:
        resp = client.messages.create(
            model=cfg.get("llm_model", "deepseek-v4-flash"),
            max_tokens=int(cfg.get("max_tokens", 700)),
            system=CATALYST_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        if getattr(resp, "stop_reason", None) in ("refusal", "max_tokens"):
            return None, f"stop_{resp.stop_reason}"
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return (text or None), (None if text else "empty_reply")
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("catalyst_tone model call failed (%s)", e)
        return None, "llm_error"


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
        "model": cfg.get("llm_model", "deepseek-v4-flash"),
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
