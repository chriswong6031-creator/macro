"""FOMC statement-diff desk — the fast lane that fires on the 14:00 ET statement.

WHAT IT PRODUCES, within minutes of the release:
  1. a FLAGSHIP house-view post — a tight hook in the body, and the 2-4 paragraph
     analysis rendered ONTO the diff card (engine/marketing/fomc_card.py)
  2. a mastermind_news STRAIGHT RELAY — decision, range, vote, no stance

WHY TWO POSTS AND NOT ONE. The wire account relays and never takes a stance
(charter §4 safety rails); the flagship exists to carry the house read. One event,
two registers, two audiences. They are enqueued as separate items so either can
fail without taking the other down, and so the outbox's own cross-account
near-duplicate guard sees them as what they are.

THE ANALYSIS IS LLM-REQUIRED; THE RELAY IS NOT. This mirrors the split the repo
already ratified (config/marketing.yml copywriter.llm.required, and the note there
that the WIRE lanes keep their deterministic fallback): wire register survives
templating and a house read does not. So when the waterfall is mute or its copy
cannot be validated, the relay still posts from a deterministic template built out
of the extracted facts, and the flagship analysis post is SKIPPED rather than
templated. Nothing about "the Fed changed its language" can be written by a
template without inventing the reading.

EVERY CLAIM TRACES TO THE FACT SHEET. The model is handed the decision facts, the
diff, and the statement text; :func:`validate_copy` then rejects any copy carrying
a number that does not appear in that corpus. That is what stops the failure mode
this lane is most exposed to: a confident post about interest rates containing a
market probability, a forecast or a level nobody gave it.

FAIL-SOFT AT EVERY SEAM. :func:`fire` never raises and never blocks the press
tick. One firing per meeting, remembered in the statements ledger.
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from engine.marketing import fomc_diff, fomc_statements

log = logging.getLogger(__name__)

# ── Arming ───────────────────────────────────────────────────────────────────
#: Two-key arming, exactly as the hot-tape and nightly copywriter lanes do it:
#: the config block must say enabled AND the environment must carry the flag. A
#: lane that is on in config but has no env flag constructs no provider and reads
#: no credential.
_ENV_FLAG = "MARKETING_LLM_ENABLED"
_TRUTHY = ("1", "true", "yes")

DEFAULT_MAX_TOKENS = 1200
DEFAULT_CLIENT_TIMEOUT_S = 45.0
#: Zero: the provider WATERFALL is the retry (llm_auth.make_call walks it), and an
#: SDK-level retry inside a rung only delays reaching the next one.
DEFAULT_CLIENT_MAX_RETRIES = 0
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_MODEL = "claude-sonnet-4-6"

#: Post character ceiling. X's limit is 280; the house copy law caps ordinary
#: posts at 275 and this lane holds the platform number because the hook and the
#: relay are both single-purpose lines with no cashtag budget to protect.
POST_MAX_CHARS = 280

#: The card holds 2-4 short paragraphs. These are the budgets that make "short"
#: checkable, and they are derived from what the 1080x1350 card actually draws
#: (see fomc_card's space accounting): three paragraphs of ~230 chars fit at the
#: 30px body size with the diff block below them.
ANALYSIS_MIN_PARAGRAPHS = 2
ANALYSIS_MAX_PARAGRAPHS = 4
ANALYSIS_PARA_MAX_CHARS = 260
ANALYSIS_TOTAL_MAX_CHARS = 900

#: Roles this desk emits. `analysis` is the flagship house view, `relay` the wire.
ROLE_ANALYSIS = "analysis"
ROLE_RELAY = "relay"

#: The class every item this desk emits carries. W3's wire_routing may declare it
#: (see resolve_accounts); until it does, this desk routes itself.
EVENT_CLASS = "fomc"

PROVENANCE = "fomc_desk"

#: Default desks. `flagship` owns the house read, `mastermind_news` the relay —
#: the split ratified on 2026-08-02 when the publication wire armed.
DEFAULT_ANALYSIS_ACCOUNT = "flagship"
DEFAULT_RELAY_ACCOUNT = "mastermind_news"


def _cfg(cfg: dict | None) -> dict:
    """The `fomc_desk` config block. {} when absent."""
    block = (cfg or {}).get("fomc_desk") if isinstance(cfg, dict) else None
    return block if isinstance(block, dict) else {}


def _llm_cfg(cfg: dict | None) -> dict:
    block = _cfg(cfg).get("llm")
    return block if isinstance(block, dict) else {}


def enabled(cfg: dict | None) -> bool:
    """Is the desk armed at all? (config only; the LLM has its own second key)"""
    value = _cfg(cfg).get("enabled", False)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUTHY


def _full_config() -> dict:
    """config.yml as a dict, or {} — never raises."""
    try:
        from lib import config as _config  # noqa: PLC0415
        return _config.load() or {}
    except Exception:  # noqa: BLE001
        return {}


def _resolve_model_id() -> str:
    """`llm_models.marketing_copy`, else the literal."""
    models = _full_config().get("llm_models") or {}
    if models.get("marketing_copy"):
        return str(models["marketing_copy"])
    return DEFAULT_MODEL


# ─────────────────────────────────────────────────────────────────────────────
# The fact sheet — the ONLY thing the model is allowed to know
# ─────────────────────────────────────────────────────────────────────────────

def build_fact_sheet(
    *,
    date_str: str,
    prior_date: str | None,
    current_paragraphs: list[str],
    prior_paragraphs: list[str],
    diff: dict,
    facts: dict,
    highlight_rows: list[dict] | None = None,
) -> dict:
    """Everything the writer gets, and the corpus its numbers are checked against.

    VERBATIM, NOT SUMMARISED. The changed phrases are the Fed's own words and the
    statement text is shipped whole, because the desk's product is a reading of
    what the Committee wrote — a paraphrased input would have the model reading
    our paraphrase.
    """
    highlight_rows = highlight_rows or []
    return {
        "meeting_date": date_str,
        "prior_meeting_date": prior_date,
        "decision": {
            "action": facts.get("action"),
            "target_range": facts.get("target_range"),
            "plain_line": fomc_diff.decision_line(facts),
            "vote": facts.get("vote"),
            "unanimous": facts.get("unanimous"),
            "dissenters": facts.get("dissenters"),
            "dissent_preference": facts.get("dissent_preference"),
            "dissent_size_percentage_points": facts.get("dissent_size"),
        },
        "diff_summary": {
            "sentences_now": diff.get("current_sentences"),
            "sentences_last_meeting": diff.get("prior_sentences"),
            "sentences_unchanged_verbatim": diff.get("unchanged_count"),
            "sentences_reworded": diff.get("changed_count"),
            "sentences_added": len(diff.get("added_sentences") or []),
            "sentences_removed": len(diff.get("removed_sentences") or []),
        },
        "changes_verbatim": [
            {
                "was": row.get("removed_text") or None,
                "now": row.get("added_text") or None,
                "kind": row.get("kind"),
            }
            for row in highlight_rows
        ],
        "sentences_added_verbatim": list(diff.get("added_sentences") or []),
        "sentences_removed_verbatim": list(diff.get("removed_sentences") or []),
        "statement_now": list(current_paragraphs or []),
        "statement_last_meeting": list(prior_paragraphs or []),
    }


def fact_sheet_text(sheet: dict) -> str:
    """The fact sheet as prompt text. Also the traceability corpus."""
    d = (sheet or {}).get("decision") or {}
    s = (sheet or {}).get("diff_summary") or {}
    lines: list[str] = [
        f"MEETING: {sheet.get('meeting_date')}",
        f"PREVIOUS MEETING: {sheet.get('prior_meeting_date')}",
        "",
        "DECISION FACTS (None means we could not prove it — never fill one in):",
        f"  action: {d.get('action')}",
        f"  target range: {d.get('target_range')}",
        f"  plain decision line: {d.get('plain_line')}",
        f"  vote: {d.get('vote')}",
        f"  unanimous: {d.get('unanimous')}",
        f"  dissenters: {d.get('dissenters')}",
        f"  dissenters preferred to: {d.get('dissent_preference')}",
        f"  dissent size (percentage points): "
        f"{d.get('dissent_size_percentage_points')}",
        "",
        "DIFF vs THE LAST STATEMENT:",
        f"  sentences in this statement: {s.get('sentences_now')}",
        f"  sentences in the last one: {s.get('sentences_last_meeting')}",
        f"  carried over VERBATIM: {s.get('sentences_unchanged_verbatim')}",
        f"  reworded: {s.get('sentences_reworded')}",
        f"  added: {s.get('sentences_added')}",
        f"  removed: {s.get('sentences_removed')}",
        "",
        "WHAT CHANGED, VERBATIM (was -> now):",
    ]
    for row in (sheet.get("changes_verbatim") or []):
        was, now = row.get("was"), row.get("now")
        if was and now:
            lines.append(f'  reworded: "{was}" -> "{now}"')
        elif now:
            lines.append(f'  added: "{now}"')
        elif was:
            lines.append(f'  removed: "{was}"')
    if not (sheet.get("changes_verbatim") or []):
        lines.append("  (nothing changed)")
    lines += ["", "THIS STATEMENT, IN FULL:"]
    lines += [f"  {p}" for p in (sheet.get("statement_now") or [])]
    lines += ["", "THE PREVIOUS STATEMENT, IN FULL:"]
    lines += [f"  {p}" for p in (sheet.get("statement_last_meeting") or [])]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────────

_SECTIONS = ("ANALYSIS", "HOOK", "RELAY")


def build_system_prompt() -> str:
    """The desk's standing instructions. Deterministic (no clock, no config)."""
    return (
        "You write for a markets desk on X the moment the FOMC statement lands. "
        "You are given the statement, the previous statement, and a machine diff "
        "of the two. Your job is to say what the Committee changed and what that "
        "change means, plainly.\n"
        "\n"
        "Produce EXACTLY three sections, each introduced by its bare label on its "
        "own line, in this order:\n"
        "\n"
        "ANALYSIS\n"
        f"{ANALYSIS_MIN_PARAGRAPHS} to {ANALYSIS_MAX_PARAGRAPHS} short paragraphs, "
        f"blank line between them, at most {ANALYSIS_PARA_MAX_CHARS} characters "
        "each. This is printed on a card, so it is read, not skimmed. Lead with "
        "what actually changed. Say what the change signals. Where the statement "
        "is unchanged, say so plainly, because a statement that did not move is "
        "itself the news.\n"
        "\n"
        "HOOK\n"
        f"One line, at most {POST_MAX_CHARS} characters. It is the post body that "
        "carries the card. It must make a reader want the card without repeating "
        "all of it.\n"
        "\n"
        "RELAY\n"
        f"One line, at most {POST_MAX_CHARS} characters, WIRE REGISTER: the "
        "decision, the target range and the vote, and nothing else. No stance, no "
        "reading, no first person, no adjectives of judgement. This one goes on a "
        "wire account that is not allowed to have an opinion.\n"
        "\n"
        "LAWS, all of them hard:\n"
        "- Every claim traces to the material you were given. If a number is not "
        "in it, you may not write that number. No forecasts, no probabilities, no "
        "market levels, no odds of a future move.\n"
        "- No advice. Never tell the reader what to do, buy, sell or position.\n"
        "- Deadpan. No hype, no hedging filler, no rhetorical questions.\n"
        "- No em dashes and no spaced en dashes anywhere. Use a period or a comma.\n"
        "- No hashtags. No exclamation marks. No emoji.\n"
        "- Numbers exactly as given to you.\n"
        "- A field given to you as None was not proven. Do not guess it and do not "
        "mention it.\n"
    )


def build_user_message(sheet: dict) -> str:
    """The user turn: the fact sheet, and the numbers the copy may use."""
    corpus = fact_sheet_text(sheet)
    allowed = sorted(_numbers_in(corpus), key=lambda s: (-len(s), s))
    return (
        f"{corpus}\n"
        "\n"
        "ALLOWED NUMBERS (every number you write must appear in this list, "
        "written exactly as shown):\n"
        + "\n".join(f"  {n}" for n in allowed)
    )


def build_repair_message(violations: list[str]) -> str:
    """The one repair turn: name the broken laws, ask for the whole thing again."""
    named = "\n".join(f"- {v}" for v in (violations or [])[:10])
    return (
        "That draft broke rules you were given:\n"
        f"{named}\n"
        "\n"
        "Rewrite all three sections from the same material, fixing exactly those "
        "problems and changing nothing else. Same labels, same order."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Parsing + validation
# ─────────────────────────────────────────────────────────────────────────────

_LABEL_RE = re.compile(r"^\s*(ANALYSIS|HOOK|RELAY)\s*:?\s*$", re.IGNORECASE)


def parse_sections(raw: str) -> dict:
    """Split the model reply into {analysis: [paras], hook: str, relay: str}.

    Tolerant of a stray colon or surrounding whitespace on the label lines and of
    a model that wraps a section in quotes; intolerant of a missing section, which
    surfaces as an empty value and therefore as a validation failure.
    """
    out: dict = {"analysis": [], "hook": "", "relay": ""}
    if not raw:
        return out
    current: str | None = None
    buckets: dict[str, list[str]] = {k: [] for k in _SECTIONS}
    for line in str(raw).splitlines():
        m = _LABEL_RE.match(line)
        if m:
            current = m.group(1).upper()
            continue
        if current:
            buckets[current].append(line)

    paragraphs: list[str] = []
    chunk: list[str] = []
    for line in buckets["ANALYSIS"]:
        if line.strip():
            chunk.append(line.strip())
        elif chunk:
            paragraphs.append(" ".join(chunk))
            chunk = []
    if chunk:
        paragraphs.append(" ".join(chunk))
    out["analysis"] = [_unquote(p) for p in paragraphs if p.strip()]
    out["hook"] = _unquote(" ".join(x.strip() for x in buckets["HOOK"] if x.strip()))
    out["relay"] = _unquote(" ".join(x.strip() for x in buckets["RELAY"] if x.strip()))
    return out


def _unquote(text: str) -> str:
    t = str(text or "").strip()
    if len(t) >= 2 and t[0] in "\"'“" and t[-1] in "\"'”":
        t = t[1:-1].strip()
    return t


#: Number tokens: 12, 9-3, 3-1/2, 1/4, 2.5, 2026. Deliberately greedy on the
#: inner punctuation so a compound rate figure stays one token.
_NUM_RE = re.compile(r"\d+(?:[./\-]\d+)*")

_DASHES = ("—", "–", "‒", "‑", "‐")


def _normalize_numbers(text: str) -> str:
    """Fold the Fed's typesetting so "9 – 3" and "9-3" are the same string."""
    out = str(text or "")
    for dash in _DASHES:
        out = out.replace(dash, "-")
    out = re.sub(r"\s*-\s*", "-", out)
    return re.sub(r"\s+", " ", out).lower()


def _numbers_in(text: str) -> set[str]:
    return set(_NUM_RE.findall(_normalize_numbers(text)))


def untraceable_numbers(text: str, corpus: str) -> list[str]:
    """Numbers in *text* that do not appear in *corpus*, in order of appearance.

    THE INVENTION THIS CATCHES. A model writing about a rate decision reaches for
    the market's reaction ("traders now price a 70% chance of a September cut") as
    naturally as it reaches for the statement, and none of that is in the
    statement. Checking every digit run against the material we supplied is a
    cheap, total guard: a number we did not give it cannot appear.

    Substring containment is deliberate, not laziness. "9-3" must match the
    statement's "9 - 3", and "3-1/2" must match inside "3-1/2 to 3-3/4 percent" —
    both fold to the same normalised form. It admits a false NEGATIVE (a "2" that
    happens to occur somewhere), which is the safe direction: the failure being
    guarded is a number with no source at all.
    """
    haystack = _normalize_numbers(corpus)
    bad: list[str] = []
    seen: set[str] = set()
    for token in _NUM_RE.findall(_normalize_numbers(text)):
        if token in seen:
            continue
        seen.add(token)
        if token not in haystack:
            bad.append(token)
    return bad


#: Advice and forecast constructions. Short and specific: the house copy laws
#: (copywriter.banned_language, applied separately) already carry the long list,
#: and these are the two families a rate-decision post reaches for that the house
#: list does not name.
_FORECAST_TELLS: tuple[str, ...] = (
    "we expect", "i expect", "will likely", "likely to cut", "likely to raise",
    "probability", "odds of", "priced in", "prices in", "our forecast",
    "we forecast", "next meeting will", "expect a cut", "expect a hike",
    "should cut", "should raise", "base case",
)
_ADVICE_TELLS: tuple[str, ...] = (
    "you should", "you need to", "buy ", "sell ", "position for",
    "size up", "size down", "take profit", "add here", "fade this",
)
#: The relay may not have a voice. First person and judgement are the two tells.
_STANCE_TELLS: tuple[str, ...] = (
    "i", "i'm", "i am", "we", "we're", "we are", "our", "my",
    "watch", "watching", "signal", "signals", "means", "suggests", "implies",
    "hawkish", "dovish", "surprise", "shock", "read as",
)


#: WORD BOUNDARIES, NOT SUBSTRINGS.
#:
#: The first version tested `tell in f" {text.lower()} "` with space-padded tells,
#: and "our " is a substring of "four " — so a relay containing the word "four"
#: was rejected as taking a first-person stance, which silently downgrades a
#: perfectly good model relay to the template. "we" inside "week", "my" inside
#: "myriad" and "i" inside anything are the same bug. Every tell here is matched
#: as a whole word or whole phrase.
def _tell_pattern(tell: str) -> re.Pattern:
    body = re.escape(tell.strip())
    left = r"\b" if tell.strip()[:1].isalnum() else ""
    right = r"\b" if tell.strip()[-1:].isalnum() else ""
    return re.compile(f"{left}{body}{right}", re.IGNORECASE)


_TELL_CACHE: dict[str, re.Pattern] = {}


def _hits(text: str, tells: tuple[str, ...]) -> list[str]:
    """Which of *tells* appear in *text* as whole words/phrases."""
    out: list[str] = []
    for tell in tells:
        pattern = _TELL_CACHE.get(tell)
        if pattern is None:
            pattern = _TELL_CACHE[tell] = _tell_pattern(tell)
        if pattern.search(str(text or "")):
            out.append(tell.strip())
    return out


def _banned_language(text: str) -> list[str]:
    """The house language screen. [] when the module is unavailable."""
    try:
        from engine.marketing.copywriter import banned_language  # noqa: PLC0415
        return list(banned_language(str(text or "")) or [])
    except Exception:  # noqa: BLE001 — the local laws below still apply
        return []


def _shared_violations(label: str, text: str, corpus: str) -> list[str]:
    """Laws every one of the three outputs must satisfy."""
    out: list[str] = []
    body = str(text or "")
    if not body.strip():
        return [f"{label}: missing"]
    if "#" in body:
        out.append(f"{label}: contains a hashtag")
    if "!" in body:
        out.append(f"{label}: contains an exclamation mark")
    for token in _banned_language(body):
        out.append(f"{label}: house language law: {token}")
    for tell in _hits(body, _FORECAST_TELLS):
        out.append(f"{label}: forecast language not in the statement: {tell}")
    for tell in _hits(body, _ADVICE_TELLS):
        out.append(f"{label}: advice language: {tell}")
    for number in untraceable_numbers(body, corpus):
        out.append(f"{label}: the number {number} is not in the material you were given")
    return out


def validate_copy(parsed: dict, sheet: dict) -> dict:
    """Per-output violations: {"analysis": [...], "hook": [...], "relay": [...]}.

    SEPARATE LISTS ON PURPOSE. The analysis is LLM-required and the relay is not,
    so a draft whose relay is clean and whose analysis invented a number should
    ship the relay and skip the flagship. One flat list would collapse that into
    "the draft failed" and lose the relay too.
    """
    corpus = fact_sheet_text(sheet)
    result: dict[str, list[str]] = {"analysis": [], "hook": [], "relay": []}

    paragraphs = [str(p).strip() for p in (parsed.get("analysis") or []) if str(p).strip()]
    if not paragraphs:
        result["analysis"].append("analysis: missing")
    else:
        if len(paragraphs) < ANALYSIS_MIN_PARAGRAPHS:
            result["analysis"].append(
                f"analysis: {len(paragraphs)} paragraph(s), the minimum is "
                f"{ANALYSIS_MIN_PARAGRAPHS}")
        if len(paragraphs) > ANALYSIS_MAX_PARAGRAPHS:
            result["analysis"].append(
                f"analysis: {len(paragraphs)} paragraphs, the maximum is "
                f"{ANALYSIS_MAX_PARAGRAPHS}")
        for i, para in enumerate(paragraphs, 1):
            if len(para) > ANALYSIS_PARA_MAX_CHARS:
                result["analysis"].append(
                    f"analysis: paragraph {i} is {len(para)} characters, the "
                    f"maximum is {ANALYSIS_PARA_MAX_CHARS}")
        total = sum(len(p) for p in paragraphs)
        if total > ANALYSIS_TOTAL_MAX_CHARS:
            result["analysis"].append(
                f"analysis: {total} characters in total, the maximum is "
                f"{ANALYSIS_TOTAL_MAX_CHARS}")
        result["analysis"] += _shared_violations("analysis", " ".join(paragraphs), corpus)

    hook = str(parsed.get("hook") or "").strip()
    if len(hook) > POST_MAX_CHARS:
        result["hook"].append(
            f"hook: {len(hook)} characters, the maximum is {POST_MAX_CHARS}")
    result["hook"] += _shared_violations("hook", hook, corpus)

    relay = str(parsed.get("relay") or "").strip()
    if len(relay) > POST_MAX_CHARS:
        result["relay"].append(
            f"relay: {len(relay)} characters, the maximum is {POST_MAX_CHARS}")
    result["relay"] += _shared_violations("relay", relay, corpus)
    if relay:
        for tell in _hits(relay, _STANCE_TELLS):
            result["relay"].append(
                f"relay: the wire account takes no stance, and this reads as "
                f"one: {tell}")
        facts = (sheet or {}).get("decision") or {}
        target = str(facts.get("target_range") or "")
        if target:
            head = _normalize_numbers(target).split(" to ")[0]
            if head and head not in _normalize_numbers(relay):
                result["relay"].append("relay: does not state the target range")
        vote = facts.get("vote")
        if isinstance(vote, dict) and vote.get("for") is not None:
            if str(vote.get("for")) not in _normalize_numbers(relay):
                result["relay"].append("relay: does not state the vote")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic relay — the wire lane's floor
# ─────────────────────────────────────────────────────────────────────────────

def deterministic_relay(facts: dict) -> str | None:
    """Wire-register relay built from the facts alone. None when unprovable.

    This is the reason a mute model cannot silence the desk entirely. It is also
    why it is only the RELAY: decision, range and vote are facts a template can
    state without adding anything, and "what the change signals" is not.
    """
    line = fomc_diff.decision_line(facts or {})
    if not line:
        return None
    parts = [f"{line}."]
    vote = (facts or {}).get("vote")
    if isinstance(vote, dict) and vote.get("for") is not None \
            and vote.get("against") is not None:
        parts.append(f"Vote {vote['for']}-{vote['against']}.")
    dissenters = (facts or {}).get("dissenters")
    if isinstance(dissenters, list) and dissenters:
        surnames = [str(n).split()[-1] for n in dissenters if str(n).strip()]
        if surnames:
            who = (", ".join(surnames[:-1]) + f" and {surnames[-1]}"
                   if len(surnames) > 1 else surnames[0])
            pref = str((facts or {}).get("dissent_preference") or "").strip()
            size = str((facts or {}).get("dissent_size") or "").strip()
            if pref and size:
                parts.append(f"{who} preferred to {pref} by {size} point.")
            elif pref:
                parts.append(f"{who} preferred to {pref}.")
            else:
                parts.append(f"{who} dissented.")

    # FIT BY DROPPING WHOLE SENTENCES, NEVER BY CUTTING ONE.
    #
    # `parts` is ordered by how load-bearing it is: the decision, then the vote,
    # then who dissented. A character-slice at 280 would end a wire post
    # mid-surname on the one meeting with four dissenters and long names, so the
    # last sentence is dropped instead. A shorter true relay beats a truncated
    # one, and the decision sentence alone is already a complete wire item.
    while parts and len(" ".join(parts)) > POST_MAX_CHARS:
        parts.pop()
    return " ".join(parts) or None


# ─────────────────────────────────────────────────────────────────────────────
# The writer
# ─────────────────────────────────────────────────────────────────────────────

def write_copy(sheet: dict, *, cfg: dict | None = None) -> dict:
    """Call the marketing waterfall for the analysis, the hook and the relay.

    ONE CALL for all three, plus at most ONE repair turn. They are written
    together because they are three registers of the same reading and a separate
    call per output produces three drafts that disagree about what happened.

    Returns:
        {analysis: [paras], hook: str, relay: str, mode: str, provider: str|None,
         violations: {analysis: [...], hook: [...], relay: [...]},
         latency_ms: int}

    `mode` is one of:
        llm            — first draft validated clean
        llm_repair     — the repair turn validated clean
        partial        — some outputs clean, some not (read `violations`)
        off            — the desk's LLM is disarmed (config or env)
        fallback_provider   — armed, but no provider produced text
        fallback_validation — text produced, still invalid after the repair turn

    Never raises.
    """
    started = time.monotonic()
    empty: dict = {"analysis": [], "hook": "", "relay": ""}

    def _done(mode: str, parsed: dict, *, provider: str | None = None,
              violations: dict | None = None) -> dict:
        out = dict(parsed or empty)
        out["mode"] = mode
        out["provider"] = provider
        out["violations"] = violations or {"analysis": [], "hook": [], "relay": []}
        out["latency_ms"] = int((time.monotonic() - started) * 1000)
        return out

    llm_cfg = _llm_cfg(cfg)
    env_on = os.environ.get(_ENV_FLAG, "").strip().lower() in _TRUTHY
    if not bool(llm_cfg.get("enabled", False)) or not env_on:
        return _done("off", empty)

    try:
        from engine import llm_auth  # noqa: PLC0415

        provider_cfg = {
            "provider_order": llm_cfg.get("provider_order")
            or ["codex", "oauth", "anthropic", "deepseek"],
            "codex_source_model": llm_cfg.get("codex_source_model", "gpt-5.6-sol"),
            "codex_reasoning_effort": llm_cfg.get("codex_reasoning_effort", "medium"),
            "oauth_token_env": llm_cfg.get("oauth_token_env", "CLAUDE_CODE_OAUTH_TOKEN"),
            "deepseek_key_env": llm_cfg.get("deepseek_key_env", "DEEPSEEK_API_KEY"),
            "oauth_pool_lane": llm_cfg.get("oauth_pool_lane", "marketing-fomc"),
            "usage_lane": llm_cfg.get("usage_lane", "marketing-fomc"),
            "client_timeout_s": llm_cfg.get("client_timeout_s", DEFAULT_CLIENT_TIMEOUT_S),
            "client_max_retries": llm_cfg.get("client_max_retries",
                                              DEFAULT_CLIENT_MAX_RETRIES),
        }
        providers = llm_auth.build_providers(
            provider_cfg,
            opus_model=_resolve_model_id(),
            deepseek_model=str(llm_cfg.get("deepseek_model", DEFAULT_DEEPSEEK_MODEL)),
        )
        if not providers:
            # ARMED BUT MUTE. The config says the desk is on and the env agrees,
            # yet no credential is visible — so the flagship analysis post will be
            # skipped on a live FOMC day and only the template relay will ship.
            # A bare print at line start: GitHub parses `::` only at column 0 and
            # every logger here prefixes the line.
            print("::warning title=fomc_desk_mute::The FOMC desk is ARMED "
                  "(fomc_desk.llm.enabled + MARKETING_LLM_ENABLED) but no provider "
                  "credential is visible. The flagship analysis post will be "
                  "SKIPPED and only the deterministic relay will ship. Pass "
                  "CLAUDE_CODE_OAUTH_TOKEN* / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY "
                  "to this step.", flush=True)
            return _done("fallback_provider", empty)

        try:
            max_tokens = int(llm_cfg.get("max_tokens", DEFAULT_MAX_TOKENS))
        except (TypeError, ValueError):
            max_tokens = DEFAULT_MAX_TOKENS
        system_prompt = build_system_prompt()
        user_msg = build_user_message(sheet)

        def _caller(messages: list[dict]):
            def _do_call(client, model):
                resp = client.messages.create(
                    model=model, max_tokens=max_tokens, system=system_prompt,
                    messages=messages,
                )
                if getattr(resp, "stop_reason", None) == "refusal":
                    return None, "stop_refusal", resp
                text = "".join(b.text for b in resp.content
                               if getattr(b, "type", "") == "text")
                return (text.strip() or None), None, resp
            return _do_call

        raw, reason, provider = llm_auth.make_call(
            providers, _caller([{"role": "user", "content": user_msg}]),
            context="fomc_desk")
    except Exception as exc:  # noqa: BLE001 — the relay must still ship
        log.warning("fomc_desk: provider path failed (%s: %s)",
                    type(exc).__name__, exc)
        return _done("fallback_provider", empty)

    if not raw:
        log.info("fomc_desk: no model copy (%s)", reason or "empty")
        return _done("fallback_provider", empty)

    parsed = parse_sections(raw)
    violations = validate_copy(parsed, sheet)
    if not any(violations.values()):
        return _done("llm", parsed, provider=provider, violations=violations)

    # ── ONE REPAIR TURN ──────────────────────────────────────────────────────
    # Strictly one. A model that fails the same NAMED law twice will not find it
    # on the third pass, and this lane runs against a clock: the post is worth
    # something within minutes of 14:00 ET and worth much less at 14:30.
    flat = [v for group in violations.values() for v in group]
    log.warning("fomc_desk: draft rejected: %s", "; ".join(flat[:8]))
    try:
        r_raw, _r_reason, r_provider = llm_auth.make_call(
            providers,
            _caller([
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": build_repair_message(flat)},
            ]),
            context="fomc_desk_repair")
    except Exception as exc:  # noqa: BLE001
        log.warning("fomc_desk: repair turn failed (%s: %s)", type(exc).__name__, exc)
        r_raw, r_provider = None, None

    if r_raw:
        r_parsed = parse_sections(r_raw)
        r_violations = validate_copy(r_parsed, sheet)
        if not any(r_violations.values()):
            return _done("llm_repair", r_parsed, provider=r_provider,
                         violations=r_violations)
        # PARTIAL IS A REAL OUTCOME, not a failure. If the repair's relay is
        # clean, that relay ships even though the analysis is not usable; the
        # caller reads `violations` per output and decides per post.
        if not all(r_violations.values()):
            return _done("partial", r_parsed, provider=r_provider,
                         violations=r_violations)
        log.warning("fomc_desk: repair still rejected: %s",
                    "; ".join(v for g in r_violations.values() for v in g)[:400])
        return _done("fallback_validation", r_parsed, provider=r_provider,
                     violations=r_violations)

    if not all(violations.values()):
        return _done("partial", parsed, provider=provider, violations=violations)
    return _done("fallback_validation", parsed, provider=provider,
                 violations=violations)


# ─────────────────────────────────────────────────────────────────────────────
# Routing — tolerant of a world where W3's wire_routing knows `fomc` and one where
# it does not
# ─────────────────────────────────────────────────────────────────────────────

def _declared_classes(cfg: dict | None) -> set[str]:
    """Keys declared under `wire_routing.classes`. Read-only, never written."""
    block = (cfg or {}).get("wire_routing") if isinstance(cfg, dict) else None
    classes = (block or {}).get("classes") if isinstance(block, dict) else None
    return {str(k) for k in classes} if isinstance(classes, dict) else set()


def resolve_accounts(cfg: dict | None, *, root: Path | str | None = None) -> dict:
    """{"analysis": account, "relay": account}.

    THE SIBLING-LANE CONTRACT. A parallel PR (W3) owns wire_routing.py and adds an
    `fomc` class to it. This desk must work whether that has landed or not, and it
    may not edit that module, so it ASKS rather than assumes:

      • relay: wire_routing already exists to answer "which desk owns a wire
        emission of this class", which is exactly what the relay is. If `fomc`
        (or `fomc.relay`) is declared, its answer wins.
      • analysis: routing maps one class to one desk and has no vocabulary for
        "the same event also gets a house read". So the analysis follows
        `fomc.analysis` when W3 declares that refinement, and otherwise this
        desk's own configured default.

    `route()` is only ever called for a class routing has been SEEN to declare, so
    the unknown-class park/redirect path is never entered by accident.

    If both roles resolve to the SAME account the relay is dropped by the caller:
    one desk does not post the same fact twice in two registers.
    """
    block = _cfg(cfg)
    accounts = block.get("accounts") if isinstance(block.get("accounts"), dict) else {}
    analysis = str(accounts.get("analysis") or DEFAULT_ANALYSIS_ACCOUNT)
    relay = str(accounts.get("relay") or DEFAULT_RELAY_ACCOUNT)

    declared = _declared_classes(cfg)
    if not declared:
        return {"analysis": analysis, "relay": relay, "source": "config"}

    try:
        from engine.marketing.wire_routing import route  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — a missing router is the config world
        return {"analysis": analysis, "relay": relay, "source": "config"}

    source = "config"
    if f"{EVENT_CLASS}.analysis" in declared:
        try:
            analysis = str(route(EVENT_CLASS, cfg=cfg, root=root,
                                 refinement="analysis") or analysis)
            source = "wire_routing"
        except Exception as exc:  # noqa: BLE001
            log.warning("fomc_desk: analysis routing lookup failed: %s", exc)
    if f"{EVENT_CLASS}.relay" in declared or EVENT_CLASS in declared:
        refinement = "relay" if f"{EVENT_CLASS}.relay" in declared else ""
        try:
            relay = str(route(EVENT_CLASS, cfg=cfg, root=root,
                              refinement=refinement) or relay)
            source = "wire_routing"
        except Exception as exc:  # noqa: BLE001
            log.warning("fomc_desk: relay routing lookup failed: %s", exc)
    return {"analysis": analysis, "relay": relay, "source": source}


# ─────────────────────────────────────────────────────────────────────────────
# Emission
# ─────────────────────────────────────────────────────────────────────────────

def _card_media(
    svg: str, *, item_id: str, as_of: str, root: Path, dry_run: bool
) -> list[dict]:
    """Write the card, raster it, publish the PNG. Returns the media[] list.

    Mirrors press_lane._host_card_media exactly, through the SAME
    media_publish.publish_card seam, so the posted PNG is a raster of the same
    SVG the admin preview shows. A card that cannot be hosted still leaves its
    local pointer for scripts/marketing_media_backfill.py to upload later.
    """
    rel_svg = f"data/marketing/outbox/media/{as_of}/{item_id}.svg"
    entry: dict = {"kind": "chart_svg", "path": rel_svg, "chart_id": item_id}
    if not svg or dry_run:
        return [entry]
    try:
        from engine.marketing.media_publish import publish_card  # noqa: PLC0415
        published = publish_card(svg, chart_id=item_id, as_of=as_of, root=root) or {}
    except Exception as exc:  # noqa: BLE001 — a picture may degrade, never block
        print(f"::warning title=fomc-card-publish-failed::{item_id}: "
              f"{type(exc).__name__}: {exc}", flush=True)
        return [entry]
    if published.get("svg_path"):
        entry["path"] = published["svg_path"]
    if published.get("media_png_path"):
        entry["media_png_path"] = published["media_png_path"]
    if published.get("media_render"):
        entry["media_render"] = published["media_render"]
    url = str(published.get("media_url") or "").strip()
    if url.lower().startswith(("http://", "https://")):
        entry["media_url"] = url
    else:
        print("::warning title=fomc-card-unhosted::"
              f"{item_id}: the diff card has no public URL, so the analysis post "
              "would ship without the card that carries its analysis", flush=True)
    return [entry]


def emit_item(
    *,
    role: str,
    account: str,
    text: str,
    as_of: str,
    date_str: str,
    source_url: str,
    root: Path,
    cfg: dict | None,
    now: datetime,
    media: list[dict] | None = None,
    dry_run: bool = False,
    priority: int = 1,
) -> dict | None:
    """Build, screen and enqueue ONE outbox item. None when refused.

    Goes through the canonical path — make_item -> validate_item -> the house
    language screen -> enqueue — so this lane inherits id-dedup, text-dedup,
    cross-account near-dup and the cadence resolver rather than reimplementing
    any of them.

    NO EXPLICIT DAILY CAP IS PASSED, AND THAT IS A DECISION. `outbox.enqueue`
    enforces `effective_cap(cfg)` at the queue seam (the publisher's immediate-rail
    exemption is applied LATER, at auto-approve, and cannot rescue an item the
    queue already refused). config/marketing.yml currently sets
    `sentinel.max_posts_per_account_per_day: -1`, i.e. unlimited, so an FOMC post
    cannot be refused for volume today. This lane deliberately does NOT pass its
    own override: the Sentinel cap is the operator's instrument and a desk that
    silently exempts itself from it is how a ceiling stops meaning anything. The
    coupling is real, though — if that cap is ever given a finite value, this
    desk inherits it and a quarterly post could be refused as `cap_exceeded` on a
    busy day. The refusal is announced (`::warning fomc-not-queued`) rather than
    silent, which is the part that matters for catching it.
    """
    from engine.marketing import outbox as _ob  # noqa: PLC0415

    body = str(text or "").strip()
    if not body:
        return None

    source = {
        "kind": "fomc_statement",
        "url": source_url,
        "meeting_date": date_str,
        "role": role,
        "desk": PROVENANCE,
    }
    try:
        item = _ob.make_item(
            account=account,
            kind="breaking",
            text=body,
            as_of=as_of,
            media=media if media is not None else [],
            scheduled_at="immediate",
            priority=priority,
            provenance=PROVENANCE,
            source=source,
            now=now,
        )
    except ValueError as exc:
        print(f"::warning title=fomc-item-invalid::{date_str}/{role}: {exc}",
              flush=True)
        return None

    # Additive fields the schema has no slot for. `immediate` is the legacy
    # share-now marker the publisher reads; `event_class` is what W3's fan-out
    # keys on; the two fomc_* keys let the admin and the ledger name the firing.
    item["immediate"] = True
    item["event_class"] = EVENT_CLASS
    item["fomc_role"] = role
    item["fomc_date"] = date_str

    errors = _ob.validate_item(item)
    if errors:
        print(f"::warning title=fomc-item-invalid::{date_str}/{role}: {errors[0]}",
              flush=True)
        return None

    violations = _banned_language(body)
    if violations:
        print("::warning title=fomc-banned-language::"
              f"{date_str}/{role}: refused by the house language law: "
              f"{', '.join(violations[:4])}", flush=True)
        return None

    if dry_run:
        return item

    result = _ob.enqueue(item, root, cfg=cfg)
    if result != "queued":
        print(f"::warning title=fomc-not-queued::{date_str}/{role} refused by the "
              f"outbox: {result}", flush=True)
        return None
    return item


# ─────────────────────────────────────────────────────────────────────────────
# The firing
# ─────────────────────────────────────────────────────────────────────────────

def _dissent_sentence_row(row: dict, dissent: str | None) -> bool:
    """Is this highlight row the dissent sentence the vote chip already states?"""
    if not dissent:
        return False
    text = str(row.get("added_text") or row.get("removed_text") or "").strip()
    return bool(text) and text == dissent.strip()


def card_highlights(diff: dict, facts: dict, current_paragraphs: list[str],
                    *, limit: int = 6) -> list[dict]:
    """Highlight rows for the CARD, with the on-chip duplication removed.

    The card already prints the dissent in plain words beside the vote chip
    ("Hammack, Kashkari, Logan wanted to raise by 1/4 point"). Drawing the Fed's
    own dissent sentence underneath it says the same thing twice, in worse
    English, and on the first render probe it also ran past three lines and
    clipped mid-word. So when the dissent is on the chip, its verbatim sentence is
    dropped from the highlights and the lines it would have taken go to the
    changes that are not stated anywhere else on the card.
    """
    rows = fomc_diff.highlights(diff, limit=limit + 2)
    if (facts or {}).get("dissenters"):
        dissent = fomc_diff.dissent_sentence(current_paragraphs or [])
        rows = [r for r in rows if not _dissent_sentence_row(r, dissent)]
    return rows[:limit]


def fire(
    *,
    date_str: str,
    root: Path | str | None = None,
    cfg: dict | None = None,
    now: datetime | None = None,
    url: str | None = None,
    html_text: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Collect, diff, write, render and enqueue for one meeting. Never raises.

    Returns a report dict: {fired, reason, date, mode, accounts, emitted,
    diff, facts, fit, violations}. `fired` False with a `reason` is the normal
    no-op answer (already done, not a decision day, statement unreadable).
    """
    started = time.monotonic()
    repo_root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    ts = now or datetime.now(timezone.utc)
    report: dict = {
        "fired": False, "reason": "", "date": date_str, "mode": "",
        "accounts": {}, "emitted": [], "violations": {},
    }

    try:
        if not enabled(cfg):
            report["reason"] = "disabled"
            return report
        if fomc_statements.is_collected(date_str, repo_root):
            # ONE FIRING PER MEETING. The ledger row is written at the END of a
            # firing, so this is "we already finished", not "we already fetched".
            report["reason"] = "already_fired"
            return report

        collected = fomc_statements.collect(
            date_str, url=url, root=repo_root, now=ts, html_text=html_text)
        if not collected:
            report["reason"] = "statement_unreadable"
            return report

        current = collected["paragraphs"]
        prior_date = fomc_statements.prior_decision_date(date_str, root=repo_root)
        prior = fomc_statements.read_statement(prior_date, repo_root) if prior_date else []
        if not prior:
            # No baseline means no diff, and a diff desk with no diff has no
            # product. The statement is stored either way, so the NEXT meeting
            # has its baseline — the desk seeds itself.
            print("::warning title=fomc-no-baseline::"
                  f"{date_str}: no stored prior statement "
                  f"({prior_date or 'no prior date known'}) — the statement is "
                  "stored as the next meeting's baseline and nothing is posted",
                  flush=True)
            report["reason"] = "no_prior_statement"
            fomc_statements.record_collection(
                collected, root=repo_root,
                extra={"emitted": [], "mode": "no_prior_statement"})
            return report

        diff = fomc_diff.diff_statements(prior, current)
        facts = fomc_diff.extract_facts(current)
        highlight_rows = card_highlights(diff, facts, current, limit=6)
        sheet = build_fact_sheet(
            date_str=date_str, prior_date=prior_date,
            current_paragraphs=current, prior_paragraphs=prior,
            diff=diff, facts=facts, highlight_rows=highlight_rows,
        )
        report["diff"] = {
            "unchanged_count": diff["unchanged_count"],
            "changed_count": diff["changed_count"],
            "added": len(diff["added_sentences"]),
            "removed": len(diff["removed_sentences"]),
        }
        report["facts"] = facts

        written = write_copy(sheet, cfg=cfg)
        report["mode"] = written["mode"]
        report["violations"] = written.get("violations") or {}
        report["provider"] = written.get("provider")

        accounts = resolve_accounts(cfg, root=repo_root)
        report["accounts"] = accounts
        as_of = ts.astimezone(timezone.utc).strftime("%Y-%m-%d")
        source_url = str(collected.get("url") or "")

        emitted: list[dict] = []
        violations = written.get("violations") or {}

        # ── The FLAGSHIP analysis post (LLM-required) ────────────────────────
        analysis_ok = (
            bool(written.get("analysis")) and bool(str(written.get("hook") or "").strip())
            and not violations.get("analysis") and not violations.get("hook")
        )
        if analysis_ok:
            from engine.marketing.fomc_card import render_fomc_card  # noqa: PLC0415

            fit: dict = {}
            svg = render_fomc_card(
                date_str=date_str,
                decision_line=fomc_diff.decision_line(facts),
                analysis_paragraphs=list(written["analysis"]),
                highlights=highlight_rows,
                facts=facts,
                unchanged_count=diff["unchanged_count"],
                prior_date=prior_date,
                fit=fit,
            )
            report["fit"] = fit
            supplied = int(fit.get("paragraphs_supplied") or 0)
            drawn = int(fit.get("paragraphs_drawn") or 0)
            if supplied and drawn < supplied:
                # The analysis IS the product on this post. A dropped paragraph is
                # a silent content loss, so it is announced rather than absorbed.
                print("::warning title=fomc-card-analysis-truncated::"
                      f"{date_str}: the card drew {drawn} of {supplied} analysis "
                      "paragraphs; the rest did not fit", flush=True)
            item_id = f"fomc-{date_str}"
            media = _card_media(svg, item_id=item_id, as_of=as_of,
                                root=repo_root, dry_run=dry_run)
            item = emit_item(
                role=ROLE_ANALYSIS, account=accounts["analysis"],
                text=str(written["hook"]).strip(), as_of=as_of, date_str=date_str,
                source_url=source_url, root=repo_root, cfg=cfg, now=ts,
                media=media, dry_run=dry_run, priority=1,
            )
            if item:
                emitted.append(item)
        else:
            # PLANNED-KIND SEMANTICS: no model copy, no house read. Counted and
            # named, never templated.
            _why = f"writer mode={written['mode']}"
            _bad = list(violations.get("analysis") or []) + \
                list(violations.get("hook") or [])
            if _bad:
                _why += f", {len(_bad)} violations: {'; '.join(_bad[:3])}"
            print("::warning title=fomc-analysis-skipped::"
                  f"{date_str}: the flagship analysis post is SKIPPED ({_why}). "
                  "The relay still ships.", flush=True)

        # ── The WIRE relay (deterministic floor) ─────────────────────────────
        relay_text = str(written.get("relay") or "").strip()
        relay_mode = "llm"
        if not relay_text or violations.get("relay"):
            relay_text = deterministic_relay(facts) or ""
            relay_mode = "template"
        if not relay_text:
            print("::warning title=fomc-relay-unprovable::"
                  f"{date_str}: no model relay and the decision facts are not "
                  "complete enough for the template, so no relay ships", flush=True)
        elif accounts["relay"] == accounts["analysis"] and analysis_ok:
            # One desk, one post about one fact. The analysis is the richer of
            # the two, so it keeps the slot.
            print("::notice title=fomc-relay-collapsed::"
                  f"{date_str}: the relay and the analysis resolved to the same "
                  f"desk ({accounts['relay']}), so only the analysis ships",
                  flush=True)
        else:
            item = emit_item(
                role=ROLE_RELAY, account=accounts["relay"], text=relay_text,
                as_of=as_of, date_str=date_str, source_url=source_url,
                root=repo_root, cfg=cfg, now=ts, media=[], dry_run=dry_run,
                priority=2,
            )
            if item:
                item["fomc_relay_mode"] = relay_mode
                emitted.append(item)

        report["emitted"] = emitted
        report["fired"] = True
        report["reason"] = "fired"
        report["latency_ms"] = int((time.monotonic() - started) * 1000)

        # THE LEDGER ROW MARKS THE FIRING DONE EVEN IF NOTHING ENQUEUED, and that
        # is deliberate. A firing that reached this line ran the whole pipeline:
        # the statement is stored, the diff is computed, the model was called. If
        # both enqueues were refused (a duplicate, a cap, a language screen) the
        # refusal was ANNOUNCED and is almost always permanent, so retrying would
        # spend one LLM call every five minutes for the rest of the day to be
        # refused the same way each time. Retries belong to the paths that never
        # got this far — a failed fetch and an unreadable page both return above
        # WITHOUT a row, and the next 5-minute tick picks them up.
        if not dry_run:
            fomc_statements.record_collection(
                collected, root=repo_root,
                extra={
                    "emitted": [str(i.get("id")) for i in emitted],
                    "mode": written["mode"],
                    "relay_mode": relay_mode if relay_text else "none",
                    "accounts": [str(i.get("account")) for i in emitted],
                },
            )
        print(f"[fomc] fired {date_str} | mode={written['mode']} | "
              f"emitted={len(emitted)} | changed={diff['changed_count']} "
              f"added={len(diff['added_sentences'])} "
              f"unchanged={diff['unchanged_count']}", flush=True)
        return report
    except Exception as exc:  # noqa: BLE001 — a desk may fail, the wire may not
        log.warning("fomc_desk.fire failed for %s (%s: %s)",
                    date_str, type(exc).__name__, exc)
        print(f"::warning title=fomc-desk-failed::{date_str}: "
              f"{type(exc).__name__}: {exc}", flush=True)
        report["reason"] = f"error:{type(exc).__name__}"
        return report


# ─────────────────────────────────────────────────────────────────────────────
# The press-wire trigger
# ─────────────────────────────────────────────────────────────────────────────

#: A Fed press item is THE STATEMENT when its title says so. The Fed's own title
#: for it has been "Federal Reserve issues FOMC statement" for over a decade, and
#: the release-letter URL (`monetaryYYYYMMDDa.htm`) is the second, independent
#: tell. Either is enough; both are checked because the desk must not miss the
#: one event it exists for, and the decision-day gate below means a false match on
#: a non-FOMC day costs nothing.
_TITLE_RE = re.compile(r"\bFOMC\s+statement\b", re.IGNORECASE)
_URL_RE = re.compile(r"/monetary(\d{8})[a-z]?\.htm", re.IGNORECASE)


def is_statement_release(item: dict, *, source_keys: tuple[str, ...] = ("fed_press",)) -> bool:
    """Is this feed item the FOMC statement press release?"""
    if not isinstance(item, dict):
        return False
    source = str(item.get("source") or item.get("source_key") or "").strip().lower()
    if source_keys and source not in {s.lower() for s in source_keys}:
        return False
    headline = str(item.get("headline") or item.get("title") or "")
    if _TITLE_RE.search(headline):
        return True
    return bool(_URL_RE.search(str(item.get("url") or "")))


def meeting_date_for(item: dict, *, now: datetime | None = None) -> str | None:
    """The decision date this item belongs to, or None.

    Read from the release-letter URL when it carries one (`monetary20260916a.htm`
    names its own date, which is the authoritative answer and survives a tick that
    runs just after midnight UTC — 14:00 ET is 18:00 or 19:00 UTC, so the ET
    decision day and the UTC day agree, but the URL removes the question). Falls
    back to the tick's own ET date.
    """
    m = _URL_RE.search(str((item or {}).get("url") or ""))
    if m:
        raw = m.group(1)
        candidate = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
        if fomc_statements.is_decision_day(candidate):
            return candidate
    ts = now or datetime.now(timezone.utc)
    for date_str in _et_candidate_dates(ts):
        if fomc_statements.is_decision_day(date_str):
            return date_str
    return None


def _et_candidate_dates(ts: datetime) -> list[str]:
    """The UTC date and the ET date of *ts*, in that order, de-duplicated.

    ET is UTC-4 or UTC-5, so a 14:00 ET release lands at 18:00/19:00 UTC on the
    SAME calendar day. The only disagreement is a tick between 00:00 and 05:00
    UTC, which is the previous ET day — and a tick at 00:30 UTC on the day after a
    decision is exactly the retry a crashed firing needs, so both are candidates.
    """
    utc = ts.astimezone(timezone.utc)
    out = [utc.strftime("%Y-%m-%d")]
    from datetime import timedelta  # noqa: PLC0415
    et_guess = (utc - timedelta(hours=5)).strftime("%Y-%m-%d")
    if et_guess not in out:
        out.append(et_guess)
    return out


def maybe_fire(
    items: list[dict],
    *,
    root: Path | str | None = None,
    cfg: dict | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
) -> dict | None:
    """The press-tick seam. Fire the desk if the statement is in this batch.

    THE SMALLEST POSSIBLE SEAM: one call from press_lane.run_press_tick, wrapped
    there in its own try/except, returning None whenever there is nothing to do.
    Fail-soft by construction — :func:`fire` never raises and this never blocks a
    wire tick.

    Idempotent through the statements ledger, so the every-5-minutes wire tick
    that keeps seeing the same RSS item fires the desk exactly once per meeting.
    """
    if not enabled(cfg) or not items:
        return None
    ts = now or datetime.now(timezone.utc)
    for item in items:
        if not is_statement_release(item):
            continue
        date_str = meeting_date_for(item, now=ts)
        if not date_str:
            # An FOMC-statement-shaped headline on a day that is not a decision
            # day. Real cause: the Fed reissues statements and minutes, and the
            # archive is linked from the feed. Not an error.
            continue
        if fomc_statements.is_collected(date_str, root):
            return None
        return fire(date_str=date_str, root=root, cfg=cfg, now=ts,
                    url=str(item.get("url") or "") or None, dry_run=dry_run)
    return None
