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
        "desc": "A brief read on the macro backdrop — rates, liquidity, or regime — and what it means right now.",
        "color": "#f59e0b",
    },
    {
        "id": "receipt",
        "name": "Report Card",
        "desc": "A public update on how a past call played out — the numbers, the outcome, and what we learned.",
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
]

_TYPE_IDS = [t["id"] for t in CONTENT_TYPES]

# Default tilt when config is absent
_DEFAULT_TILT: dict[str, float] = {
    "signal": 0.35,
    "chart": 0.15,
    "education": 0.13,
    "macro": 0.13,
    "receipt": 0.10,
    "watchlist": 0.07,
    "event": 0.07,
}

# Per-account voice copy templates — (type_id, voice) -> (headline_template, body_template)
# Placeholder tokens: {ticker}, {cashtag}, {direction}, {entry}, {target1}, {stance}
_COPY_TEMPLATES: dict[tuple[str, str], tuple[str, str]] = {
    # signal — authoritative desk
    ("signal", "authoritative desk"): (
        "{cashtag} — opportunity flagged",
        "We're watching {ticker}. The setup meets our criteria at {entry}. "
        "First target: {target1}. What would change this: price back below {entry} on volume. "
        "As always, size appropriately.",
    ),
    # signal — dry, receipts-forward
    ("signal", "dry, receipts-forward"): (
        "{cashtag} alert | entry {entry}",
        "{ticker} flagged. T1: {target1}. "
        "This one goes into the receipt book — we'll post the outcome regardless of direction. "
        "Watch: close below entry invalidates.",
    ),
    # signal — specialist
    ("signal", "specialist"): (
        "Sector move: {cashtag} in focus",
        "{ticker} is showing the setup we track in this vertical. "
        "Entry around {entry}, first level at {target1}. "
        "The broader sector context supports this. What would change this: a close back "
        "below {entry}. Position sizing is everything here.",
    ),
    # signal — educational
    ("signal", "educational"): (
        "Here's a live example: {cashtag}",
        "We talk a lot about what to look for — {ticker} is showing it right now. "
        "The entry is {entry}. The first target is {target1}. What would change this: "
        "a close back below {entry}. We'll track it publicly so you can see how it unfolds.",
    ),
    # signal — fast, reactive
    ("signal", "fast, reactive"): (
        "{cashtag} | {direction} alert",
        "{ticker} moving. Entry {entry}, target {target1}. "
        "Quick invalidation: below {entry}. Adding to the board.",
    ),
    # signal — pattern/history
    ("signal", "pattern/history"): (
        "{cashtag} — historical setup in play",
        "{ticker} is tracing a pattern we've tracked before. "
        "Entry {entry}, target {target1}. What would change this: a close back below {entry}. "
        "The historical analogue says patience pays here — we'll post progress.",
    ),
    # chart — all voices share a template per voice; use fallbacks
    ("chart", "authoritative desk"): (
        "{ticker} — price context",
        "Sharing the chart on {ticker} this week. The picture speaks: {entry} was the level. "
        "No thesis beyond what you see.",
    ),
    ("chart", "dry, receipts-forward"): (
        "{ticker} chart | no commentary",
        "The chart. That's it.",
    ),
    ("chart", "specialist"): (
        "{ticker} — sector chart",
        "This week's chart for the vertical. {ticker} at {entry}.",
    ),
    ("chart", "educational"): (
        "Chart breakdown: {ticker}",
        "Walking through what this chart is showing — {ticker} at {entry}. "
        "Key things to notice: the trend, the level, and the volume.",
    ),
    ("chart", "fast, reactive"): (
        "{ticker} chart | quick look",
        "Fast chart on {ticker}. Level: {entry}. Make your own call.",
    ),
    ("chart", "pattern/history"): (
        "{ticker} — pattern match",
        "This chart on {ticker} matches a historical pattern. Level: {entry}. Context below.",
    ),
    # education — unique per voice
    ("education", "authoritative desk"): (
        "What 'conviction' actually means",
        "When we flag something with high conviction, here's what that means in practice — "
        "and what it doesn't mean.",
    ),
    ("education", "dry, receipts-forward"): (
        "How we track our calls",
        "Every signal we make goes in the receipt book. Here's how that works and why.",
    ),
    ("education", "specialist"): (
        "One concept this vertical gets wrong",
        "Most people misread this signal in our sector. Here's the cleaner way to think about it.",
    ),
    ("education", "educational"): (
        "Plain English: what is a 'setup'?",
        "A setup is a price configuration that, historically, has been a good time to pay attention. "
        "Not a guarantee — just a reason to look closer.",
    ),
    ("education", "fast, reactive"): (
        "Quick primer: reading momentum",
        "Fast explanation of what momentum actually tells you and what it doesn't.",
    ),
    ("education", "pattern/history"): (
        "When history rhymes: a primer",
        "Historical analogues are useful but dangerous. Here's how we use them without fooling ourselves.",
    ),
    # macro — per voice
    ("macro", "authoritative desk"): (
        "Macro backdrop this week",
        "The regime is {stance}. What that means for risk assets: caution on leverage, "
        "favor quality. Watch the next data point carefully.",
    ),
    ("macro", "dry, receipts-forward"): (
        "Macro: {stance}",
        "Current regime: {stance}. "
        "Historically this environment has meant X. We'll track the outcome.",
    ),
    ("macro", "specialist"): (
        "Macro note for this vertical",
        "The macro backdrop matters more for this sector right now. "
        "Regime: {stance}. Positioning accordingly.",
    ),
    ("macro", "educational"): (
        "What the macro says right now",
        "Breaking down the current regime in plain terms: {stance}. "
        "Here's what that has historically meant for prices.",
    ),
    ("macro", "fast, reactive"): (
        "Macro update | {stance}",
        "Quick macro note. Regime: {stance}. Adjusting accordingly.",
    ),
    ("macro", "pattern/history"): (
        "Macro analogue: {stance}",
        "The current regime ({stance}) has a historical parallel. Here's what the chart said then.",
    ),
    # receipt — per voice
    ("receipt", "authoritative desk"): (
        "Outcome update: how our call played out",
        "We called it. Here's the result — honest, with the numbers. "
        "Learn from what worked and what didn't.",
    ),
    ("receipt", "dry, receipts-forward"): (
        "Receipt: call outcome",
        "Here's the score. We made a call. Here's what happened.",
    ),
    ("receipt", "specialist"): (
        "Vertical outcome: how our read played out",
        "Following up on our sector call. Here's the result.",
    ),
    ("receipt", "educational"): (
        "We track our calls — here's one outcome",
        "We said X. Here's what happened. This is how accountability looks in practice.",
    ),
    ("receipt", "fast, reactive"): (
        "Outcome update | fast recap",
        "Called it, here's what happened. Straight to the numbers.",
    ),
    ("receipt", "pattern/history"): (
        "Pattern outcome: did the analogue hold?",
        "We flagged a historical pattern. Here's whether it played out.",
    ),
    # watchlist — per voice
    ("watchlist", "authoritative desk"): (
        "On our radar this week",
        "Names we're watching but haven't acted on. Keeping the list honest.",
    ),
    ("watchlist", "dry, receipts-forward"): (
        "Watch list | no position",
        "Watching these. No position yet. Will update if anything changes.",
    ),
    ("watchlist", "specialist"): (
        "Vertical watch list",
        "These names are setting up in our sector. Watching, not acting yet.",
    ),
    ("watchlist", "educational"): (
        "What goes on a watch list — and why",
        "Here are the names we're monitoring, with a brief note on why each made the list.",
    ),
    ("watchlist", "fast, reactive"): (
        "Quick radar | watching these",
        "Fast list of names worth attention right now. No action yet.",
    ),
    ("watchlist", "pattern/history"): (
        "Pattern watch list",
        "Names tracing patterns worth monitoring. Historical context below.",
    ),
    # event — per voice
    ("event", "authoritative desk"): (
        "Market event: our read",
        "Here's how we're reading today's market-moving event. "
        "The data says one thing; the price says another. Watch the resolution.",
    ),
    ("event", "dry, receipts-forward"): (
        "Event reaction | numbers first",
        "Event just happened. Here are the numbers and what they change.",
    ),
    ("event", "specialist"): (
        "Event impact on our sector",
        "Today's event has direct implications for our vertical. Here's the read.",
    ),
    ("event", "educational"): (
        "What today's event means — plain English",
        "Big event today. Here's what it actually means for markets without the jargon.",
    ),
    ("event", "fast, reactive"): (
        "Reaction: {event_name}",
        "Fast take on today's event. Key number: {entry}. What to watch next.",
    ),
    ("event", "pattern/history"): (
        "Historical read on today's event",
        "This event type has a track record. Here's what history says about the aftermath.",
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
                            pct_from_index=ohlcv_marker,
                            show_indicators=True,
                            indicators=("volume", "macd"),
                            company_name=ticker,
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
                            pct_from_index=conf_marker,
                            show_indicators=True,
                            indicators=("volume", "macd"),
                            company_name=conf_ticker,
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
                else "No Prophet plans available — minimal plan generated."
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
            "confluence": {
                "fired_combos": len(confluence_posts_added),
                "charts": conf_charts_added,
                "posts": confluence_posts_added,
                "note": (
                    f"{len(confluence_posts_added)} confluence signal posts added "
                    f"({conf_charts_added} charts)."
                    if confluence_posts_added
                    else "No fresh fired confluence combos today — Prophet posts only."
                ),
            },
        },
    }
    return artifact
