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
    source_provenance(item) -> str          # "trump_truth" | "white_house" | ""
    opener_requires_provenance(opener) -> str
    select_opener(item, *, account, recent_openers, cfg=None) -> tuple[str, str]
    key_phrase_prompt_law() -> str
    ai_tell_hits(text, *, root=None, cfg=None) -> list[str]
    ai_tell_lexicon(root=None, cfg=None) -> list[str]   # strict: raises
    resolve_llm_tier(item, *, cfg) -> str      # "flagship" | "volume"
    resolve_model_key(item, *, cfg) -> str
    strip_wire_opener(body) -> str
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

# ATTRIBUTION LAW (2026-07-31 postmortem — a FABRICATED DATELINE SHIPPED LIVE).
#
# This pool used to hold four hooks that ASSERT who said a thing or where it was
# said: "🚨 TRUMP:", "TRUMP:", "🇺🇸 TRUMP:" and "White House, minutes ago:". The
# pool was mapped to BOTH the `people` and the `markets` registers, and
# derive_register returns `markets` for every ordinary wire story — so the hook
# was drawn by hash from a pool whose contents had nothing to do with the item's
# source. On 2026-07-31 a MarketWatch story about three Fed dissenters posted on
# the flagship datelined "White House, minutes ago:". That is a fabricated
# attribution on a finance account: nobody at the White House said it, and the
# item had never been near a White House feed.
#
# The rule now: an opener that names a SPEAKER or a VENUE is a dateline, and a
# dateline is a factual claim about provenance. It may attach ONLY to an item
# whose own source IS that speaker/venue (see `source_provenance`). Ordinary wire
# items draw from non-attributive pools, which say only what is true of every
# item on this lane — that it just crossed a wire.
#
# Enforcement is belt AND braces: the pools below are separated by provenance,
# AND `select_opener` filters any attributive opener out of a pool the item's
# provenance does not license — which also covers a `wire.opener_pools` config
# override that re-introduces one.

# Default / markets-macro register. NON-ATTRIBUTIVE by construction: every hook
# here is a statement about the wire ("this just crossed"), which is true of
# every item this lane processes, and about nothing else.
_OPENERS_DEFAULT: tuple[str, ...] = (
    "Now crossing.",
    "On the tape:",
    "New this hour:",
    "Heads up:",
    "",  # summary leads, no hook
)

# Statement/people register (a policy item, or a direct quote whose speaker feed
# we could NOT confirm). Non-attributive: without confirmed provenance the copy
# may report that a statement crossed, never stamp it with a name.
_OPENERS_PEOPLE: tuple[str, ...] = (
    "Now crossing.",
    "On the wires:",
    "New this hour:",
    "Heads up:",
    "",
)

# SPEAKER register — Trump's own post, reached ONLY through a Truth Social
# provenance check (the trumpstruth / CNN-archive mirrors, a truth_status_id, or
# a truthsocial.com/trumpstruth.org URL). These hooks assert "Trump said this",
# so the item's source has to BE Trump saying it.
_OPENERS_SPEAKER_TRUMP: tuple[str, ...] = (
    "🚨 TRUMP:",
    "TRUMP:",
    "🇺🇸 TRUMP:",
    "",  # the quote leads on its own — always compliant
)

# VENUE register — the official White House feed (whitehouse_actions /
# whitehouse.gov). "White House, minutes ago:" is a dateline and needs the
# dateline's source.
_OPENERS_WHITE_HOUSE: tuple[str, ...] = (
    "White House, minutes ago:",
    "Now crossing.",
    "New this hour:",
    "",
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

# Company / earnings register. "Company wire:" was removed in the 2026-07-31
# attribution sweep: it datelines the item to a corporate newswire release, and
# most company_news items on this lane are a REPORTER's story about a company
# (MarketWatch, CNBC), not a company's own wire. The remaining hooks claim only
# that the item crossed a wire, which is true of all of them.
_OPENERS_COMPANY: tuple[str, ...] = (
    "On the tape:",
    "Now crossing.",
    "Just out:",
    "New this hour:",
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

# Exec-voice / claims register (Dimon-class, bank calls). "Street desk:" was
# removed in the same sweep: it datelines the item to a sell-side trading desk,
# and a claims item is typically an executive on a call or a conference stage —
# a desk that never touched it.
_OPENERS_CLAIMS: tuple[str, ...] = (
    "On the wires:",
    "Now crossing.",
    "New this hour:",
    "",
)

# register -> pool. derive_register maps provenance + event_class + matched +
# route to one of these keys; the pool is chosen here. `speaker` and
# `white_house` are PROVENANCE registers — derive_register can only return them
# for an item whose own source is that speaker/venue.
_REGISTER_POOLS: dict[str, tuple[str, ...]] = {
    "topics": _OPENERS_GEOPOLITICAL,       # geopolitical
    "companies": _OPENERS_COMPANY,
    "crypto": _OPENERS_CRYPTO,
    "claims": _OPENERS_CLAIMS,
    "speaker": _OPENERS_SPEAKER_TRUMP,
    "white_house": _OPENERS_WHITE_HOUSE,
    "people": _OPENERS_PEOPLE,
    "markets": _OPENERS_DEFAULT,
    "brief_candidates": _OPENERS_GEOPOLITICAL,
}

# ─────────────────────────────────────────────────────────────────────────────
# Attribution guard — which openers are datelines, and what licenses them
# ─────────────────────────────────────────────────────────────────────────────

#: (pattern, provenance token) for every opener that ASSERTS a speaker or venue.
#: An opener matching one of these may be used ONLY when `source_provenance`
#: returns the paired token for the item. The scan runs over whatever pool is in
#: effect — including a config override — so a hook re-added by config to the
#: markets pool is dropped rather than posted.
_ATTRIBUTIVE_OPENERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\btrump\b", re.IGNORECASE), "trump_truth"),
    (re.compile(r"white\s*house", re.IGNORECASE), "white_house"),
)

#: Feed keys / URL marks that make a "TRUMP:" dateline TRUE. Both Truth Social
#: mirrors carry the status id; the URL marks catch a future mirror key.
_TRUTH_SOURCE_KEYS: frozenset[str] = frozenset({"trumpstruth", "cnn_truth_backfill"})
_TRUTH_URL_MARKS: tuple[str, ...] = ("truthsocial.com", "trumpstruth.org", "truth social")

#: Feed keys / URL marks that make a "White House" dateline TRUE — the official
#: presidential-actions feed (config/press_sources.yml wire_rss references).
_WHITE_HOUSE_SOURCE_KEYS: frozenset[str] = frozenset(
    {"whitehouse_actions", "whitehouse", "white_house"}
)
_WHITE_HOUSE_URL_MARKS: tuple[str, ...] = ("whitehouse.gov", "white house")


def _prov_blob(item: dict) -> str:
    """The provenance-bearing strings of an item, lowered and joined.

    Deliberately NOT the headline or the body: a story ABOUT the White House is
    exactly the item that must never draw a White House dateline (the 2026-07-31
    incident). Only fields that describe where the item CAME FROM are read.
    """
    parts = (
        item.get("source"), item.get("source_name"), item.get("url"),
        item.get("mirror_url"), item.get("feed_url"),
    )
    return " ".join(str(p or "") for p in parts).lower()


def source_provenance(item: dict) -> str:
    """The attribution this item's own SOURCE supports.

    Returns "trump_truth" (a Truth Social post of Trump's own), "white_house"
    (the official White House feed), or "" (an ordinary wire item — no speaker
    or venue attribution is licensed).

    Fail-CLOSED: anything unrecognised is "", which costs a distinctive hook and
    never invents a dateline. The author check on the Truth path is the same
    posture — the mirrors are Trump-only by config today, but `author:` is a
    config field, and a mirror re-pointed at another account must not keep
    stamping "TRUMP:" on someone else's words.
    """
    blob = _prov_blob(item)
    src = str(item.get("source") or "").strip().lower()

    is_truth = (
        src in _TRUTH_SOURCE_KEYS
        or bool(str(item.get("truth_status_id") or "").strip())
        or any(mark in blob for mark in _TRUTH_URL_MARKS)
    )
    if is_truth:
        who = f"{item.get('author', '')} {item.get('x_handle', '')}".strip().lower()
        # No author declared at all -> the feed key/URL already identified the
        # surface, so the mirror's own configured owner stands. A DECLARED author
        # that is not Trump revokes the hook.
        if not who or "trump" in who:
            return "trump_truth"
        return ""

    if src in _WHITE_HOUSE_SOURCE_KEYS or any(
        mark in blob for mark in _WHITE_HOUSE_URL_MARKS
    ):
        return "white_house"
    return ""


def opener_requires_provenance(opener: str) -> str:
    """The provenance token an opener asserts, or "" when it asserts none."""
    text = str(opener or "")
    if not text.strip():
        return ""
    for pattern, token in _ATTRIBUTIVE_OPENERS:
        if pattern.search(text):
            return token
    return ""


def _opener_allowed(opener: str, item: dict, provenance: str | None = None) -> bool:
    """True when this item's source licenses this opener's attribution claim."""
    needed = opener_requires_provenance(opener)
    if not needed:
        return True
    prov = source_provenance(item) if provenance is None else provenance
    return prov == needed

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
        SOURCE provenance             -> speaker / white_house  (attribution law)
        event_class=="company_news"   -> companies  (m1: wins over crypto ticker —
                                         COIN/CRCL/HOOD/MSTR earnings are company_news,
                                         not a crypto-instrument item)
        crypto ticker/keyword         -> crypto     (reserved for NON-equity crypto)
        corroboration_class=="claims" -> claims
        else                          -> people (statement lane) / markets

    PROVENANCE OUTRANKS TOPIC (2026-07-31). The attributive registers are keyed
    on where the item came FROM, never on what it is about — a wire story about
    the White House is the exact item that must not draw a White House dateline.
    They sit BELOW the geopolitical branch on purpose: the tragedy-tone law owns
    a grave story whoever said it, and a siren-emoji speaker hook on a war
    headline is the tone violation that register exists to prevent.
    """
    route = str(item.get("route", "") or "")
    if route == "brief_candidates":
        return "brief_candidates"

    event_class = str(item.get("event_class", "none") or "none")
    if event_class == "geopolitical":
        return "topics"

    provenance = source_provenance(item)
    if provenance == "trump_truth":
        return "speaker"
    if provenance == "white_house":
        return "white_house"

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

    ATTRIBUTION FILTER (2026-07-31): before anything is selected, every opener
    that asserts a speaker or a venue is dropped unless this item's own source
    licenses that claim. The register split already keeps the attributive pools
    out of ordinary items' reach; this second pass is what makes the law hold for
    a `wire.opener_pools` config override too, which is a live edit surface that
    could otherwise put "TRUMP:" back in front of a MarketWatch story.
    """
    register = derive_register(item)
    pool = _opener_pool(register, cfg)
    provenance = source_provenance(item)
    pool = tuple(o for o in pool if _opener_allowed(o, item, provenance))
    if not pool:
        # Every hook in the pool claimed provenance this item lacks. Leading with
        # the summary is always compliant, so that is the fallback — never a
        # dateline the item cannot support.
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


def ai_tell_lexicon(root: Any = None, cfg: dict | None = None) -> list[str]:
    """The AI-tell phrase list, RAISING when it cannot be read.

    `_load_ai_tell_phrases` is fail-soft by design (a style screen must not stop
    the wire), but "returned []" and "could not read config/press.yml" are then
    the same value — which is how a caller that treats the screen as a HARD gate
    silently loosens it when the file goes missing. This is the strict door for
    those callers (hot_tape_llm._ai_tell_violations): it raises on an unreadable
    or empty lexicon so the caller can say so out loud instead of passing
    everything.
    """
    if isinstance(cfg, dict):
        phrases = _load_ai_tell_phrases(root, cfg)
        if phrases:
            return phrases

    import yaml  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    if root is None:
        root = Path(__file__).resolve().parents[2]
    press_yml = Path(root) / "config" / "press.yml"
    data = yaml.safe_load(press_yml.read_text(encoding="utf-8")) or {}
    phrases = ((data.get("validators") or {}).get("ai_tell_phrases")) or []
    if not phrases:
        raise ValueError(f"{press_yml}: validators.ai_tell_phrases is empty or absent")
    return [str(p) for p in phrases]


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
# Double-opener strip — the wire's own hook, in front of ours
# ─────────────────────────────────────────────────────────────────────────────

#: The openers a wire writes into its OWN body text. Anchored at the head of the
#: body only, and the separator is required — an item that merely opens with the
#: word "Breaking" (no colon/dash) is prose, not a hook.
_WIRE_OPENERS_RE = re.compile(
    r"^\s*(?:JUST\s*IN|BREAKING|URGENT|ALERT|DEVELOPING|NEWS|FLASH|UPDATE)"
    r"\s*[:\-–—]+\s*",
    re.IGNORECASE,
)


def _split_leading_non_letters(text: str) -> tuple[str, str]:
    """Split off the run of leading NON-LETTER characters (emoji, flags, space)."""
    idx = next((i for i, ch in enumerate(text) if ch.isalpha()), len(text))
    return text[:idx], text[idx:]


def strip_wire_opener(body: str) -> str:
    """Remove an embedded wire opener ('JUST IN:', 'BREAKING:') from the head of *body*.

    Live defect 2026-08-02: "Now crossing. JUST IN: 🇺🇸🇮🇷 US CENTCOM says ..." —
    our rotating opener prepended to a body that already carried the wire's own.
    Two hooks in a row read as a scrape, and the second one is not ours to make.

    Behaviour:
      * ANCHORED. Only a hook at the head of the body is removed; a
        mid-sentence "breaking" ("the story is breaking: ...") is prose and is
        left alone.
      * STACKED hooks collapse ("BREAKING: JUST IN: text" -> "text"): the loop
        runs until nothing more matches.
      * LEADING NON-LETTERS ARE PRESERVED, IN PLACE. Real posts carry flags and
        sirens on either side of the hook. "JUST IN: 🇺🇸🇮🇷 US CENTCOM..." keeps
        its flags (they sit after the hook and simply become the new head);
        "🚨 BREAKING: text" -> "🚨 text" (they sit before it and are carried
        forward). Either way the emoji survive and their order relative to the
        surviving words is unchanged — the hook is the only thing removed.
      * NEVER EMPTIES A BODY. A body that is nothing but a hook is returned
        unchanged; deleting it would hand the composer a bald opener with no
        sentence behind it, which is worse than the doubled hook.
    """
    text = str(body or "")
    prefix = ""
    rest = text
    while True:
        lead, rest = _split_leading_non_letters(rest)
        prefix += lead
        stripped = _WIRE_OPENERS_RE.sub("", rest, count=1)
        if stripped == rest:
            break
        rest = stripped

    out = prefix + rest
    if text.strip() and not out.strip():
        return text
    return out


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
    # DOUBLE-OPENER STRIP (2026-08-02). The wire's body can already lead with the
    # wire's OWN hook ("JUST IN: ..."), and prepending ours in front of it shipped
    # "Now crossing. JUST IN: 🇺🇸🇮🇷 US CENTCOM says ...". Only when WE are adding
    # a hook: with no opener of our own the wire's is the only one there is, and
    # removing it would leave the post opening on a bald fragment.
    if opener:
        body = strip_wire_opener(body).strip()
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
