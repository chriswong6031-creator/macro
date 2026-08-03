"""engine.marketing.market_clock — the honest temporal word for a marketing post.

WHY THIS EXISTS (operator defect report 2026-08-02, three classes shipped broken)
--------------------------------------------------------------------------------
Marketing copy stamps time words — "today", "overnight", "while New York slept",
"earnings land July 29" — from templates and from an LLM, and NOTHING in the
pipeline ever asked the exchange calendar whether those words were true. Three
classes went out or sat queued over the weekend of 2026-08-01/02:

  A. ``ob-2026-08-02-7fb823aecd`` (PUBLISHED Sunday 20:16Z, generated Sunday
     03:50Z): "While New York slept, one name kept running: / $MSFT +21.8% this
     week … That's a steepening slope, and earnings land July 29. 🍵"
     — an overnight frame on a day with no session on either side of the night,
     and a FUTURE-TENSE verb ("land") on a date four days in the past.
  B. ``ob-2026-08-01-a83c188711`` (generated Saturday 21:49Z): "$AMZN +15.3%
     today" — Friday's move called "today", on a Saturday.
  C. The "4 of 11 sectors green" family — six near-identical posts fanned across
     slots D1-S1/S5/S6/S10 in two weekend runs off ONE stale Friday breadth read.

Every one of those is a clock question, and there was no clock. Nine separate
sites had independently re-implemented ``weekday() >= 5`` (see the census in the
PR body) and not one of them was holiday-aware or fact-aware.

WHAT THIS MODULE IS
-------------------
ONE authority for three questions, used by BOTH generators and validators:

  * generators ask :func:`temporal_vocab` for the word they are allowed to
    stamp ("today" / "Friday" / "" ) and stamp that;
  * validators ask :func:`temporal_violations` which words already in a text are
    dishonest, and :func:`dead_date_future_tense` whether a past date is wearing
    a future-tense verb;
  * the fan-out gates ask :func:`fact_anchor_keys` which source fact a post is
    anchored on, so one fact cannot wear six posts.

The exchange calendar is NOT reimplemented here: :mod:`lib.nyse_calendar` is the
estate's existing authority (pure rule arithmetic, stdlib only, holidays + Good
Friday + one-off closures) and this module is a thin, marketing-shaped face over
it. It is imported LAZILY and guarded, because that module builds a ``ZoneInfo``
at import time and this one must survive a host with no tzdata: such a host
degrades to the weekend-only answer (wrong on the ~9 closure days a year, never
dead) — the same contract :func:`engine.marketing.hot_tape._is_session` states.

WEEKDAY AND MONTH NAMES ARE STATIC TUPLES, never ``strftime("%A")``/``("%B")``:
those are locale-sensitive and this is PUBLISHED COPY. Same reasoning, same
shape, as :data:`engine.marketing.intelligence_context._MONTHS_EN`.

FAIL DIRECTION. Every helper here is asked "may this post say X?", so the safe
error is to REFUSE. A clock that cannot resolve returns the conservative answer
(no "today", no "overnight"), never the permissive one — an unreadable calendar
must not become a licence to call Friday's tape "today".

Display-tier: no signal authority, no ledger writes. Callers own their gates.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Calendar face
# ─────────────────────────────────────────────────────────────────────────────

try:  # pragma: no cover - exercised by the tzdata-present path everywhere
    from zoneinfo import ZoneInfo

    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - no tzdata on host
    ET = None  # type: ignore[assignment]

#: US cash-equity regular session bounds, ET. Early closes (13:00) are not
#: modeled — an early-close day is still a session, which is the only thing any
#: question here turns on.
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

#: Published copy never goes through ``strftime`` for a NAME (locale-sensitive).
_WEEKDAYS_EN: tuple[str, ...] = (
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
)
_MONTHS_EN: tuple[str, ...] = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

#: Beyond this many days back a bare weekday name is ambiguous ("Friday" reads
#: as the most recent one), so the vocab falls back to a month-day phrase.
_WEEKDAY_NAME_MAX_AGE_DAYS = 6


def weekday_name(d: date) -> str:
    """"Monday" … "Sunday" for `d`. Static table, never ``strftime("%A")``."""
    return _WEEKDAYS_EN[d.weekday()]


def month_day(d: date) -> str:
    """"July 31" for `d`. Static table, never ``strftime("%B")``."""
    return f"{_MONTHS_EN[d.month - 1]} {d.day}"


def is_session_day(d: date) -> bool:
    """True when the US cash-equity market holds a session on `d`.

    Weekends AND scheduled NYSE full-day closures (holidays, Good Friday,
    announced one-offs), from :mod:`lib.nyse_calendar`. A host that cannot load
    the calendar degrades to the weekend-only answer rather than raising.
    """
    if d.weekday() >= 5:
        return False
    try:
        from lib.nyse_calendar import is_session  # noqa: PLC0415

        return bool(is_session(d))
    except Exception:  # pragma: no cover - no tzdata / calendar unavailable
        log.warning("market_clock: nyse_calendar unavailable — weekday-only session answer")
        return True


def session_of(d: date) -> date:
    """The session `d`'s facts belong to: `d` itself, else the session before it.

    A plan built on a Saturday carries ``as_of`` = that Saturday while its facts
    are Friday's close; this is the function that says so. Bounded walk — the
    longest closed stretch is a few days.
    """
    x = d
    for _ in range(30):
        if is_session_day(x):
            return x
        x -= timedelta(days=1)
    return x


def _et(now: datetime) -> datetime:
    """`now` in ET. Naive datetimes are read as UTC (the pipeline's convention)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if ET is None:  # pragma: no cover - no tzdata
        return now.astimezone(timezone.utc) - timedelta(hours=4)
    return now.astimezone(ET)


def et_date(now: datetime) -> date:
    """`now`'s ET calendar date — the day a timestamp's facts belong to.

    Marketing timestamps are UTC, and after 20:00 ET the UTC date is already
    tomorrow: a nightly plan built at 23:51 ET Friday is stamped ``as_of
    2026-08-01`` (a Saturday) while every fact in it is Friday's close. Reading
    the ET date first is what stops that off-by-one becoming a false verdict in
    both directions.
    """
    return _et(now).date()


def current_session(now: datetime) -> date | None:
    """The session date IN PROGRESS at `now`, or None on a non-session day.

    "In progress" spans the whole ET calendar day of a session — pre-market, RTH
    and post-market alike — matching :func:`lib.nyse_calendar.session_date`'s
    stamping semantics. This is deliberately NOT "the market is open right now":
    a 08:00 ET post on a session day is legitimately talking about today.
    """
    d = _et(now).date()
    return d if is_session_day(d) else None


def last_completed_session(now: datetime) -> date:
    """The most recent session whose 16:00 ET close has passed at `now`.

    On a session day before the close this is the PRIOR session — the current
    one has not finished, so nothing about it has "closed". Distinct from
    :func:`current_session`, which answers "which session is today".
    """
    et = _et(now)
    d = et.date()
    if is_session_day(d) and et.time() >= MARKET_CLOSE:
        return d
    return session_of(d - timedelta(days=1))


def is_pre_open(now: datetime) -> bool:
    """True on a session day before 09:30 ET — the window an overnight gap has
    just elapsed into and can honestly be described."""
    et = _et(now)
    return is_session_day(et.date()) and et.time() < MARKET_OPEN


# ─────────────────────────────────────────────────────────────────────────────
# The temporal vocabulary contract
# ─────────────────────────────────────────────────────────────────────────────

#: Words that assert the fact is from the session happening NOW.
#:
#: DELIBERATELY NARROW. The publisher's quarantine is TERMINAL, so a false
#: positive kills a good post permanently — the same reasoning that makes
#: ``marketing_publisher._queued_headline`` refuse to guess. Only phrases that
#: can ONLY mean "the current session's tape" are here. Three near-misses were
#: considered and REJECTED:
#:   * "right now" — ``market_facts`` ships "Liquidity's loosening right now.",
#:     a regime statement with no session claim in it at all;
#:   * "tonight" — the futures/Asia lanes legitimately say it on a Sunday;
#:   * "this week"/"this month" — true on a Wednesday, and the weekend defect
#:     they appear in (fixture A) is already caught by its overnight frame.
_TODAY_WORDS: tuple[str, ...] = (
    "today", "today's", "so far today", "on the day", "this session",
    "on the session", "intraday", "at the close", "into the close",
    "this morning", "this afternoon",
)

#: Words that assert an overnight / pre-market gap elapsed between two sessions.
_OVERNIGHT_WORDS: tuple[str, ...] = (
    "overnight", "while new york slept", "while new york sleeps",
    "while wall street slept", "while the street slept",
    "before new york wakes", "before the bell", "premarket", "pre-market",
    "in the premarket", "last night", "overnight session",
)


def _word_re(words: tuple[str, ...]) -> re.Pattern[str]:
    """Case-insensitive alternation, longest-first so "so far today" wins over
    "today" and the receipt names the phrase the writer actually used."""
    ordered = sorted(words, key=len, reverse=True)
    return re.compile(
        r"(?<![\w'])(" + "|".join(re.escape(w) for w in ordered) + r")(?![\w])",
        re.IGNORECASE,
    )


_TODAY_RE = _word_re(_TODAY_WORDS)
_OVERNIGHT_RE = _word_re(_OVERNIGHT_WORDS)


@dataclass(frozen=True)
class TemporalVocab:
    """The honest temporal words for a fact, given when it is being said.

    ``phrase`` is what a generator STAMPS ("today", "on Friday", ""); ``word`` is
    the bare form for a headline ("today", "Friday", ""). Empty means the post
    gets NO temporal word — the honest degradation, never a guessed one.
    """

    phrase: str
    word: str
    allows_today: bool
    allows_overnight: bool
    now_session: date | None
    fact_session: date | None
    reason: str = ""


def _as_date(value: object) -> date | None:
    """Parse an ``as_of``-shaped value ("2026-08-01", a date, a datetime)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:  # noqa: BLE001
        return None


def temporal_vocab(now: datetime, fact_asof: object) -> TemporalVocab:
    """The temporal word a post may use for a fact stamped `fact_asof`, said at `now`.

    THE CONTRACT (operator brief 2026-08-02):

    * "today" ONLY when the fact's session IS the session in progress at `now`.
      On a non-session day there is no session in progress, so "today" is never
      available — that alone kills defect B ("$AMZN +15.3% today", written on a
      Saturday about Friday's tape).
    * otherwise the weekday name of the fact's session ("Friday" / "on Friday"),
      while that name is unambiguous (≤6 days back), then a month-day phrase.
    * "overnight" / "while New York slept" only when an overnight gap actually
      elapsed INTO a session — i.e. `now` is on a session day, pre-open. A
      weekend night is not an overnight gap between sessions; that kills the
      frame in defect A.

    `fact_asof` is normalized through :func:`session_of`, so a Saturday-stamped
    plan whose facts are Friday's close resolves to Friday, not to "no session".
    """
    fact_day = _as_date(fact_asof)
    fact_session = session_of(fact_day) if fact_day is not None else None
    now_session = current_session(now)

    allows_overnight = is_pre_open(now)

    if fact_session is None:
        return TemporalVocab(
            phrase="", word="", allows_today=False,
            allows_overnight=allows_overnight,
            now_session=now_session, fact_session=None,
            reason="fact as_of unparseable — no temporal word",
        )

    if now_session is not None and fact_session == now_session:
        return TemporalVocab(
            phrase="today", word="today", allows_today=True,
            allows_overnight=allows_overnight,
            now_session=now_session, fact_session=fact_session,
            reason="fact belongs to the session in progress",
        )

    age = (_et(now).date() - fact_session).days
    if 0 <= age <= _WEEKDAY_NAME_MAX_AGE_DAYS:
        name = weekday_name(fact_session)
        reason = (f"no session in progress — fact is {name}'s"
                  if now_session is None else
                  f"fact is {name}'s, not the session in progress")
        return TemporalVocab(
            phrase=f"on {name}", word=name, allows_today=False,
            allows_overnight=allows_overnight,
            now_session=now_session, fact_session=fact_session,
            reason=reason,
        )

    if age < 0:
        # A fact dated in the future has no honest temporal word at all.
        return TemporalVocab(
            phrase="", word="", allows_today=False,
            allows_overnight=allows_overnight,
            now_session=now_session, fact_session=fact_session,
            reason="fact session is in the future — no temporal word",
        )

    label = month_day(fact_session)
    return TemporalVocab(
        phrase=f"on {label}", word=label, allows_today=False,
        allows_overnight=allows_overnight,
        now_session=now_session, fact_session=fact_session,
        reason=f"fact is {age} days old — a weekday name would be ambiguous",
    )


def temporal_violations(text: str, *, now: datetime, fact_asof: object) -> list[str]:
    """Which temporal words in `text` the clock says are FALSE. Empty = honest.

    Reason strings are stable slugs with the offending phrase attached, so a
    quarantine receipt and an admin chip can both key off the head:

      ``today_word_off_session:today``     — a "today"-class word whose fact is
                                             not the session in progress
      ``overnight_without_gap:overnight``  — an overnight frame with no overnight
                                             gap into a session

    Deliberately says nothing about words the clock cannot judge: this is a
    falsity detector, not a style rule.
    """
    body = str(text or "")
    if not body.strip():
        return []
    vocab = temporal_vocab(now, fact_asof)
    out: list[str] = []

    if not vocab.allows_today:
        seen: set[str] = set()
        for m in _TODAY_RE.finditer(body):
            hit = m.group(1).lower()
            if hit in seen:
                continue
            seen.add(hit)
            out.append(f"today_word_off_session:{hit}")

    if not vocab.allows_overnight:
        seen_o: set[str] = set()
        for m in _OVERNIGHT_RE.finditer(body):
            hit = m.group(1).lower()
            if hit in seen_o:
                continue
            seen_o.add(hit)
            out.append(f"overnight_without_gap:{hit}")

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Event tense: a date in the past may not wear a future-tense verb
# ─────────────────────────────────────────────────────────────────────────────

#: Frames that place an event AHEAD of the reader, split by WHERE they sit
#: relative to the date — the split is what keeps this precise:
#:   * "earnings land July 29"  → a PRE frame (verb, then date)   → future
#:   * "July 29 is on deck"     → a POST frame (date, then frame) → future
#:   * "ahead of July 29 it ran" → "ahead of" is PRE-position but RETROSPECTIVE
#:     narration about a past date, so it is in neither list and never trips.
#: Same reason "into", "before", "until" and bare "due" (as in "due to July 29's
#: guidance") are absent: each has a common past-tense reading.
_FUTURE_PRE: tuple[str, ...] = (
    "land", "lands", "landing", "is due", "are due", "comes", "coming",
    "upcoming", "on deck", "next up", "will report", "will land",
    "will come", "will be", "set for", "slated for", "scheduled for",
    "awaits", "await", "watch for", "eyes on", "reports", "drops",
)
_FUTURE_POST: tuple[str, ...] = (
    "is ahead", "ahead", "is coming", "coming", "is on deck", "on deck",
    "is next", "next up", "is due", "are due", "lands", "land",
)


def _frame_re(frames: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        r"(?<![\w'])(" + "|".join(
            re.escape(w) for w in sorted(frames, key=len, reverse=True)
        ) + r")(?![\w])",
        re.IGNORECASE,
    )


_FUTURE_PRE_RE = _frame_re(_FUTURE_PRE)
_FUTURE_POST_RE = _frame_re(_FUTURE_POST)

_MONTH_ALT = "|".join(m[:3] for m in _MONTHS_EN)
#: "July 29", "Jul 29", "July 29th", "29 July" — the shapes marketing copy uses.
_DATE_RE = re.compile(
    rf"(?<![\w])((?:{_MONTH_ALT})[a-z]*)\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?![\d])",
    re.IGNORECASE,
)
_DATE_RE_DM = re.compile(
    rf"(?<![\w])(\d{{1,2}})(?:st|nd|rd|th)?\s+((?:{_MONTH_ALT})[a-z]*)(?![\w])",
    re.IGNORECASE,
)

#: How far either side of the date mention a future frame still binds to it.
#: A clause, not a sentence: "earnings land July 29" is 12 chars of verb-to-date,
#: while "we called it in July and by July 29 it had run" must not trip.
_FRAME_WINDOW_CHARS = 24

#: A month-day carries no year, so it is resolved to the nearest such date around
#: `now`. Beyond this the mention is treated as unresolvable and skipped.
_DATE_RESOLVE_MAX_DAYS = 200


def _month_index(token: str) -> int | None:
    t = token.strip().lower()
    for i, name in enumerate(_MONTHS_EN):
        if name.lower().startswith(t[:3]) and len(t) >= 3:
            return i + 1
    return None


def _resolve_month_day(month: int, day: int, ref: date) -> date | None:
    """The instance of month/day nearest `ref` (prior, same or next year)."""
    best: date | None = None
    for year in (ref.year - 1, ref.year, ref.year + 1):
        try:
            cand = date(year, month, day)
        except ValueError:
            continue
        if best is None or abs((cand - ref).days) < abs((best - ref).days):
            best = cand
    if best is None or abs((best - ref).days) > _DATE_RESOLVE_MAX_DAYS:
        return None
    return best


def dead_date_future_tense(text: str, *, now: datetime) -> list[str]:
    """Future-tense frames bound to a date that has already passed.

    The fixture is defect A: "That's a steepening slope, and earnings land July
    29." said on 2026-08-02 — "land" is four days too late, and no gate in the
    pipeline could see it because the sentence contains no banned word, no stale
    price and no duplicate.

    Reason slug: ``dead_date_future_tense:<frame>:<Month Day>``.

    Scope is DATE-ANCHORED on purpose. A bare "earnings are coming" carries no
    checkable date, so it is not this function's business; the operator brief
    asks for "any detectable future-tense date reference in the past", and a
    detectable one is a resolvable one. Today's date is NOT past — an event
    landing today is still ahead of the reader for most of the day.
    """
    body = str(text or "")
    if not body.strip():
        return []
    ref = _et(now).date()
    out: list[str] = []
    seen: set[tuple[str, str]] = set()

    spans: list[tuple[int, int, int, int]] = []  # (start, end, month, day)
    for m in _DATE_RE.finditer(body):
        mi = _month_index(m.group(1))
        if mi is not None:
            spans.append((m.start(), m.end(), mi, int(m.group(2))))
    for m in _DATE_RE_DM.finditer(body):
        mi = _month_index(m.group(2))
        if mi is not None:
            spans.append((m.start(), m.end(), mi, int(m.group(1))))

    for start, end, month, day in spans:
        resolved = _resolve_month_day(month, day, ref)
        if resolved is None or resolved >= ref:
            continue
        window = body[max(0, start - _FRAME_WINDOW_CHARS):start]
        after = body[end:end + _FRAME_WINDOW_CHARS]
        # A sentence boundary breaks the bond: the frame must be in this clause.
        window = re.split(r"[.!?\n]", window)[-1]
        after = re.split(r"[.!?\n]", after)[0]
        # Nearest PRE frame (the last one before the date), else the first POST.
        frame = None
        for m in _FUTURE_PRE_RE.finditer(window):
            frame = m.group(1).lower()
        if frame is None:
            m2 = _FUTURE_POST_RE.search(after)
            frame = m2.group(1).lower() if m2 else None
        if frame is None:
            continue
        label = month_day(resolved)
        key = (frame, label)
        if key in seen:
            continue
        seen.add(key)
        out.append(f"dead_date_future_tense:{frame}:{label}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Fact anchors: one source fact wears one post
# ─────────────────────────────────────────────────────────────────────────────

#: "4 of 11 sectors" — a ratio over a named universe. The SAME fact whatever
#: post kind wears it (a sector board has one true green count per session), so
#: its key is deliberately kind-agnostic: that is what collapses the six-post
#: "4 of 11 sectors green" family, which spans kinds macro AND event.
_RATIO_RE = re.compile(
    r"(?<![\w.])(\d{1,4})\s+(?:of|out of|/)\s+(\d{1,4})\s+([a-z]{3,20})",
    re.IGNORECASE,
)

#: A signed percent claim ("+15.3%", "-7%"). Only the LEAD one, and only when
#: the post names EXACTLY ONE ticker — both narrowings exist to keep this from
#: firing on coincidence rather than on a shared fact:
#:   * a theme_list post lists eight members' percents, and two unrelated themes
#:     sharing one member's +2.1% is not one fact wearing two posts;
#:   * two desks quoting 15.3% about two different names is a coincidence.
#: A single-ticker post's first percent IS its claim, which is the fixture-B
#: shape ("$AMZN +15.3% today").
_PCT_RE = re.compile(r"(?<![\w])([+-]?\d{1,3}(?:\.\d{1,2})?)\s?%")
_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})(?![\w])")

#: Plural/singular collapse so "4 of 11 sectors" and "4 of 11 sector" agree.
def _stem(noun: str) -> str:
    n = noun.lower()
    return n[:-1] if len(n) > 3 and n.endswith("s") else n


def fact_anchor_keys(text: str, kind: str = "") -> frozenset[str]:
    """The source facts a post is anchored on, as stable comparable keys.

    Two posts sharing a key are two dressings of ONE fact — the defect class C
    shape, where a single Friday breadth read was fanned into six slots across
    four desks with interchangeable hedges.

      ``ratio:4of11:sector``      — kind-agnostic (one universe, one true value)
      ``pct:mover:AMZN:15.3``     — kind- and ticker-scoped, lead claim only

    Empty set = no extractable anchor; callers must treat that as "cannot judge"
    and let the post through, never as "no duplicate".
    """
    body = str(text or "")
    k = str(kind or "").strip().lower()
    keys: set[str] = set()

    for m in _RATIO_RE.finditer(body):
        n, total, noun = m.group(1), m.group(2), _stem(m.group(3))
        if n == total:
            continue  # saturated: a definition, not a read (market_facts law)
        keys.add(f"ratio:{int(n)}of{int(total)}:{noun}")

    tickers = {m.group(1) for m in _CASHTAG_RE.finditer(body)}
    if len(tickers) == 1:
        lead = _PCT_RE.search(body)
        if lead is not None:
            try:
                val = float(lead.group(1))
            except ValueError:
                val = None  # type: ignore[assignment]
            if val is not None:
                keys.add(f"pct:{k}:{next(iter(tickers))}:{val:g}")

    return frozenset(keys)


# ─────────────────────────────────────────────────────────────────────────────
# Breadth value gate
# ─────────────────────────────────────────────────────────────────────────────

#: A breadth read is a READ when it leans. Between these two fractions of the
#: universe it says only "mixed", which is the mushy stat the six-post family
#: was built on. Saturation (0/N, N/N) is already refused upstream by
#: market_facts._is_vacuous_count as a definition rather than a fact.
BREADTH_STRONG_UP = 0.70
BREADTH_STRONG_DOWN = 0.30


def breadth_stance(n_green: object, n_total: object) -> str:
    """"up" | "down" | "indecisive" | "unknown" for a green-count breadth read."""
    try:
        g, t = int(n_green), int(n_total)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "unknown"
    if t <= 0 or g < 0 or g > t:
        return "unknown"
    frac = g / t
    if frac >= BREADTH_STRONG_UP:
        return "up"
    if frac <= BREADTH_STRONG_DOWN:
        return "down"
    return "indecisive"


#: The stance tail an indecisive breadth read must carry, keyed to the FACT KIND
#: rather than to a caller's label (the tail-keys-to-KIND law). Honest "watch,
#: don't chase" IS a stance — the defect was six interchangeable hedges on one
#: mushy stat, not hedging itself. First person, so it costs the writer
#: something (the fact-plus-cost voice law) and clears
#: publish_time_content._tail_is_bait.
_BREADTH_TAILS: dict[str, dict[str, str]] = {
    "indecisive": {
        "macro": "I am not trading a tape this split. I want one side to win a day first.",
        "event": "That is not a read I will size on, so I am sitting on my hands.",
        "": "Too split for me to lean on, so I am watching rather than chasing.",
    },
    "up": {
        "macro": "That is broad enough that I stop calling it a one-sector story.",
        "event": "Broad green is the part I care about, so I am giving it the benefit of the doubt.",
        "": "That is broad enough for me to take the move at face value.",
    },
    "down": {
        "macro": "When it is that one-sided I stop looking for the name that escapes it.",
        "event": "One-sided red is the part I respect, so I am not shopping for a bounce.",
        "": "When it is that one-sided I stop hunting for the exception.",
    },
}


def breadth_stance_tail(stance: str, kind: str = "") -> str:
    """The stance tail for a breadth read of `stance`, keyed to the fact `kind`.

    Empty string when the stance is unknown — a tail invented over a stat we
    cannot classify is exactly the interchangeable hedge this gate exists to
    stop.
    """
    bank = _BREADTH_TAILS.get(str(stance or "").lower())
    if not bank:
        return ""
    return bank.get(str(kind or "").strip().lower()) or bank.get("", "")


def breadth_may_anchor(n_green: object, n_total: object, *, now: datetime) -> bool:
    """May this breadth read anchor a standalone macro/event post right now?

    NO for an indecisive read on a NON-SESSION day: nothing traded, the number is
    the last session's, and "4 of 11 sectors green" with a hedge tail is not a
    reason for a post to exist. A read that genuinely leans still is, and on a
    session day the read is current — it ships with its stance tail instead.
    """
    if current_session(now) is not None:
        return True
    return breadth_stance(n_green, n_total) in ("up", "down")
