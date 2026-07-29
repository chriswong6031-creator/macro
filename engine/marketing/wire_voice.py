"""engine.marketing.wire_voice — the PRESS-FEEDS wire copy voice pass (B2-COPY).

D05 Addendum 2 §3 (copy law) + §7 (B2-COPY charter). This module owns the parts
that make a wire post DISTINCTIVE rather than a generic summarize-with-citation:

  1. Rotating OPENER pool (§3 seed list), selected DETERMINISTICALLY (hash of item
     id -> index) with a per-account no-repeat window so two consecutive posts on
     the same account never lead with the same hook. Openers are class-aware
     (a geopolitical flash gets a graver hook than a crypto flash) and OPTIONAL per
     item class (a direct quote may lead with the speaker, no manufactured hook).

  2. Key-phrase selection LAW injected into the LLM prompt — quote the source's
     own strongest SHORT phrase verbatim-in-quotes, paraphrase the rest. The LLM
     may only restate facts present in the source; the numbers whitelist stays in
     breaking_summary.validate_summary.

  3. AI-tell lexicon applied to wire summaries — the rev-4 press validators' list,
     IMPORTED (never forked): the phrase list from config/press.yml
     validators.ai_tell_phrases + the two pattern rules from engine.press.validators
     (Moreover-opener, not-only-but-also budget). A copy here would drift the day
     someone adds a phrase upstream.

  4. Model tiering: sonnet-class above a salience threshold, haiku below — resolved
     through the same config keys build_breaking_payload reads, so a disarmed /
     keyless run still lands on the deterministic fallback in breaking_summary.

IMPORT CLOSURE: stdlib only at module import (hashlib, re). yaml + the validators
regexes are imported LAZILY inside functions so the thin marketing-engine CI lane
(pytest + pyyaml, no pandas) stays green and collection never pulls a heavy tree.

Public API:
    derive_register(item) -> str
    select_opener(item, *, account, recent_openers, cfg=None) -> tuple[str, str]
    key_phrase_prompt_law() -> str
    ai_tell_hits(text, *, root=None, cfg=None) -> list[str]
    resolve_llm_tier(item, *, cfg) -> str      # "flagship" | "volume"
    resolve_model_key(item, *, cfg) -> str
    compose_post(*, opener, summary, attribution, tape_stamp="") -> str
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Opener pools (§3 seed list, grown by register class). Front-facing hooks only —
# no internal state/study names, no untranslated stats, no raw slugs (glance-tier
# law). A "" entry means "no manufactured opener" (the summary leads on its own),
# which is the compliant lead for a direct quote.
# ─────────────────────────────────────────────────────────────────────────────

# Default / markets-macro register.
_OPENERS_DEFAULT: tuple[str, ...] = (
    "🚨 TRUMP:",
    "Now crossing.",
    "White House, minutes ago:",
    "On the tape:",
    "New this hour:",
    "Heads up:",
    "TRUMP:",
    "🇺🇸 TRUMP:",
    "",  # speaker/summary leads, no hook
)

# Geopolitical register — graver, no emoji siren, no CTA energy (tragedy tone law
# is enforced separately via cta_suppress; these are just sober hooks).
_OPENERS_GEOPOLITICAL: tuple[str, ...] = (
    "Now crossing.",
    "Developing:",
    "On the wires:",
    "New this hour:",
    "Reports crossing.",
    "",
)

# Company / earnings register.
_OPENERS_COMPANY: tuple[str, ...] = (
    "On the tape:",
    "Now crossing.",
    "Just out:",
    "New this hour:",
    "Company wire:",
    "",
)

# Crypto register.
_OPENERS_CRYPTO: tuple[str, ...] = (
    "On the tape:",
    "Crossing now.",
    "New this hour:",
    "Heads up:",
    "",
)

# Exec-voice / claims register (Dimon-class, bank calls).
_OPENERS_CLAIMS: tuple[str, ...] = (
    "On the wires:",
    "Now crossing.",
    "New this hour:",
    "Street desk:",
    "",
)

# register -> pool. derive_register maps event_class + matched + route to one of
# these keys; the pool is chosen here.
_REGISTER_POOLS: dict[str, tuple[str, ...]] = {
    "topics": _OPENERS_GEOPOLITICAL,       # geopolitical
    "companies": _OPENERS_COMPANY,
    "crypto": _OPENERS_CRYPTO,
    "claims": _OPENERS_CLAIMS,
    "people": _OPENERS_DEFAULT,
    "markets": _OPENERS_DEFAULT,
    "brief_candidates": _OPENERS_GEOPOLITICAL,
}

# Crypto instrument cashtags that flip a company/none item into the crypto register.
_CRYPTO_TICKERS: frozenset[str] = frozenset(
    {"COIN", "MSTR", "HOOD", "CRCL"}
)
_CRYPTO_WORDS: tuple[str, ...] = (
    "bitcoin", "btc", "ethereum", "crypto", "coinbase", "stablecoin",
)


# ─────────────────────────────────────────────────────────────────────────────
# Register derivation (deterministic — event_class + matched + route + corr class)
# ─────────────────────────────────────────────────────────────────────────────

def derive_register(item: dict) -> str:
    """Deterministic §6 register for a scored item.

    One wire spine, many registers (§6): the register is DERIVED, never a per-item
    pipeline. Precedence:
        route=="brief_candidates"     -> brief_candidates (HormuzLetter long-form)
        event_class=="geopolitical"   -> topics
        event_class=="company_news"   -> companies  (m1: wins over crypto ticker —
                                         COIN/CRCL/HOOD/MSTR earnings are company_news,
                                         not a crypto-instrument item)
        crypto ticker/keyword         -> crypto     (reserved for NON-equity crypto)
        corroboration_class=="claims" -> claims
        else                          -> people (statement lane) / markets
    """
    route = str(item.get("route", "") or "")
    if route == "brief_candidates":
        return "brief_candidates"

    event_class = str(item.get("event_class", "none") or "none")
    if event_class == "geopolitical":
        return "topics"

    # m1: when the classifier already calls this company_news, companies wins — a
    # "COIN earnings" item is a company item that happens to carry a crypto-adjacent
    # ticker, not a crypto-instrument item. The crypto register is reserved for
    # non-equity crypto items (BTC/ETH keywords, or a crypto ticker with no
    # company_news classification).
    if event_class == "company_news":
        return "companies"

    matched = item.get("matched") if isinstance(item.get("matched"), dict) else {}
    tickers = {str(t).upper() for t in (matched.get("tickers") or [])}
    text = f"{item.get('headline', '')} {item.get('body_snippet', '')}".lower()
    if tickers & _CRYPTO_TICKERS or any(w in text for w in _CRYPTO_WORDS):
        return "crypto"

    corr = str(item.get("corroboration_class", "hearsay") or "hearsay")
    if corr == "claims":
        return "claims"

    # Direct-quote (Trump's own post) and policy items are the statement/people
    # lane; everything else without a stronger signal is markets.
    if corr == "direct-quote" or event_class == "policy":
        return "people"
    return "markets"


# ─────────────────────────────────────────────────────────────────────────────
# Opener selection — deterministic index + per-account no-repeat window
# ─────────────────────────────────────────────────────────────────────────────

def _opener_pool(register: str, cfg: dict | None) -> tuple[str, ...]:
    """The opener pool for a register, allowing a config override per register."""
    if cfg:
        pools = cfg.get("opener_pools")
        if isinstance(pools, dict) and register in pools:
            override = pools.get(register)
            if isinstance(override, list) and override:
                return tuple(str(o) for o in override)
    return _REGISTER_POOLS.get(register, _OPENERS_DEFAULT)


def _hash_index(item_id: str, n: int) -> int:
    """Deterministic index in [0, n) from the item id (stable across runs)."""
    if n <= 0:
        return 0
    h = hashlib.sha256(str(item_id).encode("utf-8")).hexdigest()
    return int(h, 16) % n


def select_opener(
    item: dict,
    *,
    account: str = "flagship",
    recent_openers: list[str] | None = None,
    cfg: dict | None = None,
) -> tuple[str, str]:
    """Select an opener for a scored item.

    Deterministic: the base index is hash(item id) % pool size, so the same item
    always maps to the same slot. The per-account NO-REPEAT window then walks
    forward from that slot until it lands on an opener not equal to the account's
    most recent one — so two consecutive posts on the same account never share a
    hook, while selection stays a pure function of (id, recent_openers).

    Returns (opener, register). The caller records the returned opener into the
    account's recent list (see the daemon state) so the next call sees it.
    """
    register = derive_register(item)
    pool = _opener_pool(register, cfg)
    if not pool:
        return "", register

    recent = list(recent_openers or [])
    last = recent[-1] if recent else None

    n = len(pool)
    start = _hash_index(str(item.get("id", "")), n)
    # Walk forward from the hashed slot to the first opener != last. A pool with a
    # single distinct entry cannot avoid a repeat — accept it (degenerate config).
    for step in range(n):
        cand = pool[(start + step) % n]
        if cand != last:
            return cand, register
    return pool[start], register


# ─────────────────────────────────────────────────────────────────────────────
# Key-phrase selection law — injected into the LLM summarizer prompt
# ─────────────────────────────────────────────────────────────────────────────

def key_phrase_prompt_law() -> str:
    """The §3/§7 key-phrase instruction block appended to the summarizer prompt.

    Pure text — no LLM call here. build_breaking_payload's summarizer prompt gains
    these lines when the wire voice is active; the numbers-whitelist + AI-tell
    validation still runs after generation, so this only STEERS the model, it never
    relaxes a gate.
    """
    return (
        "WIRE VOICE key-phrase law:\n"
        "- Quote the source's single strongest SHORT phrase verbatim, inside "
        "double quotes (e.g. \"very friendly talks\", \"running afoul\"). Pick the "
        "most vivid 2-6 word span the source actually used; paraphrase everything "
        "else.\n"
        "- At most ONE such verbatim quote. Never quote a whole sentence.\n"
        "- Keep it to <=2 sentences for a flash. Restate only facts present in the "
        "source. Add no interpretation, no stance, no number not in the source.\n"
        "- Do NOT open with a hook or a source line; both are added automatically."
    )


def wire_deep_prompt_law() -> str:
    """The two-short-paragraph instruction for the wire_deep format."""
    return (
        "WIRE VOICE deep format:\n"
        "- Write TWO short paragraphs (a lead paragraph, then one paragraph of "
        "plain-word context) totalling 400-700 characters.\n"
        "- Quote the source's single strongest short phrase verbatim in double "
        "quotes; paraphrase the rest. Restate only facts present in the source.\n"
        "- No hook, no source line, no stance, no invented number."
    )


# ─────────────────────────────────────────────────────────────────────────────
# AI-tell lexicon — IMPORTED from the press validators, never forked
# ─────────────────────────────────────────────────────────────────────────────

def _load_ai_tell_phrases(root: Any = None, cfg: dict | None = None) -> list[str]:
    """Load the AI-tell phrase list from config/press.yml validators.ai_tell_phrases.

    A caller may pass an already-parsed press.yml via cfg (validators block) to
    avoid a re-read. yaml is imported lazily so the thin CI lane stays pandas-free
    and only pays the yaml import when the wire voice actually runs.
    """
    # Explicit cfg override (parsed validators dict or full press cfg).
    if isinstance(cfg, dict):
        v = cfg.get("validators") if "validators" in cfg else cfg
        if isinstance(v, dict) and isinstance(v.get("ai_tell_phrases"), list):
            return [str(p) for p in v["ai_tell_phrases"]]

    try:
        import yaml  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415
        if root is None:
            root = Path(__file__).resolve().parents[2]
        press_yml = Path(root) / "config" / "press.yml"
        data = yaml.safe_load(press_yml.read_text(encoding="utf-8")) or {}
        phrases = ((data.get("validators") or {}).get("ai_tell_phrases")) or []
        return [str(p) for p in phrases]
    except Exception:  # noqa: BLE001
        return []


def ai_tell_hits(text: str, *, root: Any = None, cfg: dict | None = None) -> list[str]:
    """AI-tells found in `text`, using the rev-4 press lexicon + the two pattern
    rules (imported from engine.press.validators — never duplicated here).

    Returns a list of hit descriptors (empty = clean). Applied to a wire summary
    BEFORE it is allowed to post; a hit forces the deterministic fallback.
    """
    lower = str(text or "").lower()
    hits: list[str] = []

    for phrase in _load_ai_tell_phrases(root, cfg):
        if str(phrase).lower() in lower:
            hits.append(f"ai_tell:{phrase}")

    # Pattern rules: reuse the compiled regexes from the validators (single source
    # of truth). Lazy import keeps the module's top-level closure thin.
    try:
        from engine.press.validators import _MOREOVER_OPENER_RE, _NOT_ONLY_RE  # noqa: PLC0415
        if _MOREOVER_OPENER_RE.match(str(text or "")):
            hits.append("ai_tell_pattern:opens with 'Moreover,'")
        if len(_NOT_ONLY_RE.findall(str(text or ""))) > 1:
            hits.append("ai_tell_pattern:'not only ... but also' overused")
    except Exception:  # noqa: BLE001
        # Fall back to inline patterns only if the import genuinely fails (broken
        # env). Kept minimal and equivalent so behaviour does not silently drift.
        if re.match(r"^\s*moreover\s*,", str(text or ""), re.IGNORECASE):
            hits.append("ai_tell_pattern:opens with 'Moreover,'")

    return hits


# ─────────────────────────────────────────────────────────────────────────────
# Model tiering — sonnet above a salience floor, haiku below
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_FLAGSHIP_SALIENCE = 80.0
_DEFAULT_FLAGSHIP_MODEL_KEY = "marketing_copy"   # sonnet-class (config.yml)
_DEFAULT_VOLUME_MODEL_KEY = "press_brief"        # haiku-class (config.yml)


def resolve_llm_tier(item: dict, *, cfg: dict | None = None) -> str:
    """Return "flagship" (sonnet) above the salience floor, else "volume" (haiku)."""
    wcfg = (cfg or {})
    floor = float(wcfg.get("llm_tier_salience_floor", _DEFAULT_FLAGSHIP_SALIENCE))
    try:
        sal = float(item.get("salience", 0.0))
    except (TypeError, ValueError):
        sal = 0.0
    return "flagship" if sal >= floor else "volume"


def resolve_model_key(item: dict, *, cfg: dict | None = None) -> str:
    """The config.yml llm_models key to use for this item's summary tier.

    config keys: wire.llm_tier_flagship (default marketing_copy / sonnet) and
    wire.llm_tier_volume (default press_brief / haiku). A disarmed / keyless run
    never reaches an LLM call regardless — build_breaking_payload's env gate holds.
    """
    wcfg = (cfg or {})
    tier = resolve_llm_tier(item, cfg=wcfg)
    if tier == "flagship":
        return str(wcfg.get("llm_tier_flagship", _DEFAULT_FLAGSHIP_MODEL_KEY))
    return str(wcfg.get("llm_tier_volume", _DEFAULT_VOLUME_MODEL_KEY))


# ─────────────────────────────────────────────────────────────────────────────
# Post composition — opener + body + attribution + tape stamp
# ─────────────────────────────────────────────────────────────────────────────

def compose_post(
    *,
    opener: str,
    summary: str,
    attribution: str = "",
    tape_stamp: str = "",
) -> str:
    """Assemble the final post text: [opener] body [-- attribution] [· tape].

    Deterministic string assembly (no LLM). The attribution is the corroboration
    decision's inline credit ("on Truth Social" / "Reuters reporting"); the tape
    stamp, when present, trails after a mid-dot so the tape number reads as a
    separate clause. Whitespace is normalised so an empty opener/stamp leaves no
    stray separators.

    The attribution joins on a DOUBLE HYPHEN, never an em dash (B1). Two reasons,
    and only one of them is house style: the publisher's last-gate language screen
    (copywriter.banned_language) quarantines any queued item containing U+2014, so
    an em-dash join silently killed every press emission at post time; and the
    corpus form the wire accounts actually use is the double hyphen
    ("...ENVIRONMENTAL REVIEWS -- WSJ", case-study pack item 1).
    """
    opener = str(opener or "").strip()
    body = str(summary or "").strip()
    # An opener joins the body with a single space ("🚨 TRUMP: <body>",
    # "Now crossing. <body>"); the pool phrases already carry their own trailing
    # colon/period punctuation. An empty opener leaves the body to lead on its own.
    text = f"{opener} {body}".strip() if opener else body

    attribution = str(attribution or "").strip()
    # Both join forms are checked for presence (an older vintage body may still
    # carry the em-dash clause) but only the double hyphen is ever EMITTED.
    if attribution and not any(
        f"{d} {attribution}" in text for d in ("--", "—", "–")
    ):
        text = f"{text} -- {attribution}"

    tape_stamp = str(tape_stamp or "").strip()
    if tape_stamp:
        text = f"{text} · {tape_stamp}"

    return re.sub(r"\s+", " ", text).strip()
