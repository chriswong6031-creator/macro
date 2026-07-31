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

CALIBRATION WARNING — THE MARGIN IS ONE WORD (review F8).  The live-desk
regression passes because the corpus's terse headlines happen to contain a
device this module recognises: "The honest macro read" passes on the single word
"honest", "Macro, quick" on "quick". Delete that one adjective and the post
abstains for `grip:no_hook`. That is a THIN margin, and it means the 212/218
figure is evidence that the gate does not silence TODAY's templates — not
evidence that the thresholds are right. Two consequences: (1) a template edit
upstream can flip posts to abstaining without anyone touching this file, which
is why the frozen fixture exists; (2) nobody should read the pass rate as
validation of the bar. Before `value_gate.enforce` is flipped on, the corpus
must be extended to the kinds and languages the current sample does not cover —
see the PRE-ARMING TODO below.

TODO(xg-w3-review): PRE-ARMING REQUIREMENT — before `value_gate.enforce: true`,
extend the regression corpus beyond today's 8 observed kinds to the 7 uncovered
ones (wire, breaking, earnings, receipt, reply, news, plus any franchise-shaped
emission), to zh/CJK bodies, and to weekend/holiday posts. The current fixture
samples ONE nightly plan from ONE market day in ONE language; arming a publish
gate on that sample would be exactly the "validated on the generator it polices"
error the charter §8 register warns about.

CJK IS UNBLOCKED, NOT SOLVED (review F7).  `_words()` counts CJK codepoints, and
the interrogative/compression devices accept full-width punctuation, so a zh post
is no longer STRUCTURALLY unable to pass — before this it was: a latin-only
tokenizer scored every Chinese body at 0 words and failed it on length alone. But
the remaining grip devices (contrast, evaluative, why-now, stance) are still
English lexicons, so a zh headline can currently only reach grip through a
number, an instrument, punctuation or a question mark. Closing that properly
needs zh device lists built against a real zh corpus — part of the pre-arming
work above, and the reason a zh abstention today is RECORDED and not acted on.

PROOF IS TIERED, AND THE TIER IS RECORDED.  `hard` (chart/media, a whitelisted
number, or a citation), `instrument` (a named instrument from our own universe —
for a watchlist post the claim IS list membership, and the ticker plus
provenance is the receipt), `reasoning` (an explicit decision rule or
conditional — the only tier `education` may rest on). The verdict records WHICH
tier carried the post, so a reviewer can see at a glance that a signal post
rested on a number and not on vibes, and so XG-W6 can tighten a tier once
telemetry exists.

LLM MAY ONLY DE-ESCALATE.  `deescalate()` turns a pass into an abstention. There
is deliberately no inverse. The guard in `tests/test_marketing_desk_feeds.py` is
CAPABILITY-shaped, not name-shaped (review F14): it walks the AST and requires
every `Verdict(...)` construction to sit inside a blessed constructor, and
requires `deescalate`'s own construction to hard-code `verdict="abstain"`. The
earlier name-scan version — "no function called promote/escalate" — would have
waved through a `_recheck()` that quietly rebuilt a Verdict with `proof=True`,
which is the shape this rule actually has to stop. A critic may veto; it may
never promote.

Public API:
    evaluate(headline, body, *, kind, ...) -> Verdict
    deescalate(verdict, *, reason, actor, note="") -> Verdict
    verdict_metadata(verdict) -> dict     # the item["source"]["value_gate"] payload
    PROOF_TIERS / KIND_PROOF
"""
from __future__ import annotations

import copy
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
    # `reply` lands next door in XG-W4. Charter §2 amendment 3 puts replies at
    # dial 2 with a hard finance-value floor ("one gift, one grip, one doorway"
    # — constitution §9.3), and the gift in a reply is routinely a mechanism or
    # a condition rather than a number, so `instrument` is the honest floor.
    # Registered HERE rather than defaulted so the reply desk inherits a
    # deliberate tier instead of silently taking `_DEFAULT_PROOF`.
    "reply": "instrument",
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
#: Full-width "？" and the zh interrogative particle 吗/呢 count too — a
#: latin-only question test makes the device unreachable in zh (review F7).
_INTERROGATIVE_RE = re.compile(
    r"^\s*(how|what|where|why|who|which|when)\b|[?？]|[吗呢]\s*$", re.I
)
#: First/second person stance — the human response that reduces confusion.
_PERSON_RE = re.compile(r"\b(i|i'?m|i'?ll|i'?ve|my|we|we'?re|our|you|you'?re|your)\b", re.I)
#: A bare INSTRUMENT with no cashtag sigil. The live corpus writes headlines
#: like "CBOE, one chart" and "MSFT | tape check" — the ticker is the specific
#: even without the "$". An all-caps 2-6 letter run is a ticker in this corpus;
#: the stoplist keeps common all-caps words from counting as instruments.
_BARE_TICKER_RE = re.compile(r"\b[A-Z]{2,6}\b")
#: All-caps tokens that are NOT instruments. A false "instrument" here is a
#: false PROOF tier for watchlist/reply kinds, so the list matters (review F22):
#: "HK" and "PBOC" are Cici's everyday vocabulary and would have vouched for an
#: evidence-free post about Asia.
_NOT_TICKERS: frozenset[str] = frozenset(
    {"AI", "US", "EU", "UK", "CPI", "PPI", "GDP", "FED", "FOMC", "ETF", "IPO",
     "CEO", "CFO", "OK", "TL", "DR", "PM", "AM", "ET", "UTC", "Q", "YTD", "EPS",
     # Review F22 — regions, central banks, exchanges and index shorthand.
     "HK", "CNY", "CNH", "PBOC", "NYSE", "SPX", "CN", "JP", "KR", "TW", "SG",
     "ECB", "BOJ", "BOE", "RBA", "PCE", "ISM", "PMI", "NDX", "DJIA", "VIX",
     "APAC", "EMEA", "OPEC", "IMF", "WTO", "GMT", "EST", "PST", "HKT", "CST"}
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
#: two-beat headline shape both live desks use constantly. FULL-WIDTH forms
#: (：，、｜——) included: zh copy never uses the ASCII ones, so a latin-only
#: class made this device unreachable in Chinese (review F7).
_COMPRESSION_RE = re.compile(r"[:|,–—\-：，、｜]\s*\S")


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
#:
#: PUBLIC because producers need it, not only the gate. A lane that selects copy
#: on a different definition of "usable" than the gate admits on will build
#: drafts the gate then refuses, and the post is lost between them with nobody
#: at fault (engine/press/research_lane.compose_post, 2026-07-30). Read this name
#: rather than re-declaring the number, so raising the floor moves every stage.
MIN_BODY_WORDS = 6
#: Internal alias — this module's predicates were written against the private
#: name and there is no reason to churn them.
_MIN_BODY_WORDS = MIN_BODY_WORDS
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


#: CJK ranges: unified ideographs (+ extension A), plus kana for completeness.
#: A CJK codepoint IS a word for length purposes — Chinese does not space-
#: delimit, so a latin-only tokenizer counts zero.
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")


def _words(text: str) -> list[str]:
    """Word-ish tokens, CJK-AWARE (review F7).

    THE ZH BUG THIS FIXES: `[A-Za-z0-9']+` finds nothing in a Chinese body, so
    `body_words` came out 0, fell under `_MIN_BODY_WORDS`, and EVERY zh post
    failed `gift:body_too_thin`. The site is bilingual by law, so a latin-only
    length test silences one whole language — the exact "silent silencing" the
    calibration exercise was supposed to prevent, just aimed at zh instead of at
    the live desks.

    Each CJK codepoint counts as one token. That is the standard approximation,
    not a segmenter: it is used ONLY for a length floor, never for meaning.
    """
    s = str(text)
    return re.findall(r"[A-Za-z0-9']+", s) + _CJK_RE.findall(s)


#: Number-like tokens, DECIMAL-AWARE. The plain word tokenizer above splits
#: "402.30" into "402" and "30", so comparing it against a whitelist entry of
#: "402.30" could never match — the whitelist check would silently never fire.
_NUM_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def _num_tokens(text: str) -> set[str]:
    """Normalised number-like tokens: commas stripped, trailing zeros kept."""
    return {m.group(0).replace(",", "") for m in _NUM_TOKEN_RE.finditer(str(text))}


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
    wl = {str(n).replace(",", "").strip() for n in (numbers_whitelist or ())}
    wl.discard("")
    has_digit = bool(_DIGIT_RE.search(text))
    if wl:
        # A whitelist WAS supplied, so it is authoritative here: a number the
        # fact layer vouches for is the strongest textual evidence, and a
        # number it does NOT vouch for must not be laundered into proof by the
        # fallback below. (An unvouched number should already have been
        # rejected upstream by `copywriter.validate_copy`; if it reaches us
        # anyway, failing closed is the only safe reading.)
        if _num_tokens(text) & wl:
            return "hard"
    elif has_digit:
        # No whitelist supplied — the caller is not asserting provenance either
        # way. `copywriter.validate_copy` is what proves a number is OURS, and
        # this gate runs downstream of it, so a surviving number is treated as
        # vouched. Recorded as `hard` but the absence of a whitelist is visible
        # in `components`, so a reviewer can tell the two situations apart.
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
            # Was this kind REGISTERED, or did it silently take the default?
            # (review F7) An unregistered kind gets `_DEFAULT_PROOF`, which is
            # the strict tier — safe, but indistinguishable in the verdict from
            # a kind someone deliberately tiered. A new kind landing here should
            # be a visible decision, not a default nobody noticed.
            "kind_known": str(kind) in KIND_PROOF,
            "required_proof": required,
            "reached_proof": reached,
            "surplus": surplus,
            "grip_devices": devices,
            "body_words": body_words,
            # Whether the caller asserted number provenance at all — the
            # difference between "this number is vouched" and "nobody said".
            "numbers_whitelist_supplied": bool(numbers_whitelist),
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
    # DEEP copy (review F15). `Verdict` is a frozen dataclass, but frozen only
    # protects the ATTRIBUTE BINDINGS — `components` is a dict holding nested
    # dicts and lists, so a shallow copy would let a de-escalated verdict mutate
    # the nested `surplus`/`grip_devices` of the original. Immutability that
    # stops at the first level is not immutability.
    components = copy.deepcopy(verdict.components)
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
