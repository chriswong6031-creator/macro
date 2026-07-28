"""engine/marketing/value_gate.py — the Gift-Grip-Proof publish gate (XG-W3).

The editorial constitution §7.1 gives the model:

    Publishability ≈ Gift × Grip × Voice fit × Proof
    Virality option value rises when a Bridge is present

Charter §2 adopts it as THE publish gate, "with Bridge as a non-blocking
virality marker — the constitution's own formula: Bridge raises option value, it
never blocks". This module is that gate, deterministic:

    Gift   what does the reader gain? (§7.2 informational-surplus test)
    Grip   why do they stop, feel, or remember? (a non-template hook)
    Proof  why should they believe it? (chart / stat / citation / instrument)
    Bridge who beyond the niche can transmit it? — MARKER ONLY, never blocks

WHAT THIS GATE IS, AND IS NOT.  It is a FLOOR that catches the failure modes the
constitution names by hand: restating the source ("we rewrote the headline is not
an answer"), a bare template stem with no hook, and an assertion with no evidence
object. It is NOT a quality oracle and does not pretend to score taste. Every
element is a deterministic, greppable predicate over the emitted text and its
own metadata — no model, no learned weight, no LLM. Charter §2 amendment 9
(LLM-never-scores) and the house epistemics law both bind here: this is
display-tier internal machinery, so it ships freely, but it may never call
itself calibrated.

CALIBRATION IS AN EMPIRICAL CONSTRAINT, NOT A PREFERENCE.  The XG-W3 gate
must not silently silence the two live desks. The thresholds below were tuned
against the committed `data/marketing/content_plan.json` — every one of the
flagship's and founder's deterministic posts must pass — and
`tests/test_marketing_desk_feeds.py` pins that as a regression fixture. The
per-kind proof tiers exist because the corpus says they must: education posts
are evergreen explainers carrying no number, no cashtag and no chart, and the
constitution's own surplus list admits "a memorable explanation" as a gift. A
uniform hard-evidence rule would have deleted them.

PROOF IS TIERED, AND THE TIER IS RECORDED.  `hard` (chart/media, a whitelisted
number, or a citation), `instrument` (a named instrument from our own universe —
for a watchlist post the claim IS list membership, and the ticker plus
provenance is the receipt), `reasoning` (an explicit decision rule or
conditional — the only tier `education` may rest on). The verdict records WHICH
tier carried the post, so a reviewer can see at a glance that a signal post
rested on a number and not on vibes, and so XG-W6 can tighten a tier once
telemetry exists.

LLM MAY ONLY DE-ESCALATE.  `deescalate()` turns a pass into an abstention. There
is deliberately no inverse: no function in this module can raise a failing
element to passing, and `tests/test_marketing_desk_feeds.py` asserts that by
walking the module's AST. A critic may veto; it may never promote.

Public API:
    evaluate(headline, body, *, kind, ...) -> Verdict
    deescalate(verdict, *, reason, actor, note="") -> Verdict
    verdict_metadata(verdict) -> dict     # the item["source"]["value_gate"] payload
    PROOF_TIERS / KIND_PROOF
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

__all__ = [
    "Verdict",
    "PROOF_TIERS",
    "KIND_PROOF",
    "evaluate",
    "deescalate",
    "verdict_metadata",
]

#: Proof tiers, strongest first. A kind's entry in KIND_PROOF is the WEAKEST
#: tier it may rest on; anything stronger also satisfies it.
PROOF_TIERS: tuple[str, ...] = ("hard", "instrument", "reasoning")

#: The weakest proof tier each kind may rest on.
#:
#: Derived from the live corpus, not from taste: every non-education post in
#: `data/marketing/content_plan.json` carries a digit, a cashtag or a chart, so
#: requiring `instrument` or better costs nothing real; education carries none
#: of the three in 14/14 posts and rests on an explicit decision rule instead.
#: Kinds that ASSERT A STATE OR A MOVE (signal, chart, mover, event, macro,
#: receipt, theme_list, earnings, breaking, wire) need `hard`.
KIND_PROOF: dict[str, str] = {
    "signal": "hard",
    "chart": "hard",
    "mover": "hard",
    "theme_list": "hard",
    "receipt": "hard",
    "event": "hard",
    "macro": "hard",
    "earnings": "hard",
    "breaking": "hard",
    "wire": "hard",
    # The claim is list membership; the named instrument plus provenance is the
    # receipt. 106/120 live watchlist posts carry a cashtag, the rest a number.
    "watchlist": "instrument",
    # Evergreen explainer. §7.2 admits "a memorable explanation" as a gift and
    # §8.4 ranks educational evergreen content as legitimate. Its proof is the
    # rule it states, which is falsifiable in the reader's own use.
    "education": "reasoning",
}
_DEFAULT_PROOF = "hard"

# ─────────────────────────────────────────────────────────────────────────────
# Detectors. Each is a small, named, greppable predicate — deliberately not one
# clever regex, because a reviewer has to be able to see WHY a post passed.
# ─────────────────────────────────────────────────────────────────────────────
_DIGIT_RE = re.compile(r"\d")
_CASHTAG_RE = re.compile(r"\$[A-Za-z]{1,6}\b")
_URL_RE = re.compile(r"https?://\S+")

#: A conditional / decision rule — the §7.2 "falsification condition" and
#: "scenario map" surplus classes, and part of what `education` may rest on.
_RULE_RE = re.compile(
    r"\b(if|unless|until|when|once|whether|wrong|would prove|"
    r"invalidat\w*|stop|trigger\w*|condition|threshold|decides?|depends?|"
    r"certaint\w+|rule)\b",
    re.I,
)
#: A definition or boundary — "a memorable explanation" on the §7.2 surplus
#: list, and the other thing an evergreen explainer may rest on. An education
#: post's product IS the distinction it draws ("a setup is X, NOT a buy
#: signal"), which the reader can apply and test in their own use.
_EXPLANATION_RE = re.compile(
    r"\b(means?|meaning|is an?|are an?|isn'?t an?|not an?|a reason|"
    r"the difference|think of|in short|the point|the whole|actually|"
    r"version|what'?s a)\b",
    re.I,
)
#: Mechanism / causal connective — "a mechanism" on the surplus list.
_MECHANISM_RE = re.compile(
    r"\b(because|so that|which means|means that|drives?|driven by|"
    r"transmi\w+|knock-?on|second-?order|feeds? through|leads? to|"
    r"while|whereas|even though|despite|instead of|rather than)\b",
    re.I,
)
#: Contrast / tension — a grip device, and §7.3's "agree or disagree" social object.
_CONTRAST_RE = re.compile(
    r"\b(more than|less than|most|least|not|isn'?t|doesn'?t|don'?t|won'?t|"
    r"but|however|yet|still|vs\.?|versus|instead|rather|"
    r"disagree\w*|against|beyond|only|never|nobody|everyone)\b",
    re.I,
)
#: Why-now (§7.5) — a timeliness hook.
_WHY_NOW_RE = re.compile(
    r"\b(today|tonight|this (week|morning|afternoon|month)|just|now|"
    r"overnight|pre-?market|at the (open|close)|so far|latest|"
    r"since|yesterday|ahead of|this year)\b",
    re.I,
)
#: An interrogative or explanatory lead — a grip device ("answer a precise
#: question" on the §7.3 social-object list).
_INTERROGATIVE_RE = re.compile(r"^\s*(how|what|where|why|who|which|when)\b|\?", re.I)
#: First/second person stance — the human response that reduces confusion.
_PERSON_RE = re.compile(r"\b(i|i'?m|i'?ll|i'?ve|my|we|we'?re|our|you|you'?re|your)\b", re.I)
#: A bare INSTRUMENT with no cashtag sigil. The live corpus writes headlines
#: like "CBOE, one chart" and "MSFT | tape check" — the ticker is the specific
#: even without the "$". An all-caps 2-6 letter run is a ticker in this corpus;
#: the stoplist keeps common all-caps words from counting as instruments.
_BARE_TICKER_RE = re.compile(r"\b[A-Z]{2,6}\b")
_NOT_TICKERS: frozenset[str] = frozenset(
    {"AI", "US", "EU", "UK", "CPI", "PPI", "GDP", "FED", "FOMC", "ETF", "IPO",
     "CEO", "CFO", "OK", "TL", "DR", "PM", "AM", "ET", "UTC", "Q", "YTD", "EPS"}
)
#: An evaluative or compressive device — §11.3 "memorable compression". The
#: live desks lean on terse judgment headlines ("The honest macro read",
#: "Invalidation, fast", "Quick macro note") whose hook IS the compression.
_EVALUATIVE_RE = re.compile(
    r"\b(honest|quick|fast|slow|worth|better|best|worse|worst|real|actual\w*|"
    r"simple|short|long|boring|hard|easy|clear|obvious|quiet\w*|key|main|"
    r"big|small|important|useful|useless|ugly|clean|messy|weird|odd|"
    r"one|two|three|first|last|next|whole|entire)\b",
    re.I,
)
#: Deictic pointer — "here's the tape", "this week's read". Points at a thing
#: the reader can look at, which is the cheapest honest hook there is.
_DEICTIC_RE = re.compile(r"\b(here'?s?|there'?s?|this|that|these|those)\b", re.I)
#: A compression construction: "X: Y" or "X, Y" or "X | Y" — the terse
#: two-beat headline shape both live desks use constantly.
_COMPRESSION_RE = re.compile(r"[:|,–—-]\s*\S")


def _has_bare_ticker(text: str) -> bool:
    for tok in _BARE_TICKER_RE.findall(str(text)):
        if tok not in _NOT_TICKERS:
            return True
    return False

#: Bridge (NON-BLOCKING): could someone outside the niche transmit this?
#: Plain-language framings, analogies, and broadly legible stakes.
_BRIDGE_RE = re.compile(
    r"\b(like|as if|think of|imagine|the way|in plain|simply|basically|"
    r"anyone|everyone|most people|ordinary|household|"
    r"analog\w+|metaphor|story|reminds?)\b",
    re.I,
)

#: A body this short is a stem, not a post.
_MIN_BODY_WORDS = 6
#: Jaccard at or above which the copy is a restatement of its own source
#: headline (§7.2: "We rewrote the headline is not an answer").
_RESTATEMENT_JACCARD = 0.60


@dataclass(frozen=True)
class Verdict:
    """The Gift-Grip-Proof verdict recorded on every emission."""

    gift: bool
    grip: bool
    proof: bool
    #: Non-blocking virality marker (§7.1).
    bridge: bool
    #: "pass" | "abstain"
    verdict: str
    #: Which proof tier carried the post ("" when proof failed).
    proof_tier: str = ""
    #: Why it failed, or why an LLM de-escalated it. Never free-text on the
    #: deterministic path — these are fixed element names.
    reasons: tuple[str, ...] = ()
    #: Which detector fired for each element, for review and XG-W6 telemetry.
    components: dict[str, Any] = field(default_factory=dict)
    #: True when a critic de-escalated a deterministic pass.
    llm_deescalated: bool = False

    def __bool__(self) -> bool:
        return self.verdict == "pass"


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", str(text))


def _restates(text: str, source_headline: str) -> bool:
    """Is the copy a near-restatement of the headline it came from?

    Reuses `outbox.token_jaccard` — the same tokenizer the near-dup radar uses,
    so "too similar" means one thing across the whole marketing lobe.
    """
    src = str(source_headline or "").strip()
    if not src:
        return False
    try:
        from engine.marketing.outbox import token_jaccard

        return token_jaccard(str(text), src) >= _RESTATEMENT_JACCARD
    except Exception:
        return False


def _proof_tier(
    text: str,
    *,
    has_media: bool,
    numbers_whitelist: Iterable[str] = (),
    citation: str = "",
) -> str:
    """The STRONGEST proof tier this copy reaches, or "" for none."""
    if has_media:
        return "hard"
    if citation and _URL_RE.search(str(citation)):
        return "hard"
    if _URL_RE.search(text):
        return "hard"
    wl = {str(n) for n in (numbers_whitelist or ())}
    if wl:
        # A number the fact layer vouches for is the strongest textual evidence.
        for tok in _words(text):
            if tok in wl:
                return "hard"
    if _DIGIT_RE.search(text):
        # A digit-bearing stat with no whitelist supplied. The whitelist check
        # in `copywriter.validate_copy` is what proves a number is OURS; this
        # gate is downstream of it, so a surviving number is already vouched.
        return "hard"
    if _CASHTAG_RE.search(text) or _has_bare_ticker(text):
        return "instrument"
    if _RULE_RE.search(text) or _EXPLANATION_RE.search(text):
        return "reasoning"
    return ""


def _tier_ok(reached: str, required: str) -> bool:
    if not reached:
        return False
    try:
        return PROOF_TIERS.index(reached) <= PROOF_TIERS.index(required)
    except ValueError:
        return False


def evaluate(
    headline: str,
    body: str,
    *,
    kind: str,
    has_media: bool = False,
    numbers_whitelist: Iterable[str] = (),
    source_headline: str = "",
    citation: str = "",
    franchise_contract: Sequence[str] = (),
) -> Verdict:
    """Run the deterministic Gift-Grip-Proof gate over one emission.

    `source_headline` is the upstream headline for a breaking/press item, used
    by the informational-surplus test. `franchise_contract` is recorded for
    review (a franchise declares what its gift is) but does not gate — a
    contract is a prompt instruction, and enforcing it as a text predicate would
    be a keyword test wearing an editorial costume.
    """
    hl = str(headline or "")
    bd = str(body or "")
    text = f"{hl} {bd}".strip()
    required = KIND_PROOF.get(str(kind), _DEFAULT_PROOF)

    # ── PROOF ───────────────────────────────────────────────────────────────
    reached = _proof_tier(
        text, has_media=has_media, numbers_whitelist=numbers_whitelist, citation=citation
    )
    proof = _tier_ok(reached, required)

    # ── GIFT (§7.2 informational surplus) ───────────────────────────────────
    body_words = len(_words(bd))
    restates = _restates(text, source_headline)
    surplus = {
        "stat": bool(_DIGIT_RE.search(text)),
        "instrument": bool(_CASHTAG_RE.search(text) or _has_bare_ticker(text)),
        "mechanism": bool(_MECHANISM_RE.search(text)),
        "condition": bool(_RULE_RE.search(text)),
        "explanation": bool(_EXPLANATION_RE.search(text)),
        "media": bool(has_media),
        "stance": bool(_PERSON_RE.search(text)),
    }
    gift = (body_words >= _MIN_BODY_WORDS) and (not restates) and any(surplus.values())

    # ── GRIP (§7.1 — why stop, feel, remember) ──────────────────────────────
    #
    # HONEST SCOPE. Grip is the least mechanisable of the three elements. This
    # predicate catches what a deterministic rule CAN catch — a bare template
    # stem, an unrendered slot ("Circling" with an empty cashtag), an empty
    # headline. It does not claim to tell a strong hook from a weak one; that
    # taste judgment stays with the persona codex and, at XG-W4, the critic
    # pass. The device set is broad on purpose, and which device fired is
    # recorded so the bar can be raised on evidence rather than on a hunch.
    devices = {
        "specific": bool(_CASHTAG_RE.search(hl) or _DIGIT_RE.search(hl) or _has_bare_ticker(hl)),
        "contrast": bool(_CONTRAST_RE.search(hl)),
        "why_now": bool(_WHY_NOW_RE.search(hl)),
        "interrogative": bool(_INTERROGATIVE_RE.search(hl)),
        "stance": bool(_PERSON_RE.search(hl)),
        "evaluative": bool(_EVALUATIVE_RE.search(hl)),
        "deictic": bool(_DEICTIC_RE.search(hl)),
        "compression": bool(_COMPRESSION_RE.search(hl)),
    }
    grip = bool(hl.strip()) and any(devices.values())

    # ── BRIDGE (non-blocking marker) ────────────────────────────────────────
    bridge = bool(_BRIDGE_RE.search(text)) or surplus["mechanism"]

    reasons: list[str] = []
    if not gift:
        if body_words < _MIN_BODY_WORDS:
            reasons.append("gift:body_too_thin")
        elif restates:
            reasons.append("gift:restates_source")
        else:
            reasons.append("gift:no_informational_surplus")
    if not grip:
        reasons.append("grip:no_hook")
    if not proof:
        reasons.append(f"proof:below_{required}")

    return Verdict(
        gift=gift,
        grip=grip,
        proof=proof,
        bridge=bridge,
        verdict="pass" if (gift and grip and proof) else "abstain",
        proof_tier=reached if proof else "",
        reasons=tuple(reasons),
        components={
            "kind": str(kind),
            "required_proof": required,
            "reached_proof": reached,
            "surplus": surplus,
            "grip_devices": devices,
            "body_words": body_words,
            "franchise_contract": list(franchise_contract),
        },
    )


def deescalate(
    verdict: Verdict,
    *,
    reason: str,
    actor: str = "llm_critic",
    note: str = "",
) -> Verdict:
    """Turn a PASS into an abstention. The only direction a critic may move.

    Charter §2 amendment 9 + the house epistemics law: an LLM may veto and
    de-escalate, never originate or promote. There is deliberately no
    `escalate()` / `promote()` counterpart in this module, and the test suite
    walks the AST to prove no function ever flips a False element to True.

    De-escalating an already-abstaining verdict is a no-op that still records
    the extra reason, so a critic's objection is never lost.
    """
    r = str(reason or "").strip() or "unspecified"
    tag = f"{actor}:{r}"
    reasons = tuple(verdict.reasons) + (tag,)
    components = dict(verdict.components)
    if note:
        components.setdefault("deescalation_notes", []).append(str(note))
    return Verdict(
        gift=verdict.gift,
        grip=verdict.grip,
        proof=verdict.proof,
        bridge=verdict.bridge,
        verdict="abstain",
        proof_tier=verdict.proof_tier,
        reasons=reasons,
        components=components,
        llm_deescalated=True,
    )


def verdict_metadata(verdict: Verdict) -> dict[str, Any]:
    """The payload stamped onto `item["source"]["value_gate"]`.

    Every emission carries this (charter §0 XG-W3 gate). Kept flat and JSON-safe
    so it survives the outbox round-trip and is greppable in the ledger.
    """
    return {
        "verdict": verdict.verdict,
        "gift": verdict.gift,
        "grip": verdict.grip,
        "proof": verdict.proof,
        "bridge": verdict.bridge,
        "proof_tier": verdict.proof_tier,
        "reasons": list(verdict.reasons),
        "llm_deescalated": verdict.llm_deescalated,
        "components": verdict.components,
    }
