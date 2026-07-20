"""engine.marketing.content_studio — Deterministic mixed-content plan generator.

Produces the per-account content queue and featured chart selection for
data/marketing/content_plan.json.

Public API:
    CONTENT_TYPES          — ordered list of {id, name, desc, color}
    plan_account(account, plans, *, n_days, per_day, seed) -> list[ContentItem]
    distinctness(items)    -> {max_similarity, flags, note}
    content_plan(cfg, plans, *, closes_loader) -> dict  (frozen §2.3 shape)
    content_mix(items)     -> dict  {type_id: count}

Spec constraints (§2.1 / §2.2 / §5):
  - Deterministic: NO RNG; stable per run; differs per account via account-hash.
  - Public copy carries NO technical-indicator vocabulary.
  - All 7 content types appear in every account's queue (≥1 each where slots allow).
  - signal is the largest type weight for all accounts.
  - Featured charts ≤12, only for plans with closes available.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
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
_DEFAULT_TILT: dict[str, float] = {
    "signal": 0.30,
    "chart": 0.13,
    "education": 0.10,
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
    # event — per voice
    ("event", "authoritative desk"): (
        "My read on today's move",
        "Here's how I'm reading today's move. The data says one thing, the price says another. "
        "Watching how it resolves.",
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

    # Ensure every type gets at least 1 if we have enough slots
    for t in type_ids:
        if floors[t] == 0 and sum(floors.values()) < total_slots:
            # Give 1 slot, take from the type with the most
            max_t = max((tt for tt in type_ids if floors[tt] > 1), default=None, key=lambda tt: floors[tt])
            if max_t is not None:
                floors[max_t] -= 1
                floors[t] = 1

    return floors


# ─────────────────────────────────────────────────────────────────────────────
# Slot labels
# ─────────────────────────────────────────────────────────────────────────────

def _slot_labels(n_days: int, per_day: int) -> list[str]:
    """Generate slot labels D1-AM, D1-PM, D1-EOD, D2-AM, ..."""
    times = ["AM", "PM", "EOD"]
    labels = []
    for day in range(1, n_days + 1):
        for i in range(per_day):
            t = times[i % len(times)]
            labels.append(f"D{day}-{t}")
    return labels


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
        return d


# ─────────────────────────────────────────────────────────────────────────────
# plan_account
# ─────────────────────────────────────────────────────────────────────────────

def plan_account(
    account: dict,
    plans: list[dict],
    *,
    n_days: int = 7,
    per_day: int = 3,
    seed: int = 0,
    tilt: dict[str, float] | None = None,
) -> list[ContentItem]:
    """Generate a deterministic content queue for one account.

    account: {id, voice, kind, ...}
    plans:   list of Prophet plan dicts
    tilt:    per-type weights (all types, sum ~1.0); falls back to _DEFAULT_TILT
    seed:    additional integer offset (account-hash provides per-account variation)
    """
    account_id = account.get("id", "unknown")
    voice = account.get("voice", "authoritative desk")
    ah = _account_hash(account_id) + seed

    effective_tilt = dict(_DEFAULT_TILT)
    if tilt:
        for k in _TYPE_IDS:
            if k in tilt and tilt[k] > 0:
                effective_tilt[k] = float(tilt[k])
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

    items: list[ContentItem] = []
    plan_cursor = ah % max(len(plan_pool), 1)
    counter = 0

    for slot_idx, (type_id, slot) in enumerate(zip(seq, slots)):
        # Pick a plan for signal/chart posts
        plan = None
        ticker = ""
        cashtag = ""
        if type_id in ("signal", "chart", "receipt") and plan_pool:
            plan_idx = (plan_cursor + slot_idx * (ah % 7 + 1)) % len(plan_pool)
            plan = plan_pool[plan_idx]
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


# ─────────────────────────────────────────────────────────────────────────────
# content_plan — the full §2.3 artifact
# ─────────────────────────────────────────────────────────────────────────────

def content_plan(
    cfg: dict,
    plans: list[dict],
    *,
    closes_loader: Callable[[str], tuple[list[str], list[float]] | None] | None = None,
    root: str | Path | None = None,
) -> dict:
    """Build the full content plan artifact (frozen §2.3 shape).

    cfg:          parsed config/marketing.yml
    plans:        list of Prophet plan dicts (may be empty)
    closes_loader: callable(ticker) -> (dates, closes) | None
    root:         repo root for OHLCV loading (data/stocks/<TICKER>.parquet). If
                  None, inferred from a closes_loader built by _make_closes_loader.

    Returns the frozen dict structure with envelope fields caller will stamp.
    """
    from engine.marketing.chart_render import (
        macd_cross,
        render_signal_chart,
        load_ohlcv,
        render_chart_v2,
    )

    dn_cfg = (cfg or {}).get("desk_network", {}) or {}
    raw_accounts = dn_cfg.get("accounts", []) or []

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now_str[:10]

    # Collect per-account items
    all_items: list[ContentItem] = []
    account_rows: list[dict] = []

    for acct_cfg in raw_accounts:
        acct_id = acct_cfg.get("id", "unknown")
        tilt_cfg = acct_cfg.get("tilt", {})
        voice = acct_cfg.get("voice", "authoritative desk")
        kind = acct_cfg.get("kind", "generic")

        items = plan_account(
            account=acct_cfg,
            plans=plans,
            n_days=7,
            per_day=3,
            seed=0,
            tilt=tilt_cfg if tilt_cfg else None,
        )
        all_items.extend(items)

        mix = content_mix(items)
        # Effective tilt — from config or default
        eff_tilt = dict(_DEFAULT_TILT)
        if tilt_cfg:
            for k in _TYPE_IDS:
                if k in tilt_cfg:
                    eff_tilt[k] = float(tilt_cfg[k])
        total_w = sum(eff_tilt.values()) or 1.0
        eff_tilt = {k: round(v / total_w, 3) for k, v in eff_tilt.items()}

        account_rows.append({
            "id": acct_id,
            "name": acct_cfg.get("beat", acct_id),
            "kind": kind,
            "voice": voice,
            "tilt": eff_tilt,
            "mix_observed": mix,
            "queue": [item.as_dict() for item in items],
        })

    # Select featured charts: ≤2 per account, max 6 Prophet + up to 2 confluence = 8 total.
    # Only with closes. Eligibility gate always applies.
    _CHART_CAP = 6
    featured_charts: list[dict] = []
    chart_id_counter = 1

    if closes_loader is not None and plans:
        # Deduplicate: one chart per ticker
        seen_tickers: set[str] = set()
        # Root for OHLCV loading: explicit param preferred; "." as a safe default.
        _ohlcv_root: str = str(root) if root is not None else "."

        for acct_row in account_rows:
            if len(featured_charts) >= _CHART_CAP:
                break
            acct_id = acct_row["id"]
            acct_count = 0
            for item_dict in acct_row["queue"]:
                if len(featured_charts) >= _CHART_CAP or acct_count >= 2:
                    break
                if item_dict["type"] != "signal":
                    continue
                ticker = item_dict.get("ticker", "")
                if not ticker or ticker in seen_tickers:
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

                # LIVE gate for charts too: a featured chart is the loudest post
                # we make — an underwater/runaway/stale signal must never get one
                # (the BA case: down 5.5% from entry yet still charted with a BUY).
                try:
                    from engine.marketing.copywriter import verify_signal_live as _vsl
                    _ok_live, _ = _vsl(plan_match, closes_result, today=today)
                except Exception:  # noqa: BLE001
                    _ok_live = True  # fail-open only if the gate itself is broken
                if not _ok_live:
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

                marker_date = dates[marker_index] if marker_index < len(dates) else dates[-1]
                marker_price = closes[marker_index]

                cashtag = f"${ticker}"
                chart_id = f"chart-{chart_id_counter:03d}"

                # ── v2 chart: attempt OHLCV load for candlestick render ──────
                svg: str | None = None
                if _ohlcv_root:
                    ohlcv = load_ohlcv(ticker, _ohlcv_root, n=90)
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
                        if _m2_cfg_always and not _m2_ovl:
                            try:
                                from engine.marketing.chart_render import build_m2_overlays as _bm2
                                _m2_ovl = _bm2(
                                    ticker, ohlcv_dates, ohlcv_o, ohlcv_h,
                                    ohlcv_l, ohlcv_c, ohlcv_v, _ohlcv_root,
                                )
                            except Exception:
                                _m2_ovl = {}
                        svg = render_chart_v2(
                            ticker=ticker,
                            dates=ohlcv_dates,
                            o=ohlcv_o,
                            h=ohlcv_h,
                            l=ohlcv_l,
                            c=ohlcv_c,
                            volume=ohlcv_v,
                            timeframe="DAILY",
                            marker_index=ohlcv_marker,
                            highlight_index=ohlcv_marker,
                            pct_from_index=(ohlcv_marker if (len(ohlcv_c) - 1 - (ohlcv_marker or 0)) >= 5 else None),
                            show_indicators=True,
                            indicators=("volume", "macd"),
                            company_name=ticker,
                            logo_root=_ohlcv_root,
                            avwap_overlay=_m2_ovl.get("avwap_overlay"),
                            poc_overlay=_m2_ovl.get("poc_overlay"),
                        )

                # Fallback: v1 render (marker-only) so nothing breaks
                if svg is None:
                    subtitle = f"{cashtag} · signal"
                    svg = render_signal_chart(
                        ticker=ticker,
                        dates=dates,
                        closes=closes,
                        marker_index=marker_index,
                        subtitle=subtitle,
                    )

                # Get headline/body from queue item
                headline = item_dict.get("headline", f"{cashtag} opportunity flagged")
                body = item_dict.get("body", "")

                # Assign chart_id back to all items for this ticker+account
                for item_dict2 in acct_row["queue"]:
                    if item_dict2["ticker"] == ticker and item_dict2["type"] == "signal":
                        item_dict2["chart_id"] = chart_id

                featured_charts.append({
                    "id": chart_id,
                    "ticker": ticker,
                    "account": acct_id,
                    "cashtag": cashtag,
                    "marker_source": marker_source,
                    "marker_date": marker_date,
                    "marker_price": round(marker_price, 4),
                    "svg": svg,
                    "headline": headline,
                    "body": body,
                })

                seen_tickers.add(ticker)
                chart_id_counter += 1
                acct_count += 1

    # ── Confluence-sourced signal posts (§3 confluence→chart-post loop) ───────
    # Read fired combos from tech_confluence.json. Cap confluence charts so total
    # featured_charts stays <= 8 (Prophet uses up to 6). Fail-soft: if the file is
    # absent or has no fresh fired combos, Prophet posts still flow unchanged.
    _TOTAL_CHART_CAP = 8
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

            # Use first account's voice for confluence posts (or authoritative desk)
            conf_voice = (
                account_rows[0].get("voice", "authoritative desk")
                if account_rows else "authoritative desk"
            )
            conf_account_id = account_rows[0].get("id", "confluence") if account_rows else "confluence"

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

                # Attempt v2 chart for this confluence ticker
                # Only if we have headroom under the total cap
                if len(featured_charts) < _TOTAL_CHART_CAP and _ohlcv_root_conf:
                    from engine.marketing.chart_render import load_ohlcv, render_chart_v2
                    ohlcv = load_ohlcv(conf_ticker, _ohlcv_root_conf, n=90)
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
                            company_name=conf_ticker,
                            logo_root=_ohlcv_root_conf,
                            avwap_overlay=_m2_ovl_conf.get("avwap_overlay"),
                            poc_overlay=_m2_ovl_conf.get("poc_overlay"),
                        )

                        conf_item.chart_id = chart_id
                        featured_charts.append({
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
                        })
                        chart_id_counter += 1
                        conf_charts_added += 1
                        prophet_chart_tickers.add(conf_ticker)

                # Add to the first account's queue (additive)
                if account_rows:
                    account_rows[0]["queue"].append(conf_item.as_dict())

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
                _mv_body = (
                    f"{_mv_top_fact} Watching how it holds, not chasing the candle. "
                    f"Levels are on the chart."
                )
                _mover_item_dict = {
                    "id": f"post-mover-{_mover_item_counter:03d}",
                    "type": "mover",
                    "account": account_rows[0]["id"] if account_rows else "flagship",
                    "cashtag": f"${_mv_ticker}",
                    "ticker": _mv_ticker,
                    "headline": _mv_headline,
                    "body": _mv_body,
                    "provenance": "movers_desk",
                    "chart_id": None,
                    "slot": f"MOVER-{_mover_item_counter:02d}",
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
                    "account": account_rows[0]["id"] if account_rows else "flagship",
                    "cashtag": _cashtags[0] if _cashtags else "",
                    "cashtags": _cashtags,
                    "ticker": "",
                    "headline": _tl_headline,
                    "body": _tl_body,
                    "provenance": "movers_desk",
                    "chart_id": None,
                    "slot": f"THEME-{_mover_item_counter:02d}",
                    "status": "drafted",
                    "_theme_data": _tl,
                    "_theme_facts": _tl_facts,
                }
                _theme_items_for_queue.append(_tl_item_dict)
                _mover_item_counter += 1

            # ── Watchlist card rendering for theme_list items ─────────────────
            # Each theme_list item gets an SVG watchlist card: rows from theme members
            # {ticker, price, pct_change}, subtitle = the item's stance line (question).
            # Card goes into featured_charts the same way signal charts do; chart_id
            # is attached to the item dict.
            if len(featured_charts) < _TOTAL_CHART_CAP:
                try:
                    from engine.marketing.chart_render import render_watchlist_card as _rwc
                    for _tl_item in _theme_items_for_queue:
                        if len(featured_charts) >= _TOTAL_CHART_CAP:
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

            # Distribute reach items round-robin across the desks so the WHOLE
            # network posts reach content — and each desk gets a DISTINCT theme /
            # mover (different cashtags => inherently distinctness-safe, no
            # substantially-similar cross-account risk). Cold-start reach comes
            # from breadth of coverage across the network, not one desk.
            if account_rows:
                _n_acct = len(account_rows)
                # Interleave movers and themes so early desks get a mix.
                from itertools import zip_longest as _zip_longest  # noqa: PLC0415
                _reach_items = []
                for _m, _t in _zip_longest(_mover_items_for_queue, _theme_items_for_queue):
                    if _t is not None:
                        _reach_items.append(_t)
                    if _m is not None:
                        _reach_items.append(_m)
                for _idx, _item in enumerate(_reach_items):
                    _acct = account_rows[_idx % _n_acct]
                    _item["account"] = _acct.get("id", "flagship")
                    _acct["queue"].append(_item)

            _movers_summary = {
                "movers": [
                    {
                        "ticker": it["ticker"],
                        "pct": it["_mover_data"]["pct"],
                        "sector": it["_mover_data"].get("sector", ""),
                    }
                    for it in _mover_items_for_queue
                ],
                "theme_lists": [
                    {
                        "theme": it["_theme_data"]["theme"],
                        "direction": it["_theme_data"]["direction"],
                        "agg_pct": it["_theme_data"]["agg_pct"],
                        "n_members": len(it["_theme_data"]["members"]),
                    }
                    for it in _theme_items_for_queue
                ],
                "note": (
                    f"{len(_mover_items_for_queue)} mover posts, "
                    f"{len(_theme_items_for_queue)} theme_list posts generated "
                    f"from heatmap data."
                ),
            }

            # mover items: attempt v2 chart (same as Prophet signal flow)
            if closes_loader is not None:
                from engine.marketing.chart_render import load_ohlcv, render_chart_v2, render_signal_chart
                for _mv_item in _mover_items_for_queue:
                    _mv_ticker = _mv_item["ticker"]
                    if len(featured_charts) >= _TOTAL_CHART_CAP:
                        break
                    _mv_closes = closes_loader(_mv_ticker)
                    if _mv_closes is None:
                        continue
                    _mv_dates, _mv_cls = _mv_closes
                    if len(_mv_cls) < 10:
                        continue
                    chart_id = f"chart-{chart_id_counter:03d}"
                    svg: str | None = None
                    ohlcv = load_ohlcv(_mv_ticker, _ohlcv_root_mv, n=90)
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
                            indicators=("volume",),
                            company_name=_mv_ticker,
                            logo_root=_ohlcv_root_mv,
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
                    featured_charts.append({
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
                    })
                    chart_id_counter += 1

    except Exception:  # noqa: BLE001
        pass  # fail-soft — movers unavailable; Prophet posts unchanged

    # ── Strip neural_web mover/theme_list stubs ──────────────────────────────
    # The tilt-based queue builder creates stub mover/theme_list items for every
    # account.  These have no real data and would produce empty-token copy.
    # The movers injection block above has already added real movers_desk items
    # to account_rows[0].  Remove all neural_web mover/theme_list items so only
    # movers_desk items represent those types in the final plan.
    for _acct_row in account_rows:
        _acct_row["queue"] = [
            _it for _it in _acct_row["queue"]
            if not (
                _it.get("type") in ("mover", "theme_list")
                and _it.get("provenance") != "movers_desk"
            )
        ]

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

    try:
        from engine.marketing.copywriter import (
            verify_signal_live,
            build_context,
            write_posts_deterministic,
        )
        from engine.marketing.receipt_source import graded_receipts

        _graded_receipts_list = graded_receipts(plans or [], today=today)
        _copy_n_receipts = len(_graded_receipts_list)
        _receipts_by_ticker: dict[str, dict] = {
            r["ticker"]: r for r in _graded_receipts_list
        }

        # Build a ticker→plan lookup for fast signal matching
        _plan_by_ticker: dict[str, dict] = {}
        for _p in (plans or []):
            _pt = _p.get("asset", "")
            if _pt and _pt not in _plan_by_ticker:
                _plan_by_ticker[_pt] = _p

        # Build account id → acct_cfg lookup for persona resolution
        _acct_cfg_by_id: dict[str, dict] = {
            a.get("id", ""): a for a in raw_accounts
        }

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
                        # Demote to watchlist — dead/runaway/stale signal
                        item_dict["type"] = "watchlist"
                        item_dict["_live_gate_fail"] = reason
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
            for item_dict in queue:
                ticker = item_dict.get("ticker", "")
                type_id = item_dict.get("type", "")
                facts_data: dict = {}
                if ticker and closes_loader is not None:
                    try:
                        from engine.marketing.chart_facts import compute_facts
                        from engine.marketing.chart_render import load_ohlcv
                        _ohlcv_root_cw: str = str(root) if root is not None else "."
                        _ohlcv = load_ohlcv(ticker, _ohlcv_root_cw, n=90)
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
                contexts.append(ctx)

            # Phase 3: batch call — LLM lane first (persona ceiling; guarded by
            # config copywriter.llm.enabled AND the MARKETING_LLM_ENABLED env var,
            # so tests/local runs never trigger it), deterministic floor otherwise.
            # write_posts_llm validates every output and falls back per-post.
            posts = None
            try:
                from engine.marketing.copywriter import write_posts_llm  # noqa: PLC0415
                _cw_cfg = (cfg or {}).get("copywriter", {}) or {}
                posts = write_posts_llm(contexts, _cw_cfg)
            except Exception:  # noqa: BLE001
                posts = None
            if posts is not None:
                _copy_mode = "llm"
            else:
                posts = write_posts_deterministic(contexts)
            for item_dict, post in zip(queue, posts):
                # Confluence signal posts keep the win_rate_hook copy — it is the
                # crown-jewel framing ("worked 86% of the time historically") and
                # the generic signal templates would inject empty Prophet fields
                # ("Entry . T1 .") since combos have no entry/target.
                if item_dict.get("source") == "confluence" and item_dict.get("type") == "signal":
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
                    _copy_n_validated += 1
                    continue
                new_headline = post.get("headline", "")
                new_body = post.get("body", "")
                violations = post.get("violations", [])
                if new_headline and new_body:
                    item_dict["headline"] = new_headline
                    item_dict["body"] = new_body
                    item_dict["_copy_mode"] = post.get("mode", "deterministic")
                    item_dict["_copy_violations"] = violations
                    if violations:
                        _copy_violations_fixed += len(violations)
                    _copy_n_validated += 1
                else:
                    _copy_n_fallback += 1

            # Recount mix after type changes (signal→watchlist / receipt→watchlist)
            from collections import Counter as _Counter
            type_counts = _Counter(d.get("type", "") for d in queue)
            acct_row["mix_observed"] = dict(type_counts)

    except Exception:  # noqa: BLE001
        # Fail-soft: copywriter unavailable — old template copy survives
        _copy_mode = "fallback"

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
        },
        "content": {
            "movers": _movers_summary,
            "confluence": {
                "fired_combos": len(confluence_posts_added),
                "charts": conf_charts_added,
                "posts": confluence_posts_added,
                "note": (
                    f"{len(confluence_posts_added)} confluence signal posts added "
                    f"({conf_charts_added} charts)."
                    if confluence_posts_added
                    else "No fresh fired confluence combos today; Prophet posts only."
                ),
            },
            "copy": {
                "mode": _copy_mode,
                "n_validated": _copy_n_validated,
                "n_fallback": _copy_n_fallback,
                "violations_fixed": _copy_violations_fixed,
                "signals_killed_by_gate": _copy_signal_killed,
                "graded_receipts": _copy_n_receipts,
                "note": (
                    f"{_copy_n_validated} posts written by copywriter; "
                    f"{_copy_n_fallback} fell back to templates; "
                    f"{_copy_signal_killed} signals killed by live gate."
                ),
            },
            "links": _links_summary,
        },
    }
    return artifact
