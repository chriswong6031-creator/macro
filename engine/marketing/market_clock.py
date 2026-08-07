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
  * the fan-out gates ask :func:`lead_fact_keys` which source fact a post LEADS
    on, so one fact cannot wear six posts while a post that merely quotes a
    prior number to frame a new one still ships (:func:`fact_anchor_keys` is the
    whole-body form, kept for callers asking "what does this post touch").

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


def live_session(now: datetime) -> date:
    """The most recent session that has OPENED at `now`. The freshness clock.

    THE OPERATOR'S LAW (2026-08-06): "you can post about tickers during market
    hours and after market closes anytime and say oh this went up or this went
    down, but you cant post yesterdays action today, or todays action tomorrow."
    So the window a tape claim is publishable in is exactly ONE session, and it
    closes when the NEXT session opens — not at the bell, not at midnight.

    Distinct from both of its neighbours, and the difference is the whole point:

      * :func:`current_session` returns None off-session, which would make a
        Saturday post about Friday's close "stale" — wrong, no new session has
        opened, Friday is still the live tape;
      * :func:`last_completed_session` returns the PRIOR session all morning,
        which would make a 10:00 ET post about this morning's move "stale" —
        also wrong, and it is the same post the operator explicitly blesses
        ("during market hours").

    Falls back through the weekend/holiday to the session before, so this is
    total: there is always a most-recent open session.
    """
    return current_session(now) or last_completed_session(now)


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
# Session claims, and the freshness law over them
#
# THE OPERATOR, 2026-08-06: "we cannot keep posting stale content from the day
# before. you can post about tickers during market hours and after market closes
# anytime and say oh this went up or this went down, but you cant post yesterdays
# action today, or todays action tomorrow. no human would post stale data like
# that."
#
# THE MEASURED DEFECT. A `theme_list` planned for 2026-08-05T12:00Z reading
# "+1.9% avg on Tuesday" still offered an Approve button on Wednesday night —
# 35 hours old, one whole session past its own tape. Two siblings reached 60h.
# Every generation-time gate in the estate had passed it, correctly: "on Tuesday"
# was TRUE when it was written. The queue is what made it false, so only a
# publish-time gate can catch it — an item can be approved at any hour.
#
# WHY THIS LIVES HERE and not in the publisher. `publish_time_content` already
# resolves weekday / month-day / "today" phrases to session dates for ONE lane
# (its `_session_claims`), and the same question is now asked by the publisher
# for EVERY lane. A third copy of that resolver is how two gates start
# disagreeing about which session "on Friday" names. The resolver moves here,
# next to the calendar it depends on, and both callers ask the same function.
# ─────────────────────────────────────────────────────────────────────────────

#: A weekday name as published copy writes it ("on Friday", "Friday's move").
#: CASE-SENSITIVE on the capitalised form: these are proper nouns in a headline,
#: and a case-insensitive match would be a needless invitation for a lower-case
#: false positive to kill a good post (the refusals downstream are terminal).
_WEEKDAY_CLAIM_RE = re.compile(
    r"(?<![\w'])(" + "|".join(_WEEKDAYS_EN) + r")(?![\w])")

#: "on July 31", "Aug 1" — the shape :func:`temporal_vocab` degrades to once a
#: weekday name would be ambiguous. Two deliberate narrowings:
#:   * a BARE month name is NOT matched. "May" is also an ordinary English word,
#:     and a month with no day number names no session anyway.
#:   * the alternation lists the FULL names and their 3-letter abbreviations
#:     EXPLICITLY, longest-first, instead of `Mar[a-z]*`-style prefixing. A
#:     wildcard suffix makes "Market 5" a March date, and a false positive here
#:     kills a good post.
_MONTH_ALTS: tuple[str, ...] = tuple(
    sorted({m for name in _MONTHS_EN for m in (name, name[:3])} | {"Sept"},
           key=len, reverse=True))
_MONTH_DAY_CLAIM_RE = re.compile(
    r"(?<![\w'])(" + "|".join(_MONTH_ALTS) + r")\.?\s+(\d{1,2})(?![\d])")

#: How far back a weekday / month-day phrase is resolved. 7 days covers every
#: phrase this estate's banks can emit (the vocab switches to month-day past 6
#: days); a month-day gets a year, because that is the range over which a
#: "July 31" in a live post could still be honest.
_WEEKDAY_LOOKBACK_DAYS = 7
_MONTH_DAY_LOOKBACK_DAYS = 366


def _resolve_weekday(name: str, today: date) -> date | None:
    """The session the bare weekday `name` points at, looking back from `today`."""
    for back in range(_WEEKDAY_LOOKBACK_DAYS + 1):
        d = today - timedelta(days=back)
        if weekday_name(d) == name:
            # session_of walks back off a non-session day, so "on Friday" said
            # about a Good Friday resolves to the Thursday that actually traded —
            # the same normalisation temporal_vocab uses.
            return session_of(d)
    return None


def _resolve_month_day_claim(token: str, day_num: str, today: date) -> date | None:
    """The session "Jul 31" / "August 1" points at, looking back from `today`."""
    try:
        day = int(day_num)
        month = next(i + 1 for i, name in enumerate(_MONTHS_EN)
                     if name.startswith(token))
    except (ValueError, StopIteration):
        return None
    for back in range(_MONTH_DAY_LOOKBACK_DAYS + 1):
        d = today - timedelta(days=back)
        if d.month == month and d.day == day:
            return session_of(d)
    return None


def session_claims(text: str, *, now: datetime) -> tuple[set[date], list[str]]:
    """(sessions the text claims, unresolvable claims) for copy said at `now`.

    Every claim is resolved to a SESSION DATE so two differently-worded claims
    about the same session ("today" on Monday and "on Monday") compare equal, and
    two claims about different sessions compare unequal no matter how they were
    phrased. That is the whole point: the check is about sessions, not strings.

    An unresolvable claim (a "today" word on a day with no session in progress; a
    weekday or month-day naming no session in the lookback) is returned SEPARATELY
    rather than dropped, because "we cannot tell which session this names" is a
    refusal, not a pass.
    """
    body = str(text or "")
    claims: set[date] = set()
    unresolved: list[str] = []
    if not body.strip():
        return claims, unresolved

    today = et_date(now)

    # "today" / "this session" / "at the close" … → the session in progress NOW.
    if _TODAY_RE.search(body):
        cur = current_session(now)
        if cur is None:
            # No session in progress (weekend / holiday) — a "today" word here
            # names nothing at all. temporal_violations reports the same
            # condition; it is repeated as an unresolved CLAIM so the two halves
            # of the check share one refusal path.
            unresolved.append(
                f"today-word with no session in progress at {today.isoformat()}")
        else:
            claims.add(cur)

    for m in _WEEKDAY_CLAIM_RE.finditer(body):
        hit = _resolve_weekday(m.group(1), today)
        if hit is None:
            unresolved.append(f"weekday '{m.group(1)}' names no session in the "
                              f"last {_WEEKDAY_LOOKBACK_DAYS} days")
        else:
            claims.add(hit)

    for m in _MONTH_DAY_CLAIM_RE.finditer(body):
        hit = _resolve_month_day_claim(m.group(1), m.group(2), today)
        if hit is None:
            unresolved.append(f"date '{m.group(0)}' is not in the last "
                              f"{_MONTH_DAY_LOOKBACK_DAYS} days")
        else:
            claims.add(hit)

    return claims, unresolved


# ── A DATE IN COPY IS NOT AUTOMATICALLY A CLAIM ABOUT WHICH SESSION IT REPORTS ─
#
# Found by replaying the freshness gate over the live 492-item outbox, not by
# review: a first cut refused 78 items that were dispatched exactly on time.
# Every one of them cited a date as an ANCHOR while reporting the current tape —
#
#   "Apple $AAPL is down -9.29% so far today, now -11.06% from its all-time high
#    of 340.08 set on July 28."
#   "$GOOGL is up 5.23% right now, with a 2-day winning streak since July 29."
#   "the average price paid since the Jun 26 volume spike"
#   "The July jobs numbers are due out Friday."
#
# — against the one shape the gate is FOR, where the date is the whole subject:
#
#   "Cloud Computing ripping, +1.7% avg on Tuesday"   (posted on Wednesday)
#
# The discriminator is the word in front of the date. A citation is introduced by
# a source cue ("set on", "since", "from its", "record ... of") and a forward
# reference by a future frame ("due out", "ahead of"); a session claim is
# introduced by "on", "'s", or nothing at all. Everything below is scoped to the
# FRESHNESS leg — `session_claims` above still reports every date it finds,
# because its other caller is looking for internal contradictions, where a
# citation is a legitimate half.
_CITATION_CUES: tuple[str, ...] = (
    "set", "since", "from", "back to", "record", "high of", "low of",
    "close of", "peak", "established", "prior", "versus", "vs", "compared",
    "spike", "before", "after", "between", "through", "until", "til",
    "dated", "reported", "filed", "announced", "posted on", "of its",
)
#
# THE SIGN-OFF SHAPE (round-2 review, m5). The list below started as the ways a
# desk points at a scheduled PRINT ("payrolls land Friday"), and it missed the
# ordinary ways a desk points at its own next post: "See you Monday", "Come back
# Sunday for the weekly recap", "I post the recap Sunday". Those were absorbed
# by the today-word early return until that amnesty was removed, and each one
# then read as a claim about Monday's tape — a TERMINAL quarantine whose receipt
# names a defect the copy does not have.
_FUTURE_CUES: tuple[str, ...] = (
    "due", "due out", "ahead of", "expected", "coming", "upcoming", "next",
    "scheduled", "slated", "lands", "land", "on deck", "watch for", "eyes on",
    "will", "reports",
    # sign-offs and forward pointers to our own next post
    "see you", "come back", "back on", "more on", "recap", "tune in",
    "catch you", "join me", "join us", "post the", "posting the",
)

#: How much text before a date token is inspected for a cue. One clause: "now
#: -11.06% from its all-time high of 340.08 set on " is 46 characters between
#: "from" and the date, which is why this is not tighter.
_CUE_LOOKBEHIND_CHARS = 52


def _claim_is_cited(body: str, start: int) -> bool:
    """True when the date token at `start` is a citation or a forward reference.

    Fail direction is PERMISSIVE — an ambiguous lead-in reads as a citation and
    the post survives — because the refusal downstream is a terminal quarantine
    and the freshness gate's own first leg (the item's `as_of`) still covers a
    genuinely stale row.
    """
    window = body[max(0, start - _CUE_LOOKBEHIND_CHARS):start].lower()
    if not window.strip():
        return False
    for cue in _CITATION_CUES + _FUTURE_CUES:
        if re.search(r"(?<![\w'])" + re.escape(cue) + r"(?![\w])", window):
            return True
    return False


def _stale_claim_in_copy(body: str, *, now: datetime, live: date) -> date | None:
    """The past session this copy REPORTS, or None. See `_claim_is_cited`.

    A TODAY-WORD IS NOT AN AMNESTY (round-1 review, 2026-08-06). The first cut
    returned None the moment the copy said "today" while the session was live,
    on the theory that a post reporting today is a report on today whatever else
    it cites. Measured, that disarmed the whole leg: `_clock_violations` refused
    "Cloud Computing ripping, +1.7% avg on Tuesday" posted Wednesday and PASSED
    "Cloud Computing is ripping across the board today … +1.7% on average on
    Tuesday", which is the operator's defect in the generator's OTHER wording and
    is live in the corpus as ob-2026-08-03-7faca980f7. Leg one cannot cover it —
    it fired zero times across the whole 492-item corpus on on-time dispatch,
    because `as_of` is stamped to the scheduled day by construction.

    A post that claims BOTH the live session and a past one is not exempt, it is
    INTERNALLY CONTRADICTORY, and that is strictly worse than the plain stale
    read. `stale_session_violations` says so in the receipt.

    The wire lane's anchor-heavy copy — the thing the amnesty was protecting — is
    now protected where it belongs: `market_action_claim` no longer judges
    `breaking` (or any other kind that perishes on its own clock) at all.
    """
    today = et_date(now)

    best: date | None = None
    for m in _WEEKDAY_CLAIM_RE.finditer(body):
        if _claim_is_cited(body, m.start()):
            continue
        hit = _resolve_weekday(m.group(1), today)
        if hit is not None and hit < live and (live - hit).days <= _WEEKDAY_LOOKBACK_DAYS:
            best = hit if best is None else min(best, hit)
    for m in _MONTH_DAY_CLAIM_RE.finditer(body):
        if _claim_is_cited(body, m.start()):
            continue
        hit = _resolve_month_day_claim(m.group(1), m.group(2), today)
        # BOUNDED TO THE WEEKDAY LOOKBACK on purpose. `session_claims` resolves a
        # month-day up to a YEAR back; past a week that is history, not a
        # freshness claim, and treating it as one killed "first since Jul 2026".
        if hit is not None and hit < live and (live - hit).days <= _WEEKDAY_LOOKBACK_DAYS:
            best = hit if best is None else min(best, hit)
    return best


#: Post kinds whose PAYLOAD is the tape: every one of these describes what a
#: price did, whether or not the copy happens to spell out a day word. A
#: `theme_list` is "these names moved together"; a `mover` is "this name moved";
#: `chart`, `signal` and `watchlist` are all reads of a price series.
#:
#: DELIBERATELY EXCLUDES `macro`, `event`, `education`, `insider`, `congress` and
#: `breaking`. A jobless-claims print, a filing and a wire flash are not tape
#: action — they perish on their own clocks (the wire reaper's 3h TTL, the
#: numeric-fact cooldown), and sweeping them in here would make one gate own
#: four different perishability laws.
ACTION_KINDS: frozenset[str] = frozenset(
    {"mover", "theme_list", "chart", "signal", "watchlist"})

#: The exclusion the docstring above promised, made EXECUTABLE (round-1 review,
#: 2026-08-06). Naming these kinds in prose and then re-admitting them through
#: the percent/move-phrase route below is how the freshness gate came to judge
#: the exact lanes it says it does not own: measured on the live outbox,
#: 157/224 `breaking`, 10/20 `macro`, 7/20 `event` and 1/20 `education` items
#: returned a non-empty action claim, so a WEEKLY jobless-claims print was
#: quarantined for being one session old with a receipt reading "a percent move
#: claim", and a wire flash retried across a session boundary died with it — a
#: live path since 91b0877057f made a Buffer rate limit retry instead of delete.
#:
#: THE RULE (commissioning ruling R2): kind exclusion WINS over the percent
#: heuristic. If the kind is on this list the freshness gate does not judge it,
#: whatever the text looks like; route 2 may only ADMIT kinds that are not
#: already excluded. A weekly macro print is not a tape read, and a wire retry
#: is not stale because a session rolled — both perish on their own clocks (the
#: reaper's 3h TTL, the numeric-fact cooldown).
NON_ACTION_KINDS: frozenset[str] = frozenset(
    {"macro", "event", "education", "insider", "congress", "breaking"})

#: Phrases that report a PRICE MOVE. Used to answer "does this post claim market
#: action" for kinds outside ACTION_KINDS.
#:
#: BROAD ON PURPOSE, and it is safe to be broad here in a way it is nowhere else
#: in this module: this predicate is only ever consulted about an item that is
#: ALREADY a session stale, so its false positives are posts that should not
#: ship anyway. Its false NEGATIVES are the expensive direction, so the list
#: leans inclusive.
_ACTION_PHRASES: tuple[str, ...] = (
    "closed", "closes", "closing high", "closing low", "close above",
    "close below", "rallied", "rallies", "surged", "surges", "jumped",
    "jumps", "popped", "spiked", "ripped", "ran", "slid", "slides", "fell",
    "falls", "dropped", "drops", "sank", "sold off", "selling off", "gapped",
    "gaps", "bounced", "bounces", "reclaimed", "reclaims", "broke", "breaks",
    "held", "holds", "tagged", "printed", "green close", "green closes",
    "red close", "red closes", "record high", "yearly high", "fresh high",
    "fresh low", "new high", "new low", "off the highs", "off the lows",
    "up on the", "down on the", "bid up", "marked up", "marking up",
)
_ACTION_RE = _word_re(_ACTION_PHRASES)

#: A percent claim of any sign. "+1.9% avg" — the theme_list defect verbatim —
#: carries no verb at all, so the verb list above cannot see it.
_ANY_PCT_RE = re.compile(r"(?<![\w])[+-]?\d{1,3}(?:\.\d{1,2})?\s?%")


def market_action_claim(text: str, kind: str = "") -> str:
    """The reason this post claims market ACTION, or "" when it does not.

    Two routes, because the two live shapes of the defect look nothing alike:
    a `kind` whose whole job is a price read, and a post of some other kind
    whose sentence reports a move ("$WDC falls -4.03%").

    KIND EXCLUSION IS CHECKED FIRST AND IS FINAL. See :data:`NON_ACTION_KINDS`:
    route 2 exists to ADMIT kinds this gate has no opinion about, never to
    re-admit one it has already excluded.
    """
    k = str(kind or "").strip().lower()
    if k in ACTION_KINDS:
        return f"kind '{k}' is a tape read"
    if k in NON_ACTION_KINDS:
        return ""
    body = str(text or "")
    m = _ACTION_RE.search(body)
    if m is not None:
        return f"move phrase '{m.group(1).lower()}'"
    if _ANY_PCT_RE.search(body):
        return "a percent move claim"
    return ""


def stale_session_violations(text: str, *, now: datetime, fact_asof: object,
                             kind: str = "") -> list[str]:
    """Reasons this post's tape claim is a SESSION out of date. [] = publishable.

    Two legs, and they catch different halves of the same law:

      ``stale_session:<fact>!=<live>`` — the item's own facts belong to a session
        that is no longer the live one. This is the 35h theme_list: its copy was
        internally consistent, and the thing that had changed was the clock.
      ``stale_session_claim:<claimed>!=<live>`` — the COPY names a session other
        than the live one, whatever the item's stamp says. This is the leg that
        survives a mis-stamped row.

    THE BOUNDARIES, each one a way this gate could have been worse than the
    defect (a gate that silences a lane is the failure mode of every previous
    attempt at this):

      * SAME-DAY AFTER-CLOSE SHIPS. :func:`live_session` spans the whole ET
        calendar day of a session, so a 21:00 ET post about that afternoon's
        close is current, not stale. The window closes when the NEXT session
        opens, exactly as the operator stated it.
      * A MISSING OR MALFORMED ``as_of`` IS NOT STALE. `fact_asof` that will not
        parse yields no fact session, and leg one simply does not run — a
        garbled stamp must never be the reason a good post dies. Leg two still
        applies, because it reads the copy rather than the stamp.
      * WEEKENDS AND HOLIDAYS SHIP. `live_session` walks back to Friday, so a
        Friday-stamped post published on Saturday is current all weekend and
        dies on Monday's open. That is the honest reading of "the next session
        kills it".
      * A POST THAT CLAIMS NO MARKET ACTION IS NOT JUDGED **BY LEG ONE**. An
        education post or a filing summary has no session to be stale about —
        and neither is any kind in :data:`NON_ACTION_KINDS`, whatever numbers
        its copy carries. LEG TWO STILL RUNS FOR EVERY KIND: it fires only when
        the copy NAMES a past session, which is a falsity in the words on the
        page rather than a statement about how that kind perishes.
    """
    body = str(text or "")
    if not body.strip():
        return []
    # THE TWO LEGS RUN INDEPENDENTLY (round-2 review, m4). Returning early on an
    # empty action claim disarmed BOTH legs for the six excluded kinds, and only
    # leg 1 was ever what ruling R2 was about. Leg 1 asks a PERISHABILITY
    # question — has this post's session been overtaken — and a weekly print or a
    # wire flash perishes on its own clock, so the kind exclusion belongs there.
    # Leg 2 asks a FALSITY question about the copy's own words: a post that says
    # "today" and then reports Tuesday's tape contradicts ITSELF, and that is
    # wrong for a macro post exactly as it is wrong for a chart.
    why = market_action_claim(body, kind)

    live = live_session(now)
    out: list[str] = []

    fact_day = _as_date(fact_asof) if why else None
    fact_session = session_of(fact_day) if fact_day is not None else None
    if fact_session is not None and fact_session != live:
        # A fact session AHEAD of the live one is a forward-booked row, not a
        # stale one; `dead_date_future_tense` and the booking lanes own that
        # case and this gate must not double-refuse it.
        if fact_session < live:
            out.append(
                f"stale_session:{fact_session.isoformat()}!={live.isoformat()} "
                f"({why}; the {weekday_name(live)} session has opened)")

    claimed = _stale_claim_in_copy(body, now=now, live=live)
    if claimed is not None:
        # The two shapes get two receipts, because they are two different
        # defects and the operator reads these strings. A post that says only
        # "on Tuesday" on Wednesday is one session late; a post that says
        # "today … on Tuesday" is claiming two sessions at once, which is false
        # on its face whatever the clock says.
        if _TODAY_RE.search(body) and current_session(now) == live:
            out.append(
                f"stale_session_claim:{claimed.isoformat()}!={live.isoformat()} "
                f"(copy claims today AND {weekday_name(claimed)}'s tape)")
        else:
            out.append(
                f"stale_session_claim:{claimed.isoformat()}!={live.isoformat()} "
                f"(copy names {weekday_name(claimed)}'s tape)")

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


# ── the numeric-fact fingerprint (operator 2026-08-06) ───────────────────────
#
# "holy fuck the 203k claims it was posted so many times everywhere."
#
# MEASURED on the live corpus: ONE fact — 203k jobless claims, 8.6% below a year
# ago, 5.0% GDPNow, 2.1% median CPI — was generated on FIVE days across SEVEN
# accounts and TWO of them POSTED. Every text-similarity gate in the estate saw
# seven different strings, because they ARE seven different strings:
#
#   "203k claims a week this month, 8.6% below a year ago"          (posted)
#   "Jobless claims averaging 203k this month, 8.6% below…"          (posted)
#   "claims hit 203k this month, 8.6% below a year ago"
#   "203k jobless claims, 5.0% GDPNow, 2.1% median CPI"
#   "Jobless claims: 203 thousand a week, 8.6% below a year ago"
#
# And `fact_anchor_keys` above could not see them either: its two key families
# are RATIOS over a named universe and a single-ticker PERCENT. A weekly macro
# print is neither, so it was invisible to the one gate built for exactly this.
#
# THE LAW: a numeric fact posts once per cooldown window, NETWORK-WIDE,
# fingerprinted on (indicator, VALUE). The value half is what keeps this from
# being a mute button: GDPNow moving 5.0 -> 5.9 is NEWS and ships, while the
# same 203k reworded for a fourth desk does not. Both live in the corpus on the
# same night, and a key on the indicator alone would have killed the new print.

#: Canonical indicator slug -> the ways copy names it. Aliases collapse into one
#: slug because the desks genuinely rotate through them: "GDPNow", "the Atlanta
#: Fed", and a bare "Growth:" label are three names for one number, and keying
#: them apart is how three phrasings of one print all read as fresh.
#: THE PER-WEEK COUNT IDIOM (correction C1, 2026-08-06). A desk does not always
#: write the indicator's name: ob-2026-08-04-45e4653200 opens "203 thousand a
#: week this month, 8.6% below a year ago." and names no indicator at all in its
#: first line. That cost nothing while an unkeyed lead meant "exempt", and it
#: became the whole defect the moment C1 made the cooldown fall back to the
#: earliest keyable claim ANYWHERE in the body: the fallback then keyed the post
#: on the 5.0% GDPNow print sitting on line TWO as framing, and that mis-key
#: propagated — the post owned ``macro:gdpnow:5pct`` for seven days and took
#: down three unrelated 08-06 posts, including ob-2026-08-06-33dbf95911, whose
#: subject is narrow leadership and which quotes 5% only to frame it. Measured:
#: `event` went 1/2 -> 0/2 on today's plan, a lane at zero, on a number no post
#: involved was actually about.
#:
#: A COUNT IN THOUSANDS QUOTED PER WEEK IS THE WEEKLY CLAIMS PRINT. Nothing else
#: in this domain is published that way, which is why the idiom can carry the
#: indicator's name on its own. The lookbehind is what keeps it that narrow: the
#: phrase only counts as a name when it directly follows a `k`/`thousand` value,
#: so an ordinary "up 2% a week" never becomes a claims print.
_CLAIMS_PER_WEEK = r"(?:(?<=k)|(?<=thousand))\s+a\s+week"

_MACRO_NAME_ALIASES: tuple[tuple[str, str], ...] = (
    ("claims", r"claims|" + _CLAIMS_PER_WEEK),
    ("gdpnow", r"gdpnow|gdp\s*now|gdp\s*track\w*|atlanta\s*fed|\bgrowth\b|\bgdp\b"),
    ("cpi", r"\bcpi\b|inflation|cleveland"),
    ("payrolls", r"payrolls?|nonfarm|\bnfp\b|jobs report"),
    ("unemployment", r"unemployment rate|jobless rate"),
    ("pce", r"\bpce\b"),
    ("ism", r"\bism\b|\bpmi\b"),
    ("retail_sales", r"retail sales"),
)
_MACRO_NAME_RES: tuple[tuple[str, "re.Pattern[str]"], ...] = tuple(
    (slug, re.compile(pat, re.IGNORECASE)) for slug, pat in _MACRO_NAME_ALIASES)

#: The units each indicator is actually QUOTED in (round-1 review, 2026-08-06).
#: A weekly claims print is a count of people; GDPNow is an annualised rate. So
#: ``macro:gdpnow:203k`` is not a near-miss, it is impossible — and it was live:
#: ob-2026-08-04-45e4653200 ("203 thousand a week this month … GDPNow just ticked
#: up to 5.0%") emitted exactly that, because the only indicator name in range
#: was the wrong one. Filtering candidate names by unit costs nothing when the
#: copy is well-formed and deletes the whole nonsense-key class when it is not.
#: A count indicator keeps `pct` because the desks quote it both ways ("203k
#: claims, 8.6% below a year ago").
_MACRO_UNITS: dict[str, frozenset[str]] = {
    "claims": frozenset({"k", "m", "pct"}),
    "payrolls": frozenset({"k", "m", "pct"}),
    "gdpnow": frozenset({"pct"}),
    "cpi": frozenset({"pct"}),
    "unemployment": frozenset({"pct"}),
    "pce": frozenset({"pct"}),
    "ism": frozenset({"pct"}),
    "retail_sales": frozenset({"pct"}),
}

#: What ends a clause. A name on the far side of one of these is not THIS
#: number's name: "203k jobless claims, 5.0% GDPNow" hands 5.0% to GDPNow and not
#: to the claims two characters to its left. A colon is deliberately absent — it
#: is how a label is attached to its value ("Growth: 5.9%", "Jobless claims: 203
#: thousand"), which is one of the three shapes this has to get right.
_CLAUSE_BREAK_RE = re.compile(r"[,;.!?\n|·—–/]|\bmeanwhile\b", re.IGNORECASE)

#: Weight on a name that FOLLOWS its value, used only to break ties between two
#: equally-attached candidates. English attaches a label to what precedes it more
#: often than not ("Claims: 203k Payrolls: 198k"), so a following name has to be
#: strictly nearer to win.
_FOLLOWING_NAME_PENALTY = 2

#: The value shapes a macro print is quoted in. A BARE integer is deliberately
#: absent: ordinary copy counts things ("the 4th time", "23 sessions") and
#: fingerprinting those would collapse unrelated posts onto one key.
_MACRO_VALUE_RES: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("k", re.compile(r"(?<![\w.])(\d{1,4}(?:\.\d{1,2})?)\s?(?:k\b|thousand\b)",
                     re.IGNORECASE)),
    ("k", re.compile(r"(?<![\w.])(\d{1,3}),000(?![\d])")),
    ("pct", re.compile(r"(?<![\w])(\d{1,3}(?:\.\d{1,2})?)\s?%")),
    ("m", re.compile(r"(?<![\w.])(\d{1,4}(?:\.\d{1,2})?)\s?(?:m\b|million\b)",
                     re.IGNORECASE)),
)

#: How far from a number an indicator name may sit and still be ITS name. Sized
#: to one clause of published copy: "Jobless claims are averaging 203 thousand a
#: week this month" is 44 characters between the two.
_MACRO_PROXIMITY_CHARS = 70

#: Every macro key starts with this, so a caller can give the family its own
#: cooldown window without re-parsing the key.
MACRO_KEY_PREFIX = "macro:"

#: Vocabulary that says the number belongs to a COMPANY, not to the economy
#: (round-1 review, 2026-08-06). The no-cashtag scope below closes the "revenue
#: growth of 12%" class only when a cashtag is present, so copy that names a
#: company in WORDS — an education post, an event recap, a wire summary — still
#: keyed as ``macro:gdpnow:12pct`` and could terminally quarantine a genuine
#: GDPNow print at the same number. Kept TIGHT on purpose: "quarter", "annual"
#: and "growth" are all ordinary macro words, and suppressing on those would
#: delete "Growth: 5.9% annual rate this quarter", which is the print this whole
#: mechanism exists to let through. Suppression is the PERMISSIVE direction (a
#: post ships rather than dies), which is the right way for this to be wrong.
_COMPANY_SCOPE_RE = re.compile(
    r"(?<![\w])(?:revenue|revenues|earnings per share|\beps\b|gross margin|"
    r"operating margin|guidance|bookings|backlog|subscribers|billings|"
    r"same-?store|free cash flow|buybacks?|share repurchase|"
    r"the (?:cloud|ads?|services|data ?cent(?:re|er)) (?:unit|segment|business))"
    r"(?![\w])",
    re.IGNORECASE,
)


def _name_is_attached(body: str, v_lo: int, v_hi: int,
                      n_lo: int, n_hi: int) -> bool:
    """Is the indicator name at [n_lo, n_hi) in the same CLAUSE as the value?

    "203k jobless claims, 5.0% GDPNow, 2.1% median CPI" is the shape that broke
    the symmetric nearest-wins metric: 5.0% sits two characters from "claims"
    and one from "GDPNow", and only the comma says which one is its name.
    """
    if n_lo >= v_hi:
        between = body[v_hi:n_lo]
    else:
        between = body[n_hi:v_lo]
        # Another number between the name and this value means the name has
        # already been spent: in "Claims: 203k Payrolls: 198k", "Claims" belongs
        # to 203k and cannot also reach across it to 198k.
        if any(ch.isdigit() for ch in between):
            return False
    return _CLAUSE_BREAK_RE.search(between) is None


def _macro_fact_hits(body: str) -> list[tuple[int, str]]:
    """(value offset, key) for every macro print in `body`. See `macro_fact_keys`."""
    if not body.strip() or _CASHTAG_RE.search(body):
        return []
    if _COMPANY_SCOPE_RE.search(body):
        return []

    names: list[tuple[str, int, int]] = []
    for slug, rx in _MACRO_NAME_RES:
        for m in rx.finditer(body):
            names.append((slug, m.start(), m.end()))
    if not names:
        return []

    hits: list[tuple[int, str]] = []
    for unit, rx in _MACRO_VALUE_RES:
        for m in rx.finditer(body):
            try:
                val = float(m.group(1))
            except (TypeError, ValueError):  # pragma: no cover - regex-guarded
                continue
            lo, hi = m.start(), m.end()
            best: tuple[int, int, str] | None = None
            for slug, n_lo, n_hi in names:
                if unit not in _MACRO_UNITS.get(slug, frozenset()):
                    continue
                follows = n_lo >= hi
                gap = n_lo - hi if follows else lo - n_hi
                if gap > _MACRO_PROXIMITY_CHARS:
                    continue
                # ATTACHMENT IS REQUIRED, not merely preferred. A number whose
                # only candidate name sits across a full stop has no name that
                # can be read off the page, and GUESSING one is what produced
                # `macro:gdpnow:203k` and split one 8.6% claims print across two
                # keys that could never collide. No key is the honest answer and
                # the permissive one: the caller treats an empty set as "cannot
                # judge" and lets the post through.
                if not _name_is_attached(body, lo, hi, n_lo, n_hi):
                    continue
                rank = (gap * (_FOLLOWING_NAME_PENALTY if follows else 1),
                        1 if follows else 0, slug)
                if best is None or rank < best:
                    best = rank
            if best is not None:
                hits.append((lo, f"{MACRO_KEY_PREFIX}{best[2]}:{val:g}{unit}"))
    return hits


def macro_fact_keys(text: str) -> frozenset[str]:
    """(indicator, value) fingerprints of the macro prints a post quotes.

    NO-CASHTAG SCOPE, and it is load-bearing. "Growth" and "inflation" are also
    ordinary words about a COMPANY ("revenue growth of 12%"), and keying those
    would let two desks writing about two different names collide on
    ``macro:gdpnow:12pct`` — a terminal quarantine earned by a coincidence. Every
    post in the measured 203k family is cashtag-free, because a macro print is
    not about a ticker; requiring that costs the gate nothing real and closes the
    whole false-positive class. :data:`_COMPANY_SCOPE_RE` closes the half of it
    that names the company in words instead of a cashtag.

    A number takes ONE indicator name, and which one is decided in this order:

      1. the name has to be quoted in the value's UNIT (:data:`_MACRO_UNITS`) —
         GDPNow is never 203 thousand;
      2. names in the same CLAUSE beat names across a comma or a full stop
         (:func:`_name_is_attached`);
      3. then nearest wins, with a following name weighted by
         :data:`_FOLLOWING_NAME_PENALTY`, and a preceding name breaking the tie.

    ONE NAME, NOT ALL OF THEM. Pairing every name in range was the first cut and
    it manufactured a cross product — "203k claims … 2.1% median CPI" emitted
    ``macro:cpi:203k`` and ``macro:claims:2.1pct`` as well as the two real keys,
    so an unrelated post quoting 2.1% claims would have collided with it.

    THE THREE SHAPES THAT HAVE TO WORK, all live in the corpus and all pinned:
    ``"203k jobless claims"`` (value first), ``"GDPNow has growth at 5.9%"``
    (name first), ``"Growth: 5.9%"`` (label). A plain symmetric gap got the first
    one wrong — it handed "2.1% median CPI" to the GDPNow two characters behind
    it — which is how one 2.1% CPI print ended up on two keys that could never
    collide, the exact dedup failure this fingerprint exists to fix.
    """
    return frozenset(k for _pos, k in _macro_fact_hits(str(text or "")))


def fact_anchor_keys(text: str, kind: str = "") -> frozenset[str]:
    """The source facts a post is anchored on, as stable comparable keys.

    Two posts sharing a key are two dressings of ONE fact — the defect class C
    shape, where a single Friday breadth read was fanned into six slots across
    four desks with interchangeable hedges.

      ``ratio:4of11:sector``      — kind-agnostic (one universe, one true value)
      ``pct:mover:AMZN:15.3``     — kind- and ticker-scoped, lead claim only
      ``macro:claims:203k``       — an indicator print at a VALUE, cashtag-free
                                    copy only (see :func:`macro_fact_keys`)

    Empty set = no extractable anchor; callers must treat that as "cannot judge"
    and let the post through, never as "no duplicate".
    """
    return frozenset(k for _pos, k in _fact_anchor_hits(text, kind))


def _fact_anchor_hits(text: str, kind: str = "") -> list[tuple[int, str]]:
    """(offset of the numeric claim, key) for every anchor in `text`."""
    body = str(text or "")
    k = str(kind or "").strip().lower()
    hits: list[tuple[int, str]] = []

    for m in _RATIO_RE.finditer(body):
        n, total, noun = m.group(1), m.group(2), _stem(m.group(3))
        if n == total:
            continue  # saturated: a definition, not a read (market_facts law)
        hits.append((m.start(), f"ratio:{int(n)}of{int(total)}:{noun}"))

    tickers = {m.group(1) for m in _CASHTAG_RE.finditer(body)}
    if len(tickers) == 1:
        lead = _PCT_RE.search(body)
        if lead is not None:
            try:
                val = float(lead.group(1))
            except ValueError:
                val = None  # type: ignore[assignment]
            if val is not None:
                hits.append((lead.start(),
                             f"pct:{k}:{next(iter(tickers))}:{val:g}"))

    if k not in _MACRO_KEY_EXEMPT_KINDS:
        hits += _macro_fact_hits(body)

    return hits


# `lead_segment` (the span of the first non-empty line) lived here until
# correction C1. It was the round-2 cut's way of saying "look in the headline
# first", and once C1 replaced "empty lead == exempt" with "fall back to the
# earliest claim in the body" it stopped being able to change any answer: the
# first non-empty line is by definition the lowest offset in the text, so
# filtering to it before taking the minimum is the same function. It was
# verified dead by mutation — swapping the filtered scope for the whole body
# left every marketing test green — and dead code that documents a gate it no
# longer gates is worse than no code. The rule now lives once, in
# `lead_fact_keys`.


def lead_fact_keys(text: str, kind: str = "") -> frozenset[str]:
    """The post's LEAD fact, as anchor keys. The cooldown's unit (ruling R1).

    THE DEFECT THIS EXISTS FOR (round-1 review, 2026-08-06). The fan-out gate
    read :func:`fact_anchor_keys` over the WHOLE body and refused on the first
    key any live sibling owned, so a post whose lead fact was brand new but
    which also recited last week's numbers as framing died whole. Measured on
    the live outbox that night: macro 0/6 survivors, event 0/2, mover 0/2, and
    BOTH carriers of the genuinely new 5.0 -> 5.9 GDPNow print refused — one on
    ``macro:claims:203k`` owned by a post four days older. Zero posts carrying
    the new number reached the network, which is the precise opposite of the law
    the fingerprint was built to serve ("a NEW number is news and ships").

    THE RULE. The cooldown keys the LEAD fact — the first numeric claim in the
    post, which is the one in the headline when the headline carries one.
    Supporting numbers later in the body are CONTEXT: they neither trigger the
    cooldown nor claim an anchor of their own. "GDPNow 5.9%, up from 5.0% last
    week" is what a human analyst writes and it ships; a post whose LEAD is the
    same 203k that shipped on 08-02 does not. The defect the operator reported
    was never a post that mentioned a number, it was the same number being the
    WHOLE post, five days running.

    SYMMETRIC BY CONSTRUCTION. Ownership is claimed on the same keys refusal is
    tested against, so a post that merely cites 203k in its third line cannot
    quietly claim that anchor and starve the post whose lead it actually is.

    CORRECTION C1 (operator 2026-08-06, after the round-2 review): AN EMPTY LEAD
    LINE MEANS "LOOK FURTHER", NEVER "EXEMPT". The first cut of this function
    returned ``frozenset()`` whenever the first non-empty line carried no keyable
    number, and both callers read an empty set as "cannot judge, let it through"
    — so a post whose opening line is prose was exempt from the cooldown
    ENTIRELY. The reviewer built and verified it: "Here is what the labor market
    looks like right now / Jobless claims 203k a week, 8.6% below a year ago.
    The Atlanta Fed has growth at 5.0% this quarter." keyed NOTHING and shipped
    against any number of siblings, and 40 of the 180 corpus items carrying a
    whole-body key carried none. Live, it was the operator's own defect walking
    through the gate: ob-2026-08-04-45e4653200 leads on the 203k print itself.

    So the lead FACT is the EARLIEST keyable claim in the body. A post with
    numbers is always judged on some claim; only a post with no keyable number
    at all yields an empty set, and that is the honest "nothing to judge".

    AND THAT IS ONE RULE, NOT TWO. The first cut of this correction kept a
    `lead_segment` filter (the first non-empty line) and fell back to the whole
    body only when that came up empty. That span is by definition the LOWEST
    offset in the text, so "prefer the lead line, else look further" and "take
    the earliest claim in the body" agree on every possible input — the filter
    was dead code no mutation could reach (verified: swapping the filtered scope
    for the whole body left every marketing test green). The rule is therefore
    stated once, where a mutation can pin it. The ruling's protection is
    unharmed: "GDPNow 5.9%, up from 5.0% last week" still keys the 5.9% alone,
    because the 5.9% comes first.
    """
    hits = _fact_anchor_hits(text, kind)
    if not hits:
        return frozenset()
    first = min(pos for pos, _k in hits)
    return frozenset(key for pos, key in hits if pos == first)


def ride_along_keys(text: str, kind: str = "") -> frozenset[str]:
    """The keys this post carries that are NOT its lead fact. Its RECITAL.

    The other half of the cooldown's unit. :func:`lead_fact_keys` says what the
    post is ABOUT; this says what it is quoting on the way past. Kept as its own
    function because the two callers must count the same set — a bound applied
    to two different notions of "supporting number" is not a bound.
    """
    return fact_anchor_keys(text, kind) - lead_fact_keys(text, kind)


#: How many ALREADY-OWNED supporting facts may ride along behind a new lead.
#:
#: CORRECTION C2 (operator 2026-08-06, after the round-2 review). Keying the
#: cooldown on the lead fact alone let a post whose lead refreshes daily carry an
#: unlimited stale body — the 203k defect wearing a hat. The reviewer built it:
#: "4 of 11 sectors green today / 203k jobless claims a week this month, 8.6%
#: below a year ago. The Atlanta Fed is printing 5.0% growth and median CPI is
#: 2.1%." keys only ``ratio:4of11:sector``, and the breadth count moves nearly
#: every session, so the whole weekly macro paragraph rides through the 7-day
#: window every night on every account.
#:
#: ONE is the bound because ONE is what the ruling's own worked example needs.
#: "GDPNow 5.9%, up from 5.0% last week" recites exactly one owned number, and
#: reciting a prior print to frame a new one is what an analyst writes. Two or
#: more owned non-lead facts is not framing, it is a recital with a fresh
#: headline, and the post is refused. Config: ``publish.fact_ride_along_max``.
FACT_RIDE_ALONG_MAX_DEFAULT: int = 1


def fact_ride_along_max(value: object = None) -> int:
    """The configured ride-along bound, with the shipped floor. Typo-safe.

    Same fail direction as :func:`fact_cooldown_days`: a malformed entry falls
    back to the default rather than raising, because this figure decides whether
    a post ships and a YAML typo must not become an unbounded — or zero — bound.
    A negative value is read as "unbounded", which is the only way to turn the
    correction off deliberately rather than by accident.
    """
    if value is None:
        return FACT_RIDE_ALONG_MAX_DEFAULT
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return FACT_RIDE_ALONG_MAX_DEFAULT


#: Kinds the numeric-fact cooldown does NOT apply to. A relayed wire flash is a
#: report of what a source said, not our desk quoting a print for the fourth
#: time, and it already has two dedup mechanisms of its own (the story key and a
#: 3h TTL). Including it measured badly for one specific reason: the Fed's 2%
#: inflation TARGET appears in almost every central-bank headline, so a 7-day
#: hold on ``macro:cpi:2pct`` would mute the biggest lane in the queue for a week
#: on the strength of a number nobody is reporting as news.
_MACRO_KEY_EXEMPT_KINDS: frozenset[str] = frozenset({"breaking"})


#: Cooldown windows, in days, by key family. Claims and GDPNow are WEEKLY
#: prints, so one week is the shape: inside it there is no new number to report
#: and a second post is the same fact reworded; past it the print has been
#: refreshed and a repeat is legitimately news again. The tape families keep the
#: 5-day window the fan-out gate shipped with.
FACT_COOLDOWN_DAYS_DEFAULT: dict[str, int] = {"macro": 7, "default": 5}


def fact_cooldown_days(key: str, windows: dict | None = None) -> int:
    """How many days `key` stays claimed. Config-driven, with the shipped floor.

    A malformed or missing config entry falls back to the default rather than
    raising: this figure decides whether a post ships, and a typo in YAML must
    not become an unbounded — or zero — cooldown.
    """
    table = dict(FACT_COOLDOWN_DAYS_DEFAULT)
    for k, v in (windows or {}).items():
        try:
            table[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    family = str(key or "").split(":", 1)[0] or "default"
    try:
        return int(table.get(family, table.get("default", 5)))
    except (TypeError, ValueError):  # pragma: no cover - coerced above
        return 5


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
