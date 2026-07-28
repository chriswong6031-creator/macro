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
    fact_discipline        numbers only from whitelisted own-feed values
    vocab                  the shared banned-vocab guard + the expression dial
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
    "fact_discipline",
    "vocab",
    "dignity",
)

# --- thresholds (charter §8: config keys, not constants) --------------------
DEFAULT_THRESHOLDS: dict[str, float] = {
    #: Jaccard against the PARENT post. Lower than the corpus bar: a reply that
    #: is 55% the parent's own words has added nothing, even if it reads new.
    "parent_jaccard": 0.55,
    #: Jaccard against our own recent replies (same account and across desks).
    "corpus_jaccard": 0.50,
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
    """
    refs = _referents(draft)
    if refs:
        return _verdict("persona_label", [])
    return _verdict("persona_label", [
        "no concrete market referent (ticker, level, or mechanism) — the draft "
        "is interesting only because of who says it"
    ])


# ---------------------------------------------------------------------------
# 6. Fact discipline — numbers whitelist
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
# 7. Vocab — the SHARED guard, called not forked
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
# 8. Dignity / screenshot rubric — the ONE place an LLM may speak
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
    "fact_discipline": fact_discipline,
    "vocab": vocab,
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
    "run_critics", "screen", "stamp", "our_handles", "load_theses", "number_tokens",
    "informational_surplus", "corpus_near_dup", "blocklist",
    "position_consistency", "persona_label", "fact_discipline", "vocab", "dignity",
]
