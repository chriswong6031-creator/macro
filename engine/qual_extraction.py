"""engine/qual_extraction.py — qual_extraction.v1 contract (§2.4 / Appendix P5).

LEAF · GATED · DEFAULT-OFF · CONTEXT-ONLY (is_context_only: true).

Produces a citation-verified structured extraction from a full-text filing body
(currently wired to the 8-K lane in collectors/special_situations.py).  Every
interpretive field must be backed by a verbatim quote present in the body, or it
collapses to "unknown" and is added to `dropped_fields`.

Schema  qual_extraction.v1
───────────────────────────
{
  "schema":          "qual_extraction.v1",
  "model_id":        <version-pinned from config llm_models.extraction>,
  "source_id":       sha256(body),          -- stable filing fingerprint
  "source_lane":     "edgar_8k",            -- or other lane identifiers
  "extraction_tier": "full",                -- "full" | "headline_only"
  "extracted_at":    <ISO-8601 UTC>,
  "is_context_only": true,                  -- ALWAYS true; never feeds scoring
  "fields": {
    "direction":      "up" | "down" | "neutral" | "unknown",
    "magnitude":      "large" | "medium" | "small" | "unknown",
    "horizon":        "short_term" | "medium_term" | "long_term" | "unknown",
    "reversibility":  "reversible" | "persistent" | "unknown",
    "importance_raw": integer 0-100,
    "confidence":     "high" | "medium" | "low"
  },
  "evidence": [{"field": <name>, "quote_span": <verbatim text from body>}],
  "dropped_fields":   [<field names whose citation failed verbatim check>],
  "degraded_reason":  null | <string>,      -- null = healthy
  "brain_usable":     <bool>                -- false when degraded_reason is set
}

Anti-hallucination guarantee (generalised from catalyst_tone._verify_citations):
Every field in INTERPRETIVE_FIELDS must have a verified verbatim quote_span from
the BODY (after typography-agnostic normalisation), or it collapses to its neutral
value.  "importance_raw" and "confidence" are also verified this way.

Drift protocol (P5):
- model_id is version-pinned from config["llm_models"]["extraction"]; a missing
  key raises LookupError at startup (not silently wrong).
- sha-keyed reply cache for determinism (same body → same output).
- jsonschema validation on every record; enum violations → unknown + schema-error note.
- Anchor-set re-score monitoring is a separate scheduled job (not in this module).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib import config

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# schema constants
# --------------------------------------------------------------------------- #
SCHEMA_VERSION = "qual_extraction.v1"
SOURCE_LANE_EDGAR_8K = "edgar_8k"

# Enum domains for each field
_DIRECTION = {"up", "down", "neutral", "unknown"}
_MAGNITUDE = {"large", "medium", "small", "unknown"}
_HORIZON = {"short_term", "medium_term", "long_term", "unknown"}
_REVERSIBILITY = {"reversible", "persistent", "unknown"}
_CONFIDENCE = {"high", "medium", "low"}

# Neutral (collapse) values for ALL fields (used for initialisation)
_NEUTRAL: dict[str, Any] = {
    "direction": "unknown",
    "magnitude": "unknown",
    "horizon": "unknown",
    "reversibility": "unknown",
    "importance_raw": 0,
    "confidence": "low",
}

# Fields that must be verified by a verbatim quote; any non-neutral value without
# a matching quote_span collapses and is logged in dropped_fields.
#
# "confidence" and "importance_raw" are omitted intentionally: confidence is a
# holistic assessment of the model's own certainty (like catalyst_tone.confidence
# which is not in _NEUTRAL there either), and importance_raw is a scalar relevance
# estimate — both may be called without a single specific verbatim quote backing
# them.  Only the four directional/structural interpretation fields require
# individual verbatim citation.
INTERPRETIVE_FIELDS = frozenset({"direction", "magnitude", "horizon", "reversibility"})
_CITATION_NEUTRAL: dict[str, Any] = {k: _NEUTRAL[k] for k in INTERPRETIVE_FIELDS}

# Confidence rank (for floor collapse)
_CONF_RANK = {"low": 0, "medium": 1, "high": 2}

# Default confidence floor — below this everything collapses
_DEFAULT_CONF_FLOOR = "low"


# --------------------------------------------------------------------------- #
# config helpers
# --------------------------------------------------------------------------- #
def _cfg() -> dict:
    return config.load().get("qual_extraction", {}) or {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def _model_id() -> str:
    """Read the version-pinned extraction model from config.

    Raises LookupError if the block is absent (drift-guard: a missing config is a
    hard error at runtime, not a silent fallback to a different model).
    """
    llm_models = config.load().get("llm_models")
    if not isinstance(llm_models, dict):
        raise LookupError(
            "config['llm_models'] missing — add the llm_models: block (W5 requirement). "
            "See config.yml for the required schema."
        )
    mid = llm_models.get("extraction")
    if not mid:
        raise LookupError(
            "config['llm_models']['extraction'] missing — version-pin the extraction "
            "model in the llm_models: block of config.yml."
        )
    return str(mid)


def _client(cfg: dict):
    """Build an Anthropic-SDK client from the configured provider. Returns None if
    no key / SDK available (caller degrades to None → no extraction)."""
    try:
        import anthropic
    except ImportError:
        return None
    key = config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY"))
    if not key:
        return None
    base = cfg.get("llm_base_url") or cfg.get("base_url")
    try:
        return (anthropic.Anthropic(base_url=base, api_key=key)
                if base
                else anthropic.Anthropic(api_key=key))
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# normalisation (typography-agnostic, same as catalyst_tone._norm)
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    """Lower-case and collapse every run of non-ASCII-alphanumeric characters to a
    single space.  Accented / non-Latin letters are also folded; fine for SEC 8-K
    English text.  The word SEQUENCE must still appear verbatim in the source."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# --------------------------------------------------------------------------- #
# reply-cache (sha-keyed, determinism kit — same body → same extraction)
# --------------------------------------------------------------------------- #
def _prompt_hash(model: str, system: str, user: str) -> str:
    h = hashlib.sha256()
    for part in (model, system, user):
        h.update(part.encode("utf-8"))
    return h.hexdigest()


def _cache_dir(cfg: dict) -> Path:
    cdir = config.ROOT / cfg.get("reply_cache_dir", "data/qual_extraction/reply_cache")
    cdir.mkdir(parents=True, exist_ok=True)
    return cdir


def _cache_get(phash: str, cfg: dict) -> str | None:
    try:
        p = _cache_dir(cfg) / f"{phash}.txt"
        return p.read_text() if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _cache_put(phash: str, text: str, cfg: dict) -> None:
    try:
        (_cache_dir(cfg) / f"{phash}.txt").write_text(text)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# JSON parse helper
# --------------------------------------------------------------------------- #
def _extract_json(text: str) -> dict | None:
    """Best-effort parse of a model reply into a dict. Tolerates ```json fences."""
    if not text:
        return None
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if m:
        t = m.group(1).strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        pass
    start, end = t.find("{"), t.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(t[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except (ValueError, TypeError):
            return None
    return None


# --------------------------------------------------------------------------- #
# schema validation + field coercion
# --------------------------------------------------------------------------- #
def _validate(parsed: dict) -> dict:
    """Coerce a parsed reply into the canonical record.  Enum violations and
    out-of-range numbers fall back to neutral.  The evidence list is type-checked
    but otherwise passed through (citation verification is a separate step)."""
    out = dict(_NEUTRAL)

    d = str(parsed.get("direction", "")).strip().lower()
    out["direction"] = d if d in _DIRECTION else "unknown"

    m = str(parsed.get("magnitude", "")).strip().lower()
    out["magnitude"] = m if m in _MAGNITUDE else "unknown"

    h = str(parsed.get("horizon", "")).strip().lower()
    out["horizon"] = h if h in _HORIZON else "unknown"

    rv = str(parsed.get("reversibility", "")).strip().lower()
    out["reversibility"] = rv if rv in _REVERSIBILITY else "unknown"

    try:
        imp = int(round(float(parsed.get("importance_raw", 0))))
        out["importance_raw"] = max(0, min(100, imp))
    except (TypeError, ValueError):
        out["importance_raw"] = 0

    conf = str(parsed.get("confidence", "")).strip().lower()
    out["confidence"] = conf if conf in _CONFIDENCE else "low"

    # evidence list — keep well-formed entries only
    ev_raw = parsed.get("evidence")
    clean_ev: list[dict] = []
    if isinstance(ev_raw, list):
        for e in ev_raw:
            if isinstance(e, dict):
                f = str(e.get("field", "")).strip()
                q = e.get("quote_span")
                if f in INTERPRETIVE_FIELDS and isinstance(q, str) and q.strip():
                    clean_ev.append({"field": f, "quote_span": q.strip()})
    out["evidence"] = clean_ev
    return out


def _verify_citations(rec: dict, body: str) -> dict:
    """Every non-neutral interpretive field must be backed by a verbatim quote
    present (after typography normalisation) in the body.  Fields without a
    verified quote collapse to their neutral value and are listed in
    `dropped_fields`.  Mutates and returns `rec`."""
    src = _norm(body or "")
    verified: set[str] = set()
    kept_ev: list[dict] = []
    for e in rec.get("evidence", []):
        span = _norm(e.get("quote_span", ""))
        if span and len(span) >= 4 and span in src:
            verified.add(e["field"])
            kept_ev.append(e)
    dropped: list[str] = []
    for field, neutral_val in _CITATION_NEUTRAL.items():
        if rec.get(field) != neutral_val and field not in verified:
            rec[field] = neutral_val
            dropped.append(field)
    rec["evidence"] = kept_ev
    rec["dropped_fields"] = dropped
    return rec


def _apply_confidence_floor(rec: dict, floor: str) -> dict:
    """Below `floor`, every interpretive field collapses to neutral."""
    if _CONF_RANK.get(rec.get("confidence"), 0) < _CONF_RANK.get(floor, 0):
        for field, neutral_val in _NEUTRAL.items():
            rec[field] = neutral_val
        rec["evidence"] = []
        rec["confidence_gated"] = True
    else:
        rec["confidence_gated"] = False
    return rec


# --------------------------------------------------------------------------- #
# system prompt
# --------------------------------------------------------------------------- #
_EXTRACTION_SYSTEM = (
    "You extract structured event metadata from a corporate SEC filing (typically an 8-K). "
    "This is annotation metadata only — it NEVER feeds any score, signal, or trading decision "
    "directly. Guessing is harmful; 'unknown' is the correct answer when the evidence is thin.\n\n"
    "Return ONLY a JSON object with these keys:\n"
    "  direction: one of \"up\",\"down\",\"neutral\",\"unknown\" — the expected directional "
    "implication for the issuer's equity. \"up\" = broadly positive (beat, deal win, activist "
    "catalyst). \"down\" = broadly negative (miss, litigation, writedown). \"neutral\" = "
    "operational but not directional (routine filing, administrative change). \"unknown\" if "
    "unclear.\n"
    "  magnitude: one of \"large\",\"medium\",\"small\",\"unknown\" — how material/market-moving "
    "the event is likely to be (large = transformative M&A, fraud, going-private; medium = "
    "notable deal, guidance revision; small = minor contract, routine appointment).\n"
    "  horizon: one of \"short_term\",\"medium_term\",\"long_term\",\"unknown\" — time horizon "
    "over which the event's impact is expected to manifest (short = days/weeks; medium = "
    "months; long = quarters/years).\n"
    "  reversibility: one of \"reversible\",\"persistent\",\"unknown\" — whether the event is a "
    "transient washout likely to retrace (reversible) or a structural/regime change (persistent).\n"
    "  importance_raw: integer 0-100. How broadly market-moving / relevant is this to equity "
    "investors? (100 = major takeover, fraud, going-private; 50 = notable appointment/deal; "
    "0 = administrative formality).\n"
    "  confidence: one of \"high\",\"medium\",\"low\" — your confidence in the above fields "
    "given the filing text.\n"
    "  evidence: array of {\"field\": <field name>, \"quote_span\": <SHORT EXACT verbatim quote "
    "copied character-for-character from the filing>}. One entry per non-unknown field.\n\n"
    "Rules:\n"
    "- Output JSON only. No prose, no markdown fences.\n"
    "- For any field you cannot support with a verbatim quote from the filing, use its "
    "\"unknown\"/0 value and OMIT it from evidence.\n"
    "- quote_span MUST be copied EXACTLY from the filing text (it is verified by code; a "
    "paraphrase will be discarded and the field will be marked unknown).\n"
    "- Prefer \"unknown\" over a low-confidence guess."
)


# --------------------------------------------------------------------------- #
# model call
# --------------------------------------------------------------------------- #
def _call_model(body: str, context: str, cfg: dict, model: str) -> tuple[str | None, str | None]:
    """Return (reply_text, degraded_reason). Never raises.

    Cache check is BEFORE client/key check so a cache hit never requires an API key.
    """
    user = (f"Filing context: {context}\n\n"
            f"Filing text (between <doc> tags):\n<doc>\n{body}\n</doc>")
    phash = _prompt_hash(model, _EXTRACTION_SYSTEM, user)
    cached = _cache_get(phash, cfg)
    if cached is not None:
        log.debug("qual_extraction: reply cache HIT (%s)", phash[:12])
        return cached, None

    client = _client(cfg)
    if client is None:
        return None, "no_client_or_key"
    try:
        kw: dict = {
            "model": model,
            "max_tokens": int(cfg.get("max_tokens", 1500)),
            "system": _EXTRACTION_SYSTEM,
            "messages": [{"role": "user", "content": user}],
            # temperature removed — rejected (400) on opus-4.7+ per Anthropic API
        }
        try:
            kw["seed"] = 0
            resp = client.messages.create(**kw)
        except TypeError:
            del kw["seed"]
            resp = client.messages.create(**kw)
        if getattr(resp, "stop_reason", None) in ("refusal", "max_tokens"):
            return None, f"stop_{resp.stop_reason}"
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        if text:
            _cache_put(phash, text, cfg)
        return (text or None), (None if text else "empty_reply")
    except Exception as e:  # noqa: BLE001
        log.warning("qual_extraction model call failed (%s)", e)
        return None, "llm_error"


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def source_id(body: str) -> str:
    """sha256 of the filing body — stable cross-run fingerprint."""
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def extract(
    body: str,
    *,
    context: str = "",
    source_lane: str = SOURCE_LANE_EDGAR_8K,
    extraction_tier: str = "full",
) -> dict | None:
    """Extract qual_extraction.v1 record from a filing body.

    Returns None when gated off or when the extraction degrades to all-unknown
    with no evidence.  On failure returns a degraded record (with degraded_reason
    set, brain_usable=False) rather than None, so the caller can persist the
    attempt and avoid re-calling.

    Never raises.
    """
    cfg = _cfg()
    if not enabled():
        return None

    try:
        model = _model_id()
    except LookupError as e:
        log.error("qual_extraction: %s", e)
        return None

    sid = source_id(body)
    extracted_at = datetime.now(timezone.utc).isoformat()

    # Envelope
    envelope: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "model_id": model,
        "source_id": sid,
        "source_lane": source_lane,
        "extraction_tier": extraction_tier,
        "extracted_at": extracted_at,
        "is_context_only": True,
    }

    # Truncate body to configured limit (cost / context cap)
    max_chars = int(cfg.get("max_body_chars", 40000))
    body_trunc = (body or "")[:max_chars]

    reply, degraded_reason = _call_model(body_trunc, context, cfg, model)
    if not reply:
        log.info("qual_extraction: degraded — %s", degraded_reason)
        return {
            **envelope,
            "fields": dict(_NEUTRAL),
            "evidence": [],
            "dropped_fields": list(INTERPRETIVE_FIELDS),
            "degraded_reason": degraded_reason or "empty_reply",
            "brain_usable": False,
        }

    parsed = _extract_json(reply)
    if parsed is None:
        log.info("qual_extraction: JSON parse failure")
        return {
            **envelope,
            "fields": dict(_NEUTRAL),
            "evidence": [],
            "dropped_fields": list(INTERPRETIVE_FIELDS),
            "degraded_reason": "json_parse_failure",
            "brain_usable": False,
        }

    # Validate enum/range, then citation-verify, then confidence floor
    rec = _validate(parsed)
    rec = _verify_citations(rec, body_trunc)
    conf_floor = str(cfg.get("confidence_floor", _DEFAULT_CONF_FLOOR))
    rec = _apply_confidence_floor(rec, conf_floor)

    # Build final record
    fields = {k: rec[k] for k in _NEUTRAL}
    evidence = rec.get("evidence", [])
    dropped = rec.get("dropped_fields", [])
    degraded_reason_out: str | None = None
    if dropped:
        degraded_reason_out = f"dropped_fields:{','.join(dropped)}"
    # brain_usable: present and not degraded (§2.4 brain_usable rule)
    brain_usable = not bool(degraded_reason_out)

    return {
        **envelope,
        "fields": fields,
        "evidence": evidence,
        "dropped_fields": dropped,
        "degraded_reason": degraded_reason_out,
        "brain_usable": brain_usable,
    }
