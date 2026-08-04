"""W4 — DISPLAY-TIER earnings-catalyst math for board rows.

Pure functions over dates + a close series.  No I/O, no network, no store reads:
``scripts/build_stock_library`` already holds both the earnings assessment
(``engine.earnings_blackout.assess``) and the close panel, so this module only
shapes what the builder already has into display fields.

TIER — **display** (PROPHET_US_TREND_INTELLIGENCE masterplan §0 G0.1).  Nothing here
gates, ranks, sizes, filters, or vetoes.  ``engine/earnings_blackout.assess`` remains
the ONE earnings authority in the pick chain and its semantics are untouched by this
module — including its fail-open behaviour on a stale row.  W4's answer to that silence
is the collector's ``::warning title=earnings-staleness`` alarm plus the ``stale`` flag
these fields carry, NOT a change to the veto.

CALENDAR — ``lib.nyse_calendar`` (holiday-exact).  ``earnings_blackout`` builds its own
trading-day index from the price panel and extends it with ``pd.bdate_range``, which
does NOT drop exchange holidays; its documented imprecision is up to +1 session per
holiday in the window.  So the veto's ``days_to_earnings`` may read one session LONGER
than this module's ``days_to_report`` across a holiday week.  That divergence is
deliberate and one-directional: the SCORED number stays byte-identical (never re-derived
here), while the DISPLAYED number is exact.

Field vocabulary produced here (all display-tier):
  ``days_to_report``    signed trading-day distance to next_date (negative = already
                        reported N sessions ago); ``None`` when unknowable.
  ``reports_within_7``  ``0 <= days_to_report <= 7``; ``None`` (not ``False``) when
                        ``days_to_report`` is None — a ``False`` there would assert
                        "does not report within 7 days", which a stale row cannot know.
  ``stale``             TRI-STATE.  ``True`` = the row's ``as_of`` is older than
                        ``STALE_AGE_TD`` sessions, the same threshold at which the veto
                        fails open.  ``False`` = checked and inside it.  ``None`` = the
                        freshness question was never asked (see
                        :func:`fields_from_assessment`) — never read a ``None`` as fresh.
  ``post_earnings_move`` ``{date, day0, day0_move_pct, basis, ...}`` — see :func:`reaction`.

NAMING (commissioner ruling, W4 review).  The board-row key is ``post_earnings_move``,
not ``earnings_reaction``: the latter is already a hot-tape TRIGGER name
(``engine/marketing/hot_tape.py``, ``hot_tape_wire.py``, ``scripts/hot_tape_radar.py``)
for "the gap a report opened".  Different artifact, but close enough in meaning that a
shared token would make every future grep ambiguous, so the two vocabularies are kept
grep-separable.  The function stays :func:`reaction` — module-scoped, unambiguous as
``earnings_catalyst.reaction``, and never the emitted key.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from lib import nyse_calendar

#: Trading-day age past which a row's ``as_of`` is stale.  Mirrors
#: ``engine.earnings_blackout._STALE_AGE_TD`` on purpose: the display fields must go
#: null at exactly the age where the veto starts failing open, so a reader never sees
#: a confident countdown sitting on a row the veto has already stopped trusting.
STALE_AGE_TD = 10

#: ``reports_within_7`` window (trading days).
REPORTS_SOON_TD = 7

#: How far back :func:`reaction` will look for a just-passed report (trading days).
REACTION_LOOKBACK_SESSIONS = 5

#: Nasdaq ``next_time`` tokens (and the builder's display labels for them) that mean
#: the print lands AFTER the close, so the market's first verdict is the NEXT session.
_AFTER_HOURS = {"time-after-hours", "after close", "after-hours", "amc"}


# ── date plumbing ──────────────────────────────────────────────────────────────

def as_date(value) -> date | None:
    """Best-effort date from ISO (``2026-08-03``) or Nasdaq's ``M/D/YYYY``.

    Returns ``None`` for anything unparseable — never raises.  Timestamps and
    datetimes are reduced to their calendar date.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s or s.lower() in {"nan", "nat", "none"}:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def trading_days_between(start: date, end: date) -> int:
    """Signed session distance from ``start`` to ``end``.

    Counts sessions STRICTLY AFTER the earlier date, up to and INCLUDING the later
    one — the same position-difference semantics as
    ``engine.earnings_blackout._td_distance``, but holiday-exact:

      * same day                     → 0
      * Friday → Monday              → 1   (3 calendar days, 1 session)
      * Friday → Saturday/Sunday     → 0   (no session in between)
      * Wed → Fri across Thanksgiving→ 1   (Thursday is closed)

    Negative when ``end`` precedes ``start``.
    """
    if start == end:
        return 0
    if end > start:
        return len(nyse_calendar.sessions_between(start + timedelta(days=1), end))
    return -len(nyse_calendar.sessions_between(end + timedelta(days=1), start))


def as_of_age_td(as_of, today: date) -> int | None:
    """Trading-day age of an ``as_of`` stamp, or ``None`` when unparseable."""
    d = as_date(as_of)
    if d is None:
        return None
    return max(0, trading_days_between(d, today))


# ── the board-row catalyst fields ──────────────────────────────────────────────

def _fields(next_date, today: date, *, stale: bool | None, age: int | None) -> dict:
    """The four display fields, given a settled staleness verdict.

    ``stale`` is TRI-STATE: ``True`` (aged out), ``False`` (checked and fresh), and
    ``None`` (**never checked** — see :func:`fields_from_assessment`).  ``None`` is not
    cosmetic: it is the difference between "this row is current" and "nobody asked",
    and collapsing the second into the first is the same confident silence W4 exists to
    remove.  An unchecked row still reports ``days_to_report`` — the date it holds is a
    recorded fact — but the flag says we cannot vouch for the stamp behind it.
    """
    if stale:
        return {"days_to_report": None, "reports_within_7": None, "stale": True,
                "as_of_age_td": age}
    nd = as_date(next_date)
    if nd is None:
        return {"days_to_report": None, "reports_within_7": None, "stale": stale,
                "as_of_age_td": age}
    dtr = trading_days_between(today, nd)
    return {"days_to_report": dtr,
            "reports_within_7": bool(0 <= dtr <= REPORTS_SOON_TD),
            "stale": stale, "as_of_age_td": age}


def catalyst_fields(next_date, as_of, today: date,
                    *, stale_age_td: int = STALE_AGE_TD) -> dict:
    """Display-tier catalyst fields for one board row, from raw store columns.

    Parameters mirror the earnings store's own columns.  ``today`` is explicit
    (never ``date.today()`` inside) so the builder and the tests share one clock.

    Staleness is the FIRST gate: a row whose ``as_of`` is older than
    ``stale_age_td`` sessions (or unparseable) reports ``days_to_report=None`` and
    ``stale=True``.  We know when the store last looked; we do not know whether the
    date it recorded is still true, and a countdown printed off a six-week-old stamp
    is exactly the confident-but-wrong shape W4 exists to remove.
    """
    age = as_of_age_td(as_of, today)
    return _fields(next_date, today, stale=(age is None) or (age > stale_age_td), age=age)


def fields_from_assessment(assessment: dict | None, today: date) -> dict:
    """:func:`catalyst_fields` for an ``engine.earnings_blackout.assess()`` result.

    Reuses the assessment's OWN ``stale`` verdict instead of re-deriving one from
    ``as_of``: the veto and the display must never disagree about whether a row is
    trustworthy.  (The two would drift anyway — assess builds a holiday-blind calendar,
    this module a holiday-exact one, so an independent age could sit one session either
    side of the same 10-session line.)

    THE NOT-CHECKED CASE.  ``assess`` short-circuits several paths BEFORE it reads
    ``as_of`` at all — ``next_date_in_past`` (much the most common on a live board),
    ``next_date_missing``, ``next_date_unparseable``, ``ticker_not_in_store``.  Each
    returns ``stale=False`` with ``as_of_age_td=None``, meaning "no verdict", not
    "fresh".  Taking that ``False`` at face value would have stamped ``stale: false``
    on PLTR's genuinely six-week-old row — the W4 complaint, recursed one level down.
    So ``stale=False`` is honoured only when an age accompanies it; otherwise the flag
    is ``None``.

    A missing assessment maps to ``stale=True``: the conservative direction for a
    display field is to suppress, not to print a countdown nothing vouched for.
    """
    if not assessment:
        return {"days_to_report": None, "reports_within_7": None, "stale": True,
                "as_of_age_td": None}
    age = assessment.get("as_of_age_td")
    stale: bool | None = True if assessment.get("stale") else (None if age is None else False)
    return _fields(assessment.get("next_date"), today, stale=stale, age=age)


# ── the post-earnings reaction field ───────────────────────────────────────────

def latest_report_date(next_date, surprises, today: date) -> date | None:
    """The most recent report date the store knows has ALREADY happened.

    Two sources, because they refresh on different clocks:

    * ``next_date`` — the calendar sweep scans FORWARD from today, so a name that
      reported yesterday returns no calendar row and is carried forward with its
      previous (now-passed) ``next_date``.  That passage IS the report signal, and
      it is same-day fresh.
    * ``surprises`` — the drip's ``reported`` dates.  Authoritative but budgeted, so
      a brand-new print may not be in here yet.

    Both are considered; the max wins.  Future dates are ignored.
    """
    best: date | None = None
    for cand in (as_date(next_date), *(as_date((r or {}).get("reported"))
                                       for r in (surprises or []))):
        if cand is None or cand > today:
            continue
        if best is None or cand > best:
            best = cand
    return best


def _close_map(closes) -> dict[date, float]:
    """Normalise a pandas Series / dict of closes to ``{date: float}``."""
    if closes is None:
        return {}
    items = closes.items() if hasattr(closes, "items") else []
    out: dict[date, float] = {}
    for k, v in items:
        d = as_date(k)
        if d is None or v is None or v != v:      # NaN-safe
            continue
        try:
            out[d] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def reaction(report_date, next_time, closes, today: date,
             *, window: int = REACTION_LOOKBACK_SESSIONS) -> dict | None:
    """Day-0 price reaction to a report that landed inside the trailing ``window``.

    DAY-0 CONVENTION (deliberately simple and deterministic — one rule, no
    intraday data, no timezone arithmetic):

        day0 = the first session whose CLOSE can contain the market's verdict.
                 report after the close (``time-after-hours``) → the session AFTER
                     the report date
                 report pre-market, or time not supplied      → the report date's
                     own session (which is also the conservative default: an
                     unknown-time print is treated as already in that day's close)
        day0_move_pct = 100 * (close[day0] / close[previous session] - 1)

    So an after-hours print on Monday is graded on Tuesday's close vs Monday's, and
    a pre-market print on Monday is graded on Monday's close vs Friday's.  Both
    reduce to "the close that first saw the news, versus the close before it".

    Returns
    -------
    ``None``
        when there is no known passed report, or the report is older than
        ``window`` sessions (nothing to say — no key is attached).
    ``dict``
        ``{date, day0, day0_move_pct, basis, sessions_since}``.  ``day0_move_pct``
        is ``None`` WITH a ``basis`` naming what was missing when the close data
        needed is not in the panel — a null is disclosed, never silently dropped.
    """
    rd = as_date(report_date)
    if rd is None or rd > today:
        return None
    sessions_since = trading_days_between(rd, today)
    if sessions_since > window:
        return None

    token = str(next_time).strip().lower() if next_time is not None else ""
    after_hours = token in _AFTER_HOURS
    if after_hours:
        nxt = nyse_calendar.sessions_between(rd + timedelta(days=1),
                                             rd + timedelta(days=10))
        day0 = nxt[0] if nxt else None
    else:
        day0 = nyse_calendar.last_session_on_or_before(rd)

    out: dict = {"date": rd.isoformat(),
                 "day0": day0.isoformat() if day0 else None,
                 "day0_move_pct": None,
                 "sessions_since": sessions_since,
                 "after_hours": after_hours}
    if day0 is None or day0 > today:
        out["basis"] = "day0_not_yet_traded"
        return out

    cmap = _close_map(closes)
    if not cmap:
        out["basis"] = "no_price_data"
        return out
    prior = [d for d in cmap if d < day0]
    if day0 not in cmap or not prior:
        out["basis"] = "close_missing_for_day0" if day0 not in cmap else "no_prior_close"
        return out
    prev = max(prior)
    base = cmap[prev]
    if not base:
        out["basis"] = "prior_close_zero"
        return out
    out["day0_move_pct"] = round((cmap[day0] / base - 1.0) * 100.0, 2)
    out["prev_session"] = prev.isoformat()
    out["basis"] = "close_vs_prior_close"
    return out


# ── the whole board-row payload (one call from build_stock_library) ────────────

#: Nasdaq ``next_time`` token → the label the board chip prints.
_NEXT_TIME_LABELS = {
    "time-after-hours": "after close",
    "time-pre-market": "pre-market",
    "time-not-supplied": None,
}

#: Trading-day window inside which the proximity CHIP fires (MLC-W5 widened this from
#: the original 7; disclosure-only per MLC-R10 — it has never gated anything).
CHIP_WINDOW_TD = 14


def chip_texts(cal_days: int) -> tuple[str, str]:
    """Bilingual proximity copy, keyed on CALENDAR days (glance tier, MLC-R6).

    Calendar days on purpose: "today / tomorrow / in N d" read the way a human means
    them, and a single TRADING day across a weekend (Fri→Mon) is not calendar-tomorrow.
    """
    if cal_days <= 0:
        return "Reports today", "今日公布业绩"
    if cal_days == 1:
        return "Reports tomorrow", "明日公布业绩"
    return f"Reports in {cal_days} d", f"{cal_days}日后公布业绩"


def board_row_fields(assessment: dict | None, today: date,
                     *, closes=None, surprises=None) -> dict:
    """The complete display-tier earnings payload for one board row.

    Returns ``{"earnings_soon": dict|None, "post_earnings_move": dict|None}``.  The
    caller attaches whichever values are non-None; nothing here is a gate.

    ``earnings_soon`` has TWO shapes, and the difference is load-bearing:

    * **chip shape** — a fresh row reporting within ``CHIP_WINDOW_TD`` sessions.
      Carries ``days_to`` (calendar) + ``chip_en``/``chip_zh``.  Byte-identical to
      what shipped before W4 apart from the added catalyst keys, because every live
      consumer gates on ``days_to``: ``templates/dashboard.html.j2``
      (``_es_chip.get('days_to') is not none``), ``scripts/build_prophet``, and
      ``engine/stock_dossier``; ``engine/us_board_rank`` gates on ``in_blackout is
      True``.
    * **disclosure shape** — a STALE row, or a report outside the chip window /
      already passed.  Carries NO ``days_to`` and no chip text, so no surface renders
      it, and it is where ``stale: true`` + ``days_to_report: null`` lives.  Emitting
      this at all is W4's point: a stale row is precisely where
      ``earnings_blackout.assess`` fails open in silence.
    """
    out: dict = {"earnings_soon": None, "post_earnings_move": None}
    if not assessment:
        return out

    extra = fields_from_assessment(assessment, today)
    next_date = assessment.get("next_date")
    td = assessment.get("days_to_earnings")

    if not assessment.get("stale") and td is not None and td <= CHIP_WINDOW_TD:
        raw_nt = assessment.get("next_time")
        disp_nt = _NEXT_TIME_LABELS.get(raw_nt, raw_nt) if raw_nt else None
        nd = as_date(next_date)
        cal_days = (nd - today).days if nd is not None else td
        chip_en, chip_zh = chip_texts(cal_days)
        out["earnings_soon"] = {
            "days_to": cal_days,
            "next_date": next_date,
            "next_time": disp_nt,
            "in_blackout": bool(assessment.get("in_blackout")),
            "chip_en": chip_en,
            "chip_zh": chip_zh,
            **extra,
        }
    elif extra.get("stale") or extra.get("days_to_report") is not None:
        out["earnings_soon"] = {
            "next_date": next_date,
            "in_blackout": bool(assessment.get("in_blackout")),
            **extra,
        }

    rd = latest_report_date(next_date, surprises, today)
    if rd is not None:
        out["post_earnings_move"] = reaction(rd, assessment.get("next_time"), closes, today)
    return out
