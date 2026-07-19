"""engine.marketing.copywriter — Voice layer that kills bot-copy.

Responsibilities:
  1. verify_signal_live(plan, closes) → (ok, reason)
       Gate: requires last_close, checks underwater/runaway/age.
  2. build_context(item, *, persona, facts, extra) → dict
       Packages everything a writer needs (ticker, plan numbers, chart facts, receipts).
  3. validate_copy(headline, body, ctx) → list[str] violations
       Enforces all copy_laws from config/marketing.yml.
  4. write_posts_deterministic(contexts) → [{headline, body}]
       Fallback: 4-6 genuine variants per (type, persona), fact-woven,
       chosen deterministically. Never produces "The chart. That's it."
  5. write_posts_llm(contexts, cfg) → [{headline, body}] | None
       Optional LLM call; guarded on enabled flag; batched JSON.
       Returns None on any failure. NEVER called in tests.

Public API:
    verify_signal_live, build_context, validate_copy,
    write_posts_deterministic, write_posts_llm
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Constants from copy_laws
# ─────────────────────────────────────────────────────────────────────────────

_MAX_CHARS = 275
_BANNED_VOCAB: frozenset[str] = frozenset({
    "macd", "rsi", "stochastic", "ichimoku", "bollinger",
    "validated", "guaranteed", "can't lose", "buy now",
})
# Regex for number-like tokens in copy (%, x, price-like floats)
_NUMBER_RE = re.compile(
    r"""
    [+-]?\d+\.?\d*%            # percentage: +12.3% or -5.5%
    |
    \d+\.?\d*x                 # multiplier: 3x or 2.5x
    |
    \b\d{2,4}\.\d{2}\b        # price: 226.50 or 19.54
    |
    \b\d{3,6}\b               # bare integer: e.g. 1000 (share count not typically needed)
    """,
    re.VERBOSE,
)
# Jaccard threshold for duplicate detection
_JACCARD_THRESH = 0.8

# Live-signal gate constants
_UNDERWATER_MAX = 0.02    # 2% below entry → dead
_RUNAWAY_MAX = 0.12       # 12% above entry → no longer an actionable entry
_MAX_SIGNAL_AGE_DAYS = 10 # tighter than studio's 21-day gate


# ─────────────────────────────────────────────────────────────────────────────
# verify_signal_live
# ─────────────────────────────────────────────────────────────────────────────

def _parse_date(s: object) -> date | None:
    try:
        parts = str(s)[:10].split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        return None


def _signal_age_days(signal_date: object, *, today_date: date | None = None) -> int | None:
    sd = _parse_date(signal_date)
    if sd is None:
        return None
    nd = today_date or datetime.now(timezone.utc).date()
    return (nd - sd).days


def verify_signal_live(
    plan: dict,
    closes: tuple[list[str], list[float]] | None,
    *,
    today: str | None = None,
) -> tuple[bool, str]:
    """Gate: verify a plan is still live and at an actionable entry level.

    Returns (ok: bool, reason: str).

    Rules:
    - closes must not be None (unverifiable → skip signal post)
    - last_close >= entry * (1 - _UNDERWATER_MAX)  [not more than 2% underwater]
    - last_close <= entry * (1 + _RUNAWAY_MAX)      [not run away more than 12%]
    - signal_date within _MAX_SIGNAL_AGE_DAYS calendar days
    """
    if closes is None:
        return False, "no close data — cannot verify"
    dates, close_prices = closes
    if not close_prices:
        return False, "empty close series"
    last_close = close_prices[-1]

    entry = plan.get("entry")
    if not entry:
        return False, "no entry level in plan"
    try:
        entry = float(entry)
    except (TypeError, ValueError):
        return False, "unparseable entry"

    if last_close < entry * (1 - _UNDERWATER_MAX):
        pct = (last_close - entry) / entry * 100
        return False, f"underwater {pct:.1f}% (last={last_close:.2f}, entry={entry:.2f})"

    if last_close > entry * (1 + _RUNAWAY_MAX):
        pct = (last_close - entry) / entry * 100
        return False, f"ran away +{pct:.1f}% — no longer actionable (last={last_close:.2f}, entry={entry:.2f})"

    today_date = _parse_date(today) if today else datetime.now(timezone.utc).date()
    age = _signal_age_days(plan.get("_signal_date"), today_date=today_date)
    if age is None:
        return False, "no signal_date — cannot verify age"
    if age > _MAX_SIGNAL_AGE_DAYS:
        return False, f"signal is {age}d old (max {_MAX_SIGNAL_AGE_DAYS}d)"

    return True, "ok"


# ─────────────────────────────────────────────────────────────────────────────
# build_context
# ─────────────────────────────────────────────────────────────────────────────

def build_context(
    item: dict,
    *,
    persona: dict | None = None,
    facts: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """Build the full writer context dict.

    item: ContentItem-like dict (ticker, type, account, plan fields, receipt, ...)
    persona: persona card from marketing.yml copywriter.personas.<id>
    facts: output of chart_facts.compute_facts()
    extra: any additional data (combo win_rate for confluence, etc.)

    Returns a dict with every field the writer is allowed to use.
    """
    ticker = item.get("ticker", "")
    cashtag = f"${ticker}" if ticker else ""
    plan = item.get("_plan") or {}
    receipt = item.get("_receipt") or {}

    # Top 3 chart facts — POLARITY-AWARE for directional posts. A bullish signal
    # post must never lead with a bearish fact ("lost its 50-day — that's why
    # it's on the board" is a contradiction). Bearish facts stay available for
    # bearish posts and neutral types; they are only excluded where they clash.
    top_facts: list[dict] = []
    whitelist: list[str] = []
    if facts:
        all_facts = facts.get("facts", [])
        item_type = item.get("type", "")
        direction = str(plan.get("direction", "") or item.get("direction", "BULL")).upper()
        if item_type == "signal":
            _BEAR_MARKERS = ("lost", "below", "off its high", "down ", "red ",
                             "biggest down", "52-week low", "worst")
            _BULL_MARKERS = ("reclaimed", "above", "high", "up ", "green ",
                             "record", "surge", "streak")
            markers = _BEAR_MARKERS if direction != "BEAR" else _BULL_MARKERS
            filtered = [f for f in all_facts
                        if not any(m in f.get("text", "").lower() for m in markers)]
            top_facts = (filtered or all_facts)[:3]
        else:
            top_facts = all_facts[:3]
        whitelist = list(facts.get("numbers_whitelist", []))

    # Plan numbers — check plan dict first, fall back to direct item fields
    entry = plan.get("entry") if plan.get("entry") is not None else item.get("entry")
    targets = plan.get("targets") or item.get("targets") or []
    t1 = targets[0] if targets else None
    t2 = targets[1] if len(targets) > 1 else None
    invalidation = (
        plan.get("invalidation") if plan.get("invalidation") is not None
        else item.get("invalidation")
    )

    # Format plan numbers and add to whitelist
    def _fmtp(v: object) -> str | None:
        try:
            return f"{float(v):.2f}"
        except (TypeError, ValueError):
            return None

    entry_str = _fmtp(entry)
    t1_str = _fmtp(t1)
    t2_str = _fmtp(t2)
    inv_str = _fmtp(invalidation)

    for s in [entry_str, t1_str, t2_str, inv_str]:
        if s and s not in whitelist:
            whitelist.append(s)

    # Receipt numbers
    gain_pct_str = receipt.get("gain_pct_str")
    loss_pct_str = receipt.get("loss_pct_str")
    target_label = receipt.get("target_label", "T1")
    stop_str = _fmtp(receipt.get("stop"))
    target_str = _fmtp(receipt.get("target"))
    for s in [gain_pct_str, loss_pct_str, stop_str, target_str]:
        if s and s not in whitelist:
            whitelist.append(s)

    # Confluence / win-rate extra
    win_rate = None
    win_rate_str = None
    if extra:
        wr = extra.get("win_rate")
        if wr is not None:
            win_rate = float(wr)
            win_rate_str = f"{win_rate:.0f}%"
            if win_rate_str not in whitelist:
                whitelist.append(win_rate_str)

    # Persona card
    persona_name = (persona or {}).get("name", "")
    voice_notes = (persona or {}).get("voice_notes", "")
    example_lines = (persona or {}).get("example_lines", [])
    emoji_budget = 1  # default

    # Parse emoji budget from voice_notes text
    if persona:
        notes_lower = voice_notes.lower()
        if "emoji budget: 0" in notes_lower:
            emoji_budget = 0
        elif "0-1" in notes_lower or "0 or 1" in notes_lower:
            emoji_budget = 1
        else:
            emoji_budget = 1

    return {
        # Identity
        "ticker": ticker,
        "cashtag": cashtag,
        "type": item.get("type", ""),
        "account": item.get("account", ""),
        # Persona
        "persona_name": persona_name,
        "voice_notes": voice_notes,
        "example_lines": example_lines,
        "emoji_budget": emoji_budget,
        # Chart facts
        "top_facts": top_facts,       # list of {id, text, salience, numbers}
        "top_fact_text": top_facts[0]["text"] if top_facts else "",
        # Plan numbers
        "entry_str": entry_str or "",
        "t1_str": t1_str or "",
        "t2_str": t2_str or "",
        "inv_str": inv_str or "",
        # Receipt
        "receipt_kind": receipt.get("kind", ""),
        "gain_pct_str": gain_pct_str or "",
        "loss_pct_str": loss_pct_str or "",
        "target_label": target_label,
        "stop_str": stop_str or "",
        # Confluence
        "win_rate": win_rate,
        "win_rate_str": win_rate_str or "",
        # Numbers whitelist (copy validator uses this)
        "numbers_whitelist": whitelist,
        # Slot / plan meta
        "direction": plan.get("direction") or item.get("direction", ""),
        "signal_date": str(plan.get("_signal_date") or item.get("_signal_date") or "")[:10],
    }


# ─────────────────────────────────────────────────────────────────────────────
# validate_copy
# ─────────────────────────────────────────────────────────────────────────────

def _token_jaccard(a: str, b: str) -> float:
    ta = set(re.findall(r"\w+", a.lower()))
    tb = set(re.findall(r"\w+", b.lower()))
    if not ta and not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _count_emoji(text: str) -> int:
    """Count emoji characters (very broad: any char outside BMP range or known emoji range)."""
    count = 0
    for ch in text:
        cp = ord(ch)
        # Unicode emoji ranges (broad approximation)
        if (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or cp == 0x1F9A0:
            count += 1
    return count


def _extract_number_tokens(text: str) -> list[str]:
    """Extract all number-like tokens from text."""
    return _NUMBER_RE.findall(text)


def validate_copy(
    headline: str,
    body: str,
    ctx: dict,
    *,
    batch_headlines: list[str] | None = None,
) -> list[str]:
    """Validate a (headline, body) pair against all copy_laws.

    Returns a list of violation strings (empty list = clean).

    ctx must come from build_context().
    batch_headlines: other headlines in this batch (for duplicate detection).
    """
    violations: list[str] = []
    full_text = f"{headline} {body}"

    # 1. Cashtag on every ticker post
    ticker = ctx.get("ticker", "")
    if ticker and ctx.get("type") in ("signal", "chart", "receipt", "watchlist"):
        cashtag = f"${ticker}"
        if cashtag not in full_text:
            violations.append(f"missing cashtag {cashtag}")

    # 2. Length > 275 characters
    total_len = len(headline) + 1 + len(body)
    if total_len > _MAX_CHARS:
        violations.append(f"too long: {total_len} chars (max {_MAX_CHARS})")

    # 3. Emoji budget
    emoji_budget = ctx.get("emoji_budget", 1)
    emoji_count = _count_emoji(full_text)
    if emoji_count > max(emoji_budget, 0):
        violations.append(
            f"emoji count {emoji_count} exceeds budget {emoji_budget}"
        )
    if emoji_budget == 0 and emoji_count > 0:
        violations.append("persona has 0-emoji budget but copy contains emoji")

    # 4. Banned vocabulary (word-boundary match, case-insensitive)
    for word in _BANNED_VOCAB:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, full_text, re.IGNORECASE):
            violations.append(f"banned vocab: '{word}'")

    # 5. Numbers not in whitelist
    whitelist = set(ctx.get("numbers_whitelist") or [])
    found_tokens = _extract_number_tokens(full_text)
    for token in found_tokens:
        # Skip bare integers unless very long (prices have decimals)
        if re.match(r"^\d{1,2}$", token):
            continue  # single/two-digit bare integers are fine (e.g. "T1", "3 weeks")
        if token not in whitelist:
            violations.append(f"number '{token}' not in whitelist")

    # 6. Signal posts: invalidation / "what would change" + disclosure
    if ctx.get("type") == "signal":
        lower = full_text.lower()
        has_invalidation = any(word in lower for word in (
            "invalidat", "stop", "below", "above", "what would change",
            "kills it", "closes below", "breaks below", "breaks above",
        ))
        if not has_invalidation:
            violations.append(
                "signal post missing invalidation / 'what would change' phrase"
            )
        has_disclosure = any(phrase in lower for phrase in (
            "size appropriately", "not financial advice", "historical",
            "not a guarantee", "do your own", "position sizing",
            "publicly", "track it", "grade", "receipt",
        ))
        if not has_disclosure:
            violations.append(
                "signal post missing honesty disclosure / historical caveat"
            )

    # 7. Duplicate headline within batch (case-insensitive exact + Jaccard)
    if batch_headlines:
        hl_lower = headline.lower().strip()
        for other in batch_headlines:
            if other.lower().strip() == hl_lower:
                violations.append(f"duplicate headline: '{headline[:60]}'")
                break
            if _token_jaccard(headline, other) > _JACCARD_THRESH:
                violations.append(
                    f"near-duplicate headline (Jaccard>{_JACCARD_THRESH}): '{headline[:60]}'"
                )
                break

    return violations


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic variant templates (the anti-bot-voice library)
#
# Key rules for every template:
# - MUST weave in {top_fact} (or explicitly use a plan number)
# - chart posts MUST include {top_fact} (a digit/% fact)
# - no "Here's the score", "The chart. That's it.", "We made a call. Here's what happened."
# - each (type, persona) has 4-6 structurally different variants
# ─────────────────────────────────────────────────────────────────────────────

# Template format: (headline_template, body_template)
# Available tokens: {cashtag}, {ticker}, {entry}, {t1}, {t2}, {inv},
#                   {top_fact}, {direction_word}, {gain}, {loss}, {stop},
#                   {target_label}, {win_rate}

_TEMPLATES: dict[tuple[str, str], list[tuple[str, str]]] = {

    # ── signal / authoritative desk ───────────────────────────────────────────
    ("signal", "authoritative desk"): [
        (
            "{cashtag} — setup flagged at {entry}",
            "{top_fact}. Entry at {entry}, first target {t1}. "
            "What would change our mind: a close back below {entry}. Size appropriately.",
        ),
        (
            "{cashtag} in focus — entry {entry}",
            "We're watching {ticker}: {top_fact}. "
            "Setup entry {entry}, T1 at {t1}. Invalidation at {inv}. "
            "We'll track this one publicly.",
        ),
        (
            "{cashtag} — the chart spoke first",
            "{top_fact}. That's why {ticker} is on the board at {entry}. "
            "First level: {t1}. A close below {entry} kills the thesis. "
            "Position sizing is everything.",
        ),
        (
            "{cashtag} flagged | {entry} is the line",
            "{top_fact}. Entry {entry}. T1 {t1}. "
            "Below {entry} and we're out — position sizing is everything here.",
        ),
        (
            "{cashtag} | opportunity at {entry}",
            "{ticker} is showing something: {top_fact}. "
            "Entry {entry}, target {t1}. "
            "Invalidation below {inv}. We'll track this one publicly.",
        ),
    ],

    # ── signal / dry, receipts-forward ───────────────────────────────────────
    ("signal", "dry, receipts-forward"): [
        (
            "{cashtag} alert | entry {entry}",
            "{top_fact}. {ticker} flagged at {entry}. T1: {t1}. "
            "Invalidation: close below {entry}. Going in the receipt book.",
        ),
        (
            "{cashtag} | {entry} entry, {t1} target",
            "{top_fact}. Numbers: entry {entry}, T1 {t1}, stop below {inv}. "
            "We grade these publicly — outcome coming.",
        ),
        (
            "{cashtag} — board entry at {entry}",
            "{top_fact}. Entry {entry}. Target {t1}. Stop: below {inv}. "
            "This one goes in the ledger. We'll post the outcome.",
        ),
        (
            "Adding {cashtag} at {entry}",
            "{top_fact}. Entry {entry}, first take at {t1}. "
            "Below {entry} is the exit — clean stop, clean accounting. "
            "Graded publicly either way.",
        ),
    ],

    # ── signal / specialist ───────────────────────────────────────────────────
    ("signal", "specialist"): [
        (
            "{cashtag} — sector move flagged at {entry}",
            "{top_fact}. That's the vertical confirming what we've been tracking. "
            "Entry {entry}, first level {t1}. "
            "Below {entry} and the thesis is off the table. Position sizing is everything.",
        ),
        (
            "{cashtag} | this vertical just set up",
            "{top_fact}. Entry around {entry}, first level at {t1}. "
            "The macro backdrop supports this sector read. "
            "Close back below {inv} changes the picture. We'll track it publicly.",
        ),
        (
            "{cashtag} in our sector — entry {entry}",
            "{top_fact}. That's the tell in this vertical. Entry {entry}, T1 {t1}. "
            "Position sizing matters more here than anywhere. Below {entry}: exit.",
        ),
        (
            "Sector nerd alert: {cashtag} at {entry}",
            "{top_fact}. We track this vertical closely — this is the setup we wait for. "
            "Entry {entry}, target {t1}. Below {inv} invalidates. "
            "We'll grade this one publicly.",
        ),
    ],

    # ── signal / educational ──────────────────────────────────────────────────
    ("signal", "educational"): [
        (
            "Live example: {cashtag} at {entry}",
            "{top_fact}. We talk about setups in theory — {ticker} is showing one right now. "
            "Entry {entry}, target {t1}. What would change this: close below {inv}. "
            "We'll track it publicly so you can watch it unfold.",
        ),
        (
            "{cashtag}: here's what a setup looks like",
            "{top_fact}. That's why {ticker} made the board. Entry {entry}, T1 {t1}. "
            "Invalidation — the thing that proves us wrong — is below {inv}. "
            "Sizing is the skill, not the entry. We'll post the outcome.",
        ),
        (
            "Here's the setup — {cashtag} at {entry}",
            "Most of the time nothing qualifies. {ticker} qualifies. {top_fact}. "
            "Entry {entry}, first target {t1}. Below {inv} = wrong. We'll post the outcome.",
        ),
        (
            "{cashtag} | a real-time setup example",
            "{top_fact}. Entry {entry}. T1: {t1}. Stop: below {inv}. "
            "This is what 'wait for the setup' looks like in practice. "
            "Tracking it publicly.",
        ),
    ],

    # ── signal / fast, reactive ───────────────────────────────────────────────
    ("signal", "fast, reactive"): [
        (
            "{cashtag} | moving. Entry {entry}",
            "{top_fact}. Entry {entry}, T1 {t1}. Quick stop: below {entry}. "
            "On the board. Grading it publicly.",
        ),
        (
            "{cashtag} flagged | {entry}",
            "{top_fact}. Setup in. Entry {entry}, target {t1}. Below {inv}: out. "
            "Tracking this one.",
        ),
        (
            "{cashtag} | {entry} entry live",
            "{top_fact}. Entry {entry}. First target {t1}. Stop at {inv}. "
            "Watching it — outcome posted either way.",
        ),
        (
            "{cashtag} | adding at {entry}",
            "{top_fact}. In at {entry}. Target {t1}. Below {inv} = wrong. "
            "Adding to the board. Position sizing is everything.",
        ),
    ],

    # ── signal / pattern/history ──────────────────────────────────────────────
    ("signal", "pattern/history"): [
        (
            "{cashtag} — this pattern has a track record",
            "{top_fact}. {ticker} is tracing a setup we've tracked before. "
            "Entry {entry}, target {t1}. What would change this: close below {entry}. "
            "The pattern says patience pays — we'll post progress publicly.",
        ),
        (
            "{cashtag} | historical setup at {entry}",
            "{top_fact}. Last time {ticker} set up like this, the move followed. "
            "Entry {entry}, T1 {t1}. Below {inv} changes the picture. "
            "We'll track the outcome.",
        ),
        (
            "{cashtag} — the precedent matters here",
            "{top_fact}. We've seen this before in {ticker}. Entry {entry}, first level {t1}. "
            "Invalidation below {inv}. Not predicting — pointing at the rhyme. "
            "Grading it publicly.",
        ),
        (
            "{cashtag} | setup entry {entry}",
            "{top_fact}. Pattern active. Entry {entry}, target {t1}. "
            "Below {entry} means the pattern broke — we exit. "
            "Position sizing is everything here.",
        ),
    ],

    # ── chart / authoritative desk ────────────────────────────────────────────
    ("chart", "authoritative desk"): [
        (
            "{ticker} — what the chart shows",
            "{cashtag}: {top_fact}. That's the picture. Level to watch: {entry}.",
        ),
        (
            "{ticker} price context | {entry} is the line",
            "{top_fact}. {cashtag} at {entry}. One chart, one story.",
        ),
        (
            "{cashtag} — chart of the week",
            "{top_fact}. The level: {entry}. No thesis beyond what you can see.",
        ),
        (
            "{ticker} — the chart says more than we could",
            "{cashtag}: {top_fact}. Key level: {entry}.",
        ),
        (
            "{cashtag} | chart context this week",
            "{top_fact}. Price at {entry}. What's next is what the chart already told you.",
        ),
    ],

    # ── chart / dry, receipts-forward ─────────────────────────────────────────
    ("chart", "dry, receipts-forward"): [
        (
            "{ticker} | chart",
            "{cashtag}: {top_fact}. Level: {entry}.",
        ),
        (
            "{cashtag} — one chart, no spin",
            "{top_fact}. {ticker} at {entry}. Numbers are the commentary.",
        ),
        (
            "{ticker} — chart update",
            "{top_fact}. {cashtag} at {entry}. Draws its own conclusion.",
        ),
        (
            "{cashtag} | what the tape shows",
            "{top_fact}. Level: {entry}. Chart speaks.",
        ),
    ],

    # ── chart / specialist ────────────────────────────────────────────────────
    ("chart", "specialist"): [
        (
            "{ticker} — sector chart this week",
            "{cashtag}: {top_fact}. This vertical is telling a story. Level: {entry}.",
        ),
        (
            "{cashtag} | the vertical in chart form",
            "{top_fact}. {ticker} at {entry}. The sector context is right here.",
        ),
        (
            "{ticker} — this chart matters for the theme",
            "{cashtag}: {top_fact}. Level to watch: {entry}.",
        ),
        (
            "{cashtag} | sector price context",
            "{top_fact}. {ticker} at {entry}. One picture is worth the thread.",
        ),
    ],

    # ── chart / educational ───────────────────────────────────────────────────
    ("chart", "educational"): [
        (
            "Chart breakdown: {ticker}",
            "{cashtag}: {top_fact}. Key things to notice: the level at {entry} and what it means.",
        ),
        (
            "{ticker} — walk through the chart",
            "{top_fact}. That's one reason {cashtag} at {entry} is interesting to watch.",
        ),
        (
            "What this chart on {ticker} is showing",
            "{cashtag}: {top_fact}. Level: {entry}. Sometimes the chart explains it better than we can.",
        ),
        (
            "{cashtag} | chart anatomy this week",
            "{top_fact}. {ticker} at {entry}. Here's what that means.",
        ),
    ],

    # ── chart / fast, reactive ────────────────────────────────────────────────
    ("chart", "fast, reactive"): [
        (
            "{ticker} chart | quick look",
            "{cashtag}: {top_fact}. Level {entry}. Make your own call.",
        ),
        (
            "{cashtag} | chart update",
            "{top_fact}. {ticker} at {entry}.",
        ),
        (
            "Fast chart: {ticker}",
            "{cashtag}: {top_fact}. {entry} is the level.",
        ),
        (
            "{ticker} | tape check",
            "{top_fact}. {cashtag} at {entry}.",
        ),
    ],

    # ── chart / pattern/history ───────────────────────────────────────────────
    ("chart", "pattern/history"): [
        (
            "{ticker} — pattern in the chart",
            "{cashtag}: {top_fact}. This chart matches something we've tracked. Level: {entry}.",
        ),
        (
            "{cashtag} | historical read on the chart",
            "{top_fact}. {ticker} at {entry}. The rhyme is right there in the picture.",
        ),
        (
            "{ticker} chart | precedent matters",
            "{top_fact}. {cashtag} at {entry}. Last time this looked like this, watch what followed.",
        ),
        (
            "{cashtag} — chart with context",
            "{top_fact}. Level: {entry}. The pattern is pointing.",
        ),
    ],

    # ── education (all voices use shared variants; persona-specific below) ────
    ("education", "authoritative desk"): [
        (
            "What 'conviction' actually means at the desk",
            "When we flag something, it means the setup passed our criteria — not that it's certain. "
            "The number next to it is the invalidation. That's the constraint.",
        ),
        (
            "Why invalidation matters more than the target",
            "A target tells you where we're going. An invalidation tells you we're wrong. "
            "Knowing when you're wrong is the skill.",
        ),
        (
            "The part most people skip: position sizing",
            "You can be right on the direction and still lose money. "
            "The size of the position relative to the stop is the part that matters.",
        ),
        (
            "How we decide what goes on the board",
            "Not every setup makes it. The ones that do share one thing: "
            "a clear level that proves the thesis wrong. No clear invalidation, no post.",
        ),
    ],
    ("education", "dry, receipts-forward"): [
        (
            "How we track our calls",
            "Every signal goes in the ledger. Win, loss, or mixed — we post the outcome. "
            "The receipt book is the accountability layer.",
        ),
        (
            "Why we post losses",
            "Losses are information. We post them flat — same tone as wins. "
            "The stop did its job. That's the point.",
        ),
        (
            "What a 'receipt' actually is",
            "A receipt is the outcome of a call. Entry, target or stop hit, result. "
            "We post it regardless of direction.",
        ),
        (
            "The ledger system: how it works",
            "Signal goes in. Outcome comes out. That's the whole system. "
            "No selective memory, no cherry-picking.",
        ),
    ],
    ("education", "specialist"): [
        (
            "One thing this vertical gets wrong",
            "Most people read this sector's moves through the wrong lens. "
            "Here's the cleaner framework.",
        ),
        (
            "The factor that moves this vertical",
            "It's not what most people focus on. The one factor that actually drives this sector "
            "has been consistent for years. Here's what to watch instead.",
        ),
        (
            "Why sector context beats individual stock analysis here",
            "In this vertical, the tide really does lift or sink most boats. "
            "Get the macro read on the sector right first.",
        ),
        (
            "How to think about timing in this vertical",
            "Entry timing matters more in cyclical sectors. "
            "Here's the checklist we use before flagging anything.",
        ),
    ],
    ("education", "educational"): [
        (
            "Plain English: what is a 'setup'?",
            "A setup is a price configuration that, historically, has been a good time to pay attention. "
            "Not a guarantee — just a reason to look closer.",
        ),
        (
            "Why the 'what would change this' line matters",
            "Every signal post has a line that says what would make us wrong. "
            "That line is the whole thesis. Everything else is details.",
        ),
        (
            "Here's the part most people miss",
            "Being right about the direction is only half the job. "
            "The other half is knowing exactly when you're wrong. That's the stop.",
        ),
        (
            "What 'tracking publicly' actually means",
            "When we say we'll track it publicly, we mean: win, loss, or nothing — "
            "the outcome gets posted. That's the only honest model.",
        ),
    ],
    ("education", "fast, reactive"): [
        (
            "Quick primer: what's a setup?",
            "Price configuration that's historically worth watching. "
            "Not a buy signal. A reason to look.",
        ),
        (
            "Fast: why the stop matters more than the target",
            "Target = where we're going. Stop = when we're wrong. "
            "Get the stop wrong, the target doesn't matter.",
        ),
        (
            "One-minute explanation: position sizing",
            "Risk a fixed amount per trade. The stop sets the size. "
            "That's the whole framework.",
        ),
        (
            "Quick: what invalidation means",
            "The level that proves us wrong. "
            "If price hits it, we're out. Clean, fast, no ego.",
        ),
    ],
    ("education", "pattern/history"): [
        (
            "When history rhymes: a primer",
            "Historical analogues are useful but dangerous. "
            "We use them to calibrate expectations, not make predictions.",
        ),
        (
            "Last time the market looked like this",
            "We're not predicting repeats. We're looking at base rates. "
            "Here's what happened in comparable setups.",
        ),
        (
            "The base rate mindset",
            "What happened 70% of the time in similar conditions is useful context. "
            "It's never a guarantee. That's what 70% means.",
        ),
        (
            "How we use historical analogues without fooling ourselves",
            "Rhyme, not repeat. The context matters more than the pattern. "
            "Here's the filter we apply before drawing any analogy.",
        ),
    ],

    # ── macro (all voices) ────────────────────────────────────────────────────
    ("macro", "authoritative desk"): [
        (
            "Macro backdrop this week",
            "The regime is shifting. What it means for risk assets: quality over leverage, "
            "patience over chasing. Watch the next data point carefully.",
        ),
        (
            "What the macro is saying right now",
            "Rates, liquidity, and positioning are telling three different stories. "
            "Here's how we're reading the confluence.",
        ),
        (
            "The one macro signal we're watching",
            "Of everything on the dashboard, this is the signal that matters most right now. "
            "Here's why and what it changes.",
        ),
        (
            "Macro note: the setup for the week",
            "The backdrop is nuanced. One clear read: "
            "momentum is bifurcated, and that historically resolves in one direction.",
        ),
    ],
    ("macro", "dry, receipts-forward"): [
        (
            "Macro: current regime",
            "Regime read: constructive but not broadly. "
            "Tracking the key signals. Will update when the picture changes.",
        ),
        (
            "Macro update | this is where we stand",
            "Two things are true right now. Tracking the resolution between them.",
        ),
        (
            "The macro scorecard this week",
            "Rates: noted. Liquidity: noted. Positioning: noted. "
            "Net read: cautious on leverage, selective on risk.",
        ),
        (
            "Regime check",
            "The environment has changed since last month. Here's the updated read.",
        ),
    ],
    ("macro", "specialist"): [
        (
            "Macro note for this sector",
            "The macro backdrop matters more for this vertical than most. "
            "Here's the read that's driving our positioning.",
        ),
        (
            "How macro is affecting our sector right now",
            "Rates and liquidity have direct implications for this vertical. "
            "Here's how we're thinking about it.",
        ),
        (
            "Sector macro alignment: this week",
            "The macro is supportive for this theme. That alignment doesn't happen often — "
            "here's what changes if it breaks.",
        ),
        (
            "The macro tailwind (or headwind) this vertical is facing",
            "One factor is dominating the macro backdrop for our sector. "
            "Here's what it is and what to watch.",
        ),
    ],
    ("macro", "educational"): [
        (
            "What the macro says right now — plain English",
            "Breaking down the current environment without the jargon: "
            "here's the one-sentence read and what it has historically meant for prices.",
        ),
        (
            "How to read the macro backdrop",
            "Most macro coverage is noise. Here's the signal: "
            "the three indicators we watch and what they're saying.",
        ),
        (
            "The thing most people get wrong about the macro",
            "The macro doesn't tell you what to buy. It tells you what environment you're trading in. "
            "Here's the distinction and why it matters.",
        ),
        (
            "Plain-English macro update",
            "Rates are doing one thing. Liquidity is doing another. "
            "Here's what the gap between them usually means.",
        ),
    ],
    ("macro", "fast, reactive"): [
        (
            "Macro update | fast",
            "Regime: constructive with caveats. Key signal flipped. Adjusting accordingly.",
        ),
        (
            "Quick macro read",
            "Two things changed in the macro backdrop this week. Here's the short version.",
        ),
        (
            "Macro | what just changed",
            "The data shifted. Here's the fast read on what it means for risk assets.",
        ),
        (
            "Fast macro note",
            "The backdrop is different from last week. One signal stands out. Here's what it is.",
        ),
    ],
    ("macro", "pattern/history"): [
        (
            "Macro analogue: this has happened before",
            "The current environment has a historical parallel. "
            "Here's what the market did then and what's different now.",
        ),
        (
            "Historical read on the macro backdrop",
            "Last time rates + liquidity looked like this was [year]. "
            "The chart context from that episode is worth knowing.",
        ),
        (
            "The macro rhyme — what history says",
            "We're not predicting a repeat. But the setup has familiar features. "
            "Here's the base rate from comparable backdrops.",
        ),
        (
            "Macro precedent: what this regime historically meant",
            "Not every macro regime has a clean analogue. "
            "This one does — and the signal it sent then is worth knowing.",
        ),
    ],

    # ── receipt (all voices) — ONLY used when graded_receipts provides real data ──
    ("receipt", "authoritative desk"): [
        (
            "{cashtag} outcome | {target_label} at {t1}",
            "{cashtag}: {target_label} hit at {t1} ({gain}). Entry was {entry}. "
            "Thesis played. We'll stay with the runner per the plan.",
        ),
        (
            "{cashtag} — call graded | {gain} on {target_label}",
            "Entry {entry}, {target_label} at {t1}: {gain}. "
            "Process held. Next level is {t2} or stop triggers.",
        ),
        (
            "{cashtag} stopped out | {loss} from entry",
            "Entry {entry}, stop at {stop}: {loss}. Stop did its job. "
            "Position closed clean. Next setup, same discipline.",
        ),
        (
            "{cashtag} | mixed outcome — {gain} then stopped at {loss}",
            "{target_label} hit at {t1} ({gain}), then stopped at {stop} ({loss}). "
            "Entry: {entry}. The partial worked. The trail didn't. Graded.",
        ),
    ],
    ("receipt", "dry, receipts-forward"): [
        (
            "{cashtag} receipt | {target_label}: {gain}",
            "Entry {entry}. {target_label} at {t1}: {gain}. In the ledger.",
        ),
        (
            "{cashtag} stopped | {loss}",
            "Entry {entry}. Stop at {stop}: {loss}. Stop worked. Next.",
        ),
        (
            "{cashtag} | mixed — {gain} then {loss}",
            "Entry {entry}. {target_label} hit {t1} ({gain}). Stopped at {stop} ({loss}). "
            "Two outcomes on one trade. Graded.",
        ),
        (
            "{cashtag} graded | {gain}",
            "Entry {entry}. {target_label} at {t1}: {gain}. Outcome posted.",
        ),
    ],
    ("receipt", "specialist"): [
        (
            "Vertical outcome: {cashtag} | {gain}",
            "Our sector read played. {cashtag}: entry {entry}, {target_label} at {t1} = {gain}.",
        ),
        (
            "{cashtag} — sector call graded | {loss}",
            "The sector read didn't play. Entry {entry}, stopped at {stop}: {loss}. Graded.",
        ),
        (
            "{cashtag} | mixed vertical outcome",
            "{target_label} hit ({gain}), then stopped ({loss}). {cashtag} entry {entry}. "
            "Net: the partial worked, the runner didn't.",
        ),
        (
            "{cashtag} follow-up | {gain} on {target_label}",
            "Entry {entry}. {target_label}: {t1} hit for {gain}. Sector thesis held.",
        ),
    ],
    ("receipt", "educational"): [
        (
            "{cashtag} outcome: this is what accountability looks like",
            "We said {cashtag} at {entry}. {target_label} at {t1}: {gain}. "
            "Win, loss, or draw — we post the result. That's the model.",
        ),
        (
            "{cashtag} stopped | this is what a loss looks like",
            "Entry {entry}. Stop at {stop}: {loss}. "
            "The stop did exactly what stops are supposed to do.",
        ),
        (
            "{cashtag} | mixed result — a real example",
            "{target_label} hit at {t1} ({gain}), then the runner stopped at {stop} ({loss}). "
            "Entry {entry}. This is what 'partial' looks like in practice.",
        ),
        (
            "Live outcome: {cashtag} at {gain}",
            "Entry {entry}. {target_label} hit at {t1}: {gain}. "
            "We said we'd track it publicly. Here's the result.",
        ),
    ],
    ("receipt", "fast, reactive"): [
        (
            "{cashtag} | {target_label} hit: {gain}",
            "Entry {entry}. {t1} tagged. {gain}. Graded.",
        ),
        (
            "{cashtag} stopped | {loss}",
            "Entry {entry}. Stop {stop}. {loss}. Clean exit.",
        ),
        (
            "{cashtag} | mixed: {gain} then {loss}",
            "Entry {entry}. {target_label} hit ({gain}). Stop {stop} ({loss}). Two outcomes.",
        ),
        (
            "{cashtag} outcome | {gain}",
            "Entry {entry}. {target_label} at {t1}: {gain}.",
        ),
    ],
    ("receipt", "pattern/history"): [
        (
            "{cashtag} — did the pattern hold? Yes: {gain}",
            "We flagged a setup. Entry {entry}. {target_label} at {t1}: {gain}. Pattern held.",
        ),
        (
            "{cashtag} — pattern outcome | stopped at {loss}",
            "Entry {entry}. Stop at {stop}: {loss}. "
            "The setup didn't follow through this time. Graded.",
        ),
        (
            "{cashtag} | historical pattern graded",
            "Entry {entry}. {target_label} hit ({gain}), runner stopped ({loss}). "
            "The rhyme had a verse and a coda.",
        ),
        (
            "{cashtag} outcome | {gain} from {entry}",
            "Entry {entry}. {target_label}: {t1} = {gain}. Historical setup confirmed.",
        ),
    ],

    # ── watchlist (all voices) ────────────────────────────────────────────────
    ("watchlist", "authoritative desk"): [
        (
            "On our radar this week",
            "Names we're watching but haven't acted on. The setup isn't complete — "
            "when it is, we'll post the entry.",
        ),
        (
            "Watch list | not yet",
            "These names are interesting. None have triggered an entry yet. "
            "Watching the levels.",
        ),
        (
            "What's on the desk this week",
            "A few names are close to completing setups. Not acting yet. "
            "Keeping the list transparent.",
        ),
        (
            "Under observation: this week's names",
            "The board has gaps that could fill. These names are in contention. "
            "Entry conditions not met — yet.",
        ),
    ],
    ("watchlist", "dry, receipts-forward"): [
        (
            "Watch list | no position",
            "Watching these. No entry yet. Will post when something triggers.",
        ),
        (
            "Radar: names we're monitoring",
            "On the list, not on the board. The setup isn't complete. Watching.",
        ),
        (
            "Watchlist update | not triggered",
            "These names are close. Haven't acted. Will post the entry if the setup completes.",
        ),
        (
            "Under watch | positions not open",
            "Tracking these. No entry taken. Conditions not met.",
        ),
    ],
    ("watchlist", "specialist"): [
        (
            "Vertical watch list this week",
            "Names in our sector that are setting up but haven't triggered. "
            "Close — not close enough.",
        ),
        (
            "Sector radar | watching not acting",
            "The vertical has a few names near entry conditions. Not acting yet. "
            "Will post if one triggers.",
        ),
        (
            "What's near entry in the sector",
            "Three names in the vertical are worth watching. Setup not complete — "
            "but we're close on at least one.",
        ),
        (
            "Specialist watch: this week's setups in progress",
            "Monitoring these in the sector. The macro backdrop helps but entry isn't clean yet.",
        ),
    ],
    ("watchlist", "educational"): [
        (
            "What goes on a watch list — and why",
            "Not every interesting name makes the board. "
            "The ones on this list are interesting — just not ready.",
        ),
        (
            "The watch list: a real example of how we filter",
            "Here are the names we're monitoring and what's missing before they get an entry. "
            "This is the filter in action.",
        ),
        (
            "Why we publish the watch list",
            "Transparency on what almost made it is as useful as the actual signals. "
            "Here's what we're close on.",
        ),
        (
            "On our radar | here's what we're waiting for",
            "These names are interesting. Here's exactly what needs to happen for each "
            "to make it onto the board.",
        ),
    ],
    ("watchlist", "fast, reactive"): [
        (
            "Quick radar | watching these",
            "These are on the list right now. Not triggered. Watching.",
        ),
        (
            "Watching | not acting",
            "Fast watch list: close setups, no entry yet. Will post when one triggers.",
        ),
        (
            "Watch list update",
            "A few names near entry conditions. Nothing triggered. On watch.",
        ),
        (
            "Radar check | names close to entry",
            "These are the names near setup completion. Haven't acted. Watching.",
        ),
    ],
    ("watchlist", "pattern/history"): [
        (
            "Pattern watch list | not triggered",
            "Names tracing patterns worth monitoring. Historical context says these "
            "could be close. Not acting yet.",
        ),
        (
            "Historical watch: patterns in progress",
            "These names are in the middle of setups that have historical analogues. "
            "No entry yet — watching the completion.",
        ),
        (
            "Watch list | the rhymes in progress",
            "A few names are tracing patterns we've tracked before. "
            "Watching for the setup to complete.",
        ),
        (
            "Monitoring setups with historical support",
            "Not every pattern completes. These are the ones we think have a shot. "
            "No entry — yet.",
        ),
    ],

    # ── event (all voices) ────────────────────────────────────────────────────
    ("event", "authoritative desk"): [
        (
            "Market event: our read",
            "Today's move has a read: the price says one thing and the data says another. "
            "We watch for the resolution.",
        ),
        (
            "What just happened — and what it changes",
            "The event hit. Here's our read on what it actually means versus what the "
            "first-hour reaction suggested.",
        ),
        (
            "Event reaction | the desk's take",
            "Fast-moving events get two reads: the knee-jerk and the considered one. "
            "Here's ours.",
        ),
        (
            "Post-event: what we're watching now",
            "The event is in the books. Here's what the next session should clarify.",
        ),
    ],
    ("event", "dry, receipts-forward"): [
        (
            "Event reaction | numbers first",
            "Event happened. Numbers changed. Here's what changed and what it does "
            "to our current positions.",
        ),
        (
            "Post-event | the scorecard update",
            "Event logged. Here's the impact on the board.",
        ),
        (
            "What the event changed",
            "Not much drama — here's the actual data and what it shifts.",
        ),
        (
            "Event: reaction logged",
            "Reaction noted. Positions unaffected unless the next session confirms the move.",
        ),
    ],
    ("event", "specialist"): [
        (
            "Event impact on our sector",
            "Today's event has direct implications for the vertical. Here's the read.",
        ),
        (
            "How this event hits our theme",
            "The sector absorbs events differently than the broad market. "
            "Here's what this one changes for us.",
        ),
        (
            "Sector event reaction",
            "The event moved the vertical. Here's whether that move makes sense to us.",
        ),
        (
            "Event + sector: our take",
            "The vertical reacted. Here's our read on whether the reaction is right.",
        ),
    ],
    ("event", "educational"): [
        (
            "What today's event means — plain English",
            "Big event today. Here's what it actually means for markets, "
            "without the noise.",
        ),
        (
            "Why events move markets — and this one in particular",
            "Markets move on surprises relative to expectations. Here's what was expected, "
            "what happened, and why the gap matters.",
        ),
        (
            "Event 101: how to read what just happened",
            "Events get oversimplified in both directions. Here's the clean read on "
            "what actually matters.",
        ),
        (
            "Breaking down today's event",
            "Event happened. A lot of commentary, most of it noise. "
            "Here's the signal.",
        ),
    ],
    ("event", "fast, reactive"): [
        (
            "Reaction: what just happened",
            "Fast take: the move was X. The read is Y. What to watch next: Z.",
        ),
        (
            "Event | quick read",
            "Event in. Reaction: fast. Considered read: here it is.",
        ),
        (
            "What just moved and why",
            "Event catalyst confirmed. Here's the fast version of what it means.",
        ),
        (
            "Fast reaction | event live",
            "Event hit. Price moved. Here's what the tape is saying.",
        ),
    ],
    ("event", "pattern/history"): [
        (
            "Historical read on today's event",
            "This event type has a track record. Here's what history says about "
            "the aftermath — and what's different this time.",
        ),
        (
            "What the playbook says about events like this",
            "Not all events are created equal. This one rhymes with something. "
            "Here's the historical base rate.",
        ),
        (
            "Event analogue: what happened last time",
            "The setup before this event had a precedent. "
            "Here's what the chart looked like then and now.",
        ),
        (
            "The historical pattern after events like this",
            "Comparable events have a consistent pattern in the aftermath. "
            "Not predicting — pointing at the base rate.",
        ),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Per-voice chart context filler (used when no OHLCV data / top_fact is empty)
# Each is structurally different so Jaccard similarity stays below 0.7 across voices.
# ─────────────────────────────────────────────────────────────────────────────

_CHART_VOICE_FILLER: dict[str, str] = {
    "authoritative desk": "Price is the most honest signal we have",
    "dry, receipts-forward": "Numbers tell the story; no interpretation needed",
    "specialist": "This vertical is at a technical inflection point",
    "educational": "Read the trend before reading the news",
    "fast, reactive": "Tape doesn't lie — structure is setting up",
    "pattern/history": "This chart shape has a documented history worth knowing",
}

# When receipt has no graded data (gain/loss both absent), use this filler
# to keep bodies distinct across voices (pending outcome)
_RECEIPT_VOICE_PENDING: dict[str, str] = {
    "authoritative desk": "Outcome pending — will post the result when graded.",
    "dry, receipts-forward": "Pending. Receipt posted on close.",
    "specialist": "Tracking the vertical outcome. Result forthcoming.",
    "educational": "We track every call. Outcome update on next close.",
    "fast, reactive": "Watching. Grade posted on resolution.",
    "pattern/history": "Pattern outcome TBD. Historical context follows.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Template rendering
# ─────────────────────────────────────────────────────────────────────────────

def _render_template(template: str, ctx: dict) -> str:
    """Fill template tokens from context dict. Missing → empty string.

    Special handling for {top_fact}: when empty, substitutes a voice-specific
    context filler so chart posts stay distinctive across voices even without
    OHLCV data. When present, the real fact text is used verbatim.
    """
    result = template
    top_fact = ctx.get("top_fact_text", "") or ""

    if not top_fact:
        # Substitute a voice-specific filler so bodies stay distinct per-voice
        # even when no OHLCV data is available (test mode / missing parquet)
        voice = ctx.get("voice", "authoritative desk")
        filler = _CHART_VOICE_FILLER.get(voice, _CHART_VOICE_FILLER["authoritative desk"])
        result = result.replace("{top_fact}", filler)
    else:
        result = result.replace("{top_fact}", top_fact)

    # Map remaining template tokens to context keys
    gain = ctx.get("gain_pct_str", "") or ""
    loss = ctx.get("loss_pct_str", "") or ""
    substitutions = {
        "{cashtag}": ctx.get("cashtag", ""),
        "{ticker}": ctx.get("ticker", ""),
        "{entry}": ctx.get("entry_str", ""),
        "{t1}": ctx.get("t1_str", ""),
        "{t2}": ctx.get("t2_str", ""),
        "{inv}": ctx.get("inv_str", ""),
        "{direction_word}": "higher" if ctx.get("direction") == "BULL" else "lower",
        "{gain}": gain,
        "{loss}": loss,
        "{stop}": ctx.get("stop_str", ""),
        "{target_label}": ctx.get("target_label", "T1"),
        "{win_rate}": ctx.get("win_rate_str", ""),
    }
    for token, value in substitutions.items():
        result = result.replace(token, value or "")
    # Clean up orphaned punctuation from empty substitutions:
    # "T1 at 95.00: ." → "T1 at 95.00."  |  "| {gain}" → ""
    result = re.sub(r'\s*:\s+\.', '.', result)
    result = re.sub(r'\s*\|\s*$', '', result)
    result = re.sub(r'  +', ' ', result)
    return result.strip()


def _pick_variant(
    ctx: dict,
    variants: list[tuple[str, str]],
    slot: str = "",
    batch_index: int = 0,
) -> tuple[str, str]:
    """Pick a variant deterministically.

    For ticker-bearing types (signal, chart, receipt): hash on ticker+account+slot
    so the same ticker on different accounts gets different variants.
    For non-ticker types (education, macro, watchlist, event): rotate by batch_index
    to guarantee variant diversity across a large plan and avoid headline collisions.
    """
    ticker = ctx.get("ticker", "")
    if ticker:
        account = ctx.get("account", "")
        key = f"{ticker}|{account}|{slot}"
        h = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
        return variants[h % len(variants)]
    else:
        # Non-ticker post: rotate through variants by batch index
        return variants[batch_index % len(variants)]


# ─────────────────────────────────────────────────────────────────────────────
# write_posts_deterministic
# ─────────────────────────────────────────────────────────────────────────────

def write_posts_deterministic(contexts: list[dict]) -> list[dict]:
    """Generate (headline, body) for each context via deterministic variant selection.

    Returns a list of dicts {headline, body, violations, mode}.
    All posts pass through validate_copy; violations are noted but copy is kept.
    Chart posts MUST contain a concrete fact (a digit or %).

    Variant selection strategy:
    - Ticker posts: hash(ticker + account + slot) → stable per ticker+account
    - Non-ticker posts (education, macro, watchlist, event): rotating counter
      per (type, voice) pair to prevent repeat headlines in the same plan
    """
    results: list[dict] = []
    all_headlines: list[str] = []
    # Rotation counter per (type, voice) for non-ticker types
    type_voice_counters: dict[tuple[str, str], int] = {}

    for i, ctx in enumerate(contexts):
        type_id = ctx.get("type", "signal")
        voice = ctx.get("voice", "authoritative desk")

        key = (type_id, voice)
        variants = _TEMPLATES.get(key)
        if not variants:
            # Fallback: authoritative desk for same type
            variants = _TEMPLATES.get((type_id, "authoritative desk"))
        if not variants:
            # Last-resort generic
            variants = [("{cashtag} update", "Tracking {ticker}. {top_fact}.")]

        ticker = ctx.get("ticker", "")
        slot = ctx.get("slot", str(i))

        if ticker:
            # Ticker post: hash gives stable per ticker+account assignment
            account = ctx.get("account", "")
            hash_key = f"{ticker}|{account}|{slot}"
            h = int(hashlib.sha256(hash_key.encode()).hexdigest()[:8], 16)
            variant_idx = h % len(variants)
        else:
            # Non-ticker post: rotate through variants to avoid headline repeat
            counter = type_voice_counters.get(key, 0)
            variant_idx = counter % len(variants)
            type_voice_counters[key] = counter + 1

        hl_tpl, body_tpl = variants[variant_idx]

        headline = _render_template(hl_tpl, ctx)
        body = _render_template(body_tpl, ctx)

        # Receipt with no graded data: override body to a voice-specific pending note
        # so bodies are distinct across voices even when gain/loss are absent
        if type_id == "receipt" and not ctx.get("gain_pct_str") and not ctx.get("loss_pct_str"):
            body = _RECEIPT_VOICE_PENDING.get(voice, _RECEIPT_VOICE_PENDING["authoritative desk"])

        violations = validate_copy(headline, body, ctx, batch_headlines=all_headlines)
        all_headlines.append(headline)

        results.append({
            "headline": headline,
            "body": body,
            "violations": violations,
            "mode": "deterministic",
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# write_posts_llm  (optional; NEVER called in tests)
# ─────────────────────────────────────────────────────────────────────────────

def write_posts_llm(
    contexts: list[dict],
    cfg: dict,
) -> list[dict] | None:
    """Optional LLM copy generation (batched JSON call).

    Guards:
    - Only runs when cfg.llm.enabled is True AND MARKETING_LLM_ENABLED env var is set
    - Returns None on any failure (caller falls back to deterministic)
    - Every LLM output goes through validate_copy; per-post failures fall back
    - NEVER called in tests (the env var guard ensures this)
    """
    llm_cfg = cfg.get("llm") or {}
    enabled = bool(llm_cfg.get("enabled", False))
    # Additional env-var guard so tests NEVER trigger this path
    env_enabled = os.environ.get("MARKETING_LLM_ENABLED", "").lower() in ("1", "true", "yes")
    if not enabled or not env_enabled:
        return None

    try:
        from engine import config as _config
        model_key = llm_cfg.get("model_key", "marketing_copy")
        llm_models = _config.load().get("llm_models", {}) or {}
        model_id = llm_models.get(model_key, "")
        if not model_id:
            return None

        max_posts = int(llm_cfg.get("max_posts_per_run", 60))
        batch = contexts[:max_posts]

        # Build prompt
        system_prompt = (
            "You are a professional financial copywriter. "
            "For each item in the provided JSON array, write a short social post "
            "(headline + body) in the specified voice, weaving in the top chart fact "
            "and the exact numbers provided. "
            "Output a JSON array of objects with 'headline' and 'body' keys only. "
            "No markdown, no preamble."
        )
        items_payload = [
            {
                "index": i,
                "type": ctx.get("type"),
                "voice": ctx.get("voice"),
                "cashtag": ctx.get("cashtag"),
                "top_fact": ctx.get("top_fact_text"),
                "entry": ctx.get("entry_str"),
                "t1": ctx.get("t1_str"),
                "inv": ctx.get("inv_str"),
                "numbers_whitelist": ctx.get("numbers_whitelist", [])[:10],
            }
            for i, ctx in enumerate(batch)
        ]

        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=model_id,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": (
                    system_prompt + "\n\nItems:\n" + json.dumps(items_payload, indent=2)
                ),
            }],
        )
        raw_text = response.content[0].text if response.content else ""
        # Extract JSON array from response
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if not match:
            return None
        llm_outputs = json.loads(match.group())
        if not isinstance(llm_outputs, list) or len(llm_outputs) != len(batch):
            return None

        # Validate each output; fall back per-post on failure
        det_fallbacks = write_posts_deterministic(batch)
        results: list[dict] = []
        all_headlines: list[str] = []

        for i, (llm_out, ctx) in enumerate(zip(llm_outputs, batch)):
            hl = str(llm_out.get("headline", ""))
            bd = str(llm_out.get("body", ""))
            violations = validate_copy(hl, bd, ctx, batch_headlines=all_headlines)
            if violations:
                # Fall back to deterministic for this post
                fb = det_fallbacks[i]
                results.append({**fb, "mode": "llm_fallback"})
                all_headlines.append(fb["headline"])
            else:
                results.append({"headline": hl, "body": bd, "violations": [], "mode": "llm"})
                all_headlines.append(hl)

        return results

    except Exception:  # noqa: BLE001
        return None
