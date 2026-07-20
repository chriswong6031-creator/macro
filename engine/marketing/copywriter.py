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
# Additional banned-vocab substrings (case-insensitive, full-text match, NOT word-boundary).
# These are longer phrases unlikely to false-positive on a suffix/prefix.
_BANNED_SUBSTRINGS: tuple[str, ...] = (
    "vertical",
    "signal stack",
    "accountability layer",
    "honest model",
    "receipt book",
    "goldilocks",
    "growth score",
    "inflation score",
    "(read:",
    "de-rating",
    "positioning in",
    "implications for",
    "the backdrop",
)
# "regime" and "narrative" must be word-boundary matched to avoid false-positives
# on "regimen", "narratives", etc.
_BANNED_WORD_BOUNDARY: tuple[str, ...] = (
    "regime",
    "narrative",
)
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
# Fact polarity filter (directional-post safety)
# ─────────────────────────────────────────────────────────────────────────────

# Legacy text markers — used ONLY for facts that carry no structured "polarity"
# key (non-M2 facts). Matched at WORD BOUNDARIES so "anchored" can never match
# "red" and "highlight" can never match "high" (the F1 polarity bug: the "red "
# substring in "anchored VWAP" mis-tagged bullish AVWAP facts as bearish).
_BEAR_MARKERS = ("lost", "below", "off its high", "down", "red",
                 "biggest down", "52-week low", "worst")
_BULL_MARKERS = ("reclaimed", "above", "high", "up", "green",
                 "record", "surge", "streak")


def _marker_hits(text: str, markers: tuple[str, ...]) -> bool:
    """True if any marker appears in *text* at a word boundary (case-insensitive).

    Multi-word markers ("off its high") are matched as phrases; single-word
    markers use \\b...\\b so substrings inside larger words never trip
    (e.g. "red" must not fire inside "anchored").
    """
    low = text.lower()
    for m in markers:
        pattern = r"\b" + r"\s+".join(re.escape(w) for w in m.split()) + r"\b"
        if re.search(pattern, low):
            return True
    return False


def _filter_facts_by_polarity(all_facts: list[dict], direction: str) -> list[dict]:
    """Filter chart facts so a directional post never leads with a clashing fact.

    Two lanes:
      • Facts carrying a structured "polarity" (+1/0/-1) are filtered by that key
        alone — never text-matched. A BULL post keeps +1/0; a BEAR post keeps
        -1/0. This is the M2 path and is immune to the "red"/"anchored" bug.
      • Facts WITHOUT "polarity" (legacy facts) fall back to word-boundary marker
        matching: drop a fact whose text hits the opposing-direction markers.

    Empty-result fallback: if the filter drops everything, prefer neutral /
    unknown-polarity facts (polarity 0, or legacy facts that don't hit either
    marker set) before falling back to the full list — so a BULL post can never
    be forced to lead with a structured -1 (bearish) fact.
    """
    is_bear = direction == "BEAR"
    opposing = _BULL_MARKERS if is_bear else _BEAR_MARKERS

    kept: list[dict] = []
    neutral_pool: list[dict] = []  # safe fallback: neutral / non-clashing facts
    for f in all_facts:
        pol = f.get("polarity")
        if pol is not None:
            # Structured path: bull keeps +1/0, bear keeps -1/0.
            if pol == 0:
                kept.append(f)
                neutral_pool.append(f)
            elif (pol > 0) != is_bear:
                # +1 on a bull post, or -1 on a bear post → aligned, keep.
                kept.append(f)
            # else: clashing structured fact → excluded from both kept and pool
        else:
            # Legacy text-marker path (word-boundary).
            if _marker_hits(f.get("text", ""), opposing):
                continue  # clashes with the post direction → drop
            kept.append(f)
            neutral_pool.append(f)

    if kept:
        return kept
    # Prefer neutral/non-clashing facts over reinstating clashing ones.
    if neutral_pool:
        return neutral_pool
    return all_facts


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
         For theme_list items, item may contain "cashtags": [str] (list of cashtags).
    persona: persona card from marketing.yml copywriter.personas.<id>
    facts: output of chart_facts.compute_facts() or theme_facts/mover_facts
    extra: any additional data (combo win_rate for confluence, etc.)

    Returns a dict with every field the writer is allowed to use.
    """
    ticker = item.get("ticker", "")
    cashtag = f"${ticker}" if ticker else ""

    # Multi-cashtag support for theme_list items
    cashtags_list: list[str] = item.get("cashtags") or []
    if cashtag and cashtag not in cashtags_list:
        # single-cashtag types: expose as a single-element list for uniformity
        pass
    cashtag_list_str = " ".join(cashtags_list)  # "$NVDA $AMD $SMCI ..."

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
            top_facts = _filter_facts_by_polarity(all_facts, direction)[:3]
        else:
            top_facts = all_facts[:3]
        whitelist = list(facts.get("numbers_whitelist", []))
        # Extract 4-digit year tokens from all fact texts and add to whitelist.
        # Facts like "first since Nov 2024" produce a bare 4-digit year in copy that
        # the number-validator would otherwise flag as an invented number.
        _year_re = re.compile(r"\b(?:19|20)\d{2}\b")
        for _f in all_facts:
            for _yr_tok in _year_re.findall(_f.get("text", "")):
                if _yr_tok not in whitelist:
                    whitelist.append(_yr_tok)

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

    # For theme_list items: add member cashtag % strings to whitelist
    # (these appear in the body as "$NVDA -2.1% $AMD -4.3% ...")
    theme_data = item.get("_theme_data") or {}
    theme_members = theme_data.get("members") or []
    _theme_member_pcts: list[str] = []
    for _tm in theme_members:
        _tm_pct = _tm.get("pct")
        if _tm_pct is not None:
            try:
                _tm_s = f"{float(_tm_pct):+.1f}%"
                if _tm_s not in whitelist:
                    whitelist.append(_tm_s)
                _theme_member_pcts.append(_tm_s)
            except (TypeError, ValueError):
                pass
    # Also add agg_pct for theme
    _agg = theme_data.get("agg_pct")
    if _agg is not None:
        try:
            _agg_s = f"{float(_agg):+.1f}%"
            if _agg_s not in whitelist:
                whitelist.append(_agg_s)
        except (TypeError, ValueError):
            pass

    # For mover items: add mover pct to whitelist
    mover_data = item.get("_mover_data") or {}
    _mv_pct = mover_data.get("pct")
    if _mv_pct is not None:
        try:
            _mv_s = f"{float(_mv_pct):+.1f}%"
            if _mv_s not in whitelist:
                whitelist.append(_mv_s)
        except (TypeError, ValueError):
            pass

    return {
        # Identity
        "ticker": ticker,
        "cashtag": cashtag,
        "cashtags": cashtags_list,         # list of "$TICKER" strings (theme_list)
        "cashtag_list": cashtag_list_str,  # space-joined "$A $B $C"
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
        # Theme/mover extras
        "theme_name": theme_data.get("theme", ""),
        "theme_direction": theme_data.get("direction", ""),
        "theme_question": theme_data.get("question", ""),
        "theme_agg_pct": (f"{float(_agg):+.1f}%" if _agg is not None else ""),
        "mover_pct": (f"{float(_mv_pct):+.1f}%" if _mv_pct is not None else ""),
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
    item_type = ctx.get("type", "")

    # 1. Cashtag on every ticker post
    ticker = ctx.get("ticker", "")
    if ticker and item_type in ("signal", "chart", "receipt", "watchlist", "mover"):
        cashtag = f"${ticker}"
        if cashtag not in full_text:
            violations.append(f"missing cashtag {cashtag}")

    # 1b. theme_list: multi-cashtag rules
    if item_type == "theme_list":
        cashtags_in_ctx = ctx.get("cashtags") or []
        # Count cashtags present in full_text
        present_cashtags = [ct for ct in cashtags_in_ctx if ct in full_text]
        if len(present_cashtags) < 4:
            violations.append(
                f"theme_list post must contain ≥4 cashtags; found {len(present_cashtags)}"
            )
        # Cashtags must all be from the approved member list
        import re as _re_local
        all_cashtags_in_text = _re_local.findall(r"\$[A-Z]{1,5}", full_text)
        invalid_cashtags = [ct for ct in all_cashtags_in_text if ct not in cashtags_in_ctx]
        if invalid_cashtags:
            violations.append(
                f"theme_list cashtags not in member list: {invalid_cashtags[:3]}"
            )
        # theme_list body MUST end with a question mark (reply-bait)
        body_stripped = body.strip()
        if not body_stripped.endswith("?"):
            violations.append("theme_list body must end with a question mark (reply-bait)")

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

    # 3b. Em dash, en dash, and horizontal bar checks.
    # Em dash (U+2014) anywhere → banned.
    # En dash (U+2013) anywhere → banned (bare or spaced).
    # Horizontal bar (U+2015) anywhere → banned.
    # Hyphen-minus (U+002D / ASCII 45) stays allowed.
    if "—" in full_text:
        violations.append("em dash (U+2014)")
    if "–" in full_text:
        violations.append("en dash (U+2013)")
    if "―" in full_text:
        violations.append("horizontal bar (U+2015)")

    # 4. Banned vocabulary (word-boundary match, case-insensitive)
    for word in _BANNED_VOCAB:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, full_text, re.IGNORECASE):
            violations.append(f"banned vocab: '{word}'")

    # 4b. Banned substring phrases (case-insensitive, no word-boundary needed)
    lower_text = full_text.lower()
    for phrase in _BANNED_SUBSTRINGS:
        if phrase in lower_text:
            violations.append(f"banned vocab: '{phrase}'")

    # 4c. Banned word-boundary terms
    for word in _BANNED_WORD_BOUNDARY:
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
# Key rules for every template (see research/MARKETING_VOICE_DOCTRINE_V2_BY_FABLE.md):
# - MUST weave in {top_fact} (or explicitly use a plan number)
# - chart posts MUST include {top_fact} (a digit/% fact)
# - sound like a person on X: contractions, I/we mix, a real stance
# - ZERO em dashes; no banned vocab (vertical, regime, signal stack, etc.)
# - track-record promise on at most ~1 signal template in 4, casually phrased
# - no "Here's the score", "The chart. That's it.", "That's the [noun]." cadence
# - each (type, persona) has 4-6 structurally different variants
# ─────────────────────────────────────────────────────────────────────────────

# Template format: (headline_template, body_template)
# Available tokens: {cashtag}, {ticker}, {entry}, {t1}, {t2}, {inv},
#                   {top_fact}, {direction_word}, {gain}, {loss}, {stop},
#                   {target_label}, {win_rate}

_TEMPLATES: dict[tuple[str, str], list[tuple[str, str]]] = {

    # ── signal / authoritative desk ───────────────────────────────────────────
    # NOTE: every signal body must carry an invalidation cue (a close below / kills
    # it) AND an honesty caveat (historical / graded / publicly) so validate_copy
    # passes. Keep both, keep it human.
    ("signal", "authoritative desk"): [
        (
            "Flagged {cashtag} at {entry}",
            "{top_fact}. We're in at {entry}, first target {t1}. "
            "A close below {entry} and I'm wrong, I'm out. Historical, not a promise.",
        ),
        (
            "{cashtag} | {entry} is the line I care about",
            "We flagged {ticker} at {entry}. {top_fact}. First target {t1}. "
            "A close below {inv} kills the read. Win or lose it gets graded.",
        ),
        (
            "{cashtag} back on the board",
            "{top_fact}. I like {ticker} here at {entry}, aiming {t1}. "
            "Below {entry} I don't want it. Historical odds, not a promise.",
        ),
        (
            "Adding {cashtag} around {entry}",
            "{top_fact}. Entry {entry}, first take {t1}. "
            "Lose a close below {inv} and I'm out clean. Historically these have worked, not always.",
        ),
        (
            "{cashtag} setup I'm watching at {entry}",
            "{top_fact}. We're leaning long from {entry}, target {t1}. "
            "A close below {inv} kills it. Historically these tend to work, no guarantee.",
        ),
    ],

    # ── signal / dry, receipts-forward ───────────────────────────────────────
    ("signal", "dry, receipts-forward"): [
        (
            "{cashtag}, in at {entry}",
            "{top_fact}. Entry {entry}. T1 {t1}. Out on a close below {inv}. "
            "Historical, not a promise. Posting the result when it resolves.",
        ),
        (
            "{cashtag} | {entry} entry, {t1} target",
            "{top_fact}. Numbers: entry {entry}, T1 {t1}, out below {inv}. "
            "Historical, not a promise. Win or lose it gets graded.",
        ),
        (
            "{cashtag} flagged at {entry}",
            "{top_fact}. Entry {entry}. Target {t1}. Stop below {inv}. "
            "Clean line, clean exit. Historical odds, nothing's a guarantee.",
        ),
        (
            "Adding {cashtag} at {entry}",
            "{top_fact}. In at {entry}, first take {t1}. "
            "Below {inv} and I'm out, no argument. Historical, not certain.",
        ),
    ],

    # ── signal / specialist ───────────────────────────────────────────────────
    ("signal", "specialist"): [
        (
            "{cashtag} at {entry}, and the whole group's confirming",
            "{top_fact}. The rest of the space is moving with it, which is what I want to see. "
            "In at {entry}, first level {t1}. A close below {entry} and I'm out. Historical, not a promise.",
        ),
        (
            "{cashtag} | this is the setup I wait for here",
            "{top_fact}. Entry around {entry}, first level {t1}. "
            "A close below {inv} changes the story. Win or lose it gets graded.",
        ),
        (
            "{cashtag} in my corner of the market, {entry}",
            "{top_fact}. That's the tell I care about in these names. Entry {entry}, T1 {t1}. "
            "Below {entry} I'm gone. Historical odds, sizing matters more than being right.",
        ),
        (
            "{cashtag} at {entry} | I watch this group closely",
            "{top_fact}. This is exactly what I sit around for. Entry {entry}, target {t1}. "
            "A close below {inv} kills it. Historical odds, not certainty.",
        ),
    ],

    # ── signal / educational ──────────────────────────────────────────────────
    ("signal", "educational"): [
        (
            "A live one: {cashtag} at {entry}",
            "{top_fact}. We talk about setups in the abstract, so here's a real one. "
            "In at {entry}, target {t1}. What proves me wrong: a close below {inv}. "
            "Win or lose it gets graded so you can watch it play out.",
        ),
        (
            "{cashtag} | this is what a setup actually looks like",
            "{top_fact}. That's why {ticker} made the board. Entry {entry}, T1 {t1}. "
            "The thing that proves me wrong is a close below {inv}. "
            "Sizing is the skill, not the entry. Historical, not a guarantee.",
        ),
        (
            "Most days nothing qualifies. {cashtag} does today.",
            "{top_fact}. In at {entry}, first target {t1}. "
            "A close below {inv} and I was wrong, simple as that. Historical, not a promise.",
        ),
        (
            "{cashtag} at {entry} | watch this one with me",
            "{top_fact}. Entry {entry}, first target {t1}. Out below {inv}. "
            "This is what waiting for the setup looks like in real time. Historical, not certain.",
        ),
    ],

    # ── signal / fast, reactive ───────────────────────────────────────────────
    ("signal", "fast, reactive"): [
        (
            "{cashtag} moving. In at {entry}",
            "{top_fact}. Entry {entry}, T1 {t1}. Quick out below {entry}. "
            "On the board. Historical, not a promise.",
        ),
        (
            "{cashtag} | {entry}",
            "{top_fact}. In at {entry}, target {t1}. Close below {inv} and I'm out. "
            "Win or lose it gets graded.",
        ),
        (
            "{cashtag} | live at {entry}",
            "{top_fact}. Entry {entry}. First target {t1}. Out below {inv}. "
            "Watching it. Historical, no guarantees.",
        ),
        (
            "{cashtag} | grabbing it at {entry}",
            "{top_fact}. In at {entry}, target {t1}. Below {inv} I'm wrong. "
            "Size it small, this is historical not certain.",
        ),
    ],

    # ── signal / pattern/history ──────────────────────────────────────────────
    ("signal", "pattern/history"): [
        (
            "{cashtag} is tracing something I've seen before",
            "{top_fact}. Same shape {ticker} put in the last time it ran. "
            "In at {entry}, target {t1}. A close below {entry} and the rhyme breaks. "
            "Rhyme, not repeat. Win or lose it gets graded.",
        ),
        (
            "{cashtag} | last time this setup showed up, {entry} mattered",
            "{top_fact}. Last time {ticker} looked like this the move followed. "
            "Entry {entry}, T1 {t1}. A close below {inv} and I let it go. "
            "Historical, not a guarantee.",
        ),
        (
            "{cashtag} at {entry} | the precedent's worth a look",
            "{top_fact}. We've seen this in {ticker} before. Entry {entry}, first level {t1}. "
            "Out below {inv}. Historical, not predicting, just pointing at the rhyme.",
        ),
        (
            "{cashtag} | pattern's live at {entry}",
            "{top_fact}. In at {entry}, target {t1}. "
            "A close below {entry} and the pattern's done, so am I. Historical, not certain.",
        ),
    ],

    # ── chart / authoritative desk ────────────────────────────────────────────
    ("chart", "authoritative desk"): [
        (
            "{ticker}, one chart",
            "{cashtag}: {top_fact}. The level I'm watching is {entry}.",
        ),
        (
            "{cashtag} | {entry} is the line",
            "{top_fact}. Sitting right at {entry}. Nothing fancy, just the picture.",
        ),
        (
            "{cashtag} chart I keep coming back to",
            "{top_fact}. {entry} is where it gets interesting. No hot take beyond what you see.",
        ),
        (
            "{ticker} | worth a look",
            "{cashtag}: {top_fact}. Key level {entry}.",
        ),
        (
            "{cashtag} this week",
            "{top_fact}. Price is at {entry}. Chart says the rest.",
        ),
    ],

    # ── chart / dry, receipts-forward ─────────────────────────────────────────
    ("chart", "dry, receipts-forward"): [
        (
            "{ticker} chart",
            "{cashtag}: {top_fact}. Level {entry}.",
        ),
        (
            "{cashtag} | no spin",
            "{top_fact}. {ticker} at {entry}. That's the whole post.",
        ),
        (
            "{ticker} | where it stands",
            "{top_fact}. {cashtag} at {entry}. Draw your own line.",
        ),
        (
            "{cashtag} | the tape",
            "{top_fact}. Level {entry}. Numbers do the talking.",
        ),
    ],

    # ── chart / specialist ────────────────────────────────────────────────────
    ("chart", "specialist"): [
        (
            "{ticker} chart, and it matters for the whole group",
            "{cashtag}: {top_fact}. When this one moves the rest usually follow. Level {entry}.",
        ),
        (
            "{cashtag} | the group in one chart",
            "{top_fact}. {ticker} at {entry}. This is the name I read the space through.",
        ),
        (
            "{ticker} | this chart tells me where the theme's going",
            "{cashtag}: {top_fact}. Level I'm watching {entry}.",
        ),
        (
            "{cashtag} | sitting on my desk",
            "{top_fact}. {ticker} at {entry}. One picture beats the thread.",
        ),
    ],

    # ── chart / educational ───────────────────────────────────────────────────
    ("chart", "educational"): [
        (
            "{ticker}, let me walk you through this chart",
            "{cashtag}: {top_fact}. Notice the {entry} level and why it keeps mattering.",
        ),
        (
            "{ticker} | one thing to notice",
            "{top_fact}. That's a big part of why {cashtag} at {entry} is worth a look.",
        ),
        (
            "What {ticker}'s chart is quietly telling you",
            "{cashtag}: {top_fact}. Level {entry}. Sometimes the chart explains it better than words.",
        ),
        (
            "{cashtag} | a chart worth studying",
            "{top_fact}. {ticker} at {entry}. The chart tells the rest.",
        ),
    ],

    # ── chart / fast, reactive ────────────────────────────────────────────────
    ("chart", "fast, reactive"): [
        (
            "{ticker} chart, quick",
            "{cashtag}: {top_fact}. Level {entry}. Your call.",
        ),
        (
            "{cashtag} right now",
            "{top_fact}. {ticker} at {entry}.",
        ),
        (
            "{ticker} | fast look",
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
            "{ticker} | this chart looks familiar",
            "{cashtag}: {top_fact}. Matches something I've watched before. Level {entry}.",
        ),
        (
            "{cashtag} | history's in the picture",
            "{top_fact}. {ticker} at {entry}. The rhyme is right there if you've seen it before.",
        ),
        (
            "{ticker} chart | last time this shape showed up",
            "{top_fact}. {cashtag} at {entry}. Watch what followed the last one.",
        ),
        (
            "{cashtag} | chart with a memory",
            "{top_fact}. Level {entry}. The pattern's pointing somewhere.",
        ),
    ],

    # ── education (all voices use shared variants; persona-specific below) ────
    ("education", "authoritative desk"): [
        (
            "What flagging something actually means",
            "When we put a name on the board it means the setup lined up, not that it's a sure thing. "
            "The number that goes with it is the level that says we were wrong.",
        ),
        (
            "The stop matters more than the target",
            "A target tells you where you're hoping to go. A stop tells you when you were wrong. "
            "Knowing when you're wrong is most of the job, honestly.",
        ),
        (
            "The part most people skip",
            "You can nail the direction and still lose money. "
            "How big you go relative to your stop is the thing that actually decides the outcome.",
        ),
        (
            "How something earns a spot on the board",
            "Most setups don't make it. The ones that do all have a clear level that says "
            "the idea failed. If I can't tell you where I'm wrong, I don't post it.",
        ),
    ],
    ("education", "dry, receipts-forward"): [
        (
            "How I keep myself honest",
            "Every call gets a result posted, win or lose, same flat tone either way. "
            "No quietly forgetting the ones that didn't work.",
        ),
        (
            "Why I post the losers",
            "Losses are information. I post them the same way I post wins. "
            "The stop did its job, my ego didn't, and that's fine.",
        ),
        (
            "What a result post actually is",
            "Entry, then whether the target or the stop hit, then the number. "
            "That's it. I post it whichever way it went.",
        ),
        (
            "The whole system, plainly",
            "Call goes up. Outcome goes up. No cherry-picking, no selective memory. "
            "If it's on the page it stays on the page.",
        ),
    ],
    ("education", "specialist"): [
        (
            "The thing most people get wrong about this group",
            "Most folks read these names through the wrong lens. "
            "Here's the way I actually think about them.",
        ),
        (
            "The one thing that really moves these names",
            "It's not the headline everyone watches. One quieter driver has run this group for years. "
            "What I actually keep my eye on is a much shorter list.",
        ),
        (
            "Why the group matters more than the single name here",
            "In this space the tide really does move most of the boats together. "
            "Get the read on the group right first, then pick the name.",
        ),
        (
            "How I think about timing in these names",
            "Timing matters more in this kind of stock than people admit. "
            "Here's the short checklist I run before I flag anything.",
        ),
    ],
    ("education", "educational"): [
        (
            "Plain English: what's a 'setup'?",
            "It's a price picture that's usually been worth paying attention to. "
            "Not a buy button, just a reason to look closer. History, not a promise.",
        ),
        (
            "The 'what would prove me wrong' line is the whole thing",
            "Every real call has a line that says what would make it wrong. "
            "That line is the idea. Everything else is decoration.",
        ),
        (
            "The half of trading nobody talks about",
            "Being right on direction is only half the job. "
            "The other half is knowing exactly where you were wrong. That level is your stop.",
        ),
        (
            "What it means when I say it goes on the page",
            "Win, lose, or nothing happened, the result gets posted. "
            "Anyone can show the winners. Showing all of it is the point.",
        ),
    ],
    ("education", "fast, reactive"): [
        (
            "Quick: what's a setup?",
            "A price picture that's usually worth watching. Not a buy signal. Just a reason to look.",
        ),
        (
            "Why the stop beats the target",
            "Target is where you're hoping to go. Stop is when you were wrong. "
            "Blow the stop and the target never mattered.",
        ),
        (
            "One-minute version: how big to go",
            "Risk the same small amount every time. The stop tells you the size. That's the whole thing.",
        ),
        (
            "What invalidation means, fast",
            "The level that says you were wrong. Price hits it, you're out. No ego, no debate.",
        ),
    ],
    ("education", "pattern/history"): [
        (
            "When history rhymes, read it carefully",
            "Old analogues are useful and dangerous at once. "
            "I use them to set expectations, never to make a hard call.",
        ),
        (
            "Last time the tape looked like this",
            "I'm not calling a repeat. I'm looking at how often it worked before. "
            "Here's what happened in the closest matches.",
        ),
        (
            "The base-rate way of thinking",
            "What happened most of the time in a similar spot is context, nothing more. "
            "It's never a guarantee, and that's the honest part.",
        ),
        (
            "Using analogues without kidding yourself",
            "Rhyme, not repeat. The surrounding conditions matter more than the shape. "
            "Here's the filter I run before I lean on any comparison.",
        ),
    ],

    # ── macro (all voices) — {top_fact} carries plain observable macro/tape text ─
    ("macro", "authoritative desk"): [
        (
            "What the data's actually saying",
            "{top_fact} I'd rather own quality and stay patient than chase this here.",
        ),
        (
            "The macro read this week",
            "{top_fact} Not a comfortable mix. Leaning cautious until it clears up.",
        ),
        (
            "Where the big picture stands",
            "{top_fact} It sets the tone for everything else I'm looking at.",
        ),
        (
            "One thing worth watching up top",
            "{top_fact} How this resolves changes how much risk I want on.",
        ),
        (
            "Quick macro note",
            "{top_fact} That's the piece I care about most right now.",
        ),
        (
            "The honest macro read",
            "{top_fact} One data point, no spin.",
        ),
    ],
    ("macro", "dry, receipts-forward"): [
        (
            "Macro, plainly",
            "{top_fact} Watching the key stuff. I'll update when the picture actually shifts.",
        ),
        (
            "Where things stand up top",
            "{top_fact} Staying selective on risk until this clears.",
        ),
        (
            "Macro note",
            "{top_fact} Logged. Waiting on the next print.",
        ),
        (
            "Macro | numbers first",
            "{top_fact} That's the state of play.",
        ),
    ],
    ("macro", "specialist"): [
        (
            "Why the macro matters for these names",
            "{top_fact} That flows straight into the group I watch.",
        ),
        (
            "How the big picture's hitting my corner",
            "{top_fact} It shifts a couple of the names I follow.",
        ),
        (
            "The tailwind, or headwind, right now",
            "{top_fact} That's the current the group is swimming in.",
        ),
        (
            "The one macro driver I'm tracking",
            "{top_fact} One thing's carrying the read here, and it's this.",
        ),
    ],
    ("macro", "educational"): [
        (
            "The macro in plain words",
            "{top_fact} Watching which side blinks first.",
        ),
        (
            "Reading the big picture",
            "{top_fact} The rest is mostly noise. That part matters.",
        ),
        (
            "Macro without the jargon",
            "{top_fact} None of this tells you what to buy. It tells you the weather.",
        ),
        (
            "Why this matters for how you size up",
            "{top_fact} Here's why it should change how much risk you carry.",
        ),
    ],
    ("macro", "fast, reactive"): [
        (
            "Fast macro read",
            "{top_fact} Adjusting for it.",
        ),
        (
            "Macro, quick",
            "{top_fact} Short version above.",
        ),
        (
            "What just shifted up top",
            "{top_fact} Markets have to chew on this one.",
        ),
        (
            "Macro note, fast",
            "{top_fact} That's the one that stands out.",
        ),
    ],
    ("macro", "pattern/history"): [
        (
            "This macro setup rhymes with something",
            "{top_fact} There's a parallel worth knowing about.",
        ),
        (
            "Last time the data looked like this",
            "{top_fact} Here's roughly what followed the closest matches.",
        ),
        (
            "The rhyme, not a prediction",
            "{top_fact} Not calling a repeat. Just pointing at how it went before.",
        ),
        (
            "History's take on this setup",
            "{top_fact} This kind of read has a track record. Worth a look.",
        ),
    ],

    # ── receipt (all voices) — ONLY used when graded_receipts provides real data ──
    ("receipt", "authoritative desk"): [
        (
            "{cashtag} | {target_label} hit for {gain}",
            "That {cashtag} flag from {entry} tagged {target_label} at {t1}, {gain}. "
            "Read played out. I'm staying with the runner.",
        ),
        (
            "{cashtag} | {gain} on {target_label}",
            "Entry {entry}, {target_label} at {t1}, {gain}. "
            "Next level I care about is {t2}, or the stop takes me out.",
        ),
        (
            "{cashtag} stopped out, {loss}",
            "Entry {entry}, stopped at {stop}, {loss}. The stop did its job, my ego didn't. "
            "On to the next one, same discipline.",
        ),
        (
            "{cashtag} | partial won, runner didn't",
            "{target_label} hit at {t1} ({gain}), then stopped at {stop} ({loss}). "
            "Entry was {entry}. Took the partial, gave back the trail. That's trading.",
        ),
    ],
    ("receipt", "dry, receipts-forward"): [
        (
            "{cashtag} | {target_label}: {gain}",
            "Entry {entry}. {target_label} at {t1}, {gain}. On the page.",
        ),
        (
            "{cashtag} stopped, {loss}",
            "Entry {entry}. Out at {stop}, {loss}. Stop worked. Next.",
        ),
        (
            "{cashtag} | {gain} then {loss}",
            "Entry {entry}. {target_label} hit {t1} ({gain}). Stopped at {stop} ({loss}). "
            "Two outcomes, one trade. Both posted.",
        ),
        (
            "{cashtag} | done: {gain}",
            "Entry {entry}. {target_label} at {t1}, {gain}. Result's up.",
        ),
    ],
    ("receipt", "specialist"): [
        (
            "{cashtag} | the read on the group played, {gain}",
            "Called it off the group's move. {cashtag}: entry {entry}, {target_label} at {t1}, {gain}.",
        ),
        (
            "{cashtag} | that one didn't work, {loss}",
            "The read didn't play. Entry {entry}, stopped at {stop}, {loss}. On the page anyway.",
        ),
        (
            "{cashtag} | mixed bag",
            "{target_label} hit ({gain}), then stopped ({loss}). {cashtag} entry {entry}. "
            "Partial worked, runner didn't. Net small.",
        ),
        (
            "{cashtag} follow-up | {gain} on {target_label}",
            "Entry {entry}. {target_label} at {t1} for {gain}. The group read held up.",
        ),
    ],
    ("receipt", "educational"): [
        (
            "{cashtag} | this is what showing your work looks like",
            "I called {cashtag} at {entry}. {target_label} at {t1}, {gain}. "
            "Win, lose, or nothing, the result goes up. Anyone can post the winners.",
        ),
        (
            "{cashtag} stopped | here's a loss, posted flat",
            "Entry {entry}. Out at {stop}, {loss}. "
            "The stop did exactly what a stop is for. No drama, no story.",
        ),
        (
            "{cashtag} | a real mixed result",
            "{target_label} hit at {t1} ({gain}), then the runner stopped at {stop} ({loss}). "
            "Entry {entry}. This is what a partial actually looks like in practice.",
        ),
        (
            "{cashtag} | said I'd post it, so here it is",
            "Entry {entry}. {target_label} at {t1}, {gain}. "
            "I said win or lose it goes on the page. Here's the result.",
        ),
    ],
    ("receipt", "fast, reactive"): [
        (
            "{cashtag} | {target_label} tagged, {gain}",
            "Entry {entry}. {t1} hit. {gain}. On the page.",
        ),
        (
            "{cashtag} stopped, {loss}",
            "Entry {entry}. Out at {stop}. {loss}. Clean exit.",
        ),
        (
            "{cashtag} | {gain} then {loss}",
            "Entry {entry}. {target_label} hit ({gain}). Stop {stop} ({loss}). Two outcomes.",
        ),
        (
            "{cashtag} | done, {gain}",
            "Entry {entry}. {target_label} at {t1}, {gain}.",
        ),
    ],
    ("receipt", "pattern/history"): [
        (
            "{cashtag} | the rhyme held, {gain}",
            "Flagged the setup at {entry}. {target_label} at {t1}, {gain}. It followed through this time.",
        ),
        (
            "{cashtag} | the rhyme broke, {loss}",
            "Entry {entry}. Out at {stop}, {loss}. "
            "Didn't follow the old script this time. Posted anyway.",
        ),
        (
            "{cashtag} | a verse and a coda",
            "Entry {entry}. {target_label} hit ({gain}), runner stopped ({loss}). "
            "The rhyme got most of the way there.",
        ),
        (
            "{cashtag} | precedent held, {gain}",
            "Entry {entry}. {target_label} at {t1}, {gain}. Same shape, same result as last time.",
        ),
    ],

    # ── theme_list (all voices) — THE reach king: multi-cashtag + reply-bait ──
    # MUST contain ≥4 cashtags from {cashtag_list} and end with "?"
    # {cashtag_list} = "$NVDA $AMD $SMCI $AVGO"
    # {theme_name} = "Artificial Intelligence"
    # {theme_direction} = "down" | "up"
    # {theme_agg_pct} = "-2.1%"
    # {theme_question} = "Which one comes back first?"
    # {top_fact} = theme aggregate text
    ("theme_list", "authoritative desk"): [
        (
            "{theme_name} names all getting hit today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "Whole {theme_name} group is moving together",
            "{cashtag_list}\nEvery name here is {theme_direction} today. {top_fact} {theme_question}",
        ),
        (
            "{theme_name} down {theme_agg_pct} on average today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} rolling over, worst first",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "The whole {theme_name} group just moved",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} is {theme_direction} across the board today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],
    ("theme_list", "dry, receipts-forward"): [
        (
            "{theme_name} | {theme_agg_pct} average",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} names ranked by today's move",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | the whole list",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} tape today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],
    ("theme_list", "specialist"): [
        (
            "{theme_name} names don't all move like this on nothing",
            "{cashtag_list}\nWhen the whole group goes at once I pay attention. {top_fact} {theme_question}",
        ),
        (
            "{theme_name} | pressure across the whole group",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "Every {theme_name} name I watch is moving today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | the group's tape",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],
    ("theme_list", "educational"): [
        (
            "When a whole group moves together, notice",
            "{cashtag_list}\nA move across the whole group tells you more than any one name. {top_fact} {theme_question}",
        ),
        (
            "This is what group-wide selling looks like",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | a group move in real time",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "The {theme_name} names are all saying something today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],
    ("theme_list", "fast, reactive"): [
        (
            "{theme_name} names getting hit 👀",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "Every {theme_name} name is {theme_direction} right now",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | tape check",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | red across the board",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],
    ("theme_list", "pattern/history"): [
        (
            "Last time {theme_name} moved like this it marked something",
            "{cashtag_list}\nGroup moves this clean have shown up at turns before. {top_fact} {theme_question}",
        ),
        (
            "{theme_name} under pressure | I've seen this one",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | a rhyme worth watching",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} selling off | what happened last time",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],

    # ── mover (all voices) — biggest single mover, charted, bearish framing ok ──
    # {cashtag} = "$ISRG"  {top_fact} = "ISRG fell -14.2% today (Healthcare)."
    # {mover_pct} = "-14.2%"
    ("mover", "authoritative desk"): [
        (
            "{cashtag} {mover_pct} today. Ugly.",
            "{top_fact} This is the kind of flush where I start watching for a bottom setup. "
            "Not catching it yet, levels are on the chart.",
        ),
        (
            "{cashtag} did something worth a look today",
            "{top_fact} One of the bigger moves in the index. Watching, not chasing it here.",
        ),
        (
            "{cashtag} | {mover_pct} today",
            "{top_fact} Respecting the move, not stepping in front of it. Levels on the chart.",
        ),
        (
            "{cashtag} was the biggest move in the index today",
            "{top_fact} That's real strength (or real damage). I'd rather let it settle first.",
        ),
        (
            "{cashtag} | {mover_pct}, what happened",
            "{top_fact} Chart's below. I'm watching how it holds, not chasing the candle.",
        ),
        (
            "{cashtag} moved {mover_pct} today",
            "{top_fact} Worth knowing the same day. No urge to chase it here.",
        ),
    ],
    ("mover", "dry, receipts-forward"): [
        (
            "{cashtag} | {mover_pct} today",
            "{top_fact} Watching, not chasing.",
        ),
        (
            "{cashtag} {mover_pct}",
            "{top_fact} Numbers on the tape, chart below. Letting it settle.",
        ),
        (
            "{cashtag} | biggest mover today, {mover_pct}",
            "{top_fact} Noted. Not stepping in yet.",
        ),
        (
            "{cashtag} | {mover_pct}",
            "{top_fact} On the radar. No position.",
        ),
    ],
    ("mover", "specialist"): [
        (
            "{cashtag} {mover_pct} | the whole group should care",
            "{top_fact} Moves like this in these names are rarely random. Watching, not chasing.",
        ),
        (
            "{cashtag} | {mover_pct}, and it matters for the group",
            "{top_fact} Chart's below. I'd let it settle before doing anything.",
        ),
        (
            "{cashtag} moved {mover_pct} today",
            "{top_fact} This one ripples past the single name. Respecting it, not chasing here.",
        ),
        (
            "{cashtag} | {mover_pct}, group read",
            "{top_fact} Chart and context below. Watching how the rest of the names react.",
        ),
    ],
    ("mover", "educational"): [
        (
            "{cashtag} {mover_pct} | what a move this size looks like",
            "{top_fact} This is a real single-day move on a chart. Worth studying, not chasing.",
        ),
        (
            "{cashtag} {mover_pct} | what that tells you",
            "{top_fact} A move like this is information first, opportunity maybe. Here's how I read it.",
        ),
        (
            "How to sit with a move like {cashtag} today",
            "{top_fact} Moves this size tend to need time. I watch for the setup, I don't catch the drop.",
        ),
        (
            "{cashtag} | {mover_pct}, what to watch next",
            "{top_fact} The first day or two after a move this size tells you the most. Watching.",
        ),
    ],
    ("mover", "fast, reactive"): [
        (
            "{cashtag} {mover_pct} 👀",
            "{top_fact} Watching, not chasing. What's your read?",
        ),
        (
            "{cashtag} | {mover_pct}, fast chart",
            "{top_fact} Letting it settle before I do anything.",
        ),
        (
            "{cashtag} moving {mover_pct} today",
            "{top_fact} Chart below. Respecting it, not stepping in front.",
        ),
        (
            "{cashtag} {mover_pct}",
            "{top_fact} Tape check. No rush to touch it.",
        ),
    ],
    ("mover", "pattern/history"): [
        (
            "{cashtag} {mover_pct} | I've seen moves like this before",
            "{top_fact} These have a rough pattern. Watching for the setup, not catching the drop.",
        ),
        (
            "{cashtag} | {mover_pct}, the base rate",
            "{top_fact} Last time I saw a move this size, here's roughly what came next. Watching.",
        ),
        (
            "{cashtag} {mover_pct} today | the precedent",
            "{top_fact} Not predicting. Just pointing at how it usually goes. Not chasing here.",
        ),
        (
            "{cashtag} {mover_pct} | rhyme, not repeat",
            "{top_fact} I let these settle before I trust them. Levels on the chart.",
        ),
    ],

    # ── watchlist (all voices) ────────────────────────────────────────────────
    # ── watchlist (all voices) — {top_fact} carries breadth/sector context ──────
    ("watchlist", "authoritative desk"): [
        (
            "{cashtag} on my radar this week",
            "{top_fact} Watching {ticker}, haven't touched it. "
            "The setup isn't there yet. When it is, I'll post the entry.",
        ),
        (
            "Watching {cashtag}, not buying yet",
            "{top_fact} Interesting name, but it hasn't triggered for me. "
            "Just keeping an eye on the levels.",
        ),
        (
            "{cashtag} is sitting on my desk this week",
            "{top_fact} Close to setting up. Not acting yet, keeping the list open.",
        ),
        (
            "Keeping {cashtag} close this week",
            "{top_fact} There are gaps below that could fill. Not ready for me yet.",
        ),
        (
            "Circling {cashtag} this week",
            "{top_fact} Closest name to triggering on my list. The read is up top.",
        ),
    ],
    ("watchlist", "dry, receipts-forward"): [
        (
            "{cashtag} | watching, no position",
            "{top_fact} On the list, not in yet. I'll post when it triggers.",
        ),
        (
            "{cashtag} on the radar, not the board",
            "{top_fact} Tracking it. The setup isn't finished.",
        ),
        (
            "{cashtag} close, not triggered",
            "{top_fact} Near. Haven't acted. Entry post when it comes.",
        ),
        (
            "{cashtag} | watching only",
            "{top_fact} No entry taken. Conditions aren't met.",
        ),
    ],
    ("watchlist", "specialist"): [
        (
            "{cashtag} is the one I'm watching in my group",
            "{top_fact} Setting up but not triggered yet. Getting close.",
        ),
        (
            "Watching {cashtag}, not acting yet",
            "{top_fact} Near my entry conditions. Sitting on my hands.",
        ),
        (
            "{cashtag} near entry in my corner",
            "{top_fact} Not finished setting up, but it's close.",
        ),
        (
            "{cashtag} setup in progress",
            "{top_fact} Monitoring it. The entry isn't clean yet.",
        ),
    ],
    ("watchlist", "educational"): [
        (
            "What earns a spot on a watch list",
            "{top_fact} Not every interesting name is ready. {cashtag} is interesting and not ready.",
        ),
        (
            "How I filter what I watch",
            "{top_fact} {cashtag} stays on watch until the missing piece shows up.",
        ),
        (
            "Why I show the watch list at all",
            "{top_fact} It keeps me honest about what almost made it. {cashtag} is the one I'm close on.",
        ),
        (
            "What I'm waiting on with {cashtag}",
            "{top_fact} Interesting name. One thing still missing before it triggers.",
        ),
    ],
    ("watchlist", "fast, reactive"): [
        (
            "Watching {cashtag} right now",
            "{top_fact} On the list, not triggered. Just watching.",
        ),
        (
            "{cashtag} watching, not acting",
            "{top_fact} Close setup, no entry yet. I'll post when it goes.",
        ),
        (
            "Quick radar check on {cashtag}",
            "{top_fact} Near entry. Nothing's triggered. On watch.",
        ),
        (
            "{cashtag} close to going",
            "{top_fact} Near setup completion. Haven't touched it. Watching.",
        ),
    ],
    ("watchlist", "pattern/history"): [
        (
            "Watching a pattern in {cashtag}",
            "{top_fact} Tracing a shape worth monitoring. Not acting yet.",
        ),
        (
            "Old shapes showing up in {cashtag}",
            "{top_fact} It has analogues I've watched before. No entry yet.",
        ),
        (
            "{cashtag} rhyming with an old setup",
            "{top_fact} Tracing a pattern I've seen before. Watching for it to finish.",
        ),
        (
            "{cashtag} | a setup with a memory",
            "{top_fact} Not every one completes. This one's worth the watch.",
        ),
    ],

    # ── event (all voices) — {top_fact} carries today's catalyst read ────────
    ("event", "authoritative desk"): [
        (
            "My read on today's move",
            "{top_fact} Here's how I'm reading the price action around it.",
        ),
        (
            "What just happened, and what it changes",
            "{top_fact} My take versus the knee-jerk first-hour reaction.",
        ),
        (
            "Two reads on today's event",
            "{top_fact} There's the knee-jerk read and the one you land on after a breath. Here's mine.",
        ),
        (
            "What I'm watching after today",
            "{top_fact} It's in the books now. The next session should clear up a lot.",
        ),
        (
            "One clean read on today",
            "{top_fact} The piece I'd actually act on. Watching for the follow-through.",
        ),
    ],
    ("event", "dry, receipts-forward"): [
        (
            "Today's event, numbers first",
            "{top_fact} A few of my names care about this one. Watching them.",
        ),
        (
            "Event, logged",
            "{top_fact} Noted. Here's the impact on the board.",
        ),
        (
            "What actually shifted today",
            "{top_fact} Not much drama. A couple names will care though.",
        ),
        (
            "Reaction noted",
            "{top_fact} Watching for confirmation next session.",
        ),
    ],
    ("event", "specialist"): [
        (
            "What today's event does to my group",
            "{top_fact} This one flows straight into the names I watch.",
        ),
        (
            "How this hits my corner of the market",
            "{top_fact} My names take events differently than the broad tape. Watching which ones react.",
        ),
        (
            "Does the group's reaction make sense?",
            "{top_fact} Here's whether today's move in my names actually adds up to me.",
        ),
        (
            "My take on the group's reaction",
            "{top_fact} The names moved. Here's how I read it.",
        ),
    ],
    ("event", "educational"): [
        (
            "What today's event actually means",
            "{top_fact} Watching how markets price it in, not the noise around it.",
        ),
        (
            "Why markets moved on this one",
            "{top_fact} Markets move on surprises. Here's the read on today's.",
        ),
        (
            "How to read what just happened",
            "{top_fact} Events get oversimplified both ways. Here's the clean version.",
        ),
        (
            "Cutting through today's noise",
            "{top_fact} Lots of loud takes today. Here's the part that actually matters.",
        ),
    ],
    ("event", "fast, reactive"): [
        (
            "What just happened",
            "{top_fact} Fast take, that's the move. Watching the follow-through.",
        ),
        (
            "Quick read on today",
            "{top_fact} Knee-jerk's fast. Here's the one you keep.",
        ),
        (
            "What moved and why",
            "{top_fact} Fast read. Watching how this carries into the next session.",
        ),
        (
            "Price moved, here's the tape",
            "{top_fact} What it's actually saying is simpler than the headline.",
        ),
    ],
    ("event", "pattern/history"): [
        (
            "How events like this have played out",
            "{top_fact} We've seen this kind of day before. Watching if it rhymes.",
        ),
        (
            "This one rhymes with something",
            "{top_fact} Here's roughly how the closest matches went.",
        ),
        (
            "What happened last time we saw this",
            "{top_fact} The setup into this one has a precedent worth knowing.",
        ),
        (
            "The usual pattern after events like this",
            "{top_fact} Comparable events tend to rhyme. Not predicting, just pointing at it.",
        ),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Per-voice chart context filler (used when no OHLCV data / top_fact is empty)
# Each is structurally different so Jaccard similarity stays below 0.7 across voices.
# ─────────────────────────────────────────────────────────────────────────────

_CHART_VOICE_FILLER: dict[str, str] = {
    "authoritative desk": "Price is the most honest thing on the screen",
    "dry, receipts-forward": "Numbers tell it, no commentary needed",
    "specialist": "This group's names are at an inflection point",
    "educational": "Read the trend before you read the headlines",
    "fast, reactive": "Tape doesn't lie, and it's setting up",
    "pattern/history": "This chart shape has a history worth knowing",
}

# Filler for theme_list when top_fact is empty (theme agg context)
_THEME_VOICE_FILLER: dict[str, str] = {
    "authoritative desk": "The whole group is moving today.",
    "dry, receipts-forward": "Group-wide move, noted.",
    "specialist": "The group I watch is moving together today.",
    "educational": "When a whole group moves at once, notice.",
    "fast, reactive": "Whole group's on the tape right now.",
    "pattern/history": "This group has moved like this before.",
}

# Filler for mover when top_fact is empty
_MOVER_VOICE_FILLER: dict[str, str] = {
    "authoritative desk": "One of the bigger moves in the index today.",
    "dry, receipts-forward": "Big move, chart below. Watching.",
    "specialist": "Biggest move in my group today.",
    "educational": "A real single-day move worth studying.",
    "fast, reactive": "Biggest mover on the tape right now.",
    "pattern/history": "A move this size usually needs time.",
}

# When receipt has no graded data (gain/loss both absent), use this filler
# to keep bodies distinct across voices (pending outcome)
_RECEIPT_VOICE_PENDING: dict[str, str] = {
    "authoritative desk": "Still open. I'll post the result when it resolves.",
    "dry, receipts-forward": "Open. Result goes up on close.",
    "specialist": "Still running. Result when it's done.",
    "educational": "Every call gets a result. This one posts on the next close.",
    "fast, reactive": "Watching. Result posts when it resolves.",
    "pattern/history": "Outcome's still open. Context to follow.",
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
        item_type_for_filler = ctx.get("type", "")
        if item_type_for_filler == "theme_list":
            filler = _THEME_VOICE_FILLER.get(voice, _THEME_VOICE_FILLER["authoritative desk"])
        elif item_type_for_filler == "mover":
            filler = _MOVER_VOICE_FILLER.get(voice, _MOVER_VOICE_FILLER["authoritative desk"])
        else:
            filler = _CHART_VOICE_FILLER.get(voice, _CHART_VOICE_FILLER["authoritative desk"])
        result = result.replace("{top_fact}", filler)
    else:
        # Facts arrive without guaranteed terminal punctuation; templates
        # concatenate a following sentence, so close the fact first.
        if top_fact and top_fact[-1] not in ".!?":
            top_fact = top_fact + "."
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
        # theme_list / mover tokens
        "{cashtag_list}": ctx.get("cashtag_list", ""),
        "{theme_name}": ctx.get("theme_name", ""),
        "{theme_direction}": ctx.get("theme_direction", ""),
        "{theme_agg_pct}": ctx.get("theme_agg_pct", ""),
        "{theme_question}": ctx.get("theme_question", ""),
        "{mover_pct}": ctx.get("mover_pct", ""),
    }
    for token, value in substitutions.items():
        result = result.replace(token, value or "")
    # Clean up orphaned punctuation from empty substitutions:
    # "T1 at 95.00: ." → "T1 at 95.00."  |  "| {gain}" → ""
    result = re.sub(r'\s*:\s+\.', '.', result)
    result = re.sub(r'\s*\|\s*$', '', result)
    result = re.sub(r'\s+,', ',', result)
    result = re.sub(r'\s+\.', '.', result)
    result = re.sub(r'  +', ' ', result)
    # Collapse exactly-two-period runs: ".." → "." while preserving "..." ellipses.
    # Caused by templates that embed a literal "." after {top_fact} when the fact
    # itself already ends with a period (or the period-appender above fires first).
    result = re.sub(r'(?<!\.)\.\.(?!\.)', '.', result)
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
        try:
            from lib import config as _config  # noqa: PLC0415
            llm_models = _config.load().get("llm_models", {}) or {}
        except Exception:  # noqa: BLE001 — fall back to reading config.yml directly
            import yaml as _yaml  # noqa: PLC0415
            from pathlib import Path as _Path  # noqa: PLC0415
            _cfgp = _Path(__file__).resolve().parents[2] / "config.yml"
            llm_models = (_yaml.safe_load(_cfgp.read_text(encoding="utf-8")) or {}).get("llm_models", {}) or {}
        model_key = llm_cfg.get("model_key", "marketing_copy")
        model_id = llm_models.get(model_key, "")
        if not model_id:
            return None

        max_posts = int(llm_cfg.get("max_posts_per_run", 60))
        batch = contexts[:max_posts]

        # ── The prompt IS the product: personas + copy laws + hook grammar ────
        personas_cfg = cfg.get("personas", {}) or {}
        copy_laws = cfg.get("copy_laws", []) or []
        # Only ship the persona cards actually used in this batch.
        used_accounts = {str(c.get("account", "")) for c in batch}
        persona_cards = {
            k: {
                "name": v.get("name", k),
                "voice": str(v.get("voice_notes", "")).strip(),
                "example_lines": v.get("example_lines", [])[:2],
            }
            for k, v in personas_cfg.items() if k in used_accounts
        }

        system_prompt = (
            "You're a person who trades, posting on X. Not a research desk, not a "
            "brand, not a model. You're writing short posts for six accounts, each a "
            "distinct human with the same job but a different way of talking. Your one "
            "job: sound like a real person, not a template. If a line would sound weird "
            "said out loud to a trading buddy, rewrite it.\n\n"
            "PERSONAS (write each post as that account's human; the example_lines show "
            "the register, match their rhythm, never copy them):\n"
            + json.dumps(persona_cards, indent=1)
            + "\n\nVOICE (this is the bar; match it, don't drift formal):\n"
            "- X is casual. Contractions always. Sentence fragments are fine. Short is "
            "good, but natural-short, the way people type, not clipped telegraph style.\n"
            "- Mix 'I' and 'we'. 'I' for takes and watching ('I'm watching for a bottom "
            "setup', 'I don't love chasing this'); 'we' for the shop and the track record "
            "('we flagged it at 41.20'). All-'we' reads pretentious. Never 'our model', "
            "'the engine', 'the system'.\n"
            "- Every post carries a level, a take, or a real question. 'Here's the chart, "
            "thoughts?' gives nothing. Give a stance: watching, leaning, respecting, "
            "fading, waiting, not chasing. Down movers: 'watching for a bottom setup, not "
            "catching it yet.' Up movers: 'strength worth respecting, not chasing here.'\n"
            "- The track-record promise (post the result, win or lose it goes on the "
            "page) belongs on at most one post in four, phrased like a person. Never "
            "explain the concept of receipts or accountability. Show it, don't narrate it.\n"
            "- Macro: write only what the data plainly shows ('growth's coming in soft "
            "while inflation's still warm, not a comfortable mix'). Never a regime label "
            "or an internal score. If the facts are thin, say less.\n\n"
            "HARD BANS (a validator rejects these, obey exactly):\n"
            "- NO em dashes (—) or spaced en dashes ( – ) anywhere. Use a period, a "
            "comma, or a new sentence. Hyphens in compounds (52-week) are fine.\n"
            "- Banned words: vertical, signal stack, receipt book, accountability layer, "
            "honest model, regime, goldilocks, growth score, inflation score, de-rating, "
            "narrative, positioning in, implications for, the backdrop, '(read:'.\n"
            "- Never write an internal score, composite reading, or state label. Prices, "
            "targets, percentages, dates: yes. Engine scores: no.\n"
            "- Avoid model tells: 'Here's what it means for X', 'Let's break it down', "
            "colon-as-drama openers, the repeated 'That's the [noun].' cadence, triads "
            "everywhere, kickers like 'without the noise'.\n\n"
            "EXEMPLARS (this is the target voice):\n"
            "- Signal: \"Flagged $AMKR at 41.20. First target 46.80. If it closes back "
            "under 41 I'm wrong and I'm out. Chart below.\"\n"
            "- Down mover: \"$ISRG down 14% today. Ugly. But this is the kind of flush "
            "where I start watching for a bottom setup. Not catching it yet, levels are "
            "on the chart.\"\n"
            "- Theme list: \"Social media names all getting hit today. $SNAP -3.4% "
            "$RBLX -4.3% $MTCH -2.8% $U -4.0%. Who bounces first?\"\n"
            "- Receipt: \"That $NVDA flag from last Tuesday hit the first target, +6.2%. "
            "Next one's already on the board.\"\n"
            "- Education: \"Most days nothing qualifies. That's the whole skill, honestly. "
            "$AMD qualifies today: three of our technical signals lining up at the same "
            "level. Entry 152, out under 148.\"\n"
            "- Confluence: \"Our technical signals have resolved higher 78% of the time "
            "from this spot. $COHR is there now.\"\n\n"
            "OTHER LAWS (from config, obey exactly):\n"
            + "\n".join(f"- {law}" for law in copy_laws)
            + "\n- Use ONLY numbers from each item's numbers_whitelist, verbatim. "
            "Never invent or recompute a number.\n"
            "- Each item's cashtag(s) must appear. Body <= 275 chars. Headline <= 90 chars.\n"
            "- Signal posts must keep an invalidation line (what would prove you wrong) "
            "and an honesty caveat ('historical, not a guarantee').\n"
            "- No two headlines in the batch may share their opening words or shape.\n\n"
            "OUTPUT: a JSON array, same length and order as the input, each object "
            "exactly {\"headline\": str, \"body\": str}. No markdown, no preamble."
        )
        items_payload = [
            {
                "index": i,
                "account": ctx.get("account"),
                "type": ctx.get("type"),
                "voice": ctx.get("voice"),
                "cashtag": ctx.get("cashtag"),
                "cashtags": ctx.get("cashtags") or None,
                "facts": [f.get("text") for f in (ctx.get("top_facts") or [])[:3]],
                "entry": ctx.get("entry_str"),
                "t1": ctx.get("t1_str"),
                "inv": ctx.get("inv_str"),
                "win_rate": ctx.get("win_rate_str") or None,
                "numbers_whitelist": ctx.get("numbers_whitelist", [])[:14],
            }
            for i, ctx in enumerate(batch)
        ]

        # House LLM path: llm_auth provider waterfall (OAuth pool -> API key ->
        # deepseek), same as cortex/metabolism — NOT a bare Anthropic() client.
        from engine import llm_auth  # noqa: PLC0415
        providers = llm_auth.build_providers({}, opus_model=model_id)
        if not providers:
            return None
        max_tokens = int(llm_cfg.get("max_tokens", 6000))

        def _do_call(client, model):
            resp = client.messages.create(
                model=model, max_tokens=max_tokens, system=system_prompt,
                messages=[{"role": "user", "content":
                           "Items:\n" + json.dumps(items_payload, indent=1)}],
            )
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "stop_refusal"
            text = "".join(b.text for b in resp.content
                           if getattr(b, "type", "") == "text")
            return (text or None), None

        raw_text, _reason, _provider = llm_auth.make_call(
            providers, _do_call, context="marketing_copy")
        if not raw_text:
            return None
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
