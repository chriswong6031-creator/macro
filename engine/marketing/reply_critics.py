"""engine.marketing.reply_critics — the independent critic pass (XG-W4).

Separation of powers: the drafter writes, these critics kill. Every critic here
is DETERMINISTIC except one hook, and that hook may only de-escalate.

**LLM-never-scores, extended.** Charter §2 amendment 9 puts every critic under
the law — persona, readability, and "engagement potential" included. A model may
veto a draft this module already passed; it may never rescue one this module
rejected, and it may never originate a score. ``run_critics`` enforces that
mechanically: the LLM hook is consulted only on drafts that already passed, and
its sole legal answer is "reject".

**One vocab guard.** Charter §2 amendment 12: every new copy path REUSES the
existing copywriter guard rather than re-implementing the word law, because
``scripts/check_validated_claims.py`` is a source-text grep and cannot see
runtime-generated copy. This module calls ``copywriter.banned_language`` and
``expression_dial.violations`` directly — it does not own a banned list.

The critics:

    informational_surplus  restating the parent rejects (constitution §7.2)
    corpus_near_dup        near-dup against our own recent replies
    blocklist              satire handles + sensitive-event terms
    position_consistency   contradicting our public position rejects, unless
                           the change is explained IN the draft
    persona_label          a draft interesting only because of who says it
                           rejects — deterministic proxy: it must carry at
                           least one concrete market referent
    reply_value            the E4 doctrine bar: OP-directed questions with no
                           gift, advice-column boilerplate, unclosed length and
                           one-word reactions all reject
    fact_discipline        numbers only from whitelisted own-feed values
    vocab                  the shared banned-vocab guard + the expression dial
    warmth_register        the ANTI-COLD law: a twelve-unit instrument readout
                           on an employee desk rejects, a cold RUN of replies
                           rejects, and warmth bolted on as its own sentence in
                           front of the analysis rejects
    fabrication            AM-R1 on every account: a first-person claim about a
                           life event, a purchase or a position that the
                           persona spec does not license rejects, with the
                           offending sentence quoted
    dignity                screenshot rubric; the LLM hook lives here

Public API:
    CRITICS: tuple[str, ...]
    run_critics(draft, ctx, *, llm_de_escalate=None) -> dict
    <each critic>(draft, ctx) -> dict   # {critic, verdict, reasons}
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# One tokenizer, one bar. `_extract_number_tokens` is imported rather than
# re-derived on purpose: a divergent number regex means a figure that passes
# here fails at publish time (or, worse, the reverse). The import is deliberately
# UNGUARDED — a swallowed ImportError would turn the fact-discipline critic into
# a permanently-true gate, which is the exact failure class the house traps list.
from engine.marketing.copywriter import _NUMBER_RE as _SHARED_NUMBER_RE
from engine.marketing.copywriter import _extract_number_tokens, banned_language
from engine.marketing.outbox import token_jaccard

log = logging.getLogger(__name__)

CRITICS: tuple[str, ...] = (
    "informational_surplus",
    "corpus_near_dup",
    "blocklist",
    "position_consistency",
    "persona_label",
    "reply_value",
    "fact_discipline",
    "vocab",
    "warmth_register",
    "fabrication",
    "dignity",
)

# --- thresholds (charter §8: config keys, not constants) --------------------
DEFAULT_THRESHOLDS: dict[str, float] = {
    #: Jaccard against the PARENT post. Lower than the corpus bar: a reply that
    #: is 55% the parent's own words has added nothing, even if it reads new.
    "parent_jaccard": 0.55,
    #: Jaccard against our own recent replies (same account and across desks).
    "corpus_jaccard": 0.50,
    #: W1. Below this many content units a reply is TERSE, and terseness is
    #: doing the work warmth would otherwise do — the corpus's best analytical
    #: replies are 3 to 5 units ("Support at 900-925", "Actually closer to
    #: -10%") and killing those would contradict the strongest measured effect
    #: in the data. At twelve-plus units, carrying no human register at all is a
    #: CHOICE, and that choice is the instrument-readout defect.
    "warmth_min_units": 12.0,
    #: W2. How many of the account's recent items the register share is read
    #: over, and the floor below which the run is cold.
    "warmth_window": 20.0,
    "warmth_min_history": 8.0,
    "warmth_share_floor": 0.45,
    #: W3. Content units a referent-free FIRST SENTENCE may spend before it
    #: stops being a delivery register and becomes bolted-on praise.
    "warmth_opener_units": 5.0,
}

#: Sensitive-event vocabulary. A reply desk chases live conversations, and the
#: live conversation is sometimes a disaster. These are hard stops: we do not
#: borrow distribution from a tragedy. Deliberately blunt — a false positive
#: costs one abstention, a false negative costs the account.
DEFAULT_SENSITIVE_TERMS: tuple[str, ...] = (
    "shooting", "massacre", "terror attack", "terrorist attack", "hostage",
    "earthquake", "hurricane death", "plane crash", "crash victims", "casualties",
    "funeral", "obituary", "died today", "passed away", "killed in", "death toll",
    "suicide", "overdose", "war crime", "genocide", "assassination", "kidnapped",
)

#: Contempt tells. The screenshot rubric asks one question: if this reply were
#: screenshotted next to our profile, would it read as a serious desk? These
#: never do.
_DIGNITY_TOKENS: tuple[str, ...] = (
    "idiot", "moron", "clown", "stupid", "dumbass", "shut up", "cope", "seethe",
    "ratio", "get rekt", "rekt", "lmao", "lol no", "imagine thinking", "skill issue",
    "touch grass", "cry harder", "you're wrong and", "obviously you",
)

#: A concrete market referent. The persona-label test's deterministic proxy:
#: strip the byline and the draft must still carry something a reader can check.
_MECHANISM_TOKENS: tuple[str, ...] = (
    "spread", "spreads", "curve", "basis", "funding", "inventory", "inventories",
    "capex", "margin", "margins", "breadth", "flows", "positioning", "issuance",
    "duration", "carry", "roll", "hedging", "liquidity", "estimates", "guidance",
    "revisions", "backlog", "utilization", "capacity", "yield", "yields", "credit",
    "equity", "vol", "volatility", "correlation", "dispersion", "supply", "demand",
    "earnings", "revenue", "buyback", "dividend", "leverage", "refinancing",
    "maturity", "collateral", "repo", "swap", "futures", "options", "premium",
    "discount", "valuation", "multiple", "denominator", "numerator", "shipments",
    "freight", "tonnage", "imports", "exports", "tariff", "quota", "subsidy",
    "inflation", "deflation", "payrolls", "claims", "pmi", "cpi", "ppi", "gdp",
)

#: E4 doctrine §3 (research/MARKETING_REPLY_DOCTRINE_BY_FABLE.md). The corpus's
#: median winning reply is 11 words and 2/3 of high-engagement replies are under
#: 16; only 2 of the top 60 are mini-essays, and the one that worked closed on a
#: single crisp line while the zero-like essay of the same length carried three
#: disconnected claims. Length is not the defect — UNCLOSED length is — so the
#: bar sits far above the median and kills only the rambles.
MAX_REPLY_WORDS = 60
#: The one family whose structure IS the payload, so it may run long. Named here
#: rather than in ``reply_voice`` because THIS module is what enforces it; the
#: prompt reads the constant from here.
LONG_FORM_FAMILIES: frozenset[str] = frozenset({"micro_framework"})
#: Below this many content units (words + numbers + cashtags) a reply is the
#: corpus's "one-word / near-one-word low-effort reaction" — the shape that
#: scored zero because it is too generic to be dry wit.
#: CALIBRATED AGAINST THE WINNERS, not against intuition: a floor of 4 would
#: reject "$NVDA -18.5% today" (3 units), which is the data-drop pattern the
#: doctrine is built on, and "Support at 900-925" (4) sits one unit above it.
#: 3 kills "Oh wonderful." (2) and "This." (1) and nothing that pays the room.
MIN_CONTENT_UNITS = 3

#: E4 doctrine §8 anti-pattern 1: text that could be pasted under any headline.
#: Phrases, not single words, because "risk management" is a legitimate subject
#: and "risk management matters" is a fortune cookie.
_ADVICE_BOILERPLATE: tuple[str, ...] = (
    "risk management matters", "risk management is key", "manage your risk",
    "stay informed", "avoid emotional decisions", "before jumping to conclusions",
    "watch for official statements", "do your own research", "not financial advice",
    "always remember", "it's important to remember", "it is important to remember",
    "this is a reminder", "let this be a reminder", "let this be a lesson",
    "serves as a reminder", "reminds us why", "reminds us that",
    "stick to your plan", "stay disciplined", "stay patient", "trust the process",
    "keep calm and", "diversification is key", "time in the market beats",
    "at the end of the day, ", "as always, ",
)

#: A second person in a question sentence points the question at the POSTER.
#: Doctrine §4: genuine OP-directed questions clustered in the zero-like pool
#: ("What do you think of TIPS in this environment?"), while questions that work
#: are rhetorical and aimed at everyone reading.
_SECOND_PERSON_RE = re.compile(r"\b(you|your|yours|you're|youre|u|ur)\b", re.IGNORECASE)
#: Direct asks that address the poster without needing a pronoun.
_OP_ASK_RE = re.compile(
    r"\b(thoughts|your take|any take|what do you think|how do you see|"
    r"do you think|any read|what's your|whats your)\b", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_URL_RE = re.compile(r"https?://\S+|\bwww\.\S+", re.IGNORECASE)
_MENTION_RE = re.compile(r"(?<![\w.])@[A-Za-z0-9_]{2,}")

_CASHTAG_RE = re.compile(r"\$[A-Za-z][A-Za-z0-9.\-]{0,9}\b")
#: Word tokenizer. Hyphens SPLIT (so "capex-heavy" yields "capex" and a draft is
#: never rejected merely for hyphenating a mechanism), and a bare "-" is not a
#: word — keeping it made an unrelated draft share a token with any thesis whose
#: subject contained a dash, which read as a self-contradiction.
#: Hyphenated stance words ("risk-on") are matched against the raw text instead.
_TOKEN_RE = re.compile(r"[a-z0-9']+")

#: Number forms `copywriter._extract_number_tokens` does not tokenise. That
#: regex is the SHARED bar and stays authoritative for everything it recognises;
#: this is additive coverage, not a fork. It exists because a reply is the one
#: surface where a fabricated figure reaches a hostile audience under our name,
#: and the shared tokenizer silently passes exactly the shapes finance copy
#: hallucinates most: scaled magnitudes ($4.5B, 1.2T), basis points (100bp),
#: leading-decimal ratios (0.35), signed decimals (-3.4), and thousands
#: separators (3,500 — which the shared regex reads as the bare integer "500",
#: so a whitelist entry of "3,500" would reject the true figure and admit a
#: fabricated one).
_EXTRA_NUMBER_RE = re.compile(
    r"""
    [+-]?\$?\d+(?:,\d{3})+(?:\.\d+)?   # thousands separators: 3,500 / $1,234.50
    |
    [+-]?\$?\d+\.?\d*\s?(?:[KMBT]|bn|mn|tn)\b   # scaled: $4.5B, 1.2T, 300mn
    |
    [+-]?\d+\.?\d*\s?(?:bps?|bp)\b     # basis points: 100bp, 25 bps
    |
    [+-]?\$?\d+\.\d+                   # ANY decimal: 4.25, 3.75, 1.05, -3.4
    """,
    re.VERBOSE | re.IGNORECASE,
)
# The final alternative is the load-bearing one. A policy rate, a bond yield, an
# FX cross and an unemployment print are all `X.YY` with ONE integer digit, and
# the shared regex requires `\d{2,4}\.\d{2}` for its price form — so "the 10y at
# 3.75" and "EURUSD 1.05" cleared an empty whitelist entirely. It also fixes the
# fragment bug for decimals: without a wider span, `\b\d{3,6}\b` matched the
# FRACTIONAL TAIL of 4.567 as "567", so whitelisting the true figure rejected it
# while any N.567 fabrication produced the same token.

#: Explicit change markers. Constitution §6.3 (opinion ledger) + charter §0: a
#: contradiction is legitimate when the account OWNS the change in the draft.
#: Changing your mind in public is a feature; doing it silently is the defect.
_CHANGE_MARKERS: tuple[str, ...] = (
    "changed my mind", "i was wrong", "i had this wrong", "revising", "revised",
    "updating my read", "updated my read", "earlier i said", "i said the opposite",
    "walking that back", "that call aged", "against what i wrote", "reversing",
    "no longer think", "i've flipped", "ive flipped", "correction to",
)

#: Directional antonyms for the position-consistency check. Deliberately small
#: and explicit: a fuzzy stance classifier would be an LLM judgment wearing a
#: regex costume, and the law says the LLM does not score.
_ANTONYMS: dict[str, str] = {
    "up": "down", "higher": "lower", "rising": "falling", "rise": "fall",
    "widen": "narrow", "widening": "narrowing", "wider": "tighter",
    "bullish": "bearish", "long": "short", "expand": "contract",
    "expanding": "contracting", "accelerate": "slow", "accelerating": "slowing",
    "strengthen": "weaken", "strengthening": "weakening", "steepen": "flatten",
    "steepening": "flattening", "inflation": "disinflation", "risk-on": "risk-off",
    "overbought": "oversold", "outperform": "underperform", "tighten": "loosen",
}
# Symmetric lookup.
_ANTONYMS = {**_ANTONYMS, **{v: k for k, v in _ANTONYMS.items()}}


def _verdict(name: str, reasons: list[str]) -> dict[str, Any]:
    return {"critic": name, "verdict": "reject" if reasons else "pass", "reasons": reasons}


def _words(text: str) -> set[str]:
    """Lowercased word set. Hyphenated compounds contribute their parts, so
    "capex-heavy" carries the mechanism token "capex"."""
    return set(_TOKEN_RE.findall(str(text or "").lower()))


def _threshold(ctx: dict, key: str) -> float:
    cfg = ((ctx.get("cfg") or {}).get("reply_desk") or {}).get("critic_thresholds") or {}
    return float(cfg.get(key, DEFAULT_THRESHOLDS[key]))


# ---------------------------------------------------------------------------
# 1. Informational surplus — restating the parent rejects
# ---------------------------------------------------------------------------
def informational_surplus(draft: str, ctx: dict) -> dict[str, Any]:
    """The reply must ADD something (constitution §7.2, charter §0 gate).

    Two ways to fail: high token overlap with the parent, or carrying no
    referent the parent did not already have. A reply that agrees loudly is
    semantic confetti — it borrows attention and returns nothing.
    """
    parent = str(ctx.get("parent_text") or "")
    reasons: list[str] = []
    if not parent.strip():
        return _verdict("informational_surplus", reasons)

    bar = _threshold(ctx, "parent_jaccard")
    overlap = token_jaccard(draft, parent)
    if overlap >= bar:
        reasons.append(f"restates the parent (jaccard {overlap:.2f} >= {bar:.2f})")

    draft_refs = _referents(draft)
    parent_refs = _referents(parent)
    if draft_refs and not (draft_refs - parent_refs):
        reasons.append(
            "every concrete referent in the draft is already in the parent "
            f"({sorted(draft_refs)}) — no informational surplus"
        )
    return _verdict("informational_surplus", reasons)


# ---------------------------------------------------------------------------
# 2. Near-dup against our own reply corpus
# ---------------------------------------------------------------------------
def corpus_near_dup(draft: str, ctx: dict) -> dict[str, Any]:
    """Anti-sameness across our own replies (constitution §13.7).

    Checked BOTH within the account and across the portfolio: text-similarity
    clustering is the documented fleet-linkage signal, so two desks shipping the
    same sentence is a coordination tell, not just a style lapse.
    """
    reasons: list[str] = []
    bar = _threshold(ctx, "corpus_jaccard")
    for prior in ctx.get("corpus") or []:
        text = prior.get("draft") if isinstance(prior, dict) else str(prior)
        if not text:
            continue
        sim = token_jaccard(draft, text)
        if sim >= bar:
            who = prior.get("account") if isinstance(prior, dict) else None
            scope = f" ({who})" if who and who != ctx.get("account") else ""
            reasons.append(f"near-dup of a prior reply{scope} (jaccard {sim:.2f} >= {bar:.2f})")
            break
    return _verdict("corpus_near_dup", reasons)


# ---------------------------------------------------------------------------
# 3. Blocklists — satire handles + sensitive events
# ---------------------------------------------------------------------------
def blocklist(draft: str, ctx: dict) -> dict[str, Any]:
    """Satire + sensitive events + ZERO CROSS-ACCOUNT ENGAGEMENT.

    The satire list is the SAME config key the wire lane reads
    (``config/press_sources.yml`` ``satire_blocklist``) — one list, two lanes.

    The fleet-linkage law (charter §2 amendment 6: "zero cross-account
    engagement ever — no mutual likes/reposts/replies") is enforced HERE, in
    code, not left to operator discipline. It is the STRONGER of the two
    coordination rules — the weaker one-conversation-one-owner rule already has
    a hard lock in the queue — and text-similarity clustering plus a reply from
    one of our accounts to another is precisely the signal that chain-suspends a
    linked fleet.
    """
    reasons: list[str] = []
    satire = {str(h).lower().lstrip("@") for h in (ctx.get("satire_blocklist") or [])}
    author = str(ctx.get("parent_author") or "").lower().lstrip("@")
    if author and author in satire:
        reasons.append(f"parent author {author!r} is on the satire blocklist")

    ours = {str(h).lower().lstrip("@") for h in (ctx.get("our_handles") or ()) if h}
    if ours:
        # The parent, and every ancestor author the thread context carries.
        candidates = [author] + [
            str(h).lower().lstrip("@") for h in (ctx.get("thread_authors") or ()) if h
        ]
        for who in candidates:
            if who and who in ours:
                reasons.append(
                    f"{who!r} is one of OUR accounts — zero cross-account engagement "
                    "(fleet-linkage law, charter §2 amendment 6)"
                )
                break

    # The defaults are a FLOOR, not a default-if-unset. A caller passing an
    # empty list must not be able to switch a hard blocklist off; extra terms
    # are additive.
    terms = tuple(DEFAULT_SENSITIVE_TERMS) + tuple(ctx.get("sensitive_terms") or ())
    haystack = f"{draft}\n{ctx.get('parent_text') or ''}".lower()
    for term in terms:
        if term in haystack:
            reasons.append(f"sensitive-event term in thread or draft: {term!r}")
            break
    return _verdict("blocklist", reasons)


# ---------------------------------------------------------------------------
# 4. Position consistency
# ---------------------------------------------------------------------------
def load_theses(account: str, root: Path | str | None = None) -> list[dict]:
    """Read the account's public opinion ledger, when it exists.

    XG-W3 owns the write side (``persona_memory.py``); this is a read-only
    seam so the two waves never touch the same file. Absent store => no
    contradiction is detectable, and the critic says so rather than passing
    silently on an unchecked claim.
    """
    base = Path(root) if root is not None else Path(__file__).resolve().parent.parent.parent
    path = base / "data" / "marketing" / "personas" / str(account) / "theses.jsonl"
    if not path.exists():
        return []
    try:
        from engine.marketing.ledgers import read_jsonl  # noqa: PLC0415

        return read_jsonl(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_critics: cannot read theses for %r: %s", account, exc)
        return []


def position_consistency(draft: str, ctx: dict) -> dict[str, Any]:
    """Contradicting our own recent public position rejects — unless explained.

    Charter §0 XG-W4 gate. The account may absolutely change its mind; the
    opinion ledger exists so it can. What it may not do is assert the opposite
    of an open public call while pretending the earlier call never happened.
    """
    reasons: list[str] = []
    theses = ctx.get("theses")
    if theses is None:
        theses = load_theses(str(ctx.get("account") or ""), ctx.get("root"))
    if not theses:
        return _verdict("position_consistency", reasons)

    low = draft.lower()
    if any(marker in low for marker in _CHANGE_MARKERS):
        return _verdict("position_consistency", reasons)  # owned in-draft: legal

    draft_words = _words(draft)
    for thesis in theses:
        if not isinstance(thesis, dict):
            continue
        if str(thesis.get("status") or "open").lower() not in {"open", "live", "active"}:
            continue
        subject = str(thesis.get("subject") or "")
        direction = str(thesis.get("direction") or "").lower().strip()
        if not subject or not direction:
            continue
        subject_words = _words(subject)
        if not subject_words or not (subject_words & draft_words):
            continue  # the draft is not about this thesis
        opposite = _ANTONYMS.get(direction)
        # Hyphenated stances ("risk-on") are not single word tokens, so they are
        # matched against the raw text with word boundaries either side.
        hit = bool(opposite) and (
            opposite in draft_words
            or ("-" in (opposite or "")
                and re.search(rf"(?<!\w){re.escape(opposite)}(?!\w)", low) is not None)
        )
        if hit:
            reasons.append(
                f"contradicts the open position on {subject!r} "
                f"(held {direction!r}, draft says {opposite!r}) with no change marker in-draft"
            )
            break
    return _verdict("position_consistency", reasons)


# ---------------------------------------------------------------------------
# 5. Persona-label test
# ---------------------------------------------------------------------------
def _referents(text: str) -> set[str]:
    """Concrete, checkable things in a piece of copy.

    Cashtags, numbers, and named mechanisms. Judgment adjectives are absent by
    construction — that is the point of the test.
    """
    out: set[str] = set()
    out |= {c.lower() for c in _CASHTAG_RE.findall(text or "")}
    out |= set(number_tokens(text or ""))
    words = _words(text)
    out |= {w for w in words if w in _MECHANISM_TOKENS}
    return out


def persona_label(draft: str, ctx: dict) -> dict[str, Any]:
    """A draft interesting only because of WHO says it rejects (charter §0).

    The honest version of this test is "cover the byline — is it still worth
    reading?", which is a judgment call, and judgment calls are exactly what the
    LLM may not make here. The deterministic proxy: the draft must carry at
    least one concrete market referent (ticker, level, or named mechanism).
    Judgment adjectives alone are a personality, not a contribution.

    THE ONE EXEMPTION, and it is DOUBLE GATED. ``quiet_sympathy`` is the single
    warmth move that ships without an analytical gift: eight words on a
    professional setback, then stop. It carries no referent BY DESIGN and it is
    explicitly not a growth reply — it exists for relationship maintenance and
    is measured at the floor of the corpus (0.0026 eng/view). So the exemption
    requires BOTH ``ctx["relationship_only"]`` (the producer's tier routing) AND
    ``ctx["warmth"] == "quiet_sympathy"``: either alone would be a hole big
    enough to smuggle a referent-free growth reply through.
    """
    refs = _referents(draft)
    if refs:
        return _verdict("persona_label", [])
    if (bool(ctx.get("relationship_only"))
            and str(ctx.get("warmth") or "") == "quiet_sympathy"):
        return _verdict("persona_label", [])
    return _verdict("persona_label", [
        "no concrete market referent (ticker, level, or mechanism) — the draft "
        "is interesting only because of who says it"
    ])


# ---------------------------------------------------------------------------
# 6. Reply value — the E4 doctrine bar
# ---------------------------------------------------------------------------
def _sentences(text: str) -> list[str]:
    """Sentence-ish spans. Newlines split too: the drafter's grip and doorway
    are separate paragraphs, and a paragraph break ends a thought."""
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(str(text or "")) if s.strip()]


def _content_units(text: str) -> int:
    """What a reader actually receives: words + figures + tickers.

    Cashtags and numbers count as units so a genuine data drop ("$NVDA -18.5%
    today") is never mistaken for a one-word reaction, while "Oh wonderful."
    still is. Handles and URLs count for nothing — they are addressing, not
    content.
    """
    masked = _MENTION_RE.sub(" ", _URL_RE.sub(" ", str(text or "")))
    tags = _CASHTAG_RE.findall(masked)
    body = _CASHTAG_RE.sub(" ", masked)
    nums = number_tokens(body)
    for token in nums:
        body = body.replace(token, " ")
    words = [w for w in _TOKEN_RE.findall(body.lower()) if any(c.isalpha() for c in w)]
    return len(tags) + len(nums) + len(words)


def reply_value(draft: str, ctx: dict) -> dict[str, Any]:
    """The reply doctrine's four deterministic kills (E4).

    ``research/MARKETING_REPLY_DOCTRINE_BY_FABLE.md`` §8, from the 2026-07-29
    corpus of 180 top replies plus a matched zero-like pool:

    1. **A genuine question aimed at the OP.** "What do you think of TIPS in
       this environment?" got 0 likes: it reads as a DM, asks the account to do
       work for one person, and gives bystanders nothing.
       **Narrower than "ends with a question mark" on purpose.** Rhetorical
       questions aimed at the ROOM are a WINNING pattern (30 likes in the same
       corpus), and our ``author_question`` family exists because charter §3
       makes an author reply-back the highest-value reply outcome — the corpus
       measures likes, which is not our objective function. So the kill fires
       only when the question is second-person addressed AND the draft carries
       no concrete referent outside the question: an ask with a gift attached
       still pays the room, an ask on its own does not.
    2. **Advice-column boilerplate** that would fit under any headline.
    3. **Unclosed length.** Over ``MAX_REPLY_WORDS`` rejects unless the family
       is one whose structure is the payload (``LONG_FORM_FAMILIES``). The
       family arrives in ``ctx``; an absent family is treated as short-form,
       which fails CLOSED (a rambling draft is held, never shipped, when the
       caller forgot to say which family it came from).
    4. **One-word / near-one-word reactions**, which are too generic to be the
       dry one-liner they imitate.
    """
    reasons: list[str] = []
    text = str(draft or "").strip()
    if not text:
        return _verdict("reply_value", reasons)

    low = text.lower()

    # 1. OP-directed question with nothing for the room.
    sentences = _sentences(text)
    questions = [s for s in sentences if s.endswith("?")]
    op_directed = [s for s in questions
                   if _SECOND_PERSON_RE.search(s) or _OP_ASK_RE.search(s)]
    if op_directed:
        remainder = " ".join(s for s in sentences if not s.endswith("?"))
        if not _referents(remainder):
            reasons.append(
                "question addressed to the poster with no gift for the room "
                f"({op_directed[0][:60]!r}) — the zero-like shape in the corpus"
            )

    # 2. Advice-column boilerplate.
    for phrase in _ADVICE_BOILERPLATE:
        if phrase in low:
            reasons.append(f"advice-column boilerplate: {phrase!r}")
            break

    # 3. Unclosed length.
    family = str(ctx.get("family") or "").strip()
    words = len(_TOKEN_RE.findall(low))
    if words > MAX_REPLY_WORDS and family not in LONG_FORM_FAMILIES:
        reasons.append(
            f"{words} words (bar {MAX_REPLY_WORDS}) and family {family or 'unset'!r} "
            "is not a long-form family — the corpus median winner is 11 words"
        )

    # 4. One-word reaction.
    units = _content_units(text)
    if units < MIN_CONTENT_UNITS:
        reasons.append(
            f"low-effort reaction: {units} content unit(s), floor {MIN_CONTENT_UNITS}"
        )

    return _verdict("reply_value", reasons)


# ---------------------------------------------------------------------------
# 7. Fact discipline — numbers whitelist
# ---------------------------------------------------------------------------
def number_tokens(text: str) -> list[str]:
    """Every number-like token, shared tokenizer PLUS the reply-desk additions.

    Spans are merged, not just strings: the shared regex reads "3,500" as the
    bare integer "500", so emitting both would make a whitelist entry of "3,500"
    fail on its own figure. A match wholly inside a longer match is dropped, so
    the widest reading of each figure is the one that must be whitelisted.
    """
    text = text or ""
    spans: list[tuple[int, int, str]] = []
    for regex in (_SHARED_NUMBER_RE, _EXTRA_NUMBER_RE):
        for m in regex.finditer(text):
            tok = m.group(0).strip()
            if tok:
                spans.append((m.start(), m.end(), tok))

    # Widest first, then leftmost, so containment is decided against a keeper.
    spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
    kept: list[tuple[int, int, str]] = []
    for start, end, tok in spans:
        if any(k_start <= start and end <= k_end for k_start, k_end, _ in kept):
            continue
        kept.append((start, end, tok))

    kept.sort(key=lambda s: s[0])
    out: list[str] = []
    seen: set[str] = set()
    for _, _, tok in kept:
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def fact_discipline(draft: str, ctx: dict) -> dict[str, Any]:
    """Numbers only from whitelisted own-feed values.

    Same rule as ``copywriter.validate_copy``: bare 1-2 digit integers are
    prose, everything else must have come from a fact we computed. The
    tokenizer is the shared one plus the scaled/basis-point/separator forms it
    does not recognise (see ``_EXTRA_NUMBER_RE``) — a reply is the one surface
    where a hallucinated number reaches a hostile audience with our name on it,
    so a gap here is not survivable the way it is in a scheduled post.

    A whitelist entry matches a token either exactly or with punctuation and a
    currency mark normalised away, so a fact carrying "$4.5B" licenses "4.5B".
    """
    raw_whitelist = {str(v) for v in (ctx.get("numbers_whitelist") or [])}
    normalised = {_norm_number(v) for v in raw_whitelist}
    reasons: list[str] = []
    for token in number_tokens(draft):
        if re.fullmatch(r"\d{1,2}", token):
            continue
        if token in raw_whitelist or _norm_number(token) in normalised:
            continue
        reasons.append(f"number '{token}' not in whitelist")
    return _verdict("fact_discipline", reasons)


def _norm_number(token: str) -> str:
    """Comparable form: strip currency, separators, spaces; fold case."""
    return re.sub(r"[\s,$]", "", str(token or "")).lower()


# ---------------------------------------------------------------------------
# 8. Vocab — the SHARED guard, called not forked
# ---------------------------------------------------------------------------
def vocab(draft: str, ctx: dict) -> dict[str, Any]:
    """Charter §2 amendment 12: one vocab guard, every drafter.

    ``copywriter.banned_language`` is the word law (including "validated") and
    the expression dial is the per-persona register. Neither list is duplicated
    here; a new ban added upstream binds this lane the moment it lands.
    """
    reasons: list[str] = list(banned_language(draft))
    account = str(ctx.get("account") or "")
    if account:
        try:
            from engine.marketing import expression_dial as _dial  # noqa: PLC0415

            # include_house_bans=False: banned_language already ran above, and
            # double-reporting the same violation makes the reject reason noise.
            reasons.extend(_dial.violations(
                "", draft, account=account, kind="reply",
                root=ctx.get("root"), include_house_bans=False,
            ))
        except Exception as exc:  # noqa: BLE001
            # A dial failure must not silently pass copy. Surface it as a reject
            # reason so the draft is held, not shipped unchecked.
            reasons.append(f"expression dial unavailable ({exc}) — cannot clear reply register")
    return _verdict("vocab", reasons)


# ---------------------------------------------------------------------------
# 9. Warmth register — the ANTI-COLD law
# ---------------------------------------------------------------------------
#
# THE OPERATOR NAMED THE FAILURE: replies that are "completely analytical and
# cold". This critic is that complaint turned into three deterministic checks.
#
# WHY A NEW CRITIC RATHER THAN AN EXTENSION OF `reply_value`. That critic
# enforces the doctrine's §8 anti-patterns and coldness is not one of them (the
# prior corpus never tested for it). Folding this in would put two unrelated
# laws behind one `rejected_by` label, and an operator reading a rejection would
# not know which one fired. The roster pin in `reply_queue.validate_critic_stamp`
# also makes adding a critic a LOUD, schema-visible change, which is the correct
# ceremony for a new law.
#
# WHAT THIS DELIBERATELY DOES NOT DO: it does not require warmth on any single
# reply. It cannot — the evidence points the other way per reply (pure
# analytical median eng/view 0.0122 against pure warmth 0.0032, both THIN). It
# requires that the REGISTER is not cold (W2, rolling, per account) and that no
# single reply is a twelve-unit printout (W1, length-scoped). If a future edit
# here starts asserting "every reply must contain a feeling", it has misread the
# fusion law and should stop.

#: Class A — FIRST-PERSON ANALYTICAL STANCE. What she is watching, reading,
#: waiting on, unable to settle. NEVER a transaction verb: bought/sold/own/
#: hold/long/short/up-N% belong to `expression_dial.AM_R1_DETECTORS` and are
#: BARRED, so a test pins that this list and that one are disjoint.
_STANCE_VERBS: tuple[str, ...] = (
    "watching", "watched", "reading", "read", "waiting", "wondering", "wonder",
    "noticing", "noticed", "expecting", "expected", "doubting", "doubt",
    "missing", "missed", "learning", "learned", "keep", "kept", "cannot",
    "can't", "struggle", "struggling", "was wrong", "had this wrong",
    "changed my mind", "settle", "turning over",
)
#: Distance a stance verb may sit behind its first-person pronoun and still be
#: the same clause. Wide enough for "I keep turning over", narrow enough that
#: "we" in one clause and "watched" three clauses later is not a stance.
_STANCE_GAP_CHARS = 24
_FIRST_PERSON_RE = re.compile(r"\b(?:i|we)\b", re.IGNORECASE)

#: Class B — REACTION AND EVALUATION. Phrases, not bare adjectives, wherever
#: ambiguity exists: "risk" is a subject, "the part that" is a stance.
_REACTION_TOKENS: tuple[str, ...] = (
    "fair point", "fair.", "fair,", "agreed", "worth adding", "worth saying",
    "actually", "honestly", "genuinely", "quietly", "the part that",
    "the thing that", "what strikes me", "far fetched", "far-fetched",
    "not obvious", "underrated", "overrated", "wild", "brutal", "rough",
    "grim", "neat", "fun", "impressive", "appreciated", "the whole story", "load bearing",
    "load-bearing", "people skip", "keep turning over", "hope", "sorry to see",
    "that is a rough", "the one that carries", "gets rediscovered",
    "simpler", "plainly", "the harder part", "the open question",
    "the bit i", "the human version", "the frustrating part",
    # Added when `test_every_sanctioned_opener_carries_a_warmth_marker` caught
    # four openers the drafter offers and this list could not see — the exact
    # generator-and-gate disagreement that would have made a warm reply reject
    # for coldness. Every one is a reaction or evaluation phrase, not a subject.
    "will be told", "looks different", "same read", "the plain version",
)

#: W3's discriminator. The bolted-on shape is warmth ABOUT THE POST OR THE
#: POSTER, spending a whole sentence and returning nothing — "Great point,
#: really appreciate you laying this out so clearly!" in front of the analysis.
#:
#: THIS SCOPING IS LOAD-BEARING AND WAS ADDED AFTER A FALSE POSITIVE, not for
#: safety margin. W3 phrased as "first sentence, no referent, over five units"
#: also rejects biancoresearch's cold Fed-vote correction (18 likes, 0.0067
#: eng/view) — an eleven-unit opening CLAIM with no referent in it — which is a
#: winning reply and is the doctrine's own calibration fixture. A claim and a
#: compliment are both long and referent-free; what separates them is whether
#: the sentence is ABOUT the thread rather than about the market.
_PRAISE_META_TOKENS: tuple[str, ...] = (
    "great point", "great post", "great thread", "great read", "great call",
    "good point", "good post", "well said", "well put", "nice work",
    "love this", "loved this", "thanks for", "thank you for", "appreciate",
    "appreciated", "spot on", "so true", "brilliant", "excellent",
    "insightful", "fantastic", "amazing", "laying this out", "sharing this",
    "this is gold", "underrated post", "must read", "must-read",
)


def reply_dial_for(account: str, root: Path | str | None = None) -> int:
    """The account's reply dial, read from its persona spec. 1 when unknown.

    The flagship declares no ``dial_profile`` (``expression_dial`` deliberately
    leaves it off the dial), and an unreadable spec is not evidence about a
    register — so both resolve to 1, the evidence-desk dial. That is the
    conservative direction for this critic in particular: W1 and W2 fire only at
    dial >= 2, so an unknown register is never rejected for coldness on the
    strength of a lookup failure.
    """
    try:
        from engine.marketing import expression_dial as _dial  # noqa: PLC0415

        codex = _dial.codex_for(str(account or ""), root=root)
        if codex is None:
            return 1
        return int(codex.dial("reply"))
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_critics.reply_dial_for: %s for %r", exc, account)
        return 1


def _signature_emoji_hit(draft: str, account: str,
                         root: Path | str | None = None) -> str | None:
    """Class C — the persona's GRANTED signature emoji, present in the draft.

    One emoji is a register act by construction, and the dial already caps it,
    so this class needs no threshold of its own. Read from the live codex rather
    than a list here: an emoji this module named would be a second definition of
    a signature the spec already owns.
    """
    try:
        from engine.marketing import expression_dial as _dial  # noqa: PLC0415

        codex = _dial.codex_for(str(account or ""), root=root)
        if codex is None or codex.emoji_policy != "signature-set":
            return None
        decl = codex.declared.get("signature_emoji")
        if decl is None or not decl.enabled:
            return None
        for glyph in codex.emoji_signature:
            if _dial._bare(glyph) in "".join(_dial._bare(c) for c in draft):
                return glyph
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_critics._signature_emoji_hit: %s for %r", exc, account)
    return None


def warmth_markers(draft: str, ctx: dict | None = None) -> list[str]:
    """Every human-register marker in *draft*. ``[]`` means an instrument readout.

    Three CLOSED classes, deliberately narrow. A fuzzy warmth classifier would
    be an LLM judgment wearing a regex costume and charter §2 amendment 9 says
    the LLM does not score. Marker ids come back tagged by class ("A:watching",
    "B:fair point", "C:🔍") so a rejection can name what was missing instead of
    asserting a mood.
    """
    ctx = dict(ctx or {})
    text = str(draft or "")
    low = text.lower()
    out: list[str] = []

    # Class A: first person + a stance verb inside the same clause.
    for sentence in _sentences(low):
        for pronoun in _FIRST_PERSON_RE.finditer(sentence):
            window = sentence[pronoun.end(): pronoun.end() + _STANCE_GAP_CHARS]
            for verb in _STANCE_VERBS:
                if re.search(rf"(?<!\w){re.escape(verb)}", window):
                    tag = f"A:{verb}"
                    if tag not in out:
                        out.append(tag)

    # Class B: reaction / evaluation phrases.
    for token in _REACTION_TOKENS:
        if token in low:
            tag = f"B:{token}"
            if tag not in out:
                out.append(tag)

    # Class C: the granted signature emoji.
    glyph = _signature_emoji_hit(text, str(ctx.get("account") or ""), ctx.get("root"))
    if glyph:
        out.append(f"C:{glyph}")
    return out


def _warmth_enabled(ctx: dict) -> bool:
    """``reply_desk.warmth.enabled`` — the kill switch, defaulting to ON."""
    block = ((ctx.get("cfg") or {}).get("reply_desk") or {}).get("warmth") or {}
    return bool(block.get("enabled", True))


def warmth_register(draft: str, ctx: dict) -> dict[str, Any]:
    """W1 cold printout, W2 cold register drift, W3 bolted-on warmth."""
    reasons: list[str] = []
    text = str(draft or "").strip()
    if not text or not _warmth_enabled(ctx):
        return _verdict("warmth_register", reasons)

    account = str(ctx.get("account") or "")
    dial = reply_dial_for(account, ctx.get("root"))
    markers = warmth_markers(text, ctx)

    # W1 — cold printout. THE LENGTH CONDITION IS LOAD-BEARING AND IS NOT A
    # HEDGE. flagship and founder are exempt by the dial: charter §2 amendment 3
    # pins the flagship at reply dial 1 and the doctrine's §5 register map lists
    # "anything warm" in its Never column, so a warm flagship reply is the
    # defect there, not a cold one.
    if dial >= 2 and not markers:
        units = _content_units(text)
        bar = int(_threshold(ctx, "warmth_min_units"))
        if units >= bar:
            reasons.append(
                f"cold printout: {units} content units on an employee desk "
                f"(dial {dial}) with no human register marker at all (bar "
                f"{bar} units). Terse is fine; a long instrument readout is the "
                "shape the operator named"
            )

        # W2 — cold register DRIFT. Coldness is a property of a FEED, not of a
        # reply, so the eleventh consecutive cold reply is impossible while the
        # first is free. Self-heals the moment a warm item enqueues.
        #
        # FAIL DIRECTION IS OPEN AND THAT IS A REAL COST: below
        # `warmth_min_history` this is inert, so a freshly armed account can
        # ship its first few replies cold. The mitigation is SUPPLY SIDE — the
        # drafter's warmth LRU offers a move from item one — and NOT a tighter
        # gate: making an empty history reject would block the lane at arming,
        # which is exactly the failure class that kept this desk dark.
        window = int(_threshold(ctx, "warmth_window"))
        min_history = int(_threshold(ctx, "warmth_min_history"))
        floor = float(_threshold(ctx, "warmth_share_floor"))
        mine = [row for row in (ctx.get("corpus") or [])
                if isinstance(row, dict) and str(row.get("account") or "") == account]
        recent = mine[-window:] if window > 0 else []
        if len(recent) >= min_history:
            warm = sum(1 for row in recent
                       if warmth_markers(str(row.get("draft") or ""), ctx))
            share = warm / len(recent)
            if share < floor:
                reasons.append(
                    f"cold register: {warm} of this desk's last {len(recent)} "
                    f"replies carry any human register (share {share:.2f} < "
                    f"{floor:.2f}) and this one carries none either"
                )

    # W3 — bolted-on warmth. Kills "Great point, really appreciate you laying
    # this out so clearly!" in front of the analysis, and permits every
    # sanctioned opener: the fused ones are not standalone sentences at all, and
    # the sentence-terminating ones are short or carry a referent
    # ("Much appreciated:" is 2 units, and "Fair point but" is fused).
    #
    # NOT dial-scoped: a bolted-on praise sentence is the wrong shape on every
    # desk, including the flagship, where it is worse.
    sentences = _sentences(text)
    if sentences:
        head = sentences[0]
        head_low = head.lower()
        opener_bar = int(_threshold(ctx, "warmth_opener_units"))
        head_units = _content_units(head)
        meta = next((t for t in _PRAISE_META_TOKENS if t in head_low), None)
        if meta and head_units > opener_bar and not _referents(head):
            reasons.append(
                f"bolted-on warmth: the opening sentence {head[:60]!r} is about "
                f"the thread ({meta!r}), spends {head_units} content units (bar "
                f"{opener_bar}) and carries no concrete referent. Warmth is "
                "fused into the clause that delivers the gift, never a sentence "
                "in front of one"
            )
    return _verdict("warmth_register", reasons)


# ---------------------------------------------------------------------------
# 10. Fabrication — AM-R1 on EVERY account, with the sentence quoted
# ---------------------------------------------------------------------------
#
# WHY THIS IS NOT LEFT TO `vocab`. `vocab` reaches AM-R1 only through
# `expression_dial.violations`, and that function returns [] for any account
# with NO codex — which is the flagship (its spec declares no `dial_profile`)
# and every account whose spec fails to load. So the ONE gate standing between a
# real named human and a fabricated first-person claim was silently absent for
# part of the roster. This critic calls `am_r1_hits` DIRECTLY, so the three
# pinned lines bind on every draft on every desk regardless of codex.
#
# THE BRIGHT LINE, one sentence:
#
#   A reader may learn from a reply how she THINKS and how she REACTS.
#   They may never learn anything about her LIFE.
#
# The builder's test on any candidate sentence: "could a journalist print this
# as a fact about her?" — "Sophia thinks the tariff read is mispriced" is not a
# life fact and is lawful; "Sophia was at a museum this weekend" is, and is not.
# Note the asymmetry that makes a genuinely warm register possible with zero
# fabrication: every lawful item is a predicate about her THINKING, every
# forbidden one is a predicate about her CIRCUMSTANCES.

#: First person + a LIFE OBJECT. `AM_R1_DETECTORS` covers trades, meetings and
#: testimonials; this covers the FOURTH class the warmth register creates
#: pressure on — circumstance. Every pattern requires a first-person subject,
#: because the register is first person by design and the pronoun alone must
#: never be the tell.
#:
#: This is deliberately NOT added to `expression_dial.AM_R1_DETECTORS`: that
#: dict's key set is pinned by test against `personas.AM_R1_BANNED_PATTERNS`, so
#: a new key would force a `banned_patterns` edit across all 20 persona specs —
#: a schema change for a copy law, with no upside.
_LIFE_FACT_RE: tuple[re.Pattern[str], ...] = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\b(?:I|we)(?:'m|'ve|\s+am|\s+have)?\s+(?:just\s+)?(?:back|home|here|there|"
    r"outside|travell?ing|flying|driving|walking|sitting|standing|eating|drinking)\b",
    # ONE optional intervening word, because the ordinal is where the claim
    # actually lives: "my third coffee" and "my trading desk" are the register
    # this is here to stop, and `my\s+(?:coffee|desk)` sees neither of them.
    r"\bmy\s+(?:\w+\s+)?(?:morning|afternoon|evening|weekend|flight|commute|"
    r"desk|office|kitchen|coffee|matcha|tea|run|dog|cat|apartment|"
    r"neighbou?rhood)\b",
    r"\b(?:over\s+here\s+in|out\s+here\s+in|from\s+my\s+(?:desk|couch|kitchen))\b",
    r"\b(?:I|we)(?:'m|\s+am)?\s+(?:on|running\s+on)\s+(?:my\s+)?(?:\w+\s+)?"
    r"(?:coffee|cup|espresso|matcha|hour\s+of\s+sleep|no\s+sleep)\b",
    r"\b(?:rough|long|brutal|great)\s+(?:week|day|morning|night)\s+(?:for\s+me|"
    r"over\s+here|on\s+this\s+end)\b",
))


def _quote_sentence(text: str, needle_start: int) -> str:
    """The sentence containing the character offset, for the reject reason.

    A fabrication rejection has to be ACTIONABLE by a human reading the queue —
    "AM-R1 violation" alone does not say which clause to delete.
    """
    sentences = _sentences(text)
    cursor = 0
    body = str(text or "")
    for sentence in sentences:
        idx = body.find(sentence, cursor)
        if idx == -1:
            continue
        if idx <= needle_start < idx + len(sentence):
            return sentence
        cursor = idx + len(sentence)
    return sentences[0] if sentences else body


def fabrication(draft: str, ctx: dict) -> dict[str, Any]:
    """No fabricated biography on a real person's account (AM-R1).

    Three layers, in order of how much they already existed:

      1. the three PINNED AM-R1 lines, called directly so they bind on every
         account and not only the ones carrying a codex;
      2. ``_LIFE_FACT_RE`` — the circumstance class the warmth register creates
         pressure on, which nothing detected before this build;
      3. the parent author's display-name tokens, barred on EVERY draft. A first
         name implies a relationship we have not established and reads worse
         screenshotted; the winning corpus's own sympathy register uses first
         names, and it is the one thing in it we may not borrow.

    Every reason QUOTES the offending sentence, and names AM-R1, so an operator
    reading ``rejected_by`` next to a ``vocab: AM-R1 violation (...)`` line can
    tell the two apart and knows which clause to cut.
    """
    reasons: list[str] = []
    text = str(draft or "")
    if not text.strip():
        return _verdict("fabrication", reasons)

    try:
        from engine.marketing.expression_dial import AM_R1_DETECTORS  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        # A gate we cannot load is not a gate that passed. This is the ONE
        # hard line protecting a real employee's name; hold the draft.
        return _verdict("fabrication", [
            f"AM-R1 detectors unavailable ({exc}) — cannot clear a real name"
        ])

    for line, patterns in AM_R1_DETECTORS.items():
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                reasons.append(
                    f"AM-R1 ({line}): {_quote_sentence(text, match.start())!r}"
                )
                break
        if reasons:
            break

    for pattern in _LIFE_FACT_RE:
        match = pattern.search(text)
        if match:
            reasons.append(
                "AM-R1 class (circumstance, not analysis): "
                f"{_quote_sentence(text, match.start())!r} — a reader may learn "
                "how this desk thinks, never anything about its life"
            )
            break

    author = str(ctx.get("parent_author") or "")
    if author:
        try:
            from engine.marketing.reply_drafter import author_name_hits  # noqa: PLC0415

            hits = author_name_hits(text, author)
        except Exception as exc:  # noqa: BLE001
            log.warning("reply_critics.fabrication: name check unavailable (%s)", exc)
            hits = []
        if hits:
            reasons.append(
                f"first-name address to the parent author ({hits[0]!r}) implies a "
                "relationship we have not established and reads worse screenshotted"
            )
    return _verdict("fabrication", reasons)


# ---------------------------------------------------------------------------
# 11. Dignity / screenshot rubric — the ONE place an LLM may speak
# ---------------------------------------------------------------------------
def dignity(draft: str, ctx: dict) -> dict[str, Any]:
    """Would this read as a serious desk if screenshotted next to our profile?

    Deterministic layer only. The LLM de-escalation hook is applied by
    ``run_critics``, never here, so this function stays pure and testable.
    """
    reasons: list[str] = []
    low = draft.lower()
    for token in _DIGNITY_TOKENS:
        if token in low:
            reasons.append(f"contempt tell: {token!r}")
            break

    letters = [c for c in draft if c.isalpha()]
    if len(letters) >= 20:
        caps = sum(1 for c in letters if c.isupper())
        if caps / len(letters) > 0.5:
            reasons.append("shouting (majority caps)")

    if draft.count("!") > 1:
        reasons.append("more than one exclamation mark")

    # Correction without humiliation (constitution §9.4): correcting is a reply
    # family; naming the person while doing it is not.
    if re.search(r"\b(you|u)\s+(are|r)\s+(wrong|clueless|lying)\b", low):
        reasons.append("personal correction ('you are wrong') rather than the claim")

    return _verdict("dignity", reasons)


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------
_CRITIC_FUNCS: dict[str, Callable[[str, dict], dict]] = {
    "informational_surplus": informational_surplus,
    "corpus_near_dup": corpus_near_dup,
    "blocklist": blocklist,
    "position_consistency": position_consistency,
    "persona_label": persona_label,
    "reply_value": reply_value,
    "fact_discipline": fact_discipline,
    "vocab": vocab,
    "warmth_register": warmth_register,
    "fabrication": fabrication,
    "dignity": dignity,
}


#: Schema of the stamp a queue item must carry. `reply_queue.validate_item`
#: REFUSES any item without a passing one, which is what makes "every draft that
#: reaches the desktop cleared the critics" a structural fact rather than a
#: property of whichever producer happened to build the item.
STAMP_SCHEMA = "marketing.reply_critics/v1"


def stamp(verdict: dict) -> dict[str, Any]:
    """Reduce a `run_critics` result to the stamp that rides on a queue item.

    Carries the LIST of critics that actually ran, not just the verdict, so the
    queue can refuse a stamp produced by a partial pass — a hand-written
    ``{"verdict": "pass"}`` does not satisfy the check.
    """
    return {
        "schema": STAMP_SCHEMA,
        "verdict": verdict.get("verdict"),
        "rejected_by": list(verdict.get("rejected_by") or []),
        "critics_run": [c["critic"] for c in (verdict.get("critics") or [])],
        "stamped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def screen(
    draft: str,
    ctx: dict | None = None,
    *,
    llm_de_escalate: Callable[[str, dict], bool] | None = None,
) -> tuple[dict, dict]:
    """Run the pass and return ``(verdict, stamp)`` in one call.

    The intended producer entry point: anything building a queue item calls this
    and hands the stamp to ``reply_queue.make_item(critics=...)``.
    """
    verdict = run_critics(draft, ctx, llm_de_escalate=llm_de_escalate)
    return verdict, stamp(verdict)


def run_critics(
    draft: str,
    ctx: dict | None = None,
    *,
    llm_de_escalate: Callable[[str, dict], bool] | None = None,
) -> dict[str, Any]:
    """Run every critic. Returns {verdict, rejected_by, reasons, critics}.

    ``llm_de_escalate(draft, ctx) -> bool`` is the ONLY model in this pass. It
    is consulted only when every deterministic critic already passed, and a
    True answer can only turn that pass into a reject. There is no code path
    by which a model rescues a rejected draft, raises a score, or originates
    one — charter §2 amendment 9, enforced structurally rather than by policy.
    """
    ctx = dict(ctx or {})
    results: list[dict] = []
    reasons: list[str] = []
    rejected_by: list[str] = []

    for name in CRITICS:
        try:
            result = _CRITIC_FUNCS[name](draft, ctx)
        except Exception as exc:  # noqa: BLE001
            # A crashing critic is a FAILED critic, never an absent one: a pass
            # by exception is how a gate silently stops gating.
            log.warning("reply_critics: %s raised %s — treating as reject", name, exc)
            result = _verdict(name, [f"critic error: {exc}"])
        results.append(result)
        if result["verdict"] == "reject":
            rejected_by.append(name)
            reasons.extend(f"{name}: {r}" for r in result["reasons"])

    if not rejected_by and llm_de_escalate is not None:
        try:
            if bool(llm_de_escalate(draft, ctx)):
                rejected_by.append("dignity_llm")
                reasons.append("dignity_llm: de-escalated by review (pass -> reject)")
                results.append(_verdict("dignity_llm", ["de-escalated by review"]))
            else:
                results.append(_verdict("dignity_llm", []))
        except Exception as exc:  # noqa: BLE001
            log.warning("reply_critics: llm_de_escalate raised %s — ignored (may only reject)", exc)

    return {
        "verdict": "reject" if rejected_by else "pass",
        "rejected_by": rejected_by,
        "reasons": reasons,
        "critics": results,
    }


def our_handles(cfg: dict | None) -> list[str]:
    """Every handle the fleet owns, live or dark, from ``desk_network``.

    Dark and planned desks are included deliberately: an account that is not
    posting today may still exist and be followed, and replying to it is the
    same linkage signal as replying to a live one.
    """
    out: list[str] = []
    for acct in ((cfg or {}).get("desk_network") or {}).get("accounts") or []:
        if not isinstance(acct, dict):
            continue
        handle = str(acct.get("handle") or "").strip().lstrip("@")
        if handle:
            out.append(handle)
    return out


__all__ = [
    "CRITICS", "DEFAULT_THRESHOLDS", "DEFAULT_SENSITIVE_TERMS", "STAMP_SCHEMA",
    "MAX_REPLY_WORDS", "LONG_FORM_FAMILIES", "MIN_CONTENT_UNITS",
    "run_critics", "screen", "stamp", "our_handles", "load_theses", "number_tokens",
    "informational_surplus", "corpus_near_dup", "blocklist",
    "position_consistency", "persona_label", "reply_value", "fact_discipline",
    "vocab", "warmth_register", "fabrication", "dignity",
    "warmth_markers", "reply_dial_for",
]
