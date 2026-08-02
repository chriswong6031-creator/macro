"""engine.marketing.reply_voice — the reply desk's phrasing pass (E4).

Program: **Content Studio LLM-first** §10 E4 ("reply-craft intelligence").
Doctrine: ``research/MARKETING_REPLY_DOCTRINE_BY_FABLE.md``.
Ground truth: ``research/marketing_dockets/reply_corpus_2026_07_29/``.

WHAT THIS IS
------------
``reply_drafter.compose()`` builds a deterministic draft from an own-feed fact
(the gift) plus a family template (the grip and the doorway). It is correct, it
is safe, and it reads like a template — the corpus says the winning reply is
about **eleven words**, one thought, aimed at the room. This module is the
OPTIONAL phrasing pass on top of that draft: it hands the deterministic text,
the parent post, the family's intent and the persona card to the shared provider
waterfall and asks a model to say the same thing in the register that earns a
reply on X.

The deterministic text is passed IN as an argument, so this module never imports
the drafter — the dependency points one way only (``reply_drafter`` →
``reply_voice``), exactly as ``hot_tape`` → ``hot_tape_llm``.

THE LAWS (all imported, none forked)
------------------------------------
**The engine computes, the model phrases, the LLM never originates a number.**
Every number-like token in the model's output must resolve to a number already
on the reply's own-feed whitelist. ``numeric_violations`` comes from
``hot_tape_llm`` and ``fact_discipline`` from ``reply_critics``; both are
imported, because a second number regex means a figure that clears this gate
fails the downstream one (or, worse, the reverse).

**The model never scores and never rescues.** Nothing here grades a draft.
``reply_critics.run_critics`` still runs afterwards on whatever ships, and its
LLM hook may only de-escalate (charter §2 amendment 9). This pass can only
change WORDS, and only when every gate passes.

**A dropped reply does not exist as an outcome.** ``voice_or_fallback`` ALWAYS
returns postable text — the model's phrasing when it clears every gate, the
caller's deterministic draft otherwise — and never raises. Replies are M0/M1
human-reviewed on top of that, so the failure mode of this module is "the desk
sounds like a template today", never "the desk said something we cannot stand
behind".

WHY THE WIRE'S HEDGE GATE IS **NOT** IMPORTED
---------------------------------------------
``hot_tape_llm.hedge_violations`` bans "might/appears/looks like" because a wire
reports and never predicts. A reply is a different register: conditional
confidence is Kelly's pinned voice ("if X keeps going while Y stays put…") and
the per-persona softener bans are already enforced by ``expression_dial``, which
this module DOES call. Importing the wire's hedge list here would reject the
house's own reply exemplars.

IMPORT-CLOSURE LAW
------------------
**stdlib only at module import.** ``engine.llm_auth``, ``anthropic``, ``yaml``,
``lib.config``, ``engine.marketing.copywriter``, ``hot_tape_llm``,
``reply_critics`` and ``expression_dial`` are ALL imported lazily inside
functions. The marketing-engine CI lane installs pytest + pyyaml + jinja2 and
nothing else, so a top-level ``import anthropic`` here turns that lane red at
COLLECTION, before a single test runs.

Public API
----------
    voice_or_fallback(draft, *, family, account, parent_text, numbers_whitelist,
                      parent_author, ctx, cfg, root) -> dict
    validate_reply_copy(text, *, draft, numbers_whitelist, parent_text,
                        account, family, root) -> list[str]
    build_user_message(...) -> str
    persona_card(account, cfg) -> str
    fallback_stats() -> dict
    reset_stats() -> None
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Any, Sequence

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Defaults (every one overridable from config/marketing.yml `reply_desk.voice`)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_MODEL_KEY = "marketing_copy"
DEFAULT_MAX_TOKENS = 220
#: Hard per-provider latency budget. The reply window the charter chases is
#: 5-15 minutes wide and the producer ticks inside it; a provider that has not
#: answered in 5s has already lost to the deterministic draft.
DEFAULT_CLIENT_TIMEOUT_S = 5.0
#: SDK retries defeat the failover walk (the retry re-hits the SAME dead
#: credential before the waterfall even sees it). One attempt per provider,
#: walk on failure — the CHAIN is the retry.
DEFAULT_CLIENT_MAX_RETRIES = 0
#: Runaway guard, not a budget. The producer drafts a handful per account per
#: tick; this only ever catches a pathological target list.
DEFAULT_MAX_CALLS_PER_RUN = 40
#: THE CAP IS A ROLLING WINDOW, NOT A PROCESS LIFETIME. The Hot Tape radar gets
#: a fresh process every tick, so a lifetime counter is a per-tick cap there.
#: This module's consumer is ``scripts/marketing_fastlane_daemon.py --lane
#: reply`` — a ``while True`` loop that ticks every 120s inside ONE process —
#: so a lifetime counter would permanently mute the phrasing pass after the
#: 40th reply of the daemon's life, silently, with every later reply shipping
#: the template. That is the "armed but degraded" failure class, so the counter
#: resets when the window rolls.
DEFAULT_CALL_WINDOW_S = 3600.0

#: Doctrine §3. X's hard cap is 280; the corpus median winner is 11 words, so
#: the headroom is the point, not a safety margin.
MAX_REPLY_CHARS = 240


def _long_form_families() -> frozenset[str]:
    """Families whose structure IS the payload, so they may run long.

    Owned by ``reply_critics`` — the gate that enforces it — and read here so
    the prompt and the critic cannot disagree about which family may run long.
    Unreadable → empty, i.e. the prompt asks for short copy, which is the
    conservative direction.
    """
    try:
        from engine.marketing.reply_critics import LONG_FORM_FAMILIES  # noqa: PLC0415

        return frozenset(LONG_FORM_FAMILIES)
    except Exception:  # noqa: BLE001
        return frozenset()

_ENV_FLAG = "MARKETING_LLM_ENABLED"
_TRUTHY = ("1", "true", "yes")


# ─────────────────────────────────────────────────────────────────────────────
# The prompt — exemplars transcribed from the 2026-07-29 reply corpus
# ─────────────────────────────────────────────────────────────────────────────

#: Ten corpus winners, VERBATIM, each with the like count that is its evidence
#: (doctrine §7). Kept as a constant so the test suite can pin that the prompt
#: still ships them, and so a later re-harvest replaces evidence rather than
#: taste. Deliberately EXCLUDED: the corpus's two highest-liked replies (2,186
#: and 1,877 likes) are moral-outrage one-liners on a political-crossover post —
#: the highest ceiling in the data and a standing brand exclusion (doctrine §4).
PLAYBOOK_EXEMPLARS: tuple[tuple[int, str, str], ...] = (
    (96, "sharp analogy",
     "missing earnings expectations by $3b is like showing up to the olympics "
     "and finishing second. still incredible. wall street just doesn't care."),
    (80, "sharp read",
     "KOSPI is a semiconductor ETF with miscellaneous stocks added for "
     "diversification."),
    (75, "reasoned contrarian",
     "We have not even begun to fulfill demand this is nonsense."),
    (44, "cynical rule",
     "Doesn't matter now if companies beat or not, every earnings announcement "
     "results in a lower stock price"),
    (41, "contrarian, asks for the evidence",
     "And yet they are still making record profits and revenue with no slowdown "
     "in sight. Seriously, I have yet to see a single legitimate date as to when "
     "the growth stops for this company"),
    (25, "cross-market missing number",
     "All the blood and yet, VIX is still below 20."),
    (23, "correct the record",
     "Actually closer to -10%"),
    (23, "dry wit",
     "The nerve of them to miss earnings after that whole ipo commotion"),
    (22, "checkable level",
     "Support at 900-925"),
    (13, "human reaction plus a stance",
     "Kind of a rough quarter, but I'm still watching their long-term memory "
     "play closely."),
)

#: The zero-like shapes from the same threads and the same timing window, so
#: they are directly comparable to the exemplars (doctrine §8).
ANTI_EXEMPLARS: tuple[tuple[str, str], ...] = (
    ("advice-column boilerplate that fits under any headline",
     "Breaking events like this remind us why risk management matters. Stay "
     "informed, avoid emotional decisions, and watch for official statements "
     "before jumping to conclusions."),
    ("a genuine question aimed at the poster, which reads as a DM",
     "What do you think of TIPS in this environment?"),
    ("restating a fact the thread already has",
     "All intercepted"),
    ("a one-word reaction",
     "Oh wonderful."),
    ("a plug wearing a news reaction as a costume",
     "iran news shaking markets, check cmc for real-time btc moves"),
)


def _exemplar_block() -> str:
    return "\n".join(
        f"{i}. [{likes} likes, {pattern}] {text}"
        for i, (likes, pattern, text) in enumerate(PLAYBOOK_EXEMPLARS, start=1)
    )


def _anti_block() -> str:
    return "\n".join(f"- ({why}) {text}" for why, text in ANTI_EXEMPLARS)


SYSTEM_PROMPT = f"""You write ONE reply on X for a market-research desk, under someone else's post.

A reply is rent paid for someone else's audience. The rent is a gift the thread did not already have, delivered in about eleven words, aimed at THE ROOM and never at the poster.

You are handed our own deterministic draft. It is already true and already legal. Your job is to say the SAME THING better: compress it, sharpen it, make it sound like a person who trades rather than a template. If you cannot beat it under the laws below, return it unchanged.

HARD LAWS
1. ALLOWED NUMBERS: use ONLY numbers from the ALLOWED NUMBERS list in the user message, verbatim as they are given. Never compute a new one, never extend one, never round one further, never add a number of your own. Every number you write must appear in that list. Writing none of them is fine.
2. {MAX_REPLY_CHARS} characters maximum. Target 11 to 25 words. ONE thought, not three. A reply with three claims and no closing line gets zero.
3. Keep the fact. The draft's gift is the reason we are allowed in this thread; a rewrite that drops it is not a rewrite.
4. No advice and no calls. Nothing that tells the reader to do anything: no buying, selling, entries, exits, targets, sizing, positions. No claim about what we own.
5. Never a question aimed at the poster. "What do you think of X?" is the shape that gets zero: it asks the account to do work for one person and gives bystanders nothing. A question is legal only when it is aimed at the room AND the reply still carries the fact without it.
6. Never moral outrage, never contempt, never naming or correcting a person. Fix the fact, never the human. If it would read badly screenshotted next to our profile, it does not ship.
7. No em dashes. No hashtags. No links. No @-mentions. Emoji only if the persona card grants a budget, and at most one.
8. Plain language. No study names, no internal jargon, no "our model", no "the engine", no "validated".
9. Output the reply text only. No JSON, no quotes around it, no preamble, no sign-off.

WHAT EARNS A REPLY (the five things a reply may carry)
- DATA DROP: a concrete, checkable number or level the post did not have.
- SHARP READ: one sentence that reframes the stat into something felt.
- DRY WIT: deadpan, native idiom, no setup, no explanation. Aimed at forecasts and crowds, never at people.
- USEFUL REFRAME: grant the frame, change what the move is about.
- MISSING-NUMBER CORRECTION: fix or sharpen the record with one figure, without naming anyone.

WHAT WARMTH IS AND IS NOT
This desk is written by real, named people, and people follow an account that is BOTH insightful and worth being around. A reply that is only an instrument readout gets read and forgotten. So warmth is required of the register, and it has exactly one legal shape:

WARMTH IS FUSED INTO THE CLAUSE THAT DELIVERS THE FACT. It is never a second sentence bolted on in front of one.
- YES: "Fair point but risk premia could plausibly be supportive, and breadth never followed the index up."
- NO: "Great point! Really appreciate you laying this out. Anyway, here is a stat:"
The second shape spends a whole sentence and returns nothing. It is the losing pattern in the data, not a politeness.

THE BRIGHT LINE. A reader may learn from this reply how she THINKS and how she REACTS. They may never learn anything about her LIFE. Before writing any clause, ask: could a journalist print this as a fact about her? "She thinks the tariff read is mispriced" is not a fact about her life and is lawful. "She was at a museum this weekend" is, and is forbidden.

LAWFUL, and this is where all the warmth lives:
- rhythm, sentence length, lowercase asides, fragments, the persona's own granted emoji;
- reaction to INFORMATION ("that is the whole story");
- first person about ANALYSIS: what she is watching, reading, waiting on, cannot settle;
- first person about having been WRONG in a prior public read, when the draft already says so;
- craft judgment about a chart, an argument or a dataset ("the second chart is the load bearing one");
- delight or curiosity about a market fact;
- warmth toward the other person's IDEA, never their person, looks or career;
- humour aimed at forecasts, crowds, institutions and processes, never at a person;
- sympathy for a professional setback, eight words at most, no first name.

FORBIDDEN, all of it, with no exceptions and no hedging:
- any position, trade, entry, exit, P&L or portfolio;
- any meeting, call, source, colleague or conversation;
- any testimonial about our own product;
- any place, meal, drink, purchase, commute, travel, weather, time of day or physical state;
- any claimed routine ("my third coffee", "back at my desk");
- any claimed feeling that implies a life event ("rough week for me", "running on no sleep");
- any implied physical presence ("over here in Hong Kong", "watching from the floor");
- the other person's first name.
Every one of those is a fabricated fact about a real employee. Inventing one is the single worst thing you can do here, and it is worse than writing a dull reply.

EXEMPLARS. Real replies under real finance posts, with the likes they earned. This is the REGISTER, not a phrasebook; our own laws above still decide what may ship.
{_exemplar_block()}

NEVER THESE SHAPES. All scored zero likes in the same threads, in the same hour:
{_anti_block()}

One honest note so you do not over-fit: a genuinely sharp, specific reply in the same corpus also scored zero, because it arrived hours late from a small account. A good line is necessary, not sufficient. Write the good line anyway.
"""

#: How many ratified store exemplars may join the reply prompt.
_STORE_EXEMPLAR_K = 4


def system_prompt(cfg: dict | None = None, root: Path | str | None = None) -> str:
    """``SYSTEM_PROMPT``, plus the CONFIG-PINNED exemplar-store block (§10 E3).

    ``PLAYBOOK_EXEMPLARS`` above stays the baseline and is never replaced: those
    ten are reply-corpus winners with their like counts, i.e. evidence for THIS
    register, and the store's entries are timeline posts. The store appends a
    second, operator-ratified section when — and only when —
    ``intel.exemplar_store.active_version`` pins a version.

    DARK-SAFE BY CONSTRUCTION: with no pin (the shipped default) this returns
    ``SYSTEM_PROMPT`` itself, byte for byte, and the store file is never opened.

    ``cfg`` must be the FULL marketing config for the pin to be visible — the
    pin lives under ``intel:`` and ``voice_or_fallback`` also accepts the
    narrower ``reply_desk``/``voice`` blocks, which simply carry no pin and so
    read as dark. Their numbers never widen the reply's ALLOWED NUMBERS list.
    """
    try:
        from engine.marketing import exemplar_store  # noqa: PLC0415

        shots = exemplar_store.active_exemplars(
            None, k=_STORE_EXEMPLAR_K, root=root, cfg=cfg)
    except Exception as exc:  # noqa: BLE001 — a reply must exist regardless
        log.warning("reply_voice: exemplar store unreadable (%s: %s) — playbook "
                    "exemplars only", type(exc).__name__, exc)
        return SYSTEM_PROMPT
    if not shots:
        return SYSTEM_PROMPT

    lines = [
        f"ALSO RATIFIED (exemplar store version {shots[0].get('exemplar_version')}). "
        "Posts from other accounts the operator approved for their register. "
        "They are TIMELINE posts, not replies: take the register, never the shape, "
        "and never their numbers. Every figure you write must still be in ALLOWED "
        "NUMBERS.",
    ]
    for shot in shots:
        text = " ".join(str(shot.get("text") or "").split())
        if text:
            lines.append(f"- [{shot.get('register') or 'unknown'}] {text}")
    if len(lines) == 1:
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + "\n" + "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# Module counters (the producer's fallback-rate report reads these)
# ─────────────────────────────────────────────────────────────────────────────

#: ``repairs`` counts SECOND turns taken after a validation rejection (see the
#: repair block in ``voice_or_fallback``); it is not a fallback and is not
#: counted as one, so ``fallback_rate`` still means "did not ship model copy".
_STAT_KEYS = ("calls", "llm", "fallback_validation", "fallback_provider", "off",
              "cap_hits", "repairs")
_STATS: dict[str, int] = {k: 0 for k in _STAT_KEYS}
#: ``time.monotonic()`` of every provider call still inside the rolling window,
#: oldest first. A TIMESTAMP LOG, not a counter: see ``_take_call_slot``.
_CALL_TIMES: "deque[float]" = deque()


def fallback_stats() -> dict:
    """Counters for this process: how often the model served vs fell back.

    Keys: ``calls`` (voice attempts), ``llm``, ``fallback_validation``,
    ``fallback_provider``, ``off``, ``cap_hits`` (attempts refused by the
    runaway guard, which are ALSO counted as ``fallback_provider``),
    ``repairs`` (second turns taken after a validation rejection), plus a
    derived ``fallback_rate`` (the share of attempts that did NOT ship model
    copy). A copy — mutating it is a no-op.
    """
    out = dict(_STATS)
    calls = out.get("calls", 0)
    fell_back = calls - out.get("llm", 0)
    out["fallback_rate"] = round(fell_back / calls, 4) if calls else 0.0
    return out


def reset_stats() -> None:
    """Zero the counters AND the call-cap window. For tests and the dry run."""
    for k in _STAT_KEYS:
        _STATS[k] = 0
    _CALL_TIMES.clear()


def _take_call_slot(max_calls: int, window_s: float) -> bool:
    """Claim one provider call against the ROLLING runaway guard.

    Returns False when the last ``window_s`` seconds already hold ``max_calls``
    calls. The window rolls continuously (see ``DEFAULT_CALL_WINDOW_S``): the
    caller here is a long-lived daemon, and a guard that never resets is an off
    switch with a delay.

    A TIMESTAMP DEQUE, NOT A TUMBLING COUNTER. The counter-plus-window-start form
    this replaced reset the count wholesale the moment the window elapsed, so a
    cap of 40/hour actually permitted 80 calls in two seconds across the
    boundary — 40 at t=3599 and 40 more at t=3601 — which is the exact burst a
    runaway guard exists to stop, and it read as compliant in the counters. The
    deque holds at most ``max_calls`` entries, so the memory is bounded by the
    cap, not by traffic.
    """
    now = time.monotonic()
    cutoff = now - max(1.0, window_s)
    while _CALL_TIMES and _CALL_TIMES[0] <= cutoff:
        _CALL_TIMES.popleft()
    if len(_CALL_TIMES) >= max_calls:
        return False
    _CALL_TIMES.append(now)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Small local scanners (token shapes, not gates — every GATE is imported)
# ─────────────────────────────────────────────────────────────────────────────

_CASHTAG_RE = re.compile(r"\$[A-Za-z]{1,6}(?:[.\-][A-Za-z]{1,4})?")
_URL_RE = re.compile(r"https?://\S+|\bwww\.\S+", re.IGNORECASE)
#: `#` followed by a letter. `#` followed by a DIGIT is the streak device
#: ("Day #9") and must survive.
_HASHTAG_RE = re.compile(r"#[A-Za-z_]")
_MENTION_RE = re.compile(r"(?<![\w.])@[A-Za-z0-9_]{2,}")
_DASH_TELLS = ("—", "–", "―")


def _tidy(text: str) -> str:
    """Strip the wrappers a model adds despite law 9 — quotes, fences, blanks."""
    out = str(text or "").strip()
    if out.startswith("```"):
        out = re.sub(r"^```[a-zA-Z]*\s*", "", out)
        out = re.sub(r"\s*```$", "", out).strip()
    if len(out) >= 2 and out[0] == out[-1] and out[0] in "\"'":
        out = out[1:-1].strip()
    return out


def _cashtags(text: str) -> set[str]:
    return {m.group(0).upper() for m in _CASHTAG_RE.finditer(str(text or ""))}


# ─────────────────────────────────────────────────────────────────────────────
# The persona card + the user turn
# ─────────────────────────────────────────────────────────────────────────────

def persona_card(account: str, cfg: dict | None) -> str:
    """The desk's own voice notes, verbatim from ``copywriter.personas``.

    ONE source of persona truth. The dial (``expression_dial``) enforces the
    same register mechanically after the call, so a card copied and edited here
    would be a second, drifting definition of the same person.
    """
    personas = ((cfg or {}).get("copywriter") or {}).get("personas") or {}
    card = personas.get(str(account)) or {}
    if not card:
        return (f"DESK: {account or 'the desk'} (no persona card on file; "
                "stay plain and factual).")

    lines = [f"DESK: {card.get('name') or account}"]
    notes = str(card.get("voice_notes") or "").strip()
    if notes:
        lines.append(f"VOICE: {' '.join(notes.split())}")
    for example in list(card.get("example_lines") or [])[:2]:
        lines.append(f"HOW THIS DESK SOUNDS: {example}")

    beat = ""
    for acct in ((cfg or {}).get("desk_network") or {}).get("accounts") or []:
        if isinstance(acct, dict) and str(acct.get("id")) == str(account):
            beat = str(acct.get("beat") or "")
            break
    if beat:
        lines.append(f"BEAT: {beat}")
    return "\n".join(lines)


def _dashless(text: str) -> str:
    """A rule message with the house-banned dashes taken out.

    Violation strings are echoed VERBATIM into the repair turn, and a model that
    has just read an em dash writes one, which the dash ban then rejects —
    burning the reply's one repair round on a defect the gate itself supplied.
    Lifted deliberately from ``copywriter._dashless``: same failure, same fix,
    and the reply desk's violation strings come from four different modules.
    """
    out = str(text or "")
    for ch in _DASH_TELLS:
        out = out.replace(f" {ch} ", ": ").replace(ch, ":")
    return out


def build_user_message(
    *,
    draft: str,
    family: str,
    account: str,
    parent_text: str,
    parent_author: str = "",
    numbers_whitelist: Sequence[str] = (),
    cfg: dict | None = None,
    family_spec: dict | None = None,
    warmth: str = "",
    warmth_spec: dict | None = None,
    violations: Sequence[str] | None = None,
) -> str:
    """The user turn: the parent post, our draft, the two intents, the card.

    ``family_spec`` is the ``reply_drafter.FAMILIES`` entry and ``warmth_spec``
    the ``WARMTH_MOVES`` entry, both passed IN by the caller so this module
    never imports the drafter (the dependency points one way). Absent → the id
    alone.

    THE WARMTH MOVE IS STATED AS AN INTENT, NOT AS A PHRASE TO REUSE. The
    deterministic draft already carries the move's opener; what the model needs
    is the SENTENCE-LEVEL MECHANIC ("grant the other side in five words, no full
    stop, then run straight into the mechanism") so a rewrite keeps the shape
    instead of politely deleting it and handing back the cold version.

    ``violations`` turns this into a REPAIR turn: it names the failures and
    nothing else, never restates the laws (they are in the system prompt) and
    never suggests a rewrite — the model has to fix its own copy, so a repair
    that drifts is caught by the same validators rather than smuggled through by
    a helpful instruction. Same discipline as ``copywriter._v2_user_message``.
    """
    spec = family_spec or {}
    intent = " / ".join(str(v) for v in (spec.get("move"), spec.get("trigger")) if v)
    allowed = allowed_numbers(draft, numbers_whitelist)
    who = f" by @{str(parent_author).lstrip('@')}" if parent_author else ""
    long_ok = str(family) in _long_form_families()
    warm_block = ""
    if warmth:
        does = str((warmth_spec or {}).get("does") or "")
        warm_block = (
            f"WARMTH MOVE: {warmth}"
            + (f": {does}\n" if does else "\n")
            + "The draft already opens in this move. Keep it fused to the fact: "
              "if you drop the move you have handed back the cold version, and "
              "if you give it its own sentence you have written the losing "
              "shape.\n"
        )
    out = (
        f"THE POST WE ARE REPLYING TO{who}:\n{str(parent_text or '').strip() or '(not available)'}\n\n"
        f"OUR DETERMINISTIC DRAFT (true, legal, and what ships unchanged if you do "
        f"not beat it):\n{str(draft or '').strip()}\n\n"
        f"REPLY FAMILY: {family}"
        + (f": {intent}\n" if intent else "\n")
        + warm_block
        + (
            "This family may run long: its structure IS the payload. Still one "
            "thought.\n" if long_ok else
            f"Length: {MAX_REPLY_CHARS} characters maximum, 11 to 25 words is the target.\n"
        )
        + f"\n{persona_card(account, cfg)}\n\n"
        "ALLOWED NUMBERS (every number in your reply must be one of these, written "
        "exactly as shown; using none of them is fine):\n"
        + ("\n".join(f"  {n}" for n in allowed) if allowed else "  (none; write no numbers)")
    )
    if violations:
        out += (
            "\n\nYOUR PREVIOUS REPLY WAS REJECTED. Fix exactly these and keep "
            "everything that was fine:\n"
            + "\n".join(f"- {_dashless(v)}" for v in list(violations)[:10])
        )
    return out


def allowed_numbers(draft: str, numbers_whitelist: Sequence[str] = ()) -> list[str]:
    """The ALLOWED NUMBERS list: the own-feed whitelist plus the draft's own.

    The deterministic draft is about to ship as-is, so every figure already in
    it is admissible by construction. Anything else has to have come from a
    fact the engine computed.
    """
    out: list[str] = []
    seen: set[str] = set()
    for token in list(numbers_whitelist or []) + _draft_numbers(draft):
        tok = str(token).strip()
        if tok and tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out[:32]


def _draft_numbers(draft: str) -> list[str]:
    """Number tokens already in the deterministic draft (SHARED tokenizer)."""
    try:
        from engine.marketing.reply_critics import number_tokens  # noqa: PLC0415

        return list(number_tokens(str(draft or "")))
    except Exception as exc:  # noqa: BLE001 — a tokenizer miss must not raise
        log.warning("reply_voice: number tokenizer unavailable (%s)", exc)
        return []


def _packet(draft: str, numbers_whitelist: Sequence[str]) -> dict:
    """The FactPacket handed to ``hot_tape_llm.numeric_violations``.

    Deliberately does NOT carry the parent post. A number in the parent is a
    number OUR engine did not compute — admitting it here would license copy
    that ``fact_discipline`` kills a moment later, which costs the whole item
    instead of costing one phrasing attempt.
    """
    return {
        "numbers_whitelist": [str(n) for n in (numbers_whitelist or [])],
        "draft_numbers": _draft_numbers(draft),
    }


# ─────────────────────────────────────────────────────────────────────────────
# The gates — every one imported from the module that already owns it
# ─────────────────────────────────────────────────────────────────────────────

def validate_reply_copy(
    text: str,
    *,
    draft: str,
    numbers_whitelist: Sequence[str] = (),
    parent_text: str = "",
    parent_author: str = "",
    account: str = "",
    family: str = "",
    warmth: str = "",
    relationship_only: bool = False,
    root: Path | str | None = None,
) -> list[str]:
    """Every gate a voiced reply must clear, ALL hits reported.

    (a) numbers trace to the own-feed whitelist   (hard; two imported checks)
    (b) house banned language + call language     (hard; imported)
    (c) the reply-value doctrine bar              (hard; imported critic)
    (c2) fabrication (AM-R1) + the warmth register (hard; imported critics)
    (d) length, links, hashtags, mentions, dashes (hard; doctrine §3/§6)
    (e) smuggled cashtags                         (hard)
    (f) the per-persona expression dial           (hard; imported)

    A non-empty return means the DETERMINISTIC draft ships instead. That is
    always the right swap: the template line is plain and true, and this runs
    before the critic pass, so a rejection here costs phrasing, never the item.
    """
    violations: list[str] = []
    body = str(text or "").strip()
    if not body:
        return ["empty model reply"]

    # (a) Numbers. The wire's tokenizer AND the reply desk's own gate, because
    # the second one is what will actually judge this text in `run_critics`.
    from engine.marketing.hot_tape_llm import numeric_violations  # noqa: PLC0415
    from engine.marketing import reply_critics as _rc  # noqa: PLC0415

    violations.extend(numeric_violations(body, _packet(draft, numbers_whitelist)))
    # THE GATE MUST JUDGE THE LIST THE PROMPT HANDED OUT. `allowed_numbers` is
    # what the model is shown (own-feed whitelist UNION the deterministic draft's
    # own figures — the draft is about to ship verbatim, so its numbers are
    # admissible by construction), and this gate used to be given the whitelist
    # alone. A model that obeyed the prompt and reused a figure from our own
    # draft was therefore rejected for it, every time, inflating the fallback
    # rate with compliance. A number in NEITHER set is still a violation.
    # (The union is built raw here, not via `allowed_numbers`, whose 32-entry
    # truncation is a PROMPT budget: a gate that inherited it would reject the
    # 33rd legitimate figure.)
    fact = _rc.fact_discipline(
        body,
        {"numbers_whitelist": [str(n) for n in (numbers_whitelist or [])]
                              + _draft_numbers(draft)},
    )
    violations.extend(f"fact_discipline: {r}" for r in fact.get("reasons") or [])

    # (b) House bans are IMPORTED — one list, every lane. `call_violations` is
    # the wire's gate 0.4 (entry/exit/sizing); `hedge_violations` deliberately
    # is NOT imported (see the module docstring).
    from engine.marketing.copywriter import banned_language  # noqa: PLC0415
    from engine.marketing.hot_tape_llm import call_violations  # noqa: PLC0415

    violations.extend(banned_language(body))
    violations.extend(call_violations(body))

    # (c) The doctrine bar, run against the SAME critic the producer will run.
    value = _rc.reply_value(body, {"parent_text": parent_text, "family": family})
    violations.extend(f"reply_value: {r}" for r in value.get("reasons") or [])

    # (c2) THE WARMTH LAWS, run here as well as downstream, and the ORDER is the
    # point. The model is the most likely originator of a plausible fabricated
    # circumstance ("back at my desk", "my third coffee") and of a cold rewrite
    # that quietly deletes the warmth move the deterministic draft carried.
    # Catching both HERE means the failure costs one phrasing attempt and the
    # WARM deterministic draft ships — a warmth law must never be a reason to
    # lose the fallback.
    warm_ctx = {"account": account, "root": root, "parent_author": parent_author,
                "warmth": warmth, "relationship_only": bool(relationship_only),
                "corpus": []}
    fab = _rc.fabrication(body, warm_ctx)
    violations.extend(f"fabrication: {r}" for r in fab.get("reasons") or [])
    warm = _rc.warmth_register(body, warm_ctx)
    violations.extend(f"warmth_register: {r}" for r in warm.get("reasons") or [])

    # (d) Shape.
    if len(body) > MAX_REPLY_CHARS:
        violations.append(f"over {MAX_REPLY_CHARS} chars ({len(body)})")
    if _URL_RE.search(body):
        violations.append("link in reply copy (doctrine §8: a plug wearing a reaction as a costume)")
    if _HASHTAG_RE.search(body):
        violations.append("hashtag_banned")
    if _MENTION_RE.search(body):
        violations.append("@-mention in reply copy (the reply is already addressed)")
    for dash in _DASH_TELLS:
        if dash in body:
            violations.append(f"dash tell {dash!r}")
            break

    # (e) A cashtag the engine computed nothing about is a smuggled comparison.
    # The parent's own ticker is legitimate — it is the thread we are in.
    allowed_tags = _cashtags(draft) | _cashtags(parent_text)
    for tag in sorted(_cashtags(body) - allowed_tags):
        violations.append(f"unknown_cashtag:'{tag}'")

    # (f) The per-persona register. A dial failure is a REJECTION, not a pass:
    # falling back to the deterministic draft is free, and shipping unchecked
    # persona copy is not.
    if account:
        try:
            from engine.marketing import expression_dial as _dial  # noqa: PLC0415

            violations.extend(_dial.violations(
                "", body, account=account, kind="reply", root=root,
                include_house_bans=False,
            ))
        except Exception as exc:  # noqa: BLE001
            violations.append(f"expression dial unavailable ({exc}) — cannot clear reply register")

    return violations


# ─────────────────────────────────────────────────────────────────────────────
# Config + provider plumbing (every import here is LAZY on purpose)
# ─────────────────────────────────────────────────────────────────────────────

def _root_config() -> dict:
    """config.yml as a dict, or {} — never raises. (Model ids live there.)"""
    try:
        from lib import config as _config  # noqa: PLC0415
        return _config.load() or {}
    except Exception:  # noqa: BLE001
        pass
    try:
        import yaml  # noqa: PLC0415

        path = Path(__file__).resolve().parents[2] / "config.yml"
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def _marketing_config(root: Path | str | None = None) -> dict:
    """config/marketing.yml as a dict, or {} — never raises."""
    try:
        import yaml  # noqa: PLC0415

        base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
        path = base / "config" / "marketing.yml"
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def _voice_cfg(cfg: dict | None, root: Path | str | None = None) -> dict:
    """Resolve the ``reply_desk.voice`` block.

    ``cfg`` may be the full marketing config (has ``reply_desk``), the
    ``reply_desk`` block (has ``voice``), or the ``voice`` block itself — the
    same tolerance ``hot_tape_llm._llm_cfg`` applies to its own block.
    """
    if isinstance(cfg, dict):
        block = cfg.get("reply_desk")
        if isinstance(block, dict):
            return block.get("voice") or {}
        if isinstance(cfg.get("voice"), dict):
            return cfg["voice"] or {}
        return cfg
    block = _marketing_config(root).get("reply_desk") or {}
    return (block.get("voice") if isinstance(block, dict) else {}) or {}


def _resolve_model_id(voice_cfg: dict) -> str:
    """``llm_models[<model_key>]``, else ``llm_models.marketing_copy``, else the literal."""
    models = _root_config().get("llm_models") or {}
    for key in (str(voice_cfg.get("model_key") or DEFAULT_MODEL_KEY), DEFAULT_MODEL_KEY):
        if models.get(key):
            return str(models[key])
    return DEFAULT_MODEL


def _int_cfg(cfg: dict, key: str, default: int) -> int:
    try:
        return int(cfg.get(key, default))
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
# The public entry point
# ─────────────────────────────────────────────────────────────────────────────

def voice_or_fallback(
    draft: str,
    *,
    family: str = "",
    account: str = "",
    parent_text: str = "",
    parent_author: str = "",
    numbers_whitelist: Sequence[str] = (),
    family_spec: dict | None = None,
    warmth: str | None = None,
    warmth_spec: dict | None = None,
    relationship_only: bool = False,
    cfg: dict | None = None,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Phrase one deterministic draft in reply voice, or hand it back. Never raises.

    Parameters
    ----------
    draft:
        The drafter's DETERMINISTIC ``compose()`` output. This is what ships
        whenever the model path does not clear every gate, which is why this
        module needs no import from ``reply_drafter`` at all.
    family / family_spec:
        The reply family id and (optionally) its ``FAMILIES`` entry, so the
        prompt can state the reasoning move the draft is making.
    account / parent_text / parent_author / numbers_whitelist:
        The persona to sound like, the post being answered, and the only
        figures the copy may contain.
    cfg:
        Optional config injection (full marketing config, ``reply_desk`` block,
        or ``voice`` block). Absent → config/marketing.yml.

    Returns
    -------
    dict with keys:
        ``text``        always postable: model copy, or ``draft``.
        ``mode``        ``"llm"`` | ``"fallback_validation"`` |
                        ``"fallback_provider"`` | ``"off"``.
        ``provider``    provider name that served, else None.
        ``violations``  the gate hits that forced a fallback (else []).
        ``latency_ms``  wall time of the whole attempt.
    """
    started = time.monotonic()
    _STATS["calls"] += 1
    fallback_text = str(draft or "")

    def _done(mode: str, text: str, *, provider: str | None = None,
              violations: list[str] | None = None) -> dict:
        _STATS[mode] = _STATS.get(mode, 0) + 1
        return {
            "text": text,
            "mode": mode,
            "provider": provider,
            "violations": list(violations or []),
            "latency_ms": int((time.monotonic() - started) * 1000),
        }

    voice_cfg = _voice_cfg(cfg, root)
    env_on = os.environ.get(_ENV_FLAG, "").strip().lower() in _TRUTHY
    if not fallback_text.strip():
        # An abstention upstream stays an abstention. Nothing to phrase.
        return _done("off", fallback_text)
    if not bool(voice_cfg.get("enabled", False)) or not env_on:
        # Disarmed: no provider is constructed, no credential is read, no call
        # is made. Same two-key arming as every other emitting LLM lane here.
        return _done("off", fallback_text)

    max_calls = _int_cfg(voice_cfg, "max_calls_per_run", DEFAULT_MAX_CALLS_PER_RUN)
    try:
        window_s = float(voice_cfg.get("call_window_s", DEFAULT_CALL_WINDOW_S))
    except (TypeError, ValueError):
        window_s = DEFAULT_CALL_WINDOW_S
    if not _take_call_slot(max_calls, window_s):
        _STATS["cap_hits"] += 1
        log.warning("reply_voice: runaway guard tripped (%d calls per %.0fs) — "
                    "account=%s falls back to the deterministic draft",
                    max_calls, window_s, account)
        return _done("fallback_provider", fallback_text)

    try:
        from engine import llm_auth  # noqa: PLC0415

        # CHATGPT-FIRST (operator directive 2026-07-29, recorded on
        # config/marketing.yml copywriter.llm): the attached Codex account leads,
        # Claude follows as the balanced fallback drawn through the key_pool load
        # balancer. Terra — a reply is a short conversational turn, wire register.
        provider_cfg = {
            "provider_order": voice_cfg.get("provider_order") or ["codex", "oauth", "anthropic", "deepseek"],
            "codex_source_model": voice_cfg.get("codex_source_model", "gpt-5.6-terra"),
            "codex_reasoning_effort": voice_cfg.get("codex_reasoning_effort", "medium"),
            "oauth_token_env": voice_cfg.get("oauth_token_env", "CLAUDE_CODE_OAUTH_TOKEN"),
            "deepseek_key_env": voice_cfg.get("deepseek_key_env", "DEEPSEEK_API_KEY"),
            "oauth_pool_lane": voice_cfg.get("oauth_pool_lane", "reply-voice"),
            "usage_lane": voice_cfg.get("usage_lane", "reply-voice"),
            "client_timeout_s": voice_cfg.get("client_timeout_s", DEFAULT_CLIENT_TIMEOUT_S),
            "client_max_retries": voice_cfg.get("client_max_retries", DEFAULT_CLIENT_MAX_RETRIES),
        }
        providers = llm_auth.build_providers(
            provider_cfg,
            opus_model=_resolve_model_id(voice_cfg),
            deepseek_model=str(voice_cfg.get("deepseek_model", DEFAULT_DEEPSEEK_MODEL)),
        )

        if not providers:
            # ARMED BUT MUTE — config says the reply voice is on and the env
            # flag agrees, yet no credential is visible, so every draft is
            # silently shipping the template. The nightly copywriter lane ran
            # in exactly this state for months (2026-07-26 incident).
            # A BARE print at line start: GitHub only parses `::` at column 0,
            # and every logger here prefixes the line, so an annotation routed
            # through log.warning is dropped silently
            # (tests/test_gh_annotation_line_start.py).
            print("::warning title=reply_voice_mute::Reply voice is ARMED "
                  "(reply_desk.voice.enabled + MARKETING_LLM_ENABLED) but no provider "
                  "credential is visible — every reply is falling back to the "
                  "deterministic draft. Pass CLAUDE_CODE_OAUTH_TOKEN* / "
                  "ANTHROPIC_API_KEY / DEEPSEEK_API_KEY to this step.", flush=True)
            log.warning("reply_voice: armed but no provider credential — "
                        "deterministic drafts only")
            return _done("fallback_provider", fallback_text)

        max_tokens = _int_cfg(voice_cfg, "max_tokens", DEFAULT_MAX_TOKENS)
        user_msg = build_user_message(
            draft=fallback_text, family=family, account=account,
            parent_text=parent_text, parent_author=parent_author,
            numbers_whitelist=numbers_whitelist, cfg=cfg, family_spec=family_spec,
            warmth=str(warmth or ""), warmth_spec=warmth_spec,
        )

        # §10 E3: SYSTEM_PROMPT plus whatever the config pins, which is nothing
        # until an operator edits intel.exemplar_store.active_version.
        _system = system_prompt(cfg, root)

        def _do_call(client, model):
            resp = client.messages.create(
                model=model, max_tokens=max_tokens, system=_system,
                messages=[{"role": "user", "content": user_msg}],
            )
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "stop_refusal", resp
            text = "".join(b.text for b in resp.content
                           if getattr(b, "type", "") == "text")
            return (text.strip() or None), None, resp

        # ONE call per draft: no batching, and no retry loop of our own — the
        # waterfall walk IS the retry (client_max_retries=0 above). The slot was
        # claimed above, before any credential was read.
        raw_text, reason, provider = llm_auth.make_call(
            providers, _do_call, context="reply_voice")
    except Exception as exc:  # noqa: BLE001 — a drafted reply must still exist
        log.warning("reply_voice: provider path failed for account=%s (%s: %s) — "
                    "deterministic draft ships", account, type(exc).__name__, exc)
        return _done("fallback_provider", fallback_text)

    if not raw_text:
        log.info("reply_voice: no model copy for account=%s (%s) — deterministic "
                 "draft ships", account, reason or "empty")
        return _done("fallback_provider", fallback_text)

    text = _tidy(raw_text)

    def _validate(candidate: str) -> list[str]:
        return validate_reply_copy(
            candidate, draft=fallback_text, numbers_whitelist=numbers_whitelist,
            parent_text=parent_text, parent_author=parent_author,
            account=account, family=family, warmth=str(warmth or ""),
            relationship_only=bool(relationship_only), root=root,
        )

    try:
        violations = _validate(text)
        if violations:
            # ONE REPAIR TURN, the same discipline the copywriter v2 path uses:
            # restate only the violations, never the laws, never a suggested
            # rewrite. The reply desk needs it MORE than the post lane does,
            # because a warmth move is exactly the kind of instruction a model
            # obeys at the cost of a different gate (it writes the fused
            # concession and slips in a hedge her codex bans), and without a
            # repair a single recoverable slip costs the whole phrasing pass.
            #
            # The repair claims its OWN slot from the runaway guard. A guard
            # that counts one call per draft while the code makes two is a cap
            # of 80/hour wearing a 40 label, which is the exact bug the rolling
            # window was introduced to fix.
            if _take_call_slot(max_calls, window_s):
                _STATS["repairs"] += 1
                repair_msg = build_user_message(
                    draft=fallback_text, family=family, account=account,
                    parent_text=parent_text, parent_author=parent_author,
                    numbers_whitelist=numbers_whitelist, cfg=cfg,
                    family_spec=family_spec, warmth=str(warmth or ""),
                    warmth_spec=warmth_spec, violations=violations,
                )

                def _do_repair(client, model):
                    resp = client.messages.create(
                        model=model, max_tokens=max_tokens, system=_system,
                        messages=[{"role": "user", "content": repair_msg}],
                    )
                    if getattr(resp, "stop_reason", None) == "refusal":
                        return None, "stop_refusal", resp
                    out = "".join(b.text for b in resp.content
                                  if getattr(b, "type", "") == "text")
                    return (out.strip() or None), None, resp

                try:
                    retry_text, _reason, retry_provider = llm_auth.make_call(
                        providers, _do_repair, context="reply_voice_repair")
                except Exception as exc:  # noqa: BLE001 — repair is best-effort
                    log.warning("reply_voice: repair turn failed for account=%s "
                                "(%s: %s)", account, type(exc).__name__, exc)
                    retry_text, retry_provider = None, None
                if retry_text:
                    candidate = _tidy(retry_text)
                    retry_violations = _validate(candidate)
                    if not retry_violations:
                        return _done("llm", candidate, provider=retry_provider or provider)
                    violations = retry_violations
            else:
                _STATS["cap_hits"] += 1
    except Exception as exc:  # noqa: BLE001 — "Never raises" is the contract
        # THE GATE IS NOT ALLOWED TO BE THE CRASH. `validate_reply_copy` does
        # four LAZY imports (hot_tape_llm, reply_critics, copywriter,
        # expression_dial) and any of them can ImportError in a thin runtime —
        # exactly the CI/minimal-deps lane this package is built to survive. That
        # exception used to escape a function documented "Never raises", which is
        # the guarantee §0 gate 1 of the reply doctrine rests on: the caller
        # treats a reply as always-postable. UNVALIDATED MODEL COPY NEVER SHIPS
        # here — the deterministic draft does, and the reason is recorded in the
        # same `violations` field the gate hits use, so the producer's
        # fallback-rate report shows it instead of hiding it.
        log.warning("reply_voice: validation unavailable for account=%s (%s: %s) — "
                    "deterministic draft ships", account, type(exc).__name__, exc)
        return _done("fallback_validation", fallback_text,
                     violations=[f"validation unavailable ({type(exc).__name__}: {exc})"])
    if violations:
        log.warning("reply_voice: model copy rejected for account=%s: %s",
                    account, "; ".join(violations[:6]))
        return _done("fallback_validation", fallback_text, violations=violations)

    return _done("llm", text, provider=provider)


__all__ = [
    "SYSTEM_PROMPT", "PLAYBOOK_EXEMPLARS", "ANTI_EXEMPLARS", "MAX_REPLY_CHARS",
    "system_prompt", "voice_or_fallback", "validate_reply_copy",
    "build_user_message", "persona_card", "allowed_numbers", "fallback_stats",
    "reset_stats",
]
