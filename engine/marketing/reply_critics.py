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
    reply_elements         the POSITIVE floor (XG-W4b §D): a substantive reply
                           must carry at least TWO of {a specific reference to
                           the post, a clear opinion, a reason for it, a
                           conversational marker, an opening} — plus the four
                           named prohibitions (generic praise, parroting the
                           parent, identical openings, question-ending rate)
    register_discipline    the REGISTER laws (XG-W4b §C): one uncertainty
                           marker not two, hedging occasional not habitual,
                           "I feel like" for impressions and "I think" for
                           analysis under a rolling cap, no manufactured typos,
                           and the three anti-polish measures
    fabrication            AM-R1 on every account: a first-person claim about a
                           life event, a purchase or a position that the
                           persona spec does not license rejects, with the
                           offending sentence quoted
    dignity                screenshot rubric; the LLM hook lives here

Public API:
    CRITICS: tuple[str, ...]
    run_critics(draft, ctx, *, llm_de_escalate=None) -> dict
    <each critic>(draft, ctx) -> dict   # {critic, verdict, reasons}
    elements_present(draft, ctx) -> dict[str, str]      # element id -> evidence
    specific_reference(draft, parent, ...) -> str | None
    short_form_engaged(draft, ctx) -> str | None
    REGISTER_RULE_IDS: tuple[str, ...]  # every rule the two new critics enforce
"""
from __future__ import annotations

import logging
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

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
    "reply_elements",
    "register_discipline",
    "fabrication",
    "dignity",
)

#: Every rule the two XG-W4b critics enforce, as machine-readable ids. THIS IS
#: THE CONTRACT BETWEEN THE GATE AND THE PROMPT: every reject reason those two
#: critics emit starts with ``"<rule_id>: "``, ``reply_voice.REGISTER_LAWS``
#: keys off the same ids, and a test asserts the two sets are equal AND that
#: each id has a live code site that can actually reject. A prompt that asks
#: for what the validator bans is the defect this repo has now fixed three
#: times; a shared id list is what makes the disagreement impossible to ship.
REGISTER_RULE_IDS: tuple[str, ...] = (
    # register_discipline (§C)
    "uncertainty_stacking",
    "hedge_share",
    "hedge_on_confession",
    "i_feel_like_scope",
    "i_think_share",
    "i_think_openings",
    "artificial_typos",
    "metronome_prose",
    "memo_prose",
    "balanced_clause_tell",
    # reply_elements (§D)
    "two_of_five",
    "generic_praise",
    "parroted_span",
    "repeated_opening",
    "question_end_share",
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
    # --- XG-W4b §C/§D. Every one is a config key, not a constant, for the same
    # reason the warmth numbers are: they are calibrations, and a calibration an
    # operator cannot move is a constant that gets forked.
    #: §D. How many of the five engagement elements a substantive reply owes.
    "elements_min": 2.0,
    #: §D.0. Below this many content units the two-of-five is unmeasurable (a
    #: conversational beat is not a substantive reply — the operator's own
    #: generation rule says "every SUBSTANTIVE reply").
    "elements_min_units": 6.0,
    #: §C.1 R2 / §C.2 T1. Rolling share ceilings over the account's last
    #: `register_window` replies. The DRAFTER's supply-side hedge target
    #: (persona overlay `confidence.hedge_rate`) must sit strictly under
    #: `hedge_share_cap`, never above it.
    "hedge_share_cap": 0.30,
    "i_think_share_cap": 0.25,
    #: §C.2 T1 / §D.3. How many of the last 20 replies may share an opening.
    "i_think_open_cap": 2.0,
    "opening_repeat_cap": 2.0,
    #: §D.3. Rolling share of replies that may END on a question mark. The
    #: doctrine's §11.8 number, moved from the producer to here (see §H.3).
    "question_end_cap": 0.20,
    #: §C.4 P1. Coefficient of variation of per-sentence content units below
    #: which a >=3-sentence reply is metronome prose.
    "polish_cv_floor": 0.20,
    #: §C.4 P1, SECOND CONDITION, added from measurement — see the WHY in
    #: `register_discipline`. Mean sentence length at which uniformity starts
    #: reading as a paragraph rather than as the corpus's short register.
    "polish_sentence_units_floor": 13.0,
    #: §D.3. Words of verbatim overlap with the parent that count as parroting.
    "verbatim_span_words": 7.0,
    #: Window + fail-open floor shared by every rolling rule in §C/§D. SAME
    #: posture as W2 and for the same documented cost: under `register_history`
    #: items of history these rules are INERT, so a freshly armed account can
    #: hedge or repeat an opening for its first few replies. The mitigation is
    #: supply side; a gate that blocked the lane at arming is the failure class
    #: that kept this desk dark.
    "register_window": 20.0,
    "register_history": 8.0,
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
        # THE SHORT-FORM EXEMPTION, SECOND LEG ONLY (XG-W4b §D.4). A one-line
        # or fragment reaction to the parent's OWN number carries no referent
        # the parent did not have — that is what reacting to their figure MEANS
        # — so this leg killed every short shape the shape build emits. The
        # exemption requires a proven reference AND a committed opinion, so a
        # restatement never qualifies: restating carries no opinion.
        #
        # THE JACCARD LEG ABOVE STILL BINDS, UNCONDITIONALLY, and that is what
        # keeps "All intercepted" dead.
        if short_form_engaged(draft, ctx) is None:
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

    THE SECOND EXEMPTION, added by XG-W4b §D.4 and just as narrow. A SHORT
    shape ("one_line", "fragment_exchange") that carries both a proven specific
    reference to the parent and a committed opinion has answered this critic's
    own honest question — cover the byline, is it still worth reading? — even
    when the referent it names came from the parent rather than from us. The
    referent proxy was calibrated for gift-led replies; "Yeah, but that is the
    problem." carries no referent at all and was rejected on HEAD, which killed
    every short reaction before it was written. ``ctx["shape"]`` absent means no
    exemption: the gate fails CLOSED on a producer that forgot to stamp it.
    """
    refs = _referents(draft)
    if refs:
        return _verdict("persona_label", [])
    if (bool(ctx.get("relationship_only"))
            and str(ctx.get("warmth") or "") == "quiet_sympathy"):
        return _verdict("persona_label", [])
    if short_form_engaged(draft, ctx) is not None:
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

    THE PARENT CLAUSE (XG-W4b §D.1, and it closes a live blocker). A number
    token that is ALSO a number token of ``ctx["parent_text"]`` is licensed.
    Without it the single highest-value reply shape in the operator's brief —
    "The 18% inventory increase is the part that worries me", i.e. reacting to
    the particular figure that triggered the reply — was unshippable, because
    the parent's figure is by construction not on OUR own-feed whitelist and
    every such draft rejected here. We are QUOTING them, not asserting a
    figure, and verbatim presence in the parent is checkable by anyone reading
    the thread.

    The clause is deliberately narrow in three ways. It matches TOKEN AGAINST
    TOKEN, never substring — a substring test would let the parent's "31.55"
    license a fabricated "1.5". It licenses nothing the parent does not contain,
    so a figure in neither the parent nor the whitelist still rejects. And the
    whitelist stays the authority for everything we ASSERT, which is why the
    parent's numbers are not merged into it upstream (§H.2): mixing someone
    else's number into the licence list makes the provenance of every figure on
    the item ambiguous, and provenance is the whole point of this critic.
    """
    raw_whitelist = {str(v) for v in (ctx.get("numbers_whitelist") or [])}
    normalised = {_norm_number(v) for v in raw_whitelist}
    parent = str(ctx.get("parent_text") or "")
    parent_norm = {_norm_number(t) for t in number_tokens(parent)} if parent.strip() else set()
    reasons: list[str] = []
    for token in number_tokens(draft):
        if re.fullmatch(r"\d{1,2}", token):
            continue
        if token in raw_whitelist or _norm_number(token) in normalised:
            continue
        if _norm_number(token) in parent_norm:
            continue  # quoted from the post we are replying to; see the docstring
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
    #
    # WORD BOUNDARIES, AND THEY CLOSE A HOLE IN THE ANTI-COLD LAW ITSELF. The
    # bare `token in low` form this replaced read a warmth marker out of
    # "funding" ("fun"), "fundamentals" ("fun"), "underneath" and "beneath"
    # ("neat"), "through" and "throughput" ("rough"), "brutally", "wildest",
    # "hopeful" and "grimace". Two of those are the desk's most common mechanism
    # words, so W1 — the twelve-unit cold-printout gate — was silently inert on
    # any employee reply that mentioned funding, which is the exact instrument
    # readout the operator named. Found by the XG-W4b calibration set; measured
    # at ZERO verdict changes across the 162-render tail grid, i.e. it withdraws
    # nothing the drafter actually relies on.
    for token in _REACTION_TOKENS:
        if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", low):
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
# 10. reply_elements — the POSITIVE floor (XG-W4b §D)
# ---------------------------------------------------------------------------
#
# THE OPERATOR NAMED THE FAILURE, twice over: "the biggest difference between
# human and AI replies is that humans have a SPECIFIC REACTION, not a competent
# summary", and "every substantive reply must contain AT LEAST TWO of: a
# specific reference to the post, a clear opinion, a reason for that opinion, a
# natural conversational marker, a question or opening".
#
# WHY A NEW CRITIC AND NOT AN EXTENSION OF `reply_value`. That critic enforces
# the doctrine's §8 ANTI-patterns — four things a reply may not be. This one
# enforces a POSITIVE floor — two things a reply must have. Folding them
# together would put two unrelated laws behind one `rejected_by` label, which is
# the same argument that gave `warmth_register` its own name, and an operator
# reading a rejection would not know which one fired.
#
# WHY THE REFERENCE DETECTOR IS THE LOAD-BEARING ONE. Topical adjacency is free:
# every draft this desk writes is about the market, and so is every parent. What
# is NOT free is proving the reply engaged a PARTICULAR figure, ticker, clause or
# borrowed noun of the parent — that is the difference between "reads like
# someone actually read the post" and a competent summary that would fit under
# any headline in the sector.

#: Vocabulary that is in every market post ever written, so sharing it with the
#: parent proves nothing. Deliberately SHORT: the stoplist exists to stop
#: detector (3) from passing on ambient words, not to be a second ban list.
_GENERIC_MARKET_WORDS: frozenset[str] = frozenset({
    "market", "markets", "earnings", "quarter", "guidance", "growth", "higher",
    "lower", "another", "because", "something", "everyone", "numbers",
})

#: (b) OPINION. Explicit frames — the phrases that announce a judgment. The
#: precise alternatives ("my read is", "this looks more like") sit here beside
#: the plain ones because the operator ranks them ABOVE "I think", not beside
#: it: they sound personal without pretending the model has feelings.
_OPINION_FRAMES: tuple[str, ...] = (
    "my read is", "i think", "i'd lean", "id lean", "i would lean",
    "i'm leaning", "im leaning", "i read this as", "this looks more like",
    "that reads like", "i'm not convinced", "im not convinced", "i doubt",
    "the part that matters is", "the whole story", "this is less about",
    "i would push back", "that is the test", "the cleaner label is",
)

#: (b) A comparative verdict: X rather than Y. The last two alternatives are the
#: CONVERSATIONAL forms of the same move and come straight off the operator's
#: own examples ("credit, not semis"; "much weaker than the headline suggests").
_COMPARATIVE_RE = re.compile(
    r"\b(?:more|less)\s+(?:like|about)\b"
    r"|\brather than\b"
    r"|\bnot\s+\w+,\s*(?:it'?s|it is)\b"
    r"|\b\w+,\s*not\s+\w+"
    r"|\b(?:weaker|stronger|worse|better|softer|harder|cleaner|bigger|smaller|"
    r"slower|faster|cheaper|richer)\s+than\b",
    re.IGNORECASE)
#: (b) A modal commitment. `could`/`might`/`may` are deliberately ABSENT: the
#: operator's own WEAK example is "This could have significant implications for
#: the market", and a detector that reads `could` as a commitment would pass it.
_MODAL_COMMIT_RE = re.compile(
    r"\b(?:will|won'?t|has to|have to|cannot|can'?t)\s+\w+", re.IGNORECASE)
#: (b) An evaluative predicate on a market object.
_EVALUATIVE_PREDICATE_RE = re.compile(r"\b(?:is|are)\s+(?:the|what)\s+\w+",
                                      re.IGNORECASE)
#: (b) The CONVERSATIONAL evaluative predicate: copula + an evaluative
#: adjective. This is the register half of the same move ("the entry still looks
#: bad", "this still feels early", "I'd be pretty cautious"), and without it the
#: detector only sees the formal voice — which is precisely the voice the
#: operator is trying to get away from. The adjective list is CLOSED on purpose;
#: an open one would read "is interesting" as a judgment, and "Interesting
#: perspective." is the weak example this whole critic exists to reject.
_EVALUATIVE_ADJECTIVES: tuple[str, ...] = (
    "early", "late", "bad", "good", "wrong", "right", "cheap", "expensive",
    "thin", "ugly", "weak", "weaker", "strong", "stronger", "fine", "worse",
    "better", "overdone", "premature", "mispriced", "stretched", "fragile",
    "cautious", "nervous", "messy", "brutal", "rough", "quiet", "loud",
)
_CONVERSATIONAL_VERDICT_RE = re.compile(
    r"\b(?:is|are|was|were|be|looks?|looked|feels?|felt|reads?|sounds?|seems?)\s+"
    r"(?:pretty\s+|much\s+|already\s+|still\s+|a bit\s+|too\s+|quite\s+|very\s+)?"
    r"(?:" + "|".join(_EVALUATIVE_ADJECTIVES) + r")\b", re.IGNORECASE)
#: (b) A verdict about what the CROWD got wrong. The operator's humour example
#: ("The market heard 'AI' and temporarily forgot valuation exists") is a
#: committed judgment wearing a joke, and so is "everyone is treating this as a
#: demand story when it's really a positioning story". Both assert that the room
#: is missing something, which is a claim a reader can disagree with — the test
#: this element is actually applying.
_CROWD_VERDICT_RE = re.compile(
    r"\b(?:market|tape|room|street|crowd|consensus|everyone|nobody|people)\b"
    r"[^.?!]{0,48}?\b(?:forgot|forgets|ignored|ignoring|ignores|missed|misses|"
    r"already priced|has priced|never priced|is not pricing|isn'?t pricing)\b"
    r"|\b(?:it'?s|it is|this is|that is)\s+(?:really|actually|mostly|mainly)\b",
    re.IGNORECASE)

#: (c) REASON. Connectives that introduce a because. "when" is here beside
#: "once" and "while" for the same grammatical reason — it subordinates a clause
#: that explains the first ("...when it's really a positioning story").
_REASON_CONNECTIVES: tuple[str, ...] = (
    "because", "since", "so", "which means", "that means", "if", "once",
    "while", "when", "until", "as long as", "given that", "the reason",
)
#: The ASCII arrow chain. U+2192 is deliberately NOT accepted: it sits inside
#: `expression_dial._EMOJI_RE`'s arrow class, so a chain written with it is
#: STRIPPED before it reaches a reader and reported as an off-signature emoji.
_ARROW_RE = re.compile(r"->")

#: (d) MARKER, beyond `warmth_markers`. Sentence-initial discourse particles and
#: the first-person impression phrases the operator's item 4 is made of.
_DISCOURSE_PARTICLES: tuple[str, ...] = (
    "yeah", "yep", "fair", "honestly", "look", "right", "sure", "exactly",
    "no", "okay so", "i mean", "well",
)
_IMPRESSION_RE = re.compile(
    r"\bi (?:don'?t|do not) know\b"
    r"|\b(?:feels?|feeling)\s+(?:like|early|late|off|wrong|premature|thin)\b"
    r"|\bmy\s+(?:first\s+)?(?:read|reaction|instinct|take|mind)\b"
    r"|\bchanged my mind\b",
    re.IGNORECASE)
#: (d) First person + an evaluative adjective, i.e. micro-emotion. "This is the
#: part I find frustrating." The pronoun requirement is what keeps this a
#: REACTION rather than an adjective sweep.
_MICRO_EMOTION_RE = re.compile(
    r"\b(?:i|we|me|my)\b[^.?!]{0,40}?\b(?:frustrating|frustrated|surprised|"
    r"surprising|worries|worried|worrying|cautious|uneasy|nervous|curious|"
    r"uncomfortable|annoying|striking)\b",
    re.IGNORECASE)

#: (e) OPENING. A last sentence that leaves a condition unresolved is an
#: invitation; a resolved verdict is a full stop.
_HALF_STEP_TOKENS: tuple[str, ...] = (
    "if", "unless", "until", "watching", "the test is", "what would",
    "the open question",
)

#: §C.1. The uncertainty register, as the operator listed it. ONE of these is
#: conversation. Two is a model hedging, and the rate over a window is what
#: turns "occasional" from a wish into a gate.
UNCERTAINTY_MARKERS: tuple[str, ...] = (
    "i could be wrong", "i might be wrong", "i may be wrong",
    "maybe i'm missing", "maybe im missing", "i might be missing",
    "not fully convinced", "not entirely convinced", "i'm not convinced",
    "im not convinced",
    "i'd lean", "i would lean", "i'm leaning", "im leaning",
    "feels like", "the weird part is", "the odd part is",
    "hard to say", "i'm not sure", "im not sure", "could be nothing",
)

#: §C.2 T2. "I feel like" is for an IMPRESSION, and an impression is about a
#: crowd. These are the tokens that make a sentence one.
_CROWD_TOKENS: tuple[str, ...] = (
    "everyone", "people", "the room", "the crowd", "consensus", "positioning",
    "sentiment", "mood", "treating this as", "nobody", "the street",
)

#: §C.3. Manufactured typos. A CLOSED list plus two structural patterns, and
#: this is a FLOOR rather than a sweep — it exists because a model told to sound
#: human inserts them, and "how do you do, fellow humans" is the operator's
#: named failure. A missing-apostrophe check was CONSIDERED AND REJECTED: kelly's
#: lowercase register legitimately writes "dont", and a rule that fires on a
#: pinned voice is a rule that gets overridden. The real enforcement is the
#: prompt law `reply_voice` states (HARD LAW 10).
_TYPO_TELLS: tuple[str, ...] = (
    "teh ", " taht ", " adn ", " jsut ", "becuase", "recieve", "seperate",
    "definately", "wierd", "thier ", " alot ", "prolly",
)
#: Letter elongation ("sooo", "yesss"). THE CHARACTER CLASS IS ALPHABETIC AND
#: THAT IS LOAD-BEARING: the `\w`-based form matches "1,000" (three zeroes) and
#: would have rejected every reply carrying a round thousand.
_ELONGATION_RE = re.compile(r"\b[A-Za-z]*([A-Za-z])\1{2,}[A-Za-z]*\b")
_OVER_ELLIPSIS_RE = re.compile(r"\.{4,}")

#: §C.4 P3. The balanced-clause tell. ONE of these is a sentence a person
#: writes; two inside sixty words is a generator's rhythm.
_BALANCED_CLAUSE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bnot\s+(?:just|only)\b[^.?!]{0,60}\bbut\b", re.IGNORECASE),
    re.compile(r"\bit'?s not\b[^.?!]{0,40}\bit'?s\b", re.IGNORECASE),
)

#: A contraction, for §C.3 and §C.4 P2. `_TOKEN_RE` keeps the apostrophe inside
#: the token, so a contraction never costs a draft a content unit and no critic
#: penalises one — a test pins that.
_CONTRACTION_RE = re.compile(r"\b\w+'(?:s|t|re|ve|ll|d|m)\b", re.IGNORECASE)

#: §D.4. The shapes whose whole point is that they carry no new referent.
SHORT_FORM_SHAPES: frozenset[str] = frozenset({"one_line", "fragment_exchange"})


def _register_window(ctx: dict) -> list[dict]:
    """The account's last N replies from ``ctx["corpus"]``, or [].

    Same read W2 does, factored out because five rules in §C/§D share it and
    five copies of a window are five places for the fail-open floor to drift.
    """
    account = str(ctx.get("account") or "")
    window = int(_threshold(ctx, "register_window"))
    mine = [row for row in (ctx.get("corpus") or [])
            if isinstance(row, dict) and str(row.get("account") or "") == account]
    return mine[-window:] if window > 0 else []


def _window_is_gradeable(ctx: dict, rows: Sequence[dict]) -> bool:
    """Whether a rolling rule may fire. FAILS OPEN below the history floor."""
    return len(rows) >= int(_threshold(ctx, "register_history"))


def _uncertainty_hits(text: str) -> list[str]:
    """Distinct uncertainty markers in *text*, longest-first, no containment.

    Containment matters: without it a single phrase that happens to contain a
    shorter marker would read as two markers and R1 would reject a compliant
    reply for stacking a hedge on itself.
    """
    low = str(text or "").lower()
    found = [m for m in UNCERTAINTY_MARKERS if m in low]
    found.sort(key=len, reverse=True)
    kept: list[str] = []
    for marker in found:
        if any(marker in bigger for bigger in kept):
            continue
        kept.append(marker)
    return kept


def _sentence_units(text: str) -> list[int]:
    """Content units per sentence, EMPTY SENTENCES DROPPED.

    A numbered-list line ("1.") splits as its own sentence and carries zero
    units; counting it would report a two-sentence reply as four and drag the
    §C.4 P1 variation toward a false reject.
    """
    return [u for u in (_content_units(s) for s in _sentences(text)) if u > 0]


def _norm_opening(text: str, units: int = 4) -> str:
    """The draft's first *units* content units, normalised for comparison."""
    masked = _MENTION_RE.sub(" ", _URL_RE.sub(" ", str(text or "").lower()))
    words = [w for w in _TOKEN_RE.findall(masked) if any(c.isalpha() for c in w)]
    return " ".join(words[:units])


def _word_list(text: str) -> list[str]:
    return _TOKEN_RE.findall(str(text or "").lower())


def specific_reference(
    draft: str,
    parent: str,
    *,
    numbers_whitelist: Sequence[str] = (),
    detail: str = "",
) -> str | None:
    """EVIDENCE that the reply engaged a particular part of the parent, or None.

    Five detectors, checked in order of how much they PROVE. The point of the
    ordering is that a shared figure is unarguable and a shared noun is weak, so
    the evidence string a rejection prints names which one fired.

    ``numbers_whitelist`` is accepted and deliberately unused for matching: it
    is here so a caller cannot mistake this for a licence check. Licensing is
    ``fact_discipline``'s job, and this function's job is engagement.
    """
    d = str(draft or "")
    p = str(parent or "")

    # (5) An extracted detail is `extract_detail` having ALREADY proved the
    # engagement, so it stands even with no parent text in hand.
    if detail and str(detail).lower() in d.lower():
        return f"extracted detail {str(detail).lower()!r}"

    if not p.strip():
        return None

    # (1) A shared figure. The strongest evidence there is: the reply is about
    # a number the poster wrote.
    parent_numbers = {_norm_number(t): t for t in number_tokens(p)}
    for token in number_tokens(d):
        if _norm_number(token) in parent_numbers:
            return f"figure {token!r} from the parent"

    # (2) A shared cashtag.
    draft_tags = {t.upper() for t in _CASHTAG_RE.findall(d)}
    parent_tags = {t.upper() for t in _CASHTAG_RE.findall(p)}
    shared_tags = sorted(draft_tags & parent_tags)
    if shared_tags:
        return f"cashtag {shared_tags[0]!r} from the parent"

    # (3) A borrowed noun. Mechanism tokens are excluded because they are OUR
    # vocabulary and appear in every draft by construction, so sharing one with
    # the parent is evidence about the beat, not about the reading.
    draft_words = {w for w in _words(d) if len(w) >= 6 and w.isalpha()}
    parent_words = {w for w in _words(p) if len(w) >= 6 and w.isalpha()}
    borrowed = sorted((draft_words & parent_words)
                      - set(_MECHANISM_TOKENS) - _GENERIC_MARKET_WORDS)
    if borrowed:
        return f"borrowed noun {borrowed[0]!r} from the parent"

    # (4) A structural pointer: an ordinal reference both carry, a quoted term
    # lifted from the parent, or a short literal quotation.
    try:
        from engine.marketing.reply_drafter import _ORDINAL_DETAIL_RE  # noqa: PLC0415

        d_ord = _ORDINAL_DETAIL_RE.search(d)
        if d_ord and _ORDINAL_DETAIL_RE.search(p):
            return f"structural pointer {d_ord.group(0).lower()!r}"
    except Exception as exc:  # noqa: BLE001 — an additive detector, never a gate
        log.warning("reply_critics.specific_reference: ordinal detector "
                    "unavailable (%s)", exc)

    low_parent = p.lower()
    for match in re.finditer(r"[\"'“‘]([^\"'”’]{2,40})[\"'”’]", d):
        quoted = match.group(1).strip()
        if quoted and quoted.lower() in low_parent:
            return f"quoted term {quoted!r} from the parent"

    words = _word_list(d)
    for i in range(len(words) - 3):
        span = " ".join(words[i:i + 4])
        if span in low_parent:
            return f"quoted span {span!r} from the parent"
    return None


def _opinion_evidence(sentence: str) -> str | None:
    """A clear judgment that COMMITS, inside one sentence, or None."""
    low = sentence.lower()
    for frame in _OPINION_FRAMES:
        if frame in low:
            return frame
    for regex, label in (
        (_COMPARATIVE_RE, "comparative verdict"),
        (_CROWD_VERDICT_RE, "verdict about the room"),
        (_MODAL_COMMIT_RE, "modal commitment"),
        (_CONVERSATIONAL_VERDICT_RE, "evaluative predicate"),
        (_EVALUATIVE_PREDICATE_RE, "evaluative predicate"),
    ):
        match = regex.search(sentence)
        if match:
            return f"{label} {match.group(0).strip().lower()!r}"
    return None


def _reason_evidence(text: str, sentences: Sequence[str]) -> str | None:
    """A stated reason for the opinion, or None."""
    if len(_ARROW_RE.findall(text)) >= 2:
        return "arrow chain"
    for sentence in sentences:
        low = sentence.lower()
        if not _referents(sentence):
            continue
        for connective in _REASON_CONNECTIVES:
            if re.search(rf"(?<!\w){re.escape(connective)}(?!\w)", low):
                return f"connective {connective!r}"
    # Two clauses where the second NAMES something the first did not — the
    # structural shape of "here is why", with no connective required.
    if len(sentences) == 2:
        added = _referents(sentences[1]) - _referents(sentences[0])
        if added:
            return f"second clause adds {sorted(added)[0]!r}"
    return None


def _marker_evidence(text: str, ctx: dict) -> str | None:
    """A natural emotional or conversational marker, or None.

    ONE GUARD, TWO CALLERS: `warmth_markers` is the module's closed-class
    register detector and is reused rather than re-derived. The extensions are
    the three classes it was never built to see — a hedge, a sentence-initial
    discourse particle, and first-person micro-emotion.
    """
    markers = warmth_markers(text, ctx)
    if markers:
        return markers[0]
    hedges = _uncertainty_hits(text)
    if hedges:
        return f"uncertainty {hedges[0]!r}"
    for sentence in _sentences(text):
        head = _norm_opening(sentence, units=2)
        for particle in _DISCOURSE_PARTICLES:
            if head == particle or head.startswith(particle + " "):
                return f"discourse particle {particle!r}"
    match = _IMPRESSION_RE.search(text) or _MICRO_EMOTION_RE.search(text)
    if match:
        return f"impression {match.group(0).strip().lower()!r}"
    return None


def _opening_evidence(sentences: Sequence[str]) -> str | None:
    """A question or an opening for further discussion in the LAST sentence."""
    if not sentences:
        return None
    last = sentences[-1]
    if last.rstrip().endswith("?"):
        return "ends on a question"
    low = last.lower()
    for token in _HALF_STEP_TOKENS:
        if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", low):
            return f"unresolved condition {token!r}"
    if any(f in low for f in _OPINION_FRAMES) and _COMPARATIVE_RE.search(last):
        return "verdict implying a division"
    return None


def elements_present(draft: str, ctx: dict) -> dict[str, str]:
    """The engagement elements this draft carries: element id -> EVIDENCE.

    Evidence strings rather than booleans, so a rejection and the queue record
    can print WHAT was found. A reject an operator cannot act on is a reject
    that gets overridden — the standard `fabrication` already sets.

    ANTI-DOUBLE-COUNT. ``opinion`` and ``opening`` may not both be satisfied by
    the SAME sentence: one committed clause wearing two hats is one element, and
    without this "That reads like credit, not semis." scores two on a single
    verdict. ``reference`` and ``reason`` MAY share a sentence — they are
    structurally different claims about it.
    """
    text = str(draft or "")
    sentences = _sentences(text)
    out: dict[str, str] = {}

    evidence = specific_reference(
        text, str(ctx.get("parent_text") or ""),
        numbers_whitelist=ctx.get("numbers_whitelist") or (),
        detail=str(ctx.get("detail") or ""),
    )
    if evidence:
        out["reference"] = evidence

    opinion_at: int | None = None
    for idx, sentence in enumerate(sentences):
        evidence = _opinion_evidence(sentence)
        if evidence:
            out["opinion"] = evidence
            opinion_at = idx
            break

    evidence = _reason_evidence(text, sentences)
    if evidence:
        out["reason"] = evidence

    evidence = _marker_evidence(text, ctx)
    if evidence:
        out["marker"] = evidence

    evidence = _opening_evidence(sentences)
    if evidence and opinion_at != (len(sentences) - 1):
        out["opening"] = evidence
    return out


#: The plain-word reason each missing element is missing, for the reject line.
_ELEMENT_MISSES: dict[str, str] = {
    "reference": "no figure, cashtag, borrowed noun or quoted span shared with the parent",
    "opinion": "no committed judgment",
    "reason": "no because/so/which means/if-then link",
    "marker": "no conversational or emotional register marker",
    "opening": "no question and nothing left open",
}
_ELEMENT_ORDER: tuple[str, ...] = ("reference", "opinion", "reason", "marker", "opening")


def _data_drop_evidence(draft: str, ctx: dict) -> str | None:
    """A checkable figure this reply carries that the parent did not, or None.

    THE SECOND EXEMPTION TO THE TWO-OF-FIVE, and it is not a softening — it is
    the doctrine's own top-ranked winning pattern, which the operator's five
    elements do not describe because all five describe COMMENTARY. The reply
    playbook's first entry is "DATA DROP: a concrete, checkable number or level
    the post did not have", and the corpus's winners include "Actually closer to
    -10%" (23 likes) and "Support at 900-925" (22). A drop carries no opinion,
    no marker and, by construction, no reference — its whole content is the
    number.

    THE MEASUREMENT THAT SET THIS SHAPE. Without the exemption, 16 of the 162
    tail composes on HEAD reject on the floor, and ALL SIXTEEN are flagship or
    founder — the two desks the doctrine's §5 register map forbids to be warm
    ("anything warm" sits in their Never column). Those desks cannot produce a
    `marker` by law, so the floor was silently a two-of-four for them and their
    house shape — a terse figure plus a terse verdict — landed at one. A gate
    that rejects a register the doctrine PINS is a gate that gets overridden.

    So the discriminator is the payload, not the sentence count: a reply that
    supplies a figure the thread did not have HAS paid the room, whether it
    spends one line or three. Quoting THEIR number back earns nothing here — a
    borrowed figure is a `reference`, which is already an element and still has
    to be joined by a second one. The residual worry, a long competent summary
    with a stray figure inside it, is governed elsewhere and was before this
    build: `reply_value` kills unclosed length past sixty words,
    `warmth_register` W1 kills a twelve-unit cold employee reply,
    `informational_surplus` kills a restatement, `corpus_near_dup` kills
    sameness.
    """
    parent = str(ctx.get("parent_text") or "")
    parent_numbers = {_norm_number(t) for t in number_tokens(parent)}
    for token in number_tokens(draft):
        if re.fullmatch(r"\d{1,2}", token):
            continue  # bare 1-2 digit integers are prose, not a level
        if _norm_number(token) not in parent_numbers:
            return f"data drop {token!r} the parent did not carry"
    return None


def short_form_engaged(draft: str, ctx: dict) -> str | None:
    """The evidence that a SHORT reply earned its place without a new referent.

    None means no exemption. Requires ALL of:

      * ``ctx["shape"]`` in ``SHORT_FORM_SHAPES`` — the producer stamps it, and
        an ABSENT shape fails CLOSED (a producer that forgot to say what it
        built gets the strict gate, never the lenient one);
      * ``elements_present`` carries BOTH ``reference`` and ``opinion`` — the
        reply named something specific of theirs AND committed to a judgment
        about it, which is the whole content of "worth reading with the byline
        covered";
      * token overlap with the parent under the ``parent_jaccard`` bar, so a
        restatement can never buy the exemption.
    """
    if str(ctx.get("shape") or "") not in SHORT_FORM_SHAPES:
        return None
    elements = elements_present(draft, ctx)
    if "reference" not in elements or "opinion" not in elements:
        return None
    parent = str(ctx.get("parent_text") or "")
    if parent.strip():
        overlap = token_jaccard(draft, parent)
        if overlap >= _threshold(ctx, "parent_jaccard"):
            return None
    return (f"short form ({ctx.get('shape')}) carrying a reference "
            f"({elements['reference']}) and an opinion ({elements['opinion']})")


def reply_elements(draft: str, ctx: dict) -> dict[str, Any]:
    """Two of the five engagement elements, plus the four named prohibitions.

    SCOPE. Applies to drafts of at least ``elements_min_units`` content units.
    Below that the reply is a conversational beat governed by the shape budget
    and the two-of-five is unmeasurable — the operator's own rule says "every
    SUBSTANTIVE reply", and the threshold is the executable proxy for
    substantive. Stated here rather than left to a silent constant.

    TWO EXEMPTIONS, both narrow and both named in the verdict's own vocabulary.
    `quiet_sympathy` is DOUBLE GATED exactly as `persona_label`'s is:
    ``ctx["relationship_only"]`` AND ``ctx["warmth"] == "quiet_sympathy"``;
    either alone is a hole big enough to smuggle an elementless growth reply
    through. The second is the DATA DROP — see ``_data_drop_evidence``.

    NO HUMOR EXEMPTION, and that absence is deliberate. The operator's humor
    exemplar ("The market heard 'AI' and temporarily forgot valuation exists.")
    was believed to fail this floor and an exemption was cut for it — then
    measured: with ``parent_text`` actually supplied it PASSES on merit, at
    reference (the quoted term "AI", borrowed from the parent) plus opinion.
    The apparent failure came from a harness that passed ``target`` without
    ``parent_text``, which silently blinds every parent-dependent check here. A
    lawful joke references something; one that references nothing and asserts
    nothing is not being funny. The exemption was removed rather than left as a
    hole any thin reply could be typed into.
    """
    reasons: list[str] = []
    text = str(draft or "").strip()
    if not text:
        return _verdict("reply_elements", reasons)

    parent = str(ctx.get("parent_text") or "")
    relationship_exempt = (bool(ctx.get("relationship_only"))
                           and str(ctx.get("warmth") or "") == "quiet_sympathy")
    # Humor is exempt from the element FLOOR only (see the docstring). Every
    # prohibition below still runs on it, so an unfunny "joke" that is really
    # generic praise or a parroted parent is still rejected — by the check that
    # actually names that defect.
    units = _content_units(text)
    floor = int(_threshold(ctx, "elements_min_units"))
    minimum = int(_threshold(ctx, "elements_min"))

    elements = elements_present(text, ctx)
    drop = _data_drop_evidence(text, ctx)
    if (units >= floor and not relationship_exempt and drop is None
            and len(elements) < minimum):
        found = ", ".join(f"{k}: {elements[k]!r}" for k in _ELEMENT_ORDER if k in elements)
        missing = ", ".join(f"{k} ({_ELEMENT_MISSES[k]})"
                            for k in _ELEMENT_ORDER if k not in elements)
        reasons.append(
            f"two_of_five: only {len(elements)} of the five engagement elements "
            f"present ({found or 'none'}). A reply needs at least {minimum} of: a "
            "specific reference to the post, a clear opinion, a reason for that "
            "opinion, a conversational marker, a question or opening. "
            f"Missing — {missing}"
        )

    # --- the four prohibitions (operator item 10) --------------------------
    low = text.lower()

    # 1. Generic praise with no substance. W3 kills the LONG bolted-on form
    # (>5 units in the opening sentence); this kills the SHORT one ("Good
    # point."), which clears W3 today and is caught by `persona_label` only when
    # it happens to be referent-free. The overlap is documented, not accidental.
    praise = next((t for t in _PRAISE_META_TOKENS if t in low), None)
    if praise and "reference" not in elements and not relationship_exempt:
        reasons.append(
            f"generic_praise: {praise!r} with nothing specific from the post "
            "behind it — praise that names no figure, ticker, borrowed noun or "
            "quoted span is a reply that could sit under any post in the sector"
        )

    # 2. Repeating the original post. `informational_surplus` measures token
    # OVERLAP; jaccard is blind to one quoted sentence sitting inside a longer
    # reply, which is the exact shape of a "restate then agree" draft.
    span_words = int(_threshold(ctx, "verbatim_span_words"))
    if parent.strip() and span_words > 0:
        words = _word_list(text)
        low_parent = " ".join(_word_list(parent))
        for i in range(max(0, len(words) - span_words + 1)):
            span = " ".join(words[i:i + span_words])
            if span and span in low_parent:
                reasons.append(
                    f"parroted_span: {span_words} consecutive words lifted from "
                    f"the parent ({span!r}) — quoting the post back at it is not "
                    "informational surplus"
                )
                break

    # 3. Identical openings. The operator's own diagnosis: "if every reply
    # starts with them the account sounds like an LLM wearing a human mustache."
    rows = _register_window(ctx)
    if _window_is_gradeable(ctx, rows):
        opening = _norm_opening(text)
        cap = int(_threshold(ctx, "opening_repeat_cap"))
        if opening:
            same = sum(1 for row in rows
                       if _norm_opening(str(row.get("draft") or "")) == opening)
            if same > cap:
                reasons.append(
                    f"repeated_opening: {opening!r} opens {same} of this desk's "
                    f"last {len(rows)} replies (cap {cap})"
                )

        # 4. Question-ending RATE. Ending on a question is fine; ending on one
        # every time is a tic. RULING (§H.3): this half of doctrine §11.8's cap
        # lives in the critic, not the producer, because W2 already proves a
        # critic can read a rolling window and the producer's half stayed
        # unbuilt for a wave. The producer's REMAINING caps (at most two
        # author-directed replies per account per 7 days, never two to the same
        # author inside 30 days) genuinely need the queue and are still unbuilt.
        if text.rstrip().endswith("?"):
            end_cap = float(_threshold(ctx, "question_end_cap"))
            ended = sum(1 for row in rows
                        if str(row.get("draft") or "").rstrip().endswith("?"))
            share = ended / len(rows)
            if share >= end_cap:
                reasons.append(
                    f"question_end_share: {ended} of this desk's last {len(rows)} "
                    f"replies end on a question (share {share:.2f} >= {end_cap:.2f}) "
                    "and this one does too"
                )
    return _verdict("reply_elements", reasons)


# ---------------------------------------------------------------------------
# 11. register_discipline — the REGISTER laws (XG-W4b §C)
# ---------------------------------------------------------------------------
#
# THE OPERATOR NAMED THE FAILURE: "'I think'/'I feel' are SEASONING, NOT THE
# MEAL — if every reply starts with them the account sounds like an LLM wearing
# a human mustache." Everything here is that complaint as a predicate.
#
# WHY A THIRD CRITIC RATHER THAN A BRANCH OF `warmth_register` OR `reply_value`.
# Same argument, third time: two unrelated laws behind one `rejected_by` label
# leave an operator unable to tell which fired. `warmth_register` asks whether
# the reply has ANY human register; this asks whether the human register it has
# is being spent like a person spends it. Those can disagree in both directions.
#
# WHAT THIS DELIBERATELY DOES NOT DO. It does not penalise a contraction and it
# does not penalise a fragment. Both are LAWFUL and a test pins that they clear
# all thirteen critics, because the corpus's median winner is eleven words and
# a gate that quietly preferred complete sentences would be pulling the desk
# back toward the memo register this whole wave exists to leave.


def register_discipline(draft: str, ctx: dict) -> dict[str, Any]:
    """Hedging, the I-think ladder, manufactured typos, and over-polish."""
    reasons: list[str] = []
    text = str(draft or "").strip()
    if not text:
        return _verdict("register_discipline", reasons)

    low = text.lower()
    sentences = _sentences(text)
    rows = _register_window(ctx)
    gradeable = _window_is_gradeable(ctx, rows)

    # --- §C.1 uncertainty-marker discipline --------------------------------
    hits = _uncertainty_hits(text)

    # R1. Never stacked.
    if len(hits) > 1:
        shown = ", ".join(repr(h) for h in sorted(hits)[:3])
        reasons.append(
            f"uncertainty_stacking: {len(hits)} markers in one reply ({shown}) — "
            "one marker is conversation, two is a model hedging"
        )

    # R2. Occasional, as a RATE over the window. Fails OPEN below the history
    # floor: a freshly armed account may hedge its first few replies, and the
    # mitigation is the drafter's own rate target, never a gate that blocks the
    # lane at arming.
    if hits and gradeable:
        cap = float(_threshold(ctx, "hedge_share_cap"))
        hedged = sum(1 for row in rows if _uncertainty_hits(str(row.get("draft") or "")))
        share = hedged / len(rows)
        if share > cap:
            reasons.append(
                f"hedge_share: {hedged} of this desk's last {len(rows)} replies "
                f"carry an uncertainty marker (share {share:.2f} > {cap:.2f}) and "
                "this one carries one too"
            )

    # R3. A hedge may not ride a confession. "I was wrong about this one, though
    # I could be wrong" is a hedge on an admission, which reads as neither.
    for sentence in sentences:
        s_low = sentence.lower()
        marker = next((m for m in hits if m in s_low), None)
        change = next((c for c in _CHANGE_MARKERS if c in s_low), None)
        if marker and change:
            reasons.append(
                f"hedge_on_confession: {marker!r} in the same sentence as "
                f"{change!r} ({sentence[:60]!r}) — owning a changed mind and "
                "hedging it at once reads as neither"
            )
            break

    # --- §C.2 the "I think" ladder -----------------------------------------
    # T3 (precise alternatives: "my read is", "this looks more like", "that
    # reads like") is PREFERRED and UNCAPPED, so it has no rule here. Its
    # absence from this function is the policy, not an omission.

    # T2. "I feel like" is for an impression, which is a claim about a crowd.
    # In front of an analytical claim it is the operator's named misuse.
    for sentence in sentences:
        s_low = sentence.lower()
        if "i feel like" not in s_low:
            continue
        if any(tok in s_low for tok in _CROWD_TOKENS):
            continue
        mechanism = next((m for m in _MECHANISM_TOKENS if m in _words(sentence)), None)
        if mechanism:
            reasons.append(
                f"i_feel_like_scope: \"i feel like\" in front of an analytical "
                f"claim about {mechanism!r} ({sentence[:70]!r}) — analysis takes "
                "\"I think\" or a precise alternative; \"I feel like\" is for an "
                "impression about what the room believes"
            )
            break

    # T1. "I think" is permitted for analysis and CAPPED, both as a share and as
    # an opening. The second cap is the operator's mustache sentence, executable.
    if "i think" in low and gradeable:
        share_cap = float(_threshold(ctx, "i_think_share_cap"))
        used = sum(1 for row in rows if "i think" in str(row.get("draft") or "").lower())
        share = used / len(rows)
        if share > share_cap:
            reasons.append(
                f"i_think_share: {used} of this desk's last {len(rows)} replies "
                f"carry \"i think\" (share {share:.2f} > {share_cap:.2f}) and this "
                "one does too — it is seasoning, not the meal"
            )
        if _norm_opening(text, units=2) == "i think":
            open_cap = int(_threshold(ctx, "i_think_open_cap"))
            opened = sum(1 for row in rows
                         if _norm_opening(str(row.get("draft") or ""), units=2) == "i think")
            if opened > open_cap:
                reasons.append(
                    f"i_think_openings: \"i think\" opens {opened} of this desk's "
                    f"last {len(rows)} replies (cap {open_cap}) and it opens this "
                    "one too"
                )

    # --- §C.3 manufactured typos -------------------------------------------
    padded = f" {low} "
    tell = next((t for t in _TYPO_TELLS if t in padded), None)
    elongation = _ELONGATION_RE.search(text)
    ellipsis = _OVER_ELLIPSIS_RE.search(text)
    if tell or elongation or ellipsis:
        found = tell or (elongation.group(0) if elongation else ellipsis.group(0))
        reasons.append(
            f"artificial_typos: {found.strip()!r} — a manufactured misspelling or "
            "a stretched word is the loudest tell there is, and it is worse than "
            "a dull reply"
        )

    # --- §C.4 the anti-polish measures -------------------------------------
    # All three are scoped to >=3 sentences. A one- or two-sentence reply cannot
    # be over-polished; it can only be short, which is the goal. The operator's
    # own two-sentence example is exempt by that gate, correctly.
    units = _sentence_units(text)
    if len(units) >= 3:
        # P1. Metronome prose. SAMPLE standard deviation, not population: the
        # spec's own worked example (14/15/14 units -> variation 0.04) is the
        # sample figure, and the two differ by 22% on a three-sentence reply,
        # which is the difference between a reject and a pass.
        #
        # THE MEAN-LENGTH CONDITION IS A DEVIATION FROM THE SPEC AND IT IS
        # LOAD-BEARING. Uniformity alone is not polish: measured over the whole
        # family x account x warmth compose grid on HEAD (270 renders of three
        # or more sentences), 23 of the deterministic drafter's own outputs sit
        # under a 0.20 variation — the LOWEST at 0.062 (9/10/9 units), and every
        # one of them is the short, warm register this wave exists to produce.
        # Their mean sentence length tops out at 10.7 units. The spec's own
        # calibration example of a paragraph is 14.3. So a uniformity rule with
        # no length condition is not a polish gate at all: it is a gate against
        # writing three short sentences, and it would have rejected roughly one
        # compose in twelve, concentrated on the warmest openers.
        mean = sum(units) / len(units)
        cv = (statistics.stdev(units) / mean) if mean else 0.0
        cv_floor = float(_threshold(ctx, "polish_cv_floor"))
        units_floor = float(_threshold(ctx, "polish_sentence_units_floor"))
        if cv < cv_floor and mean >= units_floor:
            shape = "/".join(str(u) for u in units)
            reasons.append(
                f"metronome_prose: {len(units)} sentences of {shape} content units "
                f"(variation {cv:.2f} < {cv_floor:.2f}, mean {mean:.1f} >= "
                f"{units_floor:.0f}) — real speech varies its sentence length; "
                "this is a paragraph, not a comment"
            )

        # P2. The memo. THE SPEC'S FORM IS "no fragment and no contraction in a
        # >=3-sentence reply"; THIS ADDS TWO CONJUNCTS — paragraph-scale
        # sentences (the same `units_floor` P1 takes, for the same measured
        # reason) and no human-register marker anywhere — AND BOTH DEVIATIONS
        # ARE DELIBERATE.
        #
        # Measured over 972 deterministic renders on HEAD (the tail grid plus
        # the family x account x warmth compose grid), the spec's two-conjunct
        # form rejects the drafter's own output in three separate ways: the
        # module's `CLEAN_DRAFT` fixture, three of eleven distinct family
        # renders, and — with the marker conjunct alone — the flagship and
        # founder house shape, which is a data drop plus a terse two-sentence
        # verdict at 13/7/7 units. That last one is the tell: `_sentences`
        # splits on the newline between gift and doorway, so a 27-unit reply of
        # SHORT sentences counts as three, and the two desks whose §5 register
        # map lists "anything warm" in its Never column can never carry a
        # marker. Left as specified, a polish rule becomes a rule against
        # writing three short sentences, aimed hardest at the one register the
        # doctrine PINS.
        #
        # With both conjuncts the false-positive count over those 972 renders is
        # ZERO, and the rule still says what it meant: a memo is three complete,
        # uncontracted, PARAGRAPH-LENGTH sentences with nothing conversational
        # anywhere in them. `warmth_markers` is this module's own closed-class
        # register detector, reused rather than re-derived — one guard, two
        # callers.
        fragment = min(units) <= 4
        contraction = bool(_CONTRACTION_RE.search(text))
        if (mean >= units_floor and not fragment and not contraction
                and not warmth_markers(text, ctx)):
            reasons.append(
                f"memo_prose: {len(units)} complete sentences averaging "
                f"{mean:.1f} content units, no fragment, no contraction and no "
                "conversational register anywhere — that is a memo, and the "
                "corpus's median winner is eleven words"
            )

    # P3. The balanced-clause tell, NOT sentence-count scoped: two of these in
    # one short reply is a rhythm, wherever the line breaks fall.
    balanced = sum(len(r.findall(text)) for r in _BALANCED_CLAUSE_RES)
    if balanced >= 2:
        reasons.append(
            f"balanced_clause_tell: {balanced} 'not just X but Y' / 'it is not X, "
            "it is Y' constructions in one reply — one is a sentence a person "
            "writes, two is a generator's rhythm"
        )
    return _verdict("register_discipline", reasons)


# ---------------------------------------------------------------------------
# 12. Fabrication — AM-R1 on EVERY account, with the sentence quoted
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
# 13. Dignity / screenshot rubric — the ONE place an LLM may speak
# ---------------------------------------------------------------------------
def dignity(draft: str, ctx: dict) -> dict[str, Any]:
    """Would this read as a serious desk if screenshotted next to our profile?

    Deterministic layer only. The LLM de-escalation hook is applied by
    ``run_critics``, never here, so this function stays pure and testable.
    """
    reasons: list[str] = []
    low = draft.lower()
    # WORD BOUNDARIES, AND THEY ARE LOAD-BEARING. The bare `token in low` form
    # this replaced rejected two ordinary market words on a contempt list they
    # have nothing to do with: "duration" contains "ratio" and "scope" contains
    # "cope", so "Higher oil -> stickier inflation -> fewer cuts -> lower
    # long-duration multiples" — a legal, on-beat compact chain — came back as a
    # contempt tell, and so would any reply about the scope of a guide. Both are
    # in `_MECHANISM_TOKENS`, i.e. words this desk is built to use. Found by the
    # XG-W4b calibration set; the multi-word entries ("shut up", "lol no") are
    # unaffected because the boundaries sit outside the whole phrase.
    for token in _DIGNITY_TOKENS:
        if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", low):
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
    "reply_elements": reply_elements,
    "register_discipline": register_discipline,
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
    "REGISTER_RULE_IDS", "UNCERTAINTY_MARKERS", "SHORT_FORM_SHAPES",
    "run_critics", "screen", "stamp", "our_handles", "load_theses", "number_tokens",
    "informational_surplus", "corpus_near_dup", "blocklist",
    "position_consistency", "persona_label", "reply_value", "fact_discipline",
    "vocab", "warmth_register", "reply_elements", "register_discipline",
    "fabrication", "dignity",
    "warmth_markers", "reply_dial_for",
    "elements_present", "specific_reference", "short_form_engaged",
]
