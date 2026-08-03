"""engine.marketing.weekend_levels — popular-ticker "levels into the week" posts.

WHY THIS EXISTS
The signal lane (content_studio) sources posts from the Prophet plan pool, which
(a) ages out — most plans exceed the 21-day postable window, so on a quiet week
`postable_signals` can return almost nothing — and (b) skews to mid-caps. On a
weekend, markets are closed and there are no fresh signals or same-day movers to
post at all. That is exactly when the account most needs reach content: people
search the cashtags of the stocks THEY hold ($NVDA, $TSLA, $AAPL…) over the
weekend to see what the tape is saying, and there is far less competition on
those hashtags than on a weekday.

This module fills that gap with an evergreen, drought-proof lane: for a curated
set of the most-searched tickers it reads Friday's close (EOD OHLCV) and writes a
short, honest "here's where it sits into the week" WATCHLIST post — levels and
observations, never a buy/sell call. It needs no Prophet plan and no live tape,
so it works every weekend regardless of signal supply.

COMPLIANCE
Emitted as kind="watchlist", which the Sentinel does NOT require a disclosure on
(disclosure law is signal-only, sentinel.py §disclosure). Copy is generated from
level facts with no financial-advice lexicon and exactly one cashtag per post, so
it clears the plan-level gate. `_assert_clean` enforces this at build time.

DISPLAY-TIER, NO AUTHORITY. This never scores, ranks, or escalates anything; it
is a presentation of public price levels. The publisher's live tape gate still
re-verifies every item before it posts (and post-#3466 posts level kinds against
the last close on weekends).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")

_STOCKS_REL = "data/stocks"

# The most-searched, always-liquid tickers — the reach list. Mirrors
# config/marketing.yml radar.t1_always; the caller may override.
_DEFAULT_REACH_TICKERS: tuple[str, ...] = (
    "NVDA", "TSLA", "AAPL", "AMD", "PLTR", "MSFT", "AMZN", "META",
    "GOOGL", "AVGO", "COIN", "NFLX", "MSTR", "HOOD", "SMCI",
)

# Financial-advice phrasing we must never emit (defense-in-depth mirror of the
# sentinel lexicon; the sentinel is the real authority).
_BANNED_SUBSTRINGS: tuple[str, ...] = (
    "you should buy", "you should sell", "get in now", "get in before",
    "guaranteed", "can't lose", "cannot lose", "sure thing", "easy money",
    "risk-free", "risk free", "free money", "no-brainer", "back up the truck",
    "load up", "all-in", "to the moon", "buy now", "must buy", "table pounding",
)


# ─────────────────────────────────────────────────────────────────────────────
# Level math (pure)
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(px: float) -> str:
    """Human price: 2dp under 100, else whole dollars (keeps copy terse)."""
    return f"{px:.2f}" if px < 100 else f"{px:,.0f}"


def compute_levels(closes: list[float]) -> dict[str, Any] | None:
    """Derive weekend levels from a close series (oldest→newest).

    Returns None when there is not enough history to say anything honest
    (need at least ~50 sessions for a 50-day line).
    """
    if not closes or len(closes) < 50:
        return None
    last = float(closes[-1])
    if last <= 0:
        return None
    wk_ref = closes[-6] if len(closes) >= 6 else closes[0]
    wk_pct = (last / wk_ref - 1.0) * 100.0 if wk_ref else 0.0
    sma20 = sum(closes[-20:]) / 20.0
    sma50 = sum(closes[-50:]) / 50.0
    window = closes[-252:] if len(closes) >= 252 else closes
    hi52 = max(window)
    lo52 = min(window)
    return {
        "last": last,
        "wk_pct": wk_pct,
        "sma20": sma20,
        "sma50": sma50,
        "hi52": hi52,
        "lo52": lo52,
        "above20": last >= sma20,
        "above50": last >= sma50,
        "pct_from_hi": (last / hi52 - 1.0) * 100.0 if hi52 else 0.0,
        "pct_from_lo": (last / lo52 - 1.0) * 100.0 if lo52 else 0.0,
    }


def classify_state(lv: dict[str, Any]) -> str:
    """One-word structural state used to pick copy and a direction lean."""
    near_hi = lv["pct_from_hi"] >= -2.5
    near_lo = lv["pct_from_lo"] <= 8.0
    if lv["above20"] and lv["above50"]:
        return "leading" if near_hi else "uptrend"
    if lv["above50"] and not lv["above20"]:
        return "cooling"          # above the 50, lost the 20
    if lv["above20"] and not lv["above50"]:
        return "reclaiming"       # back over the 20, still under the 50
    return "basing" if near_lo else "downtrend"


_LEAN = {
    "leading": "BULL", "uptrend": "BULL", "reclaiming": "BULL",
    "cooling": "NEUTRAL", "basing": "NEUTRAL", "downtrend": "BEAR",
}


def cited_level(lv: dict[str, Any], state: str) -> tuple[str, float]:
    """(plain chip label, price) of the ONE level this state's copy cites.

    Single source for the body copy and the chart overlay, so the card always
    draws exactly the line the text names. The 2026-07-27 $AVGO post cited
    "the POC at 379.32" over a chart that drew no such line — text and chart
    were assembled from different sources, and the reader noticed. Every
    _FRAMES shape for a state uses the matching placeholder ({s20}/{s50}/{lo});
    tests pin that pairing.
    """
    if state == "reclaiming":
        return ("50-day avg", float(lv["sma50"]))
    if state == "basing":
        return ("52-wk low", float(lv["lo52"]))
    return ("20-day avg", float(lv["sma20"]))


# ─────────────────────────────────────────────────────────────────────────────
# Copy (honest, terse, watchlist voice — no calls)
# ─────────────────────────────────────────────────────────────────────────────
#
# VOICE (2026-07-26 incident fix). The first version of this lane was ONE
# f-string skeleton — "Closed {px}, {week}, {trend}. {position}. Into next week,
# {level}. {tail}" — so eight consecutive flagship posts were the same sentence
# with the numbers swapped, each stacking three raw technical clauses (the 20-,
# the 50-, % off highs, range position). It read exactly like what it was: a bot.
#
# Two changes:
#  1. The LLM copywriter is now the PRIMARY writer for this lane (write_copy →
#     copywriter.write_posts_llm_v2, the same per-post persona/voice lane
#     content_studio uses). This lane used to be the one queue that never
#     touched it, and until 2026-07-31 it was still on the RETIRED v1 batch
#     entry point, whose documented failure mode is a silent 100% template
#     fallback.
#  2. Everything below is now only the DETERMINISTIC FLOOR for when NOBODY ARMED
#     THE WRITER (no config flag, no MARKETING_LLM_ENABLED) — an armed lane that
#     produces no model copy DROPS the post instead, because `watchlist` is a
#     planned kind and the no-fallback law covers it. Even the floor obeys the
#     design doctrine: lead with the plain state, name at most ONE level, vary
#     the sentence shape per state so a run of posts does not share a skeleton.

def _week_clause(wk: float) -> str:
    if abs(wk) < 0.5:
        return "roughly flat on the week"
    return f"{'up' if wk > 0 else 'down'} {abs(wk):.0f}% on the week"


def _trend_clause(lv: dict[str, Any]) -> str:
    s20, s50 = _fmt(lv["sma20"]), _fmt(lv["sma50"])
    if lv["above20"] and lv["above50"]:
        return f"holding above both the 20- ({s20}) and 50-day ({s50})"
    if lv["above50"] and not lv["above20"]:
        return f"back under the 20-day ({s20}) but still over the 50-day ({s50})"
    if lv["above20"] and not lv["above50"]:
        return f"back above the 20-day ({s20}), still under the 50-day ({s50})"
    return f"under both the 20- ({s20}) and 50-day ({s50})"


def _position_clause(lv: dict[str, Any]) -> str:
    fh = lv["pct_from_hi"]
    if fh >= -2.5:
        return "sitting right up at its 52-week high"
    if fh >= -8:
        return "near the top of its 52-week range"
    if lv["pct_from_lo"] <= 8:
        return "down near the low end of its 52-week range"
    span = lv["hi52"] - lv["lo52"]
    pos = (lv["last"] - lv["lo52"]) / span if span > 0 else 0.5
    if pos < 0.34:
        return f"about {abs(fh):.0f}% off the highs, in the lower third of its range"
    if pos > 0.66:
        return f"about {abs(fh):.0f}% off the highs, still upper-half of its range"
    return f"about {abs(fh):.0f}% off the highs, mid-range for the year"


def _watch_level(lv: dict[str, Any]) -> str:
    """The single level worth naming: the line it's testing right now."""
    if lv["above20"] and lv["above50"]:
        return f"the 20-day at {_fmt(lv['sma20'])} is the first line to hold"
    if lv["above50"] and not lv["above20"]:
        return f"getting back over {_fmt(lv['sma20'])} is what flips it back constructive"
    if lv["above20"] and not lv["above50"]:
        return f"the 50-day at {_fmt(lv['sma50'])} is the level I want reclaimed"
    # Under both MAs. Near the low → the low is the line that matters; otherwise
    # the nearest overhead line (20-day) is the first hurdle back.
    if lv["pct_from_lo"] <= 8:
        return f"watching whether {_fmt(lv['lo52'])} holds or gives way"
    return f"the 20-day at {_fmt(lv['sma20'])} is the first hurdle back"


# Rotated honest tails — all say the same true thing (watching, not advising).
# No em dashes: copywriter.validate_copy rejects U+2014 as a model tell, and the
# floor must clear the same bar as the LLM lane it stands in for.
_TAILS: tuple[str, ...] = (
    "On the watch list, not a call.",
    "Watching, no position.",
    "On the radar, tracking it, not touching it.",
    "Levels, not advice.",
)

# X hard limit. A post over this is never emitted (caller skips it).
_MAX_LEN: int = 280

# Per-state sentence shapes for the deterministic floor. Each state gets its own
# opener AND its own read, so a weekend run (which spans several states) does not
# read as one template. {wk}=week clause, {s20}/{s50}/{lo}=levels, {px}=close.
# One level per post: the doctrine demotes technicals, and a post that names the
# 20-, the 50-, the high and the range position is a data dump, not a read.
# FOUR shapes per state, not two. A weekend batch is NOT evenly spread across
# states: market moves correlate, so a down week puts five of eight names in
# "downtrend" and they all draw from the same small pool. With two frames that
# produced literal twins ($AMZN and $META shipped the same sentence with
# different numbers). Four shapes plus the per-state spread in build_items means
# a run has to reach five names in ONE state before any shape repeats.
#
# No frame may open with the words a headline in the same state uses, or the two
# halves stutter ("$MSFT is still heavy" over "Still heavy, down 3%...").
_FRAMES: dict[str, tuple[str, ...]] = {
    "leading": (
        "Up at 52-week highs, {wk}. Nothing broken here, and I'd rather respect "
        "that than argue with it. {s20} is the line I want it to keep.",
        # Was "Strength worth respecting, not chasing up here" — retired as house
        # boilerplate 2026-07-30 (it was leaking onto nearly every post).
        "{wk_cap} and pressing new highs. Good for anyone already in; I'm not "
        "paying up here. First thing I'd watch on a pullback is {s20}.",
        "New highs, {wk}. This is what leadership looks like while it lasts. "
        "{s20} is where I'd start paying attention.",
        "{wk_cap}, right at the highs. No cracks I can point at. If that changes "
        "it shows up at {s20} first.",
        "Sitting at the highs, {wk}. I would rather own strength than argue with "
        "it. {s20} is the first thing I would watch.",
        "{wk_cap}. Leadership is a nice problem to have. {s20} is the level that "
        "keeps it.",
    ),
    "uptrend": (
        "{wk_cap}, still above both its moving averages. Constructive without "
        "being stretched. {s20} is the first line that matters.",
        "Holding its trend, {wk}. Not much to fix. I'm watching {s20} as the "
        "first sign that changes.",
        "{wk_cap}. It keeps doing enough and nothing more, which is fine by me. "
        "{s20} is the level I'd want held.",
        "Trend intact, {wk}. I'm not adding up here, just letting it work. "
        "{s20} is the line.",
        "It keeps climbing, {wk}. Nothing exciting, which is usually the point. "
        "{s20} is the line I care about.",
        "{wk_cap}, above both lines. I am content to sit with it. {s20} first.",
    ),
    "cooling": (
        "Slipped under its 20-day average this week, {wk}. Looks like a pause "
        "rather than a break so far. Getting back over {s20} is what settles it.",
        "{wk_cap} but it slipped under its 20-day average. Still above the "
        "50-day, so I'm giving it room. {s20} is the number to get back.",
        "It gave up its 20-day average, {wk}. Not worried yet, but I want it "
        "back quickly. {s20} is the ask.",
        "{wk_cap}, and the 20-day average went. The 50-day is still underneath, "
        "so this is a pause until it isn't. {s20} is the tell.",
        "Some air came out this week, {wk}. Still above the longer line, so I am "
        "patient. {s20} is the reclaim.",
        "{wk_cap}, and it lost the shorter line. Not a break yet. {s20} decides.",
    ),
    "reclaiming": (
        "Back above its 20-day average after a rough stretch, {wk}. Early, and "
        "I've been burned by early. {s50} is the level that would make it real.",
        "{wk_cap} and it's clawed back its 20-day average. The 50-day at {s50} "
        "is the actual test, so I'm waiting on that.",
        "It's off the mat, {wk}. One line back does not make a trend. {s50} is "
        "the one that would.",
        "{wk_cap}, back over its 20-day average. I want to see it hold more "
        "than I want to see it spike. {s50} next.",
        "It found a bid, {wk}. I have seen plenty of these fail at the next line. "
        "{s50} is that line.",
        "{wk_cap}. Better, not fixed. {s50} is what turns better into fixed.",
    ),
    "basing": (
        "Down near the low end of the year, {wk}. Watching for a bottom setup, "
        "not catching it yet. {lo} is the line that matters.",
        "{wk_cap}, sitting near its 52-week low. No interest until it stops going "
        "down. {lo} is where I find out.",
        "Still near the lows, {wk}. Cheap is not a reason on its own. {lo} "
        "holding would be.",
        "{wk_cap}. It has been falling long enough that people stopped asking "
        "about it. {lo} is the level I care about.",
        "It has been left for dead, {wk}. That is usually where they stop going "
        "down, eventually. {lo} is the marker.",
        "{wk_cap}, down at the lows. I want evidence, not a discount. {lo} is it.",
    ),
    "downtrend": (
        "{wk_cap}, under both moving averages. No reason to be early in something "
        "going the wrong way. {s20} is the first hurdle back.",
        "Another week lower, {wk}. I'm not trying to be the hero here. {s20} is "
        "what it has to take back.",
        "{wk_cap}. Sellers still have the ball, and I'd rather let someone else "
        "find the bottom. Watching {s20}.",
        "It keeps giving back ground, {wk}. Nothing here says the selling is "
        "done. {s20} would be the first thing that did.",
        "It is still going out with the tide, {wk}. No urgency to be involved. "
        "{s20} is the first sign of one.",
        "{wk_cap}, and every bounce has been sold. {s20} is where that changes.",
    ),
}


# Per-state HEADLINES. The first version of this lane hard-coded
# f"${ticker} into the week" for every post, so a reader scrolling the profile
# saw the identical headline eight times down the page:
#     $NVDA into the week / $AAPL into the week / $AMZN into the week ...
# Nothing marks copy as machine-written faster than a repeated frame, and the
# headline is the part that repeats VISIBLY — you see eight of them at once in a
# feed, while the bodies are read one at a time (operator, 2026-07-26).
#
# The headline now carries the READ, not a frame, and differs by state. Every
# shape holds the cashtag exactly once (_assert_clean enforces that), none use an
# em dash, and none state a level — levels live in the body so the headline stays
# short enough to survive a mobile timeline.
_HEADLINES: dict[str, tuple[str, ...]] = {
    "leading": (
        "$T keeps making highs",
        "Still nothing broken in $T",
        "$T is doing the boring thing well",
        "$T is at the highs and holding",
        "$T is not the problem right now",
        "Hard to argue with $T here",
    ),
    "uptrend": (
        "$T is quietly working",
        "No complaints about $T here",
        "$T still has its trend",
        "$T is behaving itself",
        "$T is grinding higher",
        "Nothing wrong with $T",
    ),
    "cooling": (
        "$T lost its 20-day line",
        "First real wobble in $T",
        "$T is cooling off",
        "A little air out of $T",
        "$T took a breather",
        "Some heat out of $T",
    ),
    "reclaiming": (
        "$T is trying to turn",
        "Signs of life in $T",
        "$T got its 20-day line back",
        "$T is picking itself up",
        "$T is finding its feet",
        "$T looks less broken than it did",
    ),
    "basing": (
        "$T is scraping the lows",
        "No floor yet in $T",
        "$T has not stopped going down",
        "Nobody wants $T right now",
        "$T is still for sale",
        "Nothing has changed in $T yet",
    ),
    "downtrend": (
        "$T keeps leaking",
        "$T is not finding buyers",
        "Nothing good happening in $T yet",
        "$T is still going the wrong way",
        "$T is grinding lower",
        "Still no bottom in $T",
    ),
}


def _headline(ticker: str, state: str, variant: int) -> str:
    """Short, state-specific headline carrying the read. Falls back to the
    original frame only for an unknown state (never in practice: _HEADLINES
    covers every classify_state output)."""
    pool = _HEADLINES.get(state) or ()
    if not pool:
        return f"${ticker} into the week"
    return pool[variant % len(pool)].replace("$T", f"${ticker}")


def render_post(ticker: str, lv: dict[str, Any], *, variant: int = 0,
                state_variant: int | None = None) -> tuple[str, str]:
    """(headline, body) for one ticker — the DETERMINISTIC FLOOR.

    Used when the LLM copywriter is unavailable (see write_copy). Deterministic
    given (ticker, lv, variant, state_variant). The cashtag appears once
    (headline); the body carries the substance so the post never reads like a
    cashtag-stuffed bot.

    BOTH halves vary by the ticker's structural state, so a weekend run differs
    in its headline, its sentence shape and its numbers rather than only the
    last. Falls back to the legacy single-frame body only if the state-specific
    frame would breach the X limit.

    variant:       position in the batch. Rotates the tail, so the sign-off
                   varies down the feed regardless of state.
    state_variant: how many EARLIER posts in this batch share this state.
                   Selects the headline and body shape, so five downtrend names
                   in one run take five different shapes instead of colliding on
                   `variant % len(pool)`. Defaults to `variant` for callers that
                   render a single post.
    """
    tail = _TAILS[variant % len(_TAILS)]
    state = classify_state(lv)
    sv = variant if state_variant is None else state_variant
    headline = _headline(ticker, state, sv)

    wk = _week_clause(lv["wk_pct"])
    fields = {
        "wk": wk,
        "wk_cap": wk[0].upper() + wk[1:] if wk else wk,
        "px": _fmt(lv["last"]),
        "s20": _fmt(lv["sma20"]),
        "s50": _fmt(lv["sma50"]),
        "lo": _fmt(lv["lo52"]),
    }
    frames = _FRAMES.get(state) or ()
    if frames:
        frame = frames[sv % len(frames)]
        body = f"{frame.format(**fields)} {tail}"
        if len(headline) + 2 + len(body) <= _MAX_LEN:
            return headline, body

    # Legacy floor-of-the-floor: always fits, always compliant.
    def _body(with_position: bool) -> str:
        pos = f" {_position_clause(lv).capitalize()}." if with_position else ""
        return (
            f"Closed {_fmt(lv['last'])}, {_week_clause(lv['wk_pct'])}, "
            f"{_trend_clause(lv)}.{pos} Into next week, {_watch_level(lv)}. {tail}"
        )

    body = _body(True)
    if len(headline) + 2 + len(body) > _MAX_LEN:
        body = _body(False)
    return headline, body


# ─────────────────────────────────────────────────────────────────────────────
# LLM voice lane (primary) — the same copywriter every other queue goes through
# ─────────────────────────────────────────────────────────────────────────────

def lane_armed(cfg: dict | None) -> bool:
    """Is the LLM writer lane switched on for this run?

    A MUTE LANE IS NOT A DROP (mirrors content_studio's phase-3 check). When the
    config flag is off or MARKETING_LLM_ENABLED is unset, nobody asked for model
    copy — tests and local runs are in that state constantly — and the honest
    output is this lane's own deterministic floor, not an empty weekend. When the
    lane IS armed, a post the writer will not write is a post we do not have.
    """
    llm = ((cfg or {}).get("copywriter") or {}).get("llm") or {}
    if not bool(llm.get("enabled", False)):
        return False
    return os.environ.get("MARKETING_LLM_ENABLED", "").strip().lower() in (
        "1", "true", "yes")


def write_copy(
    specs: list[dict[str, Any]],
    cfg: dict | None,
    *,
    account: str = "flagship",
    root: Path | str | None = None,
) -> list[tuple[str, str] | None]:
    """Write each spec in the account's real voice. Fail-soft, NEVER templated.

    specs: [{"ticker", "lv", "dates", "o","h","l","c","v", "headline", "body"}]
           — "headline"/"body" are the deterministic floor from render_post().

    Returns one entry per spec, in order: a (headline, body) pair, or None
    meaning THIS POST IS DROPPED. The caller must skip a None; it may not
    substitute anything for it.

    MIGRATED OFF THE v1 BATCH WRITER (X Growth W1g, 2026-07-31). This lane called
    `copywriter.write_posts_llm`, the retired batch path whose documented failure
    mode is a SILENT 100% template fallback: it asks one model call for the whole
    batch as a single JSON array, and when that reply truncates or fails to parse
    the function returns None and every post silently reverts to template prose
    (copywriter.py, `write_posts_llm`). That is the exact incident the
    Content Studio wave was built to end — a persona lane armed, credentialed,
    and producing not one live post. `write_posts_llm_v2` calls per post, so one
    bad reply costs one post, and it DROPS rather than templating.

    WHY DROP AND NOT FALL BACK TO THE FLOOR. `watchlist` is a planned kind and
    the no-fallback law (masterplan §0 gate 1) covers it: a planned post whose
    model copy fails is dropped and counted. The floor copy is good prose, but it
    is still template prose, and the whole point of the wave is that the reader
    stops meeting it. The floor keeps exactly one job — being what ships when
    nobody armed the writer at all (`lane_armed` above) — plus its old job of
    seeding the writer's context.

    WEEKEND SEMANTICS SURVIVE THE MOVE. Contexts are still built from level facts
    with `type="watchlist"`, so the post stays an evergreen levels read with no
    "today" claim, and `_assert_clean` still runs on whatever the model returns.

    The PROVIDER WATERFALL is the copywriter's, and deliberately so: the whole
    `copywriter` block (its `llm` sub-block included) is handed to the writer, so
    weekend levels inherits the marketing-copywriter lane's ChatGPT-first routing
    (codex/Sol leading, the key_pool-balanced Claude oauth rung behind it —
    operator directive 2026-07-29) with no second copy of those keys to drift.
    """
    floor: list[tuple[str, str] | None] = [
        (str(s.get("headline") or ""), str(s.get("body") or "")) for s in specs
    ]
    if not specs:
        return floor
    if not lane_armed(cfg):
        log.info("weekend_levels: LLM writer not armed — shipping the floor copy")
        return floor

    try:
        from engine.marketing.copywriter import build_context, write_posts_llm_v2  # noqa: PLC0415
        from engine.marketing import chart_facts as _cf  # noqa: PLC0415

        cw_cfg = ((cfg or {}).get("copywriter") or {})
        personas = (cw_cfg.get("personas") or {})
        persona = personas.get(account) or {}

        contexts: list[dict] = []
        for s in specs:
            ticker = str(s.get("ticker") or "")
            facts: dict = {}
            try:
                if s.get("c"):
                    facts = _cf.compute_facts(
                        ticker, s.get("dates") or [], s.get("o") or [],
                        s.get("h") or [], s.get("l") or [], s.get("c") or [],
                        s.get("v") or [])
            except Exception as exc:  # noqa: BLE001 — facts are a bonus, not a gate
                log.warning("weekend_levels: chart facts failed for %s: %s", ticker, exc)
            lv = s.get("lv") or {}
            item = {
                "ticker": ticker,
                "type": "watchlist",
                "account": account,
                "direction": _LEAN.get(classify_state(lv), "NEUTRAL") if lv else "NEUTRAL",
                "headline": s.get("headline", ""),
                "body": s.get("body", ""),
            }
            ctx = build_context(item, persona=persona, facts=facts or None)
            ctx["type"] = "watchlist"
            ctx["voice"] = persona.get("voice_notes", "") or ctx.get("voice", "")
            # `two_part` is the only shape that carries a headline, and this
            # lane's post IS a headline plus a body — asking for any other shape
            # would guarantee an empty headline and a drop on every item.
            ctx["shape"] = "two_part"
            # The writer's per-account frequency caps key off the post's date;
            # the spec carries the CONTENT day (the weekend being written for).
            if s.get("as_of"):
                ctx["as_of"] = str(s.get("as_of"))
            contexts.append(ctx)

        posts = write_posts_llm_v2(contexts, cw_cfg, root=root)
        if not posts or len(posts) != len(specs):
            # A writer that answers with the wrong SHAPE is a writer we cannot
            # read: drop the batch rather than guess which post is which. This
            # is not the mute case (checked above) — the lane is armed.
            log.warning("weekend_levels: writer returned %d result(s) for %d "
                        "spec(s) — dropping the batch",
                        len(posts or []), len(specs))
            return [None] * len(specs)

        out: list[tuple[str, str] | None] = []
        for i, post in enumerate(posts):
            ticker = str(specs[i].get("ticker") or "")
            # v2 modes: "llm" | "llm_repair" survive; "dropped" is a post we do
            # not have. There is no template mode to fall back to any more, and
            # that absence is the point.
            mode = str((post or {}).get("mode") or "")
            if not mode.startswith("llm"):
                log.info("weekend_levels: %s dropped by the writer (%s: %s)",
                         ticker, (post or {}).get("stage"), (post or {}).get("reasons"))
                out.append(None)
                continue
            hl = str(post.get("headline") or "").strip()
            bd = str(post.get("body") or "").strip()
            if not hl or not bd:
                log.info("weekend_levels: %s dropped — writer returned no "
                         "headline/body", ticker)
                out.append(None)
                continue
            try:
                _assert_clean(f"{hl}\n\n{bd}", ticker)
            except ValueError as exc:
                log.warning("weekend_levels: %s dropped — copy rejected (%s)",
                            ticker, exc)
                out.append(None)
                continue
            out.append((hl, bd))
        return out
    except Exception as exc:  # noqa: BLE001
        # The lane is ARMED and the writer path broke (import, provider
        # construction, a raise out of a helper). Dropping is the law's answer;
        # the floor is only for a lane nobody armed.
        log.warning("weekend_levels: writer lane unavailable (%s) — posts dropped", exc)
        return [None] * len(specs)


# ─────────────────────────────────────────────────────────────────────────────
# Chart card — every post ships the SAME card the Content Studio preview shows
# ─────────────────────────────────────────────────────────────────────────────

def build_card(
    ticker: str,
    root: Path | str | None,
    *,
    chart_id: str,
    as_of: str,
    n: int = 90,
    level_overlay: dict[str, Any] | None = None,
    cta: bool = True,
) -> dict[str, Any] | None:
    """Render the v2 candlestick card for *ticker* and publish it. Fail-soft.

    Returns an outbox media entry ({kind, path, chart_id, ticker, media_url,
    media_png_path}) or None when the chart cannot be built. Goes through
    media_publish.publish_card, so the PNG X receives is a raster of this exact
    SVG — footer marketing bar (mastermind-x.com + "Try Pro free for 7 days")
    included. Before 2026-07-26 this lane attached NO media at all: every post
    went out as bare text.
    """
    try:
        from engine.marketing.chart_render import load_ohlcv_windowed, render_chart_v2  # noqa: PLC0415
        from engine.marketing.media_publish import publish_card  # noqa: PLC0415

        r = Path(root) if root is not None else Path(".")
        # Windowed load: warm-up lead-in so SMA50/MACD span the whole visible window
        # (paneless volume + tall MACD; see load_ohlcv_windowed).
        _windowed = load_ohlcv_windowed(ticker, r, vis=n)
        ohlcv, _warmup = _windowed if _windowed else (None, 0)
        if ohlcv is None:
            return None
        dates, o, h, l, c, v = ohlcv
        if not c:
            return None
        svg = render_chart_v2(
            ticker=ticker, dates=dates, o=o, h=h, l=l, c=c, volume=v,
            timeframe="DAILY",
            # Weekend levels is a watchlist read, not a fired signal: no SETUP
            # pill, no entry marker, and no "since setup" return chip — the card
            # must never imply a call the copy explicitly does not make.
            marker_index=None, highlight_index=None,
            pct_from_index=None,
            show_indicators=True,
            indicators=("volume", "macd"),
            warmup=_warmup,
            volume_overlay=True,   # volume embedded in the price pane
            subpanel_h=190,        # tall, legible MACD pane
            height=880,
            logo_root=r,
            # The one level the copy cites, drawn as a labeled dashed line —
            # the text may only name a level the chart shows (cited_level).
            level_overlay=level_overlay,
            # footer_cta unset → the full marketing bar (URL, tagline, and — when
            # publish.chart_cta_enabled is on — the trial button).
            cta=cta,
        )
        if not svg:
            return None
        stamped = publish_card(svg, chart_id=chart_id, as_of=str(as_of), root=r)
        if not stamped.get("svg_path"):
            return None
        entry: dict[str, Any] = {
            "kind": "chart_svg",
            "path": stamped["svg_path"],
            "chart_id": chart_id,
            "ticker": ticker,
        }
        if stamped.get("media_png_path"):
            entry["media_png_path"] = stamped["media_png_path"]
        if stamped.get("media_url"):
            entry["media_url"] = stamped["media_url"]
        if stamped.get("media_render"):
            entry["media_render"] = stamped["media_render"]
        return entry
    except Exception as exc:  # noqa: BLE001
        log.warning("weekend_levels: card build failed for %s: %s", ticker, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Scheduling (weekend gating + ladder slot assignment)
# ─────────────────────────────────────────────────────────────────────────────

_LADDER = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")


def should_run(as_of: str) -> bool:
    """True when *as_of* (the content's target day) is a weekend (Sat/Sun).

    This lane exists to fill the low-signal, market-closed window; on trading
    days the normal signal lane carries the queue. Gated on the target DATE, not
    wall-clock — the nightly runs in the small hours UTC, so the run's local
    weekday is unreliable; the as_of it is generating for is what matters."""
    try:
        d = datetime.strptime(str(as_of)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    return d.weekday() >= 5  # Saturday=5, Sunday=6


def weekend_schedule(as_of: str, n: int) -> list[tuple[str, str]]:
    """Assign up to *n* items to the D1 (=as_of) ladder slots, each resolved to
    its advisory scheduled_at (UTC via outbox.slot_datetime). The publisher's
    10-min floor paces whatever is already due; future slots post at their time."""
    from engine.marketing.outbox import slot_datetime  # noqa: PLC0415
    out: list[tuple[str, str]] = []
    for i in range(min(n, len(_LADDER))):
        slot = f"D1-{_LADDER[i]}"
        out.append((slot, slot_datetime(as_of, slot) or "immediate"))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Data loading + item construction
# ─────────────────────────────────────────────────────────────────────────────

def load_closes(root: Path | str | None, ticker: str) -> list[float] | None:
    """Read the EOD close series for *ticker* from data/stocks/<T>.parquet.

    Fail-soft: returns None on any missing file / unreadable frame / missing
    column so a single bad ticker never breaks the batch.
    """
    r = Path(root) if root is not None else Path(".")
    path = r / _STOCKS_REL / f"{ticker}.parquet"
    try:
        if not path.exists():
            return None
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path, columns=["close"])
        if "close" not in df.columns or df.empty:
            return None
        return [float(x) for x in df["close"].tolist() if x == x]  # drop NaN
    except Exception as exc:  # noqa: BLE001
        log.warning("weekend_levels: unreadable closes for %s: %s", ticker, exc)
        return None


def _assert_clean(text: str, ticker: str) -> None:
    """Guard: no advice lexicon, no em dash, exactly one cashtag. Raises on
    violation so a non-compliant post can never be emitted (caller skips it)."""
    if len(text) > _MAX_LEN:
        raise ValueError(f"{ticker} copy is {len(text)} chars (max {_MAX_LEN})")
    low = text.lower()
    for bad in _BANNED_SUBSTRINGS:
        if bad in low:
            raise ValueError(f"banned phrase {bad!r} in {ticker} copy")
    # Mirrors copywriter.validate_copy: the em dash is the loudest model tell.
    if "—" in text:
        raise ValueError(f"em dash (U+2014) in {ticker} copy")
    distinct = set(_CASHTAG_RE.findall(text))
    if distinct != {ticker.upper()}:
        raise ValueError(f"{ticker} copy cashtags {distinct or '∅'}, want exactly {{{ticker.upper()}}}")


def _chart_cta_enabled(cfg: dict | None) -> bool:
    """publish.chart_cta_enabled, via chart_render's resolver. Lazy import keeps
    this module importable on a host with no pandas (chart_render pulls it in)."""
    try:
        from engine.marketing.chart_render import chart_cta_enabled  # noqa: PLC0415
        return chart_cta_enabled(cfg)
    except Exception:  # noqa: BLE001 — a missing renderer must not break item build
        return True


def already_built(
    root: Path | str | None,
    *,
    as_of: str,
    account: str = "flagship",
    provenance: str = "weekend_levels",
) -> int:
    """How many items this lane has EVER built for (account, as_of) — any status.

    The idempotence read. Fail-soft: an unreadable queue answers 0, because a
    lane that cannot see the outbox must still be able to fill an empty day.

    STATUS-BLIND ON PURPOSE (defect closed 2026-07-31; the incident it replays is
    2026-07-26). This used to call `rewrite.live_items_for`, which filters out
    every TERMINAL status — and `posted` is terminal. So the guard could only see
    a batch that had not shipped yet: the 03:13 batch of eight queued, POSTED
    through the morning, and by the 09:52 rerun every one of its rows was
    invisible to this check. The lane read "nothing built for 2026-07-26",
    rebuilt the whole day, and produced a second contradictory post per slot —
    eight more Chrome rasters and eight more R2 uploads against a render budget
    that is law. An idempotence guard that goes blind the moment its work
    SUCCEEDS is the exact inverse of the guarantee it advertises: the better the
    lane performs, the sooner it duplicates itself.

    "Built" therefore means ANY row for this (account, as_of, provenance) triple
    in items.jsonl, whatever the ledger later did to it — posted, quarantined,
    failed, recalled, superseded. The row is the receipt that the work was done.

    WHAT THIS COSTS, stated plainly: quarantining a bad batch no longer re-arms
    the lane for the same day (the old docstring named that as the recovery path
    and it is now gone). That is the correct trade — a duplicate slate on a live
    timeline is a public contradiction, while a day with a quarantined batch and
    no replacement is merely a quiet day. Re-running a day on purpose is an
    operator action: supersede the rows through `engine.marketing.rewrite`
    (which passes `skip_if_queued=False` precisely because it OWNS regeneration),
    or build under a different `as_of`.
    """
    try:
        from engine.marketing.outbox import fold_state  # noqa: PLC0415
        state = fold_state(root)
        return sum(
            1 for it in (state.get("items") or {}).values()
            if str(it.get("account") or "") == account
            and str(it.get("as_of") or "") == as_of
            and str(it.get("provenance") or "") == provenance
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("weekend_levels: queue unreadable for idempotence check: %s", exc)
        return 0


def build_items(
    root: Path | str | None,
    *,
    tickers: list[str] | None = None,
    as_of: str,
    account: str = "flagship",
    provenance: str = "weekend_levels",
    now: datetime | None = None,
    schedule: list[tuple[str, str]] | None = None,
    max_items: int = 8,
    cfg: dict | None = None,
    with_media: bool = True,
    skip_if_queued: bool = True,
) -> list[dict[str, Any]]:
    """Build outbox item dicts (via outbox.make_item) for the reach tickers.

    schedule: optional list of (slot_label, scheduled_at_iso) assigned in order;
    when omitted, items are scheduled "immediate" with no slot (caller schedules).
    cfg: parsed config/marketing.yml — enables the LLM voice lane (write_copy).
         Without it the deterministic floor copy ships.
    with_media: render + attach the v2 chart card per post (default on). Set
         False in tests to skip chart rendering entirely.
    skip_if_queued: return [] when this lane already has a live item for
         (account, as_of). The REWRITE path passes False — it exists precisely
         to regenerate copy for items that are already queued, and supersedes
         them one for one (engine.marketing.rewrite.apply_rewrite).

    Returns at most *max_items* items, one per ticker that has usable data and
    compliant copy. Never raises — a bad ticker is skipped with a warning.

    IDEMPOTENT BY DEFAULT (2026-07-26 double slate). This lane ran twice for
    as_of=2026-07-26 — a 03:13 batch and a 09:52 batch — and produced EIGHT
    items each time: a second, contradictory post for every slot, which the
    operator deleted by hand. The downstream `supersede_lane` retirement added
    later still lets the second run render eight fresh chart cards and write
    eight rows before retiring the first eight, so a re-run costs eight Chrome
    rasters and eight R2 uploads against a render budget that is law. Detecting
    the day up front is cheaper and is what "never duplicate" actually means.
    A PARTIAL first run is deliberately treated as built: this returns [] when
    ANY item exists for the day. Refilling the rest of a ladder needs slot
    occupancy this function does not have, and the day-cap is the real limiter
    anyway.

    "ANY item" is STATUS-BLIND — including a batch that already posted. See
    `already_built` for why the old live-items-only read let a shipped 03:13
    batch look like an empty day at 09:52, and for the recovery path that
    replaces "quarantine it to re-arm the lane".
    """
    from engine.marketing.outbox import make_item  # noqa: PLC0415

    if skip_if_queued:
        _existing = already_built(root, as_of=as_of, account=account,
                                  provenance=provenance)
        if _existing:
            log.info("weekend_levels: %s already built %d item(s) for %s "
                     "(any status) — skipping (idempotent re-run)",
                     account, _existing, as_of)
            return []

    ts_now = now if now is not None else datetime.now(timezone.utc)
    picks = [t.upper() for t in (tickers or _DEFAULT_REACH_TICKERS)]

    # ── Pass 1: level math + floor copy + OHLCV for the writer's facts ────────
    # state_seen spreads same-state names across the shape pools: a down week can
    # put most of the batch in one state, and without this they all resolve to
    # the same `variant % len(pool)` and ship as near-twins.
    specs: list[dict[str, Any]] = []
    state_seen: dict[str, int] = {}
    for idx, ticker in enumerate(picks):
        if len(specs) >= max_items:
            break
        closes = load_closes(root, ticker)
        lv = compute_levels(closes) if closes else None
        if lv is None:
            log.info("weekend_levels: skip %s (insufficient data)", ticker)
            continue
        _state = classify_state(lv)
        _sv = state_seen.get(_state, 0)
        state_seen[_state] = _sv + 1
        headline, body = render_post(ticker, lv, variant=idx, state_variant=_sv)
        try:
            _assert_clean(f"{headline}\n\n{body}", ticker)
        except ValueError as exc:
            log.warning("weekend_levels: %s", exc)
            continue
        spec: dict[str, Any] = {
            "ticker": ticker, "lv": lv, "headline": headline, "body": body,
            "variant": idx,
        }
        # OHLCV feeds chart_facts (what the writer is allowed to cite). Optional:
        # a ticker with closes but no OHLCV still posts, just with thinner facts.
        try:
            from engine.marketing.chart_render import load_ohlcv  # noqa: PLC0415
            ohlcv = load_ohlcv(ticker, Path(root) if root is not None else Path("."), n=90)
            if ohlcv is not None:
                d, o, h, l, c, v = ohlcv
                spec.update({"dates": d, "o": o, "h": h, "l": l, "c": c, "v": v})
        except Exception as exc:  # noqa: BLE001
            log.warning("weekend_levels: OHLCV unavailable for %s: %s", ticker, exc)
        specs.append(spec)

    if not specs:
        return []

    # ── Pass 2: real voice. A None here is a DROPPED post, never a template ──
    # (see write_copy: the v2 writer drops, it does not fall back).
    copy = write_copy(specs, cfg, account=account, root=root)
    _dropped = sum(1 for c in copy if c is None)
    if _dropped:
        log.warning("weekend_levels: writer dropped %d/%d post(s) — those slots "
                    "ship nothing", _dropped, len(specs))

    # ── Pass 2b: quality review (advisory, never a gate) ─────────────────────
    # The mechanical half costs nothing and catches the failure this lane
    # actually shipped: eight posts sharing one skeleton. Findings ride on the
    # item so the Outbox can show the operator WHICH posts collide; nothing is
    # dropped or rewritten here. Reviews are keyed by TICKER, not by position,
    # because a dropped post leaves no copy to review and the two lists would
    # otherwise slide out of alignment.
    review_by_ticker: dict[str, dict] = {}
    try:
        from engine.marketing.copy_review import review_batch  # noqa: PLC0415
        _reviewable = [(s, c) for s, c in zip(specs, copy) if c is not None]
        _rev = review_batch(
            [{"id": s["ticker"], "headline": c[0], "body": c[1]}
             for s, c in _reviewable],
            cfg, root=root,
        )
        for _s_c, _rp in zip(_reviewable, (_rev.get("posts") or [])):
            review_by_ticker[str(_s_c[0].get("ticker") or "")] = _rp or {}
        for _f in (_rev.get("batch") or []):
            log.warning("weekend_levels: copy review [%s] %s",
                        _f.get("severity"), _f.get("detail"))
    except Exception as exc:  # noqa: BLE001
        log.warning("weekend_levels: copy review unavailable: %s", exc)

    # ── Pass 3: assemble items, each with its chart card ─────────────────────
    out: list[dict[str, Any]] = []
    for i, spec in enumerate(specs):
        ticker = str(spec["ticker"])
        lv = spec["lv"]
        written = copy[i] if i < len(copy) else None
        if written is None:
            # The writer dropped this post. NOTHING is substituted — not the
            # floor, not a template. Skipping BEFORE build_card also means a
            # dropped post never spends a Chrome raster or an R2 upload.
            continue
        headline, body = written
        text = f"{headline}\n\n{body}"
        try:
            _assert_clean(text, ticker)
        except ValueError as exc:  # belt-and-braces; write_copy already checked
            log.warning("weekend_levels: %s", exc)
            continue

        media: list[dict] = []
        if with_media:
            _lvl_label, _lvl_price = cited_level(lv, classify_state(lv))
            entry = build_card(
                ticker, root,
                chart_id=f"wl-{as_of}-{ticker.lower()}", as_of=as_of,
                level_overlay={"price": _lvl_price, "label": _lvl_label},
                cta=_chart_cta_enabled(cfg),
            )
            if entry is not None:
                media.append(entry)
            else:
                log.warning("weekend_levels: no chart card for %s — post would be "
                            "text-only", ticker)

        slot_label: str | None = None
        scheduled_at = "immediate"
        if schedule and len(out) < len(schedule):
            slot_label, scheduled_at = schedule[len(out)]

        source = {
            "ticker": ticker,
            "direction": _LEAN.get(classify_state(lv), "NEUTRAL"),
            "state": classify_state(lv),
            "last_close": round(lv["last"], 2),
            "wk_pct": round(lv["wk_pct"], 1),
            "lane": "weekend_levels",
        }
        # The publisher reads source.media_url to attach without unpacking the
        # media list (scripts/marketing_publisher._media_urls), so mirror it.
        if media and media[0].get("media_url"):
            source["media_url"] = media[0]["media_url"]

        # Advisory review finding, surfaced next to the post in the Outbox.
        # Only attached when there IS something to say — a clean post carries
        # no marker, so a reviewed queue does not look uniformly suspicious.
        _r = review_by_ticker.get(ticker) or {}
        if _r.get("issues") or str(_r.get("verdict") or "ok") != "ok":
            source["review"] = {"verdict": _r.get("verdict") or "ok",
                                "issues": _r.get("issues") or []}

        try:
            item = make_item(
                account=account, kind="watchlist", text=text, as_of=as_of,
                media=media or None,
                scheduled_at=scheduled_at, slot=slot_label, priority=5,
                provenance=provenance, source=source, now=ts_now,
            )
        except ValueError as exc:
            log.warning("weekend_levels: make_item failed for %s: %s", ticker, exc)
            continue
        out.append(item)

    return out
