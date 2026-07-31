"""engine.marketing.hot_tape_wire — Wire copy for Hot Tape events.

Implements research/MARKETING_HOT_TAPE_MASTERPLAN.md §2.D (the device library)
and §3.3 (wire copy layer), under gates 0.2, 0.3 and 0.4:

* **0.2 differentiating stat** — every post carries at least one §2.D device: a
  "since <date>", a streak count, a dollar translation, or a record/rank. The
  bank is (template, required device slots); a variant renders only when every
  slot it needs is derivable from the FactPacket, and a family whose device law
  cannot be met REFUSES (``compose_wire`` returns None). A bare "%-move" post
  is the corpus's 95-view flop and is structurally impossible here.
* **0.3 facts are engine-computed** — :func:`check_text_numbers` re-reads the
  RENDERED text and rejects any numeric token that is not a leaf of
  ``packet.facts`` rendered through the shared formatters. compose_wire runs
  this itself, so the gate holds at runtime and not only in tests.
* **0.4 observations, not calls** — :data:`WIRE_BANNED` word-boundary scan over
  both the static bank and every rendered variant. Directive call language on
  an un-gauntleted read is the Mag-7 killed class (research/DO_NOT_REBUILD.md).
  Cashtags are stripped before the scan so the ticker $LONG cannot be read as
  the word "long".

Import discipline (gate 0.6): STDLIB ONLY at module level. Voice (§2): wire
tone, declarative, numbers carry the drama, no hedging, no hype adjectives, no
"BREAKING", no hashtags, no links, no emoji. ASCII hyphens only, never an em
dash. Ticker display names are deliberately never rendered: "3M" would inject a
digit that belongs to no fact.
"""
from __future__ import annotations

import hashlib
import logging
import re
import string
from datetime import date, datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

MAX_CHARS = 279

#: Call language. Observations only (masterplan gate 0.4).
WIRE_BANNED: tuple[str, ...] = (
    "buy", "buying", "sell", "selling", "entry", "entries", "long", "short",
    "added", "adding", "i'm in", "we're in", "load up", "loading",
    "take profit", "take profits", "stop loss", "target", "targets",
    "position", "positions", "accumulate", "trim", "exit", "calls", "puts",
    "bid", "chase",
)

#: §2.D device slots. A rendered post must carry at least one (see DEVICE_LAW).
DEVICE_SLOTS: frozenset[str] = frozenset({
    "since_clause", "streak_clause", "dollar_clause", "record_rank_clause",
    "breadth_clause", "leaders_clause", "milestone_clause", "live_marker",
    "flagged_clause", "green_list",
    # T4 (earnings reaction) + the codex two-step context brief.
    "earnings_clause", "eps_clause",
    "mechanism_clause", "affected_clause", "watch_clause",
})

_MONTHS_ABBR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MONTHS_FULL = ("January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December")

_CASHTAG_RE = re.compile(r"\$[A-Za-z][A-Za-z.\-]{0,9}")
_NUM_TOKEN_RE = re.compile(
    r"\$\d[\d,]*(?:\.\d+)?(?:\s(?:trillion|billion|million))?"   # $58 billion, $1,234.50
    r"|[+-]?\d+(?:\.\d+)?%"                                      # -8.1%
    r"|[+-]?\d[\d,]*(?:\.\d+)?"                                  # bare counts
)
_BAN_RES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (w, re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE)) for w in WIRE_BANNED
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared formatters — templates and the allow-list use THESE, never str()
# ─────────────────────────────────────────────────────────────────────────────

def _f(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    return None


def fmt_pct(v: Any, *, signed: bool = True) -> str | None:
    """'-8.1%' (signed) or '8.1%' (magnitude)."""
    f = _f(v)
    if f is None:
        return None
    return f"{f:+.1f}%" if signed else f"{abs(f):.1f}%"


def fmt_price(v: Any, *, cents: bool = True) -> str | None:
    """'$84.20', or '$1,235' with cents=False (only used above $1,000)."""
    f = _f(v)
    if f is None:
        return None
    return f"${f:,.2f}" if cents else f"${f:,.0f}"


def fmt_big(v: Any) -> str | None:
    """Dollar magnitude in words: '$1.2 trillion', '$58 billion', '$430 million'."""
    f = _f(v)
    if f is None:
        return None
    a = abs(f)
    if a >= 1e12:
        s = f"{a / 1e12:.1f}".rstrip("0").rstrip(".")
        return f"${s} trillion"
    if a >= 1e9:
        s = f"{a / 1e9:.0f}" if a >= 1e10 else f"{a / 1e9:.1f}".rstrip("0").rstrip(".")
        return f"${s} billion"
    if a >= 1e6:
        return f"${a / 1e6:.0f} million"
    return f"${int(a):,}"


def fmt_count(v: Any) -> str | None:
    """'27' — counts, day numbers, RSI bands."""
    f = _f(v)
    return None if f is None else str(int(round(f)))


def fmt_rsi(v: Any) -> str | None:
    """'28' — RSI to the nearest whole point."""
    f = _f(v)
    return None if f is None else f"{f:.0f}"


def _as_date(v: Any) -> date | None:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:  # noqa: BLE001
        return None


def fmt_date(v: Any, style: str = "full") -> str | None:
    """'Jun 9, 2026' (full) / 'Jun 9' (short) / 'June 2026' (month_year)."""
    d = _as_date(v)
    if d is None:
        return None
    if style == "short":
        return f"{_MONTHS_ABBR[d.month - 1]} {d.day}"
    if style == "month_year":
        return f"{_MONTHS_FULL[d.month - 1]} {d.year}"
    return f"{_MONTHS_ABBR[d.month - 1]} {d.day}, {d.year}"


def fmt_since(v: Any, ref: Any = None, *, far_days: int = 120) -> str | None:
    """The recency-appropriate date form: month-year when far, 'Jun 9' when near."""
    d = _as_date(v)
    if d is None:
        return None
    r = _as_date(ref) or datetime.now(timezone.utc).date()
    return fmt_date(d, "month_year" if (r - d).days > far_days else "short")


# ─────────────────────────────────────────────────────────────────────────────
# Ban scan
# ─────────────────────────────────────────────────────────────────────────────

def _strip_cashtags(text: str) -> str:
    """Blank out $TICKER tokens.

    The ticker $LONG is not the word "long", and a word-boundary ban scan
    cannot tell them apart. Cashtags are our own rendering of facts.ticker, so
    they are exempt by construction.
    """
    return _CASHTAG_RE.sub(" ", text or "")


def ban_hits(text: str) -> list[str]:
    """Banned call-language tokens present in `text` (cashtags exempted)."""
    body = _strip_cashtags(text or "")
    return [w for w, rx in _BAN_RES if rx.search(body)]


# ─────────────────────────────────────────────────────────────────────────────
# Numeric consistency (gate 0.3)
# ─────────────────────────────────────────────────────────────────────────────

def _walk_leaves(node: Any):
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk_leaves(v)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _walk_leaves(v)
    else:
        yield node


def allowed_date_strings(packet: Any) -> set[str]:
    """Every rendering of every date in the packet's facts."""
    out: set[str] = set()
    for leaf in _walk_leaves(getattr(packet, "facts", {}) or {}):
        if not isinstance(leaf, str):
            continue
        d = _as_date(leaf)
        if d is None:
            continue
        for style in ("full", "short", "month_year"):
            s = fmt_date(d, style)
            if s:
                out.add(s)
    return out


def allowed_number_strings(packet: Any) -> set[str]:
    """Every plausible rendering of every number in the packet's facts.

    Deliberately a SUPERSET per leaf (pct, price, big-dollar, count and RSI
    forms of each value, plus its magnitude): the gate exists to catch a number
    that came from nowhere, not to police which formatter a template chose.
    """
    out: set[str] = set()
    for leaf in _walk_leaves(getattr(packet, "facts", {}) or {}):
        f = _f(leaf)
        if f is None:
            continue
        for v in (f, abs(f)):
            for fn in (lambda x: fmt_pct(x), lambda x: fmt_pct(x, signed=False),
                       lambda x: fmt_price(x), lambda x: fmt_price(x, cents=False),
                       fmt_big, fmt_count, fmt_rsi):
                try:
                    s = fn(v)
                except Exception:  # noqa: BLE001
                    s = None
                if s:
                    out.add(s)
            out.add(f"${int(abs(v)):,}")
    return out


def check_text_numbers(text: str, packet: Any) -> list[str]:
    """Numeric tokens in `text` that are NOT derivable from packet.facts.

    Dates are consumed first (a "since March 2025" carries a year that is a
    date, not a free-floating number), then cashtags, then every remaining
    numeric token must be in :func:`allowed_number_strings`.
    """
    body = text or ""
    for phrase in sorted(allowed_date_strings(packet), key=len, reverse=True):
        body = body.replace(phrase, " ")
    body = _strip_cashtags(body)
    allowed = allowed_number_strings(packet)
    return [tok for tok in (m.group(0).strip() for m in _NUM_TOKEN_RE.finditer(body))
            if tok and tok not in allowed]


# ─────────────────────────────────────────────────────────────────────────────
# Phrase tables (static copy — scanned by the ban test)
# ─────────────────────────────────────────────────────────────────────────────

#: Session marker by phase. "at the close" is deliberately ONLY in after_hours:
#: the radar's window opens five minutes before the bell, so a 09:27 ET post
#: that said "at the close" would be describing a session that has not started
#: (reviewer M7). pre_open gets its own pair rather than borrowing rth's "so far
#: today", which reads as intraday.
_LIVE_MARKERS: dict[str, tuple[str, ...]] = {
    "pre_open": ("in premarket trading", "before the bell"),
    "rth": ("so far today", "right now"),
    "after_hours": ("today", "at the close"),
}
_DIR_VERB = {"up": "is up", "down": "is down"}
_DIR_WORD = {"up": "higher", "down": "lower"}
_RUN_WORD = {"up": "the climb", "down": "the slide"}
_RUN_COLOR = {"up": "green", "down": "red"}
_LEADERS_LABEL = {"up": "Best", "down": "Worst"}
_ONE_DAY_MOVE = {"up": "gain", "down": "drop"}
#: Milestone verbs come in PAIRS: one that claims the crossing just happened
#: and one that only claims where the price stands. Which one a post gets is
#: decided by `facts.crossed_in_window`, never by the template — see
#: :func:`_milestone_clause`.
_MILESTONE_VERB = {"up": "just cleared", "down": "just broke below"}
_MILESTONE_VERB_STANDING = {"up": "trades above", "down": "trades below"}
_MCAP_VERB = {"up": "just crossed", "down": "just slipped back under"}
_MCAP_VERB_STANDING = {"up": "sits above", "down": "sits below"}
#: When the report landed. A fragment, always following the cashtag, so the
#: sentence reads "$AAPL reported after yesterday's close and is up 6.0%".
_REPORT_WHEN = {"bmo": "reported before the bell",
                "ah": "reported after yesterday's close"}
_EPS_VERDICT = {True: "ahead of", False: "under"}


def static_strings() -> list[str]:
    """Every static copy string in this module (templates + phrase tables).

    The ban test scans this, so a banned word cannot enter the bank unnoticed
    even in a variant no fixture happens to render.
    """
    out: list[str] = []
    for bank in WIRE_BANK.values():
        out.extend(tpl for tpl, _ in bank)
    for table in (_DIR_VERB, _DIR_WORD, _RUN_WORD, _RUN_COLOR, _LEADERS_LABEL,
                  _ONE_DAY_MOVE, _MILESTONE_VERB, _MILESTONE_VERB_STANDING,
                  _MCAP_VERB, _MCAP_VERB_STANDING, _REPORT_WHEN,
                  _EPS_VERDICT):
        out.extend(table.values())
    for markers in _LIVE_MARKERS.values():
        out.extend(markers)
    out.extend(_STATIC_CLAUSE_FRAGMENTS)
    return out


#: Clause phrases assembled by the slot builders below, listed here so the
#: static ban scan sees them even where no fixture happens to render them. The
#: per-variant render test is the primary scan; this is the belt.
_STATIC_CLAUSE_FRAGMENTS: tuple[str, ...] = (
    "RSI is back under", "RSI is back above", "for the first time since",
    "That would be Day", "its longest", "run since", "run since at least",
    "That is roughly", "in market value gone since yesterday's close",
    "in fresh market value since yesterday's close",
    "That is its biggest one-day", "That is its biggest one-day drop since at least",
    "That is its biggest one-day gain since at least",
    "That is now", "below the record close of", "set",
    "names lower", "names higher", "officially enters correction territory",
    "is officially in bear market territory", "just cleared its record close of",
    "in market value", "the level our engine flagged in last night's plan",
    "the level our engine flagged in our", "plan", "Watching how it holds.",
    "Still green:", "are green", "Green across", "Median", "median", "Last",
    "crossed", "just traded through", "through", "again", "is up", "is down",
    # T4 earnings reaction
    "EPS came in at", "consensus", "surprise",
    # Two-step context brief (codex): mechanism, affected names, what to watch
    "This is a group move:", "names are trading together",
    "The rest of", "is not following:", "names, median",
    "so this is one name and not the group",
    "Also moving:", "What we are watching:", "whether the breadth holds",
    "names so far", "holds through the session",
)


# ─────────────────────────────────────────────────────────────────────────────
# Slot builders — each returns None when its facts are absent (gate 0.2)
# ─────────────────────────────────────────────────────────────────────────────

def _live_marker(packet: Any) -> str:
    phase = str(getattr(packet, "session", ""))
    if phase not in _LIVE_MARKERS:
        phase = "after_hours"
    options = _LIVE_MARKERS[phase]
    idx = _hash_int(str(getattr(packet, "key", "")) + phase) % len(options)
    return options[idx]


def _hash_int(seed: str) -> int:
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12], 16)


def _since_clause(packet: Any, f: dict) -> str | None:
    """D3 — the recency-rarity quantifier, from the live RSI band re-entry.

    THE SIDE COMES FROM THE BAND, NEVER THE DIRECTION (reviewer C2). Reading it
    off ``packet.direction`` inverted the sentence whenever the two disagreed:
    a name selling off from 78 to 75.3 rendered "RSI is back under 70" at an RSI
    of 75.3 — a claim contradicted by the number the same packet carries. Band
    30 means "under", band 70 means "above", and anything else refuses.

    Two belts on top of that, because this clause is a claim about a CROSSING
    and a packet that cannot support one must say nothing: the live RSI has to
    be on the side of the band it claims to have reached, and the move has to
    agree with it (a 30 crossing happens on a down day, a 70 crossing on an up
    day). A band that contradicts its own packet is corrupt input, not copy.
    """
    band, since = f.get("rsi_band"), f.get("rsi_since")
    band_f, live = _f(band), _f(f.get("rsi_live"))
    direction = str(getattr(packet, "direction", ""))
    if band_f == 30.0:
        side, crossing_dir = "under", "down"
        if live is not None and live > 30.0:
            return None
    elif band_f == 70.0:
        side, crossing_dir = "above", "up"
        if live is not None and live < 70.0:
            return None
    else:
        return None
    if direction and direction != crossing_dir:
        return None
    when = fmt_since(since, str(getattr(packet, "fired_at", ""))[:10])
    band_s = fmt_count(band)
    if not when or not band_s:
        return None
    return f"RSI is back {side} {band_s} for the first time since {when}"


#: Mirror of detectors.streak.min_len (config/hot_tape.yml + hot_tape.DEFAULTS).
#: A "Day 2 of the slide, its longest red run since at least March 2021" is not
#: a differentiating stat, it is a two-day sequence dressed as one — and the
#: mover family reaches this clause through streak_extends, which carries NO
#: rarity floor of its own (reviewer m2). Kept as a literal rather than read
#: from cfg because the slot builders are pure functions of the packet.
STREAK_CLAUSE_MIN_LEN = 5


def _streak_clause(packet: Any, f: dict) -> str | None:
    """D4 — the streak count plus how rare a run this long is."""
    src = f.get("streak_extends") if isinstance(f.get("streak_extends"), dict) else f
    n = fmt_count(src.get("len_today"))
    length = _f(src.get("len_today"))
    if not n or length is None or length < STREAK_CLAUSE_MIN_LEN:
        return None
    direction = str(src.get("dir") or getattr(packet, "direction", "") or "down")
    run, color = _RUN_WORD.get(direction, _RUN_WORD["down"]), _RUN_COLOR.get(direction, "red")
    ref = str(getattr(packet, "fired_at", ""))[:10]
    since = fmt_since(src.get("since"), ref)
    if since:
        return f"That would be Day {n} of {run}, its longest {color} run since {since}"
    window = fmt_date(src.get("window_start"), "month_year")
    if window:
        return (f"That would be Day {n} of {run}, its longest {color} run "
                f"since at least {window}")
    return None


def _dollar_clause(packet: Any, f: dict) -> str | None:
    """D2 — the dollar translation of the move."""
    value = f.get("dollar_delta_usd")
    if value is None:
        value = f.get("dollar_moved_usd")
    big = fmt_big(value)
    if not big:
        return None
    direction = str(getattr(packet, "direction", "down"))
    # "since yesterday's close", not "today": the dollar figure is mcap (a
    # last-close number) x today's move, so this is the literal claim — and
    # every mover/sector template already carries a {live_marker}, so a
    # "today" here doubled it ("... down 12.1% today. ... wiped out today.").
    tail = ("in market value gone since yesterday's close" if direction == "down"
            else "in fresh market value since yesterday's close")
    return f"That is roughly {big} {tail}"


def _record_rank_clause(packet: Any, f: dict) -> str | None:
    """D6 — a record or rank claim, immediately backed by its number."""
    ref = str(getattr(packet, "fired_at", ""))[:10]
    direction = str(getattr(packet, "direction", "down"))
    biggest = f.get("biggest_1d") if isinstance(f.get("biggest_1d"), dict) else None
    if biggest:
        # ANCHOR ON THE WINDOW, NOT THE PRIOR EXTREME (reviewer M9).
        # prior_date is the date of the LAST bigger move INSIDE our dense
        # window, so "biggest one-day drop since <prior_date>" quietly claims we
        # looked further back than we did — the pack's memory starts at
        # window_start and the 2021-2024 history has month-long holes. The
        # honest sentence names the edge of what we can see. prior_pct /
        # prior_date stay in the facts as provenance; they are not rendered.
        when = fmt_since(biggest.get("window_start"), ref)
        if when:
            word = _ONE_DAY_MOVE.get(direction, "move")
            return f"That is its biggest one-day {word} since at least {when}"
    from_ath = _f(f.get("pct_from_ath_live"))
    ath, ath_date = fmt_price(f.get("ath")), fmt_date(f.get("ath_date"), "full")
    if from_ath is not None and from_ath <= -5.0 and ath and ath_date:
        return (f"That is now {fmt_pct(from_ath, signed=False)} below the record "
                f"close of {ath} set {ath_date}")
    return None


def _breadth_clause(packet: Any, f: dict) -> str | None:
    """The group's internal breadth: '24 of 27 names lower'."""
    direction = str(getattr(packet, "direction", "down"))
    n_dir = fmt_count(f.get("n_down") if direction == "down" else f.get("n_up"))
    n_all = fmt_count(f.get("n_members"))
    if not n_dir or not n_all:
        return None
    return f"{n_dir} of {n_all} names {_DIR_WORD.get(direction, 'lower')}"


def _leaders_clause(packet: Any, f: dict) -> str | None:
    """The three most extreme members with their moves."""
    rows = f.get("leaders") if isinstance(f.get("leaders"), list) else []
    parts: list[str] = []
    for row in rows[:3]:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        pct = fmt_pct(row[1])
        if pct:
            parts.append(f"${str(row[0]).upper()} {pct}")
    return ", ".join(parts) if len(parts) >= 2 else None


def _milestone_clause(packet: Any, f: dict) -> str | None:
    """D8 — pseudo-official milestone language, with the level attached.

    "JUST" IS A CLAIM ABOUT TIME AND IT NEEDS A RECEIPT (2026-07-31).

    The threshold detector compares the live price against yesterday's close,
    so its crossing test stays true for the rest of the session once the level
    goes. Phrasing that as an event shipped "$AAPL right now: just broke below
    $325.00" at 16:00Z on a level the tape gapped through at the open — in the
    same sweep that had the name 11% below its all-time high, i.e. more than
    $20 under the level it was supposedly breaking. Both sentences were
    arithmetically correct; only one of them was about now.

    ``facts.crossed_in_window`` is the receipt (the prior tick did not have
    this crossing). Without it the clause still ships — it just says where the
    price STANDS, which is the honest half of the same fact.
    """
    kind = str(f.get("kind") or "")
    direction = str(getattr(packet, "direction", "down"))
    fresh = bool(f.get("crossed_in_window"))
    if kind in ("correction", "bear"):
        from_ath = fmt_pct(f.get("pct_from_ath_live"), signed=False)
        ath, ath_date = fmt_price(f.get("ath")), fmt_date(f.get("ath_date"), "full")
        if not (from_ath and ath and ath_date):
            return None
        # "enters" is the event form; "is officially in" is the state. Bear was
        # already stateful, so only correction has a pair to choose from.
        head = ("officially enters correction territory" if (kind == "correction" and fresh)
                else "is officially in correction territory" if kind == "correction"
                else "is officially in bear market territory")
        return f"{head}, {from_ath} below the record close of {ath} set {ath_date}"
    if kind == "ath":
        ath, ath_date = fmt_price(f.get("ath")), fmt_date(f.get("ath_date"), "full")
        if not (ath and ath_date):
            return None
        verb = "just cleared" if fresh else "trades above"
        return f"{verb} its record close of {ath} from {ath_date}"
    if kind == "round":
        level = fmt_price(f.get("level"))
        if not level:
            return None
        table = _MILESTONE_VERB if fresh else _MILESTONE_VERB_STANDING
        return f"{table.get(direction, 'trades through')} {level}"
    if kind == "mcap":
        milestone = fmt_big(f.get("milestone_usd"))
        if not milestone:
            return None
        table = _MCAP_VERB if fresh else _MCAP_VERB_STANDING
        return (f"{table.get(direction, 'trades through')} {milestone} "
                "in market value")
    return None


def _flagged_clause(packet: Any, f: dict) -> str | None:
    """The proprietary-event clause. Observation only, never a call."""
    plan = _as_date(f.get("plan_as_of"))
    fired = _as_date(str(getattr(packet, "fired_at", ""))[:10])
    if plan is None:
        return None
    if fired is not None and (fired - plan).days <= 1:
        return "the level our engine flagged in last night's plan"
    when = fmt_date(plan, "full")
    return f"the level our engine flagged in our {when} plan" if when else None


def _green_list(packet: Any, f: dict) -> str | None:
    rows = f.get("green") if isinstance(f.get("green"), list) else []
    parts: list[str] = []
    for row in rows[:4]:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        pct = fmt_pct(row[1])
        if pct:
            parts.append(f"${str(row[0]).upper()} {pct}")
    return ", ".join(parts) if len(parts) >= 3 else None


def _earnings_clause(packet: Any, f: dict) -> str | None:
    """T4 — WHEN the report landed, which is what makes the gap readable.

    Not a §2.D device on its own (it carries no number), which is why the
    earnings family's DEVICE_LAW requires it AND one of the real stats: a post
    that only says "reported and moved" is the bare %-move flop with a calendar
    entry stapled to it.
    """
    return _REPORT_WHEN.get(str(f.get("report_when") or ""))


def _eps_clause(packet: Any, f: dict) -> str | None:
    """D6 — the beat/miss, immediately backed by both numbers.

    Renders ONLY from :func:`engine.marketing.hot_tape._fresh_surprise`, i.e.
    a filing whose reported date is the report we detected. Last quarter's beat
    presented as today's is the one lie this clause could tell, so the freshness
    test lives upstream and this builder simply has nothing to say without it.
    """
    eps = f.get("eps") if isinstance(f.get("eps"), dict) else None
    if not eps:
        return None
    actual, consensus = fmt_price(eps.get("actual")), fmt_price(eps.get("consensus"))
    if not actual or not consensus:
        return None
    beat = bool(eps.get("beat"))
    verdict = _EPS_VERDICT[beat]
    surprise = fmt_pct(eps.get("surprise_pct"), signed=False)
    tail = f", a {surprise} surprise" if surprise else ""
    return f"EPS came in at {actual}, {verdict} the {consensus} consensus{tail}"


def _mechanism_clause(packet: Any, f: dict) -> str | None:
    """The two-step brief's why-it-matters sentence (codex: mechanism reposts).

    REQUIRED — the brief family refuses without it. It states the one causal
    thing we can compute honestly from our own data: whether the peer group
    moved WITH the subject or did not. Everything it says is a leaf of the
    packet, so "why it matters" never becomes "what we assume".

    THE COUNT IS AGREEING NAMES OVER GROUP SIZE (2026-07-31). It used to read
    "{n_peers} names are trading together", which was the same two-defects-in-
    one string the desk feeds shipped as "18 groups on the move today": a
    numerator with no universe, AND the wrong number in it — n_peers is the
    SIZE of the peer group, not a count of names that moved, so a group where
    5 of 12 names agreed was described as 12 names trading together. n_agree
    was already in the packet and simply never rendered.
    """
    mech = f.get("mechanism") if isinstance(f.get("mechanism"), dict) else None
    if not mech:
        return None
    group = str(mech.get("group") or "").strip()
    median = fmt_pct(mech.get("peer_median_pct"))
    n = fmt_count(mech.get("n_peers"))
    agree = fmt_count(mech.get("n_agree"))
    if not group or not median or not n or not agree:
        return None
    if str(mech.get("kind")) == "group":
        return (f"This is a group move: {agree} of {n} names are trading "
                f"together, median {median}")
    return (f"The rest of {group} is not following: {agree} of {n} names moved "
            f"with it, median {median}, so this is one name and not the group")


def _affected_clause(packet: Any, f: dict) -> str | None:
    """The brief's affected-names line: who else the same tape is moving."""
    rows = f.get("peers") if isinstance(f.get("peers"), list) else []
    parts: list[str] = []
    for row in rows[:3]:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        pct = fmt_pct(row[1])
        if pct:
            parts.append(f"${str(row[0]).upper()} {pct}")
    return "Also moving: " + ", ".join(parts) if len(parts) >= 2 else None


def _watch_clause(packet: Any, f: dict) -> str | None:
    """The brief's forward line — a WINDOW, never a call (operator 2026-07-27).

    "What we are watching" is the compliant shape: a condition that will be
    visible on the tape, not a prediction and not a falsifier verdict. The
    Calibration Lab owns verdicts; a wire post owns the condition.
    """
    watch = f.get("watch") if isinstance(f.get("watch"), dict) else None
    if not watch:
        return None
    kind = str(watch.get("kind") or "")
    if kind == "breadth":
        agree, total = fmt_count(watch.get("n_agree")), fmt_count(watch.get("n_members"))
        if not agree or not total:
            return None
        return (f"What we are watching: whether the breadth holds, {agree} of "
                f"{total} names so far")
    if kind == "level":
        price = fmt_price(watch.get("price"))
        if not price:
            return None
        return f"What we are watching: whether {price} holds through the session"
    return None


def _sectors_clause(f: dict) -> str | None:
    names = [str(s) for s in (f.get("sectors_green") or []) if s]
    if len(names) < 2:
        return None
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _index_clause(f: dict) -> str | None:
    pct = fmt_pct(f.get("index_pct"))
    if not pct:
        return None
    return f"with ${str(f.get('index_ticker') or 'SPY').upper()} {pct}"


def build_slots(packet: Any) -> dict[str, str | None]:
    """Every slot a template may reference, derived from the packet's facts."""
    f = getattr(packet, "facts", {}) or {}
    direction = str(getattr(packet, "direction", "down"))
    ticker = getattr(packet, "ticker", None) or f.get("ticker")
    price_v = f.get("price")
    slots: dict[str, str | None] = {
        "cashtag": f"${str(ticker).upper()}" if ticker else None,
        "dir_verb": _DIR_VERB.get(direction),
        "dir_word": _DIR_WORD.get(direction),
        "pct_abs": fmt_pct(f.get("pct") if f.get("pct") is not None else f.get("pct_today"),
                           signed=False),
        "price": fmt_price(price_v, cents=True),
        "live_marker": _live_marker(packet),
        "since_clause": _since_clause(packet, f),
        "streak_clause": _streak_clause(packet, f),
        "dollar_clause": _dollar_clause(packet, f),
        "record_rank_clause": _record_rank_clause(packet, f),
        "breadth_clause": _breadth_clause(packet, f),
        "leaders_clause": _leaders_clause(packet, f),
        "leaders_label": _LEADERS_LABEL.get(direction),
        "milestone_clause": _milestone_clause(packet, f),
        "flagged_clause": _flagged_clause(packet, f),
        "earnings_clause": _earnings_clause(packet, f),
        "eps_clause": _eps_clause(packet, f),
        "mechanism_clause": _mechanism_clause(packet, f),
        "affected_clause": _affected_clause(packet, f),
        "watch_clause": _watch_clause(packet, f),
        "subject_label": (str(f.get("subject_label")) if f.get("subject_label")
                          else None),
        "green_list": _green_list(packet, f),
        "sectors_clause": _sectors_clause(f),
        "index_clause": _index_clause(f),
        "index_cashtag": f"${str(f.get('index_ticker') or 'SPY').upper()}",
        "index_pct": fmt_pct(f.get("index_pct")),
        "n_green": fmt_count(f.get("n_green")),
        # The universe behind n_green. None when the detector could not supply
        # it, which drops the only variant that makes a count claim rather than
        # shipping "31 names are green" with no 31-of-what (see the note on
        # _CONTRARIAN_VARIANTS).
        "n_defensive": fmt_count(f.get("n_defensive_members")),
        "sector_label": str(f.get("sector")) if f.get("sector") else None,
        "median_pct": fmt_pct(f.get("median_pct")),
        "level": fmt_price(f.get("level")),
    }
    return slots


# ─────────────────────────────────────────────────────────────────────────────
# The bank: (template, required device slots) per trigger family
# ─────────────────────────────────────────────────────────────────────────────

_MOVER_VARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("{cashtag} {dir_verb} {pct_abs} at {price} {live_marker}. {record_rank_clause}.",
     ("record_rank_clause", "live_marker")),
    ("{cashtag} {dir_verb} {pct_abs} {live_marker}. {dollar_clause}.",
     ("dollar_clause", "live_marker")),
    ("{cashtag} {dir_verb} {pct_abs} {live_marker}. {streak_clause}.",
     ("streak_clause", "live_marker")),
    ("{cashtag} {dir_verb} {pct_abs} at {price} {live_marker}. {since_clause}.",
     ("since_clause", "live_marker")),
    ("{cashtag} {dir_verb} {pct_abs} {live_marker}. {dollar_clause}. {record_rank_clause}.",
     ("dollar_clause", "record_rank_clause", "live_marker")),
)

_SECTOR_VARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("{sector_label}: {breadth_clause} {live_marker}, median {median_pct}. {dollar_clause}.",
     ("breadth_clause", "dollar_clause", "live_marker")),
    ("{sector_label}: {breadth_clause} {live_marker}, median {median_pct}. "
     "{leaders_label}: {leaders_clause}.",
     ("breadth_clause", "leaders_clause", "live_marker")),
    ("{breadth_clause} in {sector_label} {live_marker}. Median {median_pct}. "
     "{dollar_clause}. {leaders_label}: {leaders_clause}.",
     ("breadth_clause", "dollar_clause", "live_marker")),
    ("{sector_label}: {breadth_clause} {live_marker}, median {median_pct}, {index_clause}. "
     "{leaders_label}: {leaders_clause}.",
     ("breadth_clause", "leaders_clause", "live_marker")),
    ("{sector_label}: {breadth_clause}, median {median_pct} {live_marker}. "
     "{dollar_clause}. {leaders_label}: {leaders_clause}.",
     ("breadth_clause", "dollar_clause", "live_marker")),
)

_THRESHOLD_VARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("{cashtag} {milestone_clause}. Last {price} {live_marker}.",
     ("milestone_clause",)),
    ("{cashtag} {milestone_clause}.", ("milestone_clause",)),
    ("{cashtag} {live_marker}: {milestone_clause}.", ("milestone_clause",)),
    ("{cashtag} {milestone_clause}, last {price}.", ("milestone_clause",)),
)

_STREAK_VARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("{cashtag} is {dir_word} again {live_marker}. {streak_clause}.",
     ("streak_clause", "live_marker")),
    ("{cashtag} {dir_verb} {pct_abs} {live_marker}. {streak_clause}.",
     ("streak_clause", "live_marker")),
    ("{cashtag} {dir_verb} {pct_abs} at {price} {live_marker}. {streak_clause}.",
     ("streak_clause", "live_marker")),
)

_SIGNAL_VARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("{cashtag} crossed {level} {live_marker}, {flagged_clause}. Watching how it holds.",
     ("flagged_clause", "live_marker")),
    ("{cashtag} just traded through {level} {live_marker}. {flagged_clause_cap}.",
     ("flagged_clause", "live_marker")),
    ("{cashtag} {live_marker} at {price}, through {level}. {flagged_clause_cap}.",
     ("flagged_clause", "live_marker")),
)

_CONTRARIAN_VARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("{index_cashtag} is {index_pct} {live_marker}. Still green: {green_list}.",
     ("green_list", "live_marker")),
    # A COUNT CARRIES ITS UNIVERSE OR IT DOES NOT SHIP (2026-07-31). This shape
    # used to read "and 31 names across Utilities and Consumer Defensive are
    # green" — 31 of how many? The denominator slot is a REQUIRED device here,
    # so a packet that cannot supply it renders one of the other two variants
    # (which make no count claim) instead of a bare numerator.
    ("{index_cashtag} is {index_pct} {live_marker}, and {n_green} of "
     "{n_defensive} names across {sectors_clause} are green. {green_list}.",
     ("green_list", "live_marker")),
    ("{index_cashtag} {index_pct} {live_marker}. Green across {sectors_clause}: "
     "{green_list}.",
     ("green_list", "live_marker")),
)

#: T4 — the earnings reaction. The report is the FRAME and always leads or
#: closes the first sentence; the differentiating stat is a separate clause,
#: because "reported and moved 6%" is the flop shape with a calendar attached.
#:
#: EVERY VARIANT CARRIES {eps_clause} (M3). Two of these used to close on
#: {dollar_clause} / {record_rank_clause} instead, which produced a post that
#: announced an earnings reaction and never said what the company earned: the
#: reader is told a report landed, told the stock moved, and left to look up the
#: only number the post exists to deliver. The move-leading skeleton is KEPT (it
#: is the one shape that does not open on the report) with the beat/miss added,
#: so the family still rotates across two opening frames rather than collapsing
#: to one; the old dollar_clause variant is dropped outright because with the
#: eps line required it is the last variant here with extra words.
_EARNINGS_VARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("{cashtag} {earnings_clause} and {dir_verb} {pct_abs} at {price} {live_marker}. "
     "{eps_clause}.",
     ("earnings_clause", "eps_clause", "live_marker")),
    ("{cashtag} {dir_verb} {pct_abs} at {price} {live_marker}, and it {earnings_clause}. "
     "{eps_clause}.",
     ("earnings_clause", "eps_clause", "live_marker")),
    ("{cashtag} {earnings_clause} and {dir_verb} {pct_abs} {live_marker}. "
     "{eps_clause}. {dollar_clause}.",
     ("earnings_clause", "eps_clause", "live_marker")),
)

#: The two-step follow-up (codex §Strongest controlled comparisons A). Three
#: sentences at most: what moved, WHY it matters (the mechanism), and either who
#: else it is moving or what we are watching next. The {subject_label} shapes
#: exist for a GROUP brief, which has no cashtag to lead with — and the label
#: being None on a single-name brief is what stops the two shapes swapping.
_BRIEF_VARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("{cashtag} {dir_verb} {pct_abs} at {price} {live_marker}. {mechanism_clause}. "
     "{affected_clause}.",
     ("mechanism_clause", "affected_clause")),
    ("{cashtag} {dir_verb} {pct_abs} {live_marker}. {mechanism_clause}. "
     "{watch_clause}.",
     ("mechanism_clause", "watch_clause")),
    ("{subject_label}: {mechanism_clause}. {affected_clause}.",
     ("mechanism_clause", "affected_clause")),
    ("{subject_label}: {mechanism_clause}. {watch_clause}.",
     ("mechanism_clause", "watch_clause")),
)

#: trigger -> ((template, required device slots), ...)
WIRE_BANK: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "mover_pop": _MOVER_VARIANTS,
    "mover_drop": _MOVER_VARIANTS,
    "sector_rout": _SECTOR_VARIANTS,
    "sector_rip": _SECTOR_VARIANTS,
    "threshold_cross": _THRESHOLD_VARIANTS,
    "streak_rarity": _STREAK_VARIANTS,
    "signal_fired": _SIGNAL_VARIANTS,
    "contrarian_breadth": _CONTRARIAN_VARIANTS,
    "earnings_reaction": _EARNINGS_VARIANTS,
    "context_brief": _BRIEF_VARIANTS,
}

#: trigger -> (slots that must ALL be present, set of which at least one must be)
DEVICE_LAW: dict[str, tuple[tuple[str, ...], frozenset[str]]] = {
    "mover_pop": (("live_marker",), frozenset({
        "since_clause", "streak_clause", "dollar_clause", "record_rank_clause"})),
    "mover_drop": (("live_marker",), frozenset({
        "since_clause", "streak_clause", "dollar_clause", "record_rank_clause"})),
    "sector_rout": (("breadth_clause", "live_marker"),
                    frozenset({"dollar_clause", "leaders_clause"})),
    "sector_rip": (("breadth_clause", "live_marker"),
                   frozenset({"dollar_clause", "leaders_clause"})),
    "threshold_cross": (("milestone_clause",), frozenset()),
    "streak_rarity": (("streak_clause", "live_marker"), frozenset()),
    "signal_fired": (("flagged_clause", "live_marker"), frozenset()),
    "contrarian_breadth": (("green_list", "live_marker"), frozenset()),
    # The report is context, not a stat, and on THIS family the stat is not
    # interchangeable (M3): an earnings reaction states the beat or the miss.
    # `eps_clause` was one of five acceptable devices, so a post could satisfy
    # gate 0.2 with a dollar translation and never print the EPS line. It is
    # mandatory now, which also empties the any-of set: eps_clause IS a §2.D
    # device (D6), so demanding a second one on top would reject the shortest
    # honest shape and leave the family with a single template.
    #
    # A packet with no FRESH surprise therefore cannot render an earnings post
    # at all, and that is the correct refusal rather than a coverage loss:
    # `_suppress_mover_overlap` now leaves such a name's mover twin alive, so a
    # BMO reporter whose filing has not landed by 09:30 posts as the mover story
    # it actually is. See engine/marketing/hot_tape.py.
    "earnings_reaction": (("earnings_clause", "eps_clause", "live_marker"),
                          frozenset()),
    # The brief's whole job is the mechanism (codex: "a mechanism makes context
    # worth reposting"), so it is mandatory and refusal is the alternative.
    "context_brief": (("mechanism_clause",),
                      frozenset({"affected_clause", "watch_clause"})),
}


# ─────────────────────────────────────────────────────────────────────────────
# compose_wire
# ─────────────────────────────────────────────────────────────────────────────

def _placeholders(template: str) -> list[str]:
    return [n for _, n, _, _ in string.Formatter().parse(template) if n]


def _base_slot(name: str) -> str:
    """'flagged_clause_cap' and 'flagged_clause' are the same device."""
    return name[:-4] if name.endswith("_cap") else name


def _devices_used(template: str) -> set[str]:
    return {_base_slot(n) for n in _placeholders(template) if _base_slot(n) in DEVICE_SLOTS}


def _shorten_once(template: str, slots: dict, droppable: set[str]) -> str | None:
    """Drop the sentence carrying the longest optional device slot."""
    best, best_len = None, -1
    for name in sorted(droppable):
        value = slots.get(name)
        if isinstance(value, str) and len(value) > best_len and ("{" + name + "}") in template:
            best, best_len = name, len(value)
    if best is None:
        return None
    parts = template.split(". ")
    keep = [p for p in parts if ("{" + best + "}") not in p]
    if not keep or len(keep) == len(parts):
        return None
    out = ". ".join(keep).strip()
    return out if out.endswith(".") else out + "."


def _row_symbols(f: dict, key: str) -> list[str]:
    """Uppercased symbols out of a [[SYM, pct], ...] fact list."""
    out: list[str] = []
    for row in (f.get(key) if isinstance(f.get(key), list) else []):
        if isinstance(row, (list, tuple)) and row:
            sym = str(row[0]).strip().upper()
            if sym:
                out.append(sym)
    return out


#: The ONLY fact keys forwarded to the LLM desk (M6). An ALLOWLIST, because the
#: fact dict is written by nine detectors and read by one gate that treats every
#: number it can reach as admissible: `severity` and `provenance` were kept out
#: by name, and everything a detector added afterwards walked straight in.
#:
#: The live example is the two-step brief. Its facts carry `alert_key`
#: ("mover:MU:down:2026-07-29T14:05:00Z:0"), so 2026, 29, 14 and 05 were all
#: licensed figures — a model could write "up 14" on a stock that moved 8% and
#: clear gate 0.3 against an internal id. Counters and stamps that no clause
#: renders (`prev_close`, `threshold_px`, `report_date`, `signal_id`,
#: `refire_ratio`, `quote_ts_ms`, the `earn_next_*` pair) are out for the same
#: reason: the model's job is to PHRASE the facts the template renders, and a
#: number it cannot show is a number it cannot invent.
#:
#: The list is the union of every key the slot builders in this module read.
#: `test_the_llm_packet_forwards_every_key_a_clause_renders` recomputes that
#: union from the source and fails when a new device outgrows this constant.
LLM_FACT_KEYS: frozenset[str] = frozenset({
    # identity + labels
    "ticker", "name", "sector", "subject_label", "kind", "dir", "direction",
    "mechanism", "report_when", "index_ticker", "rsi_band", "plan_as_of",
    # A BOOL, and forwarded on purpose: it is what licenses "just broke below"
    # over "trades below", and a model that cannot see it would phrase the
    # freshness claim the template just refused. Bools are dropped by both
    # numeric walkers, so it can never license a figure.
    "crossed_in_window",
    # the tape
    "pct", "pct_today", "price", "level", "median_pct", "index_pct",
    "pct_from_ath_live", "ath", "ath_date", "biggest_1d",
    # translations + devices
    "dollar_delta_usd", "dollar_moved_usd", "milestone_usd", "eps",
    "streak_extends", "len_today", "since", "window_start",
    "rsi_live", "rsi_since",
    # groups
    "n_up", "n_down", "n_members", "n_green", "n_defensive_members",
    "sectors_green", "leaders", "green", "peers", "watch",
})


def llm_packet(packet: Any) -> dict:
    """The FactPacket dict handed to the LLM wire desk (P2 phrasing).

    ``engine.marketing.hot_tape_llm`` treats every number it can reach as
    engine-computed and admissible, so what this function does NOT include is
    the load-bearing half: ``severity`` (an internal ranking score, not a fact
    about the tape), the whole ``provenance`` block (build stamps and quote
    epochs), and every fact key outside :data:`LLM_FACT_KEYS` — or a model could
    write "87" and pass gate 0.3 with a number no reader could ever check.

    ``cashtags`` must list every ticker the copy may name — the LLM gate rejects
    any cashtag outside it as a smuggled comparison — so leaders, green names,
    brief peers and the index proxy are all collected here. That collection runs
    over the FULL fact dict (a peer list is a cashtag source even though the
    model may not quote its numbers); only the forwarded facts are filtered.
    """
    f = dict(getattr(packet, "facts", {}) or {})
    ticker = getattr(packet, "ticker", None) or f.get("ticker")
    primary = f"${str(ticker).upper()}" if ticker else None

    tags: list[str] = []
    seen: set[str] = set()
    for sym in ([str(ticker).upper()] if ticker else []) + \
            _row_symbols(f, "leaders") + _row_symbols(f, "green") + \
            _row_symbols(f, "peers") + \
            ([str(f["index_ticker"]).upper()] if f.get("index_ticker") else []):
        tag = f"${sym}"
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)

    out: dict[str, Any] = {
        "trigger": str(getattr(packet, "trigger", "")),
        "direction": str(getattr(packet, "direction", "")),
        "as_of": str(getattr(packet, "fired_at", "")),
        "cashtag": primary,
        "cashtags": tags,
        "name": getattr(packet, "name", None) or f.get("name"),
        "sector": getattr(packet, "sector", None) or f.get("sector"),
        # The house live marker, so the model reaches for OUR wording of "now"
        # instead of inventing one that contradicts the session (a 09:27 ET
        # "at the close" is the failure this table exists to prevent).
        "live_marker": _live_marker(packet),
        "facts": {k: v for k, v in f.items() if k in LLM_FACT_KEYS},
    }
    return out


def compose_wire(
    packet: Any,
    *,
    cfg: dict | None = None,
    variant_seed: str = "",
) -> dict | None:
    """Render one wire post for `packet`, or None when it must REFUSE.

    Returns {"text", "devices", "trigger"}. Refusal is the designed outcome
    whenever the §2.D device law cannot be met from the facts on hand: a
    "%-move + chart" post with no differentiating stat is the 95-view flop
    gate 0.2 exists to make impossible.

    Every candidate is re-checked after rendering: length, em dashes, banned
    call language, and numeric consistency against the packet. A variant that
    fails any check is skipped, and a family whose variants all fail returns
    None rather than a post that only the tests would have caught.
    """
    try:
        trigger = str(getattr(packet, "trigger", ""))
        bank = WIRE_BANK.get(trigger)
        if not bank:
            return None
        mandatory, any_of = DEVICE_LAW.get(trigger, ((), frozenset()))
        max_chars = int(((cfg or {}).get("wire") or {}).get("max_chars", MAX_CHARS))

        slots = build_slots(packet)
        slots["flagged_clause_cap"] = (
            slots["flagged_clause"][0].upper() + slots["flagged_clause"][1:]
            if slots.get("flagged_clause") else None
        )

        start = _hash_int(str(getattr(packet, "key", "")) + str(variant_seed)) % len(bank)
        for offset in range(len(bank)):
            template, required = bank[(start + offset) % len(bank)]
            names = _placeholders(template)
            if any(slots.get(n) is None for n in names):
                continue
            if any(slots.get(n) is None for n in required):
                continue

            for candidate in (template, _shorten_once(
                    template, slots,
                    {n for n in names if _base_slot(n) in DEVICE_SLOTS} - set(required))):
                if candidate is None:
                    continue
                # Device law is checked on the CANDIDATE, not the source
                # template: _shorten_once may drop a device sentence, and a
                # shortened post must still satisfy gate 0.2 on its own.
                used = _devices_used(candidate)
                if any(m not in used for m in mandatory):
                    continue
                if any_of and not (used & any_of):
                    continue
                text = candidate.format(**slots).strip()
                if len(text) > max_chars:
                    continue
                if "—" in text or "–" in text:
                    continue
                if ban_hits(text):
                    log.warning("hot_tape_wire: banned language in a variant for %s",
                                getattr(packet, "key", "?"))
                    break
                if check_text_numbers(text, packet):
                    log.warning("hot_tape_wire: number not in facts for %s",
                                getattr(packet, "key", "?"))
                    break
                devices = sorted(_devices_used(candidate))
                return {"text": text, "devices": devices, "trigger": trigger}
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_wire.compose_wire failed: %s", exc)
        return None
