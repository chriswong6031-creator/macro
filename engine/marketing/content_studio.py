"""engine.marketing.content_studio — Deterministic mixed-content plan generator.

Produces the per-account content queue and featured chart selection for
data/marketing/content_plan.json.

Public API:
    CONTENT_TYPES          — ordered list of {id, name, desc, color}
    plan_account(account, plans, *, n_days, per_day, seed) -> list[ContentItem]
    distinctness(items)    -> {max_similarity, flags, note}
    content_plan(cfg, plans, *, closes_loader) -> dict  (frozen §2.3 shape)
    content_mix(items)     -> dict  {type_id: count}
    strip_scaffolding(plan) -> dict  (copy, minus in-process "_" keys)
    ARTIFACT_KEEP_KEYS     — the "_" keys allowed to reach the artifact

Selection layer (W1, LLM-first masterplan §5 — all pure, all deterministic):
    ticker_exposure(root, *, as_of)        -> {ticker: last exposure day}
    cooled_tickers(exposure, *, as_of, kind, cfg) -> frozenset[str]
    cooldown_override_reason(ticker, ...)  -> str | None  (new fact class)
    apply_reuse_budget(account_rows, *, cfg) -> counters (mutates queues)
    drop_degenerate_facts(facts, *, band)  -> (facts, n_dropped)
    shape_plan / assign_shapes             -> the corpus-grounded shape mixer
    record_shape_ledger(root, ...)         -> 14-day ledger (NIGHTLY ONLY)
    llm_required(cfg)                      -> the no-fallback law's switch

Spec constraints (§2.1 / §2.2 / §5):
  - Deterministic: NO RNG; stable per run; differs per account via account-hash.
  - Public copy carries NO technical-indicator vocabulary.
  - All 7 content types appear in every account's queue (≥1 each where slots allow).
  - signal is the largest type weight for all accounts.
  - Featured charts ≤12, only for plans with closes available.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

# ─────────────────────────────────────────────────────────────────────────────
# Content type catalogue
# ─────────────────────────────────────────────────────────────────────────────

CONTENT_TYPES: list[dict] = [
    {
        "id": "signal",
        "name": "Signal Alert",
        "desc": "A Prophet plan turned into a cashtag post with a price chart showing where we see opportunity.",
        "color": "#3ddc84",
    },
    {
        "id": "chart",
        "name": "Chart of the Day",
        "desc": "A single annotated price or macro chart that tells one clear story without commentary.",
        "color": "#38e0d4",
    },
    {
        "id": "education",
        "name": "Plain-English Explainer",
        "desc": "A short thread or post that explains one market concept so a non-professional can act on it.",
        "color": "#6a8dff",
    },
    {
        "id": "macro",
        "name": "Macro Note",
        "desc": "A brief plain read on the big picture (rates, liquidity, growth) and what it means right now.",
        "color": "#f59e0b",
    },
    {
        "id": "receipt",
        "name": "Report Card",
        "desc": "A public update on how a past call played out: the numbers, the outcome, what we learned.",
        "color": "#a78bfa",
    },
    {
        "id": "watchlist",
        "name": "On Our Radar",
        "desc": "A short list of names we're watching closely this week but haven't acted on yet.",
        "color": "#fb7185",
    },
    {
        "id": "event",
        "name": "Event Reaction",
        "desc": "A fast-turnaround post reacting to a market-moving event with context and what we'd watch next.",
        "color": "#34d399",
    },
    {
        "id": "mover",
        "name": "Mover of the Day",
        "desc": "The day's single biggest mover, charted, on its cashtag, with the real move %.",
        "color": "#fb923c",
    },
    {
        "id": "theme_list",
        "name": "Theme Tape",
        "desc": "One post tagged with 6-10 cashtags covering a group that's moving, the reach king at 0 followers.",
        "color": "#f472b6",
    },
]

_TYPE_IDS = [t["id"] for t in CONTENT_TYPES]

# Default tilt when config is absent.
# mover + theme_list get REACH weight (0.10 each); shaved from education/receipt
# so signal stays the largest and all weights sum to 1.0.
#
# EDUCATION IS OFF AT 0.00 (operator 2026-07-30). The kind contradicts its own
# copy law and cannot be written out of it:
#   * the law says "education posts show YOUR OWN working on something real from
#     today, never a definition, a lesson, or a rule for the reader";
#   * education items are built with NO market facts on purpose (see the
#     fact-cache branch below: "education posts: no market facts (conceptual,
#     not data-driven)").
# A post with no fact from today can only BE a definition. So the whole bank
# reads as a lecture, and a guard sweep of the 252 deterministic templates found
# 9 of the 10 lecture-register violations sitting in this one family ("Plain
# English: what's a 'setup'?", "The part most people skip"). The operator, on the
# 44 that shipped: "past education posts have all been terrible and useless" and
# "so far none of the education ones are good".
# The weight moves to CHART (0.13 -> 0.23), not into filler and not spread
# thinly across everything: a chart post is anchored to a real fact AND ships an
# illustration, which is the half of the plan the operator wants more of. Tilts
# are validated to sum to 1.0 (personas.PersonaSpecError), so the weight has to
# land somewhere explicit rather than being dropped.
# Re-enable education only when its items are anchored to a real same-day fact
# and LLM-written; the deterministic bank cannot get there.
_DEFAULT_TILT: dict[str, float] = {
    "signal": 0.30,
    "chart": 0.23,
    "education": 0.00,
    "macro": 0.11,
    "receipt": 0.08,
    "watchlist": 0.06,
    "event": 0.06,
    "mover": 0.10,
    "theme_list": 0.06,
}

# Per-account voice copy templates — (type_id, voice) -> (headline_template, body_template)
# Placeholder tokens: {ticker}, {cashtag}, {direction}, {entry}, {target1}, {stance}
_COPY_TEMPLATES: dict[tuple[str, str], tuple[str, str]] = {
    # signal — authoritative desk
    ("signal", "authoritative desk"): (
        "Flagged {cashtag} at {entry}",
        "We're in {ticker} at {entry}, first target {target1}. "
        "If it closes back under {entry} I'm wrong and I'm out. Size it sensibly.",
    ),
    # signal — dry, receipts-forward
    ("signal", "dry, receipts-forward"): (
        "{cashtag}, in at {entry}",
        "{ticker} flagged. T1 {target1}. Out on a close below {entry}. "
        "Historical, not a promise. Win or lose it goes on the page.",
    ),
    # signal — specialist
    ("signal", "specialist"): (
        "{cashtag} at {entry}, and the group's confirming",
        "{ticker} is doing the thing I wait for in these names. "
        "In around {entry}, first level {target1}. The rest of the group's moving with it. "
        "Close back below {entry} and I'm out. Sizing matters more than being right.",
    ),
    # signal — educational
    ("signal", "educational"): (
        "A live one: {cashtag}",
        "We talk about setups in the abstract, so here's a real one. {ticker} at {entry}, "
        "first target {target1}. What proves me wrong: a close under {entry}. "
        "Win or lose it goes on the page so you can watch it play out.",
    ),
    # signal — fast, reactive
    ("signal", "fast, reactive"): (
        "{cashtag} moving. In at {entry}",
        "{ticker} moving. In at {entry}, target {target1}. "
        "Out under {entry}. On the board. Historical, not a promise.",
    ),
    # signal — pattern/history
    ("signal", "pattern/history"): (
        "{cashtag} is tracing something I've seen before",
        "{ticker} is doing the same shape it did last time it ran. "
        "In at {entry}, target {target1}. Close under {entry} and the rhyme breaks. "
        "Rhyme, not repeat. Win or lose it goes on the page.",
    ),
    # chart — all voices share a template per voice; use fallbacks
    ("chart", "authoritative desk"): (
        "{ticker}, one chart",
        "The chart on {ticker} this week. {entry} is the level I keep watching. "
        "No hot take beyond what you can see.",
    ),
    ("chart", "dry, receipts-forward"): (
        "{ticker} chart",
        "{ticker} at {entry}. That's the whole post.",
    ),
    ("chart", "specialist"): (
        "{ticker} chart, and it matters for the group",
        "This week's chart for my corner of the market. {ticker} at {entry}.",
    ),
    ("chart", "educational"): (
        "{ticker}, let me walk you through this",
        "Walking through what this chart's showing on {ticker} at {entry}. "
        "Notice the trend, the level, and the volume.",
    ),
    ("chart", "fast, reactive"): (
        "{ticker} chart, quick",
        "Fast chart on {ticker}. Level {entry}. Your call.",
    ),
    ("chart", "pattern/history"): (
        "{ticker}, this chart looks familiar",
        "This chart on {ticker} matches something I've watched before. Level {entry}. Context below.",
    ),
    # education — unique per voice
    ("education", "authoritative desk"): (
        "What flagging something actually means",
        "When we put a name on the board it means the setup lined up, not that it's a sure thing. "
        "The number that goes with it is where I'm wrong.",
    ),
    ("education", "dry, receipts-forward"): (
        "How I keep myself honest",
        "Every call gets a result posted, win or lose, same flat tone either way. "
        "No quietly forgetting the ones that didn't work.",
    ),
    ("education", "specialist"): (
        "The thing most people get wrong about this group",
        "Most folks read these names through the wrong lens. Here's how I actually think about them.",
    ),
    ("education", "educational"): (
        "Plain English: what's a 'setup'?",
        "It's a price picture that's usually been worth paying attention to. "
        "Not a buy button, just a reason to look closer.",
    ),
    ("education", "fast, reactive"): (
        "Quick: reading momentum",
        "Fast version of what momentum actually tells you, and what it doesn't.",
    ),
    ("education", "pattern/history"): (
        "When history rhymes, read it carefully",
        "Old analogues are useful and dangerous at once. Here's how I use them without kidding myself.",
    ),
    # macro — per voice ({stance} = 'constructive' | 'cautious')
    ("macro", "authoritative desk"): (
        "What the data's saying this week",
        "I'm {stance} here. I'd rather own quality and stay patient than chase. "
        "Watching the next print closely.",
    ),
    ("macro", "dry, receipts-forward"): (
        "Macro, plainly",
        "I'm {stance} on risk right now. I'll update when the picture actually shifts.",
    ),
    ("macro", "specialist"): (
        "Why the macro matters for these names",
        "The big picture matters more for my group right now. "
        "I'm {stance}, and adjusting the names accordingly.",
    ),
    ("macro", "educational"): (
        "The macro in plain words",
        "Reading it plainly: I'm {stance} here. "
        "Watching which side blinks first.",
    ),
    ("macro", "fast, reactive"): (
        "Macro, quick: {stance}",
        "Quick note. I'm {stance}. Adjusting for it.",
    ),
    ("macro", "pattern/history"): (
        "This macro setup rhymes with something",
        "Being {stance} here reminds me of a past setup. Here's what the chart did then.",
    ),
    # receipt — per voice
    ("receipt", "authoritative desk"): (
        "How that call played out",
        "We called it. Here's the result with the numbers, whichever way it went. "
        "Something to learn from either way.",
    ),
    ("receipt", "dry, receipts-forward"): (
        "Call result",
        "We made a call. Here's what happened, straight to the number.",
    ),
    ("receipt", "specialist"): (
        "How the group read played out",
        "Following up on that call off the group's move. Here's the result.",
    ),
    ("receipt", "educational"): (
        "One result, posted flat",
        "We said it. Here's what happened. This is what showing your work looks like.",
    ),
    ("receipt", "fast, reactive"): (
        "Called it, here's the result",
        "Called it. Here's what happened, straight to the numbers.",
    ),
    ("receipt", "pattern/history"): (
        "Did the rhyme hold?",
        "We flagged the shape. Here's whether it followed through this time.",
    ),
    # watchlist — per voice
    ("watchlist", "authoritative desk"): (
        "On my radar this week",
        "Names I'm watching but haven't touched. Keeping the list honest.",
    ),
    ("watchlist", "dry, receipts-forward"): (
        "Watching, no position",
        "Watching these. Not in yet. I'll update if something triggers.",
    ),
    ("watchlist", "specialist"): (
        "Names in my group I'm watching",
        "These are setting up in my corner of the market. Watching, not acting yet.",
    ),
    ("watchlist", "educational"): (
        "What earns a spot on a watch list",
        "These are the names I'm monitoring and why each one's on the list.",
    ),
    ("watchlist", "fast, reactive"): (
        "Watching these right now",
        "Fast list of names worth attention. No position yet.",
    ),
    ("watchlist", "pattern/history"): (
        "Patterns I'm watching",
        "Names tracing shapes worth monitoring. Context below.",
    ),
    # event — per voice. Plan copy must stay FACT-NEUTRAL: "the data says one
    # thing, the price says another" asserts a divergence the template cannot
    # know. Only the fact layer may describe the tape.
    ("event", "authoritative desk"): (
        "My read on today's move",
        "Here's how I'm reading today's move, and what would change my mind. "
        "Watching the close.",
    ),
    ("event", "dry, receipts-forward"): (
        "Today's event, numbers first",
        "Event happened. Here are the numbers and what they change.",
    ),
    ("event", "specialist"): (
        "What today's event does to my group",
        "Today's event flows straight into the names I watch. Here's the read.",
    ),
    ("event", "educational"): (
        "What today's event actually means",
        "Big event today. Cutting through the noise and watching how markets price it in.",
    ),
    ("event", "fast, reactive"): (
        "Reaction: {event_name}",
        "Fast take on today's event. Key number: {entry}. What I'm watching next.",
    ),
    ("event", "pattern/history"): (
        "How events like this have played out",
        "We've seen this kind of day before. Watching if it rhymes.",
    ),
}


def _drafts_nightly_copy(cfg: dict | None, account_id: str) -> bool:
    """Does this desk draft nightly PERSONA copy, or is it a wire relay?

    A desk earns a nightly queue by having a `copywriter.personas.<id>` block —
    an authored voice. A desk without one is a WIRE desk: it relays in the house
    wire voice (engine/marketing/wire_voice.py) and never editorializes (charter,
    masterplan §4), and its volume arrives through the wire lanes, which never
    touch content_plan.

    THE PERSONA BLOCK IS THE RIGHT KEY, not `kind`. `kind: branded` covers the
    flagship and the founder, both of which absolutely do draft. The presence of
    an authored voice is the thing that actually differs, and it is the same fact
    `_get_copy` needs: a persona-less desk has no template bank of its own, so
    drafting for it can only borrow another desk's and collide with it under the
    cross-account near-dup guard.

    Fails OPEN (returns True) when the personas block is missing or unreadable —
    a config we cannot parse must not silently mute every desk in the network.
    """
    try:
        personas = ((cfg or {}).get("copywriter") or {}).get("personas") or {}
        if not isinstance(personas, dict) or not personas:
            return True
        return str(account_id) in personas
    except Exception:  # noqa: BLE001
        return True


def _get_copy(type_id: str, voice: str) -> tuple[str, str]:
    """Get headline/body templates for (type_id, voice), with fallback."""
    key = (type_id, voice)
    if key in _COPY_TEMPLATES:
        return _COPY_TEMPLATES[key]
    # Fallback: look for same type with authoritative desk voice
    fallback = (type_id, "authoritative desk")
    if fallback in _COPY_TEMPLATES:
        return _COPY_TEMPLATES[fallback]
    return ("{cashtag} update", "Tracking {ticker}. More details to follow.")


def _render_copy(template: str, plan: dict | None, account_id: str) -> str:
    """Fill template with plan fields. Safe — missing fields become empty string."""
    if plan is None:
        return template
    ticker = plan.get("asset", "")
    cashtag = f"${ticker}" if ticker else ""
    direction = plan.get("direction", "")
    entry = str(plan.get("entry", ""))
    targets = plan.get("targets", [])
    target1 = str(targets[0]) if targets else ""
    phase = plan.get("phase", "")
    stance = "constructive" if direction == "BULL" else "cautious"
    event_name = "today's data"
    return (
        template
        .replace("{cashtag}", cashtag)
        .replace("{ticker}", ticker)
        .replace("{direction}", direction)
        .replace("{entry}", entry)
        .replace("{target1}", target1)
        .replace("{phase}", phase)
        .replace("{stance}", stance)
        .replace("{event_name}", event_name)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Account-hash deterministic seed
# ─────────────────────────────────────────────────────────────────────────────

def _account_hash(account_id: str) -> int:
    """Deterministic integer derived from account id. Stable across runs."""
    h = hashlib.sha256(account_id.encode()).hexdigest()
    return int(h[:8], 16)


# ─────────────────────────────────────────────────────────────────────────────
# Signal eligibility gate — NEVER post a stale / failed / invalidated signal
# ─────────────────────────────────────────────────────────────────────────────
# A live post is a public commitment. A signal whose stop has been breached, or
# that has expired, or that we hold low confidence in, must never leave the desk
# — that is how the QCOM invalidated-signal leak happened. This gate is the
# single chokepoint every signal post and featured chart passes through.

# Prophet lifecycle phases / actions that mean the trade is dead or exiting.
_DEAD_PHASES = frozenset({"invalidated", "stopped_out", "closed", "expired", "overtime"})
_DEAD_ACTIONS = frozenset({"invalidated", "exit", "close", "stop", "trim", "reduce", "avoid"})
# Only genuinely live, healthy, pre-first-target plans are postable as signals.
_LIVE_PHASES = frozenset({"triggered_pre_t1", "triggered", "active", "pre_trigger", "running"})
_MIN_CONFIDENCE = 50.0        # management_confidence floor (QCOM was 13.5)
_MAX_SIGNAL_AGE_DAYS = 21     # a signal older than this is stale, not news


def _signal_age_days(signal_date: object, *, today: str | None = None) -> int | None:
    """Whole days between the plan's signal date and today (UTC). None if unparseable."""
    try:
        s = str(signal_date)[:10]
        y, m, d = (int(x) for x in s.split("-"))
        sd = date(y, m, d)
        if today:
            ty, tm, td = (int(x) for x in str(today)[:10].split("-"))
            now = date(ty, tm, td)
        else:
            now = datetime.now(timezone.utc).date()
        return (now - sd).days
    except Exception:
        return None


def is_postable_signal(plan: dict, *, today: str | None = None) -> bool:
    """True only if *plan* is a live, healthy, fresh, confident signal worth posting.

    Rejects: invalidated / stopped-out / expired / trimming plans, low-confidence
    plans, and stale signals. This is the gate the QCOM failed signal skipped.
    """
    if not isinstance(plan, dict):
        return False
    if plan.get("direction") not in ("BULL", "BEAR"):
        return False
    phase = str(plan.get("phase", "")).lower()
    action = str(plan.get("recommended_action", "")).lower()
    if phase in _DEAD_PHASES or action in _DEAD_ACTIONS:
        return False
    if _LIVE_PHASES and phase and phase not in _LIVE_PHASES:
        return False
    try:
        conf = float(plan.get("management_confidence", 0) or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if conf < _MIN_CONFIDENCE:
        return False
    age = _signal_age_days(plan.get("_signal_date"), today=today)
    if age is None or age < 0 or age > _MAX_SIGNAL_AGE_DAYS:
        return False
    return True


def postable_signals(plans: list[dict], *, today: str | None = None) -> list[dict]:
    """Filter a plan list to only the signals that pass the eligibility gate."""
    return [p for p in (plans or []) if is_postable_signal(p, today=today)]


# ─────────────────────────────────────────────────────────────────────────────
# SELECTION LAYER (W1) — cooldowns, reuse budgets, degeneracy, shapes
#
# CONTENT STUDIO LLM-FIRST masterplan §5 (research/
# MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md, operator directive
# 2026-07-29) + the W1 build contract (research/marketing_dockets/
# CONTENT_STUDIO_W1_BUILD_CONTRACT.md §Selection).
#
# WHAT THIS FIXES. The 2026-07-29 batch put ARES on five desks with the same
# entry, LKFN/GPI/CBOE two days running, and shipped "231 of 231 names bullish"
# as a fact — because NOTHING in this module had ever asked "did we already post
# this name?". Allocation was a pure function of (tilt, account hash, plan pool);
# the outbox ledger, which is repo-truth about what already went out, was never
# read on the way IN. Every helper below is a PURE function of (plan inputs,
# ledger snapshot) — no RNG, no wall clock — so re-planning the same night twice
# yields the same verdicts, which is the only property that makes a selection
# gate auditable.
# ─────────────────────────────────────────────────────────────────────────────

#: The kinds the nightly Content Studio plans and writes copy for. Distinct from
#: the wire lanes (`mover`/`theme_list` publish-time, `wire`/`breaking`/`earnings`
#: fast lanes) which keep their deterministic register and their own gates.
#: §0 gate 1: template prose may not reach the outbox on THESE kinds.
#: XG-E2 added `congress` + `insider` — the fact-locked filing lanes. They are
#: PLANNED, not wire: a filing packet reaches the reader through the v2 writer,
#: so the no-fallback law applies and a template sentence can never appear under
#: a named politician or a named executive.
PLANNED_KINDS: frozenset[str] = frozenset({
    "signal", "chart", "education", "macro", "receipt", "watchlist", "event",
    "congress", "insider",
})

#: Post shapes (contract §Shapes). `two_part` is the ONLY shape carrying a
#: headline; `caption` REQUIRES media at emit (the chart does the talking).
SHAPES: tuple[str, ...] = ("one_liner", "two_part", "stack", "list", "caption")

#: Angle vocabulary (contract §Context contract). The angle is the post's JOB —
#: when one fact legitimately reaches two desks they must draw DISJOINT angles,
#: which is what stops "one fact wearing five outfits" (§1 defect census).
ANGLES: tuple[str, ...] = (
    "level_watch", "risk_frame", "group_read", "precedent", "process",
    "receipt_frame", "macro_read", "event_read",
)

#: Angle preference per kind, in assignment order. The Nth account to keep a
#: ticker on a day takes the Nth angle, so two desks on one fact never share one.
_ANGLE_BY_KIND: dict[str, tuple[str, ...]] = {
    "signal":     ("level_watch", "risk_frame"),
    "watchlist":  ("level_watch", "risk_frame"),
    "chart":      ("level_watch", "precedent"),
    "receipt":    ("receipt_frame", "process"),
    "macro":      ("macro_read", "group_read"),
    "event":      ("event_read", "macro_read"),
    "education":  ("process", "precedent"),
    "mover":      ("group_read", "level_watch"),
    "theme_list": ("group_read", "macro_read"),
    # XG-E2 filing lanes. NOT level_watch (the `angle_for` default): a
    # disclosure names no level, and a filing post that opens on one is
    # inventing the part of the story the filing cannot supply. The job is
    # "here is what the record says" (process), then how it sits against the
    # wider tape (group_read) or against what came before (precedent).
    "congress":   ("process", "group_read"),
    "insider":    ("process", "precedent"),
}

# Selection defaults — the config block (config/marketing.yml `selection:`) is
# the operator surface; these are the safe in-code fallbacks when a key is
# absent. Cooldowns are in TRADING days, not calendar days: a Friday post is
# still one session old on Monday, and a calendar cooldown would silently give
# every weekend a free pass.
_DEFAULT_TICKER_COOLDOWN_DAYS = 3      # watchlist / chart / caption exposure
_DEFAULT_SIGNAL_COOLDOWN_DAYS = 5      # a directional call with entry/stop
_DEFAULT_MAX_ACCOUNTS_PER_TICKER_DAY = 2
_DEFAULT_MAX_SIGNAL_ACCOUNTS_PER_DAY = 1
# Low arm 0.0 = saturation-only (fix-wave ruling, mirrors market_facts): the
# diagnosed defect was "231 of 231" — a denominator the numerator cannot move
# against. The symmetric 5% floor this shipped with was NEW suppression that
# deleted washouts ("11 of 232 showing momentum"), the rarest and most
# newsworthy breadth print. A washout is information; only saturation is
# vacuous. ratio<=0.0 is unreachable for a positive count, and a 0-of-N read
# ("no triggers") is likewise information, not noise. Config can still narrow
# via selection.degenerate_stat_band.
_DEFAULT_DEGENERATE_BAND: tuple[float, float] = (0.0, 0.95)

#: Folded outbox statuses that count as EXPOSURE — the name reached, or is about
#: to reach, a timeline. `quarantined`/`failed`/`recalled` deliberately do NOT:
#: a post nobody saw must not lock a ticker out of tonight's plan (same reasoning
#: as outbox.dead_item_ids for the near-dup corpus).
_EXPOSURE_STATUSES: frozenset[str] = frozenset({
    "queued", "approved", "posting", "posted",
})

#: |day move| that re-opens a cooled ticker (masterplan §5.1 new-fact classes).
_NEW_FACT_MOVE_PCT = 4.0

_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")


def selection_cfg(cfg: dict | None) -> dict[str, Any]:
    """The resolved `selection:` block — every key with its in-code fallback.

    ONE reader of the config block, so a knob can never be honoured at one seam
    and ignored at another. Junk values fall back rather than raising: a typo in
    a cadence knob must not take the nightly down.
    """
    raw = ((cfg or {}).get("selection") or {}) if isinstance(cfg, dict) else {}

    def _int(key: str, default: int) -> int:
        try:
            return int(raw.get(key, default))
        except (TypeError, ValueError):
            return default

    band = raw.get("degenerate_stat_band")
    lo, hi = _DEFAULT_DEGENERATE_BAND
    if isinstance(band, (list, tuple)) and len(band) == 2:
        try:
            lo, hi = float(band[0]), float(band[1])
        except (TypeError, ValueError):
            lo, hi = _DEFAULT_DEGENERATE_BAND
    if lo > hi:
        lo, hi = hi, lo

    return {
        "ticker_cooldown_days": _int("ticker_cooldown_days", _DEFAULT_TICKER_COOLDOWN_DAYS),
        "signal_cooldown_days": _int("signal_cooldown_days", _DEFAULT_SIGNAL_COOLDOWN_DAYS),
        "max_accounts_per_ticker_day": _int(
            "max_accounts_per_ticker_day", _DEFAULT_MAX_ACCOUNTS_PER_TICKER_DAY),
        "max_signal_accounts_per_day": _int(
            "max_signal_accounts_per_day", _DEFAULT_MAX_SIGNAL_ACCOUNTS_PER_DAY),
        "degenerate_stat_band": (lo, hi),
    }


def _iso_date(value: object) -> date | None:
    """Parse a YYYY-MM-DD prefix to a date. None on anything unparseable."""
    try:
        y, m, d = (int(x) for x in str(value)[:10].split("-"))
        return date(y, m, d)
    except Exception:  # noqa: BLE001
        return None


def trading_days_since(earlier: object, later: object) -> int | None:
    """Mon–Fri sessions in ``(earlier, later]`` — sessions elapsed since exposure.

    Posted yesterday (Tue) and planning today (Wed) → 1. Posted Friday and
    planning Monday → 1, which is the whole reason this is not a calendar diff:
    a 3-CALENDAR-day cooldown lets every Friday name come back on Monday.

    No market-holiday calendar is consulted on purpose — this module has no
    dependency on one, and treating a holiday as a session only ever makes the
    cooldown SHORTER by one, in the direction the operator already tolerates.
    Returns None when either side is unparseable (caller fails closed), 0 when
    ``later`` is not after ``earlier``, and a large sentinel past 60 days so the
    walk can never become a hot loop on a corrupt row.
    """
    d0, d1 = _iso_date(earlier), _iso_date(later)
    if d0 is None or d1 is None:
        return None
    if d1 <= d0:
        return 0
    if (d1 - d0).days > 60:
        return 999
    n = 0
    cur = d0
    while cur < d1:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def _item_tickers(item: dict) -> set[str]:
    """The ticker(s) an outbox item put in front of readers.

    `source.ticker` is the structured stamp emit_from_content_plan writes and is
    always preferred. The cashtag fallback is deliberately narrowed to posts
    naming EXACTLY ONE ticker: a theme_list carrying eight member cashtags is
    coverage of a GROUP, and letting it cool eight names for three sessions
    would starve the plan pool for a post nobody reads as "$X coverage".
    """
    src = item.get("source") or {}
    if isinstance(src, dict):
        t = str(src.get("ticker") or "").strip().upper()
        if t:
            return {t}
    tags = set(_CASHTAG_RE.findall(str(item.get("text") or "")))
    return tags if len(tags) == 1 else set()


def ticker_exposure(
    root: str | Path | None = None,
    *,
    as_of: str,
    state: dict | None = None,
) -> dict[str, str]:
    """ticker → the LATEST prior day on which any account had exposure to it.

    Reads the outbox ledger (items.jsonl folded through status_ledger.jsonl —
    outbox.fold_state), which is repo-truth about what the network has shown
    readers. `state` lets a caller (or a test) hand in a pre-folded snapshot.

    STRICTLY EARLIER DAYS ONLY. Tonight's own emission is same-day exposure and
    is governed by the reuse BUDGET, not the cross-day cooldown — counting it
    here would mean a governor re-run for the same date found every ticker
    cooled by its own first pass and planned an empty night.

    Fail-soft: an unreadable ledger yields {} (no cooldown), because a missing
    ops file must never be able to zero a night's content. The gate it feeds is
    a quality gate, not a safety gate.
    """
    out: dict[str, str] = {}
    try:
        if state is None:
            from engine.marketing.outbox import fold_state  # noqa: PLC0415
            state = fold_state(root)
        items = state.get("items") or {}
        statuses = state.get("status") or {}
        today = str(as_of or "")[:10]
        for iid, item in items.items():
            if str(statuses.get(iid, "queued")) not in _EXPOSURE_STATUSES:
                continue
            day = str(item.get("as_of") or "")[:10]
            if not day or (today and day >= today):
                continue
            for tkr in _item_tickers(item):
                if day > out.get(tkr, ""):
                    out[tkr] = day
    except Exception as exc:  # noqa: BLE001
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "content_studio.ticker_exposure: ledger unreadable (%s) — no cooldown", exc)
        return {}
    return out


def cooldown_days_for(kind: str, cfg: dict | None = None) -> int:
    """Sessions a ticker is ineligible for, by post kind. 0 = no cooldown.

    signal carries entry/stop numbers, so a repeat inside a week reads as the
    same call re-issued (5 sessions); watchlist/chart are coverage (3). Kinds
    that name no ticker (macro/education/event) are not cooled at all.
    """
    sel = selection_cfg(cfg)
    if kind == "signal":
        return max(int(sel["signal_cooldown_days"]), 0)
    if kind in ("watchlist", "chart", "receipt"):
        return max(int(sel["ticker_cooldown_days"]), 0)
    return 0


def cooled_tickers(
    exposure: dict[str, str],
    *,
    as_of: str,
    kind: str,
    cfg: dict | None = None,
) -> frozenset[str]:
    """The tickers INELIGIBLE for ``kind`` tonight, given the exposure map.

    Fails CLOSED on an unparseable exposure date (trading_days_since → None):
    a row we cannot date is a row we cannot clear.
    """
    days = cooldown_days_for(kind, cfg)
    if days <= 0:
        return frozenset()
    out: set[str] = set()
    for tkr, day in (exposure or {}).items():
        elapsed = trading_days_since(day, as_of)
        if elapsed is None or elapsed < days:
            out.add(str(tkr).upper())
    return frozenset(out)


def cooldown_override_reason(
    ticker: str,
    *,
    pack: dict | None = None,
    facts: dict | None = None,
    plan: dict | None = None,
) -> str | None:
    """A NEW FACT CLASS that re-opens a cooled ticker, or None (masterplan §5.1).

    Four classes, and only four: an earnings print, a |day move| ≥ 4%, a level
    break, and a streak-rarity record. The returned string is threaded into the
    writer context as `cooldown_override_reason` and the post must LEAD with it —
    "we covered this name on Monday" is only defensible when the thing that
    changed is the first thing the reader sees.

    Reads the Hot Tape context pack (#3941, `data/marketing/hot_tape_pack.json`)
    when present and degrades to today's facts otherwise — dependency-inverted,
    no import of radar code (masterplan §4).
    """
    src: dict = {}
    for blob in (pack, facts, plan):
        if isinstance(blob, dict):
            for k, v in blob.items():
                src.setdefault(k, v)
    if not src:
        return None

    if src.get("earnings_today") or src.get("is_earnings_day"):
        return f"{ticker} reports today"

    for key in ("day_move_pct", "pct_change", "day_pct", "move_pct"):
        raw = src.get(key)
        if raw is None:
            continue
        try:
            pct = float(raw)
        except (TypeError, ValueError):
            continue
        if abs(pct) >= _NEW_FACT_MOVE_PCT:
            return f"{ticker} moved {pct:+.1f}% today"

    level = src.get("level_break") or src.get("broke_level")
    if level:
        return f"{ticker} broke {level}" if isinstance(level, str) else f"{ticker} broke its level"

    streak = src.get("streak_record") or src.get("streak_rarity_record")
    if streak:
        return f"{ticker} {streak}" if isinstance(streak, str) else f"{ticker} set a streak record"

    return None


# ── Degenerate-stat gate (masterplan §5.3, §0 gate 3h) ────────────────────────
# "231 of 231 names bullish" is not a fact, it is a definition — a count whose
# hit-rate saturates its universe carries ZERO information and reads as a broken
# screen. The gate is on the RATIO, not on a phrase list, because the next
# degenerate stat is always a different sentence.

_COUNT_KEY_PAIRS: tuple[tuple[str, str], ...] = (
    ("n_moving", "n_tracked"),
    ("numerator", "denominator"),
    ("n", "n_total"),
    ("count", "universe"),
    ("hits", "n_tested"),
)

_COUNT_TEXT_RE = re.compile(r"\b(\d{1,6})\s+of\s+(\d{1,6})\b", re.IGNORECASE)


def is_degenerate_count(
    numerator: object,
    denominator: object,
    *,
    band: tuple[float, float] = _DEFAULT_DEGENERATE_BAND,
) -> bool:
    """True when numerator/denominator saturates its universe (≥hi or ≤lo).

    A zero/absent denominator is NOT degenerate — it is unknown, and the
    denominator law (contract §Tests, Builder A's validator) handles a count
    that never states its universe.
    """
    try:
        num, den = float(numerator), float(denominator)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if den <= 0:
        return False
    ratio = num / den
    lo, hi = band
    # lo<=0 disables the low arm entirely: with an inclusive <=, a lo of 0.0
    # would still swallow the "0 of N" washout the saturation-only ruling
    # explicitly protects ("no triggers is information too"). A positive lo
    # remains a config opt-in with its original inclusive semantics.
    return ratio >= hi or (lo > 0 and ratio <= lo)


def _fact_is_degenerate(fact: dict, *, band: tuple[float, float]) -> bool:
    """Structured fields first, "<n> of <N>" prose second (belt and braces).

    market_facts is migrating count facts to STRUCTURED fields (masterplan §4,
    Builder A) — until every producer has, the prose form is still how a
    degenerate count reaches copy, and reading only the structured keys would
    have shipped the exact defect this gate is named for.
    """
    for num_key, den_key in _COUNT_KEY_PAIRS:
        if num_key in fact and den_key in fact:
            if is_degenerate_count(fact.get(num_key), fact.get(den_key), band=band):
                return True
    m = _COUNT_TEXT_RE.search(str(fact.get("text") or ""))
    if m and is_degenerate_count(m.group(1), m.group(2), band=band):
        return True
    return False


def drop_degenerate_facts(
    facts: dict | None,
    *,
    band: tuple[float, float] = _DEFAULT_DEGENERATE_BAND,
) -> tuple[dict, int]:
    """Return (facts-with-degenerate-counts-removed, n_dropped). Never mutates.

    Operates on the chart_facts/market_facts shape
    ``{"facts": [{"text": ..., ...}], "numbers_whitelist": [...]}``. A facts blob
    of another shape passes through untouched — this gate drops facts, it never
    invents a schema.

    THE WHITELIST IS PRUNED WITH THE FACT. A number stays licensed only while
    some surviving fact carries it: dropping "231 of 231 names" while leaving
    231 in ``numbers_whitelist`` leaves the model free to write the count the
    gate just deleted, with the packet's own blessing. Numbers the blob lists
    but no fact claims (a producer's extras) are left alone — this prunes what
    the drop orphaned, it does not rebuild the producer's list.
    """
    if not isinstance(facts, dict) or not isinstance(facts.get("facts"), list):
        return (facts if isinstance(facts, dict) else {}), 0
    kept: list = []
    removed: list = []
    for f in facts["facts"]:
        if isinstance(f, dict) and _fact_is_degenerate(f, band=band):
            removed.append(f)
        else:
            kept.append(f)
    if not removed:
        return facts, 0
    out = dict(facts)
    out["facts"] = kept
    whitelist = facts.get("numbers_whitelist")
    if isinstance(whitelist, list):
        still_claimed: set = set()
        for f in kept:
            if isinstance(f, dict):
                still_claimed.update(str(n) for n in (f.get("numbers") or []))
        orphaned: set = set()
        for f in removed:
            orphaned.update(str(n) for n in (f.get("numbers") or []))
        orphaned -= still_claimed
        if orphaned:
            out["numbers_whitelist"] = [n for n in whitelist
                                        if str(n) not in orphaned]
    return out, len(removed)


def angle_for(kind: str, rank: int) -> str:
    """The angle for the ``rank``-th account carrying a fact (0-based).

    Disjoint by construction while rank < len(preferences) — and the reuse
    budget caps the accounts per (ticker, day) at 2, which is exactly the length
    of every row in _ANGLE_BY_KIND.
    """
    prefs = _ANGLE_BY_KIND.get(kind) or ("level_watch", "risk_frame")
    return prefs[rank % len(prefs)]


def _slot_day(slot: object) -> str:
    """The ``D<n>`` prefix of a slot label, or "" for a publish-time slot."""
    s = str(slot or "")
    head = s.split("-", 1)[0]
    return head if len(head) >= 2 and head[0] == "D" and head[1:].isdigit() else ""


# ─────────────────────────────────────────────────────────────────────────────
# PERISHABILITY
# ─────────────────────────────────────────────────────────────────────────────
# Kinds whose copy makes a claim about the CURRENT tape. "Closed green 3 sessions
# in a row" is true tonight and false by Friday; "held 245 for 23 straight
# sessions" is a level that survives the week.
_DEFAULT_PERISHABLE_KINDS = frozenset({
    "signal", "chart", "macro", "event", "mover", "theme_list",
})
_DEFAULT_PERISHABLE_MAX_DAY = 1


def perishable_kinds(cfg: dict | None) -> frozenset[str]:
    raw = ((cfg or {}).get("selection") or {}).get("perishable_kinds")
    if isinstance(raw, (list, tuple, set)) and raw:
        return frozenset(str(k).strip() for k in raw if str(k or "").strip())
    return _DEFAULT_PERISHABLE_KINDS


def perishable_max_day(cfg: dict | None) -> int:
    raw = ((cfg or {}).get("selection") or {}).get("perishable_max_day")
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_PERISHABLE_MAX_DAY
    return n if n >= 1 else _DEFAULT_PERISHABLE_MAX_DAY


def _slot_day_num(slot: Any) -> int | None:
    """Day NUMBER out of a ``D<n>-S<m>`` ladder label. None when unparseable.

    Distinct from :func:`_slot_day` above, which returns the ``"D1"`` STRING the
    fact-reuse budget keys its per-day maps on. Naming this one `_slot_day`
    shadowed that function and silently disabled the whole reuse budget — the
    ARES x5 guard — because its `day_prefix="D1"` comparison started meeting an
    int. 28 tests went red. Keep the two names apart.
    """
    m = re.match(r"^D(\d+)-", str(slot or ""))
    return int(m.group(1)) if m else None


#: Share of degraded cards above which the run says so at ::warning rather than
#: ::notice. Deliberately low: the rasteriser either works on a host or it does
#: not, so a handful of fallbacks is already the failure, not noise.
_LEGACY_FALLBACK_ALARM_SHARE = 0.10

def _alarm_on_starved_receipts(
    plans: list[dict],
    n_receipts: int,
    window_days: int,
    today: str | None = None,
) -> None:
    """A receipts desk with budget and no supply must say which it is.

    THE SILENCE THIS REPLACES (2026-07-31). `graded_receipts` returned 0 every
    night, the receipts desk drew its share of the tilt, and the plan recorded a
    bare `graded_receipts: 0` that reads as "nothing resolved" — an honest quiet
    week. It was not. Six plans on the live board HAD resolved (three hit a
    profit level, three invalidated); they were 21 to 22 days old against a
    14-day window. The supply existed and the gate was cutting it off.

    Those two states look identical in the artifact and need opposite responses:
    nothing to say is fine and self-correcting; a window shorter than the horizon
    it grades is a permanent famine. So when there are ZERO receipts but resolved
    plans exist just outside the window, this names the oldest one and the number
    of days by which the window missed it.
    """
    if n_receipts:
        return
    try:
        from engine.marketing.receipt_source import _age_days, _is_resolved
    except Exception:  # noqa: BLE001
        return

    missed: list[int] = []
    for plan in plans or []:
        if not isinstance(plan, dict) or not _is_resolved(plan):
            continue
        age = _age_days(plan.get("_signal_date"), today=today)
        if age is not None and age > window_days:
            missed.append(age)
    if not missed:
        return          # genuinely nothing resolved — a quiet week, not a fault
    print(f"::warning title=marketing-receipts-starved::"
          f"{len(missed)} plan(s) RESOLVED but every one is older than the "
          f"{window_days}-day receipt window (oldest {max(missed)}d, nearest "
          f"{min(missed)}d). The receipts desk is drawing budget and can emit "
          f"nothing. Prophet's horizon is 2-4 weeks, so a window shorter than it "
          f"can only ever be empty — raise copywriter.receipt_max_age_days.",
          flush=True)


#: The ONE ladder day that can reach the outbox. outbox.emit_from_content_plan
#: takes `day_prefix="D1"` and skips every other slot with one unconditional
#: `continue`, and the governor takes that default.
_EMIT_DAY = "D1"


def _is_writable_day(slot: object, cfg: dict | None = None) -> bool:
    """Should the MODEL be paid to write copy for this slot?

    THE 93% THAT WAS THROWN AWAY (operator, 2026-07-31: "why in the hell would
    you need 915 posts planned?"). The planner books a SEVEN-DAY forward ladder,
    and the writer was handed every slot on it. On the 2026-07-31 nightly that
    was 915 posts across six enabled desks — while `_sel_report["after_budget"]`,
    the count of slots that can actually emit, was 65.

    The other 850 were not a buffer. Nothing reads a previous plan: `content_plan`
    builds from `plan_account` every night, so today's D2 never becomes tomorrow's
    D1 — tomorrow regenerates the whole ladder from scratch. So the model was paid
    for seven days of copy, six of which were overwritten before they could ever
    be read, every single night.

    Writable now:
      * the EMIT day (D1) — the only ladder slots the outbox will take;
      * every NON-ladder slot (any publish-time lane) — `_slot_day` returns ""
        for these and the publish-time lanes ship through their own path, so
        excluding them would silence live reach content. This is the part a
        naive `slot.startswith("D1-")` filter would get wrong.

        THEME-/MOVER- were listed here and no longer exist: those labels were
        the movers desk's, and "their own path" was a belief, not a path — the
        outbox skips every non-D1 slot, so those items shipped nowhere. The
        movers desk now takes real D1 rungs at distribution, which lands it in
        the first bullet.

    Forward ladder slots keep the deterministic template copy `plan_account`
    already gave them, so the admin preview still shows a populated week; they
    are simply not sent to a model to be written in prose that nothing will read.

    `copywriter.llm.write_forward_days: true` restores the old behaviour for
    anyone who wants to pay for it.
    """
    llm_cfg = ((cfg or {}).get("copywriter") or {}).get("llm") or {}
    if bool(llm_cfg.get("write_forward_days", False)):
        return True
    day = _slot_day(slot)
    return day in ("", _EMIT_DAY)

#: Share of writer drops at which a night is reported as broken rather than picky.
#: The writer rejecting a third of a plan is editing; rejecting most of it is an
#: outage wearing an editorial costume.
_COPY_DROP_ALARM_SHARE = 0.50

#: Share of PROVIDER-STAGE drops at which the night is called an outage rather
#: than a bad night. Same number as the drop alarm above, and deliberately so —
#: what changes is the SEVERITY and the diagnosis, not the trip point.
#:
#: WHY A SECOND, LOUDER GATE (07-30 and 07-31, both through green CI). The
#: existing gate fires at ::warning, which GitHub renders next to lint noise and
#: which nobody reads on a run that concluded successfully. A provider that
#: serves nothing is not a picky writer: with the no-fallback law armed, every
#: item it touches is deleted, so a provider-dominated night is the difference
#: between "we published less" and "we published nothing, and will again
#: tomorrow unless someone moves". The second night is the proof that ::warning
#: was the wrong level — the first night's warning existed and changed nothing.
_PROVIDER_OUTAGE_SHARE = 0.50

#: Stage → what an operator should actually go and check. A drop census that
#: prints stage names makes the reader translate; naming the remedy is the whole
#: difference between a number and an alert.
_COPY_DROP_REMEDY: dict[str, str] = {
    "provider": ("the writer got nothing usable back — see the reason breakdown, "
                 "which says whether that was a missing credential or a served "
                 "response with no text"),
    "validate": "the model answered and the copy laws refused it — a voice/guard problem",
    "critic": "the critic vetoed the drafts — a quality problem, not an outage",
}

#: THE STAGE IS NOT THE CAUSE, AND ON 2026-07-31 IT SENT THE READER THE WRONG WAY.
#:
#: The alarm fired correctly that night — 915 planned, 915 dropped, stage
#: "provider" — and then told the operator "the LLM never answered, check
#: credentials first". The log said otherwise: codex failed over as designed,
#: and DeepSeek SERVED ALL 916 CALLS, every one HTTP 200. Not one credential was
#: at fault. The model returned a response the writer could not read, so
#: `_v2_write_one` hit `if not text: dropped_provider` — the same stage bucket as
#: a missing key, and the opposite fix.
#:
#: Anyone following that remedy would have checked four credentials, found them
#: all working, and concluded the alarm was wrong. So the remedy is keyed on the
#: REASON the copywriter already records, and only falls back to the stage when
#: the reasons are unrecognised.
_PROVIDER_DROP_REMEDY: dict[str, str] = {
    "no_provider_credential": (
        "NO credential was visible to the step — pass CLAUDE_CODE_OAUTH_TOKEN* / "
        "ANTHROPIC_API_KEY / DEEPSEEK_API_KEY, and check MARKETING_LLM_ENABLED"),
    "provider returned no text": (
        "the provider ANSWERED and returned no usable text, so this is NOT a "
        "credential problem — check the model's response shape (a reasoning/"
        "thinking block ahead of the text block reads as empty) and the "
        "per-provider parse in engine/llm_auth"),
    # The reasons below are FAMILIES: the copywriter writes them suffixed
    # (`provider_no_text:deepseek`, `provider_error:ConnectionError`) and
    # `_drop_reason_family` strips the suffix before the lookup. The suffix is
    # not decoration — the breaker has no other channel through which to learn
    # WHICH rung broke, because the reason census is the only per-drop detail
    # that reaches this module.
    "provider_no_text": (
        "the provider ANSWERED and returned no usable text, so this is NOT a "
        "credential problem. The writer already spent its one same-provider "
        "retry and its one failover rung on each item, so every rung named in "
        "the reason served nothing: pull the named provider out of "
        "copywriter.llm.provider_order and check the model's response shape (a "
        "reasoning/thinking block ahead of the text block reads as empty under "
        "a small per_post_max_tokens)"),
    "provider_error": (
        "every provider in the waterfall failed HARD (connection/5xx) for these "
        "items — a transport or endpoint problem, not a credential; the "
        "exception type is in the reason"),
    "provider_unavailable": (
        "the waterfall had nothing left to try — every rung was rate-limited, "
        "401'd, or absent; the make_call reason is in the suffix"),
    "provider_refusal": (
        "the MODEL refused these prompts (stop_reason=refusal) — an editorial "
        "or prompt problem, not an outage, and deliberately never failed over"),
    "not_attempted": "the writer never ran — an arming or wiring problem, not the model",
}

#: Reason families whose suffix is a PROVIDER NAME (as opposed to an exception
#: type or a make_call reason). Only these may be read as "which rung broke".
_PROVIDER_TAGGED_FAMILIES = frozenset({"provider_no_text"})


def _drop_reason_family(reason: str) -> str:
    """`provider_no_text:deepseek` -> `provider_no_text`; anything else unchanged.

    Legacy reasons carry no suffix and several contain no colon at all
    ("provider returned no text"), so the split has to be conditional on the
    head naming a family this module knows. Splitting unconditionally would
    rewrite "writer_exception:APIConnectionError" into a bucket whose remedy
    cannot name the exception, which is the one useful thing it carries.
    """
    head = str(reason).split(":", 1)[0]
    return head if head in _PROVIDER_DROP_REMEDY else str(reason)


def _is_provider_reason(reason: str) -> bool:
    """True for any reason the provider-stage remedy table can speak to."""
    return (_drop_reason_family(reason) in _PROVIDER_DROP_REMEDY
            or str(reason).startswith("writer_exception:"))


def _provider_remedy(reasons: dict[str, int]) -> str:
    """The remedy for whichever provider-stage reason actually dominated."""
    known = {r: n for r, n in (reasons or {}).items() if _is_provider_reason(r)}
    if not known:
        return ""
    worst = str(max(known, key=lambda r: known[r]))
    if worst.startswith("writer_exception:"):
        return (f"the writer RAISED ({worst.split(':', 1)[1]}) on most items — a "
                f"code or transport fault, not a credential")
    return _PROVIDER_DROP_REMEDY[_drop_reason_family(worst)]


def _dominant_provider_fault(reasons: dict[str, int]) -> tuple[str, str, int]:
    """(reason, provider, count) for the largest provider-family drop reason.

    `provider` is "" unless the winning reason belongs to a family whose suffix
    really is a provider name — naming "ConnectionError" as the provider would
    send an operator looking for a rung that does not exist.
    """
    best_r, best_n = "", 0
    for r, n in (reasons or {}).items():
        try:
            n = int(n or 0)
        except (TypeError, ValueError):
            continue
        if n <= best_n or not _is_provider_reason(str(r)):
            continue
        best_r, best_n = str(r), n
    if not best_r:
        return "", "", 0
    provider = ""
    if _drop_reason_family(best_r) in _PROVIDER_TAGGED_FAMILIES and ":" in best_r:
        provider = best_r.split(":", 1)[1].strip()
    return best_r, provider, best_n


def _alarm_on_a_planless_night(
    total_posts: int,
    copy_dropped: dict[str, int],
    n_charts: int,
    sel_report: dict | None = None,
    copy_drop_reasons: dict[str, int] | None = None,
) -> None:
    """A plan that produced NO POSTS must say so, loudly, and name the stage.

    THE NIGHT THIS EXISTS FOR (2026-07-31, in production). The nightly wrote:

        summary.total_posts : 0
        summary.charts      : 102
        content.copy.dropped: {"provider": 914, "validate": 1}

    915 posts were planned, 914 died because the LLM provider never answered,
    the desks had nothing to publish, and 102 headless-Chrome cards were
    rastered for them anyway — charts are drawn BEFORE the writer runs, so the
    render budget is spent whether or not any copy survives.

    WHAT DID AND DID NOT EXIST. The copywriter's own per-desk warning DID fire —
    six times, once per enabled account ("The planned-copy lane dropped 166 of
    166 posts (100%...)"). What was missing is the whole-plan fact. Six warnings
    scattered through a 24,000-line nightly log, each true about one desk, never
    add up to "there is nothing to publish tomorrow" in the reader's head, and
    the run still concluded green. `_copy_dropped` held the total the entire time
    at content.copy.dropped and nothing looked at it.

    So this is an AGGREGATE and an ESCALATION, not the first alarm: it fires once,
    at ::error, only when the plan as a whole came out empty. The publisher has
    had the same shape on its side for a while (`::error
    title=marketing-zero-posted`); the plan side, where the supply is created,
    had per-part warnings and no whole.

    It also names the remedy. The per-desk line says "a provider-stage spike is a
    credential or quota problem", which still leaves the reader to map that onto
    an env var — and on 2026-07-31 it was misleading besides: credentials were
    fine and DeepSeek was answering, it just answered with no text because its
    thinking consumed max_tokens (see llm_auth._deepseek_no_thinking). Naming the
    variables costs nothing when the guess is right and is quickly falsified when
    it is wrong, which is the better failure of the two.

    AND IT NOW CARRIES THE OUTAGE BREAKER. The same fault ran on 07-30 and again
    on 07-31 shape-for-shape, because a plan that came out empty is only ONE of
    the ways a provider fault shows up — and the loudest one. A night where the
    provider eats 60% of the plan still ships 40% of it, still reports
    total_posts > 0, and used to say so at ::warning. The breaker below keys on
    the PROVIDER share alone, escalates to ::error, and names the rung — see
    `_PROVIDER_OUTAGE_SHARE`.
    """
    dropped = {str(k): int(v) for k, v in (copy_dropped or {}).items() if int(v or 0) > 0}
    n_dropped = sum(dropped.values())
    considered = total_posts + n_dropped
    if not considered:
        return

    worst = max(dropped, key=lambda k: dropped[k]) if dropped else ""
    remedy = _COPY_DROP_REMEDY.get(worst, "check content.copy.dropped in the plan")
    if worst == "provider":
        # Prefer the reason over the stage: they point at different subsystems.
        remedy = _provider_remedy(copy_drop_reasons or {}) or remedy
    detail = ", ".join(f"{k}={v}" for k, v in sorted(dropped.items(), key=lambda kv: -kv[1]))
    reasons = {str(k): int(v) for k, v in (copy_drop_reasons or {}).items()
               if int(v or 0) > 0}
    if reasons:
        top = sorted(reasons.items(), key=lambda kv: -kv[1])[:3]
        detail += "; reasons: " + ", ".join(f"{k}={v}" for k, v in top)

    # ── THE OUTAGE BREAKER ────────────────────────────────────────────────────
    # Fires on the PROVIDER share alone, ahead of either branch below, because
    # the two questions are different and only one of them is actionable
    # tonight: "is there anything to publish" (plan-empty) versus "is the supply
    # chain broken, and which rung" (this). On a dark night both are true and
    # both print — two annotations with different titles, not two spellings of
    # one fact. There is deliberately NO template fallback attached: the
    # no-fallback law is an editorial ruling and it stands. The breaker's whole
    # job is to be loud enough that the per-item retry/failover in
    # engine/marketing/copywriter.py is not the only thing standing between a
    # provider fault and a second silent night.
    provider_n = dropped.get("provider", 0)
    provider_share = provider_n / considered
    tripped = provider_share > _PROVIDER_OUTAGE_SHARE
    if tripped:
        worst_reason, worst_provider, worst_n = _dominant_provider_fault(reasons)
        print(f"::error title=marketing-provider-outage::"
              f"the copy lane's PROVIDER stage lost {provider_n} of {considered} "
              f"planned posts ({provider_share * 100:.0f}%, breaker trips above "
              f"{_PROVIDER_OUTAGE_SHARE * 100:.0f}%). Dominant reason: "
              f"{worst_reason or 'unrecorded'}"
              f"{f' ({worst_n})' if worst_n else ''}; provider: "
              f"{worst_provider or 'unrecorded'}. Dropped posts are never "
              f"templated, so this is lost supply, not lighter copy. "
              f"{_provider_remedy(reasons) or 'check content.copy.dropped_reasons in the plan'}.",
              flush=True)

    if total_posts == 0:
        # Nothing to publish tomorrow. This is the loudest thing this module says.
        print(f"::error title=marketing-plan-empty::"
              f"the nightly planned ZERO posts. {n_dropped} of {considered} were "
              f"dropped ({detail}) and {n_charts} chart(s) were rastered for posts "
              f"that no longer exist. Most likely: {remedy}.", flush=True)
        return

    share = n_dropped / considered
    # `not tripped`: when the breaker already spoke at ::error, repeating the
    # same census at ::warning is the "two alarms for one cause" this module's
    # docstring warns about — it trains the reader to skim both.
    if share >= _COPY_DROP_ALARM_SHARE and not tripped:
        print(f"::warning title=marketing-copy-drops::"
              f"the writer lost {n_dropped} of {considered} posts "
              f"({share * 100:.0f}%; {detail}). {total_posts} survived. "
              f"Most likely: {remedy}.", flush=True)


#: Share of ALLOCATED rungs the cross-day cooldown may swallow before the night
#: is reported as starved rather than picky. A quarter of the ladder going
#: unfilled means the postable-signal pool is smaller than the plan it is being
#: asked to fill — that is a SUPPLY fact the operator needs, not a bug in the
#: cooldown, and the remedy is more event-driven supply (press wire, hot tape),
#: never a shorter cooldown.
_COOLDOWN_DROP_ALARM_SHARE = 0.25


def _alarm_on_cooldown_starvation(sel_report: dict) -> None:
    """Say out loud when the cooldown emptied a material share of the ladder.

    W4c. `dropped_cooldown` is the largest volume sink in the allocator and it
    lived only in a caller-supplied dict — countable in principle, invisible in
    practice, which is precisely how the movers desk shipped nothing for twelve
    nights while every counter it owned read zero. The count is now persisted
    (plan `summary` + `content.selection`, by account), and a material share
    also gets an annotation, because a number nobody reads is a number nobody
    reads.

    BARE `print`, LINE-START, `flush=True` — never through `log`: this module's
    logger prefixes the level, GitHub drops any annotation that does not start
    the line, and stdout is block-buffered when piped in Actions.
    """
    offered = int(sel_report.get("slots_offered") or 0)
    dropped = int(sel_report.get("dropped_cooldown") or 0)
    if offered <= 0 or dropped <= 0:
        return
    share = dropped / offered
    if share < _COOLDOWN_DROP_ALARM_SHARE:
        return
    by_acct = sel_report.get("dropped_cooldown_by_account") or {}
    worst = sorted(by_acct.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))[:3]
    detail = ", ".join(f"{a}:{n}" for a, n in worst) or "no per-account detail"
    print(f"::warning title=marketing-plan-cooldown-starved::"
          f"the cross-day cooldown emptied {dropped} of {offered} planned rungs "
          f"({share * 100:.0f}%) — every eligible name for those kinds is inside "
          f"its cooldown. Worst desks: {detail}. Supply-honest volume means the "
          f"rung stays empty, so the remedy is MORE event-driven supply (press "
          f"wire top-K, hot tape), never a shorter cooldown.", flush=True)


def _chart_quality_census(featured_charts: list[dict]) -> dict:
    """How many posted images are the REAL card, and how many are the fallback.

    THE SILENCE THIS REPLACES. `legacy_png` is a hand-drawn PIL line chart: no
    candles, no indicators, no footer CTA. It exists so a Chrome-less host (CI,
    the ubuntu publish runner) still posts a picture instead of bare text.

    WHAT PRODUCTION ACTUALLY DOES, measured rather than inferred: the renderers
    are distinguishable by size — legacy is 1200x675, the real card rasters at
    2000x1760. All 21 PNGs the nightly wrote on 2026-07-29
    (data/marketing/outbox/media/2026-07-29/) are 2000x1760. Production ships the
    real card, and this census should read 0% on a healthy night.

    IT WAS STILL WORTH BUILDING, and the reason is the point. A committed
    content_plan.json showed 15 of 23 cards as `legacy_png`, and that one number
    was read three different ways: an audit called it "65% of our images are the
    retired legacy chart"; a refutation counted SVGs on disk, found every one v2,
    and dismissed it (the legacy path emits a PNG — that check cannot observe
    what it was used to rule out); then the 65% was believed as a live production
    failure. All three were reading an artifact a LOCAL run had overwritten,
    where Chrome was contended by parallel work — `git log` on the file names the
    author. Nobody could tell which environment produced it, because the only
    trace of a fallback was a `log.warning` GitHub drops for not starting the
    line, and nothing counted the share.

    So this exists to end the guessing rather than to report a known fire. It
    reads `media_render` — the field that actually records which renderer drew
    the image — and puts the share where the run that produced it is identified.
    A contended local run SHOULD light it up: that is correct behaviour, because
    a degraded local artifact getting committed and then misread three times is
    precisely what happened.
    """
    total = 0
    modes: dict[str, int] = {}
    degraded: list[str] = []
    for fc in featured_charts or []:
        if not isinstance(fc, dict):
            continue
        mode = str(fc.get("media_render") or "")
        if not mode:
            continue          # never rastered (deferred/pruned) — not a quality fact
        total += 1
        modes[mode] = modes.get(mode, 0) + 1
        if mode == "legacy_png":
            degraded.append(str(fc.get("id") or "?"))

    n_legacy = modes.get("legacy_png", 0)
    share = (n_legacy / total) if total else 0.0
    if total and share >= _LEGACY_FALLBACK_ALARM_SHARE:
        print(f"::warning title=marketing-chart-quality::"
              f"{n_legacy} of {total} posted cards ({share * 100:.0f}%) are the "
              f"DEGRADED legacy PNG, not the designed card. The rasteriser is "
              f"Chrome; this is it failing or timing out under load, not a "
              f"Chrome-less host. Affected: {', '.join(degraded[:6])}"
              f"{' …' if len(degraded) > 6 else ''}", flush=True)
    elif total:
        print(f"::notice title=marketing-chart-quality::"
              f"{total - n_legacy} of {total} cards rendered as the real card.",
              flush=True)

    return {
        "rastered": total,
        "by_render": modes,
        "legacy_fallback": n_legacy,
        "legacy_share": round(share, 3),
        "degraded_chart_ids": degraded,
        "note": (
            f"{n_legacy} of {total} cards fell back to the legacy PNG "
            f"(no candles, no indicators, no CTA)."
            if n_legacy else
            f"All {total} cards rendered as the designed card."
        ) if total else "No cards rastered.",
    }


def _confluence_census(
    account_rows: list[dict],
    posts_added: list[dict],
    charts_added: int,
) -> dict:
    """What the confluence lane BUILT vs what actually survived into a queue.

    THE LIE THIS REPLACES. The block reported `fired_combos: len(posts_added)`
    and a note reading "9 confluence signal posts added (8 charts)" — where
    `posts_added` is appended once per item CONSTRUCTED, several stages before
    anything downstream can drop it. On the 2026-07-30 plan it said 9 posts and 8
    charts while ZERO confluence items were in any desk queue and zero had ever
    reached the outbox (provenance census: content_studio 151, weekend_levels 22,
    claude_rewrite 12, movers 4, press 2, hot_tape 19 — no confluence, ever).

    So the operator's console reported a lane as producing nine posts a night
    that has never produced one, while 8 headless-Chrome rasters were spent on
    it against a 67-minute render budget. A built-count masquerading as a
    shipped-count is the tinted window again: it reports OUTPUT and hides the
    LOSS, which is the one thing this console exists to do the other way round.

    Counts survivors from the live queues at report time, so the number cannot
    drift from reality again, and names the gap when there is one.
    """
    built = len(posts_added or [])
    survived = sum(
        1
        for row in (account_rows or [])
        for item in (row.get("queue") or [])
        if str((item or {}).get("source") or "") == "confluence"
    )
    lost = max(0, built - survived)
    if not built:
        note = "No fresh fired confluence combos today; Prophet posts only."
    elif lost:
        # NAME THE BLOCKER, NOT JUST THE GAP (2026-07-30). "Dropped downstream"
        # was true and useless: it described a symptom and left the operator to
        # find the cause, which is how a lane sits dead for its whole existence
        # while reporting nine posts a night.
        #
        # The cause is structural and provable from the code. This lane labels
        # its slots `CONF-NN`, and outbox.emit_from_content_plan skips every item
        # whose slot does not start with `D1-` (one unconditional `continue`).
        # So a confluence post cannot reach the outbox even if it survives every
        # queue filter — which matches the record: zero confluence items in the
        # outbox across its entire history.
        #
        # Deliberately NOT "fixed" by relabelling the slot. That would start
        # publishing copy whose win rate is a selection-on-test-half statistic
        # this lane already had to be corrected about, and the house rule is that
        # a lane earns publication on evidence rather than on a prefix change.
        note = (
            f"{built} confluence post(s) built and {charts_added} chart(s) "
            f"rendered; {survived} reached a desk queue. This lane CANNOT "
            f"publish as built: it slots posts as CONF-NN and "
            f"outbox.emit_from_content_plan emits only D1- slots, so nothing it "
            f"produces has ever reached the outbox. Charts now defer, so the "
            f"render cost is no longer paid for posts that cannot ship."
        )
    else:
        note = f"{survived} confluence signal post(s) live ({charts_added} charts)."
    return {
        # Kept for readers that already parse it, but no longer the headline.
        "fired_combos": built,
        "built": built,
        "surviving": survived,
        "dropped_before_queue": lost,
        "charts": charts_added,
        "orphan_charts": charts_added if survived == 0 else 0,
        "posts": posts_added,
        "note": note,
    }


def drop_stale_forward_bookings(
    account_rows: list[dict],
    *,
    cfg: dict | None = None,
) -> dict[str, Any]:
    """Drop perishable copy booked beyond day N. Mutates queues.

    THE STALE-QUEUE FIX (operator, 2026-07-30: "these posts are things that
    happened yesterday and are stale, we should be posting intraday live
    content; overnight content is usually for stuff that is more evergreen and
    doesn't matter if it's 1 day old").

    The planner books a SEVEN-DAY forward queue, and ~150 cleared posts per plan
    made a decaying market claim scheduled D2-D7. By the time one of those posts
    reached its slot the tape had moved, so the publisher's live-tape gate
    refused it — correctly — and logged `tape_skipped`. That counter fired on
    every sweep of 2026-07-29 and was the reason ZERO posts went out that day.

    The tape gate was never the bug. Pre-writing perishable copy a week ahead
    was. This removes the supply the gate was going to reject anyway, which also
    stops us spending two model calls apiece writing it.

    Evergreen kinds (watchlist levels, receipts, education) keep the full
    horizon: a level that has held 23 sessions still reads true on Friday.
    """
    perish = perishable_kinds(cfg)
    max_day = perishable_max_day(cfg)
    counts: dict[str, Any] = {"dropped_perishable_forward": 0, "by_kind": {}}

    for row in account_rows or []:
        queue = row.get("queue")
        if not isinstance(queue, list):
            continue
        keep = []
        for item in queue:
            kind = str((item or {}).get("type") or "")
            day = _slot_day_num((item or {}).get("slot"))
            # An unparseable slot is NOT assumed fresh — it is left alone, since
            # dropping on a parse failure would silently empty the queue if the
            # ladder label format ever changed.
            if kind in perish and day is not None and day > max_day:
                counts["dropped_perishable_forward"] += 1
                counts["by_kind"][kind] = counts["by_kind"].get(kind, 0) + 1
                continue
            keep.append(item)
        row["queue"] = keep
    return counts


def apply_reuse_budget(
    account_rows: list[dict],
    *,
    cfg: dict | None = None,
    day_prefix: str = "D1",
) -> dict[str, Any]:
    """Enforce the (ticker, day) fact-reuse budget across desks. Mutates queues.

    THE ARES ×5 FIX (masterplan §1, §5.2). The planner splices one plan into
    every desk's queue, so a single fact reached five accounts with the same
    entry and target — the network-linkage fingerprint the Sentinel's
    cross-account near-dup bar exists to deny, arriving by a route that bar
    cannot see (five DIFFERENT wordings of one fact).

    Rules: ≤ `max_accounts_per_ticker_day` accounts per (ticker, day), and
    exactly `max_signal_accounts_per_day` account for signal kinds (a directional
    call with entry/stop numbers is one desk's call or it is a coordinated one).
    Survivors get DISJOINT angles. Losers are removed from the queue — never
    re-typed into filler, because supply-honest volume means an empty rung stays
    empty (§5.5).

    SCOPED TO THE EMITTED DAY. Only `day_prefix` slots ever reach the outbox
    (outbox.emit_from_content_plan defaults to D1 and the governor takes the
    default), so budgeting D2-D7 would delete posts nothing was ever going to
    send while shrinking the plan the admin reviews. Deterministic account order
    = the plan's own account order; no RNG.

    THE FILLER BUDGET rides along here (2026-07-29) for the same reason: the
    no-ticker kinds (macro/event/education) are the ONE class this function used
    to wave through unbudgeted, and the publisher now caps them per desk per day.
    Capping only the publish-time half would have quarantined 5 of flagship's 6
    planned filler posts every night — planned, written by the LLM, charted, then
    killed at the last gate. Trimming here instead means the plan the admin
    reviews is the plan that can post, and an item the budget deletes never costs
    a model call.

    Returns counters: {"before", "after", "dropped_ticker_budget",
    "dropped_signal_budget", "dropped_filler_budget", "angles_assigned"}.
    """
    sel = selection_cfg(cfg)
    max_accts = max(int(sel["max_accounts_per_ticker_day"]), 0)
    max_signal = max(int(sel["max_signal_accounts_per_day"]), 0)
    # ONE reader for the filler key: sentinel owns it, both seams call it, so the
    # plan side and the publisher cannot disagree about the number. Fail-soft —
    # an unimportable sentinel leaves the filler budget off, never crashes a plan
    # (an empty kind set makes the branch below unreachable on its own).
    max_filler: int | None = None
    filler_kinds: frozenset[str] = frozenset()
    try:
        from engine.marketing.sentinel import (  # noqa: PLC0415
            FILLER_KINDS, max_filler_per_account_per_day)
        filler_kinds = FILLER_KINDS
        max_filler = max_filler_per_account_per_day(cfg)
    except Exception:  # noqa: BLE001
        max_filler = None

    counts = {"before": 0, "after": 0, "dropped_ticker_budget": 0,
              "dropped_signal_budget": 0, "dropped_filler_budget": 0,
              "angles_assigned": 0}

    # (ticker, day) → accounts already holding it; (ticker, day) → signal holders
    held: dict[tuple[str, str], list[str]] = {}
    signal_held: dict[tuple[str, str], list[str]] = {}
    # account → filler posts already kept on the emitted day
    filler_kept: dict[str, int] = {}

    for acct_row in account_rows or []:
        acct_id = str(acct_row.get("id") or "")
        queue = acct_row.get("queue") or []
        counts["before"] += len(queue)
        kept: list[dict] = []
        for item in queue:
            ticker = str(item.get("ticker") or "").upper()
            slot_day = _slot_day(item.get("slot"))
            kind = str(item.get("type") or "")
            if not ticker or slot_day != day_prefix:
                # A ticker-less planned post (macro/education/event) is never
                # in contention for a fact, but it still has a JOB — and the
                # writer, the emit provenance and the learning lane all read the
                # angle, so it is stamped rather than left blank.
                if not ticker and slot_day == day_prefix and kind in PLANNED_KINDS:
                    # Filler budget: one macro/event/education post per desk per
                    # emitted day (sentinel.max_filler_per_account_per_day).
                    if kind in filler_kinds and max_filler is not None:
                        if filler_kept.get(acct_id, 0) >= max_filler:
                            counts["dropped_filler_budget"] += 1
                            continue
                        filler_kept[acct_id] = filler_kept.get(acct_id, 0) + 1
                    item["angle"] = angle_for(kind, 0)
                    counts["angles_assigned"] += 1
                kept.append(item)
                continue

            key = (ticker, slot_day)
            holders = held.setdefault(key, [])
            if kind == "signal":
                sig = signal_held.setdefault(key, [])
                if acct_id not in sig and len(sig) >= max_signal:
                    counts["dropped_signal_budget"] += 1
                    continue
            if acct_id not in holders and len(holders) >= max_accts:
                counts["dropped_ticker_budget"] += 1
                continue

            if acct_id not in holders:
                holders.append(acct_id)
            if kind == "signal" and acct_id not in signal_held.setdefault(key, []):
                signal_held[key].append(acct_id)

            item["angle"] = angle_for(kind, holders.index(acct_id))
            counts["angles_assigned"] += 1
            kept.append(item)

        acct_row["queue"] = kept
        counts["after"] += len(kept)

    return counts


# ── Shape mixer (masterplan §4, §0 gate 4) ────────────────────────────────────
# The 2026-07-29 batch was 65/65 headline + 2-4 clipped sentences. In the real
# fintwit corpus that exact shape is the RAREST at 2.8%: ~49% of real posts are
# one dense line, ~17% headline+blank+body, ~34% multi-line stacks. Shape is
# therefore ENFORCED here, not requested politely in a prompt — a model asked to
# "vary the shape" converges on one skeleton within a batch, every time.

_DEFAULT_ONE_LINER_MIN = 0.25
_DEFAULT_TWO_PART_MAX = 0.30

#: Rotation order. one_liner leads because it is the corpus default shape.
_SHAPE_ROTATION: tuple[str, ...] = ("one_liner", "stack", "two_part", "list")


def shape_quotas(cfg: dict | None) -> tuple[float, float]:
    """(one_liner_min, two_part_max) from `shapes.quotas`, with fallbacks."""
    raw = (((cfg or {}).get("shapes") or {}).get("quotas") or {}) if isinstance(cfg, dict) else {}

    def _f(key: str, default: float) -> float:
        try:
            v = float(raw.get(key, default))
        except (TypeError, ValueError):
            return default
        return v if 0.0 <= v <= 1.0 else default

    return (_f("one_liner_min", _DEFAULT_ONE_LINER_MIN),
            _f("two_part_max", _DEFAULT_TWO_PART_MAX))


def _rotation_offset(account: str, as_of: str) -> int:
    """Deterministic rotation seed for (account, day). NO RNG, NO clock read.

    sha256 over the pair, exactly like _account_hash: two desks on the same night
    start the rotation at different shapes, and the same desk re-planned on the
    same date lands on the identical mix (the property that lets a plan be
    diffed night over night).
    """
    h = hashlib.sha256(f"{account}|{str(as_of)[:10]}".encode()).hexdigest()
    return int(h[:8], 16)


def shape_plan(
    n: int,
    *,
    account: str,
    as_of: str,
    cfg: dict | None = None,
    prior_mix: dict[str, int] | None = None,
) -> list[str]:
    """The ordered shape assignment for ``n`` posts of one (account, day).

    Quotas (contract §Selection): one_liner ≥ 25%, two_part ≤ 30%, at least one
    stack once the day carries ≥4 posts. Whatever is left goes to the shape the
    account has leaned on LEAST over the 14-day ledger window (`prior_mix`) —
    that is the anti-streak mechanism, and it is a deterministic tie-break, not
    a jitter.
    """
    if n <= 0:
        return []
    one_min, two_max = shape_quotas(cfg)

    # one_liner_min is a FLOOR so it rounds UP; two_part_max is a CEILING so it
    # rounds DOWN. Getting either rounding backwards silently breaks the quota
    # the gate measures.
    n_one = max(math.ceil(n * one_min), 1)
    n_two = math.floor(n * two_max)
    n_stack = 1 if n >= 4 else 0
    n_one = min(n_one, n)
    n_two = min(n_two, max(n - n_one - n_stack, 0))
    n_stack = min(n_stack, max(n - n_one - n_two, 0))

    remainder = n - (n_one + n_two + n_stack)
    counts = {"one_liner": n_one, "two_part": n_two, "stack": n_stack, "list": 0}
    if remainder > 0:
        # Least-used-first over the ledger window, alphabetical on ties.
        pool = sorted(
            ("stack", "list", "one_liner"),
            key=lambda s: ((prior_mix or {}).get(s, 0), s),
        )
        for i in range(remainder):
            counts[pool[i % len(pool)]] += 1

    # Deterministic interleave: walk the rotation from the (account, day) offset
    # so a day never opens with the same shape twice running.
    order = list(_SHAPE_ROTATION)
    off = _rotation_offset(account, as_of) % len(order)
    order = order[off:] + order[:off]

    out: list[str] = []
    while len(out) < n:
        progressed = False
        for shape in order:
            if counts.get(shape, 0) > 0:
                out.append(shape)
                counts[shape] -= 1
                progressed = True
                if len(out) == n:
                    break
        if not progressed:  # defensive: counts exhausted early
            out.extend(["one_liner"] * (n - len(out)))
    return out


def assign_shapes(
    queue: list[dict],
    *,
    account: str,
    as_of: str,
    cfg: dict | None = None,
    prior_mix: dict[str, int] | None = None,
) -> dict[str, int]:
    """Stamp `shape` on every queue item, per (account, day). Returns the mix.

    `caption` is assigned ONLY to a chart-bearing item and only where the mixer
    wanted a one_liner — a caption with no image is a post with no content
    (contract §Shapes: "REQUIRES media attached at emit"). Publish-time reach
    items (mover/theme_list) are left alone: they are wire register with their
    own template banks and no shape contract. The exclusion is by KIND (the
    `PLANNED_KINDS` test below), not by slot — reach items now sit on real D1
    ladder rungs like everything else, because a non-D slot cannot be emitted.
    """
    by_day: dict[str, list[dict]] = {}
    for item in queue or []:
        day = _slot_day(item.get("slot"))
        if not day or str(item.get("type") or "") not in PLANNED_KINDS:
            continue
        by_day.setdefault(day, []).append(item)

    # THE ENGAGEMENT LOOP'S ONE MISSING JOINT (2026-07-31).
    #
    # The learning lane harvests labels, scores cells and writes a scorecard
    # nightly; `learned_rules` turns a cell into an applicable rule with a
    # promotion gate on it. `reply_producer` consults that seam for
    # `reply_family`. THE POST PATH CONSULTED IT FOR NOTHING — content_studio
    # referenced neither the scorecard nor learned_rules, so everything measured
    # about which posts work reached replies and stopped. `format_preference`
    # has been in learned_rules.KINDS the whole time with no reader.
    #
    # DARK BY CONSTRUCTION, AND NOT BY MY JUDGEMENT. `active_for` returns [] when
    # `learning.learned_rules.enabled` is false (the default), and its own
    # docstring is explicit that a caller "therefore needs no flag check of its
    # own and cannot forget one". The promotion gate underneath it is stricter
    # than anything I would have invented: min_evidence_n=30 and the cell must
    # have cleared the labels n-floor. Today that is 0 of 18 cells, so this is a
    # no-op — which is correct, not a reason to leave the joint unbuilt. It arms
    # itself when the evidence arrives instead of waiting for someone to notice.
    #
    # It may only NARROW. A learned preference removes shapes from the mixer's
    # menu; it can never invent one, and it can never empty the menu (an empty
    # intersection falls back to the full set). That keeps this a filter on a
    # deterministic plan rather than a model choosing the day's content — the
    # house line between display-tier and authority.
    _allowed = _learned_shape_preference(account=account, cfg=cfg)

    mix: dict[str, int] = {}
    for day in sorted(by_day, key=lambda d: (len(d), d)):
        items = by_day[day]
        shapes = shape_plan(len(items), account=account, as_of=f"{as_of}|{day}",
                            cfg=cfg, prior_mix=prior_mix)
        for item, shape in zip(items, shapes):
            if _allowed and shape not in _allowed:
                shape = _allowed[0]
            if shape == "one_liner" and item.get("chart_id"):
                shape = "caption"
            item["shape"] = shape
            mix[shape] = mix.get(shape, 0) + 1
    return mix


def _learned_shape_preference(*, account: str, cfg: dict | None) -> list[str]:
    """Shapes an ARMED, EVIDENCED learned rule allows for this account.

    [] means "no opinion" — which is the answer whenever consumption is disarmed
    (the default), no rule has cleared the promotion gate, or anything at all
    goes wrong. Never raises: a learning lane that cannot answer must not be able
    to stop a plan from being built.
    """
    try:
        from engine.marketing import learned_rules as _lr  # noqa: PLC0415

        allowed: list[str] = []
        for rule in _lr.active_for("format_preference", account=account, cfg=cfg):
            value = rule.get("value")
            if isinstance(value, list):
                allowed.extend(str(v) for v in value)
        # Intersect with the shapes the mixer can actually produce, preserving
        # the rule's own order. A rule naming a shape we do not have is dropped
        # rather than honoured into a KeyError.
        return [s for s in dict.fromkeys(allowed) if s in SHAPES]
    except Exception as exc:  # noqa: BLE001
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "content_studio: learned shape preference unavailable (%s)", exc)
        return []


# ── 14-day shape ledger (nightly-only write) ──────────────────────────────────

_SHAPE_LEDGER_REL = Path("data") / "marketing" / "shape_ledger.json"
_SHAPE_LEDGER_DAYS = 14


def shape_ledger_path(root: str | Path | None) -> Path:
    return (Path(root) if root is not None else Path(".")) / _SHAPE_LEDGER_REL


def load_shape_ledger(root: str | Path | None) -> dict:
    """Read the rolling shape ledger. {} on any error (the mixer degrades to its
    quota math, which is the whole contract — the ledger only breaks ties)."""
    try:
        import json  # noqa: PLC0415
        p = shape_ledger_path(root)
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def shape_ledger_prior_mix(ledger: dict, account: str) -> dict[str, int]:
    """Summed per-shape counts for one account across the ledger window."""
    out: dict[str, int] = {}
    for row in (ledger or {}).get("days") or []:
        if not isinstance(row, dict):
            continue
        for shape, n in ((row.get("accounts") or {}).get(account) or {}).items():
            try:
                out[str(shape)] = out.get(str(shape), 0) + int(n)
            except (TypeError, ValueError):
                continue
    return out


def record_shape_ledger(
    root: str | Path | None,
    *,
    as_of: str,
    mix_by_account: dict[str, dict[str, int]],
    keep_days: int = _SHAPE_LEDGER_DAYS,
) -> Path | None:
    """Append tonight's shape mix and trim to the last ``keep_days`` days.

    NIGHTLY ONLY (contract §House laws: "shape_ledger.json written in the
    nightly governor step only"). content_plan writes it exclusively when its
    caller passes `write_shape_ledger=True`, which only the governor does — a
    test or an admin preview that happened to pass a real root must never
    advance an ops file. Fail-soft: returns None on any write error.
    """
    try:
        import json  # noqa: PLC0415
        day = str(as_of)[:10]
        ledger = load_shape_ledger(root)
        days = [d for d in (ledger.get("days") or [])
                if isinstance(d, dict) and str(d.get("as_of") or "")[:10] != day]
        days.append({"as_of": day, "accounts": mix_by_account})
        days = sorted(days, key=lambda d: str(d.get("as_of") or ""))[-max(keep_days, 1):]
        out = {
            "schema_version": 1,
            "produced_by": "engine/marketing/content_studio.py",
            "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tier": "display",
            "schema": "marketing.shape_ledger/v1",
            "as_of": day,
            "window_days": keep_days,
            "days": days,
        }
        p = shape_ledger_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        return p
    except Exception as exc:  # noqa: BLE001
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "content_studio.record_shape_ledger: %s", exc)
        return None


def load_hot_tape_pack(root: str | Path | None) -> dict[str, dict]:
    """ticker → context-pack slice from `data/marketing/hot_tape_pack.json`.

    DEPENDENCY-INVERTED (masterplan §4): a read-only join on a file the Hot Tape
    radar (#3941) writes, with no import of radar code and no failure when the
    file is absent — the pack is enrichment (streak rarity, 52w distance,
    since-dates), never a prerequisite. {} when missing or malformed.
    """
    try:
        import json  # noqa: PLC0415
        p = (Path(root) if root is not None else Path(".")) / "data" / "marketing" / "hot_tape_pack.json"
        if not p.exists():
            return {}
        raw = json.loads(p.read_text(encoding="utf-8")) or {}
        blob = raw.get("tickers") if isinstance(raw.get("tickers"), dict) else raw
        return {str(k).upper(): v for k, v in blob.items() if isinstance(v, dict)}
    except Exception:  # noqa: BLE001
        return {}


def llm_required(cfg: dict | None) -> bool:
    """Is the no-fallback law armed? (`copywriter.llm.required`, contract §Config)

    §0 gate 1: while this is true a planned-kind post whose model copy failed is
    DROPPED, never template-filled, and outbox.emit refuses any planned item
    whose mode is not llm*.

    THE MISSING-BLOCK RULE, stated plainly: the key defaults to TRUE whenever a
    `copywriter.llm` block exists (so deleting the key cannot silently disarm the
    gate), and to FALSE when a caller ships no copywriter config at all — such a
    caller is not running the writer lane, and refusing its hand-built items
    would be refusing posts no writer was ever asked to write. The live
    `config/marketing.yml` always carries the block, and
    tests/test_marketing_selection.py pins that it carries `required: true`, so
    production can never take the false branch by accident.

    Parsed strictly (a quoted "false" must not enable), mirroring
    scripts/marketing_publisher._auto_approve_cfg.
    """
    cw = (cfg or {}).get("copywriter") if isinstance(cfg, dict) else None
    llm = (cw or {}).get("llm") if isinstance(cw, dict) else None
    if not isinstance(llm, dict):
        return False
    v = llm.get("required", True)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes"}


# ─────────────────────────────────────────────────────────────────────────────
# Largest-remainder allocation (no RNG)
# ─────────────────────────────────────────────────────────────────────────────

def _largest_remainder(weights: dict[str, float], total_slots: int) -> dict[str, int]:
    """Allocate *total_slots* slots across types by largest-remainder method.

    Ensures all types with weight > 0 get at least 1 slot (if slots allow),
    then distributes the remainder by largest fractional part.
    """
    type_ids = list(weights.keys())
    raw = {t: weights[t] * total_slots for t in type_ids}
    floors = {t: int(raw[t]) for t in type_ids}
    remainder = total_slots - sum(floors.values())

    # Sort by fractional part descending (stable, alphabetical on ties)
    fracs = sorted(type_ids, key=lambda t: (-(raw[t] - floors[t]), t))
    for i in range(remainder):
        floors[fracs[i % len(fracs)]] += 1

    # Every type with weight > 0 gets at least one slot when the ladder is long
    # enough to hold one of each.
    #
    # THIS USED TO BE DEAD CODE. The remainder pass above always lands
    # `sum(floors) == total_slots`, so the `< total_slots` condition it was
    # guarded by could never be true: the guarantee this docstring makes was
    # carried entirely by the allocation being 196 slots wide, where every
    # weight ≥ 0.03 floors to 1 on its own. Collapsing the ladder to ONE day
    # (W4a) made a 20-rung allocation the normal case, and a 0.05-weight kind
    # rounds to zero there — a whole content family silently leaving the plan.
    #
    # ZERO-WEIGHT TYPES ARE NOT RESURRECTED. 0.00 means OFF, not "rare":
    # education sits at 0.00 by operator ruling (2026-07-30, see _DEFAULT_TILT),
    # and handing it a slot here would reopen a family the operator closed.
    positive = [t for t in type_ids if weights.get(t, 0) > 0]
    if len(positive) <= total_slots:
        for t in positive:
            if floors[t] > 0:
                continue
            # Take from the fattest donor, ties broken by name so the allocation
            # stays deterministic (re-planning a night must reproduce it).
            donor = max((tt for tt in positive if floors[tt] > 1),
                        default=None, key=lambda tt: (floors[tt], tt))
            if donor is None:
                break
            floors[donor] -= 1
            floors[t] = 1

    return floors


# ─────────────────────────────────────────────────────────────────────────────
# Slot labels
# ─────────────────────────────────────────────────────────────────────────────

# The 45-minute Pacific ladder slots (cadence masterplan §5, operator re-spec
# 2026-07-27); outbox._LADDER_PT_TIMES resolves each to a real per-date UTC time
# via zoneinfo. 19 slots at 45-min steps, 4:00 AM–5:30 PM PT.
# Mirrors outbox._LADDER_PT_TIMES — 28 rungs at 30-min steps (operator
# re-spec 2026-07-28). The clock table lives in ONE place (outbox); this
# side only needs labels. A mismatch shows up as a slot whose scheduled_at
# resolves to None, which tests/test_marketing_outbox.py pins.
_LADDER_SLOTS = [f"S{i}" for i in range(1, 29)]


def _slot_labels(n_days: int, per_day: int) -> list[str]:
    """Generate ladder slot labels D1-S1, D1-S2, ..., D2-S1, ... — the 45-minute
    Pacific ladder. ``per_day`` slots are taken from the front of the ladder, so
    per_day=19 uses the full 4:00 AM–5:30 PM span; fewer packs the earliest
    slots."""
    labels = []
    for day in range(1, n_days + 1):
        for i in range(per_day):
            labels.append(f"D{day}-{_LADDER_SLOTS[i % len(_LADDER_SLOTS)]}")
    return labels


# ─────────────────────────────────────────────────────────────────────────────
# Ladder SHAPE — how many forward days, and how many rungs on each (W4a)
# ─────────────────────────────────────────────────────────────────────────────

#: Forward ladder days the planner books. ONE, because nothing reads a previous
#: plan: `content_plan` rebuilds the whole ladder every night from
#: `plan_account`, and `outbox.emit_from_content_plan` takes only `D1-` slots
#: (outbox.py:2199 — its own comment says D2..D7 "are supposed to be skipped").
#: The 7-day ladder therefore threw away 6/7 of everything it produced BY
#: CONSTRUCTION, and it did not throw it away evenly: the cross-day cooldown
#: pool below is applied to the EMITTED day only, so an empty cooled pool
#: dropped a D1 rung while the never-published days kept filling from the
#: uncooled pool. Measured 2026-08-02: 1,176 items planned, 168 on D1.
#: (masterplan §8.1 V1 / §8.2 W4a)
_DEFAULT_FORWARD_DAYS = 1

#: `per_day` is sized to the account's own ramp cap times this factor, not to a
#: flat 28. The headroom exists because the gates BELOW the allocator (fact-reuse
#: budget, filler budget, the writer) reject some of what is planned — measured
#: 2026-08-02, ~65% of planned D1 rungs survive the reuse budget — so a desk
#: capped at 10 posts/day needs ~20 rungs offered to fill its day. Above 2.0 the
#: extra rungs are mostly eaten by the reuse budget rather than reaching a post
#: (measured: headroom 2.0 → 128 items planned / 81 D1 survivors; 2.8 → 168 /
#: 89), which is the "generating 28 to publish 10" waste in miniature.
_DEFAULT_PER_DAY_HEADROOM = 2.0

#: STRUCTURAL floor on the rung count, independent of any cap: the allocator
#: cannot express a nine-kind tilt in fewer than nine rungs, and below it whole
#: content families leave the plan silently (`_largest_remainder`'s ≥1
#: guarantee needs one rung per positive-weight kind).
#:
#: It exists because the in-code sentinel default is 2/day — a LAUNCH FLOOR, not
#: a working cadence — so any caller without a `sentinel:` block (a test, an
#: admin preview, a fixture config) would otherwise be handed a 4-rung plan
#: carrying four of the nine kinds. Against the shipped config this floor never
#: binds: the tiers are 10/14/20, so `cap × headroom` is 20 or 28 everywhere.
_MIN_LADDER_RUNGS = len(_TYPE_IDS)


def forward_days(cfg: dict | None) -> int:
    """``content_plan.forward_days`` — ladder days to book. Floor 1, default 1.

    Read defensively so this works with OR without the config key present: a
    missing/unparseable/absurd value takes the code default rather than
    reintroducing the 7-day ladder by accident.
    """
    raw = ((cfg or {}).get("content_plan") or {}).get(
        "forward_days", _DEFAULT_FORWARD_DAYS)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_FORWARD_DAYS
    return n if n >= 1 else _DEFAULT_FORWARD_DAYS


def per_day_headroom(cfg: dict | None) -> float:
    """``content_plan.per_day_headroom`` — ramp-cap multiplier. Floor 1.0."""
    raw = ((cfg or {}).get("content_plan") or {}).get(
        "per_day_headroom", _DEFAULT_PER_DAY_HEADROOM)
    try:
        h = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_PER_DAY_HEADROOM
    return h if h >= 1.0 else _DEFAULT_PER_DAY_HEADROOM


def ladder_shape_for(
    cfg: dict | None,
    account_id: str,
    as_of: str,
    *,
    root: Path | str | None = None,
    ramp: dict | None = None,
) -> dict[str, int]:
    """``{"n_days", "per_day"}`` for ONE account's slice of the ladder.

    ``per_day`` = ceil(that account's D08 ramp cap × ``per_day_headroom``),
    floored at `_MIN_LADDER_RUNGS` and clamped to the 28-rung ladder. An
    UNLIMITED cap (-1, which is what the base sentinel block carries) means the
    ladder length itself — there is no cap to size against, so nothing is
    trimmed.

    Pass ``ramp`` (a ``sentinel.resolve_ramp`` result) when calling this in a
    loop; otherwise every account re-resolves the tier table. Fail-soft: any
    resolution error falls back to the full ladder, which is the pre-W4a
    behaviour and never silently shrinks a desk's day.

    NOTE ON SPACING. Trimming ``per_day`` packs the EARLIEST rungs (see
    `_slot_labels`), and that costs no coverage: the Sentinel's
    `cadence_cap_daily` scan is first-come-first-kept in queue order, so the
    rungs that survive to post were already rungs 1..cap. A per_day at or above
    the cap therefore leaves the posting window byte-identical.
    """
    n_days = forward_days(cfg)
    ladder = len(_LADDER_SLOTS)
    try:
        from engine.marketing.outbox import effective_cap_for  # noqa: PLC0415
        cap = effective_cap_for(cfg or {}, str(account_id), str(as_of),
                                root=root, ramp=ramp)
    except Exception as exc:  # noqa: BLE001 — sizing must never break a plan
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "content_studio.ladder_shape_for(%r): %s — full ladder", account_id, exc)
        return {"n_days": n_days, "per_day": ladder}
    if cap is None or cap < 0:
        return {"n_days": n_days, "per_day": ladder}
    per_day = min(ladder, max(_MIN_LADDER_RUNGS,
                              math.ceil(cap * per_day_headroom(cfg))))
    return {"n_days": n_days, "per_day": per_day}


# ─────────────────────────────────────────────────────────────────────────────
# Ramp FORMAT permissions — which kinds this account's tier may ship (W4b)
# ─────────────────────────────────────────────────────────────────────────────

#: content kind -> the ramp-tier boolean that decides whether the account may
#: ship that FORMAT AT ALL. A kind listed here gets ZERO allocation on a tier
#: that forbids it, instead of an allocation that dies at the gate.
#:
#: WHY THIS IS THE WHOLE LIST (audited 2026-08-02 against sentinel.gate_plan and
#: sentinel._base_caps; do not add a knob here without a gate that kills the
#: format):
#:   * `theme_list_allowed` → `ramp_theme_list` (sentinel.py:1383) quarantines
#:     the format outright on a cold tier. Kelly's ONE D1 at-bat on 2026-08-02
#:     was a theme_list on a `weeks_1_2` tier — spent on a banned format.
#:   * `links_allowed` → gates a LINK, not a kind. `links.attach_links` writes
#:     `item["link"]` as a FIELD, sentinel's link rule (sentinel.py:1347) reads
#:     headline+body only, and `emit_from_content_plan` never copies the field
#:     onto the outbox item (verified: 0 of the ledger's items carry `link`).
#:     No planned kind is unshippable because links are off.
#:   * `max_cashtags_per_post` → theme_list is EXEMPT from the breadth count by
#:     construction (sentinel.py:1365: the format requires ≥4 member cashtags,
#:     so counting them would quarantine the format itself), and no other kind
#:     emits more than one cashtag. Breadth bans no kind.
#:   * `max_posts_/max_media_posts_/max_same_cashtag_per_account_per_day`,
#:     `min_minutes_between_posts`, `max_replies_/max_new_follows_` → VOLUME
#:     caps, not format permissions. `ladder_shape_for` above sizes against the
#:     first one; the rest bound cadence, never a kind.
_RAMP_KIND_PERMISSION: dict[str, str] = {"theme_list": "theme_list_allowed"}


def ramp_banned_kinds(caps: dict | None) -> frozenset[str]:
    """Content kinds this resolved cap set forbids OUTRIGHT.

    Strict read: only an explicit ``False`` bans. A missing key is "no opinion"
    (a pre-ramp config), never a ban — inventing a ban from an absent key would
    silently delete a format network-wide.
    """
    if not isinstance(caps, dict) or not caps:
        return frozenset()
    return frozenset(
        kind for kind, flag in _RAMP_KIND_PERMISSION.items()
        if caps.get(flag) is False
    )


def ramp_banned_kinds_for(
    cfg: dict | None,
    account_id: str,
    as_of: str,
    *,
    root: Path | str | None = None,
    ramp: dict | None = None,
) -> frozenset[str]:
    """`ramp_banned_kinds` for ONE account, resolving its tier if needed.

    Fail-soft to "nothing banned" — the pre-W4b behaviour. Failing CLOSED here
    would delete a whole format from every desk on any resolution hiccup, which
    is a bigger, quieter change than the one this guard exists to make.
    """
    try:
        if ramp is None:
            from engine.marketing.sentinel import resolve_ramp  # noqa: PLC0415
            ramp = resolve_ramp(cfg or {}, as_of, root=root, announce=False)
        entry = (ramp.get("accounts") or {}).get(str(account_id))
        caps = entry.get("caps") if entry else (ramp.get("fallback") or {})
    except Exception as exc:  # noqa: BLE001 — never break a plan on a tier read
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "content_studio.ramp_banned_kinds_for(%r): %s — nothing banned",
            account_id, exc)
        return frozenset()
    return ramp_banned_kinds(caps)


# ─────────────────────────────────────────────────────────────────────────────
# ContentItem
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ContentItem:
    id: str
    type: str
    account: str
    cashtag: str
    ticker: str
    headline: str
    body: str
    provenance: str
    chart_id: str | None
    slot: str
    status: str = "drafted"
    # Optional confluence provenance fields (additive; absent on Prophet-sourced items)
    source: str | None = None
    combo_id: str | None = None
    # W1 selection/mixer stamps (contract §Selection, §Emit). NOT underscore-
    # prefixed on purpose: like `watch_reason`, they must survive
    # strip_scaffolding into content_plan.json, because outbox.emit copies them
    # into the item's source provenance and the learning lane (W1.5 per-shape
    # engagement table) joins on them.
    shape: str | None = None
    angle: str | None = None

    def as_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "type": self.type,
            "account": self.account,
            "cashtag": self.cashtag,
            "ticker": self.ticker,
            "headline": self.headline,
            "body": self.body,
            "provenance": self.provenance,
            "chart_id": self.chart_id,
            "slot": self.slot,
            "status": self.status,
        }
        if self.source is not None:
            d["source"] = self.source
        if self.combo_id is not None:
            d["combo_id"] = self.combo_id
        if self.shape is not None:
            d["shape"] = self.shape
        if self.angle is not None:
            d["angle"] = self.angle
        return d


# ─────────────────────────────────────────────────────────────────────────────
# plan_account
# ─────────────────────────────────────────────────────────────────────────────

def plan_account(
    account: dict,
    plans: list[dict],
    *,
    n_days: int = _DEFAULT_FORWARD_DAYS,
    per_day: int = 28,   # 28-slot 30-min Pacific ladder (was 19 = 45-min)
    seed: int = 0,
    tilt: dict[str, float] | None = None,
    drop_types: set[str] | None = None,
    banned_kinds: frozenset[str] | set[str] | None = None,
    cooled_watch: frozenset[str] | set[str] | None = None,
    cooled_signal: frozenset[str] | set[str] | None = None,
    emit_day_prefix: str = "D1",
    report: dict | None = None,
) -> list[ContentItem]:
    """Generate a deterministic content queue for one account.

    account: {id, voice, kind, ...}
    plans:   list of Prophet plan dicts
    n_days:  forward ladder days. ONE by default (W4a) — see `forward_days` and
                `_DEFAULT_FORWARD_DAYS`: nothing reads a previous plan, and the
                outbox takes only `D1-` slots, so every extra day is generated
                and discarded. The caller threads `content_plan.forward_days`.
    per_day: rungs booked on each day. `ladder_shape_for` sizes this to the
                account's own ramp cap × headroom; a caller that passes a flat
                number gets exactly that.
    tilt:    per-type weights (all types, sum ~1.0); falls back to _DEFAULT_TILT
    seed:    additional integer offset (account-hash provides per-account variation)
    drop_types: type ids to remove from the tilt BEFORE allocation (weight → 0, no
                slot allocated). Used to gate `event` out of the nightly plan when
                publish.publish_time_read is armed — the publish-time read lane
                (publish_time_content.generate_read_item) owns that post instead,
                so leaving it nightly too would double-post. Applied AFTER the
                _DEFAULT_TILT merge so it wins even for the default (no-tilt) path.
    banned_kinds: type ids this account's D08 ramp tier forbids OUTRIGHT
                (`ramp_banned_kinds_for`). Removed from the tilt exactly like
                `drop_types`, and for the same reason stated the other way round:
                an allocation to a banned format is not a post, it is a slot the
                Sentinel will quarantine (`ramp_theme_list`) after the writer has
                been paid for it. Kelly's ONE D1 at-bat on 2026-08-02 was a
                `theme_list` on a `weeks_1_2` tier — the account has never posted
                once, ever, and the planner spent her only rung on a format she
                is banned from using (masterplan §8.1 V2). The weight is
                RENORMALISED into the kinds she may ship, so the ban costs the
                desk no volume — it moves the at-bat, it does not delete it.
    cooled_watch / cooled_signal: tickers inside the cross-day cooldown (see
                `cooled_tickers`) for coverage kinds and for signal kinds
                respectively — the LKFN/GPI/CBOE fix (masterplan §5.1). A slot
                whose type needs a ticker and finds NO eligible plan is DROPPED,
                not filled: supply-honest volume means an empty rung stays empty
                (§5.5), and a ticker-less "signal" post renders empty tokens.
                THE EMPTY POOL NEVER FALLS BACK to the uncooled pool: doing so
                would publish exactly the repetition the cooldown exists to stop.
    emit_day_prefix: the ONLY day the cooldown is applied to. Only `D1` slots are
                ever emitted (outbox.emit_from_content_plan defaults to D1 and the
                governor takes the default), so cooling a forward day would delete
                posts nothing was going to send. At the default `n_days=1` EVERY
                slot is an emit slot, so the cooldown applies uniformly and the
                asymmetry that used to decimate D1 alone cannot arise.
    report:     optional mutable counter sink so the plan report can print the
                funnel without this function changing its return type. Keys:
                `dropped_cooldown` (+ `dropped_cooldown_by_account`),
                `slots_offered`, `ramp_banned_kinds`. content_plan persists all
                of them into the artifact — a drop counter that dies in a local
                dict is the defect class that hid 12 nights of lost posts.
    """
    account_id = account.get("id", "unknown")
    voice = account.get("voice", "authoritative desk")
    ah = _account_hash(account_id) + seed

    effective_tilt = dict(_DEFAULT_TILT)
    if tilt:
        for k in _TYPE_IDS:
            if k in tilt and tilt[k] > 0:
                effective_tilt[k] = float(tilt[k])
    if drop_types:
        for k in drop_types:
            effective_tilt.pop(k, None)

    # ── W4b: a format this tier forbids gets ZERO allocation ─────────────────
    # Applied AFTER drop_types and BEFORE the normalisation below, so the banned
    # kind's weight is redistributed across the kinds this desk may actually
    # ship rather than being burned.
    _banned = {str(k) for k in (banned_kinds or ())}
    _banned_hit = sorted(k for k in _banned if k in effective_tilt)
    if _banned_hit:
        _kept = {k: v for k, v in effective_tilt.items() if k not in _banned}
        if _kept:
            _weight = round(sum(effective_tilt[k] for k in _banned_hit), 4)
            effective_tilt = _kept
            if report is not None:
                report.setdefault("ramp_banned_kinds", {})[account_id] = {
                    "kinds": _banned_hit,
                    "weight_reallocated": _weight,
                }
        else:
            # A tier that permits NOTHING is a config defect, not a plan of zero
            # posts. Refuse the ban, keep the tilt, and say so out loud — a
            # silently empty desk is the failure mode this whole lane exists to
            # end.
            print(f"::warning title=marketing-ramp-bans-every-kind::"
                  f"{account_id}: the resolved ramp tier forbids EVERY content "
                  f"kind in this desk's tilt ({', '.join(_banned_hit)}). The ban "
                  f"is IGNORED for this plan — fix sentinel.ramp in "
                  f"config/marketing.yml.", flush=True)
            if report is not None:
                report["ramp_ban_refused"] = report.get("ramp_ban_refused", 0) + 1

    # Normalize
    total_w = sum(effective_tilt.values()) or 1.0
    effective_tilt = {k: v / total_w for k, v in effective_tilt.items()}

    total_slots = n_days * per_day
    allocation = _largest_remainder(effective_tilt, total_slots)
    slots = _slot_labels(n_days, per_day)

    # Build type sequence from allocation (round-robin within type, account-hash offset)
    type_sequence: list[str] = []
    for t in _TYPE_IDS:
        count = allocation.get(t, 0)
        type_sequence.extend([t] * count)

    # Shuffle deterministically using account hash as permutation key
    # Fisher-Yates with deterministic LCG instead of RNG
    seq = list(type_sequence)
    lcg_state = ah % (2**31)
    for i in range(len(seq) - 1, 0, -1):
        lcg_state = (lcg_state * 1664525 + 1013904223) % (2**32)
        j = lcg_state % (i + 1)
        seq[i], seq[j] = seq[j], seq[i]

    # Map plan tickers deterministically — ONLY postable (live/fresh/healthy)
    # signals. A stale, invalidated, or low-confidence plan never becomes a post.
    signal_plans = postable_signals(plans)
    bull_plans = [p for p in signal_plans if p.get("direction") == "BULL"]
    plan_pool = bull_plans if bull_plans else signal_plans

    # Cross-day cooldown pools, computed ONCE (contract §Selection). Two pools
    # because the bar differs by kind: 5 sessions for a directional call, 3 for
    # coverage. Both are applied to the emitted day only — see the docstring.
    _cooled_w = {str(t).upper() for t in (cooled_watch or ())}
    _cooled_s = {str(t).upper() for t in (cooled_signal or ())}
    watch_pool = [p for p in plan_pool
                  if str(p.get("asset", "")).upper() not in _cooled_w]
    signal_pool = [p for p in plan_pool
                   if str(p.get("asset", "")).upper() not in _cooled_s]

    items: list[ContentItem] = []
    plan_cursor = ah % max(len(plan_pool), 1)
    counter = 0

    # The denominator the drop counters are a share OF. Without it a
    # `dropped_cooldown` of 40 is unreadable — 40 out of 60 is an outage, 40 out
    # of 1,176 is a quiet night.
    if report is not None:
        report["slots_offered"] = report.get("slots_offered", 0) + min(
            len(seq), len(slots))

    for slot_idx, (type_id, slot) in enumerate(zip(seq, slots)):
        # Pick a plan for signal/chart posts
        plan = None
        ticker = ""
        cashtag = ""
        if type_id in ("signal", "chart", "receipt") and plan_pool:
            pool = plan_pool
            if slot.startswith(f"{emit_day_prefix}-"):
                pool = signal_pool if type_id == "signal" else watch_pool
            if not pool:
                # Nothing fresh to say about any name tonight for this kind.
                # NO FALLBACK TO `plan_pool`: an empty cooled pool means every
                # eligible name is inside its cross-day cooldown, and reaching
                # past it would publish the repetition the cooldown exists to
                # stop. The rung stays empty (supply-honest volume, §5.5) and
                # the drop is COUNTED — by account, because "the network lost
                # 40 rungs" and "kelly lost all 20 of hers" are different
                # nights and the second one is invisible in a network total.
                if report is not None:
                    report["dropped_cooldown"] = report.get("dropped_cooldown", 0) + 1
                    _by_acct = report.setdefault("dropped_cooldown_by_account", {})
                    _by_acct[account_id] = _by_acct.get(account_id, 0) + 1
                continue
            plan_idx = (plan_cursor + slot_idx * (ah % 7 + 1)) % len(pool)
            plan = pool[plan_idx]
            ticker = plan.get("asset", "")
            cashtag = f"${ticker}" if ticker else ""

        headline_tpl, body_tpl = _get_copy(type_id, voice)
        headline = _render_copy(headline_tpl, plan, account_id)
        body = _render_copy(body_tpl, plan, account_id)

        item_id = f"post-{account_id}-{counter + 1:03d}"
        items.append(ContentItem(
            id=item_id,
            type=type_id,
            account=account_id,
            cashtag=cashtag,
            ticker=ticker,
            headline=headline,
            body=body,
            provenance="neural_web",
            chart_id=None,  # assigned later by content_plan()
            slot=slot,
            status="drafted",
        ))
        counter += 1

    return items


# ─────────────────────────────────────────────────────────────────────────────
# Distinctness check (token-Jaccard)
# ─────────────────────────────────────────────────────────────────────────────

def _jaccard(a: str, b: str) -> float:
    """Token-Jaccard similarity between two strings."""
    ta = set(re.findall(r"\w+", a.lower()))
    tb = set(re.findall(r"\w+", b.lower()))
    if not ta and not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def distinctness(items: list[ContentItem]) -> dict[str, Any]:
    """Check distinctness across items of the same type on different accounts.

    Returns {max_similarity, flags, note}.
    Flags pairs with Jaccard similarity > 0.7.
    """
    max_sim = 0.0
    flag_count = 0

    # Group by type
    by_type: dict[str, list[ContentItem]] = {}
    for item in items:
        by_type.setdefault(item.type, []).append(item)

    for type_id, group in by_type.items():
        # Only compare items from different accounts
        account_items: dict[str, list[ContentItem]] = {}
        for item in group:
            account_items.setdefault(item.account, []).append(item)

        accounts = list(account_items.keys())
        for i in range(len(accounts)):
            for j in range(i + 1, len(accounts)):
                acct_a = accounts[i]
                acct_b = accounts[j]
                for ia in account_items[acct_a]:
                    for ib in account_items[acct_b]:
                        # Only compare if same ticker (same signal rendered differently)
                        if ia.ticker and ib.ticker and ia.ticker == ib.ticker:
                            sim = _jaccard(ia.body, ib.body)
                            if sim > max_sim:
                                max_sim = sim
                            if sim > 0.7:
                                flag_count += 1

    return {
        "max_similarity": round(max_sim, 3),
        "flags": flag_count,
        "note": "same signal rendered per-desk; variants checked",
    }


# ─────────────────────────────────────────────────────────────────────────────
# content_mix
# ─────────────────────────────────────────────────────────────────────────────

def content_mix(items: list[ContentItem]) -> dict[str, int]:
    """Return per-type observed counts."""
    counts: dict[str, int] = {t: 0 for t in _TYPE_IDS}
    for item in items:
        if item.type in counts:
            counts[item.type] += 1
        else:
            counts[item.type] = 1
    return counts


def _media_enabled(cfg: dict | None) -> bool:
    """publish.media_enabled gate (default OFF when absent — conservative)."""
    return bool(((cfg or {}).get("publish", {}) or {}).get("media_enabled", False))


def _attach_chart_media(
    fc: dict,
    *,
    closes: list[float],
    dates: list[str],
    marker_index: int | None,
    as_of: str,
    root: str | Path | None,
    cfg: dict | None,
    subtitle: str | None = None,
) -> None:
    """Render a PNG variant of a single-name signal chart and stamp it on `fc`.

    Gated by publish.media_enabled. Writes the PNG to
    data/marketing/outbox/media/<as_of>/<chart_id>.png, and — if R2 creds exist —
    uploads it to the public data plane. Mutates `fc` in place, adding:
      media_png_path : repo-relative local PNG path (always, when rendered)
      media_url      : public https URL (when R2 creds present) else None
      media_render   : "svg_raster" (the real card) or "legacy_png" (fallback)

    THE POSTED IMAGE IS THE PREVIEWED IMAGE (2026-07-26 incident fix). The PNG is
    a raster of `fc["svg"]` — the exact artwork the Content Studio preview and
    the outbox artifact show, footer marketing bar (mastermind-x.com + "Start
    free 14-day trial") included. Before this, the publish path rendered a
    SEPARATE hand-drawn PIL lookalike of the older v1 line chart, so the account
    posted a bare line chart with no URL and no CTA while the mockup promised the
    full candlestick card. Two renderers = guaranteed drift; there is now one.

    render_signal_chart_png remains ONLY as the fallback for hosts with no Chrome
    (CI, the ubuntu publish runner) so a missing rasteriser can never turn a post
    text-only. It is a degraded image, and media_render records when it was used.

    marker_index=None IS THE NO-CLAIM CONTRACT, and it must be passed by every
    caller whose SVG is markerless (the tape fallback, the filing/house-pick
    lanes). The fallback PNG is the image X actually receives when Chrome is
    missing, so a caller that renders a markerless SVG and then hands this a real
    index posts a BUY-labelled card under copy that makes no call at all. Pass
    the SAME series the SVG was drawn from, too: the SVG and this raster are two
    renderers, and feeding them different windows makes the fallback a chart of a
    different stretch of tape than the one the preview promised.

    Fully fail-soft: any render/write/upload error leaves `fc` SVG-only (no
    media_* keys) and never raises — the post degrades to text-or-SVG. No-op
    when the gate is off, when there is no chart_id, or when closes are too thin.
    """
    if not _media_enabled(cfg):
        return
    chart_id = fc.get("id")
    if not chart_id or not closes or len(closes) < 2:
        return
    try:
        from engine.marketing.chart_render import render_signal_chart_png  # noqa: PLC0415
        from engine.marketing.media_publish import publish_card  # noqa: PLC0415

        stamped = publish_card(
            fc.get("svg") or "",
            chart_id=str(chart_id),
            as_of=str(as_of),
            root=root,
            # Chrome-less hosts only (CI / ubuntu publish runner).
            legacy_png=lambda: render_signal_chart_png(
                fc.get("ticker") or "", dates or [], closes,
                marker_index=marker_index, subtitle=subtitle),
        )
        for key in ("media_png_path", "media_render"):
            if stamped.get(key):
                fc[key] = stamped[key]
        if "media_url" in stamped:
            # explicit None documents "rendered but not hosted"
            fc["media_url"] = stamped["media_url"]

        # THE DEGRADED IMAGE HAS TO BE AUDIBLE (2026-07-30).
        #
        # `legacy_png` is a hand-drawn PIL line chart with no candles, no
        # indicators and NO FOOTER CTA — a visibly worse picture than the card
        # the preview promises. media_publish already noted the swap, but through
        # `log.warning`, and this repo's builders log with a prefixing format, so
        # GitHub silently drops any annotation that does not START the line
        # (CLAUDE.md; it shipped dead five times before #3587 swept 69 sites).
        # Nothing counted it either.
        #
        # So the quality of every image we post was a number nobody could see —
        # which is how one committed plan showing 15 of 23 cards degraded got
        # read as an audit finding, then as a refuted finding, then as a live
        # production failure, when it was a LOCAL run with Chrome contended.
        # Production's own PNGs (2026-07-29, 21 of 21 at 2000x1760) are all the
        # real card. The rasteriser works when it is not fighting for the
        # machine, so a fallback is a SYMPTOM of that fight, not a steady state,
        # and it belongs on the console where the operator reads losses rather
        # than in a log nobody opens. Bare print, line start, flushed.
        if str(fc.get("media_render") or "") == "legacy_png":
            print(f"::warning title=marketing-chart-legacy-fallback::"
                  f"{chart_id}: the SVG raster produced nothing, so this post "
                  f"carries the DEGRADED legacy PNG (no candles, no indicators, "
                  f"no footer CTA). Chrome is the rasteriser; a fallback here "
                  f"means it failed or timed out, not that the card is fine.",
                  flush=True)
    except Exception as exc:  # noqa: BLE001
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "content_studio: chart PNG render failed for %s: %s", fc.get("id"), exc)


def raster_plan_media(
    plan: dict,
    *,
    cfg: dict | None,
    root: str | Path | None,
    day_prefix: str = "D1",
) -> dict:
    """Raster + upload the PNGs for charts on posts that SURVIVED the gate.

    The companion to ``content_plan(..., defer_media=True)``. Call it AFTER
    sentinel.gate_plan and BEFORE outbox.emit_from_content_plan; it mutates the
    plan's featured_charts in place, stamping the same media_png_path /
    media_url / media_render keys the inline path stamps, so every downstream
    reader is unchanged.

    WHY DEFER. Each PNG is one headless-Chrome launch (~13s). Rastering at plan
    time paid that for all 8 cards whether or not any post could carry them — on
    the 2026-07-28 plan every single rastered card was then quarantined by the
    cadence cap, so the whole spend shipped nothing. Charting every ticker post
    (which is the point) would have multiplied that waste by ten. Here we know
    which items passed, so we raster only what can actually post: ~2 cards per
    desk instead of every card in the plan.

    Selection: a featured chart is rastered when at least one queue item
    references its id, sits on the emit day, and is NOT quarantined. A plan whose
    gate crashed stamps sentinel_ok=False everywhere and correctly rasters
    nothing. Fully fail-soft — a card that cannot be rastered stays SVG-only and
    its post degrades to text.

    PRUNING. content_plan renders an SVG for every candidate ticker post because
    an SVG is ~1ms and capping it would mean guessing which posts survive. Those
    SVGs are ~45KB each and would bloat content_plan.json well past its current
    size, so the cards no surviving post references are dropped here — the
    artifact ends up carrying only the cards that ship. Reach-lane cards
    (theme/mover, which raster inline and carry no deferral blob) are kept
    regardless, since they are the plan's own reach content.

    Returns {"rastered": int, "skipped": int, "hosted": int, "pruned": int}.
    """
    charts = {
        str(fc.get("id")): fc
        for fc in (plan.get("featured_charts") or [])
        if fc.get("id")
    }
    wanted: set[str] = set()
    for acct in plan.get("accounts") or []:
        for item in acct.get("queue") or []:
            cid = item.get("chart_id")
            if not cid or cid not in charts:
                continue
            if not str(item.get("slot", "")).startswith(f"{day_prefix}-"):
                continue
            if item.get("status") == "quarantined" or item.get("sentinel_ok") is False:
                continue
            # Mirror outbox.emit_from_content_plan EXACTLY: a failed live gate
            # only bars an item that still claims an entry. Skipping every
            # _live_gate_fail item here pruned the cards off precisely the
            # demoted watchlist posts that now ship, so they emitted text-only
            # (coverage fell 21/22 -> 16/29 when the emit rule moved and this
            # one did not). These two predicates must stay in lockstep.
            if item.get("_live_gate_fail") and item.get("type") == "signal":
                continue
            wanted.add(str(cid))

    counts = {"rastered": 0, "skipped": 0, "hosted": 0, "pruned": 0}
    keep: list[dict] = []
    for cid, fc in charts.items():
        deferred = fc.pop("_defer", None)
        if deferred is None:
            # Reach-lane card (theme/mover): rastered inline, always kept.
            keep.append(fc)
            counts["skipped"] += 1
            continue
        if cid not in wanted:
            counts["pruned"] += 1
            continue
        # NONE MUST SURVIVE THE ROUND TRIP. `int(x or 0)` turned the tape card's
        # markerless None into index 0, which put a green BUY triangle + label on
        # the fallback PNG of a "watching, not buying yet" post — on the
        # PRODUCTION path, because defer_media is how the nightly rasters.
        _mi = deferred.get("marker_index")
        _attach_chart_media(
            fc,
            closes=deferred.get("closes") or [],
            dates=deferred.get("dates") or [],
            marker_index=(int(_mi) if _mi is not None else None),
            as_of=str(plan.get("as_of") or ""),
            root=root,
            cfg=cfg,
            subtitle=deferred.get("subtitle"),
        )
        if fc.get("media_png_path"):
            counts["rastered"] += 1
        if fc.get("media_url"):
            counts["hosted"] += 1
        keep.append(fc)

    # Preserve the original ordering of whatever survived.
    kept_ids = {str(fc.get("id")) for fc in keep}
    plan["featured_charts"] = [
        fc for fc in (plan.get("featured_charts") or [])
        if str(fc.get("id")) in kept_ids
    ]
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# Artifact boundary — which scaffolding keys may cross it
# ─────────────────────────────────────────────────────────────────────────────

#: Underscore-prefixed queue-item keys allowed to reach content_plan.json.
#: Every other "_" key is in-process scaffolding (see strip_scaffolding). Each
#: entry below has a NAMED reader of the written artifact — add one only with
#: the same evidence, never just because it looks small:
#:   _live_gate_fail  → admin/marketing._CONTENT_POST_KEEP ("signal demoted"
#:                      badge). Also gates outbox.emit_from_content_plan, but
#:                      that reads the in-memory plan.
#:   _copy_violations → admin/marketing._CONTENT_POST_KEEP (caution chip).
#:   _copy_mode       → telemetry._build_post_index, which re-opens
#:                      content_plan.json from disk for the Lab roll-up.
ARTIFACT_KEEP_KEYS: frozenset[str] = frozenset({
    "_live_gate_fail",
    "_copy_violations",
    "_copy_mode",
})


def strip_scaffolding(plan: dict) -> dict:
    """Return a COPY of ``plan`` with in-process scaffolding keys dropped.

    The copywriter pass hangs the whole Prophet plan dict on every queue item
    (``_plan``), plus its receipt and mover/theme fact blobs, so build_context
    can read them without a second lookup. Those are locals with a long
    lifetime, not artifact fields — nothing that re-opens content_plan.json
    reads them. Left in, ``_plan`` alone was the largest per-item field in the
    artifact by ~9x over the next one (239 KB of a 1.11 MB, 7-desk, 218-item
    plan) and grows linearly with the desk count.

    COPY-ON-WRITE IS LOAD-BEARING. The governor keeps using the in-memory plan
    AFTER the write: links.build_short_link_pages, and critically
    outbox.emit_from_content_plan, which reads ``_plan`` to stamp
    source.signal_id / direction / entry / invalidation for the publisher's
    post-time live gate (engine/marketing/live_verify.py). Stripping in place
    would silently disarm that gate — every post would lose its structured
    tape-claim and fall back to regexing cashtags out of the copy. So this
    never mutates its argument.
    """
    if not isinstance(plan, dict):
        return plan

    def _clean_item(item: Any) -> Any:
        if not isinstance(item, dict):
            return item
        return {
            k: v for k, v in item.items()
            if not k.startswith("_") or k in ARTIFACT_KEEP_KEYS
        }

    out = dict(plan)

    if isinstance(plan.get("accounts"), list):
        accounts: list[Any] = []
        for acct in plan["accounts"]:
            if not isinstance(acct, dict):
                accounts.append(acct)
                continue
            a = dict(acct)
            if isinstance(acct.get("queue"), list):
                a["queue"] = [_clean_item(i) for i in acct["queue"]]
            accounts.append(a)
        out["accounts"] = accounts

    # featured_charts get NO keep-list: `_defer` is the raster pass's internal
    # hand-off blob, which the governor already pops on its failure path.
    if isinstance(plan.get("featured_charts"), list):
        out["featured_charts"] = [
            {k: v for k, v in fc.items() if not k.startswith("_")}
            if isinstance(fc, dict) else fc
            for fc in plan["featured_charts"]
        ]

    return out


# ─────────────────────────────────────────────────────────────────────────────
# content_plan — the full §2.3 artifact
# ─────────────────────────────────────────────────────────────────────────────

def content_plan(
    cfg: dict,
    plans: list[dict],
    *,
    closes_loader: Callable[[str], tuple[list[str], list[float]] | None] | None = None,
    root: str | Path | None = None,
    defer_media: bool = False,
    write_shape_ledger: bool = False,
) -> dict:
    """Build the full content plan artifact (frozen §2.3 shape).

    cfg:          parsed config/marketing.yml
    plans:        list of Prophet plan dicts (may be empty)
    closes_loader: callable(ticker) -> (dates, closes) | None
    root:         repo root for OHLCV loading (chart_render._PRICE_SUBDIRS —
                  data/baskets/ohlcv/<TICKER>.parquet, then data/stocks/). If
                  None, inferred from a closes_loader built by _make_closes_loader.
    write_shape_ledger: nightly-only switch for the 14-day shape ledger
                  (`data/marketing/shape_ledger.json`). The governor passes True;
                  every other caller (tests, the admin preview, an ad-hoc rebuild)
                  leaves it False so a plan build can never advance an ops file —
                  the nightly stays the sole advancer (CLAUDE.md ledger law).
    defer_media:  when True, render the SVGs but DO NOT raster/upload the PNGs.
                  Each featured chart carries a private "_defer" blob instead, and
                  the caller finishes the job with raster_plan_media() AFTER the
                  Sentinel gate — so only cards attached to a post that actually
                  survives cost a headless-Chrome launch (~13s each). The governor
                  passes True; every other caller keeps the inline behaviour.

    Returns the frozen dict structure with envelope fields caller will stamp.
    """
    from engine.marketing.chart_render import (
        chart_cta_enabled,
        macd_cross,
        render_signal_chart,
        load_ohlcv,
        load_ohlcv_windowed,
        render_chart_v2,
    )

    # publish.chart_cta_enabled — the account-wide footer posture. THE POSTED
    # IMAGE IS THE PREVIEWED IMAGE (2026-07-26 single-renderer fix), so setting it
    # once here reaches every outbound card: the publisher rasterises this exact
    # SVG and the admin preview shows the same artifact by construction.
    _card_cta = chart_cta_enabled(cfg)

    # Iterate the EFFECTIVE account list (engine.marketing.accounts): only
    # accounts with a real X account behind them (enabled) get a generated queue.
    # A disabled/planned account still appears in the plan (so the admin lists it,
    # status "planned") but with an EMPTY queue — no drafted content and, downstream,
    # no Sentinel load. This kills the ~85-item nightly cadence_cap_daily noise at
    # the source: the gate was quarantining content for 5 desks that don't exist.
    from engine.marketing.accounts import effective_accounts as _eff_accounts
    eff_accounts = _eff_accounts(cfg, root)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now_str[:10]

    # When publish.publish_time_read is armed, the after-close DAILY READ is
    # generated at PUBLISH time (publish_time_content.generate_read_item), so the
    # nightly plan must NOT also allocate an `event` slot — else the read double-
    # posts once armed. Dropping `event` from the tilt zeroes its allocation.
    # Flag OFF (the default) → drop_types empty → allocation unchanged (byte-
    # identical to today).
    _pt_read_on = bool(
        ((cfg or {}).get("publish") or {}).get("publish_time_read", {}).get("enabled"))
    drop_types: set[str] = {"event"} if _pt_read_on else set()

    # ── SELECTION LAYER (W1, masterplan §5) ───────────────────────────────────
    # Read the outbox ledger ONCE and derive the two cooldown sets before any
    # allocation happens. This is the step that did not exist on 2026-07-29,
    # which is why LKFN/GPI/CBOE were planned again the day after they posted.
    # Fail-soft by construction: ticker_exposure returns {} on an unreadable
    # ledger, and {} cools nothing.
    _sel_report: dict[str, Any] = {}
    _exposure = ticker_exposure(root, as_of=today)
    # Hot Tape context pack (#3941) — read-only join, absent file degrades to
    # today's facts (masterplan §4). Feeds cooldown_override_reason and the
    # writer context's `pack` slice.
    _packs = load_hot_tape_pack(root)
    _shape_ledger = load_shape_ledger(root)

    # A cooled ticker comes BACK only when a genuinely new fact class fires
    # (earnings, |move| ≥4%, level break, streak record) — and the post must then
    # LEAD with that fact, which is why the reason travels into the writer
    # context rather than just unlocking the name silently (§5.1).
    _plan_by_asset: dict[str, dict] = {}
    for _p in (plans or []):
        _a = str(_p.get("asset") or "").upper()
        if _a and _a not in _plan_by_asset:
            _plan_by_asset[_a] = _p
    _cooldown_overrides: dict[str, str] = {}
    for _tkr in list(_exposure):
        _reason = cooldown_override_reason(
            _tkr, pack=_packs.get(_tkr), plan=_plan_by_asset.get(_tkr))
        if _reason:
            _cooldown_overrides[_tkr] = _reason

    def _uncool(blocked: frozenset[str]) -> frozenset[str]:
        return frozenset(t for t in blocked if t not in _cooldown_overrides)

    _cooled_watch = _uncool(
        cooled_tickers(_exposure, as_of=today, kind="watchlist", cfg=cfg))
    _cooled_signal = _uncool(
        cooled_tickers(_exposure, as_of=today, kind="signal", cfg=cfg))
    _sel_report["cooled_tickers"] = len(_cooled_watch)
    _sel_report["cooled_signal_tickers"] = len(_cooled_signal)
    _sel_report["cooldown_overrides"] = len(_cooldown_overrides)

    # The funnel's first two stages are counted in FACTS (postable plans), the
    # third in POSTS — stated here so nobody reads `supply` as a post count.
    # Same pool arithmetic plan_account does, evaluated once for the report.
    _supply_pool = postable_signals(plans)
    _bull_pool = [p for p in _supply_pool if p.get("direction") == "BULL"]
    _supply_pool = _bull_pool or _supply_pool
    _sel_report["supply"] = len(_supply_pool)
    _sel_report["after_cooldown"] = len(
        [p for p in _supply_pool
         if str(p.get("asset", "")).upper() not in _cooled_watch])

    # ── LADDER SHAPE + RAMP FORMAT PERMISSIONS (W4a/W4b) ─────────────────────
    # Resolve the D08 ramp table ONCE for the whole plan: both the per-account
    # rung count (`ladder_shape_for`) and the per-account banned formats
    # (`ramp_banned_kinds_for`) read it, and re-resolving per account would
    # re-read the override file 13 times and re-emit its annotations.
    # Fail-soft: an unresolvable ramp leaves _ramp None, which sizes every desk
    # to the full ladder and bans nothing — the pre-W4 behaviour.
    _ramp: dict | None = None
    try:
        from engine.marketing.sentinel import resolve_ramp as _resolve_ramp
        _ramp = _resolve_ramp(cfg or {}, today, root=root, announce=False)
    except Exception as exc:  # noqa: BLE001 — a tier read must never break a plan
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "content_studio: ramp resolve failed (%s) — full ladder, no format bans",
            exc)
    _sel_report["forward_days"] = forward_days(cfg)
    _sel_report["per_day_headroom"] = per_day_headroom(cfg)
    _sel_report["ladder_shape"] = {}

    # Collect per-account items
    all_items: list[ContentItem] = []
    account_rows: list[dict] = []

    for acct_cfg in eff_accounts:
        acct_id = acct_cfg.get("id", "unknown")
        tilt_cfg = acct_cfg.get("tilt", {})
        voice = acct_cfg.get("voice", "authoritative desk")
        kind = acct_cfg.get("kind", "generic")

        # Effective tilt — from config or default (computed for every account so
        # the admin can show the intended mix even for planned, unqueued desks).
        eff_tilt = dict(_DEFAULT_TILT)
        if tilt_cfg:
            for k in _TYPE_IDS:
                if k in tilt_cfg:
                    eff_tilt[k] = float(tilt_cfg[k])
        for k in drop_types:  # publish_time_read armed → no nightly event slot
            eff_tilt.pop(k, None)
        total_w = sum(eff_tilt.values()) or 1.0
        eff_tilt = {k: round(v / total_w, 3) for k, v in eff_tilt.items()}

        # Planned (not enabled): list it, but draft NOTHING for it.
        if not acct_cfg.get("enabled"):
            account_rows.append({
                "id": acct_id,
                "name": acct_cfg.get("beat", acct_id),
                "kind": kind,
                "voice": voice,
                "tilt": eff_tilt,
                "mix_observed": {},
                "queue": [],
                "status": "planned",
            })
            continue

        # A WIRE DESK DRAFTS NOTHING HERE (W4f, 2026-08-02). A desk with no
        # `copywriter.personas` block has no authored voice by design — it relays
        # in the house wire voice (engine/marketing/wire_voice.py), and the
        # charter is explicit that a wire account RELAYS AND NEVER EDITORIALIZES
        # (masterplan §1, §4 safety rails). Its volume comes from the wire lanes,
        # which bypass content_plan entirely: hot tape (~18 items/day on the
        # 07-30/07-31 tape) and the `wire_routing.classes` it owns.
        #
        # WHY THIS IS A REAL GATE AND NOT TIDINESS. `_get_copy` is keyed by
        # (type, voice) and FALLS BACK to the "authoritative desk" bank on an
        # unknown voice, so a persona-less desk cannot draft nightly copy in any
        # voice of its own — it can only wear another desk's. Arming
        # mastermind_news (voice "fast, reactive", founder's key) would have had
        # it drafting FOUNDER's deterministic templates: near-identical bodies
        # that the cross-account near-dup guard quarantines on whichever desk it
        # reaches second. That is precisely how meagan shipped 0 posts and sophia
        # 1 on 2026-07-28 (tests/test_marketing_chart_coverage.py
        # ::test_every_enabled_desk_has_its_own_template_bank), and it would have
        # armed the news desk straight into the silence this wave exists to end.
        #
        # Renaming its `voice` would NOT fix it: an unrecognised string falls back
        # to flagship's bank, so the collision merely becomes invisible to a guard
        # that only compares voice strings. The desk is listed with its tilt (the
        # admin still shows the intended mix) and an empty nightly queue.
        if not _drafts_nightly_copy(cfg, acct_id):
            account_rows.append({
                "id": acct_id,
                "name": acct_cfg.get("beat", acct_id),
                "kind": kind,
                "voice": voice,
                "tilt": eff_tilt,
                "mix_observed": {},
                "queue": [],
                "status": "wire",
            })
            continue

        # ONE day of rungs, sized to THIS desk's ramp cap (W4a), drawn only from
        # the formats THIS desk's tier permits (W4b).
        _shape = ladder_shape_for(cfg, acct_id, today, root=root, ramp=_ramp)
        _banned = ramp_banned_kinds_for(cfg, acct_id, today, root=root, ramp=_ramp)
        _sel_report["ladder_shape"][acct_id] = dict(_shape)

        items = plan_account(
            account=acct_cfg,
            plans=plans,
            n_days=_shape["n_days"],
            per_day=_shape["per_day"],
            seed=0,
            tilt=tilt_cfg if tilt_cfg else None,
            drop_types=drop_types,
            banned_kinds=_banned,
            cooled_watch=_cooled_watch,
            cooled_signal=_cooled_signal,
            report=_sel_report,
        )
        all_items.extend(items)

        mix = content_mix(items)

        account_rows.append({
            "id": acct_id,
            "name": acct_cfg.get("beat", acct_id),
            "kind": kind,
            "voice": voice,
            "tilt": eff_tilt,
            "mix_observed": mix,
            # What the ALLOCATOR produced, before any downstream filter touches
            # the queue. `mix_observed` is recomputed later from the surviving
            # queue, so once the perishability cut and the writer's drops land it
            # describes the SHIPPING plan — which is what that name should mean.
            # The allocator's own guarantees (largest-remainder gives every type
            # at least one slot; the tilt makes signal the biggest share) are
            # properties of THIS number and are asserted against it.
            "mix_allocated": dict(mix),
            "queue": [item.as_dict() for item in items],
        })

    # Reach content (confluence + publish-time mover/theme) may ONLY be assigned
    # to accounts that will actually post — never to a planned (disabled) desk,
    # or the Sentinel would carry content for a desk that doesn't exist (F3d). A
    # planned row keeps its empty queue; enabled_rows drives every reach-item
    # placement below. Falls back to all rows only if nothing is enabled (so a
    # fully-planned network still produces a plan rather than crashing).
    enabled_rows = [r for r in account_rows if r.get("status") != "planned"] or account_rows

    # ── Featured charts: EVERY post that names a ticker gets a card ───────────
    # Operator law, 2026-07-28: "we should always have illustrations for charting
    # tickers, unless it's some kind of event that occurred with the company —
    # but we're doing entry timing, so charting should be used."
    #
    # This loop used to read `if item_dict["type"] != "signal": continue`, which
    # made three of the four ticker-bearing content types STRUCTURALLY incapable
    # of carrying an image. The Outbox showed the result verbatim: a post headed
    # "$LKFN chart I keep coming back to" whose body ends "mine's on the chart",
    # shipped with no chart; a "Radar check on $CVI — near entry, nothing's
    # triggered" with nothing to look at. Across the 7-day plan that was ~25
    # `chart` posts and ~120 `watchlist` posts at chart_id=None, every one.
    #
    # It was worse than it looked. Most `signal` items are demoted to `watchlist`
    # by the live-price gate in the copywriter pass BELOW this loop, so watchlist
    # dominates the early ladder slots — and the Sentinel cadence cap keeps the
    # EARLIEST surviving slots. The charted signal posts sat at D1-S12/S16 and
    # were quarantined as cadence_cap_daily before they could post. Measured on
    # the 2026-07-28 plan: 8 charts rendered, 0 reached a post that shipped.
    #
    # A demoted signal is exactly the entry-timing post the operator means: "near
    # entry, not triggered" is a statement ABOUT THE TAPE and is worthless without
    # it. So the type filter widens to every ticker-bearing type, and the two
    # gates split by what each actually protects (see `variant` in the loop).
    _CHARTABLE_TYPES = ("signal", "chart", "watchlist", "receipt")

    # Only D1 slots are ever emitted (outbox.emit_from_content_plan defaults to
    # day_prefix="D1" and the governor takes the default), so charting D2+ would
    # raster images no post can ever attach.
    _CHART_DAY_PREFIX = "D1"

    # No per-account cap on the SVG lane, deliberately. An SVG is ~1ms and the
    # EXPENSIVE half (one headless-Chrome launch per PNG, ~13s) is already
    # deferred to raster_plan_media, which only pays for cards on posts that
    # survive the gate. A cap here would have to guess WHICH posts survive, and
    # guessing in slot order is wrong: the budget gets spent on early items that
    # near-dup then kills, leaving the items that actually ship with nothing
    # (measured — a cap of 3 left meagan's surviving D1-S12 post uncharted while
    # three dead earlier slots held the budget). Render every candidate; the gate
    # decides; raster_plan_media prunes the rest back out of the artifact.

    featured_charts: list[dict] = []
    chart_id_counter = 1

    if closes_loader is not None and plans:
        # Render cache keyed by (account, ticker, variant). PER-ACCOUNT is not an
        # optimisation detail — sentinel.gate_plan quarantines any second account
        # carrying a chart_id another desk already used (reason shared_media:<id>),
        # because two desks posting the identical image is the coordinated-posting
        # fingerprint it exists to catch. Each desk therefore gets its own card id.
        #
        # What is fixed here is the opposite failure: the cache used to be a single
        # GLOBAL `seen_tickers` set, so the first desk to chart a ticker locked
        # every other desk out of it entirely — the founder desk's own $EQT and
        # $ROST signal posts got no chart because flagship had already claimed
        # both names. Global dedupe starved desks; per-account dedupe feeds them
        # without tripping the shared-media guard.
        rendered: dict[tuple[str, str, str], str] = {}
        # Root for OHLCV loading: explicit param preferred; "." as a safe default.
        _ohlcv_root: str = str(root) if root is not None else "."

        for acct_row in account_rows:
            acct_id = acct_row["id"]
            for item_dict in acct_row["queue"]:
                item_type = item_dict.get("type", "")
                if item_type not in _CHARTABLE_TYPES:
                    continue
                if not str(item_dict.get("slot", "")).startswith(f"{_CHART_DAY_PREFIX}-"):
                    continue
                ticker = item_dict.get("ticker", "")
                if not ticker:
                    continue

                # Find plan for this ticker — must pass the eligibility gate.
                # Defense-in-depth: never chart a stale/invalidated signal.
                plan_match = next(
                    (p for p in plans
                     if p.get("asset") == ticker and is_postable_signal(p)),
                    None,
                )
                if plan_match is None:
                    continue

                closes_result = closes_loader(ticker)
                if closes_result is None:
                    continue

                dates, closes = closes_result
                if len(closes) < 10:
                    continue

                # A `signal` post makes an ENTRY CLAIM, so its card carries the
                # setup marker and the % callout. Every other type describes the
                # tape ("watching", "not buying yet", "here's the chart") and gets
                # the SAME card with no marker, no highlight disc and no SETUP
                # pill — an honest chart with no claim attached. Marking a "not
                # buying yet" post with a SETUP pill is the lie this split exists
                # to prevent.
                variant = "signal" if item_type == "signal" else "tape"

                # LIVE gate — decides the VARIANT, it does not veto the chart.
                # A featured chart on a signal is the loudest post we make, so an
                # underwater/runaway/stale signal must never carry the marker (the
                # BA case: down 5.5% from entry yet still charted with a BUY). But
                # that reasoning is entirely about the ENTRY CLAIM. An item that
                # fails here is about to be demoted signal→watchlist by the
                # copywriter pass below, becoming a "watching, not triggered" post
                # — which needs the tape MORE than a live signal does, not less.
                #
                # Getting this backwards is what made the first cut of this fix a
                # no-op: the gate ran before the demotion, so it stripped the card
                # from an item that was still typed `signal`, and the post that
                # eventually shipped was an uncharted watchlist. Downgrade the
                # variant here; never `continue`.
                if variant == "signal":
                    try:
                        from engine.marketing.copywriter import verify_signal_live as _vsl
                        _ok_live, _ = _vsl(plan_match, closes_result, today=today)
                    except Exception:  # noqa: BLE001
                        _ok_live = True  # fail-open only if the gate itself is broken
                    if not _ok_live:
                        variant = "tape"

                # Reuse before the cap: a second post on an already-rendered
                # ticker costs nothing and must never be starved by the budget.
                cached = rendered.get((acct_id, ticker, variant))
                if cached is not None:
                    item_dict["chart_id"] = cached
                    continue

                # Place the BUY marker at the REAL signal — the Prophet signal
                # date — first. That is the honest anchor and it avoids marking a
                # cosmetic local peak. Only if the signal date is out of the chart
                # window do we fall back to the internal momentum turn, then latest.
                # Neutral marker_source tokens only (no indicator vocabulary).
                marker_source = "latest"
                marker_index = len(closes) - 1
                signal_date = str(plan_match.get("_signal_date", ""))[:10]
                if signal_date and signal_date in dates:
                    marker_index = dates.index(signal_date)
                    marker_source = "signal_date"
                else:
                    turn = macd_cross(closes)     # internal only; name never surfaced
                    if turn is not None:
                        marker_index = turn["index"]
                        marker_source = "momentum_turn"

                if variant == "tape":
                    # No claim, no anchor: the card is the last N sessions as they
                    # are. marker_* stay as metadata for the artifact only.
                    marker_source = "none"

                marker_date = dates[marker_index] if marker_index < len(dates) else dates[-1]
                marker_price = closes[marker_index]

                cashtag = f"${ticker}"
                chart_id = f"chart-{chart_id_counter:03d}"

                # ── v2 chart: attempt OHLCV load for candlestick render ──────
                svg: str | None = None
                if _ohlcv_root:
                    # Windowed load: a warm-up lead-in so SMA50/MACD span the whole
                    # visible window (paneless volume + tall MACD; see load_ohlcv_windowed).
                    _windowed = load_ohlcv_windowed(ticker, _ohlcv_root)
                    ohlcv, _warmup = _windowed if _windowed else (None, 0)
                    if ohlcv is not None:
                        ohlcv_dates, ohlcv_o, ohlcv_h, ohlcv_l, ohlcv_c, ohlcv_v = ohlcv
                        # Re-compute marker_index against the OHLCV date list
                        ohlcv_marker = len(ohlcv_dates) - 1
                        if signal_date and signal_date in ohlcv_dates:
                            ohlcv_marker = ohlcv_dates.index(signal_date)
                        elif marker_index < len(ohlcv_dates):
                            ohlcv_marker = marker_index
                        # M2 overlays for Prophet-sourced charts.
                        # Prophet plans carry no confluence leg families, so there is
                        # no leg-driven liveness signal here (that lives on the
                        # confluence path). Two ways to attach overlays on this path:
                        #   (1) DOCUMENTED MANUAL-OVERRIDE SEAM — a caller may
                        #       pre-compute overlays and attach item_dict["m2_overlays"];
                        #       whatever it holds is passed straight through.
                        #   (2) config marketing.m2_overlays_always — force-build BOTH
                        #       overlays for every Prophet chart (debugging/QA).
                        _m2_cfg_always = bool(
                            (cfg or {}).get("marketing", {}).get("m2_overlays_always", False)
                        )
                        _m2_ovl = item_dict.get("m2_overlays") or {}  # (1) manual seam
                        # OVERLAYS ARE ON BY DEFAULT (operator 2026-07-30).
                        #
                        # This used to build ONLY when marketing.m2_overlays_always
                        # was set, and that key is set NOWHERE — so `_m2_ovl` was
                        # {} on every nightly render and avwap_overlay/poc_overlay
                        # went to the renderer as None every single time. The
                        # renderer supports both; the call site never asked.
                        #
                        # The consequence was a chart that did not support its own
                        # copy. A post reads "held 219.90, the average price paid
                        # since the Jun 26 volume spike" (an AVWAP) or "dipped back
                        # to 283.85, the most-traded price of the past four months"
                        # (a POC) and the picture drew neither — just candles, a
                        # 50 SMA and a MACD pane. The reader had to take the claim
                        # on faith, on a program whose first law is that a ticker
                        # post ships a picture.
                        #
                        # These are the two structural levels chart_facts actually
                        # computes its facts FROM (fact ids avwap_hold /
                        # avwap_reclaim / poc_level / poc_retest_hold /
                        # in_value_area), so drawing them is drawing the subject of
                        # the post. build_m2_overlays is fail-soft and returns
                        # {"avwap_overlay": None, "poc_overlay": None} on any error,
                        # so a bad load costs the overlay, never the chart.
                        # The config key is now an OPT-OUT: set it false to disable.
                        _m2_want = bool(
                            (cfg or {}).get("marketing", {})
                            .get("m2_overlays_always", True)
                        ) or _m2_cfg_always
                        if _m2_want and not _m2_ovl:
                            try:
                                from engine.marketing.chart_render import build_m2_overlays as _bm2
                                _m2_ovl = _bm2(
                                    ticker, ohlcv_dates, ohlcv_o, ohlcv_h,
                                    ohlcv_l, ohlcv_c, ohlcv_v, _ohlcv_root,
                                )
                            except Exception:
                                _m2_ovl = {}
                        # A tape card draws NO marker, NO highlight disc and NO
                        # SETUP pill — render_chart_v2 suppresses all three when
                        # both indices are None (eff_highlight stays None).
                        svg = render_chart_v2(
                            ticker=ticker,
                            dates=ohlcv_dates,
                            o=ohlcv_o,
                            h=ohlcv_h,
                            l=ohlcv_l,
                            c=ohlcv_c,
                            volume=ohlcv_v,
                            timeframe="DAILY",
                            marker_index=(ohlcv_marker if variant == "signal" else None),
                            highlight_index=(ohlcv_marker if variant == "signal" else None),
                            pct_from_index=(
                                ohlcv_marker
                                if (variant == "signal"
                                    and (len(ohlcv_c) - 1 - (ohlcv_marker or 0)) >= 5)
                                else None
                            ),
                            show_indicators=True,
                            indicators=("volume", "macd"),
                            warmup=_warmup,
                            volume_overlay=True,   # volume embedded in the price pane
                            subpanel_h=190,        # tall, legible MACD pane
                            height=880,
                            company_name=ticker,
                            logo_root=_ohlcv_root,
                            avwap_overlay=_m2_ovl.get("avwap_overlay"),
                            poc_overlay=_m2_ovl.get("poc_overlay"),
                            cta=_card_cta,
                        )

                # Fallback: v1 render (marker-only) so nothing breaks.
                # SIGNAL ONLY — the v1 card hard-draws a green "BUY" label at the
                # marker, which on a "watching, not buying yet" post would be a
                # flat contradiction of the copy. A tape post with no v2 render
                # available ships text-only rather than mislabelled.
                if svg is None and variant == "signal":
                    subtitle = f"{cashtag} · signal"
                    svg = render_signal_chart(
                        ticker=ticker,
                        dates=dates,
                        closes=closes,
                        marker_index=marker_index,
                        subtitle=subtitle,
                    )
                elif svg is None:
                    # Tape fallback (W1 CI fix 2026-07-29): when the v2 OHLCV
                    # candlestick cannot load (name outside the parquet tree, or
                    # a pyarrow-less env), a "watching, not buying yet" post used
                    # to lose its chart here and then DEFER FOREVER at publish
                    # under the ticker-post-carries-a-chart law. The markerless
                    # v1 card is an honest line chart with no claim attached —
                    # the BUY-labelled form stays signal-only, exactly as the
                    # comment above rules.
                    svg = render_signal_chart(
                        ticker=ticker,
                        dates=dates,
                        closes=closes,
                        marker_index=None,
                        subtitle=f"{cashtag} · tape",
                    )
                if svg is None:
                    continue

                # Get headline/body from queue item
                headline = item_dict.get("headline", f"{cashtag} opportunity flagged")
                body = item_dict.get("body", "")

                item_dict["chart_id"] = chart_id
                rendered[(acct_id, ticker, variant)] = chart_id

                _fc = {
                    "id": chart_id,
                    "ticker": ticker,
                    "account": acct_id,
                    "cashtag": cashtag,
                    "variant": variant,
                    "marker_source": marker_source,
                    "marker_date": marker_date,
                    "marker_price": round(marker_price, 4),
                    "svg": svg,
                    "headline": headline,
                    "body": body,
                }
                # PNG variant for X (gated by publish.media_enabled; SVG can't post).
                # With defer_media the raster is postponed until after the Sentinel
                # gate so only cards on posts that SURVIVE cost a Chrome launch —
                # see raster_plan_media().
                # THE FALLBACK PNG FOLLOWS THE CARD, NOT THE PROPHET ROW. A tape
                # card is markerless in every renderer: its SVG draws no marker
                # (v2 with both indices None, or the v1 markerless fallback
                # above), so the Chrome-less legacy raster must draw none either
                # — otherwise the post that says "watching, not buying yet"
                # arrives on the timeline stamped BUY.
                _png_marker = marker_index if variant == "signal" else None
                if not defer_media:
                    _attach_chart_media(
                        _fc, closes=closes, dates=dates, marker_index=_png_marker,
                        as_of=today, root=root, cfg=cfg,
                        subtitle=f"{cashtag} · {'signal' if variant == 'signal' else 'tape'}")
                else:
                    # Everything raster_plan_media needs to finish the job later.
                    _fc["_defer"] = {
                        "closes": closes, "dates": dates,
                        "marker_index": _png_marker,
                        "subtitle": f"{cashtag} · {'signal' if variant == 'signal' else 'tape'}",
                    }
                featured_charts.append(_fc)

                chart_id_counter += 1

    # ── Confluence-sourced signal posts (§3 confluence→chart-post loop) ───────
    # Read fired combos from tech_confluence.json. Fail-soft: if the file is
    # absent or has no fresh fired combos, Prophet posts still flow unchanged.
    #
    # REACH-LANE BUDGET, counted separately from the ticker-post lane above.
    # These three lanes (confluence / theme_list watchlist cards / mover cards)
    # used to measure headroom as `len(featured_charts) < 8`, which worked only
    # while the ticker lane was capped at 6. Now that every D1 ticker post gets a
    # card, a shared counter would starve the reach lanes to zero on the first
    # busy desk — so they get their own allowance, unchanged at 8.
    _REACH_CHART_CAP = 8
    _ticker_charts_n = len(featured_charts)

    # THE MOVERS/THEME RESERVE (defect closed 2026-07-31; cap TOTAL unchanged).
    #
    # The three reach lanes drew on one 8-card allowance in SOURCE ORDER, and
    # confluence is written first. On the 2026-07-31 plan it took all 8 and the
    # movers/theme desk got zero cards. That is the worst possible split of this
    # budget, for a reason stated by the confluence lane's own census note
    # (`_confluence_census`, ~line 1288): a confluence post slots itself CONF-NN
    # and the outbox emits only D1- slots, so NOTHING confluence renders has ever
    # reached the outbox or a timeline. Its cards are deliberately deferred for
    # exactly that reason.
    #
    # A mover/theme card is the opposite: `theme_list` and `mover` are in the
    # publisher's `_TICKER_ROLLUP_KINDS`, and `_bare_cashtag_post` refuses to
    # ship a cashtag-bearing post with no picture ("YOU WILL NOT SHIP THESE TEXT
    # ONLY" — operator, 2026-07-30). So a chartless mover is not a plainer post,
    # it is an UNPUBLISHABLE one. Giving the publishable lane the smaller half of
    # a budget spent by the unpublishable one is backwards.
    #
    # Reserved rather than reordered: the movers block reads `featured_charts`
    # and `chart_id_counter` that this block also advances, and moving ~350 lines
    # to reorder two producers is a far bigger change than fencing off the six
    # cards the movers desk can actually mint (up to 2 movers + 4 themes).
    # Confluence keeps what is left (2), still deferred, still free if it dies.
    _REACH_MOVERS_RESERVE = 6

    def _reach_headroom(reserve: int = 0) -> bool:
        """True while the reach lanes still have budget of their own.

        ``reserve`` is the slice of the cap the CALLER may not take — the movers/
        theme desk passes 0 (it may use the whole allowance), confluence passes
        `_REACH_MOVERS_RESERVE` so it cannot starve a lane that can publish.
        """
        return (len(featured_charts) - _ticker_charts_n) < (
            _REACH_CHART_CAP - max(0, reserve))

    confluence_posts_added: list[dict] = []  # for the summary block
    conf_charts_added = 0

    try:
        from engine.marketing.confluence_source import (
            load_confluence,
            fired_combo_signals,
            win_rate_hook,
        )

        _ohlcv_root_conf: str = str(root) if root is not None else "."
        conf = load_confluence(_ohlcv_root_conf)
        if conf is not None:
            fired = fired_combo_signals(
                conf,
                side="long",
                top_n=8,
                min_edge=0.05,
                max_age_days=10,
                today=today,
            )
            # Also get short-side fired combos
            fired_short = fired_combo_signals(
                conf,
                side="short",
                top_n=4,
                min_edge=0.05,
                max_age_days=10,
                today=today,
            )
            all_fired = fired + fired_short

            # Dedupe tickers already used by Prophet charts
            prophet_chart_tickers = {fc["ticker"] for fc in featured_charts}

            # Use the first ENABLED account's voice for confluence posts (a
            # planned desk must not own reach content — F3d).
            conf_voice = (
                enabled_rows[0].get("voice", "authoritative desk")
                if enabled_rows else "authoritative desk"
            )
            conf_account_id = enabled_rows[0].get("id", "confluence") if enabled_rows else "confluence"

            conf_item_counter = 1
            for sig in all_fired:
                conf_ticker = sig["ticker"]
                # Skip tickers already charted by Prophet
                if conf_ticker in prophet_chart_tickers:
                    continue

                headline, body = win_rate_hook(sig)
                cashtag = f"${conf_ticker}"

                # Assign a slot label (append after Prophet-generated slots)
                slot_label = f"CONF-{conf_item_counter:02d}"

                # Build ContentItem — signal type, confluence provenance
                conf_item = ContentItem(
                    id=f"post-conf-{conf_account_id}-{conf_item_counter:03d}",
                    type="signal",
                    account=conf_account_id,
                    cashtag=cashtag,
                    ticker=conf_ticker,
                    headline=headline,
                    body=body,
                    provenance="neural_web",
                    chart_id=None,
                    slot=slot_label,
                    status="drafted",
                    source="confluence",
                    combo_id=sig["combo_id"],
                )

                # Attempt v2 chart for this confluence ticker.
                # Only under the confluence SHARE of the reach cap: this lane
                # cannot publish what it renders (CONF-NN slots never emit), so
                # it must not spend the cards the movers/theme desk needs to be
                # publishable at all (see `_REACH_MOVERS_RESERVE`).
                if _reach_headroom(_REACH_MOVERS_RESERVE) and _ohlcv_root_conf:
                    from engine.marketing.chart_render import load_ohlcv_windowed, render_chart_v2
                    _windowed = load_ohlcv_windowed(conf_ticker, _ohlcv_root_conf)
                    ohlcv, _warmup = _windowed if _windowed else (None, 0)
                    if ohlcv is not None:
                        ohlcv_dates, ohlcv_o, ohlcv_h, ohlcv_l, ohlcv_c, ohlcv_v = ohlcv
                        # Marker at last_fire date if in window, else latest
                        conf_marker = len(ohlcv_dates) - 1
                        lf = sig.get("last_fire", "")
                        if lf and lf in ohlcv_dates:
                            conf_marker = ohlcv_dates.index(lf)

                        # ── M2 overlays for the confluence chart ──────────────
                        # Precedence: (1) explicit manual override on the sig dict
                        # [documented seam — a caller may pre-compute overlays and
                        # attach sig["m2_overlays"]]; (2) leg-family-driven liveness
                        # [F2: attach ONLY the overlay whose M2 leg actually fired —
                        # avwap iff a vwap_events leg fired, poc iff a
                        # volume_profile_events leg fired]; (3) config
                        # marketing.m2_overlays_always [force BOTH overlays on every
                        # confluence chart, for debugging/QA].
                        _MARKETING_CFG = (cfg or {}).get("marketing", {})
                        _m2_cfg_always_conf = bool(
                            _MARKETING_CFG.get("m2_overlays_always", False)
                        )
                        _m2_ovl_conf: dict = sig.get("m2_overlays") or {}  # (1) override
                        if not _m2_ovl_conf:
                            _leg_fams = set(sig.get("leg_families") or [])
                            _want_avwap = "vwap_events" in _leg_fams
                            _want_poc = "volume_profile_events" in _leg_fams
                            # (2) fire on a live M2 leg, or (3) config force-both.
                            if _want_avwap or _want_poc or _m2_cfg_always_conf:
                                try:
                                    from engine.marketing.chart_render import build_m2_overlays as _bm2c
                                    _built = _bm2c(
                                        conf_ticker, ohlcv_dates, ohlcv_o, ohlcv_h,
                                        ohlcv_l, ohlcv_c, ohlcv_v, _ohlcv_root_conf,
                                    )
                                except Exception:
                                    _built = {}
                                if _m2_cfg_always_conf:
                                    # Config override: pass whatever built (both).
                                    _m2_ovl_conf = _built
                                else:
                                    # Liveness: pass ONLY the fired overlay(s).
                                    _m2_ovl_conf = {
                                        "avwap_overlay": _built.get("avwap_overlay") if _want_avwap else None,
                                        "poc_overlay": _built.get("poc_overlay") if _want_poc else None,
                                    }

                        chart_id = f"chart-{chart_id_counter:03d}"
                        svg = render_chart_v2(
                            ticker=conf_ticker,
                            dates=ohlcv_dates,
                            o=ohlcv_o,
                            h=ohlcv_h,
                            l=ohlcv_l,
                            c=ohlcv_c,
                            volume=ohlcv_v,
                            timeframe="DAILY",
                            marker_index=conf_marker,
                            highlight_index=conf_marker,
                            pct_from_index=(conf_marker if (len(ohlcv_c) - 1 - (conf_marker or 0)) >= 5 else None),
                            show_indicators=True,
                            indicators=("volume", "macd"),
                            warmup=_warmup,
                            volume_overlay=True,   # volume embedded in the price pane
                            subpanel_h=190,        # tall, legible MACD pane
                            height=880,
                            company_name=conf_ticker,
                            logo_root=_ohlcv_root_conf,
                            avwap_overlay=_m2_ovl_conf.get("avwap_overlay"),
                            poc_overlay=_m2_ovl_conf.get("poc_overlay"),
                            cta=_card_cta,
                        )

                        conf_item.chart_id = chart_id
                        _conf_fc = {
                            "id": chart_id,
                            "ticker": conf_ticker,
                            "account": conf_account_id,
                            "cashtag": cashtag,
                            "marker_source": "last_fire" if (lf and lf in ohlcv_dates) else "latest",
                            "marker_date": ohlcv_dates[conf_marker] if conf_marker < len(ohlcv_dates) else "",
                            "marker_price": round(ohlcv_c[conf_marker], 4) if conf_marker < len(ohlcv_c) else 0.0,
                            "svg": svg,
                            "headline": headline,
                            "body": body,
                            "source": "confluence",
                            "combo_id": sig["combo_id"],
                        }
                        # DEFER LIKE EVERY OTHER TICKER CARD (2026-07-30).
                        #
                        # This called _attach_chart_media UNCONDITIONALLY, so the
                        # confluence lane rastered inline even when the governor
                        # passed defer_media=True — the whole point of which is
                        # that only cards on posts that SURVIVE cost a Chrome
                        # launch (~11.5s each).
                        #
                        # Confluence posts do not survive. On the committed
                        # 2026-07-30 plan the lane built 9 posts, rastered 8
                        # cards, and put ZERO items in any desk queue; the outbox
                        # has never held one. Worse, a card with no "_defer" blob
                        # reads to raster_plan_media as an already-rastered
                        # reach-lane card, so all 8 were KEPT in the artifact —
                        # eight Chrome launches (~92s of a ~67 min budget that is
                        # law) spent every night on pictures for posts that
                        # cannot ship, then carried in content_plan.json as if
                        # they had.
                        #
                        # Deferring makes the waste self-correcting rather than
                        # requiring the drop to be diagnosed first: if the post
                        # dies, raster_plan_media prunes the card and no launch is
                        # ever paid. If the lane is fixed, the card rasters
                        # exactly like a Prophet one. Either way this stops being
                        # a standing charge.
                        if not defer_media:
                            _attach_chart_media(
                                _conf_fc, closes=ohlcv_c, dates=ohlcv_dates,
                                marker_index=conf_marker, as_of=today,
                                root=root, cfg=cfg,
                                subtitle=f"{cashtag} · confluence")
                        else:
                            _conf_fc["_defer"] = {
                                "closes": ohlcv_c, "dates": ohlcv_dates,
                                "marker_index": conf_marker,
                                "subtitle": f"{cashtag} · confluence",
                            }
                        featured_charts.append(_conf_fc)
                        chart_id_counter += 1
                        conf_charts_added += 1
                        prophet_chart_tickers.add(conf_ticker)

                # Add to the first ENABLED account's queue (additive) — matches
                # conf_account_id above; a planned desk never receives it.
                if enabled_rows:
                    enabled_rows[0]["queue"].append(conf_item.as_dict())

                all_items.append(conf_item)
                confluence_posts_added.append({
                    "ticker": conf_ticker,
                    "combo_id": sig["combo_id"],
                    "win_rate": sig["win_rate"],
                    "edge": sig["edge"],
                })
                conf_item_counter += 1

    except Exception:  # noqa: BLE001
        # Fail-soft: confluence unavailable — Prophet posts unchanged
        pass

    # ── Strip neural_web mover/theme_list stubs ──────────────────────────────
    # The tilt-based queue builder creates stub mover/theme_list items for every
    # account. These have no real data and would produce empty-token copy. Only
    # movers_desk items may represent those types in the final plan.
    #
    # RUNS BEFORE THE INJECTION BELOW, and the order is load-bearing. It used to
    # run after, which meant the movers desk looked at a D1 ladder that was still
    # 28/28 booked — every rung the allocator had handed to a stub it was about
    # to delete — found no free rung, and dropped all six real reach items on the
    # floor. (Invisible until now: the desk's slots were MOVER-NN/THEME-NN, which
    # the outbox refuses anyway, so "seated" and "dropped" published the same
    # nothing.) Stripping first hands the injection exactly the rungs the tilt
    # allocated to `mover`/`theme_list` in the first place — the real posts land
    # where the allocator planned for them.
    for _acct_row in account_rows:
        _acct_row["queue"] = [
            _it for _it in _acct_row["queue"]
            if not (
                _it.get("type") in ("mover", "theme_list")
                and _it.get("provenance") != "movers_desk"
            )
        ]

    # ── Movers/theme desk — inject mover + theme_list items ──────────────────
    # Load heatmap data once; attach movers summary to content.movers block.
    # mover items get a real ticker from top_movers; theme_list items carry
    # a cashtags list (multi-cashtag). Both are descriptive ("here's what moved")
    # — NO live Prophet entry gate. Charts for mover items use the featured-chart
    # path (v2 candlestick). theme_list items get no chart (the list is the content).
    _movers_data: dict | None = None
    _movers_summary: dict = {
        "movers": [],
        "theme_lists": [],
        "note": "Heatmap data unavailable; mover/theme posts not generated.",
    }
    _mover_item_counter = 1
    # Declared OUTSIDE the fail-soft try below on purpose: the `all_items` fold
    # after it must run whatever the block raised. Anything already seated on a
    # desk queue when a later step (chart render, media attach) blew up is still
    # a queued post, and the plan summary has to say so.
    _seated_movers: list[dict] = []
    _seated_themes: list[dict] = []
    _reach_unseated = 0
    #: Why each reach item lost its rung, split by cause. "the ladder was full"
    #: (a distribution problem, fixed by rungs or desks) and "the card never
    #: rendered" (a render problem, fixed by budget or bars) cost the desk the
    #: identical slot and were reported as one number, so neither was ever
    #: actionable from the census alone.
    _reach_unseated_reasons: dict[str, int] = {}
    #: Per-desk pool of D1 rungs nothing has booked yet — built at distribution
    #: and MUTATED by the card-less unseat pass after the try block. Declared out
    #: here because that pass must run even when the movers block raised on its
    #: way to (or inside) the card renderers, which is exactly the case that
    #: leaves an item seated with chart_id still None.
    _reach_free: dict[str, list[str]] = {}

    try:
        from engine.marketing.movers_source import (
            load_movers,
            top_movers as _top_movers_fn,
            theme_lists as _theme_lists_fn,
            mover_facts as _mover_facts_fn,
            theme_facts as _theme_facts_fn,
        )
        _ohlcv_root_mv: str = str(root) if root is not None else "."
        _movers_data = load_movers(_ohlcv_root_mv)

        if _movers_data is not None:
            _radar_tier_map: dict | None = None
            try:
                if (cfg or {}).get("settings", {}).get("radar_tiers_enabled"):
                    from engine.marketing.radar_internal import load_cashtag_tiers as _lct
                    _tiers = _lct(Path(str(root)) if root is not None else Path("."))
                    if _tiers:
                        _radar_tier_map = {t: v["tier"] for t, v in (_tiers.get("tickers") or {}).items()}
            except Exception:  # noqa: BLE001
                _radar_tier_map = None
            # Load cashtag tiers for leading-theme weighting (fail-soft: absent → None)
            _cashtag_tiers_map: dict | None = None
            try:
                from engine.marketing.movers_source import _load_cashtag_tiers as _lct_mv
                _ct = _lct_mv(root)
                if _ct:
                    _cashtag_tiers_map = _ct
            except Exception:  # noqa: BLE001
                _cashtag_tiers_map = None

            _mv_result = _top_movers_fn(_movers_data, tier_map=_radar_tier_map)
            _tl_result = _theme_lists_fn(_movers_data, cashtag_tiers=_cashtag_tiers_map)

            # Determine the single biggest mover (prefer loser for reach — crashes > rallies)
            _all_movers_flat = _mv_result.get("losers", []) + _mv_result.get("gainers", [])
            _all_movers_flat.sort(key=lambda x: abs(x.get("pct", 0)), reverse=True)

            _mover_tickers_used: set[str] = set()
            _mover_items_for_queue: list[dict] = []

            # Build mover queue items — one per big mover (up to 2, biggest first)
            for _mv in _all_movers_flat[:2]:
                _mv_ticker = _mv["ticker"]
                if not _mv_ticker or _mv_ticker in _mover_tickers_used:
                    continue
                _mover_tickers_used.add(_mv_ticker)
                _mv_facts = _mover_facts_fn(_mv, _movers_data)
                _mv_top_fact = _mv_facts["facts"][0]["text"] if _mv_facts["facts"] else ""
                _mv_pct_str = f"{_mv['pct']:+.1f}%"
                _mv_headline = f"${_mv_ticker} {_mv_pct_str} today"
                # Direction-aware stance (doctrine v3): down = flush-watch, dry;
                # up = respect, don't chase. Same honest posture either way.
                #
                # These used to be ONE fixed sentence per direction, so every up
                # mover the desk ever posted ended "Strength worth respecting, not
                # chasing here." (retired as boilerplate 2026-07-30). Rotate on a
                # crc32 of the ticker: deterministic — the same name reads the same
                # way twice — but the batch no longer speaks in one voice.
                _mv_rot = zlib.crc32(str(_mv_ticker or "").encode("utf-8")) % 4
                if (_mv.get("pct") or 0) < 0:
                    _mv_body = f"{_mv_top_fact} " + (
                        "The dip buyers get to find out who was early. Watching how "
                        "it holds.",
                        "I'd rather be late here than early. Levels are on the chart.",
                        "No rush to be a hero on this one. Watching where it settles.",
                        "Nothing to do until it stops going down. Chart's below.",
                    )[_mv_rot]
                else:
                    _mv_body = f"{_mv_top_fact} " + (
                        "Good for anyone already in. I'm not paying this price.",
                        "Respect the move, don't pay for it. Levels are on the chart.",
                        "Nice if you were early. Late entries here get punished.",
                        "This is what leadership looks like while it lasts. Chart's below.",
                    )[_mv_rot]
                _mover_item_dict = {
                    "id": f"post-mover-{_mover_item_counter:03d}",
                    "type": "mover",
                    "account": enabled_rows[0]["id"] if enabled_rows else "flagship",
                    "cashtag": f"${_mv_ticker}",
                    "ticker": _mv_ticker,
                    "headline": _mv_headline,
                    "body": _mv_body,
                    "provenance": "movers_desk",
                    "chart_id": None,
                    # EMPTY UNTIL DISTRIBUTION — a real `D1-S<n>` ladder rung is
                    # assigned below, exactly as the filing/house-pick lane does.
                    # This used to read f"MOVER-{n:02d}", which meant the item
                    # could not be emitted at all: outbox.emit_from_content_plan
                    # skips every slot that does not start with "D1-" (one bare
                    # `continue`), so the Movers desk published NOTHING in its
                    # entire existence while every content_plan.json since
                    # 2026-07-19 carried mover+theme_list items in the queues.
                    "slot": "",
                    "status": "drafted",
                    "_mover_facts": _mv_facts,
                    "_mover_data": _mv,
                }
                _mover_items_for_queue.append(_mover_item_dict)
                _mover_item_counter += 1

            # Build theme_list queue items
            _theme_items_for_queue: list[dict] = []
            for _tl in _tl_result[:4]:
                _tl_ticker = f"theme_{_tl['theme'].lower().replace(' ', '_').replace('/', '_')}"
                _tl_facts = _theme_facts_fn(_tl)
                _tl_members = _tl["members"]
                _cashtags = [f"${m['ticker']}" for m in _tl_members[:10]]
                _cashtag_list_str = " ".join(_cashtags)
                _agg_str = f"{_tl['agg_pct']:+.1f}%"
                _member_list = " ".join(
                    f"${m['ticker']} {m['pct']:+.1f}%" for m in _tl_members[:8]
                    if m.get("pct") is not None
                )
                _tl_tone = _tl.get("tone") or ("selling off" if _tl["direction"] == "down" else "ripping")
                _tl_headline = f"{_tl['theme']} {_tl_tone}, {_agg_str} avg today"
                _tl_body = f"{_member_list} {_tl['question']}"
                _tl_item_dict = {
                    "id": f"post-theme-{_mover_item_counter:03d}",
                    "type": "theme_list",
                    "account": enabled_rows[0]["id"] if enabled_rows else "flagship",
                    "cashtag": _cashtags[0] if _cashtags else "",
                    "cashtags": _cashtags,
                    "ticker": "",
                    "headline": _tl_headline,
                    "body": _tl_body,
                    "provenance": "movers_desk",
                    "chart_id": None,
                    "slot": "",   # real D1 ladder rung assigned at distribution
                    "status": "drafted",
                    "_theme_data": _tl,
                    "_theme_facts": _tl_facts,
                }
                _theme_items_for_queue.append(_tl_item_dict)
                _mover_item_counter += 1

            # ── Distribution: real desks, REAL D1 LADDER RUNGS ────────────────
            # Round-robin across the desks so the WHOLE network posts reach
            # content — and each desk gets a DISTINCT theme / mover (different
            # cashtags => inherently distinctness-safe, no substantially-similar
            # cross-account risk). Cold-start reach comes from breadth of
            # coverage across the network, not one desk.
            #
            # THIS RUNS BEFORE THE CARD RENDERERS BELOW, and both reasons are
            # defects it closes:
            #   1. the slot. Every item minted here used to carry MOVER-NN /
            #      THEME-NN and outbox.emit_from_content_plan drops any slot that
            #      is not "D1-…", so the desk has never published a post. Seating
            #      the item first means the ladder rung — the thing that decides
            #      whether it can ship at all — is settled before a single card
            #      is rendered for it, and an item the ladder cannot seat costs
            #      no render (same rule the filing/house-pick lane follows).
            #   2. the account. The card entries below copy `_tl_item["account"]`
            #      into featured_charts; when distribution ran AFTER them, every
            #      theme card was stamped with enabled_rows[0] while the post it
            #      belongs to had been round-robined to a different desk.
            #
            # RUNG CHOICE — EARLIEST FREE, deliberately NOT "market hours". The
            # ladder is a Pacific clock (S1 = 4:00 AM … S28 = 5:30 PM PT) and the
            # nightly builds this plan AFTER the close, so every market-hours
            # rung for D1 is already in the past — and a past rung means DUE NOW:
            # the publisher's `_is_due` treats due-in-the-past as due, enqueue
            # clamps a scheduled_at earlier than its own created_at forward to
            # creation, and the publisher's min-gap floor does the spacing. The
            # earliest free rung is therefore the soonest this post can honestly
            # go out, which is exactly what a perishable "$X +5.2% today" needs.
            # A market-hours rung on any PRE-close run would instead be a real
            # future time — parking perishable copy, which is the failure that
            # quarantined two hot-tape movers on 2026-07-31 when their "right
            # now" died in an 8-hour queued stall. A desk whose D1 ladder is full
            # drops the item rather than double-book a time (§5.5: an empty rung
            # stays empty).
            if enabled_rows:
                # Round-robin across ENABLED desks only — a planned desk must
                # never receive reach content (F3d).
                _n_acct = len(enabled_rows)
                # Interleave movers and themes so early desks get a mix.
                from itertools import zip_longest as _zip_longest  # noqa: PLC0415
                _reach_items = []
                for _m, _t in _zip_longest(_mover_items_for_queue, _theme_items_for_queue):
                    if _t is not None:
                        _reach_items.append(_t)
                    if _m is not None:
                        _reach_items.append(_m)

                # Per-desk pool of D1 rungs nothing has booked yet — same
                # computation the filing lane runs a few hundred lines below.
                # (Declared above the try; filled here.)
                for _row in enabled_rows:
                    _used = {
                        str(_it.get("slot") or "").split("-", 1)[1]
                        for _it in (_row.get("queue") or [])
                        if str(_it.get("slot") or "").startswith("D1-")
                    }
                    _reach_free[str(_row.get("id") or "")] = [
                        _s for _s in _LADDER_SLOTS if _s not in _used]

                # THE ROUND-ROBIN INDEX IS A STARTING POINT, NOT AN ASSIGNMENT
                # (defect closed 2026-07-31). `enabled_rows[_idx % _n_acct]` used
                # to be final: the desk was chosen before anyone asked whether it
                # had a rung, so a single full desk dropped its whole share of the
                # reach batch while its neighbours sat on twenty-odd empty rungs.
                # The drop then reported "no free D1 rung", which was true of that
                # ONE desk and false of the network — the census read like a
                # capacity problem when it was an allocation problem.
                #
                # Now the item is OFFERED to each desk in turn starting at the
                # round-robin position and the first one with a free rung takes
                # it. Fairness is untouched (the walk still starts one desk
                # further along per item, so the lead desk still rotates), and
                # "unseated" now means what it says: every enabled desk is full.
                for _idx, _item in enumerate(_reach_items):
                    _seated_ok = False
                    for _off in range(_n_acct):
                        _acct = enabled_rows[(_idx + _off) % _n_acct]
                        _pool = _reach_free.get(str(_acct.get("id") or "")) or []
                        if not _pool:
                            continue
                        _item["account"] = _acct.get("id", "flagship")
                        _item["slot"] = f"D1-{_pool.pop(0)}"
                        _acct["queue"].append(_item)
                        if _item.get("type") == "mover":
                            _seated_movers.append(_item)
                        else:
                            _seated_themes.append(_item)
                        _seated_ok = True
                        break
                    if not _seated_ok:
                        _reach_unseated += 1
                        _reach_unseated_reasons["no_free_rung"] = (
                            _reach_unseated_reasons.get("no_free_rung", 0) + 1)

            # ── Watchlist card rendering for theme_list items ─────────────────
            # Each theme_list item gets an SVG watchlist card: rows from theme members
            # {ticker, price, pct_change}, subtitle = the item's stance line (question).
            # Card goes into featured_charts the same way signal charts do; chart_id
            # is attached to the item dict. SEATED items only — a card for a post
            # no desk queued is render budget spent on nothing.
            if _reach_headroom():
                try:
                    from engine.marketing.chart_render import render_watchlist_card as _rwc
                    for _tl_item in _seated_themes:
                        if not _reach_headroom():
                            break
                        _tl_data = _tl_item.get("_theme_data") or {}
                        _tl_members_raw = _tl_data.get("members") or []
                        # Build rows: {ticker, price=None (no close data here), pct_change}
                        _wl_rows = [
                            {
                                "ticker": _m.get("ticker", ""),
                                "price": None,   # heatmap has no absolute prices
                                "pct_change": _m.get("pct"),
                            }
                            for _m in _tl_members_raw[:8]
                            if _m.get("ticker")
                        ]
                        if not _wl_rows:
                            continue
                        _wl_title = _tl_data.get("theme", _tl_item.get("headline", ""))
                        _wl_subtitle = _tl_data.get("question", "")
                        _wl_svg = _rwc(
                            _wl_title,
                            _wl_rows,
                            # Pass the caller's root directly: None in tests (no
                            # logos written into the repo), real path on nightly.
                            logo_root=root,
                            subtitle=_wl_subtitle,
                            # Portrait 4:5 (1080×1350) — the tallest image X renders
                            # un-cropped on a phone timeline (mobile-first surface).
                            width=1080,
                            height=1350,
                            cta=_card_cta,
                        )
                        _wl_chart_id = f"chart-{chart_id_counter:03d}"
                        _tl_item["chart_id"] = _wl_chart_id
                        featured_charts.append({
                            "id": _wl_chart_id,
                            "ticker": "",
                            "account": _tl_item.get("account", ""),
                            "cashtag": _tl_item.get("cashtag", ""),
                            "marker_source": "theme_list",
                            "marker_date": today,
                            "marker_price": 0.0,
                            "svg": _wl_svg,
                            "headline": _tl_item.get("headline", ""),
                            "body": _tl_item.get("body", ""),
                            "source": "theme_list",
                        })
                        chart_id_counter += 1
                except Exception:  # noqa: BLE001
                    pass  # fail-soft: watchlist card unavailable; theme posts unchanged

            # (The census used to be built HERE, between the two card renderers.
            # It now runs after the unseat pass below the try — see there.)

            # mover items: attempt v2 chart (same as Prophet signal flow).
            # SEATED movers only — see the distribution block above.
            if closes_loader is not None:
                from engine.marketing.chart_render import load_ohlcv_windowed, render_chart_v2, render_signal_chart
                for _mv_item in _seated_movers:
                    _mv_ticker = _mv_item["ticker"]
                    if not _reach_headroom():
                        break
                    _mv_closes = closes_loader(_mv_ticker)
                    if _mv_closes is None:
                        continue
                    _mv_dates, _mv_cls = _mv_closes
                    if len(_mv_cls) < 10:
                        continue
                    chart_id = f"chart-{chart_id_counter:03d}"
                    svg: str | None = None
                    _windowed = load_ohlcv_windowed(_mv_ticker, _ohlcv_root_mv)
                    ohlcv, _warmup = _windowed if _windowed else (None, 0)
                    if ohlcv is not None:
                        od, oo, oh, ol, oc, ov = ohlcv
                        svg = render_chart_v2(
                            ticker=_mv_ticker,
                            dates=od,
                            o=oo,
                            h=oh,
                            l=ol,
                            c=oc,
                            volume=ov,
                            timeframe="DAILY",
                            marker_index=len(od) - 1,
                            highlight_index=len(od) - 1,
                            show_indicators=True,
                            indicators=("volume", "macd"),
                            warmup=_warmup,
                            volume_overlay=True,   # volume embedded in the price pane
                            subpanel_h=190,        # tall, legible MACD pane
                            height=880,
                            company_name=_mv_ticker,
                            logo_root=_ohlcv_root_mv,
                            cta=_card_cta,
                        )
                    if svg is None:
                        svg = render_signal_chart(
                            ticker=_mv_ticker,
                            dates=_mv_dates,
                            closes=_mv_cls,
                            marker_index=len(_mv_cls) - 1,
                            subtitle=f"${_mv_ticker} · mover",
                        )
                    _mv_item["chart_id"] = chart_id
                    _mv_fc = {
                        "id": chart_id,
                        "ticker": _mv_ticker,
                        "account": _mv_item["account"],
                        "cashtag": f"${_mv_ticker}",
                        "marker_source": "latest",
                        "marker_date": _mv_dates[-1] if _mv_dates else "",
                        "marker_price": round(_mv_cls[-1], 4) if _mv_cls else 0.0,
                        "svg": svg,
                        "headline": _mv_item["headline"],
                        "body": _mv_item["body"],
                        "source": "mover",
                    }
                    _attach_chart_media(
                        _mv_fc, closes=_mv_cls, dates=_mv_dates,
                        marker_index=len(_mv_cls) - 1, as_of=today, root=root, cfg=cfg,
                        subtitle=f"${_mv_ticker} · mover")
                    featured_charts.append(_mv_fc)
                    chart_id_counter += 1

    except Exception:  # noqa: BLE001
        pass  # fail-soft — movers unavailable; Prophet posts unchanged

    # ── UNSEAT every card-less reach item ────────────────────────────────────
    # THE DEFECT (reproduced end-to-end 2026-07-31). Seating runs BEFORE the two
    # card renderers — deliberately, so the ladder rung is settled before a card
    # is paid for — and both renderers are fail-soft: the theme loop is wrapped in
    # `except Exception: pass`, the mover loop `continue`s on absent bars and
    # `break`s when the reach budget runs out, and neither runs at all when
    # `closes_loader` is None or the block above raised on its way here. Any of
    # those leaves the item sitting on a real D1 rung with `chart_id` still None.
    #
    # `mover` and `theme_list` are bare-cashtag kinds — they are in the
    # publisher's `_TICKER_ROLLUP_KINDS`, and `_bare_cashtag_post` refuses to ship
    # a cashtag-bearing post with no picture ("YOU WILL NOT SHIP THESE TEXT ONLY"
    # — operator, 2026-07-30). So a chartless mover is not a plainer post, it is a
    # post that is TERMINALLY QUARANTINED at dispatch. It still consumed its
    # desk's rung and its share of the day cap on the way there, and the census
    # still counted it as queued supply — a plan that reports six reach posts and
    # delivers four, with no line anywhere saying which two died or why.
    #
    # SAME LAW AS THE PUBLISH-TIME LANE, which already refuses to build an item
    # whose card would not host ("better no post than a naked ticker post" —
    # publish_time_content's module header). The plan must never EMIT a chartless
    # mover/theme either. Unseating is the plan-time form of that law: the item
    # leaves the queue, its rung goes back to the pool for a producer that can
    # actually fill it, and the drop is counted with its reason.
    #
    # RUNS OUTSIDE THE TRY on purpose. The case that most reliably produces a
    # card-less seated item is the renderer raising, which jumps straight to the
    # `except: pass` above — a pass placed inside the block would be skipped by
    # exactly the failure it exists to clean up.

    # "Carded" is CHART PRESENT IN `featured_charts`, not merely `chart_id` set.
    # The mover loop stamps `_mv_item["chart_id"]` a few statements before it
    # appends the chart dict, and `_attach_chart_media` sits between the two — so
    # a raise there leaves an id pointing at a card that was never rendered, and
    # a `chart_id is not None` test would call that item carded and ship it bare.
    _chart_ids_rendered = {str(_fc.get("id") or "") for _fc in featured_charts}

    def _reach_is_carded(_it: dict) -> bool:
        _cid = str(_it.get("chart_id") or "")
        return bool(_cid) and _cid in _chart_ids_rendered

    _reach_cardless: list[dict] = []
    for _seated_list in (_seated_movers, _seated_themes):
        _kept = [_it for _it in _seated_list if _reach_is_carded(_it)]
        _reach_cardless.extend(_it for _it in _seated_list if not _reach_is_carded(_it))
        _seated_list[:] = _kept

    if _reach_cardless:
        _rows_by_id = {str(_r.get("id") or ""): _r for _r in enabled_rows}
        for _it in _reach_cardless:
            _acct_id = str(_it.get("account") or "")
            _row = _rows_by_id.get(_acct_id)
            if _row is not None:
                # Identity comparison, not id-field equality: the queue holds the
                # very dict object seated above, and two producers could in
                # principle mint the same id string.
                _row["queue"] = [_q for _q in (_row.get("queue") or []) if _q is not _it]
            # Return the rung to the pool, earliest-first order preserved. The
            # filing lane below recomputes its own pool from the queues, so it
            # sees the freed rung either way; this keeps `_reach_free` honest for
            # anything that reads it after this point and makes the "returned"
            # half of the fix inspectable rather than incidental.
            _slot_str = str(_it.get("slot") or "")
            if _slot_str.startswith("D1-"):
                _rung = _slot_str.split("-", 1)[1]
                _pool_back = _reach_free.get(_acct_id)
                if _pool_back is not None and _rung not in _pool_back:
                    _pool_back.append(_rung)
                    _pool_back.sort(
                        key=lambda _s: _LADDER_SLOTS.index(_s)
                        if _s in _LADDER_SLOTS else len(_LADDER_SLOTS))
            _it["slot"] = ""
            _it["status"] = "unseated_no_card"
            _reach_unseated += 1
            _reach_unseated_reasons["no_card"] = (
                _reach_unseated_reasons.get("no_card", 0) + 1)

        # Bare line-start print, NEVER through a logger — every builder here logs
        # with a prefixing format, so `log.warning("::warning …")` emits
        # "WARNING ::warning …" and GitHub silently drops it. flush because
        # stdout is block-buffered when piped in Actions.
        print(f"::warning title=reach-cardless-unseated::"
              f"{len(_reach_cardless)} mover/theme_list reach item(s) ended "
              f"card-less and were unseated (D1 rungs returned to the pool). A "
              f"bare-cashtag post with no picture is terminally quarantined at "
              f"dispatch, so emitting it would spend a day-cap slot on nothing.",
              flush=True)

    # ── The movers census — SEATED AND CARDED, at plan time ──────────────────
    # THE CENSUS IS WHAT WAS SEATED, not what was minted. A minted item the
    # ladder could not take is not a post; reporting it as one is the same
    # false-supply reading the MOVER-NN slot bug produced for two weeks (queues
    # full of items, outbox empty, census saying "2 mover posts, 4 theme_list
    # posts generated" every night).
    #
    # MOVED OUT OF THE TRY BLOCK (2026-07-31). It used to be built between the
    # two card renderers, which meant it was a snapshot of a moment that had not
    # finished happening: the mover chart loop ran after it, and the card-less
    # unseat pass above runs after that. Building it here is the first point at
    # which `_seated_movers` / `_seated_themes` are final.
    #
    # "AT PLAN TIME" IS THE HONEST QUALIFIER, and the note says so. `apply_reuse_
    # budget` runs several hundred lines below and can still DELETE a seated
    # mover from its desk's queue (the ×5-ARES fix), and the v2 writer can drop
    # one more. Those cuts have their own counters in the plan summary and this
    # block cannot see them — it is upstream of both. Naming the boundary is the
    # fix; pretending the number is final is what made it wrong.
    if _movers_data is not None:
        _movers_summary = {
            "movers": [
                {
                    "ticker": it["ticker"],
                    "pct": it["_mover_data"]["pct"],
                    "sector": it["_mover_data"].get("sector", ""),
                }
                for it in _seated_movers
            ],
            "theme_lists": [
                {
                    "theme": it["_theme_data"]["theme"],
                    "direction": it["_theme_data"]["direction"],
                    "agg_pct": it["_theme_data"]["agg_pct"],
                    "n_members": len(it["_theme_data"]["members"]),
                }
                for it in _seated_themes
            ],
            "unseated": _reach_unseated,
            "unseated_reasons": dict(_reach_unseated_reasons),
            # Rungs still unbooked when distribution finished, per desk. THE
            # AUDIT FOR `no_free_rung`: that reason is only honest when the whole
            # network is out of rungs, and this is the number that says whether
            # it was. Pre-2026-07-31 the round-robin index was final, so a single
            # full desk dropped its share of the batch while this map still
            # showed twenty-odd free rungs on its neighbours — the census read
            # like a capacity problem when it was an allocation problem. (Cards
            # returned by the unseat pass are added back here, so a desk can show
            # headroom that only opened up after the renderers ran.)
            "free_rungs": {_k: len(_v) for _k, _v in _reach_free.items()},
            "note": (
                f"{len(_seated_movers)} mover posts, "
                f"{len(_seated_themes)} theme_list posts seated on the D1 "
                f"ladder with a card, at plan time; reuse-budget cuts are "
                f"reported separately"
                + (f". {_reach_unseated} unseated ("
                   + ", ".join(f"{_k}={_v}" for _k, _v
                               in sorted(_reach_unseated_reasons.items()))
                   + ")." if _reach_unseated else ".")
            ),
        }

    # ── Movers/theme items join `all_items` (the plan's own census) ───────────
    # THE BLIND SPOT THIS CLOSES. `all_items` is what feeds `distinctness()`,
    # `total_posts` and `signal_posts`, and the movers desk was the only producer
    # that appended straight to `acct_row["queue"]` without extending it. So a
    # night whose ONLY output was reach content reported `total_posts: 0` — the
    # identical false-empty reading the DeepSeek outage produced, which is the
    # signal `_alarm_on_a_planless_night` exists to fire on. It also meant the
    # cross-desk distinctness check never saw a single mover or theme post.
    #
    # Built from the SEATED dicts (they carry the final account + D1 slot) and
    # keyed by `id`, which is what the two post-budget reconciliations below
    # filter on — an item the reuse budget or the writer deletes from a queue
    # drops out of `all_items` with everything else. `chart_id` is snapshotted
    # here and may be filled in on the queue dict afterwards; nothing reads
    # `ContentItem.chart_id` (distinctness reads type/account/ticker/body, the
    # chart census reads `featured_charts`), so the two cannot disagree where it
    # would matter.
    for _reach_dict in (*_seated_movers, *_seated_themes):
        all_items.append(ContentItem(
            id=str(_reach_dict.get("id") or ""),
            type=str(_reach_dict.get("type") or ""),
            account=str(_reach_dict.get("account") or ""),
            cashtag=str(_reach_dict.get("cashtag") or ""),
            ticker=str(_reach_dict.get("ticker") or ""),
            headline=str(_reach_dict.get("headline") or ""),
            body=str(_reach_dict.get("body") or ""),
            provenance=str(_reach_dict.get("provenance") or "movers_desk"),
            chart_id=_reach_dict.get("chart_id"),
            slot=str(_reach_dict.get("slot") or ""),
            status=str(_reach_dict.get("status") or "drafted"),
        ))

    # (The neural_web mover/theme_list stub strip that used to sit here now
    # runs BEFORE the movers injection — that block explains why the order
    # is load-bearing.)

    # ── Fact-locked filing lanes + house picks (XG-E2) ───────────────────────
    # Masterplan §10 lanes 6 and 7 (insider Form 4, politician trades), plus the
    # operator's 2026-07-29 ruling that our OWN pick engines are post sources.
    #
    # PLACED HERE ON PURPOSE — after every other producer, before the budget.
    # These are PLANNED kinds, so they must sit inside `apply_reuse_budget`,
    # `assign_shapes` and the v2 writer exactly as a Prophet item does. Putting
    # them after the budget would hand two lanes a private exemption from the
    # ×5-ARES fix; putting them before the mover strip would let the stub filter
    # walk over them.
    #
    # COOLDOWN IS APPLIED AT SOURCE (`cooled=_cooled_watch`), not downstream.
    # These lanes get two slots a day between them: a lane that spends both on
    # names a desk posted on Monday is a lane that publishes nothing, so the
    # LKFN-class deferral happens while there are still other candidates to pick.
    #
    # Fail-soft as one unit: an unreadable parquet or an absent site artifact
    # costs these lanes and leaves the rest of the plan untouched.
    _filing_summary: dict = {"congress": 0, "insider": 0, "house_picks": 0}
    #: Exception TYPE name when the block below crashed, "" when it ran clean.
    #: The census needs the two apart: `{"congress": 0, "insider": 0}` reads as
    #: "no candidates tonight" whether the feeds were empty or the lane died on
    #: line one, so two live lanes could go dark for weeks behind a green nightly.
    _filing_error: str = ""
    try:
        from engine.marketing.congress_feed import candidates as _congress_candidates
        from engine.marketing.insider_feed import candidates as _insider_candidates
        from engine.marketing.house_picks import house_picks as _house_picks

        _filing_root = root if root is not None else "."
        _filing_items: list[dict] = []
        _filing_counter = 1

        def _filing_chart(_tkr: str) -> tuple[str, list, list] | None:
            """A TAPE card for a filing/pick ticker — (svg, dates, closes) or None.

            TAPE, NOT SIGNAL, and the two differences below are the whole point:

            * **No marker, no highlight, no % callout.** A filing post makes no
              entry claim — "Rep. Public bought NVDA six weeks ago" and "our
              momentum screen has this name" are descriptions, not calls. The
              Prophet path draws those only for `variant == "signal"` for
              exactly this reason ("marking a 'not buying yet' post with a SETUP
              pill is the lie this split exists to prevent"), and a filing post
              has even less claim behind it than a watchlist one.
            * **No `render_signal_chart` fallback.** The v1 card hard-draws a
              green BUY label at the marker. On a congressional-disclosure post
              that is a fabricated recommendation attached to a named
              politician's trade — so a ticker with no v2 render gets NO chart,
              and the caller decides whether the post can live without one.

            RETURNS THE OHLCV WINDOW, not closes_loader's series. `_d`/`_c` are
            used only as the length gate (a name with under ten sessions is not
            worth a card); the bars the SVG is actually drawn from are `_od`/`_oc`
            and those are what the caller must stamp and what the Chrome-less
            legacy raster must redraw. Returning the other series made the marker
            date/price describe a different window than the card and gave the
            fallback PNG a different stretch of tape than the preview showed.
            """
            if closes_loader is None:
                return None
            try:
                _cl = closes_loader(_tkr)
                if _cl is None:
                    return None
                _d, _c = _cl
                if len(_c) < 10:
                    return None
                from engine.marketing.chart_render import (  # noqa: PLC0415
                    load_ohlcv_windowed, render_chart_v2,
                )
                _w = load_ohlcv_windowed(_tkr, str(_filing_root))
                _ohlcv, _warm = _w if _w else (None, 0)
                if _ohlcv is None:
                    return None
                _od, _oo, _oh, _ol, _oc, _ov = _ohlcv
                _svg = render_chart_v2(
                    ticker=_tkr, dates=_od, o=_oo, h=_oh, l=_ol, c=_oc,
                    volume=_ov, timeframe="DAILY",
                    marker_index=None, highlight_index=None, pct_from_index=None,
                    show_indicators=True, indicators=("volume", "macd"),
                    warmup=_warm, volume_overlay=True, subpanel_h=190,
                    height=880, company_name=_tkr,
                    logo_root=str(_filing_root), cta=_card_cta,
                )
                return (_svg, list(_od), list(_oc)) if _svg else None
            except Exception:  # noqa: BLE001
                return None

        # Tickers the plan has already claimed tonight — house picks are EXTRA
        # supply and must never displace a name a producer already put up.
        _claimed: set[str] = {
            str(_it.get("ticker") or "").upper()
            for _row in account_rows for _it in (_row.get("queue") or [])
            if _it.get("ticker")
        }

        for _kind, _fetch in (
            ("congress", _congress_candidates),
            ("insider", _insider_candidates),
        ):
            # `exclude=_claimed` is re-read on EACH fetch, so the insider lane
            # also sees the names congress just took. Without it a desk could
            # post a Prophet signal, a congressional disclosure and a Form 4 on
            # the same ticker in one evening — one name, three posts, from one
            # account. House picks have had this guard since day one (`exclude=`
            # at the `_house_picks` call below); these two lanes did not.
            for _cand in (_fetch(_filing_root, today=today, cfg=cfg,
                                 cooled=_cooled_watch,
                                 exclude=frozenset(_claimed)) or []):
                _tkr = str(_cand.get("ticker") or "").upper()
                if not _tkr or _tkr in _claimed:
                    # Second belt: two candidates for one ticker inside a single
                    # fetch batch are filtered here, since `exclude` was frozen
                    # before the batch was walked.
                    continue
                _filing_items.append({
                    "id": f"post-{_kind}-{_filing_counter:03d}",
                    "type": _kind,
                    "account": enabled_rows[0]["id"] if enabled_rows else "flagship",
                    "cashtag": f"${_tkr}",
                    "ticker": _tkr,
                    # Placeholder copy only. The v2 writer replaces both from the
                    # fact packet, and under the no-fallback law an item that
                    # never reaches the writer is DROPPED at emit rather than
                    # shipping these strings.
                    "headline": f"${_tkr} filing",
                    "body": (_cand.get("facts", {}).get("facts") or [{}])[0].get("text", ""),
                    "provenance": f"{_kind}_desk",
                    "chart_id": None,
                    # Assigned at distribution below — it MUST be a real D1
                    # ladder slot. `emit_from_content_plan` only processes
                    # `D1-`-prefixed items, so a "CONG-01"-style label (the
                    # confluence/mover convention, correct for publish-time
                    # lanes) would build the item, plan it, cost a model call
                    # and then silently never reach the outbox.
                    "slot": "",
                    "status": "drafted",
                    "source": _kind,
                    #: Which LANE produced this, for the census. Distinct from
                    #: `source`, which a house pick sets to its engine name.
                    "_lane": _kind,
                    # Read back in the context loop below — the filing packet IS
                    # the post, so it must win over the generic chart facts.
                    "_filing_facts": _cand.get("facts") or {},
                    "_filing_data": {k: v for k, v in _cand.items() if k != "facts"},
                    # OPPORTUNISTIC, never gating. `congress`/`insider` are not
                    # in the publisher's `_CHART_BEARING_KINDS`, so a bare filing
                    # post ships as text rather than deferring — a chart makes it
                    # better, its absence must not silence the lane.
                    "_filing_chart": _filing_chart(_tkr),
                })
                _claimed.add(_tkr)
                _filing_summary[_kind] += 1
                _filing_counter += 1

        # House picks ride the EXISTING watchlist kind — additional fact supply,
        # no new kind, no writer change, no gate of their own.
        _pick_counter = 1
        for _pick in (_house_picks(_filing_root, today=today, cfg=cfg,
                                   cooled=_cooled_watch, exclude=frozenset(_claimed)) or []):
            _tkr = str(_pick.get("ticker") or "").upper()
            if not _tkr:
                continue
            # CHART REQUIRED, and this is the difference that matters. A house
            # pick rides the `watchlist` kind, which IS in the publisher's
            # `_CHART_BEARING_KINDS` — a chartless one does not ship, it DEFERS
            # for three days and then quarantines as `expired_no_media`, every
            # night, forever. The charting loop that would have served it runs
            # far above this splice, so the chart is rendered here and a pick
            # that cannot get one is never created (§5.5: an empty rung stays
            # empty; it does not fill with a post that cannot publish).
            _pick_chart = _filing_chart(_tkr)
            if _pick_chart is None:
                continue
            _filing_items.append({
                "id": f"post-housepick-{_pick_counter:03d}",
                "type": "watchlist",
                "account": enabled_rows[0]["id"] if enabled_rows else "flagship",
                "cashtag": f"${_tkr}",
                "ticker": _tkr,
                "headline": f"${_tkr} on the board",
                "body": (_pick.get("facts", {}).get("facts") or [{}])[0].get("text", ""),
                "provenance": "house_picks",
                "chart_id": None,
                "slot": "",   # a real D1 ladder slot is assigned at distribution
                "status": "drafted",
                "source": _pick.get("engine", "house_picks"),
                "_lane": "house_picks",
                "_filing_facts": _pick.get("facts") or {},
                "_filing_data": {k: v for k, v in _pick.items() if k != "facts"},
                "_filing_chart": _pick_chart,
            })
            _claimed.add(_tkr)
            _filing_summary["house_picks"] += 1
            _pick_counter += 1

        # Round-robin across ENABLED desks (a planned desk must never receive
        # this content — F3d), same distribution the reach lanes use, but with a
        # REAL D1 ladder slot taken from what each desk has not already booked.
        # A desk whose D1 ladder is full drops the item rather than double-books
        # a time: supply-honest volume means an empty rung stays empty (§5.5).
        if enabled_rows and _filing_items:
            _free: dict[str, list[str]] = {}
            for _row in enabled_rows:
                _used = {
                    str(_it.get("slot") or "").split("-", 1)[1]
                    for _it in (_row.get("queue") or [])
                    if str(_it.get("slot") or "").startswith("D1-")
                }
                _free[str(_row.get("id") or "")] = [
                    _s for _s in _LADDER_SLOTS if _s not in _used]
            for _idx, _item in enumerate(_filing_items):
                _acct = enabled_rows[_idx % len(enabled_rows)]
                _acct_id = str(_acct.get("id") or "")
                _pool = _free.get(_acct_id) or []
                if not _pool:
                    # Keyed on `_lane`, NOT `source`: a house pick's `source` is
                    # its engine name ("impulse"), so decrementing by `source`
                    # invented a counter key and left the census overstating a
                    # lane that had just dropped an item.
                    _lane_key = str(_item.get("_lane") or "")
                    if _lane_key in _filing_summary:
                        _filing_summary[_lane_key] = max(_filing_summary[_lane_key] - 1, 0)
                    continue
                _item["account"] = _acct.get("id", "flagship")
                _item["slot"] = f"D1-{_pool.pop(0)}"

                # The chart joins `featured_charts` only now, because the entry
                # carries the owning account and a chart rendered for an item
                # that never made it onto a queue is render budget spent on
                # nothing.
                _chart = _item.pop("_filing_chart", None)
                if _chart is not None:
                    _svg, _cdates, _ccloses = _chart
                    _chart_id = f"chart-{chart_id_counter:03d}"
                    _item["chart_id"] = _chart_id
                    _fc_filing = {
                        "id": _chart_id,
                        "ticker": _item["ticker"],
                        "account": _item["account"],
                        "cashtag": _item.get("cashtag", ""),
                        # TAPE, declared. `variant` is what the chart-coverage
                        # guard reads to prove a no-claim post did not ship a
                        # setup card, and `marker_source: "none"` is the Prophet
                        # tape path's own spelling of "no claim, no anchor —
                        # these are the last N sessions as they are".
                        #
                        # marker_date/marker_price are the LAST BAR OF THE CARD.
                        # `_filing_chart` returns the OHLCV window it drew from,
                        # so this stamp, the drawn candles and the fallback
                        # raster all describe the same session; they used to be
                        # taken from closes_loader's separate series, which could
                        # end on a different date than the card showed.
                        "variant": "tape",
                        "marker_source": "none",
                        "marker_date": _cdates[-1] if _cdates else "",
                        "marker_price": round(_ccloses[-1], 4) if _ccloses else 0.0,
                        "svg": _svg,
                        "headline": _item.get("headline", ""),
                        "body": _item.get("body", ""),
                        "source": str(_item.get("source") or "house_picks"),
                    }
                    # marker_index=None, and it is the whole point. This card is
                    # declared `tape`/`marker_source: none`; the SVG above draws
                    # no marker. Handing the legacy raster `len(_ccloses) - 1`
                    # meant that on any Chrome-less host (CI, the ubuntu publish
                    # runner, a raster timeout) media_publish fell back to a
                    # BUY-labelled v1 card and THAT is the PNG X received —
                    # exactly the fabricated recommendation this lane's docstring
                    # forbids, enforced until now only on the SVG branch.
                    _attach_chart_media(
                        _fc_filing, closes=_ccloses, dates=_cdates,
                        marker_index=None, as_of=today,
                        root=root, cfg=cfg,
                        subtitle=f"${_item['ticker']} · {_item.get('source', '')}")
                    featured_charts.append(_fc_filing)
                    chart_id_counter += 1

                _acct["queue"].append(_item)

        # Any item the ladder could not seat still holds a rendered chart; drop
        # the reference so the plan JSON does not carry an orphan SVG.
        for _item in _filing_items:
            _item.pop("_filing_chart", None)

        if any(_filing_summary.values()):
            # Bare print, start-of-line, flushed: a logger prefixes the line and
            # GitHub drops the annotation silently (tests/test_gh_annotation_line_start.py).
            print(
                f"::notice title=marketing_filing_lanes::congress="
                f"{_filing_summary['congress']} insider={_filing_summary['insider']} "
                f"house_picks={_filing_summary['house_picks']} planned for {today}",
                flush=True,
            )
    except Exception as _filing_exc:  # noqa: BLE001
        # STILL FAIL-SOFT — the rest of the plan stands — but never SILENT. This
        # runs in the nightly Actions job, so a bare print at line start is the
        # only form GitHub surfaces (a logger prefixes it and the annotation is
        # dropped; tests/test_gh_annotation_line_start.py).
        _filing_error = type(_filing_exc).__name__
        print(
            f"::warning title=marketing-filing-lanes::{_filing_error}: "
            f"{str(_filing_exc)[:200]} — congress/insider/house-pick supply is "
            f"DARK for {today}; the rest of the plan is unaffected",
            flush=True,
        )
    finally:
        # Written from `finally` so the census reports the lane even when the
        # block crashed before reaching its own summary line.
        _sel_report["filing_lanes"] = dict(_filing_summary)
        if _filing_error:
            _sel_report["filing_lanes"]["error"] = _filing_error

    # ── Fact-reuse budget + shape mixer (W1 selection layer) ──────────────────
    # Runs AFTER every producer has contributed (Prophet + confluence + movers)
    # and BEFORE any copy is written: the writer must receive the FINAL angle and
    # shape for its item, and an item the budget is about to delete must never
    # cost a model call. Both passes are deterministic and mutate the queues in
    # place. Confluence and movers items are inside the budget on purpose
    # (contract §Selection: "count confluence + movers items toward budgets") —
    # they are the same fact reaching a reader, whatever lane produced them.
    # Perishable copy booked past D1 goes first — before the budget, before the
    # mixer, and before any model call. It is supply the publisher's live-tape
    # gate was going to reject on the day (operator 2026-07-30); writing it costs
    # two model calls apiece to produce a post that cannot legally ship.
    _perish_counts = drop_stale_forward_bookings(account_rows, cfg=cfg)
    _sel_report["dropped_perishable_forward"] = _perish_counts.get(
        "dropped_perishable_forward", 0)
    _sel_report["dropped_perishable_by_kind"] = _perish_counts.get("by_kind", {})

    _budget_counts = apply_reuse_budget(account_rows, cfg=cfg, day_prefix="D1")
    _sel_report["dropped_ticker_budget"] = _budget_counts.get("dropped_ticker_budget", 0)
    _sel_report["dropped_signal_budget"] = _budget_counts.get("dropped_signal_budget", 0)
    _sel_report["dropped_filler_budget"] = _budget_counts.get("dropped_filler_budget", 0)
    # `after_budget` is the EMITTED-DAY post count: the budget only touches D1
    # (nothing else is ever emitted), so a whole-plan number here would move for
    # reasons unrelated to the budget and hide the one it exists to show.
    _sel_report["after_budget"] = sum(
        1 for row in account_rows for it in (row.get("queue") or [])
        if _slot_day(it.get("slot")) == "D1")
    _sel_report["posts_total"] = _budget_counts.get("after", 0)

    # `all_items` feeds distinctness() and the summary counts, so it has to track
    # the deletions or the plan would report volume it no longer carries.
    _surviving_ids = {
        str(it.get("id")) for row in account_rows for it in (row.get("queue") or [])
    }
    all_items = [i for i in all_items if i.id in _surviving_ids]

    _shape_mix_by_account: dict[str, dict[str, int]] = {}
    for _acct_row in account_rows:
        _acct_id = str(_acct_row.get("id") or "")
        _shape_mix_by_account[_acct_id] = assign_shapes(
            _acct_row.get("queue") or [],
            account=_acct_id,
            as_of=today,
            cfg=cfg,
            prior_mix=shape_ledger_prior_mix(_shape_ledger, _acct_id),
        )

    # ── Copywriter pass — replaces bot-voice templates with real copy ─────────
    # Runs AFTER all queue items are settled (Prophet + confluence + movers).
    # For signal items: verify live price gate; demote failed items to watchlist.
    # For receipt items: attach graded receipt; reallocate if none available.
    # For all items: build_context → write_posts_deterministic → replace headline/body.
    # mover/theme_list items go through a dedicated copywriter path (movers_facts).
    _copy_n_validated = 0
    _copy_n_fallback = 0
    _copy_violations_fixed = 0
    _copy_mode = "deterministic"
    _copy_signal_killed = 0
    _copy_n_receipts = 0
    # W1 no-fallback lane (masterplan §0 gate 1 / §4). `_copy_modes` is the
    # per-mode census the §0 gate 8 proof reads ("plan report shows llm mode >0,
    # det = 0 on planned kinds"); `_copy_dropped` is the by-stage drop census.
    _copy_modes: dict[str, int] = {}
    _copy_dropped: dict[str, int] = {}
    #: The same drops keyed by REASON, not stage. "provider" covers both "no
    #: credential was visible" and "the credential worked and the model
    #: returned nothing usable", and those have opposite fixes — see
    #: _provider_remedy.
    _copy_drop_reasons: dict[str, int] = {}
    _copy_written = 0
    _degenerate_dropped = 0
    _llm_required = llm_required(cfg)

    try:
        from engine.marketing.copywriter import (
            verify_signal_live,
            watch_reason_from_gate,
            build_context,
            write_posts_deterministic,
        )
        from engine.marketing.receipt_source import graded_receipts

        from engine.marketing.receipt_source import receipt_max_age_days

        _receipt_window = receipt_max_age_days(cfg)
        _graded_receipts_list = graded_receipts(
            plans or [], today=today, max_age_days=_receipt_window)
        _copy_n_receipts = len(_graded_receipts_list)
        _alarm_on_starved_receipts(
            plans or [], _copy_n_receipts, _receipt_window, today)
        _receipts_by_ticker: dict[str, dict] = {
            r["ticker"]: r for r in _graded_receipts_list
        }

        # Build a ticker→plan lookup for fast signal matching
        _plan_by_ticker: dict[str, dict] = {}
        for _p in (plans or []):
            _pt = _p.get("asset", "")
            if _pt and _pt not in _plan_by_ticker:
                _plan_by_ticker[_pt] = _p

        # Build account id → acct_cfg lookup for persona resolution (from the
        # effective account list — raw_accounts was replaced by eff_accounts when
        # the enabled/planned split landed).
        _acct_cfg_by_id: dict[str, dict] = {
            a.get("id", ""): a for a in eff_accounts
        }

        # ticker → texts already written TONIGHT on earlier desks. Threaded into
        # each context as `sibling_texts` so the writer can be told "different
        # angle, different shape, zero shared phrasing", and so Builder A's
        # validator can reject a ≥6-gram overlap with a sibling (contract
        # §Context contract). Accounts are processed sequentially, so account N
        # sees accounts 1..N-1 — which is exactly the cross-account sameness the
        # 07-29 batch shipped (one fact, five outfits, jaccard 0.467).
        _sibling_texts: dict[str, list[str]] = {}

        # Which live-gate failures may still become a watchlist post. Default:
        # runaway + underwater only — both are real, sayable states. `stale` and
        # `unverified` leave instead (see the gate branch below for the measured
        # reason). Config: selection.demotable_gate_reasons.
        _demotable = frozenset(
            str(r).strip().lower()
            for r in ((cfg or {}).get("selection") or {}).get(
                "demotable_gate_reasons", ["runaway", "underwater"])
            if str(r or "").strip()
        )
        from collections import Counter as _Ctr  # noqa: PLC0415
        _signal_gate_drops: dict[str, int] = {}
        _signal_gate_reasons = _Ctr()

        for acct_row in account_rows:
            acct_id = acct_row.get("id", "")
            acct_cfg = _acct_cfg_by_id.get(acct_id, {})
            voice = acct_cfg.get("voice", "authoritative desk")
            _personas_cfg = (cfg or {}).get("copywriter", {}).get("personas", {})
            persona = _personas_cfg.get(acct_id) or _personas_cfg.get(voice) or {}

            queue = acct_row.get("queue", [])

            # Phase 1: apply live gate and receipt attachment (mutates type in-place)
            for item_dict in queue:
                type_id = item_dict.get("type", "")
                ticker = item_dict.get("ticker", "")

                # --- Signal live gate (production only: closes_loader available) ---
                # Confluence-sourced signals are EXEMPT: they have no Prophet
                # entry/target, and fired_combo_signals() already freshness-gates
                # them on last_fire. Applying the entry-price gate to them killed
                # the highest-value posts (the $VST 86% combo demoted to watchlist).
                if (
                    type_id == "signal" and ticker and closes_loader is not None
                    and item_dict.get("source") != "confluence"
                ):
                    _plan = _plan_by_ticker.get(ticker) or {}
                    closes_result = closes_loader(ticker)
                    ok, reason = verify_signal_live(_plan, closes_result, today=today)
                    if not ok:
                        # NOT every failure earns a post (operator 2026-07-30).
                        # Measured: 168 of 335 watchlist posts in the live plan
                        # were demoted signals, 39 of 57 on the shipping day, and
                        # 125 of those failed for AGE — signals 12 to 20 days old
                        # against a 10-day ceiling. They all came out wearing the
                        # same proximity copy ("$X is close", "Watching $X, not
                        # buying yet", "$X is past me"), which is where the
                        # feed's "mechanically uniform" reading came from.
                        #
                        # A stale idea is not a watch, and a name we cannot price
                        # is not a watch either — there is nothing honest to say
                        # about them, so they leave. Runaway and underwater are
                        # REAL states with something true to say ("the entry I
                        # wanted is behind the tape"), so those still demote.
                        #
                        # This restores the rule apply_reuse_budget already
                        # states and this branch was breaking: "never re-typed
                        # into filler, because supply-honest volume means an
                        # empty rung stays empty."
                        _watch_cls = watch_reason_from_gate(reason)
                        if _watch_cls not in _demotable:
                            item_dict["_drop_stale_signal"] = reason
                            continue
                        # Demote to watchlist — runaway / underwater signal
                        item_dict["type"] = "watchlist"
                        item_dict["_live_gate_fail"] = reason
                        # WHY it failed decides what the copy may claim. The
                        # watchlist bank is proximity copy ("Near entry",
                        # "close, not triggered") — true for a name that has not
                        # reached the level, FALSE for one that blew through it.
                        # Not underscore-prefixed on purpose: it survives
                        # strip_scaffolding into the artifact, where the Outbox
                        # audit needs to see why a post is only a watch.
                        item_dict["watch_reason"] = watch_reason_from_gate(reason)
                        type_id = "watchlist"
                        _copy_signal_killed += 1

                # --- Receipt attachment (only demote if closes_loader is available
                #     and we could verify but have nothing; skip in test mode) ---
                _receipt = {}
                if type_id == "receipt" and ticker and closes_loader is not None:
                    _receipt = _receipts_by_ticker.get(ticker) or {}
                    if not _receipt:
                        # No graded receipt — reallocate to watchlist
                        item_dict["type"] = "watchlist"
                        type_id = "watchlist"
                elif type_id == "receipt" and ticker:
                    # Test mode: attach receipt if exists, else keep as receipt
                    _receipt = _receipts_by_ticker.get(ticker) or {}

                # Enrich item_dict with plan and receipt for build_context
                _plan = _plan_by_ticker.get(ticker) or {}
                item_dict["_plan"] = _plan
                item_dict["_receipt"] = _receipt

            # Drop the signals that failed for a reason no post can honestly
            # carry. Done HERE — after the gate, before Phase 2 builds a context
            # and long before the writer runs — so a dead idea never costs a
            # model call.
            _stale_dropped = [d for d in queue if d.get("_drop_stale_signal")]
            if _stale_dropped:
                queue = [d for d in queue if not d.get("_drop_stale_signal")]
                acct_row["queue"] = queue
                _signal_gate_drops[acct_id] = len(_stale_dropped)
                for _d in _stale_dropped:
                    _signal_gate_reasons[
                        watch_reason_from_gate(str(_d.get("_drop_stale_signal")))
                    ] += 1

            # Phase 2: build all contexts for this account (preserves type counter ordering)
            # Pre-compute market/sector/breadth/event facts once per account (not per item).
            # These are the fact sources for non-ticker content types (macro/event/watchlist).
            _mkt_root: str = str(root) if root is not None else "."
            _macro_facts_cache: dict = {}
            _sector_facts_cache: dict = {}
            _breadth_facts_cache: dict = {}
            _event_facts_cache: dict = {}
            try:
                from engine.marketing.market_facts import (
                    macro_facts as _macro_facts_fn,
                    sector_facts as _sector_facts_fn,
                    breadth_facts as _breadth_facts_fn,
                    event_facts as _event_facts_fn,
                    merge_facts as _merge_facts_fn,
                )
                _macro_facts_cache = _macro_facts_fn(_mkt_root)
                _sector_facts_cache = _sector_facts_fn(_mkt_root)
                _breadth_facts_cache = _breadth_facts_fn(_mkt_root)
                _event_facts_cache = _event_facts_fn(_mkt_root)
            except Exception:  # noqa: BLE001
                pass

            contexts: list[dict] = []
            # ITEMS THE WRITER IS ACTUALLY ASKED TO WRITE, in context order.
            # `posts` comes back index-aligned to `contexts`, so every zip below
            # pairs against THIS list, not against `queue` — see the note on
            # _is_writable_day for why they are no longer the same thing.
            _ctx_items: list[dict] = []
            for item_dict in queue:
                if not _is_writable_day(item_dict.get("slot"), cfg):
                    continue
                ticker = item_dict.get("ticker", "")
                type_id = item_dict.get("type", "")
                facts_data: dict = {}
                # XG-E2: a filing/house-pick item carries its OWN packet, and it
                # WINS over the chart facts. The packet is the post — a Form 4's
                # share arithmetic, a disclosure's reporting lag, a desk's
                # attribution — and the generic 90-bar chart facts would both
                # bury it (build_context shows the writer three facts) and hand
                # the model price levels the filing never mentioned.
                _filing_packet = item_dict.get("_filing_facts") or {}
                if _filing_packet.get("facts"):
                    facts_data = _filing_packet
                elif ticker and closes_loader is not None:
                    try:
                        from engine.marketing.chart_facts import compute_facts
                        from engine.marketing.chart_render import load_ohlcv
                        _ohlcv_root_cw: str = str(root) if root is not None else "."
                        # 252 BARS, NOT 90. chart_facts._fact_52w_high_low takes
                        # `window = min(252, n)` and then LABELS the result a
                        # "52-week high/low" — so a 90-bar load made it emit a
                        # ~4-month extreme under a 52-week name. Measured on the
                        # live stores: MSFT's real 52-week high is 551.05 and the
                        # 90-bar window reported 466.32 (18.2% low), CDW 18.6%,
                        # META 14.9%, TSLA 10.0%. Copy already in the queue read
                        # "$TSLA ... New 52-week low" and "$AAPL -0.6% off the
                        # 52-week high at 334.99" — claims a follower can
                        # disprove in one click, on an account whose whole
                        # product is being right about levels.
                        # The CHART still draws its own 90-bar window; this is the
                        # fact layer, and a year is what the word means.
                        _ohlcv = load_ohlcv(ticker, _ohlcv_root_cw, n=252)
                        if _ohlcv is not None:
                            _od, _oo, _oh, _ol, _oc, _ov = _ohlcv
                            facts_data = compute_facts(ticker, _od, _oo, _oh, _ol, _oc, _ov)
                    except Exception:  # noqa: BLE001
                        pass
                elif not ticker:
                    # Non-ticker post: attach market/regime/breadth facts by type
                    try:
                        from engine.marketing.market_facts import merge_facts as _merge_facts_fn
                        if type_id == "macro":
                            facts_data = _macro_facts_cache
                        elif type_id == "event":
                            facts_data = _event_facts_cache
                        elif type_id == "watchlist":
                            facts_data = _merge_facts_fn(
                                _breadth_facts_cache, _sector_facts_cache
                            )
                        # education posts: no market facts (conceptual, not data-driven)
                    except Exception:  # noqa: BLE001
                        pass

                # DEGENERATE-STAT GATE (masterplan §5.3, §0 gate 3h). A count
                # that saturates its universe ("231 of 231 names bullish") is a
                # definition, not a fact — it is dropped BEFORE the packet is
                # built so the writer never sees it and the numbers whitelist
                # never blesses it.
                #
                # THIS RUNS OVER EVERY FACT SOURCE, not just chart facts:
                # `facts_data` is the chart packet for a ticker item and the
                # macro / event / merged breadth+sector packet for a non-ticker
                # one, and the count facts that actually saturate live in the
                # market_facts family (sector breadth, tracked-name breadth).
                # Gating only the ticker branch would have left the gate pointed
                # at the one source that rarely trips it.
                facts_data, _n_degen = drop_degenerate_facts(
                    facts_data, band=selection_cfg(cfg)["degenerate_stat_band"])
                _degenerate_dropped += _n_degen

                ctx = build_context(
                    item_dict,
                    persona=persona or None,
                    facts=facts_data or None,
                    extra=None,
                )
                # Ensure voice and type are set on context for template lookup
                ctx["type"] = item_dict.get("type", ctx.get("type", ""))
                ctx["voice"] = voice
                # Carry slot for hash-based selection on ticker posts
                ctx["slot"] = item_dict.get("slot", "")
                # ── W1 writer contract (contract §Context contract) ───────────
                # shape/angle are the mixer's and the budget's verdicts; the
                # writer obeys them, it does not choose them. sibling_texts is
                # what earlier desks already said about this name tonight. `pack`
                # is the Hot Tape enrichment slice when present (absent → omit,
                # never a stub). cooldown_override_reason is the NEW FACT that
                # bought this repeat its slot, and the post must lead with it.
                ctx["shape"] = item_dict.get("shape") or ""
                ctx["angle"] = item_dict.get("angle") or angle_for(
                    item_dict.get("type", ""), 0)
                ctx["sibling_texts"] = list(_sibling_texts.get(ticker, [])) if ticker else []
                _pack = _packs.get(str(ticker).upper()) if ticker else None
                if _pack:
                    ctx["pack"] = _pack
                _override = _cooldown_overrides.get(str(ticker).upper()) if ticker else None
                if _override:
                    ctx["cooldown_override_reason"] = _override
                # Carry the plan date so the deterministic variant picker can
                # seed non-ticker rotation by CALENDAR DAY — otherwise a single
                # daily post (the event "read on today's move") always lands on
                # slot 0 and repeats verbatim night to night.
                ctx["as_of"] = today
                contexts.append(ctx)
                _ctx_items.append(item_dict)

            # Phase 3: the WRITER. Per-post model calls (write_posts_llm_v2 —
            # contract §Writer API); each result is
            # {"text","headline","body","mode","critic"} or
            # {"mode":"dropped","reasons":[...],"stage":"provider|validate|critic"}.
            #
            # WHY v2 REPLACED THE BATCH CALL (masterplan §1, §0 gate 2). v1 asked
            # for SIXTY posts in one 6000-token call — ~100 tokens per post for
            # ~10k tokens of required JSON. It truncated, the parse failed, the
            # function returned None, and every post silently fell back to
            # templates: the persona lane had been armed and credentialed since
            # the 2026-07-26 incident fix and had never once produced a live post.
            # Per-item calls mean one failure isolates to one item.
            #
            # A MUTE LANE IS NOT A DROP. v2 returns an all-`dropped`/stage
            # `provider` list when the lane is not armed (flag off, no env var,
            # no credentials) — the correct read of that is "nothing was written
            # tonight", not "every post failed the critic". So the lane's armed
            # state is checked HERE and the mute case never enters the drop
            # accounting: the plan is still built off templates so the admin can
            # review what would have shipped, and the reader-facing refusal lives
            # at outbox.emit, which will not queue a planned-kind item whose mode
            # is not llm* while copywriter.llm.required is on. Calling v2 on a
            # mute lane would also charge the plan 196 pointless "drops" per desk.
            _cw_cfg = dict((cfg or {}).get("copywriter", {}) or {})
            # §10 E3 writer hook. The exemplar-store PIN lives under `intel:` and
            # the writer is handed only the `copywriter:` block, so the pin has to
            # ride along or `copywriter.store_exemplar_block` can never see it and
            # the whole ratification chain dead-ends at the config line. Copied
            # (not aliased into the caller's dict) and read-only downstream.
            # Absent `intel:` -> no pin -> no exemplars, which is the dark default.
            if isinstance((cfg or {}).get("intel"), dict):
                _cw_cfg.setdefault("intel", cfg["intel"])
            _lane_armed = bool((_cw_cfg.get("llm") or {}).get("enabled", False)) and (
                os.environ.get("MARKETING_LLM_ENABLED", "").strip().lower()
                in ("1", "true", "yes")
            )
            posts: list[dict] = []
            _det_posts: list[dict] | None = None
            if _lane_armed:
                try:
                    from engine.marketing.copywriter import write_posts_llm_v2  # noqa: PLC0415
                    posts = list(write_posts_llm_v2(contexts, _cw_cfg, root=root) or [])
                except Exception:  # noqa: BLE001
                    posts = []
            if not posts:
                posts = write_posts_deterministic(contexts)
            else:
                _copy_mode = "llm"

            # Items the writer dropped are REMOVED from the queue (never
            # template-filled) while the no-fallback law is armed. Collected
            # first, deleted after the zips so queue↔posts stays index-aligned.
            _drop_ids: set[str] = set()

            for _idx, (item_dict, post) in enumerate(zip(_ctx_items, posts)):
                if not isinstance(post, dict):
                    continue
                if post.get("mode") == "dropped":
                    _stage = str(post.get("stage") or "unknown")
                    _copy_dropped[_stage] = _copy_dropped.get(_stage, 0) + 1
                    for _r in (post.get("reasons") or ["unknown"]):
                        _r = str(_r)
                        _copy_drop_reasons[_r] = _copy_drop_reasons.get(_r, 0) + 1
                    if _llm_required and str(item_dict.get("type") or "") in PLANNED_KINDS:
                        _drop_ids.add(str(item_dict.get("id")))
                        item_dict["_copy_mode"] = "dropped"
                        item_dict["_copy_drop_stage"] = _stage
                    else:
                        # Law disarmed (emergency escape hatch) or a non-planned
                        # kind: the deterministic bank is still allowed to speak.
                        if _det_posts is None:
                            _det_posts = write_posts_deterministic(contexts)
                        if _idx < len(_det_posts):
                            posts[_idx] = _det_posts[_idx]
                    continue
                _mode = str(post.get("mode") or "deterministic")
                _copy_modes[_mode] = _copy_modes.get(_mode, 0) + 1
                if _mode.startswith("llm"):
                    _copy_written += 1
                    _crit = post.get("critic")
                    if isinstance(_crit, dict):
                        item_dict["_copy_critic"] = _crit.get("verdict")
                    _tkr = str(item_dict.get("ticker") or "")
                    _txt = str(post.get("text") or "").strip()
                    if _tkr and _txt:
                        _sibling_texts.setdefault(_tkr, []).append(_txt)

            for item_dict, post in zip(_ctx_items, posts):
                if str(item_dict.get("id")) in _drop_ids:
                    continue  # writer dropped it; deleted from the queue below
                # Confluence signal posts keep the win_rate_hook copy — it is the
                # crown-jewel framing ("worked 86% of the time historically") and
                # the generic signal templates would inject empty Prophet fields
                # ("Entry . T1 .") since combos have no entry/target.
                #
                # THE MODE STAMP IS NOT COSMETIC. This lane never reaches the
                # writer, so under the no-fallback law its copy is template prose
                # on a planned kind and outbox.emit will refuse it. Stamping the
                # mode explicitly is what makes that refusal READABLE in the
                # emit census instead of an item that merely lacks a key.
                if item_dict.get("source") == "confluence" and item_dict.get("type") == "signal":
                    item_dict.setdefault("_copy_mode", "confluence_hook")
                    _copy_modes["confluence_hook"] = _copy_modes.get("confluence_hook", 0) + 1
                    _copy_n_validated += 1
                    continue
                # mover/theme_list items keep their movers-desk copy (the real
                # ticker/% are already in the headline/body from movers_source) —
                # but they STILL pass through validate_copy so the safety net
                # (banned vocab, invented numbers, cashtag rules, reply-bait "?")
                # gates them. A malformed reach post must never ship silently.
                if item_dict.get("provenance") == "movers_desk":
                    try:
                        from engine.marketing.copywriter import (  # noqa: PLC0415
                            build_context as _bc, validate_copy as _vc,
                        )
                        _mctx = _bc(item_dict, persona=persona,
                                    facts=item_dict.get("_theme_facts")
                                    or item_dict.get("_mover_facts"),
                                    extra=None)
                        _mviol = _vc(item_dict.get("headline", ""),
                                     item_dict.get("body", ""), _mctx)
                    except Exception:  # noqa: BLE001
                        _mviol = []
                    if _mviol:
                        item_dict["_copy_violations"] = _mviol
                        _copy_violations_fixed += len(_mviol)
                    item_dict.setdefault("_copy_mode", "movers_desk")
                    _copy_n_validated += 1
                    continue
                new_headline = post.get("headline", "")
                new_body = post.get("body", "")
                violations = post.get("violations", [])
                # v2 returns the shaped post as `text`; `headline` is "" for every
                # shape except two_part (contract §Shapes), so the historic
                # `headline AND body` guard would have rejected four shapes out of
                # five as "fallback" and kept the template copy. Body carries the
                # full shaped text (may contain \n); compose_text drops the empty
                # half at emit. The relaxed guard is scoped to llm* modes so the
                # deterministic lane's contract is byte-for-byte unchanged.
                _mode_out = str(post.get("mode") or "deterministic")
                if _mode_out.startswith("llm"):
                    if not new_body:
                        new_body = str(post.get("text") or "")
                    _accept = bool(new_body)
                else:
                    _accept = bool(new_headline and new_body)
                if _accept:
                    item_dict["headline"] = new_headline
                    item_dict["body"] = new_body
                    item_dict["_copy_mode"] = post.get("mode", "deterministic")
                    item_dict["_copy_violations"] = violations
                    if violations:
                        _copy_violations_fixed += len(violations)
                    _copy_n_validated += 1
                else:
                    _copy_n_fallback += 1

            # Delete the writer's drops. Done AFTER both zips so the queue and
            # the posts list stay index-aligned while they are being read.
            if _drop_ids:
                acct_row["queue"] = [d for d in queue
                                     if str(d.get("id")) not in _drop_ids]
                queue = acct_row["queue"]

            # Recount mix after type changes (signal→watchlist / receipt→watchlist)
            from collections import Counter as _Counter
            type_counts = _Counter(d.get("type", "") for d in queue)
            acct_row["mix_observed"] = dict(type_counts)

    except Exception:  # noqa: BLE001
        # Fail-soft: copywriter unavailable — old template copy survives
        _copy_mode = "fallback"

    # Second reconciliation of `all_items` — the writer's drops land after the
    # ── Batch auditor (operator 2026-07-30, one-week probation) ──────────────
    # The last gate, and the only one that reads a whole day at once. Runs AFTER
    # the copy exists (it judges words, not plans) and BEFORE the surviving-id
    # reconciliation below, so a cut post leaves the plan the same way every
    # other drop does.
    #
    # SCOPE: the whole plan horizon by default (copywriter.llm.auditor.max_day,
    # 0 = no limit). This was pinned to D1 in code on the reasoning that "D1 is
    # the sole day that has ever enqueued, so auditing the evergreen forward
    # tail would spend calls judging posts that cannot post." That is wrong for
    # the evergreen kinds: drop_stale_forward_bookings keeps watchlist/receipt
    # copy at the full seven-day horizon ON PURPOSE, and its own docstring
    # records that such a post reaches its slot ("by the time one of those posts
    # reached its slot the tape had moved"). Reaching the slot is shipping. On
    # the 2026-07-30 plan the D1 pin left 73 watchlist posts written,
    # forward-booked and never judged — and watchlist is both the biggest kind
    # and the one carrying the repetition the operator named.
    #
    # Per ACCOUNT, because "does this feed read like a bot" is a question about
    # one timeline. Judging six desks in one window would let a repeat across
    # two different accounts — which no reader sees — cut a good post.
    _audit_report: dict[str, Any] = {
        "ran": False, "kept": 0, "cut": 0, "unaudited": 0, "cuts": [], "notes": {},
    }
    _mono_cut = 0
    try:
        from engine.marketing import copy_auditor as _auditor  # noqa: PLC0415

        # ── Cost-monoculture trim (deterministic, runs BEFORE the auditor) ────
        # The fact-plus-cost law fixed "no reaction" and grew a new defect: a
        # live 8-post run passed 8/8 with SEVEN posts saying some version of "I
        # missed it". That is the retired stock closer one level up.
        #
        # Deterministic and not left to the auditor, whose `repetitive` criterion
        # describes this exactly but depends on a model noticing: three rounds of
        # prompt work moved the measured share only 0.88 -> 0.62. The cause is
        # the input mix, not the wording — every watchlist item is "a level on a
        # name we do not hold", so "I'm outside the move" is what the material
        # invites. Enforcement is the only thing that holds.
        for _row in account_rows:
            _q = _row.get("queue") or []
            if not _q:
                continue
            from engine.marketing.copywriter import (  # noqa: PLC0415
                trim_cost_monoculture as _trim_mono)
            _cut_idx = _trim_mono(
                [f"{d.get('headline') or ''} {d.get('body') or ''}".strip() for d in _q])
            if not _cut_idx:
                continue
            _cut_set = set(_cut_idx)
            _row["queue"] = [d for i, d in enumerate(_q) if i not in _cut_set]
            _mono_cut += len(_cut_idx)
            print(f"::warning title=marketing-cost-monoculture::"
                  f"{_row.get('id')}: cut {len(_cut_idx)} post(s) that repeated the "
                  f"same admission as the rest of the batch. A feed where every "
                  f"post says 'I missed it' reads as bot-written as one that ends "
                  f"on the same sentence.", flush=True)

        _win = _auditor.window_size(cfg)
        _max_day = _auditor.max_audit_day(cfg)
        _audit_report["max_day"] = _max_day
        _audit_report["cost_monoculture_cut"] = _mono_cut
        for _row in account_rows:
            _aid = str(_row.get("id") or "")
            _queue = _row.get("queue") or []
            # An unparseable slot is AUDITED, not skipped: the auditor is the
            # last read of the copy, and silently exempting a post because its
            # label did not parse is exactly how the D1 pin hid 73 of them.
            _in_scope = [
                d for d in _queue
                if _max_day is None
                or (_slot_day_num(d.get("slot")) or 1) <= _max_day
            ]
            if not _in_scope:
                continue
            _cut_ids: set[str] = set()
            for _off in range(0, len(_in_scope), _win):
                _chunk = _in_scope[_off:_off + _win]
                _res = _auditor.audit_batch(
                    [{"account": _aid, "kind": d.get("type"),
                      "text": f"{d.get('headline') or ''}\n{d.get('body') or ''}".strip()}
                     for d in _chunk],
                    cfg=cfg,
                )
                _audit_report["ran"] = _audit_report["ran"] or bool(_res.get("ok"))
                _audit_report["unaudited"] += int(_res.get("unaudited") or 0)
                if _res.get("batch_note"):
                    _audit_report["notes"][_aid] = _res["batch_note"]
                for _d, _v in zip(_chunk, _res.get("verdicts") or []):
                    if _v.get("verdict") != "cut":
                        continue
                    _cut_ids.add(str(_d.get("id")))
                    _d["_audit_cut"] = _v.get("codes") or []
                    _audit_report["cuts"].append({
                        "id": _d.get("id"), "account": _aid,
                        "kind": _d.get("type"), "codes": _v.get("codes") or [],
                        "note": _v.get("note") or "",
                        "text": f"{_d.get('headline') or ''} {_d.get('body') or ''}".strip()[:280],
                    })
            if _cut_ids:
                _row["queue"] = [d for d in _queue if str(d.get("id")) not in _cut_ids]
                _audit_report["cut"] += len(_cut_ids)
        # Counted over the SAME scope the auditor read. This used to hard-code
        # D1 and would now report "kept: 19" for a run that judged 92 — a
        # console number that quietly contradicts the work done.
        _audit_report["kept"] = sum(
            1 for r in account_rows for d in (r.get("queue") or [])
            if _max_day is None or (_slot_day_num(d.get("slot")) or 1) <= _max_day)
    except Exception as exc:  # noqa: BLE001 — an auditor must never break a night
        _audit_report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"::warning title=marketing-auditor-failed::batch audit did not "
              f"run: {type(exc).__name__}", flush=True)

    # budget's, and both have to be reflected in distinctness() and the summary.
    _surviving_ids = {
        str(it.get("id")) for row in account_rows for it in (row.get("queue") or [])
    }
    all_items = [i for i in all_items if i.id in _surviving_ids]

    # ── 14-day shape ledger (nightly only) ────────────────────────────────────
    _shape_ledger_path: str | None = None
    if write_shape_ledger:
        _observed_mix: dict[str, dict[str, int]] = {}
        for _acct_row in account_rows:
            _acct_id = str(_acct_row.get("id") or "")
            _m: dict[str, int] = {}
            for _it in (_acct_row.get("queue") or []):
                _sh = str(_it.get("shape") or "")
                if _sh:
                    _m[_sh] = _m.get(_sh, 0) + 1
            if _m:
                _observed_mix[_acct_id] = _m
        _written_ledger = record_shape_ledger(
            root, as_of=today, mix_by_account=_observed_mix)
        _shape_ledger_path = str(_written_ledger) if _written_ledger else None

    # ── Funnel W1a (D07): canonical tagged link on every post ─────────────────
    # Every clickable URL a post carries is the canonical UTM link, exactly once.
    # Runs after the copywriter pass so utm_campaign reflects the FINAL type
    # (signal→watchlist demotions included).
    _links_summary: dict = {"posts_linked": 0, "urls_rewritten": 0, "note": "links module unavailable"}
    try:
        from engine.marketing.links import attach_links as _attach_links
        _links_summary = _attach_links(account_rows, cfg=cfg)
    except Exception:  # noqa: BLE001
        pass

    # Distinctness check
    dist = distinctness(all_items)

    total_posts = len(all_items)
    signal_posts = sum(1 for i in all_items if i.type == "signal")
    n_charts = len(featured_charts)
    _alarm_on_a_planless_night(total_posts, _copy_dropped, n_charts, _sel_report,
                               _copy_drop_reasons)
    _alarm_on_cooldown_starvation(_sel_report)
    n_plans = len(plans)
    n_with_charts = len(set(fc["ticker"] for fc in featured_charts))

    artifact = {
        "schema_version": 1,
        "produced_by": "engine/marketing/content_studio.py",
        "produced_at": now_str,
        "tier": "display",
        "schema": "marketing.content/v1",
        "as_of": today,
        "source": {
            "prophet_plans": n_plans,
            "plans_with_charts": n_with_charts,
            "note": (
                f"{n_plans} Prophet plans ingested; {n_with_charts} have close-price history for charts."
                if n_plans > 0
                else "No Prophet plans available; minimal plan generated."
            ),
        },
        "content_types": CONTENT_TYPES,
        "accounts": account_rows,
        "featured_charts": featured_charts,
        "distinctness": dist,
        "summary": {
            "total_posts": total_posts,
            "signal_posts": signal_posts,
            "charts": n_charts,
            "accounts": len(account_rows),
            # THE PLANNER'S OWN FUNNEL, at the top of the artifact (W4c).
            # `dropped_cooldown` is the largest volume sink in the allocator and
            # it used to exist only inside a caller-supplied dict — the same
            # defect class as the mover bug that hid 12 nights of lost posts.
            # `slots_offered` is its denominator; without it the count cannot be
            # read as healthy or broken. `forward_days` records the ladder shape
            # this plan was built at, so a future postmortem can tell a 1-day
            # plan from a 7-day one without re-deriving it from slot labels.
            "forward_days": _sel_report.get("forward_days", forward_days(cfg)),
            "slots_offered": _sel_report.get("slots_offered", 0),
            "dropped_cooldown": _sel_report.get("dropped_cooldown", 0),
            "dropped_cooldown_by_account": dict(
                _sel_report.get("dropped_cooldown_by_account", {})),
            "ramp_banned_kinds": dict(_sel_report.get("ramp_banned_kinds", {})),
        },
        "content": {
            "movers": _movers_summary,
            "confluence": _confluence_census(
                account_rows, confluence_posts_added, conf_charts_added),
            # WHAT THE READER ACTUALLY SEES. Per-card fallbacks are announced at
            # the moment they happen; this is the share, which is the number that
            # tells an operator whether the rasteriser is healthy or the account
            # has quietly been posting degraded pictures all week.
            "chart_quality": _chart_quality_census(featured_charts),
            "copy": {
                "mode": _copy_mode,
                "n_validated": _copy_n_validated,
                "n_fallback": _copy_n_fallback,
                "violations_fixed": _copy_violations_fixed,
                "signals_killed_by_gate": _copy_signal_killed,
                # Of the signals the live gate failed, how many were DROPPED
                # outright rather than recycled into a watchlist post — and for
                # what. Before this split, every failure became filler and the
                # count above was the only trace; the feed then read uniform
                # because half of all watchlist posts were dead signals wearing
                # proximity copy (operator 2026-07-30).
                # The batch auditor's day. `cuts` carries the post text with the
                # reason so the console can show the operator exactly what was
                # pulled and why — a gate that only prints a count is the tinted
                # window this whole operation exists to fix.
                "auditor": _audit_report,
                "signals_dropped_not_demoted": sum(_signal_gate_drops.values()),
                "signals_dropped_by_reason": dict(_signal_gate_reasons),
                "demotable_gate_reasons": sorted(_demotable),
                "graded_receipts": _copy_n_receipts,
                # W1 (§0 gate 8): the proof surface. `written` counts model-
                # authored posts, `modes` is the per-mode census (the gate reads
                # "llm > 0, deterministic = 0 on planned kinds"), `dropped` is
                # by stage (provider|validate|critic), `shape_mix` is gate 4's
                # measurement, and `llm_required` records which law was in force.
                "written": _copy_written,
                "modes": _copy_modes,
                "dropped": _copy_dropped,
                # By REASON as well as by stage: "provider" alone cannot tell a
                # missing credential from a served-but-unreadable response, and
                # the plan artifact is what a postmortem reads a week later.
                "dropped_reasons": _copy_drop_reasons,
                "shape_mix": {
                    s: sum(m.get(s, 0) for m in _shape_mix_by_account.values())
                    for s in SHAPES
                    if any(m.get(s) for m in _shape_mix_by_account.values())
                },
                "shape_mix_by_account": _shape_mix_by_account,
                "shape_ledger_path": _shape_ledger_path,
                "llm_required": _llm_required,
                "note": (
                    f"{_copy_n_validated} posts written by copywriter; "
                    f"{_copy_n_fallback} fell back to templates; "
                    f"{_copy_signal_killed} signals killed by live gate."
                ),
            },
            # W1 selection funnel (contract §Selection: "Plan report gains
            # supply, after_cooldown, after_budget"). Supply-honest volume is
            # only auditable if the plan prints what it threw away and why.
            "selection": {
                # supply / after_cooldown are FACT counts (postable plans);
                # after_budget / posts_total are POST counts. Different units on
                # purpose — the funnel narrows facts first, then posts.
                "supply": _sel_report.get("supply", 0),
                "after_cooldown": _sel_report.get("after_cooldown", 0),
                "after_budget": _sel_report.get("after_budget", 0),
                "posts_total": _sel_report.get("posts_total", 0),
                "cooled_tickers": _sel_report.get("cooled_tickers", 0),
                "cooled_signal_tickers": _sel_report.get("cooled_signal_tickers", 0),
                "cooldown_overrides": _sel_report.get("cooldown_overrides", 0),
                "dropped_cooldown": _sel_report.get("dropped_cooldown", 0),
                # BY ACCOUNT (W4c): a network total of 40 hides "kelly lost
                # every rung she had", which is exactly the shape of the night
                # this lane was opened to explain.
                "dropped_cooldown_by_account": dict(
                    _sel_report.get("dropped_cooldown_by_account", {})),
                "slots_offered": _sel_report.get("slots_offered", 0),
                "forward_days": _sel_report.get("forward_days", 0),
                "per_day_headroom": _sel_report.get("per_day_headroom", 0),
                "ladder_shape": dict(_sel_report.get("ladder_shape", {})),
                "ramp_banned_kinds": dict(_sel_report.get("ramp_banned_kinds", {})),
                "ramp_ban_refused": _sel_report.get("ramp_ban_refused", 0),
                "dropped_ticker_budget": _sel_report.get("dropped_ticker_budget", 0),
                "dropped_signal_budget": _sel_report.get("dropped_signal_budget", 0),
                "degenerate_stats_dropped": _degenerate_dropped,
                # Filing/house-pick supply, and — when the block crashed — the
                # exception type under `error`. Surfaced here because a census
                # that only ever sees zeros cannot tell "no candidates tonight"
                # from "the lane died", and two live lanes can then stay dark for
                # weeks behind a green nightly.
                "filing_lanes": _sel_report.get("filing_lanes", {}),
                "note": (
                    f"{_sel_report.get('cooled_tickers', 0)} ticker(s) inside the "
                    f"cross-day cooldown, {_sel_report.get('cooldown_overrides', 0)} "
                    f"re-opened on a new fact; "
                    f"{_sel_report.get('dropped_ticker_budget', 0)} post(s) over the "
                    f"per-ticker account budget, "
                    f"{_sel_report.get('dropped_signal_budget', 0)} over the signal "
                    f"budget; {_degenerate_dropped} degenerate stat(s) dropped."
                ),
            },
            "links": _links_summary,
        },
    }
    return artifact
